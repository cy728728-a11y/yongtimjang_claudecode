#!/usr/bin/env python3
"""공용 상품 스냅샷 회귀 테스트 — 네트워크·MCP 없이 돈다.

    python .claude/lib/eroomlib/test_snapshot.py

지키려는 계약:
  1. 이미 받아둔 상품은 **다시 조회하지 않는다** (스킬이 늘어도 workdata 는 상품당 1회)
  2. 저장 액션은 **자기가 바꾼 필드만** 되쓴다 (원문명 등 불변 필드는 그대로)
  3. 실패는 캐시하지 않는다 (다음 실행에서 재시도되어야 함)
  4. 소비 스킬 산출물의 **키 순서**가 종전과 같다 (products.json byte 동일 조건)
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eroomlib import snapshot  # noqa: E402

WD = {
    "productId": "P1", "상품명": "무선 마우스", "원문명": "无线鼠标",
    "옵션명": ["블랙"], "옵션명원문": ["黑色"], "옵션이미지": [],
    "기존카테고리": "디지털/가전>주변기기>마우스", "썸네일": ["http://x/1.jpg"],
    "원본링크": "http://taobao/1",
}


class FakeMCP:
    """workdata 호출 횟수를 세는 가짜 MCP."""

    def __init__(self, fail=()):
        self.calls = []
        self.fail = set(fail)

    def workdata(self, pid, mode="full"):
        self.calls.append(pid)
        if pid in self.fail:
            raise RuntimeError("조회 실패")
        return dict(WD, productId=pid, 불사자코드=f"CODE-{pid}", 타오바오상품번호="700001",
                    상세={"AI생성": False, "장수": 0, "생성일": "", "HTML": ""})


# 실측 workdata 원본의 축약 표본 — ProductMCP.workdata 의 '추출'을 직접 검증한다.
# (FakeMCP 는 그 계층을 통째로 대체하므로 추출 버그를 못 잡는다)
RAW = {"productName": "무선 마우스", "originalProductName": "无线鼠标",
       "uploadBulsajaCode": "CODE-1", "productNo": 700001,
       "uploadThumbnails": [], "uploadSkus": [], "product_url": "http://t/1",
       "uploadCategory": {"ss_category": {"name": ""}}}

# 실측 표본(2026-07-29 바체어 U01KY54HA4RRXCG02TS120GRM32) — AI 상세가 이미 생성된 상품
RAW_AI_DETAIL = dict(
    RAW,
    uploadDetailContents={
        "imageTranslated": "1",
        "aiImageGenerated": True,
        "aiImageOutputCount": 10,
        "aiImageGeneratedAt": "2026-07-23T04:51:33.024Z",
        "renderContent": "<div><img src='https://cdn.bulsaja.com/ai-image/output/1.jpg'></div>",
    },
)


class _StubWorkdataMCP(snapshot.ProductMCP):
    def __init__(self):  # transport 초기화 우회 — 네트워크 0
        pass

    def call_tool(self, name, payload):
        assert name == "bulsaja_product_workdata"
        return {"data": dict(RAW)}


class SnapshotBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="snapshot-test-")
        self._orig_root = snapshot.root
        snapshot.root = lambda: self.tmp

    def tearDown(self):
        snapshot.root = self._orig_root
        shutil.rmtree(self.tmp, ignore_errors=True)


class DualKeyTest(SnapshotBase):
    """대량다듬기(2026-07-28) 이중 키 — 불사자코드·타오바오상품번호."""

    def test_workdata가_원본에서_이중_키를_추출한다(self):
        rec = _StubWorkdataMCP().workdata("P1")
        self.assertEqual(rec["불사자코드"], "CODE-1")
        self.assertEqual(rec["타오바오상품번호"], "700001")  # int → str 강제 확인

    def test_키필드_없는_구_캐시는_require로_재조회된다(self):
        snapshot.save(dict(WD, productId="P1"))  # 구버전 레코드(새 필드 없음)
        mcp = FakeMCP()
        recs, _ = snapshot.ensure(
            ["P1"], mcp=mcp, sleep=0, log=None,
            require=("불사자코드", "타오바오상품번호"))
        self.assertEqual(mcp.calls, ["P1"], "구 캐시가 재조회되지 않았다")
        self.assertEqual(recs["P1"]["불사자코드"], "CODE-P1")

    def test_구_레코드의_투영은_키_순서까지_그대로다(self):
        rec = snapshot.save(dict(WD, productId="P1"))  # 새 필드 없는 레코드
        self.assertEqual(list(snapshot.as_workdata(rec)), list(WD))


class EnsureTest(SnapshotBase):
    def test_두_번째_스킬은_같은_상품을_다시_조회하지_않는다(self):
        mcp = FakeMCP()
        snapshot.ensure(["P1", "P2"], mcp=mcp, sleep=0, log=None)
        self.assertEqual(mcp.calls, ["P1", "P2"])
        # 다른 스킬이 같은 상품을 요구 → 캐시 적중
        recs, errors = snapshot.ensure(["P1", "P2"], mcp=mcp, sleep=0, log=None)
        self.assertEqual(mcp.calls, ["P1", "P2"], "캐시가 있는데 다시 조회했다")
        self.assertEqual(set(recs), {"P1", "P2"})
        self.assertFalse(errors)

    def test_섞여_있으면_없는_것만_조회한다(self):
        mcp = FakeMCP()
        snapshot.ensure(["P1"], mcp=mcp, sleep=0, log=None)
        snapshot.ensure(["P1", "P2", "P3"], mcp=mcp, sleep=0, log=None)
        self.assertEqual(mcp.calls, ["P1", "P2", "P3"])

    def test_실패는_캐시하지_않아_다음_실행에서_재시도된다(self):
        mcp = FakeMCP(fail={"P2"})
        recs, errors = snapshot.ensure(["P1", "P2"], mcp=mcp, sleep=0, log=None)
        self.assertIn("P2", errors)
        self.assertNotIn("P2", recs)
        self.assertFalse(os.path.exists(snapshot.product_path("P2")))
        mcp.fail.clear()
        recs, errors = snapshot.ensure(["P1", "P2"], mcp=mcp, sleep=0, log=None)
        self.assertEqual(mcp.calls, ["P1", "P2", "P2"], "실패건이 재시도되지 않았다")
        self.assertFalse(errors)

    def test_refresh_는_캐시를_무시한다(self):
        mcp = FakeMCP()
        snapshot.ensure(["P1"], mcp=mcp, sleep=0, log=None)
        snapshot.ensure(["P1"], mcp=mcp, sleep=0, log=None, refresh=True)
        self.assertEqual(mcp.calls, ["P1", "P1"])

    def test_중복_상품id_는_한_번만_조회한다(self):
        mcp = FakeMCP()
        snapshot.ensure(["P1", "P1", "P2"], mcp=mcp, sleep=0, log=None)
        self.assertEqual(mcp.calls, ["P1", "P2"])


class RequireTest(SnapshotBase):
    """스킬이 늘면 레코드에 필드가 추가된다 — 그 전 캐시는 다시 받아야 한다."""

    def test_요구_필드가_없는_캐시는_다시_받는다(self):
        mcp = FakeMCP()
        snapshot.ensure(["P1"], mcp=mcp, sleep=0, log=None)  # 옵션 없는 옛 레코드
        recs, _ = snapshot.ensure(["P1"], mcp=mcp, sleep=0, log=None, require=("옵션",))
        self.assertEqual(mcp.calls, ["P1", "P1"], "필드가 없는데 캐시를 그대로 썼다")

    def test_요구_필드가_있으면_다시_받지_않는다(self):
        mcp = FakeMCP()
        snapshot.save(dict(WD, productId="P1", 옵션={"차원": [], "판매행": []}))
        recs, _ = snapshot.ensure(["P1"], mcp=mcp, sleep=0, log=None, require=("옵션",))
        self.assertEqual(mcp.calls, [])
        self.assertIn("옵션", recs["P1"])


class OptionModelTest(unittest.TestCase):
    ONE_DIM = {
        "uploadSkuProps": {
            "mainOption": {"prop_name": "제품 유형", "_prop_name": "色", "values": [
                {"vid": 111, "name": "A. 100W", "_name": "100W泵", "imageUrl": "u1"},
                {"vid": 222, "name": "B. 280W", "_name": "280W泵", "exclude": True},
            ]},
            "subOption": [],
        },
        "uploadSkus": [
            {"id": "111", "text": "A. 100W", "_text": "100W泵", "sale_price": 46300,
             "origin_price": 21216, "stock": 200, "exclude": False, "main_product": True,
             "urlRef": "u1"},
            {"id": "222", "text": "B. 280W", "_text": "280W泵", "sale_price": 131200,
             "origin_price": 82784, "stock": 0, "exclude": True, "main_product": False},
        ],
    }
    MULTI_DIM = {
        "uploadSkuProps": {
            "mainOption": {"prop_name": "조명", "values": [{"vid": 1, "name": "A. 없음"}]},
            "subOption": [
                {"prop_name": "포장", "values": [{"vid": 1, "name": "A. 쌍 포장"}]},
                {"prop_name": "색상", "values": [{"vid": 1, "name": "A. 검정"},
                                                {"vid": 2, "name": "B. 흰색"}]},
            ],
        },
        "uploadSkus": [{"id": "1:1:1", "text": "A. 없음, A. 쌍 포장, A. 검정",
                        "sale_price": 91104}],
    }

    def test_1차원은_vid가_고유해_vid_리네임이_가능하다(self):
        m = snapshot.option_model(self.ONE_DIM)
        self.assertEqual(len(m["차원"]), 1)
        self.assertEqual(len(m["판매행"]), 2)
        self.assertTrue(m["vid고유"])
        self.assertEqual(m["판매행"][0]["sale_price"], 46300)
        self.assertTrue(m["판매행"][0]["main_product"])
        self.assertTrue(m["차원"][0]["values"][1]["exclude"])

    def test_복합옵션은_vid가_차원마다_1부터라_고유하지_않다(self):
        m = snapshot.option_model(self.MULTI_DIM)
        self.assertEqual([d["이름"] for d in m["차원"]], ["조명", "포장", "색상"])
        self.assertFalse(m["vid고유"], "vid 로 리네임하면 엉뚱한 차원이 바뀐다")
        self.assertEqual(m["판매행"][0]["id"], "1:1:1")

    def test_옵션이_없는_상품도_터지지_않는다(self):
        m = snapshot.option_model({})
        self.assertEqual(m, {"차원": [], "판매행": [], "vid고유": False})

    def test_as_workdata_는_옵션을_빼_기존_산출물을_유지한다(self):
        rec = dict(WD, 옵션=snapshot.option_model(self.ONE_DIM))
        self.assertEqual(list(snapshot.as_workdata(rec).keys()), list(WD.keys()))


class UpdateTest(SnapshotBase):
    def test_저장_액션은_자기가_바꾼_필드만_되쓴다(self):
        snapshot.ensure(["P1"], mcp=FakeMCP(), sleep=0, log=None)
        snapshot.update("P1", 기존카테고리="생활/건강>공구>드릴")
        rec = snapshot.load("P1")
        self.assertEqual(rec["기존카테고리"], "생활/건강>공구>드릴")
        self.assertEqual(rec["원문명"], WD["원문명"], "불변 필드가 훼손됐다")
        self.assertEqual(rec["상품명"], WD["상품명"])

    def test_갱신_후에도_재조회가_일어나지_않는다(self):
        mcp = FakeMCP()
        snapshot.ensure(["P1"], mcp=mcp, sleep=0, log=None)
        snapshot.update("P1", 상품명="새 상품명")
        recs, _ = snapshot.ensure(["P1"], mcp=mcp, sleep=0, log=None)
        self.assertEqual(mcp.calls, ["P1"])
        self.assertEqual(recs["P1"]["상품명"], "새 상품명")

    def test_스냅샷이_없으면_아무것도_만들지_않는다(self):
        self.assertIsNone(snapshot.update("없는상품", 상품명="x"))
        self.assertFalse(os.path.exists(snapshot.product_path("없는상품")))


class ProjectionTest(SnapshotBase):
    def test_as_workdata_는_메타를_빼고_키_순서를_유지한다(self):
        # FakeMCP 는 이중 키 2필드 + 상세 1필드를 함께 반환하지만, 투영은 이중 키까지만
        # 싣는다(상세는 소비 스킬이 쓰지 않는 무거운 필드라 제외 — 옵션과 같은 취급).
        # 구 레코드(새 필드 없음)의 byte 동일은 DualKeyTest·DetailFieldTest 가 별도로 지킨다.
        snapshot.ensure(["P1"], mcp=FakeMCP(), sleep=0, log=None)
        rec = snapshot.load("P1")
        self.assertIn("_수집일", rec)
        wd = snapshot.as_workdata(rec)
        expected_keys = list(WD.keys()) + ["불사자코드", "타오바오상품번호"]
        self.assertEqual(list(wd.keys()), expected_keys,
                         "products.json 키 순서가 바뀌면 기존 산출물과 어긋난다")
        self.assertEqual(wd, dict(WD, productId="P1",
                                  불사자코드="CODE-P1", 타오바오상품번호="700001"))


class SkuEvidenceTest(unittest.TestCase):
    def test_판매제외_옵션은_실물이_아니라_건너뛴다(self):
        ko, cn, img = snapshot.sku_evidence([
            {"text": "A. 블랙", "_text": "黑", "urlRef": "u1"},
            {"text": "B. 화이트", "_text": "白", "urlRef": "u2", "exclude": True},
        ])
        self.assertEqual(ko, ["블랙"])
        self.assertEqual(cn, ["黑"])
        self.assertEqual(img, ["u1"])

    def test_중복은_제거하고_8개까지만_넘긴다(self):
        skus = [{"text": f"{i}", "_text": f"c{i}"} for i in range(12)]
        skus += [{"text": "0", "_text": "c0"}]
        ko, cn, _ = snapshot.sku_evidence(skus)
        self.assertEqual(len(ko), 8)
        self.assertEqual(len(cn), 8)
        self.assertEqual(len(set(ko)), 8)

    def test_리스트가_아니면_빈_값(self):
        self.assertEqual(snapshot.sku_evidence(None), ([], [], []))


class ImageCacheTest(SnapshotBase):
    def setUp(self):
        super().setUp()
        self.hits = []

        class Resp:
            status_code = 200
            content = b"\x89PNG-fake-bytes"
            headers = {"Content-Type": "image/png"}

        def fake_get(url, **kw):
            self.hits.append(url)
            return Resp()

        import requests
        self._orig_get = requests.get
        requests.get = fake_get

    def tearDown(self):
        import requests
        requests.get = self._orig_get
        super().tearDown()

    def test_같은_URL_은_한_번만_받는다(self):
        url = "http://img/a.png"
        p1, _ = snapshot.fetch_image(url)
        p2, _ = snapshot.fetch_image(url)
        self.assertEqual(p1, p2)
        self.assertEqual(self.hits, [url], "캐시가 있는데 다시 받았다")

    def test_materialize_파일명은_기존_fetch_thumbs_규칙과_같다(self):
        out = os.path.join(self.tmp, "out")
        path, err = snapshot.materialize_image(
            "http://img/a.png", out, "U01KY54HA4TMJAGWM7WR40A00CK", 3)
        self.assertIsNone(err)
        # productId 24자 + _인덱스 + 확장자
        self.assertEqual(os.path.basename(path), "U01KY54HA4TMJAGWM7WR40A0_3.png")
        self.assertEqual(open(path, "rb").read(), b"\x89PNG-fake-bytes")

    def test_복사본을_고쳐도_캐시_원본은_그대로다(self):
        """상품명 스킬이 512px 로 줄이는 대상은 복사본이어야 한다."""
        out = os.path.join(self.tmp, "out")
        path, _ = snapshot.materialize_image("http://img/a.png", out, "P1", 0)
        with open(path, "wb") as f:
            f.write(b"shrunk")
        cached = snapshot.cached_image("http://img/a.png")
        self.assertEqual(open(cached, "rb").read(), b"\x89PNG-fake-bytes")

    def test_실패는_사유와_함께_None_을_준다(self):
        path, err = snapshot.materialize_image("", os.path.join(self.tmp, "o"), "P1", 0)
        self.assertIsNone(path)
        self.assertTrue(err)


class _StubDetailMCP(snapshot.ProductMCP):
    """uploadDetailContents 가 실린 workdata 원본을 그대로 돌려준다."""

    def __init__(self, raw):  # transport 초기화 우회 — 네트워크 0
        self._raw = raw

    def call_tool(self, name, payload):
        assert name == "bulsaja_product_workdata"
        return {"data": dict(self._raw)}


class CollectGroupTest(SnapshotBase):
    """마켓그룹 수집 — 잠금 필드 보존."""

    def setUp(self):
        super().setUp()
        # 스톱 MCP: bulsaja_market_group_products 응답을 흉내낸다
        class _StubCollectMCP(snapshot.ProductMCP):
            def __init__(self):
                pass
            def call_tool(self, name, payload):
                assert name == "bulsaja_market_group_products"
                # 1페이지만 반환 (더있음=False)
                return {
                    "항목": [
                        {"productId": "P1", "상품명": "상품1", "상태코드": 4, "잠금": True},
                        {"productId": "P2", "상품명": "상품2", "상태코드": 2, "잠금": False},
                        {"productId": "P3", "상품명": "상품3", "상태코드": 0},  # 잠금 필드 없는 경우
                    ],
                    "총상품수": 3,
                    "더있음": False,
                }
        self.mcp = _StubCollectMCP()

    def test_collect_group이_잠금_필드를_보존한다(self):
        out = self.mcp.collect_group("1001114", sleep=0)
        self.assertEqual(len(out), 3)
        # 첫 번째 상품: 잠금=True
        self.assertEqual(out[0]["productId"], "P1")
        self.assertEqual(out[0]["상품명"], "상품1")
        self.assertEqual(out[0]["상태코드"], 4)
        self.assertTrue(out[0]["잠금"])
        # 두 번째 상품: 잠금=False
        self.assertEqual(out[1]["productId"], "P2")
        self.assertFalse(out[1]["잠금"])
        # 세 번째 상품: 잠금 필드 없는 경우 None
        self.assertEqual(out[2]["productId"], "P3")
        self.assertIsNone(out[2]["잠금"])

    def test_collect_group_출력이_필수_필드를_포함한다(self):
        out = self.mcp.collect_group("1001114", sleep=0)
        for item in out:
            self.assertIn("productId", item)
            self.assertIn("상품명", item)
            self.assertIn("상태코드", item)
            self.assertIn("잠금", item)


class DetailFieldTest(SnapshotBase):
    """상세 스킬(Step6)이 쓰는 `상세` 필드 추출."""

    def test_AI생성된_상품은_생성정보를_전부_뽑는다(self):
        rec = _StubDetailMCP(RAW_AI_DETAIL).workdata("P1")
        self.assertEqual(rec["상세"]["AI생성"], True)
        self.assertEqual(rec["상세"]["장수"], 10)
        self.assertEqual(rec["상세"]["생성일"], "2026-07-23T04:51:33.024Z")
        self.assertIn("cdn.bulsaja.com", rec["상세"]["HTML"])

    def test_상세블록이_없으면_AI생성은_False다(self):
        rec = _StubDetailMCP(RAW).workdata("P1")   # uploadDetailContents 자체가 없음
        self.assertEqual(rec["상세"]["AI생성"], False)
        self.assertEqual(rec["상세"]["장수"], 0)
        self.assertEqual(rec["상세"]["HTML"], "")

    def test_원본상세만_있고_AI생성_안된_상품(self):
        raw = dict(RAW, uploadDetailContents={
            "renderContent": "<div><img src='https://img.alicdn.com/o.jpg'></div>"})
        rec = _StubDetailMCP(raw).workdata("P1")
        self.assertEqual(rec["상세"]["AI생성"], False)
        self.assertIn("alicdn", rec["상세"]["HTML"], "복구용 백업이라 원본 HTML도 보관한다")

    def test_구_레코드의_투영은_키_순서까지_그대로다(self):
        rec = snapshot.save(dict(WD, productId="P1"))
        self.assertEqual(list(snapshot.as_workdata(rec)), list(WD))

    def test_as_workdata_는_상세를_빼_products_json_을_가볍게_유지한다(self):
        # 이 투영의 유일한 소비자는 카테고리교정의 products.json 이고, 그 스킬은 상세를
        # 쓰지 않는다. 실으면 상품마다 타오바오 원본 마크업이 통째로 딸려간다
        # (1,000건이면 수십 MB). 옵션 필드를 뺀 것과 같은 이유·같은 선례.
        rec = dict(WD, productId="P1",
                   상세={"AI생성": True, "장수": 8, "생성일": "2026-07-29",
                        "HTML": "<div>" + "x" * 10000 + "</div>"})
        wd = snapshot.as_workdata(rec)
        self.assertNotIn("상세", wd)
        self.assertEqual(list(wd.keys()), list(WD.keys()))
        self.assertEqual(snapshot.save(rec)["상세"]["장수"], 8,
                         "레코드에는 남아 있어야 한다 — 상세 스킬이 이걸 읽는다")

    def test_상세필드_없는_구_캐시는_require로_재조회된다(self):
        snapshot.save(dict(WD, productId="P1"))
        mcp = FakeMCP()
        recs, _ = snapshot.ensure(["P1"], mcp=mcp, sleep=0, log=None, require=("상세",))
        self.assertEqual(mcp.calls, ["P1"], "구 캐시가 재조회되지 않았다")


class _PollMCP(snapshot.ProductMCP):
    """상태 응답을 순서대로 돌려주는 스텁 — 네트워크·대기 0."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.payloads = []

    def call_tool(self, name, payload):
        assert name == "bulsaja_detail_page_status"
        self.payloads.append(payload)
        return self._responses.pop(0)


class PollAiTaskTest(unittest.TestCase):
    def test_완료되면_이미지와_크레딧을_돌려준다(self):
        mcp = _PollMCP([
            {"완료여부": False},
            {"완료여부": True, "생성이미지": ["u1", "u2"], "사용크레딧": 40},
        ])
        imgs, credits = mcp.poll_ai_task("T1", target="detail",
                                         interval=0, sleep_fn=lambda s: None)
        self.assertEqual(imgs, ["u1", "u2"])
        self.assertEqual(credits, 40)

    def test_target을_그대로_실어_보낸다(self):
        mcp = _PollMCP([{"완료여부": True, "생성이미지": ["u"], "사용크레딧": 5}])
        mcp.poll_ai_task("T1", target="thumbnail", interval=0, sleep_fn=lambda s: None)
        self.assertEqual(mcp.payloads[0],
                         {"taskId": "T1", "target": "thumbnail"})

    def test_영문_키_응답도_읽는다(self):
        mcp = _PollMCP([{"completed": True, "imageUrls": ["u"], "consumedCredits": 5}])
        imgs, credits = mcp.poll_ai_task("T1", interval=0, sleep_fn=lambda s: None)
        self.assertEqual((imgs, credits), (["u"], 5))

    def test_실패내역이_있으면_RuntimeError(self):
        mcp = _PollMCP([{"실패내역": ["크레딧 부족"]}])
        with self.assertRaises(RuntimeError):
            mcp.poll_ai_task("T1", interval=0, sleep_fn=lambda s: None)

    def test_시간초과면_TimeoutError(self):
        mcp = _PollMCP([{"완료여부": False}] * 5)
        with self.assertRaises(TimeoutError):
            mcp.poll_ai_task("T1", interval=1, timeout=2, sleep_fn=lambda s: None)


class ShrinkImageTest(unittest.TestCase):
    """비전 토큰 절감의 단일 지점. 네 스킬이 전부 이 함수를 지난다.

    계약: 줄이는 대상은 **복사본뿐**이고, 실패는 조용히 원본을 남긴다
    (한 장 때문에 prep 전체가 멈추면 안 된다).
    """

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        try:
            from PIL import Image  # noqa: F401
            self.pil = True
        except ImportError:
            self.pil = False

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _make(self, w, h, name="x.jpg"):
        from PIL import Image
        p = os.path.join(self.dir, name)
        Image.new("RGB", (w, h), (200, 30, 30)).save(p, "JPEG")
        return p

    def _size(self, p):
        from PIL import Image
        with Image.open(p) as im:
            return im.size

    def test_긴변이_max_px_로_줄고_비율이_유지된다(self):
        if not self.pil:
            self.skipTest("Pillow 없음")
        p = self._make(1000, 500)
        self.assertTrue(snapshot.shrink_image(p, 512))
        self.assertEqual(self._size(p), (512, 256))

    def test_이미_작으면_건드리지_않는다(self):
        if not self.pil:
            self.skipTest("Pillow 없음")
        p = self._make(400, 400)
        before = os.path.getsize(p)
        self.assertFalse(snapshot.shrink_image(p, 512))
        self.assertEqual(self._size(p), (400, 400))
        self.assertEqual(os.path.getsize(p), before)

    def test_max_px_가_0_이거나_None_이면_no_op(self):
        if not self.pil:
            self.skipTest("Pillow 없음")
        p = self._make(1000, 1000)
        for v in (0, None, -1):
            self.assertFalse(snapshot.shrink_image(p, v))
        self.assertEqual(self._size(p), (1000, 1000))

    def test_깨진_파일이어도_예외를_던지지_않는다(self):
        p = os.path.join(self.dir, "broken.jpg")
        with open(p, "wb") as f:
            f.write(b"not an image")
        self.assertFalse(snapshot.shrink_image(p, 512))  # 원본 그대로 남는다
        self.assertTrue(os.path.exists(p))

    def test_없는_경로도_예외를_던지지_않는다(self):
        self.assertFalse(snapshot.shrink_image(os.path.join(self.dir, "없음.jpg"), 512))


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")  # unittest 진행 로그가 stderr 로 나간다
    except Exception:
        pass
    unittest.main(verbosity=2)
