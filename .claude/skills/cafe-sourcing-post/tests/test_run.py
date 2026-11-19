# run.py 전체 흐름 테스트 — 받기·드라이브·카페·메일을 전부 가짜로 바꿔서 순서와 분기만 본다
import os
import sys
import zipfile
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import cafe  # noqa: E402
import core  # noqa: E402
import drive  # noqa: E402
import run  # noqa: E402

TODAY = date(2026, 12, 7)
TITLE = "2026년 12월 7일 최신화"


def make_zip(tmp_path, ymd=(2026, 12, 2)):
    p = tmp_path / "dl.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr(zipfile.ZipInfo("a.xlsx", ymd + (0, 0, 0)), b"x")
    return str(p)


@pytest.fixture
def env(tmp_path, monkeypatch):
    """가짜 세계: 호출 기록(log)과 보낸 메일(mails)을 모은다."""
    log, mails = [], []
    monkeypatch.setattr(run, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(run, "download_zip", lambda out_dir: make_zip(tmp_path))
    monkeypatch.setattr(run.drive, "upload", lambda p, n, f: log.append(("upload", n)) or "FID")
    monkeypatch.setattr(run.drive, "share_anyone_reader", lambda fid: log.append(("share", fid)))
    monkeypatch.setattr(run.drive, "list_folder", lambda f: [
        {"id": str(i), "name": f"SellarSourcingAll_2026090{i}.zip", "createdTime": f"2026-09-0{i}"} for i in range(1, 5)])
    monkeypatch.setattr(run.drive, "trash", lambda fid: log.append(("trash", fid)))
    monkeypatch.setattr(run.drive, "find_by_name", lambda f, n: None)
    monkeypatch.setattr(run.drive, "set_description", lambda fid, t: None)
    monkeypatch.setattr(run.cafe, "load_config", lambda: {"club_id": "1", "menu_id": "2"})
    monkeypatch.setattr(run.cafe, "post_article",
                        lambda cfg, s, c: log.append(("post", s, c)) or "https://cafe.naver.com/hz/1")
    monkeypatch.setattr(run.notify, "send_mail", lambda subj, body: mails.append((subj, body)))
    return {"log": log, "mails": mails, "tmp": tmp_path}


LINK = drive.file_link("FID")


def test_new_round_uploads_posts_trashes_and_mails(env):
    assert run.run(TODAY) == "posted"
    kinds = [e[0] for e in env["log"]]
    assert kinds[:3] == ["upload", "share", "post"]
    assert ("upload", "SellarSourcingAll_20261202.zip") in env["log"]
    assert ("post", TITLE, cafe.make_content(LINK)) in env["log"]
    assert ("trash", "SellarSourcingAll_20260901.zip") in env["log"]  # 4개 중 가장 오래된 1개만
    assert kinds.index("trash") > kinds.index("post")
    st = core.load_state(run.STATE_PATH)
    assert core.round_status(st, "20261202") == "posted"
    assert len(env["mails"]) == 1


def test_same_date_skipped_no_mail(env):
    run.run(TODAY)
    env["log"].clear(); env["mails"].clear()
    assert run.run(TODAY) == "skipped"
    assert env["log"] == [] and env["mails"] == []


def test_uploaded_round_posts_without_reupload(env):
    core.save_state(run.STATE_PATH, {"rounds": {"20261202": {
        "file_id": "OLD", "link": "https://old", "article_url": None, "posted_at": None}}})
    assert run.run(TODAY) == "posted"
    kinds = [e[0] for e in env["log"]]
    assert "upload" not in kinds
    assert ("post", TITLE, cafe.make_content("https://old")) in env["log"]


def test_cafe_auth_error_mails_title_and_link(env, monkeypatch):
    def boom(cfg, s, c):
        raise cafe.CafeAuthError("만료")
    monkeypatch.setattr(run.cafe, "post_article", boom)
    assert run.run(TODAY) == "failed"
    subj, body = env["mails"][-1]
    assert TITLE in body and LINK in body and "cafe_setup.py" in body
    # 업로드는 됐으니 다음엔 다시 올리지 않도록 기록이 남아야 한다
    assert core.round_status(core.load_state(run.STATE_PATH), "20261202") == "uploaded"


def test_download_failure_mails_setup_hint(env, monkeypatch):
    def boom(out_dir):
        raise run.DownloadError("로그인 필요")
    monkeypatch.setattr(run, "download_zip", boom)
    assert run.run(TODAY) == "failed"
    assert "--setup" in env["mails"][-1][1]
    assert env["log"] == []


def test_drive_auth_error_mails_rclone_hint(env, monkeypatch):
    def boom(p, n, f):
        raise drive.DriveAuthError("만료")
    monkeypatch.setattr(run.drive, "upload", boom)
    assert run.run(TODAY) == "failed"
    assert "rclone config reconnect" in env["mails"][-1][1]


def test_trash_failure_does_not_fail_round(env, monkeypatch):
    def boom(fid):
        raise drive.DriveError("x")
    monkeypatch.setattr(run.drive, "trash", boom)
    assert run.run(TODAY) == "posted"


def test_dry_run_has_no_side_effects(env):
    assert run.run(TODAY, dry_run=True) == "dry-run"
    assert env["log"] == [] and env["mails"] == []
    assert not os.path.exists(run.STATE_PATH)


def test_given_zip_is_not_deleted(env):
    z = make_zip(env["tmp"])
    run.run(TODAY, zip_path=z)
    assert os.path.exists(z)


def test_existing_drive_file_is_reused_not_reuploaded(env, monkeypatch):
    # 다른 PC 가 이미 올렸거나, 공유 직전에 끊겨 기록이 없는 경우
    monkeypatch.setattr(run.drive, "find_by_name", lambda f, n: {"id": "EXIST", "name": n, "description": ""})
    assert run.run(TODAY) == "posted"
    kinds = [e[0] for e in env["log"]]
    assert "upload" not in kinds and ("share", "SellarSourcingAll_20261202.zip") in env["log"]


def test_drive_description_marks_posted_across_pcs(env, monkeypatch):
    monkeypatch.setattr(run.drive, "find_by_name",
                        lambda f, n: {"id": "EXIST", "name": n, "description": "게시: https://cafe.naver.com/hz/5"})
    assert run.run(TODAY) == "skipped"
    assert [e[0] for e in env["log"]] == []
    assert core.round_status(core.load_state(run.STATE_PATH), "20261202") == "posted"


def test_post_records_article_on_drive_file(env, monkeypatch):
    marks = []
    monkeypatch.setattr(run.drive, "set_description", lambda fid, t: marks.append((fid, t)))
    run.run(TODAY)
    assert marks == [("SellarSourcingAll_20261202.zip", "게시: https://cafe.naver.com/hz/1")]


def test_cafe_failure_mail_says_do_not_post_by_hand(env, monkeypatch):
    def boom(cfg, s, c):
        raise cafe.CafeAuthError("만료")
    monkeypatch.setattr(run.cafe, "post_article", boom)
    run.run(TODAY)
    body = env["mails"][-1][1]
    assert "직접 올리지 마" in body


def test_unexpected_error_still_mails(env, monkeypatch, tmp_path):
    bad = tmp_path / "not.zip"
    bad.write_bytes(b"xlsx not zip")
    monkeypatch.setattr(run, "download_zip", lambda out_dir: str(bad))
    assert run.run(TODAY) == "failed"
    assert env["mails"] and "unknown" in env["mails"][-1][0]
