#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
간단 이메일 발송기 (SMTP)
- 발신 계정/앱 비밀번호는 워크스페이스 루트의 .env 에서 읽음 (git 제외됨)
- 표준 라이브러리만 사용 (별도 pip 설치 불필요)
- Gmail / Daum / Naver SMTP(SSL) 지원. 발신 주소 도메인으로 자동 판별

사용 예:
  python send_email.py --to cy728@daum.net --subject "제목" --body-file body.txt
  python send_email.py --to a@b.com --subject "제목" --body "본문 한 줄"
  python send_email.py --to a@b.com --subject "제목" --body-file body.md --attach 파일.pdf
"""

import argparse
import os
import smtplib
import ssl
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.utils import formataddr
from pathlib import Path

# 제공자별 SMTP 서버 (SSL 465)
SMTP_SERVERS = {
    "gmail.com": ("smtp.gmail.com", 465),
    "daum.net": ("smtp.daum.net", 465),
    "hanmail.net": ("smtp.daum.net", 465),
    "naver.com": ("smtp.naver.com", 465),
}


def load_env(env_path: Path) -> dict:
    """.env 파일을 파싱해 dict 로 반환 (KEY=VALUE, # 주석 무시)."""
    data = {}
    try:
        if not env_path.exists():
            return data
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            data[key.strip()] = val.strip().strip('"').strip("'")
    except Exception as e:
        print(f"[경고] .env 읽기 실패: {e}", file=sys.stderr)
    return data


def find_env() -> Path:
    """워크스페이스 루트(.env) → 스크립트 폴더(.env) 순으로 탐색."""
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / ".env",   # 워크스페이스 루트 (10-projects/이메일-자동화/ 기준 2단계 위)
        here.parent / ".env",       # 스크립트와 같은 폴더
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]  # 없으면 루트 경로 반환(안내용)


def pick_smtp(sender: str):
    """발신 주소 도메인으로 SMTP 서버 결정."""
    domain = sender.split("@")[-1].lower()
    if domain not in SMTP_SERVERS:
        raise ValueError(
            f"'{domain}' 제공자는 미등록입니다. --smtp-host/--smtp-port 로 직접 지정하세요."
        )
    return SMTP_SERVERS[domain]


def build_message(sender, sender_name, to_addr, subject, body, attachments):
    """MIME 메시지 조립 (본문 UTF-8 + 선택 첨부)."""
    msg = MIMEMultipart()
    msg["From"] = formataddr((sender_name or sender, sender))
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    for path in attachments or []:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"첨부파일 없음: {p}")
        with open(p, "rb") as f:
            part = MIMEApplication(f.read(), Name=p.name)
        part["Content-Disposition"] = f'attachment; filename="{p.name}"'
        msg.attach(part)
    return msg


def main():
    parser = argparse.ArgumentParser(description="SMTP 이메일 발송기")
    parser.add_argument("--to", required=True, help="받는사람 이메일")
    parser.add_argument("--subject", required=True, help="제목")
    parser.add_argument("--body", help="본문 텍스트 (직접 입력)")
    parser.add_argument("--body-file", help="본문 파일 경로 (txt/md)")
    parser.add_argument("--attach", action="append", help="첨부파일 경로 (여러 번 사용 가능)")
    parser.add_argument("--from", dest="sender", help="발신 주소 (기본: .env 의 EMAIL_ADDRESS)")
    parser.add_argument("--smtp-host", help="SMTP 서버 직접 지정")
    parser.add_argument("--smtp-port", type=int, help="SMTP 포트 직접 지정")
    args = parser.parse_args()

    # 본문 확보
    if args.body_file:
        try:
            body = Path(args.body_file).read_text(encoding="utf-8")
        except Exception as e:
            print(f"[오류] 본문 파일 읽기 실패: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.body:
        body = args.body
    else:
        print("[오류] --body 또는 --body-file 중 하나는 필수입니다.", file=sys.stderr)
        sys.exit(1)

    # 자격증명 로드
    env_path = find_env()
    env = load_env(env_path)
    sender = args.sender or env.get("EMAIL_ADDRESS")
    password = env.get("EMAIL_APP_PASSWORD")
    sender_name = env.get("EMAIL_SENDER_NAME", "")

    if not sender or not password:
        print(
            f"[오류] 발신 자격증명이 없습니다.\n"
            f"  → {env_path} 에 EMAIL_ADDRESS 와 EMAIL_APP_PASSWORD 를 채워주세요.",
            file=sys.stderr,
        )
        sys.exit(1)

    # SMTP 서버 결정
    try:
        if args.smtp_host:
            host, port = args.smtp_host, (args.smtp_port or 465)
        else:
            host, port = pick_smtp(sender)
    except ValueError as e:
        print(f"[오류] {e}", file=sys.stderr)
        sys.exit(1)

    # 메시지 조립 & 발송
    try:
        msg = build_message(sender, sender_name, args.to, args.subject, body, args.attach)
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as server:
            server.login(sender, password)
            server.sendmail(sender, [args.to], msg.as_string())
        print(f"[성공] 발송 완료: {sender} → {args.to}  (제목: {args.subject})")
    except smtplib.SMTPAuthenticationError:
        print(
            "[오류] 인증 실패 — 앱 비밀번호가 틀렸거나, 일반 로그인 비번을 넣었을 수 있습니다.\n"
            "  Gmail은 2단계 인증 후 발급한 16자리 '앱 비밀번호'를 사용하세요.",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as e:
        print(f"[오류] 발송 실패: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
