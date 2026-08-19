import email_triage
import gws_client
import classifier
import state


def _patch_common(monkeypatch, messages, detail_map, classify_result_map):
    # email_triage.py는 "gws_client.func(...)" 형태로 호출 시점에 모듈 속성을 조회하므로
    # 아래처럼 실제 모듈 객체의 속성을 바꿔치기하면 email_triage.py 쪽 호출에도 그대로 반영된다.
    monkeypatch.setattr(gws_client, "list_unread_messages", lambda max_count=50: messages)
    monkeypatch.setattr(gws_client, "read_message", lambda mid: detail_map[mid])
    monkeypatch.setattr(
        classifier, "classify_email",
        lambda subject, sender, body_text, api_key: classify_result_map[subject]
    )


def test_process_inbox_trashes_junk_and_forwards_important(monkeypatch):
    messages = [{"id": "m1"}, {"id": "m2"}]
    detail_map = {
        "m1": {"subject": "정산금액 입금 완료 안내입니다.", "from": {"email": "a@navercorp.com"}, "body_text": "정산 입금"},
        "m2": {"subject": "클린위반 안내", "from": {"email": "b@navercorp.com"}, "body_text": "클린위반 사례"},
    }
    classify_result_map = {
        "정산금액 입금 완료 안내입니다.": {"category": "junk", "reason": "정산 입금 알림"},
        "클린위반 안내": {"category": "forward", "reason": "클린위반 경고"},
    }
    _patch_common(monkeypatch, messages, detail_map, classify_result_map)

    trashed_ids = []
    forwarded_ids = []
    marked_read_ids = []
    logged_rows = []

    monkeypatch.setattr(gws_client, "trash_message", lambda mid: trashed_ids.append(mid))
    monkeypatch.setattr(gws_client, "forward_message", lambda mid, to: forwarded_ids.append((mid, to)))
    monkeypatch.setattr(gws_client, "mark_read", lambda mid: marked_read_ids.append(mid))
    monkeypatch.setattr(gws_client, "append_log_row", lambda sheet_id, row: logged_rows.append(row))
    monkeypatch.setattr(state, "record_success", lambda ts: None)

    summary = email_triage.process_inbox(api_key="fake-key", sheet_id="sheet-123", dry_run=False)

    assert trashed_ids == ["m1"]
    assert forwarded_ids == [("m2", email_triage.FORWARD_TO)]
    assert marked_read_ids == ["m2"]
    assert len(logged_rows) == 2
    assert len(summary["trashed"]) == 1
    assert len(summary["forwarded"]) == 1
    assert summary["errors"] == []


def test_process_inbox_dry_run_does_not_call_mutating_actions(monkeypatch):
    messages = [{"id": "m1"}]
    detail_map = {
        "m1": {"subject": "정산금액 입금 완료 안내입니다.", "from": {"email": "a@navercorp.com"}, "body_text": "정산 입금"},
    }
    classify_result_map = {
        "정산금액 입금 완료 안내입니다.": {"category": "junk", "reason": "정산 입금 알림"},
    }
    _patch_common(monkeypatch, messages, detail_map, classify_result_map)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("dry-run에서는 호출되면 안 됨")

    monkeypatch.setattr(gws_client, "trash_message", fail_if_called)
    monkeypatch.setattr(gws_client, "forward_message", fail_if_called)
    monkeypatch.setattr(gws_client, "mark_read", fail_if_called)
    monkeypatch.setattr(gws_client, "append_log_row", fail_if_called)

    summary = email_triage.process_inbox(api_key="fake-key", sheet_id="sheet-123", dry_run=True)

    assert len(summary["trashed"]) == 1


def test_process_inbox_records_error_and_continues(monkeypatch):
    messages = [{"id": "m1"}, {"id": "m2"}]
    detail_map = {
        "m2": {"subject": "클린위반 안내", "from": {"email": "b@navercorp.com"}, "body_text": "클린위반"},
    }

    def read_message(mid):
        if mid not in detail_map:
            raise gws_client.GwsError("메일을 찾을 수 없음")
        return detail_map[mid]

    monkeypatch.setattr(gws_client, "list_unread_messages", lambda max_count=50: messages)
    monkeypatch.setattr(gws_client, "read_message", read_message)
    monkeypatch.setattr(
        classifier, "classify_email",
        lambda subject, sender, body_text, api_key: {"category": "forward", "reason": "클린위반"}
    )
    monkeypatch.setattr(gws_client, "forward_message", lambda mid, to: None)
    monkeypatch.setattr(gws_client, "mark_read", lambda mid: None)
    monkeypatch.setattr(state, "record_success", lambda ts: None)

    summary = email_triage.process_inbox(api_key="fake-key", sheet_id=None, dry_run=False)

    assert len(summary["errors"]) == 1
    assert len(summary["forwarded"]) == 1
