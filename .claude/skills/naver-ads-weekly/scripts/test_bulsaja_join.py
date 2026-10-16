#!/usr/bin/env python3
"""⑦c/⑦d 불사자 조인 회귀 테스트 — 가짜 lookup 으로만 돈다(네트워크·MCP·시트 0).

조인 경로: 채널상품번호 + 마켓번호 → 커머스 판매자상품코드 → find_by_code 1건 → 스스번호 일치.
상품명 매칭은 없다(D-03).
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bulsaja_join as B  # noqa: E402


def row(ad_id="a1", group="판매상품_13-2_테스트", mall="13265084103", **kw):
    d = {"adId": ad_id, "adGroup": group, "mallProductId": mall, "title": "아무 이름", "clk": 30}
    d.update(kw)
    return d


class FakeLookup:
    """dict 로 응답을 주입한다. calls 에 호출 기록."""

    def __init__(self, codes=None, finds=None, wds=None, groups=None, matrix=None,
                 no_key=(), commerce_fail=(), find_fail=(), wd_fail=(), nick="부킹"):
        self.codes = codes or {}
        self.finds = finds or {}
        self.wds = wds or {}
        self.groups = groups or {}
        self.matrix = matrix or {}
        self.no_key, self.commerce_fail = set(no_key), set(commerce_fail)
        self.find_fail, self.wd_fail = set(find_fail), set(wd_fail)
        self.nick = nick
        self.calls = []

    def profile_nick(self):
        self.calls.append(("profile",))
        return self.nick

    def seller_code(self, market, channel_no):
        self.calls.append(("code", market, channel_no))
        if market in self.no_key:
            raise B.KeyMissing(market)
        if channel_no in self.commerce_fail:
            raise B.CommerceFailed("HTTP 500")
        return self.codes.get((market, channel_no))

    def find(self, code):
        self.calls.append(("find", code))
        if code in self.find_fail:
            raise RuntimeError("MCP")
        return self.finds.get(code, [])

    def workdata(self, pid):
        self.calls.append(("wd", pid))
        if pid in self.wd_fail:
            raise RuntimeError("MCP")
        return self.wds[pid]

    def group_name(self, gid):
        return self.groups.get(gid)

    def matrix_option(self, group_name, market, pid):
        key = (group_name, pid)
        if key not in self.matrix:
            return None, False
        return self.matrix[key], True


def wd(ss="13265084103", ai=None, tr=None, code="doLX", gid="g1"):
    dc = {}
    if ai is not None:
        dc["aiImageGenerated"] = ai
    if tr is not None:
        dc["imageTranslated"] = tr
    return {"uploadDetailContents": dc, "uploadBulsajaCode": code,
            "uploadedSuccessUrl": {"smartstore": f"https://smartstore.naver.com/x/products/{ss}"},
            "uploadSelectedMarketGroupId": gid}


def happy(**kw):
    base = dict(codes={("13-2", "13265084103"): "doLX"},
                finds={"doLX": [{"productId": "P1", "판매자상품코드": "doLX"}]},
                wds={"P1": wd()}, groups={"g1": "13번_용쌤13-2"},
                matrix={("13번_용쌤13-2", "P1"): "완료"})
    base.update(kw)
    return FakeLookup(**base)


class TestPure(unittest.TestCase):
    def test_seller_code_of_실측_모양(self):
        d = {"originProduct": {"detailAttribute": {"sellerCodeInfo": {"sellerManagementCode": "doLX"}}}}
        self.assertEqual(B.seller_code_of(d), "doLX")

    def test_seller_code_of_없으면_None(self):
        self.assertIsNone(B.seller_code_of({}))
        self.assertIsNone(B.seller_code_of(None))
        self.assertIsNone(B.seller_code_of({"originProduct": {"detailAttribute": {
            "sellerCodeInfo": {"sellerManagementCode": "  "}}}}))

    def test_pick_items_정확일치만(self):
        items = [{"productId": "1", "판매자상품코드": "A"}, {"productId": "2", "판매자상품코드": "AB"}]
        self.assertEqual([i["productId"] for i in B.pick_items(items, "A")], ["1"])

    def test_pick_items_불사자코드로도_맞춘다(self):
        items = [{"productId": "1", "불사자코드": "A"}]
        self.assertEqual(len(B.pick_items(items, "A")), 1)

    def test_option_status(self):
        self.assertEqual(B.option_status("완료", True), ("정리완료", False))
        self.assertEqual(B.option_status("해당없음", True), ("정리완료", False))
        self.assertEqual(B.option_status("", True), ("미정리", True))
        self.assertEqual(B.option_status("재작업(옵션: 대표색)", True), ("미정리", True))
        self.assertEqual(B.option_status("진행중", True), ("미정리", True))
        self.assertEqual(B.option_status("완료", False), ("판정 불가", None))


class TestEnrichRows(unittest.TestCase):
    def test_히트_경로_보강필드(self):
        out = B.enrich_rows([row()], happy())[0]
        self.assertEqual(out["불사자매칭"], "히트")
        self.assertEqual(out["마켓번호"], "13-2")
        self.assertEqual(out["productId"], "P1")
        self.assertEqual(out["판매자상품코드"], "doLX")
        self.assertEqual(out["상세상태"], "중국어원본")
        self.assertIs(out["상세미가공"], True)
        self.assertEqual((out["옵션상태"], out["옵션미정리"]), ("정리완료", False))
        self.assertEqual(out["번호검증"], "히트")

    def test_AI가공완료는_상세미가공_False(self):
        lk = happy(wds={"P1": wd(ai="1", tr="1")})
        out = B.enrich_rows([row()], lk)[0]
        self.assertEqual(out["상세상태"], "AI가공완료")
        self.assertIs(out["상세미가공"], False)

    def test_단순번역만(self):
        out = B.enrich_rows([row()], happy(wds={"P1": wd(tr="1")}))[0]
        self.assertEqual(out["상세상태"], "단순번역만")

    def test_번호추출실패(self):
        out = B.enrich_rows([row(group="광고그룹 이름만")], happy())[0]
        self.assertEqual(out["불사자매칭"], "미매칭: 번호추출실패")

    def test_스토어상품ID_없어도_번호추출실패(self):
        out = B.enrich_rows([row(mall=None)], happy())[0]
        self.assertEqual(out["불사자매칭"], "미매칭: 번호추출실패")

    def test_키없음(self):
        out = B.enrich_rows([row()], happy(no_key={"13-2"}))[0]
        self.assertEqual(out["불사자매칭"], "미매칭: 키없음")
        self.assertIsNone(out["상세미가공"])
        self.assertEqual(out["옵션상태"], "판정 불가")

    def test_커머스조회실패(self):
        out = B.enrich_rows([row()], happy(commerce_fail={"13265084103"}))[0]
        self.assertEqual(out["불사자매칭"], "미매칭: 커머스조회실패")

    def test_판매자코드없음(self):
        out = B.enrich_rows([row()], happy(codes={}))[0]
        self.assertEqual(out["불사자매칭"], "미매칭: 판매자코드없음")

    def test_불사자미매칭(self):
        out = B.enrich_rows([row()], happy(finds={}))[0]
        self.assertEqual(out["불사자매칭"], "미매칭: 불사자미매칭")
        self.assertEqual(out["판매자상품코드"], "doLX")   # 커머스에서 얻은 코드는 남긴다

    def test_다건(self):
        lk = happy(finds={"doLX": [{"productId": "P1", "판매자상품코드": "doLX"},
                                   {"productId": "P2", "판매자상품코드": "doLX"}]})
        out = B.enrich_rows([row()], lk)[0]
        self.assertEqual(out["불사자매칭"], "미매칭: 다건")

    def test_번호불일치(self):
        out = B.enrich_rows([row()], happy(wds={"P1": wd(ss="99999999")}))[0]
        self.assertEqual(out["불사자매칭"], "미매칭: 번호불일치")
        self.assertEqual(out["번호검증"], "불일치")

    def test_스스번호_없으면_번호불일치_미조회증거(self):
        w = wd()
        w["uploadedSuccessUrl"] = {}
        out = B.enrich_rows([row()], happy(wds={"P1": w}))[0]
        self.assertEqual(out["불사자매칭"], "미매칭: 번호불일치")
        self.assertEqual(out["번호검증"], "미조회")

    def test_find_예외는_조회실패(self):
        out = B.enrich_rows([row()], happy(find_fail={"doLX"}))[0]
        self.assertEqual(out["불사자매칭"], "미매칭: 조회실패")

    def test_workdata_예외는_조회실패_다음행은_계속(self):
        lk = happy(wd_fail={"P1"})
        lk.codes[("13-2", "222")] = "C2"
        lk.finds["C2"] = [{"productId": "P2", "판매자상품코드": "C2"}]
        lk.wds["P2"] = wd(ss="222", code="C2")
        outs = B.enrich_rows([row(), row(ad_id="a2", mall="222")], lk)
        self.assertEqual(outs[0]["불사자매칭"], "미매칭: 조회실패")
        self.assertEqual(outs[1]["불사자매칭"], "히트")

    def test_옵션_현황판_없으면_판정불가(self):
        out = B.enrich_rows([row()], happy(matrix={}))[0]
        self.assertEqual(out["불사자매칭"], "히트")
        self.assertEqual((out["옵션상태"], out["옵션미정리"]), ("판정 불가", None))

    def test_옵션_미정리(self):
        out = B.enrich_rows([row()], happy(matrix={("13번_용쌤13-2", "P1"): ""}))[0]
        self.assertEqual((out["옵션상태"], out["옵션미정리"]), ("미정리", True))

    def test_같은_상품은_커머스_find_workdata_한번씩(self):
        lk = happy()
        B.enrich_rows([row(ad_id="a1"), row(ad_id="a2")], lk)
        kinds = [c[0] for c in lk.calls]
        self.assertEqual((kinds.count("code"), kinds.count("find"), kinds.count("wd")), (1, 1, 1))

    def test_원본을_바꾸지_않는다(self):
        r = row()
        B.enrich_rows([r], happy())
        self.assertNotIn("불사자매칭", r)


class TestCmdEnrich(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.rd = Path(self.tmp.name)
        self.result = {"generated": "t", "accounts": {"acc": {"summary": {}, "rules": {
            "①노출0": [row(ad_id="z")],
            "⑦c상세꾸미기후보": [row(ctr=5.0, imp=80)],
            "⑦d정비점검후보": [row(clk=40)],
        }}}}
        (self.rd / "result.json").write_text(json.dumps(self.result, ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _read(self):
        return json.loads((self.rd / "result.json").read_text(encoding="utf-8"))

    def test_정상_7c_7d만_보강_중복은_1회(self):
        lk = happy()
        rc = B.cmd_enrich(self.rd, lookup=lk, log=lambda m: None)
        self.assertEqual(rc, 0)
        r = self._read()
        rules = r["accounts"]["acc"]["rules"]
        self.assertEqual(rules["⑦c상세꾸미기후보"][0]["불사자매칭"], "히트")
        self.assertEqual(rules["⑦d정비점검후보"][0]["판매자상품코드"], "doLX")
        # 규칙별 지표는 보존 — ⑦c 행의 ctr 이 ⑦d 행 값으로 덮이지 않는다
        self.assertEqual(rules["⑦c상세꾸미기후보"][0]["ctr"], 5.0)
        self.assertNotIn("불사자매칭", rules["①노출0"][0])
        self.assertEqual(r["enrich"]["status"], "ok")
        self.assertEqual((r["enrich"]["rows"], r["enrich"]["hit"]), (1, 1))
        self.assertEqual([c[0] for c in lk.calls].count("code"), 1)

    def test_계정불일치면_조회0_종료코드3_원본유지(self):
        lk = happy(nick="용팀장")
        rc = B.cmd_enrich(self.rd, lookup=lk, log=lambda m: None)
        self.assertEqual(rc, 3)
        self.assertEqual(self._read(), self.result)
        self.assertEqual([c[0] for c in lk.calls], ["profile"])

    def test_result_없으면_1(self):
        (self.rd / "result.json").unlink()
        self.assertEqual(B.cmd_enrich(self.rd, lookup=happy(), log=lambda m: None), 1)


class TestNoNameMatching(unittest.TestCase):
    def test_번호정규식_상품명매칭_복제_없음(self):
        src = Path(B.__file__).read_text(encoding="utf-8")
        code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
        self.assertNotIn("d{1,2})-(", code)
        self.assertNotIn("normalize_name", code)
        self.assertIn("from webapp import join, state", code)


if __name__ == "__main__":
    unittest.main(verbosity=2)
