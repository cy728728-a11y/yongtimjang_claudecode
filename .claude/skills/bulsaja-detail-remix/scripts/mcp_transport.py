# -*- coding: utf-8 -*-
"""불사자 원격 HTTP MCP 저수준 전송 (vendored, 외부 의존 없음).

이 스킬을 다른 워크스페이스에 그대로 배포할 수 있도록, 원래 이 워크스페이스의
공용 라이브러리(`.claude/lib/eroomlib/bulsaja.py`)에 있던 transport 코드를
스킬 폴더 안으로 그대로 복사해 넣었다(2026-09-04, 수강생 배포용). 로직은 원본과
동일 — open() → call_tool() → close(). 도메인 헬퍼(find_product_id 등)는
bulsaja_client.py 에서 이 클래스를 상속해 얹는다.

보안: Bearer 토큰은 하드코딩하지 않고 매번 ~/.claude.json 에서 런타임 로드한다.
      토큰 값은 절대 로그로 내보내지 않는다.
"""
import json
import os
import time

import requests

DEFAULT_PROTOCOL = "2025-06-18"
CLIENT_INFO = {"name": "bulsaja-detail-remix", "version": "1.0"}
_RETRY_STATUS = {429, 500, 502, 503, 504}


def load_config(account_key):
    """~/.claude.json 의 mcpServers[account_key] 에서 url + Authorization 로드.
    환경변수 BULSAJA_MCP_URL / BULSAJA_MCP_TOKEN 이 있으면 우선.
    반환: (url, authorization_header_value).
    """
    url = os.environ.get("BULSAJA_MCP_URL")
    auth = os.environ.get("BULSAJA_MCP_TOKEN")
    if auth and not auth.lower().startswith("bearer "):
        auth = "Bearer " + auth
    if url and auth:
        return url, auth

    path = os.path.expanduser("~/.claude.json")
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)

    found = {}

    def walk(obj):
        if isinstance(obj, dict):
            ms = obj.get("mcpServers")
            if isinstance(ms, dict) and account_key in ms and not found:
                server = ms[account_key]
                found["url"] = server.get("url")
                found["auth"] = (server.get("headers") or {}).get("Authorization", "")
            for v in obj.values():
                walk(v)

    walk(cfg)
    if not found:
        raise RuntimeError(
            f"~/.claude.json 에서 mcpServers.{account_key} 를 찾지 못했습니다. "
            f"`claude mcp add --transport http --scope user {account_key} "
            "'<불사자 MCP 주소>' --header 'Authorization: Bearer <토큰>'` 로 먼저 등록하세요."
        )
    return url or found["url"], auth or found["auth"]


def _parse_message(resp):
    """MCP 응답(JSON 또는 SSE text/event-stream)에서 JSON-RPC 메시지 dict 반환."""
    ctype = resp.headers.get("Content-Type", "")
    text = resp.content.decode("utf-8", errors="replace")
    if "text/event-stream" in ctype:
        msgs = []
        buf = []
        for raw in text.split("\n"):
            line = raw.rstrip("\r")
            if line.startswith("data:"):
                buf.append(line[5:].lstrip())
            elif line == "":
                if buf:
                    try:
                        msgs.append(json.loads("\n".join(buf)))
                    except json.JSONDecodeError:
                        pass
                    buf = []
        if buf:
            try:
                msgs.append(json.loads("\n".join(buf)))
            except json.JSONDecodeError:
                pass
        for m in reversed(msgs):
            if isinstance(m, dict) and ("result" in m or "error" in m):
                return m
        return msgs[-1] if msgs else {}
    return json.loads(text) if text.strip() else {}


def extract_tool_payload(result):
    """tools/call result.content[] 에서 텍스트를 꺼내 JSON이면 파싱, 아니면 원문."""
    content = result.get("content") or []
    texts = [c.get("text", "") for c in content if c.get("type") == "text"]
    joined = "\n".join(t for t in texts if t)
    if not joined:
        return result
    try:
        return json.loads(joined)
    except json.JSONDecodeError:
        return {"_text": joined}


class BulsajaMCP:
    """불사자 원격 HTTP MCP 세션 transport. open() → call_tool() → close()."""

    def __init__(self, url=None, auth=None, timeout=60, sleep=0.4, max_retries=4):
        self.url = url
        self._auth = auth  # 절대 로그로 내보내지 않는다
        self.timeout = timeout
        self.sleep = sleep
        self.max_retries = max_retries
        self.session_id = None
        self.protocol = DEFAULT_PROTOCOL
        self._id = 0
        self._http = requests.Session()

    def _headers(self):
        h = {
            "Authorization": self._auth,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": self.protocol,
        }
        if self.session_id:
            h["Mcp-Session-Id"] = self.session_id
        return h

    def _post(self, payload, expect_reply=True):
        last_err = None
        for attempt in range(self.max_retries):
            try:
                resp = self._http.post(
                    self.url, headers=self._headers(),
                    data=json.dumps(payload).encode("utf-8"),
                    timeout=self.timeout,
                )
            except requests.RequestException as e:
                last_err = e
                time.sleep(self.sleep * (2 ** attempt))
                continue

            sid = resp.headers.get("Mcp-Session-Id")
            if sid:
                self.session_id = sid

            if resp.status_code in _RETRY_STATUS:
                last_err = RuntimeError(f"HTTP {resp.status_code}")
                time.sleep(self.sleep * (2 ** attempt))
                continue
            if resp.status_code == 401:
                raise RuntimeError(
                    "HTTP 401 인증 실패 — Bearer 토큰 만료/무효. "
                    "불사자 MCP 토큰을 다시 등록해야 합니다."
                )
            if resp.status_code >= 400:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")

            if not expect_reply:
                _ = resp.content
                return None, resp
            msg = _parse_message(resp)
            return msg, resp
        raise RuntimeError(f"요청 실패(재시도 {self.max_retries}회 초과): {last_err}")

    def _next_id(self):
        self._id += 1
        return self._id

    def open(self):
        init = {
            "jsonrpc": "2.0", "id": self._next_id(), "method": "initialize",
            "params": {
                "protocolVersion": self.protocol,
                "capabilities": {},
                "clientInfo": CLIENT_INFO,
            },
        }
        msg, _ = self._post(init)
        if msg.get("error"):
            raise RuntimeError(f"initialize 실패: {msg['error']}")
        result = msg.get("result", {})
        sv = result.get("protocolVersion")
        if sv:
            self.protocol = sv
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"},
                   expect_reply=False)
        return result

    def list_tools(self):
        msg, _ = self._post({"jsonrpc": "2.0", "id": self._next_id(),
                             "method": "tools/list", "params": {}})
        if msg.get("error"):
            raise RuntimeError(f"tools/list 실패: {msg['error']}")
        return msg.get("result", {}).get("tools", [])

    def call_tool(self, name, arguments):
        payload = {
            "jsonrpc": "2.0", "id": self._next_id(), "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        msg, _ = self._post(payload)
        if msg.get("error"):
            raise RuntimeError(f"{name} 호출 오류: {msg['error']}")
        result = msg.get("result", {})
        if "structuredContent" in result:
            return result["structuredContent"]
        return extract_tool_payload(result)

    def close(self):
        try:
            if self.session_id:
                self._http.delete(self.url, headers=self._headers(), timeout=10)
        except Exception:
            pass
        finally:
            self._http.close()
