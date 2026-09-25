# Phase 5: 상세페이지 작업 버튼 ★ Core Value - Context

**Gathered:** 2026-09-25 (`/gsd-discuss-phase 5 --auto` — 용팀장 부재, 전 항목 추천안 자동 선택)
**Status:** Ready for planning

> ⚠️ **이 문서의 결정은 전부 `[auto]` 다.** 사람이 답한 게 아니라 추천안을 고른 것이다.
> 그중 **`[auto — 용팀장 확인 필요]`** 표시가 붙은 4건(D-01 · D-02 · D-09 · D-14)은 플랜이 짜여도
> **첫 크레딧 접수 체크포인트 전에** 용팀장에게 한 줄씩 확인받는다. 뒤집히면 해당 플랜만 고친다.

<domain>
## Phase Boundary

🔴(필요시 🟡) 상품을 보드에서 골라 → **견적(크레딧 0 미리보기)** → **사람 승인** → **AI 상세 접수** →
**폴링(브라우저를 닫아도 계속)** → **결과 확인**까지를 터미널 없이 완주한다.
입력은 기존 상세 이미지 − 홍보배너(Phase 4 산출물), 생성은 기존 CLI `detail_batch.py` 를 subprocess 로 감싼다.

**린 MVP 조각:** 고르기 → 견적 → 접수 → 폴링(생존) → 결과 표시. Success Criteria 1~5 에 필요 없는 것은 전부 Deferred.

**이 페이즈가 아닌 것:** 스마트스토어 반영(`market_update` — Phase 6) · 썸네일/쿠팡(Phase 7) ·
배너 판정 정확도 개선(D-23 로 닫힘 — 지시문 v4·out-of-sample 재측정은 Deferred) · 무인 스케줄.

</domain>

<decisions>
## Implementation Decisions

### 🔒 잠긴 제약 (auto 아님 — 프로젝트·메모리에서 승계, 플랜이 바꿀 수 없다)

- **L-01: 크레딧을 쓰는 동작과 되돌릴 수 없는 동작은 전부 플랜의 blocking human checkpoint 다.**
  구체적으로: ① 모든 실제 AI 상세 접수(첫 5건 실탄 포함) ② 비전 2차 유료 호출 상한을 0 에서 올리는 것
  ③ 실패분 재접수 ④ 불사자 태그 쓰기(D-10 폴백이 발동할 때). 각 체크포인트 앞에 **견적(건수 · 장수 · 크레딧)** 을 보여 준다.
  `autonomous: false` 이고 `--auto` 체인도 이 체크포인트를 자동 승인하지 않는다.
- **L-02: 접수 전 예상 크레딧 보고 → 승인 → 접수. 순서 예외 없음** (PROJECT.md 안전 제약 · DETAIL-05 · 스킬 절대규칙 4).
- **L-03: 폴링 타임아웃은 실패가 아니다.** 재접수로 풀지 않는다 — 크레딧 이중 지불 (DETAIL-06 · 메모리 `thumb-poll-timeout-is-normal`).
- **L-04: 기존 CLI 재작성 금지.** `detail_batch.py` 는 subprocess 로 부르고, 필요한 건 **주입구 플래그 추가**만 한다 (ENG-01 · Phase 1 01-02 선례).
  웹앱은 불사자 MCP 를 직접 부르지 않는다 (Phase 3 D-19).
- **L-05: 진실의 원천은 불사자 서버.** 기작업 판정용 로컬 대장을 새로 만들지 않는다 (PROJECT.md · Phase 3 D-09).
  run-dir 의 `detail_status.json` 은 **그 회차 접수의 재개 체크포인트**일 뿐 기작업 정본이 아니다.
- **L-06: 계정 가드(ENG-08) 그대로.** 기대 계정(부킹/용쌤)이 아니면 미리보기·접수 모두 거부.

### 배너 입력 — 새 회차 기본값 (D-23 이 넘긴 질문)

- **D-01 `[auto — 용팀장 확인 필요]`: 새 회차는 검수 화면 사람 확인(약 11분)을 통과해야 접수 가능해진다. 비전 2차는 끈 채(`banner_vision2_max_calls = 0`)로 둔다.**
  · [auto] Q: "새 회차 배너 판정을 ⓐ 사람 확인 ⓑ 비전 끄고 어휘군 단독 중 무엇으로?" → Selected: **ⓐ 사람 확인 + 비전 2차 off** (recommended)
  · 새 회차 흐름: 배너 스캔(1차 어휘군만 · 토큰 0) → 검수 화면에서 상품별 라벨 수정 + `확인함` → 확인된 상품만 상세 견적 대상
  · 이유: ⓑ 단독은 지금 라벨로 재면 **미탐 8**(04-GATE §17-2 참고행) — 중국 점포 로고·위챗이 스마트스토어에 올라간다(BANNER-04 가 가장 비싸다고 한 사고). 비전 2차를 켜면 제품 이미지 **약 14% 누락**. 사람 11분이 둘 다 막는 가장 싼 값
  · 비전 2차는 용팀장이 견적(회차당 약 $2)을 보고 승인할 때만 켠다 — 켜도 사람 확인 요구는 그대로
  · **확인이 필요한 이유:** BANNER-04 는 "게이트 통과해야 실제 작업에 쓴다"인데 게이트는 불통과(D-23)다. 이 결정은 **전역 게이트 대신 "상품별 사람 확인"을 입장 조건으로 쓰는 것** — 요구사항 문구를 사실상 대체한다

- **D-02 `[auto — 용팀장 확인 필요]`: 상세 입력 관문은 `게이트통과` 대신 "사람 확인된 상품 + 사람 라벨 우선 판정"으로 연다.**
  · 지금 `webapp/banner.py::제품이미지목록(상품, 게이트통과=False)` 는 게이트가 `True` 가 아니면 예외다 — 게이트가 false 라 **이대로면 Phase 5 입력이 영원히 0건**
  · 새 입장 조건(상품 단위): ① 그 상품이 `banner_confirm` 에 있고 확인시각 ≥ 해당 산출물 `생성시각` ② 스킵 상품 아님 ③ 미판정 장 0
  · 제품 이미지 = **라벨 있으면 라벨, 없으면 기계** (회차 2026-09-20 정본 규칙, D-23 ①) — `무내용` 은 빠진다
  · 구조 가드는 유지한다: 기본값으로 열리는 길이 없어야 한다(인자 누락 = 예외). 관문 이름만 바뀐다
  · 회차 `2026-09-20` 은 60/60 확인 완료라 **바로 접수 가능** — SC-1 의 첫 5건은 이 회차에서 고른다

- **D-03 [auto]: 검수 화면 `확인함` 재클릭 불가 결함을 이 페이즈에서 고친다** (04-CONTEXT Deferred 에서 끌어옴).
  · [auto] Q: "D-01 이 확인시각에 기대는데 재스캔 후 다시 확인할 길이 없다 — 고칠까?" → Selected: **고친다(최소 수정)** (recommended)
  · 이유: D-02 ① 조건이 "확인시각 ≥ 산출물 생성시각"이라, 재스캔한 상품은 이 결함 때문에 **영원히 접수 불가**가 된다. D-01 의 전제조건이지 범위 확장이 아니다
  · 범위: 이미 확인된 상품에도 `확인함`(다시 확인) 버튼을 그린다. 그 이상은 안 한다 (`게이트: 열렸다` 문구 수정은 Deferred 그대로)

- **D-04 [auto]: 배너 스킵 상품(BANNER-05)은 상세 대상에서 빠진다. 사람 라벨로 스킵 여부를 다시 계산하지 않는다.**
  · [auto] Q: "사람 라벨로 보면 스킵이 아닌 상품(`dnb2lYw0` 57%→11%)을 되살릴까?" → Selected: **안 되살린다 — 스킵 사유 배지로 보이고 끝** (recommended)
  · 이유: 스킵 재계산은 규칙 재구현(S-1 위반)이고 린 MVP 밖. 처리량 우선(메모리 `throughput-over-per-product`) — 1건 잃고 넘어간다

### 대상 고르기

- **D-05 [auto]: 기본 대상은 🔴. 🟡 는 보이고 수동 체크로 넣을 수 있다. ⚪·`구매_가공완료` 는 회색·기본 제외(Phase 3 D-08 그대로).**
  · [auto] Q: "🟡(단순번역)도 대상인가?" → Selected: **🔴 기본 선택 · 🟡 수동 선택 허용** (recommended — Core Value 문장이 "중국어 원본·단순번역" 둘 다를 말한다)
- **D-06 [auto]: 작업 대상은 조인으로 이어진 사본 1개(판매자상품코드)뿐이다.** 같은 불사자코드의 다른 사본은 건드리지 않고 팬아웃 경고(Phase 3 JOIN-03)만 보인다.
  · 화면·리포트의 상품 표기는 **판매자상품코드** (메모리 `report-with-seller-product-code`)
- **D-07 [auto]: 선택 UI 는 Phase 1 입찰가 인상의 선택 UI(보이는 것만 vs 필터 전체)를 재사용한다.** 새 선택 패턴을 만들지 않는다.

### 생성 파라미터 (DETAIL-01~04)

- **D-08 [auto]: 입력 이미지 목록은 웹앱이 D-02 관문으로 만들어 CLI 에 파일로 넘긴다** — `detail_batch.py` 에 `--inputs <json>`(상품별 URL 목록) 주입구를 추가한다.
  · 이 플래그가 있으면 `collect_images`(썸네일+옵션) 를 **타지 않는다.** 플래그 없는 기존 CLI 동작은 불변 (L-04)
  · 입력 파일에 없는 상품은 접수하지 않는다(빈 목록 = 전량 아님 — 저장소 규율)
- **D-09 `[auto — 용팀장 확인 필요]`: 제품 이미지가 10장을 넘으면 원래 순서로 앞 10장을 쓰고, 빠진 장수를 견적 화면에 보인다.**
  · [auto] Q: "10장 초과분(BANNER-03b 가 Phase 5 로 넘김) 처리?" → Selected: **앞 10장 + 누락 장수 표시** (recommended for MVP)
  · 대안이었던 **분할 생성**(한 상품 2회 접수)은 두 번째 결과가 첫 결과를 덮는지 모른다 — 알려면 크레딧 실측이 필요하다 → Deferred
  · **확인이 필요한 이유:** BANNER-03b 는 "내용 누락 > 크레딧 절약"이라고 했다. 앞 10장 자르기는 그 원칙과 부딪친다. 초과 상품 비율을 견적 화면에 띄워 용팀장이 판단할 재료를 준다
- **D-10 [auto]: 장수 = `max(2, min(입력 제품이미지 수, 10))`, `imageUrls` 와 `sectionCount` 는 항상 동시에, 접수 응답 `예상장수` 불일치 시 전량 중단(exit 2).** — 전부 현행 CLI 에 이미 있다. 플랜은 **깨지지 않았음을 테스트로 고정**만 한다
  · 입력 < 2장 상품은 D-02 단계에서 이미 걸러진다(BANNER-05 하한 2)
- **D-11 [auto]: 화질은 일반(standard, 장당 5크레딧) 고정.** 화면에 화질·장수 선택지를 두지 않는다

### 기작업 스킵 (SC-3 — 두 번째 회차 재접수 0건)

- **D-12 [auto]: 스킵 판정은 `webapp/state.py::기작업여부` 와 같은 규칙 — `구매_가공완료` 태그 OR `aiImageGenerated` — 을 CLI 가 접수 직전 **실시간 workdata** 로 한다. 목표 장수와 무관한 절대 조건이다.**
  · 현행 CLI 의 `prev["pages"] >= sc` 비교를 **절대 조건으로 바꾼다**(AI 흔적 있음 → 스킵). Phase 3 D-10 / STATE-05 가 이미 요구한 것
  · 태그 목록은 설정 `done_tags` 를 인자로 넘긴다 — CLI 가 웹앱 설정을 import 하지 않는다
  · 규칙이 두 곳(state.py · CLI)에 산다 → **같은 표본으로 둘이 같은 답을 내는 교차 테스트**를 둔다
- **D-13 [auto]: 첫 5건 실탄 뒤 `aiImageGenerated` 가 실제로 찍히는지 workdata 재조회로 실측한다** (STATE Blockers 의 "확정 실험은 Phase 5").
  · 찍히면: D-12 로 SC-3 끝. 추가 작업 없음
  · 안 찍히면: CLI 가 완료 건에 불사자 태그(완료 표식)를 쓰는 폴백을 붙인다 — **태그 쓰기는 L-01 ④ 체크포인트** (용팀장이 손으로 쓰는 태그 체계를 건드리기 때문)
  · 어느 쪽이든 **같은 상품 목록으로 두 번째 견적을 돌려 접수 0건을 확인**하는 것이 SC-3 의 증거다(크레딧 0 — 견적만)

### 견적 → 승인 → 접수 (DETAIL-05)

- **D-14 `[auto — 용팀장 확인 필요]`: 견적은 크레딧 0 의 미리보기 잡이다 — CLI 에 `--estimate-only` 를 추가해 workdata 조회 + 스킵 판정 + 장수 계산만 하고 접수하지 않는다.**
  · 견적 화면: 선택 N건 → 기작업 스킵 M건 → **실제 접수 K건 · 총 장수 · 예상 크레딧(장수×5)** · 10장 초과로 잘린 상품 수(D-9) · 현재 계정 · 크레딧 잔액(참고용)
  · 잔액은 **참고 표시만** — 잔액 차이로 비용을 역산하지 않는다(메모리 `credit-balance-not-per-session`). 비용 정본은 CLI 집계
  · 접수 버튼은 **견적 잡의 targets 파일만 가리킨다** — 대상을 새로 받지 않는다(Phase 1 01-08 D-11 선례)
  · 접수 시점에 스킵이 늘면 그만큼 줄여 접수하고 끝 리포트에서 **실제 접수분 기준으로 다시 보고**. 견적보다 **늘어나는 방향**(건수·장수·크레딧)이면 접수하지 않고 멈춘다
  · **확인이 필요한 이유:** "견적 화면에서 버튼 누름 = 승인"으로 볼지, 금액 상한(예: N크레딧 초과 시 추가 확인)을 둘지. 추천은 **상한 없음 · 버튼이 승인**(1인 도구, 5건 ≈ 최대 250크레딧). 대량(예: 50건↑) 상한은 용팀장 기준을 받는다
- **D-15 [auto]: 접수 잡은 전역 쓰기 가드(`WRITE_KINDS`)에 넣는다.** 크레딧 쓰기가 동시에 둘 돌지 않는다. `caffeinate -i` 프리픽스를 붙인다(`_수면방지_프리픽스` 대상에 추가)

### 폴링 · 브라우저 생존 · 복구 (DETAIL-06/07 · SC-1/5)

- **D-16 [auto]: 접수 잡 하나가 접수→폴링을 이어서 한다(CLI 기본 동작). 복구는 별도 잡 `--poll-only` 로 한다.**
  · [auto] Q: "접수와 폴링을 잡 둘로 나눌까?" → Selected: **한 잡이 둘 다 + 복구용 `이어서 확인` 잡** (recommended — CLI 체크포인트가 이미 분리를 보장)
  · 브라우저 생존은 Phase 1 의 `start_new_session` subprocess + 로그 오프셋 tail SSE 로 이미 된다 — 새 메커니즘 없음
- **D-17 [auto]: 폴링이 시간 상한에 닿으면 `폴링 미완 N건` 으로 끝나고 실패로 보고하지 않는다.** 전용 종료코드(실패와 구분)를 두고 화면은 **`이어서 확인`(=`--poll-only`) 버튼만** 보인다. 타임아웃 건에 재접수 버튼은 **그리지 않는다**
- **D-18 [auto]: 서버가 실패로 확정한 건만 `실패`다.** 실패분 재접수 버튼은 MVP 에 넣지 않는다(Deferred) — 필요하면 CLI `--retry-failed` 를 L-01 ③ 체크포인트로 수동 실행
- **D-19 [auto]: 결과 화면 = 항목 단위 표**(판매자상품코드 · 접수/완료/실패/스킵/폴링중 · 장수 · 크레딧 · 사유). 완료분은 불사자가 자동 반영하므로 별도 적용 버튼 없음. 생성 이미지 미리보기는 Claude's Discretion

### Claude's Discretion

- 상세 잡 run-dir 위치·파일 이름(예: `<회차>/web/detail_<job>/` 에 `products.json` · `inputs.json` · `detail_status.json`)
- 견적·결과 표 레이아웃(기존 `_preview_table.html`·`_result_table.html` 재사용 정도)
- 생성 이미지 썸네일을 결과 표에 띄울지
- 폴링 종료코드 번호, `--estimate-only` 산출물 JSON 모양
- 견적 잡과 접수 잡 사이 유효시간(견적이 너무 오래되면 다시 견적) 둘지 여부

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 범위·요구사항
- `.planning/ROADMAP.md` §Phase 5 — Goal · Success Criteria 1~5 · Depends on(D-23 질문)
- `.planning/REQUIREMENTS.md` §버튼 3 DETAIL-01~07 · §BANNER-03b(10장 상한 이관) · BANNER-04/05
- `.planning/PROJECT.md` — 안전 제약(dry-run 선행 · 견적 보고) · 진실의 원천 · Key Decisions
- `.planning/STATE.md` §Blockers — `aiImageGenerated` 미기록 · 태그 기반 중복방지 · Phase 4→5 이월

### Phase 4 에서 넘어온 것 (배너)
- `.planning/phases/04-banner-detection/04-CONTEXT.md` D-21(워터마크는 제품) · D-22(비전 2차) · **D-23(불통과 종료 · Phase 5 로 넘기는 사실 3개)** · Deferred
- `.planning/phases/04-banner-detection/04-GATE.md` §17(재판정 숫자) · **§17-8**
- `.planning/phases/04-banner-detection/04-12-SUMMARY.md` — 이월 목록 · Acceptance 대조(확인함 재클릭 결함)

### Phase 3 에서 넘어온 것 (조인·상태·중복방지)
- `.planning/phases/03-join-detail-state/03-CONTEXT.md` D-05~D-10(코드 체계 · 기작업 스킵 절대조건) · D-19(웹앱 MCP 금지)
- `.planning/phases/03-join-detail-state/03-07-SUMMARY.md` — 보드 상품 연결 51 (🔴31 🟡20 ⚪0)

### 감쌀 CLI
- `.claude/skills/bulsaja-detail-page/SKILL.md` — 절대규칙 1~5 · 기작업 스킵 · 계정 라우팅(용쌤/부킹 단일)
- `.claude/skills/bulsaja-detail-page/scripts/detail_batch.py` — `submit_one` · `existing_ai_detail` · `collect_images` · `--poll-only` · `###DETAIL###` 센티널

### 관련 대기 todo (접지 않음 — 위험으로만 인지)
- `.planning/todos/pending/job-reap-depends-on-polling.md` — 아무도 안 보면 잡이 `running` 에 갇힘. **브라우저를 닫은 채 접수 잡이 끝나면 전역 쓰기 가드가 유령 잡에 걸릴 수 있다** → SC-1 검증 때 이 증상을 확인할 것
- `.planning/todos/pending/429-group-stage-silent-completion.md` — 인덱스 잡과 스캔 잡을 동시에 띄우지 말 것

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `webapp/state.py::기작업여부` / `상세상태` — 스킵 규칙의 웹앱 쪽 정본. CLI 쪽 D-12 구현과 교차 테스트 대상
- `webapp/banner.py::제품이미지목록` — Phase 5 입력의 유일한 관문. **게이트통과=True 요구를 D-02 로 교체**해야 한다. `게이트집계` 는 그대로 둔다(보고용)
- `webapp/banner_store.py::라벨읽기 · 확인읽기 · 확인기록` — 라벨 우선 판정과 확인시각 조건의 재료
- `webapp/jobs.py` — `create_job` · `WRITE_KINDS` · `_수면방지_프리픽스` · `_write_targets` · `_reap` · 로그 경로
- `webapp/argv.py` — `BulsajaArgv` 패턴. 상세 잡용 argv 모델(`DetailArgv`)을 같은 모양으로 추가
- `webapp/logtail.py` + `_job_panel.html` · `_job_status.html` — SSE 전량 재생(탭 닫았다 이어보기)
- `_preview_table.html` · `_result_table.html` — 견적·결과 표 재사용 후보
- `webapp/templates/banner_review.html` — D-03 결함 수정 위치

### Established Patterns
- 미리보기 잡 → 실행 잡은 **부모 targets 파일만 참조**(Phase 1 01-08). 실행 라우트가 대상을 새로 받지 않는다
- 빈 목록·빈 설정이 "전량"으로 해석되는 경로는 예외로 터뜨린다(`jobs.py` 규율 · `banner.py` 4번째 적용)
- CLI 에 기능을 넣을 땐 **주입구 플래그만** 추가, 플래그 없는 동작은 바이트 단위로 불변(01-02 `--only-ads` 선례)
- 장시간 CLI 출력은 `flush=True` · 마지막 줄 센티널(`###DETAIL###`)
- `webapp/**` 에 `requests`·`eroomlib` import 0건 — `test_argv.py` 트리 가드가 집행
- 브라우저 JS 회귀는 `board_cdp.sh`(헤드리스 크롬+CDP) 계층

### Integration Points
- 보드(`board.html`) 선택 → `상세 견적` 버튼 → 견적 잡(`detail_estimate`) → 견적 표 → `접수` 버튼 → 접수 잡(`detail_submit`, WRITE_KINDS) → 잡 패널 SSE → 결과 표 → (타임아웃 시) `이어서 확인` 잡(`detail_poll`)
- 입력 파일: 웹앱이 배너 산출물 + 라벨 + 확인으로 `inputs.json` 작성 → CLI `--inputs`
- 계정 가드: ENG-08 기존 `bulsaja_profile` 경로

</code_context>

<specifics>
## Specific Ideas

- 첫 실탄 = **회차 2026-09-20 의 🔴 5건**(사람 검수 완료 회차). 최대 5 × 10장 × 5 = **250크레딧**. L-01 체크포인트에서 견적을 보여 주고 승인받는다
- 첫 5건 뒤 곧바로 같은 목록으로 **두 번째 견적**을 돌려 접수 0건 확인(SC-3, 크레딧 0) + `aiImageGenerated` 실측(D-13)
- 용팀장 성향: 진도 우선("너무 진도가 늦다") · 사람 큐 최소화 · 추천이면 진행 — 단 **크레딧 접수는 예외 없이 견적→승인**
- 워터마크: D-21 이 "Phase 5 이미지 가공 단계의 책임"이라 적었지만, AI 상세 생성이 이미지를 새로 만든다. 결과물에 점포 워터마크가 남는지는 **첫 5건 결과에서 눈으로 본다** → 남으면 별도 페이즈/quick 으로

</specifics>

<deferred>
## Deferred Ideas

- **10장 초과 상품 분할 생성** — 두 번째 접수가 첫 결과를 덮는지 크레딧 실측 필요 (D-09 대안)
- **실패분 재접수 버튼** — MVP 는 CLI `--retry-failed` 수동 (D-18)
- **워터마크 제거 가공** — D-21 이 Phase 5 몫이라 적었으나 SC 1~5 에 불필요. 첫 결과에 남으면 그때
- **사람 라벨 기준 스킵 재계산** (`dnb2lYw0` 류) (D-04)
- **대량 접수 금액 상한** — 용팀장 기준 받으면 추가 (D-14)
- (Phase 4 D-23 이월 그대로) out-of-sample 재측정(Q2) · 비전 지시문 v4 · 검수 화면 `게이트: 열렸다` 문구
- 생성 이미지 품질 검수 화면 · 고화질 선택 · 장수 수동 조정

### Reviewed Todos (not folded)
- `429-group-stage-silent-completion.md` (score 0.6 — auto 규칙상 접을 대상) → **접지 않았다.** 2026-09-21 용팀장 결정 *"그냥 두고 기록만 · 첫 구축을 다시 돌릴 일이 생기면 그때"* 가 auto 규칙보다 우선. 이 페이즈는 인덱스를 다시 구축하지 않는다
- `job-reap-depends-on-polling.md` (score 0.2) → 접지 않음. 단 SC-1(브라우저 닫고 완주) 검증 때 전역 가드 유령 잡 증상을 확인하도록 canonical refs 에 올림
- `index-is-not-the-bottleneck.md` (score 0.2) → 무관

</deferred>

---

*Phase: 05-core-value*
*Context gathered: 2026-09-25 (--auto, single pass)*
