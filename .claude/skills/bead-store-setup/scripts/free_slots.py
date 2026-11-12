# 빈자리 확보: 잠금 안 된·유입 적은 업로드 상품을 골라 [삭제] 메모 → 스마트스토어에서만 삭제(불사자 원본 유지)
# 사용: free_slots.py <마켓> [run]   (run 없으면 고르기만 하고 목록만 저장)
# 고르는 순서: 30일 유입 적은 순 → 업로드 오래된 순. 비즈 복사본·잠금 상품은 절대 안 고른다.
import sys, os, json, datetime
from common import *

mk = sys.argv[1]; RUN = len(sys.argv) > 2 and sys.argv[2] == "run"
cache = os.path.join(DATA_DIR, f"traffic_{mk}.json")
try:
    m = bulsaja()
    _, names = originals(m)
    g = find_group(m, mk)
    api = commerce(mk)
    limit, cnt = sheet_limit(mk), store_count(api, mk)
    on_store = sum(1 for c in store_products(api, mk) for ch in (c.get("channelProducts") or [])[:1] if norm(ch.get("name")) in names)
    if on_store:
        print(f"스토어에 비즈가 이미 {on_store}개 있음 — 업로드 시작 뒤엔 삭제하지 않는다. 사람 확인"); sys.exit()
    need = max(0, KEEP_FREE - (limit - cnt))
    print(f"한도 {limit} · 현재 {cnt} · 빈자리 {limit - cnt} · 지울 개수 {need}", flush=True)
    if need == 0:
        print("삭제 필요 없음"); sys.exit()
    # 안전장치: 시트 한도와 실제 등록 수가 안 맞거나(현재 > 한도) 지울 양이 너무 많으면 지우지 않고 사람에게 넘긴다
    if cnt > limit or need > MAX_DELETE:
        print(f"보류: 한도 {limit}인데 현재 {cnt}, 지울 개수 {need} — 시트 한도가 틀렸거나 매출 영향이 큼. 사람 확인"); sys.exit()
    items = pages(m, "bulsaja_market_group_products", {"groupId": g["groupId"]})
    cand = [i for i in items if i.get("상태코드") == 4 and not i.get("잠금") and norm(i["상품명"]) not in names]
    rows = {r["id"]: r for r in json.load(open(cache))} if os.path.exists(cache) else {}
    for n, i in enumerate(cand):
        if i["productId"] in rows: continue
        try:
            d = call(m, "bulsaja_traffic_analytics", {"productId": i["productId"]}).get("data") or {}
            rows[i["productId"]] = {"id": i["productId"], "이름": i["상품명"],
                                    "유입30일": sum(x.get("viewCount") or 0 for x in d.get("series") or []),
                                    "업로드일": (d.get("meta") or {}).get("uploadedProductDate") or ""}
        except Exception as e:
            print("유입 조회 실패", i["productId"], repr(e)[:120], flush=True)
        if n % 25 == 0:
            json.dump(list(rows.values()), open(cache, "w"), ensure_ascii=False); print("유입 조회", n, "/", len(cand), flush=True)
    json.dump(list(rows.values()), open(cache, "w"), ensure_ascii=False)
    pool = sorted((rows[i["productId"]] for i in cand if i["productId"] in rows), key=lambda r: (r["유입30일"], r["업로드일"]))
    pick = pool[:need]
    if len(pick) < need:
        print(f"후보 부족: {len(pick)}/{need} — 사람 확인 필요"); sys.exit()
    mx = max(p["유입30일"] for p in pick)
    print(f"고른 {len(pick)}개 · 최대 유입 {mx}회 · 업로드일 {pick[0]['업로드일'][:10]}~{pick[-1]['업로드일'][:10]}", flush=True)
    json.dump(pick, open(os.path.join(DATA_DIR, f"delete_pick_{mk}.json"), "w"), ensure_ascii=False)
    if not RUN:
        print("고르기만 함(run 붙이면 삭제)"); sys.exit()
    today = datetime.date.today().isoformat()
    line = f"[삭제] {today} · 비즈300 업로드 빈자리 확보(Claude) · {mk} 한도 {limit}/현재 {cnt}, 잠금X·30일 유입 {mx}회 이하, 스스에서만 삭제"
    memo_fail = 0
    for x in pick:
        try:
            cur = (call(m, "bulsaja_product_memo", {"productId": x["id"]}) or {}).get("메모") or ""
            if cur.startswith(f"[삭제] {today} · 비즈300"): continue   # 다시 돌릴 때 메모 중복 방지
            new = line + ("\n" + cur if cur else "")
            pv = call(m, "bulsaja_product_memo", {"productId": x["id"], "memo": new})
            if pv.get("confirmationToken"):
                pv = call(m, "bulsaja_product_memo", {"productId": x["id"], "memo": new, "confirm": True, "confirmationToken": pv["confirmationToken"]})
            if not pv.get("success"): memo_fail += 1
        except Exception:
            memo_fail += 1
    print("메모 실패", memo_fail, flush=True)
    # 한 번에 많이 넣으면 "원자적 생성 실패로 전체 그룹 미접수"로 통째 거절된다(1-3, 336개) → 50개씩, 실패 묶음은 한 번 더
    ids = [x["id"] for x in pick]; okn = 0; bad = []
    for b in range(0, len(ids), 50):
        batch = ids[b:b+50]
        for attempt in range(2):
            base = {"productIds": batch, "market": "SMARTSTORE", "deleteAction": "MARKET_ONLY", "confirm": True}
            pv = call(m, "bulsaja_market_delete", base)
            tok = pv.get("confirmationToken")
            r = call(m, "bulsaja_market_delete", dict(base, confirmationToken=tok)) if tok else pv
            if r.get("success"): okn += len(batch); break
            # PARTIAL 이어도 "삭제 대기열 접수됨"인 건 실제로 지워진다(1-3 실측) → 접수된 건 세고, 남은 것만 다시
            got = [x["productId"] for x in (r.get("결과") or []) if "접수" in str(x.get("결과"))]
            okn += len(got); batch = [i for i in batch if i not in got]
            if not batch: break
            time.sleep(30)
        else:
            bad.append(json.dumps({k: v for k, v in r.items() if k != "표시규칙"}, ensure_ascii=False)[:200])
    print(f"삭제 실행 접수 {okn}/{len(ids)}" + (f" · 실패 묶음 {len(bad)}: {bad[0]}" if bad else ""))
    m.close()
except SystemExit:
    pass
except Exception as e:
    print("오류:", repr(e))
