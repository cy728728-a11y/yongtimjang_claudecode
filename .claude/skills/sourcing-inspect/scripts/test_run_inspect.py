#!/usr/bin/env python3
"""run_inspect.py 순수 함수 회귀 테스트 (pytest 불필요 — 그냥 실행).
    .venv/bin/python3 .claude/skills/sourcing-inspect/scripts/test_run_inspect.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_inspect import abs_url, exclude_dups, select_targets, to_view, make_batches, merge_judged, pending_batches, dedupe_views, spread_dups  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'} {name} {'' if cond else detail}")
    if not cond:
        FAILED.append(name)


TB = [{"item": {"title": "螺丝刀", "image": "http://t", "sku": {"def": {"price": "35.00"}}}}]
items = [
    {"id": "a", "taobaoResult": [], "taobao_match_status": "pending"},
    {"id": "b", "taobaoResult": TB},
    {"id": "c", "taobaoResult": [], "taobao_match_status": "match_failed"},
    {"id": "d"},
]
check("1차 대상 = 매칭 없음(실패 제외)", [i["id"] for i in select_targets(items, 1)] == ["a", "d"])
check("2차 대상 = 매칭 있음 + 실패", [i["id"] for i in select_targets(items, 2)] == ["b", "c"])

v = to_view({"id": "x", "catId": 50000979, "taobaoResult": []}, 2, {"50000979": "A>B"})
check("to_view 빈 매칭에도 안 죽음", v["tb_title"] is None and v["catPath"] == "A>B", v)
v = to_view({"id": "b", "taobaoResult": TB}, 2)
check("to_view 타오바오 가격", v["tb_price_cny"] == "35.00", v)

check("프로토콜 생략 URL 보정", abs_url("//img.alicdn.com/a.jpg") == "https://img.alicdn.com/a.jpg" and abs_url(None) == "")
check("85건/40 → 3배치", [len(b) for b in make_batches(list(range(85)), 40)] == [40, 40, 5])

ver, miss, extra = merge_judged(
    ["a", "b", "c"],
    [[{"id": "a", "verdict": "pass", "reason": "OK"}, {"id": "zz", "verdict": "pass"}],
     [{"id": "a", "verdict": "drop", "reason": "IP", "note": "캐릭터"},
      {"id": "b", "verdict": "maybe"}]])
check("중복 판정은 drop 우선", ver["a"]["verdict"] == "drop" and ver["a"]["reason"] == "IP", ver.get("a"))
check("형식 불량 verdict 는 drop", ver["b"]["verdict"] == "drop", ver.get("b"))
check("누락 보고", miss == ["c"], miss)
check("환각 보고", extra == ["zz"], extra)

with tempfile.TemporaryDirectory() as d:
    os.makedirs(os.path.join(d, "judged"))
    with open(os.path.join(d, "batches_index.json"), "w") as f:
        json.dump([{"n": 1}, {"n": 2}], f)
    open(os.path.join(d, "judged", "judged_001.json"), "w").write("[]")
    check("pending 은 judged 있는 배치 제외", [b["n"] for b in pending_batches(d)] == [2])

# 2차 같은 타오바오 상품 1회 판정 (2026-10-30)
vs = [{"id": "p1", "tb_item_id": "9"}, {"id": "p2", "tb_item_id": "9"}, {"id": "p3", "tb_item_id": "", "tb_thumb_url": "u"},
      {"id": "p4", "tb_item_id": "", "tb_thumb_url": "u"}, {"id": "p5"}, {"id": "p6"}]
reps, dm = dedupe_views(vs)
check("중복 묶기: itemId·썸네일 키", [v["id"] for v in reps] == ["p1", "p3", "p5", "p6"] and dm == {"p1": ["p2"], "p3": ["p4"]}, (reps, dm))
fin = {"p1": {"verdict": "drop", "reason": "IP", "note": "로고"}}
n = spread_dups(fin, dm)
check("대표 판정 복사(대표 없으면 건너뜀)", n == 1 and fin["p2"]["verdict"] == "drop" and fin["p2"]["dup_of"] == "p1" and "p4" not in fin, fin)
check("to_view 2차에 tb_item_id", to_view({"id": "x", "taobaoResult": [{"item": {"itemId": 123, "image": "//i"}}]}, 2)["tb_item_id"] == "123")

# 중복 제거 단계(dup_verdicts.json)가 있으면 prep 대상에서 뺀다
with tempfile.TemporaryDirectory() as _d:
    with open(os.path.join(_d, "dup_verdicts.json"), "w", encoding="utf-8") as _f:
        json.dump({"b": {"verdict": "drop", "reason": "DUP_SEEN", "note": "장부", "by": "ledger"}}, _f)
    _t = exclude_dups([{"id": "a"}, {"id": "b"}, {"id": "c"}], _d)
    check("dup_verdicts 가 있으면 대상에서 제외", [x["id"] for x in _t] == ["a", "c"], _t)
    check("dup_verdicts 가 없으면 그대로", len(exclude_dups([{"id": "a"}], os.path.join(_d, "none"))) == 1)

print("\nFAILED:", FAILED if FAILED else "없음")
sys.exit(1 if FAILED else 0)
