# 그룹의 비즈 복사본 중 아직 안 올라간 것을 스마트스토어 업로드 접수(확인키 2단계). 다시 돌려도 진행 중인 건 중복으로 막혀 안전.
# 사용: upload.py <마켓>
import sys, json, collections
from common import *

mk = sys.argv[1]
try:
    m = bulsaja()
    _, names = originals(m)
    g = find_group(m, mk)
    beads = group_beads(m, g["groupId"], names)
    todo = [b["productId"] for b in beads if b.get("상태코드") != 4]
    print(f"그룹 비즈 {len(beads)} · 업로드 안 된 것 {len(todo)}", flush=True)
    if len(beads) != 300:
        print("그룹에 비즈가 300개가 아님 — 먼저 원본에서 빠진 것 복사 필요"); sys.exit()
    if not todo:
        print("이미 전부 업로드됨"); sys.exit()
    base = {"productIds": todo, "market": "SMARTSTORE", "marketGroupId": g["groupId"]}
    pv = call(m, "bulsaja_market_upload", base)
    if not pv.get("confirmationToken"):
        pv = call(m, "bulsaja_market_upload", dict(base, confirm=True))
    tok = pv.get("confirmationToken")
    if not tok:
        print("확인키 없음:", json.dumps(pv, ensure_ascii=False)[:400]); sys.exit()
    r = call(m, "bulsaja_market_upload", dict(base, confirm=True, confirmationToken=tok))
    print("접수", json.dumps({k: v for k, v in r.items() if k not in ("표시규칙", "결과")}, ensure_ascii=False)[:500])
    res = r.get("결과") or []
    if isinstance(res, list):
        print("결과 분포", dict(collections.Counter(str(x.get("결과"))[:30] for x in res)))
    m.close()
except SystemExit:
    pass
except Exception as e:
    print("오류:", repr(e))
