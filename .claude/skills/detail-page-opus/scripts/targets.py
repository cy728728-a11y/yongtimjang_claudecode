# -*- coding: utf-8 -*-
"""고퀄 상세 배치 대상 뽑기 — 이룸 맥미니의 광고 상세우선순위 → 모자라면 판매 잠금 상품.

광고 우선순위는 맥미니가 매주 월요일 06:10 무렵 드라이브에 올린다(2026-11-02 이룸님 세팅·용팀장 승인).
맥북은 월요일 07:00 이후 첫 실행 때 fetch_ad_priority.py 로 한 번만 받고 그 주 내내 로컬 사본을 쓴다.
맥북은 광고 API 를 부르지 않는다(입찰·삭제·조회 모두 맥미니 전담).

순서: 광고 우선순위(파일의 '순위' 그대로: A 효자확정 → B 클릭많음 → C 클릭률상위)
     → 효자상품-작업대장 시트 '전체 현황판'(인덱스 순)
     → 판매 잠금 후보(sold-lock, 최근 잠금일 순, 잠금 → 클릭).
상품명이 '비즈 ' 로 시작하는 쥬얼리·재봉 부자재는 검수 SMALL 로 전량 탈락해 뺀다. 실시간으로 불사자를 다시 조회해
이미 가공된 상품(AI 생성 표시 · mcp-assets 직접 업로드 흔적 · 로컬 _opus 결과)은 뺀다.
상품검수 스킬 기계 규칙(타오바오 제목 금지어·와트)에 걸리면 뺀다 — 나머지 기준은 Aside 가 제작 전에 본다.

사용법:
  python targets.py [--run-dir 2026-10-26] [--limit 5]
  → ~/python_work/data/detail-opus/batches/<오늘>/targets.json
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

import common


def latest_run():
    runs = sorted(p for p in common.ADS_RUNS.iterdir()
                  if p.is_dir() and p.name[:4].isdigit() and (p / "result.json").exists())
    if not runs:
        raise RuntimeError(f"광고 회차가 없다: {common.ADS_RUNS}")
    return runs[-1]


SOLD = Path.home() / "python_work/data/sold-lock"
# 효자상품-작업대장 '전체 현황판' — 광고 우선순위 다음, 판매 잠금 앞(2026-11-04 용팀장 지시). 시트 '상세페이지' 열은 비어 있어 안 쓴다.
SHEET_ID, SHEET_RANGE = "1yCdXEuMlLSxaWnl7jxjSS0UQwIECKGRchsGN3jxCCNc", "전체 현황판!A2:F"
SHEET_CACHE = common.BATCH_ROOT / "hyoja_sheet.json"
SHEET_FROM = date(2026, 11, 9)   # 11/09(월) 광고 우선순위 회차부터 — 그 전 실행엔 시트 후보를 안 넣는다


def collect_priority():
    """맥미니 광고 상세우선순위(주 1회 받음) → 후보 행. 판매자상품코드 없는 미매칭 행은 뺀다."""
    try:
        import fetch_ad_priority as fap
        doc = fap.ensure()
    except Exception as e:
        print(f"  [경고] 광고 우선순위 받기 실패 {e} — 판매 잠금 후보만 쓴다", flush=True)
        return [], None
    done = set(fap._load(fap.DONE, {}).keys())
    rows = []
    for r in doc.get("rows") or []:
        if not r.get("판매자상품코드") or (fap._keys(r) & done):
            continue
        rows.append({"code": r["판매자상품코드"], "productId": r.get("불사자상품ID"), "title": r.get("상품명"),
                     "market": r.get("마켓번호"), "clk": r.get("30일클릭") or 0, "purCnt": r.get("30일구매") or 0,
                     "rules": [f"{r.get('등급')} {r.get('사유')}"], "src": 0, "rank": r.get("순위") or 9999})
    return rows, (doc.get("meta") or {}).get("회차")


def collect_sheet(exclude):
    """효자상품 작업대장 — 시트 인덱스 순. 읽기 실패하면 마지막 사본을 쓴다."""
    if date.today() < SHEET_FROM:
        return []
    import subprocess
    vals = None
    try:
        r = subprocess.run(["gws", "sheets", "spreadsheets", "values", "get", "--params",
                            json.dumps({"spreadsheetId": SHEET_ID, "range": SHEET_RANGE}, ensure_ascii=False)],
                           capture_output=True, text=True, timeout=120, cwd=str(Path(__file__).resolve().parents[4]))
        out = r.stdout[r.stdout.find("{"):]
        vals = json.loads(out)["values"]
        common.write_json(SHEET_CACHE, vals)
    except Exception as e:
        print(f"  [경고] 효자상품 시트 읽기 실패 {e} — 마지막 사본 사용", flush=True)
        try:
            vals = json.loads(SHEET_CACHE.read_text(encoding="utf-8"))
        except Exception:
            return []
    rows, seen = [], set(exclude)
    for i, r in enumerate(vals):
        code = r[2].strip() if len(r) > 2 else ""
        if not code or code in seen:
            continue
        seen.add(code)
        idx = int(r[0]) if r and str(r[0]).isdigit() else 100000 + i
        rows.append({"code": code, "productId": (r[3] if len(r) > 3 else None) or None, "title": r[5] if len(r) > 5 else None,
                     "market": None, "clk": 0, "purCnt": 0, "rules": ["효자상품 시트"], "src": 1, "rank": idx, "noInspect": True})
    return rows


def collect_sold(exclude):
    """판매 잠금 기록(new_locks) — 최근 잠금일 순. 광고 후보와 겹치는 코드는 뺀다."""
    by = {}
    try:
        days = sorted((p for p in SOLD.iterdir() if p.name[:4].isdigit()), reverse=True)
    except Exception:
        return []
    for day in days:
        try:
            rows = json.loads((day / "new_locks.json").read_text(encoding="utf-8"))
        except Exception:
            continue
        for r in rows:
            code = r.get("판매자상품코드")
            if code and code not in by and code not in exclude:
                by[code] = {"code": code, "productId": r.get("불사자ID"), "title": None, "market": r.get("마켓번호"),
                            "clk": int(day.name.replace("-", "")), "purCnt": 1, "rules": ["판매"], "src": 2, "rank": 0}
    return list(by.values())


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
                    "market": r.get("마켓번호"), "clk": 0, "purCnt": 0, "rules": [], "src": 0, "rank": 0})
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

    if args.run_dir:   # 예전 방식(맥북 광고 회차 지정) — 수동 재현용으로만 남김
        run_dir = common.ADS_RUNS / args.run_dir
        rows, label = collect_rows(run_dir), f"광고 {run_dir.name}"
    else:
        rows, got = collect_priority()
        label = f"광고 우선순위 {got}"
    sheet = collect_sheet({x["code"] for x in rows})
    sold = collect_sold({x["code"] for x in rows + sheet})
    print(f"[후보] {label} {len(rows)}건 + 효자상품 시트 {len(sheet)}건 + 판매 잠금 {len(sold)}건")
    rows += sheet + sold

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
                x["bead"] = bool(it and str(it.get("상품명") or "").startswith("비즈 "))
                if it:
                    x["productId"] = it.get("productId") or x["productId"]
                    x["name"] = it.get("상품명")
        # 광고 우선순위는 파일 순위 그대로, 판매 잠금은 잠금 → 최근 잠금일
        rows.sort(key=lambda x: (x["src"], x["rank"], not x["locked"], -x["purCnt"], -x["clk"]))

        # 2) 순서대로 상세를 실시간 재확인 — limit 채우면 멈춘다
        for x in rows:
            if len(picked) >= args.limit:
                break
            if not x["found"]:
                skipped.append({**x, "skip": "불사자에서 코드 못 찾음"}); continue
            if x["bead"] and not x.get("noInspect"):
                skipped.append({**x, "skip": "비즈 부자재(검수 SMALL)"}); continue
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
            mj = None if x.get("noInspect") else common.inspect_machine(wd)   # 효자상품 시트는 검수 생략
            if mj:
                skipped.append({**x, "skip": f"검수 탈락(기계) {mj['reason']} {mj['note']}"}); continue
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
    common.write_json(out / "targets.json", {"adsRun": label, "limit": args.limit,
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
