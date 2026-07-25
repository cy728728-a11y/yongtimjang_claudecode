---
name: excel-to-csv
description: Excel 파일을 CSV로 변환하여 Claude Code에서 분석 가능하게 만듦. "엑셀 변환", "Excel CSV", "xlsx 변환", "엑셀을 CSV로", "데이터 변환", "excel to csv" 등을 언급하거나 .xlsx/.xls 파일 경로를 제공하면 자동 실행.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Skill
---

# Excel to CSV Converter

Claude Code는 .xlsx/.xls 파일을 직접 읽을 수 없다. 이 스킬은 Excel 파일을 UTF-8 CSV로 변환한다.

## Script Location

`.claude/skills/excel-to-csv/scripts/excel-to-csv.py` (워크스페이스 루트 기준)

## Prerequisites

```bash
pip install -r .claude/skills/excel-to-csv/scripts/requirements.txt
```

또는:
```bash
pip install "openpyxl>=3.1.0"
```

## Workflow

### Step 1: 파일 경로 확인

Excel 파일 또는 폴더 경로 확인. 명확하지 않으면 Glob으로 `.xlsx`/`.xls` 파일 스캔.

### Step 2: 파일 정보 분석

```bash
python .claude/skills/excel-to-csv/scripts/excel-to-csv.py <파일경로> --info
```

출력:
- 시트 목록 + 각 시트 행/열 수
- 헤더 미리보기
- 데이터 미리보기 (첫 3행)
- **Complexity Analysis**: 구조 문제 자동 감지

### Step 2.5: 복잡성 분석 해석

| 감지 항목 | 의미 | 해결 |
|----------|------|------|
| MULTI_HEADER | 다단 헤더 | `--flatten-headers` |
| METADATA_SKIP | 메타데이터 행 | `--skip-rows N` |
| SUBTOTAL_ROWS | 소계/합계 | 변환 후 `csv-clean --remove-subtotals` |
| TEXT_NUMBERS | 서식 있는 숫자 | 변환 후 `csv-clean --clean-numbers` |
| CROSSTAB | 크로스탭 | 변환 후 `csv-clean --unpivot` |
| DATE_FORMATS | 날짜 혼재 | 변환 후 `csv-clean --normalize-dates` |

Excel 구조 문제는 이 스킬에서 해결, 데이터 품질은 변환 후 `csv-clean`으로.

### Step 3: CSV 변환 실행

```bash
# 기본 (전체 시트)
python .claude/skills/excel-to-csv/scripts/excel-to-csv.py <파일> --all

# 특정 시트
python .claude/skills/excel-to-csv/scripts/excel-to-csv.py <파일> --sheet "시트명"

# 다단 헤더 평탄화
python .claude/skills/excel-to-csv/scripts/excel-to-csv.py <파일> --all --flatten-headers

# 메타데이터 건너뛰기
python .claude/skills/excel-to-csv/scripts/excel-to-csv.py <파일> --all --skip-rows 3 --flatten-headers

# 헤더 행 수 지정
python .claude/skills/excel-to-csv/scripts/excel-to-csv.py <파일> --all --flatten-headers --header-rows 2

# 출력 경로
python .claude/skills/excel-to-csv/scripts/excel-to-csv.py <파일> --all --output ./data/

# 폴더 일괄
python .claude/skills/excel-to-csv/scripts/excel-to-csv.py <폴더> --all

# CSV 인코딩 변환 (EUC-KR → UTF-8)
python .claude/skills/excel-to-csv/scripts/excel-to-csv.py <파일.csv> --encoding euc-kr
```

### Step 4: 결과 확인

1. 생성된 CSV 목록과 행 수
2. Read로 첫 5행 미리보기
3. 한글 깨짐 체크

### Step 5: 데이터 정리 (필요 시)

Complexity Analysis에서 데이터 품질 문제 감지 시:

```bash
python .claude/skills/csv-clean/scripts/csv-clean.py <변환된csv> --remove-subtotals --clean-numbers
```

## CLI Options

| 옵션 | 설명 |
|------|------|
| `--info` | 시트 정보 + 복잡성 분석 |
| `--sheet <name>` | 특정 시트만 |
| `--output <path>` | 출력 디렉토리 |
| `--all` | 전체 시트 |
| `--encoding <enc>` | CSV 인코딩 강제 |
| `--flatten-headers` | 다단 헤더 평탄화 |
| `--header-rows N` | 헤더 행 수 수동 지정 |
| `--skip-rows N` | 상단 N행 건너뛰기 |

## Output Naming

| 조건 | 패턴 |
|------|------|
| 단일 시트 | `{원본}.csv` |
| 멀티 시트 | `{원본}_{시트명}.csv` |
| CSV 인코딩 변환 | `{원본}_utf8.csv` |

## Data Handling

- 헤더 행: 첫 번째 비어있지 않은 행 자동 감지
- 빈 행/열: 후행 자동 제거
- 병합 셀: 첫 번째 셀 값으로 채움
- 출력 인코딩: 항상 UTF-8
