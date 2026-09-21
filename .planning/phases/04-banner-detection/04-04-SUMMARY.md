---
phase: 04-banner-detection
plan: 04
subsystem: cli-scanner
tags: [banner, ocr, vision, lexicon, skip-rules, d07, d08, d09, d10, determinism]

# Dependency graph
requires:
  - phase: 04-banner-detection
    plan: 01
    provides: "`.venv` 의 pyobjc-framework-Vision · `banner_labels.json` 정답지 · `settings.DEFAULTS` Phase 4 키 11개"
  - phase: 04-banner-detection
    plan: 02
    provides: "`webapp/banner.py` 판정 상수 4종 · 스킵사유 상수 3종 · `제품이미지목록` 접근 가드 · `test_어휘군_한중` 자리"
  - phase: 04-banner-detection
    plan: 03
    provides: "`banner_scan.py` 앞쪽 절반(인자·다운로드·SSRF 관문·Pillow 특징·썸네일·`무내용인가`) · `test_banner_scan.py` 10개"
provides:
  - "`ocr()` · `ocr_2패스()` — Vision 2패스. `setRevision_` 고정 · 지연 import · `Vision미설치` → exit 4"
  - "`OCR_패스` — 2패스를 데이터로 선언(언어 + 언어교정 on/off). 코드가 아니라 표라서 테스트가 읽는다"
  - "`어휘군` 8군(한/중) + `어휘군걸림()` — **배너 판정의 본체**(D-10)"
  - "`무내용사유()` — 무내용 사유 문자열의 정본. `전부특징`·`전부판정` 이 같은 함수를 부른다"
  - "`판정대상인가()` · `장판정()` · `전부판정()` — 판정 순서(어휘군 → 무내용 → 제품)의 정본"
  - "`제품이미지채우기()` · `제거율계산()` · `스킵규칙적용()` — D-06/D-07/D-08/D-09"
  - "`webapp/tests/cli/` + `norecursedirs` — `.venv` 전용 테스트가 사는 경로 (PATTERNS §11 미결 ③의 답)"
  - "`test_라벨픽스처_미탐0` — 배너 9장 9/9 적중 · 경계 4장 무오탐 회귀"
affects: [04-05, 04-06, 04-07, 04-08]

# Tech tracking
tech-stack:
  added: []          # 신규 패키지 0. `.venv` 의 pyobjc 는 04-01 이 이미 깔았다
  patterns:
    - "2패스 정의를 **데이터 표(`OCR_패스`)로 선언**한다 — `return a + b` 로 박으면 '두 패스가 있다'를 테스트가 구조로 못 읽는다"
    - "판정 사유 문자열의 정본을 함수 하나(`무내용사유`)로 모은다 — 같은 판정에 두 문구가 남으면 화면이 둘을 다른 것으로 센다"
    - "`.venv` 전용 테스트는 **디렉터리로 가른다**(`cli/` + `norecursedirs`). skip 헬퍼로 덮으면 미설치가 초록으로 보인다"
    - "`norecursedirs` 는 덮어쓰기다 — 기본값(`.*`·`build`·`node_modules`…)을 같이 적지 않으면 `.git`·`.venv` 까지 뒤진다"
    - "가드가 grep 으로 찾는 낱말을 감시 대상 파일이 주석에도 들고 있지 않는다 (`test_argv.py:205-207` 규율의 3번째 적용)"

key-files:
  created:
    - webapp/tests/cli/__init__.py
    - webapp/tests/cli/test_ocr_determinism.py
  modified:
    - .claude/skills/bulsaja-detail-page/scripts/banner_scan.py
    - webapp/tests/test_banner.py
    - webapp/pytest.ini

key-decisions:
  - "`ocr(revision=...)` 에 **기본값을 두지 않았다**(키워드 전용 필수 인자). 기본값을 박으면 산출물 `판정규칙.vision_revision` 과 실제 동작의 출처가 갈라져 T-4-13 방어가 장식이 된다"
  - "어휘군 매칭을 **소문자 사본**으로 한다. 실측 `zz12:1` 의 OCR 이 `Core selling point ... FACTORY DIRECT SALES` 라 대소문자를 안 맞추면 그 장을 놓친다 — RESEARCH 목록은 소문자로만 적혀 있다"
  - "`무내용` 장도 **판정 대상이다**. 어휘군이 무내용보다 먼저 보기 때문이다(플랜 지시). 대신 `무내용사유()` 를 정본으로 두어 04-03 의 `전부특징` 과 이 플랜의 `전부판정` 이 **같은 문구**를 쓴다"
  - "판정 사유에 **OCR 원문을 싣지 않는다**(T-4-15). `어휘군:공장직판,품질보증` 만 남긴다 — 사람이 '왜 배너로 봤나' 를 읽기엔 충분하고 상세 텍스트가 산출물로 새지 않는다"
  - "OCR 실패는 그 장만 `미판정` + 사유. `Vision미설치` 만 `raise` 로 통과시켜 `__main__` 이 exit 4 로 받는다 — 전자는 장 하나의 사실이고 후자는 회차 전체의 실패다"
  - "`제품이미지` 를 **스킵된 상품에도 채운다.** 접근을 막는 것은 `banner.제품이미지목록` 의 예외이지 빈 목록이 아니다 — 비우면 '제품 이미지가 0장' 이라는 **다른 사실**을 말하게 된다"
  - "스킵 우선순위: 판정불가 > 잔여부족 > 제거율초과. **판정불가를 덮지 않는다** — 판정 자체를 못 했는데 제거율을 사유로 적으면 거짓말이다"

patterns-established:
  - "합성 이미지로 OCR 을 검증할 때 **언어별 폰트를 따로 잡는다** — 한글 폰트로 한자를 그리면 두부(`冈`)가 나와 2패스 검증이 통째로 헛돈다"
  - "동일성 테스트는 **비어있지 않음을 같이 단언한다** — 3회 전부 `[]` 여도 '동일' 은 동일이고, 그 통과는 아무것도 증명하지 않는다"

requirements-completed: [BANNER-02b, BANNER-05]
requirements-partial: [BANNER-03b]

# Metrics
duration: 약 55min
completed: 2026-09-22
---

# Phase 4 Plan 04: OCR 2패스 · 어휘군 판정 · 스킵 규칙 Summary

**배너를 배너이게 하는 것은 픽셀 모양이 아니라 글자라는 D-10 을 코드로 세웠다 — macOS 온디바이스 Vision 2패스로 글자를 읽고, 판매사 홍보문구 어휘군 8군으로 판정하고, 스킵 3종이 사유를 들고 산출물에 남는다. 토큰 0 · 크레딧 0 · 네트워크 0.**

## Performance

- **Duration:** 약 55분
- **Tasks:** 3/3
- **Files modified:** 5 (생성 2 · 수정 3)
- **Tests:** `.venv-web` 387 → **388 green** · `.venv` cli **4 green** (신규 경로)
- **`banner_scan.py`:** 838 → **1,215행** · 신규 패키지 0 · MCP 호출 0회 · 크레딧 0

## Accomplishments

- **판정의 정본이 생겼다.** 04-03 이 `제거율: null` · `제품이미지: []` 로 남긴 칸이 전부 채워졌고, 04-03 이 "정직한 신호" 로 예고한 **정상 입력의 exit 3 이 해소됐다** (e2e exit 0).
- **2패스가 데이터로 선언돼 있다.** `OCR_패스` 표가 `(("ko-KR","en-US"), True)` · `(("zh-Hans","en-US"), False)` 두 줄이다. `return ocr(...) + ocr(...)` 로 박으면 "두 패스가 있다" 를 테스트가 구조로 못 읽는다.
- **리비전이 세 층에서 고정된다.** ① `setRevision_(--vision-revision)` 이 실제 요청에 걸리고 ② 그 값이 산출물 `판정규칙.vision_revision` 에 실리고 ③ `cli/test_ocr_determinism.py` 가 소스에 그 문자열이 박혀 있는지를 글자로 확인한다. 기본값이 이미 3이라 ③이 없으면 지워도 오늘은 같은 결과가 나온다 — **그게 D-10 이 경고한 바로 그 상황이다.**
- **스킵 3종이 전부 사유를 들고 온다.** e2e 에서 `잔여부족 1` · `제거율초과 1` · `판정불가 1` 이 각각 다른 문구로 남았고, 판정불가 상품을 D-07/D-08 이 덮지 않았다. **새 상태값도 큐 파일도 0건**(D-09).
- **D-09 가드가 이제 판정의 정본도 훑는다.** `test_사람큐_없음` 이 `banner.py` 와 `banner_scan.py` 를 같이 본다 — 화면만 깨끗하고 산출물에 새 상태값이 들어가면 큐는 그대로 생긴다.
- **`.venv` 전용 테스트 경로가 실재한다.** PATTERNS §11 미결 ③ 이 닫혔다. skip 헬퍼로 덮지 않았고, 그 헬퍼 이름을 파일에 글자로도 남기지 않았다.

## Task Commits

1. **Task 1: OCR 2패스 — revision 고정 · 지연 import · exit 4** — `28cc168` (feat)
2. **Task 2: 어휘군 8군 + 장별 판정 + 스킵 규칙 + 산출물** — `3eb6103` (feat)
3. **Task 3: `.venv` 결정성 테스트 + 어휘군 미탐 0 회귀** — `c3451ba` (test)

## 🔴 어휘군 검증 현황 — 무엇이 검증됐고 무엇이 안 됐나

플랜 브리핑이 지목한 **이 플랜의 1순위 리스크**에 대한 정직한 답이다.
어휘군 8군 전부가 한국어 항목과 중국어 항목을 **둘 다** 갖는다(`test_어휘군_한중` ④가 집행).
그러나 **그 둘의 근거 등급이 다르다.**

| 군 | 한국어 절반 | 중국어 절반 |
|---|---|---|
| 공장직판 | ✅ **실측 코퍼스** — `zz11:0`(`공장 직판`·`직공구`) · `zz14:0`(`제조업체`·`직접 판매`) · `zz12:1`(`FACTORY DIRECT SALES`) | 🟡 **합성 검증** — `厂家直销` 를 렌더해 zh 패스로 읽고 `공장직판` 적중 확인 |
| 품질보증 | ✅ **실측 코퍼스** — `zz07:3`(`정품 보증`) · `zz14:0`(`고품질의 재료`·`품질 보장`) · `zz09:1`(`양심적`) · `zz12:1`(`품질 보증`) | 🟡 **합성 검증** — `品质保证` 적중 |
| 배송 | ✅ **실측 코퍼스** — `zz12:1`(`즉시 배송`) | 🟡 **합성 검증** — `包邮` 적중 |
| 반품교환 | ✅ **실측 코퍼스** — `zz07:3`(`반품`) | ❌ **미검증** (`七天无理由`·`退换货`·`分期免息` 등) |
| 경품이벤트 | ✅ **실측 코퍼스** — `zz07:0`(`활동 시간`·`참여방식`·`선물을 드립니다`) · `zz07:1`(`경품`·`위안`) · `zz11:0`(`인기 판매`) | ❌ **미검증** (`赠品`·`秒杀`·`满减` 등) |
| AS안내 | ✅ **실측 코퍼스** — `zz10:12`(`애프터서비스`·`사용 및 유지`) · `zz10:14`(`구매 안내`) | ❌ **미검증** (`售后服务`·`客服` 등) |
| 핵심셀링 | ✅ **실측 코퍼스** — `zz12:1`(`핵심 판매 포인트`·`Core selling point`) | ❌ **미검증** (`核心卖点`·`服务保障` 등) |
| 연락처 | ❌ **미검증** (실측 배너 9장 중 어느 것도 연락처 군에 안 걸린다) | ❌ **미검증** (`微信`·`淘宝`·`扫码` 등) |

**정리:**

- **회귀 정답지(`banner_labels.json` 배너 9장)로 검증되는 것은 8군 중 7군의 한국어 절반뿐이다.** 그 9장의 OCR 첫 줄에 **한자가 0글자**이기 때문이다 (04-02 가 실측으로 정정한 사실 — `test_어휘군_한중` ②가 그것을 고정한다).
- **중국어 절반에 대해 이 플랜이 새로 만든 근거는 "합성 검증" 이다.** `cli/test_ocr_determinism.py::test_2패스가_한쪽_언어를_놓치지_않는다` 가 `厂家直销 品质保证` 을 Songti 로 렌더해 zh-Hans 패스로 읽고 `공장직판` 군 적중을 단언한다. 같은 이미지에 대해 **한국어 패스는 그 줄을 아예 못 읽는다**는 것도 같이 단언한다 — 이게 2패스가 필요한 이유의 실물이다. 추가로 e2e 실측에서 중국어 배너 2장(`厂家直销 品质保证 包邮` · `七天无理由 退换货`)이 실제로 `배너` 로 찍혔다.
- **합성 검증이 증명하는 것과 못 하는 것:** 증명하는 것은 "zh-Hans 패스 + 중국어 어휘 문자열의 배관이 실제로 동작한다" 이다. **증명하지 못하는 것은 "실제 중국 상세 이미지에 이 구절들이 저 형태로 나타난다" 이다.** 후자는 실제 코퍼스 표본이 없어 이 플랜에서 증명 불가다.
- **연락처 군은 양쪽 다 미검증이다.** 실측 배너 9장 중 어느 것도 여기 안 걸린다. RESEARCH §Pattern 4 의 목록을 그대로 유지했지만, 이 군이 실제로 무언가를 잡는지는 **04-08 의 전수 검수(D-12)에서 처음 드러난다.**
- **이것이 RESEARCH §정직한 한계 2(어휘군 과적합)가 도착한 모습이다.** `test_라벨픽스처_미탐0` 의 9/9 는 **회귀 방지**이지 게이트 통과 근거가 아니고, 그 문장이 테스트 docstring 맨 앞에 적혀 있다.

**04-08 게이트가 반드시 할 일:** 게이트 세트에 🔴 중국어원본 상품을 명시적으로 포함하고, 중국어 절반의 미탐을 **따로 집계**해라. 전체 미탐 0% 뒤에 "중국어 배너 표본이 0개였다" 가 숨을 수 있다.

## Files Created/Modified

- **`.claude/skills/bulsaja-detail-page/scripts/banner_scan.py`** (838 → 1,215행, +377)
  - `Vision미설치` 예외 · `_비전()` 지연 import · `OCR_패스` 표 · `ocr()` · `ocr_2패스()`
  - `무내용사유()` (04-03 의 `전부특징` 도 이 함수를 부르도록 교체)
  - `어휘군` 8군 + `_어휘군소문자` + `어휘군걸림()`
  - `판정대상인가()` · `장판정()` · `전부판정()`
  - `제품이미지채우기()` · `제거율계산()` · `스킵규칙적용()`
  - `main()` 에 ⑥ OCR 판정 · ⑦ 상품층 집행 단계 추가 + `[4/5]`·`[5/5]` 로그 실제 숫자화
  - `__main__` 에 `Vision미설치` → **exit 4** 핸들러
- **`webapp/tests/cli/test_ocr_determinism.py`** (164행, 신규) — `.venv` 전용 4개
- **`webapp/tests/cli/__init__.py`** (신규) — 패키지 조상 경로 확보 + 실행법 docstring
- **`webapp/tests/test_banner.py`** (482 → 562행) — `스캐너` 픽스처 · `test_어휘군_한중` 실검사화 · `test_라벨픽스처_미탐0` 신규 · `test_사람큐_없음` 이 `banner_scan.py` 도 훑음
- **`webapp/pytest.ini`** (14 → 26행) — `norecursedirs` + 이유 주석

## 실측 e2e (`.venv` · 네트워크 0 · 캐시 선적재 · 합성 이미지 13장)

```
[1/5] URL 추출 14장 (상품 4 · 상세 미조회 0)
[2/5] 다운로드 13장 (실패 1)
[3/5] 특징 13장 (무내용 후보 1)
[4/5] OCR 13장 (Vision revision 3)
[5/5] 썸네일 13장 · 판정 배너 5 / 제품 7 / 무내용 1 / 미판정 1 · 스킵상품 3 (어휘군 2026-09-21)
※ 판정불가 상품 1건 · ※ 스킵 — 잔여부족 1건 (D-07) · 제거율초과 1건 (D-08)
끝 — 상품 4 · 장 14 · 판정완료 13 · 미판정 1 · 3.4초 (크레딧 0 · MCP 0회)      → exit 0
```

산출물 확인:

| 상품 | 스킵사유 | 제거율 | 제품이미지 순번 | 비고 |
|---|---|---|---|---|
| zz00 | `null` | 0.4 | [2,3,4] | `#0` 한국어 배너 · `#1` **중국어 배너**(`어휘군:공장직판,품질보증,배송`) |
| zz01 | `잔여부족` | 0.5 | [1] | "배너를 빼고 남은 제품 이미지가 1장 — D-07 하한 2장 미만" |
| zz02 | `제거율초과` | 0.6 | [3,4] | `#2` 는 `무내용(짧은변) 1200x20` · `#0` 은 `어휘군:반품교환`(중국어) |
| zz03 | `판정불가` | 0.0 | [0] | 미판정 1장 — **D-07/D-08 이 덮지 않았다** |

`게이트통과: false` · `판정규칙` 6키 전부 인자에서 왔다 · `장` 배열에 전장이 다 있다(스킵 상품 포함).

**실측 기대값(배너 87 · 제품 804 · 스킵상품 2)과의 대조는 이 플랜에서 불가능하다** — 891장 코퍼스는 저장소에 없고 CDN 다운로드가 필요하다. 04-08 이 실제 회차로 돌려 대조해야 한다.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] 플랜의 `supportedRevisions()` 호출이 `AttributeError` 다**

- **Found during:** Task 3
- **Issue:** 플랜 Task 3 의 테스트 ①이 `VNRecognizeTextRequest.alloc().init().supportedRevisions()` 라고 적었다. 실측하면 `AttributeError: 'VNRecognizeTextRequest' object has no attribute 'supportedRevisions'` 다 — **클래스 메서드**다 (04-03 SUMMARY 도 같은 경고를 남겼다).
- **Fix:** `Vision.VNRecognizeTextRequest.supportedRevisions()` 로 부르고, 반환이 `NSIndexSet` 이라 `in` 이 아니라 `.containsIndex_(3)` 으로 본다. 그 사실을 테스트 docstring 에 적었다.
- **Verification:** `.venv` 실측 → `[number of indexes: 3 (in 1 ranges), indexes: (1-3)]`
- **Committed in:** `c3451ba`

**2. [Rule 3 - Blocking] 어휘군 매칭이 대소문자를 안 맞추면 실측 배너 1장을 놓친다**

- **Found during:** Task 2
- **Issue:** RESEARCH §Pattern 4 의 영문 항목은 전부 소문자다(`core selling point` · `factory direct`). 그런데 라벨 배너 `zz12:1` 의 OCR 첫 줄은 `Core selling point / 6가지 핵심 판매 포인트 / FACTORY DIRECT SALES / ...` 다. 그대로 `in` 매칭하면 그 두 항목이 안 걸린다(한국어 항목 덕에 배너 판정 자체는 살지만, `핵심셀링` 군이 조용히 빠진다 — 사유가 절반만 참이 된다).
- **Fix:** `_어휘군소문자` 사본을 만들고 본문도 `.lower()` 해서 본다. 원본 `어휘군` dict 는 사람이 읽는 정본으로 그대로 둔다.
- **Verification:** `zz12:1` → `['공장직판', '품질보증', '배송', '핵심셀링']` (4군)
- **Committed in:** `3eb6103`

**3. [Rule 2 - Missing critical] `norecursedirs = cli` 만 적으면 `.git`·`.venv` 를 뒤지기 시작한다**

- **Found during:** Task 3
- **Issue:** 플랜은 *"`webapp/pytest.ini` 에 `norecursedirs = cli` 를 더한다"* 고 적었다. `norecursedirs` 는 **추가가 아니라 덮어쓰기**다 — pytest 기본값(`*.egg .* _darcs build CVS dist node_modules venv {arch}`)이 통째로 날아간다. 이 저장소에는 `.venv`·`.venv-web`·`.claude`·`.planning` 이 전부 루트에 있어서, 수집 범위가 조용히 넓어진다.
- **Fix:** 기본값을 전부 같이 적고 뒤에 `cli` 를 붙였다. 이유를 주석으로 남겼다.
- **Verification:** `.venv-web` 388 green · 수집 시간 변화 없음(11.5초)
- **Committed in:** `c3451ba`

**4. [Rule 2 - Missing critical] 결정성 테스트가 빈 결과로도 통과할 수 있었다**

- **Found during:** Task 3
- **Issue:** 플랜 테스트 ②는 *"3회 돌려 출력이 완전히 동일하다"* 만 요구한다. OCR 이 3회 전부 `[]` 를 돌려줘도 "동일" 은 동일이다. 폰트가 없거나 이미지가 깨졌을 때 이 테스트가 **초록으로 아무것도 증명하지 않는다.**
- **Fix:** `assert 결과들[0]` 을 먼저 건다. 실패 문구에 "동일성만 보면 빈 결과도 '통과'다" 를 적었다.
- **Committed in:** `c3451ba`

**5. [Rule 2 - Missing critical] 어휘군 중국어 절반이 실행 근거 0 으로 나갈 뻔했다 (플랜 브리핑 1순위 리스크)**

- **Found during:** Task 3
- **Issue:** 플랜은 `.venv` 테스트를 3개로 정했고 중국어 어휘군을 실제로 태우는 자리가 **한 곳도 없었다.** 라벨 정답지 배너 9장에 한자가 0글자라(04-02 실측) `test_라벨픽스처_미탐0` 도 한국어 절반만 잰다. 그대로 두면 `厂家直销` 계열 60여 개 문자열이 "코드에 있지만 한 번도 실행되지 않은" 상태로 04-08 게이트에 들어간다.
- **Fix:** 4번째 테스트 `test_2패스가_한쪽_언어를_놓치지_않는다` 를 더했다. 한/중 두 줄을 **언어별 폰트로** 렌더해 ① ko 패스가 한국어를 읽고 ② zh 패스가 중국어를 읽고 ③ **ko 패스는 중국어를 못 읽고**(2패스가 필요한 이유의 실물) ④ 양쪽 패스 결과가 **둘 다** `공장직판` 군에 걸리는지를 단언한다. 추가로 e2e 를 중국어 배너 2장을 포함해 구성했다.
- **한계는 그대로 남는다:** 이건 **합성 검증**이지 실제 코퍼스 근거가 아니다. 위 §어휘군 검증 현황 표에 군별로 등급을 적었다.
- **Verification:** `.venv` cli 4 green · e2e 에서 중국어 배너 2장이 `배너` 로 찍혔다
- **Committed in:** `c3451ba` (e2e 구성은 `3eb6103` 검증분)

**6. [Rule 2 - Missing critical] 금지 낱말 `대기` 를 감시 대상 파일이 주석에 들고 있었다**

- **Found during:** Task 2
- **Issue:** 04-03 이 남긴 `# 재시도 대기(초).` 주석이 D-09 금지 낱말 `대기` 를 글자로 들고 있었다. 플랜 acceptance 는 따옴표 붙은 형태(`"대기"`)만 보므로 통과하지만, 그 상태로는 `test_사람큐_없음` 을 `banner_scan.py` 로 **확장할 수 없다** — 판정의 정본이 영영 가드 밖에 남는다.
- **Fix:** 주석을 `# 재시도 사이에 쉬는 시간(초).` 으로 바꾸고 **왜 그 낱말을 안 쓰는지**를 같이 적었다. 그 위에서 `test_사람큐_없음` 이 `banner.py` 와 `banner_scan.py` 를 같이 훑도록 확장했다. 같은 이유로 `cli/test_ocr_determinism.py` 에서도 skip 헬퍼 이름을 글자로 안 쓴다(플랜 acceptance 가 그 파일에서 0줄을 요구한다).
- **Verification:** 세 낱말 전부 두 파일에서 0건 · 388 green
- **Committed in:** `3eb6103` · `c3451ba`

**7. [Rule 1 - Bug] 무내용 사유 문구가 두 벌이 될 뻔했다**

- **Found during:** Task 2
- **Issue:** 04-03 의 `전부특징` 은 `"무내용 장 (1200x40)"` 을 쓰고, 플랜 Task 2 는 `"무내용(종횡비)"` / `"무내용(짧은변)"` 을 지시한다. 판정을 다시 찍는 `전부판정` 이 후자를 쓰면 **같은 판정에 두 문구**가 남고, 04-06 화면·04-08 집계가 둘을 다른 것으로 센다.
- **Fix:** `무내용사유()` 를 정본으로 만들고 `전부특징` 도 그 함수를 부르게 바꿨다. `무내용인가` 와 **같은 순서**(짧은변 → 종횡비)로 보게 해서 "무내용이라는데 사유가 딴소리" 를 구조적으로 막았다. `무내용인가` 자체는 04-03 의 테스트 2개가 지키므로 손대지 않았다.
- **Verification:** e2e `무내용(짧은변) 1200x20` 1건 · `test_무내용인가_경계값` green
- **Committed in:** `3eb6103`

**8. [Rule 3 - Blocking] 워크트리에 `.venv`·`.venv-web`·`workspace.toml` 이 없다**

- **Found during:** 시작 전
- **Issue:** 04-01~04-03 과 같다. 셋 다 gitignore 대상이라 병렬 워크트리에 존재하지 않는다.
- **Fix:** 04-02/04-03 의 해법 그대로 — `.venv`/`.venv-web` 을 실제 디렉터리로 만들고 `bin`·`lib`·`pyvenv.cfg` 만 본 저장소로 심링크, `workspace.toml` 은 사본. 커밋 0건.
- **Verification:** 매 커밋 전 `git diff --cached --name-only` 확인 — 3커밋 전부 의도한 파일만
- **Committed in:** 해당 없음

**9. [정정] 워크트리 base 가 지정된 커밋보다 뒤에 있었다**

- **Found during:** 시작 전 (worktree_branch_check)
- **Issue:** HEAD 가 `3118192`(phase 4 컨텍스트 기록 시점)였다. 지정 base 는 `438d94f`(wave 3 반영 후)라 **Wave 1~3 산출물이 통째로 없는 상태**였다.
- **Fix:** 브랜치 검사(`worktree-agent-*` 네임스페이스 · 보호 ref 아님) 통과를 먼저 확인한 뒤 `git reset --hard 438d94f`. 그 전에는 `reset` 을 돌리지 않았다.
- **Verification:** `git log` → `438d94f docs(phase-04): update tracking after wave 3`

---

**Total deviations:** 9 (Rule 1 ×3 · Rule 2 ×4 · Rule 3 ×2 — 그중 8·9 는 환경 정정)
**Impact on plan:** 범위 확장 없음. 5번만 테스트 1개를 더했고(3 → 4), 그건 플랜 브리핑이 1순위 리스크로 지목한 자리다.

## Issues Encountered

- **플랜 Task 1 의 `<verify>` 가 Task 3 에서야 생기는 파일을 가리킨다** (`webapp/tests/cli/test_ocr_determinism.py`). Task 1 은 acceptance grep 4종 + `.venv-web` 의 `test_banner_scan.py` + `.venv` 애드혹 OCR 스모크로 검증했고, 그 테스트 파일이 생긴 뒤(Task 3) 다시 돌렸다.
- **플랜 acceptance 의 `setUsesLanguageCorrection_` 2회 이상**은 RESEARCH §Pattern 3 원본 코드로는 충족되지 않는다(`ocr()` 안에 1회뿐이다). 문자열을 주석으로 뿌려 grep 을 만족시키는 대신, **2패스를 `OCR_패스` 표로 선언**하고 각 줄에 어느 값이 그 API 로 들어가는지를 적었다 — 결과적으로 4회가 됐고, "두 패스가 있다" 가 데이터로 읽힌다.
- **플랜 acceptance 는 cli 테스트 3 passed 를 적었는데 4 passed 다** (Deviations 5).
- **실측 기대값(배너 87 · 제품 804 · 스킵상품 2) 대조를 못 했다.** 891장 코퍼스가 저장소에 없다. 04-08 몫이다.
- `pytest -q` 가 요약 줄을 안 찍는 현상(04-02·04-03 과 동일). `-q` 없이 돌려 숫자를 확인했다.

## Known Stubs

없다. 이 플랜이 만든 함수는 전부 실제 동작을 하고, 04-03 이 `null` 로 남긴 칸 셋이 모두 채워졌다.

| 04-03 이 남긴 칸 | 지금 상태 |
|---|---|
| `장[].판정` 의 배너/제품 | ✅ 어휘군 + 무내용 + 제품으로 채워진다 |
| `상품[].제거율` | ✅ `(배너+무내용)/판정완료`. 판정완료 0이면 여전히 `null`("모른다") |
| `상품[].스킵사유` 의 `잔여부족`/`제거율초과` | ✅ D-07/D-08 이 건다 |
| `상품[].제품이미지` | ✅ 원래 순서 · 개수 제한 없음(D-06) |

**미검증으로 남는 것**(stub 이 아니라 *근거가 없는 것*)은 위 §어휘군 검증 현황에 군별로 적었다. 요약: 중국어 절반은 합성 검증 3군 · 미검증 5군, 연락처 군은 양쪽 다 미검증.

## Threat Flags

없다. 새 네트워크 엔드포인트 0 · 인증 경로 0 · 스키마 변경 0. OCR 은 전부 온디바이스라 나가는 요청이 늘지 않았다.

위협 등록부 5건 처리 결과:

| Threat ID | Disposition | 처리 |
|---|---|---|
| T-4-13 (Vision 기본 리비전 변경) | **mitigate 완료** | `setRevision_(--vision-revision)` · 산출물 `판정규칙.vision_revision` · `cli` 테스트가 소스에 박혀 있음을 단언 + 최상단 import 0줄까지 같이 본다 |
| T-4-01 (미판정 흡수 · 스킵 누락) | **mitigate 완료** | `판정대상인가()` 가 `미판정+사유` 장을 건드리지 않는다. 제거율 분모에서 미판정 제외. 판정불가를 D-07/D-08 이 덮지 않는다. 전량 미판정만 exit 3 |
| T-4-14 (어휘군이 바뀌었는데 숫자만 남는 것) | **mitigate 완료** | `판정규칙.어휘군버전` 을 산출물에 찍는다. `test_라벨픽스처_미탐0` 이 규칙 변경을 CI 에서 드러낸다 |
| T-4-15 (OCR 텍스트가 로그로 새는 것) | **mitigate 완료** | 로그는 건수만. 사유는 `어휘군:<군이름>` 이지 OCR 원문이 아니다. 실패 사유에도 이미지 내용이 아니라 예외 종류만 들어간다 |
| T-4-16 (`.venv-web` 수집이 Vision 부재로 깨지는 것) | **mitigate 완료** | `cli/` + `norecursedirs`(기본값 포함). skip 헬퍼 금지 규율 유지 — 그 이름을 파일에 글자로도 안 남긴다 |

## Next Phase Readiness

**04-05(`BannerArgv`)가 지킬 것:**

- CLI 계약이 04-03 SUMMARY §CLI 계약 그대로다. **플래그가 하나도 늘지 않았다** — `--vision-revision`·`--skip-min-keep`·`--skip-max-removal`·`--lexicon-version` 을 이 플랜이 실제로 쓰기 시작했을 뿐이다.
- **종료코드 4 가 이제 실제로 난다.** `.venv` 에 pyobjc 가 없으면 즉시 4다. 잡 실패 문구를 만들 때 4를 "알 수 없는 오류" 로 접지 마라 — 사유가 stdout·stderr 양쪽에 한 줄로 나간다.
- 전 값을 명시적으로 넘겨라(S-4). 안 넘기면 `workspace.toml` 을 고쳐도 동작이 안 바뀐다.

**04-06(라우트·검수 화면)이 지킬 것:**

- `장[].사유` 의 모양이 4종으로 굳었다: `"어휘군:공장직판,품질보증"` · `"무내용(짧은변) 1200x20"` · `"무내용(종횡비) 1500x63"` · 실패 문구(`"HTTP 404 (재시도 무의미 — 영구)"` 등). **사유를 파싱하지 마라** — 표시용이다. 판정은 `장[].판정` 이 정본이다.
- `상품[].사유` 는 스킵 사유의 사람용 설명이고 `상품[].스킵사유` 가 코드다. 배지는 코드로, 툴팁은 설명으로.
- `장` 배열에는 **스킵된 상품도 전장이 다 있다**(D-03a). 스킵 배지를 이유로 장을 감추지 마라 — 스킵 판단 자체가 틀렸을 수 있다.
- `장[].썸네일` 은 여전히 **파일명만**이다.

**04-08(게이트)이 반드시 할 일:**

- **🔴 중국어원본 상품을 게이트 세트에 명시적으로 포함하고 중국어 미탐을 따로 집계해라.** 위 §어휘군 검증 현황이 그 이유다. 전체 미탐 0% 뒤에 "중국어 배너 표본 0개" 가 숨을 수 있다.
- **연락처 군이 한 장도 못 잡으면 그건 발견이지 실패가 아니다** — RESEARCH 가 추정으로 넣은 군이고 실측 근거가 0이다. 잡히는 게 있는지부터 보고해라.
- VALIDATION 의 명령 문자열을 갱신해라: `webapp/tests/test_ocr_determinism.py` → **`webapp/tests/cli/test_ocr_determinism.py`**. 실행 인터프리터는 `.venv/bin/python3` 다.
- 실측 기대값(배너 87 · 제품 804 · 스킵상품 2) 대조는 **이 플랜에서 못 했다.** 891장 코퍼스가 저장소에 없다. 실제 회차로 돌려 크게 벗어나면 어휘군 버전을 올리고 다시 재라 — 단, **같은 세트로 다시 잰 숫자는 게이트 통과 근거가 못 된다**(Pitfall 3).

**막는 것 없음.** `.venv-web` 388 green · `.venv` cli 4 green.

---
*Phase: 04-banner-detection*
*Completed: 2026-09-22*

## Self-Check: PASSED

- 파일 6개 전부 존재: `banner_scan.py` · `webapp/tests/cli/__init__.py` · `webapp/tests/cli/test_ocr_determinism.py` · `webapp/tests/test_banner.py` · `webapp/pytest.ini` · `04-04-SUMMARY.md`
- 커밋 4개 전부 존재: `28cc168` · `3eb6103` · `c3451ba` · `1799db7`
- **삭제된 파일 0건** (`git diff --diff-filter=D --name-only 438d94f..HEAD`)
- **공유 산출물 미수정:** base 이후 변경 파일 6개가 전부 이 플랜의 `files_modified` 안이다. `STATE.md`·`ROADMAP.md`·`REQUIREMENTS.md` 변경 0건 (오케스트레이터 몫)
- 커밋되지 않아야 할 것이 안 들어갔다: `.venv`/`.venv-web` 심링크 디렉터리 · `workspace.toml` 사본 · scratchpad e2e 산출물 전부 staged 0건
- `.venv-web` 388 green (exit 0) · `.venv` `webapp/tests/cli/test_ocr_determinism.py` 4 green (exit 0)
- D-09 금지 낱말(`보류`·`대기`·`검토요청`) `banner.py`·`banner_scan.py` 양쪽 0건 · `setRevision_` 소스에 박힘 · Vision 계열 최상단 import 0줄
