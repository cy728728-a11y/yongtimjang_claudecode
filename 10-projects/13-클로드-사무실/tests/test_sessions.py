"""sessions.py 시험 — 최근 세션 찾기, 세션 이름, 상태 판정"""
import json
import time

import activity
import sessions
from conftest import assistant, tool_use, user


def title(kind, value):
    if kind == "custom":
        return {"type": "custom-title", "customTitle": value, "sessionId": "x"}
    return {"type": "ai-title", "aiTitle": value, "sessionId": "x"}


# ── config_dir / recent_sessions ────────────────────────────
def test_config_dir_env(claude_home):
    assert sessions.config_dir() == claude_home.root


def test_recent_sessions_filters(claude_home):
    now = time.time()
    fresh = claude_home.write("aaaa1111-fresh", [user("hi")], enc="a", ago=60)
    claude_home.write("bbbb2222-old", [user("hi")], enc="a", ago=7 * 3600)
    claude_home.sub(fresh, "x1", [user("sub")], ago=10)
    claude_home.write("bad name!", [user("hi")], enc="a", ago=10)
    got = sessions.recent_sessions(6, now)
    assert [s["sid"] for s in got] == ["aaaa1111-fresh"]
    assert got[0]["path"] == fresh
    assert abs(got[0]["mtime"] - (now - 60)) < 2


def test_recent_sessions_missing_root(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "nope"))
    sessions.forget()
    assert sessions.recent_sessions(6, time.time()) == []


# ── session_name ───────────────────────────────────────────
def test_name_custom_beats_ai(claude_home):
    p = claude_home.write("abcdef123456", [title("ai", "자동 제목"), title("custom", "to-do-list"), user("hi")])
    assert sessions.session_name(p, "abcdef123456") == "to-do-list"


def test_name_last_rename_wins(claude_home):
    p = claude_home.write("abcdef123456", [title("custom", "첫이름"), user("x"), title("custom", "둘째이름")])
    assert sessions.session_name(p, "abcdef123456") == "둘째이름"


def test_name_ai_only(claude_home):
    p = claude_home.write("abcdef123456", [title("ai", "옵션 정리"), user("x")])
    assert sessions.session_name(p, "abcdef123456") == "옵션 정리"


def test_name_fallback_sid8(claude_home):
    p = claude_home.write("abcdef123456", [user("x")])
    assert sessions.session_name(p, "abcdef123456") == "abcdef12"


def test_name_far_from_tail(claude_home):
    filler = [json.dumps({"type": "progress", "data": "y" * 1000}) for _ in range(200)]  # ~200KB
    p = claude_home.write("abcdef123456", [title("custom", "앞쪽 이름")] + filler)
    assert sessions.session_name(p, "abcdef123456") == "앞쪽 이름"


def test_name_updates_when_file_grows(claude_home):
    p = claude_home.write("abcdef123456", [title("ai", "처음"), user("x")])
    assert sessions.session_name(p, "abcdef123456") == "처음"
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(title("custom", "바뀜"), ensure_ascii=False, separators=(",", ":")) + "\n")
    assert sessions.session_name(p, "abcdef123456") == "바뀜"


# ── session_status ─────────────────────────────────────────
def _last(p):
    return activity.read_tail(p)["last"]


def test_status_recent_mtime_working(claude_home):
    p = claude_home.write("s", [assistant([{"type": "text", "text": "x"}], stop_reason="end_turn")], ago=30)
    now = time.time()
    assert sessions.session_status(_last(p), now - 30, now) == "working"


def test_status_quiet_but_unresolved_tool_working(claude_home):
    p = claude_home.write("s", [user("hi"), assistant([tool_use("t1", "Bash", {"command": "sleep 999"})])])
    now = time.time()
    assert sessions.session_status(_last(p), now - 600, now) == "working"


def test_status_quiet_end_turn_rest(claude_home):
    p = claude_home.write("s", [assistant([{"type": "text", "text": "x"}], stop_reason="end_turn")])
    now = time.time()
    assert sessions.session_status(_last(p), now - 600, now) == "rest"


def test_status_interrupted_beats_recent(claude_home):
    p = claude_home.write("s", [
        assistant([tool_use("t1", "Bash", {"command": "ls"})]),
        user([{"type": "text", "text": "[Request interrupted by user for tool use]"}]),
    ])
    now = time.time()
    assert sessions.session_status(_last(p), now - 10, now) == "rest"


def test_status_api_error_rest(claude_home):
    p = claude_home.write("s", [assistant([{"type": "text", "text": "API Error: 500"}])])
    now = time.time()
    assert sessions.session_status(_last(p), now - 10, now) == "rest"


def test_status_no_last(claude_home):
    now = time.time()
    assert sessions.session_status(None, now - 10, now) == "working"
    assert sessions.session_status(None, now - 600, now) == "rest"
