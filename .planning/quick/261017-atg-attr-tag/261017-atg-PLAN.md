---
quick_id: 261017-atg
slug: attr-tag
type: quick
---
# 261017-atg 판매상품 속성·태그 입력 도구 (attr-tag)

## 목표
sold-lock 이 남기는 `~/python_work/data/sold-lock/<날짜>/new_locks.json`(마켓번호·판매자상품코드·스스상품번호) 상품에
스마트스토어 **속성**과 **공식 태그(태그사전 번호 포함)**를 커머스API로 넣는다. 판단(어떤 태그·속성 값)은 Claude 가 하고,
도구는 ① 판단 재료 수집 ② 판단 결과 검증·저장·확인 ③ 되돌리기를 맡는다.

## 실측 사실 (2026-10-17, 13-2 / 13265084103 시험 저장 성공)
- 조회 `GET /external/v2/products/channel-products/{채널상품번호}` → {originProduct, smartstoreChannelProduct}
- 저장 `PUT /external/v2/products/channel-products/{채널상품번호}` 에 **조회 응답 전체를 그대로 고쳐서** 보내면 200. 가격·재고·이름·상세 불변 확인.
- 태그: `originProduct.detailAttribute.seoInfo.sellerTags = [{code, text}]` (최대 10)
- 속성: `originProduct.detailAttribute.productAttributes = [{attributeSeq, attributeValueSeq}]` (범위형은 값/단위 필드가 다를 수 있음 → 이번엔 선택형·복수선택형만 지원, 범위형은 건너뛰고 기록)
- 카테고리 속성 `GET /external/v1/product-attributes/attributes?categoryId=` · 값 `GET /external/v1/product-attributes/attribute-values?categoryId=`
- 태그 사전 `GET /external/v2/tags/recommend-tags?keyword=` (접두 자동완성 — **text 가 정확히 일치하는 것만** 채택) · 제한 `GET /external/v2/tags/restricted-tags?tags=a,b,c` → [{tag, restricted}]. '뷔페·보온·워머·업소용' 같은 일반 단어가 restricted=True 였다.
- 커머스API 레이트리밋(GW.RATE_LIMIT) — 호출 간 ≥1초, 429/RATE_LIMIT 백오프.
- 키·토큰: `.claude/skills/sold-lock/scripts/commerce_orders.py` 의 키 로딩(`CommerceClient.load_stores`)·`issue_token` 재사용. 시크릿 출력·저장 금지.

## 산출물: `.claude/skills/attr-tag/` (SKILL.md + scripts/attr_tag.py + 테스트)
서브커맨드:
1. `prep --date YYYY-MM-DD [--input new_locks.json] [--market 13-2 --channel-no 123]`
   → run-dir `~/python_work/data/attr-tag/<날짜>/` 에 상품별 `prep_<마켓>_<번호>.json`:
   상품명, 카테고리ID·경로(가능하면), 옵션명 목록, 현재 태그(code 유무 표시), 현재 속성(이름=값으로 풀어서),
   **입력 가능 속성 목록(이름·유형·주요/부가·선택지 텍스트)**, 상세페이지 텍스트(HTML 태그 제거, 3000자 이내), 이미지 URL 몇 개.
   + `todo.json`(판단 대기 목록). 이미 처리된 상품(after 백업 존재)은 건너뜀(--force 로 재처리).
2. `apply --plan plan.json [--commit]`
   plan 형식: `[{"market":"13-2","channel_no":"…","tags":["호텔용품",…],"attributes":[{"name":"용도","values":["업소용"]}],"keep_existing_attributes":true}]`
   - 태그: 각 text 를 recommend-tags 로 정확일치 code 확인 → 없으면 제외(사유 기록) → restricted 제외 → 최대 10.
   - 속성: name/value 를 그 카테고리 선택지에 **정확히 있는 것만** seq 로 변환. 없으면 제외(사유). 복수선택형은 values 여러 개 허용, 선택형은 1개.
   - 기존 속성은 keep_existing 이면 같은 attributeSeq 만 교체, 나머지 보존.
   - dry-run(기본): 변경 전/후 diff 를 출력·`apply_dryrun.json` 기록, 쓰기 0.
   - --commit: 상품마다 `before_<마켓>_<번호>.json` 백업(이미 있으면 덮지 않음) → PUT → 재조회로 태그 code·속성 반영 확인 + 가격·재고·이름·상세 길이 불변 검사 → `after_…json`, `result.json` 누적. 한 상품 실패가 전체를 멈추지 않음.
3. `revert --market --channel-no [--commit]` — before 백업의 seoInfo.sellerTags·productAttributes 만 현재 상품에 되돌려 PUT(다른 필드는 현재값 유지).
4. 업무판 기록: commit 끝에 workspace.toml `sheets.work_board` '오늘' 탭에 1행(할 일 "⑥ 속성·태그 <날짜>", 업무# ⑥, 담당 Claude, 출처 자동, 메모 "상품 N · 태그 평균 t개 · 속성 a개 · 실패 f"). sold-lock 의 board 코드 재사용. 실패해도 본작업 유지.

## 범위 밖 (오케스트레이터 몫)
- 태그 후보(마누태그) Aside 수집 — 네이버 로그인 필요, 별도.
- 판단(plan 작성) 자동화 방식(claude -p 등) — 사용자와 논의 후.
- 실제 --commit 실행.

## 규칙
- Python, 한국어 주석, try-except. 네트워크 없는 단위테스트(태그 정확일치·제한 제외·10개 상한·속성 선택지 매핑·keep_existing 병합·불변 검사) 필수.
- 커밋 메시지 끝: Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
