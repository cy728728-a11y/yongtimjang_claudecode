# Do Better Workspace

> AI-powered PKM workspace for non-coders
> 비개발자를 위한 AI 작업 환경

---

## What is Do Better Workspace?

Claude Code와 Johnny Decimal 시스템을 결합한 **실전 PKM 워크스페이스**입니다.

**핵심 특징:**
- F&B 16년 + AI 활용 전문가의 **실제 운영 시스템** 기반
- 워크숍/교육용으로 정리된 **배포판 버전**
- 바로 clone해서 사용 가능한 **즉시 활용형** 구조
- **Skills 기반** — 자연어로 호출, 키워드 자동 트리거 (구 슬래시 커맨드 방식 대체)
- **Wiki 복리 시스템** — 지식이 쌓일수록 가치가 증가 (Karpathy LLM Wiki 아이디어)

## Quick Start

### 1. Clone
```bash
git clone https://github.com/Rhim80/do-better-workspace-v2.git
cd do-better-workspace-v2
```

### 2. Claude Code에서 열기
VS Code 또는 터미널에서 Claude Code 실행.

### 3. 초기 설정

Claude에게:
```
워크스페이스 세팅해줘
```

`setup-workspace` 스킬이 대화형으로 다음을 진행합니다:

1. **프로필 작성** — CLAUDE.md의 "내 프로필" 섹션을 4개 질문으로 채움
2. **Python 환경** — 데이터 스킬(csv-clean, excel-to-csv, pdf-to-md)용 `.venv` 생성 + 패키지 설치 (원할 때만)
3. **선택 도구 체크** — `git`, `gws` (Google Workspace CLI) 설치 상태 확인 및 안내
4. **첫 Daily Note** — 오늘의 기록 시작

각 단계는 건너뛸 수 있고, 이미 세팅된 항목은 자동 스킵됩니다.

### 4. 일상 루틴

```
오늘 daily note 만들어줘      # daily-note 스킬
할 일 추가해줘: 이메일 답장   # todo 스킬
이 아이디어 기록해줘          # idea 스킬
```

Python 스킬을 쓸 때는 가상환경 활성화:
```bash
source .venv/bin/activate
```

## Philosophy

1. **AI amplifies thinking**, not just writing
2. **File system = AI memory**
3. **Structure enables creativity**
4. **Iteration over perfection**
5. **Knowledge compounds** (via Wiki)

## Folder Structure

Johnny Decimal 시스템 기반.

```
do-better-workspace/
├── .claude/
│   ├── agents/        # 전용 서브에이전트
│   └── skills/        # 프로젝트 스킬 (키워드 자동 트리거)
├── 00-inbox/          # 빠른 캡처 공간 (20개 미만 유지)
├── 00-system/         # 시스템 설정, 템플릿, 가이드
├── 10-projects/       # 활성 프로젝트 (시한부)
├── 20-operations/     # 지속적 운영 업무
├── 30-knowledge/
│   ├── 00-wiki/       # 지식 위키 (복리 축적)
│   └── 37-claude-code/ # Claude Code 관련 지식
├── 40-personal/
│   ├── 41-daily/      # Daily Notes (월별)
│   ├── 42-weekly/     # Weekly Reviews
│   ├── 43-ideas/      # 아이디어
│   ├── 44-reflections/ # 회고/학습
│   └── 46-todos/      # active-todos.md
├── 50-resources/      # 참고 자료, 첨부
└── 90-archive/        # 완료/중단 항목
```

## Skills vs Slash Commands

이 워크스페이스는 **Skills 기반**입니다. 구 `/slash-command` 방식과 달리:

| Slash Command (구) | Skill (신) |
|---|---|
| `/daily-note` 수동 입력 | "오늘 노트 만들어줘" 자연어 호출 |
| 이름을 외워야 함 | 키워드로 자동 트리거 |
| 빠르지만 경직됨 | 유연하고 대화적 |

스킬 목록은 `.claude/skills/README.md` 참조.

## Wiki System

`30-knowledge/00-wiki/`는 **지식이 복리로 축적되는 위키**입니다.

- 주제에 대해 물으면 Claude가 여기부터 확인
- 새 소스(회의록, 영상, 기사)를 여기에 통합 (`wiki-ingest` 스킬)
- 주기적 헬스체크 (`wiki-lint` 스킬)

상세: `30-knowledge/00-wiki/SCHEMA.md`

## Credits

- [Claudesidian](https://github.com/heyitsnoah/claudesidian) by Noah Brier — PKM 아이디어 원형
- [Karpathy on LLM Wiki](https://x.com/karpathy) — Wiki 복리 구조 영감
- F&B 16년 + AI 실전 워크플로우

## License

MIT — 자유롭게 사용하고 수정하세요.

---

**Made by hovoo (이림)**
Do Better Things with Sense & AI
