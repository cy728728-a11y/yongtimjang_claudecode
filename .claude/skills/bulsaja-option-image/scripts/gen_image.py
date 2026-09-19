# -*- coding: utf-8 -*-
"""gpt-image-2 로 옵션 이미지 1장 생성 (원본 첨부 편집 — 제품 왜곡 방지).

모델은 gpt-image-2 고정(용팀장 지시: 이미지 생성은 2.0 버전만).
OpenAI 키 탐색 순서: 환경변수 → scripts/.env → smartstore-brand 스킬의 .env (재사용).
"""
import base64
import os
from pathlib import Path

import requests

from bulsaja_client import load_env_file, SCRIPT_DIR

MODEL = "gpt-image-2"
FALLBACK_ENV = SCRIPT_DIR.parent.parent / "smartstore-brand" / "scripts" / ".env"


def openai_key():
    load_env_file(SCRIPT_DIR / ".env")
    load_env_file(FALLBACK_ENV)
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError(f"OPENAI_API_KEY 없음. {SCRIPT_DIR / '.env'} 또는 {FALLBACK_ENV} 에 넣어라.")
    return key


def download(url, dest):
    """원본 이미지(URL 또는 로컬 경로)를 dest 로 가져온다."""
    dest = Path(dest)
    if not url.lower().startswith("http"):
        src = Path(url)
        if not src.exists():
            raise RuntimeError(f"소스 파일 없음: {src}")
        dest.write_bytes(src.read_bytes())
        return dest
    r = requests.get(url, timeout=60)
    if r.status_code != 200 or not r.content:
        raise RuntimeError(f"원본 내려받기 실패 HTTP {r.status_code}: {url}")
    dest.write_bytes(r.content)
    return dest


def generate(source_path, prompt, out_path, size="1024x1024"):
    """편집 API 호출 → PNG 저장. 실패는 RuntimeError."""
    key = openai_key()
    source_path, out_path = Path(source_path), Path(out_path)
    ctype = "image/png" if source_path.suffix.lower() == ".png" else "image/jpeg"
    try:
        with open(source_path, "rb") as f:
            resp = requests.post(
                "https://api.openai.com/v1/images/edits",
                headers={"Authorization": f"Bearer {key}"},
                data={"model": MODEL, "prompt": prompt, "size": size, "n": 1},
                files={"image": (source_path.name, f, ctype)},
                timeout=300,
            )
    except requests.exceptions.Timeout:
        raise RuntimeError("타임아웃(300초) — 다시 시도")
    if resp.status_code != 200:
        raise RuntimeError(f"API 오류 {resp.status_code}: {resp.text[:500]}")
    payload = resp.json()
    b64 = ((payload.get("data") or [{}])[0]).get("b64_json")
    if not b64:
        raise RuntimeError(f"응답에 이미지 없음(안전필터 등): {str(payload)[:400]}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(base64.b64decode(b64))
    return out_path
