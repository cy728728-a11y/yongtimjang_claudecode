# core.py 규칙 테스트
import os
import sys
import zipfile
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from core import (  # noqa: E402
    data_date_of_zip, files_to_trash, load_state, make_title, round_status,
    save_state, upload_name,
)


def test_title_has_no_leading_zero():
    assert make_title(date(2026, 12, 3)) == "2026년 12월 3일 최신화"


def test_data_date_is_latest_entry_date(tmp_path):
    p = tmp_path / "a.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr(zipfile.ZipInfo("a.xlsx", (2026, 9, 29, 0, 0, 0)), b"x")
        z.writestr(zipfile.ZipInfo("b.xlsx", (2026, 9, 30, 0, 0, 0)), b"y")
    assert data_date_of_zip(str(p)) == "20260930"


def test_upload_name():
    assert upload_name("20260930") == "SellarSourcingAll_20260930.zip"


def test_round_status():
    s = {"rounds": {"20260930": {"file_id": "x", "link": "L", "article_url": None, "posted_at": None},
                    "20260916": {"file_id": "y", "link": "M", "article_url": "U", "posted_at": "t"}}}
    assert round_status(s, "20260930") == "uploaded"
    assert round_status(s, "20260916") == "posted"
    assert round_status(s, "20261014") == "new"


def test_trash_keeps_3_latest_and_ignores_other_files():
    files = [{"id": str(i), "name": f"SellarSourcingAll_2026090{i}.zip", "createdTime": f"2026-09-0{i}T00:00:00Z"}
             for i in range(1, 6)]
    files.append({"id": "other", "name": "메모.txt", "createdTime": "2020-01-01T00:00:00Z"})
    out = files_to_trash(files, keep=3)
    assert sorted(f["id"] for f in out) == ["1", "2"]


def test_state_missing_file_is_empty(tmp_path):
    assert load_state(str(tmp_path / "x.json")) == {"rounds": {}}


def test_state_roundtrip(tmp_path):
    p = str(tmp_path / "s.json")
    s = {"rounds": {"20260930": {"file_id": "x", "link": "L", "article_url": None, "posted_at": None}}}
    save_state(p, s)
    assert load_state(p) == s


def test_trash_order_follows_name_date_not_mod_time():
    # rclone 의 수정시각은 원본 파일 시각이라 믿을 수 없다 → 이름의 날짜로 판단
    files = [{"id": "new", "name": "SellarSourcingAll_20261118.zip", "createdTime": "2020-01-01"},
             {"id": "a", "name": "SellarSourcingAll_20260930.zip", "createdTime": "2026-12-01"},
             {"id": "b", "name": "SellarSourcingAll_20260902.zip", "createdTime": "2026-12-02"},
             {"id": "old", "name": "SellarSourcingAll_20260819.zip", "createdTime": "2026-12-03"}]
    assert [f["id"] for f in files_to_trash(files, keep=3)] == ["old"]
