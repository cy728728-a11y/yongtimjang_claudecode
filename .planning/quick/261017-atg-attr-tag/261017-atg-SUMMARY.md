---
quick_id: 261017-atg
slug: attr-tag
status: complete
completed: 2026-10-17
key-files:
  created:
    - .claude/skills/attr-tag/SKILL.md
    - .claude/skills/attr-tag/scripts/attr_tag.py
    - .claude/skills/attr-tag/scripts/attr_tag_rules.py
    - .claude/skills/attr-tag/scripts/test_attr_tag.py
commits:
  - 8850738 feat(261017-atg): attr-tag prep/apply/revert 도구 + 단위테스트
  - d9df162 docs(261017-atg): attr-tag SKILL.md
---

# 261017-atg attr-tag Summary

판매상품(new_locks.json)에 공식 태그(사전 code)와 카테고리 속성을 커머스API 로 넣는 prep/apply/revert 도구를 만들었다. 판단은 Claude 가 plan.json 으로 하고, 도구는 검증·백업·저장·재조회 확인·되돌리기를 맡는다.

## 한 일
- `attr_tag_rules.py`(순수 로직): HTML→텍스트, 속성 표 정리, 태그 검증(정확일치→제한 제외→10개), 속성 매핑(선택형 1 / 복수선택형 max, 범위형 제외), keep_existing 병합, 본문 조립, diff, 불변 검사, 반영 확인, 업무판 메모.
- `attr_tag.py`(CLI): `CommerceApi`(sold-lock `CommerceClient.load_stores`·`issue_token` 재사용, 1초 간격, 429/5xx/RATE_LIMIT 백오프, 오류문 redact), `prep`·`apply`·`revert`, 업무판 1행(sold-lock 과 같은 행 형식).
- 테스트 20개(가짜 API) + 기존 sold-lock 28개 모두 통과.
- 스모크(읽기 전용): 13-2 / 13265084103 prep 성공 — 카테고리 경로, 태그 5개(모두 code 있음), 속성 '용도=업소용', 입력 가능 속성 23개, 옵션 53개, 상세 1152자. 결과는 scratchpad 의 별도 data_root 에 썼고 실제 run-dir 엔 안 썼다. 산출물에 시크릿 없음 확인.

## 실측으로 확정한 API 모양
- attributes: `attributeSeq · attributeName · attributeClassificationType(SINGLE_SELECT|MULTI_SELECT|RANGE) · attributeTypeCodeName(주요/부가) · attributeValueMaxMatchingCount`(0=무제한)
- attribute-values: `attributeSeq · attributeValueSeq · minAttributeValue(선택지 텍스트) · [minAttributeValueUnitCode, maxAttributeValue…]`
- recommend-tags → `[{code, text}]`, restricted-tags → `[{tag, restricted}]`, categories/{id} → `wholeCategoryName`

## Deviations
- [Rule 2] plan 의 태그가 전부 탈락하면 기존 태그를 지우지 않고 유지(빈 태그로 덮는 사고 방지).
- [Rule 2] 제한 여부 조회가 실패하면 태그를 하나도 넣지 않음(제한 태그는 저장 400 원인).
- [Rule 2] 불변 검사에 상태·카테고리·옵션 수/가격도 넣었다(플랜은 가격·재고·이름·상세 길이).
- [Rule 1] revert 때 code 없는 평문 태그에 `code: null` 을 만들어 보내지 않도록 원본 키만 복사.
- 변경 없는 상품은 commit 에서 PUT 을 생략하되 after 를 남겨 prep 가 다시 집지 않게 했다.
- apply run-dir 날짜: `--date` → plan 이 `attr-tag/<날짜>/` 안이면 그 날짜 → 오늘(KST).
- 처리 여부(after 존재)는 모든 날짜 run-dir 을 본다 — 다른 날 다시 팔린 상품을 이중 처리하지 않게.

## 하지 않은 것 (제약)
- 실제 PUT·--commit·시트 쓰기 없음. apply dry-run 도 실호출로는 안 돌렸다(스모크는 prep 만 허용됨).

## Known Stubs
없음.

## Self-Check: PASSED
- 파일 4개 존재, 커밋 8850738·d9df162 존재.
