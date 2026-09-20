---
phase: 01-board-bid-raise
plan: 07
subsystem: select-preview
tags: [tabulator, row-selection, cdp, headless-chrome, dry-run, pydantic, jinja2, tdd, oq-7]

# Dependency graph
requires:
  - phase: 01-01
    provides: "conftest(tmp_run_dir · fake_result_json · client) · result_min.json 픽스처 · no_commit_guard.sh · vendoring 된 Tabulator 6.5.3"
  - phase: 01-02
    provides: "run_ads.py bids --only-ads / --preview-out · bids.run_bids 의 plans/counts 리턴 · BID-03 실데이터 정본(70→80)"
  - phase: 01-03
    provides: "security.guard 3층 · page_cookie_ok · security_curl.sh(V-SAFE-02c2 자동 강화 장치)"
  - phase: 01-04
    provides: "board.fold_products(rule1_ads · rule1_count) · board.js 필터 · board_cdp.{sh,mjs} 하네스 모양 · '한 스텝 랙' 교훈"
  - phase: 01-05
    provides: "jobs.create_job(only_ads → targets 파일) · AdsArgv(preview_out) · 전역 쓰기 가드 · BusyError"
  - phase: 01-06
    provides: "_job_panel.html SSE 배선 · GET /jobs/{id}/stream · sse_cdp.{sh,mjs} · '벤더 소스가 정본' 교훈"
provides:
  - "webapp/flow.py — collect_rule1_ads · collect_targets · check_limits · read_preview · summarize_counts · raise_total · preview_rows · total_rows · LimitError"
  - "POST /jobs/bids/preview — BidsPreviewReq(run_dir, ad_ids[^nad-]) → {job_id}. 실행 플래그를 넘길 인자가 없다"
  - "GET /jobs/{id}/result — 미리보기 표 조각(HX) / JSON. 읽기 전용"
  - "GET /jobs/{id}/panel — 작업 패널 조각. fetch 로 접수한 잡의 SSE 를 여는 창"
  - "webapp/templates/_preview_table.html — 소재 단위 표 + action 집계 + 예상 인상액 합계"
  - "board.js 선택 컬럼 — 헤더 체크박스는 rowRange:'visible', 필터 전체는 확인 배너"
  - "paths.run_accounts / paths.scan_runs / freshness 의 accounts·missing_accounts (OQ-7)"
  - "webapp/tests/preview_cdp.{sh,mjs} — 선택·미리보기 브라우저 검증 31종"
  - "webapp/tests/test_flow.py — 11종"
affects: [01-08, 01-09, "Phase 2 삭제 버튼(타이핑 확인은 거기 몫)", "Phase 3 JOIN-03 팬아웃 표시"]

# Tech tracking
tech-stack:
  added: []          # 신규 의존성 0
  patterns:
    - "화면이 보낸 대상을 서버가 **다시 검증한다** — 정답지 밖이면 버리지 않고 400 으로 거부 (T-1-30)"
    - "빈 대상 목록도 파일로 떨군다 — 플래그가 빠지면 CLI 가 '전량' 으로 읽는다"
    - "값은 CLI 산출물에서 읽어 표시만. `to - from` 은 표시고 `bid + 10` 은 두 번째 정본이다"
    - "Tabulator 이벤트 핸들러는 이벤트가 넘겨주는 값만 믿는다 — 내부 상태는 아직 안 갈렸다"
    - "브라우저 계층 검증은 pytest 밖 CDP 하네스 (security_curl/board_cdp/sse_cdp 와 동급)"
    - "새 검증 수단은 버그 버전으로 되돌려 FAIL 을 본 뒤에만 믿는다 (음성 대조군 6종)"

patterns-established:
  - "**벤더 소스가 문서·플랜 예제보다 정본이다.** 01-06 의 `sse.js:235`(sse-close 는 연결 엘리먼트에서만 읽힌다)에 이어 두 번째다 — 이번엔 `tabulator.min.js` 의 `selectRows(undefined) → rowManager.rows`. 둘 다 '문서대로 썼는데 화면 증상이 0' 인 종류였다. **라이브러리 동작을 가정하기 전에 vendoring 된 소스를 열어라.**"
  - "육안 확인은 '보인다/움직인다' 까지만 본다. 선택 수·건수처럼 **다른 수가 같은 자리에 들어가도 그럴듯한** 값은 기계가 원본에서 직접 세서 대조해야 한다"
  - "체크포인트 항목은 가능한 한 하네스로 대행하고, 사람에게는 취향·범위 판단만 남긴다"

key-files:
  created:
    - webapp/flow.py
    - webapp/templates/_preview_table.html   # 자리만 있던 것을 채움
    - webapp/tests/test_flow.py
    - webapp/tests/preview_cdp.sh
    - webapp/tests/preview_cdp.mjs
  modified:
    - webapp/routes/jobs.py
    - webapp/routes/board.py
    - webapp/jobs.py
    - webapp/paths.py
    - webapp/static/board.js
    - webapp/templates/board.html
    - webapp/tests/test_paths.py
    - .planning/phases/01-board-bid-raise/01-VALIDATION.md

key-decisions:
  - "헤더 체크박스는 rowRange:'visible'(뷰포트) — 안 주면 Tabulator 가 필터를 무시하고 전체 행을 고른다"
  - "선택이 필터 밖에 남으면 요약 줄이 그 건수를 말한다 — Tabulator 는 필터를 바꿔도 선택을 유지한다"
  - "collect_targets 가 오염된 adId 를 버리지 않고 거부한다 — 버리면 '고른 N건' 과 '처리된 M건' 이 갈라진다"
  - "빈 대상도 targets 파일을 쓴다(only_ads is not None) — truthy 검사면 0건이 조용히 전량이 된다"
  - "미리보기 라우트와 실행 라우트를 물리적으로 분리 — 플래그 하나로 갈리는 설계면 그 플래그를 채우는 경로가 언젠가 생긴다"
  - "계정 수의 출처는 result.json 뿐(BOARD-02 와 같은 근거). (경로,mtime_ns,size) 로 메모해 재판정을 따라온다"
  - "OQ-7 은 '보여주기' 까지 — 회차 선택을 막지도 경고색을 넣지도 않는다"
  - "수동 3종(BOARD-03·FLOW-04·BID-03)을 CDP 로 자동화 — 01-06 의 SC-03 과 같은 이유로 기계가 더 정확하다"

requirements-completed: [BOARD-03, BOARD-04, BID-01, BID-02, BID-03, FLOW-04]

# Metrics
duration: 26min
completed: 2026-09-20
---

# Phase 1 Plan 07: Skeleton A 완성 — 상품 줄을 골라 `70 → 80` 표를 띄운다 Summary

**보드에서 상품을 골라 "입찰가 인상 미리보기" 를 누르면 `POST /jobs/bids/preview` → targets 파일 → CLI dry-run → `--preview-out` 산출물 → 소재 단위 표가 0.38초에 뜬다. 값은 웹앱이 한 번도 계산하지 않고 CLI 산출물을 그대로 옮긴다 — 실측 `70 → 80`(그룹 기본가 기준), 재계산했으면 `50 → 60` 이었다. 광고 API 호출 0 · 크레딧 0 · 광고비 0.**

## Performance

- **Duration:** 26 min (18:45 ~ 19:04 KST + 재검증)
- **Tasks:** 4 (플랜 2 + OQ-7 + CDP 하네스) · 커밋 7
- **Files:** 13 (신규 5 · 수정 8) · +1,877 / −52
- **테스트:** 웹앱 115 → **130 passed (10.2초)** · CDP 하네스 19 → **50종**(board 19 + preview 31) · CLI 회귀 100 불변

## Accomplishments

- **3단 계약의 앞 두 단이 파일로 굳었다.** `create_job` 이 `run-dir/web/targets_<job>.json` 을 원자적으로 딱 한 번 쓰고 jobs 행의 `targets_path` 에 묶는다. 실측: 잡 9개 → `targets_*.json` 9개 / `preview_*.json` 9개, **잡당 정확히 한 쌍**. 실행(01-08)·되돌리기(01-09)는 화면 상태가 아니라 이 파일을 재사용한다(FLOW-02 / D-11).
- **웹앱이 입찰가를 계산하지 않는다는 것이 두 겹으로 증명됐다.** (a) `webapp/` 런타임 `.py`·`.js` 를 토큰 단위로 주석·문자열을 걷어내고 훑어 `BID_STEP`·`bid ±`·`+ 10`·`* 1.1` 패턴 0건, (b) 산출물에 **산술이 안 맞는 값**(`70 → 999`)을 넣고 화면에 999 가 찍히는지 본다 — 재계산하면 80 이 나와 즉시 빨개진다. 실데이터 CDP 실측은 `70 → 80 · 그룹입찰따름 예`.
- **"보이는 것" 과 "필터 전체" 가 실제로 다른 수를 준다.** CDP 실측: 계정 필터 적용 후 헤더 체크박스 → 선택 15 / 필터 전체 89 / 전체 2,637. 선택된 행의 계정이 필터 계정 하나뿐인 것까지 확인한다. 전체 선택은 배너를 한 번 더 거치고, **취소하면 선택 수가 한 줄도 안 변한다**(취소 전 15 → 취소 후 15).
- **건수 타이핑 입력칸 0개** (FLOW-04). 입찰가는 되돌릴 수 있으므로 배너 한 번이면 충분하다. 타이핑 확인은 Phase 2 의 **삭제** 버튼 몫이고, 그 구분을 코드 주석에 남겼다 — 되돌릴 수 있는 것과 없는 것에 같은 마찰을 걸면 사람이 양쪽 다 기계적으로 통과시킨다.
- **0건 미리보기가 고장으로 안 읽힌다** (Pitfall 6). 집계 줄을 **항상** 띄운다: `대상 1,195건 → 인상 1,195` · `예상 인상액 합계 +11,950원`. 인상이 0건이면 `오늘 이미 올린 소재다 — 쿨다운 6일이 지나야 다시 오른다. 고장 아니다.` 를 붙인다. 표가 잘리면 `1,195건 중 상위 200건만 그린다` 로 **잘렸다고 말한다**(`report_md._count_label` 관례).
- **상한이 설정을 진짜로 따라온다** (D-08). `check_limits` 는 `settings.PER_ACCOUNT_LIMIT` 을 호출마다 읽고, 테스트가 상한을 3으로 낮춰 동작이 바뀌는 것까지 단언한다. 총합이 아니라 계정별이다 — 실측 최대 ownway1 1,195 < 1,500 이라 평상시 마찰 0 이고, 이번 회차 1,195건 미리보기가 거부 없이 통과했다.
- **회차마다 들어 있는 계정이 화면에 나온다** (OQ-7). 드롭다운이 `2026-08-29 회차 · 계정 2개` 처럼 **고르기 전에** 비교되게 하고, 신선도 배너가 `계정 2개 (cy728, cy7728)` + `이 회차엔 없는 계정이 있다: ownway1, pogeunae — … 대상이 없어서가 아니라 그 계정을 안 본 것이다` 를 말한다. 막지 않는다, 보여만 준다.
- **보안 9종이 새 라우트로 조여졌다.** 01-06 이 걸어 둔 장치대로 `V-SAFE-02c2` 가 라우트가 생기는 순간 판정을 `정확히 404` → `-lt 400` 으로 바꿨고, 실측 **200**. 9/9 유지.

## Task Commits

1. **Task 1: 보드 선택 UI** — `abc6e5c`
2. **Task 2: `flow.py` + `POST /jobs/bids/preview` + 미리보기 표** (TDD) — `a3ff6c7`(test, RED: import 단계부터 전량 빨강) → `bd4f3b2`(feat, GREEN)
3. **Task 3(지시 추가): OQ-7 회차별 계정 수** — `c357758`
4. **Task 4(추가): 미리보기 CDP 하네스 + 랙 버그 수정** — `6b416cb`
5. VALIDATION 갱신 — `313bbd2` · 집계 줄 천 단위 — `0b58f08`

## Files Created/Modified

- `webapp/flow.py` (신규 246줄) — 3단 계약의 파일 사슬. 모듈 docstring 에 "화면 상태가 아니라 파일이 진실" 과 "여기서 입찰가를 계산하지 않는다" 를 못박았다
- `webapp/routes/jobs.py` (+150) — `BidsPreviewReq`(`^nad-` 패턴 + 설정 기반 개수 상한) · `POST /jobs/bids/preview` · `GET /jobs/{id}/panel` · `GET /jobs/{id}/result`
- `webapp/jobs.py` (+7/−2) — `only_ads is not None` (아래 Rule 2)
- `webapp/paths.py` (+50) — `run_accounts` · `scan_runs` · `freshness` 확장
- `webapp/static/board.js` (+190) — 선택 컬럼 · 요약 · 배너 · fetch 접수
- `webapp/templates/_preview_table.html` (자리 13줄 → 90줄) · `board.html` (+60)
- `webapp/tests/test_flow.py` (신규 407줄, 11종) · `test_paths.py` (+89, 4종)
- `webapp/tests/preview_cdp.{sh,mjs}` (신규 · 31종)

### 테스트가 지키는 것

| 테스트 | 겨누는 것 |
|---|---|
| `test_targets_파일이_하나다` | FLOW-02 / T-1-06 — 잡당 한 쌍, 두 번째 잡이 남의 파일을 안 덮는다 |
| `test_대상이_0건이어도_전량으로_번지지_않는다` | T-1-05 — 빈 목록이 `--only-ads` 를 없애 '전량' 이 되는 길 |
| `test_대상은_규칙1_소재만` | BID-01 / D-06 / T-1-30 — ①2 + ③1 → 2건. 오염 시 거부 |
| `test_계정별_상한을_넘으면_거부한다` | D-08 / T-1-29 — 계정별이고 **설정을 따라온다** |
| `test_예상_인상액_합계` | BOARD-04 — 스킵 액션은 안 더한다 |
| `test_인상_0건이어도_집계를_보여준다` | Pitfall 6 / T-1-32 — counts 를 다시 세지 않는다 |
| `test_산출물이_빈_dict면_실패로_본다` | T-1-33 — 계정 하나만 `{}` 면 blind |
| `test_웹앱은_입찰가를_계산하지_않는다` | BID-02 / T-1-07 — 소스 패턴 0건 + `70 → 999` 함정 |
| `test_미리보기_표` | BID-03 / D-05 — 소재 줄 · bool 먼저 분기 |
| 라우트 2종 | 400/409/422 · 실행 플래그 부재 |
| `preview_cdp.sh` 31종 | 브라우저에서만 사는 계층 전부 |

## Decisions Made

- **헤더 체크박스 = 뷰포트, 필터 전체 = 배너.** 가상 DOM 에서 "보이는 것" 의 정직한 번역은 뷰포트다. 이 선택 덕분에 ①행 1,195건짜리 계정에서 두 수가 **반드시** 갈라지고, BOARD-03 이 화면에서 성립한다.
- **오염된 대상은 버리지 않고 거부한다.** 버리는 구현과 거부하는 구현은 성공 경로에서 **똑같이 초록**이다. 그래서 하네스가 에러 경로를 따로 친다(V-PRE-17a~d).
- **`preview_rows`/`total_rows` 를 flow.py 에 뒀다.** 표를 만드는 판단(정렬·잘림)을 템플릿에 두면 JSON 응답과 HTML 응답이 다른 표가 된다.
- **수동 검증을 CDP 로 옮겼다.** 01-06 의 SC-03 과 같은 판단이다 — 사람 눈으로는 "배너가 떴다" 까지밖에 못 보고, 취소가 실제로 선택을 되돌리는지는 **수를 세야** 안다.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] 선택 요약이 한 스텝 뒤처졌다**
- **Found during:** Task 4 (`preview_cdp.sh` V-PRE-07 이 잡았다)
- **Issue:** `dataFiltered` 핸들러 안에서 `table.getData("active")` 를 읽으면 **직전 필터의 집합**이 나온다(01-04 의 건수 배지와 같은 원인: `Filter.filter()` 가 결과를 만든 뒤 먼저 이벤트를 쏘고, 그 다음에 `RowManager` 가 `activeRows` 를 갈아끼운다). 여기서 나는 랙은 증상이 더 나쁘다 — 계정을 바꿔도 `그중 89개는 지금 필터 밖이다` 가 **안 뜬다.** 화면엔 새 계정만 보이는데 선택은 옛 계정에 남은 상태가 조용히 유지된다.
- **Fix:** 이벤트가 2번째 인자로 넘겨주는 갓 계산된 행 목록만 쓴다. 핸들러를 그대로 넘기지도 않는다 — `rowSelectionChanged` 의 첫 인자는 *선택된* 데이터라 자리가 다르다(그대로 넘기면 `필터 전체 N건` 링크가 영영 안 뜬다).
- **Files modified:** `webapp/static/board.js`
- **Verification:** 수정 전 V-PRE-07 FAIL → 수정 후 PASS (`상품 89개 선택 · … · 그중 89개는 지금 필터 밖이다`)
- **Committed in:** `6b416cb`

**2. [Rule 2 - Missing critical] `create_job` 의 빈 대상 목록이 '전량' 이 됐다**
- **Found during:** Task 2 (`V-SAFE-02c2` 가 `ad_ids: []` 를 쏘는 걸 보고)
- **Issue:** `if only_ads:` 라 빈 목록이면 targets 파일을 안 쓰고, 그러면 argv 에서 `--only-ads` 가 통째로 빠진다. CLI 의 `_load_only_ads` 는 `None` 을 **전량**으로 읽는다. 즉 "아무것도 안 골랐다" 가 조용히 "2,242건 전부" 가 된다. 보안 curl 한 줄이 4계정 전량 dry-run 을 돌리고 있었을 것이고, 같은 경로를 01-08 이 실행 플래그와 함께 재사용한다.
- **Fix:** `only_ads is not None` 으로 바꾸고 `target_count` 도 같이 고쳤다. 사유를 코드 주석에 남겼다.
- **Files modified:** `webapp/jobs.py`
- **Verification:** `test_대상이_0건이어도_전량으로_번지지_않는다` + 실측 — 빈 대상 잡의 산출물이 4계정 전부 `plans 0`. 음성 대조군(되돌리기)에서 FAIL 확인.
- **Committed in:** `bd4f3b2`

**3. [Rule 1 - Bug] 선택 컬럼 40px 이 가로 스크롤을 만들 뻔했다**
- **Found during:** Task 1
- **Issue:** 컬럼 최소 폭 합이 컨테이너를 넘으면 `board_cdp.sh` V-BOARD-07 이 빨개진다.
- **Fix:** 구매금액 105→95 · 광고비 100→95 · 상품ID 130→105 로 40px 을 벌었다. 실측 표 1448 / 컨테이너 1448.
- **Committed in:** `abc6e5c`

**4. [Rule 1 - 표기] 같은 수가 두 표기로 떴다** — `대상 1195건` 과 `1,195건 중 상위 200건` 이 한 화면에. 천 단위 구분으로 통일. `0b58f08`

### 계획과 달리 한 것

- **`_preview_table.html` 의 역할을 바꿨다.** 플랜은 board.html 이 이걸 include 하는 구조였는데, 라우트가 갈아끼우는 **조각**이어야 해서 바깥 `<section id="preview">` 셸을 board.html 로 옮겼다. 페이지 로드 때 지난 결과를 되살리지 않는다 — 새로고침했더니 예전 표가 떠 있으면 "지금 그 상태" 로 읽힌다(작업 패널을 running 만 싣는 것과 같은 이유).
- **라우트를 2개 더 만들었다** (`GET /jobs/{id}/panel`, `GET /jobs/{id}/result`). `fetch` 로 접수하면 htmx 조각을 못 받으므로 패널을 가져올 창이 필요했다. 둘 다 읽기 전용이고 `V-SAFE-01d` 스캐너 0건을 확인했다.
- **`collect_targets` 를 추가했다.** 플랜 인터페이스는 `collect_rule1_ads(rows, selected_keys)` 만 있었는데, 요청 모델이 `ad_ids` 를 받으므로 인바운드 검증이 따로 필요했다. `collect_rule1_ads(rows, None)`(= 전 상품의 ①소재)이 그 정답지고, `collect_targets` 는 그 밖의 adId 를 거부한다. 한 함수가 정본이고 다른 하나가 그걸 관문으로 쓴다.

### Deferred Issues

없음.

## Checkpoint — Task 3 (Skeleton A 실측 13단계)

**전 항목을 하네스로 대행 검증했고, 오케스트레이터가 독립적으로 재실행해 전부 통과했다.**

| 플랜 단계 | 대행 | 실측 |
|---|---|---|
| 1~2 헤더 체크박스 선택 요약 | V-PRE-03b/04 | 선택 15 · 계정 1개 · 요약이 상품/①소재를 가른다 |
| 3 보이는 것 vs 필터 전체 | V-PRE-03c/d · 05 | **선택 15 / 필터 전체 89 / 전체 2,637** · 링크 N=89 |
| 4 확인 배너 + 취소 | V-PRE-06a/b/c | 취소 전 15 → 취소 후 **15** · 확인 후 89 |
| 5 건수 타이핑 없음 | V-PRE-02 | 입력칸 **0개** |
| 6~7 미리보기 · 소재 단위 | V-PRE-08~11 | 접수→표 **0.38초**(1,195건 기준) |
| **8 그룹입찰 현재가** | **V-PRE-12a/b** | **`nad-…495390006` 70 → 80 · 그룹입찰따름 예** (50→60 아니다) |
| 9 집계 + 인상액 합계 | V-PRE-13 | `대상 1,195건 → 인상 1,195` · `+11,950원` |
| 10 두 번째 미리보기 동일 | V-PRE-15 | 결과 문자열 동일 · ledger/백업 mtime **8/30 불변** |
| 11 targets/preview 한 쌍 | 디스크 실측 | 잡 9개 → 9쌍 |
| 12 jobs 행이 경로를 묶는다 | sqlite 실측 | 전 행 `done` · `exit_code 0` · targets/result 경로 일치 |
| 13 ①0건 상품 | V-PRE-04 | `그중 규칙① 소재가 있는 건 0개 · 대상 0건 — …②③⑤ 소재는 인상 대상이 아니다` |

### 육안으로는 못 잡는 버그 2건을 이 단계에서 잡았다

둘 다 **화면 증상이 0** 이라 13단계 육안 확인을 100% 통과했을 것이다.

1. **헤더 체크박스가 필터를 무시하고 전체를 고른다.** `titleFormatterParams.rowRange` 를 안 주면 Tabulator 가 `selectRows(undefined) → rowManager.rows` 를 탄다(벤더 소스 실측). 음성 대조군: 화면엔 89줄만 보이는데 **2,637줄(계정 4개)** 선택 — 대상이 **9건 → 2,242건**. 고른 적 없는 계정의 입찰가가 올라간다.
2. **요약 줄의 한 스텝 랙** (위 Rule 1). 계정을 바꿔도 "필터 밖에 89개 골라 뒀다" 가 안 뜬다.

**잡은 방법:** 페이지를 **안에서** 조작하고(CDP `Runtime.evaluate`), 정답을 검증 대상(Tabulator)이 아니라 **페이지에 박힌 원본 JSON에서 직접 세서** 대조했다. 그리고 성공 경로만 보지 않고 **에러 경로**(오염된 adId → 400, 주입 시도 → 422)를 따로 쳤다 — 버리는 구현과 거부하는 구현은 성공 경로에서 구분이 안 되기 때문이다.

**음성 대조군 6종** 전부 FAIL 을 확인한 뒤 복원했다: 재계산 주입 / 빈 대상 전량 폴백 / 오염 대상 조용히 버리기 / 집계 줄 제거 / 계정 캐시 mtime 제거 / `rowRange` 제거.

### 사람 몫 4건 — 결정

| 항목 | 결정 | 근거 |
|---|---|---|
| 요약 줄 문구가 길다 | **그대로** | "왜 0건인지" 를 설명하는 정보가 다 필요하다 |
| 신선도 배너 소음 | **그대로** | 배너는 **문제가 있을 때만** 길어진다 — 신선 1줄 / 낡음 2줄 / 계정 빠짐 3줄. 소음이 아니라 신호에 비례한다(실측 확인) |
| OQ-7 경고색 | **안 넣는다** | 배너 본문이 이미 명시적으로 말한다. 색은 가치 대비 취향 영역 |
| 판정 안 된 회차 표시 | **Open Question 으로 이월** | 아래 참조 |

### 독립 재실행 (오케스트레이터)

```
pytest      130 passed      security_curl  9 PASS / 0 FAIL
board_cdp   19 PASS / 0     sse_cdp       12 PASS / 0 FAIL
preview_cdp 31 PASS / 0     CLI 회귀      6파일 전부 exit 0
```

## 디스크 상태 변화 (이 플랜 완료 시점)

체크포인트 중에 용팀장이 나머지 3계정 `prep` 을 돌렸고(cy7728 4,555 / ownway1 5,312 / pogeunae 4,055 소재 · 각 2분30초~3분, 전부 exit 0), 이어서 `run --run-dir 2026-09-20` 이 0.2초·네트워크 0 으로 돌았다.

내 코드가 그 상태를 그대로 처리한 실측:

```
scan_run_dirs()  ['2026-09-20', '2026-08-30', '2026-08-29']
드롭다운         2026-09-20 회차 · 계정 4개   ← 기본
                 2026-08-30 회차 · 계정 4개
                 2026-08-29 회차 · 계정 2개
배너             2026-09-20 회차 · 0일 전 · 통계 기간 2026-09-12~2026-09-18 · 계정 4개 (…)
                 → 경고 0줄 (신선하면 1줄로 줄어든다)
보드 행          3,660  (cy728 622 · cy7728 958 · ownway1 1068 · pogeunae 1012)
                 ①포함 상품 2,881 · ①소재 2,882
```

**"수집만 되고 판정 안 된 회차" 상태는 오늘 해소됐다.** `2026-09-20` 이 `result.json` 없이 드롭다운에서 빠져 있던 게 그 케이스였는데, `run` 이 돌면서 정상 편입됐다. 판정 없는 회차를 안 띄우는 판단(Pitfall 7 — 빈 보드는 "대상 없음" 으로 오독된다)은 그대로 유효하다.

전 하네스를 **새 디스크 상태에서 다시 돌려** 전부 green 인 것을 확인했다(board_cdp 가 이제 3,660행 보드를 본다).

## 관찰 (이 페이즈 범위 밖 — 판단하지 않는다)

- **`pogeunae` 의 ⑥삭제대상이 201건이다.** 같은 회차의 다른 계정은 cy728 16 · cy7728 6 · ownway1 39 로, pogeunae 혼자 5배다. 용팀장 메모리의 `naver-ads-interlock-mass-pause`(물갈이 20일 사이클의 부산물로 연동끊김 대량정지가 상시 발생 — 고장 아님)와 같은 패턴일 가능성이 있다. **이번 페이즈에서 손대지 않았고 원인도 규명하지 않았다.** 숫자만 남긴다.

## Open Questions

- **OQ-8 (신규): 수집만 되고 판정 안 된 회차를 화면이 알릴 것인가.** 보드에 "새로 수집" 버튼이 생겨서(D-15), 용팀장이 `prep` 만 누르고 `run` 을 안 누르면 그 회차가 드롭다운에서 조용히 사라진다 — 화면은 아무 말도 안 한다. 오늘은 `run` 을 돌려 해소됐지만 구조적으로 재발한다. 01-08 이 실행 흐름을 만들 때 자연스러운 자리가 생길 수 있다. **지금 고치지 않는다.**
- `elapsed_sec` 은 "끝난 시각" 이 아니라 "누가 상태를 물어본 시각" 까지를 잰다(게으른 `_reap` 의 부수효과). 화면은 0.4초마다 폴링해서 실사용엔 영향이 없지만, 아무도 안 보는 잡의 소요시간은 부풀어 보인다. 실측: 실제 0.4초짜리 잡이 14초로 기록된 적 있다.

## Known Stubs

없음. 이 플랜이 만든 화면 요소는 전부 실데이터와 연결돼 있다. `실행` 버튼은 **의도적으로 만들지 않았다** — 미리보기까지가 이 플랜의 범위이고(PROJECT.md 의 dry-run 선행 제약), 01-08 이 그 위에 한 줄을 얹는다.

## Threat Flags

없음. 새로 생긴 표면(`POST /jobs/bids/preview` · `GET /jobs/{id}/panel|result`)은 전부 플랜 `<threat_model>` 의 T-1-06/07/29/30/31/32/33 안에 있고, 각각 mitigate 로 처리됐다.

## Self-Check: PASSED

- 산출물 6개 전부 디스크에 존재 (`flow.py` · `_preview_table.html` · `test_flow.py` · `preview_cdp.sh` · `preview_cdp.mjs` · 이 파일)
- 커밋 8개 전부 git 에 존재 (abc6e5c · a3ff6c7 · bd4f3b2 · c357758 · 6b416cb · 313bbd2 · 0b58f08 · f3be3fd)
