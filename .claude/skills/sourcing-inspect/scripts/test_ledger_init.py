#!/usr/bin/env python3
"""ledger_init.py 순수 함수 테스트 (pytest 불필요 — 그냥 실행)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ledger_init import new_state, ingest_snapshot, add_market_urls, merge_markets, should_ingest  # noqa: E402
import tempfile  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'} {name} {'' if cond else detail}")
    if not cond:
        FAILED.append(name)


TB = [{"item": {"itemId": 9001}}]
items = [
    {"id": "11154-K-1", "campaignId": "K", "productId": "10000001", "mallUrl": "https://smartstore.naver.com/A/", "timestamp": "2026-10-18 03:10:11"},
    {"id": "11154-K-2", "campaignId": "K", "productId": "10000002", "mallUrl": "http://smartstore.naver.com/a", "timestamp": "2026-10-18 03:10:11", "taobaoResult": TB},
    {"id": "U01M-x", "campaignId": "K", "productId": "U01Mabc", "timestamp": "2026-10-28 00:00:00"},
    {"id": "11154-K-3", "campaignId": "K", "productId": None, "mallUrl": "https://smartstore.naver.com/B"},
]
st = new_state()
ingest_snapshot(items, {"11154-K-1": {"verdict": "pass"}}, st)
check("네이버 번호 2건, 판정 있는 건 pass 없는 건 unjudged",
      [r["pid"] for r in st["products"]] == ["10000001", "10000002"]
      and st["products"][0]["verdict"] == "pass" and st["products"][1]["verdict"] == "unjudged", st["products"])
check("내부 번호는 따로(번호 없는 상품은 제외)", st["internal"] == {"U01Mabc"}, st["internal"])
check("타오바오 번호 수집", st["taobao"] == {"9001"})
check("마켓 표기 변형 합산·캠페인 기록",
      st["markets"]["a"]["products"] == 2 and st["markets"]["a"]["full_run"] == {"campaign": "K", "date": "2026-10-18"}
      and st["markets"]["b"]["products"] == 1, st["markets"])

add_market_urls(["https://smartstore.naver.com/a", "https://smartstore.naver.com/zzz"], st, "K")
check("목록 마켓: 있는 건 유지, 없는 건 빈 밭으로", st["markets"]["a"]["products"] == 2
      and st["markets"]["zzz"]["products"] == 0 and st["markets"]["zzz"]["empty"] is True
      and st["markets"]["zzz"]["full_run"]["campaign"] == "K")

existing = {"a": {**st["markets"]["a"], "products": 5, "last_3day": "2026-11-09"}}
merged = merge_markets(existing, st["markets"])
check("기존 장부와 합치기: 상품 수 큰 쪽, 3일 기록 유지, 새 마켓 추가",
      merged["a"]["products"] == 5 and merged["a"]["last_3day"] == "2026-11-09" and "zzz" in merged)

with tempfile.TemporaryDirectory() as d:
    check("일반 run 은 초기값에 포함", should_ingest(d) is True)
    open(os.path.join(d, "ledger_committed.json"), "w").write("{}")
    check("파이프라인 회차 run 은 초기값에서 제외", should_ingest(d) is False)

print("FAILED:", FAILED)
sys.exit(1 if FAILED else 0)
