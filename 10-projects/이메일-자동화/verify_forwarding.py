#!/usr/bin/env python3
"""
자동전달 실제 가동 검증기.

"설정을 저장했다"와 "전달이 실제로 온다"는 다르다.
수집함에 도착한 메일의 Delivered-To / X-Forwarded-For 헤더를 훑어
어느 계정에서 실제로 전달이 오고 있는지 집계한다.

사용법:
    python3 verify_forwarding.py            # 최근 500통 검사
    python3 verify_forwarding.py --all      # 받은편지함 전체
    python3 verify_forwarding.py --days 3   # 최근 3일치
"""
import imaplib, email, sys, os, re, argparse
from collections import Counter
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from imap_triage import ACCOUNT, get_password, decode, find_special

imaplib._MAXLINE = 10_000_000

# 진행표의 대상 계정 (수집함 자신은 제외)
TARGETS = [
    "cy27282728@gmail.com", "cy17281728@gmail.com",
    "yjcompanyg@gmail.com", "yjcompanyj@gmail.com", "yjcompanyk@gmail.com",
    "yjcompanym@gmail.com", "yjcompanynn@gmail.com", "yjqcompany@gmail.com",
    "yjcompanyr@gmail.com", "yjcompanyt@gmail.com", "yjcompanyu@gmail.com",
    "yjcompanyv@gmail.com", "yjcompanyw@gmail.com", "yjcompanyx@gmail.com",
    "yjcompanyy@gmail.com", "yjzcompany@gmail.com",
    "cy728@naver.com",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="받은편지함 전체 검사")
    ap.add_argument("--days", type=int, default=0, help="최근 N일치만 검사")
    a = ap.parse_args()

    M = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    M.login(ACCOUNT, get_password())
    # 받은편지함만 보면 정리(휴지통 이동)된 메일이 집계에서 빠져 가동 계정을 놓친다.
    # 전체보관함 + 휴지통 + 스팸까지 훑는다 (스팸 유입은 전달 설정의 실패 신호이기도 하다)
    scan = [("전체보관함", find_special(M, "\\All", '"[Gmail]/All Mail"')),
            ("휴지통",     find_special(M, "\\Trash", '"[Gmail]/Trash"')),
            ("스팸",       find_special(M, "\\Junk", '"[Gmail]/Spam"'))]

    query = "ALL"
    if a.days:
        since = (datetime.now() - timedelta(days=a.days)).strftime("%d-%b-%Y")
        query = f'(SINCE "{since}")'
    seen, spam_seen = Counter(), Counter()
    for label, folder in scan:
        typ, _ = M.select(folder, readonly=True)
        if typ != "OK":
            print(f"  {label}: 열기 실패 — 건너뜀")
            continue
        typ, data = M.uid("SEARCH", None, query)
        uids = [u.decode() for u in data[0].split()]
        if not a.all and not a.days:
            uids = uids[-500:]
        print(f"  {label}: {len(uids)}통 검사")
        for i in range(0, len(uids), 300):
            part = uids[i:i + 300]
            typ, resp = M.uid("FETCH", ",".join(part),
                              "(BODY.PEEK[HEADER.FIELDS (DELIVERED-TO X-FORWARDED-FOR X-FORWARDED-TO)])")
            for item in resp:
                if not isinstance(item, tuple):
                    continue
                txt = item[1].decode("utf-8", "replace").lower()
                for addr in set(re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", txt)):
                    if addr != ACCOUNT:
                        seen[addr] += 1
                        if label == "스팸":
                            spam_seen[addr] += 1
    M.logout()

    print()
    print("전달이 실제로 확인된 계정")
    print("-" * 52)
    live = 0
    for t in TARGETS:
        n = seen.get(t, 0)
        mark = "✅" if n else "  "
        if n:
            live += 1
        print(f"{mark} {t:28s} {n:5d}통")
    print("-" * 52)
    print(f"가동 {live} / 대상 {len(TARGETS)}")

    if spam_seen:
        print("\n⚠️ 스팸으로 분류된 전달 메일 (수집함 스팸 설정 점검 필요)")
        for k, v in sorted(spam_seen.items(), key=lambda x: -x[1]):
            print(f"   {k:28s} {v:5d}통")

    extra = {k: v for k, v in seen.items() if k not in TARGETS}
    if extra:
        print("\n(목록에 없는 전달원 — 확인 필요)")
        for k, v in sorted(extra.items(), key=lambda x: -x[1])[:10]:
            print(f"   {k:28s} {v:5d}통")


if __name__ == "__main__":
    main()
