#!/usr/bin/env python3
"""prescreen(기준이미지 적격성) 회귀 테스트 — 불사자·시트 없이 돈다.

    python .claude/skills/bulsaja-thumbnail/scripts/test_thumb_prescreen.py

지키는 것:
  ① 승격분이 `pending` 에 잡힌다 — prep 이 전건 선기록이면 `batches_index.json` 이
     **dict** 라 `_pending_batches` 가 빈 배열을 돌려준다. list 로 갈아끼우지 않으면
     승격해놓고 아무도 안 돌린다(조용한 누락).
  ② `--commit` 이 멱등하다 — 두 번 불러도 같은 상품이 두 배치에 실리지 않는다.
  ③ 판정 누락·모르는 값은 `다중혼재`(fail-closed). 놓치면 사고(크레딧), 과잉이면
     워커 1회(크레딧 0)라 비용이 비대칭이다 — 갈매기조명 실증(2026-08-07: 무엇을 그릴지
     정해지지 않은 기준은 검수에서도 두 모델이 서로 다르게 오독했다).
  ④ 승격 배치에 판단 필드가 섞이지 않는다 — `batches/` 는 pass-through 필드의 정본이라
     워커가 채울 필드(`기준이미지경로` 등)가 미리 들어 있으면 안 된다.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
import contextlib
import io

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import run_thumbs                       # noqa: E402 — import 시 eroomlib 경로를 잡아준다
import thumb_rules as R                 # noqa: E402
from eroomlib import matrix             # noqa: E402


def _product(pid, cands=2):
    """prep 이 선기록한 모양 그대로 — 판단 필드(기준이미지경로·모드)까지 들어 있다."""
    return {
        "productId": pid,
        "상품명": f"상품 {pid}",
        "재작업사유": "",
        "기존썸네일": ["https://img.alicdn.com/x.jpg"],
        "대표이미지": f"/tmp/{pid}_0.webp",
        "후보이미지": [{"index": i, "url": "u", "path": f"/tmp/{pid}_{i}.webp"}
                       for i in range(1, cands + 1)],
        "대표옵션명": "기본형",
        "대표옵션이미지": "https://img.alicdn.com/m.jpg",
        "대표옵션이미지경로": f"/tmp/{pid}_9.webp",
        "기준이미지경로": f"/tmp/{pid}_9.webp",
        "모드": "기본",
    }


class PrescreenCommitTest(unittest.TestCase):

    def setUp(self):
        self.run_dir = tempfile.mkdtemp()
        self.marked, self.flagged = {}, {}
        self._orig = {"read": matrix.read, "mark_many": matrix.mark_many,
                      "flag_many": matrix.flag_many}
        matrix.read = lambda sheet: {p: {"썸네일": ""} for p in self.pids}
        matrix.mark_many = self._mark
        matrix.flag_many = self._flag

        self.pids = ["U01A", "U01B", "U01C", "U01D"]
        run_thumbs._dump(
            os.path.join(self.run_dir, "results", "result_000.json"),
            {"배치": 0, "선기록": True,
             "products": [_product(p) for p in self.pids]})
        # prep 이 전건 선기록이면 index 가 dict 다 — 여기가 ①의 함정.
        run_thumbs._dump(os.path.join(self.run_dir, "batches_index.json"),
                         {"배치": 0, "확정선기록": len(self.pids)})

    def tearDown(self):
        matrix.read = self._orig["read"]
        matrix.mark_many = self._orig["mark_many"]
        matrix.flag_many = self._orig["flag_many"]
        shutil.rmtree(self.run_dir, ignore_errors=True)

    def _mark(self, sheet, task, vals, matrix=None):
        self.marked.update(vals)
        return len(vals)

    def _flag(self, sheet, task, items, from_task=None, matrix=None):
        self.flagged[task] = dict(items)
        return len(items)

    def _judge(self, mapping, batch=1):
        run_thumbs._dump(
            os.path.join(self.run_dir, "prescreen_results",
                         f"presult_{batch:03d}.json"),
            {"배치": batch,
             "products": [{"productId": p, "판정": v, "사유": "테스트"}
                          for p, v in mapping.items()]})

    def _commit(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            run_thumbs._prescreen_commit("SHEET", self.run_dir)
        return out.getvalue()

    def _prerecorded_pids(self):
        _, products = run_thumbs._prerecorded(self.run_dir)
        return [p["productId"] for p in products]

    # ── ① 승격이 pending 에 잡히는가 ──────────────────────────────────────
    def test_다중혼재는_배치로_승격되고_index가_list로_바뀐다(self):
        self._judge({"U01A": R.PRE_SINGLE, "U01B": R.PRE_MIXED,
                     "U01C": R.PRE_MIXED, "U01D": R.PRE_SINGLE})
        self._commit()

        index = run_thumbs._load(os.path.join(self.run_dir, "batches_index.json"))
        self.assertIsInstance(index, list, "dict 로 남으면 pending 이 빈 배열을 돌려준다")
        pending = run_thumbs._pending_batches(self.run_dir)
        self.assertEqual(len(pending), len(index))
        promoted = set()
        for b in pending:
            for p in run_thumbs._load(b["path"])["products"]:
                promoted.add(p["productId"])
        self.assertEqual(promoted, {"U01B", "U01C"})

    def test_승격건은_선기록에서_빠지고_단일특정만_남는다(self):
        self._judge({"U01A": R.PRE_SINGLE, "U01B": R.PRE_MIXED,
                     "U01C": R.PRE_MIXED, "U01D": R.PRE_SINGLE})
        self._commit()
        self.assertEqual(sorted(self._prerecorded_pids()), ["U01A", "U01D"])

    def test_승격_배치의_imgs는_대표1_더하기_후보수다(self):
        self._judge({p: R.PRE_MIXED for p in self.pids})
        self._commit()
        index = run_thumbs._load(os.path.join(self.run_dir, "batches_index.json"))
        # 상품당 대표 1 + 후보 2 = 3장. PROMOTE_BATCH_SIZE(4)라 한 배치에 4건.
        self.assertEqual(sum(b["imgs"] for b in index), len(self.pids) * 3)
        self.assertEqual(sum(b["count"] for b in index), len(self.pids))

    # ── ④ 판단 필드가 승격 배치에 새지 않는가 ────────────────────────────
    def test_승격_배치에_판단필드가_없다(self):
        self._judge({"U01A": R.PRE_MIXED})
        self._commit()
        b = run_thumbs._pending_batches(self.run_dir)[0]
        prod = run_thumbs._load(b["path"])["products"][0]
        for f in run_thumbs._JUDGE_FIELDS:
            self.assertNotIn(f, prod, f"{f} 는 워커가 채울 필드다")
        self.assertIn("후보이미지", prod, "pass-through 필드는 남아야 한다")

    # ── ② 멱등성 ─────────────────────────────────────────────────────────
    def test_commit을_두_번_해도_승격이_중복되지_않는다(self):
        self._judge({"U01A": R.PRE_SINGLE, "U01B": R.PRE_MIXED,
                     "U01C": R.PRE_MIXED, "U01D": R.PRE_SINGLE})
        self._commit()
        first = run_thumbs._load(os.path.join(self.run_dir, "batches_index.json"))
        self._commit()
        second = run_thumbs._load(os.path.join(self.run_dir, "batches_index.json"))
        self.assertEqual(first, second, "두 번째 commit 이 배치를 또 만들면 안 된다")
        seen = [p["productId"]
                for b in second
                for p in run_thumbs._load(b["path"])["products"]]
        self.assertEqual(sorted(seen), ["U01B", "U01C"])
        self.assertEqual(len(seen), len(set(seen)))

    # ── ③ fail-closed ────────────────────────────────────────────────────
    def test_판정누락과_모르는_값은_다중혼재로_승격된다(self):
        self._judge({"U01A": "", "U01B": "이상한값", "U01C": R.PRE_SINGLE,
                     "U01D": R.PRE_SINGLE})
        self._commit()
        promoted = {p["productId"]
                    for b in run_thumbs._pending_batches(self.run_dir)
                    for p in run_thumbs._load(b["path"])["products"]}
        self.assertEqual(promoted, {"U01A", "U01B"})

    # ── 실물없음 ─────────────────────────────────────────────────────────
    def test_실물없음은_보류로_세우고_선기록에서_뺀다(self):
        self._judge({"U01A": R.PRE_NOPRODUCT, "U01B": R.PRE_SINGLE,
                     "U01C": R.PRE_SINGLE, "U01D": R.PRE_SINGLE})
        self._commit()
        self.assertEqual(self.marked, {"U01A": f"보류({R.VERDICT_NO_BASE})"})
        self.assertNotIn("U01A", self._prerecorded_pids())
        held = run_thumbs._load(os.path.join(self.run_dir, "prescreen_held.json"))
        self.assertIn("U01A", held)

    def test_실물없음은_옵션_열에_재작업_flag_를_찍는다(self):
        """**flag 를 빼먹으면 영구 정지다** — `보류(...)` 는 `matrix.pending()`
        (빈칸+재작업)에 안 잡혀 다음 회차가 다시 집어가지 않는다. 대표옵션이 비제품인 건
        뿌리가 옵션이라 옵션정리가 대표를 다시 세워야 풀린다(`R.TO_OPTION_VERDICTS`)."""
        self._judge({"U01A": R.PRE_NOPRODUCT, "U01B": R.PRE_SINGLE,
                     "U01C": R.PRE_SINGLE, "U01D": R.PRE_SINGLE})
        self._commit()
        self.assertIn("옵션", self.flagged)
        self.assertEqual(list(self.flagged["옵션"]), ["U01A"])
        self.assertTrue(self.flagged["옵션"]["U01A"])

    def test_해당없음_상품에는_보류도_flag_도_찍지_않는다(self):
        matrix.read = lambda sheet: {"U01A": {"썸네일": matrix.NA},
                                     "U01B": {"썸네일": ""},
                                     "U01C": {"썸네일": ""},
                                     "U01D": {"썸네일": ""}}
        self._judge({"U01A": R.PRE_NOPRODUCT, "U01B": R.PRE_SINGLE,
                     "U01C": R.PRE_SINGLE, "U01D": R.PRE_SINGLE})
        self._commit()
        self.assertEqual(self.marked, {}, "삭제 상품에 일감을 만들지 않는다")
        self.assertEqual(self.flagged, {})

    # ── 미판정 ───────────────────────────────────────────────────────────
    def test_미판정은_선기록에_남고_경고가_찍힌다(self):
        self._judge({"U01A": R.PRE_SINGLE, "U01B": R.PRE_MIXED})
        out = self._commit()
        # 판정이 없는 U01C·U01D 는 종전대로 그대로 생성된다(무회귀) — 대신 드러낸다.
        self.assertIn("U01C", self._prerecorded_pids())
        self.assertIn("U01D", self._prerecorded_pids())
        self.assertIn("미판정 2건", out)

    def test_결과가_없으면_아무것도_바꾸지_않는다(self):
        before = self._prerecorded_pids()
        out = self._commit()
        self.assertEqual(self._prerecorded_pids(), before)
        self.assertIn("prescreen_results 가 없다", out)


class PrescreenPartitionTest(unittest.TestCase):
    def test_세_값이_각각_제자리로_간다(self):
        mixed, noproduct, single = R.prescreen_partition([
            {"productId": "A", "판정": R.PRE_SINGLE},
            {"productId": "B", "판정": R.PRE_MIXED, "사유": "A款/B款"},
            {"productId": "C", "판정": R.PRE_NOPRODUCT, "사유": "치수 도면"},
        ])
        self.assertEqual(single, ["A"])
        self.assertEqual(mixed, {"B": "A款/B款"})
        self.assertEqual(noproduct, {"C": "치수 도면"})

    def test_사유가_비면_기본값을_채운다(self):
        mixed, noproduct, _ = R.prescreen_partition([
            {"productId": "B", "판정": R.PRE_MIXED},
            {"productId": "C", "판정": R.PRE_NOPRODUCT},
        ])
        self.assertTrue(mixed["B"])
        self.assertTrue(noproduct["C"])

    def test_상품id가_없으면_버린다(self):
        mixed, noproduct, single = R.prescreen_partition(
            [{"판정": R.PRE_MIXED}, {"productId": "", "판정": R.PRE_SINGLE}])
        self.assertEqual((mixed, noproduct, single), ({}, {}, []))


if __name__ == "__main__":
    unittest.main(verbosity=2)
