"""로봇 직원 — 예약 작업(launchd·Aside 루틴)을 로그 파일 mtime 으로 표시한다.

상태: 로그가 10분 안에 바뀜 → working / 오늘 예정시각+30분이 지났는데 로그가 예정시각 이전에
마지막으로 바뀜 → absent(결근) / 로그 경로 없음 → unknown / 그 밖 idle.
파일은 stat 만 하고 내용은 읽지 않는다.
"""
import glob
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import teams

DEFAULT_ROBOTS = Path(__file__).resolve().parent.parent / "config" / "robots.json"
WORKING_SEC = 10 * 60
ABSENT_GRACE_SEC = 30 * 60


def load_robots(path=DEFAULT_ROBOTS):
    """robots.json 읽기. 실패하면 빈 목록"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return raw if isinstance(raw, dict) else {"robots": []}
    except Exception as e:
        print(f"[robots] 설정을 못 읽었다 ({path}): {e}", file=sys.stderr)
        return {"robots": []}


def _log_mtime(log_path):
    """로그 mtime. '*' 가 있으면 맞는 파일 중 가장 최근. 없으면 None"""
    try:
        p = os.path.expanduser(str(log_path))
        files = glob.glob(p) if any(c in p for c in "*?[") else [p]
        best = None
        for f in files:
            try:
                m = os.stat(f).st_mtime
            except Exception:
                continue
            best = m if best is None or m > best else best
        return best
    except Exception:
        return None


def _iso(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
        f"{int((ts % 1) * 1000):03d}Z"


def _scheduled_today(schedule, now):
    """'HH:MM' → 오늘(로컬 시각) 그 시각의 epoch. 이상하면 None"""
    try:
        hh, mm = (int(x) for x in str(schedule).split(":"))
        d = datetime.fromtimestamp(now).replace(hour=hh, minute=mm, second=0, microsecond=0)
        return d.timestamp()
    except Exception:
        return None


def robot_status(robots_cfg, now, mapping=None):
    """로봇 목록 → [{key, name, team, teamName, schedule, status, lastAt}]"""
    items = robots_cfg.get("robots", []) if isinstance(robots_cfg, dict) else (robots_cfg or [])
    out = []
    for r in items:
        try:
            if not isinstance(r, dict):
                continue
            log_path = r.get("log_path")
            schedule = r.get("schedule")
            mtime = _log_mtime(log_path) if log_path else None
            if not log_path:
                status = "unknown"
            elif mtime is not None and now - mtime < WORKING_SEC:
                status = "working"
            else:
                status = "idle"
                sched = _scheduled_today(schedule, now) if schedule else None
                if sched is not None and now >= sched + ABSENT_GRACE_SEC and (mtime is None or mtime < sched):
                    status = "absent"
            out.append({
                "key": str(r.get("key") or ""),
                "name": str(r.get("name") or ""),
                "team": str(r.get("team") or "lobby"),
                "teamName": teams.team_name(mapping, r.get("team") or "lobby") if mapping is not None
                else str(r.get("team") or ""),
                "schedule": schedule,
                "status": status,
                "lastAt": _iso(mtime) if mtime is not None else None,
            })
        except Exception as e:
            print(f"[robots] 건너뜀 {r}: {e}", file=sys.stderr)
    return out
