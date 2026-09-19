#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""생존 확인 창.

    GET /healthz   서버가 살았는지 + 판정 회차가 몇 개 보이는지      [읽기]

**토큰도 쿠키도 안 본다.** 화면이 고장났을 때 "서버가 죽은 건가 화면만 깨진 건가"를
가르는 유일한 창이라, 이게 인증에 묶이면 진상 파악이 불가능해진다.
노출되는 건 회차 **개수** 하나뿐이다 — 경로도 계정도 안 나간다.
"""
from fastapi import APIRouter

from webapp import paths

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict:
    """`async def` 가 아니라 `def` 다.

    `scan_run_dirs()` 가 디스크를 훑는 **동기 IO** 라, async 로 선언하면 이벤트 루프를
    막아 그 순간 모든 SSE 스트림이 같이 멈춘다. `def` 로 두면 Starlette 이
    스레드풀로 보낸다.
    """
    try:
        n = len(paths.scan_run_dirs())
    except Exception:
        n = 0
    return {"ok": True, "run_dirs": n}
