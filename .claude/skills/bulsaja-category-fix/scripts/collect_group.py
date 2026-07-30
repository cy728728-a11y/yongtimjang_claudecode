#!/usr/bin/env python3
"""마켓그룹 전체 상품(productId+상품명)을 페이지네이션으로 수집.

시트 A열 채우기 전용. bulsaja_market_group_products 를 대화 밖에서 페이징 호출해
전체 productId+상품명을 dump 한다(무거운 목록을 컨텍스트 안 태움).

사용:
  python collect_group.py --group-id 1001115 -o group.json
출력: [{"productId","상품명","상태코드"}]
"""
import argparse
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bulsaja_mcp import BulsajaMCP  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group-id", type=int, required=True)
    ap.add_argument("--output", "-o", required=True)
    ap.add_argument("--page-size", type=int, default=50)
    ap.add_argument("--sleep", type=float, default=0.3)
    args = ap.parse_args()

    mcp = BulsajaMCP()
    mcp.open()
    try:
        # 페이징 본체는 eroomlib.snapshot.ProductMCP 로 옮겼다(러너·다른 스킬도 쓴다).
        out = mcp.collect_group(args.group_id, page_size=args.page_size,
                                sleep=args.sleep,
                                log=lambda m: print(m, flush=True))
    finally:
        mcp.close()
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"###GROUP### {len(out)}건 -> {args.output}")


if __name__ == "__main__":
    main()
