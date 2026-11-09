#!/usr/bin/env python3
"""회차 보고서 — 마켓 수·수집·중복 제거·1차/2차 통과·마켓당 수율·월 공급 예측을 한 장으로.

  pipeline_report.py --run1 R1 --run2 R2 [--pilot-meta 파일] [--out <R2>/report.md] [--copy-to 폴더]

R1 = 1차 run(수집 직후 스냅샷·네이버 중복·1차 판정), R2 = 2차 run(타오바오 중복·2차 판정·수집 접수).
월 공급 예측 B = 마켓당 2차 통과 × 재수확 마켓 수(16,227) × 월 회차(4). 목표는 2차 통과 140,000/월.
설계: docs/superpowers/specs/2026-11-08-sourcing-pipeline-design.md 6절 5·7절.
"""
import argparse
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402
from run_inspect import resolve_run_dir, _load, _p  # noqa: E402
from apply_sourcing import load_jsonl  # noqa: E402

TARGET = 140_000           # 월 2차 통과 목표(설계서 1절)
REHARVEST_MARKETS = 16_227  # 28765 캠페인에서 상품을 낸 마켓 수(설계서 1절)
ROUNDS_PER_MONTH = 4       # 주 1회 재수확


def _is_pass(v):
    return (v or {}).get("verdict") == "pass"


def summarize(items, v1, dup1, v2, dup2, collect, meta=None):
    """숫자만 계산한다(파일 I/O 없음). collect = apply_collect.jsonl 을 id→행 으로 읽은 것."""
    slug_of = {it["id"]: ledger.mall_slug(it.get("mallUrl")) for it in items}
    slugs = {s for s in slug_of.values() if s}
    pass1_ids = {i for i, v in v1.items() if _is_pass(v)}
    pass2_ids = {i for i, v in v2.items() if _is_pass(v)}
    n_items = len(items)
    n_markets = len(slugs) or 1
    s = {
        "markets_total": len(slugs), "markets_with_items": len(slugs),
        "collected": n_items,
        "dup_naver": sum(1 for v in dup1.values() if (v or {}).get("reason") == "DUP_SEEN"),
        "dup_taobao": sum(1 for v in dup2.values() if (v or {}).get("reason") == "DUP_TAOBAO"),
        "pass1": len(pass1_ids), "pass2": len(pass2_ids),
        "pass_rate": (len(pass2_ids) / n_items) if n_items else 0.0,
        "per_market_collected": n_items / n_markets,
        "per_market_pass2": len(pass2_ids) / n_markets,
        "collected_ok": sum(1 for r in collect.values() if r.get("ok")),
        "collect_dup": sum(1 for r in collect.values() if r.get("dup") and not r.get("ok")),
        "buckets": {},
    }
    if meta:
        # 파일럿 묶음(top/random)별 — 마켓은 meta 기준, 상품은 그 마켓에 속한 것
        for bucket in sorted(set(meta.values())):
            b_slugs = {sl for sl, bk in meta.items() if bk == bucket}
            b_items = [it for it in items if slug_of[it["id"]] in b_slugs]
            b_pass2 = sum(1 for it in b_items if it["id"] in pass2_ids)
            b_with = len({slug_of[it["id"]] for it in b_items})
            s["buckets"][bucket] = {
                "markets": len(b_slugs), "markets_with_items": b_with, "collected": len(b_items),
                "pass2": b_pass2,
                "per_market_collected": len(b_items) / len(b_slugs) if b_slugs else 0.0,
                "per_market_pass2": b_pass2 / len(b_slugs) if b_slugs else 0.0,
            }
        # 파일럿이면 마켓당 수율은 "투입한 마켓 수" 기준으로 다시 계산(상품 못 낸 마켓도 분모)
        n_in = len(meta)
        s["markets_total"] = n_in
        s["per_market_collected"] = n_items / n_in if n_in else 0.0
        s["per_market_pass2"] = len(pass2_ids) / n_in if n_in else 0.0
    s["monthly_B"] = round(s["per_market_pass2"] * REHARVEST_MARKETS * ROUNDS_PER_MONTH)
    s["gap_to_target"] = s["monthly_B"] - TARGET
    return s


def _pct(x):
    return f"{x * 100:.1f}%"


def render(s):
    gap = s["gap_to_target"]
    lines = [
        f"**월 공급 예측 B = {s['monthly_B']:,}건 / 목표 {TARGET:,} / 차이 {gap:+,}** "
        f"(마켓당 2차 통과 {s['per_market_pass2']:.3f} × 마켓 {REHARVEST_MARKETS:,} × 월 {ROUNDS_PER_MONTH}회)",
        "",
        f"작성 {time.strftime('%Y-%m-%d %H:%M')}",
        "",
        "| 항목 | 값 |", "|---|---|",
        f"| 투입 마켓 | {s['markets_total']:,} |",
        f"| 상품 낸 마켓 | {s['markets_with_items']:,} |",
        f"| 수집 | {s['collected']:,} |",
        f"| 중복 제거(네이버 번호) | {s['dup_naver']:,} |",
        f"| 중복 제거(타오바오 번호) | {s['dup_taobao']:,} |",
        f"| 1차 통과 | {s['pass1']:,} |",
        f"| 2차 통과 | {s['pass2']:,} ({_pct(s['pass_rate'])} of 수집) |",
        f"| 상품수집 접수 / 그룹 중복으로 빠짐 | {s['collected_ok']:,} / {s['collect_dup']:,} |",
        f"| 마켓당 수집 | {s['per_market_collected']:.2f} |",
        f"| 마켓당 2차 통과 | {s['per_market_pass2']:.3f} |",
    ]
    if s["buckets"]:
        lines += ["", "### 묶음별(파일럿)", "", "| 묶음 | 마켓 | 상품 낸 마켓 | 수집 | 2차 통과 | 마켓당 수집 | 마켓당 2차 통과 |",
                  "|---|---|---|---|---|---|---|"]
        for k, b in s["buckets"].items():
            lines.append(f"| {k} | {b['markets']:,} | {b['markets_with_items']:,} | {b['collected']:,} | {b['pass2']:,} "
                         f"| {b['per_market_collected']:.2f} | {b['per_market_pass2']:.3f} |")
        tb, rb = s["buckets"].get("top"), s["buckets"].get("random")
        if tb and rb and rb["per_market_pass2"] > 0:
            ratio = tb["per_market_pass2"] / rb["per_market_pass2"]
            lines += ["", f"상위 마켓이 무작위보다 마켓당 {ratio:.1f}배 낸다. "
                      + ("재수확 대상을 상위 마켓으로 좁힐 여지가 있다." if ratio >= 2 else "좁혀도 큰 이득은 없다.")]
    lines += ["", "다음 달 공급을 14만에 맞추려면: " + (
        "재수확만으로 충분하다." if gap >= 0 else
        f"재수확 외에 {-gap:,}건이 더 필요하다 — 새 마켓 전체 이력(A)·3만~5만 원 전체 이력(D)·회차 수 증가로 채운다.")]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description="회차 보고서")
    ap.add_argument("--run1", required=True)
    ap.add_argument("--run2", required=True)
    ap.add_argument("--pilot-meta")
    ap.add_argument("--out")
    ap.add_argument("--copy-to")
    a = ap.parse_args()
    r1, r2 = resolve_run_dir(a.run1), resolve_run_dir(a.run2)
    items = _load(_p(r1, "snapshot.json"))
    if items is None:
        sys.exit(f"{r1}/snapshot.json 없음")
    v1 = _load(_p(r1, "verdicts.json"), {}) or {}
    d1 = _load(_p(r1, "dup_verdicts.json"), {}) or {}
    v2 = _load(_p(r2, "verdicts.json"), {}) or {}
    d2 = _load(_p(r2, "dup_verdicts.json"), {}) or {}
    collect = load_jsonl(_p(r2, "apply_collect.jsonl"))
    meta = _load(a.pilot_meta, None) if a.pilot_meta else None
    s = summarize(items, v1, d1, v2, d2, collect, meta)
    md = f"# 회차 보고 — {os.path.basename(r1)} / {os.path.basename(r2)}\n\n" + render(s)
    out = a.out or _p(r2, "report.md")
    try:
        with open(out, "w", encoding="utf-8") as f:
            f.write(md)
        if a.copy_to:
            os.makedirs(a.copy_to, exist_ok=True)
            shutil.copy(out, os.path.join(a.copy_to, f"{time.strftime('%Y-%m-%d')}_회차보고_{os.path.basename(r2)}.md"))
    except OSError as e:
        sys.exit(f"저장 실패: {e}")
    print(md.splitlines()[2])
    print(f"[report] → {out}" + (f" (사본 {a.copy_to})" if a.copy_to else ""))


if __name__ == "__main__":
    main()
