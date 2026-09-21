---
phase: 03-join-detail-state
plan: 05
subsystem: routes-board-ui
tags: [eng-08, join-01, csrf, htmx, bulsaja-mcp, resolution, cost-guard]

# Dependency graph
requires:
  - phase: 01-board-bid-raise
    provides: "잡 엔진·라우터 관용구(_작업만들기·JobReq·요청_풀기·_판정읽기) · security.guard 3층 · board.html 의 hx-post/#job-panel/#job-error 배선 · board.fold_products"
  - phase: 03-join-detail-state
    plan: 01
    provides: "settings 8키 + workspace.toml [webapp] · anonymize_join.py 익명화 규약 · result_join_real.json · test_board.py 런타임_파일들 선등록"
  - phase: 03-join-detail-state
    plan: 02
    provides: "join.attach · resolution · cleanup_groups · index_targets · market_number · group_index"
  - phase: 03-join-detail-state
    plan: 03
    provides: "jobs.AccountMismatchError · SameKindBusyError · BULSAJA_KINDS · latest_done · bulsaja_index.profile/profile_ok/profile_path · BulsajaArgv"
  - phase: 03-join-detail-state
    plan: 04
    provides: "bulsaja_scan.py · ss_index_build.py · bulsaja_rate.py"
provides:
  - "webapp/tests/fixtures/bulsaja_groups_real.json — 실회차 마켓그룹 86개 익명화본(번호 54개 보존)"
  - "anonymize_join.py 의 `그룹익명화()` + `--groups` 모드 (픽스처 재생성 가능)"
  - "test_실회차_해상률 — 번호층 해상률 92/194 실측 고정 (JOIN-01)"
  - "POST /jobs/bulsaja/{profile,scan,index} — 얇은 핸들러 3종"
  - "routes/jobs.py 의 예외→상태코드 표에 AccountMismatchError→409 · KeyError→500"
  - "routes/jobs.py 의 `_스캔대상키()` — ③⑤ 행 → `<alias>|<mallProductId>` (중복 제거)"
  - "routes/board.py 의 `_불사자표시()` — 계정 배너 화이트리스트 투영 5키"
  - "board.html 계정 배너 + 불사자 버튼 3개 (htmx · JS 0줄)"
affects: [03-06-board-ui, 03-07-실탄, phase-05-detail-page]

# Tech tracking
tech-stack:
  added: []   # 새 외부 패키지 0건
  patterns:
    - "픽스처를 숫자에 맞추지 않는다 — 실측을 단언하고 차이 사유를 docstring 에 적는다"
    - "익명화는 판정에 쓰이는 값(마켓번호)만 글자 그대로 남긴다 — 그래야 회귀가 재현된다"
    - "상속 관계가 있는 예외는 `except` 순서가 곧 동작이다 (좁은 것부터)"
    - "읽기 라우트에서만 설정 KeyError 를 잡아 배너 문구로 바꾼다 — 쓰기 경로는 계속 터뜨린다"
    - "비용을 결정하는 계산은 실제로 잡을 띄워 `target_count` 를 눈으로 본다"

key-files:
  created:
    - webapp/tests/fixtures/bulsaja_groups_real.json
  modified:
    - webapp/tests/fixtures/anonymize_join.py
    - webapp/tests/conftest.py
    - webapp/tests/test_join.py
    - webapp/routes/jobs.py
    - webapp/tests/test_routes_jobs.py
    - webapp/routes/board.py
    - webapp/templates/board.html
    - webapp/tests/test_board.py

key-decisions:
  - "해상률 기댓값을 VALIDATION 의 179/194 가 아니라 **실측 92/194** 로 단언했다 — 픽스처가 광고그룹 정리 전 회차라 179 는 이 디스크로 재현 불가능하다. 맞추려면 픽스처를 고쳐야 하는데 그 순간 테스트가 거짓말을 시작한다"
  - "인덱스 라우트가 `fold_products` 전량이 아니라 ③⑤ 로 좁힌 행을 쓴다 — 안 좁히면 40그룹(수 시간 추가)이다. 실서버로 잡을 띄워 보고 잡았다"
  - "계정 확인 잡은 `req.run_dir` 을 일부러 버린다 — 화면이 회차를 같이 보내와도 이 잡은 회차를 모르는 게 맞다"
  - "인덱스의 '스캔 없음' 은 409, '대상 0건' 은 400 — 고치는 주체가 다르다(순서 vs 광고 청소)"
  - "보드 라우트에서만 `expected_bulsaja_nick` 의 KeyError 를 잡아 배너 문구로 바꿨다 — 500 이면 화면이 통째로 안 떠서 사용자가 그 사실을 영영 못 본다"
  - "계정 배너 테스트를 test_board.py **맨 끝에** 붙였다 — 03-06 이 그 파일을 크게 손대므로 충돌 면을 줄였다"

patterns-established:
  - "가드를 무력화해 red 를 본 뒤 원복한다 (03-01·03-03·03-04 규율 승계) — 이번엔 그 규율이 '통과하는 척만 하던 테스트' 를 실제로 잡았다"
  - "비용 회귀는 단위 테스트가 아니라 실서버 `target_count` 로 먼저 본다"

requirements-completed: [ENG-08, JOIN-01, JOIN-04]

# Metrics
duration: 48min
completed: 2026-09-21
---

# Phase 3 Plan 05: 첫 수직 슬라이스 종료 — 버튼을 누르면 불사자를 훑는다 Summary

**브라우저에서 `조인 스캔` 을 눌러 실제 불사자 스캔 잡이 `done`(exit 0 · 13초 · 194행)까지 돌았다. 화면 맨 위에는 지금 붙어 있는 계정과 크레딧이 상시로 뜬다. 그리고 실서버로 인덱스 잡을 띄워 보다가, 인덱스가 훑을 마켓그룹을 40개로 계산하던 버그를 잡았다 — ③⑤ 로 좁히면 30개다.**

## Performance

- **Duration:** 약 48분
- **Tasks:** 3 / 3 (+ 이탈 1건)
- **Tests:** 297 → **319 passed** (신규 22)
- **Files:** 신규 1 · 수정 8
- **크레딧 소모:** **0** (전부 읽기 조회)

---

## 🔴 반드시 읽어야 할 세 숫자

### 1. 첫 실스캔 — 소요 0.6초 · **429 발생 0건**

```
회차 2026-09-20 · 대상 194행 · 최소간격 0.26초 (읽기 전용 조회 · 크레딧 0)
마켓그룹 86개
인덱스에 적혀 있던 행 0/194
끝 — 행 194 · 관측 0 · 미조회 0 · 사본묶음 0건 · 0.6초
```

**0.6초인 이유를 오해하지 마라.** 인덱스가 비어 있어서 실제 MCP 호출이
`bulsaja_my_profile` + `bulsaja_market_groups` **2회뿐**이었다. 상품층(workdata 194회 +
팬아웃 배치)은 인덱스가 찬 뒤에야 돈다 — **03-07 이 볼 시간은 이 숫자가 아니다.**

나중에 브라우저 라우트로 같은 스캔을 다시 돌렸을 때는 **13.0초**였다(자식 기동 +
`caffeinate` 프리픽스 + MCP 연결 포함). 03-06 의 배너 문구는 이쪽 숫자를 써라.

설정값은 손으로 안 적고 `settings.cfg()` 에서 꺼내 넘겼다 — 설정이 정본임을 실행으로도 증명했다.

### 2. 확정 해상률 — **92 / 194 (47%)**

| | VALIDATION 기댓값 | **실측** |
|---|---:|---:|
| 번호해소 | 179 (92%) | **92 (47%)** |
| 번호미해소 | 15 | **102** |
| 광고청소 버킷 | — | **102행 / 14그룹** (추출실패 57 · 번호없음 45) |
| 시스템 버킷 | — | **92행** |
| 상품해소 | — | **0** (인덱스를 아직 안 훑었다 — 정확한 상태다) |

**차이 사유:** `result_join_real.json` 은 2026-09-20 회차, 즉 용팀장이 광고그룹을
**정리하기 전** 스냅샷이다. CONTEXT 의 179 는 정리(69→58그룹, 번호 9건 정정)를 끝낸 뒤
그 이름을 같은 회차에 다시 입혀 **재판정**한 값이라, 디스크의 이 픽스처로는 재현되지
않는다. 179 를 보려면 정리 후 광고 회차를 새로 떠야 하고 그건 네이버 광고 API 를 다시
도는 일 — 이 플랜의 범위가 아니다.

**픽스처를 숫자에 맞추지 않았다.** 플랜의 명시적 지시이기도 하고, 맞추는 순간 이
테스트가 지키는 게 0이 된다. `test_실회차_해상률` 의 docstring 에 이 문단을 그대로 적어
뒀고, "179 가 나오면 픽스처를 갈아끼운 것이니 docstring 을 같이 고쳐라" 도 적었다.

실회차 원본(`result.json`)으로 같은 계산을 돌려도 **92/194 · 102미해소 · 14그룹**으로
똑같다 — 익명화가 번호를 안 건드렸다는 교차 검증이다.

### 3. 인덱스 대상 — **30그룹** (D-18 제외 후 · 제외 전 31)

이 숫자가 03-07 의 비용을 정한다. RESEARCH 의 31그룹과 같은 수인데, **그 측정도 정리 전
회차였기 때문**이다. 정리 후 회차로 갈아타면 늘어난다(CONTEXT 는 37그룹을 말한다).

---

## 무엇이 생겼나

### Task 1 — 해상률 회귀 + 마켓그룹 픽스처

`webapp/tests/fixtures/bulsaja_groups_real.json` (86그룹 · **번호 있는 그룹 54개**).
마켓번호 `NN-N` 은 **글자 그대로** 남기고 나머지 이름은 전량 `zzfake`, `groupId` 는
연번 가짜값(`9000001~`)이다. 해상률이 번호로만 결정되므로 익명화해도 회귀가 재현된다.

`anonymize_join.py` 에 `그룹익명화()` + `--groups` 모드를 더해 **재생성 가능**하게 뒀다.
`NN번_` 접두(마켓번호가 **아닌** 숫자)도 보존한다 — 오탐 회귀의 입력이다.

테스트 2종: `test_실회차_해상률` · `test_실회차_그룹픽스처에_실물이름이_없다`.

### Task 2 — 라우트 3종

| 라우트 | 대상 | 거부 |
|---|---|---|
| `POST /jobs/bulsaja/profile` | 없음 (회차도 버린다) | 계정 가드 **안 탄다** (닭·달걀) |
| `POST /jobs/bulsaja/scan` | ③⑤ 행 → `<alias>\|<mallProductId>` (중복 제거·순서 보존) | 회차 없음 400 · 대상 0건 400 · 계정 409 |
| `POST /jobs/bulsaja/index` | `join.index_targets` 의 groupId (번호 기준 중복 제거) | 스캔 없음 **409** · 대상 0건 **400** · 계정 409 |

**🔴 03-03 의 숙제 완료:** `except jobs.AccountMismatchError` 를 `except ValueError`
**앞에** 넣어 409 로 번역한다. 상속 관계라 순서가 곧 동작이다.
`except KeyError` → 500 + "설정 `webapp.expected_bulsaja_nick` 이 비었다" 도 더했다.

**클라이언트가 대상을 지정할 인자가 아예 없다** — `JobReq` 에 필드가 없는 것이 방어의
전부이고, `test_인덱스_대상은_서버가_만든다` 가 모델 필드 집합을 기계로 고정한다.

### Task 3 — 계정 배너 + 버튼 3개

`routes/board.py` 의 `_불사자표시()` 가 5키(`닉네임·크레딧·확인시각·일치·사유)만 투영한다.
응답을 통째로 넘기지 않으므로 `표시규칙`(프롬프트 인젝션)이 화면으로 새는 길이 구조적으로 없다.

`board.html` 에 `<p id="bulsaja-account">` + 버튼 3개. **`board.js` 변경 0줄**,
`hx-post` 3개 / `hx-get` 0개. 계정 확인만 `{% if run_dir %}` **밖**이다 —
회차가 하나도 없는 상태에서 제일 먼저 눌러야 하는 버튼이다.

비용 경고에 숫자를 안 박았다(회차·설정마다 다르다). `test_불사자_버튼은_POST_다` 가
`3시간 32분`·`36그룹`·`13-2` 같은 리터럴이 템플릿에 없는 것을 기계로 본다.

---

## Deviations from Plan

### 1. [Rule 1 - Bug · 비용] 인덱스 대상을 ③⑤ 로 좁혔다 — 40그룹 → 30그룹

- **Found during:** Task 3 이후, 실서버 라우트로 실제 잡을 띄워 보다가
- **Issue:** 플랜 action 이 지시한 대로 `board.fold_products(판정)` → `join.attach` →
  `index_targets` 를 그대로 썼다. 그런데 `fold_products` 는 **6규칙 전부**를 접어
  실측 **6,945행**을 준다(③⑤ 는 194행이다). 라우트가 띄운 잡의 `target_count` 가
  30 이 아니라 **40** 으로 찍혔다 — 작업 대상이 하나도 없는 마켓그룹 10개를
  **수 시간 동안** 더 훑는다. D-18 이 2시간 7분을 깎아 낸 그 비용이 도로 붙는 자리다.
- **Fix:** `_스캔대상키()` 로 만든 키 집합으로 행을 먼저 좁힌다. **스캔과 같은 함수**에서
  기준이 오므로 "스캔한 것과 인덱스한 것이 다르다" 가 성립하지 않는다.
- **Verification:** 실회차로 30(제외 후)/31(제외 전) 확인. `test_인덱스는_작업대상_행으로만_대상을_고른다` 로 고정.
- **Files:** `webapp/routes/jobs.py` · `webapp/tests/test_routes_jobs.py`
- **Commit:** `eb2c872`

**이 버그는 단위 테스트로는 안 잡혔을 것이다.** 라우트는 200 을 주고 잡은 정상으로 도는데
**몇 시간을 더 쓸 뿐**이다. 실서버로 띄워 `target_count` 를 눈으로 본 것이 유일한 발견 경로였다.

### 2. [Rule 1 - Bug] 그 회귀 테스트가 처음엔 **물지 않았다**

- **Found during:** 네거티브 확인
- **Issue:** 좁히기를 제거했는데도 테스트가 green 이었다. 원인은 픽스처 — 두 행에
  `adId` 를 안 줘서 `board._dedupe_ads` 가 `None` 키로 **한 줄로 뭉갰다.** 행이 1개면
  좁히든 말든 결과가 같다.
- **Fix:** `adId` 를 서로 다르게 주고 red(`['9000001','9000002'] == ['9000001']`)를 본 뒤
  원복해 green 을 확인했다. 그 이유를 테스트 주석에 적었다.
- **Commit:** `eb2c872`

> "FAIL 을 본 적 없는 검증은 검증이 아니다" 가 이번엔 **실제로 무언가를 잡았다.**

### 3. [계획된 이탈] `test_계정불일치면_409` 를 인덱스가 아니라 **스캔**으로 때린다

- **Found during:** Task 2
- **Issue:** 계정 가드는 `create_job` **안**에 있다(D-17 — v2 스케줄러가 같은 함수를
  부른다). 그래서 라우트의 앞단 검사(회차·대상 계산)를 **통과해야** 가드에 도달한다.
  인덱스는 "스캔 없음 409" 가 먼저 걸려 계정 사유가 안 나온다.
- **Fix:** 대상이 있는 회차로 **스캔**을 때려 계정 409 를 확인하고, 인덱스의 순서 우선은
  `test_인덱스는_순서검사를_먼저_본다` 로 **따로 고정**했다. 둘 다 409 라 사용자가 막히는
  사실과 상태코드는 같고, 계정이 다르다는 것은 **보드 배너가 상시로** 말한다.
- **주의:** 이 테스트는 `엿듣기` 픽스처를 **일부러 안 쓴다** — 그 픽스처가 `create_job` 을
  가로채 `kind="synthetic"` 으로 바꾸므로 가드가 통째로 우회된다. 처음엔 그것 때문에
  200 이 나왔다.

### 4. [범위 추가] 계정 배너 테스트 6종을 `test_board.py` 에 더했다

플랜 수용 기준은 인라인 `python -c` 한 줄이었는데, 그건 사람이 한 번 돌리고 끝난다.
같은 검사를 pytest 로 올렸다(이 저장소가 이미 쓰는 방식). **파일 맨 끝에 붙여**
03-06 과의 충돌 면을 줄였고, `런타임_파일들` 은 03-01 이 이미 `routes/board.py`·
`templates/board.html` 을 등록해 둬서 **한 글자도 안 건드렸다**(새 런타임 파일 0개).

### 5. [범위 추가] `test_스캔_대상은_서버가_회차에서_만든다` · `test_스캔대상키는_...`

플랜이 요구한 5종 외에, 스캔 쪽도 "클라이언트가 보낸 대상이 섞이지 않는다" 를 고정했다.
인덱스만 막고 스캔을 열어 두면 D-11 이 절반만 지켜진다.

---

## 🔴 03-06 이 알아야 할 것 — "미조회" 가 "미스" 로 보인다

실스캔을 돌린 뒤 같은 회차를 조인하면 시스템 버킷의 내역이 이렇게 갈린다:

| 상황 | 시스템 버킷 내역 |
|---|---|
| 스캔 **전** (`join_doc` 없음) | 미조회 92 · 미스 0 |
| 스캔 **후** · 인덱스 **전** | 미조회 8 · **미스 84** |

원인: `bulsaja_scan.py` 의 `인덱스조회()` 가 **테이블 존재**로 `인덱스있음` 을 판정한다.
서버가 기동하면서 `init_db()` 가 빈 `ss_index` 를 만들어 두므로 `인덱스있음=True` 가 되고,
행의 `미조회` 플래그가 `False` 로 적힌다. 그러면 `재검증판정(None, None, False)` → **`미스`** 다.

**`미스` 의 뜻은 "마켓그룹은 좁혀졌는데 그 안에 이 상품이 없다" 인데, 실제로는 한 번도 안
훑었다.** 둘 다 `시스템` 버킷이라 **이 페이즈 최대 오진(광고청소로 둔갑)은 안 난다** —
그래서 여기서 계약을 고치지 않았다(`join.py`·`bulsaja_scan.py` 는 앞 웨이브 소유이고,
`재검증판정` 의 ②번 규칙을 바꾸면 인덱스가 찬 뒤의 정상 `미스` 판정이 흐려진다).

**03-06 이 할 일:** 03-03 이 이미 답을 넘겨 뒀다 —
`group_health(...)["완결"]` 이 거짓인 그룹의 행은 **"인덱스 불완전(시스템)"** 으로 띄워라.
`미스` 라는 글자를 그대로 화면에 쓰지 마라.

---

## 검증

```
.venv-web/bin/pytest webapp/tests -q                              → 319 passed (297 → +22)
.venv-web/bin/pytest "webapp/tests/test_join.py::test_실회차_해상률" -x → passed
.venv-web/bin/pytest webapp/tests/test_routes_jobs.py -q          → 27 passed
.venv-web/bin/pytest webapp/tests/test_board.py -q                → 15 passed
.venv-web/bin/pytest webapp/tests/test_board.py -k 계정을_코드에     → 1 passed
.venv-web/bin/pytest webapp/tests/test_paths.py -k 리터럴          → 3 passed
bash webapp/tests/no_commit_guard.sh                              → OK
bash webapp/tests/security_curl.sh  (실서버 8799)                  → **보안 9종 전량 PASS**

grep -c 'bulsaja/scan' webapp/routes/jobs.py                      → 2  (목차 + 라우트)
'except jobs.AccountMismatchError' 줄번호 374 < 'except ValueError' 첫 줄번호 382  → OK
'^@router.get' 첫 줄 756 > '^@router.post' 마지막 줄 688            → GET 규약 유지
grep -c 'hx-post="/jobs/bulsaja' webapp/templates/board.html      → 3
grep -c 'hx-get="/jobs/bulsaja'  webapp/templates/board.html      → 0
git diff --stat webapp/static/board.js                            → **변경 0줄**
grep -rnE '^\s*(import|from)\s+(eroomlib|requests)' webapp/       → **0건** (D-19)
번호 있는 그룹 54개 (수용 기준 40개 이상)                            → OK
스캔 로그의 HTTP 429                                               → **0건**
profile_ok(expected_bulsaja_nick, profile_max_age_min)            → 계정 확인 OK
```

**실서버 확인 (포트 8799 · 격리 DB):**

```
GET  /jobs/bulsaja/scan               → 405   (T-3-25)
POST /jobs/bulsaja/index (토큰 없음)   → 403
POST /jobs/bulsaja/index (스캔 없음)   → 409 "먼저 조인 스캔을 돌려라 …"
POST /jobs/bulsaja/scan  (정상)        → 200 → status=done · exit 0 · 194행 · 13.0초
POST /jobs/bulsaja/index (스캔 있음)   → 200 · target_count 40  ← 🔴 버그 발견 (→ 30 으로 수정)
```

인덱스 잡은 **의도적으로 즉시 정지**시켰다. 실탄 완주는 03-07 이 사람 승인 아래 돈다.

**네거티브 확인 3건 (앞 플랜들의 규율 승계):**
1. `except jobs.AccountMismatchError` 를 무력화 → `test_계정불일치면_409` 가 **400 으로 red**
2. 마켓그룹 픽스처에서 번호를 지움 → `번호해소` 가 **92 → 0**
3. 인덱스 좁히기를 제거 → 회귀가 **green 이었다**(픽스처 결함) → 픽스처를 고쳐 red 확인 후 green

---

## 인증 게이트

없었다. 불사자 MCP 토큰은 `~/.claude.json` 에 이미 있고 `bulsaja_mcp` 가 런타임에 읽는다 —
이 플랜은 토큰을 만지지 않는다. 첫 실스캔 시점의 계정이 기대값(`부킹`)과 일치해
`--expect-nick` 가드를 한 번에 통과했다.

## Known Stubs

없다. 세 라우트 모두 실서버에서 실제로 호출해 상태코드와 잡 상태를 확인했고, 배너는
실제 프로필 파일(`닉네임`·`크레딧`·`확인시각`)로 렌더된다.

`상품해소 = 0` 은 스텁이 아니라 **정확한 상태**다 — 인덱스를 아직 한 번도 안 훑었고,
`group_health` 가 `완결=False` 로 그 사실을 댄다. 03-07 실탄 뒤에 0 이 아니게 된다.

## Threat Flags

없다. 이 플랜이 만진 표면은 전부 `<threat_model>` 에 등록돼 있다(T-3-25 ~ T-3-30).
새 네트워크 엔드포인트 3개는 전부 기존 `security.guard` 3층(Host/Origin/부팅토큰) 아래에
있고, `security_curl.sh` 9종이 실서버에서 그걸 확인했다.

| 위협 | 어디서 막혔나 |
|---|---|
| T-3-25 교차 사이트 인덱스 기동 | 세 라우트 전부 POST · `test_불사자_라우트는_GET이_아니다`(405) · 실서버 405 확인 |
| T-3-26 틀린 계정으로 기동 | `create_job` 의 ENG-08 가드 + `AccountMismatchError`→409 (`ValueError` **앞**) |
| T-3-27 클라이언트가 그룹 지정 | `JobReq` 필드 집합을 테스트가 고정 · 본문의 `groups` 가 무시되는 것 확인 |
| T-3-28 닉네임·크레딧 XSS | Jinja2 자동 이스케이프 유지 · `\|safe` 0건(테스트가 본다) · 화이트리스트 투영 |
| T-3-29 거부 사유에 기대 닉네임 | `profile_ok` 사유를 그대로 쓰고, 사유에 기대·실제 닉이 없음을 테스트가 단언 |
| T-3-30 빈 대상이 전량 | 라우트 400 · `_build_argv` ValueError · CLI `exit 2` (3층) |

## 다음 플랜에 넘기는 것

- **03-06 (보드 UI):**
  - 해상률 배너 문구는 **92/194** 가 아니라 화면이 그때그때 계산한 값을 써라.
    `resolution()` 의 두 버킷을 **한 숫자로 합치지 마라** — `cleanup_groups()` 가
    "광고 쪽에 청소할 그룹 N개" 의 N 을 바로 준다(실측 14).
  - **위 §"미조회가 미스로 보인다" 를 반드시 읽어라.** `group_health(...)["완결"]` 로
    갈라서 "인덱스 불완전(시스템)" 으로 띄워야 한다.
  - 스캔 산출물은 `jobs.latest_done("bulsaja_scan", run_dir)["result_path"]` 로 찾아라.
    라우트가 이미 그 길을 쓴다.
  - 제외 표시는 `settings.cfg("index_excluded_groups")` 에서 읽어라 — 산출물의
    `제외그룹` 은 `null` 이다.
  - `test_board.py` 끝의 계정 배너 6종을 지우지 마라.
- **03-07 (실탄):**
  - **대상 30그룹**(D-18 `13-2` 제외 후)이다. 제외를 안 걸면 31.
  - 첫 실행은 **작은 그룹 하나에 `--limit`** 을 걸어 03-04 의 Known Stubs 2건을 확인해라:
    ① 진행 로그의 `(서버 집계 N건)` 이 실제 숫자인가 ② `사본 조회 1단` 이 0건이 아닌가.
  - 스캔은 이미 실물로 돌았다(exit 0 · 194행). 인덱스가 찬 뒤 스캔을 **다시** 돌려야
    상품층이 채워진다 — 스캔은 인덱스에 적힌 productId 가 있는 행만 workdata 를 부른다.
  - 라우트에서 띄우면 `caffeinate -i` 프리픽스가 자동으로 붙는다(`BulsajaArgv.prefix`).
- **Phase 5:** 크레딧 견적을 띄울 자리는 배너의 **크레딧 칸 옆**이다 — 지금 만들어 뒀다.

## Self-Check: PASSED

**생성 파일 존재 확인** — FOUND
- `webapp/tests/fixtures/bulsaja_groups_real.json`
- `.planning/phases/03-join-detail-state/03-05-SUMMARY.md`

**커밋 존재 확인** — 4/4 FOUND
`fe01431`(T1) · `a94b2a1`(T2) · `44ba915`(T3) · `eb2c872`(비용 버그 수정)

**삭제된 추적 파일 0건** — `git diff --diff-filter=D --name-only 999d253..HEAD` 비어 있음

**STATE.md · ROADMAP.md 미수정** (오케스트레이터 소유)

**`webapp/` 아래 `eroomlib`/`requests` import 0건 유지** — D-19 OK

**워크트리에 심었던 `.venv`·`.venv-web`·`workspace.toml` 심볼릭 링크 제거 확인**
(`webapp.db`·`webapp-profile.json` 은 `.gitignore` 대상이라 커밋에 안 들어갔다)

---
*Phase: 03-join-detail-state*
*Completed: 2026-09-21*
