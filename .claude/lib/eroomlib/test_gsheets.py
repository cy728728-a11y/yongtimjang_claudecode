#!/usr/bin/env python3
"""gws 시트 래퍼 회귀 테스트 — subprocess 를 가짜로 갈아끼워 네트워크 없이 돈다.

    python .claude/lib/eroomlib/test_gsheets.py

지키려는 계약:
  1. **API 오류를 삼키지 않는다** — gws 는 오류도 exit 0 + JSON 으로 돌려준다.
     그걸 그대로 반환하면 실패한 쓰기가 성공으로 보인다(2026-07-28 실제 사고:
     'Range exceeds grid limits' 가 삼켜져 매트릭스 4개 그룹에서 수만 칸이 유실됨).
  2. 청크는 **개수가 아니라 실제 JSON 길이**로 끊는다 — 윈도우 명령줄 32,767자 상한.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eroomlib import gsheets  # noqa: E402


class FakeProc:
    def __init__(self, stdout, returncode=0, stderr=""):
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr


class RunGwsTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self._orig = gsheets.subprocess.run
        self.reply = "{}"

        def fake_run(cmd, **kw):
            self.calls.append(cmd)
            r = self.reply(len(self.calls)) if callable(self.reply) else self.reply
            return FakeProc(r)

        gsheets.subprocess.run = fake_run
        self._sleep = gsheets.time.sleep
        gsheets.time.sleep = lambda s: None

    def tearDown(self):
        gsheets.subprocess.run = self._orig
        gsheets.time.sleep = self._sleep

    def test_오류_응답은_예외로_올린다(self):
        self.reply = json.dumps({"error": {"code": 400,
                                           "message": "Range exceeds grid limits"}})
        with self.assertRaises(RuntimeError) as cm:
            gsheets._run_gws(["x"])
        self.assertIn("400", str(cm.exception))
        self.assertIn("grid limits", str(cm.exception))

    def test_정상_응답은_그대로_돌려준다(self):
        self.reply = json.dumps({"values": [["a"], ["b"]]})
        self.assertEqual(gsheets.sheets_get("S", "A1:A2"), [["a"], ["b"]])

    def test_error_키가_dict_가_아니면_오류로_보지_않는다(self):
        # 시트 데이터에 'error' 라는 값이 들어 있을 수 있다 — 오진하면 안 된다
        self.reply = json.dumps({"error": "", "values": [["a"]]})
        self.assertEqual(gsheets.sheets_get("S", "A1"), [["a"]])

    def test_update_는_429_에_백오프_재시도한다(self):
        def reply(n):
            if n < 3:
                return json.dumps({"error": {"code": 429, "message": "quota exceeded"}})
            return json.dumps({"updatedCells": 1})
        self.reply = reply
        gsheets.sheets_update("S", "'T'!A1", [["x"]])
        self.assertEqual(len(self.calls), 3)

    def test_update_는_429가_아닌_오류엔_바로_터진다(self):
        self.reply = json.dumps({"error": {"code": 400, "message": "bad range"}})
        with self.assertRaises(RuntimeError):
            gsheets.sheets_update("S", "'T'!A1", [["x"]])
        self.assertEqual(len(self.calls), 1, "재시도하면 안 되는 오류를 재시도했다")

    def test_append_도_429에_재시도하고_실패는_올린다(self):
        self.reply = json.dumps({"error": {"code": 400, "message": "bad"}})
        with self.assertRaises(RuntimeError):
            gsheets.append_rows("S", "T", [["x"]])
        self.assertEqual(len(self.calls), 1)


class ChunkTest(unittest.TestCase):
    def test_길이로_끊고_시작_인덱스를_준다(self):
        rows = [["A" * 100] for _ in range(10)]
        parts = list(gsheets.chunk_by_size(rows, budget=300))
        self.assertGreater(len(parts), 1)
        # 순서·전량 보존
        self.assertEqual(sum(len(p) for _, p in parts), 10)
        self.assertEqual([i for i, _ in parts], [0, 2, 4, 6, 8])
        flat = [r for _, p in parts for r in p]
        self.assertEqual(flat, rows)

    def test_한_행이_예산보다_커도_버리지_않는다(self):
        rows = [["A" * 50000], ["b"]]
        parts = list(gsheets.chunk_by_size(rows, budget=100))
        self.assertEqual(sum(len(p) for _, p in parts), 2)

    def test_짧으면_한_번에_나간다(self):
        rows = [["완료"] for _ in range(100)]
        self.assertEqual(len(list(gsheets.chunk_by_size(rows))), 1)

    def test_빈_입력(self):
        self.assertEqual(list(gsheets.chunk_by_size([])), [])


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    unittest.main(verbosity=2)
