#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""썸네일 트랙 라우터 (Phase 7 / THUMB-02) — **트랙 소유 파일이다.**

    POST /jobs/thumb/estimate     썸네일 견적 잡 접수 (크레딧 0)       [07-04]
    POST /jobs/thumb/approve      견적 승인 → 그룹 run-dir 에 승인 파일  [07-04]
    GET  /thumb/{id}/result       결과 조각                           [07-04]

**이 파일은 07-04 가 채운다.** 공유 파일(jobs.py · routes/jobs.py · main.py · board.html ·
board.js · _job_status.html)은 07-01 에서만 고친다(D-19) — 두 트랙이 같은 레지스트리를 동시에
고치는 충돌을 없애려는 것이다. 트랙 플랜은 여기와 `static/thumb.js` · 트랙 템플릿만 만진다.

결과 조각 디스패치는 `결과표` 에 등록한다. `routes/jobs.get_job_result` 가 지연 import 로
병합하되 **기존 kind 키를 덮지 못한다**(T-07-06).
"""
from typing import Callable

from fastapi import APIRouter

router = APIRouter()

# kind → (템플릿 조각 이름, ctx 함수). 07-04 가 thumb_estimate 를 여기 등록한다.
결과표: dict[str, tuple[str, Callable[[dict], dict]]] = {}
