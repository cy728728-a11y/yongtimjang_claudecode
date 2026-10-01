# -*- coding: utf-8 -*-
"""Aside REPL 실행 다리. aside-category 의 검증된 _run_repl 을 그대로 빌려 쓴다."""
import importlib.util
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DRIVERS = HERE / "drivers"
_AC_PATH = HERE.parents[1] / "aside-category" / "scripts" / "aside_category.py"

try:
    _spec = importlib.util.spec_from_file_location("aside_category", _AC_PATH)
    _ac = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_ac)
except (OSError, ImportError, AttributeError) as e:
    sys.exit(f"aside-category 스크립트를 불러오지 못했다: {_AC_PATH} ({e})")

ASIDE_BIN = _ac.ASIDE_BIN
REPL_WALL_SEC = _ac.REPL_WALL_SEC      # repl 호출당 ~120초 벽
CHUNK_MARGIN = _ac.CHUNK_MARGIN


def auto_chunk(count, sec_per_item, sleep_max):
    """120초 벽 아래로 들어가는 한 호출당 건수. 최소 1."""
    if count <= 0:
        return 1
    per = sec_per_item + (sleep_max or 0) / 2
    return max(1, min(count, int(REPL_WALL_SEC * CHUNK_MARGIN / per)))


def load_driver(name):
    """common.js + <name>.js 를 이어붙인 템플릿. login/probe 는 단독 파일."""
    try:
        body = (DRIVERS / f"{name}.js").read_text(encoding="utf-8")
        common = DRIVERS / "common.js"
        head = (common.read_text(encoding="utf-8")
                if common.exists() and name not in ("login", "probe") else "")
    except OSError as e:
        raise RuntimeError(f"드라이버 파일 읽기 실패: {name} ({e})")
    return head + "\n" + body


def run_driver(name, items, opts, timeout):
    """드라이버 실행 → __R__ 결과 리스트. aside 가 없으면 RuntimeError."""
    if not os.path.exists(ASIDE_BIN):
        raise RuntimeError(f"aside CLI 없음: {ASIDE_BIN} (ASIDE_BIN 환경변수로 지정)")
    return _ac._run_repl(load_driver(name), items, opts, timeout)
