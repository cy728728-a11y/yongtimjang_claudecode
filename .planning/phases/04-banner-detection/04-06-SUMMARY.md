---
phase: 04-banner-detection
plan: 06
subsystem: review-screen-server
tags: [banner, route, sqlite, csrf, path-traversal, whitelist-projection, d09, asvs]

# Dependency graph
requires:
  - phase: 04-banner-detection
    plan: 02
    provides: "`webapp/banner.py` 순수 관문 — `게이트집계` · `상품키` · `사람판정허용값`"
  - phase: 04-banner-detection
    plan: 04
    provides: "산출물 JSON 계약 — `집계`·`소요초`·`판정규칙`·`상품[].스킵사유`·`장[].썸네일`(파일명만)"
  - phase: 04-banner-detection
    plan: 05
    provides: "`jobs.latest_done('banner_scan')` · `banner_label`/`banner_confirm` DDL · `jobs.banner_dir()`"
  - phase: 01-webapp-shell
    provides: "`security.guard` 3층 · `page_cookie_ok` · `paths.run_dir_path` 화이트리스트 · `routes/board.py` 투영 관례"
provides:
  - "`webapp/banner_store.py` — 사람 라벨 read/write. 이 저장소에서 sqlite3 를 쓰는 세 번째(이자 마지막) 모듈"
  - "`GET /banner/review` — 산출물 + 라벨 + 확인을 화이트리스트로 투영한 검수 화면 헤더"
  - "`GET /banner/thumb/{회차}/{상품i}/{장i}` — 정수 인덱스만 받는 썸네일. 경로 탈출이 구조적으로 불가능"
  - "`POST /banner/label` · `POST /banner/confirm` — 사람 라벨 쓰기. guard 3층을 예외 없이 탄다"
  - "`webapp/templates/banner_review.html` — 헤더까지. 전장 스트립 자리는 04-07 이 채운다"
  - "🔴 **한글 경로 파라미터가 이 FastAPI/Starlette 조합에서 라우팅되지 않는다**는 실측 (아래 이탈 1)"
affects: [04-07, 04-08]

# Tech tracking
tech-stack:
  added: []          # 신규 패키지 0. FastAPI·Pydantic·stdlib sqlite3 만 쓴다
  patterns:
    - "경로 탈출은 **막는 게 아니라 불가능하게** 만든다 — 라우트가 파일명을 받는 인자 자체를 갖지 않는다"
    - "가드가 감시하는 낱말은 **감시 대상 파일이 주석에도 안 들고 있는다** (이번에 3곳: DDL 낱말 · 정적마운트 클래스명 · 표 라이브러리 이름)"
    - "'막혔다' 를 단언하는 테스트는 **'정상 경로는 열린다' 를 같이 단언**한다 — 전부 404 인 서버에서도 통과하는 검증을 만들지 않는다"
    - "거부 테스트는 상태코드만 보지 않고 **DB 행 수 0** 까지 본다 — '거부됐다' 와 '거부는 됐는데 그 전에 썼다' 는 다르다"
    - "읽기 실패를 삼키는 범위를 **사실별로 가른다**: 파일 없음/못 엶은 빈 값, 스키마 없음은 예외"

key-files:
  created:
    - webapp/banner_store.py
    - webapp/routes/banner.py
    - webapp/templates/banner_review.html
    - webapp/tests/test_routes_banner.py
  modified:
    - webapp/main.py

key-decisions:
  - "라벨 저장을 **A안(`banner_store.py` 신규)** 으로 확정했다(PATTERNS §7 미결 1). `banner.py` 는 순수한 채로 남고 D-19 트리 가드가 계속 성립한다"
  - "`banner_store` 가 **테이블 부재를 삼키지 않는다.** 파일 없음·못 엶은 빈 값이지만 스키마 없음은 `OperationalError` 로 올린다 — 사람이 할 일이 다르다(재시작). `{}` 로 접으면 클릭이 통째로 버려지는데 화면은 멀쩡하다"
  - "`_load_banner` 의 두 번째 원소를 **시각이 아니라 작업 id** 로 했다. `board._load_join` 은 거기서 `ended_at` 을 쓰는데, 이 플랜은 그 필드 사용을 금지한다(S-5) — 모양을 베끼려다 금지된 출처를 끌고 오지 않는다"
  - "썸네일 라우트의 **경로 파라미터 이름만 영문**이다. 한글 이름은 이 조합에서 조용히 404 다(실측). 예외가 아니라 404 라서 '아직 안 만들었나' 로 읽힌다 — 사유를 핸들러 docstring 에 박았다"
  - "`사람판정` 화이트리스트를 **Literal 과 저장소 두 곳**에 뒀다. 값의 정본은 `banner.사람판정허용값` 하나이고 양쪽이 그것을 참조한다 — 문자열을 다시 적지 않았다"
  - "투영에 **CDN URL 을 싣지 않는다.** 서버 썸네일을 쓰므로 실을 이유가 없고, 실으면 브라우저가 외부 CDN 에 직접 붙어 Referer 가 샌다(T-4-22)"
  - "`_화면투영` 이 상품키를 못 만드는 상품도 **사유를 들고 남긴다.** 빼면 '전장을 깐다'(D-03a)가 조용히 깨진다"

patterns-established:
  - "라우트 테스트는 `create_job` 을 가로채지 않는다 — **가장 바깥의 부작용 하나**(잡 행 + 산출물 파일)만 가짜로 만들고 나머지는 진짜를 태운다"
  - "경로 탈출 회귀는 **변형 목록 + 정상 1건**을 한 테스트 안에 둔다. 정상이 없으면 라우트가 통째로 죽어도 초록이다"

requirements-completed: [BANNER-04, BANNER-05]
requirements-partial: []

# Metrics
duration: 약 55min
completed: 2026-09-22
---

# Phase 4 Plan 06: 검수 화면의 서버 절반 Summary

**이 페이즈가 새로 여는 보안 표면 3개(디스크 썸네일 서빙 · 사람 라벨 쓰기 · 산출물 투영)를 전부 세우고, 그 셋을 각각 자동 회귀로 물렸다 — 경로 탈출은 막는 게 아니라 라우트가 파일명을 받는 인자를 아예 갖지 않아 불가능하다.**

## Performance

- **Duration:** 약 55분
- **Tasks:** 3/3
- **Files:** 5 (생성 4 · 수정 1)
- **Tests:** `.venv-web` 407 → **429 green** (신규 22) · `.venv` cli **4 green** (변화 없음)
- **신규 패키지 0 · MCP 호출 0회 · 크레딧 0 · 네트워크 0**

## Task Commits

| # | 작업 | 커밋 | 종류 |
|---|---|---|---|
| 1 | `banner_store.py` 4함수 + 저장소 회귀 8 | `dc2585c` | feat |
| 2 | `routes/banner.py` 4라우트 + `main.py` 등록 + 최소 템플릿 | `6d0c6bb` | feat |
| 3 | 보안 회귀 3건 + 사람큐 가드 + 템플릿 가드 (신규 14) | `2353c1c` | test |

## 🔴 새 보안 표면 3개 — 무엇을 어떻게 닫았나

플랜이 *"이 페이즈에서 새로 생기는 보안 표면이 전부 여기 있다"* 고 지목한 자리다.

| 표면 | 위협 | 닫은 방식 | 지키는 테스트 |
|---|---|---|---|
| `GET /banner/review` | T-4-03 Tampering | 핸들러가 디스크·DB·레지스트리에 아무것도 안 쓴다. `latest_done` 은 WAL 의 no-op 트랜잭션이라 **주 DB 파일 mtime 이 안 바뀐다**(실측 확인 후 테스트로 고정) | `test_GET_무부작용` (행 수 2종 + DB mtime + 산출물 mtime) |
| `GET /banner/thumb/...` | T-4-04 Info Disclosure | ① 라우트가 **파일명 인자를 안 갖는다** — 정수 둘 + 화이트리스트 회차뿐 ② 파일명은 서버가 산출물 `장[].썸네일` 에서 꺼낸다 ③ 만든 경로의 **부모 디렉터리 경로 비교**(접두 비교 아님) ④ 쿠키 게이트 ⑤ 정적 마운트 금지 | `test_경로탈출`(7변형 + 정상 1) · `test_썸네일이_회차_밖을_가리키면_거부한다` · `test_쿠키_없으면_403` |
| `POST /banner/label` · `/banner/confirm` | T-4-05 Tampering | `security.guard` 3층을 **예외 코드 0줄**로 탄다. `사람판정` 은 Pydantic `Literal`, 정본은 `banner.사람판정허용값` | `test_라벨_POST_토큰`(4케이스 + DB 행 0) · `test_라벨과_확인이_실제로_저장된다` |

**음수 인덱스를 따로 막은 이유:** 파이썬 리스트는 `[-1]` 을 조용히 받아 **마지막 장**을 내준다. `if 상품순번 >= len(...)` 만 있으면 범위 검사가 있는 척만 하는 가드가 된다. 회귀가 `-1/-1` 을 실제로 쏜다.

**`test_경로탈출` 이 정상 200 을 같이 단언하는 이유:** 라우터 등록이 빠지거나 경로가 안 맞으면 모든 변형이 404 라서 **테스트가 통과한다.** 실제로 이 플랜에서 그 일이 났다(아래 이탈 1) — 정상 단언이 없었다면 한글 파라미터 버그가 초록 뒤에 숨은 채 04-07 로 넘어갔다.

## 라벨 저장소 — 읽기/쓰기를 커넥션으로 가른다

| 상황 | 동작 | 왜 |
|---|---|---|
| DB 파일 없음 | `{}` / `set()`, **파일을 만들지 않는다** | 읽기 경로가 파일을 만들면 스키마 없는 빈 파일이 생겨 이후 모든 쓰기가 터진다 |
| 파일 있는데 못 엶 (권한·손상) | `{}` / `set()` | 화면이 500 이 되는 것보다 "아직 라벨이 없다" 가 낫다. 게이트는 어차피 닫혀 있다(미검수 > 0) |
| **테이블 없음** | **`sqlite3.OperationalError` 를 올린다** | `{}` 로 접으면 사람이 아무리 클릭해도 저장이 안 되는데 화면은 멀쩡하다. 라우트가 500 + `"라벨 테이블이 없다 — 서버를 한 번 재시작해라"` 로 번역한다 |
| 같은 장에 재클릭 | `INSERT OR REPLACE`, 최신 1건 | 누적하면 같은 장이 분모에 두 번 들어가고, 뒤집었다 되돌린 클릭이 영원히 미탐으로 남는다 |

스키마를 만드는 문장은 **0건**이다(grep 가드가 집행). 정본은 `jobs.DDL` 하나다.

## Files

- **`webapp/banner_store.py`** (신규 207행) — `라벨기록`·`라벨읽기`·`확인기록`·`확인읽기` + `_ro_conn`/`_conn` + `db_path` 3줄 복제(순환 회피)
- **`webapp/routes/banner.py`** (신규 443행) — POST 2 · GET 2 · `_load_banner` · `_썸네일이름` · `_화면투영` · `_쓰기예외`
- **`webapp/templates/banner_review.html`** (신규 130행) — 헤더까지. 집계 7칸 · 게이트 분모 둘 · 소요초 분초 · 라벨 진행 · 미검수 · 판정규칙 2종 · "토큰 0 · 크레딧 0 · 외부 API 0" 고정 문구 · 산출물 없으면 접수 버튼
- **`webapp/tests/test_routes_banner.py`** (신규 498행) — 저장소 8 + 라우트·보안 14
- **`webapp/main.py`** (+1행) — `include_router(banner.router)`

## Deviations from Plan

### Auto-fixed Issues

**1. 🔴 [Rule 1 - Bug] 한글 경로 파라미터가 라우팅되지 않는다 — 조용한 404**

- **Found during:** Task 3 (회귀를 처음 돌린 순간)
- **Issue:** 플랜이 지정한 `GET /banner/thumb/{run_dir}/{상품순번}/{장순번}` 이 `/banner/thumb/2026-08-30/0/0` 에 **매치되지 않는다.** 라우터에는 등록돼 있는데(`router.routes` 에 보인다) 요청은 404 다. 최소 재현으로 확인했다 — 같은 모양의 `/{pi}/{ci}` 는 200, `/{상품순번}/{장순번}` 은 404. 이 FastAPI/Starlette 조합의 경로 매칭이 비ASCII 파라미터 이름을 흘린다.
- **왜 위험한가:** **예외가 아니라 404 다.** 기동해도 아무 소리가 안 나고, 화면에서는 썸네일이 깨진 그림으로만 보인다 — 04-07 이 "썸네일이 왜 안 뜨지" 를 스트립 코드에서 찾게 된다. 그리고 경로 탈출 회귀가 **전부 404 를 기대하므로 이 상태에서도 초록이다.**
- **Fix:** 경로 파라미터 이름만 `product_i`/`chap_i` 로 바꿨다. 내부 변수·헬퍼는 한글 그대로다. 핸들러 docstring 에 실측과 사유를 적어 다음 사람이 "관례에 맞게" 한글로 되돌리지 못하게 했다.
- **Verification:** `test_경로탈출` 의 **정상 200 단언**이 이것을 잡았다. 그 한 줄이 없었으면 이 버그는 초록 뒤에 숨는다.
- **Committed in:** `6d0c6bb`

**2. [Rule 3 - Blocking] 플랜대로 커밋하면 Task 2 의 트리가 깨진다**

- **Found during:** Task 2
- **Issue:** 플랜은 템플릿을 Task 3 에 뒀다. 그런데 Task 2 가 만드는 `get_review` 가 `banner_review.html` 을 렌더하므로, 그 순서로 커밋하면 **두 번째 커밋의 트리에서 `/banner/review` 가 `TemplateNotFound` 로 500** 이다(`git bisect` 나 부분 체크아웃이 그 커밋을 짚으면 원인 불명의 500).
- **Fix:** 템플릿을 Task 2 커밋에 포함했다. Task 3 은 테스트만 담는다. 플랜의 **내용**은 하나도 안 바꿨다 — 템플릿 요구사항(표 라이브러리 금지 · `| safe` 금지 · 고정 문구 · 헤더 항목)을 그대로 구현했다.
- **Verification:** 세 커밋 각각이 단독으로 일관된 트리다
- **Committed in:** 순서 자체가 조치

**3. [Rule 2 - Missing critical] `board._load_join` 모양을 그대로 베끼면 금지된 필드를 끌고 온다**

- **Found during:** Task 2
- **Issue:** 플랜은 `_load_banner` 를 *"`_load_join` 모양 그대로"* 만들라고 하면서, 동시에 `ended_at` 사용을 금지하고 acceptance 에 `grep -F 'ended_at'` 0줄을 걸었다. 그런데 `_load_join` 의 두 번째 반환값이 정확히 `잡.get("ended_at") or 잡.get("started_at")` 이다. 모양을 베끼면 acceptance 가 깨지고, acceptance 를 지키면 모양이 달라진다.
- **Fix:** 두 번째 원소를 **작업 id** 로 했다. 화면이 "어느 스캔 결과인가" 를 말할 수 있고(투영 화이트리스트 안의 uuid 하나), 소요시간은 산출물의 `소요초` 에서 온다(S-5 가 요구한 그대로). `(None, None, None)` 3튜플 계약은 유지했다.
- **Verification:** `grep -F 'ended_at' webapp/routes/banner.py` 0줄 · `test_라우트가_정적마운트도_ended_at_도_안_쓴다` green
- **Committed in:** `6d0c6bb`

**4. [Rule 2 - Missing critical] 저장소 층에 사람판정 2차선이 없었다**

- **Found during:** Task 1
- **Issue:** 플랜은 값 검증을 라우트의 `Literal` 한 곳에 뒀다. 그런데 `banner_store` 는 공개 함수이고 04-07·04-08 이 직접 부를 수 있다(그리고 v2 스케줄러도). 라벨 값이 허용값 밖으로 한 행이라도 들어가면 `게이트집계` 가 **예외로 터지는데, 그때는 이미 사람의 클릭이 버려진 뒤다** — 되돌릴 방법이 없다(재생성 불가한 기록이다).
- **Fix:** `라벨기록` 이 `banner.사람판정허용값` 으로 한 번 더 본다. **문자열을 다시 적지 않았다** — 정본 튜플을 참조한다. 1차선(라우트 Literal)과 2차선(저장소)이 같은 출처를 보므로 어긋날 길이 없다.
- **Verification:** `test_사람판정_허용값_밖은_저장소에서도_막힌다` green
- **Committed in:** `dc2585c`

**5. [Rule 2 - Missing critical] 플랜의 "못 열면 빈 값" 이 테이블 부재까지 삼킨다**

- **Found during:** Task 1
- **Issue:** 플랜은 *"파일이 있어도 못 열면(권한·손상) 화면이 500 이 되는 것보다 '아직 라벨이 없다'로 보이는 쪽이 낫다"* 고 적었다. 그대로 넓게 잡아 `sqlite3.Error` 를 통째로 삼키면 **테이블 부재도 `{}`** 가 된다. 그러면 사람이 아무리 클릭해도 저장이 안 되는데 화면은 "라벨 0건" 으로 멀쩡하다 — 플랜이 바로 다음 문단에서 요구한 *"`OperationalError` 를 라우트가 '서버를 재시작해라'로 번역한다"* 가 **영원히 발동하지 않는다.**
- **Fix:** 삼키는 범위를 `_ro_conn()` **열기 실패까지**로 좁혔다. 쿼리 단계의 `OperationalError` 는 그대로 올라간다. 둘이 다른 사실이라는 것을 docstring 에 적었다.
- **Verification:** `test_테이블이_없으면_조용히_비지_않는다` · `test_라벨_테이블이_없으면_고칠_자리를_말한다`(HTTP 층 500 + "재시작") green
- **Committed in:** `dc2585c`

**6. [Rule 1 - Bug] `app.routes` 가 FastAPI 0.137+ 에서 라우트 리스트가 아니다**

- **Found during:** Task 3
- **Issue:** 붙은 경로를 확인하려고 `app.routes` 를 훑었더니 `_IncludedRouter` 객체가 나온다 — STACK.md 가 적어 둔 0.137.0 브레이킹 체인지(`router.routes` 가 리스트→트리)가 실제로 이 모양이다. `getattr(r, "path", "")` 가 전부 빈 문자열이라 **가드가 0개를 훑고 통과**한다(있는 척만 하는 가드).
- **Fix:** `banner.router.routes` 를 직접 본다. 그 라우터는 여전히 평평한 리스트다. 사유를 테스트 주석에 적었다.
- **Verification:** `test_사람큐_엔드포인트_없음` 이 경로 4개를 정확히 고정한다(개수가 아니라 목록 전체를 단언한다)
- **Committed in:** `2353c1c`

**7. [Rule 2 - Missing critical] 가드가 감시하는 낱말을 감시 대상이 주석에 들고 있었다**

- **Found during:** Task 1·2·3 (세 번)
- **Issue:** ① `banner_store.py` 의 "이 모듈이 하지 않는 것" 목록이 DDL 낱말 셋을 글자로 들고 있었다 ② `routes/banner.py` 가 정적 마운트 클래스명을 "쓰지 마라" 문맥으로 들고 있었다 ③ 템플릿 머리 주석이 표 라이브러리 이름을 들고 있었다. 셋 다 acceptance 의 `grep` 을 그대로 빨갛게 만든다.
- **Fix:** 세 곳 모두 낱말을 빼고 **뜻으로 적었다**(`test_argv.py:9-14` 의 규율 — 가드가 감시하는 문자열을 감시 대상이 들고 있으면 "여기는 있어도 된다" 는 예외가 생기고 그 예외가 언젠가 진짜 코드로 자란다). 테스트 쪽도 같은 규율로 런타임 조립(`"CRE" + "ATE"`)을 쓴다.
- **Verification:** acceptance grep 7종 전부 기대값
- **Committed in:** 각 태스크 커밋

**8. [Rule 3 - Blocking] 워크트리 base 가 지정 커밋보다 뒤에 있었다**

- **Found during:** 시작 전 (worktree_branch_check)
- **Issue:** HEAD 가 `3118192`(phase 4 컨텍스트 기록 시점)였다. 지정 base 는 `0abafad`(wave 5 반영 후)라 **Wave 1~5 산출물이 통째로 없는 상태**였다. 04-04·04-05 가 겪은 것과 같다.
- **Fix:** 브랜치 검사(`worktree-agent-*` 네임스페이스 · 보호 ref 아님)를 **먼저** 통과시킨 뒤 `git reset --hard 0abafad`.
- **Committed in:** 해당 없음

**9. [Rule 3 - Blocking] 워크트리에 `.venv`·`.venv-web`·`workspace.toml` 이 없다**

- **Found during:** 시작 전
- **Issue:** 04-01~04-05 와 같다. 셋 다 gitignore 대상이라 병렬 워크트리에 존재하지 않는다. `.venv` 가 없으면 `test_cli_shim.py`·`test_cli_patch.py`·`test_revert.py` 12개가 빨갛다(실측).
- **Fix:** 앞선 웨이브의 해법 그대로 — `.venv`/`.venv-web` 을 실제 디렉터리로 만들고 `bin`·`lib`·`pyvenv.cfg` 만 본 저장소로 심링크, `workspace.toml` 은 사본. **커밋 0건.**
- **Verification:** base 이후 변경 파일 5개가 플랜 `files_modified` 와 정확히 일치. `git status` 깨끗
- **Committed in:** 해당 없음

---

**Total deviations:** 9 (Rule 1 ×2 · Rule 2 ×4 · Rule 3 ×3 — 그중 8·9 는 환경 정정)
**Impact on plan:** 범위 확장 없음. 1·6 은 조용히 통과했을 버그 둘이고, 3·4·5 는 플랜의 지시 둘이 서로 어긋나거나 규율이 목적을 절반만 지키던 자리를 메운 것이다. 테스트가 7개(플랜) → 22개로 늘었다.

## Issues Encountered

- **`pytest -q` 가 요약 줄을 안 찍는 현상**(04-02~04-05 와 동일). `-q` 없이 돌려 숫자를 확인했다.
- **`.venv` 심링크를 깔기 전 전 스위트가 12 failed** 였다. 전부 CLI venv 부재가 원인이고 이 플랜의 변경과 무관하다 — 심링크 후 407 green 을 base 로 확인한 뒤 작업을 시작했다.
- **`security_curl.sh` 전체는 못 돌렸다**(서버 기동이 필요하다). 다만 그 안의 **V-SAFE-01d ast 스캐너만 떼어 실행**해 exit 0 을 확인했다 — GET 핸들러 10개를 호출관계로 훑어 상태 변경 호출 0건이다. 서버가 필요한 나머지 curl 케이스는 04-08 몫이다.

## Known Stubs

**하나 있고, 플랜이 명시적으로 그렇게 지시한 것이다.**

| 것 | 지금 | 누가 채우나 | 사유 |
|---|---|---|---|
| `_장조각()` 이 돌려주는 조각 HTML | `<figure>` 한 줄(순번 + 판정) | **04-07** | 플랜 Task 2: *"04-07 이 템플릿 매크로로 채운다 — 이 플랜에서는 최소 `<figure>` 문자열"*. 저장은 **실제로 일어난다**(회귀가 DB 행을 확인한다) |
| `banner_review.html` 의 전장 스트립 | `"상품 N줄이 준비됐다"` 한 줄 | **04-07** | 플랜 objective: *"화면 본체(전장 스트립)는 04-07 이 얹는다"* |

**stub 이 아닌 것:** 라우트 4개·저장소 4함수는 전부 실제로 동작한다. 라벨이 DB 에 들어가고, 썸네일 바이트가 나가고(회귀가 내용까지 비교한다), 게이트 숫자가 `banner.게이트집계` 에서 온다.

## Threat Flags

**등록부 밖의 새 surface 는 없다.** GET 엔드포인트 2개가 새로 생겼지만 둘 다 `<threat_model>` 이 이미 등록한 경계(T-4-03 · T-4-04)이고, POST 2개는 T-4-05 다.

| Threat ID | Disposition | 처리 |
|---|---|---|
| T-4-03 (GET 부작용) | **mitigate 완료** | 핸들러가 아무것도 안 쓴다. 행 수 2종 + DB mtime + 산출물 mtime 불변을 회귀가 확인. V-SAFE-01d ast 스캐너 exit 0 |
| T-4-04 (썸네일 정보 노출) | **mitigate 완료** | 파일명 인자 없음 · `run_dir_path` 화이트리스트 · 부모 경로 비교 2층 · 쿠키 게이트 · 정적 마운트 0건. 7변형 회귀 + 회차 밖 포인터 회귀 |
| T-4-05 (라벨 CSRF) | **mitigate 완료** | `guard` 3층을 예외 코드 0줄로 탄다. GET 405 · 타 Origin 403 · 토큰 없음 403 · `Literal` 밖 422, **넷 다 DB 행 0** |
| T-4-21 (트레이스백 노출) | **mitigate 완료** | 전부 `f"{type(e).__name__}: {e}"` 축약. `test_트레이스백이_화면에_안_실린다` 가 `Traceback` 부재 + tmp 경로 부재를 같이 본다 |
| T-4-22 (CDN Referer 유출) | **mitigate 완료** | 투영에 `url` 을 안 싣는다(`썸네일있음` bool 만) · `<meta name="referrer" content="no-referrer">` |
| T-4-23 (라벨 테이블 자동 생성) | **mitigate 완료** | `banner_store.py` 에 스키마 문장 0건 — grep 가드 집행. DDL 정본은 `jobs.py` 하나 |
| D-09 (사람 판단 큐) | **지켜짐** | 소스 금지낱말 0 + 큐 경로 0 + **붙은 경로 4개를 목록 전체로 고정** |

## Next Phase Readiness

**04-07(전장 스트립)이 바로 쓸 수 있는 것:**

- `GET /banner/review?run_dir=<회차>` 의 ctx. 상품 투영은 `{순번, 상품키, 키사유, 판매자상품코드, 상세상태, 장수, 제거율, 스킵사유, 사유, 확인됨, 라벨수, 장:[{순번, 판정, 사유, 사람판정, 썸네일있음}]}` 이다.
- **썸네일 URL 은 `/banner/thumb/{{ run_dir }}/{{ 상품.순번 }}/{{ 장.순번 }}` 로 조립해라.** `상품.순번` 은 산출물 배열 인덱스이고, 그게 썸네일 라우트가 받는 그 정수다. 파일명은 ctx 에 **없다**(일부러 뺐다).
- `장.썸네일있음` 이 `false` 면 그 장은 404 다 — `<img>` 를 걸지 말고 자리표시를 그려라(미판정·다운로드 실패 장이다).
- 라벨 버튼은 `hx-post="/banner/label"`, 확인은 `hx-post="/banner/confirm"`. **`hx-get` 으로 바꾸지 마라** — 교차 사이트 단순 GET 에는 Origin 헤더가 없어 guard 의 Origin 층이 통째로 무력화된다.
- `hx-vals` 에 실을 것: `run_dir` · `타오바오상품번호`(= `상품.상품키`) · `판매자상품코드` · `이미지순번` · `사람판정`. 응답은 **그 장 하나의 조각**이므로 `hx-swap="outerHTML"` 로 `<figure>` 만 갈아라 — 줄 전체를 갈면 가로 스크롤 위치가 매 클릭마다 처음으로 돌아간다.
- `_장조각()` 을 04-07 이 템플릿 매크로로 바꿀 때, **`<figure>` 루트와 `data-p`/`data-i` 속성은 유지해라** — 회귀가 `figure` 문자열을 본다.

**04-07 이 조심할 것:**

- 🔴 **경로 파라미터에 한글을 쓰지 마라.** 이 조합에서 조용히 404 다(위 이탈 1). 새 라우트를 만들면 **정상 200 을 단언하는 테스트를 먼저** 써라.
- `상품키` 가 `None` 인 상품이 ctx 에 남아 있다(`키사유` 를 들고). 라벨 버튼을 걸 수 없는 줄이므로 화면이 그 사유를 말해야 한다 — 빼지 마라(D-03a).
- 경계 4장(`settings.DEFAULTS["banner_boundary_samples"]`)을 첫 화면에 배치하는 것은 04-07 몫이다. 이 플랜은 그 값을 안 읽는다.

**04-08(게이트)이 확인할 것:**

- `게이트집계` 가 화면에서 실제로 돈다. `미검수상품 > 0` 이면 `게이트통과: false` 이고 템플릿이 "닫혀 있다" 를 띄운다 — 전수가 전제라는 D-12 가 화면에서 성립한다.
- **`security_curl.sh` 전체를 서버 띄우고 한 번 돌려라.** 이 플랜은 V-SAFE-01d 만 떼어 돌렸다.
- `webapp-banner/` 가 `.gitignore` 에 있다는 것은 오케스트레이터가 확인했다(52행). 이 플랜은 실제 디렉터리를 안 만들었다.

**막는 것 없음.** `.venv-web` 429 green · `.venv` cli 4 green.

---
*Phase: 04-banner-detection*
*Completed: 2026-09-22*

## Self-Check: PASSED

- 파일 6개 전부 존재: `webapp/banner_store.py` · `webapp/routes/banner.py` · `webapp/templates/banner_review.html` · `webapp/tests/test_routes_banner.py` · `webapp/main.py` · `04-06-SUMMARY.md`
- 커밋 4개 전부 존재: `dc2585c` · `6d0c6bb` · `2353c1c` · `0a30176`
- **삭제된 파일 0건** (`git diff --diff-filter=D --name-only 0abafad..HEAD`)
- **공유 산출물 미수정:** base 이후 변경 파일 5개가 전부 플랜 `files_modified` 안이다. `STATE.md`·`ROADMAP.md`·`REQUIREMENTS.md` 변경 0건 (오케스트레이터 몫)
- 커밋되지 않아야 할 것이 안 들어갔다: `.venv`/`.venv-web` 심링크 디렉터리 · `workspace.toml` 사본 · scratchpad 산출물 전부 staged 0건. `git status` 깨끗
- `.venv-web` **429 green** (exit 0) · `.venv` `webapp/tests/cli` **4 green** (exit 0)
- acceptance grep 7종 실측: `page_cookie_ok` 2 · 사람큐 낱말 0 · 정적마운트 0 · `include_router(banner.router)` 1 · `ended_at` 0 · 템플릿 표라이브러리 0 · 템플릿 `| safe` 0 · 고정 문구 1
- `security_curl.sh` V-SAFE-01d ast 스캐너 단독 실행 **exit 0** (GET 핸들러 10개를 호출관계로 훑어 상태 변경 0건)
