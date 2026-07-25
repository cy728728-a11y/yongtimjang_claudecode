#!/usr/bin/env python3
"""구글시트 건건 기록(체크포인트) — 상품 1건 처리 끝날 때마다 그 행 B:K 를 update.

append 아님: A열 productId 는 이미 있으므로 B{row}:K{row} 만 덮어쓴다.
열: B=상품명 C=이전카테고리 D=변경카테고리 E=검색어 F=확신도 G=상태 H=기록일
    I=위험/근접플래그 J=실물판정 K=썸네일URL

J·K 는 2026-07-24 추가. 썸네일·원문명·옵션명으로 판정한 '실물 정체'와 그 근거 이미지를
남겨, 후속 `product-name` 스킬이 같은 시트에서 읽어 쓰도록 한다(썸네일 재판독 생략).

decision dict(apply 산출) → 시트 행 매핑:
  상품명 / 기존카테고리 / 변경카테고리 / 검색어 / 확신도 / 상태 / (오늘) / 위험 / 실물판정 / 썸네일
"""
import argparse
import datetime
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gws_util import sheets_update  # noqa: E402

DEFAULT_SHEET = "1DbR2upLX_DXjgjXpGPdide2SUifli_X6DTqhUTr9Syk"
DEFAULT_TAB = "시트1"


def _today():
    return datetime.date.today().isoformat()


class SheetLogger:
    def __init__(self, spreadsheet_id=DEFAULT_SHEET, tab=DEFAULT_TAB):
        self.sid = spreadsheet_id
        self.tab = tab

    def update_row(self, row, d):
        """decision dict d 를 B{row}:K{row} 에 기록."""
        conf = str(d.get("확신도", "")).strip()
        if conf and not conf.endswith("%"):
            conf = conf.rstrip("0").rstrip(".") + "%" if "." in conf else conf + "%"
        thumb = d.get("썸네일", "")
        if isinstance(thumb, list):  # workdata 원본은 리스트 — 대표 1장만
            thumb = thumb[0] if thumb else ""
        values = [[
            d.get("상품명", ""),
            d.get("기존카테고리", ""),
            d.get("변경카테고리", ""),
            d.get("검색어", ""),
            conf,
            d.get("상태", ""),
            _today(),
            d.get("위험", ""),      # I열: 대분류변경 등 위험 플래그
            d.get("실물판정", ""),   # J열: 증거 4종으로 판정한 실물 정체
            thumb,                  # K열: 판정 근거 대표 썸네일 URL
        ]]
        rng = f"{self.tab}!B{row}:K{row}"
        return sheets_update(self.sid, rng, values)


def main():
    ap = argparse.ArgumentParser(description="시트 건건 기록(테스트/일괄)")
    ap.add_argument("--sheet", default=DEFAULT_SHEET)
    ap.add_argument("--tab", default=DEFAULT_TAB)
    ap.add_argument("--decisions", "-i", required=True, help="decisions.json 일괄 기록")
    args = ap.parse_args()

    with open(args.decisions, encoding="utf-8") as f:
        decisions = json.load(f)
    logger = SheetLogger(args.sheet, args.tab)
    n = 0
    for d in decisions:
        if d.get("row"):
            logger.update_row(d["row"], d)
            n += 1
    print(f"###SHEET### {n}건 기록")


if __name__ == "__main__":
    main()
