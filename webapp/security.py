#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""보안 3층 — 이 웹앱에 인증은 없다. 대신 "이 맥북의 이 브라우저" 만 통과시킨다.

    읽기(GET/HEAD/OPTIONS)   Host 화이트리스트만 탄다. 페이지 접근은 쿠키로 막는다  [읽기]
    쓰기(POST/PUT/DELETE)    Host + Origin + 부팅 토큰 헤더, 3층을 전부 탄다        [쓰기]

세 층이 각각 막는 것:

| 층 | 막는 것 | 없으면 |
|---|---|---|
| `--host 127.0.0.1` 바인드 (run-webapp.sh) | 같은 공유기의 다른 기기 | 카페 와이파이에서 남이 내 입찰가를 올린다 |
| `TrustedHostMiddleware` | DNS rebinding (evil.com → 127.0.0.1) | 악성 페이지가 우리 서버를 자기 오리진처럼 쓴다 |
| `guard()` 의 Origin + 토큰 | 다른 탭이 쏘는 쓰기 요청 (CSRF) | 아무 사이트나 내 광고에 PUT 을 날린다 |

**쿠키와 헤더의 역할이 다르다.** 쿠키(`ct_session`)는 *페이지 접근*, 커스텀 헤더
(`X-CT-Token`)는 *쓰기 인가*다. 쿠키로 쓰기를 인가하면 CSRF 방어가 성립하지 않는다 —
브라우저가 교차 사이트 요청에도 쿠키를 알아서 붙여 주기 때문이다(SameSite=Strict 가
도와주지만 한 겹뿐이다). 반대로 커스텀 헤더는 교차 오리진에서 **붙일 수 없다**:
붙이려면 CORS preflight 가 필요한데 이 앱은 CORS 를 아예 열지 않았다.

**이 파일의 어떤 함수도 `~/.eroom/naver-ads.json` 을 열지 않는다.** 자격증명은
CLI 서브프로세스 안에만 존재한다(`nvad.py` 가 직접 읽는다). 계정 목록이 필요하면
`run_ads.py accounts` 를 subprocess 로 부른다 — 웹앱 프로세스에 시크릿을 들이지 않는 것이
SAFE-03 을 "조심한다" 가 아니라 "구조상 불가능하다" 로 만드는 유일한 방법이다.
"""
import os
import secrets

from fastapi import Request
from fastapi.responses import PlainTextResponse

from webapp import settings

# 서버 기동 시 1회. **재시작마다 바뀌는 게 의도다** — 토큰이 어딘가 적혀 남는 것보다
# 매번 기동 로그에서 새로 집어 오는 편이 안전하다.
# `CT_DEV_TOKEN` 은 개발 편의용이다(`--reload` 가 리로드마다 토큰을 바꾸면 못 쓴다).
# 운영 기본은 랜덤이고, **토큰을 파일로 떨구지 않는다** — 메모리에만 둔다 (T-1-16).
BOOT_TOKEN = os.environ.get("CT_DEV_TOKEN") or secrets.token_urlsafe(32)

COOKIE_NAME = "ct_session"
HEADER_NAME = "X-CT-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def 토큰이같나(들어온것: str, 진짜: str) -> bool:
    """상수시간 토큰 비교. **비ASCII 입력에도 예외를 던지지 않는다.**

    `secrets.compare_digest` 는 str 두 개를 받으면 내부적으로 ASCII 인코딩을 시도하고,
    한 글자라도 ASCII 밖이면 `TypeError: comparing strings with non-ASCII characters
    is not supported` 를 던진다. HTTP 헤더·쿠키 값은 **누구나 아무 바이트나** 넣을 수
    있으므로(실측: `X-CT-Token: 한글` → 500), 그대로 두면 토큰 비교가 인증 거부가
    아니라 **서버 오류**가 된다. 403 이어야 할 자리에 500 이 나오면 ① 거부 경로가
    에러 핸들러로 새고 ② 로그가 트레이스백으로 더럽혀지고 ③ "가끔 500 이 난다" 를
    쫓게 된다.

    바이트로 바꿔서 비교하면 상수시간 성질은 그대로이고 예외만 사라진다.
    """
    return secrets.compare_digest(
        들어온것.encode("utf-8", "surrogatepass"),
        진짜.encode("utf-8", "surrogatepass"))


def allowed_origins() -> set[str]:
    """쓰기를 허용할 Origin 집합.

    포트를 리터럴로 박지 않는다. 설정에서 포트를 바꾸면 허용 목록이 같이 움직여야
    한다 — 안 그러면 포트를 바꾼 순간 모든 쓰기가 403 이 되거나(운 좋은 경우),
    허용 목록이 죽은 값이 되어 방어가 조용히 무너진다.

    매 호출마다 조립한다. 모듈 상수로 굳히면 `settings.reload()` 를 따라오지 못한다.
    """
    port = settings.PORT
    return {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}


async def guard(request: Request, call_next):
    """쓰기 메서드만 검사한다. **상태를 바꾸는 GET 을 만들지 않는 것이 이 방어의 전제다.**

    브라우저는 모든 POST/PUT/DELETE 에 `Origin` 을 붙인다(교차 사이트 `<form>` POST 도).
    그런데 단순 교차 사이트 GET(`<img src>`·`<script src>`·링크)에는 Origin 이 **없다**.
    따라서 부수효과가 있는 엔드포인트를 GET 으로 하나라도 만들면 이 층이 통째로 뚫린다.
    htmx 쪽에서도 `hx-post`/`hx-delete` 만 쓴다 (T-1-01b).

    검사 순서가 중요하다:
      1. Origin 이 있는데 우리 것이 아니다  → 토큰을 볼 것도 없이 거부.
         토큰이 어쩌다 샜어도 다른 탭에서는 못 쓴다.
      2. Origin 이 없고 `Sec-Fetch-Site` 가 same-origin 도 아니다 → 거부.
         구형 폼·비브라우저 클라이언트가 Origin 을 안 붙이는 경우의 2차선이다.
         헤더 자체가 없는 경우(curl 등 `None`)는 통과시키고 3번 토큰에 맡긴다.
      3. 토큰 불일치 → 거부. `==` 가 아니라 `secrets.compare_digest` 다.
    """
    if request.method not in SAFE_METHODS:
        origin = request.headers.get("origin")
        if origin is not None and origin not in allowed_origins():
            return PlainTextResponse("origin 거부", status_code=403)
        if origin is None and request.headers.get("sec-fetch-site") not in (None, "same-origin"):
            return PlainTextResponse("sec-fetch-site 거부", status_code=403)
        토큰 = request.headers.get(HEADER_NAME.lower()) or ""
        if not 토큰이같나(토큰, BOOT_TOKEN):
            return PlainTextResponse("토큰 거부", status_code=403)
    return await call_next(request)


def page_cookie_ok(request: Request) -> bool:
    """페이지를 그려도 되는지 — 쿠키 게이트. 라우트 레벨에서 부른다.

    미들웨어가 아니라 라우트에서 보는 이유: `/healthz` 처럼 쿠키 없이도 열려야 하는
    읽기 창이 있다. 화면이 고장났을 때 서버가 살았는지 보려면 그 창은 막히면 안 된다.
    """
    return 토큰이같나(request.cookies.get(COOKIE_NAME, ""), BOOT_TOKEN)


# ── 시크릿 스크러버 ──────────────────────────────────────────────────────────
# Phase 1 에서 이 집합은 **비어 있는 것이 정상이다.** 웹앱이 자격증명을 손에 쥐지
# 않으므로 scrub() 은 사실상 항등 함수다. 그런데도 이 함수가 존재하는 이유는,
# 자식 프로세스(CLI)가 예기치 않게 시크릿을 찍을 가능성에 대비한 **로그 쓰기 시점 훅**
# 이기 때문이다. Plan 01-05 의 로그 tail 이 화면으로 나가기 전에 여기를 통과한다.
# 비용은 문자열 replace 한 번이고, 나중에 붙이려면 tail 경로를 다시 뒤져야 한다.
#
# 휴리스틱 마스킹(40자 넘는 base64 스러운 토큰을 자동으로 자르기)은 **하지 마라** —
# 중국어 상품명·긴 URL 을 오탐해 화면이 별표로 덮인다. 아는 값만 가린다.
_SECRETS: set[str] = set()


def register_secret(value: str) -> None:
    """가릴 문자열을 등록한다. 짧은 값은 무시한다(오탐으로 화면이 깨진다)."""
    if value and len(value) >= 8:
        _SECRETS.add(value)


def scrub(text: str) -> str:
    """등록된 시크릿 값을 `***` 로 치환한다. 등록된 게 없으면 원문 그대로."""
    if not text or not _SECRETS:
        return text
    for s in _SECRETS:
        if s in text:
            text = text.replace(s, "***")
    return text
