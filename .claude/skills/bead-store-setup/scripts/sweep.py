# 최종 점검: 54개 마켓 전부의 비즈 상태를 읽고, 스토어에 올라갔는데 세팅이 덜 된 상품은 그 자리에서 맞춘다.
# 사용: sweep.py   → data/sweep.json (마켓별 상태)
import sys, os, json, subprocess, time
from common import *
PY = sys.executable; HERE = os.path.dirname(os.path.abspath(__file__))
mks = sorted(json.load(open(os.path.expanduser("~/.eroom/naver-commerce-stores.json"))), key=lambda k: tuple(map(int, k.split("-"))))
mks = [m for m in mks if m != "12-1"]
OK = "('SALE', 'SUSPENSION', 100, 100)"
out = {}
def st(mk):
    r = subprocess.run([PY, os.path.join(HERE, "status.py"), mk], capture_output=True, text=True, cwd=HERE, timeout=1200)
    return json.loads(r.stdout[r.stdout.index("{"):])
for mk in mks:
    try:
        s = st(mk)
        good = s["스토어_상태(판매,전시,판매가,실판매가)"].get(OK, 0)
        if s["스토어_비즈"] > good:
            subprocess.run([PY, os.path.join(HERE, "store_fix.py"), mk, "all"], capture_output=True, text=True, cwd=HERE, timeout=3600)
            s = st(mk); good = s["스토어_상태(판매,전시,판매가,실판매가)"].get(OK, 0)
        out[mk] = {"한도": s["등록한도"], "현재등록": s["현재등록"], "스토어비즈": s["스토어_비즈"], "정상": good, "잠금": s["불사자_잠금"], "불사자복사본": s["불사자_비즈복사본"]}
    except Exception as e:
        out[mk] = {"오류": repr(e)[:120]}
    json.dump(out, open(os.path.join(DATA_DIR, "sweep.json"), "w"), ensure_ascii=False, indent=1)
    print(mk, json.dumps(out[mk], ensure_ascii=False), flush=True)
print("점검 끝", flush=True)
