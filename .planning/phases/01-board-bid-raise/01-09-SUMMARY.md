---
phase: 01-board-bid-raise
plan: 09
subsystem: revert-flow
tags: [fastapi, htmx, jinja2, sqlite, cdp, headless-chrome, tdd, naver-ads, revert, safety]

# Dependency graph
requires:
  - phase: 01-02
    provides: "bids.run_revert(only_ads=…) · run_ads.py --revert 분기(result.json 불필요) · --preview-out"
  - phase: 01-05
    provides: "jobs.create_job · WRITE_KINDS 전역 쓰기 가드 · BusyError · argv.AdsArgv(revert 필드)"
  - phase: 01-07
    provides: "flow.py 3단 계약 · read_preview · _bid_macros.html"
  - phase: 01-08
    provides: "create_job(targets_path_override=…) · flow.succeeded_ad_ids · _result_table.html · 실제 인상분 472건 + before_bids_cy728.json"
provides:
  - "POST /jobs/revert/job — commit_job_id 하나만. 대상은 실행 잡 산출물의 성공 adId 뿐 (D-13)"
  - "POST /jobs/revert/round — confirmed_count 불일치 409 + dry-run 대조 409 (D-14)"
  - "GET /jobs/revert/round/count — 확인 단계가 **누르는 순간** 묻는 수 (읽기 전용)"
  - "flow.revert_targets_for_job · revert_round_targets · revert_dry_run · check_revert_scope · ScopeError"
  - "bids.run_revert 가 plans[] 를 낸다 — adId·to·useGroupBid·restore, 쓰기 경로에선 result/error (FLOW-05 연장)"
  - "webapp/templates/_revert_table.html — 되돌리기 전용 표(인상 표를 재사용하지 않는다)"
  - "board.html 위험 구역 — 회차 전체 되돌리기, 기본 접힘 + 건수 확인 단계"
  - "webapp/tests/revert_cdp.{sh,mjs} — 26종. 되돌리기 요청을 한 건도 안 보낸다"
  - "webapp/tests/test_revert.py — 41종. 범위 분기·백업 불변·409·배너 양방향"
affects: ["Phase 2 삭제 버튼(되돌릴 수 없는 작업 — 이 계약 위에서만 열린다)", "Phase 2 ENG-04 대상별 잠금", "Phase 2 OQ-2 ledger 날짜 조건"]

# Tech tracking
tech-stack:
  added: []          # 신규 의존성 0
  patterns:
    - "되돌리기 범위는 화면이 정하지 않는다 — 실행 잡의 산출물에서 성공 adId 만 추려 --only-ads 로 넘긴다"
    - "쓰기 전에 CLI 에게 범위를 되묻는다(dry-run) — 웹앱이 백업을 해석해 추정하면 진실이 둘이 된다"
    - "위험한 버튼은 거리·접힘·확인 3층으로 가른다. '다른 섹션' 만으로는 부족하다(478px 도 다른 섹션이다)"
    - "검증이 겹치면 앞의 것을 지워도 뒤의 것이 초록을 만들어 준다 — 대조군은 격리해서 걸어야 한다"
    - "돈 쓰는 클릭의 배선은 fetch 를 가로채고 **가로채기가 걸렸는지 프로브로 확인한 뒤에만** 누른다"

key-files:
  created:
    - webapp/templates/_revert_table.html
    - webapp/tests/test_revert.py
    - webapp/tests/revert_cdp.sh
    - webapp/tests/revert_cdp.mjs
  modified:
    - .claude/skills/naver-ads-weekly/scripts/bids.py
    - webapp/flow.py
    - webapp/routes/jobs.py
    - webapp/templates/_result_table.html
    - webapp/templates/board.html
    - webapp/static/board.js
    - .planning/phases/01-board-bid-raise/01-VALIDATION.md
    - .planning/phases/01-board-bid-raise/deferred-items.md

key-decisions:
  - "RevertJobReq 는 commit_job_id 하나뿐 — ad_ids 를 받는 필드를 만들지 않는다(BidsCommitReq 와 같은 구조적 방어)"
  - "부모 실행 잡이 done 일 것을 **요구하지 않는다** — failed·orphaned 야말로 되돌려야 하는 상태다. running 만 막는다"
  - "ScopeError 를 ValueError 보다 **먼저** 잡는다 — 순서가 뒤집히면 '2,242건' 이 그냥 '잘못된 요청' 으로 뭉개진다"
  - "ScopeError 는 400 이 아니라 409 — 요청이 틀린 게 아니라 디스크 상태와 어긋난 것이다"
  - "revert_round_targets 는 백업이 깨졌으면 0 이 아니라 ValueError — '되돌릴 게 없다' 와 '못 셌다' 를 같은 화면으로 만들지 않는다"
  - "revert_dry_run 의 산출물은 회차 안에 안 남긴다(임시 폴더) — 범위 확인은 감사 대상이 아니라 게이트다"
  - "되돌리기 plans 에 from(되돌리기 직전 실효가)을 싣지 않는다 — 스냅샷은 인상 전 값이라 지금 값이 아니다"
  - "회차 전체 버튼은 페이지 맨 아래 위험 구역에 둔다. 기본 접힘 + 건수 확인 + 1,625px 거리"
  - "확인 단계의 건수는 템플릿에 박지 않고 **누르는 순간** 서버에 묻는다 — 그 사이 인상이 더해졌으면 승인 규모가 달라진다"
  - "용팀장 지시로 실제 광고 API 되돌리기는 실행하지 않았다. 인상 472건 유지"

patterns-established:
  - "**검증이 겹치면 앞의 것이 죽어도 뒤의 것이 초록을 만들어 준다.** `confirmed_count` 대조를 통째로 지웠는데 테스트가 통과했다 — 뒤의 `check_revert_scope` 가 대신 409 를 냈기 때문이다. 대조군은 **뒷 단을 고정해 앞 단만 격리**해서 걸어야 한다. 이 페이즈에서 나온 다섯 번째 '화면·테스트에 증상이 안 나타나는' 부류다(01-04 배지랙 · 01-06 sse-close · 01-07 rowRange · 01-08 result 키 없음 · 01-09 가짜 409)"
  - "**실데이터로 증명 못 하는 분기는 스위트에 남는 합성 테스트로 증명한다.** 오늘 회차는 인상이 한 번뿐이라 '작업분' 과 '회차 전체' 가 같은 수다. 일회성 샌드박스로 확인하고 지우는 대신, 진짜 CLI 프로세스로 가짜 작업분 2개를 누적시킨 회차를 만들어 `3 / 4 / 7` 이 **서로 달라야** 통과하게 묶었다 — 셋이 같아지면 빨개진다"
  - "**돈 쓰는 버튼의 배선은 fetch 를 가로채고 프로브로 확인한 뒤에만 누른다.** 확인하려는 게 '무엇이 나가는가' 라서 진짜로 보낼 수 없다. 가로채기가 안 걸렸으면 거기서 멈추고 버튼을 누르지 않으며, 마지막에 잡 레지스트리를 다시 읽어 0건을 사후 확인한다"
  - "**오클릭 방어는 픽셀로 재야 한다.** '두 버튼이 다른 섹션에 있다' 는 pytest 가 보지만, 위험 구역을 결과 표 밑으로 옮기면 그 단언은 **여전히 PASS** 고 거리만 478px 로 줄어든다(음성 대조군 실측). 거리 단언이 없으면 D-14 는 지켜지는 척만 한다"

# Metrics
duration: 약 30분
completed: 2026-09-20
tasks: 3
files: 12
---

# Phase 01 Plan 09: 되돌리기 Summary

되돌리기 기능을 전부 만들고 범위 분기를 기계로 증명했다 — **실제 광고 API 되돌리기는 0건, 인상 472건은 그대로 살아 있다**(용팀장 지시).

## 무엇을 만들었나

**Task 1 — 범위 계약 (커밋 `7fe8111` RED · `f92ca9e` GREEN)**

이 플랜이 막는 사고는 구체적이다: `before_bids_<alias>.json` 은 회차 안에서 **누적 병합**된다. 화면의 되돌리기를 `--revert` 에 그냥 연결하면 5건 올리고 눌렀는데 그 회차 인상분 전부가 풀린다 — `2026-08-30` 백업에 **2,242건**이 실제로 들어 있다(실측 재확인: 9+10+1195+1028).

`test_revert.py` 41종이 세 가지를 못박는다: `only_ads` 3건이면 대상 3건 · 백업 파일이 되돌리기 전후로 **바이트 단위로 같다**(dry-run·쓰기 양쪽) · `only_ads` 없으면 백업 전량(= 직결하면 안 되는 이유).

GREEN 단계에서 `bids.run_revert` 가 `plans[]` 를 내도록 고쳤다(플랜 이탈 1 — 아래). 건수만 돌려주면 "469 성공 / 3 실패" 에서 그 3건이 어느 소재인지 화면이 말할 수 없는데, 되돌리기는 사고 대응 경로라 다시 겨눌 대상을 알아야 한다.

**Task 2 — 버튼 2개 + 4층 방어 (커밋 `c119dd3`)**

| 층 | 무엇 | 어디 |
|---|---|---|
| (a) | 화면의 되돌리기를 `--revert` 에 직결하지 않는다 | 라우트가 갈려 있다 |
| (b) | 실행 잡 산출물의 **성공 adId 만** `targets_revert_<job>.json` → `--only-ads` | `flow.revert_targets_for_job` |
| (c) | 쓰기 전 **dry-run 선행** — CLI 가 센 대상 수가 부모 성공 건수와 다르면 차단 | `flow.revert_dry_run` + `check_revert_scope` |
| (d) | 회차 전체는 **물리적으로 다른 버튼** + 건수 확인 + `confirmed_count` 불일치 409 | 위험 구역 + `POST /jobs/revert/round` |

**Task 3 — CDP 하네스 26종 (커밋 `a259a5d`)**

되돌리기 요청을 서버에 **한 건도 안 보내고** 배선과 배치를 확인한다. 페이지 안에서 `window.fetch` 를 가로채되, **가로채기가 실제로 걸렸는지 프로브로 확인한 뒤에만** 버튼을 누른다. 마지막에 `/jobs` 를 다시 읽어 `revert_*` 잡 **0건**을 사후 확인한다.

## 범위 분기 증명 — 실데이터로는 못 한다, 그래서 이렇게 했다

`2026-09-20` 회차에는 인상이 472건 **한 번뿐**이라 "이 작업분" 과 "이 회차 전체" 가 우연히 같은 수다. 실데이터로는 D-12/D-13 의 분기를 증명할 수 없다.

진짜 CLI 프로세스로 샌드박스 회차에 **가짜 작업분 2개가 누적된** 상태를 만들었다(`test_회차전체와_작업분은_다른_수다`):

| 호출 | 대상 |
|---|---|
| `--only-ads <A>` | **3건** |
| `--only-ads <B>` | **4건** |
| 플래그 없음 | **7건** |

`argv → argparse → cmd_bids → run_revert` 사슬 전체를 탄다. 일회성 확인이 아니라 스위트에 남고, **셋이 같은 수가 되면 빨개진다**. `2026-08-30` 의 2,242건은 건드리지 않았다(`revert_round_targets` 로 읽기만).

## 검증

| 항목 | 결과 |
|---|---|
| `pytest webapp/tests -q` | **186 passed** (`test_revert.py` 41종 신설) |
| `no_commit_guard.sh` | exit 0 |
| CLI 회귀 6종 | **100 tests exit=0** (7+7+21+21+28+16) |
| `security_curl.sh` | **9/9** (V-SAFE-01d 포함 — 신규 GET 이 상태를 안 바꾼다) |
| `board_cdp` · `sse_cdp` · `preview_cdp` · `commit_cdp` | 22 · 12 · 31 · 15 전량 PASS · 불변 |
| `revert_cdp.sh` (신설) | **26/26** · 되돌리기 요청 0건 |

**디스크 대조 (되돌리기 0건 증명):** `before_bids_cy728.json` 472건 · mtime `21:00:00` 그대로 · `ledger/cy728.json` 오늘 인상 472 · `reverted` **0** · 잡 레지스트리 `revert_*` **0행**.

**409 동시 쓰기 (01-08 이 못 하고 넘긴 항목 — 여기서 닫았다).** 합성 `revert_only`/`revert_all` 잡을 띄우고 살아 있는 서버에 실측:

| 요청 | 결과 |
|---|---|
| 회차 전체 되돌리기 | **409** |
| 새로 수집(prep) | **409** |
| 입찰가 인상 실행 | **409** |
| 미리보기(쓰기 아님) | **200** ← 음성 대조군. 쓰기가 아닌 것까지 막는 가드는 사람이 가드를 끄게 만든다 |

**음성 대조군 9종 — 전부 red 를 보고 복원:** `only_ads` 무시 · 백업 키 삭제 · `record_reverted` 날짜조건 제거 · 대상 파일 미전달 · 범위 가드 생략 · 실패 소재까지 대상에 포함 · 회차전체 버튼을 결과 표 옆에 배치 · `confirmed_count` 대조 제거 · 위험 구역을 결과 표 밑으로 이동(1,625px → 478px).

## 예상과 달랐던 것

**① 가짜 초록을 하나 잡았다.** `confirmed_count` 대조를 통째로 지웠는데 테스트가 **그대로 통과**했다. 뒤의 `check_revert_scope` 가 대신 409 를 냈기 때문이다 — 같은 상태코드라 겉으로는 구분이 안 된다. dry-run 을 실제 값으로 고정해 대조 단계만 격리했더니 red 가 나왔다. **검증이 겹치면 앞의 것이 죽어도 뒤의 것이 초록을 만들어 준다.** 이 페이즈에서 나온 다섯 번째 "증상이 안 나타나는" 부류다.

**② '다른 섹션' 단언은 오클릭을 못 막는다.** 위험 구역을 결과 표 바로 밑으로 옮기는 음성 대조군에서, `V-RVT-12`(서로 다른 섹션)는 **여전히 PASS** 였고 거리만 1,625px → 478px 로 줄었다. pytest 로 보장할 수 있는 것은 "조각이 다르다" 까지이고, D-14 의 실제 내용은 픽셀에 있다.

**③ 하네스가 낡은 서버를 잡았다.** 첫 실행에서 `V-RVT-15/23/25` 가 red 였다. 원인은 코드가 아니라 **01-08 때 띄운 서버가 포트를 쥐고 있어서** 새 인스턴스가 바인드에 실패한 것이었다. 템플릿·JS 는 디스크에서 다시 읽혀 통과하는데 **파이썬 라우트만 낡아** 신규 GET 이 404 였다. 육안 확인이었으면 "건수가 0이네" 로 넘어갔을 모양이다.

**④ 되돌리기가 복원하는 건 '소재 설정' 이지 '실효 가격' 이 아니다.** 472건 중 **458건**이 되돌리면 `useGroupBidAmt: true` 로 복귀한다 = 그룹 기본가를 따른다. 그 사이 그룹 기본가가 바뀌었으면 실효가는 인상 전 값과 다르다. 실측으로 오늘 인상한 472건 중 **2건**이 21:07 에 70→80 으로 바뀐 그룹에 속해서, 되돌려도 70 이 아니라 **80** 이 된다. `build_revert_body` 는 adAttr 를 정확히 복원하므로 버그가 아니다 — 화면이 그 사실을 말하지 않을 뿐이라 `_revert_table.html` 각주로 알린다.

## Deviations from Plan

### Rule 3 — 블로킹 해소 (오케스트레이터 승인)

**1. `.claude/skills/naver-ads-weekly/scripts/bids.py` 수정 (플랜 `files_modified` 에 없음)**
- **발견:** Task 1 — `run_revert` 가 건수만 돌려줘서 산출물에 `plans` 키가 없었다. 그러면 `flow.read_preview` 가 그 계정을 `blind`(측정 안 됨)로 분류해 **되돌리기 결과 화면이 전부 "스냅샷을 못 읽었다"** 가 된다. 플랜 Task 1 의 `test_되돌리기_결과도_항목단위다` 가 명시적으로 요구한 동작이기도 하다.
- **조치:** `plans[]` 를 낸다(`adId`·`title`·`action`·`to`·`useGroupBid`·`restore`, 쓰기 경로에선 `result`/`error`). `run_bids` 와 같은 모양이라 화면이 같은 코드로 읽는다.
- **확인:** CLI 회귀 100 tests 그대로 exit=0 (키 추가는 기존 단언과 무관).
- **커밋:** `f92ca9e`

**2. `webapp/templates/_revert_table.html` 신설 (플랜에 없음)**
- **발견:** 인상 결과 표를 재사용하면 `현재가 → 인상 후` 컬럼에 복원값이 들어가 **내린 것을 올린 것처럼** 보여준다.
- **조치:** 되돌리기 전용 표. 컬럼은 `되돌린 입찰가 · 그룹입찰따름` 이고, `from` 은 아예 없다.
- **커밋:** `c119dd3`

**3. `GET /jobs/revert/round/count` 신설 (플랜에 없음)**
- **발견:** 확인 단계 건수를 템플릿에 박으면 페이지 로드 시점의 수가 된다. 그 사이 다른 작업이 인상을 더했으면 **사용자가 승인하는 규모가 달라진다.**
- **조치:** 누르는 순간 서버에 묻고, 그 수가 그대로 `confirmed_count` 로 돌아와 접수 시점에 다시 대조된다.
- **커밋:** `c119dd3`

**4. `webapp/tests/revert_cdp.{sh,mjs}` 신설 (플랜에 없음)**
- **근거:** D-14 의 실제 내용(거리·접힘·확인 단계·취소)이 board.js 와 렌더링 안에만 산다. 01-07/01-08 의 "체크포인트 항목은 하네스로 대행" 관례를 따랐다.
- **커밋:** `a259a5d`

### Rule 1 / Rule 4 해당 없음
버그 수정 없음. 아키텍처 변경 없음.

## Known Stubs

없다. 모든 화면 요소가 실데이터로 채워졌다 — 되돌리기 버튼의 `472` 는 실제 실행 잡 `61cf4b37` 의 산출물에서, 회차 전체 확인 단계의 `472` 는 실제 백업 파일에서 왔다.

## Threat Flags

없다. 새 네트워크 표면은 POST 2개 + GET 1개이고 전부 기존 가드(Host·Origin·토큰·쓰기 전역 락)를 그대로 탄다. 신규 GET 은 `V-SAFE-01d` 스캐너를 통과했다(상태를 바꾸지 않는다).

## 남은 리스크 — Phase 2 로 넘어간다

**실제 광고 API 를 상대로 한 되돌리기는 Phase 1 에서 한 번도 실행되지 않았다.**
사고가 났을 때 **처음 눌러 보는 경로**가 된다는 뜻이다.

| 리허설로 덮은 것 | 못 덮은 것 |
|---|---|
| 대상 좁히기 · 백업 불변 · 범위 가드 · argv 조립 · 409 · 화면 배치 · 요청 본문 · 복원 PUT 본문(`{bidAmt:50, useGroupBidAmt:true}` — 01-08 샌드박스 실측) | **네이버 광고 API 가 실제로 그 PUT 을 받아 값을 바꾸는 것** 하나 |

**싸게 닫는 법:** 소수 건만 되돌렸다 **즉시 재인상**. `ledger.last_raise_date` 가 `reverted` 붙은 항목을 건너뛰므로 **당일 되돌리면 쿨다운이 안 걸린다** — 되돌린 소재를 곧바로 다시 올릴 수 있다(`test_같은_날_되돌리면_플래그가_찍힌다` 로 확인). 비용은 소재 몇 개의 왕복뿐이다.

## Open Questions

- **OQ-2 (Phase 1 확정: 고치지 않는다) 재확인.** `ledger.record_reverted` 가 당일에만 `reverted` 를 찍는다. 날짜를 넘기면 입찰가는 **정상 복원되지만**(PUT 은 날짜 무관) 이력에 안 남아 쿨다운 6일 동안 재인상이 막힌다. 현재 동작을 문서화하는 테스트를 남겼다(`test_날짜를_넘기면_되돌림_플래그가_안_찍힌다`) — **Phase 2 가 로직을 바꾸면 이 테스트가 뒤집혀야 한다.** 당일 대조군도 같이 걸어 뒀다(대조군이 없으면 `record_reverted` 가 아예 안 돌아도 통과한다).
- **실탄 되돌리기를 언제 한 번 태울 것인가.** 위 "싸게 닫는 법" 이 답이다. Phase 2 의 파괴적 삭제 전에 닫는 게 맞다 — 삭제는 되돌릴 수단이 없어서, 되돌리기 경로가 검증됐다는 전제 위에서만 열린다.
- **되돌리기 중 진행 표시가 없다.** 인상과 같은 이유(OQ-3) — 경과시간만 보인다. 472건이면 100초쯤이다.

## Deferred Issues

`deferred-items.md` 참조. 이번에 4건을 적었고 그중 하나는 **닫힌 게 아니라 원인이 바뀌었다**:

> **오케스트레이터가 "`run` 재판정으로 해소" 라고 보고했는데, 재실측 결과 안 풀렸다.**
> 21:38 재판정 뒤에도 낡은 `groupBid` 13행이 그대로다. 이유가 구조적이다 — 그룹 입찰가는
> `accounts/<alias>/ads.json` 의 `groups` 에 있고 그걸 쓰는 건 **`prep`**(`GET /ncc/adgroups`,
> `collect.py:36-40`)이다. `run` 은 그 스냅샷을 **다시 읽어 규칙만 매긴다**(네트워크 0).
> 실측 확인: `grp-…858512` 가 아직 `bidAmt: 70`(실제는 80).
> **`prep` 을 다시 돌려야 풀린다**(계정당 ~3분). 항목은 **열어 뒀다.**

나머지 3건: 페이싱 문구(01-08 이월) · 되돌리기 표에 `from` 없음 · 그룹입찰따름 복귀 2건의 실효가 차이(구조적, 열어 둠).

## Self-Check: PASSED

- 생성/수정 파일 12개 전부 디스크에 존재
- 커밋 5개(`7fe8111` · `f92ca9e` · `c119dd3` · `a259a5d` · `4bf1cda`) 전부 git 에 존재
- `pytest webapp/tests -q` 186 passed · CLI 회귀 100 tests exit=0 (SUMMARY 의 수치와 일치)
- 디스크 대조: 백업 472 @ 21:00 · ledger 인상 472 / reverted 0 · `revert_*` 잡 0행 (되돌리기 0건 주장과 일치)
- 하네스 6종 실행 결과가 오케스트레이터 독립 재실행과 일치(9 · 22 · 12 · 31 · 15 · 26)
