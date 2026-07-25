# .claude/rules/ - Source of Truth

> **Source**: [code.claude.com/docs/en/memory](https://code.claude.com/docs/en/memory)
> **Updated**: 2026-06-05 (v2.1.165) - 셸 startup 파일 쓰기 프롬프트, WebFetch 규칙 우선순위, read-before-edit grep 완화, $HOME deny 규칙 반영
> **Purpose**: .claude/rules/ 시스템 유일한 참조 문서

---

## 1. 개요

`.claude/rules/` 디렉토리는 CLAUDE.md를 여러 파일로 모듈화하여 관리. 모든 `.md` 파일이 자동 로드됨. 서브디렉토리도 재귀 탐색.

---

## 2. 기본 구조

```
your-project/
├── .claude/
│   ├── CLAUDE.md
│   └── rules/
│       ├── code-style.md
│       ├── testing.md
│       ├── security.md
│       ├── frontend/
│       │   └── react.md
│       └── backend/
│           └── api.md
```

---

## 3. 저장 위치 및 우선순위

| 위치 | 경로 | 적용 범위 |
|------|------|----------|
| 프로젝트 | `./.claude/rules/*.md` | 해당 프로젝트 |
| 사용자 | `~/.claude/rules/*.md` | 모든 프로젝트 |

**우선순위** (높음 -> 낮음):
1. Enterprise policy
2. 프로젝트 CLAUDE.md
3. 프로젝트 rules
4. 사용자 CLAUDE.md
5. 사용자 rules
6. CLAUDE.local.md

`paths` 필드가 없는 규칙은 모든 파일에 무조건 적용.

---

## 4. 조건부 규칙 (Path-Specific Rules)

YAML frontmatter로 특정 파일에만 규칙 적용 가능.

### 작동하는 형식

```markdown
---
globs: **/*.ts, src/**/*.tsx
---

# API 개발 규칙
- 모든 API 엔드포인트에 입력 검증 필수
```

### paths 필드 개선 (v2.1.84)

**(v2.1.84)** Rules와 Skills의 `paths:` frontmatter가 **YAML 리스트 형식**을 정식 지원:

```yaml
# v2.1.84부터 작동 - YAML 리스트
paths:
  - "src/**/*.ts"
  - "lib/**/*.tsx"

# 기존 방식도 계속 작동
globs: **/*.ts, src/**/*.tsx
```

**이전 버그 참고** (Issue #17204): v2.1.83 이전에는 YAML 배열 형식이 작동하지 않았음. v2.1.84에서 수정됨.

**현재 권장**: `paths:` YAML 리스트 또는 `globs:` CSV 형식 모두 사용 가능.

### 알려진 제한사항

1. **user-level paths 미작동**: `~/.claude/rules/`에서 `paths:` / `globs:` 조건부 로딩이 완전히 비작동 (Issue #21858, 미해결)
2. **세션 내 해제 안 됨**: 한 번 로드된 조건부 규칙은 다른 디렉토리로 이동해도 세션 내에서 계속 활성 (Issue #16299, 미해결)
3. **Git worktree 무시**: Worktree 내에서 paths/globs 필터링이 무시됨 (Issue #23569)
4. **(v2.1.69 수정)** print 모드(`claude -p`)에서 조건부 rules와 중첩 CLAUDE.md가 로드되지 않던 버그 수정됨

### Glob 패턴

| 패턴 | 매칭 대상 |
|------|-----------|
| `**/*.ts` | 모든 디렉토리의 TypeScript 파일 |
| `src/**/*` | src/ 하위 모든 파일 |
| `*.md` | 프로젝트 루트의 마크다운 파일 |
| `**/*.{ts,tsx}` | ts와 tsx 파일 모두 |
| `{src,lib}/**/*.ts` | src와 lib 디렉토리 |

---

## 5. --add-dir 디렉토리 rules 로딩 (v2.1.20)

추가 디렉토리의 rules도 로드 가능:

```bash
CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1 claude --add-dir ../shared-config
```

공유 규칙 저장소를 여러 프로젝트에서 참조할 때 유용.

---

## 6. @import 활용

rules 파일에서 외부 문서 참조 가능:

```markdown
# Subagent 작성 규칙

@/path/to/official-docs/subagents-guide.md

## 추가 규칙
- 프로젝트 특화 규칙...
```

Recursive import 최대 깊이: 5 hops.

---

## 7. Symlink 활용

여러 프로젝트에서 공통 규칙 공유:

```bash
# 공유 rules 디렉토리 심링크
ln -s ~/shared-claude-rules .claude/rules/shared

# 개별 규칙 파일 심링크
ln -s ~/company-standards/security.md .claude/rules/security.md
```

순환 심링크는 자동 감지되어 안전하게 처리.

**(v2.1.89)** `Edit(//path/**)` 및 `Read(//path/**)` allow 규칙이 이제 심링크의 **해결된 대상 경로**(resolved symlink target)를 확인. 이전에는 요청 경로만 확인했으나, 이제 실제 파일 위치 기준으로 권한 매칭.

### Bash Permission 강화 (v2.1.97~2.1.101)

- **(v2.1.98)** 백슬래시 이스케이프된 플래그(`\-flag`)로 Bash 도구 권한 우회 방지
- **(v2.1.98)** 복합 Bash 명령어(`cmd1 && cmd2`)가 강제 권한 프롬프트를 우회하던 버그 수정
- **(v2.1.98)** 읽기 전용 명령어에 env-var 접두사가 있으면 안전한 것으로 알려진 경우에만 프롬프트 생략
- **(v2.1.98)** `/dev/tcp/...` 또는 `/dev/udp/...`로의 리다이렉트 시 프롬프트 표시
- **(v2.1.101)** `permissions.deny` 규칙이 PreToolUse 훅의 `permissionDecision: "ask"` 결정을 올바르게 오버라이드

### WSL 정책 상속 (v2.1.118)

`wslInheritsWindowsSettings` 정책 추가. WSL 환경에서 Windows side의 managed settings(보안 정책 포함)를 자동 상속.

```json
{
  "wslInheritsWindowsSettings": true
}
```

### Auto Mode 기본 리스트 확장 (v2.1.118)

`allow`/`soft_deny`/`environment` 리스트에 `"$defaults"` 토큰 사용 시 빌트인 기본 리스트를 그대로 유지하면서 사용자 항목 추가:

```json
{
  "permissions": {
    "allow": ["$defaults", "Bash(my-tool:*)"]
  }
}
```

### `blockedMarketplaces` 패턴 강제 (v2.1.119)

`blockedMarketplaces`의 `hostPattern`과 `pathPattern`이 정확히 enforce 되도록 수정. 이전에는 일부 패턴이 적용 안 되던 보안 버그 해결.

### `allowManagedDomainsOnly` (v2.1.126)

이 설정이 정확히 enforce 되도록 수정 — 관리되는 도메인 외에는 모든 외부 호출이 거부됨.

### In-project Path Allow Rules (v2.1.129)

`Edit(.claude/**)`, `Read(./src/**)` 등 프로젝트 내부 경로에 대한 allow rule이 honor 되도록 수정. 이전에는 일부 in-project 패턴이 무시되던 버그.

### `deniedMcpServers` Wildcard Scheme (v2.1.129)

```json
{
  "deniedMcpServers": ["http://*", "ws://*"]
}
```

스키마 wildcard로 차단 가능. URL prefix 패턴이 정확히 매칭되도록 수정.

### Server-managed Settings Policy (v2.1.129)

엔터프라이즈 사용자에게 server-managed settings policy가 정확히 적용되도록 수정. 이전에는 일부 케이스에서 적용 안 되던 버그.

### 병렬 Shell Tool 거부 처리 (v2.1.128)

병렬 shell tool calls에서 read-only 명령 하나가 실패하면 형제(sibling) 명령들도 자동 cancel. 이전에는 형제들이 계속 실행되던 동작.

### PowerShell Tool 권한 (v2.1.119, v2.1.126)

- **(v2.1.119)** PowerShell 명령이 permission mode에서 Bash와 동일하게 auto-approvable
- **(v2.1.126)** Windows에서 PowerShell이 primary shell로 인식 (Git Bash 부재 시)
- **(v2.1.126)** PowerShell tool에서 bare `--`가 stop-parsing flag로 mis-flag 되던 버그 수정

### 셸 Startup 파일 / 빌드 설정 쓰기 프롬프트 (v2.1.160)

- **(v2.1.160)** 셸 startup 파일(`.zshenv`, `.zlogin`, `.bash_login`)과 `~/.config/git/`에 쓰기 전 프롬프트 표시 — 의도치 않은 명령 실행 방지
- **(v2.1.160)** `acceptEdits` 모드에서도 코드 실행을 부여하는 빌드 도구 설정 파일에 쓰기 전 프롬프트: `.npmrc`, `.yarnrc*`, `bunfig.toml`, `.bazelrc`, `.pre-commit-config.yaml`, `.devcontainer/` 등

### Read-before-edit grep 완화 (v2.1.160, v2.1.144)

- **(v2.1.160)** `grep`/`egrep`/`fgrep` 단일 파일 명령이 read-before-edit 체크를 만족 — `grep`으로 파일을 본 후 별도 `Read` 없이 Edit 가능
- **(v2.1.144)** `head`/`tail` 파일 보기도 read-before-edit 체크를 만족. `egrep`/`fgrep`/`git grep`/`git diff`의 "no matches"(exit code 1)가 더 이상 명령 실패로 보고되지 않음

### WebFetch 권한 규칙 우선순위 (v2.1.162)

**(v2.1.162)** WebFetch 권한 규칙이 빌트인 preapproved 도메인에도 적용되도록 수정. 명시적 `WebFetch(domain:...)` deny/ask/allow 규칙이 preapproved-host 자동 허용보다 우선.

### `$HOME` 경로 deny 규칙 (v2.1.163)

**(v2.1.163)** home 디렉토리 경로에 대한 deny 규칙(예: `Read(~/Desktop/**)`)이 `$HOME`을 통해 경로를 참조하는 Bash 명령도 차단하도록 수정.

### hook `if` `$()`/`$VAR` 매칭 (v2.1.163)

**(v2.1.163)** hook `if: "Bash(...)"` 조건이 `$()`나 `$VAR`를 포함한 모든 Bash 명령에 잘못 발화하던 버그 수정 — 이제 subshell과 backtick 내부 명령에도 정확히 매칭.

### Windows 권한 규칙 / Read deny (v2.1.162)

- **(v2.1.162)** 백슬래시 표기(`~\`, `\\server\share`)나 대소문자 변형 경로로 작성된 Windows 권한 규칙이 매칭 안 되던 버그 수정
- **(v2.1.162)** Read deny 규칙이 Glob/Grep 결과에서 파일을 숨기도록 수정

### 데이터 유출 탐지 / 위험 경로 (v2.1.154)

- **(v2.1.154)** auto-mode classifier의 데이터 유출(특히 저장소 내용 대량 전송) 탐지 개선
- **(v2.1.154)** `HOME`에 trailing slash가 있을 때 `rm -rf $HOME`이 위험 경로로 차단 안 되던 버그 수정

### PowerShell `cd` 권한 우회 (v2.1.149)

- **(v2.1.149)** PowerShell 빌트인 `cd` 함수(`cd..`, `cd\`, `cd~`, `X:`)가 작업 디렉토리를 감지 없이 변경해 이후 명령이 워크스페이스 밖을 읽던 권한 우회 버그 수정
- **(v2.1.149)** git worktree에서 sandbox 쓰기 allowlist가 공유 `.git`만이 아닌 main 저장소 루트 전체를 덮던 버그 수정 (`hooks/`, `config`는 denied)
- **(v2.1.149)** PowerShell prefix/wildcard allow 규칙(예: `PowerShell(dotnet.exe build *)`)이 네이티브 실행 파일/스크립트를 사전 승인 안 하던 버그 수정
- **(v2.1.145)** 비-allowlist 환경변수에 대한 bare 변수 할당이 자동 승인되던 권한 프롬프트 우회 버그 수정

### Find Tool Allow Rule (v2.1.114) 재정의 — 보충

`Bash(find:*)` allow rule 하에서도 `find -exec`/`find -delete`는 자동 승인되지 않음. 필요 시 명시적 권한 부여. **(v2.1.120 보강)** `find` 명령이 file descriptor를 소진해 host가 죽던 버그가 수정됨 (macOS/Linux).

---

## 8. Best Practice

### DO

- 주제별 분리: 각 파일은 하나의 주제만 (testing.md, api-design.md)
- 명확한 파일명: 파일명만으로 내용 파악 가능
- 조건부 규칙은 `globs:` CSV 형식 사용
- 정기적 검토: 프로젝트 변화에 맞춰 갱신

### DON'T

- 모든 규칙을 조건부로 만들기
- 너무 세분화된 파일 구조
- 중복되는 규칙
- user-level rules에서 조건부 규칙 의존 (현재 미작동)

---

## 9. 일반적인 규칙 구성

| 파일 | 용도 |
|------|------|
| `code-style.md` | 코드 스타일, 포맷팅 |
| `testing.md` | 테스트 작성 컨벤션 |
| `security.md` | 보안 요구사항 |
| `git.md` | Git 워크플로우 |
| `api-design.md` | API 설계 원칙 |

---

## Sources

- [Manage Claude's memory](https://code.claude.com/docs/en/memory)
- [Issue #17204 - globs vs paths](https://github.com/anthropics/claude-code/issues/17204)
- [Issue #16299 - paths scope bug](https://github.com/anthropics/claude-code/issues/16299)
- [Issue #21858 - user-level paths](https://github.com/anthropics/claude-code/issues/21858)

## Related

- [[claude-md-guide]] - CLAUDE.md 가이드
- [[skills-guide]] - Skills 시스템 가이드

---

## Update History

- **2026-06-05**: v2.1.143~2.1.165 변경사항 반영
  - **셸 startup 파일 / 빌드 설정 쓰기 프롬프트 (v2.1.160)**: `.zshenv` 등 + `acceptEdits`에서 `.npmrc`/`.bazelrc`/`.devcontainer/` 등
  - **Read-before-edit grep/head/tail 완화 (v2.1.160, v2.1.144)**: 단일 파일 grep/head/tail이 read 체크 만족, no-match exit 1이 실패로 보고 안 됨
  - **WebFetch 권한 규칙 우선순위 (v2.1.162)**: 명시적 규칙이 preapproved-host 자동 허용보다 우선
  - **`$HOME` 경로 deny 규칙 (v2.1.163)**: `$HOME` 참조 Bash 명령도 차단
  - **hook `if` `$()`/`$VAR` 매칭 수정 (v2.1.163)**: subshell/backtick 내부도 정확 매칭
  - **Windows 백슬래시 권한 규칙 + Read deny Glob/Grep 숨김 (v2.1.162)**
  - **데이터 유출 탐지 개선 + `rm -rf $HOME` trailing slash 차단 (v2.1.154)**
  - **PowerShell `cd` 권한 우회 + worktree sandbox allowlist + bare 변수 할당 우회 수정 (v2.1.149, v2.1.145)**
- **2026-05-15**: v2.1.133~2.1.142 변경사항 반영
  - **`settings.autoMode.hard_deny` (v2.1.136)**: auto mode에서 무조건 차단할 항목 정의. allow/soft_deny와 별개로 우선 적용 — escape 불가능
  - **`parentSettingsBehavior` (v2.1.133)**: managed/policy 설정의 병합 방식을 admin-tier에서 제어. 기존 user 설정과 어떻게 병합/덮어쓸지 지정
  - **`worktree.baseRef` 설정 (v2.1.133)**: 새 worktree 분기 기준을 `fresh`(원격 HEAD) 또는 `head`(로컬 HEAD)로 선택
  - **`sandbox.bwrapPath` / `sandbox.socatPath` (v2.1.133)**: bubblewrap/socat 바이너리 경로를 명시. 사용자 정의 설치 환경에서 sandbox 활성화 가능
  - **Hooks가 `effort.level` 받음 (v2.1.133)**: hook context에 `effort.level` 필드 + `$CLAUDE_EFFORT` 환경변수 노출 — effort에 따라 hook 분기 가능
  - **Hook JSON 출력 `terminalSequence` 필드 (v2.1.141)**: 알림 hook이 터미널 escape sequence를 직접 출력 가능
  - **병렬 세션 401 race condition 수정 (v2.1.133)**
  - **Edit/Write allow rule이 drive root 패턴 인식 (v2.1.133)**: `Edit(C:\\**)` 같은 윈도우 root-level 패턴 정상 매칭
- **2026-05-07**: v2.1.115~2.1.132 변경사항 반영
  - **WSL Windows-side managed settings 상속 (v2.1.118)**: `wslInheritsWindowsSettings` 정책 추가
  - **`"$defaults"` 토큰으로 auto mode 빌트인 리스트 확장 (v2.1.118)**: allow/soft_deny/environment에서 사용
  - **`blockedMarketplaces` host/path 패턴 enforce (v2.1.119)**
  - **`allowManagedDomainsOnly` 정책 정확 enforce (v2.1.126)**
  - **In-project path allow rules honor (v2.1.129)**: `Edit(./.claude/**)` 등 프로젝트 내부 패턴
  - **`deniedMcpServers` wildcard scheme (v2.1.129)**
  - **Server-managed settings policy 적용 수정 (v2.1.129)**
  - **PowerShell auto-approvable in permission mode (v2.1.119)**: Bash와 동일 처리
  - **`--dangerously-skip-permissions` 보호 경로 우회 (v2.1.121, v2.1.126)**
  - 병렬 shell tool에서 read-only 명령 실패 시 sibling 자동 cancel (v2.1.128)
  - `find -exec`/`find -delete`는 `Bash(find:*)` allow rule하에서도 명시 권한 필요 (v2.1.114, 보강 v2.1.120 host crash 수정)
  - `managed-settings.d/` drop-in 파일 강화 (v2.1.118): 알파벳 순 병합
- **2026-04-19**: v2.1.110~2.1.114 변경사항 반영
  - **Bash 권한 관대화 (v2.1.111)**: Read-only Bash 명령에 glob 패턴 사용(`ls *.ts`)과 `cd <project-dir> && ...` 형태의 명령이 더 이상 권한 프롬프트를 띄우지 않음
  - **`cd <current-directory> && git ...` 권한 프롬프트 제거 (v2.1.114)**: `cd`가 no-op일 경우 git 명령 실행 시 프롬프트 없음
  - **macOS 위험 경로 인식 강화 (v2.1.114)**: `/private/{etc,var,tmp,home}` 경로가 `Bash(rm:*)` allow rule 하에서 dangerous removal target으로 처리
  - **deny rule wrapper 매칭 (v2.1.114)**: Bash deny rule이 `env`/`sudo`/`watch`/`ionice`/`setsid` 등 exec wrapper로 감싼 명령도 매칭
  - **`Bash(find:*)` allow rule 강화 (v2.1.114)**: `find -exec`/`find -delete`는 더 이상 자동 승인 안 됨 — 명시적 권한 필요
  - **`sandbox.network.deniedDomains` 설정 추가 (v2.1.113)**: 더 넓은 `allowedDomains` wildcard로 허용된 상태에서도 특정 도메인을 명시적으로 차단
  - **`Bash(dangerouslyDisableSandbox)` 보안 수정 (v2.1.114)**: 권한 프롬프트 없이 sandbox 외부에서 명령을 실행하던 보안 버그 수정
  - **Bash UI-spoofing 방지 (v2.1.114)**: 첫 줄이 주석인 multi-line 명령이 트랜스크립트에 전체 명령을 표시 (이전: 첫 줄만 표시되어 실제 명령 가려질 수 있었음)
- **2026-04-13**: v2.1.93~2.1.101 변경사항 반영
  - Bash 권한 강화: 백슬래시 이스케이프, 복합 명령어 우회, /dev/tcp 리다이렉트 등 (v2.1.97~2.1.98)
  - `permissions.deny`가 PreToolUse 훅의 `"ask"` 결정을 오버라이드 (v2.1.101)
  - Cedar 정책 파일 구문 강조 지원 (v2.1.97, `.cedar`, `.cedarpolicy`)
  - `sandbox.failIfUnavailable` 설정 추가 (v2.1.83 문서화, v2.1.98 PID 네임스페이스 격리 추가)
- **2026-04-04**: v2.1.90~2.1.92 변경사항 반영
  - `forceRemoteSettingsRefresh` 정책 추가 (v2.1.92) - managed settings fail-closed 동작
  - `.husky` 디렉토리 보호 (acceptEdits 모드) 추가 (v2.1.90)
  - auto mode가 사용자 명시 경계("don't push" 등)를 무시하던 버그 수정 (v2.1.90)
  - PowerShell 도구 권한 검사 강화: trailing `&` 우회, `-ErrorAction Break` 디버거 행 등 수정 (v2.1.90)
  - `Get-DnsClientCache`, `ipconfig /displaydns` auto-allow 제거 (v2.1.90, DNS 캐시 프라이버시)
- **2026-04-01**: v2.1.89 변경사항 반영
  - Symlink allow 규칙이 resolved target 경로 기준으로 매칭 (v2.1.89)
- **2026-03-31**: v2.1.79~2.1.88 변경사항 반영
  - `paths:` frontmatter YAML 리스트 정식 지원 (v2.1.84)
  - hooks `if` 조건 필드 compound commands 수정 (v2.1.88)
- **2026-03-18**: v2.1.51~2.1.78 변경사항 반영
  - print 모드 조건부 rules 로딩 수정 (v2.1.69)
  - `InstructionsLoaded` 훅 이벤트 참조 추가 (v2.1.69)
- **2026-02-22**: 전면 갱신 (source of truth 목적)
  - paths vs globs 버그 경고 추가 (Issue #17204)
  - user-level 조건부 규칙 미작동 명시 (Issue #21858)
  - Git worktree 제한사항 추가 (Issue #23569)
  - --add-dir rules 로딩 (v2.1.20)
  - Auto Memory 교차 참조 제거 (claude-md-guide에서 다룸)
- **2026-01-19**: 초기 작성
