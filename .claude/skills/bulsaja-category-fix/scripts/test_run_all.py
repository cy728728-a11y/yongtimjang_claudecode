#!/usr/bin/env python3
"""run_all.py 순수 함수 회귀 테스트 (pytest 불필요 — 그냥 실행).

대상: 팬아웃 3종(batch/merge/steer)의 계산부. MCP·시트·셀하는 건드리지 않는다.
    python .claude/skills/bulsaja-category-fix/scripts/test_run_all.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_all import make_batches, merge_named, steer_items  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        FAILED.append(name)


def N(pid, thumb=""):
    return {"productId": pid, "row": 3, "상품명": "가", "원문명": "中",
            "옵션명": ["a"], "썸네일경로": thumb}


# ── make_batches ────────────────────────────────────────────────────────────
def test_batches():
    print("\n[make_batches]")
    names = [N(f"P{i:02d}", thumb=("t.jpg" if i % 2 == 0 else "")) for i in range(10)]
    bs = make_batches(names, size=4, rules="/rules.md")
    check("4건씩 3배치", [len(b["products"]) for b in bs] == [4, 4, 2],
          str([len(b["products"]) for b in bs]))
    check("배치번호 1부터", [b["batch"] for b in bs] == [1, 2, 3])
    check("규칙문서 실림", all(b["규칙문서"] == "/rules.md" for b in bs))
    check("이미지수 계산", [b["이미지수"] for b in bs] == [2, 2, 1],
          str([b["이미지수"] for b in bs]))
    check("상품 필드 보존", bs[0]["products"][0]["원문명"] == "中")

    check("빈 입력은 빈 목록", make_batches([], size=4, rules="/r") == [])
    check("size<1 은 1로 보정", len(make_batches(names[:3], size=0, rules="/r")) == 3)


# ── merge_named ─────────────────────────────────────────────────────────────
def test_merge():
    print("\n[merge_named]")
    named = [
        {"batch": 1, "results": [
            {"productId": "P1", "name": "차량용 유압자키", "실물판정": "자키", "근거": "원문"},
            {"productId": "P2", "상태": "보류(정체불명)", "실물판정": "", "근거": "모순"}]},
        {"batch": 2, "results": [
            {"productId": "P3", "name": "원목 라운지체어", "실물판정": "의자", "근거": "옵션"}]},
    ]
    kw, rep = merge_named(named, expected=["P1", "P2", "P3"])
    check("3건 병합", len(kw) == 3, str(len(kw)))
    check("누락 없음", rep["missing"] == [])
    check("보류 집계", rep["held"] == ["P2"], str(rep["held"]))
    check("생성 집계", rep["named"] == 2, str(rep["named"]))

    # 누락 — 워커가 죽어 배치 2가 안 왔다
    kw2, rep2 = merge_named(named[:1], expected=["P1", "P2", "P3"])
    check("누락 검출", rep2["missing"] == ["P3"], str(rep2["missing"]))

    # 중복 — 재팬아웃으로 같은 상품이 두 번 왔다. 뒤엣것이 이긴다(멱등 덮어쓰기)
    dup = named + [{"batch": 2, "results": [
        {"productId": "P3", "name": "새 검색어", "실물판정": "의자", "근거": "재판정"}]}]
    kw3, rep3 = merge_named(dup, expected=["P1", "P2", "P3"])
    check("중복은 마지막 승", [k for k in kw3 if k["productId"] == "P3"][0]["name"] == "새 검색어")
    check("중복 수 보고", rep3["dups"] == 1, str(rep3["dups"]))

    # 모르는 상품id 는 거부한다 — 워커 환각이 원장에 들어가면 안 된다
    alien = [{"batch": 1, "results": [{"productId": "ZZZ", "name": "x"}]}]
    kw4, rep4 = merge_named(alien, expected=["P1"])
    check("미지의 상품id 거부", kw4 == [] and rep4["unknown"] == ["ZZZ"],
          f"{kw4} {rep4['unknown']}")

    # name 도 상태도 없는 결과 = 불완전 → 보류로 강등(셀하를 태우면 안 된다)
    bad = [{"batch": 1, "results": [{"productId": "P1", "근거": "말만 함"}]}]
    kw5, rep5 = merge_named(bad, expected=["P1"])
    check("빈 결과는 보류로 강등", kw5[0]["상태"] == "보류(정체불명)", str(kw5))


# ── steer_items ─────────────────────────────────────────────────────────────
def D(pid, 상태, row=5, conf="85"):
    return {"productId": pid, "상태": 상태, "row": row, "확신도": conf,
            "상품명": "상품", "기존카테고리": "가>나"}


def M(pid, path="가>나>다", kw="유압자키"):
    return {"productId": pid, "sellha경로": path, "최종차수": kw}


def test_steer():
    print("\n[steer_items]")
    dec = [D("P1", "매칭불가"), D("P2", "부분일치확인요"),
           D("P3", "자동저장완료"), D("P4", "sellha조회실패"),
           D("P5", "매칭불가", conf="55"), D("P6", "보류(정체불명)")]
    mg = [M(p) for p in ("P1", "P2", "P3", "P4", "P5", "P6")]
    items, skipped = steer_items(dec, mg, threshold=70)
    ids = [i["productId"] for i in items]
    check("매칭불가·부분일치만 대상", ids == ["P1", "P2"], str(ids))
    check("확신도 미달은 수동 큐로", "P5" in skipped["확신도미달"], str(skipped))
    check("target=셀하경로", items[0]["target"] == "가>나>다")
    check("seed=최종차수", items[0]["keyword"] == "유압자키")
    check("mode=exact", all(i["mode"] == "exact" for i in items))
    check("row 전달", items[0]["row"] == 5)

    # 셀하 경로가 없으면 유도할 목표가 없다 → 대상 아님
    items2, sk2 = steer_items([D("P1", "매칭불가")], [M("P1", path="")], threshold=70)
    check("경로 없으면 제외", items2 == [] and "P1" in sk2["경로없음"], str(sk2))

    # merged 에 아예 없는 상품(조인 실패)도 제외
    items3, sk3 = steer_items([D("P9", "매칭불가")], [], threshold=70)
    check("조인 실패 제외", items3 == [] and "P9" in sk3["경로없음"], str(sk3))

    # 확신도가 비어 있으면(셀하 미기재) 자동 유도 대상이 아니다
    items4, sk4 = steer_items([D("P1", "매칭불가", conf="")], [M("P1")], threshold=70)
    check("확신도 공란은 수동 큐", items4 == [] and "P1" in sk4["확신도미달"], str(sk4))


if __name__ == "__main__":
    test_batches()
    test_merge()
    test_steer()
    print("\n" + "=" * 52)
    if FAILED:
        print(f"실패 {len(FAILED)}건: {FAILED}")
        sys.exit(1)
    print("전부 통과")
