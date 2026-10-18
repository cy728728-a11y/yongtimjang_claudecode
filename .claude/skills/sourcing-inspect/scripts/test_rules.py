#!/usr/bin/env python3
"""rules.py 회귀 테스트 (pytest 불필요 — 그냥 실행).
    .venv/bin/python3 .claude/skills/sourcing-inspect/scripts/test_rules.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rules import load_banned_cats, load_keywords, machine_judge  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'} {name} {'' if cond else detail}")
    if not cond:
        FAILED.append(name)


cats = load_banned_cats()
kws = load_keywords()
check("금지 카테고리 3290개 로드", len(cats) == 3290, len(cats))

r = machine_judge({"catId": "50000979", "productName": "x"}, 1, cats, kws)
check("문자열 catId 금지", r and r["reason"] == "BANNED_CAT", r)
r = machine_judge({"catId": 50000979, "productName": "x"}, 1, cats, kws)
check("정수 catId 도 금지", r and r["reason"] == "BANNED_CAT", r)
r = machine_judge({"catId": "1", "productName": "레고 호환 블럭"}, 1, cats, kws)
check("키워드 IP", r and r["reason"] == "KEYWORD_IP", r)
r = machine_judge({"catId": "1", "productName": "말안장의자 미용 안장 검정"}, 1, cats, kws)
check("단어 경계 넘는 오탐 없음(안장 검정≠장검)", r is None, r)
r = machine_judge({"catId": "1", "productName": "전동 호이스트", "sellerTags": ["레고"]}, 1, cats, kws)
check("판매자 태그는 키워드 판정에 안 씀", r is None, r)
r = machine_judge({"catId": "1", "productName": "드라이버",
                   "taobao_match_status": "match_failed", "taobaoResult": []}, 2, cats, kws)
check("2차 매칭실패", r and r["reason"] == "NO_MATCH", r)
r = machine_judge({"catId": "1", "productName": "드라이버", "taobaoResult": []}, 2, cats, kws)
check("2차 매칭결과 빈 배열", r and r["reason"] == "NO_MATCH", r)
r = machine_judge({"catId": "1", "productName": "드라이버",
                   "taobaoResult": [{"item": {"title": "乐高 레고"}}]}, 2, cats, kws)
check("2차 타오바오 제목 키워드", r and r["reason"] == "KEYWORD_IP", r)
r = machine_judge({"catId": "1", "productName": "레고 블럭",
                   "taobaoResult": [{"item": {"title": "螺丝刀"}}]}, 2, cats, kws)
check("2차는 네이버 상품명으로 안 자름", r is None, r)
r = machine_judge({"catId": "1", "productName": "x",
                   "taobaoResult": [{"item": {"title": "레고"}}]}, 2, cats, kws)
check("2차 타오바오 제목 키워드", r and r["reason"] == "KEYWORD_IP", r)
r = machine_judge({"catId": "1", "productName": "드라이버 세트", "sellerTags": ["공구"]}, 1, cats, kws)
check("일반 상품은 None", r is None, r)
r = machine_judge({"catId": None, "productName": None, "sellerTags": None}, 1, cats, kws)
check("빈 필드도 안 죽음", r is None, r)

from rules import max_watt  # noqa: E402
check("와트 3000W", max_watt("고출력 3000W 히터") == 3000)
check("와트 3kW", max_watt("산업용 3.5kw 모터") == 3500)
check("와트 콤마", max_watt("3,000W 열풍기") == 3000)
check("와트 Wh 는 아님", max_watt("파워뱅크 5000Wh") == 0)
check("와트 모델코드 아님", max_watt("AW3000 펌프") == 0)
r = machine_judge({"catId": "1", "productName": "업소용 인덕션 3500W"}, 1, cats, kws)
check("3000W 이상 탈락", r and r["reason"] == "WATT", r)
r = machine_judge({"catId": "1", "productName": "전기 그릴 2000W"}, 1, cats, kws)
check("3000W 미만 통과", r is None, r)
r = machine_judge({"catId": "1", "productName": "전기 그릴",
                   "taobaoResult": [{"item": {"title": "商用 5000W 电炉"}}]}, 2, cats, kws)
check("2차 타오바오 제목 와트", r and r["reason"] == "WATT", r)

print("\nFAILED:", FAILED if FAILED else "없음")
sys.exit(1 if FAILED else 0)
