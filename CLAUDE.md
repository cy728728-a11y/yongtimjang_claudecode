
## 폴더 구조 (Johnny Decimal)

```
00-inbox/      # 임시 캡처 (20개 미만 유지, 주간 처리)
00-system/     # 시스템 설정, 템플릿, 가이드
10-projects/   # 활성 프로젝트 (시한부)
20-operations/ # 지속적 운영 (종료일 없음)
30-knowledge/  # 지식 (00-wiki + 도메인 아카이브)
40-personal/   # 개인 노트 (daily, weekly, ideas, reflections, todos)
50-resources/  # 외부 자료, 첨부파일
90-archive/    # 완료/중단 항목
```

### 주요 하위 폴더

| 번호 | 폴더 | 용도 |
|------|------|------|
| **00-wiki** | 30-knowledge/ | **지식 위키 (복리 축적). 아래 Wiki Schema 참조** |
| 41-daily | 40-personal/ | Daily Notes (월별: 41-daily/YYYY-MM/) |
| 42-weekly | 40-personal/ | Weekly Review |
| 43-ideas | 40-personal/ | 아이디어 캡처 |
| 44-reflections | 40-personal/ | 회고 및 학습 |
| 46-todos | 40-personal/ | active-todos.md |
| 37-claude-code | 30-knowledge/ | Claude Code 관련 지식 |

## Wiki (30-knowledge/00-wiki/)

지식이 복리로 축적되는 위키. 주제에 대해 물으면 **00-wiki/index.md를 먼저 확인**.

@30-knowledge/00-wiki/SCHEMA.md

## 파일 명명 규칙

| 유형 | 형식 | 예시 |
|------|------|------|
| Daily Note | `YYYY-MM-DD.md` | 2026-04-24.md |
| 주제 노트 | `주제명.md` | thinking-partner.md |
| JD 폴더 | `XX-name` 또는 `XX.YY-name` | 37-claude-code, 37.01-learning |
| 중복 파일명 | JD prefix 필수 | 18-progress-tracker.md |

## Inbox 관리 (00-inbox)

- **목적**: 임시 캡처, 영구 저장소 아님
- **규칙**: 20개 미만 유지
- **주기**: 주간 처리 (Capture → Process → Organize)

## 첨부파일 (50-resources/attachments/)

- 모든 비텍스트 파일 저장
- 명명: `[관련노트]_[설명].[ext]`

## Skills 사용

이 워크스페이스의 `.claude/skills/`에 프로젝트 전용 스킬이 있습니다.
스킬은 키워드 기반으로 **자동 트리거**됩니다. (수동 슬래시 커맨드 아님)

예: "오늘 daily note 만들어줘" → `daily-note` 스킬 자동 실행
예: "할 일 추가해줘" → `todo` 스킬 자동 실행

## Agents 사용

`.claude/agents/`에 서브에이전트가 있습니다. 복잡한 작업을 Claude가 자동으로 위임하거나, 명시적으로 "research-worker로 조사해줘" 같이 호출할 수 있습니다.

## 외부 도구 연동

### Google Workspace (gws CLI) ✅ 연동됨

`gws` CLI로 Google Workspace가 연동되어 있습니다. 인증 토큰은 시스템 keyring에 저장됨.

- **사용법**: `gws <service> <resource> <method> --params '<JSON>'`
- **지원 서비스**: gmail, calendar, drive, sheets, docs, slides, tasks, people, chat, forms, keep, meet 등
- **예시**:
  - 메일 목록: `gws gmail users messages list --params '{"userId":"me","maxResults":5}'`
  - 메일 내용: `gws gmail users messages get --params '{"userId":"me","id":"<ID>","format":"metadata","metadataHeaders":["From","Subject","Date"]}'`
  - 오늘 일정: `gws calendar events list --params '{"calendarId":"primary",...}'`
- `--format table|json|yaml|csv`, `--page-all`(자동 페이지네이션) 플래그 지원
- `gws schema <service.resource.method>`로 파라미터 스키마 확인 가능
- `daily-note` 스킬이 gws 인증 시 Google Calendar 오늘 일정을 자동 포함

---

## 내 프로필

**이름**: 용팀장 (**반말로 대화**. 2026-08-09 본인 지시)
**역할**: 구매대행 셀러 겸 강사 (네이버 스마트스토어 + 유튜브 + 오프라인 강의)
**관심사**: 구매대행 실전반 강의 준비·셀러 자동화 파이프라인 구축(불사자 연동, 상세페이지·상품가공)
**이 워크스페이스 용도**: 강의 커리큘럼 기획·PPT 제작 · 불사자 자동화 파이프라인 유지보수

**협업 규칙 (필수)**:
- **반말로 말한다.** 존댓말·"용팀장님" 호칭 쓰지 않는다.
- 결론 먼저, 이유 나중. 짧고 명확하게. 구조와 논리로 설명.
- 코드 요청: Python 기반, 한국어 주석, try-except 포함.

---

**Last Updated**: 2026-07-04

<!-- GSD:project-start source:PROJECT.md -->
## Project

**셀러 관제탑 (Seller Control Tower)**

네이버 검색광고 성과 판정과 불사자 상품 가공을 한 화면에서 잇는 **로컬 웹 관제탑**이다.
광고 6규칙 판정 결과를 상품 단위 보드로 띄우고, 거기서 상세페이지 작업·입찰가 인상·꺼진 소재 정리·썸네일 교체·쿠팡 복사를 각각 버튼으로 실행한다.
사용자는 용팀장 본인 한 명, 맥북 로컬에서만 돈다.

**Core Value:** **유입이나 판매가 있는데 상세페이지가 중국어 원본·단순번역인 상품을, 중복 작업 없이 한 화면에서 골라 고치고 반영하는 것.**

이게 안 되면 나머지 버튼이 다 돌아도 이 프로젝트는 실패다.

### Constraints

- **배포**: 맥북 로컬 단독 실행 — 사용자 1명, 호스팅·인증 없음
- **아키텍처**: 웹앱은 기존 CLI 스크립트의 래퍼다. 검증된 로직·테스트·가드레일을 재작성하지 않는다
- **안전**: 모든 쓰기 작업은 dry-run 선행. 크레딧 소모 작업은 접수 전 견적 보고
- **진실의 원천**: 작업 완료 여부는 불사자 서버 플래그가 정본. 로컬 대장을 정본으로 삼지 않는다
- **확장성**: 광고 계정은 `~/.eroom/naver-ads.json` 에 항목 추가로만 늘어난다 (현재 4개 → 6개 예정)
- **언어**: 코드 주석 한국어, Python 기반, try-except 포함
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## 결론 먼저
| 질문 | 답 |
|---|---|
| CLI 를 import 할까 subprocess 할까 | **subprocess.** 실제 코드를 읽고 내린 결론이다 — import 는 지금 구조에서 작동조차 안 한다 (아래 §핵심결정 1) |
| 태스크 큐(Celery/RQ/Huey)가 필요한가 | **아니다.** 내구성은 이미 CLI 의 run-dir 체크포인트가 갖고 있다. 브로커는 진실을 둘로 만든다 |
| 진행 스트리밍은 SSE / WS / 폴링 | **SSE.** 단, 파이프를 직접 흘리지 말고 **로그파일을 오프셋부터 tail** 해야 "브라우저 닫았다 재접속" 요구가 성립한다 (§핵심결정 3) |
| 프론트엔드 | **서버 렌더(Jinja2) + htmx + Tabulator CDN.** 빌드체인 0 |
| DB | **stdlib `sqlite3`.** ORM·마이그레이션 도구 없음. 보드 테이블은 재생성 가능한 캐시다 |
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
## 핵심 결정 1 — import 가 아니라 subprocess (확신도: **HIGH**)
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
## 핵심 결정 2 — 태스크 큐는 쓰지 않는다 (확신도: **HIGH**)
### 왜 정당화되지 않는가
| 큐가 주는 것 | 이 프로젝트의 현실 |
|---|---|
| 잡 내구성 (죽어도 재개) | **CLI 가 이미 갖고 있다.** `detail_batch --poll-only`, `copied.jsonl`, `run-dir` 체크포인트. 브로커를 넣으면 **재개 상태의 정본이 둘**이 된다 — 큐의 잡 레코드 vs run-dir 체크포인트. 둘이 어긋나면 크레딧 이중 지불이다 |
| 재시도 | `--retry-failed`, 중복 대기열 재시도가 CLI 안에 있다. 큐 레벨 재시도는 **전체 잡을 처음부터 다시 돌려** 오히려 위험하다 |
| 워커 확장 | 사용자 1명. 동시 잡 2~3개 |
| 지연 실행 | v1 out of scope. 3단계에서 APScheduler 로 충분 |
### 대신 이렇게 (총 코드 ~150줄)
### 큐를 다시 검토할 조건 (선을 미리 그어둔다)
- 대기 중인 잡이 상시 5개 이상 쌓인다
- 잡 우선순위가 필요해진다
- 잡 실패 후 자동 백오프 재시도를 큐 레벨에서 걸어야 한다
## 핵심 결정 3 — SSE. 단, 파이프가 아니라 로그파일을 tail (확신도: **HIGH**)
### SSE vs WebSocket vs 폴링
| 방식 | 판정 | 이유 |
|---|---|---|
| **SSE** | ✅ **채택** | 데이터가 서버→클라 **단방향**이다 (진행 로그). 브라우저 `EventSource` 가 **자동 재연결 + `Last-Event-ID` 헤더 재전송**을 공짜로 준다 — "재접속하면 이어서 보기" 요구가 브라우저 내장 기능으로 풀린다. 평문 HTTP 라 `curl -N` 으로 디버깅된다. htmx-ext-sse 로 JS 0줄 |
| WebSocket | ❌ 제외 | 양방향성을 안 쓴다. 재연결·하트비트·재개 오프셋을 전부 직접 짜야 한다 (EventSource 가 이미 하는 일). 프록시/슬립 복귀 시 끊김 처리도 수작업 |
| 폴링 | 🟡 허용 가능한 후퇴 | `GET /jobs/{id}/log?from=N` 2초 폴링은 20줄이고 1인 로컬에선 솔직히 문제없다. SSE 가 막히면 여기로 내려와라. 다만 "실시간"이 2초 계단이 된다 |
### 이게 핵심이다 — 파이프 직결 금지
### HTTP/1.1 동시 연결 한계 — 스트림을 잡마다 열지 마라
## Installation
# 웹앱 전용 venv — 기존 .venv 는 손대지 않는다.
# subprocess 로 부르므로 의존성을 섞을 이유가 전혀 없다. CLI 는 계속 .venv/bin/python3 로 돈다.
# pydantic 2.13.5 · starlette 1.6.0 은 fastapi 가 끌고 온다. 직접 pin 하지 마라.
# sqlite3 는 stdlib.
# 3단계(스케줄)에 진입할 때만:
# uv pip install --python .venv-web/bin/python "apscheduler==3.11.3"
### 실행
# --workers 1 이 협상 불가다 (§What NOT to Use 참조)
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
## Stack Patterns by Variant
- 전 행을 JSON 한 번에 내려 Tabulator 클라이언트 사이드 정렬·필터
- 필터 조작이 즉각 반응하고 서버 왕복이 없다. 구현이 절반
- SQLite 에 적재 → Tabulator `ajax` + `filterMode:"remote"` / `sortMode:"remote"` 로 서버 사이드 전환
- 전체 수집상품이 970,695건이니 **"작업 대상"을 어떻게 좁히느냐가 이 분기점을 결정한다.** 1단계 집계 결과를 보고 확정해라
- `caffeinate` 불필요, 고아 잡 복구 로직도 사실상 안 탐
- `caffeinate -i` 로 감싼다 — 맥북 idle sleep 이 폴링을 끊는다
- 서버 부팅 시 고아 잡 스캔 필수 (pid 생존 확인)
- 재개는 새 잡으로 만들지 말고 CLI 의 `--poll-only` 를 태워라. 새 접수를 태우면 크레딧 이중 지불이다
- 새 경로를 만들지 마라. APScheduler 가 **v1 과 같은 잡 생성 함수**를 부른다
- v1 설계에서 지켜야 할 것: 잡 생성이 HTTP 핸들러가 아니라 **호출 가능한 함수**에 있고, 핸들러는 그걸 얇게 감싸기만 할 것
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
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

| Skill | Description | Path |
|-------|-------------|------|
| aside-category | 상품명/키워드를 받아 네이버 가격비교에서 그 키워드의 카테고리 경로(예 '디지털/가전 > 주변기기 > 마우스 > 무선마우스')·확신도·카테고리코드를 조회하는 단일 목적 CLI 도구(JSON in/out — 다른 스킬이 subprocess 로 재사용). "카테고리 조회", "이 키워드 네이버 카테고리 뭐야", "카테고리 경로 확인", "aside 카테고리", "가격비교에서 카테고리 뽑아줘" 처럼 **키워드의 카테고리 경로만 알고 싶을 때** 자동 실행. ※ 불사자 상품 카테고리를 실제로 교정·저장하는 전체 흐름은 bulsaja-category-fix 스킬이 담당한다. | `.claude/skills/aside-category/SKILL.md` |
| biz-advisor-oldman | '마케팅깎는 노인' 페르소나로 사용자의 사업을 진단한다. 손님이 지갑을 여는 본능·의심 순위·간접 격파(직접 자랑 대신 증거로 의심을 푸는 법)·실행지침 10개·이번주 콘텐츠 3개·채널(그릇) 배정까지 고정 10단계 출력을 제시하고, 유의미한 아이디어를 골라 4천자 이상 심화조언으로 이어지도록 유도한다. "사업 조언", "사업 진단", "매출 두배", "마케팅깎는 노인", "내 사업 봐줘", "손님이 안 믿어줘", "간접 격파", "V스코어", "V-Score" 등을 언급하면 자동 실행. | `.claude/skills/biz-advisor-oldman/SKILL.md` |
| bulsaja-category-fix | 불사자 상품의 카테고리를 네이버 정답 카테고리로 교정하고 결과를 구글시트에 기록한다. "불사자 카테고리 교정", "카테고리 수정해줘", "카테고리 바꿔줘", "상품 카테고리 정리", "카테고리 잘못된거 고쳐줘" 등을 언급하면 자동 실행. ※ 키워드의 카테고리 경로만 조회하는 건 aside-category 스킬(이 스킬이 내부에서 호출). | `.claude/skills/bulsaja-category-fix/SKILL.md` |
| bulsaja-detail-page | 불사자 AI 상세페이지 생성을 배치로 실행한다. 기본 10장(UI의 "AI 상세페이지 생성" 버튼과 동일), 일반화질, 접수→폴링→자동반영, 체크포인트 재개. "상세페이지 만들어줘", "AI 상세페이지", "상세페이지 생성", "상세페이지 작업해줘", "상세 뽑아줘" 등을 언급하면 자동 실행. 접수 전 예상 크레딧 보고 필수. | `.claude/skills/bulsaja-detail-page/SKILL.md` |
| bulsaja-detail-remix | 타오바오 원본 상세이미지 zip + GPTs로 스마트스토어용으로 가공된 상세페이지 이미지 zip + 불사자 판매자상품코드, 이렇게 3개를 받아 먼저 GPTs 결과물이 타오바오 원본에 없는 내용을 지어내지 않았는지 비전으로 검수하고, 통과하면 zip 안 이미지를 가로 860px 기준 세로로 이어붙여 불사자 계정의 기존 상세페이지를 교체한다. Fatkun 다운로드·GPTs 작업 자체는 계속 수동. "상세페이지 리믹스", "GPTs 상세 반영해줘", "상세 zip 적용해줘", "상세페이지 검수하고 반영해줘", "타오바오 상세 스티칭" 등을 언급하며 타오바오 zip + 스마트 스토어 zip + 상품코드를 주면 자동 실행. | `.claude/skills/bulsaja-detail-remix/SKILL.md` |
| bulsaja-mulgari-delete | "[마켓그룹] 물갈이 삭제작업 할거야" 트리거 시, 용팀장님이 불사자에서 직접 삭제하도록 **필터 조건만 안내**하고 일정(todo)을 관리한다. Claude가 삭제를 실행하지 않는다. 물갈이(전시 최신성 회복을 위한 삭제→재업로드) 1단계(삭제). "물갈이 삭제", "1-1 물갈이 삭제작업 하자", "15-2 물갈이 삭제" 등 마켓그룹+물갈이+삭제를 언급하면 자동 실행. | `.claude/skills/bulsaja-mulgari-delete/SKILL.md` |
| bulsaja-mulgari-upload | "[마켓그룹] 물갈이 업로드/재업로드 할거야" 트리거 시, 용팀장님이 불사자에서 직접 업로드하도록 **필터 조건만 안내**하고 일정(todo)을 관리한다. Claude가 업로드를 실행하지 않는다. 물갈이(삭제→재업로드로 전시 최신성 회복) 2단계(재업로드). "물갈이 업로드", "1-1 물갈이 업로드 진행해", "15-2 재업로드" 등 마켓그룹+물갈이+업로드/재업로드를 언급하면 자동 실행. 완료 후 +20일 물갈이 삭제 todo로 사이클을 잇는다. | `.claude/skills/bulsaja-mulgari-upload/SKILL.md` |
| bulsaja-option-cleanup | 불사자 상품의 옵션을 정리한다. 비상품 행(구매금지 안내·사이즈표·보증금·배송비·부속품 단독·타모델·맞춤제작)을 판매에서 빼고, 옵션명을 중국어 원문 기준으로 25자 이내 한국어로 고쳐 서로 겹치지 않게 만들고, 옵션 축(선택 항목) 이름이 값과 어긋나면(축은 '색상'인데 값은 모델·소재·규격) 그것도 고치고, 메인상품 최저가를 대표옵션으로 세워 그 1.5배까지만 판매하도록 범위를 좁히고, 판매가 오름차순을 업로드 순서로 확정한다. "옵션 정리", "옵션명 정리해줘", "대표옵션 지정", "옵션 정리해줘", "판매범위 좁혀줘", "옵션 순서", "축 이름 바꿔줘", "선택 항목 이름", "option cleanup" 등을 언급하거나 마켓그룹을 주고 옵션 작업을 요청하면 자동 실행. 미리보기 결과를 보고한 뒤 승인을 묻지 않고 바로 저장한다(2026-08-05 이룸님 상시 위임 · before_commit.json 으로 되돌리기 가능). | `.claude/skills/bulsaja-option-cleanup/SKILL.md` |
| bulsaja-option-image | 불사자 상품의 판매 중 옵션 이미지(중국어 원본)를 한국어 스펙이 들어간 깨끗한 제품 이미지로 다시 만들어 교체한다. 옵션 이미지가 쿠팡 썸네일로 쓰이는 상품에 특히 필요. "옵션 이미지 작업해줘", "옵션 이미지 바꿔줘", "옵션 이미지 교체", "옵션 이미지 한국어로", "옵션 썸네일 만들어줘", "옵션별 이미지 생성" 등을 언급하거나 상품코드를 주고 옵션 이미지 작업을 요청하면 자동 실행. ※ 대표 썸네일은 bulsaja-thumbnail, 옵션명·판매범위 정리는 bulsaja-option-cleanup. | `.claude/skills/bulsaja-option-image/SKILL.md` |
| bulsaja-product-lock | 불사자 상품코드를 받아 판매된 상품을 삭제 방지 잠금 처리. 불사자 UI의 "잠금" 토글 = MCP상의 "숨김" 처리로, 잠금하면 실수로 삭제 버튼을 눌러도 삭제되지 않음. "상품 잠금", "잠금 걸어줘", "잠금처리", "판매된 상품 잠가줘", "삭제 방지", "상품코드 잠금" 등을 언급하거나 상품코드를 주며 잠금을 요청하면 자동 실행. | `.claude/skills/bulsaja-product-lock/SKILL.md` |
| bulsaja-shipping-cost | 불사자 수집상품 또는 확인된 무게로 해외배송비를 측정·추천·반영한다. 판매자상품코드를 주며 배송비를 계산해 달라는 요청, 무게·부피를 직접 알려주며 배송비를 계산해 달라는 요청, 해운 특가 요율 적용, 추천 배송비를 실제 상품에 반영해 달라는 요청에 사용한다. "배송비 계산해줘", "배송비 측정", "배송비 추천", "해외배송비", "이 상품 배송비 얼마", "배송비 반영해줘" 등을 언급하거나 상품코드/무게를 주며 배송비 작업을 요청하면 자동 실행. 100kg 초과 상품도 배송비는 계산·입력하되 중량 상품 경고를 별도로 보고한다. 반영(가격 변경)은 미리보기 후 별도 최종 동의 필수 — 승인 없이 실제 상품 가격을 바꾸지 않는다. | `.claude/skills/bulsaja-shipping-cost/SKILL.md` |
| bulsaja-thumbnail | 불사자 상품의 대표 썸네일을 불사자 내부 AI로 생성·교체한다. 기본은 배경만 바꾸는 대량 모드, "예쁘게/연출/레시피" 지명 시엔 기준 이미지·배경 전략·레시피를 직접 짜는 정밀 모드로 돈다. "썸네일 만들어줘", "썸네일 바꿔줘", "배경 생성", "AI 썸네일", "썸네일 예쁘게", "대표이미지 교체" 등을 언급하거나 마켓그룹/상품을 주고 썸네일 작업을 요청하면 자동 실행. | `.claude/skills/bulsaja-thumbnail/SKILL.md` |
| captcha-relay | 브라우저 작업 중 캡챠(보안 확인)를 만났을 때, 답변 '판단'만 Aside 에게 파일로 위임하고 입력·제출은 Claude 가 직접 하는 릴레이 프로토콜. "캡챠 떴어", "보안 확인 나왔어", "캡챠감지", "캡챠 풀어줘", "captcha" 를 언급하거나 카테고리 조회(aside-category·bulsaja-category-fix)가 `캡챠감지` 로 멈췄을 때 자동 실행. | `.claude/skills/captcha-relay/SKILL.md` |
| coupang-candidates | 스마트스토어 판매 실적이 검증된 상품만 골라 불사자 쿠팡 마켓그룹으로 복사·업로드한다. 주문시트에서 실적·실마진·실배송비를 집계하고, 불사자코드로 사본 중복을 병합해 원본당 1건만 올린다. "쿠팡 후보", "쿠팡에 올릴 상품", "쿠팡 업로드 준비", "쿠팡 복사", "쿠팡 파이프라인", "실적 좋은 상품 쿠팡에" 등을 언급하면 자동 실행. 복사·업로드는 --commit 과 배송비 교정 완료가 전제다. | `.claude/skills/coupang-candidates/SKILL.md` |
| cs-response | 고객 CS 상황(메시지 원문·상황 설명)을 받아 구매대행 특화 답변 문구를 정중한 존댓말로 작성하고 구글시트에 로그를 남긴다. "CS 대응", "CS 조언", "고객 답변 문구", "이 고객한테 뭐라고 답장하지", "고객 문의 답변", "CS 답변 만들어줘" 등을 언급하면 자동 실행. | `.claude/skills/cs-response/SKILL.md` |
| csv-clean | CSV 데이터 품질 정리. 소계행 제거, 숫자 정리, 날짜 정규화, unpivot 등. "데이터 정리", "CSV 정리", "소계 제거", "숫자 정리", "날짜 통일", "unpivot", "csv clean", "데이터 클리닝" 등을 언급하면 자동 실행. | `.claude/skills/csv-clean/SKILL.md` |
| daily-note | 오늘 날짜의 Daily Note 생성 또는 열기. gws (Google Workspace CLI) 인증 시 Google Calendar 오늘 일정 포함. "오늘 daily note", "일일 노트", "daily note", "오늘 작성", "하루 기록" 등을 언급하면 자동 실행. | `.claude/skills/daily-note/SKILL.md` |
| daily-review | 어제/오늘 git 변경사항을 분석하고, daily note + todos 기반으로 오늘 우선순위를 제안. "일일 리뷰", "오늘 뭐 했지", "어제 작업 정리", "daily review" 등을 언급하면 자동 실행. | `.claude/skills/daily-review/SKILL.md` |
| dashboard-prd | 대시보드 PRD 대화형 생성. "대시보드 PRD", "대시보드 기획", "대시보드 설계", "dashboard PRD" 등을 언급하면 자동 실행. | `.claude/skills/dashboard-prd/SKILL.md` |
| decompose | 미션을 병렬 실행 가능한 작업으로 분해. "작업 분해", "태스크 나누기", "병렬로 처리", "분해해줘" 등을 언급하면 자동 실행. | `.claude/skills/decompose/SKILL.md` |
| doc-updater | Claude Code 공식 문서 업데이트 확인 및 자동 반영. GitHub CHANGELOG를 읽고 30-knowledge/37-claude-code/37.00-official-docs/ 하위 가이드 문서들을 최신 버전으로 동기화. "문서 업데이트", "CHANGELOG 확인", "doc update", "공식문서 업데이트", "Claude Code 변경사항" 등을 언급하면 자동 실행. | `.claude/skills/doc-updater/SKILL.md` |
| email-triage | 수집함 cy728728@gmail.com 에 모인 메일을 정리·검증·규칙수정한다. "이메일 정리해줘", "메일 정리", "메일 뭐 왔어", "확인필요 메일", "전달 잘 되고 있어", "전달 확인", "스팸에 뭐 갇혔어", "네이버 메일 가져와", "삭제 규칙 추가", "이 발신자 지워줘", "이건 남겨줘" 등 **수집함 메일 관리**를 언급하면 자동 실행. ※ 메일을 보내는 것은 send-email 스킬. | `.claude/skills/email-triage/SKILL.md` |
| excel-to-csv | Excel 파일을 CSV로 변환하여 Claude Code에서 분석 가능하게 만듦. "엑셀 변환", "Excel CSV", "xlsx 변환", "엑셀을 CSV로", "데이터 변환", "excel to csv" 등을 언급하거나 .xlsx/.xls 파일 경로를 제공하면 자동 실행. | `.claude/skills/excel-to-csv/SKILL.md` |
| execute | 매니페스트의 병렬 작업을 워커 에이전트로 실행. "작업 실행", "워커 실행", "병렬 처리 시작", "execute tasks" 등을 언급하면 자동 실행. /decompose 후 사용. | `.claude/skills/execute/SKILL.md` |
| git-sync | "워크스페이스를 GitHub와 동기화한다. 용팀장님이 \"깃푸쉬\", \"깃 푸쉬\", \"깃푸시\", \"git push\", \"올려줘\", \"깃풀\", \"깃 풀\", \"git pull\", \"받아줘\", \"싱크\", \"동기화\", \"깃 정리\", \"커밋\", \"커밋해줘\", \"git commit\" 등을 말하면 즉시 자동 실행. 확인 질문·파일 검토·요약 없이 sync.ps1 한 줄만 돌린다. 다른 PC를 오갈 때 쓰는 최우선 속도 작업." | `.claude/skills/git-sync/SKILL.md` |
| hwpx | "한글(HWPX) 문서 생성/읽기/편집 스킬. .hwpx 파일, 한글 문서, Hancom, OWPML 관련 요청 시 사용." | `.claude/skills/hwpxskill/SKILL.md` |
| idea | 대화에서 아이디어/인사이트를 추출하여 워크스페이스에 저장. "아이디어 저장", "이거 기록", "인사이트 정리", "메모해줘" 등을 언급하면 자동 실행. | `.claude/skills/idea/SKILL.md` |
| inbox-triage | 00-inbox/raw/ (폰·텔레그램·카톡 등으로 수집된 미처리 source)를 읽어 종류를 판정하고 워크스페이스 업무 목적지(todo·info 보관·일정)로 라우팅하는 얇은 디스패처. 분류를 새로 발명하지 않고 전담 스킬(todo·wiki-ingest·transcript-organizer)로 위임한다. proposal-first(항목별 제안 → 사용자 승인 → 라우팅 → processed 마킹). "인박스 분류", "raw 분류", "수집된 거 정리", "인박스 트리아지", "inbox-triage" 등 **raw/ 수집분을 업무로 분류**하는 의도가 명시될 때 자동 실행. ※ 00-inbox 루트의 완성 파일 정리와는 다름 — 이 스킬은 raw/ 미처리 수집분 전용. | `.claude/skills/inbox-triage/SKILL.md` |
| integrate | 병렬 작업 결과를 통합하여 최종 산출물 생성. "결과 통합", "병렬 작업 합치기", "통합해줘", "integrate results" 등을 언급하면 자동 실행. /execute 후 사용. | `.claude/skills/integrate/SKILL.md` |
| kakao-read | 본인 카카오톡 대화·사진·파일을 로컬에서 직접 읽어 요약·할일 추출·검색·내용 파악. "카톡 읽어줘", "카톡 대화 정리", "카톡 요약", "카톡에서 X 찾아줘", "카톡 사진 내용 확인", "그 방 사진 뭐야", "카톡 파일 받아줘", "어제 그 방 대화 정리해줘", "카톡 체크"(지난 체크 이후 새 활동 1:1 방 메뉴형 수집), "최근 카톡 보여줘" 등 본인 카톡 내용을 가져올 때 자동 실행. Mac은 로컬 암호화 DB 직독(서버 접속 0). 윈도우는 실행 중 프로세스 메모리 직독(키 불필요). 메시지 보내기/온라인 LOCO는 범위 밖. | `.claude/skills/kakao-read/SKILL.md` |
| keyword-pick | 아이템스카우트 키워드 익스포트(.xlsx)에서 이룸님 기준(상품수 낮은 키워드)에 맞는 추천 키워드를 골라 구글 시트에 누적. "키워드 추천", "키워드 뽑아줘", "키워드 골라줘", "아이템스카우트", "상품수 낮은 키워드", "추천키워드", "keyword pick" 등을 언급하거나 아이템스카우트 익스포트 .xlsx를 제공하면 자동 실행. | `.claude/skills/keyword-pick/SKILL.md` |
| kfia-hygiene-education | 한국식품산업협회(kfia21.or.kr) 기존영업자 온라인 위생교육을 매년 신청한다. 용팀장님 + 사모님 각각 별도 계정으로 매년 재가입 후 진행. "식품산업협회 온라인교육", "위생교육 신청", "기존영업자 온라인교육", "kfia", "수입식품안전관리 위생교육" 등을 언급하면 자동 실행. | `.claude/skills/kfia-hygiene-education/SKILL.md` |
| md-to-pdf | 마크다운 문서를 A4 PDF-ready HTML 핸드아웃으로 변환. Monochrome Dark 테마(미니멀 블랙/화이트, 브랜드 중립). 페이지 overflow 자동 방지. "핸드아웃", "handout", "PDF 만들어", "배포용", "md-to-pdf", "인쇄용", "A4 변환" 등을 언급하면 자동 실행. | `.claude/skills/md-to-pdf/SKILL.md` |
| naver-ads-weekly | 네이버 검색광고 여러 계정을 주 1회 훑어 노출0·저CTR·구매0·효자상품을 분류하고 총괄 보고서를 만든다. 입찰가 인상과 꺼진 소재 삭제는 승인 후 별도 명령으로 실행한다. "광고 주간보고", "광고 성과 정리", "노출 안 되는 상품", "입찰가 올려줘", "꺼진 광고 정리", "광고 리포트", "썸네일 바꿀 상품 뽑아줘" 등을 언급하면 자동 실행. | `.claude/skills/naver-ads-weekly/SKILL.md` |
| naver-category-master | 네이버 쇼핑 전체 카테고리(코드↔경로) 마스터 파일을 커머스API로 수집·갱신하고, 경로→코드·코드→경로·최종차수명→후보 를 역조회하는 도구. "카테고리 코드 뭐야", "이 경로 카테고리 번호", "카테고리 마스터 갱신", "카테고리 코드 검증" 처럼 **번호와 경로를 서로 변환하거나 전체 목록을 다시 받을 때** 실행. ※ 키워드로 카테고리 경로를 새로 조회하는 건 aside-category 가 담당한다. | `.claude/skills/naver-category-master/SKILL.md` |
| notion-handler | Notion 데이터베이스/페이지 관리. "노션", "Notion", "DB 만들어", "데이터베이스", "페이지 추가", "설문 DB", "프로젝트 관리", "노션에 저장", "대시보드" 등을 언급하면 자동 실행. | `.claude/skills/notion-handler/SKILL.md` |
| openchina-order-excel | 오픈차이나(openchina.co.kr) 배송대행지에 자동 로그인해 주문내역을 엑셀(.xls)로 다운로드. "오픈차이나 주문내역", "오픈차이나 엑셀", "주문 엑셀 다운", "배송대행 주문 받아줘", "오픈차이나 다운로드" 등을 언급하면 자동 실행. 기간(예: 최근 1개월, 6월 한달)을 지정할 수 있음. | `.claude/skills/openchina-order-excel/SKILL.md` |
| payroll-tax-filing | 직원 급여 지급 엑셀을 받아 3.3% 원천세(소득세 3% + 지방소득세 0.3%) 신고를 반자동으로 진행. 화면별 입력값 산출 + 검산 + 근거자료 생성 + 가이드 진행(홈택스·위택스). "지난달 소득 신고", "원천세 신고", "3.3 신고", "급여 원천세", "간이지급명세서", "직원 세금 신고" 등을 언급하거나 급여 지급 엑셀(.xlsx)을 주며 신고를 요청하면 자동 실행. | `.claude/skills/payroll-tax-filing/SKILL.md` |
| pdf-to-md | PDF 파일을 구조화된 Markdown으로 변환 (pymupdf4llm 기반). 표·헤딩·이미지 레이아웃을 보존하며 대용량 PDF도 한 번에 처리. "PDF 변환", "PDF를 마크다운으로", "PDF 텍스트 추출", "문서 변환" 등을 언급하면 자동 실행. | `.claude/skills/pdf-to-md/SKILL.md` |
| product-name | 불사자 마켓그룹의 상품들을 썸네일로 확인하고, 셀러라이프 카테고리 키워드 중 상위노출에 유리한 2~5개를 골라 네이버 상품명을 만들어 실제로 바꾼다. "상품명 만들어줘", "상품명 바꿔줘", "상품명 생성", "마켓 상품명 정리", "키워드로 상품명", "상품명 일괄 변경", "product-name" 등을 언급하거나 마켓그룹을 주고 상품명 작업을 요청하면 자동 실행. 시트 기록 후 승인을 묻지 않고 바로 불사자에 반영한다(2026-08-05 이룸님 상시 위임 · 원본은 시트 E열 백업). | `.claude/skills/product-name/SKILL.md` |
| review-analyzer | 네이버 브랜드스토어 리뷰를 로그인 없이 크롤링하고 4단계 프레임워크로 분석해 실행 아이디어를 도출. "네이버 리뷰", "브랜드스토어 리뷰", "리뷰 크롤링", "리뷰 분석", "경쟁사 리뷰", "상품 리뷰 수집", "리뷰 인사이트" 등을 언급하면 자동 실행. | `.claude/skills/review-analyzer/SKILL.md` |
| ripple | 파일 수정 후 연관 파일 찾아서 함께 업데이트. "연관 업데이트", "ripple", "참조 파일도", "빠진거 없나", "관련 파일 정리" 등을 언급하면 자동 실행. | `.claude/skills/ripple/SKILL.md` |
| sellerlife-keyword | 셀러라이프(sellochomes.co.kr)에 자동 로그인해 '카테고리 소싱' 전체 엑셀을 받아, 필터링 + Gemini 브랜드/상표 판정까지 한 번에 처리하고 바로 쓸 수 있는 안전 키워드 엑셀을 만든다. "셀러라이프 키워드", "카테고리 소싱 받아줘", "키워드 파일 가공", "rawdata 가공", "브랜드 키워드 걸러줘", "키워드 블랙리스트", "셀러라이프 다운" 등을 언급하면 자동 실행. 반영 전 검토_*.xlsx 승인 필요. | `.claude/skills/sellerlife-keyword/SKILL.md` |
| send-email | 대화 내용이나 지정한 텍스트를 이메일로 발송. 기본 수신자는 cy728@daum.net. "이 내용 메일로 보내줘", "이메일 보내줘", "메일로 보내", "메일 발송", "이거 이메일로", "다음으로 보내줘" 등을 언급하면 자동 실행. 수신자·제목·첨부파일을 지정하면 그에 맞춰 발송. | `.claude/skills/send-email/SKILL.md` |
| setup-workspace | 첫 clone 후 워크스페이스 초기 설정. CLAUDE.md 프로필 작성 + Python venv 세팅 + 선택 도구(gws/git) 안내 + 첫 daily note 생성까지 한번에 진행. "워크스페이스 세팅", "초기 설정", "setup", "setup-workspace" 등을 언급하면 자동 실행. | `.claude/skills/setup-workspace/SKILL.md` |
| smartstore-brand | 스마트스토어(네이버) 브랜드 에셋 생성 — 로고 / 모바일 배너 / PC 배너. OpenAI gpt-image-2 모델 사용. "로고 만들어줘", "모바일 배너 만들어줘", "PC 배너 만들어줘", "피씨 배너", "스마트스토어 로고", "마켓 배너" 등을 언급하면서 마켓명을 주면 자동 실행. | `.claude/skills/smartstore-brand/SKILL.md` |
| thinking-partner | 복잡한 문제를 탐색하고 질문을 통해 사고를 촉진하는 협력적 사고 파트너. "같이 생각해보자", "고민이 있어", "브레인스토밍", "생각 정리 도와줘" 등을 언급하면 자동 실행. | `.claude/skills/thinking-partner/SKILL.md` |
| todo | 빠르게 Todo를 추가 (우선순위 감지, 프로젝트 태그 지원). "할 일 추가", "todo 추가", "이거 해야해", "기억해둬" 등을 언급하면 자동 실행. | `.claude/skills/todo/SKILL.md` |
| todos | 저장된 Todo 조회 및 관리. 전체/오늘/프로젝트별/오래된 것/통계 뷰 지원. "할 일 보기", "todos", "오늘 할 일", "오버듀", "할 일 통계" 등을 언급하면 자동 실행. | `.claude/skills/todos/SKILL.md` |
| transcript-organizer | \| 긴 녹음 텍스트 파일(강의, 미팅, 인터뷰)을 상세하게 분석 및 구조화. "녹음 정리", "강의 정리", "미팅록", "인터뷰 정리", "txt 파일 분석", "트랜스크립트" 등 언급 시 자동 실행. 인코딩 자동 감지(UTF-16→UTF-8), STT 오인식 교정, 내용 분석, 저장까지 완전 자동화. **분량 기준**: 1시간 미만 300줄+, 1-2시간 500줄+, 3시간+ 700줄+. 직접 인용 10회 이상. | `.claude/skills/transcript-organizer/SKILL.md` |
| web-crawler-ocr | 웹페이지 크롤링 + 이미지 OCR 자동 분석. "이 URL 분석해줘", "크롤링해줘", "웹사이트 분석", "사이트 크롤링", "경쟁사 분석", "페이지 추출", "analyze this URL", "crawl website", "competitor analysis", "extract webpage" 등을 언급하거나 https:// 또는 http:// URL을 제공하면 자동 실행. Claude의 5MB 이미지 제한을 Gemini OCR(20MB)로 우회. | `.claude/skills/web-crawler-ocr/SKILL.md` |
| webapp-prd | 본인의 니즈에 맞는 웹앱 PRD 대화형 생성. "웹앱 PRD", "웹앱 기획", "앱 설계", "webapp PRD", "웹앱 만들고 싶어" 등을 언급하면 자동 실행. | `.claude/skills/webapp-prd/SKILL.md` |
| weekly-synthesis | 한 주간의 작업과 사고를 종합하여 Weekly Synthesis 생성. "주간 정리", "이번 주 회고", "weekly review", "일주일 요약", "주간 리뷰" 등을 언급하면 자동 실행. | `.claude/skills/weekly-synthesis/SKILL.md` |
| wiki-ingest | \| 소스를 분석하여 30-knowledge/00-wiki 토픽 페이지를 자동 enrichment. 지식을 복리로 축적. 단순 추가가 아니라: 기존 페이지 통합, 핵심 요약 갱신, 교차 참조 강화, 모순 감지. "wiki-ingest", "위키 업데이트", "위키에 반영", "wiki update", "지식 축적" 등을 언급하면 자동 실행. | `.claude/skills/wiki-ingest/SKILL.md` |
| wiki-lint | \| 00-wiki 토픽 페이지 헬스체크. 모순, 고아 페이지, 오래된 정보, 누락된 교차 참조 점검. "wiki-lint", "위키 점검", "위키 헬스체크", "wiki health", "토픽 점검" 등을 언급하면 자동 실행. | `.claude/skills/wiki-lint/SKILL.md` |
| youtube-main-script | 시온 PD의 노션 회차 페이지(기획·도입부)를 크롬 브라우저로 읽고, 용팀장 말투로 유튜브 메인 스크립트 초안을 작성해 같은 페이지의 "메인 스크립트(용팀장님)" 토글에 자동 삽입. "메인 스크립트", "메인스크립트 초안", "메인 스크립트 짜줘", 노션 회차 링크 + "초안"/"스크립트" 요청 시 자동 실행. 도입부·기획·업로드 본문 작성은 범위 밖(각각 시온·하늘 담당). | `.claude/skills/youtube-main-script/SKILL.md` |
| youtube-summary | YouTube 링크를 받아 썸네일 + 1000자 요약을 만들고, 선택적으로 Notion 페이지로 저장. "유튜브 요약", "이 영상 요약", "youtube 요약", "영상 정리", "유튜브 노션에 저장" 등을 언급하거나 youtube.com / youtu.be URL을 주면 자동 실행. | `.claude/skills/youtube-summary/SKILL.md` |
| zoom-meeting | 자연어 요청("줌미팅 잡아줘", "줌 링크 만들어줘")을 받아 Zoom Server-to-Server OAuth API로 실제 미팅을 생성하고 join 링크를 반환. 날짜/시작시간/소요시간이 빠지면 먼저 질문하고, 제목은 명시돼도 없어도 항상 확인 질문. 생성 직후 (시작시간-30분)에 "줌 오픈" 리마인더를 todo에 자동 등록. | `.claude/skills/zoom-meeting/SKILL.md` |
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
