---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Completed 03-07-PLAN.md (실탄 인덱스 30,546행 완주 · Phase 3 7/7 · verify-work 대기)
last_updated: "2026-09-21T05:30:00.000Z"
last_activity: 2026-09-21 -- Phase 03 execution complete (7/7)
progress:
  total_phases: 7
  completed_phases: 2
  total_plans: 16
  completed_plans: 16
  percent: 29
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-09-19)

**Core value:** 유입이나 판매가 있는데 상세페이지가 중국어 원본·단순번역인 상품을, 중복 작업 없이 한 화면에서 골라 고치고 반영하는 것
**Current focus:** Phase 03 — join-detail-state

## Current Position

Phase: 03 (join-detail-state) — **7/7 실행 완료.** `/gsd:verify-work` 대기
Plan: 7 of 7
Status: Phase 03 execution complete
Last activity: 2026-09-21 -- 03-07 실탄 인덱스 완주 + VALIDATION 마감

Phase 01 (board-bid-raise): 9/9 완료. 검증 미완 — `01-HUMAN-UAT.md` 의 되돌리기 실탄 1건 열려 있다.
Phase 02 (꺼진 소재 정리): 2026-09-21 결정으로 Phase 3~5 뒤로 이월.

Progress: [███▒▒▒▒▒▒▒] 2 of 7 phases

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
| Phase 01 P07 | 26min | 4 tasks | 13 files |
| Phase 01 P08 | 140min | 3 tasks | 12 files |
| Phase 01 P09 | 30m | 3 tasks | 12 files |
| Phase 03 P07 | 258min | 4 tasks | 8 files |  *(그중 128min 이 인덱스 완주 대기)*

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
- [Phase 01]: 01-08 실행 라우트는 대상을 받지 않는다 — 부모 미리보기의 targets 파일만 가리킨다 (D-11)
- [Phase 01]: 01-08 첫 실제 인상은 cy728 472건(+4,720원) — 08-30 미되돌림 겹침 3건으로 두 번째 +10 위험 최소
- [Phase 01]: 01-08 되돌릴 수단을 샌드박스 revert dry-run 으로 먼저 증명하고 방아쇠를 당긴다
- [Phase ?]: 되돌리기 대상은 실행 잡 산출물의 성공 adId 만 — 화면이 목록을 만들지 않는다 (D-13)
- [Phase ?]: 회차 전체 되돌리기는 물리적으로 다른 버튼 + 기본 접힘 + 건수 확인 + 1,625px 거리 (D-14/T-1-43)
- [Phase ?]: 쓰기 전 dry-run 으로 CLI 에게 범위를 되묻는다 — 부모 성공 건수와 다르면 409 (Pitfall 2)
- [Phase ?]: 실제 광고 API 되돌리기는 Phase 1 에서 미실행 — 인상 472건 유지(용팀장 지시)
- [Phase 03]: 3시간짜리 루프의 규율은 루프를 돌려서 검증할 수 없다 — 재개 계산을 `ss_index_resume.py`(import 0줄)로 **추출만** 해 1초 테스트로 고정
- [Phase 03]: 미조회(`unresolved=1`)를 '처리완료'로 세지 않는다 — 세면 429 로 빠진 상품이 영원히 굳어 Phase 5 대상에서 영구 소실. 다시 시도하되 해소로 승격은 금지
- [Phase 03]: `r.get(키) or []` 는 **오류를 0건으로 접는 관용구**다 — `groupId` 문자열 오류가 30그룹 9.2초 '성공'으로 둔갑했다. 호출 규약을 `ss_index_calls.py` 한 자리로 모았다
- [Phase 03]: **크레딧 0인 작업은 틀려도 경보가 없다** — 돈이 안 드니 계량기가 없다. 그래서 '성공했는데 0건'을 의심하는 테스트가 따로 필요하다
- [Phase 03]: 조립 테스트가 green 이어도 호출부가 그 필드를 안 넘기면 아무 일도 안 일어난다 (`BulsajaArgv.prefix` 가 2시간 동안 그랬다 — caffeinate 미부착)
- [Phase 03]: 스캔은 `mode=full`, 인덱스는 `mode=summary` — `uploadBulsajaCode` 가 summary 14키엔 없고 full 38키엔 있다
- [Phase 03]: 인덱스 모수는 **서버가 계산한 30그룹**이 정본 (플랜·CONTEXT 의 36그룹/47,105건은 옛 숫자)
- [Phase 03]: 그룹 단계 429 구멍은 Phase 3 범위 밖 이월 — 2026-09-21 용팀장 "그냥 두고 기록만"
- [Phase 03]: 사람이 하지 않은 말을 검증 문서에 적지 않는다 — Task 3 은 **포괄 승인**으로만 기록하고 항목별 진술 미수령을 미해결로 남겼다 (T-3-40)

### Pending Todos

- 🔴 `429-group-stage-silent-completion.md` — 그룹 목록 조회 단계의 HTTP 429 가 "완주"로 둔갑한다.
  2026-09-21 용팀장 결정으로 Phase 3 범위 밖 이월("그냥 두고 기록만").
  **첫 구축을 다시 돌릴 일이 생기면(물갈이 후) 그때 문다.**
  당분간 회피책: 인덱스 잡과 스캔 잡을 동시에 띄우지 마라.

### Blockers/Concerns

- ~~**[Phase 3 선행]** `detail_batch.py` ModuleNotFoundError (STATE-01)~~ — **해소(03-01).** shim 으로 이 맥북에서 돈다
- ~~**[Phase 3 선행]** `aiImageGenerated` 외부 반영 경로 기록 여부 미확인 (STATE-04)~~ — **해소(03-02·03-07).**
  **안 찍는다.** 음성대조 26건 + 실탄 재확인(해소 51행 중 ⚪ **0건** · `uploadDetailContents` 키가
  `{imageTranslated, renderContent}` 둘뿐). **중복방지는 태그 쪽을 봐야 한다** — `aiImageGenerated`
  만 보면 기작업 29건을 다시 태운다. 확정 실험(외부 반영 1건 실측)은 예정대로 Phase 5
- **[Phase 6 게이트]** 수정업로드가 상하단 안내이미지를 어느 시점 기준으로 올리는지 모순 미해결 — 1건 육안 확인으로 깬다 (MARKET-02)
- **[Phase 4 미검증]** 홍보배너 식별은 기성 해법이 없는 가설. 100건 라벨링 미탐 0% 를 통과해야 실작업 투입
- **[환경]** 이 맥북에 `bulsaja-yongssaem` MCP 서버 항목이 없다 — 용쌤 계정 전환 경로가 끊겨 있음 (ENG-08 착수 시 확인)
- OQ-7: 회차마다 든 계정 수가 다른데 화면이 말하지 않는다. 실측 2026-08-29=2계정 · 2026-08-30=4계정 · 2026-09-20=1계정(판정 전). 신선도 배너(D-16)는 경과일만 보여준다 — 01-07/01-08 이 신선도만 보고 회차를 고르면 빠진 계정의 소재가 조용히 대상에서 사라진다(실제 광고비). 배너·드롭다운에 계정 수를 노출할지 01-07 에서 결정할 것
- OQ-8: 수집만 되고 판정 안 된 회차가 있을 때 화면이 알리지 않는다 — 보드의 '새로 수집' 버튼 때문에 재발 구조다. 01-08 이 실행 흐름을 만들 때 자리가 생길 수 있다(지금 고치지 않는다)
- 실제 광고 API 되돌리기가 Phase 1 에서 한 번도 실행되지 않았다 — 사고 시 처음 눌러보는 경로. 소수 건 되돌렸다 즉시 재인상으로 싸게 닫을 수 있다(당일이면 쿨다운 안 걸림)

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-09-21T05:30:00.000Z
Stopped at: Completed 03-07-PLAN.md — Phase 3 실행 7/7. 다음은 `/gsd:verify-work`
Resume file: .planning/phases/03-join-detail-state/.continue-here.md
