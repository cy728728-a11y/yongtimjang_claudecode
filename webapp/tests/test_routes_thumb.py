#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""썸네일 트랙 라우트(`/jobs/thumb/*` · `/thumb/{id}/result`) 검증 — Phase 7 / 07-04.

**실제 CLI 는 한 번도 안 뜬다**(`안띄운다` · `엿듣기`). 크레딧 0 · 불사자 접속 0.

보는 것:
  · 견적 대상은 서버가 보드 키로 다시 만든다 — ② 아님·조인 미해소·그룹명 미특정·상한초과는
    사유와 함께 빠진다(THUMB-01 · D-02 · L-06). inputs 의 그룹은 조인 문서의 **전체 그룹명**
  · 견적 표 숫자는 러너 summary.json 값 그대로다 — 웹앱이 곱하지 않는다(L-02)
  · 승인은 잡이 아니다 — 그룹별 web_approval.json 을 쓰고 인계 명령만 보인다(D-06 · D-07)
  · 결과 표는 판매자상품코드 단위, taskId 남은 건은 회수 대기 + recover 명령 텍스트(L-03)

과거 run-dir 픽스처(`fixtures/thumb_run/zz그룹`)는 실측 generated.json·decisions.json 필드
모양을 따르되 값은 전부 `zz*` 로 익명화했다.
"""
import json
import shutil
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

import pytest

from webapp import jobs, settings
from webapp.tests.test_routes_jobs import (_회차판정_갈아끼우기, 기대닉, 안띄운다,  # noqa: F401
                                           엿듣기, 프로필, 화면)

견적경로 = "/jobs/thumb/estimate"
승인경로 = "/jobs/thumb/approve"
픽스처 = Path(__file__).resolve().parent / "fixtures" / "thumb_run" / "zz그룹"

그룹명 = "3번_zz가짜그룹_15-2"          # 앞의 `3번_` 은 번호가 아니다 — 진짜 번호는 15-2
모호그룹 = ("zz모호A_9-9", "zz모호B_9-9")  # 같은 번호 그룹 둘 → 그룹명 미특정


# ── 도우미 ──────────────────────────────────────────────────────────────────

def _지금() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _썸네일판정() -> dict:
    """zz01 계정: ② 1~4(노출 500·300·200·100) · ③만 5 · ② 번호없음 6 · ② 모호번호 7."""
    규칙2 = [{"adId": f"nad-zz{i}", "mallProductId": f"1999999999{i}",
          "adGroup": "판매상품_15-2_zzfake", "imp": imp, "clk": 1}
         for i, imp in ((1, 500), (2, 300), (3, 200), (4, 100))]
    규칙2 += [{"adId": "nad-zz6", "mallProductId": "19999999996", "adGroup": "판매상품_zz번호없음",
           "imp": 900, "clk": 1},
          {"adId": "nad-zz7", "mallProductId": "19999999997", "adGroup": "판매상품_9-9_zz",
           "imp": 800, "clk": 1}]
    규칙3 = [{"adId": "nad-zz5", "mallProductId": "19999999995", "adGroup": "판매상품_15-2_zzfake",
          "imp": 1000, "clk": 50}]
    return {"accounts": {"zz01": {"rules": {"②썸네일교체": 규칙2, "③원인분석": 규칙3}}}}


def _조인행(i: int) -> dict:
    return {"acct": "zz01", "mallProductId": f"1999999999{i}", "productId": f"zzp{i}",
            "인덱스_smartstore": "s", "관측_smartstore": "s", "미조회": False,
            "uploadDetailContents": None, "그룹태그": [], "판매자상품코드": f"zz0{i}",
            "불사자코드": f"zzb{i}", "타오바오상품번호": f"zzt{i}", "사본": [],
            "팬아웃미조회": False}


def _썸네일조인() -> dict:
    return {"마켓그룹": [{"groupId": "zzg1", "그룹명": 그룹명},
                        {"groupId": "zzg9a", "그룹명": 모호그룹[0]},
                        {"groupId": "zzg9b", "그룹명": 모호그룹[1]}],
            "행": [_조인행(i) for i in (1, 2, 3, 4, 5, 7)]}


@pytest.fixture
def 썸네일판(tmp_run_dir, monkeypatch, 프로필, 기대닉):
    _회차판정_갈아끼우기(tmp_run_dir, _썸네일판정())
    웹 = tmp_run_dir / "web"
    웹.mkdir(parents=True, exist_ok=True)
    조인 = 웹 / "join_zzprev.json"
    조인.write_text(json.dumps(_썸네일조인(), ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(jobs, "latest_done", lambda kind, run_dir=None: (
        {"result_path": str(조인)} if kind == "bulsaja_scan" else None))
    프로필()
    return {"run_dir": tmp_run_dir.name, "조인": 조인,
            "키": [f"zz01|1999999999{i}" for i in range(1, 8)]}


def _상한(monkeypatch, n: int):
    진짜 = settings.cfg

    def 가짜(dotted, default=None, required=False):
        if dotted == "thumb_max_items":
            return n
        if dotted == "expected_bulsaja_nick":
            return "zz기대닉"
        return 진짜(dotted, default, required)
    monkeypatch.setattr(settings, "cfg", 가짜)


def _요약(폴더: Path, *, K=3, 예상=17, 최대=31, 오류=None, 대상=None) -> dict:
    """러너 summary.json 모양(07-02 계약). 예상·최대는 **일부러 K×5 가 아닌 값**이다 —
    화면이 곱하면 테스트가 잡는다."""
    대상 = ["zzp1", "zzp2", "zzp3"][:K] if 대상 is None else 대상
    그룹 = {"그룹명": 그룹명, "run_dir": str(폴더 / "zzgroup"), "선택": 대상 + ["zzp8", "zzp9"],
            "시트id": "zz-sheet-1", "대상": 대상, "이미가공": {"zzp8": "완료"},
            "정합검사": ["zzp8"], "삭제대상": {}, "조회실패": {"zzp9": "zz조회실패"},
            "현황판제외": {}, "예상크레딧": 예상, "최대크레딧": 최대, "오류": 오류}
    return {"계정": "zz기대닉", "코드": {f"zzp{i}": f"zz0{i}" for i in range(1, 10)},
            "그룹": [그룹],
            "합계": {"선택": len(그룹["선택"]), "K": len(대상), "M": 1, "A": 1, "D": 0, "E": 1,
                    "현황판제외": 0, "예상크레딧": 예상, "최대크레딧": 최대}}


def _견적잡(tmp_run_dir, *, 상태="done", exit_code=0, 요약=None, 요약쓰기=True,
           inputs=None) -> str:
    """thumb_estimate 행 + 러너 폴더(thumb_dir_of) + summary.json 을 깐다."""
    job_id = str(uuid.uuid4())
    폴더 = jobs.thumb_dir_of(job_id)
    (폴더 / "zzgroup").mkdir(parents=True, exist_ok=True)
    입력 = 폴더 / "inputs.json"
    입력.write_text(json.dumps(inputs or {
        "그룹": {그룹명: ["zzp1", "zzp2", "zzp3"]}, "코드": {"zzp1": "zz01"},
        "웹제외": {"zz01|19999999995": {"판매자상품코드": "zz05", "사유": "규칙② 아님"}},
        "선택": 4}, ensure_ascii=False), encoding="utf-8")
    결과 = 폴더 / "summary.json"
    if 요약쓰기:
        결과.write_text(json.dumps(_요약(폴더) if 요약 is None else 요약(폴더),
                                  ensure_ascii=False), encoding="utf-8")
    cx = sqlite3.connect(jobs.db_path())
    try:
        cx.execute("INSERT INTO jobs (id, kind, run_dir, accounts, argv, status, log_path, "
                   "targets_path, result_path, exit_code, started_at) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                   (job_id, "thumb_estimate", tmp_run_dir.name, "[]", "[]", 상태,
                    str(tmp_run_dir / "x.log"), str(입력), str(결과),
                    exit_code if 상태 not in jobs.LIVE_STATUSES else None, _지금()))
        cx.commit()
    finally:
        cx.close()
    return job_id


# ── 견적 접수 ────────────────────────────────────────────────────────────────

def test_견적_GET이_아니다(화면):
    assert 화면.get(견적경로).status_code == 405


def test_견적_토큰없이_안된다(화면, 엿듣기):
    응답 = 화면.post(견적경로, json={"run_dir": "x", "keys": ["zz01|1"]},
                    headers={"X-CT-Token": "wrong-token"})
    assert 응답.status_code == 403
    assert not 엿듣기


def test_견적_모르는필드는_422(화면, 엿듣기, 썸네일판):
    응답 = 화면.post(견적경로, json={"run_dir": 썸네일판["run_dir"], "keys": 썸네일판["키"],
                                   "그룹": {"zz": ["x"]}})
    assert 응답.status_code == 422
    assert not 엿듣기


def test_견적_모르는키는_400(화면, 엿듣기, 썸네일판):
    응답 = 화면.post(견적경로, json={"run_dir": 썸네일판["run_dir"],
                                   "keys": ["zz01|19999999991", "zz01|18888888888"]})
    assert 응답.status_code == 400
    assert "18888888888" in 응답.json()["detail"]
    assert not 엿듣기


def test_견적_대상은_서버가_거른다(화면, 안띄운다, 썸네일판, monkeypatch):
    """② 1~4 통과 · ③만 5 · 번호없음 6 · 모호번호 7 → 사유와 함께 제외. 그룹은 전체 이름."""
    본것 = {}
    진짜 = jobs.create_job

    def 엿보기(kind, **kw):
        본것.update({"kind": kind, **kw})
        return 진짜(kind, **kw)
    monkeypatch.setattr(jobs, "create_job", 엿보기)

    응답 = 화면.post(견적경로, json={"run_dir": 썸네일판["run_dir"], "keys": 썸네일판["키"]})
    assert 응답.status_code == 200, 응답.text
    assert 본것["kind"] == "thumb_estimate"
    입력 = 본것["thumb_inputs"]
    assert 입력["그룹"] == {그룹명: ["zzp1", "zzp2", "zzp3", "zzp4"]}   # 노출 내림차순
    assert 입력["코드"] == {f"zzp{i}": f"zz0{i}" for i in (1, 2, 3, 4)}
    assert 입력["선택"] == 7
    제외 = {x["판매자상품코드"]: x["사유"] for x in 응답.json()["제외"]}
    assert set(제외) == {"zz05", "zz01|19999999996", "zz07"}
    assert "규칙② 아님" in 제외["zz05"]
    assert "조인 미해소" in 제외["zz01|19999999996"]
    assert "그룹명 미특정" in 제외["zz07"]
    assert set(입력["웹제외"]) == {"zz01|19999999995", "zz01|19999999996", "zz01|19999999997"}
    # 잡 행이 실제로 생겼고 inputs 파일이 러너 폴더에 있다
    job_id = 응답.json()["job_id"]
    assert jobs.job_status(job_id)["kind"] == "thumb_estimate"
    assert (jobs.thumb_dir_of(job_id) / "inputs.json").is_file()


def test_견적_노출상위_상한밖은_상한초과(화면, 엿듣기, 썸네일판, monkeypatch):
    _상한(monkeypatch, 2)
    응답 = 화면.post(견적경로, json={"run_dir": 썸네일판["run_dir"], "keys": 썸네일판["키"]})
    assert 응답.status_code == 200, 응답.text
    assert 엿듣기["thumb_inputs"]["그룹"] == {그룹명: ["zzp1", "zzp2"]}
    제외 = {x["판매자상품코드"]: x["사유"] for x in 응답.json()["제외"]}
    assert "상한초과" in 제외["zz03"] and "상한초과" in 제외["zz04"]


def test_견적_통과0이면_400_잡없음(화면, 엿듣기, 썸네일판):
    키 = ["zz01|19999999995", "zz01|19999999996", "zz01|19999999997"]
    응답 = 화면.post(견적경로, json={"run_dir": 썸네일판["run_dir"], "keys": 키})
    assert 응답.status_code == 400
    사유 = 응답.json()["detail"]
    assert "zz05" in 사유 and "zz07" in 사유
    assert not 엿듣기


def test_견적_계정불일치면_409(화면, 안띄운다, 썸네일판):
    from webapp import bulsaja_index
    bulsaja_index.profile_path().write_text(json.dumps({
        "닉네임": "zz다른계정", "확인시각": _지금()}, ensure_ascii=False), encoding="utf-8")
    응답 = 화면.post(견적경로, json={"run_dir": 썸네일판["run_dir"], "keys": 썸네일판["키"]})
    assert 응답.status_code == 409, 응답.text


def test_견적_같은견적_도는중이면_409(화면, 안띄운다, 썸네일판):
    첫 = 화면.post(견적경로, json={"run_dir": 썸네일판["run_dir"], "keys": 썸네일판["키"]})
    assert 첫.status_code == 200, 첫.text
    둘 = 화면.post(견적경로, json={"run_dir": 썸네일판["run_dir"], "keys": 썸네일판["키"]})
    assert 둘.status_code == 409, 둘.text


def test_견적_조인산출물없으면_409(화면, 엿듣기, 썸네일판, monkeypatch):
    monkeypatch.setattr(jobs, "latest_done", lambda kind, run_dir=None: None)
    응답 = 화면.post(견적경로, json={"run_dir": 썸네일판["run_dir"], "keys": 썸네일판["키"]})
    assert 응답.status_code == 409
    assert not 엿듣기


# ── 견적 표 (GET /jobs/{id}/result) ─────────────────────────────────────────

def test_견적표_도는중(화면, tmp_run_dir):
    job_id = _견적잡(tmp_run_dir, 상태="starting", 요약쓰기=False)   # pid 없는 running 은 _reap 이 거둔다
    ctx = 화면.get(f"/jobs/{job_id}/result?format=json").json()
    assert ctx["running"] is True


def test_견적표_summary없으면_오류와_종료코드(화면, tmp_run_dir):
    job_id = _견적잡(tmp_run_dir, 상태="failed", exit_code=4, 요약쓰기=False)
    ctx = 화면.get(f"/jobs/{job_id}/result?format=json").json()
    assert ctx["error"] and "4" in ctx["error"]


def test_견적표_summary깨지면_오류(화면, tmp_run_dir):
    job_id = _견적잡(tmp_run_dir, 요약쓰기=False)
    jobs.thumb_dir_of(job_id).joinpath("summary.json").write_text("{깨짐", encoding="utf-8")
    ctx = 화면.get(f"/jobs/{job_id}/result?format=json").json()
    assert ctx["error"]


def test_견적표_숫자는_summary_그대로(화면, tmp_run_dir):
    """예상 17 · 최대 31 은 K(3)×5 가 아니다 — 화면이 곱하면 15 · 30 이 나온다."""
    job_id = _견적잡(tmp_run_dir)
    ctx = 화면.get(f"/jobs/{job_id}/result?format=json").json()
    assert ctx["합계"]["예상크레딧"] == 17 and ctx["합계"]["최대크레딧"] == 31
    assert ctx["계정"] == "zz기대닉"
    코드들 = {r["판매자상품코드"] for g in ctx["그룹행"] for r in g["행"]}
    assert {"zz01", "zz02", "zz03", "zz08", "zz09"} <= 코드들
    assert [x["판매자상품코드"] for x in ctx["웹제외"]] == ["zz05"]

    조각 = 화면.get(f"/jobs/{job_id}/result", headers={"HX-Request": "true"}).text
    assert "<strong>17</strong>" in 조각 and "<strong>31</strong>" in 조각
    assert "<strong>15</strong>" not in 조각 and "<strong>30</strong>" not in 조각   # 곱셈 결과가 없다
    assert "실행 승인 — 크레딧 0" in 조각
    assert "zz기대닉" in 조각


def test_견적표_K0이면_승인버튼_disabled(화면, tmp_run_dir):
    job_id = _견적잡(tmp_run_dir, 요약=lambda p: _요약(p, K=0, 예상=0, 최대=0, 대상=[]))
    조각 = 화면.get(f"/jobs/{job_id}/result", headers={"HX-Request": "true"}).text
    assert "생성 대상 0건" in 조각
    assert "disabled" in 조각


# ── 실행 승인 ────────────────────────────────────────────────────────────────

def test_승인_모르는필드는_422(화면, 엿듣기, tmp_run_dir):
    job_id = _견적잡(tmp_run_dir)
    응답 = 화면.post(승인경로, json={"estimate_job_id": job_id, "승인상한크레딧": 9999})
    assert 응답.status_code == 422
    assert not 엿듣기


def test_승인_부모가_견적아니면_400(화면, 엿듣기, tmp_run_dir):
    응답 = 화면.post(승인경로, json={"estimate_job_id": str(uuid.uuid4())})
    assert 응답.status_code == 400


@pytest.mark.parametrize("상태", ["running", "failed"])
def test_승인_부모가_미완이나_실패면_400(화면, 엿듣기, tmp_run_dir, 상태):
    job_id = _견적잡(tmp_run_dir, 상태=상태, exit_code=1)
    응답 = 화면.post(승인경로, json={"estimate_job_id": job_id})
    assert 응답.status_code == 400
    assert not 엿듣기


def test_승인_K0이면_400(화면, 엿듣기, tmp_run_dir):
    job_id = _견적잡(tmp_run_dir, 요약=lambda p: _요약(p, K=0, 예상=0, 최대=0, 대상=[]))
    응답 = 화면.post(승인경로, json={"estimate_job_id": job_id})
    assert 응답.status_code == 400
    assert "생성 대상 0건" in 응답.json()["detail"]


@pytest.mark.parametrize("예상,최대", [(True, 30), (15, -1), (15.5, 30), ("15", 30), (15, None)])
def test_승인_크레딧값이_양의정수가_아니면_400(화면, 엿듣기, tmp_run_dir, 예상, 최대):
    job_id = _견적잡(tmp_run_dir, 요약=lambda p: _요약(p, 예상=예상, 최대=최대))
    응답 = 화면.post(승인경로, json={"estimate_job_id": job_id})
    assert 응답.status_code == 400, 응답.text
    assert not (jobs.thumb_dir_of(job_id) / "zzgroup" / "web_approval.json").exists()


def test_승인_정상이면_승인파일과_인계명령_잡0(화면, 엿듣기, tmp_run_dir):
    job_id = _견적잡(tmp_run_dir)
    응답 = 화면.post(승인경로, json={"estimate_job_id": job_id})
    assert 응답.status_code == 200, 응답.text
    assert not 엿듣기, "승인이 잡을 만들었다 — 승인은 파일 쓰기뿐이다(D-06)"

    그룹폴더 = jobs.thumb_dir_of(job_id) / "zzgroup"
    승인 = json.loads((그룹폴더 / "web_approval.json").read_text(encoding="utf-8"))
    assert 승인["견적잡id"] == job_id
    assert 승인["계정"] == "zz기대닉"
    assert 승인["그룹명"] == 그룹명
    assert 승인["시트id"] == "zz-sheet-1"
    assert 승인["ids"] == ["zzp1", "zzp2", "zzp3"]
    assert 승인["예상크레딧"] == 17
    assert 승인["승인상한크레딧"] == 31          # 상한 = 그룹 최대크레딧(D-07)
    assert 승인["승인시각"]

    명령 = 응답.json()["승인"][0]["명령"]
    assert 명령 == f'썸네일 작업 이어서 "{그룹폴더}"'

    # 두 번째 승인은 거부 — 이미 파일이 있다
    둘 = 화면.post(승인경로, json={"estimate_job_id": job_id})
    assert 둘.status_code == 400
    assert not 엿듣기

    # 승인 뒤 견적 표에는 인계 명령과 결과 보기 버튼
    조각 = 화면.get(f"/jobs/{job_id}/result", headers={"HX-Request": "true"}).text
    assert "썸네일 작업 이어서" in 조각
    assert f'data-thumb-result="{job_id}"' in 조각


def test_승인_그룹폴더가_러너폴더밖이면_400(화면, 엿듣기, tmp_run_dir, tmp_path):
    def 바깥(p):
        s = _요약(p)
        s["그룹"][0]["run_dir"] = str(tmp_path / "밖")
        return s
    job_id = _견적잡(tmp_run_dir, 요약=바깥)
    응답 = 화면.post(승인경로, json={"estimate_job_id": job_id})
    assert 응답.status_code == 400
    assert not (tmp_path / "밖" / "web_approval.json").exists()


def test_인계명령은_한_함수():
    from webapp.routes import thumb
    assert thumb._인계명령("/a/b") == '썸네일 작업 이어서 "/a/b"'


# ── 결과 보기 ────────────────────────────────────────────────────────────────

def _결과판(tmp_run_dir, commit=None) -> str:
    job_id = _견적잡(tmp_run_dir, 요약=lambda p: _요약(
        p, 대상=["zzp1", "zzp2", "zzp3", "zzp4", "zzp5", "zzp6", "zzp7"]))
    그룹폴더 = jobs.thumb_dir_of(job_id) / "zzgroup"
    for f in ("generated.json", "decisions.json"):
        shutil.copyfile(픽스처 / f, 그룹폴더 / f)
    if commit is not None:
        (그룹폴더 / "commit_summary.json").write_text(json.dumps(commit, ensure_ascii=False),
                                                   encoding="utf-8")
    return job_id


def test_결과_상태매핑과_회수대기(화면, tmp_run_dir):
    job_id = _결과판(tmp_run_dir)
    ctx = 화면.get(f"/thumb/{job_id}/result").json()
    행 = {r["판매자상품코드"]: r for r in ctx["행"]}
    assert 행["zz01"]["상태"] == "사용가능"
    assert 행["zz02"]["상태"] == "제외"            # 원본대체 — fallback 종결
    assert 행["zz03"]["상태"] == "제외"            # 제외(글자변조)
    assert 행["zz04"]["상태"] == "생성"            # 생성본은 있고 판정 전
    assert 행["zz05"]["상태"] == "회수대기"
    assert "recover" in 행["zz05"]["명령"] and str(jobs.thumb_dir_of(job_id)) in 행["zz05"]["명령"]
    assert 행["zz06"]["상태"] == "보류"            # 생성 실패(taskId 없음)
    assert 행["zz07"]["상태"] == "생성 전"
    assert 행["zz01"]["크레딧"] == 5
    assert ctx["그룹"][0]["review"]["경로"].endswith("review.html")


def test_결과_commit_summary가_정본(화면, tmp_run_dir):
    job_id = _결과판(tmp_run_dir, commit={"완료": ["zzp1"], "보류": {"zzp4": "보류(저장실패)"},
                                        "기존대표유지": ["zzp3"]})
    ctx = 화면.get(f"/thumb/{job_id}/result").json()
    행 = {r["판매자상품코드"]: r for r in ctx["행"]}
    assert 행["zz01"]["상태"] == "반영완료"
    assert 행["zz04"]["상태"] == "보류" and "저장실패" in 행["zz04"]["사유"]
    assert 행["zz03"]["상태"] == "제외"


def test_결과_조각_재생성버튼없고_스토어반영미연결(화면, tmp_run_dir):
    job_id = _결과판(tmp_run_dir)
    조각 = 화면.get(f"/thumb/{job_id}/result", headers={"HX-Request": "true"}).text
    assert "스토어 반영 미연결" in 조각
    assert "회수 대기" in 조각
    assert "run_thumbs.py recover" in 조각
    assert "<button" not in 조각                   # 결과 표에는 버튼이 하나도 없다


def test_결과_견적잡아니면_404(화면):
    응답 = 화면.get(f"/thumb/{uuid.uuid4()}/result")
    assert 응답.status_code == 404


def test_결과_쿠키없으면_403(client, 화면, tmp_run_dir):
    job_id = _결과판(tmp_run_dir)
    화면.cookies.clear()
    assert 화면.get(f"/thumb/{job_id}/result").status_code == 403
