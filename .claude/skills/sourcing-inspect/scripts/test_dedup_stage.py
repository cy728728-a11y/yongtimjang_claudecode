#!/usr/bin/env python3
"""dedup_stage.py 순수 함수 테스트 (pytest 불필요 — 그냥 실행)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dedup_stage import judge_naver, judge_taobao, late_ids, committed  # noqa: E402
import tempfile  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'} {name} {'' if cond else detail}")
    if not cond:
        FAILED.append(name)


items = [{"id": "a", "productId": "10000001"}, {"id": "b", "productId": "10000002"},
         {"id": "c", "productId": "10000001"}, {"id": "d", "productId": "U01M9"}, {"id": "e", "productId": None}]
r = judge_naver(items, {"10000002"})
check("장부 중복", r.get("b", {}).get("reason") == "DUP_SEEN" and r["b"]["note"] == "장부"
      and r["b"]["verdict"] == "drop" and r["b"]["by"] == "ledger", r)
check("회차 내 중복은 두 번째만", "a" not in r and r.get("c", {}).get("note") == "같은 회차 중복", r)
check("숫자 아닌 번호는 건너뜀", "d" not in r and "e" not in r, r)


def TB(i):
    return {"taobaoResult": [{"item": {"itemId": i}}]}


r = judge_taobao([{"id": "x", **TB(5)}, {"id": "y", **TB(6)}, {"id": "z", "taobaoResult": []}], {"5"})
check("타오바오 중복", set(r) == {"x"} and r["x"]["reason"] == "DUP_TAOBAO" and r["x"]["verdict"] == "drop", r)

# C1: 장부에 같은 캠페인으로 들어간 번호는 중복이 아니다(자기 회차 재실행 방어)
r = judge_naver([{"id": "a", "productId": "10000002"}, {"id": "b", "productId": "10000003"}],
                {"10000002": "C", "10000003": "OLD"}, campaign="C")
check("같은 캠페인 장부 기록은 중복 아님", "a" not in r and r.get("b", {}).get("reason") == "DUP_SEEN", r)
with tempfile.TemporaryDirectory() as d:
    check("기록 안 된 run 은 통과", committed(d) is False)
    open(os.path.join(d, "ledger_committed.json"), "w").write("{}")
    check("이미 장부에 기록한 run 은 거부 대상", committed(d) is True)
# I2: 1차 스냅샷 뒤에 늦게 들어온 상품
check("늦게 들어온 상품 id", late_ids([{"id": "a"}, {"id": "z"}], [{"id": "a"}]) == ["z"])

print("FAILED:", FAILED)
sys.exit(1 if FAILED else 0)
