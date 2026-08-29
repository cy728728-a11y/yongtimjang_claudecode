#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""구글시트 원장 기록 — gws CLI 를 subprocess 로 부른다.

탭 구성: ①노출0 / ②썸네일교체 / ③원인분석 / ④효자후보 / ⑤효자확정 (규칙 5개)
회차마다 append 한다 — 덮어쓰면 과거 회차를 잃는다.
"""
import json
import subprocess

# 모든 탭의 앞 두 열은 회차·계정으로 고정한다. 코드가 붙이지 데이터가 정하지 않는다
PREFIX = ("회차", "계정")

# 한 번에 보내는 행 수 — gws 는 CLI 인자로 받으므로 OS 인자 길이 상한에 걸린다.
# 실측(계정 4개·3,078소재)에서 한 탭이 711KB 였고 이 기계의 ARG_MAX 는 1MB 였다.
CHUNK = 500

# 규칙별 열 정의 (헤더, 접근키) — PREFIX 뒤에 붙는 것들만 적는다
COLS = {
    "①노출0": [("상품", "title"), ("광고그룹", "adGroup"),
               ("현재입찰", "bid"), ("그룹입찰따름", "useGroupBid"), ("소재ID", "adId")],
    "②썸네일교체": [("상품", "title"), ("노출", "imp"), ("클릭", "clk"),
                 ("CTR %", "ctr"), ("순위", "rank"), ("스토어상품ID", "mallProductId"), ("소재ID", "adId")],
    "③원인분석": [("상품", "title"), ("노출", "imp"), ("클릭", "clk"),
                ("CTR %", "ctr"), ("광고비", "cost"), ("스토어상품ID", "mallProductId")],
    "④효자후보": [("상품", "title"), ("노출", "imp"), ("CTR %", "ctr"),
                ("순위", "rank"), ("스토어상품ID", "mallProductId")],
    "⑤효자확정": [("상품", "title"), ("구매수", "purCnt"),
                ("구매매출", "purAmt"), ("광고비", "cost"), ("스토어상품ID", "mallProductId")],
}


def rows_for(rule_name, rows, alias, generated):
    """규칙 1개를 시트 행 목록으로 바꾼다. 회차·계정을 앞에 고정으로 붙인다.

    앞 두 값을 '지금까지 채운 게 없으면 회차' 식으로 판단하지 않는다 —
    그렇게 하면 COLS 순서를 한 번만 바꿔도 회차가 사라지고 계정이 중복되는데,
    append 전용 시트라 실패하지 않고 틀린 행이 조용히 쌓인다.
    """
    cols = COLS.get(rule_name)
    if not cols:
        return []
    out = []
    for r in rows:
        line = [generated, alias]
        for _, key in cols:
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
    """전 계정·전 규칙을 각 탭에 append 한다. CHUNK 행씩 나눠 보낸다."""
    generated = result.get("generated", "")
    for rule_name in COLS:
        all_rows = []
        for alias, v in result.get("accounts", {}).items():
            rules = v.get("rules") or {}          # ③ KeyError 방지
            all_rows.extend(rows_for(rule_name, rules.get(rule_name, []), alias, generated))
        if not all_rows:
            continue
        sent = fail = 0
        for i in range(0, len(all_rows), CHUNK):
            batch = all_rows[i:i + CHUNK]
            ok, err = _gws({
                "spreadsheetId": sheet_id,
                "range": f"{rule_name}!A1",
                "valueInputOption": "USER_ENTERED",
                "insertDataOption": "INSERT_ROWS",
                "body": {"values": batch},
            })
            if ok:
                sent += len(batch)
            else:
                fail += len(batch)
                log(f"    {rule_name} {i}~{i + len(batch)} 실패: {err}")
        mark = "OK" if not fail else f"실패 {fail}행"
        log(f"  {rule_name:<12} {sent:>5}행 기록 {mark}")
