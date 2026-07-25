#!/usr/bin/env python3
"""불사자 원격 HTTP MCP transport (대량처리용 저수준 클라이언트).

불사자 MCP는 로컬이 아니라 원격 Streamable HTTP MCP 서버다
(url + Bearer 토큰이 ~/.claude.json 의 mcpServers.bulsaja 에 있음).
무거운 도구(workdata ~40KB/건 등)를 파이썬에서 JSON-RPC 로 직접 호출하면
응답을 스크립트 안에서 소비하고 요약만 남겨, 대화 컨텍스트를 태우지 않고
수백~수천 건을 처리할 수 있다.

이 모듈은 **transport 만** 담는다(config 로드·JSON-RPC·SSE 파싱·재시도·세션수명).
도메인 헬퍼(workdata/category_preview/category_commit 등 업무로직)는 소비 스킬이
이 BulsajaMCP 를 상속해 얹는다.

보안: Bearer 토큰은 하드코딩하지 않고 ~/.claude.json 에서 런타임 로드한다.
      토큰 값은 절대 stdout/로그로 출력하지 않는다.
"""
import json
import os
import time

import requests  # venv 에 존재 (2.34.x)

DEFAULT_PROTOCOL = "2025-06-18"
CLIENT_INFO = {"name": "bulsaja-bulk", "version": "1.0"}
# 재시도 대상 HTTP 상태
_RETRY_STATUS = {429, 500, 502, 503, 504}
# ~/.claude.json 의 mcpServers 키. "bulsaja"=용팀장 계정, "bulsaja-yongssaem"=용쌤 계정.
DEFAULT_SERVER = "bulsaja-yongssaem"


def load_config():
    """~/.claude.json 의 mcpServers[DEFAULT_SERVER] 에서 url + Authorization 로드.
    환경변수 BULSAJA_MCP_URL / BULSAJA_MCP_TOKEN 가 있으면 우선.
    반환: (url, authorization_header_value). 토큰 값은 호출부에서도 출력 금지.
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
            b = obj.get(DEFAULT_SERVER)
            if isinstance(b, dict) and "url" in b and not found:
                found["url"] = b["url"]
                found["auth"] = (b.get("headers") or {}).get("Authorization", "")
            for v in obj.values():
                walk(v)

    walk(cfg)
    if not found:
        raise RuntimeError(f"~/.claude.json 에서 mcpServers.{DEFAULT_SERVER} 를 찾지 못했습니다.")
    return url or found["url"], auth or found["auth"]


def _parse_message(resp):
    """MCP 응답(JSON 또는 SSE text/event-stream)에서 JSON-RPC 메시지 dict 반환.
    SSE 는 'data:' 라인들을 이어붙여 파싱. 여러 data 블록이면 마지막 유효본.

    주의: 서버가 Content-Type 에 charset 을 안 붙여 requests 가 latin-1 로
    잘못 디코딩(한글 깨짐)하고, 그 깨진 바이트를 str.splitlines() 가 줄바꿈으로
    오인해 JSON 을 조각낸다. 그래서 반드시 content 를 UTF-8 로 직접 디코딩하고
    '\\n' 으로만 분할한다.
    """
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
        # 응답(result/error 있는 것) 우선, 없으면 마지막
        for m in reversed(msgs):
            if isinstance(m, dict) and ("result" in m or "error" in m):
                return m
        return msgs[-1] if msgs else {}
    # 순수 JSON
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
    """불사자 원격 HTTP MCP 세션 transport. open() → call_tool() → close().

    도메인 헬퍼(workdata 등)는 소비 스킬이 상속해 얹는다.
    """

    def __init__(self, url=None, auth=None, timeout=60, sleep=0.4, max_retries=4):
        if url is None or auth is None:
            u, a = load_config()
            url = url or u
            auth = auth or a
        self.url = url
        self._auth = auth  # 절대 로그로 내보내지 않는다
        self.timeout = timeout
        self.sleep = sleep
        self.max_retries = max_retries
        self.session_id = None
        self.protocol = DEFAULT_PROTOCOL
        self._id = 0
        self._http = requests.Session()

    # ---- 저수준 전송 -------------------------------------------------
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
        """JSON-RPC 페이로드 POST. 재시도(429/5xx/네트워크) 지수백오프.
        expect_reply=False 면 알림(notification) — 본문 파싱 안 함.
        반환: (message_dict_or_None, response).
        """
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

            # 세션ID 캡처(initialize 응답 등)
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
                    "`! gws` 아님. 불사자 토큰은 ~/.claude.json 재설정 필요."
                )
            if resp.status_code >= 400:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")

            if not expect_reply:
                # 통지도 본문을 소비해야 keep-alive 커넥션이 오염되지 않는다
                # (미소비 SSE 응답이 다음 요청의 파싱을 깨뜨림).
                _ = resp.content
                return None, resp
            msg = _parse_message(resp)
            return msg, resp
        raise RuntimeError(f"요청 실패(재시도 {self.max_retries}회 초과): {last_err}")

    def _next_id(self):
        self._id += 1
        return self._id

    # ---- 세션 수명주기 -----------------------------------------------
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
            self.protocol = sv  # 서버가 고른 버전으로 정렬
        # initialized 통지
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
        """tools/call. 응답의 structuredContent 또는 content(text) 를 파싱해 반환.
        대용량 원본은 여기서 소비되고, 호출부는 요약만 취한다.
        JSON-RPC error 는 예외로 승격.
        """
        payload = {
            "jsonrpc": "2.0", "id": self._next_id(), "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        msg, _ = self._post(payload)
        if msg.get("error"):
            raise RuntimeError(f"{name} 호출 오류: {msg['error']}")
        result = msg.get("result", {})
        # MCP tools/call 결과: content[] (type=text) + 선택적 structuredContent
        if "structuredContent" in result:
            return result["structuredContent"]
        return extract_tool_payload(result)

    def close(self):
        try:
            if self.session_id:
                # DELETE 로 세션 종료 (서버가 지원하면)
                self._http.delete(self.url, headers=self._headers(), timeout=10)
        except Exception:
            pass
        finally:
            self._http.close()
