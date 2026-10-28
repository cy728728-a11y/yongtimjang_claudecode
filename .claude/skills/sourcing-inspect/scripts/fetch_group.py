#!/usr/bin/env python3
"""
수집상품 마켓그룹 → 검수용 snapshot.json (run_inspect.py prep --stage 2 가 그대로 읽는 형식).

이미 타오바오에서 수집된 상품이라 '실제로 팔 물건' 자체가 이 상품이다. 그래서 2차 형식으로 맞춘다:
  taobaoResult[0].item.title = 상품명 + 옵션 중국어 원문 일부(브랜드가 중국어로만 보일 때가 있다)
  taobaoResult[0].item.image = 대표 썸네일
  catId = 스마트스토어 카테고리 코드 → banned_cats.txt 기계탈락이 그대로 걸린다

사용법:
  python fetch_group.py --run-dir 1027_st1000 --group-id 1008211 --pages 20 --random-pages --seed 1
  python fetch_group.py --run-dir <R> --group-id 1008211 --all          # 전체 (재실행 시 이어받기)
"""
import argparse
import concurrent.futures
import json
import os
import random
import sys
import threading

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

PAGE = 50
_local = threading.local()


def mcp():
    """스레드마다 MCP 연결 하나."""
    if not getattr(_local, "m", None):
        _local.m = BulsajaMCP(sleep=3, max_retries=7)  # 429 대비
        _local.m.open()
    return _local.m


def list_page(gid, page):
    try:
        r = mcp().call_tool("bulsaja_product_list", {"marketGroupId": gid, "page": page, "pageSize": PAGE})
        return r.get("전체개수"), r.get("항목") or []
    except Exception as e:
        print(f"[목록] {page}쪽 실패: {e}")
        return None, []


def to_item(row):
    """workdata 1건 → 스냅샷 항목. 실패하면 None."""
    pid = row.get("productId")
    try:
        d = (mcp().call_tool("bulsaja_product_workdata", {"productId": pid}) or {}).get("data") or {}
    except Exception as e:
        print(f"[상세] {pid} 실패: {e}")
        return None
    name = d.get("productName") or row.get("상품명") or ""
    thumbs = d.get("uploadThumbnails") or []
    ss = ((d.get("uploadCategory") or {}).get("ss_category") or {})
    zh = []
    try:
        for v in ((d.get("uploadSkuProps") or {}).get("mainOption") or {}).get("values") or []:
            if v.get("_name") and v["_name"] not in zh:
                zh.append(v["_name"])
            if len(zh) >= 5:
                break
    except Exception:
        pass
    title = name + (" / 옵션원문: " + " | ".join(zh) if zh else "")
    return {
        "id": pid, "productId": pid, "productName": name, "catId": str(ss.get("code") or ""),
        "productImageUrl": thumbs[0] if thumbs else "", "status": "ready", "brand": "",
        "sellerTags": [], "productPrice": row.get("판매가"), "group": row.get("마켓그룹"),
        "taobaoResult": [{"item": {"title": title, "image": thumbs[0] if thumbs else "",
                                   "itemUrl": "", "sku": {"def": {"price": ""}}}}],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--group-id", type=int, required=True)
    ap.add_argument("--pages", type=int, default=20)
    ap.add_argument("--random-pages", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    rd = resolve_run_dir(a.run_dir)
    os.makedirs(rd, exist_ok=True)
    snap_path = os.path.join(rd, "snapshot.json")
    try:
        have = {i["id"]: i for i in json.load(open(snap_path))} if os.path.exists(snap_path) else {}
    except Exception as e:
        sys.exit(f"기존 snapshot 읽기 실패: {e}")

    total, first = list_page(a.group_id, 1)
    if not total:
        sys.exit("그룹 목록 조회 실패")
    npages = (total + PAGE - 1) // PAGE
    if a.all:
        pages = list(range(1, npages + 1))
    elif a.random_pages:
        pages = sorted(random.Random(a.seed).sample(range(1, npages + 1), min(a.pages, npages)))
    else:
        pages = list(range(1, min(a.pages, npages) + 1))
    print(f"[group] 총 {total}건 / {npages}쪽 중 {len(pages)}쪽 조회")

    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as ex:
        for _, items in ex.map(lambda p: list_page(a.group_id, p), pages):
            rows.extend(items)
    rows = [r for r in rows if r.get("productId") and r["productId"] not in have]
    print(f"[group] 새로 상세 조회 {len(rows)}건 (기존 {len(have)}건)")

    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as ex:
        for it in ex.map(to_item, rows):
            done += 1
            if it:
                have[it["id"]] = it
            if done % 200 == 0:
                json.dump(list(have.values()), open(snap_path, "w"), ensure_ascii=False)
                print(f"[group] {done}/{len(rows)}")
    json.dump(list(have.values()), open(snap_path, "w"), ensure_ascii=False)
    miss = sum(1 for i in have.values() if not i["productImageUrl"])
    print(f"[group] snapshot {len(have)}건 저장 (썸네일 없음 {miss}) → {snap_path}")


if __name__ == "__main__":
    main()
