#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
줌(Zoom) 미팅 생성기
- Server-to-Server OAuth로 인증 후 미팅을 예약하고 join_url을 출력
- 자격증명은 워크스페이스 루트 .env 에서 읽음 (git 제외됨)
- 표준 라이브러리만 사용 (별도 pip 설치 불필요)

사용 예:
  python zoom_meeting.py --topic "구매대행 실전반 3주차" --start 2026-08-05T14:00:00 --duration 120
"""

import argparse
import base64
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REQUIRED_KEYS = ["ZOOM_ACCOUNT_ID", "ZOOM_CLIENT_ID", "ZOOM_CLIENT_SECRET", "ZOOM_USER_EMAIL"]


def load_env(env_path: Path) -> dict:
    """.env 파일을 파싱해 dict 로 반환 (KEY=VALUE, # 주석 무시)."""
    data = {}
    if not env_path.exists():
        return data
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        data[key.strip()] = val.strip().strip('"').strip("'")
    return data


def find_env() -> Path:
    """워크스페이스 루트(.env) → 스크립트 폴더(.env) 순으로 탐색."""
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / ".env",   # 워크스페이스 루트 (10-projects/줌미팅-자동화/ 기준 2단계 위)
        here.parent / ".env",       # 스크립트와 같은 폴더
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def load_credentials(env: dict) -> dict:
    """env dict에서 줌 자격증명 4종을 검증해 반환. 누락 시 ValueError."""
    missing = [k for k in REQUIRED_KEYS if not env.get(k, "").strip()]
    if missing:
        raise ValueError(f"다음 값이 .env에 없습니다: {', '.join(missing)}")
    return {k: env[k].strip() for k in REQUIRED_KEYS}


def get_access_token(account_id: str, client_id: str, client_secret: str) -> str:
    """Server-to-Server OAuth로 access token 발급."""
    url = "https://zoom.us/oauth/token?" + urllib.parse.urlencode({
        "grant_type": "account_credentials",
        "account_id": account_id,
    })
    auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    req = urllib.request.Request(url, method="POST", headers={
        "Authorization": f"Basic {auth}",
    })
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            return data["access_token"]
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        raise RuntimeError(f"Zoom 토큰 발급 실패 ({e.code}): {body}")


def create_meeting(access_token: str, user_email: str, topic: str, start_time: str, duration_minutes: int) -> dict:
    """줌 미팅 생성. start_time은 'YYYY-MM-DDTHH:MM:SS' (KST) 형식."""
    url = f"https://api.zoom.us/v2/users/{urllib.parse.quote(user_email)}/meetings"
    payload = {
        "topic": topic,
        "type": 2,
        "start_time": start_time,
        "duration": duration_minutes,
        "timezone": "Asia/Seoul",
        "settings": {
            "waiting_room": False,
        },
    }
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            return {
                "topic": data["topic"],
                "start_time": data["start_time"],
                "duration": data["duration"],
                "join_url": data["join_url"],
                "start_url": data["start_url"],
            }
    except urllib.error.HTTPError as e:
        body_text = e.read().decode() if e.fp else ""
        raise RuntimeError(f"Zoom 미팅 생성 실패 ({e.code}): {body_text}")


def main():
    parser = argparse.ArgumentParser(description="줌 미팅 생성 (Server-to-Server OAuth)")
    parser.add_argument("--topic", required=True, help="미팅 제목")
    parser.add_argument("--start", required=True, help="시작시간, KST, 예: 2026-08-05T14:00:00")
    parser.add_argument("--duration", required=True, type=int, help="소요시간(분)")
    args = parser.parse_args()

    env = load_env(find_env())
    try:
        creds = load_credentials(env)
    except ValueError as e:
        print(f"[설정 오류] {e}", file=sys.stderr)
        print(
            "marketplace.zoom.us > Developer > Build App > Server-to-Server OAuth 로 앱을 만들고 "
            ".env에 ZOOM_ACCOUNT_ID/ZOOM_CLIENT_ID/ZOOM_CLIENT_SECRET/ZOOM_USER_EMAIL을 채워주세요.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        token = get_access_token(creds["ZOOM_ACCOUNT_ID"], creds["ZOOM_CLIENT_ID"], creds["ZOOM_CLIENT_SECRET"])
        meeting = create_meeting(token, creds["ZOOM_USER_EMAIL"], args.topic, args.start, args.duration)
    except RuntimeError as e:
        print(f"[오류] {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(meeting, ensure_ascii=False))


if __name__ == "__main__":
    main()
