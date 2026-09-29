---
phase: 05-core-value
plan: 06
subsystem: webapp/detail
tags: [detail, submit, poll, real-money, smoke, DETAIL-05, DETAIL-06, DETAIL-07]

requires:
  - phase: 05-05
    provides: "승인된 estimate_job_id = e9693275-80fc-4a84-8bc2-bb59c40eaf90 (4건 · 40장 · 예상크레딧 200 · 부킹)"
provides:
  - "첫 실탄 완주: 접수 잡 d4b3a37f (4건 · 200크레딧 · 종료코드 0)"
  - "SC-1~5 실측 판정표 (evidence/05-06-run.md)"
  - "D-13 실측: 불사자 AI 상세 생성 경로는 aiImageGenerated=True 4/4 찍는다 — 태그 쓰기 폴백 불필요"
  - "육안 확인(용팀장, 2026-09-29): 4건 다 괜찮음 — 워터마크·위챗 잔여 없음, 10장 잘림 내용 누락 없음"
affects: [06-05, 06-06]

tech-stack:
  added: []
  patterns: ["승인된 견적 id 1회만 클릭 접수 — 재접수 규칙은 detail_submit 잡 수 1로 acceptance 검증", "D-13 판정은 두 번째 견적의 사유 필드(aiImageGenerated vs 태그)로 구분"]

key-files:
  created: []
  modified:
    - .planning/phases/05-core-value/evidence/05-06-run.md
    - .planning/STATE.md
    - .planning/ROADMAP.md
    - .planning/REQUIREMENTS.md

key-decisions:
  - "D-13 기록됨 — 불사자 AI 상세 생성 경로(웹앱 접수)는 aiImageGenerated 를 4/4 찍는다. 외부 반영 경로(Phase 3 STATE-04, 29건)는 여전히 태그로만 잡힌다 — 두 사실 모두 참, 경로가 다르다"
  - "태그 쓰기 폴백(L-01 ④)은 실행하지 않는다 — D-13 이 기록됨이라 이 플랜에서 건드릴 이유가 없다"
  - "용팀장 육안 확인: 4건 다 괜찮음 — 워터마크 제거·중복작업 회피가 실제로 동작한다는 마지막 증거"

patterns-established:
  - "실탄 1회 규칙: 승인 id 로 detail_submit 잡 정확히 1개만 — 이어서 확인(--poll-only)은 크레딧 0 이라 별도 카운트"

requirements-completed: [DETAIL-05, DETAIL-06, DETAIL-07]

duration: "2026-09-26 ~ 2026-09-29 (Task 1-2 자동 실행 + Task 3 사람 육안 확인 대기 포함)"
completed: 2026-09-29
---

# Phase 5 Plan 06: 첫 실탄 · 재오픈 완주 · D-13 실측 Summary

승인된 견적 `e9693275`로 🔴 4건을 한 번만 접수해(`d4b3a37f`, 200크레딧, 종료코드 0) 브라우저 없이 완주시켰고, 같은 목록의 두 번째 견적이 접수 0건(`aiImageGenerated` 4/4 근거)임을 확인해 재작업 방지가 실제로 작동함을 증명했다. 용팀장이 4건의 새 상세페이지를 육안으로 확인해 "다 괜찮음"이라고 답하며 Core Value(중복 없이 골라 고치기)의 마지막 증거가 채워졌다.

## Performance

- **Duration:** Task 1-2는 자동 실행 후 즉시(수 분), Task 3는 용팀장 확인 대기 (2026-09-26 접수 → 2026-09-29 육안 확인 회신)
- **Started:** 2026-09-26T16:24:54+09:00 (접수 잡 시작)
- **Completed:** 2026-09-29 (Task 3 육안 확인 회신)
- **Tasks:** 3 (Task 1 자동, Task 2 자동, Task 3 checkpoint:human-verify)
- **Files modified:** 4 (evidence/05-06-run.md, STATE.md, ROADMAP.md, REQUIREMENTS.md)

## Accomplishments

- **SC-1 (재오픈 완주):** 접수 잡이 브라우저 없이 293초(폴링 7회) 만에 완주(exit 0), 재오픈한 보드에서 4행 결과표(판매자상품코드·상태·장수·크레딧·사유)와 재접수 버튼 없음을 확인 — PASS
- **SC-2 (실제분 재보고):** 실제크레딧 200(summary 집계 정본) = 예상 200, 초과 0
- **SC-3 (2차 견적 접수 0):** 같은 4건으로 두 번째 견적(`b591a063`)을 돌려 접수 K=0·예상크레딧 0 확인 — 새 detail 폴더라 로컬 체크포인트가 아니라 서버 플래그(`aiImageGenerated`)로 스킵됨을 증명
- **SC-4 (멈춤 규칙):** exit 2/4/5 발생 0, 재시도·--retry-failed 실행 0
- **SC-5 (타임아웃 처리):** 이번 실탄에서 폴링미완 0 — 발동 안 함(근거: 05-04 스모크의 exit 3 경로 단위 테스트)
- **D-13 실측:** 불사자 AI 상세 생성 경로는 `aiImageGenerated=True` 를 4/4 찍는다 → 태그 쓰기 폴백(L-01 ④) 불필요, 이 페이즈에서 태그 쓰기 호출 0회
- **육안 확인:** 용팀장이 4건 전부 확인 — 워터마크·위챗 잔여 없음, 10장 잘림으로 인한 내용 누락 안 보임

## Task Commits

1. **Task 1+2: 실탄 접수·완주·재오픈 판정 + 2차 견적 SC-3·D-13 실측** - `c38a797` (docs)
2. **Task 3: 육안 확인 회신 기록** - `711466a` (docs)

**Plan metadata:** (이 커밋) `docs(05-06): complete 실탄·재오픈·D-13·육안확인 plan`

## Files Created/Modified

- `.planning/phases/05-core-value/evidence/05-06-run.md` - 접수 잡·argv·항목별 결과·실제크레딧·재오픈 판정·2차 견적·D-13·육안 확인 전체 기록
- `.planning/STATE.md` - aiImageGenerated 블로커 05-06 실측으로 갱신, 포지션/진행률 갱신
- `.planning/ROADMAP.md` - Phase 5 플랜 진행 6/6 완료로 갱신
- `.planning/REQUIREMENTS.md` - DETAIL-05/06/07 Complete로 갱신

## Decisions Made

- D-13 기록됨 → 태그 쓰기 폴백은 실행하지 않는다 (evidence Task 2/3)
- 육안 확인 결과를 근거로 Core Value 워터마크 우려는 이번 4건에서는 해소로 기록 (재발 시 별도 quick/페이즈)

## Deviations from Plan

None - plan executed exactly as written. Task 3 체크포인트는 D-13 "기록됨" 조건에 따라 폴백 승인/보류 질문을 계획대로 건너뛰었다(플랜 §Task 3 action 명시 분기).

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 5 (Core Value) 플랜 6/6 완료. DETAIL-05/06/07 요구사항 충족
- Phase 6 (마켓 수정업로드)의 Wave 4(06-05)가 "Phase 5 05-06 완료"에 블록돼 있었음 — 이제 해제
- Deferred: 워터마크/위챗 제거 가공은 이번 4건에서 문제없었으나, 향후 다른 배치에서 재발하면 별도 quick/페이즈로 뺀다

---
*Phase: 05-core-value*
*Completed: 2026-09-29*
