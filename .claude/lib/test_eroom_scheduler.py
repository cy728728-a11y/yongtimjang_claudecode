# -*- coding: utf-8 -*-
"""eroom_scheduler 판정 테스트 (실행 없음)."""
from datetime import datetime
import eroom_scheduler as S

K = S.KST
D = {"name": "d", "kind": "daily", "at": "00:01", "cmd": []}
W = {"name": "w", "kind": "weekly", "weekday": 0, "at": "07:00", "cmd": []}
H = {"name": "h", "kind": "hourly", "cmd": []}


def test_daily():
    assert S.due_key(D, datetime(2026, 10, 17, 0, 0, tzinfo=K)) is None
    assert S.due_key(D, datetime(2026, 10, 17, 0, 1, tzinfo=K)) == "2026-10-17"
    assert S.due_key(D, datetime(2026, 10, 17, 9, 30, tzinfo=K)) == "2026-10-17"  # 잠에서 깨면 따라잡기


def test_weekly():
    assert S.due_key(W, datetime(2026, 10, 19, 6, 59, tzinfo=K)) is None
    assert S.due_key(W, datetime(2026, 10, 19, 7, 0, tzinfo=K)) == "2026-W43"
    assert S.due_key(W, datetime(2026, 10, 20, 7, 0, tzinfo=K)) is None


def test_tick_once_per_key(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "STATE", str(tmp_path / "s.json"))
    monkeypatch.setattr(S, "DATA", str(tmp_path))
    monkeypatch.setattr(S, "JOBS", [D, H])
    calls = []
    now = datetime(2026, 10, 17, 0, 5, tzinfo=K)
    S.tick(now, spawn=lambda j: calls.append(j["name"]) or 999999)
    S.tick(now, spawn=lambda j: calls.append(j["name"]) or 999999)
    assert calls == ["d", "h"]
