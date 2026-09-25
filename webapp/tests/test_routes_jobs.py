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
from pathlib import Path

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


def test_인덱스는_작업대상_행으로만_대상을_고른다(화면, 프로필, 기대닉, 엿듣기, tmp_run_dir):
    """🔴 비용 회귀 — `fold_products` 는 **6규칙 전부**를 접는다 (실측 6,945행).

    안 좁히면 `index_targets` 가 작업 대상이 하나도 없는 마켓그룹까지 집어
    **수 시간을 더 훑는다** (실측 2026-09-20 회차: 30그룹 → 40그룹).
    D-18 이 2시간 7분을 깎아 낸 바로 그 비용이 도로 붙는다.

    여기서는 ③ 행 1개와 ① 행 1개가 **서로 다른 마켓그룹**에 걸리게 만들어,
    대상에 ③ 쪽 그룹 하나만 들어오는지 본다.
    """
    # ⚠️ `adId` 를 반드시 서로 다르게 준다. `board._dedupe_ads` 가 adId 로 접으므로
    #    둘 다 없으면 `None` 키로 **한 줄로 뭉개져** 이 테스트가 통과하는 척만 한다
    #    (실제로 그랬다 — 네거티브 확인에서 잡았다).
    _회차판정_갈아끼우기(tmp_run_dir, {"accounts": {"zz01": {"rules": {
        "③원인분석": [{"adId": "nad-aaa", "mallProductId": "111",
                    "adGroup": "판매상품_15-2_zzfakeA"}],
        "①노출0": [{"adId": "nad-bbb", "mallProductId": "222",
                  "adGroup": "판매상품_20-3_zzfakeB"}],
    }}}})
    조인 = {"마켓그룹": [{"groupId": "9000001", "그룹명": "zzfake15-2"},
                      {"groupId": "9000002", "그룹명": "zzfake20-3"}],
           "제외그룹": None, "행": []}
    잡 = tmp_run_dir.parent.parent.parent / "scan_out.json"
    잡.write_text(json.dumps(조인, ensure_ascii=False), encoding="utf-8")

    진짜 = jobs.latest_done
    try:
        jobs.latest_done = lambda kind, run_dir=None: (
            {"result_path": str(잡)} if kind == "bulsaja_scan" else 진짜(kind, run_dir))
        프로필()
        응답 = 화면.post("/jobs/bulsaja/index", json={"run_dir": tmp_run_dir.name})
    finally:
        jobs.latest_done = 진짜

    assert 응답.status_code == 200, 응답.text
    assert 엿듣기["kind"] == "bulsaja_index"
    # ③ 쪽 그룹만 들어온다. ①노출0 의 그룹이 섞이면 이 회귀가 깨진 것이다.
    assert 엿듣기["only_ads"] == ["9000001"], "①노출0 의 마켓그룹까지 훑는다"


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
    for 경로 in (*불사자경로, 배너경로):
        assert 경로 in 문서, f"{경로} 가 목차에 없다"


# ── 배너 스캔 라우트 (Phase 4 / BANNER-01) ──────────────────────────────────
#
# 실제 스캐너는 한 번도 안 뜬다. 4분 12초 · CDN 271MB 짜리라 한 번만 새도 비싸다.

배너경로 = "/jobs/banner/scan"


@pytest.fixture
def 안띄운다(monkeypatch):
    """`jobs.spawn` 을 가짜로 바꾼다 — 가드만 겨누는 테스트가 진짜 자식을 안 띄우게.

    `엿듣기` 와 다르다: 저쪽은 `create_job` 자체를 가로채 `kind="synthetic"` 으로
    바꾸므로 **중복 가드가 통째로 우회된다.** `SINGLETON_KINDS` 회귀는 진짜
    `create_job` 이 돌아야 무언가를 검증한다.
    """
    class 가짜프로세스:
        def __init__(self, argv):
            self.argv = argv
            self.pid = 999_000 + len(argv)

        def poll(self):
            return None

        def kill(self):
            pass

    monkeypatch.setattr(jobs, "spawn", lambda argv_list, log_path: 가짜프로세스(argv_list))


@pytest.fixture
def 직전조인(tmp_run_dir, monkeypatch):
    """직전 성공 조인 스캔이 남긴 산출물을 깔고 `latest_done` 이 그걸 가리키게 한다.

    잡 레지스트리에 진짜 행을 넣지 않고 `latest_done` 을 돌린다 — 이 테스트가 보는
    것은 "라우트가 **레지스트리에** 물어보는가" 이지 레지스트리 자체가 아니다
    (그건 `test_jobs.py::test_latest_done_은_성공한_잡만_준다` 가 본다).
    """
    def _깔기(있게: bool = True):
        if not 있게:
            monkeypatch.setattr(jobs, "latest_done", lambda kind, run_dir=None: None)
            return None
        산출물 = tmp_run_dir / "web" / "join_zzprev.json"
        산출물.parent.mkdir(parents=True, exist_ok=True)
        산출물.write_text(json.dumps({"행": []}, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(jobs, "latest_done", lambda kind, run_dir=None: (
            {"result_path": str(산출물)} if kind == "bulsaja_scan" else None))
        return 산출물
    return _깔기


def test_배너스캔은_토큰없이_안된다(화면, 엿듣기):
    """SAFE-02 / T-1-02 — 토큰이 틀리면 **자식이 안 뜬다.**

    상태코드만 보면 "막혔다" 를 증명 못 한다. `엿듣기` 가 비어 있어야 작업 생성까지
    가지도 않았다는 뜻이다.
    """
    응답 = 화면.post(배너경로, json={}, headers={"X-CT-Token": "wrong-token"})
    assert 응답.status_code == 403
    assert not 엿듣기, "토큰이 틀렸는데 작업 생성까지 갔다"


def test_배너스캔은_타사이트_origin_도_403(화면, 엿듣기):
    """SAFE-01 / T-4-05 — 남의 탭이 열려 있다는 이유로 4분짜리 잡이 뜨지 않는다."""
    응답 = 화면.post(배너경로, json={}, headers={"Origin": "https://evil.com"})
    assert 응답.status_code == 403
    assert not 엿듣기


def test_배너스캔은_GET이_아니다(화면):
    """T-1-01b — GET 이면 `Origin` 없는 교차 사이트 요청이 그대로 통과한다.

    405 여야 한다. 200 이면 방어가 통째로 죽은 것이고, 404 면 라우트가 사라진 것이다.
    """
    assert 화면.get(배너경로).status_code == 405


def test_배너스캔은_조인_없이_409(화면, 엿듣기, 직전조인, tmp_run_dir):
    """순서 문제라 409 다 — 요청은 멀쩡하다.

    400 으로 내리면 화면이 "요청 값을 고쳐라" 로 안내하는데, 사용자가 할 일은
    조인 스캔 버튼을 먼저 누르는 것뿐이다.
    """
    직전조인(있게=False)
    응답 = 화면.post(배너경로, json={"run_dir": tmp_run_dir.name})
    assert 응답.status_code == 409, 응답.text
    assert "조인 스캔을 먼저 돌려라" in 응답.json()["detail"]
    assert not 엿듣기


def test_배너스캔_대상은_서버가_고른다(화면, 엿듣기, 직전조인, tmp_run_dir):
    """D-11 / T-4-18 — 화면이 고른 행 목록을 받지 않는다.

    대상은 `jobs.latest_done("bulsaja_scan")` 의 `result_path` **하나뿐**이고,
    그것도 새로 쓰지 않고 그 파일을 그대로 가리킨다(`targets_path_override`).
    본문에 목록을 실어 보내도 모델이 안 받는다.
    """
    산출물 = 직전조인()
    응답 = 화면.post(배너경로, json={"run_dir": tmp_run_dir.name,
                                  "targets": ["zz|111"], "only_ads": ["zz|222"]})
    assert 응답.status_code == 200, 응답.text
    assert 엿듣기["kind"] == "banner_scan"
    assert str(엿듣기["targets_path_override"]) == str(산출물)
    # 새로 쓰는 통로(`only_ads`)는 아예 안 쓴다 — 둘을 같이 주면 create_job 이 터진다
    assert "only_ads" not in 엿듣기
    assert "zz|111" not in 응답.text and "zz|222" not in 응답.text


def test_배너스캔_중복은_409(화면, 안띄운다, 직전조인, tmp_run_dir):
    """`SINGLETON_KINDS` 회귀 — 같은 잡 둘이 271MB 를 두 번 받지 않는다.

    **`엿듣기` 를 일부러 안 쓴다.** 그 픽스처는 `create_job` 을 가로채
    `kind="synthetic"` 으로 바꾸므로 중복 가드가 통째로 우회된다.
    """
    직전조인()
    첫번째 = 화면.post(배너경로, json={"run_dir": tmp_run_dir.name})
    assert 첫번째.status_code == 200, 첫번째.text

    두번째 = 화면.post(배너경로, json={"run_dir": tmp_run_dir.name})
    assert 두번째.status_code == 409, 두번째.text
    사유 = 두번째.json()["detail"]
    # 전역 쓰기 락과 헷갈리지 않게 어느 kind 가 막았는지 밝힌다
    assert "banner_scan" in 사유


def test_배너스캔이_도는_동안_쓰기버튼이_안_막힌다(화면, 안띄운다, 직전조인, tmp_run_dir):
    """🔴 T-4-19 — 라우트 층에서 확인하는 행동 회귀.

    `test_jobs.py` 가 집합과 `create_job` 을 본다면 여기는 **실제 HTTP 응답**을 본다.
    4분 동안 입찰가 인상이 409 가 되면 사람이 가드를 끈다.
    """
    직전조인()
    assert 화면.post(배너경로, json={"run_dir": tmp_run_dir.name}).status_code == 200

    쓰기 = 화면.post("/jobs/prep", json={})
    assert 쓰기.status_code == 200, f"배너 스캔이 쓰기 버튼을 막았다: {쓰기.text}"


# ── 상세 견적 라우트 (Phase 5 / 05-03) ──────────────────────────────────────
#
# 실제 CLI 는 한 번도 안 뜬다(`안띄운다`). 보는 것: 대상을 **서버가** 다시 계산하는가 ·
# 관문 통과분만 inputs 에 들어가는가 · 예외 번역 · 결과 조각.

견적경로 = "/jobs/detail/estimate"
_생성시각 = "2026-09-25T00:14:25+09:00"


def _상세판정(n: int = 3) -> dict:
    return {"accounts": {"zz01": {"rules": {"③원인분석": [
        {"adId": f"nad-zz{i}", "mallProductId": f"1999999999{i}",
         "adGroup": "판매상품_15-2_zzfake"} for i in range(1, n + 1)]}}}}


def _상세조인(n: int = 3) -> dict:
    return {"마켓그룹": [{"groupId": "zzg1", "그룹명": "15-2_zz"}], "행": [
        {"acct": "zz01", "mallProductId": f"1999999999{i}", "productId": f"zzp{i}",
         "인덱스_smartstore": "s", "관측_smartstore": "s", "미조회": False,
         "uploadDetailContents": None, "그룹태그": [], "판매자상품코드": f"zz0{i}",
         "불사자코드": f"zzb{i}", "타오바오상품번호": f"zzt{i}", "사본": [],
         "팬아웃미조회": False} for i in range(1, n + 1)]}


def _배너상품(i: int, 장수: int = 3, 스킵: str | None = None) -> dict:
    return {"판매자상품코드": f"zz0{i}", "불사자코드": f"zzb{i}", "타오바오상품번호": f"zzt{i}",
            "스킵사유": 스킵, "장": [{"순번": k, "판정": "제품",
                                   "url": f"https://zzcdn.example/{i}_{k}.jpg"}
                                  for k in range(장수)]}


@pytest.fixture
def 상세판(tmp_run_dir, monkeypatch, 프로필, 기대닉):
    """판정·조인·배너 산출물 + 확인시각을 깐다. 기본: zz01 통과 · zz02 낡은 확인 · zz03 스킵."""
    from webapp import banner_store

    _회차판정_갈아끼우기(tmp_run_dir, _상세판정())
    웹 = tmp_run_dir / "web"
    웹.mkdir(parents=True, exist_ok=True)
    조인 = 웹 / "join_zzprev.json"
    조인.write_text(json.dumps(_상세조인(), ensure_ascii=False), encoding="utf-8")
    배너 = 웹 / "banner_zzprev.json"
    배너.write_text(json.dumps({"생성시각": _생성시각, "상품": [
        _배너상품(1, 장수=12), _배너상품(2), _배너상품(3, 스킵="잔여하한")]},
        ensure_ascii=False), encoding="utf-8")
    산출물 = {"bulsaja_scan": str(조인), "banner_scan": str(배너)}
    monkeypatch.setattr(jobs, "latest_done", lambda kind, run_dir=None: (
        {"result_path": 산출물[kind]} if kind in 산출물 else None))
    monkeypatch.setattr(banner_store, "라벨읽기", lambda run_dir: {})
    monkeypatch.setattr(banner_store, "확인시각읽기", lambda run_dir: {
        "zzt1": "2026-09-25T09:00:00+09:00",       # 산출물 뒤 — 통과
        "zzt2": "2026-09-24T09:00:00+09:00",       # 산출물 앞 — 낡은 확인
        "zzt3": "2026-09-25T09:00:00+09:00"})      # 확인했지만 스킵 상품
    프로필()
    return {"run_dir": tmp_run_dir.name, "산출물": 산출물, "조인": 조인, "배너": 배너,
            "키": [f"zz01|1999999999{i}" for i in (1, 2, 3)]}


def test_detail견적_토큰없이_안된다(화면, 엿듣기):
    응답 = 화면.post(견적경로, json={"run_dir": "x", "keys": ["zz01|1"]},
                    headers={"X-CT-Token": "wrong-token"})
    assert 응답.status_code == 403
    assert not 엿듣기


def test_detail견적_타사이트_origin_도_403(화면, 엿듣기):
    응답 = 화면.post(견적경로, json={"run_dir": "x", "keys": ["zz01|1"]},
                    headers={"Origin": "https://evil.com"})
    assert 응답.status_code == 403
    assert not 엿듣기


def test_detail견적_GET이_아니다(화면):
    assert 화면.get(견적경로).status_code == 405


def test_detail견적_계정불일치면_409(화면, 안띄운다, 상세판):
    """진짜 `create_job` 이 돌아야 계정 가드에 닿는다 — `엿듣기` 를 쓰지 않는다."""
    from webapp import bulsaja_index
    bulsaja_index.profile_path().write_text(json.dumps({
        "닉네임": "zz다른계정",
        "확인시각": datetime.now().astimezone().isoformat(timespec="seconds")},
        ensure_ascii=False), encoding="utf-8")
    응답 = 화면.post(견적경로, json={"run_dir": 상세판["run_dir"], "keys": 상세판["키"]})
    assert 응답.status_code == 409, 응답.text
    assert "zz다른계정" not in 응답.json()["detail"]


def test_detail견적_관문통과분만_inputs에(화면, 안띄운다, 상세판):
    """3개 중 낡은 확인 1 · 스킵 1 · 통과 1 → items 1건 · 제외 2건(사유) · 잘림 반영."""
    응답 = 화면.post(견적경로, json={"run_dir": 상세판["run_dir"], "keys": 상세판["키"]})
    assert 응답.status_code == 200, 응답.text
    job_id = 응답.json()["job_id"]
    상태 = jobs.job_status(job_id)
    assert 상태["kind"] == "detail_estimate"
    문서 = json.loads(jobs.targets_path_of(job_id).read_text(encoding="utf-8"))
    assert 문서["선택"] == 3
    assert [x["판매자상품코드"] for x in 문서["items"]] == ["zz01"]
    항목 = 문서["items"][0]
    assert 항목["productId"] == "zzp1"
    assert len(항목["imageUrls"]) == 10 and 항목["제품이미지총수"] == 12 and 항목["잘림"] == 2
    제외 = {x["판매자상품코드"]: x["사유"] for x in 문서["제외"]}
    assert set(제외) == {"zz02", "zz03"}
    assert "다시 확인" in 제외["zz02"]
    assert "스킵" in 제외["zz03"]


def test_detail견적_전부제외면_400(화면, 엿듣기, 상세판):
    """통과 0건이면 잡을 만들지 않고 400 + 상품별 사유."""
    응답 = 화면.post(견적경로, json={"run_dir": 상세판["run_dir"], "keys": 상세판["키"][1:]})
    assert 응답.status_code == 400, 응답.text
    사유 = 응답.json()["detail"]
    assert "zz02" in 사유 and "zz03" in 사유
    assert not 엿듣기


def test_detail견적_배너산출물없으면_409(화면, 엿듣기, 상세판, monkeypatch):
    monkeypatch.setattr(jobs, "latest_done", lambda kind, run_dir=None: (
        {"result_path": 상세판["산출물"]["bulsaja_scan"]} if kind == "bulsaja_scan" else None))
    응답 = 화면.post(견적경로, json={"run_dir": 상세판["run_dir"], "keys": 상세판["키"]})
    assert 응답.status_code == 409
    assert "배너" in 응답.json()["detail"]
    assert not 엿듣기


def test_detail견적_조인산출물없으면_409(화면, 엿듣기, 상세판, monkeypatch):
    monkeypatch.setattr(jobs, "latest_done", lambda kind, run_dir=None: (
        {"result_path": 상세판["산출물"]["banner_scan"]} if kind == "banner_scan" else None))
    응답 = 화면.post(견적경로, json={"run_dir": 상세판["run_dir"], "keys": 상세판["키"]})
    assert 응답.status_code == 409
    assert "조인" in 응답.json()["detail"]
    assert not 엿듣기


def test_detail견적_모르는키는_400(화면, 엿듣기, 상세판):
    """보드에 없는 키 → 400. 클라이언트가 대상을 지어내지 못한다(T-05-10)."""
    응답 = 화면.post(견적경로, json={"run_dir": 상세판["run_dir"],
                                   "keys": [상세판["키"][0], "zz01|18888888888"]})
    assert 응답.status_code == 400
    assert "18888888888" in 응답.json()["detail"]
    assert not 엿듣기


def test_detail견적_키모양과_개수상한(화면, 엿듣기):
    assert 화면.post(견적경로, json={"run_dir": "x", "keys": []}).status_code in (400, 422)
    assert 화면.post(견적경로, json={"run_dir": "x",
                                    "keys": ["--force|1"]}).status_code in (400, 422)
    assert 화면.post(견적경로, json={"run_dir": "x", "keys": [
        f"zz01|{i}" for i in range(201)]}).status_code in (400, 422)
    assert not 엿듣기


def test_detail견적_URL은_클라이언트가_못준다():
    from webapp.routes.jobs import DetailEstimateReq
    assert set(DetailEstimateReq.model_fields) == {"run_dir", "keys"}


def _견적잡_끝남(tmp_run_dir, 견적: dict | None, 상태="done") -> str:
    """detail_estimate 잡 행 하나를 끝난 상태로 박는다(자식 없음)."""
    import sqlite3
    import uuid
    job_id = str(uuid.uuid4())
    웹 = tmp_run_dir / "web"
    폴더 = 웹 / f"detail_{job_id}"
    폴더.mkdir(parents=True, exist_ok=True)
    대상 = 웹 / f"targets_{job_id}.json"
    대상.write_text(json.dumps({"items": [], "선택": 5, "제외": [
        {"판매자상품코드": "zz09", "사유": "재스캔 뒤 다시 확인 안 함"}]}, ensure_ascii=False),
        encoding="utf-8")
    결과 = 폴더 / "estimate.json"
    if 견적 is not None:
        결과.write_text(json.dumps(견적, ensure_ascii=False), encoding="utf-8")
    cx = sqlite3.connect(jobs.db_path())
    try:
        cx.execute("INSERT INTO jobs (id, kind, run_dir, accounts, argv, status, log_path, "
                   "targets_path, result_path, exit_code, started_at) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                   (job_id, "detail_estimate", tmp_run_dir.name, "[]", "[]", 상태,
                    str(tmp_run_dir / "x.log"), str(대상), str(결과),
                    0 if 상태 == "done" else None,
                    # 지금 시각 — 오래된 starting 은 `_reap` 이 죽음으로 거둔다(STARTING_TIMEOUT)
                    datetime.now().astimezone().isoformat(timespec="seconds")))
        cx.commit()
    finally:
        cx.close()
    return job_id


_견적문서 = {"생성시각": "2026-09-25T10:00:01+09:00", "계정": "zz기대닉", "잔액": 1234,
            "per_credit": 5,
            "항목": [{"productId": "zzp1", "판매자상품코드": "zz01", "판정": "접수", "사유": None,
                     "장수": 10, "제품이미지총수": 12, "잘림": 2, "크레딧": 50},
                    {"productId": "zzp4", "판매자상품코드": "zz04", "판정": "기작업",
                     "사유": "zz가공완료 태그", "장수": 0, "제품이미지총수": 3, "잘림": 0,
                     "크레딧": 0}],
            "집계": {"선택": 2, "스킵": 1, "접수": 1, "총장수": 10, "예상크레딧": 50,
                    "잘린상품": 1}}


def test_detail견적_결과조각(화면, tmp_run_dir):
    job_id = _견적잡_끝남(tmp_run_dir, _견적문서)
    응답 = 화면.get(f"/jobs/{job_id}/result", headers={"HX-Request": "true"})
    assert 응답.status_code == 200
    본문 = 응답.text
    for 말 in ("선택", "관문 제외", "기작업 스킵", "접수", "총 장수", "예상 크레딧",
               "잘린 상품", "zz기대닉", "zz01", "zz04", "zz09", "1,234"):
        assert 말 in 본문, 말
    assert "50" in 본문
    # 선택 5 = 웹앱 선택(targets 파일) · 관문 제외 1
    assert "5" in 본문
    # JSON 모양도 같은 값
    j = 화면.get(f"/jobs/{job_id}/result?format=json").json()
    assert j["집계"]["예상크레딧"] == 50 and j["선택"] == 5 and j["관문제외"] == 1


def test_detail견적_도는중이면_표를_안그린다(화면, tmp_run_dir):
    job_id = _견적잡_끝남(tmp_run_dir, None, 상태="starting")
    응답 = 화면.get(f"/jobs/{job_id}/result", headers={"HX-Request": "true"})
    assert 응답.status_code == 200
    assert "예상 크레딧" not in 응답.text
    assert "도는 중" in 응답.text or "만드는 중" in 응답.text


# ── Phase 5 · 05-04 — 접수 · 이어서 확인 · 결과 표 ─────────────────────────────
# 실제 CLI 는 한 번도 안 뜬다. 접수는 진짜로 돌면 크레딧을 태운다 — `엿듣기`(합성 잡) 또는
# `안띄운다`(가짜 spawn) 만 쓴다.

접수경로 = "/jobs/detail/submit"
확인경로 = "/jobs/detail/poll"

_입력두건 = {"items": [
    {"productId": "zzp1", "판매자상품코드": "zz01", "imageUrls": ["https://zzcdn.example/1.jpg"],
     "제품이미지총수": 1, "잘림": 0},
    {"productId": "zzp4", "판매자상품코드": "zz04", "imageUrls": ["https://zzcdn.example/4.jpg"],
     "제품이미지총수": 1, "잘림": 0},
    {"productId": "zzp5", "판매자상품코드": "zz05", "imageUrls": ["https://zzcdn.example/5.jpg"],
     "제품이미지총수": 1, "잘림": 0}], "제외": [], "선택": 3}


def _상세행(tmp_run_dir, kind: str, 상태: str = "done", exit_code: int | None = 0,
           parent: str | None = None, 견적: dict | None = None,
           체크포인트: dict | None = None, 요약: dict | None = None) -> str:
    """detail 잡 행 하나를 박는다(자식 없음). 폴더·targets 는 부모 체인을 따른다."""
    import sqlite3
    import uuid
    job_id = str(uuid.uuid4())
    웹 = tmp_run_dir / "web"
    웹.mkdir(parents=True, exist_ok=True)
    if kind == "detail_estimate":
        견적id = job_id
        대상 = 웹 / f"targets_{job_id}.json"
        대상.write_text(json.dumps(_입력두건, ensure_ascii=False), encoding="utf-8")
    else:
        부모행 = jobs._row(parent)
        대상 = Path(부모행["targets_path"])
        견적id = (parent if kind == "detail_submit" else 부모행["parent_job_id"])
    폴더 = 웹 / f"detail_{견적id}"
    폴더.mkdir(parents=True, exist_ok=True)
    결과 = 폴더 / ("estimate.json" if kind == "detail_estimate" else f"summary_{job_id}.json")
    if kind == "detail_estimate" and 견적 is not None:
        결과.write_text(json.dumps(견적, ensure_ascii=False), encoding="utf-8")
    if 요약 is not None:
        결과.write_text(json.dumps(요약, ensure_ascii=False), encoding="utf-8")
    if 체크포인트 is not None:
        (폴더 / "detail_status.json").write_text(json.dumps(체크포인트, ensure_ascii=False),
                                                 encoding="utf-8")
    cx = sqlite3.connect(jobs.db_path())
    try:
        cx.execute("INSERT INTO jobs (id, kind, run_dir, accounts, argv, status, log_path, "
                   "targets_path, result_path, parent_job_id, exit_code, started_at) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                   (job_id, kind, tmp_run_dir.name, "[]", "[]", 상태,
                    str(tmp_run_dir / "x.log"), str(대상), str(결과), parent, exit_code,
                    datetime.now().astimezone().isoformat(timespec="seconds")))
        cx.commit()
    finally:
        cx.close()
    return job_id


_견적2건 = {**_견적문서, "집계": {"선택": 3, "스킵": 1, "접수": 2, "총장수": 20,
                                "예상크레딧": 100, "잘린상품": 0}}


# ── 접수 ──

def test_detail접수_토큰없이_안된다(화면, 엿듣기, tmp_run_dir):
    견적 = _상세행(tmp_run_dir, "detail_estimate", 견적=_견적2건)
    응답 = 화면.post(접수경로, json={"estimate_job_id": 견적},
                    headers={"X-CT-Token": "wrong-token"})
    assert 응답.status_code == 403
    assert not 엿듣기


def test_detail접수_GET이_아니다(화면):
    assert 화면.get(접수경로).status_code == 405
    assert 화면.get(확인경로).status_code == 405


def test_detail접수_부모만_가리킨다(화면, 엿듣기, tmp_run_dir):
    """요청은 견적 잡 id 하나 — 대상 필드가 없다. targets 는 부모 것을 그대로 쓴다(D-14·T-05-15)."""
    from webapp.routes.jobs import DetailSubmitReq, DetailPollReq
    assert set(DetailSubmitReq.model_fields) == {"estimate_job_id"}
    assert set(DetailPollReq.model_fields) == {"submit_job_id"}
    견적 = _상세행(tmp_run_dir, "detail_estimate", 견적=_견적2건)
    응답 = 화면.post(접수경로, json={"estimate_job_id": 견적})
    assert 응답.status_code == 200, 응답.text
    assert 엿듣기["kind"] == "detail_submit"
    assert 엿듣기["parent_job_id"] == 견적
    assert str(엿듣기["targets_path_override"]) == jobs._row(견적)["targets_path"]
    assert 엿듣기["run_dir"] == tmp_run_dir.name
    assert "only_ads" not in 엿듣기 or 엿듣기["only_ads"] is None
    assert "detail_inputs" not in 엿듣기 or 엿듣기["detail_inputs"] is None


def test_detail접수_max_credits_는_estimate_json_에서(화면, 엿듣기, tmp_run_dir):
    """화면 숫자를 믿지 않는다 — 몸통에 max_credits 를 실어도 부모 estimate.json 값이 간다."""
    견적 = _상세행(tmp_run_dir, "detail_estimate", 견적=_견적2건)
    응답 = 화면.post(접수경로, json={"estimate_job_id": 견적, "max_credits": 999999})
    assert 응답.status_code in (200, 400, 422), 응답.text
    if 응답.status_code == 200:
        assert 엿듣기["max_credits"] == 100


def test_detail접수_max_credits_정확히(화면, 엿듣기, tmp_run_dir):
    견적 = _상세행(tmp_run_dir, "detail_estimate", 견적=_견적2건)
    assert 화면.post(접수경로, json={"estimate_job_id": 견적}).status_code == 200
    assert 엿듣기["max_credits"] == 100


def test_detail접수_예상크레딧0이면_400(화면, 엿듣기, tmp_run_dir):
    견적 = _상세행(tmp_run_dir, "detail_estimate", 견적={**_견적문서, "집계": {
        "선택": 2, "스킵": 2, "접수": 0, "총장수": 0, "예상크레딧": 0, "잘린상품": 0}})
    응답 = 화면.post(접수경로, json={"estimate_job_id": 견적})
    assert 응답.status_code == 400
    assert "접수할 게 없다" in 응답.json()["detail"]
    assert not 엿듣기


def test_detail접수_부모kind틀리면_400(화면, 엿듣기, tmp_run_dir):
    견적 = _상세행(tmp_run_dir, "detail_estimate", 견적=_견적2건)
    접수 = _상세행(tmp_run_dir, "detail_submit", parent=견적)
    응답 = 화면.post(접수경로, json={"estimate_job_id": 접수})
    assert 응답.status_code == 400
    assert not 엿듣기


def test_detail접수_없는잡이면_400(화면, 엿듣기):
    응답 = 화면.post(접수경로, json={"estimate_job_id": "00000000-0000-4000-8000-000000000000"})
    assert 응답.status_code == 400
    assert not 엿듣기


def test_detail접수_잡id모양이_아니면_422(화면, 엿듣기):
    assert 화면.post(접수경로, json={"estimate_job_id": "../../x"}).status_code in (400, 422)
    assert not 엿듣기


def test_detail접수_부모running이면_400(화면, 엿듣기, tmp_run_dir):
    견적 = _상세행(tmp_run_dir, "detail_estimate", 상태="starting", exit_code=None,
                  견적=_견적2건)
    응답 = 화면.post(접수경로, json={"estimate_job_id": 견적})
    assert 응답.status_code == 400
    assert not 엿듣기


def test_detail접수_부모failed면_400(화면, 엿듣기, tmp_run_dir):
    견적 = _상세행(tmp_run_dir, "detail_estimate", 상태="failed", exit_code=4, 견적=_견적2건)
    응답 = 화면.post(접수경로, json={"estimate_job_id": 견적})
    assert 응답.status_code == 400
    assert not 엿듣기


def test_detail접수_estimate_json_없으면_400(화면, 엿듣기, tmp_run_dir):
    견적 = _상세행(tmp_run_dir, "detail_estimate", 견적=None)
    응답 = 화면.post(접수경로, json={"estimate_job_id": 견적})
    assert 응답.status_code == 400
    assert not 엿듣기


def test_detail접수_같은견적_두번은_400(화면, 엿듣기, tmp_run_dir):
    """한 견적에서 접수는 한 번. 두 번째는 '이어서 확인' 이나 새 견적이다(L-03 · D-18)."""
    견적 = _상세행(tmp_run_dir, "detail_estimate", 견적=_견적2건)
    _상세행(tmp_run_dir, "detail_submit", parent=견적)
    응답 = 화면.post(접수경로, json={"estimate_job_id": 견적})
    assert 응답.status_code == 400
    assert "이미 접수" in 응답.json()["detail"]
    assert not 엿듣기


def test_detail접수_계정불일치면_409(화면, 안띄운다, 프로필, 기대닉, tmp_run_dir):
    """진짜 `create_job` 이 돌아야 계정 가드에 닿는다."""
    프로필("zz다른계정")
    견적 = _상세행(tmp_run_dir, "detail_estimate", 견적=_견적2건)
    응답 = 화면.post(접수경로, json={"estimate_job_id": 견적})
    assert 응답.status_code == 409, 응답.text
    assert "zz다른계정" not in 응답.json()["detail"]


def test_detail접수_진짜_create_job_argv(화면, 안띄운다, 프로필, 기대닉, tmp_run_dir,
                                       monkeypatch):
    """가짜 spawn 으로 argv 를 본다 — --max-credits 100 · 같은 inputs · 같은 detail 폴더."""
    from webapp import settings as 설정
    monkeypatch.setattr(설정, "load", lambda force=False: None)
    프로필()
    견적 = _상세행(tmp_run_dir, "detail_estimate", 견적=_견적2건)
    응답 = 화면.post(접수경로, json={"estimate_job_id": 견적})
    assert 응답.status_code == 200, 응답.text
    av = json.loads(jobs._row(응답.json()["job_id"])["argv"])
    assert av[av.index("--max-credits") + 1] == "100"
    assert av[av.index("--inputs") + 1] == jobs._row(견적)["targets_path"]
    assert Path(av[av.index("--run-dir") + 1]).name == f"detail_{견적}"
    assert "--poll-only" not in av and "--retry-failed" not in av


# ── 이어서 확인 ──

_체크_미종결 = {"zzp1": {"taskId": "task-zz-000000000001", "status": "접수", "pages": 10},
               "zzp4": {"taskId": "task-zz-000000000004", "status": "완료", "pages": 10},
               "zzp5": {"status": "완료(기작업)", "pages": 10}}
_체크_종결 = {"zzp1": {"taskId": "task-zz-000000000001", "status": "완료", "pages": 10},
             "zzp4": {"taskId": "task-zz-000000000004", "status": "실패", "pages": 10,
                      "사유": "zz서버오류"},
             "zzp5": {"status": "완료(기작업)", "pages": 10}}


def _접수체인(tmp_run_dir, 상태="done", exit_code=3, 체크=None) -> tuple[str, str]:
    견적 = _상세행(tmp_run_dir, "detail_estimate", 견적=_견적2건)
    접수 = _상세행(tmp_run_dir, "detail_submit", 상태=상태, exit_code=exit_code, parent=견적,
                  체크포인트=_체크_미종결 if 체크 is None else 체크)
    return 견적, 접수


@pytest.mark.parametrize("상태,코드,체크", [
    ("done", 3, None),                      # 시간 상한 — 정상 경로
    ("orphaned", None, None),               # 서버 재시작 · 종료코드 모름 · 체크포인트엔 미종결
    ("done", 0, None),                      # 0 인데 체크포인트엔 미종결(서버 상태가 바뀜)
])
def test_detail이어서_부모는_submit_또는_poll(화면, 엿듣기, tmp_run_dir, 상태, 코드, 체크):
    _, 접수 = _접수체인(tmp_run_dir, 상태, 코드, 체크)
    응답 = 화면.post(확인경로, json={"submit_job_id": 접수})
    assert 응답.status_code == 200, 응답.text
    assert 엿듣기["kind"] == "detail_poll"
    assert 엿듣기["parent_job_id"] == 접수
    assert str(엿듣기["targets_path_override"]) == jobs._row(접수)["targets_path"]
    assert 엿듣기.get("max_credits") is None


def test_detail이어서_poll의_poll도_된다(화면, 엿듣기, tmp_run_dir):
    _, 접수 = _접수체인(tmp_run_dir)
    이전 = _상세행(tmp_run_dir, "detail_poll", exit_code=3, parent=접수)
    응답 = 화면.post(확인경로, json={"submit_job_id": 이전})
    assert 응답.status_code == 200, 응답.text
    assert 엿듣기["parent_job_id"] == 이전


@pytest.mark.parametrize("상태,코드", [("failed", 2), ("failed", 5), ("failed", 4),
                                      ("running", None)])
def test_detail이어서_실패_도는중은_400(화면, 엿듣기, tmp_run_dir, 상태, 코드):
    """장수불일치(2)·견적초과(5)는 사람 판단 — 이어서 확인으로 덮지 않는다."""
    _, 접수 = _접수체인(tmp_run_dir, 상태, 코드)
    응답 = 화면.post(확인경로, json={"submit_job_id": 접수})
    assert 응답.status_code == 400
    assert not 엿듣기


def test_detail이어서_미종결0이면_400(화면, 엿듣기, tmp_run_dir):
    _, 접수 = _접수체인(tmp_run_dir, "done", 0, _체크_종결)
    응답 = 화면.post(확인경로, json={"submit_job_id": 접수})
    assert 응답.status_code == 400
    assert not 엿듣기


def test_detail이어서_부모가_견적이면_400(화면, 엿듣기, tmp_run_dir):
    견적, _ = _접수체인(tmp_run_dir)
    assert 화면.post(확인경로, json={"submit_job_id": 견적}).status_code == 400
    assert not 엿듣기


def test_detail이어서_토큰없이_안된다(화면, 엿듣기, tmp_run_dir):
    _, 접수 = _접수체인(tmp_run_dir)
    응답 = 화면.post(확인경로, json={"submit_job_id": 접수},
                    headers={"X-CT-Token": "wrong-token"})
    assert 응답.status_code == 403
    assert not 엿듣기


def test_detail이어서_계정불일치면_409(화면, 안띄운다, 프로필, 기대닉, tmp_run_dir):
    프로필("zz다른계정")
    _, 접수 = _접수체인(tmp_run_dir)
    응답 = 화면.post(확인경로, json={"submit_job_id": 접수})
    assert 응답.status_code == 409, 응답.text


def test_detail이어서_크레딧없음(화면, 안띄운다, 프로필, 기대닉, tmp_run_dir, monkeypatch):
    """poll argv — --poll-only 있고 --max-credits·--retry-failed·--estimate-only 없음."""
    from webapp import settings as 설정
    monkeypatch.setattr(설정, "load", lambda force=False: None)
    프로필()
    _, 접수 = _접수체인(tmp_run_dir)
    응답 = 화면.post(확인경로, json={"submit_job_id": 접수})
    assert 응답.status_code == 200, 응답.text
    av = json.loads(jobs._row(응답.json()["job_id"])["argv"])
    assert "--poll-only" in av
    for 금지 in ("--max-credits", "--retry-failed", "--force", "--estimate-only"):
        assert 금지 not in av, 금지


# ── 결과 표 ──

def test_detail결과ctx_정본은_detail_status(화면, tmp_run_dir):
    """orphaned(종료코드 없음)여도 detail_status.json 으로 항목·미종결을 센다."""
    _, 접수 = _접수체인(tmp_run_dir, "orphaned", None)
    j = 화면.get(f"/jobs/{접수}/result?format=json").json()
    assert j["error"] is None
    상태들 = {h["판매자상품코드"]: h["상태"] for h in j["항목"]}
    assert 상태들 == {"zz01": "폴링중", "zz04": "완료", "zz05": "기작업스킵"}
    assert j["집계"]["폴링미완"] == 1 and j["집계"]["완료"] == 1 and j["집계"]["스킵"] == 1
    assert j["집계"]["접수"] == 2
    assert j["이어서확인가능"] is True
    assert j["미종결"] == 1
    # 크레딧 — 접수분 기준 재보고 vs 견적
    assert j["집계"]["접수크레딧"] == 100
    assert j["예상크레딧"] == 100
    # taskId 는 끝 8자리만 화면에
    assert all(len(h["taskId"] or "") <= 8 for h in j["항목"])


def test_detail결과_종결이면_이어서확인_없음(화면, tmp_run_dir):
    _, 접수 = _접수체인(tmp_run_dir, "done", 0, _체크_종결)
    j = 화면.get(f"/jobs/{접수}/result?format=json").json()
    assert j["이어서확인가능"] is False
    사유 = {h["판매자상품코드"]: h["사유"] for h in j["항목"]}
    assert 사유["zz04"] == "zz서버오류"
    assert j["집계"]["실패"] == 1


def test_detail결과조각_이어서확인만_그린다(화면, tmp_run_dir):
    _, 접수 = _접수체인(tmp_run_dir)
    응답 = 화면.get(f"/jobs/{접수}/result", headers={"HX-Request": "true"})
    assert 응답.status_code == 200
    본문 = 응답.text
    assert "이어서 확인" in 본문 and "실패 아님" in 본문
    assert f'data-submit-job="{접수}"' in 본문
    assert "재접수" not in 본문 and "retry" not in 본문.lower()
    for 말 in ("zz01", "zz04", "zz05", "폴링중", "완료"):
        assert 말 in 본문, 말


def test_detail결과조각_도는중(화면, tmp_run_dir):
    _, 접수 = _접수체인(tmp_run_dir, "starting", None)
    응답 = 화면.get(f"/jobs/{접수}/result", headers={"HX-Request": "true"})
    assert 응답.status_code == 200
    assert "이어서 확인" not in 응답.text
    assert "도는 중" in 응답.text


def test_detail결과_체크포인트없으면_에러(화면, tmp_run_dir):
    견적 = _상세행(tmp_run_dir, "detail_estimate", 견적=_견적2건)
    접수 = _상세행(tmp_run_dir, "detail_submit", 상태="failed", exit_code=4, parent=견적)
    j = 화면.get(f"/jobs/{접수}/result?format=json").json()
    assert j["error"]
    assert j["이어서확인가능"] is False
