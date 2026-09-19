#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""작업(잡) 라우터 — 자리만 먼저 판다.

Plan 01-05 가 `POST /jobs/*` 와 `GET /jobs/{id}/stream` 을 채운다.

**모든 작업 생성은 POST 다 — GET 으로 만들면 Origin 방어가 통째로 무력화된다.**
교차 사이트 단순 GET(`<img src="http://127.0.0.1:.../jobs/bids/run">`)에는
`Origin` 헤더가 없어서 `security.guard` 가 아무것도 걸러내지 못한다. 즉 아무 웹페이지나
열어 두기만 해도 내 광고 입찰가가 올라갈 수 있다. 여기에 `@router.get` 으로
부수효과 있는 엔드포인트를 추가하는 순간 SAFE-01 이 죽는다(T-1-01b).

읽기 전용 조회(`GET /jobs/{id}/stream` · `/result`)는 GET 이어도 된다 —
서버 상태를 바꾸지 않기 때문이다. 판단 기준은 "메서드 이름"이 아니라
**"이 요청이 디스크·광고 API·잡 레지스트리를 바꾸는가"** 다.

이 파일이 지금 비어 있는 이유: `main.py` 가 라우터를 등록하는 자리를 미리 확정해 두면
Plan 01-05 가 `main.py` 를 다시 건드리지 않고 이 파일만 채운다(인터페이스 우선 순서).
"""
from fastapi import APIRouter

router = APIRouter()
