# -*- coding: utf-8 -*-
"""용쌤1-1 100건 AI 상세페이지 생성 (불사자, 일반화질).

상품별: generate(confirm=False→토큰→confirm=True) 접수 → taskId 기록
→ 전체 폴링(detail_page_status) → 완료 시 자동 반영(불사자가 자동 적용).

- 체크포인트: detail_status.json {pid: {taskId, status, ...}}
- 재개: taskId 있는 상품은 접수 스킵, 미완료만 폴링
- 크레딧: 일반화질 이미지 1장당 5크레딧 (성공분만 과금)

사용: python run_yong.py python stage3_detail.py --run-dir <RUN>
      [--limit N] [--submit-only] [--poll-only] [--probe <pid>]
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SKILL_SCRIPTS = r"C:\Users\workspace\.claude\skills\bulsaja-category-fix\scripts"
sys.path.insert(0, SKILL_SCRIPTS)
from bulsaja_mcp import BulsajaMCP  # noqa: E402


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, obj):
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def sanitize(obj, depth=0):
    """응답 구조 확인용 (값 축약)."""
    if depth > 3:
        return "..."
    if isinstance(obj, dict):
        return {k: sanitize(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(v, depth + 1) for v in obj[:3]] + (["..."] if len(obj) > 3 else [])
    s = str(obj)
    return s[:60] + ("..." if len(s) > 60 else "")


def extract_task_id(r):
    """접수 응답에서 taskId 추출 (형태 유연)."""
    for k in ("taskId", "task_id", "작업번호", "작업id", "id"):
        v = r.get(k)
        if v:
            return str(v)
    for k in ("task", "작업", "data"):
        v = r.get(k)
        if isinstance(v, dict):
            t = extract_task_id(v)
            if t:
                return t
    return None


def extract_status(r):
    """상태 응답에서 진행 상태 문자열 추출."""
    for k in ("status", "상태", "진행상태", "state"):
        v = r.get(k)
        if isinstance(v, str) and v:
            return v
    return json.dumps(sanitize(r), ensure_ascii=False)[:100]


def is_done(s):
    return any(w in s for w in ("완료", "성공", "complete", "done", "success"))


def is_failed(s):
    return any(w in s for w in ("실패", "오류", "취소", "fail", "error", "cancel"))


def submit_one(mcp, pid, verbose=False):
    """2단계 확인식 접수 → taskId 반환."""
    pre = mcp.call_tool("bulsaja_detail_page_generate", {
        "productId": pid, "quality": "standard", "confirm": False})
    token = pre.get("confirmationToken")
    if not token:
        raise RuntimeError(f"확인토큰 없음: {str(sanitize(pre))[:150]}")
    fin = mcp.call_tool("bulsaja_detail_page_generate", {
        "productId": pid, "quality": "standard",
        "confirm": True, "confirmationToken": token})
    if verbose:
        print("[접수 응답 구조]")
        print(json.dumps(sanitize(fin), ensure_ascii=False, indent=1))
    tid = extract_task_id(fin)
    if not tid:
        raise RuntimeError(f"taskId 없음: {str(sanitize(fin))[:200]}")
    return tid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--submit-only", action="store_true")
    ap.add_argument("--poll-only", action="store_true")
    ap.add_argument("--probe", help="상품 1건 접수+폴링 응답 구조 확인")
    ap.add_argument("--poll-interval", type=int, default=45)
    ap.add_argument("--max-poll-min", type=int, default=240)
    ap.add_argument("--sleep", type=float, default=1.0)
    args = ap.parse_args()

    run = Path(args.run_dir)
    status_path = run / "detail_status.json"
    products = load_json(run / "products.json", [])
    status = load_json(status_path, {})

    mcp = BulsajaMCP()
    mcp.open()
    try:
        if args.probe:
            tid = submit_one(mcp, args.probe, verbose=True)
            print(f"taskId: {tid}")
            status[args.probe] = {"taskId": tid, "status": "접수"}
            save_json(status_path, status)
            time.sleep(10)
            st = mcp.call_tool("bulsaja_detail_page_status",
                               {"taskId": tid, "target": "detail"})
            print("[상태 응답 구조]")
            print(json.dumps(sanitize(st), ensure_ascii=False, indent=1))
            return

        # 1) 접수 (taskId 없는 상품만)
        if not args.poll_only:
            todo = [p for p in products
                    if not status.get(p["productId"], {}).get("taskId")
                    and not is_done(status.get(p["productId"], {}).get("status", ""))]
            if args.limit:
                todo = todo[:args.limit]
            print(f"접수 대상 {len(todo)}건")
            for i, p in enumerate(todo, 1):
                pid = p["productId"]
                try:
                    tid = submit_one(mcp, pid)
                    status[pid] = {"taskId": tid, "status": "접수"}
                    print(f"[{i}/{len(todo)}] {pid[-8:]} 접수 OK ({tid})", flush=True)
                except Exception as e:
                    status[pid] = {"status": "접수실패",
                                   "error": str(e)[:200]}
                    print(f"[{i}/{len(todo)}] {pid[-8:]} 접수 FAIL {str(e)[:100]}",
                          flush=True)
                save_json(status_path, status)
                time.sleep(args.sleep)

        # 2) 폴링 (완료/실패 아닌 taskId 전부)
        if not args.submit_only:
            deadline = time.time() + args.max_poll_min * 60
            while time.time() < deadline:
                pending = [(pid, v["taskId"]) for pid, v in status.items()
                           if v.get("taskId") and not is_done(v.get("status", ""))
                           and not is_failed(v.get("status", ""))]
                if not pending:
                    break
                print(f"폴링: 미완료 {len(pending)}건", flush=True)
                for pid, tid in pending:
                    try:
                        st = mcp.call_tool("bulsaja_detail_page_status",
                                           {"taskId": tid, "target": "detail"})
                        s = extract_status(st)
                        status[pid]["status"] = s
                    except Exception as e:
                        status[pid]["poll_error"] = str(e)[:120]
                    time.sleep(0.4)
                save_json(status_path, status)
                done = sum(1 for v in status.values() if is_done(v.get("status", "")))
                fail = sum(1 for v in status.values()
                           if is_failed(v.get("status", "")))
                print(f"  완료 {done} / 실패 {fail} / 전체 {len(status)}", flush=True)
                if not [1 for v in status.values()
                        if v.get("taskId") and not is_done(v.get("status", ""))
                        and not is_failed(v.get("status", ""))]:
                    break
                time.sleep(args.poll_interval)

        done = sum(1 for v in status.values() if is_done(v.get("status", "")))
        fail = sum(1 for v in status.values() if is_failed(v.get("status", "")))
        print(f"###DETAIL### 완료 {done} / 실패 {fail} / 전체 {len(status)}")
    finally:
        mcp.close()


if __name__ == "__main__":
    main()
