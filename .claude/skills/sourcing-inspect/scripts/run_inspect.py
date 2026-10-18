#!/usr/bin/env python3
"""불사자 소싱기 상품검수 파이프라인 (판정 단계 — 불사자 쓰기 없음).

  fetch   캠페인 스냅샷 → <run>/snapshot.json   (API 또는 --from-file)
  prep    1차/2차 대상 선별 → 기계 판정(machine.json) → 남은 것 축약(views.json) + 썸네일
  batch   views.json → batches/batch_NNN.json + batches_index.json
  pending 남은 배치를 Workflow(inspect-fanout) args JSON 으로 출력
  merge   judged/*.json + machine.json → verdicts.json (누락·환각 보고)
  report  verdicts.json → review.html (사람이 훑어보는 결과표). --only drop|pass 면 review_drop/pass.html
  remachine 기계 규칙이 바뀌면 전 대상에 다시 적용(machine.json 갱신 — merge 때 AI 판정을 덮는다)
  recheck 기준 수정 후 '통과' 중 패턴에 걸리는 것만 AI 재판정 배치(batch_9NNN)로 만든다

정본은 run-dir 디스크다. 재실행하면 judged 파일이 있는 배치는 건너뛴다.

사용:
  PY=.venv/bin/python3; S=.claude/skills/sourcing-inspect/scripts/run_inspect.py
  $PY $S fetch  --run-dir R --campaign YWfs4MpPnVWHzYW [--from-file snap.json]
  $PY $S prep   --run-dir R --stage 1 --limit 500 --sample random
  $PY $S batch  --run-dir R --size 40
  $PY $S pending --run-dir R      # → Workflow inspect-fanout args
  $PY $S merge  --run-dir R
  $PY $S report --run-dir R
"""
import argparse
import collections
import concurrent.futures
import html
import io
import json
import os
import random
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)
_d = SCRIPT_DIR
while _d and _d != os.path.dirname(_d):
    if os.path.isdir(os.path.join(_d, "lib", "eroomlib")):
        sys.path.insert(0, os.path.join(_d, "lib"))
        WORKSPACE = os.path.dirname(_d)
        break
    _d = os.path.dirname(_d)
else:
    WORKSPACE = os.getcwd()

from rules import load_banned_cats, load_keywords, machine_judge, taobao_item  # noqa: E402

WORKER_PROMPT = os.path.join(SKILL_DIR, "rules", "worker-prompt.md")
MASTER = os.path.join(WORKSPACE, "30-knowledge", "39-naver-category", "naver-category-master.json")
# 휴지통·수집완료 상태값은 쓰기 API 실측(2단계) 때 확정한다. 지금은 아무것도 빼지 않는다.
EXCLUDE_STATUS = set()
THUMB_PX = 384


def _p(run_dir, *names):
    return os.path.join(run_dir, *names)


def _load(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def _save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def resolve_run_dir(name):
    """절대경로면 그대로, 이름이면 <data_root>/sourcing-inspect/runs/<이름>."""
    if os.path.isabs(name):
        return name
    try:
        from eroomlib.config import cfg
        root = cfg("paths.data_root", required=True)
    except Exception:
        root = os.path.expanduser("~/python_work/data")
    return os.path.join(root, "sourcing-inspect", "runs", name)


# ---------- 순수 함수 (테스트 대상) ----------

def select_targets(items, stage):
    """1차 = 타오바오 매칭 결과 없음, 2차 = 매칭 결과 있음(실패 포함 → 기계가 NO_MATCH)."""
    out = []
    for it in items:
        if it.get("status") in EXCLUDE_STATUS:
            continue
        has_tb = bool(taobao_item(it))
        if stage == 1 and not has_tb and it.get("taobao_match_status") != "match_failed":
            out.append(it)
        elif stage == 2 and (has_tb or it.get("taobao_match_status") == "match_failed"):
            out.append(it)
    return out


def load_cat_paths(path=MASTER):
    try:
        d = _load(path, {}) or {}
        return {str(c.get("id")): c.get("wholeCategoryName") for c in d.get("카테고리", [])}
    except Exception as e:
        print(f"[경고] 카테고리 마스터 로드 실패: {e}")
        return {}


def to_view(item, stage, cat_paths=None):
    """워커에 넘길 축약본. 썸네일 로컬 경로는 prep 이 채운다."""
    tb = taobao_item(item) or {}
    try:
        tb_price = ((tb.get("sku") or {}).get("def") or {}).get("price")
    except Exception:
        tb_price = None
    cat = str(item.get("catId") or "")
    v = {
        "id": item.get("id"),
        "name": item.get("productName"),
        "tags": item.get("sellerTags") or [],
        "catId": cat,
        "catPath": (cat_paths or {}).get(cat),
        "brand": item.get("brand") or "",
        "price": item.get("productPrice"),
        "thumb_url": abs_url(item.get("productImageUrl")),
    }
    if stage == 2:
        v.update({"tb_title": tb.get("title"), "tb_price_cny": tb_price,
                  "tb_thumb_url": abs_url(tb.get("image")), "tb_url": abs_url(tb.get("itemUrl")),
                  "fee": item.get("overseaDeliveryFee")})
    return v


def make_batches(views, size=40):
    return [views[i:i + size] for i in range(0, len(views), size)]


def merge_judged(expected_ids, docs):
    """워커 결과 합치기. 같은 id 를 여러 번 판정하면 drop 우선(놓친 금지품이 더 비싸다)."""
    exp = set(expected_ids)
    verdicts, extra = {}, []
    for doc in docs:
        for r in doc or []:
            pid = r.get("id")
            if pid not in exp:
                extra.append(pid)
                continue
            v = r.get("verdict")
            if v not in ("pass", "drop"):
                v = "drop"  # 형식 불량은 보수적으로 탈락
            reason = r.get("reason") or "OTHER"
            if reason in ("pass", "drop"):  # 워커가 사유 칸에 판정을 적은 형식 오류
                reason = "OK" if v == "pass" else "OTHER"
            rec = {"verdict": v, "reason": reason,
                   "note": r.get("note") or "", "by": "ai"}
            if pid not in verdicts or (v == "drop" and verdicts[pid]["verdict"] == "pass"):
                verdicts[pid] = rec
    missing = [i for i in expected_ids if i not in verdicts]
    return verdicts, missing, extra


def pending_batches(run_dir):
    idx = _load(_p(run_dir, "batches_index.json"), []) or []
    return [b for b in idx if not os.path.exists(_p(run_dir, "judged", f"judged_{b['n']:03d}.json"))]


# ---------- 명령 ----------

def cmd_fetch(a):
    if a.from_file:
        raw = _load(a.from_file)
        items = raw.get("data") if isinstance(raw, dict) else raw
    else:
        from sourcing_api import fetch_products, load_token
        items = fetch_products(a.campaign, load_token())
    _save(_p(a.run_dir, "snapshot.json"), items)
    meta = _load(_p(a.run_dir, "run_meta.json"), {}) or {}
    meta.update({"campaign": a.campaign, "count": len(items)})
    _save(_p(a.run_dir, "run_meta.json"), meta)
    st = collections.Counter(i.get("status") for i in items)
    print(f"[fetch] {len(items)}건 → {a.run_dir}/snapshot.json  상태 {dict(st)}")


def abs_url(url):
    """타오바오 이미지는 '//img.alicdn.com/...' 프로토콜 생략형으로 온다 → https 붙인다."""
    url = (url or "").strip()
    return "https:" + url if url.startswith("//") else url


def _download_thumb(url, out):
    """긴 변 THUMB_PX 로 줄여 JPEG 저장. 실패하면 None."""
    if not url:
        return None
    if os.path.exists(out):
        return out
    try:
        import requests
        from PIL import Image
        from sourcing_api import UA
        r = requests.get(abs_url(url), headers={"User-Agent": UA}, timeout=20)
        r.raise_for_status()
        im = Image.open(io.BytesIO(r.content)).convert("RGB")
        im.thumbnail((THUMB_PX, THUMB_PX))
        im.save(out, "JPEG", quality=82)
        return out
    except Exception:
        return None


def cmd_prep(a):
    items = _load(_p(a.run_dir, "snapshot.json"))
    if items is None:
        sys.exit("snapshot.json 없음 — fetch 먼저")
    targets = select_targets(items, a.stage)
    if a.sample == "random":
        random.Random(a.seed).shuffle(targets)
    if a.limit:
        targets = targets[:a.limit]
    cats, kws = load_banned_cats(), load_keywords()
    cat_paths = load_cat_paths()
    machine, views = {}, []
    for it in targets:
        r = machine_judge(it, a.stage, cats, kws)
        if r:
            machine[it["id"]] = {**r, "by": "machine"}
        else:
            views.append(to_view(it, a.stage, cat_paths))
    # 썸네일 병렬 다운로드 (1차=네이버, 2차=타오바오+네이버)
    tdir = _p(a.run_dir, "thumbs")
    os.makedirs(tdir, exist_ok=True)
    jobs = []
    for v in views:
        safe = str(v["id"]).replace("/", "_")
        jobs.append((v, "thumb", v.get("thumb_url"), os.path.join(tdir, f"{safe}_n.jpg")))
        if a.stage == 2:
            jobs.append((v, "tb_thumb", v.get("tb_thumb_url"), os.path.join(tdir, f"{safe}_t.jpg")))
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(_download_thumb, url, out): (v, key) for v, key, url, out in jobs}
        for f in concurrent.futures.as_completed(futs):
            v, key = futs[f]
            v[key] = f.result()
    _save(_p(a.run_dir, "targets.json"), [t["id"] for t in targets])
    _save(_p(a.run_dir, "machine.json"), machine)
    _save(_p(a.run_dir, "views.json"), views)
    meta = _load(_p(a.run_dir, "run_meta.json"), {}) or {}
    meta.update({"stage": a.stage, "targets": len(targets)})
    _save(_p(a.run_dir, "run_meta.json"), meta)
    mc = collections.Counter(r["reason"] for r in machine.values())
    miss = sum(1 for v in views if not v.get("thumb")) + (
        sum(1 for v in views if not v.get("tb_thumb")) if a.stage == 2 else 0)
    print(f"[prep] {a.stage}차 대상 {len(targets)}건 → 기계탈락 {len(machine)} {dict(mc)} / AI 판정 {len(views)}건"
          f" / 썸네일 실패 {miss}")


def cmd_batch(a):
    views = _load(_p(a.run_dir, "views.json"), [])
    stage = (_load(_p(a.run_dir, "run_meta.json"), {}) or {}).get("stage", 1)
    index = []
    for n, chunk in enumerate(make_batches(views, a.size), 1):
        path = os.path.abspath(_p(a.run_dir, "batches", f"batch_{n:03d}.json"))
        _save(path, {"batch": n, "stage": stage, "products": chunk})
        imgs = sum(1 for v in chunk for k in ("thumb", "tb_thumb") if v.get(k))
        # 1차는 애매할 때만 썸네일을 본다 → 실제 열람은 일부. 예산 계산은 보수적으로 1/4 로 잡는다
        if stage == 1:
            imgs = max(1, imgs // 4)
        index.append({"n": n, "path": path, "count": len(chunk), "imgs": imgs})
    os.makedirs(_p(a.run_dir, "judged"), exist_ok=True)
    _save(_p(a.run_dir, "batches_index.json"), index)
    print(f"[batch] {len(views)}건 → 배치 {len(index)}개 (건당 {a.size})")


def cmd_pending(a):
    stage = (_load(_p(a.run_dir, "run_meta.json"), {}) or {}).get("stage", 1)
    print(json.dumps({"runDir": os.path.abspath(a.run_dir), "promptPath": WORKER_PROMPT,
                      "stage": stage, "batches": pending_batches(a.run_dir)}, ensure_ascii=False))


def cmd_merge(a):
    views = _load(_p(a.run_dir, "views.json"), [])
    docs = []
    jdir = _p(a.run_dir, "judged")
    revive = []  # judged_95NN = 탈락 재심(recheck --from drop) — 결과가 원판정을 양방향으로 덮는다
    for fn in sorted(os.listdir(jdir)) if os.path.isdir(jdir) else []:
        if fn.endswith(".json"):
            d = _load(os.path.join(jdir, fn), [])
            d = d.get("results", d) if isinstance(d, dict) else d
            num = fn[len("judged_"):-len(".json")]
            (revive if num.isdigit() and int(num) >= REVIVE_BASE else docs).append(d)
    verdicts, missing, extra = merge_judged([v["id"] for v in views], docs)
    # 재심끼리는 나중 배치가 이긴다(기준이 계속 바뀌므로 최신 판정이 정본)
    for d in revive:
        rv, _, _ = merge_judged(list(verdicts), [d])
        verdicts.update(rv)
    machine = _load(_p(a.run_dir, "machine.json"), {}) or {}
    final = {**verdicts, **machine}
    # 사용자가 직접 정해 준 판정(rules/feedback_*.json)이 최우선 — AI·기계 판정을 덮는다
    user = 0
    for fn in sorted(os.listdir(os.path.join(SKILL_DIR, "rules"))):
        if not (fn.startswith("feedback_") and fn.endswith(".json")):
            continue
        fb = _load(os.path.join(SKILL_DIR, "rules", fn), {}) or {}
        for want in ("pass", "drop"):
            for label, ids in (fb.get(want) or {}).items():
                for pid in ids:
                    if pid in final:
                        final[pid] = {"verdict": want, "reason": "USER" if want == "drop" else "OK",
                                      "note": f"사용자 지정: {label}", "by": "user"}
                        user += 1
    _save(_p(a.run_dir, "verdicts.json"), final)
    c = collections.Counter(r["verdict"] for r in final.values())
    rc = collections.Counter(r["reason"] for r in final.values() if r["verdict"] == "drop")
    print(f"[merge] 최종 {len(final)}건 통과 {c['pass']} / 탈락 {c['drop']}  누락 {len(missing)} 환각 {len(extra)}  사용자지정 {user}")
    print(f"  탈락 사유: {dict(rc.most_common())}")
    if missing:
        print(f"  누락 id(앞 10): {missing[:10]}")


# 결과표용 한국어 사유 이름 (사용자가 한눈에 읽도록)
REASON_KO = {
    "IP": "브랜드·캐릭터", "KEYWORD_IP": "브랜드(상품명 키워드)", "SMALL": "작은 부품·소품",
    "CATEGORY": "금지 분야", "NOSELL": "안 파는 품목", "SHIP": "대형·파손 위험", "FASHION": "패션",
    "LAW": "법규 금지품", "KEYWORD_LAW": "법규 금지품(키워드)", "DANGER": "위험물",
    "KEYWORD_DANGER": "위험물(키워드)", "TARGET": "아이·유아·성인 대상", "WATT": "3000W 이상",
    "NO_MATCH": "매칭 없음", "BANNED_CAT": "금지 카테고리 번호", "USER": "사용자 지정 삭제",
    "OTHER": "기타", "OK": "통과",
}


def _short(text, n=28):
    t = " ".join(str(text or "").split())
    return t if len(t) <= n else t[:n] + "…"


def _img(src, label):
    if not src:
        return f'<div class="col"><div class="label">{html.escape(label)} (없음)</div></div>'
    src = abs_url(src)
    return (f'<div class="col"><img loading="lazy" src="{html.escape(src)}">'
            f'<div class="label">{html.escape(label)}</div></div>')


def cmd_remachine(a):
    items = {i["id"]: i for i in (_load(_p(a.run_dir, "snapshot.json"), []) or [])}
    stage = (_load(_p(a.run_dir, "run_meta.json"), {}) or {}).get("stage", 1)
    targets = _load(_p(a.run_dir, "targets.json"), []) or []
    cats, kws = load_banned_cats(), load_keywords()
    old = _load(_p(a.run_dir, "machine.json"), {}) or {}
    machine = {}
    for pid in targets:
        it = items.get(pid)
        r = machine_judge(it, stage, cats, kws) if it else None
        if r:
            machine[pid] = {**r, "by": "machine"}
    _save(_p(a.run_dir, "machine.json"), machine)
    mc = collections.Counter(r["reason"] for r in machine.values())
    print(f"[remachine] 기계탈락 {len(old)} → {len(machine)} {dict(mc)}")


RECHECK_BASE = 9000  # 통과 재검 배치 번호대(9001~) — 원 배치(001~)와 겹치지 않게, drop 우선 병합
REVIVE_BASE = 9500   # 탈락 재심 배치 번호대(9501~) — 원판정을 덮는다


def cmd_recheck(a):
    """현재 AI 통과 중 패턴에 걸리는 상품만 재판정 배치로. merge 는 drop 우선이라 통과→탈락만 반영된다."""
    import re
    pat = re.compile(a.pattern, re.I)
    final = _load(_p(a.run_dir, "verdicts.json"), {}) or {}
    stage = (_load(_p(a.run_dir, "run_meta.json"), {}) or {}).get("stage", 1)
    views = _load(_p(a.run_dir, "views.json"), []) or []
    want = a.source
    picked = [v for v in views if (final.get(v["id"]) or {}).get("verdict") == want
              and (final.get(v["id"]) or {}).get("by") == "ai"
              and (not a.reason or (final.get(v["id"]) or {}).get("reason") in a.reason.split(","))
              and pat.search(" ".join([v.get("name") or "", v.get("tb_title") or "", v.get("catPath") or "",
                                       (final.get(v["id"]) or {}).get("note") or "" if a.note else ""]))]
    base = REVIVE_BASE if want == "drop" else RECHECK_BASE
    used = [int(f[6:10]) for f in os.listdir(_p(a.run_dir, "batches"))
            if f.startswith("batch_9") and f[6:10].isdigit() and base <= int(f[6:10]) < base + 500]
    start = max(used + [base]) + 1
    out = []
    for k, chunk in enumerate(make_batches(picked, a.size)):
        n = start + k
        path = os.path.abspath(_p(a.run_dir, "batches", f"batch_{n:03d}.json"))
        _save(path, {"batch": n, "stage": stage, "products": chunk})
        imgs = sum(1 for v in chunk for key in ("thumb", "tb_thumb") if v.get(key))
        out.append({"n": n, "path": path, "count": len(chunk), "imgs": max(1, imgs // 4) if stage == 1 else imgs})
    print(json.dumps({"runDir": os.path.abspath(a.run_dir), "promptPath": WORKER_PROMPT, "stage": stage,
                      "batches": out}, ensure_ascii=False))
    print(f"[recheck] {want} 중 패턴 일치 {len(picked)}건 → 배치 {len(out)}개", file=sys.stderr)


def cmd_report(a):
    final = _load(_p(a.run_dir, "verdicts.json"), {}) or {}
    snap = {i["id"]: i for i in (_load(_p(a.run_dir, "snapshot.json"), []) or [])}
    views = {v["id"]: v for v in (_load(_p(a.run_dir, "views.json"), []) or [])}
    meta = _load(_p(a.run_dir, "run_meta.json"), {}) or {}
    stage = meta.get("stage", 1)
    cat_paths = load_cat_paths()
    groups = {"drop": [], "pass": []}
    for pid, r in final.items():
        groups.setdefault(r["verdict"], []).append((pid, r))
    rc = collections.Counter(r["reason"] for _, r in groups["drop"])

    def card(pid, r):
        it = snap.get(pid, {})
        tb = taobao_item(it) or {}
        cat = str(it.get("catId") or "")
        imgs = [_img(it.get("productImageUrl"), "네이버 원본")]
        if stage == 2:
            imgs.append(_img(tb.get("image"), "타오바오 매칭"))
        tb_line = (f'<div class="meta">타오바오: {html.escape(tb.get("title") or "")} · ¥{html.escape(str(((tb.get("sku") or {}).get("def") or {}).get("price") or ""))}'
                   f' · 해외배송비 {it.get("overseaDeliveryFee")}</div>') if stage == 2 else ""
        return (f'<div class="card" data-reason="{html.escape(r["reason"])}"><h2>{html.escape(it.get("productName") or "")}</h2>'
                f'<div class="pid">{html.escape(pid)} · {html.escape(cat)} {html.escape(cat_paths.get(cat) or "")} · {r.get("by")}</div>'
                f'<div class="reason"><b>{html.escape(REASON_KO.get(r["reason"], r["reason"]))}</b> · '
                f'<span title="{html.escape(r.get("note") or "")}">{html.escape(_short(r.get("note")))}</span></div>'
                f'<div class="row">{"".join(imgs)}</div>{tb_line}'
                f'<div class="meta"><a href="{html.escape(it.get("productUrl") or "")}" target="_blank">네이버</a>'
                f'{" · <a href=" + chr(34) + html.escape(abs_url(tb.get("itemUrl"))) + chr(34) + " target=_blank>타오바오</a>" if tb else ""}</div></div>')

    css = (":root{color-scheme:light dark}body{font-family:-apple-system,sans-serif;background:#111;color:#eee;margin:0;padding:20px}"
           ".card{background:#1c1c1c;border:1px solid #333;border-radius:8px;padding:12px;margin:0 0 12px}"
           ".card h2{font-size:14px;margin:0 0 4px}.pid,.meta{color:#888;font-size:12px}.reason{color:#f0a020;font-size:13px;margin:6px 0}"
           ".row{display:flex;gap:12px;flex-wrap:wrap}.col{text-align:center}.col img{width:180px;height:180px;object-fit:contain;background:#000;border-radius:4px}"
           ".label{font-size:11px;color:#aaa}a{color:#6af}h1{font-size:18px}details{margin:12px 0}summary{cursor:pointer;font-size:16px}"
           ".grp{grid-column:1/-1;margin:16px 0 0;font-size:16px;color:#f0a020;border-bottom:1px solid #444}.reason b{color:#ff7b5a}"
           ".grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:12px}")
    def drop_cards():
        # 사유가 많은 순으로 묶고, 묶음마다 제목을 단다
        order = {k: i for i, (k, _) in enumerate(rc.most_common())}
        out, prev = [], None
        for p, r in sorted(groups["drop"], key=lambda x: order.get(x[1]["reason"], 99)):
            if r["reason"] != prev:
                prev = r["reason"]
                out.append(f'<h3 class="grp">{html.escape(REASON_KO.get(prev, prev))} — {rc[prev]}건</h3>')
            out.append(card(p, r))
        return "".join(out)

    only = getattr(a, "only", None)
    if only:
        groups = {k: (v if k == only else []) for k, v in groups.items()}
    summary = "".join(f"<li>{html.escape(REASON_KO.get(k, k))}: {v}</li>" for k, v in rc.most_common())
    body = (f"<h1>소싱 검수 {stage}차 결과 — {html.escape(str(meta.get('campaign')))} · 대상 {len(final)}건 · "
            f"통과 {len(groups['pass'])} / 탈락 {len(groups['drop'])}</h1><ul>{summary}</ul>"
            f"<details open><summary>통과 {len(groups['pass'])}건 — 금지품이 섞였는지 확인</summary><div class='grid'>"
            + "".join(card(p, r) for p, r in groups["pass"]) +
            f"</div></details><details{' open' if only == 'drop' else ''}><summary>탈락 {len(groups['drop'])}건 — 억울한 탈락 확인</summary><div class='grid'>"
            + drop_cards() +
            "</div></details>")
    out = _p(a.run_dir, f"review_{only}.html" if only else "review.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"<!doctype html><html lang=ko><head><meta charset=utf-8><title>소싱 검수 결과</title><style>{css}</style></head><body>{body}</body></html>")
    print(f"[report] {out}")


def main():
    ap = argparse.ArgumentParser(description="불사자 소싱기 상품검수 (판정 단계)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch"); f.add_argument("--campaign", required=True); f.add_argument("--from-file")
    p = sub.add_parser("prep"); p.add_argument("--stage", type=int, choices=[1, 2], required=True)
    p.add_argument("--limit", type=int); p.add_argument("--sample", choices=["random", "head"], default="head")
    p.add_argument("--seed", type=int, default=20261018)
    b = sub.add_parser("batch"); b.add_argument("--size", type=int, default=40)
    sub.add_parser("pending"); sub.add_parser("merge"); sub.add_parser("remachine")
    rp = sub.add_parser("report"); rp.add_argument("--only", choices=["drop", "pass"])
    rc = sub.add_parser("recheck"); rc.add_argument("--pattern", required=True); rc.add_argument("--size", type=int, default=40)
    rc.add_argument("--source", choices=["pass", "drop"], default="pass", help="drop = 탈락 재심(결과가 원판정을 덮음)")
    rc.add_argument("--note", action="store_true", help="AI 판정 메모도 패턴 검색 대상에 넣는다")
    rc.add_argument("--reason", help="사유코드 필터(쉼표 구분, 예: IP,CATEGORY)")
    for s in sub.choices.values():
        s.add_argument("--run-dir", required=True)
    a = ap.parse_args()
    a.run_dir = resolve_run_dir(a.run_dir)
    try:
        {"fetch": cmd_fetch, "prep": cmd_prep, "batch": cmd_batch, "pending": cmd_pending,
         "merge": cmd_merge, "report": cmd_report, "remachine": cmd_remachine, "recheck": cmd_recheck}[a.cmd](a)
    except RuntimeError as e:
        sys.exit(f"[오류] {e}")


if __name__ == "__main__":
    main()
