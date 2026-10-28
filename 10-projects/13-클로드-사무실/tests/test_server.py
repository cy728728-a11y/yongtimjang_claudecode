"""server.py 시험 — 포트 0 으로 스레드에 띄우고 http.client 로 두드린다"""
import http.client
import json
import threading

import pytest

import server
import snapshot
from conftest import user


@pytest.fixture
def running(claude_home, tmp_path):
    claude_home.write("aaaa1111-0000", [{"type": "custom-title", "customTitle": "옵션 정리"}, user("x")], ago=10)
    claude_home.write("bbbb2222-0000", [user("y")], ago=20)
    cfg = {"visibleHours": 6, "workingSeconds": 90, "hide": [], "robots": {"robots": []}, "lang": "ko"}
    httpd = server.create_server(0, make_snapshot=lambda: snapshot.build_snapshot(cfg=cfg), office_cfg=cfg)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def req(port, path, method="GET", host=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.putrequest(method, path, skip_host=True)
    c.putheader("Host", host or f"127.0.0.1:{port}")
    c.endheaders()
    r = c.getresponse()
    body = r.read()
    c.close()
    return r, body


def test_api_office(running):
    r, body = req(running, "/api/office")
    assert r.status == 200
    assert r.getheader("Cache-Control") == "no-store"
    assert r.getheader("X-Frame-Options") == "DENY"
    snap = json.loads(body)
    for k in ("version", "now", "hooks", "demo", "people", "robots"):
        assert k in snap
    assert len(snap["people"]) == 2
    assert {p["name"] for p in snap["people"]} == {"옵션 정리", "bbbb2222"}


def test_localhost_host_ok(running):
    r, _ = req(running, "/api/health", host=f"localhost:{running}")
    assert r.status == 200


def test_api_config_health(running):
    r, body = req(running, "/api/config")
    assert r.status == 200 and json.loads(body)["lang"] == "ko"
    r, body = req(running, "/api/health")
    h = json.loads(body)
    assert h["ok"] is True and h["demo"] is False and isinstance(h["pid"], int)


def test_evil_host_403(running):
    r, _ = req(running, "/api/office", host="evil.com")
    assert r.status == 403
    r, _ = req(running, "/api/office", host="127.0.0.1:1")
    assert r.status == 403


def test_post_405(running):
    r, _ = req(running, "/api/office", method="POST")
    assert r.status == 405 and r.getheader("Allow") == "GET"


def test_path_traversal_404(running):
    for p in ("/../server/server.py", "/%2e%2e/server/server.py", "/..%5cserver.py", "/index.html%00"):
        r, _ = req(running, p)
        assert r.status == 404, p


def test_index_and_static(running):
    r, body = req(running, "/")
    assert r.status == 200 and b"<html" in body.lower()
    assert r.getheader("Content-Type").startswith("text/html")
    etag = r.getheader("ETag")
    assert etag
    c = http.client.HTTPConnection("127.0.0.1", running, timeout=5)
    c.request("GET", "/index.html", headers={"If-None-Match": etag})
    r2 = c.getresponse()
    r2.read()
    c.close()
    assert r2.status == 304
    r, _ = req(running, "/office-view.js")
    assert r.status == 200


def test_not_whitelisted_404(running):
    for p in ("/server.py", "/nope.html", "/office/", "/api/other"):
        r, _ = req(running, p)
        assert r.status == 404, p
