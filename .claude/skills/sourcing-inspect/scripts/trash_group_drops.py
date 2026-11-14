#!/usr/bin/env python3
"""
마켓그룹 상품(상품관리) 검수 탈락분 → 사유 메모 + 휴지통(SOURCE_ONLY, 영구삭제 아님).
fetch_group 로 만든 run 의 verdicts.json 중 drop 만 대상.

  1) 메모 맨 앞에 "[삭제] 날짜 · sourcing-inspect 재검수(Claude) · 사유코드 메모" 줄을 붙여 저장(기존 메모 보존)
  2) bulsaja_market_delete SOURCE_ONLY / scope ALL (200개씩)
  3) 휴지통 대장(~/python_work/data/bulsaja-trash-ledger.jsonl)에도 기록
대장: <run-dir>/trash_group.jsonl  {"step":"memo","id":..,"ok":..} / {"step":"trash","ids":[..],"ok":..}

사용법: python trash_group_drops.py --run-dir old_1007620_recheck [--limit N] [--rpm 100] [--workers 4]
"""
import argparse
import concurrent.futures
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import transfer_group as tg  # noqa: E402  (PacedMCP·two_step·Pace 재사용)
import trash_ledger  # noqa: E402
from run_inspect import resolve_run_dir  # noqa: E402

TODAY = datetime.date.today().isoformat()


def load_done(path):
    memo, trashed = set(), set()
    if os.path.exists(path):
        for ln in open(path, encoding="utf-8"):
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if r.get("step") == "memo":
                memo.add(r["id"])
            elif r.get("step") == "trash" and r.get("ok"):
                trashed |= set(r.get("ids") or [])
    return memo, trashed


def memo_line(v):
    note = (v.get("note") or "").replace("\n", " ")[:80]
    return f"[삭제] {TODAY} · sourcing-inspect 신규소싱상품 재검수(Claude) · {v.get('reason')} {note}".strip()


def put_memo(pid, v):
    """기존 메모 앞에 삭제 사유를 붙인다. 실패해도 삭제는 진행(대장에 ok=False)."""
    try:
        cur = (tg.mcp().call_tool("bulsaja_product_memo", {"productId": pid}) or {}).get("메모") or ""
        line = memo_line(v)
        if cur.startswith("[삭제]"):
            return True
        new = line + ("\n" + cur if cur else "")
        r = tg.mcp().call_tool("bulsaja_product_memo", {"productId": pid, "memo": new})
        tok = r.get("confirmationToken")
        if tok:
            r = tg.mcp().call_tool("bulsaja_product_memo", {"productId": pid, "memo": new,
                                                             "confirm": True, "confirmationToken": tok})
        return bool(r.get("success", True))
    except Exception as e:
        print(f"[memo] {pid} 실패: {e}")
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--rpm", type=int, default=100)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    tg.PACE = tg.Pace(a.rpm)
    rd = resolve_run_dir(a.run_dir)
    lp = os.path.join(rd, "trash_group.jsonl")
    try:
        verdicts = json.load(open(os.path.join(rd, "verdicts.json"), encoding="utf-8"))
    except Exception as e:
        sys.exit(f"verdicts.json 읽기 실패: {e}")
    drops = sorted(k for k, v in verdicts.items() if v.get("verdict") == "drop")
    if a.limit:
        drops = drops[:a.limit]
    memo_done, trashed = load_done(lp)
    todo = [d for d in drops if d not in trashed]
    print(f"[drops] 탈락 {len(drops)} / 남은 {len(todo)}", flush=True)

    led = open(lp, "a", encoding="utf-8")
    need = [d for d in todo if d not in memo_done]
    with concurrent.futures.ThreadPoolExecutor(a.workers) as ex:
        for i, (pid, ok) in enumerate(zip(need, ex.map(lambda p: put_memo(p, verdicts[p]), need)), 1):
            led.write(json.dumps({"step": "memo", "id": pid, "ok": ok}, ensure_ascii=False) + "\n")
            led.flush()
            if i % 200 == 0:
                print(f"[memo] {i}/{len(need)}", flush=True)

    for i in range(0, len(todo), tg.TRASH_CHUNK):
        chunk = todo[i:i + tg.TRASH_CHUNK]
        try:
            _, r = tg.two_step("bulsaja_market_delete", {"productIds": chunk, "deleteAction": "SOURCE_ONLY", "scope": "ALL"})
            ok = bool(r.get("success"))
        except Exception as e:
            ok, r = False, {"message": f"예외: {e}"}
        led.write(json.dumps({"step": "trash", "ids": chunk, "ok": ok, "msg": str(r.get("message"))[:120]},
                             ensure_ascii=False) + "\n")
        led.flush()
        if ok:
            trash_ledger.append([{"id": p, "by": "Claude sourcing-inspect 재검수", "reason": verdicts[p].get("reason"),
                                  "note": (verdicts[p].get("note") or "")[:120], "run": a.run_dir} for p in chunk])
        print(f"[trash] {i + len(chunk)}/{len(todo)} {r.get('message')}", flush=True)
    print("[drops] 끝")


if __name__ == "__main__":
    main()
