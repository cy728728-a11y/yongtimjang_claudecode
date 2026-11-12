# 조회만: 마켓 하나의 등록한도·현재 등록·빈자리, 불사자 그룹의 비즈 복사본 상태, 스토어의 비즈 세팅 상태
# 사용: status.py <마켓 예: 25-1>
import sys, json, collections
from common import *

mk = sys.argv[1]
try:
    m = bulsaja()
    _, names = originals(m)
    g = find_group(m, mk)
    beads = group_beads(m, g["groupId"], names)
    api = commerce(mk)
    limit, cnt = sheet_limit(mk), store_count(api, mk)
    st = collections.Counter()
    for c in store_products(api, mk):
        for ch in c.get("channelProducts") or []:
            if norm(ch.get("name")) in names:
                st[(ch.get("statusType"), ch.get("channelProductDisplayStatusType"), ch.get("salePrice"), ch.get("discountedPrice"))] += 1
    res = {"마켓": mk, "그룹": g["그룹명"], "그룹ID": g["groupId"], "등록한도": limit, "현재등록": cnt, "빈자리": limit - cnt,
           "확보필요": 0 if sum(st.values()) >= 300 else max(0, KEEP_FREE - (limit - cnt)),  # 이미 다 올라갔으면 지울 필요 없음
           "불사자_비즈복사본": len(beads), "불사자_업로드됨": sum(1 for b in beads if b.get("상태코드") == 4),
           "불사자_잠금": sum(1 for b in beads if b.get("잠금")),
           "스토어_비즈": sum(st.values()),
           "스토어_상태(판매,전시,판매가,실판매가)": {str(k): v for k, v in st.items()}}
    print(json.dumps(res, ensure_ascii=False, indent=1))
    m.close()
except Exception as e:
    print("오류:", repr(e))
