# -*- coding: utf-8 -*-
"""마켓 하나의 전 상품 유입(최근 30일)을 상품별로 조회해, 유입 있는 미가공 상품 후보 파일을 만든다(읽기 전용).
사용: scan_market_traffic.py --group-id 1001114 --market 1-1   → ~/python_work/data/detail-opus/traffic-market/ 에 저장
중간 저장(체크포인트)으로 끊겨도 이어서 한다. 2026-11-14 용팀장 지시(1번 방식)."""
import argparse, json, sys, time
from datetime import date, timedelta
from pathlib import Path
import common, targets

ap = argparse.ArgumentParser()
ap.add_argument("--group-id", type=int, required=True)
ap.add_argument("--market", required=True)
a = ap.parse_args()
OUT = Path.home() / "python_work/data/detail-opus/traffic-market"; OUT.mkdir(parents=True, exist_ok=True)
ck = OUT / f"scan-{a.market}.ckpt.json"
state = json.loads(ck.read_text(encoding="utf-8")) if ck.exists() else {"list": None, "done": {}}
T = date.today(); S30 = (T - timedelta(29)).isoformat(); S7 = (T - timedelta(6)).isoformat(); E = T.isoformat()

def save():
    ck.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

m = common.mcp()
try:
    if state["list"] is None:
        items, page = [], 1
        while True:
            r = common.call(m, "bulsaja_market_group_products", {"groupId": a.group_id, "page": page, "pageSize": 50}, gap=1.0)
            got = r.get("항목") or []
            items += [{"pid": x["productId"], "name": x["상품명"], "locked": x.get("잠금")} for x in got]
            if len(got) < 50: break
            page += 1
        state["list"] = items; save()
        print(f"[목록] {len(items)}개", flush=True)
    todo = [x for x in state["list"] if x["pid"] not in state["done"]]
    print(f"[조회 남음] {len(todo)}개", flush=True)
    for i, x in enumerate(todo):
        pid = x["pid"]
        if targets.local_done(pid):
            state["done"][pid] = {"st": "로컬 결과 있음"}; continue
        try:
            t = common.call(m, "bulsaja_traffic_analytics", {"productId": pid, "startDate": S30, "endDate": E}, gap=2.5)
            ser = (t.get("data") or {}).get("series") or []
            v30 = sum(s.get("viewCount") or 0 for s in ser)
            v7 = sum(s.get("viewCount") or 0 for s in ser if s["date"] >= S7)
            vmax = max([s.get("viewCount") or 0 for s in ser] or [0])
            rec = {"st": "유입0" if v30 == 0 else "확인필요", "v30": v30, "v7": v7, "vmax": vmax}
            if v30 > 0:
                wd = common.call(m, "bulsaja_product_workdata", {"productId": pid, "mode": "full"}, gap=2.0).get("data") or {}
                rc = (wd.get("uploadDetailContents") or {}).get("renderContent") or ""
                dc = wd.get("uploadDetailContents") or {}
                rec["code"] = wd.get("uploadBulsajaCode"); rec["live"] = bool(wd.get("uploadedSuccessUrl"))
                if "/mcp-assets/" in rc or str(dc.get("aiImageGenerated")).lower() in ("true", "1"): rec["st"] = "이미 가공됨"
                elif "<img" not in rc: rec["st"] = "상세 이미지 없음"
                else: rec["st"] = "미가공"
            state["done"][pid] = rec
        except Exception as e:
            state["done"][pid] = {"st": f"조회 실패 {str(e)[:60]}"}
        if i % 25 == 0:
            save(); print(f"  {i}/{len(todo)} 유입있음 {sum(1 for v in state['done'].values() if v.get('v30'))}", flush=True)
finally:
    save(); m.close()

by = {x["pid"]: x for x in state["list"]}
cands = []
for pid, r in state["done"].items():
    if r["st"] == "미가공":
        cands.append({"pid": pid, "name": by[pid]["name"], "v30": r["v30"], "v7": r["v7"], "vmax": r["vmax"],
                      "code": r.get("code"), "live": r.get("live"), "market": a.market, "st": "미가공"})
cands.sort(key=lambda x: (-x["v30"], -x["vmax"]))
(OUT / f"traffic-candidates-{a.market}-{T.isoformat()}.json").write_text(json.dumps(cands, ensure_ascii=False, indent=1), encoding="utf-8")
import collections
print("[끝]", collections.Counter(v["st"].split(" ")[0] for v in state["done"].values()), "후보", len(cands), flush=True)
