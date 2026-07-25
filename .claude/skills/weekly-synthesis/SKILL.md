---
name: weekly-synthesis
description: 한 주간의 작업과 사고를 종합하여 Weekly Synthesis 생성. "주간 정리", "이번 주 회고", "weekly review", "일주일 요약", "주간 리뷰" 등을 언급하면 자동 실행.
allowed-tools:
  - Read
  - Write
  - Grep
  - Glob
  - Bash
---

# weekly-synthesis

이번 주 작업과 사고를 종합하여 `./40-personal/42-weekly/YYYY-WXX.md`에 저장.

## 분석 프로세스

### 1. 이번 주 범위 파악

```bash
# 이번 주 시작 (월요일) 계산
if [ "$(uname)" = "Darwin" ]; then
  WEEK_START=$(date -v-Mon +%Y-%m-%d 2>/dev/null || date -v-monday +%Y-%m-%d)
else
  WEEK_START=$(date -d "monday this week" +%Y-%m-%d)
fi

WEEK_NUM=$(date +%Y-W%V)
```

### 2. 이번 주 활동 수집

**Daily notes**: `./40-personal/41-daily/` 하위에서 이번 주에 해당하는 파일들

**Git 변경 (git repo인 경우)**:
```bash
git log --since="$WEEK_START" --name-only --pretty=format: | sort -u | grep -v '^$'
```

**활성 프로젝트**: `10-projects/` 에서 이번 주에 수정된 폴더

### 3. 패턴 식별

- 반복되는 테마
- 공통 도전 과제
- 돌파 순간
- 에너지 패턴 (무엇이 에너지를 줬고, 무엇이 소진시켰나)

### 4. 학습 종합

- 발견된 핵심 인사이트
- 사고가 어떻게 진화했나
- 발견한 연결점
- 답한 질문 / 제기된 질문

### 5. 진척도 평가

- 진전된 프로젝트
- 유지된 영역
- 추가된 자료
- 아카이브된 항목

## 출력 형식

```markdown
---
week: YYYY-WXX
period: YYYY-MM-DD ~ YYYY-MM-DD
tags: [weekly]
---

# Weekly Synthesis — Week of {YYYY-MM-DD}

## Week at a Glance
- 작성한 Daily Notes: N개
- 활성 프로젝트: [목록]
- 주요 성취: [목록]

## Key Themes

### Theme 1: [이름]
- 어디서 나타났나: [컨텍스트]
- 왜 중요한가: [의미]
- 다음 행동: [할 것]

### Theme 2: [이름]
...

## Major Insights

1. [인사이트 + 맥락]
2. [인사이트 + 맥락]

## Progress by Project

### [프로젝트명]
- 진전: ...
- 막힌 것: ...
- 다음 주 초점: ...

## Questions Emerged
- [질문 1 — 왜 중요한가]
- [질문 2 — 왜 중요한가]

## Energy Audit
- 에너지 준 것: ...
- 에너지 뺏은 것: ...
- 조정할 것: ...

## Connections Made
- [노트 A] ↔ [노트 B]: [의미]

## Next Week's Intentions
1. [주 초점]
2. [부 초점]
3. [탐색할 것]

## To Process
- Inbox 항목: N개
- 고립된 노트: [목록]
- 누락된 연결: [식별된 것]
```

## 저장 경로

`./40-personal/42-weekly/{WEEK_NUM}.md`
예: `./40-personal/42-weekly/2026-W17.md`

## 후속 행동

분석 후 사용자에게 제안:
- 완료된 프로젝트가 있으면 → "90-archive로 이동할까요?"
- Inbox 항목 많으면 → "00-inbox 폴더를 지금 함께 정리할까요?" (해당 폴더를 직접 훑어서 10-projects / 30-knowledge / 43-ideas / 90-archive로 재배치)
- 00-wiki에 승격할 인사이트가 있으면 → "wiki-ingest로 저장할까요?"

## 원칙

- **숫자보다 패턴에 집중** — "몇 개 했다"보다 "무엇이 반복되고 있나"
- **에너지 관찰** — 지속가능성의 핵심 지표
- **다음 주 intentions은 3개 이하** — 너무 많으면 지킬 수 없음
