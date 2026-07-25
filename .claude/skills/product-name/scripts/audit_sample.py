#!/usr/bin/env python3
"""표본 재검수 추출기 — 파이프라인 ⑤ product-name (2026-07-24 이룸님 결정).

왜 필요한가:
  D·B·R6·R7을 다 통과해도 **판단의 질**은 코드로 못 막는다.
  B가 반증 목록을 던져도 Claude가 "없음"이라 답하면 아무도 못 막고(지목형 b안의 구조적 빈틈),
  #4 살롱체어(적합성 오판)·#9 다이그라인더(도메인 지식)는 산술 규칙 밖이다.
  1,038건 전수 검수는 불가능하므로 **수상한 것부터 표본을 뽑아 사람이 본다.**

이룸님 결정 (2026-07-24):
  · 추출 = 플래그 우선 (수상한 것부터 자동 선별)
  · 크기 = 30~40건 (기본 35)
  · 주기 = 그룹 완료 후 한 번에

플래그 규칙 (의심 점수 = 가중합. 높을수록 먼저 검수):
  F1 반증 목록이 크다(≥threshold)는데 반증="없음"     … 대충 봤을 가능성. #8 유형   [+3]
  F2 term 4로 끝남 (키워드 부족의 신호)                                              [+1]
  F3 상위 카테고리 폴백 채택 (다른 상품 위험이 leaf보다 큼)                          [+2]
  F4 관련어를 3개 이하만 적음 (덜 훑었을 가능성)                                     [+2]
  F5 채택 키워드가 전부 10만 이상 (저상품수 직결어를 하나도 못 잡음. 대형만 붙임)     [+2]
  F6 원본 상품명 어근과 채택 어근이 1개 이하로만 겹침 (엉뚱한 카테고리 위험)         [+2]
  플래그 0점이어도 무작위 소수를 섞어(--random) 사각지대를 본다.

Usage:
  python audit_sample.py --run-dir <R> [--size 35] [--random 5] [--flag-threshold 60]
  python audit_sample.py --run-dir <R> --sheet <ID> --tab 상품명   # 시트에서 직접 읽기
"""
import argparse
import glob
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# 반증 목록이 이 개수 이상인데 "없음"이면 F1 발동 (대충 봤을 가능성)
DEFAULT_BIG_CHALLENGE = 60


def _roots(text):
    """어근 토큰 집합 — 2글자 이상. name_check와 같은 분해 규칙."""
    out = set()
    for tok in re.split(r"[\s/,·\-_()\[\]]+", str(text or "")):
        tok = tok.strip()
        if len(tok) >= 2 and not tok.isdigit():
            out.add(tok)
    return out


def _to_int(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return int(v)
    try:
        return int(float(str(v).replace(",", "")))
    except ValueError:
        return None


def score_product(p, big_challenge=DEFAULT_BIG_CHALLENGE):
    """상품 1건의 의심 점수와 플래그 사유를 계산한다. 생성완료 건만 대상."""
    status = str(p.get("상태") or "")
    if not status.startswith("생성완료") and status:
        # 보류·스킵·검증실패는 표본 대상이 아니다(이미 상태로 걸러졌거나 안 나감)
        return None

    flags, score = [], 0

    related = p.get("관련어") or []
    rebut = str(p.get("반증") or "").strip()
    challenge_n = _to_int(p.get("반증총")) or len(p.get("반증목록") or [])

    # F1 — 반증 목록 큰데 "없음"
    if challenge_n and challenge_n >= big_challenge and rebut in ("없음", "없음.", ""):
        flags.append(f"F1 반증{challenge_n}개인데 '없음'")
        score += 3

    # F2 — term 4
    tc = _to_int(p.get("term수"))
    if tc == 4:
        flags.append("F2 term4")
        score += 1

    # F3 — 상위 폴백 채택 (메모/기준에 흔적)
    blob = json.dumps(p, ensure_ascii=False)
    if "상위카테고리" in blob or "상위폴백" in blob or "상위뷰" in str(p.get("메모") or ""):
        flags.append("F3 상위폴백")
        score += 2

    # F4 — 관련어 3개 이하
    if len(related) <= 3:
        flags.append(f"F4 관련어{len(related)}개")
        score += 2

    # F5 — 채택 키워드가 '전부' 10만+ (저상품수 직결어를 하나도 못 잡음)
    #   2026-07-24: 대형으로 term 채우기가 정상이 됐으므로 max가 아니라 min을 본다.
    #   저상품수 직결어가 하나라도 있으면 정상 — 전부 대형일 때만 의심.
    pcs = []
    kws = [str(p.get(f"키워드{i}") or "").strip() for i in (1, 2, 3, 4, 5)]
    kws = [k for k in kws if k]
    by_kw = {str(r.get("키워드", "")).strip(): r for r in related}
    for k in kws:
        v = _to_int(by_kw.get(k, {}).get("상품수"))
        if v is not None:
            pcs.append(v)
    if pcs and min(pcs) >= 100000:
        flags.append(f"F5 채택 전부 대형(최저 {min(pcs):,})")
        score += 2

    # F6 — 상품명 term이 원본 어디에도 안 나타남 (엉뚱한 카테고리 위험)
    #   term분해 토큰을 원본에 substring으로 대조한다. 키워드끼리 토큰 비교하면
    #   '무선빙수기'와 '슬러시빙수기'가 0으로 나와(붙어있어서) 정답도 걸린다 — 그래서 term을 쓴다.
    #   정상은 최소 범주어 1개가 원본에 있다(빙수기·그라인더·체어). 하나도 없으면
    #   접지선 상품에 의자 키워드가 붙은 꼴 = 카테고리 오류 신호.
    terms = p.get("term분해") or []
    orig_flat = re.sub(r"\s+", "", str(p.get("원본상품명") or ""))
    if terms and orig_flat:
        hit = any(re.sub(r"\s+", "", str(t)) and re.sub(r"\s+", "", str(t)) in orig_flat
                  for t in terms)
        if not hit:
            flags.append("F6 term이 원본에 전무")
            score += 2

    return {"score": score, "flags": flags,
            "productId": p.get("productId", ""),
            "원본상품명": p.get("원본상품명", ""),
            "새상품명": p.get("새상품명", ""),
            "카테고리": p.get("카테고리", ""),
            "반증총": challenge_n, "관련어수": len(related),
            "term수": tc, "반증": rebut}


def load_from_checked(run_dir):
    out = []
    for cf in sorted(glob.glob(os.path.join(run_dir, "checked", "checked_*.json"))):
        data = json.load(open(cf, encoding="utf-8"))
        out += data.get("products", [])
    return out


def load_from_named(run_dir):
    out = []
    for nf in sorted(glob.glob(os.path.join(run_dir, "named", "named_*.json"))):
        data = json.load(open(nf, encoding="utf-8"))
        out += data.get("products", [])
    return out


def pick(products, size, random_n, big_challenge, seed_salt=""):
    """의심 점수 내림차순으로 size-random_n건 + 하위에서 random_n건.

    무작위는 Date/random 금지 환경이라 productId 해시로 결정론적 셔플한다
    (매 실행 동일 표본 — 재현 가능해야 검수 결과를 되짚을 수 있다).
    """
    scored = [s for s in (score_product(p, big_challenge) for p in products) if s]
    scored.sort(key=lambda x: (-x["score"], x["productId"]))

    flagged = [s for s in scored if s["score"] > 0]
    zero = [s for s in scored if s["score"] == 0]

    top_n = max(0, size - random_n)
    sample = flagged[:top_n]

    # 플래그가 top_n보다 적으면 zero에서 채운다
    if len(sample) < top_n:
        need = top_n - len(sample)
        sample += _hash_shuffle(zero, seed_salt)[:need]
        zero = _hash_shuffle(zero, seed_salt)[need:]

    # 무작위 몫 — 남은 zero(또는 남은 flagged)에서
    pool = zero if zero else [s for s in scored if s not in sample]
    sample += _hash_shuffle(pool, seed_salt)[:random_n]

    return scored, sample


def _hash_shuffle(items, salt=""):
    """productId 해시 기반 결정론적 정렬 (random/Date 없이 재현 가능한 셔플)."""
    def h(s):
        v = 2166136261
        for ch in (str(s.get("productId", "")) + salt):
            v = ((v ^ ord(ch)) * 16777619) & 0xFFFFFFFF
        return v
    return sorted(items, key=h)


def main():
    ap = argparse.ArgumentParser(description="표본 재검수 추출 (플래그 우선)")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--size", type=int, default=35, help="표본 크기 (기본 35)")
    ap.add_argument("--random", type=int, default=5, help="표본 중 무작위 몫 (기본 5)")
    ap.add_argument("--flag-threshold", type=int, default=DEFAULT_BIG_CHALLENGE,
                    help="F1: 반증 목록이 몇 개 이상일 때 '큰 목록'으로 볼지 (기본 60)")
    ap.add_argument("--from", dest="source", choices=["checked", "named"], default="checked",
                    help="checked/(기본) 또는 named/ 중 어디서 읽을지")
    ap.add_argument("--out", help="표본을 JSON으로 저장할 경로")
    args = ap.parse_args()

    run_dir = os.path.abspath(args.run_dir)
    products = (load_from_checked(run_dir) if args.source == "checked"
                else load_from_named(run_dir))
    if not products:
        print(f"대상이 없습니다 ({args.source}/ 비어 있음). append 전이면 --from named 를 쓰세요.",
              file=sys.stderr)
        sys.exit(1)

    scored, sample = pick(products, args.size, args.random, args.flag_threshold)

    generated = [s for s in scored]
    flagged_n = sum(1 for s in scored if s["score"] > 0)
    print(f"###AUDIT### 생성완료 {len(scored)}건 / 플래그 {flagged_n}건 / 표본 {len(sample)}건 "
          f"(무작위 {args.random} 포함)")
    print(f"플래그 규칙: F1 반증{args.flag_threshold}+인데'없음'(+3) · F2 term4(+1) · "
          f"F3 상위폴백(+2) · F4 관련어≤3(+2) · F5 채택상품수10만+(+1) · F6 원본겹침≤1(+2)\n")

    print(f"{'점수':>3} {'플래그':<38} 상품명")
    print("-" * 92)
    for s in sample:
        fl = ", ".join(s["flags"]) or "(무작위)"
        name = s["새상품명"] or s["원본상품명"]
        print(f"{s['score']:>3} {fl:<38.38} {name[:40]}")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"표본": sample, "전체점수": scored}, f, ensure_ascii=False, indent=2)
        print(f"\n-> {args.out}")

    print("\n검수 방법: 각 상품의 썸네일과 카테고리 뷰를 열어")
    print("  ① 이 상품이 맞는가(적합성) ② 더 싸고 맞는 키워드를 놓쳤나 를 본다.")
    print("  틀린 게 3건 이상이면 장치를 재점검, 0~1건이면 나머지를 신뢰한다.")


if __name__ == "__main__":
    main()
