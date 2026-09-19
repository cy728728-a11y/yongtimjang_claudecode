#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""보드 셸.

    GET /       토큰(쿼리) → 쿠키 교환 후 보드 렌더                  [읽기]

**이 라우트는 GET 이지만 서버 상태를 바꾸지 않는다.** 쿠키를 심는 것은 *브라우저*
상태를 바꾸는 것이고, 디스크·광고 API·잡 레지스트리에는 아무 일도 일어나지 않는다.
그 구분이 중요한 이유: "GET 은 상태를 안 바꾼다" 가 `security.guard` 의 Origin 방어를
성립시키는 전제이기 때문이다(T-1-01b). 여기서 한 번 예외를 허용하면 그 다음 사람이
"작업 실행도 GET 으로 하면 편한데" 로 간다.

Plan 01-04 가 이 라우트에 보드 데이터(상품 단위 접기·계정 필터·신선도)를 채운다.
지금은 회차 목록과 신선도만 넘기는 빈 셸이다.
"""
import secrets

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, RedirectResponse

from webapp import paths, security

router = APIRouter()


@router.get("/")
def home(request: Request, t: str | None = None):
    """`?t=` 로 들어오면 쿠키를 심고 **깨끗한 `/`** 로 털어낸다.

    토큰을 쿼리스트링에 남기면 주소창·브라우저 히스토리·스크린샷에 영구히 남는다
    (T-1-16). 303 으로 즉시 털어내면 사용자가 보는 URL 에는 토큰이 없다.
    비교는 `secrets.compare_digest` — `==` 를 쓰지 않는다.
    """
    if t and secrets.compare_digest(t, security.BOOT_TOKEN):
        r = RedirectResponse("/", status_code=303)
        # httponly: JS 가 못 읽는다(XSS 가 나도 쿠키는 안 샌다)
        # samesite=strict: 다른 사이트에서 넘어온 요청에는 아예 안 붙는다
        r.set_cookie(security.COOKIE_NAME, security.BOOT_TOKEN,
                     httponly=True, samesite="strict", path="/")
        return r

    if not security.page_cookie_ok(request):
        return PlainTextResponse(
            "토큰이 필요하다 — 서버 기동 로그의 URL 로 들어와라", status_code=403)

    from webapp.main import templates  # 지연 import — main 이 이 모듈을 먼저 부른다

    회차들 = paths.scan_run_dirs()
    신선도 = paths.freshness(회차들[0]) if 회차들 else None

    # 템플릿에 넘기는 것은 화면에 필요한 **값**뿐이다. 계정 객체를 통째로 넘기지 않는다
    # (SAFE-03 화이트리스트 투영). 지금 단계에서 웹앱은 계정 파일을 아예 열지 않는다.
    return templates.TemplateResponse(request, "board.html", {
        "token": security.BOOT_TOKEN,
        "run_dirs": 회차들,
        "freshness": 신선도,
    })
