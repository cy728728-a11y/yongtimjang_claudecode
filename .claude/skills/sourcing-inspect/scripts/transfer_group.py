#!/usr/bin/env python3
"""
검수 통과분을 다른 마켓그룹으로 옮긴다 (MCP).
  1) copy  : 통과 원본 → 대상 그룹 복사 (50개/회)
  2) price : 복사본 판매가를 대상 그룹 마진 설정으로 재계산 (원가 +1원 저장 → 원래 값 저장)
             원가가 바뀌어야만 서버가 재계산한다. 앱 '판매가 일괄 적용'과 원 단위까지 같음을 확인함.
  3) trash : 복사가 확인된 원본만 휴지통 (SOURCE_ONLY, 마켓 전체 범위). 영구삭제 아님.

대장: <run-dir>/transfer.jsonl (한 줄 = 한 사건, 재실행 시 이어받기)
  {"step":"copy","src":[...],"new":[...],"ok":true}   ← 청크 단위. 실패가 섞이면 ok=false 로 원본 휴지통 제외
  {"step":"price","new":id,"ok":true}
  {"step":"trash","src":[...],"ok":true}

사용법:
  python transfer_group.py --run-dir 1027_st1000 --dst-group 1008216 [--steps copy,price,trash] [--limit N]
  python transfer_group.py --run-dir 1027_st1000 --seed SRC=NEW      # 손으로 이미 옮긴 건 대장에 등록
"""
import argparse
import concurrent.futures
import json
import os
import sys
import threading
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
_d = HERE
while _d and _d != os.path.dirname(_d):
    if os.path.isdir(os.path.join(_d, "lib", "eroomlib")):
        sys.path.insert(0, os.path.join(_d, "lib"))
        break
    _d = os.path.dirname(_d)
sys.path.insert(0, HERE)

from eroomlib.bulsaja import BulsajaMCP  # noqa: E402
from run_inspect import resolve_run_dir  # noqa: E402

COPY_CHUNK = 50
TRASH_CHUNK = 200
SKU_CHUNK = 200  # 옵션 가격 변경은 한 번에 200개까지
_local = threading.local()
_lock = threading.Lock()


class Pace:
    """프로세스 전체 분당 호출 상한. 불사자 MCP 는 계정당 분당 240회(RateLimit-Policy 240;w=60)라
    조회 스크립트와 나눠 쓴다. 넘기면 429 로 서로 막혀 처리량이 오히려 떨어진다."""
    def __init__(self, rpm):
        self.gap = 60.0 / rpm
        self.next = 0.0
        self.lock = threading.Lock()

    def wait(self):
        with self.lock:
            now = time.monotonic()
            t = max(now, self.next)
            self.next = t + self.gap
        if t > now:
            time.sleep(t - now)


PACE = Pace(100)


class PacedMCP(BulsajaMCP):
    def call_tool(self, name, arguments):
        PACE.wait()
        return super().call_tool(name, arguments)


def mcp():
    """스레드마다 MCP 연결 하나."""
    if not getattr(_local, "m", None):
        _local.m = PacedMCP(sleep=5, max_retries=7)  # 429 대비 백오프
        _local.m.open()
    return _local.m


def two_step(tool, args, tries=3):
    """확인 키 2단계 호출. 삭제는 1단계도 confirm=true 여야 키를 준다.
    429 대기로 키가 만료되면 새 키를 받아 다시 한다."""
    first = dict(args)
    if tool == "bulsaja_market_delete":
        first["confirm"] = True
    for _ in range(tries):
        r = mcp().call_tool(tool, first)
        tok = r.get("confirmationToken")
        if not tok:
            raise RuntimeError(f"확인 키 없음: {str(r.get('message'))[:120]}")
        r2 = mcp().call_tool(tool, {**args, "confirm": True, "confirmationToken": tok})
        if r2.get("success") or "만료" not in str(r2.get("message")):
            return r, r2
        time.sleep(5)
    return r, r2


class Ledger:
    def __init__(self, path):
        self.path = path
        self.rows = []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.rows = [json.loads(x) for x in f if x.strip()]

    def add(self, row):
        row["ts"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with _lock:
            self.rows.append(row)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def copied_src(self):
        """복사를 시도한 원본(성공·실패 무관) — 재복사 방지용."""
        return {s for r in self.rows if r["step"] == "copy" for s in r["src"]}

    def safe_src(self):
        """복사가 확실한 원본만 — 휴지통 대상."""
        return {s for r in self.rows if r["step"] == "copy" and r.get("ok") for s in r["src"]}

    def new_ids(self):
        return [n for r in self.rows if r["step"] == "copy" for n in r.get("new") or []]

    def pairs(self):
        """(복사본, 원본) — 복사 응답의 새 id 순서가 원본 순서와 같음을 상품명으로 확인함."""
        return [(n, s) for r in self.rows if r["step"] == "copy" and r.get("ok")
                for s, n in zip(r["src"], r.get("new") or [])]

    def base(self, new):
        for r in reversed(self.rows):
            if r["step"] == "pbase" and r["new"] == new:
                return r["base"]
        return None

    def priced(self):
        return {r["new"] for r in self.rows if r["step"] == "price" and r.get("ok")}

    def trashed(self):
        return {s for r in self.rows if r["step"] == "trash" and r.get("ok") for s in r["src"]}


def do_copy(led, srcs, dst):
    todo = [s for s in srcs if s not in led.copied_src()]
    print(f"[copy] 대상 {len(todo)}건 (이미 처리 {len(srcs) - len(todo)})")
    for i in range(0, len(todo), COPY_CHUNK):
        chunk = todo[i:i + COPY_CHUNK]
        try:
            _, r = two_step("bulsaja_market_group_copy", {"productIds": chunk, "marketGroupId": dst})
            new = r.get("새상품Ids") or []
            ok = bool(r.get("success")) and int(r.get("실패") or 0) == 0 and len(new) == len(chunk)
            led.add({"step": "copy", "src": chunk, "new": new, "ok": ok,
                     "msg": str(r.get("message"))[:120]})
            print(f"[copy] {i + len(chunk)}/{len(todo)} 복사 {len(new)} 실패 {r.get('실패')}" + ("" if ok else " ⚠ 원본 휴지통 보류"))
        except Exception as e:
            # 복사 성공 여부를 모르면 재시도하지 않는다 — 중복 복사 방지. 대장에 실패로 남김
            led.add({"step": "copy", "src": chunk, "new": [], "ok": False, "msg": f"예외: {e}"[:200]})
            print(f"[copy] 청크 {i // COPY_CHUNK + 1} 예외: {e}")


def price_one(args):
    """원가 +1 저장 → 기준 원가로 저장 (호출 5회: 읽기 1 + 미리보기·확정 ×2).
    기준 원가: 대장에 남긴 값 > (전에 실패했으면) 원본 상품 > 복사본 현재 값.
    쓰기 전에 기준 원가를 대장에 남겨, 중간에 끊겨 +1 로 남아도 다음 실행이 원래 값으로 되돌린다."""
    pid, src, led, suspect = args
    try:
        d = (mcp().call_tool("bulsaja_product_workdata", {"productId": pid}) or {}).get("data") or {}
        skus = d.get("uploadSkus") or []
        if not skus:
            return pid, False, "옵션 없음"
        base = led.base(pid)
        if base is None and suspect:
            sd = (mcp().call_tool("bulsaja_product_workdata", {"productId": src}) or {}).get("data") or {}
            base = {s["id"]: s["origin_price"] for s in sd.get("uploadSkus") or []}
        if base is None:
            base = {s["id"]: s["origin_price"] for s in skus}
        if set(base) != {s["id"] for s in skus}:
            return pid, False, "옵션 구성 다름"
        led.add({"step": "pbase", "new": pid, "base": base})
        before = skus[0].get("sale_price")
        ids = list(base)
        last = None
        for delta in (1, 0):
            for i in range(0, len(ids), SKU_CHUNK):
                sp = [{"skuId": k, "costPrice": int(base[k]) + delta} for k in ids[i:i + SKU_CHUNK]]
                pre, r = two_step("bulsaja_option_update", {"productId": pid, "skuPrices": sp, "recalculateSalePrice": True})
                if not r.get("success"):
                    return pid, False, f"저장 실패({delta:+d}): {str(r.get('message'))[:100]}"
                last = pre
        after = ((last or {}).get("변경미리보기") or [{}])[0].get("판매가")
        return pid, True, f"{before}→{after} ({len(skus)}옵션)"
    except Exception as e:
        return pid, False, f"예외: {e}"[:200]


def do_price(led, workers, limit):
    failed = {r["new"] for r in led.rows if r["step"] == "price" and not r.get("ok")}
    started = {r["new"] for r in led.rows if r["step"] == "pbase"}
    suspect_n = getattr(do_price, "suspect_n", 0)
    pend = [(n, src) for n, src in led.pairs() if n not in led.priced()]
    # 원본에서 원가를 다시 읽을 대상: 전에 실패했거나, 구버전이 처리하다 끊겼을 수 있는 앞쪽 N건
    todo = [(n, src, led, n in failed or (n not in started and i < suspect_n)) for i, (n, src) in enumerate(pend)]
    if limit:
        todo = todo[:limit]
    print(f"[price] 대상 {len(todo)}건")
    done = fail = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        for pid, ok, msg in ex.map(price_one, todo):
            led.add({"step": "price", "new": pid, "ok": ok, "msg": msg})
            done += 1
            fail += 0 if ok else 1
            if not ok or done % 25 == 0:
                print(f"[price] {done}/{len(todo)} 실패 {fail}" + ("" if ok else f" — {pid} {msg}"))
    print(f"[price] 끝: {done}건 중 실패 {fail}")


def do_trash(led):
    # 재계산이 원본 원가를 읽으므로, 재계산까지 끝난 건의 원본만 보낸다
    priced = led.priced()
    todo = sorted({src for n, src in led.pairs() if n in priced} - led.trashed())
    print(f"[trash] 대상 {len(todo)}건 (복사·재계산 끝난 원본만)")
    for i in range(0, len(todo), TRASH_CHUNK):
        chunk = todo[i:i + TRASH_CHUNK]
        try:
            _, r = two_step("bulsaja_market_delete", {"productIds": chunk, "deleteAction": "SOURCE_ONLY", "scope": "ALL"})
            led.add({"step": "trash", "src": chunk, "ok": bool(r.get("success")), "msg": str(r.get("message"))[:120]})
            print(f"[trash] {i + len(chunk)}/{len(todo)} {r.get('message')}")
        except Exception as e:
            print(f"[trash] 예외: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--dst-group", type=int, default=1008216)
    ap.add_argument("--steps", default="copy,price,trash")
    ap.add_argument("--limit", type=int, default=0, help="copy 원본 수 / price 건수 제한 (시험용)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--rpm", type=int, default=100, help="분당 MCP 호출 상한(계정 한도 240을 조회와 나눠 씀)")
    ap.add_argument("--suspect-first", type=int, default=0, help="앞쪽 N건은 원본에서 원가를 읽음(끊긴 실행 복구용)")
    ap.add_argument("--seed", action="append", default=[], help="SRC=NEW (이미 손으로 복사·재계산한 건)")
    a = ap.parse_args()
    global PACE
    PACE = Pace(a.rpm)
    do_price.suspect_n = a.suspect_first
    rd = resolve_run_dir(a.run_dir)
    led = Ledger(os.path.join(rd, "transfer.jsonl"))

    for s in a.seed:
        src, new = s.split("=")
        if src not in led.copied_src():
            led.add({"step": "copy", "src": [src], "new": [new], "ok": True, "msg": "수동 등록"})
            led.add({"step": "price", "new": new, "ok": True, "msg": "수동 등록"})

    try:
        verdicts = json.load(open(os.path.join(rd, "verdicts.json"), encoding="utf-8"))
    except Exception as e:
        sys.exit(f"verdicts.json 읽기 실패: {e}")
    srcs = sorted(k for k, v in verdicts.items() if v.get("verdict") == "pass")
    if a.limit:
        srcs = srcs[:a.limit]
    print(f"[transfer] 통과 {len(srcs)}건 → 그룹 {a.dst_group}")

    steps = a.steps.split(",")
    if "copy" in steps:
        do_copy(led, srcs, a.dst_group)
    if "price" in steps:
        do_price(led, a.workers, a.limit)
    if "trash" in steps:
        do_trash(led)
    print(f"[transfer] 대장 요약: 복사확인 {len(led.safe_src())} / 재계산 {len(led.priced())} / 휴지통 {len(led.trashed())}")


if __name__ == "__main__":
    main()
