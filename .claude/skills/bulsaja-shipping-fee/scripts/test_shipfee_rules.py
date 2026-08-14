#!/usr/bin/env python3
"""shipfee_rules 단위 테스트 — 요금 산식·게이트. 외부 호출 0회.

  python .claude/skills/bulsaja-shipping-fee/scripts/test_shipfee_rules.py
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import shipfee_rules as R  # noqa: E402


class TestBillable(unittest.TestCase):
    def test_1kg_미만은_1kg(self):
        self.assertEqual(R.billable_kg(0.6), 1.0)
        self.assertEqual(R.billable_kg(0.1), 1.0)
        self.assertEqual(R.billable_kg(1.0), 1.0)

    def test_05kg_단위_올림(self):
        self.assertEqual(R.billable_kg(1.1), 1.5)
        self.assertEqual(R.billable_kg(1.5), 1.5)
        self.assertEqual(R.billable_kg(1.6), 2.0)
        self.assertEqual(R.billable_kg(2.0), 2.0, "정수 배수를 한 칸 올리면 안 된다")
        self.assertEqual(R.billable_kg(3.0), 3.0)

    def test_부동소수_오차로_한칸_더_올라가지_않는다(self):
        # 2.0/0.5 는 정확하지만 1.1/0.5 는 2.2000000000000006 이다
        for kg in (2.0, 2.5, 3.0, 4.5, 7.0, 10.0):
            self.assertEqual(R.billable_kg(kg), kg, f"{kg}kg")

    def test_무게없음(self):
        self.assertIsNone(R.billable_kg(None))
        self.assertIsNone(R.vip_fee(None))


class TestFee(unittest.TestCase):
    def test_실측_요율표(self):
        """오픈차이나 실측(2026-08-12)을 그대로 검증한다 — 어긋나면 요율이 틀린 것이다."""
        for kg, expect in ((0.6, 5500), (1.0, 5500), (1.1, 6250), (2.0, 7000),
                           (3.0, 8500), (5.0, 11500), (10.0, 19000), (38.0, 61000)):
            self.assertEqual(R.rate_fee(kg), expect, f"{kg}kg")

    def test_한칸_750원(self):
        self.assertEqual(R.rate_fee(1.5) - R.rate_fee(1.0), 750)
        self.assertEqual(R.rate_fee(4.0) - R.rate_fee(3.5), 750)

    def test_옛이름은_요율만_준다(self):
        """`vip_fee` 는 부대비용을 포함하지 않는다 — 이름이 그걸 숨겨서 별칭만 남겼다."""
        self.assertEqual(R.vip_fee(3.0), R.rate_fee(3.0))
        self.assertNotEqual(R.total_fee(3.0), R.rate_fee(3.0))


class TestPacking(unittest.TestCase):
    def test_무게구간별_위험도(self):
        self.assertEqual(R.packing_fee(1.0, "중간"), 0, "2kg 미만은 실측상 0원이 중앙")
        self.assertEqual(R.packing_fee(1.0, "높음"), 1500)
        self.assertEqual(R.packing_fee(3.0, "중간"), 3100)
        self.assertEqual(R.packing_fee(7.0, "높음"), 4000)
        self.assertEqual(R.packing_fee(15.0, "높음"), 11200)
        self.assertEqual(R.packing_fee(38.0, "낮음"), 11400)

    def test_위험도가_오르면_포장비도_오르거나_같다(self):
        for kg in (1.0, 3.0, 7.0, 15.0, 30.0):
            vals = [R.packing_fee(kg, r) for r in R.RISK_LEVELS]
            self.assertEqual(vals, sorted(vals), f"{kg}kg 에서 역전")

    def test_모르는_위험도는_중간(self):
        for bad in ("", None, "매우높음", "high"):
            self.assertEqual(R.packing_fee(5.0, bad), R.packing_fee(5.0, "중간"), repr(bad))

    def test_총액은_요율_더하기_포장비(self):
        self.assertEqual(R.total_fee(3.0, "중간"), 8500 + 3100)


class TestOCActuals(unittest.TestCase):
    """실측 원본(`오픈차이나-실측.json`) 재현 — 요율 상수를 건드리면 여기서 깨진다."""

    def setUp(self):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "references", "오픈차이나-실측.json")
        if not os.path.exists(path):
            self.skipTest("실측 데이터 없음 — fetch_oc_actuals.py 로 받는다")
        with open(path, encoding="utf-8") as f:
            self.rows = json.load(f)

    def test_순수배송비가_전건_재현된다(self):
        n, bad = 0, []
        for r in self.rows:
            kg, fee = r.get("측정무게"), (r.get("항목") or {}).get("배송비")
            if kg is None or not fee:
                continue
            n += 1
            if R.rate_fee(kg) != fee:
                bad.append((kg, fee, R.rate_fee(kg)))
        self.assertGreater(n, 30, "표본이 너무 적다")
        self.assertEqual(bad, [], f"{len(bad)}/{n}건 불일치")

    def test_측정무게는_실무게의_05kg_올림이다(self):
        for r in self.rows:
            a, b = r.get("실무게"), r.get("측정무게")
            if a is None or b is None:
                continue
            self.assertEqual(R.billable_kg(a), b, f"실{a} → 측정{b}")


class TestSurcharge(unittest.TestCase):
    def test_무게구간(self):
        self.assertEqual(R.surcharge(kg=3.0)[0], 600)
        self.assertEqual(R.surcharge(kg=6.0)[0], 1200)
        self.assertEqual(R.surcharge(kg=12.0)[0], 2800)
        self.assertEqual(R.surcharge(kg=18.0)[0], 3000)

    def test_해당없음(self):
        self.assertEqual(R.surcharge(kg=1.5)[0], 0)

    def test_무게와_세변합_중_높은쪽(self):
        # 3kg(600원 구간)인데 세변합 130cm(2800원 구간)면 2800 을 쓴다
        self.assertEqual(R.surcharge(kg=3.0, girth_cm=130)[0], 2800)

    def test_표범위_밖은_0이_아니라_사유를_남긴다(self):
        amt, why = R.surcharge(kg=30.0)
        self.assertEqual(amt, 0)
        self.assertIn("범위 밖", why)


class TestGirth(unittest.TestCase):
    def test_세변합(self):
        self.assertEqual(R.girth([45, 39, 20]), 104.0)
        self.assertEqual(R.volume_cm3([40, 40, 40]), 64000)

    def test_불완전한_치수는_None(self):
        self.assertIsNone(R.girth([45, 39]))
        self.assertIsNone(R.girth(None))
        self.assertIsNone(R.girth([45, 39, 0]))
        self.assertIsNone(R.volume_cm3(["가로", 39, 20]))


class TestKyungdong(unittest.TestCase):
    TABLE = {"부피구간": [[64000, 5500], [200000, 9000]],
             "무게구간": [[30, 8000], [60, 15000]]}

    def test_기준문서_예시(self):
        """§7 예시: 40×40×40 · 60kg · 25% → A 6,900 vs B 18,800 → 18,800."""
        amt, why = R.kyungdong(kg=60, dims=[40, 40, 40], region_rate=0.25,
                               table=self.TABLE)
        self.assertEqual(amt, 18800)
        self.assertIn("B(무게)", why)

    def test_부피가_이기는_경우(self):
        amt, why = R.kyungdong(kg=10, dims=[50, 50, 60], region_rate=0.25,
                               table=self.TABLE)
        self.assertEqual(amt, 11300)   # 9000*1.25 = 11250 → 100원 반올림
        self.assertIn("A(부피)", why)

    def test_표없으면_금액을_만들지_않는다(self):
        amt, why = R.kyungdong(kg=60, dims=[40, 40, 40], table={})
        self.assertIsNone(amt)
        self.assertIn("표준운임표", why)

    def test_구간밖(self):
        amt, _ = R.kyungdong(kg=999, dims=[300, 300, 300], table=self.TABLE)
        self.assertIsNone(amt)

    def test_부피가_없으면_금액을_만들지_않는다(self):
        """1.9m 풍차가 3kg 이라 3,800원이 나왔던 건 — 무게만으로는 장척을 못 잡는다."""
        amt, why = R.kyungdong(kg=3.0, dims=None, table=self.TABLE)
        self.assertIsNone(amt)
        self.assertIn("부피 미상", why)
        amt2, _ = R.kyungdong(kg=3.0, dims=[45, 39], table=self.TABLE)
        self.assertIsNone(amt2, "세 변이 다 있어야 한다")


class TestRealTable(unittest.TestCase):
    """실제 `경동-표준운임.json` 검산 — 재수집(fetch_kd_table.py)이 표를 망가뜨렸는지 잡는다.

    기준은 경동택배 페이지가 스스로 적어둔 예시다(수도권→경남권 25%):
      A운임 40×40×40 = 64,000㎤ × 25% = 6,900 · B운임 60kg × 25% = 18,800 → 18,800
    """

    def setUp(self):
        self.t = R.load_rate_table()
        if not self.t:
            self.skipTest("표준운임표 미보유 — fetch_kd_table.py 로 채운 뒤 검증된다")

    def test_페이지_예시가_재현된다(self):
        self.assertEqual(R._bracket(self.t["부피구간"], 64000), 5500)
        self.assertEqual(R._bracket(self.t["무게구간"], 60), 15000)
        amt, why = R.kyungdong(kg=60, dims=[40, 40, 40], region_rate=0.25, table=self.t)
        self.assertEqual(amt, 18800)
        self.assertIn("B(무게)", why)

    def test_구간이_오름차순이고_상한이_안_밀렸다(self):
        for key in ("부피구간", "무게구간"):
            rows = self.t[key]
            self.assertGreater(len(rows), 100, key)
            self.assertEqual(rows, sorted(rows), f"{key} 정렬 깨짐")
            self.assertTrue(all(f > 0 for _, f in rows), f"{key} 에 0원 구간")
        # 상한을 앞 숫자로 잡으면 표가 한 칸씩 밀려 6kg 이 아니라 7kg 이 첫 구간이 된다
        self.assertEqual(self.t["무게구간"][0][0], 6)
        self.assertEqual(self.t["부피구간"][0][0], 20000)
        self.assertEqual(self.t["무게구간"][-1][0], 10000)

    def test_정기화물_열을_담지_않았다(self):
        """정기화물은 같은 구간에서 택배보다 싸다. 6kg = 택배 3,000 / 정기화물 1,600."""
        self.assertEqual(R._bracket(self.t["무게구간"], 6), 3000)


def entry(**kw):
    base = {"productId": "U01", "실물": "선반", "무게근거": "원문 45*39",
            "무게군": [{"kg": 3.0, "행": ["*"]}], "신뢰도": "높음"}
    base.update(kw)
    return base


class TestPlan(unittest.TestCase):
    def test_기본_계획(self):
        p = R.plan_product(entry(), current_fee=7000)
        self.assertEqual(p["적용무게"], 3.0)
        self.assertEqual(p["요율"], 8500)
        self.assertEqual(p["포장비"], 3100, "3kg·중간 = 실측 중앙")
        self.assertEqual(p["제안배송비"], 11600, "제안 = 요율 + 포장비")
        self.assertEqual(p["차액"], 4600)
        self.assertEqual(p["상태"], R.S_OK)

    def test_파손위험이_제안배송비를_바꾼다(self):
        """이룸님 지적(2026-08-12) — 파손 위험이 높을수록 포장비가 커진다."""
        low = R.plan_product(entry(파손위험="낮음"))
        high = R.plan_product(entry(파손위험="높음"))
        self.assertEqual(low["요율"], high["요율"], "요율은 무게만의 함수다")
        self.assertLess(low["포장비"], high["포장비"])
        self.assertEqual(high["제안배송비"] - low["제안배송비"],
                         high["포장비"] - low["포장비"])

    def test_파손위험이_없으면_중간(self):
        self.assertEqual(R.plan_product(entry())["파손위험"], "중간")
        self.assertEqual(R.plan_product(entry(파손위험="몰라"))["파손위험"], "중간")

    def test_적용무게는_최대_대표는_대표행(self):
        e = entry(무게군=[{"kg": 1.0, "행": ["A"]}, {"kg": 6.0, "행": ["B"]}])
        p = R.plan_product(e, current_fee=5600, main_sku_id="A")
        self.assertEqual(p["적용무게"], 6.0, "적용은 판매 옵션 중 최대")
        self.assertEqual(p["대표무게"], 1.0, "대표는 대표 판매행이 속한 군")
        self.assertEqual(p["대표배송비"], 5500, "1kg·중간 = 요율 5,500 + 포장 0")

    def test_대표행을_못_찾으면_최소무게군(self):
        e = entry(무게군=[{"kg": 2.0, "행": ["A"]}, {"kg": 6.0, "행": ["B"]}])
        p = R.plan_product(e, main_sku_id="없는행")
        self.assertEqual(p["대표무게"], 2.0)

    def test_무게없음은_보류(self):
        for bad in ([], [{"kg": "1~1.5"}], [{"kg": 0}], [{"kg": None}]):
            p = R.plan_product(entry(무게군=bad))
            self.assertEqual(p["상태"], R.S_NO_WEIGHT, f"{bad}")
            self.assertFalse(R.savable(p))

    def test_신뢰도_낮음은_저장하지_않는다(self):
        p = R.plan_product(entry(신뢰도="낮음"), current_fee=7000)
        self.assertEqual(p["상태"], R.S_LOW_CONF)
        self.assertFalse(R.savable(p))

    def test_기본은_변경폭_게이트가_없다(self):
        """2026-08-12 이룸님 — 산식이 맞으면 큰 차액도 정답이다."""
        p = R.plan_product(entry(무게군=[{"kg": 10.0, "행": ["*"]}]), current_fee=5600)
        self.assertEqual(p["제안배송비"], 19000 + 5900)
        self.assertEqual(p["차액"], 19300)
        self.assertEqual(p["상태"], R.S_OK)
        self.assertTrue(R.savable(p))

    def test_max_delta_를_주면_그때만_보류(self):
        p = R.plan_product(entry(무게군=[{"kg": 10.0, "행": ["*"]}]),
                           current_fee=5600, max_delta=3000)
        self.assertEqual(p["상태"], R.S_DELTA)
        self.assertFalse(R.savable(p))

    def test_같은_금액이면_변경없음(self):
        p = R.plan_product(entry(), current_fee=11600)
        self.assertEqual(p["상태"], R.S_SAME)
        self.assertFalse(R.savable(p), "저장할 게 없는 건 저장 대상이 아니다")

    def test_신뢰도가_변경폭보다_먼저다(self):
        """금액을 못 믿는 상태에서 '변경폭' 이라고 적으면 원인이 가려진다."""
        p = R.plan_product(entry(신뢰도="낮음", 무게군=[{"kg": 20.0, "행": ["*"]}]),
                           current_fee=5600, max_delta=3000)
        self.assertEqual(p["상태"], R.S_LOW_CONF)

    def test_화물_판정은_세변합_OR_워커신고(self):
        p = R.plan_product(entry(부피cm=[60, 60, 60]))   # 세변합 180
        self.assertEqual(p["세변합"], 180.0)
        self.assertTrue(p["화물"])
        p2 = R.plan_product(entry(화물가능성="높음"))
        self.assertEqual(p2["화물"], "높음")
        p3 = R.plan_product(entry(부피cm=[10, 10, 10], 화물가능성="없음"))
        self.assertEqual(p3["화물"], "")

    def test_화물이_아니면_경동비를_계산하지_않는다(self):
        p = R.plan_product(entry(부피cm=[10, 10, 10]))
        self.assertIsNone(p["경동비"])
        self.assertEqual(p["경동근거"], "")

    def test_할증은_따로_더하지_않는다(self):
        """실측 `한진택배 할증료` 는 포장비 예상에 이미 섞여 있다 — 또 더하면 이중 계상."""
        p = R.plan_product(entry(무게군=[{"kg": 3.0, "행": ["*"]}]), current_fee=0)
        self.assertEqual(p["할증"], 600, "구간 표시는 남긴다")
        self.assertEqual(p["제안배송비"], p["요율"] + p["포장비"])
        self.assertEqual(p["제안배송비"], 11600, "8,500 + 3,100 — 할증 600 은 더하지 않는다")

    def test_세변합만_있어도_받는다(self):
        p = R.plan_product(entry(세변합=170))
        self.assertEqual(p["세변합"], 170.0)
        self.assertTrue(p["화물"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
