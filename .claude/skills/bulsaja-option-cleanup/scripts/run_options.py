#!/usr/bin/env python3
"""옵션 정리 오케스트레이터 — 스킬 계약(`prep`/`run`/`apply`)의 첫 사용자.

  prep  : 현황판에서 대상 확정 → 스냅샷(옵션 포함) → 옵션 이미지 → 배치 파일
  run   : **Claude 워커**가 배치를 읽고 판단 → results/result_*.json (스크립트 아님)
  apply : 계산·검증 → 시트 기록 → (승인 후) 저장 → 재조회 검증 → 스냅샷·현황판 갱신

판단(무엇이 메인상품인가·이 옵션이 비상품인가·이름을 뭐라 지을까)은 Claude 가,
계산(대표·1.5배 상한·순서·검증)은 `option_rules.py` 가 한다. 규칙 전문은 SKILL.md.

사용:
  python run_options.py prep    --group-name "1번_용쌤1-1" --run-dir <R> --limit 5
  python run_options.py pending --run-dir <R>          # Workflow(optclean-fanout) args 출력
  python run_options.py apply   --run-dir <R>          # 미리보기(승인 게이트)
  python run_options.py apply   --run-dir <R> --commit # 실제 저장
"""
import argparse
import glob
import json
import os
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

# `.claude` 앵커를 찾아 lib 를 sys.path 에 올린다.
_d = SCRIPT_DIR
while _d and _d != os.path.dirname(_d):
    _lib = os.path.join(_d, "lib")
    if os.path.isdir(os.path.join(_lib, "eroomlib")):
        if _lib not in sys.path:
            sys.path.insert(0, _lib)
        break
    _d = os.path.dirname(_d)

import option_rules as R  # noqa: E402
from eroomlib import matrix, snapshot  # noqa: E402
from eroomlib.config import cfg  # noqa: E402
from eroomlib.gsheets import (append_rows, ensure_tab,  # noqa: E402
                              sheets_get, sheets_update)
from eroomlib.matrix import _col_letter  # noqa: E402

TASK = "옵션"          # 현황판 열 이름
TAB = "옵션"           # 상세 로그 탭
# `옵션명변경` 은 뒤에 붙인다 — 기존 탭에 이미 쌓인 행의 열이 밀리지 않게(ensure_tab 이 꼬리만 잇는다).
HEADER = ["상품id", "작업일", "상품명", "메인상품", "옵션수", "유지", "제외",
          "대표옵션", "기준가", "상한", "순서", "상태", "메모", "옵션명변경"]

# 배치당 상품 수. 상품 1건에 옵션이 4~28개라 5건이면 워커 한 턴에 들어간다
# (카테고리교정 10건/배치보다 작다 — 옵션은 건당 정보량이 훨씬 크다).
BATCH_SIZE = 5

# 팬아웃용 고정 경로 — 규칙 정본과 워커 지시서(run_all.py 의 RULES_DOC 패턴).
RULES_DOC = os.path.normpath(os.path.join(
    SCRIPT_DIR, "..", "references", "옵션명-규칙.md"))
WORKER_PROMPT = os.path.normpath(os.path.join(
    SCRIPT_DIR, "..", "references", "옵션-워커-프롬프트.md"))


def _dump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _today():
    import datetime
    return datetime.date.today().isoformat()


class OptionMCP(snapshot.ProductMCP):
    """transport + workdata 는 상속하고, 이 스킬 고유 도구만 얹는다."""

    def option_update(self, product_id, **kw):
        """bulsaja_option_update — **미리보기 → 확인키로 커밋** 2단계(카테고리 저장과 같다).

        1번만 부르면 `success:false` + `confirmationToken` 만 오고 **아무것도 저장되지 않는다**
        (2026-07-28: 이걸 놓쳐 파일럿 5건이 전부 '저장한 줄 알았는데 무변경'이었다.
         재조회 검증이 막아줘서 손상은 0이었다).

        **renameValues 와 정렬은 같은 호출에 넣지 않는다** — 쿠팡 기존 옵션 연결 보호.
        반환: 커밋 응답. 실패면 예외.
        """
        if kw.get("renameValues") and (kw.get("sortOrder") or kw.get("skuOrder")):
            raise ValueError("이름 변경과 순서 변경은 같은 호출에 넣을 수 없다")
        payload = {"productId": product_id}
        payload.update({k: v for k, v in kw.items() if v not in (None, [], "")})

        pv = self.call_tool("bulsaja_option_update", payload)
        token = pv.get("confirmationToken")
        if not token:
            if pv.get("success"):
                return pv  # 확인이 필요 없는 응답(변경 없음 등)
            raise RuntimeError(f"확인키 미발급: {str(pv.get('message'))[:200]}")
        r = self.call_tool("bulsaja_option_update",
                           {**payload, "confirm": True, "confirmationToken": token})
        if not r.get("success"):
            raise RuntimeError(f"저장 실패: {str(r.get('message'))[:200]}")
        return r


# ---------------------------------------------------------------------------
# prep
# ---------------------------------------------------------------------------

def _resolve_sheet(args):
    if getattr(args, "sheet", None):
        return args.sheet
    name = (getattr(args, "group_name", "") or "").strip()
    if not name:
        raise RuntimeError("--sheet 또는 --group-name 중 하나는 필요하다")
    for g, sid in matrix.index_groups():
        if g == name:
            return sid
    hits = [(g, sid) for g, sid in matrix.index_groups() if name in g]
    if len(hits) != 1:
        raise RuntimeError(f"'{name}' 으로 그룹 시트를 특정하지 못했다(후보 {len(hits)}개)")
    return hits[0][1]


def cmd_prep(args):
    run_dir = os.path.abspath(args.run_dir)
    os.makedirs(run_dir, exist_ok=True)
    sheet = _resolve_sheet(args)
    print(f"  시트: {sheet}")

    # 1) 대상 확정 — 현황판 쿼리 1줄(계약 §대상 선정). --ids 면 그것만.
    m = matrix.read(sheet)
    if args.ids:
        pids = [i for i in args.ids if i.strip()]
        missing = [i for i in pids if i not in m]
        if missing:
            print(f"  [경고] 현황판에 없는 상품 {len(missing)}건: {missing[:3]}")
    else:
        pids = matrix.pending(m, TASK)
        print(f"[1/4] 현황판 '{TASK}' 미착수 {len(pids)}건")
    if args.limit:
        pids = pids[:args.limit]
        print(f"  --limit {args.limit} 적용 → {len(pids)}건")
    if not pids:
        print("처리할 상품이 없다.")
        return

    # 2) 스냅샷 — `옵션` 이 없는 옛 캐시는 자동 재조회된다
    print(f"[2/4] 스냅샷 확보 {len(pids)}건")
    recs, errors = snapshot.ensure(pids, sleep=args.sleep, require=("옵션",))
    if errors:
        print(f"  조회 실패 {len(errors)}건: {list(errors)[:3]}")

    # 3) 이미지 — 대표 썸네일 1장 + 옵션값 이미지(차원별). 실물·구성 판별의 근거다.
    thumbs_dir = os.path.join(run_dir, "thumbs")
    img = {}
    if not args.skip_thumbs:
        n = 0
        for pid, rec in recs.items():
            paths = {}
            rep = (rec.get("썸네일") or [""])[0]
            if rep:
                p, _ = snapshot.materialize_image(rep, thumbs_dir, pid + "_rep", 0)
                if p:
                    paths["대표"] = p
            for gi, d in enumerate(rec.get("옵션", {}).get("차원") or []):
                for vi, v in enumerate((d.get("values") or [])[:args.max_option_images]):
                    if not v.get("imageUrl"):
                        continue
                    p, _ = snapshot.materialize_image(
                        v["imageUrl"], thumbs_dir, f"{pid}_{gi}", vi)
                    if p:
                        paths[f"{gi}:{v.get('vid')}"] = p
            img[pid] = paths
            n += len(paths)
        print(f"[3/4] 이미지 {n}장 확보(캐시 적중분은 복사만)")
    _dump(os.path.join(run_dir, "images.json"), img)

    # 4) 배치 — 워커가 파일 하나로 완주할 수 있게 자기완결형으로 담는다
    products = []
    for pid in pids:
        rec = recs.get(pid)
        if not rec:
            continue
        o = rec.get("옵션") or {}
        products.append({
            "productId": pid,
            "상품명": rec.get("상품명", ""),
            "원문명": rec.get("원문명", ""),
            "카테고리": rec.get("기존카테고리", ""),
            "대표썸네일": img.get(pid, {}).get("대표", ""),
            "vid고유": o.get("vid고유"),
            "차원": [{
                "index": gi, "이름": d.get("이름"), "원문이름": d.get("원문이름"),
                "values": [{
                    "vid": v.get("vid"), "현재이름": v.get("name"),
                    "원문": v.get("_name"), "제외됨": v.get("exclude"),
                    "이미지": img.get(pid, {}).get(f"{gi}:{v.get('vid')}", ""),
                } for v in (d.get("values") or [])],
            } for gi, d in enumerate(o.get("차원") or [])],
            "판매행": [{
                "id": r["id"], "표시명": r.get("text"), "원문": r.get("_text"),
                "판매가": r.get("sale_price"), "재고": r.get("stock"),
                "현재제외": r.get("exclude"), "현재대표": r.get("main_product"),
            } for r in (o.get("판매행") or [])],
        })

    batches = [products[i:i + args.batch_size]
               for i in range(0, len(products), args.batch_size)]
    index = []
    for i, b in enumerate(batches, 1):
        path = os.path.abspath(os.path.join(run_dir, "batches", f"batch_{i:03d}.json"))
        _dump(path, {"배치": i, "규칙문서": RULES_DOC, "products": b})
        # imgs = 배치에 실린 **실제 이미지 파일 수**(대표+옵션값) — 팬아웃 빈패킹의 예산 축.
        index.append({"n": i, "path": path, "imgs": _batch_imgs(b),
                      "count": len(b),
                      "옵션수": sum(len(p["판매행"]) for p in b)})
    _dump(os.path.join(run_dir, "batches_index.json"), index)
    print(f"\n###PREP### 배치 {len(batches)}개 / 상품 {len(products)}건 / "
          f"옵션 {sum(len(p['판매행']) for p in products)}개 / "
          f"이미지 {sum(x['imgs'] for x in index)}장")
    print(f"  배치: {os.path.join(run_dir, 'batches')}")
    print(f"  다음(Workflow 모드): python {os.path.basename(__file__)} pending "
          f"--run-dir <R> → optclean-fanout 호출 → apply")
    print(f"  다음(수동 폴백): 워커가 배치를 읽고 results/result_NNN.json 생성 → apply")


def _batch_imgs(products):
    """배치 products 에 실린 이미지 파일 수 — 대표썸네일 + 옵션값 이미지(경로가 찬 것만)."""
    n = 0
    for p in products:
        if p.get("대표썸네일"):
            n += 1
        for d in (p.get("차원") or []):
            n += sum(1 for v in (d.get("values") or []) if v.get("이미지"))
    return n


def _pending_batches(run_dir):
    """results/result_NNN.json 이 없는 배치 = 아직 안 된 것. 디스크가 정본이다."""
    idx_path = os.path.join(run_dir, "batches_index.json")
    if not os.path.exists(idx_path):
        return []
    index = _load(idx_path)
    out = []
    for b in index:
        if "n" not in b:
            # 구형 index(파일명·상품수만) 폴백 — 배치 파일에서 재계산한다.
            n = int(str(b.get("batch", "")).replace("batch_", "").replace(".json", "") or 0)
            path = os.path.abspath(os.path.join(run_dir, "batches", b.get("batch", "")))
            imgs = _batch_imgs(_load(path).get("products", [])) if os.path.exists(path) else 0
            b = {"n": n, "path": path, "imgs": imgs, "count": b.get("상품수", 0)}
        if not os.path.exists(os.path.join(
                run_dir, "results", f"result_{b['n']:03d}.json")):
            out.append(b)
    return out


def cmd_pending(args):
    """남은 배치를 JSON 한 줄로 찍는다 — Workflow(optclean-fanout) args 에 그대로 넣는다."""
    run_dir = os.path.abspath(args.run_dir)
    print(json.dumps({"runDir": run_dir, "promptPath": WORKER_PROMPT,
                      "batches": _pending_batches(run_dir)}, ensure_ascii=False))


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------

def _expected_by_batch(run_dir):
    """batches/batch_NNN.json → {배치번호: [productId, ...]}. 없으면 빈 dict(구형 run-dir)."""
    exp = {}
    for bf in sorted(glob.glob(os.path.join(run_dir, "batches", "batch_*.json"))):
        doc = _load(bf)
        n = doc.get("배치") or int(os.path.basename(bf)[6:9])
        exp[n] = [p.get("productId") for p in doc.get("products", []) if p.get("productId")]
    return exp


def _audit_results(run_dir):
    """워커 산출물을 배치 대비 대조 — 누락·환각·번호 불일치를 apply 전에 잡는다.

    catfix `merge_named` 와 같은 역할이다. 워커가 상품을 빠뜨리면 그대로 조용히
    사라지던 결함(팬아웃 도입 전에는 메인이 직접 결과를 만들어 없던 문제)의 방어선.
    반환: (경고 문자열 리스트, 누락 여부 bool)
    """
    exp = _expected_by_batch(run_dir)
    if not exp:
        return [], False          # 구형 run-dir — 대조할 정본이 없다
    got, files = set(), {}
    for rf in sorted(glob.glob(os.path.join(run_dir, "results", "result_*.json"))):
        doc = _load(rf)
        n_file = int(os.path.basename(rf)[7:10])
        n_doc = doc.get("배치")
        if n_doc is not None and n_doc != n_file and n_file != 0:
            files.setdefault("번호불일치", []).append(
                f"{os.path.basename(rf)} 내부 배치={n_doc}")
        got |= {p.get("productId") for p in doc.get("products", []) if p.get("productId")}
    want = {pid for pids in exp.values() for pid in pids}
    missing = sorted(want - got)
    unknown = sorted(got - want)
    warns = []
    done_batches = {n for n, pids in exp.items() if all(p in got for p in pids)}
    miss_batches = sorted(set(exp) - done_batches)
    if miss_batches:
        warns.append(f"미완 배치 {len(miss_batches)}개: {miss_batches[:10]}")
    if missing:
        warns.append(f"누락 상품 {len(missing)}건: {missing[:5]}")
    if unknown:
        warns.append(f"미지의 상품id {len(unknown)}건(워커 환각 — 버린다): {unknown[:5]}")
    for msg in files.get("번호불일치", []):
        warns.append(f"파일명↔내부 배치번호 불일치: {msg}")
    return warns, bool(missing)


def _plans(run_dir):
    """results/*.json + 스냅샷 → [(상품, 계획, 결과)]. 불사자를 부르지 않는다.

    같은 pid 가 여러 파일에 있으면(재팬아웃 잔재) **마지막 파일이 이긴다.**
    배치 정본이 있으면 거기 없는 pid(워커 환각)는 버린다 — 원장 오염 방지.
    """
    exp = _expected_by_batch(run_dir)
    allow = {pid for pids in exp.values() for pid in pids} if exp else None
    by_pid, order = {}, []
    for rf in sorted(glob.glob(os.path.join(run_dir, "results", "result_*.json"))):
        for p in _load(rf).get("products", []):
            pid = p.get("productId")
            if not pid:
                continue
            if allow is not None and pid not in allow:
                continue          # 환각 — _audit_results 가 경고로 집계한다
            if pid not in by_pid:
                order.append(pid)
            by_pid[pid] = p       # 마지막 파일 승리
    out = []
    for pid in order:
        p = by_pid[pid]
        rec = snapshot.load(pid) if pid else None
        if not rec or not rec.get("옵션"):
            out.append((pid, None, {**p, "상태": "보류(스냅샷 없음)"}))
            continue
        # 워커 결과에 상품명이 없으면 스냅샷에서 채운다 — 없으면 시트 C열과
        # 검수표 머리글이 통째로 빈칸이 된다(어느 상품을 승인하는지 알 수 없다).
        if not p.get("상품명"):
            p["상품명"] = rec.get("상품명", "")
        names = {str(k): v for k, v in (p.get("이름") or {}).items()}
        plan = R.plan(rec["옵션"],
                      keep_ids=set(p.get("유지") or ()),
                      names=names,
                      prefer_id=p.get("대표후보"))
        # 계산은 id 로 하고, 승인은 이름으로 본다. 라벨을 여기서 한 번 만들어
        # 시트·--emit·미리보기 표가 같은 문자열을 쓰게 한다(어긋나면 두 벌이 된다).
        plan["라벨"] = R.row_labels(rec["옵션"], names)
        plan["이름변경"] = R.name_changes(rec["옵션"], names)
        plan["가격"] = {str(r["id"]): r.get("sale_price")
                      for r in (rec["옵션"].get("판매행") or [])}
        # 복합옵션인데 마지막 차원 값이 1개뿐이면 — 전 조합이 그 값을 공유해서 규칙 17
        # (마지막 항목에 마커)대로 저장하면 모든 조합에 '기본형'이 보인다(전면 오염).
        # 기준 재정 전까지 자동 저장하지 않고 수동 판단(2026-08-01 이룸님, 사례 수집 중).
        dims = rec["옵션"].get("차원") or []
        if len(dims) >= 2 and len(dims[-1].get("values") or []) == 1:
            plan["마커수동"] = True
        out.append((pid, plan, p))
    return out


def _lab(plan, rid):
    """판매행 id → 사람이 읽을 이름(없으면 id 그대로)."""
    return ((plan or {}).get("라벨") or {}).get(str(rid), str(rid))


def _price(plan, rid):
    return ((plan or {}).get("가격") or {}).get(str(rid))


def _status_of(plan, worker):
    if plan is None:
        return worker.get("상태") or "보류(스냅샷 없음)"
    if not plan.get("대표"):
        return "보류(남길 옵션 없음)"
    chk = plan.get("이름검사") or {}
    if chk.get("위반") or chk.get("중복"):
        return "보류(이름규칙)"
    # 마지막 차원 값 1개짜리 복합옵션 — 마커를 어디 붙여도 문제라 수동 판단으로 넘긴다.
    # 규칙대로(@마지막차원) 붙인 결과가 검증을 '통과'해 전면 오염이 자동 저장되는 걸 막는다.
    if plan.get("마커수동"):
        return "보류(기본형 수동판단)"
    # 대표옵션 마커('기본형')는 상품명 끝의 같은 단어와 짝을 이루는 유일한 표식이다 —
    # 없거나 대표 아닌 옵션에 붙어 있으면 저장 전에 멈춘다(2026-07-30 이룸님).
    mark = chk.get("마커") or {}
    if mark.get("누락") or mark.get("오부착"):
        return "보류(기본형)"
    if plan.get("경고"):
        return "확인요"
    return "정리대상"


def _print_table(rows):
    print(f"\n{'상품id':<28} {'상태':<14} {'대표':<24} {'기준가':>9} {'상한':>9} 유지/전체")
    print("-" * 104)
    for pid, plan, w, st in rows:
        if plan:
            rep = f"{_lab(plan, plan['대표'])}({plan['대표']})"
            print(f"{pid:<28} {st:<14} {rep[:23]:<24} "
                  f"{(plan['기준가'] or 0):>9,} {(plan['상한'] or 0):>9,} "
                  f"{len(plan['유지'])}/{len(plan['유지']) + len(plan['제외'])}")
        else:
            print(f"{pid:<28} {st:<14}")


def _print_review(rows):
    """승인 검수표 — 승인해야 할 **옵션명 그 자체**를 보여준다.

    신호(⚠)는 "이상하다"를 가리킬 뿐 무엇을 승인하는지 알려주지 않는다. 실전 1건에서
    이룸님이 지적한 결함: 교정된 옵션명이 표·시트·plans.json 어디에도 없었다.
    """
    for pid, plan, w, st in rows:
        if not plan:
            continue
        print(f"\n── 검수표 {pid} · {w.get('상품명', '')[:40]}")
        if w.get("메인상품"):
            print(f"   메인상품: {w['메인상품']}")
        print(f"   대표 {_lab(plan, plan['대표'])} · 기준가 {(plan['기준가'] or 0):,} "
              f"→ 상한 {(plan['상한'] or 0):,}")

        chg = [c for c in (plan.get("이름변경") or []) if c["변경"]]
        same = len(plan.get("이름변경") or []) - len(chg)
        if chg:
            print(f"   [옵션명 교정 {len(chg)}건 · 유지 {same}건]")
            for c in chg:
                pre = f"{c['차원']}·" if c["차원"] else ""
                print(f"     {pre}{c['키']:>4} {c['기존']}  →  {c['교정']}")
        elif plan.get("이름변경"):
            print(f"   [옵션명 교정 0건 — {same}건 그대로]")

        print(f"   [판매 {len(plan['유지'])}건 · 업로드 순서(판매가 오름차순)]")
        for i, rid in enumerate(plan.get("순서") or [], 1):
            mark = "★" if str(rid) == str(plan["대표"]) else " "
            print(f"     {mark}{i:>2}. {_lab(plan, rid):<26} {(_price(plan, rid) or 0):>9,}")
        if plan.get("제외"):
            print(f"   [제외 {len(plan['제외'])}건]")
            for e in plan["제외"]:
                print(f"      - {_lab(plan, e['id'])} — {e['사유']}")


def cmd_apply(args):
    run_dir = os.path.abspath(args.run_dir)
    sheet = _resolve_sheet(args)
    # 감사 — 워커 산출물을 배치 정본과 대조. 미리보기는 경고만, --commit 은 누락 시 차단.
    warns, has_missing = _audit_results(run_dir)
    for w in warns:
        print(f"  [감사] {w}")
    if args.commit and has_missing and not getattr(args, "allow_missing", False):
        print("\n누락 상품이 있어 --commit 을 차단한다. "
              "pending 재계산 → 재팬아웃으로 채우거나, 의도된 것이면 --allow-missing.",
              file=sys.stderr)
        sys.exit(3)
    items = _plans(run_dir)
    if not items:
        print(f"results 가 없다: {os.path.join(run_dir, 'results')}")
        return
    rows = [(pid, plan, w, _status_of(plan, w)) for pid, plan, w in items]
    _print_table(rows)
    if not args.no_review:
        _print_review(rows)

    for pid, plan, w, st in rows:
        if plan and plan.get("경고"):
            for x in plan["경고"]:
                print(f"  [경고] {pid}: {x}")
        if plan and (plan.get("이름검사") or {}).get("위반"):
            print(f"  [이름] {pid}: {plan['이름검사']['위반']}")
        mark = ((plan or {}).get("이름검사") or {}).get("마커") or {}
        if mark.get("누락"):
            print(f"  [기본형] {pid}: 대표옵션 이름이 '{R.BASE_SUFFIX}'로 끝나지 않는다 "
                  f"(대표값키 {plan.get('대표값키') or '없음'})")
        if mark.get("오부착"):
            print(f"  [기본형] {pid}: 대표가 아닌 옵션에 붙었다 {mark['오부착'][:3]}")

    ok = [r for r in rows if r[3] == "정리대상"]
    print(f"\n정리대상 {len(ok)}건 / 확인요·보류 {len(rows) - len(ok)}건")

    # --emit: 계획 요약을 JSON 으로 남긴다. 세로 러너(onestep)의 이상 신호 판정이 읽는다.
    # 표는 사람용이라 파싱 대상이 아니고, plan 객체는 내부 구조라 그대로 노출하지 않는다.
    if args.emit:
        _dump(args.emit, [{
            "productId": pid,
            "상태": st,
            "메인상품": (w or {}).get("메인상품", ""),
            "유지수": len((plan or {}).get("유지") or []),
            "제외수": len((plan or {}).get("제외") or []),
            "판매행수": len((plan or {}).get("순서") or []),
            "대표": (plan or {}).get("대표") or "",
            # 이름 3종은 **승인 자료**다. id 만 있으면 게이트에서 무엇을 승인하는지 알 수 없다.
            "대표이름": _lab(plan, (plan or {}).get("대표")) if plan else "",
            "순서이름": [_lab(plan, i) for i in ((plan or {}).get("순서") or [])],
            "순서상세": [{"id": i, "이름": _lab(plan, i), "판매가": _price(plan, i),
                      "대표": str(i) == str((plan or {}).get("대표"))}
                     for i in ((plan or {}).get("순서") or [])],
            "이름변경": [c for c in ((plan or {}).get("이름변경") or []) if c["변경"]],
            "제외상세": [{"id": e["id"], "이름": _lab(plan, e["id"]), "사유": e["사유"]}
                     for e in ((plan or {}).get("제외") or [])],
            "기준가": (plan or {}).get("기준가") or "",
            "상한": (plan or {}).get("상한") or "",
            "경고": list((plan or {}).get("경고") or []),
            "이름위반": list(((plan or {}).get("이름검사") or {}).get("위반") or []),
            # 대표옵션 마커 — 게이트에서 "썸네일=대표옵션=상품명"이 맞는지 보는 재료
            "대표값키": (plan or {}).get("대표값키") or "",
            "기본형누락": bool((((plan or {}).get("이름검사") or {}).get("마커")
                           or {}).get("누락")),
            "기본형오부착": list((((plan or {}).get("이름검사") or {}).get("마커")
                             or {}).get("오부착") or []),
        } for pid, plan, w, st in rows])
        print(f"  계획 요약: {args.emit}")

    if not args.no_sheet:
        _log_sheet(sheet, rows)

    if not args.commit:
        print("\n미리보기다. 실제 반영하려면 이룸님 승인 후 --commit 을 붙여라.")
        return

    _commit(sheet, rows, args)


def _row_values(pid, plan, w, st):
    """시트 1행. **id 가 아니라 이름으로 적는다** — 사람이 이걸 보고 승인한다."""
    chg = [c for c in ((plan or {}).get("이름변경") or []) if c["변경"]]
    return [
        pid, _today(), w.get("상품명", ""), w.get("메인상품", ""),
        (len(plan["유지"]) + len(plan["제외"])) if plan else "",
        len(plan["유지"]) if plan else "",
        "; ".join(f"{_lab(plan, e['id'])}:{e['사유']}"
                  for e in (plan["제외"] if plan else []))[:900],
        f"{_lab(plan, plan['대표'])} ({plan['대표']})" if plan and plan.get("대표") else "",
        (plan or {}).get("기준가") or "", (plan or {}).get("상한") or "",
        " > ".join(_lab(plan, i) for i in ((plan or {}).get("순서") or []))[:900],
        st, "; ".join((plan or {}).get("경고") or [])[:400] or w.get("메모", ""),
        "; ".join(f"{c['기존']}→{c['교정']}" for c in chg)[:900],
    ]


def _log_sheet(sheet, rows):
    """탭에 기록한다. **이미 있는 상품id 는 건너뛰지 않고 그 행을 갱신한다** —
    되돌려 다시 돌렸을 때 옛 계획이 시트에 남아 있으면 승인 자료가 거짓이 된다."""
    if ensure_tab(sheet, TAB, HEADER):
        print(f"  탭 신설: {TAB}")
    try:
        col_a = [str(r[0]).strip() if r else "" for r in sheets_get(sheet, f"'{TAB}'!A2:A")]
    except Exception:
        col_a = []
    at = {pid: i + 2 for i, pid in enumerate(col_a) if pid}   # 상품id → 시트 행번호
    last = _col_letter(len(HEADER))

    add = []
    for pid, plan, w, st in rows:
        vals = _row_values(pid, plan, w, st)
        r = at.get(pid)
        if r:
            sheets_update(sheet, f"'{TAB}'!A{r}:{last}{r}", [vals],
                          value_input="USER_ENTERED")
            print(f"  시트 갱신: {pid} → '{TAB}'!{r}행")
            # 구글시트 쓰기 쿼터(분당 60회) — 재실행으로 기존 행을 대량 갱신할 때
            # 연속호출이 걸린다(2026-08-02 118행에서 실측). 여유 있게 1.1초 간격.
            time.sleep(1.1)
        else:
            add.append(vals)
    if add:
        # 청크 분할(호출자 책임, gsheets.append_rows 계약) — 한 번에 다 보내면
        # Windows 명령줄 길이 제한(WinError 206)에 걸린다(2026-08-02 118행에서 실측).
        CHUNK = 20
        for i in range(0, len(add), CHUNK):
            append_rows(sheet, TAB, add[i:i + CHUNK])
        print(f"  시트 기록: {len(add)}행 → '{TAB}'")


def _commit(sheet, rows, args):
    """분리 저장 — ①이름 → 재조회·검증 → ②포함/제외·대표·순서 → 재조회·검증 6항목.

    이름과 순서를 **한 호출에 넣지 않는다**(쿠팡 옵션 연결 보호). 그래서 2단계다.
    """
    targets = [r for r in rows if r[3] == "정리대상"]
    if not targets:
        print("정리대상이 없다.")
        return
    # 저장 직전 상태를 run-dir 에 남긴다(헤르메스 12 단계6 "저장 직전 스냅샷 기록").
    # 스냅샷은 저장 성공 시 새 값으로 덮어쓰므로, 되돌리려면 이 백업이 유일한 원본이다.
    backup_path = os.path.join(args.run_dir, "before_commit.json")
    backup = {pid: (snapshot.load(pid) or {}).get("옵션") or {}
              for pid, _, _, _ in targets}
    _dump(backup_path, backup)
    print(f"  저장 전 상태 백업: {backup_path} ({len(backup)}건)")
    print(f"  되돌리기: python {os.path.basename(__file__)} restore --run-dir {args.run_dir}")

    mcp = OptionMCP()
    mcp.open()
    done, failed = {}, {}
    try:
        for pid, plan, w, _ in targets:
            before = backup.get(pid) or {}
            names = {str(k): v for k, v in (w.get("이름") or {}).items()}
            try:
                # ① 이름 먼저 (정렬과 같은 호출 금지)
                if names:
                    items, missing = R.rename_targets(before, names)
                    if missing:
                        raise RuntimeError(f"옵션값을 못 찾았다: {missing[:5]}")
                    mcp.option_update(pid, renameValues=items)
                    time.sleep(args.sleep)
                    mid = mcp.workdata(pid).get("옵션") or {}
                    # 위치 지정 키로 본다 — vid 로 dict 를 만들면 복합옵션에서 차원끼리
                    # vid 가 겹쳐 서로를 덮어써서 검사에서 조용히 빠진다.
                    bad = R.check_names(R.effective_names(mid),
                                        groups=R.pos_groups(mid))
                    if bad["위반"] or bad["중복"]:
                        raise RuntimeError(f"이름 저장 후 검증 실패: {bad}")

                # ② 포함/제외 · 대표 · 순서
                keep = list(plan["유지"])
                drop = [e["id"] for e in plan["제외"]]
                mcp.option_update(pid, includeSkuIds=keep, excludeSkuIds=drop,
                                  mainSkuId=plan["대표"], skuOrder=plan["순서"])
                time.sleep(args.sleep)

                after = mcp.workdata(pid).get("옵션") or {}
                fails = R.verify(before, after, plan, names=names or None)
                if fails:
                    raise RuntimeError("; ".join(fails)[:300])
                snapshot.update(pid, 옵션=after)
                done[pid] = "완료"
                print(f"  [완료] {pid} 유지 {len(keep)} / 제외 {len(drop)} / 대표 {plan['대표']}")
            except Exception as e:  # noqa: BLE001
                failed[pid] = f"{type(e).__name__}: {e}"[:200]
                print(f"  [실패] {pid}: {failed[pid]}", file=sys.stderr)
    finally:
        mcp.close()

    print(f"\n###OPTIONS### 반영 {len(done)}건 / 실패 {len(failed)}건")
    if not args.no_sheet:
        vals = dict(done)
        vals.update({pid: f"보류(저장실패)" for pid in failed})
        try:
            m = matrix.read(sheet)
            n = matrix.mark_many(sheet, TASK, vals, matrix=m)
            print(f"  현황판({matrix.TAB}) {TASK}: {n}칸 갱신")
            _handoff(sheet, rows, done, m)
        except Exception as e:  # noqa: BLE001
            print(f"  [경고] 현황판 갱신 실패: {str(e)[:120]}", file=sys.stderr)


def _handoff(sheet, rows, done, m):
    """워커가 남긴 `이관` 을 다른 단계의 현황판 칸으로 넘긴다.

    옵션을 보다 보면 옵션 범위 **밖**의 문제가 보인다 — 썸네일에 없는 색, 상품명 오표기.
    전에는 이걸 자유 텍스트 메모로만 남겨서 받는 쪽이 읽을 경로가 없었다
    (파일럿 5건 중 3건이 그렇게 유실됐다). 이제 현황판 칸으로 넘겨
    받는 단계가 `pending(..., include_redo=True)` 로 한꺼번에 집어간다.

    결과 JSON 형식:  "이관": [{"단계": "썸네일", "사유": "대표색 불일치"}]
    """
    by_task = {}
    for pid, _plan, w, _st in rows:
        if pid not in done:          # 저장 성공한 건만 넘긴다
            continue
        for h in (w.get("이관") or []):
            task, reason = (h.get("단계") or "").strip(), (h.get("사유") or "").strip()
            if task not in matrix.TASKS or not reason:
                print(f"  [경고] 이관 무시({pid}): 단계 '{task}'")
                continue
            by_task.setdefault(task, {})[pid] = reason
    for task, items in by_task.items():
        k = matrix.flag_many(sheet, task, items, from_task=TASK, matrix=m)
        print(f"  {task} 재작업 표시: {k}건")


def cmd_restore(args):
    """`before_commit.json` 으로 저장 전 상태를 되돌린다.

    이름 → 포함/제외·대표·순서 순서로 되돌리되, **이름과 순서는 같은 호출에 넣지 않는다**
    (저장 때와 같은 제약). 완전 복구는 백업이 있을 때만 가능하다.
    """
    path = os.path.join(os.path.abspath(args.run_dir), "before_commit.json")
    if not os.path.exists(path):
        print(f"백업이 없다: {path} — 되돌릴 수 없다.")
        return
    backup = _load(path)
    only = set(args.ids or ())
    mcp = OptionMCP()
    mcp.open()
    ok, bad = 0, {}
    try:
        for pid, before in backup.items():
            if only and pid not in only:
                continue
            rows = before.get("판매행") or []
            if not rows:
                bad[pid] = "백업에 판매행이 없다"
                continue
            try:
                names = {str(v.get("vid")): v.get("name")
                         for d in (before.get("차원") or [])
                         for v in (d.get("values") or []) if v.get("name")}
                if names:
                    items, _ = R.rename_targets(before, names)
                    if items:
                        mcp.option_update(pid, renameValues=items)
                        time.sleep(args.sleep)
                keep = [r["id"] for r in rows if not r.get("exclude")]
                drop = [r["id"] for r in rows if r.get("exclude")]
                main_id = next((r["id"] for r in rows if r.get("main_product")), None)
                mcp.option_update(pid, includeSkuIds=keep, excludeSkuIds=drop,
                                  mainSkuId=main_id,
                                  skuOrder=[r["id"] for r in rows])
                time.sleep(args.sleep)
                snapshot.update(pid, 옵션=mcp.workdata(pid).get("옵션") or {})
                ok += 1
                print(f"  [복구] {pid}")
            except Exception as e:  # noqa: BLE001
                bad[pid] = f"{type(e).__name__}: {e}"[:200]
                print(f"  [실패] {pid}: {bad[pid]}", file=sys.stderr)
    finally:
        mcp.close()
    print(f"\n###RESTORE### 복구 {ok}건 / 실패 {len(bad)}건")


def main():
    ap = argparse.ArgumentParser(description="불사자 옵션 정리")
    sub = ap.add_subparsers(dest="cmd", required=True)

    # 하위 명령 뒤에 써도 먹히게 각 파서에 붙인다(`prep --group-name ...`).
    def _common(x):
        x.add_argument("--sheet", default="", help="그룹 시트 id(직접 지정)")
        x.add_argument("--group-name", default="", help="마켓그룹명 (예: 1번_용쌤1-1)")

    p = sub.add_parser("prep", help="대상 확정 → 스냅샷 → 이미지 → 배치")
    _common(p)
    p.add_argument("--run-dir", required=True)
    p.add_argument("--ids", nargs="+", default=None)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    p.add_argument("--sleep", type=float, default=0.3)
    p.add_argument("--skip-thumbs", action="store_true")
    p.add_argument("--max-option-images", type=int, default=12,
                   help="차원당 내려받을 옵션 이미지 수(전 옵션이 필요하면 늘려라)")
    p.set_defaults(func=cmd_prep)

    q = sub.add_parser("pending", help="results 없는 배치를 Workflow args JSON 으로 출력")
    q.add_argument("--run-dir", required=True)
    q.set_defaults(func=cmd_pending)

    a = sub.add_parser("apply", help="계산·검증 → 시트 → (승인 후) 저장")
    _common(a)
    a.add_argument("--run-dir", required=True)
    a.add_argument("--commit", action="store_true", help="실제 저장(없으면 미리보기)")
    a.add_argument("--allow-missing", action="store_true",
                   help="감사에서 누락 상품이 있어도 --commit 강행(의도된 부분 처리)")
    a.add_argument("--emit", default="", help="계획 요약 JSON 저장 경로(세로 러너 신호 판정용)")
    a.add_argument("--no-sheet", action="store_true")
    a.add_argument("--no-review", action="store_true",
                   help="검수표(옵션명 대조·순서·제외)를 찍지 않는다")
    a.add_argument("--sleep", type=float, default=0.5)
    a.set_defaults(func=cmd_apply)

    s = sub.add_parser("restore", help="저장 전 상태로 되돌린다(before_commit.json 필요)")
    _common(s)
    s.add_argument("--run-dir", required=True)
    s.add_argument("--ids", nargs="+", default=None, help="일부만 되돌릴 때")
    s.add_argument("--sleep", type=float, default=0.5)
    s.set_defaults(func=cmd_restore)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
