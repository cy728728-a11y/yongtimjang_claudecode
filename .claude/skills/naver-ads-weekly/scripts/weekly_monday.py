#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""네이버 광고 주간 — 월요일 07:00 무인 실행 래퍼 (launchd 가 부른다).

    .venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/weekly_monday.py              # 실행
    .venv/bin/python3 ... weekly_monday.py --dry-run                                        # bids/prune 미리보기만

단계 (모두 같은 --run-dir):
    prep → run → enrich → apply --sheet <ID> → bids --commit → prune --commit → 업무판 1행

실패 정책 (2026-10-16 오케스트레이터 확정):
  · prep/run 실패 → 이후 단계 전부 생략 (판정이 없으면 쓸 게 없다)
  · bids --commit / prune --commit 은 **prep·run 성공에만** 의존한다.
    enrich·apply·업무판 실패는 각자 기록만 하고 계속 간다 — 불사자·시트 장애가 입찰 인상을 막지 않는다
  · bids 실패도 prune 을 막지 않는다(서로 다른 쓰기, 둘 다 백업 선행)
되돌리기: `run_ads.py bids --revert --commit --run-dir <회차>` (before_bids 백업)

종료코드: 전 단계 성공 0, 하나라도 실패 1. 업무판 실패는 종료코드에 반영하지 않는다(weekly_result.json 의 board.status).
본체는 run() — 3단계 스케줄러가 같은 함수를 부를 수 있게 main 은 얇게 둔다.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
RUN_ADS = SCRIPT_DIR / "run_ads.py"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import ads_rules  # noqa: E402

# 광고 원장 시트 — workspace.toml sheets.naver_ads 가 있으면 그게 우선이다
DEFAULT_SHEET = "1-oSQepeUGbdmRfSizJHUIjgHu-UYxMtyS504mzDeJKI"
EXPECT_NICK = "부킹"
TIMEOUTS = {"prep": 3600}   # 그 외 1800초
DEFAULT_TIMEOUT = 1800

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _load_eroomlib():
    d = str(SCRIPT_DIR)
    while d and d != os.path.dirname(d):
        lib = os.path.join(d, "lib")
        if os.path.isdir(os.path.join(lib, "eroomlib")):
            if lib not in sys.path:
                sys.path.insert(0, lib)
            return
        d = os.path.dirname(d)


def _cfg(key):
    try:
        _load_eroomlib()
        from eroomlib.config import cfg
        return cfg(key)
    except Exception:
        return None


def _atomic_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def make_runner(log_path):
    """기본 러너 — .venv 파이썬으로 run_ads.py 서브커맨드를 돌리고 종료코드를 돌려준다."""
    def runner(argv):
        name = argv[0]
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as lf:
            lf.write(f"\n===== {datetime.now().isoformat(timespec='seconds')} {' '.join(argv)} =====\n")
            lf.flush()
            try:
                p = subprocess.run([sys.executable, str(RUN_ADS), *argv], stdout=lf, stderr=subprocess.STDOUT,
                                   timeout=TIMEOUTS.get(name, DEFAULT_TIMEOUT))
                return p.returncode
            except subprocess.TimeoutExpired:
                lf.write(f"[타임아웃] {name}\n")
                return 124
            except Exception as e:
                lf.write(f"[실행 실패] {name}: {type(e).__name__}\n")
                return 1
    return runner


# ---------------------------------------------------------------------------
# 메모 집계 — 판정은 ads_rules 에서만 (재구현 금지)
# ---------------------------------------------------------------------------
def build_memo(run_dir, failed, dry_run=False):
    """'입찰+10 N · 썸네일변형 b · 상세꾸미기 c · 정비점검 d(미정비 x) · 꺼진소재 삭제 p'. 못 읽은 숫자는 '?'."""
    run_dir = Path(run_dir)
    b = c = d = x = "?"
    res = _read_json(run_dir / "result.json")
    if isinstance(res, dict):
        try:
            b = c = d = x = 0
            for v in (res.get("accounts") or {}).values():
                rules = (v or {}).get("rules") or {}
                b += len(rules.get("⑦b썸네일변형") or [])
                c += len(ads_rules.final_7c(rules.get("⑦c상세꾸미기후보") or []))
                dd = rules.get("⑦d정비점검후보") or []
                d += len(dd)
                x += sum(1 for r in dd if ads_rules.maintenance_verdict(r) != "정비완료")
        except Exception:
            b = c = d = x = "?"
    n = "?"
    bj = _read_json(run_dir / "bids_commit.json")
    if isinstance(bj, dict):
        try:
            if dry_run:
                n = sum(len((v or {}).get("plans") or []) for v in bj.values())
            else:
                n = sum(int((v or {}).get("committed") or 0) for v in bj.values())
        except Exception:
            n = "?"
    p = "?"
    pj = _read_json(run_dir / "prune_commit.json")
    if isinstance(pj, dict) and isinstance(pj.get("total"), int):
        p = pj["total"]
    bid_label = "입찰+10(예정)" if dry_run else "입찰+10"
    prune_label = "꺼진소재 삭제(예정)" if dry_run else "꺼진소재 삭제"
    memo = (f"{bid_label} {n} · 썸네일변형 {b} · 상세꾸미기 {c} · 정비점검 {d}(미정비 {x}) · "
            f"{prune_label} {p}")
    if failed:
        memo = "실패: " + ", ".join(failed) + " · " + memo
    return memo


# ---------------------------------------------------------------------------
# 본체
# ---------------------------------------------------------------------------
def run(args, runner=None, board_append=None, board_get=None, work_board_id=None, today=None,
        run_dir_path=None, log=print):
    """주간 1회 실행. 종료코드를 돌려준다."""
    today = today or date.today()
    name = args.run_dir or today.isoformat()
    if run_dir_path is None:
        import run_ads
        run_dir_path = run_ads.run_dir_of(name)
    run_dir_path = Path(run_dir_path)
    run_dir_path.mkdir(parents=True, exist_ok=True)
    runner = runner or make_runner(run_dir_path / "weekly.log")
    sheet = args.sheet or _cfg("sheets.naver_ads") or DEFAULT_SHEET
    rd = ["--run-dir", name]
    commit = [] if args.dry_run else ["--commit"]

    steps = {}
    failed = []

    def step(label, argv):
        try:
            rc = runner(argv)
        except Exception as e:
            log(f"[{label}] 실행 예외: {type(e).__name__}")
            rc = 1
        steps[label] = rc
        if rc != 0:
            failed.append(label)
        log(f"[{label}] 종료코드 {rc}")
        return rc == 0

    ok_base = step("prep", ["prep", *rd]) and step("run", ["run", *rd])
    if not ok_base:
        for k in ("run", "enrich", "apply", "bids", "prune"):
            steps.setdefault(k, "skipped")
    else:
        # 읽기·시트 단계 — 실패해도 기록만 하고 계속 간다
        step("enrich", ["enrich", *rd, "--expect-nick", EXPECT_NICK])
        step("apply", ["apply", *rd, "--sheet", sheet])
        # 쓰기 단계 — prep·run 성공에만 의존한다
        step("bids", ["bids", *rd, *commit, "--preview-out", str(run_dir_path / "bids_commit.json")])
        step("prune", ["prune", *rd, *commit, "--preview-out", str(run_dir_path / "prune_commit.json"),
                       "--backup-tag", f"weekly-{today.strftime('%Y%m%d')}"])

    memo = build_memo(run_dir_path, failed, dry_run=args.dry_run)
    out = {"run_dir": name, "dry_run": bool(args.dry_run), "sheet": sheet, "steps": steps,
           "memo": memo, "at": datetime.now().isoformat(timespec="seconds")}

    # 업무판 '오늘' 탭 1행 — 실패해도 본 작업 결과는 남긴다 (sold-lock 패턴)
    try:
        if board_append is None or board_get is None or work_board_id is None:
            _load_eroomlib()
            from eroomlib import gsheets
            from eroomlib.config import cfg
            board_append = board_append or gsheets.append_rows
            board_get = board_get or gsheets.sheets_get
            work_board_id = work_board_id or cfg("sheets.work_board", required=True)
        col = board_get(work_board_id, "'오늘'!A:A") or []
        nums = []
        for r in col:
            try:
                nums.append(int(str(r[0]).strip()))
            except (ValueError, IndexError, TypeError):
                pass
        todo = f"⑦ 광고 주간 {name}"
        if args.dry_run:
            todo = "[dry-run] " + todo
        row = [max(nums, default=0) + 1, today.strftime("%Y-%m-%d"), "✓" if not failed else "",
               todo, "⑦", "Claude", "자동", memo, ""]
        board_append(work_board_id, "오늘", [row])
        out["board"] = {"status": "ok"}
    except Exception as e:
        out["board"] = {"status": "failed", "error": f"{type(e).__name__}: {str(e)[:200]}"}
        log("[경고] 업무판 기록 실패 (weekly_result.json 은 남김)")

    try:
        _atomic_json(run_dir_path / "weekly_result.json", out)
    except Exception as e:
        log(f"[경고] weekly_result.json 쓰기 실패: {type(e).__name__}")
    log(f"[완료] {memo}")
    return 0 if not failed else 1


def build_parser():
    ap = argparse.ArgumentParser(description="네이버 광고 주간 — 월요일 무인 실행 래퍼")
    ap.add_argument("--run-dir", default=None, help="회차 이름(기본: 오늘 날짜)")
    ap.add_argument("--sheet", default=None, help="광고 원장 시트 ID(기본: sheets.naver_ads → 상수)")
    ap.add_argument("--dry-run", action="store_true", help="bids/prune 을 --commit 없이 돌린다(첫 실행 전 점검)")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except Exception as e:
        print(f"[오류] 예기치 못한 실패: {type(e).__name__}", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
