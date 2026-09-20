#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""webapp/paths.py · webapp/settings.py 규약 테스트.

여기서 지키는 것은 두 가지다.
  1) **경로를 코드에 박지 않는다** — data_root 는 workspace.toml 에서 온다.
     박으면 다른 PC 에서 조용히 폴백해 엉뚱한 디렉터리를 읽는다(run_ads.py:39 주석과 같은 이유).
  2) **사용자 입력이 파일 경로가 되지 않는다** — 회차 이름은 화이트리스트를 통과해야만 Path 가 된다 (T-1-11).

실제 `~/python_work/data` 를 절대 건드리지 않는다. monkeypatch 로 tmp_path 를 끼운다.
"""
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from webapp import paths, settings


@pytest.fixture(autouse=True)
def _설정원복(monkeypatch):
    """테스트가 settings 를 흔들어도 다음 테스트는 진짜 설정으로 시작하게 한다.

    settings 는 모듈 전역 캐시를 쓴다 — 원복을 안 하면 실행 순서에 따라 결과가 달라진다.
    monkeypatch 를 의존으로 받아, 이 픽스처가 monkeypatch 보다 **먼저** 정리되게 만든다.
    """
    yield
    monkeypatch.undo()
    settings.reload()


def _회차(tmp_path, monkeypatch, 이름들_결과있음, 이름들_결과없음=()):
    """tmp_path 밑에 `naver-ads/runs/<회차>` 2단 구조를 만든다.

    2단 구조를 반드시 지킨다 — bids.py:130 이 `run_dir.parent.parent/"ledger"` 를 쓴다.
    한 단이라도 빠지면 테스트가 실제 ledger 디렉터리를 만지게 된다.
    """
    monkeypatch.setattr(paths, "data_root", lambda: tmp_path)
    runs = tmp_path / "naver-ads" / "runs"
    for n in 이름들_결과있음:
        d = runs / n
        d.mkdir(parents=True, exist_ok=True)
        (d / "result.json").write_text('{"generated":"x","accounts":{}}', encoding="utf-8")
    for n in 이름들_결과없음:
        (runs / n).mkdir(parents=True, exist_ok=True)
    return runs


# ── 1. data_root 는 workspace.toml 에서 온다 ──────────────────────────────

def test_data_root_는_workspace_toml_을_먼저_본다(tmp_path, monkeypatch):
    (tmp_path / "workspace.toml").write_text(
        '[paths]\ndata_root = "/tmp/가짜-데이터루트"\n', encoding="utf-8")
    monkeypatch.setattr(paths, "repo_root", lambda: tmp_path)
    assert paths.data_root() == Path("/tmp/가짜-데이터루트")


# ── 2. 없거나 비면 폴백 ───────────────────────────────────────────────────

def test_workspace_toml_이_없으면_홈_밑으로_폴백한다(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "repo_root", lambda: tmp_path)
    assert paths.data_root() == Path.home() / "python_work" / "data"


def test_data_root_가_빈문자열이어도_폴백한다(tmp_path, monkeypatch):
    (tmp_path / "workspace.toml").write_text('[paths]\ndata_root = ""\n', encoding="utf-8")
    monkeypatch.setattr(paths, "repo_root", lambda: tmp_path)
    assert paths.data_root() == Path.home() / "python_work" / "data"


# ── 3. result.json 이 있는 회차만 보드에 뜬다 (Pitfall 7) ────────────────

def test_result_json_없는_회차는_목록에서_빠진다(tmp_path, monkeypatch):
    # prep 만 돌고 run 을 안 돌린 run-dir 은 판정이 없다 — 보드에 띄우면 빈 화면이 된다
    _회차(tmp_path, monkeypatch, ["2026-08-29", "2026-08-30"], ["2026-08-31"])
    assert paths.scan_run_dirs() == ["2026-08-30", "2026-08-29"]


def test_회차_목록은_최신이_앞이다(tmp_path, monkeypatch):
    _회차(tmp_path, monkeypatch, ["2026-07-01", "2026-08-30", "2026-08-29"])
    assert paths.scan_run_dirs() == ["2026-08-30", "2026-08-29", "2026-07-01"]


def test_runs_디렉터리가_없으면_빈목록이다(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "data_root", lambda: tmp_path)
    assert paths.scan_run_dirs() == []


# ── 4. 화이트리스트 밖 이름은 경로가 되지 않는다 (T-1-11 / ASVS V12) ────

def test_모르는_회차이름은_경로가_되지_않는다(tmp_path, monkeypatch):
    _회차(tmp_path, monkeypatch, ["2026-08-30"])
    for 나쁜이름 in ["../../etc", "2026-08-30/../../../etc", "없는회차", "/etc"]:
        with pytest.raises(ValueError):
            paths.run_dir_path(나쁜이름)


def test_아는_회차는_그_디렉터리를_돌려준다(tmp_path, monkeypatch):
    runs = _회차(tmp_path, monkeypatch, ["2026-08-30"])
    assert paths.run_dir_path("2026-08-30") == runs / "2026-08-30"


# ── 5. 신선도 — 경과일과 통계기간을 같이 준다 (D-16) ─────────────────────

def _신선도_회차(tmp_path, monkeypatch, 며칠전, summary):
    이름 = (date.today() - timedelta(days=며칠전)).isoformat()
    runs = _회차(tmp_path, monkeypatch, [이름])
    (runs / 이름 / "prep_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False), encoding="utf-8")
    return 이름


def test_신선도는_경과일과_통계기간을_같이_준다(tmp_path, monkeypatch):
    이름 = _신선도_회차(tmp_path, monkeypatch, 3, {
        "window7": ["2026-08-22", "2026-08-28"],
        "window30": ["2026-07-30", "2026-08-28"],
    })
    f = paths.freshness(이름)
    assert f["run_dir"] == 이름
    assert f["age_days"] == 3
    assert f["window7"] == ["2026-08-22", "2026-08-28"]
    assert f["window30"] == ["2026-07-30", "2026-08-28"]


def test_실제_prep_summary_모양_계정별_중첩도_읽는다(tmp_path, monkeypatch):
    # 실데이터는 alias 로 한 겹 감싸져 있다 (~/python_work/data/.../prep_summary.json 실측)
    이름 = _신선도_회차(tmp_path, monkeypatch, 1, {
        "cy728": {"alias": "cy728", "ads": 223,
                  "window7": ["2026-08-22", "2026-08-28"],
                  "window30": ["2026-07-30", "2026-08-28"]},
    })
    assert paths.freshness(이름)["window7"] == ["2026-08-22", "2026-08-28"]


def test_회차명이_날짜가_아니면_경과일은_None_이다(tmp_path, monkeypatch):
    _회차(tmp_path, monkeypatch, ["복구-임시"])
    f = paths.freshness("복구-임시")
    assert f["age_days"] is None
    assert f["stale"] is False


def test_prep_summary_가_없으면_통계기간은_None_이다(tmp_path, monkeypatch):
    이름 = (date.today() - timedelta(days=1)).isoformat()
    _회차(tmp_path, monkeypatch, [이름])
    f = paths.freshness(이름)
    assert f["window7"] is None and f["window30"] is None


# ── 5-b. 회차마다 들어 있는 계정이 다르다 (OQ-7) ─────────────────────────

def _계정있는_회차(tmp_path, monkeypatch, 회차별계정: dict):
    """회차마다 **다른 계정 집합**을 가진 result.json 을 만든다.

    실측이 그렇다: 같은 폴더 구조인데 어떤 회차는 계정 2개, 어떤 회차는 4개다.
    prep 을 한 계정만 돌린 날이 그대로 남기 때문이다.
    """
    monkeypatch.setattr(paths, "data_root", lambda: tmp_path)
    runs = tmp_path / "naver-ads" / "runs"
    for 이름, 계정들 in 회차별계정.items():
        d = runs / 이름
        d.mkdir(parents=True, exist_ok=True)
        (d / "result.json").write_text(json.dumps({
            "generated": 이름,
            "accounts": {a: {"rules": {}} for a in 계정들},
        }, ensure_ascii=False), encoding="utf-8")
    return runs


def test_회차마다_들어있는_계정수를_같이_준다(tmp_path, monkeypatch):
    """신선도만 보고 회차를 고르면 계정 절반이 측정조차 안 된 판정 위에서
    입찰가를 올리게 된다 (OQ-7). 그래서 회차 목록이 계정 수를 같이 들고 다닌다.

    계정 이름은 코드가 아니라 **result.json 에서만** 온다 — 여기 가짜 이름을 넣어도
    그대로 나와야 한다(BOARD-02 와 같은 근거).
    """
    _계정있는_회차(tmp_path, monkeypatch, {
        "2026-08-30": ["aa", "bb", "cc", "dd"],
        "2026-08-29": ["aa", "bb"],
        "2026-09-20": ["aa"],
    })

    목록 = paths.scan_runs()
    assert [r["name"] for r in 목록] == ["2026-09-20", "2026-08-30", "2026-08-29"]
    assert [r["account_count"] for r in 목록] == [1, 4, 2]
    assert 목록[1]["accounts"] == ["aa", "bb", "cc", "dd"]

    # 화이트리스트 관문은 **이름만** 돌려주는 채로 남는다 (역할이 흐려지면 안 된다)
    assert paths.scan_run_dirs() == ["2026-09-20", "2026-08-30", "2026-08-29"]


def test_신선도에_계정수와_빠진계정이_실린다(tmp_path, monkeypatch):
    """계정 1개짜리 회차를 골랐을 때 **무엇이 빠졌는지**까지 말한다.

    "할 게 별로 없네" 로 읽히는 화면이 실제로는 "3개 계정을 안 본 것" 인 상태 —
    그게 이 기능이 막는 오독이다. 막지는 않는다, 보여만 준다.
    """
    _계정있는_회차(tmp_path, monkeypatch, {
        "2026-08-30": ["aa", "bb", "cc", "dd"],
        "2026-09-20": ["aa"],
    })

    적은것 = paths.freshness("2026-09-20")
    assert 적은것["account_count"] == 1
    assert 적은것["accounts"] == ["aa"]
    assert 적은것["missing_accounts"] == ["bb", "cc", "dd"]
    assert 적은것["max_account_count"] == 4

    많은것 = paths.freshness("2026-08-30")
    assert 많은것["account_count"] == 4
    assert 많은것["missing_accounts"] == []


def test_계정목록이_재판정을_따라온다(tmp_path, monkeypatch):
    """`run` 으로 result.json 을 덮으면 계정 목록도 따라온다.

    파싱 결과를 캐시하는데 키가 mtime·크기라, 파일이 바뀌면 캐시가 저절로 무효화된다.
    안 그러면 계정을 늘리고 재판정해도 화면이 옛날 수를 계속 보여준다.
    """
    runs = _계정있는_회차(tmp_path, monkeypatch, {"2026-08-30": ["aa"]})
    assert paths.run_accounts("2026-08-30") == ["aa"]

    (runs / "2026-08-30" / "result.json").write_text(json.dumps({
        "generated": "x", "accounts": {"aa": {}, "bb": {}}}), encoding="utf-8")
    assert paths.run_accounts("2026-08-30") == ["aa", "bb"]


def test_계정을_못_읽어도_회차목록은_뜬다(tmp_path, monkeypatch):
    """result.json 이 깨져도 회차 목록 전체가 사라지지 않는다.

    계정 수를 못 읽는 것보다 회차 목록이 통째로 안 뜨는 게 훨씬 나쁘다.
    """
    runs = _계정있는_회차(tmp_path, monkeypatch, {"2026-08-30": ["aa"]})
    (runs / "2026-08-30" / "result.json").write_text("{깨짐", encoding="utf-8")
    assert paths.run_accounts("2026-08-30") == []
    assert [r["name"] for r in paths.scan_runs()] == ["2026-08-30"]


# ── 6. 임계값을 넘으면 stale ─────────────────────────────────────────────

def test_임계값을_넘은_회차는_stale_이다(tmp_path, monkeypatch):
    이름 = _신선도_회차(tmp_path, monkeypatch, 9, {"window7": None, "window30": None})
    monkeypatch.setattr(settings, "STALE_DAYS", 8)
    assert paths.freshness(이름)["stale"] is True
    monkeypatch.setattr(settings, "STALE_DAYS", 30)
    assert paths.freshness(이름)["stale"] is False


# ── 7. 상한은 설정값이다 (D-08) ──────────────────────────────────────────

def test_계정별_상한_기본값은_천오백이다(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "repo_root", lambda: tmp_path)
    settings.reload()
    assert settings.PER_ACCOUNT_LIMIT == 1500


def test_계정별_상한은_workspace_toml_로_덮인다(tmp_path, monkeypatch):
    (tmp_path / "workspace.toml").write_text(
        "[webapp]\nper_account_limit = 42\nport = 9999\n", encoding="utf-8")
    monkeypatch.setattr(paths, "repo_root", lambda: tmp_path)
    settings.reload()
    assert settings.PER_ACCOUNT_LIMIT == 42
    assert settings.PORT == 9999
    # 덮지 않은 키는 DEFAULTS 가 그대로 산다 (얕은 병합)
    assert settings.STALE_DAYS == settings.DEFAULTS["stale_days"]


def test_required_인데_값이_없으면_조용히_넘어가지_않는다(tmp_path, monkeypatch):
    # T-1-12 — 상한이 조용히 사라지면 D-08 가드가 무력화된다
    monkeypatch.setattr(paths, "repo_root", lambda: tmp_path)
    settings.reload()
    with pytest.raises(KeyError):
        settings.cfg("없는키", required=True)
    assert settings.cfg("없는키", "폴백") == "폴백"


def test_상한_숫자가_settings_밖에_리터럴로_박혀있지_않다():
    """D-08: 상한은 설정파일로 조정 가능해야 한다.

    다른 파일에 1500 이 박히면 workspace.toml 을 고쳐도 동작이 안 바뀐다.
    이 테스트는 Wave 1~7 이 파일을 더해도 계속 감시한다.
    """
    금지 = {str(settings.DEFAULTS["per_account_limit"]), str(settings.DEFAULTS["port"])}
    루트 = Path(paths.__file__).resolve().parent
    for f in list(루트.rglob("*.py")) + list(루트.rglob("*.html")) + list(루트.rglob("*.js")):
        if f.name == "settings.py" or "tests" in f.parts or "vendor" in f.parts:
            continue
        본문 = f.read_text(encoding="utf-8", errors="ignore")
        for 숫자 in 금지:
            assert 숫자 not in 본문, f"{f} 에 {숫자} 가 리터럴로 박혀 있다 — settings 를 써라"
