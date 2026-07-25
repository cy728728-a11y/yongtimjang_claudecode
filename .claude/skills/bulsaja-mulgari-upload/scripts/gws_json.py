# -*- coding: utf-8 -*-
# gws CLI를 셸 명령어 치환($(cat ...)) 없이 호출하는 래퍼.
# JSON body를 파일에서 직접 읽어 subprocess(shell=False)로 넘김 → bash 정적 분석/화이트리스트 가능.
# 사용:
#   python gws_json.py append      <spreadsheetId> <body.json> [range(기본 물갈이로그!A1)]
#   python gws_json.py batchupdate <spreadsheetId> <body.json>
import sys, json, re, subprocess, shutil

try:
    mode = sys.argv[1]
    sid = sys.argv[2]
    body_file = sys.argv[3]
    rng = sys.argv[4] if len(sys.argv) > 4 else u"물갈이로그!A1"  # 물갈이로그!A1

    with open(body_file, encoding="utf-8") as f:
        body = f.read()

    # Windows: gws.cmd는 cmd.exe 경유라 명령줄 8KB 제한에 걸림 → node로 JS 엔트리 직접 실행
    import os
    gws_cmd = shutil.which("gws.cmd") or shutil.which("gws")
    if not gws_cmd:
        sys.stderr.write("ERR: gws CLI not found\n"); sys.exit(1)
    run_js = os.path.join(os.path.dirname(gws_cmd), "node_modules", "@googleworkspace", "cli", "run.js")
    node = shutil.which("node") or shutil.which("node.exe")
    if os.path.exists(run_js) and node:
        gws = [node, run_js]
    else:
        gws = [gws_cmd]

    if mode == "append":
        params = json.dumps({"spreadsheetId": sid, "range": rng,
                             "valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"})
        cmd = [gws, "sheets", "spreadsheets", "values", "append",
               "--params", params, "--json", body, "--format", "json"]
    elif mode == "batchupdate":
        params = json.dumps({"spreadsheetId": sid})
        cmd = [gws, "sheets", "spreadsheets", "values", "batchUpdate",
               "--params", params, "--json", body, "--format", "json"]
    else:
        sys.stderr.write("ERR: unknown mode %s\n" % mode); sys.exit(1)

    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (r.stdout or "") + (r.stderr or "")
    m = re.search(r'"(totalUpdatedRows|updatedRows)"\s*:\s*(\d+)', out)
    if m:
        print('"%s": %s' % (m.group(1), m.group(2)))
        sys.exit(0)
    sys.stderr.write("ERR: " + out[-400:] + "\n")
    sys.exit(1)
except Exception as e:
    sys.stderr.write("gws_json error: %s\n" % e)
    sys.exit(1)
