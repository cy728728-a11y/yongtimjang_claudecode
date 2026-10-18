#!/usr/bin/env python3
"""불사자 웹 토큰을 크롬 프로필 localStorage 에서 꺼내 ~/.eroom/bulsaja-web.json 에 저장한다.

웹은 요청마다 accesstoken(7일)·refreshtoken(30일) 헤더를 같이 보낸다(2026-10-18 실측).
로그인할 때 둘이 같은 iat 로 발급되므로, 지정 이메일의 가장 최근 iat 쌍을 고른다.
**토큰 값은 절대 출력하지 않는다** — 이메일·만료시각만 찍는다.

사용:  .venv/bin/python3 .claude/skills/sourcing-inspect/scripts/web_token.py [--email cy17281728@gmail.com]
401 이 나면: 크롬(Claude 확장이 붙은 프로필)에서 불사자에 cy17281728 로 다시 로그인 → 이 스크립트 재실행.
"""
import argparse
import base64
import datetime
import glob
import json
import os
import re
import sys

CHROME = os.path.expanduser("~/Library/Application Support/Google/Chrome")
OUT = os.path.expanduser("~/.eroom/bulsaja-web.json")
JWT = re.compile(rb"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")


def claims_of(tok):
    try:
        pl = tok.split(".")[1]
        pl += "=" * (-len(pl) % 4)
        return json.loads(base64.urlsafe_b64decode(pl))
    except Exception:
        return None


def scan(chrome_dir=CHROME):
    """{토큰: 클레임} — bulsaja 가 들어 있는 localStorage 파일만 본다."""
    found = {}
    for fp in glob.glob(os.path.join(chrome_dir, "*", "Local Storage", "leveldb", "*")):
        try:
            data = open(fp, "rb").read()
        except Exception:
            continue
        if b"bulsaja" not in data:
            continue
        for m in JWT.finditer(data):
            tok = m.group(0).decode()
            c = claims_of(tok)
            if c and "exp" in c and "iat" in c and "email" in c:
                found[tok] = c
    return found


def pick_pair(found, email, now):
    """같은 email 의 최신 iat 묶음에서 exp 짧은 쪽=access, 긴 쪽=refresh. 만료된 건 버린다."""
    cands = {t: c for t, c in found.items() if c.get("email") == email and c["exp"] > now}
    if not cands:
        return None
    latest = max(c["iat"] for c in cands.values())
    group = sorted(((t, c) for t, c in cands.items() if c["iat"] == latest), key=lambda x: x[1]["exp"])
    access = group[0]
    refresh = group[-1] if len(group) > 1 else None
    return access, refresh


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", default="cy17281728@gmail.com")
    a = ap.parse_args()
    now = int(datetime.datetime.now().timestamp())
    try:
        pair = pick_pair(scan(), a.email, now)
    except Exception as e:
        sys.exit(f"[오류] 크롬 프로필 읽기 실패: {e}")
    if not pair:
        sys.exit(f"[오류] {a.email} 의 유효한 불사자 웹 토큰이 없다 — 크롬에서 불사자 재로그인 필요")
    (acc, ac), ref = pair
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump({"token": acc, "refresh": ref[0] if ref else ""}, f)
    os.chmod(OUT, 0o600)
    fmt = lambda t: datetime.datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M")  # noqa: E731
    print(f"[web_token] {a.email} 저장 → {OUT}  access 만료 {fmt(ac['exp'])}"
          + (f" / refresh 만료 {fmt(ref[1]['exp'])}" if ref else " / refresh 없음"))


if __name__ == "__main__":
    main()
