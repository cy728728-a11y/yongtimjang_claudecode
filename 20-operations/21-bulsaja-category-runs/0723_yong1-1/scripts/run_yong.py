#!/usr/bin/env python3
"""용쌤 서버(bulsaja-yongssaem) 라우팅 래퍼.

~/.claude.json 의 mcpServers['bulsaja-yongssaem'] 에서 url+토큰을 읽어
BULSAJA_MCP_URL / BULSAJA_MCP_TOKEN 환경변수로 넣고 하위 명령을 실행한다.
(bulsaja_mcp.py 의 load_config() 가 환경변수를 최우선으로 읽음)
토큰 값은 절대 출력하지 않는다.

사용: python run_yong.py <명령> [인자...]
예:  python run_yong.py C:/.../python.exe bulsaja_mcp.py probe
"""
import json
import os
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def find_server(obj):
    """~/.claude.json 어디에 있든 mcpServers['bulsaja-yongssaem'] 를 찾는다."""
    if isinstance(obj, dict):
        ms = obj.get("mcpServers")
        if isinstance(ms, dict) and "bulsaja-yongssaem" in ms:
            return ms["bulsaja-yongssaem"]
        for v in obj.values():
            r = find_server(v)
            if r:
                return r
    return None


def main():
    try:
        path = os.path.expanduser("~/.claude.json")
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
        server = find_server(cfg)
        if not server:
            print("[오류] ~/.claude.json 에서 bulsaja-yongssaem 서버를 찾지 못함")
            sys.exit(1)
        auth = (server.get("headers") or {}).get("Authorization", "")
        if not auth:
            print("[오류] bulsaja-yongssaem 토큰 없음")
            sys.exit(1)
        env = {
            **os.environ,
            "BULSAJA_MCP_URL": server["url"],
            "BULSAJA_MCP_TOKEN": auth,
            "BULSAJA_ACCOUNT": "bulsaja-yongssaem",  # 썸네일 완료 대장 계정 키
            "PYTHONIOENCODING": "utf-8",
        }
        proc = subprocess.run(sys.argv[1:], env=env)
        sys.exit(proc.returncode)
    except Exception as e:
        print(f"[오류] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
