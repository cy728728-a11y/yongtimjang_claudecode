#!/usr/bin/env python3
"""역방향 반증 목록 생성기(B 장치) — 파이프라인 ⑤ product-name.

왜 필요한가 (2026-07-24):
  D(cat_view)가 전 행을 훑을 수 있게 구조화해도, **빈도 1짜리 특징어는 인덱스에 안 뜬다.**
  실측: `일자그라인더`(7,763)는 인덱스에 없고 본문 178/331번째에만 있었다.
  또 Claude가 관련어 목록을 스스로 잘라 찍는 실패가 실제로 났다(후보 85개 중 36개만 봄).

  그래서 상품명 확정 **후에** 스크립트가 파일을 다시 훑어
  "채택 키워드와 같은 범주어를 쓰면서 상품수가 더 낮은 행"을 되던진다.
  목록을 기계가 만들기 때문에 누락이 원천적으로 불가능하다.

되던지는 형식 = **이름만**. 상품수·검색량은 이미 D 뷰 본문에 있고 같은 컨텍스트라 재출력이 낭비다.
  실측: 최대 케이스(서랍장) 211개 → 이름만이면 ~1,000 tok.
  검색량·상품수 하한으로 압축하려 했으나 실패했다 — 정답 키워드의 검색량이 40~140이라
  브랜드 노이즈와 같은 롱테일 구간에 섞여 있어, 자르면 정답이 먼저 죽는다.

답변 형식 (2026-07-24 이룸님 결정 = b안):
  되던진 목록 전부에 사유 코드를 찍게 하지 않는다. **채택보다 나은 게 있으면 지목, 없으면
  "없음 + 한 줄 이유"**. 200개 코드 찍기는 형식적 답변이 되어 "안 본 것을 본 것처럼"
  기록만 남기고, 그 기록이 오히려 검수자를 방심하게 만들기 때문이다.

Usage:
  # 단건
  python challenge.py --input <카테고리>.xlsx --adopted "다이그라인더,에어그라인더"
  # 배치 (named_*.json 의 각 상품에 '반증목록' 을 채워 넣는다)
  python challenge.py --named named_001.json --cat-dir <카테고리파일 디렉터리> --output named_001.chal.json
"""
import argparse
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from cat_view import load_rows, find_categories, strip_category  # noqa: E402

# 되던지기 상한 — 넘으면 상품수 오름차순으로 자르고 잘린 개수를 명시한다.
# 조용히 자르지 않는 게 핵심이다. "덮었다"는 착각이 이번 실패의 원인이었다.
DEFAULT_MAX = 250


def roots_of(keyword, cats):
    """채택 키워드가 쓰는 범주어를 뽑는다. 범주어가 없으면 접미 2~3글자를 대용."""
    hits = [s for s in cats if keyword.endswith(s) and len(keyword) > len(s)]
    if hits:
        return {max(hits, key=len)}
    inner = [s for s in cats if s in keyword]
    if inner:
        return {max(inner, key=len)}
    # 범주어를 전혀 안 쓰는 키워드 — 접미 3글자·2글자를 어근으로 본다
    out = set()
    if len(keyword) >= 3:
        out.add(keyword[-3:])
    if len(keyword) >= 2:
        out.add(keyword[-2:])
    return out


def build_challenge(path, adopted, drop_brand=True, max_items=DEFAULT_MAX):
    """채택 키워드보다 상품수가 낮으면서 같은 범주어를 쓰는 행의 '이름'을 반환.

    반환: {"목록": [키워드...], "총": int, "잘림": int, "기준상품수": int, "어근": [...]}
    """
    # 제외키워드 컷은 기본 켬 — 반증이 뷰에서 방금 거른 상표위험 키워드를 되살리면 안 된다.
    rows, _dropped, _dropped_ex, _total, _rep = load_rows(path, drop_brand)
    if not rows:
        return {"목록": [], "총": 0, "잘림": 0, "기준상품수": None, "어근": []}

    cats = find_categories(rows)
    by_kw = {r["kw"]: r for r in rows}

    roots, cutoff, found_any = set(), 0, False
    for kw in adopted:
        roots |= roots_of(kw, cats)
        r = by_kw.get(kw)
        if r:
            # 채택 키워드 각각을 '더 싼 것으로 바꿀 수 있나' 묻는 것이므로 최대값이 기준
            cutoff = max(cutoff, r["pc"])
            found_any = True
    if not found_any:
        # 채택 키워드가 전부 이 카테고리 파일 밖(예: 상위뷰)에서 온 경우 —
        # 기준 상품수를 정할 수 없어 접미사만으로 광범위 매칭하면 무의미/충돌(None 포맷 에러) 하므로 건너뛴다.
        return {"목록": [], "총": 0, "잘림": 0, "기준상품수": None, "어근": sorted(roots),
                "생략사유": "채택 키워드가 이 카테고리 파일에 없음(상위뷰 등 외부 출처로 추정) — 반증 생략"}
    if not cutoff:
        cutoff = 10 ** 9

    adopted_set = set(adopted)
    hits = [r for r in rows
            if r["kw"] not in adopted_set
            and r["pc"] < cutoff
            and any(s in r["kw"] for s in roots)]
    hits.sort(key=lambda x: x["pc"])

    total = len(hits)
    cut = 0
    if total > max_items:
        cut = total - max_items
        hits = hits[:max_items]

    return {
        "목록": [r["kw"] for r in hits],
        "총": total,
        "잘림": cut,
        "기준상품수": cutoff if cutoff < 10 ** 9 else None,
        "어근": sorted(roots),
    }


def render(ch, adopted):
    """Claude에게 던질 텍스트. 이름만 나열하고 답변 형식을 명시한다."""
    if not ch["목록"]:
        return ("## 반증 (B)\n채택 키워드보다 상품수가 낮으면서 같은 범주어를 쓰는 행이 없다. "
                "확인 불필요.")
    L = []
    L.append("## 반증 (B) — 반드시 답할 것")
    L.append(f"채택: {', '.join(adopted)} (기준 상품수 {ch['기준상품수']:,})")
    L.append(f"아래는 **채택보다 상품수가 낮으면서 같은 범주어({'·'.join(ch['어근'])})를 쓰는** "
             f"{ch['총']}개다."
             + (f" (상품수 낮은 순 {len(ch['목록'])}개만 표시, {ch['잘림']}개 생략)" if ch["잘림"] else ""))
    L.append("상품수·검색량은 위 본문에 있다. 여기서는 이름만 던진다.")
    L.append("")
    L.append(", ".join(ch["목록"]))
    L.append("")
    L.append("답변: 이 중 이 상품에 **더 적합하면서 상품수가 낮은** 키워드가 있으면 지목하고 "
             "상품명을 다시 만든다. 없으면 `반증: 없음` 과 한 줄 이유를 적는다. "
             "(전부에 사유를 달 필요는 없다)")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="역방향 반증 목록 생성 (B 장치)")
    ap.add_argument("--input", help="카테고리별 키워드 xlsx (단건 모드)")
    ap.add_argument("--adopted", help="채택 키워드 쉼표 구분 (단건 모드)")
    ap.add_argument("--named", help="named_*.json (배치 모드)")
    ap.add_argument("--cat-dir", help="카테고리 xlsx 디렉터리 (배치 모드)")
    ap.add_argument("--output", help="배치 결과 저장 경로")
    ap.add_argument("--max-items", type=int, default=DEFAULT_MAX)
    ap.add_argument("--keep-brand", action="store_true")
    args = ap.parse_args()

    drop_brand = not args.keep_brand

    # --- 단건 ---
    if args.input:
        adopted = [k.strip() for k in (args.adopted or "").split(",") if k.strip()]
        if not adopted:
            ap.error("--adopted 가 필요합니다.")
        ch = build_challenge(args.input, adopted, drop_brand, args.max_items)
        print(render(ch, adopted))
        return

    if not args.named:
        ap.error("--input 또는 --named 중 하나는 필요합니다.")

    # --- 배치 ---
    try:
        with open(args.named, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: 입력 읽기 실패({args.named}): {e}", file=sys.stderr)
        sys.exit(1)

    products = data.get("products", data if isinstance(data, list) else [])
    made = 0
    for p in products:
        if p.get("상태", "").startswith("보류") or not p.get("새상품명"):
            continue
        cat_file = p.get("카테고리파일")
        if not cat_file:
            continue
        path = cat_file if os.path.isabs(cat_file) else os.path.join(args.cat_dir or "", cat_file)
        if not os.path.exists(path):
            p["반증"] = {"오류": f"카테고리 파일 없음: {path}"}
            continue
        adopted = [str(p.get(f"키워드{i}") or "").strip() for i in range(1, 6)]
        adopted = [k for k in adopted if k]
        ch = build_challenge(path, adopted, drop_brand, args.max_items)
        p["반증목록"] = ch["목록"]
        p["반증총"] = ch["총"]
        p["반증텍스트"] = render(ch, adopted)
        made += 1

    out = args.output or args.named
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"###CHALLENGE### {made}건 생성 -> {out}")


if __name__ == "__main__":
    main()
