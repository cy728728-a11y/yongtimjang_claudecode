---
name: naver-category-master
description: 네이버 쇼핑 전체 카테고리(코드↔경로) 마스터 파일을 커머스API로 수집·갱신하고, 경로→코드·코드→경로·최종차수명→후보 를 역조회하는 도구. "카테고리 코드 뭐야", "이 경로 카테고리 번호", "카테고리 마스터 갱신", "카테고리 코드 검증" 처럼 **번호와 경로를 서로 변환하거나 전체 목록을 다시 받을 때** 실행. ※ 키워드로 카테고리 경로를 새로 조회하는 건 aside-category 가 담당한다.
allowed-tools:
  - Bash
  - Read
---

# 네이버 카테고리 마스터 (naver-category-master)

네이버 커머스API `GET /v1/categories` 로 **전체 카테고리를 한 번에 전량** 받아 마스터 파일로 두고,
경로↔코드를 오프라인으로 변환한다. **네트워크·확장·로그인이 필요 없다** — 그 점이 `aside-category` 와 다르다.

| | aside-category | **naver-category-master** |
|---|---|---|
| 하는 일 | 키워드 → 카테고리 **경로 추정** | 경로 ↔ **코드 변환**(사실 조회) |
| 근거 | 네이버 검색 1페이지 분포 | 네이버 공식 카테고리 원장 |
| 비용 | 9초/건, 캡챠·차단 위험 | 0초, 위험 없음 |
| 확신도 | 있음(추정이므로) | 없음(사실이므로) |

## 마스터 파일

`30-knowledge/39-naver-category/naver-category-master.json`

```
총건수 5815 · 최종차수 4999 · 중복경로 0        (2026-08-08 수집)
```

| 키 | 내용 |
|---|---|
| `카테고리` | 원본 행 배열 — `id` · `name` · `wholeCategoryName` · `last` · `경로정규화` |
| `경로to코드` | `"A > B > C"` → `"50003340"` 역조회 색인 |
| `중복경로` | 같은 경로에 코드가 둘 이상인 건(현재 0). **자동 확정 금지 대상** |

> `wholeCategoryName` 은 네이버가 `A>B>C`(공백 없음)로 준다. `경로정규화` 는 이걸 `A > B > C` 로
> 바꿔 놓은 값이라 **aside-category 의 `카테고리경로` 와 그대로 대조된다.**

## 갱신 (커머스API 호출)

```bash
.venv/bin/python .claude/skills/naver-category-master/scripts/fetch_categories.py
```

- 인증: `.env` 의 `NAVER_COMMERCE_CLIENT_ID` · `NAVER_COMMERCE_CLIENT_SECRET` (**.gitignore 처리됨**)
- 서명 방식: `bcrypt("{client_id}_{timestamp}", salt=client_secret)` → base64. **시크릿 자체가 bcrypt salt**다
- 의존성: `bcrypt` · `requests` (`uv pip install --python .venv/bin/python bcrypt requests`)
- 카테고리 개편은 잦지 않다. **분기 1회 정도면 충분**하다

### 실패하면 순서대로 본다

1. **토큰 발급 실패(401/403)** — 커머스API센터에 등록한 **호출 IP** 가 현재 공인 IP와 같은가.
   유동 IP라 바뀌었을 가능성이 가장 크다.
2. **시크릿 형식 오류** — 화면에서 드래그 복사하면 값이 깨진다. `[보기] > 인증 > [복사]` 로 다시 받는다.
3. **timestamp 오차** — 맥 시각이 크게 틀어져 있으면 서버가 거부한다.

## 역조회 (오프라인)

```bash
L=".claude/skills/naver-category-master/scripts/lookup.py"

.venv/bin/python $L --path "스포츠/레저 > 캠핑 > 캠핑왜건"   # → 50009182
.venv/bin/python $L --code 50008848                          # → 가구/인테리어 > DIY자재/용품 > 리모델링 > 창문/창호/새시
.venv/bin/python $L --leaf 인테리어조명                       # → 후보 목록
.venv/bin/python $L --verify result.json                     # aside-category 결과 교차검증
```

파이썬에서 직접 쓸 수도 있다:

```python
from lookup import CategoryMaster
m = CategoryMaster()
m.code_of("디지털/가전 > 주변기기 > 마우스 > 무선마우스")  # '50002927'
m.by_leaf("기타")                                          # 후보 19건 — 이름만으론 확정 불가
```

## ★ 최종차수명은 코드를 확정하지 못한다

`--leaf 기타` 는 **19건**을 돌려준다. `bulsaja-category-fix` 가 최종차수명으로 불사자 카테고리를
검색하는 구간에서 이런 이름을 만나면 **엉뚱한 대분류로 저장될 수 있다.**
이름이 아니라 **경로 전체 또는 코드로 대조**해야 안전하다.

## `--verify` 판정값

| 판정 | 뜻 | 조치 |
|---|---|---|
| `일치` | 확장 코드 = 마스터 코드 | 그대로 신뢰 |
| `불일치` | 둘이 다름 | **사람이 본다.** 자동 저장 금지 |
| `마스터로보정` | 확장 코드가 비었는데 경로로는 찾힘 | 마스터 코드로 채운다 — 패널 파싱 실패건 구제 |
| `마스터에없음` | 경로 표기가 다르거나 폐지된 카테고리 | 마스터 갱신 후 재확인 |

## 검증 기록 (2026-08-08)

- 수집: 5815건 / 최종차수 4999건 / 중복경로 0건
- 교차검증: `aside-category` 가 뽑았던 `50003340`(인테리어조명) · `50003337`(주방조명) **둘 다 일치**
- 역조회: `무선마우스 → 50002927` — `aside-category/SKILL.md` 에 적힌 예시값과 일치
- `--verify` 실물 검증: `python_work/data/category-fix/runs/25-2_ndm7_redo1/sellha.json` → `일치`

## 미연동

`bulsaja-category-fix` 의 `run_all.py` 에는 아직 물려 있지 않다. 붙이려면 저장 직전 단계에서
`CategoryMaster.code_of(카테고리경로)` 로 코드를 확정하고 `불일치` 는 자동저장에서 제외한다.
