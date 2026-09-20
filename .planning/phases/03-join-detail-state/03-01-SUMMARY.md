---
phase: 03-join-detail-state
plan: 01
subsystem: infra
tags: [settings, fixtures, pytest, literal-guard, sqlite, bulsaja-mcp, cli-shim]

# Dependency graph
requires:
  - phase: 01-board-bid-raise
    provides: "webapp/settings.py 의 DEFAULTS+cfg() 규약 · webapp/paths.py 의 workspace.toml 리더 · 리터럴 가드 3종 · conftest 픽스처 관용구 · webapp/argv.py 의 PY_CLI"
provides:
  - "settings.DEFAULTS 의 Phase 3 설정 8키 (expected_bulsaja_nick · profile_path · profile_max_age_min · mcp_min_interval · mcp_retry_after · mcp_batch_size · index_excluded_groups · done_tags)"
  - "workspace.toml [webapp] 테이블 — 기대 불사자 닉네임과 D-18 제외 마켓번호의 유일한 자리 (per-machine, 커밋 대상 아님)"
  - "문자열 전용 리터럴 가드 2종 + 새 키의 workspace.toml 덮어쓰기 테스트"
  - "픽스처 5종: result_traps · bulsaja_groups_traps · join_traps · result_join_real(실회차 194행 익명화본) · anonymize_join.py(재생성 스크립트)"
  - "conftest 픽스처 4개 (result_traps · bulsaja_groups_traps · join_traps · result_join_real)"
  - "test_board.py 런타임_파일들에 join.py · state.py · bulsaja_index.py 선등록 (파일 생성 전 가드)"
  - "test_jobs.py 테이블 가드 {jobs, ss_index} 확장 + 예외 사유 docstring (D-20)"
  - "detail_batch.py 가 이 맥북에서 --help exit 0 (STATE-01) + test_cli_shim.py 회귀"
affects: [03-02-join, 03-03-state, 03-04-index-cli, 03-05-ss-index, 03-06-board-ui, phase-05-detail-page]

# Tech tracking
tech-stack:
  added: []   # 새 외부 패키지 0건 (T-3-05 accept 그대로)
  patterns:
    - "문자열 설정값 전용 리터럴 가드 — 숫자 가드의 금지 집합은 건드리지 않는다"
    - "파일보다 가드를 먼저 등록한다 (f.is_file() 이 없는 파일을 건너뛰므로 red 가 안 난다)"
    - "픽스처의 기대 판정(조회/기대_상태/기대_사유)은 test oracle 이지 CLI 산출물 필드가 아니다"
    - "CLI 경로 shim 은 __file__ 기준 상대 계산 (run_names.py:40-46 관용구 복사)"

key-files:
  created:
    - webapp/tests/fixtures/result_traps.json
    - webapp/tests/fixtures/bulsaja_groups_traps.json
    - webapp/tests/fixtures/join_traps.json
    - webapp/tests/fixtures/result_join_real.json
    - webapp/tests/fixtures/anonymize_join.py
    - webapp/tests/test_cli_shim.py
  modified:
    - webapp/settings.py
    - workspace.toml   # .gitignore 대상 — 커밋에 안 들어간다
    - .gitignore
    - webapp/tests/test_paths.py
    - webapp/tests/conftest.py
    - webapp/tests/test_board.py
    - webapp/tests/test_jobs.py
    - .claude/skills/bulsaja-detail-page/scripts/detail_batch.py

key-decisions:
  - "새 설정 8키를 모듈 상수로 올리지 않았다 — reload() 의 global 목록 누락이 '설정을 고쳐도 안 바뀌는' 사고를 만든다"
  - "숫자 가드의 금지 집합에 아무것도 더하지 않았다 — 50·21 같은 작은 정수를 넣으면 width: 50 같은 무관한 코드가 전부 오탐된다"
  - "join_traps 의 조회/기대_상태/기대_사유 는 기대 판정(test oracle)으로만 둔다 — CLI 가 쓰면 판정이 두 곳이 된다"
  - "조회 '미조회' 3행의 사유를 추출실패/번호없음/미조회로 분리해 픽스처에 못 박았다 — 이 페이즈 최대 오진 지점이다"
  - "result_join_real 의 mallProductId 는 익명화하지 않는다 — 스마트스토어 공개 식별자이고 D-01 조인 키다"

patterns-established:
  - "리터럴 가드 확장: 문자열 값은 전용 가드, 작은 정수는 넣지 않는다"
  - "가드 선등록: 아직 없는 런타임 파일을 미리 감시 대상에 넣는다 (T-3-02)"
  - "테이블 가드를 넓힐 때는 예외 사유를 그 테스트 docstring 에 못 박는다 (D-20 / T-3-03)"
  - "네거티브 확인: 고치기 전 상태로 되돌려 테스트가 실제 red 가 되는지 본 뒤 커밋한다"

requirements-completed: [STATE-01]

# Metrics
duration: 42min
completed: 2026-09-21
---

# Phase 3 Plan 01: Wave 0 바닥 깔기 Summary

**막혀 있던 `detail_batch.py` 가 이 맥북에서 `--help` exit 0 으로 뜨고(STATE-01), 설정 8키 + `workspace.toml [webapp]` + 함정 8종을 담은 픽스처 5종 + 리터럴/테이블 가드 3종 확장이 뒤 5개 플랜의 바닥으로 깔렸다.**

## Performance

- **Duration:** 약 42분
- **Started:** 2026-09-20T22:50:00Z
- **Completed:** 2026-09-20T23:32:00Z
- **Tasks:** 3 / 3
- **Files modified:** 14 (신규 6 · 수정 8)

## Accomplishments

- **Core Value 경로의 첫 관문이 열렸다.** `detail_batch.py` 의 윈도 경로 하드코딩 한 줄이 원인이었고, `run_names.py:40-46` 관용구 복사로 총 10줄 변경(로직 무변경)에 끝났다. `--help` 가 usage 를 찍는다.
- **ENG-08 가드가 기동 시 죽지 않게 됐다 (D-21).** `settings.cfg("expected_bulsaja_nick", required=True)` 가 값을 돌려준다. 실값은 `workspace.toml [webapp]` 에만 있고 `DEFAULTS` 는 빈 문자열이라, 값이 비면 KeyError 로 터지는 설계가 그대로 산다.
- **실회차 ③⑤ 194행 익명화본을 떴다.** `03-VALIDATION.md` 의 모수 **194 와 정확히 일치**한다. 재생성 스크립트를 저장소에 남겨 회차가 바뀌어도 다시 뜰 수 있다.
- **이 페이즈 최대 오진 지점을 픽스처에 못 박았다.** `조회 == "미조회"` 인 행 3개의 사유가 각각 `추출실패`·`번호없음`·`미조회` 로 다르다. 앞 둘은 광고 쪽 오류, 마지막은 우리가 안 본 것이다.
- **새 외부 패키지 0건.** T-3-05(accept)의 전제 — "설치 태스크가 생기면 그 순간 설계가 틀린 것" — 를 지켰다.

## Task Commits

1. **Task 1: settings 8키 + workspace.toml [webapp] + 리터럴 가드 2종** — `8f93eeb` (feat)
2. **Task 2: 픽스처 5종 + conftest 픽스처 4개 + 가드 리스트 2종 확장** — `fda6d51` (test)
3. **Task 3: detail_batch.py 윈도 경로 치환 + --help 회귀 테스트 (STATE-01)** — `4ba4613` (fix)

## Files Created/Modified

### 신규
- `webapp/tests/fixtures/result_traps.json` — 광고 ③⑤ 함정 9행. 번호 추출 포맷 3종(`판매상품_15-2_` 언더바 · `20-3 ` 공백 · `1000개_22-1_` 숫자 접두) + `zzfake이동식오피스`(번호 없음) + `판매상품_9-9_`(불사자에 없는 번호) + `판매상품_13-2_`(D-18 제외) + 같은 번호 `17-3` 를 쓰는 광고그룹 2개(다른 계정·다른 접두)
- `webapp/tests/fixtures/bulsaja_groups_traps.json` — 마켓그룹 7개. `NN번_` 접두 함정 · 하이픈 없는 `1번_zzfake곰3` · 숫자 없는 그룹 · `9-9` 일부러 부재
- `webapp/tests/fixtures/join_traps.json` — 조인 잡 산출물 스키마 + 함정 8종 (판정 순서 역전 · `bool('0')` · `false` · 정수 `1` · 기작업 태그 · 미해소 3종 분리 · 팬아웃 3건(1건 잠금) · 최상위/행 안쪽 `표시규칙`)
- `webapp/tests/fixtures/result_join_real.json` — 실회차 2026-09-20 ③⑤ **194행** 익명화본. 계정 7개 전부 `zz01`~`zz07`
- `webapp/tests/fixtures/anonymize_join.py` — 위 익명화본 재생성 스크립트 (테스트 트리 전용 도구)
- `webapp/tests/test_cli_shim.py` — STATE-01 회귀 3종. 크레딧 0 · 쓰기 0 · 네트워크 0

### 수정
- `webapp/settings.py` — `DEFAULTS` 에 Phase 3 키 8개. 각 키에 근거 주석. `reload()` 의 `global` 목록은 손대지 않았다
- `workspace.toml` — `[webapp]` 테이블 신설 (**per-machine 파일이라 커밋에 없다.** 맥북 로컬 파일에 직접 적었다)
- `.gitignore` — `webapp-profile.json` 한 줄
- `webapp/tests/test_paths.py` — 리터럴 가드 3종 추가 (`-k 리터럴` 로 3건 수집)
- `webapp/tests/conftest.py` — 픽스처 4개 + 모듈 docstring 에 "가짜 이름 원칙" 한 항목
- `webapp/tests/test_board.py` — `런타임_파일들` 에 `join.py`·`state.py`·`bulsaja_index.py` 선등록
- `webapp/tests/test_jobs.py` — 테이블 가드 `{jobs, ss_index}` 확장, 테스트명 `test_스키마는_jobs_와_ss_index_뿐이다` 로 변경, 예외 사유 docstring
- `.claude/skills/bulsaja-detail-page/scripts/detail_batch.py` — 윈도 경로 → `__file__` 기준 상대 계산, 죽은 `run_yong.py` 안내 제거 (총 10줄)

## Decisions Made

- **새 설정 8키를 모듈 상수로 올리지 않았다.** 상수를 늘리면 `reload()` 의 `global` 목록을 같이 고쳐야 하고, 그걸 빠뜨리면 테스트가 `workspace.toml` 을 갈아끼워도 값이 안 따라온다. 전부 `cfg()` 로만 읽는다. 판단을 `DEFAULTS` 위 주석에 남겼다.
- **숫자 가드의 `금지` 집합에 아무것도 더하지 않았다.** `mcp_batch_size: 50`·`mcp_retry_after: 21` 을 넣으면 `50`·`21` 두 글자가 웹앱 전체에서 금지돼 오탐이 쏟아진다. 문자열 값(`expected_bulsaja_nick`·`index_excluded_groups`)만 전용 가드로 감시한다.
- **`join_traps.json` 의 `조회`/`기대_상태`/`기대_사유` 는 기대 판정으로만 둔다.** 플랜의 `<interfaces>` 는 "CLI 는 관측만 적는다" 고 못 박았고 태스크 지시는 `조회` 필드를 요구했다. 둘을 동시에 만족시키려면 `조회` 가 **픽스처 전용 test oracle** 이어야 한다 — 그래야 판정이 웹앱 한 곳에만 산다. 픽스처 `_주석` 맨 위에 그 사실을 적었다.
- **`result_join_real.json` 의 `mallProductId` 는 익명화하지 않는다.** 스마트스토어 공개 식별자이고 D-01 의 조인 키다. 바꾸면 이 픽스처로 해상률을 재볼 수 없다. 대신 계정 alias·상품명·광고그룹의 회사명 부분을 전부 치환했고, 계정 `summary` 의 매출·광고비는 남긴 행 수로 덮었다.
- **네거티브 확인을 커밋 전에 돌렸다.** Task 3 의 두 테스트가 고치기 전 상태에서 실제로 red 가 되는지(그리고 실패 메시지에 `ModuleNotFoundError` 가 실리는지) 확인한 뒤 원복하고 커밋했다. `01-09-SUMMARY` 의 "FAIL 을 본 적 없는 검증은 검증이 아니다" 를 따랐다.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] 워크트리에 `.venv` · `.venv-web` · `workspace.toml` 이 없어 검증을 돌릴 수 없었다**
- **Found during:** Task 1 시작 직전 (환경 점검)
- **Issue:** 세 항목 모두 `.gitignore` 대상이라 git worktree 에 복사되지 않는다. 플랜의 모든 `<automated>` verify 가 `.venv-web/bin/pytest` 로 시작하는데 그 경로가 없었다.
- **Fix:** 본체 저장소의 세 항목을 워크트리 안으로 **심볼릭 링크**했다. `paths.repo_root()` 가 워크트리를 가리키는 것을 확인했고(`webapp` 패키지는 워크트리 것을 쓴다), `workspace.toml` 링크 덕분에 `[webapp]` 추가가 **본체의 per-machine 파일에 직접 반영**된다 — 워크트리가 제거돼도 남아야 하는 값이라 이게 맞다.
- **Files modified:** 없음 (링크는 `.gitignore` 대상이고 커밋되지 않았다)
- **Verification:** 링크 후 기존 스위트 199종 전량 green. `git status --short` 에 `?? .venv` · `?? .venv-web` 만 남고 커밋에는 안 들어갔다.
- **Committed in:** 없음 (런타임 환경 구성)

**2. [Rule 2 - Missing Critical] `test_cli_shim.py` 에 죽은 래퍼 안내 회귀 테스트를 추가**
- **Found during:** Task 3
- **Issue:** 플랜은 `run_yong.py` 안내를 지우라고만 했고 회귀 테스트는 요구하지 않았다. 그런데 이건 "따라 하면 실패하는 문서" 라서, 지우기만 하면 다음 사람이 다시 적을 수 있다 — 윈도 경로와 같은 부류의 재발이다.
- **Fix:** `test_죽은_래퍼_안내가_남아있지_않다` 를 추가했다. 검사 대상 문자열은 이 파일에 통째로 남기지 않으려고 런타임 조립(`"run_" + "yong.py"`)했다 — `test_argv.py:25-27` 의 관용구다.
- **Files modified:** `webapp/tests/test_cli_shim.py`
- **Verification:** 옛 상태로 되돌리면 red, 고친 상태에서 green.
- **Committed in:** `4ba4613`

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 missing critical)
**Impact on plan:** 범위 확장 없음. 1번은 검증을 돌릴 수 있게 만든 환경 구성이고, 2번은 테스트 3줄이다.

## Issues Encountered

**🔴 03-04 가 반드시 읽어야 할 것 — 저장된 `2026-09-20` 회차는 광고그룹 정리 *이전* 이름을 담고 있다.**

`result_join_real.json` 실측:

| 항목 | 값 |
|---|---|
| ③⑤ 행수 | **194** (VALIDATION 모수와 일치 ✅) |
| 고유 광고그룹 | 46 |
| **번호가 없는 그룹** | **1개 → 해당 행 57행 (전체의 29%)** |
| 고유 번호 | 44 (번호 충돌 1쌍 = `20-1` 의 `판매상품_` / 공백 접두) |

번호 없는 그룹 1개(익명화본에서 `zzfake27`)는 `03-CONTEXT.md` 가 말한 `소형이동식오피스` 이고, 행수 57 이 CONTEXT 의 "③⑤ 57행" 과 정확히 맞는다. 옛 번호 `5-3`·`7-1`·`8-1`·`9-1` 도 그대로 살아 있다.

**의미:** `03-CONTEXT.md` 의 최종 해상률 **179/194 (92%)** 는 *"2026-09-20 회차에 정리 후 이름을 입혀 재판정"* 한 값이다. 디스크의 `result.json` 은 정리 전 스냅샷이라, **이 픽스처를 그대로 태우면 179 가 안 나온다.** 03-04 는 둘 중 하나를 골라야 한다:

1. 정리 **후** 회차를 새로 뜨고 그걸 모수로 삼는다 (권장 — CONTEXT 가 "다음 회차 실질 179/179 = 100%" 라고 적은 그 회차)
2. 이 픽스처를 쓰되 기댓값을 **정리 전 기준으로 다시 계산**한다 (그 값은 179 가 아니다)

**어느 쪽이든 `179` 를 이 픽스처에 대고 단언하지 마라.** 플랜이 이미 "이 플랜에서 179 를 단언하는 테스트를 쓰지 마라" 고 막아 뒀고, 그 이유가 여기서 실측으로 확인됐다.

그리고 이건 **버그가 아니라 기능이다.** 번호 없는 그룹 1개가 57행(29%)을 미해소로 만드는 이 모습이 정확히 JOIN-02 가 화면에 띄워야 할 것이고, 실제로 그 화면이 용팀장의 광고 청소 2회를 만들어냈다.

**그 밖:** `.venv-web` 스위트에 `starlette`/`anyio` DeprecationWarning 2건이 계속 뜬다. Phase 1 부터 있던 외부 라이브러리 경고이고 우리 코드와 무관하다 — `filterwarnings = error` 를 일부러 안 넣은 이유(`pytest.ini` 주석)와 같은 판단으로 건드리지 않았다.

## Known Stubs

없다. 이 플랜의 산출물은 설정값·픽스처·테스트·경로 shim 뿐이고, 빈 값이 화면으로 흘러가는 경로를 만들지 않았다.

`webapp/join.py`·`state.py`·`bulsaja_index.py` 는 **가드 리스트에만 이름이 올라가 있고 파일은 없다.** 이건 의도된 선등록이다(T-3-02) — `test_board.py` 의 `f.is_file()` 이 건너뛰므로 red 가 나지 않고, 03-02·03-03·03-05 가 그 파일들을 만드는 순간 가드가 자동으로 작동한다.

## User Setup Required

없음 — 새 외부 서비스·패키지 0건.

**단, 본체 저장소의 `workspace.toml` 이 이번에 바뀌었다** (커밋 대상 아님, per-machine 파일):

```toml
[webapp]
expected_bulsaja_nick = "부킹"
index_excluded_groups = ["13-2"]
```

다른 PC 에서 이 저장소를 돌리면 그 PC 의 `workspace.toml` 에도 같은 블록을 넣어야 한다. 안 넣으면 `settings.cfg("expected_bulsaja_nick", required=True)` 가 KeyError 로 터진다 — 그게 설계 의도다(ENG-08).

## Next Phase Readiness

**준비된 것 (뒤 플랜이 바로 쓸 수 있다):**
- 03-02 `webapp/join.py` — `join_traps` 픽스처가 미해소 3종 분리·팬아웃·`표시규칙` 버리기를 전부 겨냥하고 있다. `result_traps` 가 번호 추출 정규식 입력 전수(포맷 3종 + 오탐 함정)를 담는다
- 03-03 `webapp/state.py` — `join_traps` 의 `uploadDetailContents` 4종이 STATE-02/03 판정 순서·`bool('0')`·정수/문자열 정규화를 고정한다
- 03-04 인덱스 CLI — `mcp_min_interval`·`mcp_retry_after`·`mcp_batch_size`·`index_excluded_groups` 가 설정에서 나온다. `bulsaja_groups_traps` 가 `NN번_` 접두 함정을 담는다
- 03-05 `ss_index` — 테이블 가드가 이미 넓혀져 있어 테이블을 만들어도 red 가 안 난다
- Phase 5 상세페이지 — `detail_batch.py` 가 이 맥북에서 뜬다. 래핑만 남았다

**주의:**
- 위 "Issues Encountered" 의 해상률 모수 문제를 03-04 가 먼저 결론 내야 한다
- `179 == 100%` 를 전제로 미해소 경로를 빼지 마라. 물갈이·신규 수집·광고 재등록으로 번호는 다시 어긋난다

## Self-Check: PASSED

**생성 파일 존재 확인** — 6/6 FOUND
`webapp/tests/fixtures/result_traps.json` · `bulsaja_groups_traps.json` · `join_traps.json` · `result_join_real.json` · `anonymize_join.py` · `webapp/tests/test_cli_shim.py`

**커밋 존재 확인** — 3/3 FOUND
`8f93eeb` · `fda6d51` · `4ba4613`

**플랜 `<verification>` 블록 전량**
- `.venv-web/bin/pytest webapp/tests -q` → **205 passed** (시작 시 199 → 신규 6)
- `.venv-web/bin/pytest webapp/tests/test_paths.py -k 리터럴 -x` → **3 passed**
- `bash webapp/tests/no_commit_guard.sh` → **OK (--commit 리터럴 0건)**
- `.venv/bin/python3 .claude/skills/bulsaja-detail-page/scripts/detail_batch.py --help` → **exit 0, usage 출력**

---
*Phase: 03-join-detail-state*
*Completed: 2026-09-21*
