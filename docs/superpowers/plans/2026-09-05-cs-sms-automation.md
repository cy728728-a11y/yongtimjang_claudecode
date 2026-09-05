# CS 전용 휴대폰 문자 CS 자동화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** CS 전용 안드로이드 폰으로 오는 문자를 구글시트에 자동 수집하고, 독립 Python 스크립트가 1시간마다 무인 실행되어 답변 초안까지 자동 생성해, CS 직원이 시트에서 검토 후 폰으로 직접 발송할 수 있게 한다.

**Architecture:** MacroDroid(폰) → Google Apps Script 웹훅(비밀토큰 검증) → "CS응대로그" 구글시트(채널="문자"로 append, 상태="신규") → `sms_draft.py`(Windows 작업 스케줄러, 1시간마다) → `claude-sonnet-5` API로 유형분류+정보부족판단+초안작성 → 같은 행에 답변초안/상태 반영. `10-projects/이메일-자동화`에서 이미 검증된 "독립 스크립트 + `.env`의 `ANTHROPIC_API_KEY` + Windows 작업 스케줄러" 패턴을 그대로 재사용한다.

**Tech Stack:** Python 3.11(`C:\Users\workspace\.venv`), `anthropic` SDK, `pytest`, gws CLI(Node.js, subprocess로 직접 호출), Google Apps Script(웹앱), MacroDroid(안드로이드 자동화 앱), Windows 작업 스케줄러.

**Spec:** `docs/superpowers/specs/2026-09-05-cs-sms-automation-design.md`

## Global Constraints

- gws 실행은 반드시 `node "C:\Users\woori\AppData\Roaming\npm\node_modules\@googleworkspace\cli\run.js" <args>` 형태로 직접 호출한다. `gws`/`gws.cmd`를 subprocess에서 직접 부르면 못 찾거나 cmd.exe 8,191자 제한에 걸린다(gws-setup 메모리, 이메일 자동화 계획과 동일 제약).
- 시트 값 조회/수정은 `sheets spreadsheets values get` / `sheets spreadsheets values update`(둘 다 `--params '{"spreadsheetId":...,"range":...}'` 형태), append는 helper `sheets +append --spreadsheet ID --json-values '[[...]]'`. (2026-09-05 실측 확인: `sheets spreadsheets values get/update`가 정확한 서브커맨드 경로이며 `spreadsheets.values.get` 같은 점(.) 표기는 동작하지 않음.)
- 초안 생성 모델은 `claude-sonnet-5` 고정 (고객 발송용 문구라 품질 우선 — 이메일 자동화의 단순 2분류용 `claude-haiku-4-5-20251001`과는 다른 선택).
- 분류/판단이 애매하거나 API 호출·파싱이 실패하면 무조건 상태="확인필요"로 처리한다(틀린 초안을 보내는 것보다 사람이 직접 쓰게 하는 게 낫다는 원칙).
- 발송(문자 전송) 기능은 절대 코드에 넣지 않는다 — 항상 CS 직원이 폰에서 직접 발송.
- 코드에는 한국어 주석을 달고, 외부 호출(subprocess/API)은 모두 try-except로 감싼다 (CLAUDE.md 프로필 규칙).
- "CS응대로그" 시트는 8/18 스마트스토어 문의게시판 설계와 공유한다 — 새 시트를 만들지 않는다. 헤더 9열: `작업일 / CS유형 / 상황요약 / 고객원문 / 답변문구 / 비고 / 채널 / 문의번호 / 상태`.
- `.env` 신규 키: `CS_RESPONSE_SHEET_ID`(CS응대로그 스프레드시트 ID), `CS_SMS_WEBHOOK_TOKEN`(Apps Script 웹훅 인증 토큰). `ANTHROPIC_API_KEY`는 이메일 자동화 구축 시 이미 발급된 것을 재사용한다.

---

### Task 1: 프로젝트 준비 (폴더 · 의존성 · 환경변수 템플릿)

**Files:**
- Create: `20-operations/cs-automation/requirements.txt`
- Create: `20-operations/cs-automation/.env.example`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: 없음 (첫 태스크)
- Produces: 이후 모든 태스크가 쓰는 `anthropic`/`pytest` 패키지가 `.venv`에 설치됨. `.env`의 `ANTHROPIC_API_KEY`/`CS_RESPONSE_SHEET_ID`/`CS_SMS_WEBHOOK_TOKEN` 키 이름을 이후 태스크가 그대로 사용.

- [ ] **Step 1: requirements.txt 작성**

```text
anthropic>=0.40.0
pytest>=8.0.0
```

파일 경로: `20-operations/cs-automation/requirements.txt`

- [ ] **Step 2: .env.example 작성**

```text
# CS 문자 자동화(sms_draft.py)용 — 2026-09-05 추가
# Claude API 직접 호출용 키. 이메일 자동화 구축 시 이미 발급됨 — 같은 값 재사용.
ANTHROPIC_API_KEY=여기에_API_키

# "CS응대로그" 구글시트 ID (Task 8에서 생성/확인 후 채움). 8/18 문의게시판 자동화와 공유.
CS_RESPONSE_SHEET_ID=여기에_스프레드시트_ID

# Apps Script 웹훅 인증용 임의의 긴 문자열(Task 6에서 생성). Apps Script 스크립트 속성에도
# 반드시 같은 값을 넣어야 함.
CS_SMS_WEBHOOK_TOKEN=여기에_임의의_긴_랜덤_문자열
```

파일 경로: `20-operations/cs-automation/.env.example`

- [ ] **Step 3: .gitignore에 상태 파일 폴더 추가**

`.gitignore`의 `# Temp / work` 섹션 아래(이메일 자동화 항목 근처)에 추가:

```text
20-operations/cs-automation/.state/
```

- [ ] **Step 4: 패키지 설치**

Run: `& 'C:\Users\workspace\.venv\Scripts\python.exe' -m pip install -r '20-operations\cs-automation\requirements.txt'`
Expected: `anthropic`, `pytest` 이미 설치돼 있다는 메시지 또는 설치 완료 메시지 (이메일 자동화에서 이미 설치됨).

- [ ] **Step 5: Commit**

```bash
git add 20-operations/cs-automation/requirements.txt 20-operations/cs-automation/.env.example .gitignore
git commit -m "chore: CS 문자 자동화 스크립트 의존성·env 템플릿 준비"
```

---

### Task 2: `gws_client.py` — 시트 읽기/쓰기 래퍼

**Files:**
- Create: `20-operations/cs-automation/gws_client.py`
- Create: `20-operations/cs-automation/tests/conftest.py`
- Test: `20-operations/cs-automation/tests/test_gws_client.py`

**Interfaces:**
- Consumes: 없음
- Produces: `gws_client.GwsError`(예외), `gws_client.create_cs_response_sheet() -> str`, `gws_client.fetch_new_sms_rows(spreadsheet_id: str) -> list[dict]` (각 dict: `{"row_number": int, "timestamp": str, "body": str, "sender": str}`), `gws_client.update_row_draft(spreadsheet_id: str, row_number: int, body: str, sender: str, cs_type: str, summary: str, draft: str, note: str, status: str) -> None`. Task 5가 `fetch_new_sms_rows`/`update_row_draft`를, Task 8이 `create_cs_response_sheet`를 그대로 호출한다.

- [ ] **Step 1: conftest.py 작성 (프로젝트 루트를 import 경로에 추가)**

```python
# 20-operations/cs-automation/tests/conftest.py
# 테스트가 상위 폴더의 gws_client 등을 import할 수 있게 경로 추가
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

- [ ] **Step 2: 실패 테스트 작성**

```python
# 20-operations/cs-automation/tests/test_gws_client.py
import json
import subprocess

import pytest

import gws_client


class FakeCompletedProcess:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_create_cs_response_sheet_creates_then_appends_header(monkeypatch):
    calls = []

    def fake_run(cmd, capture_output, text, encoding, timeout):
        calls.append(cmd)
        if "create" in cmd:
            return FakeCompletedProcess(0, stdout=json.dumps({"spreadsheetId": "new-sheet-1"}))
        return FakeCompletedProcess(0, stdout="{}")

    monkeypatch.setattr(subprocess, "run", fake_run)
    spreadsheet_id = gws_client.create_cs_response_sheet()

    assert spreadsheet_id == "new-sheet-1"
    assert len(calls) == 2
    create_json_index = calls[0].index("--json") + 1
    create_body = json.loads(calls[0][create_json_index])
    assert create_body["properties"]["title"] == "CS응대로그"
    assert create_body["sheets"][0]["properties"]["title"] == "로그"
    append_json_values_index = calls[1].index("--json-values") + 1
    header_rows = json.loads(calls[1][append_json_values_index])
    assert header_rows == [["작업일", "CS유형", "상황요약", "고객원문", "답변문구", "비고", "채널", "문의번호", "상태"]]


def test_fetch_new_sms_rows_filters_status_and_channel(monkeypatch):
    # A작업일 B유형 C요약 D원문 E초안 F비고 G채널 H문의번호(발신번호) I상태
    fake_values = {
        "values": [
            ["2026-09-05T10:00:00", "", "", "배송 언제 오나요", "", "", "문자", "01011112222", "신규"],
            ["2026-08-18", "배송지연", "요약", "원문", "초안", "", "문의게시판", "12345", "대기"],
            ["2026-09-05T10:05:00", "", "", "환불하고 싶어요", "", "", "문자", "01033334444", "신규"],
        ]
    }

    def fake_run(cmd, capture_output, text, encoding, timeout):
        assert cmd[0] == "node"
        assert "values" in cmd and "get" in cmd
        return FakeCompletedProcess(0, stdout=json.dumps(fake_values))

    monkeypatch.setattr(subprocess, "run", fake_run)
    rows = gws_client.fetch_new_sms_rows("sheet-123")

    assert rows == [
        {"row_number": 2, "timestamp": "2026-09-05T10:00:00", "body": "배송 언제 오나요", "sender": "01011112222"},
        {"row_number": 4, "timestamp": "2026-09-05T10:05:00", "body": "환불하고 싶어요", "sender": "01033334444"},
    ]


def test_fetch_new_sms_rows_raises_on_nonzero_exit(monkeypatch):
    def fake_run(cmd, capture_output, text, encoding, timeout):
        return FakeCompletedProcess(1, stdout="", stderr="인증 만료됨")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(gws_client.GwsError):
        gws_client.fetch_new_sms_rows("sheet-123")


def test_update_row_draft_builds_correct_range_and_values(monkeypatch):
    captured = {}

    def fake_run(cmd, capture_output, text, encoding, timeout):
        captured["cmd"] = cmd
        return FakeCompletedProcess(0, stdout="{}")

    monkeypatch.setattr(subprocess, "run", fake_run)
    gws_client.update_row_draft(
        "sheet-123", row_number=2, body="배송 언제 오나요", sender="01011112222",
        cs_type="배송지연", summary="배송 지연 문의", draft="안녕하세요...", note="",
        status="대기",
    )

    assert "update" in captured["cmd"]
    params_index = captured["cmd"].index("--params") + 1
    params = json.loads(captured["cmd"][params_index])
    assert params["range"] == "로그!B2:I2"
    assert params["valueInputOption"] == "RAW"
    json_index = captured["cmd"].index("--json") + 1
    body = json.loads(captured["cmd"][json_index])
    assert body["values"] == [["배송지연", "배송 지연 문의", "배송 언제 오나요", "안녕하세요...", "", "문자", "01011112222", "대기"]]
```

- [ ] **Step 3: 테스트 실행해서 실패 확인**

Run: `& 'C:\Users\workspace\.venv\Scripts\python.exe' -m pytest '20-operations\cs-automation\tests\test_gws_client.py' -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gws_client'`

- [ ] **Step 4: gws_client.py 구현**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gws CLI(@googleworkspace/cli) 래퍼 — "CS응대로그" 시트 조작용.
Python subprocess에서는 gws.cmd 셸 shim을 못 찾으므로 node로 run.js를 직접 호출한다.
"""
import json
import subprocess

GWS_RUN_JS = r"C:\Users\woori\AppData\Roaming\npm\node_modules\@googleworkspace\cli\run.js"
SHEET_TAB = "로그"
# 헤더: 작업일(A) CS유형(B) 상황요약(C) 고객원문(D) 답변문구(E) 비고(F) 채널(G) 문의번호(H) 상태(I)
SMS_CHANNEL_VALUE = "문자"
NEW_STATUS_VALUE = "신규"


class GwsError(Exception):
    """gws 명령 실행/파싱 실패."""


def _run_gws(args: list) -> dict:
    """node로 gws run.js를 직접 호출하고 JSON 결과를 dict로 반환."""
    cmd = ["node", GWS_RUN_JS] + args + ["--format", "json"]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", timeout=60
        )
    except subprocess.TimeoutExpired as e:
        raise GwsError(f"gws 명령 타임아웃: {' '.join(args)}") from e
    except OSError as e:
        raise GwsError(f"gws 명령 실행 실패(node/run.js 확인 필요): {e}") from e

    if result.returncode != 0:
        raise GwsError(f"gws 명령 실패(exit {result.returncode}): {result.stderr.strip()}")

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise GwsError(f"gws 응답 JSON 파싱 실패: {result.stdout[:200]}") from e


def create_cs_response_sheet() -> str:
    """'CS응대로그' 스프레드시트를 '로그' 탭 + 9열 헤더로 생성하고 spreadsheetId를 반환."""
    data = _run_gws([
        "sheets", "spreadsheets", "create",
        "--json", json.dumps({
            "properties": {"title": "CS응대로그"},
            "sheets": [{"properties": {"title": SHEET_TAB}}],
        }),
    ])
    spreadsheet_id = data["spreadsheetId"]
    header = ["작업일", "CS유형", "상황요약", "고객원문", "답변문구", "비고", "채널", "문의번호", "상태"]
    _run_gws([
        "sheets", "+append", "--spreadsheet", spreadsheet_id,
        "--json-values", json.dumps([header]),
    ])
    return spreadsheet_id


def fetch_new_sms_rows(spreadsheet_id: str) -> list:
    """상태='신규'이고 채널='문자'인 행만 조회한다. 반환은 시트 실제 행번호(1-base) 포함."""
    data = _run_gws([
        "sheets", "spreadsheets", "values", "get",
        "--params", json.dumps({
            "spreadsheetId": spreadsheet_id,
            "range": f"{SHEET_TAB}!A2:I",
        }),
    ])
    rows = data.get("values", [])

    result = []
    for offset, row in enumerate(rows):
        row_number = offset + 2  # 헤더가 1행이므로 데이터는 2행부터
        row = row + [""] * (9 - len(row))  # 짧은 행 패딩(빈 셀 생략 대응)
        channel, status = row[6], row[8]
        if channel == SMS_CHANNEL_VALUE and status == NEW_STATUS_VALUE:
            result.append({
                "row_number": row_number,
                "timestamp": row[0],
                "body": row[3],
                "sender": row[7],
            })
    return result


def update_row_draft(
    spreadsheet_id: str, row_number: int, body: str, sender: str,
    cs_type: str, summary: str, draft: str, note: str, status: str,
) -> None:
    """B~I열(8칸)을 한 번에 갱신한다. D(고객원문)·G(채널)·H(발신번호)는 원래 값을 그대로 다시 써서
    B~I가 하나의 연속 range가 되게 한다(비연속 range를 여러 번 부르는 것보다 단순함)."""
    values = [cs_type, summary, body, draft, note, SMS_CHANNEL_VALUE, sender, status]
    _run_gws([
        "sheets", "spreadsheets", "values", "update",
        "--params", json.dumps({
            "spreadsheetId": spreadsheet_id,
            "range": f"{SHEET_TAB}!B{row_number}:I{row_number}",
            "valueInputOption": "RAW",
        }),
        "--json", json.dumps({"values": [values]}),
    ])
```

- [ ] **Step 5: 테스트 실행해서 통과 확인**

Run: `& 'C:\Users\workspace\.venv\Scripts\python.exe' -m pytest '20-operations\cs-automation\tests\test_gws_client.py' -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add 20-operations/cs-automation/gws_client.py 20-operations/cs-automation/tests/
git commit -m "feat: CS 문자 자동화 gws CLI 래퍼(gws_client.py) 추가"
```

---

### Task 3: `classifier.py` — CS 유형분류 + 초안 생성

**Files:**
- Create: `20-operations/cs-automation/classifier.py`
- Test: `20-operations/cs-automation/tests/test_classifier.py`

**Interfaces:**
- Consumes: 없음 (Anthropic SDK만 사용)
- Produces: `classifier.generate_cs_draft(sender: str, body: str, api_key: str) -> dict` — 반환값 `{"status": "대기" | "확인필요", "cs_type": str, "summary": str, "draft": str, "note": str}`. Task 5가 이 시그니처를 그대로 호출한다.

- [ ] **Step 1: 실패 테스트 작성**

```python
# 20-operations/cs-automation/tests/test_classifier.py
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


def test_generate_cs_draft_returns_ready_draft(monkeypatch):
    fake_response = json.dumps({
        "status": "대기", "cs_type": "배송지연",
        "summary": "해외배송 지연 문의", "draft": "안녕하세요, 고객님...", "note": "",
    })
    monkeypatch.setattr(classifier.anthropic, "Anthropic", lambda api_key: FakeAnthropic(fake_response))

    result = classifier.generate_cs_draft("01011112222", "주문한지 2주 됐는데 아직도 안와요", "fake-key")

    assert result == {
        "status": "대기", "cs_type": "배송지연",
        "summary": "해외배송 지연 문의", "draft": "안녕하세요, 고객님...", "note": "",
    }


def test_generate_cs_draft_returns_needs_review_when_info_missing(monkeypatch):
    fake_response = json.dumps({
        "status": "확인필요", "cs_type": "기타",
        "summary": "환불 요청이나 주문번호 없음", "draft": "", "note": "주문번호 확인 필요",
    })
    monkeypatch.setattr(classifier.anthropic, "Anthropic", lambda api_key: FakeAnthropic(fake_response))

    result = classifier.generate_cs_draft("01033334444", "환불해주세요", "fake-key")

    assert result["status"] == "확인필요"
    assert result["draft"] == ""


def test_generate_cs_draft_defaults_to_needs_review_on_invalid_status(monkeypatch):
    fake_response = json.dumps({"status": "완료", "cs_type": "기타", "summary": "", "draft": "x", "note": ""})
    monkeypatch.setattr(classifier.anthropic, "Anthropic", lambda api_key: FakeAnthropic(fake_response))

    result = classifier.generate_cs_draft("010", "본문", "fake-key")

    assert result["status"] == "확인필요"


def test_generate_cs_draft_defaults_to_needs_review_on_api_error(monkeypatch):
    class BrokenAnthropic:
        def __init__(self, api_key):
            raise RuntimeError("네트워크 오류")

    monkeypatch.setattr(classifier.anthropic, "Anthropic", BrokenAnthropic)

    result = classifier.generate_cs_draft("010", "본문", "fake-key")

    assert result["status"] == "확인필요"
    assert result["draft"] == ""


def test_generate_cs_draft_strips_markdown_code_fence(monkeypatch):
    fake_response = '```json\n{"status": "대기", "cs_type": "단순문의", "summary": "요약", "draft": "답변", "note": ""}\n```'
    monkeypatch.setattr(classifier.anthropic, "Anthropic", lambda api_key: FakeAnthropic(fake_response))

    result = classifier.generate_cs_draft("010", "사이즈 문의", "fake-key")

    assert result == {"status": "대기", "cs_type": "단순문의", "summary": "요약", "draft": "답변", "note": ""}
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `& 'C:\Users\workspace\.venv\Scripts\python.exe' -m pytest '20-operations\cs-automation\tests\test_classifier.py' -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'classifier'`

- [ ] **Step 3: classifier.py 구현**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude API로 CS 문자 1건을 유형분류 + 정보부족판단 + 답변초안 작성까지 처리한다.
`.claude/skills/cs-response/SKILL.md`의 수행 순서 1~3을 시스템 프롬프트로 이식한 것.
확신이 없거나 호출·파싱이 실패하면 항상 status="확인필요"(초안 없이 사람이 직접 판단)로 처리한다.
"""
import json

import anthropic

MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = """당신은 중국 구매대행 셀러 용팀장님의 CS 문자 응대를 돕는 어시스턴트입니다.
CS 전용 휴대폰으로 온 고객 문자 1건(발신번호, 원문)을 보고 아래 순서로 처리하세요.

1. **CS 유형 분류** (하나만 선택): 배송지연 · 통관/관부가세 · 오배송/상품상이 · 파손/불량 ·
   환불/취소 · 교환 · 품절/재고 · 단순문의(사용법/스펙/사이즈) · 기타

2. **정보 부족 판단**: 답변에 꼭 필요한 정보(주문번호, 현재 진행상황, 배송사/송장번호, 예상 소요일,
   환불 사유 등)가 문자 원문에 없으면 status를 "확인필요"로 하고 draft는 빈 문자열로 둡니다.
   note에 "어떤 정보가 부족한지" 한 문장으로 적으세요. 정보가 충분하면 3번으로 진행하고
   status는 "대기"로 합니다.

3. **답변 문구 작성** (status="대기"인 경우만):
   - 정중한 존댓말(CS 응대 톤).
   - 문장 구조: 결론(처리방향) → 이유/근거 → 다음 행동(고객이 할 일 또는 우리가 할 일).
   - 근거 없는 확답·과장 금지 — "무조건", "바로 됩니다" 대신 조건과 변수(통관 심사, 해외 배송사
     상황 등)를 명시.
   - 구매대행 특성상 해외 배송 리드타임·통관 변수가 있다는 점을 필요할 때 자연스럽게 설명.

반드시 아래 JSON 형식으로만 답하세요. 다른 설명은 절대 붙이지 마세요:
{"status": "대기 또는 확인필요", "cs_type": "위 유형 중 하나", "summary": "상황 한 문장 요약", "draft": "답변 문구 (확인필요면 빈 문자열)", "note": "확인필요 사유 또는 특이사항 (없으면 빈 문자열)"}"""

VALID_STATUSES = ("대기", "확인필요")


def _extract_json(raw_text: str) -> dict:
    """마크다운 코드펜스가 섞여 와도 JSON을 추출한다."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        first_line, _, rest = text.partition("\n")
        text = rest if first_line.strip().lower() in ("json", "") else text
    return json.loads(text)


def generate_cs_draft(sender: str, body: str, api_key: str) -> dict:
    """문자 1건을 분류/판단/초안작성. 실패 시 안전하게 확인필요를 반환."""
    try:
        client = anthropic.Anthropic(api_key=api_key)
        user_content = f"발신번호: {sender}\n문자 원문:\n{body[:1000]}"
        response = client.messages.create(
            model=MODEL,
            max_tokens=600,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        raw_text = response.content[0].text
        result = _extract_json(raw_text)
        status = result.get("status")
        if status not in VALID_STATUSES:
            status = "확인필요"
        return {
            "status": status,
            "cs_type": result.get("cs_type", ""),
            "summary": result.get("summary", ""),
            "draft": result.get("draft", "") if status == "대기" else "",
            "note": result.get("note", ""),
        }
    except Exception as e:
        # 판단 실패 시 안전 우선 — 무조건 확인필요, 초안 없음
        return {"status": "확인필요", "cs_type": "", "summary": "", "draft": "", "note": f"분류 실패(안전우선): {e}"}
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `& 'C:\Users\workspace\.venv\Scripts\python.exe' -m pytest '20-operations\cs-automation\tests\test_classifier.py' -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add 20-operations/cs-automation/classifier.py 20-operations/cs-automation/tests/test_classifier.py
git commit -m "feat: CS 문자 분류+초안생성기(classifier.py) 추가"
```

---

### Task 4: `state.py` — 실패 감지용 상태 기록

**Files:**
- Create: `20-operations/cs-automation/state.py`
- Test: `20-operations/cs-automation/tests/test_state.py`

**Interfaces:**
- Consumes: 없음
- Produces: `state.record_success(timestamp: str) -> None`, `state.read_last_success() -> str | None`. Task 5가 실행 종료 시 `record_success`를 호출한다.

- [ ] **Step 1: 실패 테스트 작성**

```python
# 20-operations/cs-automation/tests/test_state.py
import state


def test_record_and_read_last_success(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "STATE_DIR", tmp_path / ".state")
    monkeypatch.setattr(state, "LAST_SUCCESS_FILE", tmp_path / ".state" / "last_success.json")

    state.record_success("2026-09-05T09:00:00+00:00")

    assert state.read_last_success() == "2026-09-05T09:00:00+00:00"


def test_read_last_success_returns_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "LAST_SUCCESS_FILE", tmp_path / "nope.json")
    assert state.read_last_success() is None
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `& 'C:\Users\workspace\.venv\Scripts\python.exe' -m pytest '20-operations\cs-automation\tests\test_state.py' -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'state'`

- [ ] **Step 3: state.py 구현**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
마지막 성공 실행시각을 로컬 파일에 기록한다.
gws 토큰이 조용히 만료되는 등으로 스크립트가 계속 실패해도 감지할 수 있게 하기 위함.
"""
import json
from pathlib import Path

STATE_DIR = Path(__file__).resolve().parent / ".state"
LAST_SUCCESS_FILE = STATE_DIR / "last_success.json"


def record_success(timestamp: str) -> None:
    """마지막 성공 실행시각(ISO 8601 문자열)을 기록한다."""
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        LAST_SUCCESS_FILE.write_text(json.dumps({"last_success": timestamp}), encoding="utf-8")
    except OSError:
        pass  # 상태 기록 실패는 본 처리 결과에 영향을 주지 않음


def read_last_success() -> str:
    """마지막 성공 실행시각을 반환한다. 기록이 없으면 None."""
    if not LAST_SUCCESS_FILE.exists():
        return None
    try:
        data = json.loads(LAST_SUCCESS_FILE.read_text(encoding="utf-8"))
        return data.get("last_success")
    except (json.JSONDecodeError, OSError):
        return None
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `& 'C:\Users\workspace\.venv\Scripts\python.exe' -m pytest '20-operations\cs-automation\tests\test_state.py' -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add 20-operations/cs-automation/state.py 20-operations/cs-automation/tests/test_state.py
git commit -m "feat: CS 문자 자동화 실패감지용 상태 기록(state.py) 추가"
```

---

### Task 5: `sms_draft.py` — 메인 오케스트레이터 + CLI

**Files:**
- Create: `20-operations/cs-automation/sms_draft.py`
- Test: `20-operations/cs-automation/tests/test_sms_draft.py`

**Interfaces:**
- Consumes: `gws_client.fetch_new_sms_rows/update_row_draft`(Task 2), `classifier.generate_cs_draft`(Task 3), `state.record_success`(Task 4)
- Produces: `sms_draft.process_new_sms(api_key: str, spreadsheet_id: str, dry_run: bool) -> dict` — 반환값 `{"drafted": [...], "needs_review": [...], "errors": [...]}`. CLI 진입점 `main()`.

- [ ] **Step 1: 실패 테스트 작성**

```python
# 20-operations/cs-automation/tests/test_sms_draft.py
import sms_draft
import gws_client
import classifier
import state


def _patch_common(monkeypatch, rows, draft_result_map):
    monkeypatch.setattr(gws_client, "fetch_new_sms_rows", lambda spreadsheet_id: rows)
    monkeypatch.setattr(
        classifier, "generate_cs_draft",
        lambda sender, body, api_key: draft_result_map[body]
    )


def test_process_new_sms_updates_ready_and_needs_review_rows(monkeypatch):
    rows = [
        {"row_number": 2, "timestamp": "t1", "body": "배송 언제 오나요", "sender": "010111"},
        {"row_number": 4, "timestamp": "t2", "body": "환불해주세요", "sender": "010222"},
    ]
    draft_result_map = {
        "배송 언제 오나요": {"status": "대기", "cs_type": "배송지연", "summary": "배송지연 문의", "draft": "안녕하세요...", "note": ""},
        "환불해주세요": {"status": "확인필요", "cs_type": "환불/취소", "summary": "환불요청, 주문번호 없음", "draft": "", "note": "주문번호 필요"},
    }
    _patch_common(monkeypatch, rows, draft_result_map)

    updated_calls = []
    monkeypatch.setattr(
        gws_client, "update_row_draft",
        lambda spreadsheet_id, row_number, body, sender, cs_type, summary, draft, note, status:
            updated_calls.append((row_number, status))
    )
    monkeypatch.setattr(state, "record_success", lambda ts: None)

    summary = sms_draft.process_new_sms(api_key="fake-key", spreadsheet_id="sheet-123", dry_run=False)

    assert updated_calls == [(2, "대기"), (4, "확인필요")]
    assert len(summary["drafted"]) == 1
    assert len(summary["needs_review"]) == 1
    assert summary["errors"] == []


def test_process_new_sms_dry_run_does_not_call_update(monkeypatch):
    rows = [{"row_number": 2, "timestamp": "t1", "body": "배송 언제 오나요", "sender": "010111"}]
    draft_result_map = {
        "배송 언제 오나요": {"status": "대기", "cs_type": "배송지연", "summary": "요약", "draft": "안녕하세요...", "note": ""},
    }
    _patch_common(monkeypatch, rows, draft_result_map)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("dry-run에서는 호출되면 안 됨")

    monkeypatch.setattr(gws_client, "update_row_draft", fail_if_called)

    summary = sms_draft.process_new_sms(api_key="fake-key", spreadsheet_id="sheet-123", dry_run=True)

    assert len(summary["drafted"]) == 1


def test_process_new_sms_records_error_and_continues(monkeypatch):
    rows = [
        {"row_number": 2, "timestamp": "t1", "body": "정상건", "sender": "010111"},
        {"row_number": 4, "timestamp": "t2", "body": "에러건", "sender": "010222"},
    ]

    def fake_generate(sender, body, api_key):
        if body == "에러건":
            raise RuntimeError("API 타임아웃")
        return {"status": "대기", "cs_type": "기타", "summary": "요약", "draft": "답변", "note": ""}

    monkeypatch.setattr(gws_client, "fetch_new_sms_rows", lambda spreadsheet_id: rows)
    monkeypatch.setattr(classifier, "generate_cs_draft", fake_generate)
    monkeypatch.setattr(gws_client, "update_row_draft", lambda **kwargs: None)
    monkeypatch.setattr(state, "record_success", lambda ts: None)

    summary = sms_draft.process_new_sms(api_key="fake-key", spreadsheet_id="sheet-123", dry_run=False)

    assert len(summary["errors"]) == 1
    assert len(summary["drafted"]) == 1
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `& 'C:\Users\workspace\.venv\Scripts\python.exe' -m pytest '20-operations\cs-automation\tests\test_sms_draft.py' -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sms_draft'`

- [ ] **Step 3: sms_draft.py 구현**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CS 문자 자동 초안 생성 — "CS응대로그" 시트의 상태="신규"(문자 채널) 행을 훑어
유형분류+정보부족판단+답변초안까지 자동 반영한다.
Windows 작업 스케줄러로 1시간마다 무인 실행됨. 발송은 절대 하지 않음 — 항상 사람이 직접.

사용법:
  python sms_draft.py            # 실제 처리
  python sms_draft.py --dry-run  # 시트 반영 없이 분류/초안 결과만 미리보기
"""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import gws_client
import classifier
import state


def load_env(env_path: Path) -> dict:
    """.env 파일을 파싱해 dict로 반환한다."""
    data = {}
    try:
        if not env_path.exists():
            return data
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            data[key.strip()] = val.strip().strip('"').strip("'")
    except OSError as e:
        print(f"[경고] .env 읽기 실패: {e}", file=sys.stderr)
    return data


def find_env() -> Path:
    """워크스페이스 루트 .env 경로(스크립트 기준 2단계 위)."""
    return Path(__file__).resolve().parents[2] / ".env"


def process_new_sms(api_key: str, spreadsheet_id: str, dry_run: bool) -> dict:
    """상태='신규' 문자 행을 훑어 분류·초안작성·시트반영한다. 결과 요약 dict를 반환한다."""
    summary = {"drafted": [], "needs_review": [], "errors": []}

    try:
        rows = gws_client.fetch_new_sms_rows(spreadsheet_id)
    except gws_client.GwsError as e:
        summary["errors"].append(f"시트 조회 실패: {e}")
        return summary

    for row in rows:
        row_number = row["row_number"]
        try:
            result = classifier.generate_cs_draft(row["sender"], row["body"], api_key)
            status = result["status"]

            if not dry_run:
                gws_client.update_row_draft(
                    spreadsheet_id=spreadsheet_id, row_number=row_number,
                    body=row["body"], sender=row["sender"],
                    cs_type=result["cs_type"], summary=result["summary"],
                    draft=result["draft"], note=result["note"], status=status,
                )

            bucket = "drafted" if status == "대기" else "needs_review"
            summary[bucket].append({"row_number": row_number, "sender": row["sender"]})
        except Exception as e:
            summary["errors"].append(f"{row_number}행 처리 실패: {e}")

    if not dry_run and not summary["errors"]:
        state.record_success(datetime.now(timezone.utc).isoformat())

    return summary


def main():
    parser = argparse.ArgumentParser(description="CS 문자 자동 초안 생성 — CS응대로그 시트 갱신")
    parser.add_argument("--dry-run", action="store_true", help="실제 반영 없이 분류/초안 결과만 미리보기")
    args = parser.parse_args()

    env = load_env(find_env())
    api_key = env.get("ANTHROPIC_API_KEY")
    spreadsheet_id = env.get("CS_RESPONSE_SHEET_ID")

    if not api_key:
        print("[오류] ANTHROPIC_API_KEY가 .env에 없습니다.", file=sys.stderr)
        sys.exit(1)
    if not spreadsheet_id:
        print("[오류] CS_RESPONSE_SHEET_ID가 .env에 없습니다.", file=sys.stderr)
        sys.exit(1)

    summary = process_new_sms(api_key, spreadsheet_id, dry_run=args.dry_run)

    print(f"[결과] 초안완료 {len(summary['drafted'])}건 / 확인필요 {len(summary['needs_review'])}건 / 오류 {len(summary['errors'])}건")
    for err in summary["errors"]:
        print(f"  [오류] {err}", file=sys.stderr)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `& 'C:\Users\workspace\.venv\Scripts\python.exe' -m pytest '20-operations\cs-automation\tests\test_sms_draft.py' -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 전체 테스트 스위트 통과 확인**

Run: `& 'C:\Users\workspace\.venv\Scripts\python.exe' -m pytest '20-operations\cs-automation\tests' -v`
Expected: PASS (14 passed — Task 2~5 테스트 합계)

- [ ] **Step 6: Commit**

```bash
git add 20-operations/cs-automation/sms_draft.py 20-operations/cs-automation/tests/test_sms_draft.py
git commit -m "feat: CS 문자 자동화 메인 오케스트레이터(sms_draft.py) 추가"
```

---

### Task 6: Google Apps Script 웹훅 소스 + 배포 가이드

**Files:**
- Create: `20-operations/cs-automation/apps_script/sms_webhook.gs`
- Create: `20-operations/cs-automation/실행-가이드.md`

**Interfaces:**
- Consumes: Task 8에서 생성될 "CS응대로그" 시트, `.env`의 `CS_SMS_WEBHOOK_TOKEN`
- Produces: 시트에 새 문자 행을 append하는 웹앱 URL(배포 후 Task 7이 MacroDroid 설정에 사용)

이 태스크는 순수 코드가 아니라 Google Apps Script 편집기(브라우저)에 직접 붙여넣는 소스와,
용팀장님이 따라할 배포 절차 문서를 만드는 것이다. 자동 테스트는 없다 — Step 3의 curl 확인이
검증 역할을 한다.

- [ ] **Step 1: sms_webhook.gs 작성**

```javascript
// 20-operations/cs-automation/apps_script/sms_webhook.gs
// "CS응대로그" 시트에 바인딩된 Apps Script 프로젝트에 그대로 붙여넣는다.
// MacroDroid가 SMS 수신 시 이 웹앱 URL로 POST하면, 토큰을 검증한 뒤 시트에 새 행을 추가한다.

function doPost(e) {
  var props = PropertiesService.getScriptProperties();
  var expectedToken = props.getProperty('CS_SMS_WEBHOOK_TOKEN');

  var payload;
  try {
    payload = JSON.parse(e.postData.contents);
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({ error: 'invalid json' }))
      .setMimeType(ContentService.MimeType.JSON);
  }

  if (!expectedToken || payload.token !== expectedToken) {
    return ContentService.createTextOutput(JSON.stringify({ error: 'unauthorized' }))
      .setMimeType(ContentService.MimeType.JSON);
  }

  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('로그');
  // 작업일 / CS유형 / 상황요약 / 고객원문 / 답변문구 / 비고 / 채널 / 문의번호(발신번호) / 상태
  sheet.appendRow([
    payload.timestamp || new Date().toISOString(),
    '',
    '',
    payload.body || '',
    '',
    '',
    '문자',
    payload.from || '',
    '신규',
  ]);

  return ContentService.createTextOutput(JSON.stringify({ ok: true }))
    .setMimeType(ContentService.MimeType.JSON);
}
```

- [ ] **Step 2: 실행-가이드.md 작성 (배포 절차)**

```markdown
# CS 문자 자동화 — 실행 가이드

## ① Apps Script 웹훅 배포 (최초 1회, 용팀장님 직접)

1. "CS응대로그" 구글시트를 연다 (Task 8에서 생성됨).
2. 메뉴 `확장 프로그램 > Apps Script` 클릭.
3. 기본 생성된 `Code.gs` 내용을 지우고 `20-operations/cs-automation/apps_script/sms_webhook.gs`
   내용을 그대로 붙여넣는다.
4. 왼쪽 `프로젝트 설정`(톱니바퀴) > `스크립트 속성` > `속성 추가`:
   - 속성: `CS_SMS_WEBHOOK_TOKEN`
   - 값: 임의의 긴 랜덤 문자열(예: 32자 이상). 이 값을 워크스페이스 `.env`의
     `CS_SMS_WEBHOOK_TOKEN`에도 똑같이 저장해둔다.
5. 우측 상단 `배포 > 새 배포` > 유형 선택(톱니바퀴) `웹 앱`:
   - 실행 계정: 나
   - 액세스 권한: 모든 사용자
6. `배포` 클릭 후 나오는 **웹 앱 URL**을 복사해둔다 (다음 단계 MacroDroid 설정에서 사용).

## ② MacroDroid 매크로 설정 (최초 1회, CS 전용 폰에서 직접)

1. Play 스토어에서 MacroDroid 설치(무료).
2. `매크로 추가` > 트리거: `메시지 > SMS 수신(SMS Received)`.
3. 액션: `연결 > HTTP 요청(HTTP Request)`.
   - Method: `POST`
   - URL: ① 에서 복사한 웹앱 URL
   - Content Type: `application/json`
   - Body(JSON): 아래 형태로 입력하되, `[발신번호]`/`[문자 내용]`/`[현재 날짜/시간]` 자리에는
     MacroDroid 트리거 삽입 버튼으로 넣는 매직 텍스트 변수를 사용한다(트리거별 정확한 변수명은
     매크로 편집 화면에서 "매직 텍스트 삽입" 버튼을 눌러 SMS 발신번호/본문/시각에 해당하는 항목을
     직접 골라 넣을 것 — 앱 업데이트로 변수명이 달라질 수 있어 여기 고정 표기하지 않음):
     ```json
     {"token": "여기에_CS_SMS_WEBHOOK_TOKEN_값", "from": "[발신번호 변수]", "body": "[문자 내용 변수]", "timestamp": "[ISO 시각 변수]"}
     ```
4. 저장 후 본인 폰으로 테스트 문자를 보내 시트에 새 행(상태="신규")이 생기는지 확인.

## ③ 운영 메모
- 시트에서 상태="대기"인 행이 초안 완료된 것. `답변문구` 열을 확인·수정 후 CS 직원이 폰에서
  직접 문자로 발송한다.
- 상태="확인필요" 행은 정보 부족 — `비고` 열의 사유를 보고 사람이 직접 판단해서 답한다.
- 발송완료 표시는 선택사항이며 자동 추적하지 않는다.
```

- [ ] **Step 3: 웹훅 동작 확인 (Task 8 완료 후 실행 — curl)**

Run (`<웹앱URL>`과 `<토큰>`을 실제 값으로 치환):
```bash
curl -X POST "<웹앱URL>" -H "Content-Type: application/json" \
  -d '{"token":"<토큰>","from":"01099998888","body":"테스트 문자입니다","timestamp":"2026-09-05T12:00:00+09:00"}'
```
Expected: `{"ok":true}` 응답, 시트에 상태="신규"인 새 행 확인.

- [ ] **Step 4: Commit**

```bash
git add 20-operations/cs-automation/apps_script/sms_webhook.gs 20-operations/cs-automation/실행-가이드.md
git commit -m "docs: CS 문자 자동화 Apps Script 웹훅 소스 + 배포 가이드 추가"
```

---

### Task 7: Windows 작업 스케줄러 등록

**Files:**
- Create: `20-operations/cs-automation/setup_scheduler.ps1`

**Interfaces:**
- Consumes: `20-operations/cs-automation/sms_draft.py`(Task 5), `.venv`의 python.exe
- Produces: Windows 작업 스케줄러에 등록된 1시간 간격 태스크

- [ ] **Step 1: setup_scheduler.ps1 작성**

```powershell
# CS 문자 자동화 스케줄러 등록 — 1시간마다 실행
# 1회만 실행하면 됨. 재실행 시 -Force로 기존 등록을 덮어씀.

$pythonExe = "C:\Users\workspace\.venv\Scripts\python.exe"
$scriptPath = "C:\Users\workspace\20-operations\cs-automation\sms_draft.py"
$workDir = Split-Path $scriptPath
$taskName = "CS문자자동화_매시"

$action = New-ScheduledTaskAction -Execute $pythonExe -Argument "`"$scriptPath`"" -WorkingDirectory $workDir
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration ([TimeSpan]::MaxValue)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Description "CS 전용 폰 문자 CS응대로그 시트에서 신규 문자 초안 자동 생성(1시간마다)" -Force

Write-Output "등록됨: $taskName (1시간마다)"
Write-Output "확인: schtasks /query /fo LIST | findstr CS문자자동화"
```

- [ ] **Step 2: Commit**

```bash
git add 20-operations/cs-automation/setup_scheduler.ps1
git commit -m "feat: CS 문자 자동화 Windows 작업 스케줄러 등록 스크립트 추가"
```

---

### Task 8: 구글시트 생성 + .env 반영 (실행 — 코드 아님, 병합 후 컨트롤러가 직접 실행)

**Files:**
- Modify: `.env` (워크스페이스 루트, git 제외 대상 — `CS_RESPONSE_SHEET_ID`, `CS_SMS_WEBHOOK_TOKEN` 채움)
- Modify: `.claude/skills/cs-response/SKILL.md` (저장 위치 섹션의 "미생성"을 실제 ID로 채움 — 문의게시판 채널과 시트를 공유하므로)

**Interfaces:**
- Consumes: `gws_client.create_cs_response_sheet`(Task 2)
- Produces: `.env`의 `CS_RESPONSE_SHEET_ID` — Task 5의 `sms_draft.py`와 향후 문의게시판 자동화가 이 값을 읽는다.

> Task 1~7(순수 코드+문서)은 격리된 worktree에서 진행 가능하지만, 이 태스크는 실제 gws 인증
> 계정으로 프로덕션 구글시트를 생성하는 것이라 **main 병합 후 컨트롤러가 직접 실행**한다
> (이메일 자동화 계획의 Task 6/7과 동일한 이유).

- [ ] **Step 1: gws 인증 상태 확인**

Run: `node "C:\Users\woori\AppData\Roaming\npm\node_modules\@googleworkspace\cli\run.js" sheets spreadsheets values get --params '{"spreadsheetId":"1fW1QiEp79WarGSxFhT2il0o-nrVk-5jmnurnoPw7zTo","range":"A1:A1"}' --format json`
Expected: 정상 JSON 응답. `invalid_grant`/`Token has been expired` 에러가 나오면 `gws auth login`으로
재인증 먼저 진행(2026-09-05 실측 시 이 토큰이 만료된 상태였음 — gws-setup 메모리 참고).

- [ ] **Step 2: CS응대로그 시트 생성**

`20-operations/cs-automation` 폴더에서 실행:
```bash
& 'C:\Users\workspace\.venv\Scripts\python.exe' -c "import gws_client; sid = gws_client.create_cs_response_sheet(); print(sid)"
```
Expected: 스프레드시트 ID 문자열 출력.

- [ ] **Step 3: 웹훅 토큰 생성 + .env 반영**

임의의 32자 이상 랜덤 문자열을 생성해(예: `python -c "import secrets; print(secrets.token_urlsafe(32))"`)
워크스페이스 루트 `.env`에 아래 두 줄을 추가:
```text
CS_RESPONSE_SHEET_ID=<Step 2에서 나온 ID>
CS_SMS_WEBHOOK_TOKEN=<생성한 랜덤 문자열>
```

- [ ] **Step 4: cs-response 스킬 문서 갱신**

`.claude/skills/cs-response/SKILL.md`의 "저장 위치" 섹션(`spreadsheetId: _(미생성...)`)을
Step 2에서 생성된 실제 ID/URL로 채운다.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/cs-response/SKILL.md
git commit -m "docs: CS응대로그 시트 생성 완료, cs-response 스킬에 실제 spreadsheetId 반영"
```
(`.env`는 gitignore 대상이라 커밋하지 않는다.)

---

### Task 9: Apps Script 배포 + MacroDroid 설정 (실행 — 용팀장님 직접, 코드 아님)

**Files:**
- 없음 (Google Apps Script 편집기와 안드로이드 폰에서 직접 진행)

**Interfaces:**
- Consumes: Task 6의 `sms_webhook.gs`, `실행-가이드.md`, Task 8의 `CS_RESPONSE_SHEET_ID`/`CS_SMS_WEBHOOK_TOKEN`
- Produces: 실제 동작하는 웹앱 URL, CS 전용 폰의 MacroDroid 매크로

- [ ] **Step 1**: `20-operations/cs-automation/실행-가이드.md`의 "① Apps Script 웹훅 배포" 절차대로
  진행 (용팀장님 직접).

- [ ] **Step 2**: 같은 문서의 "② MacroDroid 매크로 설정" 절차대로 CS 전용 폰에 설치·설정
  (용팀장님 직접).

- [ ] **Step 3**: Task 6 Step 3의 curl 명령으로 웹훅이 실제로 시트에 행을 추가하는지 확인.

- [ ] **Step 4**: CS 전용 폰으로 실제 테스트 문자 1건을 보내 MacroDroid → 웹훅 → 시트까지
  end-to-end로 확인.

---

### Task 10: 작업 스케줄러 등록 + 전체 End-to-End 검증 (실행 — 컨트롤러, 병합 후)

**Files:**
- 없음 (등록/실행만)

**Interfaces:**
- Consumes: Task 7의 `setup_scheduler.ps1`, Task 8의 `.env` 값

- [ ] **Step 1: 등록 실행**

Run: `powershell -ExecutionPolicy Bypass -File '20-operations\cs-automation\setup_scheduler.ps1'`
Expected: `등록됨: CS문자자동화_매시 (1시간마다)` 출력.

- [ ] **Step 2: 등록 확인**

Run: `schtasks /query /fo LIST | findstr CS문자자동화`
Expected: `CS문자자동화_매시` 태스크가 출력됨.

- [ ] **Step 3: dry-run으로 먼저 검증**

Run: `& 'C:\Users\workspace\.venv\Scripts\python.exe' 20-operations\cs-automation\sms_draft.py --dry-run`
Expected: Task 9에서 넣은 테스트 문자에 대해 `[결과] 초안완료 N건 / 확인필요 M건 / 오류 0건` 출력.

- [ ] **Step 4: 실제 반영 확인**

Run: `& 'C:\Users\workspace\.venv\Scripts\python.exe' 20-operations\cs-automation\sms_draft.py`
Expected: 시트의 해당 행이 상태="대기" 또는 "확인필요"로 바뀌고 `답변문구`/`상황요약` 열이 채워짐.

- [ ] **Step 5: 수동 1회 트리거로 스케줄러 자체도 확인**

Run: `schtasks /run /tn CS문자자동화_매시`
Expected: 잠시 후 시트에 변화 확인(새 문자가 있을 때) 또는 콘솔 로그상 정상 종료.

## 구현 후 운영 메모 (코드 아님)

- **며칠은 결과를 지켜볼 것**: 초안 품질이 안정적인지 CS 직원이 확인하며 며칠 운영해보고,
  분류가 자주 틀리면 `classifier.py`의 `SYSTEM_PROMPT`를 조정한다.
- **MacroDroid 매직 텍스트 변수명은 실행-가이드에 고정 표기하지 않았음** — 앱 편집 화면에서
  직접 확인해서 넣어야 한다(Task 6 Step 2 참고).
- **가장 큰 운영 리스크는 gws 인증 만료**다. `state.py`가 마지막 성공 실행시각을 파일로 남기는
  것까지만 이 계획에 포함되며, 이를 daily-note/daily-review에서 자동 경고하는 연동은 이메일
  자동화와 마찬가지로 범위 밖 — 필요해지면 `state.read_last_success()`를 읽는 후속 작업으로 진행.
