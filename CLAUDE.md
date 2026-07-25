# Do Better Workspace 가이드

> Claude Code + Johnny Decimal 기반 PKM 워크스페이스.
> 이 파일은 Claude Code가 매 세션 시작 시 자동으로 읽는 프로젝트 지침입니다.
> 본인 프로필(이름, 역할, 관심사)은 이 파일 하단의 "내 프로필" 섹션을 직접 작성하거나 `/setup-workspace` 스킬로 채우세요.

## 폴더 구조 (Johnny Decimal)

```
00-inbox/      # 임시 캡처 (20개 미만 유지, 주간 처리)
00-system/     # 시스템 설정, 템플릿, 가이드
10-projects/   # 활성 프로젝트 (시한부)
20-operations/ # 지속적 운영 (종료일 없음)
30-knowledge/  # 지식 (00-wiki + 도메인 아카이브)
40-personal/   # 개인 노트 (daily, weekly, ideas, reflections, todos)
50-resources/  # 외부 자료, 첨부파일
90-archive/    # 완료/중단 항목
```

### 주요 하위 폴더

| 번호 | 폴더 | 용도 |
|------|------|------|
| **00-wiki** | 30-knowledge/ | **지식 위키 (복리 축적). 아래 Wiki Schema 참조** |
| 41-daily | 40-personal/ | Daily Notes (월별: 41-daily/YYYY-MM/) |
| 42-weekly | 40-personal/ | Weekly Review |
| 43-ideas | 40-personal/ | 아이디어 캡처 |
| 44-reflections | 40-personal/ | 회고 및 학습 |
| 46-todos | 40-personal/ | active-todos.md |
| 37-claude-code | 30-knowledge/ | Claude Code 관련 지식 |

## Wiki (30-knowledge/00-wiki/)

지식이 복리로 축적되는 위키. 주제에 대해 물으면 **00-wiki/index.md를 먼저 확인**.

@30-knowledge/00-wiki/SCHEMA.md

## 파일 명명 규칙

| 유형 | 형식 | 예시 |
|------|------|------|
| Daily Note | `YYYY-MM-DD.md` | 2026-04-24.md |
| 주제 노트 | `주제명.md` | thinking-partner.md |
| JD 폴더 | `XX-name` 또는 `XX.YY-name` | 37-claude-code, 37.01-learning |
| 중복 파일명 | JD prefix 필수 | 18-progress-tracker.md |

## Inbox 관리 (00-inbox)

- **목적**: 임시 캡처, 영구 저장소 아님
- **규칙**: 20개 미만 유지
- **주기**: 주간 처리 (Capture → Process → Organize)

## 첨부파일 (50-resources/attachments/)

- 모든 비텍스트 파일 저장
- 명명: `[관련노트]_[설명].[ext]`

## Skills 사용

이 워크스페이스의 `.claude/skills/`에 프로젝트 전용 스킬이 있습니다.
스킬은 키워드 기반으로 **자동 트리거**됩니다. (수동 슬래시 커맨드 아님)

예: "오늘 daily note 만들어줘" → `daily-note` 스킬 자동 실행
예: "할 일 추가해줘" → `todo` 스킬 자동 실행

## Agents 사용

`.claude/agents/`에 서브에이전트가 있습니다. 복잡한 작업을 Claude가 자동으로 위임하거나, 명시적으로 "research-worker로 조사해줘" 같이 호출할 수 있습니다.

## 외부 도구 연동

### Google Workspace (gws CLI) ✅ 연동됨

`gws` CLI로 Google Workspace가 연동되어 있습니다. 인증 토큰은 시스템 keyring에 저장됨.

- **사용법**: `gws <service> <resource> <method> --params '<JSON>'`
- **지원 서비스**: gmail, calendar, drive, sheets, docs, slides, tasks, people, chat, forms, keep, meet 등
- **예시**:
  - 메일 목록: `gws gmail users messages list --params '{"userId":"me","maxResults":5}'`
  - 메일 내용: `gws gmail users messages get --params '{"userId":"me","id":"<ID>","format":"metadata","metadataHeaders":["From","Subject","Date"]}'`
  - 오늘 일정: `gws calendar events list --params '{"calendarId":"primary",...}'`
- `--format table|json|yaml|csv`, `--page-all`(자동 페이지네이션) 플래그 지원
- `gws schema <service.resource.method>`로 파라미터 스키마 확인 가능
- `daily-note` 스킬이 gws 인증 시 Google Calendar 오늘 일정을 자동 포함

---

## 내 프로필

> 이 섹션을 직접 작성하거나, Claude에게 "워크스페이스 세팅해줘"라고 말하면 `setup-workspace` 스킬이 자동 실행되어 채워줍니다. 같은 스킬이 Python venv·선택 도구(git/gws) 세팅도 안내합니다.

**이름**: 용팀장 (용팀장님으로 호칭, 존댓말)
**역할**: 구매대행 셀러 겸 강사 (네이버 스마트스토어 + 유튜브 + 오프라인 강의)
**관심사**: 구매대행 실전반 강의 2기 준비(1기 커리큘럼 재구성·4주 구성으로 업그레이드) · 멀티에이전트 자동화 시스템(Hermes) 구축(상품등록·키워드·썸네일 자동화) · 셀러 자동화 파이프라인 고도화(불사자 연동, 상세페이지·소싱 자동화)
**이 워크스페이스 용도**: 강의 커리큘럼 기획·PPT 제작 · Hermes 멀티에이전트 자동화 시스템 개발·정리 · 불사자 자동화 파이프라인 유지보수

**협업 규칙 (필수)**:
- 결론 먼저, 이유 나중. 짧고 명확하게. 구조와 논리로 설명.
- **팩트만 제공하고 결론은 용팀장님이 내리게 함.** "~해야 해요" 식 지시·억지 실행 유도·과도한 칭찬 금지 (반골 기질).
- **시간·날짜 추측 판단 및 잔소리 금지.**
- 실행이 막혀 있을 땐 먼저 감정 케어 → 그다음 구조화된 팩트 조언.
- 코드 요청: Python 기반, 한국어 주석, try-except 포함.

_작성일: 2026-07-12_

---

**Last Updated**: 2026-07-04
