#!/usr/bin/env python3
"""입찰 이력·상한 판정 회귀 테스트 — 네트워크 없이 돈다."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger as L  # noqa: E402


class TestDecision(unittest.TestCase):
    def test_상한_미만이면_10원_올린다(self):
        self.assertEqual(L.bid_decision({}, "a", 120), ("인상", 130))

    def test_상한에_닿으면_올리지_않는다(self):
        self.assertEqual(L.bid_decision({}, "a", 200), ("상한도달", None))

    def test_인상하면_상한을_넘는_경우도_올리지_않는다(self):
        # 195 + 10 = 205 > 200
        self.assertEqual(L.bid_decision({}, "a", 195), ("상한도달", None))

    def test_3주_연속_실패면_중단한다(self):
        data = {"a": {"raises": [], "streak": 3, "capped": False}}
        self.assertEqual(L.bid_decision(data, "a", 100), ("연속실패중단", None))

    def test_2주_연속까지는_계속_올린다(self):
        data = {"a": {"raises": [], "streak": 2, "capped": False}}
        self.assertEqual(L.bid_decision(data, "a", 100), ("인상", 110))

    def test_현재값을_모르면_올리지_않는다(self):
        self.assertEqual(L.bid_decision({}, "a", None), ("입찰가불명", None))


class TestStreak(unittest.TestCase):
    def test_또_노출0이면_연속이_쌓인다(self):
        d = {}
        L.record_raise(d, "a", "2026-08-29", 100, 110)
        L.record_still_zero(d, "a")
        L.record_still_zero(d, "a")
        self.assertEqual(d["a"]["streak"], 2)

    def test_노출이_생기면_연속이_초기화된다(self):
        d = {"a": {"raises": [], "streak": 2, "capped": False}}
        L.record_recovered(d, "a")
        self.assertEqual(d["a"]["streak"], 0)

    def test_인상이력이_쌓인다(self):
        d = {}
        L.record_raise(d, "a", "2026-08-29", 100, 110)
        L.record_raise(d, "a", "2026-09-05", 110, 120)
        self.assertEqual(len(d["a"]["raises"]), 2)
        self.assertEqual(d["a"]["raises"][-1], {"date": "2026-09-05", "from": 110, "to": 120})


class TestIO(unittest.TestCase):
    def test_없는_파일은_빈_dict(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(L.load(Path(t) / "none.json"), {})

    def test_쓰고_다시_읽으면_같다(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "l.json"
            d = {"a": {"raises": [{"date": "2026-08-29", "from": 100, "to": 110}], "streak": 1, "capped": False}}
            L.save(p, d)
            self.assertEqual(L.load(p), d)

    def test_깨진_파일은_빈_dict(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "bad.json"
            p.write_text("{{{", encoding="utf-8")
            self.assertEqual(L.load(p), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
