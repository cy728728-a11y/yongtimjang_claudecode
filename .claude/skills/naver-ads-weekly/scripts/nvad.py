#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""네이버 검색광고 API 클라이언트.

서명 규칙(2026-08-27 실측 검증):
    base64(HMAC-SHA256(secret, "{timestamp_ms}.{METHOD}.{path}"))
    · path 에 쿼리스트링을 넣지 않는다
    · 리포트 다운로드 URL 도 같은 서명이 필요하다(URL 의 path 부분만 사용)
"""
import base64
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://api.searchad.naver.com"
CRED = Path.home() / ".eroom" / "naver-ads.json"
# 기본 urllib UA 를 막는 앞단이 있어 UA 를 명시한다
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"


def load_accounts():
    """자격증명 파일에서 계정 목록을 읽는다. 없으면 빈 리스트."""
    try:
        d = json.loads(CRED.read_text(encoding="utf-8"))
    except Exception:
        return []
    return d.get("accounts", []) if isinstance(d, dict) else d


def sign(secret, ts, method, path):
    """HMAC-SHA256 서명. 서명 대상은 쿼리스트링을 제외한 path 다."""
    msg = f"{ts}.{method}.{path}".encode("utf-8")
    return base64.b64encode(hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).digest()).decode("utf-8")


def headers(acct, method, path):
    """요청 헤더 4종 + UA."""
    ts = str(round(time.time() * 1000))
    return {
        "X-Timestamp": ts,
        "X-API-KEY": acct["api_key"],
        "X-Customer": str(acct["customer_id"]),
        "X-Signature": sign(acct["secret_key"], ts, method, path),
        "Content-Type": "application/json; charset=UTF-8",
        "User-Agent": UA,
    }


def call(acct, method, path, params=None, body=None, raw=False):
    """API 1회 호출. (status, body) 반환. 예외는 (0, "에러문자열")."""
    try:
        url = BASE + path + (("?" + urllib.parse.urlencode(params)) if params else "")
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers=headers(acct, method, path))
        with urllib.request.urlopen(req, timeout=60) as r:
            text = r.read().decode("utf-8")
            if raw:
                return r.status, text
            return r.status, (json.loads(text) if text.strip() else None)
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read().decode("utf-8")
        except Exception:
            return e.code, ""
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"


def download(acct, url):
    """리포트 다운로드. 같은 서명이 필요하고 서명 대상은 URL 의 path 부분이다. 실패 시 None."""
    try:
        p = urllib.parse.urlparse(url)
        h = headers(acct, "GET", p.path)
        h.pop("Content-Type", None)
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def chunks(seq, n):
    """seq 를 n개씩 자른다. /stats 의 ids 상한이 100 이라 필요하다."""
    for i in range(0, len(seq), n):
        yield seq[i:i + n]
