
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

**이름**: 용팀장
**역할**: 구매대행 셀러 겸 강사 (네이버 스마트스토어 + 유튜브 + 오프라인 강의)
**관심사**: 구매대행 실전반 강의 준비·셀러 자동화 파이프라인 구축(불사자 연동, 상세페이지·상품가공)
**이 워크스페이스 용도**: 강의 커리큘럼 기획·PPT 제작 · 불사자 자동화 파이프라인 유지보수

**협업 규칙 (필수)**:
- **용팀장에게는 한글로만 말한다.** 영어 문장·영어 단어로 답하지 않는다(작업 중 혼잣말·진행 상황 알림 포함). 상품명·브랜드처럼 원래 영어인 고유명사만 그대로 두고, 필요하면 한글 설명을 붙인다.
- **반말로 말한다.** 존댓말·"용팀장님" 호칭 쓰지 않는다.
- 결론 먼저, 이유 나중. 짧고 명확하게. 구조와 논리로 설명.
- **비개발자 수준으로 설명한다.** 용팀장은 개발자가 아니다. 개발 용어(API·커밋·브랜치·서브프로세스·스키마 등)는 되도록 쓰지 말고, 꼭 써야 하면 한 줄로 쉽게 풀어 준다. 코드·파일 경로·함수명 대신 "무엇이 어떻게 바뀌었고, 나한테 무슨 의미인지"로 말한다.
- 코드 요청: Python 기반, 한국어 주석, try-except 포함.

## 셀러 관제탑 (Seller Control Tower)

네이버 검색광고 성과 판정과 불사자 상품 가공을 한 화면에서 잇는 **로컬 웹 관제탑**(맥북 전용, 사용자 1명). v1.0 전 페이즈 완료(2026-10-01). 상세 기록은 `.planning/`.

- **핵심 가치**: 유입·판매가 있는데 상세페이지가 중국어 원본·단순번역인 상품을, 중복 작업 없이 한 화면에서 골라 고치고 반영한다.
- **아키텍처**: 웹앱은 기존 CLI 스크립트의 래퍼다. 검증된 로직·테스트·가드레일을 재작성하지 않는다.
- **안전**: 모든 쓰기 작업은 dry-run 선행. 크레딧 소모 작업은 접수 전 견적 보고.
- **진실의 원천**: 작업 완료 여부는 불사자 서버 플래그가 정본. 로컬 대장을 정본으로 삼지 않는다.
- **광고 계정**: `~/.eroom/naver-ads.json` 에 항목 추가로만 늘어난다.
- **관제탑 코드를 고칠 때만** GSD 명령(`/gsd-quick`·`/gsd-debug`·`/gsd-execute-phase`)으로 시작한다. 노트·todo 등 평소 작업엔 해당 없음.

---

**Last Updated**: 2026-11-02
