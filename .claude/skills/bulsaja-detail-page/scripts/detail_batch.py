# -*- coding: utf-8 -*-
"""불사자 AI 상세페이지 배치 생성 (기본 10장, 일반화질).

⚠️ 핵심 (2026-07-23 실측): 10장짜리 상세페이지가 되려면
   imageUrls(상품 이미지 목록, 최대 10장) + sectionCount(장수) 를 **동시에** 보내야 한다.
   - productId만 / sectionCount만 / imageUrls만 → 전부 1장짜리로 접수됨.
   - 접수 확정 응답의 '예상장수'로 즉시 검증하고, 불일치 시 전량 중단.

기작업 스킵 (2026-07-23): 접수 전 workdata의 uploadDetailContents에서
   aiImageGenerated / aiImageOutputCount / aiImageGeneratedAt 을 확인해
   이미 이번 목표 장수 이상으로 생성·반영된 상품은 접수하지 않는다 (크레딧 0).
   - 서버 기록이 진실의 원천 — 별도 로컬 대장 불필요 (썸네일과 다른 점).
   - 기존 장수 < 목표 장수(예: 1장 사고분)는 스킵하지 않고 재작업 대상.
   - 이미지 수집용 workdata 조회를 그대로 재사용하므로 추가 API 호출 없음.
   - 강제 재생성은 --force (용팀장님 명시 요청 시만).

상품별 흐름:
  workdata 조회 → 기작업 스킵 판정 → 이미지 수집(썸네일 + 옵션 이미지, 중복 제거,
  최대 --pages 장) → generate(confirm=False→토큰→confirm=True,
  imageUrls+sectionCount) 접수 → 응답 '예상장수' 검증 → 전체 폴링
  → 완료 시 불사자가 자동 반영.

- 체크포인트: <run-dir>/detail_status.json {pid: {taskId, status, pages, ...}}
- 재개: taskId 있는 상품은 접수 스킵, 미완료만 폴링 (--poll-only)
- 작업 중복(해당 상품에 AI 작업 진행 중): 대기열로 미뤘다가 말미에 재시도
- 크레딧: 일반화질 장당 5 / 고화질 장당 10 (성공분만 과금)

사용:
  python detail_batch.py --run-dir <RUN> [--pages 10] [--quality standard]
        [--limit N] [--submit-only] [--poll-only] [--retry-failed] [--force]
  용쌤 계정: python run_yong.py <python절대경로> detail_batch.py ...
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

# 불사자 MCP 클라이언트는 카테고리 교정 스킬의 것을 재사용
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
    try:
        tmp = str(path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except Exception as e:
        print(f"[경고] 체크포인트 저장 실패: {e}")


def sanitize(obj, depth=0):
    """응답 구조 확인용 (값 축약, 토큰류 노출 방지)."""
    if depth > 3:
        return "..."
    if isinstance(obj, dict):
        return {k: sanitize(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(v, depth + 1) for v in obj[:3]] + (["..."] if len(obj) > 3 else [])
    s = str(obj)
    return s[:60] + ("..." if len(s) > 60 else "")


def extract_task_id(r):
    """접수 응답에서 작업번호 추출 (형태 유연)."""
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


def is_duplicate_error(e):
    """해당 상품에 AI 작업이 이미 진행 중이라 접수가 막힌 경우."""
    s = str(e)
    return ("작업 중복" in s) or ("이미 AI 이미지 작업이 진행" in s)


SKIP_STATUS = "완료(기작업)"  # is_done 매칭되어 재접수·폴링 대상에서 빠짐


class AlreadyDone(Exception):
    """이미 목표 장수 이상으로 AI 상세페이지가 생성·반영된 상품."""

    def __init__(self, pages, at):
        self.pages = pages
        self.at = at or ""
        super().__init__(f"기작업 {pages}장 ({self.at[:10]})")


def get_workdata(mcp, pid):
    wd = mcp.call_tool("bulsaja_product_workdata",
                       {"productId": pid, "mode": "summary"})
    return wd.get("data") or {}


def existing_ai_detail(data):
    """이미 생성·반영된 AI 상세페이지 정보. 없으면 None.

    판별은 aiImageGenerated 플래그 기준 — '상세페이지있음'은 원본 번역
    이미지만 있어도 true 라서 기준이 못 됨 (2026-07-23 실측).
    """
    dc = data.get("uploadDetailContents") or {}
    if not dc.get("aiImageGenerated"):
        return None
    try:
        pages = int(dc.get("aiImageOutputCount") or 0)
    except (TypeError, ValueError):
        pages = 0
    return {"pages": pages, "at": dc.get("aiImageGeneratedAt") or ""}


def collect_images(data, cap):
    """workdata에서 상세페이지 입력 이미지 수집: 썸네일 + 옵션 이미지 (중복 제거, cap장)."""
    urls = []

    def add(u):
        if isinstance(u, str) and u.startswith("http") and u not in urls:
            urls.append(u)

    for u in (data.get("uploadThumbnails") or []):
        add(u)
    # 옵션(색상 등) 이미지 — 제외 처리된 옵션은 건너뜀
    try:
        props = data.get("uploadSkuProps") or {}
        main = props.get("mainOption") or {}
        for v in (main.get("values") or []):
            if not v.get("exclude"):
                add(v.get("imageUrl"))
    except Exception:
        pass
    return urls[:cap]


def submit_one(mcp, pid, pages, quality, force=False):
    """이미지 수집 → imageUrls+sectionCount 동시 지정 2단계 접수 → (작업번호, 장수) 반환.

    기작업(기존 장수 >= 이번 목표 장수)이면 AlreadyDone — 접수·크레딧 없음.
    접수 확정 응답의 '예상장수'가 요청 장수와 다르면 RuntimeError("장수 불일치").
    """
    data = get_workdata(mcp, pid)
    imgs = collect_images(data, pages)
    if not imgs:
        raise RuntimeError("입력 이미지 없음 (썸네일/옵션 이미지 0장)")
    sc = max(2, min(pages, len(imgs)))  # 장수 하한 2 (도구 제약)
    if not force:
        prev = existing_ai_detail(data)
        if prev and prev["pages"] >= sc:
            raise AlreadyDone(prev["pages"], prev["at"])
    base = {"productId": pid, "imageUrls": imgs, "sectionCount": sc,
            "quality": quality, "confirm": False}
    pre = mcp.call_tool("bulsaja_detail_page_generate", base)
    token = pre.get("confirmationToken")
    if not token:
        raise RuntimeError(f"확인토큰 없음: {str(sanitize(pre))[:150]}")
    fin = mcp.call_tool("bulsaja_detail_page_generate",
                        {**base, "confirm": True, "confirmationToken": token})
    tid = extract_task_id(fin)
    if not tid:
        raise RuntimeError(f"작업번호 없음: {str(sanitize(fin))[:200]}")
    # ⚠️ 즉시 검증: 서버가 접수한 예상 장수 확인 (2026-07-23 1장 사고 재발 방지)
    exp = fin.get("예상장수")
    if isinstance(exp, int) and exp != sc:
        raise RuntimeError(
            f"장수 불일치: 요청 {sc}장인데 서버 접수는 {exp}장 (작업 {tid}). "
            f"전량 접수 중단 — 접수 파라미터 확인 필요.")
    return tid, sc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--pages", type=int, default=10,
                    help="상세페이지 장수 (기본 10, 허용 2~10)")
    ap.add_argument("--quality", default="standard",
                    choices=["standard", "high"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--submit-only", action="store_true")
    ap.add_argument("--poll-only", action="store_true")
    ap.add_argument("--retry-failed", action="store_true",
                    help="실패/접수실패 건을 다시 접수")
    ap.add_argument("--force", action="store_true",
                    help="기작업 스킵 무시하고 강제 재생성 (명시 요청 시만)")
    ap.add_argument("--poll-interval", type=int, default=45)
    ap.add_argument("--max-poll-min", type=int, default=240)
    ap.add_argument("--sleep", type=float, default=1.0)
    ap.add_argument("--dup-wait", type=int, default=60,
                    help="작업 중복 시 재시도 대기(초)")
    ap.add_argument("--dup-rounds", type=int, default=8,
                    help="작업 중복 재시도 최대 회수")
    args = ap.parse_args()

    if not (2 <= args.pages <= 10):
        print("⛔ --pages 는 2~10 범위여야 함 (기본 10)")
        sys.exit(1)

    run = Path(args.run_dir)
    status_path = run / "detail_status.json"
    raw = load_json(run / "products.json", [])
    pids = [p if isinstance(p, str) else p.get("productId")
            for p in raw]
    pids = [p for p in pids if p]
    status = load_json(status_path, {})
    per_credit = 5 if args.quality == "standard" else 10

    mcp = BulsajaMCP()
    mcp.open()
    try:
        # 1) 접수 (작업번호 없는 상품만; --retry-failed 면 실패 건도 재접수)
        if not args.poll_only:
            def need_submit(pid):
                v = status.get(pid, {})
                if args.force and v.get("status") == SKIP_STATUS:
                    return True
                if args.retry_failed and (is_failed(v.get("status", ""))
                                          or v.get("status") == "접수실패"):
                    return True
                return not v.get("taskId") and not is_done(v.get("status", ""))

            todo = [pid for pid in pids if need_submit(pid)]
            if args.limit:
                todo = todo[:args.limit]
            est = len(todo) * args.pages * per_credit
            print(f"접수 대상 {len(todo)}건 × 최대 {args.pages}장 "
                  f"× {per_credit}크레딧 = 예상 최대 {est}크레딧")

            dup_queue = []

            def try_submit(pid, tag):
                try:
                    tid, sc = submit_one(mcp, pid, args.pages, args.quality,
                                         force=args.force)
                    status[pid] = {"taskId": tid, "status": "접수", "pages": sc}
                    print(f"{tag} {pid[-8:]} 접수 OK ({tid}, {sc}장)",
                          flush=True)
                    return "ok"
                except AlreadyDone as e:
                    status[pid] = {"status": SKIP_STATUS, "pages": e.pages,
                                   "generated_at": e.at}
                    print(f"{tag} {pid[-8:]} 기작업 스킵 "
                          f"({e.pages}장, {e.at[:10]})", flush=True)
                    return "skip"
                except RuntimeError as e:
                    if "장수 불일치" in str(e):
                        print("⛔", str(e))
                        save_json(status_path, status)
                        sys.exit(2)
                    if is_duplicate_error(e):
                        print(f"{tag} {pid[-8:]} 작업 중복 — 말미 재시도",
                              flush=True)
                        return "dup"
                    status[pid] = {"status": "접수실패", "error": str(e)[:200]}
                    print(f"{tag} {pid[-8:]} 접수 FAIL {str(e)[:100]}",
                          flush=True)
                    return "fail"
                except Exception as e:
                    if is_duplicate_error(e):
                        print(f"{tag} {pid[-8:]} 작업 중복 — 말미 재시도",
                              flush=True)
                        return "dup"
                    status[pid] = {"status": "접수실패", "error": str(e)[:200]}
                    print(f"{tag} {pid[-8:]} 접수 FAIL {str(e)[:100]}",
                          flush=True)
                    return "fail"

            for i, pid in enumerate(todo, 1):
                r = try_submit(pid, f"[{i}/{len(todo)}]")
                if r == "dup":
                    dup_queue.append(pid)
                save_json(status_path, status)
                time.sleep(args.sleep)

            # 작업 중복 대기열: 기존 작업이 끝날 때까지 간격을 두고 재시도
            for rnd in range(args.dup_rounds):
                if not dup_queue:
                    break
                print(f"중복 대기열 {len(dup_queue)}건 — {args.dup_wait}초 후 "
                      f"재시도 ({rnd + 1}/{args.dup_rounds})", flush=True)
                time.sleep(args.dup_wait)
                remain = []
                for pid in dup_queue:
                    r = try_submit(pid, "[중복재시도]")
                    if r == "dup":
                        remain.append(pid)
                    save_json(status_path, status)
                    time.sleep(args.sleep)
                dup_queue = remain
            for pid in dup_queue:
                status[pid] = {"status": "접수실패",
                               "error": "작업 중복 지속 (기존 작업 미종료)"}
            save_json(status_path, status)

        # 2) 폴링 (완료/실패 아닌 작업번호 전부)
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
                        status[pid]["status"] = extract_status(st)
                        n = len(st.get("생성이미지") or [])
                        if n:
                            status[pid]["images"] = n
                    except Exception as e:
                        status[pid]["poll_error"] = str(e)[:120]
                    time.sleep(0.4)
                save_json(status_path, status)
                done = sum(1 for v in status.values()
                           if is_done(v.get("status", "")))
                fail = sum(1 for v in status.values()
                           if is_failed(v.get("status", "")))
                print(f"  완료 {done} / 실패 {fail} / 전체 {len(status)}",
                      flush=True)
                if done + fail >= sum(1 for v in status.values()
                                      if v.get("taskId")):
                    break
                time.sleep(args.poll_interval)

        done = sum(1 for v in status.values() if is_done(v.get("status", "")))
        fail = sum(1 for v in status.values() if is_failed(v.get("status", "")))
        skip = sum(1 for v in status.values()
                   if v.get("status") == SKIP_STATUS)
        print(f"###DETAIL### 완료 {done} (신규 {done - skip} + 기작업스킵 {skip})"
              f" / 실패 {fail} / 전체 {len(status)}")
    finally:
        mcp.close()


if __name__ == "__main__":
    main()
