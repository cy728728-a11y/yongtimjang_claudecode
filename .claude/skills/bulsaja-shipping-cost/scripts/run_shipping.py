#!/usr/bin/env python3
"""불사자 해외배송비 측정·반영 — 스킬-계약 진입점(prep/apply). `run`은 Claude 차례다.

    prep  --ids <상품id...> --run-dir <R> [--sheet <시트id>]
          스냅샷(판매중옵션·옵션이미지·썸네일) + AI추천(shipping_cost_recommend) +
          현재 해외배송비를 모아 shipping_evidence.json 을 만든다.

    (run — Claude 차례. shipping_evidence.json 을 읽고 청구무게·포장정합을 판정해
     shipping_decision.json 을 만든다. 이 스크립트는 관여하지 않는다.)

    apply --run-dir <R> [--commit] [--sheet <시트id>]
          shipping_decision.json 을 읽어 요율표로 재검증하고, 현재 배송비와 비교해
          미리보기(항상) → --commit 이면 그 자리에서 즉시 실제 저장까지 한다.
          토큰 만료를 피하려고 preview 와 commit 을 **같은 호출 안에서 연달아** 한다
          (SKILL.md §흔한실패 11 — 확인 정보 만료 문제를 구조적으로 피한다).

시트 로그: 그룹 시트의 `06-배송비` 탭에 건건 append(원장). 매트릭스(00_진행)
`배송비` 열은 apply 가 열 통짜 1회로 갱신한다.
"""
import argparse
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

_d = SCRIPT_DIR
while _d and _d != os.path.dirname(_d):
    _lib = os.path.join(_d, "lib")
    if os.path.isdir(os.path.join(_lib, "eroomlib")):
        if _lib not in sys.path:
            sys.path.insert(0, _lib)
        break
    _d = os.path.dirname(_d)

from eroomlib import snapshot, matrix          # noqa: E402
from bulsaja_ship_mcp import ShippingMCP       # noqa: E402
import shipping_rate                            # noqa: E402

EVIDENCE = "shipping_evidence.json"
DECISION = "shipping_decision.json"
RESULT = "shipping_result.json"
SHEET_TAB = "06-배송비"
SHEET_HEADER = ("상품id", "상품", "실무게", "부피무게", "판정근거", "판정무게",
                "청구구간", "예상배송비", "기존배송비", "차액", "100kg초과",
                "포장정합", "상태", "기록일", "무게출처")


def _load(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _dump(path, obj):
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _sellable_options(rec):
    """스냅샷 옵션.판매행 중 exclude=false 만 — {이름, 판매가}."""
    opt = (rec or {}).get("옵션") or {}
    rows = opt.get("판매행") or []
    return [{"이름": r.get("text", ""), "판매가": r.get("sale_price")}
            for r in rows if not r.get("exclude")]


def _delivery_fields(raw):
    """raw workdata(mode=full) → 배송비 관련 필드만 추림(SKILL.md §흔한실패 9·12 근거).

    `data` 래핑 여부가 응답마다 다를 수 있어 두 층 모두에서 찾는다.
    """
    data = raw.get("data", raw) if isinstance(raw, dict) else {}
    delivery = data.get("uploadDelivery") or {}
    return {
        "업로드해외배송비": data.get("uploadOverseaDeliveryFee"),
        "원본해외배송비": data.get("original_deliveryFee"),
        "호환해외배송비": data.get("overseaDeliveryFee"),
        "국내기본배송비": delivery.get("delivery_fee"),
    }


def cmd_prep(args):
    mcp = ShippingMCP()
    mcp.open()
    try:
        recs, errors = snapshot.ensure(args.ids, mcp=None, log=print)
        out = []
        for pid in args.ids:
            rec = recs.get(pid)
            item = {
                "productId": pid,
                "상품명": (rec or {}).get("상품명", ""),
                "원본링크": (rec or {}).get("원본링크", ""),
                "판매중옵션": _sellable_options(rec),
                "옵션이미지": (rec or {}).get("옵션이미지", []),
                "썸네일": (rec or {}).get("썸네일", []),
            }
            try:
                item["AI추천"] = mcp.shipping_recommend(pid)
            except Exception as e:
                item["AI추천"] = None
                item["AI추천오류"] = f"{type(e).__name__}: {e}"[:200]
            try:
                raw = mcp.call_tool("bulsaja_product_workdata",
                                    {"productId": pid, "mode": "full"})
                item["현재배송비"] = _delivery_fields(raw)
            except Exception as e:
                item["현재배송비"] = None
                item["배송비조회오류"] = f"{type(e).__name__}: {e}"[:200]
            if pid in errors:
                item["조회오류"] = errors[pid]
            out.append(item)
            time.sleep(args.sleep)
    finally:
        mcp.close()

    os.makedirs(args.run_dir, exist_ok=True)
    _dump(os.path.join(args.run_dir, EVIDENCE), out)
    ok = sum(1 for o in out if o.get("AI추천") is not None or o.get("현재배송비") is not None)
    print(f"###PREP### {ok}/{len(out)} OK -> {os.path.join(args.run_dir, EVIDENCE)}")


def _sheet_log(sheet, rows):
    if not sheet or not rows:
        return 0
    from eroomlib.gsheets import ensure_tab, append_rows
    ensure_tab(sheet, SHEET_TAB, list(SHEET_HEADER))
    return append_rows(sheet, SHEET_TAB, rows)


def _process_one(mcp, d, evidence_by_id, commit):
    """decision 1건 처리 → (result_dict, sheet_row)."""
    pid = d.get("productId")
    ev = evidence_by_id.get(pid) or {}
    상품명 = ev.get("상품명", "")
    오늘 = time.strftime("%Y-%m-%d %H:%M:%S")

    if d.get("측정불가"):
        r = {"productId": pid, "상품명": 상품명, "상태": "측정불가",
             "사유": d.get("판정사유", "")}
        row = [pid, 상품명, "", "", "", "", "", "", "", "", "", "", "측정불가", 오늘, ""]
        return r, row

    try:
        q = shipping_rate.quote(d.get("실무게"), d.get("부피무게"))
    except Exception as e:
        r = {"productId": pid, "상품명": 상품명, "상태": "계산오류",
             "사유": f"{type(e).__name__}: {e}"[:200]}
        row = [pid, 상품명, d.get("실무게", ""), d.get("부피무게", ""), "", "", "",
              "", "", "", "", "", "계산오류", 오늘, d.get("무게출처", "")]
        return r, row

    포장정합 = d.get("포장정합판정", "확인불가")
    if 포장정합 == "부적합":
        r = {**q, "productId": pid, "상품명": 상품명, "상태": "반영보류(포장불일치)",
             "사유": d.get("판정사유", "")}
        row = [pid, 상품명, q["실무게"], q["부피무게"], q["판정근거"], q["판정무게"],
              q["청구구간"], q["예상배송비"], "", "", q["100kg초과"], 포장정합,
              "반영보류(포장불일치)", 오늘, d.get("무게출처", "")]
        return r, row

    # 현재 배송비를 다시 조회한다(승인 전 미리보기 시점의 최신값으로 diff를 낸다).
    try:
        raw = mcp.call_tool("bulsaja_product_workdata", {"productId": pid, "mode": "full"})
        cur_fields = _delivery_fields(raw)
        cur_fee = cur_fields.get("업로드해외배송비")
        if cur_fee in (None, 0):
            cur_fee = cur_fields.get("호환해외배송비") or 0
    except Exception as e:
        r = {**q, "productId": pid, "상품명": 상품명, "상태": "MCP오류",
             "사유": f"{type(e).__name__}: {e}"[:200]}
        row = [pid, 상품명, q["실무게"], q["부피무게"], q["판정근거"], q["판정무게"],
              q["청구구간"], q["예상배송비"], "", "", q["100kg초과"], 포장정합,
              "MCP오류", 오늘, d.get("무게출처", "")]
        return r, row

    새배송비 = q["예상배송비"]
    diff = 새배송비 - int(cur_fee or 0)
    상태 = "변경없음"
    if diff != 0:
        try:
            pv = mcp.price_preview_oversea(pid, 새배송비)
            token = pv.get("confirmationToken") or pv.get("token") or ""
            if not token:
                상태 = "미리보기실패"
            elif commit:
                cm = mcp.price_commit_oversea(pid, 새배송비, token)
                상태 = "반영완료" if cm.get("success", True) else "반영실패"
            else:
                상태 = "검토완료(미반영)"
        except Exception as e:
            상태 = "MCP오류"
            q["사유"] = f"{type(e).__name__}: {e}"[:200]

    r = {**q, "productId": pid, "상품명": 상품명, "기존배송비": int(cur_fee or 0),
         "차액": diff, "상태": 상태}
    row = [pid, 상품명, q["실무게"], q["부피무게"], q["판정근거"], q["판정무게"],
          q["청구구간"], 새배송비, int(cur_fee or 0), diff, q["100kg초과"],
          포장정합, 상태, 오늘, d.get("무게출처", "")]
    return r, row


def cmd_apply(args):
    decisions = _load(os.path.join(args.run_dir, DECISION))
    if not isinstance(decisions, list):
        raise SystemExit(f"[중단] {DECISION} 을 읽지 못했다 — run 단계가 먼저 필요하다.")
    evidence = _load(os.path.join(args.run_dir, EVIDENCE)) or []
    evidence_by_id = {e.get("productId"): e for e in evidence}

    mcp = ShippingMCP()
    mcp.open()
    results, rows = [], []
    stats = {}
    try:
        for d in decisions:
            r, row = _process_one(mcp, d, evidence_by_id, args.commit)
            results.append(r)
            rows.append(row)
            stats[r["상태"]] = stats.get(r["상태"], 0) + 1
            time.sleep(args.sleep)
    finally:
        mcp.close()

    _dump(os.path.join(args.run_dir, RESULT), results)

    if args.sheet and not args.no_sheet:
        try:
            _sheet_log(args.sheet, rows)
        except Exception as e:
            print(f"  [경고] 시트 기록 실패: {str(e)[:150]}", file=sys.stderr)

    if args.commit and args.sheet and not args.no_sheet:
        try:
            DONE_STATES = {"반영완료", "변경없음", "반영보류(포장불일치)", "측정불가"}
            m = matrix.read(args.sheet)
            vals = {}
            for r in results:
                pid = r.get("productId")
                if not pid:
                    continue
                vals[pid] = matrix.DONE if r.get("상태") in DONE_STATES else r.get("상태", "")
            n = matrix.mark_many(args.sheet, "배송비", vals, matrix=m)
            print(f"  현황판({matrix.TAB}) 배송비: {n}칸 갱신")
        except Exception as e:
            print(f"  [경고] 현황판 갱신 실패: {str(e)[:150]}", file=sys.stderr)

    print("###APPLY### " + json.dumps(stats, ensure_ascii=False)
          + f" ({'COMMIT' if args.commit else 'PREVIEW(저장안함)'})")


def main():
    ap = argparse.ArgumentParser(description="불사자 해외배송비 측정·반영")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prep", help="스냅샷+AI추천+현재배송비 → shipping_evidence.json")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--ids", nargs="+", required=True)
    p.add_argument("--sheet", default="")
    p.add_argument("--sleep", type=float, default=0.3)
    p.set_defaults(func=cmd_prep)

    a = sub.add_parser("apply", help="shipping_decision.json → 검증·미리보기·(옵션)저장")
    a.add_argument("--run-dir", required=True)
    a.add_argument("--sheet", default="")
    a.add_argument("--no-sheet", action="store_true")
    a.add_argument("--commit", action="store_true", help="실제 저장까지 한다(기본은 미리보기만)")
    a.add_argument("--sleep", type=float, default=0.3)
    a.set_defaults(func=cmd_apply)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
