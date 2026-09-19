#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""셀러 관제탑 웹앱 — FastAPI 조립부.

    GET  /            보드 셸. 쿠키가 맞아야 열린다                    [읽기]
    GET  /healthz     서버 생존 확인. 토큰 불필요                      [읽기]

**GET 은 절대 서버 상태를 바꾸지 않는다.** 이게 규칙이 아니라 방어의 전제다 —
교차 사이트 단순 GET 에는 Origin 헤더가 없어서, 부수효과가 있는 GET 을 하나라도
만들면 `security.guard` 의 Origin 층이 통째로 무력화된다(T-1-01b).
작업 생성은 전부 POST 다.

(이 단계는 보안 3층과 앱 셸만 세운다. 라우터·템플릿은 Task 2 가 붙인다.)
"""
import secrets

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from webapp import security, settings

# docs_url/redoc_url 을 끈다 — 1인 로컬 도구에 OpenAPI UI 는 공격면만 늘린다.
# debug 도 켜지 않는다(기본 False): 500 응답에 트레이스백을 실으면 ASVS V7 위반이다.
app = FastAPI(docs_url=None, redoc_url=None)

# 부팅 토큰을 앱에 매달아 둔다 — 테스트(conftest.client)와 라우터가 여기서 집는다.
app.state.boot_token = security.BOOT_TOKEN

# 보드 응답이 수백 KB 다(실측 547KB → 95KB). 로컬이라도 렌더 체감이 달라진다.
app.add_middleware(GZipMiddleware, minimum_size=1000)
# allowed_hosts 에 **포트를 적지 마라** — 미들웨어가 포트를 떼고 매칭한다.
# 와일드카드("*")는 미들웨어를 끄는 것과 같다.
app.add_middleware(TrustedHostMiddleware,
                   allowed_hosts=["127.0.0.1", "localhost"], www_redirect=False)
app.middleware("http")(security.guard)


@app.get("/")
def home(request: Request, t: str | None = None):
    """`?t=` 로 들어오면 쿠키를 심고 **깨끗한 `/`** 로 털어낸다.

    이 라우트는 GET 이지만 서버 상태를 바꾸지 않는다 — 쿠키는 브라우저 상태다.
    토큰을 쿼리스트링에 남기면 주소창·히스토리·스크린샷에 영구히 남는다(T-1-16).
    """
    if t and secrets.compare_digest(t, security.BOOT_TOKEN):
        r = RedirectResponse("/", status_code=303)
        r.set_cookie(security.COOKIE_NAME, security.BOOT_TOKEN,
                     httponly=True, samesite="strict", path="/")
        return r
    if not security.page_cookie_ok(request):
        return PlainTextResponse(
            "토큰이 필요하다 — 서버 기동 로그의 URL 로 들어와라", status_code=403)
    return PlainTextResponse("보드 셸 자리 — Task 2 가 템플릿을 건다")


def 기동안내() -> str:
    """브라우저에 붙여넣을 URL 한 줄."""
    return f"→ http://127.0.0.1:{settings.PORT}/?t={security.BOOT_TOKEN}"
