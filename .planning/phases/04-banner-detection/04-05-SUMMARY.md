---
phase: 04-banner-detection
plan: 05
subsystem: job-engine
tags: [banner, jobs, argv, sqlite-ddl, route, caffeinate, singleton, csrf]

# Dependency graph
requires:
  - phase: 04-banner-detection
    plan: 01
    provides: "`settings.DEFAULTS` Phase 4 배너 키 11개 (임계값·경로·리비전의 정본)"
  - phase: 04-banner-detection
    plan: 03
    provides: "`banner_scan.py` CLI 플래그 계약 14개 · 종료코드 0/2/3 · 캐시 파일명 규약"
  - phase: 04-banner-detection
    plan: 04
    provides: "종료코드 4(Vision 미설치) · 산출물 `판정규칙` 블록이 인자에서 온다는 계약"
  - phase: 03-join-detail-state
    provides: "잡 엔진(`_reap`·`start_new_session`·`caffeinate -i`·로그 tail·SSE) · `latest_done` · `_override_targets`"
provides:
  - "`jobs.KINDS` 의 `banner_scan` — 올바른 집합에만 등록(`SINGLETON_KINDS` O · `WRITE_KINDS`/`BULSAJA_KINDS` X)"
  - "`banner_label`·`banner_confirm` DDL — 사람 라벨 저장소. 스키마 정본이 `jobs.DDL` 한 곳"
  - "`argv.BannerArgv` + `argv.BANNER_SCAN` — 배너 argv 조립의 유일한 자리"
  - "`argv.PlainArg` — 설정에서 온 문자열이 자식 argparse 에 플래그로 읽히는 것을 막는 타입"
  - "`jobs.banner_dir()` — 원본 캐시·썸네일 루트 계산(회차 하위는 자식이 만든다)"
  - "`POST /jobs/banner/scan` — 대상을 서버가 고르는 접수 라우트(409 로 순서를 알려준다)"
affects: [04-06, 04-07, 04-08]

# Tech tracking
tech-stack:
  added: []          # 신규 패키지 0. 기존 잡 엔진·Pydantic·stdlib sqlite3 만 쓴다
  patterns:
    - "같은 집합에 **다른 사유**로 들어가는 멤버는 사유를 따로 적는다 — `SINGLETON_KINDS` 가 이제 레이트리밋과 이중 다운로드 두 이유를 담는다"
    - "가드 멤버십은 **집합 검사 + 행동 검사 두 벌**로 고정한다 — 집합이 맞아도 다른 가드를 잘못 넓히면 같은 증상이 난다"
    - "조립한 argv 를 **실제 자식에 한 번 태워** 플래그 드리프트를 확인한다(빈 입력 → exit 2, 네트워크 0)"
    - "선례가 있는 예외 메시지라도 **그 흐름에 없는 안내**면 라우트에서 미리 잡는다 (\"미리보기부터 다시 해라\")"

key-files:
  created: []
  modified:
    - webapp/jobs.py
    - webapp/argv.py
    - webapp/routes/jobs.py
    - webapp/tests/test_jobs.py
    - webapp/tests/test_argv.py
    - webapp/tests/test_routes_jobs.py

key-decisions:
  - "`banner_scan` 을 `WRITE_KINDS`·`BULSAJA_KINDS` 에 넣지 않았다. 멤버십 테스트 1개 + **행동 테스트 2개**(jobs 층·HTTP 층)로 고정했다 — 집합만 보면 다른 가드를 잘못 넓힌 회귀가 안 보인다"
  - "`SINGLETON_KINDS` 의 사유가 이제 **두 가지**다. 배너 쪽은 레이트리밋이 아니라 271MB 이중 다운로드 + 같은 캐시 파일명 동시쓰기다. 주석에 그 갈림을 적었다"
  - "대상을 `only_ads` 가 아니라 `targets_path_override` 로 넘긴다 — 조인 산출물을 **새로 쓰지 않고 그대로 가리킨다**. 다시 만들면 조인 스캔이 본 것과 배너 스캔이 읽는 것이 갈라진다(D-11)"
  - "라우트가 조인 산출물을 **읽지 않는다**. 인덱스 라우트와 다르다 — 거긴 대상 계산이 필요해서 읽지만, 여기는 경로 하나를 넘길 뿐이고 모양 검증은 자식이 한 번만 한다(S-1)"
  - "`banner_dir()` 이 회차 하위 디렉터리를 **안 만든다**. 웹앱이 미리 만들면 `회차정리()` 가 방금 지운 회차 폴더가 빈 채로 되살아나 '남길 회차 수' 계산이 흐려진다"
  - "`PlainArg` 를 `Nick` 과 제약이 같은데도 따로 뒀다 — 뜻이 다른 두 값이 한 타입을 공유하면 한쪽 규칙을 고칠 때 다른 쪽이 소리 없이 따라 바뀐다"
  - "산출물 분기를 `BULSAJA_접두` 에 얹지 않고 따로 뒀다. 얹으면 다음 사람이 '배너도 불사자 잡' 으로 읽고 `BULSAJA_KINDS` 에 넣는다"

patterns-established:
  - "🔴 등급 가드는 **두 층에서 각각 문다** — `test_jobs.py` 가 `create_job` 을, `test_routes_jobs.py` 가 실제 HTTP 응답을 본다"
  - "`엿듣기`(create_job 가로채기) 픽스처는 중복·계정 가드 검증에 쓸 수 없다 — kind 를 synthetic 으로 바꿔 가드를 통째로 우회한다. 그런 테스트는 `spawn` 만 가짜로 바꾼다"
  - "스키마 가드를 넓힐 때마다 **판별 기준을 다시 적는다** — '재생성이 공짜가 아니면 캐시가 아니라 기록이다' 가 세 번째로 적용됐다"

requirements-completed: [BANNER-01]
requirements-partial: [BANNER-02b]

# Metrics
duration: 약 40min
completed: 2026-09-22
---

# Phase 4 Plan 05: 배너 스캔을 잡 엔진에 붙이기 Summary

**화면 버튼 하나로 배너 스캔이 돌고 브라우저를 닫아도 완주하되, 그 4분 동안 입찰가 버튼이 죽지 않는다 — 잡 종류를 올바른 집합에만 등록하고, 그 사실을 집합 검사가 아니라 두 층의 행동 테스트로 고정했다.**

## Performance

- **Duration:** 약 40분
- **Tasks:** 3/3
- **Files modified:** 6 (생성 0 · 수정 6)
- **Tests:** `.venv-web` 388 → **407 green** (신규 19) · `.venv` cli **4 green** (변화 없음)
- **신규 패키지 0 · MCP 호출 0회 · 크레딧 0 · 네트워크 0**

## Accomplishments

- **이 플랜의 1순위 위험을 테스트로 닫았다.** `banner_scan` 은 `WRITE_KINDS`·`BULSAJA_KINDS` 어디에도 없고, `SINGLETON_KINDS` 에만 있다. 이것을 **세 벌**로 고정했다: ① 집합 멤버십 ② `create_job` 층 행동(배너가 도는 중에 `prep` 이 들어간다) ③ HTTP 층 행동(`POST /jobs/prep` 이 200 이다). 집합만 보면 다른 가드를 잘못 넓힌 회귀가 안 보인다.
- **조립한 argv 를 실제 자식에 태워 확인했다.** 14개 플래그 전부가 파싱되고 빈 조인 입력에 대해 `exit 2` + 사람이 읽는 사유가 stdout 에 나왔다. argparse 의 "unrecognized arguments" 가 아니다 — **플래그 이름 드리프트가 오늘 실측으로 0건**이다. 네트워크 0 · 크레딧 0.
- **라벨 테이블 2종이 `jobs.DDL` 한 곳에서만 생긴다.** `banner_scan.py` 는 SQLite 를 아예 안 만진다. 스키마 가드(`test_스키마는_기록_테이블만_있다`)를 **사유를 다시 적으며** 넓혔고, 컬럼·기본키·기계 판정 부재까지 회귀로 고정했다.
- **`banner_confirm` 이 `banner_label` 과 갈라져 있다.** "이 장을 뒤집었다" 와 "이 줄을 다 봤다" 는 다른 사실이다 — 합치면 확인 표시가 라벨로 둔갑해 게이트 집계 분모가 조용히 틀어진다. 테스트가 두 테이블의 컬럼 집합을 각각 못박는다.
- **대상을 서버가 고른다.** 본문에 `targets`·`only_ads` 를 실어 보내도 `JobReq` 가 안 받고, 응답 어디에도 그 값이 안 나타난다(회귀로 확인). 넘어가는 것은 `latest_done("bulsaja_scan").result_path` 하나뿐이고, 그것도 **새로 쓰지 않고 그대로 가리킨다**.
- **4분짜리 잡에 `caffeinate -i` 가 실제로 붙는다.** 03-07 이 실측으로 발견한 구멍(필드는 있는데 `_build_argv` 가 안 넘김)이 여기서 반복되지 않도록, 조립 층이 아니라 **잡 층에서** 확인한다.

## Task Commits

| # | 작업 | 커밋 | 종류 |
|---|---|---|---|
| 1 | `BannerArgv` + `BANNER_SCAN` + `PlainArg` (+테스트 4) | `a313cc8` | feat |
| 2 | `jobs.py` 네 군데 + 라벨 DDL 2종 (+테스트 8) | `90d1f4d` | feat |
| 3 | `POST /jobs/banner/scan` (+테스트 7) | `98b787e` | feat |

## 🔴 잡 종류 배치 — 무엇을 어떻게 증명했나

플랜이 *"이 플랜의 위험은 코드가 아니라 잡 종류를 잘못된 집합에 넣는 것"* 이라고 지목한 자리다.

| 집합 | `banner_scan` | 근거 | 지키는 테스트 |
|---|---|---|---|
| `KINDS` / `JobKind` | **있다** (둘 다) | 하나만 고치면 타입 검사는 통과하는데 런타임이 거부한다 | `test_배너잡_kind_가_등록돼_있다` |
| `WRITE_KINDS` | **없다** | 광고·불사자에 한 글자도 안 쓴다. 넣으면 4분 동안 입찰가 인상이 409 → 사람이 가드를 끈다 (T-4-19) | `test_배너잡은_전역_쓰기가드에_안_들어간다` · `test_배너잡이_도는_동안에도_쓰기잡이_들어간다` · `test_배너스캔이_도는_동안_쓰기버튼이_안_막힌다` |
| `BULSAJA_KINDS` | **없다** | MCP 0회 → ENG-08 계정 사전점검의 대상 자체가 아니다(계정이 뭐든 판정이 같다) | 같은 테스트 |
| `SINGLETON_KINDS` | **있다** | **레이트리밋이 아니다.** 271MB 이중 다운로드 + 같은 회차 캐시 파일명 동시쓰기 | `test_배너잡_둘은_동시에_안_돈다` · `test_배너스캔_중복은_409` |

**주의해서 읽을 것:** `BULSAJA_KINDS` 와 `SINGLETON_KINDS` 는 Phase 3 까지 멤버가 같았고, 그래서 기존 주석이 *"멤버가 같지만 뜻이 다르다"* 라고 경고하고 있었다. 이 플랜이 **둘을 실제로 갈라놨다** — 이제 `SINGLETON_KINDS` 가 한 멤버 더 많다. 주석을 그 사실에 맞춰 고쳤고, 새 멤버의 사유를 🔵 블록으로 따로 적었다. 안 적으면 다음 사람이 배너 스캔도 레이트리밋 때문에 들어간 줄 안다.

## Files Modified

- **`webapp/jobs.py`** (900 → 1,025행)
  - 모듈 docstring 에 배너 잡 표 1행 + "MCP 0회" 근거
  - `JobKind`/`KINDS` 에 `banner_scan`
  - `WRITE_KINDS` 주석에 금지 근거 4줄 · `SINGLETON_KINDS` 에 멤버 + 🔵 사유 블록
  - `DDL` 에 `banner_label`·`banner_confirm` + `※` 판별 근거 6블록(키가 URL 이 아닌 이유 D-01a 포함)
  - `banner_dir()` 신규 — 캐시·썸네일 루트. 회차 하위는 만들지 않는다
  - `_수면방지_프리픽스` 를 `("bulsaja_index", "banner_scan")` 으로 확장 + 실측 4분 12초 근거
  - `_build_argv` 에 `banner_scan` 분기(가드 3종 + `settings.cfg` 8키)
  - `create_job` 의 `result_path` 분기 추가 — `<회차>/web/banner_<job_id>.json`
- **`webapp/argv.py`** (196 → 264행) — `BANNER_SCAN` · `PlainArg` · `BannerArgv`(13 필수 필드 + `prefix`)
- **`webapp/routes/jobs.py`** (886 → 932행) — 목차 1행 + `post_banner_scan`
- **`webapp/tests/test_jobs.py`** (1,071 → 1,250행) — 스키마 가드 확장 · 라벨 DDL 회귀 · 배너 잡 7개
- **`webapp/tests/test_argv.py`** (457 → 566행) — 배너 argv 4개
- **`webapp/tests/test_routes_jobs.py`** (470 → 619행) — `안띄운다`·`직전조인` 픽스처 + 라우트 6개

## 실측 (네트워크 0 · 크레딧 0)

```
$ <조립한 argv 14플래그> --join <상세 0건 조인> …
⛔ 상세 보유 행이 0건이다 — **빈 목록은 전량이 아니다.** 조인 스캔을 먼저 돌려라   → exit 2
```

argparse 가 "unrecognized arguments" 로 죽은 것이 **아니다** — 14개 플래그가 전부 파싱된 뒤 입력 검증 단계에서 의도대로 거부됐다. 04-03 이 확정한 CLI 계약과 `BannerArgv` 사이에 드리프트가 0 이라는 뜻이다.

라우트 3종 상태코드도 실제 응답으로 확인했다:

| 상황 | 코드 | 몸통 |
|---|---|---|
| 토큰 없음 / 타 사이트 Origin | **403** | (자식이 안 뜬다 — `엿듣기` 가 비어 있다) |
| `GET /jobs/banner/scan` | **405** | — |
| 조인 산출물 없음 | **409** | `조인 스캔을 먼저 돌려라 — 배너 스캔은 그 산출물을 입력으로 쓴다` |
| 같은 잡이 이미 도는 중 | **409** | `같은 작업이 이미 돌고 있다: … (banner_scan). 전역 쓰기 락이 아니라 …` |
| 정상 접수 | **200** | 잡 상태 (그 뒤 `POST /jobs/prep` 도 **200**) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] 플랜의 태스크 순서대로 커밋하면 중간 커밋이 깨진 트리다**

- **Found during:** Task 1 착수 시점
- **Issue:** 플랜은 Task 1(`jobs.py`) → Task 2(`argv.py`) 순이다. 그런데 Task 1 이 만드는 `_build_argv` 분기가 `argv_mod.BannerArgv` 를 부르는데, 그 클래스는 Task 2 에서야 생긴다. 그 순서로 커밋하면 **첫 커밋의 트리에 존재하지 않는 이름을 부르는 코드**가 들어간다(라우트가 아직 없어 실제로 터지지는 않지만, `git bisect` 나 부분 체크아웃이 그 커밋을 짚으면 원인 불명의 `AttributeError` 다).
- **Fix:** 커밋 순서만 뒤집었다 — `argv.py`(a313cc8) → `jobs.py`(90d1f4d) → 라우트(98b787e). 각 커밋이 단독으로 일관된 트리다. 플랜의 **내용**은 하나도 안 바꿨다.
- **Verification:** 세 커밋 각각에서 전 스위트가 green 인 순서다(검증은 최종 트리에서 수행)
- **Committed in:** 순서 자체가 조치

**2. [Rule 1 - Bug] 기존 스키마 가드가 라벨 테이블을 추가하는 순간 빨개진다**

- **Found during:** Task 2
- **Issue:** `test_스키마는_jobs_와_ss_index_뿐이다` 가 `이름들 - {"jobs", "ss_index"} == set()` 을 단언한다. 라벨 2종을 더하면 즉시 실패다. 플랜은 이 가드를 언급하지 않았다.
- **Fix:** 허용 집합을 넓히되 **Phase 3 이 한 그대로** 사유를 다시 적었다 — 판별 기준("재생성이 공짜가 아니면 캐시가 아니라 기록이다")을 세 항목 표로 만들고, 사람 라벨이 왜 기록인지(사람의 시간)와 기계 판정이 왜 여전히 금지인지(몇 분이면 다시 나오는 투영)를 나란히 적었다. 테스트 이름도 `test_스키마는_기록_테이블만_있다` 로 바꿔 **원칙이 무엇인지**가 이름에 남게 했다.
- **Verification:** 407 green
- **Committed in:** `90d1f4d`

**3. [Rule 2 - Missing critical] 어휘군 버전이 `--force` 모양이면 자식이 플래그로 읽는다**

- **Found during:** Task 2
- **Issue:** 플랜은 `lexicon_version: str` 로만 적었다. 이 값은 `workspace.toml` 에서 오므로 클라이언트가 못 만지지만, 값이 `-x` 나 `--force` 모양이면 **리스트 argv 라도** 자식의 argparse 가 그걸 옵션으로 파싱한다. `BulsajaArgv.expect_nick` 이 정확히 같은 이유로 `Nick` 타입을 쓰고 있고(T-3-13), 위협 등록부 T-4-17 이 *"인자는 `BannerArgv`(Pydantic) 로만 조립"* 을 요구한다 — 타입이 아무것도 안 막으면 그 문장이 장식이다.
- **Fix:** `PlainArg`(선행 하이픈·공백 거부, 길이 상한 40)를 만들어 붙였다. `Nick` 과 제약이 같지만 **이름을 따로 뒀다** — 뜻이 다른 두 값이 한 타입을 공유하면 한쪽 규칙을 고칠 때 다른 쪽이 소리 없이 따라 바뀐다(`BULSAJA_KINDS`/`SINGLETON_KINDS` 를 안 합치는 것과 같은 규율).
- **Verification:** `test_어휘군_버전이_플래그_모양이면_거부된다` green (5케이스)
- **Committed in:** `a313cc8`

**4. [Rule 2 - Missing critical] 조인 산출물이 사라진 경우의 안내가 틀린 흐름을 가리킨다**

- **Found during:** Task 3
- **Issue:** 파일이 사라지면 `_override_targets` 가 `ValueError("대상 파일이 사라졌다 — **미리보기부터 다시 해라**")` 를 던지고 `_작업만들기` 가 그걸 400 으로 번역한다. 그런데 **배너 스캔 흐름에는 미리보기가 없다.** 사용자가 존재하지 않는 버튼을 찾으러 간다. 그리고 상태코드도 틀리다 — 요청은 멀쩡하고 순서가 아직 아니므로 409 다.
- **Fix:** 라우트에서 `Path(산출물).is_file()` 을 먼저 보고 409 + `"조인 산출물 파일이 사라졌다 — 조인 스캔을 다시 돌려라"` 를 낸다. 공용 예외 메시지는 안 건드렸다(입찰가 흐름에서는 그 문구가 맞다).
- **Verification:** 라우트 6개 green
- **Committed in:** `98b787e`

**5. [Rule 2 - Missing critical] 플랜의 중복 테스트가 `엿듣기` 로는 아무것도 검증하지 못한다**

- **Found during:** Task 3
- **Issue:** 플랜 Task 3 테스트 ④가 *"같은 kind 가 이미 도는 중이면 409 (`SINGLETON_KINDS` 회귀)"* 다. 그런데 이 파일의 `엿듣기` 픽스처는 `create_job` 을 가로채 **`kind="synthetic"` 으로 바꿔** 진짜를 부른다 — 중복 가드가 통째로 우회되어 두 번째 요청도 200 이 된다. 픽스처를 그대로 쓰면 테스트가 빨갛고, 통과시키려면 가드를 망가뜨려야 한다. (`test_계정불일치면_409` 가 이미 같은 함정을 주석으로 경고하고 있다.)
- **Fix:** `안띄운다` 픽스처를 이 파일에도 두고(spawn 만 가짜) 진짜 `create_job` 을 돌렸다. 그 차이를 픽스처 docstring 에 적었다. 덤으로 이 픽스처가 있어서 **"배너가 도는 동안 `POST /jobs/prep` 이 200"** 이라는 HTTP 층 행동 회귀를 추가할 수 있었다 — 성공기준 2의 가장 직접적인 증거다.
- **Verification:** `test_배너스캔_중복은_409` · `test_배너스캔이_도는_동안_쓰기버튼이_안_막힌다` green
- **Committed in:** `98b787e`

**6. [Rule 2 - Missing critical] 회차 하위 캐시 폴더를 웹앱이 만들면 회차 회전이 흐려진다**

- **Found during:** Task 1
- **Issue:** 플랜은 *"캐시·썸네일은 설정 경로 아래 `<run_dir>/` 하위다"* 라고 적었다. 그대로 읽으면 `banner_dir()` 이 회차 폴더까지 만들고 그 경로를 넘기게 된다. 그러면 ① `banner_scan.py` 가 받는 `--cache` 가 **루트**여야 하는 계약과 어긋나고(`회차정리(인자.cache, …)` 가 루트를 훑는다) ② 웹앱이 만든 빈 회차 폴더가 방금 지운 회차를 되살려 "남길 회차 수" 계산이 흐려진다.
- **Fix:** `banner_dir()` 은 **루트만** 계산하고 `mkdir` 을 하지 않는다. 회차 하위는 자식이 만든다. 그 이유를 함수 docstring 에 적었다.
- **Verification:** 실측 e2e 에서 `--cache` 루트로 자식이 정상 진행(회차 하위를 스스로 만든다)
- **Committed in:** `90d1f4d`

**7. [Rule 2 - Missing critical] `result_path` 가 없는 채로 조립이 진행될 수 있었다**

- **Found during:** Task 2
- **Issue:** 플랜은 `targets_path is None` 만 터뜨리라고 적었다. 그런데 `_build_argv` 는 `result_path=None` 으로도 호출 가능한 함수다(테스트·v2 스케줄러). 그 경우 `BannerArgv(out=None)` 이 `ValidationError` 를 내는데, 그건 `_작업만들기` 의 예외 표에 없어서 **500** 이 된다 — 사유가 "지금은 때가 아니다" 도 "요청이 틀렸다" 도 아닌 트레이스백이다.
- **Fix:** `run_dir` 과 `result_path` 에도 명시적 `ValueError` 가드를 더했다(400 으로 번역된다). 운영 경로에서는 `create_job` 이 항상 채우므로 동작 변화는 없고, 잘못 부르는 길만 닫혔다.
- **Verification:** 407 green
- **Committed in:** `90d1f4d`

**8. [Rule 3 - Blocking] 워크트리 base 가 지정된 커밋보다 뒤에 있었다**

- **Found during:** 시작 전 (worktree_branch_check)
- **Issue:** HEAD 가 `3118192`(phase 4 컨텍스트 기록 시점)였다. 지정 base 는 `2329d39`(wave 4 반영 후)라 **Wave 1~4 산출물이 통째로 없는 상태**였다(`.planning/phases/04-banner-detection/` 에 CONTEXT·DISCUSSION-LOG 두 파일뿐).
- **Fix:** 브랜치 검사(`worktree-agent-*` 네임스페이스 · 보호 ref 아님)를 **먼저** 통과시킨 뒤 `git reset --hard 2329d39`. 그 전에는 `reset` 을 돌리지 않았다. 04-04 가 겪은 것과 같은 일이다.
- **Verification:** `git log` → `2329d39 docs(phase-04): update tracking after wave 4`
- **Committed in:** 해당 없음

**9. [Rule 3 - Blocking] 워크트리에 `.venv`·`.venv-web`·`workspace.toml` 이 없다**

- **Found during:** 시작 전
- **Issue:** 04-01~04-04 와 같다. 셋 다 gitignore 대상이라 병렬 워크트리에 존재하지 않는다.
- **Fix:** 앞선 웨이브의 해법 그대로 — `.venv`/`.venv-web` 을 실제 디렉터리로 만들고 `bin`·`lib`·`pyvenv.cfg` 만 본 저장소로 심링크, `workspace.toml` 은 사본. **커밋 0건**(매 커밋 전 `git diff --cached --name-only` 확인).
- **Verification:** 3커밋 전부 의도한 파일만. base 이후 변경 파일 6개가 플랜 `files_modified` 와 정확히 일치
- **Committed in:** 해당 없음

---

**Total deviations:** 9 (Rule 1 ×1 · Rule 2 ×5 · Rule 3 ×3 — 그중 8·9 는 환경 정정)
**Impact on plan:** 범위 확장 없음. 1 은 커밋 순서만, 3~7 은 플랜이 세운 규율이 목적을 절반만 지키던 자리를 메운 것이다. 테스트가 13개(플랜) → 19개로 늘었고 그중 3개가 성공기준 2(쓰기 버튼이 안 막힌다)를 직접 겨눈다.

## Issues Encountered

- **플랜 Task 1 의 `<files>` 가 `webapp/jobs.py` 하나인데 검증은 `test_jobs.py` 를 돌린다.** 기존 테스트만으로는 새 집합 배치가 하나도 검증되지 않으므로(그리고 스키마 가드는 오히려 빨개지므로) `test_jobs.py` 를 같이 고쳤다 — 플랜 frontmatter 의 `files_modified` 에는 들어 있다.
- **`pytest -q` 가 요약 줄을 안 찍는 현상**(04-02·04-03·04-04 와 동일). `-q` 없이 돌려 숫자를 확인했다.
- **`webapp-banner/` 캐시·썸네일 디렉터리가 `.gitignore` 에 있는지 이 플랜은 확인하지 않았다.** 지금은 아무도 안 만든다(자식이 실제로 돌 때 생긴다). 04-08 이 실제 회차를 돌리기 전에 확인해야 한다 — 271MB × 2회차가 저장소에 들어가면 곤란하다.

## Known Stubs

없다. 이 플랜이 만든 것은 전부 실제로 동작한다 — 잡이 접수되고, argv 가 조립되고, 자식이 그 argv 를 받아 파싱한다(실측 확인).

**아직 아무도 쓰지 않는 것**(stub 이 아니라 *다음 웨이브의 입력*)이 둘 있다:

| 것 | 누가 쓰나 | 지금 상태 |
|---|---|---|
| `banner_label`·`banner_confirm` 테이블 | 04-06(검수 화면)·04-07 | `init_db()` 가 만든다. **읽고 쓰는 코드는 아직 없다** — 이 플랜의 범위가 DDL 까지다(플랜 §Task 1(d)) |
| `POST /jobs/banner/scan` 버튼 | 04-06(화면) | 라우트는 돈다. 누를 버튼이 화면에 아직 없다 |

## Threat Flags

새 **네트워크 엔드포인트가 하나 생겼다** — 하지만 플랜의 `<threat_model>` 이 이미 등록한 경계(T-4-05)이고, 기존 `security.guard` 미들웨어를 **예외 없이** 그대로 탄다. 등록부 밖의 새 surface 는 없다.

| Threat ID | Disposition | 처리 |
|---|---|---|
| T-4-05 (CSRF · 쓰기 라우트) | **mitigate 완료** | POST 전용(GET 405 회귀) · Origin + `sec-fetch-site` + 부팅 토큰 3층을 자동으로 탄다. 라우트에 예외 코드 0줄. 403 테스트 2종이 **자식이 안 떴다**(`엿듣기` 비어 있음)까지 확인 |
| T-4-17 (argv 주입) | **mitigate 완료** | `kind` 를 호출부가 고정 · 인자는 `BannerArgv`(Pydantic)로만 조립 · `lexicon_version` 에 `PlainArg` 적용 · `shell=True`/`os.system` 트리 가드 그대로 green |
| T-4-18 (화면이 대상을 고르는 것) | **mitigate 완료** | 대상은 `latest_done("bulsaja_scan").result_path` 하나. `JobReq` 필드가 `{run_dir, accounts}` 뿐이고 본문에 목록을 실어도 응답에 안 나타난다(회귀). `targets_path is None` → ValueError |
| T-4-19 (4분 잡이 쓰기 잡을 막는 것) | **mitigate 완료** | `WRITE_KINDS` 미등록 + **행동 테스트 2층**(jobs·HTTP). `SINGLETON_KINDS` 만 등록 |
| T-4-20 (사람 라벨과 기계 판정이 섞이는 것) | **mitigate 완료** | `banner_label` 에 기계 판정 컬럼 0개(회귀가 5개 낱말을 확인) · `banner_confirm` 별도 테이블 · DDL 정본 `jobs.py` 하나 |

## Next Phase Readiness

**04-06(검수 화면·라벨 라우트)이 바로 쓸 수 있는 것:**

- `jobs.latest_done("banner_scan", run_dir)` → 그 회차의 마지막 성공 배너 스캔. 산출물은 `result_path` = `<회차>/web/banner_<job_id>.json` 이다. **`web/banner_*.json` 을 glob 으로 뒤지지 마라** — 중간에 죽은 잡도 반쯤 쓴 파일을 남긴다.
- 라벨 테이블 2종이 이미 있다. **쓰는 쪽을 만들 때 `jobs.DDL` 에 컬럼을 더하지 말고 먼저 이 SUMMARY 의 `key-decisions` 를 읽어라** — 기계 판정을 복사하는 순간 진실이 둘이 되고 `test_라벨_테이블이_DDL_한곳에서_생긴다` 가 빨개진다(그게 그 테스트의 목적이다).
- 라벨 키는 `(run_dir, 타오바오상품번호, 이미지순번)` 이다. `판매자상품코드` 는 **사람이 앱에서 검색할 때 쓰는 표시값**이지 키가 아니다(물갈이로 재발급된다).
- 썸네일 경로는 서버가 `(산출물, 상품순번, 장순번)` 정수 인덱스로 만든다. 산출물의 `장[].썸네일` 에는 **파일명만** 있다(04-03 규약). 루트는 `jobs.banner_dir("banner_thumb_dir")` 이고 그 아래 `<run_dir>/` 이다.

**04-06 이 버튼을 붙일 때 지킬 것:**

- `hx-disabled-elt` 는 중복 방어의 대체물이 **아니다**(POST 왕복 중에만 잠근다). 진짜 방어는 `SINGLETON_KINDS` 이고 409 로 돌아온다 — 화면이 그 사유를 그대로 보여줘야 한다.
- 조인 산출물이 없을 때의 409 문구(`조인 스캔을 먼저 돌려라 …`)를 화면이 **그대로** 띄워라. 순서를 알려주는 것이 이 응답의 전부다.

**04-08(게이트)이 확인할 것:**

- **`webapp-banner/` 가 `.gitignore` 에 있는지 먼저 확인해라.** 이 플랜은 디렉터리를 만들지 않아 확인할 대상이 없었다. 실제 회차를 돌리면 회차당 약 271MB 가 생긴다.
- 실측 4분 12초는 **RESEARCH 의 수치**다. 이 플랜은 실제 회차를 안 돌렸다 — `caffeinate` 를 붙인 근거가 그 수치이므로, 실제 소요가 크게 다르면 `_수면방지_프리픽스` 주석의 근거를 갱신해라.

**막는 것 없음.** `.venv-web` 407 green · `.venv` cli 4 green.

---
*Phase: 04-banner-detection*
*Completed: 2026-09-22*

## Self-Check: PASSED

- 파일 7개 전부 존재: `webapp/jobs.py` · `webapp/argv.py` · `webapp/routes/jobs.py` · `webapp/tests/test_jobs.py` · `webapp/tests/test_argv.py` · `webapp/tests/test_routes_jobs.py` · `04-05-SUMMARY.md`
- 커밋 4개 전부 존재: `a313cc8` · `90d1f4d` · `98b787e` · `6c79031`
- **삭제된 파일 0건** (`git diff --diff-filter=D --name-only 2329d39..HEAD`)
- **공유 산출물 미수정:** base 이후 변경 파일 6개가 전부 플랜 `files_modified` 안이다. `STATE.md`·`ROADMAP.md`·`REQUIREMENTS.md` 변경 0건 (오케스트레이터 몫)
- 커밋되지 않아야 할 것이 안 들어갔다: `.venv`/`.venv-web` 심링크 디렉터리 · `workspace.toml` 사본 · scratchpad e2e 산출물 전부 staged 0건. `git status` 깨끗
- `.venv-web` **407 green** (exit 0) · `.venv` `webapp/tests/cli` **4 green** (exit 0)
- 집합 배치 실측: `banner_scan` ∈ `KINDS`·`SINGLETON_KINDS` · ∉ `WRITE_KINDS`·`BULSAJA_KINDS`
- 조립 argv 14플래그를 실제 자식에 태워 전부 파싱 확인 (빈 조인 → exit 2 · 네트워크 0 · 크레딧 0)
