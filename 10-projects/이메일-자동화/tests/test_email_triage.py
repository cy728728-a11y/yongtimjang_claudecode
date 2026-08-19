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
    success_calls = []

    monkeypatch.setattr(gws_client, "trash_message", lambda mid: trashed_ids.append(mid))
    monkeypatch.setattr(gws_client, "forward_message", lambda mid, to: forwarded_ids.append((mid, to)))
    monkeypatch.setattr(gws_client, "mark_read", lambda mid: marked_read_ids.append(mid))
    monkeypatch.setattr(gws_client, "append_log_row", lambda sheet_id, row: logged_rows.append(row))
    monkeypatch.setattr(state, "record_success", lambda ts: success_calls.append(ts))

    summary = email_triage.process_inbox(api_key="fake-key", sheet_id="sheet-123", dry_run=False)

    assert trashed_ids == ["m1"]
    assert forwarded_ids == [("m2", email_triage.FORWARD_TO)]
    assert marked_read_ids == ["m2"]
    assert len(logged_rows) == 2
    assert len(summary["trashed"]) == 1
    assert len(summary["forwarded"]) == 1
    assert summary["errors"] == []
    # finding 6: record_success가 정확히 1회 호출됐는지 검증(기존엔 no-op 스텁만 있고 미검증)
    assert len(success_calls) == 1


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

    def fail_if_called(*args, **kwargs):
        raise AssertionError("errors가 있으면 record_success가 호출되면 안 됨")

    monkeypatch.setattr(state, "record_success", fail_if_called)

    summary = email_triage.process_inbox(api_key="fake-key", sheet_id=None, dry_run=False)

    assert len(summary["errors"]) == 1
    assert len(summary["forwarded"]) == 1


def test_process_inbox_forward_circuit_breaker_stops_after_consecutive_failures(monkeypatch):
    """finding 1: 전달이 연속 N회 실패하면(gmail.send 스코프 문제 등) 이후 메일은 건드리지 않고 중단해야 한다."""
    threshold = email_triage.FORWARD_FAILURE_THRESHOLD
    total = threshold + 2  # 임계치보다 메일이 더 있어야 "중단됐는지" 확인 가능
    messages = [{"id": f"m{i}"} for i in range(1, total + 1)]
    detail_map = {
        f"m{i}": {"subject": f"제목{i}", "from": {"email": "a@navercorp.com"}, "body_text": "본문"}
        for i in range(1, total + 1)
    }
    read_ids = []

    def read_message(mid):
        read_ids.append(mid)
        return detail_map[mid]

    monkeypatch.setattr(gws_client, "list_unread_messages", lambda max_count=50: messages)
    monkeypatch.setattr(gws_client, "read_message", read_message)
    monkeypatch.setattr(
        classifier, "classify_email",
        lambda subject, sender, body_text, api_key: {"category": "forward", "reason": "확인 필요"}
    )

    def always_fail_forward(mid, to):
        raise gws_client.GwsError("gmail.send 스코프 없음")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("전달이 중단된 뒤에는 호출되면 안 됨")

    monkeypatch.setattr(gws_client, "forward_message", always_fail_forward)
    monkeypatch.setattr(gws_client, "trash_message", fail_if_called)
    monkeypatch.setattr(gws_client, "mark_read", fail_if_called)
    monkeypatch.setattr(gws_client, "append_log_row", fail_if_called)

    def fail_record_success(*args, **kwargs):
        raise AssertionError("errors가 있으면 record_success가 호출되면 안 됨")

    monkeypatch.setattr(state, "record_success", fail_record_success)

    summary = email_triage.process_inbox(api_key="fake-key", sheet_id=None, dry_run=False)

    # 임계치만큼만 시도하고 나머지 메일은 아예 건드리지 않아야 한다.
    assert read_ids == [f"m{i}" for i in range(1, threshold + 1)]
    assert summary["forwarded"] == []
    assert any(f"연속 {threshold}회 전달 실패로 실행 중단" in e for e in summary["errors"])


def test_process_inbox_forward_scattered_failures_do_not_trip_breaker(monkeypatch):
    """finding 1: 연속이 아니라 간헐적으로 섞인 전달 실패는 전체 배치를 중단시키면 안 된다."""
    messages = [{"id": f"m{i}"} for i in range(1, 6)]
    detail_map = {
        f"m{i}": {"subject": f"제목{i}", "from": {"email": "a@navercorp.com"}, "body_text": "본문"}
        for i in range(1, 6)
    }
    read_ids = []

    def read_message(mid):
        read_ids.append(mid)
        return detail_map[mid]

    monkeypatch.setattr(gws_client, "list_unread_messages", lambda max_count=50: messages)
    monkeypatch.setattr(gws_client, "read_message", read_message)
    monkeypatch.setattr(
        classifier, "classify_email",
        lambda subject, sender, body_text, api_key: {"category": "forward", "reason": "확인 필요"}
    )

    fail_ids = {"m1", "m3", "m5"}  # 실패가 연속이 아니라 하나씩 걸러 발생
    marked_read_ids = []

    def forward_message(mid, to):
        if mid in fail_ids:
            raise gws_client.GwsError("일시적 전달 실패")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("이 테스트에서는 junk가 없어야 함")

    monkeypatch.setattr(gws_client, "forward_message", forward_message)
    monkeypatch.setattr(gws_client, "mark_read", lambda mid: marked_read_ids.append(mid))
    monkeypatch.setattr(gws_client, "trash_message", fail_if_called)

    summary = email_triage.process_inbox(api_key="fake-key", sheet_id=None, dry_run=False)

    # 중단되지 않고 5건 전부 시도돼야 한다.
    assert read_ids == [f"m{i}" for i in range(1, 6)]
    assert marked_read_ids == ["m2", "m4"]
    assert not any("실행 중단" in e for e in summary["errors"])
    assert len(summary["errors"]) == 3  # m1, m3, m5 개별 실패만 기록(회로차단기 미발동)


def test_process_inbox_log_row_failure_does_not_count_as_processing_error(monkeypatch):
    """finding 2/3: 시트 로그 기록 실패는 이미 성공한 메일 처리를 실패로 오귀속시키거나
    record_success를 막으면 안 되고, 별도 log_errors로만 남아야 한다."""
    messages = [{"id": "m1"}]
    detail_map = {
        "m1": {"subject": "정산금액 입금 완료 안내입니다.", "from": {"email": "a@navercorp.com"}, "body_text": "정산 입금"},
    }
    classify_result_map = {
        "정산금액 입금 완료 안내입니다.": {"category": "junk", "reason": "정산 입금 알림"},
    }
    _patch_common(monkeypatch, messages, detail_map, classify_result_map)

    trashed_ids = []
    monkeypatch.setattr(gws_client, "trash_message", lambda mid: trashed_ids.append(mid))

    def failing_append_log_row(sheet_id, row):
        raise gws_client.GwsError("시트 API 일시 오류")

    monkeypatch.setattr(gws_client, "append_log_row", failing_append_log_row)

    success_calls = []
    monkeypatch.setattr(state, "record_success", lambda ts: success_calls.append(ts))

    summary = email_triage.process_inbox(api_key="fake-key", sheet_id="sheet-123", dry_run=False)

    assert trashed_ids == ["m1"]  # 실제 메일 처리(휴지통)는 성공
    assert summary["errors"] == []  # 로그 실패가 처리 실패로 오귀속되면 안 됨
    assert len(summary["log_errors"]) == 1
    assert len(success_calls) == 1  # 로그 실패가 record_success를 막으면 안 됨


def test_process_inbox_warns_when_unread_count_hits_max(monkeypatch):
    """finding 4: 안읽은 메일이 max_count와 같으면(=더 있을 수 있음) 경고 신호를 남겨야 한다."""
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
    monkeypatch.setattr(gws_client, "trash_message", lambda mid: None)
    monkeypatch.setattr(gws_client, "forward_message", lambda mid, to: None)
    monkeypatch.setattr(gws_client, "mark_read", lambda mid: None)
    monkeypatch.setattr(gws_client, "append_log_row", lambda sheet_id, row: None)
    monkeypatch.setattr(state, "record_success", lambda ts: None)

    # messages 개수(2) == max_count(2) -> 잘림 가능성 경고가 있어야 함
    summary_truncated = email_triage.process_inbox(api_key="fake-key", sheet_id="sheet-123", dry_run=False, max_count=2)
    assert any("2건 이상일 수 있음" in w for w in summary_truncated["warnings"])

    # messages 개수(2) < max_count(5) -> 경고 없어야 함
    summary_ok = email_triage.process_inbox(api_key="fake-key", sheet_id="sheet-123", dry_run=False, max_count=5)
    assert summary_ok["warnings"] == []
