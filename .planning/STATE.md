---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Completed 01-06-PLAN.md (진행 로그 SSE)
last_updated: "2026-09-20T09:35:18.543Z"
last_activity: 2026-09-20
progress:
  total_phases: 7
  completed_phases: 0
  total_plans: 9
  completed_plans: 6
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-09-19)

**Core value:** 유입이나 판매가 있는데 상세페이지가 중국어 원본·단순번역인 상품을, 중복 작업 없이 한 화면에서 골라 고치고 반영하는 것
**Current focus:** Phase 01 — board-bid-raise

## Current Position

Phase: 01 (board-bid-raise) — EXECUTING
Plan: 7 of 9
Status: Ready to execute
Last activity: 2026-09-20

Progress: [███████░░░] 67%

## Performance Metrics

**Velocity:**

- Total plans completed: 0
- Average duration: —
- Total execution time: —

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**

- Last 5 plans: —
- Trend: —

*Updated after each plan completion*
| Phase 01 P01 | 8min | 3 tasks | 19 files |
| Phase 01 P02 | 14min | 3 tasks | 3 files |
| Phase 01 P03 | 22min | 3 tasks | 14 files |
| Phase 01 P04 | 32min | 3 tasks | 8 files |
| Phase 01 P05 | 47min | 3 tasks | 9 files |
| Phase 01 P06 | 78min | 3 tasks | 17 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [로드맵]: v1 순서는 [A] — 조인 불필요·되돌릴 수 있는 버튼 2개로 3단 틀을 먼저 굳히고 Core Value 를 얹는다
- [로드맵]: `traffic_analytics` 는 v1 유입 소스로 쓰지 않는다 → 엔티티 해소(JOIN)가 실제 단계로 필요 (Phase 3)
- [로드맵]: 홍보배너 식별은 독립 단계(Phase 4). 상세 생성에 묶으면 100건 라벨링 게이트가 생략된다
- [로드맵]: 마켓 쓰기(Phase 6)를 크레딧 쓰기(Phase 5)와 분리 — 실패 모드와 복구 비용이 다르다
- [로드맵]: 기존 CLI 는 재작성하지 않고 서브프로세스로 래핑한다 (ENG-01)
- [Phase 01]: 웹앱 의존은 `.venv-web` 로 분리 — CLI `.venv` 는 손대지 않는다 (subprocess 경계)
- [Phase 01]: `prep_summary.json` 실데이터는 계정 alias 로 한 겹 중첩 — `freshness()` 가 평평·중첩 두 모양을 모두 읽는다
- [Phase 01]: `workspace.toml` 파싱 실패는 RuntimeError, 파일 부재는 `{}`. `data_root()` 만 삼킨다(폴백이 돈으로 안 이어짐) — `settings` 는 안 삼킨다(D-08 가드 보존, T-1-12)
- [Phase 01]: D-08 상한 리터럴 금지를 문서가 아니라 테스트로 강제 — `webapp/**` 를 매 실행 훑는다
- [Phase 01]: `run_dir_path()` 가 회차 이름의 유일한 관문 — 화이트리스트 밖 이름은 Path 가 되지 않는다 (T-1-11)
- [Phase 01]: 01-02 only_ads 필터는 run_bids 안쪽 update_streaks 뒤·plan_raise 앞 한 줄 — 앞에 걸면 연속실패 카운팅이 통째로 빠진다
- [Phase 01]: 01-02 --only-ads 읽기 실패는 exit 1. 전량 실행으로 폴백하지 않는다 (T-1-05)
- [Phase 01]: 01-02 accounts 서브커맨드 화이트리스트 투영으로 SAFE-03 을 구조로 보장 — 웹앱이 자격증명 파일을 두 번째로 갖지 않는다
- [Phase 01]: 01-03 openapi_url=None 까지 껐다 — docs 만 끄면 /openapi.json 이 토큰 없이 라우트 전체를 내준다
- [Phase 01]: 01-03 장시간 프로세스의 줄 출력은 flush=True 필수 — tty 가 아니면 버퍼가 영영 안 비워져 기동 토큰 URL 이 사라진다
- [Phase 01]: 01-03 CT_PORT 는 settings 계층에서 처리 — 기동 스크립트가 직접 읽으면 Origin 화이트리스트가 옛 포트에 남는다
- [Phase 01]: 01-04 보드 데이터는 인라인 script type=application/json + tojson — 요청 1번이라 신선도 배너와 표가 어긋나지 않고 tojson 이스케이프로 상품명 XSS 가 구조적으로 불가능 (T-1-17)
- [Phase 01]: 01-04 템플릿 컨텍스트 키 rows_json(문자열) → rows(리스트). 문자열은 자동 이스케이프를 꺼야 script 에 들어가고 그게 XSS 방어를 무너뜨린다. Plan 01-06/01-07 이 이 이름을 전제
- [Phase 01]: 01-04 Tabulator dataFiltered 안에서 getDataCount('active') 금지 — activeRows 커밋 전에 발화해 건수가 한 스텝 뒤처진다. 이벤트 2번째 인자만 믿는다
- [Phase 01]: 01-04 브라우저 JS 회귀는 pytest 로 흉내 내지 않는다. board_cdp.sh(헤드리스 크롬+CDP)를 security_curl.sh 와 같은 계층에 둔다
- [Phase 01]: 01-05 작업 생성은 HTTP 를 모르는 jobs.create_job 함수. 라우트는 예외를 상태코드로 번역만 (D-17/ENG-07)
- [Phase 01]: 01-05 쓰기 잡(prep·bids_commit·revert_*)은 전역 1개. 가드+INSERT 를 BEGIN IMMEDIATE 로 원자 결합 (Pitfall 3)
- [Phase 01]: 01-05 htmx 폼은 stdlib parse_qsl 로 직접 푼다 — python-multipart 의존성을 늘리지 않는다
- [Phase ?]: 01-06 폴링과 SSE 를 조각 단위로 분리 — 패널 전체를 2초마다 outerHTML 로 교체하면 그 안의 EventSource 가 2초마다 끊겼다 붙는다. _job_status.html 만 폴링이 때린다
- [Phase ?]: 01-06 진행 로그는 매 접속 오프셋 0 전량 재생. 재연결 헤더에 이어받기를 맡기지 않는다 — htmx-ext-sse 가 재연결 때 EventSource 를 새로 만들어 그 상태를 버린다 (T-1-27)
- [Phase ?]: 01-06 sse-close 는 연결을 여는 엘리먼트에 붙인다(sse.js:235). 자식에 붙이면 조용히 무시돼 작업 종료 후 무한 재연결 — 리서치·플랜 예제가 틀렸다. vendoring 소스가 문서보다 정본
- [Phase ?]: 01-06 SC-03 자동 테스트는 진짜 uvicorn 을 띄운다 — TestClient 는 ASGI 앱을 끝까지 돌린 뒤 BytesIO 로 주므로 부분 수신·끊김을 흉내조차 못 한다 (CT_DB_PATH/CT_JOB_LOG_DIR env 추가 이유)
- [Phase ?]: 01-06 토큰 비교는 바이트로 — compare_digest 가 str 비ASCII 에서 TypeError 를 던져 403 자리에 500 이 났다
- [Phase ?]: 01-06 V-SAFE-02c 를 c1/c2 로 분리 — c1 은 실재 라우트로 '가드를 통과해 앱 로직이 답한다'까지 보고, c2 는 미리보기 라우트가 생기면 자동으로 -lt 400 이 된다

### Pending Todos

None yet.

### Blockers/Concerns

- **[Phase 3 선행]** `detail_batch.py` 가 이 맥북에서 `ModuleNotFoundError` 로 안 돈다 (윈도 경로 하드코딩) — Core Value 경로가 막혀 있다 (STATE-01)
- **[Phase 3 선행]** `aiImageGenerated` 가 외부 반영 경로에서 찍히는지 미확인 — 답이 안 나오면 중복방지 설계가 확정되지 않고 크레딧 무한 루프 위험 (STATE-04)
- **[Phase 6 게이트]** 수정업로드가 상하단 안내이미지를 어느 시점 기준으로 올리는지 모순 미해결 — 1건 육안 확인으로 깬다 (MARKET-02)
- **[Phase 4 미검증]** 홍보배너 식별은 기성 해법이 없는 가설. 100건 라벨링 미탐 0% 를 통과해야 실작업 투입
- **[환경]** 이 맥북에 `bulsaja-yongssaem` MCP 서버 항목이 없다 — 용쌤 계정 전환 경로가 끊겨 있음 (ENG-08 착수 시 확인)
- OQ-7: 회차마다 든 계정 수가 다른데 화면이 말하지 않는다. 실측 2026-08-29=2계정 · 2026-08-30=4계정 · 2026-09-20=1계정(판정 전). 신선도 배너(D-16)는 경과일만 보여준다 — 01-07/01-08 이 신선도만 보고 회차를 고르면 빠진 계정의 소재가 조용히 대상에서 사라진다(실제 광고비). 배너·드롭다운에 계정 수를 노출할지 01-07 에서 결정할 것

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-09-20T09:35:18.538Z
Stopped at: Completed 01-06-PLAN.md (진행 로그 SSE)
Resume file: None
