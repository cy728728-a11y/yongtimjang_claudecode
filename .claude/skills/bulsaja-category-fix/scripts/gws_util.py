#!/usr/bin/env python3
"""[shim] gws 시트 래퍼 — 실체는 eroomlib.gsheets 로 이동.

이 파일은 하위호환 재수출 껍데기다. 기존 소비자(sys.path 로 이 폴더를 잡고
`from gws_util import sheets_get/sheets_update/_run_gws` 하는 코드: bulsaja_mcp·
sheet_log·collect_targets·keyword-pick/sheet_io·product-name/run_names)를
무수정으로 통과시킨다. 새 코드는 `import eroomlib.gsheets` 를 직접 써라.
"""
import os
import sys

# 상위로 `.claude` 앵커(= lib/eroomlib 를 품은 디렉토리)를 찾아 lib 를 1회 insert.
_d = os.path.dirname(os.path.abspath(__file__))
while _d and _d != os.path.dirname(_d):
    _lib = os.path.join(_d, "lib")
    if os.path.isdir(os.path.join(_lib, "eroomlib")):
        if _lib not in sys.path:
            sys.path.insert(0, _lib)
        break
    _d = os.path.dirname(_d)

from eroomlib.gsheets import _run_gws, sheets_get, sheets_update  # noqa: E402,F401


if __name__ == "__main__":
    # 스모크 테스트: python gws_util.py <spreadsheetId> <range>
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    vals = sheets_get(sys.argv[1], sys.argv[2])
    print(f"{len(vals)} rows")
    for r in vals[:5]:
        print(r)
