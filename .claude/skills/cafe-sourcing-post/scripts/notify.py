"""알림 메일 — gws 로그인 계정(본인)에게 보낸다. 실패해도 전체 작업을 멈추지 않는다.

메일이 안 가면(구글 로그인 만료 등) 흔적을 두 곳에 남긴다:
  1) ~/.eroom/cafe-sourcing-LAST-FAILURE.txt 에 보내려던 내용 저장
  2) 맥북이면 화면 오른쪽 위 알림 띄우기
"""
import base64
import json
import os
import subprocess
import sys
from datetime import datetime
from email.mime.text import MIMEText

import drive

FAIL_PATH = os.path.join(os.path.expanduser("~"), ".eroom", "cafe-sourcing-LAST-FAILURE.txt")


def _desktop_alert(subject: str) -> None:
    """맥북 화면 알림(맥이 아니면 아무것도 안 함)."""
    if sys.platform != "darwin":
        return
    try:
        safe = subject.replace('"', "'")
        subprocess.run(["osascript", "-e", f'display notification "{safe}" with title "카페 자료 자동 게시"'],
                       timeout=15)
    except Exception:
        pass


def send_mail(subject: str, body: str) -> None:
    try:
        me = drive._gws(["gmail", "users", "getProfile", "--params", json.dumps({"userId": "me"})])["emailAddress"]
        msg = MIMEText(body, "plain", "utf-8")
        msg["To"] = me
        msg["From"] = me
        msg["Subject"] = subject
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
        drive._gws(["gmail", "users", "messages", "send", "--params", json.dumps({"userId": "me"}),
                    "--json", json.dumps({"raw": raw})])
        print(f"[알림] 메일 보냄: {subject}")
    except Exception as e:  # 메일이 안 가도 파일·화면 알림으로 남긴다
        print(f"[알림 실패] {e}\n--- 보내려던 내용 ---\n{subject}\n{body}")
        try:
            os.makedirs(os.path.dirname(FAIL_PATH), exist_ok=True)
            with open(FAIL_PATH, "w", encoding="utf-8") as f:
                f.write(f"{datetime.now():%Y-%m-%d %H:%M} 메일 발송 실패({e})\n\n{subject}\n\n{body}\n")
        except Exception:
            pass
        _desktop_alert(subject + " (메일 실패 — " + FAIL_PATH + " 확인)")
