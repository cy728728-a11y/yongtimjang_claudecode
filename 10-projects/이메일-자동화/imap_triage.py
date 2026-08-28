#!/usr/bin/env python3
"""
이메일 자동관리 — IMAP 판(OAuth 불필요, 토큰 만료 없음).

OAuth 프로덕션 게시가 제한된 범위(gmail.modify·drive) 때문에 막혀서
(앱 도메인·개인정보처리방침 URL 필요) IMAP + 앱 비밀번호로 전환했다. 2026-08-27.

사전 준비 (1회):
    1) https://myaccount.google.com/apppasswords 에서 앱 비밀번호 발급
    2) 터미널에서 키체인에 저장 (비밀번호는 화면에 안 보임):
       security add-generic-password -a cy728728@gmail.com -s gmail-imap -w

사용법:
    python3 imap_triage.py            # 미리보기 (삭제 안 함)
    python3 imap_triage.py --apply    # 실제 휴지통 이동 (30일 복구 가능)
    python3 imap_triage.py --apply --folder INBOX
"""
import imaplib, email, json, os, re, subprocess, sys, argparse
from email.header import decode_header, make_header
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rules import judge2

ACCOUNT = "cy728728@gmail.com"
KEYCHAIN_SERVICE = "gmail-imap"
# launchd 실행 시엔 ~/Documents 를 읽지 못하므로(TCC) 설치본 디렉터리로 넘어온다
LOG_DIR = os.environ.get("MAIL_TRIAGE_LOGS") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
imaplib._MAXLINE = 10_000_000  # 헤더 대량 응답 대비


def get_password():
    """macOS 키체인에서 앱 비밀번호를 읽는다. 평문 파일 보관 금지."""
    try:
        r = subprocess.run(
            ["security", "find-generic-password", "-a", ACCOUNT, "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, timeout=30)
    except Exception as e:
        raise SystemExit(f"키체인 조회 실패: {e}")
    if r.returncode != 0:
        raise SystemExit(
            "키체인에 앱 비밀번호가 없다. 터미널에서 먼저 실행:\n"
            f"  security add-generic-password -a {ACCOUNT} -s {KEYCHAIN_SERVICE} -w")
    # 앱 비밀번호는 4자씩 끊어 표시되므로 공백이 섞여 저장돼도 통과시킨다
    return re.sub(r"\s+", "", r.stdout)


def find_special(M, flag, fallback):
    """LIST 응답에서 특수용도 플래그(\\Trash, \\All …)가 붙은 폴더명을 찾는다.

    한국어 계정은 폴더명이 [Gmail]/휴지통 처럼 modified UTF-7 로 오므로
    이름을 추측하지 말고 플래그로 찾아야 한다.
    """
    typ, data = M.list()
    if typ != "OK":
        raise SystemExit("IMAP LIST 실패")
    for line in data:
        s = line.decode("utf-8", "replace") if isinstance(line, bytes) else str(line)
        if flag in s:
            m = re.search(r'"([^"]*)"\s*$', s)      # 끝의 따옴표 안이 폴더명
            if m:
                return '"%s"' % m.group(1)
    return fallback


def find_trash(M):
    """휴지통 폴더명"""
    return find_special(M, "\\Trash", '"[Gmail]/Trash"')


def decode(v):
    """MIME 인코딩된 헤더를 사람이 읽는 문자열로."""
    if not v:
        return ""
    try:
        return str(make_header(decode_header(v)))
    except Exception:
        return v


def fetch_headers(M, uids, chunk=300):
    """UID 목록의 헤더를 청크 단위로 가져온다."""
    out = []
    for i in range(0, len(uids), chunk):
        part = uids[i:i + chunk]
        # UID 를 명시적으로 요청한다 — 서버에 따라 응답에 UID 를 안 실어주는 경우가 있다
        typ, data = M.uid("FETCH", ",".join(part),
                          "(UID BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE LIST-UNSUBSCRIBE)])")
        if typ != "OK":
            raise SystemExit("IMAP FETCH 실패")
        cur_uid = None
        for item in data:
            if isinstance(item, tuple):
                m = re.search(rb"UID (\d+)", item[0])
                cur_uid = m.group(1).decode() if m else cur_uid
                msg = email.message_from_bytes(item[1])
                out.append({
                    "id": cur_uid,
                    "from": decode(msg.get("From")),
                    "subject": decode(msg.get("Subject")),
                    "date": msg.get("Date", ""),
                    "unsub": bool(msg.get("List-Unsubscribe")),
                })
        print(f"  헤더 수집 {min(i+chunk, len(uids))}/{len(uids)}", flush=True)
    return out


def move_to_trash(M, uids, trash, chunk=500):
    """UID MOVE 로 휴지통 이동. MOVE 미지원 시 COPY+삭제플래그로 폴백."""
    moved = 0
    for i in range(0, len(uids), chunk):
        part = ",".join(uids[i:i + chunk])
        typ, _ = M.uid("MOVE", part, trash)
        if typ != "OK":
            typ, _ = M.uid("COPY", part, trash)
            if typ != "OK":
                raise SystemExit("휴지통 이동 실패 (COPY)")
            M.uid("STORE", part, "+FLAGS", "(\\Deleted)")
            M.expunge()
        moved += len(uids[i:i + chunk])
        print(f"  휴지통 이동 {moved}/{len(uids)}", flush=True)
    return moved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="실제 삭제 실행 (미지정 시 미리보기)")
    ap.add_argument("--folder", default="INBOX", help="대상 폴더 (기본 INBOX)")
    ap.add_argument("--archive", action="store_true",
                    help="받은편지함 밖 아카이브를 대상으로 (보낸편지함·임시보관·휴지통·스팸 제외)")
    a = ap.parse_args()

    M = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    try:
        M.login(ACCOUNT, get_password())
    except imaplib.IMAP4.error as e:
        raise SystemExit(f"IMAP 로그인 실패 — 앱 비밀번호를 확인해라: {e}")
    print("계정:", ACCOUNT)

    trash = find_trash(M)
    print("휴지통 폴더:", trash)

    if a.archive:
        # 아카이브는 폴더가 아니다 — 전체보관함에서 받은편지함·보낸편지함 등을 뺀 나머지.
        # 보낸편지함을 빼지 않으면 본인이 보낸 메일까지 지우게 된다.
        a.folder = find_special(M, "\\All", '"[Gmail]/All Mail"')
        typ, _ = M.select(a.folder, readonly=not a.apply)
        if typ != "OK":
            raise SystemExit("전체보관함 열기 실패")
        typ, data = M.uid("SEARCH", None, "X-GM-RAW",
                          '"-in:inbox -in:sent -in:drafts -in:trash -in:spam"')
    else:
        typ, _ = M.select(a.folder, readonly=not a.apply)
        if typ != "OK":
            raise SystemExit(f"폴더 열기 실패: {a.folder}")
        typ, data = M.uid("SEARCH", None, "ALL")
    uids = data[0].split()
    uids = [u.decode() for u in uids]
    print(f"대상 {len(uids)}건 ({a.folder})")
    if not uids:
        M.logout()
        return

    meta = fetch_headers(M, uids)
    dele = [m for m in meta if judge2(m) == "DELETE"]
    keep = [m for m in meta if judge2(m) != "DELETE"]
    print(f"\n삭제 대상 {len(dele)} / 남김 {len(keep)}")

    os.makedirs(LOG_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    logfile = os.path.join(LOG_DIR, f"{stamp}-imap-{'apply' if a.apply else 'preview'}.json")
    json.dump({"folder": a.folder, "delete": dele, "keep": keep},
              open(logfile, "w"), ensure_ascii=False, indent=1)
    print("로그:", logfile)

    if not a.apply:
        print("\n[미리보기] 삭제 예정 상위 20건:")
        for m in dele[:20]:
            print("  -", m["from"][:35], "|", (m["subject"] or "")[:55])
        print("\n실제 삭제하려면 --apply 를 붙여 다시 실행.")
        M.logout()
        return

    move_to_trash(M, [m["id"] for m in dele], trash)
    M.logout()
    print(f"\n완료. {len(dele)}건 휴지통 이동 (30일 복구 가능). 남은 {a.folder} {len(keep)}건.")


if __name__ == "__main__":
    main()
