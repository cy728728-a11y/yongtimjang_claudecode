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


if __name__ == "__main__":
    unittest.main(verbosity=2)
