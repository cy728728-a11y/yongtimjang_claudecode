#!/usr/bin/env python3
"""작업 매트릭스 회귀 테스트 — 시트 호출을 가짜로 갈아끼워 네트워크 없이 돈다.

    python .claude/lib/eroomlib/test_matrix.py

지키려는 계약:
  1. **멱등** — 같은 상태로 rebuild 를 두 번 돌려도 두 번째는 시트를 안 건드린다
  2. 열 통짜 되쓰기가 **대상 아닌 행의 기존 값을 보존**한다 (빠뜨리면 지워진다)
  3. `sync_products` 는 기존 행을 절대 안 건드리고 **없는 상품만** 추가한다
  4. 상품삭제는 어느 원장에서 알았든 이후 작업이 `해당없음`이 된다
  5. `pending` 이 "빈칸=미착수"만 고른다 (보류·진행중을 자동 재처리하지 않는다)
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eroomlib import matrix  # noqa: E402


class FakeSheet:
    """탭 이름 → 2차원 값. update/append 호출을 기록한다."""

    def __init__(self, tabs=None):
        self.tabs = {k: [list(r) for r in v] for k, v in (tabs or {}).items()}
        self.updates = []   # (range, values)
        self.appends = []   # (tab, rows)

    # --- eroomlib.gsheets 대체 ---
    def sheets_get(self, sid, rng):
        tab = rng.split("!")[0].strip("'")
        if tab not in self.tabs:
            raise RuntimeError(f"Unable to parse range: {rng}")
        return [list(r) for r in self.tabs[tab]]

    def sheets_update(self, sid, rng, values, value_input="RAW"):
        self.updates.append((rng, values))
        tab, a1 = rng.split("!")
        tab = tab.strip("'")
        col = "".join(c for c in a1.split(":")[0] if c.isalpha())
        row0 = int("".join(c for c in a1.split(":")[0] if c.isdigit()))
        ci = 0
        for ch in col:
            ci = ci * 26 + (ord(ch) - 64)
        ci -= 1
        grid = self.tabs.setdefault(tab, [])
        for k, vrow in enumerate(values):
            r = row0 - 1 + k
            while len(grid) <= r:
                grid.append([])
            while len(grid[r]) < ci + len(vrow):
                grid[r].append("")
            for j, v in enumerate(vrow):
                grid[r][ci + j] = v
        return {}

    def ensure_tab(self, sid, tab, header):
        if tab in self.tabs:
            return False
        self.tabs[tab] = [list(header)]
        return True

    def append_rows(self, sid, tab, rows):
        self.appends.append((tab, [list(r) for r in rows]))
        self.tabs.setdefault(tab, []).extend([list(r) for r in rows])
        return len(rows)


class MatrixBase(unittest.TestCase):
    def setUp(self):
        self.fs = FakeSheet()
        self._orig = (matrix.sheets_get, matrix.sheets_update, matrix.ensure_tab)
        matrix.sheets_get = self.fs.sheets_get
        matrix.sheets_update = self.fs.sheets_update
        matrix.ensure_tab = self.fs.ensure_tab
        import eroomlib.gsheets as gs
        self._orig_append = gs.append_rows
        gs.append_rows = self.fs.append_rows

    def tearDown(self):
        matrix.sheets_get, matrix.sheets_update, matrix.ensure_tab = self._orig
        import eroomlib.gsheets as gs
        gs.append_rows = self._orig_append

    def seed(self, rows):
        """00_진행 탭을 헤더 + rows 로 채운다."""
        self.fs.tabs[matrix.TAB] = [list(matrix.HEADER)] + [list(r) for r in rows]


PRODUCTS = [{"productId": "P1", "상품명": "무선 마우스"},
            {"productId": "P2", "상품명": "커튼링"},
            {"productId": "P3", "상품명": "자키 받침대"}]


class SyncTest(MatrixBase):
    def test_없는_상품만_추가하고_기존_행은_안_건드린다(self):
        self.seed([["P1", "무선 마우스", "완료", "완료", "", "", "", "", "", "", ""]])
        n = matrix.sync_products("S", PRODUCTS)
        self.assertEqual(n, 2)
        self.assertEqual([r[0] for r in self.fs.appends[0][1]], ["P2", "P3"])
        m = matrix.read("S")
        self.assertEqual(m["P1"]["카테고리"], "완료", "기존 행의 값이 훼손됐다")
        self.assertEqual(m["P2"]["카테고리"], "")

    def test_전부_이미_있으면_시트를_건드리지_않는다(self):
        self.seed([[p["productId"], p["상품명"]] + [""] * len(matrix.TASKS)
                   for p in PRODUCTS])
        self.assertEqual(matrix.sync_products("S", PRODUCTS), 0)
        self.assertFalse(self.fs.appends)


class MarkTest(MatrixBase):
    def test_대상_아닌_행의_기존_값을_보존한다(self):
        self.seed([["P1", "a", "완료", "완료", "", "", "", "", "", "", ""],
                   ["P2", "b", "완료", "보류(정체불명)", "", "", "", "", "", "", ""],
                   ["P3", "c", "완료", "", "", "", "", "", "", "", ""]])
        n = matrix.mark_many("S", "상품명", {"P1": "완료"})
        self.assertEqual(n, 1)
        m = matrix.read("S")
        self.assertEqual(m["P1"]["상품명"], "완료")
        self.assertEqual(m["P2"]["카테고리"], "보류(정체불명)", "다른 열이 지워졌다")
        self.assertEqual(m["P3"]["수집"], "완료", "대상 아닌 행이 지워졌다")

    def test_바뀐_게_없으면_시트를_치지_않는다(self):
        self.seed([["P1", "a", "완료", "완료", "완료"] + [""] * 6])
        self.assertEqual(matrix.mark_many("S", "상품명", {"P1": "완료"}), 0)
        self.assertFalse(self.fs.updates)

    def test_모르는_작업이면_바로_터진다(self):
        self.seed([["P1", "a"] + [""] * len(matrix.TASKS)])
        with self.assertRaises(KeyError):
            matrix.mark_many("S", "없는작업", {"P1": "완료"})

    def test_단건_mark_는_칸_하나만_친다(self):
        self.seed([["P1", "a"] + [""] * len(matrix.TASKS),
                   ["P2", "b"] + [""] * len(matrix.TASKS)])
        self.assertTrue(matrix.mark("S", "P2", "옵션", "완료"))
        rng = self.fs.updates[-1][0]
        self.assertTrue(rng.endswith("!F3"), rng)  # 옵션 = 6번째 열(F), P2 = 3행
        self.assertFalse(matrix.mark("S", "없는id", "옵션", "완료"))


class PendingTest(MatrixBase):
    def test_빈칸만_미착수로_본다(self):
        self.seed([["P1", "a", "완료", "완료", "", "", "", "", "", "", ""],
                   ["P2", "b", "완료", "보류(정체불명)", "", "", "", "", "", "", ""],
                   ["P3", "c", "완료", "완료", "진행중(미반영)", "", "", "", "", "", ""],
                   ["P4", "d", "완료", "해당없음", "해당없음", "", "", "", "", "", ""]])
        m = matrix.read("S")
        self.assertEqual(matrix.pending(m, "카테고리"), [])
        self.assertEqual(matrix.pending(m, "상품명"), ["P1", "P2"])
        self.assertEqual(sorted(matrix.pending(m, "옵션")), ["P1", "P2", "P3", "P4"])


class RedoTest(MatrixBase):
    """재작업 이관 — 단계 A 가 단계 B 에 넘긴 일감이 살아남아 다시 잡히는가."""

    def test_표시값_파싱(self):
        v = matrix.redo_value("대표색 불일치", "옵션")
        self.assertEqual(v, "재작업(옵션: 대표색 불일치)")
        self.assertTrue(matrix.is_redo(v))
        self.assertEqual(matrix.redo_reason(v), "옵션: 대표색 불일치")
        self.assertFalse(matrix.is_redo("완료"))
        self.assertEqual(matrix.redo_reason("완료"), "")
        # 발신 단계 없이도 만들 수 있다(사람이 직접 찍는 경우)
        self.assertEqual(matrix.redo_value("카테고리 변경"), "재작업(카테고리 변경)")

    def test_flag_가_칸_하나만_친다(self):
        self.seed([["P1", "a", "완료", "완료", "완료"] + [""] * 6,
                   ["P2", "b", "완료", "완료", "완료"] + [""] * 6])
        self.assertTrue(matrix.flag("S", "P1", "썸네일", "대표색 불일치", from_task="옵션"))
        self.assertEqual(len(self.fs.updates), 1)
        m = matrix.read("S")
        self.assertEqual(m["P1"]["썸네일"], "재작업(옵션: 대표색 불일치)")
        self.assertEqual(m["P2"]["썸네일"], "", "다른 행이 오염됐다")

    def test_삭제_상품에는_일감을_넘기지_않는다(self):
        self.seed([["P1", "a", "해당없음", "해당없음", "해당없음", "해당없음",
                    "해당없음"] + [""] * 4])
        self.assertFalse(matrix.flag("S", "P1", "썸네일", "x", from_task="옵션"))
        self.assertFalse(self.fs.updates)

    def test_현황판에_없는_상품이면_거짓(self):
        self.seed([["P1", "a"] + [""] * len(matrix.TASKS)])
        self.assertFalse(matrix.flag("S", "ZZ", "썸네일", "x"))

    def test_pending_은_기본으로_재작업을_함께_잡는다(self):
        self.seed([["P1", "a", "완료", "완료", "완료", "완료",
                    "재작업(옵션: 대표색 불일치)"] + [""] * 4,
                   ["P2", "b", "완료", "완료", "완료", "완료"] + [""] * 4,
                   ["P3", "c", "완료", "완료", "완료", "완료", "보류(확인요)"] + [""] * 4])
        m = matrix.read("S")
        self.assertEqual(sorted(matrix.pending(m, "썸네일")), ["P1", "P2"])
        self.assertEqual(matrix.pending(m, "썸네일", include_redo=False), ["P2"],
                         "옵트아웃하면 신규 미착수만")
        self.assertNotIn("P3", matrix.pending(m, "썸네일"), "보류는 자동 재처리 안 함")

    def test_빈칸에_사유를_실어도_대상에서_빠지지_않는다(self):
        """대상 여부와 사유 전달을 한 값에 묶었으므로 둘 다 켜져 있어야 앞뒤가 맞는다."""
        self.seed([["P1", "a", "완료", "완료", "완료", "완료"] + [""] * 4])
        matrix.flag("S", "P1", "썸네일", "대표색 불일치", from_task="옵션")
        m = matrix.read("S")
        self.assertIn("P1", matrix.pending(m, "썸네일"), "빈칸에 찍었더니 대상에서 빠졌다")
        self.assertEqual(matrix.redo_pending(m, "썸네일"), {"P1": "옵션: 대표색 불일치"})

    def test_완료된_단계도_재작업이면_다시_잡힌다(self):
        """용쌤1-1 상품명 재시도 143건 = 원장은 '완료'인데 다시 해야 하는 건."""
        self.seed([["P1", "a", "완료", "완료", "재작업(카테고리: 대분류 변경)"] + [""] * 6,
                   ["P2", "b", "완료", "완료", "완료"] + [""] * 6])
        m = matrix.read("S")
        self.assertEqual(matrix.pending(m, "상품명"), ["P1"])
        self.assertEqual(matrix.pending(m, "상품명", include_redo=False), [],
                         "옵트아웃하면 완료된 건 안 잡힌다")
        self.assertEqual(matrix.redo_pending(m, "상품명"),
                         {"P1": "카테고리: 대분류 변경"})

    def test_flag_many_는_열_통짜_1회로_쓴다(self):
        self.seed([["P1", "a", "완료"] + [""] * 8,
                   ["P2", "b", "완료"] + [""] * 8,
                   ["P3", "c", "해당없음", "해당없음", "해당없음", "해당없음",
                    "해당없음"] + [""] * 4])
        n = matrix.flag_many("S", "썸네일",
                             {"P1": "대표색 불일치", "P2": "워터마크", "P3": "무시됨"},
                             from_task="옵션")
        self.assertEqual(n, 2, "삭제 상품은 빠져야 한다")
        self.assertEqual(len(self.fs.updates), 1, "열 통짜 1회여야 한다")
        m = matrix.read("S")
        self.assertEqual(m["P1"]["썸네일"], "재작업(옵션: 대표색 불일치)")
        self.assertEqual(m["P2"]["썸네일"], "재작업(옵션: 워터마크)")
        self.assertEqual(m["P3"]["썸네일"], "해당없음")

    def test_재작업을_마치면_완료가_덮어쓴다(self):
        self.seed([["P1", "a", "완료", "완료", "재작업(카테고리: 대분류 변경)"] + [""] * 6])
        matrix.mark_many("S", "상품명", {"P1": "완료"})
        self.assertEqual(matrix.read("S")["P1"]["상품명"], "완료")

    def test_rebuild_가_재작업_표시를_지우지_않는다(self):
        """원장은 '옛 작업을 완료했다'고만 말한다 — 재작업은 되살릴 수 없는 정보다."""
        self.seed([["P1", "a", "완료", "완료", "재작업(카테고리: 대분류 변경)"] + [""] * 6])
        self.fs.tabs["시트1"] = [["상품id"] + [""] * 6,
                                 ["P1"] + [""] * 5 + ["자동저장완료"]]
        self.fs.tabs["상품명"] = [["상품id", "상태"], ["P1", "반영완료"]]
        matrix.rebuild("S", [{"productId": "P1", "상품명": "a"}], log=lambda *a: None)
        self.assertEqual(matrix.read("S")["P1"]["상품명"],
                         "재작업(카테고리: 대분류 변경)")


class MapTest(unittest.TestCase):
    def test_카테고리_상태_매핑(self):
        self.assertEqual(matrix.map_catfix("자동저장완료"), "완료")
        self.assertEqual(matrix.map_catfix("저장완료"), "완료")
        self.assertEqual(matrix.map_catfix("이미정확"), "완료")
        self.assertEqual(matrix.map_catfix(""), "")
        self.assertEqual(matrix.map_catfix("상품삭제(이룸님)"), "해당없음")
        # 저장 안 된 것들은 원값을 그대로 남긴다 — 왜 안 됐는지가 현황판에 보여야 한다
        self.assertEqual(matrix.map_catfix("매칭불가"), "매칭불가")
        self.assertEqual(matrix.map_catfix("승인보류"), "승인보류")
        self.assertEqual(matrix.map_catfix("변경대상"), "변경대상")

    def test_상품명_상태_매핑(self):
        self.assertEqual(matrix.map_name("반영완료"), "완료")
        self.assertEqual(matrix.map_name("생성완료"), "진행중(미반영)")
        self.assertEqual(matrix.map_name("스킵(카테고리미설정)"), "스킵(카테고리미설정)")
        self.assertEqual(matrix.map_name("상품삭제(이룸님)"), "해당없음")


class RebuildTest(MatrixBase):
    def setUp(self):
        super().setUp()
        self.fs.tabs["시트1"] = [
            ["상품id", "상품명", "이전카테고리", "변경카테고리", "검색어", "확신도", "상태", "기록일"],
            ["P1", "무선 마우스", "", "디지털>마우스", "무선마우스", "100%", "자동저장완료", "2026-07-20"],
            ["P2", "커튼링", "", "", "커튼링", "", "매칭불가", "2026-07-20"],
        ]
        self.fs.tabs["상품명"] = [
            ["상품id", "작업일", "마켓그룹", "카테고리", "원본상품명", "새상품명", "상태"],
            ["P1", "2026-07-25", "G", "디지털>마우스", "무선 마우스", "새이름", "반영완료"],
        ]

    def test_원장에서_역산해_채운다(self):
        matrix.rebuild("S", PRODUCTS, log=lambda m: None)
        m = matrix.read("S")
        self.assertEqual(len(m), 3)
        self.assertEqual(m["P1"]["수집"], "완료")
        self.assertEqual(m["P1"]["카테고리"], "완료")
        self.assertEqual(m["P1"]["상품명"], "완료")
        self.assertEqual(m["P2"]["카테고리"], "매칭불가")
        self.assertEqual(m["P2"]["상품명"], "", "원장에 없는 건 미착수여야 한다")
        self.assertEqual(m["P3"]["카테고리"], "", "원장에 없는 건 미착수여야 한다")
        self.assertEqual(m["P3"]["옵션"], "", "담당 스킬이 없는 작업은 빈칸")

    def test_두_번_돌려도_두_번째는_시트를_안_친다(self):
        matrix.rebuild("S", PRODUCTS, log=lambda m: None)
        self.fs.updates.clear()
        self.fs.appends.clear()
        matrix.rebuild("S", PRODUCTS, log=lambda m: None)
        self.assertFalse(self.fs.appends, "같은 상품을 또 추가했다")
        self.assertFalse(self.fs.updates, "바뀐 게 없는데 시트를 갱신했다")

    def test_상품삭제는_이후_작업이_해당없음이_된다(self):
        self.fs.tabs["상품명"].append(
            ["P2", "2026-07-25", "G", "", "커튼링", "", "상품삭제(이룸님)"])
        matrix.rebuild("S", PRODUCTS, log=lambda m: None)
        m = matrix.read("S")
        self.assertEqual(m["P2"]["상품명"], "해당없음")
        self.assertEqual(m["P2"]["카테고리"], "해당없음",
                         "한쪽 원장에서 삭제를 알았으면 다른 작업도 해당없음이어야 한다")
        # 담당 스킬이 아직 없는 작업까지 전부 — 안 그러면 나중에 없는 상품이 대상에 잡힌다
        for t in ("옵션", "썸네일", "상세", "지재권", "배송비", "업로드"):
            self.assertEqual(m["P2"][t], "해당없음", f"{t} 열이 미착수로 남았다")
        self.assertEqual(matrix.pending(m, "옵션"), ["P1", "P3"])

    def test_상품명_탭에_같은_상품이_여러_행이면_마지막이_최신(self):
        self.fs.tabs["상품명"].append(
            ["P1", "2026-07-27", "G", "디지털>마우스", "무선 마우스", "재작업이름", "생성완료"])
        matrix.rebuild("S", PRODUCTS, log=lambda m: None)
        self.assertEqual(matrix.read("S")["P1"]["상품명"], "진행중(미반영)")

    def test_원장_탭이_없어도_완주한다(self):
        del self.fs.tabs["상품명"]
        matrix.rebuild("S", PRODUCTS, log=lambda m: None)
        m = matrix.read("S")
        self.assertEqual(m["P1"]["카테고리"], "완료")
        self.assertEqual(m["P1"]["상품명"], "")

    def test_헤더가_짧으면_뒤에만_확장한다(self):
        self.fs.tabs[matrix.TAB] = [list(matrix.HEADER[:5]),
                                    ["P1", "무선 마우스", "완료", "완료", ""]]
        matrix.ensure("S")
        self.assertEqual([str(c) for c in self.fs.tabs[matrix.TAB][0]], list(matrix.HEADER))
        self.assertEqual(matrix.read("S")["P1"]["카테고리"], "완료")

    def test_1행이_헤더가_아니면_헤더_행을_끼워_넣는다(self):
        """탭 생성 직후 헤더 쓰기가 실패하면 append 가 1행부터 채운다(2026-07-28 실제 사고).
        그 상태면 read 가 작업 열을 하나도 못 알아본다."""
        self.fs.tabs[matrix.TAB] = [["P1", "무선 마우스", "완료"],
                                    ["P2", "커튼링", "완료"]]
        inserted = []
        matrix._insert_header_row = lambda sheet, tab: (
            inserted.append(tab),
            self.fs.tabs[tab].insert(0, list(matrix.HEADER)))
        matrix.ensure("S")
        self.assertEqual(inserted, [matrix.TAB])
        m = matrix.read("S")
        self.assertEqual(set(m), {"P1", "P2"})
        self.assertEqual(m["P1"]["수집"], "완료", "작업 열을 못 알아봤다")

    def test_헤더_순서가_어긋난_시트는_손대지_않는다(self):
        self.fs.tabs[matrix.TAB] = [["상품id", "엉뚱한열"], ["P1", "x"]]
        matrix.ensure("S")
        self.assertEqual([str(c) for c in self.fs.tabs[matrix.TAB][0]],
                         ["상품id", "엉뚱한열"])


class LedgerTest(MatrixBase):
    """이력 열 — **저장이 덮지 않는 자리** (2026-08-19 2-2 4회차 §8).

    썸네일↔옵션 왕복 종결 판정이 `옵션` 작업 열 문자열을 근거로 삼고 있었는데,
    옵션정리가 저장에 성공하면 그 열이 `완료` 로 덮여 근거가 사라졌다 —
    **옵션이 저장에 성공할수록 왕복이 안 닫히는** 뒤집힌 구조였다.
    """

    def seed_one(self, ledger=""):
        self.seed([["P1", "무선 마우스"] + [""] * len(matrix.TASKS) + [ledger]])

    def test_이력_열은_작업_열이_아니다(self):
        # 작업 열이면 `mark_many`·`rebuild` 가 덮는다 — 그게 이 열을 만든 이유의 반대다.
        self.assertNotIn(matrix.LEDGER, matrix.TASKS)
        self.assertEqual(matrix.HEADER[-1], matrix.LEDGER)

    def test_토큰을_덧붙이고_읽는다(self):
        self.seed_one()
        self.assertEqual(matrix.note_many("S", {"P1": "실물기준없음"}), 1)
        self.assertTrue(matrix.has_note(matrix.read("S"), "P1", "실물기준없음"))

    def test_같은_토큰을_두_번_붙이지_않는다(self):
        self.seed_one("실물기준없음")
        self.assertEqual(matrix.note_many("S", {"P1": "실물기준없음"}), 0)
        self.assertFalse(self.fs.updates, "바뀐 게 없으면 시트를 건드리지 않는다")

    def test_다른_토큰은_기존_것을_지우지_않는다(self):
        self.seed_one("실물기준없음")
        matrix.note_many("S", {"P1": "품목대조"})
        self.assertEqual(matrix.notes(matrix.read("S")["P1"]),
                         ["실물기준없음", "품목대조"])

    def test_작업_열_저장이_이력을_덮지_않는다(self):
        """이게 이 열의 존재 이유다 — 옵션 저장(`완료`)이 근거를 지우면 안 된다."""
        self.seed_one("실물기준없음")
        matrix.mark_many("S", "옵션", {"P1": "완료"})
        m = matrix.read("S")
        self.assertEqual(m["P1"]["옵션"], "완료")
        self.assertTrue(matrix.has_note(m, "P1", "실물기준없음"))

    def test_rebuild_도_이력을_보존한다(self):
        self.seed_one("실물기준없음")
        matrix.rebuild("S", PRODUCTS[:1], log=lambda *a: None)
        self.assertTrue(matrix.has_note(matrix.read("S"), "P1", "실물기준없음"))

    def test_열이_없는_옛_시트는_헤더부터_붙이고_쓴다(self):
        """헤더 없이 12열째에 값만 쓰면 `read` 가 **열 이름으로 못 찾아** 영영 안 읽는다."""
        self.fs.tabs[matrix.TAB] = [list(matrix.HEADER[:-1]),
                                    ["P1", "무선 마우스"] + [""] * len(matrix.TASKS)]
        self.assertEqual(matrix.note_many("S", {"P1": "실물기준없음"}), 1)
        self.assertEqual(self.fs.tabs[matrix.TAB][0][-1], matrix.LEDGER,
                         "헤더가 안 붙었다 — 값은 보이는데 코드는 못 읽는다")
        self.assertTrue(matrix.has_note(matrix.read("S"), "P1", "실물기준없음"))

    def test_열_순서가_어긋난_시트에는_쓰지_않는다(self):
        """`ensure` 가 확장을 거부한 시트다 — 엉뚱한 열에 쓰느니 안 쓴다."""
        self.fs.tabs[matrix.TAB] = [["상품id", "엉뚱한열"], ["P1", "x"]]
        self.assertEqual(matrix.note_many("S", {"P1": "실물기준없음"}), 0)

    def test_이력_열이_없는_옛_시트도_읽힌다(self):
        # 헤더가 11열이던 시절 시트. `ensure` 가 확장하기 전에도 read 가 죽으면 안 된다.
        self.fs.tabs[matrix.TAB] = [list(matrix.HEADER[:-1]),
                                    ["P1", "무선 마우스"] + [""] * len(matrix.TASKS)]
        m = matrix.read("S")
        self.assertEqual(matrix.notes(m["P1"]), [])
        self.assertFalse(matrix.has_note(m, "P1", "실물기준없음"))


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    unittest.main(verbosity=2)
