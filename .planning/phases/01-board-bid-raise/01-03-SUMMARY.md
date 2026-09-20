---
phase: 01-board-bid-raise
plan: 03
subsystem: security-shell
tags: [fastapi, starlette, trustedhost, csrf, boot-token, jinja2, htmx, uvicorn, tdd]

# Dependency graph
requires:
  - "01-01: webapp/settings.py(PORT) · webapp/paths.py(scan_run_dirs·freshness) · conftest.client 픽스처 · static/vendor 5종 · no_commit_guard.sh"
provides:
  - "webapp/security.py — BOOT_TOKEN · COOKIE_NAME · HEADER_NAME · SAFE_METHODS · allowed_origins() · guard() · page_cookie_ok() · register_secret() · scrub()"
  - "webapp/main.py — app(FastAPI) · templates(Jinja2Templates) · BASE · lifespan(기동 안내 URL)"
  - "webapp/routes/health.py — GET /healthz (토큰 불필요, 읽기 전용)"
  - "webapp/routes/board.py — GET / (?t= → 쿠키 303 교환, 쿠키 없으면 403)"
  - "webapp/routes/jobs.py — 빈 router + '작업 생성은 전부 POST' 규칙"
  - "webapp/templates/board.html — hx-headers 로 X-CT-Token 을 심는 셸 + partial 2개 include"
  - "webapp/run-webapp.sh — 127.0.0.1 · --workers 1 고정 기동"
  - "webapp/tests/test_security.py — 12개 · webapp/tests/test_boot_log.py — 2개 · webapp/tests/security_curl.sh — 8종"
  - "settings.PORT 가 CT_PORT 환경변수를 우선 반영 (바인드 포트 = Origin 화이트리스트 = 안내 URL)"
affects: [01-04, 01-05, 01-06, 01-07, 01-08, 01-09]

# Tech tracking
tech-stack:
  added: [httpx==0.28.1]
  patterns:
    - "쿠키 = 페이지 접근 / 커스텀 헤더 = 쓰기 인가 (역할 분리가 CSRF 방어의 핵심)"
    - "쓰기 메서드 전용 가드 — 상태를 바꾸는 GET 을 만들지 않는 것이 전제이고, 그 전제를 스캐너가 감시한다"
    - "라우터 → main.templates 는 핸들러 안에서 지연 import (paths→settings 선례 계승)"
    - "인터페이스 우선 순서 — 빈 라우터·빈 partial 을 먼저 파서 후속 플랜이 main.py 를 다시 안 건드린다"
    - "장시간 프로세스의 줄 출력은 flush=True — tty 가 아니면 버퍼가 영영 안 비워진다"

key-files:
  created:
    - webapp/security.py
    - webapp/main.py
    - webapp/routes/__init__.py
    - webapp/routes/health.py
    - webapp/routes/board.py
    - webapp/routes/jobs.py
    - webapp/templates/board.html
    - webapp/templates/_job_panel.html
    - webapp/templates/_preview_table.html
    - webapp/run-webapp.sh
    - webapp/tests/test_security.py
    - webapp/tests/test_boot_log.py
    - webapp/tests/security_curl.sh
  modified:
    - webapp/settings.py

key-decisions:
  - "openapi_url=None 까지 껐다 — docs 만 끄면 /openapi.json 이 토큰 없이 열린 채 라우트 전체를 내준다"
  - "V-SAFE-01d 를 grep 에서 AST 근사 스캐너로 교체 — VALIDATION 원문 패턴은 줄바꿈을 못 넘어 항상 빈 통과였다"
  - "CT_PORT 를 settings 계층에서 처리 — 기동 스크립트가 직접 읽으면 바인드 포트만 바뀌고 Origin 화이트리스트가 옛 포트에 남는다"
  - "기동 안내 print 는 flush=True 필수 — launchd 가 stdout 을 파일로 돌리므로 이게 없으면 토큰을 영영 못 본다"
  - "회귀 테스트를 flush=True grep 이 아니라 실제 서브프로세스 PIPE 관찰로 짰다 — 철자가 아니라 증상을 검사한다"
  - "Task 1 GREEN 에 main.py 최소본을 포함 — Host 400·Origin 403 은 앱 레벨 동작이라 앱 없이는 Task 1 의 verify 가 성립하지 않는다"

patterns-established:
  - "보안 테스트는 conftest.client(정상 사용자)에서 헤더를 걷어내 공격자를 흉내 낸다"
  - "시크릿 단언은 assert 가 아니라 pytest.fail(사유만) — assert 는 실패 시 값을 화면에 찍는다"
  - "가드 스크립트는 프로브를 심어 FAIL 이 나는 것까지 확인한 뒤에야 믿는다 (01-01 no_commit_guard 선례 계승)"
  - "셸 스크립트 식별자는 ASCII — macOS 기본 bash 3.2 는 비ASCII 변수·함수명에서 죽는다"

requirements-completed: [SAFE-01, SAFE-02, SAFE-03]

# Metrics
duration: 22min
completed: 2026-09-20
---

# Phase 1 Plan 03: 보안 3층 + 앱 셸 Summary

**127.0.0.1 에만 뜨는 FastAPI 서버에 Host 화이트리스트·쓰기 전용 Origin 가드·부팅 토큰 3층을 세워, 브라우저로 실제 보드 셸까지 들어가게 만들었다 — 보안 8종 curl 전량 PASS, 토큰은 주소창에도 디스크에도 안 남는다.**

## Performance

- **Duration:** 약 22분 (본 작업 8분 + 체크포인트 FAIL 수정 14분)
- **Tasks:** 3 (Task 3 은 체크포인트 — 오케스트레이터 대행 검증)
- **Files modified:** 14 (신규 13 · 수정 1)

## Accomplishments

- **서버가 뜨고, 나 말고는 아무도 못 들어온다.** 보안 8종 curl 이 실행 중인 서버 대상으로 전량 PASS 한다. `lsof` 에 `127.0.0.1:8765` 단독이고 `0.0.0.0` 이 없다.
- **토큰이 어디에도 안 남는다.** `GET /?t=` → `303 See Other` + `set-cookie: ct_session=…; HttpOnly; Path=/; SameSite=strict` → 주소창은 깨끗한 `/`. 토큰은 메모리에만 있고 파일로 안 떨어진다 (T-1-16).
- **쿠키와 헤더의 역할을 갈랐다.** 쿠키는 페이지 접근, `X-CT-Token` 헤더는 쓰기 인가다. 커스텀 헤더는 교차 오리진에서 붙일 수 없다(CORS 미개방) — 이게 CSRF 방어의 본체이고, 쿠키로 쓰기를 인가했으면 방어가 성립하지 않았다.
- **"상태를 바꾸는 GET 없음"이 문서 규칙이 아니라 기계 검사가 됐다.** GET 데코레이터 아래 본문을 실제로 훑어 `create_job`/`spawn`/`Popen`/`run_bids`/`run_revert` 호출을 찾는다. 가짜 핸들러를 심어 FAIL 나는 것까지 확인했다.
- **후속 6개 플랜이 `main.py` 를 다시 안 건드린다.** 라우터 3개와 partial 2개를 빈 스텁으로 먼저 파 두고 조립 순서(health → board → jobs)를 확정했다.
- **CLI 기준선 100 tests 불변.** 이 플랜은 `.claude/skills/` 를 한 줄도 안 건드렸다.

## Task Commits

1. **Task 1: `security.py` — 부팅 토큰 · Origin 가드 · 스크러버** (TDD) — `0a82efa` (test, RED) → `34c1b73` (feat, GREEN). REFACTOR 불필요.
2. **Task 2: `main.py` · 라우터 3개 · 템플릿 셸 · 기동 스크립트** — `88fcf68` (feat)
3. **Task 3 산출물: 보안 8종 curl 스크립트** — `dcd92a5` (test)
4. **체크포인트 [1] FAIL 수정: 기동 안내 URL flush** — `280071e` (fix)

## Checkpoint (Task 3) — 검증 경위

체크포인트는 `gate="blocking"` 이었고, **오케스트레이터가 6항목을 대행 검증**했다. 결과는 5 PASS / 1 FAIL:

| # | 항목 | 결과 |
|---|------|------|
| 1 | 기동 로그에 `→ …/?t=…` 줄 | ❌ **FAIL** → 이 플랜의 `280071e` 로 닫힘 |
| 2 | curl 8종 전량 PASS + exit 0 | ✅ PASS |
| 3 | 토큰 없이 `GET /` → 403 | ✅ PASS |
| 4 | `?t=` → 303 + 쿠키, 쿠키만으로 재진입 200 (2352B) | ✅ PASS |
| 5 | 시크릿성 값 8개 전수 대조 → 응답 본문·`webapp-logs/` 0건 | ✅ PASS |
| 6 | `lsof` → `127.0.0.1:8765` 단독, `0.0.0.0` 없음 | ✅ PASS |

**브라우저 육안 확인(개발자도구 Network 탭)은 수행하지 않았다.** 크롬 확장이 연결돼 있지 않아 실제 렌더링·주소창을 눈으로 보지 못했고, curl 등가 검증으로 대체했다 — 303 응답 헤더와 `Location: /` 로 "주소창이 깨끗해진다"를, 쿠키 단독 재진입 200 으로 "보드가 열린다"를, 시크릿 8개 전수 대조로 "페이지 소스에 시크릿이 없다"를 각각 덮었다. **남는 구멍은 CSS·JS 가 실제로 그려지는지 하나뿐이고**, 이건 Plan 01-04 가 보드 테이블을 채울 때 어차피 눈으로 보게 된다.

## Files Created/Modified

- `webapp/security.py` — `BOOT_TOKEN`(CT_DEV_TOKEN 없으면 `token_urlsafe(32)`) · `allowed_origins()`(매 호출 조립, 포트 리터럴 0건) · `guard()`(Origin → Sec-Fetch-Site → `compare_digest` 토큰) · `page_cookie_ok()` · `register_secret()`/`scrub()`
- `webapp/main.py` — GZip → TrustedHost → guard 3층, `Jinja2Templates`, `/static` 마운트, `WEB_CONCURRENCY` 경고, 기동 안내 URL, 라우터 등록
- `webapp/routes/health.py` — `GET /healthz`. **동기 `def`** — `scan_run_dirs()` 가 동기 IO라 async 로 두면 이벤트 루프를 막아 모든 SSE 스트림이 같이 멈춘다
- `webapp/routes/board.py` — `GET /`. 쿠키 교환 303, 쿠키 없으면 403, 있으면 `board.html`
- `webapp/routes/jobs.py` — 빈 `router` + "작업 생성은 전부 POST" 규칙 docstring
- `webapp/templates/board.html` — `hx-headers` 한 줄로 모든 htmx 쓰기에 토큰을 붙인다. 신선도 배너 · partial 2개 include · `div#board`. vendoring 정적파일만 참조
- `webapp/run-webapp.sh` — `--host 127.0.0.1 --workers 1`, 포트는 settings 에서 읽는다
- `webapp/tests/test_security.py` — 12개 (behavior 10항목 + Origin 조립 + compare_digest 강제)
- `webapp/tests/test_boot_log.py` — 2개 (파이프 기동 안내 · CT_PORT 일관성)
- `webapp/tests/security_curl.sh` — 실행 중인 서버 대상 8종
- `webapp/settings.py`(수정) — `PORT` 가 `CT_PORT` 를 우선 반영

## Decisions Made

- **`openapi_url=None` 까지 껐다.** 플랜은 `docs_url`/`redoc_url` 만 지정했는데, 그러면 `/openapi.json` 이 **토큰 없이 열린 채** 라우트 전체와 스키마를 내준다(GET 이라 `guard` 도 안 탄다). `app.openapi()` 는 그대로 쓸 수 있어 검증에는 영향이 없다. 실측: `GET /openapi.json` → 404.
- **V-SAFE-01d 를 스캐너로 교체.** VALIDATION 원문 `grep -rnE '@app\.get\(.*\)\s*\n\s*def …'` 는 grep 이 줄 단위라 **영원히 매치되지 않는다** = 항상 PASS. "전부 막힘"을 성공으로 오독하지 말라던 플랜의 경고가 정작 이 줄에 적용되지 않은 상태였다.
- **`CT_PORT` 를 settings 계층에서 처리.** 기동 스크립트가 직접 읽으면 uvicorn 바인드 포트만 바뀌고 `settings.PORT` 를 쓰는 Origin 화이트리스트·안내 URL 은 옛 포트에 남는다. 증상이 "모든 버튼이 403" 이라 원인을 엉뚱한 데서 찾게 된다.
- **회귀 테스트를 grep 이 아니라 관찰로 짰다.** 코디네이터 지시대로 `flush=True` 소스 grep 을 피했다. 철자를 검사하면 나중에 로거로 바꿨을 때 테스트는 초록인데 입구는 막힌다.
- **Task 1 GREEN 에 `main.py` 최소본을 포함했다.** Task 1 의 behavior 10항목 중 8개(Host 400·Origin 403·토큰 403)가 **앱 레벨 동작**이라, 앱 없이는 Task 1 의 `<verify>`(`pytest test_security.py -x -q` 전량 통과)가 성립하지 않는다. Task 2 가 그 최소본을 템플릿·정적파일·라우터로 확장하고 `/` 를 `routes/board.py` 로 옮겼다. 두 커밋 모두 자기 시점에서 초록이다.

## Deviations from Plan

### 체크포인트 FAIL 수정

**0. [체크포인트 [1]] 기동 안내 URL 이 파이프·파일 리다이렉트에서 안 나왔다**
- **Found during:** 오케스트레이터 대행 검증 (Task 3)
- **Issue:** `lifespan` 의 `print()` 에 `flush=True` 가 없었다. stdout 이 tty 면 줄 버퍼링이라 보이지만, 파일 리다이렉트/파이프면 블록 버퍼링(8KB)으로 바뀌고 서버 프로세스가 끝나지 않으니 버퍼가 **영원히** 안 비워진다. 토큰은 재시작마다 바뀌고 디스크에 안 남기므로 그 줄이 유일한 입구다. 상시 기동 수단인 launchd LaunchAgent 가 정확히 stdout→파일 경로라, 그대로 올렸으면 들어갈 길이 사라졌다. 저장소 관례 위반이기도 하다(`detail_batch.py` 는 줄 출력에 `flush=True` 를 쓴다).
- **왜 내 self-smoke 가 놓쳤나:** 나는 `nohup … > server.log` 로 띄운 뒤 `cat` 했는데, 그때는 startup 직후 uvicorn 이 stderr 로 쓴 줄들과 섞여 URL 줄이 보였다. 재현이 간헐적이었고 버퍼 크기에 의존했다 — 확정적으로 재현한 것은 코디네이터의 리포트다.
- **Fix:** `print()` 2개 모두 `flush=True` + 한국어 근거 docstring.
- **Files modified:** `webapp/main.py`
- **Verification:** 아래 § 실측 증거의 리다이렉트 재현 출력. 추가로 `flush=True` 를 빼고 테스트를 돌려 `stdout 0줄` 로 FAIL 나는 것까지 확인한 뒤 되돌렸다.
- **Committed in:** `280071e`

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `.venv-web` 에 `httpx` 가 없어 TestClient 가 못 돈다**
- **Found during:** Task 1 GREEN
- **Issue:** starlette 1.6.0 의 `testclient` 가 `httpx2` → `httpx` 순으로 찾는데 둘 다 없어 `RuntimeError` 로 테스트 전량 ERROR. Wave 0 은 이 픽스처를 아무도 안 썼기 때문에 드러나지 않았다(01-01 이 "의도된 스텁"으로 남겨 둔 지점).
- **Fix:** CLAUDE.md 기술스택 표에 이미 핀으로 적힌 `httpx==0.28.1` 설치. **새 패키지 도입이 아니라 문서에 선언된 의존성의 뒤늦은 설치다** — 그래서 체크포인트 없이 진행했다.
- **Note:** "httpx2 를 쓰라"는 deprecation 경고가 뜨지만 동작은 정상이다. `pytest.ini` 가 `filterwarnings=error` 를 안 쓰기로 한 01-01 의 결정이 여기서 값을 했다.
- **Verification:** `pytest webapp/tests` 41 passed
- **Committed in:** `34c1b73` (코드) — `.venv-web` 자체는 `.gitignore` 대상

**2. [Rule 3 - Blocking] 플랜의 acceptance 명령이 FastAPI 0.141.1 에서 안 돈다**
- **Found during:** Task 2
- **Issue:** `[r.path for r in app.routes]` → `AttributeError: '_IncludedRouter' object has no attribute 'path'`. CLAUDE.md 가 경고해 둔 "`router.routes` 리스트→트리" 브레이킹 체인지가 실제로 물렸다.
- **Fix:** `sorted(app.openapi()['paths'])` 로 검증. 결과 `['/', '/healthz']`.
- **Files modified:** 없음 (검증 명령만)
- **Committed in:** `88fcf68`

**3. [Rule 2 - Missing Critical] `openapi_url=None`**
- **Found during:** Task 2
- **Issue:** `docs_url`/`redoc_url` 만 끄면 `/openapi.json` 이 인증 없이 열린 채 남는다. 시크릿은 없지만 라우트 지도를 통째로 내주고, T-1-03 의 "공격면을 줄인다"는 의도와 어긋난다.
- **Fix:** `openapi_url=None`.
- **Verification:** `GET /openapi.json` → 404
- **Committed in:** `88fcf68`

**4. [Rule 2 - Missing Critical] V-SAFE-01d 가 빈 통과였다**
- **Found during:** Task 3
- **Issue:** VALIDATION 원문 패턴이 `\n` 을 포함해 grep 으로는 절대 매치되지 않는다 → 무조건 PASS. T-1-01b(상태를 바꾸는 GET 금지)를 지킨다고 주장하면서 아무것도 안 보고 있었다.
- **Fix:** GET 데코레이터 아래 본문을 훑어 쓰기 호출을 찾는 스캐너로 교체.
- **Verification:** `webapp/_probe_get.py` 에 `@router.get` + `create_job()` 을 심어 FAIL 확인 후 제거
- **Committed in:** `dcd92a5`

**5. [Rule 1 - Bug] macOS bash 3.2 가 한글 변수·함수명에서 죽는다**
- **Found during:** Task 3
- **Issue:** `실패=0: command not found`, `unbound variable`. 스크립트가 통째로 안 돌았다.
- **Fix:** 셸 식별자를 ASCII 로(`fails`·`check`·`code`·`bind_ok`·`leaked`). 주석은 한국어 유지. 파이썬 블록은 3 이라 한글 식별자를 그대로 둘 수 있었다.
- **Committed in:** `dcd92a5`

**6. [Rule 1 - Bug] `CT_PORT` 가 바인드 포트와 Origin 화이트리스트를 어긋나게 했다**
- **Found during:** 체크포인트 수정 중 (회귀 테스트가 다른 포트를 필요로 하면서 드러남)
- **Issue:** 내가 Task 2 에서 넣은 `PORT="${CT_PORT:-$(settings.PORT)}"` 가 원인이다. `CT_PORT=9999` 면 uvicorn 은 9999 에 뜨는데 `settings.PORT` 를 읽는 `allowed_origins()` 와 안내 URL 은 8765 에 남는다 → 모든 쓰기가 403.
- **Fix:** 우선순위를 settings 안으로 옮겼다(`CT_PORT` > `workspace.toml` > 기본값). 기동 스크립트는 `settings.PORT` 만 읽는다.
- **Verification:** `test_CT_PORT_가_설정포트를_이긴다` + `test_기동_URL_이_파이프로도_보인다` 의 포트 단언
- **Committed in:** `280071e`

**7. [Rule 1 - Bug] 내 문서 주석이 자기 가드를 트립시켰다**
- **Found during:** Task 2
- **Issue:** `board.html` 주석에 금지 필터 이름을 그대로 적어서 `! grep -rqn '| safe' webapp/templates/` 가 실패했다.
- **Fix:** 설명에서 그 형태를 빼고 "grep 가드가 이 문자열을 감시하므로 설명에도 그 형태를 안 적는다" 를 명시.
- **Committed in:** `88fcf68`

---

**Total deviations:** 1 체크포인트 FAIL 수정 + 7 auto-fixed (4 bug, 2 missing-critical, 2 blocking — 2번은 검증 명령만 수정)
**Impact on plan:** 인터페이스 계약(`<interfaces>` 의 security 8심볼 · main 2심볼 · 라우터 3개 · 템플릿 3개)은 하나도 안 바뀌었다. 추가된 것은 `settings.PORT` 의 env 우선순위와 `test_boot_log.py` 뿐이다. 스코프 확장 없음.

## Issues Encountered

- **`security.py` ↔ `settings` 순환 없음 확인.** `security` 가 `settings` 를 import 하고 `settings` 는 `paths` 만 쓰므로 방향이 한쪽이다. 반면 라우터 → `main.templates` 는 진짜 순환이라 핸들러 안에서 지연 import 했다(`paths.freshness()` 가 `settings` 를 지연 import 하는 01-01 선례와 같은 처리).
- **미들웨어 실행 순서가 직관과 반대다.** `add_middleware` 는 앞에 끼워 넣으므로 나중에 붙인 것이 바깥이다. 즉 실제 순서는 guard → TrustedHost → GZip. 그래서 `Host: evil.com` 으로 오는 **POST** 는 400 이 아니라 403(origin/토큰)이 먼저 난다. GET 은 guard 를 안 타므로 400 이 정상이고, V-SAFE-01b 가 GET 으로 검사하는 이유가 이것이다.
- **`nohup … > log` self-smoke 가 flush 버그를 통과시켰다.** 버퍼 크기·타이밍에 따라 간헐적으로 보였다. **교훈: 장시간 프로세스의 출력 검증은 "한 번 보였다"로 끝내면 안 된다.** 그래서 회귀 테스트를 확정적(PIPE + `PYTHONUNBUFFERED` 제거)으로 짰다.

## Known Stubs

전부 **의도된 스텁**이고 각각 어느 플랜이 해소하는지 파일 안에 적어 뒀다.

| 스텁 | 파일 | 해소 플랜 |
|---|---|---|
| 빈 `router` (라우트 0개) | `webapp/routes/jobs.py` | 01-05 (POST /jobs/* · SSE) |
| 보드 테이블 자리만 있는 `div#board` | `webapp/templates/board.html` | 01-04 |
| 빈 진행 패널 (`hidden`) | `webapp/templates/_job_panel.html` | 01-05 |
| 빈 미리보기 표 (`hidden`) | `webapp/templates/_preview_table.html` | 01-06 |
| V-SAFE-02c 기준이 "403 아님"(현재 404) | `webapp/tests/security_curl.sh` | 01-06 완료 후 `-lt 400` 으로 조인다 (주석에 명시) |

**플랜 목표 달성을 막는 스텁은 없다.** 이 플랜의 목표는 "서버가 뜨고 나 말고는 못 들어온다" 이고, 그건 전부 실동작으로 증명됐다. `scrub()` 이 사실상 항등 함수인 것도 스텁이 아니라 **정상**이다 — Phase 1 은 웹앱이 시크릿을 손에 쥐지 않으므로 `_SECRETS` 가 비어 있는 게 맞고, 함수는 01-05 의 로그 tail 이 통과할 훅으로 미리 자리를 잡은 것이다.

## Threat Flags

없음 — 이 플랜은 신뢰경계를 **새로 만들지 않고 닫는다**. 새로 생긴 네트워크 표면은 `GET /`·`GET /healthz`·`/static` 셋이고 전부 읽기 전용이며, 셋 다 위 검증에 포함됐다. 웹앱 프로세스는 `~/.eroom/naver-ads.json` 을 한 번도 열지 않는다.

## Verification Evidence

```
웹앱:        .venv-web/bin/pytest webapp/tests -q → 41 passed (0.57초)
             test_security.py 12 · test_boot_log.py 2 · (01-01/01-02 분 27)
가드:        bash webapp/tests/no_commit_guard.sh → exit 0
CLI 기준선:  test_nvad · test_reports · test_ads_rules · test_ledger · test_bids · test_prune
             = 100 tests, 6파일 전부 exit=0 (불변)
Task2 수락:  app.openapi()['paths'] = ['/', '/healthz'] · workers 1 있음
             · 템플릿에 CDN 0건 · 자동이스케이프 해제 필터 0건

보안 8종 (실행 중인 서버, settings.py 수정 후 재검):
  PASS V-SAFE-01a  127.0.0.1 에만 바인드 (0.0.0.0 없음)
  PASS V-SAFE-01b  Host: evil.com → 400
  PASS V-SAFE-01c  Origin: evil.com + 올바른 토큰 → 403
  PASS V-SAFE-01d  상태를 바꾸는 GET 엔드포인트 0건
  PASS V-SAFE-02a  토큰 없는 POST → 403
  PASS V-SAFE-02b  틀린 토큰 POST → 403
  PASS V-SAFE-02c  올바른 Origin + 올바른 토큰 POST → 403 아님 (현재 404)
  PASS V-SAFE-03   응답 본문·webapp-logs 에 광고 시크릿 0건
  → exit 0

기동 안내 URL — 코디네이터 재현 명령 그대로 (파일 리다이렉트):
  $ CT_DEV_TOKEN=devtoken123 ./webapp/run-webapp.sh > /tmp/ct-server.log 2>&1 &
  $ cat /tmp/ct-server.log
  INFO:     Started server process [89482]
  INFO:     Waiting for application startup.
  → http://127.0.0.1:8765/?t=devtoken123
  INFO:     Application startup complete.
  INFO:     Uvicorn running on http://127.0.0.1:8765 (Press CTRL+C to quit)

flush 프로브 (회귀 테스트가 빈 통과가 아님을 증명):
  flush=True 제거 → Failed: 25.0초 안에 기동 안내 줄이 stdout 으로 안 나왔다. stdout 0줄
  복원 후 → 2 passed

브라우저 흐름 (curl 등가):
  GET /?t=devtoken123  → 303 See Other · location: / ·
                         set-cookie: ct_session=…; HttpOnly; Path=/; SameSite=strict
  GET /  (토큰 없음)    → 403 "토큰이 필요하다 — 서버 기동 로그의 URL 로 들어와라"
  GET /  (쿠키만)       → 200, <title>셀러 관제탑</title> ·
                         <body hx-headers='{"X-CT-Token": "…"}'> · div#board
  GET /healthz         → {"ok":true,"run_dirs":2}
  GET /openapi.json    → 404 (껐다)
  정적파일              → pico 200 · htmx 200
  lsof                 → TCP 127.0.0.1:8765 (LISTEN) 단독

신선도 배너 실측 (D-16):
  2026-08-30 회차 · 21일 전 · 통계 기간 2026-08-22~2026-08-28 · "이 회차 낡았다"
  → 회차명과 통계기간이 8일 어긋난 것이 화면에 그대로 드러난다
```

## User Setup Required

없음. 다만 **다른 PC 에서 `.venv-web` 재생성 시 `httpx` 를 빼먹지 마라** — 빠지면 웹앱 테스트가 전량 ERROR 다:

```
uv venv .venv-web --python 3.12
uv pip install --python .venv-web/bin/python \
  "fastapi==0.141.1" "uvicorn==0.53.0" "jinja2==3.1.6" "sse-starlette==3.4.11" \
  "pytest" "httpx==0.28.1"
```

`run-webapp.sh` 가 `.venv-web` 부재를 감지하면 이 명령을 그대로 찍어 준다.

## Next Phase Readiness

**Wave 2(01-04)로 바로 갈 수 있다.**

- `01-04` (보드): `routes/board.py` 의 `GET /` 가 이미 `run_dirs`·`freshness`·`token` 을 템플릿에 넘긴다. `board.html` 의 `div#board` 와 신선도 배너 자리에 Tabulator 와 경고색을 채우면 된다. `main.py` 는 안 건드려도 된다.
- `01-05` (잡 엔진): `routes/jobs.py` 에 POST 를 채운다. **`@router.get` 으로 작업을 만들면 `security_curl.sh` 의 V-SAFE-01d 가 즉시 빨개진다** — 규칙이 기계로 집행된다. 로그 tail 은 `security.scrub()` 을 통과시켜라.
- `01-06` 완료 후: `security_curl.sh` 의 V-SAFE-02c 판정을 `-lt 400` 으로 조여라(스크립트 주석에 적어 뒀다).
- **주의:** 마지막 회차가 21일 묵어 `stale=True` 다. 01-06 Task 3 의 수동 확인에서 `prep --account cy728` 로 광고 API 자격증명 유효성부터 봐야 한다(OQ-6, 01-01 에서 이월).

## Self-Check: PASSED

- 신규 파일 13개 + 수정 1개 전부 FOUND
- 커밋 5개 전부 FOUND: `0a82efa` · `34c1b73` · `88fcf68` · `dcd92a5` · `280071e`
- 커밋에 의도치 않은 파일 삭제 0건 (`git diff --diff-filter=D e0da6f8..HEAD` 비었음)
- 프로브 파일(`webapp/_probe_get.py`) 제거 확인 — 작업트리 깨끗

---
*Phase: 01-board-bid-raise*
*Completed: 2026-09-20*
