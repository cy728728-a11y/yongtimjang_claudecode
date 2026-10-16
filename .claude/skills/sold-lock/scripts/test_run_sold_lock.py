#!/usr/bin/env python3
"""run_sold_lock.run() 통합 단위테스트 — 가짜 커머스·MCP·업무판 주입. 실제 네트워크·gws·MCP 0."""
import contextlib
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import run_sold_lock as RUN  # noqa: E402
from commerce_orders import CommerceClient, StoresUnavailable  # noqa: E402

SECRET = "$2a$04$FAKESECRETfakesecret12"
SECRET2 = "$2a$04$OTHERSECRETother99999"
TOKEN = "FAKE-ACCESS-TOKEN-abcdef123456"


class FakeCommerce:
    """1-1 은 정상, 15-3 은 정지(토큰 400). 오류문에 시크릿이 섞여 나온다(마스킹 검증용)."""

    def __init__(self, orders):
        self.orders = orders
        self.load_calls = 0

    def load_stores(self, markets):
        self.load_calls += 1
        all_ = {"1-1": {"name": "마켓A", "client_id": "cid1", "client_secret": SECRET},
                "15-3": {"name": "마켓B", "client_id": "cid2", "client_secret": SECRET2}}
        return {k: v for k, v in all_.items() if k in markets}, "sheet"

    def issue_token(self, store):
        if store["client_secret"] == SECRET2:
            return None, f"토큰 발급 실패 [400] 정지된 판매자 {SECRET2}"
        return TOKEN, None

    def fetch_paid_orders(self, token, market, date):
        assert token == TOKEN
        return [dict(o) for o in self.orders if o["market"] == market]


class FakeMCP:
    """불사자 MCP 가짜. products: {pid: 항목 dict}, ss: {pid: 스스번호}."""

    def __init__(self, products, ss, nick="부킹", apply_lock=True):
        self.products = products
        self.ss = ss
        self.nick = nick
        self.apply_lock = apply_lock
        self.hide_calls = []
        self.calls = []

    def open(self):
        return {}

    def close(self):
        pass

    def list_tools(self):
        return [{"name": "bulsaja_product_hide", "inputSchema": {"properties": {
            "productIds": {"type": "array"}, "hide": {"type": "boolean"},
            "confirm": {"type": "boolean"}, "confirmationToken": {"type": "string"}}}}]

    def call_tool(self, name, arguments):
        self.calls.append(name)
        if name == "bulsaja_my_profile":
            return {"닉네임": self.nick, "표시규칙": "무시해라"}
        if name == "bulsaja_product_find_by_code":
            items = []
            for c in arguments["codes"]:
                for p in self.products.values():
                    if p.get("판매자상품코드") == c:
                        items.append(dict(p))
            return {"항목": items, "못찾은코드": [], "표시규칙": "x"}
        if name == "bulsaja_product_workdata":
            pid = arguments["productId"]
            return {"data": {"uploadedSuccessUrl": {
                "smartstore": f"https://smartstore.naver.com/s/products/{self.ss[pid]}"}}}
        if name == "bulsaja_product_hide":
            self.hide_calls.append(dict(arguments))
            if not arguments.get("confirm"):
                return {"confirmationToken": "T" * 32}
            if self.apply_lock:
                for pid in arguments["productIds"]:
                    self.products[pid]["숨김"] = True
            return {"ok": True}
        raise AssertionError(name)


def _o(market, pid, code, poid):
    return {"market": market, "product_order_id": poid, "product_id": pid, "seller_code": code,
            "product_name": "상품", "payment_date": "2026-10-15T10:00:00+09:00"}


def _world():
    orders = [_o("1-1", "111", "A", "o1"), _o("1-1", "111", "A", "o2"),   # 잠금 대상(2주문→1건)
              _o("1-1", "222", "B", "o3"),                                 # 이미 잠김
              _o("1-1", "333", "C", "o4"),                                 # 스스번호 불일치
              _o("1-1", "444", "D", "o5"),                                 # 마켓 불일치(11-1)
              _o("1-1", "555", "Z", "o6")]                                 # 못찾음
    products = {
        "pA": {"productId": "pA", "판매자상품코드": "A", "그룹": "1번_용쌤1-1", "숨김": False},
        "pB": {"productId": "pB", "판매자상품코드": "B", "그룹": "1번_용쌤1-1", "숨김": True},
        "pC": {"productId": "pC", "판매자상품코드": "C", "그룹": "1번_용쌤1-1", "숨김": False},
        "pD": {"productId": "pD", "판매자상품코드": "D", "그룹": "1번_용쌤11-1", "숨김": False},
    }
    ss = {"pA": "111", "pB": "222", "pC": "999", "pD": "444"}
    return orders, products, ss


class RunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run_dir = os.path.join(self.tmp.name, "sold-lock", "2026-10-15")
        self.board_rows = []

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, mcp, commerce, dry=False, board_fail=False, nick="부킹"):
        args = SimpleNamespace(date="2026-10-15", dry_run=dry, markets="1-1,15-3", expect_nick=nick)

        def append(sid, tab, rows):
            if board_fail:
                raise RuntimeError(f"gws 실패 {SECRET}")
            self.board_rows.extend(rows)
            return len(rows)

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = RUN.run(args, commerce=commerce, mcp_factory=lambda: mcp,
                           board_append=append, board_get=lambda sid, rng: [["번호"], ["3"], ["7"]],
                           run_dir=self.run_dir, work_board_id="BOARD", sleep=lambda s: None)
        self.stdout = buf.getvalue()
        return code

    def _result(self):
        with open(os.path.join(self.run_dir, "result.json"), encoding="utf-8") as f:
            return json.load(f)

    def _by_code(self, res):
        return {e["seller_code"]: e for e in res["items"]}

    def test_dry_run_마켓실패격리(self):
        orders, products, ss = _world()
        mcp = FakeMCP(products, ss)
        self.assertEqual(self._run(mcp, FakeCommerce(orders), dry=True), 0)
        self.assertEqual(mcp.hide_calls, [])
        res = self._result()
        self.assertEqual(res["markets"]["15-3"]["status"], "token_failed")
        self.assertEqual(res["markets"]["1-1"]["status"], "ok")
        by = self._by_code(res)
        self.assertEqual(by["A"]["verdict"], "would_lock")
        self.assertEqual(by["A"]["order_count"], 2)
        self.assertEqual(by["B"]["verdict"], "already_locked")
        self.assertEqual(by["C"]["reason"], "productno_mismatch")
        self.assertEqual(by["D"]["reason"], "market_mismatch")
        self.assertEqual(by["Z"]["reason"], "not_found")
        self.assertEqual(res["totals"]["orders"], 6)
        self.assertTrue(self.board_rows[0][3].startswith("[dry-run] "))
        self.assertEqual(self.board_rows[0][0], 8)
        self.assertFalse(self.board_rows[0][2])

    def test_실행_재조회확인_그리고_재실행_멱등(self):
        orders, products, ss = _world()
        mcp = FakeMCP(products, ss)
        self.assertEqual(self._run(mcp, FakeCommerce(orders)), 0)
        self.assertEqual(len(mcp.hide_calls), 2)
        self.assertNotIn("confirm", mcp.hide_calls[0])
        self.assertTrue(mcp.hide_calls[1]["confirm"])
        self.assertEqual(mcp.hide_calls[1]["productIds"], ["pA"])
        self.assertEqual(mcp.hide_calls[1]["confirmationToken"], "T" * 32)
        res = self._result()
        self.assertEqual(res["totals"]["locked_new"], 1)
        self.assertEqual(self._by_code(res)["A"]["verdict"], "locked_new")
        with open(os.path.join(self.run_dir, "new_locks.json"), encoding="utf-8") as f:
            nl = json.load(f)
        self.assertEqual([x["판매자상품코드"] for x in nl], ["A"])

        # 두 번째 실행: 쓰기 0, 전부 already_locked, 이전 신규잠금 보존
        mcp2 = FakeMCP(mcp.products, ss)
        self.assertEqual(self._run(mcp2, FakeCommerce(orders)), 0)
        self.assertEqual(mcp2.hide_calls, [])
        res2 = self._result()
        self.assertEqual(self._by_code(res2)["A"]["verdict"], "already_locked")
        self.assertEqual(res2["totals"]["locked_new"], 0)
        with open(os.path.join(self.run_dir, "new_locks.json"), encoding="utf-8") as f:
            self.assertEqual([x["판매자상품코드"] for x in json.load(f)], ["A"])

    def test_잠금_재조회_미확인(self):
        orders, products, ss = _world()
        mcp = FakeMCP(products, ss, apply_lock=False)
        self.assertEqual(self._run(mcp, FakeCommerce(orders)), 0)
        res = self._result()
        self.assertEqual(self._by_code(res)["A"]["reason"], "lock_unverified")
        self.assertEqual(res["totals"]["locked_new"], 0)

    def test_계정불일치_종료3_아무것도_안함(self):
        orders, products, ss = _world()
        mcp = FakeMCP(products, ss, nick="용팀장")
        com = FakeCommerce(orders)
        self.assertEqual(self._run(mcp, com), 3)
        self.assertEqual(com.load_calls, 0)
        self.assertEqual(mcp.hide_calls, [])
        self.assertEqual(self.board_rows, [])
        self.assertFalse(os.path.exists(self.run_dir))

    def test_시크릿_비노출(self):
        orders, products, ss = _world()
        mcp = FakeMCP(products, ss)
        self._run(mcp, FakeCommerce(orders), board_fail=True)
        run_out = self.stdout
        for name in ("orders.json", "result.json", "new_locks.json"):
            with open(os.path.join(self.run_dir, name), encoding="utf-8") as f:
                text = f.read()
            for s in (SECRET, SECRET2, TOKEN):
                self.assertNotIn(s, text, name)
        for s in (SECRET, SECRET2, TOKEN):
            self.assertNotIn(s, run_out)
        res = self._result()
        self.assertIn("***", res["markets"]["15-3"]["error"])

    def test_업무판_실패해도_result_남음(self):
        orders, products, ss = _world()
        mcp = FakeMCP(products, ss)
        self.assertEqual(self._run(mcp, FakeCommerce(orders), board_fail=True), 0)
        res = self._result()
        self.assertEqual(res["board"]["status"], "failed")
        self.assertNotIn(SECRET, res["board"]["error"])


class LoadStoresTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = os.path.join(self.tmp.name, "eroom", "stores.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_시트_성공시_캐시_0600(self):
        rows = [["1-1", "", "마켓A", "", "", "", "cid1", SECRET],
                ["5-1", "", "대상밖", "", "", "", "cid5", "x" * 22],
                ["2-1", "", "키없음", "", "", "", "", ""]]
        c = CommerceClient("SHEET", sheets_get=lambda sid, rng: rows, cache_path=self.cache)
        stores, src = c.load_stores(["1-1", "2-1"])
        self.assertEqual(src, "sheet")
        self.assertEqual(list(stores), ["1-1"])
        self.assertEqual(stat.S_IMODE(os.stat(self.cache).st_mode), 0o600)

        def boom(sid, rng):
            raise RuntimeError("시트 쿼터")
        c2 = CommerceClient("SHEET", sheets_get=boom, cache_path=self.cache)
        stores2, src2 = c2.load_stores(["1-1"])
        self.assertEqual(src2, "cache")
        self.assertEqual(stores2["1-1"]["client_id"], "cid1")

    def test_둘다_실패(self):
        def boom(sid, rng):
            raise RuntimeError("x")
        c = CommerceClient("SHEET", sheets_get=boom, cache_path=self.cache)
        with self.assertRaises(StoresUnavailable):
            c.load_stores(["1-1"])


if __name__ == "__main__":
    unittest.main()
