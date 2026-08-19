#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
마지막 성공 실행시각을 로컬 파일에 기록한다.
gws 토큰이 조용히 만료되는 등으로 스크립트가 계속 실패해도 감지할 수 있게 하기 위함.
"""
import json
from pathlib import Path

STATE_DIR = Path(__file__).resolve().parent / ".state"
LAST_SUCCESS_FILE = STATE_DIR / "last_success.json"


def record_success(timestamp: str) -> None:
    """마지막 성공 실행시각(ISO 8601 문자열)을 기록한다."""
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        LAST_SUCCESS_FILE.write_text(json.dumps({"last_success": timestamp}), encoding="utf-8")
    except OSError:
        pass  # 상태 기록 실패는 본 처리 결과에 영향을 주지 않음


def read_last_success() -> str:
    """마지막 성공 실행시각을 반환한다. 기록이 없으면 None."""
    if not LAST_SUCCESS_FILE.exists():
        return None
    try:
        data = json.loads(LAST_SUCCESS_FILE.read_text(encoding="utf-8"))
        return data.get("last_success")
    except (json.JSONDecodeError, OSError):
        return None
