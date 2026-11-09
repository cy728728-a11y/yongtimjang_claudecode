#!/usr/bin/env python3
"""pilot_select.py 순수 함수 테스트 (pytest 불필요 — 그냥 실행)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pilot_select import pick  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'} {name} {'' if cond else detail}")
    if not cond:
        FAILED.append(name)


def mk(slug, n, camp="kwy9jllI5NICgPo"):
    return {"slug": slug, "url": f"https://smartstore.naver.com/{slug}", "first_seen": "",
            "full_run": {"campaign": camp, "date": ""} if camp else None, "last_3day": None, "products": n, "empty": n == 0}


markets = {"big": mk("big", 9), "m1": mk("m1", 5), "m2": mk("m2", 5), "small": mk("small", 1),
           "zero": mk("zero", 0), "other": mk("other", 50, camp="YWfs4MpPnVWHzYW"), "none": mk("none", 7, camp=None)}
r = pick(markets, top_n=1, rand_n=2, seed=1)
check("상위 1건은 상품 수 최다", [k for k, v in r.items() if v == "top"] == ["big"], r)
rnd = {k for k, v in r.items() if v == "random"}
check("무작위 2건은 상품>0·같은 캠페인에서만", len(rnd) == 2 and rnd <= {"m1", "m2", "small"}, r)
check("0개·다른 캠페인·캠페인 없음은 안 뽑힘", not ({"zero", "other", "none"} & set(r)), r)
check("같은 seed 면 같은 결과", pick(markets, top_n=1, rand_n=2, seed=1) == r)
check("모자라면 있는 만큼", len(pick(markets, top_n=10, rand_n=10, seed=1)) == 4)

print("FAILED:", FAILED)
sys.exit(1 if FAILED else 0)
