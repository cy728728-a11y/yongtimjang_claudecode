#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
줌(Zoom) 미팅 생성기
- Server-to-Server OAuth로 인증 후 미팅을 예약하고 join_url을 출력
- 자격증명은 워크스페이스 루트 .env 에서 읽음 (git 제외됨)
- 표준 라이브러리만 사용 (별도 pip 설치 불필요)

사용 예:
  python zoom_meeting.py --topic "구매대행 실전반 3주차" --start 2026-08-05T14:00:00 --duration 120
"""

import argparse
import json
import sys
from pathlib import Path

REQUIRED_KEYS = ["ZOOM_ACCOUNT_ID", "ZOOM_CLIENT_ID", "ZOOM_CLIENT_SECRET", "ZOOM_USER_EMAIL"]


def load_env(env_path: Path) -> dict:
    """.env 파일을 파싱해 dict 로 반환 (KEY=VALUE, # 주석 무시)."""
    data = {}
    if not env_path.exists():
        return data
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        data[key.strip()] = val.strip().strip('"').strip("'")
    return data


def find_env() -> Path:
    """워크스페이스 루트(.env) → 스크립트 폴더(.env) 순으로 탐색."""
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / ".env",   # 워크스페이스 루트 (10-projects/줌미팅-자동화/ 기준 2단계 위)
        here.parent / ".env",       # 스크립트와 같은 폴더
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def load_credentials(env: dict) -> dict:
    """env dict에서 줌 자격증명 4종을 검증해 반환. 누락 시 ValueError."""
    missing = [k for k in REQUIRED_KEYS if not env.get(k, "").strip()]
    if missing:
        raise ValueError(f"다음 값이 .env에 없습니다: {', '.join(missing)}")
    return {k: env[k].strip() for k in REQUIRED_KEYS}


if __name__ == "__main__":
    pass
