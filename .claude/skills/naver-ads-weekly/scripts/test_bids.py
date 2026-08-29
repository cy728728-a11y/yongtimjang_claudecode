#!/usr/bin/env python3
"""입찰 인상 가드레일 회귀 테스트 — 네트워크 없이 돈다.

여기서 틀리면 실제 광고비가 잘못 나간다. 가장 조심할 곳이다.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bids  # noqa: E402
import ledger  # noqa: E402


def row(ad_id="a", bid=100, use_group=False, group_bid=70):
    return {"adId": ad_id, "bid": bid, "useGroupBid": use_group, "groupBid": group_bid, "title": "상품"}


class TestPlanRaise(unittest.TestCase):
    def test_개별입찰은_현재값에_10원(self):
        p = bids.plan_raise(row(bid=120, use_group=False), {})
        self.assertEqual((p["action"], p["from"], p["to"]), ("인상", 120, 130))

    def test_그룹입찰은_그룹기본가에_10원이다(self):
        # 잠자던 bidAmt 를 쓰면 올리려다 내리게 된다. 실측: 그룹 70 / 잠자던 값 50
        p = bids.plan_raise(row(bid=70, use_group=True, group_bid=70), {})
        self.assertEqual((p["action"], p["from"], p["to"]), ("인상", 70, 80))

    def test_상한_200원을_넘기지_않는다(self):
        p = bids.plan_raise(row(bid=195), {})
        self.assertEqual(p["action"], "상한도달")
        self.assertIsNone(p["to"])

    def test_정확히_200원이면_더_올리지_않는다(self):
        self.assertEqual(bids.plan_raise(row(bid=200), {})["action"], "상한도달")

    def test_3주_연속_실패면_중단한다(self):
        led = {"a": {"raises": [], "streak": 3, "capped": False}}
        self.assertEqual(bids.plan_raise(row(), led)["action"], "연속실패중단")

    def test_입찰가를_모르면_건드리지_않는다(self):
        p = bids.plan_raise(row(bid=None, use_group=True, group_bid=None), {})
        self.assertEqual(p["action"], "입찰가불명")
        self.assertIsNone(p["to"])

    def test_오늘_이미_인상한_소재는_재수집후_또_올리지_않는다(self):
        # Critical 1 재현: bids --commit 이 100→110 올린 뒤 죽고, 운영자가
        # prep && run && bids --commit 으로 복구하면 새 스냅샷의 bid=110 을 보고
        # 계획을 세운다 — today 를 넘기지 않으면 110→120 으로 또 올라간다.
        led = {"a": {"raises": [{"date": "2026-08-30", "from": 100, "to": 110}],
                     "streak": 0, "capped": False}}
        p = bids.plan_raise(row(ad_id="a", bid=110), led, today="2026-08-30")
        self.assertEqual(p["action"], "오늘이미인상")
        self.assertIsNone(p["to"])


class TestBody(unittest.TestCase):
    def test_전환시_useGroupBidAmt_를_False_로_바꾼다(self):
        ad_obj = {"nccAdId": "a", "adAttr": {"bidAmt": 50, "useGroupBidAmt": True}}
        body = bids.build_body(ad_obj, 80)
        self.assertEqual(body["adAttr"], {"bidAmt": 80, "useGroupBidAmt": False})

    def test_원본_객체를_변조하지_않는다(self):
        ad_obj = {"nccAdId": "a", "adAttr": {"bidAmt": 50, "useGroupBidAmt": True}}
        bids.build_body(ad_obj, 80)
        self.assertEqual(ad_obj["adAttr"], {"bidAmt": 50, "useGroupBidAmt": True})

    def test_다른_필드는_그대로_보낸다(self):
        ad_obj = {"nccAdId": "a", "nccAdgroupId": "g", "type": "SHOPPING_PRODUCT_AD",
                  "adAttr": {"bidAmt": 120, "useGroupBidAmt": False}}
        body = bids.build_body(ad_obj, 130)
        self.assertEqual(body["nccAdgroupId"], "g")
        self.assertEqual(body["type"], "SHOPPING_PRODUCT_AD")


class TestApplyRaiseRetry(unittest.TestCase):
    """Important 9 — apply_raise 도 delete_ads 수준의 회복력(429/5xx 재시도)을 갖는다."""

    def setUp(self):
        self._orig_call = bids.nvad.call
        self._orig_sleep = bids.time.sleep
        bids.time.sleep = lambda *_: None  # 테스트가 실제로 기다리지 않게 한다
        self.calls = []

    def tearDown(self):
        bids.nvad.call = self._orig_call
        bids.time.sleep = self._orig_sleep

    def test_429는_재시도후_성공한다(self):
        seq = [(429, "too many"), (200, {})]

        def fake_call(acct, method, path, params=None, body=None):
            self.calls.append(1)
            return seq.pop(0)

        bids.nvad.call = fake_call
        ad_obj = {"nccAdId": "a", "adAttr": {"bidAmt": 100, "useGroupBidAmt": False}}
        good, err = bids.apply_raise({}, ad_obj, 110)
        self.assertTrue(good)
        self.assertEqual(len(self.calls), 2)

    def test_4회_전부_실패하면_포기한다(self):
        def fake_call(acct, method, path, params=None, body=None):
            self.calls.append(1)
            return 503, "down"

        bids.nvad.call = fake_call
        ad_obj = {"nccAdId": "a", "adAttr": {"bidAmt": 100, "useGroupBidAmt": False}}
        good, err = bids.apply_raise({}, ad_obj, 110)
        self.assertFalse(good)
        self.assertEqual(len(self.calls), 4)

    def test_하드에러는_재시도하지_않는다(self):
        def fake_call(acct, method, path, params=None, body=None):
            self.calls.append(1)
            return 400, "bad request"

        bids.nvad.call = fake_call
        ad_obj = {"nccAdId": "a", "adAttr": {"bidAmt": 100, "useGroupBidAmt": False}}
        good, err = bids.apply_raise({}, ad_obj, 110)
        self.assertFalse(good)
        self.assertEqual(len(self.calls), 1)


class TestRevert(unittest.TestCase):
    """Important 4 — bids --revert 되돌리기."""

    def test_원본_adAttr_그대로_되쓴다(self):
        ad_obj = {"nccAdId": "a", "nccAdgroupId": "g", "adAttr": {"bidAmt": 120, "useGroupBidAmt": False}}
        original = {"bidAmt": 70, "useGroupBidAmt": True}
        body = bids.build_revert_body(ad_obj, original)
        self.assertEqual(body["adAttr"], {"bidAmt": 70, "useGroupBidAmt": True})
        self.assertEqual(body["nccAdgroupId"], "g")  # 다른 필드는 그대로

    def test_그룹입찰_복원도_함께_취소된다(self):
        # 인상 때 useGroupBidAmt 를 False 로 개별 전환했더라도, 되돌리면 원본의
        # useGroupBidAmt: True 가 그대로 실려 그룹입찰로 복귀한다.
        ad_obj = {"nccAdId": "a", "adAttr": {"bidAmt": 130, "useGroupBidAmt": False}}
        original = {"bidAmt": 70, "useGroupBidAmt": True}
        body = bids.build_revert_body(ad_obj, original)
        self.assertTrue(body["adAttr"]["useGroupBidAmt"])

    def test_원본_객체를_변조하지_않는다(self):
        ad_obj = {"nccAdId": "a", "adAttr": {"bidAmt": 120, "useGroupBidAmt": False}}
        original = {"bidAmt": 70, "useGroupBidAmt": True}
        bids.build_revert_body(ad_obj, original)
        self.assertEqual(ad_obj["adAttr"], {"bidAmt": 120, "useGroupBidAmt": False})

    def test_run_revert_dry_run은_아무것도_바꾸지_않는다(self):
        with tempfile.TemporaryDirectory() as t:
            run_dir = Path(t)
            (run_dir / "accounts" / "cy728").mkdir(parents=True)
            (run_dir / f"before_bids_cy728.json").write_text(
                json.dumps({"a": {"bidAmt": 70, "useGroupBidAmt": True}}), encoding="utf-8")
            (run_dir / "accounts" / "cy728" / "ads.json").write_text(
                json.dumps({"ads": [{"nccAdId": "a", "adAttr": {"bidAmt": 120, "useGroupBidAmt": False}}]}),
                encoding="utf-8")
            calls = []
            orig = bids.nvad.call
            bids.nvad.call = lambda *a, **k: calls.append(1)
            try:
                out = bids.run_revert({"alias": "cy728"}, run_dir, commit=False)
            finally:
                bids.nvad.call = orig
            self.assertEqual(out["targets"], 1)
            self.assertEqual(len(calls), 0)  # dry-run 은 네트워크를 타지 않는다

    def test_run_revert_commit은_원본으로_되돌리고_이력에_남긴다(self):
        with tempfile.TemporaryDirectory() as t:
            run_dir = Path(t) / "runs" / "2026-08-30"
            (run_dir / "accounts" / "cy728").mkdir(parents=True)
            (run_dir / f"before_bids_cy728.json").write_text(
                json.dumps({"a": {"bidAmt": 70, "useGroupBidAmt": True}}), encoding="utf-8")
            (run_dir / "accounts" / "cy728" / "ads.json").write_text(
                json.dumps({"ads": [{"nccAdId": "a", "nccAdgroupId": "g",
                                     "adAttr": {"bidAmt": 120, "useGroupBidAmt": False}}]}),
                encoding="utf-8")
            sent_bodies = []

            def fake_call(acct, method, path, params=None, body=None):
                sent_bodies.append(body)
                return 200, {}

            orig = bids.nvad.call
            bids.nvad.call = fake_call
            bids.time.sleep = lambda *_: None
            try:
                out = bids.run_revert({"alias": "cy728"}, run_dir, commit=True)
            finally:
                bids.nvad.call = orig
            self.assertEqual(out["committed"], 1)
            self.assertEqual(sent_bodies[0]["adAttr"], {"bidAmt": 70, "useGroupBidAmt": True})
            led = ledger.load(run_dir.parent.parent / "ledger" / "cy728.json")
            self.assertTrue(led["a"]["raises"][-1]["reverted"])


class TestStreaks(unittest.TestCase):
    def test_인상이력있고_이번에도_노출0이면_streak_증가(self):
        led = {"a": {"raises": [{"date": "2026-08-01", "from": 70, "to": 80}], "streak": 1, "capped": False}}
        bids.update_streaks(led, {"a"}, set(), "2026-08-30")
        self.assertEqual(led["a"]["streak"], 2)

    def test_인상이력있고_이번엔_노출_회복이면_streak_초기화(self):
        led = {"a": {"raises": [{"date": "2026-08-01", "from": 70, "to": 80}], "streak": 2, "capped": False}}
        # a 는 이번 회차 노출0 목록엔 없고, 7일 통계(stats_7d)에 실제로 행이 있다 = 노출 회복
        bids.update_streaks(led, set(), {"a"}, "2026-08-30")
        self.assertEqual(led["a"]["streak"], 0)

    def test_검수중으로_빠진_소재는_streak_이_유지된다(self):
        # Critical 2 재현: a 는 이번 회차 ①노출0 목록에도 없고(검수중이라 규칙에서 제외됐다)
        # stats_7d 에도 없다(노출이 없으니 당연히 없다) — "노출0 목록에 없음"을 "노출 회복"
        # 으로 오인하면 안 된다. 검수중·비활성으로 빠진 소재는 streak 을 건드리지 않는다.
        led = {"a": {"raises": [{"date": "2026-08-01", "from": 70, "to": 80}], "streak": 2, "capped": False}}
        bids.update_streaks(led, set(), set(), "2026-08-30")  # zero_ids·recovered_ids 둘 다 없음
        self.assertEqual(led["a"]["streak"], 2)  # 0으로 리셋되면 안 된다 — 유지

    def test_노출이_생긴_소재만_streak_이_0이_된다(self):
        # 같은 회차에 a(검수중으로 빠짐)와 b(진짜 노출 회복)가 섞여 있어도 구분해야 한다
        led = {
            "a": {"raises": [{"date": "2026-08-01", "from": 70, "to": 80}], "streak": 2, "capped": False},
            "b": {"raises": [{"date": "2026-08-01", "from": 70, "to": 80}], "streak": 2, "capped": False},
        }
        bids.update_streaks(led, set(), {"b"}, "2026-08-30")
        self.assertEqual(led["a"]["streak"], 2)  # 검수중 등으로 빠짐 — 유지
        self.assertEqual(led["b"]["streak"], 0)  # 실제 노출 회복 — 리셋

    def test_한번도_안올린_소재는_건드리지_않는다(self):
        led = {"a": {"raises": [], "streak": 0, "capped": False}}
        bids.update_streaks(led, {"a"}, set(), "2026-08-30")
        self.assertEqual(led["a"]["streak"], 0)

    def test_같은_회차를_두번_돌려도_중복_갱신되지_않는다(self):
        led = {"a": {"raises": [{"date": "2026-08-01", "from": 70, "to": 80}], "streak": 1, "capped": False}}
        bids.update_streaks(led, {"a"}, set(), "2026-08-30")
        bids.update_streaks(led, {"a"}, set(), "2026-08-30")  # 같은 날짜 재호출
        self.assertEqual(led["a"]["streak"], 2)

    def test_반환값은_갱신건수다(self):
        led = {
            "a": {"raises": [{"date": "2026-08-01", "from": 70, "to": 80}], "streak": 0, "capped": False},
            "b": {"raises": [{"date": "2026-08-01", "from": 70, "to": 80}], "streak": 1, "capped": False},
        }
        still, rec = bids.update_streaks(led, {"a"}, {"b"}, "2026-08-30")
        self.assertEqual((still, rec), (1, 1))

    def test_이력_갱신이_실제_판정까지_이어진다(self):
        # streak 2 인 소재가 이번 회차에도 노출0 이면 3이 되고, 그 갱신이 즉시
        # plan_raise 의 "연속실패중단" 판정에 반영돼야 한다 — 갱신이 죽은 코드가 아님을
        # 끝단(end-to-end)에서 검증한다.
        led = {"a": {"raises": [{"date": "2026-08-01", "from": 70, "to": 80}], "streak": 2, "capped": False}}
        bids.update_streaks(led, {"a"}, set(), "2026-08-30")
        p = bids.plan_raise(row(ad_id="a"), led)
        self.assertEqual(p["action"], "연속실패중단")



if __name__ == "__main__":
    unittest.main(verbosity=2)
