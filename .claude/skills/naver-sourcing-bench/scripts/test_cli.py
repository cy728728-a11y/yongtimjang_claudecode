# -*- coding: utf-8 -*-
import json

import pytest

import sheet_schema as S
import sourcing_bench as C


class FakeSheet:
    def __init__(self, scan_rows=None, bench_rows=None):
        self.tabs = {S.SCAN_TAB: scan_rows or [], S.BENCH_TAB: bench_rows or []}
        self.cells = []

    def read(self, tab):
        return [list(r) for r in self.tabs[tab]]

    def append(self, tab, rows):
        self.tabs[tab] += rows
        return len(rows)

    def set_cell(self, tab, r, c, v):
        self.cells.append((tab, r, c, v))


def prod(rank, review, price="15,000", url=None):
    return {"순위": rank, "상품명": f"p{rank}", "url": url or f"https://smartstore.naver.com/s/products/{rank}",
            "마켓명": "s", "가격": price, "리뷰수": review, "광고": False, "카테고리": ["a", "b", "c", "d"]}


MASTER = {"카테고리": [
    {"id": "2", "last": False, "경로정규화": "A > B"},
    {"id": "10", "last": True, "경로정규화": "A > B > C1"},
    {"id": "11", "last": True, "경로정규화": "A > B > C2"},
]}
OPTS = {"sleep": 0, "sleepMax": 0}


def test_require_login_blocks():
    with pytest.raises(SystemExit) as e:
        C.require_login(run=lambda *a: [{"kind": "login", "loggedIn": False}])
    assert e.value.code == 3


def test_require_login_passes():
    C.require_login(run=lambda *a: [{"kind": "login", "loggedIn": True}])


def test_scan_sorted_desc_and_checkpoint(tmp_path):
    pages = {"10": [prod(1, 1500)], "11": [prod(1, 2000), prod(2, 1200)]}
    calls = []

    def run(name, items, opts, t):
        calls.append([i["코드"] for i in items])
        return [{"kind": "page", "key": i["코드"], "상태": "성공", "products": pages[i["코드"]]} for i in items]

    sh = FakeSheet()
    ck = tmp_path / "scan.json"
    n = C.do_scan(sh, MASTER, "A>B", ck, run, "2026-10-02", OPTS)
    assert n == 2
    assert [r[5] for r in sh.tabs[S.SCAN_TAB]] == ["11", "10"]       # 리뷰1000+ 많은 순
    # 재실행: 체크포인트가 있으니 aside 를 다시 부르지 않고, 이미 시트에 있는 코드는 안 쓴다
    calls.clear()
    assert C.do_scan(sh, MASTER, "A>B", ck, run, "2026-10-02", OPTS) == 0
    assert calls == []


def test_scan_captcha_saves_partial_and_exits4(tmp_path):
    def run(name, items, opts, t):
        return [{"kind": "page", "key": "10", "상태": "성공", "products": [prod(1, 1500)]},
                {"kind": "page", "key": "11", "상태": "캡챠감지", "products": []}]

    ck = tmp_path / "scan.json"
    with pytest.raises(SystemExit) as e:
        C.do_scan(FakeSheet(), MASTER, "A>B", ck, run, "2026-10-02", OPTS)
    assert e.value.code == 4
    assert list(json.loads(ck.read_text(encoding="utf-8"))["done"]) == ["10"]


def test_bench_appends_filtered_and_skips_existing_url(tmp_path):
    existing = [["a", "b", "c", "d", "kw", "s", "https://smartstore.naver.com/s/products/1"]]
    sh = FakeSheet(bench_rows=existing)

    def run(name, items, opts, t):
        if name == "search":
            return [{"kind": "page", "key": "kw", "상태": "성공",
                     "products": [prod(1, 900), prod(2, 800), prod(3, 100), prod(4, 900, "9,000")]}]
        return [{"kind": "detail", "key": i["url"], "상태": "성공", "options": [{"이름": "x", "가격": 14000}]}
                for i in items]

    n = C.do_bench(sh, "kw", tmp_path / "b.json", run, "2026-10-02", OPTS)
    assert n == 1
    row = sh.tabs[S.BENCH_TAB][-1]
    assert row[6] == "https://smartstore.naver.com/s/products/2" and row[20] == 14000


def test_bench_detail_failure_marks_manual(tmp_path):
    def run(name, items, opts, t):
        if name == "search":
            return [{"kind": "page", "key": "kw", "상태": "성공", "products": [prod(1, 900)]}]
        return [{"kind": "detail", "key": items[0]["url"], "상태": "파싱실패", "options": None}]

    sh = FakeSheet()
    C.do_bench(sh, "kw", tmp_path / "b.json", run, "2026-10-02", OPTS)
    assert sh.tabs[S.BENCH_TAB][-1][23] == "옵션수동"


def test_bench_from_scan_marks_done(tmp_path):
    row = ["2026-10-02", "A", "B", "C1", "", "10", 3, "x", "압축봉", "", "", "", ""]
    sh = FakeSheet(scan_rows=[row, ["2026-10-02", "A", "B", "C2", "", "11", 1, "y", "", "", "", "", ""]])

    def run(name, items, opts, t):
        if name == "search":
            return [{"kind": "page", "key": "압축봉", "상태": "성공", "products": [prod(1, 900)]}]
        return [{"kind": "detail", "key": items[0]["url"], "상태": "성공", "options": [{"이름": "x", "가격": 15000}]}]

    assert C.bench_from_scan(sh, tmp_path, run, "2026-10-02", OPTS) == 1
    assert sh.cells == [(S.SCAN_TAB, 0, S.SCAN_COL["벤치완료"], "Y")]
