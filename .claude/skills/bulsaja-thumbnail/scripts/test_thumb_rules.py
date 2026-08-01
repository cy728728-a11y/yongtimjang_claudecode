#!/usr/bin/env python3
"""썸네일 규칙 회귀 테스트 — 불사자·시트 없이 돈다.

    python .claude/skills/bulsaja-thumbnail/scripts/test_thumb_rules.py

호스트 판별은 캘리브레이션 실측 URL(2026-07-28)을 그대로 박제한다 — 규칙이 바뀌면
여기가 제일 먼저 깨져야 한다.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import thumb_rules as R  # noqa: E402

# 실측 URL (이번 세션 캘리브레이션)
ORIGINAL = "https://img.alicdn.com/bao/uploaded/i4/1103720702/O1CN01rkWiY61H3Z3SiKTjv_!!4611686018427384062-0-item_pic.jpg"
PROCESSED_MCP_ASSETS = "https://cdn.bulsaja.com/mcp-assets/11154/U01KY54HA4RRXCG02TS120GRM32/thumbnail/7754d2013cfe074ca963b56b7cc3e52f453fb77a4"
PROCESSED_SOURCING = "https://cdn.bulsaja.com/sourcing-product/images/U01KPZYXXRECAVR0Z8K2ZD1AVKA/thumbnail-image/1SOeYCF2t7yRqTu.jpeg"
PROCESSED_PRODUCTS = "https://cdn.bulsaja.com/products/U01K10FF4B2A12D71K0DXKAPEX1/a73962d2-713e-4544-8da2-640a3ffd4f1d.jpg"
PROCESSED_AI_OUTPUT = "https://cdn.bulsaja.com/ai-image/output/11154/5c1d2bfc464f8192c726e688c5e8e4c948da6cc3fb4acad315e32769e68c72f4-ef077f993beae00afa43d53b67fd0472451808a626afbc7c4ad5cd2b419cf9e1.jpg"


class HostTest(unittest.TestCase):
    def test_원본_호스트는_미가공(self):
        self.assertFalse(R.is_processed_url(ORIGINAL))
        self.assertEqual(R.host_of(ORIGINAL), "img.alicdn.com")

    def test_가공_경로_4종_전부_가공됨(self):
        for url in (PROCESSED_MCP_ASSETS, PROCESSED_SOURCING,
                    PROCESSED_PRODUCTS, PROCESSED_AI_OUTPUT):
            self.assertTrue(R.is_processed_url(url), url)
            self.assertEqual(R.host_of(url), "cdn.bulsaja.com")

    def test_빈_URL은_미가공(self):
        self.assertFalse(R.is_processed_url(""))
        self.assertFalse(R.is_processed_url(None))


class ProductStatusTest(unittest.TestCase):
    def test_대표가_가공물이면_가공됨(self):
        self.assertEqual(R.product_status([PROCESSED_MCP_ASSETS, ORIGINAL]), "가공됨")

    def test_대표가_원본이면_미가공(self):
        self.assertEqual(R.product_status([ORIGINAL, ORIGINAL]), "미가공")

    def test_후보에_가공물_있어도_대표가_원본이면_미가공(self):
        # 실측: products/<다른pid> 패턴이 후보 자리(1번 이후)에 섞여 등장한 사례가 있었다.
        # 판별은 항상 0번(대표)만 본다.
        self.assertEqual(R.product_status([ORIGINAL, PROCESSED_PRODUCTS]), "미가공")

    def test_빈_목록은_미확인(self):
        self.assertEqual(R.product_status([]), "미확인")

    def test_is_already_done_은_product_status_과_일치(self):
        self.assertTrue(R.is_already_done([PROCESSED_SOURCING, ORIGINAL]))
        self.assertFalse(R.is_already_done([ORIGINAL, ORIGINAL]))


class CreditTest(unittest.TestCase):
    def test_장당_5크레딧(self):
        self.assertEqual(R.credit_estimate(1), 5)
        self.assertEqual(R.credit_estimate(10), 50)

    def test_커스텀_단가(self):
        self.assertEqual(R.credit_estimate(2, per_image=10), 20)


class AutoReflectTest(unittest.TestCase):
    """파일럿 실측(2026-07-28, U01KYMCESDCMAMKNE9RAMYP8Z49)에서 확인된 자동반영 감지."""

    def test_생성_전후_대표가_바뀌면_감지한다(self):
        before = [ORIGINAL, ORIGINAL, ORIGINAL]
        after = [PROCESSED_AI_OUTPUT, ORIGINAL, ORIGINAL, ORIGINAL]
        self.assertTrue(R.representative_changed(before, after))

    def test_대표가_그대로면_감지하지_않는다(self):
        before = [ORIGINAL, ORIGINAL]
        after = [ORIGINAL, ORIGINAL]
        self.assertFalse(R.representative_changed(before, after))

    def test_둘_다_비어있으면_변화_없음(self):
        self.assertFalse(R.representative_changed([], []))

    def test_생성_전이_비어있으면_변화로_본다(self):
        self.assertTrue(R.representative_changed([], [PROCESSED_AI_OUTPUT]))


class RegenTest(unittest.TestCase):
    def test_기본_상한_2회(self):
        self.assertTrue(R.can_regenerate(0))
        self.assertTrue(R.can_regenerate(1))
        self.assertFalse(R.can_regenerate(2))

    def test_커스텀_상한(self):
        self.assertTrue(R.can_regenerate(2, max_regen=3))
        self.assertFalse(R.can_regenerate(3, max_regen=3))


class ReviewRowTest(unittest.TestCase):
    def test_기본_필드_구성(self):
        row = R.review_row("U01K...", "바체어", ORIGINAL, [ORIGINAL, ORIGINAL],
                            generated_url=PROCESSED_AI_OUTPUT, verdict="사용가능",
                            reason="색상 일치 확인")
        self.assertEqual(row["productId"], "U01K...")
        self.assertEqual(row["기존대표"], ORIGINAL)
        self.assertEqual(len(row["후보"]), 2)
        self.assertEqual(row["판정"], "사용가능")

    def test_판정_대기중이면_None(self):
        row = R.review_row("pid", "이름", ORIGINAL, [])
        self.assertIsNone(row["판정"])

    def test_후보_기본값은_빈_리스트(self):
        row = R.review_row("pid", "이름", ORIGINAL, None)
        self.assertEqual(row["후보"], [])


class RedoReasonTest(unittest.TestCase):
    def test_현황판_재작업_문구에서_사유만_뽑는다(self):
        v = "재작업(썸네일: 대표 썸네일이 검정인데 옵션에 검정 없음(호두색/원목색뿐))"
        self.assertEqual(
            R.redo_reason_from_flag(v),
            "대표 썸네일이 검정인데 옵션에 검정 없음(호두색/원목색뿐)")

    def test_형식이_다르면_원문_그대로(self):
        self.assertEqual(R.redo_reason_from_flag("완료"), "완료")
        self.assertEqual(R.redo_reason_from_flag(""), "")


def _opt(rows):
    return {"차원": [], "판매행": rows, "vid고유": True}


def _row(rid, main=False, text="", url=""):
    return {"id": rid, "text": text or f"opt{rid}", "sale_price": 1000,
            "stock": 5, "exclude": False, "main_product": main, "urlRef": url}


class MainOptionTest(unittest.TestCase):
    """썸네일 = 대표옵션 = 상품명 정합 (2026-07-30 이룸님).

    썸네일은 글자가 없어 `기본형` 마커를 쓸 수 없다 — 대표옵션 이미지를 기준으로 못박는다.
    """

    def test_대표옵션의_이름과_이미지를_뽑는다(self):
        o = _opt([_row("1", main=True, text="3톤 기본형", url="https://a/3t.jpg"),
                  _row("2", text="10톤", url="https://a/10t.jpg")])
        self.assertEqual(R.main_option_of(o),
                         {"이름": "3톤 기본형", "이미지": "https://a/3t.jpg"})

    def test_대표가_없으면_None이다(self):
        # 옵션정리를 안 거친 상품 → 호출부가 종전 비전 판단으로 폴백한다
        self.assertIsNone(R.main_option_of(_opt([_row("1"), _row("2")])))

    def test_옵션이_없으면_None이다(self):
        self.assertIsNone(R.main_option_of({}))
        self.assertIsNone(R.main_option_of(None))

    def test_이미지가_비어도_이름은_넘긴다(self):
        # 이름만으로도 검수 화면에서 대조할 수 있다(이미지 없으면 기준 고정만 못 한다)
        o = _opt([_row("1", main=True, text="블랙 기본형", url="")])
        self.assertEqual(R.main_option_of(o), {"이름": "블랙 기본형", "이미지": ""})

    def test_review_row가_대표옵션을_실어_보낸다(self):
        r = R.review_row("U01", "바체어", "https://a/rep.jpg", ["https://a/c1.jpg"],
                         main_option={"이름": "원목 기본형", "이미지": "https://a/m.jpg"})
        self.assertEqual(r["대표옵션명"], "원목 기본형")
        self.assertEqual(r["대표옵션이미지"], "https://a/m.jpg")

    def test_review_row는_대표옵션이_없어도_빈값으로_돈다(self):
        r = R.review_row("U01", "바체어", "https://a/rep.jpg", [])
        self.assertEqual(r["대표옵션명"], "")
        self.assertEqual(r["대표옵션이미지"], "")


if __name__ == "__main__":
    unittest.main()
