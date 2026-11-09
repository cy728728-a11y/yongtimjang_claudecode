#!/usr/bin/env python3
"""campaign_watch.py 순수 함수 테스트 (pytest 불필요 — 그냥 실행)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from campaign_watch import is_complete  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'} {name} {'' if cond else detail}")
    if not cond:
        FAILED.append(name)


check("0건 안정은 완료 아님", not is_complete([0, 0, 0], 3))
check("3회 같으면 완료", is_complete([10, 50, 50, 50], 3))
check("아직 늘면 미완료", not is_complete([10, 50, 60], 3) and not is_complete([50, 50], 3))
check("빈 이력은 미완료", not is_complete([], 3))

print("FAILED:", FAILED)
sys.exit(1 if FAILED else 0)
