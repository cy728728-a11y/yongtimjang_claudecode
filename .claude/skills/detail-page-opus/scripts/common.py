# -*- coding: utf-8 -*-
"""detail-page-opus 배치 공용 — 경로·불사자 MCP 호출·Aside 사용량 조회."""
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]                      # 워크스페이스 루트
REMIX = ROOT / ".claude/skills/bulsaja-detail-remix/scripts"     # 반영 스크립트(run.py)·MCP 클라이언트
sys.path.insert(0, str(REMIX))
import bulsaja_client  # noqa: E402

PY = ROOT / ".venv/bin/python3"
ASIDE = Path.home() / ".local/bin/aside"
ASIDE_DB = Path.home() / ".aside/u/0/state.db"
PAGES = Path.home() / ".aside/u/0/detail-pages"
BRIEF_DIR = PAGES / "_brief"
ADS_RUNS = Path.home() / "python_work/data/naver-ads/runs"
BATCH_ROOT = Path.home() / "python_work/data/detail-opus/batches"
MODEL = "claude-code/claude-opus-5-5"


def mcp():
    """열린 불사자 MCP 클라이언트. 호출부가 close 한다."""
    m = bulsaja_client.DetailRemixMCP()
    m.open()
    return m


def call(m, tool, args, gap=2.0):
    """도구 호출 — 확인 단계 응답(success:false + 확인키)도 dict 로 그대로 돌려준다.
    불사자가 연속 호출을 429 로 막아서 호출마다 간격을 두고, 429 면 길게 쉬었다 다시 한다."""
    for wait in (0, 60, 120, 240):
        if wait:
            print(f"  [429] {wait}초 쉬고 다시 — {tool}", flush=True)
            time.sleep(wait)
        try:
            time.sleep(gap)
            r = m.call_tool(tool, args)
            return r if isinstance(r, dict) else {"raw": r}
        except RuntimeError as e:
            if "429" not in str(e):
                raise
    raise RuntimeError(f"{tool} 429 반복 — 나중에 다시")


def market_no(group_name):
    """그룹명 '5번_용쌤25-2' · '용쌤4-1' → '25-2'. 없으면 None."""
    mt = re.search(r"용쌤(\d{1,2}-\d)(?!\d)", group_name or "")
    return mt.group(1) if mt else None


def aside_usage(start_ts, end_ts):
    """그 시간대에 시작한 Aside 턴의 토큰·비용 합(API 환산). 다른 Aside 작업이 겹치면 과대 계상된다."""
    try:
        con = sqlite3.connect(f"file:{ASIDE_DB}?mode=ro", uri=True)
        row = con.execute(
            "select count(*), sum(json_extract(token_usage,'$.totalTokens')),"
            " sum(json_extract(token_usage,'$.cost.total')) from session_turns"
            " where started_at between ? and ?", (int(start_ts), int(end_ts))).fetchone()
        con.close()
        return {"turns": row[0] or 0, "tokens": int(row[1] or 0), "cost_usd": round(row[2] or 0, 2)}
    except Exception as e:
        return {"error": str(e)}


def write_json(path, data):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
