# -*- coding: utf-8 -*-
"""맥북 자동작업 예약관리자 — launchd 가 1분마다 부른다(com.eroom.scheduler, StartInterval 60).

왜: 이 맥북에선 새로 등록한 StartCalendarInterval(정시 실행) 예약이 안 터진다(2026-10-17 실측 2회).
     StartInterval 은 정상이라 1분 틱으로 '할 때가 된 작업'을 직접 띄운다.
     맥이 잠들어 시각을 놓쳐도 깨어난 첫 틱에 따라잡는다(같은 날 1회).

작업 표는 JOBS 한 곳. 상태는 ~/python_work/data/scheduler/state.json (작업별 마지막 실행 키).
로그는 ~/python_work/data/scheduler/logs/<작업>.log
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
WS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # 워크스페이스 루트
PY = os.path.join(WS, ".venv", "bin", "python3")
DATA = os.path.expanduser("~/python_work/data/scheduler")
STATE = os.path.join(DATA, "state.json")

# kind: daily(HH:MM 이후 하루 1회) · weekly(요일 0=월, HH:MM 이후 주 1회) · hourly(매시 1회)
JOBS = [
    {"name": "sold-lock", "kind": "daily", "at": "00:01",
     "cmd": [PY, ".claude/skills/sold-lock/scripts/run_sold_lock.py"], "caffeinate": True},
    {"name": "board-rollover", "kind": "daily", "at": "04:30",
     "cmd": [PY, ".claude/skills/work-board/scripts/board_sync.py", "rollover"]},
    {"name": "board-sync", "kind": "hourly",
     "cmd": [PY, ".claude/skills/work-board/scripts/board_sync.py", "sync"]},
    {"name": "ads-weekly", "kind": "weekly", "weekday": 0, "at": "07:00",
     "cmd": [PY, ".claude/skills/naver-ads-weekly/scripts/weekly_monday.py"], "caffeinate": True},
    {"name": "auto-watch", "kind": "daily", "at": "07:30",
     "cmd": [PY, ".claude/skills/auto-watch/scripts/watch.py"]},
]


def due_key(job, now):
    """지금 돌릴 때면 이번 회차 키(문자열), 아니면 None."""
    kind = job["kind"]
    if kind == "hourly":
        return now.strftime("%Y-%m-%d %H")
    hh, mm = map(int, job["at"].split(":"))
    if (now.hour, now.minute) < (hh, mm):
        return None
    if kind == "daily":
        return now.strftime("%Y-%m-%d")
    if kind == "weekly":
        if now.weekday() != job["weekday"]:
            return None
        return now.strftime("%G-W%V")
    return None


def _load_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state):
    os.makedirs(DATA, exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE)


def _alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def tick(now=None, spawn=None):
    """할 때가 된 작업을 띄운다. 같은 작업이 아직 돌고 있으면 건너뛴다."""
    now = now or datetime.now(KST)
    state = _load_state()
    started = []
    for job in JOBS:
        key = due_key(job, now)
        if key is None:
            continue
        st = state.get(job["name"], {})
        if st.get("last_key") == key:
            continue
        if st.get("pid") and _alive(st["pid"]):
            continue  # 지난 회차가 아직 실행 중
        try:
            pid = (spawn or _spawn)(job)
            state[job["name"]] = {"last_key": key, "pid": pid,
                                  "started_at": now.isoformat(timespec="seconds")}
            started.append(job["name"])
        except Exception as e:
            state[job["name"]] = dict(st, error=f"{type(e).__name__}: {e}"[:300],
                                      error_at=now.isoformat(timespec="seconds"))
    _save_state(state)
    return started


def _spawn(job):
    """작업을 분리 실행(예약관리자가 끝나도 계속 돈다)."""
    os.makedirs(os.path.join(DATA, "logs"), exist_ok=True)
    log = open(os.path.join(DATA, "logs", f"{job['name']}.log"), "a", encoding="utf-8")
    log.write(f"\n===== {datetime.now(KST).isoformat(timespec='seconds')} 시작 =====\n")
    log.flush()
    cmd = (["/usr/bin/caffeinate", "-i"] if job.get("caffeinate") else []) + job["cmd"]
    p = subprocess.Popen(cmd, cwd=WS, stdout=log, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, start_new_session=True,
                         env=dict(os.environ, PYTHONUNBUFFERED="1"))
    return p.pid


if __name__ == "__main__":
    try:
        s = tick()
        if s:
            print(f"[scheduler] {datetime.now(KST):%Y-%m-%d %H:%M} 시작: {', '.join(s)}")
    except Exception as e:
        print(f"[scheduler] 실패: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
