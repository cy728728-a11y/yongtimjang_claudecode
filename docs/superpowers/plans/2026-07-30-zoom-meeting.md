# Zoom 미팅 생성 스킬 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** "8월5일 2시에 2시간짜리 줌미팅 잡아줘" 같은 자연어 요청을 받아 실제 Zoom Server-to-Server OAuth API로 미팅을 생성하고 join 링크를 대화창에 반환하는 스킬을 만든다.

**Architecture:** Claude(스킬 오케스트레이션)가 자연어를 파싱해 CLI 인자를 만들고, `zoom_meeting.py`(순수 함수 4개 + CLI 진입점)가 OAuth 토큰 발급 → 미팅 생성 API 호출을 담당한다. 결과는 stdout에 JSON 한 줄로 나오고, Claude가 이를 파싱해 사용자에게 보여준다.

**Tech Stack:** Python 3 표준 라이브러리만 사용 (`urllib.request`, `json`, `argparse`, `pathlib`) — `10-projects/이메일-자동화/send_email.py`와 동일한 무의존성 원칙. 테스트는 `unittest` + `unittest.mock` (표준 라이브러리, pytest 설치 불필요 — 이 워크스페이스에 pytest 미설치 확인됨).

## Global Constraints

- Python 표준 라이브러리만 사용, 별도 pip 설치 불필요 (send-email 스킬과 동일 원칙)
- 자격증명은 워크스페이스 루트 `.env`에서 읽음 (git 제외 확인됨: `.gitignore:25`) — `find_env()`/`load_env()` 패턴을 `send_email.py`에서 그대로 재사용
- 필수 자격증명 4종: `ZOOM_ACCOUNT_ID`, `ZOOM_CLIENT_ID`, `ZOOM_CLIENT_SECRET`, `ZOOM_USER_EMAIL` (이미 `.env`에 설정 완료됨)
- Server-to-Server OAuth는 `me` 축약을 지원하지 않음 → 미팅 생성 API 경로에 `ZOOM_USER_EMAIL`을 명시적으로 사용
- 미팅 생성 시: `type: 2`(예약), `timezone: Asia/Seoul`, `settings.waiting_room: false`
- 제목은 요청에 이미 포함돼 있어도 **항상 재확인 질문** (절대 임의 생성하거나 확인 없이 그대로 쓰지 않음)
- `start_url`은 호스트 전용이므로 대화창에 노출하지 않음 — 조기 오픈 리마인더 등록에만 사용
- 조기 오픈은 API 설정이 아니라 (시작시간-30분) 시각에 "줌 오픈" todo 항목을 `40-personal/46-todos/active-todos.md`에 직접 추가하는 방식으로 구현 (todo 스킬과 동일한 포맷 사용)
- `duration`은 Zoom이 강제 종료하지 않는 메타데이터 — 코드에서 별도 타임아웃 처리 불필요

---

## File Structure

- `10-projects/줌미팅-자동화/zoom_meeting.py` — CLI 스크립트 (env 로더, OAuth 토큰 발급, 미팅 생성, argparse 진입점)
- `10-projects/줌미팅-자동화/test_zoom_meeting.py` — unittest 테스트
- `10-projects/줌미팅-자동화/.env.example` — 자격증명 템플릿 (send-email과 동일 패턴)
- `.claude/skills/zoom-meeting/SKILL.md` — 스킬 정의 (자연어 파싱, 누락 항목 질문, 스크립트 호출, 결과 표시, 리마인더 등록 오케스트레이션)

---

### Task 1: `.env` 로더 (find_env / load_env / load_credentials)

**Files:**
- Create: `10-projects/줌미팅-자동화/zoom_meeting.py`
- Create: `10-projects/줌미팅-자동화/test_zoom_meeting.py`
- Create: `10-projects/줌미팅-자동화/.env.example`

**Interfaces:**
- Produces: `find_env() -> Path`, `load_env(env_path: Path) -> dict`, `load_credentials(env: dict) -> dict` (raises `ValueError`), 모듈 상수 `REQUIRED_KEYS = ["ZOOM_ACCOUNT_ID", "ZOOM_CLIENT_ID", "ZOOM_CLIENT_SECRET", "ZOOM_USER_EMAIL"]`

- [ ] **Step 1: Write the failing tests**

`10-projects/줌미팅-자동화/test_zoom_meeting.py`:

```python
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zoom_meeting


class TestLoadEnv(unittest.TestCase):
    def test_load_env_parses_key_value_and_ignores_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text(
                "# 주석\n"
                "ZOOM_ACCOUNT_ID=acc123\n"
                'ZOOM_CLIENT_ID="cid123"\n'
                "\n"
                "ZOOM_CLIENT_SECRET=secret123\n",
                encoding="utf-8",
            )
            result = zoom_meeting.load_env(env_path)
        self.assertEqual(result["ZOOM_ACCOUNT_ID"], "acc123")
        self.assertEqual(result["ZOOM_CLIENT_ID"], "cid123")
        self.assertEqual(result["ZOOM_CLIENT_SECRET"], "secret123")

    def test_load_env_missing_file_returns_empty_dict(self):
        result = zoom_meeting.load_env(Path("존재하지않는경로") / ".env")
        self.assertEqual(result, {})


class TestLoadCredentials(unittest.TestCase):
    def test_load_credentials_success(self):
        env = {
            "ZOOM_ACCOUNT_ID": "acc123",
            "ZOOM_CLIENT_ID": "cid123",
            "ZOOM_CLIENT_SECRET": "secret123",
            "ZOOM_USER_EMAIL": "user@example.com",
        }
        creds = zoom_meeting.load_credentials(env)
        self.assertEqual(creds["ZOOM_USER_EMAIL"], "user@example.com")

    def test_load_credentials_missing_raises_with_key_names(self):
        env = {"ZOOM_ACCOUNT_ID": "acc123"}
        with self.assertRaises(ValueError) as ctx:
            zoom_meeting.load_credentials(env)
        self.assertIn("ZOOM_CLIENT_ID", str(ctx.exception))
        self.assertIn("ZOOM_CLIENT_SECRET", str(ctx.exception))
        self.assertIn("ZOOM_USER_EMAIL", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m unittest 10-projects.줌미팅-자동화.test_zoom_meeting -v` (경로에 한글/하이픈이 있어 모듈 임포트가 안 되면, 대신 `cd "10-projects\줌미팅-자동화"` 후 `..\..\.venv\Scripts\python.exe -m unittest test_zoom_meeting -v` 사용)

Expected: FAIL — `ModuleNotFoundError: No module named 'zoom_meeting'` (파일이 아직 없음)

- [ ] **Step 3: Write minimal implementation**

`10-projects/줌미팅-자동화/zoom_meeting.py`:

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
줌(Zoom) 미팅 생성기
- Server-to-Server OAuth로 인증 후 미팅을 예약하고 join_url을 출력
- 자격증명은 워크스페이스 루트 .env 에서 읽음 (git 제외됨)
- 표준 라이브러리만 사용 (별도 pip 설치 불필요)

사용 예:
  python zoom_meeting.py --topic "구매대행 실전반 3주차" --start 2026-08-05T14:00:00 --duration 120
"""

import argparse
import json
import sys
from pathlib import Path

REQUIRED_KEYS = ["ZOOM_ACCOUNT_ID", "ZOOM_CLIENT_ID", "ZOOM_CLIENT_SECRET", "ZOOM_USER_EMAIL"]


def load_env(env_path: Path) -> dict:
    """.env 파일을 파싱해 dict 로 반환 (KEY=VALUE, # 주석 무시)."""
    data = {}
    if not env_path.exists():
        return data
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        data[key.strip()] = val.strip().strip('"').strip("'")
    return data


def find_env() -> Path:
    """워크스페이스 루트(.env) → 스크립트 폴더(.env) 순으로 탐색."""
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / ".env",   # 워크스페이스 루트 (10-projects/줌미팅-자동화/ 기준 2단계 위)
        here.parent / ".env",       # 스크립트와 같은 폴더
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def load_credentials(env: dict) -> dict:
    """env dict에서 줌 자격증명 4종을 검증해 반환. 누락 시 ValueError."""
    missing = [k for k in REQUIRED_KEYS if not env.get(k, "").strip()]
    if missing:
        raise ValueError(f"다음 값이 .env에 없습니다: {', '.join(missing)}")
    return {k: env[k].strip() for k in REQUIRED_KEYS}


if __name__ == "__main__":
    pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "10-projects\줌미팅-자동화" ; ..\..\.venv\Scripts\python.exe -m unittest test_zoom_meeting -v`

Expected: PASS (4 tests)

- [ ] **Step 5: Create `.env.example`**

`10-projects/줌미팅-자동화/.env.example`:

```
# 줌 미팅 생성 자격증명 (zoom_meeting.py 용)
# 발급: marketplace.zoom.us > Developer > Build App > Server-to-Server OAuth
ZOOM_ACCOUNT_ID=
ZOOM_CLIENT_ID=
ZOOM_CLIENT_SECRET=
# 줌 로그인 이메일 (S2S OAuth는 'me' 축약 불가, 실제 유저ID 필요)
ZOOM_USER_EMAIL=
```

- [ ] **Step 6: Commit**

```bash
git add "10-projects/줌미팅-자동화/zoom_meeting.py" "10-projects/줌미팅-자동화/test_zoom_meeting.py" "10-projects/줌미팅-자동화/.env.example"
git commit -m "feat: zoom_meeting.py env 로더 (find_env/load_env/load_credentials)"
```

---

### Task 2: `get_access_token()` — OAuth 토큰 발급

**Files:**
- Modify: `10-projects/줌미팅-자동화/zoom_meeting.py`
- Modify: `10-projects/줌미팅-자동화/test_zoom_meeting.py`

**Interfaces:**
- Consumes: 없음 (Task 1과 독립)
- Produces: `get_access_token(account_id: str, client_id: str, client_secret: str) -> str` (raises `RuntimeError` on HTTP 에러)

- [ ] **Step 1: Write the failing test**

`test_zoom_meeting.py`에 추가 (파일 상단 import에 `import json`, `from unittest.mock import patch, MagicMock`, `import urllib.error` 추가):

```python
class TestGetAccessToken(unittest.TestCase):
    @patch("zoom_meeting.urllib.request.urlopen")
    def test_get_access_token_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"access_token": "abc123"}).encode()
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        token = zoom_meeting.get_access_token("acc", "cid", "secret")

        self.assertEqual(token, "abc123")

    @patch("zoom_meeting.urllib.request.urlopen")
    def test_get_access_token_http_error_raises_runtime_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://zoom.us/oauth/token", code=401,
            msg="Unauthorized", hdrs=None,
            fp=__import__("io").BytesIO(b'{"error":"invalid_client"}'),
        )

        with self.assertRaises(RuntimeError) as ctx:
            zoom_meeting.get_access_token("acc", "bad-cid", "bad-secret")

        self.assertIn("401", str(ctx.exception))
```

파일 상단 import 블록을 다음과 같이 갱신:

```python
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch, MagicMock
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `..\..\.venv\Scripts\python.exe -m unittest test_zoom_meeting -v` (경로는 `10-projects\줌미팅-자동화` 안에서 실행)

Expected: FAIL — `AttributeError: module 'zoom_meeting' has no attribute 'get_access_token'`

- [ ] **Step 3: Write minimal implementation**

`zoom_meeting.py` 상단 import에 추가:

```python
import base64
import urllib.error
import urllib.parse
import urllib.request
```

`load_credentials` 함수 뒤에 추가:

```python
def get_access_token(account_id: str, client_id: str, client_secret: str) -> str:
    """Server-to-Server OAuth로 access token 발급."""
    url = "https://zoom.us/oauth/token?" + urllib.parse.urlencode({
        "grant_type": "account_credentials",
        "account_id": account_id,
    })
    auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    req = urllib.request.Request(url, method="POST", headers={
        "Authorization": f"Basic {auth}",
    })
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            return data["access_token"]
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        raise RuntimeError(f"Zoom 토큰 발급 실패 ({e.code}): {body}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `..\..\.venv\Scripts\python.exe -m unittest test_zoom_meeting -v`

Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add "10-projects/줌미팅-자동화/zoom_meeting.py" "10-projects/줌미팅-자동화/test_zoom_meeting.py"
git commit -m "feat: zoom_meeting.py OAuth 토큰 발급 (get_access_token)"
```

---

### Task 3: `create_meeting()` — 미팅 생성 API 호출

**Files:**
- Modify: `10-projects/줌미팅-자동화/zoom_meeting.py`
- Modify: `10-projects/줌미팅-자동화/test_zoom_meeting.py`

**Interfaces:**
- Consumes: 없음 (access_token은 문자열로 주입받음 — Task 2의 `get_access_token` 반환값과 타입 일치)
- Produces: `create_meeting(access_token: str, user_email: str, topic: str, start_time: str, duration_minutes: int) -> dict` — 반환 dict 키: `topic`, `start_time`, `duration`, `join_url`, `start_url` (raises `RuntimeError` on HTTP 에러)

- [ ] **Step 1: Write the failing test**

`test_zoom_meeting.py`에 추가:

```python
class TestCreateMeeting(unittest.TestCase):
    @patch("zoom_meeting.urllib.request.urlopen")
    def test_create_meeting_success_returns_expected_fields(self, mock_urlopen):
        api_response = {
            "topic": "구매대행 실전반 3주차",
            "start_time": "2026-08-05T14:00:00Z",
            "duration": 120,
            "join_url": "https://zoom.us/j/1234567890",
            "start_url": "https://zoom.us/s/1234567890?zak=xyz",
            "id": 1234567890,
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(api_response).encode()
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        result = zoom_meeting.create_meeting(
            access_token="token123",
            user_email="bulsaja23@gmail.com",
            topic="구매대행 실전반 3주차",
            start_time="2026-08-05T14:00:00",
            duration_minutes=120,
        )

        self.assertEqual(result["topic"], "구매대행 실전반 3주차")
        self.assertEqual(result["join_url"], "https://zoom.us/j/1234567890")
        self.assertEqual(result["start_url"], "https://zoom.us/s/1234567890?zak=xyz")
        self.assertEqual(result["duration"], 120)

        sent_request = mock_urlopen.call_args[0][0]
        self.assertIn("bulsaja23%40gmail.com", sent_request.full_url)
        sent_body = json.loads(sent_request.data.decode())
        self.assertEqual(sent_body["settings"]["waiting_room"], False)
        self.assertEqual(sent_body["timezone"], "Asia/Seoul")
        self.assertEqual(sent_body["type"], 2)

    @patch("zoom_meeting.urllib.request.urlopen")
    def test_create_meeting_http_error_raises_runtime_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://api.zoom.us/v2/users/x/meetings", code=400,
            msg="Bad Request", hdrs=None,
            fp=__import__("io").BytesIO(b'{"message":"Invalid start_time"}'),
        )

        with self.assertRaises(RuntimeError) as ctx:
            zoom_meeting.create_meeting(
                access_token="token123",
                user_email="bulsaja23@gmail.com",
                topic="테스트",
                start_time="잘못된형식",
                duration_minutes=60,
            )

        self.assertIn("400", str(ctx.exception))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `..\..\.venv\Scripts\python.exe -m unittest test_zoom_meeting -v`

Expected: FAIL — `AttributeError: module 'zoom_meeting' has no attribute 'create_meeting'`

- [ ] **Step 3: Write minimal implementation**

`zoom_meeting.py`에서 `get_access_token` 함수 뒤에 추가:

```python
def create_meeting(access_token: str, user_email: str, topic: str, start_time: str, duration_minutes: int) -> dict:
    """줌 미팅 생성. start_time은 'YYYY-MM-DDTHH:MM:SS' (KST) 형식."""
    url = f"https://api.zoom.us/v2/users/{urllib.parse.quote(user_email)}/meetings"
    payload = {
        "topic": topic,
        "type": 2,
        "start_time": start_time,
        "duration": duration_minutes,
        "timezone": "Asia/Seoul",
        "settings": {
            "waiting_room": False,
        },
    }
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            return {
                "topic": data["topic"],
                "start_time": data["start_time"],
                "duration": data["duration"],
                "join_url": data["join_url"],
                "start_url": data["start_url"],
            }
    except urllib.error.HTTPError as e:
        body_text = e.read().decode() if e.fp else ""
        raise RuntimeError(f"Zoom 미팅 생성 실패 ({e.code}): {body_text}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `..\..\.venv\Scripts\python.exe -m unittest test_zoom_meeting -v`

Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add "10-projects/줌미팅-자동화/zoom_meeting.py" "10-projects/줌미팅-자동화/test_zoom_meeting.py"
git commit -m "feat: zoom_meeting.py 미팅 생성 API 호출 (create_meeting)"
```

---

### Task 4: CLI 진입점 (`main()`)

**Files:**
- Modify: `10-projects/줌미팅-자동화/zoom_meeting.py`
- Modify: `10-projects/줌미팅-자동화/test_zoom_meeting.py`

**Interfaces:**
- Consumes: `find_env`, `load_env`, `load_credentials` (Task 1), `get_access_token` (Task 2), `create_meeting` (Task 3) — 모두 동일 모듈 내 함수라 직접 호출
- Produces: `main() -> None`. 성공 시 stdout에 JSON 한 줄 출력 후 정상 종료. 실패 시 stderr에 에러 메시지 출력 후 `sys.exit(1)`.

- [ ] **Step 1: Write the failing test**

`test_zoom_meeting.py`에 추가 (상단 import에 `import io` 추가):

```python
class TestMain(unittest.TestCase):
    @patch("zoom_meeting.create_meeting")
    @patch("zoom_meeting.get_access_token")
    @patch("zoom_meeting.find_env")
    def test_main_success_prints_json_to_stdout(self, mock_find_env, mock_get_token, mock_create_meeting):
        mock_find_env.return_value = Path("dummy/.env")
        with patch("zoom_meeting.load_env", return_value={
            "ZOOM_ACCOUNT_ID": "acc", "ZOOM_CLIENT_ID": "cid",
            "ZOOM_CLIENT_SECRET": "secret", "ZOOM_USER_EMAIL": "user@example.com",
        }):
            mock_get_token.return_value = "token123"
            mock_create_meeting.return_value = {
                "topic": "테스트 미팅", "start_time": "2026-08-05T14:00:00Z",
                "duration": 120, "join_url": "https://zoom.us/j/111",
                "start_url": "https://zoom.us/s/111",
            }
            test_args = ["zoom_meeting.py", "--topic", "테스트 미팅",
                          "--start", "2026-08-05T14:00:00", "--duration", "120"]
            captured = io.StringIO()
            with patch("sys.argv", test_args), patch("sys.stdout", captured):
                zoom_meeting.main()

        output = json.loads(captured.getvalue().strip())
        self.assertEqual(output["join_url"], "https://zoom.us/j/111")
        self.assertEqual(output["start_url"], "https://zoom.us/s/111")

    @patch("zoom_meeting.find_env")
    def test_main_missing_credentials_exits_with_error(self, mock_find_env):
        mock_find_env.return_value = Path("dummy/.env")
        with patch("zoom_meeting.load_env", return_value={}):
            test_args = ["zoom_meeting.py", "--topic", "테스트",
                          "--start", "2026-08-05T14:00:00", "--duration", "60"]
            captured_err = io.StringIO()
            with patch("sys.argv", test_args), patch("sys.stderr", captured_err):
                with self.assertRaises(SystemExit) as ctx:
                    zoom_meeting.main()

        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("ZOOM_ACCOUNT_ID", captured_err.getvalue())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `..\..\.venv\Scripts\python.exe -m unittest test_zoom_meeting -v`

Expected: FAIL — `AttributeError: module 'zoom_meeting' has no attribute 'main'`

- [ ] **Step 3: Write minimal implementation**

`zoom_meeting.py` 맨 아래 `if __name__ == "__main__": pass`를 다음으로 교체:

```python
def main():
    parser = argparse.ArgumentParser(description="줌 미팅 생성 (Server-to-Server OAuth)")
    parser.add_argument("--topic", required=True, help="미팅 제목")
    parser.add_argument("--start", required=True, help="시작시간, KST, 예: 2026-08-05T14:00:00")
    parser.add_argument("--duration", required=True, type=int, help="소요시간(분)")
    args = parser.parse_args()

    env = load_env(find_env())
    try:
        creds = load_credentials(env)
    except ValueError as e:
        print(f"[설정 오류] {e}", file=sys.stderr)
        print(
            "marketplace.zoom.us > Developer > Build App > Server-to-Server OAuth 로 앱을 만들고 "
            ".env에 ZOOM_ACCOUNT_ID/ZOOM_CLIENT_ID/ZOOM_CLIENT_SECRET/ZOOM_USER_EMAIL을 채워주세요.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        token = get_access_token(creds["ZOOM_ACCOUNT_ID"], creds["ZOOM_CLIENT_ID"], creds["ZOOM_CLIENT_SECRET"])
        meeting = create_meeting(token, creds["ZOOM_USER_EMAIL"], args.topic, args.start, args.duration)
    except RuntimeError as e:
        print(f"[오류] {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(meeting, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `..\..\.venv\Scripts\python.exe -m unittest test_zoom_meeting -v`

Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add "10-projects/줌미팅-자동화/zoom_meeting.py" "10-projects/줌미팅-자동화/test_zoom_meeting.py"
git commit -m "feat: zoom_meeting.py CLI 진입점 (main)"
```

---

### Task 5: `zoom-meeting` 스킬 정의 작성

**Files:**
- Create: `.claude/skills/zoom-meeting/SKILL.md`

**Interfaces:**
- Consumes: Task 4에서 완성된 `zoom_meeting.py` CLI (`--topic --start --duration` 인자, stdout JSON 출력)
- Produces: 없음 (스킬 문서, 다른 태스크가 이걸 소비하지 않음)

- [ ] **Step 1: SKILL.md 작성**

`.claude/skills/zoom-meeting/SKILL.md`:

```markdown
---
name: zoom-meeting
description: 자연어 요청("줌미팅 잡아줘", "줌 링크 만들어줘")을 받아 Zoom Server-to-Server OAuth API로 실제 미팅을 생성하고 join 링크를 반환. 날짜/시작시간/소요시간이 빠지면 먼저 질문하고, 제목은 명시돼도 없어도 항상 확인 질문. 생성 직후 (시작시간-30분)에 "줌 오픈" 리마인더를 todo에 자동 등록.
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
---

# zoom-meeting

Zoom Server-to-Server OAuth로 실제 미팅을 예약하고 join_url을 대화창에 반환하는 스킬.
실행 엔진은 `10-projects/줌미팅-자동화/zoom_meeting.py` (표준 라이브러리만 사용).

## 전제

- 자격증명은 워크스페이스 루트 `.env`의 `ZOOM_ACCOUNT_ID`/`ZOOM_CLIENT_ID`/`ZOOM_CLIENT_SECRET`/`ZOOM_USER_EMAIL`에서 읽음 (git 제외)
- 값이 없으면 스크립트가 안내 메시지 출력 → 사용자에게 Server-to-Server OAuth 앱 생성 안내 (marketplace.zoom.us > Developer > Build App)

## 수행 순서

### 1. 입력 파싱 및 확인

사용자 요청에서 **날짜 / 시작시간 / 소요시간 / 제목** 4개를 추출한다.

- 날짜/시작시간/소요시간 중 빠진 게 있으면, 빠진 항목만 한 번에 질문
- **제목은 요청에 이미 포함돼 있어도 항상 재확인 질문한다.** ("제목은 뭐로 할까요?") 절대 임의로 만들거나, 사용자가 준 값을 확인 없이 그대로 쓰지 않는다.
- 연도 생략 시 올해로 간주, 시간대는 KST 고정
- "N시간" → 분 단위로 환산 (예: 2시간 → 120)

### 2. 미팅 생성

Windows(이 워크스페이스)에서는 venv 파이썬 사용:

```bash
.venv/Scripts/python.exe "10-projects/줌미팅-자동화/zoom_meeting.py" \
  --topic "제목" \
  --start "2026-08-05T14:00:00" \
  --duration 120
```

- 성공: stdout에 JSON 한 줄 (`topic`, `start_time`, `duration`, `join_url`, `start_url`)
- 실패: stderr 메시지를 그대로 사용자에게 전달 (자격증명 문제 / Zoom API 에러)

### 3. 결과 출력

대화창에는 다음만 간결하게 표시:
- 제목
- 일시 (날짜 + 시작시간 + 소요시간)
- join_url

`start_url`은 호스트 전용 링크이므로 대화 로그에 노출하지 않는다 (리마인더 등록에만 사용).

### 4. 조기 오픈 리마인더 자동 등록

미팅 생성 성공 직후, (시작시간 - 30분) 시각을 계산해 `40-personal/46-todos/active-todos.md`의 `## 🔥 Today` (당일이면) 또는 `## 📅 This Week` 섹션에 아래 형식으로 직접 추가 (todo 스킬과 동일 포맷, 별도 확인 질문 없이 바로 등록):

```markdown
- [ ] 줌 오픈: [제목] (HH:MM 접속 → start_url로 열기)
  - added: YYYY-MM-DD HH:MM
  - priority: normal
```

Zoom은 호스트가 `start_url`로 접속하는 순간 예약 시간과 무관하게 즉시 미팅을 열기 때문에, 이 리마인더 시각에 접속하면 30분 조기 오픈이 그대로 달성된다.

## 참고

- `waiting_room: false`로 생성되므로 참가자는 대기실 없이 바로 입장 (단, 호스트가 미팅을 연 이후에만 가능)
- 반복 미팅/참가자 초대/Google Calendar 등록은 범위 밖 (필요 시 send-email 스킬과 별도 조합)
- 스크립트 상세: `10-projects/줌미팅-자동화/zoom_meeting.py`
- 자격증명 템플릿: `10-projects/줌미팅-자동화/.env.example`
```

- [ ] **Step 2: Commit**

```bash
git add ".claude/skills/zoom-meeting/SKILL.md"
git commit -m "feat: zoom-meeting 스킬 정의 추가"
```

---

### Task 6: 실 자격증명으로 End-to-End 수동 검증

**Files:** 없음 (코드 변경 없이 수동 실행 검증)

**Interfaces:**
- Consumes: Task 4의 `zoom_meeting.py` CLI, `.env`에 이미 설정된 4개 값
- Produces: 없음 (검증 결과만 확인)

- [ ] **Step 1: 실제 API 호출로 테스트 미팅 생성**

Run:
```bash
.venv/Scripts/python.exe "10-projects/줌미팅-자동화/zoom_meeting.py" \
  --topic "[테스트] 삭제예정" \
  --start "2026-08-01T10:00:00" \
  --duration 30
```

Expected: stdout에 JSON 출력, `join_url`이 `https://zoom.us/j/`로 시작하는 유효한 URL

- [ ] **Step 2: join_url 브라우저에서 열어 미팅 존재 확인**

브라우저에서 join_url 접속 → "회의 대기 중" 또는 참가 화면이 뜨는지 확인 (호스트가 아직 안 열었으므로 바로 입장은 안 되는 게 정상)

- [ ] **Step 3: 테스트 미팅 삭제**

Zoom 웹(zoom.us) 로그인 → 내 미팅 목록에서 방금 생성된 "[테스트] 삭제예정" 미팅 찾아 삭제

- [ ] **Step 4: 날짜/시간/제목 누락 시나리오로 스킬 자체 동작 확인**

Claude에게 "줌미팅 잡아줘" (날짜/시간/제목 없이)라고 요청 → 빠진 항목을 모두 질문하는지, 제목은 명시해도 항상 재확인하는지 확인

- [ ] **Step 5: 리마인더 등록 확인**

미팅 생성 완료 후 `40-personal/46-todos/active-todos.md`를 열어 "줌 오픈" 항목이 (시작시간-30분)으로 정확히 등록됐는지 확인

---

## Self-Review 결과

- **스펙 커버리지**: 자연어 파싱(누락 질문 + 제목 필수 질문) → Task 5, OAuth+미팅 생성 → Task 1-4, 조기 오픈 리마인더 → Task 5, 에러 처리(.env 누락/API 에러) → Task 1/2/3/4, 실제 검증 → Task 6. 스펙 전 항목 커버됨.
- **플레이스홀더 스캔**: 없음 — 모든 코드 블록은 실행 가능한 실제 구현.
- **타입 일관성**: `get_access_token` 반환 `str` → `create_meeting`의 `access_token: str` 인자와 일치. `create_meeting` 반환 dict 키(`topic`/`start_time`/`duration`/`join_url`/`start_url`)가 Task 5 SKILL.md의 "결과 출력" 절에서 참조하는 필드명과 일치. `load_credentials` 반환 dict 키(`ZOOM_ACCOUNT_ID` 등)가 `main()`에서 사용하는 키와 일치.
