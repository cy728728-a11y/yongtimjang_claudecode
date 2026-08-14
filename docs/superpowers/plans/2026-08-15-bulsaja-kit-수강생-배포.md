# bulsaja-kit 수강생 배포판 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 용팀장의 `bulsaja-thumbnail` · `bulsaja-shipping-fee` 스킬을, 개인정보·구글시트·gws 의존을 제거한 Claude Code 플러그인으로 재패키징해 수강생이 명령 2줄로 설치·사용하게 한다.

**Architecture:** 스크립트 본문은 건드리지 않는다. 스크립트가 경유하는 `eroomlib.gsheets` 한 모듈을 로컬 JSON 저장소 백엔드로 교체하고, `requests` 의존을 stdlib `urllib` 셔임으로 대체한다. 결과적으로 판정 로직·프롬프트·크레딧 계산은 원본과 동일하게 유지되고, 저장 위치만 구글시트 → 수강생 로컬 폴더로 바뀐다.

**Tech Stack:** Python 3.9+ (표준 라이브러리만), Claude Code 플러그인 규격(`.claude-plugin/marketplace.json`), 불사자 원격 HTTP MCP

**Spec:** `docs/superpowers/specs/2026-08-15-bulsaja-kit-수강생-배포-design.md`

## Global Constraints

- **파이썬 3.9 호환 필수.** 맥 시스템 파이썬이 3.9.6이다. `match`, `X | Y` 타입표기, `tomllib` 금지
- **외부 패키지 의존 0.** 표준 라이브러리만. `pip install` 을 수강생에게 시키지 않는다
- **설정 파일은 `ini`**, `configparser` 로 읽는다 (`tomllib` 은 3.11+ 전용)
- **빌드 위치**: `/Users/choiyongsmacbook/Documents/bulsaja-kit` — 용팀장 워크스페이스 저장소 **밖**의 독립 git 저장소
- **원본은 읽기 전용.** `.claude/skills/`, `.claude/lib/`, worktree 를 수정하지 않는다. 복사만 한다
- **불사자 토큰을 stdout·로그·파일에 출력 금지**
- **인명 표기 금지**: "이룸", "용팀장", "용쌤" 이 산출물에 남으면 안 된다
- 판정 기준·프롬프트·크레딧 계산 로직은 **원본과 동일하게 유지**한다. 개선하지 않는다
- 커밋 메시지는 한국어, 배포 저장소에는 Co-Authored-By 트레일러를 넣지 않는다

**원본 경로 (읽기 전용):**
- 썸네일: `/Users/choiyongsmacbook/Documents/yongtimjang_claudecode/.claude/skills/bulsaja-thumbnail`
- 배송비: `/Users/choiyongsmacbook/Documents/yongtimjang_claudecode/.claude/worktrees/shipfee-skill-install/.claude/skills/bulsaja-shipping-fee`
- 라이브러리: `/Users/choiyongsmacbook/Documents/yongtimjang_claudecode/.claude/lib/eroomlib`

---

### Task 1: 저장소 뼈대와 플러그인 매니페스트

**Files:**
- Create: `~/Documents/bulsaja-kit/.claude-plugin/marketplace.json`
- Create: `~/Documents/bulsaja-kit/.claude-plugin/plugin.json`
- Create: `~/Documents/bulsaja-kit/.gitignore`
- Test: `~/Documents/bulsaja-kit/tests/test_manifest.py`

**Interfaces:**
- Produces: 플러그인 이름 `bulsaja-kit`, 마켓플레이스 이름 `bulsaja-kit`. 이후 모든 스킬은 `skills/<name>/SKILL.md` 에 놓인다

- [ ] **Step 1: 저장소 생성**

```bash
mkdir -p ~/Documents/bulsaja-kit/{.claude-plugin,skills,lib,config,scripts,tests}
cd ~/Documents/bulsaja-kit && git init -b main
```

- [ ] **Step 2: 매니페스트 검증 테스트 작성**

`tests/test_manifest.py`:

```python
"""플러그인 매니페스트 규격 검증 — 설치 실패를 배포 전에 잡는다."""
import json
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestManifest(unittest.TestCase):
    def test_마켓플레이스가_플러그인을_1개_선언한다(self):
        with open(os.path.join(ROOT, ".claude-plugin", "marketplace.json"),
                  encoding="utf-8") as f:
            m = json.load(f)
        self.assertEqual(m["name"], "bulsaja-kit")
        self.assertEqual(len(m["plugins"]), 1)
        self.assertEqual(m["plugins"][0]["name"], "bulsaja-kit")
        self.assertEqual(m["plugins"][0]["source"], "./")

    def test_플러그인_버전이_마켓플레이스와_같다(self):
        d = os.path.join(ROOT, ".claude-plugin")
        with open(os.path.join(d, "marketplace.json"), encoding="utf-8") as f:
            mk = json.load(f)
        with open(os.path.join(d, "plugin.json"), encoding="utf-8") as f:
            pl = json.load(f)
        self.assertEqual(mk["plugins"][0]["version"], pl["version"])

    def test_선언된_스킬이_실제로_존재한다(self):
        for name in ("bulsaja-thumbnail", "bulsaja-shipping-fee"):
            p = os.path.join(ROOT, "skills", name, "SKILL.md")
            self.assertTrue(os.path.exists(p), f"{name}/SKILL.md 없음")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: 실패 확인**

Run: `cd ~/Documents/bulsaja-kit && /usr/bin/python3 -m unittest tests.test_manifest -v`
Expected: FAIL — `marketplace.json` 없음 (FileNotFoundError)

- [ ] **Step 4: 매니페스트 작성**

`.claude-plugin/marketplace.json`:

```json
{
  "name": "bulsaja-kit",
  "description": "불사자 셀러 자동화 스킬 모음 — 썸네일 생성, 배송비 계산",
  "owner": { "name": "bulsaja-kit" },
  "plugins": [
    {
      "name": "bulsaja-kit",
      "description": "불사자 마켓그룹 단위로 AI 썸네일을 생성·검수해 반영하고, 상품 무게·부피를 판정해 해외배송비를 계산·저장하는 스킬 모음",
      "version": "1.0.0",
      "source": "./"
    }
  ]
}
```

`.claude-plugin/plugin.json`:

```json
{
  "name": "bulsaja-kit",
  "description": "불사자 셀러 자동화 스킬 모음 — 썸네일 생성, 배송비 계산",
  "version": "1.0.0",
  "keywords": ["bulsaja", "smartstore", "ecommerce", "thumbnail", "shipping"]
}
```

`.gitignore`:

```
__pycache__/
*.pyc
.env
.venv/
runs/
products/
.DS_Store
```

- [ ] **Step 5: 스킬 자리만 먼저 채워 테스트 통과시키기**

Task 5·6 에서 실제 내용이 들어온다. 지금은 디렉터리와 최소 SKILL.md 만 만든다.

```bash
cd ~/Documents/bulsaja-kit
mkdir -p skills/bulsaja-thumbnail skills/bulsaja-shipping-fee
printf -- '---\nname: bulsaja-thumbnail\ndescription: placeholder\n---\n' > skills/bulsaja-thumbnail/SKILL.md
printf -- '---\nname: bulsaja-shipping-fee\ndescription: placeholder\n---\n' > skills/bulsaja-shipping-fee/SKILL.md
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `cd ~/Documents/bulsaja-kit && /usr/bin/python3 -m unittest tests.test_manifest -v`
Expected: PASS (3 tests)

- [ ] **Step 7: 커밋**

```bash
cd ~/Documents/bulsaja-kit
git add -A
git commit -m "저장소 뼈대와 플러그인 매니페스트 추가"
```

---

### Task 2: `_http.py` — `requests` 를 표준 라이브러리로 대체

**Files:**
- Create: `~/Documents/bulsaja-kit/lib/eroomlib/_http.py`
- Test: `~/Documents/bulsaja-kit/tests/test_http.py`

**Interfaces:**
- Produces:
  - `class Response` — 속성 `status_code: int`, `headers: dict`(대소문자 무시 조회), `content: bytes`, `text: str`
  - `class Session` — 메서드 `post(url, headers=None, data=None, timeout=None) -> Response`
  - `def get(url, headers=None, timeout=None) -> Response`
  - `class RequestException(Exception)`
- Consumes: 없음 (표준 라이브러리만)

**왜 필요한가:** 원본 `eroomlib` 는 `requests` 를 3곳에서 쓴다 (`bulsaja.py:133` Session, `bulsaja.py:160` RequestException, `snapshot.py:505` get). 맥 시스템 파이썬 3.9.6 에는 `requests` 가 없다. 수강생에게 `pip install` 을 시키지 않으려면 대체가 필요하다.

**핵심 주의:** HTTP 4xx/5xx 는 **예외를 던지지 않는다.** `urllib` 은 기본적으로 `HTTPError` 를 던지지만, 호출부(`bulsaja._post`)가 `resp.status_code` 로 401·429·5xx 를 직접 분기하므로 `HTTPError` 를 잡아 `Response` 로 변환해야 한다. 이걸 놓치면 재시도·토큰만료 안내가 전부 죽는다.

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_http.py`:

```python
"""_http 셔임 — requests 없이 도는지 검증. 로컬 HTTP 서버로 실제 통신한다."""
import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))

from eroomlib import _http  # noqa: E402


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # 테스트 출력 오염 방지
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path == "/echo":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Mcp-Session-Id", "sess-42")
            self.end_headers()
            self.wfile.write(json.dumps({
                "받은본문": json.loads(body.decode("utf-8")),
                "받은인증": self.headers.get("Authorization"),
            }).encode("utf-8"))
        elif self.path == "/error401":
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"unauthorized")
        elif self.path == "/error500":
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"boom")

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.end_headers()
        self.wfile.write(b"\x89PNG binary")


class TestHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), _Handler)
        cls.base = "http://127.0.0.1:%d" % cls.srv.server_address[1]
        cls.t = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.t.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_post_가_본문과_헤더를_보낸다(self):
        s = _http.Session()
        r = s.post(self.base + "/echo",
                   headers={"Authorization": "Bearer X", "Content-Type": "application/json"},
                   data=json.dumps({"a": 1}).encode("utf-8"), timeout=5)
        self.assertEqual(r.status_code, 200)
        got = json.loads(r.text)
        self.assertEqual(got["받은본문"], {"a": 1})
        self.assertEqual(got["받은인증"], "Bearer X")

    def test_응답헤더를_대소문자_무시하고_읽는다(self):
        s = _http.Session()
        r = s.post(self.base + "/echo", headers={"Content-Type": "application/json"},
                   data=b"{}", timeout=5)
        self.assertEqual(r.headers.get("Mcp-Session-Id"), "sess-42")
        self.assertEqual(r.headers.get("mcp-session-id"), "sess-42")

    def test_401은_예외가_아니라_status_code로_온다(self):
        s = _http.Session()
        r = s.post(self.base + "/error401", data=b"{}", timeout=5)
        self.assertEqual(r.status_code, 401)

    def test_500도_예외가_아니라_status_code로_온다(self):
        s = _http.Session()
        r = s.post(self.base + "/error500", data=b"{}", timeout=5)
        self.assertEqual(r.status_code, 500)
        self.assertIn("boom", r.text)

    def test_get_이_바이너리를_content로_준다(self):
        r = _http.get(self.base + "/img", timeout=5)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, b"\x89PNG binary")

    def test_연결실패는_RequestException(self):
        s = _http.Session()
        with self.assertRaises(_http.RequestException):
            s.post("http://127.0.0.1:1/none", data=b"{}", timeout=2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패 확인**

Run: `cd ~/Documents/bulsaja-kit && /usr/bin/python3 -m unittest tests.test_http -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'eroomlib'`

- [ ] **Step 3: 구현**

`lib/eroomlib/_http.py`:

```python
#!/usr/bin/env python3
"""`requests` 최소 대체 — 표준 라이브러리(urllib)만 쓴다.

**왜**: 배포판은 수강생에게 `pip install` 을 시키지 않는 것이 목표다. 맥 시스템
파이썬(3.9.6)에는 requests 가 없다. eroomlib 이 requests 에서 쓰는 기능은
`Session().post` · 모듈 수준 `get` · `RequestException` 뿐이라 얇게 감쌀 수 있다.

**중요**: HTTP 4xx/5xx 에서 예외를 던지지 않는다. 호출부(bulsaja._post)가
status_code 로 401/429/5xx 를 직접 분기하기 때문이다.
"""
import urllib.error
import urllib.request


class RequestException(Exception):
    """네트워크 계층 실패(연결 불가·타임아웃). HTTP 에러 응답은 여기 해당 없음."""


class _Headers(object):
    """대소문자 무시 헤더 조회. `resp.headers.get("Mcp-Session-Id")` 대응."""

    def __init__(self, pairs):
        self._d = {}
        for k, v in pairs:
            self._d[k.lower()] = v

    def get(self, key, default=None):
        return self._d.get(key.lower(), default)

    def __contains__(self, key):
        return key.lower() in self._d

    def __getitem__(self, key):
        return self._d[key.lower()]

    def items(self):
        return self._d.items()


class Response(object):
    def __init__(self, status_code, headers, content):
        self.status_code = status_code
        self.headers = headers
        self.content = content

    @property
    def text(self):
        try:
            return self.content.decode("utf-8")
        except UnicodeDecodeError:
            return self.content.decode("utf-8", "replace")

    def json(self):
        import json
        return json.loads(self.text)


def _send(method, url, headers=None, data=None, timeout=None):
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        # HTTP 에러도 정상 응답으로 돌려준다 — 호출부가 status_code 로 분기한다
        body = e.read() if hasattr(e, "read") else b""
        return Response(e.code, _Headers(e.headers.items() if e.headers else []), body)
    except Exception as e:
        # URLError·socket.timeout·ssl 오류 등 네트워크 계층 실패
        raise RequestException(str(e))
    with resp:
        return Response(resp.getcode(), _Headers(resp.headers.items()), resp.read())


class Session(object):
    """requests.Session 자리. urllib 은 커넥션 재사용을 안 하지만 인터페이스는 같다."""

    def post(self, url, headers=None, data=None, timeout=None):
        return _send("POST", url, headers=headers, data=data, timeout=timeout)

    def get(self, url, headers=None, timeout=None):
        return _send("GET", url, headers=headers, timeout=timeout)

    def close(self):
        pass


def post(url, headers=None, data=None, timeout=None):
    return _send("POST", url, headers=headers, data=data, timeout=timeout)


def get(url, headers=None, timeout=None):
    return _send("GET", url, headers=headers, timeout=timeout)
```

`lib/eroomlib/__init__.py` 는 Task 4 에서 원본을 복사해 온다. 이 테스트를 먼저 돌리려면 빈 파일을 만들어 둔다:

```bash
touch ~/Documents/bulsaja-kit/lib/eroomlib/__init__.py
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd ~/Documents/bulsaja-kit && /usr/bin/python3 -m unittest tests.test_http -v`
Expected: PASS (6 tests)

- [ ] **Step 5: 커밋**

```bash
cd ~/Documents/bulsaja-kit
git add lib/eroomlib/_http.py lib/eroomlib/__init__.py tests/test_http.py
git commit -m "requests 대체 HTTP 셔임 추가 (표준 라이브러리만 사용)"
```

---

### Task 3: `localstore.py` — 구글시트를 대체하는 로컬 JSON 저장소

**Files:**
- Create: `~/Documents/bulsaja-kit/lib/eroomlib/localstore.py`
- Test: `~/Documents/bulsaja-kit/tests/test_localstore.py`

**Interfaces:**
- Produces:
  - `def parse_range(rng) -> (tab_or_None, r1, c1, r2_or_None, c2_or_None)` — A1 표기 파싱. 0-기반 인덱스 반환. 끝이 열려 있으면(`A2:A`) `r2` 는 `None`
  - `def load(store_id) -> dict` — `{"탭이름": [[셀,...],...]}`
  - `def save(store_id, doc) -> None` — 원자적 쓰기
  - `def get_values(store_id, rng, default_tab) -> list[list[str]]`
  - `def set_values(store_id, rng, values, default_tab) -> int` — 쓴 셀 수
  - `def append(store_id, tab, rows) -> int`
  - `def ensure_tab(store_id, tab, header) -> bool` — 새로 만들었으면 True
  - `def insert_header_row(store_id, tab, header) -> None` — 맨 위에 행 삽입
- Consumes: 없음

**설계 근거:** 원본 `matrix.py` 는 시트를 직접 부르지 않고 `gsheets.ensure_tab` / `sheets_get` / `sheets_update` 만 쓴다(`matrix.py:31-35`). 따라서 이 3개 + `append_rows` / `sheets_batch_update` 만 로컬로 구현하면 `matrix.py` 를 그대로 재사용할 수 있다. `store_id` 는 원본의 `spreadsheetId` 자리에 그대로 들어가는 **파일 경로 문자열**이다.

**A1 표기에서 실제로 쓰이는 형태** (원본 호출부에서 수집):
- `A2:B200` — 탭 생략
- `'00_진행'!A2:A` — 탭 지정 + 끝 열림
- `00_진행!A1:K1` — 따옴표 없는 탭
- `C2:C` — 단일 열, 끝 열림

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_localstore.py`:

```python
"""로컬 저장소 — 구글시트 대체. A1 범위 파싱과 읽기/쓰기 왕복을 검증한다."""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))

from eroomlib import localstore as LS  # noqa: E402


class TestParseRange(unittest.TestCase):
    def test_탭_없는_사각범위(self):
        self.assertEqual(LS.parse_range("A2:B200"), (None, 1, 0, 199, 1))

    def test_따옴표_탭과_끝열린_범위(self):
        self.assertEqual(LS.parse_range("'00_진행'!A2:A"), ("00_진행", 1, 0, None, 0))

    def test_따옴표_없는_탭(self):
        self.assertEqual(LS.parse_range("00_진행!A1:K1"), ("00_진행", 0, 0, 0, 10))

    def test_단일열_끝열림(self):
        self.assertEqual(LS.parse_range("C2:C"), (None, 1, 2, None, 2))

    def test_두글자_열(self):
        tab, r1, c1, r2, c2 = LS.parse_range("AA1:AB2")
        self.assertEqual((c1, c2), (26, 27))


class TestStore(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.sid = os.path.join(self.dir, "board.json")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_탭을_헤더와_함께_만든다(self):
        created = LS.ensure_tab(self.sid, "00_진행", ["상품id", "상품", "썸네일"])
        self.assertTrue(created)
        self.assertFalse(LS.ensure_tab(self.sid, "00_진행", ["상품id", "상품", "썸네일"]))
        rows = LS.get_values(self.sid, "A1:C1", "00_진행")
        self.assertEqual(rows, [["상품id", "상품", "썸네일"]])

    def test_쓰고_읽으면_같은_값이_나온다(self):
        LS.ensure_tab(self.sid, "00_진행", ["상품id", "상품", "썸네일"])
        LS.set_values(self.sid, "A2:C3",
                      [["p1", "상품하나", "완료"], ["p2", "상품둘", ""]], "00_진행")
        self.assertEqual(LS.get_values(self.sid, "A2:C3", "00_진행"),
                         [["p1", "상품하나", "완료"], ["p2", "상품둘", ""]])

    def test_끝열린_범위는_있는_데이터까지만_준다(self):
        LS.ensure_tab(self.sid, "00_진행", ["상품id", "상품"])
        LS.set_values(self.sid, "A2:B4",
                      [["p1", "가"], ["p2", "나"], ["p3", "다"]], "00_진행")
        self.assertEqual(LS.get_values(self.sid, "'00_진행'!A2:A", "00_진행"),
                         [["p1"], ["p2"], ["p3"]])

    def test_범위밖_읽기는_빈_리스트(self):
        LS.ensure_tab(self.sid, "00_진행", ["상품id"])
        self.assertEqual(LS.get_values(self.sid, "A50:A", "00_진행"), [])

    def test_append_는_끝에_붙인다(self):
        LS.ensure_tab(self.sid, "썸네일", ["상품id", "판정"])
        LS.append(self.sid, "썸네일", [["p1", "합격"], ["p2", "재작업"]])
        LS.append(self.sid, "썸네일", [["p3", "합격"]])
        self.assertEqual(LS.get_values(self.sid, "A1:B4", "썸네일"),
                         [["상품id", "판정"], ["p1", "합격"],
                          ["p2", "재작업"], ["p3", "합격"]])

    def test_쓰기가_행을_자동_확장한다(self):
        LS.ensure_tab(self.sid, "00_진행", ["상품id", "상품"])
        LS.set_values(self.sid, "A10:B10", [["p9", "구"]], "00_진행")
        self.assertEqual(LS.get_values(self.sid, "A10:B10", "00_진행"), [["p9", "구"]])

    def test_헤더행_삽입은_기존행을_밀어낸다(self):
        LS.ensure_tab(self.sid, "00_진행", ["상품id"])
        LS.set_values(self.sid, "A2:A2", [["p1"]], "00_진행")
        LS.insert_header_row(self.sid, "00_진행", ["새헤더", "둘"])
        self.assertEqual(LS.get_values(self.sid, "A1:B3", "00_진행"),
                         [["새헤더", "둘"], ["상품id", ""], ["p1", ""]])

    def test_없는_저장소를_읽으면_빈_문서(self):
        self.assertEqual(LS.load(os.path.join(self.dir, "none.json")), {})

    def test_저장은_원자적이다_임시파일이_남지_않는다(self):
        LS.ensure_tab(self.sid, "t", ["a"])
        leftovers = [f for f in os.listdir(self.dir) if f.endswith(".tmp")]
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패 확인**

Run: `cd ~/Documents/bulsaja-kit && /usr/bin/python3 -m unittest tests.test_localstore -v`
Expected: FAIL — `ImportError: cannot import name 'localstore'`

- [ ] **Step 3: 구현**

`lib/eroomlib/localstore.py`:

```python
#!/usr/bin/env python3
"""구글시트 대체 로컬 저장소 — 스프레드시트 1장을 JSON 파일 1개로 흉내낸다.

**왜**: 배포판 수강생은 구글시트도 gws CLI 도 없다. 그런데 스킬 스크립트는
`eroomlib.matrix` 를 통해 현황판을 읽고 쓴다. matrix 는 시트를 직접 부르지 않고
`gsheets` 의 몇 함수만 쓰므로, 그 아래를 이 모듈로 갈아끼우면 matrix 와 스킬
스크립트를 **한 줄도 고치지 않고** 그대로 쓸 수 있다.

저장 형식: {"탭이름": [[셀, 셀, ...], ...]}  — 셀은 전부 문자열.
`store_id` 는 원본의 spreadsheetId 자리에 들어가는 **파일 경로 문자열**이다.
"""
import json
import os
import re
import tempfile

_A1 = re.compile(r"^(?:'([^']+)'|([^!]+))!(.+)$")
_CELL = re.compile(r"^([A-Z]+)(\d*)$")


def _col_index(letters):
    """'A' -> 0, 'Z' -> 25, 'AA' -> 26"""
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n - 1


def parse_range(rng):
    """A1 표기 -> (탭|None, r1, c1, r2|None, c2|None). 인덱스는 0-기반, 끝 포함.

    끝 행이 비어 있으면(`A2:A`) r2 는 None — "있는 데이터 끝까지" 를 뜻한다.
    """
    tab = None
    body = rng
    m = _A1.match(rng)
    if m:
        tab = m.group(1) or m.group(2)
        body = m.group(3)
    if ":" in body:
        a, b = body.split(":", 1)
    else:
        a = b = body
    ma, mb = _CELL.match(a.upper()), _CELL.match(b.upper())
    if not ma or not mb:
        raise ValueError("범위를 해석할 수 없습니다: %r" % rng)
    c1 = _col_index(ma.group(1))
    c2 = _col_index(mb.group(1))
    r1 = int(ma.group(2)) - 1 if ma.group(2) else 0
    r2 = int(mb.group(2)) - 1 if mb.group(2) else None
    return (tab, r1, c1, r2, c2)


def load(store_id):
    """저장소 문서를 읽는다. 파일이 없거나 깨졌으면 빈 문서."""
    if not os.path.exists(store_id):
        return {}
    try:
        with open(store_id, encoding="utf-8") as f:
            doc = json.load(f)
        return doc if isinstance(doc, dict) else {}
    except (ValueError, OSError):
        return {}


def save(store_id, doc):
    """원자적 저장 — 중간에 죽어도 반쪽 파일이 남지 않는다."""
    d = os.path.dirname(os.path.abspath(store_id))
    if d:
        os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d or ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
        os.replace(tmp, store_id)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _grid(doc, tab):
    return doc.get(tab) or []


def get_values(store_id, rng, default_tab=None):
    tab, r1, c1, r2, c2 = parse_range(rng)
    doc = load(store_id)
    grid = _grid(doc, tab or default_tab)
    end = len(grid) - 1 if r2 is None else min(r2, len(grid) - 1)
    out = []
    for i in range(r1, end + 1):
        row = grid[i] if i < len(grid) else []
        out.append([str(row[j]) if j < len(row) and row[j] is not None else ""
                    for j in range(c1, c2 + 1)])
    # 구글시트는 뒤쪽 빈 행을 돌려주지 않는다 — 같은 동작을 흉내낸다
    while out and not any(c.strip() for c in out[-1]):
        out.pop()
    return out


def set_values(store_id, rng, values, default_tab=None):
    tab, r1, c1, _r2, _c2 = parse_range(rng)
    name = tab or default_tab
    doc = load(store_id)
    grid = doc.setdefault(name, [])
    for i, row in enumerate(values):
        r = r1 + i
        while len(grid) <= r:
            grid.append([])
        line = grid[r]
        for j, val in enumerate(row):
            c = c1 + j
            while len(line) <= c:
                line.append("")
            line[c] = "" if val is None else str(val)
    save(store_id, doc)
    return sum(len(r) for r in values)


def append(store_id, tab, rows):
    doc = load(store_id)
    grid = doc.setdefault(tab, [])
    for row in rows:
        grid.append(["" if v is None else str(v) for v in row])
    save(store_id, doc)
    return len(rows)


def ensure_tab(store_id, tab, header):
    """탭이 없으면 헤더와 함께 만든다. 새로 만들었으면 True."""
    doc = load(store_id)
    if tab in doc and doc[tab]:
        return False
    doc[tab] = [[str(h) for h in header]]
    save(store_id, doc)
    return True


def insert_header_row(store_id, tab, header):
    """맨 위에 행을 하나 끼워 넣는다 (원본 matrix._insert_header_row 대응)."""
    doc = load(store_id)
    grid = doc.setdefault(tab, [])
    grid.insert(0, [str(h) for h in header])
    save(store_id, doc)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd ~/Documents/bulsaja-kit && /usr/bin/python3 -m unittest tests.test_localstore -v`
Expected: PASS (14 tests)

- [ ] **Step 5: 커밋**

```bash
cd ~/Documents/bulsaja-kit
git add lib/eroomlib/localstore.py tests/test_localstore.py
git commit -m "구글시트 대체 로컬 JSON 저장소 추가"
```

---

### Task 4: `gsheets.py` 로컬 백엔드 + eroomlib 이식

**Files:**
- Create: `~/Documents/bulsaja-kit/lib/eroomlib/gsheets.py` (원본을 대체하는 새 구현)
- Copy: `bulsaja.py`, `snapshot.py`, `matrix.py`, `config.py`, `envload.py`, `textnorm.py`, `dedup.py`, `exclusion.py`, `review_page.py`, `__init__.py` (원본에서)
- Modify: `lib/eroomlib/bulsaja.py` (import 한 줄), `lib/eroomlib/snapshot.py` (import 한 줄), `lib/eroomlib/matrix.py` (`index_groups`, `_insert_header_row`), `lib/eroomlib/config.py` (기본 경로)
- Test: `~/Documents/bulsaja-kit/tests/test_gsheets_local.py`

**Interfaces:**
- Consumes: `localstore` (Task 3), `_http` (Task 2)
- Produces: 원본과 **동일한 시그니처**의 `sheets_get(spreadsheet_id, rng, max_retries=4)`, `sheets_update(spreadsheet_id, rng, values_2d, value_input="RAW", max_retries=4)`, `sheets_batch_update(spreadsheet_id, data, value_input="USER_ENTERED", max_retries=4)`, `append_rows(spreadsheet_id, tab, rows, max_retries=7)`, `ensure_tab(spreadsheet_id, tab, header)`, `chunk_by_size(rows, budget=12000)`
- Produces: `matrix.index_groups(master_sheet=None) -> [(그룹명, store_path)]` — 로컬 해석
- Produces: `config.runs_root() -> str`, `config.store_for_group(group_name) -> str`

**주의:** `gdrive.py` 와 `webdriver.py` 는 복사하지 않는다. 배포판이 쓰지 않고, 각각 구글드라이브·셀레니움 결합을 끌고 온다.

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_gsheets_local.py`:

```python
"""gsheets 로컬 백엔드 — 원본 시그니처를 유지하는지, matrix 가 그대로 도는지."""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))

from eroomlib import gsheets as G  # noqa: E402
from eroomlib import matrix as M  # noqa: E402


class TestGsheetsLocal(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.sid = os.path.join(self.dir, "board.json")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_gws를_부르지_않는다(self):
        self.assertFalse(hasattr(G, "_run_gws"),
                         "배포판 gsheets 에 gws 호출이 남아 있으면 안 된다")

    def test_ensure_tab_후_읽기(self):
        G.ensure_tab(self.sid, "00_진행", ["상품id", "상품"])
        self.assertEqual(G.sheets_get(self.sid, "'00_진행'!A1:B1"),
                         [["상품id", "상품"]])

    def test_update_와_get_왕복(self):
        G.ensure_tab(self.sid, "00_진행", ["상품id", "상품"])
        G.sheets_update(self.sid, "'00_진행'!A2:B2", [["p1", "가"]])
        self.assertEqual(G.sheets_get(self.sid, "'00_진행'!A2:B2"), [["p1", "가"]])

    def test_append_rows(self):
        G.ensure_tab(self.sid, "썸네일", ["상품id", "판정"])
        G.append_rows(self.sid, "썸네일", [["p1", "합격"]])
        self.assertEqual(G.sheets_get(self.sid, "'썸네일'!A2:B2"), [["p1", "합격"]])

    def test_batch_update(self):
        G.ensure_tab(self.sid, "00_진행", ["상품id", "상품"])
        G.sheets_batch_update(self.sid, [
            {"range": "'00_진행'!A2:B2", "values": [["p1", "가"]]},
            {"range": "'00_진행'!A3:B3", "values": [["p2", "나"]]},
        ])
        self.assertEqual(G.sheets_get(self.sid, "'00_진행'!A2:B3"),
                         [["p1", "가"], ["p2", "나"]])

    def test_chunk_by_size_는_원본_동작을_유지한다(self):
        rows = [["x" * 100] for _ in range(50)]
        chunks = G.chunk_by_size(rows, budget=1000)
        self.assertGreater(len(chunks), 1)
        self.assertEqual(sum(len(c) for c in chunks), 50)


class TestMatrixOnLocal(unittest.TestCase):
    """matrix.py 를 한 줄도 안 고치고 로컬 저장소 위에서 돌린다."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.sid = os.path.join(self.dir, "board.json")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_ensure_read_mark_왕복(self):
        M.ensure(self.sid)
        M.sync_products(self.sid, [{"productId": "p1", "상품명": "가"},
                                   {"productId": "p2", "상품명": "나"}])
        m = M.read(self.sid)
        self.assertIn("p1", m)
        self.assertEqual(M.pending(m, "썸네일"), ["p1", "p2"])

        M.mark_many(self.sid, "썸네일", {"p1": M.DONE})
        m2 = M.read(self.sid)
        self.assertEqual(M.pending(m2, "썸네일"), ["p2"])

    def test_재작업_플래그가_pending에_잡힌다(self):
        M.ensure(self.sid)
        M.sync_products(self.sid, [{"productId": "p1", "상품명": "가"}])
        M.mark_many(self.sid, "썸네일", {"p1": M.DONE})
        M.flag(self.sid, "p1", "썸네일", "배경 이상")
        m = M.read(self.sid)
        self.assertIn("p1", M.redo_pending(m, "썸네일"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 원본 모듈 복사**

```bash
SRC=/Users/choiyongsmacbook/Documents/yongtimjang_claudecode/.claude/lib/eroomlib
DST=~/Documents/bulsaja-kit/lib/eroomlib
for f in __init__.py bulsaja.py snapshot.py matrix.py config.py envload.py textnorm.py dedup.py exclusion.py review_page.py; do
  cp "$SRC/$f" "$DST/$f"
done
# gdrive.py, webdriver.py, gsheets.py 는 복사하지 않는다 (각각 드라이브·셀레니움·gws 결합)
```

- [ ] **Step 3: 실패 확인**

Run: `cd ~/Documents/bulsaja-kit && /usr/bin/python3 -m unittest tests.test_gsheets_local -v`
Expected: FAIL — `ImportError: cannot import name 'gsheets'` (복사에서 제외했으므로)

- [ ] **Step 4: 로컬 `gsheets.py` 구현**

`lib/eroomlib/gsheets.py`:

```python
#!/usr/bin/env python3
"""시트 접근 계층 — **배포판은 로컬 JSON 파일에 쓴다.**

원본(용팀장 워크스페이스)은 이 자리에서 `gws` CLI 로 구글시트를 호출한다.
배포판 수강생은 구글 계정·gws 가 없으므로 같은 함수 이름·같은 인자·같은 반환값을
유지한 채 저장 위치만 로컬 파일로 바꾼다. 그 덕분에 `matrix.py` 와 스킬 스크립트를
한 줄도 고치지 않는다.

`spreadsheet_id` 인자는 **로컬 저장소 파일 경로**다(이름은 원본 호환을 위해 유지).
재시도(max_retries)·쿼터 개념은 로컬 파일에 의미가 없어 인자만 받고 무시한다.
"""
from . import localstore as _ls

# 원본 호환 — 호출부가 기본 탭 없이 범위를 주는 경우가 있다
DEFAULT_TAB = "00_진행"


def sheets_get(spreadsheet_id, rng, max_retries=4):
    return _ls.get_values(spreadsheet_id, rng, DEFAULT_TAB)


def sheets_update(spreadsheet_id, rng, values_2d, value_input="RAW", max_retries=4):
    return _ls.set_values(spreadsheet_id, rng, values_2d, DEFAULT_TAB)


def sheets_batch_update(spreadsheet_id, data, value_input="USER_ENTERED",
                        max_retries=4):
    n = 0
    for item in data:
        n += _ls.set_values(spreadsheet_id, item["range"], item["values"],
                            DEFAULT_TAB)
    return n


def append_rows(spreadsheet_id, tab, rows, max_retries=7):
    return _ls.append(spreadsheet_id, tab, rows)


def ensure_tab(spreadsheet_id, tab, header):
    return _ls.ensure_tab(spreadsheet_id, tab, header)


def chunk_by_size(rows, budget=12000):
    """긴 요청을 나누는 원본 로직 — 로컬에서도 동작을 바꾸지 않는다.

    로컬 파일에는 인자 길이 제한이 없지만, 호출부가 청크 단위로 진행 로그를
    찍으므로 동작을 유지한다.
    """
    out, cur, size = [], [], 0
    for r in rows:
        w = sum(len(str(c)) for c in r) + 4
        if cur and size + w > budget:
            out.append(cur)
            cur, size = [], 0
        cur.append(r)
        size += w
    if cur:
        out.append(cur)
    return out
```

- [ ] **Step 5: `matrix.py` 두 곳 수정**

`_insert_header_row` 가 `gsheets._run_gws` 로 시트 API 를 직접 부른다. 로컬로 바꾼다.
원본 `matrix.py:167-186` 의 함수 본문 전체를 아래로 교체:

```python
def _insert_header_row(sheet, tab):
    """맨 위에 헤더 행을 끼워 넣는다 (배포판: 로컬 저장소)."""
    from . import localstore as _ls
    _ls.insert_header_row(sheet, tab, list(HEADER))
```

`index_groups` 는 마스터 인덱스 시트를 읽는다. 배포판은 마스터 시트가 없다.
원본 `matrix.py:471-484` 를 아래로 교체:

```python
def index_groups(master_sheet=None):
    """배포판: 마스터 인덱스 시트가 없다. 로컬 runs 폴더에서 그룹을 찾는다.

    반환: [(그룹명, 저장소경로)] — 원본과 같은 모양이라 호출부를 고치지 않는다.
    """
    from .config import runs_root
    root = runs_root()
    out = []
    if not os.path.isdir(root):
        return out
    for name in sorted(os.listdir(root)):
        p = os.path.join(root, name, "board.json")
        if os.path.exists(p):
            out.append((name, p))
    return out
```

`sync_all` 과 `rebuild` 는 마스터 시트·원장 탭에 의존하므로 배포판에서 쓰지 않는다.
호출되면 명확히 알리도록 `sync_all` 본문 첫 줄에 추가:

```python
    raise RuntimeError("배포판에는 마스터 인덱스 시트가 없어 sync_all 을 쓰지 않습니다.")
```

- [ ] **Step 6: `config.py` 배포판 기본값으로 교체**

`config.py` 의 `DEFAULTS` 를 개인 경로(`D:\python_work` 등)에서 수강생 홈 기준으로 바꾸고, 두 헬퍼를 추가한다. 파일 끝에 추가:

```python
def runs_root():
    """작업 결과 루트 — 기본 `~/bulsaja-kit/runs`. 환경변수로 바꿀 수 있다."""
    return os.environ.get(
        "BULSAJA_KIT_RUNS",
        os.path.join(os.path.expanduser("~"), "bulsaja-kit", "runs"))


def store_for_group(group_name):
    """마켓그룹명 → 그 그룹의 로컬 저장소 파일 경로. 없으면 폴더를 만든다."""
    d = os.path.join(runs_root(), group_name)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "board.json")


def data_root():
    """snapshot 캐시 루트 — 기본 `~/bulsaja-kit`."""
    return os.environ.get(
        "BULSAJA_KIT_HOME",
        os.path.join(os.path.expanduser("~"), "bulsaja-kit"))
```

`DEFAULTS` 딕셔너리에서 개인 경로·시트 ID·드라이브 folderId·계정 주소를 **전부 빈 문자열로** 바꾼다.

- [ ] **Step 7: `bulsaja.py` · `snapshot.py` import 교체**

`bulsaja.py` 의 `import requests` 를:

```python
try:
    import requests  # 있으면 쓴다
except ImportError:  # 배포판 기본 경로 — 표준 라이브러리 셔임
    from . import _http as requests
```

`snapshot.py` 의 `import requests` 도 같은 형태로 바꾼다. `snapshot.root()` 가
개인 경로를 반환하면 `config.data_root()` 를 쓰도록 바꾼다.

- [ ] **Step 8: 테스트 통과 확인**

Run: `cd ~/Documents/bulsaja-kit && /usr/bin/python3 -m unittest discover -s tests -v`
Expected: PASS — Task 1·2·3·4 테스트 전부

- [ ] **Step 9: 커밋**

```bash
cd ~/Documents/bulsaja-kit
git add lib tests
git commit -m "eroomlib 이식 — 시트 접근을 로컬 저장소로 교체"
```

---

### Task 5: 썸네일 스킬 이식

**Files:**
- Copy: 원본 `bulsaja-thumbnail/{SKILL.md,references/,scripts/}` → `skills/bulsaja-thumbnail/`
- Modify: `skills/bulsaja-thumbnail/SKILL.md` (팬아웃 절 삭제, `_shared` 참조 해소, 인명 제거, 대상 선정 설명 교체)
- Modify: `skills/bulsaja-thumbnail/scripts/run_thumbs.py` (라이브러리 경로 해석, 대상 선정)
- Test: `skills/bulsaja-thumbnail/scripts/test_thumb_rules.py` 등 원본 테스트 4종 그대로 통과

**Interfaces:**
- Consumes: `eroomlib.matrix`, `eroomlib.snapshot`, `eroomlib.config.store_for_group` (Task 4)
- Produces: `python skills/bulsaja-thumbnail/scripts/run_thumbs.py {prep,run,audit,apply} --group <마켓그룹명>`

**대상 선정 변경 (스펙 §6.1):** 원본 `run_thumbs.py:230-233` 의 `matrix.index_groups()` 로 그룹→시트 해석하던 부분을 `config.store_for_group(그룹명)` 으로 바꾸고, 최초 실행 시 `matrix.ensure()` + `matrix.sync_products()` 로 board 를 만든 뒤 대표이미지 URL 이 `cdn.bulsaja.com` 인 상품을 `matrix.mark_many(..., DONE)` 처리한다. 그 이후 로직은 원본 그대로 `matrix.pending()` 이 대상을 뽑는다.

- [ ] **Step 1: 원본 복사 (`__pycache__` 제외)**

```bash
SRC=/Users/choiyongsmacbook/Documents/yongtimjang_claudecode/.claude/skills/bulsaja-thumbnail
DST=~/Documents/bulsaja-kit/skills/bulsaja-thumbnail
rm -f $DST/SKILL.md
mkdir -p $DST
rsync -a --exclude='__pycache__' "$SRC/" "$DST/"
```

- [ ] **Step 2: 원본 테스트가 배포판에서 도는지 먼저 확인**

이 테스트들은 불사자·시트 없이 도는 순수 로직 테스트다. 이식이 로직을 깨지 않았다는 회귀 방어선이다.

Run:
```bash
cd ~/Documents/bulsaja-kit/skills/bulsaja-thumbnail/scripts
/usr/bin/python3 -m unittest test_thumb_rules test_thumb_prep test_thumb_prescreen test_review_html -v
```
Expected: 라이브러리 경로 문제로 일부 FAIL → Step 3 에서 해결

- [ ] **Step 3: 라이브러리 경로 해석 수정**

원본 `run_thumbs.py:55-70` 은 `.claude/lib` 를 워크스페이스 앵커로 찾는다. 배포판은 플러그인 안에 있다. 그 블록을 아래로 교체:

```python
# eroomlib 위치: 이 파일 기준 ../../../lib  (플러그인 루트/lib)
_here = os.path.dirname(os.path.abspath(__file__))
_lib = os.path.abspath(os.path.join(_here, "..", "..", "..", "lib"))
if os.path.isdir(os.path.join(_lib, "eroomlib")) and _lib not in sys.path:
    sys.path.insert(0, _lib)
```

- [ ] **Step 4: 그룹 해석을 로컬로 교체**

`run_thumbs.py` 에서 `matrix.index_groups()` 로 그룹명→시트를 찾는 부분(원본 230-233행 부근)을 교체:

```python
def _resolve_group(name):
    """마켓그룹명 → (그룹명, 로컬 저장소 경로). 배포판은 마스터 시트가 없다."""
    from eroomlib.config import store_for_group
    return name, store_for_group(name)
```

호출부에서 `sheet` 변수에 이 반환값의 두 번째 원소를 넣는다. 이후 `matrix.*` 호출은 전부 원본 그대로 동작한다.

- [ ] **Step 5: 최초 실행 시 board 자동 생성 + 기가공 자동 완료**

`prep` 진입부에 추가 (원본의 현황판 조회 자리):

```python
def _bootstrap_board(sheet, group_name):
    """board 가 없으면 그룹 상품으로 만들고, 이미 가공된 상품은 완료 처리한다.

    원본은 이 정보를 구글시트 현황판에서 읽었다. 배포판은 불사자에서 직접 읽어
    같은 모양의 board 를 만든다 — 이후 대상 선정 로직은 원본과 동일하다.
    """
    from eroomlib import matrix
    from eroomlib.matrix import _group_products
    matrix.ensure(sheet)
    products = _group_products(group_name)
    matrix.sync_products(sheet, products)
    already = {}
    for p in products:
        url = str(p.get("대표이미지") or p.get("썸네일") or "")
        if "cdn.bulsaja.com" in url:
            already[p["productId"]] = matrix.DONE
    if already:
        matrix.mark_many(sheet, "썸네일", already)
        print("  이미 가공된 상품 %d건 완료 처리" % len(already))
    return products
```

- [ ] **Step 6: SKILL.md 개조**

다음을 수행한다:
1. 팬아웃 관련 절 전체 삭제 (`_shared/스킬-계약.md §팬아웃 공통 규약` 참조부, Workflow 모드 지시)
2. `_shared/스킬-계약.md`·`_shared/불사자-안전규칙.md` 참조를 제거하고, 그 문서에서 실제로 필요한 규칙(반영은 기본 자동 · 실패 보존 · 이미지 해상도 512)을 SKILL.md 본문에 직접 서술
3. "현황판" 을 "진행상황 파일(board.json)" 로, "그룹 시트 `썸네일` 탭" 을 "결과 파일(ledger)" 로 표현 교체
4. "이룸님" 표기 전부 제거. 결정 근거는 남기되 인명 없이 서술
5. frontmatter `description` 을 수강생 트리거에 맞게 재작성
6. 문서 끝에 결과 확인 안내 추가 — `~/bulsaja-kit/runs/<그룹명>/review.html`

- [ ] **Step 7: 원본 테스트 전수 통과 확인**

Run:
```bash
cd ~/Documents/bulsaja-kit/skills/bulsaja-thumbnail/scripts
/usr/bin/python3 -m unittest test_thumb_rules test_thumb_prep test_thumb_prescreen test_review_html -v
```
Expected: PASS — 원본과 같은 테스트 수

- [ ] **Step 8: 커밋**

```bash
cd ~/Documents/bulsaja-kit
git add skills/bulsaja-thumbnail
git commit -m "썸네일 스킬 이식 — 시트 의존 제거, 마켓그룹 스캔으로 대상 선정"
```

---

### Task 6: 배송비 스킬 이식 + 요율 외부화

**Files:**
- Copy: worktree `bulsaja-shipping-fee/{SKILL.md,references/,scripts/}` → `skills/bulsaja-shipping-fee/`
- Delete: `scripts/fetch_oc_actuals.py`, `scripts/fetch_kd_table.py`, `references/오픈차이나-실측.json`
- Create: `config/shipfee.ini`
- Modify: `scripts/shipfee_rules.py` (요율을 ini 에서 읽기), `scripts/run_shipfee.py` (경로·그룹 해석)
- Test: `skills/bulsaja-shipping-fee/scripts/test_shipfee_rules.py` 그대로 통과 + `tests/test_shipfee_config.py` 신규

**Interfaces:**
- Consumes: Task 4 의 `eroomlib`, Task 5 와 동일한 경로 해석 패턴
- Produces: `python skills/bulsaja-shipping-fee/scripts/run_shipfee.py {prep,apply} --group <마켓그룹명>`
- Produces: `shipfee_rules.load_rates() -> dict` — 키 `기본요금`(int), `추가요금`(int), `포장비`(dict: 낮음/중간/높음 → float)

**`references/오픈차이나-실측.json` 삭제 이유:** 용팀장의 실제 결제 내역이다. 요율은 이미 `shipfee.ini` 로 추출되므로 원본 거래 기록을 공개 저장소에 올릴 이유가 없다.

- [ ] **Step 1: 요율 로더 실패 테스트 작성**

`tests/test_shipfee_config.py`:

```python
"""배송비 요율 외부화 — ini 를 읽고, 없으면 기본값으로 도는지."""
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "lib"))
sys.path.insert(0, os.path.join(ROOT, "skills", "bulsaja-shipping-fee", "scripts"))

import shipfee_rules as R  # noqa: E402


class TestRates(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self._old = os.environ.get("BULSAJA_KIT_SHIPFEE_INI")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)
        if self._old is None:
            os.environ.pop("BULSAJA_KIT_SHIPFEE_INI", None)
        else:
            os.environ["BULSAJA_KIT_SHIPFEE_INI"] = self._old

    def test_동봉된_기본_ini를_읽는다(self):
        os.environ.pop("BULSAJA_KIT_SHIPFEE_INI", None)
        r = R.load_rates()
        self.assertEqual(r["기본요금"], 5500)
        self.assertEqual(r["추가요금"], 750)
        self.assertAlmostEqual(r["포장비"]["중간"], 1.19, places=2)

    def test_수강생이_고친_값이_반영된다(self):
        p = os.path.join(self.dir, "my.ini")
        with open(p, "w", encoding="utf-8") as f:
            f.write("[요율]\n기본요금 = 6000\n추가요금 = 900\n")
        os.environ["BULSAJA_KIT_SHIPFEE_INI"] = p
        r = R.load_rates()
        self.assertEqual(r["기본요금"], 6000)
        self.assertEqual(r["추가요금"], 900)

    def test_ini가_없어도_기본값으로_돈다(self):
        os.environ["BULSAJA_KIT_SHIPFEE_INI"] = os.path.join(self.dir, "none.ini")
        r = R.load_rates()
        self.assertEqual(r["기본요금"], 5500)

    def test_일부만_적힌_ini는_나머지를_기본값으로_채운다(self):
        p = os.path.join(self.dir, "partial.ini")
        with open(p, "w", encoding="utf-8") as f:
            f.write("[요율]\n기본요금 = 7000\n")
        os.environ["BULSAJA_KIT_SHIPFEE_INI"] = p
        r = R.load_rates()
        self.assertEqual(r["기본요금"], 7000)
        self.assertEqual(r["추가요금"], 750)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 원본 복사 후 개인 결합 파일 삭제**

```bash
SRC=/Users/choiyongsmacbook/Documents/yongtimjang_claudecode/.claude/worktrees/shipfee-skill-install/.claude/skills/bulsaja-shipping-fee
DST=~/Documents/bulsaja-kit/skills/bulsaja-shipping-fee
rm -f $DST/SKILL.md
rsync -a --exclude='__pycache__' "$SRC/" "$DST/"
rm -f "$DST/scripts/fetch_oc_actuals.py" "$DST/scripts/fetch_kd_table.py"
rm -f "$DST/references/오픈차이나-실측.json"
```

- [ ] **Step 3: 실패 확인**

Run: `cd ~/Documents/bulsaja-kit && /usr/bin/python3 -m unittest tests.test_shipfee_config -v`
Expected: FAIL — `AttributeError: module 'shipfee_rules' has no attribute 'load_rates'`

- [ ] **Step 4: `config/shipfee.ini` 작성**

```ini
; 배송비 요율 설정
; 다른 배대지를 쓴다면 아래 두 줄만 고치면 됩니다.

[요율]
; 0.5kg 기준 기본요금 (원)
기본요금 = 5500
; 0.5kg 추가될 때마다 붙는 금액 (원)
추가요금 = 750

[포장비]
; 파손위험별 배율 — 요율에 곱합니다
낮음 = 1.05
중간 = 1.19
높음 = 1.42
```

- [ ] **Step 5: `shipfee_rules.py` 에 로더 추가**

파일 상단 상수 정의부(원본 19-49행 부근) 아래에 추가하고, 기존 하드코딩 상수를 이 함수 결과로 대체:

```python
import configparser

_DEFAULT_RATES = {
    "기본요금": 5500,
    "추가요금": 750,
    "포장비": {"낮음": 1.05, "중간": 1.19, "높음": 1.42},
}


def _ini_path():
    p = os.environ.get("BULSAJA_KIT_SHIPFEE_INI")
    if p:
        return p
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, "..", "..", "..", "config", "shipfee.ini"))


def load_rates():
    """요율 설정을 읽는다. 파일이 없거나 항목이 빠져도 기본값으로 채운다.

    수강생이 다른 배대지를 쓰면 config/shipfee.ini 를 고치면 된다.
    """
    rates = {
        "기본요금": _DEFAULT_RATES["기본요금"],
        "추가요금": _DEFAULT_RATES["추가요금"],
        "포장비": dict(_DEFAULT_RATES["포장비"]),
    }
    path = _ini_path()
    if not os.path.exists(path):
        return rates
    cp = configparser.ConfigParser()
    cp.read(path, encoding="utf-8")
    if cp.has_section("요율"):
        for key in ("기본요금", "추가요금"):
            if cp.has_option("요율", key):
                try:
                    rates[key] = int(cp.get("요율", key).split(";")[0].strip())
                except ValueError:
                    pass
    if cp.has_section("포장비"):
        for key in ("낮음", "중간", "높음"):
            if cp.has_option("포장비", key):
                try:
                    rates["포장비"][key] = float(cp.get("포장비", key).split(";")[0].strip())
                except ValueError:
                    pass
    return rates
```

`import os` 가 없으면 추가한다.

- [ ] **Step 6: 테스트 통과 확인**

Run: `cd ~/Documents/bulsaja-kit && /usr/bin/python3 -m unittest tests.test_shipfee_config -v`
Expected: PASS (4 tests)

- [ ] **Step 7: 원본 배송비 로직 테스트 통과 확인**

Run:
```bash
cd ~/Documents/bulsaja-kit/skills/bulsaja-shipping-fee/scripts
/usr/bin/python3 -m unittest test_shipfee_rules -v
```
Expected: PASS — 원본과 같은 테스트 수. 실패하면 `load_rates()` 도입이 기존 상수 동작을 바꾼 것이므로 되돌린다

- [ ] **Step 8: `run_shipfee.py` 경로·그룹 해석 수정**

Task 5 Step 3·4 와 동일한 패턴을 적용한다. `eroomlib` 경로는 `../../../lib`, 그룹 해석은 `config.store_for_group(name)`.

`_log_sheet` 계열이 쓰던 그룹 시트 `배송비` 탭은 `ledger.json` 으로 그대로 간다(gsheets 백엔드가 이미 로컬이므로 코드 변경 불필요).

- [ ] **Step 9: SKILL.md 개조**

Task 5 Step 6 과 동일한 6개 항목을 수행한다. 추가로:
- 오픈차이나 실측 수집 절차를 설명하는 절 삭제
- 경동비에 대해 "참고용 — 불사자에 저장되지 않습니다" 를 명시
- 요율을 바꾸려면 `config/shipfee.ini` 를 고치라는 안내 추가

- [ ] **Step 10: 커밋**

```bash
cd ~/Documents/bulsaja-kit
git add skills/bulsaja-shipping-fee config/shipfee.ini tests/test_shipfee_config.py
git commit -m "배송비 스킬 이식 — 오픈차이나 결합 제거, 요율 설정파일 분리"
```

---

### Task 7: 설치 진단 `doctor.py`

**Files:**
- Create: `~/Documents/bulsaja-kit/scripts/doctor.py`
- Test: `~/Documents/bulsaja-kit/tests/test_doctor.py`

**Interfaces:**
- Consumes: `eroomlib.bulsaja.load_config`, `eroomlib.snapshot.ProductMCP`
- Produces: `def checks() -> list[dict]` — 각 항목 `{"이름": str, "통과": bool, "메시지": str, "조치": str}`
- Produces: CLI `python scripts/doctor.py` — 사람이 읽는 표 출력, 전부 통과 시 종료코드 0

**보안 요구:** 토큰 값을 절대 출력하지 않는다. 존재 여부와 계정명만 보고한다.

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_doctor.py`:

```python
"""설치 진단 — 항목 구조와 토큰 비노출을 검증한다."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "lib"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import doctor  # noqa: E402


class TestDoctor(unittest.TestCase):
    def test_항목이_필수키를_갖는다(self):
        for c in doctor.checks():
            for k in ("이름", "통과", "메시지", "조치"):
                self.assertIn(k, c, "%r 에 %s 없음" % (c.get("이름"), k))

    def test_파이썬_버전_점검이_포함된다(self):
        names = [c["이름"] for c in doctor.checks()]
        self.assertIn("파이썬", names)

    def test_불사자_MCP_점검이_포함된다(self):
        names = [c["이름"] for c in doctor.checks()]
        self.assertTrue(any("불사자" in n for n in names))

    def test_어떤_메시지에도_Bearer_토큰이_없다(self):
        for c in doctor.checks():
            blob = c["메시지"] + c["조치"]
            self.assertNotIn("Bearer ", blob)
            self.assertNotIn("gho_", blob)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패 확인**

Run: `cd ~/Documents/bulsaja-kit && /usr/bin/python3 -m unittest tests.test_doctor -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'doctor'`

- [ ] **Step 3: 구현**

`scripts/doctor.py` — 스펙 §8 의 7개 항목을 구현한다. 각 점검은 실패해도 다음 항목을 계속 진행한다(하나 막혔다고 나머지를 못 보면 진단의 의미가 없다).

점검 목록과 실패 시 `조치` 문구:

| 이름 | 통과 조건 | 조치 |
|---|---|---|
| 파이썬 | `sys.version_info >= (3, 8)` | "파이썬 3.8 이상이 필요합니다. python.org 에서 설치하세요." |
| 표준 라이브러리 | `_http` import 성공 | "플러그인이 손상됐습니다. `/plugin update bulsaja-kit` 를 실행하세요." |
| 불사자 MCP 설정 | `~/.claude.json` 에 `mcpServers.bulsaja` 존재 | "불사자 MCP 가 등록돼 있지 않습니다. 불사자 사이트에서 MCP 연결을 먼저 하세요." |
| 불사자 연결 | `ProductMCP().open()` 성공 | "불사자에 연결하지 못했습니다. 토큰이 만료됐을 수 있으니 MCP 를 다시 연결하세요." |
| 불사자 계정 | `bulsaja_my_profile` 호출 성공 | (통과 시 계정명 표시) |
| AI 크레딧 | `bulsaja_ai_credit_balance` 조회, 잔액 > 0 | "크레딧이 없습니다. 불사자에서 충전 후 다시 시도하세요." |
| 저장 폴더 | `config.runs_root()` 에 쓰기 가능 | "홈 폴더에 쓸 수 없습니다. 환경변수 BULSAJA_KIT_RUNS 로 경로를 바꾸세요." |

출력 형식:

```
불사자 키트 설치 점검
─────────────────────────────
 ✅ 파이썬            3.12.4
 ✅ 표준 라이브러리    정상
 ✅ 불사자 MCP 설정    등록됨
 ✅ 불사자 연결        정상
 ✅ 불사자 계정        hong@naver.com
 ✅ AI 크레딧          1,240
 ✅ 저장 폴더          ~/bulsaja-kit/runs
─────────────────────────────
준비 완료. 마켓그룹 이름을 말하면 시작합니다.
```

실패 항목이 있으면 `❌` 와 함께 `조치` 를 출력하고 종료코드 1.

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd ~/Documents/bulsaja-kit && /usr/bin/python3 -m unittest tests.test_doctor -v`
Expected: PASS (4 tests)

- [ ] **Step 5: 실제 실행 확인**

Run: `cd ~/Documents/bulsaja-kit && /usr/bin/python3 scripts/doctor.py`
Expected: 표가 출력된다. 이 맥에는 불사자 MCP 가 있으므로 대부분 통과해야 한다

- [ ] **Step 6: 커밋**

```bash
cd ~/Documents/bulsaja-kit
git add scripts/doctor.py tests/test_doctor.py
git commit -m "설치 진단 스크립트 추가"
```

---

### Task 8: README + 진단 스킬 연결

**Files:**
- Create: `~/Documents/bulsaja-kit/README.md`
- Create: `~/Documents/bulsaja-kit/skills/bulsaja-kit-doctor/SKILL.md`
- Modify: `tests/test_manifest.py` (스킬 3개로)

**Interfaces:**
- Produces: `"설치 점검해줘"` 트리거로 `scripts/doctor.py` 를 실행하는 스킬

**README 구성** (수강생이 이미 Claude Code·불사자 MCP 를 쓰고 있다는 전제 — 스펙 §3):
1. 이게 뭔가 (2줄)
2. 설치 — 명령 2줄
3. 설치 확인 — `"설치 점검해줘"`
4. 쓰는 법 — 썸네일 / 배송비 각각 한 문장 예시
5. 결과 보는 곳 — `~/bulsaja-kit/runs/<그룹명>/`
6. 배송비 요율 바꾸기 — `config/shipfee.ini`
7. 자주 막히는 것 3가지 (파이썬 없음 / 크레딧 0 / 토큰 만료)
8. 주의 — 자동 반영된다, 실습은 20~30건씩

- [ ] **Step 1: 진단 스킬 작성**

`skills/bulsaja-kit-doctor/SKILL.md`:

```markdown
---
name: bulsaja-kit-doctor
description: 불사자 키트가 제대로 설치됐는지 점검한다. 파이썬·불사자 MCP 연결·계정·AI 크레딧·저장 폴더를 확인하고, 막힌 곳이 있으면 무엇을 해야 하는지 알려준다. "설치 점검해줘", "불사자 키트 확인", "잘 깔렸나 확인해줘", "준비됐는지 봐줘" 를 언급하면 자동 실행.
---

# 불사자 키트 설치 점검

아래를 실행하고, 출력된 표를 사용자에게 **그대로** 보여준다.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py"
```

`python3` 이 없으면 `python` 으로 한 번 더 시도한다.

## 결과 해석

- 전부 ✅ → "준비 완료" 를 전하고, 마켓그룹 이름을 물어본다
- ❌ 가 있으면 → 그 항목의 `조치` 문구를 그대로 안내한다. 여러 개면 위에서부터 하나씩
- 스크립트 자체가 실행되지 않으면 → 파이썬 미설치일 가능성이 높다. 맥은 `brew install python3`, 윈도우는 python.org 설치를 안내한다

## 하지 말 것

- 토큰 값을 출력하거나 사용자에게 묻지 않는다
- 점검이 실패했는데 작업을 그대로 진행하지 않는다
```

- [ ] **Step 2: `tests/test_manifest.py` 의 스킬 목록에 `bulsaja-kit-doctor` 추가**

```python
        for name in ("bulsaja-thumbnail", "bulsaja-shipping-fee", "bulsaja-kit-doctor"):
```

- [ ] **Step 3: README 작성**

위 8개 절을 수강생 눈높이로 작성한다. 개발자 용어(import, 백엔드, 어댑터)를 쓰지 않는다.

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd ~/Documents/bulsaja-kit && /usr/bin/python3 -m unittest discover -s tests -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
cd ~/Documents/bulsaja-kit
git add README.md skills/bulsaja-kit-doctor tests/test_manifest.py
git commit -m "README 와 설치 점검 스킬 추가"
```

---

### Task 9: 개인정보 정화 검증

**Files:**
- Create: `~/Documents/bulsaja-kit/tests/test_sanitized.py`

**Interfaces:**
- Produces: 저장소 전체를 훑어 금지 패턴이 0건인지 검증하는 테스트. **푸시 전 마지막 관문**

**이 테스트는 반드시 통과해야 푸시한다.** 스펙 §9 의 체크리스트를 자동화한 것이다.

- [ ] **Step 1: 테스트 작성**

`tests/test_sanitized.py`:

```python
"""배포 전 정화 검증 — 개인정보·개인 인프라 결합이 남아 있는지 전수 검사.

이 테스트가 실패하면 절대 푸시하지 않는다.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SKIP_DIRS = {".git", "__pycache__", ".venv", "runs", "products", "node_modules"}
SKIP_FILES = {"test_sanitized.py"}

# (패턴, 설명) — 대소문자 무시
FORBIDDEN = [
    (r"이룸", "인명"),
    (r"용팀장", "인명"),
    (r"용쌤", "인명"),
    (r"OPENCHINA", "오픈차이나 자격증명"),
    (r"오픈차이나", "오픈차이나 결합"),
    (r"openchina\.co\.kr", "오픈차이나 URL"),
    (r"_run_gws", "gws CLI 호출"),
    (r"gws\s+sheets", "gws CLI 호출"),
    (r"1[A-Za-z0-9_-]{40,}", "구글 스프레드시트/드라이브 ID로 보이는 문자열"),
    (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.(?:com|net|kr|org)", "이메일 주소"),
    (r"D:\\+python_work", "개인 절대경로"),
    (r"/Users/choiyongsmacbook", "개인 절대경로"),
    (r"gho_[A-Za-z0-9]+", "깃허브 토큰"),
    (r"Bearer\s+[A-Za-z0-9._-]{20,}", "하드코딩된 토큰"),
]

TEXT_EXT = {".md", ".py", ".json", ".ini", ".txt", ".js", ".html", ".yml", ".yaml"}


def _files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn in SKIP_FILES:
                continue
            if os.path.splitext(fn)[1].lower() in TEXT_EXT:
                yield os.path.join(dirpath, fn)


class TestSanitized(unittest.TestCase):
    def test_금지패턴이_하나도_없다(self):
        hits = []
        for path in _files():
            try:
                with open(path, encoding="utf-8") as f:
                    lines = f.readlines()
            except (UnicodeDecodeError, OSError):
                continue
            rel = os.path.relpath(path, ROOT)
            for i, line in enumerate(lines, 1):
                for pat, why in FORBIDDEN:
                    if re.search(pat, line, re.IGNORECASE):
                        hits.append("%s:%d [%s] %s" % (rel, i, why, line.strip()[:110]))
        self.assertEqual(hits, [], "정화되지 않은 내용 %d건:\n%s"
                         % (len(hits), "\n".join(hits[:40])))

    def test_env_파일이_없다(self):
        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            self.assertNotIn(".env", filenames, "%s 에 .env 가 있다" % dirpath)

    def test_오픈차이나_수집_스크립트가_없다(self):
        for name in ("fetch_oc_actuals.py", "fetch_kd_table.py"):
            for dirpath, dirnames, filenames in os.walk(ROOT):
                dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
                self.assertNotIn(name, filenames, "%s 가 남아 있다" % name)

    def test_실측_원본_json이_없다(self):
        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in filenames:
                self.assertNotIn("오픈차이나", fn, "%s 가 남아 있다" % fn)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실행하고 걸리는 것 전부 수정**

Run: `cd ~/Documents/bulsaja-kit && /usr/bin/python3 -m unittest tests.test_sanitized -v`

걸린 항목을 하나씩 고친다. 원칙:
- 인명 → 삭제하거나 "운영 판단(2026-08)" 같은 중립 표현으로
- 개인 경로 → 상대경로 또는 `~/bulsaja-kit`
- gws 흔적 → 로컬 저장소 표현으로
- 스프레드시트 ID → 삭제

**주의:** 정화 때문에 판정 기준의 **내용**을 바꾸지 않는다. 표기만 바꾼다.

- [ ] **Step 3: 통과 확인**

Run: `cd ~/Documents/bulsaja-kit && /usr/bin/python3 -m unittest tests.test_sanitized -v`
Expected: PASS (4 tests)

- [ ] **Step 4: 전체 테스트 재확인**

Run:
```bash
cd ~/Documents/bulsaja-kit && /usr/bin/python3 -m unittest discover -s tests -v
cd ~/Documents/bulsaja-kit/skills/bulsaja-thumbnail/scripts && /usr/bin/python3 -m unittest discover -p 'test_*.py' -v
cd ~/Documents/bulsaja-kit/skills/bulsaja-shipping-fee/scripts && /usr/bin/python3 -m unittest discover -p 'test_*.py' -v
```
Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
cd ~/Documents/bulsaja-kit
git add -A
git commit -m "개인정보 정화 검증 추가 및 정화 반영"
```

---

### Task 10: 설치 리허설과 배포

**Files:** 없음 (검증·배포만)

**이 태스크를 건너뛰면 강의 당일 현장에서 실패한다.** (스펙 §10)

- [ ] **Step 1: 로컬 마켓플레이스로 설치 리허설**

Claude Code 는 로컬 경로도 마켓플레이스로 받는다. GitHub 에 올리기 전에 구조를 검증한다.

```
/plugin marketplace add /Users/choiyongsmacbook/Documents/bulsaja-kit
/plugin install bulsaja-kit@bulsaja-kit
```

설치 후 확인:
- 스킬 3개(`bulsaja-thumbnail`, `bulsaja-shipping-fee`, `bulsaja-kit-doctor`)가 스킬 목록에 뜨는가
- `"설치 점검해줘"` 로 doctor 가 실행되는가

- [ ] **Step 2: 실제 소량 작업 완주**

실제 마켓그룹에서 **3~5건**으로 썸네일 `prep` 까지 돌려, board 가 만들어지고 대상이 잡히는지 확인한다.

```bash
cd ~/Documents/bulsaja-kit
/usr/bin/python3 skills/bulsaja-thumbnail/scripts/run_thumbs.py prep --group <실제그룹명> --limit 3
```

확인: `~/bulsaja-kit/runs/<그룹명>/board.json` 이 생기고 대상이 잡혔는가.

**크레딧을 쓰는 생성 단계(`run`)는 리허설에서 돌리지 않는다.** 구조 검증이 목적이다.

- [ ] **Step 3: 리허설 흔적 정리**

```bash
/plugin uninstall bulsaja-kit
/plugin marketplace remove bulsaja-kit
rm -rf ~/bulsaja-kit/runs/<그룹명>
```

- [ ] **Step 4: 정화 테스트 최종 재확인**

Run: `cd ~/Documents/bulsaja-kit && /usr/bin/python3 -m unittest tests.test_sanitized -v`
Expected: PASS

**여기서 실패하면 푸시하지 않는다.**

- [ ] **Step 5: GitHub 공개 저장소 생성 및 푸시**

```bash
cd ~/Documents/bulsaja-kit
gh repo create bulsaja-kit --public \
  --description "불사자 셀러 자동화 스킬 모음 — 썸네일 생성, 배송비 계산" \
  --source . --remote origin --push
```

- [ ] **Step 6: 공개 상태에서 설치 재확인**

```
/plugin marketplace add cy728728-a11y/bulsaja-kit
/plugin install bulsaja-kit@bulsaja-kit
```

README 에 적힌 명령과 **글자 하나까지 같은지** 확인하고, 다르면 README 를 고쳐 다시 푸시한다.

- [ ] **Step 7: 최종 보고**

수강생에게 공지할 문구를 정리해 남긴다:
- 설치 명령 2줄
- 첫 실행 시 `"설치 점검해줘"`
- 실습은 20~30건씩

---

## Self-Review

**스펙 커버리지**

| 스펙 절 | 태스크 |
|---|---|
| §4 어댑터 교체 | Task 3, 4 |
| §5 저장소 구조 | Task 1, 4, 8 |
| §6.1 썸네일 개조 | Task 5 |
| §6.2 배송비 개조 | Task 6 |
| §7 안전선(자동 반영 유지) | Task 5 Step 6 (SKILL.md 에서 원본 동작 유지) |
| §8 진단 | Task 7, 8 |
| §9 정화 체크리스트 | Task 9 |
| §10 검증 절차 | Task 5 Step 7, Task 6 Step 7, Task 9 Step 4, Task 10 |
| §11 강의 운영 메모 | Task 8 README |
| §13 미해결(shipfee 소스) | Task 6 Step 2 에서 worktree 를 읽기 전용 소스로 확정 |

**추가된 항목 (스펙 작성 후 발견)**

- `requests` 의존 제거 (Task 2) — 맥 시스템 파이썬 3.9.6 에 `requests` 가 없음을 확인. 스펙 §8 은 `pip install requests` 안내로 처리하려 했으나, 의존 자체를 없애는 편이 수강생 실패 지점을 하나 줄인다
- `gdrive.py` · `webdriver.py` 이식 제외 (Task 4 Step 2) — 배포판이 쓰지 않으며 각각 구글드라이브·셀레니움 결합을 끌고 온다
- `references/오픈차이나-실측.json` 삭제 (Task 6) — 실제 결제 내역이라 공개 저장소에 부적합. 요율은 이미 ini 로 추출됨

**타입 일관성 확인**

- `localstore.parse_range` 반환 5-튜플 → `get_values`/`set_values` 에서 동일하게 언팩 ✅
- `gsheets.*` 시그니처가 원본과 일치 (`sheets_get(id, rng, max_retries=4)` 등) ✅
- `matrix.index_groups` 반환 `[(그룹명, 경로)]` — 원본 `[(그룹명, spreadsheetId)]` 와 같은 모양 ✅
- `config.store_for_group(name) -> str` 이 Task 5·6 양쪽에서 같은 이름으로 쓰임 ✅
- `shipfee_rules.load_rates()` 반환 키(`기본요금`/`추가요금`/`포장비`)가 Task 6 테스트와 일치 ✅
