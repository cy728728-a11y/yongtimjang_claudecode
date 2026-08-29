#!/usr/bin/env python3
"""AD_CONVERSION 리포트 파싱 회귀 테스트 — 네트워크 없이 돈다."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reports  # noqa: E402

# 2026-08-25 cy728 실제 응답 2행 (탭 구분, 13열)
REAL = (
    "20260825\t4158478\tcmp-a001-02-000000009889842\tgrp-a001-02-000000056901303\t-\t"
    "nad-a001-02-000000487628566\tbsn-a001-00-000000012981745\t623353\tM\t1\tadd_to_cart\t1\t218600\n"
    "20260825\t4158478\tcmp-a001-02-000000009889842\tgrp-a001-02-000000056901104\t-\t"
    "nad-a001-02-000000501855520\tbsn-a001-00-000000012981702\t644590\tM\t1\tpurchase\t1\t233900\n"
)


class TestParse(unittest.TestCase):
    def test_전환유형과_금액을_뽑는다(self):
        rows = reports.parse_conversion_tsv(REAL)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["convType"], "add_to_cart")
        self.assertEqual(rows[1]["convType"], "purchase")
        self.assertEqual(rows[1]["adId"], "nad-a001-02-000000501855520")
        self.assertEqual(rows[1]["cnt"], 1)
        self.assertEqual(rows[1]["amt"], 233900)

    def test_짧은_행은_버린다(self):
        self.assertEqual(reports.parse_conversion_tsv("a\tb\tc\n"), [])

    def test_빈_문자열은_빈_리스트다(self):
        self.assertEqual(reports.parse_conversion_tsv(""), [])

    def test_빈_줄을_건너뛴다(self):
        self.assertEqual(len(reports.parse_conversion_tsv(REAL + "\n\n")), 2)


from datetime import date  # noqa: E402
import collect  # noqa: E402


class TestWindow(unittest.TestCase):
    def test_끝은_D_2_다(self):
        # D-1 은 "20007 지표 준비중" 이라 못 쓴다
        since, until = collect.window(7, today=date(2026, 8, 29))
        self.assertEqual(until, date(2026, 8, 27))

    def test_7일이면_시작은_끝에서_6일_전이다(self):
        since, until = collect.window(7, today=date(2026, 8, 29))
        self.assertEqual(since, date(2026, 8, 21))
        self.assertEqual((until - since).days, 6)

    def test_30일_창(self):
        since, until = collect.window(30, today=date(2026, 8, 29))
        self.assertEqual((until - since).days, 29)


if __name__ == "__main__":
    unittest.main(verbosity=2)
