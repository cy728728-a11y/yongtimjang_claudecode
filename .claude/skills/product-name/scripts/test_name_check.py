#!/usr/bin/env python3
"""name_check.py 회귀 테스트 — R12 재작업 게이트 (stdlib unittest).

실행: python test_name_check.py   (또는 python -m unittest test_name_check -v)

발단 = 2026-08-15 25-2 3회차 표본검수. 전건 27건 중 의심 3건이 **전부 같은 패턴**이었다:
옵션정리·정합검사가 넘긴 `재작업사유` 가 배치에 실려 워커까지 갔는데, 워커가 사유가
지목한 낱말을 상품명에 그대로 남겼다.

  · 사유 "상품명은 '레드'인데 원문 대다수는 녹색"      → `레드` 유지
  · 사유 "원문·옵션 전부 라쳇렌치인데 상품명은 임팩렌치" → `임팩` 유지
  · 사유 "규격 불일치"                                → 규격만 보고 품목 오지칭을 놓침

원인은 워커 지시서가 `재작업사유` 필드를 **언급조차 하지 않은 것**이었다. 지시서에
게이트를 넣었지만(§1-1), 이 스킬의 실측 교훈은 "지시문만으로는 안 막힌다"이므로
기계 쪽에도 R12 를 건다. 사유는 자연어라 지목 낱말을 뽑는 건 불안정하다 — 대신
**게이트를 밟았다는 기록(`재작업반영`)이 있는지**를 본다(100% 판정 가능).

R12 는 경고다(실패 아님). 재팬아웃 비용보다 표본검수 우선순위를 올리는 게 싸다.
"""
import sys
import unittest

for _s in (sys.stdout, sys.stderr):  # 콘솔 cp949 에서 한글 테스트명이 깨지지 않게
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

import name_check  # noqa: E402


def _r12(result):
    return [w for w in result["경고"] if w.startswith("R12")]


def _product(**over):
    """R12 외 규칙을 통과하는 최소 정상 상품 — 여기에 재작업 필드만 얹어 본다."""
    p = {
        "productId": "U01TEST",
        "원본상품명": "전동 라쳇렌치",
        "새상품명": "핸드 전동라쳇렌치 미니 앵글 충전식 기본형",
        "실물판정": "전동 라쳇렌치",
        "키워드1": "전동라쳇렌치",
        "키워드2": "앵글렌치",
        "term분해": ["핸드", "전동라쳇렌치", "미니", "앵글", "충전식", "기본형"],
        "관련어": [{"키워드": "전동라쳇렌치", "상품수": 100, "검색량": 10}],
        "반증": "없음",
    }
    p.update(over)
    return p


class R12Test(unittest.TestCase):
    def test_재작업이_아니면_R12는_아무것도_안_한다(self):
        r = name_check.check_one(_product())
        self.assertEqual(_r12(r), [])

    def test_재작업사유가_있는데_재작업반영이_비면_경고(self):
        r = name_check.check_one(_product(
            재작업사유="원문·옵션 전부 라쳇렌치인데 상품명은 임팩렌치"))
        self.assertTrue(_r12(r), "재작업반영 누락을 못 잡았다")
        self.assertIn("재작업반영", _r12(r)[0])

    def test_재작업반영을_적었으면_경고하지_않는다(self):
        r = name_check.check_one(_product(
            재작업사유="원문·옵션 전부 라쳇렌치인데 상품명은 임팩렌치",
            재작업반영="'임팩' 제거 → '라쳇렌치'로 교체(원문 电动棘轮扳手)"))
        self.assertEqual(_r12(r), [])

    def test_공백만_적은_재작업반영은_안_적은_것이다(self):
        r = name_check.check_one(_product(
            재작업사유="사유 있음", 재작업반영="   "))
        self.assertTrue(_r12(r))

    def test_사유가_따옴표로_지목한_낱말이_남으면_추가_경고(self):
        # 실측 재현 — 3회차 의심 건(라쳇렌치)
        r = name_check.check_one(_product(
            새상품명="핸드 전동라쳇렌치 미니 무선임팩렌치 앵글 기본형",
            term분해=["핸드", "전동라쳇렌치", "미니", "무선임팩렌치", "앵글", "기본형"],
            재작업사유="원문·옵션 전부 라쳇렌치인데 상품명은 '임팩'렌치"))
        ws = _r12(r)
        self.assertEqual(len(ws), 2, f"지목 낱말 잔존 경고가 없다: {ws}")
        self.assertIn("임팩", ws[1])

    def test_지목_낱말을_뺐으면_잔존_경고는_없다(self):
        # 실측 재현 — 3회차 의심 건(레이저레벨기)을 제대로 처리한 형태
        r = name_check.check_one(_product(
            새상품명="수평계 녹색 전자식레이저레벨기 고정밀 바닥 기본형",
            키워드1="레이저레벨기", 키워드2="전자식수평계",
            term분해=["수평계", "녹색", "전자식레이저레벨기", "고정밀", "바닥", "기본형"],
            관련어=[{"키워드": "레이저레벨기", "상품수": 100, "검색량": 10}],
            재작업사유="상품명은 '레드'인데 원문 대다수는 녹색",
            재작업반영="'레드' 제거 → '녹색'(옵션 11행 중 7행)"))
        self.assertEqual(_r12(r), [])

    def test_곡선_따옴표도_인식한다(self):
        r = name_check.check_one(_product(
            새상품명="핸드 전동라쳇렌치 미니 무선임팩렌치 앵글 기본형",
            term분해=["핸드", "전동라쳇렌치", "미니", "무선임팩렌치", "앵글", "기본형"],
            재작업사유="상품명은 “임팩”렌치인데 원문은 라쳇렌치"))
        self.assertEqual(len(_r12(r)), 2)

    def test_R12는_경고일뿐_통과를_막지_않는다(self):
        r = name_check.check_one(_product(재작업사유="사유 있음"))
        self.assertTrue(r["통과"], "R12 가 실패로 격상되면 재팬아웃 비용이 든다")

    def test_지목_낱말이_상품명에_없으면_잔존_경고는_안_뜬다(self):
        r = name_check.check_one(_product(재작업사유="상품명은 '임팩'인데 실제는 라쳇"))
        ws = _r12(r)
        self.assertEqual(len(ws), 1, f"잔존 경고가 잘못 떴다: {ws}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
