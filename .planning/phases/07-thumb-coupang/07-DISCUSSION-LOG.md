# Phase 7: 남은 버튼 — 썸네일 교체 / 쿠팡 복사 - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-29
**Phase:** 07-남은 버튼 — 썸네일 교체 / 쿠팡 복사
**Mode:** `--auto` (용팀장 부재 — 추천안 자동 선택, 단일 패스, auto_advance 없음)
**Areas discussed:** Phase 2 이월 처리 · 썸네일 대상 · 썸네일 실행 경로 · 썸네일 스토어 반영 · 쿠팡 전공정 체인 · 쿠팡 커밋 확인·상한 · 쿠팡 게이트·후보 범위 · 순서·병렬

[--auto] Selected all gray areas.
[--auto] Todos folded (score ≥ 0.4): job-reap-depends-on-polling (0.4), 429-group-stage-silent-completion (0.6 — 원칙만 쿠팡 gate 에 적용)

---

## Phase 2 이월 처리

| Option | Description | Selected |
|--------|-------------|----------|
| Phase 2 먼저 | 안전 계약 전체 완성 뒤 쿠팡 트랙 | |
| Phase 5/6 패턴 재사용 + commit 영구 사람 체크포인트 | 버튼 로컬 안전장치만, Phase 2 요구는 완료 표시 안 함 | ✓ |

**Choice:** [auto] 추천안 (D-01)

## 썸네일 대상

| Option | Description | Selected |
|--------|-------------|----------|
| 이미 가공된 썸네일도 재생성 | 현황판 재작업 flag/레시피 모드 필요 | |
| 스킬 prep 기작업 판정 그대로 — 스킵 표시 | 실대상이 적을 수 있음 | ✓ |

**Choice:** [auto — 용팀장 확인 필요] (D-03). 그룹 단위 prep 묶기(D-04), 상한 20(D-02)

## 썸네일 실행 경로

| Option | Description | Selected |
|--------|-------------|----------|
| ⓐ 크레딧 0 까지 웹 · 이후 Claude 세션 인계 | 승인 기록 + 복사용 명령 + `--max-credits` 로 승인과 지출을 묶음 | ✓ |
| ⓑ 웹앱이 `claude -p` 헤드리스 구동 | 버튼 완결이지만 무인 크레딧 지출·팬아웃 미검증 | |

**Choice:** [auto — 용팀장 확인 필요] (D-05~D-07)

## 썸네일 스토어 반영

| Option | Description | Selected |
|--------|-------------|----------|
| Phase 6 마켓 버튼 재사용(부모 출처 추가) | 광고 중 상품이라 반영 안 하면 CTR 불변 | ✓ |
| 불사자 저장까지만 | Phase 6 범위 불변 | |

**Choice:** [auto — 용팀장 확인 필요] (D-08)

## 쿠팡 전공정 체인

| Option | Description | Selected |
|--------|-------------|----------|
| 미리보기 잡 1개가 6단계(apply 무커밋) 차례로 | 전 구간 읽기 전용 | ✓ |
| 단계별 버튼 | 클릭 6번 | |

**Choice:** [auto] (D-09, D-10)

## 쿠팡 커밋 확인·상한

| Option | Description | Selected |
|--------|-------------|----------|
| 다른 버튼 + 건수 타이핑 + 직전 gate 재조회 + 첫 10건/이후 20건 상한 + verify 자동 | PITFALLS §10 그대로 | ✓ |
| 일반 확인 모달 | 다른 버튼과 같은 습관으로 눌림 | |

**Choice:** [auto] (D-11~D-14)

## 쿠팡 게이트·후보 범위

| Option | Description | Selected |
|--------|-------------|----------|
| 게이트 기준 화면 변경 불가 · CLI 기본값 | CP-03 | ✓ |
| 상세작업 완료 필터 추가 | PROJECT.md 문구 | |
| 추가 필터 없음 | CP/SC 에 없는 조건 | ✓ |

**Choice:** D-15 [auto] · D-16 [auto — 용팀장 확인 필요] · D-17 [auto] gate 그룹 읽기 fail-closed

## 순서·병렬

**Choice:** [auto] 크레딧 0 작업 전부 선행 (D-18) · 두 트랙 병렬, 공유 레지스트리 편집은 한 플랜에 (D-19)

---

## Claude's Discretion

- 썸네일 run-dir 배치 · `web_approval.json` 스키마 · 인계 명령 문구
- 쿠팡 체인 구현 방식 · 주입구 JSON·종료코드(0/2/3/4/5 계약 준수)
- 표 레이아웃 재사용 정도 · review.html 링크 방식

## Deferred Ideas

- 웹 완결형 썸네일(`claude -p`) 스파이크 · 가공본 재작업 · 쿠팡 컷 완화 · sheet/models 웹 버튼 · 쿠팡 사고 감시 · Phase 2 공통 계약 · 썸네일 재생성 버튼
