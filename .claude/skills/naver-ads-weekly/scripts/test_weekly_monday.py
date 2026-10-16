#!/usr/bin/env python3
"""월요일 래퍼 회귀 테스트 — 가짜 러너·가짜 업무판(네트워크·subprocess 0).

실패 정책(2026-10-16 확정): bids/prune 은 prep·run 성공에만 의존. enrich·apply·업무판 실패는 기록만.
"""
import json
import os
import sys
import tempfile
import types
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import weekly_monday as W  # noqa: E402

TODAY = date(2026, 10, 19)


class FakeRunner:
    def __init__(self, rc=None):
        self.rc = rc or {}
        self.calls = []

    def __call__(self, argv):
        self.calls.append(list(argv))
        return self.rc.get(argv[0], 0)

    def names(self):
        return [c[0] for c in self.calls]


class FakeBoard:
    def __init__(self, existing=(("번호",), ("3",), ("7",)), fail=False):
        self.existing = [list(r) for r in existing]
        self.fail = fail
        self.appended = []

    def get(self, sid, rng):
        return self.existing

    def append(self, sid, tab, rows):
        if self.fail:
            raise RuntimeError("시트 429")
        self.appended.append((sid, tab, rows))
        return len(rows)


def rd_rows():
    """result.json — ⑦b 2, ⑦c 후보 3(그중 AI가공완료 히트 1 → 최종 2), ⑦d 3(정비완료 1 → 미정비 2)."""
    return {"generated": "2026-10-19", "accounts": {
        "A": {"summary": {}, "rules": {
            "⑦b썸네일변형": [{"adId": "b1"}, {"adId": "b2"}],
            "⑦c상세꾸미기후보": [
                {"adId": "c1", "불사자매칭": "히트", "상세상태": "중국어원본"},
                {"adId": "c2", "불사자매칭": "히트", "상세상태": "AI가공완료"},
                {"adId": "c3", "불사자매칭": "미매칭: 키없음"}],
            "⑦d정비점검후보": [
                {"adId": "d1", "불사자매칭": "히트", "상세미가공": False, "옵션미정리": False},
                {"adId": "d2", "불사자매칭": "히트", "상세미가공": True, "옵션미정리": False},
                {"adId": "d3"}],
        }}}}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.rd = Path(self.tmp.name)
        (self.rd / "result.json").write_text(json.dumps(rd_rows(), ensure_ascii=False), encoding="utf-8")
        (self.rd / "bids_commit.json").write_text(json.dumps(
            {"A": {"committed": 5, "plans": [1] * 5}, "B": {"committed": 2, "plans": [1, 2]}}), encoding="utf-8")
        (self.rd / "prune_commit.json").write_text(json.dumps({"total": 4, "adIds": []}), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def go(self, rc=None, board=None, dry=False, sheet="SHEET"):
        self.runner = FakeRunner(rc)
        self.board = board or FakeBoard()
        args = types.SimpleNamespace(run_dir="2026-10-19", sheet=sheet, dry_run=dry)
        code = W.run(args, runner=self.runner, board_append=self.board.append, board_get=self.board.get,
                     work_board_id="WB", today=TODAY, run_dir_path=self.rd, log=lambda m: None)
        self.wr = json.loads((self.rd / "weekly_result.json").read_text(encoding="utf-8"))
        return code


class TestOrder(Base):
    def test_전_단계_성공_순서와_인자(self):
        self.assertEqual(self.go(), 0)
        self.assertEqual(self.runner.names(), ["prep", "run", "enrich", "apply", "bids", "prune"])
        c = {x[0]: x for x in self.runner.calls}
        self.assertIn("--sheet", c["apply"])
        self.assertEqual(c["apply"][c["apply"].index("--sheet") + 1], "SHEET")
        self.assertIn("--commit", c["bids"])
        self.assertIn("--commit", c["prune"])
        self.assertEqual(c["enrich"][c["enrich"].index("--expect-nick") + 1], "부킹")
        self.assertEqual(c["prune"][c["prune"].index("--backup-tag") + 1], "weekly-20261019")
        for x in self.runner.calls:
            self.assertEqual(x[x.index("--run-dir") + 1], "2026-10-19")

    def test_업무판_1행_모양(self):
        self.go()
        self.assertEqual(len(self.board.appended), 1)
        sid, tab, rows = self.board.appended[0]
        self.assertEqual((sid, tab), ("WB", "오늘"))
        row = rows[0]
        self.assertEqual(row[0], 8)   # 최대 7 + 1
        self.assertEqual(row[1], "2026-10-19")
        self.assertEqual(row[2], "✓")
        self.assertEqual(row[3], "⑦ 광고 주간 2026-10-19")
        self.assertEqual(row[4:7], ["⑦", "Claude", "자동"])
        self.assertEqual(row[8], "")
        self.assertEqual(self.wr["board"]["status"], "ok")

    def test_메모_형식(self):
        self.go()
        self.assertEqual(self.wr["memo"],
                         "입찰+10 7 · 썸네일변형 2 · 상세꾸미기 2 · 정비점검 3(미정비 2) · 꺼진소재 삭제 4")

    def test_시트_기본값은_상수(self):
        self.go(sheet=None)
        c = {x[0]: x for x in self.runner.calls}
        sid = c["apply"][c["apply"].index("--sheet") + 1]
        self.assertTrue(sid in (W.DEFAULT_SHEET, W._cfg("sheets.naver_ads")))


class TestFailurePolicy(Base):
    def test_run_실패면_이후_전부_생략(self):
        self.assertEqual(self.go(rc={"run": 1}), 1)
        self.assertEqual(self.runner.names(), ["prep", "run"])
        self.assertTrue(self.wr["memo"].startswith("실패: run"))
        for k in ("enrich", "apply", "bids", "prune"):
            self.assertEqual(self.wr["steps"][k], "skipped")
        self.assertEqual(self.board.appended[0][2][0][2], "")   # 체크칸 빈칸

    def test_prep_실패면_run도_생략(self):
        self.go(rc={"prep": 2})
        self.assertEqual(self.runner.names(), ["prep"])
        self.assertEqual(self.wr["steps"]["run"], "skipped")

    def test_enrich_실패해도_apply_bids_prune_실행(self):
        self.assertEqual(self.go(rc={"enrich": 3}), 1)
        self.assertEqual(self.runner.names(), ["prep", "run", "enrich", "apply", "bids", "prune"])
        self.assertTrue(self.wr["memo"].startswith("실패: enrich"))
        self.assertEqual(self.wr["steps"]["enrich"], 3)

    def test_apply_실패해도_bids_prune_실행(self):
        self.go(rc={"apply": 1})
        self.assertIn("bids", self.runner.names())
        self.assertIn("prune", self.runner.names())

    def test_bids_실패해도_prune_실행(self):
        self.go(rc={"bids": 1})
        self.assertEqual(self.runner.names()[-1], "prune")

    def test_러너_예외도_실패로_기록(self):
        def boom(argv):
            if argv[0] == "enrich":
                raise RuntimeError("x")
            return 0
        board = FakeBoard()
        args = types.SimpleNamespace(run_dir="2026-10-19", sheet="S", dry_run=False)
        code = W.run(args, runner=boom, board_append=board.append, board_get=board.get,
                     work_board_id="WB", today=TODAY, run_dir_path=self.rd, log=lambda m: None)
        self.assertEqual(code, 1)

    def test_업무판_예외면_종료코드는_단계대로_board_failed(self):
        self.assertEqual(self.go(board=FakeBoard(fail=True)), 0)
        self.assertEqual(self.wr["board"]["status"], "failed")


class TestMemoRobust(Base):
    def test_파일_없으면_물음표(self):
        for f in ("result.json", "bids_commit.json", "prune_commit.json"):
            (self.rd / f).unlink()
        m = W.build_memo(self.rd, [])
        self.assertEqual(m, "입찰+10 ? · 썸네일변형 ? · 상세꾸미기 ? · 정비점검 ?(미정비 ?) · 꺼진소재 삭제 ?")

    def test_깨진_파일도_물음표(self):
        (self.rd / "bids_commit.json").write_text("{깨짐", encoding="utf-8")
        self.assertIn("입찰+10 ?", W.build_memo(self.rd, []))


class TestDryRun(Base):
    def test_dry_run은_commit_없이_할일_접두(self):
        self.go(dry=True)
        c = {x[0]: x for x in self.runner.calls}
        self.assertNotIn("--commit", c["bids"])
        self.assertNotIn("--commit", c["prune"])
        self.assertTrue(self.board.appended[0][2][0][3].startswith("[dry-run] "))
        self.assertIn("입찰+10(예정) 7", self.wr["memo"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
