#!/usr/bin/env python3
"""옵션 정리 규칙 회귀 테스트 — 불사자·시트 없이 돈다.

    python .claude/skills/bulsaja-option-cleanup/scripts/test_option_rules.py

매출에 직결되는 규칙이라(무엇을 팔고 무엇을 내리고 어느 가격을 대표로 세우나)
계산 부분은 전부 여기서 고정한다.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import option_rules as R  # noqa: E402


def row(i, price, stock=100, exclude=False, main=False):
    return {"id": str(i), "text": f"opt{i}", "_text": f"选项{i}", "sale_price": price,
            "origin_price": price // 2, "stock": stock, "exclude": exclude,
            "main_product": main, "urlRef": ""}


def opt(rows, dims=None, vid_unique=True):
    return {"차원": dims if dims is not None else [
        {"이름": "종류", "원문이름": "类", "values": [
            {"vid": int(r["id"]), "name": r.get("text", ""), "_name": r.get("_text", ""),
             "imageUrl": "", "exclude": r.get("exclude", False)} for r in rows]}],
        "판매행": rows, "vid고유": vid_unique}


class NameTest(unittest.TestCase):
    def test_접두사만_벗기고_사이즈는_보존한다(self):
        self.assertEqual(R.strip_prefix("A. 블랙 수트"), "블랙 수트")
        self.assertEqual(R.strip_prefix("H) 화이트"), "화이트")
        self.assertEqual(R.strip_prefix("S/M/L"), "S/M/L", "사이즈를 접두사로 오인했다")
        self.assertEqual(R.strip_prefix("XL 롱패딩"), "XL 롱패딩")

    def test_25자_초과와_중국어와_접두사를_잡는다(self):
        self.assertEqual(R.name_problems("블랙 3단 선반"), [])
        self.assertIn("중국어 잔존", R.name_problems("블랙 增压泵"))
        self.assertIn("정렬용 접두사 잔존", R.name_problems("A. 블랙"))
        p = R.name_problems("가" * 26)
        self.assertTrue(any("26자" in x for x in p))
        self.assertEqual(R.name_problems(""), ["빈 이름"])

    def test_25자는_공백_포함해_센다(self):
        self.assertEqual(R.name_problems("가" * 25), [])
        self.assertTrue(R.name_problems("가" * 24 + " 나"))

    def test_중복은_같은_차원_안에서만_본다(self):
        names = {"1": "블랙", "2": "블랙"}
        self.assertTrue(R.check_names(names, groups={"1": 0, "2": 0})["중복"])
        self.assertFalse(R.check_names(names, groups={"1": 0, "2": 1})["중복"],
                         "차원이 다르면 같은 이름이 정상이다")


class PlanTest(unittest.TestCase):
    def test_최저가가_대표가_되고_1_5배가_상한이_된다(self):
        rows = [row(1, 10000), row(2, 14000), row(3, 16000)]
        p = R.plan(opt(rows), keep_ids={"1", "2", "3"})
        self.assertEqual(p["대표"], "1")
        self.assertEqual(p["기준가"], 10000)
        self.assertEqual(p["상한"], 15000)
        self.assertEqual(p["유지"], ["1", "2"])
        self.assertIn("1.5배 상한 초과", next(
            e["사유"] for e in p["제외"] if e["id"] == "3"))

    def test_상한과_같은_값은_유지한다(self):
        rows = [row(1, 10000), row(2, 15000)]
        p = R.plan(opt(rows), keep_ids={"1", "2"})
        self.assertEqual(p["유지"], ["1", "2"], "같은 값 포함 규칙이 안 지켜졌다")

    def test_비상품은_기준가_계산에서_아예_빠진다(self):
        # 500원짜리 부속품이 섞여 있으면 상한이 750원이 되어 본품이 전멸한다
        rows = [row(99, 500), row(1, 10000), row(2, 14000)]
        p = R.plan(opt(rows), keep_ids={"1", "2"})
        self.assertEqual(p["기준가"], 10000)
        self.assertEqual(p["유지"], ["1", "2"])
        self.assertEqual(next(e["사유"] for e in p["제외"] if e["id"] == "99"),
                         "비상품/메인상품 아님")

    def test_판매가_오름차순이고_동가는_원본_순서다(self):
        rows = [row(1, 14000), row(2, 10000), row(3, 10000)]
        p = R.plan(opt(rows), keep_ids={"1", "2", "3"})
        self.assertEqual(p["순서"], ["2", "3", "1"])
        self.assertEqual(p["대표"], "2", "동가면 원본 순서가 앞선 쪽")

    def test_재고_0은_판매불가로_빠진다(self):
        rows = [row(1, 10000, stock=0), row(2, 12000)]
        p = R.plan(opt(rows), keep_ids={"1", "2"})
        self.assertEqual(p["대표"], "2", "재고 0을 대표로 세웠다")
        self.assertIn("판매불가", next(e["사유"] for e in p["제외"] if e["id"] == "1"))

    def test_동률일_때_지정한_대표를_쓴다(self):
        rows = [row(1, 10000), row(2, 10000)]
        p = R.plan(opt(rows), keep_ids={"1", "2"}, prefer_id="2")
        self.assertEqual(p["대표"], "2")
        self.assertEqual(p["순서"][0], "2", "대표가 정렬 첫 번째여야 한다")

    def test_더_비싼_옵션을_대표로_올리지_않는다(self):
        rows = [row(1, 10000), row(2, 12000)]
        p = R.plan(opt(rows), keep_ids={"1", "2"}, prefer_id="2")
        self.assertEqual(p["대표"], "1")
        self.assertTrue(any("최저가가 아니라 무시" in w for w in p["경고"]))

    def test_동률인데_지정이_없으면_경고한다(self):
        rows = [row(1, 10000), row(2, 10000)]
        p = R.plan(opt(rows), keep_ids={"1", "2"})
        self.assertTrue(any("최저가 동률" in w for w in p["경고"]))

    def test_남길_게_없으면_경고하고_대표를_비운다(self):
        rows = [row(1, 10000)]
        p = R.plan(opt(rows), keep_ids=set())
        self.assertIsNone(p["대표"])
        self.assertTrue(any("저장하면 안 된다" in w for w in p["경고"]))

    def test_가격이_없으면_판매불가로_뺀다(self):
        rows = [row(1, 10000), {"id": "2", "sale_price": None, "stock": 5}]
        p = R.plan(opt(rows), keep_ids={"1", "2"})
        self.assertEqual(p["유지"], ["1"])


class RenameTargetTest(unittest.TestCase):
    def test_vid가_고유하면_vid로_지정한다(self):
        rows = [row(11, 1000), row(22, 2000)]
        items, missing = R.rename_targets(opt(rows), {"11": "블랙", "22": "화이트"})
        self.assertEqual(missing, [])
        self.assertEqual(items, [{"vid": 11, "name": "블랙"}, {"vid": 22, "name": "화이트"}])

    def test_복합옵션은_차원_인덱스로_지정한다(self):
        dims = [{"이름": "조명", "values": [{"vid": 1, "name": "없음"}]},
                {"이름": "색상", "values": [{"vid": 1, "name": "검정"},
                                          {"vid": 2, "name": "흰색"}]}]
        o = {"차원": dims, "판매행": [], "vid고유": False}
        items, missing = R.rename_targets(o, {"2": "아이보리"})
        self.assertEqual(items, [{"groupIndex": 1, "valueIndex": 1, "name": "아이보리"}],
                         "vid 로 지정하면 엉뚱한 차원이 바뀐다")

    def test_없는_키는_조용히_넘기지_않고_알려준다(self):
        rows = [row(11, 1000)]
        items, missing = R.rename_targets(opt(rows), {"999": "x"})
        self.assertEqual(items, [])
        self.assertEqual(missing, ["999"])

    def test_위치키로_복합옵션_2번째_차원을_찍는다(self):
        # 2026-07-30: vid 1 이 두 차원에 다 있어서 vid 로는 도달 불가였던 값
        items, missing = R.rename_targets(_dual(), {"@1:1": "검정 기본형"})
        self.assertEqual(missing, [])
        self.assertEqual(items, [{"groupIndex": 1, "valueIndex": 0,
                                  "name": "검정 기본형"}])

    def test_두_차원에_겹치는_vid는_모호해서_거부한다(self):
        items, missing = R.rename_targets(_dual(), {"1": "검정 기본형"})
        self.assertEqual(items, [])
        self.assertEqual(missing, ["1"],
                         "첫 차원으로 조용히 붙으면 엉뚱한 차원이 바뀐다")

    def test_위치키에_없는_좌표를_주면_알려준다(self):
        items, missing = R.rename_targets(_dual(), {"@9:1": "x"})
        self.assertEqual(items, [])
        self.assertEqual(missing, ["@9:1"])


def _dual():
    """복합옵션 — vid 1 이 두 차원에 겹친다(vid고유=False). 판매행 id 는 조합키."""
    return {
        "차원": [
            {"이름": "조명", "원문이름": "", "values": [
                {"vid": 1, "name": "없음", "_name": "", "imageUrl": "", "exclude": False}]},
            {"이름": "색상", "원문이름": "", "values": [
                {"vid": 1, "name": "검정", "_name": "", "imageUrl": "", "exclude": False},
                {"vid": 2, "name": "흰색", "_name": "", "imageUrl": "", "exclude": False}]},
        ],
        "판매행": [
            {"id": "1:1", "text": "없음 / 검정", "_text": "", "sale_price": 10000,
             "origin_price": 5000, "stock": 5, "exclude": False,
             "main_product": False, "urlRef": ""},
            {"id": "1:2", "text": "없음 / 흰색", "_text": "", "sale_price": 12000,
             "origin_price": 6000, "stock": 5, "exclude": False,
             "main_product": False, "urlRef": ""},
        ],
        "vid고유": False,
    }


class BaseSuffixTest(unittest.TestCase):
    """대표옵션 마커 `기본형` — 2026-07-30 이룸님.

    네이버는 '대표상품'(추가금 0원 옵션)을 상품명으로 쓰라고 요구한다. 상품명 끝과
    대표옵션명 끝에 같은 단어를 붙여 짝을 지목하는 게 이 규칙의 목적이다.
    """

    def test_1차원은_판매행id가_곧_vid다(self):
        key, err = R.main_value_key(opt([row(1, 10000), row(2, 14000)]), "1")
        self.assertEqual(err, "")
        self.assertEqual(key, "@0:1")

    def test_복합옵션은_마지막_차원에_붙인다(self):
        key, err = R.main_value_key(_dual(), "1:1")
        self.assertEqual(err, "")
        self.assertEqual(key, "@1:1", "마지막 차원(색상)의 값이어야 한다")

    def test_판매행id_조각수가_차원수와_다르면_오류다(self):
        key, err = R.main_value_key(opt([row(1, 10000)]), "1:1")
        self.assertEqual(key, "")
        self.assertIn("차원", err)

    def test_대표가_없으면_오류다(self):
        key, err = R.main_value_key(opt([row(1, 10000)]), "")
        self.assertEqual(key, "")
        self.assertIn("대표", err)

    def test_대표에만_붙으면_통과한다(self):
        o = opt([row(1, 10000), row(2, 14000)])
        r = R.check_base_suffix(o, {"1": "블랙 기본형", "2": "화이트"}, "@0:1")
        self.assertFalse(r["누락"])
        self.assertEqual(r["오부착"], [])

    def test_대표에_없으면_누락이다(self):
        o = opt([row(1, 10000), row(2, 14000)])
        r = R.check_base_suffix(o, {"1": "블랙", "2": "화이트"}, "@0:1")
        self.assertTrue(r["누락"])

    def test_대표가_아닌_옵션에_붙으면_오부착이다(self):
        o = opt([row(1, 10000), row(2, 14000)])
        r = R.check_base_suffix(o, {"1": "블랙 기본형", "2": "화이트 기본형"}, "@0:1")
        self.assertEqual(r["오부착"], ["@0:2"])

    def test_안_바꾸는_옵션의_현재이름도_본다(self):
        # names 에 없어도 이미 '기본형'을 달고 있으면 짝이 흐려진다
        o = opt([row(1, 10000), row(2, 14000)])
        o["차원"][0]["values"][1]["name"] = "화이트 기본형"
        r = R.check_base_suffix(o, {"1": "블랙 기본형"}, "@0:1")
        self.assertEqual(r["오부착"], ["@0:2"])

    def test_plan이_대표값키와_마커검사를_같이_준다(self):
        o = opt([row(1, 10000), row(2, 14000)])
        p = R.plan(o, keep_ids={"1", "2"}, names={"1": "블랙", "2": "화이트"})
        self.assertEqual(p["대표값키"], "@0:1")
        self.assertTrue(p["이름검사"]["마커"]["누락"],
                        "기본형이 없으면 누락으로 잡아야 한다")

    def test_plan이_붙은_이름은_통과시킨다(self):
        o = opt([row(1, 10000), row(2, 14000)])
        p = R.plan(o, keep_ids={"1", "2"},
                   names={"1": "블랙 기본형", "2": "화이트"})
        self.assertFalse(p["이름검사"]["마커"]["누락"])
        self.assertEqual(p["이름검사"]["마커"]["오부착"], [])

    def test_모호한_vid는_정규화가_거부한다(self):
        self.assertEqual(R.normalize_key(_dual(), "1"), "")
        self.assertEqual(R.normalize_key(_dual(), "2"), "@1:2")
        self.assertEqual(R.normalize_key(_dual(), "@0:1"), "@0:1")

    def test_25자는_기본형을_포함해_센다(self):
        # 결정 2(2026-07-30): 상한을 늘리지 않고 본문을 줄여 흡수한다
        self.assertEqual(R.name_problems("가" * 21 + " 기본형"), [])
        self.assertTrue(R.name_problems("가" * 22 + " 기본형"))


class VerifyBaseSuffixTest(unittest.TestCase):
    """저장 후 검증 — 마커는 `names` 를 넘길 때만 본다(실제 저장 경로가 그렇다)."""

    def setUp(self):
        self.before = opt([row(1, 10000), row(2, 14000)])
        self.plan = R.plan(self.before, keep_ids={"1", "2"})

    def _after(self, n1, n2):
        rows = [row(1, 10000, main=True), row(2, 14000)]
        o = opt(rows)
        o["차원"][0]["values"][0]["name"] = n1
        o["차원"][0]["values"][1]["name"] = n2
        return o

    def test_대표에_기본형이_있으면_통과한다(self):
        a = self._after("블랙 기본형", "화이트")
        self.assertEqual(R.verify(self.before, a, self.plan, names={"1": "블랙 기본형"}), [])

    def test_대표에_기본형이_없으면_잡는다(self):
        a = self._after("블랙", "화이트")
        f = R.verify(self.before, a, self.plan, names={"1": "블랙"})
        self.assertTrue(any("기본형" in x for x in f))

    def test_대표가_아닌_옵션에_붙어_있으면_잡는다(self):
        a = self._after("블랙 기본형", "화이트 기본형")
        f = R.verify(self.before, a, self.plan, names={"1": "블랙 기본형"})
        self.assertTrue(any("대표가 아닌" in x for x in f))

    def test_names가_없으면_마커를_보지_않는다(self):
        # 이름을 안 바꾸는 저장(포함/제외·순서만)에서 마커로 실패시키지 않는다
        a = self._after("블랙", "화이트")
        self.assertEqual(R.verify(self.before, a, self.plan), [])


class VerifyTest(unittest.TestCase):
    def setUp(self):
        self.before = opt([row(1, 10000), row(2, 14000), row(3, 20000)])
        self.plan = R.plan(self.before, keep_ids={"1", "2", "3"})

    def _after(self, **over):
        rows = [row(1, 10000, main=True), row(2, 14000),
                row(3, 20000, exclude=True)]
        for i, changes in over.items():
            for r in rows:
                if r["id"] == i:
                    r.update(changes)
        return opt(rows)

    def test_계획대로면_통과한다(self):
        self.assertEqual(R.verify(self.before, self._after(), self.plan), [])

    def test_대표가_없으면_잡는다(self):
        a = self._after(**{"1": {"main_product": False}})
        self.assertTrue(any("대표옵션이 0개" in f for f in R.verify(self.before, a, self.plan)))

    def test_대표가_판매제외면_잡는다(self):
        a = self._after(**{"1": {"exclude": True}})
        f = R.verify(self.before, a, self.plan)
        self.assertTrue(any("판매 포함이 다르다" in x or "판매 제외 상태" in x for x in f))

    def test_상한_초과가_살아있으면_잡는다(self):
        a = self._after(**{"3": {"exclude": False}})
        f = R.verify(self.before, a, self.plan)
        self.assertTrue(any("판매 포함이 다르다" in x for x in f))

    def test_판매가가_바뀌면_잡는다(self):
        a = self._after(**{"2": {"sale_price": 99000}})
        self.assertTrue(any("판매가가 바뀐" in x for x in R.verify(self.before, a, self.plan)))

    def test_옵션_수가_바뀌면_잡는다(self):
        a = opt([row(1, 10000, main=True)])
        self.assertTrue(any("옵션 수가 바뀌었다" in x for x in R.verify(self.before, a, self.plan)))

    def test_표시명이_겹치면_잡는다(self):
        a = self._after(**{"2": {"text": "opt1"}})
        self.assertTrue(any("표시명이 겹친다" in x for x in R.verify(self.before, a, self.plan)))


class LabelTest(unittest.TestCase):
    """승인 자료용 라벨 — id 만 보고는 승인할 수 없다."""

    def test_1차원은_교정_이름이_판매행에_그대로_붙는다(self):
        o = opt([row(1, 10000), row(2, 20000)])
        lab = R.row_labels(o, {"1": "A형 스탠드형", "2": "A형 벽걸이형"})
        self.assertEqual(lab["1"], "A형 스탠드형")
        self.assertEqual(lab["2"], "A형 벽걸이형")

    def test_교정_이름이_없으면_현재_표시명을_쓴다(self):
        o = opt([row(1, 10000)])
        self.assertEqual(R.row_labels(o, {})["1"], "opt1")

    def test_복합옵션은_표시명_안의_옛_이름을_바꿔_끼운다(self):
        rows = [{"id": "1:1", "text": "블랙 / 대형", "_text": "", "sale_price": 1000,
                 "stock": 5, "exclude": False, "main_product": False}]
        dims = [{"이름": "색상", "values": [{"vid": 1, "name": "블랙", "_name": "黑"}]},
                {"이름": "크기", "values": [{"vid": 2, "name": "대형", "_name": "大"}]}]
        o = {"차원": dims, "판매행": rows, "vid고유": True}
        lab = R.row_labels(o, {"1": "무광 블랙", "2": "라지"})
        self.assertEqual(lab["1:1"], "무광 블랙 / 라지")

    def test_긴_이름부터_치환해_짧은_이름이_먼저_먹지_않는다(self):
        rows = [{"id": "1:1", "text": "블랙에디션 / 블랙", "sale_price": 1000,
                 "stock": 5, "exclude": False, "main_product": False}]
        dims = [{"이름": "모델", "values": [{"vid": 1, "name": "블랙에디션"}]},
                {"이름": "색상", "values": [{"vid": 2, "name": "블랙"}]}]
        o = {"차원": dims, "판매행": rows, "vid고유": True}
        lab = R.row_labels(o, {"1": "프로", "2": "차콜"})
        self.assertEqual(lab["1:1"], "프로 / 차콜")

    def test_이름변경표는_안_바뀐_것도_남긴다(self):
        o = opt([row(1, 10000), row(2, 20000)])
        chg = {c["키"]: c for c in R.name_changes(o, {"1": "스탠드형", "2": "opt2"})}
        self.assertTrue(chg["1"]["변경"])
        self.assertEqual(chg["1"]["기존"], "opt1")
        self.assertFalse(chg["2"]["변경"], "같은 이름인데 변경으로 셌다")
        self.assertEqual(chg["1"]["차원"], "종류")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    unittest.main(verbosity=2)
