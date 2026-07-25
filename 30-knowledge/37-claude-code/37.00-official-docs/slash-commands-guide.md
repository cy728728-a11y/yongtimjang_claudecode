# Claude Code Slash Commands 가이드

> **DEPRECATED (2026-02-22)**: 공식 문서에서 `/slash-commands` URL이 `/skills`로 리다이렉트됨.
> Custom slash commands는 Skills로 통합되었음. **[[skills-guide]]를 참조할 것.**
> 기존 `.claude/commands/` 파일은 계속 작동하지만, Skills가 권장됨.
> Built-in commands는 [Interactive Mode](https://code.claude.com/docs/en/interactive-mode#built-in-commands)로 이동.
>
> 이 문서는 아카이브 참고용으로 유지됨. 새로운 내용은 skills-guide.md에서 관리.

> 출처: [Claude Code 공식 문서](https://code.claude.com/docs/en/slash-commands) (-> /skills로 리다이렉트)
> 작성일: 2026-01-16

---

## 📚 목차

1. [Slash Commands란?](#slash-commands란)
2. [Built-in Commands](#built-in-commands)
3. [Custom Commands 생성](#custom-commands-생성)
4. [고급 YAML Frontmatter](#고급-yaml-frontmatter)
5. [Arguments & Parameters](#arguments--parameters)
6. [Skill Tool을 통한 프로그래매틱 호출](#skill-tool을-통한-프로그래매틱-호출)
7. [Commands vs Skills vs Subagents](#commands-vs-skills-vs-subagents)
8. [실전 예제](#실전-예제)
9. [베스트 프랙티스](#베스트-프랙티스)

---

## Slash Commands란?

Slash Commands는 **빠르고 재사용 가능한 프롬프트 템플릿**입니다.

### 핵심 특징

- **간단한 구조**: 단일 Markdown 파일
- **빠른 실행**: `/명령어` 입력 즉시 실행
- **팀 공유**: 프로젝트 레벨 커맨드는 Git으로 공유
- **개인 맞춤**: 사용자 레벨 커맨드는 모든 프로젝트에서 사용

### 사용 사례

- 자주 사용하는 프롬프트 저장
- 팀 워크플로우 표준화
- 반복 작업 자동화
- 컨텍스트 수집 (git status, 파일 읽기 등)

---

## Built-in Commands

Claude Code는 **40개 이상**의 내장 커맨드를 제공합니다. (v2.1.x 기준)

### Essential Operations

| Command | 설명 |
|---------|------|
| `/clear` | 대화 히스토리 제거 |
| `/compact [instructions]` | 대화 압축 (선택적 포커스 지시 가능) |
| `/context` | 현재 컨텍스트 사용량을 색상 그리드로 시각화 |
| `/help` | 사용법 표시 |
| `/config` | 설정 인터페이스 |
| `/export [filename]` | 대화를 파일 또는 클립보드로 내보내기 |
| `/exit` | REPL 종료 |

### Development & Code

| Command | 설명 |
|---------|------|
| `/model` | AI 모델 선택/전환 |
| `/sandbox` | 격리된 bash 도구 활성화 (파일시스템/네트워크 보호) |
| `/plan` | 플랜 모드 직접 입력 (구현 전 설계) |
| `/ide` | IDE 통합 관리 및 상태 표시 |
| `/security-review` | 보안 검토 |

### Project Management

| Command | 설명 |
|---------|------|
| `/init` | CLAUDE.md 가이드로 프로젝트 초기화 |
| `/add-dir` | 추가 작업 디렉토리 포함 |
| `/agents` | 커스텀 서브에이전트 관리 |
| `/skills` | Skills 목록 및 관리 |

### Utility Functions

| Command | 설명 |
|---------|------|
| `/cost` | 토큰 사용량 통계 표시 |
| `/stats` | 일일 사용량, 세션 이력, 연속 사용 시간 시각화 |
| `/doctor` | Claude Code 설치 상태 확인 |
| `/bug` | Anthropic에 버그 리포트 전송 |
| `/bashes` | 백그라운드 작업 목록 및 관리 |

### Account & Authentication

| Command | 설명 |
|---------|------|
| `/login` | Anthropic 계정 전환 |
| `/logout` | 현재 계정 로그아웃 |
| `/mcp` | MCP 서버 연결 및 OAuth 관리 |
| `/permissions` | 권한 설정 관리 |

### Configuration & Customization

| Command | 설명 |
|---------|------|
| `/hooks` | 훅 구성 관리 |
| `/memory` | CLAUDE.md 메모리 파일 편집 |
| `/theme` | 색상 테마 변경 |
| `/vim` | Vim 모드 입력 |
| `/plugin` | Claude Code 플러그인 관리 |

---

## Custom Commands 생성

### 파일 구조

**프로젝트 레벨** (팀 공유):
```
.claude/commands/
├── optimize.md          # /optimize
├── fix-issue.md         # /fix-issue
└── frontend/
    └── component.md     # /component (project:frontend)
```

**사용자 레벨** (개인용):
```
~/.claude/commands/
├── daily-note.md        # /daily-note (user)
└── idea.md              # /idea (user)
```

### 기본 예제

**파일**: `.claude/commands/optimize.md`

```markdown
---
description: Analyze code for optimization opportunities
---

Examine this code for performance issues and suggest improvements.
```

**사용**: `/optimize`

---

### YAML Frontmatter

```markdown
---
description: Brief command overview
argument-hint: [issue-number] [priority]
allowed-tools: Bash, Read, Write
model: sonnet
disable-model-invocation: true
---

Your prompt template here.
```

#### 필드 설명

| 필드 | 필수 | 설명 |
|------|------|------|
| `description` | 권장 | 커맨드 설명 (Skill tool 사용 시 필수) |
| `argument-hint` | 선택 | 자동완성 시 표시될 인자 힌트 |
| `allowed-tools` | 선택 | 허용할 도구 목록 |
| `model` | 선택 | 특정 AI 모델 지정 |
| `disable-model-invocation` | 선택 | 자동 실행 방지 (수동 실행만) |

---

## 고급 YAML Frontmatter

### 전체 필드 참조 (v2.1.x)

```yaml
---
description: Brief command overview
argument-hint: [arg1] [arg2]
allowed-tools: Bash, Read, Write
model: sonnet
context: fork
agent: agent-name
disable-model-invocation: false
hooks:
  PreToolUse:
    - path: ./scripts/pre-tool.sh
  PostToolUse:
    - path: ./scripts/post-tool.sh
  Stop:
    - path: ./scripts/on-stop.sh
---

Your prompt template here.
```

### 필드 상세 설명

| 필드 | 필수 | 설명 |
|------|------|------|
| **description** | 권장 | 커맨드 설명 (Skill tool 호출 시 필수) |
| **argument-hint** | No | 자동완성 시 표시될 인자 힌트 |
| **allowed-tools** | No | 허용할 도구 목록 (쉼표 구분) |
| **model** | No | `sonnet`, `opus`, `haiku`, `'inherit'` |
| **context** | No | `fork` - 독립 서브에이전트 컨텍스트에서 실행 |
| **agent** | No | `context: fork` 시 사용할 agent 타입 |
| **disable-model-invocation** | No | `true` - 명시적 호출만 허용 |
| **hooks** | No | PreToolUse, PostToolUse, Stop 이벤트 핸들러 |

### `context: fork` 설명

커맨드를 독립적인 서브에이전트 컨텍스트에서 실행합니다.

```yaml
---
description: Heavy analysis that needs separate context
context: fork
agent: analysis-worker
model: opus
---

Perform deep analysis of the codebase...
```

**사용 사례**:
- 긴 분석 작업
- 메인 대화 컨텍스트 보존 필요 시
- 복잡한 멀티스텝 작업

### `hooks` 설명

커맨드 실행 중 특정 이벤트에 스크립트를 실행합니다.

```yaml
---
description: Command with event hooks
hooks:
  PreToolUse:
    - path: ./scripts/log-start.sh
      timeout: 5000
  Stop:
    - path: ./scripts/cleanup.sh
---
```

**이벤트 유형**:
| 이벤트 | 실행 시점 |
|--------|----------|
| **PreToolUse** | 도구 실행 전 |
| **PostToolUse** | 도구 실행 후 |
| **Stop** | 커맨드 종료 시 |

**환경 변수**:
- `${CLAUDE_SESSION_ID}` - 현재 세션 ID
- `${TOOL_NAME}` - 실행 중인 도구 이름

---

## Arguments & Parameters

### `$ARGUMENTS` - 모든 인자 캡처

**정의**: `.claude/commands/fix-issue.md`
```markdown
---
description: Fix numbered issue
argument-hint: [issue-number]
---

Fix issue #$ARGUMENTS following our coding standards.
```

**사용**: `/fix-issue 123`
**결과**: `$ARGUMENTS` → "123"

---

### `$1`, `$2`, `$3` - 개별 인자

**정의**: `.claude/commands/translate.md`
```markdown
---
description: Translate text
argument-hint: [source-lang] [target-lang] [text]
---

Translate "$3" from $1 to $2.
```

**사용**: `/translate en ko "Hello World"`
**결과**:
- `$1` → "en"
- `$2` → "ko"
- `$3` → "Hello World"

---

### `!command` - Bash 실행

**정의**: `.claude/commands/git-review.md`
```markdown
---
description: Review recent git changes
allowed-tools: Bash
---

Recent changes:
!git log --oneline -5
!git diff HEAD~1

Please review these changes and suggest improvements.
```

**효과**: `!` 접두사가 붙은 명령어 출력이 프롬프트에 포함됨

---

### `@file` - 파일 참조

**정의**: `.claude/commands/review-config.md`
```markdown
---
description: Review configuration files
---

Review these configuration files:

@package.json
@tsconfig.json
@.eslintrc.js

Suggest improvements for consistency and best practices.
```

**효과**: `@` 접두사가 붙은 파일 내용이 프롬프트에 포함됨

---

## Skill Tool을 통한 프로그래매틱 호출

### 개요

Slash Commands와 Agent Skills를 프로그래밍 방식으로 호출할 수 있습니다.

**호출 가능 항목**:
- `.claude/commands/` 또는 `~/.claude/commands/`의 커스텀 슬래시 커맨드
- `.claude/skills/` 또는 `~/.claude/skills/`의 Agent Skills

**호출 불가**: `/compact`, `/init` 등 내장 커맨드

### Skill Tool 사용

**서브에이전트에서 커맨드 호출**:
```markdown
---
name: blog-workflow
description: Complete blog publishing workflow
---

# Blog Publishing Workflow

## Instructions

1. Use Skill tool to invoke `/seo-optimizer` with the content
2. Use Skill tool to invoke `/ghost-validator` for validation
3. Use Skill tool to invoke `/ghost-publisher` to publish

Example call:
Use the Skill tool with:
- skill: "seo-optimizer"
- args: "content-slug-here"
```

### Claude가 특정 커맨드 사용하도록 유도

```markdown
> Run /write-unit-test when you are about to start writing tests.
```

### Skill Tool 비활성화

```bash
/permissions
# 거부 규칙에 추가: Skill
```

### 특정 커맨드/Skill 비활성화

```yaml
---
description: My command
disable-model-invocation: true
---
```

### Skill 권한 규칙

```
Skill(commit)          # commit (인자 없음)만 허용
Skill(review-pr:*)     # review-pr + 모든 인자 허용
```

### 문자 예산 제한

- **기본값**: 15,000 문자
- **커스텀**: `SLASH_COMMAND_TOOL_CHAR_BUDGET` 환경변수로 설정

### 활용 시나리오

**워크플로우 오케스트레이션**:
```markdown
---
name: full-publish-workflow
description: Complete content publishing workflow
---

# Full Publish Workflow

Execute in order:
1. `/seo-optimizer` - SEO 최적화
2. `/image-validator` - 이미지 검증
3. `/ghost-publisher` - Ghost 발행
4. `/social-poster` - 소셜 미디어 공유

Use Skill tool for each step, passing results to next step.
```

---

## Commands vs Skills vs Subagents

### 비교표

| 측면 | **Slash Commands** | **Agent Skills** |
|------|-------------------|-----------------|
| **복잡도** | 간단한 프롬프트 | 복잡한 기능 |
| **구조** | 단일 .md 파일 | SKILL.md + 리소스 |
| **발견** | 명시적 호출 (`/command`) | 자동 (컨텍스트 기반) |
| **파일** | 한 개만 | 여러 파일, 스크립트, 템플릿 |
| **범위** | 프로젝트/개인 | 프로젝트/개인 |

---

### 언제 무엇을 사용할까?

**Slash Commands 사용 시**:
- 자주 사용하는 같은 프롬프트
- 한 파일에 맞는 프롬프트
- 실행 시점을 명시적으로 제어

**Skills 사용 시**:
- Claude가 자동으로 발견해야 함
- 여러 파일/스크립트 필요
- 복잡한 워크플로우
- 팀 표준화된 상세 지침

---

## 실전 예제

### 예제 1: 간단한 코드 리뷰

**파일**: `.claude/commands/review.md`

```markdown
---
description: Quick code review for recent changes
allowed-tools: Bash
---

Recent changes:
!git diff HEAD~1

Please review:
1. Code quality and readability
2. Potential bugs or edge cases
3. Performance considerations
4. Best practices adherence
```

**사용**: `/review`

---

### 예제 2: 인자를 받는 이슈 수정

**파일**: `.claude/commands/fix-issue.md`

```markdown
---
description: Fix GitHub issue with best practices
argument-hint: [issue-number]
allowed-tools: Bash, Read, Write
---

I need to fix issue #$ARGUMENTS.

First, show me the issue details:
!gh issue view $ARGUMENTS

Then:
1. Analyze the issue requirements
2. Suggest implementation approach
3. Create necessary code changes
4. Write appropriate tests
5. Update documentation if needed
```

**사용**: `/fix-issue 123`

---

### 예제 3: 여러 인자 처리

**파일**: `.claude/commands/create-component.md`

```markdown
---
description: Create React component with tests
argument-hint: [component-name] [component-type]
allowed-tools: Write
---

Create a $2 React component named $1.

Requirements:
- TypeScript
- Proper PropTypes
- Unit tests with Jest
- Storybook story
- README documentation

Follow our component structure in src/components/
```

**사용**: `/create-component UserProfile functional`

---

### 예제 4: 파일 참조 활용

**파일**: `.claude/commands/update-docs.md`

```markdown
---
description: Update documentation based on code changes
---

Review current documentation:
@README.md
@CONTRIBUTING.md

Review recent code changes:
!git diff HEAD~5

Please update the documentation to reflect:
1. New features added
2. API changes
3. Configuration updates
4. Migration steps if needed
```

**사용**: `/update-docs`

---

### 예제 5: 네임스페이스 커맨드

**파일**: `.claude/commands/frontend/component.md`

```markdown
---
description: Create frontend component with full setup
---

Create a new frontend component with:
- React component file
- CSS modules
- Unit tests
- Storybook story
```

**사용**: `/component` (표시: `(project:frontend)`)

---

## 베스트 프랙티스

### 1. Scope 선택

**프로젝트 레벨** (`.claude/commands/`):
- 팀 공유 워크플로우
- 프로젝트 특화 작업
- Git으로 버전 관리

**사용자 레벨** (`~/.claude/commands/`):
- 개인 생산성 도구
- 모든 프로젝트 공통 작업
- 개인 워크플로우

---

### 2. Description 필수 작성

**이유**: `SlashCommand` tool이 프로그래밍 방식으로 실행 시 필요

```markdown
---
description: Clear, concise description of what this command does
---
```

---

### 3. 조직화

**서브디렉토리 활용**:
```
.claude/commands/
├── git/
│   ├── review.md
│   └── stats.md
├── frontend/
│   ├── component.md
│   └── test.md
└── docs/
    └── update.md
```

**장점**:
- 명확한 분류
- 네임스페이스 자동 생성
- 대규모 프로젝트 관리 용이

---

### 4. 자동 실행 방지

**사용 사례**: 민감한 작업, 수동 확인 필요

```markdown
---
description: Deploy to production
disable-model-invocation: true
---

Deploy current branch to production environment.
```

---

### 5. Allowed Tools 명시

**보안**: 필요한 도구만 허용

```markdown
---
allowed-tools: Bash, Read
---

Review git history:
!git log --oneline -10

Read current config:
@config/production.json
```

---

### 6. Argument Hints 제공

**사용자 경험**: 자동완성 시 힌트 표시

```markdown
---
argument-hint: [component-name] [type: class|functional]
---
```

---

### 7. 명확한 단계별 지침

**✅ 좋은 예**:
```markdown
Please follow these steps:
1. Analyze the requirements
2. Create implementation plan
3. Write code with tests
4. Update documentation
5. Verify all tests pass
```

**❌ 나쁜 예**:
```markdown
Make it better.
```

---

## Plugin Commands

### 구조

플러그인은 `commands/` 디렉토리에 Markdown 파일로 커맨드를 제공합니다.

### 네이밍

**패턴**: `/plugin-name:command-name`

**예시**:
- `/github:create-pr`
- `/docker:build`

**충돌 없으면**: 접두사 생략 가능 (`/create-pr`)

---

## MCP Slash Commands

### 자동 생성

MCP 서버가 연결되면 자동으로 커맨드 생성:

**패턴**: `/mcp__<server-name>__<prompt-name>`

**예시**:
- `/mcp__github__get_issue`
- `/mcp__notion__search_pages`

### 권한 설정

**중요**: 와일드카드 미지원

**올바른 형식**:
```
mcp__github              # 모든 도구 승인
mcp__github__get_issue   # 특정 도구만
```

---

## 체크리스트

### 커맨드 생성 전

- [ ] 목적이 명확한가? (단일 책임)
- [ ] 프로젝트 vs 개인 레벨 결정
- [ ] 필요한 도구 파악
- [ ] 인자가 필요한가?

### 작성 중

- [ ] `description` 작성
- [ ] `argument-hint` 추가 (인자 사용 시)
- [ ] `allowed-tools` 명시 (보안)
- [ ] 명확한 단계별 지침
- [ ] 예제 포함 (복잡한 경우)

### 작성 후

- [ ] 실제 시나리오 테스트
- [ ] 팀원 피드백 (프로젝트 레벨)
- [ ] Git 커밋 (프로젝트 레벨)
- [ ] 문서화 (README 업데이트)

---

## 고급 기능

### 1. Extended Thinking

특정 키워드 사용 시 깊은 사고 모드 활성화:

```markdown
---
description: Complex architectural analysis
---

Analyze this architecture with extended thinking:

[복잡한 시스템 분석 요청]
```

---

### 2. Bash Integration

```markdown
---
allowed-tools: Bash
---

Current system info:
!uname -a
!node --version
!npm --version

Based on this environment, suggest optimal setup.
```

---

### 3. File Reference Patterns

```markdown
---
description: Review all config files
---

Review configuration:

@**/*.config.js
@package.json
@tsconfig.json

Suggest improvements for consistency.
```

---

## 추가 리소스

### 공식 문서

- [Slash Commands](https://code.claude.com/docs/en/slash-commands)
- [Skills](https://code.claude.com/docs/en/skills)
- [Subagents](https://code.claude.com/docs/en/sub-agents)
- [CHANGELOG](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md)

### 관련 가이드

- [[skills-guide]] - Skills 시스템 가이드
- [[subagents-guide]] - 서브에이전트 베스트 프랙티스

---

## 핵심 요약

1. ✅ **단순함 유지** - 복잡하면 Skill이나 Subagent 사용
2. ✅ **Description 필수** - Skill tool 호환성
3. ✅ **적절한 Scope** - 프로젝트 vs 개인
4. ✅ **인자 활용** - `$ARGUMENTS`, `$1`, `$2` 등
5. ✅ **도구 제한** - `allowed-tools`로 보안 강화
6. ✅ **context: fork** - 무거운 작업은 독립 컨텍스트에서
7. ✅ **hooks 활용** - 이벤트 기반 자동화
8. ✅ **조직화** - 서브디렉토리로 분류
9. ✅ **팀 공유** - Git으로 버전 관리

---

## 업데이트 이력

- **2026-01-16 (v2)**: 공식 문서 최신 반영
  - 빌트인 커맨드 업데이트 (`/security-review`, `/exit` 추가, 설명 수정)
  - Skill Tool 섹션 강화 (비활성화 방법, 권한 규칙, 문자 예산 제한)
  - Commands vs Skills 비교표 개선
- **2026-01-16 (v1)**: v2.1.x 신규 기능 반영 (40+ 빌트인 커맨드, context: fork, hooks, Skill tool 연동)
- **2025-11-01**: 초기 작성 (공식 문서 기반 정리)
