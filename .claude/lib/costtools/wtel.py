#!/usr/bin/env python3
"""워커 텔레메트리 집계 — `.output` JSONL 에서 **usage 필드만** 읽는다.

**본문은 절대 안 읽는다.** 그 파일은 서브에이전트 전체 트랜스크립트라 통째로 열면
호출자 컨텍스트가 넘친다. 여기서 파싱해 숫자만 남기는 게 이 스크립트의 존재 이유다.

사용:
  python wtel.py <라벨>=<agentId> [<라벨>=<agentId> ...]
  python wtel.py --turns <agentId>            # 한 워커의 턴별 과금
  python wtel.py --scan [--minutes N]         # 최근 N분 안에 끝난 워커 전부 합산
                                              # (팬아웃 실측용 — agentId 를 손으로 안 모아도 된다)
                                              # 기본은 **현재 세션만**
                     [--session <id>]         # 다른 세션을 지정해서 재기
                     [--all-sessions]         # 전 세션 합산(섞이면 경고 + 세션별 내역)
  python wtel.py --dir <transcriptDir> [--rate N]
                                              # **한 워크플로 run 만** 집계 (Workflow 도구가
                                              # 돌려주는 Transcript dir). mtime 창에 기대는
                                              # --scan 과 달리 run 경계가 정확해서, 두 군을
                                              # 동시에 돌려도 안 섞인다 — 모델 A/B 는 이걸 쓴다.
"""
import json
import os
import sys

# 세션마다 tasks 디렉터리가 다르다 → agentId 로 실제 위치를 찾는다(EROOM_TASKS 로 고정 가능).
_BASE = "/private/tmp/claude-501/-Users-eunji-Desktop-eroom-studio"


def _find(agent_id):
    import glob
    env = os.environ.get("EROOM_TASKS")
    if env and os.path.exists(os.path.join(env, agent_id + ".output")):
        return os.path.join(env, agent_id + ".output")
    hits = glob.glob(os.path.join(_BASE, "*", "tasks", agent_id + ".output"))
    return hits[0] if hits else None


def usages(agent_id):
    """(턴수, [usage dict...]) — agentId 로 파일을 찾아 집계. 본문은 안 읽는다."""
    path = _find(agent_id)
    return usages_path(path) if path else (0, [])


def usages_path(path):
    """(턴수, [usage dict...]) — assistant 메시지의 usage 만. **중복 제거 필수.**

    JSONL 에는 한 턴이 스트리밍 스냅샷으로 여러 줄 기록된다 —
    `(cache_read, cache_creation)` 이 같고 `output_tokens` 만 자라는 연속 줄이 한 턴이다.
    그냥 세면 턴 수도 토큰도 몇 배로 부풀려진다(대조군 29줄 = 실제 8턴).
    연속 구간마다 출력이 가장 큰 줄(=그 턴의 최종 상태)만 남긴다.
    """
    raw = []
    with open(path, encoding="utf-8") as f:
        for ln in f:
            try:
                d = json.loads(ln)
            except Exception:      # 깨진 줄 하나가 집계를 막지 않는다
                continue
            # 백그라운드 Bash 로그 등은 dict 가 아닌 줄이 섞인다 — 워커 로그가 아니다
            if not isinstance(d, dict) or d.get("type") != "assistant":
                continue
            raw.append((d.get("message") or {}).get("usage") or {})

    out, cur = [], None
    for u in raw:
        key = (u.get("cache_read_input_tokens") or 0,
               u.get("cache_creation_input_tokens") or 0)
        if cur is not None and cur[0] == key:
            if (u.get("output_tokens") or 0) >= (cur[1].get("output_tokens") or 0):
                cur = (key, u)          # 같은 턴의 더 뒤 스냅샷
            continue
        if cur is not None:
            out.append(cur[1])
        cur = (key, u)
    if cur is not None:
        out.append(cur[1])
    return len(out), out


def total(u_list, key):
    return sum((u.get(key) or 0) for u in u_list)


# 과금 가중치 — 기본 입력 1 기준. 근거: 팬아웃-비용.md §①
W_READ, W_WRITE, W_OUT = 0.1, 1.25, 5.0


# Workflow 팬아웃 워커는 `tasks/*.output` 이 아니라 세션 트랜스크립트 아래에 쌓인다
# (2026-08-07 실측: --scan 이 워커 23명을 통째로 놓치고 무관한 백그라운드 Bash 로그 9개를
#  집계하려다 죽었다). Agent 도구 팬아웃(폴백 모드 A)은 tasks/ 쪽이라 **둘 다** 본다.
_PROJ = os.path.expanduser("~/.claude/projects/-Users-eunji-Desktop-eroom-studio")


def _session_of(path):
    """워커 로그 경로 → 그 워커를 띄운 세션 라벨. 못 알아보면 `?`.

    Workflow 워커는 `<프로젝트>/<세션id>/subagents/…` 아래라 세션이 경로에 있다.
    `tasks/*.output` 쪽은 id 체계가 달라(같은 세션이 다른 id를 쓴다) 묶지 않고 `tasks`.
    """
    if path.startswith(_PROJ + os.sep):
        return path[len(_PROJ) + 1:].split(os.sep)[0]
    return "tasks"


def _scan(minutes, session=None):
    """최근 N분 안에 수정된 워커 로그를 전부 모은다 — 팬아웃 한 판의 워커 전체.

    ① `tasks/*.output` (Agent 도구 서브에이전트) — 가장 최근에 쓰인 tasks 디렉터리
    ② `<세션id>/subagents/**/agent-*.jsonl` (Workflow 워커)

    `session` 은 ②를 그 세션으로 좁힌다. **기본값이 현재 세션**(`CLAUDE_CODE_SESSION_ID`)
    인 이유: 같은 프로젝트에서 다른 세션이 동시에 돌면 그 워커가 조용히 섞인다
    (2026-08-07 실측 — 3단계 측정에 남의 워커 5명이 들어와 $9.87 이 $11.46 으로 +16%).
    전 세션을 합치려면 `--all-sessions`(session="*").
    EROOM_TASKS 를 주면 ①을 그 경로로 고정하고 ②는 건너뛴다.
    """
    import glob
    import time
    cutoff = time.time() - minutes * 60
    fixed = os.environ.get("EROOM_TASKS")
    srcs, hits = [], []
    if fixed:
        srcs.append(os.path.join(fixed, "*.output"))
    else:
        dirs = glob.glob(os.path.join(_BASE, "*", "tasks"))
        if dirs:
            srcs.append(os.path.join(max(dirs, key=os.path.getmtime), "*.output"))
        srcs.append(os.path.join(_PROJ, session or "*", "subagents", "**",
                                 "agent-*.jsonl"))
    for pat in srcs:
        hits += [p for p in glob.glob(pat, recursive=True)
                 if os.path.getmtime(p) >= cutoff]
    return " + ".join(srcs), sorted(hits, key=os.path.getmtime)


def _weighted(cr, cw, ot):
    return cr * W_READ + cw * W_WRITE + ot * W_OUT


def cmd_scan(minutes, rate=3.0, session=None):
    # rate = 모델의 기본 입력 단가($/M). Sonnet 3 · Haiku 1 — 모델 A/B 때 넘긴다.
    d, paths = _scan(minutes, session)
    if not paths:
        print(f"최근 {minutes}분 안에 끝난 워커가 없다"
              + (f" ({d})" if d else " — tasks 디렉터리를 못 찾았다"))
        return
    tt = tcr = tcw = tot = 0
    n = 0
    by_sess = {}
    for p in paths:
        turns, us = usages_path(p)
        if not turns:
            continue          # 워커 로그가 아닌 파일(백그라운드 Bash 로그 등)
        n += 1
        cr = total(us, "cache_read_input_tokens")
        cw = total(us, "cache_creation_input_tokens")
        ot = total(us, "output_tokens")
        tt += turns; tcr += cr; tcw += cw; tot += ot
        s = by_sess.setdefault(_session_of(p), [0, 0.0])
        s[0] += 1
        s[1] += _weighted(cr, cw, ot)
    print(f"{d}\n최근 {minutes}분 · 워커 {n}명 (후보 파일 {len(paths)}개)\n")
    # 여러 세션이 섞였으면 **조용히 합치지 않는다** — 어느 세션 몫인지 보여준다.
    if len(by_sess) > 1:
        print("⚠ 세션이 둘 이상 섞였다 — 다른 세션의 팬아웃이 들어왔는지 확인할 것")
        for k, (cnt, w_) in sorted(by_sess.items(), key=lambda x: -x[1][1]):
            print(f"    {k:40} 워커 {cnt:>3}명 · 가중 {w_:>12,.0f}")
        print("    (현재 세션만 보려면 --session <id>, 전부 합치려면 --all-sessions)\n")
    print(f"{'턴 합계':12} {tt:>12,}")
    print(f"{'캐시읽기':12} {tcr:>12,}  ×0.1  = {tcr * W_READ:>12,.0f}")
    print(f"{'캐시쓰기':12} {tcw:>12,}  ×1.25 = {tcw * W_WRITE:>12,.0f}")
    print(f"{'출력':12} {tot:>12,}  ×5    = {tot * W_OUT:>12,.0f}")
    w = _weighted(tcr, tcw, tot)
    print(f"\n{'가중 총합':12} {w:>12,.0f}   ← 게이트는 이 값이다(토큰 수 아님)")
    label = {3.0: "Sonnet 환산", 1.0: "Haiku 환산"}.get(rate, "환산")
    print(f"{label:12} ${w * rate / 1e6:>11,.2f}   (기본 입력 ${rate:g}/M)")


def cmd_dir(tdir, rate=3.0):
    """워크플로 transcript dir 하나만 집계 — run 경계가 파일 위치로 확정된다.

    `--scan` 은 mtime 창으로 고르기 때문에 두 군을 연달아/동시에 돌리면 섞인다.
    Workflow 도구가 돌려주는 Transcript dir 를 그대로 넘기면 그 run 의 워커만 잡힌다.
    """
    import glob
    paths = sorted(glob.glob(os.path.join(tdir, "**", "agent-*.jsonl"), recursive=True))
    tt = tcr = tcw = tot = n = 0
    rows = []
    for p in paths:
        turns, us = usages_path(p)
        if not turns:
            continue
        cr = total(us, "cache_read_input_tokens")
        cw = total(us, "cache_creation_input_tokens")
        ot = total(us, "output_tokens")
        n += 1
        tt += turns; tcr += cr; tcw += cw; tot += ot
        rows.append((os.path.basename(p)[:24], turns, cr, cw, ot,
                     us[0].get("cache_read_input_tokens", 0)
                     + us[0].get("cache_creation_input_tokens", 0)))
    if not n:
        print(f"워커 로그가 없다: {tdir}")
        return
    print(f"{tdir}\n워커 {n}명\n")
    print(f"{'워커':26} {'턴':>4} {'캐시읽기':>11} {'캐시쓰기':>10} {'출력':>8} {'첫턴컨텍스트':>10}")
    for r in rows:
        print(f"{r[0]:26} {r[1]:>4} {r[2]:>11,} {r[3]:>10,} {r[4]:>8,} {r[5]:>10,}")
    w = _weighted(tcr, tcw, tot)
    print(f"\n{'턴 합계':12} {tt:>12,}")
    print(f"{'캐시읽기':12} {tcr:>12,}  ×0.1  = {tcr * W_READ:>12,.0f}")
    print(f"{'캐시쓰기':12} {tcw:>12,}  ×1.25 = {tcw * W_WRITE:>12,.0f}")
    print(f"{'출력':12} {tot:>12,}  ×5    = {tot * W_OUT:>12,.0f}")
    print(f"\n{'가중 총합':12} {w:>12,.0f}")
    print(f"{'실비':12} ${w * rate / 1e6:>11,.4f}   (기본 입력 ${rate:g}/M)")
    print("※ 모델이 다른 두 run 을 비교할 땐 가중 총합이 아니라 이 실비로 본다.")
    mids = sorted(r[5] for r in rows)
    print(f"※ 첫 턴 컨텍스트 중앙값 {mids[len(mids) // 2]:,} (고정비)")


def main():
    if sys.argv[1:2] == ["--dir"]:
        rate = 3.0
        if "--rate" in sys.argv:
            rate = float(sys.argv[sys.argv.index("--rate") + 1])
        cmd_dir(sys.argv[2], rate)
        return
    if sys.argv[1:2] == ["--scan"]:
        mins = 120
        rate = 3.0
        if "--minutes" in sys.argv:
            mins = float(sys.argv[sys.argv.index("--minutes") + 1])
        if "--rate" in sys.argv:
            rate = float(sys.argv[sys.argv.index("--rate") + 1])
        # 기본은 **현재 세션만**. 남의 세션 워커가 조용히 섞이는 쪽이 더 위험하다.
        sess = os.environ.get("CLAUDE_CODE_SESSION_ID") or None
        if "--all-sessions" in sys.argv:
            sess = None
        elif "--session" in sys.argv:
            sess = sys.argv[sys.argv.index("--session") + 1]
        cmd_scan(mins, rate, session=sess)
        return
    if sys.argv[1:2] == ["--turns"]:
        turns, us = usages(sys.argv[2])
        print(f"{'턴':>3} {'캐시읽기':>10} {'캐시쓰기':>10} {'출력':>7}  {'컨텍스트':>10}")
        for i, u in enumerate(us, 1):
            cr = u.get("cache_read_input_tokens") or 0
            cw = u.get("cache_creation_input_tokens") or 0
            print(f"{i:>3} {cr:>10,} {cw:>10,} {u.get('output_tokens', 0):>7,} {cr + cw:>10,}")
        return

    rows = []
    for arg in sys.argv[1:]:
        label, _, aid = arg.partition("=")
        turns, us = usages(aid)
        cr = total(us, "cache_read_input_tokens")
        cw = total(us, "cache_creation_input_tokens")
        ot = total(us, "output_tokens")
        rows.append((label, turns, cr, cw, ot, cr + cw + ot))

    print(f"{'군':10} {'턴':>4} {'캐시읽기':>12} {'캐시쓰기':>10} {'출력':>8} {'합계':>12}")
    for r in rows:
        print(f"{r[0]:10} {r[1]:>4} {r[2]:>12,} {r[3]:>10,} {r[4]:>8,} {r[5]:>12,}")
    if len(rows) == 2:
        a, b = rows
        for i, name in ((1, "턴"), (2, "캐시읽기"), (5, "합계")):
            if a[i]:
                print(f"  {name} 변화: {a[i]:,} → {b[i]:,} "
                      f"({(b[i] - a[i]) * 100 / a[i]:+.1f}%)")


if __name__ == "__main__":
    main()
