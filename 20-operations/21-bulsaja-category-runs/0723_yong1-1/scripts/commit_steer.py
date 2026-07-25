# -*- coding: utf-8 -*-
"""부분일치확인요 2건 — keyword 변형으로 top==target 조준 재시도 + 성공 시 즉시 저장.

steer_probe.py 의 변형 생성 로직을 확장(수제 변형 추가)하고,
조준 성공하면 그 자리에서 category_commit 까지 실행한다.
"""
import json
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SKILL_SCRIPTS = r"C:\Users\workspace\.claude\skills\bulsaja-category-fix\scripts"
sys.path.insert(0, SKILL_SCRIPTS)
from bulsaja_mcp import BulsajaMCP, _norm_path, _seg  # noqa: E402

# 대상: (productId, target 경로, 수제 변형 keyword 들)
ITEMS = [
    {
        "productId": "U01KY54HA46KK7V2HKY9W0H3ZPV",
        "상품명": "전동 청소솔 싱크대 청소 배관 욕실 화장실 자동 주방",
        "target": "생활/건강>청소용품>솔",
        "extra": ["청소솔", "청소용 솔", "바닥솔", "욕실솔", "다용도 솔", "솔 브러쉬"],
    },
    {
        "productId": "U01KY54HA3HR8YKTF4VFH3721N0",
        "상품명": "수제 동주전자 구리주전자 주전자 찻주전자 순수",
        "target": "생활/건강>주방용품>주전자/티포트>주전자",
        "extra": ["티포트 주전자", "찻주전자", "동주전자", "구리주전자",
                  "주방 주전자", "물 주전자"],
    },
]


def gen_keywords(target, name, extra):
    """조준용 keyword 후보 생성 (steer_probe 로직 + 수제 변형)."""
    t = _seg(target)
    leaf = t[-1] if t else ""
    kws = []

    def add(*parts):
        kw = " ".join(p for p in parts if p).strip()[:60]
        if kw and kw not in kws:
            kws.append(kw)

    add(leaf)
    add(leaf.replace("/", " "))
    for i in range(len(t) - 2, -1, -1):
        add(t[i], leaf)
        add(t[i].replace("/", " "), leaf)
    if len(t) >= 3:
        add(t[-3], t[-2], leaf)
    if t:
        add(t[0], leaf)
    if len(t) >= 2 and "/" in t[-2]:
        for piece in t[-2].split("/"):
            add(piece, leaf)
    for e in extra:
        add(e)
    if name:
        add(name.split()[0], leaf)
    return kws[:16]


def main():
    mcp = BulsajaMCP()
    mcp.open()
    results = []
    try:
        for it in ITEMS:
            pid = it["productId"]
            tgt = _norm_path(it["target"])
            kws = gen_keywords(tgt, it["상품명"], it["extra"])
            hit = None
            tried = []
            for kw in kws:
                try:
                    pv = mcp.category_preview(pid, kw)
                except Exception as e:
                    tried.append((kw, f"ERR {str(e)[:60]}"))
                    continue
                top = _norm_path(pv["ss_name"])
                tried.append((kw, top))
                if top == tgt and pv["token"]:
                    # 조준 성공 → 즉시 저장
                    cm = mcp.category_commit(pid, kw, pv["token"])
                    hit = kw if cm["success"] else None
                    if hit:
                        break
                time.sleep(0.3)
            status = "자동저장완료" if hit else "부분일치확인요(수동)"
            results.append({"productId": pid, "target": tgt,
                            "hit_keyword": hit, "상태": status, "tried": tried})
            print(f"{pid[-8:]} {status}" + (f" (keyword: {hit})" if hit else ""))
            if not hit:
                for kw, top in tried:
                    print(f"    [{kw}] -> {top}")
    finally:
        mcp.close()
    out = r"C:\Users\woori\AppData\Local\Temp\claude\C--Users-workspace\07619181-8232-427a-9023-2f3ea269bfe6\scratchpad\runs\0723_yong1-1\steer_results.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    ok = sum(1 for r in results if r["hit_keyword"])
    print(f"###STEER### 저장 {ok}/{len(results)}")


if __name__ == "__main__":
    main()
