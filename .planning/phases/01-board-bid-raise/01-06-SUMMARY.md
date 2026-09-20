---
phase: 01-board-bid-raise
plan: 06
subsystem: progress-stream
tags: [sse, sse-starlette, htmx-ext-sse, logtail, offset-tail, cdp, headless-chrome, tdd]

# Dependency graph
requires:
  - phase: 01-01
    provides: "conftest 의 synthetic_job 픽스처 · settings.POLL_INTERVAL · vendoring 된 htmx-ext-sse 2.2.4 · no_commit_guard.sh"
  - phase: 01-03
    provides: "앱 셸 · security.scrub/page_cookie_ok · GZipMiddleware 배치 · security_curl.sh"
  - phase: 01-04
    provides: "board.html 컨텍스트(rows) · board_cdp.{sh,mjs} 하네스 모양 · '숫자가 움직인다는 근거가 아니다' 교훈"
  - phase: 01-05
    provides: "jobs.spawn(PYTHONUNBUFFERED=1 · start_new_session) · log_path_of · job_status · _job_panel.html 의 빈 <pre> · POST /jobs/*"
provides:
  - "webapp/logtail.py — read_from(path, offset) 바이트 오프셋 tail + sse_generator(전량 재생)"
  - "GET /jobs/{id}/stream — EventSourceResponse(ping=15, send_timeout=30). 라우터의 유일한 async"
  - "webapp/templates/_job_status.html — 2초 폴링이 갈아끼우는 상태 조각 (패널에서 분리)"
  - "_job_panel.html 의 SSE 배선 — hx-ext=sse · sse-swap=log · sse-close=done (JS 0줄)"
  - "jobs.active_job() — 도는 작업 하나. GET / 이 이걸 실어야 새로고침 후 패널이 산다"
  - "settings 의 CT_DB_PATH / CT_JOB_LOG_DIR env 오버라이드 (임시 레지스트리로 서버 띄우기)"
  - "security.토큰이같나() — 비ASCII 입력에도 안 터지는 상수시간 비교"
  - "webapp/tests/sse_cdp.{sh,mjs} — 헤드리스 크롬에서 탭을 진짜 닫았다 여는 12종 검증"
  - "security_curl.sh 9종 (V-SAFE-02c 를 c1/c2 로 조임 · 라우트가 생기면 자동 강화)"
affects: [01-07, 01-08, 01-09, "Phase 3 상세 생성 폴링(수십 분)이 올라탈 진행 표시 계약"]

# Tech tracking
tech-stack:
  added: []          # 신규 의존성 0 — sse-starlette·htmx-ext-sse 는 01-01 이 이미 깔았다
  patterns:
    - "진행 로그는 파이프가 아니라 append-only 파일을 오프셋부터 tail 한다 (ENG-03 / PATTERNS §C-3)"
    - "매 접속 오프셋 0 전량 재생 — 재연결 헤더에 이어받기를 맡기지 않는다 (T-1-27)"
    - "서버가 누적본을 보내고 클라이언트는 innerHTML 로 교체한다 (붙이기 금지 = 중복 방지)"
    - "폴링이 갈아끼우는 조각과 살아 있는 커넥션을 담은 조각을 분리한다"
    - "async 라우트는 오래 사는 커넥션에만. 그 안에서 sqlite 는 to_thread 로 밀어낸다"
    - "브라우저 생명주기 검증은 pytest 밖 CDP 계층 (security_curl/board_cdp 와 동급)"
    - "검증 문구는 '보인다/움직인다' 가 아니라 '첫 줄이 정확히 X · 목록이 1..N 연속'"

key-files:
  created:
    - webapp/logtail.py
    - webapp/templates/_job_status.html
    - webapp/tests/test_logtail.py
    - webapp/tests/sse_cdp.sh
    - webapp/tests/sse_cdp.mjs
  modified:
    - webapp/routes/jobs.py
    - webapp/routes/board.py
    - webapp/jobs.py
    - webapp/security.py
    - webapp/settings.py
    - webapp/templates/_job_panel.html
    - webapp/templates/board.html
    - webapp/tests/test_jobs.py
    - webapp/tests/test_routes_jobs.py
    - webapp/tests/test_security.py
    - webapp/tests/security_curl.sh
    - .planning/phases/01-board-bid-raise/01-VALIDATION.md

key-decisions:
  - "폴링과 SSE 를 조각 단위로 분리했다 — 패널 전체를 2초마다 outerHTML 로 갈아끼우면 그 안의 EventSource 가 2초마다 끊겼다 붙는다"
  - "SC-03 자동 테스트가 진짜 uvicorn 을 띄운다 — TestClient 는 ASGI 앱을 끝까지 돌린 뒤 BytesIO 로 주므로(소스 확인) 부분 수신·끊김을 흉내조차 못 한다"
  - "V-SAFE-02c 를 c1/c2 로 쪼갰다 — 미리보기 라우트는 01-07 이 만든다. c1 은 실재 라우트로 '앱 로직이 답한다'까지 보고, c2 는 라우트가 생기면 자동으로 -lt 400 이 된다"
  - "sse-close 는 연결을 여는 엘리먼트에 붙인다 — 확장이 그 엘리먼트에서만 속성을 읽는다(sse.js:235). 리서치·플랜 예제가 자식에 붙여 둔 것은 틀렸다"
  - "active_job() 은 running 만 돌려주고 레지스트리가 없으면 만들지 않는다 — GET 이 파일을 만들기 시작하면 'GET 은 상태를 안 바꾼다' 전제가 흐려진다"
  - "로그 자동 스크롤을 flex column-reverse 로 한다 — 그거 하나 때문에 JS 를 들이지 않는다"
  - "로그 센티널을 새로 만들지 않았다 — 로그는 사람이 보는 용도로만 쓴다 (D-02/D-03)"

patterns-established:
  - "테스트가 감시하는 문자열은 런타임 파일의 주석에도 쓰지 않는다 (01-05 의 교훈이 이 플랜에서 3번 더 걸렸다 — 가드가 맞다)"
  - "새 검증 수단은 버그 버전으로 되돌려 FAIL 을 확인한 뒤에만 믿는다 (음성 대조군)"
  - "문서·리서치의 예제 스니펫보다 vendoring 된 라이브러리 소스가 정본이다"

requirements-completed: [ENG-02, ENG-03]

# Metrics
duration: 78min
completed: 2026-09-20
---

# Phase 1 Plan 06: 진행 로그 SSE Summary

**브라우저 탭을 닫았다 다시 열어도 진행 로그가 1번 줄부터 빠짐없이 다시 흐른다 — 헤드리스 크롬에서 탭을 진짜로 닫고(25줄) 5초 뒤 새 탭을 열어(41줄) 첫 줄이 정확히 `[1/40] tick` 임을 기계로 확인했다. 성공기준 3 이 여기서 닫혔다.**

## Performance

- **Duration:** 78분
- **Tasks:** 2/2 자동 태스크 (TDD RED/GREEN 커밋 4개) + 체크포인트 1건(오케스트레이터 대행 + 용팀장 승인)
- **Files:** 17 (신규 5 · 수정 12)
- **테스트:** 웹앱 **115개** 전량 green (이번에 +26) · CLI 100개 불변

## Accomplishments

### Task 1 — `webapp/logtail.py` (TDD: `52d900c` RED → `92cecc9` GREEN)

설계의 전부가 한 줄에 있다: **`off = 0`.**

매 접속마다 오프셋 0 부터 읽는다. 이어받기를 브라우저의 재연결 헤더에 맡기지 않는 이유는
htmx-ext-sse 2.2.4 가 재연결할 때 `EventSource` 를 **새로 만들어** 이전 연결의 이벤트 ID
상태를 버리기 때문이다(소스 확인). 그 위에 이어받기를 세우면 "이어보기가 가끔 된다"는
재현 불가 버그가 된다. 잡 로그가 실측 4.5KB / 53줄이라 전량 재생이 더 단순하고 더 정확하며,
요구사항 문장("처음부터 이어서 본다")과 글자 그대로 맞는다.

**이벤트마다 '지금까지의 전체 로그'를 보낸다.** `sse-swap` 의 기본 swap 이 innerHTML
(전량 교체)이라 청크만 보내면 화면에 마지막 청크만 남는다. 반대로 클라이언트가 붙이기로
받으면 재연결 때 로그가 두 번 찍힌다(T-1-26). **서버 전량 재생 + 클라이언트 전량 교체가
한 쌍**이고, 둘 중 하나만 바꾸면 조용히 깨진다.

`read_from` 의 모든 실패(파일 없음·디렉터리·권한)는 `("", offset)` 으로 폴백한다.
로그를 못 읽는 건 돈으로 이어지지 않는데(저장소 S-2 판별 기준), 여기서 예외를 올리면
작업이 시작되자마자 스트림이 죽고 사용자는 "작업이 멈췄다"로 오독한다 — 실제로는 잘 도는데.

한글 로그라 **멀티바이트 절단이 실제로 난다.** `errors="replace"` 로 버티는데, 전량 재생
설계 덕분에 다음 회차(0.4초)에 나머지 바이트가 붙으면서 누적본이 통째로 다시 그려진다 —
깨진 글자가 화면에 남지 않는다. 정교한 꼬리 버퍼링이 사는 값이 0 이라 안 만들었다.

`job_status` 는 sqlite 를 만지므로 `anyio.to_thread` 로 밀어낸다. 이 제너레이터는
**이벤트 루프 위에서 도는 유일한 경로**라 blocking IO 를 직접 하면 다른 요청이 전부 멈춘다
(T-1-28). 상태 조회는 새 로그가 없을 때만 한다 — 흐르는 중이면 물을 것도 없다.

### Task 2 — `GET /jobs/{id}/stream` + 패널 배선 (TDD: `be6624e` RED → `55a6f9b` GREEN)

라우터에서 **유일한 `async def`** 다. 수 분씩 살아 있는 커넥션이 스레드풀 자리를 차지하면
안 되기 때문이고, 나머지 핸들러는 전부 `def` 로 남아 sqlite·파일 IO 를 스레드풀이 받는다.
`test_라우트_중_async_는_스트림_하나다` 가 데코레이터 붙은 def 만 골라 세서 이걸 지킨다
(`grep -c 'async def'` 로는 못 센다 — 01-05 의 폼 파싱 의존성도 async 라서 2가 나온다).

**폴링과 SSE 를 조각 단위로 분리했다** (플랜과 다르게 간 것 1). 01-05 의 패널은 2초마다
`#job-panel` 전체를 `outerHTML` 로 교체하는데, 그 안에 SSE 커넥션을 넣으면 2초마다
끊겼다 붙는다 — 로그가 2초마다 처음부터 다시 그려지고 죽은 커넥션이 쌓인다(T-1-24,
HTTP/1.1 호스트당 6개). 그래서 `_job_status.html` 을 새로 떼어:

| 조각 | 누가 교체하나 | 무엇이 들었나 |
|---|---|---|
| `_job_status.html` | 2초 폴링 (`GET /jobs/{id}`) | 경과시간·상태·안내 문구 |
| `_job_panel.html` | 작업 생성 (`POST /jobs/*`) · 페이지 로드 | 위 조각 + **살아 있는 SSE 커넥션** |

`jobs.active_job()` 이 `GET /` 에 도는 작업을 실어 준다. **이게 없으면 탭을 다시 열었을 때
패널이 비어서 열 스트림 자체가 없다** — 재접속 스트림이 아무리 완벽해도 화면에서는
성공기준 3 이 성립하지 않는다. 읽기만 한다: 레지스트리 파일이 없으면 만들지 않고 None 이다.

경과시간을 크게 띄운다(OQ-3 확정). `bids --commit` 은 1,200건을 100초 동안 도는데 실패 줄
말고는 아무것도 안 찍는다. CLI 에 진행률을 주입하면 stdout 파싱이 진실의 두 번째 원천이
되므로(D-02/D-03) 그렇게 하지 않고 화면의 시계로 덮는다 — "멈춘 게 아니다" 라는 반말 안내와 함께.

로그 박스는 `flex-direction: column-reverse` 로 스크롤이 아래에 붙는다. 자동 스크롤 하나
때문에 JS 를 들이지 않으려는 배치다. **이 플랜이 추가한 JS 는 0줄이다.**

## 체크포인트 — 오케스트레이터 대행 + 용팀장 승인

### (a) 탭 닫았다 열기 — 헤드리스 크롬으로 **진짜** 닫았다

플랜은 사람이 탭을 닫았다 30초 뒤 다시 열기를 요구했다. 대신 `webapp/tests/sse_cdp.{sh,mjs}`
를 만들어 CDP `/json/close` 로 탭을 **실제로 닫고** `/json/new` 로 새 탭을 열었다.
`board_cdp.sh` 와 같은 계층(pytest 밖, 살아 있는 서버)이고, 광고 API 는 한 번도 안 부른다 —
임시 포트 + `CT_DB_PATH`/`CT_JOB_LOG_DIR` 임시 디렉터리 + 합성 잡이다.

```
PASS V-SSE-00  새로고침만으로 도는 작업 패널이 뜬다
PASS V-SSE-01  5초 시점 14줄 · 첫 줄 "[1/40] tick"      ← 빈 화면이면 실패 (Pitfall 1)
PASS V-SSE-02  EventSource 정확히 1개
PASS V-SSE-03  2초 폴링이 4번 돌아도 만든횟수 1
PASS V-SSE-04  폴링이 돌아도 중복 0        14줄 → 25줄
PASS V-SSE-05  탭 닫았다 열면 첫 줄 "[1/40] tick"
PASS V-SSE-06  닫기 전 25줄 → 다시 연 뒤 41줄
PASS V-SSE-07  누락 0 중복 0 (41줄)
PASS V-SSE-08  done → readyState 2 (CLOSED)
PASS V-SSE-09  폴링 정지
PASS V-SSE-10  로그 전량 잔존
PASS V-SSE-11  done 요약 렌더
```

**음성 대조군으로 이빨을 확인했다.** `off = 0` 을 이어받기 설계로 되돌리니:

```
FAIL V-SSE-01  첫 줄 "[3/40] tick"
FAIL V-SSE-05  첫 줄 "[39/40] tick"          ← 사람 눈엔 "로그가 흐른다" 로 보인다
FAIL V-SSE-06  닫기 전 23줄 → 다시 연 뒤 3줄
FAIL V-SSE-07  3줄
```

**이게 01-04 교훈의 두 번째 적용이다.** 육안 확인이라면 "재접속했더니 로그가 흐른다" 로
PASS 를 줬을 것이다 — 이어받기 설계에서도 로그는 흐른다. 첫 줄이 `[39/40]` 인 것을
알아채야만 잡힌다. 그래서 판정 문구를 **"첫 줄이 정확히 `[1/40] tick` 이고 줄 목록이
1..N 연속"** 으로 썼다. 01-VALIDATION.md 의 Manual-Only 표에서 SC-03 행을 뺐다.

### (b) OQ-6 — 광고 API 자격증명 **살아 있다** (용팀장 승인 후 오케스트레이터 실행)

리서치·플랜 전 단계에서 한 번도 광고 API 를 부른 적이 없어 키 유효성이 미확인이었다.
나는 임의로 실행하지 않고 체크포인트로 분리했고, 용팀장 승인 후 오케스트레이터가 돌렸다:

```
$ caffeinate -i .venv/bin/python3 .../run_ads.py prep --run-dir "$(date +%F)" --account cy728
[cy728] 수집 시작
  소재 3892개 (게재중 3876)
  통계 7일 3376행 / 30일 3486행
    구매완료 리포트 28/30일 · 발생 소재 15개
수집 완료 → .../runs/2026-09-20                                   PREP_EXIT=0
```

**401/403 없음.** 산출물 실측: `ads.json` 7.5MB · `stats_30d.json` 478KB · `stats_7d.json` 461KB ·
`purchase.json` 862B · `prep_summary.json` 233B(run-dir 최상위). 시크릿성 값 8개를 prep 로그와
`webapp-logs/` 전 파일에 전수 대조 → **0건**.

→ **A8 / Open Question 6 해소.** 01-07~01-09 의 미리보기·인상·되돌리기가 전부 이 키 위에 선다.

내가 화면 쪽으로 기계 확인한 것(광고 API 0 — 없는 계정을 필터에 심어 실제 버튼을 눌렀다.
CLI 가 네트워크 타기 전에 종료한다):

```
버튼 → 패널 교체까지 58ms (블로킹 없음)
t=1.0s  로그 1줄 "계정이 없다 — ~/.eroom/naver-ads.json 을 확인해라"  ES=1  폴링=true
t=3.0s  done "새로 수집 — 실패 (종료코드 1) · 0분 0초"  readyState=2  폴링=false
```

플랜 수동 4·5·8·9번이 **실제 CLI 경로**로 덮였다. 만들어진 빈 오늘자 run-dir 은 정리했다.

### (c) 🔴 남은 플랜이 밟을 지뢰 — **회차마다 들어 있는 계정 수가 다르다**

OQ-6 확인이 한 계정만 돌린 탓에 `2026-09-20` 은 **cy728 하나짜리** 회차다.
그리고 이건 이번에 새로 생긴 문제가 아니다 — 디스크 실측:

| 회차 | 계정 | `result.json` | 보드 드롭다운 |
|---|---|---|---|
| 2026-08-29 | **2개** (cy728, cy7728) | 있다 | **나온다** |
| 2026-08-30 | 4개 (전부) | 있다 | 나온다 |
| 2026-09-20 | **1개** (cy728) | 없다 | 아직 안 나온다 (정상 — 판정을 안 돌렸다) |

즉 **오늘 이미 드롭다운에 계정 2개짜리 회차가 신선한 얼굴로 앉아 있다.**
신선도 배너(D-16)는 "며칠 묵었나" 는 말해주지만 "몇 계정이 들었나" 는 말하지 않는다.
01-07 이 미리보기 대상을 고르고 01-08 이 실행하는데, 회차를 신선도만 보고 고르면
**계정 3개가 조용히 빠진 판정 위에서 입찰가를 올리게 된다.** 그건 실제 광고비다.

이번 플랜에서 고치지 않았다(범위 밖이고 화면 설계 결정이다). **Open Questions 에 OQ-7 로
남겼다** — 다음 플랜이 이 사실을 알고 들어가게.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `sse-close` 가 자식에 붙어 있어 조용히 무시됐다**
- **Found during:** 체크포인트 검증 (sse_cdp.mjs 의 V-SSE-08)
- **Issue:** 확장 소스 `sse.js:235` 가 `getAttributeValue(elt, "sse-close")` 를 **EventSource 를
  만든 그 엘리먼트에서만** 읽는다. 자식(`<div sse-swap="done" sse-close="done">`)에 붙이면
  무시된다. 그러면 작업이 끝나 서버 제너레이터가 닫힐 때 브라우저가 "끊겼다"로 보고
  **영원히 재연결**하고, 서버는 로그 전량 + done 을 무한 반복한다.
- **왜 자동 스위트가 못 잡았나:** 화면에 증상이 **전혀** 없다. 로그도 멀쩡히 보이고
  done 요약도 붙는다. `readyState` 를 들여다봐야만 보인다.
- **어떻게 잡았나:** CDP 로 `window.EventSource` 를 래핑해 생성 횟수와 `readyState` 를
  페이지 안에서 직접 읽었다. 실측 `readyState 0(CONNECTING)` → 고친 뒤 `2(CLOSED)`.
- **출처:** 리서치 §5.4 와 플랜 Task 2 의 예제 스니펫이 둘 다 자식에 붙여 뒀고 그대로 베꼈다.
  **vendoring 된 라이브러리 소스가 문서보다 정본이다.**
- **Files:** `webapp/templates/_job_panel.html` · `webapp/tests/test_jobs.py`(가드 강화)
- **Commit:** `12914af`

**2. [Rule 2 - Missing] 비ASCII 토큰이 403 이 아니라 500 을 냈다**
- **Found during:** `security_curl.sh` 음성 대조군 (틀린 토큰으로 돌려 FAIL 을 확인하다가)
- **Issue:** `secrets.compare_digest` 는 str 두 개를 받으면 ASCII 인코딩을 시도하고
  한 글자라도 ASCII 밖이면 `TypeError: comparing strings with non-ASCII characters is not
  supported` 를 던진다. 헤더·쿠키에는 누구나 아무 바이트나 넣는다 —
  실측 `curl -H "X-CT-Token: 한글" → 500`.
- **왜 지금 내 범위인가:** 이번에 붙인 스트림 라우트가 `page_cookie_ok` 를 타고,
  그게 같은 비교 함수를 쓴다. 거부 경로가 예외로 새면 403 자리에 500 이 나오고
  트레이스백이 로그를 덮는다.
- **어떻게 잡았나:** 검증 스크립트를 "통과만 시키지 말고 **버그 버전으로 되돌려 FAIL 을
  확인**하라"는 01-04 의 관례를 따르다가 나왔다. 정상 경로만 돌렸으면 영원히 못 봤다.
- **Fix:** `security.토큰이같나()` — 양쪽을 바이트로 바꿔 비교한다(상수시간 성질 유지).
  httpx 가 비ASCII 헤더를 **클라이언트 쪽에서** 먼저 막아 HTTP 로는 재현이 안 되므로,
  회귀 테스트는 순수 함수 검증 + 바이트 헤더 두 갈래로 썼다.
- **Files:** `webapp/security.py` · `webapp/tests/test_security.py`
- **Commit:** `d959694`

**3. [Rule 1 - Bug] 재접속 테스트가 간헐 실패**
- **Issue:** 잡이 2차 수신 창 안에서 끝나면 마지막에 완료 줄이 하나 더 붙는데,
  "줄 목록이 정확히 `[1..N] tick`" 이라는 판정이 그걸 불일치로 봤다.
- **Fix:** 진행 줄만 골라 연속성을 본다. 전체 스위트 3회 연속 exit=0 확인.
- **Commit:** `d959694`

**4. [Rule 1 - Bug] 내 가드가 나를 세 번 잡았다**
- **Issue:** `logtail.py` 주석의 `Popen`·재연결 헤더 이름, `_job_panel.html` 주석의 swap 모드
  이름·연결 속성 이름이 각각 자기 감시 테스트를 빨갛게 만들었다.
- **판단:** 가드가 맞다. 01-05 가 이미 배운 것(`patterns-established`)이고 이번에 세 번 더
  확인됐다 — **주석의 예시가 내일의 복붙 코드가 된다.** 같은 내용을 금지 토큰 없이 설명했다.
- **Commits:** `92cecc9` · `55a6f9b` · `12914af`

### 플랜과 다르게 한 것 (의도적 · 오케스트레이터 승인)

**1. 폴링과 SSE 를 조각 단위로 분리했다.**
플랜 Task 2 는 패널 안에 SSE 를 넣으라고 했는데, 01-05 의 패널은 2초마다 자기 자신을
`outerHTML` 로 교체한다. 그대로 두면 EventSource 가 2초마다 재생성된다.
대안으로 `hx-preserve` 를 검토했지만 htmx 내부(`handlePreservedElements` → pantry 이동)에
기대는 설계라 버렸다 — 조각을 쪼개는 쪽이 구조적으로 안 깨진다.
01-05 의 `test_htmx_요청에는_화면조각이_온다` 를 새 계약에 맞게 고치고
`test_작업을_만들면_패널_전체가_온다` 를 더했다.

**2. SC-03 자동 테스트가 진짜 uvicorn 을 띄운다.**
`starlette/testclient.py` 의 전송 계층이 `portal.call(app, ...)` 로 ASGI 앱을 **끝까지 돌린 뒤**
본문을 `io.BytesIO` 에 모아 한 번에 준다(소스 확인). "0.8초 받고 끊는다"를 흉내조차 못 하고
서버 쪽 `is_disconnected()` 가 영원히 False 다. 그래서 임시 포트에 서버를 띄운다(+4초).
헤더·404·즉시 done 처럼 앱을 끝까지 돌려도 답이 같은 항목은 TestClient 로 남겼다.
이를 위해 `settings` 에 `CT_DB_PATH`/`CT_JOB_LOG_DIR` env 오버라이드를 더했다 —
별도 프로세스라 monkeypatch 가 안 닿고, 저장소 루트의 진짜 `webapp.db` 를 쓰면
테스트가 화면에 유령 작업을 남긴다.

**3. `V-SAFE-02c` 를 "무조건 `-lt 400`" 으로는 못 조였다 — 두 갈래로 조였다.**
`POST /jobs/bids/preview` 는 **01-07** 이 만드는 라우트다(스크립트 주석은 01-05 가 만든다고
잘못 적혀 있었고 VALIDATION.md 본문은 "01-07 완료 후"로 맞게 적혀 있다). 지금 무조건
`-lt 400` 을 걸면 404 로 빨개진다. 대신:
- **02c1** — 실재하는 쓰기 라우트(`POST /jobs/run`)에 정상 Origin·토큰으로 쏴서
  **가드 3층을 통과해 앱 로직이 답하는 것**까지 본다(400 + 몸통에 "회차"). 부수효과 0
  (`create_job` 이 회차 화이트리스트에서 거부하므로 자식이 안 뜬다).
  기존 "403 아님"보다 훨씬 강하다 — 404·000·500 이 전부 걸린다.
- **02c2** — `grep '/jobs/bids/preview' webapp/routes/jobs.py` 로 라우트 존재를 보고,
  **생기는 순간 기준이 `-lt 400` 으로 자동 전환**된다. 그전엔 "정확히 404".
- 이빨 확인: 틀린 토큰으로 돌리면 `FAIL ... (현재 403)`.

## Verification

| 검증 | 결과 |
|---|---|
| `.venv-web/bin/pytest webapp/tests -q` | **115 passed** (test_logtail 14 · test_jobs 25 · test_routes_jobs 13 · test_security 13 + 기존 50) · 10.2초 |
| `bash webapp/tests/no_commit_guard.sh` | exit 0 |
| `CT_DEV_TOKEN=… bash webapp/tests/security_curl.sh` | **9/9 PASS** |
| `CT_DEV_TOKEN=… bash webapp/tests/board_cdp.sh` | 전량 PASS (01-04 불변) |
| `bash webapp/tests/sse_cdp.sh` | **12/12 PASS** |
| CLI 회귀 6파일 | 전부 exit=0 (100 tests 불변) |
| `run_ads.py prep --account cy728` (실계정) | **exit 0 · 401/403 없음** (OQ-6 해소) |
| 템플릿·board.js 의 CDN URL | 0건 |
| `webapp-logs/` 광고 시크릿 | 0건 |

## Open Questions

**OQ-7 — 회차에 몇 계정이 들었는지를 화면이 말하지 않는다.**
디스크 실측으로 `2026-08-29`(2계정) · `2026-08-30`(4계정) · `2026-09-20`(1계정, 판정 전)이
공존한다. 신선도 배너는 경과일만 보여준다. 01-07 이 "이 회차에서 ①규칙 N건" 을 세고
01-08 이 그 위에서 입찰가를 올리는데, 계정이 빠진 회차를 신선하다는 이유로 고르면
**빠진 계정의 소재가 조용히 대상에서 사라진다** — 화면 어디에도 그 사실이 안 나온다.

내 판단으로는 **배너와 회차 드롭다운에 계정 수를 노출하는 게 맞다.** 근거:
① `result.json` 에 이미 계정 목록이 있어 `board.account_list()` 로 공짜로 셀 수 있다
(새 대장을 만들지 않는다 — 산출물 투영 원칙 그대로).
② D-16 이 신선도를 배너에 올린 이유가 "낡은 판정으로 실행하는 것"을 막는 것인데,
"계정이 빠진 판정으로 실행하는 것"은 같은 종류의 위험이고 더 조용하다.
③ 비용이 배너 한 조각이다.
다만 화면 설계 결정이라 01-07 플래너/용팀장이 정할 일로 남긴다.

## Known Stubs

| 위치 | 내용 | 해소 |
|---|---|---|
| `jobs.py` 의 `bids_*`·`revert_*` kind | argv 조립은 되지만 부르는 라우트가 없다 | 01-07(미리보기) · 01-08(실행) · 01-09(되돌리기) |
| `status='orphaned'` | 표시만 하고 복구 안 함 | Phase 2 (ENG-05) |
| `AdsArgv.prefix` | 항상 빈 리스트 (`caffeinate -i` 자리) | Phase 2 (ENG-06) |
| 최근 작업 목록의 다른 행 | 스트림을 안 연다 (의도 — T-1-24) | 해소 대상 아님 |

로그·스트림 쪽 스텁은 없다. 진행 표시는 실데이터로 끝까지 돈다.

## Threat Flags

없다. 이 플랜이 만든 표면은 `GET /jobs/{id}/stream` 하나이고 읽기 전용이다
(`V-SAFE-01d` 가 기계로 집행한다). `<threat_model>` 의 T-1-03d·T-1-17b·T-1-24·T-1-25·
T-1-26·T-1-27·T-1-28 에 각각 자동 테스트가 붙었다.
추가로 **기존 표면의 결함 하나를 고쳤다**(비ASCII 토큰 → 500). 새 surface 가 아니라
01-03 이 만든 `security.guard`/`page_cookie_ok` 의 수리다.

## Next

- **Plan 01-07:** 미리보기(`bids --preview-out`). 진행 표시 계약은 굳었으니 그대로 올라타면 된다.
  **OQ-7 을 먼저 읽어라** — 회차 선택이 곧 "어느 계정에 돈을 쓰나"다.
- `security_curl.sh` 의 V-SAFE-02c2 는 `/jobs/bids/preview` 가 생기는 순간 자동으로
  `-lt 400` 으로 조여진다. 라우트를 만들면 그게 초록인지 확인해라.
- `_job_panel.html`·`logtail.py` 를 건드리면 `bash webapp/tests/sse_cdp.sh` 를 돌려라.

## Self-Check: PASSED

- 생성 파일 5개 전부 디스크에 존재 (`webapp/logtail.py` · `webapp/templates/_job_status.html` ·
  `webapp/tests/test_logtail.py` · `webapp/tests/sse_cdp.sh` · `webapp/tests/sse_cdp.mjs`)
- 태스크 커밋 7개(`52d900c`·`92cecc9`·`be6624e`·`55a6f9b`·`d959694`·`12914af`·`dfe4b32`)
  전부 git 이력에 존재
