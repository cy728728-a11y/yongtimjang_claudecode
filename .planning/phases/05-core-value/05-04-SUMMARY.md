---
phase: 05-core-value
plan: 04
subsystem: webapp/detail
tags: [detail, submit, poll, exit-code, result-table, board, zero-cost-smoke, DETAIL-05, DETAIL-06, DETAIL-07]
requires: ["05-01 detail_batch 종료코드·summary·detail_status 계약", "05-03 detail kind 3종 · _상세폴더 · 견적 표"]
provides:
  - "POST /jobs/detail/submit (견적 잡 id 하나 → detail_submit, max_credits=estimate.json 예상크레딧)"
  - "POST /jobs/detail/poll (접수/이전 이어서확인 id 하나 → detail_poll --poll-only)"
  - "jobs._finish: detail_submit/poll exit 3 → done (POLL_INCOMPLETE_OK_KINDS)"
  - "jobs.children_of(parent, kind)"
  - "_상세결과ctx · _detail_result_table.html (detail_status.json 정본)"
  - "보드 #detail-submit-wrap · #detail-result(최근 상세 작업, hx-trigger=load) · ctx detail_last"
  - "evidence/smoke_inputs.py · 05-04-zero-cost-check.md"
affects: [05-05, 05-06]
tech-stack:
  added: []
  patterns: ["요청은 부모 잡 id 하나(대상·상한은 부모 산출물에서)", "체크포인트 파일이 결과 정본(잡 exit_code 는 보조)", "SSE done 이벤트(htmx:sseMessage)로 장기 잡 결과 로드 — 폴링으로 붙잡지 않음"]
key-files:
  created:
    - webapp/templates/_detail_result_table.html
    - .planning/phases/05-core-value/evidence/smoke_inputs.py
    - .planning/phases/05-core-value/evidence/05-04-zero-cost-check.md
  modified:
    - webapp/jobs.py
    - webapp/routes/jobs.py
    - webapp/routes/board.py
    - webapp/templates/_job_status.html
    - webapp/templates/_detail_estimate_table.html
    - webapp/templates/board.html
    - webapp/static/board.js
    - webapp/tests/test_jobs.py
    - webapp/tests/test_routes_jobs.py
    - webapp/tests/test_board.py
    - .gitignore
decisions:
  - "exit 3 은 새 상태값 없이 done + exit_code 3 — kind 가 detail_submit/poll 일 때만. bulsaja_scan 의 3(계정 불일치)과 뜻이 달라 kind 로 가른다"
  - "한 견적에서 접수는 한 번 — 두 번째 접수는 taskId 없는 건(접수실패)을 재접수하게 되어 D-18(실패분 재접수 Deferred)과 같다. 단 앞선 접수가 failed 이고 체크포인트에 taskId 가 0이면(아무것도 안 나감) 허용"
  - "이어서 확인 허용 = done+exit3, 또는 done/orphaned 이면서 체크포인트 미종결 > 0. failed(2/4/5)는 400"
  - "결과 ctx 크레딧은 두 가지로 재보고: 접수크레딧(taskId 받은 건 장수×단가, 견적 대비) · 완료크레딧(CLI summary 의 실제크레딧과 같은 정의)"
  - "결과 ctx 의 상태 분류는 detail_batch._요약상태/_미종결과 같은 규칙을 읽기 전용으로 옮겼다 — summary 는 잡이 끝날 때만 쓰여서 orphaned·도중 상태를 못 본다(Pitfall 4)"
  - "접수 버튼 숫자는 견적 조각의 #detail-estimate-meta data 속성(표시용). 활성화 조건 = 견적 잡 done(hidden 칸 일치) · 접수>0 · 예상크레딧>0"
  - "스모크 산출물(evidence/smoke/)은 실상품 코드·이미지 URL 이 있어 .gitignore"
metrics:
  duration: "~45분"
  completed: 2026-09-25
  tasks: 3
  files: 14
---

# Phase 5 Plan 04: 상세 접수·결과·이어서 확인 슬라이스 Summary

견적 표 아래 `접수 — 예상 N크레딧` 버튼이 **견적 잡 id 하나만** 보내면, 서버가 그 견적의 targets 파일과 estimate.json 예상크레딧(`--max-credits`)으로 `detail_submit` 을 띄운다. 폴링이 시간 상한에 닿은 exit 3 은 `done` 으로 남아 "폴링 미완 — 실패 아님" 과 `이어서 확인`(--poll-only) 버튼만 보인다. 결과 표는 `detail_status.json` 을 정본으로 항목 단위를 그리고, 보드를 새로 열면 이 회차의 최근 상세 작업 결과가 되살아난다. 실제 불사자 MCP 견적 스모크는 크레딧 0 으로 돌았다. 실제 접수 0회.

## 완료 태스크

| Task | 내용 | 커밋 |
|------|------|------|
| 1 RED | exit 3·접수·이어서 확인·결과 ctx 실패 테스트 | e92fb96 |
| 1 GREEN | _finish kind 분기 · submit/poll 라우트 · children_of · _상세결과ctx · 결과 표 템플릿 | 14621d8 |
| 2 | 보드 접수 버튼 · SSE done → 결과 표 · 이어서 확인 위임 · _job_status 문구 · detail_last | ee7c5f3 |
| 3 | 크레딧 0 실측 (smoke_inputs.py · 실제 MCP --estimate-only · 기록) | 13b23dd |

## 검증

- `webapp/tests` 전체: **613 passed** (시작 563 → +50: jobs 11 · routes 37 · board 2)
- `node --check webapp/static/board.js` OK
- acceptance grep: submit/poll 라우트 2 · routes/jobs.py 의 retry 0 · `detail_status.json` 5 · 결과 표 `이어서 확인` 3 · 결과 표 `재접수|retry` 0 · board.js submit 1 / poll 1 · `detail_last` 2 · `detail-submit-btn` 1
- 새/수정 템플릿 `| safe` 0건 (board.html 의 두 건은 기존 "쓰지 마라" 주석)
- 사용자 서버(:8765) 재시작·POST·GET 0회. `security_curl.sh` 는 실행 중 서버를 때리므로 돌리지 않았다 — 같은 방어(토큰 403·GET 405)는 TestClient 테스트로 고정

## 크레딧 0 실측 (Task 3-A) — PASS

| 항목 | 값 |
|------|----|
| 계정 | **부킹** (= expected_bulsaja_nick) |
| 잔액 전 → 후 | 총 **930,282** → **930,282** (보유 929,482 · 오늘 무료 800) — 변화 0 |
| 입력 | 회차 2026-09-20 · 배너 `232c3bb3` · 조인 `0889aa1f` · 🔴 후보 5 → 관문 통과 4 (1건 제거율초과 스킵, D-04) |
| 종료코드 | **0** (6초) |
| 선택 · 스킵 · 접수 | 4 · 0 · 4 |
| 총 장수 · 예상 크레딧 | **40장 · 200크레딧** (장당 5) |
| 잘린 상품 | **3개** (27·29·15장 → 10) |
| 접수 0 증거 | `evidence/smoke/detail_status.json` 없음 · generate 문자열 없음 |
| A2 (`find_by_code` 의 `그룹`) | **채워진다** — 3건 `'구매'`, 1건 `None`(조인 산출물과 일치). 전건 null 재발 시 태그 스킵이 죽는 위험은 05-05 견적 때 분포 확인으로 남긴다 |
| workdata 모양 | `data.uploadDetailContents` = `imageTranslated · renderContent` (aiImageGenerated 키 없음 — 미생성 상품의 정상 모양) · 이상 없음 |

상세: `evidence/05-04-zero-cost-check.md`.

## Deviations from Plan

**1. [Rule 2 - 크레딧 안전] 같은 견적의 두 번째 접수 거부 + `jobs.children_of` 추가**
- 계획은 부모 3단 검사만. 그러면 끝난 견적으로 접수를 한 번 더 누를 수 있고, CLI 는 taskId 없는 건(접수실패)을 다시 접수한다 = D-18 이 미룬 실패분 재접수. 400 으로 막고, 앞선 접수가 아무것도 안 낸 경우(failed + 체크포인트 taskId 0)만 허용. 조회 함수 하나를 jobs.py 에 더했다(DB 는 jobs.py 한 곳 규율). 커밋 14621d8

**2. [Rule 3] `_detail_result_table.html` 을 Task 1 에서 만들었다** — Task 1 의 결과 조각 테스트가 템플릿을 요구해서. 내용은 Task 2 명세 그대로(재접수·적용·썸네일 없음)

**3. [Rule 2 - UX] 새 견적을 뜨는 순간 지난 견적의 접수 버튼을 닫는다** — 남기면 지난 견적이 접수된다

**4. [Rule 2] `_job_status.html` 의 failed 분기에서 exit 3 문구 제거** — 이제 3 은 done 분기로 간다. 대신 `done and exit_code == 3` 분기 추가

**5. [Rule 3] 스모크 입력 스크립트는 `jobs.latest_done` 대신 읽기 전용 SQL** — `latest_done` 이 `_reap` 로 사용자 서버의 webapp.db 를 고치기 때문. `.gitignore` 에 `evidence/smoke/` 추가(실상품 코드)

**6. [환경] Task 3-B uat-verifier 미실행 → BLOCKED(오케스트레이터 대기)** — 계획은 BLOCKED 를 계정/연결 사유로만 허용하지만, 이 실행기에는 에이전트 도구가 없다. 아래 통합 조건으로 넘긴다

## UI 자동 검증 (uat-verifier) — 오케스트레이터 대기 · 05-02·05-03·05-04 통합 1회

**환경 조건**
- 사용자 서버(PID 41865, :8765) 재시작·POST 금지 → **격리 DB(`CT_DB_PATH`)·격리 포트 인스턴스**에서 본다. 격리 DB 는 실DB 사본이면 라벨/확인 테이블이 있어 화면이 실제와 같다(사본에 쓰는 건 무방, 원본 webapp.db 는 쓰지 않는다)
- 🔴 **불사자 호출·크레딧 차단**: 접수(`#detail-submit-btn`)·이어서 확인(`.detail-poll-btn`)·`다시 확인` 버튼은 **누르지 마라.** 견적 버튼은 누르면 불사자 조회(크레딧 0)가 나가므로, 격리 인스턴스에선 `jobs.spawn` 을 가짜로 두거나 미리 깐 산출물로 결과 조각만 본다
- 접수 결과 화면은 **시드로** 확인: 격리 DB 에 detail_estimate(done) → detail_submit(done, exit 3) 행과 `web/detail_<견적>/detail_status.json`(taskId 있는 `접수` 1 · `완료` 1 · `완료(기작업)` 1)을 깔고 보드를 연다

**확인 항목**
- 05-02 ① `/banner/review` 확인된 상품 줄에 `확인함` 배지 옆 `다시 확인` 버튼 ② 산출물 생성시각보다 이른 확인은 배지 없이 `확인함` 버튼만 ③ 에러 시 `#label-error`. (실운영 회차는 확인이 전부 낡아 배지가 전부 사라지는 게 정상)
- 05-03 ④ 보드에 `🔴 기본 선택`·`상세 견적 — 크레딧 0`, 화질·장수 입력 없음 ⑤ `🔴 기본 선택` 이 필터 통과·기작업 아님·팬아웃 조회됨 🔴 만 고르고 🟡 는 안 고름, 요약 줄 🔴/🟡 수 ⑥ 🟡 수동 체크 시 요약 🟡 증가 ⑦ 선택 0이면 견적 버튼 비활성 ⑧ 관문 전부 제외 시 `#job-error` 에 상품별 400 사유("다시 확인") 문자열, 잡 안 생김 ⑨ 견적 조각 = 선택→관문 제외→기작업 스킵→접수, 총 장수·예상 크레딧·잘린 상품·계정·잔액(문자열 그대로)
- 05-04 ⑩ 견적 조각이 뜨고 접수>0 이면 `#detail-submit-wrap` 이 열리고 버튼 문구 `접수 — 예상 N크레딧 (K건)` + 안내 "누르는 즉시 크레딧이 나간다 — 위 견적표가 확인 창이다" ⑪ 접수 0 견적이면 접수 버튼이 안 열림 ⑫ 시드한 접수 잡이 있을 때 보드 새로 열기 → `최근 상세 작업` 섹션이 결과 표를 자동 로드: 집계 줄(접수·완료·실패·스킵·폴링 미완·실제 접수분 크레딧/견적 예상) · 항목 표(판매자상품코드·상태·장수·크레딧·사유·작업번호 끝 8자리) ⑬ 미종결 있으면 "폴링 미완 N건 — 실패 아님" + `이어서 확인 — 크레딧 0` 버튼만, 재접수/실패분 다시 보내기/적용 버튼 없음 ⑭ 작업 상태 조각: done+exit3 은 "폴링 미완 — 실패 아님", failed 2/4/5 는 장수 불일치/계정 불일치/견적 초과 문구 ⑮ 콘솔 에러 0

## Known Stubs

없음. (생성 이미지 썸네일은 계획상 재량 — 린 MVP 로 넣지 않았다.)

## Threat Flags

없음 — 새 표면(POST /jobs/detail/submit · /jobs/detail/poll)은 threat_model T-05-15~20 에 있고 전부 반영: 요청은 잡 id 하나(추가 필드 무시) · 상한은 부모 estimate.json · 재접수 경로 없음 · WRITE_KINDS 가드 · BULSAJA 사전점검 409 + CLI --expect-nick · 스모크 산출물 web/ 밖 · 결과 표 taskId 끝 8자리만.

## Self-Check: PASSED

## uat-verifier 결과 (2026-09-25 · 05-02/03/04 통합 1회 · 오케스트레이터 실행)

- **판정: PASS** — 항목 ①~⑮ 전부 pass · P0~P2 없음 · P3 1건(배너 검수 스트립 figure 접근성 이름 — Phase 4 기존 마크업, 스캐너 오탐 가능)
- 격리 인스턴스(DB 복사본·별도 포트)만 사용 · 사용자 서버(:8765)·실 webapp.db·실 run-dir 미접촉 · 불사자 호출 0 · 크레딧 0 · 소스 변경 0
- 사람 몫: 심미만 — `~/.claude/uat/uat-artifacts/20260925-seller-control-tower/board-detail-result.png`, `banner-review.png`
