---
phase: quick-261008-0qx
plan: 01
status: complete
subsystem: naver-sourcing-bench
tags: [sourcing, store-expansion, origin-filter, aside]
requires: [quick-261002-mbo]
provides: [bench store expansion, origin=China filter, expand command, origin command]
tech-stack:
  added: []
  patterns: [product_key(nv:<id>) dedupe, checkpoint stores key, DOM-first origin read]
key-files:
  created:
    - .claude/skills/naver-sourcing-bench/scripts/drivers/store.js
  modified:
    - .claude/skills/naver-sourcing-bench/scripts/rules.py
    - .claude/skills/naver-sourcing-bench/scripts/sheet_schema.py
    - .claude/skills/naver-sourcing-bench/scripts/sourcing_bench.py
    - .claude/skills/naver-sourcing-bench/scripts/drivers/options.js
    - .claude/skills/naver-sourcing-bench/scripts/test_rules.py
    - .claude/skills/naver-sourcing-bench/scripts/test_sheet_schema.py
    - .claude/skills/naver-sourcing-bench/scripts/test_cli.py
    - .claude/skills/naver-sourcing-bench/SKILL.md
    - .claude/skills/naver-sourcing-bench/evidence/probe-2026-10.md
decisions:
  - "brand.naver.com 스토어 목록은 st=REVIEW 여도 리뷰순이 아님 → 첫 500 미만에서 자르지 않고 정렬 후 500+ 필터"
  - "원산지는 PRELOADED_STATE 에 없음(originAreaInfo=null) → 상세 '상품정보' 칸 DOM 라벨 옆 칸에서 읽음"
  - "스토어 목록에 원산지 필드 없음 → 목록 단계 원산지 필터는 코드만 있고 실제로는 작동 안 함(상세에서 판정)"
  - "'상세설명참조' 는 국가 없는 안내문 → 미확인(계획 behavior 의 '제외' 예시와 NO_COUNTRY 규칙이 충돌, 규칙 쪽을 따름)"
  - "SEC_STORE 15→10 (실측 스토어당 3~6초)"
metrics:
  completed: 2026-10-08
  tests: "86 passed (기존 57 + 신규 29)"
---

# Quick 261008-0qx: bench 스토어 확장 + 원산지(중국만) 필터 Summary

bench 후보 하나가 올라갈 때마다 판매자 스토어(smartstore·brand.naver.com) 리뷰 500+ 상품을 같은 조건(원산지 중국 포함)으로 원 행 바로 뒤에 붙이고, 기존 행 소급용 `expand`·`origin --dry-run` 명령을 추가했다. 중복은 상품번호(`nv:<id>`) 기준.

## Commits

| Task | Commit | 내용 |
|---|---|---|
| 1 RED | 457d418 | rules/schema 테스트 |
| 1 GREEN | 011691a | store_base·product_key·store_products·store_filter·origin_verdict, bench_row status/origin_unknown |
| 2 RED | fda5b44 | CLI 테스트(확장 순서·스토어 1회·상품번호 중복·캡챠 재개·원산지·expand·origin·파서) |
| 2 GREEN | 0d83472 | store.js, options.js href·origin, _expand_rows/_fetch_stores, do_expand, do_origin_check, --no-expand |
| 3 | 226c79d | 실측 반영(원산지 DOM, brand 정렬, SEC_STORE), SKILL.md, evidence |

## 실측 결과 (Aside, 캡챠 0, 시트 쓰기 0)

- **스토어 목록 필드**: `id`(= 검색 `main/products/<id>` 번호와 동일 — 스토리행거 3942331141 일치), `productNo`(원상품번호, 다름 → 안 씀), `name`, `benefitsView.discountedSalePrice`(할인가 28,000 = 검색 가격), `salePrice`(정가 34,000), `reviewAmount.totalReviewCount`, `category.wholeCategoryName`, `channelProductDisplayStatusType`. **원산지 필드 없음**.
- **brand.naver.com**: 같은 경로·같은 PRELOADED 구조로 **지원**. 단 `st=REVIEW` 인데 리뷰순 아님(진심감성 26, 3, 1197, 650 …) → 정렬 후 필터로 수정. 진심감성 2/12, 네이쳐리빙 60/80 건 500+.
- **원산지 위치**: PRELOADED `product.originAreaInfo` = null. 상세 상단 '상품정보' `<li><div>원산지</div><div>중국산(…)</div></li>` 에서 읽음. 실측 6건: 중국산 4건 → 중국, `국산(경기도 광주시)` → 제외, `상세설명에 표시` → 미확인.
- **href**: `main/products/<id>` → `smartstore.naver.com/piachang/…`, `brand.naver.com/natureliving/…` 등 정상 반환.
- 소요: 스토어당 3~6초.

## Deviations from Plan

1. **[Rule 1 - Bug] brand 목록 정렬** — 계획은 "리뷰 내림차순이라 500 미만에서 끊음". brand 에선 0건이 됨 → 정렬 후 500+ 필터. (226c79d)
2. **[Rule 1 - Bug] 원산지 읽기 순서** — 계획은 PRELOADED 우선. 실측상 null 이라 DOM 라벨 → 본문 텍스트 → PRELOADED 순으로 변경, 비면 0.7초×3 재시도. (226c79d)
3. **origin_verdict("상세설명참조")** — behavior 목록에선 "제외" 예시였지만 같은 계획의 NO_COUNTRY 규칙(상세·참조 → 미확인)과 충돌. D-ORIGIN "못 읽으면 제외하지 말 것" 에 맞춰 미확인으로 판정·테스트.
4. SEC_STORE 15 → 10 (실측 반영).

## 오케스트레이터 참고 (위험)

- 리뷰 500+ 가 많은 브랜드 스토어(네이쳐리빙 60건)는 확장 후보마다 상세를 열어 옵션·원산지를 읽는다 → 스토어 하나에 수 분~수십 분. `expand --all` 전에 `--dry-run` 으로 규모 확인 권장(dry-run 도 Aside 는 돌고 체크포인트는 남아 본 실행이 이어서 씀). 스토어당 상한이 필요하면 별도 결정.
- 검색 결과 리뷰수와 스토어 목록 리뷰수가 다를 수 있다(진심감성 13658084817: 2,546 vs 3, 그룹 합산 추정). 확장 판정은 스토어 목록 값 기준.
- 소급(`expand`)·원산지 삭제(`origin` without --dry-run)는 실행하지 않았다.

## Known Stubs

- store.js 의 `origin` 매핑(`originAreaInfo`)은 실측상 항상 "" — 목록 단계 원산지 사전필터는 현재 작동하지 않고 상세 단계에서 판정한다(의도, evidence 기록).

## Self-Check: PASSED

- 파일: store.js·SKILL.md·evidence 존재, `category/ALL?st=REVIEW`·`def do_origin_check` grep 확인
- 커밋: 457d418, 011691a, fda5b44, 0d83472, 226c79d 존재
- pytest 86 passed
