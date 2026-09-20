#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""기동 안내 줄이 **파이프로도** 나오는지 — 실제 서버를 띄워서 본다.

왜 이 테스트가 따로 있나: 토큰은 서버 재시작마다 바뀌고 디스크에 안 남긴다(T-1-16).
그래서 기동 로그의 `→ http://127.0.0.1:<포트>/?t=<토큰>` 한 줄이 **유일한 입구**다.
이 줄이 안 나오면 서버는 멀쩡히 떠 있는데 아무도 못 들어간다.

그런데 이 고장은 tty 에서 절대 재현되지 않는다. tty 면 stdout 이 줄 단위 버퍼링이라
`print()` 가 바로 보인다. 파일 리다이렉트(`> ct-server.log`)나 파이프면 블록 버퍼링
(8KB)으로 바뀌고, 서버 프로세스는 끝나지 않으니 그 버퍼가 **영원히** 안 비워진다.
상시 기동 수단인 launchd LaunchAgent 가 정확히 그 경로(stdout → 파일)라, 손으로
터미널에서 띄워 보는 확인은 이 고장을 통과시킨다.

**소스에서 `flush=True` 를 grep 하는 식으로 짜지 않는다.** 그건 증상이 아니라 철자를
검사하는 것이라, 나중에 로거로 바꾸거나 출력 경로가 달라지면 테스트는 초록인데 입구는
막힌다. 여기서는 tty 가 아닌 파이프로 진짜 서버를 띄워 그 줄이 **실제로 읽히는지** 본다.
"""
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from webapp import paths

REPO = paths.repo_root()
기동토큰 = "bootprobe-토큰-확인용"
대기초 = 25.0


def _빈_포트() -> int:
    """지금 비어 있는 포트 하나. 8765 를 쓰면 사용자가 띄워 둔 서버와 충돌한다."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.skipif(not (REPO / ".venv-web" / "bin" / "python").exists(),
                    reason=".venv-web 이 없는 환경이다")
def test_기동_URL_이_파이프로도_보인다():
    """stdout 을 PIPE 로 받아(= tty 아님) 기동 안내 줄이 시간 안에 읽히는지 본다."""
    포트 = _빈_포트()

    env = dict(os.environ)
    env["CT_DEV_TOKEN"] = 기동토큰
    env["CT_PORT"] = str(포트)
    # **이게 핵심이다.** PYTHONUNBUFFERED 가 남아 있으면 flush=True 가 없어도 통과한다.
    # 그러면 이 테스트는 아무것도 지키지 않는 장식이 된다.
    env.pop("PYTHONUNBUFFERED", None)
    env.pop("WEB_CONCURRENCY", None)

    p = subprocess.Popen(
        ["bash", "webapp/run-webapp.sh"],
        cwd=str(REPO), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL, text=True, bufsize=1,
    )

    읽은줄: list[str] = []
    찾음 = threading.Event()

    def _읽기():
        try:
            for line in p.stdout:          # type: ignore[union-attr]
                읽은줄.append(line)
                if "?t=" in line:
                    찾음.set()
                    return
        except Exception:
            pass

    리더 = threading.Thread(target=_읽기, daemon=True)
    리더.start()

    try:
        찾음.wait(대기초)
        if not 찾음.is_set():
            p.terminate()
            try:
                에러 = p.stderr.read()      # type: ignore[union-attr]
            except Exception:
                에러 = ""
            if "Address already in use" in 에러 or "error while attempting to bind" in 에러:
                pytest.skip(f"포트 {포트} 가 그 사이 물렸다")
            # 값(토큰)을 그대로 찍지 않는다 — 어차피 테스트용 상수지만 관례를 지킨다
            pytest.fail(
                f"{대기초}초 안에 기동 안내 줄이 stdout 으로 안 나왔다. "
                f"stdout {len(읽은줄)}줄. print 에 flush=True 가 빠지면 "
                f"파이프·파일 리다이렉트에서 이 줄이 영영 안 나온다")

        본문 = "".join(읽은줄)
        assert f"?t={기동토큰}" in 본문, "안내 줄에 토큰이 없다"
        # 포트도 같이 확인한다 — CT_PORT 로 바인드 포트만 바뀌고 안내 URL 이 옛 포트에
        # 남으면, 사용자가 붙여넣은 주소가 아무 데도 안 닿는다.
        assert f"127.0.0.1:{포트}/" in 본문, "안내 줄의 포트가 실제 바인드 포트와 다르다"
    finally:
        p.terminate()
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait(timeout=10)
        for 스트림 in (p.stdout, p.stderr):
            try:
                스트림.close()              # type: ignore[union-attr]
            except Exception:
                pass


def test_CT_PORT_가_설정포트를_이긴다(monkeypatch):
    """바인드 포트와 Origin 화이트리스트가 **같은 값**에서 나오는지.

    둘이 갈라지면 서버는 9999 에 떠 있는데 8765 를 허용하고 8765 를 안내하는 상태가 된다.
    증상은 "모든 버튼이 403" 이라 원인을 엉뚱한 데서 찾게 된다.
    """
    from webapp import security, settings

    monkeypatch.setenv("CT_PORT", "9911")
    settings.reload()
    try:
        assert settings.PORT == 9911
        assert security.allowed_origins() == {
            "http://127.0.0.1:9911", "http://localhost:9911"}
    finally:
        monkeypatch.delenv("CT_PORT", raising=False)
        settings.reload()
