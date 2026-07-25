---
name: keyword-pick
description: 아이템스카우트 키워드 익스포트(.xlsx)에서 용팀장님 기준(상품수 낮은 키워드)에 맞는 추천 키워드를 골라 구글 시트에 누적. "키워드 추천", "키워드 뽑아줘", "키워드 골라줘", "아이템스카우트", "상품수 낮은 키워드", "추천키워드", "keyword pick" 등을 언급하거나 아이템스카우트 익스포트 .xlsx를 제공하면 자동 실행. (레퍼런스 없는 경우 = 상품 참조 없이 키워드만 선별하는 모드)
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
---

# 키워드 선별 (레퍼런스 없는 경우)

아이템스카우트에서 뽑은 키워드 엑셀을 받아, **상품수 기준으로 괜찮은 키워드만** 걸러 구글 마스터 시트에 누적한다.
파이썬 스크립트가 기계적 필터(정보성 제외 · 상품수 컷 · 자동 확장 · 정렬)를 하고, **브랜드/부적합 키워드 제거와 선정근거 작성은 Claude가 판단**한다.

> 이 스킬은 **레퍼런스(상품 참조)가 없는** 경우 전용이다. 타오바오 상품에 맞춘 적합성 판정·상품명 생성은 별도 흐름(추후 구현)에서 다룬다.

## Script Location

워크스페이스 루트 기준:
```
.claude/skills/keyword-pick/scripts/keyword-filter.py
```

## Prerequisites

- Python + `openpyxl` (워크스페이스 `.venv` 또는 전역). 미설치 시 스크립트가 안내 후 종료.
  - 설치: `pip install -r .claude/skills/keyword-pick/scripts/requirements.txt`
- `gws` CLI 인증 (Google Workspace) — 시트 append용.

## 저장 위치 (고정)

**마스터 시트 (추천 키워드 누적 대상)**
- **이름**: `추천키워드-누적`
- **위치**: Google Drive `00 키워드` 폴더 (`16YazqD_lv4Q517cmQ_N8CKQPCc0M5olR`)
- **spreadsheetId**: `1H5h9uotZy6NwJZ5064-gJZmZsy-VZ5XCzYpLXD6lgp8`
- **URL**: https://docs.google.com/spreadsheets/d/1H5h9uotZy6NwJZ5064-gJZmZsy-VZ5XCzYpLXD6lgp8/edit
- **탭**: `[01 추천키워드]` (대괄호 포함이 정식 탭명)
- **헤더(10열)**: `작업일 / 상품명 / 대표키워드 / 카테고리 / 키워드 / 총검색수 / 상품수 / 원본파일링크 / 선정근거 / 기준`

**raw 데이터 보관 폴더 (원본 xlsx 업로드 대상)**
- **폴더명**: `01 raw-원본데이터` (`00 키워드` 하위)
- **folderId**: `1kD0w-BwFgEIbRH7LhhaIMabRamb3LQLL`
- 원본 xlsx는 여기에 **`날짜6자리_1차_2차_3차_4차카테고리.xlsx`** 이름으로 업로드하고, 그 Drive 링크를 시트의 `원본파일링크`로 쓴다.

## 추천 기준 (레퍼런스 없는 경우)

1. **상품수 ≤ 10,000** (기본 컷)
2. **정보성 키워드 제외** — 쇼핑성만 (스크립트 기본값, `--keep-info`로 해제 가능)
3. **브랜드 키워드 제외** — Claude가 후보에서 직접 판단해 제거 (예: 다이소·한샘·락앤락·매직캔 등 브랜드/제조사명)
4. **추천 5개 미만 → 상품수 ≤ 20,000으로 자동 확장** (5개 찾아지면 충분 — 상품수를 늘려가며 더 찾지 않는다. 스크립트가 처리, 확장분은 `기준`에 "상품수 2만 이하 확장" 표기)
5. **억지로 안 채운다** — 애매하거나 안 맞으면 뺀다. 최대 10개.

> 상품 적합성·유사키워드 판단(원문 확인 필요한 소재·효능·인증 등)은 레퍼런스가 있어야 가능 → 이 모드에서는 스킵.

## Workflow

### Step 1. 입력 확인
용팀장님에게서 받는 것:
- (필수) 아이템스카우트 익스포트 `.xlsx` 경로
- (선택) `대표키워드`(익스포트의 seed/주제어), `상품명`(있으면), `원본파일링크`(raw 폴더에 올린 원본 링크 등)

### Step 2. 후보 필터 (스크립트)
```bash
python .claude/skills/keyword-pick/scripts/keyword-filter.py "<xlsx경로>" --top 10
```
- 콘솔 표 + `# 추천 파일명:` 줄 + `###RENAME###`(파일명·대표카테고리 JSON) + `###JSON###`(후보 배열) 출력.
- 옵션: `--max-products`(기본 10000) · `--expand`(기본 20000) · `--min-count`(기본 5) · `--top`(기본 10) · `--keep-info`
- Windows에서 한글이 콘솔에 깨지면 `PYTHONIOENCODING=utf-8`을 앞에 붙인다.

### Step 3. raw 데이터 리네임 + 업로드
스크립트가 준 `추천 파일명`(= `날짜6자리_1차_2차_3차_4차카테고리.xlsx`)으로 원본 xlsx를 raw 폴더에 올린다.
`+upload --name`이 업로드하며 이름을 바꿔주므로 로컬 파일을 먼저 rename 하지 않아도 된다.
```bash
gws drive +upload "<원본xlsx경로>" \
  --parent 1kD0w-BwFgEIbRH7LhhaIMabRamb3LQLL \
  --name "260705_생활건강_청소용품_휴지통_다용도휴지통.xlsx" \
  --format json 2>/dev/null
```
- 반환된 `id`로 `원본파일링크` = `https://drive.google.com/file/d/<id>/view` 를 만들어 Step 5에서 사용.
- 대표 카테고리는 전체 행의 최빈 경로. 여러 카테고리가 섞여 애매하면 용팀장님께 확인.
- (선택) 로컬 원본 정리는 용팀장님 판단 — 스킬이 임의로 삭제하지 않는다.

### Step 4. Claude 판단
`###JSON###` 후보에서:
- **브랜드/제조사명 키워드 제거** (구매대행이라 브랜드 정품 키워드는 부적합)
- 검색수가 사실상 0에 가까운(예: 20~30) 노이즈 키워드는 제외 판단
- 남은 키워드마다 `선정근거`를 짧게 작성 (예: "상품수 5개로 사실상 무경쟁", "검색 990에 상품 1개")
- `기준`은 스크립트가 준 값(`상품수 1만 이하` / `상품수 2만 이하 확장`)을 그대로 사용

### Step 5. 마스터 시트에 append
각 추천 키워드를 한 행으로 `[01 추천키워드]` 탭에 추가한다. 열 순서:
`작업일 / 상품명 / 대표키워드 / 카테고리 / 키워드 / 총검색수 / 상품수 / 원본파일링크 / 선정근거 / 기준`

```bash
gws sheets +append --spreadsheet 1H5h9uotZy6NwJZ5064-gJZmZsy-VZ5XCzYpLXD6lgp8 \
  --json-values '[["2026-07-05","","휴지통","생활/건강 > 청소용품 > 휴지통 > 다용도휴지통","매직캔히포227l","990","1","https://drive.google.com/file/d/<id>/view","검색 990에 상품 1개, 사실상 무경쟁","상품수 1만 이하"]]'
```
- 여러 행이면 `--json-values`에 여러 배열을 한 번에 전달.
- `작업일`은 오늘 날짜(YYYY-MM-DD). `원본파일링크`는 Step 3 업로드 링크. `상품명`은 없으면 공란.

### Step 6. 보고
추가한 키워드 개수·주요 키워드·확장 발동 여부를 용팀장님께 요약 보고하고 시트 URL을 안내한다.

## gws 사용 주의 (실측 확인됨)

- **요청 본문은 `--json`**, URL/쿼리 파라미터는 `--params`. (create/batchUpdate 등은 `--json` 사용)
- `+read`는 `--range` **플래그**로 범위를 준다(`--params` 아님). 대괄호 탭명은 작은따옴표로 감싼다:
  `--range "'[01 추천키워드]'!A1:J50"`
- `gws`는 stderr에 `Using keyring backend: keyring`를 출력 → JSON 파싱 시 `2>/dev/null` 권장.
- 스프레드시트를 특정 폴더에 두려면: `sheets spreadsheets create`로 생성 → `drive files update`에 `addParents`/`removeParents`로 이동(removeParents에 기존 부모 ID 필요).

## 다음 단계 (이 스킬 밖)

- 레퍼런스 있는 경우: 타오바오 이미지/URL/텍스트 기반 적합성 판정 → 저장 폴더·시트 별도.
- **`smartstore-seo-product-name` 스킬 (구현됨, 2026-07-19)**: 추천키워드 5~6개 → 핵심 상품명 2개(겹치는 단어 ≤1) + 추가 키워드(나머지 키워드의 미사용 단어) → 최종 상품명 1개(term count ≤7·중복 단어 1개·2회). 규칙 원본은 해당 스킬의 `references/상품명-작성-규칙.md`.
