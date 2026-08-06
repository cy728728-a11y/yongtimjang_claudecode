#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
줌(Zoom) 클라우드 녹화(다시보기) 조회기
- Server-to-Server OAuth로 인증 후 특정 기간의 클라우드 녹화 목록을 조회
- 미팅별 다시보기 공유 링크(share_url)와 개별 녹화 파일 재생 링크(play_url)를 출력
- 자격증명은 워크스페이스 루트 .env 에서 읽음 (zoom_meeting.py 와 동일)
- 표준 라이브러리만 사용 (별도 pip 설치 불필요)

사용 예:
  # 어제 녹화 (기본값)
  python zoom_recordings.py

  # 특정 날짜
  python zoom_recordings.py --date 2026-08-05

  # 기간 지정
  python zoom_recordings.py --from 2026-08-01 --to 2026-08-06

  # 사람이 읽기 쉬운 형태로
  python zoom_recordings.py --date 2026-08-05 --pretty

주의:
  녹화 조회에는 Zoom S2S OAuth 앱에 'cloud_recording:read:list_user_recordings:admin'
  (구 스코프명 'recording:read:admin') 권한이 필요합니다.
  스코프가 없으면 Zoom이 4xx 에러와 함께 'does not contain scopes' 류 메시지를 돌려줍니다.
"""

import argparse
import base64
import datetime as dt
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


def _call_zoom_api(req: urllib.request.Request, action_label: str):
    """urlopen을 감싸 HTTPError/URLError를 일관된 RuntimeError로 변환.

    - HTTPError: 응답은 왔지만 에러 상태 (자격증명/스코프/요청 오류 등)
    - URLError: 응답 자체가 없음 (오프라인, DNS 실패, 방화벽 차단 등)
    """
    try:
        return urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        raise RuntimeError(f"{action_label} 실패 ({e.code}): {body}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Zoom 서버에 연결할 수 없습니다: {e.reason}")


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
    with _call_zoom_api(req, "Zoom 토큰 발급") as resp:
        data = json.loads(resp.read().decode())
        return data["access_token"]


def list_recordings(access_token: str, user_email: str, date_from: str, date_to: str) -> list:
    """특정 기간의 클라우드 녹화 목록을 조회.

    Zoom 'List all recordings' API는 from/to 구간이 최대 1개월이며,
    next_page_token 으로 페이지네이션한다. 여기선 모든 페이지를 모아 반환.
    반환: 미팅 dict 리스트 (원본 Zoom 응답의 meetings 항목).
    """
    meetings = []
    next_token = ""
    base = f"https://api.zoom.us/v2/users/{urllib.parse.quote(user_email, safe='')}/recordings"
    while True:
        params = {
            "from": date_from,
            "to": date_to,
            "page_size": 300,
        }
        if next_token:
            params["next_page_token"] = next_token
        url = base + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, method="GET", headers={
            "Authorization": f"Bearer {access_token}",
        })
        with _call_zoom_api(req, "Zoom 녹화 목록 조회") as resp:
            data = json.loads(resp.read().decode())
        meetings.extend(data.get("meetings", []))
        next_token = data.get("next_page_token", "")
        if not next_token:
            break
    return meetings


def simplify(meetings: list) -> list:
    """Zoom 원본 응답을 다시보기에 필요한 핵심 필드만 추려 정리."""
    result = []
    for m in meetings:
        files = []
        for f in m.get("recording_files", []):
            # 녹화 영상/음성 파일만 (채팅·자막 등 부가 파일은 play_url 없음)
            play = f.get("play_url")
            if not play:
                continue
            files.append({
                "type": f.get("recording_type", ""),
                "file_type": f.get("file_type", ""),
                "play_url": play,
                "download_url": f.get("download_url", ""),
            })
        result.append({
            "topic": m.get("topic", ""),
            "start_time": m.get("start_time", ""),
            "duration": m.get("duration", 0),
            # share_url: 미팅 단위 다시보기 공유 링크 (참석자에게 보내는 링크)
            "share_url": m.get("share_url", ""),
            # 공유 링크에 암호가 걸려 있으면 함께 전달해야 함
            "play_passcode": m.get("recording_play_passcode", ""),
            "files": files,
        })
    return result


def print_pretty(items: list, date_from: str, date_to: str):
    """사람이 읽기 좋은 형태로 출력."""
    if not items:
        print(f"[알림] {date_from} ~ {date_to} 기간에 클라우드 녹화가 없습니다.")
        print("  - 녹화가 '로컬 저장'이면 이 API에는 안 잡힙니다 (호스트 PC에만 있음).")
        print("  - 클라우드 녹화는 회의 종료 후 처리에 수 분~수십 분 걸릴 수 있습니다.")
        return
    for i, m in enumerate(items, 1):
        print(f"\n[{i}] {m['topic']}")
        print(f"    시작: {m['start_time']}  ({m['duration']}분)")
        if m["share_url"]:
            print(f"    ▶ 다시보기(공유): {m['share_url']}")
        if m["play_passcode"]:
            print(f"    🔑 재생 암호: {m['play_passcode']}")
        for f in m["files"]:
            label = f["type"] or f["file_type"]
            print(f"      - [{label}] {f['play_url']}")


def main():
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="줌 클라우드 녹화(다시보기) 조회 (Server-to-Server OAuth)")
    parser.add_argument("--date", help="조회할 특정 날짜 (KST 기준, 예: 2026-08-05). 지정 시 --from/--to 무시")
    parser.add_argument("--from", dest="date_from", help="시작 날짜 (예: 2026-08-01)")
    parser.add_argument("--to", dest="date_to", help="끝 날짜 (예: 2026-08-06)")
    parser.add_argument("--pretty", action="store_true", help="사람이 읽기 쉬운 형태로 출력 (기본은 JSON 한 줄)")
    args = parser.parse_args()

    # 기간 결정: --date 우선, 없으면 --from/--to, 둘 다 없으면 '어제'
    if args.date:
        date_from = date_to = args.date
    elif args.date_from or args.date_to:
        # 한쪽만 준 경우 나머지는 같은 날로 채움
        date_from = args.date_from or args.date_to
        date_to = args.date_to or args.date_from
    else:
        yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
        date_from = date_to = yesterday

    env = load_env(find_env())
    try:
        creds = load_credentials(env)
    except ValueError as e:
        print(f"[설정 오류] {e}", file=sys.stderr)
        print(
            "워크스페이스 루트에 .env를 만들고 "
            "ZOOM_ACCOUNT_ID/ZOOM_CLIENT_ID/ZOOM_CLIENT_SECRET/ZOOM_USER_EMAIL을 채워주세요. "
            "(.env.example 참고) 녹화 조회에는 'cloud_recording:read:list_user_recordings:admin' 스코프도 필요합니다.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        token = get_access_token(creds["ZOOM_ACCOUNT_ID"], creds["ZOOM_CLIENT_ID"], creds["ZOOM_CLIENT_SECRET"])
        meetings = list_recordings(token, creds["ZOOM_USER_EMAIL"], date_from, date_to)
    except RuntimeError as e:
        print(f"[오류] {e}", file=sys.stderr)
        sys.exit(1)

    items = simplify(meetings)

    if args.pretty:
        print_pretty(items, date_from, date_to)
    else:
        print(json.dumps({"from": date_from, "to": date_to, "meetings": items}, ensure_ascii=False))


if __name__ == "__main__":
    main()
