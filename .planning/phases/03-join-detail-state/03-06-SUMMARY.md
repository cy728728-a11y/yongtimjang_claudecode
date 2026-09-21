---
phase: 03-join-detail-state
plan: 06
subsystem: board-ui-join
tags: [join-01, join-02, join-03, state-03, state-05, pitfall-3, tabulator, cdp]

# Dependency graph
requires:
  - phase: 01-board-bid-raise
    provides: "board.fold_products · board.js columns/필터적용/선택요약 · board.html 배너·필터 관용구 · board_cdp.sh 하네스"
  - phase: 03-join-detail-state
    plan: 02
    provides: "join.attach · resolution · cleanup_groups · selectable · 사유코드 5종 · 버킷 2종"
  - phase: 03-join-detail-state
    plan: 03
    provides: "bulsaja_index.group_health(완결) · jobs.latest_done"
  - phase: 03-join-detail-state
    plan: 05
    provides: "실회차 해상률 92/194 · 인덱스 30그룹 · `미조회가 미스로 보인다` 숙제"
provides:
  - "routes/board.py `_load_join()` — 마지막 성공 스캔 산출물 읽기 (레지스트리가 정본 · 폴백 없음)"
  - "routes/board.py `_인덱스표시()` — group_health 로 `미스` 를 갈라 `인덱스 불완전` 으로 띄운다"
  - "ctx 6키: index_error · join_at · resolution · index_health · cleanup · filters"
  - "board.html `.system-warn` — 광고청소(.stale)와 **다른 클래스**의 시스템 배너"
  - "board.html `#cleanup` — 광고그룹 단위 청소 표 (원문·번호·사유·행수·계정)"
  - "board.html `#f-state` · `#f-join` 필터 · `.ct-done` 기작업 회색"
  - "board.js 컬럼 4종(상세·기작업·사본·해소) · formatter 3종 · rowFormatter · 전체선택 기작업 제외"
  - "board_cdp.mjs V-BOARD-09~22 (신규 14검사) + SKIP 보고 체계"
  - "webapp/tests/fixtures/render_check.py — 실렌더 1회 확인 스크립트"
  - "test_board.py 계정 리터럴 가드를 **트리 전체 훑기**로 교체 (명시 목록 폐기)"
affects: [03-07-실탄, phase-05-detail-page]

# Tech tracking
tech-stack:
  added: []   # 새 외부 패키지 0건
  patterns:
    - "판정 코드와 화면 이름을 분리한다 — 코드는 데이터에 남고 화면엔 사람 말이 뜬다"
    - "사유 이름 자체가 버킷을 말하게 짓는다 (`번호…`=광고 / `인덱스…`=시스템) — 기호·색에 기대지 않는다"
    - "라벨만 고치지 말고 **사유 문장도** 같이 고친다 — 툴팁에 틀린 말이 남는다"
    - "리터럴 가드는 명시 목록이 아니라 트리 전체를 훑는다 — 목록은 사람이 기억해야 작동한다"
    - "Tabulator `fitColumns` 에서 `widthShrink` 는 고정폭 합이 이미 컨테이너 안일 때만 뜻이 있다"
    - "SKIP 을 초록으로 세지 않는다 — 재료가 없어 못 본 검사는 그렇게 보고한다"

key-files:
  created:
    - webapp/tests/fixtures/render_check.py
  modified:
    - webapp/routes/board.py
    - webapp/templates/board.html
    - webapp/static/board.js
    - webapp/tests/board_cdp.mjs
    - webapp/tests/test_board.py
    - webapp/paths.py
    - webapp/flow.py

key-decisions:
  - "`미스` 재라벨을 **라우트 층**에서 했다 — `join.py` 의 사유코드·버킷은 한 글자도 안 바꿨다. 판정의 정본은 거기 하나고, `재검증판정` 을 고치면 인덱스가 찬 뒤의 정상 `미스` 판정이 흐려진다"
  - "해소 컬럼의 field 를 `사유코드` 가 아니라 `표시사유` 로 잡았다 (플랜 interfaces 에서 이탈). `사유코드` 를 그리면 `미스` 가 그대로 화면에 뜬다"
  - "`사유코드`·`상품조회` 를 브라우저 payload 에서 **지우지는 않았다** — 기계의 판정 기록이고 소스 보기로 되짚는 통로다. 요구는 '사람이 읽는 자리에 0건' 이므로 검사를 마크업으로 한정했다"
  - "계정 alias 가드를 명시 목록 → 트리 전체로 바꿨다. 바꾸자마자 `paths.py`·`flow.py` 주석의 실제 alias 2건이 잡혔다 — 목록 방식이 있는 척만 하고 있었다는 증거"
  - "`widthShrink` 를 버리고 고정폭 예산으로 갔다. shrink 는 실측에서 표를 **더 넓게**(2,022) 만들었고, 벤더 소스를 읽어 원인을 확인했다"
  - "CDP 실서버 검증을 실데이터가 아니라 **익명화 픽스처 + 격리 data_root** 로 돌렸다 — 크레딧 0, 실회차 오염 0, 그리고 ⚪🟡🔴·기작업·미스가 전부 들어 있는 유일한 입력이다"

patterns-established:
  - "네거티브 대조 4건을 전부 실제로 봤다 (앞 플랜들의 규율 승계)"
  - "화면 검증은 pytest(HTML 문자열) → render_check(실렌더) → CDP(진짜 브라우저) 3층으로 쌓는다"

requirements-completed: [JOIN-01, JOIN-02, JOIN-03, STATE-03, STATE-05]

# Metrics
duration: 62min
completed: 2026-09-21
---

# Phase 3 Plan 06: 보드에 상태·해상률·청소 목록을 띄운다 Summary

**보드 한 줄에 ⚪🟡🔴 상세 상태가 뜨고, 🔴만 남기는 필터가 실제로 행을 줄이고, 해상률이
광고 청소(빨강 `.stale`)와 시스템 사정(파랑 `.system-warn`) **두 개의 다르게 생긴 배너**로
갈려서 뜬다. 그리고 03-05 가 넘긴 숙제 — 인덱스를 한 번도 안 훑은 행이 `미스`("그룹에 이
상품이 없다")로 보이던 것 — 을 `group_health` 로 갈라 "인덱스 불완전" 으로 고쳤다.**

## Performance

- **Duration:** 약 62분
- **Tasks:** 3 / 3
- **Tests:** 319 → **327 passed** (신규 8) + CDP 신규 14검사
- **Files:** 신규 1 · 수정 7
- **크레딧 소모:** **0** (불사자 MCP 접촉 0회 · 전부 익명화 픽스처)

---

## 🔴 이 플랜의 한 문장

**화면이 두 종류의 미해소를 섞지 않는다.**

섞이면 용팀장이 멀쩡한 광고그룹을 지우러 간다. 되돌릴 수 없고, 이 페이즈 최대 오진이다.
그래서 세 층에서 갈라 뒀다:

| 층 | 무엇이 갈리나 |
|---|---|
| 배너 | `#resolution-ads`(`.stale`, 빨강) vs `#resolution-system`(`.system-warn`, 파랑·점선·기울임) — **다른 DOM · 다른 클래스** |
| 셀 | `🛠 번호 추출 실패` vs `⚙ 인덱스 불완전` — **이름 자체가** `번호…`/`인덱스…` 로 갈린다 |
| 목록 | `#cleanup` 표에는 `버킷 == 광고청소` 인 그룹만 들어간다. 시스템 사정은 구조적으로 못 샌다 |

세 번째 줄이 중요하다. 색과 기호는 흑백 출력·색맹에서 죽는다. **글자가 구분을 지고 있다.**

---

## 🔴 03-05 가 넘긴 숙제 — 처리 완료

03-05 가 적어 둔 그대로다: 스캔 후·인덱스 전 상태에서 시스템 버킷이
`미조회 8 · **미스 84**` 로 갈린다. `init_db()` 가 빈 `ss_index` 를 만들어 두므로 스캔이
`인덱스있음=True` 로 적고, `재검증판정(None, None, False)` 이 `미스` 를 낸다.

**고친 방법 — `webapp/routes/board.py` 의 `_인덱스표시()`:**

1. `사유코드 == 미스` 인 행이 가리키는 **그룹만** 골라 `bulsaja_index.group_health()` 에 묻는다
   (전 그룹을 묻는 질의로 키우지 않는다)
2. `완결` 이 거짓이면 `표시사유 = "인덱스 불완전"`, 참이면 `"인덱스에 없음"`
3. **사유 문장도 같이 고친다.** 원래 문장("마켓그룹은 좁혀졌는데 그 안에 이 상품이 없다")은
   그 행에 대해 **사실이 아니다**. 라벨만 바꾸면 툴팁에 틀린 말이 그대로 남는다
4. 인덱스를 못 읽으면 `완결` 을 거짓으로 본다 (fail-closed) — "모른다" 를 "다 훑었다" 로
   접으면 화면이 없는 확신을 만든다

**`join.py` 는 한 글자도 안 바꿨다.** 사유코드도 버킷도 그대로다. 판정의 정본은 거기 하나고,
`재검증판정` 의 ②번 규칙을 손대면 인덱스가 찬 뒤의 **정상** `미스` 판정이 흐려진다.
여기서 바뀌는 것은 사람이 읽는 글자뿐이다 (화이트리스트 투영과 같은 성질).

**검증:** `test_미조회가_미스로_보이지_않는다` + CDP `V-BOARD-22`(화면 글자 0건)
+ `render_check.py`(마크업 0건).

---

## 무엇이 생겼나

### Task 1 — 조인 부착 · 배너 2종 · 청소 목록 (`5a9d8f4`)

**`routes/board.py`**

| 추가 | 하는 일 |
|---|---|
| `_load_join(run_dir)` | `jobs.latest_done("bulsaja_scan", run_dir)` → `result_path` 읽기. **폴백 없음** |
| `_인덱스표시(rows, join_doc)` | 위 §숙제. 집계(`불완전`/`그룹`/`미보유`/`불일치`/`그룹에없음`) 반환 |
| ctx 6키 | `index_error` · `join_at` · `resolution` · `index_health` · `cleanup` · `filters` |

`_load_join` 의 빈값이 `{}` 가 아니라 **`None`** 인 것이 이 파일에서 제일 중요한 한 글자다.
`{}` 를 주면 "마켓그룹 목록이 비었다" 가 되어 전 행이 **광고 청소 대상**으로 둔갑한다.
네거티브 대조에서 실제로 `광고청소 9/9` 가 나왔다 — Pitfall 3 의 실물이다.

`index_error` 는 `load_error` 와 **다른 키**다. 판정 결과를 못 읽으면 회차를 다시 뽑고,
조인 산출물을 못 읽으면 조인 스캔을 다시 돌린다. 사용자가 할 일이 다르다.

**스캔을 한 번도 안 돌린 것은 실패가 아니다** — 사유 없이 `(None, None, None)` 이고,
배너가 "아직 조인 스캔을 안 돌렸다" 를 말한다. 사유를 채우면 고장으로 읽힌다.

**`board.fold_products` 는 고치지 않았다.** 그 모듈이 "네트워크도 크레딧도 0" 인 계약을
지키게 두고, 조인은 그 위에 얹는 층이다.

**`board.html`** — `.system-warn` 신설(테두리 점선·위치·기울임까지 `.stale` 과 다르다) ·
`#cleanup` 그룹 단위 표 · `#f-state`/`#f-join` 필터 · `.ct-done` 회색 · 회색의 뜻을 적은 한 줄 안내.
광고그룹명에 `|safe` 0건.

**`webapp/tests/fixtures/render_check.py`** — 격리 tmp 에 회차·조인 산출물·성공 스캔 잡을
깔고 `GET /` 를 한 번 그려 본다. 데이터 블록을 덜어 낸 **마크업**에서 `미스` 를 센다.

### Task 2 — 보드 열 4종 · 필터 2종 · 기작업 제외 (`a6be928`)

formatter 3종을 기존 3종 **옆에** 더했다. 규율을 그대로 지켰다:
`빈칸이면()` 가드 통과 · 미판정은 **빈칸**(🔴로 대체하지 않는다, T-3-35) ·
기호만 내지 않고 **글자를 같이** 낸다.

필터는 기존 `필터적용()` **같은 함수 안**에 합쳤다 — `table.setFilter` 호출은 여전히 1개다.

**전체 선택에서 기작업 제외** (D-08 / STATE-05). 링크 표시 기준을 `활성.length > 고른것.length`
에서 **"아직 안 고른 후보 수"** 로 바꿨다 — 안 바꾸면 기작업 행이 남아 있는 한 링크가
영영 안 사라지고 눌러도 아무 일이 안 생긴다. (플랜에 없던 버그를 미리 막은 것)

헤더 체크박스(`rowRange: "visible"`)는 **건드리지 않았다.** 눈으로 보고 직접 고르는 경로는
그대로 열려 있어야 한다.

### Task 3 — CDP 하네스 14검사 (`498f9ba`)

| ID | 검사 |
|---|---|
| V-BOARD-09/10/11 | 헤더 4열 · 판정값 셀은 전부 기호+글자 · 미판정은 빈칸 |
| V-BOARD-12 | 상태 필터 **연속 전환** (배지 한 스텝 랙 탐지) |
| V-BOARD-13/14 | 필터 2종 동시 적용 → 하나만 풀면 나머지만 남는다 (합쳐진 함수의 증거) |
| V-BOARD-15/16/17 | 기작업 회색 · 전체선택 = 전체-기작업 · **손으로 체크하면 들어간다** |
| V-BOARD-18/19 | 배너 2종이 다른 DOM · 다른 className |
| V-BOARD-20/21 | 청소 표 렌더 · 셀이 원본 `adGroups` 값과 **정확히 일치** |
| V-BOARD-22 | 화면 글자에 `미스` 0건 |

정답은 여기서도 **원본 JSON**에서 직접 센다 — Tabulator 에게 묻지 않는다.
`SKIP` 체계를 더했다: 재료가 없어 못 본 검사는 그렇게 보고되고 **초록으로 세지 않는다**.

---

## Deviations from Plan

### 1. [Rule 1 - Bug] 컬럼 4개가 가로 스크롤 회귀를 만들었다 (V-BOARD-07)

- **Found during:** Task 3, 실서버 CDP 첫 실행
- **Issue:** 기존 검사 `V-BOARD-07`("표가 컨테이너 안에 들어온다")이 **FAIL** 로 돌았다 —
  표 1,775 / 컨테이너 1,448. 내가 더한 4컬럼(110+100+70+145=425px)이 원인이다.
- **첫 수정이 틀렸다:** `widthShrink: 1` 을 켜면 `fitColumns` 가 비율로 거둬 갈 줄 알았는데
  **2,022 로 더 넓어졌다.** 벤더 소스(`tabulator-6.5.3.min.js` 의 `fitColumns`)를 읽어 원인을 확인:
    · 고정폭 합 `n` 이 컨테이너 `o` 보다 크면 잔여 `r = o - n` 이 **음수**
    · grow 컬럼(상품명)은 `minWidth` 아래로 못 내려가 그 음수를 못 흡수
    · 남은 음수 `c` 가 `h[h.length-1].width -= c` 로 **마지막 shrink 컬럼에 더해진다**
      → 상품ID 가 105 → **392** 로 부풀었다 (CDP 로 컬럼별 폭을 실측해 확인)
- **Fix:** `widthShrink` 를 전부 걷어내고 **고정폭 예산**(1,270 + 상품명 minWidth 130 = 1,400
  ≤ 1,448)으로 맞췄다. 숫자 열을 한 번 더 깎았다 — 세 자리 콤마 숫자는 72px 에 들어간다.
  왜 shrink 가 안 되는지를 주석에 남겼다(다음 사람이 같은 수를 둘 것이 뻔하다).
- **Verification:** `V-BOARD-07` → **PASS · 표 1448 / 컨테이너 1448**
- **Files:** `webapp/static/board.js`
- **Commit:** `498f9ba`

### 2. [Rule 2 - 가드 무력화] 계정 리터럴 가드가 있는 척만 하고 있었다

- **Found during:** Task 1
- **Issue:** 플랜의 하드 제약이 "새 런타임 파일을 `런타임_파일들` 에 등록해라" 였다.
  그런데 **등록을 사람이 기억해야 작동하는 가드**는 가드가 아니다.
  `test_paths.py` 의 `_런타임_파일들()` 은 이미 트리 전체를 훑고 있었는데,
  `test_board.py` 만 파일 7개짜리 명시 목록이었다.
- **Fix:** 같은 제외 규칙(`settings.py` · `tests` · `vendor`)으로 **트리 전체 훑기**로 교체.
  바꾸는 순간 실제 위반 2건이 잡혔다:
    · `webapp/paths.py:155` docstring 에 진짜 계정 alias
    · `webapp/flow.py:125` docstring 에 진짜 계정 alias 2개
  둘 다 주석이라 동작은 0이지만, Pitfall 5 가 경고한 "주석에 남은 이름은 다음 사람에게
  별칭표로 읽힌다" 그 자체다. 일반화된 문구로 바꾸고 이유를 적어 뒀다.
- **Verification:** alias 를 주석에 되돌리니 red → 원복 후 green
- **Files:** `webapp/tests/test_board.py` · `webapp/paths.py` · `webapp/flow.py`
- **Commit:** `5a9d8f4`

### 3. [계획된 이탈] 해소 컬럼의 field 를 `표시사유` 로 잡았다

- **플랜 `<interfaces>`:** `{title: "해소", field: "사유코드", ...}`
- **왜 바꿨나:** `사유코드` 를 그리면 `미스` 가 그대로 셀에 뜬다. 그게 이 플랜이 막으라고
  받은 바로 그 문제다. 정렬도 표시 이름 기준이 맞다 — 사람이 보는 순서와 어긋나면 안 된다.
- `사유코드` 는 행 데이터에 그대로 남아 있고, 그 사실과 이유를 `board.js` 주석에 적었다.

### 4. [계획된 이탈] ctx 키가 5개가 아니라 6개다

플랜 interfaces 의 5키(`rows`·`resolution`·`cleanup`·`join_at`·`index_error`)에
**`index_health`** 와 **`filters`** 를 더했다.
- `index_health` — 시스템 배너가 "인덱스 불완전 N행(M그룹)" 을 말하려면 필요하다.
  `resolution["시스템"]["사유별"]` 을 그대로 그리면 딕셔너리 키 `미스` 가 화면에 뜬다.
- `filters` — 플랜이 **권장한** 쪽(상태 옵션 값을 라우트 ctx 로 넘긴다)을 택했다.
  버킷 이름도 같이 넘겨 한 키로 묶었다.

### 5. [범위 추가] 미해소 사유 이름을 버킷이 드러나게 다시 지었다

`그룹에 없음` → `인덱스에 없음`. 이제 시스템 사유가 전부 `인덱스…` 로 시작하고
광고 사유는 전부 `번호…` 로 시작한다. **기호·색이 죽어도 글자가 구분을 진다.**
(원래는 `광고 · ` / `시스템 · ` 접두를 붙였는데, 폭도 먹고 이름이 이미 말하고 있었다.)

---

## 검증

```
.venv-web/bin/pytest webapp/tests -q                       → 327 passed (319 → +8)
.venv-web/bin/pytest webapp/tests/test_board.py -q         → 23 passed (15 → +8)
.venv-web/bin/pytest webapp/tests/test_board.py -k 계정을_코드에 → 1 passed
.venv-web/bin/pytest webapp/tests/test_paths.py -k 리터럴    → 3 passed
.venv-web/bin/python3 webapp/tests/fixtures/render_check.py → 렌더 확인 전량 PASS
bash webapp/tests/no_commit_guard.sh                        → OK
node --check webapp/static/board.js                         → exit 0
node --check webapp/tests/board_cdp.mjs                     → exit 0

grep -c 'join.attach' webapp/routes/board.py                → 1
grep -c 'latest_done' webapp/routes/board.py                → 2  (목차 + 호출)
grep -c 'glob'        webapp/routes/board.py                → 0
grep -c 'system-warn' webapp/templates/board.html           → 3  (CSS 정의 + 사용 2)
grep -c 'f-state' / 'f-join' webapp/templates/board.html    → 1 / 1
table.setFilter 호출 수 (주석 제외)                            → 1
grep -rnE '^\s*(import|from)\s+(eroomlib|requests)' webapp/ → **0건** (D-19)
```

**실서버 CDP 검증 (포트 8799 · 격리 `data_root` · 격리 DB · 익명화 픽스처):**

```
V-BOARD-00~08   기존 9검사   → 전량 PASS (V-BOARD-07 포함, 표 1448 / 컨테이너 1448)
V-BOARD-09      헤더 4열                          → PASS  상세|기작업|사본|해소
V-BOARD-10      판정값 셀 전부 기호+글자            → PASS  값 4 / 기호 4 · 예 "🟡 단순번역만"
V-BOARD-11      미판정은 빈칸                      → PASS  빈칸 5 / 판정있음 4
V-BOARD-12      상태 필터 연속 전환 3회            → PASS  🔴2 · ⚪1 · 🟡1 전부 배지 일치
V-BOARD-13      상태+해소 동시 적용                → PASS
V-BOARD-14      하나 풀면 나머지만 남는다           → PASS  배지 3 / 정답 3
V-BOARD-15      기작업 행 회색                     → PASS  그려진 회색 2 / 원본 2
V-BOARD-16      전체선택 = 전체 - 기작업           → PASS  선택 7 / 정답 7 (전체 9)
V-BOARD-17      손으로 체크하면 들어간다            → PASS  7 → 8
V-BOARD-18      배너 2개 · 다른 DOM               → PASS
V-BOARD-19      배너 className 상이                → PASS  "stale" vs "system-warn"
V-BOARD-20      청소 표 렌더                       → PASS  셀 10개
V-BOARD-21      셀 = 원본 adGroups 값              → PASS  일치 2
V-BOARD-22      화면 글자에 '미스' 0건             → PASS  0건
────────────────────────────────────────────────────────────
                                                     보드 CDP 검증 전량 PASS
```

**네거티브 대조 4건 (앞 플랜들의 규율 승계 — "FAIL 을 본 적 없는 검증은 검증이 아니다"):**

| # | 무엇을 깨뜨렸나 | 무엇이 red 가 됐나 |
|---|---|---|
| 1 | `paths.py` 주석에 계정 alias 를 되돌림 | `test_계정을_코드에_박지_않는다` **FAIL** |
| 2 | `group_health` 갈림을 `완결 = True` 로 무력화 | `'그룹에 없음' == '인덱스 불완전'` **FAIL** |
| 3 | `_load_join` 을 `{}` 로 폴백 | `광고청소 9 == 0` **FAIL** — Pitfall 3 실물 재현 |
| 4 | `상태기호` 맵을 비움 (CDP 음성 대조) | `V-BOARD-10 값 4 / 기호 0` **FAIL** |

4건 전부 원복 후 green 을 다시 확인했다.

**CDP 실행 환경에 대해:** 실데이터가 아니라 **익명화 픽스처 + 격리 `data_root`** 로 돌렸다.
실회차에는 ⚪🟡🔴 판정도 기작업도 `미스` 도 아직 없어서(인덱스를 안 훑었다) 6종 중 4종이
SKIP 으로 빠진다. `result_traps.json` + `join_traps.json` 이 그 셋을 전부 담은 유일한 입력이다.
크레딧 0 · 불사자 접촉 0 · 실회차 파일 접촉 0. 검증이 끝난 뒤 임시 `workspace.toml` 을
지우고 원래 심볼릭 링크를 되돌렸다.

---

## 인증 게이트

없었다. 이 플랜은 불사자 MCP 도 광고 API 도 부르지 않는다 — 전부 읽기·렌더다.

## Known Stubs

없다. 화면 요소 전부가 실제 데이터로 렌더되는 것을 3층(pytest · render_check · CDP)에서 확인했다.

`상품해소 4/7` · `광고청소 2그룹` 같은 숫자는 픽스처 기준이고, 실회차에서는 그때그때
`resolution()` 이 계산한 값이 뜬다. **템플릿에 박힌 숫자는 0개**다
(`test_불사자_버튼은_POST_다` 가 기계로 본다).

## Threat Flags

없다. 이 플랜이 만진 표면은 전부 `<threat_model>` 에 등록돼 있다.

| 위협 | 어디서 막혔나 |
|---|---|
| T-3-31 시스템 문제가 광고 오류로 보임 | 배너 2종 분리 + `_인덱스표시` 재라벨 · CDP V-BOARD-18/19/22 · `test_미조회가_미스로_보이지_않는다` |
| T-3-32 광고그룹명·상품명 XSS | `|safe` 0건 · 보드 데이터는 `tojson` · 청소 표는 Jinja2 자동 이스케이프 |
| T-3-33 프롬프트 인젝션 필드 렌더 | `test_보드_HTML_에_표시규칙이_없다`(전문 0건) + `render_check.py` |
| T-3-34 기작업이 기본 선택에 섞임 | `필터 전체 선택` 제외 + CDP V-BOARD-16 (선택 7 = 9 - 2) |
| T-3-35 미판정을 🔴로 대체 | `빈칸이면()` 가드 + CDP V-BOARD-11 |

---

## 다음 플랜에 넘기는 것

**03-07 (실탄 인덱스):**
- 인덱스가 차면 `index_health.불완전` 이 줄고 `상품해소` 가 오른다. **그게 진척 지표다** —
  보드 위 시스템 배너를 그대로 보면 된다. 별도 대시보드를 만들지 마라.
- `완결=True` 가 된 그룹의 `미스` 행은 그때부터 **"인덱스에 없음"** 으로 바뀐다.
  그건 진짜 미스다(그룹은 다 훑었는데 이 상품이 없다 — 물갈이로 사라졌을 수 있다).
  그 숫자가 크면 `불일치` 와 같이 봐라.
- 화면은 이미 준비돼 있다. 03-07 이 할 일은 인덱스를 채우는 것뿐이고, **UI 를 더 고칠 필요가 없다.**

**Phase 5 (상세페이지):**
- 작업 대상은 `#f-state` 를 🔴 로, `#f-join` 을 `해소` 로 놓고 나온 행이다.
  선택 요약이 `🔴 N개 · 기작업 M건 제외` 를 이미 말한다.
- 기작업 제외는 화면(기본 선택)과 서버(`join.selectable`) **두 곳**에 있다.
  Phase 5 가 대상 목록을 만들 때 **서버 쪽을 정본으로 써라** — 화면만 믿지 않는다.
- 크레딧 견적을 띄울 자리는 03-05 가 만들어 둔 계정 배너의 크레딧 칸 옆이다.

**컬럼을 더 붙일 사람에게:**
- 고정폭 예산이 1,270 + 상품명 130 = 1,400 이다. 여유가 48px 뿐이다.
- `widthShrink` 로 해결하려 하지 마라 — `board.js` 주석에 왜 안 되는지 적어 뒀다.
- 붙였으면 **반드시** `board_cdp.sh` 의 V-BOARD-07 을 돌려라. 그게 이 예산을 지키는
  유일한 장치다.

## Self-Check: PASSED

**생성 파일 존재 확인** — FOUND
- `webapp/tests/fixtures/render_check.py`
- `.planning/phases/03-join-detail-state/03-06-SUMMARY.md`

**커밋 존재 확인** — 3/3 FOUND
`5a9d8f4`(T1) · `a6be928`(T2) · `498f9ba`(T3)

**삭제된 추적 파일 0건** — `git diff --diff-filter=D --name-only 3dd0610..HEAD` 비어 있음

**STATE.md · ROADMAP.md 미수정** (오케스트레이터 소유)

**`webapp/` 아래 `eroomlib`/`requests` import 0건 유지** — D-19 OK

**워크트리에 심었던 `.venv`·`.venv-web` 심볼릭 링크 제거 · `workspace.toml` 원상복구 확인**

---
*Phase: 03-join-detail-state*
*Completed: 2026-09-21*
