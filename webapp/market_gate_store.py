#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""첫 1건 육안 확인 게이트 저장소 — `market_gate` 를 읽고 쓴다 (MARKET-02 · SC-2 · D-09).

스마트스토어 반영은 첫 1건이 나간 뒤 **사람이 자기 브라우저로 스토어를 열어 본 판정**
(정상/이상)이 있어야 나머지가 열린다. 상하단 안내이미지가 현재 불사자 설정으로 붙는지,
옛것으로 되돌아가는지는 문서로 판명이 안 났다 — 한 번의 사람 판정으로 그 모순을 깬다.

이건 **완료 대장이 아니라 사람 판정 기록이다** (L-05 비충돌). 작업 완료 여부의 정본은
여전히 불사자 서버 플래그 · `market_status.json` 이고, 여기는 "누가 언제 무엇을 보고
게이트를 열었나/닫았나" 만 남긴다. 재생성할 수 없는 사람의 시간이라 SQLite 에 둔다.

읽기와 쓰기를 **커넥션 수준에서 가른다** (`banner_store.py` 와 같은 모양):
  · 읽기(`최신판정`·`통과`) → `_ro_conn()` (`mode=ro` URI). 파일이 없으면 **만들지 않는다**
  · 쓰기(`판정기록`) → `_conn()` + `INSERT` — **덮어쓰지 않는다.** 판정 이력은 누적이다(T-06-25)

## 이 모듈이 절대 하지 않는 것

  ① **스키마를 다루지 않는다.** 테이블 정의 문장이 이 파일에 0건이고, 그 사실을
     `test_market_gate_store.py` 의 grep 가드가 집행한다 — 그래서 그 낱말들을 주석에도
     글자로 남기지 않는다. 스키마 정본은 `jobs.DDL` 이고 `init_db()` 가 만든다.
  ② **작업 완료를 기록하지 않는다.** 반영 성공/실패는 CLI 체크포인트가 정본이다.
     여기 적히는 것은 사람의 정상/이상 판정 하나뿐이다.
  ③ **불사자·네이버를 부르지 않는다.** MCP 호출도, 스토어 조회도 없다 — 사람이 본 것을 적을 뿐이다.
  ④ **판정 대상 상품을 화면에서 받지 않는다.** 라우트가 체크포인트의 성공 항목에서 정해 넘긴다.
"""
import sqlite3
from datetime import datetime
from pathlib import Path

from webapp import paths, settings

# 사람이 찍을 수 있는 값. 라우트의 Literal 과 같은 집합이다 — 여기서 한 번 더 본다.
판정허용값 = ("정상", "이상")


def db_path() -> Path:
    """판정이 사는 파일. `jobs.db_path()` 와 **같은 파일**이다 (`banner_store.db_path` 와 같은 이유로 복제)."""
    p = Path(settings.DB_PATH).expanduser()
    return p if p.is_absolute() else paths.repo_root() / p


def _ro_conn() -> sqlite3.Connection:
    """읽기 전용 커넥션. 파일이 없으면 열기 자체가 실패한다 — **읽기 경로가 파일을 만들지 않는다.**"""
    cx = sqlite3.connect(f"file:{db_path()}?mode=ro", uri=True, timeout=5)
    cx.row_factory = sqlite3.Row
    return cx


def _conn() -> sqlite3.Connection:
    """쓰기 커넥션. `timeout=5` 로 잠깐의 경합은 기다린다 (`jobs._conn` 과 같다)."""
    cx = sqlite3.connect(db_path(), timeout=5)
    cx.row_factory = sqlite3.Row
    return cx


def _now() -> str:
    """로컬 시각 + 오프셋."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


# ── 읽기 ────────────────────────────────────────────────────────────────────

def 최신판정() -> dict | None:
    """가장 최근 판정 한 줄. 없으면 None.

    **DB 파일이 없거나, 못 열거나, 조회가 실패하면 None = 게이트 닫힘이다** (T-06-24).
    판정을 못 읽는 상황에서 게이트가 열리면 육안 확인 없이 20건이 나간다 — 닫힌 쪽으로
    떨어지면 최악이 "1건씩만 나간다" 다. 그래서 여기서는 테이블 부재도 삼킨다.
    """
    if not db_path().is_file():
        return None
    try:
        cx = _ro_conn()
    except sqlite3.Error:
        return None
    try:
        r = cx.execute(
            "SELECT id, 판정, 기록시각, 판매자상품코드, productId, commit_job_id, "
            "스토어교체여부, 메모 FROM market_gate ORDER BY id DESC LIMIT 1").fetchone()
    except sqlite3.Error:
        return None
    finally:
        cx.close()
    return dict(r) if r is not None else None


def 통과() -> bool:
    """게이트가 열렸나 — 최신 판정이 '정상' 일 때만 참 (D-09 1회성)."""
    최신 = 최신판정()
    return bool(최신) and 최신.get("판정") == "정상"


# ── 쓰기 ────────────────────────────────────────────────────────────────────

def 판정기록(판정: str, 판매자상품코드: str, productId: str, commit_job_id: str,
          스토어교체여부: str | None, 메모: str | None) -> None:
    """사람 판정 한 줄을 **덧붙인다.** 같은 상품을 다시 판정해도 이전 줄은 남는다.

    값 검증의 진짜 관문은 라우트의 Pydantic 이다. 다만 판정 값과 빈 키는 여기서 한 번 더
    본다 — 아무 글자나 들어가면 `통과()` 가 조용히 닫힌 채로 남고, 사람은 이유를 모른다.
    """
    if 판정 not in 판정허용값:
        raise ValueError(f"판정 값이 허용값 {판정허용값} 밖이다: {판정!r}")
    코드 = str(판매자상품코드 or "").strip()
    pid = str(productId or "").strip()
    잡 = str(commit_job_id or "").strip()
    if not 코드:
        raise ValueError("판매자상품코드가 비었다 — 어느 상품을 보고 판정했는지 남지 않는다")
    if not pid:
        raise ValueError("productId 가 비었다 — 어느 상품을 보고 판정했는지 남지 않는다")
    if not 잡:
        raise ValueError("commit_job_id 가 비었다 — 어느 반영을 보고 판정했는지 남지 않는다")

    cx = _conn()
    try:
        cx.execute(
            "INSERT INTO market_gate "
            "(판정, 기록시각, 판매자상품코드, productId, commit_job_id, 스토어교체여부, 메모) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (판정, _now(), 코드, pid, 잡, str(스토어교체여부 or ""), str(메모 or "")))
        cx.commit()
    finally:
        cx.close()
