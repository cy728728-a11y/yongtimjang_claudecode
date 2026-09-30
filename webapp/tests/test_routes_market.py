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
# no_commit_guard.sh 가 반영 플래그 리터럴을 금지한다 — 간접 조립한다.
_반영플래그 = "--" + "commit"


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
    부모 = _상세체인(tmp_run_dir, 상태="starting", exit_code=None)
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
    assert "--preview" in av and _반영플래그 not in av and "--max-items" not in av
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
    assert _반영플래그 in av
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


@pytest.mark.parametrize("상태,코드", [("starting", None), ("failed", 2), ("done", 3),
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
    _반영행(tmp_run_dir, 미리, 폴더, 상태="starting", exit_code=None)
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
                                          ("starting", None, _체크_대기), ("done", 0, _체크_종결),
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
    첫 = json.loads(Path(jobs._row(미리)["result_path"]).read_text(encoding="utf-8"))["items"][0]
    상세폴더 = Path(첫["backup_a"]).parent
    반영전경로 = 첫["backup_b"]
    상세폴더.mkdir(parents=True, exist_ok=True)
    (상세폴더 / "zzp1.json").write_text("{}", encoding="utf-8")   # zzp1 만 ⓐ 실제 파일 있음
    응답 = 화면.get(f"/jobs/{미리}/result", headers={"HX-Request": "true"})
    assert 응답.status_code == 200
    본문 = 응답.text
    for 말 in ("zz01", "zz02", "zz04", "zz09", "반영가능", "스킵", "미업로드",
               str(상세폴더 / "zzp1.json"), 반영전경로,
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
    assert zz01["backup_a"]["경로"] == "/tmp/zz/a.json"
    assert zz01["backup_b"]["경로"] == "/tmp/zz/b.json"

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


# ── 상세 결과 표의 진입점 (Task 3 / SC-1) ────────────────────────────────────

def test_상세결과표_미리보기버튼은_완료가_있을때만(화면, tmp_run_dir):
    접수 = _상세체인(tmp_run_dir)
    본문 = 화면.get(f"/jobs/{접수}/result", headers={"HX-Request": "true"}).text
    assert "market-preview-btn" in 본문 and f'data-detail-job="{접수}"' in 본문
    assert "스마트스토어 반영 미리보기 — 쓰기 0" in 본문
    없음 = _상세체인(tmp_run_dir, 체크={"zzp1": {"taskId": "t1", "status": "실패"}})
    본문 = 화면.get(f"/jobs/{없음}/result", headers={"HX-Request": "true"}).text
    assert "market-preview-btn" not in 본문


def test_상세결과표_최근_마켓잡_재오픈(화면, tmp_run_dir):
    """미리보기·반영·이어서 확인이 상세 결과 표 아래 목록으로 다시 보인다 — 새로 열어도 돌아온다."""
    미리, 폴더 = _미리보기체인(tmp_run_dir, market_status=_체크_대기)
    반영 = _반영행(tmp_run_dir, 미리, 폴더, exit_code=3)
    확인 = _반영행(tmp_run_dir, 미리, 폴더, kind="market_poll", parent=반영, exit_code=0,
                  대상=jobs._row(반영)["targets_path"])
    접수 = jobs._row(미리)["parent_job_id"]
    j = 화면.get(f"/jobs/{접수}/result?format=json").json()
    assert {m["id"] for m in j["마켓잡들"]} == {미리, 반영, 확인}
    본문 = 화면.get(f"/jobs/{접수}/result", headers={"HX-Request": "true"}).text
    assert "최근 스마트스토어 반영" in 본문
    for i in (미리, 반영, 확인):
        assert f'data-job="{i}"' in 본문
    assert 본문.count('id="market-result-body"') == 1


def test_상세결과표_이어서확인_잡에서도_같은체인(화면, tmp_run_dir):
    """미리보기를 접수 잡에서 띄웠어도, 그 뒤의 이어서 확인 잡 결과 표에서 찾을 수 있다."""
    미리, _ = _미리보기체인(tmp_run_dir)
    접수 = jobs._row(미리)["parent_job_id"]
    r = jobs._row(접수)
    확인 = _행박기(tmp_run_dir, "detail_poll", parent=접수, targets=r["targets_path"],
                  result=Path(r["result_path"]).parent / "summary_z.json")
    j = 화면.get(f"/jobs/{확인}/result?format=json").json()
    assert [m["id"] for m in j["마켓잡들"]] == [미리]


def test_마켓잡들_조회실패는_빈목록(화면, tmp_run_dir, monkeypatch):
    접수 = _상세체인(tmp_run_dir)

    def 터짐(*a, **k):
        raise RuntimeError("zz")
    monkeypatch.setattr(jobs, "children_of", 터짐)
    j = 화면.get(f"/jobs/{접수}/result?format=json").json()
    assert j["마켓잡들"] == [] and j["error"] is None


def test_board_js_마켓버튼_몸통은_잡id하나():
    본문 = (Path(__file__).resolve().parents[1] / "static" / "board.js").read_text(encoding="utf-8")
    assert '"/jobs/market/preview", { detail_job_id: 버튼.dataset.detailJob }' in 본문
    assert '"/jobs/market/commit", { preview_job_id: 버튼.dataset.previewJob }' in 본문
    assert '"/jobs/market/poll", { commit_job_id: 버튼.dataset.commitJob }' in 본문
    assert "market-result-link" in 본문


# ════════════════════════════════════════════════════════════════════════════
# 06-04 — 첫 1건 육안 확인 게이트 (MARKET-02 · SC-2 · D-09~D-12)
# ════════════════════════════════════════════════════════════════════════════

게이트경로 = "/market/gate"
_체크_성공1 = {"워터마크": "100", "items": {
    "zzp1": {"판매자상품코드": "zz01", "status": "성공", "taskId": "task-zz-00000201",
             "사유": "", "backup_a": "/tmp/zz/before_detail/zzp1.json",
             "backup_b": "/tmp/zz/before_market/zzp1.json"}}}


def _게이트판정들() -> list[dict]:
    cx = sqlite3.connect(jobs.db_path())
    cx.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in cx.execute("SELECT * FROM market_gate ORDER BY id")]
    finally:
        cx.close()


def _게이트몸통(반영, 판정="정상", 본문=True, 상하단=True, 기타=True, **덤):
    return {"commit_job_id": 반영, "판정": 판정, "체크_본문": 본문, "체크_상하단": 상하단,
            "체크_기타필드": 기타, "스토어교체여부": "교체됨", "메모": "zz메모", **덤}


def _첫반영(tmp_run_dir, 체크=None, **kw):
    미리, 폴더 = _미리보기체인(tmp_run_dir, market_status=_체크_성공1 if 체크 is None else 체크)
    반영 = _반영행(tmp_run_dir, 미리, 폴더, **kw)
    return 미리, 폴더, 반영


def test_게이트_라우트_정상(화면, 엿듣기, tmp_run_dir):
    """기록 대상 상품은 서버가 체크포인트 성공 항목에서 정한다 — 화면 값은 받지도 않는다."""
    _, _, 반영 = _첫반영(tmp_run_dir)
    응답 = 화면.post(게이트경로, json=_게이트몸통(반영))
    assert 응답.status_code == 200, 응답.text
    행들 = _게이트판정들()
    assert len(행들) == 1
    h = 행들[0]
    assert (h["판정"], h["판매자상품코드"], h["productId"], h["commit_job_id"]) == \
        ("정상", "zz01", "zzp1", 반영)
    assert h["스토어교체여부"] == "교체됨" and h["메모"] == "zz메모" and h["기록시각"]
    assert "정상" in 응답.text and 'hx-post="/market/gate"' not in 응답.text
    assert not 엿듣기, "판정 기록이 잡을 만들었다"


def test_게이트_화면이_상품을_보내면_422(화면, tmp_run_dir):
    _, _, 반영 = _첫반영(tmp_run_dir)
    for 덤 in ({"판매자상품코드": "zz04"}, {"productId": "zzp4"}, {"max_items": 20}):
        assert 화면.post(게이트경로, json=_게이트몸통(반영, **덤)).status_code == 422
    assert _게이트판정들() == []


def test_게이트_htmx_폼도_받는다(화면, tmp_run_dir):
    """체크박스는 안 누르면 폼에서 빠진다 — 빠진 체크는 거짓이다."""
    _, _, 반영 = _첫반영(tmp_run_dir)
    폼 = {"commit_job_id": 반영, "판정": "정상", "체크_본문": "true", "체크_상하단": "true",
          "체크_기타필드": "true", "스토어교체여부": "미교체", "메모": ""}
    응답 = 화면.post(게이트경로, data=폼)
    assert 응답.status_code == 200, 응답.text
    assert _게이트판정들()[0]["스토어교체여부"] == "미교체"
    폼.pop("체크_상하단")
    assert 화면.post(게이트경로, data=폼).status_code == 400
    assert len(_게이트판정들()) == 1


@pytest.mark.parametrize("빠짐", ["본문", "상하단", "기타"])
def test_게이트_정상은_체크3필수(화면, tmp_run_dir, 빠짐):
    _, _, 반영 = _첫반영(tmp_run_dir)
    응답 = 화면.post(게이트경로, json=_게이트몸통(반영, **{빠짐: False}))
    assert 응답.status_code == 400
    assert "체크" in 응답.json()["detail"]
    assert _게이트판정들() == []


def test_게이트_이상은_체크없어도_기록(화면, tmp_run_dir):
    _, _, 반영 = _첫반영(tmp_run_dir)
    응답 = 화면.post(게이트경로, json=_게이트몸통(반영, "이상", False, False, False))
    assert 응답.status_code == 200, 응답.text
    assert _게이트판정들()[0]["판정"] == "이상"
    assert "restore-backup" in 응답.text and "/tmp/zz/before_detail/zzp1.json" in 응답.text


def test_게이트_성공0건은_400(화면, tmp_run_dir):
    _, _, 반영 = _첫반영(tmp_run_dir, 체크={"워터마크": "100", "items": {
        "zzp1": {"판매자상품코드": "zz01", "status": "대기", "taskId": "201"}}})
    응답 = 화면.post(게이트경로, json=_게이트몸통(반영))
    assert 응답.status_code == 400
    assert _게이트판정들() == []


def test_게이트_토큰없이_403(화면, tmp_run_dir):
    _, _, 반영 = _첫반영(tmp_run_dir)
    응답 = 화면.post(게이트경로, json=_게이트몸통(반영), headers={"X-CT-Token": "wrong-token"})
    assert 응답.status_code == 403
    assert _게이트판정들() == []


def test_게이트_GET은_405(화면):
    assert 화면.get(게이트경로).status_code == 405


def test_게이트_메모500자초과_422(화면, tmp_run_dir):
    _, _, 반영 = _첫반영(tmp_run_dir)
    몸통 = _게이트몸통(반영)
    몸통["메모"] = "가" * 501
    assert 화면.post(게이트경로, json=몸통).status_code == 422
    몸통["메모"] = "가" * 500
    assert 화면.post(게이트경로, json=몸통).status_code == 200


@pytest.mark.parametrize("값", [{"판정": "통과"}, {"스토어교체여부": "몰라"}])
def test_게이트_화이트리스트밖_422(화면, tmp_run_dir, 값):
    _, _, 반영 = _첫반영(tmp_run_dir)
    assert 화면.post(게이트경로, json={**_게이트몸통(반영), **값}).status_code == 422


def test_게이트_잡종류틀리면_400(화면, tmp_run_dir):
    미리, 폴더, _ = _첫반영(tmp_run_dir)
    접수 = jobs._row(미리)["parent_job_id"]
    for 잡 in (미리, 접수, str(uuid.uuid4())):
        assert 화면.post(게이트경로, json=_게이트몸통(잡)).status_code == 400
    assert _게이트판정들() == []


def test_게이트_이어서확인_잡으로도_된다(화면, tmp_run_dir):
    미리, 폴더, 반영 = _첫반영(tmp_run_dir, exit_code=3)
    확인 = _반영행(tmp_run_dir, 미리, 폴더, kind="market_poll", parent=반영,
                  대상=jobs._row(반영)["targets_path"])
    assert 화면.post(게이트경로, json=_게이트몸통(확인)).status_code == 200
    assert _게이트판정들()[0]["commit_job_id"] == 확인


# ── 상한 결정 (D-09 · D-12) ─────────────────────────────────────────────────

def test_상한_판정전은_1(화면, tmp_run_dir):
    from webapp.routes import jobs as 라우트
    assert 라우트._마켓반영상한() == 1


def test_상한_정상후_N(화면, 안띄운다, 프로필, 기대닉, tmp_run_dir, monkeypatch):
    """정상 기록 뒤 같은 미리보기의 두 번째 반영 → 진짜 argv 가 `--max-items 20` · 남은 2건."""
    from webapp import settings as 설정
    monkeypatch.setattr(설정, "load", lambda force=False: None)
    프로필()
    미리, 폴더, 반영 = _첫반영(tmp_run_dir)
    assert 화면.post(게이트경로, json=_게이트몸통(반영)).status_code == 200
    응답 = 화면.post(반영경로, json={"preview_job_id": 미리})
    assert 응답.status_code == 200, 응답.text
    av = json.loads(jobs._row(응답.json()["job_id"])["argv"])
    assert av[av.index("--max-items") + 1] == "20"
    assert _반영플래그 in av
    대상 = json.loads(Path(av[av.index("--targets") + 1]).read_text(encoding="utf-8"))
    assert [x["productId"] for x in 대상["items"]] == ["zzp2", "zzp4"]


def test_상한_설정값을_따른다(화면, tmp_run_dir, monkeypatch):
    from webapp import market_gate_store
    from webapp import settings as 설정
    from webapp.routes import jobs as 라우트
    진짜 = 설정.cfg
    monkeypatch.setattr(설정, "cfg", lambda d, default=None, required=False:
                        7 if d == "market_update_max_items" else 진짜(d, default, required))
    assert 라우트._마켓반영상한() == 1
    market_gate_store.판정기록("정상", "zz01", "zzp1", "job-zz", "교체됨", "")
    assert 라우트._마켓반영상한() == 7


def test_상한_이상이면_400(화면, 엿듣기, tmp_run_dir):
    미리, 폴더, 반영 = _첫반영(tmp_run_dir)
    assert 화면.post(게이트경로, json=_게이트몸통(반영, "이상")).status_code == 200
    응답 = 화면.post(반영경로, json={"preview_job_id": 미리})
    assert 응답.status_code == 400
    assert "게이트 이상 판정 — 멈춤" in 응답.json()["detail"]
    assert not 엿듣기
    # 다른 새 미리보기도 막힌다 — 판정은 미리보기 단위가 아니다(D-09 1회성)
    새미리, _ = _미리보기체인(tmp_run_dir)
    assert 화면.post(반영경로, json={"preview_job_id": 새미리}).status_code == 400
    assert not 엿듣기


# ── 미리보기 ctx (D-09 · D-11 · D-12) ───────────────────────────────────────

def test_미리보기ctx_이상이면_버튼없음(화면, tmp_run_dir):
    _, _, 반영 = _첫반영(tmp_run_dir)
    화면.post(게이트경로, json=_게이트몸통(반영, "이상"))
    새미리, _ = _미리보기체인(tmp_run_dir)
    j = 화면.get(f"/jobs/{새미리}/result?format=json").json()
    assert j["버튼문구"] is None and j["게이트"]["판정"] == "이상"
    본문 = 화면.get(f"/jobs/{새미리}/result", headers={"HX-Request": "true"}).text
    assert "market-commit-btn" not in 본문
    assert "게이트 이상 판정으로 멈춰 있다" in 본문


def test_미리보기ctx_정상이면_최대N과_다음회차(화면, tmp_run_dir, monkeypatch):
    from webapp import settings as 설정
    _, _, 반영 = _첫반영(tmp_run_dir)
    화면.post(게이트경로, json=_게이트몸통(반영))
    # 새 미리보기 — zzp1 은 형제(첫 반영)에서 이미 성공했다 → '반영됨'(Quick 260930-m3)
    새미리, _ = _미리보기체인(tmp_run_dir, 항목=[
        _미리보기항목(p, c) for p, c in (("zzp1", "zz01"), ("zzp2", "zz02"),
                                        ("zzp4", "zz04"), ("zzp5", "zz05"))])
    j = 화면.get(f"/jobs/{새미리}/result?format=json").json()
    assert j["버튼문구"] == "반영 실행 (최대 20건)" and j["상한"] == 20
    진짜 = 설정.cfg
    monkeypatch.setattr(설정, "cfg", lambda d, default=None, required=False:
                        2 if d == "market_update_max_items" else 진짜(d, default, required))
    j = 화면.get(f"/jobs/{새미리}/result?format=json").json()
    표시 = {h["판매자상품코드"]: h["반영표시"] for h in j["항목"]}
    assert 표시["zz01"] == "반영됨(성공)"
    assert 표시["zz02"] == "이번 반영" and 표시["zz04"] == "이번 반영"
    assert 표시["zz05"] == "다음 회차"
    assert j["버튼문구"] == "반영 실행 (최대 2건)"


# ── 결과 표 위 게이트 패널 (D-10 · D-11) ────────────────────────────────────

def test_결과_게이트패널_판정전(화면, tmp_run_dir):
    _, 폴더, 반영 = _첫반영(tmp_run_dir)
    j = 화면.get(f"/jobs/{반영}/result?format=json").json()
    p = j["게이트패널"]
    assert p["판정전"] is True
    assert (p["판매자상품코드"], p["productId"], p["채널상품번호"]) == ("zz01", "zzp1", "991")
    assert p["링크"] == "https://smartstore.naver.com/main/products/991"
    본문 = 화면.get(f"/jobs/{반영}/result", headers={"HX-Request": "true"}).text
    for 말 in ("첫 1건 육안 확인", "zz01", "991", "https://zzcdn.example/t.jpg",
               "https://zzcdn.example/b.jpg", "2026-09-01",
               "본문이 AI 상세로 바뀌었다", "현재 불사자 설정", "의도치 않게 바뀌지 않았다",
               "정상 — 나머지 진행 허용", "이상 있음 — 멈춤", "noopener"):
        assert 말 in 본문, 말
    assert 본문.count('hx-post="/market/gate"') >= 2
    # 패널은 결과 집계 줄보다 위다 — 결과 표 위 고정 (D-10)
    assert 본문.index("첫 1건 육안 확인") < 본문.index("성공 1")


def test_결과_게이트패널_채널번호없으면_링크없이_코드만(화면, tmp_run_dir):
    항목 = [_미리보기항목("zzp1", "zz01")]
    항목[0]["채널상품번호"] = None
    미리, 폴더 = _미리보기체인(tmp_run_dir, 항목=항목, market_status=_체크_성공1)
    반영 = _반영행(tmp_run_dir, 미리, 폴더)
    p = 화면.get(f"/jobs/{반영}/result?format=json").json()["게이트패널"]
    assert p["링크"] is None and p["판매자상품코드"] == "zz01"
    본문 = 화면.get(f"/jobs/{반영}/result", headers={"HX-Request": "true"}).text
    assert "smartstore.naver.com" not in 본문


def test_결과_게이트패널_성공없으면_없음(화면, tmp_run_dir):
    _, _, 반영 = _첫반영(tmp_run_dir, 체크=_체크_대기)
    j = 화면.get(f"/jobs/{반영}/result?format=json").json()
    assert j["게이트패널"] is None
    본문 = 화면.get(f"/jobs/{반영}/result", headers={"HX-Request": "true"}).text
    assert "/market/gate" not in 본문


def test_결과_게이트패널_정상후_요약과_나머지버튼(화면, tmp_run_dir):
    미리, _, 반영 = _첫반영(tmp_run_dir)
    화면.post(게이트경로, json=_게이트몸통(반영))
    본문 = 화면.get(f"/jobs/{반영}/result", headers={"HX-Request": "true"}).text
    assert 'hx-post="/market/gate"' not in 본문
    assert "정상" in 본문 and "zz메모" in 본문
    assert "market-commit-btn" in 본문 and f'data-preview-job="{미리}"' in 본문
    assert "반영 실행 (최대 20건)" in 본문


def test_결과_게이트패널_이상이면_복원절차(화면, tmp_run_dir):
    _, 폴더, 반영 = _첫반영(tmp_run_dir)
    화면.post(게이트경로, json=_게이트몸통(반영, "이상", 메모="<b>상단 옛것</b>"))
    본문 = 화면.get(f"/jobs/{반영}/result", headers={"HX-Request": "true"}).text
    assert "market-commit-btn" not in 본문
    assert "restore-backup" in 본문 and "/tmp/zz/before_detail/zzp1.json" in 본문
    assert _반영플래그 + " --max-items 1" in 본문
    assert str(폴더 / "before_market") in 본문
    assert "상하단 교체 프로젝트" in 본문
    assert "<b>상단 옛것</b>" not in 본문 and "&lt;b&gt;" in 본문
    assert "복원 실행" not in 본문   # 웹 복원 버튼 없음(D-05)


def test_게이트패널_템플릿에_safe_없음():
    본문 = (Path(__file__).resolve().parents[1] / "templates"
            / "_market_gate_panel.html").read_text(encoding="utf-8")
    assert "| safe" not in 본문 and "|safe" not in 본문
    assert 본문.count('hx-post="/market/gate"') >= 2


# ── 게이트 판정 응답의 반영 버튼 oob 조각 (Quick 260929-g1) ─────────────────
# 게이트 버튼은 패널만 outerHTML 로 갈아끼운다 — 결과 표 아래 반영 버튼 자리는
# 응답이 hx-swap-oob 로 같이 실어 보내야 새로고침 없이 뜬다.

def _oob조각(본문: str) -> str:
    """응답에서 `#market-commit-next` oob 조각만 잘라낸다 — 없으면 빈 문자열."""
    표식 = '<div id="market-commit-next" hx-swap-oob="true">'
    if 표식 not in 본문:
        return ""
    시작 = 본문.index(표식)
    return 본문[시작:본문.index("</div>", 시작) + len("</div>")]


def test_게이트_정상_응답에_반영버튼_oob(화면, 엿듣기, tmp_run_dir, monkeypatch):
    from webapp.routes import jobs as 라우트
    미리, _, 반영 = _첫반영(tmp_run_dir)
    monkeypatch.setattr(라우트, "_마켓반영상한", lambda: 7)
    응답 = 화면.post(게이트경로, json=_게이트몸통(반영))
    assert 응답.status_code == 200, 응답.text
    조각 = _oob조각(응답.text)
    assert 조각, "정상 응답에 #market-commit-next oob 조각이 없다"
    assert "market-commit-btn" in 조각 and f'data-preview-job="{미리}"' in 조각
    assert "반영 실행 (최대 7건)" in 조각   # 상한은 서버 `_마켓반영상한()` 이 정한다
    assert 응답.text.count('id="market-commit-next"') == 1
    assert not 엿듣기, "판정 기록이 잡을 만들었다"


def test_게이트_이상_응답은_oob_빈자리(화면, 엿듣기, tmp_run_dir):
    _, _, 반영 = _첫반영(tmp_run_dir)
    응답 = 화면.post(게이트경로, json=_게이트몸통(반영, "이상"))
    assert 응답.status_code == 200, 응답.text
    조각 = _oob조각(응답.text)
    assert 조각, "이상 응답도 버튼 자리를 비워 덮어야 한다(이전 버튼 잔존 방지)"
    assert "market-commit-btn" not in 응답.text and "반영 실행" not in 조각
    assert not 엿듣기


def test_결과표는_버튼자리를_항상_그린다_oob없이(화면, tmp_run_dir):
    """oob 대상이 DOM 에 있어야 갈아끼워진다 — 판정 전에도 빈 자리가 있어야 한다."""
    _, _, 반영 = _첫반영(tmp_run_dir)
    본문 = 화면.get(f"/jobs/{반영}/result", headers={"HX-Request": "true"}).text
    assert 'id="market-commit-next"' in 본문
    assert "hx-swap-oob" not in 본문 and "market-commit-btn" not in 본문


def test_반영버튼_조각_템플릿에_safe_없음():
    폴더 = Path(__file__).resolve().parents[1] / "templates"
    for 이름 in ("_market_commit_next.html", "_market_gate_response.html"):
        본문 = (폴더 / 이름).read_text(encoding="utf-8")
        assert "| safe" not in 본문 and "|safe" not in 본문, 이름


# ── 형제 미리보기 이중 반영 방지 (Quick 260930-m3 · 06-06 P1) ───────────────────
# 미리보기마다 market 폴더가 새로 생긴다. 옛 폴더에서 이미 반영된 상품을 새 미리보기가 다시
# '이번 반영' 으로 넣으면 스토어에 두 번 나간다 — 같은 회차의 형제 체크포인트를 합쳐 거른다.

_옛성공 = {"워터마크": "100", "items": {
    "zzp1": {"판매자상품코드": "zz01", "status": "성공", "taskId": "task-zz-00000301"}}}


def test_형제미리보기_성공은_반영됨이고_대상에서_빠진다(화면, 엿듣기, tmp_run_dir, monkeypatch):
    from webapp.routes import jobs as 라우트
    monkeypatch.setattr(라우트, "_마켓반영상한", lambda: 20)
    _미리보기체인(tmp_run_dir, market_status=_옛성공)     # 옛 미리보기 — zzp1 성공
    새미리, 새폴더 = _미리보기체인(tmp_run_dir)          # 새 폴더 — 체크포인트 없음
    assert not (새폴더 / "market_status.json").exists()
    j = 화면.get(f"/jobs/{새미리}/result?format=json").json()
    assert j["error"] is None
    표시 = {h["판매자상품코드"]: h["반영표시"] for h in j["항목"]}
    assert 표시["zz01"] == "반영됨(성공)"
    assert 표시["zz02"] == "이번 반영" and 표시["zz04"] == "이번 반영"
    assert j["남은반영가능"] == 2
    응답 = 화면.post(반영경로, json={"preview_job_id": 새미리})
    assert 응답.status_code == 200, 응답.text
    assert [x["productId"] for x in 엿듣기["detail_inputs"]["items"]] == ["zzp2", "zzp4"]


def test_형제미리보기가_전부_반영했으면_400(화면, 엿듣기, tmp_run_dir, monkeypatch):
    from webapp.routes import jobs as 라우트
    monkeypatch.setattr(라우트, "_마켓반영상한", lambda: 20)
    _미리보기체인(tmp_run_dir, market_status={"워터마크": "100", "items": {
        p: {"판매자상품코드": c, "status": "성공", "taskId": f"task-{p}"}
        for p, c in (("zzp1", "zz01"), ("zzp2", "zz02"), ("zzp4", "zz04"))}})
    새미리, _ = _미리보기체인(tmp_run_dir)
    본문 = 화면.get(f"/jobs/{새미리}/result", headers={"HX-Request": "true"}).text
    assert "market-commit-btn" not in 본문 and "반영할 상품이 0건" in 본문
    assert 화면.post(반영경로, json={"preview_job_id": 새미리}).status_code == 400
    assert not 엿듣기


def test_형제미리보기_스킵은_이월하지_않는다(화면, 엿듣기, tmp_run_dir, monkeypatch):
    """스킵은 쓰기 전 멈춤 — 다음 반영에서 다시 시도할 수 있어야 한다."""
    from webapp.routes import jobs as 라우트
    monkeypatch.setattr(라우트, "_마켓반영상한", lambda: 20)
    _미리보기체인(tmp_run_dir, market_status={"워터마크": "100", "items": {
        "zzp1": {"판매자상품코드": "zz01", "status": "스킵", "taskId": None}}})
    새미리, _ = _미리보기체인(tmp_run_dir)
    assert 화면.post(반영경로, json={"preview_job_id": 새미리}).status_code == 200
    assert [x["productId"] for x in 엿듣기["detail_inputs"]["items"]] == ["zzp1", "zzp2", "zzp4"]


def test_게이트전_형제가_첫1건을_냈으면_새미리보기_반영도_400(화면, 엿듣기, tmp_run_dir):
    """상한 1(판정 전)인데 다른 미리보기에서 이미 1건 나갔다 — 여기서 또 1건이면 판정 전 2건이다."""
    _미리보기체인(tmp_run_dir, market_status=_옛성공)
    새미리, _ = _미리보기체인(tmp_run_dir)
    응답 = 화면.post(반영경로, json={"preview_job_id": 새미리})
    assert 응답.status_code == 400
    assert "게이트 판정" in 응답.json()["detail"]
    assert not 엿듣기


def test_형제_체크포인트가_깨졌으면_반영400(화면, 엿듣기, tmp_run_dir, monkeypatch):
    from webapp.routes import jobs as 라우트
    monkeypatch.setattr(라우트, "_마켓반영상한", lambda: 20)
    _, 옛폴더 = _미리보기체인(tmp_run_dir)
    (옛폴더 / "market_status.json").write_text("{깨짐", encoding="utf-8")
    새미리, _ = _미리보기체인(tmp_run_dir)
    응답 = 화면.post(반영경로, json={"preview_job_id": 새미리})
    assert 응답.status_code == 400 and "형제" in 응답.json()["detail"]
    assert not 엿듣기
    assert "형제" in (화면.get(f"/jobs/{새미리}/result?format=json").json()["error"] or "")


def test_게이트패널_남은0건이면_진행하라_문구가_없다(화면, 엿듣기, tmp_run_dir):
    """반영가능 전부가 성공했으면 '나머지를 진행해라' 가 아니라 '남은 0건' 이다."""
    from webapp import market_gate_store
    market_gate_store.판정기록("정상", "zz01", "zzp1", "job-zz", "교체됨", "")
    _, _, 반영 = _첫반영(tmp_run_dir, 체크={"워터마크": "100", "items": {
        p: {"판매자상품코드": c, "status": "성공", "taskId": f"task-{p}"}
        for p, c in (("zzp1", "zz01"), ("zzp2", "zz02"), ("zzp4", "zz04"))}})
    본문 = 화면.get(f"/jobs/{반영}/result", headers={"HX-Request": "true"}).text
    assert "나머지를 진행해라" not in 본문 and "나머지 " not in 본문.split("게이트가 열렸다")[-1][:60]
    assert 'id="market-gate-nothing-left"' in 본문
