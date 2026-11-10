#!/usr/bin/env python3
"""소싱 수집 멈춤 감지 — 문제가 생기면 한 줄 출력하고 종료한다(백그라운드 실행 → 종료 = 알림).

  stall_alert.py --run-dir R --group-id 432 [--every 600] [--stall-min 60]

감지하는 것
  1) 상품 수집 감시(campaign_watch)의 기록(watch.log)이 25분 넘게 안 쌓임 → 감시 프로그램이 죽었다
  2) watch.log 의 상품 수가 stall-min 분 동안 그대로인데 '완료' 기록이 없음 → 수집이 멈췄다(맥북 잠듦·탭 닫힘 등)
  3) watch.log 에 조회 실패가 연속 3번 → 불사자 응답 문제
  4) 수집사이트 그룹(키워드 마켓수집 결과) 마켓 수가 stall-min 분 동안 그대로 → 다른 PC 마켓수집이 멈췄다
  5) watch.log 에 '완료' → 정상 종료(출력만, 폰 푸시 없음)
알림: 출력 한 줄 + 폰 푸시(1~4만)(ntfy, ~/.eroom/ntfy.json 있을 때). 대화 창이 닫혀 있어도 폰으로 간다.
"""
import argparse
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_inspect import resolve_run_dir, _p  # noqa: E402

def notify(text, ok=False):
    """출력 + 폰 푸시. 정상 완료(ok=True)는 푸시하지 않는다 — 폰 알림은 예상 못 한 멈춤만(2026-11-11 용팀장). 푸시 실패는 무시."""
    print(text, flush=True)
    if ok:
        return
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "lib"))
        from eroomlib.ntfy import send
        send("소싱 수집 완료" if ok else "소싱 수집 확인 필요", text, priority="default" if ok else "high",
             tags="white_check_mark" if ok else "warning")
    except Exception:
        pass


LINE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) (.*)$")


def parse_watch(lines):
    """watch.log 줄 → [(시각 epoch, 종류, 값)] 종류: count|fail|done"""
    out = []
    for ln in lines:
        m = LINE.match(ln.strip())
        if not m:
            continue
        t = time.mktime(time.strptime(m.group(1), "%Y-%m-%d %H:%M:%S"))
        msg = m.group(2)
        c = re.search(r"상품 (\d+)건$", msg)
        if "완료" in msg:
            out.append((t, "done", None))
        elif c:
            out.append((t, "count", int(c.group(1))))
        elif "실패" in msg or "오류" in msg or "만료" in msg:
            out.append((t, "fail", msg[:80]))
    return out


def judge_watch(events, now, stall_min):
    """문제 문장 또는 None."""
    if not events:
        return None
    if events[-1][1] == "done":
        return "DONE"
    if now - events[-1][0] > 25 * 60:
        return "감시 프로그램 기록이 25분 넘게 멈춤(감시가 죽었거나 맥북이 잠듦)"
    tail = [e for e in events if e[1] in ("count", "fail")][-3:]
    if len(tail) == 3 and all(e[1] == "fail" for e in tail):
        return f"불사자 조회 3번 연속 실패: {tail[-1][2]}"
    counts = [e for e in events if e[1] == "count"]
    if counts:
        last = counts[-1][2]
        since = [e for e in counts if e[2] == last][0][0]   # 이 숫자가 처음 나온 시각
        if now - since >= stall_min * 60:
            return f"상품 수가 {int((now - since) / 60)}분째 {last:,}건에서 안 늘어남(수집 멈춤?)"
    return None


def group_count(gid):
    import requests
    import sourcing_api as sa
    j = requests.post(sa.API + "/opensearch/proxy/marketinfo/list", json={"userId": 11154},
                      headers=sa._headers(sa.load_token()), timeout=180).json()
    return {g["groupId"]: g["count"] for g in j.get("groupCounts", [])}.get(gid)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir")
    ap.add_argument("--group-id", type=int)
    ap.add_argument("--every", type=int, default=600)
    ap.add_argument("--stall-min", type=int, default=60)
    a = ap.parse_args()
    gseen = None  # (값, 처음 본 시각)
    gfail = 0
    while True:
        now = time.time()
        if a.run_dir:
            try:
                with open(_p(resolve_run_dir(a.run_dir), "watch.log"), encoding="utf-8", errors="ignore") as f:
                    v = judge_watch(parse_watch(f.readlines()), now, a.stall_min)
            except FileNotFoundError:
                v = None
            if v == "DONE":
                notify("[상품수집] 완료 — 검수 단계로 넘어갈 차례", ok=True)
                return 0
            if v:
                notify(f"[상품수집] {v}")
                return 1
        if a.group_id:
            try:
                c = group_count(a.group_id)
                gfail = 0
                if gseen is None or c != gseen[0]:
                    gseen = (c, now)
                elif now - gseen[1] >= a.stall_min * 60:
                    notify(f"[마켓수집] 그룹 마켓 수가 {int((now - gseen[1]) / 60)}분째 {c:,}개에서 안 늘어남(다른 PC 확인)")
                    return 1
            except Exception as e:
                gfail += 1
                if gfail >= 3:
                    notify(f"[마켓수집] 그룹 조회 3번 연속 실패: {str(e)[:80]}")
                    return 1
        time.sleep(a.every)


if __name__ == "__main__":
    sys.exit(main())
