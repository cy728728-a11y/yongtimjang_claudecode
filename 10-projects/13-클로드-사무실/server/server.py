"""클로드 사무실 로컬 HTTP 서버 — 127.0.0.1 에만 붙는 보기 전용 화면.

원본 server/server.mjs (MIT) 를 Python 표준 라이브러리로 옮겼다.
사용법: python3 server/server.py [--port N]
라우트: GET /api/office · /api/config · /api/health · web/ 정적 파일(시작 때 만든 화이트리스트만)
"""
import argparse
import errno
import json
import os
import re
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import snapshot  # noqa: E402

APP = "claude-office"
VERSION = "0.1.0-py"
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
BIND = "127.0.0.1"  # Tailscale 바인딩은 3단계
SNAPSHOT_MEMO_SEC = 1.0  # 탭 여러 개가 동시에 물어도 1초에 한 번만 조립
MAX_STATIC = 5000

TYPES = {
    ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8", ".txt": "text/plain; charset=utf-8",
    ".svg": "image/svg+xml", ".webp": "image/webp", ".png": "image/png", ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg", ".gif": "image/gif", ".ico": "image/x-icon", ".woff2": "font/woff2",
    ".woff": "font/woff", ".glb": "model/gltf-binary", ".gltf": "model/gltf+json",
    ".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".wav": "audio/wav", ".map": "application/json",
}
BASE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cross-Origin-Resource-Policy": "same-origin",
}
_BAD_PATH = re.compile(r"\.\.|%2e|\\|%5c|%00", re.IGNORECASE)


def scan_web(web_dir=WEB_DIR):
    """web/ 를 훑어 내줄 파일 목록 {'/office/frog.webp': 절대경로}. '_'·'.' 이름과 링크는 뺀다"""
    files = {}

    def walk(d, prefix):
        try:
            ents = sorted(os.scandir(d), key=lambda e: e.name)
        except Exception:
            return
        for e in ents:
            if len(files) >= MAX_STATIC:
                return
            if e.name.startswith("_") or e.name.startswith("."):
                continue
            try:
                if e.is_symlink():
                    continue
                if e.is_dir(follow_symlinks=False):
                    walk(e.path, f"{prefix}{e.name}/")
                elif e.is_file(follow_symlinks=False) and Path(e.name).suffix.lower() in TYPES:
                    files[f"{prefix}{e.name}"] = e.path
            except Exception:
                continue

    walk(str(web_dir), "/")
    return files


def create_server(port=0, web_dir=WEB_DIR, make_snapshot=None, office_cfg=None):
    """ThreadingHTTPServer 를 만들어 127.0.0.1:port 에 바인딩한다(serve_forever 는 호출자가)"""
    files = scan_web(web_dir)
    make = make_snapshot or snapshot.build_snapshot
    cfg = office_cfg if office_cfg is not None else snapshot.load_office_config()
    memo = {"at": 0.0, "value": None}
    lock = threading.Lock()

    def get_snapshot():
        with lock:
            now = time.time()
            if memo["value"] is None or now - memo["at"] >= SNAPSHOT_MEMO_SEC:
                memo["value"] = make()
                memo["at"] = now
            return memo["value"]

    class Handler(BaseHTTPRequestHandler):
        server_version = APP
        sys_version = ""

        def log_message(self, fmt, *args):
            # 3초 폴링 소음 줄이기 — /api/office 200 은 찍지 않는다
            try:
                msg = fmt % args
                if '"GET /api/office' in msg and '" 200 ' in msg:
                    return
                sys.stderr.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}\n")
            except Exception:
                pass

        def _send(self, code, body, ctype="text/plain; charset=utf-8", extra=None, cache="no-store"):
            data = body if isinstance(body, bytes) else str(body).encode("utf-8")
            self.send_response(code)
            for k, v in BASE_HEADERS.items():
                self.send_header(k, v)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", cache)
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def _json(self, code, obj):
            self._send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

        def _host_ok(self):
            # DNS 리바인딩 방지 — 남의 도메인 이름으로 들어온 요청은 거절
            port = self.server.server_address[1]
            host = str(self.headers.get("Host") or "").lower()
            return host in (f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}")

        def _guard(self):
            """공통 검사. 통과하면 True"""
            if not self._host_ok():
                self._send(403, "forbidden")
                return False
            if self.command != "GET":
                self._send(405, "method not allowed", extra={"Allow": "GET"})
                return False
            return True

        def _static(self, abs_path):
            try:
                st = os.stat(abs_path)
                etag = f'W/"{st.st_size}-{int(st.st_mtime * 1000)}"'
                ctype = TYPES[Path(abs_path).suffix.lower()]
                if self.headers.get("If-None-Match") == etag:
                    self.send_response(304)
                    for k, v in BASE_HEADERS.items():
                        self.send_header(k, v)
                    self.send_header("ETag", etag)
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    return
                with open(abs_path, "rb") as f:
                    data = f.read()
                self._send(200, data, ctype, extra={"ETag": etag}, cache="no-cache")
            except Exception:
                self._send(404, "not found")

        def do_GET(self):
            try:
                if not self._guard():
                    return
                raw = str(self.path or "/")
                p = raw.split("?", 1)[0]
                if _BAD_PATH.search(p):
                    return self._send(404, "not found")  # 경로조작
                try:
                    route = unquote(p, errors="strict")
                except Exception:
                    return self._send(404, "not found")
                if route == "/api/office":
                    try:
                        return self._json(200, get_snapshot())
                    except Exception:
                        sys.stderr.write(f"snapshot failed:\n{traceback.format_exc()}\n")
                        return self._json(500, {"error": "snapshot failed"})
                if route == "/api/config":
                    return self._json(200, {"lang": cfg.get("lang", "ko"), "version": VERSION})
                if route == "/api/health":
                    return self._json(200, {"ok": True, "app": APP, "version": VERSION, "demo": False,
                                            "pid": os.getpid()})
                abs_path = files.get("/index.html" if route == "/" else route)
                if not abs_path:
                    return self._send(404, "not found")
                return self._static(abs_path)
            except Exception:
                sys.stderr.write(f"request failed:\n{traceback.format_exc()}\n")
                try:
                    self._send(500, "error")
                except Exception:
                    pass

        def _not_get(self):
            try:
                if not self._host_ok():
                    return self._send(403, "forbidden")
                self._send(405, "method not allowed", extra={"Allow": "GET"})
            except Exception:
                pass

        do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_HEAD = _not_get

    httpd = ThreadingHTTPServer((BIND, port), Handler)
    httpd.daemon_threads = True
    return httpd


def resolve_port(arg_port, cfg):
    """포트: --port > OFFICE_PORT > office.json"""
    if arg_port:
        return arg_port
    env = os.environ.get("OFFICE_PORT")
    if env:
        try:
            v = int(env)
            if 1 <= v <= 65535:
                return v
        except ValueError:
            pass
        print(f"OFFICE_PORT 값이 이상해서 무시한다: {env}", file=sys.stderr)
    return int(cfg.get("port", 4778))


def main(argv=None):
    ap = argparse.ArgumentParser(description="클로드 사무실 데이터 서버(보기 전용, 127.0.0.1)")
    ap.add_argument("--port", type=int, default=None)
    args = ap.parse_args(argv)
    if args.port is not None and not (1 <= args.port <= 65535):
        print(f"잘못된 포트: {args.port}", file=sys.stderr)
        return 1
    cfg = snapshot.load_office_config()
    port = resolve_port(args.port, cfg)
    try:
        httpd = create_server(port, office_cfg=cfg)
    except OSError as e:
        if e.errno == errno.EADDRINUSE:
            print(f"포트 {port} 를 이미 다른 프로그램이 쓰고 있다. --port 나 OFFICE_PORT 로 바꿔라.", file=sys.stderr)
        else:
            print(f"서버를 못 띄웠다: {e}", file=sys.stderr)
        return 1
    print(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {APP} {VERSION} listening on http://{BIND}:{port}/", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
