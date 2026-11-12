# -*- coding: utf-8 -*-
"""정인호 고객 구매정산시트에 마켓별 최근 등록 상품을 채운다.

사용법 (워크스페이스 루트에서):
  .venv/bin/python3 .claude/skills/jeonginho-sheet/scripts/jeonginho_sheet.py add 4-1 5-2
  .venv/bin/python3 .claude/skills/jeonginho-sheet/scripts/jeonginho_sheet.py remove 2-3
  .venv/bin/python3 .claude/skills/jeonginho-sheet/scripts/jeonginho_sheet.py reset 1-3 2-2
  .venv/bin/python3 .claude/skills/jeonginho-sheet/scripts/jeonginho_sheet.py count 1-1 4-1   # 시트는 안 건드리고 건수만
  옵션: --days 30 (기본 30일) · --dry-run

- add    : 시트 맨 아래(마지막 채워진 행 다음)에 이어 붙인다. 시트에 이미 있는 판매자상품코드는 건너뛴다.
- remove : 그 마켓의 행을 통째로 지운다(행 삭제라 고객이 적어 둔 다른 칸도 같이 빠진다).
- reset  : 5행부터 아래 A~D 를 비우고 새로 쓴다.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

SHEET_ID = "11bk9FvZWtKk8gD-IR7fxZt5IGWryYKBtuy1Cz1RLakQ"
TAB = "구매정산"
TAB_GID = 1802319683
START_ROW = 5  # 1행 제목, 2~3행 요약, 4행 빈칸 → 5행부터 상품
STORES_JSON = os.path.expanduser("~/.eroom/naver-commerce-stores.json")
SKILLS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
COMMERCE_BASE = "https://api.commerce.naver.com/external"
KST = timezone(timedelta(hours=9))


# ---------- 구글시트 (gws) ----------
def gws(args, body=None):
    """gws 호출 → JSON. 실패하면 예외."""
    cmd = ["gws"] + args
    if body is not None:
        cmd += ["--json", json.dumps(body, ensure_ascii=False)]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd="/tmp")
    out = r.stdout.strip()
    if r.returncode != 0:
        raise RuntimeError(f"gws 실패: {(r.stderr or out)[:300]}")
    i = out.find("{")
    return json.loads(out[i:]) if i >= 0 else {}


def read_rows():
    """5행부터 A~D 읽기 → [(행번호, [마켓, 등록일, 코드, 상품명]), ...] (빈 줄 포함, 마지막 채워진 줄까지)"""
    d = gws(["sheets", "spreadsheets", "values", "get", "--params",
             json.dumps({"spreadsheetId": SHEET_ID, "range": f"{TAB}!A{START_ROW}:D"})])
    vals = d.get("values", [])
    return [(START_ROW + i, r) for i, r in enumerate(vals)]


def grid_rows():
    d = gws(["sheets", "spreadsheets", "get", "--params",
             json.dumps({"spreadsheetId": SHEET_ID, "fields": "sheets.properties(sheetId,gridProperties.rowCount)"})])
    for s in d["sheets"]:
        if s["properties"]["sheetId"] == TAB_GID:
            return s["properties"]["gridProperties"]["rowCount"]
    raise RuntimeError("구매정산 탭을 못 찾음")


def batch(requests_):
    return gws(["sheets", "spreadsheets", "batchUpdate", "--params", json.dumps({"spreadsheetId": SHEET_ID})],
               {"requests": requests_})


def ensure_rows(last_row):
    """last_row 까지 쓸 수 있게 행을 늘린다."""
    have = grid_rows()
    if last_row > have:
        batch([{"appendDimension": {"sheetId": TAB_GID, "dimension": "ROWS", "length": last_row - have + 20}}])


def write(start_row, values):
    end = start_row + len(values) - 1
    ensure_rows(end)
    gws(["sheets", "spreadsheets", "values", "update", "--params",
         json.dumps({"spreadsheetId": SHEET_ID, "range": f"{TAB}!A{start_row}:D{end}",
                     "valueInputOption": "USER_ENTERED"})], {"values": values})
    return end


# ---------- 커머스 연동 ----------
def issue_token(store):
    p = os.path.join(SKILLS_DIR, "naver-ads-thumbnail", "scripts")
    if p not in sys.path:
        sys.path.insert(0, p)
    from verify_creds import issue_token as _issue
    return _issue(store["client_id"], store["client_secret"])


def fetch_recent(market, store, days):
    """최근 days 일 안에 등록한 상품 → 시트용 행 목록 (최근 등록이 위)."""
    import requests
    tok, err = issue_token(store)
    if not tok:
        raise RuntimeError(f"토큰 실패: {str(err)[:150]}")
    h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    today = datetime.now(KST).date()
    frm = today - timedelta(days=days)
    rows, page = [], 1
    while True:
        body = {"page": page, "size": 500, "periodType": "PROD_REG_DAY",
                "fromDate": frm.isoformat(), "toDate": today.isoformat(), "orderType": "REG_DATE"}
        r = None
        for t in range(5):
            r = requests.post(f"{COMMERCE_BASE}/v1/products/search", headers=h, json=body, timeout=60)
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(2 * (t + 1))
                continue
            break
        if r.status_code >= 400:
            raise RuntimeError(f"상품 검색 실패 HTTP {r.status_code} {r.text[:200]}")
        d = r.json()
        for e in d.get("contents") or []:
            for c in e.get("channelProducts") or []:
                if c.get("statusType") == "PROHIBITION":  # 판매금지는 뺀다
                    continue
                rows.append(c)
        if page >= (d.get("totalPages") or 1):
            break
        page += 1
        time.sleep(0.3)
    out = []
    for c in sorted(rows, key=lambda x: x.get("regDate", ""), reverse=True):
        day, hm = c["regDate"][:16].split("T")
        hh, mm = hm.split(":")
        out.append([store["name"], f"{day} {int(hh)}:{mm}", c.get("sellerManagementCode", ""), c.get("name", "")])
    return out


def load_stores():
    with open(STORES_JSON, encoding="utf-8") as f:
        return json.load(f)


# ---------- 명령 ----------
def collect(markets, days):
    stores = load_stores()
    result = {}
    for m in markets:
        if m not in stores:
            print(f"[건너뜀] {m}: 커머스 키 없음")
            continue
        try:
            rows = fetch_recent(m, stores[m], days)
            result[m] = rows
            print(f"{m} {stores[m]['name']}: {len(rows)}개")
        except Exception as e:
            print(f"[실패] {m} {stores[m].get('name')}: {e}")
    return result


def cmd_add(markets, days, dry):
    existing = read_rows()
    codes = {r[2] for _, r in existing if len(r) > 2 and r[2]}
    last = max([n for n, r in existing if any(r)], default=START_ROW - 1)
    new = []
    for m, rows in collect(markets, days).items():
        keep = [r for r in rows if r[2] not in codes]
        if len(keep) < len(rows):
            print(f"  {m}: 이미 시트에 있는 {len(rows) - len(keep)}개 건너뜀")
        new += keep
        codes |= {r[2] for r in keep}
    if not new:
        print("추가할 상품 없음")
        return
    if dry:
        print(f"[미리보기] {last + 1}행부터 {len(new)}개 추가 예정")
        return
    end = write(last + 1, new)
    print(f"완료: {last + 1}~{end}행에 {len(new)}개 추가")


def cmd_remove(markets, dry):
    stores = load_stores()
    names = {stores[m]["name"] for m in markets if m in stores}
    rows = [n for n, r in read_rows() if r and r[0] in names]
    if not rows:
        print("지울 행 없음")
        return
    print(f"{', '.join(sorted(names))}: {len(rows)}행 삭제" + (" 예정(미리보기)" if dry else ""))
    if dry:
        return
    # 아래 행부터 연속 구간 단위로 지운다(위부터 지우면 번호가 밀린다)
    spans, s = [], None
    for n in sorted(rows):
        if s and n == s[1] + 1:
            s[1] = n
        else:
            s = [n, n]
            spans.append(s)
    reqs = [{"deleteDimension": {"range": {"sheetId": TAB_GID, "dimension": "ROWS",
                                           "startIndex": a - 1, "endIndex": b}}} for a, b in reversed(spans)]
    batch(reqs)
    print("완료")


def cmd_reset(markets, days, dry):
    new = []
    for rows in collect(markets, days).values():
        new += rows
    existing = read_rows()
    last = max([n for n, r in existing if any(r)], default=START_ROW)
    if dry:
        print(f"[미리보기] {START_ROW}~{last}행 A~D 비우고 {len(new)}개 새로 씀")
        return
    if not new:
        print("가져온 상품이 없어 시트를 건드리지 않음")
        return
    gws(["sheets", "spreadsheets", "values", "clear", "--params",
         json.dumps({"spreadsheetId": SHEET_ID, "range": f"{TAB}!A{START_ROW}:D{max(last, START_ROW)}"})])
    end = write(START_ROW, new)
    print(f"완료: {START_ROW}~{end}행에 {len(new)}개 새로 씀")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["add", "remove", "reset", "count"])
    ap.add_argument("markets", nargs="+", help="마켓 번호 (예: 1-3 2-2)")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    try:
        if a.cmd == "add":
            cmd_add(a.markets, a.days, a.dry_run)
        elif a.cmd == "remove":
            cmd_remove(a.markets, a.dry_run)
        elif a.cmd == "reset":
            cmd_reset(a.markets, a.days, a.dry_run)
        else:
            collect(a.markets, a.days)
    except Exception as e:
        print(f"[오류] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
