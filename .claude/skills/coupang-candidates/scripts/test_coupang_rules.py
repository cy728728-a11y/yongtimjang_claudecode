#!/usr/bin/env python3
"""coupang_rules.py 테스트 — 네트워크 0, LLM 0. 전부 계산이다."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coupang_rules as R


class TestCoupangFee(unittest.TestCase):
    def test_known_category_matches_by_prefix(self):
        self.assertEqual(R.coupang_fee("가구/인테리어 > 책장 > 일반책장"), 10.8)

    def test_unknown_category_is_conservative_max(self):
        """모르는 카테고리는 최고율로 잡는다 — 게이트가 낙관하면 안 된다."""
        self.assertEqual(R.coupang_fee("듣도보도못한 > 카테고리"), R.MAX_FEE)
        self.assertEqual(R.coupang_fee(""), R.MAX_FEE)
        self.assertEqual(R.coupang_fee(None), R.MAX_FEE)

    def test_longest_prefix_wins(self):
        """더 구체적인 경로가 이긴다."""
        table = {"디지털/가전": 5.0, "디지털/가전 > 계절가전": 8.0}
        self.assertEqual(R.coupang_fee("디지털/가전 > 계절가전 > 선풍기", table), 8.0)
        self.assertEqual(R.coupang_fee("디지털/가전 > 음향기기", table), 5.0)


class TestAdjustMargin(unittest.TestCase):
    def test_coupang_fee_higher_lowers_margin(self):
        # 가중마진 30%, 쿠팡 10.8%, 스마트스토어 7% → 30 - 3.8 = 26.2
        self.assertAlmostEqual(R.adjust_margin(30.0, 10.8, 7.0), 26.2, places=4)

    def test_coupang_fee_lower_raises_margin(self):
        self.assertAlmostEqual(R.adjust_margin(30.0, 5.0, 7.0), 32.0, places=4)

    def test_missing_ss_fee_uses_default(self):
        """마켓수수료율 결측이면 실측 기본값 7% 를 쓴다."""
        self.assertAlmostEqual(R.adjust_margin(30.0, 10.8, None), 26.2, places=4)

    def test_none_margin_stays_none(self):
        self.assertIsNone(R.adjust_margin(None, 10.8, 7.0))


class TestGate(unittest.TestCase):
    def rec(self, **kw):
        base = {"판매자상품코드": "A" * 21, "주문수": 5, "가중마진": 30.0,
                "유효행수": 5, "카테고리": "가구/인테리어 > 책장"}
        base.update(kw)
        return base

    def test_pass_when_above_threshold(self):
        ok, why = R.passes(self.rec(), min_margin=15.0, min_orders=3)
        self.assertTrue(ok, why)

    def test_reject_below_margin(self):
        ok, why = R.passes(self.rec(가중마진=12.0), min_margin=15.0, min_orders=3)
        self.assertFalse(ok)
        self.assertIn("마진미달", why)

    def test_reject_below_order_cut(self):
        ok, why = R.passes(self.rec(주문수=2), min_margin=15.0, min_orders=3)
        self.assertFalse(ok)
        self.assertIn("주문수부족", why)

    def test_missing_margin_fails_closed(self):
        """마진을 모르는 건 통과시키지 않는다 — 게이트의 존재 이유가 손실 차단이다."""
        ok, why = R.passes(self.rec(가중마진=None, 유효행수=0), min_margin=15.0, min_orders=3)
        self.assertFalse(ok)
        self.assertIn("마진미상", why)

    def test_boundary_is_inclusive(self):
        rec = self.rec(가중마진=R.MAX_FEE - 7.0 + 15.0)  # 보정 후 정확히 15.0
        ok, why = R.passes(rec, min_margin=15.0, min_orders=3, category_fee=R.MAX_FEE)
        self.assertTrue(ok, why)


class TestChooseTopSeller(unittest.TestCase):
    def insts(self):
        return [
            # 판매 실적 없지만 가공은 많이 된 사본
            {"productId": "P_polished", "상태": "업로드 완료", "잠금": False,
             "그룹명": "1번_용쌤1-1", "주문수": 0, "매출": 0.0},
            # 실제로 팔린 사본 — 잠금이 걸려 있다
            {"productId": "P_seller", "상태": "업로드 완료", "잠금": True,
             "그룹명": "20번_용쌤20-1", "주문수": 33, "매출": 1_500_000.0},
            # 업로드 실패 사본
            {"productId": "P_failed", "상태": "업로드 실패", "잠금": False,
             "그룹명": "9번_용쌤9-1", "주문수": 0, "매출": 0.0},
        ]

    def test_picks_actual_seller_not_most_polished(self):
        done = {"P_polished": 8, "P_seller": 2, "P_failed": 0}
        rep = R.choose_top_seller(self.insts(), done_counts=done)
        self.assertEqual(rep["productId"], "P_seller")

    def test_excludes_abnormal_status(self):
        insts = [{"productId": "X", "상태": "판매중지", "잠금": False,
                  "그룹명": "g", "주문수": 99, "매출": 1.0}]
        self.assertIsNone(R.choose_top_seller(insts))

    def test_excludes_target_group_copies(self):
        """이미 쿠팡 그룹에 있는 사본은 대표가 될 수 없다."""
        insts = [{"productId": "C", "상태": "수집됨", "잠금": False,
                  "그룹명": "1번_용쌤쿠팡cy1728", "주문수": 5, "매출": 100.0}]
        self.assertIsNone(R.choose_top_seller(insts, exclude_groups={"1번_용쌤쿠팡cy1728"}))

    def test_done_counts_breaks_tie_when_no_sales(self):
        insts = [
            {"productId": "A", "상태": "수집됨", "잠금": False, "그룹명": "g1",
             "주문수": 0, "매출": 0.0},
            {"productId": "B", "상태": "수집됨", "잠금": False, "그룹명": "g2",
             "주문수": 0, "매출": 0.0},
        ]
        rep = R.choose_top_seller(insts, done_counts={"A": 1, "B": 7})
        self.assertEqual(rep["productId"], "B")

    def test_lock_breaks_tie_after_done_counts(self):
        insts = [
            {"productId": "A", "상태": "수집됨", "잠금": False, "그룹명": "g1",
             "주문수": 0, "매출": 0.0},
            {"productId": "B", "상태": "수집됨", "잠금": True, "그룹명": "g2",
             "주문수": 0, "매출": 0.0},
        ]
        rep = R.choose_top_seller(insts, done_counts={"A": 0, "B": 0})
        self.assertEqual(rep["productId"], "B")

    def test_deterministic_on_full_tie(self):
        insts = [
            {"productId": "Z", "상태": "수집됨", "잠금": False, "그룹명": "g2",
             "주문수": 0, "매출": 0.0},
            {"productId": "A", "상태": "수집됨", "잠금": False, "그룹명": "g1",
             "주문수": 0, "매출": 0.0},
        ]
        a = R.choose_top_seller(list(insts))
        b = R.choose_top_seller(list(reversed(insts)))
        self.assertEqual(a["productId"], b["productId"])

    def test_empty(self):
        self.assertIsNone(R.choose_top_seller([]))


class TestShippingDiff(unittest.TestCase):
    def test_flags_underpriced(self):
        d = R.shipping_diff(실측P75=30000, 불사자현재=12000)
        self.assertEqual(d["차액"], 18000)
        self.assertTrue(d["교정필요"])
        self.assertEqual(d["방향"], "인상")

    def test_within_tolerance_no_action(self):
        d = R.shipping_diff(실측P75=12500, 불사자현재=12000, tolerance_pct=10.0)
        self.assertFalse(d["교정필요"])

    def test_unknown_current_needs_check(self):
        d = R.shipping_diff(실측P75=30000, 불사자현재=None)
        self.assertTrue(d["교정필요"])
        self.assertEqual(d["방향"], "미상")

    def test_no_measurement_no_action(self):
        d = R.shipping_diff(실측P75=None, 불사자현재=12000)
        self.assertFalse(d["교정필요"])


class TestDedupeByBulsajaCode(unittest.TestCase):
    def test_groups_copies_under_one_code(self):
        resolved = {
            "codeA": {"productId": "P1", "불사자코드": "SHARED", "상태": "업로드 완료",
                      "잠금": True, "그룹": "20번_용쌤20-1"},
            "codeB": {"productId": "P2", "불사자코드": "SHARED", "상태": "업로드 실패",
                      "잠금": False, "그룹": "9번_용쌤9-1"},
            "codeC": {"productId": "P3", "불사자코드": "OTHER", "상태": "업로드 완료",
                      "잠금": True, "그룹": "1번_용쌤1-1"},
        }
        sales = {"codeA": {"주문수": 10, "매출": 100.0},
                 "codeB": {"주문수": 1, "매출": 10.0},
                 "codeC": {"주문수": 5, "매출": 50.0}}
        groups = R.group_by_bulsaja_code(resolved, sales)
        self.assertEqual(len(groups), 2)
        shared = groups["SHARED"]
        self.assertEqual(shared["합산주문수"], 11)
        self.assertEqual(len(shared["사본"]), 2)

    def test_missing_bulsaja_code_stays_solo(self):
        resolved = {"c1": {"productId": "P1", "불사자코드": "", "상태": "수집됨",
                           "잠금": False, "그룹": None}}
        groups = R.group_by_bulsaja_code(resolved, {"c1": {"주문수": 1, "매출": 1.0}})
        self.assertEqual(len(groups), 1)
        self.assertTrue(list(groups)[0].startswith("solo:"))


if __name__ == "__main__":
    unittest.main()
