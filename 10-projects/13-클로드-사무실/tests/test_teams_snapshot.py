"""teams.py · robots.py · snapshot.py 시험"""
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import robots
import snapshot
import teams
from conftest import assistant, tool_use, user

CONFIG = Path(__file__).resolve().parent.parent / "config"
REAL_MAP = teams.load_map(CONFIG / "office-map.json")

ORIGINAL_KEYS = ["id", "name", "path", "status", "pending", "ask", "sessions", "source", "commits",
                 "kid", "home", "subs", "subCount", "doing", "log"]


# ── teams ──────────────────────────────────────────────────
def test_real_map_shape():
    assert len(REAL_MAP["teams"]) == 8
    assert len(REAL_MAP["rules"]) == 8
    ads = [t for t in REAL_MAP["teams"] if t["key"] == "ads"][0]
    assert ads.get("closed") is True


def test_sessions_direct_by_name():
    t = teams.assign_team("x", "to-do-list", REAL_MAP)
    assert t["team"] == "sec" and t["role"] == "업무관리" and t["teamName"] == "비서실"


def test_sessions_direct_by_sid():
    m = {"teams": REAL_MAP["teams"], "sessions": {"sid-123": {"team": "it", "role": "r"}}, "rules": []}
    t = teams.assign_team("sid-123", "아무이름", m)
    assert t["team"] == "it" and t["role"] == "r"


def test_rules():
    assert teams.assign_team("y", "고퀄 상세페이지 배치", REAL_MAP)["team"] == "plan"
    assert teams.assign_team("y", "옵션 정리", REAL_MAP)["team"] == "ops"
    assert teams.assign_team("y", "cs 답변", REAL_MAP)["team"] == "cs"
    # 첫 번째로 맞는 규칙이 이긴다: "업무"(sec) 가 "광고"(ads) 보다 위
    assert teams.assign_team("y", "광고 업무", REAL_MAP)["team"] == "sec"


def test_closed_team_flag():
    t = teams.assign_team("y", "입찰가 조정", REAL_MAP)
    assert t["team"] == "ads" and t["teamClosed"] is True and t["teamColor"] == "#7b8a83"


def test_lobby_default():
    t = teams.assign_team("y", "아무 관련 없는 이름", REAL_MAP)
    assert t == {"team": "lobby", "teamName": "로비·미배정", "teamColor": "#9a9a9a", "teamClosed": False, "role": ""}


def test_broken_or_missing_map(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    m = teams.load_map(bad)
    assert teams.assign_team("x", "to-do-list", m)["team"] == "lobby"
    m2 = teams.load_map(tmp_path / "none.json")
    assert teams.assign_team("x", "옵션", m2)["team"] == "lobby"


def test_bad_regex_rule_skipped():
    m = {"teams": REAL_MAP["teams"], "sessions": {},
         "rules": [{"match": "([", "team": "it"}, {"match": "옵션", "team": "ops"}]}
    assert teams.assign_team("x", "옵션", m)["team"] == "ops"


def test_map_reload_on_mtime(tmp_path):
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"teams": [], "sessions": {}, "rules": []}), encoding="utf-8")
    assert teams.get_map(p)["rules"] == []
    p.write_text(json.dumps({"teams": [], "sessions": {}, "rules": [{"match": "a", "team": "it"}]}), encoding="utf-8")
    t = time.time() + 5
    os.utime(p, (t, t))
    assert len(teams.get_map(p)["rules"]) == 1


# ── robots ─────────────────────────────────────────────────
def _robot(**kw):
    base = {"key": "r", "name": "로봇", "team": "ops", "schedule": None, "log_path": None}
    base.update(kw)
    return base


def test_robot_unknown_without_log():
    out = robots.robot_status({"robots": [_robot()]}, time.time())
    assert out[0]["status"] == "unknown" and out[0]["lastAt"] is None


def test_robot_working_recent_log(tmp_path):
    log = tmp_path / "a.log"
    log.write_text("x")
    out = robots.robot_status({"robots": [_robot(log_path=str(log))]}, time.time())
    assert out[0]["status"] == "working" and out[0]["lastAt"]


def test_robot_absent_and_idle(tmp_path):
    log = tmp_path / "a.log"
    log.write_text("x")
    now_dt = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
    now = now_dt.timestamp()
    # 로그가 오늘 07:00(예정 09:00 이전)에 마지막으로 바뀜 → 09:30 지났으니 결근
    t = now_dt.replace(hour=7).timestamp()
    os.utime(log, (t, t))
    out = robots.robot_status({"robots": [_robot(schedule="09:00", log_path=str(log))]}, now)
    assert out[0]["status"] == "absent"
    # 로그가 09:05 에 바뀜 → idle
    t2 = now_dt.replace(hour=9, minute=5).timestamp()
    os.utime(log, (t2, t2))
    out = robots.robot_status({"robots": [_robot(schedule="09:00", log_path=str(log))]}, now)
    assert out[0]["status"] == "idle"
    # 예정 11:45 + 30분 아직 안 지남 → idle
    os.utime(log, (t, t))
    out = robots.robot_status({"robots": [_robot(schedule="11:45", log_path=str(log))]}, now)
    assert out[0]["status"] == "idle"


def test_robot_glob_newest(tmp_path):
    for d, ago in (("2026-10-27", 3600 * 5), ("2026-10-28", 60)):
        (tmp_path / d).mkdir()
        f = tmp_path / d / "batch.log"
        f.write_text("x")
        t = time.time() - ago
        os.utime(f, (t, t))
    out = robots.robot_status({"robots": [_robot(log_path=str(tmp_path / "*" / "batch.log"))]}, time.time())
    assert out[0]["status"] == "working"


def test_robot_team_name():
    out = robots.robot_status({"robots": [_robot(team="cs")]}, time.time(), REAL_MAP)
    assert out[0]["teamName"] == "CS·권리팀"


# ── snapshot ───────────────────────────────────────────────
def _cfg(**kw):
    c = {"visibleHours": 6, "workingSeconds": 90, "hide": [], "office_map": REAL_MAP, "robots": {"robots": []}}
    c.update(kw)
    return c


def _title(v):
    return {"type": "custom-title", "customTitle": v, "sessionId": "x"}


def test_snapshot_three_sessions_same_cwd(claude_home):
    claude_home.write("aaaa1111-0000", [_title("옵션 정리"), user("hi"), assistant([tool_use("t", "Read")])], ago=10)
    claude_home.write("bbbb2222-0000", [_title("to-do-list"), assistant([{"type": "text", "text": "x"}], stop_reason="end_turn")], ago=600)
    claude_home.write("cccc3333-0000", [user("hi")], ago=20)
    snap = snapshot.build_snapshot(now=time.time(), cfg=_cfg())
    assert snap["version"] == 1 and snap["hooks"] is False and snap["demo"] is False
    assert snap["now"].endswith("Z")
    assert snap["robots"] == []
    people = snap["people"]
    assert len(people) == 3
    assert len({p["id"] for p in people}) == 3
    by = {p["id"]: p for p in people}
    a = by["aaaa1111-0000"]
    assert a["name"] == "옵션 정리" and a["team"] == "ops" and a["status"] == "working"
    assert a["path"] == "/Users/me/ws" and a["doing"] == {"k": "read", "a": "server.py"}
    b = by["bbbb2222-0000"]
    assert b["name"] == "to-do-list" and b["team"] == "sec" and b["status"] == "rest" and b["role"] == "업무관리"
    c = by["cccc3333-0000"]
    assert c["name"] == "cccc3333" and c["team"] == "lobby"
    for p in people:
        for k in ORIGINAL_KEYS + ["team", "teamName", "teamColor", "teamClosed", "role"]:
            assert k in p, k
        assert p["sessions"] == 1 and p["source"] == "transcript" and p["pending"] == 0
        assert p["ask"] == "" and p["commits"] is None and p["kid"] is False and p["home"] is None
    # 팀 키 → 이름 순
    assert [p["team"] for p in people] == sorted(p["team"] for p in people)


def test_snapshot_duplicate_names(claude_home):
    claude_home.write("abcd1234-aaaa", [_title("같은이름"), user("x")], ago=10)
    claude_home.write("efgh5678-bbbb", [_title("같은이름"), user("x")], ago=10)
    names = sorted(p["name"] for p in snapshot.build_snapshot(cfg=_cfg())["people"])
    assert names == ["같은이름 (abcd1234)", "같은이름 (efgh5678)"]


def test_snapshot_hide(claude_home):
    claude_home.write("abcd1234-aaaa", [_title("숨길것"), user("x")], ago=10)
    claude_home.write("efgh5678-bbbb", [_title("보일것"), user("x")], ago=10)
    claude_home.write("zzzz9999-cccc", [_title("세션id로숨김"), user("x")], ago=10)
    snap = snapshot.build_snapshot(cfg=_cfg(hide=["숨길것", "zzzz9999-cccc"]))
    assert [p["name"] for p in snap["people"]] == ["보일것"]


def test_snapshot_subagents(claude_home):
    p = claude_home.write("abcd1234-aaaa", [_title("옵션"), user("x")], ago=10)
    for i in range(14):
        claude_home.sub(p, f"s{i:02d}", [assistant([tool_use("a", "Read")])], meta={"agentType": "Explore"}, ago=5)
    person = snapshot.build_snapshot(cfg=_cfg())["people"][0]
    assert person["subCount"] == 14 and len(person["subs"]) == 12


def test_snapshot_parent_waiting_but_subagent_running_is_working(claude_home):
    # 주인은 10분 전에 턴을 끝냈지만 서브에이전트가 일하는 중 → working
    p = claude_home.write("abcd1234-aaaa", [_title("옵션"), assistant([{"type": "text", "text": "x"}], stop_reason="end_turn")], ago=600)
    claude_home.sub(p, "s01", [assistant([tool_use("a", "Read")])], meta={"agentType": "gsd-executor"}, ago=5)
    claude_home.write("efgh5678-bbbb", [_title("쉬는세션"), assistant([{"type": "text", "text": "x"}], stop_reason="end_turn")], ago=600)
    by = {p["name"]: p for p in snapshot.build_snapshot(cfg=_cfg())["people"]}
    assert by["옵션"]["status"] == "working" and by["옵션"]["subCount"] == 1
    assert by["쉬는세션"]["status"] == "rest"


def test_snapshot_one_broken_session_does_not_kill(claude_home, monkeypatch):
    claude_home.write("good0000-aaaa", [_title("좋음"), user("x")], ago=10)
    claude_home.write("bad00000-bbbb", [_title("나쁨"), user("x")], ago=10)
    real = snapshot.activity.read_tail

    def boom(path):
        if "bad00000" in str(path):
            raise RuntimeError("boom")
        return real(path)

    monkeypatch.setattr(snapshot.activity, "read_tail", boom)
    snap = snapshot.build_snapshot(cfg=_cfg())
    assert [p["name"] for p in snap["people"]] == ["좋음"]


def test_snapshot_robots_included(claude_home):
    snap = snapshot.build_snapshot(cfg=_cfg(robots={"robots": [_robot(team="ops")]}))
    assert snap["robots"][0]["status"] == "unknown" and snap["robots"][0]["teamName"] == "상품운영팀"
