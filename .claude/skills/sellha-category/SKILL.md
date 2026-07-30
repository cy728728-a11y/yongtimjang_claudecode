---
name: sellha-category
description: 상품명/키워드 하나 이상을 받아 셀하(sellha.kr)에서 그 키워드가 속한 네이버 카테고리 경로(예 '디지털/가전 > 주변기기 > 마우스 > 무선마우스')와 확신도를 조회하는 단일 목적 도구. 셀하에 이메일 로그인 후 research 페이지를 렌더해 최빈 카테고리 라인을 파싱한다. CLI(JSON in/out)라 다른 스킬이 subprocess 로 재사용한다(불사자 카테고리 교정·대표키워드 도출이 이 도구를 부른다). "셀하에서 카테고리 조회", "이 키워드 네이버 카테고리 뭐야", "셀하 카테고리 경로", "sellha 조회", "키워드 카테고리 확인" 처럼 **셀하 카테고리 경로만 알고 싶을 때** 자동 실행. ※ 불사자 상품 카테고리를 실제로 교정·저장하는 전체 흐름은 bulsaja-category-fix 스킬이 담당(이 도구를 내부에서 호출).
allowed-tools:
  - Bash
  - Read
---

# 셀하 카테고리 조회 (sellha-category)

셀하(sellha.kr)를 렌더해 **상품명/키워드 → 네이버 카테고리 경로 + 확신도**를 뽑는 단일 목적 도구.
아이템스카우트와 달리 확장 프로그램 없이 렌더되므로 크롤 가능하다.

이 스킬은 **재사용 부품**이다. 불사자 카테고리 교정(`bulsaja-category-fix`)과
대표키워드 도출(`rep-keyword`)이 이 도구를 CLI subprocess 로 호출한다. 실제 상품 카테고리
저장·교정 흐름은 `bulsaja-category-fix` 가 담당하고, 이 스킬은 "경로 조회"만 한다.

## 준비 (최초 1회)

`.claude/skills/sellha-category/.env` 에 셀하 자격증명을 넣는다(git 제외):

```
SELLHA_EMAIL=<셀하 이메일>
SELLHA_PW=<셀하 비밀번호>
```

드라이버는 `eroomlib.webdriver`(봇 감지 우회 Chrome)를 쓴다. selenium 이 venv 에 있어야 한다.

## 사용

```bash
PY=".venv/Scripts/python.exe"     # 저장소 루트 기준
S=".claude/skills/sellha-category/scripts/sellha.py"

# 1) 키워드 하나 이상 즉시 조회 (stdout JSON)
"$PY" "$S" --query "무선 마우스" "낚시텐트"

# 2) 배치: [{"productId":"..","name":".."}] JSON → 결과 JSON
"$PY" "$S" --input targets.json --output result.json --resume
```

**창 숨김(headless)이 기본값**이다(2026-07-30, 이룸님 확정 — 카테고리 교정 중 크롬창이 화면에
반복적으로 뜨는 게 방해가 됨). 렌더 이슈(파싱실패 다발 등)를 눈으로 직접 확인해야 할 때만
`--no-headless` 로 창을 띄운다.

주요 옵션: `--no-headless`(디버깅용 창 표시) · `--resume`(output 의 성공건 스킵, 실패건만 재시도) ·
`--restart-every N`(N건마다 브라우저 재시작, 장시간 드라이버 행 방지).

## 반환 (항목별 dict)

| 필드 | 뜻 |
|------|-----|
| 검색어 | 조회한 상품명/키워드 |
| productId | (배치 입력 시) 입력 id 그대로 |
| 카테고리경로 | '대분류 > … > 최종차수' |
| 최종차수 | 경로 마지막 차수(불사자 카테고리 검색 키워드로 씀) |
| 확신도 | 셀하가 준 % (최빈 카테고리 신뢰도) |
| 마켓 | 네이버 |
| url | 조회 research URL |
| 상태 | 성공 / 조회실패(검색결과없음) / 파싱실패 / 로그인실패 |
| error | 실패 사유 |

## 트러블슈팅

- **로그인 실패**: 비번 변경 시 `.env` 갱신. 로그인 폼 구조 변경 시 `sellha.py` 의 `login()` 셀렉터 갱신.
- **파싱실패 다발**: 셀하 페이지 구조 변경 가능 → `sellha.py` 의 `CAT_PAT` 정규식 점검.
- **장시간 배치 드라이버 행**: `--restart-every 150` 로 주기적 재시작(기본값).
