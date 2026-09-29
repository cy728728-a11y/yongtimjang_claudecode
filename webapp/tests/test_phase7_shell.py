#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 7 공유 자리(07-01) — 보드 버튼·패널·스크립트 태그 · 결과표 디스패치.

트랙 플랜(07-04 썸네일 · 07-05 쿠팡)이 공유 파일을 안 건드리고 붙을 **자리**가 있는지만 본다.
자식을 띄우지 않는다. 잡 DB 는 tmp(`화면`)다.
"""
import sqlite3
import uuid
from datetime import datetime

import pytest

from webapp import jobs, paths
from webapp.routes import coupang as 쿠팡트랙
from webapp.routes import thumb as 썸네일트랙
from webapp.tests.test_routes_jobs import 화면  # noqa: F401


def _행박기(kind: str) -> str:
    job_id = str(uuid.uuid4())
    때 = datetime.now().astimezone().isoformat(timespec="seconds")
    cx = sqlite3.connect(jobs.db_path())
    try:
        cx.execute("INSERT INTO jobs (id, kind, accounts, argv, status, exit_code, log_path, "
                   "started_at, ended_at) VALUES (?,?,?,?,?,?,?,?,?)",
                   (job_id, kind, "[]", "[]", "done", 0, "x.log", 때, 때))
        cx.commit()
    finally:
        cx.close()
    return job_id


def test_보드에_썸네일_버튼과_쿠팡_패널_스크립트가_있다(화면, tmp_run_dir):
    본문 = 화면.get(f"/?run_dir={tmp_run_dir.name}").text
    assert 'id="thumb-estimate-btn"' in 본문
    assert "썸네일 견적 — 크레딧 0" in 본문
    assert 'id="thumb-estimate"' in 본문 and 'id="thumb-estimate-body"' in 본문
    assert 'id="coupang"' in 본문
    assert 'id="coupang-preview-btn"' in 본문
    assert 'id="coupang-body"' in 본문 and 'id="coupang-preview-job"' in 본문
    assert "/static/thumb.js" in 본문 and "/static/coupang.js" in 본문
    # 트랙 JS 는 board.js 뒤다 — window.관제탑 훅이 먼저 있어야 한다
    assert 본문.index("/static/board.js") < 본문.index("/static/thumb.js")
    assert 본문.index("/static/board.js") < 본문.index("/static/coupang.js")


def test_트랙_버튼은_배선_전까지_disabled_다(화면, tmp_run_dir):
    본문 = 화면.get(f"/?run_dir={tmp_run_dir.name}").text
    for 버튼id in ("thumb-estimate-btn", "coupang-preview-btn"):
        i = 본문.index(f'id="{버튼id}"')
        태그 = 본문[본문.rfind("<", 0, i):본문.index(">", i)]
        assert "disabled" in 태그, f"{버튼id} 가 disabled 가 아니다"


def test_회차가_없어도_쿠팡_패널은_뜬다(화면, monkeypatch):
    monkeypatch.setattr(paths, "scan_runs", lambda: [])
    본문 = 화면.get("/").text
    assert 'id="coupang"' in 본문
    assert 'id="thumb-estimate-btn"' not in 본문   # 썸네일 견적은 회차가 필요하다


def test_결과표_디스패치는_트랙_등록을_따른다(화면, monkeypatch):
    monkeypatch.setitem(썸네일트랙.결과표, "thumb_estimate",
                        ("_x.html", lambda 상태: {"트랙표": "썸네일", "id": 상태["id"]}))
    monkeypatch.setitem(쿠팡트랙.결과표, "coupang_preview",
                        ("_y.html", lambda 상태: {"트랙표": "쿠팡"}))
    잡 = _행박기("thumb_estimate")
    r = 화면.get(f"/jobs/{잡}/result")
    assert r.status_code == 200
    assert r.json() == {"트랙표": "썸네일", "id": 잡}
    r2 = 화면.get(f"/jobs/{_행박기('coupang_preview')}/result")
    assert r2.json() == {"트랙표": "쿠팡"}


def test_결과표_병합은_기존_키를_덮지_못한다(화면, monkeypatch):
    """트랙 모듈이 기존 kind 를 등록해도 기존 표가 이긴다 (T-07-06)."""
    monkeypatch.setitem(썸네일트랙.결과표, "bids_commit",
                        ("_x.html", lambda 상태: {"트랙표": "가로챔"}))
    monkeypatch.setitem(쿠팡트랙.결과표, "market_preview",
                        ("_x.html", lambda 상태: {"트랙표": "가로챔"}))
    for kind in ("bids_commit", "market_preview"):
        r = 화면.get(f"/jobs/{_행박기(kind)}/result")
        assert "가로챔" not in r.text


def test_트랙_라우터_모듈은_빈_결과표로_시작한다():
    """07-01 은 자리만 깐다 — 채우는 건 07-04 · 07-05 다."""
    assert 썸네일트랙.결과표 == {}
    assert 쿠팡트랙.결과표 == {}
    assert 썸네일트랙.router is not 쿠팡트랙.router


@pytest.mark.parametrize("kind, 이름", [("thumb_estimate", "썸네일 견적"),
                                       ("coupang_preview", "쿠팡 후보 뽑기"),
                                       ("coupang_commit", "쿠팡 복사")])
def test_잡_상태_조각에_phase7_이름이_있다(kind, 이름):
    from webapp.main import templates
    t = templates.env.get_template("_job_status.html")
    html = t.render(job={"id": "x", "kind": kind, "status": "failed", "exit_code": 3,
                         "elapsed_sec": None, "run_dir": None, "target_count": None})
    assert 이름 in html
    assert "부분 실패" in html
