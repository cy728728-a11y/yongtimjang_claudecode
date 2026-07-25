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
    return json.loads(out[start:])


def sheets_get(spreadsheet_id, rng):
    """range 값 2차원 배열 반환(없으면 [])."""
    d = _run_gws(["sheets", "spreadsheets", "values", "get",
                  "--params", json.dumps({"spreadsheetId": spreadsheet_id,
                                          "range": rng}),
                  "--format", "json"])
    return d.get("values", [])


def sheets_update(spreadsheet_id, rng, values_2d, value_input="RAW"):
    """range 에 2차원 배열 기록(update, append 아님)."""
    return _run_gws(["sheets", "spreadsheets", "values", "update",
                     "--params", json.dumps({"spreadsheetId": spreadsheet_id,
                                             "range": rng,
                                             "valueInputOption": value_input})],
                    body={"values": values_2d})


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
