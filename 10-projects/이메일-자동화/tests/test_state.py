import state


def test_record_and_read_last_success(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "STATE_DIR", tmp_path / ".state")
    monkeypatch.setattr(state, "LAST_SUCCESS_FILE", tmp_path / ".state" / "last_success.json")

    state.record_success("2026-08-19T09:00:00+00:00")

    assert state.read_last_success() == "2026-08-19T09:00:00+00:00"


def test_read_last_success_returns_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "LAST_SUCCESS_FILE", tmp_path / "nope.json")
    assert state.read_last_success() is None
