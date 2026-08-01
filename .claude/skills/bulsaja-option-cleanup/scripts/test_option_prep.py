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

    def test_마지막_차원_값이_1개면_수동판단_보류(self):
        # 제품유형 32 × 전력 1 모양(U01KR7VXBEAKCP3392VXQ9B415J 사례) — 어디 붙여도
        # 문제라 자동 저장을 막는다. 규칙대로 붙인 결과가 검증을 통과해 버리는 게 위험.
        self.assertEqual(
            run_options._status_of({"대표": "1", "이름검사": {}, "마커수동": True}, {}),
            "보류(기본형 수동판단)")
        # 마커수동이 없으면 기존 흐름 그대로
        self.assertNotEqual(
            run_options._status_of({"대표": "1", "이름검사": {}}, {}),
            "보류(기본형 수동판단)")

    def test_배치_정본이_없는_구형_run_dir은_대조를_생략한다(self):
        shutil.rmtree(os.path.join(self.run_dir, "batches"))
        self._w("results", "result_001.json", {"products": [
            {"productId": "U01legacy"}]})
        warns, missing = run_options._audit_results(self.run_dir)
        self.assertEqual((warns, missing), ([], False))
        pids = [pid for pid, _, _ in run_options._plans(self.run_dir)]
        self.assertEqual(pids, ["U01legacy"])


if __name__ == "__main__":
    unittest.main()
