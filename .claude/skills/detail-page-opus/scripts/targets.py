# -*- coding: utf-8 -*-
"""고퀄 상세 배치 대상 뽑기 — 광고 주간보고 ⑦c·⑦d 중 상세 미가공 상품.

순서: 판매된 상품(잠금) → 구매수 → 클릭수. 실시간으로 불사자를 다시 조회해
이미 가공된 상품(AI 생성 표시 · mcp-assets 직접 업로드 흔적 · 로컬 _opus 결과)은 뺀다.

사용법:
  python targets.py [--run-dir 2026-10-26] [--limit 5]
  → ~/python_work/data/detail-opus/batches/<오늘>/targets.json
"""
import argparse
import json
import sys
from datetime import date

import common


def latest_run():
    runs = sorted(p for p in common.ADS_RUNS.iterdir()
                  if p.is_dir() and p.name[:4].isdigit() and (p / "result.json").exists())
    if not runs:
        raise RuntimeError(f"광고 회차가 없다: {common.ADS_RUNS}")
    return runs[-1]


def collect_rows(run_dir):
    """⑦c·⑦d 에서 상세 미가공 + 불사자 히트 행을 판매자상품코드 단위로 합친다."""
    res = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    by = {}
    for acct, a in res.get("accounts", {}).items():
        for rule, rows in (a.get("rules") or {}).items():
            if "⑦c" not in rule and "⑦d" not in rule:
                continue
            for r in rows:
                code = r.get("판매자상품코드")
                if r.get("불사자매칭") != "히트" or not code or not r.get("상세미가공"):
                    continue
                cur = by.setdefault(code, {
                    "code": code, "productId": r.get("productId"), "title": r.get("title"),
                    "market": r.get("마켓번호"), "clk": 0, "purCnt": 0, "rules": []})
                cur["clk"] = max(cur["clk"], r.get("clk") or 0)
                cur["purCnt"] = max(cur["purCnt"], r.get("purCnt") or 0)
                tag = "⑦c" if "⑦c" in rule else "⑦d"
                if tag not in cur["rules"]:
                    cur["rules"].append(tag)
    return list(by.values())


def local_done(pid):
    """로컬에 이미 _opus 결과(report.md)가 있으면 그 폴더."""
    for p in common.PAGES.glob(f"*/{pid}/*_opus/report.md"):
        return str(p.parent)
    return None


def main():
    ap = argparse.ArgumentParser(description="고퀄 상세 배치 대상 뽑기")
    ap.add_argument("--run-dir", help="광고 회차 이름(기본: 최신)")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--out", help="배치 폴더(기본: batches/<오늘>)")
    args = ap.parse_args()

    run_dir = common.ADS_RUNS / args.run_dir if args.run_dir else latest_run()
    rows = collect_rows(run_dir)
    print(f"[후보] {run_dir.name} ⑦c/⑦d 상세 미가공 {len(rows)}건")

    m = common.mcp()
    picked, skipped = [], []
    try:
        # 1) 잠금·그룹을 코드 50개씩 한 번에
        for i in range(0, len(rows), 20):
            chunk = rows[i:i + 20]
            r = common.call(m, "bulsaja_product_find_by_code", {"codes": [x["code"] for x in chunk]})
            items = {it.get("판매자상품코드"): it for it in (r.get("항목") or [])}
            for x in chunk:
                it = items.get(x["code"])
                x["locked"] = bool(it and it.get("잠금"))
                x["found"] = bool(it)
                if it:
                    x["productId"] = it.get("productId") or x["productId"]
                    x["name"] = it.get("상품명")
        rows.sort(key=lambda x: (not x["locked"], -x["purCnt"], -x["clk"]))

        # 2) 순서대로 상세를 실시간 재확인 — limit 채우면 멈춘다
        for x in rows:
            if len(picked) >= args.limit:
                break
            if not x["found"]:
                skipped.append({**x, "skip": "불사자에서 코드 못 찾음"}); continue
            done = local_done(x["productId"])
            if done:
                skipped.append({**x, "skip": f"로컬 결과 있음 {done}"}); continue
            try:
                wd = common.call(m, "bulsaja_product_workdata",
                                 {"productId": x["productId"], "mode": "full"}).get("data") or {}
            except Exception as e:
                skipped.append({**x, "skip": f"workdata 조회 실패 {e}"}); continue
            dc = wd.get("uploadDetailContents") or {}
            rc = dc.get("renderContent") or ""
            if "/mcp-assets/" in rc or str(dc.get("aiImageGenerated")).lower() in ("true", "1"):
                skipped.append({**x, "skip": "이미 가공됨(불사자 기록)"}); continue
            if "<img" not in rc:
                skipped.append({**x, "skip": "상세 이미지 없음"}); continue
            gid = wd.get("uploadSelectedMarketGroupId")
            gname = None
            if gid:
                gname = common.call(m, "bulsaja_market_groups", {"groupId": int(gid)}).get("그룹명")
            mk = common.market_no(gname) or x["market"]
            if not mk or not gid:
                skipped.append({**x, "skip": f"마켓그룹 불명 ({gname})"}); continue
            if x["market"] and mk != x["market"]:
                skipped.append({**x, "skip": f"마켓번호 불일치 광고 {x['market']} ≠ 불사자 {mk}"}); continue
            skus = wd.get("uploadSkus") or []
            picked.append({**x, "market": mk, "marketGroupId": int(gid), "marketGroupName": gname,
                           "name": wd.get("uploadSmartStoreProductName") or x.get("name"),
                           "imgCount": rc.count("<img"),
                           "sellOptions": [s.get("text") for s in skus if not s.get("exclude")],
                           "excludedOptions": [s.get("text") for s in skus if s.get("exclude")]})
            print(f"  + {x['code']} {mk} 잠금={x['locked']} 구매={x['purCnt']} 클릭={x['clk']} {picked[-1]['name']}")
    finally:
        m.close()

    out = common.BATCH_ROOT / (args.out or date.today().isoformat())
    out.mkdir(parents=True, exist_ok=True)
    common.write_json(out / "targets.json", {"adsRun": run_dir.name, "limit": args.limit,
                                             "targets": picked, "skipped": skipped})
    print(f"[대상] {len(picked)}건 · 건너뜀 {len(skipped)}건 → {out / 'targets.json'}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    try:
        main()
    except Exception as e:
        print(f"[오류] {e}")
        sys.exit(1)
