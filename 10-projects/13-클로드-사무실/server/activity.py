"""대화 기록(jsonl) 꼬리 → '지금 하는 일'(Act) + 최근 활동 + 마지막 대화 줄의 상태.

원본 claude-3d-frog-office 의 server/activity.mjs (MIT) 를 Python 으로 옮겨 고쳤다.
- 대화 기록 형식은 Claude Code 내부 형식이라 바뀔 수 있다 — 모르는 모양은 조용히 건너뛴다.
- Bash 는 사람이 읽으라고 쓴 description 을 먼저 쓴다(명령 원문엔 토큰이 섞일 수 있다).
- 읽기 창은 끝 64KB 부터 시작해 64KB→256KB→1MB→4MB 로 넓힌다. 4MB 넘게는 절대 안 읽는다.
  (대화 줄 사이에 2MB 짜리 api-request-blob 같은 기록용 줄이 끼어 있다.)
- 파일은 읽기 모드('rb')로만 연다. 쓰기·삭제·touch 없음.
"""
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

LOG_N = 8  # 사람마다 넘기는 최근 활동 수
MAX_SUBS = 12  # 화면에 넘기는 서브에이전트 상한
SUB_QUIET_SEC = 30 * 60  # 30분 넘게 멈춘 서브에이전트는 끝난(끊긴) 것
WINDOWS = [64 * 1024, 256 * 1024, 1024 * 1024, 4 * 1024 * 1024]  # 꼬리 창 넓혀 가기
MAX_READ = WINDOWS[-1]
CACHE_MAX = 300  # 파일별 캐시 상한 — 넘으면 비운다

_cache = {}  # 경로 → (ino, size, mtime, info)


def forget():
    """캐시 비우기(시험 격리용)"""
    _cache.clear()


def one_line(text, n):
    """공백을 접어 한 줄로, n 글자 넘으면 말줄임"""
    s = " ".join(str(text or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def base_name(p):
    """'C:\\a\\b.txt' 도 '/a/b.txt' 도 마지막 토막"""
    parts = [x for x in re.split(r"[\\/]+", str(p or "")) if x]
    return parts[-1] if parts else ""


def _host_of(url):
    try:
        return urlparse(str(url or "")).hostname or ""
    except Exception:
        return ""


_MD_RE = re.compile(r"\*\*|__|`+|^#+\s*|\n#+\s*")


def describe(block):
    """assistant 블록 하나 → Act {k, a}. thinking·빈 글·모르는 모양은 None"""
    try:
        if not isinstance(block, dict):
            return None
        btype = block.get("type")
        if btype == "text":
            a = one_line(_MD_RE.sub(" ", str(block.get("text") or "")), 60)
            return {"k": "text", "a": a} if a else None
        if btype != "tool_use":
            return None
        name = str(block.get("name") or "")
        inp = block.get("input") if isinstance(block.get("input"), dict) else {}
        if name == "Read":
            return {"k": "read", "a": base_name(inp.get("file_path"))}
        if name in ("Edit", "MultiEdit", "NotebookEdit"):
            return {"k": "edit", "a": base_name(inp.get("file_path") or inp.get("notebook_path"))}
        if name == "Write":
            return {"k": "write", "a": base_name(inp.get("file_path"))}
        if name == "Bash":
            if inp.get("description"):
                return {"k": "bash", "a": one_line(inp.get("description"), 44)}
            return {"k": "bash", "a": one_line(inp.get("command"), 40)}
        if name == "Grep":
            return {"k": "grep", "a": one_line(inp.get("pattern"), 24)}
        if name == "Glob":
            return {"k": "glob", "a": one_line(inp.get("pattern"), 28)}
        if name == "WebFetch":
            return {"k": "fetch", "a": _host_of(inp.get("url"))}
        if name == "WebSearch":
            return {"k": "search", "a": one_line(inp.get("query"), 24)}
        if name in ("Agent", "Task"):
            return {"k": "agent", "a": one_line(inp.get("description"), 30)}
        if name == "TodoWrite":
            return {"k": "todo", "a": ""}
        if name == "Skill":
            return {"k": "skill", "a": one_line(inp.get("skill"), 24)}
        if name.startswith("mcp__"):
            return {"k": "mcp", "a": one_line(name.split("__")[-1], 24)}
        return {"k": "tool", "a": one_line(name, 24)} if name else None
    except Exception:
        return None


def _user_text(msg):
    """user 줄의 글(문자열·text 블록·tool_result 안의 글)을 한데 모은다"""
    c = msg.get("content") if isinstance(msg, dict) else None
    if isinstance(c, str):
        return c
    if not isinstance(c, list):
        return ""
    parts = []
    for b in c:
        if not isinstance(b, dict):
            continue
        if isinstance(b.get("text"), str):
            parts.append(b["text"])
        if isinstance(b.get("content"), str):
            parts.append(b["content"])
        if isinstance(b.get("content"), list):
            for x in b["content"]:
                if isinstance(x, dict) and isinstance(x.get("text"), str):
                    parts.append(x["text"])
    return "\n".join(parts)


def _first_text(msg):
    c = msg.get("content") if isinstance(msg, dict) else None
    if isinstance(c, str):
        return c
    if not isinstance(c, list):
        return ""
    for x in c:
        if isinstance(x, dict) and x.get("type") == "text" and isinstance(x.get("text"), str):
            return x["text"]
    return ""


def _epoch(iso):
    """ISO 시각 → epoch 초. 못 읽으면 None"""
    try:
        s = str(iso or "")
        if not s:
            return None
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return None


_CMD_RE = re.compile(r"^\s*<(local-command|command-)")
_API_ERR_RE = re.compile(r"^\s*API Error")


def _entry_state(e):
    """대화 줄 하나의 상태. 사람이 친 게 아닌 기록용 user 줄은 None"""
    msg = e.get("message") if isinstance(e.get("message"), dict) else {}
    if e.get("type") == "user":
        text = _user_text(msg)
        if "[Request interrupted by user" in text:
            return {"type": "user", "at": _epoch(e.get("timestamp")), "end_turn": False,
                    "interrupted": True, "api_error": False}
        if e.get("isMeta") is True or _CMD_RE.match(text):
            return None
        return {"type": "user", "at": _epoch(e.get("timestamp")), "end_turn": False,
                "interrupted": False, "api_error": False}
    if e.get("type") != "assistant":
        return None
    return {
        "type": "assistant",
        "at": _epoch(e.get("timestamp")),
        "end_turn": msg.get("stop_reason") == "end_turn",
        "interrupted": False,
        "api_error": e.get("isApiErrorMessage") is True or bool(_API_ERR_RE.match(_first_text(msg))),
    }


def _new_acc():
    # open_tools: 아직 tool_result 로 닫히지 않은 tool_use id
    return {"events": [], "last": None, "cwd": "", "open_tools": set()}


def _absorb(acc, e):
    """대화 줄 하나를 누적값에 더한다 — 앞에서 뒤 순서로"""
    if isinstance(e.get("cwd"), str) and e["cwd"]:
        acc["cwd"] = e["cwd"]
    msg = e.get("message") if isinstance(e.get("message"), dict) else {}
    content = msg.get("content")
    # 도구 호출 열고 닫기 추적
    if e.get("type") == "assistant" and isinstance(content, list):
        for b in content:
            if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("id"):
                acc["open_tools"].add(str(b["id"]))
        if msg.get("stop_reason") == "end_turn":
            acc["open_tools"].clear()
    elif e.get("type") == "user":
        closed_any = False
        if isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    closed_any = True
                    acc["open_tools"].discard(str(b.get("tool_use_id") or ""))
        st_tmp = _entry_state(e)
        # 사람이 새로 친 말(도구 결과가 아님)이면 앞선 미해결 호출은 버려진 것
        if st_tmp is not None and not closed_any and not st_tmp.get("interrupted"):
            acc["open_tools"].clear()
    st = _entry_state(e)
    if st is not None:
        acc["last"] = st
    if e.get("type") == "assistant" and isinstance(content, list):
        for block in content:
            act = describe(block)
            if act:
                acc["events"].append({"at": str(e.get("timestamp") or ""), "k": act["k"], "a": act["a"]})
        if len(acc["events"]) > LOG_N:
            del acc["events"][: len(acc["events"]) - LOG_N]


_TYPE_HEAD = b'{"type":"'
_NEEDLES = (b'"type":"assistant"', b'"type":"user"')
_HEAD_OK = (b'assistant"', b'user"')


def _candidate(line):
    """파싱할 가치가 있는 줄인가 — 큰 기록용 줄을 매번 json.loads 하지 않게 바이트에서 거른다"""
    if line.startswith(_TYPE_HEAD):
        rest = line[len(_TYPE_HEAD):]
        return any(rest.startswith(h) for h in _HEAD_OK)
    return any(n in line for n in _NEEDLES)


def _scan(buf, drop_first):
    """바이트 덩어리 → 누적값. 끝의 줄바꿈 없는 줄(아직 쓰는 중)은 건드리지 않는다"""
    acc = _new_acc()
    found = 0
    pos = 0
    if drop_first:
        nl = buf.find(b"\n")
        pos = len(buf) if nl < 0 else nl + 1
    while True:
        nl = buf.find(b"\n", pos)
        if nl < 0:
            break
        line = buf[pos:nl]
        pos = nl + 1
        if not _candidate(line):
            continue
        try:
            e = json.loads(line.decode("utf-8", errors="replace"))
        except Exception:
            continue
        if isinstance(e, dict) and e.get("type") in ("assistant", "user"):
            found += 1
            _absorb(acc, e)
    return acc, found


def _empty():
    return {"doing": None, "log": [], "last": None, "cwd": ""}


def _to_info(acc):
    events = acc["events"][-LOG_N:]
    last = acc["last"]
    if last is not None:
        last = dict(last)
        last["unresolved_tool"] = bool(acc["open_tools"]) and not last.get("interrupted")
    doing = {"k": events[-1]["k"], "a": events[-1]["a"]} if events else None
    return {"doing": doing, "log": events, "last": last, "cwd": acc["cwd"]}


def read_tail(path):
    """대화 파일 하나 → {doing, log:[{at,k,a}], last, cwd}. 파일이 그대로면 캐시"""
    if not path:
        return _empty()
    p = str(path)
    try:
        with open(p, "rb") as f:
            st = os.fstat(f.fileno())
            key = (st.st_ino, st.st_size, st.st_mtime)
            hit = _cache.get(p)
            if hit is not None and hit[0] == key:
                return hit[1]
            size = st.st_size
            acc = _new_acc()
            for w in WINDOWS:
                start = max(0, size - w)
                f.seek(start)
                buf = f.read(size - start)
                acc, found = _scan(buf, start > 0)
                if (found > 0 and len(acc["events"]) >= LOG_N and acc["last"] is not None) or start == 0:
                    break
            info = _to_info(acc)
            if len(_cache) >= CACHE_MAX:
                _cache.clear()
            _cache[p] = (key, info)
            return info
    except Exception:
        return _empty()


def subagent_running(path, now=None):
    """서브에이전트가 아직 일하는가 — 마지막 대화 줄이 end_turn(또는 API 오류)이 아니면 일하는 중"""
    now = time.time() if now is None else now
    try:
        st = os.stat(path)
    except Exception:
        return False
    if now - st.st_mtime > SUB_QUIET_SEC:
        return False
    last = read_tail(path)["last"]
    if not last:
        return True  # 막 생겨 아직 쓴 게 없다 — 출근 중으로 본다
    return not (last["type"] == "assistant" and (last["end_turn"] or last["api_error"]))


def _read_meta(path):
    try:
        mp = str(path)[: -len(".jsonl")] + ".meta.json"
        with open(mp, "r", encoding="utf-8") as f:
            m = json.load(f)
        return m if isinstance(m, dict) else {}
    except Exception:
        return {}


def running_subagents(transcript_path, now=None):
    """그 대화가 띄운 서브에이전트 중 지금 일하는 것 — 먼저 출근한 순서. 원소 {id,type,desc,doing}"""
    now = time.time() if now is None else now
    if not transcript_path:
        return []
    tp = str(transcript_path)
    if tp.endswith(".jsonl"):
        tp = tp[: -len(".jsonl")]
    folder = Path(tp) / "subagents"
    try:
        names = [n for n in os.listdir(folder) if n.startswith("agent-") and n.endswith(".jsonl")]
    except Exception:
        return []
    found = []
    for n in names:
        f = folder / n
        try:
            if not subagent_running(f, now):
                continue
            st = os.stat(f)
            born = getattr(st, "st_birthtime", None) or st.st_ctime
            meta = _read_meta(f)
            found.append((born, {
                "id": n[len("agent-"): -len(".jsonl")],
                "type": str(meta.get("agentType") or ""),
                "desc": one_line(meta.get("description"), 60),
                "doing": read_tail(f)["doing"],
            }))
        except Exception as e:  # 한 개가 이상해도 나머지는 낸다
            print(f"[activity] 서브에이전트 건너뜀 {n}: {e}", file=sys.stderr)
            continue
    found.sort(key=lambda x: x[0])
    return [x[1] for x in found]
