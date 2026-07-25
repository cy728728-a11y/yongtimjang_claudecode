---
name: setup-workspace
description: 첫 clone 후 워크스페이스 초기 설정. CLAUDE.md 프로필 작성 + Python venv 세팅 + 선택 도구(gws/git) 안내 + 첫 daily note 생성까지 한번에 진행. "워크스페이스 세팅", "초기 설정", "setup", "setup-workspace" 등을 언급하면 자동 실행.
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
---

# setup-workspace

Do Better Workspace를 처음 clone한 사용자를 위한 초기 설정 스킬.
5단계: **루트 확인 → 프로필 → Python 환경 → 선택 도구 안내 → 첫 Daily Note**.

## 수행 작업

### 1. 워크스페이스 루트 + 시드 무결성 확인

**1-1. 루트 여부**:

```bash
test -f CLAUDE.md && test -d 40-personal && test -d 30-knowledge/00-wiki \
  || { echo "ERROR: 워크스페이스 루트에서 실행하세요 (CLAUDE.md·40-personal·30-knowledge 없음)"; exit 1; }
```

루트가 아니면 종료.

**1-2. 시드 파일/폴더 무결성**:

각 스킬이 실제로 참조하는 시드가 살아있는지 일괄 체크. 누락된 건 경고로만 출력하고 자동 복원은 하지 않음 (clone이 불완전했거나 사용자가 실수로 지운 경우 빨리 감지).

```bash
echo "=== 시드 무결성 체크 ==="
missing=()

# 템플릿 (daily-note, weekly-synthesis, ripple이 읽음)
test -f 00-system/01-templates/daily-note-template.md   || missing+=("00-system/01-templates/daily-note-template.md")
test -f 00-system/01-templates/weekly-review-template.md || missing+=("00-system/01-templates/weekly-review-template.md")
test -f 00-system/01-templates/progress-template.md     || missing+=("00-system/01-templates/progress-template.md")

# Personal 디렉토리 (daily/weekly/idea 스킬 저장 경로)
test -d 40-personal/41-daily    || missing+=("40-personal/41-daily/")
test -d 40-personal/42-weekly   || missing+=("40-personal/42-weekly/")
test -d 40-personal/43-ideas    || missing+=("40-personal/43-ideas/")
test -d 40-personal/46-todos    || missing+=("40-personal/46-todos/")

# Todo 시드 (todo/todos 스킬 타깃)
test -f 40-personal/46-todos/active-todos.md || missing+=("40-personal/46-todos/active-todos.md")

# raw 인박스 (kakao-read 수집 → inbox-triage 분류 경로)
test -d 00-inbox/raw || missing+=("00-inbox/raw/")

# Wiki 시드 (wiki-ingest, wiki-lint가 읽고 씀)
test -f 30-knowledge/00-wiki/SCHEMA.md || missing+=("30-knowledge/00-wiki/SCHEMA.md")
test -f 30-knowledge/00-wiki/index.md  || missing+=("30-knowledge/00-wiki/index.md")
test -f 30-knowledge/00-wiki/log.md    || missing+=("30-knowledge/00-wiki/log.md")

if [ ${#missing[@]} -eq 0 ]; then
  echo "✓ 모든 시드 파일 정상"
else
  echo "⚠️  누락된 시드 (${#missing[@]}개):"
  printf '  - %s\n' "${missing[@]}"
  echo ""
  echo "이 상태로 진행 가능하나, 관련 스킬 실행 시 에러가 날 수 있습니다."
  echo "clone 상태를 확인하거나 원본 레포에서 누락된 파일을 가져오세요."
fi
```

누락이 있으면 사용자에게 "이대로 진행할까요? (y/N)" 확인. N이면 종료.

### 2. 대화형 프로필 질문

순서대로 하나씩 물어본다. 한 번에 하나씩 (일괄 질문 금지).

먼저 **CLAUDE.md의 "내 프로필" 섹션이 이미 채워져 있는지** 확인:
- 비어있으면 → 아래 질문 진행
- 이미 채워져 있으면 → "프로필이 이미 있어요. 다시 채울까요? (y/N)" → N이면 이 단계 스킵

질문 목록:
1. **이름 또는 호칭** — "어떻게 불러드릴까요?"
2. **역할/직업** — "현재 어떤 일을 하고 계세요? (ex: 카페 사장, 마케터, 프리랜서 디자이너)"
3. **주요 관심사** — "요즘 가장 집중하고 있는 것 2~3개만 알려주세요"
4. **이 워크스페이스 용도** — "이 워크스페이스를 어떻게 쓰고 싶으세요? (ex: 일일 기록, 프로젝트 관리, 학습 정리)"

답변은 변수로 저장 (`USER_NAME`, `USER_ROLE`, `USER_INTERESTS`, `USER_PURPOSE`).

### 3. CLAUDE.md 업데이트

`CLAUDE.md` 하단의 "내 프로필" 섹션만 `Edit` 도구로 부분 수정. 덮어쓰기 금지.

기존 → 업데이트:
```markdown
## 내 프로필

**이름**: {USER_NAME}
**역할**: {USER_ROLE}
**관심사**: {USER_INTERESTS}
**이 워크스페이스 용도**: {USER_PURPOSE}

_작성일: YYYY-MM-DD_
```

### 4. Python 환경 세팅 (신규)

**왜 필요한가**: `csv-clean`, `excel-to-csv`, `pdf-to-md` 세 스킬이 Python 스크립트를 사용함. 나중에 갑자기 에러 나는 것보다 처음에 한 번에 세팅하는 게 편하다.

**4-1. Python 설치 확인**:

```bash
if command -v python3 &> /dev/null; then
  echo "Python: $(python3 --version)"
else
  echo "ERROR: python3 미설치. Mac은 'brew install python', Ubuntu는 'sudo apt install python3 python3-venv'"
fi
```

없으면 설치 안내 후 이 단계 스킵.

**4-2. venv 세팅 제안**:

```
데이터 처리 스킬(csv-clean, excel-to-csv, pdf-to-md)을 쓰려면 Python 패키지 3개가 필요합니다.
워크스페이스 전용 가상환경(.venv)을 지금 만들까요? (Y/n)
```

Yes (기본)면:

```bash
# 이미 .venv 있으면 스킵
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install --upgrade pip --quiet
pip install "pandas>=2.0.0" "openpyxl>=3.1.0" "pymupdf4llm>=0.0.17"
```

설치 완료 후 확인:
```bash
source .venv/bin/activate && python -c "import pandas, openpyxl, pymupdf4llm; print('OK: pandas', pandas.__version__, '| openpyxl', openpyxl.__version__, '| pymupdf4llm imported')"
```

**안내 출력**:
```
✓ .venv/ 생성 및 패키지 설치 완료

**사용법**: 새 터미널을 열 때마다 가상환경 활성화:
  source .venv/bin/activate

Claude Code가 Python 스크립트를 호출할 때 자동으로 이 venv를 쓰려면 매 세션 시작 시
위 명령을 한 번 실행하거나, 셸 시작 시 자동 활성화 스크립트를 설정하세요.
```

No면 "나중에 필요할 때 다시 이 스킬을 호출하거나 직접 `pip install`로 설치하세요" 안내 후 다음 단계.

### 5. 선택 도구 안내 (설치 강제 X)

**어떤 도구가 어떤 스킬을 풀어주는지** 한번에 체크하고 보여준다:

```bash
echo "=== 선택 도구 상태 ==="
command -v git &>/dev/null && echo "✓ git: $(git --version)" || echo "✗ git: 미설치 (daily-review, weekly-synthesis 동작 제한)"
command -v gws &>/dev/null && echo "✓ gws: $(gws --version 2>&1 | head -1)" || echo "✗ gws: 미설치 (daily-note의 Google Calendar 연동 스킵)"
if [ "$(uname)" = "Darwin" ]; then
  command -v sqlcipher &>/dev/null && echo "✓ sqlcipher: $(sqlcipher --version 2>&1 | head -1)" \
    || echo "✗ sqlcipher: 미설치 (kakao-read 카톡 읽기 비활성 — brew install sqlcipher)"
else
  echo "ℹ️  kakao-read: macOS 전용 — 현재 OS($(uname))에선 비활성 (다른 스킬엔 영향 없음)"
fi
```

출력 후 설명:

```markdown
**git**: 현재 워크스페이스가 git repo면 daily-review / weekly-synthesis가 변경사항을 분석해줍니다.
  - 세팅: `git init` 후 첫 커밋

**gws (Google Workspace CLI)**: daily-note가 오늘의 Google Calendar 일정을 자동으로 가져와줍니다.
  - 설치: `npm install -g @googleworkspace/cli` (구 문서의 `gws-cli`는 존재하지 않는 패키지명)
  - 인증: `gcloud auth login` → `gws auth setup` → `gws auth login` (브라우저 OAuth, gcloud 필요)
  - 없어도 daily-note는 정상 동작하며 일정 섹션만 비어있음

**sqlcipher (macOS 전용)**: kakao-read가 Mac 카카오톡 로컬 DB를 읽습니다.
  - 설치: `brew install sqlcipher`
  - 최초 1회: `python3 .claude/skills/kakao-read/scripts/kakao_read.py setup` (본인 userId 캐시)
  - 카카오톡 데스크톱 앱에 한 번 이상 로그인돼 있어야 함
  - macOS 전용 — Windows/Linux에선 자동 비활성, 다른 스킬엔 영향 없음
```

설치까지 자동으로 하지 않음. 사용자가 필요성 판단 후 진행.

### 6. 첫 Daily Note 생성 제안

"오늘의 첫 Daily Note를 만들까요? (Y/n)"
Yes면 `daily-note` 스킬 호출.

### 7. 다음 단계 안내

```
워크스페이스 세팅 완료!

다음에 해볼 것:
1. "오늘 daily note 만들어줘" → 매일의 기록 시작
2. "할 일 추가해줘: XXX" → 첫 todo 추가
3. "같이 생각해보자: XXX" → thinking-partner로 문제 탐색
4. "이 아이디어 저장해줘" → idea 스킬로 인사이트 캡처

폴더 구조 힌트:
- 00-inbox/ : 생각나는 즉시 캡처
- 10-projects/ : 시한부 프로젝트
- 20-operations/ : 지속적 운영
- 30-knowledge/00-wiki/ : 지식 복리 축적
- 40-personal/ : Daily/Weekly/Ideas/Todos

Python 스킬 사용 시: source .venv/bin/activate 먼저 실행

자세한 건 README.md 참고!
```

## 원칙

- **일괄 질문 금지**. 하나씩 물어야 인지 부담 낮음.
- **답변은 짧게 유도**. 긴 자기소개 요구하지 말 것.
- **CLAUDE.md 덮어쓰기 금지**. "내 프로필" 섹션만 `Edit` 도구로 부분 수정.
- **이미 채워져 있으면** 덮어쓰기 전 사용자에게 확인.
- **Python 환경은 권장, 강제 X**. 데이터 스킬 안 쓸 사람도 있음.
- **선택 도구(git/gws)는 상태만 체크**. 자동 설치·인증은 안 함 (교육 과정에서 별도 안내되는 영역).
- **재실행 안전**. 이미 세팅된 항목은 스킵.
