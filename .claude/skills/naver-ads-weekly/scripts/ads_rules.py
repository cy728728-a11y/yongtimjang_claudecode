#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""광고 규칙 판정 — 순수 함수. 네트워크·파일을 타지 않는다.

⑦ 체계 (2026-10-16 용팀장 확정):
  ⑦a (=①) 7일 노출 0 → 입찰 +10원. result.json 키는 `①노출0` 그대로(bids 가 읽는다)
  ⑦b      7일 노출 ≥ POP_IMP_MIN 게재중 소재(전 계정 합산 1풀)의 CTR 하위 CTR_TAIL_PCT → 썸네일 변형
  ⑦c      같은 풀의 CTR 상위 CTR_TAIL_PCT 중 상세 미가공만 → 상세 꾸미기 (최종 거름은 final_7c)
  ⑦d      30일 클릭 ≥ MAINT_CLICK_MIN 전부(구매 무관) → 상세+옵션명 정비 점검
  ③⑤⑥   그대로. ②④ 는 result.json 에 계속 남지만(웹앱·테스트가 읽는다) 시트·보고서엔 안 쓴다

기간은 호출자가 정한다: ①·⑦b·⑦c 는 7일 통계, ②③④⑤·⑦d 는 30일 통계를 넘긴다.
노출 0 소재는 /stats 응답에서 행 자체가 빠지므로 '게재중 전체 − 통계에 있는 것' 으로 역산한다.
⑦b/⑦c 는 계정을 넘나드는 1풀이라 classify(계정 1개) 밖의 split_global 이 계산한다.
"""
import math

IMP_MIN = 100      # ②④ 노출 하한 — 없으면 ②가 전체의 66% 가 된다(실측)
CLICK_MIN = 20     # ③ 클릭 하한
CTR_LOW = 1.0      # ② 기준
CTR_HIGH = 2.0     # ④ 기준
# 검수 대기 상태 — 노출이 없는 게 정상이라 규칙 ①(입찰 인상) 대상에서 뺀다
INSPECT_WAITING = ("PENDING", "UNDER_REVIEW")

# ── ⑦ 상수 — 조정은 여기 한 곳에서만 한다 ─────────────────────────────
POP_IMP_MIN = 50        # ⑦b/⑦c 모집단 7일 노출 하한 (2026-10-16 용팀장 확정 · 2~3주 뒤 조정 예정)
CTR_TAIL_PCT = 0.10     # ⑦b/⑦c CTR 끝단 비율, 개수 = ceil(풀×비율) (2026-10-16 용팀장 확정 · 2~3주 뒤 조정 예정)
MAINT_CLICK_MIN = 20    # ⑦d 30일 클릭 하한 (2026-10-16 용팀장 확정 · 2~3주 뒤 조정 예정)

# ⑦c 에 남길 상세 상태 — 미가공(중국어원본/단순번역)만. 문자열은 webapp/state.py 의 판정값이다
DETAIL_UNPROCESSED = ("중국어원본", "단순번역만")
MATCH_HIT = "히트"
UNMATCHED_PREFIX = "미매칭:"
NOT_LOOKED_UP = "불사자 미조회"   # enrich 를 안 돌렸거나 실패해 보강 키가 아예 없는 행


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


def _info_of_fn(group_of):
    """group_of 해석 — classify 와 pool_rows 가 같은 방식으로 그룹명·그룹가를 붙인다."""
    def info_of(a):
        g = group_of.get(a.get("nccAdgroupId")) or {}
        return ad_info(a, g.get("name") or "", g.get("bidAmt"))
    return info_of


def pool_rows(ads, group_of, stats_7d):
    """⑦b/⑦c 모집단 — 게재중 + 7일 통계 있음 + 노출 ≥ POP_IMP_MIN. 7일 지표가 붙은 행."""
    info_of = _info_of_fn(group_of)
    out = []
    for a in live_ads(ads):
        s = stats_7d.get(a["nccAdId"])
        if not s:
            continue
        if (s.get("impCnt") or 0) >= POP_IMP_MIN:
            out.append(_with_stat(info_of(a), s))
    return out


def ctr_tail(rows, pct=CTR_TAIL_PCT, top=False):
    """CTR 끝단 ceil(len×pct) 건. 하위는 CTR 오름차순, 상위는 내림차순 — 동률은 노출 많은 쪽 먼저."""
    if not rows:
        return []
    n = math.ceil(len(rows) * pct)
    if top:
        key = lambda r: (-(r.get("ctr") or 0.0), -(r.get("imp") or 0))
    else:
        key = lambda r: ((r.get("ctr") or 0.0), -(r.get("imp") or 0))
    return [dict(r) for r in sorted(rows, key=key)[:n]]


def split_global(pools):
    """{alias: [풀 행]} → 전 계정 합산 1풀로 끝단을 구해 계정별로 되돌린다.

    계정별로 따로 자르면 노출 적은 계정의 '상대적 하위'가 섞여 기준이 흔들린다 —
    용팀장 결정은 전 계정 1풀이다. 각 행에 acct 를 붙인다.
    """
    merged = []
    for alias, rows in (pools or {}).items():
        merged.extend(dict(r, acct=alias) for r in rows or [])
    out = {alias: {"⑦b썸네일변형": [], "⑦c상세꾸미기후보": []} for alias in (pools or {})}
    for key, top in (("⑦b썸네일변형", False), ("⑦c상세꾸미기후보", True)):
        for r in ctr_tail(merged, top=top):
            out.setdefault(r["acct"], {"⑦b썸네일변형": [], "⑦c상세꾸미기후보": []})[key].append(r)
    return out


def _enriched(row):
    """보강(enrich) 을 거친 행인가 — 불사자매칭 키가 있으면 거친 것이다."""
    return isinstance(row, dict) and "불사자매칭" in row


def match_label(row):
    """시트·보고서용 불사자매칭 표기. 보강 키가 없으면 '불사자 미조회'."""
    return row.get("불사자매칭") if _enriched(row) else NOT_LOOKED_UP


def final_7c(rows):
    """⑦c 최종 — 히트 & 상세 미가공 ∪ 미매칭(라벨 남김) ∪ 미조회. 히트 & AI가공완료 만 뺀다."""
    out = []
    for r in rows or []:
        if not _enriched(r):
            out.append(r)
            continue
        m = str(r.get("불사자매칭") or "")
        if m.startswith(UNMATCHED_PREFIX):
            out.append(r)
        elif m == MATCH_HIT and r.get("상세상태") in DETAIL_UNPROCESSED:
            out.append(r)
        elif m == MATCH_HIT and r.get("상세상태") is None:
            # 히트인데 상세 판정을 못 했다 — 빼면 조용히 사라진다. 남겨서 사람이 본다
            out.append(r)
    return out


def maintenance_verdict(row):
    """⑦d 정비 판정 문자열."""
    if not _enriched(row):
        return NOT_LOOKED_UP
    if str(row.get("불사자매칭") or "").startswith(UNMATCHED_PREFIX):
        return "불사자 미매칭"
    d, o = row.get("상세미가공"), row.get("옵션미정리")
    if d is False and o is False:
        return "정비완료"
    parts = []
    if d is True:
        parts.append("상세 미가공")
    if o is True:
        parts.append("옵션명 미정리")
    if parts:
        return " · ".join(parts)
    # 남은 경우: 하나 이상 None 이고 True 는 없다
    if d is None and o is None:
        return "판정 불가(상세·옵션)"
    return "판정 불가(옵션)" if o is None else "판정 불가(상세)"


def classify(ads, group_of, stats_7d, stats_30d, purchases):
    """6개 규칙으로 소재를 분류한다.

    ads        : 소재 전량(꺼진 것 포함)
    group_of   : {nccAdgroupId: {"name": str, "bidAmt": int|None}}
    stats_7d   : {adId: stat}  — 규칙 ① 용
    stats_30d  : {adId: stat}  — 규칙 ②③④⑤ 용
    purchases  : {adId: {"cnt": int, "amt": int}} — 구매완료만
    """
    info_of = _info_of_fn(group_of)

    live = live_ads(ads)
    off = [a for a in ads if not a.get("enable")]

    # ① 7일 통계에 행이 없는 게재중 소재 = 노출 0
    #    단 검수 대기 중인 소재는 뺀다 — 노출이 없는 게 당연하고, 입찰가를 올려도
    #    노출이 생기지 않는다. 실측(2026-08-29): 검수대기 7건이 전부 규칙 ① 에 잡혔다.
    r1 = [info_of(a) for a in live
          if a["nccAdId"] not in stats_7d and a.get("inspectStatus") not in INSPECT_WAITING]

    r2, r3, r4, r5, r7d = [], [], [], [], []
    # BOARD-05: 꺼진 소재의 과거 실적은 현재 유입 판정에 들어가지 않는다 — live 만 순회한다.
    # test_ads_rules.TestPausedAdsRule6 이 고정한다.
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
        # ⑦d 는 구매 여부와 무관 — 팔리는 상품도 상세·옵션 정비 대상이다
        if clk >= MAINT_CLICK_MIN:
            r7d.append(dict(row, purCnt=(pur or {}).get("cnt", 0)))

    # ⑥ 행 보강용 — 같은 계정·같은 상품에 게재중 소재가 하나라도 있으면 상품은 아직 광고 중이다.
    # ad_info 를 고치지 않고 ⑥ 행에만 붙인다: ad_info 에 넣으면 ①~⑤ 행까지 불어나 result.json(2.2MB)이 커진다
    live_malls = {(a.get("referenceData") or {}).get("mallProductId") for a in live} - {None}

    # ② 는 노출 많은 순 — 노출은 많은데 클릭이 안 되는 쪽이 썸네일 문제가 가장 확실하다
    r2.sort(key=lambda x: -x["imp"])
    r4.sort(key=lambda x: -x["ctr"])
    r5.sort(key=lambda x: -x["purAmt"])
    r7d.sort(key=lambda x: -x["clk"])

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
        "⑥삭제대상": [dict(info_of(a), statusReason=a.get("statusReason"),
                         editTm=a.get("editTm"),
                         productLive=(a.get("referenceData") or {}).get("mallProductId") in live_malls)
                    for a in off],
        "⑦d정비점검후보": r7d,
        "_summary": summary,
    }
