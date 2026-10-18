# -*- coding: utf-8 -*-
"""아침 자동작업 점검 → 문제 있으면 카톡 '나에게 보내기'.

점검 항목(하나 실패해도 나머지는 계속):
  ① 판매상품 잠금(sold-lock) 어제치 결과 존재·실패마켓
  ② 물갈이(Aside) 오늘 진행 상태 — blocked·미시작
  ③ 예약관리자 — 오늘 업무판 날짜넘기기·최근 연동이 돌았는지
  ④ 구글 인증(gws) — 업무판 1칸 읽기
  ⑤ 불사자 MCP — 계정 프로필 조회
  ⑥ 카톡 refresh 토큰 남은 기간(7일 미만 경고)
문제 0건이면 조용히 끝(월요일만 '정상 작동 중' 한 줄).

실행: .venv/bin/python3 .claude/skills/auto-watch/scripts/watch.py [--dry-run] [--always]
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WS = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(WS, ".claude", "lib"))
KST = timezone(timedelta(hours=9))
DATA = os.path.expanduser("~/python_work/data")
ASIDE_STATE = os.path.expanduser("~/.aside/u/0/routines/bulsaja-smartstore-refresh/state.json")
SCHED_STATE = os.path.join(DATA, "scheduler", "state.json")
KNOWN_STOPPED = {"15-3"}  # 정지로 알고 있는 마켓 — 토큰 실패를 알림하지 않는다


def _json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def check_sold_lock(now):
    d = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    p = os.path.join(DATA, "sold-lock", d, "result.json")
    if not os.path.exists(p):
        return [f"잠금: {d[5:]}치 결과 없음 (00:01 실행 안 됨)"]
    r = _json(p)
    if not r.get("finished_at"):
        return [f"잠금: {d[5:]}치 중간에 멈춤"]
    bad = [no for no, m in (r.get("markets") or {}).items()
           if (m or {}).get("status") not in (None, "ok") and no not in KNOWN_STOPPED]
    out = []
    if bad:
        out.append(f"잠금: 조회 실패 마켓 {', '.join(bad[:6])}")
    if (r.get("board") or {}).get("status") == "failed":
        out.append("잠금: 업무판 기록 실패(구글 인증?)")
    return out


def check_mulgari(now):
    today = now.strftime("%Y-%m-%d")
    s = _json(ASIDE_STATE)
    ip = s.get("inProgress")
    # 막힘 판정: stage 이름에 blocked/required 가 있거나, 마지막 이력 결과가 blocked
    last = (s.get("history") or [{}])[-1]
    stage = str((ip or {}).get("stage") or "")
    if ip and ("blocked" in stage or "required" in stage or last.get("result") == "blocked"):
        return [f"물갈이: {ip.get('marketNumber')} 막힘({stage})"]
    if s.get("lastStartedLocalDate") != today and not ip:
        return [f"물갈이: 오늘 시작 안 함(마지막 시작 {s.get('lastStartedLocalDate')})"]
    return []


def check_scheduler(now):
    st = _json(SCHED_STATE)
    out = []
    if now.hour >= 5 and (st.get("board-rollover") or {}).get("last_key") != now.strftime("%Y-%m-%d"):
        out.append("예약관리자: 오늘 업무판 날짜넘기기 안 돔")
    last = (st.get("board-sync") or {}).get("started_at")
    if not last or datetime.fromisoformat(last) < now - timedelta(hours=3):
        out.append("예약관리자: 업무판 연동 3시간 넘게 멈춤")
    return out


def check_gws():
    from eroomlib.config import cfg
    from eroomlib import gsheets
    gsheets.sheets_get(cfg("sheets.work_board", required=True), "'오늘'!A1:A1", max_retries=1)
    return []


def check_bulsaja():
    from eroomlib.snapshot import ProductMCP
    r = ProductMCP().call_tool("bulsaja_my_profile", {})
    if "부킹" not in json.dumps(r, ensure_ascii=False):
        return ["불사자: 연결 계정이 부킹이 아님"]
    return []


def check_kakao():
    from eroomlib import kakao
    left = kakao.refresh_days_left()
    if left is not None and left < 7:
        return [f"카톡: 인증 {int(left)}일 남음 — 재인증 필요"]
    return []


CHECKS = [("잠금", check_sold_lock, True), ("물갈이", check_mulgari, True),
          ("예약관리자", check_scheduler, True), ("구글 인증", check_gws, False),
          ("불사자", check_bulsaja, False), ("카톡", check_kakao, False)]


def run_checks(now):
    problems = []
    for name, fn, needs_now in CHECKS:
        try:
            problems += fn(now) if needs_now else fn()
        except Exception as e:
            problems.append(f"{name}: 점검 실패 {type(e).__name__}: {str(e)[:60]}")
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description="아침 자동작업 점검 → 카톡")
    ap.add_argument("--dry-run", action="store_true", help="카톡 안 보내고 출력만")
    ap.add_argument("--always", action="store_true", help="문제 없어도 보낸다")
    a = ap.parse_args(argv)
    now = datetime.now(KST)
    problems = run_checks(now)
    if problems:
        msg = f"⚠️ 자동작업 점검 {now:%m-%d %H:%M}\n" + "\n".join("· " + p for p in problems)
    elif a.always or now.weekday() == 0:
        msg = f"✅ 자동작업 정상 ({now:%m-%d}) — 잠금·물갈이·업무판·인증 이상 없음"
    else:
        print("[watch] 이상 없음")
        return 0
    print(msg)
    if a.dry_run:
        return 0
    try:
        from eroomlib import kakao
        kakao.send_me(msg)
    except Exception as e:
        print(f"[watch] 카톡 발송 실패: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
