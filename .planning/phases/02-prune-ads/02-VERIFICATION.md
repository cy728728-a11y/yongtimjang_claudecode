---
phase: 02-prune-ads
verified: 2026-10-01T19:30:00+09:00
status: passed
score: 6/6 must-haves verified
overrides_applied: 0
---

# Phase 2: 되돌릴 수 없는 쓰기 — 꺼진 소재 정리 Verification Report

**Phase Goal:** 백업이 선행되는 파괴적 삭제를 화면에서 안전하게 돌리고, 그 과정에서 모든 버튼이 공유할 안전 계약(재조회·상한·감사 로그·작업 잠금)을 완성한다
**Verified:** 2026-10-01
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP §Phase 2 Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | 규칙⑥ 중 `AD_ABNORMAL_INTERLOCK` 소재만 전부 나열, 건수 타이핑 확인 뒤에만 삭제 실행 (검수중·거부 제외) | ✓ VERIFIED | `prune.py:26` `DELETE_REASONS = ("AD_ABNORMAL_INTERLOCK",)`, `deletable()` 필터. `routes/prune.py:230-234` typed_count ≠ 합계 → 409. 실데이터: 02-06 커밋 1350건 전부 `AD_ABNORMAL_INTERLOCK`(사유분포 100%), `typed_count=1350` 일치. UAT U1-U4 PASS(미리보기 표·건수 타이핑·409) |
| 2 | 백업 실패 시 삭제 0건 + 사유 화면 표시 | ✓ VERIFIED | `routes/prune.py:418-419` `_백업실패문구` = "백업을 못 써서 이 계정은 한 건도 지우지 않았다", `aborted == "backup_failed"` 분기. UAT U6에서 uat-b 백업실패 시나리오 PASS로 실증(실데이터는 7계정 백업 전부 성공이라 이 경로는 UAT 시드로만 확인됨 — 코드·테스트는 존재) |
| 3 | 미리보기 낡음(24h) → 실행 거부, 실행 직전 재조회에서 빠진 항목이 사유와 함께 보고 | ✓ VERIFIED | `routes/prune.py:181-183` 24h 초과 400, `prune.py` revived_filter(CLI) → `excluded`(다시_켜짐/재조회에_없음/사유_바뀜). 실데이터: 02-06 결과 재조회 제외 0·새로 꺼짐 0(대상 그대로 지나감 — 보고 경로가 '해당 없음'으로 정상 통과). UAT U5(만료 B)·U6(제외 사유 5행) PASS |
| 4 | 정지 소재 과거 클릭이 현재 유입으로 안 보임 + 1클릭 오판정 표시 | ✓ VERIFIED | `webapp/tests/test_board.py:899` `test_꺼진_소재의_과거_실적은_합산하지_않는다` 등 BOARD-05 테스트 다수 green. `routes/board.py:314` `POST /board/misjudged` → `misjudged.jsonl` append, 최신 줄이 이김. UAT U9(광고정지 배지)·U10(오판정 토글 유지/해제) PASS |
| 5 | 같은 대상 중복 실행 차단 + 재시작 시 고아 정리 + 장시간 작업 중 절전 방지 | ✓ VERIFIED | ENG-04: `routes/prune.py:202-204` 성공 커밋 있으면 409. ENG-05: `main.py:64-68` lifespan에서 `job_engine.reap_on_startup()` 호출, 02-06 재시작 로그 "[기동] 고아 잡 0건 정리" 실측. ENG-06: `jobs.py:916` `_수면방지_프리픽스`에 `"prune_commit"` 포함 → caffeinate -i 래핑. UAT U8(3겹 중복 차단: UI disabled·조각 재요청·훅 직접 POST 전부 차단) PASS |
| 6 | 실패분만 재시도 가능 + 모든 실행이 audit.jsonl(JSONL)에 기록 | ✓ VERIFIED | `routes/prune.py:264-313` `/jobs/prune/retry` (실패 adId ∩ 미리보기 adId). `webapp/audit.py` + `jobs.py:488` WRITE_KINDS 종료 훅. 실데이터: `~/python_work/data/control-tower/audit.jsonl`에 prune_commit 1줄 실측 확인(시각/잡id/부모/계정/대상수 1350/성공 1350/실패 0/크레딧 0/종료코드 0 — 전부 일치). UAT U7(재시도 플로우) PASS |

**Score:** 6/6 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `.claude/skills/naver-ads-weekly/scripts/prune.py` | `DELETE_REASONS`·`deletable`·`backup_paused`·`delete_ads`·`run_prune`·`excluded_reasons` | ✓ VERIFIED | 모든 함수 존재, 테스트 33개 통과 |
| `.claude/skills/naver-ads-weekly/scripts/run_ads.py` | `cmd_prune` + `--only-ads`/`--preview-out`/`--max-items`/`--backup-tag` | ✓ VERIFIED | 전 플래그 확인, cmd_prune 구현 |
| `.claude/skills/naver-ads-weekly/scripts/ads_rules.py` | ⑥ 행 `productLive`/`statusReason` | ✓ VERIFIED | `productLive=(...).get("mallProductId") in live_malls` |
| `webapp/jobs.py` | prune kind 2종, WRITE_KINDS/SINGLETON_KINDS 등록, reap_on_startup, caffeinate | ✓ VERIFIED | 전부 확인 |
| `webapp/audit.py` | append-only JSONL 기록 | ✓ VERIFIED | 실데이터 audit.jsonl 라인 실측 일치 |
| `webapp/routes/prune.py` | preview/commit/retry 3라우트 + ctx 2종 | ✓ VERIFIED | 459줄, 54개 라우트 테스트 통과, 스텁 패턴 0건 |
| `webapp/routes/board.py` | `POST /board/misjudged` | ✓ VERIFIED | append + 최신 줄 우선 로직 확인 |
| `webapp/board.py` | 정지사유 집계·광고정지 배지 | ✓ VERIFIED | D-13 로직 + 테스트 다수 |
| `webapp/templates/_prune_preview_table.html`, `_prune_result_table.html` | 미리보기/결과 조각 | ✓ VERIFIED | `결과표` 딕셔너리에 등록, UAT에서 실제 렌더 확인(U2/U6) |
| `webapp/static/prune.js`, `board.js` | 건수 타이핑·htmx 훅 | ✓ VERIFIED | 존재·UAT 실클릭으로 동작 확인 |
| `webapp/tests/fixtures/prune_uat_seed.py` | 격리 UAT 시드 | ✓ VERIFIED | 02-05 UAT 11/11 PASS로 사용 실증 |
| `.planning/phases/02-prune-ads/02-UAT.md` | 판정 + `uat-auto: done` | ✓ VERIFIED | 파일에 마커 존재, PASS 11/FLAKY 0/FAIL 0/BLOCKED 0 |
| `evidence/02-06-commit.md` | 승인 원문·잡id·결과·백업·감사로그 줄 | ✓ VERIFIED | 실제 job DB·audit.jsonl·backup 파일과 전부 교차 확인됨 |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `run_ads.cmd_prune --preview-out` | `prune_preview` 잡 산출물 | `_상세잡만들기` → CLI subprocess | WIRED | `_산출물()`이 result_path JSON을 읽고 accounts dict 검증 |
| 미리보기 산출물 | `prune_commit --only-ads` | `targets_path_override=부모.get("result_path")` | WIRED | `routes/prune.py:239` 코드 확인 — 미리보기와 커밋이 같은 파일을 공유(SAFE-06) |
| `POST /jobs/prune/commit` | `jobs.create_job` | `_상세잡만들기("prune_commit", ...)` | WIRED | 실데이터: 커밋 응답 job_id `96e2b934…`가 실제 webapp.db jobs 테이블·audit.jsonl과 일치 |
| 웹 `board.js` 오판정 버튼 | `POST /board/misjudged` | `window.관제탑.요청` | WIRED | `board.js:210` 확인, UAT U10 실클릭으로 확인 |
| lifespan 기동 | `job_engine.reap_on_startup()` | 직접 호출 | WIRED | `main.py:66`, 02-06 실재시작 로그로 실증 |
| WRITE_KINDS 잡 종료 | `audit.record()` | 잡 종료 훅 | WIRED | `jobs.py:488`, 실데이터 audit.jsonl에 prune_commit 라인 실존 |

### Behavioral Spot-Checks (실데이터 교차검증)

| Behavior | Check | Result | Status |
|----------|-------|--------|--------|
| 02-06 SUMMARY의 커밋 잡id가 실제 jobs 테이블에 존재 | `sqlite3 webapp.db "select id,kind,status,exit_code from jobs where id='96e2b934-...'"` | `prune_commit\|done\|0` | ✓ PASS |
| 02-06 SUMMARY의 미리보기 잡id가 실제 jobs 테이블에 존재 | 동일 쿼리 | `prune_preview\|done\|0` | ✓ PASS |
| audit.jsonl에 해당 줄이 SUMMARY 원문과 일치 | `tail audit.jsonl` | 대상수 1350·성공 1350·실패 0·종료코드 0 전부 일치 | ✓ PASS |
| 백업 파일 14개(미리보기 7 + 커밋 7) 실존 | `ls paused-backup/ \| grep "96e2b934\|e5363aac"` | 14개 파일 확인 | ✓ PASS |
| 전체 테스트 스위트 | `.venv-web/bin/pytest webapp/tests` | 1086 passed | ✓ PASS |
| CLI 테스트 스위트 | `.venv/bin/python3 -m pytest .claude/skills/naver-ads-weekly/scripts` | 129 passed | ✓ PASS |
| no_commit_guard | `bash webapp/tests/no_commit_guard.sh` | OK (--commit 리터럴 0건) | ✓ PASS |
| 운영 서버 무손상 | `lsof -iTCP:8765`, `git status` | PID 유지, 트리 clean | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Status | Evidence |
|-------------|------------|--------|----------|
| ENG-04 | 02-02 | ✓ SATISFIED | 멱등 409, UAT U8 3겹 확인 |
| ENG-05 | 02-02 | ✓ SATISFIED | lifespan reap, 02-06 실재시작 로그 |
| ENG-06 | 02-02 | ✓ SATISFIED | `_수면방지_프리픽스`에 prune_commit 포함 |
| SAFE-04 | 02-01/03/06 | ✓ SATISFIED | backup_tag, 02-06 잡별 14개 백업 실존 |
| SAFE-05 | 02-01/03/06 | ✓ SATISFIED | 재조회·제외 사유, 02-06 결과 집계 일치 |
| SAFE-06 | 02-01/03 | ✓ SATISFIED | 미리보기/커밋 동일 산출물 경로 공유 |
| SAFE-07 | 02-01/02/03 | ✓ SATISFIED | 상한 8000, 02-06 1350<8000 확인 · UAT U5(9000 초과 거부) |
| FLOW-03 | 02-03 | ✓ SATISFIED | 24h 체크, UAT U5 만료 사례 |
| FLOW-06 | 02-03 | ✓ SATISFIED | `/jobs/prune/retry`, UAT U7 |
| FLOW-07 | 02-02/06 | ✓ SATISFIED | audit.jsonl 실라인 |
| BOARD-05 | 02-04 | ✓ SATISFIED | 정지사유·광고정지 배지·합산 제외 테스트 |
| BOARD-06 | 02-04 | ✓ SATISFIED | 오판정 토글, UAT U10 |
| PRUNE-01 | 02-01/06 | ✓ SATISFIED | DELETE_REASONS 단일값, 실데이터 사유분포 100% |
| PRUNE-02 | 02-01/06 | ✓ SATISFIED | 백업 성공 후에만 삭제(코드+실데이터) |
| PRUNE-03 | 02-01/03/06 | ✓ SATISFIED | 전 행 나열, UAT U2 |

모든 15개 요구사항이 02-01~06 플랜 중 하나 이상에서 구현·테스트·실데이터로 뒷받침됨. 고아(orphaned) 요구사항 없음.

### Anti-Patterns Found

없음. 트랙 소유 파일(`routes/prune.py`, `webapp/jobs.py`, `webapp/audit.py`, `prune.py`, `run_ads.py`, `board.py`, `routes/board.py`, `static/prune.js`, `static/board.js`, 템플릿 2개)에 TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER/"구현 예정" 패턴 0건.

### Human Verification Required

없음. UAT.md의 화면 흐름 10항목(U1-U10)은 `uat-verifier` 역할을 대신한 직접 Playwright 세션으로 이미 PASS 처리됐고 `<!-- uat-auto: done -->` 마커가 남아 있다. CLAUDE.md 규칙상 사람 몫 ①(시각 심미)만 남아 있으나 — 이는 UAT.md 자체가 이미 "사용자 확인 (① 시각 심미만)" 섹션으로 분리해 둔 선택 항목이며, 02-06 실탄 삭제는 이미 용팀장 승인("전부 승인, 상한 유지")을 받아 완료됐다. 게이트를 막는 미판정 항목은 없다.

### Gaps Summary

갭 없음. 6개 로드맵 성공기준, 15개 REQUIREMENTS 항목, 6개 플랜의 모든 must_haves(truths/artifacts/key_links)가 코드·테스트·실데이터(실제 webapp.db 잡 레코드, 실제 audit.jsonl 라인, 실제 14개 백업 파일, 실제 1350건 삭제 결과)로 교차 검증됐다. 테스트 스위트 1215건(웹앱 1086 + CLI 129) 전부 green, no_commit_guard 통과, 운영 서버·실데이터 무손상 확인.

---

*Verified: 2026-10-01*
*Verifier: Claude (gsd-verifier)*
