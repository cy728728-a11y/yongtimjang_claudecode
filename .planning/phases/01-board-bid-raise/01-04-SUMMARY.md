---
phase: 01-board-bid-raise
plan: 04
subsystem: ui
tags: [tabulator, jinja2, fastapi, gzip, cdp, headless-chrome, board-projection]

# Dependency graph
requires:
  - phase: 01-01
    provides: "paths.scan_run_dirs()/run_dir_path()/freshness() · settings.STALE_DAYS · conftest 의 fake_result_json 픽스처(가짜 5번째 계정 zzfake 포함) · no_commit_guard.sh"
  - phase: 01-03
    provides: "앱 셸(main.py · GZipMiddleware · TrustedHost · security.guard) · 토큰/쿠키 게이트가 붙은 GET / · board.html 셸 · security_curl.sh"
provides:
  - "webapp/board.py — result.json → 상품 단위 행 투영(fold_products/account_list/rule_list). 읽기 전용 순수 함수"
  - "GET / 가 실데이터 2,637행 보드를 렌더한다 (계정·규칙·상품명 필터, 열 정렬, 회차 드롭다운)"
  - "신선도 배너 — 회차 날짜 · 경과일 · 실제 통계기간 3종 + stale 경고색 (D-16)"
  - "webapp/static/board.js — Tabulator 6.5.3 초기화, 컬럼 정의를 데이터 구조로"
  - "브라우저 JS 검증 계층 webapp/tests/board_cdp.{sh,mjs} — 헤드리스 크롬 + CDP"
  - "템플릿 컨텍스트 계약: request · token · run_dirs · run_dir · freshness · accounts · rules · rows · load_error"
affects: [01-06 선택 UI, 01-07 미리보기·대상 확정, 01-08 실행 결과 투영, Phase 3 상세페이지 판정 보드]

# Tech tracking
tech-stack:
  added: []          # 신규 의존성 0 — 01-01 이 vendoring 한 Tabulator/Pico/htmx 만 쓴다
  patterns:
    - "산출물 투영(세 번째 길): 보드 데이터는 CLI 실행도 CLI import 도 아니고 run-dir JSON 읽기"
    - "2단계 접기: (계정,adId) dedupe → (계정,mallProductId) 접기. 규칙 중복 계상 차단"
    - "데이터를 script type=application/json + tojson 으로 내보내기 (자동 이스케이프 유지)"
    - "브라우저 JS 는 pytest 밖 통합 계층(security_curl.sh 와 동급)에서 검증"

key-files:
  created:
    - webapp/board.py
    - webapp/static/board.js
    - webapp/tests/test_board.py
    - webapp/tests/board_cdp.sh
    - webapp/tests/board_cdp.mjs
  modified:
    - webapp/routes/board.py
    - webapp/templates/board.html
    - .planning/phases/01-board-bid-raise/01-VALIDATION.md

key-decisions:
  - "보드 데이터를 인라인 script type=application/json + tojson 으로 내보낸다 (별도 /board-data 라우트 대신) — 요청 1번이라 배너와 표가 절대 어긋나지 않고, tojson 이 < > & ' 를 \\uXXXX 로 바꿔 상품명 XSS 가 구조적으로 불가능하다"
  - "템플릿 컨텍스트 키를 rows_json(문자열) 대신 rows(리스트)로 바꿨다 — 문자열을 script 안에 넣으려면 자동 이스케이프를 꺼야 하는데 그게 T-1-17 방어를 무너뜨린다"
  - "dataFiltered 안에서 getDataCount('active') 를 읽지 않는다 — Tabulator 가 activeRows 를 커밋하기 전에 이벤트를 쏘므로 배지가 한 스텝 뒤처진다. 이벤트의 2번째 인자만 믿는다"
  - "상품명 줄바꿈(variableHeight)을 버리고 tooltip + 폭 재배분을 택했다 — 2,637행 보드에서 행 높이가 2~3배가 되면 훑는 용도가 죽는다"
  - "브라우저 JS 회귀는 pytest 로 흉내 내지 않는다. 가짜 Tabulator 를 검증하는 초록 테스트보다 정직한 공백 + CDP 통합 스크립트가 낫다"

patterns-established:
  - "BOARD-02 가드: 런타임 파일(board.py/routes/board.py/board.html/board.js)에 계정 alias 리터럴 0건을 테스트가 기계로 집행한다. 주석도 예외 없다"
  - "빈 값은 0 이 아니라 None/빈칸이다 — '노출 0 이었다'는 판정과 '통계에 행이 없다'를 화면에서 구분한다"
  - "검증 수단은 통과만 시키지 말고 버그 버전으로 되돌려 FAIL 을 확인한다 (뽑아놔도 통과하는 검증 금지)"

requirements-completed: [BOARD-01, BOARD-02]

# Metrics
duration: 32min
completed: 2026-09-20
---

# Phase 1 Plan 04: 상품 단위 보드 Summary

**판정 2,726행을 (계정, 상품) 2,637줄로 접어 브라우저에 띄웠다 — 계정·규칙·상품명으로 거르고 정렬되며, 21일 묵은 회차라는 사실이 경고색으로 상단에 박힌다.**

## Performance

- **Duration:** 32분
- **Started:** 2026-09-20 17:03 KST
- **Completed:** 2026-09-20 17:35 KST
- **Tasks:** 2/2 자동 태스크 + 체크포인트 1건(오케스트레이터 대행)
- **Files modified:** 8 (신규 5 · 수정 3)

## Accomplishments

### Task 1 — `webapp/board.py` 상품 단위 접기 (TDD)

`3da4d39` RED(테스트 9종) → `d9767de` GREEN.

핵심은 **2단계**다. RESEARCH 의 Pattern 2 는 규칙을 순회하며 지표를 더하는데, PATTERNS §C-2 가 지적한 대로 그러면 같은 소재가 ②와 ③에 동시에 들어가 **노출·클릭·광고비가 정확히 2배**가 된다. 그래서 규칙을 돌기 전에 `(계정, adId)` 로 소재를 먼저 dedupe 하고, 그 다음에 상품으로 접는다. `report_md.py:59` 의 경고를 주석에 그대로 인용해 뒀다.

`ctr` 은 합산하지 않고 `clk/imp*100` 으로 다시 낸다 — 비율을 더하면 0.23 + 0.23 = 0.46 이라는 거짓말이 된다. 분모가 없으면 `0` 이 아니라 `None` 이다.

실데이터 스모크가 플랜의 사전 실측치와 **정확히** 일치했다:

| 항목 | 기대 | 실측 |
|---|---|---|
| 접힌 행 수 | 2,637 근처 | **2,637** |
| ①소재 합계 | 2,242 | **2,242** |
| 계정별 ①소재 | cy728 9 · cy7728 10 · ownway1 1,195 · pogeunae 1,028 | **동일** |

### Task 2 — GET / 데이터 연결 + Tabulator (`70ae4ce`)

- `run_dir` 쿼리는 `paths.run_dir_path()` 화이트리스트만 통과한다. `../../etc` → 400, `nope` → 400, 실재 회차 → 200 (T-1-11)
- `result.json` 읽기 실패는 **폴백하지 않는다**. 다른 회차로 몰래 갈아타지 않고 사유를 화면에 띄운다
- 회차가 0개면 빈 표 대신 "먼저 수집해라" 안내를 낸다 — 빈 표는 "대상이 없다"로 오독된다
- 필터 옵션(계정·규칙)은 전부 서버가 넘긴 목록으로만 렌더. 계정 alias 리터럴 **런타임 파일 4개 전부 0건**
- 컬럼 정의를 `sheets_out.py:28-48` 관례대로 데이터 구조로 뒀다. `null` → 빈칸, bool 을 int 보다 먼저 분기해 `예`/`아니오`, `cost` 헤더는 **광고비**

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] 건수 배지가 필터보다 한 스텝 뒤처짐**
- **Found during:** 체크포인트 검증(오케스트레이터가 헤드리스 크롬으로 대행)
- **Issue:** Tabulator 의 `Filter.filter()` 는 필터 결과를 만든 뒤 **먼저** `dataFiltered` 를 쏘고, 그 다음에 `RowManager.refreshActiveData` 가 `activeRows` 를 갈아끼운다. 핸들러 안에서 `getDataCount("active")` 를 읽으면 아직 **직전 필터의 집합**이다. 계정 필터·규칙 필터·상품명 검색·초기화 버튼이 전부 같은 증상이었다.
- **Fix:** 이벤트의 2번째 인자(갓 계산된 행 목록)만 쓴다. 커밋되지 않은 내부 상태를 뒤지지 않는다. 최초 1회만 `tableBuilt` 에서 `getDataCount` 를 읽는다(그 시점엔 필터가 진행 중이 아니다).
- **Files modified:** `webapp/static/board.js`
- **Commit:** `79ba992`

**2. [Rule 2 - 누락된 검증 수단] 브라우저 JS 계층에 검증이 없었다**
- **Issue:** 위 버그를 자동 스위트가 하나도 못 잡았다. `TestClient` 는 JS 를 한 줄도 실행하지 않는다.
- **Fix:** `webapp/tests/board_cdp.{sh,mjs}` 신설 — 헤드리스 크롬 + CDP 로 실제 JS 를 돌린다. `security_curl.sh` 와 **같은 계층**(살아 있는 서버 대상, pytest 밖)이다. 정답은 Tabulator 에게 묻지 않고 페이지에 박힌 원본 JSON 에서 직접 센다.
- **Commit:** `79ba992`

**3. [Rule 1 - Bug] 내 BOARD-02 가드가 나를 잡음**
- **Issue:** 버그 설명 주석에 계정 alias 를 예시로 적었다가 `test_계정을_코드에_박지_않는다` 가 FAIL.
- **Fix:** 주석에서 alias 제거. 가드가 맞다 — 주석의 예시가 내일의 복붙 리터럴이 된다.
- **Commit:** `79ba992`

### Interface 계약 변경 (문서화 필요)

플랜의 `<interfaces>` 는 템플릿 컨텍스트에 `rows_json`(= `json.dumps` 한 **문자열**)을 넘기라고 적었다. **`rows`(리스트)로 바꿨다.**

이유: 문자열을 `<script>` 안에 넣으려면 Jinja2 자동 이스케이프를 꺼야 한다. 그런데 자동 이스케이프가 걸린 채로는 `"` 가 `&#34;` 가 되어 `JSON.parse` 가 깨지고, 끄면 T-1-17(상품명 XSS) 방어가 무너진다. `tojson` 은 리스트를 받아 `< > & '` 를 `\uXXXX` 로 바꿔 주므로 **둘 다** 해결된다.

**Plan 01-06/01-07 이 이 컨텍스트에 올라탈 때 키 이름이 `rows` 인 것을 전제해라.**

### 레이아웃 판단 (오케스트레이터가 넘긴 건)

상품명 260px 에서 38/40 셀이 잘리고 표 폭 1,520 > 컨테이너 1,448 로 가로 스크롤이 났다.

**선택:** 숫자 열 폭을 깎아 스크롤을 없애고(1,448 = 1,448), 상품명을 260 → 297px 로 넓히고, **상품명·상품ID 에 `tooltip: true`** 를 달았다. 잘림 38/40 → **28/40**, 나머지 11열 잘림 0.

**버린 것:** 줄바꿈(`variableHeight`). 2,637행 보드에서 행 높이가 2~3배가 되면 한 화면에 7~8줄밖에 안 들어와 "훑어서 고른다"는 용도 자체가 죽는다. 상품명 전문이 상시 필요해지는 건 상세페이지 판정(Phase 3)이고, 그때는 목록이 아니라 상세 패널이 맡을 일이다.

## Checkpoint — 실데이터 육안 확인 (오케스트레이터 대행)

**(a) 대행 방식.** 크롬 확장은 못 붙었지만 `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome` 을 `--headless --remote-debugging-port=9222` 로 띄워 DOM 덤프 · 스크린샷 · CDP `Runtime.evaluate` 조작까지 **실제로** 했다. 사람 눈 대신 기계가 봤다.

대행 결과 PASS 8건: Tabulator 렌더(`tabulator-cell` 260 = 20행 × 13열, 가상 DOM 동작) · 배지 초기값 2,637(= board.js 가 실행된 증거, HTML 소스엔 `0` 이 박혀 있다) · 정렬(`imp` asc 47 / desc 82,487) · 컬럼 13개 · 필터 옵션이 데이터에서 나옴 · 필터링 자체는 정확 · 주소창에 토큰 없음(303+쿠키 실제 브라우저 확인) · 배너 앰버 배경 + 붉은 좌측 보더.

**(b) FAIL 1건 → `79ba992` 로 닫힘.** 건수 배지 한 스텝 랙(위 Deviation 1). 수정 후 재검증은 내가 같은 방식으로 다시 돌렸다:

```
             정답    배지    내부
cy728          89 |    89 |    89   PASS
cy7728         55 |    55 |    55   PASS
ownway1      1272 |  1272 |  1272   PASS
pogeunae     1221 |  1221 |  1221   PASS
규칙 ①~⑥    2241/198/78/138/38/32  전부 PASS
검색 카트/전정기/없는단어  78/3/0   전부 PASS
초기화 → 2637                       PASS
렌더된 셀 520개 undefined·NaN 0건   PASS
표 1448 ≤ 컨테이너 1448             PASS
```

**커밋된 버그 버전으로 되돌려 돌려 FAIL 이 나는 것을 확인했다** — 뽑아놔도 통과하는 검증이 아니다:

```
cy728      정답    89 | 배지  2637          ← 초기값 그대로
cy7728     정답    55 | 배지    89   ← 직전 값이다
ownway1    정답  1272 | 배지    55   ← 직전 값이다
pogeunae   정답  1221 | 배지  1272   ← 직전 값이다
```

**(c) 교훈 — "숫자가 움직인다"를 PASS 근거로 쓰지 마라.**

이 버그는 육안 확인으로 **절대 안 잡혔을 것이다.** 필터를 바꾸면 숫자가 *움직이긴* 하고, 플랜의 확인 문구도 "앞 숫자가 필터에 따라 움직이는지"였다. 사람이 보면 PASS 를 준다. **두 번 연속 바꿔 직전 값과 대조해야만** 드러난다.

그리고 이 배지는 장식이 아니다. Plan 01-07 의 "몇 건에 입찰가를 올릴 건가"라는 규모 감각이 여기서 나오고, D-08(계정별 1,500건 상한)이 존재하는 이유가 그 규모를 묶는 것이며, 그건 **실제 광고비**다.

→ 남은 체크포인트(BOARD-03 보이는 선택 vs 필터 전체, FLOW-04 확인 배너)에도 같은 함정이 있다. "숫자가 다르다"가 아니라 **"숫자가 정확히 얼마여야 한다"** 를 확인 문구로 써라. `01-VALIDATION.md` Manual-Only 표에 이 항목을 `~~시각 확인~~ → 육안으로는 못 잡는다` 로 명문화하고 `board_cdp.sh` 로 옮겼다.

## Verification 편차 — 5번 단계 "전부 빈칸"은 사실이 아니다

플랜의 `how-to-verify` 5번이 "규칙 ① 필터 → 노출·클릭·CTR 열이 **전부** 빈칸"이라고 적었는데, 실측은 **2,241줄 중 2,229줄만 빈칸이고 12줄엔 숫자가 있다.**

버그가 아니라 D-05(한 줄 = 상품) + D-04(6규칙 전부 싣기)의 당연한 귀결이다. 같은 상품에 ①소재와 ②③④소재가 같이 있으면 한 줄로 접히면서 `rules` 가 `①②` 가 되고 지표는 ②소재 것이 실린다. 실제 12줄: `①②`×2, `①③`, `①③④`, `①④`×2, `①②`×2, `①⑤`, `①②`×3 (계정 4개에 걸쳐 분포).

**판정 기준은 "빈칸이 아닌 줄이 있으면 실패"가 아니라 "`undefined`/`NaN` 이 한 칸이라도 보이면 실패"다.** 후자는 기계로 23,733셀(정적) + 520셀(실제 렌더) 전부 확인했고 0건이다.

## 실측 수치

| 항목 | 값 |
|---|---|
| 접힌 행 | 2,637 (①만 2,229 · ①겸침 12 · ②198 · ③78 · ④138 · ⑤38 · ⑥32) |
| HTML 원본 | 909KB |
| gzip 응답 | **114KB** (`curl -H 'Accept-Encoding: gzip'` 실측 116,948 bytes) — 기준 200KB 미만 |
| 신선도 | `2026-08-30 회차 · 21일 전 · 통계 기간 2026-08-22~2026-08-28`, `class="stale"` |
| CDN URL | 0건 |
| 계정 alias 리터럴 (런타임 4파일) | 0건 |
| 가로 스크롤 | 없음 (표 1,448 = 컨테이너 1,448) |

## Verification Results

| 검증 | 결과 |
|---|---|
| `.venv-web/bin/pytest webapp/tests -q` | **50 passed** |
| `bash webapp/tests/no_commit_guard.sh` | exit 0 |
| CLI 회귀 6파일 | **100 tests 전부 exit 0** (7+7+21+21+28+16) |
| `CT_DEV_TOKEN=… bash webapp/tests/security_curl.sh` | **8/8 PASS** |
| `CT_DEV_TOKEN=… bash webapp/tests/board_cdp.sh` | **전량 PASS** (V-BOARD-00~08) |
| `! grep -q '매출' webapp/static/board.js` | 0건 |
| 실데이터 스모크 (2,637 / 2,242) | 기대치 일치 |

## Known Stubs

없다. 보드는 실데이터로 끝까지 돈다.

선택(체크박스) 컬럼과 실행 버튼이 **의도적으로** 없다 — Plan 01-06/01-07 이 "보이는 것만 vs 필터 전체"(BOARD-03/D-07) 확인 배너와 **같이** 붙인다. 지금 넣으면 확인 배너 없는 전체 선택이 먼저 생긴다(플랜 Task 2 명시).

## Threat Flags

없다. 이 플랜은 읽기 전용이고 새 네트워크 엔드포인트·인증 경로·스키마 변경이 없다. `GET /?run_dir=` 은 `<threat_model>` 의 T-1-11 이 이미 다루고 있고 화이트리스트로 막혔다.

## Self-Check: PASSED

- `webapp/board.py` FOUND · `webapp/static/board.js` FOUND · `webapp/tests/test_board.py` FOUND · `webapp/tests/board_cdp.sh` FOUND · `webapp/tests/board_cdp.mjs` FOUND
- `3da4d39` FOUND · `d9767de` FOUND · `70ae4ce` FOUND · `79ba992` FOUND
