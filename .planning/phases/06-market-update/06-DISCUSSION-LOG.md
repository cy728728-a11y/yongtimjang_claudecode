# Phase 6: 마켓 수정업로드 - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-26
**Phase:** 06-마켓 수정업로드
**Mode:** `--auto` (용팀장 부재 — 전 항목 추천안 자동 선택, single pass)
**Areas discussed:** 대상 출처, 원본 백업 시점, 복원 범위, 쓰기 경로·결과 확인, 육안 게이트 빈도, 게이트 화면·실패 처리, 규모 상한

[--auto] Selected all gray areas. Todo 매칭 0건.

---

## 대상 출처

| Option | Description | Selected |
|--------|-------------|----------|
| 상세 잡 완료분 | Phase 5 detail_status.json `완료` 만, 부모 잡 체인 | ✓ |
| 보드 임의 선택 | 어떤 상품이든 반영 | |

[auto] 대상 — Q: "무엇을 반영 대상으로?" → Selected: "상세 잡 완료분" (recommended)

## 원본 백업 시점

| Option | Description | Selected |
|--------|-------------|----------|
| AI 접수 직전 + 마켓 반영 직전 둘 다(복원 기준은 전자) | detail_batch `--backup-out` 주입구, 05-06 전 머지 | ✓ |
| 마켓 반영 직전만 | 이미 AI 가 덮은 뒤라 원본 아님 | |
| 스마트스토어 원문(커머스API) | 맥북 IP 허용목록 밖 — 불가 | |

[auto] 백업 — Q: "원본 HTML 을 언제 뜨나?" → Selected: "둘 다, 복원은 AI 직전" (recommended) · **용팀장 확인 필요**(Phase 5 실행 순서 변경)

## 복원 범위

| Option | Description | Selected |
|--------|-------------|----------|
| CLI 서브커맨드만 | detail_apply → market_update, 미리보기까지 크레딧 0 검증 | ✓ |
| 웹 버튼까지 | | |
| 이번엔 안 함 | Pitfall 10 위반 | |

[auto] 복원 — Q: "restore 를 이 페이즈에?" → Selected: "CLI 만" (recommended)

## 쓰기 경로·결과 확인

| Option | Description | Selected |
|--------|-------------|----------|
| 새 CLI market_update.py + upload_tasks 폴링, exit 3=대기 미완 | Phase 5 계약 재사용 | ✓ |
| 접수 응답만 믿기 | 안전규칙 ⑤ 위반 | |

[auto] 쓰기 — Q: "반영 성공을 무엇으로 판정?" → Selected: "upload_tasks 폴링" (recommended)

## 육안 게이트 빈도

| Option | Description | Selected |
|--------|-------------|----------|
| 1회성(모순 판명용) | 판정 기록 후 강제 1건 정지 해제 | ✓ |
| 매 실행 첫 1건 정지 | 안전하지만 매번 사람 큐 | |

[auto] 게이트 — Q: "첫 1건 정지를 매번?" → Selected: "1회성" (recommended) · **용팀장 확인 필요**(SC-2 해석)

## 게이트 화면·실패 처리

| Option | Description | Selected |
|--------|-------------|----------|
| 3항목 체크(본문·상하단·기타필드) + 정상/이상 버튼, 이상이면 멈춤+복원 안내+contradiction 기록 | | ✓ |
| 상하단만 확인 | market_update 가 다른 필드도 미는 위험 놓침 | |

[auto] 게이트 화면 — Q: "무엇을 확인받나?" → Selected: "3항목" (recommended)

## 규모 상한

| Option | Description | Selected |
|--------|-------------|----------|
| 설정값 market_update_max_items 기본 20 | | ✓ |
| 상한 없음 | | |

[auto] 상한 — Q: "게이트 후 1회 반영 상한?" → Selected: "기본 20" (recommended)

## Claude's Discretion

- market_update.py 내부 구조·폴링 기본값·upload_tasks 매칭 방법
- 미리보기 표 컬럼, market_gate 스키마, 게이트 패널 문구, 스토어 링크 조립, run-dir 배치

## Deferred Ideas

- 웹 복원 버튼 · 스토어 HTML 자동 대조 · 매 실행 1건 정지 · 다른 마켓 · 실패분 재시도 버튼 · 백업 없는 상품 원본 복구 수단
