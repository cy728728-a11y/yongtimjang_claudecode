#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""쿠팡 트랙 라우터 (Phase 7 / CP-01~04) — **트랙 소유 파일이다.**

    POST /jobs/coupang/preview    쿠팡 후보 뽑기 잡 접수 (쓰기 0)       [07-05]
    POST /jobs/coupang/commit     쿠팡 복사 잡 접수 (잡 id + 타이핑 건수) [07-05]

**이 파일은 07-05 가 채운다.** 공유 파일(jobs.py · routes/jobs.py · main.py · board.html ·
board.js · _job_status.html)은 07-01 에서만 고친다(D-19). 트랙 플랜은 여기와
`static/coupang.js` · 트랙 템플릿만 만진다.

요청 모델에 게이트 기준·skip·strict 필드를 두지 마라(L-04 · D-15) — 기준은 CLI 기본값이 정본이다.
결과 조각 디스패치는 `결과표` 에 등록한다(기존 kind 키는 덮이지 않는다 · T-07-06).
"""
from typing import Callable

from fastapi import APIRouter

router = APIRouter()

# kind → (템플릿 조각 이름, ctx 함수). 07-05 가 coupang_preview · coupang_commit 을 여기 등록한다.
결과표: dict[str, tuple[str, Callable[[dict], dict]]] = {}
