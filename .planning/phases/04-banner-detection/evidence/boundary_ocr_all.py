# 경계 의심 장 정의 실측용 — 캐시 원본 전량 OCR (네트워크 0 · 크레딧 0)
import json, os, sys
sys.path.insert(0, ".claude/skills/bulsaja-detail-page/scripts")
import banner_scan as bs
F = os.path.expanduser("~/python_work/data/naver-ads/runs/2026-09-20/web/banner_97c3578d-eee3-4c56-ab37-0006de292932.json")
d = json.load(open(F))
out = {}
for i, p in enumerate(d["상품"]):
    for s in p["장"]:
        path = bs.원본경로("webapp-banner/cache", "2026-09-20", i, s["순번"])
        key = f'{p["타오바오상품번호"]}:{s["순번"]}'
        if key in out or not os.path.exists(path):
            continue
        try:
            ko = bs.ocr(path, ("ko-KR", "en-US"), True, revision=3)
            zh = bs.ocr(path, ("zh-Hans", "en-US"), False, revision=3)
            out[key] = {"ko": ko, "zh": zh, "n": len(p["장"]), "판정": s["판정"]}
        except Exception as e:
            out[key] = {"err": f"{type(e).__name__}: {e}"}
json.dump(out, open(sys.argv[1], "w"), ensure_ascii=False)
print(len(out))
