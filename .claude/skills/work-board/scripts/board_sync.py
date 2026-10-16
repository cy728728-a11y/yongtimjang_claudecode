# -*- coding: utf-8 -*-
"""용팀장 업무판 '오늘' 탭 관리.

  sync     — 이룸 업무판 '오늘' 탭에서 용팀장 몫 행을 가져와 내 '오늘' 탭에 넣거나 갱신한다
  rollover — 날짜가 지난 행 정리: 완료(✓)·자동 보고 행은 '기록' 탭으로, 미완료는 오늘로 이월(+1)
  (둘 다 끝에 '오늘' 탭을 빈 줄 없이 다시 쓰고 체크박스를 실제 행에만 건다)

실행: .venv/bin/python3 .claude/skills/work-board/scripts/board_sync.py sync|rollover [--dry-run]
"""
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
KST = timezone(timedelta(hours=9))
HEADER = ["번호", "날짜", "✓", "할 일", "업무 #", "담당", "출처", "메모", "이월", "연동키"]
WIDTH = len(HEADER)
SRC_EROOM = "이룸 판"
SRC_AUTO = "자동"
MAX_ROWS = 500


def _load_eroomlib():
    """스크립트 위치에서 위로 올라가며 lib/eroomlib 를 찾아 sys.path 에 넣는다."""
    d = SCRIPT_DIR
    while d and d != os.path.dirname(d):
        lib = os.path.join(d, "lib")
        if os.path.isdir(os.path.join(lib, "eroomlib")):
            if lib not in sys.path:
                sys.path.insert(0, lib)
            return
        d = os.path.dirname(d)
    raise RuntimeError("eroomlib 를 찾지 못함")


# ---------------------------------------------------------------------------
# 순수 함수 (테스트 대상)
# ---------------------------------------------------------------------------
def pad(row, n=WIDTH):
    row = list(row or [])
    return (row + [""] * n)[:n]


def is_checked(v):
    return str(v).strip().upper() == "TRUE"


def is_mine(eroom_row):
    """이룸 '오늘' 행(번호,날짜,✓,할일,업무#,담당,예상,메모,이월)이 용팀장 몫인가."""
    r = pad(eroom_row, 9)
    return "용팀장" in r[5] or "용팀장" in r[3]


def eroom_key(eroom_row):
    """연동키 = 업무# + 할 일의 '—' 앞부분. 숫자가 바뀌어도 같은 행으로 본다."""
    r = pad(eroom_row, 9)
    head = r[3].split("—")[0].strip()
    return f"이룸|{r[4].strip()}|{head}"


def merge_eroom(mine, eroom_rows, today):
    """내 행 목록에 이룸 몫을 합친다. 반환 (새 목록, 추가수, 갱신수).

    - 같은 연동키가 있으면 할 일·메모를 최신으로 갱신, 이룸 쪽이 ✓ 면 내 것도 ✓.
      내 ✓ 는 이룸이 안 끝냈다고 되돌리지 않는다.
    - 없으면 새로 추가(출처 '이룸 판').
    """
    out = [pad(r) for r in mine]
    idx = {r[9]: i for i, r in enumerate(out) if r[9]}
    added = updated = 0
    for er in eroom_rows:
        if not is_mine(er):
            continue
        e = pad(er, 9)
        key = eroom_key(er)
        if key in idx:
            r = out[idx[key]]
            new = list(r)
            new[3], new[4], new[7] = e[3], e[4], e[7]
            if is_checked(e[2]):
                new[2] = "TRUE"
            if new != r:
                out[idx[key]] = new
                updated += 1
        else:
            out.append(["", today, "TRUE" if is_checked(e[2]) else "FALSE", e[3], e[4],
                        "용팀장", SRC_EROOM, e[7], "", key])
            idx[key] = len(out) - 1
            added += 1
    return out, added, updated


def rollover(mine, today):
    """날짜 지난 행 정리. 반환 (남길 행, 기록으로 보낼 행)."""
    keep, archive = [], []
    for r in (pad(x) for x in mine):
        if not r[3].strip():
            continue
        if r[1] >= today:
            keep.append(r)
        elif is_checked(r[2]) or r[6] == SRC_AUTO or r[3].startswith("[dry-run]"):
            archive.append(r)
        else:
            r = list(r)
            r[1] = today
            try:
                r[8] = str(int(r[8] or 0) + 1)
            except ValueError:
                r[8] = "1"
            keep.append(r)
    return keep, archive


def renumber(rows):
    out = []
    for i, r in enumerate((pad(x) for x in rows if pad(x)[3].strip()), 1):
        r = list(r)
        r[0] = str(i)
        r[2] = "TRUE" if is_checked(r[2]) else "FALSE"
        out.append(r)
    return out


# ---------------------------------------------------------------------------
# 시트 입출력
# ---------------------------------------------------------------------------
def _sheet_ids():
    _load_eroomlib()
    from eroomlib.config import cfg
    return cfg("sheets.work_board", required=True), cfg("sheets.eroom_board", required=True)


def _tab_id(gs, sid, tab):
    """탭 이름 → sheetId (sheets_tabs 는 이름만 주므로 직접 조회)."""
    import json
    d = gs._run_gws(["sheets", "spreadsheets", "get", "--params",
                     json.dumps({"spreadsheetId": sid, "fields": "sheets.properties(title,sheetId)"}),
                     "--format", "json"])
    for s in (d or {}).get("sheets") or []:
        p = s.get("properties", {})
        if p.get("title") == tab:
            return p.get("sheetId")
    return None


def write_today(gs, sid, rows):
    """'오늘' 탭을 빈 줄 없이 다시 쓰고, 체크박스는 실제 행에만 건다."""
    rows = renumber(rows)
    gs.sheets_clear(sid, f"'오늘'!A2:J{MAX_ROWS}")
    if rows:
        gs.sheets_update(sid, f"'오늘'!A2:J{len(rows) + 1}", rows, value_input="USER_ENTERED")
    gs.sheets_update(sid, "'오늘'!A1:J1", [HEADER])
    tab = _tab_id(gs, sid, "오늘")
    if tab is not None:
        # 체크박스 범위를 실제 행으로 한정 — 빈 줄에 FALSE 가 깔리면 append 가 맨 아래로 밀린다
        gs._run_gws(["sheets", "spreadsheets", "batchUpdate", "--params",
                     __import__("json").dumps({"spreadsheetId": sid})],
                    body={"requests": [
                        {"setDataValidation": {"range": {"sheetId": tab, "startRowIndex": 1,
                                                         "endRowIndex": MAX_ROWS, "startColumnIndex": 2,
                                                         "endColumnIndex": 3}}},
                        {"setDataValidation": {"range": {"sheetId": tab, "startRowIndex": 1,
                                                         "endRowIndex": len(rows) + 1,
                                                         "startColumnIndex": 2, "endColumnIndex": 3},
                                               "rule": {"condition": {"type": "BOOLEAN"}}}}]})
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description="용팀장 업무판 '오늘' 탭 연동·이월")
    ap.add_argument("cmd", choices=["sync", "rollover"])
    ap.add_argument("--dry-run", action="store_true", help="시트에 쓰지 않고 결과만 출력")
    args = ap.parse_args(argv)
    today = datetime.now(KST).strftime("%Y-%m-%d")
    try:
        my_id, eroom_id = _sheet_ids()
        from eroomlib import gsheets as gs
        mine = [r for r in gs.sheets_get(my_id, f"'오늘'!A2:J{MAX_ROWS}") if pad(r)[3].strip()]

        archive = []
        if args.cmd == "rollover":
            mine, archive = rollover(mine, today)
        eroom = gs.sheets_get(eroom_id, "'오늘'!A2:I200")
        mine, added, updated = merge_eroom(mine, eroom, today)

        msg = f"[board] {args.cmd} · 이룸 추가 {added} · 갱신 {updated} · 기록 이동 {len(archive)} · 남은 행 {len(mine)}"
        if args.dry_run:
            print(msg + " (dry-run)")
            return 0
        if archive:
            gs.append_rows(my_id, "기록", [pad(r)[:9] for r in archive])
        write_today(gs, my_id, mine)
        print(msg)
        return 0
    except Exception as e:
        print(f"[board] 실패: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
