#!/usr/bin/env python3
"""대상 상품 수집 — 마켓그룹 시트 A·B·G열을 읽어 '상태(G)가 빈 행'만 추린다.

시트 열: A=상품id B=상품명 C=이전카테고리 D=변경카테고리 E=검색어 F=확신도 G=상태 H=기록일
재개 안전: G열이 채워진 행은 이미 처리된 것 → 건너뛴다(--all 이면 전부).

출력 targets.json: [{"productId","상품명","row"}]  (row=1-based 시트 행번호)

사용법:
  python collect_targets.py --output targets.json
  python collect_targets.py --sheet <id> --tab 시트1 --all --output all.json
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
from gws_util import sheets_get  # noqa: E402
from eroomlib.config import cfg as _cfg  # noqa: E402

# 시트를 안 주면 쓰는 폴백. workspace.toml 로 뺐다(없으면 DEFAULTS = 현행 값).
DEFAULT_SHEET = _cfg("sheets.keyword_default")
DEFAULT_TAB = "시트1"


def collect(spreadsheet_id, tab, include_done=False):
    # A2:H (헤더 제외, 열려있는 범위) — 뒤쪽 빈 상태행까지 A열 기준으로 포함
    rows = sheets_get(spreadsheet_id, f"{tab}!A2:H")
    targets = []
    for idx, row in enumerate(rows):
        rownum = idx + 2  # 헤더가 1행
        pid = (row[0] if len(row) > 0 else "").strip()
        if not pid:
            continue
        name = (row[1] if len(row) > 1 else "").strip()
        status = (row[6] if len(row) > 6 else "").strip()
        if status and not include_done:
            continue  # 이미 처리됨 → 스킵
        targets.append({"productId": pid, "상품명": name, "row": rownum})
    return targets


def main():
    ap = argparse.ArgumentParser(description="카테고리 교정 대상 상품 수집")
    ap.add_argument("--sheet", default=DEFAULT_SHEET, help="spreadsheetId")
    ap.add_argument("--tab", default=DEFAULT_TAB, help="시트 탭 이름")
    ap.add_argument("--output", "-o", required=True, help="targets.json 저장 경로")
    ap.add_argument("--all", action="store_true", help="상태 채워진 행도 포함(재처리)")
    ap.add_argument("--limit", type=int, default=0, help="앞 N건만(청크). 0=전체")
    args = ap.parse_args()

    targets = collect(args.sheet, args.tab, include_done=args.all)
    if args.limit > 0:
        targets = targets[:args.limit]
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(targets, f, ensure_ascii=False, indent=2)
    print(f"###TARGETS### {len(targets)}건 -> {args.output}")
    if targets:
        print(f"  첫 행 {targets[0]['row']} ~ 끝 행 {targets[-1]['row']}")


if __name__ == "__main__":
    main()
