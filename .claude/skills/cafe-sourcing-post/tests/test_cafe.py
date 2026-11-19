# cafe.py 테스트 — 네이버 호출은 가짜 응답으로 확인
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import cafe  # noqa: E402


class Resp:
    def __init__(self, status, data):
        self.status_code = status
        self._data = data
        self.text = json.dumps(data, ensure_ascii=False)

    def json(self):
        return self._data


OK = {"message": {"status": "200", "result": {"msg": "Success", "cafeUrl": "hz", "articleId": 9001,
                                               "articleUrl": "https://cafe.naver.com/hz/9001"}}}


def cfg(tmp_path):
    c = {"client_id": "CID", "client_secret": "SEC", "refresh_token": "R", "access_token": "OLD",
         "club_id": "111", "menu_id": "22"}
    p = tmp_path / "naver-cafe.json"
    p.write_text(json.dumps(c), encoding="utf-8")
    c["_path"] = str(p)
    return c


def test_post_double_encodes_korean_subject(monkeypatch, tmp_path):
    sent = {}

    def fake_post(url, data=None, headers=None, timeout=None):
        sent.update(url=url, data=data, headers=headers)
        return Resp(200, OK)

    monkeypatch.setattr(cafe.requests, "post", fake_post)
    url = cafe.post_article(cfg(tmp_path), "2026년 12월 3일 최신화", "<a href=\"L\">L</a>")
    assert url == "https://cafe.naver.com/hz/9001"
    assert sent["url"] == "https://openapi.naver.com/v1/cafe/111/menu/22/articles"
    assert sent["headers"]["Authorization"] == "Bearer OLD"
    # 공식 문서: UTF-8 로 한 번, 그 결과를 다시 한 번 인코딩
    assert "subject=2026%25EB%2585%2584" in sent["data"]


def test_401_refreshes_token_then_retries(monkeypatch, tmp_path):
    c = cfg(tmp_path)
    posts = []

    def fake_post(url, data=None, headers=None, timeout=None, params=None):
        if "oauth2.0/token" in url:
            return Resp(200, {"access_token": "NEW", "token_type": "bearer", "expires_in": "3600"})
        posts.append(headers["Authorization"])
        return Resp(401, {"errorMessage": "expired", "errorCode": "024"}) if len(posts) == 1 else Resp(200, OK)

    monkeypatch.setattr(cafe.requests, "post", fake_post)
    cafe.post_article(c, "제목", "본문")
    assert posts == ["Bearer OLD", "Bearer NEW"]
    assert json.loads(open(c["_path"], encoding="utf-8").read())["access_token"] == "NEW"


def test_refresh_error_raises_auth(monkeypatch, tmp_path):
    monkeypatch.setattr(cafe.requests, "post",
                        lambda url, **kw: Resp(200, {"error": "invalid_request", "error_description": "no"}))
    with pytest.raises(cafe.CafeAuthError):
        cafe.refresh_access_token(cfg(tmp_path))


def test_other_failure_is_cafe_error(monkeypatch, tmp_path):
    monkeypatch.setattr(cafe.requests, "post",
                        lambda url, **kw: Resp(403, {"errorMessage": "글쓰기 권한 없음", "errorCode": "AP002"}))
    with pytest.raises(cafe.CafeError) as e:
        cafe.post_article(cfg(tmp_path), "제목", "본문")
    assert not isinstance(e.value, cafe.CafeAuthError)
    assert "AP002" in str(e.value)


def test_make_content_is_link():
    assert cafe.make_content("https://x/y") == '<a href="https://x/y">https://x/y</a>'


def test_article_id_without_url_still_success(monkeypatch, tmp_path):
    # 200 인데 articleUrl 이 빠져도 글은 생긴 것 — 실패로 보면 다음 주에 또 올라간다
    data = {"message": {"status": "200", "result": {"msg": "Success", "cafeUrl": "hz", "articleId": 77}}}
    monkeypatch.setattr(cafe.requests, "post", lambda url, **kw: Resp(200, data))
    assert cafe.post_article(cfg(tmp_path), "제목", "본문") == "https://cafe.naver.com/hz/77"
