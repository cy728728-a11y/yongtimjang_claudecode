#!/usr/bin/env python3
"""네이버 쇼핑 안전거래센터 KC인증 소명접수 메일 자동처리 (kc-claim).

흐름: 수집함 IMAP 감지 → 메일의 상품번호 → 커머스API(전 마켓) 판매자상품코드
      → 불사자 원본 + 같은 불사자코드 복사본 전부 삭제(MARKET_AND_SOURCE · ALL)
      → 스마트스토어 삭제 확인 → 대장 기록 + 검수기준 반영 대기열.

소명 메일은 보내지 않는다 (2026-11-19 용팀장 결정 — 상품이 지워지면 구매불가·판매금지 걸 대상이 없다).
불사자 계정 확인·삭제·확인 로직은 rights-claim 의 검증된 함수를 그대로 쓴다.
"""
import argparse
import email
import fcntl
import imaplib
import json
import os
import re
import sys
import types
from datetime import datetime, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILLS_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
RC_DIR = os.path.join(SKILLS_DIR, "rights-claim", "scripts")
if RC_DIR not in sys.path:
    sys.path.insert(0, RC_DIR)

import run_rights_claim as RC  # noqa: E402

KC_FROM = "help_safety_shopping@navercorp.com"
KC_SUBJECT_KEY = "KC인증"
SKIP_MARKETS = {"12-1"}   # 운영 안 함 — 토큰 실패가 정상


# ---------------------------------------------------------------------------
# 순수함수
# ---------------------------------------------------------------------------
def parse_kc_mail(body):
    """메일 본문 → {nos:[상품번호...], deadline:'2026년 11월 19일'}. 상품번호 없으면 nos=[]."""
    text = RC.html_to_text(body) if RC._looks_html(body) else (body or "")
    nos = []
    for n in re.findall(r"smartstore\.naver\.com/(?:main|[\w-]+)/products/(\d{6,})", text) + \
            re.findall(r"상품\s*번호\s*[:：]?\s*(\d{6,})", text):
        if n not in nos:
            nos.append(n)
    m = re.search(r"소명\s*기간\s*[:：]?\s*(\d{4}년\s*\d{1,2}월\s*\d{1,2}일)", text)
    return {"nos": nos, "deadline": m.group(1) if m else ""}


def is_kc_mail(from_, subject):
    return KC_FROM in (from_ or "").lower() and KC_SUBJECT_KEY in (subject or "")


def all_siblings(items, tokens, exclude_pids):
    """KC 용 복사본 선택: 같은 불사자코드면 상품명과 무관하게 전부 (같은 물건이라 같은 인증 문제)."""
    out, seen = [], set(str(p) for p in (exclude_pids or ()))
    for it in items or []:
        if not isinstance(it, dict):
            continue
        pid = str(it.get("productId") or "")
        if pid and pid not in seen:
            seen.add(pid)
            out.append(it)
    return out


def ledger_dir(data_root):
    return os.path.join(data_root, "kc-claim")


def read_ledger(data_root):
    rows = []
    try:
        with open(os.path.join(ledger_dir(data_root), "ledger.jsonl"), encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    return rows


def append_jsonl(data_root, name, row):
    d = ledger_dir(data_root)
    os.makedirs(d, exist_ok=True)
    row = dict(row)
    row.setdefault("ts", RC._now_iso())
    with open(os.path.join(d, name), "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def last_status(rows, no):
    st = ""
    for r in rows:
        if r.get("no") == no:
            st = r.get("status", "")
    return st


# ---------------------------------------------------------------------------
# 메일 (수집함 IMAP, 읽기전용)
# ---------------------------------------------------------------------------
def fetch_mails(since_days, secrets, log):
    if RC.MAIL_DIR not in sys.path:
        sys.path.insert(0, RC.MAIL_DIR)
    from imap_triage import ACCOUNT, decode, find_special, get_password
    pw = get_password()
    secrets.append(pw)
    out = []
    M = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    try:
        M.login(ACCOUNT, pw)
        box = find_special(M, "\\All", '"[Gmail]/All Mail"')
        typ, _ = M.select(box, readonly=True)
        if typ != "OK":
            M.select("INBOX", readonly=True)
        since = RC._imap_date(datetime.now() - timedelta(days=since_days))
        typ, data = M.uid("SEARCH", None, "SINCE", since, "FROM", f'"{KC_FROM}"')
        for uid in ((data[0] or b"").split() if typ == "OK" and data else []):
            try:
                typ, d = M.uid("FETCH", uid, "(BODY.PEEK[])")
                raw = next((x[1] for x in d or [] if isinstance(x, tuple)), None)
                if not raw:
                    continue
                msg = email.message_from_bytes(raw)
                frm, subj = decode(msg.get("From")), decode(msg.get("Subject"))
                if not is_kc_mail(frm, subj):
                    continue
                h, p = RC._mail_bodies(msg)
                parsed = parse_kc_mail(h or p or "")
                if not parsed["nos"] and h and p:
                    parsed = parse_kc_mail(p)
                parsed.update(to=decode(msg.get("To")), date=decode(msg.get("Date")))
                out.append(parsed)
            except Exception as e:
                log(f"[mail] uid {uid!r} 읽기 실패: {type(e).__name__}: {e}")
    finally:
        try:
            M.logout()
        except Exception:
            pass
    return out


# ---------------------------------------------------------------------------
# 처리
# ---------------------------------------------------------------------------
def resolve(ctx, no, log):
    """상품번호 → 전 마켓 커머스 조회. (market, seller_code, name, status) / 전 마켓에 없으면 None.

    조회 오류가 난 마켓이 하나라도 있으면 '없다'고 단정하지 않고 예외를 낸다(그 마켓에 있을 수 있다).
    """
    errors = []
    for mk in ctx.deps.stores:
        if mk in SKIP_MARKETS:
            continue
        try:
            p = ctx.commerce().get_product(mk, no)
        except RuntimeError as e:
            if RC.NOT_FOUND_MARK in str(e):
                continue
            errors.append(mk)
            continue
        except Exception:
            errors.append(mk)
            continue
        code, status = RC._seller_code(p)
        name = ((p or {}).get("originProduct") or {}).get("name", "")
        return mk, code, name, status
    if errors:
        raise RuntimeError(f"조회 오류 마켓 {', '.join(errors)} — 없음 단정 불가")
    return None


def process(ctx, args, mail, no, log):
    row = {"no": no, "to": mail.get("to", ""), "mail_date": mail.get("date", ""),
           "deadline": mail.get("deadline", "")}
    found = resolve(ctx, no, log)
    if not found:
        log(f"  - {no} 전 마켓에 없음 → 이미 삭제된 것으로 본다")
        row.update(status="done", note="already_deleted")
        return row
    mk, code, name, status = found
    row.update(market=mk, seller_code=code, name=name, store_status=status)
    log(f"  - {no} ({mk}) {name} · {status} · 판매자코드 {code}")
    if not code:
        row.update(status="failed", fail_stage="no_seller_code")
        return row
    target = {"no": no, "market": mk, "seller_code": code, "status": status, "state": "resolved"}
    res = {"already_deleted": 0, "deleted": 0, "copies": 0, "locked": 0, "right_name": ""}
    orig_filter = RC.filter_copies
    RC.filter_copies = all_siblings          # 같은 불사자코드 복사본은 전부
    try:
        hard, issues, nick_bad, confirm = RC._bulsaja_stage(ctx, args, res, [target], log)
    finally:
        RC.filter_copies = orig_filter
    row.update(deleted=res["deleted"], copies=res["copies"], locked=res["locked"], issues=issues)
    if hard:
        row.update(status="failed", fail_stage=hard)
        return row
    if not args.apply:
        row.update(status="dry-run")
        return row
    ok = RC._confirm_market(ctx, confirm, log) if confirm else (res["locked"] == 0)
    row.update(market_confirmed=bool(ok))
    if res["locked"] and not res["deleted"]:
        row.update(status="locked")          # 판매된 상품 — 지우지 않는다. 사람 판단
    else:
        row.update(status="done" if ok and not issues else "partial")
    return row


def run(args):
    deps = RC._real_deps()
    log = RC._Log(deps.secrets)
    data_root = deps.data_root
    rows = read_ledger(data_root)
    mails = fetch_mails(args.since_days, deps.secrets, log)
    todo = []
    for m in mails:
        for no in m["nos"]:
            if args.no and no != args.no:
                continue
            if not args.no and last_status(rows, no) in ("done", "locked"):
                continue
            if no not in [t[1] for t in todo]:
                todo.append((m, no))
    if not mails:
        log("[kc] 새 KC 메일 없음")
    log(f"[kc] 메일 {len(mails)}통 · 처리 대상 {len(todo)}건 · {'실행' if args.apply else 'dry-run'}")
    if not todo:
        return 0
    ctx = RC._Ctx(deps)
    bad = 0
    try:
        for m, no in todo:
            try:
                row = process(ctx, args, m, no, log)
            except Exception as e:
                row = {"no": no, "status": "failed", "fail_stage": f"exception:{type(e).__name__}"}
                log(f"  ! {no} 처리 중 예외: {type(e).__name__}: {e}")
            log(f"[kc] {no} → {row.get('status')} (삭제 {row.get('deleted', 0)} · 잠금 {row.get('locked', 0)})")
            if args.apply:
                append_jsonl(data_root, "ledger.jsonl", row)
                if row.get("name") and row.get("status") in ("done", "partial", "locked"):
                    # 검수기준 반영 대기열 — sourcing-inspect 가 작업 시작 때 읽어 규칙에 넣는다
                    append_jsonl(data_root, "inspect_queue.jsonl",
                                 {"no": no, "name": row["name"], "reason": "네이버 KC인증 민원", "reflected": False})
            if row.get("status") in ("failed", "partial", "locked"):
                bad += 1
                if args.apply:
                    try:
                        from eroomlib.ntfy import send
                        send("KC 소명 자동처리 확인 필요",
                             f"상품번호 {no} {row.get('name', '')[:30]} → {row.get('status')} "
                             f"({row.get('fail_stage', '')}) 소명기한 {row.get('deadline', '')}", priority="high")
                    except Exception:
                        pass
    finally:
        ctx.close()
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="KC인증 소명접수 메일 → 신고 상품 삭제")
    ap.add_argument("--apply", action="store_true", help="실제 삭제·대장 기록 (없으면 dry-run)")
    ap.add_argument("--since-days", type=int, default=14)
    ap.add_argument("--no", help="이 상품번호만 처리 (대장 done 이어도)")
    ap.add_argument("--expect-nick", default="부킹")
    args = ap.parse_args(argv)
    lock_dir = os.path.expanduser("~/python_work/data/kc-claim")
    os.makedirs(lock_dir, exist_ok=True)
    lf = open(os.path.join(lock_dir, ".lock"), "w")
    try:
        fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("[kc] 다른 실행 중 — 종료")
        return 4
    try:
        return run(args)
    except Exception as e:
        print(f"[kc] 실패: {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
