---
phase: 06-market-update
plan: 02
subsystem: market-update-cli
tags: [market-01, market-02, market-03, market_update, cli, offline-tests]
requires: []
provides:
  - "market_update.py --preview / --commit / --poll-only / --tasks-snapshot / --restore-backup"
  - "market_status.json 체크포인트 · preview 문서 · ⓑ before_market 백업 계약"
  - "###MARKET### 센티널 · 종료코드 0/2/3/4/5"
affects: [06-03, 06-05]
tech-stack:
  added: []
  patterns:
    - "쓰기 0 미리보기 두 겹: confirm:true 코드 경로 부재 + 매 건 사후 upload_tasks 창 새 행 확인"
    - "확인모드 가드: mcp_settings confirmationMode ∉ {strict, balanced} → exit 2"
    - "upload_tasks 창 합치기(기본+SUCCESS+FAILED+DLQ) + taskId / 워터마크+productId 대체 매칭"
    - "깨진 체크포인트는 빈 값으로 읽지 않는다 (이중 반영 방지)"
key-files:
  created:
    - .claude/skills/bulsaja-detail-page/scripts/market_update.py
    - webapp/tests/test_market_cli.py
    - webapp/tests/fixtures/upload_tasks_real.json
    - webapp/tests/fixtures/market_targets_min.json
  modified: []
decisions:
  - "confirm:false 호출이 예외를 던지면 쓰기 전이므로 스킵(재시도 가능) — 실패(종결)로 세지 않는다"
  - "confirm:true 응답에 taskId 가 없거나 호출이 예외면 status=대기 · taskId=null — 재접수하지 않고 폴링의 워터마크 대체 매칭이 찾는다"
  - "워터마크 대체 매칭은 후보 중 가장 작은 taskId 를 쓰고, 다른 항목이 이미 가진 taskId 는 제외한다"
  - "미리보기 사후 창 확인 조회가 실패해도 P0 로 중단한다 — 쓰기 0 을 증명 못 하면 계속하지 않는다"
  - "workdata(full) 조회 실패도 backup_failed 스킵 — ⓑ 증거(상하단·그룹)가 불완전하면 반영하지 않는다"
  - "복원 미리보기 센티널: 토큰 받으면 성공 1, 못 받으면 스킵 1"
metrics:
  duration: "~30분"
  completed: 2026-09-26
  tasks: 3
  files: 4
---

# Phase 6 Plan 02: market_update.py CLI Summary

불사자 `bulsaja_market_update`(SMARTSTORE 고정)를 감싸는 새 CLI 로 미리보기(쓰기 0 두 겹 증명)·반영(상품당 2단 접수 + taskId 선저장)·이어서 확인(upload_tasks 창 매칭)·복원(detail_apply 2단 + 재반영)·작업창 스냅샷을 제공한다. 가짜 MCP 오프라인 테스트 66건으로 증명했고, 불사자 실호출 0 · 크레딧 0 · 스토어 변경 0 이다.

## Interfaces 계약 (06-03 이 이것만 보고 조립한다)

실행: `.venv/bin/python3 .claude/skills/bulsaja-detail-page/scripts/market_update.py ...`

**인자**
- 공통 필수: `--run-dir <dir>` · `--expect-nick <닉>`
- 모드(상호배타, 하나 필수 — 어기면 argparse exit 2): `--preview` | `--commit` | `--poll-only` | `--tasks-snapshot <out.json>`
- `--targets <json>`: preview/commit/poll-only 필수. 모양 `{"items":[{"productId":str,"판매자상품코드":str}]}`. 빈 items·깨진 파일·productId 없는 항목 = exit 2 (MCP 열기 전). 중복 productId 는 첫 것만
- `--detail-backup-dir <dir>`: ⓐ 폴더(`.../detail_<견적id>/before_detail`) — preview/commit 필수
- `--backup-dir <dir>`: ⓑ 폴더(`.../market_<미리보기id>/before_market`) — preview/commit/restore-commit 필수
- `--max-items N`: commit·restore-commit 필수(없거나 1 미만 = exit 2)
- `--summary-out <path>`: preview 는 미리보기 문서(없으면 `<run-dir>/preview.json`), commit/poll/restore 는 결과 요약
- `--poll-interval <초>`(기본 20) · `--max-poll-min <분>`(기본 30)
- `--restore-backup <ⓐ json>` + `--preview`|`--commit` → 복원 모드. poll-only·snapshot 과 조합 = exit 2
- `--sleep <초>`(기본 0.3) — 상품 사이 간격
- **market 인자 없음** — `--market` 을 주면 argparse exit 2 (L-07)

**종료코드**: 0 전부 종결/미리보기 완료 · 2 입력오류·확인모드 거부·P0 쓰기의심·복원 재조회 불일치 · 3 대기 미완(실패 아님) · 4 계정 불일치 · 5 `--max-items` 초과 시도(쓰기 전)

**센티널**(마지막 줄, flush=True): `###MARKET### 성공 a / 실패 f / 스킵 s / 대기 p / 전체 t` — preview 에선 성공 = 반영가능 수, 대기 = 0. 가드 거부·예외 때도 찍힌다.

**파일**
- preview 문서: `{"모드":"preview","계정","확인모드","워터마크","생성시각","items":[{"productId","판매자상품코드","판정":"반영가능|스킵|실패","사유","backup_a","backup_a_있음","backup_b","채널상품번호","상단이미지","하단이미지","상하단날짜","마켓그룹","미리보기요약"}],"집계":{"반영가능","스킵","실패","전체"}}` (+ P0 중단 시 `"중단"`). 토큰·표시규칙 저장 안 함
- 체크포인트 `<run-dir>/market_status.json`: `{"워터마크": str|null, "items": {productId: {"판매자상품코드","status":"접수|성공|실패|스킵|대기","taskId","사유","backup_a","backup_b","접수시각","확정시각"}}}` — commit·poll·restore 공유, 워터마크는 첫 commit 에서만 기록
- commit/poll/restore 요약: `{"모드":"commit|poll|restore","계정","max_items","집계":{"성공","실패","스킵","대기","전체"},"items":[{productId, ...체크포인트 항목}],"종료코드","생성시각"}` — restore 는 `복원원본`·`비고`·`복원후_aiImageGenerated` 추가. 체크포인트에 없는 대상(상한·중단)은 `스킵 · 미처리(중단·상한)` 로 집계
- ⓑ `<backup-dir>/<productId>.json`: `productId·판매자상품코드·조회시각·계정·renderContent·imageTranslated` + `상단이미지·하단이미지·마켓그룹` (실행 시점 증거, 덮어씀)
- 복원 미리보기: `<run-dir>/before_restore_<pid>.json`(호출 전 현재 상태 6키) · `<run-dir>/restore_preview.json`(`productId·판매자상품코드·토큰받음·응답요약·전후동일·사유`)
- 스냅샷: `{"계정","확인모드","생성시각","최대taskId","기본창행수","PENDING행수","PROCESSING행수","기본창":[{taskId,productId,상태,작업,마켓}],"work_progress_마켓작업"}`
- 스킵 사유 어휘(접두): `미업로드` · `AI상세없음` · `backup_failed` · `이미진행중` · `미리보기 호출 실패`. 체크포인트 대기 사유: `접수 응답 유실` · `응답에 taskId 없음`

## 한 일

| Task | 내용 | 커밋 |
|------|------|------|
| 1 | 가짜 불사자 판 하네스 + 픽스처(30건 창) · 미리보기 경로 | f27c3a5 (test) · 171bf26 (feat) |
| 2 | commit(상한 exit 5 · 2단 새토큰 · 선저장 · 재접수 0) + poll-only(창 매칭 · exit 3) | acbee4d (test) · c00e0e7 (feat) |
| 3 | 복원(--restore-backup) + 작업창 스냅샷(--tasks-snapshot) | 1ba8cc0 (test) · 41cbba7 (feat) |

테스트: `test_market_cli.py` 66 passed · `webapp/tests` 전체 689 passed. `.venv/bin/python3 market_update.py --help` exit 0.

가짜 MCP 는 시나리오 밖 도구 호출을 즉시 실패시키고, 기본 판은 정상 2단 프로토콜(confirm:true 는 발급 토큰이 맞을 때만 창에 새 행)이다. 그래서 예상 밖 쓰기, 토큰 재사용, `taskIds` 필터 사용이 테스트에서 걸린다.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] 테스트 식별자에 ⓐ/ⓑ 사용 → SyntaxError**
- **발견:** Task 1 RED 커밋(f27c3a5) 직후
- **문제:** 파이썬 식별자에 원문자(U+24D0)는 쓸 수 없다. 그래서 RED 커밋이 "실패 테스트"가 아니라 수집 오류였다
- **수정:** `원본쓰기`·`test_백업_원본없으면_…`·`test_백업_반영전_…` 로 이름을 바꿨다(171bf26 에 포함). 문자열·주석 안의 ⓐ/ⓑ 는 그대로 뒀다

**2. [Rule 2 - Correctness] 깨진 체크포인트 거부**
- 플랜에 없던 규칙이다. `load_json(default)` 모양이면 깨진 `market_status.json` 을 빈 값으로 읽는다. 그러면 taskId 를 가진 상품을 다시 접수한다(T-06-08 이중 반영). 그래서 commit·poll·restore 가 exit 2 로 거부하게 했다. poll-only 는 체크포인트가 없어도 exit 2 다. 테스트 3건을 더했다(c00e0e7)

**3. [Rule 2 - Correctness] 미리보기 사후 창 조회 실패 = P0 중단**
- 플랜은 "새 행이 생기면 P0" 까지만 정했다. 그런데 사후 조회가 실패하면 쓰기 0 을 증명할 수 없어서, 그 경우도 중단하게 했다

**4. [테스트 조정] test_이어서_poll_only_계정가드**
- 체크포인트가 없는 상태에서는 입력 검증(exit 2)이 계정 확인보다 먼저 걸린다. 테스트에 체크포인트를 미리 깔아 계정 가드(exit 4)를 따로 검증하게 했다

## Known Stubs

없음. 미리보기 표 컬럼(`미리보기요약`)은 confirm:false 응답의 sanitize 문자열 200자다. 06-05 라이브 스모크가 응답 원문을 박제한 뒤 컬럼을 확정한다(RESEARCH Open Question 1, 의도된 보류).

## Threat Flags

없음. 새 네트워크 표면이 없고, 불사자 MCP 경계는 threat_model T-06-06~14 가 전부 덮는다.

## TDD Gate Compliance

세 태스크 모두 test(...) → feat(...) 순서로 커밋했다. Task 1 의 RED 커밋은 수집 오류(SyntaxError)였고, 다음 GREEN 커밋에서 바로잡았다(Deviation 1).

## Self-Check: PASSED
- FOUND: .claude/skills/bulsaja-detail-page/scripts/market_update.py · webapp/tests/test_market_cli.py · fixtures 2개
- FOUND commits: f27c3a5 · 171bf26 · acbee4d · c00e0e7 · 1ba8cc0 · 41cbba7
