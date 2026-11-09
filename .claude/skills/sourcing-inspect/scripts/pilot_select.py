#!/usr/bin/env python3
"""재수확 파일럿 마켓 선정 — 28765 캠페인에서 상품을 낸 마켓 중 상위 1,000 + 무작위 1,000.

  pilot_select.py [--out-dir 10-projects/16-불사자-소싱-파이프라인] [--top 1000] [--random 1000] [--seed 20261110]

출력:
  pilot_markets_YYMMDD.txt  한 줄 한 마켓 주소(소싱기 캠페인 마켓 칸에 붙여넣기용)
  pilot_meta_YYMMDD.json    {slug: "top"|"random"} — 보고서가 묶음별 수율을 나눠 셀 때 쓴다
설계: docs/superpowers/specs/2026-11-08-sourcing-pipeline-design.md 7절.
"""
import argparse
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402

CAMPAIGN_28765 = "kwy9jllI5NICgPo"
# scripts → sourcing-inspect → skills → .claude → 워크스페이스 루트
_WS = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
DEFAULT_OUT = os.path.join(_WS, "10-projects", "16-불사자-소싱-파이프라인")


def pick(markets, top_n=1000, rand_n=1000, seed=20261110, campaign=CAMPAIGN_28765):
    """slug → "top"/"random". 대상 = 상품>0 이고 full_run.campaign == campaign 인 마켓."""
    cands = [r for r in markets.values()
             if int(r.get("products") or 0) > 0 and ((r.get("full_run") or {}).get("campaign") == campaign)]
    cands.sort(key=lambda r: (-int(r["products"]), r["slug"]))   # 상품 수 내림차순, 동률은 이름순
    top = cands[:top_n]
    rest = cands[top_n:]
    rnd = random.Random(seed).sample(rest, min(rand_n, len(rest)))
    out = {r["slug"]: "top" for r in top}
    out.update({r["slug"]: "random" for r in rnd})
    return out


def main():
    ap = argparse.ArgumentParser(description="재수확 파일럿 마켓 선정")
    ap.add_argument("--out-dir", default=DEFAULT_OUT)
    ap.add_argument("--top", type=int, default=1000)
    ap.add_argument("--random", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=20261110)
    a = ap.parse_args()
    markets = ledger.load_markets()
    if not markets:
        sys.exit("마켓 장부가 비어 있다 — ledger_init.py 먼저")
    chosen = pick(markets, a.top, a.random, a.seed)
    tag = time.strftime("%y%m%d")
    try:
        os.makedirs(a.out_dir, exist_ok=True)
        txt = os.path.join(a.out_dir, f"pilot_markets_{tag}.txt")
        meta = os.path.join(a.out_dir, f"pilot_meta_{tag}.json")
        with open(txt, "w", encoding="utf-8") as f:
            for slug in chosen:
                f.write((markets[slug].get("url") or f"https://smartstore.naver.com/{slug}") + "\n")
        with open(meta, "w", encoding="utf-8") as f:
            json.dump(chosen, f, ensure_ascii=False, indent=0)
    except OSError as e:
        sys.exit(f"저장 실패: {e}")
    n_top = sum(1 for v in chosen.values() if v == "top")
    print(f"[pilot] top {n_top} / random {len(chosen) - n_top} → {txt}\n[pilot] 묶음 표 → {meta}")


if __name__ == "__main__":
    main()
