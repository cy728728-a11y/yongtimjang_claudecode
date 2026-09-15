#!/usr/bin/env python3
"""쿠팡 업로드 후보 선별 파이프라인 — S0~S7 오케스트레이터.

    prep    주문시트 12탭 → 코드별 실적·배송비 원장          [읽기]
    resolve 상위 코드 → find_by_code 로 pid·불사자코드 해상   [읽기]
    build   불사자코드로 사본 병합 → 대표 1건 선정            [읽기]
    ship    실측 배송비(P75) vs 불사자 입력값 대조            [읽기]
    gate    쿠팡보정 가중마진 게이트                          [읽기]
    apply   쿠팡 마켓그룹으로 복사                            [쓰기 — --commit 필요]
    verify  복사 결과 검증(중복 0 증명·판매가 검산)           [읽기]
    sheet   원장 기록

**S6(apply) 이전은 전부 읽기 전용이라 언제 끊겨도 손실이 0이다.**
`bulsaja_market_group_copy` 에는 중복 방지 옵션이 없으므로 `copied.jsonl` 이
같은 상품을 두 번 복사하지 않게 막는 **유일한 방어선**이다 — 건건 즉시 append 한다.

사용 예:
    PYTHONPATH=.claude/lib .venv/bin/python3 run_coupang.py prep --run-dir <R>
"""
import argparse
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)


def _bootstrap():
    """워크스페이스 루트의 .claude/lib 을 import 경로에 올린다."""
    d = _HERE
    while d and d != os.path.dirname(d):
        lib = os.path.join(d, ".claude", "lib")
        if os.path.isdir(lib):
            if lib not in sys.path:
                sys.path.insert(0, lib)
            return
        d = os.path.dirname(d)


_bootstrap()

from eroomlib import gsheets, orders, snapshot          # noqa: E402
from eroomlib.config import cfg                          # noqa: E402
from eroomlib.runner import propagate                    # noqa: E402

import coupang_rules as R                                # noqa: E402

ORDERS_SHEET = "sheets.orders"
FIND_BATCH = 50          # find_by_code 최대 50개/콜
COPY_BATCH = 20          # 복사 배치 — 응답이 신 pid 를 안 줄 때 diff 매핑 오류 피해를 줄인다


# ------------------------------------------------------------------ 입출력

def _p(run_dir, name):
    return os.path.join(run_dir, name)


def _load(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _dump(path, obj):
    """원자적 쓰기 — 중간에 끊겨도 반쪽 파일이 남지 않는다."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _append_jsonl(path, rec):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _read_jsonl(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


class CoupangMCP(propagate.PropagateMCP):
    """상품 조회(ProductMCP) + 확인키 2단계 호출(PropagateMCP) 을 그대로 쓴다."""

    def find_by_code(self, codes):
        return self.call_tool("bulsaja_product_find_by_code", {"codes": list(codes)})

    def raw_workdata(self, pid):
        return self.call_tool("bulsaja_product_workdata",
                              {"productId": pid, "mode": "full"})

    def group_products(self, group_id, page_size=50, sleep=0.3):
        """그룹 전건을 **판매가까지 살려서** 가져온다.

        `snapshot.ProductMCP.collect_group` 은 productId·상품명·상태코드·잠금만 남기고
        판매가를 버린다. V4 판매가 검산에는 그 값이 꼭 필요해서 따로 둔다.
        """
        out, seen, page = [], set(), 1
        while True:
            r = self.call_tool("bulsaja_market_group_products",
                               {"groupId": int(group_id), "page": page,
                                "pageSize": page_size})
            items = r.get("항목") or []
            if not items:
                break
            for it in items:
                pid = it.get("productId")
                if pid and pid not in seen:
                    seen.add(pid)
                    out.append(it)
            if not r.get("더있음"):
                break
            page += 1
            time.sleep(sleep)
        return out

    def copy_to_group(self, product_ids, group_id):
        return self._confirmed_call("bulsaja_market_group_copy",
                                    {"productIds": list(product_ids),
                                     "marketGroupId": int(group_id)})


# ------------------------------------------------------------------ S0 · S1

def cmd_prep(args):
    sheet_id = args.sheet_id or cfg(ORDERS_SHEET, required=True)
    print(f"[prep] 주문시트 {sheet_id}")
    tabs = orders.month_tabs(sheet_id)
    print(f"  월별 탭 {len(tabs)}개: {tabs[0]} ~ {tabs[-1]}")

    stat, skipped = orders.load(sheet_id, tabs, log=print)
    if skipped:
        print(f"  ⚠️ 건너뛴 탭 {len(skipped)}개 (판매자상품코드 열 없음): "
              f"{', '.join(sorted(skipped))}")

    _dump(_p(args.run_dir, "sales.json"),
          {"시트": sheet_id, "탭": tabs, "건너뜀": skipped, "실적": stat})

    ranked = sorted(stat.values(), key=lambda r: (-r["주문수"], -r["매출"]))
    _dump(_p(args.run_dir, "ranked.json"),
          [{"판매자상품코드": r["판매자상품코드"], "주문수": r["주문수"],
            "매출": r["매출"], "가중마진": r["가중마진"], "상품명": r["상품명"]}
           for r in ranked])

    print(f"  고유 코드 {len(stat):,}개 / 총 주문 "
          f"{sum(r['주문수'] for r in stat.values()):,}건")
    for thr in (2, 3, 4, 5):
        print(f"    {thr}회 이상: {sum(1 for r in stat.values() if r['주문수'] >= thr):,}개")
    return 0


# ------------------------------------------------------------------ S2

def cmd_resolve(args):
    sales = (_load(_p(args.run_dir, "sales.json")) or {}).get("실적") or {}
    if not sales:
        print("[resolve] sales.json 이 없다. prep 먼저 돌려라.", file=sys.stderr)
        return 2

    targets = [c for c, r in sales.items() if r["주문수"] >= args.min_orders]
    targets.sort(key=lambda c: -sales[c]["주문수"])
    print(f"[resolve] 주문 {args.min_orders}회 이상 {len(targets)}개")

    path = _p(args.run_dir, "resolved.json")
    resolved = _load(path, {}) or {}
    todo = [c for c in targets if c not in resolved]
    print(f"  이미 해상 {len(resolved)} / 새로 조회 {len(todo)}")

    if todo:
        mcp = CoupangMCP()
        mcp.open()
        try:
            for i in range(0, len(todo), FIND_BATCH):
                chunk = todo[i:i + FIND_BATCH]
                r = mcp.find_by_code(chunk)
                for it in (r.get("항목") or []):
                    code = str(it.get("판매자상품코드") or "").strip()
                    if code in sales:
                        resolved[code] = it
                _dump(path, resolved)
                print(f"  {i + len(chunk)}/{len(todo)} (누적 해상 {len(resolved)})")
                time.sleep(args.sleep)
        finally:
            mcp.close()

    missing = [c for c in targets if c not in resolved]
    _dump(_p(args.run_dir, "unresolved.json"), missing)
    locked = sum(1 for c in targets if resolved.get(c, {}).get("잠금"))
    print(f"  해상 {len(targets) - len(missing)}/{len(targets)} · 조회 실패 {len(missing)}")
    print(f"  그중 잠금 상태: {locked}개")
    return 0


# ------------------------------------------------------------------ S3

def cmd_build(args):
    sales = (_load(_p(args.run_dir, "sales.json")) or {}).get("실적") or {}
    resolved = _load(_p(args.run_dir, "resolved.json"), {}) or {}
    if not resolved:
        print("[build] resolved.json 이 없다. resolve 먼저.", file=sys.stderr)
        return 2

    groups = R.group_by_bulsaja_code(resolved, sales)
    _dump(_p(args.run_dir, "groups.json"), groups)

    exclude = {cfg("coupang.group_name", "")}
    reps = {}
    dropped = {}
    for key, g in groups.items():
        rep = R.choose_top_seller(g["사본"], exclude_groups=exclude)
        if rep is None:
            dropped[key] = "정상 상태 사본 없음"
            continue
        reps[key] = {
            "불사자코드": key,
            "대표pid": rep["productId"],
            "판매자상품코드": rep["판매자상품코드"],
            "상품명": (sales.get(rep["판매자상품코드"]) or {}).get("상품명", ""),
            "그룹명": rep.get("그룹명"),
            "잠금": rep.get("잠금"),
            "상태": rep.get("상태"),
            "판매가": rep.get("판매가"),
            "사본수": len(g["사본"]),
            "사본pid": [c["productId"] for c in g["사본"]],
            "합산주문수": g["합산주문수"],
            "합산매출": g["합산매출"],
        }
    _dump(_p(args.run_dir, "reps.json"), reps)
    _dump(_p(args.run_dir, "build_dropped.json"), dropped)

    merged = len(resolved) - len(reps)
    multi = sum(1 for r in reps.values() if r["사본수"] > 1)
    print(f"[build] 조회 {len(resolved)}개 → 원본 {len(reps)}개 "
          f"(중복 병합으로 {merged}개 감소)")
    print(f"  사본 2개 이상인 원본: {multi}개 · 대표 없음(상태 이상): {len(dropped)}개")
    locked = sum(1 for r in reps.values() if r["잠금"])
    print(f"  대표가 잠금(판매 실적으로 지켜둔) 상태: {locked}개")
    return 0


# ------------------------------------------------------------------ S4

def cmd_ship(args):
    sales = (_load(_p(args.run_dir, "sales.json")) or {}).get("실적") or {}
    reps = _load(_p(args.run_dir, "reps.json"), {}) or {}
    if not reps:
        print("[ship] reps.json 이 없다. build 먼저.", file=sys.stderr)
        return 2

    pids = [r["대표pid"] for r in reps.values()]
    print(f"[ship] 대표 {len(pids)}건 — 스냅샷 확보(캐시 적중은 조회 0)")
    mcp = CoupangMCP()
    mcp.open()
    try:
        snaps, snap_err = snapshot.ensure(pids, mcp=mcp, log=print)

        path = _p(args.run_dir, "ship_diff.json")
        diffs = _load(path, {}) or {}
        todo = [r for r in reps.values() if r["대표pid"] not in diffs]
        print(f"  이미 대조 {len(diffs)} / 새로 조회 {len(todo)}")

        for n, rep in enumerate(todo, 1):
            pid = rep["대표pid"]
            code = rep["판매자상품코드"]
            st = sales.get(code) or {}
            try:
                raw = mcp.raw_workdata(pid)
                data = raw.get("data", raw) if isinstance(raw, dict) else {}
                현재 = data.get("uploadOverseaDeliveryFee")
            except Exception as e:
                현재 = None
                print(f"  ! {pid} workdata 실패: {str(e)[:120]}")
            d = R.shipping_diff(st.get("배송비P75"), 현재, args.tolerance)
            d.update({
                "대표pid": pid, "판매자상품코드": code,
                "상품명": st.get("상품명", ""),
                "기록건수": len(st.get("배송비단위") or []),
                "중앙값": st.get("배송비중앙"),
                "편차%": st.get("배송비편차"),
                "카테고리": (snaps.get(pid) or {}).get("기존카테고리", ""),
                "타오바오상품번호": (snaps.get(pid) or {}).get("타오바오상품번호", ""),
            })
            diffs[pid] = d
            _dump(path, diffs)
            if n % 10 == 0 or n == len(todo):
                print(f"  {n}/{len(todo)}")
            time.sleep(args.sleep)
    finally:
        mcp.close()

    need = [d for d in diffs.values() if d.get("교정필요")]
    up = [d for d in need if d.get("방향") == "인상"]
    print(f"\n[ship] 교정 필요 {len(need)}/{len(diffs)}건 (인상 {len(up)} · "
          f"인하 {len(need) - len(up)})")
    if up:
        worst = sorted(up, key=lambda d: -(d.get("차액") or 0))[:10]
        print("  과소책정 상위 10건 (실측P75 − 현재 = 차액):")
        for d in worst:
            print(f"    {d['판매자상품코드']}  {d['실측P75']:>8,} − "
                  f"{(d['현재'] or 0):>8,} = {d['차액']:>8,}  {d['상품명'][:26]}")
    # **인상만 반영 대상이다.** 실측 배송비는 '실제 팔린 옵션'의 것이라, 안 팔린
    # 무거운 옵션이 남아 있으면 인하는 그 옵션을 역마진으로 만든다. 인하 후보는
    # 목록으로만 남기고 사람이 옵션 구성을 보고 판단한다.
    ids = [d["대표pid"] for d in up]
    _dump(_p(args.run_dir, "ship_fix_ids.json"), ids)
    _dump(_p(args.run_dir, "ship_overpriced.json"),
          sorted((d for d in need if d.get("방향") == "인하"),
                 key=lambda d: d.get("차액") or 0))
    print(f"\n  → 인상(과소책정) {len(ids)}건을 ship_fix_ids.json 에 적었다.")
    print(f"     인하 후보 {len(need) - len(up)}건은 ship_overpriced.json 에만 남긴다 —"
          f" 자동 반영하지 않는다(팔린 옵션 기준이라 무거운 옵션을 놓친다).")
    print("     반영은 bulsaja-shipping-cost 스킬이 한다(별도 최종 동의 필요):")
    print("       run_shipping.py prep --run-dir <R> --ids $(...)")
    return 0


# ------------------------------------------------------------------ S5

def cmd_gate(args):
    sales = (_load(_p(args.run_dir, "sales.json")) or {}).get("실적") or {}
    reps = _load(_p(args.run_dir, "reps.json"), {}) or {}
    diffs = _load(_p(args.run_dir, "ship_diff.json"), {}) or {}
    if not reps:
        print("[gate] reps.json 이 없다. build 먼저.", file=sys.stderr)
        return 2

    min_margin = args.min_margin if args.min_margin is not None else cfg("coupang.min_margin", 15.0)
    min_orders = args.min_orders if args.min_orders is not None else cfg("coupang.min_orders", 3)

    # **실물 대조 (3중 방어의 3층).** `copied.jsonl` 은 run-dir 안에만 있어서,
    # 새 run-dir 로 돌리면 방어선이 사라진다. 복사본은 불사자코드를 **승계**하지만
    # 목록 조회에는 그 필드가 없으므로, 스냅샷의 타오바오상품번호로 대조한다.
    # (2026-09-13 시험 복사로 승계 확인: 원본·복사본 모두 74FOyS2vS6DZg9NggZ8Ty)
    already = set()
    if not args.skip_group_check:
        gid = int(cfg("coupang.group_id", required=True))
        mcp = CoupangMCP()
        mcp.open()
        try:
            items = mcp.collect_group(gid)
            snaps, _ = snapshot.ensure([i["productId"] for i in items], mcp=mcp, log=None)
            already = {str((snaps.get(i["productId"]) or {}).get("타오바오상품번호") or "")
                       for i in items}
            already.discard("")
        finally:
            mcp.close()
        print(f"[gate] 쿠팡 그룹 기존 {len(items)}건 → 원본 {len(already)}종 (재복사 제외 대상)")

    passed, rejected = [], []
    for key, rep in reps.items():
        code = rep["판매자상품코드"]
        st = dict(sales.get(code) or {})
        st["주문수"] = rep["합산주문수"] or st.get("주문수", 0)
        d = diffs.get(rep["대표pid"]) or {}
        st["카테고리"] = d.get("카테고리", "")

        fee = R.coupang_fee(st["카테고리"])
        보정 = R.adjust_margin(st.get("가중마진"), fee, st.get("평균수수료율"))
        ok, why = R.passes(st, min_margin=min_margin, min_orders=min_orders,
                           category_fee=fee)

        row = {
            "불사자코드": key, "대표pid": rep["대표pid"], "판매자상품코드": code,
            "상품명": rep["상품명"], "그룹명": rep["그룹명"], "잠금": rep["잠금"],
            "사본수": rep["사본수"], "사본pid": rep["사본pid"],
            "합산주문수": rep["합산주문수"], "합산매출": rep["합산매출"],
            "판매가": rep.get("판매가"),
            "가중마진": st.get("가중마진"), "최소마진": st.get("최소마진"),
            "적자건수": st.get("적자건수"), "유효행수": st.get("유효행수"),
            "카테고리": st["카테고리"], "쿠팡수수료율": fee, "쿠팡보정마진": 보정,
            "배송비P75": st.get("배송비P75"), "배송비편차": st.get("배송비편차"),
            # **막는 건 과소책정(인상)뿐이다.** 인하는 복사를 막지 않는다 —
            # 실측은 '실제 팔린 옵션'의 배송비라, 안 팔린 무거운 옵션이 있으면
            # 내리는 게 오히려 위험하다(그 옵션이 쿠팡에서 팔리면 역마진).
            "배송비과소": bool(d.get("교정필요")) and d.get("방향") in ("인상", "미상"),
            "배송비방향": d.get("방향", ""),
            "배송비차액": d.get("차액"),
            "타오바오상품번호": d.get("타오바오상품번호", ""),
            "사유": why,
        }
        # 이미 쿠팡에 올라간 상품은 제외 — 중복 방어 2층.
        마켓 = rep.get("업로드된마켓") or []
        if any("쿠팡" in str(m) for m in (마켓 if isinstance(마켓, list) else [마켓])):
            ok, row["사유"] = False, "기업로드(쿠팡)"
        elif row["타오바오상품번호"] and row["타오바오상품번호"] in already:
            ok, row["사유"] = False, "쿠팡그룹에이미있음"
        (passed if ok else rejected).append(row)

    passed.sort(key=lambda r: (-(r["합산주문수"] or 0), -(r["쿠팡보정마진"] or 0)))
    if args.limit:
        over = passed[args.limit:]
        for r in over:
            r["사유"] = f"상한초과(상위 {args.limit}건 밖)"
        rejected.extend(over)
        passed = passed[:args.limit]

    _dump(_p(args.run_dir, "candidates.json"), passed)
    _dump(_p(args.run_dir, "rejected.json"), rejected)

    print(f"[gate] 기준: 주문 {min_orders}회 이상 AND 쿠팡보정마진 {min_margin}% 이상")
    print(f"  통과 {len(passed)}건 / 탈락 {len(rejected)}건")
    by = {}
    for r in rejected:
        k = r["사유"].split("(")[0]
        by[k] = by.get(k, 0) + 1
    for k, v in sorted(by.items(), key=lambda kv: -kv[1]):
        print(f"    탈락 {k}: {v}건")
    under = sum(1 for r in passed if r["배송비과소"])
    over = sum(1 for r in passed if r["배송비방향"] == "인하")
    if under:
        print(f"  · 통과분 중 배송비 과소책정 {under}건 — 원장 `배송비` 탭에 측정값이 있다"
              f"(쿠팡 등록 전 직접 확인 대상)")
    if over:
        print(f"  · 통과분 중 배송비 과다책정 {over}건 — 복사는 막지 않는다(손해가 아니라 "
              f"가격이 비싼 것). 다만 실측은 '팔린 옵션' 기준이라 자동 인하는 위험하다.")
    if passed:
        print("\n  통과 상위 10건:")
        for r in passed[:10]:
            print(f"    주문{r['합산주문수']:>3} 보정마진{(r['쿠팡보정마진'] or 0):>6.1f}% "
                  f"사본{r['사본수']:>2} {r['상품명'][:30]}")
    return 0


# ------------------------------------------------------------------ S6

def cmd_apply(args):
    cands = _load(_p(args.run_dir, "candidates.json"), []) or []
    if not cands:
        print("[apply] candidates.json 이 비었다. gate 먼저.", file=sys.stderr)
        return 2

    gid = int(cfg("coupang.group_id", required=True))
    done = {r["원본pid"] for r in _read_jsonl(_p(args.run_dir, "copied.jsonl"))}
    todo = [c for c in cands if c["대표pid"] not in done]

    if args.limit:
        # 시험 복사용. 후보는 이미 (합산주문수, 보정마진) 내림차순이라 상위부터 집힌다.
        todo = todo[:args.limit]

    # **이번에 실제로 복사할 것만** 보고 판정한다. 후보 전체를 보면 안 건드릴 상품
    # 때문에 막힌다(시험 복사 1건이 남의 사유로 중단되는 일).
    blocked = [c for c in todo if c.get("배송비과소")]

    print(f"[apply] 대상 {len(todo)}건 (이미 복사 {len(done)}건 제외) → 그룹 {gid}")
    if blocked:
        print(f"  · 배송비 과소책정 {len(blocked)}건 — 복사는 진행한다. "
              f"쿠팡 등록 전에 직접 확인할 목록:")
        for c in blocked:
            print(f"      {c['판매자상품코드']} 차액 {c.get('배송비차액') or 0:>8,}원 "
                  f"{c['상품명'][:30]}")

    # 미리보기는 읽기 전용이라 막지 않는다. **실제 복사만** 막는다.
    if not args.commit:
        print("  ** 미리보기 — 실제 복사 안 함. 진행하려면 --commit **")
        for c in todo[:20]:
            print(f"    {c['판매자상품코드']} 주문{c['합산주문수']:>3} "
                  f"보정마진{(c['쿠팡보정마진'] or 0):>6.1f}% {c['상품명'][:34]}")
        if len(todo) > 20:
            print(f"    … 외 {len(todo) - 20}건")
        return 0

    # **배송비는 복사를 막지 않는다** (2026-09-13 용팀장 지시): 쿠팡 상품은 배송비를
    # 건건 직접 확인하므로, 대략적인 값이 들어 있으면 된다. 사람이 매 건 보는 통제가
    # 자동 판정보다 정확하다. 측정값은 원장 `배송비` 탭에 참고용으로 남는다.
    # 막고 싶으면 --strict-shipping.
    if blocked and args.strict_shipping:
        print(f"\n[apply] 중단(--strict-shipping) — 배송비 과소책정 {len(blocked)}건.")
        return 3

    mcp = CoupangMCP()
    mcp.open()
    try:
        before = {p["productId"] for p in mcp.collect_group(gid)}
        _dump(_p(args.run_dir, "before_copy.json"), sorted(before))
        print(f"  복사 전 쿠팡 그룹 상품수: {len(before)}")

        for i in range(0, len(todo), args.batch):
            chunk = todo[i:i + args.batch]
            pids = [c["대표pid"] for c in chunk]
            mcp.copy_to_group(pids, gid)
            time.sleep(args.sleep)
            after = {p["productId"] for p in mcp.collect_group(gid)}
            new = sorted(after - before)
            if len(new) != len(chunk):
                print(f"  ⚠️ 배치 {i // args.batch + 1}: 요청 {len(chunk)}건인데 "
                      f"신규 {len(new)}건 — 수동 확인 필요")
            for c, npid in zip(chunk, new + [None] * len(chunk)):
                _append_jsonl(_p(args.run_dir, "copied.jsonl"), {
                    "원본pid": c["대표pid"], "판매자상품코드": c["판매자상품코드"],
                    "불사자코드": c["불사자코드"], "신pid": npid,
                    "원본판매가": c.get("판매가"), "상품명": c["상품명"],
                    "타오바오상품번호": c.get("타오바오상품번호", ""),
                    "복사일": time.strftime("%Y-%m-%d %H:%M:%S"),
                })
            before = after
            print(f"  {min(i + args.batch, len(todo))}/{len(todo)} "
                  f"(그룹 누적 {len(after)})")
    finally:
        mcp.close()
    print("  복사 완료. 다음: verify")
    return 0


# ------------------------------------------------------------------ S7

def cmd_verify(args):
    copied = _read_jsonl(_p(args.run_dir, "copied.jsonl"))
    if not copied:
        print("[verify] copied.jsonl 이 비었다.", file=sys.stderr)
        return 2
    gid = int(cfg("coupang.group_id", required=True))

    mcp = CoupangMCP()
    mcp.open()
    try:
        items = mcp.group_products(gid)
        pids = [p["productId"] for p in items]
        print(f"[verify] 쿠팡 그룹 전건 {len(pids)}개")

        snaps, _ = snapshot.ensure(pids, mcp=mcp, log=None)
        nos = [str((snaps.get(p) or {}).get("타오바오상품번호") or "") for p in pids]
        real = [n for n in nos if n]
        dup_ok = len(set(real)) == len(real)
        print(f"  V3 중복 0 증명: 타오바오번호 {len(set(real))}종 / 상품 {len(real)}건 "
              f"→ {'통과' if dup_ok else '❌ 중복 있음'}")
        dups = {}
        if not dup_ok:
            for p, n in zip(pids, nos):
                if n:
                    dups.setdefault(n, []).append(p)
            dups = {k: v for k, v in dups.items() if len(v) > 1}
            for n, ps in list(dups.items())[:10]:
                print(f"    중복 {n}: {ps}")

        # V4 판매가 검산 — 복사 후 판매가가 게이트 전제와 어긋나는지.
        if args.only == "dup":
            _dump(_p(args.run_dir, "verified.json"),
                  {"중복0": dup_ok, "중복": dups, "그룹상품수": len(pids)})
            return 0 if dup_ok else 4

        # 판매가는 group_products 응답에 이미 실려 온다 — 추가 조회가 필요 없다.
        prices = {}
        for it in items:
            prices[it["productId"]] = it.get("판매가")
        reps = _load(_p(args.run_dir, "reps.json"), {}) or {}
        orig_price = {r["대표pid"]: r.get("판매가") for r in reps.values()}
        checked = []
        for c in copied:
            if not c.get("신pid"):
                continue
            before_p = c.get("원본판매가") or orig_price.get(c["원본pid"])
            after_p = prices.get(c["신pid"])
            checked.append({
                "원본pid": c["원본pid"], "신pid": c["신pid"],
                "원본판매가": before_p, "복사후판매가": after_p,
                "동일": bool(before_p) and before_p == after_p,
                "상품명": c.get("상품명", ""),
            })
        diff_cnt = sum(1 for c in checked if not c["동일"])
        print(f"  V4 판매가 검산: 동일 {len(checked) - diff_cnt} / 어긋남 {diff_cnt}")
        if diff_cnt:
            print("     ⚠️ 판매가가 원본과 다르다 — 쿠팡 그룹 가격설정이 게이트 전제와 "
                  "어긋난다. 업로드 전에 배수를 다시 재라.")
        _dump(_p(args.run_dir, "verified.json"),
              {"중복0": dup_ok, "중복": dups, "판매가": checked,
               "그룹상품수": len(pids)})
        if checked[:5]:
            print("  표본:")
            for c in checked[:5]:
                print(f"    원본 {c['원본판매가']} → 복사후 {c['복사후판매가']}  "
                      f"{c['상품명'][:28]}")
    finally:
        mcp.close()
    return 0


# ------------------------------------------------------------------ 원장

LEDGER_TABS = {
    "실적": ["판매자상품코드", "상품명", "주문수", "수량", "매출", "유효행수",
           "가중마진", "최소마진", "적자건수", "평균수수료율", "마켓그룹",
           "최초주문일", "최근주문일"],
    "배송비": ["판매자상품코드", "대표pid", "상품명", "기록건수", "중앙값", "P75(채택)",
            "편차%", "불사자현재", "차액", "교정필요", "방향"],
    "후보": ["대표pid", "판매자상품코드", "불사자코드", "사본수", "상품명", "그룹명",
           "합산주문수", "합산매출", "가중마진", "쿠팡수수료율", "쿠팡보정마진",
           "카테고리", "메인키워드", "잠금", "배송비방향", "배송비차액", "배송비과소",
           "게이트", "사유"],
    "복사": ["원본pid", "신pid", "불사자코드", "판매자상품코드", "상품명",
           "메인키워드", "확신도", "카테고리", "모델명", "추천상품명(쿠팡)",
           "원본판매가", "복사후판매가", "복사일", "최종상품명(용팀장)"],
    "제외": ["판매자상품코드", "상품명", "합산주문수", "가중마진", "쿠팡보정마진", "사유"],
}


def _sheet_models(sid, tab="복사"):
    """원장 `복사` 탭에서 `{원본pid: 모델명}` 을 읽는다 — 모델명 정본.

    run-dir 은 회차마다 새로 만들어지므로 과거 회차의 모델명은 로컬에 없다.
    시트만이 회차를 넘어 남는 기록이라 여기서 읽는다.
    """
    try:
        hdr = (gsheets.sheets_get(sid, f"'{tab}'!A1:Z1") or [[]])[0]
        if "모델명" not in hdr:
            return {}
        mi, pi = hdr.index("모델명"), hdr.index("원본pid")
        out = {}
        for r in (gsheets.sheets_get(sid, f"'{tab}'!A2:Z5000") or []):
            pid = (r[pi] if len(r) > pi else "").strip()
            m = (r[mi] if len(r) > mi else "").strip()
            if pid and m:
                out[pid] = m
        return out
    except Exception as e:  # noqa: BLE001
        print(f"  [경고] 기존 모델명 읽기 실패 — 중복 검사 못 함: {str(e)[:90]}")
        return None


def _report_models(verdict):
    """모델명 판정 출력. 통과면 한 줄, 아니면 사유별로."""
    if verdict["통과"]:
        print("  모델명 검사: 중복·형식 문제 없음")
        return
    if verdict["누락"]:
        print(f"  ❌ 모델명 누락 {len(verdict['누락'])}건: {verdict['누락'][:6]}")
    if verdict["형식위반"]:
        print(f"  ❌ 형식 위반(ON-XXX-000 이어야 한다): {verdict['형식위반'][:6]}")
    for m, ps in list(verdict["런내중복"].items())[:6]:
        print(f"  ❌ 이번 회차 안에서 중복 — {m}: {ps}")
    for m, d in list(verdict["기존충돌"].items())[:6]:
        print(f"  ❌ 기존 상품과 충돌 — {m}: 새 {d['새상품']} vs 기존 {d['기존상품']}")


def cmd_models(args):
    """모델명 중복·형식 검사(읽기 전용). 시트 기록 전에 단독으로 돌려볼 수 있다."""
    sid = args.sheet or cfg("sheets.coupang")
    models = _load(_p(args.run_dir, "models.json"), {}) or {}
    if not models:
        print("[models] models.json 이 없다.", file=sys.stderr)
        return 2
    existing = _sheet_models(sid) if sid else {}
    v = R.model_conflicts(models, existing or {})
    print(f"[models] 이번 회차 {len(models)}건 · 시트 기존 "
          f"{len(existing or {})}건과 대조")
    _report_models(v)
    if not v["통과"] and args.suggest:
        taken = R.taken_models(models, existing or {})
        for m in list(v["런내중복"]) + list(v["기존충돌"]):
            parts = m.split("-")
            if len(parts) == 3:
                try:
                    print(f"     {m} → 빈 번호 제안: "
                          f"{R.next_model(parts[1], parts[2][-1], taken)}")
                except ValueError as e:
                    print(f"     {m}: {e}")
    return 0 if v["통과"] else 5


def cmd_sheet(args):
    sid = args.sheet or cfg("sheets.coupang")
    if not sid:
        print("[sheet] 원장 시트 ID 가 없다. workspace.toml [sheets] coupang 에 채우거나 "
              "--sheet 로 넘겨라.", file=sys.stderr)
        return 2

    sales = (_load(_p(args.run_dir, "sales.json")) or {}).get("실적") or {}
    diffs = _load(_p(args.run_dir, "ship_diff.json"), {}) or {}
    cands = _load(_p(args.run_dir, "candidates.json"), []) or []
    rej = _load(_p(args.run_dir, "rejected.json"), []) or []
    copied = _read_jsonl(_p(args.run_dir, "copied.jsonl"))
    ver = _load(_p(args.run_dir, "verified.json"), {}) or {}
    price = {c["신pid"]: c.get("복사후판매가") for c in (ver.get("판매가") or [])}
    # 카테고리교정 때 실제로 조회에 넣은 키워드(그룹 시트 `시트1` E열 "검색어(사용)").
    # 그 키워드가 카테고리를 결정했으므로 상품명·상위노출 작업의 출발점이 된다.
    kw = _load(_p(args.run_dir, "keywords.json"), {}) or {}
    # 쿠팡 상품명 = 후킹 + 후킹 + 메인키워드 + 서브키워드 (2026-09-13 용팀장 지시).
    # 후킹은 클릭을 부르는 수식어, 서브키워드는 색상·규격 같은 간단한 특징.
    names = _load(_p(args.run_dir, "product_names.json"), {}) or {}
    # 모델명 — 실제 제품에는 모델명이 없어 임의로 부여한다(2026-09-15 용팀장 지시).
    # `ON`(오네이) + 품목 약어 3자 + 규격 3자. 상품마다 고유해야 한다.
    models = _load(_p(args.run_dir, "models.json"), {}) or {}

    # **기록 전에 모델명을 검사한다.** 같은 모델명을 다른 상품에 쓰면 쿠팡이 동일상품으로
    # 묶을 수 있다. 시트가 회차를 넘는 정본이라 거기서 기존 코드를 읽어 대조한다.
    if models:
        existing = _sheet_models(sid)
        if existing is None:
            print("  [경고] 기존 모델명을 못 읽었다 — 중복 검사 없이 진행한다")
        else:
            v = R.model_conflicts(models, existing)
            _report_models(v)
            if not v["통과"] and not args.allow_model_conflict:
                print("  중단 — 모델명을 고치고 다시 돌려라 "
                      "(알고도 진행하려면 --allow-model-conflict, "
                      "빈 번호 제안은 `models --suggest`)", file=sys.stderr)
                return 5

    # **사람이 손으로 적은 열은 보존한다.** `sheet` 는 전체 덮어쓰기라, 지키지 않으면
    # 용팀장이 직접 적은 최종상품명이 다음 실행에서 통째로 날아간다.
    manual = {}
    try:
        cur = gsheets.sheets_get(sid, f"'복사'!A2:Z3000") or []
        hdr = (gsheets.sheets_get(sid, f"'복사'!A1:Z1") or [[]])[0]
        if "최종상품명(용팀장)" in hdr:
            ci = hdr.index("최종상품명(용팀장)")
            for r in cur:
                pid = (r[0] if r else "").strip()
                val = (r[ci] if len(r) > ci else "").strip()
                if pid and val:
                    manual[pid] = val
        if manual:
            print(f"  손으로 적은 최종상품명 {len(manual)}건 보존")
    except Exception as e:
        print(f"  [경고] 기존 최종상품명 읽기 실패 — 보존 못 함: {str(e)[:90]}")

    def num(v, nd=1):
        return "" if v is None else round(float(v), nd)

    only = set(c["판매자상품코드"] for c in cands) | set(r["판매자상품코드"] for r in rej)
    blocks = {
        "실적": [[r["판매자상품코드"], r["상품명"], r["주문수"], r["수량"],
                num(r["매출"], 0), r["유효행수"], num(r["가중마진"]),
                num(r["최소마진"]), r["적자건수"], num(r.get("평균수수료율")),
                ",".join(f"{k}:{v}" for k, v in sorted(r["마켓그룹"].items())),
                r["최초주문일"], r["최근주문일"]]
               for c, r in sorted(sales.items(), key=lambda kv: -kv[1]["주문수"])
               if c in only],
        "배송비": [[d["판매자상품코드"], d["대표pid"], d.get("상품명", ""),
                 d.get("기록건수"), num(d.get("중앙값"), 0), num(d.get("실측P75"), 0),
                 num(d.get("편차%"), 0), num(d.get("현재"), 0), num(d.get("차액"), 0),
                 "Y" if d.get("교정필요") else "", d.get("방향", "")]
                for d in diffs.values()],
        "후보": [[c["대표pid"], c["판매자상품코드"], c["불사자코드"], c["사본수"],
                c["상품명"], c["그룹명"] or "", c["합산주문수"], num(c["합산매출"], 0),
                num(c["가중마진"]), num(c["쿠팡수수료율"]), num(c["쿠팡보정마진"]),
                c["카테고리"], (kw.get(c["대표pid"]) or {}).get("검색어", ""),
                "Y" if c["잠금"] else "", c.get("배송비방향", ""),
                c.get("배송비차액") or "", "Y" if c["배송비과소"] else "",
                "통과", c["사유"]]
               for c in cands],
        "복사": [[c["원본pid"], c.get("신pid") or "", c["불사자코드"],
                c["판매자상품코드"], c["상품명"],
                (kw.get(c["원본pid"]) or {}).get("검색어", ""),
                (kw.get(c["원본pid"]) or {}).get("확신도", ""),
                (kw.get(c["원본pid"]) or {}).get("카테고리", ""),
                models.get(c["원본pid"], ""),
                names.get(c["원본pid"], ""),
                c.get("원본판매가") or "",
                price.get(c.get("신pid")) or "", c["복사일"],
                manual.get(c["원본pid"], "")]
               for c in copied],
        "제외": [[r["판매자상품코드"], r["상품명"], r["합산주문수"],
                num(r["가중마진"]), num(r["쿠팡보정마진"]), r["사유"]]
               for r in rej],
    }

    # **덮어쓰기다, append 가 아니다.** 이 탭들은 전부 run-dir 파일에서 매번 전체를
    # 다시 뽑는 산출물이라, append 하면 재실행마다 행이 배로 늘어난다(실측: 2회
    # 실행으로 152 → 304행). 건건 즉시 기록의 정본은 `copied.jsonl` 쪽이다.
    for tab, header in LEDGER_TABS.items():
        rows = blocks.get(tab) or []
        if not rows:
            continue
        gsheets.ensure_tab(sid, tab, header)
        # **헤더도 매번 다시 쓴다.** `ensure_tab` 은 탭을 새로 만들 때만 헤더를 쓰므로,
        # 열을 추가하면 데이터는 새 구조인데 머리글은 옛 것이 남아 라벨이 어긋난다.
        gsheets.sheets_update(sid, f"'{tab}'!A1", [list(header)])
        gsheets.sheets_clear(sid, f"'{tab}'!A2:ZZ")
        # chunk_by_size 는 (시작인덱스, 행들) 쌍을 내준다 — 시작 인덱스로 행 위치를 잡는다.
        for start, chunk in gsheets.chunk_by_size(rows):
            gsheets.sheets_update(sid, f"'{tab}'!A{start + 2}", chunk,
                                  value_input="USER_ENTERED")
        print(f"  {tab}: {len(rows)}행 기록(덮어쓰기)")
    print(f"[sheet] 완료 → https://docs.google.com/spreadsheets/d/{sid}/edit")
    return 0


# ------------------------------------------------------------------ CLI

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--run-dir", required=True)
        p.add_argument("--sleep", type=float, default=0.3)
        return p

    p = common(sub.add_parser("prep", help="S0·S1 주문시트 집계 → 실적·배송비 원장"))
    p.add_argument("--sheet-id", default="")
    p.set_defaults(fn=cmd_prep)

    p = common(sub.add_parser("resolve", help="S2 상위 코드 → 불사자 조회"))
    p.add_argument("--min-orders", type=int, default=3)
    p.set_defaults(fn=cmd_resolve)

    p = common(sub.add_parser("build", help="S3 불사자코드 병합 → 대표 선정"))
    p.set_defaults(fn=cmd_build)

    p = common(sub.add_parser("ship", help="S4 실측 배송비 vs 불사자 입력값 대조"))
    p.add_argument("--tolerance", type=float, default=10.0)
    p.set_defaults(fn=cmd_ship)

    p = common(sub.add_parser("gate", help="S5 쿠팡보정 마진 게이트"))
    p.add_argument("--min-margin", type=float, default=None)
    p.add_argument("--min-orders", type=int, default=None)
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--skip-group-check", action="store_true",
                   help="쿠팡 그룹 실물 대조를 건너뛴다(조회 절약용, 재복사 위험)")
    p.set_defaults(fn=cmd_gate)

    p = common(sub.add_parser("apply", help="S6 쿠팡 그룹으로 복사 (쓰기)"))
    p.add_argument("--commit", action="store_true", help="실제 복사. 없으면 미리보기")
    p.add_argument("--batch", type=int, default=COPY_BATCH)
    p.add_argument("--strict-shipping", action="store_true",
                   help="배송비 과소책정 후보가 있으면 복사를 중단한다(기본은 경고만)")
    p.add_argument("--limit", type=int, default=0,
                   help="상위 N건만 복사(0=전부). 시험 복사에 쓴다")
    p.set_defaults(fn=cmd_apply)

    p = common(sub.add_parser("verify", help="S7 중복 0 증명 · 판매가 검산"))
    p.add_argument("--only", choices=["dup", "all"], default="all",
                   help="dup = 중복 0 증명만. 판매가 검산은 사람이 따로 볼 때 쓴다")
    p.set_defaults(fn=cmd_verify)

    p = common(sub.add_parser("sheet", help="원장 기록"))
    p.add_argument("--sheet", default="")
    p.add_argument("--allow-model-conflict", action="store_true",
                   help="모델명 충돌이 있어도 기록한다(기본은 중단)")
    p.set_defaults(fn=cmd_sheet)

    p = common(sub.add_parser("models", help="모델명 중복·형식 검사(읽기 전용)"))
    p.add_argument("--sheet", default="")
    p.add_argument("--suggest", action="store_true", help="빈 번호를 제안한다")
    p.set_defaults(fn=cmd_models)

    args = ap.parse_args()
    os.makedirs(args.run_dir, exist_ok=True)
    return args.fn(args)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main() or 0)
