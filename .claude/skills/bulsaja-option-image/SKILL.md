---
name: bulsaja-option-image
description: 불사자 상품의 판매 중 옵션 이미지(중국어 원본)를 한국어 스펙이 들어간 깨끗한 제품 이미지로 다시 만들어 교체한다. 옵션 이미지가 쿠팡 썸네일로 쓰이는 상품에 특히 필요. "옵션 이미지 작업해줘", "옵션 이미지 바꿔줘", "옵션 이미지 교체", "옵션 이미지 한국어로", "옵션 썸네일 만들어줘", "옵션별 이미지 생성" 등을 언급하거나 상품코드를 주고 옵션 이미지 작업을 요청하면 자동 실행. ※ 대표 썸네일은 bulsaja-thumbnail, 옵션명·판매범위 정리는 bulsaja-option-cleanup.
allowed-tools:
  - Bash
  - Read
  - Write
---

# 불사자 옵션 이미지 교체

판매 중인 옵션마다 **원본 사진을 그대로 두고** 배경·중국어·로고만 걷어낸 뒤 한국어 스펙 문구를
얹은 이미지를 만들어 불사자 옵션 이미지로 교체한다. 1회 실행 = 1상품.
불사자 공통 안전선은 [`_shared/불사자-안전규칙.md`](../_shared/불사자-안전규칙.md).

## 왜 필요한가

옵션 이미지는 타오바오 원본(중국어 배지·중국 브랜드 로고)이 그대로 남는다. 옵션 이미지를 마켓 썸네일로
쓰는 상품(예: 쿠팡 썸네일 모드 "옵션 이미지 사용" — `product.json` 의 `coupang_uploaded` 가 참이면 그 상품)은
**옵션 이미지 = 마켓 썸네일**이라 그대로 두면 중국어 썸네일이 노출된다.
아이템위너 회피에도 자체 이미지가 유리하다(보조 수단 — 주 수단은 브랜드 속성+자체 모델명).

## 흐름 (4단계, 검수는 Claude 가 직접)

```bash
cd .claude/skills/bulsaja-option-image/scripts
PY=C:/Users/workspace/.venv/Scripts/python.exe   # PYTHONUTF8=1 필요

# ① 조회 (쓰기 없음) — 판매 중 옵션 목록·현재 이미지·기작업 여부 → options.json
PYTHONUTF8=1 $PY run.py inspect --code <판매자상품코드 또는 상품ID>
#    run-dir 기본값 C:/python_work/data/option-image/<코드>/   (--run-dir 로 변경)
#    첫 줄의 [계정] 이 의도한 계정(닉네임·이메일)인지 반드시 본다 — §계정

# ② spec.json 작성 — Claude 가 원본을 보고 쓴다 (§spec)

# ③ 생성 (OpenAI 과금, 장당 30~90초, 기본 3장 동시) → gen_<옵션번호>.png
PYTHONUTF8=1 $PY run.py generate --run-dir <R> [--vids 2,3] [--force]

# ④ 검수 (§검수) → 통과분만 반영 → 재조회 검증까지 자동
PYTHONUTF8=1 $PY run.py apply --run-dir <R> [--vids 2,3]
PYTHONUTF8=1 $PY run.py restore --run-dir <R>      # 되돌리기 (before_apply.json 기준)
```

- **①→② 사이**에 Claude 가 `inspect` 가 받아 둔 현재 옵션 이미지 `cur_<번호>.*` 를 `Read` 로 전부 열어
  실물·스펙을 확인한다. 상세페이지 이미지 주소는 `product.json` 의 `detail_images` 에 있다 — 스펙 근거가
  더 필요하면 `curl -s -o <R>/detail_N.jpg <주소>` 로 받아 `Read` 로 연다.
- **③→④ 사이**에 Claude 가 `gen_*.png` 를 전부 `Read` 로 열어 검수한다. 스크립트가 대신하지 않는다.
- 반영은 검수 통과 즉시 한다(2026-08-06 `_shared/스킬-계약.md` §반영은 기본 자동). 불합격 옵션은
  `--vids` 로 빼고 나머지만 반영한 뒤 보고에 사유를 싣는다.
- **마켓 재업로드는 이 스킬 범위 밖**이다. 옵션 이미지를 바꿔도 이미 올라간 쿠팡 상품에 자동 반영되진
  않는다 — 필요하면 별도 요청으로 `bulsaja_market_upload`(접수 전 확인).

## spec — Claude 가 쓰는 유일한 판단 파일

`<R>/spec.json`. 예(2026-09-16 탄산디스펜서 실측본):

```json
{
  "product_desc": "stainless steel beverage dispenser",
  "background": "soft light blue gradient",
  "angle": "",
  "common_texts": [
    "Left side vertical measurement line: \"높이 58CM\"",
    "Two bottom dimension callouts near the base: \"폭 35CM\" and \"길이 26CM\"",
    "Small badge near the faucet: \"스테인리스 수도꼭지 업그레이드\""
  ],
  "options": {
    "2": {"banner": "단일 헤드 8리터 - 두꺼운 유형 - 실버"},
    "3": {"banner": "단일 헤드 8리터 - 두꺼운 유형 - 골드",
          "source": "https://img.alicdn.com/bao/uploaded/i2/.../O1CN01aaRe0s....jpg"}
  }
}
```

| 키 | 규칙 |
|---|---|
| `product_desc` | 영어 한 구절. "이 물건 그대로"를 모델에 못 박는 용도 |
| `common_texts` | 모든 옵션에 공통으로 얹을 문구. `위치(영어): "한국어 문구"` 형식 |
| `options.<번호>.banner` | 하단 띠 문구. 옵션 구분(색상·규격)이 여기 들어간다 |
| `options.<번호>.source` | 생성 소스(주소 또는 로컬 경로). 생략 = 현재 옵션 이미지. **기작업 옵션을 다시 만들 땐 가공본 위에 또 만들지 않는다** — 이전 run-dir 의 `src_<번호>.*`(첫 작업 때 받아 둔 원본) 나 타오바오 원본 주소를 넣는다. 그래서 **run-dir 을 지우지 않는다** |
| `angle` | 생략 권장. 앵글 지시는 효과가 작고 왜곡 위험만 는다(실측) |
| `size` | 생략 = `1024x1024`. 세로 원본이면 `1024x1536`, 가로면 `1536x1024` |

**문구는 원본에 있는 것만 쓴다.** 치수·용량·재질·기능은 옵션 원본 이미지·옵션명(`name_cn`)·상세페이지에서
**읽은 것만** 넣는다. 원본에 없는 스펙을 만들어 넣으면 CS 로 돌아온다. 원본에 "두꺼운 유형" 배지만 있고
강화형/일반형 구분이 없으면 이미지도 구분하지 않는다(옵션명으로만 구분). 중국 브랜드명은 넣지 않는다.

`inspect` 의 상태 열: `원본`(타오바오) · `번역본`(불사자 자동번역 — 글자가 깨져 있을 수 있으니 열어 보고,
지저분하면 `source` 에 타오바오 원본 주소) · `기작업`(우리가 이미 교체 — `--force` 나 `source` 없이는 건너뜀).

## 검수 (반영 전, 옵션마다 전부 연다)

| 축 | 불합격 기준 |
|---|---|
| 스펙 문구 | 오타·숫자 틀림·한자 잔존·문구 누락 |
| 제품 동일성 | 형태·부품·비율이 원본과 다름, 색상 옵션인데 색이 안 바뀜(골드인데 실버) |
| 잔존물 | 중국 로고·워터마크·중국어 |
| 배경 | 소품·그림자 지저분함, 제품이 잘림 |

불합격은 `--force --vids <번호>` 로 그 옵션만 재생성(프롬프트는 spec 을 고쳐서). 2회 불합격이면
그 옵션은 빼고 보고한다. `--force` 를 `--vids` 없이 주면 spec 의 전 옵션을 다시 만든다(과금) — 스크립트가
경고만 찍고 진행하니 옵션 번호를 꼭 붙인다. 일시 오류(타임아웃·안전필터)는 스크립트가 1회 자동 재시도한다.

## 원장·보고

- `apply` 가 `C:/python_work/data/option-image/ledger.jsonl` 에 한 줄 append 한다(시각·계정·상품·옵션별
  전/후 주소·검증 결과). 이 스킬은 1상품 단위라 구글시트 대신 **로컬 원장**을 쓴다(2026-09-16 결정 —
  대량 회차가 생기면 그때 시트로 올린다).
- 종합보고에 싣는 것: 계정(닉네임) · 상품명 · 반영한 옵션 수와 이름 · 생성 장수(OpenAI 과금 건수, 재시도
  포함) · 불합격/제외 옵션과 사유 · 복원 명령.

## 계정

쓰기 전 `[계정]` 줄의 닉네임·이메일이 의도한 계정인지 확인한다. 이름은 `scripts/.env` 의
`BULSAJA_ACCOUNT_KEY`(기본 `bulsaja-yongssaem` = 마켓용 용쌤 계정) 또는 `--account`.
**이 PC 는 전역 환경변수 `BULSAJA_MCP_TOKEN` 이 박혀 있어** 다른 스킬의 파이썬 클라이언트는 계정
이름을 무시하고 용팀장 계정으로 붙는다. 이 스킬의 `load_config_by_key()` 는 그 변수를 걷어내고
`~/.claude.json` 의 이름으로만 찾는다(실측 2026-09-16 — 상품이 "없다"고 나오면 이 문제부터 의심).

## 산출물 (`<R>/`)

`product.json`(상품ID·계정·상세 이미지 주소) · `options.json`(판매 중 옵션) · `cur_<번호>.*`(현재 옵션 이미지) ·
`spec.json` · `src_<번호>.*`(생성 소스) · `prompt_<번호>.txt` · `gen_<번호>.png` ·
`before_apply.json`(교체 전 옵션값·가격탭 주소, 복원용) · `after_apply.json`

## 알려진 제약·함정

- **1차원 옵션만.** 선택 항목이 2개 이상인 복합옵션은 옵션 번호가 차원마다 겹쳐 `inspect` 가 거부한다.
- 옵션 이미지 교체 도구는 옵션값 이미지와 가격탭 이미지를 **같이** 바꾼다(번호 지정 시). `apply` 는
  재조회로 옵션값 주소가 바뀌었는지 확인한다 — 성공 응답만 믿지 않는다. `before_apply.json` 은 둘을
  따로 저장하고, `restore` 는 원래 둘이 달랐던 옵션만 가격탭을 별도로 되돌린다.
- 업로드 티켓은 5분 1회용. `apply` 가 티켓 발급 직후 바로 올리므로 사람이 끼어들 틈이 없다.
- 업로드 주소는 내용 해시로 정해진다 — 같은 그림을 다시 올리면 같은 주소가 나오고 교체는 `변경 0건`
  으로 끝난다(멱등, 실측). `apply` 를 두 번 돌려도 안전하다는 뜻이지 실패가 아니다.
- 생성 모델은 gpt-image-2 고정(용팀장 지시). 키는 `scripts/.env` → 없으면 `smartstore-brand/scripts/.env` 재사용.
- 상세 조회 도구(`bulsaja_product_detail`)에는 옵션 이미지 주소가 안 나온다. 가공 현황(`workdata`)으로 본다.

## 테스트

```bash
cd .claude/skills/bulsaja-option-image/scripts
PYTHONUTF8=1 C:/Users/workspace/.venv/Scripts/python.exe -m unittest test_option_rules -v
```

네트워크 없이 옵션 추리기·기작업 판별·spec 검증·프롬프트 조립을 검증한다. 반영·복원은
2026-09-16 실제 상품(탄산디스펜서, 옵션 4개)으로 apply→restore 왕복 확인했다.
