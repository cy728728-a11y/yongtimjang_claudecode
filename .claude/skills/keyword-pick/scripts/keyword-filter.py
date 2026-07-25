#!/usr/bin/env python3
"""아이템스카우트 키워드 익스포트(.xlsx) → 상품수 기준 후보 키워드 필터.

레퍼런스(상품 참조) 없이 "상품수 낮은 괜찮은 키워드"만 기계적으로 걸러낸다.
브랜드/부적합 제거와 선정근거 작성은 Claude(스킬 본문)가 담당한다.

Usage:
  python keyword-filter.py <xlsx> [options]

Options:
  --max-products N    기본 상품수 컷 (default: 10000)
  --expand N          부족 시 확장 상품수 컷 (default: 20000)
  --min-count N       이 개수 미만이면 확장 발동 (default: 5)
  --top N             출력 상위 개수 (default: 10)
  --keep-info         정보성 키워드도 유지 (기본은 정보성 제외 = 쇼핑성만)
  --output <path>     후보 JSON 저장 경로 (미지정 시 stdout만)
"""

import argparse
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

try:
    import openpyxl
except ImportError:
    print("ERROR: openpyxl not installed. Run: pip install openpyxl>=3.1.0", file=sys.stderr)
    sys.exit(1)


# 아이템스카우트 헤더(한글) → 내부 키 매핑. 부분일치로 유연하게 잡는다.
COLUMN_ALIASES = {
    "keyword": ["키워드"],
    "category": ["대표 카테고리", "카테고리"],
    "classification": ["키워드 분류", "분류"],
    "total_search": ["총 검색수", "총검색수", "총 검색"],
    "product_count": ["상품수", "상품 수"],
    "competition": ["경쟁강도"],
}


def find_header_index(headers):
    """헤더 행에서 각 내부 키의 컬럼 인덱스를 찾는다. 정확일치 우선, 없으면 부분일치."""
    norm = [(str(h).strip() if h is not None else "") for h in headers]
    idx = {}
    for key, aliases in COLUMN_ALIASES.items():
        found = None
        # 정확 일치 우선 (긴 별칭부터)
        for alias in aliases:
            for i, h in enumerate(norm):
                if h == alias:
                    found = i
                    break
            if found is not None:
                break
        # 부분 일치 fallback
        if found is None:
            for alias in aliases:
                for i, h in enumerate(norm):
                    if alias in h:
                        found = i
                        break
                if found is not None:
                    break
        idx[key] = found
    return idx


def to_number(value):
    """'-', 콤마, 공백 섞인 셀을 정수로. 실패 시 None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip().replace(",", "")
    if s in ("", "-"):
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def is_informational(classification):
    """키워드 분류가 '정보성'이면 True."""
    if classification is None:
        return False
    return "정보" in str(classification)


def sanitize_part(s):
    """카테고리 조각을 파일명 안전 문자열로. 슬래시·공백·특수문자 제거."""
    s = str(s).strip()
    s = s.replace("/", "").replace("\\", "")
    s = re.sub(r'[<>:"|?*]', "", s)
    s = s.replace(" ", "")
    return s


def representative_category(idx, data):
    """대표 카테고리 컬럼에서 전체 행의 최빈(mode) 경로를 반환. 예: '생활/건강 > 청소용품 > 휴지통 > 다용도휴지통'."""
    ci = idx.get("category")
    if ci is None:
        return None
    paths = []
    for row in data:
        if ci < len(row) and row[ci] is not None and str(row[ci]).strip():
            paths.append(str(row[ci]).strip())
    if not paths:
        return None
    return Counter(paths).most_common(1)[0][0]


def suggested_filename(rep_category):
    """오늘날짜6자리_1차_2차_3차_4차 형식 파일명(확장자 제외)을 만든다."""
    ymd = date.today().strftime("%y%m%d")
    if not rep_category:
        return f"{ymd}_미분류"
    parts = [sanitize_part(p) for p in rep_category.split(">")]
    parts = [p for p in parts if p]
    return "_".join([ymd] + parts)


def load_rows(xlsx_path):
    """xlsx의 첫 시트를 읽어 헤더 인덱스와 데이터 행을 반환."""
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        return {}, []
    # 첫 번째 비어있지 않은 행을 헤더로
    header_row_idx = 0
    for i, r in enumerate(rows):
        if any(c is not None and str(c).strip() for c in r):
            header_row_idx = i
            break
    idx = find_header_index(rows[header_row_idx])
    data = rows[header_row_idx + 1:]
    return idx, data


def build_candidates(idx, data, max_products, exclude_info):
    """상품수 <= max_products 이고 (옵션) 정보성 제외한 후보 목록을 만든다."""
    if idx.get("keyword") is None or idx.get("product_count") is None:
        raise ValueError("필수 컬럼(키워드/상품수)을 찾지 못했습니다. 아이템스카우트 익스포트가 맞는지 확인하세요.")

    candidates = []
    for row in data:
        def cell(key):
            i = idx.get(key)
            return row[i] if (i is not None and i < len(row)) else None

        keyword = cell("keyword")
        if keyword is None or not str(keyword).strip():
            continue

        classification = cell("classification")
        if exclude_info and is_informational(classification):
            continue

        product_count = to_number(cell("product_count"))
        if product_count is None or product_count > max_products:
            continue

        candidates.append({
            "키워드": str(keyword).strip(),
            "대표카테고리": (str(cell("category")).strip() if cell("category") is not None else ""),
            "총검색수": to_number(cell("total_search")),
            "상품수": product_count,
            "분류": (str(classification).strip() if classification is not None else ""),
            "경쟁강도": cell("competition"),
        })
    return candidates


def main():
    parser = argparse.ArgumentParser(description="아이템스카우트 키워드 상품수 필터 (레퍼런스 없는 경우)")
    parser.add_argument("xlsx", help="아이템스카우트 익스포트 .xlsx 경로")
    parser.add_argument("--max-products", type=int, default=10000, help="기본 상품수 컷 (default: 10000)")
    parser.add_argument("--expand", type=int, default=20000, help="부족 시 확장 상품수 컷 (default: 20000)")
    parser.add_argument("--min-count", type=int, default=5, help="이 개수 미만이면 확장 (default: 5)")
    parser.add_argument("--top", type=int, default=10, help="출력 상위 개수 (default: 10)")
    parser.add_argument("--keep-info", action="store_true", help="정보성 키워드도 유지 (기본: 제외)")
    parser.add_argument("--output", help="후보 JSON 저장 경로")
    args = parser.parse_args()

    path = Path(args.xlsx)
    if not path.exists():
        print(f"ERROR: 파일을 찾을 수 없습니다: {path}", file=sys.stderr)
        sys.exit(1)

    exclude_info = not args.keep_info
    idx, data = load_rows(str(path))

    # 대표 카테고리 + 추천 파일명 (raw data 리네임/업로드용)
    rep_cat = representative_category(idx, data)
    new_name = suggested_filename(rep_cat)

    try:
        base = build_candidates(idx, data, args.max_products, exclude_info)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # 기본 컷 결과에 기준 태그
    for c in base:
        c["기준"] = f"상품수 {args.max_products // 10000}만 이하" if args.max_products % 10000 == 0 else f"상품수 {args.max_products} 이하"

    expanded_used = False
    if len(base) < args.min_count and args.expand > args.max_products:
        # 확장 컷: max~expand 구간을 추가 후보로
        expanded_all = build_candidates(idx, data, args.expand, exclude_info)
        base_keywords = {c["키워드"] for c in base}
        for c in expanded_all:
            if c["키워드"] not in base_keywords:
                c["기준"] = f"상품수 {args.expand // 10000}만 이하 확장" if args.expand % 10000 == 0 else f"상품수 {args.expand} 이하 확장"
                base.append(c)
        expanded_used = True

    # 상품수 오름차순 정렬 (적을수록 블루오션 우선)
    base.sort(key=lambda c: (c["상품수"] if c["상품수"] is not None else 10**12))
    result = base[:args.top]

    # 콘솔 표 출력
    print(f"# 입력: {path.name}")
    print(f"# 대표 카테고리: {rep_cat or '미확인'}")
    print(f"# 추천 파일명: {new_name}{path.suffix}")
    print(f"# 필터: 상품수 <= {args.max_products}" + (f" (부족 → {args.expand}까지 확장)" if expanded_used else ""))
    print(f"# 정보성 제외: {exclude_info} | 총 후보: {len(base)} | 출력: {len(result)}")
    print("-" * 72)
    print(f"{'키워드':<20} {'총검색수':>8} {'상품수':>8}  기준")
    print("-" * 72)
    for c in result:
        ts = c["총검색수"] if c["총검색수"] is not None else "-"
        print(f"{c['키워드']:<20} {str(ts):>8} {str(c['상품수']):>8}  {c['기준']}")
    print("-" * 72)
    print("※ 브랜드/부적합 키워드 제거와 선정근거 작성은 Claude가 이어서 판단합니다.")

    if args.output:
        out = Path(args.output)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"# JSON 저장: {out}")

    # 리네임 정보 (스킬이 raw data 업로드 시 파싱)
    print("###RENAME###")
    print(json.dumps({"suggested_filename": new_name + path.suffix,
                      "representative_category": rep_cat}, ensure_ascii=False))

    # stdout 마지막 줄에 machine-readable JSON (스킬이 파싱용으로 활용 가능)
    print("###JSON###")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
