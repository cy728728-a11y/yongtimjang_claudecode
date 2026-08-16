#!/usr/bin/env python3
"""상품명 규칙 산술 검증기 — 파이프라인 ⑤ product-name.

Claude가 만든 상품명(키워드 2개 조합 + term 분해)이 이룸님 규칙을 지켰는지
기계적으로 검증한다. 의미 판단(썸네일 대조 / 이 상품이 맞나)은 여기서 하지 않는다.

검증 규칙:
  R1. term 분해가 상품명을 정확히 분할하는가  ("".join(terms) == 상품명 공백제거)
  R2. 고유 **내용어** term 수 4~6 (목표 6 무조건) (4~5=경고 / 3 이하·7 이상=실패)
  R3. 중복 term 최대 1개, 각 2회까지           (3회 이상 / 중복 2종 이상 = 실패)
  R4. 사용 키워드 2~5개가 서로 다른가
      (1개 = `키워드확장` 증빙 있을 때 / 0개 = `무키워드사유` 있을 때만 허용)
  R5. **적합도** — 키워드가 상품명에 연속 문자열 그대로 있는가 (하나도 없으면 실패)
  R8. **대표옵션 마커** — 상품명이 `기본형` 으로 끝나고, 그게 1번만 나오는가
  R9. **배치** — 원본 단어와 키워드를 `a 1 b 2 c` 로 번갈아 놓았는가 (앞자리부터 채운다)
  R11. **유통 브랜드** — 남의 유통사 브랜드를 상품명에 넣었는가
       (원본에 있던 것=경고 / 새로 붙인 것=실패)

적합도가 왜 핵심인가 (2026-07-24 이룸님):
  네이버는 검색어가 상품명에 **그대로** 있을 때 적합도 점수를 높게 준다.
  term으로 쪼개 재배열하면 그 검색어로는 상위노출이 안 된다.
    "전동미용의자 이발의자"  → 두 검색어 모두 적합도 만점
    "전동 미용 이발 의자"    → 둘 다 적합도 하락 (연속으로 없음)
  **R3의 '중복 term 1종 2회 허용'은 바로 이걸 위한 장치다** — 두 키워드를 온전히 넣으면
  공유 term('의자')이 2번 나올 수밖에 없다. 뒤집어 말하면 **term을 2종 이상 공유하는
  키워드 쌍은 함께 쓸 수 없다**(유압자키2톤 + 전동유압자키 = '유압'·'자키' 2종 → 불가).
  --- 이하 2026-07-24 추가. 산술이 아니라 **절차** 검증이다 ---
  R6. 관련어 목록과 반증(B) 답변이 있는가       (없으면 "봤다"는 증거가 없다)
  R7. 관련어 중 채택보다 상품수가 낮은 게 있는데 사유가 비었는가 (있으면 실패)

R6·R7이 왜 산술 검증기에 들어왔나:
  이전 파일럿의 실패는 규칙 위반이 아니었다 — 규칙은 5건 전부 통과했다.
  실패는 **후보를 다 안 보고 스스로 잘라 찍은 것**이었다(후보 85개 중 36개만 봄).
  그래서 결과물이 아니라 절차를 검사한다. R7은 이룸님이 #8 서랍장에서 잡아낸
  "자릿수 2개 낮은 키워드를 놔두고 비싼 걸 골랐다"를 기계가 대신 잡는 규칙이다.

  ※ 한때 R8(채택 어근이 원본 상품명 어근과 안 겹치면 경고)을 검토했으나 폐기했다.
    키워드 발굴의 본질이 '원본에 없는 말을 찾는 것'이라 경고가 남발되고,
    실제로 잡아야 할 #9(베이비그라인더=다른 공구)는 '그라인더'가 겹쳐서 안 걸린다.
    그 건은 B(challenge.py)가 잡는다 — 되던지기 51개에 일자그라인더가 들어온다.

term 예산 (2026-07-30 이룸님 변경): **내용어 6 + 맨 끝에 `기본형`** = 실질 7단어.
  채우는 순서: ① 저상품수 직결어 → ② 적합한 대형 키워드 → ③ **원본 상품명 단어**.
  원본은 판매자가 단 것이라 관련이 보장되므로, 그래도 6이 안 되면 원본에서 term을 가져온다
  (예: 자키 상품의 '작키·받침대·수리'). 원본조차 부족하면 4~5로 내보낸다(경고).
  (이전 규칙은 '내용어 7 무조건'이었다 — 네이버 패널티 임계가 카테고리별 7 또는 9라
   7을 꽉 채우는 건 의도적 실험이었다. 2026-07-30에 마커 자리를 만들려고 6으로 내렸다.)

대표옵션 마커 `기본형` (2026-07-30 이룸님) — R8:
  네이버는 **'대표상품'(추가금 0원인 대표옵션)을 상품명으로 작성**하라고 요구한다.
  따라서 **썸네일 = 대표옵션 = 상품명**이 같은 옵션 하나를 지칭해야 한다.
  대표옵션명 끝에도 같은 `기본형` 이 붙어(→ bulsaja-option-cleanup 규칙 17)
  **같은 단어가 짝을 지목한다.** 이 방식의 요점은 스킬 간 데이터 계약이 필요 없다는 것 —
  이 스킬은 대표옵션이 무엇인지 몰라도 무조건 끝에 붙이면 된다.
  `기본형` 은 **term 수에 세지 않는다**(결정: 별도 부착). 단 `term분해` 에는 마지막 원소로
  포함돼야 한다 — R1(상품명 전체 분할 검사)을 그대로 유지하기 위해서다.

배치 규칙 `a 1 b 2 c` (2026-07-31 이룸님) — R9:
  원본 상품명 단어(a·b·c)와 채택 키워드(1·2)를 **번갈아** 놓는다. 키워드끼리 앞에 몰고
  원본 단어를 뒤에 붙이면 안 된다.
    원본  면삶는냄비 업소용 탕면기 우동 스테인레스 뜰채 깊은
    키워드 1=스파게티냄비 2=면삶는냄비
    ✗  스파게티냄비 면삶는냄비 업소용 뜰채 깊은     (키워드 2개가 앞에 몰림 = R9 실패)
    ✓  탕면기 스파게티냄비 우동 면삶는냄비 업소용   (a 1 b 2 c)
  - **a·b·c는 실물 직결어 우선 순서** — 실물을 정확히 지칭하는 단어가 a, 약한 수식어가 뒤로.
  - **자리가 모자라면 c → b → a 순으로 지운다.** 키워드는 절대 자르지 않는다
    (내용어 6 예산을 키워드가 다 먹으면 원본 단어는 a 하나만 들어간다:
     `탕면기 스파게티냄비 면삶는냄비` — 이때 키워드가 붙어 있는 건 정상이다).
  - 키워드가 3개 이상이면 계속 번갈아: `a 1 b 2 c 3`.
  - 검사 방법: 상품명을 어절로 쪼개 키워드 덩어리를 찾고, 그 사이 빈칸(gap)이
    **앞에서부터** 채워졌는지 본다. 빈 gap 뒤에 원본 단어가 남아 있으면 실패.

키워드 선택 우선순위 (2026-07-24 이룸님 재편):
  ① 실제 상품과 맞는가(썸네일 대조) → ② 상품수 낮은 직결어 먼저 → ③ term 7 무조건 채우기
  term이 모자라면 상품수 높은 대형 키워드라도 붙이고, 그래도 부족하면 원본 상품명 단어로 채운다
  (안 넣으면 그 검색 조합 노출이 0). 단 **관계없는 키워드는 절대 금지** — 적합성이 상한.

규칙 원본: keyword-pick/references/키워드&상품명작성에이전트.md §6-1~§6-4
보정 근거: keyword-pick/references/상품명-설계결정.md §1 (의미 먼저, 산술은 검증)

Usage:
  # 배치 (named_*.json 검증)
  python name_check.py --input named_001.json [--output checked_001.json] [--max-terms 5]
  # 단건 (빠른 확인)
  python name_check.py --name "가정용 무선 각얼음 빙수기 눈꽃 슬러시 기본형" \
                       --terms "가정용,무선,각얼음,빙수기,눈꽃,슬러시,기본형" \
                       --keywords "무선빙수기,각얼음빙수기"
"""
import argparse
import json
import re
import sys
from collections import Counter

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 대표옵션 마커 (2026-07-30 이룸님) — 상품명 맨 끝에 고정 부착. **term 수에 세지 않는다.**
#   대표옵션명 끝에도 같은 단어가 붙어(bulsaja-option-cleanup 규칙 17) 짝을 지목한다.
BASE_SUFFIX = "기본형"
# term 예산 (2026-07-30 이룸님 변경): **내용어 6** + 마커 = 실질 7단어.
#   키워드·카테고리 특징어로 부족하면 **원본 상품명 단어로 6까지 채운다**
#   (원본은 판매자가 단 것이라 그 상품과 관련이 보장됨 — 관계없는 걸 붙이는 위험이 없다).
#   3 이하 = 너무 짧음(실패) / 4~5 = 허용하되 "6까지 채워라" 경고 / 6 = 정상 / 7+ = 실패
#   ※ 아래 셋은 전부 **`기본형` 을 뺀 내용어** 기준이다.
DEFAULT_MIN_TERMS = 4      # 4~5 = 허용(경고) / 6 = 정상 / 3 이하 = 실패
DEFAULT_MAX_TERMS = 6
TARGET_MIN_TERMS = 6       # 목표 = 6 무조건. 미달(4~5)이면 경고(탈락은 아님)
# 사용 키워드 개수: 2개 기본, term 6~7을 못 채우면 5개까지 붙인다
MIN_KEYWORDS = 2
MAX_KEYWORDS = 5
# 중복 허용: term 1종, 2회까지
MAX_DUP_TERMS = 1
MAX_DUP_COUNT = 2

# 유통·리테일 브랜드 (2026-08-14 이룸님 표본검수 발) — R11.
#   발단: `전동 계단 리프트`(중국산)에 채택 키워드 `코스트코접이식카트` 가 붙었다.
#   셀러라이프 O열 브랜드키워드 컷도, 블랙리스트 `제외브랜드`(33개, 소비재 위주)도
#   유통사명은 안 걸러서 뷰에 남아 있었다. 남의 유통사·가구 브랜드를 상품명에 넣는 건
#   상표 리스크이고, 구매대행 상품은 그 브랜드 제품이 아니다.
#   **원본 상품명에 이미 있으면 경고**(판매자가 단 것 — 판단은 사람 몫),
#   **원본에 없는데 붙었으면 위반**(워커가 새로 끌어온 것).
RETAIL_BRANDS = (
    "코스트코", "이케아", "다이소", "무인양품", "이마트", "트레이더스", "홈플러스",
    "롯데마트", "쿠팡", "마켓컬리", "올리브영", "무신사", "오늘의집", "한샘", "리바트",
    "스타벅스", "알리익스프레스", "테무", "쉬인", "아마존",
)


def nows(s):
    """공백·줄바꿈 전부 제거 (상품명 ↔ term 결합 비교용)."""
    return re.sub(r"\s+", "", str(s)) if s is not None else ""


def is_exact_in_name(keyword, name):
    """적합도 — 키워드가 상품명에 **연속된 문자열 그대로** 있는가 (2026-07-24 이룸님).

    네이버 적합도 점수는 검색어가 상품명에 그대로 있을 때 높다.
    term으로 쪼개 재배열하면 그 검색어로는 상위노출이 안 된다.

        상품명 "전동미용의자 이발의자"
          '전동미용의자' 검색 → 그대로 있음 → 적합도 만점
          '이발의자'     검색 → 그대로 있음 → 적합도 만점
        상품명 "전동 미용 이발 의자"   (쪼개서 재배열 — 잘못된 조합)
          '전동미용의자' → 연속으로 없음 → 적합도 하락, '전동미용의자' 상품에 밀림
          '이발의자'     → 연속으로 없음 → 마찬가지

    띄어쓰기는 무시하고 순서만 본다(공백 제거 후 부분문자열 검사).
    """
    k, n = nows(keyword), nows(name)
    return bool(k) and k in n


def keyword_blocks(name, keywords):
    """상품명을 어절로 쪼개고, 그 안에서 키워드 덩어리의 위치를 찾는다 (R9용).

    반환: (words, blocks)
      words  = 마커(`기본형`)를 뺀 어절 리스트
      blocks = [(start, end)] 반열림 구간. 키워드 하나가 어절 1개일 수도, 여러 개일 수도 있다
               (`각얼음 빙수기` 두 어절이 키워드 `각얼음빙수기` 하나를 이룬다).

    같은 키워드를 두 번 세지 않으려고 매칭된 키워드는 소진한다. 한 자리에서 여러 키워드가
    맞으면 **더 긴 쪽**을 택한다(`냄비` 보다 `면삶는냄비`).
    """
    words = [w for w in str(name or "").split() if w]
    if words and words[-1] == BASE_SUFFIX:
        words = words[:-1]
    targets = [nows(k) for k in keywords or [] if nows(k)]

    blocks, used, i = [], set(), 0
    while i < len(words):
        best = None  # (end, target_index)
        for ti, t in enumerate(targets):
            if ti in used:
                continue
            acc = ""
            for j in range(i, len(words)):
                acc += nows(words[j])
                if len(acc) > len(t):
                    break
                if acc == t:
                    if best is None or j + 1 > best[0]:
                        best = (j + 1, ti)
                    break
        if best:
            blocks.append((i, best[0]))
            used.add(best[1])
            i = best[0]
        else:
            i += 1
    return words, blocks


def _to_int(v):
    """'21,202' · 21202 · None 을 정수로. 실패하면 None."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip().replace(",", "")
    try:
        return int(float(s))
    except ValueError:
        return None


def collect_keywords(product):
    """키워드1/키워드2/키워드3 또는 '키워드' 리스트에서 사용 키워드를 순서대로 뽑는다."""
    kws = product.get("키워드")
    if isinstance(kws, list):
        vals = [str(k).strip() for k in kws]
    else:
        vals = [str(product.get(f"키워드{i}") or "").strip() for i in (1, 2, 3, 4, 5)]
    return [v for v in vals if v]


def evidence_text(product):
    """근거 뭉치 — 이 상품에 대해 확인된 문자열 전부를 공백 없이 합친다.

    ⚠️ **이걸로 "근거 없는 term" 검사를 만들지 마라 (2026-08-14 실측으로 폐기).**
    한 번 만들었다가(R10) 2-1 표본 35건 중 23건이 오탐이라 그날 되돌렸다. 이유는
    구조적이다 — 증거의 절반이 **중국어 원문**이고 상품명은 한국어라, 문자열 대조로는
    `고속`↔`高速` · `북유럽`↔`北欧` · `3단`↔`三层` 이 전부 "근거 없음"으로 잡힌다.
    대역 사전 없이는 못 넘는다. 발단이 된 사례('발광글자')조차 원문 `广告发光字` 에
    근거가 있었다 — **규칙이 잡으려던 그 건 자체가 오탐이었다.**
    지어낸 속성은 여전히 기계가 못 잡는다. 표본검수(사람)가 그 방어선이다.

    재료: 원본상품명 · 실물판정 · 중국어 원문명 · 옵션명(요약) · 옵션구성(전량 원문 포함) ·
    채택 키워드. 앞의 넷은 `prep` 이 배치에 실어 보낸 가공 전 증거이고, 워커가 이름을
    지을 때 실제로 본 것과 같다. `run_names` 가 배치에서 `증거` 로 주입한다(없으면 이
    함수가 product 안에 있는 것만으로 만든다 — 단건 모드·구버전 named 호환).
    """
    parts = [product.get("원본상품명"), product.get("실물판정"),
             product.get("원문명"), product.get("증거")]
    opts = product.get("옵션명") or []
    if isinstance(opts, (list, tuple)):
        parts += [str(o) for o in opts]
    spec = product.get("옵션구성")
    if isinstance(spec, dict):
        for o in (spec.get("옵션전량") or []):
            if isinstance(o, dict):
                parts += [o.get("원문"), o.get("text"), o.get("옵션명")]
    parts += collect_keywords(product)
    return nows(" ".join(str(p) for p in parts if p))


# 원본유지 경로에서 살려 두는 규칙 — 이름 품질이 아니라 **구조**를 보는 둘뿐이다.
KEEP_KEPT_RULES = ("R1", "R8")


def _apply_keep_gate(violations, warnings, keep_note):
    """원본유지(`원본유지사유`) 경로면 R1·R8 외 위반을 경고로 내린다 (2026-08-07 이룸님).

    **원본 상품명이 이미 실물을 맞게 지칭하는 건**은 새로 짓지 않고 그대로 두되 마커만
    붙인다. 그 결정 자체가 "이 이름의 검색 품질은 따지지 않는다"는 뜻이라, 원본이
    R2(term수)·R4(키워드수)·R9(배치) 따위를 어긴다고 실패시키면 경로가 성립하지 않는다.
    **R1(term분해 정합)·R8(마커)만 남긴다** — 마커를 붙이는 게 이 경로의 유일한 변경이고,
    그게 틀리면 썸네일=대표옵션=상품명 짝이 깨진다.

    발단 = 라인테이핑기(3-2). 재교정으로 카테고리를 바꾸고 새 뷰를 다시 훑었는데 근접어
    (`주차선도색기계`)가 **있었지만 기계 메커니즘이 달라**(도색 vs 테이프 부착) 쓰면
    오지칭이었다. 워커 판단은 옳았고 원본 이름도 이미 맞았는데 갈 곳이 사람 큐뿐이라
    쌓였다 — 이룸님: "원본 이름이 이미 맞는 경우는 그대로 두는 걸로 자동화. 일일이 다
    체크할 수가 없어서."
    """
    if not keep_note:
        return violations
    kept, waived = [], []
    for v in violations:
        (kept if str(v).startswith(KEEP_KEPT_RULES) else waived).append(v)
    warnings.append(
        f"원본유지 — 원본 상품명이 이미 실물을 지칭해 마커만 붙였다. "
        f"이름 품질 검사 면제"
        + (f"({len(waived)}건: {'; '.join(x[:40] for x in waived[:3])})" if waived else "")
        + f": {keep_note[:80]}")
    return kept


def check_one(product, max_terms=DEFAULT_MAX_TERMS, min_terms=DEFAULT_MIN_TERMS,
              strict=True):
    """상품 1건 검증. product를 변형하지 않고 검증 결과 dict를 반환한다.

    입력 키: 새상품명 / term분해(list, 등장순서대로 중복 포함) / 키워드1 / 키워드2
             관련어(list of {키워드,상품수,검색량,사유}) / 반증(str)
    strict=False 면 절차 검증(R6·R7)을 건너뛴다 — 단건 빠른 확인용.
    반환:   {"통과": bool, "term수": int, "중복어": str, "위반": [...], "경고": [...]}
    """
    violations = []
    warnings = []

    name = str(product.get("새상품명") or "").strip()
    terms = product.get("term분해") or []
    if isinstance(terms, str):  # "가정용/무선/빙수기" 형태도 허용
        terms = [t.strip() for t in re.split(r"[/,·]", terms) if t.strip()]
    terms = [str(t).strip() for t in terms if str(t).strip()]

    kws = collect_keywords(product)

    if not name:
        violations.append("새상품명 없음")
    if not terms:
        violations.append("term분해 없음")

    # R1. term 분해가 상품명을 정확히 분할하는가
    if name and terms:
        joined = "".join(nows(t) for t in terms)
        if joined != nows(name):
            violations.append(
                f"R1 term분해 불일치: 결합='{joined}' vs 상품명='{nows(name)}'"
            )

    # R2. 고유 **내용어** term 수 — 6이 정상 (4~5 경고 통과, 7+ 실패)
    #     마커(`기본형`)는 모든 상품명에 붙는 고정 접미어라 변별력이 0이다 —
    #     term 예산에 세면 내용어 하나를 빼앗는 셈이라 세지 않는다(2026-07-30 이룸님).
    content_terms = [t for t in terms if t != BASE_SUFFIX]
    unique_terms = list(dict.fromkeys(content_terms))  # 순서 보존 중복 제거
    term_count = len(unique_terms)
    if term_count > max_terms:
        violations.append(f"R2 term수 초과: {term_count} > {max_terms} (패널티 구간)")
    elif term_count < min_terms:
        violations.append(
            f"R2 term수 부족: {term_count} < {min_terms} "
            f"(키워드를 {MAX_KEYWORDS}개까지 붙여 채울 것)")
    elif term_count < TARGET_MIN_TERMS:
        warnings.append(
            f"term {term_count}개 — 목표는 {TARGET_MIN_TERMS}(무조건). "
            f"키워드로 부족하면 원본 상품명 단어로 {TARGET_MIN_TERMS}까지 채울 것")

    # R3. 중복 term (마커 제외 — 마커는 R8이 따로 본다)
    counter = Counter(content_terms)
    dups = {t: c for t, c in counter.items() if c >= 2}
    if len(dups) > MAX_DUP_TERMS:
        violations.append(f"R3 중복 term {len(dups)}종 (최대 {MAX_DUP_TERMS}종): {list(dups)}")
    over = [f"{t}×{c}" for t, c in dups.items() if c > MAX_DUP_COUNT]
    if over:
        violations.append(f"R3 중복 {MAX_DUP_COUNT}회 초과: {', '.join(over)}")

    # R4. 키워드 2~5개, 서로 달라야
    #     ★ 1개 예외 (2026-08-05 이룸님): 뷰에 직결어가 1개뿐이면 보류하지 않고
    #       **원본 상품명 단어로 채워 내보낸다.** 단 `키워드확장` 소진 증빙이 있을 때만 —
    #       증빙 없이 1개면 종전대로 실패다(게으른 1개짜리 제출은 계속 막는다.
    #       재팬아웃 emphasis 가 R4 실패를 104→9로 줄인 그 장치를 잃지 않기 위해서다).
    #       0개는 직결어 자체가 없다는 뜻이라 카테고리 문제다 → 예외 없음.
    #     ★ 0개 예외 (2026-08-06 이룸님): 뷰에 직결어가 **하나도** 없는 건(통다운에 그
    #       카테고리 키워드가 없거나 뷰 파일이 빔)도 보류로 두지 말고 **원본 상품명·원문·
    #       옵션명 단어만으로** 짓는다. 카테고리 재교정을 이미 소진한 뒤의 마지막 경로다.
    #       전용 필드 `무키워드사유` 가 있을 때만 열린다(1개 예외의 `키워드확장`과 별개 —
    #       실수로 섞여 열리면 안 되는, 훨씬 넓은 면제라서 게이트를 따로 둔다).
    #       ⚠ 이 경로의 상품명은 **검색 적합도 기대값이 낮다.** 목적은 상위노출이 아니라
    #       "원본 오기재를 실물 지칭으로 바로잡는 것"이다(원본명 오기재가 실측 다수).
    #     ★★ 원본유지 (2026-08-07 이룸님): 무키워드 라운드에서 **원본 상품명이 이미 실물을
    #        맞게 지칭하고 있으면** 새로 짓지 않고 그대로 두되 마커만 붙인다.
    #        발단 = 라인테이핑기(3-2) — 재교정으로 카테고리를 바꾼 뒤 새 뷰를 다시 훑었는데
    #        근접어(`주차선도색기계`)가 **있었지만 기계 메커니즘이 달라**(도색 vs 테이프)
    #        쓰면 오지칭이었다. 워커 판단은 옳았고 원본 이름도 이미 맞았는데, 갈 곳이
    #        사람 큐뿐이라 쌓였다("일일이 다 체크할 수가 없어서").
    #        **이름 품질 검사(R2·R3·R4·R5·R6·R7·R9)를 전부 면제한다** — 원본을 그대로 쓰기로
    #        한 결정 자체가 "이 이름의 검색 품질은 따지지 않는다"는 뜻이라, 원본이 규칙을
    #        어긴다고 실패시키면 경로가 성립하지 않는다.
    #        **R1(term분해 정합)·R8(마커)은 그대로 건다** — 마커를 붙이는 게 이 경로의
    #        유일한 변경이고, 그게 틀리면 썸네일=대표옵션=상품명 짝이 깨진다.
    expand_note = str(product.get("키워드확장") or "").strip()
    nokw_note = str(product.get("무키워드사유") or "").strip()
    no_kw = (len(kws) == 0 and bool(nokw_note))
    if no_kw:
        warnings.append(
            f"키워드 0개(무키워드 경로) — 적합도 검사(R5)·절차(R6/R7) 면제. "
            f"상위노출 기대값 낮음: {nokw_note[:80]}")
    elif len(kws) < MIN_KEYWORDS:
        if len(kws) == 1 and expand_note:
            warnings.append(
                f"키워드 1개 — 확장 소진 증빙으로 통과. 나머지 자리는 원본·원문·옵션명 "
                f"단어로 채운다: {expand_note[:80]}")
        else:
            violations.append(
                f"R4 사용 키워드가 {MIN_KEYWORDS}개 미만 ({len(kws)}개)"
                + (" — 1개로 내보내려면 `키워드확장`에 계단 확장 상한·상위뷰 확인 결과를 "
                   "남길 것" if len(kws) == 1 else ""))
    elif len(kws) > MAX_KEYWORDS:
        violations.append(f"R4 사용 키워드가 {MAX_KEYWORDS}개 초과 ({len(kws)}개)")
    normed = [nows(k) for k in kws]
    if len(set(normed)) != len(normed):
        violations.append(f"R4 중복된 키워드: {kws}")

    # R5. 적합도 — 키워드가 상품명에 '연속된 문자열 그대로' 있는가 (2026-07-24 이룸님)
    #     쪼개서 재배열하면 그 검색어로는 상위노출이 안 된다. 최소 1개는 반드시 만점이어야 한다.
    exact = [kw for kw in kws if is_exact_in_name(kw, name)]
    partial = [kw for kw in kws if kw not in exact]
    if no_kw:
        pass                                    # 검사할 키워드가 없다 — 적합도 개념이 성립 안 함
    elif name and not exact:
        violations.append(
            "R5 적합도 0 — 어느 키워드도 상품명에 그대로 없다. "
            "키워드를 쪼개 재배열하지 말고 원문 그대로 넣을 것")
    elif partial:
        warnings.append(
            f"적합도 만점 {len(exact)}개 / 부분반영 {len(partial)}개({', '.join(partial)}) "
            f"— 부분반영 키워드로는 상위노출이 어렵다")

    # R9. 배치 — 원본 단어와 키워드를 `a 1 b 2 c` 로 번갈아 놓았는가 (2026-07-31 이룸님).
    #     키워드를 앞에 몰고 원본 단어를 뒤에 붙이면, 실물을 지칭하는 원본 직결어가
    #     상품명 꼬리로 밀려 노출 조합에서 약해진다. 그래서 **앞자리부터** 번갈아 채운다.
    #     자리가 모자라 c·b가 빠져 키워드끼리 붙는 건 정상이다(키워드는 자르지 않는다).
    if name and exact:
        words, blocks = keyword_blocks(name, exact)
        if blocks:
            gaps, prev = [], 0
            for s, e in blocks:
                gaps.append(words[prev:s])
                prev = e
            gaps.append(words[prev:])
            # 앞에서부터 채운다 = 빈 gap 뒤에 원본 단어가 남아 있으면 안 된다
            first_empty = next((i for i, g in enumerate(gaps) if not g), None)
            if first_empty is not None:
                misplaced = [w for g in gaps[first_empty + 1:] for w in g]
                if misplaced:
                    violations.append(
                        f"R9 배치 어긋남 — 원본 단어 {', '.join(misplaced)}를 키워드 사이에 "
                        f"끼워야 한다(a 1 b 2 c). 키워드를 앞에 몰지 말 것")

    # R11. 유통 브랜드 — 남의 유통사·가구 브랜드를 상품명에 넣었는가 (2026-08-14 이룸님)
    #      발단: 중국산 계단카트에 채택 키워드 `코스트코접이식카트`. 구매대행 상품은 그
    #      브랜드 제품이 아니라 상표 리스크다. 원본에 이미 있으면(판매자가 단 것) 경고,
    #      원본에 없는데 워커가 새로 끌어왔으면 위반.
    if name:
        origin = nows(product.get("원본상품명"))
        nname = nows(name)
        for b in RETAIL_BRANDS:
            if b not in nname:
                continue
            if b in origin:
                warnings.append(
                    f"R11 상품명에 유통 브랜드 '{b}' — 원본 상품명에 이미 있던 말이다. "
                    f"이 상품이 실제 그 브랜드 제품이 아니면 빼는 게 안전하다")
            else:
                violations.append(
                    f"R11 상품명에 유통 브랜드 '{b}' — 원본에 없는데 새로 붙였다. "
                    f"구매대행 상품은 그 브랜드 제품이 아니다(상표 리스크). 다른 키워드로 교체")

    # R8. 대표옵션 마커 — 상품명은 `기본형` 으로 끝나고, 그게 딱 1번 나와야 한다.
    #     네이버는 '대표상품'(추가금 0원 옵션)을 상품명으로 쓰라고 요구한다. 대표옵션명 끝에도
    #     같은 단어가 붙어(bulsaja-option-cleanup 규칙 17) **같은 단어가 짝을 지목한다.**
    #     2회 이상 나오면 어느 쪽이 마커인지 알 수 없어 짝이 흐려진다.
    if name:
        if not name.strip().endswith(BASE_SUFFIX):
            violations.append(
                f"R8 상품명이 '{BASE_SUFFIX}'으로 끝나지 않는다 — 대표옵션과 짝이 안 맞는다")
        n_mark = nows(name).count(BASE_SUFFIX)
        if n_mark > 1:
            violations.append(f"R8 '{BASE_SUFFIX}'이 {n_mark}번 나온다(마커는 1번)")
        if terms and terms[-1] != BASE_SUFFIX:
            violations.append(
                f"R8 term분해의 마지막이 '{BASE_SUFFIX}'이 아니다(현재 '{terms[-1]}')")

    # R12. 재작업 게이트 — 재작업사유를 처리했다는 흔적이 있는가 (2026-08-16)
    #      재작업건은 "왜 틀렸는지"가 사유로 실려 온다. 그런데 워커가 사유를 무시하고
    #      문제된 낱말을 그대로 두는 일이 반복됐다(2026-08-15 25-2 3회차 표본검수
    #      의심 3건이 **전부** 이 패턴: '레드' 유지 · '임팩' 유지 · 품목 오지칭 미교정).
    #      사유는 자연어라 "지목된 낱말"을 기계로 뽑는 건 불안정하다 — 대신 **게이트를
    #      밟았다는 기록(`재작업반영`)이 있는지**를 본다. 이건 100% 판정 가능하다.
    #      경고다(실패 아님): 재팬아웃 비용보다 표본검수 우선순위를 올리는 게 싸다.
    redo_why = str(product.get("재작업사유") or "").strip()
    if redo_why and not str(product.get("재작업반영") or "").strip():
        warnings.append(
            f"R12 재작업사유가 있는데 `재작업반영` 이 비었다 — 사유를 처리했다는 근거가 "
            f"없다. **표본검수 우선 대상.** 사유: {redo_why[:80]}")
        # 사유에 따옴표로 지목된 낱말이 새 상품명에 그대로 남아 있으면 더 강하게 찍는다.
        quoted = re.findall(r"['‘’\"“”]([^'‘’\"“”]{1,12})"
                            r"['‘’\"“”]", redo_why)
        left = [q for q in quoted if q and nows(q) in nows(name)]
        if left:
            warnings.append(
                f"R12 사유가 지목한 낱말 {left} 이 새 상품명에 그대로 남았다 — "
                f"빼거나 원문·옵션 증거를 `재작업반영` 에 대라")

    # R6. 절차 — 관련어 목록과 반증 답변이 남았는가
    related = product.get("관련어") or []
    keep_note = str(product.get("원본유지사유") or "").strip()
    if not strict:
        dup_label = ", ".join(f"{t}({c}회)" for t, c in dups.items()) if dups else "없음"
        violations = _apply_keep_gate(violations, warnings, keep_note)
        return {"통과": not violations, "term수": term_count, "중복어": dup_label,
                "키워드수": len(kws), "관련어수": len(related),
                "위반": violations, "경고": warnings}
    # 무키워드 경로는 R6 면제 — 고른 키워드가 없으니 "무엇을 보고 골랐나"도, 채택을
    # 되던지는 반증(challenge.py)도 성립하지 않는다. 대신 `무키워드사유`가 증거다.
    if not no_kw:
        if not related:
            violations.append("R6 관련어 목록 없음 — 무엇을 보고 골랐는지 증거가 없다")
        if not str(product.get("반증") or "").strip():
            violations.append("R6 반증(B) 답변 없음 — challenge.py 목록에 답해야 한다")

    # R7. 관련어 중 채택보다 상품수가 낮은데 사유가 비었는가
    #     "더 싼 걸 놔두고 비싼 걸 골랐으면 이유를 대라". #8 서랍장 케이스를 잡는 규칙
    if related and kws:
        by_kw = {str(r.get("키워드", "")).strip(): r for r in related}
        adopted_pcs = [_to_int(by_kw[k].get("상품수")) for k in kws if k in by_kw]
        adopted_pcs = [v for v in adopted_pcs if v is not None]
        if adopted_pcs:
            floor = min(adopted_pcs)
            unexplained = []
            for r in related:
                kw = str(r.get("키워드", "")).strip()
                if not kw or kw in kws:
                    continue
                pc = _to_int(r.get("상품수"))
                if pc is not None and pc < floor and not str(r.get("사유") or "").strip():
                    unexplained.append(f"{kw}({pc:,})")
            if unexplained:
                violations.append(
                    f"R7 채택({floor:,})보다 상품수가 낮은데 사유가 없는 관련어 "
                    f"{len(unexplained)}건: {', '.join(unexplained[:6])}"
                    + (" …" if len(unexplained) > 6 else ""))

    dup_label = ", ".join(f"{t}({c}회)" for t, c in dups.items()) if dups else "없음"
    violations = _apply_keep_gate(violations, warnings, keep_note)

    return {
        "통과": not violations,
        "term수": term_count,
        "중복어": dup_label,
        "키워드수": len(kws),
        "관련어수": len(related),
        "위반": violations,
        "경고": warnings,
    }


def main():
    ap = argparse.ArgumentParser(description="상품명 규칙 산술 검증 (파이프라인 ⑤)")
    ap.add_argument("--input", help="named_*.json (products 배열 포함)")
    ap.add_argument("--output", help="검증 결과를 병합해 저장할 경로 (미지정시 stdout 요약만)")
    ap.add_argument("--batch", help="같은 번호의 batch_*.json — R10 근거 검사에 원문명·"
                                    "옵션명·옵션구성을 실어 준다(없으면 원본상품명·"
                                    "실물판정·키워드만으로 판정해 오탐이 는다)")
    ap.add_argument("--max-terms", type=int, default=DEFAULT_MAX_TERMS,
                    help=f"고유 내용어 term 상한 ('{BASE_SUFFIX}' 제외, "
                         f"default: {DEFAULT_MAX_TERMS})")
    ap.add_argument("--min-terms", type=int, default=DEFAULT_MIN_TERMS,
                    help=f"고유 내용어 term 하한 (default: {DEFAULT_MIN_TERMS})")
    # 단건 모드
    ap.add_argument("--name", help=f"단건 검증: 상품명 (맨 끝이 '{BASE_SUFFIX}'이어야 한다)")
    ap.add_argument("--terms", help=f"단건 검증: term 분해 (쉼표 구분, 중복 포함, "
                                   f"마지막은 '{BASE_SUFFIX}')")
    ap.add_argument("--keywords", help="단건 검증: 사용 키워드 2~5개 (쉼표 구분)")
    ap.add_argument("--expand-note", default="",
                    help="단건 검증: 키워드가 1개일 때의 확장 소진 증빙(`키워드확장`). "
                         "계단 확장 상한·상위뷰 확인 결과를 적으면 R4 1개 예외가 열린다")
    ap.add_argument("--nokw-note", default="",
                    help="단건 검증: 직결어가 0개일 때의 사유(`무키워드사유`). "
                         "적으면 R4 0개 예외 + R5·R6 면제가 열린다(적합도 기대값 낮음)")
    args = ap.parse_args()

    # --- 단건 모드 ---
    if args.name:
        product = {
            "새상품명": args.name,
            "term분해": [t.strip() for t in (args.terms or "").split(",") if t.strip()],
            "키워드": [k.strip() for k in (args.keywords or "").split(",") if k.strip()],
            "키워드확장": args.expand_note,
            "무키워드사유": args.nokw_note,
        }
        r = check_one(product, args.max_terms, args.min_terms, strict=False)
        print(f"상품명: {args.name}")
        print(f"  term수: {r['term수']} / 키워드 {r['키워드수']}개 / 중복어: {r['중복어']}")
        print(f"  판정: {'통과' if r['통과'] else '실패'}")
        for v in r["위반"]:
            print(f"    - {v}")
        for w in r["경고"]:
            print(f"    ! {w}")
        sys.exit(0 if r["통과"] else 2)

    if not args.input:
        ap.error("--input 또는 --name 중 하나는 필요합니다.")

    # --- 배치 모드 ---
    try:
        with open(args.input, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: 입력 읽기 실패({args.input}): {e}", file=sys.stderr)
        sys.exit(1)

    products = data.get("products", data if isinstance(data, list) else [])
    passed, failed, held, warned = 0, 0, 0, 0

    # R10 근거 보강 — 배치의 가공 전 증거(원문명·옵션명·옵션구성)를 named 레코드에 얹는다.
    # named 는 워커 산출이라 이 셋이 없다. 없으면 R10 이 원본상품명·실물판정·키워드만
    # 보게 되어 정당한 말까지 "근거 없음"으로 잡는다(경고라 막지는 않지만 소음이 는다).
    if args.batch:
        try:
            with open(args.batch, encoding="utf-8") as f:
                bp = {x["productId"]: x for x in json.load(f).get("products", [])}
            for p in products:
                b = bp.get(p.get("productId"))
                if not b:
                    continue
                # `재작업사유` 도 배치에만 있다 — R12 가 이걸 봐야 한다(2026-08-16).
                for k in ("원문명", "옵션명", "옵션구성", "재작업사유"):
                    p.setdefault(k, b.get(k))
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as e:
            # 근거 보강 실패가 검증을 죽이면 안 된다 — R10 은 경고일 뿐이다.
            print(f"  [경고] 배치 근거 읽기 실패 — R10 정확도만 낮아진다: "
                  f"{str(e)[:100]}", file=sys.stderr)

    for p in products:
        # 보류 건(실물불명·카테고리의심 등)은 검증 대상이 아니다 — 상태만 유지.
        # ※ 키워드 2개 미달은 더 이상 보류 사유가 아니다(2026-08-05) — 1개 + 원본 단어로
        #   생성해 R4 예외로 통과시킨다. 여기 걸리는 건 직결어 0개거나 재료 자체가 없는 건뿐.
        if p.get("상태", "").startswith("보류") or not p.get("새상품명"):
            p.setdefault("상태", "보류")
            p["검증"] = {"통과": None, "위반": ["보류 건 — 검증 생략"]}
            held += 1
            continue
        r = check_one(p, args.max_terms, args.min_terms)
        p["검증"] = r
        p["term수"] = r["term수"]
        p["중복어"] = r["중복어"]
        if r["통과"]:
            p["상태"] = "생성완료"
            passed += 1
            if r["경고"]:
                warned += 1
        else:
            p["상태"] = "검증실패"
            failed += 1

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"###CHECK### 통과 {passed}(그중 경고 {warned}) / 실패 {failed} / "
          f"보류 {held} (총 {len(products)}건)")
    if failed:
        print("--- 실패 상세 ---")
        for p in products:
            v = (p.get("검증") or {}).get("위반") or []
            if p.get("상태") == "검증실패":
                print(f"  [{p.get('productId')}] {p.get('새상품명')}")
                for x in v:
                    print(f"    - {x}")
    if args.output:
        print(f"-> {args.output}")


if __name__ == "__main__":
    main()
