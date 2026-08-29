#!/usr/bin/env python3
"""
정리 결과 보고서를 cy728@daum.net 으로 발송.

보고서의 핵심은 "삭제했다"가 아니라 **확인이 필요한 새 메일이 뭐가 왔는가**다.
수집함에 남은(KEEP 판정) 메일 중 아직 보고하지 않은 것만 골라 알린다.

**조용한 회차는 보내지 않는다** — 새 메일도 삭제도 없으면 아무것도 안 한다.
안 그러면 보고서 자체가 스팸이 된다.

인증은 수집함과 같은 앱 비밀번호(키체인 `gmail-imap`)를 SMTP 에 그대로 쓴다.

사용법:
    python3 report_mail.py                      # 미리보기 (발송 안 함)
    python3 report_mail.py --send               # 실제 발송
    python3 report_mail.py --send --deleted 12 --naver 3
"""
import imaplib, email, smtplib, json, os, re, sys, argparse
from email.message import EmailMessage
from email.utils import formatdate
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from imap_triage import ACCOUNT, get_password, decode
from rules import judge2

imaplib._MAXLINE = 10_000_000
TO = "cy728@daum.net"
STATE_DIR = os.path.expanduser("~/.local/share/mail-triage/state")
STATE = os.path.join(STATE_DIR, "reported.json")


def load_reported():
    try:
        return set(json.load(open(STATE)))
    except Exception:
        return set()


def save_reported(ids):
    os.makedirs(STATE_DIR, exist_ok=True)
    json.dump(sorted(ids)[-5000:], open(STATE, "w"))


def collect_new_keep():
    """수집함에 남아 있는 메일 중 아직 보고하지 않은 것"""
    M = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    M.login(ACCOUNT, get_password())
    M.select("INBOX", readonly=True)
    typ, d = M.uid("SEARCH", None, "ALL")
    uids = [u.decode() for u in d[0].split()]
    out = []
    for i in range(0, len(uids), 300):
        typ, resp = M.uid("FETCH", ",".join(uids[i:i + 300]),
                          "(UID BODY.PEEK[HEADER.FIELDS "
                          "(MESSAGE-ID FROM SUBJECT DATE LIST-UNSUBSCRIBE DELIVERED-TO)])")
        for item in resp:
            if not isinstance(item, tuple):
                continue
            m = email.message_from_bytes(item[1])
            rec = {"mid": (m.get("Message-ID") or "").strip(),
                   "from": decode(m.get("From")), "subject": decode(m.get("Subject")),
                   "date": m.get("Date", ""), "unsub": bool(m.get("List-Unsubscribe"))}
            # 어느 사업자 계정으로 온 메일인지 (전달 경로)
            dts = [a for a in (m.get_all("Delivered-To") or []) if ACCOUNT not in a]
            rec["via"] = dts[0].strip() if dts else ""
            if judge2(rec) != "DELETE":
                out.append(rec)
    M.logout()
    return out


def compose(new_keep, deleted, naver):
    lines = [f"수집함 정리 보고 — {datetime.now().strftime('%Y-%m-%d %H:%M')}", ""]
    lines.append(f"확인 필요한 새 메일  {len(new_keep)}건")
    lines.append(f"자동 삭제(휴지통)    {deleted}건")
    lines.append(f"네이버 수집          {naver}건")
    lines.append("")
    if new_keep:
        lines.append("─" * 52)
        lines.append("확인 필요한 새 메일")
        lines.append("─" * 52)
        for m in new_keep:
            via = f"  [{m['via'].split('@')[0]}]" if m["via"] else ""
            frm = re.sub(r".*<|>", "", m["from"])
            lines.append(f"· {m['subject'] or '(제목 없음)'}")
            lines.append(f"    {frm}{via}")
        lines.append("")
    lines.append("삭제된 메일은 휴지통에서 30일간 복구할 수 있습니다.")
    lines.append("수집함: https://mail.google.com/mail/u/0/#inbox")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true", help="실제 발송 (미지정 시 미리보기)")
    ap.add_argument("--seed", action="store_true",
                    help="지금 수집함에 있는 것을 '보고 완료'로 표시만 하고 끝낸다(최초 1회)")
    ap.add_argument("--to", default=TO)
    ap.add_argument("--deleted", type=int, default=0, help="이번 회차 삭제 건수")
    ap.add_argument("--naver", type=int, default=0, help="이번 회차 네이버 수집 건수")
    a = ap.parse_args()

    reported = load_reported()
    keep = collect_new_keep()

    if a.seed:
        # 최초 1회: 기존 재고를 보고 대상에서 제외한다.
        # 안 하면 첫 보고서가 수백 건짜리가 되어 아무도 안 읽는다.
        ids = {m["mid"] for m in keep if m["mid"]}
        save_reported(reported | ids)
        print(f"기존 {len(ids)}건을 보고 완료로 표시. 이제부터 새로 오는 것만 보고한다.")
        return

    new_keep = [m for m in keep if m["mid"] and m["mid"] not in reported]

    if not new_keep and not a.deleted and not a.naver:
        print("보고할 것 없음 — 발송하지 않는다.")
        return

    body = compose(new_keep, a.deleted, a.naver)
    subject = f"[수집함] 확인필요 {len(new_keep)}건 · 삭제 {a.deleted}건"

    if not a.send:
        print("=== 미리보기 (발송 안 함) ===")
        print(f"To: {a.to}\nSubject: {subject}\n")
        print(body)
        return

    msg = EmailMessage()
    msg["From"] = ACCOUNT
    msg["To"] = a.to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg.set_content(body)
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=60) as s:
            s.starttls()
            s.login(ACCOUNT, get_password())   # 수집함과 같은 앱 비밀번호
            s.send_message(msg)
    except Exception as e:
        print(f"발송 실패: {e}")
        sys.exit(1)

    save_reported(reported | {m["mid"] for m in new_keep})
    print(f"보고서 발송: {a.to} (확인필요 {len(new_keep)} · 삭제 {a.deleted} · 네이버 {a.naver})")


if __name__ == "__main__":
    main()
