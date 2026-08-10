#!/usr/bin/env python3
"""spec_match.py 회귀 테스트 (stdlib unittest — pytest 불필요).

실행: python test_spec_match.py   (또는 python -m unittest test_spec_match -v)

대상은 2026-08-05 설계 결정(00-system/04-specs/2026-08-05-상품명-대표옵션-규격어-design.md):
  규격어가 붙은 저상품수 키워드를 쓸 때, 그 규격이 대표옵션의 규격과 같아야 한다.
  발단 = U01KR7VXBA7SF37GR6XHZ9VTVGH 상품명 `3단`인데 대표옵션은 2단 퇴식카트.
"""
import sys
import unittest

for _s in (sys.stdout, sys.stderr):  # 콘솔 cp949 에서 한글 테스트명이 깨지지 않게
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

import spec_match  # noqa: E402


def _v(vid, name, cn):
    return {"vid": vid, "name": name, "_name": cn}


class ExtractTest(unittest.TestCase):
    """규격어 추출 — 수량+단위 · 소재어 · 치수. 크기어는 제외(이룸님 2026-08-05)."""

    def test_수량단위를_뽑는다(self):
        self.assertEqual(spec_match.extract("3단서빙카트"), ["3단"])
        self.assertEqual(spec_match.extract("3인용리클라이너소파"), ["3인용"])
        self.assertEqual(spec_match.extract("9구액자"), ["9구"])

    def test_소재어를_뽑는다(self):
        self.assertEqual(spec_match.extract("스텐사이드테이블"), ["스텐"])
        self.assertEqual(spec_match.extract("거실원목장식장"), ["원목"])

    def test_치수를_뽑는다(self):
        self.assertEqual(spec_match.extract("서빙카트스텐600주방"), ["스텐"])
        self.assertEqual(spec_match.extract("60cm선반"), ["60cm"])
        self.assertEqual(spec_match.extract("15l휴지통"), ["15l"])

    def test_크기어는_뽑지_않는다(self):
        """대형/중형/소형/미니는 상대 표현이라 옵션 매칭이 불안정하다."""
        self.assertEqual(spec_match.extract("대형우산통"), [])
        self.assertEqual(spec_match.extract("미니사이드테이블"), [])
        self.assertEqual(spec_match.extract("소형에어건"), [])

    def test_규격어가_없으면_빈_목록(self):
        self.assertEqual(spec_match.extract("업소용서빙카트"), [])
        self.assertEqual(spec_match.extract("퇴식카트"), [])

    def test_한_키워드에_여럿이면_모두(self):
        self.assertEqual(spec_match.extract("3단스텐카트"), ["3단", "스텐"])

    def test_미터도_단위다(self):
        """`m` 이 단위 목록에 없어서 `인조잔디2m` 의 규격어가 통째로 빠졌다 (2026-08-10)."""
        self.assertEqual(spec_match.extract("인조잔디2m"), ["2m"])
        self.assertEqual(spec_match.extract("인조잔디25m"), ["25m"])
        # `mm`·`ml` 이 `m` 으로 먼저 잘리면 안 된다 — 단위 대안 순서가 지켜지는지
        self.assertEqual(spec_match.extract("3mm아크릴"), ["3mm"])
        self.assertEqual(spec_match.extract("500ml물병"), ["500ml"])
        # 영문에 얹힌 숫자는 규격이 아니다
        self.assertEqual(spec_match.extract("xmax300등받이"), [])


class VariantTest(unittest.TestCase):
    """한중 정규화 — 규칙 6이 한국어 이름에서 공통 정보를 지우므로 원문을 함께 본다."""

    def test_단과_층은_같은_말이다(self):
        ko, cn = spec_match.variants("3단")
        self.assertIn("3단", ko)
        self.assertIn("3층", ko)
        self.assertIn("3层", cn)

    def test_인용과_인은_같은_말이다(self):
        ko, cn = spec_match.variants("3인용")
        self.assertIn("3인", ko)
        self.assertIn("3人", cn)

    def test_스텐_계열은_불수강으로(self):
        for t in ("스텐", "스테인리스", "스테인레스"):
            ko, cn = spec_match.variants(t)
            self.assertIn("不锈钢", cn)
            self.assertIn("스테인리스", ko)

    def test_원목은_실목_원목_수종까지(self):
        ko, cn = spec_match.variants("원목")
        self.assertIn("우드", ko)
        for c in ("实木", "原木", "松木"):
            self.assertIn(c, cn)

    def test_2단은_쌍층_이중까지_본다(self):
        """2는 한자로 `二` 보다 `双` 을 더 자주 쓴다 (2026-08-07 3-2 클린룸 대차).

        옵션 원문이 `400*400*850双层`, 기계번역 이름이 `이중` 이라 이게 없으면
        옵션에 双层/三层/四层 이 나란히 있는데도 `2단` 이 (다)=근거없음으로 떨어진다.
        """
        ko, cn = spec_match.variants("2단")
        self.assertIn("双层", cn)
        self.assertIn("二层", cn)
        self.assertIn("이중", ko)

    def test_겹도_단_층과_같은_말이다(self):
        """`三层` 의 기계번역이 `3겹` 으로 나온다."""
        ko, cn = spec_match.variants("3층")
        self.assertIn("3겹", ko)
        self.assertEqual(spec_match.extract("3겹선반"), ["3겹"])

    def test_双_단독은_넣지_않는다(self):
        """`双人`(2인)·`双色`(2색)처럼 층수와 무관한 말에 걸린다."""
        _, cn = spec_match.variants("2단")
        self.assertNotIn("双", cn)

    def test_3단은_쌍층을_보지_않는다(self):
        _, cn = spec_match.variants("3단")
        self.assertNotIn("双层", cn)


class MatchTest(unittest.TestCase):
    """숫자 경계 — `3단` 이 `13단` 에 걸리면 안 된다."""

    def test_앞자리_숫자가_붙으면_매칭하지_않는다(self):
        self.assertFalse(spec_match.hit("3단", "13단 선반", ""))
        self.assertFalse(spec_match.hit("3층", "", "十三层餐车"))
        self.assertFalse(spec_match.hit("60cm", "160cm 선반", ""))

    def test_정확히_일치하면_매칭한다(self):
        self.assertTrue(spec_match.hit("3단", "3단 소형 카트", ""))
        self.assertTrue(spec_match.hit("3단", "", "三层小号收碗车"))
        self.assertTrue(spec_match.hit("3단", "3층 대형 카트", ""))

    def test_한자_숫자도_읽는다(self):
        self.assertTrue(spec_match.hit("2단", "", "二层小号餐车(加厚静音轮)"))
        self.assertTrue(spec_match.hit("4단", "", "四层大号餐车"))

    def test_소재어는_부분일치(self):
        self.assertTrue(spec_match.hit("스텐", "", "【不锈钢特厚】小号收碗车"))
        self.assertTrue(spec_match.hit("스텐", "스테인리스 소형 카트", ""))

    def test_뒤에_다른_치수가_붙어도_매칭한다(self):
        """공백을 지우고 비교하므로 `500kg 7.6m` 은 `500kg7.6m` 이 된다.

        뒤 경계로 숫자까지 막으면 이게 통째로 죽어 500kg 윈치가 (나)로 떨어졌다
        (2026-08-10 용쌤2-1). 글자만 막는다.
        """
        self.assertTrue(spec_match.hit("500kg", "무선 500kg 7.6m", ""))
        self.assertTrue(spec_match.hit("2m", "폭 2m 10장", ""))
        self.assertFalse(spec_match.hit("2m", "2mode 자동", ""))
        self.assertFalse(spec_match.hit("500kg", "무선 1500kg 7.6m", ""))

    def test_미터는_한자_米로도_본다(self):
        self.assertTrue(spec_match.hit("25m", "", "60米遥控100公斤25米"))
        self.assertTrue(spec_match.hit("2m", "", "长度二米"))


def _dim(name, values):
    return {"이름": name, "values": values}


class ClassifyTest(unittest.TestCase):
    """(가) 갈리는 값 / (나) 전 옵션 공통·제목에만 / (다) 근거 없음.

    값키는 `option_rules` 와 같은 `@차원인덱스:vid` 규약.
    """

    # 발단 사례 — 옵션이 2층/3층으로 갈린다
    CART = [_dim("제품 종류", [
        _v(1, "소형 식당카트 2층", "二层小号餐车(加厚静音轮)"),
        _v(4, "소형 식당카트 3층", "三层小号餐车(加厚静音轮)"),
        _v(10, "소형 식기수거카트", "小号收碗车(特厚静音轮)"),
        _v(35, "3단 소형 식기수거카트", "三层小号收碗车(加厚静音轮)"),
    ])]

    def test_가_일부_옵션만_해당하면_갈리는_값(self):
        판정, keys = spec_match.classify(
            "3단", self.CART,
            상품명="음식점 서빙 카트 3단",
            원문명="包邮加厚酒店餐车三层不锈钢送餐车收碗车")
        self.assertEqual(판정, "가")
        self.assertEqual(sorted(keys), ["@0:35", "@0:4"])

    def test_나_전_옵션_공통이면_변별값이_아니다(self):
        dims = [_dim("색상", [_v(1, "블랙", "黑色三层"), _v(2, "화이트", "白色三层")])]
        판정, keys = spec_match.classify("3단", dims, 상품명="3단 선반", 원문명="三层置物架")
        self.assertEqual(판정, "나")
        self.assertEqual(keys, [])

    def test_나_옵션에_없어도_제목에_있으면_공통_속성(self):
        """규칙 6이 전 옵션 공통 정보를 이름에서 지운다 — 제목이 마지막 근거."""
        dims = [_dim("색상", [_v(1, "블랙", "黑色"), _v(2, "화이트", "白色")])]
        판정, keys = spec_match.classify("3단", dims, 상품명="3단 선반", 원문명="三层置物架")
        self.assertEqual(판정, "나")
        self.assertEqual(keys, [])

    def test_값이_하나뿐인_차원은_선택지가_아니다(self):
        """복합옵션의 `레이어 수(1개)` 같은 축 — 전 옵션 공통이라 (나)."""
        dims = [_dim("색상", [_v(1, "블랙", "黑色"), _v(2, "화이트", "白色")]),
                _dim("레이어 수", [_v(1, "2단", "两层")])]
        판정, keys = spec_match.classify("2단", dims, 상품명="선반", 원문명="置物架")
        self.assertEqual(판정, "나")
        self.assertEqual(keys, [])

    def test_복합옵션은_해당_차원의_값키만_준다(self):
        dims = [_dim("크기", [_v(1, "소형", "小"), _v(2, "대형", "大")]),
                _dim("소재", [_v(1, "원목", "实木"), _v(2, "철제", "铁艺")])]
        판정, keys = spec_match.classify("원목", dims, 상품명="", 원문명="")
        self.assertEqual(판정, "가")
        self.assertEqual(keys, ["@1:1"])

    def test_다_옵션에도_제목에도_없으면_근거_없음(self):
        dims = [_dim("색상", [_v(1, "블랙", "黑色"), _v(2, "화이트", "白色")])]
        판정, keys = spec_match.classify("3단", dims, 상품명="예쁜 선반", 원문명="置物架")
        self.assertEqual(판정, "다")

    def test_차원이_비어도_제목_근거면_나(self):
        판정, _ = spec_match.classify("3단", [], 상품명="3단 선반", 원문명="")
        self.assertEqual(판정, "나")


class AnalyzeTest(unittest.TestCase):
    """배치에 실을 `규격후보` — 스크립트가 계산하고 워커는 확인만 한다."""

    DIMS = ClassifyTest.CART
    ROWS = [
        {"id": "1", "sale_price": 64800, "exclude": True},
        {"id": "4", "sale_price": 72400, "exclude": True},
        {"id": "10", "sale_price": 88000, "exclude": False},
        {"id": "35", "sale_price": 101500, "exclude": False},
    ]

    def test_규격축과_가격범위를_담는다(self):
        out = spec_match.analyze(
            ["3단서빙카트", "퇴식카트"], self.DIMS, self.ROWS,
            상품명="음식점 서빙 카트 3단", 원문명="包邮加厚酒店餐车三层收碗车")
        self.assertEqual(out["가격범위"], [64800, 101500])
        축 = {a["규격"]: a for a in out["규격축"]}
        self.assertEqual(축["3단"]["판정"], "가")
        self.assertEqual(sorted(축["3단"]["값키"]), ["@0:35", "@0:4"])

    def test_옵션전량에_원문과_가격이_실린다(self):
        out = spec_match.analyze(["3단서빙카트"], self.DIMS, self.ROWS,
                                 상품명="", 원문명="")
        row = {o["id"]: o for o in out["옵션전량"]}
        self.assertEqual(row["35"]["원문"], "三层小号收碗车(加厚静音轮)")
        self.assertEqual(row["35"]["가격"], 101500)
        self.assertTrue(row["1"]["제외"])

    def test_규격어가_없으면_규격축이_비어_있다(self):
        out = spec_match.analyze(
            ["퇴식카트", "업소용서빙카트"], self.DIMS, self.ROWS,
            상품명="퇴식카트", 원문명="收碗车")
        self.assertEqual(out["규격축"], [])

    def test_옵션_전량을_싣고_상한을_넘으면_생략수를_남긴다(self):
        """`_OPT_MAX = 8`(정체판별용)과 별개 — 규격 판단은 전량을 봐야 한다.
        생략은 반드시 표면화한다(조용한 절단 금지)."""
        many_vals = [_v(i, f"값{i}", f"选项{i}") for i in range(spec_match.OPT_LIST_MAX + 5)]
        many_rows = [{"id": str(i), "sale_price": 1000 + i, "exclude": False}
                     for i in range(spec_match.OPT_LIST_MAX + 5)]
        out = spec_match.analyze(
            ["3단선반"], [_dim("종류", many_vals)], many_rows,
            상품명="3단 선반", 원문명="三层架")
        self.assertEqual(len(out["옵션전량"]), spec_match.OPT_LIST_MAX)
        self.assertEqual(out["생략"], 5)

    def test_상한_이하면_생략이_0(self):
        out = spec_match.analyze(
            ["3단서빙카트"], self.DIMS, self.ROWS,
            상품명="카트", 원문명="餐车")
        self.assertEqual(out["생략"], 0)
        self.assertEqual(len(out["옵션전량"]), 4)


class PickTest(unittest.TestCase):
    """(가)일 때 대표 후보 = 매칭 옵션 중 최저가."""

    def test_매칭_옵션_중_최저가를_고른다(self):
        rows = [{"id": "4", "sale_price": 72400}, {"id": "35", "sale_price": 101500}]
        self.assertEqual(spec_match.pick_main(["@0:4", "@0:35"], rows), "4")

    def test_가격이_없는_옵션은_후보에서_뺀다(self):
        rows = [{"id": "4", "sale_price": None}, {"id": "35", "sale_price": 101500}]
        self.assertEqual(spec_match.pick_main(["@0:4", "@0:35"], rows), "35")

    def test_후보가_전부_가격이_없으면_None(self):
        rows = [{"id": "4", "sale_price": None}]
        self.assertIsNone(spec_match.pick_main(["@0:4"], rows))

    def test_유지_집합을_주면_교집합에서만_고른다(self):
        """발단 사례 — `3단` 이 3층 식기수거카트(35, 유지)와 3층 훠궈카트(44, 제외)에
        동시에 걸린다. 훠궈가 더 싸므로 유지를 모르면 훠궈가 대표가 된다."""
        rows = [{"id": "35", "sale_price": 101500}, {"id": "44", "sale_price": 45200}]
        keys = ["@0:35", "@0:44"]
        self.assertEqual(spec_match.pick_main(keys, rows), "44")
        self.assertEqual(spec_match.pick_main(keys, rows, keep={"35"}), "35")

    def test_유지와_겹치는_후보가_없으면_None_대표충돌(self):
        rows = [{"id": "44", "sale_price": 45200}]
        self.assertIsNone(spec_match.pick_main(["@0:44"], rows, keep={"10", "35"}))

    def test_복합옵션은_해당_차원_자리만_본다(self):
        """판매행 id `3:1` — 차원0 vid 3 × 차원1 vid 1."""
        rows = [{"id": "1:1", "sale_price": 50000}, {"id": "2:1", "sale_price": 40000},
                {"id": "1:2", "sale_price": 60000}]
        self.assertEqual(spec_match.pick_main(["@0:1"], rows), "1:1")
        self.assertEqual(spec_match.pick_main(["@1:1"], rows), "2:1")
        self.assertEqual(
            sorted(r["id"] for r in spec_match.rows_for(["@1:1"], rows)), ["1:1", "2:1"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
