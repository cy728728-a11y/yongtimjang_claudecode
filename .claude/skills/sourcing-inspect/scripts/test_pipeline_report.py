#!/usr/bin/env python3
"""pipeline_report.py 순수 함수 테스트 (pytest 불필요 — 그냥 실행)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline_report import summarize, render, REHARVEST_MARKETS, ROUNDS_PER_MONTH, TARGET  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'} {name} {'' if cond else detail}")
    if not cond:
        FAILED.append(name)


def it(i, mall):
    return {"id": f"x{i}", "productId": f"1000000{i}", "mallUrl": f"https://smartstore.naver.com/{mall}"}


items = [it(1, "a"), it(2, "a"), it(3, "b"), it(4, "b"), it(5, "c"), it(6, "c")]
dup1 = {"x6": {"verdict": "drop", "reason": "DUP_SEEN"}}
v1 = {"x1": {"verdict": "pass"}, "x2": {"verdict": "pass"}, "x3": {"verdict": "pass"}, "x4": {"verdict": "drop", "reason": "BANNED_CAT"},
      "x5": {"verdict": "pass"}, **dup1}
dup2 = {"x5": {"verdict": "drop", "reason": "DUP_TAOBAO"}}
v2 = {"x1": {"verdict": "pass"}, "x2": {"verdict": "drop", "reason": "IP"}, "x3": {"verdict": "pass"}, **dup2}
collect = {"x1": {"ok": True}, "x3": {"ok": False, "dup": True}}
meta = {"a": "top", "b": "top", "c": "random"}

s = summarize(items, v1, dup1, v2, dup2, collect, meta)
check("기본 집계", s["markets_total"] == 3 and s["markets_with_items"] == 3 and s["collected"] == 6
      and s["dup_naver"] == 1 and s["dup_taobao"] == 1 and s["pass1"] == 4 and s["pass2"] == 2, s)
check("통과율·마켓당", abs(s["pass_rate"] - 2 / 6) < 1e-9 and abs(s["per_market_collected"] - 2) < 1e-9
      and abs(s["per_market_pass2"] - 2 / 3) < 1e-9, s)
check("수집 접수 수", s["collected_ok"] == 1 and s["collect_dup"] == 1, s)
check("묶음별", s["buckets"]["top"]["markets"] == 2 and s["buckets"]["top"]["pass2"] == 2 and s["buckets"]["random"]["pass2"] == 0
      and abs(s["buckets"]["top"]["per_market_pass2"] - 1.0) < 1e-9, s["buckets"])
check("월 예측 B", s["monthly_B"] == round(2 / 3 * REHARVEST_MARKETS * ROUNDS_PER_MONTH) and s["gap_to_target"] == s["monthly_B"] - TARGET, s)
md = render(s)
check("첫 줄에 목표 140,000", "140,000" in md.splitlines()[0] and "월 공급 예측" in md.splitlines()[0], md.splitlines()[0])

print("FAILED:", FAILED)
sys.exit(1 if FAILED else 0)
