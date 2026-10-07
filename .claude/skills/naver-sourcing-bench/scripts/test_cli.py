# -*- coding: utf-8 -*-
import json

import pytest

import sheet_schema as S
import sourcing_bench as C


class FakeSheet:
    def __init__(self, scan_rows=None, bench_rows=None):
        self.tabs = {S.SCAN_TAB: scan_rows or [], S.BENCH_TAB: bench_rows or []}
        self.cells = []
        self.updates, self.deleted = [], []

    def read(self, tab):
        return [list(r) for r in self.tabs[tab]]

    def append(self, tab, rows):
        self.tabs[tab] += rows
        return len(rows)

    def set_cell(self, tab, r, c, v):
        self.cells.append((tab, r, c, v))

    def update_cells(self, tab, cells):
        self.updates.append((tab, list(cells)))
        for r, c, v in cells:
            row = self.tabs[tab][r]
            row += [""] * (c + 1 - len(row))
            row[c] = v

    def delete_rows(self, tab, idx):
        self.deleted.append((tab, sorted(set(idx), reverse=True)))
        for r in sorted(set(idx), reverse=True):
            del self.tabs[tab][r]


def prod(rank, review, price="15,000", url=None):
    return {"순위": rank, "상품명": f"p{rank}", "url": url or f"https://smartstore.naver.com/s/products/{rank}",
            "마켓명": "s", "가격": price, "리뷰수": review, "광고": False, "카테고리": ["a", "b", "c", "d"]}


MASTER = {"카테고리": [
    {"id": "2", "last": False, "경로정규화": "A > B"},
    {"id": "10", "last": True, "경로정규화": "A > B > C1"},
    {"id": "11", "last": True, "경로정규화": "A > B > C2"},
]}
OPTS = {"sleep": 0, "sleepMax": 0}


def opt_probe(url, 상태="성공", combos=None, price="12,900"):
    """options 드라이버 원시 결과 모양."""
    return {"kind": "options", "key": url, "상태": 상태, "priceText": f"상품 가격\n{price}원",
            "combos": combos or []}


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
        return [opt_probe(i["url"], combos=[["x"]], price="14,000") for i in items]

    n = C.do_bench(sh, "kw", tmp_path / "b.json", run, "2026-10-02", OPTS)
    assert n == 1
    row = sh.tabs[S.BENCH_TAB][-1]
    assert row[6] == "https://smartstore.naver.com/s/products/2" and row[S.COL_REP] == 14000


def test_bench_detail_failure_marks_manual(tmp_path):
    def run(name, items, opts, t):
        if name == "search":
            return [{"kind": "page", "key": "kw", "상태": "성공", "products": [prod(1, 900)]}]
        return [opt_probe(items[0]["url"], 상태="읽기실패")]

    sh = FakeSheet()
    C.do_bench(sh, "kw", tmp_path / "b.json", run, "2026-10-02", OPTS)
    assert sh.tabs[S.BENCH_TAB][-1][S.COL_STATUS] == "옵션수동"


def test_bench_from_scan_marks_done(tmp_path):
    row = ["2026-10-02", "A", "B", "C1", "", "10", 3, "x", "압축봉", "", "", "", ""]
    sh = FakeSheet(scan_rows=[row, ["2026-10-02", "A", "B", "C2", "", "11", 1, "y", "", "", "", "", ""]])

    def run(name, items, opts, t):
        if name == "search":
            return [{"kind": "page", "key": "압축봉", "상태": "성공", "products": [prod(1, 900)]}]
        return [opt_probe(items[0]["url"], combos=[["x"]], price="15,000")]

    assert C.bench_from_scan(sh, tmp_path, run, "2026-10-02", OPTS) == 1
    assert sh.cells == [(S.SCAN_TAB, 0, S.SCAN_COL["벤치완료"], "Y")]


def test_bench_detail_driver_missing_marks_manual(tmp_path):
    def run(name, items, opts, t):
        if name == "search":
            return [{"kind": "page", "key": "kw", "상태": "성공", "products": [prod(1, 900)]}]
        raise RuntimeError("드라이버 파일 읽기 실패: detail")

    sh = FakeSheet()
    assert C.do_bench(sh, "kw", tmp_path / "b.json", run, "2026-10-02", OPTS) == 1
    assert sh.tabs[S.BENCH_TAB][-1][S.COL_STATUS] == "옵션수동"


def test_cli_bench_options_on_by_default():
    assert C.build_parser().parse_args(["bench", "--keyword", "x"]).no_options is False
    assert C.build_parser().parse_args(["bench", "--keyword", "x", "--no-options"]).no_options is True
    a = C.build_parser().parse_args(["options", "--keyword", "바지걸이"])
    assert a.cmd == "options" and a.keyword == "바지걸이"


def test_scan_failed_page_not_cached(tmp_path):
    state = {"n": 0}

    def run(name, items, opts, t):
        state["n"] += 1
        return [{"kind": "page", "key": i["코드"], "상태": "파싱실패", "error": "x", "products": []} for i in items]

    ck = tmp_path / "scan.json"
    C.do_scan(FakeSheet(), MASTER, "A>B", ck, run, "2026-10-02", OPTS)
    C.do_scan(FakeSheet(), MASTER, "A>B", ck, run, "2026-10-02", OPTS)
    assert state["n"] == 2                      # 실패 페이지는 재실행 때 다시 연다


def test_bench_from_scan_failed_search_not_marked(tmp_path):
    row = ["2026-10-02", "A", "B", "C1", "", "10", 3, "x", "압축봉", "", "", "", ""]
    sh = FakeSheet(scan_rows=[row])

    def run(name, items, opts, t):
        return [{"kind": "page", "key": "압축봉", "상태": "파싱실패", "products": []}]

    assert C.bench_from_scan(sh, tmp_path, run, "2026-10-02", OPTS) == 0
    assert sh.cells == []


# ---- 옵션 자동 수집 (quick-261002-mbo) ----

CAT_URL = "https://search.shopping.naver.com/catalog/555"


def _bench_run(products, by_url, calls=None):
    """search 는 products, options 는 url → 원시결과 함수."""
    def run(name, items, opts, t):
        if name == "search":
            return [{"kind": "page", "key": "kw", "상태": "성공", "products": products}]
        assert name == "options"
        assert opts.get("maxCombos") == 50
        if calls is not None:
            calls.append([i["url"] for i in items])
        out = []
        for i in items:
            r = by_url(i["url"])
            out.append(r)
            if r.get("상태") in C.STOP:
                break
        return out
    return run


def test_bench_over_limit_not_appended(tmp_path):
    many = [[f"o{i}"] for i in range(51)]
    run = _bench_run([prod(1, 900), prod(2, 900)],
                     lambda u: opt_probe(u, combos=many) if u.endswith("/1") else opt_probe(u, 상태="옵션초과"))
    sh = FakeSheet()
    assert C.do_bench(sh, "kw", tmp_path / "b.json", run, "2026-10-02", OPTS) == 0
    assert sh.tabs[S.BENCH_TAB] == []


def test_bench_single_item(tmp_path):
    run = _bench_run([prod(1, 900)], lambda u: opt_probe(u, 상태="단품"))
    sh = FakeSheet()
    C.do_bench(sh, "kw", tmp_path / "b.json", run, "2026-10-02", OPTS)
    row = sh.tabs[S.BENCH_TAB][-1]
    assert row[8] == 1 and row[9] == "단품:12,900" and row[S.COL_REP] == 12900 and row[S.COL_STATUS] == ""


def test_bench_catalog_not_opened(tmp_path):
    calls = []
    run = _bench_run([prod(1, 900, url=CAT_URL), prod(2, 900)],
                     lambda u: opt_probe(u, combos=[["화이트", "10개 (+1,000원)"]]), calls)
    sh = FakeSheet()
    assert C.do_bench(sh, "kw", tmp_path / "b.json", run, "2026-10-02", OPTS) == 2
    assert all(CAT_URL not in c for c in calls)
    cat_row, ok_row = sh.tabs[S.BENCH_TAB]
    assert cat_row[8] == "" and cat_row[9] == "" and cat_row[S.COL_STATUS] == "옵션수동"
    assert ok_row[8] == 1 and ok_row[9] == "화이트-10개:13,900" and ok_row[S.COL_REP] == 13900


def test_bench_captcha_exit4_then_resume(tmp_path):
    calls = []
    state = {"captcha": True}

    def by_url(u):
        if u.endswith("/2") and state["captcha"]:
            return opt_probe(u, 상태="캡챠감지")
        return opt_probe(u, combos=[["x"]])

    run = _bench_run([prod(1, 900), prod(2, 900)], by_url, calls)
    sh = FakeSheet()
    ck = tmp_path / "b.json"
    with pytest.raises(SystemExit) as e:
        C.do_bench(sh, "kw", ck, run, "2026-10-02", OPTS)
    assert e.value.code == 4 and sh.tabs[S.BENCH_TAB] == []
    assert list(json.loads(ck.read_text(encoding="utf-8"))["details"]) == [
        "https://smartstore.naver.com/s/products/1"]
    state["captcha"], calls[:] = False, []
    assert C.do_bench(sh, "kw", ck, run, "2026-10-02", OPTS) == 2
    assert calls == [["https://smartstore.naver.com/s/products/2"]]


def _cand(n, kw="바지걸이", opt_cnt="", url=None, price=15000):
    """후보 탭 행(26열)."""
    r = ["a", "b", "c", "d", kw, "s", url or f"https://smartstore.naver.com/s/products/{n}", f"p{n}",
         opt_cnt, "", "", "", "", "", "", "", "", "", "", "", "", "", price, "2026-10-01", 900, "" if opt_cnt else "옵션수동"]
    return r


def test_refill_fill_delete_manual(tmp_path):
    rows = [_cand(1), _cand(2), _cand(3), _cand(4, url=CAT_URL), _cand(5, opt_cnt=2), _cand(6, kw="다른")]
    sh = FakeSheet(bench_rows=rows)
    calls = []

    def run(name, items, opts, t):
        assert name == "options"
        calls.append([i["url"] for i in items])
        res = {"1": opt_probe("", combos=[["흰 (+500원)"], ["검"]]),
               "2": opt_probe("", 상태="옵션초과"),
               "3": opt_probe("", 상태="읽기실패")}
        out = []
        for i in items:
            d = dict(res[i["url"].rsplit("/", 1)[1]])
            d["key"] = i["url"]
            out.append(d)
        return out

    ck = tmp_path / "o.json"
    r = C.do_refill(sh, "바지걸이", ck, run, OPTS)
    assert r == {"채움": 1, "삭제": 1, "수동": 1, "건너뜀": 2}
    assert calls == [[f"https://smartstore.naver.com/s/products/{n}" for n in (1, 2, 3)]]
    tab, cells = sh.updates[0]
    assert tab == S.BENCH_TAB
    assert cells == [(0, 8, 2), (0, 9, "흰:13,400 / 검:12,900"), (0, S.COL_REP, 12900), (0, S.COL_STATUS, "")]
    assert sh.deleted == [(S.BENCH_TAB, [1])]
    urls = [x[6] for x in sh.tabs[S.BENCH_TAB]]
    assert "https://smartstore.naver.com/s/products/2" not in urls and len(urls) == 5
    assert sh.tabs[S.BENCH_TAB][1][S.COL_STATUS] == "옵션수동"          # 실패 행은 그대로

    # 재실행: 채운 행은 대상에서 빠지고, 체크포인트에 있는 URL 은 run 을 다시 안 부른다
    calls.clear()
    r2 = C.do_refill(sh, "바지걸이", ck, run, OPTS)
    assert calls == [] and r2["채움"] == 0 and r2["삭제"] == 0


def test_refill_captcha_applies_then_exit4(tmp_path):
    sh = FakeSheet(bench_rows=[_cand(1), _cand(2)])

    def run(name, items, opts, t):
        return [opt_probe(items[0]["url"], 상태="단품"), opt_probe(items[1]["url"], 상태="캡챠감지")]

    with pytest.raises(SystemExit) as e:
        C.do_refill(sh, "바지걸이", tmp_path / "o.json", run, OPTS)
    assert e.value.code == 4
    assert sh.tabs[S.BENCH_TAB][0][8] == 1 and sh.tabs[S.BENCH_TAB][0][9] == "단품:12,900"
    assert sh.tabs[S.BENCH_TAB][1][8] == ""


def test_read_options_requeues_missing_and_stops_on_empty(tmp_path):
    seen = []

    def run(name, items, opts, t):
        seen.append([i["url"] for i in items])
        return [opt_probe(items[0]["url"], 상태="단품")] if len(seen) == 1 else []

    ck = {"details": {}}
    stop = C._read_options(["u1", "u2", "u3"], ck, run, OPTS, tmp_path / "x.json")
    assert stop is False
    assert list(ck["details"]) == ["u1"]
    assert seen[1][0] == "u2" and len(seen) == 2       # 빈 응답이면 무한 반복하지 않고 멈춘다
