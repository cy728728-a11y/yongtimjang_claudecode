# 그룹에 빠진 비즈 원본을 복사해 300개를 채우고, 비즈 복사본을 전부 잠금(=숨김). 이미 잠긴 건 그대로.
# 사용: fill_and_lock.py <마켓>
import sys, json, time
from common import *

mk = sys.argv[1]
try:
    m = bulsaja()
    src, names = originals(m)
    g = find_group(m, mk)
    have = {norm(b["상품명"]) for b in group_beads(m, g["groupId"], names)}
    miss = [i["productId"] for i in src if norm(i["상품명"]) not in have]
    print(f"{g['그룹명']} 비즈 {len(have)} · 빠진 것 {len(miss)}", flush=True)
    for b in range(0, len(miss), 50):
        batch = miss[b:b+50]
        pv = call(m, "bulsaja_market_group_copy", {"productIds": batch, "marketGroupId": g["groupId"]})
        if pv.get("대상그룹") != g["그룹명"] or not pv.get("confirmationToken"):
            print("복사 미리보기 이상:", json.dumps(pv, ensure_ascii=False)[:300]); sys.exit()
        r = call(m, "bulsaja_market_group_copy", {"productIds": batch, "marketGroupId": g["groupId"], "confirm": True, "confirmationToken": pv["confirmationToken"]})
        print("복사", r.get("복사됨"), "실패", r.get("실패"), flush=True)
    if miss: time.sleep(5)
    beads = group_beads(m, g["groupId"], names)
    todo = [b["productId"] for b in beads if not b.get("잠금")]
    new = 0
    for b in range(0, len(todo), 50):
        batch = todo[b:b+50]
        pv = call(m, "bulsaja_product_hide", {"productIds": batch, "hide": True})
        tok = pv.get("confirmationToken")
        r = call(m, "bulsaja_product_hide", {"productIds": batch, "hide": True, "confirm": True, "confirmationToken": tok}) if tok else pv
        if r.get("success"): new += len(batch)
        else: print("잠금 실패", json.dumps(r, ensure_ascii=False)[:200], flush=True)
    print(f"비즈 {len(beads)} · 새 잠금 {new} · 기존 잠금 {len(beads) - len(todo)}")
    m.close()
except SystemExit:
    pass
except Exception as e:
    print("오류:", repr(e))
