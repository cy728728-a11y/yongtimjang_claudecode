#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""게이트 판정 저장소(`market_gate_store`) 단위 검증 — Phase 6 / 06-04 · D-09 · T-06-24·25.

보는 것:
  · DB 가 없으면(또는 못 열면) 판정 없음 = 게이트 닫힘 — **안전 쪽으로 떨어진다**
  · 판정은 누적이다(덮어쓰지 않는다) — 누가 언제 무엇을 보고 열었나가 남는다
  · 판정 값은 정상/이상 둘뿐 · 빈 코드는 거부
  · 저장소 소스에 스키마 조작 낱말이 없다 — 스키마 정본은 `jobs.DDL`
"""
import re
import sqlite3
from pathlib import Path

import pytest

from webapp import jobs, market_gate_store, settings


@pytest.fixture
def 빈DB(tmp_path, monkeypatch):
    """tmp DB 경로만 돌린다 — 파일은 만들지 않는다."""
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "gate.db"))
    return tmp_path / "gate.db"


@pytest.fixture
def DB(빈DB):
    jobs.init_db()
    return 빈DB


def _기록(판정="정상", 코드="zz01", pid="zzp1", 잡="job-zz-1", 교체="교체됨", 메모=""):
    market_gate_store.판정기록(판정, 코드, pid, 잡, 교체, 메모)


def test_저장소_DB없음은_닫힘(빈DB):
    assert not 빈DB.exists()
    assert market_gate_store.최신판정() is None
    assert market_gate_store.통과() is False
    assert not 빈DB.exists(), "읽기 경로가 DB 파일을 만들었다"


def test_저장소_못여는DB도_닫힘(빈DB):
    빈DB.write_bytes(b"not a sqlite file at all" * 10)
    assert market_gate_store.최신판정() is None
    assert market_gate_store.통과() is False


def test_저장소_판정없으면_닫힘(DB):
    assert market_gate_store.최신판정() is None
    assert market_gate_store.통과() is False


def test_저장소_누적기록(DB):
    _기록("정상", 메모="첫 판정")
    _기록("이상", 메모="상단 이미지가 옛것")
    cx = sqlite3.connect(DB)
    try:
        n = cx.execute("SELECT count(*) FROM market_gate").fetchone()[0]
    finally:
        cx.close()
    assert n == 2, "판정을 덮어썼다 — 이력이 누적돼야 한다"
    최신 = market_gate_store.최신판정()
    assert 최신["판정"] == "이상" and 최신["메모"] == "상단 이미지가 옛것"
    assert 최신["판매자상품코드"] == "zz01" and 최신["productId"] == "zzp1"
    assert 최신["commit_job_id"] == "job-zz-1" and 최신["기록시각"]
    assert market_gate_store.통과() is False


def test_저장소_최신이_정상이면_통과(DB):
    _기록("이상")
    _기록("정상")
    assert market_gate_store.통과() is True


@pytest.mark.parametrize("판정", ["", "통과", "ok", "정상 "])
def test_저장소_화이트리스트(DB, 판정):
    with pytest.raises(ValueError):
        _기록(판정)
    assert market_gate_store.최신판정() is None


@pytest.mark.parametrize("필드", ["코드", "pid", "잡"])
def test_저장소_빈값은_거부(DB, 필드):
    with pytest.raises(ValueError):
        _기록(**{필드: "  "})
    assert market_gate_store.최신판정() is None


def test_저장소_DDL0():
    소스 = Path(market_gate_store.__file__).read_text(encoding="utf-8")
    assert not re.search(r"create|alter|drop", 소스, re.IGNORECASE)


def test_jobs_DDL에_market_gate():
    assert jobs.DDL.count("CREATE TABLE IF NOT EXISTS market_gate") == 1
