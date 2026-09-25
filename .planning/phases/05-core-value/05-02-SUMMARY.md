---
phase: 05-core-value
plan: 02
subsystem: webapp/banner
tags: [banner, gate, D-02, D-03, detail-input]
requires: []
provides:
  - "banner.상세입력목록 — D-02 상품 단위 관문 (05-03 견적 라우트가 소비)"
  - "banner_store.확인시각읽기 — {상품키: 확인시각 ISO}"
  - "검수 화면 '다시 확인' 버튼 + 낡은 확인 배지 숨김"
affects: [05-03, 05-05]
tech-stack:
  added: []
  patterns: ["fromisoformat 시각 비교 (오프셋 없는 값은 로컬로)", "키워드 인자 기본값 없음 = 구조 가드"]
key-files:
  created: []
  modified:
    - webapp/banner.py
    - webapp/banner_store.py
    - webapp/routes/banner.py
    - webapp/templates/banner_review.html
    - webapp/tests/test_banner.py
    - webapp/tests/test_routes_banner.py
decisions:
  - "상세입력목록은 기계 '제품이미지' 필드를 쓰지 않고 장 판정 + 라벨로 유효판정을 다시 투영한다 (D-23 ①)"
  - "생성시각 없는 옛 산출물은 화면 '확인함'을 존재 여부로 폴백 — 04 회차 화면이 통째로 미확인으로 뒤집히지 않게"
  - "게이트집계(전역 게이트)는 여전히 확인 집합을 받는다 — 전역 게이트 규칙 변경은 Deferred"
metrics:
  duration: "~20분"
  completed: 2026-09-25
  tasks: 2
  files: 6
---

# Phase 5 Plan 02: D-02 입력 관문 + D-03 다시 확인 Summary

상품 단위 관문 `banner.상세입력목록`(확인시각 ≥ 산출물 생성시각 · 라벨 우선 · 스킵/미판정/하한 차단 · URL 중복 제거 후 앞 10장 + 총수·잘림)과 검수 화면의 `다시 확인` 버튼·낡은 확인 배지 숨김을 추가했다. 크레딧 0, 네트워크 0.

## 완료 태스크

| Task | 내용 | 커밋 |
|------|------|------|
| 1 RED | 상세입력목록·확인시각읽기 실패 테스트 12개 | cb6a526 |
| 1 GREEN | `상세입력목록` + `확인시각읽기` (옛 `제품이미지목록` 불변) | e188349 |
| 2 RED | 다시확인 버튼·갱신·낡은확인 배지 테스트 3개 | 739eecc |
| 2 GREEN | `_확인유효` · `_화면투영` 시각 기반 확인됨 · 템플릿 `다시 확인` 버튼 | 9b36f22 |

## 검증

- `test_banner.py` + `test_routes_banner.py`: 79 passed
- `webapp/tests` 전체: 535 passed (트리 가드 `test_argv.py` 포함)
- `| safe` 개수 0 → 0 유지, `banner_vision2_max_calls` 미변경
- `grep requests|eroomlib|PIL` banner.py·banner_store.py: 0줄

## Deviations from Plan

**1. [Rule 2 - 정확성] aware/naive 시각 비교 가드 `banner._시각` 추가**
- **Found during:** Task 2 (라우트에 같은 비교를 붙이면서)
- **Issue:** `fromisoformat` 으로만 비교하면 오프셋 없는 옛 산출물 생성시각과 오프셋 달린 확인시각이 만나는 순간 TypeError. 현재 실데이터는 양쪽 다 오프셋이 있지만(`banner_scan.지금()`, `banner_store._now()` 확인) 옛 산출물 방어 필요.
- **Fix:** 오프셋 없는 값은 로컬 시각으로 읽는 `_시각` 헬퍼를 관문과 화면이 함께 쓴다(화면·관문 규칙 단일화). 화면 쪽은 못 읽으면 미확인(안전한 쪽).
- **Commit:** 9b36f22

**2. [TDD 참고] `test_다시확인_누르면_확인시각이_갱신된다` 는 RED 단계에서 이미 통과**
- `확인기록` 이 원래 `INSERT OR REPLACE` 라 서버 쪽은 수정이 필요 없었다(연구 §D-03 예고와 일치). 회귀 방지 테스트로 유지. 나머지 2개는 RED 에서 실패 확인.

## UI 자동 검증 (uat-verifier) — 오케스트레이터 대기

이 실행기는 에이전트를 띄울 수 없어 uat-verifier 는 **대기(pending)** 다. 조건:
- 사용자 서버(PID 41865, :8765)는 재시작·POST 금지 제약이 있었으므로, **격리 DB·격리 포트로 띄운 인스턴스**에서 확인할 것
- 확인 항목: ① `/banner/review` 에서 확인된 상품 줄에 `확인함` 배지 옆 `다시 확인` 버튼이 보이고 눌리면 200 + 줄 흐림 ② 산출물 생성시각보다 이른 확인은 배지 없이 `확인함` 버튼만 보임 ③ 에러 시 `#label-error` 표시
- 참고: 실운영 회차(2026-09-20, 산출물 2026-09-25T00:14)는 모든 확인이 산출물보다 앞서므로, 새 코드가 로드되면 **전 상품에서 `확인함` 배지가 사라지는 것이 정상**이다.

## Known Stubs

없음.

## Self-Check: PASSED

## uat-verifier 결과 (2026-09-25 · 05-02/03/04 통합 1회 · 오케스트레이터 실행)

- **판정: PASS** — 항목 ①~⑮ 전부 pass · P0~P2 없음 · P3 1건(배너 검수 스트립 figure 접근성 이름 — Phase 4 기존 마크업, 스캐너 오탐 가능)
- 격리 인스턴스(DB 복사본·별도 포트)만 사용 · 사용자 서버(:8765)·실 webapp.db·실 run-dir 미접촉 · 불사자 호출 0 · 크레딧 0 · 소스 변경 0
- 사람 몫: 심미만 — `~/.claude/uat/uat-artifacts/20260925-seller-control-tower/board-detail-result.png`, `banner-review.png`
