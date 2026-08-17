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
                         R.DROP_REASON_MISSING)

    def test_워커가_미리_뺀_상한초과분에_가격_근거를_되살린다(self):
        """`유지` 에 넣었어야 할 큰 규격을 워커가 손으로 빼 오면 사유가 뭉개진다.

        2026-08-14 3-2 실측: 150cm 공원벤치·3x3m 갠트리크레인이 전부
        `비상품/메인상품 아님` 으로만 찍혀 왜 안 파는지가 사라졌다.
        저장 결과는 같으므로 막지 않고 사유에 가격 사실만 덧붙인다.
        """
        rows = [row(1, 10000), row(2, 14000), row(3, 30000)]
        p = R.plan(opt(rows), keep_ids={"1", "2"})   # 워커가 3(상한 초과)을 먼저 뺐다
        why = next(e["사유"] for e in p["제외"] if e["id"] == "3")
        self.assertIn("비상품/메인상품 아님", why)
        self.assertIn("1.5배 상한 초과", why)
        self.assertIn("30,000원 > 15,000원", why)

    def test_싼_부속품에는_가격_근거를_붙이지_않는다(self):
        """부속품은 원래 하한 아래다 — 붙이면 정상 제외가 워커 실수로 읽힌다."""
        rows = [row(99, 500), row(1, 10000), row(2, 14000)]
        p = R.plan(opt(rows), keep_ids={"1", "2"})
        self.assertEqual(next(e["사유"] for e in p["제외"] if e["id"] == "99"),
                         R.DROP_REASON_MISSING)

    def test_스크립트가_직접_뺀_건은_사유가_한_번만_붙는다(self):
        """`유지` 에 정상적으로 들어온 상한 초과분 — 종전 사유 그대로다."""
        rows = [row(1, 10000), row(2, 30000)]
        p = R.plan(opt(rows), keep_ids={"1", "2"})
        why = next(e["사유"] for e in p["제외"] if e["id"] == "2")
        self.assertNotIn("비상품", why)
        self.assertEqual(why.count("1.5배 상한 초과"), 1)

    def test_워커가_쓴_제외_사유가_원장에_남는다(self):
        """2026-08-15 — 워커 사유를 버리고 고정 문자열로 덮어써 매 런 2,772건이 사라졌다."""
        rows = [row(1, 10000), row(99, 3000)]
        p = R.plan(opt(rows), keep_ids={"1"},
                   drop_reasons={"99": "부속품단독: 원문 '单独顶（无支架）' — 지붕만, 프레임 미포함"})
        self.assertEqual(next(e["사유"] for e in p["제외"] if e["id"] == "99"),
                         "부속품단독: 원문 '单独顶（无支架）' — 지붕만, 프레임 미포함")

    def test_사유를_안_준_행만_미기재로_표시된다(self):
        """정당한 제외와 '워커가 사유를 안 썼다'가 원장에서 구분돼야 한다."""
        rows = [row(1, 10000), row(98, 3000), row(99, 2000)]
        p = R.plan(opt(rows), keep_ids={"1"}, drop_reasons={"98": "사이즈표: 치수 안내행"})
        why = {e["id"]: e["사유"] for e in p["제외"]}
        self.assertEqual(why["98"], "사이즈표: 치수 안내행")
        self.assertEqual(why["99"], R.DROP_REASON_MISSING)
        self.assertIn("사유 미기재", R.DROP_REASON_MISSING)

    def test_파생_사유는_워커가_덮지_못한다(self):
        """1.5배 상한·재고 0 은 스크립트가 계산한 사실이다 — 워커 문장이 이기면 안 된다."""
        rows = [row(1, 10000), row(2, 30000), row(3, 12000, stock=0)]
        p = R.plan(opt(rows), keep_ids={"1", "2", "3"},
                   drop_reasons={"2": "다른모델: 큰 규격", "3": "홍보배너: 안내문"})
        why = {e["id"]: e["사유"] for e in p["제외"]}
        self.assertIn("1.5배 상한 초과", why["2"])
        self.assertNotIn("다른모델", why["2"])
        self.assertIn("판매불가", why["3"])

    def test_워커_사유에도_상한_초과_가격_근거는_덧붙는다(self):
        rows = [row(1, 10000), row(2, 30000)]
        p = R.plan(opt(rows), keep_ids={"1"}, drop_reasons={"2": "다른모델: 대형 규격"})
        why = next(e["사유"] for e in p["제외"] if e["id"] == "2")
        self.assertIn("다른모델", why)
        self.assertIn("1.5배 상한 초과", why)


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


class WorkerQCTest(unittest.TestCase):
    """워커가 지시서를 지켰는지 **재는** 검사 (2026-08-15, 4-2 발).

    말한 걸 지켰는지 재는 자리가 없으면 지켜지지 않는다 — 4-1 에서 51%가 `제외` 를 비웠고,
    4-2 에서 17건이 금지된 근거를 썼다(손으로 79건을 되돌린 뒤 1건으로 수렴).
    """

    def test_유지_제외_어디에도_없는_판매행을_행_단위로_잡는다(self):
        rows = [row(1, 10000), row(2, 11000), row(3, 12000)]
        qc = R.worker_qc(opt(rows), {"유지": ["1"], "제외": [{"id": "2", "사유": "사이즈표: 안내"}]})
        self.assertEqual(qc["미언급"], ["3"])
        self.assertTrue(qc["위반"])

    def test_전부_적었으면_위반이_아니다(self):
        rows = [row(1, 10000), row(2, 11000)]
        qc = R.worker_qc(opt(rows), {"유지": ["1"],
                                     "제외": [{"id": "2", "사유": "다른모델: 단일모터"}]})
        self.assertEqual(qc["미언급"], [])
        self.assertEqual(qc["무분류수"], 0)
        self.assertFalse(qc["위반"])

    def test_현재상태를_근거로_뺐으면_잡는다(self):
        rows = [row(1, 10000), row(2, 11000)]
        qc = R.worker_qc(opt(rows), {"유지": ["1"], "제외": [
            {"id": "2", "사유": "현재제외 상태 유지 — 최고가·재고 저조"}]})
        self.assertEqual([x["id"] for x in qc["상태근거"]], ["2"])

    def test_상태를_뒤집었다는_서술은_잡지_않는다(self):
        """4-1 에서 12건 중 9건이 이런 정상 건이었다 — 낱말만 보면 정상을 재작업시킨다."""
        rows = [row(1, 10000), row(2, 11000), row(3, 12000)]
        qc = R.worker_qc(opt(rows), {"유지": ["1"], "제외": [
            {"id": "2", "사유": "홍보배너: 우선발송 안내문 — 기존 현재대표였으나 뒤집힘"},
            {"id": "3", "사유": "부속품단독: LED 미포함 — 현재상태는 유지였으나 정정"}]})
        self.assertEqual(qc["상태근거"], [])
        self.assertFalse(qc["위반"])

    def test_분류가_안_붙은_사유를_센다(self):
        rows = [row(1, 10000), row(2, 11000), row(3, 12000)]
        qc = R.worker_qc(opt(rows), {"유지": ["1"], "제외": [
            {"id": "2", "사유": "부속품단독: 원문 单独"},
            {"id": "3", "사유": "그냥 본품이 아님"}]})
        self.assertEqual(qc["무분류수"], 1)


class SpecMainTest(unittest.TestCase):
    """상품명이 규격어로 지정한 대표 (2026-08-05 이룸님).

    발단 = U01KR7VXBA7SF37GR6XHZ9VTVGH — 상품명 `3단`인데 대표옵션은 2단 퇴식카트.
    `prefer_id`(썸네일 최유사, 최저가 동률에만 유효)와 달리 **최저가가 아니어도 수용**한다.
    """

    def test_최저가가_아니어도_지정한_대표를_쓴다(self):
        rows = [row(1, 10000), row(2, 12000), row(3, 14000)]
        p = R.plan(opt(rows), keep_ids={"1", "2", "3"}, spec_main="2")
        self.assertEqual(p["대표"], "2")
        self.assertEqual(p["기준가"], 12000)
        self.assertEqual(p["상한"], 18000, "기준가가 오르면 상한도 오른다(이룸님 감수)")
        self.assertEqual(p["하한"], 6000)
        self.assertNotIn("최저가가 아니라 무시", " ".join(p["경고"]))

    def test_지정한_대표가_정렬_맨_앞이다(self):
        """옵션 목록 첫 항목의 가격이 튀는 것은 감수한다 — 유리한 키워드가 우선."""
        rows = [row(1, 10000), row(2, 12000), row(3, 11000)]
        p = R.plan(opt(rows), keep_ids={"1", "2", "3"}, spec_main="2")
        self.assertEqual(p["순서"], ["2", "1", "3"])

    def test_지정이_없으면_기존대로_최저가다(self):
        rows = [row(1, 10000), row(2, 12000)]
        p = R.plan(opt(rows), keep_ids={"1", "2"})
        self.assertEqual(p["대표"], "1")
        self.assertEqual(p["순서"], ["1", "2"])

    def test_지정_옵션이_제외됐으면_대표충돌로_멈춘다(self):
        """워커가 '메인상품 아님'으로 뺀 옵션을 상품명이 지정 — 판단이 갈린다."""
        rows = [row(1, 10000), row(2, 12000)]
        p = R.plan(opt(rows), keep_ids={"1"}, spec_main="2", spec_keyword="3단서빙카트")
        self.assertIsNotNone(p["대표충돌"])
        self.assertEqual(p["대표충돌"]["지정"], "2")
        self.assertEqual(p["대표충돌"]["근거키워드"], "3단서빙카트")
        self.assertEqual(p["대표충돌"]["사유"], R.DROP_REASON_MISSING)
        self.assertIsNone(p["대표"], "충돌이면 계산하지 않는다")

    def test_대표충돌_사유에_워커_문장이_올라간다(self):
        """`다른모델이 맞다` 와 `잘못 뺐다` 는 사유를 읽어야 갈린다 — 그래서 사유가 정본이다."""
        rows = [row(1, 10000), row(2, 12000)]
        p = R.plan(opt(rows), keep_ids={"1"}, spec_main="2", spec_keyword="3단",
                   drop_reasons={"2": "다른모델: 상품명·대표군은 듀얼모터인데 이 행은 단일모터"})
        self.assertIn("다른모델", p["대표충돌"]["사유"])

    def test_지정_옵션이_재고0이어도_대표충돌이다(self):
        rows = [row(1, 10000), row(2, 12000, stock=0)]
        p = R.plan(opt(rows), keep_ids={"1", "2"}, spec_main="2")
        self.assertIsNotNone(p["대표충돌"])
        self.assertIn("판매불가", p["대표충돌"]["사유"])


class MarkerRetargetTest(unittest.TestCase):
    """대표가 옮겨지면 `기본형` 마커도 따라 옮긴다 (규칙 17 × 규격어 지정).

    워커는 판정 시점에 상품명의 지정을 볼 수 없어 "유지 중 최저가"에 붙여 놓는다.
    안 옮기면 마커가 옛 대표에 남아 전건이 `보류(기본형)` 으로 멈춘다.
    """

    def test_옛_대표에서_떼고_새_대표에_붙인다(self):
        rows = [row(1, 10000), row(2, 12000)]
        names = {"1": "블랙 기본형", "2": "화이트"}
        p = R.plan(opt(rows), keep_ids={"1", "2"}, names=names, spec_main="2")
        # 위치키(`@차원:vid`)로 돌려준다 — `rename_targets` 가 받는 키 규약이다
        self.assertEqual(p["마커이동"], {"@0:1": "블랙", "@0:2": "화이트 기본형"})
        self.assertFalse(p["이름검사"]["마커"]["누락"])
        self.assertEqual(p["이름검사"]["마커"]["오부착"], [])

    def test_규칙16_붙여쓰지_않는다(self):
        rows = [row(1, 10000), row(2, 12000)]
        p = R.plan(opt(rows), keep_ids={"1", "2"},
                   names={"1": "블랙 기본형", "2": "화이트"}, spec_main="2")
        self.assertIn(" 기본형", p["마커이동"]["@0:2"])

    def test_이미_새_대표에_붙어_있으면_그대로다(self):
        rows = [row(1, 10000), row(2, 12000)]
        p = R.plan(opt(rows), keep_ids={"1", "2"},
                   names={"1": "블랙", "2": "화이트 기본형"}, spec_main="2")
        self.assertFalse(p.get("마커이동"))

    def test_지정이_없으면_마커를_건드리지_않는다(self):
        """회귀 — 규격어 미사용 상품은 종전 동작 그대로여야 한다."""
        rows = [row(1, 10000), row(2, 12000)]
        p = R.plan(opt(rows), keep_ids={"1", "2"}, names={"1": "블랙 기본형"})
        self.assertNotIn("마커이동", p)


class PriceFloorTest(unittest.TestCase):
    """네이버 옵션가 = 기준가 ±50% (2026-08-05 이룸님 확인). 하한 ×0.5 신설."""

    def test_대표가_최저가면_하한은_구조적으로_안_걸린다(self):
        rows = [row(1, 10000), row(2, 14000)]
        p = R.plan(opt(rows), keep_ids={"1", "2"})
        self.assertEqual(p["하한"], 5000)
        self.assertEqual(p["유지"], ["1", "2"], "하한이 멀쩡한 옵션을 잘랐다")

    def test_대표가_올라가면_절반_미만_옵션이_빠진다(self):
        """지정 대표가 최저가의 2배를 넘을 때만 실제로 발동한다."""
        rows = [row(1, 10000), row(2, 25000), row(3, 30000)]
        p = R.plan(opt(rows), keep_ids={"1", "2", "3"}, spec_main="2")
        self.assertEqual(p["하한"], 12500)
        self.assertEqual(p["유지"], ["2", "3"])
        self.assertIn("±50% 범위 미만", next(
            e["사유"] for e in p["제외"] if e["id"] == "1"))

    def test_하한과_같은_값은_유지한다(self):
        rows = [row(1, 10000), row(2, 20000)]
        p = R.plan(opt(rows), keep_ids={"1", "2"}, spec_main="2")
        self.assertEqual(p["하한"], 10000)
        self.assertEqual(sorted(p["유지"]), ["1", "2"], "같은 값 포함 규칙이 안 지켜졌다")

    def test_가격이_없으면_판매불가로_뺀다(self):
        rows = [row(1, 10000), {"id": "2", "sale_price": None, "stock": 5}]
        p = R.plan(opt(rows), keep_ids={"1", "2"})
        self.assertEqual(p["유지"], ["1"])


class MaxRowsTest(unittest.TestCase):
    """판매행 상한 — 조합이 199개를 넘으면 싼 것부터 남기고 자른다(2026-08-05 이룸님)."""

    def test_상한_이하면_안_자른다(self):
        rows = [row(i, 10000) for i in range(1, 51)]
        p = R.plan(opt(rows), keep_ids={r["id"] for r in rows})
        self.assertEqual(len(p["유지"]), 50)
        self.assertNotIn("행제한", p)

    def test_상한을_넘으면_가격순으로_자른다(self):
        # 전부 같은 값이면 1.5배 상한에 안 걸린다 — 오직 행수 제한만 작동해야 한다
        rows = [row(i, 10000) for i in range(1, 251)]
        p = R.plan(opt(rows), keep_ids={r["id"] for r in rows})
        self.assertEqual(len(p["유지"]), R.MAX_SKU_ROWS)
        # 자르기는 정책이라 `경고` 에 넣지 않는다 — 넣으면 상태가 '확인요' 로 떨어져 저장이 막힌다
        self.assertIn("잘랐다", p.get("행제한", ""))
        self.assertFalse([w for w in p["경고"] if "잘랐다" in w])
        cut = [e for e in p["제외"] if "판매행" in e["사유"]]
        self.assertEqual(len(cut), 250 - R.MAX_SKU_ROWS)

    def test_대표는_잘려나가지_않는다(self):
        # 싼 것부터 남기므로 대표(최저가)는 언제나 살아남는다
        rows = [row(1, 9000)] + [row(i, 10000) for i in range(2, 251)]
        p = R.plan(opt(rows), keep_ids={r["id"] for r in rows})
        self.assertEqual(p["대표"], "1")
        self.assertIn("1", p["유지"])
        self.assertEqual(p["유지"][0], "1")


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

    def test_plan이_빠진_마커를_자동으로_붙인다(self):
        # 2026-08-06 이룸님: 붙일 자리(대표값키)는 스크립트가 안다 — 판단이 아니라 기계
        # 작업이라 보류로 사람을 한 바퀴 더 돌리지 않는다.
        o = opt([row(1, 10000), row(2, 14000)])
        p = R.plan(o, keep_ids={"1", "2"}, names={"1": "블랙", "2": "화이트"})
        self.assertEqual(p["대표값키"], "@0:1")
        self.assertEqual(p["마커이동"], {"@0:1": "블랙 기본형"})
        self.assertFalse(p["이름검사"]["마커"]["누락"])

    def test_25자를_넘으면_손대지_않고_누락으로_남긴다(self):
        # 붙이면 상한을 넘는다 → 본문을 줄이는 건 사람 몫이라 기계가 포기한다.
        # 상태는 `보류(기본형)` 이 되고 run_options 가 부분저장 + 재작업으로 보낸다.
        o = opt([row(1, 10000), row(2, 14000)])
        long_name = "가" * (R.NAME_MAX - 1)
        p = R.plan(o, keep_ids={"1", "2"}, names={"1": long_name, "2": "화이트"})
        self.assertFalse(p.get("마커이동"))
        self.assertTrue(p["이름검사"]["마커"]["누락"])

    def test_마커를_떼서_이름이_겹치면_손대지_않는다(self):
        # @0:2 에서 마커를 떼면 안 건드린 @0:3 의 현재 이름과 같아진다 — 어느 쪽을
        # 비틀지는 판단이라 기계가 포기하고 `보류(기본형)` 으로 남긴다.
        o = opt([row(1, 10000), row(2, 14000), row(3, 15000)])
        o["차원"][0]["values"][2]["name"] = "화이트"
        p = R.plan(o, keep_ids={"1", "2", "3"},
                   names={"1": "블랙", "2": "화이트 기본형"})
        self.assertFalse(p.get("마커이동"))
        self.assertTrue(p["이름검사"]["마커"]["누락"])

    def test_오부착도_자동으로_뗀다(self):
        o = opt([row(1, 10000), row(2, 14000)])
        p = R.plan(o, keep_ids={"1", "2"},
                   names={"1": "블랙", "2": "화이트 기본형"})
        self.assertEqual(p["마커이동"], {"@0:1": "블랙 기본형", "@0:2": "화이트"})
        self.assertEqual(p["이름검사"]["마커"]["오부착"], [])

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

    def test_이름을_안_바꿔도_마커는_검사한다(self):
        # 용쌤1-3 실측 1건: 워커가 이름을 하나도 안 주면 이름검사가 통째로 생략돼
        # **마커가 없는 상품이 '정리대상'으로 통과**했다(저장된 뒤에야 발견).
        # 2026-08-06 부터는 검사에서 끝나지 않고 **자동으로 붙인다**(붙일 자리를 안다).
        rows = [row(1, 10000), row(2, 12000)]
        p = R.plan(opt(rows), keep_ids={"1", "2"}, names={})
        self.assertEqual(p["마커이동"], {"@0:1": "opt1 기본형"},
                         "이름 변경이 없어도 마커는 붙여야 한다")
        self.assertFalse((p.get("이름검사") or {}).get("마커", {}).get("누락"))

    def test_이름을_안_바꿔도_이미_붙은_마커는_통과한다(self):
        rows = [row(1, 10000), row(2, 12000)]
        o = opt(rows)
        o["차원"][0]["values"][0]["name"] = "블랙 기본형"
        p = R.plan(o, keep_ids={"1", "2"}, names={})
        self.assertFalse((p["이름검사"]["마커"]).get("누락"))
        self.assertEqual(p["이름검사"]["마커"].get("오부착"), [])

    def test_값이_1개인_마지막_차원은_건너뛰고_그_앞에_붙인다(self):
        # 2026-08-05 이룸님: 값이 1개인 차원은 고객이 고를 게 없으니 선택 항목이 아니다.
        # 거기 붙이면 전 조합에 마커가 보인다(전면 오염) — 용쌤1-3 에서 49건 나왔다.
        dims = [{"이름": "제품 유형", "values": [{"vid": 31, "name": "자흡식"},
                                             {"vid": 32, "name": "일반형"}]},
                {"이름": "전력", "values": [{"vid": 1, "name": "750W"}]}]
        o = {"차원": dims, "판매행": [], "vid고유": False}
        self.assertEqual(R.main_value_key(o, "31:1"), ("@0:31", ""))

    def test_뒤쪽_1개짜리_차원이_여러개여도_건너뛴다(self):
        dims = [{"이름": "색상", "values": [{"vid": 1, "name": "골드"},
                                          {"vid": 2, "name": "실버"}]},
                {"이름": "크기", "values": [{"vid": 1, "name": "기타"}]},
                {"이름": "저장 공간", "values": [{"vid": 1, "name": "예"}]}]
        o = {"차원": dims, "판매행": [], "vid고유": False}
        self.assertEqual(R.main_value_key(o, "2:1:1"), ("@0:2", ""))

    def test_마지막_차원_값이_2개_이상이면_그대로_마지막이다(self):
        dims = [{"이름": "색상", "values": [{"vid": 1, "name": "블랙"},
                                          {"vid": 2, "name": "화이트"}]},
                {"이름": "용량", "values": [{"vid": 1, "name": "2000mAh"},
                                          {"vid": 2, "name": "4500mAh"}]}]
        o = {"차원": dims, "판매행": [], "vid고유": False}
        self.assertEqual(R.main_value_key(o, "1:1"), ("@1:1", ""))

    def test_전_차원이_1개짜리면_마지막에_붙인다(self):
        # 조합이 하나뿐이라 오염이 성립하지 않는다.
        dims = [{"이름": "종류", "values": [{"vid": 1, "name": "기본"}]},
                {"이름": "전력", "values": [{"vid": 1, "name": "750W"}]}]
        o = {"차원": dims, "판매행": [], "vid고유": False}
        self.assertEqual(R.main_value_key(o, "1:1"), ("@1:1", ""))

    def test_워커가_준_이름의_접두사도_기계적으로_뗀다(self):
        # 기본형 재작업 실측: 워커가 기존 이름에 마커만 붙여 'A. 750W 기본형' 을 냈다.
        n = R.normalize_names({"@1:1": "A. 750W 기본형", "@1:2": "B) 1200W"})
        self.assertEqual(n, {"@1:1": "750W 기본형", "@1:2": "1200W"})
        self.assertEqual(R.check_names(n)["위반"], {})

    def test_정규화가_실사이즈를_깎지_않는다(self):
        self.assertEqual(R.normalize_names({"1": "XL 롱패딩", "2": "S/M/L"}),
                         {"1": "XL 롱패딩", "2": "S/M/L"})

    def test_워커가_안_준_값의_접두사를_기계적으로_메운다(self):
        # 용쌤1-3 실측: 값이 1개뿐인 차원을 워커가 손대지 않아 'A. 1개' 가 남았고,
        # 저장 후 검사가 표시명 **전체**를 보는 탓에 상품 하나가 통째로 실패했다(32건).
        dims = [{"이름": "디스크 수", "values": [{"vid": 1, "name": "A. 1개"}]},
                {"이름": "색상", "values": [{"vid": 1, "name": "A. 자동회전 20개"},
                                          {"vid": 2, "name": "B. 입식 20개"}]}]
        o = {"차원": dims, "판매행": [], "vid고유": False}
        out = R.with_prefix_cleanup(o, {"@1:1": "심플형 10kg 기본형", "@1:2": "입식 10kg"})
        self.assertEqual(out["@0:1"], "1개", "안 준 값의 접두사를 안 뗐다")
        self.assertEqual(out["@1:1"], "심플형 10kg 기본형", "워커 이름을 덮어썼다")
        self.assertEqual(R.check_names(R.effective_names(o, out),
                                       groups=R.pos_groups(o))["위반"], {})

    def test_접두사가_없는_값은_건드리지_않는다(self):
        dims = [{"이름": "종류", "values": [{"vid": 1, "name": "블랙"},
                                          {"vid": 2, "name": "A. 화이트"}]}]
        o = {"차원": dims, "판매행": [], "vid고유": True}
        out = R.with_prefix_cleanup(o, {"1": "무광 블랙"})
        self.assertNotIn("@0:1", out, "이미 워커가 준 값을 중복으로 넣었다")
        self.assertEqual(out["@0:2"], "화이트")

    def test_이름을_아예_안_바꾸는_상품은_손대지_않는다(self):
        # 범위를 좁힌 결정: 워커가 rename 을 하나도 안 준 상품까지 쓰기를 늘리지 않는다.
        dims = [{"이름": "종류", "values": [{"vid": 1, "name": "A. 블랙"}]}]
        o = {"차원": dims, "판매행": [], "vid고유": True}
        self.assertEqual(R.with_prefix_cleanup(o, {}), {})

    def test_기존_이름끼리_겹치면_기계적으로_갈라놓는다(self):
        # 25-2 실측: 워커가 손도 안 댄 기존 이름끼리 겹쳐 저장이 통째로 거부됐다
        # ("최종 옵션 이름이 서로 겹쳐 저장할 수 없습니다. 겹치는 이름 16가지").
        dims = [{"이름": "색상", "values": [{"vid": 1, "name": "펄 화이트 일반"},
                                          {"vid": 2, "name": "펄 화이트 일반"},
                                          {"vid": 3, "name": "펄 화이트 일반"}]}]
        o = {"차원": dims, "판매행": [], "vid고유": True}
        out = R.with_dedup_cleanup(o, {})
        self.assertEqual(R.check_names(R.effective_names(o, out),
                                       groups=R.pos_groups(o))["중복"], {},
                         "중복을 못 풀었다")
        self.assertNotIn("@0:1", out, "첫 번째는 그대로 둬야 한다")
        self.assertEqual(out["@0:2"], "펄 화이트 일반 2")
        self.assertEqual(out["@0:3"], "펄 화이트 일반 3")

    def test_기본형_마커가_붙은_이름은_번호를_면한다(self):
        # 마커는 상품명과 짝을 이루는 유일한 표식이라 이름 끝에 남아야 한다.
        dims = [{"이름": "색상", "values": [{"vid": 1, "name": "회색 테이블"},
                                          {"vid": 2, "name": "회색 테이블 기본형"}]}]
        o = {"차원": dims, "판매행": [], "vid고유": True}
        out = R.with_dedup_cleanup(o, {"1": "회색 테이블 기본형"})
        self.assertEqual(out["1"], "회색 테이블 기본형", "마커 붙은 워커 이름에 번호를 붙였다")
        self.assertTrue(out["@0:2"].endswith(" 2"))

    def test_중복이_없으면_아무것도_안_바꾼다(self):
        dims = [{"이름": "색상", "values": [{"vid": 1, "name": "블랙"},
                                          {"vid": 2, "name": "화이트"}]}]
        o = {"차원": dims, "판매행": [], "vid고유": True}
        self.assertEqual(R.with_dedup_cleanup(o, {"1": "무광 블랙"}), {"1": "무광 블랙"})

    def test_차원이_다르면_같은_이름을_그대로_둔다(self):
        out = R.with_dedup_cleanup(_dual(), {})
        self.assertEqual(out, {}, "차원이 다른 동명을 중복으로 잡았다")

    def test_번호를_붙여도_이름_상한을_넘지_않는다(self):
        long = "가" * R.NAME_MAX
        dims = [{"이름": "색상", "values": [{"vid": 1, "name": long},
                                          {"vid": 2, "name": long}]}]
        o = {"차원": dims, "판매행": [], "vid고유": True}
        out = R.with_dedup_cleanup(o, {})
        self.assertLessEqual(len(out["@0:2"]), R.NAME_MAX)
        self.assertTrue(out["@0:2"].endswith(" 2"))

    def test_이름변경표는_안_바뀐_것도_남긴다(self):
        o = opt([row(1, 10000), row(2, 20000)])
        chg = {c["키"]: c for c in R.name_changes(o, {"1": "스탠드형", "2": "opt2"})}
        self.assertTrue(chg["1"]["변경"])
        self.assertEqual(chg["1"]["기존"], "opt1")
        self.assertFalse(chg["2"]["변경"], "같은 이름인데 변경으로 셌다")
        self.assertEqual(chg["1"]["차원"], "종류")


class AxisTest(unittest.TestCase):
    """규칙 18 — 옵션 축(선택 항목) 이름 정합. 판정만 하고 저장하지 않는다."""

    def dim(self, name, vals, ori=""):
        return {"이름": name, "원문이름": ori,
                "values": [{"vid": i + 1, "name": v} for i, v in enumerate(vals)]}

    def test_멀쩡한_축_이름은_신호가_없다(self):
        self.assertEqual(R.axis_problems("색상"), [])
        self.assertEqual(R.axis_problems("제품 종류"), [])

    def test_번역_잔재와_무의미한_축을_잡는다(self):
        self.assertIn("번역 잔재", R.axis_problems("색상별로 정렬하십시오"))
        self.assertIn("번역 잔재", R.axis_problems("용량별 정렬"))
        self.assertIn("의미 없는 축 이름", R.axis_problems("제품명"))
        self.assertIn("의미 없는 축 이름", R.axis_problems("분류"))
        self.assertEqual(R.axis_problems(""), ["빈 축 이름"])
        self.assertIn("중국어 잔존", R.axis_problems("颜色分类"))
        self.assertTrue(any("상한" in p for p in R.axis_problems("가" * 21)))

    def test_종류라는_축은_잡지_않는다(self):
        # '종류'·'유형'은 실제로 쓸 만한 축 이름이다 — 잡으면 헛신호가 대량으로 난다.
        self.assertEqual(R.axis_problems("종류"), [])
        self.assertEqual(R.axis_problems("제품 유형"), [])

    def test_색상축인데_값에_색이_없으면_잡는다(self):
        # 颜色分类 함정 — 용쌤1-2 881축 중 90건이 이 모양이었다.
        self.assertTrue(R.axis_color_mismatch(
            self.dim("색상", ["고속도로 모델", "철도 모델", "시티 스타일"])))
        self.assertTrue(R.axis_color_mismatch(self.dim("색상", ["플란넬", "면 리넨 아트"])))

    def test_진짜_색상축은_잡지_않는다(self):
        self.assertFalse(R.axis_color_mismatch(self.dim("색상", ["블랙", "화이트"])))
        self.assertFalse(R.axis_color_mismatch(self.dim("색상", ["A. 아이보리", "네이비"])))
        self.assertFalse(R.axis_color_mismatch(self.dim("크기", ["대형", "소형"])),
                         "색상 축이 아닌데 검사했다")
        self.assertFalse(R.axis_color_mismatch(self.dim("색상", [])),
                         "값이 없으면 판단 근거가 없다")

    def test_감사는_문제있는_축만_돌려준다(self):
        o = {"차원": [self.dim("색상", ["블랙", "화이트"], "颜色"),
                    self.dim("색상별로 정렬", ["1.2m", "1.5m"], "颜色分类")],
             "판매행": [], "vid고유": True}
        got = R.axis_audit(o)
        self.assertEqual([a["차원"] for a in got], [1], "멀쩡한 축까지 원장에 올렸다")
        self.assertIn("번역 잔재", got[0]["신호"])
        self.assertEqual(got[0]["원문"], "颜色分类")

    def test_워커_제안을_싣고_값예시는_4개까지(self):
        o = {"차원": [self.dim("색상", ["가", "나", "다", "라", "마"], "颜色分类")],
             "판매행": [], "vid고유": True}
        got = R.axis_audit(o, [{"차원": 0, "제안": "모델", "사유": "값이 전부 모델 구분"}])
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["제안"], "모델")
        self.assertEqual(got[0]["사유"], "값이 전부 모델 구분")
        self.assertEqual(len(got[0]["값예시"]), 4)

    def test_현재와_같은_제안은_제안이_아니다(self):
        o = {"차원": [self.dim("색상", ["블랙", "화이트"], "颜色")],
             "판매행": [], "vid고유": True}
        self.assertEqual(R.axis_audit(o, [{"차원": 0, "제안": "색상"}]), [],
                         "같은 이름을 제안으로 받아 원장에 올렸다")

    def test_제안_축_이름이_규칙_위반이면_신호로_남는다(self):
        o = {"차원": [self.dim("색상", ["가", "나"], "颜色分类")],
             "판매행": [], "vid고유": True}
        got = R.axis_audit(o, [{"차원": 0, "제안": "颜色分类"}])
        self.assertTrue(any("제안 축 이름" in s for s in got[0]["신호"]))

    def test_망가진_제안은_무시하고_감사는_계속한다(self):
        o = {"차원": [self.dim("색상별로 정렬", ["가"], "颜色分类")],
             "판매행": [], "vid고유": True}
        got = R.axis_audit(o, [{"제안": "모델"}, "쓰레기", {"차원": "x"}])
        self.assertEqual(len(got), 1)
        self.assertNotEqual(got[0]["제안"], "모델", "차원 없는 제안을 붙였다")
        # 제안은 못 받았지만 이름이 객관적으로 깨졌으니 코드가 짓는다(2026-08-17).
        self.assertEqual(got[0]["제안"], "색상")
        self.assertTrue(got[0]["자동"])

    def test_축_이름은_값_저장에_섞이지_않는다(self):
        # rename_targets 는 값만 만든다 — 축이 섞여 나가면 엉뚱한 값이 바뀐다.
        # 축은 `renameGroups`(axis_saveable)라는 **별도 경로**로만 나간다.
        o = opt([row(1, 10000)])
        items, missing = R.rename_targets(o, {"1": "블랙 기본형"})
        self.assertEqual(missing, [])
        for it in items:
            self.assertNotIn("groupName", it)
            self.assertNotIn("propName", it)


class AxisSaveTest(unittest.TestCase):
    """규칙 18 저장부 — `renameGroups` 로 나갈 축만 골라낸다 (2026-08-17).

    보내기 전에 걸러야 하는 이유: 축 이름이 거부되면 그 호출이 통째로 실패한다.
    ②(판매·대표·순서)와 분리해서 보내지만, 헛호출은 그것대로 낭비고 원인이 안 보인다.
    """

    def dim(self, name, vals=("가", "나"), ori=""):
        return {"이름": name, "원문이름": ori,
                "values": [{"vid": i + 1, "name": v} for i, v in enumerate(vals)]}

    def opt2(self, *names):
        return {"차원": [self.dim(n) for n in names], "판매행": [], "vid고유": True}

    def audit(self, o, proposals):
        return R.axis_audit(o, proposals)

    def test_멀쩡한_제안은_그대로_나간다(self):
        o = self.opt2("색상")
        items, rej = R.axis_saveable(o, self.audit(o, [{"차원": 0, "제안": "모델"}]))
        self.assertEqual(items, [{"groupIndex": 0, "name": "모델"}])
        self.assertEqual(rej, [])

    def test_제안이_없어도_깨진_이름은_코드가_고쳐_보낸다(self):
        # 2026-08-17 이룸님: "대체 이름 못 지어도 진행해라." 전에는 `대기` 로 쌓아
        # 사람에게 넘겼는데 그게 사람 큐를 만드는 유일한 원인이었다(1-2 실측 83축).
        # 번역 잔재는 **꼬리만 떼면** 원뜻이 남는다 — 추측이 아니다.
        o = self.opt2("색상별로 정렬하십시오")
        a = self.audit(o, None)
        self.assertEqual(len(a), 1, "감사가 신호를 냈어야 한다")
        items, rej = R.axis_saveable(o, a)
        self.assertEqual(items, [{"groupIndex": 0, "name": "색상"}])
        self.assertEqual(rej, [])

    def test_꼬리를_못_떼면_종류로_간다(self):
        # 중국어 잔존·무의미어는 벗겨낼 꼬리가 없다. `종류` 는 값이 뭐든 참이라 틀리지 않는다.
        for cur in ("颜色分类", "제품명"):
            o = self.opt2(cur)
            items, _ = R.axis_saveable(o, self.audit(o, None))
            self.assertEqual(items, [{"groupIndex": 0, "name": R.AXIS_LAST_RESORT}])

    def test_휴리스틱_신호만_있으면_이름을_안_바꾼다(self):
        # '색상 축인데 값에 색이 없다'는 헛신호가 난다(사전에 없는 색). 아무도 제안을
        # 안 냈으면 지금 이름이 맞을 수 있다 — 코드가 `종류` 로 덮으면 개악이다.
        o = self.opt2("색상")
        o["차원"][0]["values"] = [{"vid": 1, "name": "카멜"}, {"vid": 2, "name": "라벤더"}]
        a = self.audit(o, None)
        self.assertEqual(len(a), 1, "휴리스틱 신호는 나야 한다(기록용)")
        self.assertEqual(a[0]["제안"], "", "휴리스틱만 보고 이름을 바꿨다")
        self.assertEqual(R.axis_saveable(o, a), ([], []))

    def test_워커가_유지라고_하면_확인으로_닫는다(self):
        # "지금 이름이 맞다"는 판정이다. 제안이 아니라 확인이라 다시 잡히면 안 된다.
        o = self.opt2("색상별로 정렬하십시오")
        a = self.audit(o, [{"차원": 0, "제안": "유지"}])
        self.assertTrue(a[0]["확인"])
        self.assertEqual(a[0]["제안"], "", "확인인데 이름을 바꾸려 했다")

    def test_금지문자가_든_제안은_거부한다(self):
        # MCP 축 이름 제약: , [ ] / { } ( ) * ? \ ^ $ |
        # **`/` 는 여기 없다** — 구분자라 뜻이 확실해서 `·` 로 고쳐 보낸다
        # (아래 test_구분자_슬래시는_가운뎃점으로_고쳐_보낸다).
        for bad in ("구성(세트)", "모델*", "용량[L]", "종류|타입", "색상,사이즈"):
            o = self.opt2("색상")
            items, rej = R.axis_saveable(o, self.audit(o, [{"차원": 0, "제안": bad}]))
            self.assertEqual(items, [], f"금지문자 '{bad}' 가 그대로 나갔다")
            self.assertEqual(len(rej), 1)
            self.assertIn("금지문자", rej[0]["사유"])

    def test_결함있는_제안은_거부한다(self):
        for bad, why in (("颜色分类", "중국어"), ("색상별로 정렬하십시오", "번역"),
                         ("분류", "의미"), ("가" * 21, "상한")):
            o = self.opt2("색상")
            items, rej = R.axis_saveable(o, self.audit(o, [{"차원": 0, "제안": bad}]))
            self.assertEqual(items, [], f"'{bad}' 가 그대로 나갔다 ({why})")
            self.assertEqual(len(rej), 1)

    def test_다른_축과_이름이_겹치면_거부한다(self):
        # 같은 상품 안에서 축끼리 같은 이름을 쓸 수 없다(MCP 거부).
        o = self.opt2("색상", "크기")
        items, rej = R.axis_saveable(o, self.audit(o, [{"차원": 0, "제안": "크기"}]))
        self.assertEqual(items, [], "안 바꾸는 축과 겹치는 이름을 보냈다")
        self.assertIn("겹친다", rej[0]["사유"])

    def test_겹침은_공백과_대소문자를_무시하고_본다(self):
        # MCP 는 앞뒤 공백 제거·연속 공백 1칸·대소문자 무시로 비교한다.
        o = self.opt2("색상", "Size")
        items, rej = R.axis_saveable(o, self.audit(o, [{"차원": 0, "제안": " size "}]))
        self.assertEqual(items, [], "정규화하면 겹치는 이름을 보냈다")
        self.assertIn("겹친다", rej[0]["사유"])

    def test_두_축이_같은_이름을_제안하면_둘_다_거부한다(self):
        o = self.opt2("색상", "색상 분류")
        items, rej = R.axis_saveable(o, self.audit(
            o, [{"차원": 0, "제안": "종류"}, {"차원": 1, "제안": "종류"}]))
        self.assertEqual(items, [], "서로 겹치는 제안 둘을 다 보냈다")
        self.assertEqual(len(rej), 2)

    def test_바꾸는_축끼리_자리를_맞바꾸는_건_통과한다(self):
        # 축0='크기'→'색상', 축1='색상'→'크기'. 최종 상태는 안 겹친다.
        o = self.opt2("크기", "색상")
        items, rej = R.axis_saveable(o, self.audit(
            o, [{"차원": 0, "제안": "색상"}, {"차원": 1, "제안": "크기"}]))
        self.assertEqual(rej, [], "최종 상태가 멀쩡한데 거부했다")
        self.assertEqual(sorted(i["groupIndex"] for i in items), [0, 1])

    def test_차원_범위_밖_제안은_거부한다(self):
        o = self.opt2("색상")
        a = [{"차원": 5, "현재": "", "원문": "", "값예시": [], "신호": [],
              "제안": "모델", "사유": ""}]
        items, rej = R.axis_saveable(o, a)
        self.assertEqual(items, [])
        self.assertIn("차원", rej[0]["사유"])

    def test_여러_축을_한_번에_보낸다(self):
        o = self.opt2("색상", "색상별로 정렬")
        items, rej = R.axis_saveable(o, self.audit(
            o, [{"차원": 0, "제안": "모델"}, {"차원": 1, "제안": "길이"}]))
        self.assertEqual(rej, [])
        self.assertEqual(items, [{"groupIndex": 0, "name": "모델"},
                                 {"groupIndex": 1, "name": "길이"}])

    def test_저장된_축_이름을_재조회로_검증한다(self):
        after = self.opt2("모델", "길이")
        items = [{"groupIndex": 0, "name": "모델"}, {"groupIndex": 1, "name": "길이"}]
        self.assertEqual(R.axis_verify(after, items), [])

    def test_구분자_슬래시는_가운뎃점으로_고쳐_보낸다(self):
        # 워커가 "두 속성이 섞였다"를 `/` 로 적는데 그건 축 이름 금지문자다.
        # 뜻은 그대로고 문자만 문제라 거부하지 않고 고친다 (2026-08-17 이룸님).
        for bad, want in (("색상/마감", "색상·마감"), ("모델 / 용량", "모델·용량"),
                          ("브랜드/용량/구성", "브랜드·용량·구성")):
            o = self.opt2("색상")
            items, rej = R.axis_saveable(o, self.audit(o, [{"차원": 0, "제안": bad}]))
            self.assertEqual(rej, [], f"'{bad}' 를 고치지 않고 거부했다")
            self.assertEqual(items, [{"groupIndex": 0, "name": want}])

    def test_뜻을_모르는_금지문자는_고치지_않고_거부한다(self):
        # `/` 만 뜻이 확실하다. 괄호를 무엇으로 바꿔야 할지는 기계가 모른다 — 사람 몫.
        o = self.opt2("색상")
        items, rej = R.axis_saveable(o, self.audit(o, [{"차원": 0, "제안": "구성(세트)"}]))
        self.assertEqual(items, [])
        self.assertIn("금지문자", rej[0]["사유"])

    def test_고친_제안이_현재_이름과_같아지면_제안이_아니다(self):
        # `색상/` → `색상`. 바꿀 게 없는데 호출하면 헛일이다.
        o = self.opt2("색상")
        self.assertEqual([a["제안"] for a in self.audit(o, [{"차원": 0, "제안": "색상/"}])],
                         [""])

    def test_반영_안_된_축은_검증이_잡는다(self):
        after = self.opt2("색상", "길이")      # 축0 이 안 바뀌었다
        items = [{"groupIndex": 0, "name": "모델"}, {"groupIndex": 1, "name": "길이"}]
        fails = R.axis_verify(after, items)
        self.assertEqual(len(fails), 1)
        self.assertEqual(fails[0]["차원"], 0)
        self.assertIn("모델", fails[0]["사유"])


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    unittest.main(verbosity=2)
