#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""작업 라우터(`webapp/routes/jobs.py`) 검증 — **실제 CLI 는 한 번도 안 뜬다.**

라우터가 하는 일은 셋뿐이다: 요청 풀기 · 예외를 상태코드로 번역 · 응답 모양 고르기.
그래서 이 파일은 `jobs.create_job` 을 가로채 **무엇이 넘어갔는지**만 본다 —
작업 생성 로직은 `test_jobs.py` 가 본다. 가로채지 않으면 `POST /jobs/prep` 한 번이
네이버 광고 API 에 수 분짜리 수집을 걸어 버린다.

겨누는 위협:
  T-1-01b  작업 생성이 전부 POST 이고 GET 은 아무것도 만들지 않는다
  T-1-02   토큰 없는 쓰기는 403
  T-1-23   클라이언트가 작업 종류·argv 를 고르지 못한다
  T-1-09   이미 도는 쓰기 작업은 409 로 거부되고 **사유가 몸통에 실린다**
"""
import sys

import pytest

from webapp import jobs, security, settings

합성 = [sys.executable, "-c", "pass"]


@pytest.fixture
def 화면(client, tmp_path, monkeypatch):
    """보드에서 온 것처럼 쿠키까지 붙인 클라이언트 + tmp 잡 DB."""
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.setattr(settings, "JOB_LOG_DIR", str(tmp_path / "logs"))
    jobs.init_db()
    client.cookies.set(security.COOKIE_NAME, security.BOOT_TOKEN)
    yield client
    for proc in list(jobs._PROCS.values()):
        try:
            proc.kill()
        except Exception:
            pass
    jobs._PROCS.clear()


@pytest.fixture
def 엿듣기(monkeypatch):
    """`create_job` 호출 인자를 붙잡고, 진짜 CLI 대신 합성 잡을 태운다."""
    본것 = {}
    진짜 = jobs.create_job

    def 가짜(kind, **kw):
        본것.clear()
        본것.update({"kind": kind, **kw})
        return 진짜("synthetic", argv_override=합성)

    monkeypatch.setattr(jobs, "create_job", 가짜)
    return 본것


def test_토큰_없는_작업생성은_403(화면, 엿듣기):
    """SAFE-02 — 부팅 토큰 없이는 아무 작업도 못 만든다."""
    응답 = 화면.post("/jobs/prep", json={}, headers={"X-CT-Token": "wrong-token"})
    assert 응답.status_code == 403
    assert not 엿듣기, "토큰이 틀렸는데 작업 생성까지 갔다"


def test_타사이트_origin_은_토큰이_맞아도_403(화면, 엿듣기):
    """SAFE-01 — 다른 탭이 쏘는 쓰기(CSRF). 토큰이 새도 여기서 막힌다."""
    응답 = 화면.post("/jobs/prep", json={}, headers={"Origin": "https://evil.com"})
    assert 응답.status_code == 403
    assert not 엿듣기


def test_모르는_회차는_400(화면, monkeypatch):
    """T-1-11 — 회차 화이트리스트는 `create_job` 안에 있다. 라우트는 번역만 한다."""
    응답 = 화면.post("/jobs/run", json={"run_dir": "없는회차"})
    assert 응답.status_code == 400
    assert "회차" in 응답.json()["detail"]


def test_나쁜_계정_alias_는_400(화면, 엿듣기):
    """Pydantic 이 관문이다. 셸 메타문자가 argv 근처에도 못 간다 (T-1-10)."""
    응답 = 화면.post("/jobs/prep", json={"accounts": ["good", "bad;rm -rf /"]})
    assert 응답.status_code == 400
    assert not 엿듣기


def test_작업종류와_argv_를_클라이언트가_못_고른다(화면, 엿듣기):
    """T-1-23 — 합성 잡(임의 argv)은 운영 라우트에서 닿을 수 없다.

    `kind`·`argv_override` 를 본문에 실어 보내도 모델에 없는 필드라 무시된다.
    라우트마다 kind 가 **고정**이라는 것이 이 방어의 전부다.
    """
    응답 = 화면.post("/jobs/prep", json={
        "kind": "synthetic",
        "argv_override": ["/bin/sh", "-c", "echo pwned"],
        "commit": True,
    })
    assert 응답.status_code == 200
    assert 엿듣기["kind"] == "prep"
    assert "argv_override" not in 엿듣기
    assert "commit" not in 엿듣기


def test_이미_도는_쓰기작업은_409(화면):
    """Pitfall 3 / T-1-09 — 화면에 사유가 뜨도록 몸통에 이유를 싣는다."""
    돌고있는것 = jobs.create_job(
        "prep", argv_override=[sys.executable,
                               "webapp/tests/fixtures/synthetic_job.py", "40", "0.2", "0"])

    응답 = 화면.post("/jobs/prep", json={})
    assert 응답.status_code == 409
    사유 = 응답.json()["detail"]
    assert 돌고있는것 in 사유 and "끝나고 다시" in 사유

    # 쓰기가 아닌 판정은 같은 상황에서도 열려 있다
    assert 화면.post("/jobs/run", json={}).status_code in (200, 400)


def test_상태_GET_은_작업을_만들지_않는다(화면):
    """T-1-01b — 읽기 라우트가 부수효과를 가지면 Origin 방어의 전제가 무너진다."""
    job_id = jobs.create_job("synthetic", argv_override=합성)
    처음 = len(jobs.recent_jobs(50))

    for _ in range(3):
        assert 화면.get(f"/jobs/{job_id}").status_code == 200
        assert 화면.get("/jobs").status_code == 200

    assert len(jobs.recent_jobs(50)) == 처음


def test_상태_JSON_은_화이트리스트다(화면):
    """SAFE-03 투영 — 행을 통째로 내보내지 않는다. argv·내부 경로는 화면 밖이다."""
    job_id = jobs.create_job("synthetic", argv_override=합성)
    몸통 = 화면.get(f"/jobs/{job_id}").json()

    assert set(몸통) == {"id", "kind", "status", "exit_code", "started_at",
                         "ended_at", "run_dir", "target_count", "elapsed_sec"}
    assert "argv" not in 몸통 and "log_path" not in 몸통


def test_htmx_요청에는_화면조각이_온다(화면):
    """같은 엔드포인트가 htmx 에는 HTML, 그 외에는 JSON 을 준다.

    **폴링이 받는 조각은 패널 전체가 아니라 상태 문단이다** (Plan 01-06 에서 바뀌었다).
    패널 전체를 2초마다 갈아끼우면 그 안의 SSE 커넥션이 2초마다 끊겼다 붙어
    로그가 계속 처음부터 다시 그려진다 — 조각을 쪼갠 이유가 그거다.
    """
    job_id = jobs.create_job("synthetic", argv_override=합성)
    조각 = 화면.get(f"/jobs/{job_id}", headers={"HX-Request": "true"}).text

    assert '<div id="job-status"' in 조각
    assert '<section id="job-panel"' not in 조각, "폴링이 패널 전체를 갈아끼운다 — SSE 가 끊긴다"
    assert "sse-connect" not in 조각, "폴링 조각이 스트림을 다시 연다"
    assert f'hx-get="/jobs/{job_id}"' in 조각      # 도는 동안 2초 폴링
    assert 'hx-trigger="every 2s"' in 조각


def test_작업을_만들면_패널_전체가_온다(화면, 엿듣기):
    """POST 응답은 패널 전체다 — 그래야 **새 작업의** 스트림이 열린다."""
    조각 = 화면.post("/jobs/prep", json={}, headers={"HX-Request": "true"}).text

    assert '<section id="job-panel"' in 조각
    assert '<div id="job-status"' in 조각
    assert 조각.count("sse-connect") == 1


def test_끝난_작업은_폴링을_멈춘다(화면):
    """`done` 응답에는 hx-trigger 가 아예 없다 — 끄는 코드를 따로 두지 않는다."""
    job_id = jobs.create_job("synthetic", argv_override=합성)
    jobs._PROCS[job_id].wait(timeout=10)

    조각 = 화면.get(f"/jobs/{job_id}", headers={"HX-Request": "true"}).text
    assert "hx-trigger" not in 조각
    assert "끝남" in 조각


def test_없는_작업은_404(화면):
    assert 화면.get("/jobs/no-such-job").status_code == 404


def test_쿠키_없이는_상태를_못_본다(client, tmp_path, monkeypatch):
    """페이지 접근은 쿠키로 막는다 (`/healthz` 만 예외)."""
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.setattr(settings, "JOB_LOG_DIR", str(tmp_path / "logs"))
    jobs.init_db()
    client.cookies.clear()

    assert client.get("/jobs").status_code == 403
    assert client.get("/jobs/anything").status_code == 403
