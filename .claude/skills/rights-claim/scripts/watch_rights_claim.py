#!/usr/bin/env python3
"""rights-claim 감시 실행기 — 매시 정각 즈음 스케줄러가 부른다.

- 소명요청을 처리하고, 실패하면 다음 시간(1시간 뒤)에 재시도한다.
- 최초 시도 + 재시도 2번(총 3회)까지 실패하면 용팀장 폰으로 전화(call-me)한다. 전화는 접수번호당 1번.
- 상태는 ~/python_work/data/rights-claim/watch_state.json 에 남긴다.
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
DATA = os.path.expanduser("~/python_work/data/rights-claim")
STATE = os.path.join(DATA, "watch_state.json")
LEDGER = os.path.join(DATA, "ledger.jsonl")
CALL = os.path.expanduser("~/.claude/skills/call-me/call.py")
MAX_ATTEMPTS = 3   # 최초 1 + 재시도 2


def load_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(st):
    try:
        os.makedirs(DATA, exist_ok=True)
        with open(STATE, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, indent=1)
    except OSError as e:
        print(f"[watch] 상태 저장 실패: {e}", flush=True)


def read_rows():
    rows = []
    try:
        with open(LEDGER, encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    return rows


def phone_call(rows_failed):
    names = ", ".join(f"{r.get('reporter','?')}의 {r.get('right_name','?')}" for r in rows_failed)
    q = (f"권리침해 소명이 {MAX_ATTEMPTS}번 시도했는데도 자동으로 안 됐어. {names} 건이야. "
         f"기한이 3일이라 직접 확인해야 해. 컴퓨터 앞에서 클로드한테 소명요청 처리해 달라고 말해 줘.")
    try:
        out = subprocess.run([PY, CALL, "call", "--question", q,
                              "--voicemail", "권리침해 소명 자동 처리가 계속 실패했어. 클로드에게 확인하라고 해 줘."],
                             capture_output=True, text=True, timeout=120)
        print(f"[watch] 전화 결과: {out.stdout.strip()[:300]} {out.stderr.strip()[:200]}", flush=True)
        cid = ""
        try:
            cid = json.loads(out.stdout).get("call_id") or ""
        except ValueError:
            pass
        if cid:   # 안 받으면 wait 가 ntfy 푸시를 보낸다
            subprocess.run([PY, CALL, "wait", cid, "--timeout", "300"], capture_output=True, text=True, timeout=400)
        return "success" in out.stdout
    except Exception as e:
        print(f"[watch] 전화 실패: {type(e).__name__}: {e}", flush=True)
        return False


def main():
    st = load_state()
    exhausted = [rc for rc, v in st.items() if v.get("attempts", 0) >= MAX_ATTEMPTS]
    before = len(read_rows())
    cmd = [PY, os.path.join(HERE, "run_rights_claim.py"), "--apply"]
    if exhausted:
        cmd += ["--skip-receipts", ",".join(exhausted)]
    rc = subprocess.run(cmd).returncode
    new_rows = read_rows()[before:]
    latest = {}
    for r in new_rows:
        latest[r.get("receipt")] = r
    need_call = []
    for receipt, r in latest.items():
        if not receipt:
            continue
        if r.get("status") == "done":
            st.pop(receipt, None)
            continue
        v = st.setdefault(receipt, {"attempts": 0})
        v["attempts"] += 1
        v["last_ts"] = time.strftime("%Y-%m-%d %H:%M:%S")
        v["reporter"], v["right_name"] = r.get("reporter"), r.get("right_name")
        print(f"[watch] {receipt} 미완료 — 시도 {v['attempts']}/{MAX_ATTEMPTS}", flush=True)
        if v["attempts"] >= MAX_ATTEMPTS and not v.get("called"):
            need_call.append((receipt, r))
    if need_call:
        ok = phone_call([r for _, r in need_call])
        for receipt, _ in need_call:
            st[receipt]["called"] = bool(ok) or True   # 걸림 여부와 무관하게 1회만 시도(반복 전화 방지)
            st[receipt]["call_ok"] = bool(ok)
    save_state(st)
    return rc


if __name__ == "__main__":
    sys.exit(main())
