---
phase: 01-board-bid-raise
plan: 05
subsystem: job-engine
tags: [subprocess, sqlite, pydantic, htmx, fastapi, tdd, concurrency-guard]

# Dependency graph
requires:
  - phase: 01-01
    provides: "conftest 의 synthetic_job 픽스처 · tmp_run_dir · no_commit_guard.sh · webapp/paths.py · webapp/settings.py"
  - phase: 01-02
    provides: "run_ads.py 의 --only-ads · --preview-out · accounts 서브커맨드 (argv 계약의 반대편)"
  - phase: 01-03
    provides: "앱 셸 · security.guard(Origin+토큰) · page_cookie_ok · 빈 routes/jobs.py · settings.PORT"
  - phase: 01-04
    provides: "board.html 템플릿 컨텍스트(rows 리스트) · _job_panel.html 자리 · 계정 필터 select"
provides:
  - "webapp/argv.py — AdsArgv(Pydantic) + build(). argv 조립의 유일한 곳. PY_CLI=.venv/bin/python3"
  - "webapp/jobs.py — init_db/create_job/spawn/job_status/recent_jobs/log_path_of/targets_path_of/result_path_of/BusyError"
  - "jobs 테이블(id·kind·run_dir·accounts·argv·pid·status·exit_code·log_path·targets_path·result_path·parent_job_id·target_count·started_at·ended_at)"
  - "쓰기 잡 전역 1개 가드 (WRITE_KINDS = prep·bids_commit·revert_only·revert_all) → BusyError → 409"
  - "POST /jobs/prep · POST /jobs/run · GET /jobs · GET /jobs/{id} (htmx 면 HTML 조각, 아니면 JSON)"
  - "보드의 '새로 수집'·'판정 다시' 버튼 + 2초 상태 폴링 작업 패널 + 409 배너"
  - "webapp/tests/test_argv.py(12) · test_jobs.py(15) · test_routes_jobs.py(12)"
affects: [01-06, 01-07, 01-08, 01-09, "Phase 2~7 의 모든 실행 버튼"]

# Tech tracking
tech-stack:
  added: []          # 신규 의존성 0 — stdlib sqlite3·subprocess + 이미 있던 pydantic
  patterns:
    - "작업 생성은 HTTP 를 모르는 호출 가능한 함수. 라우트는 예외를 상태코드로 번역만 한다 (D-17/ENG-07)"
    - "argv 조립 단일 지점 + Literal 화이트리스트 + alias 패턴 = 명령 주입 경로 없음 (T-1-10)"
    - "가드 → 검증 → 파일 → argv → INSERT 를 BEGIN IMMEDIATE 한 트랜잭션에 (전역 1개 가드의 원자성)"
    - "htmx 폼 인코딩은 stdlib parse_qsl 로 직접 푼다 — python-multipart 를 안 늘린다"
    - "폴링 중단을 JS 로 끄지 않는다. running 이 아닌 응답에는 hx-trigger 가 아예 없다"

key-files:
  created:
    - webapp/argv.py
    - webapp/jobs.py
    - webapp/tests/test_argv.py
    - webapp/tests/test_jobs.py
    - webapp/tests/test_routes_jobs.py
  modified:
    - webapp/routes/jobs.py
    - webapp/templates/_job_panel.html
    - webapp/templates/board.html
    - .planning/phases/01-board-bid-raise/01-VALIDATION.md

key-decisions:
  - "쓰기 잡 가드를 create_job 의 **맨 앞**으로 옮겼다 — 어차피 409 될 작업 때문에 run-dir/web 에 대상 파일을 떨구지 않으려고"
  - "jobs.run_dir 컬럼에서 NOT NULL 을 뺐다 — prep 의 회차명은 CLI 가 오늘 날짜로 정한다(웹앱이 미리 지어내면 진실이 둘)"
  - "폼 파싱에 request.form() 을 안 쓴다 — Starlette 이 urlencoded 에도 python-multipart 를 요구한다(실측). parse_qsl 로 충분"
  - "작업 패널이 hx-swap=outerHTML 로 자기 자신을 교체한다 — innerHTML 이면 같은 id 의 섹션이 중첩된다"
  - "POST/GET 응답이 HX-Request 헤더로 HTML/JSON 을 가른다 — 화면은 JS 0줄, 스케줄러·curl 은 JSON"
  - "GET 핸들러를 라우터 파일 맨 아래에 모았다 — V-SAFE-01d 스캐너가 GET 데코레이터 뒤 60줄을 훑기 때문"
  - "종료코드를 모르면 지어내지 않는다 — 인메모리 Popen 에 없고 pid 도 죽었으면 orphaned (복구는 Phase 2)"

patterns-established:
  - "테스트가 감시하는 문자열(sys.executable·셸 경유 실행)은 런타임 파일의 주석에도 쓰지 않는다"
  - "프로세스 그룹 시그널 테스트는 fork + setpgid 로 '가짜 서버'를 만들어 그 그룹만 몰살한다 (러너를 죽이지 않고 진짜로 쏜다)"
  - "합성 잡(argv_override)은 테스트 전용 경로. 운영 라우트는 kind 가 고정이라 구조적으로 닿지 않는다"

requirements-completed: [ENG-01, ENG-07]

# Metrics
duration: 47min
completed: 2026-09-20
---

# Phase 1 Plan 05: 작업 엔진 — 버튼 하나로 CLI 를 띄운다 Summary

**보드의 버튼이 `.venv/bin/python3 run_ads.py` 를 세션 분리된 자식으로 띄우고, 화면은 즉시 돌아오며, 쓰기 작업은 전역에서 한 번에 하나만 돈다 — 이후 5개 버튼이 전부 올라탈 실행 틀이 굳었다.**

## Performance

- **Duration:** 47분
- **Tasks:** 3/3 (TDD 2건 = RED/GREEN 커밋 4개 + 기능 커밋 1개)
- **Files:** 9 (신규 5 · 수정 4)
- **테스트:** 웹앱 89개 전량 green (이번에 +39) · CLI 100개 불변

## Accomplishments

### Task 1 — `webapp/argv.py` (TDD: `08395a7` RED → `48a34c2` GREEN)

argv 를 조립하는 곳이 저장소에 **하나**다. 그 하나에 세 겹이 걸려 있다:
`subcommand` 는 `Literal` 화이트리스트, 계정 alias 는 `^[A-Za-z0-9_-]+$`, 결과는 리스트라
셸을 안 거친다. 그래서 계정 이름에 `;rm -rf ~` 를 넣으면 Pydantic 이 거부하고,
설령 통과해도 "그런 이름의 계정 없음" 으로 끝난다.

**`PY_CLI` 는 `.venv/bin/python3` 로 못박았다.** 웹앱은 `.venv-web` 에서 도는데 CLI 는
selenium·openpyxl 이 깔린 `.venv` 가 필요하다. 저장소의 다른 스크립트들이 현재 인터프리터로
자식을 띄우는 건 그들이 CLI 와 같은 venv 안에 있기 때문이고, 웹앱은 다르다 —
그 차이를 주석과 테스트 2개(`test_sys_executable_을_쓰지_않는다`,
`test_문자열로_명령을_만드는_코드가_없다`)가 웹앱 런타임 전체에서 상시 감시한다.

**`--account` 빈 리스트 함정**이 한 줄로 막혔다: `accounts` 가 비면 플래그를 **아예 안 붙인다.**
`run_ads.py` 의 `--account` 는 `nargs="*"` 라 값 없이 붙이면 `[]` → falsy → **전 계정**이 된다.
한 계정(3분)만 돌리려다 4계정(12분)을 돌리는 사고가 거기서 난다.

`prefix` 필드는 Phase 2 의 `caffeinate -i` 자리다. 지금은 항상 비어 있지만 있어야 그때 한 줄로 끝난다.

### Task 2 — `webapp/jobs.py` (TDD: `fa4b729` RED → `78ba4fb` GREEN)

`create_job` 이 **HTTP 를 모른다.** `grep -c 'fastapi\|Request' webapp/jobs.py` = 0 이고
테스트가 그걸 기계로 지킨다. v2 의 APScheduler 는 라우터를 거치지 않고 이 함수를 그대로 부른다.

`spawn` 의 네 인자가 각각 실측된 실패를 막는다:

| 인자 | 없으면 |
|---|---|
| `PYTHONUNBUFFERED=1` | 0.5초 시점 로그파일 **0바이트** — 10분짜리 `prep` 이 10분 내내 빈 화면 |
| `start_new_session=True` | `uvicorn --reload` 재시작에 자식이 같이 죽는다 |
| `stdin=DEVNULL` | 자식이 입력을 기다리며 영원히 멈춘다 |
| `cwd=repo_root()` | `run_ads.py` 의 `lib/eroomlib` 탐색이 깨진다 |

**Pitfall 3 가드가 들어갔다.** `run_bids` 가 `before_bids_<alias>.json` 과 `ledger/<alias>.json` 을
읽고-병합하고-통째로 다시 쓰는데 락이 없다. 겹치면 백업 항목이 사라지고 **그 소재는 영영
되돌릴 수 없다.** 그래서 쓰기 잡(`prep`·`bids_commit`·`revert_only`·`revert_all`)은 전역 1개다.
가드 검사와 INSERT 를 `BEGIN IMMEDIATE` 한 트랜잭션에 묶어, 스레드풀에서 두 요청이 겹쳐도
"둘 다 비었네" 로 둘 다 들어가지 않는다. 미리보기·판정은 아무것도 안 쓰므로 가드에서 뺐다 —
쓰기가 아닌 것까지 막는 가드는 사람이 가드를 끄게 만든다.

`_reap()` 이 가드보다 먼저 돈다. 이게 없으면 끝난 작업의 행이 `running` 으로 남아
**아무것도 안 도는데 409** 가 된다. 종료코드는 인메모리 `Popen.poll()` 로 읽고
(`--workers 1` 전제 — Pitfall 9), 맵에 없고 pid 도 죽었으면 **지어내지 않고** `orphaned` 로 둔다.

`test_자식은_서버_종료를_견딘다` 는 진짜로 `killpg` 를 쏜다. pytest 그룹에 쏘면 러너가 죽으므로
`fork` 한 '가짜 서버' 가 `setpgid` 로 자기 그룹을 새로 판 뒤 그 그룹을 몰살한다 — 가짜 서버는
죽고 세션이 분리된 손자만 살아남는다.

### Task 3 — 라우트 + 버튼 (`88531f4`)

라우트는 얇다: 요청 풀기 → 예외 번역(`BusyError`→409, `ValueError`→400) → 응답 모양 선택.
**kind 는 경로마다 고정**이라 클라이언트가 작업 종류도, `argv_override` 도 고르지 못한다(T-1-23).
`GET /jobs`·`GET /jobs/{id}` 는 읽기 전용이고 **파일 맨 아래**에 모았다 — `V-SAFE-01d` 스캐너가
GET 데코레이터 뒤 60줄을 훑기 때문이다.

보드 상단에 **새로 수집**·**판정 다시** 버튼이 붙었다. `hx-include="#f-acct"` 라 계정 필터를
걸어 두면 그 계정만 돌고, 아무것도 안 고르면 전 계정이다. `hx-disabled-elt="this"` 로
3분짜리 작업에서 두 번 눌리는 것을 막고, 409 는 배너로 사유를 띄운다.
안내 문구는 OQ-4 확정대로 **"광고를 바꾸지는 않는다"** 지 "광고 API 에 아무것도 안 쓴다" 가 아니다
(`prep` 은 통계를 받으려고 리포트 잡을 만든다).

작업 패널은 `running` 일 때만 `hx-trigger="every 2s"` 를 달고 자기 자신을 `outerHTML` 로 교체한다.
끝나면 그 속성이 없는 HTML 이 오므로 **폴링이 저절로 멈춘다** — 끄는 코드가 없다.

## 살아 있는 서버로 확인한 것 (광고 API 호출 0)

`POST /jobs/prep {"accounts":["zzfakeacct"]}` 로 **전 사슬을 실제로 태웠다.**
없는 계정이라 CLI 가 네트워크를 타기 전에 `계정이 없다 — ~/.eroom/naver-ads.json 을 확인해라`
를 찍고 exit 1 한다:

```
POST → {"id":"15748eea…","status":"running","elapsed_sec":0.5}   ← 즉시 돌아온다
2초 후 → {"status":"failed","exit_code":1,"elapsed_sec":7.0}
webapp-logs/15748eea….log → 계정이 없다 — ~/.eroom/naver-ads.json 을 확인해라
```

HTTP → `create_job` → `.venv/bin/python3 run_ads.py prep --account zzfakeacct` → 로그파일 →
종료 감지 → 화면 조각(`실패 · 0분 7초`)까지 한 번에 확인됐다.
`cmd_prep` 이 만든 빈 오늘자 run-dir 은 정리했다(`result.json` 이 없어 보드 목록엔 안 잡힌다).

## Task Commits

| # | 태스크 | 커밋 |
|---|---|---|
| 1 | argv 조립 (RED) | `08395a7` |
| 1 | argv 조립 (GREEN) | `48a34c2` |
| 2 | 잡 엔진 (RED) | `fa4b729` |
| 2 | 잡 엔진 (GREEN) | `78ba4fb` |
| 3 | 라우트 + 버튼 + 라우터 테스트 | `88531f4` |

## Verification

| 항목 | 결과 |
|---|---|
| `.venv-web/bin/pytest webapp/tests -q` | **89 passed** (test_argv 12 · test_jobs 15 · test_routes_jobs 12 + 기존 50) |
| `bash webapp/tests/no_commit_guard.sh` | exit 0 |
| `CT_DEV_TOKEN=… bash webapp/tests/security_curl.sh` | **8/8 PASS** |
| `CT_DEV_TOKEN=… bash webapp/tests/board_cdp.sh` | **전량 PASS** (보드 안 깨짐) |
| CLI 회귀 6파일 | **전부 exit=0** (100 tests 불변) |
| `grep -c 'fastapi\|Request' webapp/jobs.py` | 0 |
| `grep -c 'board_cache\|job_locks' webapp/jobs.py` | 0 |
| 런타임 `sys.executable` | 0건 |

## Decisions Made

- **가드를 `create_job` 맨 앞으로.** 플랜의 ①②③④⑤⑥ 순서는 회차 검증 → 대상 파일 → 가드였는데,
  그러면 어차피 409 될 작업이 `run-dir/web/targets_*.json` 을 떨구고 간다. 가드를 먼저 보게 바꿨다.
- **`run_dir` NOT NULL 제거.** `prep` 의 회차명은 CLI 가 오늘 날짜로 정한다. 웹앱이 미리 지어내면
  진실이 둘이 되고, 자정 근처에서 어긋난다.
- **`request.form()` 대신 `parse_qsl`.** Starlette 은 urlencoded 폼에도 `python-multipart` 를
  요구한다(실측 `AssertionError`). 파일 업로드가 없는 화면에 멀티파트 파서를 깔 이유가 없다.
- **응답 모양을 `HX-Request` 로 가른다.** 화면은 HTML 조각(JS 0줄), 스케줄러·curl 은 JSON.
- **쿠키 게이트를 `GET /jobs*` 에도.** `/healthz` 만 무조건 열린 창으로 남긴다 —
  화면이 고장났을 때 "서버가 죽은 건가" 를 가르는 유일한 창이라 그건 인증에 묶지 않는다.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `request.form()` 이 `python-multipart` 를 요구해 htmx POST 가 500**
- **Found during:** Task 3 스모크
- **Issue:** htmx 기본 인코딩이 urlencoded 인데 Starlette 이 `parse_options_header` 부재로
  `AssertionError: The python-multipart library must be installed` 를 던졌다. 버튼이 통째로 안 돈다.
- **Fix:** 의존성을 늘리지 않고 stdlib `parse_qsl` 로 본문을 직접 풀었다(3줄). 이유를 docstring 에 남겼다.
- **Files:** `webapp/routes/jobs.py`
- **Commit:** `88531f4`

**2. [Rule 1 - Bug] 가드가 대상 파일을 떨군 **뒤에** 걸려 run-dir 에 쓰레기가 남는다**
- **Found during:** Task 2 GREEN
- **Issue:** 플랜 순서대로면 `bids_commit` 이 409 로 거부돼도 `targets_<job>.json` 은 이미 쓰인 상태다.
- **Fix:** 가드를 트랜잭션 맨 앞으로. 검증·파일 쓰기·argv 조립이 전부 가드 뒤로 갔다.
- **Files:** `webapp/jobs.py`
- **Commit:** `78ba4fb`

**3. [Rule 2 - Missing] 라우터 계약에 자동 테스트가 없었다**
- **Found during:** Task 3
- **Issue:** 플랜의 Task 3 검증은 일회성 인라인 명령 하나였다. 403/400/409 번역과
  "클라이언트가 kind·argv 를 못 고른다"(T-1-23)는 **보안 동작**인데 회귀 방어가 없었다.
- **Fix:** `webapp/tests/test_routes_jobs.py` 12개 추가. `jobs.create_job` 을 가로채
  실제 CLI 는 한 번도 안 띄운다. VALIDATION.md 에 `✚라우터-01` 행으로 등록했다.
- **Files:** `webapp/tests/test_routes_jobs.py` · `01-VALIDATION.md`
- **Commit:** `88531f4`

**4. [Rule 1 - Bug] 테스트가 감시하는 문자열이 런타임 주석에 있어 자기 테스트를 깨뜨림**
- **Found during:** Task 1 GREEN
- **Issue:** `webapp/argv.py` 주석에 `sys.executable`·셸 경유 실행 문자열을 설명으로 적었더니
  "웹앱 런타임에 그 문자열이 0건" 을 확인하는 테스트가 빨개졌다.
- **Fix:** 금지 토큰을 쓰지 않고 같은 내용을 설명했다. 플랜의 `<done>` 이 요구한
  `grep -rn 'sys.executable' webapp/` 0건도 이걸로 충족된다.
- **Files:** `webapp/argv.py`
- **Commit:** `48a34c2`

### 플랜과 다르게 한 것 (의도적)

- **작업 패널 swap 을 `innerHTML` → `outerHTML` 로.** 플랜은 `hx-target="#job-panel"` +
  `hx-swap="innerHTML"` 인데, 조각이 `<section id="job-panel">` 을 스스로 품어야
  폴링 속성을 갈아끼울 수 있다. innerHTML 이면 같은 id 의 섹션이 중첩된다.
- **`GET /jobs/{id}` 가 JSON 만이 아니라 HTML 조각도 낸다.** 플랜의 JSON 키 9개는 그대로 유지하되,
  htmx 요청에는 패널을 돌려준다 — 안 그러면 폴링이 JSON 문자열을 화면에 붙인다.

## Known Stubs

| 위치 | 내용 | 해소 |
|---|---|---|
| `_job_panel.html` 의 `<pre id="job-log">` | 실시간 로그 자리가 비어 있다. 지금은 상태 폴링까지 | **Plan 01-06** 이 SSE 로 채운다 (로그파일은 이미 쌓이고 있다) |
| `jobs.py` 의 `bids_*`·`revert_*` kind | argv 조립은 되지만 부르는 라우트가 없다 | Plan 01-07(미리보기) · 01-08(실행) · 01-09(되돌리기) |
| `status='orphaned'` | 표시만 하고 복구는 안 한다 | Phase 2 (ENG-05) |
| `AdsArgv.prefix` | 항상 빈 리스트 | Phase 2 (ENG-06 `caffeinate -i`) |

의도된 공백이다 — 이 플랜의 목표(`prep` 을 위험 0 으로 태워 실행 틀을 굳히는 것)는 전부 달성됐다.

## Threat Flags

없음. 이 플랜이 만든 표면(POST 2개 · GET 2개)은 전부 `<threat_model>` 의 T-1-09·T-1-10·T-1-11·
T-1-01b·T-1-03c·T-1-23 에 이미 들어 있고, 각각 자동 테스트가 붙었다.

## Next

- **Plan 01-06:** 로그 오프셋 tail + SSE. 로그파일은 이미 실시간으로 쌓이고 있으니
  `_job_panel.html` 의 빈 `<pre>` 에 붙이면 된다. **파이프를 쓰지 마라** — 파일 tail 이라야
  "탭 닫았다 열기" 가 성립한다.
- **수동 확인 1건(사용자):** 실제 `prep --account <진짜계정>` 을 화면에서 눌러
  401/403 없이 완주하는지 (광고 API 자격증명 유효성 — VALIDATION Manual-Only, OQ-6).

## Self-Check: PASSED

- 생성 파일 7개 전부 디스크에 존재
- 태스크 커밋 5개(`08395a7`·`48a34c2`·`fa4b729`·`78ba4fb`·`88531f4`) 전부 git 이력에 존재
