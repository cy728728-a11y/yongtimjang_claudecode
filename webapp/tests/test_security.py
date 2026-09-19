#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""보안 3층 회귀 테스트 — RESEARCH §4.1 의 curl 6케이스를 TestClient 로 옮긴 것.

이 파일이 지키는 것은 **"나 말고는 아무도 못 들어온다"** 하나다.

    Host 화이트리스트   → DNS rebinding (evil.com 을 127.0.0.1 로 재바인딩) 차단
    Origin 가드        → 다른 탭의 임의 사이트가 쏘는 쓰기 요청 차단 (CSRF)
    부팅 토큰 헤더      → 위 둘을 뚫어도 토큰 없이는 쓰기 불가

**왜 쿠키가 아니라 헤더로 쓰기를 인가하는지**가 이 테스트의 핵심 설계다.
쿠키는 브라우저가 알아서 붙여 주므로 CSRF 방어가 되지 않는다. 커스텀 헤더는
교차 오리진에서 붙일 수 없다(CORS 를 아예 안 열었으므로 preflight 가 불가능).
쿠키 = 페이지 접근, 헤더 = 쓰기 인가.

`client` 픽스처(conftest)는 **정상 사용자**를 흉내 낸다 — Origin 과 X-CT-Token 이
이미 붙어 있다. 공격자를 흉내 내는 테스트는 그 헤더를 걷어내고(`del client.headers[...]`)
쏜다. 픽스처가 function-scope 라 이 변조는 다음 테스트로 새지 않는다.

시크릿 테스트는 실제 `~/.eroom/naver-ads.json` 을 읽는다. **값을 절대 출력하지 않는다** —
`assert 값 not in 본문` 을 쓰면 실패 시 pytest 가 양쪽을 화면에 찍는다. 그래서
`pytest.fail(사유만)` 로 간다.
"""
import json
from pathlib import Path

import pytest

from webapp import security, settings

# 쓰기 경로 하나를 고정해 둔다. Plan 01-05 가 이 라우트를 실제로 만들기 전까지는 404 지만,
# 미들웨어는 라우팅 **전에** 돌므로 403/404 의 구분만으로 가드가 증명된다.
쓰기경로 = "/jobs/bids/preview"


# ── SAFE-01: Host 화이트리스트 (DNS rebinding) ───────────────────────────────

def test_evil_호스트는_400(client):
    """`Host: evil.com` → 400. 공격자가 자기 도메인을 127.0.0.1 로 재바인딩해도
    브라우저가 보내는 Host 는 evil.com 이라 여기서 멈춘다."""
    r = client.get("/", headers={"Host": "evil.com"})
    assert r.status_code == 400


def test_포트가_붙은_로컬호스트는_통과한다(client):
    """`Host: 127.0.0.1:<PORT>` 는 통과한다 — 미들웨어가 포트를 떼고 매칭하기 때문.

    `allowed_hosts` 에 포트를 적으면 이게 깨진다(그래서 적지 않는다).
    여기서 겨누는 것은 200 이 아니라 **400 이 아님**이다. 쿠키가 없으니
    라우트 레벨에서 403 이 나는 것은 정상이다.
    """
    r = client.get("/", headers={"Host": f"127.0.0.1:{settings.PORT}"})
    assert r.status_code != 400


# ── SAFE-01 후반: Origin 가드 (CSRF) ─────────────────────────────────────────

def test_타사이트_origin_은_토큰이_맞아도_거부(client):
    """Origin 이 토큰보다 **먼저** 걸린다. 토큰이 어쩌다 샜어도 다른 탭에서는 못 쓴다."""
    r = client.post(쓰기경로, headers={"Origin": "https://evil.com"})
    assert r.status_code == 403
    assert "origin" in r.text


def test_올바른_origin_과_토큰이면_거부되지_않는다(client):
    """**이게 없으면 '전부 막힘' 을 성공으로 오독한다.**

    Plan 01-05 가 라우트를 만들기 전이라 404 다. 겨누는 것은 403 이 아님.
    """
    r = client.post(쓰기경로)
    assert r.status_code != 403


def test_origin_없는_교차사이트_쓰기는_거부(client):
    """Origin 헤더가 없는 쓰기(구형 폼·비브라우저)는 `Sec-Fetch-Site` 로 한 번 더 본다."""
    del client.headers["Origin"]
    r = client.post(쓰기경로, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    assert "sec-fetch-site" in r.text


def test_허용_origin_은_설정_포트에서_조립된다(monkeypatch):
    """포트를 바꾸면 허용 목록도 따라 움직인다 — 8765 를 리터럴로 박으면 조용히 깨진다."""
    monkeypatch.setattr(settings, "PORT", 9999)
    assert security.allowed_origins() == {
        "http://127.0.0.1:9999", "http://localhost:9999"}


# ── SAFE-02: 부팅 토큰 ───────────────────────────────────────────────────────

def test_토큰_없는_쓰기는_403(client):
    del client.headers["X-CT-Token"]
    r = client.post(쓰기경로)
    assert r.status_code == 403
    assert "토큰" in r.text


def test_틀린_토큰_쓰기는_403(client):
    client.headers["X-CT-Token"] = "wrong"
    r = client.post(쓰기경로)
    assert r.status_code == 403
    assert "토큰" in r.text


def test_읽기는_토큰가드를_타지_않는다(client):
    """GET 은 미들웨어의 토큰·Origin 검사를 타지 않는다.

    **이 방어의 전제는 "상태를 바꾸는 GET 을 만들지 않는다" 다.** 교차 사이트
    단순 GET(`<img src>`·`<script src>`)에는 Origin 헤더가 없어서, 부수효과가 있는
    GET 을 하나라도 만들면 Origin 방어가 통째로 무력화된다.
    페이지 접근 자체는 쿠키(`ct_session`)가 라우트 레벨에서 막는다.
    """
    del client.headers["X-CT-Token"]
    del client.headers["Origin"]
    r = client.get("/healthz")
    assert r.status_code != 403


def test_토큰_비교는_상수시간이다():
    """`==` 가 아니라 `secrets.compare_digest` 를 쓴다. 로컬이라 과해 보여도 비용이 0 이다."""
    본문 = Path(security.__file__).read_text(encoding="utf-8")
    assert 본문.count("compare_digest") >= 2


# ── SAFE-03: 시크릿 비노출 ───────────────────────────────────────────────────

def test_스크러버가_등록된_시크릿을_가린다():
    """Phase 1 에서 `_SECRETS` 는 비어 있는 게 정상이다(웹앱이 시크릿을 안 쥔다).

    그래도 함수는 있어야 한다 — 자식 프로세스가 예기치 않게 찍을 가능성에 대비한
    로그 쓰기 시점 훅이고, Plan 01-05 의 로그 tail 이 여기를 통과한다.
    """
    원래 = set(security._SECRETS)
    try:
        security.register_secret("s3cr3t-value")
        가린것 = security.scrub("앞 s3cr3t-value 뒤")
        assert "s3cr3t-value" not in 가린것
        assert "***" in 가린것
        # 빈 문자열을 등록해도 전체가 별표로 덮이지 않는다
        security.register_secret("")
        assert security.scrub("멀쩡한 줄") == "멀쩡한 줄"
    finally:
        security._SECRETS.clear()
        security._SECRETS.update(원래)


def test_시크릿이_새지_않는다(client):
    """`~/.eroom/naver-ads.json` 의 첫 계정 secret_key 가 응답 본문·템플릿에서 0건.

    웹앱은 이 파일을 **열지 않는다**(계정 목록이 필요하면 `run_ads.py accounts`).
    그러니 이 테스트는 "안 열었다" 를 밖에서 관찰하는 방식이다.
    값은 어디에도 출력하지 않는다 — assert 대신 pytest.fail(사유만).
    """
    설정 = Path.home() / ".eroom" / "naver-ads.json"
    if not 설정.is_file():
        pytest.skip("광고 계정 설정이 없는 환경이다")
    계정 = json.loads(설정.read_text(encoding="utf-8"))["accounts"][0]
    시크릿 = str(계정.get("secret_key") or "")
    if len(시크릿) < 8:
        pytest.skip("첫 계정에 secret_key 가 없다")

    client.cookies.set("ct_session", client.headers["X-CT-Token"])
    r = client.get("/")
    if r.status_code != 200:
        pytest.fail(f"쿠키를 심었는데 보드가 안 열린다 (status={r.status_code})")
    if 시크릿 in r.text:
        pytest.fail("GET / 응답 본문에 광고 시크릿이 들어 있다")

    템플릿 = Path(security.__file__).resolve().parent / "templates"
    for f in sorted(템플릿.rglob("*")) if 템플릿.is_dir() else []:
        if f.is_file() and 시크릿 in f.read_text(encoding="utf-8", errors="ignore"):
            pytest.fail(f"템플릿에 광고 시크릿이 들어 있다: {f.name}")
