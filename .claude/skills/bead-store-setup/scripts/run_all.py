# 여러 마켓을 한 번에: 마켓마다 채우기·잠금 → (필요하면) 빈자리 확보 → 업로드(정체 감시·재접수) → 스토어 세팅 → 최종 확인.
# 사용: run_all.py <동시 마켓 수> [마켓 ...]   (마켓 생략 시 용쌤N-M 전체, 12-1 제외)
# 결과: data/run_all.jsonl (마켓별 한 줄), 로그: data/logs/<마켓>.log. 끝난 마켓(완료)은 다시 돌려도 건너뜀.
import sys, os, json, time, subprocess, re, threading
from concurrent.futures import ThreadPoolExecutor
from common import DATA_DIR, bulsaja, originals, commerce, store_products, store_count, norm

BLOCK = threading.Lock()   # 불사자 요청은 한 번에 한 마켓만(동시에 하면 429). 업로드 기다리는 동안은 스토어 쪽만 본다.
_m = bulsaja(); _, NAMES = originals(_m); _m.close()

HERE = os.path.dirname(os.path.abspath(__file__)); PY = sys.executable
N = int(sys.argv[1])
SKIP = {"12-1"}
ALL = sorted(json.load(open(os.path.expanduser("~/.eroom/naver-commerce-stores.json"))), key=lambda k: tuple(map(int, k.split("-"))))
MARKETS = sys.argv[2:] or [m for m in ALL if m not in SKIP]
OUT = os.path.join(DATA_DIR, "run_all.jsonl"); LOGD = os.path.join(DATA_DIR, "logs"); os.makedirs(LOGD, exist_ok=True)
done = set()
if os.path.exists(OUT):
    for l in open(OUT):
        r = json.loads(l)
        if r.get("결과") == "완료": done.add(r["마켓"])

POLL, STALL_POLLS, MAX_RESUBMIT, MAX_WAIT = 60, 6, 3, 90 * 60   # 1분마다 확인, 6분 정체면 재접수, 재접수 3번까지, 업로드 최대 90분


def store_beads(mk):
    """스토어에 올라간 비즈 수(커머스API만 사용, 불사자 안 부름)"""
    for t in range(5):
        try:
            api = commerce(mk)
            return sum(1 for c in store_products(api, mk) for ch in (c.get("channelProducts") or [])[:1] if norm(ch.get("name")) in NAMES)
        except Exception:
            time.sleep(20 * (t + 1))
    return -1


def run(mk, script, *args, timeout=5400):
    with BLOCK:
        return _run(mk, script, *args, timeout=timeout)


def _run(mk, script, *args, timeout=5400):
    r = subprocess.run([PY, os.path.join(HERE, script), mk, *args], capture_output=True, text=True, timeout=timeout, cwd=HERE)
    out = r.stdout + r.stderr
    with open(os.path.join(LOGD, f"{mk}.log"), "a") as f:
        f.write(f"\n=== {time.strftime('%F %T')} {script} {' '.join(args)}\n{out}")
    return out


def status(mk):
    out = run(mk, "status.py")
    try:
        return json.loads(out[out.index("{"):])
    except Exception:
        raise RuntimeError("상태 조회 실패: " + out[-300:])


def finished(s):
    return s["스토어_비즈"] == 300 and s["불사자_잠금"] == 300 and \
        s["스토어_상태(판매,전시,판매가,실판매가)"] == {"('SALE', 'SUSPENSION', 100, 100)": 300}


def work(mk):
    rec = {"마켓": mk}
    try:
        s = status(mk); rec.update(한도=s["등록한도"], 시작등록=s["현재등록"], 시작비즈=s["스토어_비즈"])
        if finished(s):
            rec["결과"] = "완료"; rec["메모"] = "이미 끝나 있음"; return rec
        run(mk, "fill_and_lock.py")
        s = status(mk)
        remain = 300 - s["스토어_비즈"]
        rec["삭제"] = 0
        if s["스토어_비즈"] == 0 and s["빈자리"] < 350:
            out = run(mk, "free_slots.py", "run")
            m = re.search(r"지울 개수 (\d+)", out)
            if "삭제 실행" not in out:
                rec["결과"] = "보류"; rec["메모"] = "빈자리 확보 실패: " + out.strip().splitlines()[-1][:200]; return rec
            rec["삭제"] = int(m.group(1)) if m else None
            for _ in range(30):   # 스스 삭제 반영까지 최대 약 60분(실측: 300개 넘게 지우면 1시간 가까이 걸림)
                time.sleep(120)
                s = status(mk)
                if s["빈자리"] >= 300: break
            if s["빈자리"] < 300:
                rec["결과"] = "보류"; rec["메모"] = f"삭제 뒤 빈자리 {s['빈자리']} — 스스 삭제 반영 지연/실패"; return rec
        elif remain > 0 and s["빈자리"] < remain:
            rec["결과"] = "보류"; rec["메모"] = f"일부만 올라간 마켓인데 빈자리 {s['빈자리']} < 남은 {remain} — 사람 확인"; return rec
        # 업로드 + 정체 감시
        if remain > 0:
            base_cnt, base_beads = s["현재등록"], s["스토어_비즈"]
            run(mk, "upload.py")
            t0, last, stall, resub = time.time(), -1, 0, 0
            while time.time() - t0 < MAX_WAIT:
                time.sleep(POLL)
                # 전체 상품을 훑지 않고 등록 수 증가분으로 센다(호출 1번)
                try: n = base_beads + store_count(commerce(mk), mk) - base_cnt
                except Exception: continue
                if n >= 300: break
                if n == last: stall += 1
                else: stall, last = 0, n
                if stall >= STALL_POLLS:
                    if resub >= MAX_RESUBMIT: break
                    run(mk, "upload.py"); resub += 1; stall = 0
            rec["재접수"] = resub
        out = _run(mk, "store_fix.py", "all")   # 거의 스토어 쪽 작업이라 불사자 순번을 안 기다린다(스토어마다 따로 돌 수 있음)
        rec["세팅"] = (re.search(r"완료 \d+ · 이미 맞음 \d+ · 실패 \d+", out) or [out[-200:]])[0]
        run(mk, "fill_and_lock.py")   # 늦게 들어온 것까지 잠금 재확인
        s = status(mk)
        rec.update(최종등록=s["현재등록"], 스토어비즈=s["스토어_비즈"], 잠금=s["불사자_잠금"], 상태=s["스토어_상태(판매,전시,판매가,실판매가)"])
        rec["제외"] = 300 - s["스토어_비즈"]
        rec["결과"] = "완료" if finished(s) else "일부"
    except Exception as e:
        rec["결과"] = "오류"; rec["메모"] = repr(e)[:300]
    return rec


def job(mk):
    rec = work(mk); rec["시각"] = time.strftime("%F %T")
    with open(OUT, "a") as f: f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(json.dumps(rec, ensure_ascii=False), flush=True)


todo = [m for m in MARKETS if m not in done]
print("대상", len(todo), todo, flush=True)
with ThreadPoolExecutor(N) as ex:
    list(ex.map(job, todo))
print("전체 끝", flush=True)
