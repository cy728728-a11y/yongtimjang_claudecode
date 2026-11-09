#!/usr/bin/env python3
"""장부 기반 중복 제거 단계 — 검수 전에 이미 본 상품을 걸러 크레딧·시간을 아낀다.

  dedup_stage.py naver  --run-dir R   # 수집 직후: 네이버 상품번호가 본 상품 장부에 있으면 DUP_SEEN
  dedup_stage.py taobao --run-dir R   # 매칭 직후(2차 전): 타오바오 번호가 장부에 있으면 DUP_TAOBAO

결과는 <R>/dup_verdicts.json {문서id: {verdict:"drop", reason, note, by:"ledger"}} 에 합쳐 저장한다.
run_inspect.py prep 이 이 id 를 대상에서 빼고, merge 가 drop 으로 합치므로 휴지통 반영은
기존 apply_sourcing.py trash 가 그대로 한다(사유는 휴지통 대장에 남는다).
설계: docs/superpowers/specs/2026-11-08-sourcing-pipeline-design.md 5절.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402
from run_inspect import resolve_run_dir, _load, _save, _p  # noqa: E402


def _drop(reason, note):
    return {"verdict": "drop", "reason": reason, "note": note, "by": "ledger"}


def judge_naver(items, seen):
    """네이버 상품번호 기준. 장부에 있으면 DUP_SEEN(장부), 같은 회차에 두 번 나오면 두 번째부터 DUP_SEEN(같은 회차 중복).
    번호가 없거나 숫자가 아닌 상품은 건너뛴다(장부에도 안 넣는 상품)."""
    out, in_run = {}, set()
    for it in items:
        pid = it.get("productId")
        if not ledger.is_naver_pid(pid):
            continue
        pid = str(pid).strip()
        if pid in seen:
            out[it["id"]] = _drop("DUP_SEEN", "장부")
        elif pid in in_run:
            out[it["id"]] = _drop("DUP_SEEN", "같은 회차 중복")
        else:
            in_run.add(pid)
    return out


def judge_taobao(items, seen):
    """타오바오 상품번호 기준. 번호 없는 상품은 건너뛴다(그건 기계 NO_MATCH 몫)."""
    out = {}
    for it in items:
        tb = ledger.taobao_item_id(it)
        if tb and tb in seen:
            out[it["id"]] = _drop("DUP_TAOBAO", "장부")
    return out


def main():
    ap = argparse.ArgumentParser(description="장부 기반 중복 제거(판정 파일만 만든다, 불사자 쓰기 없음)")
    ap.add_argument("kind", choices=["naver", "taobao"])
    ap.add_argument("--run-dir", required=True)
    a = ap.parse_args()
    run = resolve_run_dir(a.run_dir)
    items = _load(_p(run, "snapshot.json"))
    if items is None:
        sys.exit("snapshot.json 없음 — fetch 먼저")
    if a.kind == "naver":
        r = judge_naver(items, ledger.load_seen_products())
    else:
        r = judge_taobao(items, ledger.load_seen_taobao())
    prev = _load(_p(run, "dup_verdicts.json"), {}) or {}
    prev.update(r)
    _save(_p(run, "dup_verdicts.json"), prev)
    n_ledger = sum(1 for v in r.values() if v["note"] == "장부")
    print(f"[dedup] {a.kind} 대상 {len(items)}건 중 중복 {len(r)}건(장부 {n_ledger}, 회차내 {len(r) - n_ledger})"
          f" → dup_verdicts.json 누적 {len(prev)}건")


if __name__ == "__main__":
    main()
