---
phase: 05-core-value
verified: 2026-09-29T00:49:38Z
status: passed
score: 5/5 must-haves verified (SC-1 verified with disclosed scope caveat)
overrides_applied: 0
notes:
  - "SC-1 문구는 '5건' 이지만 실탄 대상은 4건이었다. 5번째 후보(dnb2lYw0…)는 배너 제거율초과로 D-04(2026-09-25 auto 결정, 스킵 상품은 라벨로 되살리지 않는다)에 의해 정당하게 제외됐다. 05-05-estimate.md 가 '적격 🔴 가 4건뿐'임을 승인 시점에 용팀장에게 명시적으로 알렸고, 05-06-run.md Task 3 에서 4건 모두 육안 확인 통과했다. 기능 결함이 아니라 그 날 데이터의 실제 모집단이 4건이었던 것 — SC-1 을 실패로 판정하지 않는다."
  - "REQUIREMENTS.md 는 DETAIL-03/04 를 여전히 'Pending' 으로 표기한다. 코드 상으로는 구현·오프라인 테스트·05-06 실탄(요청 10장=서버 10장, 불일치 0)으로 전부 검증됐다 — 이는 05-01-SUMMARY 의 의도적 보류('웹앱 슬라이스·실탄 미완')가 05-06 완료 후 갱신되지 않은 문서 부채다. 기능은 VERIFIED, 문서만 stale (anti-pattern 항목 참조)."
---

# Phase 5: 상세페이지 작업 버튼 ★ Core Value Verification Report

**Phase Goal:** 🔴 상품을 화면에서 골라 기존 상세 이미지(배너 제거분)를 입력으로 AI 상세 생성을 접수하고, 브라우저를 닫아도 폴링이 완주해 결과를 확인한다
**Verified:** 2026-09-29T00:49:38Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria 1-5)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC-1 | 🔴 상품 5건을 골라 접수→폴링까지 터미널 없이 완주, 브라우저를 닫아도 완주 | ✓ VERIFIED (scope caveat) | `evidence/05-06-run.md` Task 1: 접수 잡 `d4b3a37f…` 4건·40장·200크레딧, 종료코드 0, 293초. `webapp/jobs.py:477-520` `spawn()` 이 `start_new_session=True` 로 자식 프로세스를 새 세션에 분리 — 서버/브라우저 생존과 무관하게 완주하는 구조. 실측: 용팀장이 폴링 293초 동안 브라우저 앞에 없었음(evidence 명시), job-reap 유령 잡 미재현. **단 대상은 5건이 아니라 4건** — 5번째(`dnb2lYw0…`)는 D-04(배너 제거율초과 스킵, 사람 라벨로 되살리지 않음)로 정당 제외, 용팀장에게 승인 시점에 고지됨(`05-05-estimate.md` L.35). 재오픈 판정은 읽기전용 GET(`/jobs/{id}/result`)으로 했고 실제 Playwright 브라우저 재현은 하지 않았다(evidence 자인, P3) — 아키텍처·서버상태 증거로 충분하다고 판단 |
| SC-2 | 접수 전 예상 크레딧이 보이고, 기작업 스킵분을 뺀 실제 접수분 기준으로 재보고 | ✓ VERIFIED | `webapp/routes/jobs.py:1516-1623` `POST /jobs/detail/estimate`, `_detail_estimate_table.html`. 실측: 견적 `e9693275…` 선택4→접수4·40장·200크레딧 표시 → 실제 접수 결과(`05-06-run.md`) 실제크레딧 200 = 예상 200 일치. 늘어나는 방향이면 접수 중단하는 가드가 `detail_batch.py:614-618`(D-14)에 존재 |
| SC-3 | 같은 상품 목록 두 번째 회차 재접수 0건 | ✓ VERIFIED | `05-06-run.md` Task 2: 두 번째 견적 `b591a063…` — 선택4/접수0/스킵4, 사유 전부 `aiImageGenerated=True`. `detail_submit` 잡 수 실탄 전후 그대로 1(`select count(*) from jobs where kind='detail_submit'`). D-12 교차 테스트 `webapp/tests/test_detail_cli.py:387-389` (`state.기작업여부` == CLI `기작업`) |
| SC-4 | 생성 장수 `min(제품이미지 수,10)` 하한 2, 예상장수 불일치 시 전량 접수 전 중단 | ✓ VERIFIED | `detail_batch.py:194,483-501` `imageUrls`+`sectionCount` 동시 전송, `:642-651` 예상장수 비교 후 불일치 시 `장수불일치` 상태 기록 + 중단. 단위테스트 `test_detail_cli.py:490-515`(`test_불일치_exit2_taskId_보존` 등, taskId 보존 확인). 실탄 실측: 요청 10장 = 서버 응답 10장 전건 일치, exit 2 미발동(정상 경로) |
| SC-5 | 폴링 타임아웃은 실패로 보고되지 않고 recover 경로 안내 | ✓ VERIFIED | `webapp/jobs.py:421-432` `POLL_INCOMPLETE_OK_KINDS`(exit 3 → done 취급), `webapp/routes/jobs.py:1718-1747` `POST /jobs/detail/poll` — failed(2/4/5)는 400 거부·재접수 경로 없음, done+exit3 또는 미종결>0 만 허용. `_detail_result_table.html:48` `이어서 확인` 버튼만 그림(재시도 버튼 없음). 실탄에서는 타임아웃이 발동하지 않아(폴링 7회 안에 완료) 라이브로 발동하진 않았으나, 05-04 스모크 exit 3 시나리오 + `test_routes_jobs.py:1037-1131` 로 코드 경로가 고정돼 있다 |

**Score:** 5/5 truths verified (SC-1 disclosed scope shortfall — 5건 목표 중 4건 실행, 근거는 정상 스킵 규칙)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `.claude/skills/bulsaja-detail-page/scripts/detail_batch.py` | `--inputs`/`--estimate-only`/`--max-credits`/`--expect-nick`/`--backup-out` 주입구, exit 2/3/4/5 계약 | ✓ VERIFIED | 플래그 전부 존재(L.794 이하), exit 코드 분기 확인(L.642-651, L.868), 플래그 없는 기존 동작은 골든 테스트로 불변 고정(05-01-SUMMARY) |
| `webapp/banner.py::상세입력목록` | D-02 상품 단위 입력 관문 | ✓ VERIFIED | L.265-330, 확인시각/스킵/미판정/하한 전부 예외로 막는 구조 가드 — 기본값으로 열리는 길 없음 |
| `webapp/banner_store.py::확인시각읽기` | D-03 재확인 시각 조회 | ✓ VERIFIED | L.143 |
| `webapp/routes/jobs.py` (`detail/estimate`·`detail/submit`·`detail/poll`) | 견적→승인→접수→이어서확인 라우트 3종 | ✓ VERIFIED | L.1516,1663,1718 각 라우트 존재, 부모 잡 검증·가드 로직 확인 |
| `webapp/templates/board.html` `#detail-estimate`/`#detail-submit-wrap`/`#detail-result` | 보드 UI 진입점 | ✓ VERIFIED | L.352-373,526 — hx-trigger=load 로 최근 상세 작업 재로드(SC-1 재오픈 지원) |
| `webapp/static/board.js` | 견적/접수/이어서확인 버튼 fetch 배선 | ✓ VERIFIED | L.665,786,796 — 각 라우트를 정확히 호출 |
| `webapp/tests/test_detail_cli.py` | 오프라인 CLI 계약 테스트 | ✓ VERIFIED | 726줄, 골든·D-12 교차·불일치exit2·polling 등 커버 |
| `evidence/05-04-zero-cost-check.md`, `05-05-estimate.md`, `05-06-run.md` | 크레딧 0 스모크 · 유료 체크포인트 · 실탄 기록 | ✓ VERIFIED | 세 문서 모두 존재, 서로 견적 id·잡 id·잔액 흐름이 정합함(교차검증됨) |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| 보드 `상세 견적` 버튼 | `POST /jobs/detail/estimate` | `board.js:665` fetch | WIRED | 버튼 클릭 → fetch → 견적 표 렌더 |
| 견적 표 `접수` 버튼 | `POST /jobs/detail/submit` | `board.js:786` (`estimate_job_id`) | WIRED | 견적 잡 id 하나만 참조(대상 재수신 없음, D-14 준수) |
| 결과 표 `이어서 확인` 버튼 | `POST /jobs/detail/poll` | `board.js:796` (`submit_job_id`) | WIRED | 이벤트 위임으로 동적 DOM에도 바인딩 |
| `webapp/jobs.py::spawn` | `detail_batch.py` subprocess | `start_new_session=True` | WIRED | 실탄 실측 293초 완주로 확인 |
| `_판정`(CLI) | `webapp/state.py::기작업여부` | 같은 표본 교차 테스트 | WIRED | `test_detail_cli.py:387-389` |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| 웹앱 테스트 스위트 전체 (read-only) | `.venv-web/bin/pytest webapp/tests -q` | 613 passed, 0 failed | ✓ PASS |
| detail_batch.py 문법/구조 확인 | grep으로 exit 코드·플래그 존재 확인 | 전부 확인됨 | ✓ PASS |
| 실서버 POST 재현 | (지시에 따라 생략 — 크레딧/불사자 서버 재호출 금지) | N/A | ? SKIP (지시에 의해 생략, evidence 문서로 대체 검증) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| DETAIL-01 | 05-01,02,03 | 입력=기존 상세이미지−배너 | ✓ SATISFIED | `banner.상세입력목록`, REQUIREMENTS.md 상 Complete |
| DETAIL-02 | 05-01,02,03 | 장수 min(N,10) 하한2 | ✓ SATISFIED | `detail_batch.py` D-10 로직, REQUIREMENTS.md 상 Complete |
| DETAIL-03 | 05-01 | imageUrls+sectionCount 동시 전송 | ✓ SATISFIED (문서 미갱신) | `detail_batch.py:194,490` 코드로 구현+실탄 실측(10=10) 확인됨. REQUIREMENTS.md 는 여전히 Pending — 문서 부채(anti-pattern 참조) |
| DETAIL-04 | 05-01 | 예상장수 불일치 시 전량 중단 | ✓ SATISFIED (문서 미갱신) | `detail_batch.py:642-651`, 단위테스트 다수. REQUIREMENTS.md Pending — 문서 부채 |
| DETAIL-05 | 05-03,04,05 | 견적→승인→실접수 재보고 | ✓ SATISFIED | 라우트·evidence 정합 |
| DETAIL-06 | 05-04,06 | 폴링 타임아웃≠실패 | ✓ SATISFIED | `POLL_INCOMPLETE_OK_KINDS` |
| DETAIL-07 | 05-01,04 | 접수·폴링 분리, 체크포인트 이어서 확인 | ✓ SATISFIED | `--poll-only`, `POST /jobs/detail/poll` |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `.planning/REQUIREMENTS.md` | 111-112, 223-224 | DETAIL-03/04 가 `[ ] Pending` 으로 남아 있으나 코드·실탄 증거는 완료를 가리킴 | ℹ️ Info | 기능 결함 아님 — 05-06 완료 커밋에서 `requirements-completed` 갱신 시 DETAIL-01~04 를 누락한 문서 부채. 다음 세션에서 REQUIREMENTS.md 체크박스와 상태표만 갱신하면 해소됨 |
| (TBD/FIXME/XXX/TODO 스캔) | - | 없음 | - | Phase 5 가 건드린 모든 파일에서 debt marker 0건 |

### Human Verification Required

없음. 이 페이즈의 유일한 시각적 확인 대상(생성된 상세페이지의 워터마크·내용 누락 여부)은 이미 실행 중 사람이 직접 수행했다 — `05-06-run.md` Task 3, 2026-09-29 용팀장 육안 확인 "4건 다 괜찮음"(워터마크·위챗 잔여 없음, 10장 잘림 내용 누락 없음). 남은 항목(SC-1 브라우저 재오픈의 완전한 시각적 재현)은 아키텍처 증거(`start_new_session=True` 분리 프로세스) + 서버 상태 증거(읽기전용 GET 결과 일치)로 충분하다고 판단했다 — 필요 시 추가로 uat-verifier 브라우저 재현을 원하면 별도 요청.

### Gaps Summary

블로킹 갭 없음. 두 가지만 참고 기록:

1. **SC-1 수량 문구 미달(5건→4건)** — 기능 결함이 아니라 그날 데이터 모집단(D-04 스킵 규칙 정당 적용)의 결과이며, 크레딧 지출 전 용팀장에게 명시적으로 고지·승인받았다. 재발 방지가 필요하면 ROADMAP.md SC-1 문구를 "적격 대상 전량(최대 5건)"처럼 조건부로 다듬는 것을 고려할 수 있으나, Phase 재작업 사유는 아니다.
2. **REQUIREMENTS.md DETAIL-03/04 상태 미갱신** — 문서 부채. 코드·테스트·실탄 증거는 모두 충족을 가리킨다. 다음 커밋에서 체크박스만 갱신하면 된다.

---

_Verified: 2026-09-29T00:49:38Z_
_Verifier: Claude (gsd-verifier)_
