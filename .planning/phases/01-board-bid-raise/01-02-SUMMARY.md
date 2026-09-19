---
phase: 01-board-bid-raise
plan: 02
subsystem: cli-patch
tags: [naver-ads, argparse, subprocess, json, atomic-write, whitelist-projection, tdd]

# Dependency graph
requires:
  - "01-01: webapp/tests/conftest.py · fixtures/targets_broken.json · no_commit_guard.sh · .venv-web(pytest)"
provides:
  - "bids.run_bids(acct, run_dir, rows, commit=False, log=print, only_ads=None) -> dict"
  - "bids.run_revert(acct, run_dir, commit=False, log=print, only_ads=None) -> dict"
  - "plans[i]['result'] ('성공'|'실패'|'스킵') + plans[i]['error'] (commit 경로에만)"
  - "run_ads.py bids --only-ads <경로> — 대상 소재 좁히기. 파일 깨지면 exit 1"
  - "run_ads.py bids --preview-out <경로> — 계정별 plans/counts/committed 전량 JSON (원자적 쓰기)"
  - "run_ads.py accounts — [{alias, customer_id}] stdout. 시크릿 0"
  - "run_ads._load_only_ads(path) · run_ads._dump_preview(path, outputs)"
  - "webapp/tests/test_cli_patch.py — 10개 테스트 (회귀-02/03/04 · FLOW-05 · SAFE-03)"
affects: [01-05, 01-07, 01-08, 01-09]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "필터 주입구를 로직 앞이 아니라 **로직 뒤·소비 직전**에 건다 — 집계 함수의 입력을 오염시키지 않으려고"
    - "읽기 실패는 전량 폴백이 아니라 exit 1 — 돈이 나가는 명령의 기본값은 '아무것도 안 함'"
    - "화이트리스트 투영으로 시크릿 비노출을 구조로 보장(블랙리스트 금지)"
    - "테스트가 EROOM_WORKSPACE_TOML 로 data_root 를 tmp 로 옮긴다 — 실제 회차·ledger 무오염"

key-files:
  created:
    - webapp/tests/test_cli_patch.py
  modified:
    - .claude/skills/naver-ads-weekly/scripts/bids.py
    - .claude/skills/naver-ads-weekly/scripts/run_ads.py

key-decisions:
  - "only_ads 필터는 update_streaks 뒤·plan_raise 앞 단 한 줄 (OQ-1 확정, T-1-04)"
  - "dry-run plan 에는 result 키를 넣지 않는다 — 실행 안 한 걸 '성공'이라 하면 거짓말"
  - "run_revert 는 백업 파일을 읽기만 한다 — 되돌린 키를 지우지 않는다(D-13)"
  - "항목단위 결과 테스트는 seq.pop(0) 대신 소재별 응답 분기 — 500 은 4회 재시도라 순번이 터진다"
  - "프로세스 테스트는 EROOM_WORKSPACE_TOML 로 data_root 를 격리 — run_dir_of 가 폴더를 만들기 때문"

requirements-completed: [FLOW-02, FLOW-05]

# Metrics
duration: 14min
completed: 2026-09-20
---

# Phase 1 Plan 02: CLI 주입구 2개 + 읽기 전용 서브커맨드 1개 Summary

**`bids.py`·`run_ads.py` 에 `--only-ads`·`--preview-out`·`accounts` 를 뚫어, 웹앱이 판정·입찰가 계산·백업·ledger 로직을 한 줄도 재구현하지 않고 "고른 것만" 처리하고 "전량 결과"를 표로 만들 수 있게 했다 — CLI 회귀 100 tests 불변.**

## Performance

- **Duration:** 14 min
- **Started:** 2026-09-19T17:11Z (KST 2026-09-20 02:11)
- **Completed:** 2026-09-19T17:25Z (KST 2026-09-20 02:25)
- **Tasks:** 3
- **Files modified:** 3 (신규 1 · 수정 2)

## Accomplishments

- **`--only-ads` 로 대상이 좁혀지는데 `update_streaks` 는 여전히 전량을 본다.** 필터는 `run_bids` 안쪽, `update_streaks` 호출 **뒤**·`plan_raise` 리스트 컴프리헨션 **앞** 단 한 줄이다. `cmd_bids` 에 걸었으면 `zero_ids = {r["adId"] for r in rows}` 가 축소돼 나머지 소재의 연속실패 카운팅이 이번 회차에 통째로 빠지고, `_last_streak_update=today` 가 찍혀 같은 날 도는 전량 실행마저 건너뛴다. 이 한 가지를 `test_필터해도_streak_은_전량기준` 이 몽키패치로 상시 감시한다(T-1-04).
- **대상 파일이 깨지면 전량으로 번지지 않는다.** `run_ads.py bids --only-ads <깨진파일>` → stdout `--only-ads 읽기 실패 — 전량 실행으로 폴백하지 않는다: JSONDecodeError: ...` + **exit 1**. 실제 프로세스를 띄워 returncode 를 확인하는 테스트 2개(깨진 파일 · 없는 파일)가 지킨다. 5건인 줄 알았던 게 2,242건이 되는 게 이 명령의 가장 비싼 실수라, 실패 시 기본 동작을 "아무것도 안 함"으로 고정했다(T-1-05).
- **미리보기 표를 stdout 파싱 없이 만들 수 있다.** `cmd_bids` 가 `run_bids`/`run_revert` 의 리턴값을 더 이상 버리지 않고 `outputs[alias]` 에 모아 `--preview-out` 으로 쓴다. stdout 은 기존대로 10건에서 `… 외 N건` 으로 접지만 산출물은 전량이다 — 테스트가 12건을 넣어 stdout 접기(`… 외 2건`)와 산출물 12건을 동시에 단언한다(D-02).
- **실행 결과가 항목 단위로 남는다** (FLOW-05). commit 경로의 각 plan 이 `result`("성공"/"실패"/"스킵")와 `error`(사유)를 갖는다. 스킵 사유는 곧 `action`(최근인상·연속실패중단·상한도달·입찰가불명), 스냅샷 부재는 `"스냅샷에 소재 없음"`, API 실패는 `str(err)[:150]`. 로그 파싱은 쓰지 않는다.
- **`run_ads.py accounts` 로 SAFE-03 이 테스트가 아니라 구조로 보장된다.** `nvad.load_accounts()` 결과를 `{"alias", "customer_id"}` 로 **화이트리스트 투영**한다 — 자격증명 파일에 새 키가 생겨도 안 샌다. `grep "secret_key\|api_key" run_ads.py` 가 0건. 웹앱이 `~/.eroom/naver-ads.json` 을 두 번째로 갖지 않는다.
- **실데이터 스모크가 플랜 기대치와 정확히 일치했다.** `--only-ads` 1건 → `{'cy728': 0, 'cy7728': 0, 'ownway1': 1, 'pogeunae': 0}`, **0.062초, 네트워크 0**. 그 1건이 `useGroupBid: true` 에 `70→80` 이다(그룹 기본가 기준 — 웹앱이 재계산하면 50→60 이 된다. BID-03 의 정본).
- **회귀 기준선 불변.** CLI 6파일 **100 tests 전부 exit=0**(7+7+21+21+28+16). 새 인자가 전부 기본값 `None` 이라 기존 호출부(`test_bids.py:166,200,248,262` 포함)가 하나도 안 깨졌다. 실제 `~/python_work/data` 의 회차 폴더·ledger 파일 mtime 도 8/30 그대로다.

## Task Commits

1. **Task 1: `bids.py` — `only_ads` 필터 + 항목단위 result/error** (TDD) — `e79261d` (test, RED: 6개 중 5개 실패) → `5b3f873` (feat, GREEN). REFACTOR 불필요.
2. **Task 2: `run_ads.py` — `--only-ads`·`--preview-out`·`accounts`** — `dbec48d` (feat)
3. **Task 3: 프로세스 레벨 CLI 계약 테스트 4종** — `85277c5` (test)

**Plan metadata:** 아래 docs 커밋

## Files Created/Modified

- `.claude/skills/naver-ads-weekly/scripts/bids.py` (+36/-4) — `run_bids`/`run_revert` 시그니처에 `only_ads=None`(`log` 뒤, 저장소 관례), 필터 1줄, commit 루프의 `result`/`error` 4곳, 백업 병합·`try/finally` `ledger.save` 구조는 무변경
- `.claude/skills/naver-ads-weekly/scripts/run_ads.py` (+74/-5) — `cmd_accounts` · `_load_only_ads` · `_dump_preview` 신규, `cmd_bids` 의 `outputs` 수집, 서브파서 2줄 + `accounts` 파서, 디스패치 dict 1키, `import os`
- `webapp/tests/test_cli_patch.py` (신규 276줄) — 10개 테스트

### 테스트 10개가 지키는 것

| 테스트 | 겨누는 것 |
|---|---|
| `test_only_ads_none_은_전량과_같다` | 회귀-02 — 인자 생략 == `only_ads=None` |
| `test_필터해도_streak_은_전량기준` | 회귀-03 / T-1-04 — **필터 위치**의 유일한 자동 방어선 |
| `test_항목단위_결과` | FLOW-05 / T-1-15 — 성공 1·실패 1·스킵 1 + 사유 |
| `test_dry_run_은_결과를_말하지_않는다` | 실행 안 한 걸 "성공"이라 하지 않는다 |
| `test_스냅샷에_소재가_없으면_실패로_남는다` | Pitfall 7 — 스냅샷 기반 실행의 정상적 실패 |
| `test_revert_도_고른것만_되돌린다` | D-13 — 대상 좁힘 + **백업 파일 불변** |
| `test_only_ads_깨지면_실패한다` | 회귀-04 / T-1-05 — 실제 프로세스 exit 1 |
| `test_only_ads_파일이_없어도_실패한다` | 같은 위협의 다른 입구(파일 부재) |
| `test_preview_out_이_전량을_쓴다` | D-02 — stdout 10건 접기와 무관한 전량 산출 |
| `test_accounts_는_시크릿을_찍지_않는다` | SAFE-03 / T-1-03b — 화이트리스트 투영 |

## Decisions Made

- **필터 위치 = OQ-1 확정대로.** `cmd_bids` 가 아니라 `run_bids` 안쪽. 플랜이 요구한 근거 주석(Pitfall 5)을 코드에 그대로 남겼다. 이 위치를 되돌리면 테스트가 즉시 빨개진다.
- **dry-run plan 에는 `result` 키를 만들지 않는다.** 없는 키를 읽으면 `KeyError` 로 터지지, 조용히 "성공"으로 읽히지 않는다 — 화면이 미리보기를 실행 결과로 오독할 길을 막는다.
- **`run_revert` 는 백업 파일을 읽기만 한다.** 되돌린 키를 지우면 같은 회차의 다른 작업분을 되돌릴 근거가 사라지고, 중간에 죽었을 때 재시도할 원본도 함께 날아간다. docstring 에 못박았다(D-13).
- **`_load_only_ads` 는 예외를 안 잡는다.** 잡는 곳은 `cmd_bids` 한 곳이다. 함수가 스스로 삼키면 `None`(=전량)을 돌려주는 실수가 언젠가 들어온다.
- **`_dump_preview` 실패는 exit 1.** 조용히 성공으로 끝내면 화면이 "결과 0건"을 정상으로 읽는다(T-1-13).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `test_항목단위_결과` 의 `seq.pop(0)` 방식이 구조적으로 터진다**
- **Found during:** Task 1 (RED 작성)
- **Issue:** 플랜은 `(200, {})` 과 `(500, "서버 오류")` 를 `seq.pop(0)` 으로 번갈아 주라고 했다. 그런데 500 은 `apply_raise` 의 **Important 9 재시도 대상**이라 한 소재가 응답을 최대 4개 소비한다 — 순번 방식은 `IndexError` 로 터지고, 억지로 리스트를 늘리면 재시도 횟수라는 구현 세부에 테스트가 묶인다.
- **Fix:** 소재별 응답 분기(`path.endswith("/a")` → 200, 그 외 → 500)로 바꿨다. `test_bids.py:238` 의 `round1` 관례와 같은 모양이다. 이유를 테스트 주석에 남겼다.
- **Files modified:** `webapp/tests/test_cli_patch.py`
- **Verification:** 성공 1·실패 1·스킵 1 단언 통과. 재시도 4회가 그대로 돌고도 테스트가 안정적이다.
- **Committed in:** `e79261d`

**2. [Rule 2 - Missing Critical] 프로세스 테스트가 실제 데이터 루트에 폴더를 만든다**
- **Found during:** Task 3
- **Issue:** 플랜은 `--run-dir <tmp회차>` 로 실제 프로세스를 띄우라고 했다. 그런데 `run_ads.run_dir_of()` 는 `mkdir(parents=True, exist_ok=True)` 로 회차 폴더를 **만든다** — `--only-ads` 읽기 실패로 중단되기 **전에** 이미 만들어진다. 테스트를 돌릴 때마다 `~/python_work/data/naver-ads/runs/` 에 쓰레기 폴더가 쌓이고, 최악의 경우 보드가 그걸 빈 회차로 읽는다.
- **Fix:** `_격리된_데이터루트()` 헬퍼가 tmp 에 `workspace.toml` 을 쓰고 `EROOM_WORKSPACE_TOML` 환경변수로 넘긴다(`eroomlib/config.py:_toml_path` 가 보는 1순위). `data_root` 자체가 tmp 로 옮겨져 회차·ledger·백업이 전부 tmp 안에서만 생긴다.
- **Files modified:** `webapp/tests/test_cli_patch.py`
- **Verification:** 테스트 후 `ls ~/python_work/data/naver-ads/runs/` → `2026-08-29`, `2026-08-30` 만(기존 그대로). `ledger/*.json` mtime 전부 8/30 그대로.
- **Committed in:** `85277c5`

**3. [Rule 1 - Bug] `no_commit_guard.sh` 가 docstring 의 플래그 언급을 잡았다**
- **Found during:** Task 3
- **Issue:** `test_preview_out_이_전량을_쓴다` 의 docstring 에 "쓰기 플래그 없음"을 설명하려고 그 플래그 이름을 적었더니 가드가 exit 1 을 냈다.
- **Fix:** 문장을 플래그 이름 없이 다시 썼고, **왜** 이름을 안 적는지를 그 자리에 설명으로 남겼다. 가드를 고치지 않았다 — 가드의 요지가 "주석이든 코드든 글자 자체가 없어야 한다" 이고, 예외를 한 번 열면 다음 사람이 코드에도 연다.
- **Files modified:** `webapp/tests/test_cli_patch.py`
- **Verification:** `bash webapp/tests/no_commit_guard.sh` → exit 0
- **Committed in:** `85277c5`
- **Note:** 가드가 **빈 통과가 아님**이 실전에서 한 번 더 증명됐다.

### 플랜 기준 초과 (보고)

- **`<verification>` 의 "`bids.py`+`run_ads.py` 합쳐 +30줄 미만" 을 넘었다 — 실제 +114/-9.** 순수 로직은 플랜대로 20줄 미만이다(필터 1줄 · result/error 4곳 · revert 조건 1줄 · 시그니처 2곳 · 서브파서 3줄 · 디스패치 1키). 나머지는 플랜의 `<action>` 이 **명시적으로 요구한** 한국어 docstring·근거 주석(Pitfall 5 · D-12~D-14 · Pitfall 7 · T-1-05 · T-1-13 · SAFE-03)과 신규 함수 3개(`cmd_accounts`·`_load_only_ads`·`_dump_preview`)의 본문이다. 주석을 줄여 줄수를 맞추는 것은 이 저장소 관례(§S-1)와 플랜 지시를 동시에 어기는 선택이라 하지 않았다.
- **테스트를 10개 썼다** (플랜 명시 5개). VALIDATION 표가 이름을 지정한 5개는 **글자 그대로** 있고, 추가 5개는 플랜 Task 1 `<behavior>` 가 적은 동작(dry-run 에 result 없음 · 스냅샷 부재 실패 · revert 전량 불변 · 파일 부재 · accounts 투영)을 각각 덮는다.

---

**Total deviations:** 3 auto-fixed (2 bug, 1 missing-critical) + 2 보고 항목
**Impact on plan:** `<interfaces>` 계약은 한 글자도 안 바뀌었다. `run_bids`/`run_revert` 시그니처, `--only-ads`/`--preview-out`/`accounts` 동작, 산출물 스키마 전부 플랜대로다. 01-05 의 `AdsArgv` 와 01-07 의 파일 사슬이 그대로 붙는다.

## Issues Encountered

- **`--revert` 분기의 `--preview-out`.** 플랜대로 revert 분기도 `outputs[alias] = run_revert(...)` 를 모아 `_dump_preview` 를 부른다. `run_revert` 리턴은 `{"targets", "committed", "failed"}` 라 `plans` 키가 없다 — 01-09 가 이 산출물을 읽을 때 `v.get("plans", [])` 로 받아야 한다(실데이터 스모크의 집계 표현이 이미 그 모양이다).
- **`accounts` 가 자격증명 파일을 읽는다.** 파일이 없거나 깨지면 `nvad.load_accounts()` 가 `[]` 를 돌려주고 `accounts` 는 `[]` + exit 0 이다. 웹앱은 "빈 배열"을 "설정이 비었다"로 읽어야 한다 — exit code 로는 구분되지 않는다(의도된 계약).

## Known Stubs

없음. 이 플랜의 산출물은 전부 실제로 동작하고, 실데이터로 한 번 돌려 확인했다.

## Threat Flags

없음 — 새로 생긴 네트워크 표면 0개. `accounts` 서브커맨드는 자격증명 파일 → stdout 경계를 하나 만들지만, 화이트리스트 투영으로 시크릿이 그 경계를 넘지 못한다(플랜 `<threat_model>` T-1-03b 의 처분대로 mitigate 완료).

## Verification Evidence

```
CLI 회귀(기준선 불변):
  test_nvad 7 · test_reports 7 · test_ads_rules 21 · test_ledger 21 · test_bids 28 · test_prune 16
  = 100 tests, 6파일 전부 exit=0

웹앱:
  .venv-web/bin/pytest webapp/tests -q          → 27 passed (기존 17 + 신규 10)
  .venv-web/bin/pytest webapp/tests/test_cli_patch.py -x -q → 10 passed
  bash webapp/tests/no_commit_guard.sh          → exit 0

Task 2 수용 명령:
  run_ads.py accounts | (alias/customer_id 만인지 검사)  → PASS 4
  ! grep -n "secret_key\|api_key" run_ads.py             → 0건

실데이터 스모크(네트워크 0):
  echo '["nad-a001-02-000000495390006"]' > t.json
  run_ads.py bids --run-dir 2026-08-30 --only-ads t.json --preview-out p.json
  → {'cy728': 0, 'cy7728': 0, 'ownway1': 1, 'pogeunae': 0}   (플랜 기대치와 일치)
  → 0.062 total (real)
  → plans[0] = {adId: nad-...495390006, action: 인상, from: 70, to: 80, useGroupBid: True}

깨진 대상 파일:
  run_ads.py bids --only-ads targets_broken.json
  → "--only-ads 읽기 실패 — 전량 실행으로 폴백하지 않는다: JSONDecodeError: ..."  exit=1

무오염:
  ls ~/python_work/data/naver-ads/runs/   → 2026-08-29, 2026-08-30 (기존 그대로)
  ls -la ~/python_work/data/naver-ads/ledger/ → mtime 전부 Aug 30 (실제 ledger 무변경)
  git status --short → 비었음

grep only_ads bids.py → 시그니처 2 · 필터 2줄(1곳) · revert 조건 1 + docstring/주석 4
```

## User Setup Required

None — 새 의존성·외부 설정 0개. `run_ads.py` 의 기존 사용법도 그대로다(새 플래그는 전부 선택).

## Next Phase Readiness

**Wave 1 의 나머지(01-03 보안·부팅토큰)와 이후 웨이브가 이 계약 위에 바로 올라탄다.**

- `01-05` (`AdsArgv`): 조립할 argv 가 확정됐다 — `bids --run-dir <회차> --account <alias> --only-ads <경로> --preview-out <경로>`. `accounts` 서브커맨드로 alias 목록을 받으므로 웹앱에 계정을 박을 이유가 없다.
- `01-07` (미리보기): `--only-ads` 파일 하나를 미리보기·실행·되돌리기가 같이 지목하면 FLOW-02/SAFE-06 이 성립한다. 미리보기 표는 `--preview-out` 산출물의 `plans` 를 그대로 그리면 된다 — 웹앱은 입찰가를 계산하지 않는다.
- `01-08` (실행 결과 투영): `plans[i].result`/`error` 를 그대로 읽으면 FLOW-05 화면 절반이 끝난다. D-10("미리보기와 달라진 N건")은 같은 스키마의 두 산출물을 `adId` 로 대조하면 된다.
- `01-09` (되돌리기): `run_revert(only_ads=...)` 와 "백업 파일 불변"이 테스트로 못박혀 있다. 되돌리기 산출물은 `plans` 가 아니라 `targets`/`committed` 임에 유의.

**주의 하나:** 마지막 실제 회차가 아직 21일 묵었다(`stale`). Wave 4 의 수동 확인에서 `prep` 로 광고 API 자격증명 유효성부터 봐야 한다(OQ-6) — 이번 플랜은 네트워크를 한 번도 타지 않아 그걸 확인하지 못했다.

## Self-Check: PASSED

- 파일 3개 전부 FOUND (`bids.py` · `run_ads.py` · `webapp/tests/test_cli_patch.py`)
- 커밋 4개 전부 FOUND: `e79261d` · `5b3f873` · `dbec48d` · `85277c5`
- 커밋에 파일 삭제 0건 (`git diff --diff-filter=D` 전부 비었음)

---
*Phase: 01-board-bid-raise*
*Completed: 2026-09-20*
