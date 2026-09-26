#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""마켓 수정업로드 라우트(`/jobs/market/*`) 검증 — Phase 6 / 06-03. **실제 CLI 는 한 번도 안 뜬다.**

보는 것:
  · 요청은 잡 id 하나 — 대상·상한·마켓 필드가 없다(L-02 · L-07 · T-06-15)
  · 대상은 서버가 정본(detail_status.json · preview.json)에서 만든다
  · 게이트 판정 전에는 반영이 항상 1건이다(D-09 · SC-2) — 상한은 서버 결정(T-06-16)
  · 미리보기·결과 조각에 ⓐ·ⓑ 백업 경로가 텍스트로 보인다(D-04 · MARKET-03)
  · 결과 표에 재반영 버튼이 없고 '이어서 확인' 만 있다(D-08)

산출물(preview.json · market_status.json)은 06-02 계약 모양으로 tmp 회차에 직접 깐다.
"""
import json
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from webapp import jobs
from webapp.tests.test_routes_jobs import 기대닉, 안띄운다, 엿듣기, 프로필, 화면  # noqa: F401

미리보기경로 = "/jobs/market/preview"
반영경로 = "/jobs/market/commit"
확인경로 = "/jobs/market/poll"


# ── 도우미 ──────────────────────────────────────────────────────────────────

def _지금(시간전: float = 0) -> str:
    return (datetime.now().astimezone() - timedelta(hours=시간전)).isoformat(timespec="seconds")


def _행박기(tmp_run_dir, kind, *, 상태="done", exit_code=0, parent=None,
           targets=None, result=None, 시작=None) -> str:
    job_id = str(uuid.uuid4())
    cx = sqlite3.connect(jobs.db_path())
    try:
        cx.execute("INSERT INTO jobs (id, kind, run_dir, accounts, argv, status, log_path, "
                   "targets_path, result_path, parent_job_id, exit_code, started_at) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                   (job_id, kind, tmp_run_dir.name, "[]", "[]", 상태,
                    str(tmp_run_dir / "x.log"), str(targets) if targets else None,
                    str(result) if result else None, parent, exit_code, 시작 or _지금()))
        cx.commit()
    finally:
        cx.close()
    return job_id


def _쓰기(p: Path, 문서) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(문서, ensure_ascii=False), encoding="utf-8")
    return p


_상세입력 = {"items": [
    {"productId": "zzp1", "판매자상품코드": "zz01"},
    {"productId": "zzp2", "판매자상품코드": "zz02"},
    {"productId": "zzp3", "판매자상품코드": "zz03"},
    {"productId": "zzp4", "판매자상품코드": "zz04"}], "제외": [], "선택": 4}

_상세체크 = {"zzp1": {"taskId": "task-zz-0001", "status": "완료", "pages": 10},
            "zzp2": {"taskId": "task-zz-0002", "status": "완료", "pages": 10},
            "zzp3": {"taskId": "task-zz-0003", "status": "실패", "pages": 10},
            "zzp4": {"taskId": "task-zz-0004", "status": "완료", "pages": 10}}


def _상세체인(tmp_run_dir, *, 상태="done", exit_code=0, 체크=None,
             kind="detail_submit") -> str:
    """견적 → 접수 행 + detail_status.json. 접수(또는 이어서 확인) 잡 id 를 돌려준다."""
    웹 = tmp_run_dir / "web"
    견적 = str(uuid.uuid4())
    대상 = _쓰기(웹 / f"targets_{견적}.json", _상세입력)
    폴더 = 웹 / f"detail_{견적}"
    견적 = _행박기(tmp_run_dir, "detail_estimate", targets=대상, result=폴더 / "estimate.json")
    # 폴더 이름을 실제 견적 id 로 다시 맞춘다
    폴더 = 웹 / f"detail_{견적}"
    _쓰기(폴더 / "detail_status.json", _상세체크 if 체크 is None else 체크)
    접수 = _행박기(tmp_run_dir, "detail_submit", 상태=상태, exit_code=exit_code,
                  parent=견적, targets=대상, result=폴더 / "summary_x.json")
    if kind == "detail_poll":
        return _행박기(tmp_run_dir, "detail_poll", 상태=상태, exit_code=exit_code,
                      parent=접수, targets=대상, result=폴더 / "summary_y.json")
    return 접수


def _미리보기항목(pid, 코드, 판정="반영가능", 사유="", 폴더=None, a있음=True):
    a = str((폴더 or Path("/tmp/zz")) / "before_detail" / f"{pid}.json")
    return {"productId": pid, "판매자상품코드": 코드, "판정": 판정, "사유": 사유,
            "backup_a": a, "backup_a_있음": a있음,
            "backup_b": str((폴더 or Path("/tmp/zz")) / "before_market" / f"{pid}.json"),
            "채널상품번호": f"99{pid[-1]}", "상단이미지": "https://zzcdn.example/t.jpg",
            "하단이미지": "https://zzcdn.example/b.jpg", "상하단날짜": "2026-09-01",
            "마켓그룹": "15-2_zz", "미리보기요약": "zz요약"}


def _미리보기체인(tmp_run_dir, *, 항목=None, 상태="done", exit_code=0, 시간전=0.0,
               market_status=None) -> tuple[str, Path]:
    """접수 → 미리보기 행 + preview.json. (미리보기 id, market 폴더) 를 돌려준다."""
    접수 = _상세체인(tmp_run_dir)
    웹 = tmp_run_dir / "web"
    임시 = str(uuid.uuid4())
    대상 = _쓰기(웹 / f"targets_{임시}.json", {"items": [
        {"productId": p, "판매자상품코드": c} for p, c in
        (("zzp1", "zz01"), ("zzp2", "zz02"), ("zzp4", "zz04"))]})
    미리 = _행박기(tmp_run_dir, "market_preview", 상태=상태, exit_code=exit_code, parent=접수,
                  targets=대상, result=None, 시작=_지금(시간전))
    폴더 = 웹 / f"market_{미리}"
    상세폴더 = Path(jobs._row(접수)["result_path"]).parent
    if 항목 is None:
        항목 = [_미리보기항목("zzp1", "zz01", 폴더=상세폴더),
                _미리보기항목("zzp2", "zz02", 폴더=상세폴더),
                _미리보기항목("zzp4", "zz04", 폴더=상세폴더),
                _미리보기항목("zzp9", "zz09", 판정="스킵", 사유="미업로드", 폴더=상세폴더,
                          a있음=False)]
    _쓰기(폴더 / "preview.json", {"모드": "preview", "계정": "zz기대닉", "items": 항목,
                                  "집계": {"반영가능": sum(1 for x in 항목 if x["판정"] == "반영가능"),
                                         "스킵": sum(1 for x in 항목 if x["판정"] == "스킵"),
                                         "실패": 0, "전체": len(항목)}})
    cx = sqlite3.connect(jobs.db_path())
    try:
        cx.execute("UPDATE jobs SET result_path=? WHERE id=?", (str(폴더 / "preview.json"), 미리))
        cx.commit()
    finally:
        cx.close()
    if market_status is not None:
        _쓰기(폴더 / "market_status.json", market_status)
    return 미리, 폴더


def _반영행(tmp_run_dir, 미리, 폴더, *, 상태="done", exit_code=0, kind="market_commit",
           parent=None, 대상=None) -> str:
    임시 = str(uuid.uuid4())
    대상 = 대상 or _쓰기(tmp_run_dir / "web" / f"targets_{임시}.json",
                       {"items": [{"productId": "zzp1", "판매자상품코드": "zz01"}]})
    return _행박기(tmp_run_dir, kind, 상태=상태, exit_code=exit_code, parent=parent or 미리,
                  targets=대상, result=폴더 / f"summary_{임시}.json")


# ── 요청 모델 ───────────────────────────────────────────────────────────────

def test_요청모델은_잡id_하나뿐():
    """대상·상한·마켓 필드가 없다 — 받을 필드 자체를 두지 않는다(L-02 · L-07 · D-09)."""
    from webapp.routes.jobs import MarketCommitReq, MarketPollReq, MarketPreviewReq
    assert set(MarketPreviewReq.model_fields) == {"detail_job_id"}
    assert set(MarketCommitReq.model_fields) == {"preview_job_id"}
    assert set(MarketPollReq.model_fields) == {"commit_job_id"}


def test_반영_라우트_잡id만_모르는필드는_422(화면, 엿듣기, tmp_run_dir):
    미리, _ = _미리보기체인(tmp_run_dir)
    for 덤 in ({"targets": ["zzp4"]}, {"max_items": 20}, {"market": "COUPANG"}):
        응답 = 화면.post(반영경로, json={"preview_job_id": 미리, **덤})
        assert 응답.status_code == 422, 응답.text
    assert not 엿듣기


def test_토큰없이_403(화면, 엿듣기, tmp_run_dir):
    접수 = _상세체인(tmp_run_dir)
    for 경로, 몸통 in ((미리보기경로, {"detail_job_id": 접수}),
                     (반영경로, {"preview_job_id": 접수}),
                     (확인경로, {"commit_job_id": 접수})):
        응답 = 화면.post(경로, json=몸통, headers={"X-CT-Token": "wrong-token"})
        assert 응답.status_code == 403
    assert not 엿듣기


def test_GET은_작업을_안만든다(화면, 엿듣기):
    for 경로 in (미리보기경로, 반영경로, 확인경로):
        assert 화면.get(경로).status_code == 405
    assert not 엿듣기


def test_잡id모양이_아니면_422(화면, 엿듣기):
    for 경로, 키 in ((미리보기경로, "detail_job_id"), (반영경로, "preview_job_id"),
                   (확인경로, "commit_job_id")):
        assert 화면.post(경로, json={키: "../../x"}).status_code == 422
    assert not 엿듣기


# ── 미리보기 ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("kind,상태,코드", [("detail_submit", "done", 0),
                                          ("detail_submit", "done", 3),
                                          ("detail_poll", "done", 0)])
def test_미리보기_라우트_완료항목만(화면, 엿듣기, tmp_run_dir, kind, 상태, 코드):
    """대상 = detail_status.json 의 완료 항목만(실패 zzp3 제외) · 판매자상품코드는 부모 대상에서."""
    부모 = _상세체인(tmp_run_dir, 상태=상태, exit_code=코드, kind=kind)
    응답 = 화면.post(미리보기경로, json={"detail_job_id": 부모})
    assert 응답.status_code == 200, 응답.text
    assert 엿듣기["kind"] == "market_preview"
    assert 엿듣기["parent_job_id"] == 부모
    assert 엿듣기["run_dir"] == tmp_run_dir.name
    assert 엿듣기["detail_inputs"] == {"items": [
        {"productId": "zzp1", "판매자상품코드": "zz01"},
        {"productId": "zzp2", "판매자상품코드": "zz02"},
        {"productId": "zzp4", "판매자상품코드": "zz04"}]}


def test_미리보기_부모kind틀리면_400(화면, 엿듣기, tmp_run_dir):
    미리, _ = _미리보기체인(tmp_run_dir)
    응답 = 화면.post(미리보기경로, json={"detail_job_id": 미리})
    assert 응답.status_code == 400
    응답 = 화면.post(미리보기경로, json={"detail_job_id": "00000000-0000-4000-8000-000000000000"})
    assert 응답.status_code == 400
    assert not 엿듣기


def test_미리보기_부모running이면_400(화면, 엿듣기, tmp_run_dir):
    부모 = _상세체인(tmp_run_dir, 상태="running", exit_code=None)
    assert 화면.post(미리보기경로, json={"detail_job_id": 부모}).status_code == 400
    assert not 엿듣기


def test_미리보기_완료0건이면_400(화면, 엿듣기, tmp_run_dir):
    부모 = _상세체인(tmp_run_dir, 체크={"zzp1": {"taskId": "t1", "status": "실패"}})
    응답 = 화면.post(미리보기경로, json={"detail_job_id": 부모})
    assert 응답.status_code == 400
    assert "완료 항목이 없다" in 응답.json()["detail"]
    assert not 엿듣기


def test_미리보기_계정불일치면_409(화면, 안띄운다, 프로필, 기대닉, tmp_run_dir):
    프로필("zz다른계정")
    부모 = _상세체인(tmp_run_dir)
    응답 = 화면.post(미리보기경로, json={"detail_job_id": 부모})
    assert 응답.status_code == 409, 응답.text


def test_미리보기_진짜_create_job_argv(화면, 안띄운다, 프로필, 기대닉, tmp_run_dir, monkeypatch):
    from webapp import settings as 설정
    monkeypatch.setattr(설정, "load", lambda force=False: None)
    프로필()
    부모 = _상세체인(tmp_run_dir)
    응답 = 화면.post(미리보기경로, json={"detail_job_id": 부모})
    assert 응답.status_code == 200, 응답.text
    새 = 응답.json()["job_id"]
    av = json.loads(jobs._row(새)["argv"])
    assert "--preview" in av and "--commit" not in av and "--max-items" not in av
    assert Path(av[av.index("--run-dir") + 1]).name == f"market_{새}"
    assert av[av.index("--detail-backup-dir") + 1].endswith("before_detail")
    대상 = json.loads(Path(av[av.index("--targets") + 1]).read_text(encoding="utf-8"))
    assert [x["productId"] for x in 대상["items"]] == ["zzp1", "zzp2", "zzp4"]


# ── 반영 ────────────────────────────────────────────────────────────────────

def test_반영_게이트전_1건(화면, 안띄운다, 프로필, 기대닉, tmp_run_dir, monkeypatch):
    """반영가능 3건이어도 진짜 argv 는 --max-items 1 · 대상 파일 1건(미리보기 순서 첫 건)."""
    from webapp import settings as 설정
    monkeypatch.setattr(설정, "load", lambda force=False: None)
    프로필()
    미리, 폴더 = _미리보기체인(tmp_run_dir)
    응답 = 화면.post(반영경로, json={"preview_job_id": 미리})
    assert 응답.status_code == 200, 응답.text
    새 = 응답.json()["job_id"]
    av = json.loads(jobs._row(새)["argv"])
    assert av[av.index("--max-items") + 1] == "1"
    assert "--commit" in av
    assert Path(av[av.index("--run-dir") + 1]) == 폴더
    대상 = json.loads(Path(av[av.index("--targets") + 1]).read_text(encoding="utf-8"))
    assert 대상 == {"items": [{"productId": "zzp1", "판매자상품코드": "zz01"}]}


def test_반영_상한은_서버결정(화면, 엿듣기, tmp_run_dir):
    미리, _ = _미리보기체인(tmp_run_dir)
    assert 화면.post(반영경로, json={"preview_job_id": 미리}).status_code == 200
    assert 엿듣기["kind"] == "market_commit"
    assert 엿듣기["max_items"] == 1
    assert 엿듣기["parent_job_id"] == 미리
    assert len(엿듣기["detail_inputs"]["items"]) == 1


@pytest.mark.parametrize("상태,코드", [("running", None), ("failed", 2), ("done", 3),
                                      ("orphaned", None)])
def test_반영_부모검사(화면, 엿듣기, tmp_run_dir, 상태, 코드):
    미리, _ = _미리보기체인(tmp_run_dir, 상태=상태, exit_code=코드)
    assert 화면.post(반영경로, json={"preview_job_id": 미리}).status_code == 400
    assert not 엿듣기


def test_반영_부모가_미리보기가_아니면_400(화면, 엿듣기, tmp_run_dir):
    접수 = _상세체인(tmp_run_dir)
    assert 화면.post(반영경로, json={"preview_job_id": 접수}).status_code == 400
    assert not 엿듣기


def test_반영_미리보기_24시간_경과는_400(화면, 엿듣기, tmp_run_dir):
    미리, _ = _미리보기체인(tmp_run_dir, 시간전=25)
    응답 = 화면.post(반영경로, json={"preview_job_id": 미리})
    assert 응답.status_code == 400
    assert "새 미리보기부터" in 응답.json()["detail"]
    assert not 엿듣기


def test_반영_자식이_도는중이면_400(화면, 엿듣기, tmp_run_dir):
    미리, 폴더 = _미리보기체인(tmp_run_dir)
    _반영행(tmp_run_dir, 미리, 폴더, 상태="running", exit_code=None)
    assert 화면.post(반영경로, json={"preview_job_id": 미리}).status_code == 400
    assert not 엿듣기


def test_반영_게이트전_두번째는_거부(화면, 엿듣기, tmp_run_dir):
    """게이트 판정 전(상한 1)에는 한 미리보기에서 반영이 한 번뿐이다 — 두 번 누르면 2건이 나간다."""
    미리, 폴더 = _미리보기체인(tmp_run_dir, market_status={"워터마크": "100", "items": {
        "zzp1": {"판매자상품코드": "zz01", "status": "성공", "taskId": "200"}}})
    _반영행(tmp_run_dir, 미리, 폴더)
    응답 = 화면.post(반영경로, json={"preview_job_id": 미리})
    assert 응답.status_code == 400
    assert "게이트" in 응답.json()["detail"]
    assert not 엿듣기


def test_반영_게이트전_앞선반영이_아무것도_안썼으면_다시_허용(화면, 엿듣기, tmp_run_dir):
    """앞선 반영이 쓰기 전에 실패(계정 불일치 exit 4 등)했고 체크포인트에 아무것도 없으면 다시 누를 수 있다."""
    미리, 폴더 = _미리보기체인(tmp_run_dir)
    _반영행(tmp_run_dir, 미리, 폴더, 상태="failed", exit_code=4)
    assert 화면.post(반영경로, json={"preview_job_id": 미리}).status_code == 200
    assert 엿듣기["max_items"] == 1


def test_반영_두번째_허용_세번째_거부(화면, 엿듣기, tmp_run_dir, monkeypatch):
    """게이트 통과(상한 >1) 뒤엔 두 번째 반영이 된다 — 남은 반영가능만. 세 번째는 400(Pitfall 5)."""
    from webapp.routes import jobs as 라우트
    monkeypatch.setattr(라우트, "_마켓반영상한", lambda: 20)
    미리, 폴더 = _미리보기체인(tmp_run_dir, market_status={"워터마크": "100", "items": {
        "zzp1": {"판매자상품코드": "zz01", "status": "성공", "taskId": "200"}}})
    _반영행(tmp_run_dir, 미리, 폴더)
    응답 = 화면.post(반영경로, json={"preview_job_id": 미리})
    assert 응답.status_code == 200, 응답.text
    assert 엿듣기["max_items"] == 20
    assert [x["productId"] for x in 엿듣기["detail_inputs"]["items"]] == ["zzp2", "zzp4"]
    엿듣기.clear()
    _반영행(tmp_run_dir, 미리, 폴더)
    응답 = 화면.post(반영경로, json={"preview_job_id": 미리})
    assert 응답.status_code == 400
    assert not 엿듣기


def test_반영_남은_반영가능_0건이면_400(화면, 엿듣기, tmp_run_dir, monkeypatch):
    from webapp.routes import jobs as 라우트
    monkeypatch.setattr(라우트, "_마켓반영상한", lambda: 20)
    미리, 폴더 = _미리보기체인(tmp_run_dir, market_status={"워터마크": "100", "items": {
        p: {"판매자상품코드": c, "status": s, "taskId": t} for p, c, s, t in (
            ("zzp1", "zz01", "성공", "201"), ("zzp2", "zz02", "대기", None),
            ("zzp4", "zz04", "접수", "203"))}})
    응답 = 화면.post(반영경로, json={"preview_job_id": 미리})
    assert 응답.status_code == 400
    assert not 엿듣기


def test_반영_체크포인트가_깨졌으면_400(화면, 엿듣기, tmp_run_dir):
    """깨진 market_status.json 을 빈 값으로 읽으면 이미 반영된 건을 다시 반영한다."""
    미리, 폴더 = _미리보기체인(tmp_run_dir)
    (폴더 / "market_status.json").write_text("{깨짐", encoding="utf-8")
    assert 화면.post(반영경로, json={"preview_job_id": 미리}).status_code == 400
    assert not 엿듣기


def test_반영_계정불일치면_409(화면, 안띄운다, 프로필, 기대닉, tmp_run_dir):
    프로필("zz다른계정")
    미리, _ = _미리보기체인(tmp_run_dir)
    assert 화면.post(반영경로, json={"preview_job_id": 미리}).status_code == 409


# ── 이어서 확인 ─────────────────────────────────────────────────────────────

_체크_대기 = {"워터마크": "100", "items": {
    "zzp1": {"판매자상품코드": "zz01", "status": "대기", "taskId": "201", "사유": "",
             "backup_a": "/tmp/zz/a.json", "backup_b": "/tmp/zz/b.json"}}}
_체크_종결 = {"워터마크": "100", "items": {
    "zzp1": {"판매자상품코드": "zz01", "status": "성공", "taskId": "task-zz-00000201",
             "사유": "", "backup_a": "/tmp/zz/a.json", "backup_b": "/tmp/zz/b.json"}}}


@pytest.mark.parametrize("상태,코드,체크", [("done", 3, _체크_종결), ("orphaned", None, _체크_대기),
                                          ("done", 0, _체크_대기)])
def test_이어서확인_라우트_허용(화면, 엿듣기, tmp_run_dir, 상태, 코드, 체크):
    미리, 폴더 = _미리보기체인(tmp_run_dir, market_status=체크)
    반영 = _반영행(tmp_run_dir, 미리, 폴더, 상태=상태, exit_code=코드)
    응답 = 화면.post(확인경로, json={"commit_job_id": 반영})
    assert 응답.status_code == 200, 응답.text
    assert 엿듣기["kind"] == "market_poll"
    assert 엿듣기["parent_job_id"] == 반영
    assert str(엿듣기["targets_path_override"]) == jobs._row(반영)["targets_path"]
    assert 엿듣기.get("max_items") is None


def test_이어서확인_poll의_poll도_된다(화면, 엿듣기, tmp_run_dir):
    미리, 폴더 = _미리보기체인(tmp_run_dir, market_status=_체크_대기)
    반영 = _반영행(tmp_run_dir, 미리, 폴더, 상태="done", exit_code=3)
    확인 = _반영행(tmp_run_dir, 미리, 폴더, kind="market_poll", parent=반영, exit_code=3,
                  대상=jobs._row(반영)["targets_path"])
    assert 화면.post(확인경로, json={"commit_job_id": 확인}).status_code == 200


@pytest.mark.parametrize("상태,코드,체크", [("failed", 2, _체크_대기), ("failed", 5, _체크_대기),
                                          ("running", None, _체크_대기), ("done", 0, _체크_종결),
                                          ("orphaned", None, _체크_종결)])
def test_이어서확인_거부(화면, 엿듣기, tmp_run_dir, 상태, 코드, 체크):
    미리, 폴더 = _미리보기체인(tmp_run_dir, market_status=체크)
    반영 = _반영행(tmp_run_dir, 미리, 폴더, 상태=상태, exit_code=코드)
    assert 화면.post(확인경로, json={"commit_job_id": 반영}).status_code == 400
    assert not 엿듣기


def test_이어서확인_부모가_미리보기면_400(화면, 엿듣기, tmp_run_dir):
    미리, _ = _미리보기체인(tmp_run_dir, market_status=_체크_대기)
    assert 화면.post(확인경로, json={"commit_job_id": 미리}).status_code == 400
    assert not 엿듣기


# ── 조각 ────────────────────────────────────────────────────────────────────

def test_미리보기_조각(화면, tmp_run_dir):
    """행마다 코드·판정·사유·ⓐ 경로 텍스트+있음/없음·ⓑ 경로·채널상품번호·상하단날짜.
    버튼은 '첫 1건만 반영 (육안 확인 게이트)' 하나, 2번째 이후 반영가능은 '게이트 대기'."""
    미리, 폴더 = _미리보기체인(tmp_run_dir)
    상세폴더 = Path(json.loads(Path(jobs._row(미리)["result_path"]).read_text(
        encoding="utf-8"))["items"][0]["backup_a"]).parent
    상세폴더.mkdir(parents=True, exist_ok=True)
    (상세폴더 / "zzp1.json").write_text("{}", encoding="utf-8")   # zzp1 만 ⓐ 실제 파일 있음
    응답 = 화면.get(f"/jobs/{미리}/result", headers={"HX-Request": "true"})
    assert 응답.status_code == 200
    본문 = 응답.text
    for 말 in ("zz01", "zz02", "zz04", "zz09", "반영가능", "스킵", "미업로드",
               str(상세폴더 / "zzp1.json"), str(폴더 / "before_market" / "zzp1.json"),
               "991", "2026-09-01", "있음", "없음"):
        assert 말 in 본문, 말
    assert "첫 1건만 반영 (육안 확인 게이트)" in 본문
    assert 본문.count("게이트 대기") == 2
    assert f'data-preview-job="{미리}"' in 본문
    assert 본문.count("market-commit-btn") == 1


def test_미리보기_ctx_json(화면, tmp_run_dir):
    미리, _ = _미리보기체인(tmp_run_dir)
    j = 화면.get(f"/jobs/{미리}/result?format=json").json()
    assert j["error"] is None
    assert j["상한"] == 1
    표시 = {h["판매자상품코드"]: h["반영표시"] for h in j["항목"]}
    assert 표시["zz01"] == "이번 반영"
    assert 표시["zz02"] == "게이트 대기" and 표시["zz04"] == "게이트 대기"
    assert 표시["zz09"] == ""


def test_미리보기_조각_반영가능0이면_버튼없음(화면, tmp_run_dir):
    미리, _ = _미리보기체인(tmp_run_dir, 항목=[
        _미리보기항목("zzp9", "zz09", 판정="스킵", 사유="AI상세없음")])
    본문 = 화면.get(f"/jobs/{미리}/result", headers={"HX-Request": "true"}).text
    assert "market-commit-btn" not in 본문


def test_미리보기_조각_도는중(화면, tmp_run_dir):
    미리, _ = _미리보기체인(tmp_run_dir, 상태="starting", exit_code=None)
    본문 = 화면.get(f"/jobs/{미리}/result", headers={"HX-Request": "true"}).text
    assert "도는 중" in 본문 and "market-commit-btn" not in 본문


def test_미리보기_산출물없으면_에러(화면, tmp_run_dir):
    미리, 폴더 = _미리보기체인(tmp_run_dir, 상태="failed", exit_code=4)
    (폴더 / "preview.json").unlink()
    j = 화면.get(f"/jobs/{미리}/result?format=json").json()
    assert j["error"] and "계정" in j["error"]


def test_결과_조각(화면, tmp_run_dir):
    """market_status.json 정본 · 항목 행 · 작업번호 끝 8자리 · 미반영(게이트 대기) 행 · 재반영 버튼 없음."""
    미리, 폴더 = _미리보기체인(tmp_run_dir, market_status=_체크_종결)
    반영 = _반영행(tmp_run_dir, 미리, 폴더)
    j = 화면.get(f"/jobs/{반영}/result?format=json").json()
    assert j["error"] is None
    상태들 = {h["판매자상품코드"]: h["상태"] for h in j["항목"]}
    assert 상태들["zz01"] == "성공"
    assert 상태들["zz02"] == "미반영(게이트 대기)" and 상태들["zz04"] == "미반영(게이트 대기)"
    assert j["집계"]["성공"] == 1 and j["집계"]["미반영"] == 2
    assert j["이어서확인가능"] is False
    zz01 = next(h for h in j["항목"] if h["판매자상품코드"] == "zz01")
    assert zz01["taskId"] == "00000201"
    assert zz01["backup_a"] == "/tmp/zz/a.json" and zz01["backup_b"] == "/tmp/zz/b.json"

    본문 = 화면.get(f"/jobs/{반영}/result", headers={"HX-Request": "true"}).text
    for 말 in ("zz01", "성공", "00000201", "/tmp/zz/a.json", "/tmp/zz/b.json",
               "미반영(게이트 대기)"):
        assert 말 in 본문, 말
    assert "market-poll-btn" not in 본문
    assert "market-commit-btn" not in 본문 and "재반영" not in 본문.replace("재반영 버튼", "")
    assert 본문.count('id="market-gate-slot"') == 1


def test_결과_조각_대기면_이어서확인(화면, tmp_run_dir):
    미리, 폴더 = _미리보기체인(tmp_run_dir, market_status=_체크_대기)
    반영 = _반영행(tmp_run_dir, 미리, 폴더, exit_code=3)
    본문 = 화면.get(f"/jobs/{반영}/result", headers={"HX-Request": "true"}).text
    assert "이어서 확인" in 본문 and "실패 아님" in 본문
    assert f'data-commit-job="{반영}"' in 본문
    assert 본문.count("market-poll-btn") == 1


def test_결과_체크포인트없으면_에러(화면, tmp_run_dir):
    미리, 폴더 = _미리보기체인(tmp_run_dir)
    반영 = _반영행(tmp_run_dir, 미리, 폴더, 상태="failed", exit_code=4)
    j = 화면.get(f"/jobs/{반영}/result?format=json").json()
    assert j["error"] and j["항목"] == []
    본문 = 화면.get(f"/jobs/{반영}/result", headers={"HX-Request": "true"}).text
    assert "<table" not in 본문


def test_결과_체크포인트깨졌으면_에러(화면, tmp_run_dir):
    미리, 폴더 = _미리보기체인(tmp_run_dir)
    (폴더 / "market_status.json").write_text("[1,2", encoding="utf-8")
    반영 = _반영행(tmp_run_dir, 미리, 폴더)
    j = 화면.get(f"/jobs/{반영}/result?format=json").json()
    assert j["error"]


def test_조각_이스케이프(화면, tmp_run_dir):
    """서버 원문(사유)에 <script> 가 있어도 이스케이프된다 — `| safe` 없음(T-06-19)."""
    독 = "<script>alert(1)</script>"
    미리, 폴더 = _미리보기체인(tmp_run_dir, 항목=[
        _미리보기항목("zzp1", "zz01", 판정="스킵", 사유=독)],
        market_status={"워터마크": None, "items": {
            "zzp1": {"판매자상품코드": "zz01", "status": "실패", "taskId": "1", "사유": 독}}})
    반영 = _반영행(tmp_run_dir, 미리, 폴더)
    for 잡 in (미리, 반영):
        본문 = 화면.get(f"/jobs/{잡}/result", headers={"HX-Request": "true"}).text
        assert 독 not in 본문
        assert "&lt;script&gt;" in 본문


def test_템플릿에_safe_없음():
    루트 = Path(__file__).resolve().parents[1] / "templates"
    for 이름 in ("_market_preview_table.html", "_market_result_table.html"):
        본문 = (루트 / 이름).read_text(encoding="utf-8")
        assert "| safe" not in 본문 and "|safe" not in 본문


def test_상태조각_market_이름과_exit3(화면, tmp_run_dir):
    미리, 폴더 = _미리보기체인(tmp_run_dir, market_status=_체크_대기)
    반영 = _반영행(tmp_run_dir, 미리, 폴더, exit_code=3)
    본문 = 화면.get(f"/jobs/{반영}", headers={"HX-Request": "true"}).text
    assert "마켓 반영" in 본문
    assert "대기 미완 — 실패 아님" in 본문
    assert "실패했다" not in 본문


@pytest.mark.parametrize("코드,말", [(2, "쓰기의심"), (4, "계정 불일치"), (5, "상한 초과")])
def test_상태조각_market_실패코드별_문구(화면, tmp_run_dir, 코드, 말):
    미리, 폴더 = _미리보기체인(tmp_run_dir)
    반영 = _반영행(tmp_run_dir, 미리, 폴더, 상태="failed", exit_code=코드)
    본문 = 화면.get(f"/jobs/{반영}", headers={"HX-Request": "true"}).text
    assert 말 in 본문
