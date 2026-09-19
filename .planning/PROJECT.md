# 셀러 관제탑 (Seller Control Tower)

## What This Is

네이버 검색광고 성과 판정과 불사자 상품 가공을 한 화면에서 잇는 **로컬 웹 관제탑**이다.
광고 6규칙 판정 결과를 상품 단위 보드로 띄우고, 거기서 상세페이지 작업·입찰가 인상·꺼진 소재 정리·썸네일 교체·쿠팡 복사를 각각 버튼으로 실행한다.
사용자는 용팀장 본인 한 명, 맥북 로컬에서만 돈다.

## Core Value

**유입이나 판매가 있는데 상세페이지가 중국어 원본·단순번역인 상품을, 중복 작업 없이 한 화면에서 골라 고치고 반영하는 것.**

이게 안 되면 나머지 버튼이 다 돌아도 이 프로젝트는 실패다.

## Requirements

### Validated

<!-- 기존 CLI 로 이미 돌고 있고 실측으로 검증된 것. 웹앱은 이걸 감싸기만 한다. -->

- ✓ 네이버 광고 4계정 수집 + 6규칙 판정 (`naver-ads-weekly`: collect/ads_rules) — existing
- ✓ 입찰가 인상 dry-run↔commit↔revert 백업 복원 (`bids.py`) — existing
- ✓ 꺼진 소재(`AD_ABNORMAL_INTERLOCK`) 삭제, 백업 선행 (`prune.py`) — existing
- ✓ 구매완료 기준 보고서·시트 원장 (`reports.py`/`sheets_out.py`, 장바구니 혼동 방어) — existing
- ✓ 불사자 AI 상세페이지 배치 생성: 접수→폴링→자동반영, 체크포인트 재개 (`detail_batch.py`) — existing
- ✓ 상세페이지 기작업 스킵 (서버 `aiImageGenerated`/`aiImageOutputCount` 기준, 로컬 대장 불필요) — existing
- ✓ 쿠팡 복사 중복 방지 (`gate` 가 매번 쿠팡 그룹 실물을 읽어 타오바오상품번호로 대조) — existing, 1차 파일럿 84건 검증
- ✓ 주문시트 12탭 실적·실마진·실배송비 집계 (`coupang-candidates` prep) — existing
- ✓ AI 썸네일 생성·교체 (`bulsaja-thumbnail`) — existing

### Active

<!-- 이번 마일스톤에서 새로 만드는 것. 전부 가설이다. -->

**대상 선별**
- [ ] 광고 규칙 ⑤(구매완료 발생) → "판매된 상품" 목록을 뽑는다
- [ ] 광고 규칙 ③(클릭 20+ & 구매완료 0) → "유입은 있는데 안 팔리는 상품" 목록을 뽑는다
- [ ] 광고 소재 ↔ 불사자 상품을 연결한다 (현재 두 데이터가 이어져 있지 않음)
- [ ] 정지된 소재의 과거 클릭을 유입으로 오독하지 않는다 (물갈이 사이클 부산물 방어)

**상태 판정**
- [ ] `imageTranslated` × `aiImageGenerated` 조합으로 3단계 상태를 판정한다
      (🔴 중국어 원본 / 🟡 단순번역만 / ⚪ AI 가공 완료)
- [ ] 보드에서 상태별·우선순위별로 정렬·필터해서 본다

**상세페이지 작업 (본론)**
- [ ] AI 상세 생성의 입력 소스를 `uploadDetailContents.renderContent` 의 기존 상세 이미지로 교체한다
      (현재는 썸네일 + 옵션 이미지를 쓴다)
- [ ] 기존 상세 이미지에서 중국 판매사 홍보배너를 제거하고 제품 이미지만 입력으로 넣는다
- [ ] 생성 장수를 기존 상세 길이에 비례시킨다 (`min(제품이미지 수, 10)`, 하한 2)
- [ ] 생성 완료분을 `market_update` 로 즉시 스마트스토어에 수정업로드한다

**관제탑 화면**
- [ ] 상품 단위 보드: 한 줄에 상품명·계정·광고성과·상세상태·작업이력이 보인다
- [ ] 실행 버튼 5종을 각각 따로 누른다 — 상세페이지 / 입찰가 인상 / 꺼진 소재 정리 / 썸네일 교체 / 쿠팡 복사
- [ ] 모든 쓰기 버튼은 미리보기(dry-run) → 확인 → 실행 2단으로 간다
- [ ] 접수 전 예상 크레딧을 보고한다
- [ ] 광고 계정은 설정 파일로만 늘어난다 — 화면·코드에 계정 수를 박지 않는다

**쿠팡 복사**
- [ ] 상세작업 끝난 상품 중 **판매 실적 있는 것만** 쿠팡 그룹으로 복사한다 (기존 게이트 유지)
- [ ] 버튼 하나로 prep→resolve→build→ship→gate→apply 전공정을 돌리고, `apply --commit` 만 재확인받는다

### Out of Scope

- **스마트스토어 유입 통계 연동** — 1차는 광고 데이터로 대리한다. 광고 안 도는 자연유입 상품이 안 보이는 건 감수하고, 다음 마일스톤으로 미룬다
- **인증·로그인·권한** — 나 혼자 로컬에서만 쓴다. 호스팅도 안 한다
- **수강생·직원 배포** — 계정 분리와 자격증명 격리가 통째로 필요해져서 프로젝트가 배로 커진다
- **무인 스케줄 자동화** — 크레딧·마켓 쓰기 사고가 감시 없이 나간다. 버튼은 사람이 누른다
- **기존 CLI 로직 재작성** — 실측으로 쌓은 함정 방어(장바구니 혼동·그룹입찰 함정·배송비 P75)가 통째로 날아간다. 웹앱은 래퍼다
- **중복방지용 로컬 대장 신설** — 서버 플래그가 이미 정본이다. 대장을 새로 만들면 진실이 둘이 되어 어긋난다
- **전환율 상승 측정** — 완료 기준은 "마찰이 낮아 계속 돌리게 되는가"다. 전환 측정은 나중 문제
- **쿠팡에 유입만 있는 상품 올리기** — 쿠팡은 취소·반품 잦으면 계정정지다. 팔린 것만 올린다

## Context

**기존 자산 (이 프로젝트는 브라운필드다)**

| 자산 | 위치 | 성숙도 |
|---|---|---|
| 광고 자동화 | `.claude/skills/naver-ads-weekly/` | 높음 — 6규칙·입찰·정리·원장·보고서에 테스트까지 |
| 상세페이지 배치 | `.claude/skills/bulsaja-detail-page/` | 높음 — 접수 검증·기작업 스킵·체크포인트 재개 |
| 쿠팡 후보 선별 | `.claude/skills/coupang-candidates/` | 높음 — 6단계 파이프라인, 1차 파일럿 84건 완료 |
| 썸네일 생성 | `.claude/skills/bulsaja-thumbnail/` | 중간 |
| 상세 리믹스 | `.claude/skills/bulsaja-detail-remix/` | 중간 — Fatkun 수동 단계 잔존 |

**이 프로젝트가 잇는 이음매**

광고 규칙 ③(클릭 20+ & 구매완료 0)의 "원인분석 리스트"가 곧 "유입은 되는데 안 팔리는 상품"이고,
그 원인 1순위가 상세페이지 미번역이다. 규칙 ⑤(구매완료 발생)가 "판매된 상품"이다.
지금은 광고 판정과 상세 작업 사이가 사람 눈으로 끊겨 있다. 웹앱이 그 이음매다.

**실측으로 확인한 데이터 구조 (2026-09-19, 용쌤 계정 `U01M2SKAHKZM6035K6PB1DZSCBB`)**

```jsonc
"uploadDetailContents": {
  "imageTranslated": false,        // 이미지 번역 여부 — 단순번역 판정 근거
  "renderContent": "<div><img src=...>...",  // 기존 상세페이지 = <img> 나열 HTML (이 상품 7장)
  // "aiImageGenerated"/"aiImageOutputCount"/"aiImageGeneratedAt" — AI 작업 흔적(이 상품은 없음)
}
"uploadDetail_page": { "top_image": ..., "bottom_image": ... }  // 마켓그룹 고정 배너 (별개!)
```

- 전체 수집상품 970,695건. 작업 대상 모수는 1단계에서 집계로 센다
- 상태 판정 3단계가 플래그 조합만으로 가능 — 비전 호출 0, 추가 API 콜 0 (workdata 는 어차피 조회한다)
- 불사자 MCP 프로필에 "유입수·상품 조회" 기능이 있다 — 2차 유입 소스 후보

**알려진 함정 (실측 기록)**

- `/stats` 의 `convAmt`·`ccnt` 는 장바구니 포함. 구매완료는 `AD_CONVERSION` 의 `purchase` 만
- `salesAmt` 는 매출이 아니라 광고비
- 그룹입찰 상품의 인상 출발점은 그룹 기본입찰가 — `bidAmt` 쓰면 올리려다 내린다
- `상세페이지있음` 필드는 작업 여부 기준이 못 된다 (원본 번역 이미지만 있어도 true)
- AI 상세는 `imageUrls` + `sectionCount` 를 **동시에** 보내야 요청 장수대로 나온다 (하나만 보내면 1장)
- 광고 연동끊김 대량정지는 고장이 아니라 물갈이 20일 사이클의 부산물 — 계속 나온다
- 불사자 계정이 둘이다 (용팀장 / 용쌤=부킹). 작업 전 프로필 확인 필수

## Constraints

- **배포**: 맥북 로컬 단독 실행 — 사용자 1명, 호스팅·인증 없음
- **아키텍처**: 웹앱은 기존 CLI 스크립트의 래퍼다. 검증된 로직·테스트·가드레일을 재작성하지 않는다
- **안전**: 모든 쓰기 작업은 dry-run 선행. 크레딧 소모 작업은 접수 전 견적 보고
- **진실의 원천**: 작업 완료 여부는 불사자 서버 플래그가 정본. 로컬 대장을 정본으로 삼지 않는다
- **확장성**: 광고 계정은 `~/.eroom/naver-ads.json` 에 항목 추가로만 늘어난다 (현재 4개 → 6개 예정)
- **언어**: 코드 주석 한국어, Python 기반, try-except 포함

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| 웹앱은 기존 CLI 를 감싸는 래퍼로 만든다 | 실측으로 쌓은 함정 방어(장바구니 혼동·그룹입찰·배송비 P75)를 통째로 잃지 않는다 | — Pending |
| 유입 판단을 네이버광고 데이터로 대리한다 | 연동 비용 0. 스마트스토어 통계는 다음 마일스톤 | — Pending |
| 상세 상태 판정을 `imageTranslated` 플래그로 한다 (비전 미사용) | 실측으로 필드 존재 확인. 비용 0, 추가 콜 0 | — Pending |
| AI 상세 입력을 기존 상세 이미지로 교체한다 (썸네일·옵션 제외) | 홍보배너 제거와 동적 장수 두 요구를 한 변경으로 푼다 | — Pending |
| 중복방지 대장을 새로 만들지 않는다 | 서버 플래그가 정본. 대장을 만들면 진실이 둘이 된다 | — Pending |
| 쿠팡 복사는 기존 게이트(주문 3회+마진 20%)를 유지한다 | 쿠팡은 취소·반품 잦으면 계정정지. 유입만 있는 상품은 올리지 않는다 | — Pending |
| 완료 기준을 전환율이 아니라 마찰로 잡는다 | 간편해야 지속적으로 돌린다. 안 쓰면 전환도 없다 | — Pending |
| 홍보배너 식별 방법은 리서치에서 결정한다 | 판매사마다 배너가 0~2장으로 다르다. 실물 샘플을 봐야 정한다 | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-09-19 after initialization*
