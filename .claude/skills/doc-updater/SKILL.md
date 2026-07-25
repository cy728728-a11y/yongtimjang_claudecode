---
name: doc-updater
description: Claude Code 공식 문서 업데이트 확인 및 자동 반영. GitHub CHANGELOG를 읽고 30-knowledge/37-claude-code/37.00-official-docs/ 하위 가이드 문서들을 최신 버전으로 동기화. "문서 업데이트", "CHANGELOG 확인", "doc update", "공식문서 업데이트", "Claude Code 변경사항" 등을 언급하면 자동 실행.
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
  - WebFetch
---

# Claude Code 공식 문서 자동 업데이트

GitHub의 Claude Code CHANGELOG를 읽어 이 워크스페이스의 공식 문서 요약본을 최신 버전과 동기화한다.

## 대상 문서

`./30-knowledge/37-claude-code/37.00-official-docs/` 하위 5개:

- `skills-guide.md`
- `subagents-guide.md`
- `claude-md-guide.md`
- `rules-guide.md`
- `plugins-guide.md`

> `slash-commands-guide.md`는 의도적으로 제외 (공식 권장이 Skills로 통합됨).

## 경로 설정

```yaml
config:
  changelog_url: https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md
  cache_dir: ./.cache/doc-updater
  cache_file: ./.cache/doc-updater/changelog.md
  version_tracker: ./.cache/doc-updater/doc-versions.json
  docs_path: ./30-knowledge/37-claude-code/37.00-official-docs
```

- **경로는 모두 워크스페이스 루트 기준 상대경로**. 스킬 실행 시 현재 디렉토리가 워크스페이스 루트여야 함
- `.cache/`는 `.gitignore`에 등록되어 버전 관리 대상 아님

## 핵심: 2단계 버전 추적

이 스킬은 **두 가지 버전**을 별도로 추적:

1. **changelog_version**: 캐시된 CHANGELOG의 최신 버전 (GitHub와 비교)
2. **docs_synced_version**: 가이드 문서가 실제로 반영한 마지막 CHANGELOG 버전

**업데이트 필요 판단 기준**:
- `changelog_version < GitHub 최신` → 새 CHANGELOG 있음
- `docs_synced_version < changelog_version` → 가이드가 CHANGELOG에 뒤처짐
- 둘 중 하나라도 해당하면 업데이트 진행

## 버전 추적 파일

`./.cache/doc-updater/doc-versions.json`:
```json
{
  "changelog_version": "2.1.119",
  "docs_synced_version": "2.1.119",
  "last_checked": "2026-04-24",
  "docs": {
    "skills-guide.md": "2.1.119",
    "subagents-guide.md": "2.1.119",
    "claude-md-guide.md": "2.1.119",
    "rules-guide.md": "2.1.119",
    "plugins-guide.md": "2.1.119"
  }
}
```

## 작업 순서

### Step 1: 환경 체크 + 버전 상태 확인

1. **워크스페이스 루트 확인**:
   ```bash
   test -f CLAUDE.md && test -d 30-knowledge/37-claude-code/37.00-official-docs \
     || { echo "ERROR: 워크스페이스 루트에서 실행하세요"; exit 1; }
   mkdir -p ./.cache/doc-updater
   ```

2. **GitHub에서 최신 CHANGELOG 가져오기**:
   ```
   WebFetch: https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md
   ```
   - GitHub API는 rate limit이 있으므로 `WebFetch`로 raw URL을 직접 받는 방식 사용
   - 결과를 `./.cache/doc-updater/changelog.md`에 저장

3. **버전 추적 파일 읽기**:
   - 파일이 있으면 그대로 읽기
   - 없으면 초기화: `{"docs_synced_version": "0.0.0", "changelog_version": "0.0.0", ...}`

4. **업데이트 필요 여부 판단**:
   - GitHub 최신 버전 파싱 (CHANGELOG의 `## X.Y.Z` 첫 번째 항목)
   - **둘 다 동일하면**: "이미 최신 버전입니다 (vX.Y.Z)" 출력 후 종료
   - **하나라도 다르면**: 계속 진행

### Step 2: 변경사항 분석

`docs_synced_version` 이후 추가된 모든 버전의 변경사항을 수집하고 주제별로 분류:

| 카테고리 | 키워드 (CHANGELOG 본문에서 찾을 것) | 영향받는 문서 |
|----------|--------|---------------|
| Skills | skill, SKILL.md, allowed-tools, `${CLAUDE_SKILL_DIR}`, `/skills` | skills-guide.md |
| Subagents | agent, subagent, Task tool, SendMessage, worktree, `--agent`, `--print` frontmatter | subagents-guide.md |
| CLAUDE.md | memory, CLAUDE.md, @import, auto-memory, recap | claude-md-guide.md |
| Rules | rules/, paths, globs, conditional, sandbox | rules-guide.md |
| Plugins | plugin, marketplace, `${CLAUDE_PLUGIN_ROOT}`, `plugin tag` | plugins-guide.md |
| Hooks | hook, PreToolUse, PostToolUse, Stop, `mcp_tool`, `duration_ms` | subagents-guide.md (Hooks 섹션) |
| Breaking Changes | BREAKING, deprecated, removed | 모든 문서 — 사용자에게 별도 알림 필수 |

### Step 3: 로컬 공식 문서 업데이트

**업데이트 방식**:
1. 각 문서 상단 `> **Updated**: YYYY-MM-DD (vX.Y.Z)` 라인 갱신 (간단한 변경 요약 suffix 포함)
2. 해당 섹션이 이미 있으면 내용 보강, 없으면 적절한 위치에 새 섹션 추가
3. 예시 코드가 달라진 게 있으면 최신 문법으로 교체
4. **대규모 재구성이 필요해 보이면 자동 적용 대신 사용자에게 확인 요청**

Breaking Change가 감지되면 Step 5 리포트에 별도 섹션으로 강조.

### Step 4: 워크스페이스 스킬/에이전트 영향 체크 (선택)

이 워크스페이스의 `.claude/skills/`, `.claude/agents/` 하위 파일이 변경의 영향을 받는지 간이 점검:

- SKILL.md frontmatter에 더 이상 지원 안 되는 필드가 있는지
- agents/*.md에 deprecated된 도구/필드가 있는지

영향 있는 항목을 **리포트에만 나열**하고 **자동 수정은 하지 않음** (사용자가 직접 판단 후 수정).

### Step 5: 캐시 업데이트 및 결과 리포트

1. **버전 추적 파일 갱신**:
   - `changelog_version` = GitHub 최신 버전
   - `docs_synced_version` = 업데이트 완료된 버전
   - 각 문서별 동기화 버전 기록
   - `last_checked` = 오늘 날짜

2. **결과 리포트 출력**:
   ```markdown
   # Doc Updater 실행 결과

   ## 버전 정보
   - 캐시 CHANGELOG 버전: (이전) P.Q.R → (현재) X.Y.Z
   - 가이드 동기화 버전: (이전) A.B.C → (현재) X.Y.Z
   - 확인 일시: YYYY-MM-DD

   ## 업데이트된 가이드 문서
   - [x] skills-guide.md
   - [x] subagents-guide.md
   - [ ] claude-md-guide.md (변경 없음)
   - ...

   ## Breaking Changes (수동 확인 필요)
   - (있으면 나열)

   ## 워크스페이스 스킬/에이전트 영향 체크
   - (영향 받는 파일 + 어떤 변경 때문인지)

   ## 다음 단계
   - 변경된 문서를 git diff로 확인
   - Breaking Change 있으면 프로젝트 스킬에 반영 필요
   ```

## 에러 처리

| 상황 | 대응 |
|------|------|
| `WebFetch` 접근 실패 | 오프라인 모드 — 캐시된 CHANGELOG만으로 진행 ("원격 확인 실패" 명시) |
| 캐시 파일 없음 | 새로 생성 후 전체 동기화 |
| 버전 추적 파일 없음 | 초기화 (`docs_synced_version: "0.0.0"`) → 최초 1회 풀 싱크 |
| 버전 파싱 실패 | 원본 CHANGELOG 링크 제공 후 중단 |
| 공식 문서 파일 누락 | 해당 파일 스킵하고 리포트에 표시 |

## 주의사항

- **기존 커스터마이징 존중**: 문서에 사용자가 수기로 추가한 섹션/메모가 있으면 덮어쓰지 말고 병합
- **Breaking Changes는 반드시 강조**: 자동 적용하지 말고 리포트에 먼저 알림
- **git commit 금지**: 업데이트 후 commit은 사용자가 직접. 이 스킬은 파일 변경까지만
- **다중 버전 점프 시**: 한 번에 5개 버전 이상 밀렸으면 Step 2에서 사용자에게 "범위가 큽니다. 계속할까요?" 확인
