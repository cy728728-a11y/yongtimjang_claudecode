#!/usr/bin/env python3
"""
스팸함에 잘못 들어간 전달 메일 구조.

전달 메일은 원 발신자를 유지한 채 우회 경로로 들어와서 Gmail 이 스팸으로 의심한다.
수집함에 `deliveredto:` 필터로 "스팸으로 분류하지 않음"을 걸어도
**이미 스팸에 들어간 메일은 되살아나지 않는다** (필터는 신규 수신에만 적용).
이 스크립트가 그걸 받은편지함으로 되돌린다.

사용법:
    python3 rescue_spam.py            # 미리보기
    python3 rescue_spam.py --apply    # 실제로 받은편지함으로 이동
"""
import imaplib, email, sys, os, re, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from imap_triage import ACCOUNT, get_password, decode, find_special
from verify_forwarding import TARGETS

imaplib._MAXLINE = 10_000_000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="실제로 받은편지함으로 이동")
    a = ap.parse_args()

    M = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    M.login(ACCOUNT, get_password())
    spam = find_special(M, "\\Junk", '"[Gmail]/Spam"')
    typ, _ = M.select(spam, readonly=not a.apply)
    if typ != "OK":
        raise SystemExit("스팸함 열기 실패")

    typ, data = M.uid("SEARCH", None, "ALL")
    uids = [u.decode() for u in data[0].split()]
    print(f"스팸함 {len(uids)}통 검사")
    if not uids:
        M.logout()
        return

    targets = {t.lower() for t in TARGETS}
    rescue = []
    for i in range(0, len(uids), 300):
        part = uids[i:i + 300]
        typ, resp = M.uid("FETCH", ",".join(part),
                          "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT X-FORWARDED-FOR DELIVERED-TO)])")
        cur = None
        for item in resp:
            if not isinstance(item, tuple):
                continue
            # 응답 앞머리의 첫 숫자는 시퀀스 번호다. UID MOVE 에 쓸 값은 "UID <n>" 쪽이다.
            m = re.search(rb"UID (\d+)", item[0])
            cur = m.group(1).decode() if m else cur
            msg = email.message_from_bytes(item[1])
            hay = " ".join(filter(None, [msg.get("X-Forwarded-For", "")] +
                                  (msg.get_all("Delivered-To") or []))).lower()
            src = [t for t in targets if t in hay]
            if src:
                rescue.append((cur, src[0], decode(msg.get("From")), decode(msg.get("Subject"))))

    print(f"\n전달 메일로 확인된 스팸 {len(rescue)}통")
    print("-" * 88)
    for uid, src, frm, subj in rescue:
        print(f"  {src[:24]:24s} | {frm[:26]:26s} | {subj[:32]}")

    if not rescue:
        M.logout()
        return
    if not a.apply:
        print("\n실제로 옮기려면 --apply 를 붙여 다시 실행.")
        M.logout()
        return

    ids = ",".join(u for u, *_ in rescue)
    typ, _ = M.uid("MOVE", ids, "INBOX")
    if typ != "OK":
        typ, _ = M.uid("COPY", ids, "INBOX")
        if typ != "OK":
            raise SystemExit("받은편지함 이동 실패")
        M.uid("STORE", ids, "+FLAGS", "(\\Deleted)")
        M.expunge()
    M.logout()
    print(f"\n완료. {len(rescue)}통을 받은편지함으로 되돌렸다.")


if __name__ == "__main__":
    main()
