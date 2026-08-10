#!/usr/bin/env python3
"""워커 패킹 곡선 — "워커 1명에게 몇 건을 맡기는 게 싼가"를 실측으로 답한다.

워커 로그에서 **파생행만** 뽑아 CSV 에 쌓는다. 워커 프롬프트·반환 스키마는 건드리지 않는다
(그쪽에 계측을 심으면 고정비가 늘고, 반환 필드는 출력 ×5 라 제일 비싸다).

**조인 키는 배치 경로가 아니라 상품id다.** 배치 경로로 붙이려던 첫 시도는 실패했다 —
지시서에 예시로 적힌 경로를 집었고, 워커 1명이 배치를 3~8개 맡는다는 것도 놓쳤다.
로그에는 상품 이미지 경로(`/eroom-data/<축>/runs/<런>/thumbs/U01…_0.webp`)가 들어 있어서
**distinct 상품id 를 세면 그 워커가 맡은 건수**가 바로 나온다. 축·런도 같은 경로에서 뽑는다.

로그는 오래 안 남는다(구 `tasks/*.output` 은 /private/tmp 라 스캔 도중에도 사라졌다).
**팬아웃이 끝나면 바로 `--collect`** 를 돌려 CSV 로 굳힌다.

사용:
  python3 pack_curve.py --collect              # 로그 → CSV (멱등)
  python3 pack_curve.py --curve                # 축별 곡선
  python3 pack_curve.py --curve --axis product-name
  python3 pack_curve.py --curve --run yong3-2-t100
"""
import csv
import glob
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wtel  # noqa: E402  — usages_path·total·_weighted 재사용

CSV_PATH = os.path.expanduser("~/eroom-data/_telemetry/worker_packing.csv")
COLS = ("agent_id", "axis", "run", "items", "turns",
        "cache_read", "cache_write", "output", "weighted", "first_ctx", "collected_at")

PID = re.compile(r"\bU01[A-Z0-9]{15,30}\b")
# /Users/eunji/eroom-data/<축>/runs/<런>/...
AXIS = re.compile(r"/eroom-data/([a-z][a-z-]*)/runs/([^/\"'\s]+)")


def _sources():
    """워커 로그가 쌓이는 두 곳 — wtel._scan() 과 같은 규칙."""
    proj = os.path.expanduser("~/.claude/projects/-Users-eunji-Desktop-eroom-studio")
    out = glob.glob(os.path.join(proj, "*", "subagents", "**", "agent-*.jsonl"),
                    recursive=True)
    out += glob.glob(os.path.join(wtel._BASE, "*", "tasks", "*.output"))
    return out


def _scrape(path):
    """(상품id 집합, 축, 런) — 한 번만 읽는다. 본문은 메모리에 안 담는다."""
    pids, axis, run = set(), None, None
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            for ln in f:
                pids.update(PID.findall(ln))
                if axis is None:
                    m = AXIS.search(ln)
                    if m:
                        axis, run = m.group(1), m.group(2)
    except OSError:
        return set(), None, None      # 스캔 중 사라진 파일 — 조용히 넘긴다
    return pids, axis, run


def collect():
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    seen = set()
    rows = []
    if os.path.exists(CSV_PATH):
        with open(CSV_PATH, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                seen.add(r["agent_id"])
                rows.append(r)
    before = len(rows)

    stamp = time.strftime("%Y-%m-%d %H:%M")
    added = skipped = 0
    for p in _sources():
        aid = os.path.basename(p).rsplit(".", 1)[0]
        if aid.startswith("agent-"):
            aid = aid[len("agent-"):]
        if aid in seen:
            continue
        try:
            turns, us = wtel.usages_path(p)
        except OSError:
            continue
        if not turns:
            continue                  # 워커 로그가 아니다(백그라운드 Bash 출력 등)
        pids, axis, run = _scrape(p)
        if not pids or not axis:
            skipped += 1              # 상품을 안 다룬 워커(탐침·라우팅 등)
            continue
        u0 = us[0]
        rows.append({
            "agent_id": aid, "axis": axis, "run": run,
            "items": len(pids), "turns": turns,
            "cache_read": wtel.total(us, "cache_read_input_tokens"),
            "cache_write": wtel.total(us, "cache_creation_input_tokens"),
            "output": wtel.total(us, "output_tokens"),
            "weighted": round(wtel._weighted(
                wtel.total(us, "cache_read_input_tokens"),
                wtel.total(us, "cache_creation_input_tokens"),
                wtel.total(us, "output_tokens"))),
            "first_ctx": (u0.get("cache_read_input_tokens") or 0)
                         + (u0.get("cache_creation_input_tokens") or 0),
            "collected_at": stamp,
        })
        seen.add(aid)
        added += 1

    with open(CSV_PATH, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    print(f"{CSV_PATH}\n  기존 {before} + 신규 {added} = {len(rows)}행"
          f"  (상품 안 다룬 워커 {skipped}개 제외)")


def _load(axis=None, run=None):
    if not os.path.exists(CSV_PATH):
        print(f"CSV 가 없다 — 먼저 --collect ({CSV_PATH})")
        return []
    out = []
    with open(CSV_PATH, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if axis and r["axis"] != axis:
                continue
            if run and r["run"] != run:
                continue
            for k in ("items", "turns", "weighted", "first_ctx"):
                r[k] = int(float(r[k]))
            out.append(r)
    return out


def curve(axis=None, run=None, rate=3.0):
    rows = _load(axis, run)
    if not rows:
        print("해당 행이 없다")
        return
    from collections import defaultdict
    by_axis = defaultdict(list)
    for r in rows:
        by_axis[r["axis"]].append(r)

    for ax in sorted(by_axis):
        sub = by_axis[ax]
        runs = sorted({r["run"] for r in sub})
        fc = sorted(r["first_ctx"] for r in sub)
        print(f"── {ax}  워커 {len(sub)}명 · 상품슬롯 {sum(r['items'] for r in sub)} "
              f"· 런 {len(runs)}개 · 고정비중앙값 {fc[len(fc)//2]:,}")
        g = defaultdict(list)
        for r in sub:
            g[r["items"]].append(r)
        print(f"{'건/워커':>7} {'워커':>4} {'평균턴':>7} {'턴/건':>6} "
              f"{'건당가중':>10} {'건당$':>8}  비고")
        best = None
        for n in sorted(g):
            v = g[n]
            at = sum(x["turns"] for x in v) / len(v)
            aw = sum(x["weighted"] for x in v) / len(v)
            note = "(표본부족)" if len(v) < 3 else ""
            if not note and (best is None or aw / n < best[1]):
                best = (n, aw / n)
            print(f"{n:>7} {len(v):>4} {at:>7.1f} {at/n:>6.2f} "
                  f"{aw/n:>10,.0f} {aw/n*rate/1e6:>8.3f}  {note}")
        if best:
            print(f"   → 표본 3명 이상 구간의 최저: {best[0]}건/워커 "
                  f"(건당 ${best[1]*rate/1e6:.3f})")
        else:
            print("   → 표본 3명 이상인 구간이 없다. 판단하지 마라")
        print()


def main():
    a = sys.argv[1:]
    if "--collect" in a:
        collect()
        return
    if "--curve" in a:
        def opt(name):
            return a[a.index(name) + 1] if name in a else None
        curve(opt("--axis"), opt("--run"))
        return
    print(__doc__)


if __name__ == "__main__":
    main()
