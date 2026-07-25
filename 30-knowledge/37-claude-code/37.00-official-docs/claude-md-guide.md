# CLAUDE.md - Source of Truth

> **Source**: [code.claude.com/docs/en/memory](https://code.claude.com/docs/en/memory)
> **Updated**: 2026-06-05 (v2.1.165) - requiredMinimumVersion 관리 설정, Opus 4.8/lean 프롬프트, GFM 체크박스 반영
> **Purpose**: CLAUDE.md 작성 시 유일한 참조 문서

---

## 1. 개요

CLAUDE.md는 Claude Code가 세션 시작 시 자동 로드하는 설정 파일. 프로젝트 컨텍스트, 작업 규칙, 코드 스타일을 정의.

---

## 2. 전체 계층 구조 (Hierarchy)

Claude Code는 다음 순서로 메모리를 로드 (모두 병합됨):

| 우선순위 | 위치 | 용도 |
|---------|------|------|
| 1 (최상위) | Managed Policy | 조직 전사 강제 규칙 |
| 2 | `~/.claude/CLAUDE.md` | 개인 전역 설정 |
| 3 | `./CLAUDE.md` 또는 `./.claude/CLAUDE.md` | 프로젝트 설정 |
| 4 | `./.claude/rules/*.md` | 프로젝트 규칙 (자동 로드) |
| 5 | `~/.claude/rules/*.md` | 개인 전역 규칙 (자동 로드) |
| 6 | `./CLAUDE.local.md` | 로컬 전용 (gitignore 권장) |
| 7 | Auto Memory | 세션 간 자동 학습 기록 |

### Managed Policy (조직 전사)

조직 IT/DevOps가 관리하는 최상위 규칙. 개인 사용자가 변경 불가.

| OS | 경로 |
|----|------|
| macOS | `/Library/Application Support/ClaudeCode/CLAUDE.md` |
| Linux | `/etc/claude-code/CLAUDE.md` |
| Windows | `C:\Program Files\ClaudeCode\CLAUDE.md` |

MDM, Group Policy, Ansible 등으로 배포.

### 버전 강제 managed settings (v2.1.163)

```json
{
  "requiredMinimumVersion": "2.1.150",
  "requiredMaximumVersion": "2.1.165"
}
```

**(v2.1.163)** Claude Code 버전이 허용 범위를 벗어나면 시작을 거부하고 승인된 버전으로 안내. 조직이 사용 버전을 통제할 때 사용.

### `allowAllClaudeAiMcps` managed setting (v2.1.149)

**(v2.1.149)** 엔터프라이즈용. `managed-mcp.json`과 함께 claude.ai 클라우드 MCP 커넥터를 로드.

---

## 3. Auto Memory (v2.1.32, 신규)

Claude가 세션 작업 중 자동으로 패턴, 명령어, 선호도를 기록하는 시스템.

### 저장 위치

```
~/.claude/projects/<project>/memory/
├── MEMORY.md           # 인덱스 (매 세션 첫 200줄 자동 로드)
├── debugging.md        # 토픽별 상세 노트
└── api-conventions.md  # Claude가 자동 생성
```

- `<project>`는 git 저장소 루트에서 파생
- git worktree는 별도 디렉토리
- git 외부는 작업 디렉토리 기준

### 동작

- **세션 시작**: `MEMORY.md` 첫 200줄만 자동 로드
- **토픽 파일**: startup 미로드, Claude가 필요할 때 on-demand 읽기
- **기록 방식**: Claude가 작업 중 자동 기록 또는 직접 지시 ("remember that we use pnpm")

### 제어

```bash
export CLAUDE_CODE_DISABLE_AUTO_MEMORY=1  # 비활성화
export CLAUDE_CODE_DISABLE_AUTO_MEMORY=0  # 활성화
```

`/memory` 커맨드로 파일 선택기 열기 가능 (CLAUDE.md + Auto Memory 포함).

### Worktree 간 공유 (v2.1.63)

프로젝트 설정과 auto memory가 같은 git 저장소의 모든 worktree에서 공유됨.

### 커스텀 메모리 디렉토리 (v2.1.74)

```json
{
  "autoMemoryDirectory": "/path/to/custom/memory"
}
```

`settings.json`에서 auto-memory 저장 위치를 변경 가능.

### 메모리 파일 타임스탬프 (v2.1.75)

메모리 파일에 last-modified 타임스탬프가 추가되어, Claude가 최신/오래된 메모리를 구분 가능.

### MEMORY.md 크기 제한 (v2.1.83)

`MEMORY.md` 인덱스가 200줄 제한에 더해 **25KB 크기 제한**도 추가됨. 둘 중 먼저 도달하는 기준으로 잘림.

---

## 4. @import 문법

외부 파일을 참조하여 CLAUDE.md를 모듈화:

```markdown
@30-knowledge/37-claude-code/skills-guide.md
@./docs/coding-standards.md
@~/.claude/my-project-instructions.md
```

### 규칙

- 상대 경로 또는 절대 경로 사용 가능
- 참조된 파일은 컨텍스트에 자동 포함
- Code span/code block 내 `@`는 import 처리 안 됨
- **Recursive import 최대 깊이: 5 hops**
- 외부 import 포함 프로젝트 첫 실행 시 **승인 다이얼로그** 표시
- 바이너리 파일(이미지, PDF)은 자동 제외

### HTML 주석 처리 (v2.1.72)

CLAUDE.md 내 HTML 주석(`<!-- ... -->`)은 자동 주입 시 Claude에게 숨겨짐. Read 도구로 직접 읽을 때는 보임. 내부 메모를 Claude에게 노출하지 않으면서 유지 가능.

### Worktree 환경 권장 패턴

```markdown
# CLAUDE.local.md에서 home directory import로 공유
@~/.claude/my-project-instructions.md
```

worktree마다 `CLAUDE.local.md`가 별도 존재하므로 home directory import 활용.

---

## 5. .claude/rules/ 자동 로드

`.claude/rules/` 내 모든 `.md` 파일 자동 로드. 서브디렉토리 재귀 탐색 지원.

```
.claude/
├── CLAUDE.md
├── rules/
│   ├── git.md
│   ├── security.md
│   ├── frontend/
│   │   └── react.md
│   └── backend/
│       └── api.md
└── settings.json
```

조건부 규칙은 [[rules-guide]] 참조.

---

## 6. --add-dir + CLAUDE.md 로딩 (v2.1.20)

`--add-dir`로 추가된 디렉토리의 CLAUDE.md와 rules도 로드 가능:

```bash
CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1 claude --add-dir ../shared-config
```

로드 대상: `CLAUDE.md`, `.claude/CLAUDE.md`, `.claude/rules/*.md`

기본값은 비활성화. 환경변수 설정 필요.

---

## 7. 권장 포함 내용

### 필수

1. **프로젝트 개요**: 목적, 기술 스택
2. **폴더 구조**: 주요 디렉토리 설명
3. **코딩 규칙**: 스타일 가이드, 네이밍 컨벤션
4. **작업 규칙**: 파일 작업, Git, 보안 규칙

### 선택

- 사용자 프로필 / 작업 스타일
- 도구 설정 (MCP, 외부 도구)
- 자주 쓰는 명령어

---

## 8. settings.json과의 관계

| 항목 | CLAUDE.md | settings.json |
|------|-----------|---------------|
| 프로젝트 지침 | O | X |
| 코딩 스타일 | O | X |
| 도구 권한 | X | O |
| 모델 설정 | X | O |
| 환경 변수 | X | O |

**원칙**: 지침은 CLAUDE.md, 설정은 settings.json

### `/config` 영구 저장 (v2.1.119)

`/config`로 변경한 설정이 `~/.claude/settings.json`에 영구 저장됨. 우선순위는 project > local > policy 순으로 override. 이전에는 세션 한정이었으나 이제 재시작 후에도 유지.

### `claude project purge` (v2.1.126)

```bash
claude project purge [path]
```

해당 프로젝트의 모든 Claude Code state(세션, auto memory, 캐시)를 삭제. 프로젝트 정리 또는 fresh start에 유용.

### `CLAUDE_CODE_HIDE_CWD` (v2.1.119)

```bash
export CLAUDE_CODE_HIDE_CWD=1
```

시작 로고에서 작업 디렉토리를 숨김. 데모/녹화 시 경로 노출 방지.

### Prompt Cache TTL 제어 (v2.1.108~2.1.129)

- `ENABLE_PROMPT_CACHING_1H=1` (v2.1.108): API key/Bedrock/Vertex/Foundry에서 1시간 prompt cache TTL 활성화 (기존 `ENABLE_PROMPT_CACHING_1H_BEDROCK` deprecated)
- `FORCE_PROMPT_CACHING_5M=1`: 5분 TTL 강제
- `DISABLE_PROMPT_CACHING*` 설정 시 시작 경고 (v2.1.108)
- **(v2.1.129 수정)** 1시간 prompt cache TTL이 5분으로 다운그레이드되던 버그 수정
- **(v2.1.132 수정)** Bedrock/Vertex 400 errors with `ENABLE_PROMPT_CACHING_1H` 수정

---

## 9. 작성 팁

### 간결하게 유지

- 목표: 150줄 이하
- 상세 내용은 @import 또는 rules/ 활용
- 반복 방지: 한 곳에만 정의

### 명확한 규칙

```markdown
# Good
- **커밋 전**: `npm test` 실행 필수

# Bad
- 커밋 전에 테스트를 실행하면 좋을 것 같아요
```

### 주의사항

1. 민감정보 제외 (API 키, 비밀번호 절대 금지)
2. 경로 일관성 (팀 공유 시 상대 경로 권장)
3. CLAUDE.local.md는 .gitignore에 추가
4. 정기적으로 프로젝트 변화에 맞춰 갱신

### 시스템 프롬프트 / 모델 기본값 (v2.1.154)

- **(v2.1.154)** Opus 4.8 출시. 기본 high effort, 가장 어려운 작업은 `/effort xhigh`
- **(v2.1.154)** **lean 시스템 프롬프트**가 Haiku/Sonnet/Opus 4.7 이전 모델을 제외한 모든 모델에서 기본값. 시스템 컨텍스트가 가벼워져 CLAUDE.md 등 사용자 지침의 상대 비중이 커짐
- **(v2.1.154)** Claude가 스스로 판단 가능한 경우 multiple-choice 질문을 자제하고 바로 진행 — 충분한 컨텍스트가 있으면 묻지 않음
- **(v2.1.149)** 마크다운 출력이 GFM task list 체크박스(`- [ ] todo` / `- [x] done`)를 일반 불릿이 아닌 체크박스로 렌더링. CLAUDE.md/메모리의 체크리스트 표시에 영향

### 알려진 수정

- **(v2.1.101)** 인식되지 않는 hook 이벤트 이름에 대한 settings 내구성 개선 (설정 파일에 미래 hook 이벤트가 있어도 크래시하지 않음)
- **(v2.1.94)** `forceRemoteSettingsRefresh` 정책과 함께 기본 effort 수준이 medium에서 high로 변경 (API-key, Bedrock/Vertex/Foundry, Team, Enterprise)
- **(v2.1.90)** 도구 호출 중 CLAUDE.md 자동 로드 시 축소된 search/read 요약 배지가 fullscreen 스크롤백에서 여러 번 표시되던 버그 수정
- **(v2.1.88)** 긴 세션에서 중첩 CLAUDE.md 파일이 수십 번 재주입되는 버그 수정
- **(v2.1.86)** Read 도구가 compact line-number 포맷 사용 + 변경 없는 재읽기 중복 제거 (토큰 절약)

---

## Sources

- [Manage Claude's memory](https://code.claude.com/docs/en/memory)
- [Claude Code Changelog](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md)

## Related

- [[rules-guide]] - .claude/rules/ 상세 가이드
- [[skills-guide]] - Skills 시스템 가이드
- [[subagents-guide]] - Subagent 가이드

---

## Update History

- **2026-06-05**: v2.1.143~2.1.165 변경사항 반영
  - **버전 강제 managed settings (v2.1.163)**: `requiredMinimumVersion`/`requiredMaximumVersion`으로 허용 범위 밖 버전 시작 거부
  - **`allowAllClaudeAiMcps` managed setting (v2.1.149)**: claude.ai 클라우드 MCP 커넥터 로드
  - **Opus 4.8 출시 + lean 시스템 프롬프트 기본화 (v2.1.154)**: 대부분 모델에서 lean 프롬프트가 기본 — 사용자 지침 상대 비중 증가
  - **불필요한 multiple-choice 질문 자제 (v2.1.154)**: 충분한 컨텍스트 시 바로 진행
  - **GFM task list 체크박스 렌더링 (v2.1.149)**: `- [ ]`/`- [x]`를 체크박스로 표시
  - **`/usage` 카테고리별 분해 (v2.1.149)**: skills/subagents/plugins/MCP별 limits 사용량 표시
  - `NO_COLOR`/`FORCE_COLOR`가 settings.json `env`에서 Claude Code 자체 UI 색상을 벗기던 버그 수정 — 이제 서브프로세스에만 적용 (v2.1.143)
- **2026-05-15**: v2.1.133~2.1.142 변경사항 반영
  - **`/goal` 명령 (v2.1.139)**: 여러 turn에 걸쳐 유지되는 완료 조건(goal) 정의. Claude가 매 응답마다 goal 충족 여부 자가 점검
  - **`/scroll-speed` 명령 (v2.1.139)**: 트랜스크립트 스크롤 속도 사용자 설정
  - **Transcript view 네비게이션 (v2.1.139)**: `?`로 단축키, `{`/`}`로 prompt 간 이동
  - **Rewind "Summarize up to here" (v2.1.141)**: 특정 지점까지의 컨텍스트를 요약본으로 대체 — 컨텍스트 압축의 새 옵션
  - **`/feedback`이 최근 세션 첨부 (v2.1.141)**: 피드백 제출 시 최근 세션 컨텍스트 동봉 가능
  - **Compaction prompt 민감 instruction 보존 (v2.1.139)**: 압축 후에도 CLAUDE.md의 민감 instruction 유지
  - **MCP 서버가 `CLAUDE_PROJECT_DIR` 받음 (v2.1.139)**: 프로젝트 경로를 환경변수로 직접 인식 — CLAUDE.md 기반 프로젝트 인식과 시너지
  - **`CLAUDE_CODE_SESSION_ID`/`CLAUDE_CODE_DISABLE_ALTERNATE_SCREEN`는 기존 노출 유지 (v2.1.132)**
- **2026-05-07**: v2.1.115~2.1.132 변경사항 반영
  - **`/config` 영구 저장 (v2.1.119)**: 설정이 `~/.claude/settings.json`에 영구 저장. project/local/policy override 정밀화
  - **`claude project purge [path]` (v2.1.126)**: 프로젝트의 모든 Claude Code state 삭제
  - **`CLAUDE_CODE_HIDE_CWD` 환경변수 (v2.1.119)**: 시작 로고에서 작업 디렉토리 숨김
  - **`DISABLE_UPDATES` 환경변수 (v2.1.118)**: 모든 업데이트 경로 차단(`claude update` 포함)
  - **`CLAUDE_CODE_DISABLE_ALTERNATE_SCREEN=1` (v2.1.132)**: 풀스크린 렌더링 opt-out
  - **`CLAUDE_CODE_PACKAGE_MANAGER_AUTO_UPDATE` (v2.1.129)**: 백그라운드 자동 업그레이드 제어
  - Prompt cache 1h TTL 5m으로 다운그레이드 버그 수정 (v2.1.129) 및 Bedrock/Vertex 400 errors 수정 (v2.1.132)
  - 멀티라인 paste의 newline 손실/CRLF 빈 줄 추가 버그 수정 (v2.1.119)
  - `/clear`가 터미널 탭 타이틀 reset 안 하던 버그 수정 (v2.1.129)
  - `verbose` 설정이 재시작 후 persist 안 하던 버그 수정 (v2.1.119)
  - 컨텍스트 percent inflation 및 premature autocompaction (Opus 4.7) 수정 (v2.1.117)
- **2026-04-19**: v2.1.110~2.1.114 — CLAUDE.md/Memory 시스템 자체 변경 없음, 버전만 동기화
  - 관련 환경 변경: `Ctrl+A`/`Ctrl+E` readline 기본 동작 복원 (v2.1.113), `Ctrl+U` 입력 버퍼 전체 삭제 (v2.1.111, `Ctrl+Y`로 복원), `Ctrl+L` 전체 화면 redraw (v2.1.111)
  - Auto mode가 Max 구독자에게 Opus 4.7 사용 시 기본 제공 (v2.1.111) — `--enable-auto-mode` 플래그 불필요
  - Opus 4.7 `xhigh` effort level 추가 (v2.1.111, `high`와 `max` 사이)
  - `/effort` 인터랙티브 슬라이더 (v2.1.111) — 인자 없이 호출 시
  - 세션 복귀 시 자동 recap이 미발신 입력 작성 중 발화하던 버그 수정 (v2.1.114)
- **2026-04-15**: v2.1.105~2.1.109 변경사항 반영
  - **Recap 기능 추가 (v2.1.108)**: 세션 복귀 시 자동 요약 컨텍스트 제공. `/config`에서 설정, `/recap`으로 수동 호출. 텔레메트리 disabled 환경은 `CLAUDE_CODE_ENABLE_AWAY_SUMMARY`로 강제 활성화
  - `ENABLE_PROMPT_CACHING_1H` 환경 변수 (v2.1.108) - API key/Bedrock/Vertex/Foundry에서 1시간 prompt cache TTL opt-in (기존 `ENABLE_PROMPT_CACHING_1H_BEDROCK` deprecated). `FORCE_PROMPT_CACHING_5M`로 5분 TTL 강제 가능
  - `DISABLE_PROMPT_CACHING*` 설정 시 시작 경고 표시 (v2.1.108)
  - `DISABLE_TELEMETRY` 설정한 구독자가 5분 TTL로 떨어지던 버그 수정 (v2.1.108)
  - `/undo`가 `/rewind` alias로 추가 (v2.1.108)
  - `CLAUDE_ENV_FILE`(예: `~/.zprofile`)이 `#` 주석 줄로 끝나면 Bash 도구 출력 사라지던 버그 수정 (v2.1.108)
- **2026-04-13**: v2.1.93~2.1.101 변경사항 반영
  - 기본 effort 수준 medium에서 high로 변경 (v2.1.94, API-key/Bedrock/Vertex/Foundry/Team/Enterprise)
  - settings 내구성 개선: 인식되지 않는 hook 이벤트 이름 처리 (v2.1.101)
  - OS CA certificate store 기본 신뢰 (v2.1.101) - 엔터프라이즈 TLS 프록시 지원
- **2026-04-04**: v2.1.90~2.1.92 변경사항 반영
  - CLAUDE.md 자동 로드 시 축소 배지 다중 표시 수정 (v2.1.90)
  - `forceRemoteSettingsRefresh` 정책: 원격 managed settings 강제 갱신, 실패 시 종료 (v2.1.92)
  - `managed-settings.d/` drop-in과 관련된 조직 정책 강화
- **2026-03-31**: v2.1.79~2.1.88 변경사항 반영
  - `MEMORY.md` 25KB 크기 제한 추가 (v2.1.83)
  - 중첩 CLAUDE.md 재주입 버그 수정 (v2.1.88)
  - Read 도구 compact format + 중복 제거 (v2.1.86)
- **2026-03-18**: v2.1.51~2.1.78 변경사항 반영
  - Worktree 간 프로젝트 설정/auto memory 공유 (v2.1.63)
  - `autoMemoryDirectory` 설정 (v2.1.74)
  - 메모리 파일 last-modified 타임스탬프 (v2.1.75)
  - HTML 주석 자동 주입 시 숨김 처리 (v2.1.72)
  - `InstructionsLoaded` 훅 이벤트 (v2.1.69)
- **2026-02-22**: 전면 갱신 (source of truth 목적)
  - Auto Memory 시스템 신규 섹션 (v2.1.32)
  - Managed Policy 계층 추가 (최상위)
  - Hierarchy 표 전면 수정 (7단계)
  - --add-dir + CLAUDE.md 로딩 (v2.1.20)
  - Import 안전 동작 (승인 다이얼로그, 5 hops 제한)
  - MCP 섹션 제거 (별도 문서로 분리)
- **2026-01-19**: 초기 작성
