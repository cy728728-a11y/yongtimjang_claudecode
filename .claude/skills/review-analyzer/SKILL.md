---
name: review-analyzer
description: 네이버 브랜드스토어 리뷰를 로그인 없이 크롤링하고 4단계 프레임워크로 분석해 실행 아이디어를 도출. "네이버 리뷰", "브랜드스토어 리뷰", "리뷰 크롤링", "리뷰 분석", "경쟁사 리뷰", "상품 리뷰 수집", "리뷰 인사이트" 등을 언급하면 자동 실행.
---

# Review Analyzer

네이버 브랜드스토어 상품 리뷰를 **로그인 없이** 크롤링하고, CSV/JSON으로 저장한 뒤, 4단계 프레임워크로 분석하여 **실행 가능한 아이디어**를 도출하는 스킬.

## 핵심 워크플로우

```
[제품 URL] → [ID 자동 추출] → [크롤링(로그인 X)] → [CSV/JSON] → [4단계 분석] → [아이디어]
```

경쟁사 상품, 자사 상품, 벤치마킹 대상 등 **공개된 브랜드스토어 상품이면 무엇이든** 대상이 된다.

---

## 사전 요구사항

- **Python + Selenium + Chrome**: 브라우저 세션으로 리뷰 API를 캡처 (필수)
- **로그인 불필요**: 공개 리뷰는 페이지가 익명 방문자에게도 리뷰 API를 호출한다. 자격증명 없이 수집 가능

### 설치 (워크스페이스 .venv 권장)

```bash
# 워크스페이스 루트에서
source .venv/bin/activate      # 없으면: python3 -m venv .venv && source .venv/bin/activate
pip install -r .claude/skills/review-analyzer/scripts/requirements.txt
```

`selenium>=4.6`은 Chrome 드라이버(chromedriver)를 자동 관리하므로 별도 설치가 필요 없다. Chrome 브라우저만 설치돼 있으면 된다.

---

## 사용법

### Step 1: 제품 페이지 URL 확보

크롤링할 브랜드스토어 상품의 URL만 있으면 된다.

```
https://brand.naver.com/<스토어명>/products/<상품ID>
예: https://brand.naver.com/iloom/products/11659509026
```

`merchantNo`·`originProductNo`는 스킬이 페이지에서 **자동 추출**하므로 직접 찾을 필요 없다.

### Step 2: 크롤링 (권장 — 로그인 없음)

```bash
# 최신순 50개를 CSV로
python3 .claude/skills/review-analyzer/scripts/naver-brand-reviews.py \
  --no-login \
  --referer 'https://brand.naver.com/iloom/products/11659509026' \
  --max 50 --sort RECENT --output reviews.csv

# 낮은 별점순 100개 (불만 분석용)
python3 .claude/skills/review-analyzer/scripts/naver-brand-reviews.py \
  --no-login \
  --referer 'https://brand.naver.com/iloom/products/11659509026' \
  --max 100 --sort RATING_LOW --output low.csv
```

실행하면 Chrome 창이 뜨고, 리뷰 탭을 자동으로 열어 페이지의 리뷰 API 응답을 가로채 수집한다.

### 정렬 옵션 (`--sort`)

| 옵션 | 설명 |
|------|------|
| RANKING | 랭킹순 (기본) |
| RECENT | 최신순 |
| RATING_HIGH | 별점 높은순 |
| RATING_LOW | 별점 낮은순 (불만·개선점 분석에 유용) |

### 주요 인자

| 인자 | 설명 |
|------|------|
| `--no-login` | 로그인 없이 익명 세션으로 크롤 (권장) |
| `--referer` | 제품 페이지 URL (`--no-login` 필수, 여기서 ID 자동 추출) |
| `--max` | 최대 수집 수 (기본 200) |
| `--sort` | 정렬 (위 표) |
| `--output` | 출력 파일 (`.csv` 또는 `.json`) |

### 출력 컬럼 (CSV)

`date, rating, content, writer, product_name, product_option, has_photo, image_count`

---

## 분석 프레임워크 (4단계)

수집한 CSV를 읽고 아래 순서로 분석한다. "이 리뷰 분석해줘: reviews.csv" 처럼 요청하면 실행.

### Stage 1: 리뷰 분류
| 카테고리 | 설명 |
|----------|------|
| Pain Point | 불만, 문제점 |
| Praise | 칭찬, 만족 |
| Feature Request | 기능/개선 요청 |
| Comparison | 타사 비교 언급 |
| Switching | 구매/이탈 이유 |

### Stage 2: 테마 클러스터링
- 유사 Pain Point 그룹핑
- 빈도 + 강도 기준 정렬

### Stage 3: 우선순위 매트릭스
```
           빈도 높음          빈도 낮음
         +-------------+-------------+
강도 높음 | Must Fix    | Watch       |
         +-------------+-------------+
강도 낮음 | Quick Win   | Nice to Have|
         +-------------+-------------+
```

### Stage 4: 아이디어 도출
- Pain Point → 해결책
- 경쟁사 약점 → 차별화 기회
- Feature Request → 신제품 아이디어

> 팁: `--sort RATING_LOW`로 낮은 별점을 모으면 Pain Point가 집중적으로 잡혀 Stage 1~2가 빨라진다.

---

## 동작 원리 (왜 이 방식인가)

네이버 nfront WAF는 외부에서 직접 호출하는 리뷰 API 요청을 차단한다:
- `curl`/`requests`: TLS 핑거프린팅으로 차단 (HTTP 204)
- `curl_cffi`(TLS 위장): 다음 방어선인 429 에러페이지로 차단
- Selenium `execute_script`로 만든 XHR/fetch: Selenium 컨텍스트 감지로 차단

유일하게 통하는 방법은 **페이지 자체가 만드는 리뷰 API 호출을 가로채기**(XHR 인터셉터)다. 그래서 Selenium으로 실제 페이지를 열고, 리뷰 탭 클릭·페이지네이션으로 API 호출을 유발한 뒤 응답을 캡처한다. 리뷰는 공개 데이터라 로그인이 필요 없다.

- **리뷰 API**: `/n/v1/contents/reviews/group-products/query-pages` (XHR, POST)
- **페이지네이션**: 리뷰 전체보기 모달 → 스크롤 → 다음 페이지 (페이지당 20개)

---

## 파일 구조

```
review-analyzer/
├── SKILL.md                      # 이 파일
├── .env.example                  # (선택) 로그인 모드용 자격증명 템플릿
└── scripts/
    ├── naver-brand-reviews.py    # 메인 CLI (크롤 + 파싱 + 저장)
    ├── cookie_extractor.py       # 세션 + XHR 인터셉터 엔진 (NaverSession)
    └── requirements.txt
```

`cookie_extractor.py`의 `NaverSession`이 인터셉터 설치·리뷰 트리거·응답 캡처를 담당한다.

---

## 트러블슈팅

### 리뷰가 수집되지 않음 (인터셉터 타임아웃)
- 리뷰 탭/페이지네이션 클릭이 안 되면 네이버 페이지 구조 변경 가능성 → `cookie_extractor.py`의 셀렉터 업데이트 필요
- 정렬이 "not found"로 나오면 정렬 버튼 텍스트 변경 → `change_sort`의 매칭 로직 확인 (현재는 `<button>` + '…정렬하기' 텍스트 기준)

### ID 자동 추출 실패
- 페이지 구조가 바뀌어 `extract_ids_from_page`의 정규식이 안 맞을 수 있음
- 우회: F12 → Network → `query-pages` 요청 Payload에서 `checkoutMerchantNo`(merchantNo), `originProductNos`(productNo)를 확인해 인자로 직접 지정
  ```bash
  python3 .../naver-brand-reviews.py <merchantNo> <productNo> --no-login --referer '<제품URL>'
  ```

### Chrome/드라이버 오류
- `pip install -U selenium` (4.6+ 자동 드라이버 관리)
- Chrome 브라우저가 설치돼 있는지 확인

---

## (선택) 로그인 모드 · 구글 시트 업로드

공개 리뷰엔 불필요하지만, 필요 시:
- **로그인 모드**: `.env.example`을 `.env`로 복사해 `NAVER_ID`/`NAVER_PW` 입력 후 `--no-login` 대신 `--selenium` 사용 (`pyperclip`, `python-dotenv` 필요)
- **구글 시트 업로드**: `--sheet '<시트URL>'` 사용. 본인 Google 서비스 계정(`~/.config/gspread/service_account.json`)과 시트 편집 권한이 필요 (`gspread`, `google-auth` 필요)

---

## 버전

- v1.0.0 (2026-07-04): 전역 review-analyzer v4.1.0에서 워크스페이스용으로 이식. 네이버 브랜드스토어 크롤(로그인 불필요, URL→ID 자동 추출, 4정렬), 4단계 분석 프레임워크 포함. 개인 자격증명·다나와·개인 시트 의존 제거
