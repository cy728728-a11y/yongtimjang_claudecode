---
name: pdf-to-md
description: PDF 파일을 구조화된 Markdown으로 변환 (pymupdf4llm 기반). 표·헤딩·이미지 레이아웃을 보존하며 대용량 PDF도 한 번에 처리. "PDF 변환", "PDF를 마크다운으로", "PDF 텍스트 추출", "문서 변환" 등을 언급하면 자동 실행.
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
---

# PDF to Markdown Converter

`pymupdf4llm`을 사용해 PDF를 LLM 친화적인 Markdown으로 변환. Claude의 `Read` 도구보다 품질이 훨씬 좋고(표·레이아웃 보존), 토큰을 소비하지 않으며, 대용량 PDF도 한 번에 처리.

## Script Location

`.claude/skills/pdf-to-md/scripts/pdf_to_md.py` (워크스페이스 루트 기준)

## Prerequisites

```bash
pip install -r .claude/skills/pdf-to-md/scripts/requirements.txt
```

또는:
```bash
pip install "pymupdf4llm>=0.0.17"
```

**PEP 668 에러가 나는 경우 (Python 3.12+ / Mac Homebrew 환경)**:

가장 깔끔한 방법은 워크스페이스 전용 가상환경:
```bash
# 워크스페이스 루트에서 1회 세팅
python3 -m venv .venv
source .venv/bin/activate
pip install "pymupdf4llm>=0.0.17" "pandas>=2.0.0" "openpyxl>=3.1.0"
```

이후 Python 쓰는 스킬은 `source .venv/bin/activate` 된 상태에서 호출. `.venv/`는 이미 `.gitignore` 처리됨.

> 궁금한 점: Python 환경 세팅이 처음이면 `setup-workspace` 스킬 실행 시 함께 안내됨.

## Workflow

### Step 1: PDF 파일 경로 확인

사용자로부터 PDF 파일 경로 확인.
경로가 명확하지 않으면 Glob으로 `.pdf` 파일 스캔.

### Step 2: PDF 정보 분석

```bash
python .claude/skills/pdf-to-md/scripts/pdf_to_md.py <파일> --info
```

출력:
- 페이지 수, 파일 크기
- 페이지당 평균 문자 수 (5페이지 샘플링)
- **스캔 이미지 기반 PDF 감지**: 텍스트가 거의 없고 이미지만 있으면 경고

스캔 PDF로 판정되면 → "이 PDF는 OCR이 필요합니다. tesseract 또는 Gemini Vision 같은 OCR 도구를 고려하세요" 안내 후 사용자에게 계속 진행할지 확인.

### Step 3: 변환 실행

```bash
# 기본 변환 (전체 페이지)
python .claude/skills/pdf-to-md/scripts/pdf_to_md.py <파일>

# 특정 페이지 범위
python .claude/skills/pdf-to-md/scripts/pdf_to_md.py <파일> --pages 1-10

# 복합 페이지 지정
python .claude/skills/pdf-to-md/scripts/pdf_to_md.py <파일> --pages 1,3,5-10

# 이미지도 함께 추출 (별도 폴더에 png 저장, 마크다운에서 링크)
python .claude/skills/pdf-to-md/scripts/pdf_to_md.py <파일> --images

# 출력 경로 지정
python .claude/skills/pdf-to-md/scripts/pdf_to_md.py <파일> --output ./30-knowledge/paper.md
```

### Step 4: 저장 위치 결정

`--output`을 지정하지 않으면 기본값은 **원본 PDF와 같은 폴더에 `_converted.md`**.

사용자 주제에 따라 적절한 위치 제안:
- 프로젝트 관련 → `./10-projects/[해당 프로젝트]/`
- 지식/레퍼런스 → `./30-knowledge/` 또는 `./50-resources/`
- 명확하지 않음 → `./00-inbox/` (주간 정리에서 재배치)

### Step 5: 결과 확인

1. 생성된 `.md` 파일 Read로 첫 50줄 미리보기
2. 표·헤딩·이미지 링크가 제대로 들어갔는지 확인
3. 이미지 추출했으면 `_images/` 폴더 존재 확인

### Step 6 (선택): 후처리

긴 PDF를 변환한 경우 뒤에 이어지는 작업 제안:
- 내용이 가치 있으면 → `wiki-ingest` 스킬로 00-wiki에 축적
- 녹음/강의 자료면 → `transcript-organizer` 대신 이걸 쓰면 된다고 안내 (구조가 다름)

## CLI Options

| 옵션 | 설명 |
|------|------|
| `--info` | PDF 정보만 출력 (변환 안 함) |
| `--output PATH` | 출력 `.md` 경로 |
| `--pages RANGE` | 페이지 범위 (예: `1-5`, `1,3,5-10`) |
| `--images` | 이미지 추출 → `<output>_images/` |

## Output Naming

| 조건 | 파일명 |
|------|--------|
| 기본 | `{원본}_converted.md` (원본과 같은 폴더) |
| `--output` 지정 | 지정된 경로 |
| `--images` | 추가로 `{출력}_images/` 폴더 생성 |

## Data Handling

- **인코딩**: 출력은 항상 UTF-8
- **표**: Markdown 표로 변환 (병합 셀은 첫 셀 값으로 채움)
- **헤딩**: PDF 폰트 크기 기반으로 `#` 레벨 자동 추정
- **이미지**: 기본은 `![](image_ref)` 링크만, `--images` 시 실제 png 파일 추출
- **다단 레이아웃**: 좌→우 자연 순서로 선형화
- **각주**: 본문 흐름에 인라인 또는 페이지 하단에 배치

## 한계 및 대안

| 상황 | pdf-to-md(이 스킬) | 대안 |
|------|---------------------|------|
| 일반 텍스트 PDF | ★★★★ | — |
| 표 많은 PDF | ★★★ | pdfplumber (표 특화) |
| 스캔 이미지 PDF | ✗ (텍스트 없음) | tesseract OCR, Gemini Vision |
| 수식 많은 논문 | ★★ (LaTeX 깨질 수 있음) | marker-pdf (AI 기반) |
| 한중일 세로쓰기 | ★★ | 전용 OCR 도구 |

## Error Handling

- `pymupdf4llm` 미설치 → 설치 명령 안내 후 종료
- 파일 없음 → 경로 확인 요청
- `.pdf` 아닌 파일 → 거부
- 스캔 PDF 감지 → 경고만 출력하고 변환은 시도 (출력이 빈약할 수 있음 명시)

## 왜 Claude의 Read 도구 대신?

- **토큰 0 소비**: Claude 컨텍스트를 쓰지 않음. 100페이지 PDF도 스크립트가 직접 처리
- **레이아웃 보존**: 표·다단·이미지 링크가 깨지지 않음
- **재현성**: 같은 입력 → 같은 출력 (Read 도구는 LLM 해석이 끼어듦)
- **속도**: 수 초 내 변환
