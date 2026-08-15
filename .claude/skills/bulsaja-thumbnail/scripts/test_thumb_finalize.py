#!/usr/bin/env python3
"""2026-08-15 용쌤2-1 결함정리 회귀 테스트 — 종결·재판정·복구·기준출처.

인계문서(`00-inbox/2026-08-15-용쌤2-1-썸네일-완료.md`)의 §6·§7·§8 과
'광집게·크레인이 왜 어긋났나' 를 코드로 못박는다.

    python .claude/skills/bulsaja-thumbnail/scripts/test_thumb_finalize.py
"""
import argparse
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import run_thumbs                       # noqa: E402 — import 시 eroomlib 경로를 잡아준다
import thumb_rules as R                 # noqa: E402
from eroomlib import matrix, snapshot   # noqa: E402


class FakeMCP:
    """썸네일 배열을 메모리로만 들고 있는 가짜 불사자."""

    def __init__(self, thumbs):
        self.thumbs = {pid: list(v) for pid, v in thumbs.items()}

    def open(self):
        pass

    def close(self):
        pass

    def workdata(self, pid):
        return {"썸네일": list(self.thumbs.get(pid) or [])}

    def update_thumbnails(self, pid, thumbnails):
        self.thumbs[pid] = list(thumbnails)
        return {"success": True}


class _MCPPatch:
    """`ThumbMCP` 를 가짜로 바꾸고 시트 쓰기를 막는 공용 setUp/tearDown."""

    def _patch(self, thumbs):
        self.mcp = FakeMCP(thumbs)
        self._orig = {"ThumbMCP": run_thumbs.ThumbMCP,
                      "ensure": snapshot.ensure,
                      "update": snapshot.update,
                      "mark_many": matrix.mark_many,
                      "flag_many": matrix.flag_many,
                      "read": matrix.read,
                      "ensure_tab": run_thumbs.ensure_tab,
                      "append_rows": run_thumbs.append_rows,
                      "_log_sheet": run_thumbs._log_sheet}
        run_thumbs.ThumbMCP = lambda *a, **kw: self.mcp
        snapshot.update = lambda pid, **kw: None
        matrix.read = lambda sheet, tab=matrix.TAB: {}
        self.marked = {}
        matrix.mark_many = lambda sheet, task, vals, matrix=None: (
            self.marked.update(vals), len(vals))[1]
        matrix.flag_many = lambda sheet, task, vals, **kw: len(vals)
        run_thumbs.ensure_tab = lambda *a, **kw: False
        run_thumbs.append_rows = lambda *a, **kw: None
        run_thumbs._log_sheet = lambda sheet, rows: None

    def _unpatch(self):
        run_thumbs.ThumbMCP = self._orig["ThumbMCP"]
        snapshot.ensure = self._orig["ensure"]
        snapshot.update = self._orig["update"]
        matrix.mark_many = self._orig["mark_many"]
        matrix.flag_many = self._orig["flag_many"]
        matrix.read = self._orig["read"]
        run_thumbs.ensure_tab = self._orig["ensure_tab"]
        run_thumbs.append_rows = self._orig["append_rows"]
        run_thumbs._log_sheet = self._orig["_log_sheet"]


class FallbackFinalizeTest(_MCPPatch, unittest.TestCase):
    """§8 — `fallback` 뒤에 `apply --commit` 을 돌리면 원본대체가 되감기던 결함."""

    PID = "U01KREA81Z2DSF9BW8JXC237DKN"
    ORIG = "https://alicdn/main-option.jpg"
    GENERATED = "https://cdn.bulsaja.com/generated.jpg"

    def setUp(self):
        self.run_dir = tempfile.mkdtemp()
        self._patch({self.PID: ["https://cdn.bulsaja.com/old.jpg"]})
        # 대표옵션 원본이 있는 상품 — fallback 이 이걸 대표로 올린다
        snapshot.ensure = lambda pids, **kw: ({self.PID: {
            "상품명": "크레인 지지대",
            "옵션": {"판매행": [{"id": "1", "text": "기본", "main_product": True,
                              "urlRef": self.ORIG}]}}}, {})
        # 생성은 됐지만 3축 판정이 `제외` 로 떨어진 상태 = 판정 큐 '다시 해' 건
        self._dump("generated.json", {self.PID: {
            "상품명": "크레인 지지대", "생성본": self.GENERATED,
            "기존대표": "https://cdn.bulsaja.com/old.jpg", "후보": [], "크레딧": 5}})
        self._dump("decisions.json", {self.PID: {
            "판정": "제외", "사유": "재생성 2회 모두 불일치"}})

    def tearDown(self):
        self._unpatch()
        shutil.rmtree(self.run_dir, ignore_errors=True)

    def _dump(self, name, obj):
        with open(os.path.join(self.run_dir, name), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)

    def _read(self, name):
        with open(os.path.join(self.run_dir, name), encoding="utf-8") as f:
            return json.load(f)

    def _fallback(self, run_dir=None):
        args = argparse.Namespace(
            ids=[self.PID], run_dir=self.run_dir if run_dir is None else run_dir,
            sheet="SHEET", group_name=None, reason="", no_sheet=True, no_matrix=False)
        with contextlib.redirect_stdout(io.StringIO()) as out, \
                contextlib.redirect_stderr(io.StringIO()) as err:
            run_thumbs.cmd_fallback(args)
        return out.getvalue() + err.getvalue()

    def _commit(self):
        args = argparse.Namespace(run_dir=self.run_dir, sheet="SHEET",
                                  group_name=None, no_sheet=True, no_matrix=False,
                                  sleep=0)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            run_thumbs._commit("SHEET", self.run_dir, args)
        return out.getvalue()

    def test_fallback_이_decisions_에_원본대체를_남긴다(self):
        self._fallback()
        self.assertEqual(self._read("decisions.json")[self.PID]["판정"],
                         R.VERDICT_FALLBACK)
        self.assertEqual(self.mcp.thumbs[self.PID][0], self.ORIG)
        self.assertTrue(self.marked[self.PID].startswith("완료(원본대체"))

    def test_fallback_뒤_commit_이_원본대체를_되감지_않는다(self):
        """실측 사고 재현 — 완료가 658→628 로 떨어지고 에러도 경고도 없었다."""
        self._fallback()
        self.marked.clear()
        log = self._commit()
        # 현황판을 아예 안 건드려야 한다 — `보류(제외)` 로 되돌리면 그게 되감기다
        self.assertNotIn(self.PID, self.marked,
                         "commit 이 fallback 종결건의 현황판을 되썼다(되감기)")
        self.assertIn("fallback 종결 1건 건너뜀", log)
        # 불사자 대표도 그대로 원본이어야 한다
        self.assertEqual(self.mcp.thumbs[self.PID][0], self.ORIG)

    def test_commit_뒤_fallback_은_종전대로_동작한다(self):
        """권장 순서(커밋 → fallback)도 깨지지 않았는지."""
        self._commit()                       # 판정이 `제외` 라 보류로 기록
        self.assertEqual(self.marked[self.PID], "보류(제외)")
        self._fallback()
        self.assertTrue(self.marked[self.PID].startswith("완료(원본대체"))
        self.assertEqual(self.mcp.thumbs[self.PID][0], self.ORIG)

    def test_run_dir_없이_부르면_되감김_위험을_경고한다(self):
        log = self._fallback(run_dir="")
        self.assertIn("decisions.json 을 못 고쳤다", log)


class HealPidTest(unittest.TestCase):
    """§6 — 워커가 이미지 파일명에서 베낀 상품코드 복구(접미까지)."""

    FULL = "U01KSD7D7Y3338WQQKZWT0XTABC"          # 27자 정본
    VALID = {FULL, "U01KREA822Y4E8Q5MTHTA090839"}

    def test_정본은_그대로_둔다(self):
        self.assertIsNone(R.heal_pid(self.FULL, self.VALID))

    def test_잘리기만_한_것을_되살린다(self):
        self.assertEqual(R.heal_pid(self.FULL[:24], self.VALID), self.FULL)

    def test_파일명_접미까지_벤_것도_되살린다(self):
        """`_2`·`_9`·`_Y` — 2026-08-15 에 손으로 고쳤던 형태."""
        for suffix in ("_2", "_9", "_Y", "_10"):
            with self.subTest(suffix=suffix):
                self.assertEqual(R.heal_pid(self.FULL[:24] + suffix, self.VALID),
                                 self.FULL)

    def test_후보가_둘이면_고치지_않는다(self):
        """fail-closed — 남의 판정을 엉뚱한 상품에 붙이느니 버린다."""
        valid = {self.FULL, self.FULL[:24] + "ZZZ"}
        self.assertIsNone(R.heal_pid(self.FULL[:24], valid))
        self.assertIsNone(R.heal_pid(self.FULL[:24] + "_2", valid))

    def test_아예_모르는_id_는_None(self):
        self.assertIsNone(R.heal_pid("U01NOPE", self.VALID))
        self.assertIsNone(R.heal_pid("", self.VALID))

    def test_수합부가_접미까지_되살린다(self):
        """`_heal_pids` 가 새 규칙을 실제로 태우는지 — 결과 dict 를 직접 고친다."""
        products = [{"productId": self.FULL[:24] + "_2", "판정": "사용가능"}]
        with contextlib.redirect_stderr(io.StringIO()):
            healed = run_thumbs._heal_pids(products, self.VALID, "run")
        self.assertEqual(products[0]["productId"], self.FULL)
        self.assertEqual(len(healed), 1)


class VerdictIdsTest(_MCPPatch, unittest.TestCase):
    """§7 — `verdict --ids` 로 재생성분만 다시 판정한다."""

    A, B = "U01AAA", "U01BBB"

    def setUp(self):
        self.run_dir = tempfile.mkdtemp()
        self._orig_mat = snapshot.materialize_image
        snapshot.materialize_image = (
            lambda url, d, stem, i, **kw: (os.path.join(d, f"{stem}_{i}.jpg"), None))
        self._dump("generated.json", {
            self.A: {"상품명": "가", "생성본": "https://g/a.jpg", "기존대표": "https://c/a.jpg"},
            self.B: {"상품명": "나", "생성본": "https://g/b.jpg", "기존대표": "https://c/b.jpg"},
        })

    def tearDown(self):
        snapshot.materialize_image = self._orig_mat
        shutil.rmtree(self.run_dir, ignore_errors=True)

    def _dump(self, name, obj):
        path = os.path.join(self.run_dir, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)

    def _read(self, name):
        with open(os.path.join(self.run_dir, name), encoding="utf-8") as f:
            return json.load(f)

    def _verdict(self, ids=None, commit=False):
        args = argparse.Namespace(run_dir=self.run_dir, ids=ids, batch_size=10,
                                  commit=commit, max_px=0)
        with contextlib.redirect_stdout(io.StringIO()) as out, \
                contextlib.redirect_stderr(io.StringIO()) as err:
            run_thumbs.cmd_verdict(args)
        return out.getvalue() + err.getvalue()

    def _answer(self, n, answers):
        """워커 산출물(vresult) 을 흉내낸다."""
        self._dump(os.path.join("verdict", "results", f"vresult_{n:03d}.json"),
                   {"products": [{"productId": p, "판정": v, "사유": ""}
                                 for p, v in answers.items()]})

    def test_ids_는_그_상품만_배치에_싣는다(self):
        self._verdict(ids=[self.B])
        batch = self._read(os.path.join("verdict", "batches", "vbatch_001.json"))
        self.assertEqual([p["productId"] for p in batch["products"]], [self.B])

    def test_재판정이_다른_상품의_판정을_지우지_않는다(self):
        """예전엔 decisions.json 을 통째로 덮어써서, 안 지목한 건이 판정 없음
        (= apply --commit 에서 전부 '사용가능')으로 흘러갔다."""
        self._verdict()                                     # 1라운드: 전건
        self._answer(1, {self.A: "사용가능", self.B: "제외"})
        self._verdict(commit=True)
        self.assertEqual(set(self._read("decisions.json")), {self.A, self.B})

        self._verdict(ids=[self.B])                         # 2라운드: B 만 재판정
        self._answer(1, {self.B: "사용가능"})
        log = self._verdict(commit=True)
        dec = self._read("decisions.json")
        self.assertEqual(dec[self.A]["판정"], "사용가능", "A 의 판정이 사라졌다")
        self.assertEqual(dec[self.B]["판정"], "사용가능", "B 의 재판정이 안 들어갔다")
        self.assertIn("앞 라운드 판정 1건 유지", log)

    def test_앞_라운드_결과는_지우지_않고_보존한다(self):
        self._verdict()
        self._answer(1, {self.A: "사용가능", self.B: "제외"})
        self._verdict(ids=[self.B])
        kept = os.path.join(self.run_dir, "verdict", "rounds", "001",
                            "vresult_001.json")
        self.assertTrue(os.path.exists(kept), "앞 라운드 판정 근거가 사라졌다")
        # 새 라운드는 빈 results 에서 시작해야 한다 — 안 그러면 commit 이 앞 라운드
        # 결과까지 읽어 '배치에 없는 상품' 환각 경고를 쏟는다
        self.assertEqual(
            os.listdir(os.path.join(self.run_dir, "verdict", "results")), [])


class ReferenceSourceTest(unittest.TestCase):
    """광집게·크레인 — 기준이 이미 0번이면 기존 대표가 그대로 배경교체된다."""

    def test_워커가_고르면_워커선택(self):
        p = {"기준이미지": 1, "기존썸네일": ["a", "b"],
             "대표옵션이미지": "https://mo.jpg"}
        self.assertEqual(R.reference_source(p), R.REF_WORKER)
        self.assertEqual(R.reference_url(p), "b")

    def test_대표옵션이_있으면_대표옵션(self):
        p = {"기존썸네일": ["a"], "대표옵션이미지": "https://mo.jpg"}
        self.assertEqual(R.reference_source(p), R.REF_MAIN_OPTION)

    def test_아무것도_없으면_기존대표_맹목(self):
        """워커 판단도 대표옵션도 없이 기존 대표로 떨어진 것 — 태우기 전에 봐야 한다."""
        p = {"기존썸네일": ["https://cur.jpg"]}
        self.assertEqual(R.reference_source(p), R.REF_EXISTING)
        self.assertEqual(R.reference_url(p), "https://cur.jpg")
        # 올릴 게 없다 = 불사자가 기존 대표를 그대로 배경교체한다
        self.assertIsNone(R.staged_thumbnails(p["기존썸네일"], R.reference_url(p)))

    def test_bool_은_index_가_아니다(self):
        """`기준이미지: True` 를 index 1 로 읽으면 엉뚱한 이미지를 태운다."""
        p = {"기준이미지": True, "기존썸네일": ["a", "b"]}
        self.assertEqual(R.reference_source(p), R.REF_EXISTING)


class IsFinalTest(unittest.TestCase):
    def test_원본대체는_종결이다(self):
        self.assertTrue(R.is_final(R.VERDICT_FALLBACK))
        self.assertTrue(R.is_final("원본대체(대표옵션)"))

    def test_그_밖의_판정은_종결이_아니다(self):
        for v in ("사용가능", "제외", "제외(글자변조)", "제외(대표옵션의심)", "", None):
            with self.subTest(verdict=v):
                self.assertFalse(R.is_final(v))


if __name__ == "__main__":
    unittest.main()
