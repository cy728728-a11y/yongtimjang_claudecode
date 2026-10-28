"""팀 매핑 — config/office-map.json 으로 세션을 팀에 배정한다.

순서: sessions 직접지정(세션 id 또는 이름) > rules 키워드(위에서부터, 대소문자 무시) > 로비(미배정).
매핑 파일은 mtime 이 바뀔 때만 다시 읽는다(서버 재시작 없이 한 줄 추가 반영).
"""
import json
import os
import re
import sys
from pathlib import Path

DEFAULT_MAP = Path(__file__).resolve().parent.parent / "config" / "office-map.json"
LOBBY = {"team": "lobby", "teamName": "로비·미배정", "teamColor": "#9a9a9a", "teamClosed": False, "role": ""}

_map_cache = {}  # 경로 → (mtime, mapping)


def forget():
    """캐시 비우기(시험 격리용)"""
    _map_cache.clear()


def _empty_map():
    return {"teams": [], "sessions": {}, "rules": []}


def load_map(path=DEFAULT_MAP):
    """매핑 파일 읽기. 깨졌거나 없으면 빈 매핑(전원 로비) + stderr 경고"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            raise ValueError("최상위가 객체가 아님")
        m = _empty_map()
        if isinstance(raw.get("teams"), list):
            m["teams"] = [t for t in raw["teams"] if isinstance(t, dict) and t.get("key")]
        if isinstance(raw.get("sessions"), dict):
            m["sessions"] = {str(k): v for k, v in raw["sessions"].items() if isinstance(v, dict)}
        if isinstance(raw.get("rules"), list):
            m["rules"] = [r for r in raw["rules"] if isinstance(r, dict) and r.get("match") and r.get("team")]
        return m
    except Exception as e:
        print(f"[teams] 매핑 파일을 못 읽어 전원 로비로 둔다 ({path}): {e}", file=sys.stderr)
        return _empty_map()


def get_map(path=DEFAULT_MAP):
    """mtime 이 바뀔 때만 다시 읽는 매핑"""
    p = str(path)
    try:
        m = os.stat(p).st_mtime
    except Exception:
        m = None
    hit = _map_cache.get(p)
    if hit is not None and hit[0] == m:
        return hit[1]
    mapping = load_map(p)
    _map_cache[p] = (m, mapping)
    return mapping


def _team_info(mapping, key, role=""):
    """팀 키 → 팀 필드. 모르는 키면 로비"""
    for t in mapping.get("teams", []):
        if t.get("key") == key:
            return {"team": key, "teamName": str(t.get("name") or key), "teamColor": str(t.get("color") or "#9a9a9a"),
                    "teamClosed": bool(t.get("closed", False)), "role": str(role or "")}
    return dict(LOBBY)


def team_name(mapping, key):
    """팀 키 → 팀 이름(없으면 키 그대로, lobby 는 로비 이름)"""
    if key == "lobby":
        return LOBBY["teamName"]
    for t in (mapping or {}).get("teams", []):
        if t.get("key") == key:
            return str(t.get("name") or key)
    return str(key or "")


def assign_team(sid, name, mapping=None):
    """세션 하나 → {team, teamName, teamColor, teamClosed, role}"""
    if mapping is None:
        mapping = get_map()
    try:
        sess = mapping.get("sessions", {})
        hit = sess.get(str(sid)) or sess.get(str(name))
        if hit and hit.get("team"):
            return _team_info(mapping, hit["team"], hit.get("role", ""))
        for r in mapping.get("rules", []):
            try:
                if re.search(str(r["match"]), str(name or ""), re.IGNORECASE):
                    return _team_info(mapping, r["team"], r.get("role", ""))
            except re.error:
                continue  # 잘못된 정규식 한 줄은 건너뛴다
    except Exception as e:
        print(f"[teams] 배정 실패 {sid}: {e}", file=sys.stderr)
    return dict(LOBBY)
