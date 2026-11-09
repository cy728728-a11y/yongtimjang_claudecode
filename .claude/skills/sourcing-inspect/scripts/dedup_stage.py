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


def committed(run_dir):
    """이미 장부에 기록한 run 인가 — 그런 run 을 다시 중복 판정하면 자기 상품을 전부 중복으로 오인한다."""
    return os.path.exists(os.path.join(run_dir, "ledger_committed.json"))


def late_ids(items_r2, items_r1):
    """2차 run 에는 있는데 1차 스냅샷에는 없던 상품 id — 완료 감지 뒤 늦게 들어와 1차·네이버 중복을 건너뛴 것."""
    seen = {it.get("id") for it in items_r1}
    return [it["id"] for it in items_r2 if it.get("id") not in seen]


def judge_naver(items, seen, campaign=None):
    """네이버 상품번호 기준. 장부에 있으면 DUP_SEEN(장부), 같은 회차에 두 번 나오면 두 번째부터 DUP_SEEN(같은 회차 중복).
    seen 이 pid→캠페인 지도이고 campaign 이 주어지면, 같은 캠페인으로 기록된 번호는 중복이 아니다
    (자기 회차를 장부에 넣은 뒤 다시 돌려도 자기 상품을 휴지통에 보내지 않게 — 2026-11-10 검토 C1).
    번호가 없거나 숫자가 아닌 상품은 건너뛴다(장부에도 안 넣는 상품)."""
    out, in_run = {}, set()
    own = isinstance(seen, dict) and campaign
    for it in items:
        pid = it.get("productId")
        if not ledger.is_naver_pid(pid):
            continue
        pid = str(pid).strip()
        if pid in seen and not (own and seen[pid] == campaign):
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
    ap.add_argument("--stage1-run", help="taobao 때 1차 run — 늦게 들어온 상품이 있으면 멈춘다")
    ap.add_argument("--allow-late", action="store_true", help="늦게 들어온 상품을 알고도 진행")
    a = ap.parse_args()
    run = resolve_run_dir(a.run_dir)
    if committed(run):
        sys.exit(f"이미 장부에 기록한 run 이다({run}) — 다시 중복 판정하면 자기 상품을 중복으로 오인한다")
    items = _load(_p(run, "snapshot.json"))
    if items is None:
        sys.exit("snapshot.json 없음 — fetch 먼저")
    meta = _load(_p(run, "run_meta.json"), {}) or {}
    campaign = meta.get("campaign") or (items[0].get("campaignId") if items else None)
    if a.kind == "taobao" and a.stage1_run:
        r1 = _load(_p(resolve_run_dir(a.stage1_run), "snapshot.json"), []) or []
        late = late_ids(items, r1)
        if late and not a.allow_late:
            sys.exit(f"[dedup] 1차 스냅샷 뒤에 늦게 들어온 상품 {len(late)}건(앞 5: {late[:5]}) — "
                     "수집이 덜 끝난 채 1차를 돌렸다. 늦은 상품만 1차를 다시 돌리거나 --allow-late")
    if a.kind == "naver":
        r = judge_naver(items, ledger.load_seen_products_map(), campaign=campaign)
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
