#!/usr/bin/env python3
"""불사자 소싱기 반영(쓰기) — 휴지통 이동 · 이미지 매칭.

요청 형식은 2026-10-19 웹 화면 코드(실측)에서 그대로 옮겼다:
- 휴지통:   POST /api/sourcing/bulk-workflow-transition {productIds:[문서ID], toStatus:"delete"}
- 매칭 1건: POST /api/sourcing/taobao/officialimage {imageUrl}
            → POST /opensearch/proxy/sourcing/match-status/apply
               {docId, matchStatus, failReason, taobaoResult, averageTaobaoPrice, overseaDeliveryFee, enforceFrom}
            → (성공 시) POST /api/user/use/limit {data:{limitValue:"taobao_image"}}
  평균가·배송비 계산(calcSafePrice/calcDeliveryFee)도 웹과 같은 공식이다.
- 웹 화면은 '매칭대기'에서 매칭에 실패한 상품을 휴지통으로 보낸다 → 실패분은 마지막에 휴지통 이동.

사용:
  apply_sourcing.py trash --run-dir R1 --run-dir R2 [--dry-run]     # 판정 drop 중 서버에 남은 것 휴지통
  apply_sourcing.py match --run-dir R1 [--limit N] [--workers 3]    # 판정 pass 중 매칭대기인 것 이미지 매칭
체크포인트: <첫 run-dir>/apply_trash.jsonl, <run-dir>/apply_match.jsonl (재실행 시 이미 처리한 건 건너뜀)
"""
import argparse
import json
import math
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sourcing_api as sa  # noqa: E402

DATA_ROOT = os.path.expanduser("~/python_work/data/sourcing-inspect/runs")
CAMPAIGN = "YWfs4MpPnVWHzYW"


def run_path(r):
    return r if os.path.isabs(r) else os.path.join(DATA_ROOT, r)


def post(tok, path, body, timeout=120):
    """웹과 같은 헤더로 POST. 실패는 예외."""
    try:
        r = requests.post(sa.API + path, json=body, headers=sa._headers(tok), timeout=timeout)
    except requests.RequestException as e:
        raise RuntimeError(f"{path} 연결 실패: {e}")
    if r.status_code == 401:
        raise RuntimeError("401 — 웹 토큰 만료. 크롬에서 불사자 재로그인 후 web_token.py")
    if r.status_code >= 400:
        raise RuntimeError(f"{path} HTTP {r.status_code}: {r.text[:300]}")
    try:
        return r.json()
    except ValueError:
        return {}


def load_jsonl(p):
    out = {}
    try:
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    d = json.loads(line)
                    out[d["id"]] = d
    except FileNotFoundError:
        pass
    return out


def server_state(tok, ids=()):
    """현재 서버 목록(휴지통 제외) → {id: product}. 캠페인은 문서ID '11154-<캠페인>-<상품>' 에서 뽑는다."""
    camps = {str(i).split("-")[1] for i in ids if str(i).count("-") >= 2} or {CAMPAIGN}
    out = {}
    for c in sorted(camps):
        try:
            out.update({p["id"]: p for p in sa.fetch_products(c, tok)})
        except RuntimeError as e:
            print(f"[server] 캠페인 {c} 조회 실패: {e}")
            raise
    return out


# ---------------- 휴지통 ----------------
def cmd_trash(a):
    tok = sa.load_token()
    drop = []
    for r in a.run_dir:
        v = json.load(open(os.path.join(run_path(r), "verdicts.json"), encoding="utf-8"))
        drop += [i for i, x in v.items() if x.get("verdict") == "drop"]
    live = server_state(tok, drop)
    targets = sorted(set(i for i in drop if i in live))
    print(f"[trash] 판정 drop {len(set(drop))}건 중 서버에 남은 {len(targets)}건")
    if a.dry_run:
        return
    ck = os.path.join(run_path(a.run_dir[0]), "apply_trash.jsonl")
    done = load_jsonl(ck)
    todo = [i for i in targets if i not in done]
    ok = fail = 0
    with open(ck, "a", encoding="utf-8") as f:
        for k in range(0, len(todo), 200):
            chunk = todo[k:k + 200]
            try:
                res = post(tok, "/api/sourcing/bulk-workflow-transition",
                           {"productIds": chunk, "toStatus": "delete"}, timeout=300)
            except RuntimeError as e:
                print(f"[trash] 묶음 {k // 200 + 1} 실패: {e}")
                fail += len(chunk)
                continue
            bad = {str(x.get("productId") or x.get("id") or x) for x in (res.get("failedItems") or [])}
            for i in chunk:
                f.write(json.dumps({"id": i, "ok": i not in bad}, ensure_ascii=False) + "\n")
            ok += res.get("successCount", 0)
            fail += res.get("failCount", 0)
            print(f"[trash] {min(k + 200, len(todo))}/{len(todo)}  성공 {ok} 실패 {fail}", flush=True)
    print(f"[trash] 완료 성공 {ok} / 실패 {fail}")


# ---------------- 이미지 매칭 ----------------
def calc_safe_price(lst):
    """웹 calcSafePrice: 중앙값의 60% 이상 중 최저가(원화 아님, 위안)."""
    ps = []
    for e in lst or []:
        d = ((e or {}).get("item") or {}).get("sku", {}).get("def", {}) or {}
        c = d.get("promotionPrice")
        if c is None:
            c = d.get("price")
        if c is None:
            c = "0"
        try:
            c = c if isinstance(c, (int, float)) else float(str(c))
        except ValueError:
            continue
        if c > 0 and not math.isnan(c):
            ps.append(c)
    if not ps:
        return 0
    a = sorted(ps)
    r = len(a) // 2
    med = (a[r - 1] + a[r]) / 2 if len(a) % 2 == 0 else a[r]
    n = [x for x in a if x >= 0.6 * med]
    return round(n[0] if n else a[0])  # JS Math.round 와 .5 처리 차이는 무시 가능


def calc_delivery_fee(price, avg, rate=200):
    """웹 calcDeliveryFee 그대로."""
    r = price - avg * rate * 1.25
    if r > 0.35 * price:
        r = 0.35 * price
        if r >= 1e5:
            r = 0.15 * price
        elif r < 6e3:
            r = 6e3
    elif r <= 0.17 * price:
        r = 0.2 * price
        if r >= 1e5:
            r = 0.15 * price
        elif r < 6e3:
            r = 6e3
    elif r < 6e3:
        r = 6e3
    elif r >= 1e5:
        r = 0.15 * price
    r *= 1.1
    return 1000 * round(r / 1000)


def match_one(tok, p, enforce_from="pending"):
    """상품 1건 매칭 → {'id','status','reason','n'}."""
    status, reason, lst = "match_failed", None, None
    try:
        res = post(tok, "/api/sourcing/taobao/officialimage", {"imageUrl": p["productImageUrl"]}, timeout=90)
        lst = ((res or {}).get("result") or {}).get("resultList")
        if isinstance(lst, list) and lst:
            status = "completed"
        else:
            reason = "no_result"
    except RuntimeError as e:
        msg = str(e)
        if "401" in msg:
            raise
        reason = "no_result" if ("DATA_EMPTY" in msg or "404" in msg) else (
            "limit_exhausted" if ("LIMIT_EXHAUSTED" in msg or "PAID_PLEASE" in msg) else "api_error")
    avg = fee = None
    if status == "completed" and (p.get("productPrice") or 0) > 0:
        avg = calc_safe_price(lst)
        if avg > 0:
            fee = calc_delivery_fee(p["productPrice"], avg)
    body = {"docId": p["id"], "matchStatus": status, "failReason": reason}
    if enforce_from:  # 웹: 1차검토에서 매칭할 땐 enforceFrom 을 안 보낸다
        body["enforceFrom"] = enforce_from
    if status == "completed":
        body.update(taobaoResult=lst, averageTaobaoPrice=avg, overseaDeliveryFee=fee)
    skipped = False
    try:
        r = post(tok, "/opensearch/proxy/sourcing/match-status/apply", body, timeout=120)
        skipped = bool((r or {}).get("skipped"))
    except RuntimeError as e:
        if "401" in str(e):
            raise
        status, reason = "match_failed", "apply_error"
    if status == "completed" and not skipped:
        try:
            post(tok, "/api/user/use/limit", {"data": {"limitValue": "taobao_image"}}, timeout=30)
        except RuntimeError:
            pass
    return {"id": p["id"], "status": "skipped" if skipped else status, "reason": reason,
            "n": len(lst) if isinstance(lst, list) else 0}


def cmd_match(a):
    tok = sa.load_token()
    R = run_path(a.run_dir)
    v = json.load(open(os.path.join(R, "verdicts.json"), encoding="utf-8"))
    live = server_state(tok, v.keys())
    targets = [live[i] for i, x in v.items()
               if x.get("verdict") == "pass" and i in live
               and (live[i].get("status") == "first_review" if a.from_status == "first_review"
                    else live[i].get("status") == "ready" and live[i].get("taobao_match_status") == "pending")
               and live[i].get("productImageUrl")]
    enforce = None if a.from_status == "first_review" else "pending"
    ck = os.path.join(R, "apply_match.jsonl")
    done = load_jsonl(ck)
    todo = [p for p in targets if p["id"] not in done]
    if a.limit:
        todo = todo[:a.limit]
    print(f"[match] 판정 pass·매칭대기 {len(targets)}건, 이번 {len(todo)}건 (이미 처리 {len(done)})", flush=True)
    lock = threading.Lock()
    cnt = {"completed": 0, "match_failed": 0, "skipped": 0}
    stop = threading.Event()
    t0 = time.time()
    with open(ck, "a", encoding="utf-8") as f, ThreadPoolExecutor(a.workers) as ex:
        futs = {}
        it = iter(todo)

        def submit_next():
            p = next(it, None)
            if p is not None and not stop.is_set():
                futs[ex.submit(match_one, tok, p, enforce)] = p

        for _ in range(a.workers * 2):
            submit_next()
        k = 0
        while futs:
            for fu in as_completed(list(futs)):
                futs.pop(fu)
                try:
                    r = fu.result()
                except RuntimeError as e:
                    print(f"[match] 중단: {e}", flush=True)
                    stop.set()
                    continue
                with lock:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
                    f.flush()
                    cnt[r["status"]] = cnt.get(r["status"], 0) + 1
                    k += 1
                    if r.get("reason") == "limit_exhausted":
                        print("[match] 한도 소진 — 중단", flush=True)
                        stop.set()
                if k % 100 == 0:
                    el = time.time() - t0
                    print(f"[match] {k}/{len(todo)}  {cnt}  {el / k:.2f}s/건", flush=True)
                submit_next()
                break
    print(f"[match] 완료 {k}건 {cnt}", flush=True)


# ---------------- 상품수집 ----------------
# 2026-10-19 사용자가 수집창에서 실제로 누른 옵션(콘솔 '폼 데이터' 실측) 그대로
COLLECT_OPTIONS = {"applyOriginalMarketPrice": False, "originalMarketPrice": None, "collectType": 1,
                   "mainThumbnailCount": 1, "productNameOption": 0, "cleanOptionPrice": True,
                   "cleanOptionText": True, "applyProductNameFilter": True, "aiOption": False, "model": ""}
NEW_SOURCING_GROUP = 1007620  # 신규소싱상품


def get_json(tok, path, timeout=60):
    try:
        r = requests.get(sa.API + path, headers=sa._headers(tok), timeout=timeout)
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError):
        return {}


def mall_key(url):
    """웹 source_mall_key: 프로토콜·끝 슬래시 제거."""
    if not url:
        return None
    u = url.split("://", 1)[-1].rstrip("/")
    return u or None


def collect_item(p, group_id):
    it = ((p.get("taobaoResult") or [{}])[0] or {}).get("item") or {}
    item_id = str(it.get("itemId") or "")
    if not item_id:
        return None
    tags = p.get("sellerTags") if isinstance(p.get("sellerTags"), list) and p.get("sellerTags") else None
    return {
        "selectedItem": {
            "bulsaSourcingId": p["id"], "itemId": item_id,
            "url": f"https://item.taobao.com/item.htm?id={item_id}", "sourcingType": "taobao",
            "method": "엔잡곰소싱기", "productName": p.get("productName"),
            "overseaDeliveryFee": p.get("overseaDeliveryFee"),
            "recommendedOverseaDeliveryFee": p.get("overseaDeliveryFee"),
            "plusMargin": None, "tags": tags, "naverCategoryCode": p.get("catId") or "",
            "firstThumbnail": None, "smartstoreFirstThumbnail": None,
            "ref_product_url": p.get("productUrl"), "source_mall_key": mall_key(p.get("mallUrl")),
        },
        "uploadSelectedMarketGroupId": group_id,
        "selectedOptions": dict(COLLECT_OPTIONS),
        "SourceLanguage": "zh-CN", "TargetLanguage": "ko",
        "preventDuplicateInGroup": True, "isReSourcing": False,
    }


def cmd_collect(a):
    tok = sa.load_token()
    ok_ids = set()
    for r in a.run_dir:
        v = json.load(open(os.path.join(run_path(r), "verdicts.json"), encoding="utf-8"))
        bad = {i for i, x in v.items() if x.get("verdict") == "drop"}
        ok_ids |= {i for i, x in v.items() if x.get("verdict") == "pass"}
        ok_ids -= bad
    live = server_state(tok, ok_ids)
    items = [collect_item(live[i], a.group) for i in sorted(ok_ids) if i in live]
    items = [x for x in items if x]
    ck = os.path.join(run_path(a.run_dir[-1]), "apply_collect.jsonl")
    done = load_jsonl(ck)
    todo = [x for x in items if x["selectedItem"]["bulsaSourcingId"] not in done]
    if a.limit:
        todo = todo[:a.limit]
    print(f"[collect] 판정 pass {len(ok_ids)}건 중 서버에 남은 수집가능 {len(items)}건, 이번 {len(todo)}건", flush=True)
    if a.dry_run:
        print(json.dumps(todo[:1], ensure_ascii=False, indent=1)[:1500])
        return
    excl = []
    for kind in ("common", "sourcing"):
        excl += get_json(tok, f"/api/sourcing/filter-words/{kind}").get("excluded_markets") or []
    reg = skip = 0
    with open(ck, "a", encoding="utf-8") as f:
        for k in range(0, len(todo), a.size):
            chunk = todo[k:k + a.size]
            try:
                res = post(tok, "/api/scrape", {"data": {"options": chunk,
                                                        "batchId": f"bulsa-sourcing-{int(time.time() * 1000)}",
                                                        "excluded_mall_keys": excl}}, timeout=900)
            except RuntimeError as e:
                print(f"[collect] 묶음 {k // a.size + 1} 실패: {e}", flush=True)
                if "401" in str(e):
                    break
                continue
            d = (res or {}).get("data") or {}
            regs = {o["selectedItem"]["bulsaSourcingId"] for o in d.get("registeredOptions") or []}
            skips = {(o.get("selectedItem") or {}).get("bulsaSourcingId") or o.get("bulsaSourcingId")
                     for o in d.get("skippedOptions") or []}
            for x in chunk:
                i = x["selectedItem"]["bulsaSourcingId"]
                f.write(json.dumps({"id": i, "ok": i in regs, "skipped": i in skips}, ensure_ascii=False) + "\n")
            reg += len(regs)
            skip += len(d.get("skippedOptions") or [])
            print(f"[collect] {min(k + a.size, len(todo))}/{len(todo)}  예약 {reg} 실패 {skip}  "
                  f"남은한도 {(d.get('remainingLimit') or {}).get('taobao')}", flush=True)
            time.sleep(1)
    print(f"[collect] 완료 예약 {reg} / 실패 {skip}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    t = sp.add_parser("trash")
    t.add_argument("--run-dir", action="append", required=True)
    t.add_argument("--dry-run", action="store_true")
    m = sp.add_parser("match")
    m.add_argument("--run-dir", required=True)
    m.add_argument("--limit", type=int, default=0)
    m.add_argument("--workers", type=int, default=3)
    m.add_argument("--from-status", choices=["pending", "first_review"], default="pending",
                   help="first_review = 1차검토 탭 상품(웹처럼 실패해도 1차검토에 남음)")
    c = sp.add_parser("collect")
    c.add_argument("--run-dir", action="append", required=True)
    c.add_argument("--group", type=int, default=NEW_SOURCING_GROUP)
    c.add_argument("--size", type=int, default=100)
    c.add_argument("--limit", type=int, default=0)
    c.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    try:
        {"trash": cmd_trash, "match": cmd_match, "collect": cmd_collect}[a.cmd](a)
    except RuntimeError as e:
        print(f"[오류] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
