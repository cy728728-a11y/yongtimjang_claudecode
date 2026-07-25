---
name: todos
description: 저장된 Todo 조회 및 관리. 전체/오늘/프로젝트별/오래된 것/통계 뷰 지원. "할 일 보기", "todos", "오늘 할 일", "오버듀", "할 일 통계" 등을 언급하면 자동 실행.
argument-hint: "[today|project|overdue|stats|] (없으면 전체)"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
---

# todos - Todo List Viewer & Manager

`./40-personal/46-todos/active-todos.md`의 Todo를 다양한 관점으로 조회.

## 사용 예시

```
todos              # 전체 Todo
todos today        # 오늘 할 일만
todos project      # 프로젝트별 그룹화
todos overdue      # 1주일 이상 된 것
todos stats        # 통계
```

## 파일

- 읽기: `./40-personal/46-todos/active-todos.md`
- 아카이브: `./40-personal/46-todos/completed-todos.md` (auto-cleanup 시 생성)

## 모드별 동작

### 기본 (전체 보기)

active-todos.md를 그대로 읽어서 섹션별 개수와 함께 표시.

```markdown
# 전체 Todo 목록 (N개)

## 🔥 Today (3개)
- [ ] ...

## 📅 This Week (5개)
- [ ] ...

## 🔮 Someday (2개)
- [ ] ...

## 📥 Inbox (1개)
- [ ] ...
```

### Scheduled 섹션 표시 규칙 (모든 조회 모드 공통)

`## Scheduled` 섹션의 todo는 `due:` 날짜와 오늘 날짜를 비교해 표시 여부 결정:

- **due가 미래**: 항목 내용 숨김. 개수와 가장 이른 due만 한 줄로 표시.
  예: `## ⏳ Scheduled (2개 예약 — 가장 이른 due: 2026-08-05)`
- **due가 오늘이거나 지남**: 숨기지 않고 목록 **최상단**(Today보다 위)에 "📌 시작할 예약 작업"으로 표시
- due 필드가 없는 Scheduled 항목은 항상 표시
- 사용자가 명시적으로 요청하면("예약된 것도 보여줘", "scheduled 전부") 전체 표시

### today

`🔥 Today` 섹션만 추출. 우선순위 필드 기준 정렬 (high → normal → low).

### project

모든 섹션의 todo를 읽어 `project:` 필드로 그룹화.
프로젝트 미지정 todo는 "Unassigned" 그룹.

### overdue

`added:` 필드 기준 7일 이상 경과한 todo 필터링. 오래된 순 정렬.

날짜 차이 계산 (Mac/Linux 호환):
```bash
# Mac
days_ago=$(( ($(date +%s) - $(date -j -f "%Y-%m-%d %H:%M" "$added" +%s)) / 86400 ))

# Linux
days_ago=$(( ($(date +%s) - $(date -d "$added" +%s)) / 86400 ))
```

### stats

집계:
- 총 개수
- 섹션별 (Today/This Week/Someday/Inbox)
- 우선순위별 (high/normal/low)
- 프로젝트별 (있는 것)

### Auto-cleanup (모든 모드에서 공통)

체크된 todo (`[x]`) 감지 시:
1. 완료 날짜 기록
2. `completed-todos.md`로 이동 (월별 섹션)
3. active-todos.md에서 제거

## 출력 원칙

- 섹션별 개수 항상 표시
- 빈 섹션은 "비어있음"
- 80자 이상 todo는 축약
- 다음 행동 제안 1개 (옵션)

## 참고

- 이 스킬은 **로컬 파일만** 읽고 씁니다. 외부 동기화는 별도.
- Today/This Week 섹션만 사용자가 적극 관리. Someday/Inbox는 자유.
