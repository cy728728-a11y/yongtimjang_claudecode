#!/usr/bin/env python3
"""상품명 규칙 산술 검증기 — 파이프라인 ⑤ product-name.

Claude가 만든 상품명(키워드 2개 조합 + term 분해)이 이룸님 규칙을 지켰는지
기계적으로 검증한다. 의미 판단(썸네일 대조 / 이 상품이 맞나)은 여기서 하지 않는다.

검증 규칙:
  R1. term 분해가 상품명을 정확히 분할하는가  ("".join(terms) == 상품명 공백제거)
  R2. 고유 term 수 4~7 (목표 7 무조건)          (4~6=경고 / 3 이하·8 이상=실패)
  R3. 중복 term 최대 1개, 각 2회까지           (3회 이상 / 중복 2종 이상 = 실패)
  R4. 사용 키워드 2~5개가 서로 다른가
  R5. **적합도** — 키워드가 상품명에 연속 문자열 그대로 있는가 (하나도 없으면 실패)

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

term 예산 (2026-07-24 이룸님 변경): 옵션명 몫을 빼고 상품명만으로 7을 무조건 채운다.
  네이버 패널티 임계가 카테고리별 7 또는 9 — 7은 카테고리에 따라 패널티 시작점이라
  꽉 채우는 건 의도적 실험이다(순위 반응을 검수에서 관찰).
  채우는 순서: ① 저상품수 직결어 → ② 적합한 대형 키워드 → ③ **원본 상품명 단어**.
  원본은 판매자가 단 것이라 관련이 보장되므로, 그래도 7이 안 되면 원본에서 term을 가져온다
  (예: 자키 상품의 '작키·받침대·수리'). 원본조차 부족하면 4~6으로 내보낸다(경고).

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
  python name_check.py --name "가정용 무선 각얼음 빙수기" \
                       --terms "가정용,무선,각얼음,빙수기" \
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

# term 예산 (2026-07-24 이룸님 변경): 옵션명 몫을 빼고 상품명만으로 7을 무조건 채운다.
#   네이버 패널티 임계는 카테고리별 7 또는 9 — 7은 카테고리에 따라 패널티 시작점이므로
#   상한을 7로 꽉 채우는 건 의도적 실험이다(순위 반응을 검수에서 관찰).
#   목표는 7 하나. 키워드·카테고리 특징어로 부족하면 **원본 상품명 단어로 7까지 채운다**
#   (원본은 판매자가 단 것이라 그 상품과 관련이 보장됨 — 관계없는 걸 붙이는 위험이 없다).
#   3 이하 = 너무 짧음(실패) / 4~6 = 허용하되 "7까지 채워라" 경고 / 7 = 정상 / 8+ = 실패
DEFAULT_MIN_TERMS = 4      # 4~6 = 허용(경고) / 7 = 정상 / 3 이하 = 실패
DEFAULT_MAX_TERMS = 7
TARGET_MIN_TERMS = 7       # 목표 = 7 무조건. 미달(4~6)이면 경고(탈락은 아님)
# 사용 키워드 개수: 2개 기본, term 6~7을 못 채우면 5개까지 붙인다
MIN_KEYWORDS = 2
MAX_KEYWORDS = 5
# 중복 허용: term 1종, 2회까지
MAX_DUP_TERMS = 1
MAX_DUP_COUNT = 2


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

    # R2. 고유 term 수 — 6~7만 정상 (4~5 경고 통과, 8+ 실패)
    unique_terms = list(dict.fromkeys(terms))  # 순서 보존 중복 제거
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

    # R3. 중복 term
    counter = Counter(terms)
    dups = {t: c for t, c in counter.items() if c >= 2}
    if len(dups) > MAX_DUP_TERMS:
        violations.append(f"R3 중복 term {len(dups)}종 (최대 {MAX_DUP_TERMS}종): {list(dups)}")
    over = [f"{t}×{c}" for t, c in dups.items() if c > MAX_DUP_COUNT]
    if over:
        violations.append(f"R3 중복 {MAX_DUP_COUNT}회 초과: {', '.join(over)}")

    # R4. 키워드 2~3개, 서로 달라야
    if len(kws) < MIN_KEYWORDS:
        violations.append(f"R4 사용 키워드가 {MIN_KEYWORDS}개 미만 ({len(kws)}개)")
    elif len(kws) > MAX_KEYWORDS:
        violations.append(f"R4 사용 키워드가 {MAX_KEYWORDS}개 초과 ({len(kws)}개)")
    normed = [nows(k) for k in kws]
    if len(set(normed)) != len(normed):
        violations.append(f"R4 중복된 키워드: {kws}")

    # R5. 적합도 — 키워드가 상품명에 '연속된 문자열 그대로' 있는가 (2026-07-24 이룸님)
    #     쪼개서 재배열하면 그 검색어로는 상위노출이 안 된다. 최소 1개는 반드시 만점이어야 한다.
    exact = [kw for kw in kws if is_exact_in_name(kw, name)]
    partial = [kw for kw in kws if kw not in exact]
    if name and not exact:
        violations.append(
            "R5 적합도 0 — 어느 키워드도 상품명에 그대로 없다. "
            "키워드를 쪼개 재배열하지 말고 원문 그대로 넣을 것")
    elif partial:
        warnings.append(
            f"적합도 만점 {len(exact)}개 / 부분반영 {len(partial)}개({', '.join(partial)}) "
            f"— 부분반영 키워드로는 상위노출이 어렵다")

    # R6. 절차 — 관련어 목록과 반증 답변이 남았는가
    related = product.get("관련어") or []
    if not strict:
        dup_label = ", ".join(f"{t}({c}회)" for t, c in dups.items()) if dups else "없음"
        return {"통과": not violations, "term수": term_count, "중복어": dup_label,
                "키워드수": len(kws), "관련어수": len(related),
                "위반": violations, "경고": warnings}
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
    ap.add_argument("--max-terms", type=int, default=DEFAULT_MAX_TERMS,
                    help=f"고유 term 상한 (default: {DEFAULT_MAX_TERMS})")
    ap.add_argument("--min-terms", type=int, default=DEFAULT_MIN_TERMS,
                    help=f"고유 term 하한 (default: {DEFAULT_MIN_TERMS})")
    # 단건 모드
    ap.add_argument("--name", help="단건 검증: 상품명")
    ap.add_argument("--terms", help="단건 검증: term 분해 (쉼표 구분, 중복 포함)")
    ap.add_argument("--keywords", help="단건 검증: 사용 키워드 2~3개 (쉼표 구분)")
    args = ap.parse_args()

    # --- 단건 모드 ---
    if args.name:
        product = {
            "새상품명": args.name,
            "term분해": [t.strip() for t in (args.terms or "").split(",") if t.strip()],
            "키워드": [k.strip() for k in (args.keywords or "").split(",") if k.strip()],
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

    for p in products:
        # 보류 건(키워드 2개 확보 실패 등)은 검증 대상이 아니다 — 상태만 유지
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
