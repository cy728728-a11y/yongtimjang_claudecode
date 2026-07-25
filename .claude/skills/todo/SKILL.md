---
name: todo
description: 빠르게 Todo를 추가 (우선순위 감지, 프로젝트 태그 지원). "할 일 추가", "todo 추가", "이거 해야해", "기억해둬" 등을 언급하면 자동 실행.
argument-hint: "[우선순위] [프로젝트] 할 일 내용"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
---

# todo - Quick Todo Capture

`./40-personal/46-todos/active-todos.md`에 빠르게 할 일을 추가.

## 사용 예시

```
할 일 추가: 세무사한테 4월 자료 보내기
todo [urgent] 매장 전기점검 예약
todo [website] 랜딩페이지 문구 수정
```

## 파싱 규칙

1. **우선순위 태그** (맨 앞 `[...]` 형태):
   - `[urgent]` 또는 `[high]` → high priority → `## 🔥 Today` 섹션
   - `[low]` → low priority → `## 🔮 Someday` 섹션
   - 그 외 `[태그]` → 프로젝트명으로 간주 → `## 📅 This Week` 섹션
   - 없음 → normal → `## 📅 This Week` 섹션

2. **프로젝트 태그** (우선순위 외 대괄호):
   - 있으면 `project:` 필드에 저장

## 추가 형식

```markdown
- [ ] [Todo 내용]
  - added: YYYY-MM-DD HH:MM
  - priority: [high/normal/low]
  - project: [프로젝트명]  # 있을 때만
```

## 실행 단계

1. 입력 파싱 (우선순위, 프로젝트, 내용)
2. 현재 시각 확인: `date +"%Y-%m-%d %H:%M"`
3. `./40-personal/46-todos/active-todos.md` 읽기
4. 우선순위에 맞는 섹션에 **맨 아래** 추가 (`Edit` 도구)
5. 저장
6. 결과 출력:

```
✅ Todo 추가됨: [내용]
   섹션: 🔥 Today | 📅 This Week | 🔮 Someday
   우선순위: high | normal | low
   프로젝트: [프로젝트명]  (있을 때만)
```

## 파일 초기 구조

파일이 없거나 섹션이 없으면 이 구조로 초기화:

```markdown
# Active Todos

## 🔥 Today

## 📅 This Week

## 🔮 Someday

## 📥 Inbox
```

## 참고

- 이 스킬은 **로컬 파일에만 저장**합니다. 외부 서비스(Google Tasks 등) 동기화는 별도 스킬로.
- 완료된 todo는 `todos` 스킬의 auto-cleanup으로 `completed-todos.md`로 이동.
