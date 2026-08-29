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

    def test_오늘_이미_인상한_소재는_다시_올리지_않는다(self):
        # Critical 1 재현: bids --commit 이 중간에 죽고 prep&&run&&bids--commit 으로
        # 자연스럽게 복구하면, 이력에 오늘 날짜 인상이 이미 있는데도 스냅샷 bid 기준으로
        # 또 인상해버려 하루에 두 번(100→110→120) 오르면 안 된다.
        data = {"a": {"raises": [{"date": "2026-08-30", "from": 100, "to": 110}],
                      "streak": 0, "capped": False}}
        self.assertEqual(L.bid_decision(data, "a", 110, today="2026-08-30"),
                         ("최근인상", None))

    def test_7일_지나면_다시_인상한다(self):
        # 룩백 창(RAISE_COOLDOWN_DAYS=6) 밖이면 주 1회 케이던스상 다시 인상 대상이다
        data = {"a": {"raises": [{"date": "2026-08-23", "from": 100, "to": 110}],
                      "streak": 0, "capped": False}}
        self.assertEqual(L.bid_decision(data, "a", 110, today="2026-08-30"),
                         ("인상", 120))

    def test_3일_지나면_최근인상으로_막는다(self):
        # Important 2 재현: 자정을 넘겨 복구해도(날짜가 달라져도) 룩백 창 안이면 막는다.
        # 고치기 전엔 `date == today` 비교라 하루라도 다르면 통과해버려 100→110→120 처럼
        # 같은 회차 몫을 두 번 올리는 사고가 났다.
        data = {"a": {"raises": [{"date": "2026-08-27", "from": 100, "to": 110}],
                      "streak": 0, "capped": False}}
        self.assertEqual(L.bid_decision(data, "a", 110, today="2026-08-30"),
                         ("최근인상", None))

    def test_날짜_파싱_실패하면_막지_않는다(self):
        # 이력이 깨졌다고 인상을 영영 못 하면 안 된다 — 파싱 실패는 통과시킨다
        data = {"a": {"raises": [{"date": "이상한값", "from": 100, "to": 110}],
                      "streak": 0, "capped": False}}
        self.assertEqual(L.bid_decision(data, "a", 110, today="2026-08-30"),
                         ("인상", 120))

    def test_today_인자_없으면_기존과_동일하게_동작한다(self):
        # today 를 안 주는 기존 호출부(테스트 포함)는 동작이 바뀌면 안 된다
        data = {"a": {"raises": [{"date": "2026-08-30", "from": 100, "to": 110}],
                      "streak": 0, "capped": False}}
        self.assertEqual(L.bid_decision(data, "a", 110), ("인상", 120))

    def test_되돌린_인상은_당일_재인상을_막지_않는다(self):
        # Important 4(revert) 와 맞물리는 경계: record_reverted 가 붙인 reverted 플래그는
        # "오늘이미인상" 판정에서 제외한다 — 되돌렸으면 다시 올릴 수 있어야 한다.
        data = {"a": {"raises": [{"date": "2026-08-30", "from": 100, "to": 110}],
                      "streak": 0, "capped": False}}
        L.record_reverted(data, "a", "2026-08-30")
        self.assertEqual(L.bid_decision(data, "a", 100, today="2026-08-30"),
                         ("인상", 110))


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

    def test_되돌리면_마지막_인상에_플래그가_붙는다(self):
        # 같은 날 인상·되돌림(revert 는 보통 같은 회차에 바로 뒤따른다)
        d = {}
        L.record_raise(d, "a", "2026-08-30", 100, 110)
        L.record_reverted(d, "a", "2026-08-30")
        self.assertEqual(d["a"]["raises"][-1]["reverted"], True)
        self.assertEqual(d["a"]["raises"][-1]["from"], 100)  # 원본 인상 정보는 남는다

    def test_인상이력없는_소재는_되돌려도_플래그를_지어내지_않는다(self):
        # Minor 5 재현: run_revert 는 백업의 모든 키를 되돌리는데, 그중엔 이번 회차
        # 인상 시도가 실패해 이력이 아예 없는 소재도 섞여 있다 — 없던 인상 이력을
        # 지어내면 안 된다.
        d = {}
        L.record_reverted(d, "a", "2026-08-30")
        self.assertEqual(d["a"]["raises"], [])

    def test_지난주_인상은_이번_되돌림으로_건드리지_않는다(self):
        # Minor 5 재현: 마지막 인상 날짜가 이번 되돌림 날짜와 다르면(지난주 인상 등,
        # 이번 회차 시도는 실패해 새 이력이 없음) 엉뚱한 인상 항목에 reverted 플래그를
        # 찍으면 안 된다 — 실제로 되돌려지지 않은 과거 인상의 이력이 오염된다.
        d = {"a": {"raises": [{"date": "2026-08-23", "from": 70, "to": 80}],
                   "streak": 0, "capped": False}}
        L.record_reverted(d, "a", "2026-08-30")
        self.assertNotIn("reverted", d["a"]["raises"][-1])

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
