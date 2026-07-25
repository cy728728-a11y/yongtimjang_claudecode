#!/usr/bin/env python3
"""카테고리교정_1번_용쌤1-1 로그 시트 준비.

- 카테고리교정 폴더에서 시트를 찾고, 없으면 생성(헤더 포함)
- A열(상품id)·B열(상품명)에 대상 100건 기록 (이미 있는 ID는 스킵)
- 새로 만들면 00_마스터-인덱스에 행 추가
사용: python setup_sheet.py <targets.json>
"""
import datetime
import json
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SKILL_SCRIPTS = r"C:\Users\workspace\.claude\skills\bulsaja-category-fix\scripts"
sys.path.insert(0, SKILL_SCRIPTS)

from gws_util import _run_gws, sheets_get, sheets_update  # noqa: E402

FOLDER = "1bVa3y725YCCSrOtx_bqBylBpvaXvwm2w"  # 카테고리교정/
MASTER = "1R4XdWohipaYeR-0QOAyRiVYZlk6iDofGONEBzSymGqs"  # 00_마스터-인덱스
NAME = "카테고리교정_1번_용쌤1-1"
HEADER = ["상품id", "상품명", "이전 카테고리", "변경 카테고리",
          "검색어(사용)", "확신도", "상태", "기록일"]


def main():
    with open(sys.argv[1], encoding="utf-8") as f:
        targets = json.load(f)

    # 1) 시트 찾기 (없으면 생성)
    q = f"'{FOLDER}' in parents and name = '{NAME}' and trashed = false"
    d = _run_gws(["drive", "files", "list",
                  "--params", json.dumps({"q": q}, ensure_ascii=False),
                  "--format", "json"])
    files = d.get("files", [])
    created = False
    if files:
        sid = files[0]["id"]
        print(f"기존 시트 사용: {sid}")
    else:
        d = _run_gws(["drive", "files", "create"],
                     body={"name": NAME,
                           "mimeType": "application/vnd.google-apps.spreadsheet",
                           "parents": [FOLDER]})
        sid = d["id"]
        created = True
        print(f"새 시트 생성: {sid}")

    # 2) 탭 이름 확인 (시트1 vs Sheet1)
    meta = _run_gws(["sheets", "spreadsheets", "get",
                     "--params", json.dumps({
                         "spreadsheetId": sid,
                         "fields": "sheets.properties.title"})])
    tab = meta["sheets"][0]["properties"]["title"]
    print(f"탭 이름: {tab}")

    if created:
        sheets_update(sid, f"{tab}!A1:H1", [HEADER])
        url = f"https://docs.google.com/spreadsheets/d/{sid}"
        today = datetime.date.today().isoformat()
        _run_gws(["sheets", "spreadsheets", "values", "append",
                  "--params", json.dumps({
                      "spreadsheetId": MASTER, "range": "A1",
                      "valueInputOption": "USER_ENTERED"})],
                 body={"values": [["1번_용쌤1-1", url, len(targets),
                                   "", "", "", today, "신규수집 100건 (용쌤 계정)"]]})
        print("마스터 인덱스에 행 추가")

    # 3) A·B열 채우기 (기존 ID 스킵)
    vals = sheets_get(sid, f"{tab}!A2:A")
    existing = {r[0].strip() for r in vals if r and r[0].strip()}
    new = [t for t in targets if t["productId"] not in existing]
    if new:
        start = 2 + len(vals)
        rows = [[t["productId"], t["상품명"]] for t in new]
        sheets_update(sid, f"{tab}!A{start}:B{start + len(rows) - 1}", rows)
        print(f"A/B열 {len(rows)}건 기록 (행 {start}~{start + len(rows) - 1})")
    else:
        print("A열 이미 채워짐 (신규 0건)")

    print(f"###SHEET### {sid} TAB={tab}")


if __name__ == "__main__":
    main()
