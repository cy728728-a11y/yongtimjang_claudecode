#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""쿠팡 트랙 라우트(`/jobs/coupang/*` · 결과 조각) 검증 — Phase 7 / 07-05.

**실제 러너는 한 번도 안 뜬다**(`안띄운다` 가 spawn 을 가짜로). 불사자 접속 0 · 쓰기 0.

보는 것:
  · 후보 뽑기 요청은 빈 본문뿐 — 기준 필드를 실어 보내면 422 (L-04 · T-07-26)
  · 복사 요청은 미리보기 잡 id + 타이핑 건수뿐 — 승인목록·상한은 서버가 정한다(D-11 · D-13 · D-16)
  · 건수 불일치 409 · 부모 이상 400 · 재커밋 400 (오케스트레이터 제약 6)
  · 첫 복사 상한 10, 성공 이력 뒤 20 — `--limit` 은 항상 붙는다
  · 후보/결과 조각은 summary 값을 그대로 보인다 — 기준 문구 원문, 중복0 은 파일 값(Pitfall 5)

summary 픽스처는 07-03 러너 계약 모양을 테스트 안에서 dict 로 만든다. 값은 전부 `zz*` 익명.
"""
import json
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from webapp import jobs, settings
from webapp.tests.test_routes_jobs import 기대닉, 안띄운다, 프로필, 화면  # noqa: F401

후보경로 = "/jobs/coupang/preview"
복사경로 = "/jobs/coupang/commit"
# no_commit_guard.sh 가 커밋 플래그 리터럴을 금지한다 — 상한 플래그도 간접 조립으로 통일한다.
_상한플래그 = "--" + "limit"
_금지 = ["--" + x for x in ("skip-group-check", "min-margin", "min-orders", "strict-shipping")]


# ── 도우미 ──────────────────────────────────────────────────────────────────

def _지금(시간전: float = 0) -> str:
    return (datetime.now().astimezone() - timedelta(hours=시간전)).isoformat(timespec="seconds")


def _통과(n: int) -> list[dict]:
    """gate 통과 행 n 개 — candidates.json 모양. 정렬은 이미 gate 가 했다고 본다."""
    return [{"불사자코드": f"zzb{i:02d}", "대표pid": f"zzp{i:02d}", "판매자상품코드": f"zz{i:02d}",
             "상품명": f"zz상품{i:02d}", "합산주문수": 10 - (i % 5), "쿠팡보정마진": 21.5 + i,
             "배송비차액": -300 if i == 0 else 0, "배송비과소": i == 0, "사유": ""}
            for i in range(n)]


def _미리보기요약(n: int = 3, **덮기) -> dict:
    문서 = {"단계": [{"이름": s, "exit": 0} for s in
                     ("prep", "resolve", "build", "ship", "gate", "apply")],
            "정지단계": None,
            "기준": "[gate] 기준: 주문 3회 이상 AND 쿠팡보정마진 20.0% 이상",
            "통과": _통과(n), "탈락사유별": {"주문수부족": 7, "마진미달": 4, "쿠팡그룹에이미있음": 2},
            "이미있음": 2, "그룹읽기": {"총상품수": 87, "읽음": 87, "타오바오결측": 1},
            "apply미리보기": {"대상": n}}
    문서.update(덮기)
    return 문서


def _행박기(kind, *, 상태="done", exit_code=0, parent=None, result=None, 시작=None) -> str:
    job_id = str(uuid.uuid4())
    cx = sqlite3.connect(jobs.db_path())
    try:
        cx.execute("INSERT INTO jobs (id, kind, run_dir, accounts, argv, status, log_path, "
                   "targets_path, result_path, parent_job_id, exit_code, started_at) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                   (job_id, kind, None, "[]", "[]", 상태, "/dev/null", None,
                    str(result) if result else None, parent,
                    exit_code if 상태 not in jobs.LIVE_STATUSES else None, 시작 or _지금()))
        cx.commit()
    finally:
        cx.close()
    return job_id


def _미리보기잡(*, 요약=None, 상태="done", exit_code=0, 시작=None, 요약쓰기=True) -> str:
    """coupang_preview 행 + 러너 폴더(coupang_dir_of)의 summary.json."""
    job_id = str(uuid.uuid4())
    폴더 = jobs.coupang_dir_of(job_id)
    폴더.mkdir(parents=True, exist_ok=True)
    결과 = 폴더 / "summary.json"
    if 요약쓰기:
        결과.write_text(json.dumps(_미리보기요약() if 요약 is None else 요약, ensure_ascii=False),
                       encoding="utf-8")
    cx = sqlite3.connect(jobs.db_path())
    try:
        cx.execute("INSERT INTO jobs (id, kind, run_dir, accounts, argv, status, log_path, "
                   "targets_path, result_path, parent_job_id, exit_code, started_at) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                   (job_id, "coupang_preview", None, "[]", "[]", 상태, "/dev/null", None,
                    str(결과), None, exit_code if 상태 not in jobs.LIVE_STATUSES else None,
                    시작 or _지금()))
        cx.commit()
    finally:
        cx.close()
    return job_id


@pytest.fixture
def 쿠팡판(tmp_run_dir, 화면, 프로필, 기대닉, 안띄운다):
    """tmp data_root(쿠팡 러너 뿌리 포함) + tmp 잡 DB + 계정 일치 + spawn 가짜."""
    프로필()
    return 화면


def _argv(job_id: str) -> list[str]:
    return json.loads(jobs.job_status(job_id)["argv"])


# ── ① 후보 뽑기 ─────────────────────────────────────────────────────────────

def test_후보뽑기는_잡_하나를_띄우고_argv_에_preview(쿠팡판):
    응답 = 쿠팡판.post(후보경로, json={})
    assert 응답.status_code == 200, 응답.text
    job_id = 응답.json()["job_id"]
    상태 = jobs.job_status(job_id)
    assert 상태["kind"] == "coupang_preview"
    av = _argv(job_id)
    assert "preview" in av
    assert not any(f in av for f in _금지)
    assert _상한플래그 not in av, "미리보기에 상한이 붙었다 — 쓰기 경로 인자다"
    assert str(jobs.coupang_dir_of(job_id)) in av


def test_후보뽑기에_기준을_실으면_422(쿠팡판):
    for 몸통 in ({"min_margin": 15}, {"skip_group_check": True}, {"min_orders": 1}):
        응답 = 쿠팡판.post(후보경로, json=몸통)
        assert 응답.status_code == 422, 몸통
    assert not jobs.recent_jobs()


def test_같은_후보뽑기가_도는_중이면_409(쿠팡판):
    _행박기("coupang_preview", 상태="starting")
    응답 = 쿠팡판.post(후보경로, json={})
    assert 응답.status_code == 409, 응답.text


def test_계정이_다르면_409(쿠팡판, 프로필):
    프로필("zz딴계정")
    응답 = 쿠팡판.post(후보경로, json={})
    assert 응답.status_code == 409, 응답.text


# ── ② 복사 — 요청 모양 ──────────────────────────────────────────────────────

def test_복사_요청에_다른_필드가_있으면_422(쿠팡판):
    pid = _미리보기잡()
    for 몸통 in ({"preview_job_id": pid, "typed_count": 3, "limit": 50},
                 {"preview_job_id": pid, "typed_count": 3, "pids": ["zzp00"]},
                 {"preview_job_id": pid, "typed_count": "3"},
                 {"preview_job_id": pid, "typed_count": True},
                 {"preview_job_id": pid, "typed_count": -1},
                 {"preview_job_id": pid},
                 {"preview_job_id": "../../etc", "typed_count": 3}):
        응답 = 쿠팡판.post(복사경로, json=몸통)
        assert 응답.status_code == 422, 몸통
    assert not jobs.children_of(pid, "coupang_commit")


# ── ② 복사 — 부모 검사 ──────────────────────────────────────────────────────

def test_부모가_없거나_종류가_다르면_400(쿠팡판):
    응답 = 쿠팡판.post(복사경로, json={"preview_job_id": str(uuid.uuid4()), "typed_count": 3})
    assert 응답.status_code == 400
    남 = _행박기("market_preview")
    응답 = 쿠팡판.post(복사경로, json={"preview_job_id": 남, "typed_count": 3})
    assert 응답.status_code == 400


def test_부모가_도는_중이면_409(쿠팡판):
    pid = _미리보기잡(상태="starting")
    응답 = 쿠팡판.post(복사경로, json={"preview_job_id": pid, "typed_count": 3})
    assert 응답.status_code == 409, 응답.text


def test_부모가_실패했으면_400(쿠팡판):
    pid = _미리보기잡(상태="failed", exit_code=1)
    응답 = 쿠팡판.post(복사경로, json={"preview_job_id": pid, "typed_count": 3})
    assert 응답.status_code == 400
    assert "새 미리보기" in 응답.json()["detail"]


def test_24시간_넘은_미리보기는_400(쿠팡판):
    pid = _미리보기잡(시작=_지금(25))
    응답 = 쿠팡판.post(복사경로, json={"preview_job_id": pid, "typed_count": 3})
    assert 응답.status_code == 400
    assert "24시간" in 응답.json()["detail"]


def test_같은_미리보기로_성공한_복사가_있으면_400(쿠팡판):
    pid = _미리보기잡()
    _행박기("coupang_commit", parent=pid)
    응답 = 쿠팡판.post(복사경로, json={"preview_job_id": pid, "typed_count": 3})
    assert 응답.status_code == 400
    assert "이미 복사" in 응답.json()["detail"]


def test_요약이_깨졌으면_400(쿠팡판):
    pid = _미리보기잡(요약쓰기=False)
    응답 = 쿠팡판.post(복사경로, json={"preview_job_id": pid, "typed_count": 3})
    assert 응답.status_code == 400


def test_통과_0건이면_400(쿠팡판):
    pid = _미리보기잡(요약=_미리보기요약(0))
    응답 = 쿠팡판.post(복사경로, json={"preview_job_id": pid, "typed_count": 0})
    assert 응답.status_code == 400


# ── ② 복사 — 건수 확인 · 상한 · 승인목록 ────────────────────────────────────

def test_타이핑_건수가_다르면_409_이고_잡을_안_만든다(쿠팡판):
    pid = _미리보기잡()          # 통과 3
    응답 = 쿠팡판.post(복사경로, json={"preview_job_id": pid, "typed_count": 4})
    assert 응답.status_code == 409
    assert "화면이 본 건수" in 응답.json()["detail"]
    assert not jobs.children_of(pid, "coupang_commit")


def test_쓰기잡이_도는_중이면_409(쿠팡판):
    pid = _미리보기잡()
    _행박기("bids_commit", 상태="starting")
    응답 = 쿠팡판.post(복사경로, json={"preview_job_id": pid, "typed_count": 3})
    assert 응답.status_code == 409, 응답.text


def test_첫_복사는_상한_10_승인목록은_통과_상위순(쿠팡판):
    pid = _미리보기잡(요약=_미리보기요약(15))
    응답 = 쿠팡판.post(복사경로, json={"preview_job_id": pid, "typed_count": 10})
    assert 응답.status_code == 200, 응답.text
    본문 = 응답.json()
    assert 본문["건수"] == 10 and 본문["상한"] == 10
    av = _argv(본문["job_id"])
    i = av.index(_상한플래그)
    assert av[i + 1] == "10"
    assert "commit" in av and not any(f in av for f in _금지)
    승인 = json.loads((jobs.coupang_dir_of(pid) / f"approved_{본문['job_id']}.json")
                     .read_text(encoding="utf-8"))
    assert 승인 == [f"zzp{i:02d}" for i in range(10)]


def test_성공_이력이_있으면_상한_20(쿠팡판):
    옛 = _미리보기잡()
    _행박기("coupang_commit", parent=옛)        # 성공(done/0) 이력
    pid = _미리보기잡(요약=_미리보기요약(25))
    응답 = 쿠팡판.post(복사경로, json={"preview_job_id": pid, "typed_count": 20})
    assert 응답.status_code == 200, 응답.text
    assert 응답.json()["상한"] == 20
    av = _argv(응답.json()["job_id"])
    assert av[av.index(_상한플래그) + 1] == "20"


def test_통과가_상한보다_적으면_통과_전부(쿠팡판):
    pid = _미리보기잡()          # 통과 3 < 10
    응답 = 쿠팡판.post(복사경로, json={"preview_job_id": pid, "typed_count": 3})
    assert 응답.status_code == 200, 응답.text
    assert 응답.json()["건수"] == 3


def test_상한과_승인목록은_각각_한_곳에서만():
    from webapp.routes import coupang
    src = Path(coupang.__file__).read_text(encoding="utf-8")
    assert src.count("def _쿠팡복사상한") == 1 and src.count("def _승인목록") == 1
    assert src.count("coupang_first_max_items") >= 1
    # 라우트 파일에 기준 플래그가 없다(L-04)
    assert not any(f in src for f in _금지)


def test_승인목록은_상세완료_필터가_없다():
    from webapp.routes.coupang import _승인목록
    요약 = {"통과": _통과(5) + [{"대표pid": "zzp00"}, "깨진행"]}
    assert _승인목록(요약, 3) == ["zzp00", "zzp01", "zzp02"]
    assert _승인목록(요약, 100) == [f"zzp{i:02d}" for i in range(5)]


# ── 후보 표 ctx ─────────────────────────────────────────────────────────────

def _조각(client, job_id) -> str:
    응답 = client.get(f"/jobs/{job_id}/result", headers={"HX-Request": "true"})
    assert 응답.status_code == 200, 응답.text
    return 응답.text


def test_후보표_ctx_는_summary_값_그대로(쿠팡판):
    from webapp.routes.coupang import _쿠팡미리보기ctx
    요약 = _미리보기요약(12)
    pid = _미리보기잡(요약=요약)
    ctx = _쿠팡미리보기ctx(jobs.job_status(pid))
    assert ctx["기준"] == 요약["기준"]
    assert ctx["이미있음"] == 2
    assert ctx["탈락사유별"]["주문수부족"] == 7
    assert ctx["그룹읽기"] == {"총상품수": 87, "읽음": 87, "타오바오결측": 1}
    assert ctx["상한"] == 10 and ctx["복사예정"] == 10
    행 = ctx["통과"]
    assert len(행) == 12
    assert set(행[0]) >= {"판매자상품코드", "상품명", "합산주문수", "쿠팡보정마진", "배송비차액", "사유"}
    assert 행[0]["쿠팡보정마진"] == 21.5                   # 다시 계산하지 않는다
    assert [r["상한초과"] for r in 행] == [False] * 10 + [True] * 2
    assert not ctx["이미복사"] and not ctx["error"]


def test_후보표_조각_커밋영역은_접혀있고_다른색(쿠팡판):
    pid = _미리보기잡(요약=_미리보기요약(12))
    html = _조각(쿠팡판, pid)
    assert "20.0%" in html
    assert 'id="coupang-commit-details"' in html
    assert "<details id=\"coupang-commit-details\" open" not in html
    assert 'class="contrast"' in html
    assert 'id="coupang-typed-count"' in html
    assert f'data-preview-job="{pid}"' in html
    assert "상한초과" in html
    assert "쿠팡그룹에이미있음" in html


def test_정지단계가_있으면_단계명과_gws_안내(쿠팡판):
    요약 = _미리보기요약(0, 정지단계="prep", 단계=[{"이름": "prep", "exit": 1}])
    pid = _미리보기잡(요약=요약, 상태="failed", exit_code=1)
    from webapp.routes.coupang import _쿠팡미리보기ctx
    ctx = _쿠팡미리보기ctx(jobs.job_status(pid))
    assert ctx["정지단계"] == "prep" and ctx["gws"]
    html = _조각(쿠팡판, pid)
    assert "prep" in html and "gws" in html
    assert 'id="coupang-commit-details"' not in html


def test_orphaned_정지는_요약의_단계코드를_보인다(쿠팡판):
    """실측(2026-09-29): 다른 프로세스가 먼저 거둬 orphaned(exit None) — '종료코드 None' 대신 1."""
    from webapp.routes.coupang import _쿠팡미리보기ctx
    요약 = _미리보기요약(0, 정지단계="prep", 단계=[{"이름": "prep", "exit": 1}])
    pid = _미리보기잡(요약=요약, 상태="orphaned", exit_code=None)
    ctx = _쿠팡미리보기ctx(jobs.job_status(pid))
    assert "종료코드 1" in ctx["error"] and "None" not in ctx["error"]


def test_도는_중이면_읽지_않는다(쿠팡판):
    from webapp.routes.coupang import _쿠팡미리보기ctx
    pid = _미리보기잡(상태="starting", 요약쓰기=False)
    ctx = _쿠팡미리보기ctx(jobs.job_status(pid))
    assert ctx["running"] and not ctx["error"]


def test_산출물이_없으면_오류(쿠팡판):
    from webapp.routes.coupang import _쿠팡미리보기ctx
    pid = _미리보기잡(요약쓰기=False)
    ctx = _쿠팡미리보기ctx(jobs.job_status(pid))
    assert ctx["error"] and not ctx["통과"]


def test_이미_복사한_미리보기는_커밋영역_대신_안내(쿠팡판):
    pid = _미리보기잡()
    _행박기("coupang_commit", parent=pid)
    html = _조각(쿠팡판, pid)
    assert 'id="coupang-commit-details"' not in html
    assert "새 미리보기부터" in html


def test_복사예정_0이면_커밋영역이_없다(쿠팡판):
    pid = _미리보기잡(요약=_미리보기요약(0))
    html = _조각(쿠팡판, pid)
    assert 'id="coupang-commit-details"' not in html


# ── 결과 표 ctx ─────────────────────────────────────────────────────────────

def _복사잡(pid: str, 요약: dict, *, exit_code=0, 상태="done") -> str:
    결과 = jobs.coupang_dir_of(pid) / f"commit_summary_{uuid.uuid4()}.json"
    결과.write_text(json.dumps(요약, ensure_ascii=False), encoding="utf-8")
    return _행박기("coupang_commit", parent=pid, result=결과, exit_code=exit_code, 상태=상태)


def _복사요약(**덮기) -> dict:
    문서 = {"단계": [{"이름": "gate", "exit": 0}, {"이름": "apply", "exit": 0},
                    {"이름": "verify", "exit": 0}],
            "정지단계": None,
            "재조회": {"옛": 3, "새": 2, "빠짐": {"zzp02": "마진미달"}, "늘어남": [],
                      "상한경계": False},
            "복사": [{"원본pid": "zzp00", "판매자상품코드": "zz00", "신pid": "zznew0",
                     "원본판매가": "12,300원", "상품명": "zz상품00"},
                    {"원본pid": "zzp01", "판매자상품코드": "zz01", "신pid": "",
                     "원본판매가": None, "상품명": "zz상품01"}],
            "신pid없음": 1, "중복0": True,
            "verify": {"중복0": True, "중복": {}, "그룹상품수": 89, "판매가검산": 1,
                       "판매가어긋남": 0}}
    문서.update(덮기)
    return 문서


def test_결과표_복사행_신pid없음_빠짐_잠금안내(쿠팡판):
    from webapp.routes.coupang import _쿠팡결과ctx
    pid = _미리보기잡()
    cid = _복사잡(pid, _복사요약())
    ctx = _쿠팡결과ctx(jobs.job_status(cid))
    assert [r["신pid"] for r in ctx["복사"]] == ["zznew0", ""]
    assert ctx["신pid없음"] == 1 and ctx["중복0"] is True
    assert ctx["빠짐"] == [{"판매자상품코드": "zz02", "사유": "마진미달"}]
    assert "잠금" in ctx["잠금안내"]
    html = _조각(쿠팡판, cid)
    assert "신pid 없음" in html and "잠금" in html and "마진미달" in html


def test_결과표_중복0_false_면_경고(쿠팡판):
    pid = _미리보기잡()
    cid = _복사잡(pid, _복사요약(중복0=False, 정지단계="verify"), exit_code=1, 상태="failed")
    html = _조각(쿠팡판, cid)
    assert "중복 발견" in html


def test_결과표_중복0_은_종료코드로_추정하지_않는다(쿠팡판):
    from webapp.routes.coupang import _쿠팡결과ctx
    pid = _미리보기잡()
    cid = _복사잡(pid, _복사요약(중복0=None))       # exit 0 이어도 파일 값이 None 이면 None
    assert _쿠팡결과ctx(jobs.job_status(cid))["중복0"] is None


def test_결과표_exit5_는_재조회_늘어남_복사0(쿠팡판):
    pid = _미리보기잡()
    요약 = _복사요약(정지단계="재조회", 복사=[], 신pid없음=0, 중복0=None, verify=None,
                   재조회={"옛": 3, "새": 4, "빠짐": {}, "늘어남": ["zzp09"], "상한경계": False})
    cid = _복사잡(pid, 요약, exit_code=5, 상태="failed")
    html = _조각(쿠팡판, cid)
    assert "재조회 후보가 늘어 복사 0건" in html
