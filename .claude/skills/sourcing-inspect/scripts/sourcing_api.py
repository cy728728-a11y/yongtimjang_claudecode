#!/usr/bin/env python3
"""불사자 소싱기 웹 API (읽기 전용 — 이 단계에서는 쓰기 호출을 두지 않는다).

인증은 MCP 토큰이 아니라 웹 로그인 JWT 다(만료됨). 토큰 파일:
    ~/.eroom/bulsaja-web.json   {"token": "<JWT>"}
사용자가 로그인된 크롬 DevTools 에서 localStorage.token 을 복사해 직접 넣는다.
토큰이 없거나 만료면 브라우저에서 스냅샷을 받아 `run_inspect.py fetch --from-file` 로 대체.
"""
import json
import os

import requests

API = "https://api.bulsaja.com"
TOKEN_PATH = os.path.expanduser("~/.eroom/bulsaja-web.json")
# 불사자 앞단 방화벽이 비브라우저 UA 를 막는다(메모리: bulsaja-mcp-blocks-urllib-ua)
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")


def load_token(path=TOKEN_PATH):
    """{'token': 액세스(7일), 'refresh': 리프레시(30일)} — 웹이 헤더 두 개를 같이 보낸다(실측)."""
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except FileNotFoundError:
        raise RuntimeError(f"웹 토큰 파일 없음: {path} — 크롬 로그인 후 토큰을 넣어라")
    if not (d.get("token") or "").strip():
        raise RuntimeError(f"웹 토큰이 비어 있음: {path}")
    return d


def _headers(token):
    tok = token if isinstance(token, dict) else {"token": token}
    h = {"accesstoken": tok.get("token", ""), "User-Agent": UA,
         "Content-Type": "application/json", "Origin": "https://bulsaja.com",
         "Referer": "https://bulsaja.com/"}
    if tok.get("refresh"):
        h["refreshtoken"] = tok["refresh"]
    return h


def fetch_products(campaign_id, token, timeout=300):
    """캠페인 전체 상품(한 번에 전량, 약 30MB)."""
    try:
        r = requests.post(f"{API}/api/sourcing/bulsa-sourcing-products",
                          headers=_headers(token), json={"campaignId": campaign_id},
                          timeout=timeout)
    except requests.RequestException as e:
        raise RuntimeError(f"소싱 목록 요청 실패: {e}")
    if r.status_code == 401:
        raise RuntimeError("401 — 웹 토큰 만료. 크롬에서 불사자 재로그인 후 토큰 파일 갱신")
    if r.status_code != 200:
        raise RuntimeError(f"소싱 목록 HTTP {r.status_code}: {r.text[:300]}")
    body = r.json()
    if not body.get("success"):
        raise RuntimeError(f"소싱 목록 실패 응답: {str(body)[:300]}")
    return body.get("data") or []
