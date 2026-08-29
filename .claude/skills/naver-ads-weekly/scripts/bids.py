#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""① 노출 0 소재의 입찰가를 10원 올린다. 이 스킬에서 돈이 나가는 유일한 곳이다.

가드레일(2026-08-28~29 확정):
  1. enable=true 인 소재만            — 꺼진 광고 입찰가를 올리지 않는다
  2. 7일 노출 0 만                    — 30일 노출0 은 포기 후보이지 인상 대상이 아니다
  3. 그룹입찰이면 개별 전환 + 그룹기본가+10원
  4. 상한 200원 — 도달분은 상한도달-무노출 리스트
  5. 3주 연속 인상 실패면 중단
  6. 실행 전 원본 adAttr 전량 백업
  7. 결과를 이력에 기록
쓰기 방법(실측): PUT /ncc/ads/{adId}?fields=adAttr, body = 조회한 소재 객체 전체
"""
import json
from datetime import date

import ledger
import nvad


def plan_raise(row, ledger_data):
    """이 소재를 어떻게 할지 정한다. 네트워크를 타지 않는다."""
    # 그룹입찰을 따르는 상품은 '잠자던 bidAmt' 가 아니라 그룹 기본가가 출발점이다
    base = row.get("groupBid") if row.get("useGroupBid") else row.get("bid")
    action, new = ledger.bid_decision(ledger_data, row["adId"], base)
    return {"adId": row["adId"], "title": row.get("title", ""), "action": action,
            "from": base, "to": new, "useGroupBid": bool(row.get("useGroupBid"))}


def build_body(ad_obj, new_bid):
    """PUT 본문. 조회한 소재 객체 전체에 adAttr 만 갈아끼운다.

    useGroupBidAmt 는 False 로 바꾼다 — 개별 입찰가를 적용하려면 필수다.
    가역적이므로(실측 확인) 되돌릴 수 있다.
    """
    body = dict(ad_obj)
    body["adAttr"] = dict(ad_obj.get("adAttr") or {})
    body["adAttr"]["bidAmt"] = new_bid
    body["adAttr"]["useGroupBidAmt"] = False
    return body


def apply_raise(acct, ad_obj, new_bid):
    """실제로 입찰가를 바꾼다. (성공여부, 메시지)."""
    st, res = nvad.call(acct, "PUT", f"/ncc/ads/{ad_obj['nccAdId']}",
                        params={"fields": "adAttr"}, body=build_body(ad_obj, new_bid))
    if st in (200, 201):
        return True, ""
    return False, f"{st} {str(res)[:150]}"


def run_bids(acct, run_dir, rows, commit=False, log=print):
    """규칙 ① 대상 전체를 처리한다. commit 이 False 면 계획만 세운다."""
    alias = acct.get("alias") or str(acct.get("customer_id"))
    led_path = run_dir.parent.parent / "ledger" / f"{alias}.json"
    led = ledger.load(led_path)

    # 현재 소재 상태를 다시 조회한다 — 수집 이후 바뀌었을 수 있다
    ad_by_id = {}
    ads_path = run_dir / "accounts" / alias / "ads.json"
    try:
        for a in json.loads(ads_path.read_text(encoding="utf-8"))["ads"]:
            ad_by_id[a["nccAdId"]] = a
    except Exception as e:
        log(f"[{alias}] 소재 읽기 실패: {type(e).__name__}: {e}")
        return {}

    plans = [plan_raise(r, led) for r in rows]
    counts = {}
    for p in plans:
        counts[p["action"]] = counts.get(p["action"], 0) + 1

    log(f"[{alias}] 대상 {len(plans)}건 → " + " · ".join(f"{k} {v}" for k, v in counts.items()))
    for p in plans[:10]:
        log(f"    {p['action']:<10} {str(p['from']):>4}→{str(p['to']):<4} {p['title'][:30]}")
    if len(plans) > 10:
        log(f"    … 외 {len(plans)-10}건")

    if not commit:
        log("  (dry-run — --commit 을 주면 실제로 바꾼다)")
        return {"plans": plans, "counts": counts, "committed": 0}

    # 백업 먼저 — 실행 전 원본 adAttr 전량
    bk = run_dir / f"before_bids_{alias}.json"
    bk.write_text(json.dumps(
        {p["adId"]: (ad_by_id.get(p["adId"], {}).get("adAttr")) for p in plans if p["action"] == "인상"},
        ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"  백업 → {bk.name}")

    today = date.today().isoformat()
    ok = fail = 0
    for p in plans:
        if p["action"] != "인상":
            continue
        ad_obj = ad_by_id.get(p["adId"])
        if not ad_obj:
            fail += 1
            continue
        good, err = apply_raise(acct, ad_obj, p["to"])
        if good:
            ok += 1
            ledger.record_raise(led, p["adId"], today, p["from"], p["to"])
        else:
            fail += 1
            log(f"    ✗ {p['adId']} {err}")
    ledger.save(led_path, led)
    log(f"  인상 완료 {ok}건 / 실패 {fail}건 · 이력 → {led_path}")
    return {"plans": plans, "counts": counts, "committed": ok, "failed": fail}
