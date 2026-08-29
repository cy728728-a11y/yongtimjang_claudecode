#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AD_CONVERSION 리포트 — 구매완료(purchase) 전환만 뽑는다.

왜 필요한가(2026-08-27 실측):
    /stats 의 ccnt·convAmt 는 전환유형을 전부 합산한 값이라 장바구니가 섞인다.
    cy728 30일: add_to_cart 7,321,700원 vs purchase 596,920원 — 12배 차이.
    breakdown 파라미터는 400 이 아니라 200 에 안 쪼개진 값을 주므로 눈치채기 어렵다.

리포트는 하루치씩만 생성된다. D-1 은 "20007 지표 준비중" 이라 D-2 부터 쓴다.
"""
import time
from collections import defaultdict
from datetime import timedelta

import nvad

# 전환유형 컬럼은 0-based 10 번, 전환수 11, 금액 12
_COL_AD_ID = 5
_COL_CONV_TYPE = 10
_COL_CNT = 11
_COL_AMT = 12
_MIN_COLS = 13


def parse_conversion_tsv(text):
    """리포트 TSV 를 행 리스트로 바꾼다. 열이 모자란 행은 버린다."""
    rows = []
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        c = line.split("\t")
        if len(c) < _MIN_COLS:
            continue
        try:
            rows.append({
                "adId": c[_COL_AD_ID],
                "convType": c[_COL_CONV_TYPE],
                "cnt": int(c[_COL_CNT] or 0),
                "amt": int(c[_COL_AMT] or 0),
            })
        except (ValueError, IndexError):
            continue
    return rows


def _build_and_download(acct, day, log):
    """하루치 리포트를 생성·폴링·다운로드한다. 전환 0인 날은 빌드되지 않는다."""
    st, job = nvad.call(acct, "POST", "/stat-reports",
                        body={"reportTp": "AD_CONVERSION", "statDt": day.isoformat() + "T00:00:00Z"})
    if st not in (200, 201) or not isinstance(job, dict):
        log(f"    {day} 생성 실패 {st} {str(job)[:120]}")
        return None
    jid = job.get("reportJobId")
    for _ in range(12):
        time.sleep(4)
        st, j = nvad.call(acct, "GET", f"/stat-reports/{jid}")
        if not isinstance(j, dict):
            continue
        if j.get("status") == "BUILT" and j.get("downloadUrl"):
            # nvad.download 는 실패하면 예외 대신 None 을 준다
            text = nvad.download(acct, j["downloadUrl"])
            if text is None:
                log(f"    {day} 다운로드 실패")
            return text
        if j.get("status") in ("NONE", "ERROR"):
            return None
    log(f"    {day} 빌드 대기 초과")
    return None


def fetch_purchases(acct, until, days, log=print):
    """until 부터 거슬러 days 일치 구매완료 전환을 소재별로 합산한다."""
    out = defaultdict(lambda: {"cnt": 0, "amt": 0})
    ok_days = 0
    for d in range(days):
        day = until - timedelta(days=d)
        text = _build_and_download(acct, day, log)
        if text is None:
            continue
        ok_days += 1
        for r in parse_conversion_tsv(text):
            if r["convType"] != "purchase":
                continue
            out[r["adId"]]["cnt"] += r["cnt"]
            out[r["adId"]]["amt"] += r["amt"]
    log(f"    구매완료 리포트 {ok_days}/{days}일 · 발생 소재 {len(out)}개")
    return dict(out)
