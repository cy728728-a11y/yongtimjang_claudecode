#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""웹앱 테스트 공통 픽스처.

원칙 하나: **테스트는 실제 `~/python_work/data` 를 절대 만지지 않는다.**
`tmp_run_dir` 이 monkeypatch 로 `paths.data_root` 를 tmp_path 로 갈아끼우고,
모든 파일 접근은 그 아래에서만 일어난다. 여기가 뚫리면 테스트 한 번에
실제 회차의 `before_bids_*.json` 백업이나 ledger 가 오염될 수 있다.
"""
import json
import shutil
import sys
from pathlib import Path

import pytest

from webapp import paths, settings

FIXTURES = Path(__file__).resolve().parent / "fixtures"
RESULT_MIN = FIXTURES / "result_min.json"
SYNTHETIC_JOB = FIXTURES / "synthetic_job.py"

# 픽스처 회차명. `result_min.json` 의 `generated` 와 맞춰 둔다.
RUN_NAME = "2026-08-30"


@pytest.fixture
def fake_result_json() -> dict:
    """`result_min.json` 을 파싱한 dict.

    파일 IO 없이 순수 함수(보드 투영·집계)를 때릴 때 쓴다.
    매번 새로 파싱한다 — 테스트가 dict 를 고쳐도 다음 테스트에 안 샌다.
    """
    return json.loads(RESULT_MIN.read_text(encoding="utf-8"))


@pytest.fixture
def tmp_run_dir(tmp_path, monkeypatch) -> Path:
    """`tmp_path/naver-ads/runs/2026-08-30` 을 만들고 data_root 를 거기로 돌린다.

    **`runs/<회차>` 2단 구조를 반드시 만든다.** `bids.py:130` 이 ledger 를
    `run_dir.parent.parent/"ledger"` 로 찾는다 — 한 단이라도 빠뜨리면
    테스트가 tmp 밖(실제 ledger)을 짚는다.
    """
    run_dir = tmp_path / "naver-ads" / "runs" / RUN_NAME
    run_dir.mkdir(parents=True)
    shutil.copyfile(RESULT_MIN, run_dir / "result.json")

    # 통계기간은 회차명보다 항상 2일 이상 과거다 — collect.window() 가 until=today-2일.
    # 신선도 표시(D-16)가 둘을 같이 보여주는지 검증하려면 픽스처도 그 간극을 가져야 한다.
    (run_dir / "prep_summary.json").write_text(json.dumps({
        "window7": ["2026-08-22", "2026-08-28"],
        "window30": ["2026-07-30", "2026-08-28"],
    }, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(paths, "data_root", lambda: tmp_path)
    return run_dir


@pytest.fixture
def synthetic_job(tmp_path):
    """합성 잡의 argv 와 로그 경로를 돌려주는 팩토리.

    실제 CLI 대신 이걸 태워서 잡 엔진(로그 tail · SSE 재접속 · 고아 자식)을 검증한다.
    광고 API 를 안 부르므로 돈이 0 이다.
    """
    def _만들기(lines: int = 12, delay: float = 0.2, rc: int = 0, name: str = "synthetic"):
        return {
            "argv": [sys.executable, str(SYNTHETIC_JOB), str(lines), str(delay), str(rc)],
            "log_path": tmp_path / f"{name}.log",
            "lines": lines,
            "delay": delay,
            "expected_seconds": lines * delay,
        }
    return _만들기


@pytest.fixture
def client():
    """`TestClient` + 부팅 토큰.

    **Plan 01-03 이 `webapp/main.py` 와 부팅 토큰을 만들기 전까지는 여기서 ImportError 가 난다.**
    `pytest.importorskip` 으로 덮지 않는다 — 덮으면 Wave 1 이 라우트를 못 만들어도
    테스트가 초록으로 보인다. Wave 0 에서는 아무도 이 픽스처를 안 쓰므로 전체는 green 이다.
    """
    from fastapi.testclient import TestClient

    from webapp.main import app  # 01-03 산출물

    base = f"http://127.0.0.1:{settings.PORT}"
    with TestClient(app, base_url=base) as c:
        # Origin 은 자기 자신이어야 통과한다 (SAFE-01: 타 사이트 Origin 의 쓰기는 403)
        c.headers["Origin"] = base
        token = getattr(app.state, "boot_token", None)
        if token:
            c.headers["X-CT-Token"] = token
        yield c
