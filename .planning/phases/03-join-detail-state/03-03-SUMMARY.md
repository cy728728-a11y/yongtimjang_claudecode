---
phase: 03-join-detail-state
plan: 03
subsystem: jobs-engine
tags: [sqlite, ss-index, bulsaja-mcp, argv, job-guard, eng-08, rate-limit]

# Dependency graph
requires:
  - phase: 01-board-bid-raise
    provides: "webapp/jobs.py 잡 엔진(create_job·전역 쓰기 락·LIVE_STATUSES·_reap) · webapp/argv.py 의 PY_CLI/AdsArgv/prefix 규약 · settings.cfg() · paths.repo_root()"
  - phase: 03-join-detail-state
    plan: 01
    provides: "settings 8키 + workspace.toml [webapp] · test_jobs.py 테이블 가드 {jobs, ss_index} 확장 · test_board.py 런타임_파일들 선등록 · test_paths.py 문자열 리터럴 가드"
provides:
  - "webapp.db 의 ss_index 테이블 + 인덱스 2종 (smartstore / market_group_id)"
  - "webapp/bulsaja_index.py — lookup · indexed_group_ids · group_health · profile_path · profile · profile_ok (stdlib sqlite3 mode=ro, 네트워크 0, 쓰기 0)"
  - "webapp/argv.py 의 BulsajaArgv + Nick 타입 + SS_INDEX_BUILD/BULSAJA_SCAN 경로 상수"
  - "잡 kind 3종 (bulsaja_profile / bulsaja_index / bulsaja_scan) + _build_argv 분기"
  - "jobs.AccountMismatchError (ENG-08) · jobs.SameKindBusyError (레이트리밋)"
  - "jobs.BULSAJA_KINDS · jobs.SINGLETON_KINDS"
  - "jobs.latest_done(kind, run_dir=None) — 마지막 성공 잡을 찾는 유일한 길"
affects: [03-04-index-cli, 03-05-routes, 03-06-board-ui, phase-05-detail-page]

# Tech tracking
tech-stack:
  added: []   # 새 외부 패키지 0건
  patterns:
    - "읽기 전용 저장소 모듈: mode=ro URI + is_file() 선확인 + 파일을 만들지 않는다"
    - "가드를 꺼서 red 가 되는 것을 확인한 뒤 커밋 (03-01 의 네거티브 확인 승계)"
    - "가드 위치를 성질로 가른다 — 파일 읽기는 트랜잭션 밖, DB 상태 확인은 안"
    - "같은 멤버여도 뜻이 다른 두 집합은 합치지 않는다 (BULSAJA_KINDS vs SINGLETON_KINDS)"
    - "설정값은 호출부가 cfg() 로 읽어 모델에 넘긴다 — 모델·CLI 에 기본값을 두지 않는다"

key-files:
  created:
    - webapp/bulsaja_index.py
    - webapp/tests/test_index.py
  modified:
    - webapp/jobs.py
    - webapp/argv.py
    - webapp/tests/test_jobs.py
    - webapp/tests/test_argv.py

key-decisions:
  - "group_health 의 완결 에 `행수 > 0` 을 더했다 — 플랜 공식대로면 한 번도 안 훑은 그룹이 완결=True 로 나와 D-18 제외 그룹의 행이 '광고 쪽 오류'로 둔갑한다 (fail-closed)"
  - "bulsaja_index/bulsaja_scan 은 회차를 필수로 했다 — 대상 파일이 회차의 web/ 밑에만 떨어지므로 회차 없는 경로는 어차피 죽은 길이고, 죽은 길에 폴백을 두면 다음 사람이 그게 지원되는 줄 안다"
  - "재검증 판정(히트/미스/미조회/불일치)을 이 모듈에 두지 않았다 — join.py(03-02)가 정본. 판정이 두 곳이면 화면과 산출물이 다른 말을 한다"
  - "AccountMismatchError 는 ValueError 상속을 유지했다 — 03-05 이전에도 400 으로 닫혀 있어 '열린 채로 새지' 않는다"
  - "bulsaja_index.db_path() 는 jobs.db_path() 를 세 줄 복제했다 — jobs → bulsaja_index → jobs 순환을 피하려면 이 방향뿐이고, settings.DB_PATH 라는 같은 출처를 보므로 어긋날 길이 없다"
  - "profile_path() 를 공개 함수로 올렸다 — 자식에게 --profile-out 을 넘기는 쪽과 그 파일을 읽는 쪽이 같은 계산을 봐야 한다"

patterns-established:
  - "인덱스 히트는 값이지 판정이 아니다 — 꺼내 주는 모듈과 판정하는 모듈을 분리"
  - "미조회(시스템)와 번호없음(광고 오류)을 구조로 분리 — group_health 가 전자의 근거를 댄다"
  - "kind 단위 동시성 가드: 전역 락으로 번지지 않으면서 레이트리밋 예산을 지킨다"

requirements-completed: [ENG-08, JOIN-04]

# Metrics
duration: 38min
completed: 2026-09-21
---

# Phase 3 Plan 03: 불사자 잡 3종 + 인덱스 관문 Summary

**`ss_index` 가 `webapp.db` 에 서고, 그걸 읽는 유일한 관문(`webapp/bulsaja_index.py`)이 네트워크 0·쓰기 0 으로 섰다. 불사자 잡 3종이 Phase 1 의 잡 엔진 계약을 그대로 타면서, 틀린 계정으로 도는 것과 같은 잡이 둘 동시에 도는 것을 `create_job` 안에서 막는다.**

## Performance

- **Duration:** 약 38분
- **Tasks:** 3 / 3
- **Tests:** 205 → **253 passed** (신규 48)
- **Files:** 신규 2 · 수정 4

## 무엇이 생겼나

### 1. `ss_index` 테이블 (`webapp/jobs.py` DDL)

`jobs` DDL 바로 옆, 같은 `# ※` 주석 관용구로 **두 줄을 못 박았다**:

- `※ observed_at 이 있어야 D-04 를 안 어긴다` — "채널상품ID 를 영구 키로 저장하는 것"과
  "관측 기록을 관측시각과 함께 보관하는 것"은 다르다. 20일 물갈이로 번호가 재발급되므로,
  적힌 값을 그대로 믿으면 조용히 틀린 상품을 가리킨다. 쓰기 직전 재검증이 그 선을 지킨다.
- `※ 이건 보드 캐시가 아니다` — 보드 캐시는 `result.json` 에서 언제든 재생성되는 투영이지만,
  이건 3시간 반을 태워야 다시 얻는 **외부 관측 기록**이다. 재생성이 공짜가 아니면 캐시가 아니다.

`smartstore` 에 `NOT NULL` 을 걸지 않았다 — 업로드 안 된 상품이 정상적으로 NULL 이고,
걸면 인덱스 잡이 그 그룹 중간에서 통째로 죽는다. 테스트로 고정했다.

### 2. `webapp/bulsaja_index.py` (275행)

| 함수 | 하는 일 |
|---|---|
| `db_path()` | `jobs.db_path()` 와 같은 파일. 순환 회피를 위해 세 줄 복제 (주석에 이유) |
| `lookup(smartstores)` | `{번호: {product_id, market_group_id, group_total, unresolved, observed_at}}`. 같은 번호는 **최신 관측이 이긴다** |
| `indexed_group_ids()` | 한 줄이라도 있는 마켓그룹 집합 |
| `group_health(gids)` | `{행수, 미조회, 총상품수, 완결}` — 그룹이 얼마나 훑렸나 |
| `profile_path()` | 계정 확인 산출물 자리 (읽는 쪽과 `--profile-out` 이 같은 계산을 본다) |
| `profile()` | 없거나 깨졌으면 `None`. `표시규칙` 을 버린다 |
| `profile_ok(nick, age)` | `(통과, 사유)`. 사유에 **기대·실제 닉네임을 싣지 않는다** (T-3-16) |

**절대 안 하는 것 4개**가 모듈 docstring에 박혀 있고, 그중 셋은 grep 가드로 고정된다:
MCP 호출(D-19) · 쓰기 · DB 파일 생성 · 인덱스 히트를 해소로 접기(JOIN-04).

`향후` 메모로 커머스API 500배 우회 경로(30초 vs 3시간 32분, 막는 건 자격증명과 앱 50개 등록)를
남겼다 — 인덱스 비용이 다시 아플 때 다음 사람이 같은 조사를 처음부터 하지 않게.

### 3. `BulsajaArgv` + 잡 3종

`webapp/argv.py` **같은 파일**에 뒀다 (`test_argv.py` 의 마지막 두 테스트가 "조립은 한 곳"을
기계로 집행한다). `Nick` 은 `Alias` 와 같은 계열의 방어인데 한 군데만 다르다 — 닉네임이 한글이라
문자 화이트리스트를 못 써서 **선행 하이픈과 공백만 거부**한다. `--force` 같은 닉네임이
자식의 argparse 에서 옵션으로 읽히는 길을 막는다 (T-3-13).

| kind | 스크립트 | 전역 쓰기 가드 | 같은 kind 중복 | ENG-08 |
|---|---|---|---|---|
| `bulsaja_profile` | `bulsaja_scan.py --profile-only` | 안 탄다 | 허용 | **안 탄다** (닭·달걀) |
| `bulsaja_index` | `ss_index_build.py` | 안 탄다 | **거부** | 탄다 |
| `bulsaja_scan` | `bulsaja_scan.py` | 안 탄다 | **거부** | 탄다 |

### 4. 가드 2종 — 둘 다 `create_job` 안이다

**①.5 ENG-08 계정 가드 (트랜잭션 밖).** 파일 읽기라 DB 경합과 무관하고, 3시간 32분짜리
인덱스를 틀린 계정으로 쌓고 나면 되돌리는 비용이 그 시간 전부다. **라우트가 아니라 여기**인
이유는 v2 의 APScheduler 가 같은 함수를 부르기 때문이다 (D-17/ENG-07).

**①.9 같은 kind 중복 가드 (`BEGIN IMMEDIATE` 안).** DB 상태를 보는 체크라 쓰기 가드와
같은 창 안에 있어야 두 요청이 "둘 다 없네"를 보고 둘 다 들어가지 않는다. `starting` 도 본다.
인덱스 잡 둘이 각자 초당 4회를 지켜도 합산 8회/초라 `240;w=60` 을 넘기고, 그 429 가
`unresolved=1` 로 남아 화면에서 **"미해소"로 둔갑**한다 — 이 페이즈 최대 오진이다 (Pitfall 3).

`WRITE_KINDS` 는 **건드리지 않았다.** 넣었으면 3시간 32분 동안 입찰가 인상·되돌리기가 전부
409 가 되고, 그러면 사람이 가드를 끈다(`jobs.py` 의 기존 판단). 양방향으로 테스트했다.

## Deviations from Plan

### 1. [Rule 2 - 누락된 필수 방어] `group_health` 의 `완결` 에 `행수 > 0` 을 더했다

- **Found during:** Task 1
- **Issue:** 플랜이 준 공식은 `미조회==0 and (총상품수 is None or 행수 >= 총상품수)` 였는데,
  **한 번도 안 훑은 그룹**(행수 0 · 총상품수 None)이 이 식에서 `완결=True` 로 나온다.
  D-18 로 뺀 그룹이 정확히 그 상태다 — 그러면 그 그룹의 행이 화면에서 "인덱스 불완전(시스템)"이
  아니라 "광고 쪽 오류"로 뜨고, 용팀장이 멀쩡한 광고그룹을 지우러 간다 (Pitfall 3 그 자체).
- **Fix:** `행수 > 0` 을 조건에 더하고, docstring 에 *"안 훑었다"와 "훑었는데 못 찾았다"는
  다른 사실*이라고 못 박았다. `test_디비가_없으면_만들지_않는다` · `test_그룹_완결성` 이 고정한다.
- **Files:** `webapp/bulsaja_index.py`
- **Commit:** `ccc8520`

### 2. [Rule 3 - 죽은 경로 제거] `bulsaja_index`/`bulsaja_scan` 은 회차를 필수로 했다

- **Found during:** Task 2
- **Issue:** 플랜은 `bulsaja_profile` 만 회차 없이 도는 것으로 적었고 나머지 둘의 `out` 자리를
  열어 뒀다. 그런데 대상(그룹/타깃) 파일은 `_write_targets`·`_override_targets` **둘 다
  회차의 `web/` 밑만** 허용한다 — 회차 없는 index/scan 은 대상 파일을 가질 수 없고,
  `_build_argv` 가 곧바로 ValueError 다. 즉 "회차 없는 index" 는 도달 불가능한 경로다.
- **Fix:** 그 경우 잡 로그 옆에 산출물을 떨구는 폴백을 **두지 않고** 명시적 ValueError 로 바꿨다.
  죽은 길에 폴백을 두면 다음 사람이 그게 지원되는 줄 안다.
- **Files:** `webapp/jobs.py`
- **Commit:** `e328635`

### 3. [계약 추가] `profile_path()` 를 공개 함수로 올렸다

- **Found during:** Task 2
- **Issue:** 플랜 인터페이스에는 `profile()`/`profile_ok()` 만 있었는데, `jobs._build_argv` 가
  자식에게 `--profile-out` 으로 넘길 경로를 **같은 계산**으로 구해야 한다. 각자 계산하면
  자식이 갱신한 파일을 이쪽이 안 읽는 상태가 조용히 생긴다.
- **Fix:** private `_프로필경로()` 를 `profile_path()` 로 공개. 03-05·03-06 도 이걸 쓴다.
- **Commit:** `e328635`

### 4. [테스트 산술 정정] `test_caffeinate_프리픽스가_앞에_붙는다`

플랜 본문은 *"`av[2]` 가 스크립트 경로"* 라고 적었는데, 2원소 프리픽스에서는 `av[2]` 가
인터프리터고 `av[3]` 이 스크립트다 (`test_prefix_는_맨_앞에_온다` 의 기존 관용구와 같다).
기존 관용구를 따랐다.

## 두 플랜에 걸친 이탈 — VALIDATION 2행의 실제 자리

**플랜이 미리 지시한 이탈이고, 03-02 SUMMARY 에도 같은 내용이 적혀야 한다.**

| VALIDATION 행 | 문서상 자리 | **실제 자리** | 이유 |
|---|---|---|---|
| `test_히트도_재검증한다` | `test_index.py` | **`test_join.py` (03-02)** | 재검증 판정 함수가 `join.py` 에 산다 |
| `test_불일치는_미해소` | `test_index.py` | **`test_join.py` (03-02)** | 같은 이유 |

이 플랜은 `test_index.py` 에 그 자리를 **비워 두고**, 대신 "이 모듈은 판정하지 않는다"를
docstring 과 테스트 주석으로 못 박았다. 판정이 두 곳에 있으면 화면과 산출물이 다른 말을 한다.

**Task 1 수용 기준 중 `pytest webapp/tests/test_join.py::...` 두 줄은 이 워크트리에서 돌릴 수
없었다** — `webapp/join.py`·`test_join.py` 는 같은 웨이브의 03-02 가 자기 워크트리에서 만든다.
병합 후 통합 회귀에서 확인해야 한다. (파일 소유권 분리가 병렬 실행의 전제였다.)

## 마찬가지로 아직 없는 것 (03-04 몫)

- `ss_index_build.py` · `bulsaja_scan.py` 두 CLI 가 아직 없다. `BulsajaArgv` 가 그 경로를
  가리키지만 **파일 존재를 확인하지 않는다** — `AdsArgv`/`RUN_ADS` 와 같은 규약이다.
  잡을 실제로 띄우면 지금은 자식이 즉시 실패한다(그게 맞는 동작이다).
- 레이트리밋 throttle(`test_초당4회_상한`)과 `test_429는_미조회로_남는다` 는 **일부러 안 썼다.**
  그 루프는 CLI 안에 있고, 여기서 흉내 내면 "우리가 짠 가짜 루프"를 검증하게 된다.
  `test_index.py` 상단에 그 사실을 적어 뒀다.

## 검증

```
.venv-web/bin/pytest webapp/tests -q               → 253 passed
bash webapp/tests/no_commit_guard.sh               → OK
.venv-web/bin/pytest webapp/tests/test_paths.py -k 리터럴  → 3 passed
grep -c 'mode=ro' webapp/bulsaja_index.py          → 4
grep -cE '(INSERT|UPDATE|DELETE|CREATE)' webapp/bulsaja_index.py  → 0
grep -cE '(eroomlib|requests|fastapi|starlette|APIRouter|HTTPException)' … → 0
grep -c '커머스API' webapp/bulsaja_index.py         → 1
grep -c 'ss_index' webapp/jobs.py                  → 4
grep -c '※ 이건 보드 캐시가 아니다' webapp/jobs.py   → 1
WRITE_KINDS ∩ SINGLETON_KINDS                      → 공집합
```

**네거티브 확인 (03-01 의 규율 승계):** 가드 둘(`if kind in BULSAJA_KINDS` / `if kind in
SINGLETON_KINDS`)을 `if False` 로 바꿔 돌렸더니 **7개 테스트가 정확히 빨개졌다** —
계정 3종 + kind 중복 3종 + 설정 연동 1종. 원복 후 다시 green 인 것을 확인하고 커밋했다.
"FAIL 을 본 적 없는 검증은 검증이 아니다."

## Known Stubs

없다. 이 플랜이 만든 함수는 전부 실제 데이터(테스트가 직접 INSERT 한 `ss_index` 행 ·
tmp 프로필 파일)로 동작이 확인됐다. 다만 **인덱스를 채우는 쪽이 아직 없어서**(03-04),
실행 중 화면에서는 `lookup()` 이 당분간 `{}` 를 준다 — 그건 스텁이 아니라 "아직 안 훑었다"
라는 정확한 상태이고, `group_health` 가 `완결=False` 로 그 사실을 댄다.

## Threat Flags

없다. 이 플랜이 만진 표면은 전부 `<threat_model>` 에 이미 등록돼 있다
(T-3-11 ~ T-3-17). 새 네트워크 엔드포인트·인증 경로·신뢰 경계는 0건이다.

## 다음 플랜에 넘기는 것

- **03-04 (CLI):** `BulsajaArgv` 가 내는 플래그 집합이 그쪽 argparse 의 계약이다 —
  `--db · --out · --profile-out · --expect-nick · --min-interval · --retry-after ·
  --batch-size · --run-dir · --groups · --targets · --limit · --profile-only`.
  자식은 `--expect-nick` 으로 **스스로 한 번 더** 계정을 확인해야 한다(웹앱 가드는 사전 점검일 뿐,
  잡이 뜨고 나서 계정이 바뀌는 창은 자식만 닫을 수 있다).
  프로필 JSON 규약: `{"닉네임": ..., "확인시각": ISO8601+오프셋}`. `표시규칙` 은 써서 보내도
  이쪽이 버리지만, 애초에 쓰지 마라.
- **03-05 (라우트):** `AccountMismatchError` 를 **`ValueError` 보다 먼저** `except` 해서 409 로
  번역해라. 안 하면 400 이 되어 "모르는 회차"와 구분이 안 된다. `SameKindBusyError` 는
  기존 `except jobs.BusyError` 가 이미 409 로 번역한다 — 손댈 필요 없다.
- **03-06 (보드):** 산출물은 `jobs.latest_done("bulsaja_scan", run_dir)` 으로 찾아라.
  `web/join_*.json` 을 glob 하지 마라 — 중간에 죽은 잡도 반쯤 쓴 파일을 남긴다.
  `group_health(...)["완결"]` 이 거짓인 그룹의 행은 **"인덱스 불완전(시스템)"** 으로 띄워라.
  "번호없음(광고 오류)"과 같은 칸에 담으면 안 된다.
