---
name: daily-review
description: 어제/오늘 git 변경사항을 분석하고, daily note + todos 기반으로 오늘 우선순위를 제안. "일일 리뷰", "오늘 뭐 했지", "어제 작업 정리", "daily review" 등을 언급하면 자동 실행.
allowed-tools:
  - Read
  - Bash
  - Grep
  - Glob
---

# daily-review

어제~오늘의 git 변경사항과 daily note, todos를 종합하여 오늘 우선순위를 제안.

**전제**: 오늘 daily note가 존재해야 함. 없으면 "먼저 daily-note 스킬로 생성해주세요" 안내.

## 수행 작업

### 1. Git 변경사항 분석

```bash
# 워크스페이스 루트가 git repo인지 확인
if [ -d .git ] || git rev-parse --git-dir > /dev/null 2>&1; then
  # 어제 이후 변경된 파일
  git log --since="yesterday" --name-only --pretty=format: | sort -u | grep -v '^$'
else
  echo "git repo가 아님. daily note + todos만 분석합니다."
fi
```

변경된 파일을 **최상위 카테고리별로 그룹화**:
- `10-projects/` 하위 변경사항
- `20-operations/` 하위 변경사항
- `30-knowledge/` 하위 변경사항
- `40-personal/` 하위 변경사항 (daily, todos 등)
- `.claude/` 설정 변경

카테고리별로 어떤 폴더/파일이 움직였는지 요약.

### 2. 오늘 우선순위 제안

**읽을 파일**:

```bash
TODAY=$(date +%Y-%m-%d)
MONTH=$(date +%Y-%m)

# 오늘 daily note
cat "./40-personal/41-daily/$MONTH/$TODAY.md"

# active todos
cat "./40-personal/46-todos/active-todos.md"
```

**분석 기반**:
- 어제 git 변경에서 이어질 작업
- daily note에 이미 적힌 일정/계획
- active-todos의 Today/This Week 항목
- 프로젝트 마감일 (있으면)

### 3. 출력 형식

```markdown
## Git 변경사항 (어제~오늘)

### 10-projects/
- [변경된 프로젝트 폴더명]: [요약]

### 30-knowledge/
- [변경된 파일]: [요약]

## 오늘 우선순위 제안

1. [우선순위 1] — 근거
2. [우선순위 2] — 근거
3. [우선순위 3] — 근거

## 인사이트
- [패턴]
- [이어갈 작업]
```

## 원칙

- 하드코딩된 프로젝트 이름 사용 금지. **실제 변경된 폴더명으로 그룹핑**.
- 3개 이하 우선순위만 제안. 그 이상이면 사용자가 부담됨.
- 근거를 항상 명시 (왜 이게 우선인가).
