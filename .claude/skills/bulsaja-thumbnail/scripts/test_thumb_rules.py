#!/usr/bin/env python3
"""썸네일 규칙 회귀 테스트 — 불사자·시트 없이 돈다.

    python .claude/skills/bulsaja-thumbnail/scripts/test_thumb_rules.py

호스트 판별은 캘리브레이션 실측 URL(2026-07-28)을 그대로 박제한다 — 규칙이 바뀌면
여기가 제일 먼저 깨져야 한다.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import thumb_rules as R  # noqa: E402

# 실측 URL (이번 세션 캘리브레이션)
ORIGINAL = "https://img.alicdn.com/bao/uploaded/i4/1103720702/O1CN01rkWiY61H3Z3SiKTjv_!!4611686018427384062-0-item_pic.jpg"
PROCESSED_MCP_ASSETS = "https://cdn.bulsaja.com/mcp-assets/11154/U01KY54HA4RRXCG02TS120GRM32/thumbnail/7754d2013cfe074ca963b56b7cc3e52f453fb77a4"
PROCESSED_SOURCING = "https://cdn.bulsaja.com/sourcing-product/images/U01KPZYXXRECAVR0Z8K2ZD1AVKA/thumbnail-image/1SOeYCF2t7yRqTu.jpeg"
PROCESSED_PRODUCTS = "https://cdn.bulsaja.com/products/U01K10FF4B2A12D71K0DXKAPEX1/a73962d2-713e-4544-8da2-640a3ffd4f1d.jpg"
PROCESSED_AI_OUTPUT = "https://cdn.bulsaja.com/ai-image/output/11154/5c1d2bfc464f8192c726e688c5e8e4c948da6cc3fb4acad315e32769e68c72f4-ef077f993beae00afa43d53b67fd0472451808a626afbc7c4ad5cd2b419cf9e1.jpg"


class HostTest(unittest.TestCase):
    def test_원본_호스트는_미가공(self):
        self.assertFalse(R.is_processed_url(ORIGINAL))
        self.assertEqual(R.host_of(ORIGINAL), "img.alicdn.com")

    def test_가공_경로_4종_전부_가공됨(self):
        for url in (PROCESSED_MCP_ASSETS, PROCESSED_SOURCING,
                    PROCESSED_PRODUCTS, PROCESSED_AI_OUTPUT):
            self.assertTrue(R.is_processed_url(url), url)
            self.assertEqual(R.host_of(url), "cdn.bulsaja.com")

    def test_빈_URL은_미가공(self):
        self.assertFalse(R.is_processed_url(""))
        self.assertFalse(R.is_processed_url(None))


class ProductStatusTest(unittest.TestCase):
    def test_대표가_가공물이면_가공됨(self):
        self.assertEqual(R.product_status([PROCESSED_MCP_ASSETS, ORIGINAL]), "가공됨")

    def test_대표가_원본이면_미가공(self):
        self.assertEqual(R.product_status([ORIGINAL, ORIGINAL]), "미가공")

    def test_후보에_가공물_있어도_대표가_원본이면_미가공(self):
        # 실측: products/<다른pid> 패턴이 후보 자리(1번 이후)에 섞여 등장한 사례가 있었다.
        # 판별은 항상 0번(대표)만 본다.
        self.assertEqual(R.product_status([ORIGINAL, PROCESSED_PRODUCTS]), "미가공")

    def test_빈_목록은_미확인(self):
        self.assertEqual(R.product_status([]), "미확인")

    def test_is_already_done_은_product_status_과_일치(self):
        self.assertTrue(R.is_already_done([PROCESSED_SOURCING, ORIGINAL]))
        self.assertFalse(R.is_already_done([ORIGINAL, ORIGINAL]))


class NeedsAuditTest(unittest.TestCase):
    """가공됨 ≠ 맞게 가공됨 (2026-08-05 실측 불량률 68%) — 백필 3갈래 게이트의 순수 부분."""

    def test_가공됨_대표옵션_있음은_정합검사_대상(self):
        self.assertTrue(R.needs_audit([PROCESSED_SOURCING],
                                      {"이름": "3톤", "이미지": "https://a/3t.jpg"}))

    def test_가공됨_대표옵션_없음은_대상_아님(self):
        # 대조할 근거가 없다 → 종전대로 백필
        self.assertFalse(R.needs_audit([PROCESSED_SOURCING], None))
        self.assertFalse(R.needs_audit([PROCESSED_SOURCING], {"이름": "3톤", "이미지": ""}))

    def test_미가공은_대표옵션이_있어도_대상_아님(self):
        # 미가공은 생성 대상이지 감사 대상이 아니다
        self.assertFalse(R.needs_audit([ORIGINAL],
                                       {"이름": "3톤", "이미지": "https://a/3t.jpg"}))
        self.assertFalse(R.needs_audit([], {"이름": "3톤", "이미지": "https://a/3t.jpg"}))


class AuditPartitionTest(unittest.TestCase):
    """audit 판정 분류 — 대조불가는 flag 하지 않는다(무한 재작업 루프 방지)."""

    def test_판정_4종을_나눈다(self):
        mism, match, unc, sus = R.audit_partition([
            {"productId": "U01a", "판정": "불일치", "사유": "3000W인데 8500W 표기"},
            {"productId": "U01b", "판정": "일치"},
            {"productId": "U01c", "판정": "대조불가", "사유": "옵션 이미지 404"},
            {"productId": "U01d", "판정": "대표옵션의심",
             "사유": "대표옵션이 걸이판 부속 — 상품명은 캠핑박스"},
        ])
        self.assertEqual(mism, {"U01a": "3000W인데 8500W 표기"})
        self.assertEqual(match, ["U01b"])
        self.assertEqual(unc, {"U01c": "옵션 이미지 404"})
        self.assertEqual(sus, {"U01d": "대표옵션이 걸이판 부속 — 상품명은 캠핑박스"})

    def test_모르는_판정값은_대조불가로_본다(self):
        # fail-safe — 함부로 재작업을 만들지 않는다
        mism, match, unc, sus = R.audit_partition([
            {"productId": "U01x", "판정": "애매함"},
            {"productId": "U01y"},
        ])
        self.assertEqual((mism, match, sus), ({}, [], {}))
        self.assertEqual(set(unc), {"U01x", "U01y"})

    def test_불일치_사유가_비면_기본값을_채운다(self):
        # 사유는 그대로 현황판 재작업 문구에 실린다 — 빈 문자열로 두지 않는다
        mism, _, _, _ = R.audit_partition([{"productId": "U01a", "판정": "불일치"}])
        self.assertEqual(mism, {"U01a": "대표옵션 불일치"})

    def test_대표옵션의심_사유가_비면_기본값을_채운다(self):
        _, _, _, sus = R.audit_partition([{"productId": "U01a", "판정": "대표옵션의심"}])
        self.assertEqual(sus, {"U01a": "대표옵션이 본품이 아님(부속 의심)"})

    def test_pid_없는_행은_버린다(self):
        self.assertEqual(R.audit_partition([{"판정": "불일치"}]), ({}, [], {}, {}))
        self.assertEqual(R.audit_partition(None), ({}, [], {}, {}))


class CreditTest(unittest.TestCase):
    def test_장당_5크레딧(self):
        self.assertEqual(R.credit_estimate(1), 5)
        self.assertEqual(R.credit_estimate(10), 50)

    def test_커스텀_단가(self):
        self.assertEqual(R.credit_estimate(2, per_image=10), 20)


class AutoReflectTest(unittest.TestCase):
    """파일럿 실측(2026-07-28, U01KYMCESDCMAMKNE9RAMYP8Z49)에서 확인된 자동반영 감지."""

    def test_생성_전후_대표가_바뀌면_감지한다(self):
        before = [ORIGINAL, ORIGINAL, ORIGINAL]
        after = [PROCESSED_AI_OUTPUT, ORIGINAL, ORIGINAL, ORIGINAL]
        self.assertTrue(R.representative_changed(before, after))

    def test_대표가_그대로면_감지하지_않는다(self):
        before = [ORIGINAL, ORIGINAL]
        after = [ORIGINAL, ORIGINAL]
        self.assertFalse(R.representative_changed(before, after))

    def test_둘_다_비어있으면_변화_없음(self):
        self.assertFalse(R.representative_changed([], []))

    def test_생성_전이_비어있으면_변화로_본다(self):
        self.assertTrue(R.representative_changed([], [PROCESSED_AI_OUTPUT]))


class RegenTest(unittest.TestCase):
    def test_기본_상한_2회(self):
        self.assertTrue(R.can_regenerate(0))
        self.assertTrue(R.can_regenerate(1))
        self.assertFalse(R.can_regenerate(2))

    def test_커스텀_상한(self):
        self.assertTrue(R.can_regenerate(2, max_regen=3))
        self.assertFalse(R.can_regenerate(3, max_regen=3))


class ReviewRowTest(unittest.TestCase):
    def test_기본_필드_구성(self):
        row = R.review_row("U01K...", "바체어", ORIGINAL, [ORIGINAL, ORIGINAL],
                            generated_url=PROCESSED_AI_OUTPUT, verdict="사용가능",
                            reason="색상 일치 확인")
        self.assertEqual(row["productId"], "U01K...")
        self.assertEqual(row["기존대표"], ORIGINAL)
        self.assertEqual(len(row["후보"]), 2)
        self.assertEqual(row["판정"], "사용가능")

    def test_판정_대기중이면_None(self):
        row = R.review_row("pid", "이름", ORIGINAL, [])
        self.assertIsNone(row["판정"])

    def test_후보_기본값은_빈_리스트(self):
        row = R.review_row("pid", "이름", ORIGINAL, None)
        self.assertEqual(row["후보"], [])


class RedoReasonTest(unittest.TestCase):
    def test_현황판_재작업_문구에서_사유만_뽑는다(self):
        v = "재작업(썸네일: 대표 썸네일이 검정인데 옵션에 검정 없음(호두색/원목색뿐))"
        self.assertEqual(
            R.redo_reason_from_flag(v),
            "대표 썸네일이 검정인데 옵션에 검정 없음(호두색/원목색뿐)")

    def test_형식이_다르면_원문_그대로(self):
        self.assertEqual(R.redo_reason_from_flag("완료"), "완료")
        self.assertEqual(R.redo_reason_from_flag(""), "")


def _opt(rows):
    return {"차원": [], "판매행": rows, "vid고유": True}


def _row(rid, main=False, text="", url=""):
    return {"id": rid, "text": text or f"opt{rid}", "sale_price": 1000,
            "stock": 5, "exclude": False, "main_product": main, "urlRef": url}


class MainOptionTest(unittest.TestCase):
    """썸네일 = 대표옵션 = 상품명 정합 (2026-07-30 이룸님).

    썸네일은 글자가 없어 `기본형` 마커를 쓸 수 없다 — 대표옵션 이미지를 기준으로 못박는다.
    """

    def test_대표옵션의_이름과_이미지를_뽑는다(self):
        o = _opt([_row("1", main=True, text="3톤 기본형", url="https://a/3t.jpg"),
                  _row("2", text="10톤", url="https://a/10t.jpg")])
        self.assertEqual(R.main_option_of(o),
                         {"이름": "3톤 기본형", "이미지": "https://a/3t.jpg"})

    def test_대표가_없으면_None이다(self):
        # 옵션정리를 안 거친 상품 → 호출부가 종전 비전 판단으로 폴백한다
        self.assertIsNone(R.main_option_of(_opt([_row("1"), _row("2")])))

    def test_옵션이_없으면_None이다(self):
        self.assertIsNone(R.main_option_of({}))
        self.assertIsNone(R.main_option_of(None))

    def test_이미지가_비어도_이름은_넘긴다(self):
        # 이름만으로도 검수 화면에서 대조할 수 있다(이미지 없으면 기준 고정만 못 한다)
        o = _opt([_row("1", main=True, text="블랙 기본형", url="")])
        self.assertEqual(R.main_option_of(o), {"이름": "블랙 기본형", "이미지": ""})

    def test_review_row가_대표옵션을_실어_보낸다(self):
        r = R.review_row("U01", "바체어", "https://a/rep.jpg", ["https://a/c1.jpg"],
                         main_option={"이름": "원목 기본형", "이미지": "https://a/m.jpg"})
        self.assertEqual(r["대표옵션명"], "원목 기본형")
        self.assertEqual(r["대표옵션이미지"], "https://a/m.jpg")

    def test_review_row는_대표옵션이_없어도_빈값으로_돈다(self):
        r = R.review_row("U01", "바체어", "https://a/rep.jpg", [])
        self.assertEqual(r["대표옵션명"], "")
        self.assertEqual(r["대표옵션이미지"], "")


class 기준이미지_해석(unittest.TestCase):
    """생성에 실제로 태울 기준 이미지 — 2026-08-05 실측 사고(기준이 무시됨)의 회귀 방어."""

    def test_워커가_고른_후보index를_URL로_바꾼다(self):
        p = {"기존썸네일": ["https://a/0.jpg", "https://a/1.jpg", "https://a/2.jpg"],
             "후보이미지": [{"index": 1, "url": "https://a/1.jpg"},
                        {"index": 2, "url": "https://a/2.jpg"}],
             "기준이미지": 2}
        self.assertEqual(R.reference_url(p), "https://a/2.jpg")

    def test_기준이미지_0은_기존대표다(self):
        p = {"기존썸네일": ["https://a/0.jpg", "https://a/1.jpg"],
             "후보이미지": [{"index": 1, "url": "https://a/1.jpg"}], "기준이미지": 0}
        self.assertEqual(R.reference_url(p), "https://a/0.jpg")

    def test_선기록은_대표옵션이미지가_기준이다(self):
        p = {"기존썸네일": ["https://a/0.jpg"], "대표옵션이미지": "https://a/main.jpg"}
        self.assertEqual(R.reference_url(p), "https://a/main.jpg")

    def test_워커판단이_대표옵션URL보다_우선이다(self):
        # 대표옵션 이미지 다운로드가 실패해 비전 판단으로 넘어온 상품 — 워커 판단을 덮지 않는다
        p = {"기존썸네일": ["https://a/0.jpg", "https://a/1.jpg"],
             "후보이미지": [{"index": 1, "url": "https://a/1.jpg"}],
             "기준이미지": 1, "대표옵션이미지": "https://a/main.jpg"}
        self.assertEqual(R.reference_url(p), "https://a/1.jpg")

    def test_아무_판단도_없으면_기존대표다(self):
        self.assertEqual(R.reference_url({"기존썸네일": ["https://a/0.jpg"]}),
                         "https://a/0.jpg")
        self.assertEqual(R.reference_url({}), "")


class 기준_스테이징(unittest.TestCase):

    def test_기준이_이미_대표면_바꾸지_않는다(self):
        self.assertIsNone(R.staged_thumbnails(["https://a/0.jpg", "https://a/1.jpg"],
                                              "https://a/0.jpg"))

    def test_배열_안의_기준을_맨_앞으로_옮긴다(self):
        got = R.staged_thumbnails(["https://a/0.jpg", "https://a/1.jpg", "https://a/2.jpg"],
                                  "https://a/2.jpg")
        self.assertEqual(got, ["https://a/2.jpg", "https://a/0.jpg", "https://a/1.jpg"])

    def test_배열에_없는_기준은_맨_앞에_끼워넣는다(self):
        # 대표옵션 이미지는 썸네일 목록 밖인 경우가 대부분(실측 303/311)
        got = R.staged_thumbnails(["https://a/0.jpg"], "https://a/main.jpg")
        self.assertEqual(got, ["https://a/main.jpg", "https://a/0.jpg"])

    def test_기준이_없으면_None이다(self):
        self.assertIsNone(R.staged_thumbnails(["https://a/0.jpg"], ""))
        self.assertIsNone(R.staged_thumbnails(["https://a/0.jpg"], None))

    def test_썸네일이_비면_None이다(self):
        self.assertIsNone(R.staged_thumbnails([], "https://a/main.jpg"))

    def test_중복을_만들지_않는다(self):
        got = R.staged_thumbnails(["https://a/0.jpg", "https://a/1.jpg"], "https://a/1.jpg")
        self.assertEqual(got.count("https://a/1.jpg"), 1)


class 생성계획_재개(unittest.TestCase):
    """`--generate` 재실행이 이미 태운 건을 또 태우면 안 된다(2026-08-05 F안).

    1-3 회차 실측: DNS 단절로 63건에서 멈췄는데 재실행이 처음부터 다시 태우는
    구조였다 — 315크레딧 중복 과금 + 끝낸 검수 무효화.
    """

    ITEMS = [{"productId": "A"}, {"productId": "B"}, {"productId": "C"}]

    def test_성공한_건은_건너뛴다(self):
        prev = {"A": {"생성본": "https://x/a.jpg"}}
        todo, skipped = R.generate_plan(self.ITEMS, prev)
        self.assertEqual([p["productId"] for p in todo], ["B", "C"])
        self.assertEqual(skipped, [("A", "이미 생성됨(재개)")])

    def test_실패기록만_있으면_다시_시도한다(self):
        # 실패 원인은 대개 일시적 네트워크다 — 재개 때 다시 태워야 한다.
        prev = {"A": {"오류": "RuntimeError: DNS"}}
        todo, _ = R.generate_plan(self.ITEMS, prev)
        self.assertEqual([p["productId"] for p in todo], ["A", "B", "C"])

    def test_기록이_없으면_전건_생성한다(self):
        todo, skipped = R.generate_plan(self.ITEMS, {})
        self.assertEqual(len(todo), 3)
        self.assertEqual(skipped, [])

    def test_ids로_지목하면_성공분도_다시_태운다(self):
        # 검수 불합격분 재생성 경로 — 성공 기록이 있어도 대상이다.
        prev = {"A": {"생성본": "https://x/a.jpg", "재생성횟수": 1}}
        todo, skipped = R.generate_plan(self.ITEMS, prev, only_ids=["A"])
        self.assertEqual([p["productId"] for p in todo], ["A"])
        self.assertEqual(sorted(pid for pid, _ in skipped), ["B", "C"])

    def test_재생성_상한을_넘기면_막는다(self):
        prev = {"A": {"생성본": "https://x/a.jpg", "재생성횟수": R.MAX_REGEN}}
        todo, skipped = R.generate_plan(self.ITEMS, prev, only_ids=["A"])
        self.assertEqual(todo, [])
        self.assertIn(f"재생성 상한 {R.MAX_REGEN}회 도달", dict(skipped)["A"])

    def test_ids로_지목한_미생성건은_상한과_무관하다(self):
        todo, _ = R.generate_plan(self.ITEMS, {}, only_ids=["B"])
        self.assertEqual([p["productId"] for p in todo], ["B"])


class RecoverTest(unittest.TestCase):
    """타임아웃 회수 — 접수됐는데 폴링이 못 기다린 건을 taskId 로 되찾는다."""

    # 2026-08-06 실측 그대로. 그때는 taskId 전용 필드가 없어서 오류 문자열뿐이었다.
    OLD_TIMEOUT = {"상품명": "세라믹 타원형거실테이블 대리석 골드 기본형",
                   "오류": "TimeoutError: 타임아웃(300s): taskId=15652"}

    def test_taskId_필드가_정본이다(self):
        rec = {"taskId": 20001, "오류": "TimeoutError: 타임아웃(300s): taskId=15652"}
        self.assertEqual(R.task_id_of(rec), "20001")

    def test_필드가_없으면_오류_문자열에서_뽑는다(self):
        self.assertEqual(R.task_id_of(self.OLD_TIMEOUT), "15652")

    def test_taskId_가_없으면_None(self):
        self.assertIsNone(R.task_id_of({"오류": "NameResolutionError: DNS 단절"}))
        self.assertIsNone(R.task_id_of({}))
        self.assertIsNone(R.task_id_of(None))

    def test_결과를_받은_기록은_taskId가_없어서_대상이_아니다(self):
        # 성공 기록은 새 dict 로 통째로 갈려서 taskId·오류가 남지 않는다.
        gen = {"A": {"생성본": "https://x/a.jpg", "재생성횟수": 1},
               "B": dict(self.OLD_TIMEOUT)}
        self.assertEqual(R.recover_targets(gen), {"B": "15652"})

    def test_재생성이_타임아웃하면_옛_생성본이_있어도_회수한다(self):
        # 옛 이미지는 이미 불합격 판정된 것 — 새 결과로 덮는 게 목적이다.
        gen = {"A": {"생성본": "https://x/old.jpg", "재생성횟수": 1, "taskId": 15660,
                     "오류": "TimeoutError: 타임아웃(300s): taskId=15660"}}
        self.assertEqual(R.recover_targets(gen), {"A": "15660"})

    def test_taskId_없는_실패는_회수할_수_없다(self):
        gen = {"A": {"오류": "RuntimeError: 확인키 미발급"}}
        self.assertEqual(R.recover_targets(gen), {})

    def test_ids로_범위를_좁힌다(self):
        gen = {"A": {"taskId": 1}, "B": {"taskId": 2}}
        self.assertEqual(R.recover_targets(gen, only_ids=["B"]), {"B": "2"})


class ToOptionVerdictTest(unittest.TestCase):
    """썸네일이 아니라 **옵션 단계로 되돌릴** 판정값 (2026-08-07 이룸님).

    둘 다 뿌리가 대표옵션이다 — 재생성·fallback 은 같은 기준을 다시 쓰는 것이라 교정이
    아니다. `기준이미지없음`(대표옵션이 도면·배너)을 2026-08-07 에 합류시켰다:
    "아예 대표옵션 새로 정하는 걸로, 옵션 단계로 돌아가서 다시 하는 걸로 자동화하자."
    """

    def test_두_판정값이_모두_들어_있다(self):
        self.assertIn(R.AUDIT_MAIN_SUSPECT, R.TO_OPTION_VERDICTS)
        self.assertIn(R.VERDICT_NO_BASE, R.TO_OPTION_VERDICTS)

    def test_판정_문자열에서_찾아낸다(self):
        """실제 판정은 `제외(기준이미지없음)` 처럼 감싸여 온다."""
        for verdict, want in (("제외(기준이미지없음)", R.VERDICT_NO_BASE),
                              ("제외(대표옵션의심)", R.AUDIT_MAIN_SUSPECT)):
            with self.subTest(verdict=verdict):
                hit = next((v for v in R.TO_OPTION_VERDICTS if v in verdict), None)
                self.assertEqual(hit, want)

    def test_그_밖의_제외는_옵션으로_안_보낸다(self):
        """구성·색 불일치는 썸네일 쪽 문제라 재생성·fallback 경로로 남는다."""
        for verdict in ("제외", "제외(글자변조)", "사용가능"):
            with self.subTest(verdict=verdict):
                self.assertIsNone(
                    next((v for v in R.TO_OPTION_VERDICTS if v in verdict), None))


if __name__ == "__main__":
    unittest.main()
