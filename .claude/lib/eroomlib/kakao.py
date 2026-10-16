# -*- coding: utf-8 -*-
"""카카오톡 '나에게 보내기' 알림.

설정: ~/.eroom/kakao.json (600) — rest_api_key · client_secret(선택) · redirect_uri
토큰: ~/.eroom/kakao-token.json (600) — access(6시간)·refresh(2달, 남은 기간이 1달 미만이면 갱신 때 새로 받음)

최초 1회:  python3 -m eroomlib.kakao auth   → 링크를 브라우저로 열어 동의 → 로컬 서버가 코드를 받아 토큰 저장
발송:      from eroomlib.kakao import send_me; send_me("내용")
시험:      python3 -m eroomlib.kakao test
"""
import json
import os
import sys
import time
import urllib.parse

CONF = os.path.expanduser("~/.eroom/kakao.json")
TOKEN = os.path.expanduser("~/.eroom/kakao-token.json")
AUTH_URL = "https://kauth.kakao.com/oauth/authorize"
TOKEN_URL = "https://kauth.kakao.com/oauth/token"
SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"


class KakaoError(RuntimeError):
    pass


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_private(path, obj):
    """토큰 파일을 600 으로 원자적 저장."""
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _conf():
    try:
        c = _read(CONF)
    except Exception as e:
        raise KakaoError(f"설정 파일 없음/깨짐: {CONF} ({type(e).__name__})")
    key = str(c.get("rest_api_key") or "").strip()
    if not key or "여기에" in key:
        raise KakaoError("kakao.json 에 REST API 키가 비어 있다")
    sec = str(c.get("client_secret") or "").strip()
    if "빈칸" in sec or "여기에" in sec:
        sec = ""
    return key, sec, c.get("redirect_uri") or "http://localhost:8799/kakao"


def _post(url, data, headers=None):
    import requests
    r = requests.post(url, data=data, headers=headers or {}, timeout=20)
    try:
        j = r.json()
    except Exception:
        j = {"raw": r.text[:300]}
    if r.status_code >= 400:
        raise KakaoError(f"HTTP {r.status_code}: {j.get('error_description') or j.get('msg') or j}")
    return j


def _save_tokens(j, old=None):
    now = int(time.time())
    t = dict(old or {})
    t["access_token"] = j["access_token"]
    t["access_expires_at"] = now + int(j.get("expires_in", 21599)) - 60
    if j.get("refresh_token"):  # 갱신 응답엔 refresh 가 없을 수도 있다(남은 기간 충분할 때)
        t["refresh_token"] = j["refresh_token"]
        t["refresh_expires_at"] = now + int(j.get("refresh_token_expires_in", 5184000))
    t["updated_at"] = now
    _write_private(TOKEN, t)
    return t


def auth_url():
    key, _, redirect = _conf()
    q = {"client_id": key, "redirect_uri": redirect, "response_type": "code", "scope": "talk_message"}
    return AUTH_URL + "?" + urllib.parse.urlencode(q)


def exchange_code(code):
    key, sec, redirect = _conf()
    data = {"grant_type": "authorization_code", "client_id": key, "redirect_uri": redirect, "code": code}
    if sec:
        data["client_secret"] = sec
    return _save_tokens(_post(TOKEN_URL, data))


def auth_interactive(timeout=600):
    """로컬 서버로 리다이렉트 코드를 받는다. 링크를 출력하고 기다린다."""
    from http.server import BaseHTTPRequestHandler, HTTPServer
    _, _, redirect = _conf()
    u = urllib.parse.urlparse(redirect)
    got = {}

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            got["code"] = (qs.get("code") or [None])[0]
            got["error"] = (qs.get("error_description") or qs.get("error") or [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = "카카오 연결 완료. 이 창은 닫아도 돼." if got["code"] else f"실패: {got['error']}"
            self.wfile.write(msg.encode("utf-8"))

        def log_message(self, *a):
            pass

    srv = HTTPServer((u.hostname or "localhost", u.port or 80), H)
    srv.timeout = 5
    print("이 링크를 이 맥북 브라우저에서 열고 동의해 줘:\n" + auth_url(), flush=True)
    end = time.time() + timeout
    while "code" not in got and time.time() < end:
        srv.handle_request()
    srv.server_close()
    if not got.get("code"):
        raise KakaoError(f"인증 코드 못 받음: {got.get('error') or '시간 초과'}")
    exchange_code(got["code"])
    return True


def access_token():
    """유효한 access 토큰. 만료 임박이면 refresh 로 갱신."""
    try:
        t = _read(TOKEN)
    except Exception:
        raise KakaoError("토큰 없음 — 최초 인증(auth) 필요")
    if t.get("access_expires_at", 0) > time.time():
        return t["access_token"]
    if not t.get("refresh_token") or t.get("refresh_expires_at", 0) < time.time():
        raise KakaoError("refresh 토큰 만료 — 재인증(auth) 필요")
    key, sec, _ = _conf()
    data = {"grant_type": "refresh_token", "client_id": key, "refresh_token": t["refresh_token"]}
    if sec:
        data["client_secret"] = sec
    return _save_tokens(_post(TOKEN_URL, data), old=t)["access_token"]


def refresh_days_left():
    try:
        t = _read(TOKEN)
        return (t.get("refresh_expires_at", 0) - time.time()) / 86400
    except Exception:
        return None


def send_me(text, link="https://sell.smartstore.naver.com"):
    """나와의 채팅으로 텍스트 발송(최대 200자 — 넘으면 자른다)."""
    text = str(text)
    if len(text) > 200:
        text = text[:197] + "…"
    tpl = {"object_type": "text", "text": text, "link": {"web_url": link, "mobile_web_url": link}}
    j = _post(SEND_URL, {"template_object": json.dumps(tpl, ensure_ascii=False)},
              {"Authorization": f"Bearer {access_token()}"})
    if j.get("result_code") != 0:
        raise KakaoError(f"발송 실패: {j}")
    return True


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "test"
    try:
        if cmd == "auth":
            auth_interactive()
            print("인증 완료 — 토큰 저장:", TOKEN)
        elif cmd == "url":
            print(auth_url())
        else:
            send_me("✅ 용팀장 자동작업 알림 시험 메시지야. 이게 보이면 카톡 연결 끝.")
            print("발송 완료")
    except KakaoError as e:
        print("[kakao] " + str(e), file=sys.stderr)
        sys.exit(1)
