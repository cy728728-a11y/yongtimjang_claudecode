#!/usr/bin/env python3
"""run_names.py rename 경로 회귀 테스트 (stdlib unittest — pytest 불필요).

실행: python test_run_names.py   (또는 python -m unittest test_run_names -v)

대상은 2026-07-27 용쌤1-1 실측 결함 2개:
  F1 배치 거부 시 재시도가 없어 불량 1건이 정상 49건을 같이 죽인다
  F2 반영 결과를 시트 상태열에 되쓰지 않는다
"""
import argparse
import contextlib
import glob
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

for _s in (sys.stdout, sys.stderr):  # 콘솔 cp949 에서 한글 테스트명이 깨지지 않게
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

import run_names  # noqa: E402
import name_check  # noqa: E402  (BASE_SUFFIX = 마커의 단일 출처)


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


class RenameIdsFilterTest(unittest.TestCase):
    """--ids 필터 — propagate 가 자기 append 분만 rename 대상으로 잡게 하는
    승인 게이트 가드(피어리뷰 #9). commit=False 경로만 확인(MCP 미호출)."""

    def _rows(self):
        h = run_names.NAME_HEADER
        i_id, i_orig = h.index("상품id"), h.index("원본상품명")
        i_new, i_status = h.index("새상품명"), h.index("상태")

        def row(pid, status="생성완료"):
            r = [""] * len(h)
            r[i_id], r[i_orig], r[i_new], r[i_status] = pid, "원본", "새이름", status
            return r

        return [row("P001"), row("P002"), row("P003"), row("P004", status="보류")]

    def _patch_sheet(self, rows):
        import eroomlib.gsheets as g
        orig = g.sheets_get
        g.sheets_get = lambda s, r: rows
        self.addCleanup(lambda: setattr(g, "sheets_get", orig))

    def _run(self, ids=None):
        args = argparse.Namespace(sheet="SHEET", tab=run_names.NAME_TAB,
                                   commit=False, limit=None, ids=ids)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            run_names.cmd_rename(args)
        return buf.getvalue()

    def test_ids_지정시_해당_pid만_대상이_된다(self):
        self._patch_sheet(self._rows())
        out = self._run(ids=["P002"])
        self.assertIn("반영 대상: 1건", out)
        self.assertIn("P002", out)
        self.assertNotIn("P001", out)
        self.assertNotIn("P003", out)

    def test_ids_미지정시_기존과_동일한_대상이_된다(self):
        """생성완료 3건(P001~P003) 그대로 — 보류(P004)는 원래도 제외."""
        self._patch_sheet(self._rows())
        out = self._run(ids=None)
        self.assertIn("반영 대상: 3건", out)
        for pid in ("P001", "P002", "P003"):
            self.assertIn(pid, out)

    def test_시트에_없는_pid를_줘도_에러_없이_대상_0건이_된다(self):
        self._patch_sheet(self._rows())
        out = self._run(ids=["P999"])
        self.assertIn("반영 대상: 0건", out)

    def test_ids에_있어도_생성완료가_아니면_대상에서_빠진다(self):
        """--ids 는 상태=생성완료 필터 위에 얹는 추가 필터일 뿐,
        상태 조건 자체를 우회하면 안 된다."""
        self._patch_sheet(self._rows())
        out = self._run(ids=["P004"])
        self.assertIn("반영 대상: 0건", out)


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
    """뒤에 붙인 열들 — 속성제안·태그제안(2026-07-27) + 대표지정(2026-08-05).

    새 열은 **항상 맨 뒤에만** 붙인다. 앞 열이 밀리면 rename 의 상태 write back 이
    엉뚱한 열을 친다(상태 = Z 고정).
    """

    def test_헤더는_30열이고_새_열들이_맨_뒤다(self):
        self.assertEqual(len(run_names.NAME_HEADER), 30)
        self.assertEqual(run_names.NAME_HEADER[-3:],
                         ["속성제안", "태그제안", "대표지정"])

    def test_뒤에_붙였으므로_기존_열_위치는_안_밀린다(self):
        """상태열이 Z에서 밀리면 rename 의 상태 write back 이 엉뚱한 열을 친다."""
        h = run_names.NAME_HEADER
        self.assertEqual(h.index("상품id"), 0)
        self.assertEqual(h.index("원본상품명"), 4)
        self.assertEqual(run_names._col_letter(h.index("상태") + 1), "Z")
        self.assertEqual(run_names._col_letter(len(h)), "AD")

    def test_속성_태그가_없는_구버전_결과도_전체_열을_만든다(self):
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
        self.assertEqual(values, [["속성제안", "태그제안", "대표지정"]])

    def test_이미_전체_열이면_아무것도_쓰지_않는다(self):
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


def _snap(rows):
    """스냅샷 레코드 흉내 — 판매행만 있으면 된다."""
    return {"옵션": {"차원": [], "판매행": rows, "vid고유": True}}


def _row(rid, price, exclude=False, main=False, text=""):
    return {"id": rid, "text": text or f"opt{rid}", "sale_price": price,
            "stock": 10, "exclude": exclude, "main_product": main}


class SamePriceOptionTest(unittest.TestCase):
    """색상 예외 규칙의 근거 — 워커는 옵션 가격을 못 보므로 prep 이 계산한다."""

    def _f(self, rec):
        return run_names._same_price_options("P1", load=lambda _pid: rec)

    def test_전부_동가면_참이다(self):
        self.assertTrue(self._f(_snap([_row("1", 9900), _row("2", 9900),
                                       _row("3", 9900)])))

    def test_하나라도_다르면_거짓이다(self):
        self.assertFalse(self._f(_snap([_row("1", 9900), _row("2", 12000)])))

    def test_제외행은_보지_않는다(self):
        # 판매에서 빠진 행의 가격은 고객이 보는 추가금과 무관하다
        self.assertTrue(self._f(_snap([_row("1", 9900), _row("2", 9900),
                                       _row("3", 50000, exclude=True)])))

    def test_판매행이_1개면_거짓이다(self):
        # 구분할 대상이 없으면 색상을 생략할 이유도 없다
        self.assertFalse(self._f(_snap([_row("1", 9900)])))

    def test_가격이_비면_보수적으로_거짓이다(self):
        self.assertFalse(self._f(_snap([_row("1", 9900), _row("2", None)])))

    def test_옵션이_없으면_거짓이다(self):
        self.assertFalse(self._f({}))

    def test_스냅샷_읽기가_터져도_prep_을_멈추지_않는다(self):
        def boom(_pid):
            raise OSError("깨진 스냅샷")
        self.assertFalse(run_names._same_price_options("P1", load=boom))


class FlipSuspectHandoffTest(unittest.TestCase):
    """보류(옵션뒤집힘)을 옵션 열 재작업 flag 로 넘긴다 (2026-08-06 슬링랙/풋패드 사례)."""

    def setUp(self):
        self.calls = []
        self.tmp = tempfile.mkdtemp()
        self.checked = os.path.join(self.tmp, "checked")
        os.makedirs(self.checked)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _flag(self, sheet, task, items, from_task=None):
        self.calls.append((sheet, task, dict(items), from_task))
        return len(items)

    def _write(self, products):
        with open(os.path.join(self.checked, "checked_001.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"products": products}, f, ensure_ascii=False)

    def test_뒤집힘_보류만_옵션_열에_찍는다(self):
        self._write([
            {"productId": "P1", "상태": "보류(옵션뒤집힘)",
             "메모": "본품(데드리프트랙) 전부 제외, 판매중은 풋패드뿐"},
            {"productId": "P2", "상태": "생성완료", "새상품명": "정상 상품"},
            {"productId": "P3", "상태": "보류(키워드부족)"},
        ])
        n = run_names._handoff_flip_suspect("SHEET", self.checked, flag=self._flag)
        self.assertEqual(n, 1)
        sheet, task, items, from_task = self.calls[0]
        self.assertEqual((sheet, task, from_task), ("SHEET", "옵션", "상품명"))
        self.assertEqual(list(items), ["P1"])
        self.assertIn("풋패드", items["P1"])

    def test_메모가_비면_기본_사유를_쓴다(self):
        self._write([{"productId": "P1", "상태": "보류(옵션뒤집힘)", "메모": ""}])
        run_names._handoff_flip_suspect("SHEET", self.checked, flag=self._flag)
        self.assertEqual(self.calls[0][2]["P1"], "본품 전부 판매제외 의심")

    def test_대상이_없으면_flag를_부르지_않는다(self):
        self._write([{"productId": "P1", "상태": "생성완료", "새상품명": "정상"}])
        self.assertEqual(
            run_names._handoff_flip_suspect("SHEET", self.checked, flag=self._flag), 0)
        self.assertEqual(self.calls, [])

    def test_flag_실패는_append_결과를_뒤엎지_않는다(self):
        self._write([{"productId": "P1", "상태": "보류(옵션뒤집힘)", "메모": "x"}])
        def boom(*a, **k):
            raise RuntimeError("gws 응답 없음")
        self.assertEqual(
            run_names._handoff_flip_suspect("SHEET", self.checked, flag=boom), 0)


class CatfixAlreadyCorrectTest(unittest.TestCase):
    """③b 무키워드 경로의 게이트 — 재교정이 `이미정확` 이라 답한 건만 (2026-08-07).

    `이미정확` = 카테고리는 맞다. 그런데도 뷰에 직결어가 0이면 재교정을 또 돌려도 안 나온다
    (통다운에 그 카테고리 키워드가 없는 것) → 무키워드로 짓는다. 경로가 바뀐 건은
    아직 카테고리 쪽에 할 일이 남았으므로 여기 끼면 안 된다.
    """

    def _mk(self, rows):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "decisions.json"), "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False)
        return d

    def test_이미정확만_고른다(self):
        d = self._mk([{"productId": "P1", "상태": "이미정확"},
                      {"productId": "P2", "상태": "자동저장완료"},
                      {"productId": "P3", "상태": "이미정확"},
                      {"productId": "P4", "상태": "변경대상"}])
        self.assertEqual(run_names._catfix_already_correct(d), {"P1", "P3"})

    def test_decisions_가_없으면_빈_집합(self):
        """분류를 못 해도 죽지 않는다 — 무키워드 대상이 0이 되어 전부 수동큐로 간다."""
        self.assertEqual(run_names._catfix_already_correct(tempfile.mkdtemp()), set())

    def test_productId_없는_행은_버린다(self):
        d = self._mk([{"상태": "이미정확"}, {"productId": "P9", "상태": "이미정확"}])
        self.assertEqual(run_names._catfix_already_correct(d), {"P9"})


class RedoExemptTest(unittest.TestCase):
    """`redo.json` 면제 목록 — prep → append 로 넘어가는 A열 중복 면제 (2026-08-07).

    발단: 이 목록을 `auto_redo` 가 있을 때만 썼더니, 현황판 flag 없는 `--ids --redo`
    회차가 append 에서 전건 `스킵(이미처리)` 로 버려졌다(3-2 재교정 11건 — 워커 비용을
    다 쓰고 시트 0행). 두 출처는 독립이라 **한쪽만 있어도 파일이 나와야 한다.**
    """

    def test_현황판_편입이_없어도_redo_ids_는_남는다(self):
        self.assertEqual(run_names._redo_exempt({"P1", "P2"}, {}), ["P1", "P2"])

    def test_ids_가_없어도_현황판_편입은_남는다(self):
        self.assertEqual(run_names._redo_exempt(set(), {"P3": "사유"}), ["P3"])

    def test_두_출처를_합치고_중복을_없앤다(self):
        self.assertEqual(run_names._redo_exempt({"P1", "P3"}, {"P3": "사유", "P2": "사유"}),
                         ["P1", "P2", "P3"])

    def test_둘_다_비면_빈_목록(self):
        self.assertEqual(run_names._redo_exempt(set(), {}), [])
        self.assertEqual(run_names._redo_exempt(None, None), [])


class MatrixRedoTest(unittest.TestCase):
    """현황판 `상품명` 재작업 자동 편입 (2026-08-06 — 옵션이 되돌려 보낸 건)."""

    M = {
        "P1": {"row": 2, "상품명": "재작업(옵션: 상품명 10인치인데 원문은 8인치)"},
        "P2": {"row": 3, "상품명": "완료"},
        "P3": {"row": 4, "상품명": ""},
        "P4": {"row": 5, "상품명": "재작업(옵션: 대표충돌)"},
    }

    def test_재작업이면서_이미_시트에_있는_것만_집는다(self):
        # 빈칸(P3)은 어차피 대상이라 편입할 게 없고, 완료(P2)는 다시 할 이유가 없다.
        got = run_names._matrix_redo("SHEET", {"P1", "P2", "P4"},
                                     read=lambda s: self.M)
        self.assertEqual(sorted(got), ["P1", "P4"])
        self.assertIn("8인치", got["P1"])

    def test_후보가_비면_시트를_읽지도_않는다(self):
        def boom(_sheet):
            raise AssertionError("읽으면 안 된다")
        self.assertEqual(run_names._matrix_redo("SHEET", set(), read=boom), {})

    def test_현황판을_못_읽어도_prep을_멈추지_않는다(self):
        def boom(_sheet):
            raise RuntimeError("gws 응답 없음")
        self.assertEqual(run_names._matrix_redo("SHEET", {"P1"}, read=boom), {})


class RedoCandidatesTest(unittest.TestCase):
    """사유를 물어볼 후보 집합 — `--ids --redo` 가 자동 편입을 죽이던 버그 (2026-08-14).

    발단: prep 이 `done_ids - want` 를 먼저 해서, 손으로 지목한 재작업이 후보에서
    빠졌다. 사유가 안 실리니 재작업 라운드가 첫 라운드와 같은 이름을 다시 만들었다.
    """

    def test_수동_지목분도_후보에_남는다(self):
        # `--redo` 가 done_ids 에서 뺀 뒤라도 redo_hit 로 되살아나야 한다.
        got = run_names._redo_candidates({"P1", "P2"}, {"P2"}, {"P1"})
        self.assertEqual(got, {"P1", "P2"})

    def test_자동_편입_경로는_그대로다(self):
        self.assertEqual(run_names._redo_candidates({"P1", "P2"}, {"P1"}, set()), {"P1"})

    def test_시트에_없는_신규는_후보가_아니다(self):
        # 빈칸은 어차피 대상이라 사유를 물어볼 것이 없다.
        self.assertEqual(run_names._redo_candidates({"P9"}, set(), set()), set())

    def test_그룹_밖_id는_redo_hit_라도_들어오지_않는다(self):
        # redo_hit 는 `--ids` 를 그룹과 교집합하기 전에 잡혀 그룹 밖 id 가 섞일 수 있다
        # (2-3 실측: 다른 마켓그룹으로 옮겨간 상품). 그건 pending 에 없어 실을 자리가 없다.
        got = run_names._redo_candidates({"P1"}, {"P1"}, {"P1", "P_다른그룹"})
        self.assertEqual(got, {"P1"})

    def test_빈_입력(self):
        self.assertEqual(run_names._redo_candidates(set(), set(), None), set())


class AuditNamedTest(unittest.TestCase):
    """append 감사 — 워커 산출물 ↔ 배치 정본 대조 (2026-08-15 용쌤4-1 사고).

    옵션정리 apply 에는 이 감사가 있어 잘린 id 가 `--commit` 을 막았는데,
    상품명 append 에는 없어서 26자 짜리 id 가 그대로 시트 A열에 들어갔다.
    """

    P1 = "U01KSER86W5QCP907SEXBMFQP4W"   # 27자 (정상)
    P2 = "U01KSER86WGCHX4DQ09JC6QWZ2J"

    def setUp(self):
        self.d = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.d, "batches"))
        os.makedirs(os.path.join(self.d, "named"))
        self.addCleanup(shutil.rmtree, self.d, True)

    def _batch(self, n, pids):
        run_names._dump(os.path.join(self.d, "batches", f"batch_{n:03d}.json"),
                        {"products": [{"productId": p} for p in pids]})

    def _named(self, n, pids):
        run_names._dump(os.path.join(self.d, "named", f"named_{n:03d}.json"),
                        {"batch": n, "products": [{"productId": p} for p in pids]})

    def _ids(self, n):
        doc = run_names._load(os.path.join(self.d, "named", f"named_{n:03d}.json"))
        return [p["productId"] for p in doc["products"]]

    def test_가운데_글자가_빠진_id를_고친다(self):
        # 4-1 상품명 실측: …BMFQP4W(27) → …BMFQ4W(26). 접두 매칭으로는 안 잡힌다.
        self._batch(1, [self.P1]); self._named(1, ["U01KSER86W5QCP907SEXBMFQ4W"])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            warns, missing, fixed = run_names._audit_named(self.d)
        self.assertEqual((warns, missing, fixed), ([], False, 1))
        self.assertEqual(self._ids(1), [self.P1])

    def test_뒤가_잘린_id를_고친다(self):
        # 4-1 옵션 실측: …JC6QWZ2J(27) → …JC6QW(24)
        self._batch(2, [self.P2]); self._named(2, ["U01KSER86WGCHX4DQ09JC6QW"])
        with contextlib.redirect_stdout(io.StringIO()):
            warns, missing, fixed = run_names._audit_named(self.d)
        self.assertEqual((warns, missing, fixed), ([], False, 1))
        self.assertEqual(self._ids(2), [self.P2])

    def test_후보가_둘이면_손대지_않고_보고한다(self):
        a, b = "U01AAAAAAAAAAAAAAAAAAAAAAAX", "U01AAAAAAAAAAAAAAAAAAAAAAAY"
        self._batch(3, [a, b]); self._named(3, ["U01AAAAAAAAAAAAAAAAAAAAAAA"])
        with contextlib.redirect_stdout(io.StringIO()):
            warns, missing, fixed = run_names._audit_named(self.d)
        self.assertEqual(fixed, 0)
        self.assertTrue(missing)
        self.assertTrue(any("미지의 상품id" in w for w in warns))

    def test_누락은_append를_막는_신호로_보고한다(self):
        self._batch(4, [self.P1, self.P2]); self._named(4, [self.P1])
        with contextlib.redirect_stdout(io.StringIO()):
            warns, missing, fixed = run_names._audit_named(self.d)
        self.assertTrue(missing)
        self.assertTrue(any("누락 상품 1건" in w for w in warns))
        self.assertTrue(any("미완 배치" in w for w in warns))

    def test_정상이면_조용하다(self):
        self._batch(5, [self.P1, self.P2]); self._named(5, [self.P1, self.P2])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(run_names._audit_named(self.d), ([], False, 0))

    def test_배치가_없는_구형_run_dir는_통과시킨다(self):
        shutil.rmtree(os.path.join(self.d, "batches"))
        self.assertEqual(run_names._audit_named(self.d), ([], False, 0))


class DropGoneTest(unittest.TestCase):
    """삭제대기 게이트 (2026-08-15 용쌤4-1 사고).

    prep 의 멱등 판정은 `상품명` 탭 A열 기준인데 삭제대기는 현황판에만 찍힌다 —
    두 저장소가 어긋나 삭제 예정 상품 137/227건이 대상에 들어갔고 93건이 rename 됐다.
    """

    M = {
        # 상품명 열은 멀쩡한데 다른 열이 삭제대기 → 잡아야 한다(4-1 에서 실제로 이 모양이었다)
        "GONE1": {"row": 2, "상품명": "", "옵션": "삭제대기(제외카테고리)",
                  "썸네일": "삭제대기(제외카테고리)", "상세": "삭제대기(제외카테고리)"},
        # 이미 지운 상품
        "GONE2": {"row": 3, "상품명": "상품삭제(이룸님)", "옵션": "해당없음",
                  "썸네일": "해당없음"},
        # 정상 대상
        "LIVE": {"row": 4, "상품명": "", "옵션": "완료", "썸네일": ""},
        # 재작업도 정상 대상이다 — 게이트가 이걸 먹으면 안 된다
        "REDO": {"row": 5, "상품명": "재작업(옵션: 대표충돌)", "옵션": "완료", "썸네일": ""},
    }

    def _pend(self, *ids):
        return [{"productId": i} for i in ids]

    def test_한_열만_삭제대기여도_뺀다(self):
        kept, gone = run_names._drop_gone(
            self._pend("GONE1", "LIVE", "GONE2", "REDO"), self.M)
        self.assertEqual([g["productId"] for g in kept], ["LIVE", "REDO"])
        self.assertEqual(gone, ["GONE1", "GONE2"])

    def test_현황판에_없는_상품은_남긴다(self):
        # 신규 수집분은 아직 현황판에 행이 없다 — 게이트가 이걸 지우면 안 된다.
        kept, gone = run_names._drop_gone(self._pend("NEW"), self.M)
        self.assertEqual([g["productId"] for g in kept], ["NEW"])
        self.assertEqual(gone, [])

    def test_현황판을_못_읽으면_경고하고_아무것도_안_뺀다(self):
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            kept, gone = run_names._drop_gone(self._pend("GONE1", "LIVE"), {})
        self.assertEqual(len(kept), 2)
        self.assertEqual(gone, [])
        self.assertIn("게이트를 걸지 못했습니다", buf.getvalue())


class MarkGoneColumnTest(unittest.TestCase):
    """`_drop_gone` 이 뺀 건의 `상품명` 열 되찍기 (2026-08-17 25-2 실측).

    게이트는 워커 비용을 막아주지만 현황판 pending 은 안 비워준다 — 25-2 에서
    pending 54건 중 18건이 "이미 삭제됐는데 상품명 열만 안 찍힌" 건이었고,
    회차마다 남은 일감으로 다시 세어져 인계문서가 실제 작업량을 잘못 적었다.
    """

    M = {
        # 상품명 열이 빈칸 + 다른 열은 삭제 → 그 값을 그대로 복사해 찍는다
        "G1": {"row": 2, "상품명": "", "옵션": "상품삭제(제외카테고리·자동)",
               "썸네일": "상품삭제(제외카테고리·자동)"},
        # 재작업이 찍혀 있어도 실물이 없으면 마킹 대상이다
        "G2": {"row": 3, "상품명": "재작업(카테고리: 카테고리 변경)",
               "옵션": "상품삭제(옵션: 품목불일치·자동)"},
        # 이미 삭제 표시가 있다 → 건드리지 않는다
        "G3": {"row": 4, "상품명": "상품삭제(이룸님)", "옵션": "해당없음"},
        # 작업이 진행 중인 값이 들어 있다 → 덮어쓰지 않는다
        "G4": {"row": 5, "상품명": "진행중(미반영)", "옵션": "삭제대기(제외카테고리)"},
    }

    def _run(self, ids):
        seen = {}

        def _mark(sheet, col, tgt):
            seen.update({"sheet": sheet, "col": col, "tgt": dict(tgt)})

        n = run_names._mark_gone_column("SHEET", self.M, ids, mark=_mark)
        return n, seen

    def test_빈칸이면_다른_열의_삭제사유를_그대로_복사한다(self):
        n, seen = self._run(["G1"])
        self.assertEqual(n, 1)
        self.assertEqual(seen["col"], "상품명")
        self.assertEqual(seen["tgt"], {"G1": "상품삭제(제외카테고리·자동)"})

    def test_재작업이_찍혀_있어도_마킹한다(self):
        n, seen = self._run(["G2"])
        self.assertEqual(seen["tgt"], {"G2": "상품삭제(옵션: 품목불일치·자동)"})

    def test_이미_삭제표시가_있으면_건드리지_않는다(self):
        n, seen = self._run(["G3"])
        self.assertEqual(n, 0)
        self.assertEqual(seen, {})

    def test_진행중_같은_값은_덮어쓰지_않는다(self):
        # 사람이나 다른 단계가 쓴 값을 게이트가 지우면 안 된다.
        n, _ = self._run(["G4"])
        self.assertEqual(n, 0)

    def test_시트가_없으면_아무것도_안_한다(self):
        self.assertEqual(run_names._mark_gone_column("", self.M, ["G1"]), 0)


class DropStaleJkTest(unittest.TestCase):
    """상품id 재할당으로 다른 상품 것이 된 J열 격리 (2026-08-17 25-2 실측).

    카테고리교정 시트의 상품명과 현황판 상품명이 완전히 다른 행이 162건 있었고,
    그대로 믿으면 모니터 받침대에 소파 이름이 붙는다.
    """

    M = {
        "OK1": {"row": 2, "상품": "스탠딩 모니터 받침대 높이조절"},
        "BAD": {"row": 3, "상품": "스탠딩 모니터 받침대 높이조절"},
        "SPACE": {"row": 4, "상품": "곰돌이전신거울 미용실"},
        "NOROW": {"row": 5, "상품": ""},
    }

    def _jk(self):
        return {
            "OK1": {"실물판정": "모니터 받침대", "썸네일URL": "u1",
                    "시트상품명": "모니터 받침대 높이조절 스탠드"},
            # 같은 id 인데 시트는 소파라고 한다 = 재할당
            "BAD": {"실물판정": "2인용 패브릭 소파", "썸네일URL": "u2",
                    "시트상품명": "2인용 인테리어 쇼파 패브릭 클라우드"},
            # 띄어쓰기만 다른 같은 물건 — 버리면 안 된다
            "SPACE": {"실물판정": "곰돌이 전신거울", "썸네일URL": "u3",
                      "시트상품명": "곰돌이 전신거울 피팅 드레스룸"},
            # 현황판 상품명이 비어 판정 불가 — 그대로 둔다
            "NOROW": {"실물판정": "무언가", "썸네일URL": "u4", "시트상품명": "다른 무언가"},
        }

    def test_다른_상품_것이면_J와_K를_모두_버린다(self):
        jk, stale = run_names._drop_stale_jk(self._jk(), self.M)
        self.assertEqual([p for p, _, _ in stale], ["BAD"])
        self.assertEqual(jk["BAD"]["실물판정"], "")
        self.assertEqual(jk["BAD"]["썸네일URL"], "")   # 행 자체가 남의 것이라 K도 못 믿는다
        self.assertTrue(jk["BAD"]["대조불일치"])

    def test_같은_물건이면_유지한다(self):
        jk, stale = run_names._drop_stale_jk(self._jk(), self.M)
        self.assertEqual(jk["OK1"]["실물판정"], "모니터 받침대")
        self.assertEqual(jk["SPACE"]["실물판정"], "곰돌이 전신거울")
        self.assertNotIn("SPACE", [p for p, _, _ in stale])

    def test_한쪽이_비면_판정하지_않는다(self):
        jk, stale = run_names._drop_stale_jk(self._jk(), self.M)
        self.assertEqual(jk["NOROW"]["실물판정"], "무언가")

    def test_현황판에_행이_없으면_그대로_둔다(self):
        jk, stale = run_names._drop_stale_jk(self._jk(), {})
        self.assertEqual(stale, [])
        self.assertEqual(jk["BAD"]["실물판정"], "2인용 패브릭 소파")

    def test_J와_K가_둘_다_비면_대조하지_않는다(self):
        jk, stale = run_names._drop_stale_jk(
            {"BAD": {"실물판정": "", "썸네일URL": "", "시트상품명": "전혀 다른 물건"}},
            self.M)
        self.assertEqual(stale, [])


class RecoverGroupOrphansTest(unittest.TestCase):
    """그룹 목록이 빠뜨린 미아 편입 (2026-08-17 25-2 실측).

    불사자 그룹 목록 API 가 살아 있는 상품을 빠뜨려 13건이 어느 회차도 안 집혔다.
    옵션정리엔 같은 장치가 있는데 이 축에만 없었다.
    """

    M = {
        "IN": {"row": 2, "상품": "그룹에 있는 상품", "상품명": "", "옵션": "완료"},
        "ORPH": {"row": 3, "상품": "미아 상품", "상품명": "", "옵션": "완료",
                 "썸네일": "완료"},
        "ORPH2": {"row": 4, "상품": "미아 재작업", "상품명": "재작업(옵션: 뒤집힘)",
                  "옵션": "완료"},
        "DONE": {"row": 5, "상품": "이미 끝난 상품", "상품명": "완료", "옵션": "완료"},
        "DEAD": {"row": 6, "상품": "삭제된 미아", "상품명": "",
                 "옵션": "상품삭제(제외카테고리·자동)"},
    }
    GROUP = [{"productId": "IN"}]

    def test_그룹에_없고_pending_이면_편입한다(self):
        out = run_names._recover_group_orphans(self.GROUP, self.M)
        self.assertEqual({o["productId"] for o in out}, {"ORPH", "ORPH2"})
        self.assertTrue(all(o["미아편입"] for o in out))
        # 현황판 `상품` 열의 이름을 실어 보낸다(로그·배치에서 사람이 알아볼 수 있게)
        self.assertEqual(
            next(o for o in out if o["productId"] == "ORPH")["상품명"], "미아 상품")

    def test_삭제된_미아는_편입하지_않는다(self):
        out = run_names._recover_group_orphans(self.GROUP, self.M)
        self.assertNotIn("DEAD", {o["productId"] for o in out})

    def test_ids_를_주면_그_안의_것만(self):
        out = run_names._recover_group_orphans(self.GROUP, self.M, want={"ORPH2"})
        self.assertEqual([o["productId"] for o in out], ["ORPH2"])

    def test_상품명탭에_이미_있는_건은_빼고_redo_에_맡긴다(self):
        out = run_names._recover_group_orphans(
            self.GROUP, self.M, done_ids={"ORPH"})
        self.assertEqual([o["productId"] for o in out], ["ORPH2"])

    def test_현황판을_못_읽으면_빈_리스트(self):
        self.assertEqual(run_names._recover_group_orphans(self.GROUP, {}), [])


class RetireStaleRowsTest(unittest.TestCase):
    """재진입 시 옛 `생성완료` 행 내리기 — rename 이 옛 이름까지 반영하는 걸 막는다."""

    def setUp(self):
        self.updates = []
        i_id = run_names.NAME_HEADER.index("상품id")
        i_st = run_names.NAME_HEADER.index("상태")
        self.rows = []
        for pid, st in [("P1", "생성완료"), ("P2", "반영완료"), ("P1", "반영완료"),
                        ("P3", "생성완료"), ("P1", "생성완료")]:
            r = [""] * len(run_names.NAME_HEADER)
            r[i_id], r[i_st] = pid, st
            self.rows.append(r)
        self.mod = sys.modules["eroomlib.gsheets"]
        self._orig = (self.mod.sheets_get, self.mod.sheets_update)
        self.mod.sheets_get = lambda sheet, rng: self.rows
        self.mod.sheets_update = lambda sheet, rng, vals: self.updates.append((rng, vals))

    def tearDown(self):
        self.mod.sheets_get, self.mod.sheets_update = self._orig

    def test_해당_pid의_생성완료_행만_내린다(self):
        n = run_names._retire_stale_rows("SHEET", "탭", {"P1"}, {"P1": "대표충돌"})
        self.assertEqual(n, 2)                       # P1 의 생성완료 2행
        _rng, col = self.updates[0]
        self.assertEqual([c[0] for c in col],
                         ["재작업(대표충돌)", "반영완료", "반영완료",
                          "생성완료", "재작업(대표충돌)"])   # P2·P3 과 반영완료는 그대로

    def test_내릴_행이_없으면_쓰지_않는다(self):
        self.assertEqual(run_names._retire_stale_rows("SHEET", "탭", {"P2"}, {}), 0)
        self.assertEqual(self.updates, [])

    def test_dry_run은_쓰지_않는다(self):
        n = run_names._retire_stale_rows("SHEET", "탭", {"P1"}, {}, dry_run=True)
        self.assertEqual((n, self.updates), (2, []))


class HoldsFlipBucketTest(unittest.TestCase):
    """holds 가 보류(옵션뒤집힘)을 별도 버킷으로 집계한다."""

    def test_옵션뒤집힘_버킷(self):
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, "checked"))
            with open(os.path.join(tmp, "checked", "checked_001.json"), "w",
                      encoding="utf-8") as f:
                json.dump({"products": [
                    {"productId": "P1", "상태": "보류(옵션뒤집힘)"},
                    {"productId": "P2", "상태": "보류(카테고리의심)"},
                ]}, f, ensure_ascii=False)
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            class A:  # noqa: D401
                run_dir = tmp
            with redirect_stdout(buf):
                run_names.cmd_holds(A())
            out = json.loads(buf.getvalue().strip().splitlines()[-1])
            self.assertEqual(out["옵션뒤집힘"], ["P1"])
            self.assertEqual(out["카테고리의심"], ["P2"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class BaseSuffixHandoffTest(unittest.TestCase):
    """상품명엔 기본형, 옵션명엔 없는 반쪽 상품을 옵션 단계로 넘긴다(결정 6)."""

    def setUp(self):
        self.calls = []

    def _flag(self, sheet, task, items, from_task=None):
        self.calls.append((sheet, task, dict(items), from_task))
        return len(items)

    def _run(self, recs, ok_ids=("P1",)):
        return run_names._handoff_base_suffix(
            "SHEET", list(ok_ids),
            load=lambda pid: recs.get(pid), flag=self._flag)

    def test_대표옵션명에_기본형이_없으면_플래그를_찍는다(self):
        recs = {"P1": _snap([_row("1", 9900, main=True, text="블랙"),
                             _row("2", 12000)])}
        self.assertEqual(self._run(recs), 1)
        sheet, task, items, from_task = self.calls[0]
        self.assertEqual((sheet, task, from_task), ("SHEET", "옵션", "상품명"))
        self.assertIn("P1", items)
        self.assertIn(name_check.BASE_SUFFIX, items["P1"])

    def test_이미_붙어_있으면_넘기지_않는다(self):
        recs = {"P1": _snap([_row("1", 9900, main=True, text="블랙 기본형")])}
        self.assertEqual(self._run(recs), 0)
        self.assertEqual(self.calls, [], "짝이 맞는 상품까지 재작업으로 만들면 안 된다")

    def test_옵션이_없는_단일상품은_제외한다(self):
        # 마커를 붙일 대상이 없다 — 재작업 플래그가 영원히 해소되지 않는다
        self.assertEqual(self._run({"P1": {}}), 0)
        self.assertEqual(self.calls, [])

    def test_대표가_아직_없으면_넘기지_않는다(self):
        # 옵션 단계를 안 거친 상품 — 그 단계가 오면 규칙대로 마커가 붙는다
        recs = {"P1": _snap([_row("1", 9900), _row("2", 12000)])}
        self.assertEqual(self._run(recs), 0)
        self.assertEqual(self.calls, [])

    def test_여러_상품을_한_번에_모아_찍는다(self):
        recs = {
            "P1": _snap([_row("1", 9900, main=True, text="블랙")]),
            "P2": _snap([_row("1", 9900, main=True, text="화이트 기본형")]),
            "P3": _snap([_row("1", 9900, main=True, text="베이지")]),
        }
        self.assertEqual(self._run(recs, ok_ids=("P1", "P2", "P3")), 2)
        self.assertEqual(len(self.calls), 1, "열 통짜 1회로 써야 한다")
        self.assertEqual(sorted(self.calls[0][2]), ["P1", "P3"])

    def test_시트나_대상이_없으면_아무것도_하지_않는다(self):
        self.assertEqual(run_names._handoff_base_suffix("", ["P1"]), 0)
        self.assertEqual(run_names._handoff_base_suffix("SHEET", []), 0)

    def test_플래그_쓰기_실패는_반영결과를_뒤엎지_않는다(self):
        def boom(*_a, **_k):
            raise RuntimeError("gws 응답 없음")
        recs = {"P1": _snap([_row("1", 9900, main=True, text="블랙")])}
        n = run_names._handoff_base_suffix(
            "SHEET", ["P1"], load=lambda pid: recs.get(pid), flag=boom)
        self.assertEqual(n, 0)


class PlacementR9Test(unittest.TestCase):
    """R9 — 원본 단어와 키워드를 `a 1 b 2 c` 로 번갈아 놓았는가 (2026-07-31 이룸님).

    실측 계기: 3-1 그룹 `스파게티냄비 면삶는냄비 업소용 뜰채 깊은` — 키워드를 앞에 몰아
    실물 직결어(탕면기·우동)가 잘려 나갔다.
    """

    def _check(self, name, terms, keywords):
        return name_check.check_one(
            {"새상품명": name, "term분해": terms, "키워드": keywords}, strict=False)

    def _r9(self, r):
        return [v for v in r["위반"] if v.startswith("R9")]

    def test_키워드를_앞에_몰고_원본을_뒤에_붙이면_실패한다(self):
        r = self._check("스파게티냄비 면삶는냄비 업소용 뜰채 깊은 기본형",
                        ["스파게티", "냄비", "면", "삶는", "냄비", "업소용", "뜰채", "깊은",
                         name_check.BASE_SUFFIX],
                        ["스파게티냄비", "면삶는냄비"])
        self.assertTrue(self._r9(r), "R9가 잡아야 한다")
        self.assertIn("업소용", self._r9(r)[0], "밀려난 원본 단어를 지목해야 한다")

    def test_a1b2_로_번갈아_놓으면_통과한다(self):
        r = self._check("탕면기 스파게티냄비 우동 면삶는냄비 기본형",
                        ["탕면기", "스파게티", "냄비", "우동", "면", "삶는", "냄비",
                         name_check.BASE_SUFFIX],
                        ["스파게티냄비", "면삶는냄비"])
        self.assertEqual(r["위반"], [])
        self.assertEqual(r["term수"], 6)

    def test_자리가_모자라_키워드가_붙는_건_정상이다(self):
        # 내용어 6을 키워드가 다 먹으면 원본 단어는 a 하나뿐 — c·b가 없어 붙는다
        r = self._check("탕면기 스파게티냄비 면삶는냄비 기본형",
                        ["탕면기", "스파게티", "냄비", "면", "삶는", "냄비",
                         name_check.BASE_SUFFIX],
                        ["스파게티냄비", "면삶는냄비"])
        self.assertEqual(self._r9(r), [])

    def test_원본_단어가_아예_없으면_키워드만_이어도_된다(self):
        r = self._check("이발의자 전동미용의자 기본형",
                        ["이발", "의자", "전동", "미용", "의자", name_check.BASE_SUFFIX],
                        ["이발의자", "전동미용의자"])
        self.assertEqual(self._r9(r), [])

    def test_두_어절에_걸친_키워드도_한_덩어리로_본다(self):
        # '각얼음빙수기' = 각얼음 + 빙수기 두 어절. 앞뒤에 원본 단어가 있으니 통과
        r = self._check("가정용 무선 각얼음 빙수기 눈꽃 슬러시 기본형",
                        ["가정용", "무선", "각얼음", "빙수기", "눈꽃", "슬러시",
                         name_check.BASE_SUFFIX],
                        ["무선빙수기", "각얼음빙수기"])
        self.assertEqual(self._r9(r), [])

    def test_부분반영_레시피_결과는_통과한다(self):
        # 구별 term('자바라')이 a 자리를 채운다 → 회귀 방지
        r = self._check("자바라 조립식캐노피천막 원터치 접이식 기본형",
                        ["자바라", "조립식", "캐노피", "천막", "원터치", "접이식",
                         name_check.BASE_SUFFIX],
                        ["조립식캐노피천막", "자바라캐노피천막"])
        self.assertEqual(r["위반"], [])

    def test_키워드3개도_계속_번갈아야_한다(self):
        bad = self._check("업소용 이발의자 전동미용의자 미용실의자 높이조절 기본형",
                          ["업소용", "이발", "의자", "전동", "미용", "의자", "미용실",
                           "의자", "높이조절", name_check.BASE_SUFFIX],
                          ["이발의자", "전동미용의자", "미용실의자"])
        self.assertTrue(self._r9(bad), "2·3번 키워드가 붙었는데 뒤에 원본 단어가 남았다")

    def test_마커는_배치_판정에서_빼고_본다(self):
        # 마지막 gap 이 마커뿐이면 '원본 단어가 남은 것'이 아니다
        r = self._check("업소용 이발의자 전동미용의자 기본형",
                        ["업소용", "이발", "의자", "전동", "미용", "의자",
                         name_check.BASE_SUFFIX],
                        ["이발의자", "전동미용의자"])
        self.assertEqual(self._r9(r), [])


class NamedFilesTest(unittest.TestCase):
    """지시서1 — chal/draft 중간산출물이 집계 glob 에 섞이면 안 된다(두 번째 재발)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.named = os.path.join(self.tmp, "named")
        self.checked = os.path.join(self.tmp, "checked")
        os.makedirs(self.named)
        os.makedirs(self.checked)

    def _touch(self, d, name):
        with open(os.path.join(d, name), "w", encoding="utf-8") as f:
            f.write("{}")

    def test_named는_숫자3자리_최종본만_잡는다(self):
        for n in ("named_000.json", "named_001.json",
                  "named_000.chal.json", "draft_000.json", "named_extra.json"):
            self._touch(self.named, n)
        got = [os.path.basename(p) for p in run_names._named_files(self.tmp)]
        self.assertEqual(got, ["named_000.json", "named_001.json"])

    def test_checked도_같은_규칙으로_chal을_배제한다(self):
        for n in ("checked_000.json", "checked_000.chal.json", "checked_abc.json"):
            self._touch(self.checked, n)
        got = [os.path.basename(p) for p in run_names._checked_files(self.checked)]
        self.assertEqual(got, ["checked_000.json"])


class CheckProductCountTest(unittest.TestCase):
    """지시서2 — ###CHECK### 는 배치 수만이 아니라 **상품 수**를 같이 찍어야 한다."""

    def test_상품단위_통과_실패_보류를_같이_찍는다(self):
        tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(tmp, "named"))
        with open(os.path.join(tmp, "named", "named_000.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"products": [
                {"productId": "P001", "상태": "보류(실물불명)"},
                {"productId": "P002", "새상품명": "규칙 다 어긴 이름",  # 마커 없음 → 실패
                 "term분해": ["규칙"], "키워드1": "규칙"},
            ]}, f, ensure_ascii=False)
        # chal 이 named/ 에 남아 있어도 집계에 안 섞인다
        with open(os.path.join(tmp, "named", "named_000.chal.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"products": [{"productId": "P003", "상태": "검증실패"}]}, f)

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            run_names.cmd_check(argparse.Namespace(run_dir=tmp))
        out = buf.getvalue()
        self.assertIn("###CHECK### 상품 통과 0 / 실패 1 / 보류 1", out)
        self.assertIn("배치 실패 1 / 1", out)


class FixR9Test(unittest.TestCase):
    """지시서3 — R9 단독 실패의 기계 재배열(1-1 회차 124건 실전 검증 알고리즘)."""

    def setUp(self):
        import fix_r9
        self.fix_r9 = fix_r9
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "named"))
        os.makedirs(os.path.join(self.tmp, "checked"))

    def _write(self, sub, name, products):
        with open(os.path.join(self.tmp, sub, name), "w", encoding="utf-8") as f:
            json.dump({"products": products}, f, ensure_ascii=False)

    def _r9_product(self, pid="P001"):
        # 키워드 2개가 앞에 몰림 → R9 단독 실패 형태
        return {"productId": pid,
                "새상품명": "스파게티냄비 면삶는냄비 업소용 뜰채 깊은 기본형",
                "term분해": ["스파게티냄비", "면삶는냄비", "업소용", "뜰채", "깊은",
                             name_check.BASE_SUFFIX],
                "키워드1": "스파게티냄비", "키워드2": "면삶는냄비",
                "상태": "검증실패"}

    def test_재배열_후_R1과_R9를_동시에_통과한다(self):
        p = self._r9_product()
        self._write("named", "named_000.json", [p])
        self._write("checked", "checked_000.json",
                    [dict(p, 검증={"위반": ["R9 배치 어긋남 — ..."]})])

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            fixed, skipped = self.fix_r9.run(self.tmp, commit=True)
        self.assertEqual((fixed, skipped), (1, 0))

        with open(os.path.join(self.tmp, "named", "named_000.json"),
                  encoding="utf-8") as f:
            it = json.load(f)["products"][0]
        self.assertIn("R9 기계 재배열", it["메모"])
        r = name_check.check_one(it, strict=False)
        self.assertFalse([v for v in r["위반"] if v.startswith(("R1", "R9"))],
                         f"재배열 후에도 위반: {r['위반']}")
        # a 1 b 2 c — 원본 단어가 앞자리부터 키워드 사이에 끼었다
        self.assertEqual(it["새상품명"],
                         "업소용 스파게티냄비 뜰채 면삶는냄비 깊은 기본형")

    def test_R9외_위반이_섞인_건은_손대지_않는다(self):
        p = self._r9_product()
        self._write("named", "named_000.json", [p])
        self._write("checked", "checked_000.json",
                    [dict(p, 검증={"위반": ["R9 배치 어긋남", "R4 키워드 1개"]})])
        with contextlib.redirect_stdout(io.StringIO()):
            fixed, _ = self.fix_r9.run(self.tmp, commit=True)
        self.assertEqual(fixed, 0)
        with open(os.path.join(self.tmp, "named", "named_000.json"),
                  encoding="utf-8") as f:
            self.assertEqual(json.load(f)["products"][0]["새상품명"],
                             p["새상품명"])  # 원형 그대로

    def test_dry_run은_디스크를_바꾸지_않는다(self):
        p = self._r9_product()
        self._write("named", "named_000.json", [p])
        self._write("checked", "checked_000.json",
                    [dict(p, 검증={"위반": ["R9 배치 어긋남"]})])
        with contextlib.redirect_stdout(io.StringIO()):
            fixed, _ = self.fix_r9.run(self.tmp, commit=False)
        self.assertEqual(fixed, 1)
        with open(os.path.join(self.tmp, "named", "named_000.json"),
                  encoding="utf-8") as f:
            self.assertEqual(json.load(f)["products"][0]["새상품명"],
                             p["새상품명"])  # dry-run = 무변경


class HoldsTest(unittest.TestCase):
    """holds — 보류 3종 + 카테고리미설정 집계(자동 재교정 서브플로의 입력)."""

    def _mkrun(self, name="r1"):
        tmp = os.path.join(tempfile.mkdtemp(), name)
        os.makedirs(os.path.join(tmp, "checked"))
        with open(os.path.join(tmp, "checked", "checked_000.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"products": [
                {"productId": "P001", "상태": "보류(카테고리의심)"},
                {"productId": "P002", "상태": "보류(실물불명)"},
                {"productId": "P003", "상태": "생성완료"},
                {"productId": "P001", "상태": "보류(카테고리의심)"},  # 중복 → 1건
            ]}, f, ensure_ascii=False)
        with open(os.path.join(tmp, "skipped.json"), "w", encoding="utf-8") as f:
            json.dump([{"productId": "P009", "사유": "카테고리미설정"},
                       {"productId": "P010", "사유": "그룹부재"}], f, ensure_ascii=False)
        return tmp

    def _run(self, run_dir):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            run_names.cmd_holds(argparse.Namespace(run_dir=run_dir))
        return buf.getvalue()

    def test_보류와_미설정을_중복없이_집계한다(self):
        out = self._run(self._mkrun())
        got = json.loads(out.strip().splitlines()[-1])
        self.assertEqual(got["카테고리의심"], ["P001"])
        self.assertEqual(got["실물불명"], ["P002"])
        self.assertEqual(got["카테고리미설정"], ["P009"])  # 그룹부재는 제외
        self.assertEqual(got["키워드부족"], [])

    def test_redo_런디렉토리면_재진입금지_경고를_찍는다(self):
        out = self._run(self._mkrun(name="yong1-1_redo1"))
        self.assertIn("[재진입금지]", out)
        json.loads(out.strip().splitlines()[-1])  # 경고가 있어도 JSON 은 마지막 줄

    def test_일반_런디렉토리면_경고가_없다(self):
        self.assertNotIn("[재진입금지]", self._run(self._mkrun()))


class MarkTest(unittest.TestCase):
    """mark — 기존 행 상태 변경. 같은 pid 여러 행이면 **마지막 행**(최신)만."""

    def setUp(self):
        self.updates = []
        import eroomlib.gsheets as g
        self._g = g
        self._orig_get, self._orig_upd = g.sheets_get, g.sheets_update
        g.sheets_update = lambda s, r, v: self.updates.append((s, r, v)) or {}
        self.addCleanup(lambda: (setattr(g, "sheets_get", self._orig_get),
                                 setattr(g, "sheets_update", self._orig_upd)))
        # cmd_mark 는 현황판도 갱신한다(2026-08-19) — 실제 시트를 치지 않게 가로챈다.
        from eroomlib import matrix as _mx
        self.matrix_calls = []
        self._orig_mark = _mx.mark_many
        _mx.mark_many = lambda s, col, tgt, **kw: (
            self.matrix_calls.append((s, col, dict(tgt))) or len(tgt))
        self.addCleanup(lambda: setattr(_mx, "mark_many", self._orig_mark))

    def _rows(self):
        h = run_names.NAME_HEADER
        i_id, i_status, i_memo = h.index("상품id"), h.index("상태"), h.index("메모")

        def row(pid, status, memo=""):
            r = [""] * len(h)
            r[i_id], r[i_status], r[i_memo] = pid, status, memo
            return r
        # P001 이 2행(옛 행 + redo 새 행) — 마지막 행만 바뀌어야 한다
        return [row("P001", "반영완료"), row("P002", "생성완료", "기존메모"),
                row("P001", "생성완료"), row("P003", "생성완료")]

    def _run(self, ids, status, note=""):
        self._g.sheets_get = lambda s, r: self._rows()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            run_names.cmd_mark(argparse.Namespace(
                sheet="SHEET", tab=run_names.NAME_TAB,
                ids=ids, status=status, note=note,
                no_matrix=getattr(self, "no_matrix", False)))
        return buf.getvalue()

    def test_마지막_행만_바꾸고_다른_행은_보존한다(self):
        out = self._run(["P001"], "재작업(카테고리변경)")
        self.assertIn("###MARK### 1건", out)
        self.assertEqual(len(self.updates), 1)  # 상태열 1회(메모 없음)
        _, rng, values = self.updates[0]
        i_status = run_names.NAME_HEADER.index("상태")
        letter = run_names._col_letter(i_status + 1)
        self.assertEqual(rng, f"'상품명'!{letter}2:{letter}5")
        self.assertEqual([v[0] for v in values],
                         ["반영완료", "생성완료", "재작업(카테고리변경)", "생성완료"])

    def test_노트를_주면_메모열_끝에_덧붙인다(self):
        self._run(["P002"], "보류(표본의심)", note="표본검수 — 실물 불일치 의심")
        self.assertEqual(len(self.updates), 2)  # 상태열 + 메모열
        _, _, memo_values = self.updates[1]
        self.assertEqual(memo_values[1], ["기존메모 | 표본검수 — 실물 불일치 의심"])
        self.assertEqual(memo_values[0], [""])  # 대상 아닌 행 메모는 그대로

    def test_현황판도_같이_찍는다(self):
        # 종전엔 상품명 탭만 고쳐 두 저장소가 갈렸다 — 표본검수로 뺀 건이 탭에는
        # `보류(표본의심)` 인데 현황판에는 `진행중(미반영)` 로 남아 영영 굳었다.
        self._run(["P001"], "보류(표본의심)")
        self.assertEqual(len(self.matrix_calls), 1)
        _, col, tgt = self.matrix_calls[0]
        self.assertEqual(col, "상품명")
        self.assertEqual(tgt, {"P001": "보류(표본의심)"})

    def test_no_matrix면_현황판을_건드리지_않는다(self):
        self.no_matrix = True
        self._run(["P001"], "보류(표본의심)")
        self.assertEqual(self.matrix_calls, [])

    def test_현황판_실패해도_상품명탭_반영은_유지된다(self):
        # 시트 쓰기는 이미 끝난 뒤라 여기서 예외가 나가면 성공한 작업이 실패로 보인다.
        from eroomlib import matrix as _mx

        def _boom(*a, **k):
            raise RuntimeError("429")
        _mx.mark_many = _boom
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            out = self._run(["P001"], "보류(표본의심)")
        self.assertIn("###MARK### 1건", out)
        self.assertIn("현황판 갱신 실패", buf.getvalue())

    def test_시트에_없는_pid는_경고만_찍고_있는_것만_처리한다(self):
        out = self._run(["P003", "P999"], "보류(표본의심)")
        self.assertIn("[경고] 시트에 없는 상품id 1건", out)
        self.assertIn("###MARK### 1건", out)

    def test_전부_없으면_시트를_건드리지_않는다(self):
        out = self._run(["P998", "P999"], "보류(표본의심)")
        self.assertIn("###MARK### 0건", out)
        self.assertEqual(self.updates, [])


class SingleKeywordExemptionTest(unittest.TestCase):
    """R4 1개 예외 (2026-08-05 이룸님) — 직결어가 1개뿐이면 원본 단어로 채워 내보낸다.

    근거: 1-2 회차 `보류(키워드부족)` 64건이 전부 "뷰에 직결어 1개뿐"인 니치 상품이었다
    (연못방수포·키보드흡음재·스티로폼알갱이·의자머리받침). 버리면 노출이 0이 된다.
    단 증빙 없는 1개는 계속 막는다 — 재팬아웃 emphasis 가 R4 실패를 104→9로 줄인 장치다.
    """

    BASE = {
        "새상품명": "양어장 연못방수포 저수지 물막이 시트 기본형",
        "term분해": ["양어장", "연못", "방수포", "저수지", "물막이", "시트",
                   name_check.BASE_SUFFIX],
        "키워드1": "연못방수포",
        "관련어": [{"키워드": "연못방수포", "상품수": 1820, "검색량": 260}],
        "반증": "없음 — 나머지는 방수페인트로 시트가 아니다",
    }

    def _check(self, **over):
        p = dict(self.BASE)
        p.update(over)
        return name_check.check_one(p)

    def test_증빙이_있으면_키워드_1개도_통과한다(self):
        r = self._check(키워드확장="상품수 5만까지 확장 + 상위뷰 확인 — 직결어 1개뿐")
        self.assertTrue(r["통과"], r["위반"])
        self.assertTrue(any("키워드 1개" in w for w in r["경고"]),
                        "1개 경로는 경고로 남아야 추적된다")

    def test_증빙이_없으면_종전대로_R4_실패다(self):
        r = self._check()
        self.assertFalse(r["통과"])
        self.assertTrue(any(v.startswith("R4") for v in r["위반"]))

    def test_증빙이_공백뿐이면_증빙으로_안_쳐준다(self):
        r = self._check(키워드확장="   ")
        self.assertFalse(r["통과"])
        self.assertTrue(any(v.startswith("R4") for v in r["위반"]))

    def test_실패_사유가_증빙_남기는_법을_알려준다(self):
        r = self._check()
        self.assertTrue(any("키워드확장" in v for v in r["위반"]))

    def test_키워드_0개는_증빙이_있어도_실패다(self):
        # 직결어 0 = 카테고리 문제다. 예외를 열어주면 억지 상품명이 나온다
        r = self._check(키워드1="", 키워드확장="다 뒤졌는데 없음")
        self.assertFalse(r["통과"])
        self.assertTrue(any(v.startswith("R4") for v in r["위반"]))

    def test_1개_예외여도_다른_규칙은_그대로_적용된다(self):
        # term 3개(R2 미달)까지 봐주지는 않는다
        r = self._check(새상품명="연못방수포 시트 기본형",
                        term분해=["연못", "방수포", "시트", name_check.BASE_SUFFIX],
                        키워드확장="확장 소진")
        self.assertFalse(r["통과"])
        self.assertTrue(any(v.startswith("R2") for v in r["위반"]))

    def test_1개여도_R9_배치는_지켜야_한다(self):
        # 키워드를 맨 앞에 몰고 원본 단어를 뒤로 밀면 실패 (a 1 b c)
        r = self._check(새상품명="연못방수포 양어장 저수지 물막이 시트 기본형",
                        term분해=["연못", "방수포", "양어장", "저수지", "물막이", "시트",
                               name_check.BASE_SUFFIX],
                        키워드확장="확장 소진")
        self.assertFalse(r["통과"])
        self.assertTrue(any(v.startswith("R9") for v in r["위반"]))

    def test_시트_메모에_키워드1개_증빙이_박힌다(self):
        p = dict(self.BASE, productId="P1", 키워드확장="상품수 5만까지 확장",
                 메모="썸네일=검정 PVC 롤")
        memo = run_names._build_row(p, "g")[run_names.NAME_HEADER.index("메모")]
        self.assertTrue(memo.startswith("[키워드1개] 상품수 5만까지 확장"))
        self.assertIn("썸네일=검정 PVC 롤", memo)

    def test_키워드가_2개면_메모를_건드리지_않는다(self):
        p = dict(self.BASE, productId="P1", 키워드2="방수시트",
                 키워드확장="남아있는 값", 메모="원래메모")
        memo = run_names._build_row(p, "g")[run_names.NAME_HEADER.index("메모")]
        self.assertEqual(memo, "원래메모")

    def test_증빙이_없으면_메모는_그대로다(self):
        p = dict(self.BASE, productId="P1", 메모="원래메모")
        memo = run_names._build_row(p, "g")[run_names.NAME_HEADER.index("메모")]
        self.assertEqual(memo, "원래메모")

    def test_2개_이상이면_증빙이_없어도_통과한다(self):
        # 예외를 넣느라 정상 경로를 깨뜨리지 않았는지 (내용어 6 = 양어장·연못·방수포·저수지·방수·시트)
        r = self._check(새상품명="양어장 연못방수포 저수지 방수시트 기본형",
                        term분해=["양어장", "연못", "방수포", "저수지", "방수", "시트",
                               name_check.BASE_SUFFIX],
                        키워드2="방수시트",
                        관련어=[{"키워드": "연못방수포", "상품수": 1820, "검색량": 260},
                             {"키워드": "방수시트", "상품수": 9100, "검색량": 700}])
        self.assertTrue(r["통과"], r["위반"])


class KeepOriginalPathTest(unittest.TestCase):
    """원본유지 경로 (2026-08-07 이룸님) — 원본이 이미 실물을 지칭하면 마커만 붙인다.

    발단 = 라인테이핑기(3-2). 재교정으로 카테고리를 바꾼 뒤 새 뷰를 다시 훑었는데
    근접어(`주차선도색기계`)가 **있었지만** 도색 방식이라 테이프 부착식 실물과
    메커니즘이 달라 쓰면 오지칭이었다. 판단은 옳았고 원본 이름도 맞았는데 갈 곳이
    사람 큐뿐이라 쌓였다 — "일일이 다 체크할 수가 없어서".

    **면제는 이름 품질(R2~R7·R9)까지고 구조(R1·R8)는 그대로다.**
    """

    ORIG = "라인 테이핑기 바닥 주차 경기장 라인테이프"
    BASE = {
        "새상품명": ORIG + " " + name_check.BASE_SUFFIX,
        "term분해": ["라인", "테이핑기", "바닥", "주차", "경기장", "라인테이프",
                   name_check.BASE_SUFFIX],
    }
    SAYU = "재교정 후 새 뷰를 다시 훑었으나 근접어는 메커니즘 불일치. 원본이 이미 실물 지칭"

    def _check(self, **over):
        p = dict(self.BASE)
        p.update(over)
        return name_check.check_one(p)

    def test_사유가_있으면_키워드_0개_term_6개여도_통과한다(self):
        r = self._check(원본유지사유=self.SAYU)
        self.assertTrue(r["통과"], r["위반"])
        self.assertTrue(any("원본유지" in w for w in r["경고"]))

    def test_사유가_없으면_실패한다(self):
        self.assertFalse(self._check()["통과"])

    def test_면제해도_R8_마커는_못_뚫는다(self):
        """마커를 붙이는 게 이 경로의 유일한 변경이라, 그것만은 반드시 건다."""
        r = self._check(원본유지사유=self.SAYU, 새상품명=self.ORIG,
                        term분해=["라인", "테이핑기", "바닥", "주차", "경기장", "라인테이프"])
        self.assertFalse(r["통과"])
        self.assertTrue(all(v.startswith("R8") for v in r["위반"]), r["위반"])

    def test_면제해도_R1_term분해_정합은_못_뚫는다(self):
        r = self._check(원본유지사유=self.SAYU,
                        term분해=["라인", "테이핑기", name_check.BASE_SUFFIX])
        self.assertFalse(r["통과"])
        self.assertTrue(any(v.startswith("R1") for v in r["위반"]), r["위반"])

    def test_면제한_위반을_경고에_남긴다(self):
        """무엇을 봐주고 통과시켰는지가 안 보이면 사후에 못 되짚는다."""
        r = self._check(원본유지사유=self.SAYU)
        self.assertTrue(any("면제" in w and "R4" in w for w in r["경고"]), r["경고"])


class NoKeywordPathTest(unittest.TestCase):
    """무키워드 경로 (2026-08-06 이룸님) — 직결어 0개도 원본 단어만으로 짓는다.

    카테고리 재교정까지 소진한 잔여분 전용. 게이트를 `키워드확장` 과 **따로** 둔 이유:
    R4·R5·R6 을 한꺼번에 여는 훨씬 넓은 면제라, 1개 예외와 실수로 섞이면 안 된다.
    """

    BASE = {
        "새상품명": "그릴판 오프너 병따개 지렛대 스테인리스 기본형",
        "term분해": ["그릴판", "오프너", "병따개", "지렛대", "스테인리스",
                   name_check.BASE_SUFFIX],
    }

    def _check(self, **over):
        p = dict(self.BASE)
        p.update(over)
        return name_check.check_one(p)

    def test_사유가_있으면_키워드_0개도_통과한다(self):
        r = self._check(무키워드사유="leaf·상위뷰 모두 오프너/병따개 직결어 0건")
        self.assertTrue(r["통과"], r["위반"])
        self.assertTrue(any("무키워드" in w for w in r["경고"]))

    def test_사유가_없으면_R4로_실패한다(self):
        r = self._check()
        self.assertFalse(r["통과"])
        self.assertTrue(any(v.startswith("R4") for v in r["위반"]))

    def test_관련어_반증이_비어도_R6로_실패하지_않는다(self):
        # 고른 키워드가 없으면 되던질 것도 없다
        r = self._check(무키워드사유="뷰 0KB")
        self.assertFalse(any(v.startswith("R6") for v in r["위반"]))

    def test_적합도_R5는_면제된다(self):
        r = self._check(무키워드사유="뷰 0KB")
        self.assertFalse(any(v.startswith("R5") for v in r["위반"]))

    def test_키워드확장으로는_0개가_안_열린다(self):
        # 게이트가 분리돼 있어야 1개 예외가 0개까지 번지지 않는다
        r = self._check(키워드확장="상품수 5만까지 확장")
        self.assertFalse(r["통과"])
        self.assertTrue(any(v.startswith("R4") for v in r["위반"]))

    def test_무키워드여도_term수_마커_규칙은_그대로다(self):
        r = self._check(새상품명="오프너 병따개 기본형",
                        term분해=["오프너", "병따개", name_check.BASE_SUFFIX],
                        무키워드사유="뷰 0KB")
        self.assertFalse(r["통과"])
        self.assertTrue(any(v.startswith("R2") for v in r["위반"]))

    def test_키워드가_있으면_무키워드사유가_있어도_평소대로_검사한다(self):
        # 사유를 남겨둔 채 키워드를 채웠으면 면제가 열리면 안 된다
        r = self._check(키워드1="오프너", 무키워드사유="남아있는 값")
        self.assertFalse(r["통과"])
        self.assertTrue(any(v.startswith("R4") or v.startswith("R6")
                            for v in r["위반"]))

    def test_시트_메모에_무키워드_태그가_박힌다(self):
        p = dict(self.BASE, productId="P1", 무키워드사유="뷰 0KB", 메모="썸네일=지렛대형")
        memo = run_names._build_row(p, "g")[run_names.NAME_HEADER.index("메모")]
        self.assertTrue(memo.startswith("[무키워드] 뷰 0KB"))
        self.assertIn("썸네일=지렛대형", memo)


class HoldsReentryGuardTest(unittest.TestCase):
    """재진입 run-dir(`_redo`·`_kw1`)은 서브플로를 다시 태우지 않는다."""

    def _run(self, dirname):
        with tempfile.TemporaryDirectory() as td:
            run_dir = os.path.join(td, dirname)
            os.makedirs(os.path.join(run_dir, "checked"))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                run_names.cmd_holds(argparse.Namespace(run_dir=run_dir))
            return buf.getvalue()

    def test_kw1_런디렉토리는_재진입금지를_찍는다(self):
        self.assertIn("[재진입금지]", self._run("yong1-2_kw1"))

    def test_redo_런디렉토리도_그대로_찍는다(self):
        self.assertIn("[재진입금지]", self._run("yong1-2_redo1"))

    def test_본_라운드는_경고를_안_찍는다(self):
        self.assertNotIn("[재진입금지]", self._run("yong1-2"))


class RetailBrandR11Test(unittest.TestCase):
    """R11 (2026-08-14) — 남의 유통사 브랜드를 상품명에 넣었나.

    발단: 2-1 표본검수. 중국산 계단카트에 채택 키워드 `코스트코접이식카트`. 셀러라이프
    브랜드키워드 컷도 블랙리스트 `제외브랜드`(소비재 위주)도 유통사명을 안 걸렀다.
    """

    BASE = {
        "새상품명": "계단 코스트코접이식카트 소형 계단용카트 기본형",
        "term분해": ["계단", "코스트코", "접이식카트", "소형", "계단용", "카트",
                   name_check.BASE_SUFFIX],
        "키워드1": "코스트코접이식카트",
        "키워드2": "계단용카트",
        "원본상품명": "전동 계단 리프트 소형 화물 접이식 카트 이삿짐",
        "관련어": [{"키워드": "코스트코접이식카트", "상품수": 893}],
        "반증": "없음",
    }

    def _check(self, **over):
        p = dict(self.BASE)
        p.update(over)
        return name_check.check_one(p)

    def test_원본에_없는_브랜드를_붙이면_실패다(self):
        r = self._check()
        self.assertFalse(r["통과"])
        self.assertTrue(any("R11" in v and "코스트코" in v for v in r["위반"]))

    def test_원본에_이미_있으면_경고로만_낸다(self):
        r = self._check(원본상품명="코스트코 접이식 카트 계단 화물")
        self.assertTrue(r["통과"])
        self.assertTrue(any("R11" in w for w in r["경고"]))

    def test_브랜드가_없으면_아무것도_안_찍는다(self):
        r = self._check(새상품명="계단 화물운반카트 소형 계단용카트 기본형",
                        term분해=["계단", "화물운반카트", "소형", "계단용", "카트",
                                name_check.BASE_SUFFIX],
                        키워드1="화물운반카트")
        self.assertFalse(any("R11" in x for x in r["위반"] + r["경고"]))


class NokwViewlessBatchTest(unittest.TestCase):
    """`--nokw-mode` 가 **뷰 없는 대상**도 배치에 싣는가 (2026-08-14).

    발단: 2-1 회차. 통다운밖 12건은 `manifest.categories` 에 항목이 없어(not_found)
    뷰도 배치도 0개가 됐다 — `--nokw-mode` 는 이미 만들어진 배치에 플래그만 얹는 코드라
    정작 제 대상에 안 걸렸다. 손으로 배치를 만들어 우회해야 했다.
    """

    def _build(self, nokw):
        import tempfile
        run_dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(run_dir, "batches"), exist_ok=True)
        # 카테고리 항목이 하나도 없는 manifest = 통다운밖만 있는 상태
        with open(os.path.join(run_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"categories": {}, "parents": {}, "not_found": ["A", "B"]}, f)
        targets = [{"productId": "U01A", "상품명": "가림막 병풍", "카테고리": "가구>병풍"},
                   {"productId": "U01B", "상품명": "초밥용기", "카테고리": "생활>용기"}]
        with mock.patch.object(run_names, "_same_price_options", return_value=False), \
             mock.patch.object(run_names, "_spec_view", return_value={}):
            run_names._build_views_and_batches(
                run_dir, targets, {}, no_parent=True, skipped_n=0,
                wd_by_id={}, jk_by_id={}, nokw_mode=nokw)
        return sorted(glob.glob(os.path.join(run_dir, "batches", "batch_*.json")))

    def test_무키워드모드면_뷰가_없어도_배치가_생긴다(self):
        files = self._build(nokw=True)
        self.assertTrue(files, "뷰가 없다고 배치가 0개면 안 된다")
        got = []
        for f in files:
            b = json.load(open(f, encoding="utf-8"))
            self.assertTrue(b["무키워드모드"])
            self.assertEqual(b["카테고리뷰"], "")      # 뷰는 비어 있어도 되는 규칙
            got += [p["productId"] for p in b["products"]]
        self.assertEqual(sorted(got), ["U01A", "U01B"])

    def test_평상시_라운드는_뷰_없는_배치를_만들지_않는다(self):
        # 직결어 0은 원래 카테고리 신호다(Step 5 ②) — 여기서 이름을 지으면 안 된다.
        self.assertEqual(self._build(nokw=False), [])


class PrepIdsPreservesRunDirTest(unittest.TestCase):
    """`prep --ids` 가 run-dir 상태를 덮어쓰던 결함 3건 (2026-08-15 용쌤2-1 3회차 실측).

    셋 다 **에러 없이 조용히 사라진다.** 로그 숫자를 직접 세야만 드러난다.
    """

    def setUp(self):
        self.run_dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.run_dir, "batches"), exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.run_dir, ignore_errors=True)

    def _write(self, name, obj):
        with open(os.path.join(self.run_dir, name), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)

    # --- ① 배치 번호 ------------------------------------------------------
    def _build(self, targets, append):
        self._write("manifest.json", {"categories": {}, "parents": {},
                                      "not_found": [t["productId"] for t in targets]})
        with mock.patch.object(run_names, "_same_price_options", return_value=False), \
             mock.patch.object(run_names, "_spec_view", return_value={}), \
             contextlib.redirect_stdout(io.StringIO()):
            run_names._build_views_and_batches(
                self.run_dir, targets, {}, no_parent=True, skipped_n=0,
                wd_by_id={}, jk_by_id={}, nokw_mode=True, append=append)
        return sorted(os.path.basename(p) for p in
                      glob.glob(os.path.join(self.run_dir, "batches", "batch_*.json")))

    def test_append면_기존_배치를_덮어쓰지_않는다(self):
        # 실측: 배치 14개가 있는 run-dir 에 `--ids <1건>` 을 쳤더니 batch_001 을
        # 덮어써서 거기 있던 2건(강의대·연단)이 사라졌다.
        first = self._build([{"productId": "U01A", "상품명": "강의대",
                              "카테고리": "가구>강의대"}], append=False)
        self.assertEqual(first, ["batch_001.json"])
        with open(os.path.join(self.run_dir, "batches", "batch_001.json"),
                  encoding="utf-8") as f:
            keep = json.load(f)

        after = self._build([{"productId": "U01B", "상품명": "연단",
                              "카테고리": "가구>연단"}], append=True)
        self.assertEqual(after, ["batch_001.json", "batch_002.json"])
        with open(os.path.join(self.run_dir, "batches", "batch_001.json"),
                  encoding="utf-8") as f:
            self.assertEqual(json.load(f), keep, "batch_001 이 덮어써졌다")

    def test_append면_인덱스도_이어붙인다(self):
        self._build([{"productId": "U01A", "상품명": "강의대", "카테고리": "가구>강의대"}],
                    append=False)
        self._build([{"productId": "U01B", "상품명": "연단", "카테고리": "가구>연단"}],
                    append=True)
        with open(os.path.join(self.run_dir, "batches_index.json"),
                  encoding="utf-8") as f:
            idx = json.load(f)
        self.assertEqual([x["batch"] for x in idx],
                         ["batch_001.json", "batch_002.json"])

    def test_전량_prep_은_종전대로_1번부터_새로_만든다(self):
        self._build([{"productId": "U01A", "상품명": "강의대", "카테고리": "가구>강의대"}],
                    append=False)
        after = self._build([{"productId": "U01B", "상품명": "연단",
                              "카테고리": "가구>연단"}], append=False)
        self.assertEqual(after, ["batch_001.json"])

    def test_다음_배치번호는_최댓값_다음이다(self):
        self.assertEqual(run_names._next_batch_no(self.run_dir), 1)
        for n in (1, 2, 7):
            open(os.path.join(self.run_dir, "batches",
                              f"batch_{n:03d}.json"), "w").close()
        self.assertEqual(run_names._next_batch_no(self.run_dir), 8)

    # --- ② redo.json ------------------------------------------------------
    def test_면제목록은_덮어쓰지_않고_합친다(self):
        # 실측(제일 비싼 결함): `--ids <2건>` 이 redo.json 을 2건으로 덮어써서 앞서
        # 편입된 14건이 면제에서 빠지고 append 가 전부 `스킵(이미처리)` 로 버렸다
        # — 워커 비용은 다 쓰고 시트엔 2행.
        self._write("redo.json", [f"P{i:02d}" for i in range(14)])
        with contextlib.redirect_stdout(io.StringIO()):
            got = run_names._merge_exempt(self.run_dir, ["NEW1", "NEW2"])
        self.assertEqual(len(got), 16)
        self.assertIn("P00", got)
        self.assertIn("NEW1", got)

    def test_이미_소진된_면제는_되살리지_않는다(self):
        # 면제는 1회용(append 가 redo.json.done 으로 소진) — 되살리면 시트에 두 줄 들어간다
        self._write("redo.json", ["A", "B"])
        self._write("redo.json.done", ["A"])
        with contextlib.redirect_stdout(io.StringIO()):
            got = run_names._merge_exempt(self.run_dir, ["C"])
        self.assertEqual(got, ["B", "C"])

    def test_기존_파일이_없으면_이번_회차분_그대로다(self):
        self.assertEqual(run_names._merge_exempt(self.run_dir, ["X"]), ["X"])

    # --- ③ workdata.json --------------------------------------------------
    def test_캐시에_없는_대상만_조회해_덧붙인다(self):
        # 실측: group.json 에 손으로 넣어도 workdata.json 이 캐시 재사용이라
        # `[4/6] 대상 0건 / 카테고리미설정 스킵 1건` 으로 떨어져 멈췄다.
        wd = os.path.join(self.run_dir, "workdata.json")
        self._write("workdata.json", [{"productId": "A", "상품명": "가"}])
        pending = [{"productId": "A"}, {"productId": "B"}]
        seen = {}

        def _fake_run(cmd, label):
            with open(cmd[cmd.index("--input") + 1], encoding="utf-8") as f:
                seen["input"] = json.load(f)
            with open(cmd[cmd.index("--output") + 1], "w", encoding="utf-8") as f:
                json.dump([{"productId": "B", "상품명": "나"}], f, ensure_ascii=False)

        with mock.patch.object(run_names, "_run", _fake_run), \
             contextlib.redirect_stdout(io.StringIO()):
            run_names._fill_workdata(self.run_dir, wd, pending, "python", 0)

        self.assertEqual([p["productId"] for p in seen["input"]], ["B"],
                         "이미 있는 건까지 다시 조회하면 안 된다")
        with open(wd, encoding="utf-8") as f:
            self.assertEqual([w["productId"] for w in json.load(f)], ["A", "B"])

    def test_전부_캐시에_있으면_조회하지_않는다(self):
        wd = os.path.join(self.run_dir, "workdata.json")
        self._write("workdata.json", [{"productId": "A"}])
        with mock.patch.object(run_names, "_run") as m, \
             contextlib.redirect_stdout(io.StringIO()):
            run_names._fill_workdata(self.run_dir, wd, [{"productId": "A"}], "python", 0)
        m.assert_not_called()



class AppendRerunIdempotencyTest(unittest.TestCase):
    """append 를 중단 후 다시 돌려도 같은 행이 두 번 들어가지 않는다 (2026-08-19 25-2 사고).

    **재현한 결함**: 재작업 회차는 `done_ids - redo_ids` 로 A열 이중실행 방어를 일부러
    뚫는다(재작업 = 새 행 추가). 그런데 그 면제가 *이번 run 이 방금 넣은 행*에도 걸려서,
    append 가 중간에 죽으면 재실행이 앞서 넣은 행을 통째로 다시 넣었다. 소진
    (`redo.json` → `.done`)은 **완주해야** 일어나므로 중단 경로에선 아무 방어도 없었다.

    실측: 178행 append 가 2분 타임아웃에 끊긴 뒤 재실행되어 71행이 127행 간격으로 재삽입.
    """

    def setUp(self):
        self.run_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.run_dir, True)
        os.makedirs(os.path.join(self.run_dir, "named"))
        os.makedirs(os.path.join(self.run_dir, "checked"))
        # 과거 회차에 P1·P2 가 이미 시트에 있고, 이번엔 둘 다 재작업 면제 대상이다.
        self.sheet_ids = {"P1", "P2"}
        self.appended_rows = []

        for n, pid in (("001", "P1"), ("002", "P2")):
            with open(os.path.join(self.run_dir, "named", f"named_{n}.json"), "w",
                      encoding="utf-8") as f:
                json.dump({"products": [{"productId": pid}]}, f)
            with open(os.path.join(self.run_dir, "checked", f"checked_{n}.json"), "w",
                      encoding="utf-8") as f:
                json.dump({"products": [{"productId": pid, "새상품명": f"이름{pid}",
                                         "상태": "생성완료"}]}, f)
        with open(os.path.join(self.run_dir, "redo.json"), "w", encoding="utf-8") as f:
            json.dump(sorted(self.sheet_ids), f)

    def _args(self):
        return argparse.Namespace(
            run_dir=self.run_dir, sheet="SHEET", tab=run_names.NAME_TAB,
            group_name="G", dry_run=False, no_related=True, sheet_map=None,
            allow_missing=True)

    def _append(self, fail_on=None):
        """cmd_append 실행. fail_on 이 주어지면 그 pid 배치의 append 에서 터뜨린다."""
        def _fake_append(sheet, tab, rows):
            pids = [r[0] for r in rows]
            if fail_on and fail_on in pids:
                raise RuntimeError("타임아웃 흉내")
            self.appended_rows.extend(pids)
            self.sheet_ids.update(pids)
            return len(rows)

        with mock.patch.object(run_names, "_run"), \
             mock.patch.object(run_names, "_audit_named", return_value=([], False, 0)), \
             mock.patch.object(run_names, "_done_ids",
                               side_effect=lambda *a, **k: set(self.sheet_ids)), \
             mock.patch.object(run_names, "_mark_matrix"), \
             mock.patch.object(run_names, "_retire_stale_rows"), \
             mock.patch.object(run_names, "_handoff_flip_suspect"), \
             mock.patch.object(run_names.sheet_io, "ensure_tab", return_value=False), \
             mock.patch.object(run_names, "_extend_header"), \
             mock.patch.object(run_names.sheet_io, "append_rows", _fake_append), \
             contextlib.redirect_stdout(io.StringIO()) as buf:
            try:
                run_names.cmd_append(self._args())
            except RuntimeError:
                pass  # 중단 흉내 — redo.json 은 소진되지 않은 채 남는다
        return buf.getvalue()

    def test_중단_후_재실행이_같은_행을_또_넣지_않는다(self):
        self._append(fail_on="P2")            # P1 만 들어가고 P2 에서 죽는다
        self.assertEqual(self.appended_rows, ["P1"])
        self.assertTrue(os.path.exists(os.path.join(self.run_dir, "redo.json")),
                        "중단이면 면제가 남는다 — 이게 결함의 전제조건이다")

        self._append()                        # 재실행
        self.assertEqual(self.appended_rows, ["P1", "P2"],
                         "P1 이 다시 들어가면 중복 행이 생긴 것이다")

    def test_이번_run_이_넣은_id_를_appended_json_에_남긴다(self):
        self._append(fail_on="P2")
        path = os.path.join(self.run_dir, "appended.json")
        self.assertTrue(os.path.exists(path), "중단 지점 전까지의 성공분이 남아야 한다")
        with open(path, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"SHEET": ["P1"]})

    def test_과거_회차_행에_대한_재작업_면제는_그대로다(self):
        # appended.json 이 없는 첫 실행에서는 A열에 P1·P2 가 있어도 둘 다 append 된다.
        self._append()
        self.assertEqual(self.appended_rows, ["P1", "P2"],
                         "재작업 면제가 과대차단되면 워커 비용만 쓰고 시트 0행이 된다")


class AppendedLedgerTest(unittest.TestCase):
    """`appended.json` 원장 — 시트별로 나눠 담고, 깨져도 append 를 막지 않는다."""

    def setUp(self):
        self.run_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.run_dir, True)

    def test_시트별로_분리해_담는다(self):
        run_names._appended_add(self.run_dir, "S1", ["P1", "P2"])
        run_names._appended_add(self.run_dir, "S2", ["P3"])
        self.assertEqual(run_names._appended_load(self.run_dir, "S1"), {"P1", "P2"})
        self.assertEqual(run_names._appended_load(self.run_dir, "S2"), {"P3"})

    def test_같은_시트에_누적하고_중복은_합친다(self):
        run_names._appended_add(self.run_dir, "S1", ["P1"])
        run_names._appended_add(self.run_dir, "S1", ["P1", "P2"])
        self.assertEqual(run_names._appended_load(self.run_dir, "S1"), {"P1", "P2"})

    def test_파일이_없으면_빈_집합(self):
        self.assertEqual(run_names._appended_load(self.run_dir, "S1"), set())

    def test_빈_목록은_파일을_만들지_않는다(self):
        run_names._appended_add(self.run_dir, "S1", [])
        self.assertFalse(os.path.exists(run_names._appended_path(self.run_dir)))

    def test_깨진_파일은_경고만_하고_빈_집합(self):
        with open(run_names._appended_path(self.run_dir), "w", encoding="utf-8") as f:
            f.write("{이건 JSON 이 아니다")
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(run_names._appended_load(self.run_dir, "S1"), set())
        self.assertIn("appended.json", err.getvalue())


class SyncStaleProgressTest(unittest.TestCase):
    """굳은 `진행중(…)` 되맞추기 (2026-08-19 25-2 실측 — §3⑥ 의 과거분).

    `진행중` 은 중간표시인데 `matrix.pending` 은 빈칸·재작업만 집으므로 pending 도 아니고
    prep 도 집지 않는다 — 한 번 찍히면 영영 굳고, 다음 세션은 "반영 대기"로 오해한다.
    실측 5건은 상품명 탭에서 이미 `보류(…)` 로 종결된 건이었다.
    """

    def setUp(self):
        self.marked = []
        self.mark = lambda s, col, tgt: self.marked.append((s, col, dict(tgt))) or len(tgt)

    def _rows(self, pairs):
        h = run_names.NAME_HEADER
        i_id, i_st = h.index("상품id"), h.index("상태")
        out = []
        for pid, st in pairs:
            r = [""] * len(h)
            r[i_id], r[i_st] = pid, st
            out.append(r)
        return out

    def _run(self, matrix_vals, tab_pairs):
        m = {pid: {"상품명": v} for pid, v in matrix_vals.items()}
        with mock.patch("eroomlib.gsheets.sheets_get", return_value=self._rows(tab_pairs)), \
             contextlib.redirect_stdout(io.StringIO()) as buf:
            n = run_names._sync_stale_progress("SHEET", m, run_names.NAME_TAB, mark=self.mark)
        return n, buf.getvalue()

    def test_탭이_종결됐으면_그_값으로_되맞춘다(self):
        n, _ = self._run({"P1": "진행중(미반영)"}, [("P1", "보류(표본의심)")])
        self.assertEqual(n, 1)
        self.assertEqual(self.marked[0][2], {"P1": "보류(표본의심)"})

    def test_같은_pid_여러_행이면_마지막_행이_최신이다(self):
        n, _ = self._run({"P1": "진행중(미반영)"},
                         [("P1", "검증실패"), ("P1", "반영완료")])
        self.assertEqual(self.marked[0][2], {"P1": "반영완료"})
        self.assertEqual(n, 1)

    def test_진행중이_아닌_현황판_값은_건드리지_않는다(self):
        # 현황판이 더 최신인 정상 케이스 — 삭제가 나중에 일어났거나 어휘만 다르다.
        n, _ = self._run({"P1": "상품삭제(제외카테고리·자동)", "P2": "완료"},
                         [("P1", "반영완료"), ("P2", "반영완료")])
        self.assertEqual(n, 0)
        self.assertEqual(self.marked, [])

    def test_탭도_진행중이면_되맞출_게_없다(self):
        n, _ = self._run({"P1": "진행중(미반영)"}, [("P1", "진행중(미반영)")])
        self.assertEqual(n, 0)

    def test_탭에_행이_없으면_그냥_둔다(self):
        n, _ = self._run({"P1": "진행중(미반영)"}, [("P9", "반영완료")])
        self.assertEqual(n, 0)

    def test_탭_조회_실패는_경고만_하고_prep_을_막지_않는다(self):
        m = {"P1": {"상품명": "진행중(미반영)"}}
        with mock.patch("eroomlib.gsheets.sheets_get", side_effect=RuntimeError("api")), \
             contextlib.redirect_stderr(io.StringIO()) as err, \
             contextlib.redirect_stdout(io.StringIO()):
            n = run_names._sync_stale_progress("SHEET", m, run_names.NAME_TAB, mark=self.mark)
        self.assertEqual(n, 0)
        self.assertIn("경고", err.getvalue())

    def test_현황판이_비면_시트를_읽지도_않는다(self):
        with mock.patch("eroomlib.gsheets.sheets_get") as g:
            self.assertEqual(run_names._sync_stale_progress("SHEET", {}, None, mark=self.mark), 0)
        g.assert_not_called()


class FirstOriginalNameTest(unittest.TestCase):
    """재작업이 **이미 가공된 이름**을 원본으로 삼던 결함 (2026-08-19 25-2 실측).

    E열은 prep 이 불사자의 *현재* 이름으로 채우는데, rename 한 상품은 그게 앞 회차
    결과물이다. 실측 65행이 앞 결과물을 재가공했고(3연속 1건) **15행은 원본==새것**으로
    워커 비용만 썼다. 되돌리기 경로(SKILL.md "원본은 E열")도 같이 끊긴다.
    """

    def _rows(self, triples):
        h = run_names.NAME_HEADER
        i_id, i_orig = h.index("상품id"), h.index("원본상품명")
        out = []
        for pid, orig in triples:
            r = [""] * len(h)
            r[i_id], r[i_orig] = pid, orig
            out.append(r)
        return out

    def _first(self, triples):
        with mock.patch("eroomlib.gsheets.sheets_get", return_value=self._rows(triples)):
            return run_names._first_original_names("SHEET", run_names.NAME_TAB)

    def test_가장_오래된_행의_원본을_지킨다(self):
        # 위에서 아래로 = 오래된 순. 2회차 행의 E열(가공본)이 이겨선 안 된다.
        got = self._first([("P1", "진짜 원본 이름"), ("P1", "1회차 결과물 기본형")])
        self.assertEqual(got, {"P1": "진짜 원본 이름"})

    def test_빈_원본은_건너뛰고_다음_행을_본다(self):
        got = self._first([("P1", ""), ("P1", "보류행 뒤의 원본")])
        self.assertEqual(got, {"P1": "보류행 뒤의 원본"})

    def test_이력이_없으면_빈_맵(self):
        self.assertEqual(self._first([]), {})

    def test_조회_실패는_종전_동작으로_떨어진다(self):
        with mock.patch("eroomlib.gsheets.sheets_get", side_effect=RuntimeError("api")), \
             contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(run_names._first_original_names("SHEET"), {})
        self.assertIn("경고", err.getvalue())

    def test_배치는_최초_원본을_우선_쓴다(self):
        tgt = {"P1": {"productId": "P1", "상품명": "1회차 결과물 기본형",
                      "원본상품명": "진짜 원본 이름", "카테고리": "C"}}
        with mock.patch.object(run_names, "_same_price_options", return_value=[]), \
             mock.patch.object(run_names, "_spec_view", return_value=[]):
            got = run_names._mk_product("P1", "C", tgt, {}, {}, {})
        self.assertEqual(got["원본상품명"], "진짜 원본 이름")

    def test_최초_원본이_없으면_현재_이름을_쓴다(self):
        tgt = {"P1": {"productId": "P1", "상품명": "현재 이름", "카테고리": "C"}}
        with mock.patch.object(run_names, "_same_price_options", return_value=[]), \
             mock.patch.object(run_names, "_spec_view", return_value=[]):
            got = run_names._mk_product("P1", "C", tgt, {}, {}, {})
        self.assertEqual(got["원본상품명"], "현재 이름")

if __name__ == "__main__":
    unittest.main(verbosity=2)
