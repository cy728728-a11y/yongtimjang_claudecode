#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""셀러 관제탑 웹앱 — FastAPI 조립부.

    GET  /            보드 셸. 쿠키가 맞아야 열린다                    [읽기]
    GET  /healthz     서버 생존 확인. 토큰·쿠키 불필요                 [읽기]
    (POST /jobs/*)    작업 생성·실행. Plan 01-05 가 채운다             [쓰기 — 토큰 필요]

**GET 은 절대 서버 상태를 바꾸지 않는다.** 이건 취향이 아니라 방어의 전제다 —
교차 사이트 단순 GET(`<img src>`·`<script src>`)에는 Origin 헤더가 없어서,
부수효과가 있는 GET 을 하나라도 만들면 `security.guard` 의 Origin 층이
통째로 무력화된다(T-1-01b). 작업 생성은 예외 없이 POST 다.

조립 순서에 의미가 있다:

    GZip          → 보드 응답 수백 KB 를 줄인다 (실측 547KB → 95KB)
    TrustedHost   → Host 화이트리스트. DNS rebinding 을 400 에서 끊는다
    security.guard→ 쓰기 메서드 전용 Origin + 부팅 토큰

`add_middleware` 는 앞에 끼워 넣으므로 **나중에 붙인 것이 바깥**이다.
즉 실제 실행 순서는 guard → TrustedHost → GZip → 라우팅이고,
이 배치가 RESEARCH §4.1 에서 curl 6케이스를 통과한 그 배치다.
"""
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from webapp import security, settings

# 경로는 이 파일 기준으로 잡는다. 절대경로를 박으면 다른 PC 에서 조용히 깨진다.
BASE = Path(__file__).resolve().parent

# Jinja2 자동 이스케이프에 기댄다. **`| safe` 필터를 쓰지 마라** —
# 상품명에 중국어 원문·특수문자가 섞여 들어온다(T-1-17). grep 가드가 감시한다.
templates = Jinja2Templates(directory=str(BASE / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """기동 시 붙여넣을 URL 한 줄을 찍는다. 이 줄이 사실상의 로그인 화면이다."""
    conc = os.environ.get("WEB_CONCURRENCY")
    if conc is not None and conc != "1":
        # Pitfall 9 — 워커가 갈라지면 잡 레지스트리와 SSE 구독자 집합이 프로세스별로
        # 나뉜다. 잡을 띄운 워커와 스트림 요청을 받은 워커가 다르면 진행 로그가 안 뜬다.
        # 재현이 어려운 "가끔 안 보임" 버그로 나타나므로 기동 때 크게 경고한다.
        print(f"[경고] WEB_CONCURRENCY={conc} — 워커는 반드시 1이어야 한다. "
              f"진행 로그가 간헐적으로 안 뜬다")
    print(f"→ http://127.0.0.1:{settings.PORT}/?t={security.BOOT_TOKEN}")
    yield


# docs_url/redoc_url 을 끈다 — 1인 로컬 도구에 OpenAPI UI 는 공격면만 늘린다.
# openapi_url 도 끈다: docs 만 끄면 `/openapi.json` 이 **토큰 없이 열린 채로 남아**
# 전체 라우트 목록과 스키마를 그대로 내준다(GET 이라 guard 도 안 탄다).
# 스키마 자체는 `app.openapi()` 로 여전히 만들 수 있어 테스트는 영향을 안 받는다.
# debug 도 켜지 않는다(기본 False): 500 응답에 트레이스백을 실으면 ASVS V7 위반이다.
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

# 부팅 토큰을 앱에 매달아 둔다 — 테스트(conftest.client)와 라우터가 여기서 집는다.
app.state.boot_token = security.BOOT_TOKEN

app.add_middleware(GZipMiddleware, minimum_size=1000)
# allowed_hosts 에 **포트를 적지 마라** — 미들웨어가 포트를 떼고 매칭한다.
# 와일드카드("*")는 미들웨어를 끄는 것과 같다.
app.add_middleware(TrustedHostMiddleware,
                   allowed_hosts=["127.0.0.1", "localhost"], www_redirect=False)
app.middleware("http")(security.guard)

app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")

# 라우터 등록은 health → board → jobs 순. 라우터 모듈을 여기서 import 하므로
# 반대 방향(라우터 → main.templates)은 **핸들러 안에서 지연 import** 한다
# (`paths.freshness()` 가 settings 를 지연 import 하는 것과 같은 이유).
from webapp.routes import board, health, jobs  # noqa: E402

app.include_router(health.router)
app.include_router(board.router)
app.include_router(jobs.router)
