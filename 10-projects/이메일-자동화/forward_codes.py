#!/usr/bin/env python3
"""
자동전달 확인 코드 수집기.

각 계정에서 cy728728 로 전달을 걸면 Google 이 확인 메일을 보낸다.
그 17통을 일일이 열어보지 않도록, 요청 계정 · 확인 코드 · 확인 링크를 표로 뽑는다.

사용법:
    python3 forward_codes.py          # 확인 메일 전부 훑어 표로 출력
    python3 forward_codes.py --open   # 확인 링크를 맥북 크롬에서 순서대로 연다
"""
import imaplib, email, re, sys, os, argparse, subprocess
from email.header import decode_header, make_header

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from imap_triage import ACCOUNT, get_password, decode, find_special

imaplib._MAXLINE = 10_000_000

SENDER = "forwarding-noreply@google.com"


def body_text(msg):
    """멀티파트 포함 본문을 평문으로 합친다."""
    parts = []
    for p in msg.walk():
        if p.get_content_maintype() == "multipart":
            continue
        try:
            payload = p.get_payload(decode=True)
            if payload:
                parts.append(payload.decode(p.get_content_charset() or "utf-8", "replace"))
        except Exception:
            continue
    return "\n".join(parts)


def extract(text, subject):
    """본문에서 요청 계정 · 확인 코드 · 확인 링크를 뽑는다."""
    # 확인 링크: https://mail-settings.google.com/mail/vf-...
    # ⚠️ 같은 본문에 취소 링크(/mail/uf-...)가 함께 들어있다. 반드시 vf- 만 잡을 것.
    link = None
    m = re.search(r"https://mail(?:-settings)?\.google\.com/mail/vf-[^\s\"'<>]*", text)
    if m:
        link = m.group(0).rstrip(").,")
    # 확인 코드: 8~11자리 숫자 (제목에도 자주 들어있다)
    code = None
    for src in (subject, text):
        m = re.search(r"\b(\d{8,11})\b", src or "")
        if m:
            code = m.group(1)
            break
    # 요청 계정: 본문에 등장하는 gmail/naver 주소 중 수집함 자신은 제외
    reqs = [a for a in re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
            if a.lower() != ACCOUNT and "google.com" not in a.lower()]
    requester = reqs[0] if reqs else None
    return requester, code, link


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--open", action="store_true", help="확인 링크를 맥북 크롬에서 연다")
    a = ap.parse_args()

    M = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    M.login(ACCOUNT, get_password())

    # 받은편지함에 없을 수 있으니 전체보관함까지 훑는다.
    # 폴더명은 한국어 계정에서 modified UTF-7 이므로 특수용도 플래그로 찾는다.
    all_mail = find_special(M, "\\All", '"[Gmail]/All Mail"')
    found = []
    for folder in ("INBOX", all_mail):
        try:
            typ, _ = M.select(folder, readonly=True)
            if typ != "OK":
                continue
        except Exception:
            continue
        typ, data = M.uid("SEARCH", None, f'(FROM "{SENDER}")')
        if typ != "OK":
            continue
        uids = [u.decode() for u in data[0].split()]
        if not uids:
            continue
        typ, msgs = M.uid("FETCH", ",".join(uids), "(RFC822)")
        for item in msgs:
            if not isinstance(item, tuple):
                continue
            msg = email.message_from_bytes(item[1])
            subj = decode(msg.get("Subject"))
            req, code, link = extract(body_text(msg), subj)
            found.append({"requester": req, "code": code, "link": link,
                          "date": msg.get("Date", ""), "subject": subj})
        if found:
            break
    M.logout()

    if not found:
        print("확인 메일이 아직 없다. 각 계정에서 전달 주소를 추가하면 여기로 온다.")
        return

    # 계정별 최신 1건만
    latest = {}
    for f in found:
        k = (f["requester"] or f["subject"])
        latest[k] = f

    print(f"확인 메일 {len(found)}통 / 계정 {len(latest)}개\n")
    print(f"{'요청 계정':32s} {'확인코드':12s} 링크")
    print("-" * 100)
    for k, f in sorted(latest.items()):
        print(f"{(f['requester'] or '?'):32s} {(f['code'] or '?'):12s} {(f['link'] or '(없음)')[:60]}")

    if a.open:
        for k, f in sorted(latest.items()):
            if f["link"]:
                subprocess.run(["open", "-a", "Google Chrome", f["link"]])
        print("\n확인 링크를 크롬에서 열었다. 각 탭에서 '확인' 버튼을 눌러라.")


if __name__ == "__main__":
    main()
