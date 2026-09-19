---
phase: 01-board-bid-raise
plan: 01
subsystem: testing
tags: [pytest, fastapi, uvicorn, jinja2, sse-starlette, htmx, tabulator, pico-css, tomllib, uv]

# Dependency graph
requires: []
provides:
  - ".venv-web (py3.12) — 웹앱 전용 가상환경. CLI .venv 와 의존성이 겹치지 않는다"
  - "webapp/pytest.ini + webapp/__init__.py + webapp/tests/__init__.py — `webapp.*` 모듈 경로 성립"
  - "webapp/paths.py — repo_root/data_root/ads_root/runs_root/scan_run_dirs/run_dir_path/freshness"
  - "webapp/settings.py — DEFAULTS + workspace.toml [webapp] 병합, cfg(required=True), PORT/PER_ACCOUNT_LIMIT/STALE_DAYS/POLL_INTERVAL"
  - "webapp/tests/conftest.py — tmp_run_dir · fake_result_json · synthetic_job · client 픽스처"
  - "webapp/tests/fixtures/ — result_min.json(5계정 × 6규칙) · targets_one.json · targets_broken.json · synthetic_job.py"
  - "webapp/tests/no_commit_guard.sh — 테스트 트리에 --commit 리터럴 0건 증명"
  - "webapp/static/vendor/ — htmx 2.0.10 · htmx-ext-sse 2.2.4 · Tabulator 6.5.3(js/css) · Pico 2.1.1"
affects: [01-02, 01-03, 01-04, 01-05, 01-06, 01-07, 01-08, 01-09]

# Tech tracking
tech-stack:
  added: [fastapi==0.141.1, uvicorn==0.53.0, jinja2==3.1.6, sse-starlette==3.4.11, pytest==9.1.1, starlette==1.6.0, pydantic==2.13.5]
  patterns:
    - "subprocess 경계로 CLI(.venv)와 웹앱(.venv-web) 의존성 완전 분리"
    - "경로 화이트리스트 관문(run_dir_path) — 사용자 입력으로 Path 를 조합하지 않는다"
    - "숫자 상수는 settings.py DEFAULTS 한 곳. 다른 파일 리터럴 금지를 테스트가 상시 감시"
    - "정적파일 vendoring(curl) — npm 미사용, 런타임 CDN 의존 0"

key-files:
  created:
    - webapp/paths.py
    - webapp/settings.py
    - webapp/pytest.ini
    - webapp/tests/conftest.py
    - webapp/tests/test_paths.py
    - webapp/tests/no_commit_guard.sh
    - webapp/tests/fixtures/result_min.json
    - webapp/tests/fixtures/targets_one.json
    - webapp/tests/fixtures/targets_broken.json
    - webapp/tests/fixtures/synthetic_job.py
    - webapp/static/vendor/htmx-2.0.10.min.js
    - webapp/static/vendor/htmx-ext-sse-2.2.4.js
    - webapp/static/vendor/tabulator-6.5.3.min.js
    - webapp/static/vendor/tabulator-6.5.3.min.css
    - webapp/static/vendor/pico-2.1.1.min.css
  modified:
    - .gitignore

key-decisions:
  - "prep_summary.json 의 실데이터는 계정 alias 로 한 겹 중첩돼 있다 — freshness() 가 평평한 모양과 중첩 모양을 모두 읽는다"
  - "paths.read_workspace_toml() 은 파일 부재에는 {} 를, 파싱 실패에는 RuntimeError 를 낸다. data_root() 만 그 실패를 삼킨다(폴백이 돈으로 이어지지 않으므로)"
  - "settings.reload() 를 노출해 모듈 상수를 재계산 가능하게 했다 — 테스트가 workspace.toml 을 갈아끼운 뒤 원복할 수 있다"
  - "no_commit_guard.sh 는 자기 자신을 제외하고 webapp/tests 전체를 grep 한다. 빈 통과가 아님을 프로브로 확인했다"
  - "1500/8765 리터럴 금지를 문서가 아니라 테스트(test_상한_숫자가_settings_밖에_리터럴로_박혀있지_않다)로 강제한다"

patterns-established:
  - "한국어 테스트 이름: test_모르는_회차이름은_경로가_되지_않는다 (저장소 CLI 테스트 관례 계승)"
  - "tmp_run_dir 은 runs/<회차> 2단 구조를 반드시 만든다 — bids.py:130 의 run_dir.parent.parent/ledger 규약 때문"
  - "합성 잡은 flush=True 를 쓰지 않는다 — PYTHONUNBUFFERED 주입을 거짓 통과시키지 않기 위해"

requirements-completed: [BOARD-02, SAFE-03]

# Metrics
duration: 8min
completed: 2026-09-20
---

# Phase 1 Plan 01: 테스트 기반 + 경로·설정 규약 Summary

**`.venv-web`(fastapi 0.141.1 / pytest 9.1.1)과 `webapp/paths.py`·`settings.py` 를 세워, 이후 8개 플랜이 15초 안에 돌려보고 고칠 수 있는 검증 기반을 만들었다 — 가짜 5번째 계정 `zzfake` 픽스처와 `--commit` 리터럴 가드 포함.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-09-19T17:08:25Z (KST 2026-09-20 02:08)
- **Completed:** 2026-09-19T17:16:40Z (KST 2026-09-20 02:16)
- **Tasks:** 3
- **Files modified:** 19 (신규 18 · 수정 1)

## Accomplishments

- **웹앱 테스트가 실제로 돈다.** `.venv-web/bin/pytest webapp/tests -q` → 17 tests green, 약 0.3초. CLI 회귀 기준선 100 tests 는 손대지 않았고 여전히 전부 exit=0.
- **경로를 코드에 박지 않는 규약이 섰다.** `paths.data_root()` 가 `workspace.toml [paths] data_root` 를 읽어 이 맥북의 `/Users/choiyongsmacbook/python_work/data` 를 돌려준다. `eroomlib` 는 import 하지 않고 stdlib `tomllib` 로 같은 결과를 낸다(`sys.path.insert` 가 stdlib 를 가리는 문제 회피).
- **경로 조작 관문이 생겼다** (T-1-11). `run_dir_path("../../etc")` → `ValueError: 모르는 회차다`. 블랙리스트가 아니라 `scan_run_dirs()` 화이트리스트 통과분만 Path 가 된다. 이후 모든 플랜이 이 함수를 유일한 관문으로 쓴다.
- **D-16 의 위험이 실측으로 확인됐다.** 실제 회차에 `freshness()` 를 돌리니 `{"run_dir":"2026-08-30","age_days":21,"window7":["2026-08-22","2026-08-28"],"stale":true}`. 회차명(08-30)과 실제 통계기간(08-22~08-28)이 8일 어긋나 있어, 둘을 같이 보여줘야 한다는 근거가 숫자로 나왔다.
- **BOARD-02 를 진짜로 검증하는 픽스처.** `result_min.json` 에 설정에 없는 가짜 계정 `zzfake` 를 넣었다 — 어느 코드든 계정 alias 를 리터럴로 박는 순간 이 계정이 화면에서 사라져 테스트가 깨진다.
- **광고비 사고 방지선이 기계로 증명된다** (SAFE-03 / T-1-SC2). `no_commit_guard.sh` 가 `webapp/tests/` 에 `--commit` 리터럴이 0건임을 확인한다. 프로브 파일을 넣어 exit 1 이 나오는 것까지 확인해 "빈 통과"가 아님을 검증했다.
- **npm 이 저장소에 들어오지 않았다.** 정적파일 5개를 `curl` 로 `webapp/static/vendor/` 에 고정했고 `node_modules/`·`package*.json` 은 0건 + `.gitignore` 로 차단.

## Task Commits

1. **Task 1: `.venv-web` · pytest 설정 · .gitignore · 프론트 vendoring** — `97afb8b` (chore)
2. **Task 2: `webapp/paths.py` · `webapp/settings.py`** (TDD) — `8a73ebe` (test, RED) → `4121a24` (feat, GREEN). REFACTOR 불필요.
3. **Task 3: conftest + 픽스처 4종** — `70d8cd2` (test)

**Plan metadata:** 아래 docs 커밋

## Files Created/Modified

- `webapp/paths.py` — 경로 규약 한 곳. `repo_root()`(`.claude` while-loop) · `read_workspace_toml()` · `data_root()` · `ads_root()` · `runs_root()` · `scan_run_dirs()` · `run_dir_path()` · `freshness()`
- `webapp/settings.py` — `DEFAULTS`(port 8765 · per_account_limit 1500 · stale_days 8 · poll_interval 0.4 · job_log_dir · db_path) + `workspace.toml [webapp]` 얕은 병합 · `cfg(dotted, default, required)` · `reload()`
- `webapp/pytest.ini` — `testpaths` 를 비워 두고 저장소 루트에서 경로를 명시해 돈다
- `webapp/tests/test_paths.py` — 17개 테스트. behavior 8항목 + 폴백·중첩 summary·required 가드·리터럴 감시
- `webapp/tests/conftest.py` — `tmp_run_dir` · `fake_result_json` · `synthetic_job` · `client`
- `webapp/tests/fixtures/result_min.json` — 5계정 × 6규칙. ①·⑥ 행은 정확히 7필드
- `webapp/tests/fixtures/targets_one.json` / `targets_broken.json` — `--only-ads` 정상 / 손상 경로
- `webapp/tests/fixtures/synthetic_job.py` — 합성 잡 (줄수·지연·종료코드 argv)
- `webapp/tests/no_commit_guard.sh` — `--commit` 리터럴 가드
- `webapp/static/vendor/*` — htmx 2.0.10 · htmx-ext-sse 2.2.4 · tabulator 6.5.3 js/css · pico 2.1.1
- `.gitignore` — `.venv-web/` · `webapp.db*` · `webapp-logs/` · `package.json` · `package-lock.json` 추가

### 픽스처에 심어 둔 함정 4종 (전부 검증 스크립트로 확인)

| 함정 | 위치 | 겨누는 것 |
|---|---|---|
| (a) `useGroupBid: true`, `bid=groupBid=70` | `ownway1` ①, `nad-...495390006` | BID-03 — 웹앱이 입찰가를 재계산하면 70→80 이 아니라 50→60 이 된다 |
| (b) `useGroupBid: false`, `bid: 130` | `ownway1` ①, `nad-...495390007` | 비교군 |
| (c) 같은 `adId` 가 ②·③에 동시에 | `nad-...502308153` | PATTERNS §C-2 지표 중복 계상 |
| (d) 같은 `mallProductId` 에 ① 2개 + ③ 1개 | `12610054809` | D-05 접기 · D-06 "이 버튼이 N건" 의 N |

## Decisions Made

- **`freshness()` 가 `prep_summary.json` 의 두 모양을 모두 읽는다.** 플랜은 평평한 `{"window7": [...]}` 를 가정했는데, 실데이터는 `{"cy728": {..., "window7": [...]}}` 로 alias 한 겹이 더 있다. `--account` 로 나눠 돌려도 통계기간은 같으므로 처음 찾은 것을 쓴다.
- **`read_workspace_toml()` 의 실패 처리를 둘로 갈랐다.** 파일 부재 → `{}`, 파싱 실패 → `RuntimeError`. `data_root()` 만 그 예외를 삼킨다(플랜 §S-2: 이 폴백은 돈으로 이어지지 않는다). `settings.load()` 는 삼키지 않는다 — 상한 1500 이 조용히 사라지면 D-08 가드가 있는 척만 하게 된다(T-1-12).
- **`settings.reload()` 를 공개 API 로 뒀다.** 모듈 상수는 import 시점에 굳는데, 테스트가 `workspace.toml` 을 갈아끼운 뒤 원복할 길이 필요했다.
- **D-08 리터럴 금지를 테스트로 강제했다.** 문서 규칙은 Wave 1~7 이 파일을 더하면 무너진다. `test_상한_숫자가_settings_밖에_리터럴로_박혀있지_않다` 가 `webapp/**/*.py|html|js` 를 상시 훑는다(`settings.py`·`tests/`·`vendor/` 제외).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `no_commit_guard.sh` 의 grep 옵션 순서 — 자기 자신을 못 걸러 항상 exit 1**
- **Found during:** Task 1
- **Issue:** `grep -rn -- '--commit' "$HERE" --exclude=...` 로 썼는데, `--` 뒤의 `--exclude` 는 옵션이 아니라 **파일 이름**으로 읽힌다. 가드가 자기 설명 주석을 위반으로 잡아 무조건 실패했다.
- **Fix:** 옵션을 `--` 앞으로 옮기고 패턴을 `-e '--commit'` 으로 줬다. 이유를 스크립트 주석에 남겼다.
- **Files modified:** `webapp/tests/no_commit_guard.sh`
- **Verification:** 정상 시 exit 0. `_guardprobe.py` 에 위반을 심어 exit 1 + 해당 줄 출력 확인 후 제거 — 빈 통과가 아님을 증명했다.
- **Committed in:** `97afb8b`

**2. [Rule 1 - Bug] `freshness()` 가 실제 `prep_summary.json` 에서 통계기간을 못 읽음**
- **Found during:** Task 2
- **Issue:** 플랜/픽스처는 평평한 `{"window7": [...]}` 를 가정했으나 실데이터는 계정 alias 로 한 겹 중첩돼 있다. 그대로 짰으면 실화면에서 통계기간이 항상 빈칸으로 뜨고 D-16 이 반쪽만 산다.
- **Fix:** `_windows_of()` 가 평평한 모양과 중첩 모양을 모두 처리한다.
- **Files modified:** `webapp/paths.py`, `webapp/tests/test_paths.py`
- **Verification:** `test_실제_prep_summary_모양_계정별_중첩도_읽는다` 통과 + 실제 회차 `2026-08-30` 에서 `window7: ["2026-08-22","2026-08-28"]` 확인
- **Committed in:** `8a73ebe`(테스트) / `4121a24`(구현)

**3. [Rule 2 - Missing Critical] D-08 리터럴 금지를 감시하는 테스트 추가**
- **Found during:** Task 2
- **Issue:** 플랜의 done 기준은 `grep -rn "1500\|8765" webapp/` 이 `settings.py` 밖에서 0건인 것이었다. 지금 한 번 확인해도 Wave 1~7 이 파일을 더하면 조용히 무너진다 — 상한이 설정으로 조정 불가해지면 D-08 가드가 무력화된다.
- **Fix:** `test_상한_숫자가_settings_밖에_리터럴로_박혀있지_않다` 를 추가해 `webapp/**` 를 매 실행 훑게 했다.
- **Files modified:** `webapp/tests/test_paths.py`
- **Verification:** 현재 통과. `grep -rn "1500\|8765" webapp/ --include=*.py --include=*.html | grep -v /tests/` → `settings.py` DEFAULTS 2줄만.
- **Committed in:** `8a73ebe` / `4121a24`
- **Note:** 이 테스트 파일 자체에는 `1500` 리터럴이 있다(기본값을 못박는 테스트). 플랜 done 기준의 `webapp/` 범위를 **비테스트 코드**로 해석했다 — 리터럴 금지의 목적은 "설정을 고쳐도 동작이 안 바뀌는 것"을 막는 것이고, 테스트는 그 위험이 아니라 그 규칙의 집행자다.

**4. [Rule 2 - Missing Critical] 합성 잡에 종료코드 argv 추가**
- **Found during:** Task 3
- **Issue:** 플랜은 줄수·지연만 받게 했다. 잡 엔진은 **실패한 자식**(non-zero exit + stderr)도 다뤄야 하는데 그걸 재현할 대역이 없었다.
- **Fix:** 세 번째 argv 로 종료코드를 받고, 0 이 아니면 stderr 에 사유를 찍고 그 코드로 끝난다.
- **Files modified:** `webapp/tests/fixtures/synthetic_job.py`, `webapp/tests/conftest.py`(`synthetic_job(rc=...)`)
- **Verification:** `synthetic_job.py 4 0.05` 정상 완주 확인. Wave 4(01-06)가 실패 경로에 쓴다.
- **Committed in:** `70d8cd2`

---

**Total deviations:** 4 auto-fixed (2 bug, 2 missing-critical)
**Impact on plan:** 전부 정확성·안전 요구다. 인터페이스 계약(`<interfaces>` 시그니처 7+4개)은 하나도 안 바뀌었고, 추가된 것은 `read_workspace_toml()`·`settings.reload()`·`synthetic_job(rc=)` 뿐이다. 스코프 확장 없음.

## Issues Encountered

- **순환 import 위험** — `settings` 가 `paths.read_workspace_toml()` 을 쓰고 `paths.freshness()` 가 `settings.STALE_DAYS` 를 쓴다. `freshness()` 안에서만 `from webapp import settings` 로 지연 import 해 모듈 로드 시점 순환을 끊었다. 부작용으로 `monkeypatch.setattr(settings, "STALE_DAYS", N)` 이 그대로 먹는다(테스트에 유리).
- **테스트 간 전역 오염** — `settings` 는 모듈 캐시를 쓴다. 자동 픽스처 `_설정원복` 이 `monkeypatch.undo()` → `settings.reload()` 순서로 정리해 실행 순서에 따라 결과가 달라지지 않게 했다.

## Known Stubs

- `webapp/tests/conftest.py` 의 `client` 픽스처는 지금 부르면 `ImportError` 다 — `webapp/main.py` 와 부팅 토큰을 **Plan 01-03 이 만든다**. `pytest.importorskip` 으로 덮지 않았다(덮으면 Wave 1 이 라우트를 못 만들어도 초록으로 보인다). Wave 0 에서는 아무도 이 픽스처를 안 쓰므로 전량 green 이다. 의도된 스텁이며 01-03 에서 해소된다.

## Threat Flags

없음 — 이 플랜은 네트워크 표면을 0개 만든다. `curl` vendoring 은 실행 시점이 아니라 이번 1회이고, 산출물은 저장소에 고정됐다.

## Verification Evidence

```
CLI 기준선:  test_nvad 7 · test_reports 7 · test_ads_rules 21 · test_ledger 21 · test_bids 28 · test_prune 16 = 100 tests, 전부 exit=0 (불변)
웹앱:        .venv-web/bin/pytest webapp/tests -q → 17 passed
가드:        bash webapp/tests/no_commit_guard.sh → exit 0 (프로브로 exit 1 도 확인)
누출:        git status --porcelain 비었고 node_modules/package.json 0건
실측:        freshness("2026-08-30") = age_days 21 · window7 08-22~08-28 · stale True
             data_root() = /Users/choiyongsmacbook/python_work/data (workspace.toml 경유)
             run_dir_path("../../etc") → ValueError
리터럴:      grep "1500\|8765" webapp/ (비테스트) → settings.py DEFAULTS 2줄만
             grep "python_work" webapp/paths.py → 폴백 1줄만
```

## User Setup Required

None — 외부 서비스 설정 없음. 다만 `.venv-web` 은 `.gitignore` 대상이라 **다른 PC 에서는 재생성이 필요하다**:
```
uv venv .venv-web --python 3.12
uv pip install --python .venv-web/bin/python "fastapi==0.141.1" "uvicorn==0.53.0" "jinja2==3.1.6" "sse-starlette==3.4.11" "pytest"
```

## Next Phase Readiness

**Wave 1(01-02 · 01-03)로 바로 갈 수 있다.**

- `01-02` (CLI `--only-ads`/`--preview-out` 패치): `targets_one.json`·`targets_broken.json` 준비됨. `test_cli_patch.py` 를 `webapp/tests/` 에 두면 바로 돈다. CLI 100 tests 기준선이 이 플랜 전후로 불변임을 확인해 뒀다.
- `01-03` (보안·부팅토큰): `conftest.client` 가 `webapp.main:app` 과 `app.state.boot_token` 을 기대한다. 그 이름으로 만들면 픽스처 수정 없이 붙는다. `settings.PORT` 가 8765 를 준다.
- `01-04` (보드): `fake_result_json` 픽스처가 `zzfake` 포함 5계정을 준다 — 계정을 박으면 즉시 빨개진다.
- `01-06` (잡 엔진): `synthetic_job(lines, delay, rc)` 팩토리로 장시간·실패 경로를 광고비 0 으로 재현한다.

**주의 하나:** 실제 마지막 회차가 21일 묵었고 `stale=True` 다. Wave 4(01-06 Task 3)의 수동 확인에서 `prep --account cy728` 를 돌려 광고 API 자격증명이 아직 유효한지부터 봐야 한다(OQ-6).

## Self-Check: PASSED

- 파일 18개 전부 FOUND (`.gitignore` 포함 19)
- 커밋 4개 전부 FOUND: `97afb8b` · `8a73ebe` · `4121a24` · `70d8cd2`
- 커밋에 의도치 않은 파일 삭제 0건

---
*Phase: 01-board-bid-raise*
*Completed: 2026-09-20*
