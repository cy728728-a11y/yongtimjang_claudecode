---
phase: 04-banner-detection
plan: 12
subsystem: banner-gate
tags: [banner, gate, 재판정, in-sample, d23, gap-closure, 불통과]
status: 완료 — 게이트 🔴 불통과 (누락률 13.70% > 10%). Phase 4 는 D-23(용팀장 결정)으로 불통과 상태 종료

requires:
  - phase: 04-banner-detection
    plan: 11
    provides: "재측정 산출물 banner_232c3bb3 · regate.py · 재검수 목록 §16-6"
provides:
  - "04-GATE §17 — 사람 재검수 후 게이트 재판정 · 세 시점 비교 · 2차가 한 일 · 이월 · D-23"
  - "04-CONTEXT D-23 — 불통과 상태 종료 결정 + Phase 5 로 넘기는 사실 3개"
  - "VALIDATION Sign-Off gate_passed false · 재측정 조건 3/4"
affects: [05-detail-button]

tech-stack:
  added: []
  patterns:
    - "게이트 숫자는 regate 계산값만 옮긴다 — 사람 헤더 숫자가 없으면 없다고 적는다"
    - "플랜 완료와 게이트 통과를 분리 표기 — ROADMAP [x] 옆에 '게이트 불통과 · 용팀장 결정으로 종료'"

key-files:
  created:
    - .planning/phases/04-banner-detection/04-12-SUMMARY.md
  modified:
    - .planning/phases/04-banner-detection/04-GATE.md
    - .planning/phases/04-banner-detection/04-VALIDATION.md
    - .planning/phases/04-banner-detection/04-CONTEXT.md
    - .planning/phases/04-banner-detection/.continue-here.md
    - .planning/ROADMAP.md
    - .planning/STATE.md
    - workspace.toml (git 비추적 — banner_vision2_max_calls 894 → 0)

decisions:
  - "D-23: Phase 4 를 게이트 불통과 상태로 종료 (2026-09-25 용팀장 '배너 잡는건 이번까지 하고, 다음단계로 넘어가자. 너무 진도가 늦다'). 기준 불변 · 통과로 적지 않음"
  - "회차 2026-09-20 정본 = 사람 라벨 우선 판정(라벨 있으면 라벨, 없으면 기계)"
  - "새 회차 배너 판정 방식(사람 확인 11분 vs 비전 끄고 어휘군 단독)은 Phase 5 discuss 에서 결정"
  - "banner_vision2_max_calls 0 으로 복귀 — 새 회차 의도치 않은 유료 호출 차단"

metrics:
  duration: 약 40분 (Task 2 · 사람 재검수 시간 제외)
  completed: 2026-09-25
  tasks: 2 of 2
---

# Phase 4 Plan 12: 사람 재검수 후 게이트 재판정 Summary

**🔴 불통과. 사람 재검수(라벨 35→135) 뒤 기준 그대로 다시 재니 미탐 0/50(상한 5.8%) · 오탐 116 · 누락률 13.70% > 10% → `게이트통과 false`. 비전 v3 가 글자·치수표·도식으로 상품 정보를 주는 장 103장을 배너로 찍은 것이 원인. 같은 날 용팀장 결정(D-23)으로 Phase 4 를 불통과 상태로 닫고 Phase 5 로 넘어간다.**

## 숫자 (regate 계산값 · 기준 불변)

| 조건 | 값 | |
|---|---|---|
| `미검수상품 == 0` | 0 (60/60) | ✅ |
| `미탐 == 0` | 0 — 미탐 0/50, 상한 5.8%(95%) | ✅ |
| `오탐율_누락률 <= 10%` | **13.70%** (116/847) · 정밀도 68.6% (116/169) | 🔴 |
| `게이트통과` | **false** (산출물 파일 값도 false 그대로) | |

전후: 2026-09-23 미탐 11 · 오탐 16 · 누락률 1.93% → §16-7(재검수 전) 미탐 0 · 오탐 13 · 1.75% → **재검수 후 미탐 0 · 오탐 116 · 13.70%**.

## Tasks

| Task | 이름 | 커밋 |
|---|---|---|
| 1 | 용팀장 재검수 (사람 작업 — 2026-09-25 12:51~13:16, "검수 다 했어") | (DB 기록 — 커밋 없음) |
| 2 | 게이트 재판정 §17 · VALIDATION · CONTEXT D-23 · ROADMAP · STATE | `838d071` + 메타 커밋 |

## Acceptance 대조

- Task 1 #1 **미충족** — `banner_confirm` max 확인시각 2026-09-23T00:55 < 재측정 생성시각 2026-09-25T00:14. 사람 탓이 아니라 **화면 결함**: `banner_review.html` 이 이미 확인된 상품엔 `확인함` 글자만 그리고 버튼을 안 그려 다시 누를 수 없다. 기계가 확인시각을 대신 쓰지 않았다 → D-23 이월
- Task 1 #2 충족 — 2차 판정 실패 0장이라 대상 없음
- Task 1 #3 부분 — 헤더 숫자 6개는 용팀장이 직접 안 보냈다(regate 로 읽기 전용 확인). 오라벨 2장 답 = **그대로(제품)**
- Task 2 전부 충족 — §17-1~17-7(+17-8) · 조건 문자열 원문 · 17-6 `in-sample`/`미이행` · `gate_passed` = regate `게이트통과` = false · 산출물 `게이트통과` false · `git diff --stat webapp/` 비어 있음 · pytest exit 0

## Deviations from Plan

**1. [사용자 결정 — 플랜 acceptance 예외] ROADMAP Phase 4 체크박스 `[x]`**
- 플랜은 "게이트 통과일 때만 `[x]`" 였다. 용팀장이 2026-09-25 Phase 4 종료를 결정(D-23)해 오케스트레이터 지시로 `[x]` 로 닫되, 괄호에 **"게이트 불통과 · 용팀장 결정으로 종료 (2026-09-25, D-23)"** 를 붙였다. 게이트 통과로 읽히지 않게 Progress 표 상태도 "Closed — 게이트 불통과" 로 적었다

**2. [사용자 결정] §17-5 남은 길을 실행 계획이 아니라 Deferred 로**
- 처음엔 지시문 v4 재측정을 다음 수로 정했지만 D-23 으로 취소. 세 길(Q2 · v4 · 어휘군)은 전부 CONTEXT Deferred 로 넘겼다

**3. [Rule 2 — 비용 안전] `workspace.toml banner_vision2_max_calls` 894 → 0**
- 새 회차 스캔이 의도치 않게 유료 호출을 내지 않게 했다(오케스트레이터 지시 · git 비추적 · 사유 주석)

**4. [기록] `.continue-here.md` 를 한 줄 종료 표시로 축소**
- Phase 4 가 닫혀 이어할 것이 없다. 안티패턴 표 대신 GATE §17-8 · CONTEXT D-23 을 가리킨다

**5. [기록] 비전 추가 배너 사람 제품 수 113 vs 103**
- 오케스트레이터 113 은 물갈이 사본 포함(62상품), 게이트 기준(사본 제외 60상품)은 103. 둘 다 §17-3 에 적었다

**6. [관찰] 옛 미탐 11 → 현 라벨로 8**
- 옛 산출물을 지금 라벨로 재면 미탐 8. 이번 재검수에서 옛 `배너` 라벨 일부가 바뀌었는데 `banner_label` 이 INSERT OR REPLACE 라 어느 3장인지 특정 못 한다. 기록만 했다

## 이월 (D-23 · CONTEXT Deferred)

- 확인함 재클릭 불가 결함 · 검수 화면 `게이트: 열렸다` 문구(04-11 UAT P2) · out-of-sample 재측정(Q2) · 지시문 v4(상품 정보 기준)
- Phase 5 discuss 입력: 새 회차 배너 판정을 ⓐ 사람 확인(약 11분) ⓑ 비전 끄고 어휘군 단독(미탐 위험) 중 무엇으로 할지

## Known Stubs

없음 — 문서만 고쳤다.

## Self-Check: PASSED
- 04-GATE.md `## 17.` · `### 17-1`~`17-8` 존재
- 커밋 838d071 존재
- `git diff --stat webapp/` 비어 있음 · 산출물 `게이트통과` false
