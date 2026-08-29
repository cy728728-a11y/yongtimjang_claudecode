#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""6개 규칙 판정 — 순수 함수. 네트워크·파일을 타지 않는다.

기간은 호출자가 정한다: ① 은 7일 통계, ②③④⑤ 는 30일 통계를 넘긴다.
노출 0 소재는 /stats 응답에서 행 자체가 빠지므로 '게재중 전체 − 통계에 있는 것' 으로 역산한다.
"""

IMP_MIN = 100      # ②④ 노출 하한 — 없으면 ②가 전체의 66% 가 된다(실측)
CLICK_MIN = 20     # ③ 클릭 하한
CTR_LOW = 1.0      # ② 기준
CTR_HIGH = 2.0     # ④ 기준


def live_ads(ads):
    """게재중 소재만. 꺼진 소재를 안 거르면 죽은 광고 입찰가만 올리게 된다."""
    return [a for a in ads if a.get("enable")]


def effective_bid(ad, group_bid):
    """실제로 적용되는 입찰가.

    useGroupBidAmt=True 면 adAttr.bidAmt 는 잠자는 값이고 그룹 기본가가 적용된다.
    이걸 헷갈리면 입찰가를 올리려다 오히려 내리게 된다(실측: 그룹 70원 / 잠자던 값 50원).
    """
    attr = ad.get("adAttr") or {}
    if attr.get("useGroupBidAmt"):
        return group_bid
    return attr.get("bidAmt")


def ad_info(ad, group_name, group_bid):
    """판정 결과 1행의 공통 필드."""
    rd = ad.get("referenceData") or {}
    attr = ad.get("adAttr") or {}
    return {
        "adId": ad["nccAdId"],
        "adGroup": group_name,
        "title": rd.get("productTitle") or "",
        "mallProductId": rd.get("mallProductId"),   # 썸네일 스킬 매칭 키
        "bid": effective_bid(ad, group_bid),
        "useGroupBid": bool(attr.get("useGroupBidAmt")),
        "groupBid": group_bid,
    }


def _with_stat(info, s):
    """통계 지표를 판정행에 붙인다. salesAmt 는 매출이 아니라 광고비다."""
    info = dict(info)
    info.update({
        "imp": s.get("impCnt", 0), "clk": s.get("clkCnt", 0),
        "ctr": s.get("ctr") or 0.0, "rank": s.get("avgRnk") or 0.0,
        "cost": s.get("salesAmt", 0),
    })
    return info


def classify(ads, group_of, stats_7d, stats_30d, purchases):
    """6개 규칙으로 소재를 분류한다.

    ads        : 소재 전량(꺼진 것 포함)
    group_of   : {nccAdgroupId: {"name": str, "bidAmt": int|None}}
    stats_7d   : {adId: stat}  — 규칙 ① 용
    stats_30d  : {adId: stat}  — 규칙 ②③④⑤ 용
    purchases  : {adId: {"cnt": int, "amt": int}} — 구매완료만
    """
    def info_of(a):
        g = group_of.get(a.get("nccAdgroupId")) or {}
        return ad_info(a, g.get("name") or "", g.get("bidAmt"))

    live = live_ads(ads)
    off = [a for a in ads if not a.get("enable")]

    # ① 7일 통계에 행이 없는 게재중 소재 = 노출 0
    r1 = [info_of(a) for a in live if a["nccAdId"] not in stats_7d]

    r2, r3, r4, r5 = [], [], [], []
    for a in live:
        s = stats_30d.get(a["nccAdId"])
        if not s:
            continue
        row = _with_stat(info_of(a), s)
        imp, clk, ctr = row["imp"], row["clk"], row["ctr"]
        pur = purchases.get(a["nccAdId"])

        if imp >= IMP_MIN and ctr < CTR_LOW:
            r2.append(row)
        if clk >= CLICK_MIN and not pur:
            r3.append(row)
        if imp >= IMP_MIN and ctr >= CTR_HIGH:
            r4.append(row)
        if pur:
            r5.append(dict(row, purCnt=pur["cnt"], purAmt=pur["amt"]))

    # ② 는 노출 많은 순 — 노출은 많은데 클릭이 안 되는 쪽이 썸네일 문제가 가장 확실하다
    r2.sort(key=lambda x: -x["imp"])
    r4.sort(key=lambda x: -x["ctr"])
    r5.sort(key=lambda x: -x["purAmt"])

    # 요약은 30일 통계 전량에서 한 번만 계산한다.
    # 규칙별 행을 합산하면 같은 소재가 ②와 ③에 동시에 들어가 광고비가 두 번 세진다.
    summary = {
        "ads": len(ads),
        "live": len(live),
        "cost": sum((stats_30d.get(a["nccAdId"]) or {}).get("salesAmt", 0) for a in live),
        "purAmt": sum(v.get("amt", 0) for v in purchases.values()),
        "purCnt": sum(v.get("cnt", 0) for v in purchases.values()),
    }

    return {
        "①노출0": r1,
        "②썸네일교체": r2,
        "③원인분석": r3,
        "④효자후보": r4,
        "⑤효자확정": r5,
        "⑥삭제대상": [info_of(a) for a in off],
        "_summary": summary,
    }
