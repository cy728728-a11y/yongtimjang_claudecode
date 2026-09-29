# Phase 7: 남은 버튼 — 썸네일 교체 / 쿠팡 복사 - Research

**Researched:** 2026-09-29
**Domain:** 기존 CLI 2종(`run_thumbs.py` · `run_coupang.py`) 을 웹 잡으로 감싸기 — 주입구 플래그 · 체인 러너 · 잡 레지스트리 확장
**Confidence:** HIGH (전부 로컬 코드 실측. 네트워크·MCP·크레딧 호출 0회)

<user_constraints>
## User Constraints (from CONTEXT.md)

> 아래는 `07-CONTEXT.md` 의 `<decisions>` · `<deferred>` 원문 그대로다(스크립트로 발췌 — 한 글자도 바꾸지 않았다).

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

### Deferred Ideas (OUT OF SCOPE)

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
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| THUMB-01 | 규칙②(노출 100+ & CTR<1%) 대상을 판정해 보여준다 | 보드 행 `rules` 에 ② 가 이미 있다(`board.py` RULE_ORDER · `board.js` f-rule 필터). 조인 행 → `productId` + `번호`(NN-N) → 조인문서 `마켓그룹` 으로 불사자 그룹명(§썸네일 대상 매핑) |
| THUMB-02 | 기존 `bulsaja-thumbnail` 스킬로 실행한다 | 웹은 `prep` 까지만(크레딧 0), 나머지는 D-06 인계. `apply --generate --max-credits` 주입구(§D-07) · `web_approval.json` · SKILL.md 인계 절 |
| THUMB-03 | 접수 전 예상 크레딧을 보고한다 | `prep` 은 기작업/정합검사/404/조회실패 건수를 **파일로 안 남긴다**(stdout 만) → `--estimate-out` 주입구 필수. 최대치 공식 = K×5×MAX_REGEN = **K×10** (§크레딧 산식) |
| CP-01 | 버튼 하나로 prep→resolve→build→ship→gate→apply 전공정 | 체인 러너 스크립트 1개(스킬 디렉터리) → 단계별 subprocess · 비0 즉시 정지 · 센티널 줄 |
| CP-02 | `apply --commit` 만 따로 확인 | `coupang_commit` kind ∈ WRITE_KINDS · 미리보기 잡 id 하나만 받음 · gate 재조회 비교(§D-12) · `--limit` 항상(첫 회 10) |
| CP-03 | 게이트(주문 3+ · 쿠팡보정마진 20%) 그대로 | ⚠️ **현재 `workspace.toml [coupang] min_margin = 15.0`** — 웹이 `--min-margin` 을 안 넘기면(D-15) 15%로 돈다. §Open Q1 |
| CP-04 | 중복 방지 = gate 의 쿠팡 그룹 실물 대조 | 대조는 있음. 단 **스냅샷 조회 오류를 버리는 fail-open 구멍**이 있다(`snaps, _ = snapshot.ensure(...)`) → §D-17 최소 수정 |
</phase_requirements>

## Summary

두 CLI 모두 웹앱이 필요로 하는 표면이 **거의** 있다. 빠진 것은 전부 "무플래그 불변" 주입구로 막을 수 있는 크기다. 핵심 발견 다섯 가지:

1. **썸네일 `prep` 은 견적에 필요한 숫자를 파일로 남기지 않는다.** 기작업 백필(M)·정합검사 대상·404 삭제대상·조회실패는 stdout 에만 찍힌다(`audit_targets.json`·`deletion_candidates.json` 만 예외). 그리고 **`--ids` 로 부르면 현황판 `pending` 필터를 우회한다** — `완료(원본대체)`·`보류(...)` 인 상품도 URL 판정만으로 다시 생성 대상이 된다(크레딧 낭비 경로). → `prep --estimate-out <json> --only-pending` 두 주입구가 필요하다.
2. **재생성 포함 최대치는 K×10 이지 K×15 가 아니다.** `재생성횟수` 는 첫 생성에서 1이 되고 `can_regenerate(attempts < MAX_REGEN=2)` 라 상품당 생성은 최대 2회다.
3. **쿠팡 gate 의 fail-open 구멍은 429 자체가 아니라 스냅샷 오류 무시다.** `collect_group` 의 페이지 조회는 429 재시도 초과 시 예외로 죽는다(fail-closed OK). 그러나 그 뒤 `snapshot.ensure` 가 상품별 예외를 `errors` 로 삼키고 gate 가 `snaps, _` 로 버린다 → 그 상품의 타오바오번호가 `already` 집합에서 빠진다 → **재복사**. 추가로 빈 페이지 조기 종료(`총상품수` 미대조)도 조용히 덜 읽힌다.
4. **CP-03 의 20% 가 설정에 없다.** SKILL 은 `gate --min-margin 20` 을 손으로 붙여 1차 파일럿을 돌렸고, `workspace.toml` 은 15.0 이다. D-15(웹은 기준 인자를 안 넘긴다)를 지키면 웹 경로는 15%로 돈다.
5. **D-08(썸네일 → Phase 6 마켓 반영)은 이 페이즈에서 못 닫는다.** Phase 6 은 06-05·06-06 SUMMARY 가 없어 미완료이고, `market_update.py` 는 `--detail-backup-dir`(상세 원본 백업 ⓐ)를 필수로 요구하는데 썸네일 경로엔 그런 백업이 없다(있는 건 `before_generate.json` = 대표이미지 순서). D-08 자체 조건("Phase 6 이 끝나지 않았으면 미룬다")을 발동시켜라.

**Primary recommendation:** Wave 1 = 공유 파일(jobs/argv/settings/board.html·board.js) 한 플랜 + CLI 주입구 두 플랜(썸네일·쿠팡, 각자 스킬 디렉터리 테스트) → Wave 2 = 트랙별 라우트·표 → Wave 3 = 트랙별 실데이터 크레딧 0 스모크 → 마지막 = 트랙별 blocking 체크포인트(첫 `apply --generate` 인계 / 첫 `apply --commit` 10건). D-08 은 Phase 6 완료 뒤 별도 플랜으로 미룬다.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| 규칙② 대상 표시·선택 | Browser (board.js 필터) | API (보드 행 재구성·키 검증) | 기존 보드·선택 UI 재사용. 서버가 키로 행을 다시 만든다(클라이언트가 대상을 못 지어냄) |
| 썸네일 대상 → 그룹·productId 매핑 | API (`routes/jobs.py`, `join.attach`) | — | 조인 산출물만 쓴다(L-06) |
| 썸네일 견적(prep) | CLI 자식(`run_thumbs.py prep`) via 러너 | 현황판 시트(백필 쓰기) | 판정 재구현 금지(L-02) |
| 크레딧 지출(run→generate→verdict→commit) | Claude 세션(인계) | CLI `--max-credits` | 웹앱엔 LLM 없음(D-06) |
| 쿠팡 6단계 체인 | CLI 자식(체인 러너 → `run_coupang.py`) | — | 단계별 비0 정지·센티널 |
| 재조회 비교(D-12) | 체인 러너(commit 모드) | API(승인 목록 파일 작성) | 비교 로직이 웹앱이 아니라 CLI 경계 너머에 있어야 로그·종료코드로 남는다 |
| 계정 가드 | CLI `--expect-nick`(exit 4) | API 사전점검(BULSAJA_KINDS, 프로필 파일) | 이중 방어(T-05-12 관례) |
| 잡 레지스트리·가드 | API (`webapp/jobs.py`, SQLite) | — | 기존 엔진 |

## Standard Stack

새 라이브러리 **0개.** 전부 기존 스택이다 [VERIFIED: 로컬 코드].

| 구성 | 위치 | 용도 |
|------|------|------|
| FastAPI/Jinja2/htmx 2.x (기존) | `.venv-web` | 라우트·표 조각 |
| stdlib `sqlite3` (기존) | `webapp/jobs.py` | 잡 이력 — 첫 실행 판정(D-13) |
| `.venv/bin/python3` (`argv.PY_CLI`) | 자식 | 두 CLI + 새 러너 2개 (eroomlib·requests·PIL 이 `.venv` 에만 있다 — 실측: `.venv-web` 엔 requests·PIL 없음) |
| pytest 9.1.1 | 두 venv 모두 | 웹앱 스위트(.venv-web) / 스킬 스위트(.venv) |

**Installation:** 없음.

## Package Legitimacy Audit

이 페이즈는 외부 패키지를 설치하지 않는다 — slopcheck 대상 없음.

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## CLI 표면 실측 (연구 질문 1)

### `run_thumbs.py` [VERIFIED: `.claude/skills/bulsaja-thumbnail/scripts/run_thumbs.py`]

| 서브커맨드 | 핵심 인자 | 산출물(run-dir) | 종료 | 크레딧 / 쓰기 |
|---|---|---|---|---|
| `prep` | `--run-dir`(필수) `--group-name`\|`--sheet` `--ids ...` `--limit` `--batch-size` `--max-candidates` `--max-px` | `batches_index.json`(0건이면 `{"대상":0,"이유":…}` / 전건선기록이면 `{"배치":0,"확정선기록":n}` / 보통은 배열), `batches/batch_NNN.json`, `results/result_000.json`(대표옵션 확정 선기록), `audit_targets.json`, `deletion_candidates.json`, `thumbs/` | **항상 0** (`return` 만, 조회실패로 대상 0이면 산출물 없이 0) · `_resolve_sheet` 실패는 RuntimeError(=1) | 크레딧 0 · **현황판 쓰기**: 기작업 `완료` 백필 + 원본404 `보류(원본404·삭제대상)` · 이미지 다운로드 |
| `apply` (무플래그) | `--run-dir` `--group-name`/`--sheet` `--ids` | 없음(stdout 미리보기) | 0 | 0 · 단 **보류건 현황판 기록은 미리보기에서도 한다** |
| `apply --generate` | 위 + `--allow-missing` `--no-sheet` `--no-matrix` `--sleep` | `generated.json`(건별, taskId 선기록), `before_generate.json`, `review.html` | 3 = 누락 차단 · **4 = 잔액 부족**(`_guard_credits`) · 0 | **크레딧 소모** |
| `apply --commit` | 위 | 요약 파일 **없음**(시트 로그 + 현황판만) · `###COMMIT### 반영 N건 / 보류·실패 M건` | 0 | 불사자 대표이미지 저장 |
| `recover` | `--run-dir` `--ids` | `generated.json` 갱신, `review.html` | 2 = generated.json 없음 · 0 | 크레딧 0 · **불사자 쓰기 있음**(자동반영 방어 `_restore_if_changed`) |
| `prescreen`/`verdict`/`audit`/`pending` | — | Claude 비전 팬아웃 입력 | 2/3 | 크레딧 0, Claude 판단 필요 → 웹 범위 밖 |

**기작업 판별 경로(prep) 3갈래** [VERIFIED: run_thumbs.py:319-338]: 재작업 flag 있으면 무조건 대상 / `가공됨 + 대표옵션 있음` → `audit_targets.json`(자동 완료 금지, 생성 대상 아님) / `가공됨 + 대표옵션 없음` → 현황판 `완료` 백필 / 나머지 → 생성 대상.

→ 견적 표는 **4갈래**를 보여야 한다: 생성 대상 K · 이미 가공(백필) M · 정합검사 대상 A(생성 안 함 — audit 은 Claude 몫) · 원본404 삭제대상 D · 조회실패 E. D-03 의 "선택 N → 이미 가공 M → 실제 생성 K" 에 A·D·E 를 더해야 숫자가 맞는다.

### 크레딧 산식 [VERIFIED: thumb_rules.py:29-32, 376-395 · run_thumbs.py:1568-1579]

- `CREDITS_PER_IMAGE = 5`, `credit_estimate(n) = n*5`
- 첫 생성 성공 시 `재생성횟수 = 0+1 = 1`; `--ids` 재생성 시 `can_regenerate(attempts) = attempts < MAX_REGEN(2)` → **상품당 생성 최대 2회**
- recover 회수분도 `재생성횟수 +1` (상한 우회 방지)
- **예상 = K×5, 재생성 포함 최대 = K×5×MAX_REGEN = K×10.** 러너는 `R.credit_estimate`·`R.MAX_REGEN` 을 import 해 계산한다(웹앱은 곱하지 않는다 — L-02)

### `run_coupang.py` [VERIFIED: `.claude/skills/coupang-candidates/scripts/run_coupang.py`]

공통 인자: `--run-dir`(필수) `--sleep 0.3`. `.claude/lib` 은 `_bootstrap()` 이 스스로 찾는다(PYTHONPATH 불필요). 설정은 `eroomlib.config.cfg` → `workspace.toml [coupang]`(`group_id=1003308`, `group_name="1번_용쌤쿠팡cy1728"`, `min_margin=15.0`, `min_orders=3`).

| 단계 | 인자 | 읽음 | 씀 | MCP | 종료 |
|---|---|---|---|---|---|
| `prep` | `--sheet-id` | 주문시트(gws) | `sales.json`, `ranked.json` | 없음 | 0 (gws 실패 = 예외 1) |
| `resolve` | `--min-orders 3`(argparse 기본) | sales | `resolved.json`, `unresolved.json` | find_by_code | 2 = sales 없음 |
| `build` | — | resolved, sales | `groups.json`, `reps.json`, `build_dropped.json` | 없음 | 2 |
| `ship` | `--tolerance 10` | reps | `ship_diff.json`, `ship_fix_ids.json`, `ship_overpriced.json` | workdata(대표 수만큼, 0.3s 간격 → 수 분) | 2 |
| `gate` | `--min-margin`(None→cfg 15.0) `--min-orders`(None→cfg 3) **`--limit 100`**(기본) `--skip-group-check` | reps, sales, ship_diff | **`candidates.json`, `rejected.json`**(덮어씀) | collect_group + snapshot.ensure | 2 |
| `apply` | `--commit` `--batch 20` `--strict-shipping` `--limit 0` | candidates, `copied.jsonl` | `before_copy.json`, `copied.jsonl`(건건 fsync) | collect_group, market_group_copy | 2 = 후보 없음 · 3 = strict-shipping 중단 |
| `verify` | `--only dup\|all`(기본 all) | copied.jsonl | `verified.json` | group_products + snapshot | 2 · **dup 모드에서만 중복이면 4** · all 모드는 중복이어도 **0** |

**gate 의 행 스키마** (candidates/rejected 공통, 1차 파일럿 실파일 확인): `대표pid 판매자상품코드 불사자코드 상품명 그룹명 잠금 사본수 사본pid 합산주문수 합산매출 판매가 가중마진 최소마진 적자건수 유효행수 카테고리 쿠팡수수료율 쿠팡보정마진 배송비P75 배송비편차 배송비과소 배송비방향 배송비차액 타오바오상품번호 사유`. 사유 값: `통과(x%)` · `주문수부족(...)` · `마진미상…` · `마진미달(...)` · `기업로드(쿠팡)` · `쿠팡그룹에이미있음` · `상한초과(상위 N건 밖)`. 기준 문구는 stdout `[gate] 기준: 주문 {min_orders}회 이상 AND 쿠팡보정마진 {min_margin}% 이상` 한 줄뿐이다 → 러너가 요약 JSON 에 `기준` 필드로 옮겨 적어야 화면이 "CLI 출력에서 그대로" 읽는다(D-10).

**1차 파일럿 실측** [VERIFIED: `~/python_work/data/coupang/runs/20260913-1215`, 읽기만]: candidates 84 · copied.jsonl 85행(타오바오번호 결측 0 · 신pid 결측 0) · verified.json `중복0: true, 그룹상품수: 87` (`--only dup` 으로 돌렸다 — `판매가` 키 없음).

## Architecture Patterns

### System Architecture Diagram

```
[썸네일 트랙]
 보드(② 필터) ─선택 키─▶ POST /jobs/thumb/estimate
      │  서버: 회차 판정 → fold_products → join.attach → 키 검증(없으면 400)
      │        행 → productId · 판매자상품코드 · 번호 → 조인문서 마켓그룹 → 그룹명
      │        미해소/pid없음 → 제외(사유)  · 노출순 상위 thumb_max_items 초과분 → 제외(상한초과)
      ▼
 create_job("thumb_estimate", inputs={그룹명: [pid…]})  ─BULSAJA 사전점검(409)─
      ▼ (자식, caffeinate)
 thumb_web.py estimate ──for 그룹──▶ run_thumbs.py prep --group-name G --ids … --only-pending
      │                                  --expect-nick N --estimate-out <G>/estimate.json --run-dir <G>
      │   그룹 하나 실패해도 나머지 계속 · 그룹별 결과 합산 → summary.json (K·M·A·D·E·예상·최대·계정)
      ▼
 견적 표 ─[실행 승인]─▶ POST /jobs/thumb/approve (견적 잡 id 하나)
      │  web_approval.json(그룹별 run-dir) 기록 + 복사용 한 줄 명령 표시 · 쓰기 0 · 잡 아님
      ▼
 (Claude 세션 — 사람 체크포인트) run → prescreen → apply --generate --max-credits C → verdict → apply --commit
      ▼
 결과 표 ◀─ run-dir 읽기(generated.json · decisions.json · commit_summary.json · review.html 경로)
      └─ taskId 남은 건 = 회수 대기 → recover 명령만(재생성 버튼 없음, L-03)

[쿠팡 트랙]
 보드 상단 패널 [쿠팡 후보 뽑기 — 쓰기 0] ─▶ POST /jobs/coupang/preview
      ▼ create_job("coupang_preview")  run-dir = <data_root>/coupang/runs/web-<잡id>
 coupang_web.py preview --run-dir R --expect-nick N --summary-out S
      │  prep → resolve → build → ship → gate → apply(무 --commit)   (비0 = 그 단계에서 정지)
      │  센티널 `###STAGE### <이름> exit <n>` · summary: 기준문구·통과표·탈락사유별 건수·이미있음 건수
      ▼
 후보 표 ─(접힌 영역·다른 색·건수 타이핑)─▶ POST /jobs/coupang/commit (미리보기 잡 id + 타이핑 건수)
      │  서버: 부모=coupang_preview 성공 · 첫 성공 커밋 이력 없으면 limit=10 아니면 coupang_copy_max_items
      │        승인목록 = 미리보기 통과 상위 limit 건 → approved.json · 타이핑 != len(승인목록) → 400
      ▼ create_job("coupang_commit", WRITE_KINDS, caffeinate)
 coupang_web.py commit --run-dir R --approved A --limit L --expect-nick N --summary-out S2
      │  gate 재실행(그룹 실물 재조회) → 새 통과집합 vs 미리보기 통과집합
      │     새 ⊄ 옛(늘어남) → 복사 0, exit 5    줄어듦 → 빠진 건 사유 보고, 나머지만
      │  apply --commit --limit L --pids-file <승인∩새>  → verify(all) → verified.json
      ▼
 결과 표 ◀─ copied.jsonl · verified.json(중복0 · 판매가) · 잠금 승계 안내 1줄
```

### Recommended Project Structure

```
.claude/skills/bulsaja-thumbnail/scripts/
├── run_thumbs.py            # +주입구: prep --estimate-out/--only-pending/--expect-nick, apply --max-credits, apply --commit --summary-out
├── thumb_web.py             # 새 러너: 그룹별 prep 순회 + 합산 요약 (크레딧 0)
└── test_thumb_web.py        # 주입구·러너 오프라인 테스트 (.venv)
.claude/skills/coupang-candidates/scripts/
├── run_coupang.py           # +주입구: --expect-nick(공통), apply --pids-file · gate fail-closed(D-17)
├── coupang_web.py           # 새 러너: preview 체인 / commit(재조회 비교→apply→verify)
└── test_coupang_web.py      # (.venv)
webapp/
├── jobs.py                  # KINDS·JobKind·WRITE/BULSAJA/SINGLETON·caffeinate·_build_argv·_alive 좀비
├── argv.py                  # ThumbArgv · CoupangArgv (조립 한 곳)
├── settings.py              # thumb_max_items 20 · coupang_copy_max_items 20 · coupang_first_max 10
├── paths.py                 # thumb_runs_root() · coupang_runs_root() (data_root 기준)
├── routes/jobs.py           # (트랙별 플랜) 라우트
└── templates/_thumb_*.html · _coupang_*.html
```

### Pattern 1: 러너 스크립트로 다단계를 한 잡에 담기 (D-04 · D-09 재량 → 러너 권장)

**What:** 잡 엔진은 argv 하나를 띄운다(`spawn`). 다단계를 잡 엔진에 넣으면 부모 체인·상태·로그가 단계 수만큼 늘어난다. 대신 스킬 디렉터리에 얇은 러너를 두고, 러너가 기존 CLI 를 **subprocess** 로 차례로 부른다(CLI 를 import 하지 않는다 — 무플래그 동작·전역 상태 보존).
**Why here:** 자식의 stdout 은 러너의 stdout(=잡 로그 파일 fd)을 그대로 물려받는다 → SSE tail 이 그대로 산다. 비교 로직(D-12)이 로그와 종료코드로 남는다.

```python
# coupang_web.py 골격 — 실측 계약에 맞춘 제안 (한국어 주석 · try-except)
STAGES = ["prep", "resolve", "build", "ship", "gate", "apply"]

def _단계(stage, run_dir, extra, expect_nick):
    """run_coupang.py <stage> 를 자식으로 부른다. stdout 은 물려받는다(로그 tail 유지)."""
    av = [sys.executable, RUN_COUPANG, stage, "--run-dir", run_dir, *extra]
    if stage != "prep" and stage != "build":        # MCP 를 여는 단계만
        av += ["--expect-nick", expect_nick]
    print(f"###STAGE### {stage} 시작", flush=True)
    try:
        code = subprocess.call(av, cwd=REPO_ROOT)
    except OSError as e:
        print(f"###STAGE### {stage} 실행불가 {e}", flush=True)
        return 2
    print(f"###STAGE### {stage} exit {code}", flush=True)
    return code
```
※ `--skip-group-check` · `--min-margin` · `--min-orders` · `--strict-shipping` 문자열이 이 파일과 `webapp/**` 에 **0회** 나와야 한다(트리 grep 테스트 — L-04 · D-15 · D-10).

### Pattern 2: 부모 잡 id 하나만 받는 실행 라우트 (05-04 · 06 재사용)

실행 라우트 요청 본문 = `{job_id, 타이핑건수}` 뿐. run-dir·대상은 부모 잡 행과 부모의 summary 산출물에서 **서버가** 푼다(`_상세폴더`/`_마켓폴더` 관용구). 쿠팡 run-dir 은 `paths.coupang_runs_root() / f"web-{미리보기잡id}"` 로 **부모 id 에서 유도**한다 — 요청에서 경로를 받지 않는다. 같은 미리보기로 두 번째 커밋은 `children_of(부모, "coupang_commit")` 에 성공분이 있으면 400(05-04 Deviation 1 과 같은 규율; `copied.jsonl` 이 같은 run-dir 재복사는 막지만 한 번 더 누르는 습관 자체를 막는다).

### Pattern 3: 주입구 = 무플래그 불변 + 골든

`detail_batch.py` 의 `--expect-nick` / `--max-credits` / `--estimate-out` 과 같은 모양. `_계정확인`(detail_batch.py:323) 관용구: `bulsaja_my_profile` 1회 → `닉네임` 비교, 조회 실패 + 기대닉 있음 = 불통과. 불일치면 **다른 도구를 부르기 전에** exit 4.

### Anti-Patterns to Avoid
- **웹앱이 `run_thumbs`/`run_coupang` 을 import** — `.venv-web` 에 requests·PIL 이 없어 ImportError. 테스트도 스킬 쪽은 `.venv` 로 돈다.
- **gate 재실행 후 `candidates.json` 을 웹앱이 손으로 고쳐 쓰기** — CLI 산출물 오염. 필터는 `apply --pids-file` 주입구로.
- **verify 종료코드로 중복 판정** — `--only all`(기본)은 중복이어도 0 이다. `verified.json["중복0"]` 을 읽어라.
- **쿠팡 run-dir 를 광고 회차(`jobs.run_dir`) 칸에 넣기** — `paths.run_dir_path` 화이트리스트는 광고 runs 전용이다. 쿠팡 잡의 `run_dir` 칸은 비우고 폴더는 잡 id 에서 유도.

## 연구 질문별 결론

### D-07 `--max-credits N` 최소 주입점 [VERIFIED: run_thumbs.py:1376-1392, 1492-1510]
`cmd_apply` 의 `if args.generate:` 블록, `_guard_credits(items)` **직전**. 계산은 `_generate` 와 같은 계획으로:
```python
if getattr(args, "max_credits", None) is not None:
    prev = _load(gen_path) if os.path.exists(gen_path) else {}
    todo, _ = R.generate_plan(items, prev, getattr(args, "ids", None))
    # 누적: 이 run-dir 에서 이미 나간 것(생성 성공 횟수 + 결과 미확인 taskId) + 이번 계획
    spent = sum(int(v.get("재생성횟수") or 0) for v in prev.values()) * R.CREDITS_PER_IMAGE
    spent += sum(1 for v in prev.values() if v.get("taskId") and "생성본" not in v) * R.CREDITS_PER_IMAGE
    need = R.credit_estimate(len(todo))
    if spent + need > args.max_credits:
        print(f"\n승인 상한 초과 — 누적 {spent:,} + 이번 {need:,} > 승인 {args.max_credits:,}. 생성 0건.", file=sys.stderr)
        sys.exit(5)
```
**누적으로 봐야 하는 이유:** 재생성은 `apply --generate --ids …` 를 **다시 부르는** 경로다. 호출마다 따로 보면 승인 K×10 을 넘어도 매번 통과한다. 승인 상한 기본값 = 견적의 최대치(K×10). 무플래그는 `max_credits=None` → 기존 경로 그대로. 서브파서 `a.add_argument("--max-credits", type=int, default=None)`. ⚠️ 이 CLI 에서 **exit 4 는 이미 "잔액 부족"** 이다(무플래그 동작이라 못 바꾼다) → 5 를 쓰는 게 맞다.

### D-14 `--expect-nick` 최소 주입점 (쿠팡) [VERIFIED: run_coupang.py:97-135, 800-855]
MCP 를 여는 자리는 전부 `CoupangMCP().open()` 이다(resolve·ship·gate·apply·verify). 가장 작은 주입: `CoupangMCP.open()` 을 오버라이드 — `super().open()` 뒤 모듈 전역 `_EXPECT_NICK` 이 있으면 `bulsaja_my_profile` 1회, 불일치/조회실패면 `close()` 후 `sys.exit(4)`. `common()` 에 `--expect-nick default=""` 추가, `main()` 이 전역에 넣는다. prep·build 는 MCP 를 안 열어 자동 무관. 무플래그 = 빈 문자열 = 검사 안 함(불변). 한 곳 수정으로 5단계를 덮는다.
**썸네일도 필요하다(L-05 — 견적도 거부):** `run_thumbs.py prep --expect-nick` — `snapshot.ensure` 가 연결을 **스스로** 열기 때문에 훅 자리가 없다. `cmd_prep` 맨 앞(시트 읽기 전)에서 `snapshot.ProductMCP()` 를 한 번 열어 프로필만 보고 닫는다. 불일치 exit 4(prep 경로엔 잔액 가드가 없어 4 가 모호하지 않다).

### D-17 `collect_group` fail-closed 여부 [VERIFIED: eroomlib/bulsaja.py:147-189 · snapshot.py:213-238, 380-429 · run_coupang.py:349-362]
| 실패 모양 | 현재 | 판정 |
|---|---|---|
| 페이지 조회 429/5xx | `_post` 가 4회 지수백오프 후 `RuntimeError` → gate 죽음(exit 1) | ✅ fail-closed |
| 페이지가 중간에 빈 `항목` 으로 옴 | `if not items: break` — 조용히 종료, `총상품수` 대조 없음 | ❌ fail-open |
| 그룹 상품 스냅샷(workdata) 429·오류 | `snapshot.ensure` 가 건별 예외를 `errors` 에 담고, gate 가 `snaps, _` 로 **버림** → 타오바오번호 결측 → `already` 에서 빠짐 | ❌ **fail-open — 재복사 직행** |
| 스냅샷은 있는데 `타오바오상품번호` 빈칸 | `already.discard("")` 로 조용히 빠짐 | ⚠️ 원본이 쿠팡 그룹에 있어도 못 거른다 |

**최소 수정(전부 `run_coupang.py` 안, eroomlib 은 안 건드린다 — 다른 스킬 공용):**
1. `CoupangMCP.collect_group_strict(gid)`: `collect_group` 과 같은 순회 + 첫 페이지 `총상품수` 기억 → 끝에 `len(out) < 총상품수` 면 `RuntimeError`. gate 만 이걸 쓴다.
2. gate: `snaps, errs = snapshot.ensure(...)`; `errs` 가 있으면 `[gate] 쿠팡 그룹 스냅샷 {n}건 실패 — 부분 대조 금지` 출력 후 **candidates.json 을 쓰지 않고** 비0 종료(권장 exit 3 = "미완, 다시 돌리면 된다" — 체인은 비0 이면 멈춘다).
3. 타오바오번호 빈 그룹 상품: 스냅샷 `불사자코드` 로 2차 키 집합을 만들어 `row["불사자코드"] in already_codes` 도 `쿠팡그룹에이미있음` 처리(복사본이 불사자코드를 승계함은 코드 주석 2026-09-13 실증). 결측 건수는 stdout·요약에 찍는다.
테스트: 가짜 MCP 로 ① 스냅샷 오류 1건 → candidates.json 미생성·비0 ② 빈 페이지 조기종료 → 비0 ③ 정상 → 기존과 byte 동일(골든). `--skip-group-check` 경로는 불변.

### D-12 재조회 후 축소된 id 집합을 apply 에 넣는 법 [VERIFIED: run_coupang.py:441-516]
기존 플래그로는 불가 — `apply` 는 `candidates.json` 전체에서 `copied.jsonl` 만 빼고 `--limit` 상위를 집는다. **주입구 `apply --pids-file <json 배열>`**: 있으면 `todo = [c for c in todo if c["대표pid"] in set(pids)]`, 파일에 있는데 후보에 없는 pid 는 `[apply] 승인됐지만 재조회 후보에 없음: …` 으로 찍는다. 무플래그 불변.
비교 규칙(러너 commit 모드): `옛 = 미리보기 summary 의 통과 대표pid 집합`, 재gate 후 `새 = candidates.json 대표pid 집합`.
- `새 - 옛` 비어있지 않음 → **늘어남 → 복사 0, exit 5**(Phase 5 "승인보다 커지면 5" 와 같은 뜻). 가장 흔한 원인이 그룹 읽기 축소(= `쿠팡그룹에이미있음` 감소)라 바로 그 재복사 신호다.
- 승인목록 ∩ 새 → `--pids-file`. 빠진 승인 건은 rejected.json 의 새 사유와 함께 요약에.
- ⚠️ gate 기본 `--limit 100` 경계: 미리보기 통과가 100건을 넘으면, 재조회에서 하나가 빠질 때 101번째가 올라와 "늘어남"으로 오탐 정지한다. 안전 쪽 오탐이라 허용하되 사유 문구를 구분해 찍어라(`상한 경계 진입`). 지금 규모(84)에선 안 난다.

### D-13 `--limit` 의미 · 첫 실행 [VERIFIED: run_coupang.py:448-453 · jobs.py DDL]
`apply --limit N` = `copied.jsonl` 에 없는 후보 중 **정렬 상위 N**(합산주문수·보정마진 내림차순, gate 가 이미 정렬). `0` = 전부 → 웹은 **절대 0 을 안 보낸다**(argv 모델에서 `limit >= 1` 검증). 첫 실행 판정: `SELECT 1 FROM jobs WHERE kind='coupang_commit' AND status='done' AND exit_code=0 LIMIT 1` 없으면 10. 이 조회는 `jobs.py` 에 함수로(DB 는 jobs.py 한 곳 규율 — 05-04 `children_of` 선례).

### D-04 선택 행 → 그룹명·productId [VERIFIED: webapp/join.py:92-116, 296-310 · routes/jobs.py:1516-1620 · run_thumbs.py:257-269]
`join.attach` 행: `해소` · `productId` · `번호`(NN-N). 그룹명 = `join.group_index(조인문서["마켓그룹"])[번호]["그룹명"]`. `prep --group-name` 은 마스터 인덱스(`matrix.index_groups`)에서 **정확일치 우선, 없으면 부분일치 1건** — 불사자 그룹명 전체를 넘겨라(NN-N 만 넘기면 `1-1` 이 `11-1` 도 잡아 "특정 못함"). 인덱스 이름과 불사자 그룹명이 다르면 `RuntimeError` → 러너가 그 그룹만 `그룹시트 미특정` 사유로 제외하고 계속.
**`--ids` 가 현황판 pending 을 우회한다** [VERIFIED: run_thumbs.py:299-303]: `args.ids` 가 있으면 `matrix.pending` 을 안 탄다 → `완료`(원본대체 fallback 포함)·`보류(...)`·`해당없음` 상품도 URL 판정만으로 생성 대상이 된다. 주입구 `--only-pending`: ids ∩ `matrix.pending(m, TASK)` 로 좁히고 빠진 건을 `{pid: 현황판값}` 으로 estimate-out 에 싣는다. 무플래그 불변.

### D-06 인계 (web_approval.json · 한 줄 명령)
- 위치: 그룹별 run-dir `<data_root>/thumbnail/runs/web-<견적잡id>/<그룹명 정규화>/web_approval.json`
- 스키마(제안): `{"승인시각", "견적잡id", "계정", "그룹명", "시트id"(prep 이 쓴 값 — estimate-out 에 싣기), "ids": [...K], "예상크레딧": K*5, "승인상한크레딧": K*10}`
- 명령(화면 복사용): `썸네일 작업 이어서 <run-dir>` — `bulsaja-thumbnail` 스킬이 키워드로 뜬다. **SKILL.md 에 "웹 승인 인계" 절을 한 단락 추가**해야 세션이 `web_approval.json` 을 읽고 `apply --generate --max-credits <승인상한>` 을 붙인다(스킬 문서 수정은 CLI 재작성이 아니다). 계정 확인·`THUMB_POLL_TIMEOUT` 접수모드 규칙은 스킬 기존 절 그대로.
- 결과 읽기: `generated.json`(생성본/taskId/오류/크레딧/재생성횟수) · `decisions.json` · `review.html` 경로 · **`apply --commit --summary-out <json>` 주입구**(권장, `{완료:[pid], 보류:{pid:사유}}`) — 없으면 반영 여부가 시트·현황판에만 있어 웹이 "완료" 를 증명 못 한다. 판매자상품코드는 견적 inputs 의 pid→코드 맵으로 붙인다.
- 승인 버튼은 **잡이 아니다**(파일 쓰기만, 크레딧 0) — 그래도 L-01 에 따라 **실제 첫 `apply --generate` 는 플랜의 blocking checkpoint** 에서 사람이 인계 명령을 실행한다.

### D-08 → 이 페이즈에서 미룬다 [VERIFIED: 06-05/06-06 SUMMARY 없음 · jobs.py `_마켓부모` · argv.MarketArgv]
`market_preview` 부모 집합은 `{detail_submit, detail_poll}` 이고 `MarketArgv` 는 preview/commit 에 `detail_backup_dir`(ⓐ) 가 없으면 ValueError. 썸네일엔 ⓐ 에 해당하는 상세 원본 백업이 없다. "부모 출처 하나 추가"로 안 끝나고 ⓐ 의미를 재정의해야 한다 + Phase 6 미완. → Phase 7 플랜에서 제외, 결과 표에 "스토어 반영 미연결(Phase 6 완료 후)" 한 줄. `--summary-out` 산출물이 나중 연결의 입력이 된다.

### 공유 파일 편집 목록 (D-19 — Wave 1 한 플랜에 모은다) [VERIFIED: webapp/jobs.py:62-160, 738-760 · argv.py]
| 파일 | 추가 |
|---|---|
| `jobs.py` | `JobKind`+`KINDS`: `thumb_estimate`, `coupang_preview`, `coupang_commit` · `WRITE_KINDS += coupang_commit` · `BULSAJA_KINDS += 셋 다` · `SINGLETON_KINDS += thumb_estimate, coupang_preview` · `_수면방지_프리픽스` += 셋 다(수 분짜리) · `_build_argv` 분기 3개(빈 inputs/approved/limit None 이면 ValueError) · `create_job` kwargs(`thumb_inputs`, `coupang_approved`, `copy_limit`) · 쿠팡 폴더 유도 헬퍼 · `first_coupang_commit_done()` · `_alive` 좀비 판정 |
| `argv.py` | `THUMB_WEB`, `COUPANG_WEB` 경로 상수 · `ThumbArgv` · `CoupangArgv`(mode preview/commit, commit 은 approved·limit≥1 필수, 기준 인자 필드 **없음**) |
| `settings.py` | `thumb_max_items: 20` · `coupang_copy_max_items: 20` · `coupang_first_max_items: 10` |
| `paths.py` | `thumb_runs_root()` = data_root/thumbnail/runs · `coupang_runs_root()` = data_root/coupang/runs |
| `templates/board.html` + `static/board.js` | 썸네일 견적 버튼(선택 바) · 쿠팡 패널(상단, 접힌 커밋 영역) — **board.js 도 공유 파일이다**(CONTEXT 목록에 빠짐) |
`POLL_INCOMPLETE_OK_KINDS` 에는 **넣지 않는다**(두 러너 모두 3 = 폴링 미완이 아니다).

### Folded Todo — `_alive` 좀비 [VERIFIED: jobs.py:406-416, 438-474]
`os.kill(pid,0)` 은 좀비에도 성공한다. **`os.waitpid(WNOHANG)` 을 쓰지 마라** — `_PROCS` 에 Popen 이 있는 pid 를 남이 먼저 거두면 `Popen.poll()` 이 ECHILD 를 받고 CPython 은 `returncode = 0` 으로 적는다 [ASSUMED: CPython subprocess `_internal_poll` ECHILD 처리] → **실패한 쓰기 잡이 done/0 으로 기록**된다. 권장: `_alive` 에서 kill(0) 성공 뒤 `ps -o stat= -p <pid>` 첫 글자 `Z` 면 False(읽기 전용, 남의 상태를 안 뺏음; argv 리스트 subprocess). 참고: `create_job` 은 가드 전에 `_reap` 을 돌리므로 "다음 버튼 409" 는 `_PROCS` 가 있는 한 이미 안 난다 — 좀비 판정은 `_PROCS` 를 잃은 뒤(서버 재시작) 경로의 보강이다. 관측자 없는 수거 루프는 범위 밖(CONTEXT).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| 크레딧 곱셈·최대치 | 웹앱 `K*5` | 러너가 `thumb_rules.credit_estimate`·`MAX_REGEN` import → JSON | 진실 둘(L-02) |
| 기작업 판정 | URL 호스트 검사 재구현 | `prep` 산출(`--estimate-out`) | `PROCESSED_HOSTS`·재작업 예외·audit 3갈래가 이미 있다 |
| 게이트·마진 | 웹 필터 | `gate` candidates/rejected | CP-03 |
| 재복사 방어 | 웹 로컬 대장 | gate 그룹 실물 대조 + `copied.jsonl` | L-04 · L-07 |
| 계정 확인 | 웹이 MCP 호출 | CLI `--expect-nick` + 기존 프로필 사전점검 | D-19(Phase 3) |
| 좀비 판별 | psutil 추가 | `ps -o stat=` | 의존성 0 |

## Runtime State Inventory

리네임/마이그레이션 페이즈가 아니다 — 생략. 단, 쓰기 흔적은 기록해 둔다: 썸네일 견적(`prep`)은 **그룹 현황판 시트에 쓴다**(기작업 `완료` 백필 · 원본404 `보류(원본404·삭제대상)`). 크레딧·마켓 쓰기는 아니지만 "쓰기 0" 이라고 표기하면 거짓이다 — 버튼 문구는 `썸네일 견적 — 크레딧 0`.

## Common Pitfalls

### Pitfall 1: CP-03 20% 가 설정에 없다
**What goes wrong:** 웹 경로 gate 가 15%로 돌아 1차보다 느슨한 후보가 나온다. **How to avoid:** Open Q1 결정 → 권장: `workspace.toml [coupang] min_margin = 20.0` 한 줄(설정이지 코드가 아니고, SKILL 명령표와 일치). 요약 JSON 의 `기준` 필드를 화면에 그대로 보이고, 테스트로 `cfg("coupang.min_margin") == 20.0` 고정. **Warning sign:** 미리보기 기준 문구에 `15.0%`.

### Pitfall 2: gws 의존 — 웹 경로 최초
**What goes wrong:** 두 트랙 모두 gws 를 탄다(쿠팡 prep = 주문시트, 썸네일 prep = 마스터 인덱스·현황판). gws 는 `~/.npm-global/bin/gws` — 서버를 PATH 없는 환경(launchd 등)에서 띄우면 `shutil.which` 실패, 7일 토큰 만료 시 403. **How to avoid:** 첫 스모크에서 확인. 실패 시 stderr 꼬리를 그대로 보이고 재로그인/`token_cache.json` 안내(메모리 `gws-oauth-testing-mode-expiry`·`gws-stale-token-cache`).

### Pitfall 3: 썸네일 대상이 거의 0 건 (D-03)
규칙② = 광고 중 = 대부분 한 번 가공됐을 가능성. 게다가 가공됨+대표옵션 있음은 생성이 아니라 audit 으로 간다. 견적 표가 0 이어도 정상 — K·M·A·D·E 를 전부 보여야 "고장" 과 구분된다.

### Pitfall 4: MCP 레이트리밋 합산
쿠팡 preview(ship 단계 수백 workdata) · 썸네일 견적 · 인덱스/스캔이 겹치면 합산 초당 4회를 넘겨 429 → 스냅샷 오류 → (D-17 수정 후) gate 가 fail-closed 로 멈춘다. 안전하지만 헛걸음. SINGLETON 은 같은 kind 만 막는다. **How to avoid:** 화면 문구로 "인덱스·스캔 도는 중엔 누르지 마라" 또는 BULSAJA 무거운 잡끼리 상호배제 — 린 MVP 는 문구로.

### Pitfall 5: verify 종료코드 · apply 매핑 경고
`verify`(all) 는 중복이어도 0. `apply` 의 `요청 N건인데 신규 M건 — 수동 확인` 은 종료코드 없이 stdout 경고뿐이고 `copied.jsonl` 에 `신pid: null` 로 남는다. 결과 표는 파일에서 읽어 `신pid 없음` 을 경고색으로.

### Pitfall 6: 실탄 중 웹앱 코드 수정 금지
`--reload` 가 `_PROCS` 를 비운다(05-06 Pitfall 4). 쿠팡 커밋·썸네일 견적 도중 코드 저장 금지 — 체크포인트 플랜에 명시.

### Pitfall 7: `apply` 미리보기도 현황판에 쓴다 (썸네일)
무플래그 `apply` 도 워커 보류건을 현황판에 기록한다. 웹이 `apply` 미리보기를 부를 이유는 없다 — 견적은 prep 산출만 쓴다.

### Pitfall 8: 그룹명 디렉터리
불사자 그룹명(한글·공백·`/` 가능성)을 run-dir 이름으로 쓸 때 `/`·`..` 치환. 인계 명령 문자열에 경로가 들어가므로 공백 인용.

## Code Examples

### 러너 요약 JSON 모양 (제안 — 웹이 읽는 유일한 계약)
```json
// thumb_web.py estimate → summary.json
{"계정": "부킹", "그룹": [{"그룹명": "...", "run_dir": "...", "시트id": "...",
  "대상": ["pid..."], "이미가공": {"pid": "완료(기존 가공 확인)"}, "정합검사": ["pid"],
  "삭제대상": {"pid": "상품명"}, "조회실패": {"pid": "오류"}, "현황판제외": {"pid": "보류(...)"},
  "오류": null}],
 "합계": {"K": 3, "M": 12, "A": 4, "D": 0, "E": 0, "예상크레딧": 15, "최대크레딧": 30}}
```
```json
// coupang_web.py preview → summary.json
{"단계": [{"이름": "prep", "exit": 0}, ...], "기준": "주문 3회 이상 AND 쿠팡보정마진 20.0% 이상",
 "통과": [/* candidates.json 행 */], "탈락사유별": {"쿠팡그룹에이미있음": 84, "마진미달": 40},
 "이미있음": 84, "그룹읽기": {"총상품수": 87, "읽음": 87, "타오바오결측": 0}}
```

## State of the Art

| Old | Current | Impact |
|---|---|---|
| 쿠팡: 세션에서 단계별 수동 + `gate --min-margin 20` 손으로 | 웹 체인 + 설정값 | 20% 를 설정으로 옮겨야 같은 동작 |
| 썸네일 생성 승인 게이트 없음(2026-08-06) · 잔액 가드만 | + 웹 승인 상한 `--max-credits` | 승인과 지출을 코드로 묶는 첫 고리 |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | CPython `Popen.poll()` 이 ECHILD 에서 `returncode=0` 으로 적는다 → waitpid 를 쓰면 실패 잡이 성공으로 기록될 수 있다 | Folded Todo | 낮음 — 권장안(ps stat)은 이 가정과 무관하게 안전 |
| A2 | 마스터 인덱스 그룹명 == 불사자 마켓그룹명(정확일치) | D-04 | 중 — 다르면 그룹 단위 제외. 첫 스모크에서 확인 |
| A3 | `bulsaja_market_group_products` 응답의 `총상품수` 가 그룹 전건 수와 같다(현재 로그 표시에만 쓰임) | D-17 | 중 — 다르면 strict 가 항상 실패. 테스트 전 실 1회 읽기(크레딧 0)로 확인 |
| A4 | 복사본 스냅샷이 원본의 `불사자코드` 를 승계한다(코드 주석 2026-09-13) | D-17 ③ | 낮음 — 2차 키일 뿐, 1차 키 동작 불변 |
| A5 | 스킬 키워드 트리거("썸네일 작업 이어서 <run-dir>")로 인계 세션이 뜬다 | D-06 | 낮음 — 안 뜨면 명령에 스킬명 명시 |

## Open Questions (RESOLVED)

1. **쿠팡 게이트 마진 20 vs 설정 15** — RESOLVED: 07-03 에서 `workspace.toml` min_margin=20.0 + 테스트, 07-07 체크포인트에서 용팀장 확인
   - What we know: CP-03·ROADMAP SC-3·SKILL 명령표·1차 파일럿 = 20. `workspace.toml` = 15.0. D-15 = 웹은 기준 인자 안 넘김.
   - Recommendation: `workspace.toml` 을 20.0 으로(설정 한 줄 + 테스트). 용팀장 확인 항목에 올린다 — 메모리상 2차엔 18 로 낮출 여지도 언급됨. 추천안으로 진행(메모리 `go-with-recommendation-by-default`).
2. **썸네일 `recover` 웹 버튼** — RESOLVED: 07-04 에서 버튼 없이 복사용 명령만 표시
   - `recover` 는 크레딧 0 이지만 불사자 쓰기(순서 복원)가 있고, 회수 후 verdict·commit 은 어차피 Claude 세션. 린 MVP 권장: 버튼 없이 **복사용 recover 명령**만 표시. 버튼이 필요하면 `thumb_recover` ∈ WRITE_KINDS·BULSAJA_KINDS.
3. **쿠팡 prep 소요시간** — OPEN(실측 항목): 07-05 라이브 미리보기 스모크에서 기록 — 12탭 gws 읽기 + ship workdata 수백 회. 실측 없음 → 첫 미리보기 스모크에서 기록.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|---|---|---|---|---|
| `.venv/bin/python3` (eroomlib·requests·PIL) | 두 CLI·러너 | ✓ | 3.12 | — |
| `.venv-web` (fastapi·pytest) | 웹앱·테스트 | ✓ | pytest 9.1.1 | — |
| gws | 두 prep | ✓ `~/.npm-global/bin/gws` | — | 없음 — 서버 PATH·토큰 확인 필요 |
| `/usr/bin/caffeinate` | 수 분 잡 | ✓ | — | 없으면 프리픽스 생략(기존 로직) |
| sqlite3 | 잡 레지스트리 | ✓ | — | — |

## Validation Architecture

### Test Framework
| Property | Value |
|---|---|
| Framework | pytest 9.1.1 (두 venv) |
| Config | `webapp/pytest.ini` (웹앱) · 스킬 쪽은 설정 없음(unittest/pytest 혼용) |
| Quick run (웹) | `.venv-web/bin/pytest webapp/tests/test_jobs.py webapp/tests/test_argv.py -q` |
| Quick run (CLI) | `.venv/bin/python3 -m pytest -q .claude/skills/coupang-candidates/scripts/ .claude/skills/bulsaja-thumbnail/scripts/` |
| Full suite | 위 둘 전부 — 기준선 실측: 웹앱 ~808 passed(약 14초) · 썸네일 205 passed · 쿠팡 36 passed |

### Phase Requirements → Test Map
| Req | Behavior | Type | Command | File |
|---|---|---|---|---|
| THUMB-01 | ② 행 선택 → 서버 재구성 · 미해소 제외 사유 · 그룹명 매핑 · 상한 20 | unit/route | `.venv-web/bin/pytest webapp/tests/test_routes_thumb.py -q` | ❌ Wave 0 |
| THUMB-02 | `--max-credits` 누적 초과 exit 5 · 무플래그 불변 · `--only-pending` · `--expect-nick` exit 4 · 러너 그룹 실패 격리 | unit(가짜 MCP·matrix) | `.venv/bin/python3 -m pytest -q .claude/skills/bulsaja-thumbnail/scripts/test_thumb_web.py` | ❌ Wave 0 |
| THUMB-03 | estimate-out 4갈래 + K×5/K×10 · 견적 표 렌더 · web_approval.json 스키마 | unit + TestClient | 위 둘 | ❌ |
| CP-01 | 체인 단계 순서 · 비0 정지 · 센티널 · summary | unit(가짜 stage 실행기) | `.venv/bin/python3 -m pytest -q .claude/skills/coupang-candidates/scripts/test_coupang_web.py` | ❌ |
| CP-02 | 커밋 라우트 = 미리보기 id 하나 · 타이핑 불일치 400 · 첫 회 10 · 두 번째 커밋 400 · WRITE 가드 409 · 늘어남 exit 5 · `--pids-file` 필터 | unit/route | `.venv-web/bin/pytest webapp/tests/test_routes_coupang.py -q` + 위 | ❌ |
| CP-03 | argv·러너·webapp 트리에 `--min-margin`/`--min-orders`/`--strict-shipping` 0회 · cfg min_margin == 20 | tree grep | `.venv-web/bin/pytest webapp/tests/test_argv.py -q -k 쿠팡` | ❌ |
| CP-04 | `--skip-group-check` 트리 0회 · 스냅샷 오류 → candidates 미생성 비0 · 빈 페이지 조기종료 비0 · 불사자코드 2차 키 · 정상 골든 | unit | `test_coupang_web.py` | ❌ |
| (todo) | `_alive` 좀비 → False (가짜 ps) | unit | `.venv-web/bin/pytest webapp/tests/test_jobs.py -q -k 좀비` | ❌ |
| 실측 | 썸네일 prep 1회 · 쿠팡 미리보기 1회(1차 87건이 `쿠팡그룹에이미있음`) | smoke(크레딧 0) | 체크포인트 플랜 | manual |
| 시각 | 쿠팡 커밋 버튼 색·위치·접힘 | uat-verifier + 사람(심미) | — | manual |

### Sampling Rate
- 태스크 커밋마다: 해당 트랙 quick run
- 웨이브 머지마다: 두 스위트 전체
- Phase gate: 전체 green + 크레딧 0 스모크 2건 → 그 뒤 blocking 체크포인트 2건

### Wave 0 Gaps
- [ ] `.claude/skills/coupang-candidates/scripts/test_coupang_web.py` — 가짜 `CoupangMCP`(collect_group/snapshot.ensure 스텁) + 골든(`gate` 무플래그 candidates.json byte 동일)
- [ ] `.claude/skills/bulsaja-thumbnail/scripts/test_thumb_web.py` — `test_thumb_prep.py` 의 matrix/snapshot 몽키패치 관용구 재사용
- [ ] `webapp/tests/test_routes_thumb.py` · `test_routes_coupang.py` — `jobs.spawn` 가짜(05 관례)
- [ ] 무플래그 골든 픽스처는 **CLI 를 한 줄도 고치기 전** 커밋에서 만든다(`detail_golden_noflag.json` 선례)

## Security Domain

| ASVS | Applies | Control |
|---|---|---|
| V2/V3 인증·세션 | 기존 | 127.0.0.1 · Host/Origin · 부팅 토큰(Phase 1) — 새 POST 라우트 전부 같은 미들웨어 |
| V4 접근제어 | yes | 실행 라우트는 부모 잡 id 만 · 경로는 서버 유도 |
| V5 입력검증 | yes | pydantic 요청 모델(추가 필드 무시) · 타이핑 건수 정수 · 보드 키 화이트리스트 · 그룹명 디렉터리 정규화 |
| V6 암호 | no | — |

| Threat | STRIDE | Mitigation |
|---|---|---|
| 클라이언트가 대상 pid·run-dir 주입 | Tampering | 서버 재구성 · 부모 체인 유도 |
| 인자 주입(`--skip-group-check` 등) | Elevation | argv 모델에 필드 없음 + 트리 grep 테스트 |
| 잘못된 계정으로 복사/생성 | Spoofing | 사전점검 409 + CLI exit 4 |
| 동일 미리보기 반복 커밋 | Repudiation/비가역 | `children_of` 성공분 있으면 400 + `copied.jsonl` + gate 대조 |
| 명령 문자열 복사 시 경로 인젝션 | Tampering | 인계 명령은 표시용 텍스트, 서버가 실행하지 않음 · 그룹명 정규화 |

## Sources

### Primary (HIGH — 로컬 코드 실측, 2026-09-29)
- `.claude/skills/bulsaja-thumbnail/scripts/run_thumbs.py` (prep 292-535 · _guard_credits 1299 · cmd_apply 1327 · _generate 1492 · recover 2057 · argparse 2375)
- `.claude/skills/bulsaja-thumbnail/scripts/thumb_rules.py` (MAX_REGEN · CREDITS_PER_IMAGE · generate_plan · credit_estimate)
- `.claude/skills/coupang-candidates/scripts/run_coupang.py` 전체 · `SKILL.md` · `coupang_rules.passes`
- `.claude/lib/eroomlib/bulsaja.py` (`_post` 재시도) · `snapshot.py` (collect_group · ensure) · `matrix.py` (pending · mark_many · index_groups) · `gsheets.py` (gws 탐색)
- `webapp/jobs.py` · `argv.py` · `settings.py` · `paths.py` · `join.py` · `routes/jobs.py`(detail estimate) · `templates/board.html` · `static/board.js`
- `workspace.toml [coupang]` · `~/python_work/data/coupang/runs/20260913-1215/*` (읽기만)
- `.bulsaja-detail-page/scripts/detail_batch.py` `_계정확인` · `market_update.py` `_연결과가드`
- 테스트 실행: 스킬 205+36 passed, 웹앱 전체 passed

### Tertiary (LOW)
- CPython ECHILD → returncode 0 동작 (A1, 훈련 지식)

## Metadata

**Confidence breakdown:**
- CLI 표면·주입점: HIGH — 코드 직독
- D-17 구멍 분석: HIGH — 코드 경로 추적(실 429 재현은 안 함)
- 러너 설계: MEDIUM-HIGH — 기존 관용구 조합, 재량 영역
- 소요시간·gws 환경: LOW — 실측 전

**Research date:** 2026-09-29
**Valid until:** 2026-10-29 (CLI 가 바뀌면 즉시 무효)
