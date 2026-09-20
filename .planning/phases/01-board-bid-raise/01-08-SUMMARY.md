---
phase: 01-board-bid-raise
plan: 08
subsystem: commit-flow
tags: [fastapi, htmx, jinja2, sqlite, cdp, headless-chrome, tdd, naver-ads, first-write]

# Dependency graph
requires:
  - phase: 01-02
    provides: "run_ads.py bids --only-ads / --preview-out · run_bids 의 항목 단위 result/error · before_bids 백업 병합"
  - phase: 01-05
    provides: "jobs.create_job(only_ads → targets 파일) · WRITE_KINDS 전역 쓰기 가드 · BusyError · argv.AdsArgv"
  - phase: 01-06
    provides: "_job_panel.html SSE 배선 · 경과시간 표시(OQ-3) · sse_cdp 하네스 모양"
  - phase: 01-07
    provides: "flow.py 3단 계약 · targets_<job>.json · POST /jobs/bids/preview · _preview_table.html · preview_cdp 하네스"
provides:
  - "POST /jobs/bids/commit — preview_job_id 하나만 받는다. 대상은 부모 targets 파일에서만 온다 (D-11 / FLOW-02)"
  - "jobs.create_job(targets_path_override=…) — only_ads 와 상호배타(ValueError). 새 파일을 쓰지 않는다"
  - "flow.classify_results · result_counts · result_rows · cli_totals · succeeded_ad_ids · diff_preview"
  - "webapp/templates/_result_table.html — 집계 · 항목 단위 성공/실패/스킵+사유 · 미리보기 대비 diff"
  - "webapp/templates/_bid_macros.html — 미리보기·결과 표가 공유하는 컬럼/잘림안내/입찰가칸"
  - "board.html 실행 버튼 + 경고 배너 2줄 · board.js 실행 배선(미리보기 끝나야 열린다)"
  - "GET /jobs/{id}/result 가 kind 로 조각을 고르고 ?format=json 을 받는다"
  - "webapp/tests/commit_cdp.{sh,mjs} — 실행 버튼 게이트 15종 (버튼은 누르지 않는다)"
  - "**실제 인상분 472건(cy728) + before_bids_cy728.json 백업 472건** — Plan 01-09 되돌리기의 입력"
affects: [01-09, "Phase 2 삭제 버튼(같은 3단 형판)", "Phase 5 상세 생성 접수"]

# Tech tracking
tech-stack:
  added: []          # 신규 의존성 0
  patterns:
    - "실행 라우트는 대상을 받지 않는다 — 부모 미리보기 잡의 targets 파일을 가리키기만 한다"
    - "상호배타를 주석이 아니라 ValueError 로 강제한다 (only_ads vs targets_path_override)"
    - "종료코드를 성공 근거로 쓰지 않는다 — 항목 단위 result 파일만 본다"
    - "재계산 차이를 거부하지 않고 보고한다. 0건이어도 한 줄 띄워 대조가 돌았음을 증명한다"
    - "돈 쓰는 버튼의 게이트는 CDP 하네스가 확인하고, 버튼 자체는 사람이 누른다"

key-files:
  created:
    - webapp/templates/_result_table.html
    - webapp/templates/_bid_macros.html
    - webapp/tests/commit_cdp.sh
    - webapp/tests/commit_cdp.mjs
  modified:
    - webapp/jobs.py
    - webapp/routes/jobs.py
    - webapp/flow.py
    - webapp/templates/board.html
    - webapp/templates/_preview_table.html
    - webapp/static/board.js
    - webapp/tests/test_flow.py
    - .planning/phases/01-board-bid-raise/01-VALIDATION.md

key-decisions:
  - "BidsCommitReq 는 preview_job_id 하나뿐 — ad_ids 를 받는 필드를 만들지 않는다(T-1-06 구조적 방어)"
  - "targets_path_override 는 회차 web/ 밑인지 · 실재하는지만 보고 그대로 쓴다. 없으면 ValueError — 빈 목록 폴백 금지"
  - "target_count 는 가리킨 파일을 읽어 센다 — 화면이 준 수를 믿지 않는다"
  - "부모 상태가 done 이 아니면 400 (running 은 별도 문구). 화면 잠금만으로는 부족하다"
  - "result 키가 없는 plan 은 '실행 안 됨' — 성공으로 세지 않고 되돌리기 대상에도 안 넣는다"
  - "결과 표는 실패·스킵을 위로 정렬한다. 표가 잘려도 안 된 것이 먼저 남는다"
  - "CLI 의 committed/failed 와 표의 수가 어긋나면 한쪽을 고르지 않고 둘 다 보여준다"
  - "diff 는 거부하지 않는다 — D-09 로 실행 시점 재계산을 유지했으므로 갈라지는 건 정상이다"
  - "첫 실제 실행은 option-a(cy728 472건). 08-30 미되돌림 겹침이 3건뿐이라 '두 번째 +10' 위험이 제일 작다"

patterns-established:
  - "**되돌릴 수단을 먼저 증명하고 방아쇠를 당긴다.** 실제 원본 adAttr 로 샌드박스 회차를 만들어 `--revert` dry-run 을 태워 복원값·백업 불변·`--only-ads` 좁히기·깨진 파일 폴백 거부까지 확인한 뒤에 실행했다. 백업이 없는 상태에서는 되돌리기 dry-run 이 성립하지 않으므로(파일이 없다) 이 리허설이 유일한 사전 증명 경로다"
  - "**당일 제약의 범위를 정확히 좁혀 말한다.** Pitfall 4 는 '되돌릴 수 없다' 가 아니다 — 입찰가 복원(PUT)은 날짜와 무관하게 동작하고, 날짜 조건은 ledger 의 reverted 플래그에만 걸린다. 넘기면 쿨다운 6일 재인상이 막히는 것뿐이다"
  - "**돈 쓰는 클릭 앞에 서버 쪽 대조를 하나 더 끼운다.** 화면이 '472건' 이라고 말한 뒤, 누르기 전에 jobs 행·targets 파일 내용을 정답지와 교집합해서 확인했다(다른 계정 소재 0건, 중복 0건). 화면과 파일이 갈라지는 순간을 클릭 전에 잡는 유일한 자리다"
  - "체크포인트 자동화는 '게이트는 기계가, 방아쇠는 사람이' 로 나눈다 — commit_cdp.sh 는 버튼이 언제 열리는지만 보고 절대 누르지 않는다"

# Metrics
duration: 약 2시간 20분
completed: 2026-09-20
tasks: 3
files: 12
---

# Phase 01 Plan 08: 실행 — 진짜 입찰가를 올린다 Summary

미리보기가 만든 그 targets 파일을 실행이 재사용하는 3단 계약의 마지막 단을 닫고, **Phase 1 에서 처음으로 실제 네이버 광고 입찰가를 바꿨다 — cy728 472건 전량 성공, 실패 0.**

## 무엇을 만들었나

**Task 1 — `POST /jobs/bids/commit` (커밋 `927df82`)**

실행 라우트가 받는 것은 `preview_job_id` 하나뿐이다. `ad_ids` 를 받는 필드가 모델에 아예 없다 — 화면 상태에서 대상을 다시 만들면 미리보기 뒤 필터를 바꾼 만큼 본 것과 다른 게 실행된다(T-1-06). `jobs.create_job` 에 `targets_path_override` 를 더했고, `only_ads` 와 동시 지정은 `ValueError` 다. "대상 파일은 하나" 가 주석이 아니라 호출하는 순간 터지는 규칙이 됐다.

**Task 2 — 항목 단위 결과 + diff (커밋 `b8d7b73`)**

`classify_results` 가 성공/실패/스킵/실행 안 됨으로 가르고, `diff_preview` 가 미리보기와 갈라진 항목을 사유·before/after 로 보고한다. **거부하지 않는다** — D-09 로 실행 시점 재계산을 유지했으므로 갈라지는 건 정상이고, 이 함수의 일은 숨기지 않는 것이다. 0건이어도 `미리보기 그대로 실행됐다` 한 줄을 띄운다(D-10).

**Task 3 — 첫 실제 실행 (체크포인트, option-a 승인)**

## 실행 결과 (2026-09-20 21:00)

| 항목 | 값 |
|---|---|
| 범위 | `cy728` 단독 · 규칙①노출0 472건 |
| 결과 | **성공 472 · 실패 0 · 스킵 0 · 실행 안 됨 0** |
| CLI 리턴 대조 | `committed 472 / failed 0` — 표와 일치(불일치 경고 미발생) |
| 미리보기 대비 diff | **0건** → `미리보기 그대로 실행됐다` |
| 소요 | 109초 (실측 4.3건/초 — 예상 40초보다 길다, 아래 참조) |
| 인상액 합계 | +4,720원 (클릭당 단가 기준) |
| 백업 | `before_bids_cy728.json` **472건** · None 항목 0 |
| ledger | `2026-09-20` 인상 **472건** 기록 (mtime 08-30 → 09-20) |

**D-11 성립 (실측):** commit 잡 `61cf4b37` 의 `targets_path` 가 부모 미리보기 잡 `d6e53fcc` 의 것과 **문자열까지 동일**하다. argv 에 `--only-ads <그 파일>` 이 실렸다.

**클릭 전 서버 쪽 대조:** targets 파일 472건 · 중복 0 · cy728 ①소재 정답지의 부분집합 · 다른 계정 소재 0건.

## 되돌리기 — 방아쇠 전에 증명했다

백업이 없는 상태에서는 `--revert` dry-run 이 성립하지 않는다(읽을 파일이 없다). 그래서 **실제 cy728 원본 adAttr 2건으로 샌드박스 회차를 만들어** 되돌리기 경로를 먼저 태웠다:

- 복원값이 정확하다 — `{bidAmt: 50, useGroupBidAmt: true}`. **`useGroupBidAmt` 가 원본대로 복원**되므로 인상이 만든 그룹→개별 전환도 함께 취소된다(`build_revert_body`)
- 되돌린 뒤에도 백업 파일은 **불변** — 재시도·부분 되돌리기가 살아 있다
- `--only-ads` 로 2건 → 1건 좁히기 동작 (D-13 의 근거)
- 깨진 대상 파일은 **전량 폴백을 거부**한다
- 샌드박스는 검증 후 삭제

**당일 제약(Pitfall 4 / OQ-2)의 정확한 범위:** 입찰가 복원 PUT 은 날짜와 무관하게 동작한다. 날짜 조건은 `ledger.record_reverted` 의 `reverted` 플래그에만 걸린다 — 날짜를 넘기면 이력에 되돌림이 안 남아 쿨다운 6일 동안 재인상이 막히는 것뿐이고, **돈을 되돌리는 능력은 잃지 않는다.**

실행 직후 같은 targets 파일로 되돌리기 dry-run 을 다시 태워 **되돌릴 대상 472건**을 확인했다 — 지금 무장돼 있다.

## 검증

| 항목 | 결과 |
|---|---|
| `pytest webapp/tests -q` | 147 passed (test_flow 28종 · 01-08 에서 17종 추가) |
| `no_commit_guard.sh` | exit 0 |
| `security_curl.sh` | 9/9 PASS |
| `board_cdp.sh` · `sse_cdp.sh` · `preview_cdp.sh` | 전량 PASS · 불변 |
| `commit_cdp.sh` (신설) | 15/15 PASS — 버튼 미클릭 |
| CLI 회귀 6종 | 100 tests exit 0 |

**음성 대조군 5종** (전부 FAIL 을 보고 복원): override 가 새 파일을 쓰면 D-11 2종 red · diff 은폐하면 1종 red · 실행 안 됨을 성공으로 세면 1종 red · `commit-wrap` 의 hidden 제거하면 V-CMT-01/15 red.

## 예상과 달랐던 것

**① 플랜의 옵션 건수가 전부 낡았다.** 옵션 a 의 "9건" 은 오늘 대상이 아니라 08-30 회차에서 cy728 이 올렸던 9건이었다. 오늘 실측은 **472건**이다. 실행 범위가 52배 차이났으므로 숫자를 다시 재서 체크포인트에 실었다.

**② 스킵이 0건이다.** 마지막 인상이 21일 전이라 쿨다운 6일을 전부 통과했고, 현재가 최대가 120원이라 상한(200)에 걸리는 소재가 없었다. 고른 만큼 전부 올라간다 — 그래서 대상 수 확인이 곧 실행 규모 확인이었다.

**③ 초당 12건은 낙관적이다.** CLI 의 `time.sleep(0.08)` 만 보면 40초지만, 실제는 **109초(4.3건/초)** 였다. PUT 왕복 지연이 sleep 보다 크다. 화면의 예상 시간 문구가 실제보다 2.7배 짧게 나온다 — 경과시간이 주 진행 표시라 치명적이지 않지만, 1,300건짜리 계정이면 "40초라더니 5분" 이 된다. `deferred-items.md` 에 적었다.

## Deviations from Plan

### Rule 3 — 블로킹 해소

**1. `webapp/static/board.js` 수정 (플랜 files_modified 에 없음)**
- **발견:** Task 1 — 실행 버튼을 board.html 에만 두면 FLOW-01("미리보기 job_id 가 있어야 활성화")을 만족시킬 수단이 없다. 미리보기 job_id 는 board.js 안에만 산다.
- **조치:** `결과기다리기` 를 자리/몸통 인자로 일반화해 미리보기·실행이 같은 흐름을 타게 하고, `실행열기`/`실행닫기` 를 더했다.
- **커밋:** `927df82`

**2. `webapp/routes/jobs.py` 의 `GET /jobs/{id}/result` 분기 (Task 2 files 에 없음)**
- **발견:** 결과 표를 만들어도 라우트가 kind 를 안 보면 실행 잡에 미리보기 조각이 그려진다.
- **조치:** kind 로 조각을 고르고 `?format=json` 을 받게 했다. 컨텍스트 조립은 `_미리보기표ctx`/`_실행표ctx` 헬퍼로 분리(V-SAFE-01d 스캐너가 GET 핸들러 본문을 훑으므로 위험 호출을 본문 밖으로 뺀다).
- **커밋:** `b8d7b73`

### Rule 2 — 빠진 검증 추가

**3. `test_결과가_안_적힌_항목은_성공이_아니다` 추가**
- **발견:** 음성 대조군을 돌렸더니 "`result` 키 없는 plan 을 성공으로 센다" 는 변이를 **아무 테스트도 못 잡았다.** 플랜이 명시한 규칙인데 검증이 비어 있었다.
- **조치:** 테스트를 더하고 같은 변이로 red 를 확인한 뒤 복원.
- **커밋:** `b8d7b73`

**4. `webapp/tests/commit_cdp.{sh,mjs}` 신설 (플랜에 없음)**
- **근거:** FLOW-01 의 절반이 board.js 안에 있어 pytest 로는 닿지 않는다. 01-07 의 "체크포인트 항목은 하네스로 대행" 관례를 따라 게이트만 기계가 보게 했다. 버튼은 누르지 않는다.
- **커밋:** `8e378de`

### Rule 1/4 해당 없음
버그 수정 없음. 아키텍처 변경 없음.

## Known Stubs

없다. 이 플랜의 모든 화면 요소가 실데이터로 채워졌다(실행 결과 표는 실제 472건 실행 산출물로 렌더됐다).

## 남은 확인 — 사람 몫

**네이버 검색광고 관리 화면에서 대조할 소재 (8번):**

| 항목 | 값 |
|---|---|
| adId | `nad-a001-02-000000440618182` |
| 상품명 | 인명구조 밧줄 화재 아파트화재 인명구조용로프 노끈 로프 |
| 계정 | cy728 |
| 변경 | **70 → 80** (그룹 기본가 70 에서 출발 · 그룹입찰따름이었다) |
| 화면에서 보일 모습 | 입찰가 **80원** · 그룹 입찰가 사용 **해제됨** |
| 되돌리면 | `bidAmt 50 · useGroupBidAmt true` (= 그룹 기본가 70 을 다시 따른다) |

**10번(실행 중 다른 쓰기 버튼 → 409)은 확인하지 못했다.** 109초 실행이 끝난 뒤에 확인을 시작했다. 플랜이 허용한 대로 Plan 01-09 에서 되돌리기 실행 중에 확인한다.

## Deferred Issues

`deferred-items.md` 참조 — 페이싱 문구(초당 12건 vs 실측 4.3건/초).

## Self-Check: PASSED

- 생성/수정 파일 11개 전부 디스크에 존재
- 커밋 3개(`927df82` · `b8d7b73` · `8e378de`) 전부 git 에 존재
- 실행 산출물 2개(`before_bids_cy728.json` 472건 · `result_61cf4b37….json`) 존재
- jobs 행 대조: `bids_commit` exit 0 · target_count 472
- 결과 파일 대조: plans 472 · 성공 472 · committed 472 · failed 0 (SUMMARY 의 수치와 일치)
