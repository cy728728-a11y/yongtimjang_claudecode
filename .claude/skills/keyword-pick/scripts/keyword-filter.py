#!/usr/bin/env python3
"""아이템스카우트 키워드 익스포트(.xlsx) → 상품수 기준 후보 키워드 필터.

레퍼런스(상품 참조) 없이 "상품수 낮은 괜찮은 키워드"만 기계적으로 걸러낸다.
브랜드/부적합 제거와 선정근거 작성은 Claude(스킬 본문)가 담당한다.

Usage:
  python keyword-filter.py <xlsx> [options]

Options:
  --max-products N    기본 상품수 컷 (default: 10000)
  --expand N          부족 시 확장 상품수 컷 (default: 20000)
  --min-count N       이 개수 미만이면 확장 발동 (default: 6)
  --top N             출력 상위 개수 (default: 10)
  --keep-info         정보성 키워드도 유지 (기본은 정보성 제외 = 쇼핑성만)
  --output <path>     후보 JSON 저장 경로 (미지정 시 stdout만)
"""

import argparse
import json
import os
import sys
from pathlib import Path

# kwlib.py가 같은 폴더에 있으므로, 어느 경로에서 실행해도 import 가능하도록 경로 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kwlib import (
    build_candidates,
    load_rows,
    representative_category,
    suggested_filename,
)


def main():
    parser = argparse.ArgumentParser(description="아이템스카우트 키워드 상품수 필터 (레퍼런스 없는 경우)")
    parser.add_argument("xlsx", help="아이템스카우트 익스포트 .xlsx 경로")
    parser.add_argument("--max-products", type=int, default=10000, help="기본 상품수 컷 (default: 10000)")
    parser.add_argument("--expand", type=int, default=20000, help="부족 시 확장 상품수 컷 (default: 20000)")
    parser.add_argument("--min-count", type=int, default=6, help="이 개수 미만이면 확장 (default: 6)")
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
