#!/usr/bin/env python3
"""run_names.py rename 경로 회귀 테스트 (stdlib unittest — pytest 불필요).

실행: python test_run_names.py   (또는 python -m unittest test_run_names -v)

대상은 2026-07-27 용쌤1-1 실측 결함 2개:
  F1 배치 거부 시 재시도가 없어 불량 1건이 정상 49건을 같이 죽인다
  F2 반영 결과를 시트 상태열에 되쓰지 않는다
"""
import argparse
import json
import os
import sys
import tempfile
import unittest

for _s in (sys.stdout, sys.stderr):  # 콘솔 cp949 에서 한글 테스트명이 깨지지 않게
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

import run_names  # noqa: E402


def _targets(n, prefix="P"):
    return [{"productId": f"{prefix}{i:03d}", "name": f"상품명{i}", "원본": ""}
            for i in range(n)]


class RenameCascadeTest(unittest.TestCase):
    """F1 — 배치 거부 시 계단식 분해(50 → 10 → 1)."""

    def test_전량_성공이면_50건씩만_호출한다(self):
        calls = []

        def submit(chunk):
            calls.append(len(chunk))
            return True, ""

        ok, bad, err = run_names._rename_cascade(_targets(120), submit)

        self.assertEqual(len(ok), 120)
        self.assertEqual(bad, [])
        self.assertEqual(err, [])
        self.assertEqual(calls, [50, 50, 20])  # 분해가 일어나지 않는다

    def test_불량_1건이_섞여도_같은_배치의_정상건은_살린다(self):
        bad_id = "P037"

        def submit(chunk):
            if any(t["productId"] == bad_id for t in chunk):
                return False, "내 상품이 아닌 상품이 1개 있어 중단했습니다."
            return True, ""

        ok, bad, err = run_names._rename_cascade(_targets(50), submit)

        self.assertEqual(len(ok), 49)
        self.assertNotIn(bad_id, ok)
        self.assertEqual([pid for pid, _ in bad], [bad_id])
        self.assertEqual(err, [])

    def test_불량_2건이_서로_다른_10청크에_있어도_둘_다_찾아낸다(self):
        bad_ids = {"P003", "P044"}

        def submit(chunk):
            if any(t["productId"] in bad_ids for t in chunk):
                return False, "내 상품이 아닌 상품이 있어 중단했습니다."
            return True, ""

        ok, bad, err = run_names._rename_cascade(_targets(50), submit)

        self.assertEqual(len(ok), 48)
        self.assertEqual(sorted(pid for pid, _ in bad), sorted(bad_ids))
        self.assertEqual(err, [])

    def test_끝자락_짧은_청크는_같은_크기로_재호출하지_않는다(self):
        """50건 청크가 3건뿐이면 10건 단계를 건너뛰고 바로 1건씩으로 내려간다."""
        calls = []

        def submit(chunk):
            calls.append(len(chunk))
            return False, "거부"

        ok, bad, err = run_names._rename_cascade(_targets(3), submit)

        self.assertEqual(ok, [])
        self.assertEqual(len(bad), 3)
        self.assertEqual(calls, [3, 1, 1, 1])  # 3건을 3건으로 다시 던지지 않는다

    def test_예외는_불량이_아니라_오류로_분류된다(self):
        """네트워크 오류를 '상품삭제'로 확정하면 멀쩡한 상품이 죽는다."""
        def submit(chunk):
            raise RuntimeError("HTTP 503")

        ok, bad, err = run_names._rename_cascade(_targets(2), submit)

        self.assertEqual(ok, [])
        self.assertEqual(bad, [])
        self.assertEqual(sorted(pid for pid, _ in err), ["P000", "P001"])
        self.assertIn("HTTP 503", err[0][1])

    def test_예외도_분해해서_원인_1건만_격리한다(self):
        """MCP 오류가 특정 상품 때문일 수 있다. 통째로 포기하면 그 배치는
        재실행마다 같은 자리에서 계속 막힌다."""
        def submit(chunk):
            if any(t["productId"] == "P007" for t in chunk):
                raise RuntimeError("호출 오류: invalid product")
            return True, ""

        ok, bad, err = run_names._rename_cascade(_targets(20), submit)

        self.assertEqual(len(ok), 19)
        self.assertEqual(bad, [])
        self.assertEqual([pid for pid, _ in err], ["P007"])

    def test_연속_오류가_이어지면_분해를_멈추고_남은_건은_호출_없이_넘긴다(self):
        """통신 장애에서 50→10→1 로 다 쪼개면 재시도 폭풍이 된다."""
        calls = []

        def submit(chunk):
            calls.append(len(chunk))
            raise RuntimeError("HTTP 503")

        ok, bad, err = run_names._rename_cascade(
            _targets(120), submit, max_consecutive_errors=3)

        self.assertEqual(ok, [])
        self.assertEqual(bad, [])
        self.assertEqual(len(err), 120)          # 전건이 '오류'로 남는다(상태 보존)
        self.assertLessEqual(len(calls), 6)      # 폭주하지 않는다
        self.assertTrue(any("중단" in msg for _, msg in err))

    def test_차단을_유발한_청크는_진짜_오류_메시지를_남긴다(self):
        """'미시도'로 뭉뚱그리면 무엇 때문에 멈췄는지 로그에서 사라진다."""
        calls = []

        def submit(chunk):
            calls.append(len(chunk))
            raise RuntimeError("HTTP 503")

        ok, bad, err = run_names._rename_cascade(
            _targets(20), submit, sizes=(10, 1), max_consecutive_errors=1)

        self.assertEqual(len(calls), 1)                  # 차단 후 추가 호출 없음
        msgs = dict(err)
        self.assertIn("HTTP 503", msgs["P000"])          # 실제로 던진 청크
        self.assertIn("미시도", msgs["P010"])             # 호출조차 안 한 청크

    def test_성공하면_연속_오류_카운터가_풀린다(self):
        seq = {"n": 0}

        def submit(chunk):
            seq["n"] += 1
            if seq["n"] in (1, 3):               # 1·3번째 호출만 오류
                raise RuntimeError("일시 오류")
            return True, ""

        ok, bad, err = run_names._rename_cascade(
            _targets(30), submit, sizes=(10, 1), max_consecutive_errors=2)

        self.assertEqual(len(ok) + len(err), 30)
        self.assertGreater(len(ok), 0)           # 중단되지 않고 끝까지 간다

    def test_빈_입력은_호출하지_않는다(self):
        calls = []

        def submit(chunk):
            calls.append(len(chunk))
            return True, ""

        ok, bad, err = run_names._rename_cascade([], submit)

        self.assertEqual((ok, bad, err, calls), ([], [], [], []))


class StatusColumnTest(unittest.TestCase):
    """F2 — 상태열 write back (행 단위 update 금지, 열 한 번에)."""

    I_ID = 0
    I_STATUS = 3

    def _rows(self):
        # [상품id, ..., ..., 상태]
        return [
            ["P001", "x", "y", "생성완료"],
            ["P002", "x", "y", "생성완료"],
            ["P003", "x", "y", "생성완료"],
            ["P004", "x", "y", "보류"],
            ["", "", "", ""],
        ]

    def test_성공은_반영완료_확정불량은_상품삭제로_바뀐다(self):
        col, n = run_names._build_status_col(
            self._rows(), self.I_ID, self.I_STATUS,
            ok_ids={"P001", "P002"}, bad_ids={"P003"})

        self.assertEqual(col, [["반영완료"], ["반영완료"], ["상품삭제(이룸님)"],
                               ["보류"], [""]])
        self.assertEqual(n, 3)

    def test_대상이_아닌_행의_기존_상태는_보존한다(self):
        col, n = run_names._build_status_col(
            self._rows(), self.I_ID, self.I_STATUS,
            ok_ids=set(), bad_ids=set())

        self.assertEqual(col, [["생성완료"], ["생성완료"], ["생성완료"],
                               ["보류"], [""]])
        self.assertEqual(n, 0)

    def test_상태칸이_잘린_짧은_행도_인덱스_에러_없이_처리한다(self):
        """시트는 뒤쪽 빈 칸을 잘라 보낸다. 상태칸이 없는 행은 생성완료가
        아니므로 손대지 않고, 그 아래 정상 행은 정상 처리돼야 한다."""
        rows = [["P001", "x"], ["P002"], ["P003", "x", "y", "생성완료"]]
        col, n = run_names._build_status_col(
            rows, self.I_ID, self.I_STATUS,
            ok_ids={"P001", "P003"}, bad_ids=set())

        self.assertEqual(col, [[""], [""], ["반영완료"]])
        self.assertEqual(n, 1)

    def test_생성완료가_아닌_행은_같은_상품id여도_건드리지_않는다(self):
        """반영 대상은 상태=생성완료 행뿐이다. 같은 id의 보류·스킵 행까지
        덮으면 기록이 사라진다(중복 행이 있을 때의 안전장치)."""
        rows = [
            ["P001", "x", "y", "생성완료"],
            ["P001", "x", "y", "보류(검증실패)"],
            ["P003", "x", "y", "스킵(카테고리미설정)"],
        ]
        col, n = run_names._build_status_col(
            rows, self.I_ID, self.I_STATUS,
            ok_ids={"P001"}, bad_ids={"P003"})

        self.assertEqual(col, [["반영완료"], ["보류(검증실패)"],
                               ["스킵(카테고리미설정)"]])
        self.assertEqual(n, 1)

    def test_이미_반영완료인_행은_재실행해도_변경으로_세지_않는다(self):
        rows = [["P001", "x", "y", "반영완료"]]
        col, n = run_names._build_status_col(
            rows, self.I_ID, self.I_STATUS, ok_ids={"P001"}, bad_ids=set())

        self.assertEqual(col, [["반영완료"]])
        self.assertEqual(n, 0)

    def test_오류건은_생성완료로_남겨_재실행에서_다시_잡히게_한다(self):
        col, n = run_names._build_status_col(
            self._rows(), self.I_ID, self.I_STATUS,
            ok_ids={"P001"}, bad_ids=set())

        self.assertEqual(col[1], ["생성완료"])  # P002 = 오류건 → 그대로
        self.assertEqual(n, 1)


class WritebackTest(unittest.TestCase):
    """상태열 되쓰기 — 시트 호출은 딱 1회여야 한다(320행 × 1회 update 금지)."""

    def setUp(self):
        self.calls = []

    def _update(self, sheet, rng, values):
        self.calls.append((sheet, rng, values))
        return {}

    def _rows(self, n=320):
        i_status = run_names.NAME_HEADER.index("상태")
        rows = []
        for i in range(n):
            r = [""] * len(run_names.NAME_HEADER)
            r[0] = f"P{i:03d}"
            r[i_status] = "생성완료"
            rows.append(r)
        return rows

    def test_320행이어도_update_는_한_번만_친다(self):
        rows = self._rows(320)
        n = run_names._writeback_status(
            "SHEET1", "상품명", rows,
            ok_ids={f"P{i:03d}" for i in range(318)},
            bad_ids={"P318", "P319"},
            update=self._update)

        self.assertEqual(n, 320)
        self.assertEqual(len(self.calls), 1)
        sheet, rng, values = self.calls[0]
        self.assertEqual(sheet, "SHEET1")
        self.assertEqual(rng, "'상품명'!Z2:Z321")   # 헤더 1행 + 320행
        self.assertEqual(len(values), 320)
        self.assertEqual(values[0], ["반영완료"])
        self.assertEqual(values[-1], ["상품삭제(이룸님)"])

    def test_변경할_게_없으면_시트를_건드리지_않는다(self):
        n = run_names._writeback_status(
            "SHEET1", "상품명", self._rows(5),
            ok_ids=set(), bad_ids=set(), update=self._update)

        self.assertEqual(n, 0)
        self.assertEqual(self.calls, [])

    def test_시트_쓰기_실패는_예외로_터지지_않고_0을_반환한다(self):
        def boom(*a, **k):
            raise RuntimeError("gws 응답 없음")

        n = run_names._writeback_status(
            "SHEET1", "상품명", self._rows(3),
            ok_ids={"P000"}, bad_ids=set(), update=boom)

        self.assertEqual(n, 0)


class ColLetterTest(unittest.TestCase):
    def test_26열_초과도_A1_문자로_변환한다(self):
        f = run_names._col_letter
        self.assertEqual([f(1), f(26), f(27), f(52), f(53)],
                         ["A", "Z", "AA", "AZ", "BA"])

    def test_상태열은_현재_헤더에서_Z열이다(self):
        i = run_names.NAME_HEADER.index("상태")
        self.assertEqual(run_names._col_letter(i + 1), "Z")


class AttrTagColumnTest(unittest.TestCase):
    """2026-07-27 헤르메스 02 흡수 — 속성제안·태그제안 2열을 뒤에 붙였다."""

    def test_헤더는_29열이고_속성_태그가_맨_뒤다(self):
        self.assertEqual(len(run_names.NAME_HEADER), 29)
        self.assertEqual(run_names.NAME_HEADER[-2:], ["속성제안", "태그제안"])

    def test_뒤에_붙였으므로_기존_열_위치는_안_밀린다(self):
        """상태열이 Z에서 밀리면 rename 의 상태 write back 이 엉뚱한 열을 친다."""
        h = run_names.NAME_HEADER
        self.assertEqual(h.index("상품id"), 0)
        self.assertEqual(h.index("원본상품명"), 4)
        self.assertEqual(run_names._col_letter(h.index("상태") + 1), "Z")
        self.assertEqual(run_names._col_letter(len(h)), "AC")

    def test_속성_태그가_없는_구버전_결과도_29열을_만든다(self):
        row = run_names._build_row({"productId": "P1", "새상품명": "x"}, "g")
        self.assertEqual(len(row), len(run_names.NAME_HEADER))
        self.assertEqual(row[-2:], ["", ""])

    def test_리스트로_와도_문자열로_와도_받는다(self):
        j = run_names._joinlist
        self.assertEqual(j(["가", "나"]), "가, 나")
        self.assertEqual(j("가"), "가")
        self.assertEqual(j(None), "")
        self.assertEqual(j([]), "")
        self.assertEqual(j(["가", "", "  ", "나"]), "가, 나")  # 빈 항목은 버린다


class ExtendHeaderTest(unittest.TestCase):
    """기존 27열 시트에 AB·AC 헤더를 1회 채우는 경로.

    `ensure_tab` 은 탭이 없을 때만 헤더를 쓴다 — 기존 그룹 시트는 이 경로가 유일하다.
    """

    def _patch(self, cur, monkey):
        """sheets_get/sheets_update 를 가짜로 갈아끼운다."""
        import eroomlib.gsheets as g
        orig = (g.sheets_get, g.sheets_update)
        g.sheets_get = lambda s, r: [list(cur)]
        g.sheets_update = lambda s, r, v: monkey.append((r, v))
        self.addCleanup(lambda: setattr(g, "sheets_get", orig[0]))
        self.addCleanup(lambda: setattr(g, "sheets_update", orig[1]))

    def test_짧은_헤더면_빠진_열만_뒤에_채운다(self):
        wrote = []
        self._patch(run_names.NAME_HEADER[:27], wrote)
        run_names._extend_header("SHEET", "상품명", run_names.NAME_HEADER)
        self.assertEqual(len(wrote), 1)
        rng, values = wrote[0]
        self.assertEqual(rng, "'상품명'!AB1")
        self.assertEqual(values, [["속성제안", "태그제안"]])

    def test_이미_29열이면_아무것도_쓰지_않는다(self):
        wrote = []
        self._patch(run_names.NAME_HEADER, wrote)
        run_names._extend_header("SHEET", "상품명", run_names.NAME_HEADER)
        self.assertEqual(wrote, [])

    def test_앞_열이_다르면_손대지_않는다(self):
        """열 순서가 어긋난 시트를 덮어쓰면 되돌릴 수 없다 — 사람이 보게 둔다."""
        wrote = []
        self._patch(["엉뚱한열"] + run_names.NAME_HEADER[1:27], wrote)
        run_names._extend_header("SHEET", "상품명", run_names.NAME_HEADER)
        self.assertEqual(wrote, [])


class PooledModeTest(unittest.TestCase):
    """풀링 모드(--targets-json / --sheet-map) 헬퍼 — 대량다듬기 M3b."""

    def test_targets_json_주입은_그룹조회를_건너뛴다(self):
        with tempfile.TemporaryDirectory() as d:
            tj = os.path.join(d, "targets.json")
            with open(tj, "w", encoding="utf-8") as f:
                json.dump({"작업": "상품명", "targets": [
                    {"productId": "P1", "그룹명": "1번_테스트",
                     "groupId": 11, "코드": "tb:1"}]}, f, ensure_ascii=False)
            pending = run_names._load_pooled_targets(tj)
            self.assertEqual([p["productId"] for p in pending], ["P1"])
            self.assertEqual(pending[0]["상품명"], "")  # 실명은 workdata(스냅샷)가 채운다

    def test_sheet_map_라우팅은_상품을_소속_시트로_묶는다(self):
        sm = {"P1": {"sheet": "S_A", "그룹명": "A"}, "P2": {"sheet": "S_B", "그룹명": "B"},
              "P3": {"sheet": "S_A", "그룹명": "A"}}
        grouped = run_names._route_by_sheet(
            {"P1": ["P1행"], "P2": ["P2행"], "P3": ["P3행"]}, sm)
        self.assertEqual(grouped, {"S_A": [["P1행"], ["P3행"]], "S_B": [["P2행"]]})

    def test_sheet_map에_없는_상품은_라우팅에서_명시적으로_실패한다(self):
        with self.assertRaises(RuntimeError) as cm:
            run_names._route_by_sheet({"PX": ["행"]}, {})
        self.assertIn("PX", str(cm.exception))  # 조용히 엉뚱한 시트에 쓰면 로그 오염

    def test_targets_json과_ids를_같이_주면_거부한다(self):
        # 피어리뷰 지적: --targets-json 은 --ids/--redo/--group-id 와 조용히 섞이면
        # 안 된다(대표 목록과 애드혹 단건 경로가 뒤섞여 의도치 않은 범위로 처리될 위험).
        with tempfile.TemporaryDirectory() as d:
            args = argparse.Namespace(
                run_dir=d, views_only=False, targets_json="t.json", sheet_map="s.json",
                group_id=None, ids=["P1"], redo=False)
            with self.assertRaises(RuntimeError) as cm:
                run_names.cmd_prep(args)
            self.assertIn("--targets-json", str(cm.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
