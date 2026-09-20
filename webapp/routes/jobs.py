#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""작업(잡) 라우터 — `webapp/jobs.py` 를 얇게 감싼다.

    POST /jobs/prep        새로 수집 (계정당 ~3분, 쓰기 가드를 탄다)    [쓰기 — 토큰 필요]
    POST /jobs/run         판정 다시 (디스크만, 초 단위)                [쓰기 — 토큰 필요]
    GET  /jobs/{id}        작업 상태 조각 (2초 폴링용)                  [읽기 — 쿠키]
    GET  /jobs/{id}/stream 진행 로그 SSE (전량 재생 + tail)             [읽기 — 쿠키]
    GET  /jobs             최근 작업 목록                               [읽기 — 쿠키]

**모든 작업 생성은 POST 다 — GET 으로 만들면 Origin 방어가 통째로 무력화된다.**
교차 사이트 단순 GET(`<img src="http://127.0.0.1:.../jobs/bids/run">`)에는
`Origin` 헤더가 없어서 `security.guard` 가 아무것도 걸러내지 못한다. 즉 아무 웹페이지나
열어 두기만 해도 내 광고 입찰가가 올라갈 수 있다. 여기에 `@router.get` 으로
부수효과 있는 엔드포인트를 추가하는 순간 SAFE-01 이 죽는다(T-1-01b).
`webapp/tests/security_curl.sh` 의 V-SAFE-01d 가 이 파일의 GET 핸들러 본문을 실제로
훑어서 기계로 집행한다 — 그래서 **GET 핸들러는 이 파일 맨 아래**에 모아 둔다.

**핸들러는 얇다.** 작업을 만드는 판단은 전부 `jobs.create_job` 안에 있다(D-17 / ENG-07):
회차 화이트리스트도, 쓰기 잡 전역 가드도, 대상 파일 쓰기도 거기다. 여기서 하는 일은
요청 모델을 풀고, 예외를 상태코드로 번역하고, 화면 조각이나 JSON 을 고르는 것뿐이다.
v2 의 APScheduler 는 이 라우터를 거치지 않고 같은 함수를 직접 부른다.

**클라이언트가 작업 종류를 문자열로 넘기지 못한다.** 경로마다 kind 가 고정이고,
임의 argv 를 태우는 `argv_override`(합성 잡)는 여기서 아예 닿지 않는다 (T-1-23).

**핸들러는 `async def` 가 아니라 `def` 다 — 스트림 하나만 빼고.** SQLite 와 파일 IO 가
동기라서 async 로 두면 이벤트 루프를 막고, 그러면 진행 로그 스트림이 같이 멈춘다(T-1-28).
스트림만 async 인 이유는 그게 **오래 살아 있는 커넥션**이라 스레드풀 자리를 몇 분씩
차지하면 안 되기 때문이다. 그 안에서도 sqlite 는 직접 만지지 않는다(`logtail` 이
스레드로 밀어낸다).
"""
import json
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ValidationError
from sse_starlette import EventSourceResponse

from webapp import jobs, logtail, security
from webapp.argv import Alias

router = APIRouter()

# 화면에 내보내는 상태 필드 **화이트리스트**. 행을 통째로 돌려주지 않는다 —
# argv·log_path 같은 내부 경로는 화면이 쓸 일이 없고, 새 컬럼이 생겼을 때
# 자동으로 밖으로 새는 설계를 만들지 않는다 (SAFE-03 의 투영 관례).
공개필드 = ("id", "kind", "status", "exit_code", "started_at", "ended_at",
            "run_dir", "target_count", "elapsed_sec")


class JobReq(BaseModel):
    """작업 요청. 회차와 계정만 받는다 — 경로도, 작업 종류도 받지 않는다.

    `run_dir` 은 여기서 검증하지 않는다. `jobs.create_job` 안의
    `paths.run_dir_path()` 화이트리스트가 본다 — 입구가 늘어나도 한 곳에서 막히게.
    `accounts` 는 `webapp/argv.py` 의 `Alias` 패턴을 그대로 쓴다(영숫자·`_`·`-`).
    """

    run_dir: str | None = None
    accounts: list[Alias] = []


async def 요청_풀기(request: Request) -> JobReq:
    """JSON 과 폼 인코딩을 **둘 다** 받아 `JobReq` 로 만든다.

    htmx 는 기본이 `application/x-www-form-urlencoded` 라 `hx-post` 가 JSON 을 안 보낸다.
    JSON 만 받으면 버튼이 422 로 튕기고, 폼만 받으면 v2 스케줄러·`curl` 이 불편해진다.
    입력 모양을 둘 받되 **검증은 한 곳(Pydantic)** 에서 한다 — 그게 진짜 관문이다.

    폼을 `request.form()` 으로 풀지 않는다. Starlette 은 urlencoded 폼에도
    `python-multipart` 를 요구해서(실측: `AssertionError: The python-multipart library
    must be installed`) 의존성이 하나 늘어난다. 파일 업로드가 없는 화면에 멀티파트
    파서를 깔 이유가 없다 — stdlib `parse_qsl` 로 충분하고, 이게 정확히 필요한 만큼이다.
    """
    본문 = await request.body()
    ctype = request.headers.get("content-type", "")

    if not 본문:
        값 = {}
    elif "application/json" in ctype:
        try:
            값 = json.loads(본문)
        except Exception:
            raise HTTPException(status_code=400, detail="요청 본문이 JSON 이 아니다")
        if not isinstance(값, dict):
            raise HTTPException(status_code=400, detail="요청 본문은 객체여야 한다")
    else:
        쌍 = parse_qsl(본문.decode("utf-8", "replace"))
        값 = {"run_dir": next((v for k, v in 쌍 if k == "run_dir" and v), None),
              "accounts": [v for k, v in 쌍 if k == "accounts" and v]}

    try:
        return JobReq(**값)
    except ValidationError as e:
        # 트레이스백·모델 내부 구조를 화면에 싣지 않는다 (ASVS V7). 건수만 알린다.
        raise HTTPException(status_code=400,
                            detail=f"요청 값이 잘못됐다 ({len(e.errors())}건)")


def _투영(상태: dict) -> dict:
    return {k: 상태.get(k) for k in 공개필드}


def _응답(request: Request, 상태: dict, 전체: bool = True):
    """htmx 요청이면 HTML 조각을, 아니면 JSON 을 돌려준다.

    같은 엔드포인트가 두 모양을 내는 이유: 화면은 HTML 조각을 그대로 갈아끼우면
    되고(JS 0줄), 스케줄러·`curl` 은 JSON 이 편하다. 판단 기준은 htmx 가 붙이는
    `HX-Request` 헤더 하나다.

    **`전체` 가 조각의 크기를 가른다. 이게 SSE 와 폴링이 안 싸우게 하는 장치다.**
    작업을 새로 만들 때(POST)는 패널 전체를 준다 — 그래야 새 작업의 스트림이 열린다.
    2초 폴링(GET)에는 **상태 문단만** 준다: 폴링이 패널 전체를 갈아끼우면 그 안의
    SSE 커넥션이 2초마다 끊기고 다시 붙어, 로그가 계속 처음부터 다시 그려지고
    커넥션이 쌓인다(T-1-24). 폴링은 경과시간만 갱신하면 된다.
    """
    if not request.headers.get("hx-request"):
        return _투영(상태)

    from webapp.main import templates  # 지연 import — main 이 이 모듈을 먼저 부른다

    조각 = "_job_panel.html" if 전체 else "_job_status.html"
    return templates.TemplateResponse(request, 조각, {"job": 상태})


def _작업만들기(request: Request, kind: str, req: JobReq):
    """POST 핸들러 3줄의 공통부. **kind 는 호출부가 고정한다** — 요청에서 오지 않는다."""
    try:
        job_id = jobs.create_job(kind, run_dir=req.run_dir, accounts=req.accounts)
    except jobs.BusyError as e:
        # 409 = "지금은 안 된다". 400 이 아닌 이유: 요청이 틀린 게 아니라 때가 아니다.
        raise HTTPException(status_code=409,
                            detail=f"이미 도는 작업이 있다 — 끝나고 다시 눌러라 ({e})")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return _응답(request, jobs.job_status(job_id))


@router.post("/jobs/prep")
def post_prep(request: Request, req: JobReq = Depends(요청_풀기)):
    """새로 수집. 계정당 ~3분이 걸리지만 **호출은 즉시 돌아온다**.

    `prep` 은 광고를 바꾸지 않는다 — 소재·통계를 새로 받아올 뿐이다. 다만
    "광고 API 에 아무것도 쓰지 않는다" 라고 말하면 틀리다: 통계를 받으려고
    `POST /stat-reports` 로 리포트 잡을 만든다(OQ-4 확정). 광고 설정은 불변이다.
    """
    return _작업만들기(request, "prep", req)


@router.post("/jobs/run")
def post_run(request: Request, req: JobReq = Depends(요청_풀기)):
    """판정 다시. 이미 받아 둔 스냅샷으로 6규칙을 다시 매긴다 — 디스크만 만지고 초 단위다."""
    return _작업만들기(request, "run", req)


# ── 여기서부터 읽기 전용 ─────────────────────────────────────────────────────
# 아래 GET 들은 작업을 **만들지 않는다.** 상태를 읽어 화면에 옮길 뿐이다.
# 이 파일에서 GET 핸들러를 맨 아래 모아 두는 이유는 V-SAFE-01d 스캐너가
# GET 데코레이터 뒤의 본문을 훑기 때문이다 — 위쪽 POST 들과 섞으면 오탐이 난다.

@router.get("/jobs")
def get_jobs(request: Request):
    """최근 작업 20건. 화면이 고장났을 때 "뭐가 돌았나" 를 보는 창이다."""
    if not security.page_cookie_ok(request):
        return PlainTextResponse("토큰이 필요하다", status_code=403)
    return {"jobs": [_투영(j) for j in jobs.recent_jobs(20)]}


@router.get("/jobs/{job_id}")
def get_job(job_id: str, request: Request):
    """작업 상태 하나. 작업 패널이 2초마다 이걸 때린다.

    `elapsed_sec` 이 같이 나온다 — `bids --commit` 에는 진행률이 없어서(항목 수는
    알아도 CLI 가 몇 번째인지 알려주지 않는다) 화면은 **경과시간**으로 덮는다(OQ-3).
    """
    if not security.page_cookie_ok(request):
        return PlainTextResponse("토큰이 필요하다", status_code=403)
    상태 = jobs.job_status(job_id)
    if 상태 is None:
        raise HTTPException(status_code=404, detail="그런 작업이 없다")
    return _응답(request, 상태, 전체=False)


@router.get("/jobs/{job_id}/stream")
async def get_job_stream(job_id: str, request: Request):
    """진행 로그 SSE. 붙을 때마다 **처음부터** 흘리고 그 뒤를 tail 한다 (SC-03).

    **이 파일에서 유일한 `async def` 라우트다.** 수 분씩 살아 있는 커넥션이라
    스레드풀 자리를 차지하면 안 된다. 대신 이 안에서 sqlite·파일을 직접 만지지
    않는다 — `logtail.sse_generator` 가 blocking 호출을 스레드로 밀어낸다(T-1-28).

    **아무것도 쓰지 않는다.** `security_curl.sh` 의 V-SAFE-01d 가 GET 핸들러 본문을
    훑어 이걸 기계로 집행한다. 여기에 작업 생성이 끼어들면 Origin 방어가 통째로
    무너진다(T-1-01b) — 교차 사이트 단순 GET 에는 Origin 헤더가 없기 때문이다.

    `ping=15` 는 keepalive, `send_timeout=30` 은 죽은 클라이언트를 30초 넘게
    붙잡지 않기 위함이다. `Cache-Control: no-cache` 가 없으면 중간 캐시가 스트림을
    통째로 삼킨다(로컬엔 중간 캐시가 없지만, 이 헤더는 SSE 의 관례다).
    """
    if not security.page_cookie_ok(request):
        return PlainTextResponse("토큰이 필요하다", status_code=403)
    if jobs.job_status(job_id) is None:
        raise HTTPException(status_code=404, detail="그런 작업이 없다")

    return EventSourceResponse(
        logtail.sse_generator(job_id, request),
        ping=15, send_timeout=30,
        headers={"Cache-Control": "no-cache"})
