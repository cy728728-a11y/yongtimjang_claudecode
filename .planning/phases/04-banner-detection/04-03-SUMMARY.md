---
phase: 04-banner-detection
plan: 03
subsystem: cli-scanner
tags: [banner, cli, ssrf, pillow, thumbnail, download, cache-rotation, d19]

# Dependency graph
requires:
  - phase: 04-banner-detection
    plan: 01
    provides: "`settings.DEFAULTS` Phase 4 키 11개 · `.venv` 의 Pillow/Vision · `.venv-web` pytest 경로"
  - phase: 04-banner-detection
    plan: 02
    provides: "`webapp/banner.py` 순수 접근자(`상세이미지목록`·`상세보유행들`·판정 상수 4종) · D-19 트리 순회 가드"
  - phase: 03-join-detail-state
    provides: "`bulsaja_scan.py` 조인 산출물(`행[].uploadDetailContents`) · `state.상세상태` · `ss_index_build.py` CLI 관용구 4종"
provides:
  - "`banner_scan.py` — 인자·종료코드 계약 · 조인 읽기 · URL 추출 · 병렬 다운로드 · Pillow 특징 · 썸네일"
  - "`허용URL인가()` — SSRF 단일 관문 (외부에서 받은 URL 이 내부망을 겨누지 못한다)"
  - "`회차정리()` — 원본 캐시 회차 회전 (회차당 약 271MB)"
  - "`무내용인가()` — 구분선·슬라이스 규칙. **배너 판정이 아니다**"
  - "`bulsaja_scan.py` 의 `타오바오상품번호` — 물갈이 사본이 게이트 분모를 부풀리지 않는 근거 (MCP 호출 0회 추가)"
  - "캐시·썸네일 파일명 규약(`<상품순번 4자리>_<장순번 2자리>`) — 04-04·04-06 공용"
  - "`webapp/tests/test_banner_scan.py` — CLI 순수부 회귀 10개 + CLI 폴백↔settings 드리프트 가드"
affects: [04-04, 04-05, 04-06, 04-07, 04-08]

# Tech tracking
tech-stack:
  added: []          # 신규 패키지 0. 전부 stdlib + 이미 있던 Pillow 12.3.0
  patterns:
    - "`.venv-web` 으로 도는 테스트가 `.venv` 전용 스크립트를 importlib 로 로드한다 — 그 대가로 `PIL`·`Vision` import 가 **함수 안쪽 지연 import** 로 강제된다"
    - "CLI 폴백 기본값을 `settings.DEFAULTS` 와 대조하는 테스트로 S-4 드리프트를 기계로 잡는다 (설정 모듈을 CLI 가 import 하지 않고도)"
    - "실패 판별식을 `미판정` 이 아니라 **`미판정 + 사유`** 로 잡는다 — 미완성 단계의 '아직 안 함'과 실패를 구조적으로 가른다"

key-files:
  created:
    - .claude/skills/bulsaja-detail-page/scripts/banner_scan.py
    - webapp/tests/test_banner_scan.py
  modified:
    - .claude/skills/bulsaja-detail-page/scripts/bulsaja_scan.py

key-decisions:
  - "404 사유를 `\"HTTP 404 (재시도 무의미 — 영구)\"` 로 적는다. RESEARCH 예시의 `\"HTTP 404 (3회 재시도)\"` 는 **안 한 재시도를 했다고 적는 것**이라 쓰지 않았다"
  - "`무내용인가` 의 종횡비를 `긴변/짧은변` 으로 잰다(`w/h` 가 아니다) — 가로·세로 구분선이 같은 규칙에 걸린다. 배너(0.89→1.12)는 어느 쪽으로 재도 6.0 근처에 못 간다"
  - "썸네일을 **키우지 않는다**. 구분선(1200x40)을 높이 200 에 맞추면 6000x200 으로 원본보다 커진다 — 실측 확인 후 `min(썸높이, 원본높이)` 로 잘랐다"
  - "`webapp.state` 도 import 했다. 플랜은 `banner` 만 적었지만 `상세상태` 를 재현하면 진실이 둘이 된다(S-1). `state.py` 는 import 0 인 순수 모듈이라 `.venv` 에서도 안전하다"
  - "CLI 가 `webapp.settings` 를 import 하지 않는다 — `settings` 는 `paths` 를 끌고 오고 그건 `workspace.toml` 에 묶인다. 대신 폴백 dict 를 두고 **테스트로 드리프트를 잡는다**"
  - "`무내용` 판정은 이 플랜에서 내린다(픽셀 기하 규칙이라 특징 단계의 일이다). 배너/제품은 04-04 의 OCR + 어휘군 몫이다"
  - "`제거율`·D-07/D-08 스킵 규칙은 **이 플랜이 계산하지 않는다** — 분자가 배너 판정이라 04-04 가 채워야 옳다"

patterns-established:
  - "금지 토큰(불사자 MCP 클라이언트 모듈명)을 주석에도 글자로 남기지 않는다 — `test_argv.py:205-207` 규율의 CLI 판"
  - "지운 캐시 회차를 로그로 말한다. 조용히 지우면 디스크가 왜 줄었는지 아무도 모른다"
  - "썸네일 생성 실패는 판정 불가가 아니다 — 등급을 나눠 실패 하나가 회차를 죽이지 않게 한다"

requirements-completed: []
requirements-partial: [BANNER-01, BANNER-03b, BANNER-04]

# Metrics
duration: 约 33min
completed: 2026-09-22
---

# Phase 4 Plan 03: CLI 스캐너 앞쪽 절반 — 다운로드부터 썸네일까지 Summary

**이미지에 손대는 코드 전부를 `.venv` 자식 프로세스 한 파일에 몰아넣고, 외부에서 받은 URL 이 내부망을 겨누지 못하게 관문 하나를 세우고, 실패한 장이 '배너 아님'으로 흡수되지 않고 사유를 들고 남게 만들었다.**

## Performance

- **Duration:** 약 33분
- **Tasks:** 3/3
- **Files modified:** 3 (생성 2 · 수정 1)
- **Tests:** 377 → **387 green** (신규 10)
- **`banner_scan.py`:** 838행 · 신규 패키지 0 · MCP 호출 0회 · 크레딧 0

## Accomplishments

- **D-19 경계가 실물이 됐다.** `webapp/` 은 여전히 HTTP 도 Pillow 도 안 만진다. 다운로드·디코딩·썸네일이 전부 `banner_scan.py` 안에 있고, 파싱 규칙만 `webapp.banner` 에서 빌려 쓴다 — 규칙을 복제하지 않았으므로 화면과 산출물이 다른 말을 할 여지가 없다.
- **SSRF 관문이 단 하나다.** `허용URL인가()` 를 다운로드 직전 한 자리에서 부른다. `https` 만 · IP 리터럴 전부 거부 · `localhost` · 사설/루프백/링크로컬/예약/멀티캐스트 대역 · 자격증명 박힌 호스트(`https://cdn.bulsaja.com@127.0.0.1/…`) · 빈 문자열. **거부가 예외가 아니라 `(False, 사유)`** 라 URL 한 개가 회차를 죽이지 않는다.
- **실패가 사유를 들고 온다.** 404·타임아웃·거부 URL·디코딩 실패·decompression bomb 이 전부 `판정: "미판정"` + 사유로 남고, 그 상품에 `스킵사유: "판정불가"` 가 붙는다. `try/except: pass` 가 0줄이다.
- **빈 대상이 '전량'이 되는 경로가 두 군데 더 막혔다.** `--join` 누락 / 상세 보유 0건 → exit 2. 그리고 **`--keep-runs 0` → 예외** — 이건 삭제판이라 미끄러지면 캐시를 통째로 민다.
- **`타오바오상품번호` 가 조인 산출물에 실린다.** MCP 호출 **0회 추가** (`mode=full` 응답을 한 번 더 읽을 뿐). 이게 없으면 게이트 집계가 항상 불사자코드로 폴백해 "물갈이 사본이 분모를 부풀리지 않는다"(성공기준 4)를 증명하지 못한다.
- **종횡비가 배너 판정에 쓰이지 않는다.** `무내용인가` 의 docstring이 그 사실을 못박고, 실측 배너 5모양이 이 규칙에 안 걸리는 것을 회귀로 고정했다(Pitfall 1).

## Task Commits

1. **Task 1: 골격 — 인자·종료코드·조인읽기·URL추출** — `ef9dc64` (feat)
2. **Task 2: 병렬 다운로드 — SSRF 관문·재시도·캐시 회차 정리** — `05a4437` (feat)
3. **Task 3: Pillow 특징 + 썸네일 + 무내용 장 규칙** — `d630605` (feat)

## Files Created/Modified

- **`.claude/skills/bulsaja-detail-page/scripts/banner_scan.py`** (838행, 신규)
  - 모듈 docstring 맨 위에 **종료코드 계약**과 exit 3 경계의 근거
  - 공용 유틸 4종(`말하기`/`오류말하기`/`원자적쓰기`/`지금`)을 `ss_index_build.py` 에서 복사
  - 이름 규약 4함수: `장이름`/`원본경로`/`썸네일이름`/`썸네일경로` — **파일명은 정수 인덱스에서만 만든다**
  - `허용URL인가` · `회차정리` · `한장받기` · `호스트이름` · `전부받기` · `상품별미판정반영`
  - `무내용인가` · `특징과썸네일` · `전부특징`
  - `상품골격` · `장골격` · `URL추출` · `집계내기` · `인자만들기` · `main`
- **`webapp/tests/test_banner_scan.py`** (233행, 신규) — 10개
  - SSRF 3개(거부 18케이스 · 통과 4케이스 · 거부가 예외가 아님)
  - 캐시 회차 4개(오래된 것만 · 지금 회차 보호 · `keep_runs=0` 예외 · 루트 부재)
  - S-4 드리프트 1개 · 무내용 규칙 2개
- **`.claude/skills/bulsaja-detail-page/scripts/bulsaja_scan.py`** — 행 초기화 dict 에 `"타오바오상품번호": None` + `d.get("productNo")` 채움 (2곳, +11행)

## CLI 계약 (04-05 `BannerArgv` 가 그대로 쓴다)

```
--join --out --run-dir --cache --thumbs            (5개 전부 필수. 없으면 exit 2)
--workers --vision-revision --blank-ar --blank-short-px
--skip-min-keep --skip-max-removal --lexicon-version --keep-runs

종료코드  0 정상 / 2 대상 없음 / 3 전량 미판정 / 4 Vision 미설치(04-04)
```

`argparse required=True` 를 **한 곳도 쓰지 않았다.** argparse 가 직접 죽으면 사유가 stderr 로만 나가고 stdout(=잡 로그·SSE 화면)에 한 글자도 안 남는다. 사람이 화면에서 "왜 멈췄나" 를 읽을 수 있어야 한다는 것이 `bulsaja_scan.py:291-299` 규약의 요점이다.

## 실측 (e2e · `.venv`)

```
$ .venv/bin/python3 banner_scan.py --out … --run-dir zz --cache … --thumbs …
⛔ 배너 스캔에는 --join 이 반드시 있어야 한다                       → exit 2

$ … --join <상세 보유 0건>
⛔ 상세 보유 행이 0건이다 — **빈 목록은 전량이 아니다.** …          → exit 2

$ … --join <2행: 상세 2장 + 상세 None>
[1/5] URL 추출 2장 (상품 2 · 상세 미조회 1)
[2/5] 다운로드 0장 (실패 2)
    실패 호스트별: zzcdn.example 2
※ 판정불가 상품 2건 — …  **'배너 없음' 이 아니다**                  → exit 3

특징·썸네일 단계 (실제 이미지 3장, 캐시 히트로 네트워크 0):
  790x880  배너 모양   → 무내용 **아님** · 썸네일 180x200 webp 158B
  1200x40  구분선      → **무내용** · 썸네일 1200x40 webp 164B (키우지 않음)
  깨진 바이트           → 미판정 "이미지를 알아볼 수 없다 (디코딩 실패)" · w/h null
  집계 {"장":3,"판정완료":1,"미판정":2,"무내용":1,"스킵상품":1}
  캐시 히트 재다운로드 0 (`한장받기` → (True, "캐시"))
```

## Decisions Made

- **404 사유 문구를 사실대로 적었다.** RESEARCH §산출물 계약 예시는 `"HTTP 404 (3회 재시도)"` 인데, 같은 문서 §소요시간이 "404 는 즉시 포기(재시도 무의미)" 라고 전략을 정한다. 즉시 포기하면서 "3회 재시도" 라고 적는 것은 **안 한 일을 했다고 적는 것**이다. `"HTTP 404 (재시도 무의미 — 영구)"` 로 썼다. 다른 코드(타임아웃·5xx)는 실제로 3회 돌므로 `"({n}회 재시도)"` 를 그대로 쓴다.
- **실패 판별식을 `미판정 + 사유` 로 잡았다.** 판정은 04-04 가 얹으므로 이 플랜이 끝난 시점에도 멀쩡히 받은 장은 `미판정` 이다(사유 `None`). 사유 없는 미판정을 실패로 세면 **전 상품이 '판정불가'** 가 된다. 사유를 들고 오는 것이 실패라는 이 파일의 규약이 그대로 판별식이 됐고, 04-04 가 올라와도 그대로 참이다.
- **`무내용` 은 여기서 내리고 `제거율`·D-07/D-08 은 안 건드렸다.** 무내용은 픽셀 기하 규칙이라 특징 단계의 일이다. 반면 제거율의 분자는 배너 판정이라 지금 계산하면 부분값이 나오고, 그 부분값으로 스킵을 걸면 멀쩡한 상품이 버려진다. `제거율: null` 로 남겼다 — **`null` = 아직 모른다.**
- **종횡비를 `긴변/짧은변` 으로 쟀다.** 플랜 문구는 "종횡비"만 적었다. `w/h` 로 재면 세로 구분선(200x1200)을 못 잡는다. 긴변/짧은변은 엄격히 더 많이 잡는데, 배너(0.89 → 1.12)는 어느 정의로도 6.0 근처에 못 가므로 **미탐 위험이 0 이면서 탐지만 넓어진다.**
- **썸네일을 키우지 않는다.** 실측 후 발견 — 아래 Deviations 3.
- **CLI 가 `webapp.settings` 를 import 하지 않는다.** `settings` → `paths` → `workspace.toml` 사슬에 CLI 를 묶으면 터미널 실행이 PC별 설정 파일 때문에 죽는다. 대신 폴백 dict 를 두고 **`test_CLI_폴백이_settings와_같다`** 가 8키 드리프트를 기계로 잡는다. 웹앱 잡은 어차피 전 값을 명시적으로 넘긴다.
- **`webapp.state` 를 같이 import 했다.** 플랜의 `key_links` 는 `from webapp import banner` 만 요구한다(문자열로 충족). `상세상태` 판정 순서(AI생성 먼저, 번역 나중)를 여기서 재현하면 "이미 가공된 상품에 크레딧을 다시 태우는" 그 조용한 버그가 두 번째 사본을 갖게 된다.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `PIL` 을 모듈 최상단에 두면 테스트가 collect 단계에서 죽는다**

- **Found during:** Task 2 (테스트 설계 시점)
- **Issue:** 플랜 Task 3 는 *"`from PIL import Image` 는 이 파일에서만(CLI)"* 이라 적고, Task 2 는 *"`Vision` import 는 04-04 에서 `ocr` 함수 안쪽 지연 import"* 라는 제약만 못박았다. 그런데 **`.venv-web` 에 Pillow 도 없다**(실측: `find_spec('PIL') is None`). 테스트가 `importlib` 로 `banner_scan.py` 를 로드하므로, `PIL` 이 최상단에 있으면 `test_banner_scan.py` 전체가 collect 단계에서 ImportError 다 — Vision 과 **똑같은** 이유인데 플랜이 Vision 만 적었다.
- **Fix:** `PIL` import 를 `특징과썸네일()` 안쪽 지연 import 로 넣고, 그 이유를 함수 docstring 과 테스트 파일 헤더 양쪽에 적었다. 04-04 가 Vision 에 같은 처리를 하도록 테스트 파일 주석이 지시한다.
- **Files modified:** `banner_scan.py` · `webapp/tests/test_banner_scan.py`
- **Verification:** `.venv-web` 에서 10개 green. `.venv` 에서 e2e 정상
- **Committed in:** `d630605`

**2. [Rule 1 - Bug] `집계내기` 가 미판정 장을 두 번 셌다**

- **Found during:** Task 1 실측
- **Issue:** `banner.미판정` 의 값이 문자열 `"미판정"` 이고 집계 dict 에도 같은 키가 있어서, `칸[판정] += 1` 과 `칸["미판정"] += 1` 이 같은 칸을 두 번 올렸다. **실측: 장 2개인데 미판정 4.** 이 숫자가 화면과 게이트 보고에 그대로 나간다.
- **Fix:** 미판정을 판정별 칸에서 분리하고 `continue` 로 갈랐다. 판정별 칸은 `배너`/`제품`/`무내용` 3종만 받는다.
- **Files modified:** `banner_scan.py`
- **Verification:** 같은 입력 재실행 → `미판정 2` (장 수와 일치). e2e 집계도 `장 3 = 판정완료 1 + 미판정 2`
- **Committed in:** `ef9dc64`

**3. [Rule 1 - Bug] 썸네일이 짧은 장을 **확대**해 원본보다 커졌다**

- **Found during:** Task 3 실측
- **Issue:** "높이 200px 고정" 을 곧이곧대로 구현하면 구분선(실측 1200x40)이 **6000x200** 이 된다. 정보는 하나도 안 늘고 바이트만 는다(2,280B vs 원본 164B 수준). 실측 코퍼스에 무내용 21장이 있으니 매 회차 반복된다. 썸네일의 존재 이유(원본의 1/71)와 정반대다.
- **Fix:** `실제높이 = min(썸높이, 원본높이)`. 원본보다 낮을 때만 줄인다. 검수 스트립의 "한 줄 높이 일정" 은 **상한선** 얘기라는 것을 주석에 적었다.
- **Files modified:** `banner_scan.py`
- **Verification:** 1200x40 → 썸네일 1200x40 (164B). 790x880 → 180x200 (158B, 높이 고정 유지)
- **Committed in:** `d630605`

**4. [Rule 2 - Missing critical] `--keep-runs 0` 이 캐시를 통째로 밀 수 있었다**

- **Found during:** Task 2
- **Issue:** 플랜은 *"`--keep-runs` 개를 넘는 오래된 회차를 지운다"* 까지만 적었다. `0` 이 오면 그대로 전량 삭제다. 이 저장소가 네 번 막은 "빈 값이 전량이 되는 경로"의 **삭제판**인데, 앞선 네 곳과 달리 **되돌릴 수 없다**(271MB 재다운로드).
- **Fix:** `남길회차 < 1` 이면 `ValueError`. `main` 이 잡아 exit 2 로 내린다. 추가로 **돌고 있는 회차를 `보호` 인자로 절대 안 지우고**(재실행이 자기 캐시를 미는 경로), 심링크·파일은 건드리지 않는다(캐시 루트를 청소기로 미는 경로).
- **Files modified:** `banner_scan.py` · `webapp/tests/test_banner_scan.py`
- **Verification:** `test_회차정리_0은_전부_지워라가_아니다` · `test_회차정리_지금_회차는_안_지운다` green
- **Committed in:** `05a4437`

**5. [Rule 2 - Missing critical] CLI 폴백 기본값이 `settings` 와 조용히 어긋날 수 있었다 (S-4)**

- **Found during:** Task 1
- **Issue:** 플랜 `<interfaces>` 는 플래그에 기본값(`실측 8`, `6.0`, `32` …)을 적었는데, `settings.py` Phase 4 블록은 *"이 숫자들을 리터럴로 베끼지 마라 — 베끼면 workspace.toml 을 고쳐도 동작이 안 바뀐다"* 고 명시한다. 그렇다고 CLI 가 `settings` 를 import 하면 `paths`→`workspace.toml` 에 묶여 터미널 실행이 환경 문제로 죽는다.
- **Fix:** 폴백 dict 를 한 곳에 모으고(키 이름이 `banner_` 접두만 뗀 형태), **`test_CLI_폴백이_settings와_같다`** 가 8키를 `settings.DEFAULTS` 와 전수 대조한다. 어긋나면 터진다. 정본은 여전히 `settings` 고, 웹앱 잡은 전 값을 명시적으로 넘긴다.
- **Files modified:** `banner_scan.py` · `webapp/tests/test_banner_scan.py`
- **Verification:** `test_CLI_폴백이_settings와_같다` green (8키 전부 매칭)
- **Committed in:** `05a4437`

**6. [Rule 2 - Missing critical] 금지 토큰을 주석에 글자로 남기고 있었다**

- **Found during:** Task 1 acceptance 확인
- **Issue:** 불사자 MCP 클라이언트 모듈명을 *"이걸 import 하지 마라"* 는 주석에 글자로 적었다 → acceptance 의 `grep -F` 가 2줄을 잡았다. `test_argv.py:205-207` 이 이미 세운 규율("가드가 감시하는 문자열을 감시 대상이 들고 있으면 '주석에는 있어도 된다' 는 예외가 생기고, 그 예외가 언젠가 진짜 코드로 자란다")과 정확히 같은 함정이다.
- **Fix:** 두 자리 모두 모듈명 없이 서술로 바꾸고, **왜 이름을 안 적는지**를 docstring 에 남겼다.
- **Files modified:** `banner_scan.py`
- **Verification:** `grep -cF` → 0
- **Committed in:** `ef9dc64`

**7. [Rule 1 - Bug] 플랜이 지시한 테스트 경계값이 실제로는 반대 결과다**

- **Found during:** Task 3
- **Issue:** "짧은 변 32px 경계" 회귀를 처음에 `무내용인가(800, 33)` → `False` 로 잡았다. 실제로는 `800/33 = 24.2 >= 6.0` 이라 **종횡비 규칙에 걸려 True** 다. 그대로 뒀으면 테스트가 빨갛고, 고치려면 규칙을 망가뜨려야 했다.
- **Fix:** 짧은 변만 보도록 종횡비가 6 미만인 모양(`150x33`, 비 4.5)으로 케이스를 바꿨다. 32px 경계 포함은 `160x32`(비 5.0)로 확인한다. 규칙은 그대로다.
- **Files modified:** `webapp/tests/test_banner_scan.py`
- **Verification:** `test_무내용인가_경계값` green (경계 포함 여부까지)
- **Committed in:** `d630605`

**8. [Rule 3 - Blocking] 워크트리에 `.venv`·`.venv-web`·`workspace.toml` 이 없어 검증 불가**

- **Found during:** 시작 전
- **Issue:** 04-01·04-02 가 겪은 것과 같다. 셋 다 gitignore 대상이라 병렬 워크트리에 존재하지 않는다.
- **Fix:** 04-02 의 해법을 그대로 썼다 — `.venv`/`.venv-web` 을 **실제 디렉터리로 만들고** 안의 `bin`·`lib`·`pyvenv.cfg` 만 본 저장소로 심링크(디렉터리라서 `.gitignore` 가 가린다), `workspace.toml` 은 사본. 셋 다 커밋되지 않았다 — 매 커밋 전 `git diff --cached --name-only` 확인.
- **Files modified:** 없음(커밋된 것 0건)
- **Verification:** 3커밋 전부 의도한 파일만. `git diff --diff-filter=D 247464a..HEAD` → 삭제 0건
- **Committed in:** 해당 없음

---

**Total deviations:** 8 auto-fixed (Rule 1 ×3 · Rule 2 ×3 · Rule 3 ×2)
**Impact on plan:** 범위 확장 없음. 1·8 은 환경/제약 정정, 2·3·7 은 실측으로 잡은 버그, 4·5·6 은 플랜이 세운 규율이 목적을 절반만 지키던 자리를 메운 것이다.

## Issues Encountered

- **이 플랜이 끝난 상태에서 정상 입력도 exit 3 이 나올 수 있다.** 판정(배너/제품)은 04-04 가 얹으므로, 무내용 장이 한 장도 없는 회차는 `판정완료 = 0` 이 되어 exit 3 이다. **이건 고장이 아니라 정직한 신호다** — 파이프라인이 미완이고 그 산출물로 Phase 5 를 돌리면 안 된다는 뜻이다. `전부특징` docstring 에 적어 뒀다. 04-04 가 어휘군 판정을 넣으면 자연히 해소된다.
- **`pytest -q` 가 여전히 요약 줄을 안 찍는다**(04-02 가 겪은 것과 같음). `-q` 없이 돌려 `387 passed` 를 확인했다.
- **플랜 `<verify>` 의 Task 1 명령이 `.venv/bin/python3` 를 쓴다.** `banner_scan.py` 의 인자 검증 단계는 stdlib 뿐이라 `.venv-web` 으로도 돌지만, 원래 돌 인터프리터가 `.venv` 라 그대로 따랐다.

## Known Stubs

없다. 이 플랜이 만든 함수는 전부 실제 동작을 한다.

다만 **웨이브 경계로 비어 있는 칸**이 셋 있다 — stub 이 아니라 *아직 계산할 근거가 없는 값*이고, 전부 `null` 로 남겼다(`null` = 모른다):

| 칸 | 누가 채우나 | 왜 지금 못 채우나 |
|---|---|---|
| `장[].판정` 의 배너/제품 | 04-04 | OCR + 어휘군이 그 웨이브다 |
| `상품[].제거율` | 04-04 | 분자가 배너 판정이다. 부분값으로 스킵을 걸면 멀쩡한 상품이 버려진다 |
| `상품[].스킵사유` 의 `잔여부족`/`제거율초과` | 04-04 | 위와 같다. 지금 채워지는 값은 `판정불가` 뿐이다 |

`제품이미지` 도 빈 배열이다 — 04-04 가 채운다. 그 전까지 `banner.제품이미지목록` 이 "제품 이미지가 0장이다" 로 막는데, **그게 맞는 동작이다.**

## Threat Flags

없다. 새 네트워크 **엔드포인트**·인증 경로·스키마 변경 0건. 나가는 방향의 HTTP 요청이 새로 생겼지만 그건 플랜의 `<threat_model>` 이 이미 등록한 경계다.

위협 등록부 5건 처리 결과:

| Threat ID | Disposition | 처리 |
|---|---|---|
| T-4-06 (SSRF · 다운로더) | **mitigate 완료** | `허용URL인가()` 단일 관문. 거부 18케이스 회귀. 자격증명 박힌 호스트까지 막았다(플랜 목록 밖 — 사람 눈을 속이는 모양) |
| T-4-07 (캐시 271MB) | **mitigate 완료** | 받기 전에 `회차정리()`. 지운 회차를 로그로 보고. `keep_runs=0` 예외 + 현재 회차 보호(플랜 목록 밖) |
| T-4-08 (Pillow decompression bomb) | **mitigate 완료** | `MAX_IMAGE_PIXELS` 기본 제한 유지(`= None` 0줄). `DecompressionBombError` 는 그 장만 미판정, 프로세스 계속 |
| T-4-01 (실패 처리 Tampering) | **mitigate 완료** | 404·타임아웃·거부·디코딩 실패 전부 미판정 + 사유. `except: pass` 0줄. 전량 미판정만 exit 3 |
| T-4-12 (CDN 응답 위조) | accept (그대로) | stdlib 기본 인증서 체인. 받은 바이트는 판정에만 쓰이고 실행되지 않는다 |

## Next Phase Readiness

**04-04(판정)가 바로 쓸 수 있는 것 / 반드시 지킬 것:**

- **`Vision` import 는 `ocr()` 함수 안쪽 지연 import 다.** 최상단에 두면 `.venv-web` 으로 도는 `test_banner_scan.py` 가 collect 단계에서 통째로 깨진다(Deviations 1 이 `PIL` 에서 실제로 겪었다). `pytest.importorskip` 도 쓰지 마라 — 미설치는 **실패**여야 한다(04-01 이 세운 규율).
- **`supportedRevisions()` 는 클래스 메서드다** (04-01 실측). `setRevision_(3)` 은 명시적으로 박아라 — 기본값이 이미 3 이라 안 박아도 오늘은 같은 결과가 나온다. 그게 D-10 이 경고한 바로 그 상황이다.
- 장 dict 에 **`엔트로피`·`단색비율`이 이미 들어 있다.** 891장을 다시 디코딩하지 마라. 원본은 `원본경로(cache, run_dir, 상품순번, 장순번)` 에 그대로 있다(캐시 히트 확인됨).
- **판정을 덮어쓸 때 `미판정 + 사유` 인 장은 건드리지 마라.** 그건 못 받은 장이다. 배너/제품을 찍는 대상은 `판정 == 미판정 and 사유 is None` 인 장뿐이다.
- `제거율`·D-07/D-08 스킵은 **04-04 가 채운다.** `스킵사유` 는 `판정불가` 가 이미 들어간 상품을 덮지 마라 — 판정불가가 더 강한 사실이다.
- `--vision-revision` · `--skip-min-keep` · `--skip-max-removal` · `--lexicon-version` 플래그는 **이미 파싱되고 `판정규칙` 칸에 실린다.** 새로 추가하지 말고 그대로 읽어라.
- **어휘군 중국어 절반은 회귀 정답지로 검증되지 않는다** (04-02 Deviations 1). 근거를 따로 마련하거나 "미검증" 이라고 적어라.

**04-05(`BannerArgv`)가 지킬 것:**

- 위 §CLI 계약의 플래그 이름을 글자 그대로. 전부 `default` 가 있으므로 웹앱이 안 넘겨도 죽지는 않지만, **전 값을 명시적으로 넘겨라** — 안 넘기면 `workspace.toml` 을 고쳐도 동작이 안 바뀐다(S-4).
- `--keep-runs` 에 0 을 넘기지 마라. 자식이 exit 2 로 죽는다(의도된 가드).

**04-06(라우트)이 지킬 것:**

- `장[].썸네일` 에는 **파일명만** 있다. 경로는 서버가 `(산출물, 상품순번, 장순번)` 정수 인덱스로 만들어라 — `썸네일경로()` 가 그 규약의 정본이다.

**막는 것 없음.** 전 스위트 387 green.

---
*Phase: 04-banner-detection*
*Completed: 2026-09-22*

## Self-Check: PASSED

- 파일 4개 전부 존재: `banner_scan.py` · `bulsaja_scan.py` · `webapp/tests/test_banner_scan.py` · `04-03-SUMMARY.md`
- 커밋 4개 전부 존재: `ef9dc64` · `05a4437` · `d630605` · `ef5e39f`
- 삭제된 파일 0건 (`git diff --diff-filter=D 247464a..HEAD`)
- 커밋되지 않아야 할 것이 안 들어갔다: `.venv`/`.venv-web` 디렉터리 · `workspace.toml` 사본 전부 staged 0건. 워크트리 밖 임시 e2e 산출물(`scratchpad/`)도 저장소에 0건
- 공유 산출물 미수정: `STATE.md` · `ROADMAP.md` · `REQUIREMENTS.md` 변경 0건
- 전 스위트 387 green (exit 0) · `banner_scan.py` 에 `import requests` 0건 · 불사자 MCP 모듈 토큰 0건 · `MAX_IMAGE_PIXELS = None` 0건 · `except …: pass` 는 `말하기`/`오류말하기` 안쪽 2곳뿐
