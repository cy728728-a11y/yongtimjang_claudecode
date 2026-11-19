# notify.py — 메일이 안 갈 때도 흔적을 남기는지
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import drive  # noqa: E402
import notify  # noqa: E402


def test_mail_failure_leaves_failure_file(monkeypatch, tmp_path):
    def boom(args, cwd=None):
        raise drive.DriveAuthError("만료")
    monkeypatch.setattr(notify.drive, "_gws", boom)
    monkeypatch.setattr(notify, "FAIL_PATH", str(tmp_path / "LAST-FAILURE.txt"))
    monkeypatch.setattr(notify, "_desktop_alert", lambda s: None)
    notify.send_mail("제목A", "본문B")
    text = open(notify.FAIL_PATH, encoding="utf-8").read()
    assert "제목A" in text and "본문B" in text
