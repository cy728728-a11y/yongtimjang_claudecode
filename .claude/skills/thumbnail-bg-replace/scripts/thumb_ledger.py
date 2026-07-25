# -*- coding: utf-8 -*-
"""썸네일 배경교체 전역 완료 대장 (thumbnail-done.json).

배치(run)를 넘어 "이 상품은 이미 썸네일 스킬로 작업했다"를 기억하는 장부.
새 작업 명령 시 대상 상품을 이 대장과 대조해 이미 완료된 상품은 skip 한다.

- 위치: 20-operations/21-bulsaja-category-runs/thumbnail-done.json
- 구조: {"accounts": {"<계정>": {"<productId>": {status, date, run, url?, name?, reason?}}}}
- 계정 키: "bulsaja"(용팀장 계정) / "bulsaja-yongssaem"(용쌤 계정)
- status: "ok"(교체 반영) | "kept-original"(생성 후 원본 유지 결정) — 둘 다 완료로 취급

CLI:
  python thumb_ledger.py stats
  python thumb_ledger.py check --account bulsaja-yongssaem <productId> [...]
  python thumb_ledger.py mark  --account <계정> --run <run명> [--status ok] <productId> [...]
  python thumb_ledger.py seed  --run-dir <RUN폴더> --account <계정> --date YYYY-MM-DD
    (RUN폴더의 upload_status.json + products.json 을 대장으로 이관.
     ok → ok, skip → kept-original(사유 유지), fail → 기록 안 함)
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

# 워크스페이스 루트 = .claude/skills/thumbnail-bg-replace/scripts 의 4단계 위
# (parents[0]=scripts, [1]=스킬, [2]=skills, [3]=.claude, [4]=워크스페이스)
_WORKSPACE = Path(__file__).resolve().parents[4]
DEFAULT_LEDGER = _WORKSPACE / "20-operations" / "21-bulsaja-category-runs" / "thumbnail-done.json"

DONE_STATUSES = ("ok", "kept-original")


def ledger_path():
    """대장 경로 (환경변수 BULSAJA_THUMB_LEDGER 로 재지정 가능)."""
    return Path(os.getenv("BULSAJA_THUMB_LEDGER") or DEFAULT_LEDGER)


def resolve_account(cli_value=None, require=False):
    """계정 결정: CLI 인자 > BULSAJA_ACCOUNT 환경변수 > 'bulsaja'(용팀장 기본).

    require=True: 명시(인자/환경변수)가 없으면 RuntimeError.
    대장 대조·기록처럼 계정이 틀리면 조용히 사고 나는 곳은 require=True 로 호출
    (예: 용쌤 상품을 기본값 bulsaja로 대조 → skip 0건 → 전량 재생성 과금).
    """
    acct = cli_value or os.getenv("BULSAJA_ACCOUNT")
    if acct:
        return acct
    if require:
        raise RuntimeError(
            "계정 미지정 — --account bulsaja|bulsaja-yongssaem 을 주거나 "
            "BULSAJA_ACCOUNT 환경변수를 설정 (용쌤 작업은 run_yong.py 경유 시 자동 주입)")
    return "bulsaja"


def load_ledger(path=None):
    """대장 로드 (없으면 빈 골격 반환)."""
    p = Path(path) if path else ledger_path()
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data.get("accounts"), dict):
            data["accounts"] = {}
        return data
    except FileNotFoundError:
        return {
            "_doc": ("불사자 썸네일 배경교체 완료 대장. "
                     "accounts.<계정>.<productId> = {status, date, run, url?, name?, reason?}. "
                     "status ok|kept-original 은 완료로 취급 → 새 작업 시 skip."),
            "accounts": {},
        }
    except Exception as e:
        # 대장이 깨졌으면 조용히 새로 만들지 않는다 — 기록 유실 방지
        raise RuntimeError(f"대장 파일 파싱 실패({p}): {e}")


def save_ledger(data, path=None):
    """원자적 저장 (tmp → replace)."""
    p = Path(path) if path else ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(p) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def is_done(ledger, account, product_id):
    """이미 썸네일 작업이 끝난 상품인지."""
    entry = (ledger.get("accounts", {}).get(account) or {}).get(product_id)
    return bool(entry) and entry.get("status") in DONE_STATUSES


def done_set(ledger, account):
    """해당 계정의 완료 productId 집합."""
    acc = ledger.get("accounts", {}).get(account) or {}
    return {pid for pid, e in acc.items() if e.get("status") in DONE_STATUSES}


def mark_done(account, product_id, status="ok", run=None, url=None,
              name=None, reason=None, date=None, path=None):
    """완료 1건 기록 (즉시 저장). 반환: 기록된 entry."""
    ledger = load_ledger(path)
    acc = ledger["accounts"].setdefault(account, {})
    entry = {
        "status": status,
        "date": date or time.strftime("%Y-%m-%d"),
    }
    if run:
        entry["run"] = run
    if url:
        entry["url"] = url
    if name:
        entry["name"] = name
    if reason:
        entry["reason"] = reason
    acc[product_id] = entry
    save_ledger(ledger, path)
    return entry


def _cmd_stats(args):
    ledger = load_ledger()
    accounts = ledger.get("accounts", {})
    if not accounts:
        print("대장 비어 있음:", ledger_path())
        return
    print(f"대장: {ledger_path()}")
    for acct, items in accounts.items():
        ok = sum(1 for e in items.values() if e.get("status") == "ok")
        kept = sum(1 for e in items.values() if e.get("status") == "kept-original")
        print(f"  {acct}: 완료 {ok + kept} (교체 {ok} / 원본유지 {kept})")


def _cmd_check(args):
    ledger = load_ledger()
    acct = resolve_account(args.account)
    n_done = 0
    for pid in args.product_ids:
        if is_done(ledger, acct, pid):
            e = ledger["accounts"][acct][pid]
            print(f"DONE {pid} ({e.get('status')}, {e.get('date')}, run={e.get('run', '-')})")
            n_done += 1
        else:
            print(f"TODO {pid}")
    print(f"-- {acct}: 완료 {n_done} / 미완료 {len(args.product_ids) - n_done}")


def _cmd_mark(args):
    # 기록은 계정이 틀리면 사고 → 명시 필수
    acct = resolve_account(args.account, require=True)
    for pid in args.product_ids:
        mark_done(acct, pid, status=args.status, run=args.run, reason=args.reason)
        print(f"기록: [{acct}] {pid} → {args.status}")


def _cmd_seed(args):
    """기존 run 폴더(upload_status.json + products.json)를 대장으로 이관."""
    run_dir = Path(args.run_dir)
    run_name = run_dir.name
    acct = resolve_account(args.account)
    try:
        with open(run_dir / "upload_status.json", encoding="utf-8") as f:
            upload = json.load(f)
    except Exception as e:
        print(f"[오류] upload_status.json 읽기 실패: {e}")
        sys.exit(1)
    names = {}
    try:
        with open(run_dir / "products.json", encoding="utf-8") as f:
            for p in json.load(f):
                names[p.get("productId")] = p.get("상품명")
    except Exception:
        pass  # 상품명은 부가 정보 — 없어도 이관 진행

    ledger = load_ledger()
    acc = ledger["accounts"].setdefault(acct, {})
    added = updated = skipped = 0
    for pid, rec in upload.items():
        st = rec.get("status")
        if st == "ok":
            entry = {"status": "ok", "date": args.date, "run": run_name,
                     "url": rec.get("url")}
        elif st == "skip":
            entry = {"status": "kept-original", "date": args.date, "run": run_name}
            if rec.get("reason"):
                entry["reason"] = rec["reason"]
        else:
            skipped += 1  # fail 등은 미완료 → 기록 안 함
            continue
        if names.get(pid):
            entry["name"] = names[pid]
        if pid in acc:
            updated += 1
        else:
            added += 1
        acc[pid] = entry
    save_ledger(ledger)
    print(f"[seed] {run_name} → [{acct}] 신규 {added} / 갱신 {updated} / 미이관(fail 등) {skipped}")
    print(f"대장: {ledger_path()}")


def main():
    ap = argparse.ArgumentParser(description="썸네일 완료 대장 관리")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("stats", help="계정별 완료 건수")

    p = sub.add_parser("check", help="productId 완료 여부 확인")
    p.add_argument("--account", help="계정 (기본: BULSAJA_ACCOUNT 또는 bulsaja)")
    p.add_argument("product_ids", nargs="+")

    p = sub.add_parser("mark", help="완료 수동 기록")
    p.add_argument("--account")
    p.add_argument("--run", help="run 폴더명 (예: 0723_yong1-1)")
    p.add_argument("--status", default="ok", choices=DONE_STATUSES)
    p.add_argument("--reason")
    p.add_argument("product_ids", nargs="+")

    p = sub.add_parser("seed", help="기존 run 결과를 대장으로 이관")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--account", required=True)
    p.add_argument("--date", required=True, help="작업일 YYYY-MM-DD")

    args = ap.parse_args()
    try:
        {"stats": _cmd_stats, "check": _cmd_check,
         "mark": _cmd_mark, "seed": _cmd_seed}[args.cmd](args)
    except RuntimeError as e:
        print(f"[오류] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
