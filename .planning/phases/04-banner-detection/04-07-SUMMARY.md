---
phase: 04-banner-detection
plan: 07
subsystem: review-screen-strip
tags: [banner, htmx, jinja2, cdp, d03a, 전장노출, accessibility, boundary-samples]

# Dependency graph
requires:
  - phase: 04-banner-detection
    plan: 06
    provides: "`GET /banner/review` ctx · `GET /banner/thumb/{run_dir}/{product_i}/{chap_i}` · `POST /banner/label`·`/banner/confirm` · `_화면투영`"
  - phase: 04-banner-detection
    plan: 05
    provides: "`jobs.latest_done('banner_scan')` · `jobs.banner_dir` · `banner_label`/`banner_confirm` DDL · `POST /jobs/banner/scan`"
  - phase: 04-banner-detection
    plan: 04
    provides: "산출물 JSON 계약 — `집계`·`상품[].스킵사유`·`장[].판정`·`장[].썸네일`(파일명만)"
  - phase: 04-banner-detection
    plan: 02
    provides: "`banner.배너/제품/무내용/미판정` · `사람판정허용값` · `상품키` · `게이트집계`"
  - phase: 01-webapp-shell
    provides: "`security.guard` 3층 · `_job_panel.html` SSE 배선 · `board.html` htmx 관용구 · `sse_cdp.sh` 자체기동 CDP 관용구"
provides:
  - "`webapp/templates/_banner_strip.html` — 장 한 개 조각. 화면 3곳(스트립·기준 확인·라벨 POST 응답)이 **같은 파일**을 쓴다"
  - "전장 스트립이 실제로 깔리는 `banner_review.html` — 상품당 가로 한 줄, 펼치기 클릭 0회"
  - "`routes/banner.py` 의 `_토글순환`·`_다음판정`·`_장투영` — 판정 순환을 **서버가** 계산한다"
  - "기준 확인 섹션(경계 4장) + 못 찾았을 때의 정직한 폴백"
  - "`webapp/tests/banner_cdp.sh`·`banner_cdp.mjs` — 전장 노출(D-03a)을 기계가 집행하는 브라우저 회귀"
  - "`_회차확인()` — 쓰기 경로의 회차 화이트리스트 (04-06 docstring 이 주장만 하던 것)"
affects: [04-08]

# Tech tracking
tech-stack:
  added: []          # 신규 패키지 0. htmx 2.0.10 · htmx-ext-sse 2.2.4 · Pico 2.1.1 전부 기존 vendored
  patterns:
    - "같은 조각을 세 곳이 쓰면 **템플릿 파일 하나**로 만든다 — 클릭 전후로 테두리 규약이 어긋나면 사람은 그걸 저장 실패와 구분하지 못한다"
    - "판정 순환을 템플릿에 넣지 않는다. 다음 값·테두리 클래스·글자를 전부 서버 ctx 가 들고 간다(S-1)"
    - "라벨 POST 응답이 **산출물을 다시 읽어** 조각을 그린다 — 요청이 보낸 값으로 그리면 화면이 DB 가 아니라 자기 자신을 비춘다"
    - "같은 장이 두 자리에 나오면 `data-slot` 으로 가른다 — 안 가르면 전장 수가 부풀어 보이고 회귀가 거짓 초록이 된다"
    - "설정 표본과 설명 문장을 join 할 때 **코드를 두 번 적지 않는다**: `DEFAULTS` 의 자리(index)로 묶는다"
    - "브라우저 회귀는 **정상 경로 200 을 먼저 단언**한다 (04-06 의 조용한 404 교훈을 계승)"

key-files:
  created:
    - webapp/templates/_banner_strip.html
    - webapp/tests/banner_cdp.mjs
    - webapp/tests/banner_cdp.sh
  modified:
    - webapp/routes/banner.py
    - webapp/templates/banner_review.html
    - webapp/tests/test_routes_banner.py

key-decisions:
  - "**토글 순환의 마지막 칸을 기계 판정으로 뒀다.** 배너→제품→무내용→배너. 되돌리기 버튼을 따로 만들면 상태가 하나 더 생기고, 새 상태는 곧 사람 판단 큐의 입구다(D-09). `post_label` docstring 의 '원래 판정을 다시 찍는 것이 되돌리기다' 를 화면 동선으로 실현했다"
  - "**기계가 `미판정` 인 장은 복귀 자리가 없다.** 사람은 '모르겠다'를 못 찍으므로(`사람판정허용값` 에 미판정 없음) 세 값만 돈다. 그 장은 누군가 반드시 값을 정해야 하고, 그게 `게이트집계` 가 미판정 장을 분모에서 빼는 이유와 한 쌍이다"
  - "**라벨 POST 응답을 요청 값으로 그리지 않는다.** 산출물을 다시 읽어 기계 판정·사유·썸네일 유무를 서버가 꺼낸다. 클라이언트가 보낸 값으로 테두리를 칠하면 화면이 DB 가 아니라 자기 자신을 비추고, 그 순간 '미탐 0%' 의 근거가 사라진다"
  - "**기준 확인 섹션의 장이 아래 전장 목록에도 그대로 다시 나온다.** 중복이 아니라 D-03a 다 — 기준 확인을 위해 전장을 깎으면 협상 불가 조건이 조용히 깨진다. 대신 `data-slot` 으로 갈라 회귀가 전장만 세게 했다"
  - "**경계 4장의 '물어볼 것' 을 `DEFAULTS` 의 index 로 join 했다.** 설정에는 코드만 있고 질문이 없는데, 질문을 설정에 넣으면 익명화 불가 값이 한 벌 더 생기고 라우트에 코드를 다시 적으면 정본이 둘이 된다. index join 이면 코드를 한 글자도 안 적고, 설정이 표본을 갈아 끼우면 질문 없이(None) 뜬다 — 자리가 밀려 엉뚱한 질문이 붙는 일이 없다"
  - "**테두리 클래스 이름을 판정값 문자열이 아니라 ASCII 상수로 뒀다**(`ct-banner`·`ct-blank`·`ct-unjudged`·`ct-product`). 판정 어휘가 바뀌는 날 스타일이 조용히 사라지는 것을 막는다"
  - "**제품 장에만 판정 글자를 안 붙인다.** 891장 중 대부분이 제품이라 거기까지 글자를 붙이면 줄이 글자로 덮여 3초 훑기가 안 된다. 눈에 걸려야 하는 것은 제품이 아닌 장이다"
  - "**CDP 스크립트가 서버를 스스로 띄운다**(`sse_cdp.sh` 방식). `board_cdp.sh` 처럼 터미널 2개를 요구하면 이 회귀는 아무도 안 돌린다 — D-03a 는 사람의 기억이 아니라 기계가 지켜야 한다"

patterns-established:
  - "브라우저 회귀의 첫 검사는 **정상 경로가 200/렌더된다**를 단언한다. 그게 없으면 통째로 고장난 서버에서도 나머지가 전부 초록이다(04-06 이 비싸게 배운 것)"
  - "한글 `data-*` 속성 셀렉터를 쓸 때는 **ASCII 카운트와 대조하는 단언을 같이** 둔다 — 조용히 0을 세는 것을 잡는다"
  - "화면 검사(node)와 DB 검사(sqlite3)를 한 스크립트가 이어서 하고, 최종 exit 코드는 셸이 합산한다"

requirements-completed: [BANNER-04, BANNER-05]
requirements-partial: []

# Metrics
duration: 약 65min
completed: 2026-09-22
---

# Phase 4 Plan 07: 검수 화면 본체 — 전장 스트립 Summary

**상품의 전 이미지가 가로 한 줄로 깔리고 틀린 장만 클릭으로 뒤집힌다 — 그리고 "전장이 깔린다"가 사람의 기억이 아니라 브라우저 회귀의 단언이 됐다(D-03a).**

## Performance

- **Duration:** 약 65분
- **Tasks:** 3/3
- **Files:** 6 (생성 3 · 수정 3) — 플랜 `files_modified` 와 정확히 일치
- **Tests:** `.venv-web` 429 → **441 green** (신규 12) · `.venv` cli **4 green** (변화 없음)
- **브라우저 회귀:** `banner_cdp.sh` 검사 4개 + 준비 확인 2개 전부 PASS, **exit 0**
- **신규 패키지 0 · MCP 호출 0회 · 크레딧 0 · 네트워크 0 · 배너 스캔 자식 0개**

## Task Commits

| # | 작업 | 커밋 | 종류 |
|---|---|---|---|
| 1 | 전장 스트립 + 테두리 4종 + 라벨 클릭 (회귀 8) | `7fb4294` | feat |
| 2 | 기준 확인(경계 4장) + 접수 버튼 + 잡 패널 (회귀 4) | `cac0b20` | feat |
| 3 | 전장 노출 브라우저 회귀 `banner_cdp.sh`/`.mjs` | `f02e281` | test |

## 🔴 D-03a — 전장 노출을 어떻게 기계로 못박았나

플랜의 objective 가 *"이 화면이 미탐 0% 의 측정 장치 그 자체다"* 라고 적은 자리다. 배너로 판정한 것만 보여주는 화면은 **오탐만 잡고 미탐을 구조적으로 증명할 수 없다.** 그래서 이 사실을 세 겹으로 고정했다:

| 층 | 무엇을 단언하나 | 어디 |
|---|---|---|
| pytest | `data-slot="strip"` 개수 == 산출물 `집계.장`, 그리고 **`집계.배너` 와 같지 않다** | `test_전장이_다_깔린다` |
| pytest | 스킵 상품(순번 1)의 장 3개가 전부 썸네일 경로로 깔린다 + 그 줄에도 라벨 POST 가 산다 | `test_스킵_상품도_전장을_깐다` |
| 브라우저 | 실제 DOM 의 `figure[data-slot="strip"]` 수 == 19, 스킵 줄 figure 3/3 + 클릭 가능 3 | `banner_cdp.sh` ①② |

**일부러 깨 봤다.** 템플릿의 스트립 루프를 `{% for 장 in 상품.장 if 장.표시판정 == 배너값 %}` 로 바꾸니:

```
FAIL V-BANNER-01  전장 노출이 깨졌다 — figure 3개 / 산출물 장 19개.
                  배너만 깔면 미탐을 구조적으로 못 본다(D-03a). (배너 3개)
FAIL V-BANNER-02  스킵줄 figure 1/3 · 클릭 가능 1
```
pytest 쪽도 4개가 빨개졌다(`test_전장이_다_깔린다`·`test_스킵_상품도_전장을_깐다` + 기준 확인 2개). 확인 후 되돌렸고 441 green 을 다시 확인했다.

## 브라우저 회귀 — 자체 기동 · 크레딧 0

`board_cdp.sh` 는 터미널 2개(서버 + 검증)를 요구한다. 그 형태로 만들면 **이 회귀는 아무도 안 돌린다.** `sse_cdp.sh` 의 자체 기동 관용구를 따라 한 줄로 끝나게 했다:

```
bash webapp/tests/banner_cdp.sh
```

- 임시 포트 + `CT_DB_PATH`/`CT_JOB_LOG_DIR` mktemp → **저장소 루트의 `webapp.db` 를 안 건드린다**
- 산출물은 스크립트가 만든 합성 JSON, 잡 행을 `done` 으로 직접 넣는다 → **배너 스캔 자식 0개, 4분 기다림 0**
- 회차는 실제 목록에서 최신 하나를 **읽기만** 한다(화이트리스트 통과가 필요하므로)
- 썸네일만은 저장소 썸네일 루트에 실제로 쓴다(그 경로는 설정에서만 오고 env 로 못 바꾼다). `zzcdp_` 접두 파일만 만들고 cleanup 이 **그것만** 지운다 — 디렉터리째 지우면 실제 스캔 결과를 날린다

실측 출력:

```
회차 2026-09-20 · 장 19 (배너 3) · 스킵 상품 순번 1 (3장)
PASS V-BANNER-00   썸네일 정상 경로가 200 이다                      status 200
PASS V-BANNER-01   전장이 다 깔린다 (figure 수 == 집계.장)           19장
PASS V-BANNER-01b  한글 data-* 셀렉터가 실제로 먹는다                data-장순번 19 / strip 19 + sample 0
PASS V-BANNER-02   스킵 상품도 전장을 깐다                          스킵줄 figure 3/3 · 클릭 가능 3
PASS V-BANNER-03-화면  클릭한 장이 사람 판정으로 바뀐다
PASS V-BANNER-04-화면  확인함이 배지로 바뀐다 (라벨 테두리는 그대로)
PASS V-BANNER-03   장 클릭이 banner_label 에 1행으로 남았다          (1행)
PASS V-BANNER-04   확인함은 banner_confirm 에만 쓴다                (confirm 1 · label 1)
```

**V-BANNER-00 과 01b 는 04-06 의 교훈을 그대로 계승한 줄이다.** 04-06 에서 한글 경로 파라미터 때문에 썸네일이 전부 404 였는데 "막혔다"만 보는 검증은 통째로 초록이었다. 그래서 ① 정상 경로가 진짜 200 인지 ② 한글 `data-*` 셀렉터가 조용히 0을 세고 있지 않은지를 먼저 본다. **실측 결과 브라우저에서 `figure[data-장순번]` 셀렉터는 정상 동작한다** — 경로 파라미터와 달리 여기는 문제가 없다(19개를 정확히 센다).

## 화면 규약

**테두리 4종 — 색만으로 가르지 않는다** (흑백 출력·색맹):

| 판정 | 테두리 | 글자 | 클래스 |
|---|---|---|---|
| 배너 | 빨강 **실선** | `배너` | `ct-banner` |
| 무내용 | 회색 **점선** | `무내용` | `ct-blank` |
| 미판정 | 주황 **이중선** | `⚠ 미판정` | `ct-unjudged` |
| 제품 | 없음(투명, 같은 두께) | (없음) | `ct-product` |
| 사람이 찍음 | 위 + 아래 밑줄 | `✋` 추가 | `+ ct-human` |

제품 장도 **같은 두께의 투명 테두리**를 갖는다 — 클릭으로 판정이 바뀔 때 줄이 덜컹 밀리지 않게 하려는 것이다. 제품에만 글자를 안 붙이는 이유는 위 key-decisions 에 적었다.

**CSS 3줄(RESEARCH 요구) 전부 들어갔다:** 썸네일 `height: 200px; width: auto` · 줄 넘침 `overflow-x: auto` · 화면 밖 상품 `content-visibility: auto` (+ `contain-intrinsic-size`, `<img loading="lazy">`).

**스킵 줄은 흐려지되 클릭이 산다.** `opacity: .5; font-style: italic` 만 건다 — 클릭을 죽이는 CSS 를 넣는 순간 스킵 오판정을 영영 못 잡는다. 그 속성 이름은 템플릿 주석에도 안 남긴다(회귀가 글자로 찾는다).

## 클릭 순환

```
기계 배너:  (라벨 없음)→제품→무내용→배너(복귀)
기계 제품:  (라벨 없음)→배너→무내용→제품(복귀)
기계 무내용: (라벨 없음)→배너→제품→무내용(복귀)
기계 미판정: 배너→제품→무내용→배너   ← 복귀 자리가 없다
```

계산은 전부 `routes/banner.py:_다음판정()` 이 한다. 템플릿은 `장.라벨요청` dict 를 `| tojson` 으로 `hx-vals` 에 싣기만 한다 — **판정 로직이 템플릿에 한 줄도 없다**(S-1).

기계가 `제품`이라 한 장을 **한 번만 누르면 `배너`** 가 되게 한 것이 요점이다. 미탐(사람이 배너라 했는데 기계가 놓친 장)을 찍는 동선이 가장 짧아야 한다 — 그게 이 화면이 재는 바로 그 숫자다.

## 기준 확인 (경계 4장)

- `settings.cfg("banner_boundary_samples")` 의 `"코드:순번"` 4개를 산출물에서 찾아 **첫 화면에 크게**(`ct-big`, 320px) 깐다
- 각 장 아래에 RESEARCH Appendix A 의 "물어볼 것" 한 줄을 그대로 적는다
- **미리 묻지 않는다** — 화면에 배치해 클릭으로 답을 받는다(사람 큐를 안 만드는 원칙과 같은 결)
- **같은 장이 아래 전장 목록에도 또 나온다.** 회귀가 썸네일 URL 이 정확히 2번 나오는지 센다
- 못 찾으면 **조용히 감추지 않는다**: `"기준 표본 4/4 를 이 회차에서 못 찾았다 — 어느 것인지:"` + 토큰별 사유(`이 회차에 그 판매자상품코드가 없다 (물갈이로 재발급됐을 수 있다)` / `그 상품에 N번 장이 없다 (장수 M)` / 모양 오류)

**이 폴백은 가정이 아니라 테스트다.** `test_경계_표본을_못_찾으면_조용히_감추지_않는다` 가 zz* 코드만 있는 산출물로 섹션이 살아 있고 문구가 뜨고 **전장은 그대로 19장 깔리는지**를 확인한다. Wave 0 이 경고한 대로 이 값은 다음 물갈이 회차에 반드시 낡는다.

## Files

- **`webapp/templates/_banner_strip.html`** (신규 60행) — `<figure>` 하나. `data-p`/`data-i`(04-06 회귀가 본다) + `data-장순번`(브라우저 회귀) + `data-slot`(스트립/기준 구분)
- **`webapp/templates/banner_review.html`** (130 → 295행) — CSS 스트립 블록 · 스캔버튼 매크로 · 잡 패널 · 기준 확인 섹션 · 상품 줄 반복
- **`webapp/routes/banner.py`** (443 → 680행) — `_판정클래스`/`_판정글자` · `_토글순환` · `_다음판정` · `_장투영` · `_회차확인` · `_경계질문` · `_기준표본` · `_장조각` 재작성
- **`webapp/tests/test_routes_banner.py`** (498 → 813행) — 신규 12 (§7 전장 노출 8 · §8 기준 확인·접수 4)
- **`webapp/tests/banner_cdp.sh`** (신규 227행) · **`banner_cdp.mjs`** (신규 254행)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical] 쓰기 경로에 회차 화이트리스트가 없었다**

- **Found during:** Task 1
- **Issue:** `LabelReq` docstring 이 *"`run_dir` 은 여기서 검증하지 않는다 — `paths.run_dir_path()` 화이트리스트가 본다"* 고 적어 뒀는데, **`post_label`·`post_confirm` 은 그 함수를 한 번도 안 부른다.** 경로를 조합하지 않으므로 탈출 위험은 없지만, 모르는 회차로 들어온 라벨은 DB 에 남는데 어느 화면에도 안 보인다 — 사람은 클릭이 먹혔다고 믿고 게이트는 그 라벨을 영원히 못 센다. 이 저장소가 가장 싫어하는 "저장은 됐는데 화면이 거짓말" 모양이다. 그리고 04-07 이 라벨 POST 응답에서 산출물을 읽게 되면서 이 구멍이 실제 동작 차이로 드러난다(회차를 모르면 조각을 못 그린다).
- **Fix:** `_회차확인()` 을 만들어 두 POST 핸들러가 Pydantic 통과 직후 탄다. 모르는 회차는 400 + `"모르는 회차다: ..."`.
- **Verification:** `test_모르는_회차로는_라벨이_안_들어간다` — 400 이고 `banner_label`·`banner_confirm` 둘 다 0행
- **Committed in:** `7fb4294`

**2. [Rule 2 - Missing critical] 기준 확인 섹션이 전장 수를 부풀린다**

- **Found during:** Task 2 설계
- **Issue:** 플랜이 Task 1 acceptance 로 *"`<figure>` 가 장 수만큼 나온다"* 를, Task 2 로 *"경계 4장이 아래 목록에도 또 나온다"* 를 동시에 요구한다. 둘 다 옳지만 **그대로 두면 `<figure>` 총 개수가 `장수 + 4`** 라 두 acceptance 가 서로를 깬다. 더 나쁜 건 브라우저 회귀 ①이 "배너만 깔렸다" 버그를 그 4개 때문에 놓칠 수 있다는 점이다.
- **Fix:** 조각에 `data-slot="strip"|"sample"` 을 붙여 두 자리를 갈랐다. 전장을 세는 모든 단언(pytest·CDP)은 `strip` 만 센다. 기준 섹션 수는 따로 단언한다. **플랜의 두 요구를 둘 다 만족시키면서** 회귀가 거짓 초록이 되지 않는다.
- **Verification:** `test_경계_4장이_첫화면에_있고_아래_목록에도_또_나온다` 가 썸네일 URL 이 **정확히 2번** 나오는지 센다 + `V-BANNER-01b` 가 `strip + sample == data-장순번 전체` 를 확인
- **Committed in:** `7fb4294` (속성) · `cac0b20` (기준 섹션)

**3. [Rule 3 - Blocking] 가드가 감시하는 낱말을 감시 대상이 주석에 들고 있었다 (3곳)**

- **Found during:** Task 1·3
- **Issue:** 04-06 이 세 번 겪은 것과 같은 병이 또 났다. ① `banner_review.html` CSS 주석이 "클릭을 막는 속성" 이름을 글자로 들고 있어 `test_스킵_상품도_전장을_깐다` 가 빨갛다 ② `_banner_strip.html`·`banner_review.html` 주석이 `hx-` + `get` 을 들고 있어 플랜 acceptance(`hx-get` 0줄)가 깨진다 ③ `banner_cdp.sh` 주석이 배너 스캔 스크립트 파일명을 들고 있어 acceptance(`banner_scan.py` 0줄)가 깨진다.
- **Fix:** 셋 다 낱말을 빼고 **뜻으로** 적고, 각 자리에 "이 이름을 주석에도 안 남긴다 — 회귀가 글자로 찾는다" 를 명시했다(`test_argv.py:9-14` 규율).
- **Verification:** acceptance grep 실측 — `hx-get` 0/0 · `banner_scan.py` 0 · `| safe` 0/0 · 표 라이브러리 0/0
- **Committed in:** `7fb4294` · `f02e281`

**4. [Rule 1 - Bug] bash 3.2 가 `$VAR` 뒤의 한글을 변수 이름으로 먹는다**

- **Found during:** Task 3 첫 실행
- **Issue:** `banner_cdp.sh` 가 `SKIP_N장: unbound variable` 로 즉사했다. `"...($SKIP_N장)"` 에서 macOS 기본 bash 3.2 가 `장` 을 식별자의 일부로 읽는다. 스크립트 머리에 *"변수 이름을 한글로 쓰지 마라"* 라고 적어 뒀는데, **변수 이름이 아니라 바로 뒤에 붙는 한글**도 같은 사고를 낸다는 것은 그 주석이 안 적고 있었다.
- **Fix:** `${SKIP_N}장`·`${LABELS}행` 으로 중괄호를 쳤다(2곳). 파일 전체를 grep 으로 훑어 같은 모양이 더 없는지 확인했다.
- **Verification:** `bash webapp/tests/banner_cdp.sh` exit 0
- **Committed in:** `f02e281`

**5. [Rule 3 - Blocking] 워크트리 base 가 지정 커밋보다 뒤에 있었다**

- **Found during:** 시작 전 (worktree_branch_check)
- **Issue:** HEAD 가 `3118192`(phase 4 컨텍스트 기록 시점)였다. 04-04·04-05·04-06 이 겪은 것과 같다 — Wave 1~6 산출물이 통째로 없는 상태.
- **Fix:** 브랜치 검사(`worktree-agent-*` 네임스페이스 · 보호 ref 아님)를 **먼저** 통과시킨 뒤 `git reset --hard 93c8d9b`.
- **Committed in:** 해당 없음

**6. [Rule 3 - Blocking] 워크트리에 `.venv`·`.venv-web`·`workspace.toml` 이 없다**

- **Found during:** 시작 전
- **Issue:** 04-01~04-06 과 같다. 셋 다 gitignore 대상이라 병렬 워크트리에 존재하지 않는다.
- **Fix:** 앞선 웨이브의 해법 그대로 — `.venv`/`.venv-web` 을 실제 디렉터리로 만들고 `bin`·`lib`·`pyvenv.cfg` 만 본 저장소로 심링크, `workspace.toml` 은 사본. **커밋 0건.**
- **Verification:** base 이후 변경 파일 6개가 플랜 `files_modified` 와 정확히 일치. `git status` 깨끗
- **Committed in:** 해당 없음

### 작업 순서 조정 (이탈 아님)

플랜의 Task 1·2 가 같은 파일 셋을 건드리므로, **먼저 둘 다 구현해 전 스위트를 통과시킨 뒤 Task 1 범위만 남긴 트리로 되돌려 커밋하고, 그다음 Task 2 를 얹었다.** 두 커밋 각각이 단독으로 일관된 트리이고 각자의 회귀가 그 트리에서 green 이다(437 → 441). 플랜의 **내용**은 하나도 안 바꿨다.

`_banner_strip.html` 만은 두 커밋에서 같은 내용이다 — 그 파일의 머리 주석이 기준 확인 섹션을 먼저 언급하게 되지만, 파일 자체는 Task 1 트리에서도 그대로 동작한다(`자리` 의 기본값이 `strip`).

---

**Total deviations:** 6 (Rule 1 ×1 · Rule 2 ×2 · Rule 3 ×3 — 그중 5·6 은 환경 정정)
**Impact on plan:** 범위 확장 없음. 1·2 는 플랜의 요구 둘이 서로 어긋나거나 04-06 의 docstring 이 주장만 하던 자리를 메운 것이고, 3·4 는 기계 가드가 잡아 준 것이다. 테스트가 12개(플랜 명시) + 브라우저 검사 6개로 늘었다.

## Issues Encountered

- **`pytest -q` 가 요약 줄을 안 찍는 현상**(04-02~04-06 과 동일). `-q` 없이 돌려 숫자를 확인했다.
- **`.venv` 심링크를 깔기 전 전 스위트가 빨갛다**(CLI venv 부재). 심링크 후 **429 green** 을 base 로 확인한 뒤 작업을 시작했다.
- **`banner_cdp.sh` 가 종료할 때 `Terminated: 15` 한 줄이 stderr 로 남는다.** 서버 프로세스를 `kill` 하면서 bash 의 job control 이 찍는 것이고, `sse_cdp.sh` 도 같다. **exit 코드는 0 이다**(실측). 기능에 영향 없어 그대로 뒀다.
- **`security_curl.sh` 전체는 이번에도 못 돌렸다.** 04-06 이 넘긴 숙제 그대로 04-08 몫이다. 다만 이 플랜은 새 GET 핸들러를 하나도 안 만들었다 — `get_review` 가 `jobs.active_job()` 을 더 부르는데, 그건 `latest_done` 과 같은 WAL no-op 트랜잭션이라 `test_GET_무부작용`(DB mtime + 행 수 불변)이 계속 green 이다.

## Known Stubs

**없다.** 스캔한 결과 이 플랜이 만든 화면 경로에 하드코딩된 빈 값·플레이스홀더 텍스트·데이터 미연결 컴포넌트가 없다.

혼동하기 쉬운 두 가지는 **stub 이 아니라 실제 상태**다:

| 보이는 것 | 왜 stub 이 아닌가 |
|---|---|
| `썸네일 없음` 자리표시 | `장.썸네일있음 == false` 인 장은 진짜로 썸네일이 없다(미판정·다운로드 실패). `<img>` 를 걸면 깨진 그림이 되고, 빼 버리면 전장이 아니게 된다(D-03a) — 자리를 남기고 없다고 말하는 것이 정답이다 |
| `기준 표본 4/4 를 못 찾았다` | 합성 픽스처(zz* 코드)에서 나오는 정직한 결과다. 실제 회차에서는 표본이 있으면 4장이 뜬다. 이 문구가 나오는 것 자체가 설계대로 동작한다는 뜻이다 |

## Threat Flags

**등록부 밖의 새 surface 는 없다.** 새 엔드포인트 0개이고, 라벨 POST 가 산출물 JSON 을 **읽는** 동작이 하나 늘었을 뿐이다(쓰기 아님).

| Threat ID | Disposition | 처리 |
|---|---|---|
| T-4-24 (템플릿 XSS) | **mitigate 완료** | Jinja2 자동 이스케이프 유지 · `\| safe` 0건(grep 가드) · `hx-vals` 는 `\| tojson`(`<`,`>`,`&`,`'` 를 `\uXXXX` 로) · 산출물 URL·파일명을 템플릿에 안 싣는다 |
| T-4-05 (라벨 CSRF) | **mitigate 완료** | 조각·버튼 전부 `hx-post`. 쓰기용 GET 속성 0건(회귀가 렌더 결과에서 글자로 확인) · 토큰은 `<body hx-headers>` 한 줄 |
| T-4-25 (저장 실패인데 화면만 바뀜) | **mitigate 완료** | 테두리는 서버 조각 교체(`hx-swap="outerHTML"`)로만 바뀐다 — 200 이 아니면 교체가 없다. `hx-on::response-error` 가 상단 배너를 띄우고, CDP ③이 `banner_label` 행 수를 sqlite3 로 직접 센다 |
| T-4-26 (CDN Referer 유출) | **mitigate 완료** | 서버 썸네일만 쓴다(직링크 0) · `<meta name="referrer" content="no-referrer">` 유지 |
| T-4-27 (891 `<img>` 동시 로드) | **accept (설계대로)** | `loading="lazy"` + `.ct-row { content-visibility: auto; contain-intrinsic-size: auto 280px }`. 1인 로컬 · 서버 썸네일 총 3.8MB |
| D-03a (전장 노출) | **지켜짐 · 기계 집행** | pytest 2 + 브라우저 1. 일부러 깨서 빨개지는 것까지 확인 |
| D-09 (사람 판단 큐) | **지켜짐** | 금지 낱말 0 · 큐 경로 0 · 라우트 경로 4개 그대로 · 되돌리기 버튼 대신 순환 복귀 |

## Next Phase Readiness

**04-08(게이트·최종 검증)이 바로 쓸 수 있는 것:**

- **`bash webapp/tests/banner_cdp.sh` 한 줄이면 전장 노출·라벨 기록이 확인된다.** 서버를 따로 안 띄워도 되고 크레딧 0이다.
- 게이트 숫자(`게이트집계`)는 헤더에 이미 뜬다. 미검수 > 0 이면 "닫혀 있다" 가 화면에 나온다 — 전수가 전제라는 D-12 가 화면에서 성립한다.
- 사람 라벨 동선이 실제로 돈다: 장 클릭 → `banner_label` 1행, `확인함` → `banner_confirm` 1행. 둘이 섞이지 않는다(CDP ④).

**04-08 이 조심할 것:**

- **`security_curl.sh` 전체를 서버 띄우고 한 번 돌려라.** 04-06 이 V-SAFE-01d 만 떼어 돌렸고 이 플랜도 마찬가지다. `banner_cdp.sh` 가 임시 서버를 띄우는 관용구를 그대로 베끼면 터미널 하나로 끝난다.
- **경계 4장은 실제 회차에서 아직 사람이 안 눌렀다.** 화면에 배치하는 것까지가 이 플랜이고, 답을 받아 어휘군에 반영하는 것은 사람의 클릭 + 그 뒤의 판단이다(RESEARCH Open Questions 3).
- 🔴 **새 라우트를 만들면 경로 파라미터를 영문으로 써라**(04-06 이탈 1). 한편 **`data-*` 속성 이름은 한글이어도 브라우저에서 정상 동작한다** — 이번에 실측으로 확인했다(`V-BANNER-01b`). 둘을 같은 문제로 묶지 마라.
- `banner_cdp.sh` 는 실제 회차가 **하나라도 있어야** 돈다(화이트리스트 통과 때문). 없으면 exit 2 + `"판정된 회차가 하나도 없다"` 로 정직하게 멈춘다.

**막는 것 없음.** `.venv-web` 441 green · `.venv` cli 4 green · `banner_cdp.sh` exit 0 · `no_commit_guard.sh` OK.

---
*Phase: 04-banner-detection*
*Completed: 2026-09-22*
