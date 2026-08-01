#!/usr/bin/env python3
"""불사자 카테고리 교정 대량 파이프라인 오케스트레이터.

파이프라인 중간에 Claude(정체판별+키워드 추출)가 끼므로 완전 원샷이 불가 → 2단계로 나눈다.

  [prep]   collect(G빈행) → workdata(카테고리+정체증거 4종) → 썸네일 전건 다운로드
           → products.json + names.json(정체판별용) 출력
      ↓  (Claude/서브에이전트가 증거 4종 → keywords.json:
      ↓   [{productId, name=대표검색어, 실물판정, 근거}] / 불명이면 상태='보류(정체불명)')
  [finish] sellha(보류 제외) → merge(products+keywords+sellha) → apply(실저장+시트기록)

재개: 시트 G열이 체크포인트. prep 는 항상 'G 빈 행'만 가져오므로, finish 로 저장돼
      G가 채워지면 다음 prep 는 자동으로 그다음 청크를 집는다. --limit 로 청크 크기 조절.

사용:
  # 1) 준비(다음 청크 50건)
  python run_all.py prep --limit 50 --run-dir runs/0713_c1
  # 2) (여기서 names.json → keywords.json 을 Claude 가 만든다)
  # 3) 마무리(실저장)
  python run_all.py finish --run-dir runs/0713_c1 --keywords runs/0713_c1/keywords.json
  #    미리보기만: --dry-run
"""
import argparse
import json
import os
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

# 경로·시트 id 는 workspace.toml 1벌에서 온다(없으면 DEFAULTS = 현행 값).
# `.claude` 앵커를 찾아 lib 를 sys.path 에 올린 뒤 eroomlib 를 든다.
_d = SCRIPT_DIR
while _d and _d != os.path.dirname(_d):
    _lib = os.path.join(_d, "lib")
    if os.path.isdir(os.path.join(_lib, "eroomlib")):
        if _lib not in sys.path:
            sys.path.insert(0, _lib)
        break
    _d = os.path.dirname(_d)
from eroomlib.config import cfg as _cfg  # noqa: E402

SHEET = _cfg("sheets.keyword_default")
TAB = "시트1"


# 셀하 조회는 sellha-category 스킬로 분리됨(Step4). 절대경로로 호출한다.
SELLHA_SCRIPT = os.path.normpath(os.path.join(
    SCRIPT_DIR, "..", "..", "sellha-category", "scripts", "sellha.py"))

# 셀하 확장이 설치된 크롬 프로필. 없으면 카테고리가 전건 빈값으로 온다.
SELLHA_PROFILE = (os.environ.get("SELLHA_PROFILE")
                  or _cfg("paths.sellha_profile")
                  or "D:/python_work/data/sellha/profile")


def sh(script, *args):
    # script 가 절대경로(다른 스킬)면 그대로, 아니면 이 스킬 SCRIPT_DIR 에서 찾는다.
    path = script if os.path.isabs(script) else os.path.join(SCRIPT_DIR, script)
    label = os.path.basename(script)
    cmd = [PY, path, *[str(a) for a in args]]
    print(f"\n$ {label} {' '.join(str(a) for a in args)}\n{'-'*56}")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run(cmd, env=env)
    if proc.returncode != 0:
        raise RuntimeError(f"{label} 실패 (exit {proc.returncode})")


def _p(run_dir, name):
    return os.path.join(run_dir, name)


def _fetch_thumbs(run_dir, prods, refresh=False):
    """전건 대표 썸네일 다운로드 → {productId: 로컬경로}.

    fetch_thumbs.py 는 입력 순서대로 한 줄씩(성공=절대경로 / 실패='FAIL\\t..') 출력한다.
    """
    thumbs_json = _p(run_dir, "thumbs.json")
    thumbs_dir = _p(run_dir, "thumbs")
    items = [{"productId": p["productId"], "url": (p.get("썸네일") or [""])[0]}
             for p in prods if (p.get("썸네일") or [""])[0]]
    if not items:
        print("[3/4] 썸네일 URL 없음 — 건너뜀")
        return {}
    with open(thumbs_json, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    os.makedirs(thumbs_dir, exist_ok=True)
    print(f"[3/4] 썸네일 {len(items)}장 다운로드 중...")
    cmd = [PY, os.path.join(SCRIPT_DIR, "fetch_thumbs.py"),
           "--input", thumbs_json, "--out-dir", thumbs_dir] + (["--refresh"] if refresh else [])
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    out = {}
    for i, ln in enumerate([l for l in (proc.stdout or "").splitlines() if l.strip()]):
        if i < len(items) and not ln.startswith("FAIL"):
            out[items[i]["productId"]] = os.path.abspath(ln.strip())
    print(f"  로컬 확보: {len(out)}/{len(items)}장")
    return out


def cmd_prep(args):
    os.makedirs(args.run_dir, exist_ok=True)
    targets = _p(args.run_dir, "targets.json")
    products = _p(args.run_dir, "products.json")
    names = _p(args.run_dir, "names.json")

    # 1) 대상수집 (G 빈 행만, --limit 청크)
    collect_args = ["--sheet", args.sheet, "--tab", args.tab, "-o", targets]
    if args.limit and not args.ids:
        collect_args += ["--limit", args.limit]
    if args.ids and args.include_done:
        collect_args += ["--all"]  # 상태가 이미 찬 행도 대상에 넣는다(재작업)
    sh("collect_targets.py", *collect_args)

    # 1b) --ids: 특정 상품만 남긴다. 세로 러너(onestep)가 상품 1건을 지정하는 경로이자,
    #     보류 건 애드혹 재작업용. 수집 뒤에 거르는 이유 = 시트 행번호·원장 상태를
    #     collect_targets 가 붙여 주므로 그 산출물을 그대로 쓰는 게 안전하다.
    if args.ids:
        want = [i.strip() for i in args.ids if i.strip()]

        def _filter():
            with open(targets, encoding="utf-8") as f:
                allt = json.load(f)
            kept = [t for t in allt if t.get("productId") in want]
            miss = [i for i in want
                    if not any(t.get("productId") == i for t in kept)]
            return kept, miss

        kept, missing = _filter()

        # 시트1에 **행이 없는** 상품은 대상이 될 수 없다(collect_targets 가 시트를 읽으므로).
        # 현황판에는 있는데 여기엔 없는 상품이 그룹당 수백 건이다(용쌤1-1: 833/833).
        # → 현황판의 상품명으로 A·B열만 채워 행을 만들고 다시 수집한다. 그래야 대상 선정이
        #   "현황판 쿼리 1줄"이라는 계약과 실제가 맞는다.
        if missing and not args.no_seed:
            from eroomlib import matrix
            from eroomlib.gsheets import append_rows
            m = matrix.read(args.sheet)
            seed = [[pid, (m.get(pid) or {}).get("상품", "")]
                    for pid in missing if pid in m]
            if seed:
                append_rows(args.sheet, args.tab, seed)
                print(f"[1b] 시트1에 행 신설 {len(seed)}건 (현황판에는 있으나 원장에 없던 상품)")
                sh("collect_targets.py", *collect_args)
                kept, missing = _filter()

        with open(targets, "w", encoding="utf-8") as f:
            json.dump(kept, f, ensure_ascii=False, indent=2)
        print(f"[1b] --ids {len(want)}건 지정 → {len(kept)}건 매칭")
        if missing:
            print(f"  [경고] 대상에 못 넣음 {len(missing)}건: {missing[:5]}")
            print("   상태열이 이미 차 있거나(--include-done) 현황판에 없는 상품이다.")
        if not kept:
            print("[중단] 대상 0건.")
            sys.exit(2)   # 조용한 성공 금지 — 러너가 다음 단계로 넘어가면 안 된다

    # 2) workdata (현재 카테고리 + 정체증거 4종) — 대화 밖 직접 MCP.
    #    공용 스냅샷을 먼저 본다(상품명 스킬이 이미 받아둔 상품이면 MCP 0회).
    wd_args = ["workdata", "-i", targets, "-o", products, "--sleep", args.sleep]
    if args.refresh:
        wd_args.append("--refresh")
    sh("bulsaja_mcp.py", *wd_args)

    with open(products, encoding="utf-8") as f:
        prods = json.load(f)

    # 3) 썸네일 전건 다운로드 (2026-07-24: 폴백이 아니라 기본 경로)
    thumb_map = ({} if args.skip_thumbs
                 else _fetch_thumbs(args.run_dir, prods, refresh=args.refresh))

    # 4) 정체판별용 names.json — 증거 4종을 한 장에 모아 넘긴다.
    #    한국어 상품명은 '정답'이 아니라 '용의자'다. 원문명·옵션명은 가공 전 원본이라
    #    상품명·썸네일이 함께 틀어졌을 때 이것만이 실물을 가리킨다.
    names_list = [{
        "productId": p["productId"],
        "row": p.get("row"),
        "상품명": p.get("상품명", ""),
        "원문명": p.get("원문명", ""),
        "옵션명": p.get("옵션명", []),
        "썸네일경로": thumb_map.get(p["productId"], ""),
    } for p in prods]
    with open(names, "w", encoding="utf-8") as f:
        json.dump(names_list, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 56)
    print(f"[prep 완료] {len(names_list)}건 → {products}")
    print(f"다음: {names} 의 증거 4종(상품명·원문명·옵션명·썸네일)으로 keywords.json 생성")
    print("  [{productId, name=대표검색어, 실물판정, 근거}] "
          "/ 정체 불명이면 {productId, 상태:'보류(정체불명)', 실물판정, 근거}")
    print(f"그 후: python run_all.py finish --run-dir {args.run_dir} "
          f"--keywords {os.path.join(args.run_dir, 'keywords.json')}")


def cmd_finish(args):
    products = _p(args.run_dir, "products.json")
    sellha = _p(args.run_dir, "sellha.json")
    merged = _p(args.run_dir, "merged.json")
    decisions = _p(args.run_dir, "decisions.json")
    keywords = args.keywords or _p(args.run_dir, "keywords.json")

    # 4) 셀하 조회 (배치, 증분저장+재개). --force 면 처음부터 재조회
    #    '보류(정체불명)' 건은 정체가 안 잡힌 것이라 셀하를 아예 태우지 않는다
    #    (셀하 ~15초/건이 유일한 직렬 병목 — 어차피 2바퀴에서 재조회하므로 1회만 태운다).
    with open(keywords, encoding="utf-8") as f:
        kw_list = json.load(f)
    kw_map = {k.get("productId"): k for k in kw_list}
    held = {pid for pid, k in kw_map.items()
            if str(k.get("상태", "")).startswith("보류") or not k.get("name")}
    if held:
        askable = _p(args.run_dir, "keywords_askable.json")
        with open(askable, "w", encoding="utf-8") as f:
            json.dump([k for k in kw_list if k.get("productId") not in held],
                      f, ensure_ascii=False, indent=2)
        keywords_for_sellha = askable
        print(f"[보류] 정체불명 {len(held)}건은 셀하 조회 제외 → 2바퀴 큐")
    else:
        keywords_for_sellha = keywords

    if args.force and os.path.exists(sellha):
        os.remove(sellha)
    # ★ 셀하는 이제 **확장 프로필**이 있어야 카테고리를 준다(2026-07-31, 네이버 API 종료 여파).
    # 헤드리스에서는 확장이 안 돌아 전건 파싱실패가 된다 → 창 모드 고정.
    # 프로필 준비 → sellha-category/SKILL.md §확장 프로필 준비
    sh(SELLHA_SCRIPT, "--input", keywords_for_sellha, "--output", sellha,
       "--profile", SELLHA_PROFILE, "--resume")

    # 5) 병합 (products + keywords + sellha, productId 기준)
    with open(products, encoding="utf-8") as f:
        prods = {p["productId"]: p for p in json.load(f)}
    with open(sellha, encoding="utf-8") as f:
        sl = {r.get("productId"): r for r in json.load(f)}
    merged_list = []
    for pid, w in prods.items():
        s = sl.get(pid, {})
        k = kw_map.get(pid, {})
        thumbs = w.get("썸네일") or []
        merged_list.append({
            "productId": pid, "상품명": w.get("상품명", ""), "row": w.get("row"),
            "기존카테고리": w.get("기존카테고리", ""), "검색어": s.get("검색어", ""),
            "sellha경로": s.get("카테고리경로", ""), "최종차수": s.get("최종차수", ""),
            "확신도": s.get("확신도", ""),
            "sellha상태": "보류(정체불명)" if pid in held else s.get("상태", ""),
            # 시트 J·K (상품명 스킬이 재활용)
            "실물판정": k.get("실물판정", ""),
            "썸네일": thumbs[0] if thumbs else "",
        })
    with open(merged, "w", encoding="utf-8") as f:
        json.dump(merged_list, f, ensure_ascii=False, indent=2)
    print(f"\n병합 {len(merged_list)}건 → {merged}")

    # 6) 적용 (미리보기→비교→커밋 + 시트 건건 기록)
    apply_args = ["apply", "-i", merged, "-o", decisions,
                  "--threshold", args.threshold, "--sleep", args.sleep]
    if args.dry_run:
        apply_args.append("--dry-run")
    if args.no_sheet:
        apply_args.append("--no-sheet")
    else:
        apply_args += ["--sheet", args.sheet]
    sh("bulsaja_mcp.py", *apply_args)
    print("\n" + "=" * 56)
    print(f"[finish 완료] 결과 {decisions}"
          + ("  (DRY-RUN)" if args.dry_run else ""))


# ── 팬아웃 3종(batch / merge / steer)의 계산부 ───────────────────────────────
# 순수 함수로 떼어 둔다 — MCP·시트·셀하 없이 test_run_all.py 가 검증한다.

def make_batches(names_list, size, rules):
    """names.json → 자기완결형 배치. 워커는 배치 파일 경로 하나로 완주할 수 있어야 한다."""
    size = max(1, int(size or 1))
    out = []
    for i in range(0, len(names_list), size):
        chunk = names_list[i:i + size]
        out.append({
            "batch": len(out) + 1,
            "규칙문서": rules,
            "이미지수": sum(1 for p in chunk if p.get("썸네일경로")),
            "products": chunk,
        })
    return out


def merge_named(named_docs, expected):
    """워커 산출물(named_*.json) → keywords.json + 감사 리포트.

    디스크가 정본이므로 같은 상품이 두 번 와도(재팬아웃) 마지막이 이긴다.
    모르는 상품id 는 버린다 — 워커 환각이 원장에 들어가면 되돌릴 경로가 없다.
    name 도 상태도 없는 결과는 **보류로 강등**한다. 그대로 두면 셀하를 태워
    빈 검색어로 조회하고 '조회실패'가 되어 원인이 지워진다.
    """
    want = list(dict.fromkeys(expected))
    allow = set(want)
    by_pid, order, dups, unknown = {}, [], 0, []
    for doc in named_docs:
        for r in (doc.get("results") or []):
            pid = r.get("productId")
            if not pid:
                continue
            if pid not in allow:
                unknown.append(pid)
                continue
            if pid in by_pid:
                dups += 1
            else:
                order.append(pid)
            rec = dict(r)
            if not rec.get("name") and not str(rec.get("상태", "")).startswith("보류"):
                rec["상태"] = "보류(정체불명)"
                rec.setdefault("근거", "")
                rec["근거"] = (rec["근거"] + " [자동강등: 검색어 없음]").strip()
            by_pid[pid] = rec
    kw = [by_pid[p] for p in order]
    held = [p for p in order if str(by_pid[p].get("상태", "")).startswith("보류")]
    return kw, {
        "missing": [p for p in want if p not in by_pid],
        "unknown": unknown,
        "dups": dups,
        "held": held,
        "named": len(kw) - len(held),
    }


def steer_items(decisions, merged, threshold=70):
    """저장 4단계 폴백 1단계(유도)의 대상 산출.

    자동 유도는 **확신도가 임계 이상인 것만** 한다. 미달은 이룸님 수동 큐로 남긴다
    (확신도는 '키워드↔카테고리' 신뢰도라, 낮은 걸 유도 저장하면 확신에 찬 오답이 굳는다).
    """
    mg = {m.get("productId"): m for m in merged}
    items, skipped = [], {"확신도미달": [], "경로없음": []}
    for d in decisions:
        if d.get("상태") not in ("매칭불가", "부분일치확인요"):
            continue
        pid = d.get("productId")
        m = mg.get(pid) or {}
        target = (m.get("sellha경로") or "").strip()
        if not target:
            skipped["경로없음"].append(pid)
            continue
        conf = _conf(d.get("확신도"))
        if conf is None or conf < float(threshold):
            skipped["확신도미달"].append(pid)
            continue
        items.append({
            "productId": pid, "row": d.get("row"), "target": target,
            "keyword": m.get("최종차수", ""), "mode": "exact",
            "상품명": d.get("상품명", ""), "기존카테고리": d.get("기존카테고리", ""),
            "확신도": d.get("확신도", ""),
        })
    return items, skipped


def _conf(v):
    try:
        return float(str(v).replace("%", "").strip())
    except (TypeError, ValueError):
        return None


RULES_DOC = os.path.normpath(os.path.join(
    SCRIPT_DIR, "..", "references", "대표검색어-도출.md"))
WORKER_PROMPT = os.path.normpath(os.path.join(
    SCRIPT_DIR, "..", "references", "판정-워커-프롬프트.md"))


def cmd_batch(args):
    """names.json → batches/batch_NNN.json + batches_index.json.

    Workflow 스크립트는 파일시스템이 없다 — pending·이미지수를 여기서 미리 계산해
    index 에 박아 두면 호출자가 그대로 args 로 넘길 수 있다.
    """
    names = _p(args.run_dir, "names.json")
    with open(names, encoding="utf-8") as f:
        names_list = json.load(f)
    bdir = _p(args.run_dir, "batches")
    os.makedirs(bdir, exist_ok=True)
    os.makedirs(_p(args.run_dir, "named"), exist_ok=True)
    batches = make_batches(names_list, args.size, RULES_DOC)
    index = []
    for b in batches:
        path = os.path.abspath(os.path.join(bdir, f"batch_{b['batch']:03d}.json"))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(b, f, ensure_ascii=False, indent=2)
        index.append({"n": b["batch"], "path": path, "imgs": b["이미지수"],
                      "count": len(b["products"])})
    idx_path = _p(args.run_dir, "batches_index.json")
    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print(f"[batch] {len(names_list)}건 → 배치 {len(index)}개 (건당 {args.size}) → {bdir}")
    print(f"  index: {idx_path}")
    print(f"  워커 지시서: {WORKER_PROMPT}")


def _pending_batches(run_dir):
    """named/named_NNN.json 이 없는 배치 = 아직 안 된 것. 디스크가 정본이다."""
    idx_path = _p(run_dir, "batches_index.json")
    if not os.path.exists(idx_path):
        return []
    with open(idx_path, encoding="utf-8") as f:
        index = json.load(f)
    ndir = _p(run_dir, "named")
    return [b for b in index
            if not os.path.exists(os.path.join(ndir, f"named_{b['n']:03d}.json"))]


def cmd_pending(args):
    """남은 배치를 JSON 한 줄로 찍는다 — Workflow args 에 그대로 넣는다."""
    pend = _pending_batches(args.run_dir)
    print(json.dumps({"runDir": os.path.abspath(args.run_dir),
                      "promptPath": WORKER_PROMPT,
                      "batches": pend}, ensure_ascii=False))


def cmd_merge(args):
    """named/*.json → keywords.json. 누락·중복·환각을 여기서 잡는다."""
    with open(_p(args.run_dir, "names.json"), encoding="utf-8") as f:
        expected = [n["productId"] for n in json.load(f)]
    ndir = _p(args.run_dir, "named")
    docs = []
    for fn in sorted(os.listdir(ndir)) if os.path.isdir(ndir) else []:
        if not fn.startswith("named_") or not fn.endswith(".json"):
            continue
        with open(os.path.join(ndir, fn), encoding="utf-8") as f:
            docs.append(json.load(f))
    kw, rep = merge_named(docs, expected)
    out = args.keywords or _p(args.run_dir, "keywords.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(kw, f, ensure_ascii=False, indent=2)
    print(f"[merge] 워커산출 {len(docs)}파일 → {len(kw)}건 → {out}")
    print(f"  생성 {rep['named']} · 보류 {len(rep['held'])} · 중복덮어씀 {rep['dups']}")
    if rep["unknown"]:
        print(f"  [경고] 미지의 상품id {len(rep['unknown'])}건 버림: {rep['unknown'][:5]}")
    if rep["missing"]:
        print(f"  [경고] 누락 {len(rep['missing'])}건 — 해당 배치 재팬아웃 필요: "
              f"{rep['missing'][:5]}")
        if not args.allow_missing:
            print("###MERGE### 미완 — 재팬아웃 후 다시 실행 (강행은 --allow-missing)")
            sys.exit(3)
    print("###MERGE### " + json.dumps(
        {k: (len(v) if isinstance(v, list) else v) for k, v in rep.items()},
        ensure_ascii=False))


def cmd_steer(args):
    """저장 폴백 1단계(유도) 자동 실행 — 매칭불가·부분일치를 목표 경로로 밀어 넣는다."""
    dec_path = _p(args.run_dir, "decisions.json")
    mg_path = _p(args.run_dir, "merged.json")
    if not os.path.exists(dec_path):
        print("[steer] decisions.json 이 없다 — finish 를 먼저 돌린다.")
        return
    with open(dec_path, encoding="utf-8") as f:
        decisions = json.load(f)
    with open(mg_path, encoding="utf-8") as f:
        merged = json.load(f)
    items, skipped = steer_items(decisions, merged, threshold=float(args.threshold))
    print(f"[steer] 대상 {len(items)}건 · 확신도미달 {len(skipped['확신도미달'])} "
          f"· 경로없음 {len(skipped['경로없음'])}")
    if not items:
        return
    sin = _p(args.run_dir, "steer.json")
    sout = _p(args.run_dir, "steer_result.json")
    with open(sin, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    steer_args = ["--input", sin, "--output", sout, "--sleep", args.sleep]
    if args.dry_run:
        steer_args.append("--dry-run")
    if not args.no_sheet:
        steer_args += ["--sheet", args.sheet]
    sh("category_steer.py", *steer_args)
    if args.dry_run or args.no_sheet:
        return
    # 저장된 건은 카테고리가 실제로 바뀐 것 → 현황판 갱신 + 상품명 재작업 이관.
    # (bulsaja_mcp.py apply 가 자동저장분에 대해 하는 일과 같은 계약)
    try:
        with open(sout, encoding="utf-8") as f:
            res = json.load(f)
    except OSError:
        return
    saved = {r["productId"]: r for r in res if r.get("saved")}
    if not saved:
        print("  유도 저장 0건 — 현황판 변경 없음")
        return
    try:
        from eroomlib import matrix
        m = matrix.read(args.sheet)
        n = matrix.mark_many(args.sheet, "카테고리",
                             {p: "완료" for p in saved}, matrix=m)
        k = matrix.flag_many(args.sheet, "상품명",
                             {p: "카테고리 변경 — 키워드 재선정 필요" for p in saved},
                             from_task="카테고리", matrix=m)
        print(f"  현황판 카테고리 {n}칸 · 상품명 재작업 {k}건")
    except Exception as e:  # noqa: BLE001
        print(f"  [경고] 현황판 갱신 실패: {str(e)[:120]}", file=sys.stderr)


def cmd_auto(args):
    """merge → finish → steer 를 한 프로세스로. **백그라운드로 띄우는 진입점.**

    셀하가 ~15초/건이라 수백 건이면 몇 시간이 걸린다. 대화 세션이 이걸 붙잡고 있으면
    턴이 쌓여 컨텍스트가 차고, 그래서 지금까지 세션이 쪼개졌다. 한 프로세스로 묶어
    백그라운드에 두면 메인은 시작·확인 두 턴이면 된다.
    """
    class A:  # 서브커맨드 인자 재사용용 얇은 어댑터
        pass

    a = A()
    a.run_dir, a.keywords, a.allow_missing = args.run_dir, args.keywords, args.allow_missing
    cmd_merge(a)

    a.threshold, a.sleep, a.dry_run = args.threshold, args.sleep, args.dry_run
    a.no_sheet, a.sheet, a.force = args.no_sheet, args.sheet, args.force
    a.sellha_sleep = args.sellha_sleep
    a.sellha_sleep_max = args.sellha_sleep_max
    a.sellha_rest_every = args.sellha_rest_every
    cmd_finish(a)

    a.sleep = "0.3"
    cmd_steer(a)
    print("\n" + "=" * 56)
    print("[auto 완료] 남은 것 = 확신도 미달·유도 실패 건의 수동 판정")


def cmd_recheck(args):
    """2바퀴 — 1바퀴에서 '보류(정체불명)'로 남은 건만 증거를 보강해 다시 판정한다.

    싼 것부터 올라가는 사다리: 남은 썸네일(2·3장, 이미 받아둔 URL이라 공짜) →
    옵션 이미지(실물 변형이라 정체가 드러남) → 그래도 불명이면 이룸님 보고.
    """
    products = _p(args.run_dir, "products.json")
    keywords = args.keywords or _p(args.run_dir, "keywords.json")
    out_dir = _p(args.run_dir, "recheck")
    os.makedirs(out_dir, exist_ok=True)

    with open(products, encoding="utf-8") as f:
        prods = {p["productId"]: p for p in json.load(f)}
    held = set(args.ids or [])
    if not held and os.path.exists(keywords):
        with open(keywords, encoding="utf-8") as f:
            held = {k["productId"] for k in json.load(f)
                    if str(k.get("상태", "")).startswith("보류") or not k.get("name")}
    if not held:
        print("[recheck] 대상 없음 (보류 건이 없거나 --ids 미지정)")
        return

    # 이미지 목록: 남은 썸네일(2·3장) + 옵션 이미지
    items, owner = [], []
    for pid in held:
        w = prods.get(pid, {})
        urls = (w.get("썸네일") or [])[1:3] + (w.get("옵션이미지") or [])[:3]
        for u in urls:
            items.append({"productId": pid, "url": u})
            owner.append(pid)
    manifest_in = _p(args.run_dir, "recheck_urls.json")
    with open(manifest_in, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    paths = {pid: [] for pid in held}
    if items:
        print(f"[recheck] {len(held)}건 / 이미지 {len(items)}장 다운로드 중...")
        cmd = [PY, os.path.join(SCRIPT_DIR, "fetch_thumbs.py"),
               "--input", manifest_in, "--out-dir", out_dir]
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        for i, ln in enumerate([l for l in (proc.stdout or "").splitlines() if l.strip()]):
            if i < len(owner) and not ln.startswith("FAIL"):
                paths[owner[i]].append(os.path.abspath(ln.strip()))

    pack = [{
        "productId": pid,
        "row": prods.get(pid, {}).get("row"),
        "상품명": prods.get(pid, {}).get("상품명", ""),
        "원문명": prods.get(pid, {}).get("원문명", ""),
        "옵션명": prods.get(pid, {}).get("옵션명", []),
        "옵션명원문": prods.get(pid, {}).get("옵션명원문", []),
        "추가이미지": paths.get(pid, []),
        "원본링크": prods.get(pid, {}).get("원본링크", ""),
    } for pid in held]
    out = _p(args.run_dir, "recheck.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(pack, f, ensure_ascii=False, indent=2)
    print("\n" + "=" * 56)
    print(f"[recheck 준비 완료] {len(pack)}건 → {out}")
    print("다음: 추가이미지를 Read 로 열어 실물 판정 → keywords.json 갱신 → finish 재실행")


def main():
    ap = argparse.ArgumentParser(description="불사자 카테고리 교정 대량 파이프라인")
    ap.add_argument("--sheet", default=SHEET)
    ap.add_argument("--tab", default=TAB)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prep", help="collect+workdata → products.json/names.json")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--limit", type=int, default=0, help="청크 크기(0=전체 남은 것)")
    p.add_argument("--ids", nargs="+", default=None,
                   help="특정 productId 만 대상으로(세로 러너·애드혹 1건 작업). --limit 무시")
    p.add_argument("--include-done", action="store_true",
                   help="--ids 와 함께. 상태열이 이미 찬 행도 대상에 넣는다(재작업)")
    p.add_argument("--no-seed", action="store_true",
                   help="--ids 와 함께. 시트1에 행이 없어도 새로 만들지 않는다")
    p.add_argument("--sleep", default="0.3")
    p.add_argument("--skip-thumbs", action="store_true",
                   help="썸네일 다운로드 생략(텍스트 증거만으로 판정할 때)")
    p.add_argument("--refresh", action="store_true",
                   help="공용 스냅샷 무시하고 불사자에서 다시 받는다")
    p.set_defaults(func=cmd_prep)

    f = sub.add_parser("finish", help="sellha→merge→apply(실저장)")
    f.add_argument("--run-dir", required=True)
    f.add_argument("--keywords", help="keywords.json 경로(기본 run-dir/keywords.json)")
    f.add_argument("--threshold", default="70")  # 2026-07-24 이룸님 90→70 하향
    f.add_argument("--sleep", default="0.4")
    f.add_argument("--dry-run", action="store_true", help="미리보기만")
    f.add_argument("--no-sheet", action="store_true")
    f.add_argument("--force", action="store_true", help="셀하 재조회")
    f.add_argument("--sellha-sleep", default="3",
                   help="셀하 조회 간 최소 대기(초)")
    f.add_argument("--sellha-sleep-max", default="10",
                   help="셀하 조회 간 최대 대기(초). 실제는 최소~최대 난수")
    f.add_argument("--sellha-rest-every", default="25",
                   help="평균 N건마다 긴 휴식. 0=끔")
    f.set_defaults(func=cmd_finish)

    b = sub.add_parser("batch", help="names.json → batches/ (팬아웃 단위)")
    b.add_argument("--run-dir", required=True)
    b.add_argument("--size", type=int, default=8, help="배치당 상품 수(기본 8)")
    b.set_defaults(func=cmd_batch)

    pd = sub.add_parser("pending", help="남은 배치를 Workflow args JSON 으로 출력")
    pd.add_argument("--run-dir", required=True)
    pd.set_defaults(func=cmd_pending)

    mg = sub.add_parser("merge", help="named/*.json → keywords.json")
    mg.add_argument("--run-dir", required=True)
    mg.add_argument("--keywords", help="출력 경로(기본 run-dir/keywords.json)")
    mg.add_argument("--allow-missing", action="store_true",
                    help="누락이 있어도 강행(기본은 exit 3)")
    mg.set_defaults(func=cmd_merge)

    st = sub.add_parser("steer", help="저장 폴백 1단계(유도) 자동 실행")
    st.add_argument("--run-dir", required=True)
    st.add_argument("--threshold", default="70")
    st.add_argument("--sleep", default="0.3")
    st.add_argument("--dry-run", action="store_true")
    st.add_argument("--no-sheet", action="store_true")
    st.set_defaults(func=cmd_steer)

    au = sub.add_parser("auto", help="merge→finish→steer (백그라운드 진입점)")
    au.add_argument("--run-dir", required=True)
    au.add_argument("--keywords")
    au.add_argument("--allow-missing", action="store_true")
    au.add_argument("--threshold", default="70")
    au.add_argument("--sleep", default="0.4")
    au.add_argument("--dry-run", action="store_true")
    au.add_argument("--no-sheet", action="store_true")
    au.add_argument("--force", action="store_true", help="셀하 재조회")
    au.add_argument("--sellha-sleep", default="3",
                   help="셀하 조회 간 최소 대기(초)")
    au.add_argument("--sellha-sleep-max", default="10",
                   help="셀하 조회 간 최대 대기(초). 실제는 최소~최대 난수")
    au.add_argument("--sellha-rest-every", default="25",
                   help="평균 N건마다 긴 휴식. 0=끔")
    au.set_defaults(func=cmd_auto)

    r = sub.add_parser("recheck", help="2바퀴: 보류(정체불명) 건 증거 보강")
    r.add_argument("--run-dir", required=True)
    r.add_argument("--keywords", help="keywords.json 경로(기본 run-dir/keywords.json)")
    r.add_argument("--ids", nargs="+", help="대상 productId 직접 지정(기본=보류 전건)")
    r.set_defaults(func=cmd_recheck)

    # prep/finish 는 상위 --sheet/--tab 을 물려받도록 보정
    args = ap.parse_args()
    if not hasattr(args, "sheet"):
        args.sheet = SHEET
    args.func(args)


if __name__ == "__main__":
    main()
