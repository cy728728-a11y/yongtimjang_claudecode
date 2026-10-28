"""시험 공통 준비 — server/ 를 import 경로에 넣고, 가짜 ~/.claude 폴더를 tmp 에 만든다.

실제 ~/.claude 는 절대 건드리지 않는다: CLAUDE_CONFIG_DIR 을 tmp 로 바꿔 끼운다.
"""
import json
import os
import sys
import time
from pathlib import Path

import pytest

SERVER_DIR = Path(__file__).resolve().parent.parent / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))


def _line(obj):
    """dict 는 JSON 한 줄로, 문자열은 그대로"""
    if isinstance(obj, (bytes, str)):
        return obj if isinstance(obj, str) else obj.decode("utf-8")
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


class ClaudeHome:
    """가짜 Claude 설정 폴더 헬퍼"""

    def __init__(self, root: Path):
        self.root = root
        self.projects = root / "projects"
        self.projects.mkdir(parents=True, exist_ok=True)

    def write(self, sid, lines, enc="-Users-me-ws", ago=None):
        """projects/<enc>/<sid>.jsonl 을 만든다. ago 초 전으로 mtime 을 맞춘다"""
        d = self.projects / enc
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{sid}.jsonl"
        p.write_text("".join(_line(x) + "\n" for x in lines), encoding="utf-8")
        if ago is not None:
            self.set_mtime(p, ago)
        return p

    def sub(self, transcript: Path, agent_id, lines, meta=None, ago=None):
        """대화 파일 옆 <sid>/subagents/agent-<id>.jsonl (+ .meta.json)"""
        d = transcript.with_suffix("") / "subagents"
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"agent-{agent_id}.jsonl"
        p.write_text("".join(_line(x) + "\n" for x in lines), encoding="utf-8")
        if meta is not None:
            (d / f"agent-{agent_id}.meta.json").write_text(json.dumps(meta), encoding="utf-8")
        if ago is not None:
            self.set_mtime(p, ago)
        return p

    @staticmethod
    def set_mtime(path, ago):
        """mtime 을 ago 초 전으로"""
        t = time.time() - ago
        os.utime(path, (t, t))


@pytest.fixture
def claude_home(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    # 모듈 캐시가 시험 사이에 새지 않게 비운다
    for name in ("activity", "sessions", "teams", "snapshot"):
        mod = sys.modules.get(name)
        if mod is not None and hasattr(mod, "forget"):
            mod.forget()
    return ClaudeHome(tmp_path / "claude")


# ── 대화 줄 만들기 헬퍼 ──────────────────────────────────────
def assistant(content, stop_reason=None, ts="2026-10-28T01:00:00.000Z", cwd="/Users/me/ws", **extra):
    e = {"type": "assistant", "timestamp": ts, "cwd": cwd,
         "message": {"role": "assistant", "content": content, "stop_reason": stop_reason}}
    e.update(extra)
    return e


def user(content, ts="2026-10-28T01:00:01.000Z", cwd="/Users/me/ws", **extra):
    e = {"type": "user", "timestamp": ts, "cwd": cwd, "message": {"role": "user", "content": content}}
    e.update(extra)
    return e


def tool_use(tid, name="Read", inp=None):
    return {"type": "tool_use", "id": tid, "name": name, "input": inp or {"file_path": "/a/b/server.py"}}


def tool_result(tid, text="ok"):
    return {"type": "tool_result", "tool_use_id": tid, "content": text}
