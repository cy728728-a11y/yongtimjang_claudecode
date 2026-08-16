#!/usr/bin/env python3
"""prep 의 '대상 0건' sentinel 회귀 테스트 — 조회 실패를 '전부 기작업'으로 둔갑시키지 않는지.

run_detail.py 와 같은 결함의 썸네일 쪽 대응 — 세로 러너(onestep.py)는
batches_index.json 에 {"대상": 0, ...} 가 있으면 그 단계를 DONE 으로 기록한다.
targets 가 0건인 이유가 "대표가 이미 가공돼서"가 아니라 "workdata 조회가
실패해서"라면 이 sentinel 을 남기면 안 된다.

    python .claude/skills/bulsaja-thumbnail/scripts/test_thumb_prep.py
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
            lambda url, d, stem, i, **kw: (os.path.join(d, f"{stem}_{i}.jpg"), url))

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
        snapshot.materialize_image = lambda url, d, stem, i, **kw: (None, "HTTP 404")
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


class PrepBackfillGateTest(unittest.TestCase):
    """백필 3갈래 게이트(2026-08-05 수정지시서 §6A) — 가공됨 ≠ 맞게 가공됨."""

    PROCESSED = ["https://cdn.bulsaja.com/x.jpg", "https://img.alicdn.com/c1.jpg"]
    MAIN_OPT = {"차원": [], "vid고유": True, "판매행": [
        {"id": "1", "text": "3톤 기본형", "sale_price": 28000, "stock": 5,
         "exclude": False, "main_product": True, "urlRef": "https://a/3t.jpg"}]}

    def setUp(self):
        self.run_dir = tempfile.mkdtemp()
        self.marked = {}
        self._orig = {
            "read": matrix.read, "redo_pending": matrix.redo_pending,
            "mark_many": matrix.mark_many, "ensure": snapshot.ensure,
            "materialize_image": snapshot.materialize_image,
        }
        matrix.read = lambda sheet: {}
        matrix.redo_pending = lambda m, task: {}
        matrix.mark_many = (lambda sheet, task, d, matrix=None:
                            (self.marked.update(d), len(d))[1])
        snapshot.materialize_image = (
            lambda url, d, stem, i, **kw: (os.path.join(d, f"{stem}_{i}.jpg"), url))

    def tearDown(self):
        for k, v in self._orig.items():
            setattr(matrix if k in ("read", "redo_pending", "mark_many") else snapshot,
                    k, v)
        shutil.rmtree(self.run_dir, ignore_errors=True)

    def _read(self, *parts):
        path = os.path.join(self.run_dir, *parts)
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _prep(self, rec, ids=("U01x",)):
        snapshot.ensure = lambda pids, **kw: ({pid: rec for pid in pids}, {})
        run_thumbs.cmd_prep(argparse.Namespace(
            run_dir=self.run_dir, sheet="SHEET", group_name=None, ids=list(ids),
            limit=None, sleep=0, max_candidates=3, batch_size=10))

    def test_가공됨_대표옵션_있음은_백필하지_않고_정합검사_대상이다(self):
        self._prep({"썸네일": self.PROCESSED, "상품명": "유압자키",
                    "옵션": self.MAIN_OPT})
        self.assertEqual(self.marked, {}, "정합검사 대상인데 완료로 백필했다")
        self.assertEqual(self._read("audit_targets.json"), ["U01x"])
        # '전부 기작업' sentinel 로 DONE 둔갑 금지 — 산출물 없이 멈춘다(fail-closed)
        self.assertIsNone(self._read("batches_index.json"))
        self.assertIsNone(self._read("batches", "batch_001.json"))

    def test_가공됨_대표옵션_없음은_종전대로_백필한다(self):
        self._prep({"썸네일": self.PROCESSED, "상품명": "유압자키", "옵션": None})
        self.assertEqual(self.marked, {"U01x": "완료(기존 가공 확인)"})
        self.assertIsNone(self._read("audit_targets.json"))

    def test_가공됨_재작업_flag는_종전대로_대상에_남는다(self):
        # 기존 방어 회귀 — 재작업 flag 는 정합검사·백필보다 먼저 대상으로 잡힌다
        matrix.redo_pending = (lambda m, task:
                               {"U01x": "대표 썸네일이 대표옵션과 다른 색"})
        self._prep({"썸네일": self.PROCESSED, "상품명": "유압자키", "옵션": None})
        self.assertEqual(self.marked, {}, "재작업 건을 백필해 버렸다")
        batch = self._read("batches", "batch_001.json")
        self.assertEqual([p["productId"] for p in batch["products"]], ["U01x"])


class AuditBuildTest(unittest.TestCase):
    """audit 준비 단계 — 완료* 대상 확정·표본 추출·배치 구성·대조불가 선기록."""

    MAIN_OPT = {"차원": [], "vid고유": True, "판매행": [
        {"id": "1", "text": "3톤 기본형", "sale_price": 28000, "stock": 5,
         "exclude": False, "main_product": True, "urlRef": "https://a/3t.jpg"}]}

    def setUp(self):
        self.run_dir = tempfile.mkdtemp()
        self._orig = {"read": matrix.read, "ensure": snapshot.ensure,
                      "materialize_image": snapshot.materialize_image}
        # 현황판: 완료 2건(하나는 대표옵션 없음) + 미착수 1건
        self.m = {
            "U01done": {"row": 2, "썸네일": "완료(기존 가공 확인)"},
            "U01nomo": {"row": 3, "썸네일": "완료"},
            "U01todo": {"row": 4, "썸네일": ""},
        }
        matrix.read = lambda sheet, tab=matrix.TAB: self.m
        rec_mo = {"상품명": "유압자키", "옵션": self.MAIN_OPT,
                  "썸네일": ["https://cdn.bulsaja.com/cur.jpg"]}
        rec_plain = {"상품명": "무옵션", "옵션": None,
                     "썸네일": ["https://cdn.bulsaja.com/cur2.jpg"]}
        self.recs = {"U01done": rec_mo, "U01nomo": rec_plain, "U01todo": rec_mo}
        snapshot.ensure = (lambda pids, **kw:
                           ({p: self.recs[p] for p in pids if p in self.recs}, {}))
        snapshot.materialize_image = (
            lambda url, d, stem, i, **kw: (os.path.join(d, f"{stem}_{i}.jpg"), None))

    def tearDown(self):
        matrix.read = self._orig["read"]
        snapshot.ensure = self._orig["ensure"]
        snapshot.materialize_image = self._orig["materialize_image"]
        shutil.rmtree(self.run_dir, ignore_errors=True)

    def _read(self, *parts):
        path = os.path.join(self.run_dir, *parts)
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _audit(self, **over):
        args = dict(run_dir=self.run_dir, sheet="SHEET", group_name=None,
                    sample=0, limit=0, batch_size=12, commit=False, sleep=0,
                    sweep=False)
        args.update(over)
        run_thumbs.cmd_audit(argparse.Namespace(**args))

    def test_sweep_이면_완료건_중_대표옵션_있는_것만_배치에_싣는다(self):
        self._audit(sweep=True)
        batch = self._read("audit_batches", "audit_batch_001.json")
        self.assertEqual([p["productId"] for p in batch["products"]], ["U01done"])
        p = batch["products"][0]
        self.assertEqual(p["대표옵션명"], "3톤 기본형")
        # 두 이미지는 **idx 로** 구분한다 — name_hint 는 24자에서 잘려서 `_main`/`_cur`
        # 접미사가 사라지고, 확장자까지 같으면 같은 파일에 덮어써진다(2026-08-06 실측 3건).
        self.assertTrue(p["대표옵션이미지경로"].endswith("_0.jpg"), p["대표옵션이미지경로"])
        self.assertTrue(p["현재대표경로"].endswith("_1.jpg"), p["현재대표경로"])
        self.assertNotEqual(p["대표옵션이미지경로"], p["현재대표경로"])
        idx = self._read("audit_batches_index.json")
        self.assertEqual(idx[0]["imgs"], 2)   # 건당 이미지 2장

    def _targets(self, pids, dir_=None):
        path = os.path.join(dir_ or self.run_dir, "audit_targets.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(pids, f)
        return path

    def test_기본_대상은_prep이_넘긴_정합검사_대상뿐이다(self):
        # 2026-08-06 이룸님: 완료* 재대조는 verdict 와 중복 + 판정이 흔들려 재작업이
        # 되살아난다. 현황판 완료(U01done)가 있어도 --sweep 없이는 안 잡는다.
        self._targets(["U01todo"])
        self._audit()
        batch = self._read("audit_batches", "audit_batch_001.json")
        self.assertEqual([p["productId"] for p in batch["products"]], ["U01todo"])

    def test_sweep이면_완료건이_대상에_더해진다(self):
        self._targets(["U01todo"])
        self._audit(sweep=True)
        batch = self._read("audit_batches", "audit_batch_001.json")
        self.assertEqual(sorted(p["productId"] for p in batch["products"]),
                         ["U01done", "U01todo"])

    def test_targets_명시로_다른_런디렉토리의_대상을_읽는다(self):
        # §6-G: prep run-dir ≠ audit run-dir 이면 대상이 조용히 빠졌다 — --targets 로 명시
        other = tempfile.mkdtemp()
        try:
            self._audit(targets=self._targets(["U01todo"], other))
            batch = self._read("audit_batches", "audit_batch_001.json")
            self.assertEqual([p["productId"] for p in batch["products"]], ["U01todo"])
        finally:
            shutil.rmtree(other, ignore_errors=True)

    def test_targets도_sweep도_없으면_중단한다(self):
        # 조용히 0건으로 끝내면 "감사했는데 깨끗하다"로 읽힌다(§6-G 와 같은 결함)
        with self.assertRaises(SystemExit) as cm:
            self._audit()
        self.assertEqual(cm.exception.code, 2)
        self.assertIsNone(self._read("audit_batches", "audit_batch_001.json"))

    def test_명시한_targets_파일이_없으면_중단한다(self):
        # 명시했는데 못 찾으면 조용히 진행하는 게 §6-G 의 원래 결함이다 — 멈춘다
        with self.assertRaises(SystemExit):
            self._audit(targets=os.path.join(self.run_dir, "없는파일.json"))

    def test_대표옵션_404는_삭제대상으로_분리된다(self):
        # 2026-08-06 이룸님: 대표옵션 이미지 404 = 소싱 소멸 → 대조불가가 아니라 자동 삭제 대상
        snapshot.materialize_image = lambda url, d, stem, i, **kw: (None, "HTTP 404")
        self._audit(sweep=True)
        d404 = self._read("audit_delete_404.json")
        self.assertIn("U01done", d404)
        self.assertIn("404", d404["U01done"]["사유"])
        self.assertIsNone(self._read("audit_results", "audit_result_000.json"))
        self.assertIsNone(self._read("audit_batches", "audit_batch_001.json"))

    def test_그외_이미지_확보_실패는_대조불가_선기록으로_남긴다(self):
        snapshot.materialize_image = lambda url, d, stem, i, **kw: (None, "연결 시간 초과")
        self._audit(sweep=True)
        pre = self._read("audit_results", "audit_result_000.json")
        self.assertTrue(pre["선기록"])
        self.assertEqual(pre["products"][0]["productId"], "U01done")
        self.assertEqual(pre["products"][0]["판정"], "대조불가")
        self.assertIsNone(self._read("audit_delete_404.json"))
        self.assertIsNone(self._read("audit_batches", "audit_batch_001.json"))

    def test_표본은_균등_간격으로_뽑는다(self):
        # 대조 가능 4건에서 --sample 2 → 정렬 후 0번째·2번째
        rec = self.recs["U01done"]
        self.m = {f"U01s{i}": {"row": 2 + i, "썸네일": "완료"} for i in range(4)}
        self.recs = {pid: rec for pid in self.m}
        self._audit(sample=2, sweep=True)
        batch = self._read("audit_batches", "audit_batch_001.json")
        self.assertEqual([p["productId"] for p in batch["products"]],
                         ["U01s0", "U01s2"])


class AuditCommitTest(unittest.TestCase):
    """audit --commit — 불일치만 재작업 flag, 대조불가는 flag 하지 않는다."""

    def setUp(self):
        self.run_dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.run_dir, "audit_results"))
        self.marked = {}
        # 현황판: 전부 백필 완료 상태 + 삭제(해당없음) 상품 1건
        self.m = {
            "U01bad": {"row": 2, "썸네일": "완료(기존 가공 확인)"},
            "U01ok": {"row": 3, "썸네일": "완료(기존 가공 확인)"},
            "U01na": {"row": 4, "썸네일": matrix.NA},
            "U01broken": {"row": 5, "썸네일": "완료(기존 가공 확인)"},
        }
        self._orig = {"read": matrix.read, "mark_many": matrix.mark_many}
        matrix.read = lambda sheet, tab=matrix.TAB: self.m
        matrix.mark_many = (lambda sheet, task, d, tab=matrix.TAB, matrix=None:
                            (self.marked.update(d), len(d))[1])

    def tearDown(self):
        matrix.read = self._orig["read"]
        matrix.mark_many = self._orig["mark_many"]
        shutil.rmtree(self.run_dir, ignore_errors=True)

    def _commit(self, products):
        with open(os.path.join(self.run_dir, "audit_results", "audit_result_001.json"),
                  "w", encoding="utf-8") as f:
            json.dump({"배치": 1, "products": products}, f, ensure_ascii=False)
        run_thumbs._audit_commit("SHEET", self.run_dir)

    def test_불일치는_재작업_flag_되고_다음_pending에_잡힌다(self):
        self._commit([{"productId": "U01bad", "판정": "불일치",
                       "사유": "대표옵션 3000W인데 8500W 표기"}])
        self.assertEqual(self.marked,
                         {"U01bad": "재작업(정합검사: 대표옵션 3000W인데 8500W 표기)"})
        # flag 반영 후 현황판을 다시 읽으면 pending(미착수+재작업)에 잡힌다
        after = {pid: {**rec, "썸네일": self.marked.get(pid, rec["썸네일"])}
                 for pid, rec in self.m.items()}
        self.assertIn("U01bad", matrix.pending(after, "썸네일"))

    def test_대조불가는_flag_하지_않는다(self):
        # 무한 재작업 루프 방지 — flag 하면 다음 prep 이 또 집어가고 또 대조불가가 난다
        self._commit([{"productId": "U01broken", "판정": "대조불가",
                       "사유": "대표옵션 이미지 404"}])
        self.assertEqual(self.marked, {}, "대조불가를 재작업으로 flag 했다")
        unc = None
        path = os.path.join(self.run_dir, "audit_uncomparable.json")
        with open(path, encoding="utf-8") as f:
            unc = json.load(f)
        self.assertEqual(list(unc), ["U01broken"])

    def test_일치는_정합확인으로_찍고_삭제상품은_건드리지_않는다(self):
        self._commit([{"productId": "U01ok", "판정": "일치"},
                      {"productId": "U01na", "판정": "불일치", "사유": "다른 제품"}])
        self.assertEqual(self.marked, {"U01ok": "완료(정합확인)"},
                         "삭제(해당없음) 상품에 일감을 만들었다")

    def _index(self, pids):
        """audit_batches_index.json + 그 배치 파일 — 미대조 검사의 정본."""
        bdir = os.path.join(self.run_dir, "audit_batches")
        os.makedirs(bdir, exist_ok=True)
        path = os.path.join(bdir, "audit_batch_001.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"배치": 1, "products": [{"productId": p} for p in pids]},
                      f, ensure_ascii=False)
        with open(os.path.join(self.run_dir, "audit_batches_index.json"),
                  "w", encoding="utf-8") as f:
            json.dump([{"n": 1, "path": path, "imgs": 2 * len(pids),
                        "count": len(pids)}], f)

    def test_배치_대비_미대조는_경고하고_목록을_남긴다(self):
        # 결과 파일이 통째로 빠져도 ###AUDIT### 이 정상 종료로 찍혀 "감사했는데 깨끗하다"로
        # 읽힌다(2026-08-15 2-3: run 팬아웃이 "완료배치 7" 을 반환했는데 디스크에 result 가
        # 없었다). verdict 처럼 차단하진 않되 **건수는 반드시 보인다.**
        self._index(["U01ok", "U01bad"])
        self._commit([{"productId": "U01ok", "판정": "일치"}])
        with open(os.path.join(self.run_dir, "audit_missing.json"),
                  encoding="utf-8") as f:
            self.assertEqual(json.load(f), ["U01bad"])
        # 차단은 하지 않는다 — 판정된 건은 그대로 반영된다
        self.assertEqual(self.marked, {"U01ok": "완료(정합확인)"})

    def test_전건_대조되면_미대조_파일을_만들지_않는다(self):
        self._index(["U01ok"])
        self._commit([{"productId": "U01ok", "판정": "일치"}])
        self.assertFalse(os.path.exists(
            os.path.join(self.run_dir, "audit_missing.json")))

    def test_인덱스가_없으면_미대조_검사를_건너뛴다(self):
        # 그 축을 안 돌린 run-dir — 대조할 정본이 없다. 거짓 경고를 내지 않는다.
        self._commit([{"productId": "U01ok", "판정": "일치"}])
        self.assertFalse(os.path.exists(
            os.path.join(self.run_dir, "audit_missing.json")))


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


class PrepImagePathCollisionTest(unittest.TestCase):
    """prep 의 대표이미지 ↔ 대표옵션이미지 파일명 충돌 (2026-08-06 결함정리 §2-1).

    `materialize_image` 가 name_hint 를 **24자로 자른다**. 상품id 가 27자라
    `_rep`·`_main` 접미사가 통째로 날아가고, idx 가 둘 다 0이면 **같은 파일**이 된다 —
    생성은 URL 로 도니 무사하지만 **워커가 보는 이미지가 뒤바뀐다**.
    """

    PID = "U01KSAKSYKTA2S22AAP9DTZG0H0"      # 27자 — 실제 상품id 길이

    def setUp(self):
        self.run_dir = tempfile.mkdtemp()
        self._orig = {"read": matrix.read, "redo_pending": matrix.redo_pending,
                      "mark_many": matrix.mark_many, "ensure": snapshot.ensure,
                      "materialize_image": snapshot.materialize_image}
        matrix.read = lambda sheet: {}
        matrix.redo_pending = lambda m, task: {}
        matrix.mark_many = lambda sheet, task, d, matrix=None: len(d)
        # **실물과 같이 24자에서 자른다** — 이 절단이 없으면 결함이 재현되지 않는다.
        snapshot.materialize_image = (
            lambda url, d, stem, i, **kw: (os.path.join(d, f"{stem[:24]}_{i}.jpg"), None))

    def tearDown(self):
        for k, v in self._orig.items():
            setattr(matrix if k in ("read", "redo_pending", "mark_many") else snapshot,
                    k, v)
        shutil.rmtree(self.run_dir, ignore_errors=True)

    def test_대표이미지와_대표옵션이미지가_다른_파일이다(self):
        rec = {"썸네일": ["https://img/rep.jpg", "https://img/c1.jpg"],
               "상품명": "슬링랙",
               "옵션": {"판매행": [{"id": "1", "main_product": True, "exclude": False,
                                 "text": "랙 기본형",
                                 "urlRef": "https://img/main.jpg"}]}}
        snapshot.ensure = lambda pids, **kw: ({pid: rec for pid in pids}, {})
        args = argparse.Namespace(run_dir=self.run_dir, sheet="SHEET", group_name=None,
                                  ids=[self.PID], limit=None, sleep=0, batch_size=10,
                                  max_candidates=5)
        run_thumbs.cmd_prep(args)
        # 대표옵션이 있으면 배치가 아니라 result_000(확정 선기록)으로 간다
        with open(os.path.join(self.run_dir, "results", "result_000.json"),
                  encoding="utf-8") as f:
            p = json.load(f)["products"][0]
        self.assertTrue(p["대표옵션이미지경로"], "대표옵션 이미지가 비었다")
        self.assertNotEqual(p["대표이미지"], p["대표옵션이미지경로"],
                            "대표이미지와 대표옵션이미지가 같은 파일이다(워커가 뒤바뀐 걸 본다)")

    def test_후보_idx와도_겹치지_않는다(self):
        rec = {"썸네일": ["https://img/rep.jpg"] + [f"https://img/c{i}.jpg"
                                                 for i in range(1, 10)],
               "상품명": "슬링랙",
               "옵션": {"판매행": [{"id": "1", "main_product": True, "exclude": False,
                                 "text": "랙 기본형",
                                 "urlRef": "https://img/main.jpg"}]}}
        snapshot.ensure = lambda pids, **kw: ({pid: rec for pid in pids}, {})
        args = argparse.Namespace(run_dir=self.run_dir, sheet="SHEET", group_name=None,
                                  ids=[self.PID], limit=None, sleep=0, batch_size=10,
                                  max_candidates=9)      # 후보 idx 1..9
        run_thumbs.cmd_prep(args)
        with open(os.path.join(self.run_dir, "results", "result_000.json"),
                  encoding="utf-8") as f:
            p = json.load(f)["products"][0]
        paths = [p["대표이미지"]] + [c["path"] for c in p["후보이미지"]]
        self.assertNotIn(p["대표옵션이미지경로"], paths,
                         "대표옵션 이미지가 후보 이미지와 같은 파일이다")


class VerdictCommitTest(unittest.TestCase):
    """검수 판정 팬아웃 수합 (2026-08-06 결함정리 §2-3).

    누락을 그냥 통과시키면 판정 안 한 상품이 `decisions.json` 에 없다는 이유로
    `apply --commit` 에서 **전부 사용가능으로 반영**된다 — 검수 생략이 검수 통과로 둔갑.
    """

    def setUp(self):
        self.run_dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.run_dir, "verdict", "batches"), exist_ok=True)
        os.makedirs(os.path.join(self.run_dir, "verdict", "results"), exist_ok=True)
        bpath = os.path.join(self.run_dir, "verdict", "batches", "vbatch_001.json")
        self._w(bpath, {"배치": 1, "products": [{"productId": "U01a"},
                                              {"productId": "U01b"}]})
        self._w(os.path.join(self.run_dir, "verdict_batches_index.json"),
                [{"n": 1, "path": bpath, "count": 2, "imgs": 6}])

    def tearDown(self):
        shutil.rmtree(self.run_dir, ignore_errors=True)

    @staticmethod
    def _w(path, obj):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)

    def _result(self, products):
        self._w(os.path.join(self.run_dir, "verdict", "results", "vresult_001.json"),
                {"배치": 1, "products": products})

    def _dec(self):
        p = os.path.join(self.run_dir, "decisions.json")
        if not os.path.exists(p):
            return None
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    def test_전건_판정되면_decisions를_쓴다(self):
        self._result([{"productId": "U01a", "판정": "사용가능", "사유": ""},
                      {"productId": "U01b", "판정": "제외", "사유": "3구인데 2구"}])
        run_thumbs._verdict_commit(self.run_dir, {})
        dec = self._dec()
        self.assertEqual(dec["U01b"]["판정"], "제외")
        self.assertEqual(dec["U01b"]["사유"], "3구인데 2구")

    def test_판정_누락이면_쓰지_않고_멈춘다(self):
        self._result([{"productId": "U01a", "판정": "사용가능"}])
        with self.assertRaises(SystemExit) as e:
            run_thumbs._verdict_commit(self.run_dir, {})
        self.assertEqual(e.exception.code, 3)
        self.assertIsNone(self._dec(), "누락이 있는데 decisions.json 을 썼다")

    def test_배치에_없는_환각은_버린다(self):
        self._result([{"productId": "U01a", "판정": "사용가능"},
                      {"productId": "U01b", "판정": "주의", "사유": "그림자"},
                      {"productId": "U01ghost", "판정": "제외", "사유": "환각"}])
        run_thumbs._verdict_commit(self.run_dir, {})
        self.assertNotIn("U01ghost", self._dec())

    def test_잘린_productId는_자기_배치_안에서_복구된다(self):
        """워커가 이미지 파일명(24자)에서 베껴 id 가 잘리면 판정이 통째로 버려지고
        같은 건이 누락으로도 잡혀 commit 이 막힌다(2026-08-14 3-2 2건·2-2 15건).
        판정 내용은 멀쩡하므로 접두 매칭으로 되살린다."""
        self._result([{"productId": "U01a", "판정": "사용가능"},
                      {"productId": "U01", "판정": "제외", "사유": "3구인데 2구"}])
        # 'U01' 은 U01a·U01b 둘 다에 걸려 모호 → 복구 안 되고 누락으로 막혀야 한다
        with self.assertRaises(SystemExit):
            run_thumbs._verdict_commit(self.run_dir, {})

        # 후보가 하나뿐이면 복구된다
        self._result([{"productId": "U01a", "판정": "사용가능"},
                      {"productId": "U01", "판정": "제외", "사유": "3구인데 2구"}])
        bpath = os.path.join(self.run_dir, "verdict", "batches", "vbatch_001.json")
        self._w(bpath, {"배치": 1, "products": [{"productId": "U01a"},
                                              {"productId": "U01zzz"}]})
        self._result([{"productId": "U01a", "판정": "사용가능"},
                      {"productId": "U01zz", "판정": "제외", "사유": "3구인데 2구"}])
        run_thumbs._verdict_commit(self.run_dir, {})
        dec = self._dec()
        self.assertIn("U01zzz", dec, "잘린 id 가 복구되지 않았다")
        self.assertNotIn("U01zz", dec, "잘린 id 가 그대로 남았다")
        self.assertEqual(dec["U01zzz"]["사유"], "3구인데 2구")

    def test_다른_배치의_id로는_복구되지_않는다(self):
        """배치를 넘어 매칭하면 남의 판정을 엉뚱한 상품에 붙이게 된다."""
        b2 = os.path.join(self.run_dir, "verdict", "batches", "vbatch_002.json")
        self._w(b2, {"배치": 2, "products": [{"productId": "U01ccc"}]})
        b1 = os.path.join(self.run_dir, "verdict", "batches", "vbatch_001.json")
        self._w(os.path.join(self.run_dir, "verdict_batches_index.json"),
                [{"n": 1, "path": b1, "count": 2, "imgs": 6},
                 {"n": 2, "path": b2, "count": 1, "imgs": 3}])
        # 배치1 결과에 배치2 상품의 잘린 id 를 넣는다 → 복구되면 안 된다
        self._result([{"productId": "U01a", "판정": "사용가능"},
                      {"productId": "U01b", "판정": "사용가능"},
                      {"productId": "U01cc", "판정": "제외", "사유": "남의 배치"}])
        self._w(os.path.join(self.run_dir, "verdict", "results", "vresult_002.json"),
                {"배치": 2, "products": [{"productId": "U01ccc", "판정": "사용가능"}]})
        run_thumbs._verdict_commit(self.run_dir, {})
        dec = self._dec()
        self.assertEqual(dec["U01ccc"]["판정"], "사용가능",
                         "배치를 넘어 복구돼 남의 판정이 덮였다")

    def test_남은_배치는_pending에_잡힌다(self):
        self.assertEqual([b["n"] for b in
                          run_thumbs._pending_verdict_batches(self.run_dir)], [1])
        self._result([{"productId": "U01a", "판정": "사용가능"}])
        self.assertEqual(run_thumbs._pending_verdict_batches(self.run_dir), [])


class PrepNoRealBaseTest(unittest.TestCase):
    """옵션이 `실물기준없음` 으로 되돌린 건은 **선기록하지 않는다** (2026-08-07 이룸님).

    **이게 썸네일↔옵션 왕복의 종결 상태다.** 선기록하면 `prescreen` 이 또 `실물없음` 을 내
    옵션으로 되돌리는데, 그 상품엔 실물 옵션이 애초에 없으니 또 되돌아온다 — 무한 왕복.
    옵션 이미지가 전부 비제품인 상품은 실재한다(3-2 실측 57건 중 고유 옵션이미지 1장 3건).
    여기서 비전 배치로 보내 **썸네일 워커가 후보에서 고르게** 하면 왕복이 1회로 끝난다.
    """

    OPTION = {"차원": [], "vid고유": True, "판매행": [
        {"id": "1", "text": "기본형", "sale_price": 28000, "stock": 5,
         "exclude": False, "main_product": True, "urlRef": "https://a/main.jpg"}]}

    def setUp(self):
        self.run_dir = tempfile.mkdtemp()
        self._orig = {
            "read": matrix.read, "redo_pending": matrix.redo_pending,
            "mark_many": matrix.mark_many, "ensure": snapshot.ensure,
            "materialize_image": snapshot.materialize_image,
        }
        matrix.read = lambda sheet: {}
        matrix.mark_many = lambda sheet, task, d, matrix=None: len(d)
        snapshot.materialize_image = (
            lambda url, d, stem, i, **kw: (os.path.join(d, f"{stem}_{i}.jpg"), url))
        rec = {"썸네일": ["https://img.alicdn.com/rep.jpg",
                        "https://img.alicdn.com/c1.jpg"],
               "상품명": "장대톱", "옵션": self.OPTION}
        snapshot.ensure = lambda pids, **kw: ({pid: rec for pid in pids}, {})

    def tearDown(self):
        for k, v in self._orig.items():
            setattr(matrix if k in ("read", "redo_pending", "mark_many") else snapshot,
                    k, v)
        shutil.rmtree(self.run_dir, ignore_errors=True)

    def _run(self, redo_reason):
        matrix.redo_pending = lambda m, task: ({"U01x": redo_reason}
                                               if redo_reason else {})
        run_thumbs.cmd_prep(argparse.Namespace(
            run_dir=self.run_dir, sheet="SHEET", group_name=None, ids=["U01x"],
            limit=None, sleep=0, max_candidates=3, batch_size=10))
        pre = os.path.join(self.run_dir, "results", "result_000.json")
        bat = os.path.join(self.run_dir, "batches", "batch_001.json")
        return os.path.exists(pre), os.path.exists(bat)

    def test_마커가_있으면_선기록이_아니라_비전_배치로_간다(self):
        prerecorded, batched = self._run("옵션: 실물기준없음: 모든 옵션 이미지가 비제품")
        self.assertFalse(prerecorded, "선기록하면 prescreen 이 또 되돌려 무한 왕복이 된다")
        self.assertTrue(batched, "후보에서 고르게 하려면 비전 배치에 실려야 한다")

    def test_마커가_없는_재작업은_종전대로_선기록된다(self):
        prerecorded, batched = self._run("옵션: 대표색 불일치")
        self.assertTrue(prerecorded, "일반 재작업까지 비전으로 보내면 워커 비용이 되돌아온다")
        self.assertFalse(batched)

    def test_재작업이_아니어도_종전대로_선기록된다(self):
        prerecorded, batched = self._run(None)
        self.assertTrue(prerecorded)
        self.assertFalse(batched)

    def _batch_product(self):
        with open(os.path.join(self.run_dir, "batches", "batch_001.json"),
                  encoding="utf-8") as f:
            return json.load(f)["products"][0]

    def test_비전_배치에_대표옵션_기준을_남기지_않는다(self):
        """2026-08-17 용쌤2-1 실측 — 남기면 배치가 **모순된 지시**를 담는다.

        워커 프롬프트 규칙 0 은 "`대표옵션이미지경로` 가 있으면 그게 기준이다, 고르지
        마라"다. 비전 배치로 보내놓고 그 경로를 남기면 워커는 규칙대로 대표옵션을 도로
        집는다(실측 3건 전부). 그 index 는 후보에 없어 URL 해석이 실패하고 **맹목
        배경교체**로 떨어진다 — 크레딧은 나가고 기준은 한 글자도 안 바뀐다.
        """
        self._run("옵션: 실물기준없음: 모든 옵션 이미지가 비제품")
        p = self._batch_product()
        self.assertEqual(p.get("대표옵션이미지경로"), "")
        self.assertEqual(p.get("대표옵션이미지"), "")

    def test_대표옵션명은_남긴다(self):
        """후보에서 '그 옵션과 같은 물건'을 고르려면 이름이 필요하다.

        이름은 규칙 0 을 발동시키지 않으므로 지울 이유가 없다.
        """
        self._run("옵션: 실물기준없음: 모든 옵션 이미지가 비제품")
        self.assertEqual(self._batch_product().get("대표옵션명"), "기본형")


class NoRealBaseMarkerTest(unittest.TestCase):
    """마커 판별 — 옵션 워커가 사유 안에 낱말을 넣고, 썸네일이 그걸 읽는다."""

    def test_사유_어디에_있어도_찾는다(self):
        for s in ("실물기준없음", "옵션: 실물기준없음: 전부 도면",
                  "재작업(옵션: 실물기준없음)"):
            self.assertTrue(run_thumbs.R.no_real_base(s), s)

    def test_그_밖의_사유는_아니다(self):
        for s in ("", None, "옵션: 대표색 불일치", "기준이미지없음"):
            self.assertFalse(run_thumbs.R.no_real_base(s), s)


class HealTruncatedPidTest(unittest.TestCase):
    """워커가 이미지 파일명(24자)에서 베낀 productId 복구 — 2026-08-14.

    `materialize_image` 가 파일명을 24자로 자르는데 productId 는 27자다. 지시서에 경고를
    넣은 당일 2-2 에서 15건이 또 났다 = 지시문으로 안 막힌다. 수합부가 되살린다.
    """

    FULL = "U01KSD7D7Y3338WQQKZWT0XTH5C"      # 27자 정본
    CUT = "U01KSD7D7Y3338WQQKZWT0XT"          # 파일명에서 베낀 24자

    def _capture(self, products, valid, axis="테스트"):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            healed = run_thumbs._heal_pids(products, valid, axis)
        return healed, err.getvalue()

    def test_후보가_1개면_정본으로_되살린다(self):
        prods = [{"productId": self.CUT, "판정": "사용가능"}]
        healed, log = self._capture(prods, {self.FULL, "U01OTHER0000000000000000AAA"})
        self.assertEqual(prods[0]["productId"], self.FULL)
        self.assertEqual(healed, [f"{self.CUT}→{self.FULL}"])
        self.assertIn("잘린 productId 1건", log)

    def test_후보가_2개_이상이면_손대지_않는다(self):
        """접두가 두 상품을 가리키면 어느 쪽인지 알 수 없다 — 환각으로 남긴다."""
        twin = self.CUT + "ZZZ"
        prods = [{"productId": self.CUT}]
        healed, _ = self._capture(prods, {self.FULL, twin})
        self.assertEqual(prods[0]["productId"], self.CUT)
        self.assertEqual(healed, [])

    def test_후보가_없으면_손대지_않는다(self):
        prods = [{"productId": "U01ENTIRELY_MADE_UP_XXXXXXX"}]
        healed, _ = self._capture(prods, {self.FULL})
        self.assertEqual(healed, [])

    def test_이미_정본이면_건드리지_않는다(self):
        prods = [{"productId": self.FULL}]
        healed, log = self._capture(prods, {self.FULL})
        self.assertEqual(healed, [])
        self.assertEqual(log, "")

    def test_정본_집합이_비면_아무것도_하지_않는다(self):
        """구형 run-dir·그 축을 안 돌린 run-dir — 복구 기준이 없다."""
        prods = [{"productId": self.CUT}]
        self.assertEqual(self._capture(prods, set())[0], [])
        self.assertEqual(prods[0]["productId"], self.CUT)

    def test_index_pids_는_없는_파일에_죽지_않는다(self):
        d = tempfile.mkdtemp()
        try:
            self.assertEqual(run_thumbs._index_pids(d, "audit_batches_index.json"), set())
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_index_pids_가_배치의_정본_id_를_모은다(self):
        d = tempfile.mkdtemp()
        try:
            bp = os.path.join(d, "audit_batch_001.json")
            with open(bp, "w", encoding="utf-8") as f:
                json.dump({"products": [{"productId": self.FULL},
                                        {"productId": "U01SECOND000000000000000BBB"}]}, f)
            with open(os.path.join(d, "audit_batches_index.json"), "w",
                      encoding="utf-8") as f:
                json.dump([{"n": 1, "path": bp},
                           {"n": 2, "path": os.path.join(d, "없는파일.json")}], f)
            got = run_thumbs._index_pids(d, "audit_batches_index.json")
            self.assertEqual(got, {self.FULL, "U01SECOND000000000000000BBB"})
        finally:
            shutil.rmtree(d, ignore_errors=True)


class MarkDeletedTest(unittest.TestCase):
    """mark-deleted — 404 로 지운 건을 현황판 `해당없음` 으로 확정한다 (2026-08-16).

    404 목록은 **둘 다 있을 거라는 보장이 없다.** prep 이 대표 원본 404 를 하나도
    안 만나면 `deletion_candidates.json` 이 아예 안 생기고, audit 만 404 를 잡는다
    (2-3 r5 실측: audit 404 4건 · prep 404 0건). 없는 파일에 죽으면 **audit 쪽
    404 목록이 멀쩡히 있어도 확정이 통째로 실패**해 현황판이 `보류(...삭제대상)` 로
    남고, 다음 회차가 이미 지운 상품을 또 삭제 대상으로 집는다.
    """

    def setUp(self):
        self.run_dir = tempfile.mkdtemp()
        self.marked = {}
        self._orig = matrix.mark_many
        matrix.mark_many = (lambda sheet, task, d, tab=matrix.TAB, matrix=None:
                            (self.marked.update(d), len(d))[1])

    def tearDown(self):
        matrix.mark_many = self._orig
        shutil.rmtree(self.run_dir, ignore_errors=True)

    def _write(self, name, obj):
        with open(os.path.join(self.run_dir, name), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)

    def _run(self, ids=None):
        args = argparse.Namespace(sheet="SHEET", group_name="", run_dir=self.run_dir,
                                  ids=ids, no_matrix=False)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            run_thumbs.cmd_mark_deleted(args)
        return out.getvalue()

    def test_audit_목록만_있어도_확정된다(self):
        # deletion_candidates.json 은 만들지 않는다 — 실측에서 자주 없는 쪽이다
        self._write("audit_delete_404.json",
                    {"U01a": {"상품명": "종이전시대", "사유": "대표옵션 이미지 404"}})
        log = self._run()
        self.assertEqual(self.marked, {"U01a": "해당없음(원본404·삭제)"})
        self.assertIn("확정 1건", log)

    def test_prep_목록만_있어도_확정된다(self):
        self._write("deletion_candidates.json", {"U01b": "임팩트렌치"})
        self._run()
        self.assertEqual(self.marked, {"U01b": "해당없음(원본404·삭제)"})

    def test_두_목록을_합친다(self):
        self._write("deletion_candidates.json", {"U01b": "임팩트렌치"})
        self._write("audit_delete_404.json", {"U01a": {"상품명": "종이전시대"}})
        self._run()
        self.assertEqual(set(self.marked), {"U01a", "U01b"})

    def test_목록이_하나도_없으면_exit_2_로_멈춘다(self):
        """조용히 0건으로 끝나면 '확정했다'로 오독된다."""
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(io.StringIO()):
            self._run()
        self.assertEqual(cm.exception.code, 2)
        self.assertEqual(self.marked, {})

    def test_ids_는_목록에_없는_id_도_받고_나머지는_좁힌다(self):
        self._write("audit_delete_404.json", {"U01a": {"상품명": "종이전시대"},
                                              "U01skip": {"상품명": "안 지운 것"}})
        self._run(ids=["U01a", "U01manual"])
        self.assertEqual(set(self.marked), {"U01a", "U01manual"})


if __name__ == "__main__":
    unittest.main()
