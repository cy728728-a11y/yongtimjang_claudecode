# Phase 5: 상세페이지 작업 버튼 ★ Core Value - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-25
**Phase:** 05-core-value
**Mode:** `--auto` (용팀장 부재 — 모든 질문에 추천안 자동 선택, single pass)
**Areas discussed:** 새 회차 배너 판정 기본값, 상세 입력 관문, 검수 화면 재확인 결함, 스킵 상품 처리, 대상 범위, 10장 초과 처리, 기작업 스킵 규칙, 견적·승인, 접수/폴링 분리, 타임아웃·실패 처리

`[--auto] Selected all gray areas.`
`[auto] Todo 429-group-stage (score 0.6) — auto 규칙상 fold 대상이나 2026-09-21 용팀장 결정("기록만")이 우선 → not folded.`

---

## 새 회차 배너 판정 기본값 (D-23 이 넘긴 질문)

| Option | Description | Selected |
|--------|-------------|----------|
| ⓐ 사람 확인 + 비전 2차 off | 검수 화면 약 11분 · 미탐·누락 둘 다 막음 · 토큰 0 | ✓ (용팀장 확인 필요) |
| ⓑ 어휘군 단독 | 사람 0분 · 현 라벨 기준 미탐 8 | |
| ⓒ 비전 2차 on + 기계만 | 제품 이미지 약 14% 누락 · 회차당 약 $2 | |

**Choice:** [auto] ⓐ (recommended)

## 상세 입력 관문

| Option | Description | Selected |
|--------|-------------|----------|
| 상품별 사람 확인 + 라벨 우선 | `게이트통과` 대신 확인시각 ≥ 산출물 생성시각 | ✓ (용팀장 확인 필요) |
| 전역 게이트 유지 | 게이트 false 라 입력 영원히 0건 | |

## 검수 화면 `확인함` 재클릭 결함

| Option | Description | Selected |
|--------|-------------|----------|
| 최소 수정으로 이 페이즈에서 고침 | D-01/D-02 전제조건 | ✓ |
| Deferred 유지 | 재스캔 상품이 영원히 접수 불가 | |

## 배너 스킵 상품

| Option | Description | Selected |
|--------|-------------|----------|
| 스킵 유지 · 배지만 | 규칙 재구현 없음 | ✓ |
| 라벨 기준 재계산 | S-1 위반 · MVP 밖 | |

## 대상 범위

| Option | Description | Selected |
|--------|-------------|----------|
| 🔴 기본 · 🟡 수동 허용 | Core Value 문장 둘 다 포함 | ✓ |
| 🔴 만 | | |

## 10장 초과 제품 이미지

| Option | Description | Selected |
|--------|-------------|----------|
| 앞 10장 + 누락 장수 표시 | MVP · 크레딧 실측 불필요 | ✓ (용팀장 확인 필요) |
| 분할 생성(2회 접수) | 덮어쓰기 여부 미확인 · 실측 크레딧 필요 | |
| 균등 샘플링 | 누락은 똑같이 발생 | |

## 기작업 스킵 (SC-3)

| Option | Description | Selected |
|--------|-------------|----------|
| 태그 OR aiImageGenerated 절대조건 + 첫 5건 뒤 실측, 안 찍히면 태그 쓰기 폴백 | state.py 와 같은 규칙 | ✓ |
| 로컬 대장 | L-05 위반 | |

## 견적·승인

| Option | Description | Selected |
|--------|-------------|----------|
| `--estimate-only` 견적 잡 → 버튼 = 승인 · 금액 상한 없음 | Phase 1 미리보기→실행 틀 재사용 | ✓ (용팀장 확인 필요 — 대량 상한 기준) |
| 금액 상한 초과 시 추가 확인 | | |

## 접수/폴링 분리

| Option | Description | Selected |
|--------|-------------|----------|
| 한 잡이 접수+폴링 · 복구는 `--poll-only` 잡 | CLI 체크포인트가 분리 보장 | ✓ |
| 접수 잡 / 폴링 잡 항상 분리 | 잡 수 증가 | |

## 타임아웃·실패

| Option | Description | Selected |
|--------|-------------|----------|
| 타임아웃=미완(이어서 확인만) · 실패 재접수는 MVP 제외 | 이중 지불 차단 | ✓ |
| 재접수 버튼 제공 | 이중 지불 위험 | |

## Claude's Discretion

run-dir 레이아웃 · 표 레이아웃 · 생성 이미지 썸네일 · 종료코드 번호 · 견적 유효시간

## Deferred Ideas

분할 생성 · 실패 재접수 버튼 · 워터마크 제거 · 라벨 기준 스킵 재계산 · 대량 금액 상한 · D-23 이월(Q2·v4·게이트 문구)
