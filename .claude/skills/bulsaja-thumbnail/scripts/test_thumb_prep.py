#!/usr/bin/env python3
"""prep 의 '대상 0건' sentinel 회귀 테스트 — 조회 실패를 '전부 기작업'으로 둔갑시키지 않는지.

run_detail.py 와 같은 결함의 썸네일 쪽 대응 — 세로 러너(onestep.py)는
batches_index.json 에 {"대상": 0, ...} 가 있으면 그 단계를 DONE 으로 기록한다.
targets 가 0건인 이유가 "대표가 이미 가공돼서"가 아니라 "workdata 조회가
실패해서"라면 이 sentinel 을 남기면 안 된다.

    python .claude/skills/bulsaja-thumbnail/scripts/test_thumb_prep.py
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import run_thumbs                       # noqa: E402 — import 시 eroomlib 경로를 잡아준다
from eroomlib import matrix, snapshot   # noqa: E402


def _args(run_dir, ids):
    return argparse.Namespace(run_dir=run_dir, sheet="SHEET", group_name=None,
                              ids=ids, limit=None, sleep=0)


class PrepZeroTargetSentinelTest(unittest.TestCase):

    def setUp(self):
        self.run_dir = tempfile.mkdtemp()
        self._orig = {
            "read": matrix.read, "redo_pending": matrix.redo_pending,
            "mark_many": matrix.mark_many, "ensure": snapshot.ensure,
        }
        matrix.read = lambda sheet: {}
        matrix.redo_pending = lambda m, task: {}
        matrix.mark_many = lambda sheet, task, d, matrix=None: len(d)

    def tearDown(self):
        matrix.read = self._orig["read"]
        matrix.redo_pending = self._orig["redo_pending"]
        matrix.mark_many = self._orig["mark_many"]
        snapshot.ensure = self._orig["ensure"]
        shutil.rmtree(self.run_dir, ignore_errors=True)

    def _sentinel(self):
        path = os.path.join(self.run_dir, "batches_index.json")
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def test_조회_실패로_0건이면_sentinel을_남기지_않는다(self):
        # snapshot.ensure 가 전량 실패했다고 시뮬레이션 — recs 는 비고 errors 만 찬다.
        snapshot.ensure = (lambda pids, **kw:
                           ({}, {pid: "RuntimeError: timeout" for pid in pids}))
        run_thumbs.cmd_prep(_args(self.run_dir, ["U01fail"]))
        sentinel = self._sentinel()
        self.assertIsNone(
            sentinel,
            "조회 실패인데 sentinel 을 남겼다 — 세로 러너가 이 단계를 DONE 으로 오판한다")

    def test_진짜_기작업이면_sentinel을_그대로_남긴다(self):
        # snapshot.ensure 성공 + 대표가 이미 가공됨 → 진짜 대상 0건, 에러 없음.
        done_rec = {"썸네일": ["https://cdn.bulsaja.com/x.jpg"]}
        snapshot.ensure = lambda pids, **kw: ({pid: done_rec for pid in pids}, {})
        run_thumbs.cmd_prep(_args(self.run_dir, ["U01done"]))
        self.assertEqual(
            self._sentinel(),
            {"대상": 0, "이유": "전부 기작업(대표가 이미 cdn.bulsaja.com)"},
            "진짜 기작업인데 sentinel 을 안 남겼다 — 러너가 산출물 없음으로 멈춰버린다")


class PrepMainOptionTest(unittest.TestCase):
    """prep 이 대표옵션을 배치에 실어야 한다 — 없으면 기준 이미지를 고정할 수 없다."""

    def setUp(self):
        self.run_dir = tempfile.mkdtemp()
        self._orig = {
            "read": matrix.read, "redo_pending": matrix.redo_pending,
            "mark_many": matrix.mark_many, "ensure": snapshot.ensure,
            "materialize_image": snapshot.materialize_image,
        }
        matrix.read = lambda sheet: {}
        matrix.redo_pending = lambda m, task: {}
        matrix.mark_many = lambda sheet, task, d, matrix=None: len(d)
        # 실제 다운로드 대신 "받았다"고만 답한다 — 경로는 url 에서 파생시켜 구분 가능하게.
        snapshot.materialize_image = (
            lambda url, d, stem, i: (os.path.join(d, f"{stem}_{i}.jpg"), url))

    def tearDown(self):
        for k, v in self._orig.items():
            setattr(matrix if k in ("read", "redo_pending", "mark_many") else snapshot,
                    k, v)
        shutil.rmtree(self.run_dir, ignore_errors=True)

    def _batch(self):
        path = os.path.join(self.run_dir, "batches", "batch_001.json")
        with open(path, encoding="utf-8") as f:
            return json.load(f)["products"][0]

    def _read(self, *parts):
        path = os.path.join(self.run_dir, *parts)
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _run(self, option, fixed=False, expect_batch=True):
        rec = {"썸네일": ["https://img.alicdn.com/rep.jpg",
                        "https://img.alicdn.com/c1.jpg"],
               "상품명": "유압자키", "옵션": option}
        snapshot.ensure = lambda pids, **kw: ({pid: rec for pid in pids}, {})
        args = argparse.Namespace(run_dir=self.run_dir, sheet="SHEET", group_name=None,
                                  ids=["U01x"], limit=None, sleep=0,
                                  max_candidates=3, batch_size=10)
        run_thumbs.cmd_prep(args)
        if fixed:   # 확정건은 배치가 아니라 result_000(선기록)에 실린다 (2026-08-01)
            return self._read("results", "result_000.json")["products"][0]
        if not expect_batch:
            return None
        return self._batch()

    def test_대표옵션이_있으면_선기록으로_가고_전_필드를_싣는다(self):
        p = self._run({"차원": [], "vid고유": True, "판매행": [
            {"id": "1", "text": "3톤 기본형", "sale_price": 28000, "stock": 5,
             "exclude": False, "main_product": True, "urlRef": "https://a/3t.jpg"},
            {"id": "2", "text": "10톤", "sale_price": 68000, "stock": 5,
             "exclude": False, "main_product": False, "urlRef": "https://a/10t.jpg"}]},
            fixed=True)
        self.assertEqual(p["대표옵션명"], "3톤 기본형")
        self.assertEqual(p["대표옵션이미지"], "https://a/3t.jpg")
        self.assertTrue(p["대표옵션이미지경로"], "기준 이미지를 로컬로 받아둬야 Read 할 수 있다")
        # 선기록은 prep 이 기준이미지경로·모드를 직접 채운다(워커 판단 0)
        self.assertEqual(p["기준이미지경로"], p["대표옵션이미지경로"])
        self.assertEqual(p["모드"], "기본")
        # 확정건뿐이면 배치가 없고, index 는 sentinel 이 아닌 dict 로 남는다
        self.assertIsNone(self._read("batches", "batch_001.json"))
        idx = self._read("batches_index.json")
        self.assertEqual(idx, {"배치": 0, "확정선기록": 1})
        # pending 은 빈 배열 — 워크플로 호출이 필요 없다
        self.assertEqual(run_thumbs._pending_batches(self.run_dir), [])

    def test_대표가_없으면_빈값으로_두고_비전_판단에_맡긴다(self):
        p = self._run({"차원": [], "vid고유": True, "판매행": [
            {"id": "1", "text": "3톤", "sale_price": 28000, "stock": 5,
             "exclude": False, "main_product": False, "urlRef": "https://a/3t.jpg"}]})
        self.assertEqual(p["대표옵션명"], "")
        self.assertEqual(p["대표옵션이미지경로"], "")
        self.assertTrue(p["후보이미지"], "폴백 경로가 살아 있어야 한다")

    def test_대표옵션에_이미지가_없으면_경로만_빈다(self):
        p = self._run({"차원": [], "vid고유": True, "판매행": [
            {"id": "1", "text": "블랙 기본형", "sale_price": 9900, "stock": 5,
             "exclude": False, "main_product": True, "urlRef": ""}]})
        self.assertEqual(p["대표옵션명"], "블랙 기본형")
        self.assertEqual(p["대표옵션이미지경로"], "")

    def test_옵션_필드가_아예_없어도_prep_이_돈다(self):
        p = self._run(None)
        self.assertEqual(p["대표옵션명"], "")
        self.assertEqual(p["대표옵션이미지경로"], "")

    def test_원본_404면_삭제대상으로_기재하고_배치에서_뺀다(self):
        # 대표 다운로드가 404 → 워커에 안 보내고 deletion_candidates + 현황판 보류 기재
        marked = {}
        matrix.mark_many = (lambda sheet, task, d, matrix=None:
                            (marked.update(d), len(d))[1])
        snapshot.materialize_image = lambda url, d, stem, i: (None, "HTTP 404")
        self._run(None, expect_batch=False)
        cand = self._read("deletion_candidates.json")
        self.assertEqual(list(cand), ["U01x"])
        self.assertEqual(marked, {"U01x": "보류(원본404·삭제대상)"})
        self.assertIsNone(self._read("batches", "batch_001.json"))
        idx = self._read("batches_index.json")
        self.assertEqual(idx.get("대상"), 0)
        self.assertIn("404", idx.get("이유", ""))

    def test_비전건은_index가_신형식이고_pending에_잡힌다(self):
        self._run(None)
        idx = self._read("batches_index.json")
        self.assertEqual(len(idx), 1)
        b = idx[0]
        self.assertEqual(b["n"], 1)
        self.assertTrue(os.path.isabs(b["path"]))
        self.assertEqual(b["count"], 1)
        # 대표 1 + 후보 1 (스텁 rec 의 썸네일 2장)
        self.assertEqual(b["imgs"], 2)
        pend = run_thumbs._pending_batches(self.run_dir)
        self.assertEqual([x["n"] for x in pend], [1])
        # 결과 파일이 생기면 pending 에서 빠진다
        os.makedirs(os.path.join(self.run_dir, "results"), exist_ok=True)
        with open(os.path.join(self.run_dir, "results", "result_001.json"),
                  "w", encoding="utf-8") as f:
            json.dump({"배치": 1, "products": []}, f)
        self.assertEqual(run_thumbs._pending_batches(self.run_dir), [])


class ResultsJoinAuditTest(unittest.TestCase):
    """_results 조인·_audit — 워커 환각이 백업·복원 경로에 못 들어가는지."""

    def setUp(self):
        self.run_dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.run_dir, "batches"))
        os.makedirs(os.path.join(self.run_dir, "results"))
        self._w("batches", "batch_001.json", {"배치": 1, "products": [
            {"productId": "U01a", "상품명": "자키", "기존썸네일": ["https://t/1.jpg"],
             "대표이미지": "D:/a_rep.jpg", "후보이미지": [], "대표옵션명": "",
             "대표옵션이미지": "", "대표옵션이미지경로": ""}]})

    def tearDown(self):
        shutil.rmtree(self.run_dir, ignore_errors=True)

    def _w(self, *parts_and_obj):
        *parts, obj = parts_and_obj
        with open(os.path.join(self.run_dir, *parts), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)

    def test_pass_through는_배치가_정본이고_판단_필드만_워커것이다(self):
        # 워커가 기존썸네일을 훼손해 보내도(환각) 배치 값이 이긴다
        self._w("results", "result_001.json", {"배치": 1, "products": [
            {"productId": "U01a", "기준이미지": 0, "기준이미지경로": "D:/a_rep.jpg",
             "모드": "기본", "기존썸네일": ["https://EVIL/x.jpg"]}]})
        items = run_thumbs._results(self.run_dir)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["기존썸네일"], ["https://t/1.jpg"],
                         "워커가 보낸 pass-through 가 백업 경로에 들어갔다")
        self.assertEqual(items[0]["기준이미지경로"], "D:/a_rep.jpg")

    def test_배치에_없는_pid는_버리고_감사가_경고한다(self):
        self._w("results", "result_001.json", {"배치": 1, "products": [
            {"productId": "U01a", "기준이미지": 0, "모드": "기본"},
            {"productId": "U01ghost", "기준이미지": 1, "모드": "기본"}]})
        items = run_thumbs._results(self.run_dir)
        self.assertEqual([p["productId"] for p in items], ["U01a"])
        warns, missing = run_thumbs._audit(self.run_dir)
        self.assertFalse(missing)
        self.assertTrue(any("U01ghost" in w for w in warns))

    def test_누락이_있으면_감사가_missing을_알린다(self):
        # 결과 파일이 아예 없다 → U01a 누락
        warns, missing = run_thumbs._audit(self.run_dir)
        self.assertTrue(missing)
        self.assertTrue(any("U01a" in w for w in warns))

    def test_선기록_result000은_그대로_신뢰한다(self):
        self._w("results", "result_000.json", {"배치": 0, "선기록": True, "products": [
            {"productId": "U01fix", "상품명": "고정건", "기존썸네일": ["https://t/f.jpg"],
             "기준이미지경로": "D:/f_main.jpg", "모드": "기본"}]})
        self._w("results", "result_001.json", {"배치": 1, "products": [
            {"productId": "U01a", "기준이미지": 0, "모드": "기본"}]})
        items = {p["productId"]: p for p in run_thumbs._results(self.run_dir)}
        self.assertIn("U01fix", items)
        self.assertEqual(items["U01fix"]["기준이미지경로"], "D:/f_main.jpg")
        # 선기록은 배치에 없어도 감사 누락·환각으로 잡히지 않는다
        warns, missing = run_thumbs._audit(self.run_dir)
        self.assertFalse(missing)
        self.assertFalse(any("U01fix" in w for w in warns))


if __name__ == "__main__":
    unittest.main()
