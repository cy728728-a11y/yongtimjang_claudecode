#!/usr/bin/env python3
"""입찰 인상 가드레일 회귀 테스트 — 네트워크 없이 돈다.

여기서 틀리면 실제 광고비가 잘못 나간다. 가장 조심할 곳이다.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bids  # noqa: E402


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


class TestStreaks(unittest.TestCase):
    def test_인상이력있고_이번에도_노출0이면_streak_증가(self):
        led = {"a": {"raises": [{"date": "2026-08-01", "from": 70, "to": 80}], "streak": 1, "capped": False}}
        bids.update_streaks(led, {"a"}, "2026-08-30")
        self.assertEqual(led["a"]["streak"], 2)

    def test_인상이력있고_이번엔_노출_회복이면_streak_초기화(self):
        led = {"a": {"raises": [{"date": "2026-08-01", "from": 70, "to": 80}], "streak": 2, "capped": False}}
        bids.update_streaks(led, set(), "2026-08-30")  # a 는 이번 회차 노출0 목록에 없다 = 회복
        self.assertEqual(led["a"]["streak"], 0)

    def test_한번도_안올린_소재는_건드리지_않는다(self):
        led = {"a": {"raises": [], "streak": 0, "capped": False}}
        bids.update_streaks(led, {"a"}, "2026-08-30")
        self.assertEqual(led["a"]["streak"], 0)

    def test_같은_회차를_두번_돌려도_중복_갱신되지_않는다(self):
        led = {"a": {"raises": [{"date": "2026-08-01", "from": 70, "to": 80}], "streak": 1, "capped": False}}
        bids.update_streaks(led, {"a"}, "2026-08-30")
        bids.update_streaks(led, {"a"}, "2026-08-30")  # 같은 날짜 재호출
        self.assertEqual(led["a"]["streak"], 2)

    def test_반환값은_갱신건수다(self):
        led = {
            "a": {"raises": [{"date": "2026-08-01", "from": 70, "to": 80}], "streak": 0, "capped": False},
            "b": {"raises": [{"date": "2026-08-01", "from": 70, "to": 80}], "streak": 1, "capped": False},
        }
        still, rec = bids.update_streaks(led, {"a"}, "2026-08-30")
        self.assertEqual((still, rec), (1, 1))

    def test_이력_갱신이_실제_판정까지_이어진다(self):
        # streak 2 인 소재가 이번 회차에도 노출0 이면 3이 되고, 그 갱신이 즉시
        # plan_raise 의 "연속실패중단" 판정에 반영돼야 한다 — 갱신이 죽은 코드가 아님을
        # 끝단(end-to-end)에서 검증한다.
        led = {"a": {"raises": [{"date": "2026-08-01", "from": 70, "to": 80}], "streak": 2, "capped": False}}
        bids.update_streaks(led, {"a"}, "2026-08-30")
        p = bids.plan_raise(row(ad_id="a"), led)
        self.assertEqual(p["action"], "연속실패중단")



if __name__ == "__main__":
    unittest.main(verbosity=2)
