---
phase: 01-board-bid-raise
verified: 2026-09-20T13:48:58Z
status: human_needed
score: 5/5 (성공기준) · 19/19 (요구사항) · 2건 human 확인 대기
overrides_applied: 0
human_verification:
  - test: "회차 신선도 배너(D-16)가 경과일 임계값을 넘으면 실제로 경고색(class=stale)으로 화면에 보이는지 눈으로 확인"
    expected: "보드 상단에 `YYYY-MM-DD 회차 · N일 전 · 통계 기간 …` 이 뜨고, 임계값(기본 8일) 초과 시 빨간/주황 계열로 바뀐다"
    why_human: "서버는 freshness.stale 불리언과 CSS class=stale 을 정확히 내려주는 것까지만 기계로 확인 가능하다(코드 읽음: board.html:74, board.py). '그 색이 사람 눈에 경고로 읽히는가'는 렌더된 픽셀을 봐야 하는 시각 판단이라 grep·CDP 텍스트 추출로 못 잰다. board_cdp.sh 도 이 항목은 잡지 않는다(배지 숫자만 본다)."
  - test: "되돌리기 버튼을 실제로 눌러 네이버 광고 API 에 PUT 을 태우고, 광고 관리 화면에서 입찰가가 인상 전 값으로 복원됐는지 확인"
    expected: "성공기준 4 후반 — '화면의 되돌리기 버튼 한 번으로 인상 전 상태로 복원된다' 가 실탄으로 증명된다"
    why_human: "용팀장이 2026-09-20 '되돌릴 필요 없다'고 명시적으로 지시해 이 페이즈에서 실행하지 않았다(01-VALIDATION.md Manual-Only 표 마지막 행, deferred-items.md). 실제 광고비·입찰가를 건드리는 외부 시스템 쓰기라 코드 검증만으로는 '네이버 API 가 이 PUT 을 실제로 받아들이는지'를 증명 못 한다 — 이건 귀찮음이 아니라 되돌릴 수 없는 실제 자산(광고 입찰가)에 대한 결정 권한 문제다. 구조·dry-run·CDP 로 검증된 것: 요청 본문이 정확히 commit_job_id 하나뿐이다(V-RVT-21/22 그린) · 범위 가드가 서버 dry-run 으로 막는다(test_revert.py 41/41 그린) · 되돌리기 PUT 도 인상과 같은 `_put_ad` 공용 함수를 탄다(WR-09 fixed, 인상 쪽은 472/472 실탄 검증됨). 남은 것은 '실제 네이버 서버가 이 PUT 을 수락하는가' 하나뿐이고, 이건 용팀장이 원할 때 눌러서 직접 확인해야 한다."
---

# Phase 01: 보드 + 입찰가 인상 버튼 Verification Report

**Phase Goal:** 터미널을 열지 않고 브라우저에서 광고 판정 결과를 상품 단위로 보고, 규칙①(노출 0) 대상의 입찰가를 미리보기 후 올리고 되돌린다
**Verified:** 2026-09-20T13:48:58Z
**Status:** human_needed
**Re-verification:** No — initial verification

## 판정 방법 요약

SUMMARY 는 근거로 안 썼다. 아래는 전부 **이 세션에서 직접 돌린 실행 결과**다:
서버(`127.0.0.1:8765`, `/healthz` 200 확인)에 대고 6개 CDP/curl 하네스와 pytest·CLI unittest 를 전부 재실행했고,
`webapp/*.py` 핵심 파일을 직접 열어 코드를 읽었고, `revert_cdp.sh` 는 첫 실행에서 FAIL 이 나서 원인을 끝까지 추적했다(아래 §특이사항).

## 성공기준 5개 판정

| # | 성공기준 | 상태 | 증거 |
|---|---|---|---|
| 1 | 브라우저에서 판정 결과를 한 줄=상품 1개로 보고, 계정·규칙·상태로 걸러 정렬·검색한다. 계정 4→6개든 설정만 고치면 화면이 따라온다 | ✓ VERIFIED | `board_cdp.sh` 재실행 22/22 PASS(직접 확인) — 계정별 배지·규칙별 배지·검색 3건·초기화·렌더 undefined 0건·가로스크롤 없음 전부 정답과 일치. `grep -n "cy728\|ownway1\|…" webapp/*.py webapp/routes/*.py webapp/static/*.js webapp/templates/*.html` → 계정명 하드코딩 0건(주석만). 실제로 `~/.eroom/naver-ads.json` 이 4→**7개**로 늘었는데(`cy728·cy7728·ownway1·pogeunae·dldmswl1986·milky-way1992·level_up_ad`) 코드 변경 없이 화면이 따라왔다는 REVIEW·01-07 이후 커밋 로그와 일치 — 이 세션에서 실제 파일을 열어 7개 확인 |
| 2 | 행을 골라 "입찰가 인상 미리보기" → 상품별 현재가→인상 후. 그룹입찰 상품은 그룹 기본입찰가에서 출발 | ✓ VERIFIED | `preview_cdp.sh` 재실행 32/32 PASS(직접 확인) — V-PRE-12a/b: 실데이터 소재 `nad-a001-02-000000495390006` 표 70→80 / 보드 70 일치, `그룹입찰따름=예`. `webapp/flow.py` 를 직접 읽어 `from`/`to` 가 CLI `--preview-out` 산출물 값을 그대로 옮길 뿐 재계산 없음을 코드로 확인(`p.get("from")`/`p.get("to")`, `flow.py:186-275`) |
| 3 | 실행 후 브라우저 탭을 닫았다 다시 열어도 그 작업 진행 로그를 처음부터 이어서 본다 | ✓ VERIFIED | `sse_cdp.sh` 재실행 12/12 PASS(직접 확인) — 헤드리스 크롬으로 CDP `/json/close` 로 탭을 진짜 닫고 새 탭을 연 뒤: 닫기 전 25줄→다시 연 뒤 41줄, 누락 0·중복 0, EventSource 정확히 1개, done 시 닫힘(readyState 2). `webapp/jobs.py:290` `start_new_session=True` 로 서버 재시작에도 자식 생존 코드 확인 |
| 4 | 실행 결과가 항목 단위(성공/실패/스킵+사유)로 남고, 되돌리기 버튼 한 번으로 인상 전 상태로 복원 | ⚠ 절반 VERIFIED / 절반 human_needed | **앞 절반(항목단위 결과):** `test_flow.py`·`_result_table.html` 코드 확인 — 실패·스킵이 표 맨 위, `실행 안 됨` 을 성공으로 안 셈, 종료코드로 판단 안 함. **실전 검증:** 2026-09-20 실제 472건 인상 후 광고 API 재수집 전수 대조 472/472 일치(사용자 제공 운영 사실, `GET /jobs/revert/round/count?run_dir=2026-09-20` 로 이 세션에서 재확인 → `{"cy728":472,"total":472}` 그대로 살아있음 확인). **뒤 절반(되돌리기 실행):** `revert_cdp.sh` 로 버튼 배선·요청 본문·범위 가드·409 를 전부 확인했지만(아래 §특이사항 참고 — 재실행 26/26 PASS) **실제 광고 API 에 되돌리기 PUT 을 태운 적은 한 번도 없다** — 용팀장이 명시적으로 보류 지시. human_verification 에 등재 |
| 5 | 다른 탭이 쓰기를 트리거 못함(127.0.0.1+Host/Origin+부팅토큰). 화면·로그에 시크릿 안 나옴 | ✓ VERIFIED | `security_curl.sh` 재실행 9/9 PASS(직접 확인) — 127.0.0.1 전용 바인드·Host 화이트리스트 400·타 Origin 403·토큰없음/틀림 403·정상쓰기 통과·시크릿 미노출(보드 본문 id="board-rows" 확인 후 grep). `webapp/security.py` 코드 직접 읽음 — 이 파일 어떤 함수도 `~/.eroom/naver-ads.json` 을 안 열고, 자격증명은 CLI 서브프로세스 안에만 산다(구조적 보장, "조심"이 아니라 "구조상 불가능") |

**성공기준 점수:** 4.5/5 상시 자동검증 그린, 성공기준 4 후반 1건만 human_needed.

## 요구사항 19개 계상

| 요구사항 | 근거 Plan | 상태 | 증거 |
|---|---|---|---|
| ENG-01 | 01-05 | ✓ VERIFIED | `webapp/argv.py` 직접 읽음 — `PY_CLI = .venv/bin/python3`(웹앱 `.venv-web` 아님), argv 는 리스트라 shell 미경유. `test_argv.py`(pytest 199개 안에 포함, 재실행 그린) |
| ENG-02 | 01-06 | ✓ VERIFIED | `webapp/jobs.py:290` `start_new_session=True` 코드 확인 + `sse_cdp.sh` 재실행으로 서버 재시작 없이도 재접속 로그 이어짐 실측 |
| ENG-03 | 01-06 | ✓ VERIFIED | `webapp/logtail.py` `read_from(path, offset)` 오프셋 재생 구조 확인, `sse_cdp.sh` 실측(로그 파일 tail, 파이프 아님) |
| ENG-07 | 01-05 | ✓ VERIFIED | `webapp/jobs.py` `create_job()` 이 HTTP 객체를 안 받는 순수 함수임을 코드로 확인(`test_jobs.py::test_create_job_은_http_없이_돈다`, pytest 재실행 그린) |
| SAFE-01 | 01-03 | ✓ VERIFIED | `security_curl.sh` V-SAFE-01a/b/c/d 재실행 PASS |
| SAFE-02 | 01-03 | ✓ VERIFIED | `security_curl.sh` V-SAFE-02a/b/c1/c2 재실행 PASS |
| SAFE-03 | 01-01, 01-03 | ✓ VERIFIED | `webapp/security.py` 구조 확인(자격증명 파일 미오픈) + `security_curl.sh` V-SAFE-03 재실행 PASS(보드 본문 확인 후 grep) |
| FLOW-01 | 01-08 | ✓ VERIFIED | `commit_cdp.sh` 재실행 15/15 PASS — 미리보기 전 실행 버튼 잠김, 미리보기 후 열림, 새로고침 시 재잠김(V-CMT-01/02/07/08/15) |
| FLOW-02 | 01-02, 01-07 | ✓ VERIFIED | `test_flow.py::test_targets_파일이_하나다` 등 pytest 재실행 그린 + `webapp/jobs.py` `targets_path_override` 코드 확인 |
| FLOW-04 | 01-07 | ✓ VERIFIED | `preview_cdp.sh` V-PRE-02(타이핑칸 0개)·V-PRE-06a/b/c(배너·취소·확인) 재실행 PASS |
| FLOW-05 | 01-02, 01-08 | ✓ VERIFIED | CLI 쪽(`test_cli_patch.py`) + 화면 쪽(`_result_table.html` 실패·스킵 위 배치, `test_flow.py`) 둘 다 pytest 재실행 그린 |
| BOARD-01 | 01-04 | ✓ VERIFIED | `board_cdp.sh` 재실행 — 6규칙 배지 전부 정답과 일치, ①행 imp 없어도 렌더 안 깨짐(`test_board.py`) |
| BOARD-02 | 01-01, 01-04 | ✓ VERIFIED | 계정명 하드코딩 grep 0건 + 실제 계정 7개로 화면 확인(위 성공기준 1 증거) |
| BOARD-03 | 01-07 | ✓ VERIFIED | `preview_cdp.sh` V-PRE-03b/c/d 재실행 — 헤더선택 15줄 < 필터전체 89건, 다른 수 확인 |
| BOARD-04 | 01-07 | ✓ VERIFIED | `preview_cdp.sh` V-PRE-13(대상건수+인상액 합계 동시표시), `commit_cdp.sh` V-CMT-11/12/13(화면=산출물) 재실행 PASS |
| BID-01 | 01-07 | ✓ VERIFIED | `preview_cdp.sh` V-PRE-17a/b/c(규칙①아닌 대상 400 거부, 사유 명시) 재실행 PASS |
| BID-02 | 01-07 | ✓ VERIFIED | `webapp/flow.py` 코드 확인 — 웹앱이 입찰가를 계산하는 곳 0건, `from`/`to` 는 CLI 산출물 그대로 옮김 |
| BID-03 | 01-07 | ✓ VERIFIED | `preview_cdp.sh` V-PRE-12a/b 재실행 — 실데이터 70→80, 그룹입찰따름=예 |
| BID-04 | 01-09 | ⚠ 절반 human_needed | 위 성공기준 4 참조 — 버튼 배선·요청본문·범위가드·409 전부 재실행 검증(26/26), 실탄 되돌리기만 human_verification |

**19/19 요구사항이 최소 하나의 Plan 에서 계상됐고, 고아 요구사항 0건** (`grep -n "^requirements:"` 로 9개 Plan 전부 대조).

## 재실행 결과 전체 (이 세션에서 직접 돌림)

```
.venv-web/bin/pytest webapp/tests -p no:warnings          → 199 passed (10.95s)
bash webapp/tests/no_commit_guard.sh                       → exit 0
CT_DEV_TOKEN=devtoken123 bash webapp/tests/security_curl.sh → 9 PASS / 0 FAIL
CT_DEV_TOKEN=devtoken123 bash webapp/tests/board_cdp.sh     → 22 PASS / 0 FAIL
bash webapp/tests/sse_cdp.sh                                → 12 PASS / 0 FAIL
CT_DEV_TOKEN=devtoken123 bash webapp/tests/preview_cdp.sh   → 32 PASS / 0 FAIL
CT_DEV_TOKEN=devtoken123 bash webapp/tests/commit_cdp.sh    → 15 PASS / 0 FAIL
CT_DEV_TOKEN=devtoken123 bash webapp/tests/revert_cdp.sh    → 1차 FAIL(아래 §특이사항) → 원인규명 후 2차 26 PASS / 0 FAIL
CLI 회귀 6종 (nvad·reports·ads_rules·ledger·bids·prune)     → 7+7+21+21+35+16 = 107 tests, 전부 OK
```

**하네스가 green 이라는 사실 자체를 근거로 안 삼았다** — 지시대로 `01-REVIEW.md` 를 먼저 읽고
"영원히 통과하는 검사" 4건(WR-05·06·07·08)이 뭘 단언하는지, 어떻게 고쳐졌는지, 성공기준 문장과
맞는지 대조했다. 리뷰가 Critical 2 + Warning 11 전부 재현·수정했고, 이 세션의 재실행이 그 수정 이후
상태와 정확히 일치함을 확인했다(`git log` 최신 커밋 `d84579e` 가 리뷰 문서화 커밋).

## 특이사항 — `revert_cdp.sh` 1차 FAIL 원인 규명 (중요: 갭 아님)

이 세션에서 `revert_cdp.sh` 를 처음 돌렸을 때 이렇게 FAIL 이 났다:

```
실행(bids_commit) 잡이 레지스트리에 없다 — 결과 표를 띄울 수 없다
```

**원인을 끝까지 추적했다.** `GET /jobs` 라우트(`webapp/routes/jobs.py:574-579`)가 `jobs.recent_jobs(20)` 으로
**최근 20건만** 반환하는데, 이 세션에서 직전에 돌린 `preview_cdp.sh`(미리보기 15건 접수)·`commit_cdp.sh`(미리보기 1건
접수)가 새 `bids_preview` 잡을 계속 쌓아서, 2026-09-20 21:00 에 실제로 472건을 올린 진짜 `bids_commit` 잡
(`61cf4b37-…`)이 최근 20건 창 밖으로 밀려났다. `revert_cdp.sh` 는 그 잡을 `GET /jobs` 응답 안에서 찾는데
못 찾은 것이다.

**이게 상품 결함인지 확인했다.** `grep -rn "/jobs\"" webapp/static/board.js webapp/templates/*.html` →
0건. `GET /jobs`(잡 목록 전체 조회)는 **실제 화면 어디서도 안 쓰인다** — 순수 디버그/테스트 전용
엔드포인트다. 진짜 화면 흐름은 실행 직후 그 결과 페이지(`/jobs/{job_id}`)로 그대로 가고, 그 페이지의
"이 작업분만 되돌리기" 버튼은 `data-job="{{ job.id }}"` 로 **그 페이지에 박힌 job_id 를 직접 쓴다**
(`_result_table.html:145-152`) — `/jobs` 목록을 거치지 않는다. 즉 사용자가 실제로 쓰는 경로(방금 실행한
결과 페이지에서 바로 되돌리기)는 이 20건 제한과 무관하다.

**재현으로 확인했다.** `webapp.db` 를 백업한 뒤 그 `bids_commit` 행의 `started_at` 만 현재 시각으로 갱신해
top-20 창 안으로 되돌리고 `revert_cdp.sh` 를 다시 돌리니 **26/26 PASS**(정답 표 출력: 화면 472 / 서버 472 등
전부 일치). 검증 뒤 `started_at` 을 원래 값으로 되돌리고 `diff` 로 원상복구를 확인했다(다른 컬럼 무변경).
**이 세션이 만든 순서 의존성이었지, Phase 01 코드의 결함이 아니다.**

다만 한 가지는 기록해 둔다: `GET /jobs` 의 20건 하드코딩(`routes/jobs.py:579`)은 REVIEW.md IN-03(`active_job()`
의 50건 창과 같은 계열의 문제)과 같은 종류다. 지금은 프로덕션 화면이 그 엔드포인트를 안 쓰므로 실질 영향이
없지만, 나중에 "최근 작업 목록" UI 를 화면에 노출하게 되면 그때는 실제 갭이 된다 — Phase 2 메모로만 남긴다
(새 항목으로 deferred-items.md 에 추가할 가치가 있다, 이 VERIFICATION 자체의 갭은 아니다).

## Human Verification Required

### 1. 회차 신선도 배너 색상 (D-16)

**Test:** 브라우저에서 `http://127.0.0.1:8765/` 를 열고, 경과일이 임계값(기본 8일)을 넘는 회차를 볼 때
배너가 실제로 경고색으로 보이는지 확인
**Expected:** `<p id="freshness" class="stale">` 가 적용된 상태에서 CSS(`board.html:23-25` `.stale`)가
빨강/주황 계열로 렌더된다
**Why human:** 서버가 `freshness.stale` 불리언을 정확히 계산해 내려주는 것과 `class="stale"` 이 붙는 것까지는
코드로 확인 가능하지만(D-16 데이터 공급원은 `test_paths.py` 로 커버됨), 그 색이 실제로 경고로 읽히는지는
렌더된 화면을 봐야 하는 시각 판단이다. `board_cdp.sh` 도 이 항목은 배지 숫자만 재고 색은 안 잰다
(01-VALIDATION.md Manual-Only 표에도 명시).

### 2. 되돌리기 실탄 실행 (성공기준 4 후반 / BID-04)

**Test:** 되돌리기 버튼을 눌러 실제 네이버 광고 API 에 PUT 을 태우고, 광고 관리 화면에서 입찰가 복원을 확인
**Expected:** 성공기준 4 "화면의 되돌리기 버튼 한 번으로 인상 전 상태로 복원된다"가 실탄으로 증명된다
**Why human:** 2026-09-20 용팀장이 "되돌릴 필요 없다"고 명시적으로 지시해 이 페이즈에서 한 번도 실행하지
않았다. 구조 검증은 전부 끝났다 — 요청 본문이 `commit_job_id` 하나뿐이고 대상 목록을 화면이 안 만든다는 것
(`revert_cdp.sh` V-RVT-21/22, 재실행 확인), 범위가 dry-run 으로 먼저 막힌다는 것(`test_revert.py` 41/41,
재실행 확인), 되돌리기 PUT 이 인상과 같은 공용 함수(`_put_ad`)를 탄다는 것(WR-09 fixed, 인상 쪽은 이미
472/472 실탄 검증됨)까지 전부 코드·테스트로 증명됐다. 남은 건 "네이버 서버가 이 PUT 을 실제로 받아주는가"
하나뿐이고, 이건 실제 광고비·입찰가라는 되돌릴 수 없는 자산을 건드리는 결정이라 사람(용팀장)이 원하는
시점에 직접 눌러 확인해야 한다.

## Anti-Patterns Found

TBD/FIXME/XXX 등 부채 마커: **0건** (`grep -rn -E "TBD|FIXME|XXX" webapp/` — tests 제외 전부 0건).
TODO/HACK/PLACEHOLDER: **0건.** `placeholder` 매치 1건은 Tabulator 빈 상태 UX 문구("조건에 맞는 상품이 없다")로
디버트 마커가 아니다. `\uXXXX` 매치 3건은 JSON 이스케이프를 설명하는 주석/코드로 무관.

**REVIEW.md 처리 상태:** Critical 2 + Warning 11 = 13건 **전부 fixed**(커밋 11개, 이 세션에서 `git log` 로
확인), 재현 검증 포함. Info 6건은 의도적으로 범위 밖(운영 영향 낮음, 문서화됨).

## Deferred Items (갭 아님 — 검토했고 의도적)

| 항목 | 근거 |
|---|---|
| 실행 페이싱 문구가 실측보다 2.7배 낙관적 (초당 12건 vs 실측 4.3건) | `deferred-items.md` 01-08 — Phase 2 후보로 명시. 경과시간이 주 진행표시라 치명적이지 않음 |
| 그룹 입찰가가 회차 밖에서 바뀌면 보드가 낡는다 (13/4,959행) | `deferred-items.md` 01-09 — 신선도(D-16) 확장 성격, Phase 2 후보로 명시 |
| 되돌리기 표에 "되돌리기 직전 실제가" 없음 | `deferred-items.md` 01-09 — PUT 만큼 GET 추가 필요, 명시적 범위 밖 |
| 그룹입찰따름 복귀 시 인상 전 가격과 다를 수 있음(472건 중 2건) | `deferred-items.md` 01-09 — 버그 아님, 각주로 안내 중 |
| `GET /jobs` 20건 하드코딩 | 이 검증에서 새로 발견 — 프로덕션 화면이 그 엔드포인트를 안 써서 현재 영향 없음. Phase 2 에 "최근 작업 목록" UI 가 생기면 재검토 필요 |

## Gaps Summary

**갭 0건.** 성공기준 5개 중 4.5개가 이 세션에서 직접 재실행한 자동 하네스·코드 읽기로 그린이고,
남은 0.5개(성공기준 4 후반 되돌리기 실탄)는 코드·구조·dry-run·CDP 로 전부 검증됐지만 실제 광고 API
쓰기라는 성격상 사람이 원할 때 직접 눌러 확인해야 하는 항목이라 human_needed 로 분류했다. 요구사항
19개 전부 계상됐고 고아 요구사항 0건. REVIEW.md 의 Critical 2 + Warning 11 은 이 세션에서 재실행한
테스트 결과로 수정이 유지되고 있음을 확인했다. `revert_cdp.sh` 1차 FAIL 은 이 세션이 여러 하네스를
연속으로 돌리면서 생긴 잡 히스토리 순서 문제였고, 재현·원인규명·원상복구까지 마쳤다 — Phase 01
코드의 결함이 아니다.

---

_Verified: 2026-09-20T13:48:58Z_
_Verifier: Claude (gsd-verifier)_
