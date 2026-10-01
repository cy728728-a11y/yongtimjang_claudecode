# -*- coding: utf-8 -*-
import json

import pytest

import gws_sheet as G


class Fake:
    def __init__(self, replies):
        self.calls, self.replies = [], list(replies)

    def __call__(self, argv):
        self.calls.append(argv)
        return self.replies.pop(0)


def _params(argv):
    return json.loads(argv[argv.index("--params") + 1])


def test_read_skips_header():
    f = Fake([{"values": [["h1", "h2"], ["a", "b"], ["c"]]}])
    rows = G.Sheet("SID", runner=f).read("후보")
    assert rows == [["a", "b"], ["c"]]
    assert f.calls[0][:4] == ["sheets", "spreadsheets", "values", "get"]
    assert _params(f.calls[0]) == {"spreadsheetId": "SID", "range": "후보!A:X"}


def test_read_empty_tab():
    assert G.Sheet("SID", runner=Fake([{}])).read("후보") == []


def test_append_user_entered():
    f = Fake([{"updates": {"updatedRows": 2}}])
    n = G.Sheet("SID", runner=f).append("후보", [["a"], ["=1+1"]])
    assert n == 2
    p = _params(f.calls[0])
    assert p["valueInputOption"] == "USER_ENTERED" and p["range"] == "후보!A1"
    assert json.loads(f.calls[0][f.calls[0].index("--json") + 1]) == {"values": [["a"], ["=1+1"]]}


def test_append_nothing_makes_no_call():
    f = Fake([])
    assert G.Sheet("SID", runner=f).append("후보", []) == 0 and f.calls == []


def test_set_cell_a1():
    f = Fake([{"updatedCells": 1}])
    G.Sheet("SID", runner=f).set_cell("카테고리스캔", 0, 12, "Y")
    assert _params(f.calls[0])["range"] == "카테고리스캔!M2"


def test_error_reply_raises():
    with pytest.raises(G.GwsError):
        G.Sheet("SID", runner=Fake([{"error": {"code": 403, "message": "x"}}])).read("후보")
