#!/usr/bin/env python3
"""R9(배치 어긋남) 단독 실패 건을 기계적으로 재배열한다.

25-2 회차에서 확립된 경로 — 워커 재팬아웃으로는 수렴 안 되고(144→117), 규칙 자체가
결정론적이라 파이썬이 정확히 고칠 수 있다. 1-1 회차 실전 검증: 124건 교정 · 재검증
전건 통과 · 비용 0 (원본: 00-system/04-specs/2026-08-04-상품명스킬-fix_r9.py).

하는 일:
  1) checked_*.json 에서 위반이 R9 **하나뿐인** 건을 고른다
  2) 상품명을 어절로 쪼개 키워드 덩어리(a 1 b 2 c 의 1·2)와 원본 단어(a·b·c)로 분리
  3) 원본 단어와 키워드를 앞에서부터 번갈아 재배치 → 끝에 `기본형`
  4) term분해를 어절 단위로 되매핑(원래 순서에서 소진) → R1 유지
  5) named_*.json 을 제자리 수정 (메모에 'R9 기계 재배열' 표기)

수정 후 run_names.py check 를 다시 돌린다. 호출은 run_names.py fix-r9 서브커맨드가
기본 경로다(기본 dry-run, --commit 시 저장).
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from name_check import BASE_SUFFIX, keyword_blocks, nows, is_exact_in_name  # noqa: E402


def word_terms(words, terms):
    """어절마다 그 어절을 이루는 term 묶음을 돌려준다(원래 순서에서 소진).

    실패하면 None — 그러면 term분해를 못 믿으므로 이 건은 손대지 않는다.
    """
    out, i = [], 0
    for w in words:
        acc, grp = "", []
        while i < len(terms) and acc != nows(w):
            acc += nows(terms[i])
            grp.append(terms[i])
            i += 1
            if len(acc) > len(nows(w)):
                return None
        if acc != nows(w):
            return None
        out.append(grp)
    return out if i == len(terms) else None


def rearrange(name, keywords, terms):
    """`a 1 b 2 c` 로 재배열한 (새이름, 새term분해). 못 고치면 None."""
    exact = [k for k in keywords if is_exact_in_name(k, name)]
    if not exact:
        return None
    words, blocks = keyword_blocks(name, exact)
    if not blocks:
        return None
    # term분해에서 마커를 떼고 어절 매핑
    terms_wo = list(terms)
    if terms_wo and terms_wo[-1] == BASE_SUFFIX:
        terms_wo = terms_wo[:-1]
    wt = word_terms(words, terms_wo)
    if wt is None:
        return None

    kw_units = []      # 키워드 덩어리 (어절 여러 개일 수 있음)
    covered = set()
    for s, e in blocks:
        kw_units.append(list(range(s, e)))
        covered.update(range(s, e))
    plain = [i for i in range(len(words)) if i not in covered]   # 원본 단어 a·b·c
    # 앞에서부터 번갈아: a 1 b 2 c 3 ... 남는 쪽은 뒤에 이어 붙인다
    order = []
    pi = ki = 0
    while pi < len(plain) or ki < len(kw_units):
        if pi < len(plain):
            order.append([plain[pi]]); pi += 1
        if ki < len(kw_units):
            order.append(kw_units[ki]); ki += 1

    new_words, new_terms = [], []
    for unit in order:
        for idx in unit:
            new_words.append(words[idx])
            new_terms.extend(wt[idx])
    new_name = " ".join(new_words + [BASE_SUFFIX])
    return new_name, new_terms + [BASE_SUFFIX]


def run(run_dir, commit=False):
    """R9 단독 실패 건을 재배열해 named_*.json 을 제자리 수정. (fixed, skipped) 반환."""
    run_dir = os.path.expanduser(run_dir)
    # 1) R9 단독 실패 pid 수집 — chal/draft 는 run_names 와 같은 이유로 배제
    targets = {}
    for p in sorted(glob.glob(os.path.join(run_dir, "checked",
                                           "checked_[0-9][0-9][0-9].json"))):
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        for it in data.get("products", []):
            if it.get("상태") != "검증실패":
                continue
            v = (it.get("검증") or {}).get("위반", [])
            if len(v) == 1 and v[0].startswith("R9"):
                targets[it["productId"]] = True
    print(f"R9 단독 실패 {len(targets)}건")

    fixed = skipped = 0
    for p in sorted(glob.glob(os.path.join(run_dir, "named",
                                           "named_[0-9][0-9][0-9].json"))):
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        touched = False
        for it in d.get("products", []):
            if it.get("productId") not in targets:
                continue
            kws = [it.get(f"키워드{i}") for i in range(1, 6)]
            kws = [k for k in kws if k]
            r = rearrange(it.get("새상품명", ""), kws, it.get("term분해") or [])
            if not r:
                skipped += 1
                continue
            old = it["새상품명"]
            it["새상품명"], it["term분해"] = r
            it["메모"] = (it.get("메모") or "") + f" | R9 기계 재배열(이전: {old})"
            touched = True
            fixed += 1
        if touched and commit:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
    print(f"재배열 {fixed}건 / 손 못 댄 건 {skipped}건"
          + ("  [저장]" if commit else "  [dry-run]"))
    return fixed, skipped


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if len(sys.argv) < 2 or sys.argv[1].startswith("--"):
        print("사용법: fix_r9.py <run-dir> [--commit]")
        sys.exit(2)
    run(sys.argv[1], commit="--commit" in sys.argv)
