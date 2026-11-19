# drive.py 테스트 — rclone 호출은 가짜로 바꿔서 확인
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import drive  # noqa: E402


class FakeRun:
    """subprocess.run 대역: 호출 기록 + (명령 → 출력) 규칙으로 돌려주기"""

    def __init__(self, rules=None, returncode=0, stderr=""):
        self.calls = []
        self.rules = rules or {}
        self.returncode = returncode
        self.stderr = stderr

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        out = ""
        for key, val in self.rules.items():
            if key in cmd:
                out = val
        return subprocess.CompletedProcess(cmd, self.returncode, stdout=out, stderr=self.stderr)


LS = json.dumps([
    {"Name": "SellarSourcingAll_20260930.zip", "ID": "A", "ModTime": "2026-11-19T10:00:00Z"},
    {"Name": "posted_SellarSourcingAll_20260930.txt", "ID": "M", "ModTime": "2026-11-19T10:00:00Z"},
])


def test_upload_copies_into_folder_and_returns_id(monkeypatch):
    fake = FakeRun({"lsjson": LS})
    monkeypatch.setattr(drive.subprocess, "run", fake)
    fid = drive.upload("x/a.zip", "SellarSourcingAll_20260930.zip", "FOLDER")
    assert fid == "A"
    up = fake.calls[0]
    assert "copyto" in up and "x/a.zip" in up
    assert f"{drive.REMOTE}:SellarSourcingAll_20260930.zip" in up
    assert "--drive-root-folder-id" in up and up[up.index("--drive-root-folder-id") + 1] == "FOLDER"


def test_share_makes_public_link(monkeypatch):
    fake = FakeRun()
    monkeypatch.setattr(drive.subprocess, "run", fake)
    drive.share_anyone_reader("n.zip")
    assert "link" in fake.calls[0] and f"{drive.REMOTE}:n.zip" in fake.calls[0]


def test_list_folder_maps_fields(monkeypatch):
    monkeypatch.setattr(drive.subprocess, "run", FakeRun({"lsjson": LS}))
    files = drive.list_folder("FOLDER")
    assert {"id": "A", "name": "SellarSourcingAll_20260930.zip", "createdTime": "2026-11-19T10:00:00Z"} in files


def test_find_by_name_reads_posted_marker(monkeypatch):
    monkeypatch.setattr(drive.subprocess, "run", FakeRun({"lsjson": LS, "cat": "게시: U\n"}))
    f = drive.find_by_name("FOLDER", "SellarSourcingAll_20260930.zip")
    assert f == {"id": "A", "name": "SellarSourcingAll_20260930.zip", "description": "게시: U"}


def test_find_by_name_none_when_missing(monkeypatch):
    monkeypatch.setattr(drive.subprocess, "run", FakeRun({"lsjson": "[]"}))
    assert drive.find_by_name("FOLDER", "n.zip") is None


def test_set_description_writes_marker_file(monkeypatch):
    fake = FakeRun()
    monkeypatch.setattr(drive.subprocess, "run", fake)
    drive.set_description("SellarSourcingAll_20260930.zip", "게시: U")
    cmd = fake.calls[0]
    assert "rcat" in cmd and f"{drive.REMOTE}:posted_SellarSourcingAll_20260930.txt" in cmd


def test_trash_by_name(monkeypatch):
    fake = FakeRun()
    monkeypatch.setattr(drive.subprocess, "run", fake)
    drive.trash("old.zip")
    assert "deletefile" in fake.calls[0] and f"{drive.REMOTE}:old.zip" in fake.calls[0]


def test_auth_error_detected(monkeypatch):
    monkeypatch.setattr(drive.subprocess, "run",
                        FakeRun(returncode=1, stderr="Failed to create file system: couldn't fetch token: invalid_grant"))
    with pytest.raises(drive.DriveAuthError):
        drive.list_folder("FOLDER")


def test_other_error_is_drive_error_not_auth(monkeypatch):
    monkeypatch.setattr(drive.subprocess, "run", FakeRun(returncode=3, stderr="directory not found"))
    with pytest.raises(drive.DriveError) as e:
        drive.trash("x")
    assert not isinstance(e.value, drive.DriveAuthError)


def test_link_format():
    assert drive.file_link("F123") == "https://drive.google.com/file/d/F123/view?usp=drive_link"


def test_find_by_name_returns_file_with_description(monkeypatch):
    fake = FakeRun(stdout=json.dumps({"files": [{"id": "F9", "name": "n.zip", "description": "게시: U"}]}))
    monkeypatch.setattr(drive.subprocess, "run", fake)
    f = drive.find_by_name("FOLDER", "n.zip")
    assert f["id"] == "F9" and f["description"] == "게시: U"
    q = json.loads(fake.calls[0][fake.calls[0].index("--params") + 1])["q"]
    assert "name='n.zip'" in q and "'FOLDER' in parents" in q


def test_find_by_name_none_when_missing(monkeypatch):
    monkeypatch.setattr(drive.subprocess, "run", FakeRun(stdout=json.dumps({"files": []})))
    assert drive.find_by_name("FOLDER", "n.zip") is None


def test_set_description(monkeypatch):
    fake = FakeRun(stdout=json.dumps({"id": "F9"}))
    monkeypatch.setattr(drive.subprocess, "run", fake)
    drive.set_description("F9", "게시: U")
    cmd = fake.calls[0]
    assert json.loads(cmd[cmd.index("--json") + 1]) == {"description": "게시: U"}
