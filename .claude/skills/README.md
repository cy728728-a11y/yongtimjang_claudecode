# Skills

이 폴더는 이 워크스페이스 전용 스킬을 담습니다.

## Skills란?

Skills는 Claude Code가 **키워드 기반으로 자동 트리거**하는 기능 모음입니다.
구 슬래시 커맨드 방식(`/daily-note`)을 대체합니다.

- 자연어 호출: "오늘 daily note 만들어줘"
- Claude가 description에 있는 키워드를 감지하여 자동 실행
- 각 스킬은 `SKILL.md`를 루트에 두고, 필요시 `scripts/`, `resources/` 같은 하위 폴더 사용

## 파일 구조

```
.claude/skills/
├── README.md             # 이 파일
└── [skill-name]/
    ├── SKILL.md          # 스킬 정의 (YAML frontmatter + 설명 + 실행 절차)
    ├── scripts/          # (선택) 실행 스크립트
    └── resources/        # (선택) 참고 자료, 템플릿
```

## SKILL.md 구조

```yaml
---
name: skill-name
description: 이 스킬이 언제 트리거되는지 명확히. "X를 언급하면 자동 실행" 형식 권장.
---

# 스킬 제목

본문 — 실행 절차, 예시, 주의사항
```

## 전역 vs 프로젝트 스킬

- **전역**: `~/.claude/skills/` — 모든 프로젝트에서 적용
- **프로젝트**: 이 폴더 — 이 워크스페이스에서만 적용

프로젝트 스킬이 전역 스킬과 이름이 같으면 프로젝트 것이 우선.

## 포함된 스킬

### Core (기본 일일 워크플로우)

| 스킬 | 용도 | 트리거 예시 |
|------|------|-------------|
| `setup-workspace` | 첫 clone 후 초기 설정 (대화형 프로필 작성) | "워크스페이스 세팅" |
| `daily-note` | 오늘의 Daily Note 생성/열기 | "오늘 daily note" |
| `daily-review` | 어제~오늘 git 변경 + todos 기반 우선순위 제안 | "일일 리뷰" |
| `todo` | 빠른 할 일 추가 (우선순위 자동 감지) | "할 일 추가" |
| `todos` | 할 일 조회/관리 (today/project/overdue/stats) | "todos", "오늘 할 일" |
| `thinking-partner` | 협력적 사고 — 질문으로 탐색 | "같이 생각해보자" |
| `idea` | 대화에서 아이디어 추출 후 저장 | "이거 기록", "메모해줘" |
| `weekly-synthesis` | 주간 종합 (테마/인사이트/다음 주 방향) | "주간 리뷰" |

### 확장

| 스킬 | 용도 | 트리거 예시 |
|------|------|-------------|
| `pdf-to-md` | PDF → Markdown 변환 | "PDF 변환", "PDF를 마크다운으로" |
| `csv-clean` | CSV 품질 정리 (소계/숫자/날짜/unpivot) | "CSV 정리", "데이터 클리닝" |
| `excel-to-csv` | Excel → CSV 변환 (UTF-8) | "엑셀 변환", "xlsx 변환" |
| `dashboard-prd` | 대시보드 PRD 대화형 생성 | "대시보드 PRD", "대시보드 기획" |
| `webapp-prd` | 웹앱 PRD 대화형 생성 | "웹앱 PRD", "앱 설계" |
| `transcript-organizer` | 긴 녹음 텍스트 구조화 (강의/미팅/인터뷰) | "녹음 정리", "미팅록" |
| `wiki-ingest` | 소스 → 00-wiki 복리 축적 | "wiki-ingest", "위키에 반영" |
| `wiki-lint` | 00-wiki 헬스체크 | "위키 점검", "wiki-lint" |
| `doc-updater` | Claude Code CHANGELOG 기반 공식 문서 자동 동기화 | "문서 업데이트", "CHANGELOG 확인" |
| `md-to-pdf` | 마크다운 → A4 PDF-ready HTML (Monochrome Dark 테마) | "핸드아웃", "PDF 만들어", "배포용" |
| `ripple` | 파일 수정 후 연관 파일 함께 갱신 + 프로젝트 progress.md 생성/추가 | "연관 업데이트", "ripple", "빠진거 없나" |

### 로컬 수집·분류

| 스킬 | 용도 | 트리거 예시 |
|------|------|-------------|
| `kakao-read` **(macOS 전용)** | Mac 카톡 로컬 읽기/요약/검색, 카톡 체크(놓친 1:1 수집) | "카톡 읽어줘", "카톡 체크" |
| `inbox-triage` | 00-inbox/raw 수집분을 종류 판정 후 todo·info로 라우팅 | "인박스 분류", "수집된 거 정리" |

### 의존성이 있는 스킬

- `csv-clean` ← `excel-to-csv` (Excel → CSV → 정리 파이프라인)
- `dashboard-prd` / `webapp-prd` → 파일 분석 시 `excel-to-csv` 호출 가능
- `transcript-organizer` → 마지막 단계에서 `wiki-ingest` 자동 호출
- `kakao-read`(카톡 체크) → `00-inbox/raw/` → `inbox-triage`(분류·라우팅) → `todo` / `wiki-ingest`
- `ripple` → `00-system/01-templates/progress-template.md`(progress.md 생성) + 마지막에 `wiki-ingest` 제안

### Python 의존성이 있는 스킬

- `csv-clean` — pandas
- `excel-to-csv` — openpyxl
- `pdf-to-md` — pymupdf4llm

### 시스템 의존성 / 플랫폼 제약

- `kakao-read` — **macOS 전용**. Windows/Linux에선 스크립트가 "macOS 전용" 안내 후 종료(다른 스킬엔 영향 없음). Python 패키지 의존은 없음(표준 라이브러리만). 단 시스템 도구 `sqlcipher`가 필요:
  ```bash
  brew install sqlcipher
  # 최초 1회 본인 userId 캐시 (워크스페이스 루트에서)
  python3 .claude/skills/kakao-read/scripts/kakao_read.py setup
  ```
  카카오톡 데스크톱 앱에 한 번 이상 로그인돼 있어야 한다. 설정은 `~/.config/kakao-read/`(HOME)에 저장 — 워크스페이스 밖이라 git 추적 안 됨.
- `inbox-triage` — OS·패키지 의존 없음(순수 마크다운/grep). `kakao-read`의 카톡 체크 결과를 받지만 단독으로도 동작.

**권장 세팅 (워크스페이스 전용 venv)**:

```bash
# 워크스페이스 루트에서 1회 실행
python3 -m venv .venv
source .venv/bin/activate
pip install "pandas>=2.0.0" "openpyxl>=3.1.0" "pymupdf4llm>=0.0.17"
```

이후 Python 스킬을 쓸 때마다 `source .venv/bin/activate` 한 번 실행. `.venv/`는 `.gitignore` 처리됨.

**venv 없이 직접 설치하려면** (Python 3.12+ / Homebrew 환경에서는 PEP 668 때문에 실패할 수 있음):

```bash
pip install -r .claude/skills/csv-clean/scripts/requirements.txt
# 실패 시: pip install --user ... 또는 pipx 고려
```
