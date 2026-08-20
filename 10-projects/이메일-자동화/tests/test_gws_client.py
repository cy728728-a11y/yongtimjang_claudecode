import json
import subprocess

import pytest

import gws_client


class FakeCompletedProcess:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_list_unread_messages_parses_json(monkeypatch):
    fake_output = json.dumps({
        "messages": [{"id": "abc123", "from": "a@b.com", "subject": "제목", "date": "today"}]
    })

    def fake_run(cmd, capture_output, text, encoding, timeout):
        assert cmd[0] == "node"
        assert cmd[1] == gws_client.GWS_RUN_JS
        assert "+triage" in cmd
        return FakeCompletedProcess(0, stdout=fake_output)

    monkeypatch.setattr(subprocess, "run", fake_run)
    messages = gws_client.list_unread_messages(max_count=10)
    assert messages == [{"id": "abc123", "from": "a@b.com", "subject": "제목", "date": "today"}]


def test_run_gws_raises_on_nonzero_exit(monkeypatch):
    def fake_run(cmd, capture_output, text, encoding, timeout):
        return FakeCompletedProcess(1, stdout="", stderr="인증 만료됨")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(gws_client.GwsError):
        gws_client.list_unread_messages()


def test_trash_message_builds_correct_params(monkeypatch):
    captured = {}

    def fake_run(cmd, capture_output, text, encoding, timeout):
        captured["cmd"] = cmd
        return FakeCompletedProcess(0, stdout="{}")

    monkeypatch.setattr(subprocess, "run", fake_run)
    gws_client.trash_message("msg-1")

    assert "trash" in captured["cmd"]
    params_index = captured["cmd"].index("--params") + 1
    assert json.loads(captured["cmd"][params_index]) == {"userId": "me", "id": "msg-1"}
