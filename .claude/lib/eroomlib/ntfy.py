# -*- coding: utf-8 -*-
"""폰 푸시 알림(ntfy) — 설정 ~/.eroom/ntfy.json {"server","topic"}.
사용: from eroomlib.ntfy import send; send("제목", "본문")   /   python -m eroomlib.ntfy test
주제 이름이 곧 수신 주소라서 남에게 알려 주지 않는다. 알림 문구에 개인정보·비밀값을 넣지 않는다.
"""
import json
import os
import sys
import urllib.request

CONF = os.path.expanduser("~/.eroom/ntfy.json")


def send(title, body, priority="default", tags=""):
    """성공하면 True. 설정이 없거나 실패하면 False(예외를 밖으로 던지지 않는다)."""
    try:
        c = json.load(open(CONF, encoding="utf-8"))
        # 한글 제목이 깨지지 않게 JSON 방식으로 보낸다(헤더 방식은 한글 불가)
        payload = {"topic": c["topic"], "title": title, "message": body,
                   "priority": {"min": 1, "low": 2, "default": 3, "high": 4, "max": 5}.get(priority, 3)}
        if tags:
            payload["tags"] = [t for t in tags.split(",") if t]
        req = urllib.request.Request(c.get("server", "https://ntfy.sh").rstrip("/"),
                                     data=json.dumps(payload).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json", "User-Agent": "eroom-notify/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return 200 <= r.status < 300
    except Exception as e:  # 알림 실패가 본 작업을 멈추게 하면 안 된다
        print(f"[ntfy] 전송 실패: {e}", file=sys.stderr)
        return False


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        print("ok" if send("소싱 알림 시험", "이 알림이 보이면 연결 완료", tags="white_check_mark") else "fail")
