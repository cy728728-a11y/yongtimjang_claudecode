import json
from types import SimpleNamespace

import classifier


class FakeMessages:
    def __init__(self, response_text):
        self._response_text = response_text

    def create(self, model, max_tokens, system, messages):
        block = SimpleNamespace(text=self._response_text)
        return SimpleNamespace(content=[block])


class FakeAnthropic:
    def __init__(self, response_text):
        self.messages = FakeMessages(response_text)


def test_classify_email_returns_junk(monkeypatch):
    fake_response = json.dumps({"category": "junk", "reason": "정산금액 입금 알림"})
    monkeypatch.setattr(
        classifier.anthropic, "Anthropic",
        lambda api_key: FakeAnthropic(fake_response)
    )
    result = classifier.classify_email("정산금액 입금 완료 안내입니다.", "smartstore_noreply@navercorp.com", "정산금액이 입금되었습니다.", "fake-key")
    assert result == {"category": "junk", "reason": "정산금액 입금 알림"}


def test_classify_email_returns_forward(monkeypatch):
    fake_response = json.dumps({"category": "forward", "reason": "클린위반 경고"})
    monkeypatch.setattr(
        classifier.anthropic, "Anthropic",
        lambda api_key: FakeAnthropic(fake_response)
    )
    result = classifier.classify_email("클린위반 안내", "noreply@navercorp.com", "클린위반 사례로 접수되었습니다.", "fake-key")
    assert result == {"category": "forward", "reason": "클린위반 경고"}


def test_classify_email_defaults_to_forward_on_invalid_category(monkeypatch):
    fake_response = json.dumps({"category": "spam", "reason": "모름"})
    monkeypatch.setattr(
        classifier.anthropic, "Anthropic",
        lambda api_key: FakeAnthropic(fake_response)
    )
    result = classifier.classify_email("제목", "a@b.com", "본문", "fake-key")
    assert result["category"] == "forward"


def test_classify_email_defaults_to_forward_on_api_error(monkeypatch):
    class BrokenAnthropic:
        def __init__(self, api_key):
            raise RuntimeError("네트워크 오류")

    monkeypatch.setattr(classifier.anthropic, "Anthropic", BrokenAnthropic)
    result = classifier.classify_email("제목", "a@b.com", "본문", "fake-key")
    assert result["category"] == "forward"


def test_classify_email_strips_markdown_code_fence(monkeypatch):
    fake_response = '```json\n{"category": "junk", "reason": "광고"}\n```'
    monkeypatch.setattr(
        classifier.anthropic, "Anthropic",
        lambda api_key: FakeAnthropic(fake_response)
    )
    result = classifier.classify_email("제목", "a@b.com", "본문", "fake-key")
    assert result == {"category": "junk", "reason": "광고"}
