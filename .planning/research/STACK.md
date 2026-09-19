# Stack Research

**Domain:** 로컬 단독 실행 웹 관제탑 (기존 Python CLI 래퍼 + 상품 보드 + 장기작업 실행기)
**Researched:** 2026-09-19
**Confidence:** HIGH (버전·호환성은 PyPI/npm 레지스트리와 공식 문서로 직접 확인. 프레임워크 선택 판단은 MEDIUM~HIGH)

---

## 결론 먼저

| 질문 | 답 |
|---|---|
| CLI 를 import 할까 subprocess 할까 | **subprocess.** 실제 코드를 읽고 내린 결론이다 — import 는 지금 구조에서 작동조차 안 한다 (아래 §핵심결정 1) |
| 태스크 큐(Celery/RQ/Huey)가 필요한가 | **아니다.** 내구성은 이미 CLI 의 run-dir 체크포인트가 갖고 있다. 브로커는 진실을 둘로 만든다 |
| 진행 스트리밍은 SSE / WS / 폴링 | **SSE.** 단, 파이프를 직접 흘리지 말고 **로그파일을 오프셋부터 tail** 해야 "브라우저 닫았다 재접속" 요구가 성립한다 (§핵심결정 3) |
| 프론트엔드 | **서버 렌더(Jinja2) + htmx + Tabulator CDN.** 빌드체인 0 |
| DB | **stdlib `sqlite3`.** ORM·마이그레이션 도구 없음. 보드 테이블은 재생성 가능한 캐시다 |

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | **3.12.13** (현행 유지) | 웹앱 런타임 | 기존 `.venv` 와 같은 메이저. 3.13/3.14 로 올릴 이유가 없다 — 얻는 게 없고 selenium·pillow 재빌드 리스크만 생긴다 |
| FastAPI | **0.141.1** (2026-07-29) | HTTP 엔드포인트 · JSON API · 폼 처리 | ① 3단계(스케줄 자동화)가 로드맵에 있다 → 스케줄러가 브라우저 없이 때릴 HTTP 표면이 어차피 필요하다. ② async 로 SSE 스트림 수십 개를 스레드 없이 유지한다. ③ Pydantic 으로 dry-run 결과 스키마를 한 곳에 정의 |
| Uvicorn | **0.53.0** (2026-09-14) | ASGI 서버 | FastAPI 표준 조합. **반드시 `--workers 1`** (§치명 주의) |
| Starlette | **1.6.0** (2026-08-08) | FastAPI 하부 (직접 설치 안 함) | FastAPI 0.141.1 이 `starlette>=0.46.0` 으로 상한 없이 받고, 리포지토리가 실제로 1.6.0 으로 올려 테스트 중임을 확인 |
| Pydantic | **2.13.5** (2026-08-28) | dry-run 미리보기 / 작업 요청 스키마 | "판정 → 미리보기 → 실행" 3단이 구조화된 타입 없이는 화면마다 딕셔너리를 손으로 까게 된다 |
| Jinja2 | **3.1.6** | 서버 사이드 HTML | Python 사람이 쓰는 템플릿. SPA 상태관리를 통째로 안 한다 |
| SQLite | **stdlib `sqlite3`** (시스템 3.51.0) | 잡 레지스트리 · 보드 캐시 · 동시성 락 | 파일 1개. 서버 재시작해도 잡 이력이 남는다. 별도 프로세스 0 |
| htmx | **2.0.10** | 버튼 → 부분 갱신, 폼 제출 | ⚠️ **4.0.0 이 2026-08-28 출시됐지만 쓰지 마라** — 공식 사이트가 "2.x 사용자가 실수로 올라가지 않도록 npm `latest` 를 안 옮겼고, 2027년 중 옮길 예정"이라고 명시. 확장(sse/ws)도 2.x 기준이다 |
| htmx-ext-sse | **2.2.4** | `sse-connect`/`sse-swap` 선언만으로 진행로그 수신 | JS 를 한 줄도 안 쓰고 SSE 를 붙인다 |
| Tabulator | **6.5.3** | 상품 보드 테이블 | 가상 DOM 렌더링·정렬·다중 필터·행 다중선택이 **전부 내장**이고 CDN `<script>` 한 줄로 끝. 수천 행이 목표 규모에 정확히 맞는다 |
| sse-starlette | **3.4.11** (2026-09-05) | `EventSourceResponse` | Starlette 1.6.0 `responses.py` 에 SSE 클래스가 **없음을 직접 확인**했다. 손으로 짜면 클라이언트 끊김 감지·keepalive ping 을 직접 관리해야 한다 |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| uv | **0.12.2** (이미 설치됨) | 웹앱 전용 venv 생성·의존성 관리 | 처음부터. `uv venv .venv-web && uv pip install ...` |
| Pico.css | **2.1.1** | classless CSS | 클래스를 안 붙여도 `<table>`·`<button>` 이 봐줄 만해진다. 1인 도구에 디자인 시스템은 사치 |
| Alpine.js | **3.17.3** | 체크박스 전체선택, 모달 토글 등 순수 클라이언트 상태 | htmx 로 서버 왕복하기엔 과한 UI 조작이 생겼을 때만. 처음엔 넣지 마라 |
| APScheduler | **3.11.3** (2026-06-28) | 3단계 스케줄 자동화 | **3단계 진입 시점에만.** v1 에는 넣지 않는다. ⚠️ 4.0 은 아직 알파다 (마지막 `4.0.0a6` 가 2025-04-27, 1년 넘게 정체) — 3.11.x 를 써라 |
| httpx | 0.28.1 | 서버 내부 자기호출 / 통합테스트 | FastAPI `TestClient` 가 이미 의존. 별도 설치 불필요 |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `uvicorn --reload` | 개발 중 자동 재시작 | 재시작이 실행 중인 자식 프로세스를 죽이지 않도록, 잡은 `start_new_session=True` 로 띄운다 (§핵심결정 2) |
| `caffeinate -i` | 맥북 잠들어서 폴링 끊기는 것 방지 | man 페이지 확인: `-i` = idle sleep 방지, utility 지정 시 그 프로세스 수명 동안만 유지. **장기 잡은 `caffeinate -i .venv/bin/python3 ...` 로 감싼다** — 수십 분 폴링을 노트북에서 돌리는 이 프로젝트에 직결된다 |
| launchd LaunchAgent | 서버 상시 기동 | "브라우저 닫아도 살아있게" 는 서버가 살아있어야 성립. tmux 세션에 띄워도 되지만 로그인 때마다 수동이다 |
| `sqlite3` CLI | 잡 상태 직접 조회 | 화면이 고장나도 `sqlite3 jobs.db 'select * from jobs'` 로 진상 파악 |

---

## 핵심 결정 1 — import 가 아니라 subprocess (확신도: **HIGH**)

프로젝트 제약이 "검증된 CLI 를 안 건드린다" 인데, 이건 취향 문제가 아니라 **지금 코드 구조상 import 가 실제로 깨진다.** 실물을 읽고 확인한 근거 6개:

**1. 모듈 이름이 전역에서 충돌한다 (결정적)**
`run_ads.py:18` 이 `sys.path.insert(0, <자기 scripts 디렉터리>)` 를 하고 `collect`, `reports`, `ledger`, `bids`, `prune`, `nvad` 를 **최상위 이름으로** import 한다. 네임스페이스 패키지가 아니다. 웹앱 한 프로세스에 `naver-ads-weekly/scripts` 와 `coupang-candidates/scripts` 를 같이 올리면 먼저 insert 한 쪽이 이긴다. `eroomlib.runner` 에도 `signals.py`·`inventory.py` 가 따로 있다. 이걸 고치려면 CLI 를 패키지로 재구성해야 하고, 그게 곧 "재작성 금지" 제약 위반이다.

**2. 계정 자격증명이 `os.environ` 으로 주입된다 (치명)**
`run_yong.py` 가 `BULSAJA_MCP_URL/TOKEN` 을 환경변수로 넣어 자식을 띄운다. import 방식이면 `os.environ` 이 웹서버 **프로세스 전역**이라, 용쌤 잡과 용팀장 잡이 겹치는 순간 토큰이 섞인다. 이 워크스페이스는 계정 전환 사고를 이미 겪어 메모리에 남겨둔 상태다. subprocess 는 `env=` 인자만으로 잡별 격리가 **구조적으로** 보장된다.

**3. CLI 가 `sys.exit()` 로 끝난다**
`detail_batch.py` 는 검증 실패 시 `⛔` 찍고 종료하고, argparse 는 인자 오류에 `SystemExit` 을 던진다. in-process 면 이게 웹서버를 죽인다.

**4. 블로킹 코드다**
`time.sleep(args.poll_interval)` + 동기 `requests`. async FastAPI 안에서 돌리면 이벤트 루프가 멈춘다. 스레드풀로 밀어내도 셀레니움(`.venv` 에 selenium 4.47 설치됨)이 크래시하면 서버가 같이 간다.

**5. 반환 채널이 이미 있다 — 새로 만들 게 없다**
CLI 는 벌써 `print(..., flush=True)` 로 줄 단위 진행을 뱉고, 끝에 `###DETAIL### 완료 N (신규 M + 기작업스킵 K)` 같은 **기계가 읽을 센티널**을 찍고, 구조화 결과는 run-dir JSON(`result.json`·`detail_status.json`·`copied.jsonl`)에 남긴다. subprocess 의 "구조화된 값을 못 받는다"는 통상적 단점이 **이 프로젝트엔 해당 없다.** 계약이 이미 존재한다.

**6. zero-diff 속성**
subprocess 면 CLI 는 바이트 단위로 안 변하고, 손으로도 Claude Code 스킬로도 계속 돌아간다. import 면 웹앱이 두 번째 호출자가 되어 시그니처를 서서히 자기 쪽으로 구부린다. 제약이 "희망사항"이 아니라 "강제"가 되는 쪽이 subprocess 다.

### 진짜 비용 (정직하게)

- 인터프리터 기동 0.2~0.5초/호출 — 분 단위로 도는 잡에 무의미
- 예외 트레이스백을 객체로 못 받는다 → **완화:** 종료코드 + stderr 마지막 N줄 + run-dir 의 결과 JSON, 3개를 잡 레코드에 보존
- 타입 안전성 없음 → **완화:** 웹앱이 부르는 서브커맨드·인자를 Pydantic 모델로 한 곳에 정의하고 거기서만 argv 를 조립

### 세 번째 길 — 보드 데이터는 아예 실행하지 않는다 (권장)

| 무엇을 | 어떻게 |
|---|---|
| 보드 테이블 표시 | **CLI 가 이미 써 둔 run-dir JSON 산출물을 읽는다.** import 도 subprocess 도 아니다 |
| 버튼 실행 | subprocess |
| 순수 함수 재사용 (`coupang_rules.py` 마진공식, `ads_rules.py` 규칙) | **하지 마라.** 마진 공식을 웹앱이 다시 계산하면 진실이 둘이 된다 — 프로젝트가 이미 "중복방지 대장 신설 금지"로 거부한 바로 그 패턴이다. 판정값은 CLI 산출물에서만 읽는다 |

---

## 핵심 결정 2 — 태스크 큐는 쓰지 않는다 (확신도: **HIGH**)

### 왜 정당화되지 않는가

브로커의 존재 이유는 **내구성·재시도·분산**이다. 이 프로젝트는 셋 다 이미 다른 곳에서 해결돼 있다.

| 큐가 주는 것 | 이 프로젝트의 현실 |
|---|---|
| 잡 내구성 (죽어도 재개) | **CLI 가 이미 갖고 있다.** `detail_batch --poll-only`, `copied.jsonl`, `run-dir` 체크포인트. 브로커를 넣으면 **재개 상태의 정본이 둘**이 된다 — 큐의 잡 레코드 vs run-dir 체크포인트. 둘이 어긋나면 크레딧 이중 지불이다 |
| 재시도 | `--retry-failed`, 중복 대기열 재시도가 CLI 안에 있다. 큐 레벨 재시도는 **전체 잡을 처음부터 다시 돌려** 오히려 위험하다 |
| 워커 확장 | 사용자 1명. 동시 잡 2~3개 |
| 지연 실행 | v1 out of scope. 3단계에서 APScheduler 로 충분 |

### 대신 이렇게 (총 코드 ~150줄)

```
POST /jobs → subprocess.Popen(argv, env=..., cwd=...,
                              stdout=로그파일, stderr=합류,
                              start_new_session=True)   # ← 서버 --reload 나 종료에 안 딸려 죽음
           → SQLite jobs 행 삽입 (id, kind, argv, pid, log_path, run_dir, state, started_at)
백그라운드 감시 태스크 → 종료 감지 → exit_code·finished_at 기록
서버 부팅 시 → state='running' 행의 pid 생존 확인 → 죽었으면 'orphaned' 로 마킹
```

**큐 대신 반드시 넣어야 할 것은 "잡 락"이다.** 큐가 주는 기능 중 여기서 진짜 필요한 건 동시성 제어 하나뿐이다:

```sql
-- 같은 자원에 두 잡이 동시에 붙는 것을 막는다.
-- 예: 같은 불사자 계정의 detail_batch 2개, bids --commit 2번 클릭
CREATE TABLE job_locks (resource TEXT PRIMARY KEY, job_id INTEGER, acquired_at TEXT);
```
`INSERT` 가 UNIQUE 위반으로 실패하면 거절. SQLite 트랜잭션이 원자성을 보장한다. 이게 브로커 도입의 유일한 정당 사유였고, 3줄로 대체된다.

### 큐를 다시 검토할 조건 (선을 미리 그어둔다)

아래 중 **둘 이상**이 실제로 발생하면 그때 **Huey 3.4.0 + SqliteHuey** 를 검토한다 (Celery/RQ 아님 — Redis 가 필요 없는 건 Huey 뿐):
- 대기 중인 잡이 상시 5개 이상 쌓인다
- 잡 우선순위가 필요해진다
- 잡 실패 후 자동 백오프 재시도를 큐 레벨에서 걸어야 한다

---

## 핵심 결정 3 — SSE. 단, 파이프가 아니라 로그파일을 tail (확신도: **HIGH**)

### SSE vs WebSocket vs 폴링

| 방식 | 판정 | 이유 |
|---|---|---|
| **SSE** | ✅ **채택** | 데이터가 서버→클라 **단방향**이다 (진행 로그). 브라우저 `EventSource` 가 **자동 재연결 + `Last-Event-ID` 헤더 재전송**을 공짜로 준다 — "재접속하면 이어서 보기" 요구가 브라우저 내장 기능으로 풀린다. 평문 HTTP 라 `curl -N` 으로 디버깅된다. htmx-ext-sse 로 JS 0줄 |
| WebSocket | ❌ 제외 | 양방향성을 안 쓴다. 재연결·하트비트·재개 오프셋을 전부 직접 짜야 한다 (EventSource 가 이미 하는 일). 프록시/슬립 복귀 시 끊김 처리도 수작업 |
| 폴링 | 🟡 허용 가능한 후퇴 | `GET /jobs/{id}/log?from=N` 2초 폴링은 20줄이고 1인 로컬에선 솔직히 문제없다. SSE 가 막히면 여기로 내려와라. 다만 "실시간"이 2초 계단이 된다 |

### 이게 핵심이다 — 파이프 직결 금지

**틀린 구현:** `Popen(stdout=PIPE)` → 파이프를 읽어 SSE 로 바로 흘린다.
→ 브라우저를 닫았다 열면 **그 사이 출력이 영영 사라진다.** 요구사항 3이 깨진다.

**맞는 구현:**
```
자식 stdout/stderr → 로그파일에 직접 리다이렉트 (append)
GET /jobs/{id}/stream  (Last-Event-ID: <줄번호>)
   1) 로그파일을 <줄번호>+1 부터 읽어 전부 재생 (=놓친 구간 복원)
   2) EOF 도달 후 tail 모드로 전환, 새 줄이 생기면 push
   3) 각 이벤트에 id: <줄번호> 를 박는다   ← 재연결 재개의 열쇠
   4) 잡 종료 시 종료 이벤트 1발 후 스트림 종료
```
로그파일이 단일 정본이라 서버가 재시작돼도, 자식이 여전히 살아있어도, 화면을 10번 새로고침해도 같은 결과가 나온다.

### HTTP/1.1 동시 연결 한계 — 스트림을 잡마다 열지 마라

브라우저는 오리진당 동시 연결을 ~6개로 제한한다. 잡 5개를 각각 SSE 로 열면 나머지 일반 요청이 큐에 걸려 **화면 전체가 먹통처럼 보인다.** Uvicorn 은 평문 HTTP/1.1 이라 HTTP/2 멀티플렉싱도 없다.

→ **스트림은 페이지당 1개.** 한 엔드포인트가 구독 중인 여러 잡의 줄을 `event: job-42` 처럼 이름으로 구분해 흘린다.

---

## Installation

```bash
# 웹앱 전용 venv — 기존 .venv 는 손대지 않는다.
# subprocess 로 부르므로 의존성을 섞을 이유가 전혀 없다. CLI 는 계속 .venv/bin/python3 로 돈다.
cd /Users/choiyongsmacbook/Documents/yongtimjang_claudecode
uv venv .venv-web --python 3.12

uv pip install --python .venv-web/bin/python \
  "fastapi==0.141.1" \
  "uvicorn[standard]==0.53.0" \
  "jinja2==3.1.6" \
  "sse-starlette==3.4.11" \
  "python-multipart==0.0.32"

# pydantic 2.13.5 · starlette 1.6.0 은 fastapi 가 끌고 온다. 직접 pin 하지 마라.
# sqlite3 는 stdlib.

# 3단계(스케줄)에 진입할 때만:
# uv pip install --python .venv-web/bin/python "apscheduler==3.11.3"
```

프론트엔드는 **npm 설치 없음.** CDN `<script>` 3줄:
```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@2.1.1/css/pico.min.css">
<script src="https://cdn.jsdelivr.net/npm/htmx.org@2.0.10/dist/htmx.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/htmx-ext-sse@2.2.4/sse.js"></script>
<link  href="https://cdn.jsdelivr.net/npm/tabulator-tables@6.5.3/dist/css/tabulator.min.css" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/tabulator-tables@6.5.3/dist/js/tabulator.min.js"></script>
```
> 로컬 전용이지만 CDN 이 끊기면 화면이 안 뜬다. 5개 파일을 `static/vendor/` 에 받아두고 그걸 서빙하는 쪽이 낫다 — 총 ~600KB, 오프라인에서도 돈다.

### 실행

```bash
# --workers 1 이 협상 불가다 (§What NOT to Use 참조)
.venv-web/bin/uvicorn app:app --host 127.0.0.1 --port 8765 --workers 1
```
`--host 127.0.0.1` 이 인증을 대신한다. `0.0.0.0` 으로 바꾸는 순간 인증 없는 마켓 쓰기 API 가 같은 와이파이에 열린다.

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| FastAPI + htmx | **NiceGUI 3.17.1** | HTML 을 아예 쓰기 싫을 때. 솔직히 이게 유일하게 진지한 대안이다 — 진짜 async 이고 `ui.log` 로 로그 스트리밍이 내장이라 초기 개발이 빠르다. **버린 이유:** ① 상태가 클라이언트 세션에 묶여 "브라우저 닫고 재접속" 이 프레임워크와 싸우는 지점이 된다 ② 3단계 스케줄러가 때릴 HTTP 표면이 안 생긴다 ③ 테이블 컴포넌트가 수천 행 복합 필터에서 Tabulator 보다 약하다. **확신도 MEDIUM — 취향이 섞인 판단이다** |
| FastAPI + htmx | Flask 3.1.3 | 동기 코드만 쓰겠다면. SSE 스트림 하나당 스레드 하나를 먹고, 장기 잡 감시 태스크를 붙이기가 더 번거롭다 |
| Tabulator | AG Grid Community 36.2.0 | 행 그룹핑·트리 뷰가 필요해질 때. 더 무겁고, 탐나는 기능 상당수가 Enterprise 유료 |
| Tabulator | TanStack Table 9.2.4 | React 앱을 이미 갖고 있을 때만. headless 라 셀·정렬 UI 를 전부 직접 그려야 하고 빌드체인이 필수다 |
| stdlib sqlite3 | SQLModel / SQLAlchemy 2.x | 스키마가 10테이블을 넘고 관계가 복잡해지면. 지금은 테이블 3개(jobs / job_locks / board_cache)다 |
| subprocess 직접 관리 | Huey 3.4.0 (SqliteHuey) | §핵심결정 2 의 "다시 검토할 조건" 충족 시 |
| SSE | 2초 폴링 | SSE 구현이 예상보다 오래 걸리면 주저 없이 후퇴해라. 1인 로컬에서 실질 차이는 작다 |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| **`uvicorn --workers N` (N>1)** | 🔴 **조용히 다 깨진다.** 잡 레지스트리·SSE 구독자 집합이 프로세스마다 갈라져서, 잡을 띄운 워커와 스트림 요청을 받은 워커가 다르면 진행로그가 안 나온다. 재현이 어려운 "가끔 안 보임" 버그로 나타난다 | `--workers 1` 고정. 사용자 1명에 워커 1개면 남는다 |
| **Celery / RQ** | Redis 브로커 + 워커 프로세스 + 결과 백엔드 = 상시 구동 부품 3개 추가. 그리고 잡 진실의 원천이 run-dir 체크포인트와 **둘**이 된다 | subprocess.Popen + SQLite 잡 테이블 |
| **htmx 4.0.0** | 2026-08-28 출시됐지만 htmx.org 가 "npm `latest` 를 의도적으로 안 옮겼다, 2027년 중 옮길 예정"이라 명시. 확장 생태계(sse/ws)와 대부분의 예제가 아직 2.x 기준 | htmx 2.0.10 |
| **APScheduler 4.x** | 아직 알파. 마지막 릴리스가 `4.0.0a6`(2025-04-27)로 1년 넘게 멈춰 있는 반면 3.11.x 는 2026-06 까지 유지보수됐다 | APScheduler 3.11.3 (그것도 3단계 때만) |
| **Docker / docker-compose** | 자격증명 경계만 새로 만든다 — `~/.eroom/naver-ads.json`(600), gws 의 macOS 키체인 토큰, `~/python_work/data` 를 전부 마운트·포워딩해야 한다. 얻는 이식성은 이 프로젝트가 안 쓴다 | 맥북에 네이티브로 실행 |
| **PostgreSQL / Redis** | 동시 쓰기 1명. 서버 프로세스를 늘려 얻는 게 0 | SQLite 파일 1개 |
| **인증 (OAuth / JWT / 세션)** | PROJECT.md 가 명시적으로 out of scope | `--host 127.0.0.1` |
| **React / Next.js / Vite 빌드체인** | Node 24 가 깔려 있긴 하지만, 두 번째 툴체인 + 두 번째 의존성 트리 + dev 서버 = Python 1인 프로젝트에 영구 세금 | Jinja2 서버 렌더 + CDN 스크립트 |
| **Tailwind 빌드 파이프라인** | 로컬 전용 도구에 CSS 컴파일 단계를 붙일 이유가 없다 | Pico.css CDN (classless) |
| **SQLAlchemy + Alembic 마이그레이션** | 보드 테이블은 run-dir 산출물에서 **언제든 재생성 가능한 캐시**다. 마이그레이션이 곧 `DROP TABLE` + 재적재 | stdlib `sqlite3` + 평문 SQL |
| **WebSocket** | 양방향성 미사용. EventSource 가 공짜로 주는 재연결·재개를 직접 구현하게 된다 | SSE |
| **k8s / nginx / gunicorn** | 127.0.0.1:8765 에 단일 사용자 | uvicorn 직접 |
| **CLI 로직을 웹앱에 복제 (마진공식·규칙판정 재구현)** | 진실이 둘이 된다. 프로젝트가 이미 "중복방지 대장 신설 금지"로 거부한 패턴 | 산출물 JSON 을 읽기만 |

---

## Stack Patterns by Variant

**보드 행 수가 5,000 이하면:**
- 전 행을 JSON 한 번에 내려 Tabulator 클라이언트 사이드 정렬·필터
- 필터 조작이 즉각 반응하고 서버 왕복이 없다. 구현이 절반

**보드 행 수가 5,000 초과면:**
- SQLite 에 적재 → Tabulator `ajax` + `filterMode:"remote"` / `sortMode:"remote"` 로 서버 사이드 전환
- 전체 수집상품이 970,695건이니 **"작업 대상"을 어떻게 좁히느냐가 이 분기점을 결정한다.** 1단계 집계 결과를 보고 확정해라

**잡이 5분 이하로만 끝나면:**
- `caffeinate` 불필요, 고아 잡 복구 로직도 사실상 안 탐

**잡이 수십 분 폴링을 포함하면 (= `detail_batch`, 실제 케이스):**
- `caffeinate -i` 로 감싼다 — 맥북 idle sleep 이 폴링을 끊는다
- 서버 부팅 시 고아 잡 스캔 필수 (pid 생존 확인)
- 재개는 새 잡으로 만들지 말고 CLI 의 `--poll-only` 를 태워라. 새 접수를 태우면 크레딧 이중 지불이다

**3단계(스케줄 자동화)로 갈 때:**
- 새 경로를 만들지 마라. APScheduler 가 **v1 과 같은 잡 생성 함수**를 부른다
- v1 설계에서 지켜야 할 것: 잡 생성이 HTTP 핸들러가 아니라 **호출 가능한 함수**에 있고, 핸들러는 그걸 얇게 감싸기만 할 것

---

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| fastapi 0.141.1 | starlette >= 0.46.0 (상한 없음) | 메타데이터 직접 확인. 리포지토리가 실제로 1.6.0 으로 올려 테스트 중 |
| fastapi 0.141.1 | pydantic >= 2.9.0 | v1 호환 레이어에 의존하지 마라 |
| fastapi 0.141.1 | Python >= 3.10 | 3.12.13 OK |
| sse-starlette 3.4.11 | starlette >= 0.49.1 | 1.6.0 이 만족 (PEP440 정렬상 1.6.0 > 0.49.1) |
| fastapi 0.137.0 | — | 브레이킹 체인지는 `router.routes` 가 리스트→트리로 바뀐 것. **내부 구현 세부이고 신규 앱엔 무관.** 릴리스 노트 원문 확인 |
| htmx 2.0.10 | htmx-ext-sse 2.2.4 | 확장은 htmx 2.x 기준. htmx 4 로 올리면 확장 생태계와 갈라진다 |
| Tabulator 6.5.3 | 프레임워크 무관 | 순수 JS. React/Vue 없이 동작 |
| 웹앱 `.venv-web` | CLI `.venv` | **의존성이 겹치지 않는다** — subprocess 경계 덕분. 기존 `.venv` 는 requests/selenium/openpyxl/pillow 만 담은 상태로 유지 |

---

## Sources

- PyPI JSON API (`pypi.org/pypi/<pkg>/json`) — fastapi 0.141.1 / uvicorn 0.53.0 / starlette 1.6.0 / pydantic 2.13.5 / sse-starlette 3.4.11 / huey 3.4.0 / rq 2.12.0 / apscheduler 3.11.3 / jinja2 3.1.6 버전·업로드일·`requires_dist` 직접 조회 — **HIGH**
- npm registry (`registry.npmjs.org`) — htmx.org 2.0.10(dist-tags `next`=4.0.0) / htmx-ext-sse 2.2.4 / tabulator-tables 6.5.3 / @tanstack/table-core 9.2.4 / ag-grid-community 36.2.0 / @picocss/pico 2.1.1 / alpinejs 3.17.3 — **HIGH**
- https://htmx.org/ — "htmx 4.0 has been released! It is not currently marked as `latest` in NPM so that people using the 2.x line are not accidentally upgraded." + 2027년 전환 예정 — **HIGH**
- https://fastapi.tiangolo.com/release-notes/ + GitHub Releases API (tag 0.137.0) — 최신 릴리스 및 브레이킹 체인지 원문 — **HIGH**
- `starlette/responses.py` (GitHub master) — SSE/EventSource 클래스 부재 확인 → sse-starlette 필요 근거 — **HIGH**
- https://tabulator.info/docs/6.5 — 가상 DOM 대용량 렌더링 / 정렬 / 필터 / 행 다중선택 내장 확인 — **HIGH**
- 로컬 코드 실측 — `run_ads.py`(sys.path 삽입 + 최상위 모듈명 import), `detail_batch.py`(`flush=True` 줄 출력, `###DETAIL###` 센티널, `time.sleep` 폴링), `run_yong.py`(env 주입), `.venv/lib/python3.12/site-packages`(48항목, FastAPI 없음), `workspace.toml`(data_root), `uv 0.12.2`·`node 24.19.0`·`sqlite3 3.51.0` 설치 확인 — **HIGH**
- `man caffeinate` (macOS 로컬) — `-i` idle sleep 방지, utility 수명 동안 유지 — **HIGH**
- NiceGUI vs FastAPI 판단, 5,000행 클라이언트/서버 분기 임계치 — 경험 기반 판단, 실측 아님 — **MEDIUM**

---
*Stack research for: 로컬 단독 실행 웹 관제탑 (Python CLI 래퍼)*
*Researched: 2026-09-19*
