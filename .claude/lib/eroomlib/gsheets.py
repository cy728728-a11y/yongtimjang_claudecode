#!/usr/bin/env python3
"""gws CLI(Google Workspace) 얇은 래퍼 — 시트 읽기/쓰기.

계정은 chloe91727 (gws 인증 계정). 요청 바디는 --json, 쿼리는 --params.
gws 출력의 첫 줄 'Using keyring backend: keyring' 같은 잡음은 걸러 JSON만 파싱.

(구 bulsaja-category-fix/scripts/gws_util.py 를 eroomlib 로 승격. 동작 동일.)
"""
import json
import os
import shutil
import subprocess
import sys
import time

# gws 는 npm 전역 셔임(gws.CMD). 이 .CMD 를 subprocess 로 돌리면 npm 셔임이
# 인자를 cmd.exe 의 %* 로 재전개하는데, 이때 카테고리 경로의 '>' 가 파일
# 리다이렉트로 해석돼 gws 가 깨진다. 그래서 셔임이 부르는 node 스크립트
# (run.js)를 node 로 직접 호출해 cmd.exe 를 완전히 우회한다.
_GWS_SHIM = shutil.which("gws") or "gws"


def _resolve_gws_cmd():
    """[node, run.js] 형태(권장) 또는 셔임 경로를 프리픽스로 반환."""
    shim = _GWS_SHIM
    if shim and shim.lower().endswith((".cmd", ".bat")):
        npm_dir = os.path.dirname(shim)
        run_js = os.path.join(npm_dir, "node_modules", "@googleworkspace",
                              "cli", "run.js")
        node = shutil.which("node")
        if node and os.path.exists(run_js):
            return [node, run_js]
    return [shim]  # 폴백(‘>’ 없는 데이터에서만 안전)


_GWS_CMD = _resolve_gws_cmd()


def _run_gws(args, body=None):
    """gws 명령 실행 → stdout 에서 JSON 부분만 파싱해 반환."""
    cmd = list(_GWS_CMD) + args
    if body is not None:
        cmd += ["--json", json.dumps(body, ensure_ascii=False)]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    out = proc.stdout or ""
    # JSON 시작({ 또는 [)부터 파싱
    start = min([i for i in (out.find("{"), out.find("[")) if i >= 0] or [-1])
    if start < 0:
        raise RuntimeError(f"gws JSON 응답 없음 (exit {proc.returncode}): "
                           f"{(proc.stderr or out)[:300]}")
    data = json.loads(out[start:])
    # gws 는 API 오류도 exit 0 + JSON 으로 돌려준다. 이걸 그대로 반환하면
    # 실패한 쓰기가 **성공으로 보인다**(2026-07-28: 매트릭스 4개 그룹에서 수만 칸이
    # 조용히 유실됨 — 'Range exceeds grid limits' 가 삼켜졌다). 반드시 예외로 올린다.
    if isinstance(data, dict) and isinstance(data.get("error"), dict):
        err = data["error"]
        raise RuntimeError(
            f"gws API 오류 {err.get('code')}: {str(err.get('message'))[:300]}")
    return data


def _with_retry(fn, what, max_retries=4):
    """429/쿼터 초과만 지수 백오프(2·4·8·16초) 재시도. 그 밖의 오류는 즉시 올린다."""
    last = None
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            msg = str(e)
            last = e
            if any(h.lower() in msg.lower() for h in _RETRY_HINTS) and attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"[gsheets] {what} 429/쿼터, {wait}초 대기 후 재시도 "
                      f"({attempt + 1}/{max_retries})", file=sys.stderr)
                time.sleep(wait)
                continue
            raise
    raise RuntimeError(f"{what} 최대 재시도 초과: {last}")


def sheets_get(spreadsheet_id, rng, max_retries=4):
    """range 값 2차원 배열 반환(없으면 []).

    읽기도 분당 쿼터가 있다 — 그룹 수십 개를 훑으면 걸린다. 쓰기와 같이 백오프한다.
    """
    d = _with_retry(lambda: _run_gws(
        ["sheets", "spreadsheets", "values", "get",
         "--params", json.dumps({"spreadsheetId": spreadsheet_id, "range": rng}),
         "--format", "json"]), f"get({rng})", max_retries)
    return d.get("values", [])


def sheets_update(spreadsheet_id, rng, values_2d, value_input="RAW", max_retries=4):
    """range 에 2차원 배열 기록(update, append 아님).

    쓰기 쿼터(분당 60회)에 걸리면 429 가 나온다 — append_rows 와 같은 백오프를 둔다.
    (매트릭스처럼 열을 여러 청크로 연달아 쓰면 쉽게 걸린다.)
    """
    args = ["sheets", "spreadsheets", "values", "update",
            "--params", json.dumps({"spreadsheetId": spreadsheet_id,
                                    "range": rng,
                                    "valueInputOption": value_input})]
    last_err = None
    for attempt in range(max_retries):
        try:
            return _run_gws(args, body={"values": values_2d})
        except Exception as e:
            msg = str(e)
            last_err = e
            if any(h.lower() in msg.lower() for h in _RETRY_HINTS) and attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"[gsheets] update 429/쿼터 오류, {wait}초 대기 후 재시도 "
                      f"({attempt + 1}/{max_retries}): {msg[:150]}", file=sys.stderr)
                time.sleep(wait)
                continue
            raise
    raise RuntimeError(f"sheets_update 최대 재시도 초과({rng}): {last_err}")


def chunk_by_size(rows, budget=12000):
    """행 목록을 **실제 JSON 길이** 기준으로 끊어 순서대로 내준다.

    gws 는 요청 바디를 명령줄 인자로 넘기는데 윈도우 CreateProcess 상한이 32,767자다.
    행 길이가 제각각이라(상품명 20자~100자) 개수로 끊으면 긴 이름이 몰린 구간에서만
    터진다 — 길이로 끊어야 한다. 반환: (시작 인덱스, 행들) 순서쌍.
    """
    cur, size, start = [], 0, 0
    for i, r in enumerate(rows):
        n = len(json.dumps(r, ensure_ascii=False)) + 1
        if cur and size + n > budget:
            yield start, cur
            cur, size, start = [], 0, i
        cur.append(r)
        size += n
    if cur:
        yield start, cur


# 429/쿼터 초과로 판단할 오류 메시지 키워드
_RETRY_HINTS = ("429", "quota", "RESOURCE_EXHAUSTED", "rateLimitExceeded")


def append_rows(spreadsheet_id, tab, rows, max_retries=4):
    """rows(2차원 리스트)를 탭 끝에 append (USER_ENTERED, INSERT_ROWS).

    429/쿼터 초과 오류는 지수 백오프(2·4·8·16초) 후 최대 max_retries 회 재시도.
    그 외 오류(4xx 등)는 즉시 예외를 올린다.
    rows 가 크면 그대로 한 호출로 보낸다 — 청크 분할은 호출자 책임.

    반환: 추가된 행수(len(rows)). 실패 시 RuntimeError.
    (구 keyword-pick/scripts/sheet_io.py 에서 승격 — 스킬 2개 이상이 쓴다.)
    """
    if not rows:
        return 0

    args = [
        "sheets", "spreadsheets", "values", "append",
        "--params", json.dumps({
            "spreadsheetId": spreadsheet_id,
            "range": f"'{tab}'!A1",
            "valueInputOption": "USER_ENTERED",
            "insertDataOption": "INSERT_ROWS",
        }, ensure_ascii=False),
    ]
    body = {"values": rows}

    last_err = None
    for attempt in range(max_retries):
        try:
            _run_gws(args, body=body)
            return len(rows)
        except Exception as e:
            msg = str(e)
            last_err = e
            if any(h.lower() in msg.lower() for h in _RETRY_HINTS) and attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"[gsheets] append 429/쿼터 오류, {wait}초 대기 후 재시도 "
                      f"({attempt + 1}/{max_retries}): {msg[:150]}", file=sys.stderr)
                time.sleep(wait)
                continue
            raise RuntimeError(f"append_rows 실패(tab={tab}, {len(rows)}행): {msg}")
    raise RuntimeError(f"append_rows 최대 재시도 초과(tab={tab}): {last_err}")


def ensure_tab(spreadsheet_id, tab, header):
    """탭이 없으면 addSheet + 헤더(1행) 기록.

    탭이 이미 있으면 **헤더 뒤에 열이 늘어난 경우에만** 꼬리를 이어 쓴다.
    기존 헤더가 새 헤더의 접두사일 때로 한정한다 — 중간에 열을 끼워 넣으면 이미 쌓인
    행의 값이 통째로 밀리므로, 그건 사람이 손으로 판단할 일이지 스크립트가 할 일이 아니다.
    반환: 탭을 새로 만들었으면 True.
    """
    try:
        meta = _run_gws(["sheets", "spreadsheets", "get",
                         "--params", json.dumps({"spreadsheetId": spreadsheet_id})])
    except Exception as e:
        raise RuntimeError(f"ensure_tab 실패(메타 조회): {e}")

    existing = {s["properties"]["title"] for s in meta.get("sheets", [])}
    if tab in existing:
        want = list(header)
        try:
            got = (sheets_get(spreadsheet_id, f"'{tab}'!1:1") or [[]])[0]
        except Exception:
            return False
        got = [str(c) for c in got]
        if got and len(got) < len(want) and want[:len(got)] == got:
            sheets_update(spreadsheet_id, f"'{tab}'!A1", [want])
            print(f"[gsheets] '{tab}' 헤더 확장: +{want[len(got):]}")
        return False  # 이미 존재

    try:
        _run_gws(["sheets", "spreadsheets", "batchUpdate",
                  "--params", json.dumps({"spreadsheetId": spreadsheet_id})],
                 body={"requests": [{"addSheet": {"properties": {"title": tab}}}]})
        _run_gws(["sheets", "spreadsheets", "values", "update",
                  "--params", json.dumps({"spreadsheetId": spreadsheet_id,
                                          "range": f"'{tab}'!A1",
                                          "valueInputOption": "RAW"})],
                 body={"values": [list(header)]})
    except Exception as e:
        raise RuntimeError(f"ensure_tab 실패(탭 생성, tab={tab}): {e}")
    return True


if __name__ == "__main__":
    # 스모크 테스트: python -m eroomlib.gsheets <spreadsheetId> <range>
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    vals = sheets_get(sys.argv[1], sys.argv[2])
    print(f"{len(vals)} rows")
    for r in vals[:5]:
        print(r)
