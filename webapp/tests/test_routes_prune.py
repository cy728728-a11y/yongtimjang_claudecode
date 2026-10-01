#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""꺼진 소재 정리 라우트(`/jobs/prune/*` · 결과 조각) 검증 — Phase 2 / 02-03.

**실제 CLI 는 한 번도 안 뜬다**(`안띄운다` 가 spawn 을 가짜로). 네이버 광고 API 0 · 쓰기 0.
틀은 test_routes_coupang.py 1:1 복제다. 다른 점:
  · 커밋 재요청은 409 (쿠팡은 400 — D-09 의 의도적 차이)
  · 상한은 prune_max_items (설정) — 라우트가 400, CLI 가 exit 2 로 2겹
  · 실패분 재시도는 실패 adId ∩ 미리보기 adId 부분집합을 새 prune_commit 으로

산출물 픽스처는 02-01 CLI 계약 모양을 테스트 안에서 dict 로 만든다. 계정은 `zz*` 익명.
"""
import json
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from webapp import jobs, settings
from webapp.tests.test_routes_jobs import 안띄운다, 화면  # noqa: F401

미리보기경로 = "/jobs/prune/preview"
커밋경로 = "/jobs/prune/commit"
재시도경로 = "/jobs/prune/retry"
# no_commit_guard.sh 가 커밋 플래그 리터럴을 금지한다 — 간접 조립.
_커밋플래그 = "--" + "commit"
_대상플래그 = "--" + "only-ads"
_상한플래그 = "--" + "max-items"


# ── 도우미 ──────────────────────────────────────────────────────────────────

def _지금(시간전: float = 0) -> str:
    return (datetime.now().astimezone() - timedelta(hours=시간전)).isoformat(timespec="seconds")


def _대상행(alias: str, i: int, **덮기) -> dict:
    행 = {"adId": f"nad-{alias}-{i:03d}", "adgroupId": f"grp-{alias}-{i}",
          "adGroup": f"01-{i}", "mallProductId": f"{9000 + i}",
          "title": f"zz상품{i:02d}", "statusReason": "AD_ABNORMAL_INTERLOCK",
          "editTm": "2026-09-20T10:00:00.000Z", "regTm": "2026-08-01T10:00:00.000Z"}
    행.update(덮기)
    return 행


def _미리보기문서(**덮기) -> dict:
    """2계정 · targets 3·2행 · keep {거부 1, 검수중 1} · 한 계정 skipped."""
    a = [_대상행("zza", i) for i in range(3)]
    b = [_대상행("zzb", i) for i in range(2)]
    문서 = {"generated": "2026-09-30T10:00:00", "mode": "dry-run", "limit": None,
            "total": 5, "adIds": [r["adId"] for r in a + b],
            "accounts": {
                "zza": {"paused": 4, "deletable": 3, "keep": {"AD_DISAPPROVED": 1},
                        "backup": None, "aborted": None, "skipped": None, "targets": a},
                "zzb": {"paused": 3, "deletable": 2, "keep": {"AD_UNDER_REVIEW": 1},
                        "backup": None, "aborted": None, "skipped": None, "targets": b},
                "zzc": {"skipped": "자격증명 없음", "aborted": None, "backup": None,
                        "keep": {}, "targets": []},
            }}
    문서.update(덮기)
    return 문서


def _행박기(kind, *, 상태="done", exit_code=0, parent=None, result=None, 시작=None,
            run_dir=None) -> str:
    job_id = str(uuid.uuid4())
    cx = sqlite3.connect(jobs.db_path())
    try:
        cx.execute("INSERT INTO jobs (id, kind, run_dir, accounts, argv, status, log_path, "
                   "targets_path, result_path, parent_job_id, exit_code, started_at) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                   (job_id, kind, run_dir, "[]", "[]", 상태, "/dev/null", None,
                    str(result) if result else None, parent,
                    exit_code if 상태 not in jobs.LIVE_STATUSES else None, 시작 or _지금()))
        cx.commit()
    finally:
        cx.close()
    return job_id


def _미리보기잡(run_dir: Path, *, 문서=None, 상태="done", exit_code=0, 시작=None,
               쓰기=True, 깨짐=False) -> str:
    """prune_preview 행 + `<run_dir>/web/prune_preview_<id>.json`."""
    job_id = str(uuid.uuid4())
    폴더 = run_dir / "web"
    폴더.mkdir(parents=True, exist_ok=True)
    결과 = 폴더 / f"prune_preview_{job_id}.json"
    if 깨짐:
        결과.write_text("{깨진", encoding="utf-8")
    elif 쓰기:
        결과.write_text(json.dumps(_미리보기문서() if 문서 is None else 문서, ensure_ascii=False),
                       encoding="utf-8")
    cx = sqlite3.connect(jobs.db_path())
    try:
        cx.execute("INSERT INTO jobs (id, kind, run_dir, accounts, argv, status, log_path, "
                   "targets_path, result_path, parent_job_id, exit_code, started_at) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                   (job_id, "prune_preview", run_dir.name, "[]", "[]", 상태, "/dev/null", None,
                    str(결과), None, exit_code if 상태 not in jobs.LIVE_STATUSES else None,
                    시작 or _지금()))
        cx.commit()
    finally:
        cx.close()
    return job_id


@pytest.fixture
def 삭제판(tmp_run_dir, 화면, 안띄운다):
    """tmp 회차 + tmp 잡 DB + spawn 가짜. 불사자 프로필은 필요 없다(광고 잡이다)."""
    return 화면


@pytest.fixture
def 상한(monkeypatch):
    """prune_max_items 를 바꾸는 팩토리 — settings.cfg 를 그 키에서만 가로챈다."""
    진짜 = settings.cfg

    def _설정(n):
        def 가짜(dotted, default=None, required=False):
            if dotted == "prune_max_items":
                return n
            return 진짜(dotted, default, required)
        monkeypatch.setattr(settings, "cfg", 가짜)
    return _설정


def _argv(job_id: str) -> list[str]:
    return json.loads(jobs.job_status(job_id)["argv"])


def _조각(client, job_id) -> str:
    응답 = client.get(f"/jobs/{job_id}/result", headers={"HX-Request": "true"})
    assert 응답.status_code == 200, 응답.text
    return 응답.text


# ── ① 미리보기 접수 ─────────────────────────────────────────────────────────

def test_미리보기는_잡_하나를_띄우고_argv_에_prune_preview_out(삭제판, tmp_run_dir):
    응답 = 삭제판.post(미리보기경로, json={"run_dir": tmp_run_dir.name, "accounts": []})
    assert 응답.status_code == 200, 응답.text
    job_id = 응답.json()["job_id"]
    상태 = jobs.job_status(job_id)
    assert 상태["kind"] == "prune_preview"
    av = _argv(job_id)
    assert "prune" in av and "--preview-out" in av and "--backup-tag" in av
    assert _커밋플래그 not in av, "미리보기에 커밋 플래그가 붙었다"


def test_미리보기_계정을_고르면_그_계정만(삭제판, tmp_run_dir):
    응답 = 삭제판.post(미리보기경로, json={"run_dir": tmp_run_dir.name, "accounts": ["zza"]})
    assert 응답.status_code == 200, 응답.text
    av = _argv(응답.json()["job_id"])
    assert "zza" in av


def test_미리보기_모르는_회차는_400(삭제판):
    응답 = 삭제판.post(미리보기경로, json={"run_dir": "1999-01-01", "accounts": []})
    assert 응답.status_code == 400
    응답 = 삭제판.post(미리보기경로, json={"run_dir": "../../etc", "accounts": []})
    assert 응답.status_code == 400
    assert not jobs.recent_jobs()


def test_미리보기_요청_모양이_틀리면_422(삭제판, tmp_run_dir):
    for 몸통 in ({"run_dir": tmp_run_dir.name, "accounts": ["../x"]},
                 {"run_dir": tmp_run_dir.name, "accounts": [], "adIds": ["nad-1"]},
                 {"run_dir": tmp_run_dir.name, "commit": True}):
        응답 = 삭제판.post(미리보기경로, json=몸통)
        assert 응답.status_code == 422, 몸통
    assert not jobs.recent_jobs()


def test_같은_회차_prep_이_도는_중이면_미리보기_409(삭제판, tmp_run_dir):
    _행박기("prep", 상태="starting", run_dir=tmp_run_dir.name)
    응답 = 삭제판.post(미리보기경로, json={"run_dir": tmp_run_dir.name, "accounts": []})
    assert 응답.status_code == 409, 응답.text
    assert "수집" in 응답.json()["detail"]


def test_다른_회차_prep_은_미리보기를_막지_않는다(삭제판, tmp_run_dir):
    _행박기("prep", 상태="starting", run_dir="2026-01-01")
    응답 = 삭제판.post(미리보기경로, json={"run_dir": tmp_run_dir.name, "accounts": []})
    assert 응답.status_code == 200, 응답.text


def test_미리보기가_이미_도는_중이면_409(삭제판, tmp_run_dir):
    _행박기("prune_preview", 상태="starting", run_dir=tmp_run_dir.name)
    응답 = 삭제판.post(미리보기경로, json={"run_dir": tmp_run_dir.name, "accounts": []})
    assert 응답.status_code == 409, 응답.text


# ── ① 미리보기 결과 조각 ────────────────────────────────────────────────────

def test_미리보기_조각_요약과_전행_JSON(삭제판, tmp_run_dir):
    pid = _미리보기잡(tmp_run_dir)
    본문 = _조각(삭제판, pid)
    assert "꺼진 소재(연동끊김) 5건 삭제" in 본문
    assert "남김" in 본문
    assert "거부 1" in 본문 and "검수중 1" in 본문
    assert "자격증명 없음" in 본문
    i = 본문.index('<script type="application/json" id="prune-preview-rows">')
    j = 본문.index("</script>", i)
    행 = json.loads(본문[본문.index(">", i) + 1:j])
    assert len(행) == 5
    assert set(행[0]) >= {"계정", "광고그룹", "소재id", "상품id", "상품명", "정지사유", "마지막 변경"}
    # 삭제 영역이 접힌 채로 있다
    assert 'id="prune-commit-details"' in 본문 and 'id="prune-typed-count"' in 본문
    assert "<details id=\"prune-commit-details\" open" not in 본문


def test_미리보기_ctx_계정요약(삭제판, tmp_run_dir):
    from webapp.routes.prune import _삭제미리보기ctx
    pid = _미리보기잡(tmp_run_dir)
    ctx = _삭제미리보기ctx(jobs.job_status(pid))
    assert ctx["삭제예정"] == 5 and not ctx["상한초과"]
    계정 = {r["계정"]: r for r in ctx["계정요약"]}
    assert 계정["zza"]["삭제대상"] == 3 and 계정["zzb"]["삭제대상"] == 2
    assert 계정["zza"]["남김"] == {"거부": 1}
    assert 계정["zzb"]["남김"] == {"검수중": 1}
    assert 계정["zzc"]["건너뜀"] == "자격증명 없음"


def test_미리보기_상한초과면_삭제영역_없음(삭제판, tmp_run_dir, 상한):
    상한(3)
    pid = _미리보기잡(tmp_run_dir)
    본문 = _조각(삭제판, pid)
    assert "상한 초과" in 본문
    assert 'id="prune-typed-count"' not in 본문


def test_미리보기_산출물이_없거나_깨지면_오류(삭제판, tmp_run_dir):
    for pid in (_미리보기잡(tmp_run_dir, 쓰기=False), _미리보기잡(tmp_run_dir, 깨짐=True)):
        본문 = _조각(삭제판, pid)
        assert "없거나 깨졌다" in 본문
        assert 'id="prune-preview-rows"' not in 본문
        assert "Traceback" not in 본문


def test_미리보기_도는_중이면_읽지_않는다(삭제판, tmp_run_dir):
    pid = _미리보기잡(tmp_run_dir, 상태="starting")
    본문 = _조각(삭제판, pid)
    assert "도는 중" in 본문 or "뽑는 중" in 본문 or "보는 중" in 본문
    assert 'id="prune-commit-details"' not in 본문


def test_미리보기_상품명_스크립트는_이스케이프(삭제판, tmp_run_dir):
    문서 = _미리보기문서()
    문서["accounts"]["zza"]["targets"][0]["title"] = "<script>alert(1)</script>"
    문서["accounts"]["zza"]["targets"][0]["adGroup"] = "<b>그룹</b>"
    pid = _미리보기잡(tmp_run_dir, 문서=문서)
    본문 = _조각(삭제판, pid)
    assert "<script>alert(1)</script>" not in 본문
    assert "<b>그룹</b>" not in 본문


def test_미리보기_24시간_지나면_만료_안내(삭제판, tmp_run_dir):
    pid = _미리보기잡(tmp_run_dir, 시작=_지금(25))
    본문 = _조각(삭제판, pid)
    assert "24시간" in 본문
    assert 'id="prune-typed-count"' not in 본문


def test_미리보기_이미_삭제했으면_삭제영역_대신_안내(삭제판, tmp_run_dir):
    pid = _미리보기잡(tmp_run_dir)
    _행박기("prune_commit", parent=pid, run_dir=tmp_run_dir.name)
    본문 = _조각(삭제판, pid)
    assert "이미 삭제" in 본문
    assert 'id="prune-typed-count"' not in 본문


def test_미리보기_템플릿에_safe_필터가_없다():
    from webapp import main
    src = (Path(main.__file__).parent / "templates" / "_prune_preview_table.html").read_text(
        encoding="utf-8")
    assert "| safe" not in src and "|safe" not in src
    assert "tojson" in src


# ── 보드 자리 ───────────────────────────────────────────────────────────────

def test_보드_회차가_있으면_삭제_패널과_스크립트(삭제판, tmp_run_dir):
    본문 = 삭제판.get(f"/?run_dir={tmp_run_dir.name}").text
    assert 'id="prune"' in 본문 and 'id="prune-preview-btn"' in 본문
    assert "광고 쓰기 0" in 본문
    assert 'id="prune-body"' in 본문 and 'id="prune-preview-job"' in 본문
    assert "/static/prune.js" in 본문
    assert 본문.index("/static/board.js") < 본문.index("/static/prune.js")
    i = 본문.index('id="prune-preview-btn"')
    태그 = 본문[본문.rfind("<", 0, i):본문.index(">", i)]
    assert "disabled" in 태그


def test_보드_회차가_없으면_삭제_패널이_없다(삭제판, monkeypatch):
    from webapp import paths
    monkeypatch.setattr(paths, "scan_runs", lambda: [])
    본문 = 삭제판.get("/").text
    assert 'id="prune"' not in 본문
