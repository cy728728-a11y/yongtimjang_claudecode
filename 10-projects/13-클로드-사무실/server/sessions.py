"""최근 대화 파일 찾기 · 세션 이름 · 상태 판정.

원본 server/sessions.mjs (MIT) 의 recentTranscripts() 를 옮기고, 세션 단위 이름·상태를 더했다.
- 대화 파일: <config>/projects/<encoded-cwd>/<sessionId>.jsonl (한 단계만, subagents 제외)
- 파일은 읽기 모드('rb')로만 연다. 쓰기·삭제·touch 없음.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

SID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
SCAN_TTL_SEC = 5  # 대화 폴더 훑기는 5초에 한 번
TAIL_BYTES = 64 * 1024  # 이름 찾기: 꼬리 먼저
CHUNK = 1024 * 1024  # 이름 찾기: 앞에서부터 1MB 덩어리
_NAME_NEEDLES = (b'"type":"custom-title"', b'"type":"ai-title"')

_scan_cache = {"key": None, "at": 0.0, "value": []}
_name_cache = {}  # (경로, inode) → {"end": 오프셋, "custom": str|None, "ai": str|None}
NAME_CACHE_MAX = 1000


def forget():
    """캐시 비우기(시험 격리용)"""
    _scan_cache.update({"key": None, "at": 0.0, "value": []})
    _name_cache.clear()


def config_dir():
    """Claude 설정 폴더 — CLAUDE_CONFIG_DIR 우선, 없으면 ~/.claude"""
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env).expanduser() if env else Path("~/.claude").expanduser()


def recent_sessions(visible_hours, now=None):
    """최근 visible_hours 시간 안에 바뀐 대화 파일 → [{sid, path, mtime}]"""
    now = time.time() if now is None else now
    root = config_dir() / "projects"
    key = f"{root}|{visible_hours}"
    if _scan_cache["key"] == key and now - _scan_cache["at"] < SCAN_TTL_SEC:
        return list(_scan_cache["value"])
    since = now - float(visible_hours) * 3600
    out = []
    try:
        dirs = [d for d in os.scandir(root) if d.is_dir(follow_symlinks=False)]
    except Exception:
        dirs = []
    for d in dirs:
        try:
            names = os.listdir(d.path)
        except Exception:
            continue
        for n in names:
            if not n.endswith(".jsonl"):
                continue
            sid = n[: -len(".jsonl")]
            if not SID_RE.match(sid):
                continue
            p = Path(d.path) / n
            try:
                st = os.stat(p)
                if p.is_file() and st.st_mtime >= since:
                    out.append({"sid": sid, "path": p, "mtime": st.st_mtime})
            except Exception:
                continue  # 그새 사라졌다
    out.sort(key=lambda x: x["sid"])
    _scan_cache.update({"key": key, "at": now, "value": out})
    return list(out)


def _scan_titles(buf, state):
    """완전한 줄들에서 제목 줄만 파싱해 state 의 custom/ai 를 마지막 값으로 갱신"""
    for line in buf.split(b"\n"):
        if not any(n in line for n in _NAME_NEEDLES):
            continue
        try:
            e = json.loads(line.decode("utf-8", errors="replace"))
        except Exception:
            continue
        if not isinstance(e, dict):
            continue
        if e.get("type") == "custom-title" and isinstance(e.get("customTitle"), str) and e["customTitle"].strip():
            state["custom"] = e["customTitle"].strip()
        elif e.get("type") == "ai-title" and isinstance(e.get("aiTitle"), str) and e["aiTitle"].strip():
            state["ai"] = e["aiTitle"].strip()


def _scan_from(f, start, size, state):
    """start 부터 size 까지 1MB 덩어리로 훑는다. 경계에 걸친 줄은 다음 덩어리로 이월. 처리한 끝 오프셋 반환"""
    pos = start
    carry = b""
    f.seek(start)
    while pos < size:
        chunk = f.read(min(CHUNK, size - pos))
        if not chunk:
            break
        pos += len(chunk)
        data = carry + chunk
        nl = data.rfind(b"\n")
        if nl < 0:
            carry = data
            continue
        _scan_titles(data[:nl], state)
        carry = data[nl + 1:]
    return pos - len(carry)


def session_name(path, sid):
    """세션 이름 — 마지막 customTitle → 없으면 마지막 aiTitle → 없으면 sid 앞 8자"""
    fallback = str(sid)[:8]
    try:
        with open(path, "rb") as f:
            st = os.fstat(f.fileno())
            size = st.st_size
            ckey = (str(path), st.st_ino)
            state = _name_cache.get(ckey)
            if state is not None and state["end"] <= size:
                # 자란 만큼만 이어 훑는다
                if state["end"] < size:
                    state["end"] = _scan_from(f, state["end"], size, state)
            else:
                state = {"end": 0, "custom": None, "ai": None}
                # 1) 꼬리 64KB — customTitle 이 여기 있으면 끝(제일 최근 값이자 ai 보다 우선)
                start = max(0, size - TAIL_BYTES)
                f.seek(start)
                raw = f.read(size - start)
                body = 0
                if start > 0:  # 창 시작이 줄 중간이면 첫 반쪽 줄은 버린다
                    nl = raw.find(b"\n")
                    body = nl + 1 if nl >= 0 else len(raw)
                last_nl = raw.rfind(b"\n")
                tail_state = {"custom": None, "ai": None}
                if last_nl >= body:
                    _scan_titles(raw[body:last_nl], tail_state)
                if tail_state["custom"]:
                    state["custom"] = tail_state["custom"]
                    state["end"] = start + last_nl + 1
                else:
                    # 2) 앞에서부터 끝까지(파일당 처음 한 번만)
                    state["end"] = _scan_from(f, 0, size, state)
                if len(_name_cache) >= NAME_CACHE_MAX:
                    _name_cache.clear()
                _name_cache[ckey] = state
            return state["custom"] or state["ai"] or fallback
    except Exception as e:
        print(f"[sessions] 이름 읽기 실패 {path}: {e}", file=sys.stderr)
        return fallback


def session_status(last, mtime, now=None, working_sec=90):
    """세션 상태 — "working" | "rest" (승인 대기는 1단계 범위 밖)

    1) 끊김 표시·API 오류로 끝났으면 rest (90초 규칙보다 우선)
    2) 대화 파일이 working_sec 안에 바뀌었으면 working
    3) 마지막 도구 호출의 결과가 아직 없으면 working
    4) 그 밖 rest
    """
    now = time.time() if now is None else now
    try:
        if last and (last.get("interrupted") or (last.get("type") == "assistant" and last.get("api_error"))):
            return "rest"
        if now - float(mtime or 0) < working_sec:
            return "working"
        if last and last.get("unresolved_tool"):
            return "working"
    except Exception:
        return "rest"
    return "rest"
