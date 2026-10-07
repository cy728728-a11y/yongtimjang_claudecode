# Quick Task 261008-0qx: bench 스토어 확장 — Context

**Gathered:** 2026-10-08
**Status:** Ready for planning

<domain>
## Task Boundary
naver-sourcing-bench `bench`: 후보 상품 하나를 시트에 올릴 때마다, 그 상품 판매자 스토어의 **전체 상품 중 리뷰 500개 이상**인 것을 훑어 같은 조건을 충족하는 상품도 후보로 추가하고 다음 상품으로 넘어간다.
</domain>

<decisions>
## Implementation Decisions (사용자 지시 · 잠금)
- 조건 = 기존 bench 조건 그대로: 리뷰 ≥500, 가격 ≥10,000원, 가격비교(카탈로그) 제외, 제외 마켓(rules.EXCLUDED_MALLS, 현재 한샘) 제외, 옵션 조합 15 초과 제외(rules.MAX_COMBOS=15), URL 중복 제외(시트 기존 행 포함).
- 순서: 원 상품 행 → 그 스토어 확장 행들 → 다음 원 상품.

### Claude's Discretion
- 확장 행 키워드(E열) = 원 키워드 그대로. 상태(X열)에 `스토어확장` 표기(옵션 못 읽으면 `스토어확장·옵션수동`). 카테고리 A~D 는 스토어 데이터의 wholeCategoryName 에서.
- 스토어는 한 실행·체크포인트당 1회만 확장(같은 스토어 상품이 여러 개 걸려도 재확장 X). 확장 행에서 다시 확장하지 않음(재귀 금지).
- 스토어 목록은 리뷰 많은순 1페이지(size=80)만 — 리뷰 내림차순이라 500 미만이 나오면 거기서 끊는다.
- 기존 시트 82행에 소급 적용할 명령도 제공(예 `expand --keyword K` / `expand --all`). 소급 실행은 오케스트레이터가 한다.
- `bench --no-expand` 로 끌 수 있게.
</decisions>

<specifics>
## 실측 (2026-10-08, Aside, 캡챠 0)
- URL: `https://smartstore.naver.com/<storeSlug>/category/ALL?st=REVIEW&dt=BIG_IMAGE&page=1&size=80` → 리뷰 많은순 정렬된 전체상품.
- 데이터: `window.__PRELOADED_STATE__.categoryProducts.simpleProducts[]` — 원소에 `id`, `name`(추정), `category.wholeCategoryName`("생활/건강>수납/정리용품>옷걸이>바지걸이"), `reviewAmount.totalReviewCount`, 가격 필드(salePrice/discountedSalePrice 등 — 실행자가 실측으로 확정), `channelProductDisplayStatusType`("ON" 만). 실측 예: piachang(스토리행거) 총 8개, 1위 리뷰 9,485.
- 상품 URL 은 `https://smartstore.naver.com/<storeSlug>/products/<id>` 로 만든다(norm_url 로 기존 `main/products/<id>` 형식과 중복 판정되는지 확인 — 다르면 product id 기준 중복 판정).
- storeSlug: 검색 결과 URL 은 `smartstore.naver.com/main/products/<id>` 라 슬러그가 없다. 상품 상세를 열면 `smartstore.naver.com/<slug>/products/<id>` 또는 `brand.naver.com/<slug>/products/<id>` 로 리다이렉트 → options 드라이버가 이미 상세를 여니 최종 location.href 를 같이 돌려주게 해서 슬러그를 얻는다. brand.naver.com 스토어도 같은 `/category/ALL?st=REVIEW` 경로인지 실측 필요(아니면 그 스토어는 건너뛰고 경고).
- 참고 프로브: storeprobe.reference.js, 기존 드라이버 패턴 drivers/options.js·common.js, 120초 벽 → aside_bridge.auto_chunk.
</specifics>

<canonical_refs>
- .claude/skills/naver-sourcing-bench/SKILL.md
- .planning/quick/261002-mbo-bench-option-auto-fill/ (옵션 자동수집 선행 작업)
</canonical_refs>
