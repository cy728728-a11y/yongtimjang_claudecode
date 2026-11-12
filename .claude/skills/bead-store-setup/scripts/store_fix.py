# 스토어에 올라간 비즈 300개를 한 번에 세팅(커머스API):
#   판매중 유지 + 전시중지 / 묶음배송 가능(기본 묶음그룹) / 유료 2,500 선결제 / 국내 상품출고지 / 반품 2,500 · 교환 5,000
#   즉시할인 제거 / 판매가 = --price (기본 100원)
# 사용: store_fix.py <마켓> <one|all> [가격]
# 수정 전 원본은 data/backup_<마켓>.jsonl 에 남기고, 저장 후 다시 불러와 확인한다. 이미 맞는 상품은 건너뜀.
import sys, os, json, copy, time, re
from common import *

mk, mode = sys.argv[1], sys.argv[2]
PRICE = int(sys.argv[3]) if len(sys.argv) > 3 else 100
WANT = {"bundle": True, "feeType": "PAID", "base": 2500, "ret": 2500, "exc": 5000, "disp": "SUSPENSION", "price": PRICE, "할인": None}


def setup(api):
    ab = api._request(mk, "GET", "/v1/seller/addressbooks-for-page", params={"page": 1, "size": 50})["addressBooks"]
    dom = [a for a in ab if not a.get("overseasAddress") and a.get("addressType") in ("GENERAL", "RELEASE") and "출고" in (a.get("name") or "")]
    bg = [g for g in api._request(mk, "GET", "/v1/product-delivery-info/bundle-groups", params={"page": 1, "size": 50})["contents"]
          if g.get("baseGroup") and g.get("usable")]
    # 국내 출고지가 여러 개여도 주소가 전부 같으면 문제없다: "상품출고지" 우선, 없으면 첫 번째
    if len(dom) > 1 and len({a.get("baseAddress") for a in dom}) == 1:
        dom = [next((a for a in dom if a.get("name") == "상품출고지"), dom[0])]
    if len(dom) != 1 or len(bg) != 1:
        raise RuntimeError(f"국내 출고지 {[a['name'] for a in dom]} / 기본 묶음그룹 {[g['name'] for g in bg]} — 하나로 안 정해짐, 사람 확인")
    return dom[0], bg[0]


def build(p, addr, grp):
    b = copy.deepcopy(p); op = b["originProduct"]
    di = op["deliveryInfo"]
    di["deliveryBundleGroupUsable"] = True; di["deliveryBundleGroupId"] = grp["id"]
    fee = di.setdefault("deliveryFee", {})
    fee["deliveryFeeType"] = "PAID"; fee["baseFee"] = 2500; fee.setdefault("deliveryFeePayType", "PREPAID")
    fee.pop("deliveryFeeByArea", None)          # 묶음그룹 쓰면 지역별 배송비를 상품에 넣으면 400 에러
    cl = di.setdefault("claimDeliveryInfo", {})
    cl["returnDeliveryFee"] = 2500; cl["exchangeDeliveryFee"] = 5000; cl["shippingAddressId"] = addr["addressBookNo"]
    (op.get("customerBenefit") or {}).pop("immediateDiscountPolicy", None)
    op["salePrice"] = PRICE
    # 옵션가는 판매가의 100%까지만 가능(100원이면 0~100원). 옵션마다 가격 차이가 큰 마켓(1-3: 0/2,100/3,700원)은 옵션가를 0으로 맞춘다.
    # → 옵션 상관없이 전부 같은 PRICE. 원래 옵션가는 backup_<마켓>.jsonl 에 남아 있다.
    for o in (op.get("detailAttribute") or {}).get("optionInfo", {}).get("optionCombinations") or []:
        if (o.get("price") or 0) > PRICE: o["price"] = 0
    for o in (op.get("detailAttribute") or {}).get("optionInfo", {}).get("optionStandards") or []:
        if (o.get("price") or 0) > PRICE: o["price"] = 0
    b.setdefault("smartstoreChannelProduct", {})["channelProductDisplayStatusType"] = "SUSPENSION"
    return b


def check(p, addr):
    op = p["originProduct"]; di = op["deliveryInfo"]; fee = di.get("deliveryFee") or {}; cl = di.get("claimDeliveryInfo") or {}
    got = {"bundle": di.get("deliveryBundleGroupUsable"), "feeType": fee.get("deliveryFeeType"), "base": fee.get("baseFee"),
           "ret": cl.get("returnDeliveryFee"), "exc": cl.get("exchangeDeliveryFee"),
           "disp": (p.get("smartstoreChannelProduct") or {}).get("channelProductDisplayStatusType"),
           "price": op.get("salePrice"), "할인": (op.get("customerBenefit") or {}).get("immediateDiscountPolicy")}
    bad = {k: got[k] for k in WANT if got[k] != WANT[k]}
    if cl.get("shippingAddressId") != addr["addressBookNo"]: bad["출고지"] = cl.get("shippingAddressId")
    if any((o.get("price") or 0) > PRICE for o in (op.get("detailAttribute") or {}).get("optionInfo", {}).get("optionCombinations") or []):
        bad["옵션가"] = "판매가보다 큼"
    if op.get("statusType") != "SALE": bad["판매상태"] = op.get("statusType")
    return bad


try:
    m = bulsaja(); _, names = originals(m); m.close()
    api = commerce(mk)
    addr, grp = setup(api)
    print(f"출고지: {addr['name']} / 묶음그룹: {grp['name']} / 판매가 {PRICE}원·할인 없음", flush=True)
    tg = []
    for c in store_products(api, mk):
        for ch in c.get("channelProducts") or []:
            if norm(ch.get("name")) in names:
                tg.append((c["originProductNo"], ch.get("name"))); break
    print("스토어 비즈", len(tg), flush=True)
    if mode == "one": tg = tg[:1]
    bk = open(os.path.join(DATA_DIR, f"backup_{mk}.jsonl"), "a")
    ok, skip, fail = 0, 0, []
    for no, name in tg:
        try:
            p = api._request(mk, "GET", f"/v2/products/origin-products/{no}")
            if not check(p, addr): skip += 1; continue
            bk.write(json.dumps({"no": no, "at": time.strftime("%F %T"), "product": p}, ensure_ascii=False) + "\n"); bk.flush()
            body = build(p, addr, grp)
            try:
                api._request(mk, "PUT", f"/v2/products/origin-products/{no}", json=body)
            except RuntimeError as e:
                # 네이버가 나중에 등록불가로 바꾼 태그 단어(예: "서브")가 있으면 저장이 통째로 막힌다 → 그 단어 든 태그만 빼고 다시
                w = re.search(r"등록불가인 단어\(([^)]+)\)", str(e))
                if not w: raise
                seo = body["originProduct"]["detailAttribute"].get("seoInfo") or {}
                seo["sellerTags"] = [t for t in seo.get("sellerTags") or [] if w.group(1) not in (t.get("text") or "")]
                api._request(mk, "PUT", f"/v2/products/origin-products/{no}", json=body)
            # 다시 불러와 확인은 처음 3개만(호출 1초 간격 제한 때문에 전수 확인은 느림). 가격·전시는 마지막 상태 확인에서 300개 전수로 본다.
            bad = check(api._request(mk, "GET", f"/v2/products/origin-products/{no}"), addr) if ok + len(fail) < 3 else {}
            if bad: fail.append((no, name[:30], bad))
            else: ok += 1
        except Exception as e:
            fail.append((no, name[:30], str(e)[:300]))
    print(f"완료 {ok} · 이미 맞음 {skip} · 실패 {len(fail)}")
    for f in fail[:10]: print("실패", f)
except Exception as e:
    print("오류:", repr(e)[:400])
