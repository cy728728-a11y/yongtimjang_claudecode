#!/usr/bin/env python3
"""ledger_commit.py 순수 함수 테스트 (pytest 불필요 — 그냥 실행)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ledger_commit import market_rows, product_rows, taobao_ids, updates_markets  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'} {name} {'' if cond else detail}")
    if not cond:
        FAILED.append(name)


items = [
    {"id": "x1", "productId": "10000001", "mallUrl": "https://smartstore.naver.com/A/", "taobaoResult": [{"item": {"itemId": 9}}]},
    {"id": "x2", "productId": "10000002", "mallUrl": "http://smartstore.naver.com/a"},
    {"id": "x3", "productId": "U01Mzz", "mallUrl": "https://smartstore.naver.com/newbie"},
]
existing = {"a": {"slug": "a", "url": "https://smartstore.naver.com/a", "first_seen": "2026-10-18",
                  "full_run": {"campaign": "K", "date": "2026-10-18"}, "last_3day": None, "products": 3, "empty": False}}
rows = market_rows(items, "3day", "P1", "2026-11-16", existing)
check("3일 회차: 상품 수 누적·last_3day 세팅·full_run 유지",
      rows["a"]["products"] == 5 and rows["a"]["last_3day"] == "2026-11-16"
      and rows["a"]["full_run"]["campaign"] == "K" and rows["a"]["empty"] is False, rows.get("a"))
check("새 마켓은 추가(first_seen=회차 날짜)", rows["newbie"]["products"] == 1 and rows["newbie"]["first_seen"] == "2026-11-16"
      and rows["newbie"]["last_3day"] == "2026-11-16" and rows["newbie"]["full_run"] is None, rows.get("newbie"))
rows2 = market_rows(items[:1], "full", "F1", "2026-11-16", {})
check("전체 이력 회차: full_run 세팅", rows2["a"]["full_run"] == {"campaign": "F1", "date": "2026-11-16"} and rows2["a"]["last_3day"] is None)

pr = product_rows(items, {"x1": {"verdict": "pass"}}, "P1", "2026-11-16")
check("상품 행: 네이버 번호만, 판정 없으면 unjudged",
      [(r["pid"], r["verdict"]) for r in pr] == [("10000001", "pass"), ("10000002", "unjudged")]
      and pr[0]["campaign"] == "P1" and pr[0]["date"] == "2026-11-16", pr)
check("타오바오 번호 모음", taobao_ids(items) == {"9"})

check("마켓 수는 1차 run 에서만 더한다(R1·R2 이중 가산 방지)", updates_markets(1) is True and updates_markets(2) is False)

print("FAILED:", FAILED)
sys.exit(1 if FAILED else 0)
