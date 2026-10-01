# -*- coding: utf-8 -*-
"""gws CLI 로 구글 시트를 읽고 쓴다. JSON 은 셸 치환 없이 argv 로 넘긴다."""
import json
import shutil
import subprocess

import sheet_schema as S


class GwsError(Exception):
    pass


def _gws_runner(argv):
    """실제 gws 호출. 결과 JSON dict 를 돌려준다."""
    gws = shutil.which("gws")
    if not gws:
        raise GwsError("gws CLI 를 찾지 못했다")
    try:
        r = subprocess.run([gws, *argv, "--format", "json"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise GwsError(f"gws 실행 실패: {e}")
    if r.returncode != 0:
        # 인증 만료 등. 빈 응답을 {} 로 삼키면 '0행 추가' 성공처럼 보인다.
        raise GwsError(f"gws 종료코드 {r.returncode}: {((r.stdout or '') + (r.stderr or ''))[-300:]}")
    try:
        return json.loads(r.stdout or "{}")
    except ValueError:
        raise GwsError(f"gws 응답 파싱 실패: {((r.stdout or '') + (r.stderr or ''))[-300:]}")


def _col(i):
    """0-based 열 번호 → A1 열 문자."""
    s = ""
    i += 1
    while i:
        i, rem = divmod(i - 1, 26)
        s = chr(65 + rem) + s
    return s


class Sheet:
    def __init__(self, spreadsheet_id, runner=None):
        self.sid = spreadsheet_id
        self.run = runner or _gws_runner

    def _call(self, argv):
        out = self.run(argv)
        if isinstance(out, dict) and out.get("error"):
            raise GwsError(f"gws 오류: {out['error']}")
        return out

    @classmethod
    def create(cls, title, runner=None):
        """두 탭(카테고리스캔·후보)을 가진 새 스프레드시트 + 헤더."""
        run = runner or _gws_runner
        body = {"properties": {"title": title},
                "sheets": [{"properties": {"title": S.SCAN_TAB}}, {"properties": {"title": S.BENCH_TAB}}]}
        out = run(["sheets", "spreadsheets", "create", "--json", json.dumps(body, ensure_ascii=False)])
        if not isinstance(out, dict) or not out.get("spreadsheetId"):
            raise GwsError(f"스프레드시트 생성 실패: {out}")
        sh = cls(out["spreadsheetId"], runner=run)
        sh.append(S.SCAN_TAB, [S.SCAN_HEADER])
        sh.append(S.BENCH_TAB, [S.BENCH_HEADER])
        return sh

    def read(self, tab):
        """헤더를 뺀 전체 행."""
        p = {"spreadsheetId": self.sid, "range": f"{tab}!A:X"}
        out = self._call(["sheets", "spreadsheets", "values", "get",
                          "--params", json.dumps(p, ensure_ascii=False)])
        return (out.get("values") or [])[1:]

    def append(self, tab, rows):
        if not rows:
            return 0
        p = {"spreadsheetId": self.sid, "range": f"{tab}!A1",
             "valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"}
        out = self._call(["sheets", "spreadsheets", "values", "append",
                          "--params", json.dumps(p, ensure_ascii=False),
                          "--json", json.dumps({"values": rows}, ensure_ascii=False)])
        return int((out.get("updates") or {}).get("updatedRows", 0))

    def set_cell(self, tab, row_index, col_index, value):
        """row_index 는 헤더 제외 데이터 행 기준(0 = 시트 2행)."""
        rng = f"{tab}!{_col(col_index)}{row_index + 2}"
        p = {"spreadsheetId": self.sid, "range": rng, "valueInputOption": "USER_ENTERED"}
        self._call(["sheets", "spreadsheets", "values", "update",
                    "--params", json.dumps(p, ensure_ascii=False),
                    "--json", json.dumps({"values": [[value]]}, ensure_ascii=False)])
