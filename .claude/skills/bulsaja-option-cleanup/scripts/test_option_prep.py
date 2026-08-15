#!/usr/bin/env python3
"""팬아웃 인프라(2026-08-01) 회귀 테스트 — index 신형식·imgs 산정·pending·감사·조인.

워커가 상품을 빠뜨리면 조용히 사라지던 결함(_plans 가 expected 대조 없이 concat)의
방어선을 검증한다. cmd_prep 전체가 아니라 순수 계산부만 tmpdir 로 잰다.

    python .claude/skills/bulsaja-option-cleanup/scripts/test_option_prep.py
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import run_options                      # noqa: E402 — import 시 eroomlib 경로를 잡아준다
from eroomlib import snapshot           # noqa: E402


def _prod(pid, rep="D:/rep.jpg", opt_imgs=2):
    return {"productId": pid, "대표썸네일": rep,
            "차원": [{"index": 0, "이름": "색", "원문이름": "颜色",
                    "values": [{"vid": i, "이미지": f"D:/{pid}_{i}.jpg" if i < opt_imgs
                                else ""} for i in range(3)]}],
            "판매행": [{"id": f"{pid}-r{i}"} for i in range(4)]}


class BatchImgsTest(unittest.TestCase):

    def test_대표와_경로가_찬_옵션값만_센다(self):
        # 대표 1 + 옵션값 2(빈 경로 1개 제외) = 3, 두 상품이면 6
        self.assertEqual(run_options._batch_imgs([_prod("A"), _prod("B")]), 6)

    def test_대표가_비면_옵션값만(self):
        self.assertEqual(run_options._batch_imgs([_prod("A", rep="")]), 2)


class PendingTest(unittest.TestCase):

    def setUp(self):
        self.run_dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.run_dir, "batches"))
        os.makedirs(os.path.join(self.run_dir, "results"))

    def tearDown(self):
        shutil.rmtree(self.run_dir, ignore_errors=True)

    def _w(self, *parts_and_obj):
        *parts, obj = parts_and_obj
        with open(os.path.join(self.run_dir, *parts), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)

    def test_결과가_없는_배치만_남는다(self):
        self._w("batches_index.json", [
            {"n": 1, "path": "p1", "imgs": 3, "count": 5},
            {"n": 2, "path": "p2", "imgs": 4, "count": 5}])
        self._w("results", "result_001.json", {"배치": 1, "products": []})
        pend = run_options._pending_batches(self.run_dir)
        self.assertEqual([b["n"] for b in pend], [2])

    def test_구형_index는_배치_파일에서_재계산한다(self):
        self._w("batches", "batch_001.json",
                {"배치": 1, "products": [_prod("A")]})
        self._w("batches_index.json",
                [{"batch": "batch_001.json", "상품수": 1, "옵션수": 4}])
        pend = run_options._pending_batches(self.run_dir)
        self.assertEqual(len(pend), 1)
        self.assertEqual(pend[0]["n"], 1)
        self.assertEqual(pend[0]["imgs"], 3)
        self.assertTrue(os.path.isabs(pend[0]["path"]))

    def test_index가_없으면_빈_배열(self):
        self.assertEqual(run_options._pending_batches(self.run_dir), [])

    def _pending_json(self):
        import argparse
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            run_options.cmd_pending(argparse.Namespace(run_dir=self.run_dir))
        return json.loads(buf.getvalue())

    def test_경로가_템플릿이면_compact_로_찍는다(self):
        """152배치에서 인라인 args 가 25KB 까지 부풀던 것을 없앤다 (2026-08-09)."""
        for n in (1, 2):
            self._w("batches", f"batch_{n:03d}.json",
                    {"배치": n, "products": [_prod("A")]})
        self._w("batches_index.json", [
            {"n": n,
             "path": os.path.join(self.run_dir, "batches", f"batch_{n:03d}.json"),
             "imgs": n + 2, "count": 5} for n in (1, 2)])
        out = self._pending_json()
        self.assertEqual(out["compact"], [[1, 3, 5], [2, 4, 5]])
        self.assertNotIn("batches", out)

    def test_경로가_템플릿과_다르면_완전형으로_떨어진다(self):
        self._w("batches_index.json", [{"n": 1, "path": "/어딘가/딴데.json",
                                        "imgs": 3, "count": 5}])
        out = self._pending_json()
        self.assertNotIn("compact", out)
        self.assertEqual(out["batches"][0]["path"], "/어딘가/딴데.json")


class AuditAndPlansTest(unittest.TestCase):

    def setUp(self):
        self.run_dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.run_dir, "batches"))
        os.makedirs(os.path.join(self.run_dir, "results"))
        self._w("batches", "batch_001.json", {"배치": 1, "products": [
            {"productId": "U01a"}, {"productId": "U01b"}]})
        self._orig_load = snapshot.load
        snapshot.load = lambda pid: None   # 스냅샷 없음 → 전부 보류로 흐른다(조인만 검증)

    def tearDown(self):
        snapshot.load = self._orig_load
        shutil.rmtree(self.run_dir, ignore_errors=True)

    def _w(self, *parts_and_obj):
        *parts, obj = parts_and_obj
        with open(os.path.join(self.run_dir, *parts), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)

    def test_누락이_있으면_missing_참(self):
        self._w("results", "result_001.json", {"배치": 1, "products": [
            {"productId": "U01a"}]})
        warns, missing = run_options._audit_results(self.run_dir)
        self.assertTrue(missing)
        self.assertTrue(any("U01b" in w for w in warns))

    def test_환각_pid는_경고하고_plans에서_버린다(self):
        self._w("results", "result_001.json", {"배치": 1, "products": [
            {"productId": "U01a"}, {"productId": "U01b"},
            {"productId": "U01ghost"}]})
        warns, missing = run_options._audit_results(self.run_dir)
        self.assertFalse(missing)
        self.assertTrue(any("U01ghost" in w for w in warns))
        pids = [pid for pid, _, _ in run_options._plans(self.run_dir)]
        self.assertEqual(sorted(pids), ["U01a", "U01b"])

    def test_같은_pid는_마지막_파일이_이긴다(self):
        self._w("results", "result_001.json", {"배치": 1, "products": [
            {"productId": "U01a", "메모": "옛것"}, {"productId": "U01b"}]})
        self._w("results", "result_002.json", {"배치": 2, "products": [
            {"productId": "U01a", "메모": "새것"}]})
        rows = {pid: w for pid, _, w in run_options._plans(self.run_dir)}
        self.assertEqual(rows["U01a"]["메모"], "새것")
        self.assertEqual(len(rows), 2, "중복이 두 행으로 불어나면 안 된다")

    def test_마커수동은_폐지됐다(self):
        # 제품유형 32 × 전력 1 모양이면 예전엔 '보류(기본형 수동판단)' 으로 멈췄다.
        # 규칙 17이 확정되면서(값 2개 이상인 마지막 차원에 붙인다) 오염이 사라져 폐지됐다.
        # **옛 run-dir 의 계획에 이 키가 남아 있어도 무시해야 한다** — 안 그러면 이미
        # 해소된 건이 영영 보류로 남는다(용쌤1-1 에서 75건이 그랬다).
        self.assertEqual(
            run_options._status_of({"대표": "1", "이름검사": {}, "마커수동": True}, {}),
            "정리대상")
        self.assertEqual(
            run_options._status_of({"대표": "1", "이름검사": {}}, {}),
            "정리대상")

    def test_배치_정본이_없는_구형_run_dir은_대조를_생략한다(self):
        shutil.rmtree(os.path.join(self.run_dir, "batches"))
        self._w("results", "result_001.json", {"products": [
            {"productId": "U01legacy"}]})
        warns, missing = run_options._audit_results(self.run_dir)
        self.assertEqual((warns, missing), ([], False))
        pids = [pid for pid, _, _ in run_options._plans(self.run_dir)]
        self.assertEqual(pids, ["U01legacy"])


class ItemMismatchTest(unittest.TestCase):
    """품목대조 — 상품명과 메인상품이 한 낱말도 안 겹치면 신호 (2026-08-10).

    실사례는 전부 용쌤2-1(2026-08-09)에서 워커가 놓치고 사람이 손으로 찾아낸 건들이다.
    """

    def test_딴_품목이면_잡는다(self):
        for 상품명, 메인 in [
            ("평판프레스 인쇄기 핸드 소형 기계 티셔츠프린팅기계", "304E/304H 퀵클램프 지그"),
            ("매장용 회전간판 큐브모형 식당 간판 입간판", "LED 크리스탈 메뉴 라이트박스"),
            ("구멍파기 갯벌삽 파이프 농기구 관통삽 말뚝", "절연 뤄양삽(탐침삽)"),
            ("원예 조경 전기톱 자르기 나뭇가지 조경톱", "전동 헤지트리머"),
            ("음식물 수거대 짬 잔반처리대 업소용 주방", "스테인리스 개수대 캐비닛"),
        ]:
            self.assertTrue(run_options._item_mismatch(상품명, 메인), 상품명)

    def test_같은_품목이면_안_잡는다(self):
        for 상품명, 메인 in [
            ("3단 스텐 서빙카트 업소용 퇴식카트", "스테인리스 퇴식카트(3층)"),
            ("정원 인조잔디2m 테라스 베란다인조잔디", "인조잔디 롤(폭·길이별)"),
            ("접이식 플라스틱2단서랍장 수납 다용도", "플라스틱 접이식 수납 서랍장"),
        ]:
            self.assertFalse(run_options._item_mismatch(상품명, 메인), 상품명)

    def test_수식어만_겹치는_건_근거가_아니다(self):
        """`업소용`·`이동식` 같은 말은 어느 상품명에나 붙어 겹쳐도 뜻이 없다."""
        self.assertTrue(run_options._item_mismatch(
            "업소용 이동식 하이볼기계 칵테일", "업소용 이동식 와인 디스펜서 랙"))

    def test_한쪽이_비면_신호를_내지_않는다(self):
        self.assertFalse(run_options._item_mismatch("", "무엇이든"))
        self.assertFalse(run_options._item_mismatch("무엇이든", ""))

    def test_신호가_상품명_이관으로_나간다(self):
        run_dir = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(run_dir, "batches"))
            os.makedirs(os.path.join(run_dir, "results"))
            for name, obj in (
                ("batches/batch_001.json",
                 {"배치": 1, "products": [{"productId": "U01x"}]}),
                ("results/result_001.json",
                 {"배치": 1, "products": [{"productId": "U01x",
                                         "상품명": "매장용 회전간판 큐브모형 입간판",
                                         "메인상품": "LED 크리스탈 메뉴 라이트박스"}]}),
            ):
                with open(os.path.join(run_dir, *name.split("/")), "w",
                          encoding="utf-8") as f:
                    json.dump(obj, f, ensure_ascii=False)
            orig = snapshot.load
            snapshot.load = lambda pid: None      # 스냅샷 없음 → 보류로 흐른다
            try:
                (_pid, _plan, w), = run_options._plans(run_dir)
            finally:
                snapshot.load = orig
            self.assertTrue(w["품목대조"])
            self.assertEqual([h["단계"] for h in w["이관"]], ["상품명"])
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)


class TruncatedPidTest(unittest.TestCase):
    """워커가 27자 상품id를 잘라 반환한 건을 접두사로 되살린다 (2026-08-09 용쌤2-1 6건).

    환각과 절단은 다르다 — 절단은 정본의 접두사라 되살릴 근거가 있다. 그때는 감사가
    둘을 구분하지 못하고 `미지의 상품id` 로 버려 상품이 통째로 유실됐다.
    """

    A = "U01KREA81YHN1V3SD217VVMTSHV"
    B = "U01KREA821ZC89N4MXM18WKTWYQ"

    def setUp(self):
        self.run_dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.run_dir, "batches"))
        os.makedirs(os.path.join(self.run_dir, "results"))
        self._w("batches", "batch_001.json", {"배치": 1, "products": [
            {"productId": self.A}, {"productId": self.B}]})
        self._orig_load = snapshot.load
        snapshot.load = lambda pid: None

    def tearDown(self):
        snapshot.load = self._orig_load
        shutil.rmtree(self.run_dir, ignore_errors=True)

    def _w(self, *parts_and_obj):
        *parts, obj = parts_and_obj
        with open(os.path.join(self.run_dir, *parts), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)

    def test_잘린_id를_되살리고_경고한다(self):
        self._w("results", "result_001.json", {"배치": 1, "products": [
            {"productId": self.A[:18], "메모": "잘림"}, {"productId": self.B}]})
        warns, missing = run_options._audit_results(self.run_dir)
        self.assertFalse(missing, "되살렸으면 누락이 아니다")
        self.assertTrue(any("잘린 상품id" in w for w in warns))
        pids = [pid for pid, _, _ in run_options._plans(self.run_dir)]
        self.assertEqual(sorted(pids), sorted([self.A, self.B]))

    def test_되살린_id가_계획에도_실린다(self):
        self._w("results", "result_001.json", {"배치": 1, "products": [
            {"productId": self.A[:18], "메모": "잘림"}]})
        rows = {pid: w for pid, _, w in run_options._plans(self.run_dir)}
        self.assertEqual(rows[self.A]["productId"], self.A,
                         "계획 안의 productId 도 온전해야 저장 경로가 옳은 상품을 친다")

    def test_접두사가_여럿이면_손대지_않는다(self):
        """추정으로 엉뚱한 상품을 고치느니 환각으로 버리는 게 낫다."""
        twin = self.A[:20] + "XXXXXXX"
        self.assertEqual(len(twin), len(self.A))
        self.assertEqual(run_options._repair_pid(self.A[:18], {self.A, twin}),
                         self.A[:18])

    def test_짧은_id는_접두사_복원을_시도하지_않는다(self):
        self.assertEqual(run_options._repair_pid("U01K", {self.A, self.B}), "U01K")


class ThumbPreferTest(unittest.TestCase):
    """대표썸네일과 **바이트가 같은** 옵션 = 동률 자동 해소 (2026-08-06 이룸님).

    비용 0이다 — prep 이 대표썸네일·옵션 이미지를 이미 받아 뒀다. 3-1 w1 실측:
    `확인요` 5건 중 2건이 이 대조만으로 끝났다(승마가방·미끄럼틀).
    """

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self._w("rep.jpg", b"THUMB")      # 대표썸네일
        self._w("v1.jpg", b"other")
        self._w("v2.jpg", b"THUMB")       # ← 대표썸네일과 동일
        self.bp = {"대표썸네일": os.path.join(self.d, "rep.jpg"),
                   "차원": [{"index": 0, "values": [
                       {"vid": 1, "이미지": os.path.join(self.d, "v1.jpg")},
                       {"vid": 2, "이미지": os.path.join(self.d, "v2.jpg")}]}]}

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def _w(self, name, data):
        with open(os.path.join(self.d, name), "wb") as f:
            f.write(data)

    @staticmethod
    def _opt(p1, p2):
        return {"판매행": [
            {"id": "1", "sale_price": p1, "stock": 9, "exclude": False},
            {"id": "2", "sale_price": p2, "stock": 9, "exclude": False}]}

    def test_동률이면_썸네일과_같은_파일을_고른다(self):
        got = run_options._thumb_prefer_id(self.bp, self._opt(1000, 1000), ["1", "2"])
        self.assertEqual(got, "2")

    def test_동률군_밖이면_지목하지_않는다(self):
        # 더 비싼 걸 지목하면 plan 이 무시하면서 경고를 하나 더 단다 → 오히려 확인요가 된다
        got = run_options._thumb_prefer_id(self.bp, self._opt(1000, 2000), ["1", "2"])
        self.assertEqual(got, "")

    def test_일치가_없으면_빈값(self):
        self._w("v2.jpg", b"nope")
        got = run_options._thumb_prefer_id(self.bp, self._opt(1000, 1000), ["1", "2"])
        self.assertEqual(got, "")

    def test_유지에_없는_행은_후보가_아니다(self):
        got = run_options._thumb_prefer_id(self.bp, self._opt(1000, 1000), ["1"])
        self.assertEqual(got, "")

    def test_복합옵션은_해당_차원_조각만_본다(self):
        bp = {"대표썸네일": os.path.join(self.d, "rep.jpg"),
              "차원": [{"index": 1, "values": [
                  {"vid": 7, "이미지": os.path.join(self.d, "v2.jpg")}]}]}
        opt = {"판매행": [
            {"id": "1:3", "sale_price": 1000, "stock": 9, "exclude": False},
            {"id": "1:7", "sale_price": 1000, "stock": 9, "exclude": False}]}
        self.assertEqual(run_options._thumb_prefer_id(bp, opt, ["1:3", "1:7"]), "1:7")

    def test_대표썸네일이_없으면_조용히_넘어간다(self):
        self.assertEqual(run_options._thumb_prefer_id({}, self._opt(1000, 1000), ["1"]), "")


class PartialSaveTest(unittest.TestCase):
    """`보류(기본형)` 부분저장 (2026-08-06 이룸님).

    발단: 3-1 워터건 — 워커가 뒤집힘(본품 19행 제외·부속 예비배터리 1행만 판매·대표)을
    정확히 복구했는데 대표옵션 이름에 `기본형` 이 없다는 이유로 **저장이 통째로** 막혀,
    스마트스토어에 배터리만 팔리는 채로 남아 있었다(w1 69건 중 12건이 이렇게 빠졌다).
    """

    @staticmethod
    def _row(status):
        return ("U01x", {"대표": "1"}, {"이름": {"1": "블랙"}}, status)

    def test_기본형_보류도_저장_대상이다(self):
        rows = [self._row("보류(기본형)")]
        self.assertEqual([r[0] for r in run_options._commit_targets(rows)], ["U01x"])

    def test_정리대상과_함께_고른다(self):
        rows = [self._row("정리대상"), self._row("보류(기본형)")]
        self.assertEqual(len(run_options._commit_targets(rows)), 2)

    def test_무엇을_팔지가_안_정해진_보류는_저장하지_않는다(self):
        for st in ("보류(대표충돌)", "보류(남길 옵션 없음)", "보류(이름규칙)",
                   "확인요", "보류(스냅샷 없음)"):
            with self.subTest(st=st):
                self.assertEqual(run_options._commit_targets([self._row(st)]), [])

    def test_최저가_동률_경고는_저장을_막지_않는다(self):
        """2026-08-07 이룸님 — 대표는 원본 순서여도 되고, 썸네일만 대표옵션과 맞으면 된다.

        `경고가 하나라도 있으면 확인요` 가 너무 뭉툭해서 3-2 에서 4건이 사람 큐에 쌓였다.
        규칙이 이미 답을 내는 상황(동률→원본 순서)은 저장하고 썸네일로 넘긴다.
        """
        plan = {"대표": "r1", "경고": ["최저가 동률 14건 — 썸네일 최유사 판단 없이 원본 순서로 정했다"]}
        self.assertEqual(run_options._status_of(plan, {}), "정리대상")

    def test_그_밖의_경고는_종전대로_확인요(self):
        plan = {"대표": "r1", "경고": ["뭔가 다른 경고"]}
        self.assertEqual(run_options._status_of(plan, {}), "확인요")

    def test_동률과_다른_경고가_같이_있으면_확인요(self):
        """비차단 경고가 차단 경고를 덮어 통과시키면 안 된다."""
        plan = {"대표": "r1", "경고": ["최저가 동률 2건 — …", "뭔가 다른 경고"]}
        self.assertEqual(run_options._status_of(plan, {}), "확인요")

    def test_부분저장은_옵션명을_보내지_않는다(self):
        before = {"차원": [{"index": 0, "values": [{"vid": 1, "name": "A. 블랙"}]}]}
        self.assertEqual(run_options._names_to_save({"이름": {"1": "블랙"}}, before, True), {})

    def test_정상저장은_이름을_그대로_보낸다(self):
        before = {"차원": [{"index": 0, "values": [{"vid": 1, "name": "A. 블랙"}]}]}
        got = run_options._names_to_save({"이름": {"1": "블랙 기본형"}}, before, False)
        self.assertEqual(got.get("1"), "블랙 기본형")

    def test_부분저장_표시는_재작업이라_다음_회차가_집는다(self):
        from eroomlib import matrix
        v = matrix.redo_value(run_options.PARTIAL_REASON, from_task=run_options.TASK)
        self.assertTrue(matrix.is_redo(v))
        # 현황판 값이 재작업이면 pending 이 다시 골라낸다(보류였다면 영영 안 잡힌다)
        self.assertEqual(matrix.pending({"U01x": {"옵션": v}}, "옵션"), ["U01x"])


class HandoffTest(unittest.TestCase):
    """이관 — 상품명은 저장 여부와 무관하게 넘어간다 (2026-08-06 이룸님).

    발단: 상품명 이상이 가장 잘 보이는 자리가 `보류(대표충돌)`(상품명이 규격어로 지정한
    대표를 워커가 본품이 아니라고 뺀 상태)인데, `_handoff` 가 저장 성공분만 넘겨
    그 신호를 통째로 버리고 있었다.
    """

    def setUp(self):
        self.calls = []
        self._orig = run_options.matrix.flag_many
        run_options.matrix.flag_many = self._flag

    def tearDown(self):
        run_options.matrix.flag_many = self._orig

    def _flag(self, sheet, task, items, from_task=None, **kw):
        self.calls.append((task, dict(items), from_task))
        return len(items)

    @staticmethod
    def _row(pid, status, handoffs):
        return (pid, {"대표": "1"}, {"이관": handoffs}, status)

    def test_보류건도_상품명_이관은_넘어간다(self):
        rows = [self._row("P1", "보류(대표충돌)",
                          [{"단계": "상품명", "사유": "규격어 '3단'이 옵션에 없다"}])]
        run_options._handoff("SHEET", rows, {}, {})       # done 이 비어 있다
        self.assertEqual(len(self.calls), 1)
        task, items, from_task = self.calls[0]
        self.assertEqual((task, from_task), ("상품명", "옵션"))
        self.assertIn("3단", items["P1"])

    def test_보류건의_썸네일_이관은_넘기지_않는다(self):
        # 대표가 확정돼야 대조 대상이 생긴다 — 저장 못 한 건은 넘길 근거가 없다
        rows = [self._row("P1", "보류(대표충돌)",
                          [{"단계": "썸네일", "사유": "대표색 불일치"}])]
        run_options._handoff("SHEET", rows, {}, {})
        self.assertEqual(self.calls, [])

    def test_저장된_건은_종전대로_전부_넘어간다(self):
        rows = [self._row("P1", "정리대상",
                          [{"단계": "썸네일", "사유": "x"}, {"단계": "상품명", "사유": "y"}])]
        run_options._handoff("SHEET", rows, {"P1": "완료"}, {})
        self.assertEqual(sorted(c[0] for c in self.calls), ["상품명", "썸네일"])


class RoundtripCloseTest(unittest.TestCase):
    """옵션↔썸네일 왕복 종결 — 2회차부터는 `실물기준없음` 을 코드가 붙인다.

    2026-08-15 용쌤2-1 §9: 옵션 57건을 고쳐 31건을 썸네일로 돌려보냈는데 2회전에서
    `대표옵션의심` 8건 · `기준이미지없음` 1건이 또 나왔다. 끊는 낱말은 이미 있고
    워커 프롬프트도 그걸 넣으라고 시키는데 **워커가 안 붙였다**.
    """

    def setUp(self):
        self.calls = []
        self.run_dir = tempfile.mkdtemp()
        self._orig = run_options.matrix.flag_many
        run_options.matrix.flag_many = (
            lambda sheet, task, items, from_task=None, **kw:
            (self.calls.append((task, dict(items))), len(items))[1])

    def tearDown(self):
        run_options.matrix.flag_many = self._orig
        shutil.rmtree(self.run_dir, ignore_errors=True)

    def _batch(self, redo_reason):
        """배치에 `재작업사유`(썸네일이 되돌리며 남긴 값)를 실어둔다."""
        os.makedirs(os.path.join(self.run_dir, "batches"), exist_ok=True)
        with open(os.path.join(self.run_dir, "batches", "batch_001.json"),
                  "w", encoding="utf-8") as f:
            json.dump({"products": [{"productId": "P1", "재작업사유": redo_reason}]},
                      f, ensure_ascii=False)

    def _run(self, redo_reason, handoff_reason):
        self._batch(redo_reason)
        rows = [("P1", {"대표": "1"},
                 {"이관": [{"단계": "썸네일", "사유": handoff_reason}]}, "정리대상")]
        run_options._handoff("SHEET", rows, {"P1": "완료"}, {}, self.run_dir)
        return self.calls[0][1]["P1"] if self.calls else None

    def test_썸네일이_되돌린_건이면_실물기준없음을_붙인다(self):
        for mark in run_options.FROM_THUMB_MARKS:
            with self.subTest(mark=mark):
                self.calls.clear()
                got = self._run(f"[썸네일] {mark}: 대표옵션이 배너다", "대표를 새로 세웠다")
                self.assertTrue(got.startswith(run_options.NO_REAL_BASE), got)
                self.assertIn("대표를 새로 세웠다", got, "원래 사유가 사라졌다")

    def test_워커가_이미_붙였으면_두_번_안_붙인다(self):
        got = self._run("[썸네일] 기준이미지없음",
                        f"{run_options.NO_REAL_BASE}: 옵션 이미지가 전부 도면")
        self.assertEqual(got.count(run_options.NO_REAL_BASE), 1)

    def test_첫_이관에는_붙이지_않는다(self):
        """옵션이 처음 보내는 건은 대표를 새로 세운 것뿐 — 왕복이 아니다."""
        got = self._run("", "대표 동률로 원본 순서 지정")
        self.assertEqual(got, "대표 동률로 원본 순서 지정")

    def test_썸네일발이_아닌_재작업사유에는_붙이지_않는다(self):
        got = self._run("[상품명] 규격어 누락", "대표색 불일치")
        self.assertEqual(got, "대표색 불일치")

    def test_run_dir_이_없으면_종전대로_동작한다(self):
        rows = [("P1", {"대표": "1"},
                 {"이관": [{"단계": "썸네일", "사유": "대표색 불일치"}]}, "정리대상")]
        run_options._handoff("SHEET", rows, {"P1": "완료"}, {})
        self.assertEqual(self.calls[0][1]["P1"], "대표색 불일치")


class DeletionCandidateTest(unittest.TestCase):
    """`삭제후보` — 상품명과 옵션 실물이 아예 다른 품목 (2026-08-06 이룸님)."""

    def test_삭제후보면_상태가_삭제대상이다(self):
        st = run_options._status_of({"대표": "1"}, {"삭제후보": "상품명은 청소기, 옵션은 깔창"})
        self.assertEqual(st, "보류(삭제대상)")

    def test_계획이_멀쩡해도_삭제후보가_이긴다(self):
        # 옵션을 정리해 봐야 팔 수 없는 물건이다 — 저장 대상에서 뺀다
        plan = {"대표": "1", "이름검사": {}, "경고": []}
        self.assertEqual(run_options._status_of(plan, {"삭제후보": "품목 불일치"}),
                         "보류(삭제대상)")
        self.assertEqual(run_options._commit_targets(
            [("P1", plan, {"삭제후보": "x"}, "보류(삭제대상)")]), [])

    def test_빈_삭제후보는_무시한다(self):
        plan = {"대표": "1", "이름검사": {}, "경고": []}
        self.assertEqual(run_options._status_of(plan, {"삭제후보": "  "}), "정리대상")


class PrepCarriesRedoReasonTest(unittest.TestCase):
    """배치에 `재작업사유` 를 실어야 워커가 §2-10(대표옵션 이미지 실물 확인)을 켠다.

    안 실어 보내면 워커는 그 상품이 **썸네일에서 되돌아온 건**이라는 걸 모른다 —
    옵션명만 보고 대표를 다시 세우고, 그 이미지가 또 도면이면 썸네일이 또 되돌린다.
    옵션명으로는 알 수 없다(2026-08-07 실측: `1m 원목벤치 월넛 기본형`=도면 vs
    `브러시 단일노즐 기본형`=실물 — 이름만으로는 전혀 구분되지 않았다).
    """

    REASON = "썸네일: 대표옵션 이미지가 비제품(도면·배너)"

    def setUp(self):
        import argparse
        from eroomlib import matrix
        self.argparse = argparse
        self.matrix = matrix
        self.run_dir = tempfile.mkdtemp()
        self._orig = {"read": matrix.read, "redo_pending": matrix.redo_pending,
                      "pending": matrix.pending, "mark_many": matrix.mark_many,
                      "ensure": snapshot.ensure}
        matrix.read = lambda sheet: {"U01x": {}}
        matrix.pending = lambda m, task, **kw: ["U01x"]
        matrix.mark_many = lambda sheet, task, d, matrix=None: len(d)
        snapshot.ensure = lambda pids, **kw: ({pid: {
            "상품명": "장대톱", "원문명": "高空锯", "기존카테고리": "공구",
            "썸네일": ["https://img.alicdn.com/rep.jpg"],
            "옵션": {"차원": [], "vid고유": True, "판매행": [
                {"id": "1", "text": "기본형", "sale_price": 1000, "stock": 3,
                 "exclude": False, "main_product": True, "urlRef": "https://a/m.jpg"}]},
        } for pid in pids}, {})

    def tearDown(self):
        for k, v in self._orig.items():
            setattr(self.matrix if k != "ensure" else snapshot, k, v)
        shutil.rmtree(self.run_dir, ignore_errors=True)

    def _batch_product(self, redo):
        self.matrix.redo_pending = lambda m, task: redo
        run_options.cmd_prep(self.argparse.Namespace(
            run_dir=self.run_dir, sheet="SHEET", group_name=None, ids=None,
            limit=0, batch_size=10, sleep=0, skip_thumbs=True,
            max_option_images=12, max_px=512))
        with open(os.path.join(self.run_dir, "batches", "batch_001.json"),
                  encoding="utf-8") as f:
            return json.load(f)["products"][0]

    def test_이관_사유가_배치에_실린다(self):
        p = self._batch_product({"U01x": self.REASON})
        self.assertEqual(p["재작업사유"], self.REASON)

    def test_재작업이_아니면_빈_문자열이다(self):
        p = self._batch_product({})
        self.assertEqual(p["재작업사유"], "")


class CommitResumeAndMatrixTest(unittest.TestCase):
    """`--no-sheet` 가 현황판을 막던 것 + `committed.json` 재개 (2026-08-14).

    발단(2-2): 저장 회차를 `--no-sheet` 로 돌렸더니 옵션 664건이 다 저장됐는데
    `00_진행` 은 `재작업` 그대로였고 이관도 안 나갔다 — 다음 회차가 같은 726건을
    통째로 다시 집는다. 게다가 SKILL.md 에 있다던 `committed.json` 재개가 코드에
    없어서, 현황판을 채우려고 한 번 더 치자 700건을 처음부터 다시 저장했다(1시간).
    """

    def setUp(self):
        from eroomlib import matrix
        self.matrix = matrix
        self.run_dir = tempfile.mkdtemp()
        self.marks, self.handoffs, self.logged = [], [], []
        self._orig = {
            "read": matrix.read, "mark_many": matrix.mark_many,
            "load": snapshot.load,
            "_log_sheet": run_options._log_sheet,
            "_log_axis_sheet": run_options._log_axis_sheet,
            "_handoff": run_options._handoff,
            "OptionMCP": run_options.OptionMCP,
        }
        self._orig_verify = run_options.R.verify
        matrix.read = lambda sheet: {}
        matrix.mark_many = lambda sheet, task, d, matrix=None: (
            self.marks.append(dict(d)) or len(d))
        snapshot.load = lambda pid: {"옵션": {"판매행": [{"id": "1"}]}}
        run_options._log_sheet = lambda *a, **k: self.logged.append("원장")
        run_options._log_axis_sheet = lambda *a, **k: self.logged.append("축")
        run_options._handoff = (lambda sheet, rows, done, m, run_dir="":
                                self.handoffs.append(dict(done)))

    def tearDown(self):
        for k, v in self._orig.items():
            setattr(self.matrix if k in ("read", "mark_many") else
                    (snapshot if k == "load" else run_options), k, v)
        # **`run_options.R` 은 option_rules 모듈 그 자체다** — `_run` 이 거기에 꽂은
        # `verify` 스텁을 안 되돌리면 프로세스 전역으로 남는다. 실제로 discover 실행에서
        # 뒤에 오는 test_option_rules 의 검증 테스트 8개가 통째로 무력화돼 있었다
        # (혼자 돌리면 통과, 전체로 돌리면 실패 — 반대로 착각하기 쉬운 형태다).
        run_options.R.verify = self._orig_verify
        shutil.rmtree(self.run_dir, ignore_errors=True)

    def _args(self, **kw):
        import argparse
        base = dict(run_dir=self.run_dir, commit=True, sleep=0,
                    no_sheet=False, no_matrix=False, ignore_committed=False)
        base.update(kw)
        return argparse.Namespace(**base)

    @staticmethod
    def _rows(pids):
        return [(p, {"대표": "1", "유지": ["1"], "제외": [], "순서": ["1"]},
                 {"이름": {}}, "정리대상") for p in pids]

    def _fake_mcp(self, ok=True):
        outer = self

        class _M:
            def open(self): pass

            def close(self): pass

            def option_update(self, pid, **kw):
                outer.saved.append(pid)
                if not ok:
                    raise RuntimeError("저장 거부")

            def workdata(self, pid):
                return {"옵션": {"판매행": [{"id": "1"}]}}
        return _M

    def _run(self, pids, **kw):
        self.saved = []
        run_options.OptionMCP = self._fake_mcp()
        run_options.R.verify = lambda *a, **k: []
        run_options.snapshot.update = lambda pid, **k: None
        run_options._commit("SHEET", self._rows(pids), self._args(**kw))

    def test_no_sheet_여도_현황판과_이관은_나간다(self):
        self._run(["P1", "P2"], no_sheet=True)
        self.assertEqual(len(self.marks), 1)
        self.assertEqual(set(self.marks[0]), {"P1", "P2"})
        self.assertEqual(self.handoffs, [{"P1": "완료", "P2": "완료"}])

    def test_no_matrix_라야_현황판이_막힌다(self):
        self._run(["P1"], no_matrix=True)
        self.assertEqual(self.marks, [])
        self.assertEqual(self.handoffs, [])

    def test_저장된_건은_committed에_즉시_쌓인다(self):
        self._run(["P1", "P2"])
        with open(os.path.join(self.run_dir, "committed.json"), encoding="utf-8") as f:
            self.assertEqual(set(json.load(f)), {"P1", "P2"})

    def test_재실행은_MCP를_다시_치지_않는다(self):
        self._run(["P1", "P2"])
        self._run(["P1", "P2"])          # 두 번째 회차 — 전건 재개 대상
        self.assertEqual(self.saved, [])

    def test_재개_회차도_현황판을_채운다(self):
        """이 재개 기능을 만든 이유 그 자체 — 저장은 끝났는데 현황판이 빈 상태를 고친다."""
        self._run(["P1", "P2"], no_matrix=True)   # 1회차: 저장만, 현황판 안 씀
        self.assertEqual(self.marks, [])
        self._run(["P1", "P2"])                   # 2회차: MCP 0회 + 현황판만
        self.assertEqual(self.saved, [])
        self.assertEqual(set(self.marks[-1]), {"P1", "P2"})
        self.assertEqual(self.handoffs[-1], {"P1": "완료", "P2": "완료"})

    def test_ignore_committed면_다시_저장한다(self):
        self._run(["P1"])
        self._run(["P1"], ignore_committed=True)
        self.assertEqual(self.saved, ["P1"])

    def test_실패해도_스냅샷을_실제상태로_되맞춘다(self):
        """저장 2단계 중 ①만 넘어가고 죽으면 불사자에는 새 이름이, 스냅샷엔 옛 이름이 남는다.

        그대로 두면 다음 회차 prep 이 낡은 상태로 계획을 세워 같은 상품이 매 회차 같은
        사유로 실패한다(2-2 실측: 1회차 마커 실패 9건 → 2회차 같은 사유 4건 재발).
        """
        updated = {}
        orig_update = run_options.snapshot.update
        run_options.snapshot.update = lambda pid, **kw: updated.__setitem__(pid, kw)
        try:
            self.saved = []
            run_options.OptionMCP = self._fake_mcp(ok=False)   # 저장이 죽는다
            run_options._commit("SHEET", self._rows(["P1"]), self._args())
        finally:
            run_options.snapshot.update = orig_update
        # 실패했어도 실제 상태(workdata)로 스냅샷이 되맞춰져야 한다
        self.assertIn("P1", updated)
        self.assertEqual(updated["P1"]["옵션"], {"판매행": [{"id": "1"}]})

    def test_실패건은_committed에_안_들어간다(self):
        self.saved = []
        run_options.OptionMCP = self._fake_mcp(ok=False)
        run_options._commit("SHEET", self._rows(["P1"]), self._args())
        p = os.path.join(self.run_dir, "committed.json")
        self.assertTrue(not os.path.exists(p) or json.load(open(p)) == {})

    def test_재개_회차가_원본백업을_덮지_않는다(self):
        """`before_commit.json` 은 유일한 되돌리기 경로다 — 남은 건만 담으면 안 된다."""
        self._run(["P1", "P2"])
        # P3 만 새로 도는 회차: 앞의 P1·P2 백업이 살아 있어야 restore 가 된다
        self._run(["P1", "P2", "P3"])
        with open(os.path.join(self.run_dir, "before_commit.json"), encoding="utf-8") as f:
            self.assertEqual(set(json.load(f)), {"P1", "P2", "P3"})


if __name__ == "__main__":
    unittest.main()
