#!/usr/bin/env python3
"""attr-tag 단위테스트 — 가짜 커머스API·업무판 주입. 실제 네트워크·gws 0."""
import contextlib
import copy
import io
import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import attr_tag as T  # noqa: E402
import attr_tag_rules as A  # noqa: E402

SECRET = "$2a$04$FAKESECRETfakesecret12"
TOKEN = "FAKE-ACCESS-TOKEN-abcdef123456"

ATTRS = [
    {"attributeSeq": 1, "attributeName": "품목", "attributeClassificationType": "SINGLE_SELECT",
     "attributeClassificationCodeName": "선택형", "attributeType": "PRIMARY", "attributeTypeCodeName": "주요",
     "attributeValueMaxMatchingCount": 0},
    {"attributeSeq": 2, "attributeName": "용도", "attributeClassificationType": "MULTI_SELECT",
     "attributeClassificationCodeName": "복수선택형", "attributeType": "PRIMARY", "attributeTypeCodeName": "주요",
     "attributeValueMaxMatchingCount": 2},
    {"attributeSeq": 3, "attributeName": "무게", "attributeClassificationType": "RANGE",
     "attributeClassificationCodeName": "범위형", "attributeType": "PRIMARY", "attributeTypeCodeName": "주요",
     "attributeValueMaxMatchingCount": 0},
]
VALUES = [
    {"attributeSeq": 1, "attributeValueSeq": 11, "minAttributeValue": "워머", "exposureOrder": 1},
    {"attributeSeq": 1, "attributeValueSeq": 12, "minAttributeValue": "전기그릴", "exposureOrder": 2},
    {"attributeSeq": 2, "attributeValueSeq": 21, "minAttributeValue": "업소용", "exposureOrder": 1},
    {"attributeSeq": 2, "attributeValueSeq": 22, "minAttributeValue": "가정용", "exposureOrder": 2},
    {"attributeSeq": 2, "attributeValueSeq": 23, "minAttributeValue": "캠핑용", "exposureOrder": 3},
    {"attributeSeq": 3, "attributeValueSeq": 31, "minAttributeValue": "1", "minAttributeValueUnitCode": "KG",
     "exposureOrder": 1},
]
DICT = {"호텔용품": 141955, "식당용품": 145201, "뷔페": 9, "보온접시": 2653072, "호텔": 535}
RESTRICTED = {"뷔페"}


def make_product():
    return {
        "originProduct": {
            "statusType": "SALE", "leafCategoryId": "50001726", "name": "호텔 워머",
            "detailContent": "<div><p>스테인리스 &amp; 보온</p><img src='https://img/1.jpg'><script>x()</script></div>",
            "images": {"representativeImage": {"url": "https://rep.jpg"}, "optionalImages": [{"url": "https://o1.jpg"}]},
            "salePrice": 83300, "stockQuantity": 10600,
            "detailAttribute": {
                "seoInfo": {"pageTitle": "t", "sellerTags": [{"text": "평문태그"}]},
                "productAttributes": [{"attributeSeq": 2, "attributeValueSeq": 22},
                                      {"attributeSeq": 3, "attributeValueSeq": 31, "minAttributeValue": "1"}],
                "optionInfo": {"optionCombinations": [{"id": 1, "price": 0, "optionName1": "A. 9L"},
                                                      {"id": 2, "price": 2900, "optionName1": "B. 9L"}]},
            },
        },
        "smartstoreChannelProduct": {"channelProductDisplayStatusType": "ON"},
    }


class FakeApi:
    """GET/PUT 를 메모리로. mutate_on_put 으로 '저장이 다른 필드를 바꿔버린' 상황을 흉내낸다."""

    def __init__(self, fail_put=None, mutate_on_put=False, drop_tags_on_put=False):
        self.products = {("13-2", "100"): make_product(), ("13-2", "200"): make_product()}
        self.puts = []
        self.fail_put = fail_put or set()
        self.mutate_on_put = mutate_on_put
        self.drop_tags_on_put = drop_tags_on_put
        self.secrets = None

    def load(self, markets):
        return "sheet"

    def get_product(self, market, no):
        if (market, no) not in self.products:
            raise RuntimeError(f"HTTP 404 not found token={TOKEN}")
        return copy.deepcopy(self.products[(market, no)])

    def put_product(self, market, no, body):
        if no in self.fail_put:
            raise RuntimeError(f"HTTP 400 bad secret={SECRET}")
        self.puts.append((market, no))
        b = copy.deepcopy(body)
        if self.mutate_on_put:
            b["originProduct"]["salePrice"] += 100
        if self.drop_tags_on_put:
            b["originProduct"]["detailAttribute"]["seoInfo"]["sellerTags"] = []
        self.products[(market, no)] = b
        return {}

    def category(self, market, cat):
        return {"wholeCategoryName": "디지털/가전>주방가전>기타주방가전"}

    def attributes(self, market, cat):
        return ATTRS

    def attribute_values(self, market, cat):
        return VALUES

    def recommend_tags(self, market, kw):
        # 접두 자동완성 흉내 — kw 로 시작하는 사전 항목 전부
        return [{"code": c, "text": t} for t, c in DICT.items() if t.startswith(kw)] + \
               [{"code": 777, "text": kw + "세트"}]

    def restricted_tags(self, market, tags):
        return {t: t in RESTRICTED for t in tags}


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _table():
    return A.build_attr_table(ATTRS, VALUES)


def _rec(t):
    return FakeApi().recommend_tags("13-2", t)


def _restr(ts):
    return FakeApi().restricted_tags("13-2", ts)


# ---------------------------------------------------------------------------
# 순수 규칙
# ---------------------------------------------------------------------------
class TagRulesTest(unittest.TestCase):
    def test_정확일치만_채택(self):
        tags, dropped = A.resolve_tags(["호텔", "보온"], _rec, _restr)
        # '호텔' 은 '호텔용품'·'호텔세트' 도 접두로 걸리지만 정확일치 535 만
        self.assertEqual(tags, [{"code": 535, "text": "호텔"}])
        self.assertIn({"text": "보온", "reason": "not_in_dictionary"}, dropped)

    def test_제한태그_제외(self):
        tags, dropped = A.resolve_tags(["뷔페", "호텔용품"], _rec, _restr)
        self.assertEqual([t["text"] for t in tags], ["호텔용품"])
        self.assertIn({"text": "뷔페", "reason": "restricted"}, dropped)

    def test_10개_상한_중복(self):
        rec = lambda t: [{"code": hash(t) % 10000, "text": t}]  # noqa: E731
        texts = [f"태그{i}" for i in range(13)] + ["태그0"]
        tags, dropped = A.resolve_tags(texts, rec, lambda ts: {t: False for t in ts})
        self.assertEqual(len(tags), 10)
        self.assertEqual(sum(1 for d in dropped if d["reason"] == "over_limit"), 3)
        self.assertIn({"text": "태그0", "reason": "duplicate"}, dropped)

    def test_제한조회_실패면_아무것도_안넣음(self):
        def boom(ts):
            raise RuntimeError("x")
        tags, dropped = A.resolve_tags(["호텔용품"], _rec, boom)
        self.assertEqual(tags, [])
        self.assertTrue(dropped[0]["reason"].startswith("restricted_check_error"))


class AttrRulesTest(unittest.TestCase):
    def test_선택지_매핑(self):
        out, dropped = A.resolve_attributes(
            [{"name": "품목", "values": ["워머"]}, {"name": "용도", "values": ["업소용", "캠핑용"]}], _table())
        self.assertEqual(out, [{"attributeSeq": 1, "attributeValueSeq": 11},
                               {"attributeSeq": 2, "attributeValueSeq": 21},
                               {"attributeSeq": 2, "attributeValueSeq": 23}])
        self.assertEqual(dropped, [])

    def test_선택형은_1개_복수는_max(self):
        out, dropped = A.resolve_attributes(
            [{"name": "품목", "values": ["워머", "전기그릴"]},
             {"name": "용도", "values": ["업소용", "가정용", "캠핑용"]}], _table())
        self.assertEqual(len([a for a in out if a["attributeSeq"] == 1]), 1)
        self.assertEqual(len([a for a in out if a["attributeSeq"] == 2]), 2)
        self.assertEqual(sorted(d["value"] for d in dropped if d["reason"] == "over_select_limit"),
                         ["전기그릴", "캠핑용"])

    def test_없는값_없는속성_범위형(self):
        out, dropped = A.resolve_attributes(
            [{"name": "품목", "values": ["워머기"]}, {"name": "색깔", "values": ["빨강"]},
             {"name": "무게", "values": ["1"]}], _table())
        self.assertEqual(out, [])
        reasons = {d["reason"] for d in dropped}
        self.assertEqual(reasons, {"value_not_in_choices", "unknown_attribute", "range_type_unsupported"})

    def test_keep_existing_병합(self):
        existing = [{"attributeSeq": 2, "attributeValueSeq": 22},
                    {"attributeSeq": 3, "attributeValueSeq": 31, "minAttributeValue": "1"}]
        new = [{"attributeSeq": 2, "attributeValueSeq": 21}, {"attributeSeq": 1, "attributeValueSeq": 11}]
        merged = A.merge_attributes(existing, new, keep_existing=True)
        self.assertIn({"attributeSeq": 3, "attributeValueSeq": 31, "minAttributeValue": "1"}, merged)
        self.assertNotIn({"attributeSeq": 2, "attributeValueSeq": 22}, merged)
        self.assertIn({"attributeSeq": 2, "attributeValueSeq": 21}, merged)
        self.assertEqual(A.merge_attributes(existing, new, keep_existing=False), new)


class MiscRulesTest(unittest.TestCase):
    def test_html_to_text(self):
        s = A.html_to_text(make_product()["originProduct"]["detailContent"])
        self.assertEqual(s, "스테인리스 & 보온")
        self.assertEqual(len(A.html_to_text("가" * 5000)), 3000)

    def test_불변검사(self):
        p = make_product()
        q = copy.deepcopy(p)
        q["originProduct"]["detailAttribute"]["seoInfo"]["sellerTags"] = [{"code": 1, "text": "x"}]
        self.assertEqual(A.invariant_diff(p, q), [])
        q["originProduct"]["salePrice"] = 1
        q["originProduct"]["detailAttribute"]["optionInfo"]["optionCombinations"][1]["price"] = 0
        self.assertEqual({d["field"] for d in A.invariant_diff(p, q)}, {"salePrice", "option_prices"})

    def test_build_body_원본불변(self):
        p = make_product()
        b = A.build_body(p, tags=[{"code": 1, "text": "x"}])
        self.assertEqual(p["originProduct"]["detailAttribute"]["seoInfo"]["sellerTags"], [{"text": "평문태그"}])
        self.assertEqual(b["originProduct"]["detailAttribute"]["seoInfo"]["pageTitle"], "t")
        self.assertEqual(b["originProduct"]["detailAttribute"]["productAttributes"],
                         p["originProduct"]["detailAttribute"]["productAttributes"])


# ---------------------------------------------------------------------------
# 통합 (prep / apply / revert)
# ---------------------------------------------------------------------------
class FlowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        d = os.path.join(self.root, "sold-lock", "2026-10-16")
        os.makedirs(d)
        with open(os.path.join(d, "new_locks.json"), "w", encoding="utf-8") as f:
            json.dump([{"마켓번호": "13-2", "스스상품번호": "100"}, {"마켓번호": "13-2", "스스상품번호": "200"},
                       {"마켓번호": "13-2", "스스상품번호": "100"}], f)
        self.run_dir = os.path.join(self.root, "attr-tag", "2026-10-16")
        self.board_rows = []

    def tearDown(self):
        self.tmp.cleanup()

    def _quiet(self, fn, *a, **kw):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = fn(*a, **kw)
        return rc, buf.getvalue()

    def _plan(self, entries):
        os.makedirs(self.run_dir, exist_ok=True)
        p = os.path.join(self.run_dir, "plan.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False)
        return p

    def _apply(self, api, plan, commit, board_fail=False):
        def bget(sid, rng):
            if board_fail:
                raise RuntimeError("gws down")
            return [["번호"], ["3"]]

        def bappend(sid, tab, rows):
            self.board_rows.extend(rows)
        args = SimpleNamespace(plan=plan, date="2026-10-16", commit=commit)
        return self._quiet(T.run_apply, args, api=api, data_root=self.root, board_append=bappend,
                           board_get=bget, work_board_id="SHEET")

    PLAN = [{"market": "13-2", "channel_no": "100", "tags": ["호텔용품", "뷔페", "보온", "식당용품"],
             "attributes": [{"name": "품목", "values": ["워머"]}, {"name": "용도", "values": ["업소용"]}],
             "keep_existing_attributes": True}]

    def test_prep(self):
        api = FakeApi()
        args = SimpleNamespace(date="2026-10-16", input=None, market=None, channel_no=None, force=False)
        rc, _ = self._quiet(T.run_prep, args, api=api, data_root=self.root)
        self.assertEqual(rc, 0)
        todo = _load(os.path.join(self.run_dir, "todo.json"))
        self.assertEqual([t["channel_no"] for t in todo], ["100", "200"])
        d = _load(os.path.join(self.run_dir, "prep_13-2_100.json"))
        self.assertEqual(d["category_path"], "디지털/가전>주방가전>기타주방가전")
        self.assertEqual(d["current_tags"], [{"text": "평문태그", "code": None, "has_code": False}])
        self.assertIn({"name": "용도", "value": "가정용"}, d["current_attributes"])
        self.assertEqual(d["options"], ["A. 9L", "B. 9L"])
        self.assertIn("https://img/1.jpg", d["image_urls"])
        self.assertEqual(len(d["available_attributes"]), 3)

    def test_apply_dryrun_쓰기0(self):
        api = FakeApi()
        rc, _ = self._apply(api, self._plan(self.PLAN), commit=False)
        self.assertEqual(rc, 0)
        self.assertEqual(api.puts, [])
        self.assertEqual(self.board_rows, [])
        d = _load(os.path.join(self.run_dir, "apply_dryrun.json"))
        it = d["items"][0]
        self.assertEqual([t["text"] for t in it["diff"]["tags_after"]], ["호텔용품", "식당용품"])
        self.assertFalse(os.path.exists(os.path.join(self.run_dir, "before_13-2_100.json")))

    def test_apply_commit_백업_확인_업무판_그리고_prep_건너뜀(self):
        api = FakeApi()
        rc, _ = self._apply(api, self._plan(self.PLAN), commit=True)
        self.assertEqual(rc, 0)
        self.assertEqual(api.puts, [("13-2", "100")])
        saved = api.products[("13-2", "100")]
        self.assertEqual(A.current_tags(saved), [{"code": 141955, "text": "호텔용품"},
                                                 {"code": 145201, "text": "식당용품"}])
        attrs = A.current_attributes(saved)
        self.assertIn({"attributeSeq": 3, "attributeValueSeq": 31, "minAttributeValue": "1"}, attrs)
        self.assertNotIn({"attributeSeq": 2, "attributeValueSeq": 22}, attrs)
        before = _load(os.path.join(self.run_dir, "before_13-2_100.json"))
        self.assertEqual(A.current_tags(before), [{"text": "평문태그"}])
        res = _load(os.path.join(self.run_dir, "result.json"))
        self.assertEqual(res["items"][0]["status"], "ok")
        self.assertEqual(res["board"], {"status": "ok"})
        self.assertEqual(self.board_rows[0][0], 4)
        self.assertEqual(self.board_rows[0][3], "⑥ 속성·태그 2026-10-16")
        self.assertEqual(self.board_rows[0][7], "상품 1 · 태그 평균 2.0개 · 속성 2개 · 실패 0")

        # 재실행해도 before 백업은 덮지 않는다
        self._apply(api, self._plan([dict(self.PLAN[0], tags=["호텔"])]), commit=True)
        before2 = _load(os.path.join(self.run_dir, "before_13-2_100.json"))
        self.assertEqual(A.current_tags(before2), [{"text": "평문태그"}])

        # 처리된 100 은 prep 에서 건너뛴다
        args = SimpleNamespace(date="2026-10-17", input=None, market=None, channel_no=None, force=False)
        os.makedirs(os.path.join(self.root, "sold-lock", "2026-10-17"))
        with open(os.path.join(self.root, "sold-lock", "2026-10-17", "new_locks.json"), "w") as f:
            json.dump([{"마켓번호": "13-2", "스스상품번호": "100"}], f)
        self._quiet(T.run_prep, args, api=api, data_root=self.root)
        self.assertFalse(os.path.exists(os.path.join(self.root, "attr-tag", "2026-10-17", "prep_13-2_100.json")))

    def test_불변위반_및_반영누락은_unverified(self):
        api = FakeApi(mutate_on_put=True)
        self._apply(api, self._plan(self.PLAN), commit=True)
        res = _load(os.path.join(self.run_dir, "result.json"))
        self.assertEqual(res["items"][0]["status"], "unverified")
        self.assertEqual(res["items"][0]["problems"][0]["what"], "invariant_changed")
        self.assertIs(self.board_rows[0][2], False)

        api2 = FakeApi(drop_tags_on_put=True)
        self._apply(api2, self._plan(self.PLAN), commit=True)
        res = _load(os.path.join(self.run_dir, "result.json"))
        self.assertEqual(res["items"][0]["problems"][0]["what"], "tags_missing")

    def test_한상품_실패_격리_시크릿_비노출_업무판실패(self):
        api = FakeApi(fail_put={"100"})
        plan = self.PLAN + [dict(self.PLAN[0], channel_no="200"), {"market": "13-2", "channel_no": "999",
                                                                   "tags": ["호텔"]}]
        rc, out = self._apply(api, self._plan(plan), commit=True, board_fail=True)
        self.assertEqual(rc, 0)
        self.assertEqual(api.puts, [("13-2", "200")])
        res = _load(os.path.join(self.run_dir, "result.json"))
        st = {r["channel_no"]: r["status"] for r in res["items"]}
        self.assertEqual(st, {"100": "failed", "200": "ok", "999": "failed"})
        self.assertEqual(res["board"]["status"], "failed")

    def test_시크릿_마스킹(self):
        """실제 CommerceApi 가 시크릿·토큰을 secrets 에 넣으면 로그·산출물에서 가려진다."""
        secrets = []

        class Client:
            def load_stores(self, markets):
                return {"13-2": {"name": "m", "client_id": "cid", "client_secret": SECRET}}, "sheet"

            def issue_token(self, st):
                return TOKEN, None

        class Resp:
            def __init__(self, code, text):
                self.status_code, self.text = code, text

            def json(self):
                return json.loads(self.text)

        class Http:
            def request(self, method, url, **kw):
                assert kw["headers"]["Authorization"] == f"Bearer {TOKEN}"
                return Resp(400, f'{{"msg":"bad {SECRET} {TOKEN}"}}')

        api = T.CommerceApi(Client(), secrets, http=Http(), sleep=lambda s: None)
        api.load(["13-2"])
        with self.assertRaises(RuntimeError) as cm:
            api.get_product("13-2", "1")
        self.assertNotIn(SECRET, str(cm.exception))
        self.assertNotIn(TOKEN, str(cm.exception))
        path = os.path.join(self.root, "x.json")
        T._write_json(path, {"e": str(cm.exception), "raw": SECRET}, secrets)
        with open(path, encoding="utf-8") as f:
            txt = f.read()
        self.assertNotIn(SECRET, txt)
        self.assertNotIn(TOKEN, txt)

    def test_레이트리밋_백오프(self):
        calls = {"n": 0}

        class Resp:
            def __init__(self, code, text):
                self.status_code, self.text = code, text

            def json(self):
                return json.loads(self.text)

        class Http:
            def request(self, method, url, **kw):
                calls["n"] += 1
                if calls["n"] == 1:
                    return Resp(400, '{"code":"GW.RATE_LIMIT"}')
                return Resp(200, '{"ok": 1}')

        class Client:
            def load_stores(self, markets):
                return {"13-2": {"client_id": "c", "client_secret": SECRET}}, "sheet"

            def issue_token(self, st):
                return TOKEN, None

        slept = []
        api = T.CommerceApi(Client(), [], http=Http(), sleep=slept.append)
        self.assertEqual(api.get_product("13-2", "1"), {"ok": 1})
        self.assertEqual(calls["n"], 2)
        self.assertTrue(any(s >= 2.0 for s in slept))

    def test_revert(self):
        api = FakeApi()
        self._apply(api, self._plan(self.PLAN), commit=True)
        n = len(api.puts)
        # dry-run: 쓰기 0
        args = SimpleNamespace(market="13-2", channel_no="100", date=None, date_given=False, commit=False)
        rc, _ = self._quiet(T.run_revert, args, api=api, data_root=self.root)
        self.assertEqual(rc, 0)
        self.assertEqual(len(api.puts), n)
        # 이름을 바꿔 둔 뒤 되돌려도 이름(다른 필드)은 현재값 유지
        api.products[("13-2", "100")]["originProduct"]["name"] = "바뀐 이름"
        args.commit = True
        rc, _ = self._quiet(T.run_revert, args, api=api, data_root=self.root)
        self.assertEqual(rc, 0)
        p = api.products[("13-2", "100")]
        self.assertEqual(A.current_tags(p), [{"text": "평문태그"}])
        self.assertIn({"attributeSeq": 2, "attributeValueSeq": 22}, A.current_attributes(p))
        self.assertEqual(p["originProduct"]["name"], "바뀐 이름")

    def test_revert_백업없음(self):
        args = SimpleNamespace(market="13-2", channel_no="100", date=None, date_given=False, commit=True)
        rc, _ = self._quiet(T.run_revert, args, api=FakeApi(), data_root=self.root)
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
