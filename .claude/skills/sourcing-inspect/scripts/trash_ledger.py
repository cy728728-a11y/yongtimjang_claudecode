#!/usr/bin/env python3
"""불사자 휴지통 사유 대장 — 누가·언제·왜 휴지통에 넣었는지 남기고 찾는다.

소싱기(캠페인) 상품에는 메모 칸이 없다(2026-11-04 웹 화면 코드 확인). 그래서 휴지통에 넣을 때
사유를 이 대장(jsonl, 한 줄 = 상품 하나)에 남긴다. 상품관리 상품은 불사자 메모에도 사유를 적는다.

사용:
  trash_ledger.py find <문서ID 또는 상품번호> [...]   # 휴지통 사유 조회
  trash_ledger.py backfill                           # 지난 검수 run 의 휴지통 기록을 대장으로 옮김(한 번만)
"""
import argparse
import glob
import json
import os
import sys
import time

LEDGER = os.path.expanduser("~/python_work/data/bulsaja-trash-ledger.jsonl")
RUNS = os.path.expanduser("~/python_work/data/sourcing-inspect/runs")


def now():
    return time.strftime("%Y-%m-%d %H:%M")


def append(rows):
    """rows: [{id, by, reason, note?, run?, at?}] — 대장 끝에 덧붙인다."""
    if not rows:
        return
    try:
        os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
        with open(LEDGER, "a", encoding="utf-8") as f:
            for r in rows:
                r = {"at": now(), **r}
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    except OSError as e:
        print(f"[대장] 기록 실패: {e}", file=sys.stderr)


def cmd_find(a):
    keys = set(a.ids)
    hit = 0
    try:
        with open(LEDGER, encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                pid = str(r["id"]).split("-")[-1]
                if r["id"] in keys or pid in keys:
                    hit += 1
                    print(json.dumps(r, ensure_ascii=False))
    except FileNotFoundError:
        print("대장 없음")
    if not hit:
        print("기록 없음 — 이 대장이 생기기 전에 다른 경로로 지워졌을 수 있다")


def cmd_backfill(a):
    """각 run 의 apply_trash*.jsonl(성공분) + verdicts.json 사유 → 대장. 이미 있는 id 는 건너뜀."""
    seen = set()
    try:
        with open(LEDGER, encoding="utf-8") as f:
            seen = {json.loads(l)["id"] for l in f if l.strip()}
    except FileNotFoundError:
        pass
    rows = []
    for ck in sorted(glob.glob(f"{RUNS}/*/apply_trash*.jsonl")):
        d = os.path.dirname(ck)
        run = os.path.basename(d)
        try:
            v = json.load(open(f"{d}/verdicts.json", encoding="utf-8"))
        except (OSError, ValueError):
            v = {}
        at = time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(ck)))
        unmatched = "unmatched" in os.path.basename(ck)
        with open(ck, encoding="utf-8") as f:
            for l in f:
                if not l.strip():
                    continue
                x = json.loads(l)
                if not x.get("ok", True) or x["id"] in seen:
                    continue
                seen.add(x["id"])
                vv = v.get(x["id"]) or {}
                reason = "매칭 실패(타오바오 이미지 매칭 안 됨)" if unmatched else (vv.get("reason") or "검수 탈락")
                rows.append({"id": x["id"], "at": at, "by": "sourcing-inspect 검수(Claude)",
                             "reason": reason, "note": vv.get("note", ""), "run": run, "backfill": True})
    append(rows)
    print(f"[대장] {len(rows)}건 추가 → {LEDGER}")


def main():
    p = argparse.ArgumentParser()
    s = p.add_subparsers(dest="cmd", required=True)
    f = s.add_parser("find")
    f.add_argument("ids", nargs="+")
    f.set_defaults(fn=cmd_find)
    s.add_parser("backfill").set_defaults(fn=cmd_backfill)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
