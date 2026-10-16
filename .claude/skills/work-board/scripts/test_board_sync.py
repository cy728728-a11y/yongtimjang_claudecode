# -*- coding: utf-8 -*-
"""board_sync 순수 함수 테스트 (네트워크 없음)."""
import board_sync as B

TODAY = "2026-10-17"
ER = ["3", "2026-10-16", "FALSE", "용팀장님 전달 — 업로드 397", "1-A", "이룸님", "", "메모1", "1"]


def test_is_mine():
    assert B.is_mine(ER)
    assert B.is_mine(["1", "d", "FALSE", "업로드", "1-A", "용팀장님"])
    assert not B.is_mine(["1", "d", "FALSE", "효자 29", "8", "다른 세션"])


def test_key_ignores_numbers():
    other = list(ER)
    other[3] = "용팀장님 전달 — 업로드 500"
    assert B.eroom_key(ER) == B.eroom_key(other)


def test_merge_adds_then_updates():
    rows, a, u = B.merge_eroom([], [ER], TODAY)
    assert (a, u) == (1, 0) and rows[0][6] == B.SRC_EROOM
    er2 = list(ER)
    er2[3], er2[7] = "용팀장님 전달 — 업로드 500", "메모2"
    rows2, a2, u2 = B.merge_eroom(rows, [er2], TODAY)
    assert (a2, u2) == (0, 1) and len(rows2) == 1
    assert rows2[0][3].endswith("500") and rows2[0][7] == "메모2"


def test_merge_never_unchecks_mine():
    rows, _, _ = B.merge_eroom([], [ER], TODAY)
    rows[0][2] = "TRUE"
    rows2, _, _ = B.merge_eroom(rows, [ER], TODAY)
    assert rows2[0][2] == "TRUE"


def test_rollover():
    mine = [
        ["1", "2026-10-16", "TRUE", "끝난 일", "", "", "내 판", "", ""],
        ["2", "2026-10-16", "FALSE", "남은 일", "", "", "내 판", "", "1"],
        ["3", "2026-10-16", "FALSE", "⑥ 잠금", "⑥", "Claude", "자동", "", ""],
        ["4", "2026-10-16", "FALSE", "[dry-run] x", "", "", "자동", "", ""],
        ["5", TODAY, "FALSE", "오늘 일", "", "", "내 판", "", ""],
    ]
    keep, arch = B.rollover(mine, TODAY)
    assert [r[3] for r in arch] == ["끝난 일", "⑥ 잠금", "[dry-run] x"]
    assert [r[3] for r in keep] == ["남은 일", "오늘 일"]
    assert keep[0][1] == TODAY and keep[0][8] == "2"


def test_renumber_drops_blank():
    out = B.renumber([["", "", "FALSE", ""], ["9", "d", "", "a"], ["9", "d", "true", "b"]])
    assert [r[0] for r in out] == ["1", "2"] and out[1][2] == "TRUE"
