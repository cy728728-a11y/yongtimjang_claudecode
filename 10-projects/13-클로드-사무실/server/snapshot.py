"""GET /api/office 응답 조립 — 원본 CONTRACT.md §4 형식, 단 세션 1개 = 직원 1명.

원본 server/snapshot.mjs (MIT) 의 Person 조립을 따르되, 폴더별로 묶지 않고 세션마다 한 명을 만든다.
원본 Person 키는 전부 유지하고 team/teamName/teamColor/teamClosed/role 을 덧붙인다.
최상위에는 원본 키에 더해 robots(로봇 직원) 배열을 붙인다.
"""
import json
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import activity
import robots
import sessions
import teams

API_VERSION = 1
CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
OFFICE_JSON = CONFIG_DIR / "office.json"
DEFAULTS = {"port": 4778, "visibleHours": 6, "workingSeconds": 90, "lang": "ko", "hide": []}


def load_office_config(path=OFFICE_JSON):
    """office.json 읽기 — 값이 이상하면 기본값"""
    cfg = dict(DEFAULTS)
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            raw = {}
    except Exception as e:
        print(f"[snapshot] office.json 을 못 읽어 기본값을 쓴다: {e}", file=sys.stderr)
        raw = {}
    for k in ("port", "visibleHours", "workingSeconds"):
        v = raw.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
            cfg[k] = int(v) if k == "port" else v
    if not (1 <= int(cfg["port"]) <= 65535):
        cfg["port"] = DEFAULTS["port"]
    if raw.get("lang") in ("auto", "ko", "en"):
        cfg["lang"] = raw["lang"]
    if isinstance(raw.get("hide"), list):
        cfg["hide"] = [str(x) for x in raw["hide"]]
    return cfg


def _iso(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
        f"{int((ts % 1) * 1000):03d}Z"


def _person(s, now, cfg, mapping):
    """세션 하나 → Person"""
    sid, path, mtime = s["sid"], s["path"], s["mtime"]
    info = activity.read_tail(path)
    name = sessions.session_name(path, sid)
    status = sessions.session_status(info["last"], mtime, now, cfg.get("workingSeconds", 90))
    subs = activity.running_subagents(path, now)
    team = teams.assign_team(sid, name, mapping)
    p = {
        "id": sid,
        "name": name,
        "path": info.get("cwd") or "",
        "status": status,
        "pending": 0,
        "ask": "",
        "sessions": 1,
        "source": "transcript",
        "commits": None,
        "kid": False,
        "home": None,
        "subs": subs[: activity.MAX_SUBS],
        "subCount": len(subs),
        "doing": info["doing"],
        "log": info["log"],
    }
    p.update(team)
    return p


def build_snapshot(now=None, cfg=None):
    """스냅샷 한 장. cfg 를 주면(시험용) 그 값으로, 없으면 config/*.json 에서 읽는다"""
    now = time.time() if now is None else now
    if cfg is None:
        cfg = load_office_config()
    mapping = cfg.get("office_map")
    if mapping is None:
        mapping = teams.get_map()
    robots_cfg = cfg.get("robots")
    if robots_cfg is None:
        robots_cfg = robots.load_robots()
    hide = set(str(x) for x in cfg.get("hide", []) or [])

    people = []
    for s in sessions.recent_sessions(cfg.get("visibleHours", 6), now):
        try:
            p = _person(s, now, cfg, mapping)
        except Exception:
            print(f"[snapshot] 세션 건너뜀 {s.get('sid')}:\n{traceback.format_exc()}", file=sys.stderr)
            continue
        if p["id"] in hide or p["name"] in hide:
            continue
        people.append(p)

    # 이름이 같은 세션이 둘 이상이면 "이름 (sid 앞 8자)" 로 가른다
    count = {}
    for p in people:
        count[p["name"]] = count.get(p["name"], 0) + 1
    for p in people:
        if count[p["name"]] > 1:
            p["name"] = f"{p['name']} ({p['id'][:8]})"
    people.sort(key=lambda p: (p["team"], p["name"], p["id"]))

    return {
        "version": API_VERSION,
        "now": _iso(now),
        "hooks": False,
        "demo": False,
        "people": people,
        "robots": robots.robot_status(robots_cfg, now, mapping),
    }
