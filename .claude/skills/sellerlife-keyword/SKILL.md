---
name: sellerlife-keyword
description: 셀러라이프(sellochomes.co.kr)에 자동 로그인해 '카테고리 소싱' 전체 엑셀을 받아, 필터링 + Gemini 브랜드/상표 판정까지 한 번에 처리하고 바로 쓸 수 있는 안전 키워드 엑셀을 만든다. "셀러라이프 키워드", "카테고리 소싱 받아줘", "키워드 파일 가공", "rawdata 가공", "브랜드 키워드 걸러줘", "키워드 블랙리스트", "셀러라이프 다운" 등을 언급하면 자동 실행. 반영 전 검토_*.xlsx 승인 필요.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
---

# 셀러라이프 키워드 소싱 파이프라인

`다운로드 → 필터 → AI 브랜드 판정 → 최종/검토 분리` 를 명령 한 줄로 수행한다.
이룸님이 손대는 지점은 **마지막 검토 승인 한 곳뿐**이다.

기존 수작업(`sellerlife_filter.py` + `gemini_detector.py` + 손으로 엑셀 다운로드)을 대체한다.

> **키워드→상품명 파이프라인과의 관계**: 이 스킬은 "대량 안전 키워드 풀 생성"(별도 상류 스테이지)이고,
> `keyword-pick`(상품 1개용 6개 선별)과는 목적이 다르다. 흡수하지 않는다. 다만 여기서 만든 `최종_*.xlsx`(안전 키워드)를
> **③ 키워드 raw 소스로 keyword-pick에 태울 수 있다** — 필요한 카테고리 행만 걸러 `keyword-filter.py`에 넘기면 된다
> (`상품수` 컬럼이 부분일치로 인식됨). 전체 흐름은 `keyword-pick/references/keyword-pipeline-flow.md` 참조.

## 사전 요구사항

- **워크스페이스 `.venv`** — selenium · openpyxl · requests (추가 설치 불필요, `google-genai` 안 씀)
- **`.env`** (이 폴더) — `SELLERLIFE_GOOGLE_EMAIL`, `GEMINI_API_KEY`. **구글 비밀번호는 저장하지 않는다.**
- **최초 1회 구글 로그인** — 아래 Step 0
- **블랙리스트** — `d:\python_work\data\sellerlife\keyword_blacklist\keyword_blacklist.xlsx` (단일 원본, 계속 누적)
- **통다운 raw** — 로컬에 없으면 구글 드라이브 `51-셀러라이프-통다운` 에서 받는다 (→ Step 0-b)

## Workflow

### Step 0-a. 새 PC 최초 1회 — 설치 (대화형)
```bash
PYTHONIOENCODING=utf-8 python .claude/skills/sellerlife-keyword/scripts/install.py
```
저장 루트(`DATA_ROOT`)·구글 이메일·Gemini 키를 물어 `.env` 를 쓰고, `runs/`·`keyword_blacklist/` 를 만들고,
`assets/keyword_blacklist.xlsx` 가 동봉돼 있으면 복사한다. **기존 블랙리스트는 덮지 않는다.**
기존 `.env` 값이 기본값이 되므로 재실행해도 안전. `--data-root <경로> --yes` 로 비대화형 실행 가능.

> 이미 세팅된 PC(이룸님 본 PC)에서는 건너뛴다. `.env` 에 `DATA_ROOT` 가 없으면 `d:\python_work\data\sellerlife` 로 동작.
> 블랙리스트 기본 경로는 `<DATA_ROOT>/keyword_blacklist/keyword_blacklist.xlsx` 로 따라간다.

### Step 0. 최초 1회 — 구글 로그인 (사람이 직접)
```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe .claude/skills/sellerlife-keyword/scripts/download.py --setup --wait 600
```
Chrome 창이 `/auth/login` 에서 **'구글로 시작하기'** 를 누른 상태로 뜬다.
이룸님이 그 창에서 **직접** 구글 로그인(2FA 포함)을 끝내면 스크립트가 자동 감지하고 종료한다.
세션은 `_chrome_profile/` 에 남아 이후 실행은 자동 통과한다.

- `--wait N` — 사람 로그인 대기 초 (기본 300). 자리를 비울 거면 넉넉히.
- 대기 중 15초마다 현재 URL/제목을 찍는다. 구글이 '안전하지 않을 수 있습니다' 로 막으면 즉시 감지해 알린다.
- **Chrome 창이 다른 창 뒤에 숨을 수 있다.** 작업표시줄을 확인할 것.

> 구글은 Selenium 의 자동 비밀번호 입력을 차단한다. 그래서 비밀번호 단계는 딱 한 번 사람이 통과한다. 셀록홈즈 세션 자체는 Chrome 을 닫으면 만료되지만, **구글 세션이 프로필에 남아 다음 실행부터는 계정 선택 화면을 자동 클릭해 비밀번호 없이 재로그인**한다(사람 개입 0). `.env` 에 비밀번호를 저장하지 않는 이유다.
> 몇 달 뒤 구글 세션이 만료되면 자동 실행이 "비밀번호/2FA 필요"를 감지해 `--setup` 재실행을 안내한다.

### Step 0-b. 통다운을 드라이브에서 받기 (셀러라이프 재다운로드 대신)

통다운 raw 의 **단일 원본은 구글 드라이브 `51-셀러라이프-통다운` 폴더**다
(`runs/<YYMMDD>/raw/` + `keyword_blacklist/` 구조 그대로).
PC 를 옮겼거나 로컬에 raw 가 없으면 **셀러라이프에 다시 로그인해 받지 말고 여기서 가져온다.**

```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe .claude/skills/sellerlife-keyword/scripts/pull_drive.py --list          # 날짜 목록
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe .claude/skills/sellerlife-keyword/scripts/pull_drive.py                  # 최신 날짜
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe .claude/skills/sellerlife-keyword/scripts/pull_drive.py --date 260731 --blacklist
```

- `<DATA_ROOT>/runs/<YYMMDD>/raw/` 로 내려받는다 → 그대로 `product-name --source-date <YYMMDD>` 에 물린다
- 같은 크기 파일은 건너뛴다(재실행 안전). 전제는 `gws` CLI 인증뿐 — 셀러라이프 로그인 불필요
- 구버전 레이아웃(raw/ 없이 날짜 폴더에 xlsx 직접)도 인식한다
- **새로 받은 통다운은 이 드라이브 폴더에 올려 원본을 한 곳으로 유지한다**

### Step 1. 파이프라인 실행 (매번 이것만)
```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe .claude/skills/sellerlife-keyword/scripts/run_all.py
```
→ `d:\python_work\data\sellerlife\runs\<YYMMDD>\` 에 산출물 생성:

| 파일 | 내용 |
|---|---|
| `최종_통합_<YYMMDD>.xlsx` | **3개 카테고리 합본** (맨 앞 `소싱카테고리` 열 + 13열). 바로 소싱에 사용 |
| `최종_가구인테리어.xlsx` 등 3개 | 카테고리별 '안전' 행, 13열 (합본의 원본) |
| `검토_가구인테리어.xlsx` 등 3개 | **AI위험 행 + AI분류/AI사유 + `승인` 열(규칙대로 미리 채워짐)** |

`--force`(재다운로드) · `--skip-download` · `--ship-rate` · `--max-price` · `--max-products` · `--headless` 지원.
`finalize.py` 단독 실행 시 `--no-prefill`(승인 자동채움 끔) · `--no-merge`(통합본 끔) 지원.

### Step 2. 검토 → 승인 (자동채움 + 오탐만 정리)
`검토_*.xlsx` 의 `승인` 열은 **규칙대로 미리 채워져** 나온다:
- `어린이용` 분류 → 키워드에 아동 표현(어린이/유아/키즈/아동/주니어/초등/고학년/아기/공주/남매/아이)이 있을 때만 `O`, 없으면 빈칸(성인 겸용 오탐 살림)
- 그 외 분류(브랜드/캐릭터/상표/모델 등) → `O`

사람은 파일을 열어 **오탐만 빈칸으로 지우면** 된다 (`X` 는 승인으로 인정 안 함). 규칙 상수는 `common.py`의 `KID_TOKENS`.

### Step 3. 블랙리스트 반영
```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe .claude/skills/sellerlife-keyword/scripts/blacklist_update.py --review-dir "d:\python_work\data\sellerlife\runs\<YYMMDD>"
```
- 원본은 타임스탬프 백업(`.bak_YYMMDD_HHMM.xlsx`) 후 `제외키워드` 시트에 append
- 이미 있는 키워드는 건너뜀 · `--dry-run` 으로 미리보기
- **`run_all.py` 는 절대 블랙리스트를 건드리지 않는다.**

다음 실행부터 그 키워드들은 AI 호출 전에 자동 제외된다 → 갈수록 빨라지고 정확해진다.

## 파이프라인 상세

| 스크립트 | 역할 |
|---|---|
| `download.py` | 구글 로그인(전용 프로필) → 셀러라이프 → 상품 소싱 → 카테고리 소싱 → '전체 카테고리 엑셀 다운로드'. `--setup` / `--probe` |
| `ingest.py` | ZIP 해제 → 대상 3개 카테고리만 추출 (단일 엑셀 형태도 지원) |
| `filter.py` | 열 22개 삭제(35→13열) + 행 필터 6종. **openpyxl 스트리밍** (원본 최대 260MB) |
| `detect.py` | ①카테고리 제외 ②키워드 정확일치 제외 ②.5 브랜드 부분일치 제외(`제외브랜드` 시트) ③Gemini 배치 판정. **이어하기 지원** |
| `finalize.py` | 카테고리별 `최종`/`검토` 분리. 분할 파일(`생활&건강2`) 병합 + **최종 통합본 생성** + 검토 `승인` 규칙 **자동채움**(어린이용은 아동표현 명시분만). `--no-prefill`/`--no-merge` |
| `blacklist_update.py` | 승인된 것만 블랙리스트에 추가 |
| `run_all.py` | 위 전부를 순서대로 |
| `install.py` | 새 PC 최초 설치. 저장 경로·계정·키를 묻고 `.env`+폴더 생성 |

### 필터 기준 (기본값)
- 브랜드키워드 `O` 제거 · 쇼핑성키워드 `X` 제거
- 네이버 상품수 ≤ 30,000
- 네이버·쿠팡 해외배송비율 각각 ≥ 0.1 (10%)
- 네이버 평균가 ≤ 5,000,000 (빈칸·0은 '가격정보 없음'이라 유지)

### 블랙리스트 시트 3종
- **`제외카테고리`** (부분일치) — 카테고리 경로에 조각이 포함되면 제외. 헤더 없음, A열.
- **`제외키워드`** (정확일치) — 키워드가 정확히 같으면 제외. `blacklist_update.py`가 검토 승인분을 여기 append.
- **`제외브랜드`** (부분일치) — 어근이 키워드에 **포함**되면 제외 (예: `하리오`→`하리오알파02`, `df64`→`df64e그라인더`). 대소문자 무시. 브랜드/모델명 전용, **수동 관리**. `와인잔`·`소주잔` 같은 도구/잡화는 어근에 안 넣어 오탐 방지. 시트가 없으면 조용히 건너뜀(선택 기능).

### AI 판정 (Gemini)
- REST 직접 호출 (`gemini-2.5-flash-lite`, `responseSchema` 로 `risk` 를 `Y`/`N` enum 고정)
- 배치 60개 · 429 백오프 재시도 4회
- 실패한 행은 `AI오류-재실행필요` 로 남고, **같은 명령을 다시 돌리면 그 행만** 재처리

## 동작 원리 (주의점)

- **20만행 export 상한**: 셀러라이프는 카테고리당 20만행에서 파일을 쪼갠다(`생활&건강` + `생활&건강2`). `cat_key()` 가 꼬리 숫자와 `&`/`/` 표기를 흡수해 같은 카테고리로 묶고, `finalize` 가 하나로 병합한다.
- **대용량**: rawdata 는 카테고리당 100~260MB, 총 50만행. `pd.read_excel` 은 메모리를 터뜨리므로 `filter.py` 는 read_only 스트리밍으로 읽는다.
- **시트명 계약**: `filter.py` 출력 시트는 반드시 `Sheet1`. `detect.py` 가 이걸 읽는다.
- **열은 이름으로 찾는다**: 헤더에 줄바꿈(`브랜드\n키워드`)이 섞여 있어 `norm()` 으로 정규화 후 매칭. 열 순서가 바뀌어도 안전.
- **`_create_driver` 는 건드리지 않았다**: 프로필 인자가 없고 호출자가 3곳이라, `common.make_driver()` 로 따로 뒀다.

## 트러블슈팅

- **`user data directory is already in use`** → 이 프로필로 띄운 Chrome 창을 닫고 재실행.
- **로그인이 안 잡힘 / 세션 만료** → `download.py --setup` 을 다시 실행.
- **메뉴·버튼을 못 찾음** → `download.py --probe` 로 실제 페이지 텍스트를 덤프해 `SOURCING_HINTS` / `DOWNLOAD_BTN_HINTS` 를 갱신.
- **ZIP 안 한글 파일명이 깨짐** → `ingest._decode_member()` 가 cp437→cp949 로 복구. 그래도 깨지면 `--probe` 출력의 실제 멤버명을 확인.
- **Gemini 401/403** → `.env` 의 `GEMINI_API_KEY` 확인 (https://aistudio.google.com/apikey). `AQ.` · `AIza` 키 모두 동작.
- **429 한도초과** → `--batch-size` 를 줄이거나 `detect.py --sleep 7`.
- **`AI오류-재실행필요` 가 남음** → `run_all.py --skip-download` 을 한 번 더 실행하면 그 행만 재처리.

## 보안

- `.gitignore` 로 `.env` · `_chrome_profile/` · `_dl_tmp/` 를 제외한다. **`_chrome_profile/` 에는 구글 세션 쿠키가 들어있어 커밋되면 계정이 탈취된다.**
- 구글 비밀번호는 어디에도 저장하지 않는다.

## 실측 (2026-07-12 전 구간 실전 검증 완료)

- 로그인 진입: 헤더 `로그인/회원가입` → `https://sellochomes.co.kr/auth/login`
- 구글 버튼: `<a class="btn-google" href="/auth/google">구글로 시작하기</a>` — **팝업 아님, 같은 탭 리다이렉트**
- **셀록홈즈 세션은 세션 쿠키** → Chrome 닫으면 만료. 하지만 구글 세션은 프로필에 남아, 재실행 시 앱이 강제하는 `prompt=select_account` 계정 선택 화면에서 **계정 타일(`div[data-identifier="이메일"]`)을 자동 클릭**해 비밀번호 없이 3초 만에 재로그인 (사람 개입 0).
- 카테고리 소싱 페이지: **`https://sellochomes.co.kr/sellerlife/sourcing/category/`** (메뉴 클릭 대신 직접 진입)
- 다운로드 버튼: **`button.all-excel`** (아이콘 버튼, 텍스트 없음). 홍보 모달이 떠도 다운로드는 진행됨.
- 다운로드 산출물: **`SellarSourcingAll_<날짜>.zip` (~205MB)**, 내부 12개 카테고리 xlsx (파일명 cp949). 대상 3개(가구&인테리어·디지털&가전·생활&건강+생활&건강2)만 추출, 나머지 8개(도서·식품·스포츠&레저·여가&생활편의·출산&육아·패션의류·패션잡화·화장품&미용) 버림.
- rawdata: 시트명 `all`, 35열, 헤더에 줄바꿈. 카테고리당 100~260MB / 최대 20만행
- 필터 통과: 가구인테리어 5,120 · 디지털가전 15,503 · 생활건강 16,507+5,489 = **42,619행**
- Gemini `AQ.` 키는 REST(`x-goog-api-key` 헤더 · `?key=` 쿼리) 양쪽 다 200 OK

## 버전

- v1.1.0 (2026-07-31): 이관 대응. `install.py`(대화형 설치 — 저장 경로를 설치 시 지정) 추가.
  블랙리스트 기본 경로를 `d:\python_work...` 하드코딩에서 `<DATA_ROOT>` 추종으로 교체
  (`common.DEFAULT_BLACKLIST` 상수 → `default_blacklist()` 함수).
- v1.0.1 (2026-07-12): 전 구간 실전 검증. 카테고리 소싱 URL·`button.all-excel`·ZIP 구조 확정. 구글 세션 자동 계정선택(재로그인 사람개입 0). is_logged_in 오탐(빈 페이지) 수정. Gemini SDK 제거(REST).
- v1.0.0 (2026-07-10): 초판. 구글 OAuth(전용 프로필) 다운로드 + 스트리밍 필터(SyntaxError 수정) + Gemini REST 판정(SDK 의존성 제거, risk enum 고정) + 최종/검토 분리 + 승인 기반 블랙리스트 누적.
