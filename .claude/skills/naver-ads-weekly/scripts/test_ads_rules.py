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


class TestPausedAdsRule6(unittest.TestCase):
    """BOARD-05 — 꺼진 소재는 ⑥ 에만 있고, 정지사유·게재 여부를 싣는다."""

    def _off(self, ad_id, mall="1", reason="AD_ABNORMAL_INTERLOCK"):
        return dict(ad(ad_id, enable=False, mall=mall), statusReason=reason,
                    editTm="2026-09-01T00:00:00Z")

    def test_꺼진_소재의_30일_실적은_2345_어디에도_없다(self):
        ads = [self._off("off1")]
        s30 = {"off1": stat(imp=500, clk=50, ctr=0.5, cost=9000)}
        pur = {"off1": {"cnt": 1, "amt": 30000}}
        res = R.classify(ads, {}, {}, s30, pur)
        for k in ("②썸네일교체", "③원인분석", "④효자후보", "⑤효자확정"):
            self.assertNotIn("off1", [r["adId"] for r in res[k]], k)
        self.assertEqual([r["adId"] for r in res["⑥삭제대상"]], ["off1"])

    def test_정지_행에_statusReason_editTm(self):
        res = R.classify([self._off("off1", reason="AD_DISAPPROVED")], {}, {}, {}, {})
        row = res["⑥삭제대상"][0]
        self.assertEqual(row["statusReason"], "AD_DISAPPROVED")
        self.assertEqual(row["editTm"], "2026-09-01T00:00:00Z")

    def test_productLive_같은_상품_게재중이면_True_아니면_False(self):
        ads = [self._off("off1", mall="M1"), ad("on1", mall="M1"), self._off("off2", mall="M2")]
        res = R.classify(ads, {}, {}, {}, {})
        by = {r["adId"]: r for r in res["⑥삭제대상"]}
        self.assertIs(by["off1"]["productLive"], True)
        self.assertIs(by["off2"]["productLive"], False)

    def test_productLive_mallProductId_없으면_False(self):
        ads = [self._off("off1", mall=None), ad("on1", mall=None)]
        res = R.classify(ads, {}, {}, {}, {})
        self.assertIs(res["⑥삭제대상"][0]["productLive"], False)

    def test_1에서5_행에는_정지_필드가_없다(self):
        ads = [ad("on1"), ad("on2"), self._off("off1")]
        s30 = {"on2": stat(imp=500, clk=50, ctr=0.5)}
        res = R.classify(ads, {}, {}, s30, {"on2": {"cnt": 1, "amt": 1}})
        for k in ("①노출0", "②썸네일교체", "③원인분석", "④효자후보", "⑤효자확정"):
            for r in res[k]:
                self.assertNotIn("statusReason", r, k)
                self.assertNotIn("productLive", r, k)
        self.assertTrue(res["①노출0"] and res["⑤효자확정"])


# ── ⑦ 체계 (2026-10-16) ─────────────────────────────────────────────────
G = {"grp1": {"name": "판매상품_11-2_테스트", "bidAmt": 70}}


def prow(ad_id, ctr, imp=100):
    """풀 행 1건(ctr_tail/split_global 입력 모양)."""
    return {"adId": ad_id, "ctr": ctr, "imp": imp}


class TestPool7(unittest.TestCase):
    def test_노출_49는_빠지고_50은_들어간다(self):
        rows = R.pool_rows([ad("a"), ad("b")], G, {"a": stat(imp=49), "b": stat(imp=50)})
        self.assertEqual([r["adId"] for r in rows], ["b"])

    def test_꺼진_소재와_통계없는_소재는_제외(self):
        rows = R.pool_rows([ad("a", enable=False), ad("b")], G, {"a": stat(imp=500)})
        self.assertEqual(rows, [])

    def test_7일_지표와_광고그룹이_붙는다(self):
        r = R.pool_rows([ad("a")], G, {"a": stat(imp=60, clk=3, ctr=5.0)})[0]
        self.assertEqual((r["imp"], r["clk"], r["ctr"], r["adGroup"]), (60, 3, 5.0, "판매상품_11-2_테스트"))

    def test_상수는_50_10퍼센트_20(self):
        self.assertEqual((R.POP_IMP_MIN, R.CTR_TAIL_PCT, R.MAINT_CLICK_MIN), (50, 0.10, 20))


class TestCtrTail(unittest.TestCase):
    def test_풀20건이면_2건(self):
        rows = [prow(str(i), ctr=float(i)) for i in range(20)]
        self.assertEqual(len(R.ctr_tail(rows)), 2)

    def test_풀21건이면_올림해서_3건(self):
        rows = [prow(str(i), ctr=float(i)) for i in range(21)]
        self.assertEqual(len(R.ctr_tail(rows)), 3)

    def test_빈_풀은_빈_결과(self):
        self.assertEqual(R.ctr_tail([]), [])

    def test_풀1건이면_1건(self):
        self.assertEqual(len(R.ctr_tail([prow("a", 1.0)])), 1)

    def test_하위는_CTR_오름차순_동률은_노출_많은_쪽(self):
        rows = [prow("a", 0.5, imp=100), prow("b", 0.1, imp=100), prow("c", 0.1, imp=900)] + \
               [prow(f"x{i}", 5.0) for i in range(17)]
        got = R.ctr_tail(rows, pct=0.15)
        self.assertEqual([r["adId"] for r in got], ["c", "b", "a"])

    def test_상위는_CTR_내림차순_동률은_노출_많은_쪽(self):
        rows = [prow("a", 3.0, imp=100), prow("b", 4.0, imp=100), prow("c", 4.0, imp=900)] + \
               [prow(f"x{i}", 0.1) for i in range(17)]
        got = R.ctr_tail(rows, pct=0.15, top=True)
        self.assertEqual([r["adId"] for r in got], ["c", "b", "a"])

    def test_원본을_바꾸지_않는다(self):
        rows = [prow("a", 1.0)]
        R.ctr_tail(rows)[0]["ctr"] = 99
        self.assertEqual(rows[0]["ctr"], 1.0)


class TestSplitGlobal(unittest.TestCase):
    def test_계정별이_아니라_전_계정_1풀이다(self):
        # A 의 CTR 0.1 1건 + B 의 CTR 0.5 19건 = 20건 → 하위 2건 = A 1 + B 1
        pools = {"A": [prow("a1", 0.1)], "B": [prow(f"b{i}", 0.5) for i in range(19)]}
        out = R.split_global(pools)
        self.assertEqual([r["adId"] for r in out["A"]["⑦b썸네일변형"]], ["a1"])
        self.assertEqual(len(out["B"]["⑦b썸네일변형"]), 1)
        self.assertEqual(out["A"]["⑦b썸네일변형"][0]["acct"], "A")
        self.assertEqual(out["B"]["⑦b썸네일변형"][0]["acct"], "B")

    def test_상위는_7c후보로_간다(self):
        pools = {"A": [prow("a1", 9.0)], "B": [prow(f"b{i}", 0.5) for i in range(9)]}
        out = R.split_global(pools)
        self.assertEqual([r["adId"] for r in out["A"]["⑦c상세꾸미기후보"]], ["a1"])
        self.assertEqual(out["B"]["⑦c상세꾸미기후보"], [])

    def test_풀이_빈_계정도_빈_리스트_두개(self):
        out = R.split_global({"A": [], "B": [prow("b", 1.0)]})
        self.assertEqual(out["A"], {"⑦b썸네일변형": [], "⑦c상세꾸미기후보": []})


class TestRule7d(unittest.TestCase):
    def _run(self, ads, s30=None, pur=None):
        return R.classify(ads, G, {}, s30 or {}, pur or {})

    def test_30일_클릭20_이상만_구매_있어도_포함(self):
        res = self._run([ad("a"), ad("b"), ad("c")],
                        s30={"a": stat(clk=20), "b": stat(clk=19), "c": stat(clk=50)},
                        pur={"c": {"cnt": 3, "amt": 9000}})
        got = res["⑦d정비점검후보"]
        self.assertEqual([r["adId"] for r in got], ["c", "a"])   # 클릭 많은 순
        self.assertEqual([r["purCnt"] for r in got], [3, 0])

    def test_꺼진_소재는_제외(self):
        res = self._run([ad("a", enable=False)], s30={"a": stat(clk=99)})
        self.assertEqual(res["⑦d정비점검후보"], [])

    def test_키_순서_6_다음_summary_앞(self):
        keys = list(self._run([ad("a")]).keys())
        self.assertEqual(keys.index("⑦d정비점검후보"), keys.index("⑥삭제대상") + 1)
        self.assertEqual(keys[-1], "_summary")


def er(match="히트", detail="중국어원본", **kw):
    """보강(enrich) 을 거친 행."""
    d = {"adId": "x", "불사자매칭": match, "상세상태": detail}
    d.update(kw)
    return d


class TestFinal7c(unittest.TestCase):
    def test_히트_미가공은_포함_AI가공완료는_제외(self):
        rows = [er(detail="중국어원본", adId="a"), er(detail="단순번역만", adId="b"),
                er(detail="AI가공완료", adId="c")]
        self.assertEqual([r["adId"] for r in R.final_7c(rows)], ["a", "b"])

    def test_미매칭은_라벨째_포함(self):
        rows = [er(match="미매칭: 키없음", detail=None, adId="a")]
        self.assertEqual([r["adId"] for r in R.final_7c(rows)], ["a"])

    def test_보강키가_없으면_포함_라벨_불사자_미조회(self):
        rows = [{"adId": "a"}]
        self.assertEqual(len(R.final_7c(rows)), 1)
        self.assertEqual(R.match_label(rows[0]), "불사자 미조회")


class TestMaintenanceVerdict(unittest.TestCase):
    def test_미매칭(self):
        self.assertEqual(R.maintenance_verdict(er(match="미매칭: 다건")), "불사자 미매칭")

    def test_둘다_OK면_정비완료(self):
        self.assertEqual(R.maintenance_verdict(er(상세미가공=False, 옵션미정리=False)), "정비완료")

    def test_상세_미가공(self):
        self.assertIn("상세 미가공", R.maintenance_verdict(er(상세미가공=True, 옵션미정리=False)))

    def test_옵션명_미정리(self):
        self.assertIn("옵션명 미정리", R.maintenance_verdict(er(상세미가공=False, 옵션미정리=True)))

    def test_둘다면_가운뎃점으로_연결(self):
        self.assertEqual(R.maintenance_verdict(er(상세미가공=True, 옵션미정리=True)),
                         "상세 미가공 · 옵션명 미정리")

    def test_옵션_판정불가(self):
        self.assertEqual(R.maintenance_verdict(er(상세미가공=False, 옵션미정리=None)), "판정 불가(옵션)")

    def test_상세_판정불가(self):
        self.assertEqual(R.maintenance_verdict(er(상세미가공=None, 옵션미정리=False)), "판정 불가(상세)")

    def test_보강키_없음(self):
        self.assertEqual(R.maintenance_verdict({"adId": "a"}), "불사자 미조회")


if __name__ == "__main__":
    unittest.main(verbosity=2)
