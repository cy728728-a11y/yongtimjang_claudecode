---
phase: 07-thumb-coupang
plan: 02
subsystem: bulsaja-thumbnail CLI / 웹 견적 러너
tags: [thumb-02, thumb-03, d-03, d-04, d-05, d-06, d-07, l-02, l-05, golden]
requires: []
provides:
  - "run_thumbs.py prep --estimate-out · --only-pending · --expect-nick"
  - "run_thumbs.py apply --generate --max-credits (누적 검사 exit 5) · apply --commit --summary-out"
  - "thumb_web.py estimate (그룹별 prep subprocess → summary.json · ###THUMB###)"
  - "SKILL.md '웹 승인 인계' 절 (web_approval.json → --max-credits)"
affects: [07-04]
tech-stack:
  added: []
  patterns: ["무플래그 골든을 CLI 수정 전 커밋에 고정", "estimate-out 은 finally 에서 원자 쓰기 — 어느 종료 경로든 파일이 남는다", "러너는 CLI 를 import 하지 않고 subprocess 로만"]
key-files:
  created:
    - .claude/skills/bulsaja-thumbnail/scripts/thumb_web.py
    - .claude/skills/bulsaja-thumbnail/scripts/test_thumb_web.py
    - .claude/skills/bulsaja-thumbnail/scripts/fixtures/thumb_golden_noflag.json
  modified:
    - .claude/skills/bulsaja-thumbnail/scripts/run_thumbs.py
    - .claude/skills/bulsaja-thumbnail/SKILL.md
decisions:
  - "prep 견적의 '대상' = 원본404 삭제대상을 뺀 실제 생성 상품 — 예상크레딧 = 대상×5, 최대 = ×MAX_REGEN(2)"
  - "누적 지출 = Σ재생성횟수×5 + (생성본 없이 taskId 만 남은 건)×5 — recover 가 회수하면 taskId 가 지워져 이중 계산 없음"
  - "--only-pending 에서 현황판에 행이 없는 pid 는 '(현황판 없음)' 값으로 제외 보고"
  - "summary-out 은 생성실패(held 에 안 드는) 건도 '보류(생성실패)' 로 싣고, 기존대표유지 목록을 추가 키로 싣는다"
  - "러너는 자식에 --group-name=<그룹명> (= 붙임) 으로 넘긴다 — 그룹명이 '-' 로 시작해도 플래그로 안 읽힌다"
metrics:
  duration: "~30분"
  completed: 2026-09-29
  tasks: 3
  files: 5
---

# Phase 7 Plan 02: 썸네일 CLI 주입구 + 견적 러너 Summary

썸네일 CLI(`run_thumbs.py`)에 무플래그 불변 주입구 5개를 달고, 웹 견적 잡이 부를 러너 `thumb_web.py estimate` 와 Claude 세션 인계 절(SKILL.md)을 붙였다. 견적 숫자(K·M·A·D·E·예상·최대)는 prep 산출 파일에서만 나오고(L-02), 크레딧 지출은 `--max-credits` 누적 검사로 웹 승인액에 묶였다(D-07). 크레딧 0 · 불사자/시트 접속 0 · 오프라인 테스트만.

## 무엇을 만들었나

- **Task 1 (31e4e3a)** — CLI 를 고치기 전에 무플래그 골든 고정. 상품 5개(미가공2·백필1·정합1·조회실패1) + 현황판 완료 1건으로 `prep --ids`·`prep`(pending) 산출 JSON 전부·현황판 호출·stdout, `apply --generate` 의 `_guard_credits → _generate` 순서를 `fixtures/thumb_golden_noflag.json` 에 저장(tmp·저장소 경로 정규화). `THUMB_GOLDEN_WRITE=1` 일 때만 재생성.
- **Task 2 (a771492 RED → 95b2f73 GREEN)** — `cmd_prep` 를 얇은 래퍼 + `_cmd_prep(args, est)` 로 갈랐다. 플래그가 없으면 `est=None` 으로 종전 본체 그대로. `--estimate-out` 은 finally 에서 `_dump_atomic` — 0건 조기반환·조회실패 중단·예외(오류 필드 기록)에서도 파일이 남는다. `--only-pending` 은 ids ∩ `matrix.pending`, 빠진 건 `{pid: 현황판값}`. `--expect-nick` 은 `_resolve_sheet`·`matrix.read` 보다 먼저 프로필 닉 비교, 불일치·조회실패 exit 4. `--max-credits` 는 `_guard_credits` 직전 `_guard_approval` — `generate_plan` 으로 이번 계획, `_spent_credits` 로 누적, 초과면 stderr `승인 상한 초과 …` 후 exit 5. `--summary-out` 은 `###COMMIT###` 줄 직전에 `{완료, 보류, 기존대표유지}` 원자 쓰기.
- **Task 3 (e257046 RED → cf9f1ae GREEN)** — `thumb_web.py estimate`: inputs 검증(깨짐·그룹0·빈 pid 목록·플래그 모양 pid → exit 2), 그룹마다 `_그룹폴더` 정규화 하위 폴더에서 `run_thumbs.py prep` subprocess, `###GROUP###` 줄, 자식 4 면 summary(계정불일치) 쓰고 즉시 exit 4, 실패 그룹 격리, 성공 그룹만 합산(곱셈 없음), summary.json 원자 쓰기, 마지막 줄 `###THUMB###`. SKILL.md 에 `## 웹 승인 인계 (관제탑, 2026-09-29)` 절 — web_approval.json 선독, 계정 확인, ids 만, 매 `apply --generate` 에 `--sheet <시트id> --max-credits <승인상한크레딧>`, `--commit --summary-out`, exit 5 는 멈추고 보고, 타임아웃·429 는 recover, 마켓 반영은 범위 밖.

## 검증

- `.venv/bin/python3 -m pytest -q .claude/skills/bulsaja-thumbnail/scripts/` → **235 passed**(기준선 205 + 신규 30), 골든 green(재생성 플래그 없이)
- `.venv-web/bin/pytest webapp/tests` → 867 passed (회귀 없음)
- acceptance grep: 주입구 플래그 10회 · `sys.exit(5)` 1 · 러너의 run_thumbs import 0 · `###THUMB###` 있음 · SKILL.md `--max-credits`·`web_approval.json`·`웹 승인 인계` 있음
- 사용자 서버(:8765)·webapp.db·실제 run-dir 무접촉

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - 보안] 자식 argv 에 그룹명을 `--group-name=<이름>` 으로 붙여 넘김**
- **Found during:** Task 3
- **Issue:** 계획은 `--group-name <그룹명>` 두 인자. 그룹명이 `-` 로 시작하면 자식 argparse 가 값이 아니라 옵션으로 읽는다(리스트 argv 라도 파서는 거친다 — argv.PlainArg 와 같은 이유).
- **Fix:** `=` 로 붙인 한 인자. 같은 이유로 pid 가 `-` 로 시작하거나 공백을 담으면 inputs 오류(exit 2).
- **Files modified:** thumb_web.py · test_thumb_web.py
- **Commit:** cf9f1ae

**2. [Rule 2] 신규 계약 파일은 원자 쓰기 헬퍼 `_dump_atomic` 추가**
- **Found during:** Task 2
- **Issue:** 계획은 "_dump 로 원자 쓰기" 인데 기존 `_dump` 는 원자 쓰기가 아니다. `_dump` 를 바꾸면 무플래그 경로도 바뀐다.
- **Fix:** estimate-out·summary-out 전용 `_dump_atomic`(tmp + os.replace). 기존 `_dump` 는 그대로.
- **Commit:** 95b2f73

**3. [Rule 2] summary-out 에 생성실패건·기존대표유지 추가**
- **Issue:** `_commit` 의 `held` 에는 생성 실패건(생성본 없음)이 안 들어가 웹에서 사라진다.
- **Fix:** `보류` 에 `보류(생성실패)` 로 합치고 `기존대표유지` 키를 덧붙임(`완료`·`보류` 계약은 그대로).
- **Commit:** 95b2f73

## TDD Gate Compliance

Task 2: test(a771492) → feat(95b2f73). Task 3: test(e257046) → feat(cf9f1ae). Task 3 은 러너 초안을 먼저 쓴 뒤 파일을 잠시 치운 상태에서 테스트가 실패(9 failed)함을 확인하고 RED 를 커밋했다.

## 요구사항 체크

THUMB-02·THUMB-03 은 **체크하지 않았다** — CLI·러너 쪽만 끝났고 웹 견적 화면·승인 파일(07-04)이 남았다. 07-04 완료 때 체크한다.

## Known Stubs

없음.

## Self-Check: PASSED
