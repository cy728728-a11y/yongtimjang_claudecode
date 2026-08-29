#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""계정 순회 수집 — prep 단계의 본체. 여기서 네트워크가 전부 끝난다.

호출 규모(실측): 계정 1개당 캠페인 1 + 그룹 1 + 소재 10~13 + /stats 3~6
                + 전환 리포트 30(생성·폴링). 계정 수에 선형이다.
"""
import json
from datetime import date, timedelta

import nvad
import reports

# salesAmt 는 광고비다(매출 아님). convAmt·ccnt 는 장바구니가 섞여 있어 요청하지 않는다
STATS_FIELDS = ["impCnt", "clkCnt", "ctr", "salesAmt", "avgRnk"]


def window(days, today=None):
    """(since, until) — until 은 항상 D-2. D-1 은 리포트 지표가 준비되지 않는다."""
    today = today or date.today()
    until = today - timedelta(days=2)
    return until - timedelta(days=days - 1), until


def fetch_ads(acct):
    """SHOPPING 캠페인의 소재 전량과 광고그룹 정보를 받는다.

    SHOPPING 캠페인은 계정당 여러 개일 수 있다(cy7728 은 2개) — 전부 순회한다.
    WEB_SITE 등 다른 유형은 이 스킬 범위가 아니다.
    """
    ads, group_of = [], {}
    st, camps = nvad.call(acct, "GET", "/ncc/campaigns")
    if st != 200 or not isinstance(camps, list):
        return [], {}
    for c in [x for x in camps if x.get("campaignTp") == "SHOPPING"]:
        st, groups = nvad.call(acct, "GET", "/ncc/adgroups", {"nccCampaignId": c["nccCampaignId"]})
        if st != 200 or not isinstance(groups, list):
            continue
        for g in groups:
            group_of[g["nccAdgroupId"]] = {"name": g.get("name") or "", "bidAmt": g.get("bidAmt")}
            st, a = nvad.call(acct, "GET", "/ncc/ads", {"nccAdgroupId": g["nccAdgroupId"]})
            if st == 200 and isinstance(a, list):
                ads.extend(a)
    return ads, group_of


def fetch_stats(acct, ad_ids, since, until):
    """기간 합계 통계. ids 는 100개씩 끊어 보낸다.

    노출 0 소재는 응답에서 행 자체가 빠진다 — 그래서 규칙 ① 이 역산이다.
    """
    tr = json.dumps({"since": since.isoformat(), "until": until.isoformat()})
    fields = json.dumps(STATS_FIELDS)
    out = {}
    for batch in nvad.chunks(ad_ids, 100):
        st, res = nvad.call(acct, "GET", "/stats",
                            {"ids": ",".join(batch), "fields": fields, "timeRange": tr})
        if st != 200:
            continue
        rows = res.get("data", []) if isinstance(res, dict) else (res or [])
        for r in rows:
            if isinstance(r, dict) and r.get("id"):
                out[r["id"]] = r
    return out


def collect_account(acct, run_dir, log=print):
    """계정 1개를 수집해 run-dir 에 저장하고 요약을 돌려준다."""
    alias = acct.get("alias") or str(acct.get("customer_id"))
    out_dir = run_dir / "accounts" / alias
    out_dir.mkdir(parents=True, exist_ok=True)
    log(f"[{alias}] 수집 시작")

    ads, group_of = fetch_ads(acct)
    live_ids = [a["nccAdId"] for a in ads if a.get("enable")]
    log(f"  소재 {len(ads)}개 (게재중 {len(live_ids)})")
    (out_dir / "ads.json").write_text(
        json.dumps({"ads": ads, "groups": group_of}, ensure_ascii=False), encoding="utf-8")

    s7_since, s7_until = window(7)
    s30_since, s30_until = window(30)
    s7 = fetch_stats(acct, live_ids, s7_since, s7_until)
    s30 = fetch_stats(acct, live_ids, s30_since, s30_until)
    log(f"  통계 7일 {len(s7)}행 / 30일 {len(s30)}행")
    (out_dir / "stats_7d.json").write_text(json.dumps(s7, ensure_ascii=False), encoding="utf-8")
    (out_dir / "stats_30d.json").write_text(json.dumps(s30, ensure_ascii=False), encoding="utf-8")

    pur = reports.fetch_purchases(acct, s30_until, 30, log=log)
    (out_dir / "purchase.json").write_text(json.dumps(pur, ensure_ascii=False), encoding="utf-8")

    return {
        "alias": alias, "ads": len(ads), "live": len(live_ids),
        "stats7": len(s7), "stats30": len(s30), "purchaseAds": len(pur),
        "window7": [s7_since.isoformat(), s7_until.isoformat()],
        "window30": [s30_since.isoformat(), s30_until.isoformat()],
    }
