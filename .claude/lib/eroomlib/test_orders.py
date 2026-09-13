#!/usr/bin/env python3
"""orders.py 순수 로직 테스트 — 네트워크 0.

실측 헤더(2025 01 ~ 2026 09, 21개 탭)에서 뽑은 실제 문자열을 그대로 쓴다.
헤더가 월마다 달라서(47~67열) 여기서 깨지면 집계가 통째로 어긋난다.
"""
import unittest

from eroomlib import orders


class TestNormAndHeader(unittest.TestCase):
    def test_norm_removes_all_whitespace(self):
        self.assertEqual(orders.norm_header("  판매자 상품 코드 "), "판매자상품코드")
        self.assertEqual(orders.norm_header("A+B+C+D\n지출계"), "A+B+C+D지출계")
        self.assertEqual(orders.norm_header("마켓\n주문번호"), "마켓주문번호")

    def test_exact_match_beats_substring(self):
        """'배송비' 는 7개 열에 부분일치한다 — 정확일치(I열)가 이겨야 한다."""
        hdr = ["", "", "", "", "", "사업자명의", "결제통화", " 타오/알리 결제액",
               " 배송비", "마진율", "통관번호 명의", "배대지"]
        m = orders.header_map(hdr)
        self.assertEqual(m["배송비"], 8)          # I열
        self.assertNotEqual(m.get("배송비"), 11)  # 배대지 아님

    def test_substring_fallback_when_no_exact(self):
        """'지출계' 는 정확일치가 없다 — 'A+B+C+D지출계' 로 떨어져야 한다."""
        hdr = ["이익", "A+B+C+D\n지출계", "마진률"]
        m = orders.header_map(hdr, fields=("이익", "지출계", "마진률"))
        self.assertEqual(m["지출계"], 1)
        self.assertEqual(m["이익"], 0)

    def test_profit_exact_not_confused_with_pre_fee_profit(self):
        hdr = ["수수료\n차감전\n이익", "이익", "마진률"]
        m = orders.header_map(hdr)
        self.assertEqual(m["이익"], 1)

    def test_missing_column_is_absent(self):
        """2025 01~09 탭에는 판매자상품코드 열이 아예 없다."""
        hdr = ["배대지", "판매처", "상품명"]
        m = orders.header_map(hdr)
        self.assertIsNone(m.get("판매자상품코드"))
        self.assertEqual(m["판매처"], 1)

    def test_col_letter(self):
        self.assertEqual(orders.col_letter(0), "A")
        self.assertEqual(orders.col_letter(17), "R")
        self.assertEqual(orders.col_letter(25), "Z")
        self.assertEqual(orders.col_letter(26), "AA")
        self.assertEqual(orders.col_letter(50), "AY")


class TestParsers(unittest.TestCase):
    def test_parse_money(self):
        self.assertEqual(orders.parse_money("16,161"), 16161.0)
        self.assertEqual(orders.parse_money("  23,008 "), 23008.0)
        self.assertEqual(orders.parse_money("116.66"), 116.66)

    def test_parse_money_missing_is_none(self):
        """결측은 빈칸이 아니라 '  - ' 로 들어온다."""
        for s in ("  - ", "-", "", "   ", None, "입력하기"):
            self.assertIsNone(orders.parse_money(s), f"{s!r} 는 None 이어야 한다")

    def test_parse_money_negative(self):
        self.assertEqual(orders.parse_money("-3,500"), -3500.0)
        self.assertEqual(orders.parse_money("(3,500)"), -3500.0)

    def test_parse_pct(self):
        self.assertEqual(orders.parse_pct("18%"), 18.0)
        self.assertEqual(orders.parse_pct("7%"), 7.0)
        self.assertEqual(orders.parse_pct("0.18"), 18.0)   # 소수 표기는 %로 환산
        self.assertIsNone(orders.parse_pct("  - "))

    def test_code_kind(self):
        self.assertEqual(orders.code_kind("ngIwHbNzOYSXDmlxeGBl1"), "bulsaja")
        self.assertEqual(orders.code_kind("PTk/PT0/ODtHcWVuanV3Mw=="), "other")
        self.assertEqual(orders.code_kind(""), "none")
        self.assertEqual(orders.code_kind("  "), "none")

    def test_market_group_of(self):
        self.assertEqual(orders.market_group_of("스마트스토어(20-1)"), "20번_용쌤20-1")
        self.assertEqual(orders.market_group_of("스마트스토어(13-2)"), "13번_용쌤13-2")
        self.assertIsNone(orders.market_group_of("쿠팡"))
        self.assertIsNone(orders.market_group_of(""))

    def test_market_number_of(self):
        self.assertEqual(orders.market_number_of("스마트스토어(13-2)"), "13-2")
        self.assertIsNone(orders.market_number_of("쿠팡"))


class TestAggregate(unittest.TestCase):
    def rows(self):
        return [
            # 같은 코드 2건 — 가중마진이 산술평균과 달라야 한다
            {"판매자상품코드": "AAAAAAAAAAAAAAAAAAAAA", "판매처": "스마트스토어(20-1)",
             "상품명": "옷걸이", "수량": "1", "결제금액": "10,000", "이익": "5,000",
             "마진률": "50%", "마켓수수료율": "7%", "배송비": "3,000",
             "주문일자": "2026-09-01 06:30", "사업자명의": "최용"},
            {"판매자상품코드": "AAAAAAAAAAAAAAAAAAAAA", "판매처": "스마트스토어(20-1)",
             "상품명": "옷걸이", "수량": "2", "결제금액": "90,000", "이익": "9,000",
             "마진률": "10%", "마켓수수료율": "7%", "배송비": "12,000",
             "주문일자": "2026-09-05 06:30", "사업자명의": "최용"},
            # 마진 결측 행 — 매출엔 남고 유효행에선 빠진다
            {"판매자상품코드": "AAAAAAAAAAAAAAAAAAAAA", "판매처": "스마트스토어(20-1)",
             "상품명": "옷걸이", "수량": "1", "결제금액": "20,000", "이익": "  - ",
             "마진률": "  - ", "마켓수수료율": "", "배송비": "  - ",
             "주문일자": "2026-09-07 06:30", "사업자명의": "최용"},
            # 불사자 코드가 아닌 행 — 집계에서 빠진다
            {"판매자상품코드": "PTk/PT0/ODtHcWVuanV3Mw==", "판매처": "스마트스토어(17-2)",
             "상품명": "캐노피", "수량": "1", "결제금액": "50,000", "이익": "5,000",
             "마진률": "10%", "마켓수수료율": "7%", "배송비": "5,000",
             "주문일자": "2026-09-02 06:30", "사업자명의": "최용"},
        ]

    def test_weighted_margin_not_arithmetic_mean(self):
        st = orders.aggregate(self.rows())
        rec = st["AAAAAAAAAAAAAAAAAAAAA"]
        # 가중: (5000+9000)/(10000+90000) = 14%   산술평균이면 (50+10)/2 = 30%
        self.assertAlmostEqual(rec["가중마진"], 14.0, places=4)
        self.assertNotAlmostEqual(rec["가중마진"], 30.0, places=1)

    def test_counts_and_revenue_include_missing_margin_rows(self):
        rec = orders.aggregate(self.rows())["AAAAAAAAAAAAAAAAAAAAA"]
        self.assertEqual(rec["주문수"], 3)        # 결측행도 실적은 실적
        self.assertEqual(rec["매출"], 120000.0)   # 10000+90000+20000
        self.assertEqual(rec["유효행수"], 2)      # 마진 계산에 쓴 행만

    def test_min_margin_and_loss_count(self):
        rec = orders.aggregate(self.rows())["AAAAAAAAAAAAAAAAAAAAA"]
        self.assertEqual(rec["최소마진"], 10.0)
        self.assertEqual(rec["적자건수"], 0)

    def test_non_bulsaja_code_excluded(self):
        st = orders.aggregate(self.rows())
        self.assertNotIn("PTk/PT0/ODtHcWVuanV3Mw==", st)
        self.assertEqual(len(st), 1)

    def test_shipping_is_per_unit_normalized(self):
        """배송비는 수량으로 나눠 단위당으로 정규화한다 — 2개 주문의 12,000 은 6,000."""
        rec = orders.aggregate(self.rows())["AAAAAAAAAAAAAAAAAAAAA"]
        self.assertEqual(sorted(rec["배송비단위"]), [3000.0, 6000.0])

    def test_market_groups_collected(self):
        rec = orders.aggregate(self.rows())["AAAAAAAAAAAAAAAAAAAAA"]
        self.assertEqual(rec["마켓그룹"], {"20-1": 3})

    def test_empty_rows(self):
        self.assertEqual(orders.aggregate([]), {})

    def test_all_margin_missing_gives_none(self):
        rows = [{"판매자상품코드": "B" * 21, "판매처": "스마트스토어(1-1)",
                 "상품명": "x", "수량": "1", "결제금액": "10,000",
                 "이익": "  - ", "마진률": "  - ", "마켓수수료율": "",
                 "배송비": "  - ", "주문일자": "", "사업자명의": ""}]
        rec = orders.aggregate(rows)["B" * 21]
        self.assertIsNone(rec["가중마진"])
        self.assertEqual(rec["유효행수"], 0)


class TestShippingQuantile(unittest.TestCase):
    def test_p75_picks_conservative_value(self):
        self.assertEqual(orders.p75([1000, 2000, 3000, 4000]), 3250.0)

    def test_p75_single_value(self):
        self.assertEqual(orders.p75([5000]), 5000.0)

    def test_p75_empty(self):
        self.assertIsNone(orders.p75([]))

    def test_spread_pct(self):
        self.assertAlmostEqual(orders.spread_pct([1000, 2000]), 100.0)
        self.assertEqual(orders.spread_pct([1000]), 0.0)
        self.assertIsNone(orders.spread_pct([]))


class TestMonthTabs(unittest.TestCase):
    def test_filters_and_sorts(self):
        tabs = ["월별신용카드Dashboard", "2026 09", "Summary_2025", "2025 10",
                "시트7", "2026 08 정인호", "2026 01", "메모"]
        self.assertEqual(orders.month_tab_names(tabs),
                         ["2025 10", "2026 01", "2026 09"])

    def test_excludes_suffixed_tabs(self):
        """'2026 08 정인호' 는 별도 탭이다 — 본 탭과 중복 집계하면 안 된다."""
        self.assertEqual(orders.month_tab_names(["2026 08 정인호"]), [])


if __name__ == "__main__":
    unittest.main()
