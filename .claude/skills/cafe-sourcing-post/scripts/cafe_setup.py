"""네이버 카페 글쓰기 최초 1회 설정 — 용팀장이 브라우저에서 '동의'만 누르면 된다.

사용:
  python cafe_setup.py --client-id <ID> --client-secret <SECRET> --club-id <카페번호> --menu-id <게시판번호>
  (이미 설정이 있으면 빠진 값은 기존 값을 그대로 쓴다 — 허락만 다시 받을 때 인자 없이 실행)

흐름: 주소 출력(+브라우저 열기) → 용팀장 로그인·동의 → 이 PC의 localhost:8765 로 돌아온 코드를 받아
      토큰으로 바꿔 ~/.eroom/naver-cafe.json 에 저장.
네이버 개발자센터 앱의 Callback URL 은 http://localhost:8765/callback 으로 등록해야 한다.
"""
import argparse
import http.server
import secrets
import sys
import urllib.parse
import webbrowser

import requests

sys.stdout.reconfigure(encoding="utf-8")
import os  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cafe import CONFIG_PATH, TOKEN_URL, save_config  # noqa: E402

PORT = 8765
REDIRECT = f"http://localhost:{PORT}/callback"


def wait_for_code(state: str) -> str:
    """localhost 로 돌아오는 요청 하나를 받아 code 를 꺼낸다."""
    got = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("state", [""])[0] == state and q.get("code"):
                got["code"] = q["code"][0]
                msg = "네이버 허락 완료! 이 창은 닫아도 돼요."
            else:
                got["error"] = q.get("error_description", q.get("error", ["알 수 없음"]))[0]
                msg = f"실패: {got['error']}"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"<h2>{msg}</h2>".encode("utf-8"))

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", PORT), H)
    while not got:
        srv.handle_request()
    srv.server_close()
    if "error" in got:
        raise SystemExit(f"[실패] 네이버 허락 실패: {got['error']}")
    return got["code"]


def main():
    ap = argparse.ArgumentParser(description="네이버 카페 글쓰기 최초 설정")
    for k in ("client-id", "client-secret", "club-id", "menu-id"):
        ap.add_argument(f"--{k}")
    a = ap.parse_args()

    cfg = {}
    if os.path.exists(CONFIG_PATH):
        import json
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
    for k in ("client_id", "client_secret", "club_id", "menu_id"):
        v = getattr(a, k)
        if v:
            cfg[k] = v
        if not cfg.get(k):
            raise SystemExit(f"[실패] --{k.replace('_', '-')} 값이 필요합니다")

    state = secrets.token_urlsafe(16)
    url = "https://nid.naver.com/oauth2.0/authorize?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": cfg["client_id"], "redirect_uri": REDIRECT, "state": state})
    print("아래 주소를 브라우저에서 열고 네이버 로그인 → 동의를 눌러 주세요:\n")
    print(url, flush=True)
    try:
        webbrowser.open(url)
    except Exception:
        pass

    code = wait_for_code(state)
    try:
        data = requests.post(TOKEN_URL, params={
            "grant_type": "authorization_code", "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"], "code": code, "state": state}, timeout=30).json()
    except Exception as e:
        raise SystemExit(f"[실패] 토큰 교환 요청 실패: {e}")
    if not data.get("refresh_token"):
        raise SystemExit(f"[실패] 토큰을 못 받았습니다: {data}")
    cfg["access_token"] = data["access_token"]
    cfg["refresh_token"] = data["refresh_token"]
    cfg["_path"] = CONFIG_PATH
    save_config(cfg)
    print(f"\n완료: {CONFIG_PATH} 에 저장했습니다.")


if __name__ == "__main__":
    main()
