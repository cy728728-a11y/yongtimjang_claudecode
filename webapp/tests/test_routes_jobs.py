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
import json
import sys
from datetime import datetime

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


# ── 불사자 잡 3종 (Phase 3) ─────────────────────────────────────────────────
# 실제 MCP 는 한 번도 안 뜬다. 여기서 보는 건 라우터가 하는 세 가지뿐이다:
# 대상을 **서버가** 만드는가 · 예외를 맞는 상태코드로 번역하는가 · GET 이 아닌가.

불사자경로 = ("/jobs/bulsaja/profile", "/jobs/bulsaja/scan", "/jobs/bulsaja/index")


@pytest.fixture
def 프로필(tmp_path, monkeypatch):
    """계정 확인 산출물을 tmp 에 깔아 주는 팩토리. 기본은 **일치**.

    실제 저장소 루트의 `webapp-profile.json` 을 읽으면 이 테스트가 개발 PC 의
    실제 로그인 상태에 따라 갈린다 — 그건 검증이 아니라 점괘다.
    """
    from webapp import bulsaja_index

    경로 = tmp_path / "profile.json"
    monkeypatch.setattr(bulsaja_index, "profile_path", lambda: 경로)

    def _깔기(닉: str = "zz기대닉", 크레딧: str = "1,000크레딧"):
        경로.write_text(json.dumps({
            "닉네임": 닉, "크레딧": 크레딧,
            "확인시각": datetime.now().astimezone().isoformat(timespec="seconds"),
        }, ensure_ascii=False), encoding="utf-8")
        return 경로

    _깔기.경로 = 경로
    return _깔기


@pytest.fixture
def 기대닉(monkeypatch):
    """`expected_bulsaja_nick` 을 가짜 값으로 고정한다.

    실제 workspace.toml 값을 읽으면 이 테스트가 **PC 설정에 따라** 갈린다.
    가짜 닉은 `zz` 로 시작한다 — 픽스처 익명화와 같은 규약이다.
    """
    진짜 = settings.cfg

    def 가짜(dotted, default=None, required=False):
        if dotted == "expected_bulsaja_nick":
            return "zz기대닉"
        return 진짜(dotted, default, required)

    monkeypatch.setattr(settings, "cfg", 가짜)
    return "zz기대닉"


def _회차판정_갈아끼우기(run_dir, 판정: dict):
    """tmp 회차의 `result.json` 을 통째로 바꾼다.

    `tmp_run_dir` 이 깔아 주는 `result_min.json` 에는 ③⑤ 행이 **4건 있다** —
    그래서 "대상 0건" 도 "대상이 있다" 도 이 헬퍼로 직접 만든다.
    """
    (run_dir / "result.json").write_text(
        json.dumps(판정, ensure_ascii=False), encoding="utf-8")
    return run_dir


def test_불사자_라우트는_토큰없이_안된다(화면, 엿듣기):
    """T-3-25 — 세 경로 전부 쓰기 취급이다. 읽기 잡이어도 기동은 쓰기 행위다."""
    for 경로 in 불사자경로:
        응답 = 화면.post(경로, json={}, headers={"X-CT-Token": "wrong-token"})
        assert 응답.status_code == 403, 경로
    assert not 엿듣기, "토큰이 틀렸는데 작업 생성까지 갔다"


def test_불사자_라우트는_타사이트_origin_도_403(화면, 엿듣기):
    """CSRF — 남의 탭이 수 시간짜리 인덱스 잡을 띄우지 못한다."""
    for 경로 in 불사자경로:
        응답 = 화면.post(경로, json={}, headers={"Origin": "https://evil.com"})
        assert 응답.status_code == 403, 경로
    assert not 엿듣기


def test_불사자_라우트는_GET이_아니다(화면):
    """T-3-25 — GET 이면 `Origin` 이 없는 교차 사이트 요청이 그대로 통과한다.

    405 여야 한다. 200 이면 방어가 통째로 죽은 것이고, 404 면 라우트가 사라진 것이다.
    """
    for 경로 in 불사자경로:
        assert 화면.get(경로).status_code == 405, 경로


def test_계정불일치면_409(화면, 프로필, 기대닉, tmp_run_dir):
    """ENG-08 / T-3-26 — `AccountMismatchError` 가 400 이 아니라 409 다.

    🔴 이게 400 으로 떨어지면 `except` 순서가 뒤집힌 것이다
    (`AccountMismatchError` 는 `ValueError` 상속이다). 그러면 "모르는 회차" 와
    구분이 사라져 화면이 "회차를 다시 골라라" 로 잘못 안내한다.

    ⚠️ 계정 가드는 **라우트가 아니라 `create_job` 안**에 있다(D-17 — v2 스케줄러가
    같은 함수를 부른다). 그래서 라우트의 앞단 검사(회차·대상 계산)를 **통과해야**
    가드에 도달한다. 대상이 있는 회차로 때리는 이유가 그것이다.
    그리고 **`엿듣기` 를 일부러 안 쓴다** — 그 픽스처는 `create_job` 을 가로채
    `kind="synthetic"` 으로 바꾸므로 가드가 통째로 우회된다. 여기서는 진짜
    `create_job` 이 돌아야 이 테스트가 무언가를 검증한다.
    """
    _회차판정_갈아끼우기(tmp_run_dir, {"accounts": {"zz01": {"rules": {
        "③원인분석": [{"mallProductId": "19999999991", "adGroup": "판매상품_15-2_zzfake"}]}}}})
    프로필(닉="zz다른계정")          # 붙어 있는 계정이 기대와 다르다

    # 계정 확인 잡은 일부러 가드를 안 탄다(닭·달걀) — 가드를 타는 스캔으로 때린다.
    응답 = 화면.post("/jobs/bulsaja/scan", json={"run_dir": tmp_run_dir.name})
    assert 응답.status_code == 409, 응답.text
    사유 = 응답.json()["detail"]

    # 기대 닉네임도 붙어 있는 닉네임도 싣지 않는다 (T-3-29)
    assert "zz기대닉" not in 사유
    assert "zz다른계정" not in 사유
    assert "계정" in 사유
    # 거부됐으니 잡이 하나도 안 생겼다 — 자식도 안 떴다
    assert jobs.recent_jobs(50) == [], "계정이 다른데 잡을 만들었다"


def test_인덱스는_순서검사를_먼저_본다(화면, 프로필, 기대닉, 엿듣기, tmp_run_dir):
    """계정이 달라도 **스캔이 없으면** 인덱스는 "스캔 먼저" 로 막힌다 — 둘 다 409 다.

    계정 가드가 `create_job` 안에 있어서 생기는 순서다. 사용자 입장에서 막히는
    사실과 상태코드가 같고, 계정이 다르다는 것은 **보드 상단 배너**가 상시로 말한다.
    스캔을 누르면 그때 계정 사유가 정확히 뜬다.
    """
    프로필(닉="zz다른계정")
    응답 = 화면.post("/jobs/bulsaja/index", json={"run_dir": tmp_run_dir.name})
    assert 응답.status_code == 409, 응답.text
    assert "스캔" in 응답.json()["detail"]
    assert not 엿듣기


def test_계정이_맞으면_계정확인_잡이_뜬다(화면, 프로필, 기대닉):
    """닭·달걀 — 계정 확인 잡의 가드 제외 여부는 `jobs.BULSAJA_KINDS` 가 정한다.

    여기서는 "맞는 계정에서 라우트가 막지 않는다" 만 본다.
    """
    프로필()                          # 기대 계정과 같다
    응답 = 화면.post("/jobs/bulsaja/profile", json={})
    assert 응답.status_code == 200, 응답.text


def test_스캔은_회차가_없으면_400(화면, 프로필, 기대닉, 엿듣기):
    프로필()
    응답 = 화면.post("/jobs/bulsaja/scan", json={})
    assert 응답.status_code == 400
    assert "회차" in 응답.json()["detail"]
    assert not 엿듣기


def test_스캔은_대상이_없으면_400(화면, 프로필, 기대닉, 엿듣기, tmp_run_dir):
    """빈 대상으로 잡을 만들지 않는다 — 실패 잡이 화면에서 오독된다.

    입력은 ①노출0 만 있는 회차다. CLI 도 `exit 2` 로 거부하지만(2층 방어),
    그 잡은 레지스트리에 `failed` 로 남아 "인덱스가 비었나?" 로 읽힌다.
    """
    _회차판정_갈아끼우기(tmp_run_dir, {"accounts": {"zz01": {"rules": {
        "①노출0": [{"mallProductId": "19999999999"}]}}}})
    프로필()
    응답 = 화면.post("/jobs/bulsaja/scan", json={"run_dir": tmp_run_dir.name})
    assert 응답.status_code == 400, 응답.text
    assert "③" in 응답.json()["detail"]
    assert not 엿듣기, "대상 0건인데 잡을 만들었다"


def test_스캔_대상은_서버가_회차에서_만든다(화면, 프로필, 기대닉, 엿듣기, tmp_run_dir):
    """D-11 — 화면이 고른 행 목록을 받지 않는다. 회차 판정이 정본이다.

    `only_ads` 에 `"<alias>|<mallProductId>"` 키가 그대로 실린다 (03-03 계약).
    """
    _회차판정_갈아끼우기(tmp_run_dir, {"accounts": {"zz01": {"rules": {
        "③원인분석": [{"mallProductId": "111"}, {"mallProductId": "222"}],
        "⑤효자확정": [{"mallProductId": "222"}],      # ③과 겹친다 — 한 번만 나가야 한다
        "①노출0": [{"mallProductId": "999"}],         # 대상이 아니다
    }}}})
    프로필()
    응답 = 화면.post("/jobs/bulsaja/scan",
                    json={"run_dir": tmp_run_dir.name, "only_ads": ["나쁜것"]})
    assert 응답.status_code == 200, 응답.text
    assert 엿듣기["kind"] == "bulsaja_scan"
    assert 엿듣기["run_dir"] == tmp_run_dir.name
    assert 엿듣기["only_ads"] == ["zz01|111", "zz01|222"]
    assert "나쁜것" not in 엿듣기["only_ads"], "클라이언트가 보낸 대상이 섞였다"


def test_인덱스는_스캔없이_409(화면, 프로필, 기대닉, 엿듣기, tmp_run_dir):
    """순서 문제라 409 다 — 요청은 멀쩡하다.

    마켓그룹 목록 없이 돌리면 대상이 빈 목록이 되고, 그걸 "전량" 으로 읽는 경로가
    하나라도 생기면 인덱스가 통째로 다시 돈다.
    """
    프로필()
    응답 = 화면.post("/jobs/bulsaja/index", json={"run_dir": tmp_run_dir.name})
    assert 응답.status_code == 409, 응답.text
    assert "스캔" in 응답.json()["detail"]
    assert not 엿듣기


def test_인덱스_대상은_서버가_만든다(화면, 프로필, 기대닉, tmp_run_dir):
    """D-11 / T-3-27 — 클라이언트가 그룹을 지정할 **인자가 아예 없다.**

    모델에 필드가 없는 것이 이 방어의 전부다. 있으면 언젠가 채워진다.
    """
    from webapp.routes.jobs import JobReq

    필드 = set(JobReq.model_fields)
    assert 필드 == {"run_dir", "accounts"}, f"JobReq 에 필드가 늘었다: {필드}"
    for 금지 in ("groups", "group_ids", "groupId", "only_ads", "targets", "kind"):
        assert 금지 not in 필드, f"클라이언트가 '{금지}' 를 지정할 수 있게 됐다"

    # 본문에 그룹을 실어 보내도 그대로 무시된다 — 모델이 안 받는다.
    프로필()
    응답 = 화면.post("/jobs/bulsaja/index",
                    json={"run_dir": tmp_run_dir.name, "groups": ["9999999"]})
    assert 응답.status_code == 409          # 스캔이 없어서 막힌다 (그룹 때문이 아니다)
    assert "9999999" not in 응답.text


def test_스캔대상키는_중복을_없애고_순서를_지킨다():
    """같은 상품이 ③과 ⑤에 동시에 있으면 한 번만 조회한다 (레이트리밋 예산)."""
    from webapp.routes.jobs import _스캔대상키

    판정 = {"accounts": {"zz01": {"rules": {
        "③원인분석": [{"mallProductId": "111"}, {"mallProductId": "222"}],
        "⑤효자확정": [{"mallProductId": "222"}, {"mallProductId": "333"}],
        "①노출0": [{"mallProductId": "999"}],        # 대상이 아니다
    }}}}
    assert _스캔대상키(판정) == ["zz01|111", "zz01|222", "zz01|333"]

    # mallProductId 가 없는 행은 조용히 건너뛴다 — 키가 "zz01|None" 이 되면 안 된다
    assert _스캔대상키({"accounts": {"zz01": {"rules": {
        "③원인분석": [{"adGroup": "zzfake"}]}}}}) == []
    assert _스캔대상키({}) == []
    assert _스캔대상키(None) == []


def test_불사자_라우트_목차가_docstring_에_있다():
    """이 파일의 라우트 목록이 목차다 — 빠지면 다음 사람이 경로를 못 찾는다."""
    from webapp.routes import jobs as 라우터

    문서 = 라우터.__doc__ or ""
    for 경로 in 불사자경로:
        assert 경로 in 문서, f"{경로} 가 목차에 없다"
