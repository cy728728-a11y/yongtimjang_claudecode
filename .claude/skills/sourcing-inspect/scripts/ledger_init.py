#!/usr/bin/env python3
"""장부 초기값 생성 — 지난 검수 run 의 스냅샷 전부와 마켓 목록 파일에서 세 장부를 만든다.

  ledger_init.py [--runs-dir ~/python_work/data/sourcing-inspect/runs]
                 [--seen-markets ~/python_work/data/sourcing-pipeline/seen_markets.txt]
                 [--market-list <28765 캠페인 입력 마켓 목록 파일>]

- 네이버 번호(숫자) 상품 → seen_products.jsonl, 그 외(U01M…) → internal_ids.txt
- 타오바오 번호가 있는 상품 → seen_taobao.txt
- mallUrl 별 상품 수 → markets.jsonl. 지금까지의 캠페인은 모두 '과거 판매 이력 전부' 모드였으므로
  스냅샷에 보이는 campaignId 는 전부 full_run 으로 기록한다.
- 멱등: 두 번 돌려도 수가 변하지 않는다(append 가 중복 제외, 마켓은 큰 값 유지).
"""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger  # noqa: E402

RUNS_DIR = os.path.expanduser("~/python_work/data/sourcing-inspect/runs")
SEEN_MARKETS = os.path.join(ledger.DATA_DIR, "seen_markets.txt")
CAMPAIGN_28765 = "kwy9jllI5NICgPo"


def new_state():
    return {"products": [], "product_ids": set(), "internal": set(), "taobao": set(), "markets": {}}


def _date_of(item):
    ts = str(item.get("timestamp") or "")
    return ts[:10] if len(ts) >= 10 else ""


def ingest_snapshot(items, verdicts, st):
    """스냅샷 한 개를 상태에 흘려 넣는다. verdicts = 그 run 의 verdicts.json(없으면 {})."""
    for it in items:
        if not isinstance(it, dict):
            continue
        pid = it.get("productId")
        camp = it.get("campaignId") or ""
        date = _date_of(it)
        if ledger.is_naver_pid(pid):
            pid = str(pid).strip()
            if pid not in st["product_ids"]:
                v = (verdicts.get(it.get("id")) or {}).get("verdict") or "unjudged"
                st["products"].append({"pid": pid, "campaign": camp, "date": date, "verdict": v})
                st["product_ids"].add(pid)
        elif pid not in (None, "") and str(pid).strip():
            st["internal"].add(str(pid).strip())   # 불사자 내부 번호(U01M…) — 번호 없는 상품은 기록 안 함
        tb = ledger.taobao_item_id(it)
        if tb:
            st["taobao"].add(tb)
        slug = ledger.mall_slug(it.get("mallUrl"))
        if slug:
            row = st["markets"].get(slug)
            if row is None:
                row = {"slug": slug, "url": str(it.get("mallUrl")).strip().rstrip("/"), "first_seen": date,
                       "full_run": {"campaign": camp, "date": date} if camp else None,
                       "last_3day": None, "products": 0, "empty": True}
                st["markets"][slug] = row
            row["products"] += 1
            row["empty"] = False
            if row["first_seen"] and date and date < row["first_seen"]:
                row["first_seen"] = date


def add_market_urls(urls, st, campaign):
    """마켓 목록 파일의 주소들 — 장부에 없는 것만 '상품 0개(빈 밭), 전체 이력은 돌렸음' 으로 추가."""
    for u in urls:
        slug = ledger.mall_slug(u)
        if not slug or slug in st["markets"]:
            continue
        st["markets"][slug] = {"slug": slug, "url": str(u).strip().rstrip("/"), "first_seen": "",
                               "full_run": {"campaign": campaign, "date": ""}, "last_3day": None,
                               "products": 0, "empty": True}


def merge_markets(existing, fresh):
    """기존 장부(운영 중 갱신된 값) 위에 새로 계산한 것을 합친다. 상품 수는 큰 쪽, 3일 기록은 기존 유지."""
    out = {k: dict(v) for k, v in existing.items()}
    for slug, row in fresh.items():
        if slug not in out:
            out[slug] = dict(row)
            continue
        cur = out[slug]
        cur["products"] = max(int(cur.get("products") or 0), int(row.get("products") or 0))
        cur["empty"] = cur["products"] == 0
        if not cur.get("full_run") and row.get("full_run"):
            cur["full_run"] = row["full_run"]
        if not cur.get("first_seen") and row.get("first_seen"):
            cur["first_seen"] = row["first_seen"]
    return out


def _load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except (OSError, ValueError) as e:
        print(f"[ledger_init] 읽기 실패(건너뜀) {path}: {e}", file=sys.stderr)
        return default


def _read_urls(path):
    try:
        with open(path, encoding="utf-8") as f:
            return [ln.strip() for ln in f if ln.strip()]
    except FileNotFoundError:
        return []
    except OSError as e:
        print(f"[ledger_init] 마켓 목록 읽기 실패 {path}: {e}", file=sys.stderr)
        return []


def main():
    ap = argparse.ArgumentParser(description="소싱 파이프라인 장부 초기값 생성")
    ap.add_argument("--runs-dir", default=RUNS_DIR)
    ap.add_argument("--seen-markets", default=SEEN_MARKETS)
    ap.add_argument("--market-list", help="28765 캠페인 입력 마켓 목록(한 줄 한 주소)")
    a = ap.parse_args()

    st = new_state()
    snaps = sorted(glob.glob(os.path.join(a.runs_dir, "*", "snapshot.json")))
    for sp in snaps:
        run = os.path.dirname(sp)
        items = _load_json(sp, None)
        if items is None:
            continue
        if isinstance(items, dict):
            items = items.get("data") or []
        verdicts = _load_json(os.path.join(run, "verdicts.json"), {}) or {}
        before = len(st["products"])
        ingest_snapshot(items, verdicts, st)
        print(f"[ledger_init] {os.path.basename(run)}: {len(items)}건 → 네이버 +{len(st['products']) - before}", flush=True)
    with_items = sum(1 for r in st["markets"].values() if r["products"] > 0)
    add_market_urls(_read_urls(a.seen_markets), st, CAMPAIGN_28765)
    if a.market_list:
        add_market_urls(_read_urls(a.market_list), st, CAMPAIGN_28765)

    n_p = ledger.append_seen_products(st["products"])
    n_t = ledger.append_seen_taobao(st["taobao"])
    n_i = ledger.append_seen_taobao(st["internal"], path=ledger.INTERNAL_IDS)  # 같은 "한 줄 한 번호" 형식
    merged = merge_markets(ledger.load_markets(), st["markets"])
    ledger.upsert_markets(merged)
    print(f"[ledger_init] 네이버 {len(ledger.load_seen_products()):,}(추가 {n_p:,}) / 내부번호 {len(ledger.load_seen_taobao(ledger.INTERNAL_IDS)):,}(추가 {n_i:,})"
          f" / 타오바오 {len(ledger.load_seen_taobao()):,}(추가 {n_t:,}) / 마켓 {len(merged):,}(상품 있음 {with_items:,})")


if __name__ == "__main__":
    main()
