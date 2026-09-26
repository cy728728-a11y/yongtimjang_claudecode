---
phase: 06-market-update
plan: 01
subsystem: detail-batch / webapp-argv
tags: [market-03, backup, detail_batch, argv, d-03]
requires: []
provides:
  - "detail_batch.py --backup-out (AI 접수 직전 원본 상세 백업 · 불덮음 · 실패 시 generate 0)"
  - "DetailArgv.backup_out (submit 필수)"
  - "jobs._build_argv detail_submit → <detail_dir>/before_detail"
affects: [05-06, 06-02, 06-03]
tech-stack:
  added: []
  patterns: ["O_EXCL('x') 첫 기록 보존", "백업 실패 = 접수실패(backup_failed) · generate 0 (L-03)"]
key-files:
  created: [.planning/phases/06-market-update/06-01-SUMMARY.md]
  modified:
    - .claude/skills/bulsaja-detail-page/scripts/detail_batch.py
    - webapp/argv.py
    - webapp/jobs.py
    - webapp/tests/test_detail_cli.py
    - webapp/tests/test_argv.py
    - webapp/tests/test_jobs.py
    - .planning/STATE.md
decisions:
  - "원본 백업은 _판정 이 이미 받은 workdata(dc) 를 재사용 — 추가 MCP 호출 0"
  - "백업 폴더 mkdir 의 FileExistsError 는 실패로 친다 — O_EXCL open 의 FileExistsError 만 '기존 원본 유지'"
  - "DetailArgv submit 은 backup_out 없으면 ValueError — 백업 없는 접수 경로 없음"
metrics:
  duration: "~15분"
  completed: 2026-09-26
  tasks: 2
  files: 7
---

# Phase 6 Plan 01: --backup-out 원본 상세 백업 Summary

**⚠️ 05-06 전에 사용자 서버 재시작 필요.** 서버(PID 45635, :8765, `--reload` 없음)는 옛 `DetailArgv` 를 메모리에 들고 있어서, 재시작 전에 접수하면 `--backup-out` 없이 돈다(원본 백업 유실). 이 플랜은 재시작하지 않았다 — 도는 잡 0 일 때 오케스트레이터가 재시작하고, 05-06 첫 접수 잡 argv 에 `--backup-out …/before_detail` 이 있는지 확인해야 한다(STATE.md Blockers 에 기록).

detail_batch.py 에 `--backup-out <dir>` 을 추가해 AI 상세 접수 직전 원본(renderContent + imageTranslated)을 `<dir>/<productId>.json` 6키로 떨구고, 웹앱 detail_submit 잡이 이 플래그를 `<회차>/web/detail_<견적잡id>/before_detail` 로 항상 붙이게 배선했다. 크레딧 0 · 불사자 호출 0 (가짜 MCP 오프라인 테스트만).

## 무엇을 만들었나

- **Task 1 (75280d6)** — `detail_batch.py`
  - `_판정` 이 `접수` 결과에 `dc`(이미 받은 uploadDetailContents)를 담는다. `_견적` 은 키를 골라 담으므로 estimate.json 불변(테스트로 확인).
  - `_원본백업()` — mkdir → 이미 있으면 유지 → renderContent 10자 미만이면 실패 → 직렬화 먼저 → `open(경로, "x")` 로 기록.
  - `시도()` 안 상한 검사 뒤 · `_입력접수` 직전에 호출. 실패면 `{"status": "접수실패", "사유": "backup_failed: …"}` 저장 · generate 0회.
  - `_입력모드` 가 `args.계정` 에 닉을 흘린다.
  - 테스트 6건(`-k 백업`): 파일 생성 6키 · 추가 호출 0 · 불덮음 · 실패 2종(generate 0) · 견적/poll-only/무플래그 파일 0.
- **Task 2 (33a63ed)** — `DetailArgv.backup_out`(submit 필수, 없으면 `ValueError("백업 없는 접수는 없다 …")`, estimate/poll 은 안 붙임) · `jobs._build_argv` detail_submit 에 `detail_dir / "before_detail"` · STATE.md Blockers 맨 위에 순서 계약.

## 검증

- `pytest webapp/tests` — **623 passed**
- 골든 `test_플래그없음_골든_불변` 통과, `fixtures/detail_golden_noflag.json` diff 없음
- 05-core-value PLAN 파일 diff 없음 · 펜딩 견적잡 5f5feac7 과 그 run dir 은 건드리지 않음
- 편집 전 webapp.db(ro) 조회: starting/running 잡 0건

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] 백업 폴더 자리에 파일이 있으면 백업 없이 접수되던 경로**
- **Found during:** Task 1 (GREEN)
- **Issue:** RESEARCH 예시 코드는 함수 전체를 `except FileExistsError: return True, "기존 원본 유지"` 로 감쌌다. `mkdir(exist_ok=True)` 도 경로에 일반 파일이 있으면 `FileExistsError` 를 내므로, 백업을 못 떴는데 성공으로 처리되어 generate 가 불렸다(`test_백업_실패시_generate_0회[폴더자리에_파일]` 가 잡음).
- **Fix:** `FileExistsError` 를 `open(경로, "x")` 호출에만 좁혀 잡는다. 추가로 직렬화를 open 전에 끝내 반쪽 파일이 "원본"으로 남지 않게 했다.
- **Files modified:** detail_batch.py
- **Commit:** 75280d6

**2. [Rule 3 - Blocking] 기존 테스트 `test_DetailArgv_모드별_플래그` 에 backup_out 추가**
- submit 에 backup_out 이 필수가 되어 기존 테스트가 ValueError 를 냈다 — 의도된 계약 변경이라 테스트 입력에 경로를 넣었다.

**3. [판단] MARKET-03 을 REQUIREMENTS.md 에서 완료로 표시하지 않음**
- MARKET-03 은 06-02·03·05·06 도 걸쳐 있다(ⓑ before_market · restore). 06-01 은 ⓐ 접수 직전 백업만이라 Pending 유지.

## Threat Flags

없음 — 새 표면은 plan threat_model(T-06-01~05) 범위 안이다.

## Self-Check: PASSED

- FOUND: detail_batch.py `--backup-out` · `open(경로, "x"` · `backup_failed`
- FOUND: webapp/jobs.py `before_detail` · webapp/argv.py `백업 없는 접수는 없다`
- FOUND commits: 75280d6, 33a63ed
