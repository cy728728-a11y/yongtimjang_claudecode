#!/usr/bin/env python3
"""
네이버 메일 → 수집함(cy728728) 끌어오기.

네이버는 자동전달을 제공하지 않는다 (자동분류 처리 방법에 '전달'이 없다).
Gmail 쪽 POP3 가져오기("Check mail from other accounts")도 개인 계정에서 사라졌다.
그래서 네이버 IMAP 에서 새 메일을 읽어 수집함 IMAP 에 APPEND 하는 방식으로 잇는다.

중복 방지: 옮긴 메일의 Message-ID 를 state 파일에 기록한다.
원본은 네이버에 그대로 둔다(읽음 표시도 건드리지 않는다).

사전 준비 (1회):
    1) 네이버 → 환경설정 → POP3/IMAP 설정 → IMAP/SMTP 설정 → 사용함
    2) 네이버 → 내 정보 → 보안 설정 → 애플리케이션 비밀번호 발급
    3) security add-generic-password -a cy728@naver.com -s naver-imap -w

사용법:
    python3 naver_pull.py            # 미리보기 (옮기지 않음)
    python3 naver_pull.py --apply    # 실제로 수집함에 넣음
    python3 naver_pull.py --apply --account <다른-네이버-계정>
"""
import imaplib, email, json, os, re, subprocess, sys, argparse, time
from email.utils import parsedate_to_datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from imap_triage import ACCOUNT as COLLECTOR, get_password as collector_password, decode

imaplib._MAXLINE = 10_000_000
HERE = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.environ.get("MAIL_TRIAGE_LOGS") or os.path.join(HERE, "logs")


def keychain(account, service):
    """키체인에서 앱 비밀번호를 읽는다. 값은 절대 출력하지 않는다."""
    r = subprocess.run(["security", "find-generic-password", "-a", account, "-s", service, "-w"],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise SystemExit(
            f"키체인에 {account} 앱 비밀번호가 없다. 터미널에서 먼저 실행:\n"
            f"  security add-generic-password -a {account} -s {service} -w")
    return re.sub(r"\s+", "", r.stdout)


def state_path(account):
    return os.path.join(STATE_DIR, f"naver-pull-{account.replace('@', '_at_')}.json")


def load_state(account):
    p = state_path(account)
    if os.path.exists(p):
        try:
            return set(json.load(open(p)))
        except Exception:
            return set()
    return set()


def save_state(account, seen):
    os.makedirs(STATE_DIR, exist_ok=True)
    # 무한정 커지지 않도록 최근 5000건만 유지
    json.dump(sorted(seen)[-5000:], open(state_path(account), "w"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="실제로 수집함에 넣는다")
    ap.add_argument("--account", default="cy728@naver.com", help="네이버 계정")
    ap.add_argument("--limit", type=int, default=200, help="한 번에 옮길 최대 통수")
    a = ap.parse_args()

    seen = load_state(a.account)
    print(f"네이버 계정: {a.account} (이미 옮긴 기록 {len(seen)}건)")

    N = imaplib.IMAP4_SSL("imap.naver.com", 993)
    N.login(a.account, keychain(a.account, "naver-imap"))
    N.select("INBOX", readonly=True)          # 원본은 건드리지 않는다
    typ, data = N.uid("SEARCH", None, "ALL")
    uids = [u.decode() for u in data[0].split()]
    print(f"네이버 받은메일함 {len(uids)}통")

    # 아직 안 옮긴 것만 추린다 (Message-ID 로 판별)
    todo = []
    for i in range(0, len(uids), 100):
        part = uids[i:i + 100]
        # 네이버는 UID FETCH 응답에 UID 를 안 실어준다. 명시적으로 요청해야 한다.
        typ, resp = N.uid("FETCH", ",".join(part),
                          "(UID BODY.PEEK[HEADER.FIELDS (MESSAGE-ID FROM SUBJECT DATE)])")
        cur = None
        for item in resp:
            if not isinstance(item, tuple):
                continue
            m = re.search(rb"UID (\d+)", item[0])
            cur = m.group(1).decode() if m else cur
            msg = email.message_from_bytes(item[1])
            mid = (msg.get("Message-ID") or f"nomid:{a.account}:{cur}").strip()
            if mid not in seen:
                todo.append((cur, mid, decode(msg.get("From")), decode(msg.get("Subject"))))

    todo = todo[:a.limit]
    print(f"\n옮길 대상 {len(todo)}통")
    print("-" * 84)
    for _, _, frm, subj in todo[:20]:
        print(f"  {frm[:32]:32s} | {subj[:44]}")
    if len(todo) > 20:
        print(f"  … 외 {len(todo)-20}통")

    if not todo:
        N.logout()
        print("네이버수집: 0통 (새 메일 없음)")
        return
    if not a.apply:
        N.logout()
        print(f"네이버수집: 미리보기 {len(todo)}통 — 실제 이동은 --apply")
        return

    G = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    G.login(COLLECTOR, collector_password())

    moved, failed = 0, 0
    for uid, mid, frm, subj in todo:
        # 네이버 IMAP 은 (RFC822) 를 "Invalid arguments" 로 거절한다. BODY.PEEK[] 를 쓴다.
        typ, resp = N.uid("FETCH", uid, "(BODY.PEEK[])")
        raw = next((i[1] for i in resp if isinstance(i, tuple)), None)
        if not raw:
            failed += 1
            continue
        # 원본 수신 시각을 보존해 수집함에서 시간순이 어긋나지 않게 한다
        try:
            when = imaplib.Time2Internaldate(
                parsedate_to_datetime(email.message_from_bytes(raw).get("Date")).timestamp())
        except Exception:
            when = imaplib.Time2Internaldate(time.time())
        try:
            typ, _ = G.append("INBOX", "", when, raw)
            if typ != "OK":
                failed += 1
                continue
        except Exception:
            failed += 1
            continue
        seen.add(mid)
        moved += 1
        if moved % 20 == 0:
            print(f"  {moved}/{len(todo)} 이동", flush=True)

    save_state(a.account, seen)
    N.logout(); G.logout()
    print(f"\n완료. 원본은 네이버에 그대로 있다.")
    print(f"네이버수집: {moved}통" + (f" (실패 {failed})" if failed else ""))


if __name__ == "__main__":
    main()
