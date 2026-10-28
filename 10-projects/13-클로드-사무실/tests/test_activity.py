"""activity.py 시험 — Act 변환, 꼬리 읽기, 미해결 도구, 서브에이전트"""
import json
import time

import activity
from conftest import assistant, tool_result, tool_use, user


# ── describe(): CONTRACT Act 표 ─────────────────────────────
def test_describe_read_basename():
    assert activity.describe(tool_use("t", "Read", {"file_path": "/x/y/server.mjs"})) == {"k": "read", "a": "server.mjs"}


def test_describe_edit_write():
    assert activity.describe(tool_use("t", "Edit", {"file_path": "C:\\a\\b.txt"})) == {"k": "edit", "a": "b.txt"}
    assert activity.describe(tool_use("t", "MultiEdit", {"file_path": "/a/c.py"}))["k"] == "edit"
    assert activity.describe(tool_use("t", "NotebookEdit", {"notebook_path": "/a/n.ipynb"})) == {"k": "edit", "a": "n.ipynb"}
    assert activity.describe(tool_use("t", "Write", {"file_path": "/a/w.md"})) == {"k": "write", "a": "w.md"}


def test_describe_bash_description_first():
    d = "가" * 60
    act = activity.describe(tool_use("t", "Bash", {"command": "echo secret", "description": d}))
    assert act["k"] == "bash" and len(act["a"]) == 44 and act["a"].endswith("…")
    act2 = activity.describe(tool_use("t", "Bash", {"command": "x" * 100}))
    assert act2 == {"k": "bash", "a": "x" * 39 + "…"}


def test_describe_misc_tools():
    assert activity.describe(tool_use("t", "Grep", {"pattern": "abc"})) == {"k": "grep", "a": "abc"}
    assert activity.describe(tool_use("t", "Glob", {"pattern": "**/*.py"})) == {"k": "glob", "a": "**/*.py"}
    assert activity.describe(tool_use("t", "WebFetch", {"url": "https://example.com/a?b"})) == {"k": "fetch", "a": "example.com"}
    assert activity.describe(tool_use("t", "WebFetch", {"url": "not a url"})) == {"k": "fetch", "a": ""}
    assert activity.describe(tool_use("t", "WebSearch", {"query": "q"})) == {"k": "search", "a": "q"}
    assert activity.describe(tool_use("t", "Agent", {"description": "find it"})) == {"k": "agent", "a": "find it"}
    assert activity.describe(tool_use("t", "Task", {"description": "x"}))["k"] == "agent"
    assert activity.describe(tool_use("t", "TodoWrite", {})) == {"k": "todo", "a": ""}
    assert activity.describe(tool_use("t", "Skill", {"skill": "daily-note"})) == {"k": "skill", "a": "daily-note"}
    assert activity.describe(tool_use("t", "mcp__srv__do_thing", {})) == {"k": "mcp", "a": "do_thing"}
    assert activity.describe(tool_use("t", "Whatever", {})) == {"k": "tool", "a": "Whatever"}


def test_describe_text_strips_markdown_and_cuts():
    act = activity.describe({"type": "text", "text": "## 제목\n**굵게** `코드` 끝"})
    assert act["k"] == "text"
    assert "#" not in act["a"] and "*" not in act["a"] and "`" not in act["a"]
    long = activity.describe({"type": "text", "text": "a " * 100})
    assert len(long["a"]) == 60


def test_describe_skips_thinking_empty_unknown():
    assert activity.describe({"type": "thinking", "thinking": "hmm"}) is None
    assert activity.describe({"type": "text", "text": "   "}) is None
    assert activity.describe(None) is None
    assert activity.describe("x") is None
    assert activity.describe({"type": "tool_use", "name": ""}) is None


# ── read_tail(): 미해결 도구 ─────────────────────────────────
def test_unresolved_tool_true_when_no_result(claude_home):
    p = claude_home.write("s1", [
        user("hi"),
        assistant([tool_use("tu1", "Read")], stop_reason="tool_use"),
    ])
    info = activity.read_tail(p)
    assert info["last"]["unresolved_tool"] is True
    assert info["doing"] == {"k": "read", "a": "server.py"}
    assert info["cwd"] == "/Users/me/ws"


def test_unresolved_tool_false_after_result(claude_home):
    p = claude_home.write("s1", [
        user("hi"),
        assistant([tool_use("tu1", "Read")], stop_reason="tool_use"),
        user([tool_result("tu1")]),
    ])
    info = activity.read_tail(p)
    assert info["last"]["unresolved_tool"] is False
    assert info["last"]["type"] == "user"


def test_end_turn_and_log_order(claude_home):
    p = claude_home.write("s1", [
        user("hi"),
        assistant([tool_use("a", "Grep", {"pattern": "p1"})], ts="2026-10-28T01:00:00Z"),
        user([tool_result("a")]),
        assistant([{"type": "text", "text": "끝났어"}], stop_reason="end_turn", ts="2026-10-28T01:00:05Z"),
    ])
    info = activity.read_tail(p)
    assert info["last"]["end_turn"] is True
    assert info["last"]["unresolved_tool"] is False
    assert [x["k"] for x in info["log"]] == ["grep", "text"]
    assert info["log"][0]["at"] == "2026-10-28T01:00:00Z"


def test_log_keeps_last_8(claude_home):
    lines = []
    for i in range(12):
        lines.append(assistant([tool_use(f"t{i}", "Grep", {"pattern": f"p{i}"})]))
        lines.append(user([tool_result(f"t{i}")]))
    p = claude_home.write("s1", lines)
    info = activity.read_tail(p)
    assert len(info["log"]) == activity.LOG_N
    assert info["log"][-1]["a"] == "p11"


def test_meta_user_line_does_not_change_last(claude_home):
    p = claude_home.write("s1", [
        assistant([{"type": "text", "text": "done"}], stop_reason="end_turn"),
        user("<local-command-stdout>x</local-command-stdout>"),
        user("meta", isMeta=True),
    ])
    info = activity.read_tail(p)
    assert info["last"]["type"] == "assistant" and info["last"]["end_turn"] is True


def test_interrupted_flag(claude_home):
    p = claude_home.write("s1", [
        assistant([tool_use("x", "Bash", {"command": "ls"})]),
        user([{"type": "text", "text": "[Request interrupted by user]"}]),
    ])
    assert activity.read_tail(p)["last"]["interrupted"] is True


def test_widens_window_past_big_blob(claude_home):
    blob = json.dumps({"type": "api-request-blob", "data": "z" * 200_000})
    p = claude_home.write("s1", [
        user("hi"),
        assistant([tool_use("tu1", "Read", {"file_path": "/q/found.py"})]),
        blob,
    ])
    info = activity.read_tail(p)
    assert info["doing"] == {"k": "read", "a": "found.py"}
    assert info["last"] is not None


def test_broken_lines_are_skipped(claude_home):
    p = claude_home.write("s1", [
        '{"type":"assistant", broken',
        assistant([tool_use("a", "Glob", {"pattern": "*.md"})]),
    ])
    assert activity.read_tail(p)["doing"] == {"k": "glob", "a": "*.md"}


def test_missing_file_is_empty():
    info = activity.read_tail("/nonexistent/zzz.jsonl")
    assert info == {"doing": None, "log": [], "last": None, "cwd": ""}


# ── running_subagents() ────────────────────────────────────
def test_running_subagents(claude_home):
    p = claude_home.write("s1", [user("hi")])
    claude_home.sub(p, "run1", [assistant([tool_use("a", "Read", {"file_path": "/x/r.py"})])],
                    meta={"agentType": "Explore", "description": "find auth"}, ago=5)
    claude_home.sub(p, "done1", [assistant([{"type": "text", "text": "fin"}], stop_reason="end_turn")],
                    meta={"agentType": "general"}, ago=5)
    claude_home.sub(p, "old1", [assistant([tool_use("b", "Read")])], ago=activity.SUB_QUIET_SEC + 60)
    subs = activity.running_subagents(p, time.time())
    assert [s["id"] for s in subs] == ["run1"]
    assert subs[0]["type"] == "Explore" and subs[0]["desc"] == "find auth"
    assert subs[0]["doing"] == {"k": "read", "a": "r.py"}


def test_running_subagents_no_folder(claude_home):
    p = claude_home.write("s1", [user("hi")])
    assert activity.running_subagents(p, time.time()) == []
