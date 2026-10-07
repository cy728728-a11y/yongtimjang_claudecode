# -*- coding: utf-8 -*-
import json

import pytest

import rules
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
        assert opts.get("maxCombos") == rules.MAX_COMBOS == 15
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
    many = [[f"o{i}"] for i in range(16)]
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
    assert row[8] == 1 and row[S.COL_REP] == 12900 and row[S.COL_STATUS] == ""


def test_bench_catalog_not_opened(tmp_path):
    calls = []
    run = _bench_run([prod(1, 900, url=CAT_URL), prod(2, 900)],
                     lambda u: opt_probe(u, combos=[["화이트", "10개 (+1,000원)"]]), calls)
    sh = FakeSheet()
    assert C.do_bench(sh, "kw", tmp_path / "b.json", run, "2026-10-02", OPTS) == 1   # 가격비교는 후보에서 패스
    assert all(CAT_URL not in c for c in calls)
    (ok_row,) = sh.tabs[S.BENCH_TAB]
    assert ok_row[8] == 1 and ok_row[S.COL_REP] == 13900


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
    """후보 탭 행(25열)."""
    r = ["a", "b", "c", "d", kw, "s", url or f"https://smartstore.naver.com/s/products/{n}", f"p{n}",
         opt_cnt, "", "", "", "", "", "", "", "", "", "", "", "", price, "2026-10-01", 900, "" if opt_cnt else "옵션수동"]
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
    assert cells == [(0, 8, 2), (0, S.COL_REP, 12900), (0, S.COL_STATUS, "")]
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
    assert sh.tabs[S.BENCH_TAB][0][8] == 1
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


# ---- 스토어 확장 · 원산지 (quick-261008-0qx) ----

MAIN = "https://smartstore.naver.com/main/products/"
SA, SBB = "https://smartstore.naver.com/storeA", "https://smartstore.naver.com/storeB"


def mprod(pid, review=900, mall="A몰"):
    """검색 결과 모양 — 슬러그 없는 main/products/<id>."""
    p = prod(pid, review, url=f"{MAIN}{pid}")
    p["마켓명"] = mall
    return p


def sitem(pid, review=800, price=15000, **kw):
    d = {"id": pid, "productNo": pid + 1000, "name": f"s{pid}", "price": price, "salePrice": price,
         "review": review, "category": "가>나>다>라", "display": "ON", "origin": ""}
    d.update(kw)
    return d


class World:
    """search / options / store 를 이름으로 나눠 흉내 내는 fake run. 호출 기록을 남긴다."""

    def __init__(self, products, href=None, stores=None, origin=None, combos=None, opt_state=None,
                 store_state=None):
        self.products = products
        self.href = href or {}              # 상품번호 → 스토어 base
        self.stores = stores or {}          # base → items
        self.origin = origin or {}          # 상품번호 → 원산지 원문
        self.combos = combos or {}          # 상품번호 → combos
        self.opt_state = opt_state or {}    # 상품번호 → 상태
        self.store_state = store_state or {}  # base → 상태
        self.calls = {"search": [], "options": [], "store": []}

    @staticmethod
    def pid(url):
        return int(url.rstrip("/").rsplit("/", 1)[1])

    def __call__(self, name, items, opts, t):
        self.calls[name].append(list(items))
        if name == "search":
            return [{"kind": "page", "key": "kw", "상태": "성공", "products": self.products}]
        out = []
        if name == "options":
            for i in items:
                n = self.pid(i["url"])
                d = opt_probe(i["url"], 상태=self.opt_state.get(n, "성공"), combos=self.combos.get(n, [["x"]]))
                base = self.href.get(n)
                d["href"] = f"{base}/products/{n}" if base else i["url"]
                d["origin"] = self.origin.get(n, "중국")
                out.append(d)
                if d["상태"] in C.STOP:
                    break
            return out
        assert name == "store"
        for i in items:
            base = i["base"] or self.href.get(self.pid(i["url"]), "")
            st = self.store_state.get(base, "성공")
            out.append({"kind": "store", "key": i["url"], "base": base, "상태": st,
                        "items": self.stores.get(base, []) if st == "성공" else []})
            if st in C.STOP:
                break
        return out


def _bench(sh, w, tmp_path, **kw):
    return C.do_bench(sh, "kw", tmp_path / "b.json", w, "2026-10-08", OPTS, **kw)


def test_bench_expand_order_and_status(tmp_path):
    w = World([mprod(1, mall="A몰"), mprod(2, mall="B몰")], href={1: SA, 2: SBB},
              stores={SA: [sitem(1, review=5000), sitem(11, review=3000), sitem(12, review=700)],
                      SBB: [sitem(21, review=900)]})
    sh = FakeSheet()
    assert _bench(sh, w, tmp_path, expand=True) == 5
    urls = [r[6] for r in sh.tabs[S.BENCH_TAB]]
    assert urls == [f"{MAIN}1", f"{SA}/products/11", f"{SA}/products/12", f"{MAIN}2", f"{SBB}/products/21"]
    ext = sh.tabs[S.BENCH_TAB][1]
    assert ext[4] == "kw" and ext[5] == "A몰" and ext[S.COL_STATUS] == "스토어확장"
    assert sh.tabs[S.BENCH_TAB][0][S.COL_STATUS] == ""


def test_bench_expand_same_store_once(tmp_path):
    w = World([mprod(1), mprod(2)], href={1: SA, 2: SA}, stores={SA: [sitem(11)]})
    sh = FakeSheet()
    _bench(sh, w, tmp_path, expand=True)
    assert sum(len(c) for c in w.calls["store"]) == 1
    assert [r[6] for r in sh.tabs[S.BENCH_TAB]] == [f"{MAIN}1", f"{SA}/products/11", f"{MAIN}2"]


def test_bench_expand_dedupe_by_product_id(tmp_path):
    existing = [["a", "b", "c", "d", "kw", "A몰", f"{MAIN}11"]]
    w = World([mprod(1)], href={1: SA}, stores={SA: [sitem(1), sitem(11), sitem(12)]})
    sh = FakeSheet(bench_rows=existing)
    _bench(sh, w, tmp_path, expand=True)
    assert [r[6] for r in sh.tabs[S.BENCH_TAB][1:]] == [f"{MAIN}1", f"{SA}/products/12"]


def test_bench_expand_over_limit_and_manual(tmp_path):
    many = [[f"o{i}"] for i in range(16)]
    w = World([mprod(1)], href={1: SA}, stores={SA: [sitem(11), sitem(12)]},
              combos={11: many}, opt_state={12: "읽기실패"})
    sh = FakeSheet()
    _bench(sh, w, tmp_path, expand=True)
    rows = sh.tabs[S.BENCH_TAB]
    assert [r[6] for r in rows] == [f"{MAIN}1", f"{SA}/products/12"]
    assert rows[1][S.COL_STATUS] == "스토어확장·옵션수동"


def test_bench_expand_unsupported_keeps_original(tmp_path):
    w = World([mprod(1)], href={1: SA}, store_state={SA: "미지원"})
    sh = FakeSheet()
    assert _bench(sh, w, tmp_path, expand=True) == 1


def test_bench_expand_driver_error_keeps_original(tmp_path):
    w = World([mprod(1)], href={1: SA})

    def run(name, items, opts, t):
        if name == "store":
            raise RuntimeError("aside 없음")
        return w(name, items, opts, t)

    sh = FakeSheet()
    assert C.do_bench(sh, "kw", tmp_path / "b.json", run, "d", OPTS, expand=True) == 1


def test_bench_expand_captcha_exit4_then_resume(tmp_path):
    w = World([mprod(1), mprod(2)], href={1: SA, 2: SBB}, stores={SA: [sitem(11)], SBB: [sitem(21)]},
              store_state={SBB: "캡챠감지"})
    sh = FakeSheet()
    ck = tmp_path / "b.json"
    with pytest.raises(SystemExit) as e:
        C.do_bench(sh, "kw", ck, w, "d", OPTS, expand=True)
    assert e.value.code == 4 and sh.tabs[S.BENCH_TAB] == []
    assert list(json.loads(ck.read_text(encoding="utf-8"))["stores"]) == [f"{MAIN}1"]
    w.store_state = {}
    w.calls["store"].clear()
    assert C.do_bench(sh, "kw", ck, w, "d", OPTS, expand=True) == 4
    assert [[i["url"] for i in c] for c in w.calls["store"]] == [[f"{MAIN}2"]]


def test_bench_expand_off_by_default(tmp_path):
    w = World([mprod(1)], href={1: SA}, stores={SA: [sitem(11)]})
    sh = FakeSheet()
    assert _bench(sh, w, tmp_path) == 1
    assert w.calls["store"] == []


def test_bench_origin_filter(tmp_path):
    w = World([mprod(1), mprod(2), mprod(3), mprod(4)], href={1: SA, 2: SA, 3: SBB, 4: SBB},
              origin={1: "대한민국", 2: "중국", 3: "", 4: ""}, opt_state={4: "읽기실패"},
              stores={SA: [sitem(11), sitem(12), sitem(13)]}, )
    w.origin.update({11: "베트남", 12: "", 13: "중국산"})
    sh = FakeSheet()
    _bench(sh, w, tmp_path, check_origin=True, expand=True)
    got = [(r[6], r[S.COL_STATUS]) for r in sh.tabs[S.BENCH_TAB]]
    assert got == [(f"{MAIN}2", ""),
                   (f"{SA}/products/12", "스토어확장·원산지미확인"), (f"{SA}/products/13", "스토어확장"),
                   (f"{MAIN}3", "원산지미확인"), (f"{MAIN}4", "옵션수동·원산지미확인")]
    # 원산지 제외된 1번의 스토어(A)는 2번 덕분에 확장됐지만, 1번 기준으로 따로 요청되지는 않는다
    assert [i["url"] for c in w.calls["store"] for i in c] == [f"{MAIN}2", f"{MAIN}3"]


def test_bench_store_list_origin_prefilter(tmp_path):
    w = World([mprod(1)], href={1: SA}, stores={SA: [sitem(11, origin="국산"), sitem(12, origin="중국")]})
    sh = FakeSheet()
    _bench(sh, w, tmp_path, check_origin=True, expand=True)
    opened = [i["url"] for c in w.calls["options"] for i in c]
    assert f"{SA}/products/11" not in opened and f"{SA}/products/12" in opened


def test_bench_no_options_origin_unknown(tmp_path):
    w = World([mprod(1)])
    sh = FakeSheet()
    _bench(sh, w, tmp_path, check_origin=True, with_options=False)
    assert sh.tabs[S.BENCH_TAB][0][S.COL_STATUS] == "옵션수동·원산지미확인"


def test_bench_from_scan_shares_expanded(tmp_path):
    rows = [["d", "A", "B", "C1", "", "10", 3, "x", "k1", "", "", "", ""],
            ["d", "A", "B", "C2", "", "11", 3, "x", "k2", "", "", "", ""]]
    sh = FakeSheet(scan_rows=rows)
    state = {"kw": None}
    w = World([], href={1: SA, 2: SA}, stores={SA: [sitem(11)]})

    def run(name, items, opts, t):
        if name == "search":
            kw = items[0]["키워드"]
            return [{"kind": "page", "key": kw, "상태": "성공", "products": [mprod(1 if kw == "k1" else 2)]}]
        return w(name, items, opts, t)

    assert C.bench_from_scan(sh, tmp_path, run, "d", OPTS, expand=True) == 3
    assert sum(len(c) for c in w.calls["store"]) == 1


def _row(pid, kw="kw", mall="A몰", status="", url=None):
    r = _cand(pid, kw=kw, opt_cnt=1, url=url or f"{MAIN}{pid}")
    r[5] = mall
    r[S.COL_STATUS] = status
    return r


def test_expand_backfill(tmp_path):
    rows = [_row(1, mall="A몰"), _row(2, mall="A몰"), _row(3, mall="B몰"), _row(4, mall="C몰", kw="other"),
            _row(5, url=CAT_URL, mall="D몰"), _row(6, mall="E몰"), _row(7, mall="E몰", status="스토어확장"),
            _row(8, mall="F몰", url="https://www.coupang.com/vp/products/8")]
    sh = FakeSheet(bench_rows=rows)
    w = World([], href={1: SA, 3: SBB}, stores={SA: [sitem(2), sitem(11)], SBB: [sitem(31)]})
    r = C.do_expand(sh, "kw", tmp_path / "e.json", w, "d", OPTS)
    assert [i["url"] for c in w.calls["store"] for i in c] == [f"{MAIN}1", f"{MAIN}3"]
    assert [x[6] for x in sh.tabs[S.BENCH_TAB][8:]] == [f"{SA}/products/11", f"{SBB}/products/31"]
    assert all(x[S.COL_STATUS] == "스토어확장" for x in sh.tabs[S.BENCH_TAB][8:])
    assert r["추가"] == 2 and r["스토어"] == 2


def test_expand_all_and_dry_run(tmp_path):
    rows = [_row(1, mall="A몰"), _row(4, mall="C몰", kw="other")]
    sh = FakeSheet(bench_rows=rows)
    w = World([], href={1: SA, 4: SBB}, stores={SA: [sitem(11)], SBB: [sitem(41)]})
    appended = []
    sh.append = lambda tab, rs: appended.append(rs) or len(rs)
    r = C.do_expand(sh, None, tmp_path / "e.json", w, "d", OPTS, dry_run=True)
    assert appended == [] and r["추가"] == 2


def test_expand_origin_excluded(tmp_path):
    sh = FakeSheet(bench_rows=[_row(1)])
    w = World([], href={1: SA}, stores={SA: [sitem(11), sitem(12)]}, origin={11: "국산"})
    r = C.do_expand(sh, "kw", tmp_path / "e.json", w, "d", OPTS)
    assert r["추가"] == 1 and sh.tabs[S.BENCH_TAB][-1][6] == f"{SA}/products/12"


def test_expand_captcha_exit4(tmp_path):
    sh = FakeSheet(bench_rows=[_row(1)])
    w = World([], href={1: SA}, store_state={SA: "캡챠감지"})
    with pytest.raises(SystemExit) as e:
        C.do_expand(sh, "kw", tmp_path / "e.json", w, "d", OPTS)
    assert e.value.code == 4 and len(sh.tabs[S.BENCH_TAB]) == 1


def test_origin_check_dry_run_no_sheet_calls(tmp_path, capsys):
    rows = [_row(1), _row(2), _row(3), _row(4, url=CAT_URL), _row(5, kw="other")]
    sh = FakeSheet(bench_rows=rows)
    w = World([], origin={1: "중국", 2: "대한민국", 3: ""})
    r = C.do_origin_check(sh, "kw", tmp_path / "o.json", w, OPTS, dry_run=True)
    assert r["중국"] == 1
    assert [x["행"] for x in r["제외"]] == [3] and r["제외"][0]["원산지"] == "대한민국"
    assert [x["행"] for x in r["미확인"]] == [4]
    assert sh.updates == [] and sh.deleted == []
    out = capsys.readouterr().out
    assert "중국 1 · 제외 1 · 미확인 1" in out and "3 | A몰 | p2 | 대한민국" in out


def test_origin_check_apply(tmp_path):
    rows = [_row(1), _row(2), _row(3, status="옵션수동"), _row(6, kw="other")]
    sh = FakeSheet(bench_rows=rows)
    w = World([], origin={1: "중국", 2: "베트남", 3: "", 6: "국산"})
    r = C.do_origin_check(sh, None, tmp_path / "o.json", w, OPTS, dry_run=False)
    assert len(r["제외"]) == 2
    urls = [x[6] for x in sh.tabs[S.BENCH_TAB]]
    assert urls == [f"{MAIN}1", f"{MAIN}3"]
    assert sh.tabs[S.BENCH_TAB][0][S.COL_STATUS] == ""
    assert sh.tabs[S.BENCH_TAB][1][S.COL_STATUS] == "옵션수동·원산지미확인"


def test_cli_expand_origin_parse():
    p = C.build_parser()
    assert p.parse_args(["bench", "--keyword", "x"]).no_expand is False
    assert p.parse_args(["bench", "--keyword", "x", "--no-expand"]).no_expand is True
    a = p.parse_args(["expand", "--keyword", "바지걸이"])
    assert a.cmd == "expand" and a.keyword == "바지걸이" and not a.all and not a.dry_run
    a = p.parse_args(["expand", "--all", "--dry-run", "--no-options"])
    assert a.all and a.dry_run and a.no_options
    a = p.parse_args(["origin", "--all", "--dry-run"])
    assert a.cmd == "origin" and a.all and a.dry_run
    with pytest.raises(SystemExit):
        p.parse_args(["expand"])
    with pytest.raises(SystemExit):
        p.parse_args(["origin", "--keyword", "x", "--all"])
