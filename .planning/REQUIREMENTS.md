# Requirements: 셀러 관제탑 (Seller Control Tower)

**Defined:** 2026-09-19
**Core Value:** 유입이나 판매가 있는데 상세페이지가 중국어 원본·단순번역인 상품을, 중복 작업 없이 한 화면에서 골라 고치고 반영하는 것

**v1 전략:** 조인이 필요 없고 되돌릴 수 있는 버튼 2개(입찰가·소재정리)로 3단 실행 틀을 먼저 굳힌 뒤, Core Value(상세페이지)를 그 틀 위에 얹는다. 버튼 5개는 모두 v1 안에 들어가되 순서가 있다.

---

## v1 Requirements

### 기반 — 실행 엔진 (ENG)

- [x] **ENG-01**: 기존 CLI 를 **서브프로세스로** 실행한다 — 같은 프로세스에 올리지 않는다
      (`run_ads.py` 가 네임스페이스 없는 이름을 `sys.path.insert` 로 import 하고, `run_yong.py` 가 토큰을 환경변수로 주입한다. in-process 면 계정 자격증명이 작업 간에 섞인다)
- [ ] **ENG-02**: 실행한 작업이 브라우저를 닫아도 계속 돌고, 재접속하면 그동안의 출력을 처음부터 이어서 볼 수 있다
- [ ] **ENG-03**: 자식 프로세스의 출력을 append-only 로그 파일에 쌓고, 화면은 그 파일의 오프셋부터 재생한다 (스트림 직결 금지 — 닫힌 사이 출력이 사라진다)
- [ ] **ENG-04**: 같은 대상에 같은 작업이 동시에 두 번 돌지 않는다 (작업 잠금)
- [ ] **ENG-05**: 서버를 재시작하면 고아가 된 작업을 감지해 상태를 정리한다
- [ ] **ENG-06**: 수십 분짜리 작업 중 맥북이 절전으로 자지 않는다 (`caffeinate -i`)
- [x] **ENG-07**: 작업 생성이 HTTP 핸들러가 아니라 **호출 가능한 함수**로 존재한다 (3단계 스케줄 자동화가 같은 경로를 쓰게 하기 위함)
- [ ] **ENG-08**: 작업 시작 전 `bulsaja_my_profile` 로 계정을 확인하고, 기대 계정(부킹/용쌤)이 아니면 실행을 거부한다
      — 화면에 현재 계정이 항상 표시된다 (토큰을 바꿔 끼우는 구조라 틀린 계정으로 도는 걸 알아챌 방법이 이것뿐이다)

### 기반 — 안전 (SAFE)

- [x] **SAFE-01**: 서버는 `127.0.0.1` 에만 바인드하고, Host 헤더 화이트리스트와 Origin 검증을 통과한 요청만 받는다
- [x] **SAFE-02**: 부팅 시 발급한 랜덤 토큰이 있어야 쓰기 요청이 통과한다 (다른 탭의 사이트가 CSRF 로 크레딧을 태우는 걸 막는다)
- [x] **SAFE-03**: 자격증명(광고 시크릿·불사자 토큰)이 화면·로그·에러 메시지에 절대 나오지 않는다
- [ ] **SAFE-04**: 백업이 선행되는 작업은 **백업 실패 시 쓰기를 중단**한다
- [ ] **SAFE-05**: `--commit` 직전에 대상을 재조회해, 미리보기 시점 이후 상태가 바뀐 항목은 제외하고 그 사실을 보고한다
- [ ] **SAFE-06**: 미리보기와 실행이 **같은 대상 선정 함수**를 쓴다 (둘이 갈라지면 본 것과 다른 게 실행된다)
- [ ] **SAFE-07**: 1회 실행 건수 상한과 크레딧 상한을 넘으면 실행이 거부된다

### 실행 틀 — 3단 계약 (FLOW)

- [ ] **FLOW-01**: 모든 버튼이 **판정 → 미리보기 → 실행** 3단을 똑같은 모양으로 지난다
- [x] **FLOW-02**: 미리보기 결과가 화면 상태가 아니라 **run-dir 의 파일**로 저장되고, 실행은 그 파일을 지목해서 돈다
- [ ] **FLOW-03**: 미리보기가 낡으면(대상 상태가 바뀜) 실행이 거부되고 다시 판정하라고 안내한다
- [ ] **FLOW-04**: 확인 강도가 버튼마다 다르다 — 되돌릴 수 있는 작업은 모달 없이 되돌리기 버튼만, 되돌릴 수 없는 작업만 건수 타이핑
- [x] **FLOW-05**: 결과가 **항목 단위**로 남는다 — 성공 / 실패 / 스킵을 사유와 함께 구분해 보여준다
- [ ] **FLOW-06**: 실패한 항목만 골라 재시도할 수 있다
- [ ] **FLOW-07**: 실행 이력이 감사 로그(JSONL)로 남는다 — 언제·뭘·몇 건·크레딧 얼마

### 보드 (BOARD)

- [x] **BOARD-01**: 광고 판정 결과를 한 줄 = 상품 1개로 보여준다 (상품명·계정·노출·클릭·구매완료·규칙번호)
- [x] **BOARD-02**: 계정·규칙·상태로 거르고, 정렬하고, 검색한다 (계정 수를 화면·코드에 박지 않는다)
- [ ] **BOARD-03**: 다중 선택 시 **"보이는 것만"과 "필터 전체"를 명시적으로 구분**한다 — 헤더 체크박스는 현재 페이지만 고르고, 전체 선택은 별도 확인을 거친다
- [ ] **BOARD-04**: 선택한 항목 수와 예상 비용이 실행 버튼 옆에 항상 보인다
- [ ] **BOARD-05**: 정지된 소재의 과거 실적을 현재 유입으로 표시하지 않는다 (물갈이 부산물인 연동끊김 대량정지 방어)
- [ ] **BOARD-06**: 판정이 틀렸을 때 **1클릭으로 오판정 표시**를 남긴다 (2단계 자동화의 승인 근거가 된다)

### 버튼 1 — 입찰가 인상 (BID)

- [ ] **BID-01**: 규칙①(노출 0, 7일) 대상을 판정해 보여준다
- [ ] **BID-02**: 미리보기로 상품별 현재가 → 인상 후 가격을 보여준다
- [ ] **BID-03**: 그룹입찰 상품의 출발점이 **그룹 기본입찰가**다 (개별 `bidAmt` 를 쓰면 올리려다 내린다)
- [ ] **BID-04**: 실행 후 화면에서 바로 되돌릴 수 있다 (`--revert`)

### 버튼 2 — 꺼진 소재 정리 (PRUNE)

- [ ] **PRUNE-01**: 규칙⑥ 중 `AD_ABNORMAL_INTERLOCK` 만 삭제 대상으로 판정한다 (검수중·거부는 제외)
- [ ] **PRUNE-02**: 백업이 성공한 뒤에만 삭제가 실행된다
- [ ] **PRUNE-03**: 삭제 대상을 실행 전에 전부 나열해 보여준다

### 엔티티 해소 (JOIN)

- [ ] **JOIN-01**: 광고 소재와 불사자 상품을 잇고, **해상률을 숫자로 보여준다** (몇 건 중 몇 건이 이어졌는지)
- [ ] **JOIN-02**: 이어지지 않은 항목을 숨기지 않고 "미해소"로 표시한다 (조용히 빠지면 대상 누락을 모른다)
- [ ] **JOIN-03**: 불사자코드 하나에 사본이 여러 개 붙는 팬아웃을 감지해, 실행 전에 "이 버튼이 N건에 적용됩니다"를 보여준다 (실측: 코드 1개에 사본 27건)
- [ ] **JOIN-04**: 채널상품ID는 물갈이로 재발급되므로 **영구 키로 쓰지 않는다** (실측: 교집합 0/160)

### 상세페이지 상태 판정 (STATE)

- [ ] **STATE-01**: `detail_batch.py` 의 윈도 경로 하드코딩을 고쳐 이 맥북에서 돌게 한다 (로직 무변경 shim)
- [ ] **STATE-02**: `imageTranslated` 를 **타입 안전하게** 해석한다 — 실측 4종(`'0'` `'1'` `False` `1`)을 모두 올바로 처리한다
- [ ] **STATE-03**: 상품 상태를 3단계로 판정한다 — 🔴 중국어 원본 / 🟡 단순번역만 / ⚪ AI 가공 완료
- [ ] **STATE-04**: 불사자 외부 경로로 상세를 반영해도 `aiImageGenerated` 가 찍히는지 **1건 실측으로 확인**하고, 안 찍히면 보완 인덱스를 둔다 (안 하면 크레딧 무한 루프)
- [ ] **STATE-05**: 기작업 스킵 조건을 **목표 장수와 분리된 절대 조건**으로 둔다 (동적 장수가 스킵을 무력화하지 않게)

### 홍보배너 식별 (BANNER)

- [ ] **BANNER-01**: `renderContent` 에서 상세페이지 이미지 목록을 뽑는다
- [ ] **BANNER-02**: 이미지를 **pHash** 로 지문화해 코퍼스 빈도를 센다 (URL 로 세면 물갈이 사본이 다른 이미지로 잡힌다)
- [ ] **BANNER-03**: 빈도를 **타오바오상품번호 distinct** 기준으로 센다 (productId 기준이면 제품 사진도 배너로 판정되어 전량 오탐)
- [ ] **BANNER-04**: 100건 라벨링으로 검증하고 **미탐 0%** 를 통과해야 실제 작업에 쓴다 (중국 점포 로고·위챗·QR이 스마트스토어에 게시되는 게 오탐보다 비싸다)
- [ ] **BANNER-05**: 제거율 상한(50%)과 잔여 장수 하한(2장)을 두고, 애매하면 그 상품을 통째로 스킵한다 (사람 큐를 만들지 않는다)

### 버튼 3 — 상세페이지 작업 (DETAIL) ★ Core Value

- [ ] **DETAIL-01**: AI 상세 생성 입력을 **기존 상세 이미지 − 홍보배너** 로 한다 (썸네일·옵션 이미지는 쓰지 않는다)
- [ ] **DETAIL-02**: 생성 장수를 `min(제품이미지 수, 10)` 으로 하고 하한 2를 지킨다
- [ ] **DETAIL-03**: `imageUrls` 와 `sectionCount` 를 **동시에** 보낸다 (하나만 보내면 1장짜리로 접수되어 크레딧이 날아간다)
- [ ] **DETAIL-04**: 접수 확정 응답의 `예상장수`가 요청과 다르면 전량 접수 전에 중단한다
- [ ] **DETAIL-05**: 접수 전 예상 크레딧을 보고하고, 기작업 스킵분을 반영해 실제 접수분 기준으로 다시 보고한다
- [ ] **DETAIL-06**: 폴링 타임아웃을 실패로 취급하지 않는다 (재생성하면 크레딧 이중 지불)
- [ ] **DETAIL-07**: 접수와 폴링이 분리되어, 폴링이 끊겨도 체크포인트로 이어서 확인한다

### 버튼 4 — 마켓 수정업로드 (MARKET)

- [ ] **MARKET-01**: 생성 완료분을 `market_update` 로 스마트스토어에 반영한다
- [ ] **MARKET-02**: **1건 먼저 반영하고 스토어에서 육안 확인**한 뒤에야 나머지가 실행된다 (상하단 안내이미지 되돌림 모순 검증 게이트)
- [ ] **MARKET-03**: 반영 전 원본 상세 HTML 을 보관한다

### 버튼 5 — 쿠팡 복사 (CP)

- [ ] **CP-01**: 버튼 하나로 prep→resolve→build→ship→gate→apply 전공정을 돌린다
- [ ] **CP-02**: `apply --commit` 만 따로 확인받는다
- [ ] **CP-03**: 기존 게이트(주문 3회 이상 + 쿠팡보정 가중마진 20%)를 그대로 유지한다 — 유입만 있는 상품은 올리지 않는다
- [ ] **CP-04**: 중복 복사 방지는 기존 `gate` 방식(쿠팡 그룹 실물을 매번 읽어 타오바오상품번호로 대조)을 그대로 쓴다

### 버튼 6 — 썸네일 교체 (THUMB)

- [ ] **THUMB-01**: 규칙②(노출 100+ & CTR<1%) 대상을 판정해 보여준다
- [ ] **THUMB-02**: 기존 `bulsaja-thumbnail` 스킬로 실행한다
- [ ] **THUMB-03**: 접수 전 예상 크레딧을 보고한다

---

## v2 Requirements

- **TRAFFIC-01**: 스마트스토어 통계를 유입 소스로 연동한다 (광고 안 도는 자연유입 상품이 보이게)
- **TRAFFIC-02**: 불사자 `traffic_analytics` 값의 의미를 검증하고, 믿을 만하면 유입 소스로 승격한다
- **AUTO-01**: 미리보기를 보고 "전부 실행"만 누르는 2단계 자동화
- **AUTO-02**: 스케줄이 알아서 도는 3단계 자동화 (되돌리기 가능한 작업 한정)
- **AUTO-03**: 자동화 승인 게이트를 숫자로 정의한다 — "미리보기 대비 실제 실행 불일치율 0%를 N회차 연속"
- **CONV-01**: 작업 전후 구매완료 변화를 측정해 효과를 증명한다

## Out of Scope

| Feature | Reason |
|---------|--------|
| 인증·로그인·권한 | 나 혼자 로컬. 대신 SAFE-01~03 으로 localhost 공격면만 막는다 |
| 호스팅·외부 접속 | 맥북 로컬 단독 |
| 수강생·직원 배포 | 계정 분리·자격증명 격리가 통째로 필요해져 프로젝트가 배로 커진다 |
| 기존 CLI 로직 재작성 | 실측으로 쌓은 함정 방어가 통째로 날아간다. 웹앱은 래퍼다 |
| 태스크 큐 (Celery/RQ/Redis) | run-dir 체크포인트와 작업 진실이 둘이 된다 — "로컬 대장 금지"와 같은 실수 |
| `--workers N>1` | 작업 레지스트리와 스트림 구독자가 프로세스별로 갈라져 "진행 로그가 안 뜬다"가 간헐적으로 난다 |
| 중복방지용 로컬 대장 신설 | 서버 플래그가 정본. 단 STATE-04 실측 결과에 따라 보완 인덱스는 예외 |
| npm 빌드 체인 (React/Vite/Tailwind) | 1인 로컬 도구에 과하다. 빌드 단계 0 으로 간다 |
| 서버사이드 페이징·가상 스크롤 | 작업 모수가 주당 ~120행이다. 필요 없다 |
| 비전 모델로 번역 여부 판정 | `imageTranslated` 플래그로 공짜로 된다 |
| 배너 애매 건의 사람 판단 큐 | 애매하면 상품을 스킵한다. 큐를 만들면 안 본다 |

---

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| ENG-01 | Phase 1 | Complete |
| ENG-02 | Phase 1 | Pending |
| ENG-03 | Phase 1 | Pending |
| ENG-04 | Phase 2 | Pending |
| ENG-05 | Phase 2 | Pending |
| ENG-06 | Phase 2 | Pending |
| ENG-07 | Phase 1 | Complete |
| ENG-08 | Phase 3 | Pending |
| SAFE-01 | Phase 1 | Complete |
| SAFE-02 | Phase 1 | Complete |
| SAFE-03 | Phase 1 | Complete |
| SAFE-04 | Phase 2 | Pending |
| SAFE-05 | Phase 2 | Pending |
| SAFE-06 | Phase 2 | Pending |
| SAFE-07 | Phase 2 | Pending |
| FLOW-01 | Phase 1 | Pending |
| FLOW-02 | Phase 1 | Complete |
| FLOW-03 | Phase 2 | Pending |
| FLOW-04 | Phase 1 | Pending |
| FLOW-05 | Phase 1 | Complete |
| FLOW-06 | Phase 2 | Pending |
| FLOW-07 | Phase 2 | Pending |
| BOARD-01 | Phase 1 | Complete |
| BOARD-02 | Phase 1 | Complete |
| BOARD-03 | Phase 1 | Pending |
| BOARD-04 | Phase 1 | Pending |
| BOARD-05 | Phase 2 | Pending |
| BOARD-06 | Phase 2 | Pending |
| BID-01 | Phase 1 | Pending |
| BID-02 | Phase 1 | Pending |
| BID-03 | Phase 1 | Pending |
| BID-04 | Phase 1 | Pending |
| PRUNE-01 | Phase 2 | Pending |
| PRUNE-02 | Phase 2 | Pending |
| PRUNE-03 | Phase 2 | Pending |
| JOIN-01 | Phase 3 | Pending |
| JOIN-02 | Phase 3 | Pending |
| JOIN-03 | Phase 3 | Pending |
| JOIN-04 | Phase 3 | Pending |
| STATE-01 | Phase 3 | Pending |
| STATE-02 | Phase 3 | Pending |
| STATE-03 | Phase 3 | Pending |
| STATE-04 | Phase 3 | Pending |
| STATE-05 | Phase 3 | Pending |
| BANNER-01 | Phase 4 | Pending |
| BANNER-02 | Phase 4 | Pending |
| BANNER-03 | Phase 4 | Pending |
| BANNER-04 | Phase 4 | Pending |
| BANNER-05 | Phase 4 | Pending |
| DETAIL-01 | Phase 5 | Pending |
| DETAIL-02 | Phase 5 | Pending |
| DETAIL-03 | Phase 5 | Pending |
| DETAIL-04 | Phase 5 | Pending |
| DETAIL-05 | Phase 5 | Pending |
| DETAIL-06 | Phase 5 | Pending |
| DETAIL-07 | Phase 5 | Pending |
| MARKET-01 | Phase 6 | Pending |
| MARKET-02 | Phase 6 | Pending |
| MARKET-03 | Phase 6 | Pending |
| CP-01 | Phase 7 | Pending |
| CP-02 | Phase 7 | Pending |
| CP-03 | Phase 7 | Pending |
| CP-04 | Phase 7 | Pending |
| THUMB-01 | Phase 7 | Pending |
| THUMB-02 | Phase 7 | Pending |
| THUMB-03 | Phase 7 | Pending |

**Coverage:**
- v1 requirements: 66 total
- Mapped to phases: 66
- Unmapped: 0 ✅

**Phase 요약:**

| Phase | 이름 | 요구사항 수 |
|-------|------|------------|
| 1 | 첫 왕복 — 보드 + 입찰가 인상 버튼 | 19 |
| 2 | 되돌릴 수 없는 쓰기 — 꺼진 소재 정리 | 15 |
| 3 | 작업 대상 확정 — 엔티티 해소 + 상세 상태 판정 | 10 |
| 4 | 홍보배너 식별 | 5 |
| 5 | 상세페이지 작업 버튼 ★ Core Value | 7 |
| 6 | 마켓 수정업로드 | 3 |
| 7 | 남은 버튼 — 썸네일 교체 / 쿠팡 복사 | 7 |

---
*Requirements defined: 2026-09-19*
