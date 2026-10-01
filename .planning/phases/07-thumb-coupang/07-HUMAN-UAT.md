---
status: partial
phase: 07-thumb-coupang
source: [07-VERIFICATION.md]
started: 2026-10-01T10:00:00+09:00
updated: 2026-10-01T10:00:00+09:00
---

<!-- uat-auto: done -->

## Current Test

[다음 쿠팡 회차 대기 — 지금은 대상 0건]

## Tests

### 1. 쿠팡 첫 실복사 — verify 중복 0 실측
expected: 미리보기 통과 1건 이상 → 화면 건수 타이핑 → 복사 1회 → 결과 표 재조회·verify '중복 0'(녹색) · copied.jsonl 생성
result: [pending]

why_human: 되돌릴 수 없는 쓰기(사람 몫 ②). 2026-10-01 미리보기는 통과 0건(기존 쿠팡 사본 2건을 gate 가 차단)이라 돌릴 대상이 없다.

이미 닫힌 것: 웹 경로 스모크(07-05) · 건수 불일치 409 · gate 계보 대조 실데이터 2건 차단(260930-c4) · 0건 정상 종료(06d2c45) · 테스트 쿠팡 97 / 웹앱 941 그린.
언제: 주문시트 실적이 쌓여 새 미리보기에 후보가 생길 때.
