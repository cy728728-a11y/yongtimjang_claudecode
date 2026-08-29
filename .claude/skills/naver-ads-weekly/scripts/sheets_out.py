#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""구글시트 원장 기록 — gws CLI 를 subprocess 로 부른다.

탭 구성: 00_총괄 / ①노출0 / ②썸네일교체 / ③원인분석 / ④효자후보 / ⑤효자확정 / 이력
회차마다 append 한다 — 덮어쓰면 과거 회차를 잃는다.
"""
import json
import subprocess

# 규칙별 열 정의 (헤더, 접근키)
COLS = {
    "①노출0": [("회차", None), ("계정", None), ("상품", "title"), ("광고그룹", "adGroup"),
               ("현재입찰", "bid"), ("그룹입찰따름", "useGroupBid"), ("소재ID", "adId")],
    "②썸네일교체": [("회차", None), ("계정", None), ("상품", "title"), ("노출", "imp"), ("클릭", "clk"),
                 ("CTR %", "ctr"), ("순위", "rank"), ("스토어상품ID", "mallProductId"), ("소재ID", "adId")],
    "③원인분석": [("회차", None), ("계정", None), ("상품", "title"), ("노출", "imp"), ("클릭", "clk"),
                ("CTR %", "ctr"), ("광고비", "cost"), ("스토어상품ID", "mallProductId")],
    "④효자후보": [("회차", None), ("계정", None), ("상품", "title"), ("노출", "imp"), ("CTR %", "ctr"),
                ("순위", "rank"), ("스토어상품ID", "mallProductId")],
    "⑤효자확정": [("회차", None), ("계정", None), ("상품", "title"), ("구매수", "purCnt"),
                ("구매매출", "purAmt"), ("광고비", "cost"), ("스토어상품ID", "mallProductId")],
}


def rows_for(rule_name, rows, alias, generated):
    """규칙 1개를 시트 행 목록으로 바꾼다. 첫 두 열은 회차·계정이다."""
    cols = COLS.get(rule_name)
    if not cols:
        return []
    out = []
    for r in rows:
        line = []
        for _, key in cols:
            if key is None:
                line.append(generated if not line else alias)
            else:
                v = r.get(key, "")
                line.append("" if v is None else v)
        out.append(line)
    return out


def _gws(args_json, service="sheets", resource="spreadsheets.values", method="append"):
    """gws CLI 호출. 실패해도 배치를 죽이지 않는다."""
    cmd = ["gws", service, *resource.split("."), method, "--params", json.dumps(args_json, ensure_ascii=False)]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if p.returncode != 0:
            return False, (p.stderr or p.stdout)[:300]
        return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def write_sheet(sheet_id, result, log=print):
    """전 계정·전 규칙을 각 탭에 append 한다."""
    generated = result.get("generated", "")
    for rule_name, cols in COLS.items():
        all_rows = []
        for alias, v in result.get("accounts", {}).items():
            all_rows.extend(rows_for(rule_name, v["rules"].get(rule_name, []), alias, generated))
        if not all_rows:
            continue
        ok, err = _gws({
            "spreadsheetId": sheet_id,
            "range": f"{rule_name}!A1",
            "valueInputOption": "USER_ENTERED",
            "insertDataOption": "INSERT_ROWS",
            "body": {"values": all_rows},
        })
        log(f"  {rule_name:<12} {len(all_rows):>4}행 {'✓' if ok else '✗ ' + err}")
