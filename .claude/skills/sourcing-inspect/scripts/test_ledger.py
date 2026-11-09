#!/usr/bin/env python3
"""ledger.py 회귀 테스트 (pytest 불필요 — 그냥 실행).
    .venv/bin/python3 .claude/skills/sourcing-inspect/scripts/test_ledger.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ledger import (mall_slug, is_naver_pid, load_seen_products, append_seen_products,  # noqa: E402
                    load_seen_taobao, append_seen_taobao, load_markets, upsert_markets, taobao_item_id)

FAILED = []


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'} {name} {'' if cond else detail}")
    if not cond:
        FAILED.append(name)


check("slug 표기 변형 통일",
      mall_slug("HTTP://smartstore.naver.com/Clover131/") == "clover131"
      and mall_slug("https://m.smartstore.naver.com/clover131") == "clover131"
      and mall_slug("https://brand.naver.com/abc/") == "brand.naver.com/abc"
      and mall_slug("") is None and mall_slug(None) is None)
check("네이버 번호 판별",
      is_naver_pid("10162030898") and is_naver_pid(10162030898)
      and not is_naver_pid("U01M123") and not is_naver_pid(None) and not is_naver_pid("") and not is_naver_pid("12"))

with tempfile.TemporaryDirectory() as d:
    p = os.path.join(d, "sub", "seen_products.jsonl")   # 없는 하위 폴더 — 쓰기 때 만들어야 한다
    t = os.path.join(d, "sub", "seen_taobao.txt")
    m = os.path.join(d, "sub", "markets.jsonl")
    check("없는 파일은 빈 집합", load_seen_products(p) == set() and load_seen_taobao(t) == set() and load_markets(m) == {})
    row = {"pid": "1", "campaign": "c", "date": "2026-11-10", "verdict": "pass"}
    n1 = append_seen_products([row, dict(row)], p)
    n2 = append_seen_products([row], p)
    check("append 는 중복 제외·개수 반환", n1 == 1 and n2 == 0 and load_seen_products(p) == {"1"}, (n1, n2))
    n3 = append_seen_taobao([123, "123", "456"], t)
    check("타오바오 int→str", n3 == 2 and load_seen_taobao(t) == {"123", "456"}, n3)
    mrow = {"slug": "a", "url": "https://smartstore.naver.com/a", "first_seen": "2026-11-10",
            "full_run": {"campaign": "k", "date": "2026-10-17"}, "last_3day": None, "products": 3, "empty": False}
    upsert_markets({"a": mrow}, m)
    back = load_markets(m)
    check("markets 왕복", back["a"]["products"] == 3 and back["a"]["full_run"]["campaign"] == "k", back)

check("taobao_item_id",
      taobao_item_id({"taobaoResult": [{"item": {"itemId": 77}}]}) == "77"
      and taobao_item_id({"taobaoResult": None}) is None
      and taobao_item_id({"taobaoResult": []}) is None
      and taobao_item_id({}) is None)

print("FAILED:", FAILED)
sys.exit(1 if FAILED else 0)
