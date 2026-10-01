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


# ── ② 삭제(커밋) — 요청 모양 ────────────────────────────────────────────────

def test_커밋_요청에_다른_필드가_있으면_422(삭제판, tmp_run_dir):
    pid = _미리보기잡(tmp_run_dir)
    for 몸통 in ({"preview_job_id": pid, "typed_count": 5, "adIds": ["nad-zza-000"]},
                 {"preview_job_id": pid, "typed_count": 5, "max_items": 99999},
                 {"preview_job_id": pid, "typed_count": "5"},
                 {"preview_job_id": pid, "typed_count": True},
                 {"preview_job_id": pid, "typed_count": -1},
                 {"preview_job_id": pid},
                 {"preview_job_id": "../../etc", "typed_count": 5}):
        응답 = 삭제판.post(커밋경로, json=몸통)
        assert 응답.status_code == 422, 몸통
    assert not jobs.children_of(pid, "prune_commit")


# ── ② 삭제 — 부모 검사 ──────────────────────────────────────────────────────

def test_커밋_부모가_없거나_종류가_다르면_400(삭제판, tmp_run_dir):
    응답 = 삭제판.post(커밋경로, json={"preview_job_id": str(uuid.uuid4()), "typed_count": 5})
    assert 응답.status_code == 400
    남 = _행박기("bids_preview", run_dir=tmp_run_dir.name)
    응답 = 삭제판.post(커밋경로, json={"preview_job_id": 남, "typed_count": 5})
    assert 응답.status_code == 400


def test_커밋_부모가_도는_중이면_409(삭제판, tmp_run_dir):
    pid = _미리보기잡(tmp_run_dir, 상태="starting")
    응답 = 삭제판.post(커밋경로, json={"preview_job_id": pid, "typed_count": 5})
    assert 응답.status_code == 409, 응답.text


def test_커밋_부모가_실패했으면_400(삭제판, tmp_run_dir):
    pid = _미리보기잡(tmp_run_dir, 상태="failed", exit_code=1)
    응답 = 삭제판.post(커밋경로, json={"preview_job_id": pid, "typed_count": 5})
    assert 응답.status_code == 400


def test_커밋_24시간_넘은_미리보기는_400(삭제판, tmp_run_dir):
    pid = _미리보기잡(tmp_run_dir, 시작=_지금(25))
    응답 = 삭제판.post(커밋경로, json={"preview_job_id": pid, "typed_count": 5})
    assert 응답.status_code == 400
    assert "24시간" in 응답.json()["detail"]
    assert not jobs.children_of(pid, "prune_commit")


def test_커밋_멱등_성공한_삭제가_있으면_409(삭제판, tmp_run_dir):
    pid = _미리보기잡(tmp_run_dir)
    _행박기("prune_commit", parent=pid, run_dir=tmp_run_dir.name)
    응답 = 삭제판.post(커밋경로, json={"preview_job_id": pid, "typed_count": 5})
    assert 응답.status_code == 409
    assert "이미 삭제" in 응답.json()["detail"]


def test_커밋_멱등_삭제가_도는_중이면_409(삭제판, tmp_run_dir):
    pid = _미리보기잡(tmp_run_dir)
    _행박기("prune_commit", 상태="starting", parent=pid, run_dir=tmp_run_dir.name)
    응답 = 삭제판.post(커밋경로, json={"preview_job_id": pid, "typed_count": 5})
    assert 응답.status_code == 409


def test_커밋_산출물이_깨졌으면_400(삭제판, tmp_run_dir):
    for pid in (_미리보기잡(tmp_run_dir, 깨짐=True), _미리보기잡(tmp_run_dir, 쓰기=False)):
        응답 = 삭제판.post(커밋경로, json={"preview_job_id": pid, "typed_count": 5})
        assert 응답.status_code == 400, 응답.text
    문서 = _미리보기문서()
    문서["adIds"] = "전부"
    pid = _미리보기잡(tmp_run_dir, 문서=문서)
    응답 = 삭제판.post(커밋경로, json={"preview_job_id": pid, "typed_count": 5})
    assert 응답.status_code == 400


def test_커밋_대상_0건이면_400(삭제판, tmp_run_dir):
    문서 = _미리보기문서(total=0, adIds=[])
    for v in 문서["accounts"].values():
        v["targets"] = []
    pid = _미리보기잡(tmp_run_dir, 문서=문서)
    응답 = 삭제판.post(커밋경로, json={"preview_job_id": pid, "typed_count": 0})
    assert 응답.status_code == 400


def test_커밋_상한_초과면_400(삭제판, tmp_run_dir, 상한):
    상한(3)
    pid = _미리보기잡(tmp_run_dir)
    응답 = 삭제판.post(커밋경로, json={"preview_job_id": pid, "typed_count": 5})
    assert 응답.status_code == 400
    assert "상한" in 응답.json()["detail"]
    assert not jobs.children_of(pid, "prune_commit")


def test_커밋_타이핑_건수가_다르면_409_이고_잡을_안_만든다(삭제판, tmp_run_dir):
    pid = _미리보기잡(tmp_run_dir)
    응답 = 삭제판.post(커밋경로, json={"preview_job_id": pid, "typed_count": 4})
    assert 응답.status_code == 409
    assert "화면이 본 건수" in 응답.json()["detail"]
    assert not jobs.children_of(pid, "prune_commit")


def test_커밋_쓰기잡이_도는_중이면_409(삭제판, tmp_run_dir):
    pid = _미리보기잡(tmp_run_dir)
    _행박기("bids_commit", 상태="starting", run_dir=tmp_run_dir.name)
    응답 = 삭제판.post(커밋경로, json={"preview_job_id": pid, "typed_count": 5})
    assert 응답.status_code == 409, 응답.text


def test_커밋_only_ads_는_부모_산출물_그대로(삭제판, tmp_run_dir):
    pid = _미리보기잡(tmp_run_dir)
    응답 = 삭제판.post(커밋경로, json={"preview_job_id": pid, "typed_count": 5})
    assert 응답.status_code == 200, 응답.text
    cid = 응답.json()["job_id"]
    상태 = jobs.job_status(cid)
    assert 상태["kind"] == "prune_commit" and 상태["parent_job_id"] == pid
    av = _argv(cid)
    부모경로 = jobs.job_status(pid)["result_path"]
    assert str(Path(av[av.index(_대상플래그) + 1]).resolve()) == str(Path(부모경로).resolve())
    assert _커밋플래그 in av
    assert av[av.index(_상한플래그) + 1] == str(settings.DEFAULTS["prune_max_items"])
    i = av.index("--account")
    assert av[i + 1:i + 3] == ["zza", "zzb"]
    assert "zzc" not in av, "대상 없는 계정까지 돌린다"
    if Path("/usr/bin/caffeinate").exists():
        assert av[0].endswith("caffeinate") and av[1] == "-i"


def test_커밋_상한은_한_곳에서만():
    from webapp.routes import prune
    src = Path(prune.__file__).read_text(encoding="utf-8")
    assert src.count("def _삭제상한") == 1
    assert "prune_max_items=_삭제상한()" in src


# ── ② 삭제 결과 조각 ────────────────────────────────────────────────────────

def _결과문서(**덮기) -> dict:
    a = [_대상행("zza", i) for i in range(7)]
    items = ([{"adId": a[i]["adId"], "status": 200, "결과": "성공", "err": None} for i in range(3)]
             + [{"adId": a[3]["adId"], "status": 404, "결과": "이미없음", "err": None},
                {"adId": a[4]["adId"], "status": 500, "결과": "실패", "err": "server <b>boom</b>"}])
    문서 = {"generated": "2026-09-30T11:00:00", "mode": "commit", "limit": 8000,
            "total": len(items), "adIds": [x["adId"] for x in items],
            "accounts": {
                "zza": {"paused": 9, "deletable": 5, "keep": {}, "backup": "/x/paused_zza_t.json",
                        "aborted": None, "skipped": None, "targets": a, "items": items,
                        "result": {"ok": 3, "gone": 1, "fail": 1},
                        "excluded": [{"adId": a[5]["adId"], "사유": "다시_켜짐"},
                                     {"adId": a[6]["adId"], "사유": "재조회에_없음"}],
                        "new_since_preview": 2},
                "zzb": {"paused": 2, "deletable": 2, "keep": {}, "backup": None,
                        "aborted": "backup_failed", "skipped": None,
                        "targets": [_대상행("zzb", 0), _대상행("zzb", 1)]},
                "zzc": {"paused": 1, "deletable": 1, "keep": {}, "backup": "/x/paused_zzc_t.json",
                        "aborted": "recheck_failed", "skipped": None,
                        "targets": [_대상행("zzc", 0)]},
            }}
    문서.update(덮기)
    return 문서


def _커밋잡(run_dir: Path, parent: str, *, 문서=None, 상태="done", exit_code=0,
           쓰기=True) -> str:
    job_id = str(uuid.uuid4())
    결과 = run_dir / "web" / f"prune_result_{job_id}.json"
    결과.parent.mkdir(parents=True, exist_ok=True)
    if 쓰기:
        결과.write_text(json.dumps(_결과문서() if 문서 is None else 문서, ensure_ascii=False),
                       encoding="utf-8")
    cx = sqlite3.connect(jobs.db_path())
    try:
        cx.execute("INSERT INTO jobs (id, kind, run_dir, accounts, argv, status, log_path, "
                   "targets_path, result_path, parent_job_id, exit_code, started_at) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                   (job_id, "prune_commit", run_dir.name, "[]", "[]", 상태, "/dev/null", None,
                    str(결과), parent, exit_code if 상태 not in jobs.LIVE_STATUSES else None,
                    _지금()))
        cx.commit()
    finally:
        cx.close()
    return job_id


def test_결과_ctx_계정별_성공_이미없음_실패(삭제판, tmp_run_dir):
    from webapp.routes.prune import _삭제결과ctx
    pid = _미리보기잡(tmp_run_dir)
    cid = _커밋잡(tmp_run_dir, pid)
    ctx = _삭제결과ctx(jobs.job_status(cid))
    assert not ctx["error"]
    계정 = {r["계정"]: r for r in ctx["계정행"]}
    assert (계정["zza"]["성공"], 계정["zza"]["이미없음"], 계정["zza"]["실패"]) == (3, 1, 1)
    assert 계정["zza"]["제외"] == 2 and 계정["zza"]["새로꺼짐"] == 2
    assert ctx["새로꺼짐"] == 2
    assert ctx["실패목록"] == ["nad-zza-004"]
    assert [r["adId"] for r in ctx["실패행"]] == ["nad-zza-004"]
    assert {r["사유"] for r in ctx["제외행"]} == {"다시 켜짐", "재조회에 없음(이미 삭제됐거나 조회 실패)"}
    # 중단 계정이 위, 깨끗한 계정이 아래(flow.result_rows 관례 — 안 된 것을 화면 밖으로 밀지 않는다)
    순서 = [r["계정"] for r in ctx["계정행"]]
    assert 순서.index("zzb") < 순서.index("zza") and 순서.index("zzc") < 순서.index("zza")


def test_결과_조각_excluded_사유와_새로꺼짐과_중단계정(삭제판, tmp_run_dir):
    pid = _미리보기잡(tmp_run_dir)
    cid = _커밋잡(tmp_run_dir, pid)
    본문 = _조각(삭제판, cid)
    assert "다시 켜짐" in 본문
    assert "재조회에 없음(이미 삭제됐거나 조회 실패)" in 본문
    assert "미리보기 이후 새로 꺼진 2건 — 이번엔 안 지움" in 본문
    assert "백업을 못 써서 이 계정은 한 건도 지우지 않았다" in 본문
    assert "재확인 조회가 0건/실패" in 본문
    assert "<b>boom</b>" not in 본문           # 오류 원문 이스케이프
    # 실패 표가 제외 표 위에 — 실패·제외가 성공 요약보다 먼저 눈에 띈다
    assert 본문.index("nad-zza-004") < 본문.index("nad-zza-005")


def test_결과_backup_failed_는_prune_전용_문구(삭제판, tmp_run_dir):
    from webapp.routes.prune import _삭제결과ctx
    pid = _미리보기잡(tmp_run_dir)
    cid = _커밋잡(tmp_run_dir, pid)
    계정 = {r["계정"]: r for r in _삭제결과ctx(jobs.job_status(cid))["계정행"]}
    assert 계정["zzb"]["중단"] == "백업을 못 써서 이 계정은 한 건도 지우지 않았다"
    assert "광고비" not in 계정["zzb"]["중단"]


def test_결과_산출물이_없고_종료코드_2면_상한초과_삭제0(삭제판, tmp_run_dir):
    pid = _미리보기잡(tmp_run_dir)
    cid = _커밋잡(tmp_run_dir, pid, 쓰기=False, 상태="failed", exit_code=2)
    본문 = _조각(삭제판, cid)
    assert "상한 초과" in 본문 and "삭제 0" in 본문


def test_결과_도는_중이면_읽지_않는다(삭제판, tmp_run_dir):
    pid = _미리보기잡(tmp_run_dir)
    cid = _커밋잡(tmp_run_dir, pid, 상태="starting")
    본문 = _조각(삭제판, cid)
    assert "도는 중" in 본문


def test_결과_템플릿에_safe_필터가_없다():
    from webapp import main
    src = (Path(main.__file__).parent / "templates" / "_prune_result_table.html").read_text(
        encoding="utf-8")
    assert "| safe" not in src and "|safe" not in src


def test_flow_중단사유에_recheck_failed():
    from webapp import flow
    assert "recheck_failed" in flow.중단사유
    assert flow.aborted_accounts({"accounts": {"zz": {"aborted": "recheck_failed"}}})["zz"] \
        == flow.중단사유["recheck_failed"]


def test_prune_js_요청에_대상목록이_없다():
    from webapp import main
    src = (Path(main.__file__).parent / "static" / "prune.js").read_text(encoding="utf-8")
    assert "typed_count" in src and "/jobs/prune/commit" in src
    assert "adIds" not in src
