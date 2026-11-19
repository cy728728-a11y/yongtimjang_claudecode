"""네이버 카페 글쓰기 — 공식 카페 API(네이버 로그인 OAuth) 사용."""
import json
import os
from urllib.parse import quote

import requests

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".eroom", "naver-cafe.json")
TOKEN_URL = "https://nid.naver.com/oauth2.0/token"
POST_URL = "https://openapi.naver.com/v1/cafe/{club_id}/menu/{menu_id}/articles"


class CafeError(Exception):
    """카페 게시 실패"""


class CafeAuthError(CafeError):
    """네이버 허락(토큰) 만료 — cafe_setup.py 다시 필요"""


def load_config(path: str = CONFIG_PATH) -> dict:
    """설정 읽기. 어디서 읽었는지 '_path' 로 기억해 둔다(토큰 갱신 때 같은 곳에 저장)."""
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except FileNotFoundError as e:
        raise CafeAuthError(f"네이버 카페 설정이 없습니다: {path} (cafe_setup.py 먼저 실행)") from e
    cfg["_path"] = path
    return cfg


def save_config(cfg: dict) -> None:
    path = cfg.get("_path", CONFIG_PATH)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({k: v for k, v in cfg.items() if k != "_path"}, f, ensure_ascii=False, indent=2)


def refresh_access_token(cfg: dict) -> str:
    """리프레시 토큰으로 새 접근 토큰을 받아 설정에 저장하고 돌려준다."""
    try:
        r = requests.post(TOKEN_URL, params={
            "grant_type": "refresh_token", "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"], "refresh_token": cfg["refresh_token"],
        }, timeout=30)
        data = r.json()
    except Exception as e:
        raise CafeError(f"네이버 토큰 갱신 요청 실패: {e}") from e
    if data.get("error") or not data.get("access_token"):
        raise CafeAuthError(f"네이버 허락이 만료됐어요: {data.get('error_description') or data}")
    cfg["access_token"] = data["access_token"]
    if data.get("refresh_token"):
        cfg["refresh_token"] = data["refresh_token"]
    save_config(cfg)
    return cfg["access_token"]


def _encode(text: str) -> str:
    # 공식 문서 규칙: UTF-8 로 한 번 인코딩한 결과를 다시 한 번 인코딩
    return quote(quote(text, safe=""), safe="")


def make_content(link: str) -> str:
    """본문: 드라이브 링크 주소 한 줄. <a> 태그를 넣으면 네이버가 999 오류로 거절한다(2026-11-19 실측)."""
    return link


def post_article(cfg: dict, subject: str, content: str) -> str:
    """실전반 소통방에 글을 올리고 글 주소를 돌려준다. 토큰 만료(401)면 갱신 후 1회 재시도."""
    url = POST_URL.format(club_id=cfg["club_id"], menu_id=cfg["menu_id"])
    body = f"subject={_encode(subject)}&content={_encode(content)}"
    for attempt in range(2):
        headers = {"Authorization": f"Bearer {cfg.get('access_token', '')}",
                   "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
        try:
            r = requests.post(url, data=body, headers=headers, timeout=60)
        except Exception as e:
            raise CafeError(f"카페 게시 요청 실패: {e}") from e
        if r.status_code == 401 and attempt == 0:
            refresh_access_token(cfg)
            continue
        try:
            data = r.json()
        except ValueError:
            data = {}
        result = (data.get("message") or {}).get("result") or {}
        if r.status_code == 200 and result.get("articleUrl"):
            return result["articleUrl"]
        if r.status_code == 200 and result.get("articleId"):
            # 주소가 빠져도 글은 생긴 것 — 실패로 보면 다음 주에 또 올라간다
            return f"https://cafe.naver.com/{result.get('cafeUrl', '')}/{result['articleId']}"
        if r.status_code == 401:
            raise CafeAuthError(f"네이버 허락이 만료됐어요: {r.text[:300]}")
        raise CafeError(f"카페 게시 실패({r.status_code}): {r.text[:300]}")
    raise CafeError("카페 게시 실패: 재시도 후에도 실패")
