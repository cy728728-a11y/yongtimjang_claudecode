#!/usr/bin/env python3
"""6개 규칙 판정 회귀 테스트 — 네트워크 없이 돈다.

수치는 cy728 실측(2026-08-27~29)에서 가져왔다. 규칙이 바뀌면 여기가 먼저 깨져야 한다.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ads_rules as R  # noqa: E402


def ad(ad_id, enable=True, bid=None, use_group=True, title="상품", mall="1", group="grp1"):
    """소재 1건을 만든다. adAttr 구조는 실측 응답 그대로다."""
    return {
        "nccAdId": ad_id, "nccAdgroupId": group, "enable": enable,
        "adAttr": {"bidAmt": bid, "useGroupBidAmt": use_group},
        "referenceData": {"productTitle": title, "mallProductId": mall},
    }


def stat(imp=0, clk=0, ctr=0.0, cost=0, rank=0.0):
    return {"impCnt": imp, "clkCnt": clk, "ctr": ctr, "salesAmt": cost, "avgRnk": rank}


class TestLiveAds(unittest.TestCase):
    def test_꺼진_소재를_거른다(self):
        got = R.live_ads([ad("a"), ad("b", enable=False)])
        self.assertEqual([x["nccAdId"] for x in got], ["a"])


class TestEffectiveBid(unittest.TestCase):
    def test_그룹입찰이면_그룹_기본가가_적용가다(self):
        # 잠자던 bidAmt(50)가 아니라 그룹값(70)이 실제 적용가다
        self.assertEqual(R.effective_bid(ad("a", bid=50, use_group=True), 70), 70)

    def test_개별입찰이면_자기_bidAmt_가_적용가다(self):
        self.assertEqual(R.effective_bid(ad("a", bid=120, use_group=False), 70), 120)

    def test_그룹가가_없으면_None(self):
        self.assertIsNone(R.effective_bid(ad("a", bid=50, use_group=True), None))


class TestClassify(unittest.TestCase):
    def setUp(self):
        self.group_of = {"grp1": {"name": "판매상품_11-2_테스트", "bidAmt": 70}}

    def _run(self, ads, s7=None, s30=None, pur=None):
        return R.classify(ads, self.group_of, s7 or {}, s30 or {}, pur or {})

    def test_규칙1_7일_통계에_없는_게재중_소재가_노출0이다(self):
        res = self._run([ad("a"), ad("b")], s7={"a": stat(imp=10)})
        self.assertEqual([x["adId"] for x in res["①노출0"]], ["b"])

    def test_규칙1은_검수대기_소재를_담지_않는다(self):
        # 검수 대기는 노출이 없는 게 정상이다. 입찰가를 올려도 노출이 생기지 않는다
        # 실측 2026-08-29: 검수대기 7건이 전부 규칙 ① 에 잡혔다
        a = ad("a"); a["inspectStatus"] = "PENDING"
        b = ad("b"); b["inspectStatus"] = "UNDER_REVIEW"
        c = ad("c"); c["inspectStatus"] = "APPROVED"
        res = self._run([a, b, c])
        self.assertEqual([x["adId"] for x in res["①노출0"]], ["c"])

    def test_검수대기여도_다른_규칙에는_정상적으로_들어간다(self):
        # ① 만 제외 대상이다 — 노출·클릭이 있으면 ②④ 판정은 정상으로 받는다
        a = ad("a"); a["inspectStatus"] = "PENDING"
        res = self._run([a], s30={"a": stat(imp=500, ctr=0.5)})
        self.assertEqual([x["adId"] for x in res["②썸네일교체"]], ["a"])

    def test_규칙1은_꺼진_소재를_담지_않는다(self):
        # 꺼진 소재는 당연히 노출 0이다. 담으면 죽은 광고 입찰가만 올리게 된다
        res = self._run([ad("a", enable=False)])
        self.assertEqual(res["①노출0"], [])

    def test_규칙6은_꺼진_소재만_담는다(self):
        res = self._run([ad("a"), ad("b", enable=False)])
        self.assertEqual([x["adId"] for x in res["⑥삭제대상"]], ["b"])

    def test_규칙2는_노출하한_미만을_제외한다(self):
        # 노출 99·CTR 0% 는 표본 부족이지 썸네일 문제가 아니다
        res = self._run([ad("a"), ad("b")],
                        s30={"a": stat(imp=99, ctr=0.0), "b": stat(imp=100, ctr=0.5)})
        self.assertEqual([x["adId"] for x in res["②썸네일교체"]], ["b"])

    def test_규칙2는_노출_많은_순으로_정렬된다(self):
        res = self._run([ad("a"), ad("b")],
                        s30={"a": stat(imp=200, ctr=0.5), "b": stat(imp=900, ctr=0.5)})
        self.assertEqual([x["adId"] for x in res["②썸네일교체"]], ["b", "a"])

    def test_규칙3은_구매완료가_있으면_제외한다(self):
        res = self._run([ad("a"), ad("b")],
                        s30={"a": stat(imp=500, clk=25), "b": stat(imp=500, clk=25)},
                        pur={"a": {"cnt": 1, "amt": 1000}})
        self.assertEqual([x["adId"] for x in res["③원인분석"]], ["b"])

    def test_규칙3은_클릭이_모자라면_제외한다(self):
        res = self._run([ad("a")], s30={"a": stat(imp=500, clk=19)})
        self.assertEqual(res["③원인분석"], [])

    def test_규칙4는_CTR2퍼센트_이상_노출하한_충족만(self):
        res = self._run([ad("a"), ad("b"), ad("c")],
                        s30={"a": stat(imp=500, ctr=2.0), "b": stat(imp=500, ctr=1.9),
                             "c": stat(imp=50, ctr=5.0)})
        self.assertEqual([x["adId"] for x in res["④효자후보"]], ["a"])

    def test_규칙5는_구매완료_금액을_싣는다(self):
        res = self._run([ad("a")], s30={"a": stat(imp=500, cost=1000)},
                        pur={"a": {"cnt": 2, "amt": 50000}})
        row = res["⑤효자확정"][0]
        self.assertEqual(row["purCnt"], 2)
        self.assertEqual(row["purAmt"], 50000)
        self.assertEqual(row["cost"], 1000)

    def test_판정행에_매칭키_mallProductId_가_실린다(self):
        # ②를 썸네일 스킬로 넘기려면 이 키가 반드시 있어야 한다
        res = self._run([ad("a", mall="12896544275")], s30={"a": stat(imp=500, ctr=0.1)})
        self.assertEqual(res["②썸네일교체"][0]["mallProductId"], "12896544275")

    def test_판정행에_광고그룹명이_실린다(self):
        res = self._run([ad("a")], s7={})
        self.assertEqual(res["①노출0"][0]["adGroup"], "판매상품_11-2_테스트")


class TestSummary(unittest.TestCase):
    def setUp(self):
        self.group_of = {"grp1": {"name": "판매상품_11-2_테스트", "bidAmt": 70}}

    def _run(self, ads, s7=None, s30=None, pur=None):
        return R.classify(ads, self.group_of, s7 or {}, s30 or {}, pur or {})

    def test_요약_광고비는_규칙_중복과_무관하다(self):
        # a 는 ②(노출100+ CTR<1%)와 ③(클릭20+ 구매0)에 동시에 들어간다.
        # 규칙별로 합산하면 광고비가 2,000원으로 두 번 세진다 — 요약은 1,000원이어야 한다
        res = self._run([ad("a")], s30={"a": stat(imp=500, clk=25, ctr=0.5, cost=1000)})
        self.assertIn("a", [x["adId"] for x in res["②썸네일교체"]])
        self.assertIn("a", [x["adId"] for x in res["③원인분석"]])
        self.assertEqual(res["_summary"]["cost"], 1000)

    def test_요약에_소재수와_게재중수가_들어간다(self):
        res = self._run([ad("a"), ad("b", enable=False)])
        self.assertEqual(res["_summary"]["ads"], 2)
        self.assertEqual(res["_summary"]["live"], 1)

    def test_요약_구매매출은_purchases_전량_합이다(self):
        res = self._run([ad("a"), ad("b")],
                        s30={"a": stat(imp=500), "b": stat(imp=500)},
                        pur={"a": {"cnt": 1, "amt": 5000}, "b": {"cnt": 2, "amt": 7000}})
        self.assertEqual(res["_summary"]["purAmt"], 12000)
        self.assertEqual(res["_summary"]["purCnt"], 3)

    def test_꺼진_소재의_광고비는_요약에_넣지_않는다(self):
        # 게재중이 아닌 소재는 이번 회차 성과가 아니다
        res = self._run([ad("a", enable=False)], s30={"a": stat(imp=500, cost=9999)})
        self.assertEqual(res["_summary"]["cost"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
