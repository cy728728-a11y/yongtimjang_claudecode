# Roadmap: 셀러 관제탑 (Seller Control Tower)

## Overview

되돌릴 수 있고 조인이 필요 없는 버튼 하나(입찰가 인상)로 "판정 → 미리보기 → 실행" 3단 틀을 실물로 굳힌 뒤,
그 틀 위에 파괴적 쓰기(꺼진 소재 정리)를 얹어 안전 계약을 완성한다.
틀이 굳으면 이 프로젝트 최대 리스크인 엔티티 해소(광고↔불사자)와 상세 상태 판정을 붙여 **작업 대상을 정확히 골라내고**,
기성 해법이 없는 홍보배너 식별을 독립 단계로 검증한 다음, Core Value인 상세페이지 생성 버튼과 마켓 반영을 얹는다.
마지막으로 남은 버튼 두 개(썸네일 교체 / 쿠팡 복사)를 붙여 관제탑을 닫는다.

**전제:** 웹앱은 기존 CLI 의 서브프로세스 래퍼다. 검증된 로직을 재작성하지 않는다.
**모수:** 주당 약 120행. 성능 최적화 단계는 없다.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: 첫 왕복 — 보드 + 입찰가 인상 버튼** - 터미널 없이 브라우저에서 규칙① 대상을 보고 입찰가를 올리고 되돌린다
- [ ] **Phase 2: 되돌릴 수 없는 쓰기 — 꺼진 소재 정리** - 백업 선행·상한·재조회로 안전 계약을 완성하고 삭제 버튼을 연다
- [ ] **Phase 3: 작업 대상 확정 — 엔티티 해소 + 상세 상태 판정** - 광고 행을 불사자 상품에 잇고 🔴🟡⚪ 상태로 대상 목록을 뽑는다
- [ ] **Phase 4: 홍보배너 식별** - 기존 상세 이미지에서 중국 판매사 배너를 골라내고 100건 라벨링으로 검증한다
- [ ] **Phase 5: 상세페이지 작업 버튼 ★ Core Value** - 🔴 상품을 화면에서 골라 AI 상세를 접수·폴링까지 완주한다
- [ ] **Phase 6: 마켓 수정업로드** - 생성 완료분을 스마트스토어에 반영한다 (1건 육안 확인 게이트)
- [ ] **Phase 7: 남은 버튼 — 썸네일 교체 / 쿠팡 복사** - 규칙② 썸네일 교체와 쿠팡 6단계 원클릭을 붙여 관제탑을 닫는다

## Phase Details

### Phase 1: 첫 왕복 — 보드 + 입찰가 인상 버튼

**Goal**: 터미널을 열지 않고 브라우저에서 광고 판정 결과를 상품 단위로 보고, 규칙①(노출 0) 대상의 입찰가를 미리보기 후 올리고 되돌린다
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: ENG-01, ENG-02, ENG-03, ENG-07, SAFE-01, SAFE-02, SAFE-03, FLOW-01, FLOW-02, FLOW-04, FLOW-05, BOARD-01, BOARD-02, BOARD-03, BOARD-04, BID-01, BID-02, BID-03, BID-04
**Success Criteria** (what must be TRUE):

  1. 사용자가 브라우저에서 광고 판정 결과를 한 줄 = 상품 1개로 보고, 계정·규칙·상태로 걸러 정렬·검색한다 (계정이 4개든 6개든 설정 파일만 고치면 화면이 따라온다)
  2. 사용자가 행을 골라 "입찰가 인상 미리보기"를 누르면 상품별 현재가 → 인상 후 가격이 나오고, 그룹입찰 상품은 그룹 기본입찰가에서 출발한 값이 보인다
  3. 사용자가 실행을 누른 뒤 브라우저 탭을 닫았다 다시 열어도 그 작업의 진행 로그를 처음부터 이어서 본다
  4. 실행 결과가 항목 단위(성공/실패/스킵 + 사유)로 남고, 화면의 되돌리기 버튼 한 번으로 인상 전 상태로 복원된다
  5. 다른 탭의 임의 사이트가 이 서버에 쓰기를 트리거하지 못한다 (127.0.0.1 바인드 + Host/Origin 검증 + 부팅 토큰), 그리고 화면·로그 어디에도 광고 시크릿·불사자 토큰이 나오지 않는다

**Plans**: 9 plans in 8 waves

Plans:
**Wave 1**

- [x] 01-01-PLAN.md — Wave 0: 테스트 기반(.venv-web · pytest · 픽스처) + paths/settings + 프론트 vendoring
- [ ] 01-02-PLAN.md — Wave 1: CLI 주입구 패치 (--only-ads · --preview-out · accounts · 항목단위 result/error)
- [ ] 01-03-PLAN.md — Wave 1: 보안 3층(127.0.0.1 · Host · Origin · 부팅토큰) + 앱 셸 + 기동 스크립트

**Wave 2** *(blocked on Wave 1 completion)*

- [ ] 01-04-PLAN.md — Wave 2: 상품 단위 보드(6규칙 · 필터 · 정렬 · 검색) + 회차 신선도 배너

**Wave 3** *(blocked on Wave 2 completion)*

- [ ] 01-05-PLAN.md — Wave 3: 작업 엔진(argv · jobs SQLite · subprocess · 쓰기 잡 전역 가드) + "새로 수집" 버튼

**Wave 4** *(blocked on Wave 3 completion)*

- [ ] 01-06-PLAN.md — Wave 4: 로그 오프셋 tail + SSE 전량 재생 (탭 닫았다 이어보기) + Skeleton B

**Wave 5** *(blocked on Wave 4 completion)*

- [ ] 01-07-PLAN.md — Wave 5: 선택 UI(보이는 것만 vs 필터 전체) + 입찰가 인상 미리보기 (Skeleton A)

**Wave 6** *(blocked on Wave 5 completion)*

- [ ] 01-08-PLAN.md — Wave 6: 실행(commit) + 항목 단위 결과 + 미리보기 대비 diff

**Wave 7** *(blocked on Wave 6 completion)*

- [ ] 01-09-PLAN.md — Wave 7: 되돌리기 2종(이 작업분만 / 이 회차 전체) + 범위 가드

**UI hint**: yes

### Phase 2: 되돌릴 수 없는 쓰기 — 꺼진 소재 정리

**Goal**: 백업이 선행되는 파괴적 삭제를 화면에서 안전하게 돌리고, 그 과정에서 모든 버튼이 공유할 안전 계약(재조회·상한·감사 로그·작업 잠금)을 완성한다
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: ENG-04, ENG-05, ENG-06, SAFE-04, SAFE-05, SAFE-06, SAFE-07, FLOW-03, FLOW-06, FLOW-07, BOARD-05, BOARD-06, PRUNE-01, PRUNE-02, PRUNE-03
**Success Criteria** (what must be TRUE):

  1. 사용자가 규칙⑥ 중 `AD_ABNORMAL_INTERLOCK` 소재만 삭제 대상으로 전부 나열해 보고, 건수를 타이핑해 확인한 뒤에야 삭제가 실행된다 (검수중·거부는 목록에 없다)
  2. 백업이 실패하면 삭제가 한 건도 나가지 않고 그 사유가 화면에 뜬다
  3. 미리보기가 낡았으면(그 사이 상태가 바뀜) 실행이 거부되고, 실행 직전 재조회에서 빠진 항목이 사유와 함께 보고된다
  4. 정지된 소재의 과거 클릭이 현재 유입으로 표시되지 않고, 판정이 틀렸을 때 1클릭으로 오판정 표시를 남긴다
  5. 같은 대상에 같은 작업을 두 번 눌러도 두 번 돌지 않고, 서버를 재시작하면 고아 작업이 정리된 상태로 보이며, 수십 분짜리 작업 중 맥북이 자지 않는다
  6. 실패한 항목만 골라 재시도할 수 있고, 모든 실행이 감사 로그(JSONL)에 언제·뭘·몇 건·크레딧 얼마로 남는다

**Plans**: TBD
**UI hint**: yes

### Phase 3: 작업 대상 확정 — 엔티티 해소 + 상세 상태 판정

**Goal**: 광고 판정 행을 불사자 상품에 실제로 잇고 상세 상태를 3단계로 판정해, "유입은 있는데 상세가 중국어 원본인 상품" 목록을 화면에서 정확히 뽑아낸다
**Mode:** mvp
**Depends on**: Phase 2
**Requirements**: ENG-08, JOIN-01, JOIN-02, JOIN-03, JOIN-04, STATE-01, STATE-02, STATE-03, STATE-04, STATE-05
**Success Criteria** (what must be TRUE):

  1. 사용자가 규칙③+⑤ 약 120행의 해상률을 숫자로 본다 (몇 건 중 몇 건이 이어졌는지), 이어지지 않은 항목은 숨겨지지 않고 "미해소"로 사유와 함께 보인다
  2. 보드 한 줄에서 광고 성과 옆에 상세 상태가 🔴 중국어 원본 / 🟡 단순번역만 / ⚪ AI 가공 완료로 보이고, 상태로 걸러 작업 대상 목록을 뽑는다 (`imageTranslated` 가 `'0'` `'1'` `False` `1` 어느 형태로 와도 판정이 뒤집히지 않는다)
  3. 불사자코드 하나에 사본이 여러 개 붙은 항목은 "이 버튼이 N건에 적용됩니다"로 팬아웃이 먼저 보인다
  4. 지금 이 맥북에서 `detail_batch.py` 가 `ModuleNotFoundError` 없이 돈다 (로직 무변경 shim)
  5. 불사자 외부 경로로 상세를 반영해도 `aiImageGenerated` 가 찍히는지 1건 실측으로 답이 나오고, 안 찍히면 보완 인덱스가 서 있다 (크레딧 무한 루프 차단)
  6. 작업 화면에 현재 불사자 계정이 항상 표시되고, 기대 계정(부킹/용쌤)이 아니면 실행이 거부된다

**Plans**: TBD
**UI hint**: yes

### Phase 4: 홍보배너 식별

**Goal**: 기존 상세 이미지에서 중국 판매사 홍보배너만 골라내고, 실제 작업에 쓰기 전에 100건 라벨링으로 미탐 0%를 증명한다
**Mode:** mvp
**Depends on**: Phase 3
**Requirements**: BANNER-01, BANNER-02, BANNER-03, BANNER-04, BANNER-05
**Success Criteria** (what must be TRUE):

  1. 사용자가 아무 상품이나 골라 "이 상세의 몇 번째 이미지를 배너로 봤는지"와 남는 제품 이미지 목록을 눈으로 확인한다
  2. 100건 손라벨링 세트에서 미탐 0% · 오탐 10% 이하가 숫자로 보고되고, 이 게이트를 통과하기 전에는 상세 생성 입력으로 쓰이지 않는다
  3. 제거율이 50%를 넘거나 남는 제품 이미지가 2장 미만이면 그 상품이 통째로 스킵되고 스킵 사유가 보인다 (사람 판단 큐를 만들지 않는다)
  4. 빈도 판정이 타오바오상품번호 distinct 기준으로 돌고, 같은 타오바오 상품의 물갈이 사본이 빈도를 부풀리지 않는다

**Plans**: TBD

### Phase 5: 상세페이지 작업 버튼 ★ Core Value

**Goal**: 🔴 상품을 화면에서 골라 기존 상세 이미지(배너 제거분)를 입력으로 AI 상세 생성을 접수하고, 브라우저를 닫아도 폴링이 완주해 결과를 확인한다
**Mode:** mvp
**Depends on**: Phase 4
**Requirements**: DETAIL-01, DETAIL-02, DETAIL-03, DETAIL-04, DETAIL-05, DETAIL-06, DETAIL-07
**Success Criteria** (what must be TRUE):

  1. 사용자가 🔴 상품 5건을 골라 접수→폴링까지 터미널 없이 완주하고, 중간에 브라우저를 닫아도 완주한다
  2. 접수 전에 예상 크레딧이 보이고, 기작업 스킵분을 뺀 실제 접수분 기준으로 다시 보고된다
  3. 같은 상품 목록으로 두 번째 회차를 돌리면 재접수가 0건이다 (기작업 스킵이 목표 장수 변동과 무관하게 걸린다)
  4. 생성 장수가 `min(제품이미지 수, 10)` 하한 2로 나오고, 접수 확정 응답의 예상장수가 요청과 다르면 전량 접수 전에 멈춘다
  5. 폴링이 타임아웃돼도 실패로 보고되지 않고 recover 경로로 안내된다 (크레딧 이중 지불 없음)

**Plans**: TBD
**UI hint**: yes

### Phase 6: 마켓 수정업로드

**Goal**: AI 상세 생성 완료분을 화면에서 스마트스토어에 반영하되, 상하단 안내이미지 되돌림 모순을 1건 육안 확인으로 먼저 깬다
**Mode:** mvp
**Depends on**: Phase 5
**Requirements**: MARKET-01, MARKET-02, MARKET-03
**Success Criteria** (what must be TRUE):

  1. 사용자가 생성 완료분을 골라 버튼 하나로 스마트스토어에 반영하고, 항목 단위 성공/실패를 본다
  2. 첫 1건이 반영된 뒤 화면이 멈추고 "스토어에서 육안 확인" 확인을 받기 전에는 나머지가 나가지 않는다 (상하단 안내이미지가 되돌려지는지 여기서 판명된다)
  3. 반영 전 원본 상세 HTML 이 보관되어 있고, 사용자가 그 백업의 위치를 화면에서 확인한다

**Plans**: TBD
**UI hint**: yes

### Phase 7: 남은 버튼 — 썸네일 교체 / 쿠팡 복사

**Goal**: 규칙②(노출 100+ & CTR<1%) 썸네일 교체와 쿠팡 복사 6단계 원클릭을 붙여, 버튼 6종이 한 화면에 모인 관제탑을 닫는다
**Mode:** mvp
**Depends on**: Phase 3 (썸네일 트랙) / Phase 2 (쿠팡 트랙) — Phase 6 이후 실행 권장, 두 트랙은 서로 병렬 가능
**Requirements**: THUMB-01, THUMB-02, THUMB-03, CP-01, CP-02, CP-03, CP-04
**Success Criteria** (what must be TRUE):

  1. 사용자가 규칙② 대상을 화면에서 보고 예상 크레딧을 확인한 뒤 썸네일 교체를 실행한다 (기존 `bulsaja-thumbnail` 스킬이 그대로 돈다)
  2. 사용자가 버튼 하나로 prep→resolve→build→ship→gate→apply 전공정을 돌리고, `apply --commit` 단계에서만 따로 확인을 받는다
  3. 기존 게이트(주문 3회 이상 + 쿠팡보정 가중마진 20%)가 그대로 걸려 유입만 있는 상품은 후보에 나타나지 않는다
  4. 이미 쿠팡에 올라간 상품이 두 번 복사되지 않는다 (매번 쿠팡 그룹 실물을 읽어 타오바오상품번호로 대조)

**Plans**: TBD
**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. 첫 왕복 — 보드 + 입찰가 인상 버튼 | 1/9 | In Progress|  |
| 2. 되돌릴 수 없는 쓰기 — 꺼진 소재 정리 | 0/TBD | Not started | - |
| 3. 작업 대상 확정 — 엔티티 해소 + 상세 상태 판정 | 0/TBD | Not started | - |
| 4. 홍보배너 식별 | 0/TBD | Not started | - |
| 5. 상세페이지 작업 버튼 ★ Core Value | 0/TBD | Not started | - |
| 6. 마켓 수정업로드 | 0/TBD | Not started | - |
| 7. 남은 버튼 — 썸네일 교체 / 쿠팡 복사 | 0/TBD | Not started | - |

## Sequencing Notes

리서치 실측에서 나온 순서 제약. 단계 순서를 바꿀 때 반드시 다시 확인할 것.

| 제약 | 반영 |
|---|---|
| `detail_batch.py` 가 이 맥북에서 `ModuleNotFoundError` 로 안 돈다 (STATE-01) | Phase 3 — 상세 버튼(Phase 5)보다 앞 |
| `aiImageGenerated` 외부 반영 경로 기록 여부 미확인 (STATE-04) | Phase 3 — 중복방지 설계 확정 전제 |
| 홍보배너 식별은 기성 해법 없음 + 100건 라벨링 게이트 | Phase 4 독립 단계 — 상세 생성에 끼워 넣으면 게이트가 생략된다 |
| 조인은 보드가 있어야 해상률을 보며 전략을 고친다 | Phase 3 — Phase 1~2 보드 이후, 조인 필요한 버튼(상세·썸네일) 이전 |
| 입찰가·소재정리·쿠팡복사는 조인 불필요 (adId / `find_by_code` 자체 해결) | Phase 1, 2, 7 |
| 채널상품ID는 20일 물갈이로 재발급 (실측 교집합 0/160) | JOIN-04 — 영구 키 금지 |
| 작업 모수 주당 ~120행 | 성능 최적화 단계 없음. 서버사이드 페이징·가상 스크롤 Out of Scope |
| 자동화 2단계(전부 실행)·3단계(스케줄) | v2. 단 v1 의 3단 구조와 감사 로그가 그 승인 근거를 쌓는다 (ENG-07, FLOW-07, BOARD-06) |
