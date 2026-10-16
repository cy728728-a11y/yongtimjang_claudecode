#!/usr/bin/env python3
"""sold_lock_rules 단위테스트 — 네트워크 0, 표준라이브러리만."""
import json
import os
import sys
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sold_lock_rules as R  # noqa: E402

KST = ZoneInfo("Asia/Seoul")


class TargetMarketsTest(unittest.TestCase):
    def test_52개(self):
        m = R.target_markets()
        self.assertEqual(len(m), 52)
        self.assertEqual(len(set(m)), 52)
        for no in ["1-1", "4-3", "11-1", "11-3", "13-1", "24-3", "25-1"]:
            self.assertIn(no, m)
        for no in ["5-1", "10-3", "12-1", "12-3", "25-2", "4-4", "26-1"]:
            self.assertNotIn(no, m)

    def test_parse_markets_arg(self):
        self.assertEqual(R.parse_markets_arg("1-1,2-1"), ["1-1", "2-1"])
        self.assertEqual(R.parse_markets_arg(" 1-1 , 2-1 "), ["1-1", "2-1"])
        with self.assertRaises(ValueError):
            R.parse_markets_arg("5-1")
        with self.assertRaises(ValueError):
            R.parse_markets_arg("1-1,25-2")


class DateTest(unittest.TestCase):
    def test_day_range(self):
        self.assertEqual(
            R.day_range_kst("2026-10-15"),
            ("2026-10-15T00:00:00.000+09:00", "2026-10-15T23:59:59.999+09:00"))

    def test_default_target_date(self):
        now = datetime(2026, 10, 16, 0, 1, tzinfo=KST)
        self.assertEqual(R.default_target_date(now), "2026-10-15")

    def test_is_paid_on(self):
        self.assertTrue(R.is_paid_on("2026-10-15T10:12:33.0+09:00", "2026-10-15"))
        self.assertFalse(R.is_paid_on("2026-10-16T00:00:01.0+09:00", "2026-10-15"))
        # UTC 10-14 15:30 = KST 10-15 00:30
        self.assertTrue(R.is_paid_on("2026-10-14T15:30:00Z", "2026-10-15"))
        self.assertFalse(R.is_paid_on("2026-10-14T14:59:59Z", "2026-10-15"))
        self.assertFalse(R.is_paid_on(None, "2026-10-15"))
        self.assertFalse(R.is_paid_on("엉터리", "2026-10-15"))


def _row(market, pid, code, poid="1"):
    return {"market": market, "product_order_id": poid, "product_id": pid,
            "seller_code": code, "product_name": "상품", "payment_date": "2026-10-15T10:00:00+09:00"}


class DedupTest(unittest.TestCase):
    def test_코드기준_묶음(self):
        rows = [_row("1-1", "111", "A", "o1"), _row("1-1", "111", "A", "o2"),
                _row("1-1", "222", "", "o3"), _row("1-1", "222", None, "o4"),
                _row("2-1", "333", "A", "o5")]
        out = R.dedup_orders(rows)
        self.assertEqual(len(out), 3)
        by = {(o["market"], o["seller_code"] or o["product_id"]): o for o in out}
        self.assertEqual(by[("1-1", "A")]["order_count"], 2)
        self.assertEqual(by[("1-1", "222")]["order_count"], 2)
        self.assertEqual(by[("2-1", "A")]["order_count"], 1)
        self.assertEqual(sorted(by[("1-1", "A")]["product_order_ids"]), ["o1", "o2"])


def _item(pid="p1", group="1번_용쌤1-1", 숨김=False, **kw):
    d = {"productId": pid, "판매자상품코드": "A", "그룹": group}
    if 숨김 is not None:
        d["숨김"] = 숨김
    d.update(kw)
    return d


class DecideTest(unittest.TestCase):
    order = {"market": "1-1", "product_id": "12345678", "seller_code": "A"}

    def d(self, items, ss=None, market="1-1"):
        if ss is None:
            ss = {"p1": "12345678"}
        return R.decide(self.order, items, ss, market)

    def test_not_found(self):
        self.assertEqual(self.d([]), ("skip", "not_found"))

    def test_multiple(self):
        self.assertEqual(self.d([_item(), _item(pid="p2")]), ("skip", "multiple"))

    def test_ss_lookup_failed(self):
        self.assertEqual(self.d([_item()], ss={"p1": None}), ("skip", "ss_lookup_failed"))
        self.assertEqual(self.d([_item()], ss={}), ("skip", "ss_lookup_failed"))

    def test_productno_mismatch(self):
        self.assertEqual(self.d([_item()], ss={"p1": "999"}), ("skip", "productno_mismatch"))

    def test_market_mismatch_경계(self):
        self.assertEqual(self.d([_item(group="1번_용쌤11-1")]), ("skip", "market_mismatch"))
        self.assertEqual(self.d([_item(group="1번_용쌤1-12")]), ("skip", "market_mismatch"))
        self.assertEqual(self.d([_item(group="1번_용쌤2-1")]), ("skip", "market_mismatch"))
        self.assertEqual(self.d([_item(group=None)]), ("skip", "market_mismatch"))
        self.assertEqual(self.d([_item(group="3번_용쌤1-1 백업")]), ("lock", None))

    def test_lock_state_unknown(self):
        self.assertEqual(self.d([_item(숨김=None)]), ("skip", "lock_state_unknown"))
        self.assertEqual(self.d([_item(숨김="false")]), ("skip", "lock_state_unknown"))

    def test_잠금키_둘다_인정(self):
        self.assertEqual(self.d([_item(숨김=None, 잠금=True)]), ("already_locked", None))
        self.assertEqual(R.lock_state({"숨김": True}), True)
        self.assertEqual(R.lock_state({"잠금": False}), False)
        self.assertIsNone(R.lock_state({}))

    def test_already_locked(self):
        self.assertEqual(self.d([_item(숨김=True)]), ("already_locked", None))

    def test_lock(self):
        self.assertEqual(self.d([_item()]), ("lock", None))


class ExtractSsNoTest(unittest.TestCase):
    def test_extract(self):
        self.assertEqual(R.extract_ss_no("https://smartstore.naver.com/x/products/12345678"), "12345678")
        self.assertEqual(R.extract_ss_no("12345678"), "12345678")
        self.assertEqual(R.extract_ss_no(12345678), "12345678")
        self.assertIsNone(R.extract_ss_no(None))
        self.assertIsNone(R.extract_ss_no(""))
        self.assertIsNone(R.extract_ss_no("https://smartstore.naver.com/x"))


class SummaryTest(unittest.TestCase):
    def test_memo(self):
        result = {
            "totals": {"orders": 10, "locked_new": 3, "already_locked": 4, "would_lock": 0,
                       "skipped": {"not_found": 2, "multiple": 1}},
            "markets": {"1-1": {"status": "ok"}, "15-3": {"status": "token_failed"}},
        }
        memo = R.summary_memo(result)
        self.assertEqual(
            memo,
            "주문 10 · 신규잠금 3 · 기존잠금 4 · 스킵 3(not_found 2, multiple 1) · 실패마켓 15-3(정지/토큰실패)")
        self.assertFalse(R.checked_flag(result))

    def test_checked_flag(self):
        ok = {"totals": {"orders": 1, "locked_new": 1, "already_locked": 0, "skipped": {}},
              "markets": {"1-1": {"status": "ok"}}}
        self.assertTrue(R.checked_flag(ok))
        self.assertEqual(R.summary_memo(ok), "주문 1 · 신규잠금 1 · 기존잠금 0 · 스킵 0")
        fail = {"totals": {"orders": 0, "locked_new": 0, "already_locked": 0, "skipped": {}},
                "markets": {"1-1": {"status": "orders_failed"}}}
        self.assertFalse(R.checked_flag(fail))


class RedactTest(unittest.TestCase):
    SEC = "$2a$04$ABCDEFGHIJKLMNOPQRSTUu"

    def test_redact(self):
        self.assertEqual(R.redact(f"x {self.SEC} y", [self.SEC, "", None]), "x *** y")
        self.assertEqual(R.redact(None, [self.SEC]), "")

    def test_safe_json(self):
        obj = {"store": {"client_secret": self.SEC, "client_id": "cid"}, "err": f"bad {self.SEC}"}
        s = R.safe_json(obj, [self.SEC])
        self.assertNotIn(self.SEC, s)
        self.assertIn("***", s)
        json.loads(s)


if __name__ == "__main__":
    unittest.main()
