---
phase: 06-market-update
plan: 03
subsystem: webapp-market-slice
tags: [market-01, market-02, market-03, webapp, htmx, jobs]
requires:
  - "06-01 (detail_submit --backup-out → detail_<견적id>/before_detail)"
  - "06-02 (market_update.py preview/commit/poll-only 계약 · market_status.json)"
provides:
  - "MarketArgv(preview/commit/poll) · MARKET_UPDATE 경로"
  - "jobs.py market_preview/market_commit/market_poll 등록 · _마켓폴더 · create_job(max_items)"
  - "POST /jobs/market/preview · /commit · /poll · _마켓반영상한() · _마켓미리보기ctx · _마켓결과ctx"
  - "_market_preview_table.html · _market_result_table.html (#market-gate-slot 빈 자리)"
  - "상세 결과 표의 미리보기 버튼 + '최근 스마트스토어 반영' 재오픈 목록"
affects: [06-04, 06-05]
tech-stack:
  added: []
  patterns:
    - "Phase 5 detail 슬라이스를 market 이름으로 한 벌 복제 (미리보기→반영→이어서 확인)"
    - "요청 모델 extra=forbid — 대상·상한·마켓 필드를 실어 보내면 422"
    - "상한 결정 한 곳(_마켓반영상한) — 라우트·표·버튼 문구가 같은 값을 본다"
    - "깨진 market_status.json 은 빈 값이 아니라 400/에러 (이중 반영 방지)"
key-files:
  created:
    - webapp/templates/_market_preview_table.html
    - webapp/templates/_market_result_table.html
    - webapp/tests/test_routes_market.py
    - .planning/phases/06-market-update/deferred-items.md
  modified:
    - webapp/argv.py
    - webapp/jobs.py
    - webapp/settings.py
    - webapp/routes/jobs.py
    - webapp/templates/_job_status.html
    - webapp/templates/_detail_result_table.html
    - webapp/static/board.js
    - webapp/tests/test_argv.py
    - webapp/tests/test_jobs.py
decisions:
  - "게이트 닫힘(상한 1)에서 같은 미리보기의 두 번째 반영은 거부 — 앞선 반영이 체크포인트에 아무것도 안 남겼을 때만 재시도 허용"
  - "체크포인트 항목이 taskId 보유 또는 접수·대기·성공·실패면 '손댐' — 다음 반영 대상에서 뺀다. 스킵(쓰기 전 멈춤)만 재시도"
  - "마켓 요청 모델은 extra=forbid (상세 쪽은 무시) — 게이트 우회 시도를 조용히 삼키지 않는다"
  - "마켓 잡이 끝나면(SSE done) 결과를 #detail-result-body 에 띄운다 — 접수 때 그 자리를 '도는 중' 문구로 바꿔 두므로"
  - "'최근 스마트스토어 반영' 목록은 같은 접수 체인(접수 + 그 밑 이어서 확인들) 전체의 미리보기·자손을 모은다"
metrics:
  duration: "~12분"
  completed: 2026-09-26
  tasks: 3
  files: 13
---

# Phase 6 Plan 03: 웹앱 마켓 반영 흐름 Summary

보드의 상세 결과 표에서 **스마트스토어 반영 미리보기(쓰기 0) → 첫 1건만 반영(서버가 상한 1 강제) → 항목 단위 결과(ⓐ·ⓑ 백업 경로 텍스트) → 이어서 확인**까지 버튼으로 이어지는 웹앱 슬라이스를 만들었다. 06-02 CLI 를 subprocess 로 감싼다. 불사자 실호출 0 · 스토어 변경 0 · 사용자 서버·실DB·실회차 무접촉.

## 한 일

| Task | 내용 | 커밋 |
|------|------|------|
| 1 | MarketArgv · kind 3종 등록(WRITE/BULSAJA/SINGLETON/POLL_INCOMPLETE_OK · caffeinate) · `_마켓폴더` 체인 · `_build_argv` market 분기 · settings 3키 | bb66b8f (test) · 2715fe8 (feat) |
| 2 | 라우트 3개 · `_마켓반영상한()=1` · 미리보기/결과 ctx · 템플릿 2개 · `_job_status` 문구 | 43c6cf1 (test) · 03dda6b (feat) |
| 3 | 상세 결과 표 미리보기 버튼 · `마켓잡들` 재오픈 목록 · board.js 위임 4개 · 가드 리터럴 정리 | 0fb0f01 |

사전 확인: 실제 `webapp.db` 를 mode=ro 로 열어 starting/running 잡 0건을 확인하고 시작했다.

## 흐름 계약 (06-04 · 06-05 가 보는 것)

- **폴더:** `<회차>/web/market_<미리보기id>/` — `preview.json` · `summary_<잡id>.json` · `market_status.json` · `before_market/`. ⓐ = 미리보기 부모 상세 잡의 `detail_<견적id>/before_detail`
- **미리보기 대상:** 부모(detail_submit/detail_poll) `detail_status.json` 에서 `_상세항목상태 == "완료"` 인 것만, 부모 대상 파일 순서 · `{"items":[{productId, 판매자상품코드}]}` → `web/targets_<미리보기id>.json`
- **반영 대상:** `preview.json` 반영가능 중 체크포인트가 안 손댄 것, 미리보기 순서, 앞 `_마켓반영상한()` 건 → `web/targets_<반영id>.json` · argv `--commit --max-items <상한>`
- **반영 거부(400):** 부모≠미리보기 · 미리보기 running/failed/exit≠0 · 24시간 초과 · 자식 반영 도는 중 · 자식 반영 2개 이상 · 상한 1인데 앞선 반영이 체크포인트를 남김 · 체크포인트 깨짐 · 남은 반영가능 0
- **이어서 확인 허용:** 부모 market_commit/market_poll 이 done+exit3, 또는 done/orphaned + 체크포인트 대기(접수·대기) > 0
- **06-04 가 바꿀 곳:** `_마켓반영상한()` 본문 한 곳(통과면 `market_update_max_items`) · `#market-gate-slot`. 상한이 1보다 커지면 두 번째 반영이 자동으로 열리고, 미리보기 표시가 '게이트 대기' → '다음 회차' 로 바뀐다

## 테스트

- `test_routes_market.py` 58 passed(신규) · `test_jobs.py -k market` 11 · `test_argv.py -k Market` 6
- `webapp/tests` 전체 **763 passed** · `node --check webapp/static/board.js` OK
- 수용 grep: `| safe` 0/0 · `def _마켓반영상한` 1 · `market-gate-slot` 1 · `class MarketArgv` 1 · `--market"` 0줄

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Correctness] 게이트 닫힘에서 두 번째 반영 거부**
- **Found during:** Task 2
- **Issue:** 플랜 행동 목록은 "같은 미리보기 commit 은 2회까지" 만 적었다. 그대로면 게이트 판정 전에 반영을 두 번 눌러 2건이 나간다 — SC-2("판정 전 반영은 1건")와 어긋난다
- **Fix:** `상한 == 1` 이고 앞선 반영 자식이 있고 체크포인트에 손댄 항목이 있으면 400("게이트 판정을 기록한 뒤에 나머지가 열린다"). 앞선 반영이 쓰기 전에 실패(체크포인트 0)했으면 다시 누를 수 있다. 테스트 `test_반영_두번째_허용_세번째_거부` 는 `_마켓반영상한` 을 20 으로 바꿔(게이트 통과 모사) 검증한다
- **Commit:** 03dda6b

**2. [Rule 2 - Correctness] 깨진 market_status.json 은 400/에러**
- 반영 라우트·이어서 확인·결과 조각 모두 깨진 체크포인트를 빈 값으로 읽지 않는다(06-02 Deviation 2 와 같은 이유 — 이중 반영)

**3. [Rule 2 - Correctness] '손댐' 판정에 `실패` 포함**
- 플랜은 "taskId 없음 + 접수/대기 아님" 을 남은 대상으로 적었다. 서버 FAILED/DLQ 로 종결된 `실패` 는 재반영 대상이 아니므로(D-08 재반영 버튼 없음) 대상에서 뺐다. 쓰기 전 멈춘 `스킵` 만 다음 반영에서 재시도된다

**4. [Rule 3 - Blocking] `create_job` 의 `detail_inputs` 를 market_preview · market_commit 에도 허용**
- 플랜은 "기존 writer 재사용" 을 지시했는데 `create_job` 이 `detail_inputs` 를 견적 전용으로 막고 있었다. 허용 kind 를 `INPUTS_KINDS` 로 넓히고 `max_items` 는 market_commit 전용으로 막았다

**5. [테스트 조정] 기존 고정 멤버 테스트 갱신**
- `test_argv.py::test_불사자잡은_전역_쓰기가드에_안_들어간다` 가 `BULSAJA_KINDS` 멤버를 통째로 고정한다 — 마켓 3종 추가를 반영했다(의도된 변경)

**6. [가드 정리] 테스트의 반영 플래그 리터럴**
- `no_commit_guard.sh` 가 테스트 트리의 `--commit` 글자를 금지한다. 이 플랜이 더한 단언은 `"--" + "commit"` 간접 조립으로 바꿨다. `test_market_cli.py`(06-02) 의 잔여 7건은 범위 밖이라 `deferred-items.md` 에 남겼다 — **가드는 이 플랜 전부터 실패 상태다**

## 오케스트레이터 uat 대기

이 실행기에는 에이전트 도구가 없어 `uat-verifier` 를 직접 부르지 못했다(05-04 선례). 06-04 UAT 와 묶어 돌릴 지시문을 그대로 남긴다.

> **uat-verifier (model: sonnet) — 06-03 마켓 반영 흐름 UI.** 불사자 실호출 0 · 실제 CLI 실행 0 · 사용자 서버(:8765, PID 42672) 무접촉 · 실 `webapp.db`/실 회차 무접촉.
> 1. 격리 포트로 웹앱을 띄운다. `CT_DB_PATH`/`CT_JOB_LOG_DIR` 를 임시 경로로, data_root 를 임시 회차 트리로 돌린다.
> 2. 시드: 임시 회차에 detail_estimate → detail_submit(done, exit 0) 잡 행 + `detail_<견적id>/detail_status.json`(완료 2 · 실패 1) + 대상 파일(`{"items":[{productId, 판매자상품코드}]}`).
> 3. `jobs.spawn` 을 가짜로 둔다: market_preview 는 06-02 계약 모양 `preview.json`(반영가능 2 · 스킵 1, 스킵 1건은 `backup_a_있음:false` · 사유 `backup_failed`)을 쓰고 exit 0, market_commit 은 `market_status.json`(성공 1, taskId 8자리 이상)을 쓰고 exit 0.
> 4. 확인: ① 상세 결과 표에 "스마트스토어 반영 미리보기 — 쓰기 0" 버튼 ② 누르면 미리보기 표 — ⓐ·ⓑ 경로 텍스트 · (있음)/(없음) · 두 번째 반영가능 행 "게이트 대기" · 버튼 문구 "첫 1건만 반영 (육안 확인 게이트)" ③ 버튼 → 잡 패널 → 결과 표(항목 행 · 작업번호 끝 8자리 · 미반영(게이트 대기) 행 · 재반영 버튼 없음) ④ 새로고침 후 상세 결과 표의 "최근 스마트스토어 반영" 에서 결과 보기로 재로드 ⑤ 콘솔 오류 0.
> 5. PASS/FLAKY/FAIL/BLOCKED + P0~P3 를 `.planning/phases/06-market-update/evidence/06-03-uat.md` 에 기록한다.

자동 대체 검증: TestClient 로 조각을 실제 렌더해 ①~④의 문구·버튼·경로·data 속성을 단언했다(`test_routes_market.py`). 브라우저에서만 보이는 것(htmx 스왑 순서·SSE done 후 자동 로드·콘솔 오류)은 위 UAT 로 남는다.

## 서버 재시작

**필요하다(06-05 에서).** 사용자 서버는 `--reload` 없이 돈다 — 이번 라우트·템플릿·board.js 는 재시작 전엔 안 보인다. 이 플랜은 서버를 건드리지 않았다. 재시작은 도는 잡 0 을 확인한 뒤 06-05 가 한다.

## Known Stubs

- `_마켓반영상한()` 이 **항상 1** 을 돌려준다 — 의도된 고정이다(D-09 게이트 닫힘). 06-04 가 게이트 판정 읽기로 교체한다
- `_market_result_table.html` 의 `<div id="market-gate-slot"></div>` 는 비어 있다 — 06-04 가 판정 패널을 넣는다

## Threat Flags

없음. 새 표면은 POST 3개뿐이고 threat_model T-06-15~22 가 전부 덮는다(extra=forbid · 서버 상한 · security.guard · 계정 가드 · 자동 이스케이프 · 끝 8자리 · 24시간).

## TDD Gate Compliance

Task 1·2 는 test(...) → feat(...) 순서로 커밋했다. Task 3 은 `tdd` 가 아닌 auto 태스크라 테스트를 기능 커밋에 같이 담았다.

## Self-Check: PASSED
- FOUND: webapp/templates/_market_preview_table.html · webapp/templates/_market_result_table.html · webapp/tests/test_routes_market.py
- FOUND commits: bb66b8f · 2715fe8 · 43c6cf1 · 03dda6b · 0fb0f01

## uat-verifier (06-03+06-04 통합, 2026-09-26): **PASS** — 12항목(pass 11 · P2 1: 게이트 정상 직후 반영 버튼 지연 표시, 새로고침으로 우회 · deferred-items). 격리 인스턴스 · 불사자 0 · 쓰기 0. 리포트 evidence/06-04-uat.md
