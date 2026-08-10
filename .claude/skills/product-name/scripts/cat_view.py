#!/usr/bin/env python3
"""카테고리 키워드 파일 → Claude가 훑을 수 있는 뷰(D 장치) — 파이프라인 ⑤ product-name.

왜 필요한가 (2026-07-24):
  이전 방식은 필터가 후보 90개로 추려서 넘겼는데, 그 필터가 **카테고리 전용어를 죽였다.**
  '의자'(194/317=61%)가 노이즈 컷에 걸려 삭제되자 그 어근만 가진 직결어
  (전동미용의자 18,381 · 일자그라인더 7,763)가 경쟁 진입 전에 전멸했다.
  임계값 조정으로는 못 푼다 — 범주어(변별력 0이지만 필수)와 특징어(변별력 생성)를
  단일 규칙으로 처리하는 게 원인이기 때문이다.

  그래서 필터를 걷어내고 **전 행을 넘기되 훑을 수 있게 구조화**한다.
  실측 근거: 놓친 키워드의 상품수 오름차순 순위가 148~231위였다(전체 300~380행).
  상위 N개를 자르는 어떤 컷도 이걸 못 잡는다.

구조:
  1. 범주어 — 많은 키워드의 '접미'로 등장하는 어근 (의자 145 · 체어 43). 본문 묶음의 기준
  2. 특징어 — 범주어를 떼어낸 접두부에서만 찾은 어근 (미용 5 · 이발 2 · 바버 2)
     → 전체 substring에서 찾으면 '샵의자'·'용의자' 같은 경계 파괴 어근이 나온다(v1 실패)
  3. 특징어 인덱스 — 희소순(변별력순)으로 키워드 이름만 나열. 훑기의 진입점
  4. 본문 — 범주어별 1회 나열. 중복 출력 없음

브랜드키워드 O는 제외한다(실측: 27파일 8,131행 중 26%, 정답 손실 0).
쇼핑성키워드는 **제외하지 않고 표시만 한다** — X를 자르면 이번에 찾은 정답 12개 중 6개가 죽는다
(미용전동의자·바버샵의자·엔틱3단서랍장 등).

블랙리스트 `제외키워드`(정확일치)도 제외한다 (2026-08-09 추가).
**값은 비용이 아니라 상표 리스크다** — 그 시트는 상표 위험으로 판정돼 이룸님이 승인한 키워드고,
이 뷰는 그 키워드로 **상품명을 만든다.** 안 거르면 위험 키워드가 상품명에 박히고 되돌리려면
상품명 재작업이다. 행이 줄어드는 건 부산물(워커 비용 ~1%).
여기서 AI 판정을 하지 않는다 — 판정은 `sellerlife-keyword/detect.py` 가 통다운 가공 때 하고,
이 파일은 그 결과 명단을 **조회만** 한다.
※ `제외카테고리`·`제외브랜드`는 넣지 않는다. 전자는 카테고리 뷰가 통째로 비어 `키워드부족`
   → 보류 → 재교정이라는 제일 비싼 경로로 가고, 후자는 부분일치인데 손실 검증이 없다.

Usage:
  python cat_view.py --input <카테고리>.xlsx [--out view.txt] [--keep-brand] [--keep-excluded]
"""
import argparse
import os
import sys
from collections import Counter

try:
    import openpyxl
except ImportError:
    print("ERROR: openpyxl not installed. Run: pip install openpyxl>=3.1.0", file=sys.stderr)
    sys.exit(1)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 블랙리스트 판정은 eroomlib 1벌을 쓴다(catfix 게이트·재고 스캔과 같은 규칙).
# `.claude` 앵커(= lib/eroomlib)를 찾아 lib 를 1회 insert — standalone CLI 로도 돌기 때문.
_d = os.path.dirname(os.path.abspath(__file__))
while _d and _d != os.path.dirname(_d):
    _lib = os.path.join(_d, "lib")
    if os.path.isdir(os.path.join(_lib, "eroomlib")):
        if _lib not in sys.path:
            sys.path.insert(0, _lib)
        break
    _d = os.path.dirname(_d)

# 셀러라이프 rawdata 열 위치 (0-based)
COL_KW, COL_CAT, COL_BRAND, COL_SHOP, COL_SV, COL_PC = 1, 2, 3, 4, 6, 17

# 범주어 판정: 전체의 이 비율 이상을 접미로 차지하면 범주어
CAT_RATIO = 0.12
CAT_MIN_HIT = 8
# 포함관계 정리: 긴 어근이 짧은 어근 빈도의 이 비율 이상이면 짧은 쪽을 버린다
#   '랍장'(141) vs '서랍장'(140) → 0.99 → '랍장' 폐기
#   '의자'(145) vs '용의자'(7)   → 0.05 → '의자' 유지
CONTAIN_RATIO = 0.9
# 특징어 최소 빈도. 1로 낮추면 인덱스가 폭발하므로 2 — 빈도 1짜리는 B(반증)가 잡는다
FEAT_MIN_FREQ = 2


def _num(v, default=10 ** 9):
    try:
        return int(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def load_rows(path, drop_brand=True, drop_excluded=True):
    """카테고리 xlsx → 행 리스트(상품수 오름차순).

    반환: `(rows, dropped_brand, dropped_excluded, total, category)`

    **컷이 `render()` 가 아니라 여기 사는 이유**: 소비자가 셋이다 — `render()`(뷰) ·
    `audit_sample.py`(감사) · `challenge.py`(반증). 여기 넣으면 셋이 한 번에 일치한다.
    `render()` 에만 넣으면 반증(challenge)이 방금 거른 위험 키워드를 되살릴 수 있다.

    `drop_excluded` 실패는 삼키지 않는다 — 블랙리스트를 못 읽으면 예외가 그대로 올라가
    prep 이 실패한다. prep 은 워커 비용이 나가기 전 단계라 실패해도 공짜이고 재실행되지만,
    조용히 통과시키면 상표 위험 키워드가 상품명에 박혀 사후에야 드러난다.
    """
    excluded = set()
    if drop_excluded:
        from eroomlib.exclusion import excluded_keywords
        excluded = excluded_keywords()   # 프로세스 캐시 — 카테고리마다 불러도 로드는 1회

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    raw = list(wb.active.iter_rows(values_only=True))
    wb.close()
    if not raw:
        return [], 0, 0, 0, ""

    rows, dropped, dropped_ex = [], 0, 0
    cats = Counter()
    for r in raw[1:]:
        if not r or len(r) <= COL_PC or not r[COL_KW]:
            continue
        if drop_brand and r[COL_BRAND] == "O":
            dropped += 1
            continue
        if excluded and str(r[COL_KW]).strip() in excluded:
            dropped_ex += 1
            continue
        if r[COL_CAT]:
            cats[str(r[COL_CAT]).strip()] += 1
        rows.append({
            "kw": str(r[COL_KW]).strip(),
            "pc": _num(r[COL_PC]),
            "sv": _num(r[COL_SV], 0),
            "shop": "O" if r[COL_SHOP] == "O" else "-",
        })
    rows.sort(key=lambda x: x["pc"])
    rep = cats.most_common(1)[0][0] if cats else ""
    return rows, dropped, dropped_ex, len(raw) - 1, rep


def _has_digit_only(s):
    """숫자만으로 이뤄진 어근 제외 — 모델번호('00', '1000')가 범주어로 잡히는 걸 막는다."""
    return s.isdigit()


def find_categories(rows, ratio=CAT_RATIO, min_hit=CAT_MIN_HIT):
    """범주어 = 다수 키워드의 접미로 등장하는 어근. 접미로 한정해 경계 파괴를 막는다."""
    cnt = Counter()
    for r in rows:
        w = r["kw"]
        for L in range(2, min(6, len(w)) + 1):
            cnt[w[-L:]] += 1
    cut = max(len(rows) * ratio, min_hit)
    cand = {s: c for s, c in cnt.items() if c >= cut and not _has_digit_only(s)}

    # 포함관계 정리 — 짧은 어근이 긴 어근에 거의 흡수되면 짧은 쪽을 버린다
    keep = {}
    for s, c in sorted(cand.items(), key=lambda x: -len(x[0])):
        absorbed = any(s in t and cand[t] >= c * CONTAIN_RATIO for t in keep)
        if not absorbed:
            keep[s] = c
    # 남은 것 중 서로 포함관계면 긴 쪽만 (역방향 정리)
    final = {}
    for s, c in sorted(keep.items(), key=lambda x: -len(x[0])):
        if any(s in t for t in final):
            continue
        final[s] = c
    return final


def strip_category(kw, cats):
    """키워드에서 범주어 접미를 떼어낸 접두부. 범주어가 없거나 접두부가 없으면 None."""
    hits = [s for s in cats if kw.endswith(s) and len(kw) > len(s)]
    if not hits:
        return None
    return kw[:-len(max(hits, key=len))]


def find_features(rows, cats, min_freq=FEAT_MIN_FREQ):
    """특징어 = 접두부들 사이의 공통 부분문자열. 범주어 제거 후라 경계가 깨끗하다."""
    prefixes = [p for p in (strip_category(r["kw"], cats) for r in rows) if p and len(p) >= 2]
    cnt = Counter()
    for p in prefixes:
        seen = set()
        for L in range(2, min(5, len(p)) + 1):
            for i in range(len(p) - L + 1):
                seen.add(p[i:i + L])
        for s in seen:
            if not _has_digit_only(s):
                cnt[s] += 1
    cand = {s: c for s, c in cnt.items() if c >= min_freq}
    # 같은 빈도면 긴 쪽만 유지 ('미용실'과 '미용'이 동률이면 '미용실')
    keep = {}
    for s, c in sorted(cand.items(), key=lambda x: -len(x[0])):
        if any(s in t and cand[t] == c for t in keep):
            continue
        keep[s] = c
    return keep


def build_index(rows, feats, max_members=12):
    """특징어 → 그 어근을 포함하는 키워드 이름. 희소순(변별력순)으로 정렬해 반환."""
    out = []
    for s in feats:
        members = [r["kw"] for r in rows if s in r["kw"]]
        if len(members) < FEAT_MIN_FREQ:
            continue
        out.append((s, members))
    # 멤버 수 오름차순 = 변별력 순. 같으면 가나다
    out.sort(key=lambda x: (len(x[1]), x[0]))
    return [(s, m[:max_members], len(m)) for s, m in out]


def render(path, drop_brand=True, index_max=60, index_members=12, drop_excluded=True):
    rows, dropped, dropped_ex, total, rep = load_rows(path, drop_brand, drop_excluded)
    if not rows:
        return f"# (빈 파일) {path}"

    cats = find_categories(rows)
    feats = find_features(rows, cats)
    index = build_index(rows, feats, index_members)[:index_max]

    L = []
    L.append(f"# 카테고리: {rep}")
    # 감사 흔적 — 워커가 읽는다. 무엇이 몇 개 빠졌는지가 뷰 안에 남아야 사후 대조가 된다.
    L.append(f"# 원본 {total}행 · 브랜드키워드 제외 {dropped}"
             f" · 상표위험(블랙리스트) 제외 {dropped_ex} → 검토대상 {len(rows)}행")
    L.append("# 범주어(변별력 없음·필수): " +
             (" · ".join(f"{s}({c})" for s, c in sorted(cats.items(), key=lambda x: -x[1])) or "없음"))
    L.append("")
    L.append("## 특징어 인덱스 — 희소할수록 변별력이 크다. 여기가 훑기의 진입점")
    if index:
        for s, members, n in index:
            more = f" …+{n - len(members)}" if n > len(members) else ""
            L.append(f"{s}({n}): " + ", ".join(members) + more)
    else:
        L.append("(특징어 없음 — 본문을 직접 훑을 것)")
    L.append("")
    L.append("## 전체 — 키워드 / 상품수 / 월검색 / 쇼핑성")
    L.append("# 쇼핑성 '-' 는 참고용 표시일 뿐 배제 사유가 아니다(실측: 정답의 절반이 '-' 였다)")

    buckets = {}
    for r in rows:
        hits = [s for s in cats if r["kw"].endswith(s)]
        key = max(hits, key=len) if hits else "기타"
        buckets.setdefault(key, []).append(r)
    for key, rs in sorted(buckets.items(), key=lambda kv: (kv[0] == "기타", -len(kv[1]))):
        L.append(f"[{key}] {len(rs)}행")
        for r in rs:
            pc = "?" if r["pc"] >= 10 ** 9 else r["pc"]
            L.append(f"{r['kw']}\t{pc}\t{r['sv']}\t{r['shop']}")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="카테고리 키워드 파일 → 훑기용 뷰 (D 장치)")
    ap.add_argument("--input", required=True, help="카테고리별 키워드 xlsx")
    ap.add_argument("--out", help="출력 경로 (미지정시 stdout)")
    ap.add_argument("--keep-brand", action="store_true", help="브랜드키워드 O도 포함")
    ap.add_argument("--keep-excluded", action="store_true",
                    help="블랙리스트 제외키워드도 포함(상표 리스크 컷 끄기)")
    ap.add_argument("--index-max", type=int, default=60, help="특징어 인덱스 최대 줄 수")
    args = ap.parse_args()

    try:
        text = render(args.input, drop_brand=not args.keep_brand, index_max=args.index_max,
                      drop_excluded=not args.keep_excluded)
    except OSError as e:
        print(f"ERROR: 파일 읽기 실패({args.input}): {e}", file=sys.stderr)
        sys.exit(1)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"-> {args.out} ({len(text):,}자)")
    else:
        print(text)


if __name__ == "__main__":
    main()
