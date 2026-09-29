# Phase 7: 남은 버튼 — 썸네일 교체 / 쿠팡 복사 - Context

**Gathered:** 2026-09-29 (`--auto` — 용팀장 부재, 추천안 자동 선택. `[auto — 용팀장 확인 필요]` 표시 항목은 돌아오면 확인)
**Status:** Ready for planning

<domain>
## Phase Boundary

보드에 버튼 2종을 더 붙여 관제탑을 닫는다. 두 트랙은 서로 독립이라 **병렬로 플랜·실행 가능**하다.

- **썸네일 트랙 (THUMB-01~03):** 규칙②(노출 100+ & CTR<1%) 대상을 보드에서 상품 단위로 보고 → 크레딧 0 견적 → 승인 → 기존 `bulsaja-thumbnail` 스킬이 그대로 돈다.
- **쿠팡 트랙 (CP-01~04):** 버튼 하나로 `prep→resolve→build→ship→gate→apply(미리보기)` 를 돌리고, **`apply --commit` 만 따로** 건수 타이핑으로 확인받는다. 기존 게이트(주문 3회+ · 쿠팡보정 가중마진 20%)와 쿠팡 그룹 실물 대조를 그대로 쓴다.

범위 밖: 쿠팡 실제 등록(업로드 — 용팀장이 건건 직접), 쿠팡 원장 시트 기록(`sheet`), 레시피 모드 썸네일, Phase 2 안전 계약 전체 구현.

</domain>

<decisions>
## Implementation Decisions

### 🔒 잠긴 제약 (auto 아님 — 프로젝트·메모리·Phase 5/6 에서 승계, 플랜이 바꿀 수 없다)

- **L-01: 크레딧을 쓰는 동작과 되돌릴 수 없는 동작은 전부 플랜의 blocking human checkpoint 다.** 구체적으로 ① 첫 실제 썸네일 생성(`apply --generate`) ② 쿠팡 `apply --commit` 전부(첫 회만이 아니라 **매번** — PROJECT.md "3단계에서도 끝까지 사람이 누르는 것"). 체크포인트 앞에 **견적(건수 · 크레딧 · 계정 · 대상 판매자상품코드)** 을 보여 준다. `autonomous: false` 이고 `--auto` 체인·`workflow.auto_advance` 도 자동 승인하지 않는다.
- **L-02: 기존 CLI 재작성 금지.** `run_thumbs.py` · `run_coupang.py` 는 subprocess 로 부르고, 필요한 건 **주입구 플래그 추가만**(ENG-01 · Phase 5 L-04). 무플래그 동작은 불변. 웹앱은 불사자 MCP 를 직접 부르지 않는다(Phase 3 D-19). 마진 공식·규칙 판정을 웹앱에 재구현하지 않는다 — 판정값은 CLI 산출물에서만 읽는다(CLAUDE.md §What NOT to Use).
- **L-03: 썸네일 폴링 타임아웃·poll 단계 429 는 실패가 아니다.** 재생성으로 풀지 않는다 — `recover`(크레딧 0) 먼저. taskId 가 있으면 회수 대상(메모리 `thumb-poll-timeout-is-normal` · SKILL §결과 미수신 회수). 화면에 타임아웃 건 재생성 버튼을 그리지 않는다(Phase 5 D-17 과 같은 규율).
- **L-04: 쿠팡 중복 방어는 `gate` 의 쿠팡 그룹 실물 대조가 정본이다.** `copied.jsonl` 은 run-dir 안에서만 유효하다. 웹앱은 `--skip-group-check` 를 **절대 붙이지 않는다**(테스트로 강제). 1차 파일럿 87건이 들어 있는 그룹이라 이게 뚫리면 곧바로 재복사 사고다(메모리 `coupang-pilot-round1`).
- **L-05: 계정 가드(ENG-08) 그대로** — 기대 계정(부킹/용쌤) 아니면 견적·미리보기·실행 모두 거부(exit 4).
- **L-06: 광고↔불사자 조인 키는 광고그룹명의 마켓번호 NN-N** (메모리 `ad-group-number-is-join-key`). 썸네일 대상의 상품 식별은 Phase 3 조인 산출물(`webapp/join.py`)만 쓴다. 화면 표기는 **판매자상품코드**.
- **L-07: 진실의 원천은 불사자 서버·현황판.** "썸네일 했음/쿠팡 복사했음" 로컬 대장을 새로 만들지 않는다. 잡 산출물은 그 회차 기록일 뿐.

### Phase 2 미완(이월)에 대한 처리 — 쿠팡 트랙의 의존성

- **D-01 [auto]: Phase 2 를 선행시키지 않는다. 쿠팡·썸네일 버튼은 Phase 5/6 에서 이미 굳은 잡·가드 패턴을 재사용해 "버튼 로컬 안전장치"만 갖춘다.**
  · [auto] Q: "Phase 2(안전 계약)가 이월됐는데 쿠팡 트랙을 어떻게 여나 — ⓐ Phase 2 먼저 ⓑ Phase 5/6 패턴 재사용 + `apply --commit` 영구 사람 체크포인트" → Selected: **ⓑ** (recommended)
  · 재사용하는 것: 미리보기 잡 → 실행 잡은 **미리보기 잡 id 하나만** 받는다(대상을 새로 받지 않는다 — 01-08 D-11 · 05-04 · 06 L-02) · 쓰기 잡은 `WRITE_KINDS` 전역 1개 · `caffeinate -i` · 상한 인자 필수(빈 값 = 전량 금지) · 항목 단위 결과 표 · 마지막 줄 센티널 + `flush=True`
  · Phase 2 요구(ENG-04/05 · SAFE-04~07 · FLOW-03/06/07)는 **이 페이즈에서 완료로 표시하지 않는다.** 아래 D-12(재조회)·D-13(상한)은 그 요구의 버튼 로컬 등가물일 뿐이다. 감사 로그 JSONL(FLOW-07)은 Phase 2 몫으로 남긴다

### 썸네일 트랙 — 대상 (THUMB-01)

- **D-02 [auto]: 규칙② 대상은 보드의 기존 규칙 필터(`②`)에서 고른다. 선택 UI 는 Phase 1/5 의 선택 UI(보이는 것만 vs 필터 전체)를 재사용한다.** 새 화면을 만들지 않는다.
  · 조인이 안 된 행(추출실패·불사자 미발견)은 회색 + 사유로 보이고 선택 불가
  · 한 회 견적 상한 = 설정 `thumb_max_items`(기본 20 — 스킬 "노출 많은 순 상위 20건" 관례). 초과 선택은 노출 많은 순 앞 20 + 나머지 표시
- **D-03 `[auto — 용팀장 확인 필요]`: 이미 AI 가공된 썸네일(스킬의 기작업 판별 = `cdn.bulsaja.com` 등)인 규칙② 상품은 이 버튼 대상에서 빠진다 — 스킬의 prep 판정을 그대로 따른다.**
  · [auto] Q: "CTR 이 낮다는 건 지금 썸네일이 안 먹힌다는 뜻인데, 이미 가공된 썸네일도 다시 만들까?" → Selected: **안 만든다 — 견적 표에 `이미 가공됨(prep 판정)` 스킵 사유로 보이고 끝** (recommended — L-02, 스킬 기작업 규칙 재구현·우회 금지)
  · **확인이 필요한 이유:** 규칙② 상품은 광고 중 = 대부분 이미 한 번 썸네일 작업을 거쳤을 수 있다. 그러면 이 버튼의 실대상이 **거의 0건**이 될 수 있다. 가공본을 다시 만들려면 현황판 `재작업` flag 를 찍는 경로(또는 레시피 모드)가 필요한데 그건 Deferred. 견적 화면에 "선택 N → 이미 가공 M → 실제 생성 K" 를 크게 보여 판단 재료를 준다
- **D-04 [auto]: 스킬 `prep` 은 `--group-name` 단위다 → 선택 상품을 조인 산출물의 불사자 그룹명으로 묶어 그룹별 run-dir 에 `prep --group-name <그룹> --ids <productId…>` 를 돌린다.** 견적 잡 하나가 그룹들을 차례로 돈다(묶는 방법·run-dir 배치는 Claude's Discretion).

### 썸네일 트랙 — 견적 → 승인 → 실행 (THUMB-02/03)

- **D-05 [auto]: 견적은 크레딧 0 잡이다 — `prep`(스냅샷 · 기작업 판별 · 선기록) 까지만 돌고, 결과를 `대상 K건 · 예상 크레딧 K×5 · 재생성 포함 최대치 · 이미 가공 스킵 M건 · 계정 · 잔액(참고)` 표로 보인다.**
  · 예상 크레딧 공식은 스킬 `thumb_rules.credit_estimate`(장당 5) 를 CLI 산출물로 받는다 — 웹앱이 곱셈을 재구현하지 않는다(L-02). 필요하면 `prep` 에 `--estimate-out <json>` 주입구
  · 재생성 상한(상품당 누적 2회)을 반영한 **최대치**를 같이 보인다. 정확한 상한 산식은 연구에서 `run_thumbs.py` 로 확인
  · 잔액은 참고 표시만 — 잔액 차이로 비용 역산 금지(메모리 `credit-balance-not-per-session`)
  · `prep` 이 현황판에 쓰는 기작업 `완료` 백필은 스킬 표준 동작이라 견적 단계에 허용한다(크레딧·마켓 쓰기 아님)
- **D-06 `[auto — 용팀장 확인 필요]`: 크레딧을 쓰는 구간(run 기준선택 → prescreen → `apply --generate` → verdict → `apply --commit`)은 웹앱이 직접 돌리지 않고 Claude 세션에 인계한다. 웹 `실행 승인` 버튼은 승인 기록(run-dir · 대상 ids · 승인 크레딧 상한)을 남기고, 붙여 넣을 한 줄 명령을 보여 준다. 결과는 웹이 run-dir 을 읽어 보인다.**
  · [auto] Q: "스킬의 run(기준 이미지 선택)·prescreen·verdict(3축 판정)는 Claude 비전 판단이다. 웹앱에서 어떻게 돌리나 — ⓐ 크레딧 0 까지 웹, 이후 Claude 세션 인계 ⓑ 웹앱이 `claude -p` 헤드리스를 subprocess 로 띄움" → Selected: **ⓐ** (recommended for MVP)
  · 이유: 웹앱엔 LLM 이 없다. ⓑ 는 무인 에이전트가 크레딧을 쓰는 경로가 되고, 헤드리스에서 Workflow 팬아웃(`thumb-fanout`)·권한 모드가 도는지 미검증이다. 스킬은 "검수 판정 주체 = Claude · 절대 자동 통과 금지"라 판정 단계를 결정론 코드로 대체할 수도 없다(L-02)
  · 인계 산출물: `<run-dir>/web_approval.json` = `{승인시각, 계정, 그룹, ids, 견적크레딧, 승인상한크레딧}` + 화면의 복사용 명령(예: `썸네일 작업 이어서 <run-dir>`)
  · 결과 표: run-dir 의 `decisions.json`·생성 결과·사용 크레딧·`review.html` 경로(판매자상품코드 · 생성/사용가능/제외/보류/회수대기 · 크레딧 · 사유). `taskId` 남은 건은 `회수 대기` 로 보이고 버튼은 `recover`(크레딧 0) 만
  · **확인이 필요한 이유:** SC-1 "썸네일 교체를 실행한다"를 **웹 버튼 한 번으로 끝까지**로 읽으면 ⓐ 는 모자란다(마지막에 Claude 세션 한 번 필요). 버튼 완결을 원하면 ⓑ 를 별도 스파이크로 검증해야 한다 → Deferred
- **D-07 [auto]: `run_thumbs.py apply --generate` 에 `--max-credits N` 주입구를 추가한다. 예상 크레딧(재생성 포함)이 N 을 넘으면 생성 0건으로 exit 5.** 인계받은 Claude 세션이 `web_approval.json` 의 승인 상한을 이 플래그로 넘긴다 — 웹 승인과 실제 지출을 코드로 묶는 유일한 고리. 무플래그 동작은 불변(기존 잔액 가드 `_guard_credits` 그대로)
- **D-08 `[auto — 용팀장 확인 필요]`: 썸네일 교체는 불사자 대표이미지만 바꾼다(스킬 §불사자 저장 ≠ 마켓 반영). 규칙② 상품은 광고 중 = 이미 스마트스토어에 올라가 있으므로, 반영은 Phase 6 `market_preview/market_commit` 경로를 재사용한다 — 썸네일 run-dir 의 `apply --commit` 성공분을 market 미리보기의 부모 출처로 받는다.**
  · [auto] Q: "스토어 반영 — ⓐ Phase 6 마켓 버튼 재사용(부모 출처 추가) ⓑ 이 페이즈에선 불사자 저장까지만" → Selected: **ⓐ** (recommended — 안 올리면 CTR 이 안 바뀌어 규칙② 버튼의 존재 이유가 없다)
  · Phase 6 의 L-01(모든 실제 market_update 는 사람 체크포인트)·백업·게이트는 그대로. 새 쓰기 경로를 만들지 않고 부모 출처만 하나 늘린다
  · **확인이 필요한 이유:** Phase 6 D-01 이 대상을 "상세 잡 완료분"으로 못박았다. 출처를 넓히는 건 마켓 쓰기 범위 확장이다. 그리고 `market_update` 는 불사자 쪽 변경(가격·상품명 등)을 통째로 다시 민다(06 D-10 ③) — Phase 6 게이트가 먼저 `정상` 판정돼 있어야 한다. Phase 6 이 끝나지 않았으면 이 연결(D-08)만 Phase 6 완료 뒤로 미룬다

### 쿠팡 트랙 — 원클릭 전공정 (CP-01/02)

- **D-09 [auto]: 버튼 `쿠팡 후보 뽑기 — 쓰기 0` = 미리보기 잡 1개가 `prep→resolve→build→ship→gate→apply(무 --commit)` 를 한 run-dir 에서 차례로 돈다.** 어느 단계든 비0 종료면 거기서 멈추고 그 단계 이름·stderr 꼬리를 보인다. 전 구간 읽기 전용(SKILL §재개·안전 "S6 이전은 전부 읽기 전용"). kind 는 `BULSAJA_KINDS`(쓰기 아님) + 같은 kind 중복만 막는 `SINGLETON_KINDS`.
  · run-dir = 스킬 관례 `<data_root>/coupang/runs/<타임스탬프>` — 새 회차마다 새 run-dir(재복사 방어는 L-04 가 한다)
  · 단계 체인 구현(작은 체인 러너 스크립트 vs 잡 엔진 다단계)은 Claude's Discretion
- **D-10 [auto]: 미리보기 화면 = 게이트 통과 후보 표(판매자상품코드 · 상품명 · 합산주문수 · 쿠팡보정마진 · 배송비 차액 표시 · 사유) + 탈락 사유별 건수 + `쿠팡그룹에이미있음` 건수.** 기준 문구(`주문 3회 이상 AND 쿠팡보정마진 20%`)는 CLI 출력에서 그대로 읽어 보인다.
  · 배송비 과소책정은 **막지 않고 표시만**(2026-09-13 용팀장 지시 · SKILL). `--strict-shipping` 은 붙이지 않는다
- **D-11 [auto]: `apply --commit` 은 물리적으로 다른 버튼(다른 색·다른 위치·기본 접힘) + 건수 타이핑 확인(FLOW-04 — 되돌릴 수 없는 작업).** 실행 라우트는 미리보기 잡 id 하나만 받고 같은 run-dir 로 돈다. 잡 kind `coupang_commit` ∈ `WRITE_KINDS` + `caffeinate -i`. 복사 뒤 같은 잡이 `verify`(중복 0 증명 · 판매가 검산, 읽기 전용)까지 돌고 결과를 표에 붙인다.
  · PITFALLS §Pitfall 10-3 "이 버튼만 다른 색·다른 위치" 그대로
- **D-12 [auto]: 커밋 잡은 `apply --commit` 직전에 `gate` 를 한 번 더 돌린다(쿠팡 그룹 실물 재조회 — 크레딧 0).** 재조회 후보가 미리보기보다 **줄면** 빠진 건을 사유와 함께 보고하고 나머지만 복사, **늘면** 복사 0건으로 멈춘다(Phase 5 D-14 "늘어나는 방향이면 멈춘다"와 같은 규율). 미리보기와 커밋 사이 그룹이 바뀌어 재복사되는 틈을 닫는 SAFE-05 의 로컬 등가물.
- **D-13 [auto]: 1회 복사 상한 — `apply --commit` 에 `--limit` 을 **항상** 붙인다. 이 웹 경로의 첫 실행은 코드로 10건(PITFALLS §Pitfall 10-4), 첫 실행 결과를 사람이 본 뒤로는 설정 `coupang_copy_max_items`(기본 20 = CLI 복사 배치 1개).** 상한 밖 후보는 미리보기 표에 `상한초과` 로 남는다. 첫 실행 여부는 이 웹앱의 `coupang_commit` 잡 이력 유무로 판단(대장 아님 — 잡 레지스트리).
- **D-14 [auto]: `run_coupang.py` 에 계정 가드 주입구(`--expect-nick`)를 추가한다** — `gate`·`apply` 가 불사자를 부르기 전에 `bulsaja_my_profile` 을 확인하고 불일치면 exit 4(Phase 5/6 종료코드 계약). 쿠팡 그룹 id 는 CLI 설정 `coupang.group_id` 그대로.

### 쿠팡 트랙 — 게이트·중복 (CP-03/04)

- **D-15 [auto]: 게이트 기준(주문 3회+ · 쿠팡보정 가중마진 20%)은 화면에서 못 바꾼다.** 웹앱은 `--min-orders`/`--min-margin` 을 넘기지 않고 CLI 기본값·설정을 그대로 쓴다. 기준을 바꾸는 입력칸을 두지 않는다(CP-03 "그대로 유지").
  · 메모리 `coupang-pilot-round1` 의 "2차엔 컷을 낮춰야 할 수 있다"는 Deferred — 필요하면 CLI 설정에서 바꾼다(웹 경로 밖)
- **D-16 `[auto — 용팀장 확인 필요]`: 쿠팡 후보를 "상세작업 끝난 상품"으로 추가 제한하지 않는다.** 후보 = 스킬 게이트 통과분 그대로.
  · [auto] Q: "PROJECT.md 는 '상세작업 끝난 상품 중 판매 실적 있는 것만'이라고 쓰는데, 상세 완료 필터를 더할까?" → Selected: **안 더한다** (recommended — CP-01~04·ROADMAP SC 에 없는 조건이고, 게이트 통과분 대부분이 판매용 잠금 대표라 상세 상태와 무관하게 이미 팔린 상품이다. 더하면 조인(Phase 3)을 쿠팡 트랙에 끌고 와야 한다)
  · **확인이 필요한 이유:** PROJECT.md Active 요구 문구와 어긋난다. 쿠팡에 중국어 상세가 그대로 올라갈 수 있다(쿠팡 등록은 용팀장이 건건 직접 보니 거기서 걸러진다는 전제)
- **D-17 [auto]: 중복 방지는 기존 `gate` 방식 그대로(L-04). 추가로, 쿠팡 그룹 읽기(`collect_group`)가 429·부분 실패로 **일부만 읽히면 게이트를 실패로 끝낸다(fail-closed)** — 덜 읽힌 그룹 = "이미 있음" 집합이 작아짐 = 재복사.** 현행 동작이 이미 예외로 죽는지 연구에서 확인하고, 아니면 주입구 없이 고칠 수 있는 최소 수정 + 테스트(아래 Folded Todo).

### 공통 — 순서·병렬

- **D-18 [auto]: 크레딧 0·쓰기 0 작업을 전부 먼저 끝내고, 첫 유료/비가역 동작은 각 트랙 마지막 플랜의 체크포인트에서만 한다.** (아래 code_context §비용 0 으로 먼저 끝낼 수 있는 것)
- **D-19 [auto]: 두 트랙은 병렬 가능. 단 공유 파일(`webapp/jobs.py` KINDS/WRITE_KINDS · `webapp/argv.py` · `webapp/templates/board.html` · `webapp/settings.py`) 편집은 한 플랜(Wave 1)에 모으거나 트랙별 플랜이 겹치지 않게 나눈다** — 병렬 실행자가 같은 레지스트리를 동시에 고치면 충돌한다. `JobKind` 와 `KINDS` 는 항상 같이 고친다(jobs.py 주석).

### Claude's Discretion

- 썸네일 견적 잡의 그룹 묶기·run-dir 배치(권장: `<data_root>/thumbnail/runs/web-<잡id>/<그룹>/`) · `web_approval.json` 스키마 · 인계 명령 문구
- 쿠팡 단계 체인 구현 방식(체인 러너 스크립트 vs 잡 엔진 다단계) · 단계별 진행 표시
- `--estimate-out` · `--expect-nick` · `--max-credits` 산출물 JSON 모양·종료코드 번호(Phase 5/6 계약 0/2/3/4/5 를 따를 것)
- 미리보기·결과 표 레이아웃(`_preview_table.html`·`_detail_result_table.html`·`_market_*` 재사용 정도)
- `review.html` 을 웹에서 링크로 열지(run-dir 한정 정적 라우트) 경로만 보일지

### Folded Todos

- **`job-reap-depends-on-polling.md`** (score 0.4) — 쿠팡 커밋·썸네일 견적은 수 분짜리 잡이고 쿠팡 커밋은 `WRITE_KINDS` 전역 가드를 잡는다. 보는 사람 없이 끝난 잡이 좀비로 `running` 에 갇히면 다음 버튼이 전부 409 다. 이 페이즈에서 **`_alive()` 의 좀비 판정(`waitpid(WNOHANG)`/`Popen.poll`)만** 고친다 — 백그라운드 수거 루프는 넣지 않는다(최소 수정).
- **`429-group-stage-silent-completion.md`** (score 0.6) — 원 사례(인덱스 그룹 단계)는 Phase 7 범위 밖이라 그 todo 는 pending 으로 남긴다. **같은 원칙("429 를 완주로 접지 마라")을 쿠팡 `gate` 의 그룹 읽기에 적용**한 것만 접는다 → D-17.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 범위·요구사항
- `.planning/ROADMAP.md` §Phase 7 — Goal · SC 1~4 · 의존(Phase 3 썸네일 / Phase 2 쿠팡 — D-01 로 처리)
- `.planning/REQUIREMENTS.md` §THUMB-01~03 · §CP-01~04 · (참고) §ENG-04/05 · SAFE-04~07 · FLOW-03/06/07 은 Phase 2 몫
- `.planning/PROJECT.md` — 안전 제약 · "3단계에서도 끝까지 사람이 누르는 것: `apply --commit`(쿠팡)" · 쿠팡 복사 Active 문구(D-16)
- `.planning/research/PITFALLS.md` §Pitfall 10(쿠팡 복사 비가역 · 다른 색·다른 위치 · 첫 실행 10건 상한 · 쓰기 후 재조회)
- `.planning/research/SUMMARY.md` · `.planning/research/ARCHITECTURE.md` — subprocess 래핑 · 잡 엔진 원칙

### 이전 페이즈에서 굳은 패턴 (직접 재사용)
- `.planning/phases/05-core-value/05-CONTEXT.md` — L-01~L-06 · D-14(견적=크레딧 0 미리보기 잡, 늘어나는 방향이면 멈춤) · D-15(WRITE_KINDS·caffeinate) · D-17(타임아웃≠실패)
- `.planning/phases/06-market-update/06-CONTEXT.md` — L-01~L-07 · D-01(부모 잡 출처) · D-06(CLI 종료코드 0/2/3/4/5 · 상한 인자 필수) · D-09/D-10(게이트) — D-08 이 이 경로를 재사용
- `.planning/phases/05-core-value/05-04-SUMMARY.md` — 부모 잡 id 하나만 받는 실행 라우트 · exit 3=done 처리

### 감쌀 스킬·CLI
- `.claude/skills/bulsaja-thumbnail/SKILL.md` — 흐름 ①~⑤ · 기작업 판별 · 결과 미수신 회수(recover) · 되돌리기(restore) · 불사자 저장 ≠ 마켓 반영
- `.claude/skills/bulsaja-thumbnail/scripts/run_thumbs.py` — `cmd_prep`(292) · `_guard_credits`(1299) · `apply` 서브파서 · `recover`/`restore`
- `.claude/skills/bulsaja-thumbnail/scripts/thumb_rules.py` — `CREDITS_PER_IMAGE=5` · `credit_estimate`
- `.claude/skills/bulsaja-thumbnail/references/사고-이력.md` — 규칙 근거(코드 손댈 때만)
- `.claude/skills/coupang-candidates/SKILL.md` — 단계표 S0~S7 · 시험 복사 확정 사실 · 마진 공식 · 하지 않는 것
- `.claude/skills/coupang-candidates/scripts/run_coupang.py` — `cmd_gate`(334, 그룹 실물 대조) · `cmd_apply`(441, `--commit`/`--limit`/`--batch`) · `cmd_verify`(521)
- `.claude/skills/coupang-candidates/scripts/coupang_rules.py` — 마진 공식·게이트(웹앱 재구현 금지)
- `.claude/skills/coupang-candidates/references/파이프라인-단계.md`
- `.claude/skills/naver-ads-weekly/SKILL.md` §규칙표 ② · `.claude/skills/naver-ads-weekly/scripts/ads_rules.py`(`CTR_LOW=1.0`, `IMP_MIN`)
- `.claude/skills/_shared/불사자-안전규칙.md` · `.claude/skills/_shared/스킬-계약.md`

### 웹앱 접점
- `webapp/jobs.py` — `KINDS`·`WRITE_KINDS`·`BULSAJA_KINDS`·`SINGLETON_KINDS`·`POLL_INCOMPLETE_OK_KINDS`·`_alive`/`_reap`(Folded Todo)·`CAFFEINATE`
- `webapp/argv.py` · `webapp/routes/jobs.py` · `webapp/board.py`(규칙 dedupe) · `webapp/join.py`(NN-N 조인 · productId)
- `webapp/templates/board.html` · `_preview_table.html` · `_detail_estimate_table.html` · `_detail_result_table.html` · `_market_preview_table.html` · `_job_panel.html` · `_job_status.html`

### 메모리 (사실 근거)
- `thumb-poll-timeout-is-normal` · `coupang-pilot-round1` · `ad-group-number-is-join-key` · `credit-balance-not-per-session` · `report-with-seller-product-code` · `delete-blocked-by-product-lock`(쿠팡 복사본은 잠금 승계 → 지우려면 잠금부터)

### 접은 todo
- `.planning/todos/pending/job-reap-depends-on-polling.md` · `.planning/todos/pending/429-group-stage-silent-completion.md`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- 보드 규칙 필터(②) · 상품 단위 dedupe(`board.py` — ②·③ 동시 소속 소재 중복 계상 방지) · 선택 UI(Phase 1/5)
- 조인 산출물(`join.py`) — 광고행 → productId · 판매자상품코드 · 불사자 그룹
- 잡 엔진: `create_job`(HTTP 무관 함수 — ENG-07) · 로그 tail SSE · 부모 잡 체인 · `children_of`
- 견적/미리보기/결과 표 템플릿 5종 · Phase 6 마켓 미리보기/커밋/게이트(D-08 재사용)
- 가짜 MCP 오프라인 하네스(`webapp/tests/test_detail_cli.py` — sys.modules 스텁) → 두 CLI 주입구 테스트에 재사용
- 스킬 자체 테스트: `bulsaja-thumbnail/scripts/test_*.py` · `coupang-candidates/scripts/test_coupang_rules.py`

### Established Patterns
- 미리보기 잡 → 실행 잡은 미리보기 잡 id 만 참조 · 빈 목록/빈 상한 = 예외(전량 금지)
- CLI 주입구 플래그만 추가 · 무플래그 동작 불변(골든 테스트)
- 종료코드 0 전부 종결 · 2 입력 오류 · 3 대기 미완(실패 아님) · 4 계정 불일치 · 5 상한 초과
- `webapp/**` 에 `requests`·`eroomlib` import 0건(트리 가드) — 쿠팡 CLI 는 eroomlib 을 쓰지만 subprocess 경계 너머라 무관
- 실탄 도는 동안 웹앱 코드 수정 금지(`--reload` 가 `_PROCS` 를 비움 — 05-06 Pitfall 4)
- 쿠팡 `prep` 은 주문시트를 gws/eroomlib 로 읽는다 → gws 인증 7일 만료·403 이면 첫 단계에서 죽는다. 화면에 원인(재로그인·token_cache)을 그대로 보인다(메모리 `gws-oauth-testing-mode-expiry` · `gws-stale-token-cache`)

### Integration Points
- 썸네일: 보드 `②` 필터 → 선택 → `thumb_estimate`(prep, 크레딧 0) → 견적 표 → `실행 승인` → `web_approval.json` + 인계 명령 → (Claude 세션: run→prescreen→generate `--max-credits`→verdict→commit) → 결과 표(run-dir 읽기) → [D-08] Phase 6 `market_preview` 부모 출처
- 쿠팡: 보드 상단 별도 패널 `쿠팡 후보 뽑기 — 쓰기 0` → `coupang_preview`(6단계 체인) → 후보 표 → (접힌 영역·다른 색) `쿠팡 복사 실행` + 건수 타이핑 → `coupang_commit`(gate 재조회 → apply --commit --limit → verify) → 결과 표

### 비용 0 으로 먼저 끝낼 수 있는 것 (첫 유료/비가역 동작 전)
**썸네일 트랙**
1. `run_thumbs.py` 주입구(`--estimate-out` 필요 시 · `--max-credits`) + 무플래그 불변 테스트 — 오프라인
2. 웹앱 kind(`thumb_estimate`)·라우트·견적/결과 표·`web_approval.json` — TestClient + uat-verifier(격리 포트·DB)
3. **실제 `prep` 스모크 1회(크레딧 0 · 현황판 백필만)** → 견적 표 실데이터 확인
4. 결과 표는 기존 썸네일 run-dir(과거 회차) 산출물로 읽기 검증
→ 그 뒤에야 **첫 실제 `apply --generate`**(L-01 ① 체크포인트, 견적·상한 제시)

**쿠팡 트랙**
1. `run_coupang.py --expect-nick` 주입구 · gate 그룹 읽기 fail-closed(D-17) · 무플래그 불변 — 오프라인
2. 체인 러너 + 웹앱 kind(`coupang_preview`/`coupang_commit`)·라우트·후보/결과 표·건수 타이핑·첫 실행 10건 강제 — TestClient + uat-verifier
3. `--skip-group-check`·`--strict-shipping`·게이트 기준 인자가 argv 에 절대 안 들어가는 테스트
4. **실제 미리보기 잡 1회(prep→…→gate→apply 무커밋 · 쓰기 0)** — 1차 파일럿 87건이 `쿠팡그룹에이미있음` 으로 걸러지는지 실측(CP-04 의 살아 있는 증거)
→ 그 뒤에야 **첫 실제 `apply --commit`**(L-01 ② 체크포인트, 10건 상한)

**공통:** Folded Todo `_alive` 좀비 판정 수정 — 오프라인

</code_context>

<specifics>
## Specific Ideas

- 쿠팡 커밋 버튼은 입찰가 인상·상세 접수 버튼과 **같은 습관으로 눌리면 안 된다** — 색·위치·접힘·건수 타이핑 4중(PITFALLS §Pitfall 10-3, UI 표 505행)
- 1차 파일럿 그룹(`1번_용쌤쿠팡cy1728`, 87건)이 미리보기에서 전부 `쿠팡그룹에이미있음` 으로 빠지는 것 = CP-04 SC-4 의 실측 증거로 쓴다
- 쿠팡 복사본은 잠금이 승계된다 — 잘못 복사하면 지우기 전에 잠금부터 풀어야 한다. 결과 표에 이 한 줄 안내

</specifics>

<deferred>
## Deferred Ideas

- **웹 버튼 완결형 썸네일 실행**(웹앱이 `claude -p` 헤드리스로 스킬 전 구간 구동) — 헤드리스 Workflow 팬아웃·권한·무인 크레딧 지출 검증 스파이크 필요 (D-06 대안 ⓑ)
- **이미 가공된 규칙② 썸네일 재작업**(현황판 `재작업` flag 또는 레시피 모드) — D-03
- **쿠팡 게이트 컷 완화**(`--min-orders 2` / `--min-margin 18`) — 메모리 `coupang-pilot-round1`. CLI 설정에서만
- **쿠팡 원장 시트 기록(`sheet`)·모델명 검사(`models`) 웹 버튼** — 지금은 Claude 세션/CLI 로
- **쿠팡 실제 등록 확인·사고 감시**(반품·품절취소) — 스킬 "하지 않는 것"
- **감사 로그 JSONL · 실패분 재시도 · 서버 재시작 고아 잡 정리 · 작업 잠금** — Phase 2(ENG-04/05 · FLOW-06/07)
- **썸네일 실패분 재생성 버튼** — 스킬 재생성 2회 규칙은 Claude 세션에서

### Reviewed Todos (not folded)
- `index-is-not-the-bottleneck.md` (score 0.2) — 인덱스 성능, Phase 7 과 무관
- `429-group-stage-silent-completion.md` 의 **원 사례(인덱스 그룹 단계)** 는 pending 유지 — 원칙만 D-17 로 접음

</deferred>

---

*Phase: 07-thumb-coupang*
*Context gathered: 2026-09-29*
