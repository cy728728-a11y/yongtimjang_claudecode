#!/usr/bin/env python3
"""회차 결과를 장부에 기록 — 2차 merge 뒤 한 번(1차 run 은 --stage 1, 2차 run 은 --stage 2).

  ledger_commit.py --run-dir R --kind full|3day [--stage 1|2] [--date YYYY-MM-DD]

- 본 상품 장부: 스냅샷의 네이버 번호 상품 전부(판정은 verdicts.json, 없으면 unjudged)
- 타오바오 장부: --stage 2 일 때만(2차 run 스냅샷에 매칭 번호가 있다)
- 마켓 장부: mallUrl 별 상품 수 누적, kind=full 이면 full_run, 3day 면 last_3day 갱신
순서: **2차 run 먼저**(--stage 2: 최종 판정·타오바오 기록) → 1차 run(--stage 1: 마켓 갱신·2차까지 못 간 상품).
  먼저 기록된 판정이 남으므로 2차를 먼저 넣어야 장부 판정이 최종값이 된다(검토 I3).
멱등: run 당 한 번(ledger_committed.json 표식). 마켓 상품 수는 누적이라 두 번 더하면 안 된다.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402
from run_inspect import resolve_run_dir, _load, _p  # noqa: E402


def market_rows(items, kind, campaign, date, existing):
    """existing(slug→row) 위에 이번 회차를 더한 전체 마켓 표를 돌려준다(원본은 건드리지 않음)."""
    out = {k: dict(v) for k, v in existing.items()}
    counts = {}
    urls = {}
    for it in items:
        slug = ledger.mall_slug(it.get("mallUrl"))
        if not slug:
            continue
        counts[slug] = counts.get(slug, 0) + 1
        urls.setdefault(slug, str(it.get("mallUrl")).strip().rstrip("/"))
    for slug, n in counts.items():
        row = out.get(slug)
        if row is None:
            row = {"slug": slug, "url": urls[slug], "first_seen": date, "full_run": None,
                   "last_3day": None, "products": 0, "empty": True}
            out[slug] = row
        row["products"] = int(row.get("products") or 0) + n
        row["empty"] = row["products"] == 0
        if kind == "full":
            row["full_run"] = {"campaign": campaign, "date": date}
        else:
            row["last_3day"] = date
    return out


def updates_markets(stage):
    """마켓 상품 수는 1차 run 에서만 더한다. 2차 run 은 같은 캠페인을 다시 받은 것이라 더하면 두 배가 된다(검토 I1)."""
    return stage == 1


def product_rows(items, verdicts, campaign, date):
    rows, seen = [], set()
    for it in items:
        pid = it.get("productId")
        if not ledger.is_naver_pid(pid):
            continue
        pid = str(pid).strip()
        if pid in seen:
            continue
        seen.add(pid)
        v = (verdicts.get(it.get("id")) or {}).get("verdict") or "unjudged"
        rows.append({"pid": pid, "campaign": campaign, "date": date, "verdict": v})
    return rows


def taobao_ids(items):
    return {t for t in (ledger.taobao_item_id(it) for it in items) if t}


def main():
    ap = argparse.ArgumentParser(description="회차 결과 장부 기록")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--kind", choices=["full", "3day"], required=True)
    ap.add_argument("--stage", type=int, choices=[1, 2], default=1)
    ap.add_argument("--date", default=time.strftime("%Y-%m-%d"))
    a = ap.parse_args()
    run = resolve_run_dir(a.run_dir)
    items = _load(_p(run, "snapshot.json"))
    if items is None:
        sys.exit("snapshot.json 없음")
    verdicts = _load(_p(run, "verdicts.json"), {}) or {}
    meta = _load(_p(run, "run_meta.json"), {}) or {}
    campaign = meta.get("campaign") or (items[0].get("campaignId") if items else "") or ""
    marker = _p(run, "ledger_committed.json")
    if os.path.exists(marker):
        sys.exit(f"이미 기록한 run 이다({marker}) — 마켓 상품 수가 두 번 더해지므로 다시 돌리지 않는다")

    n_p = ledger.append_seen_products(product_rows(items, verdicts, campaign, a.date))
    n_t = ledger.append_seen_taobao(taobao_ids(items)) if a.stage == 2 else 0
    new_m = 0
    if updates_markets(a.stage):
        existing = ledger.load_markets()
        merged = market_rows(items, a.kind, campaign, a.date, existing)
        new_m = len(merged) - len(existing)
        ledger.upsert_markets(merged)
    try:
        import json
        with open(marker, "w", encoding="utf-8") as f:
            json.dump({"at": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": a.kind, "stage": a.stage,
                       "naver_added": n_p, "taobao_added": n_t, "markets_new": new_m}, f, ensure_ascii=False)
    except OSError as e:
        print(f"[ledger] 기록 표식 저장 실패: {e}", file=sys.stderr)
    touched = len({ledger.mall_slug(it.get("mallUrl")) for it in items} - {None}) if updates_markets(a.stage) else 0
    print(f"[ledger] 네이버 +{n_p} 타오바오 +{n_t} 마켓 갱신 {touched}(새 마켓 {new_m})")


if __name__ == "__main__":
    main()
