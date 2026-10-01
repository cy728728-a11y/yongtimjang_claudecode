#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""잡 엔진(`webapp/jobs.py`) 검증 — 합성 잡으로만 돈다. 광고 API 호출 0.

이 파일이 증명하는 것은 "수 분짜리 자식 프로세스"의 네 가지 성질이다:

  · 진행 로그가 **끝나기 전에** 쌓인다            (`PYTHONUNBUFFERED=1` / ENG-03)
  · 부모 프로세스 그룹이 몰살돼도 자식이 산다     (`start_new_session=True` / ENG-02)
  · 작업 생성이 HTTP 를 모른다                    (D-17 / ENG-07)
  · 쓰기 잡이 전역에서 한 번에 하나만 돈다        (Pitfall 3 / T-1-09)

실제 CLI(`run_ads.py`)를 띄우는 테스트는 **하나도 없다.** 대신 `synthetic_job`
픽스처(Plan 01-01)가 주는 대역을 태운다 — 같은 성질(장시간·줄 단위 출력·종료코드)을
2초 안에 재현하면서 네이버 광고 API 에는 한 번도 닿지 않는다.
"""
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from webapp import jobs, settings


# ── 도우미 ──────────────────────────────────────────────────────────────────

def 살아있나(pid: int) -> bool:
    """시그널 0 은 "존재 확인만" 이다 — 프로세스에 아무 영향이 없다."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def 끝날때까지(job_id: str, 초=6.0) -> dict:
    """상태가 running 을 벗어날 때까지 폴링한다. 못 벗어나면 테스트를 세운다."""
    한계 = time.time() + 초
    while time.time() < 한계:
        상태 = jobs.job_status(job_id)
        if 상태 and 상태["status"] != "running":
            return 상태
        time.sleep(0.05)
    pytest.fail(f"{초}초 안에 안 끝났다: {jobs.job_status(job_id)}")


class 가짜프로세스:
    """`spawn` 대역 — 프로세스를 띄우지 않고 '도는 중' 만 흉내 낸다.

    argv 조립·DB 기록·대상 파일 쓰기처럼 **자식을 띄우기 전까지** 의 경로를
    검증할 때 쓴다. 진짜 자식이 필요 없는 테스트가 공연히 2초를 쓰지 않게.
    """

    def __init__(self, argv):
        self.argv = argv
        self.pid = 999_000 + len(argv)

    def poll(self):
        return None


# ── 픽스처 ──────────────────────────────────────────────────────────────────

@pytest.fixture
def 잡판(tmp_path, monkeypatch):
    """잡 DB·로그 디렉터리를 tmp 로 돌린다. 저장소 루트의 webapp.db 를 안 건드린다."""
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.setattr(settings, "JOB_LOG_DIR", str(tmp_path / "logs"))
    jobs.init_db()
    yield tmp_path
    # 테스트가 띄운 자식이 남아 돌지 않게 전부 정리한다. 합성 잡은 몇 초짜리라
    # 그냥 둬도 알아서 죽지만, 남겨 두면 다음 테스트의 쓰기 가드가 엉뚱하게 걸린다.
    for proc in list(jobs._PROCS.values()):
        try:
            proc.kill()
        except Exception:
            pass
    jobs._PROCS.clear()


# ── 테스트 ──────────────────────────────────────────────────────────────────

def test_create_job_은_http_없이_돈다(잡판, synthetic_job):
    """`TestClient` 없이 함수를 직접 부른다 (D-17 / ENG-07).

    v2 의 APScheduler 가 이 함수를 그대로 부른다 — 그때 HTTP 계층이 껴 있으면
    스케줄러가 자기 프로세스에서 자기 서버에 요청을 쏘는 우스운 모양이 된다.
    "HTTP 를 모른다" 는 주장은 **import 가 없다** 로만 증명된다.
    """
    스펙 = synthetic_job(lines=2, delay=0.05)
    job_id = jobs.create_job("synthetic", argv_override=스펙["argv"])

    uuid.UUID(job_id)                       # uuid4 형식이어야 한다
    상태 = jobs.job_status(job_id)
    assert 상태["kind"] == "synthetic"
    assert 상태["pid"] > 0
    assert 상태["status"] in ("running", "done")
    assert Path(상태["log_path"]).parent.is_dir()

    본문 = Path(jobs.__file__).read_text(encoding="utf-8")
    for 금지 in ("fastapi", "starlette", "APIRouter", "HTTPException"):
        assert 금지 not in 본문, f"jobs.py 가 {금지} 를 안다 — HTTP 를 모르게 해라"


def test_자식은_서버_종료를_견딘다(잡판, synthetic_job, tmp_path):
    """부모의 **프로세스 그룹 전체**를 죽여도 자식이 산다 (ENG-02).

    이 테스트는 진짜로 `killpg` 를 쏜다. 다만 pytest 자신의 그룹에 쏘면 러너가
    같이 죽으므로, `fork` 한 '가짜 서버' 가 `setpgid` 로 **자기 그룹을 새로 만든 뒤**
    그 그룹을 몰살한다. 가짜 서버는 죽고, `start_new_session=True` 로 띄운 손자만
    다른 세션에 있어 살아남는다 — `uvicorn --reload` 재시작과 서버 종료가 실제로
    자식에게 하는 일이 이것이다.
    """
    스펙 = synthetic_job(lines=40, delay=0.2)
    pid_파일 = tmp_path / "손자.pid"

    새끼 = os.fork()
    if 새끼 == 0:                                    # ── 가짜 서버 ──
        try:
            os.setpgid(0, 0)                         # 내 그룹을 새로 판다
            proc = jobs.spawn(스펙["argv"], 스펙["log_path"])
            pid_파일.write_text(str(proc.pid), encoding="utf-8")
            os.killpg(os.getpgid(0), signal.SIGKILL)  # 내 그룹 몰살
        except Exception:
            pass
        finally:
            os._exit(0)

    os.waitpid(새끼, 0)                               # 가짜 서버가 죽기를 기다린다
    손자 = int(pid_파일.read_text(encoding="utf-8"))

    try:
        assert 살아있나(손자), "가짜 서버 그룹을 몰살했더니 자식도 같이 죽었다"
        assert os.getpgid(손자) != os.getpgid(0)      # 세션·그룹이 분리돼 있다
    finally:
        try:
            os.kill(손자, signal.SIGKILL)
        except ProcessLookupError:
            pass


def test_로그가_실시간으로_쌓인다(잡판, synthetic_job):
    """작업이 **끝나기 전**에 로그파일이 이미 커져 있다 (ENG-03 / Pitfall 1).

    **끝난 뒤에 재면 의미가 없다.** 블록 버퍼링이 걸려 있어도 종료 시점에 한꺼번에
    떨어지므로 그 측정은 `PYTHONUNBUFFERED` 가 없어도 통과한다 — 뽑아 놔도 초록인
    검증이 된다. 그래서 중간 시점에 잰다. 실측 근거(RESEARCH §5.1):
    기본 0.5초 시점 **0바이트** / 환경변수 주입 시 14바이트.
    """
    스펙 = synthetic_job(lines=12, delay=0.2)        # 총 2.4초
    job_id = jobs.create_job("synthetic", argv_override=스펙["argv"])
    로그 = jobs.log_path_of(job_id)

    time.sleep(0.6)
    크기 = 로그.stat().st_size
    assert jobs.job_status(job_id)["status"] == "running", "너무 빨리 끝났다 — 측정이 무의미"
    assert 크기 > 0, "작업 중인데 로그가 0바이트다 — PYTHONUNBUFFERED 가 빠졌다"
    assert b"tick" in 로그.read_bytes()


def test_쓰기잡은_동시에_두개가_안된다(잡판, synthetic_job):
    """쓰기 잡은 전역에서 하나만 (Pitfall 3 / T-1-09).

    `run_bids` 가 `before_bids_<alias>.json` 과 `ledger/<alias>.json` 을
    읽고-병합하고-통째로 다시 쓰는데 락이 없다. 두 개가 겹치면 백업 항목이 사라지고
    **그 소재는 영영 되돌릴 수 없다.** 되돌릴 수 없는 손실이라 Phase 1 에서 막는다.
    """
    스펙 = synthetic_job(lines=40, delay=0.2)
    첫번째 = jobs.create_job("prep", argv_override=스펙["argv"])

    for 쓰기종류 in ("prep", "bids_commit", "revert_only", "revert_all"):
        with pytest.raises(jobs.BusyError) as e:
            jobs.create_job(쓰기종류, argv_override=스펙["argv"])
        assert 첫번째 in str(e.value), "사유에 어떤 작업이 막고 있는지가 있어야 한다"

    # 먼저 것이 끝나면 다시 열린다
    jobs._PROCS[첫번째].kill()
    끝날때까지(첫번째)
    두번째 = jobs.create_job("prep", argv_override=synthetic_job(lines=1, delay=0.05)["argv"])
    assert 두번째 != 첫번째


def test_띄우는_중인_쓰기잡도_가드에_잡힌다(잡판, synthetic_job, monkeypatch):
    """CR-01 재현 방어 — **INSERT 와 spawn 사이의 창**에서도 전역 쓰기 가드가 산다.

    예전에는 INSERT 가 `status='running'` · `pid=NULL` 이었고 pid 는 spawn 뒤에 들어왔다.
    그 수~수십 ms 창에서 `_reap`(SSE 가 0.4초마다 부른다)이 `_alive(None)=False` 를 보고
    그 행을 **`orphaned` 로 찍었다.** 그러면 `status='running'` 만 보던 가드가 그 잡을
    못 봐서 **두 번째 쓰기 잡이 들어간다** — `before_bids_<alias>.json` 병합이 깨지면
    그 소재는 영영 못 되돌린다(WRITE_KINDS 주석의 그 사고).

    창을 시간으로 재현하면 확률 테스트가 된다. 대신 `spawn` 안에서 강제로 끼어들어
    **창을 정확히 한 번 벌린다** — 그 순간 ① 폴링이 상태를 못 망가뜨리고
    ② 두 번째 쓰기 잡이 `BusyError` 로 막히는지 본다.
    """
    본것 = {}
    원래spawn = jobs.spawn
    끼어드는중 = {"on": False}

    def 창에서_폴링하는_spawn(argv, log_path):
        # 여기가 그 창이다 — 행은 커밋됐고 pid 는 아직 없다.
        if not 끼어드는중["on"]:
            끼어드는중["on"] = True
            try:
                # ① SSE 폴링이 부르는 그 경로(_reap 포함)를 강제로 돌린다
                본것["창안"] = [(j["id"], j["status"], j["pid"])
                              for j in jobs.recent_jobs(5)]
                # ② 바로 그 순간 두 번째 쓰기 잡을 넣어 본다
                try:
                    본것["두번째"] = jobs.create_job("revert_only", argv_override=argv)
                except jobs.BusyError as e:
                    본것["두번째"] = f"막혔다: {e}"
            finally:
                끼어드는중["on"] = False
        return 원래spawn(argv, log_path)

    monkeypatch.setattr(jobs, "spawn", 창에서_폴링하는_spawn)

    스펙 = synthetic_job(lines=40, delay=0.2)
    첫번째 = jobs.create_job("bids_commit", argv_override=스펙["argv"])

    # 창 안에서 폴링이 돌았다는 것 자체를 먼저 못박는다 — 안 돌았으면 이 테스트는
    # 아무것도 검증하지 않은 것이다(영원히 통과하는 검사를 만들지 않는다).
    assert 첫번째 in [id for id, _, _ in 본것["창안"]], "창 안에서 그 행을 못 봤다"

    # ② **제일 강한 주장부터.** 두 번째 쓰기 잡은 반드시 막혔어야 한다.
    assert str(본것["두번째"]).startswith("막혔다"), \
        f"창 안에서 두 번째 쓰기 잡이 들어갔다: {본것['두번째']} · 창안={본것['창안']}"
    assert 첫번째 in str(본것["두번째"]), "사유에 막은 잡의 id 가 있어야 한다"

    창안상태 = dict((id, st) for id, st, _ in 본것["창안"])[첫번째]
    assert 창안상태 == "starting", f"창 안 상태가 starting 이 아니다: {창안상태}"

    # ③ 창이 닫힌 뒤 그 잡은 멀쩡히 running 이다 — orphaned 로 찍히지 않았다
    상태 = jobs.job_status(첫번째)
    assert 상태["status"] == "running", f"멀쩡한 잡이 {상태['status']} 로 찍혔다"
    assert 상태["pid"] > 0


def test_띄우다_죽은_잡은_가드를_영원히_잡지_않는다(잡판, monkeypatch):
    """`starting` 이 영원히 남으면 `_reap` 이 원래 막던 고장이 이름만 바꿔 돌아온다.

    INSERT 는 됐는데 spawn 전에 프로세스가 통째로 죽은 경우다. `STARTING_TIMEOUT_SEC`
    을 넘기면 `failed` 로 닫혀 **다음 쓰기 작업이 열려야 한다.**
    """
    monkeypatch.setattr(jobs, "spawn", lambda argv, log_path: 가짜프로세스(argv))
    죽은놈 = jobs.create_job("bids_commit", argv_override=["x"])

    # 서버가 INSERT 직후에 죽은 상태를 손으로 만든다 — starting 으로 되돌리고
    # 시작 시각을 상한 너머로 민다.
    cx = jobs._conn()
    옛날 = (datetime.now().astimezone()
          - timedelta(seconds=jobs.STARTING_TIMEOUT_SEC + 5)).isoformat(timespec="seconds")
    cx.execute("UPDATE jobs SET status='starting', pid=NULL, started_at=? WHERE id=?",
               (옛날, 죽은놈))
    cx.commit()
    cx.close()
    jobs._PROCS.pop(죽은놈, None)

    # 상한을 넘겼으니 다음 쓰기 잡이 들어가야 한다
    다음 = jobs.create_job("bids_commit", argv_override=["y"])
    assert jobs.job_status(죽은놈)["status"] == "failed"
    assert jobs.job_status(죽은놈)["exit_code"] == -1
    assert 다음 != 죽은놈


def test_띄우는_중인_잡은_상한_전까지는_가드를_잡는다(잡판, monkeypatch):
    """음성 대조군 — 위 테스트가 "그냥 starting 을 다 풀어 준다" 로 통과하지 않게.

    상한을 **안 넘긴** `starting` 은 살아 있는 잡이므로 가드가 그대로 걸려야 한다.
    """
    monkeypatch.setattr(jobs, "spawn", lambda argv, log_path: 가짜프로세스(argv))
    도는놈 = jobs.create_job("bids_commit", argv_override=["x"])

    cx = jobs._conn()
    cx.execute("UPDATE jobs SET status='starting', pid=NULL WHERE id=?", (도는놈,))
    cx.commit()
    cx.close()

    with pytest.raises(jobs.BusyError) as e:
        jobs.create_job("revert_all", argv_override=["y"])
    assert 도는놈 in str(e.value)
    assert jobs.job_status(도는놈)["status"] == "starting", "상한 전인데 상태가 바뀌었다"


def test_미리보기는_가드를_안탄다(잡판, synthetic_job):
    """`bids_preview`·`run` 은 아무것도 쓰지 않으므로 겹쳐도 안전하다.

    가드를 넓게 걸면 "미리보기조차 못 누르는" 화면이 된다 — 안전하지도 않으면서
    쓰기가 아닌 것까지 막는 가드는 사람이 가드를 끄게 만든다.
    """
    스펙 = synthetic_job(lines=40, delay=0.2)
    jobs.create_job("prep", argv_override=스펙["argv"])          # 쓰기 잡 가동 중

    미리보기 = jobs.create_job("bids_preview", argv_override=스펙["argv"])
    판정 = jobs.create_job("run", argv_override=스펙["argv"])
    assert jobs.job_status(미리보기)["status"] == "running"
    assert jobs.job_status(판정)["status"] == "running"


def test_argv_에_시크릿이_없다(잡판, monkeypatch):
    """jobs 테이블의 argv 컬럼에 자격증명이 들어갈 설계를 만들지 않는다 (T-1-03c).

    CLI 가 `~/.eroom/naver-ads.json` 을 **직접** 읽으므로 웹앱이 넘길 것이 없다.
    env 로 넘기는 설계도 쓰지 않는다 — `ps -E` 에 그대로 뜬다.
    """
    monkeypatch.setattr(jobs, "spawn", lambda argv, log_path: 가짜프로세스(argv))
    job_id = jobs.create_job("prep", accounts=["acct_one"])

    기록 = json.loads(jobs.job_status(job_id)["argv"])
    합친것 = " ".join(기록)
    for 금지 in ("api_key", "secret_key", "customer_id", "CUSTOMER", "password"):
        assert 금지 not in 합친것
    assert 기록[:1] == [str(jobs.argv.PY_CLI)]
    assert "--account" in 기록 and "acct_one" in 기록

    # 자식 환경에도 자격증명을 심지 않는다 — 넘길 필요가 없으니 넘기지 않는다
    엔진 = Path(jobs.__file__).read_text(encoding="utf-8")
    assert "naver-ads.json" not in 엔진


def test_잡이_끝나면_exit_code_가_기록된다(잡판, synthetic_job):
    """종료 감지 — 상태가 `done`, exit_code 가 0, ended_at 이 채워진다."""
    스펙 = synthetic_job(lines=2, delay=0.05)
    job_id = jobs.create_job("synthetic", argv_override=스펙["argv"])

    상태 = 끝날때까지(job_id)
    assert 상태["status"] == "done"
    assert 상태["exit_code"] == 0
    assert 상태["ended_at"]
    assert 상태["elapsed_sec"] >= 0

    # 끝난 잡은 쓰기 가드를 막지 않는다
    assert jobs.create_job("prep", argv_override=스펙["argv"])


def test_실패한_잡은_failed_다(잡판, synthetic_job):
    """종료코드가 0 이 아니면 `failed`. **실패를 조용히 done 으로 접지 않는다.**"""
    스펙 = synthetic_job(lines=1, delay=0.05, rc=1)
    job_id = jobs.create_job("synthetic", argv_override=스펙["argv"])

    상태 = 끝날때까지(job_id)
    assert 상태["status"] == "failed"
    assert 상태["exit_code"] == 1


def test_모르는_회차는_작업이_되지_않는다(잡판, tmp_run_dir, monkeypatch):
    """회차 화이트리스트를 **create_job 안에서** 통과시킨다 (T-1-11).

    라우트가 깜빡해도 막힌다 — 검증을 입구 한 곳에만 두면 입구가 늘어날 때마다
    빠뜨린다. 여기 두면 v2 의 스케줄러도 같은 문을 통과한다.
    """
    monkeypatch.setattr(jobs, "spawn", lambda argv, log_path: 가짜프로세스(argv))

    for 나쁜회차 in ("nope", "../../etc", "2026-08-31"):
        with pytest.raises(ValueError):
            jobs.create_job("bids_preview", run_dir=나쁜회차)

    # 실재하는 회차는 통과한다 (tmp_run_dir 픽스처가 만든 것)
    assert jobs.create_job("bids_preview", run_dir=tmp_run_dir.name)


def test_대상_목록이_파일로_떨어지고_argv_가_그_파일을_지목한다(잡판, tmp_run_dir, monkeypatch):
    """FLOW-02 의 '그 파일' — 미리보기·실행·되돌리기가 같이 지목할 대상 파일.

    화면 상태에서 대상을 다시 만들지 않는다(D-11). 그러려면 대상이 **파일로**
    남아야 하고, 그 파일 경로가 jobs 행에 붙어 있어야 한다.
    """
    monkeypatch.setattr(jobs, "spawn", lambda argv, log_path: 가짜프로세스(argv))
    대상 = ["nad-a001-02-000000495390006", "nad-a001-02-000000502308153"]

    job_id = jobs.create_job("bids_preview", run_dir=tmp_run_dir.name, only_ads=대상)
    상태 = jobs.job_status(job_id)

    떨어진파일 = Path(상태["targets_path"])
    assert 떨어진파일.is_file()
    assert json.loads(떨어진파일.read_text(encoding="utf-8")) == 대상
    assert 떨어진파일.parent == tmp_run_dir / "web"
    assert 상태["target_count"] == 2

    기록 = json.loads(상태["argv"])
    assert 기록[기록.index("--only-ads") + 1] == str(떨어진파일)
    # 미리보기 산출물 경로도 웹앱이 정한다 — 사용자 입력에서 경로를 받지 않는다(ASVS V12)
    assert 기록[기록.index("--preview-out") + 1] == 상태["result_path"]
    # dry-run 이다: 실행 플래그가 붙지 않는다
    assert not any("commit" in a for a in 기록)


def test_대상_없는_revert_only_는_만들어지지_않는다(잡판, tmp_run_dir, monkeypatch):
    """WR-02 — **kind 이름은 `revert_only` 인데 동작이 `revert_all` 이 되는 경로를 막는다.**

    대상 파일이 없으면 `AdsArgv` 가 `--only-ads` 를 안 붙이고, CLI 는 그걸 "백업 전량"
    으로 읽는다. 지금 운영 라우트는 항상 대상 파일을 넘기므로 안 나지만, v2 의
    APScheduler 가 `create_job("revert_only", run_dir=X, commit=True)` 로 부르는 순간
    회차 전체(실측 2,242건)가 풀린다. **빈 값이 '전량' 이 되는 경로는 예외로 터뜨린다.**
    """
    만든argv = []
    monkeypatch.setattr(jobs, "spawn",
                        lambda argv, log_path: (만든argv.append(argv), 가짜프로세스(argv))[1])

    with pytest.raises(ValueError) as e:
        jobs.create_job("revert_only", run_dir=tmp_run_dir.name, commit=True)
    assert "회차 전체" in str(e.value), "사유가 '왜 위험한지' 를 말해야 한다"
    assert 만든argv == [], "거부했는데 자식이 떴다"

    # 음성 대조군 — 대상 파일을 주면 통과하고 argv 에 --only-ads 가 붙는다.
    # (이게 없으면 "그냥 revert_only 를 전부 막는다" 로도 위 assert 가 초록이다)
    부모 = jobs.create_job("bids_preview", run_dir=tmp_run_dir.name,
                          only_ads=["nad-a001-02-000000495390006"])
    대상파일 = jobs.job_status(부모)["targets_path"]
    좁힌것 = jobs.create_job("revert_only", run_dir=tmp_run_dir.name, commit=True,
                           targets_path_override=대상파일)
    기록 = json.loads(jobs.job_status(좁힌것)["argv"])
    assert 기록[기록.index("--only-ads") + 1] == 대상파일

    # `revert_all` 은 대상 파일 없이도 만들어진다 — 이름 그대로 회차 전체이므로
    # 여기서 막으면 D-14 의 두 번째 버튼이 사라진다.
    jobs._PROCS.clear()
    cx = jobs._conn()
    cx.execute("UPDATE jobs SET status='done' WHERE status IN ('running','starting')")
    cx.commit(); cx.close()
    전체 = jobs.create_job("revert_all", run_dir=tmp_run_dir.name, commit=True)
    전체argv = json.loads(jobs.job_status(전체)["argv"])
    assert "--only-ads" not in 전체argv


def test_최근_작업_목록이_최신순이다(잡판, monkeypatch):
    monkeypatch.setattr(jobs, "spawn", lambda argv, log_path: 가짜프로세스(argv))
    만든것 = [jobs.create_job("run") for _ in range(3)]

    목록 = jobs.recent_jobs(limit=2)
    assert [j["id"] for j in 목록] == 만든것[::-1][:2]


def test_고아_잡은_orphaned_로_남는다(잡판, synthetic_job):
    """서버가 재시작되면 인메모리 맵이 비는데 자식은 살아 있을 수 있다.

    `--workers 1` 전제의 인메모리 `poll()` 맵이 성립하지 않는 유일한 경우다.
    Phase 1 은 **`orphaned` 로 표시만** 하고 복구는 Phase 2(ENG-05)에 넘긴다 —
    지어낸 exit_code 를 적는 것보다 "모른다" 를 적는 편이 정직하다.
    """
    스펙 = synthetic_job(lines=1, delay=0.05)
    job_id = jobs.create_job("synthetic", argv_override=스펙["argv"])
    proc = jobs._PROCS.pop(job_id)            # 서버 재시작 흉내
    proc.wait(timeout=5)

    상태 = jobs.job_status(job_id)
    assert 상태["status"] == "orphaned"
    assert 상태["exit_code"] is None


def test_스키마는_기록_테이블만_있다(잡판):
    """허용 테이블은 `jobs`·`ss_index`·`banner_label`·`banner_confirm`·`market_gate` 다섯뿐이다.

    **보드 캐시 금지는 여전히 유효하다.** Phase 1 에서는 `jobs` 하나뿐이었고, Phase 3 이
    `ss_index`(D-20 / T-3-03), Phase 4 가 라벨 2종(BANNER-02b)을 더하면서 이 가드를
    **일부러** 넓혔다. 조용히 고치면 다음 사람이 "보드 캐시 금지" 원칙이 통째로 풀린 줄
    안다 — 그래서 예외 사유를 매번 여기 못 박는다.

    판별 기준은 세 번 다 하나다 — **재생성이 공짜가 아니면 그건 캐시가 아니라 기록이다**:
      - 보드 캐시(금지): `result.json` 에서 **언제든 재생성 가능한 투영**이다. 두는 순간
        진실이 둘이 되고, 회차를 다시 판정해도 화면이 안 따라오는 사고가 난다.
      - `ss_index`: `smartstore번호 → productId` 는 3시간 반을 태워야 다시 얻는 **외부 관측
        기록**이다(36그룹 / 47,105 상품, D-18).
      - `banner_label`/`banner_confirm`: **사람의 시간**이다. 다시 얻으려면 사람이 그 장을
        다시 다 봐야 한다. 반대로 기계 판정은 몇 분이면 다시 나오는 투영이라 산출물 JSON
        하나가 정본이고, 이 테이블에 복사하지 않는다(그래서 `사람판정` 컬럼만 있다).
      - `market_gate` (Phase 6 / 06-04 · D-09): 첫 1건을 **사람이 스토어에서 눈으로 본 판정**이다.
        완료 대장이 아니다(L-05) — 반영 완료의 정본은 불사자 서버 · market_status.json 이고,
        여기는 정상/이상 한 줄씩만 누적한다.

    **대상별 잠금 테이블은 여전히 Phase 2(ENG-04)다.** 지금 만들면 안 쓰는 스키마가 굳는다.
    """
    import sqlite3
    cx = sqlite3.connect(jobs.db_path())
    이름들 = {r[0] for r in cx.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    cx.close()
    assert "jobs" in 이름들
    # sqlite_sequence 는 market_gate 의 AUTOINCREMENT 가 SQLite 안에서 스스로 두는 내부 표다 — 우리 스키마 아님
    assert 이름들 - {"jobs", "ss_index", "banner_label", "banner_confirm",
                   "market_gate", "sqlite_sequence"} == set(), f"예상 밖 테이블: {이름들}"


def test_라벨_테이블이_DDL_한곳에서_생긴다(잡판):
    """`init_db()` 만으로 라벨 2종이 생긴다 — 스키마 정본이 `jobs.DDL` 하나다.

    `banner_scan.py` 는 SQLite 를 아예 안 만진다. 자식이 테이블을 만들기 시작하면
    스키마가 두 곳에서 자라고, 둘이 어긋난 날 "라벨을 저장했는데 화면에 없다" 가 된다
    (`ss_index_build.py:165-176` 이 만들지 않고 확인만 하는 것과 같은 선).

    **기계 판정 컬럼이 없다는 것**도 같이 못박는다 (T-4-20). 여기 배너/제품/무내용을
    복사하면 진실이 둘이 되고, 어휘군을 고쳐 다시 돌린 회차에서 화면과 산출물이 다른
    말을 한다.
    """
    import sqlite3
    cx = sqlite3.connect(jobs.db_path())
    try:
        라벨 = {r[1] for r in cx.execute("PRAGMA table_info(banner_label)")}
        확인 = {r[1] for r in cx.execute("PRAGMA table_info(banner_confirm)")}
        라벨키 = [r[1] for r in cx.execute("PRAGMA table_info(banner_label)") if r[5]]
    finally:
        cx.close()

    assert 라벨 == {"run_dir", "타오바오상품번호", "판매자상품코드",
                  "이미지순번", "사람판정", "기록시각"}, 라벨
    assert 확인 == {"run_dir", "타오바오상품번호", "확인시각"}, 확인

    # 키가 URL 이 아니다. 불사자는 수집할 때마다 같은 이미지를 **새 CDN 경로에 복사**하므로
    # (D-01a 실측), URL 을 키로 잡으면 다음 수집에서 라벨이 통째로 미아가 된다.
    assert 라벨키 == ["run_dir", "타오바오상품번호", "이미지순번"], 라벨키

    # 🔴 "이 장을 뒤집었다" 와 "이 줄을 다 봤다" 는 **다른 사실**이다. 합치면 확인 표시가
    #    라벨로 둔갑해 게이트 집계의 분모가 조용히 틀어진다.
    assert "사람판정" not in 확인, "확인 표시에 판정이 섞였다 — 두 테이블을 합치지 마라"
    for 기계 in ("판정", "배너", "제품", "무내용", "사유"):
        assert 기계 not in 라벨, f"banner_label 에 기계 판정('{기계}')이 복사됐다 (T-4-20)"


def test_자식_환경에_버퍼링해제가_들어간다(잡판, tmp_path):
    """`spawn` 이 실제로 환경변수를 주입하는지 자식에게 물어본다.

    문자열 검사(`'PYTHONUNBUFFERED' in 소스`)로 때우지 않는다 — 그건 주석에도 걸린다.
    """
    로그 = tmp_path / "env.log"
    코드 = "import os;print(os.environ.get('PYTHONUNBUFFERED'), os.environ.get('HOME') is not None)"
    proc = jobs.spawn([sys.executable, "-c", 코드], 로그)
    proc.wait(timeout=10)

    찍힌것 = 로그.read_text(encoding="utf-8").strip()
    assert 찍힌것.startswith("1"), f"PYTHONUNBUFFERED 가 안 들어갔다: {찍힌것}"
    # env 는 **병합**이다 — 통째로 갈아치우면 PATH·HOME 이 사라져 CLI 가 죽는다
    assert 찍힌것.endswith("True")


def test_자식은_표준입력을_기다리지_않는다(잡판, tmp_path):
    """`stdin=DEVNULL` — 자식이 입력을 기다리며 영원히 멈추는 사고를 막는다."""
    로그 = tmp_path / "stdin.log"
    proc = jobs.spawn([sys.executable, "-c", "import sys;print(repr(sys.stdin.read()))"], 로그)
    proc.wait(timeout=10)

    assert proc.returncode == 0
    assert 로그.read_text(encoding="utf-8").strip() == "''"


# ── 진행 로그 스트림 (Plan 01-06) ───────────────────────────────────────────
#
# 여기서부터는 **HTTP 를 탄다.** 위쪽 엔진 테스트와 달리 증명 대상이
# "커넥션의 생명주기" 이기 때문이다 — 붙었다 끊겼다 다시 붙는 동안 무엇이 보이는가.
# 함수를 직접 불러서는 그걸 만들어 낼 수 없다. 그래도 **실제 CLI 는 여전히 0번**
# 뜬다: 전부 합성 잡이다.

def 이벤트들(원문: str) -> list[tuple[str, str]]:
    """SSE 원문을 `[(event, data)]` 로 푼다. **잘린 마지막 블록은 버린다.**

    끊긴 지점에서 반쪽짜리 이벤트가 남는데, 그걸 세면 "몇 줄 받았나" 가 흔들린다.
    빈 줄 두 개로 끝난 블록만 완결로 본다.
    """
    정규 = 원문.replace("\r\n", "\n")
    블록들 = 정규.split("\n\n")
    if not 정규.endswith("\n\n"):
        블록들 = 블록들[:-1]              # 잘린 꼬리
    나온것 = []
    for 블록 in 블록들:
        ev, 데이터 = None, []
        for 줄 in 블록.split("\n"):
            if 줄.startswith("event: "):
                ev = 줄[len("event: "):]
            elif 줄.startswith("data: "):
                데이터.append(줄[len("data: "):])
        if ev:
            나온것.append((ev, "\n".join(데이터)))
    return 나온것


def 마지막로그줄(원문: str) -> list[str]:
    """마지막 `log` 이벤트가 담은 로그 줄 목록."""
    로그 = [d for e, d in 이벤트들(원문) if e == "log"]
    if not 로그:
        return []
    return [줄 for 줄 in 로그[-1].split("\n") if 줄.strip()]


@pytest.fixture
def 화면(잡판, client):
    """보드에서 온 것처럼 쿠키까지 붙인 클라이언트 + tmp 잡 DB."""
    from webapp import security
    client.cookies.set(security.COOKIE_NAME, security.BOOT_TOKEN)
    return client


@pytest.fixture
def 실서버(잡판):
    """**진짜 uvicorn 을 띄운다.** `TestClient` 로는 스트리밍을 검증할 수 없다.

    실측 근거: `starlette/testclient.py` 의 전송 계층은 `portal.call(app, ...)` 로
    ASGI 앱을 **끝까지 돌린 뒤** 본문을 `io.BytesIO` 에 모아 한 번에 돌려준다.
    그래서 "0.8초 받고 끊는다" 를 흉내조차 못 내고, 서버 쪽 `is_disconnected()` 도
    영원히 False 다. 이 파일의 다른 스트림 테스트(헤더·404·즉시 done)는 앱을 끝까지
    돌려도 답이 같아서 TestClient 로 충분하지만, **재접속만은 진짜 소켓이 필요하다.**

    레지스트리·로그 경로는 환경변수로 넘긴다 — 별도 프로세스라 monkeypatch 가
    닿지 않고, 저장소 루트의 진짜 `webapp.db` 를 쓰면 테스트가 화면에 유령 작업을 남긴다.
    """
    import httpx

    포트 = _빈포트()
    토큰 = "ct-test-" + uuid.uuid4().hex   # 쿠키 헤더는 ASCII 만 받는다
    env = {
        **os.environ,
        "CT_PORT": str(포트),
        "CT_DEV_TOKEN": 토큰,
        "CT_DB_PATH": str(잡판 / "jobs.db"),
        "CT_JOB_LOG_DIR": str(잡판 / "logs"),
        "PYTHONUNBUFFERED": "1",
    }
    서버 = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "webapp.main:app",
         "--host", "127.0.0.1", "--port", str(포트), "--workers", "1",
         "--log-level", "warning"],
        cwd=str(Path(jobs.__file__).resolve().parent.parent),
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    주소 = f"http://127.0.0.1:{포트}"
    try:
        한계 = time.time() + 15
        while time.time() < 한계:
            try:
                if httpx.get(f"{주소}/healthz", timeout=1).status_code == 200:
                    break
            except Exception:
                time.sleep(0.1)
        else:
            pytest.fail("uvicorn 이 15초 안에 안 떴다")
        yield 주소, 토큰
    finally:
        서버.terminate()
        try:
            서버.wait(timeout=5)
        except subprocess.TimeoutExpired:
            서버.kill()


def _빈포트() -> int:
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    포트 = s.getsockname()[1]
    s.close()
    return 포트


def 잠깐붙기(주소: str, 토큰: str, job_id: str, 초: float) -> str:
    """스트림에 붙어 `초` 동안 받고 **끊는다.** 브라우저 탭을 닫는 것과 같은 일이다."""
    import httpx

    받은 = b""
    시작 = time.time()
    with httpx.stream("GET", f"{주소}/jobs/{job_id}/stream",
                      headers={"Cookie": f"ct_session={토큰}"}, timeout=10) as r:
        assert r.status_code == 200, r.status_code
        for 덩어리 in r.iter_raw():
            받은 += 덩어리
            if time.time() - 시작 >= 초:
                break
    return 받은.decode("utf-8", "replace")


def test_재접속하면_처음부터_이어본다(실서버, synthetic_job):
    """**SC-03.** 탭을 닫았다 다시 열면 로그가 처음부터 흐르고 끊긴 사이까지 이어진다.

    합성 잡 12줄 × 0.2초(2.4초)를 띄우고:
      0.0~0.8초  붙어서 본다        → 앞부분만 보인다
      0.8~1.6초  끊겨 있다          → 그동안에도 자식은 계속 찍는다
      1.6~2.4초  다시 붙는다        → **1번 줄부터** 다시 흐르고 끊긴 사이 줄까지 온다

    판정 기준을 "줄이 더 많아졌다" 로 쓰지 않는다 — 그건 오프셋 이어받기 설계에서도
    통과한다. **첫 줄이 정확히 `[1/12] tick` 이고, 받은 줄이 1번부터 빠짐없이
    연속이며, 중복이 없다**는 것까지 본다 (01-04 의 교훈: "숫자가 움직인다"는 근거가 아니다).

    잡은 이 테스트 프로세스가 만든다 — 합성 잡은 운영 라우트로 못 만든다(T-1-23).
    서버는 같은 레지스트리 파일을 읽어 그 작업을 본다.
    """
    주소, 토큰 = 실서버
    스펙 = synthetic_job(lines=12, delay=0.2)
    job_id = jobs.create_job("synthetic", argv_override=스펙["argv"])

    앞 = 잠깐붙기(주소, 토큰, job_id, 0.8)
    앞줄 = 마지막로그줄(앞)
    assert 앞줄, "1차 접속에서 아무것도 못 받았다"
    assert 앞줄[0] == "[1/12] tick"
    assert len(앞줄) < 12, f"1차 접속이 다 받아 버렸다 ({len(앞줄)}줄) — 측정이 무의미"

    time.sleep(0.8)                                # 탭이 닫혀 있는 동안

    뒤 = 잠깐붙기(주소, 토큰, job_id, 0.8)
    뒤줄 = 마지막로그줄(뒤)

    assert 뒤줄[0] == "[1/12] tick", "재접속했더니 첫 줄이 없다 (전량 재생이 아니다)"
    assert 뒤줄[:len(앞줄)] == 앞줄, "재접속 페이로드가 1차와 어긋난다"
    assert len(뒤줄) > len(앞줄), "끊긴 사이에 찍힌 줄이 안 왔다 (파이프를 읽고 있다)"

    # 진행 줄은 1번부터 빠짐없이 연속이어야 한다(중복 0 · 누락 0).
    # 잡이 창 안에서 끝나면 마지막에 완료 줄이 하나 더 붙는다 — 그건 진행 줄이 아니다.
    틱 = [줄 for 줄 in 뒤줄 if 줄.endswith("tick")]
    assert 틱 == [f"[{i}/12] tick" for i in range(1, len(틱) + 1)], \
        f"줄이 빠졌거나 중복됐다: {뒤줄}"
    assert 뒤줄[:len(틱)] == 틱, f"진행 줄 사이에 다른 게 끼었다: {뒤줄}"


def test_스트림은_event_stream_이고_gzip_으로_묶이지_않는다(화면, synthetic_job):
    """gzip 이 걸리면 압축 버퍼에 고여서 **로그가 끝날 때까지 안 보인다.**

    Starlette 1.6.0 의 GZipMiddleware 가 `text/event-stream` 을 기본 제외 목록에
    두고 있어서 지금은 안전하다. 그 기본값은 우리 것이 아니므로 기계로 지킨다.
    """
    job_id = jobs.create_job("synthetic", argv_override=synthetic_job(lines=2, delay=0.05)["argv"])
    with 화면.stream("GET", f"/jobs/{job_id}/stream") as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        assert "content-encoding" not in r.headers, "SSE 가 압축됐다 — 로그가 고인다"
        assert r.headers.get("cache-control", "").find("no-cache") >= 0
        r.close()


def test_모르는_잡의_스트림은_404(화면):
    assert 화면.get("/jobs/그런거없음/stream").status_code == 404


def test_쿠키_없이는_스트림을_못_연다(잡판, client, synthetic_job):
    job_id = jobs.create_job("synthetic", argv_override=synthetic_job(lines=1, delay=0.05)["argv"])
    client.cookies.clear()
    assert client.get(f"/jobs/{job_id}/stream").status_code == 403


def test_끝난_잡의_스트림은_전량재생후_즉시_닫힌다(화면, synthetic_job):
    """작업이 끝난 뒤 붙어도 로그를 전부 보여주고 `done` 으로 스스로 닫는다."""
    job_id = jobs.create_job("synthetic", argv_override=synthetic_job(lines=2, delay=0.05)["argv"])
    끝날때까지(job_id)

    받은 = 화면.get(f"/jobs/{job_id}/stream").text       # 스스로 닫히니 통째로 받힌다
    종류 = [e for e, _ in 이벤트들(받은)]
    assert 종류.count("done") == 1
    assert 종류[-1] == "done", f"done 뒤에 더 보냈다: {종류}"
    assert 마지막로그줄(받은) == ["[1/2] tick", "[2/2] tick", "합성 잡 완료"]


def test_스트림_GET_은_작업을_만들지_않는다(화면, synthetic_job):
    """T-1-01b — 읽기 라우트가 부수효과를 가지면 Origin 방어의 전제가 무너진다."""
    job_id = jobs.create_job("synthetic", argv_override=synthetic_job(lines=1, delay=0.05)["argv"])
    끝날때까지(job_id)
    처음 = len(jobs.recent_jobs(50))

    for _ in range(3):
        assert 화면.get(f"/jobs/{job_id}/stream").status_code == 200

    assert len(jobs.recent_jobs(50)) == 처음


def test_라우트_중_async_는_스트림_하나다():
    """T-1-28 — `async def` 라우트 안의 blocking IO 는 이벤트 루프를 통째로 세운다.

    나머지 핸들러는 `def` 로 둬서 Starlette 스레드풀이 sqlite·파일 IO 를 받는다.
    `grep -c 'async def'` 로는 못 센다 — 라우트가 아닌 의존성 함수도 async 라서.
    데코레이터가 붙은 def 만 골라서 본다.
    """
    본문 = Path(jobs.__file__).parent.joinpath("routes/jobs.py").read_text(encoding="utf-8")
    줄들 = 본문.splitlines()
    async_라우트 = []
    for i, 줄 in enumerate(줄들):
        if not 줄.startswith("@router."):
            continue
        for 뒤 in 줄들[i + 1:i + 4]:
            if 뒤.startswith("async def "):
                async_라우트.append(뒤.split("(")[0].replace("async def ", ""))
            if 뒤.startswith(("def ", "async def ")):
                break
    assert len(async_라우트) == 1, f"async 라우트가 여럿이다: {async_라우트}"
    assert "stream" in async_라우트[0]


def test_작업패널이_로그를_붙이지_않고_교체한다():
    """T-1-26 — `beforeend` 를 쓰면 재연결 때 로그가 두 번 찍힌다.

    서버가 누적본을 보내므로 클라이언트는 기본 swap(innerHTML 전량 교체)을 써야 맞다.
    """
    패널 = Path(jobs.__file__).parent.joinpath("templates/_job_panel.html")
    본문 = 패널.read_text(encoding="utf-8")
    assert "beforeend" not in 본문
    assert 'hx-ext="sse"' in 본문
    assert 'sse-swap="log"' in 본문
    # **닫기 속성은 연결을 여는 그 엘리먼트에 있어야 한다.** 확장이 EventSource 를
    # 만든 엘리먼트에서만 이 속성을 읽는다(sse.js:235). 자식에 붙이면 조용히 무시되고
    # 작업이 끝난 뒤 브라우저가 영원히 재연결한다 (헤드리스 크롬 실측).
    연결줄 = [줄 for 줄 in 본문.splitlines() if "sse-connect" in 줄]
    assert len(연결줄) == 1
    assert 'sse-close="done"' in 연결줄[0], f"닫기 속성이 연결 엘리먼트에 없다: {연결줄[0]}"
    assert "/stream" in 본문
    # 스트림은 **활성 잡 하나만** 연다 (T-1-24: HTTP/1.1 호스트당 6 커넥션)
    assert 본문.count("sse-connect") == 1


def test_보드가_도는_작업을_들고_있다(잡판, synthetic_job):
    """탭을 닫았다 다시 열었을 때 패널이 비어 있으면 SC-03 자체가 성립하지 않는다.

    페이지를 새로 그리는 것은 `GET /` 이고, 그때 도는 작업을 컨텍스트에 실어야
    패널이 나오고 그 패널이 스트림을 연다.
    """
    assert jobs.active_job() is None
    job_id = jobs.create_job("synthetic", argv_override=synthetic_job(lines=40, delay=0.2)["argv"])

    도는것 = jobs.active_job()
    assert 도는것 and 도는것["id"] == job_id

    jobs._PROCS[job_id].kill()
    끝날때까지(job_id)
    assert jobs.active_job() is None, "끝난 작업이 계속 패널에 남는다"


def test_새로고침하면_도는_작업_패널이_다시_뜬다(화면, tmp_run_dir, synthetic_job):
    """**탭을 다시 여는 것 = `GET /` 이다.** 그 응답에 패널과 스트림 주소가 있어야 한다.

    이게 비면 재접속 스트림이 아무리 완벽해도 화면에서는 성공기준 3 이 성립하지 않는다 —
    열 스트림이 없으니까.
    """
    빈보드 = 화면.get("/").text
    assert "/stream" not in 빈보드, "도는 작업이 없는데 패널이 떴다"

    job_id = jobs.create_job("synthetic", argv_override=synthetic_job(lines=40, delay=0.2)["argv"])

    본문 = 화면.get("/").text
    assert '<section id="job-panel">' in 본문
    assert f'/jobs/{job_id}/stream' in 본문
    assert 본문.count("sse-connect") == 1, "스트림을 여럿 연다 (HTTP/1.1 6 커넥션 한계)"
    assert 'id="job-log"' in 본문


# ── 불사자 잡 가드 2종 (Phase 3 / ENG-08 · Pitfall 3) ───────────────────────
#
# 자식을 **한 번도 띄우지 않는다.** `jobs.spawn` 을 가짜로 바꿔 가드만 겨눈다 —
# 불사자 CLI 는 03-04 가 만들고, 여기서 태우면 레이트리밋 예산을 실제로 갉아먹는다.

from webapp import bulsaja_index, paths  # noqa: E402


@pytest.fixture
def 계정확인(tmp_path, monkeypatch):
    """저장소 루트를 tmp 로 돌리고 프로필 파일을 깔아 주는 팩토리.

    `내용=None` 으로 부르면 파일을 안 깐다("계정 확인을 한 번도 안 했다" 상태).
    """
    monkeypatch.setattr(paths, "repo_root", lambda: tmp_path)

    def _깔기(닉: str | None = None, 분전: float = 0):
        if 닉 is None:
            return
        본때 = (datetime.now().astimezone()
                - timedelta(minutes=분전)).isoformat(timespec="seconds")
        bulsaja_index.profile_path().write_text(
            json.dumps({"닉네임": 닉, "확인시각": 본때}, ensure_ascii=False),
            encoding="utf-8")
    return _깔기


@pytest.fixture
def 기대닉(monkeypatch):
    """기대 닉네임을 테스트가 정한 값으로 돌린다.

    **진짜 닉네임을 테스트에 적지 않는다** — 적으면 리터럴 가드와 충돌하고, 저장소가
    공개될 때 계정 정보가 같이 나간다(conftest.py 원칙 둘).
    """
    값 = "zz기대계정"
    원래 = settings.load()
    monkeypatch.setattr(settings, "_cache", {**원래, "expected_bulsaja_nick": 값})
    return 값


@pytest.fixture
def 안띄운다(monkeypatch):
    """`spawn` 을 가짜로 바꾼다. 가드만 겨누는 테스트가 진짜 자식을 안 띄우게."""
    monkeypatch.setattr(jobs, "spawn", lambda argv_list, log_path: 가짜프로세스(argv_list))


def _행수() -> int:
    import sqlite3
    cx = sqlite3.connect(jobs.db_path())
    try:
        return cx.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    finally:
        cx.close()


def _인덱스잡(run_dir: str) -> str:
    """인덱스 잡 하나를 만든다.

    대상(그룹) 목록은 광고 쪽과 **같은 통로**로 떨어진다 — `only_ads` 가 `_write_targets`
    로 회차의 `web/` 밑에 JSON 배열을 쓴다. 담기는 내용만 groupId 리스트다.
    """
    return jobs.create_job("bulsaja_index", run_dir=run_dir, only_ads=["zzgrp-a"])


def test_계정불일치_거부(잡판, 계정확인, 기대닉, 안띄운다, tmp_run_dir):
    """붙어 있는 계정이 기대와 다르면 **자식을 띄우기 전에** 거부된다 (ENG-08).

    그리고 **jobs 테이블에 행이 안 생긴다** — 거부가 INSERT 보다 먼저라는 증거다.
    행이 생기면 화면 목록에 "실패한 불사자 잡" 이 쌓여 진짜 실패와 구분이 안 된다.
    """
    계정확인("zz다른계정")
    이전 = _행수()

    with pytest.raises(jobs.AccountMismatchError):
        _인덱스잡(tmp_run_dir.name)

    assert _행수() == 이전, "거부했는데 jobs 행이 생겼다"


def test_계정확인이_없으면_거부(잡판, 계정확인, 기대닉, 안띄운다):
    """프로필 파일 자체가 없으면 같은 예외다 — "모르면 통과" 하는 가드는 없는 것이다."""
    계정확인(None)

    with pytest.raises(jobs.AccountMismatchError):
        jobs.create_job("bulsaja_scan")


def test_계정확인이_오래되면_거부(잡판, 계정확인, 기대닉, 안띄운다, monkeypatch):
    """닉네임이 맞아도 확인이 낡았으면 거부다 — 그 사이에 계정을 바꿨을 수 있다."""
    상한 = int(settings.cfg("profile_max_age_min",
                            settings.DEFAULTS["profile_max_age_min"]))
    계정확인(기대닉, 분전=상한 + 10)

    with pytest.raises(jobs.AccountMismatchError):
        jobs.create_job("bulsaja_scan")


def test_프로필잡은_가드를_안_탄다(잡판, 계정확인, 기대닉, 안띄운다):
    """계정 확인 잡이 계정 가드를 타면 **첫 확인을 영영 못 한다**(닭·달걀).

    `argv_override` 로 합성 스펙을 태워 피하지 않는다 — 그러면 `_build_argv` 를 안 타서
    "가드를 안 탄다" 가 아니라 "그 경로를 안 밟았다" 를 검증하게 된다.
    """
    계정확인(None)

    job_id = jobs.create_job("bulsaja_profile")

    상태 = jobs.job_status(job_id)
    assert 상태 and 상태["kind"] == "bulsaja_profile"
    assert "--profile-only" in json.loads(상태["argv"])


def test_인덱스잡은_쓰기가드를_안_탄다(잡판, 계정확인, 기대닉, 안띄운다, tmp_run_dir):
    """도는 `bulsaja_index` 가 있어도 입찰가 실행이 만들어진다.

    넣었으면 3시간 32분 동안 입찰가 인상·되돌리기가 전부 409 다 — 그러면 사람이 가드를 끈다.
    """
    계정확인(기대닉)
    _인덱스잡(tmp_run_dir.name)

    미리보기 = jobs.create_job("bids_preview", run_dir=tmp_run_dir.name,
                               only_ads=["nad-zz1"])
    대상 = jobs.job_status(미리보기)["targets_path"]
    # 쓰기 잡(`bids_commit`)도 BusyError 없이 들어간다
    assert jobs.create_job("bids_commit", run_dir=tmp_run_dir.name, commit=True,
                           targets_path_override=대상)


def test_같은_kind_두번째는_거부된다(잡판, 계정확인, 기대닉, 안띄운다, tmp_run_dir):
    """인덱스 잡 두 개가 각자 초당 4회로 돌면 합산 8회/초라 429 가 쏟아진다 (Pitfall 3).

    그 429 는 `unresolved=1` 로 남고 화면에서 "미해소" 로 보인다 — 최대 오진이다.
    그리고 **jobs 행이 안 늘어난다**(거부가 INSERT 보다 먼저).
    """
    계정확인(기대닉)

    첫번째 = _인덱스잡(tmp_run_dir.name)
    이전 = _행수()

    with pytest.raises(jobs.SameKindBusyError):
        _인덱스잡(tmp_run_dir.name)

    assert _행수() == 이전, "거부했는데 jobs 행이 생겼다"
    assert jobs.job_status(첫번째)["status"] == "running"


def test_starting_상태도_중복을_막는다(잡판, 계정확인, 기대닉, 안띄운다, tmp_run_dir):
    """`running` 만 보면 **자식을 띄우는 중인 잡**을 못 잡아 구멍이 그대로 남는다.

    `LIVE_STATUSES` 주석이 이미 한 번 고친 실수와 같은 부류다.
    """
    계정확인(기대닉)
    첫번째 = _인덱스잡(tmp_run_dir.name)

    import sqlite3
    cx = sqlite3.connect(jobs.db_path())
    try:
        cx.execute("UPDATE jobs SET status='starting', pid=NULL WHERE id=?", (첫번째,))
        cx.commit()
    finally:
        cx.close()
    jobs._PROCS.pop(첫번째, None)

    with pytest.raises(jobs.SameKindBusyError):
        _인덱스잡(tmp_run_dir.name)


def test_다른_kind_는_안_막힌다(잡판, 계정확인, 기대닉, 안띄운다, tmp_run_dir):
    """**kind 단위 가드가 전역 락으로 번지지 않았다는 증거.**

    도는 `bulsaja_index` 가 있어도 계정 확인과 입찰가 미리보기는 그대로 만들어진다.
    """
    계정확인(기대닉)
    _인덱스잡(tmp_run_dir.name)

    assert jobs.create_job("bulsaja_profile")
    # 입찰가 미리보기도 막히지 않는다 — 인덱스는 불사자에 아무것도 안 쓴다
    assert jobs.create_job("bids_preview", run_dir=tmp_run_dir.name, only_ads=["nad-zz1"])


def test_쓰기잡이_돌아도_인덱스잡은_만들어진다(잡판, 계정확인, 기대닉, 안띄운다, tmp_run_dir):
    """반대 방향. 회차 준비(`prep`)가 도는 동안에도 인덱스는 시작할 수 있다."""
    계정확인(기대닉)
    jobs.create_job("prep")

    assert _인덱스잡(tmp_run_dir.name)


def test_kind가드는_전역쓰기락과_다른_예외다(잡판, 계정확인, 기대닉, 안띄운다, tmp_run_dir):
    """409 로는 같이 번역되지만 **타입으로 구분되고 메시지가 다르다.**

    섞이면 사용자가 "입찰가 작업이 도나?" 를 찾으러 간다.
    """
    계정확인(기대닉)
    _인덱스잡(tmp_run_dir.name)

    with pytest.raises(jobs.SameKindBusyError) as 터진것:
        _인덱스잡(tmp_run_dir.name)

    # 라우트를 안 고쳐도 409 가 된다
    assert isinstance(터진것.value, jobs.BusyError)
    # 그런데 전역 쓰기 락은 아니다
    assert type(터진것.value) is not jobs.BusyError
    메시지 = str(터진것.value)
    assert "bulsaja_index" in 메시지
    assert "전역 쓰기 락이 아니" in 메시지


def test_기대닉네임이_코드가_아니라_설정에서_온다(잡판, 계정확인, 안띄운다, monkeypatch):
    """**문자열 검사가 아니라 동작으로** 본다 (`test_paths.py` 의 리터럴 가드와 상보적).

    설정값을 바꾸면 거부/통과가 따라 바뀐다 — 그래야 그 값이 진짜로 가드를 움직인다.
    """
    계정확인("zz계정하나")
    원래 = settings.load()

    monkeypatch.setattr(settings, "_cache", {**원래, "expected_bulsaja_nick": "zz계정둘"})
    with pytest.raises(jobs.AccountMismatchError):
        jobs.create_job("bulsaja_scan")

    monkeypatch.setattr(settings, "_cache", {**원래, "expected_bulsaja_nick": "zz계정하나"})
    # 이제 계정은 통과하고, 막히는 건 **대상 파일 없음**(다른 가드)이다
    with pytest.raises(ValueError) as 터진것:
        jobs.create_job("bulsaja_scan")
    assert not isinstance(터진것.value, jobs.AccountMismatchError)


def test_latest_done_은_성공한_잡만_준다(잡판, 계정확인, 기대닉, 안띄운다, tmp_run_dir):
    """산출물 파일을 glob 으로 뒤지지 않는 이유 — 파일이 있는 것과 성공은 다르다.

    중간에 죽은 잡도 반쯤 쓴 파일을 남긴다. 어느 잡이 성공했는지는 레지스트리가 정본이다.
    """
    계정확인(기대닉)

    assert jobs.latest_done("bulsaja_index") is None

    돌던것 = _인덱스잡(tmp_run_dir.name)
    assert jobs.latest_done("bulsaja_index") is None, "도는 잡이 '성공' 으로 나왔다"

    import sqlite3
    cx = sqlite3.connect(jobs.db_path())
    try:
        cx.execute("UPDATE jobs SET status='failed', exit_code=1 WHERE id=?", (돌던것,))
        cx.commit()
    finally:
        cx.close()
    jobs._PROCS.pop(돌던것, None)
    assert jobs.latest_done("bulsaja_index") is None, "실패한 잡이 '성공' 으로 나왔다"

    끝난것 = _인덱스잡(tmp_run_dir.name)
    cx = sqlite3.connect(jobs.db_path())
    try:
        cx.execute("UPDATE jobs SET status='done', exit_code=0 WHERE id=?", (끝난것,))
        cx.commit()
    finally:
        cx.close()
    jobs._PROCS.pop(끝난것, None)

    최근 = jobs.latest_done("bulsaja_index")
    assert 최근 and 최근["id"] == 끝난것
    # 다른 종류까지 집어오지 않는다
    assert jobs.latest_done("bulsaja_scan") is None


def test_latest_done_은_디비를_만들지_않는다(tmp_path, monkeypatch):
    """읽기 경로가 파일을 만들면 "GET 은 상태를 안 바꾼다" 가 흐려진다 (T-1-01b)."""
    없는디비 = tmp_path / "아직없다.db"
    monkeypatch.setattr(settings, "DB_PATH", str(없는디비))

    assert jobs.latest_done("bulsaja_scan") is None
    assert not 없는디비.exists()


# ── 배너 스캔 잡 (Phase 4 / BANNER-01) ──────────────────────────────────────
#
# 자식을 **한 번도 띄우지 않는다.** 실측 4분 12초 · CDN 271MB 짜리라, 테스트가
# 실수로 태우면 그 회차 캐시가 통째로 다시 받아진다.


def _배너잡(run_dir: Path) -> str:
    """배너 스캔 잡 하나를 만든다.

    "대상" 은 상품 목록이 아니라 **직전 성공 조인 스캔의 산출물 파일**이다. 그래서
    `only_ads`(새로 쓴다)가 아니라 `targets_path_override`(있는 파일을 그대로 가리킨다)
    로 넘어간다 — D-11 의 "본 것과 다른 게 돌지 않는다" 가 여기서도 같은 모양이다.
    """
    조인 = run_dir / "web" / "join_zzprev.json"
    조인.parent.mkdir(parents=True, exist_ok=True)
    조인.write_text(json.dumps({"행": []}, ensure_ascii=False), encoding="utf-8")
    return jobs.create_job("banner_scan", run_dir=run_dir.name,
                           targets_path_override=조인)


def _toml덮기(monkeypatch, **webapp덮기):
    """`workspace.toml [webapp]` 을 **파일 읽기 자리에서** 갈아끼운다.

    실제 toml 의 다른 테이블([paths] 등)은 그대로 두고 `[webapp]` 에만 덮는다.
    `_cache` 도 monkeypatch 에 등록해 둔다 — 테스트가 끝나면 강제 재적재로 바뀐
    캐시가 원래대로 돌아간다(다음 테스트가 가짜 설정을 물려받지 않게).
    """
    진짜 = paths.read_workspace_toml()
    가짜 = {**진짜, "webapp": {**(진짜.get("webapp") or {}), **webapp덮기}}
    monkeypatch.setattr(settings, "_cache", settings._cache)
    monkeypatch.setattr(paths, "read_workspace_toml", lambda: 가짜)


def test_배너잡_kind_가_등록돼_있다():
    """`JobKind` 만 고치고 `KINDS` 를 빠뜨리면 런타임이 거부한다 — 둘 다 본다."""
    assert "banner_scan" in jobs.KINDS
    assert "banner_scan" in jobs.JobKind.__args__


def test_배너잡은_전역_쓰기가드에_안_들어간다():
    """🔴 **이 플랜의 1순위 위험이다** (T-4-19).

    `WRITE_KINDS` 에 넣으면 4분 동안 입찰가 인상·되돌리기가 전부 409 가 되고,
    그러면 사람이 가드를 끈다 — `WRITE_KINDS` 주석이 이미 세워 둔 판단 그대로다.
    `BULSAJA_KINDS`(ENG-08 계정 사전점검)에도 없다: MCP 를 0회 부르므로 계정이
    뭐든 판정 결과가 같다.

    집합을 **눈으로 읽어** 확인하지 마라 — 그래서 이게 테스트다.
    """
    assert "banner_scan" not in jobs.WRITE_KINDS
    assert "banner_scan" not in jobs.BULSAJA_KINDS
    # 같은 잡 중복만 막는다. 사유는 레이트리밋이 아니라 271MB 이중 다운로드다.
    assert "banner_scan" in jobs.SINGLETON_KINDS


def test_배너잡이_도는_동안에도_쓰기잡이_들어간다(잡판, 안띄운다, tmp_run_dir):
    """🔴 위 집합 검사의 **행동 판**이다 — 멤버십이 맞아도 동작이 틀릴 수 있다.

    `WRITE_KINDS` 조회가 `IN (...)` 이라 집합만 보면 맞는데, 다른 가드를 잘못 넓히면
    같은 증상이 난다. 그래서 실제로 두 잡을 연달아 만든다.
    """
    배너 = _배너잡(tmp_run_dir)
    assert jobs.job_status(배너)["status"] in jobs.LIVE_STATUSES

    # 배너가 도는 중에도 쓰기 잡이 만들어진다. 여기서 BusyError 가 나면 4분 동안
    # 입찰가 버튼이 죽는다는 뜻이다.
    쓰기 = jobs.create_job("prep")
    assert jobs.job_status(쓰기)["status"] in jobs.LIVE_STATUSES


def test_배너잡_둘은_동시에_안_돈다(잡판, 안띄운다, tmp_run_dir):
    """같은 잡 둘이 271MB 를 두 번 받는 낭비를 막는다 (`SINGLETON_KINDS`).

    **레이트리밋 때문이 아니다** — 불사자 MCP 를 0회 부른다. 거기에 둘이 같은 회차
    캐시에 같은 파일명으로 동시에 쓰면 반쪽 파일이 서로의 입력이 된다.
    """
    _배너잡(tmp_run_dir)
    with pytest.raises(jobs.SameKindBusyError):
        _배너잡(tmp_run_dir)


def test_배너잡은_조인_산출물이_없으면_안_만들어진다(잡판, tmp_run_dir):
    """빈 값이 조용히 '전량' 으로 미끄러지는 경로를 예외로 터뜨린다.

    `revert_only`·`bulsaja_index` 와 **똑같은 모양**이다. 막는 자리는 한 곳
    (`jobs._build_argv`)이고, CLI 의 exit 2 가 그 뒤를 받는 2층이다.
    """
    with pytest.raises(ValueError) as 터진것:
        jobs._build_argv("banner_scan", "zzjob", tmp_run_dir.name, [], None,
                         Path("/tmp/zz-banner.json"), False)
    assert "조인" in str(터진것.value)


def test_배너잡_argv_가_설정에서_온다(잡판, 안띄운다, tmp_run_dir, monkeypatch):
    """`workspace.toml` 을 고치면 자식에게 가는 값이 **실제로** 바뀐다 (S-4 / T-1-12).

    모델이나 CLI 기본값에 기대면 이 테스트가 빨개진다 — 그게 "있는 척만 하는 설정"
    이고, 배너 쪽은 그 값이 그대로 산출물 `판정규칙` 에 찍히므로 한 겹 더 나쁘다.
    `caffeinate` 가 실제로 붙는지도 같이 본다 — 4분 12초짜리다(ENG-06 / T-3-37).
    """
    # 04-10 부터 배너 분기가 `settings.load(force=True)` 로 toml 을 새로 읽는다 —
    # 그래서 `_cache` 를 덮는 대신 **toml 자체**를 갈아끼운다(메모리 덮기는 바로 버려진다).
    _toml덮기(monkeypatch, banner_workers=3, banner_vision_revision=2,
              banner_skip_max_removal=0.75, banner_lexicon_version="zz9999-01-01")
    job_id = _배너잡(tmp_run_dir)

    av = json.loads(jobs._row(job_id)["argv"])
    assert av[av.index("--workers") + 1] == "3"
    assert av[av.index("--vision-revision") + 1] == "2"
    assert av[av.index("--skip-max-removal") + 1] == "0.75"
    assert av[av.index("--lexicon-version") + 1] == "zz9999-01-01"

    # 산출물은 조인 입력과 **같은 폴더**다 — 무엇을 넣어 무엇이 나왔나가 한 곳에 모인다.
    나온것 = Path(av[av.index("--out") + 1])
    assert 나온것.parent == (tmp_run_dir / "web")
    assert 나온것.name == f"banner_{job_id}.json"
    # `--join` 은 새로 쓴 파일이 아니라 넘긴 그 파일이다 (D-11)
    assert Path(av[av.index("--join") + 1]).name == "join_zzprev.json"

    if os.path.exists(jobs.CAFFEINATE):
        assert av[:2] == [jobs.CAFFEINATE, "-i"], "4분짜리 잡에 절전 방지가 안 붙었다"


def test_배너잡은_회차밖_파일을_안_받는다(잡판, tmp_run_dir, tmp_path):
    """대상 파일은 **회차의 `web/` 밑**이어야 한다 (`_override_targets` / ASVS V12).

    경로를 받아 그대로 믿으면 조인 산출물인 척하는 아무 파일이나 자식에게 넘어간다.
    """
    남의것 = tmp_path / "join_zz남의것.json"
    남의것.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        jobs.create_job("banner_scan", run_dir=tmp_run_dir.name,
                        targets_path_override=남의것)


def test_배너잡_비전2차_설정이_재시작_없이_반영된다(잡판, 안띄운다, tmp_run_dir, monkeypatch):
    """🔴 04-08 사고 회귀 (04-GATE §0) — 서버가 옛 설정을 메모리에 들고 있으면 안 된다.

    먼저 한 번 읽어 캐시를 **데워 둔다**(서버가 떠 있던 상태). 그 뒤 toml 만 바꾸고
    `settings.load()` 를 **수동으로 force 하지 않은 채** 다음 잡을 만든다.
    argv 가 새 값을 들고 있어야 한다 — 재시작 없이.
    """
    settings.load(force=True)            # 서버 기동 때 데워진 캐시
    _toml덮기(monkeypatch, banner_vision2_model="zz-gemini-테스트",
              banner_vision2_enabled=False, banner_vision2_max_calls=7,
              banner_vision2_prompt="v9", banner_vision2_timeout=12.5,
              banner_vision2_interval=0.9,
              banner_vision2_key_file="zz/경로만/.env")

    av = jobs._build_argv("banner_scan", "zzjob", tmp_run_dir.name, [],
                          tmp_run_dir / "web" / "join_zz.json",
                          Path("/tmp/zz-banner.json"), False)

    assert av[av.index("--vision2-model") + 1] == "zz-gemini-테스트"
    assert av[av.index("--vision2-enabled") + 1] == "off"
    assert av[av.index("--vision2-max-calls") + 1] == "7"
    assert av[av.index("--vision2-prompt") + 1] == "v9"
    assert av[av.index("--vision2-timeout") + 1] == "12.5"
    assert av[av.index("--vision2-interval") + 1] == "0.9"
    assert av[av.index("--vision2-key-file") + 1] == "zz/경로만/.env"
    # 웹앱이 넘기지 않는 CLI 전용 플래그
    assert "--vision2-estimate" not in av


def test_배너잡_argv_컬럼에_키_값이_없다(잡판, 안띄운다, tmp_run_dir):
    """🔴 T-4-40 — `jobs.argv` 는 평문 영구 저장이다. 경로만 실리고 키는 0회."""
    job_id = _배너잡(tmp_run_dir)
    원문 = jobs._row(job_id)["argv"]
    av = json.loads(원문)
    assert "--vision2-key-file" in av
    assert "GEMINI_API_KEY" not in 원문
    assert "AIza" not in 원문   # 구글 API 키 접두어


# ── 상세페이지 잡 3종 (Phase 5 / 05-03) ─────────────────────────────────────
#
# 자식을 **한 번도 띄우지 않는다**(`안띄운다`). submit 은 진짜로 돌면 크레딧을 태운다.

상세3종 = ("detail_estimate", "detail_submit", "detail_poll")


def _상세입력() -> dict:
    return {"items": [{"productId": "zzp1", "판매자상품코드": "zz01",
                       "imageUrls": ["https://zzcdn.example/1.jpg"],
                       "제품이미지총수": 1, "잘림": False}],
            "제외": [], "선택": 1}


def _끝냄(job_id: str) -> None:
    """가짜 프로세스는 영원히 도는 중이다 — 다음 쓰기 잡을 위해 행을 done 으로 닫는다."""
    import sqlite3
    jobs._PROCS.pop(job_id, None)
    cx = sqlite3.connect(jobs.db_path())
    try:
        cx.execute("UPDATE jobs SET status='done', exit_code=0 WHERE id=?", (job_id,))
        cx.commit()
    finally:
        cx.close()


def test_detail잡_kind_가_등록돼_있다():
    """`JobKind` 만 고치고 `KINDS` 를 빠뜨리면 런타임이 거부한다 — 둘 다 본다."""
    for k in 상세3종:
        assert k in jobs.KINDS
        assert k in jobs.JobKind.__args__


def test_detail잡_가드집합():
    """견적은 크레딧 0 이라 쓰기 가드 밖, 접수·이어서 확인은 안(같은 detail_status.json 을 쓴다)."""
    assert "detail_submit" in jobs.WRITE_KINDS
    assert "detail_poll" in jobs.WRITE_KINDS
    assert "detail_estimate" not in jobs.WRITE_KINDS
    for k in 상세3종:
        assert k in jobs.BULSAJA_KINDS
    assert "detail_estimate" in jobs.SINGLETON_KINDS


def test_detail잡_수면방지(monkeypatch):
    """접수·폴링은 수십 분짜리 — caffeinate. 견적은 수 초라 안 붙인다(D-15)."""
    monkeypatch.setattr(jobs.os.path, "exists", lambda p: True)
    assert jobs._수면방지_프리픽스("detail_submit") == [jobs.CAFFEINATE, "-i"]
    assert jobs._수면방지_프리픽스("detail_poll") == [jobs.CAFFEINATE, "-i"]
    assert jobs._수면방지_프리픽스("detail_estimate") == []


def test_detail잡_inputs_없으면_ValueError(tmp_path):
    """빈 값은 전량이 아니다 — inputs 없는 상세 잡은 조립조차 안 된다."""
    for k in 상세3종:
        with pytest.raises(ValueError) as 터진것:
            jobs._build_argv(k, "zzjob", "2026-08-30", [], None,
                             tmp_path / "zz.json", False,
                             detail_dir=tmp_path, max_credits=10)
        assert "inputs" in str(터진것.value)


def test_detail잡_submit_max_credits_없으면_ValueError(tmp_path, 기대닉):
    with pytest.raises(ValueError):
        jobs._build_argv("detail_submit", "zzjob", "2026-08-30", [],
                         tmp_path / "t.json", tmp_path / "s.json", False,
                         detail_dir=tmp_path, max_credits=None)


def test_detail잡_submit_만_backup_out(tmp_path, 기대닉):
    """06-01 · D-03 — detail_submit 은 <detail_dir>/before_detail, estimate·poll 은 없음."""
    for kind in 상세3종:
        av = jobs._build_argv(kind, "zzjob", "2026-08-30", [],
                              tmp_path / "t.json", tmp_path / "s.json", False,
                              detail_dir=tmp_path / "detail_zz", max_credits=10)
        if kind == "detail_submit":
            assert av[av.index("--backup-out") + 1] == str(tmp_path / "detail_zz"
                                                           / "before_detail")
        else:
            assert "--backup-out" not in av


def test_detail견적잡은_inputs_dict_가_없으면_안_만들어진다(잡판, 계정확인, 기대닉, 안띄운다,
                                                    tmp_run_dir):
    계정확인(기대닉)
    with pytest.raises(ValueError):
        jobs.create_job("detail_estimate", run_dir=tmp_run_dir.name)


def test_detail잡_argv_가_설정에서_온다(잡판, 계정확인, 안띄운다, tmp_run_dir, monkeypatch):
    """--expect-nick · --done-tag · --max-poll-min · --poll-interval 이 workspace.toml 에서 온다."""
    _toml덮기(monkeypatch, expected_bulsaja_nick="zz설정계정",
              done_tags=["zz태그1", "zz태그2"], detail_max_poll_min=17,
              detail_poll_interval=9)
    settings.load(force=True)
    계정확인("zz설정계정")
    job_id = jobs.create_job("detail_estimate", run_dir=tmp_run_dir.name,
                             detail_inputs=_상세입력())
    av = json.loads(jobs._row(job_id)["argv"])
    assert av[av.index("--expect-nick") + 1] == "zz설정계정"
    태그 = [av[i + 1] for i, x in enumerate(av) if x == "--done-tag"]
    assert 태그 == ["zz태그1", "zz태그2"]
    assert av[av.index("--max-poll-min") + 1] == "17"
    assert av[av.index("--poll-interval") + 1] == "9"
    assert "--estimate-only" in av
    assert av[0] != jobs.CAFFEINATE


def test_detail잡_기본값():
    assert settings.DEFAULTS["detail_max_poll_min"] == 60
    assert settings.DEFAULTS["detail_poll_interval"] == 45


def test_detail잡_폴더_규칙(잡판, 계정확인, 안띄운다, tmp_run_dir, monkeypatch):
    """estimate 가 web/detail_<id>/ 를 열고, submit·poll 은 parent 체인으로 같은 폴더를 받는다."""
    # `_build_argv` 가 설정을 새로 읽으므로(`load(force=True)`) 메모리 덮기가 아니라 toml 을 덮는다.
    _toml덮기(monkeypatch, expected_bulsaja_nick="zz기대계정")
    settings.load(force=True)
    계정확인("zz기대계정")
    견적 = jobs.create_job("detail_estimate", run_dir=tmp_run_dir.name,
                           detail_inputs=_상세입력())
    폴더 = tmp_run_dir / "web" / f"detail_{견적}"
    av = json.loads(jobs._row(견적)["argv"])
    assert Path(av[av.index("--run-dir") + 1]) == 폴더
    assert 폴더.is_dir()
    대상 = Path(av[av.index("--inputs") + 1])
    assert 대상 == tmp_run_dir / "web" / f"targets_{견적}.json"
    assert json.loads(대상.read_text(encoding="utf-8"))["items"][0]["productId"] == "zzp1"
    assert jobs.result_path_of(견적) == 폴더 / "estimate.json"
    assert jobs._row(견적)["target_count"] == 1          # {"items":[…]} 모양도 센다
    _끝냄(견적)

    접수 = jobs.create_job("detail_submit", run_dir=tmp_run_dir.name,
                           parent_job_id=견적, targets_path_override=대상,
                           max_credits=5)
    av2 = json.loads(jobs._row(접수)["argv"])
    assert Path(av2[av2.index("--run-dir") + 1]) == 폴더
    assert av2[av2.index("--max-credits") + 1] == "5"
    assert jobs.result_path_of(접수) == 폴더 / f"summary_{접수}.json"
    _끝냄(접수)

    확인 = jobs.create_job("detail_poll", run_dir=tmp_run_dir.name,
                           parent_job_id=접수, targets_path_override=대상)
    av3 = json.loads(jobs._row(확인)["argv"])
    assert Path(av3[av3.index("--run-dir") + 1]) == 폴더
    assert "--poll-only" in av3


def test_detail잡_부모체인이_틀리면_거부(잡판, 계정확인, 안띄운다, tmp_run_dir, monkeypatch):
    """submit 의 부모가 견적이 아니면(없거나 다른 kind) ValueError — 폴더를 지어내지 않는다."""
    _toml덮기(monkeypatch, expected_bulsaja_nick="zz기대계정")
    settings.load(force=True)
    계정확인("zz기대계정")
    견적 = jobs.create_job("detail_estimate", run_dir=tmp_run_dir.name,
                           detail_inputs=_상세입력())
    _끝냄(견적)
    대상 = jobs.targets_path_of(견적)
    with pytest.raises(ValueError):
        jobs.create_job("detail_submit", run_dir=tmp_run_dir.name,
                        targets_path_override=대상, max_credits=5)
    with pytest.raises(ValueError):
        jobs.create_job("detail_poll", run_dir=tmp_run_dir.name,
                        parent_job_id=견적, targets_path_override=대상)


# ── Phase 5 · 05-04 — detail 잡의 exit 3 해석 (L-03 · D-17) ─────────────────
# 3 은 "폴링 미완 — 실패 아님" 이다. failed 로 적으면 사람이 실패로 읽고 다시 접수한다(이중 지불).

class _끝난프로세스:
    """`poll()` 이 정해진 종료코드를 돌려주는 대역. 자식을 띄우지 않는다."""

    def __init__(self, code):
        self.code = code
        self.pid = os.getpid()

    def poll(self):
        return self.code


def _도는행(kind: str, code: int) -> str:
    """running 행 하나 + 끝난 가짜 프로세스를 박는다. `_reap` 이 거두게 한다."""
    import sqlite3
    job_id = str(uuid.uuid4())
    cx = sqlite3.connect(jobs.db_path())
    try:
        cx.execute("INSERT INTO jobs (id, kind, accounts, argv, status, log_path, pid, started_at) "
                   "VALUES (?,?,?,?,?,?,?,?)",
                   (job_id, kind, "[]", "[]", "running", "x.log", os.getpid(),
                    datetime.now().astimezone().isoformat(timespec="seconds")))
        cx.commit()
    finally:
        cx.close()
    jobs._PROCS[job_id] = _끝난프로세스(code)
    return job_id


@pytest.mark.parametrize("kind", ["detail_submit", "detail_poll"])
def test_detail_exit3_은_done(잡판, kind):
    상태 = jobs.job_status(_도는행(kind, 3))
    assert 상태["status"] == "done"
    assert 상태["exit_code"] == 3


@pytest.mark.parametrize("kind", ["bids_commit", "detail_estimate", "bulsaja_scan", "prep"])
def test_detail_아닌_kind_의_exit3_은_여전히_failed(잡판, kind):
    상태 = jobs.job_status(_도는행(kind, 3))
    assert 상태["status"] == "failed"
    assert 상태["exit_code"] == 3


@pytest.mark.parametrize("code", [2, 4, 5, 1])
def test_detail_의_2_4_5_는_failed(잡판, code):
    상태 = jobs.job_status(_도는행("detail_submit", code))
    assert 상태["status"] == "failed"
    assert 상태["exit_code"] == code


def test_detail_exit3_은_latest_done_에_잡힌다(잡판):
    """새 상태값을 만들지 않았다는 증거 — 'done' 을 보는 기존 쿼리가 그대로 잡는다."""
    job_id = _도는행("detail_poll", 3)
    jobs.job_status(job_id)
    assert jobs.latest_done("detail_poll")["id"] == job_id


# ── Phase 6 · 06-03 — 마켓 수정업로드 잡 3종 ───────────────────────────────
# 자식을 **한 번도 띄우지 않는다**(`안띄운다`). market_commit 은 진짜로 돌면 스토어를 바꾼다.

마켓3종 = ("market_preview", "market_commit", "market_poll")


def test_market잡_kind_가_등록돼_있다():
    for k in 마켓3종:
        assert k in jobs.KINDS
        assert k in jobs.JobKind.__args__


def test_market잡_가드집합():
    """반영·이어서 확인은 쓰기(같은 market_status.json), 미리보기는 쓰기 0 이라 밖."""
    assert {"market_commit", "market_poll"} <= jobs.WRITE_KINDS
    assert "market_preview" not in jobs.WRITE_KINDS
    for k in 마켓3종:
        assert k in jobs.BULSAJA_KINDS
    assert "market_preview" in jobs.SINGLETON_KINDS
    assert {"market_commit", "market_poll"} <= jobs.POLL_INCOMPLETE_OK_KINDS
    assert "market_preview" not in jobs.POLL_INCOMPLETE_OK_KINDS


def test_market잡_수면방지(monkeypatch):
    monkeypatch.setattr(jobs.os.path, "exists", lambda p: True)
    assert jobs._수면방지_프리픽스("market_commit") == [jobs.CAFFEINATE, "-i"]
    assert jobs._수면방지_프리픽스("market_poll") == [jobs.CAFFEINATE, "-i"]
    assert jobs._수면방지_프리픽스("market_preview") == []


@pytest.mark.parametrize("kind", ["market_commit", "market_poll"])
def test_market_exit3_은_done(잡판, kind):
    상태 = jobs.job_status(_도는행(kind, 3))
    assert 상태["status"] == "done" and 상태["exit_code"] == 3


def test_market_preview_exit3_은_failed(잡판):
    상태 = jobs.job_status(_도는행("market_preview", 3))
    assert 상태["status"] == "failed"


def test_market잡_build_argv_빈값_거부(tmp_path, 기대닉):
    """targets 없음 · commit 상한 없음 → ValueError (빈 값은 전량이 아니다)."""
    공통 = dict(market_dir=tmp_path / "market_a",
              detail_backup_dir=tmp_path / "detail_d" / "before_detail")
    with pytest.raises(ValueError):
        jobs._build_argv("market_preview", "zzjob", "2026-08-30", [], None,
                         tmp_path / "p.json", False, **공통)
    with pytest.raises(ValueError):
        jobs._build_argv("market_commit", "zzjob", "2026-08-30", [], tmp_path / "t.json",
                         tmp_path / "s.json", False, max_items=None, **공통)
    av = jobs._build_argv("market_commit", "zzjob", "2026-08-30", [], tmp_path / "t.json",
                          tmp_path / "s.json", False, max_items=1, **공통)
    assert av[av.index("--max-items") + 1] == "1"
    assert av[av.index("--backup-dir") + 1] == str(tmp_path / "market_a" / "before_market")
    assert av[av.index("--detail-backup-dir") + 1] == str(tmp_path / "detail_d"
                                                          / "before_detail")


def _상세체인(run_name: str) -> tuple[str, str, Path]:
    """견적 → 접수 잡을 만들고 (견적id, 접수id, 대상파일) 을 돌려준다."""
    견적 = jobs.create_job("detail_estimate", run_dir=run_name, detail_inputs=_상세입력())
    _끝냄(견적)
    대상 = jobs.targets_path_of(견적)
    접수 = jobs.create_job("detail_submit", run_dir=run_name, parent_job_id=견적,
                           targets_path_override=대상, max_credits=5)
    _끝냄(접수)
    return 견적, 접수, 대상


def _마켓대상() -> dict:
    return {"items": [{"productId": "zzp1", "판매자상품코드": "zz01"}]}


def test_market잡_폴더_체인(잡판, 계정확인, 안띄운다, tmp_run_dir, monkeypatch):
    """preview 가 market_<미리보기id>/ 를 열고 commit·poll 이 체인으로 같은 폴더를 받는다.
    ⓐ 폴더는 부모 detail 잡의 detail_<견적id>/before_detail 이다."""
    _toml덮기(monkeypatch, expected_bulsaja_nick="zz기대계정")
    settings.load(force=True)
    계정확인("zz기대계정")
    견적, 접수, _ = _상세체인(tmp_run_dir.name)
    web = tmp_run_dir / "web"

    미리 = jobs.create_job("market_preview", run_dir=tmp_run_dir.name, parent_job_id=접수,
                           detail_inputs=_마켓대상())
    폴더 = web / f"market_{미리}"
    av = json.loads(jobs._row(미리)["argv"])
    assert Path(av[av.index("--run-dir") + 1]) == 폴더
    assert av[av.index("--detail-backup-dir") + 1] == str(web / f"detail_{견적}"
                                                          / "before_detail")
    assert av[av.index("--backup-dir") + 1] == str(폴더 / "before_market")
    assert jobs.result_path_of(미리) == 폴더 / "preview.json"
    대상 = Path(av[av.index("--targets") + 1])
    assert 대상 == web / f"targets_{미리}.json"
    assert json.loads(대상.read_text(encoding="utf-8"))["items"][0]["productId"] == "zzp1"
    _끝냄(미리)

    반영 = jobs.create_job("market_commit", run_dir=tmp_run_dir.name, parent_job_id=미리,
                           detail_inputs=_마켓대상(), max_items=1)
    av2 = json.loads(jobs._row(반영)["argv"])
    assert Path(av2[av2.index("--run-dir") + 1]) == 폴더
    assert av2[av2.index("--max-items") + 1] == "1"
    assert jobs.result_path_of(반영) == 폴더 / f"summary_{반영}.json"
    _끝냄(반영)

    확인 = jobs.create_job("market_poll", run_dir=tmp_run_dir.name, parent_job_id=반영,
                           targets_path_override=jobs.targets_path_of(반영))
    av3 = json.loads(jobs._row(확인)["argv"])
    assert Path(av3[av3.index("--run-dir") + 1]) == 폴더
    assert "--poll-only" in av3
    _끝냄(확인)
    # poll 의 부모가 poll 이어도 같은 폴더
    확인2 = jobs.create_job("market_poll", run_dir=tmp_run_dir.name, parent_job_id=확인,
                            targets_path_override=jobs.targets_path_of(반영))
    av4 = json.loads(jobs._row(확인2)["argv"])
    assert Path(av4[av4.index("--run-dir") + 1]) == 폴더


def test_market잡_부모체인이_틀리면_거부(잡판, 계정확인, 안띄운다, tmp_run_dir, monkeypatch):
    _toml덮기(monkeypatch, expected_bulsaja_nick="zz기대계정")
    settings.load(force=True)
    계정확인("zz기대계정")
    견적, 접수, _ = _상세체인(tmp_run_dir.name)
    # preview 부모가 견적(detail_estimate) → 거부
    with pytest.raises(ValueError):
        jobs.create_job("market_preview", run_dir=tmp_run_dir.name, parent_job_id=견적,
                        detail_inputs=_마켓대상())
    # 부모 없음 → 거부
    with pytest.raises(ValueError):
        jobs.create_job("market_preview", run_dir=tmp_run_dir.name, detail_inputs=_마켓대상())
    # commit 부모가 detail_submit → 거부
    with pytest.raises(ValueError):
        jobs.create_job("market_commit", run_dir=tmp_run_dir.name, parent_job_id=접수,
                        detail_inputs=_마켓대상(), max_items=1)
    미리 = jobs.create_job("market_preview", run_dir=tmp_run_dir.name, parent_job_id=접수,
                           detail_inputs=_마켓대상())
    _끝냄(미리)
    # poll 부모가 preview → 거부
    with pytest.raises(ValueError):
        jobs.create_job("market_poll", run_dir=tmp_run_dir.name, parent_job_id=미리,
                        targets_path_override=jobs.targets_path_of(미리))
    # 회차가 다르면 거부
    다른 = tmp_run_dir.parent / "2026-08-31"
    다른.mkdir()
    (다른 / "result.json").write_text((tmp_run_dir / "result.json").read_text(encoding="utf-8"),
                                      encoding="utf-8")
    with pytest.raises(ValueError):
        jobs.create_job("market_preview", run_dir="2026-08-31", parent_job_id=접수,
                        detail_inputs=_마켓대상())


def test_market잡_기본값():
    assert settings.DEFAULTS["market_update_max_items"] == 20
    assert settings.DEFAULTS["market_poll_interval"] == 20
    assert settings.DEFAULTS["market_max_poll_min"] == 30


# ── Phase 7 · 07-01 — 썸네일 견적 · 쿠팡 후보/복사 잡 3종 ─────────────────────
# 자식을 **한 번도 띄우지 않는다**(`안띄운다`). coupang_commit 은 진짜로 돌면 불사자에 사본을 만든다.
# data_root 를 반드시 tmp 로 돌린다 — 안 돌리면 러너 폴더가 실제 ~/python_work/data 밑에 생긴다.

칠단계3종 = ("thumb_estimate", "coupang_preview", "coupang_commit")


@pytest.fixture
def 칠판(잡판, 계정확인, 안띄운다, monkeypatch, tmp_path):
    """계정 확인 통과 + data_root tmp. (tmp 루트를 돌려준다)"""
    _toml덮기(monkeypatch, expected_bulsaja_nick="zz기대계정")
    settings.load(force=True)
    계정확인("zz기대계정")
    # data_root 자체를 돌리면 광고 회차(tmp_run_dir)까지 딸려 간다 — 러너 뿌리 둘만 돌린다.
    뿌리 = tmp_path / "data"
    monkeypatch.setattr(paths, "thumb_runs_root", lambda: 뿌리 / "thumbnail" / "runs")
    monkeypatch.setattr(paths, "coupang_runs_root", lambda: 뿌리 / "coupang" / "runs")
    return 뿌리


def _썸네일입력() -> dict:
    return {"그룹": {"zz1-1 테스트그룹": ["zzp1", "zzp2"]}, "코드": {"zzp1": "zz01", "zzp2": "zz02"}}


def _쿠팡미리보기끝(code: int = 0, status: str = "done") -> str:
    미리 = jobs.create_job("coupang_preview")
    import sqlite3
    jobs._PROCS.pop(미리, None)
    cx = sqlite3.connect(jobs.db_path())
    try:
        cx.execute("UPDATE jobs SET status=?, exit_code=? WHERE id=?", (status, code, 미리))
        cx.commit()
    finally:
        cx.close()
    return 미리


def test_phase7_kind_가_등록돼_있다():
    for k in 칠단계3종:
        assert k in jobs.KINDS
        assert k in jobs.JobKind.__args__


def test_phase7_가드집합():
    """복사만 쓰기(되돌릴 수 없다 · D-11). 셋 다 계정 사전점검(L-05). exit3 은 폴링미완이 아니다."""
    assert "coupang_commit" in jobs.WRITE_KINDS
    assert "thumb_estimate" not in jobs.WRITE_KINDS
    assert "coupang_preview" not in jobs.WRITE_KINDS
    for k in 칠단계3종:
        assert k in jobs.BULSAJA_KINDS
        assert k not in jobs.POLL_INCOMPLETE_OK_KINDS
    assert {"thumb_estimate", "coupang_preview"} <= jobs.SINGLETON_KINDS
    assert "coupang_commit" not in jobs.SINGLETON_KINDS


def test_phase7_수면방지(monkeypatch):
    monkeypatch.setattr(jobs.os.path, "exists", lambda p: True)
    for k in 칠단계3종:
        assert jobs._수면방지_프리픽스(k) == [jobs.CAFFEINATE, "-i"]


@pytest.mark.parametrize("kind", 칠단계3종)
def test_phase7_exit3_은_failed(잡판, kind):
    """러너 3 = 쿠팡 그룹 부분 읽기 실패 등 재시도 필요 — 폴링미완(done)이 아니다(D-17)."""
    상태 = jobs.job_status(_도는행(kind, 3))
    assert 상태["status"] == "failed" and 상태["exit_code"] == 3


def test_thumb_견적_그룹_0개는_거부(칠판, tmp_run_dir):
    with pytest.raises(ValueError):
        jobs.create_job("thumb_estimate", run_dir=tmp_run_dir.name, thumb_inputs={"그룹": {}})
    with pytest.raises(ValueError):
        jobs.create_job("thumb_estimate", run_dir=tmp_run_dir.name, thumb_inputs=None)
    with pytest.raises(ValueError):
        jobs.create_job("thumb_estimate", run_dir=tmp_run_dir.name,
                        thumb_inputs={"그룹": {"zz그룹": []}})
    assert _행수() == 0


def test_thumb_inputs_는_다른_kind_에_못_준다(칠판):
    with pytest.raises(ValueError):
        jobs.create_job("coupang_preview", thumb_inputs=_썸네일입력())


def test_thumb_견적_argv_와_폴더(칠판, tmp_run_dir, monkeypatch):
    잡 = jobs.create_job("thumb_estimate", run_dir=tmp_run_dir.name, thumb_inputs=_썸네일입력())
    폴더 = 칠판 / "thumbnail" / "runs" / f"web-{잡}"
    assert jobs.thumb_dir_of(잡) == 폴더
    av = json.loads(jobs._row(잡)["argv"])
    i = av.index(str(jobs.argv.PY_CLI))
    assert av[i + 1] == str(jobs.argv.THUMB_WEB) and av[i + 2] == "estimate"
    assert Path(av[av.index("--run-dir") + 1]) == 폴더
    assert Path(av[av.index("--inputs") + 1]) == 폴더 / "inputs.json"
    assert av[av.index("--expect-nick") + 1] == "zz기대계정"
    assert jobs.result_path_of(잡) == 폴더 / "summary.json"
    assert json.loads((폴더 / "inputs.json").read_text(encoding="utf-8")) == _썸네일입력()
    assert jobs._row(잡)["run_dir"] == tmp_run_dir.name


def test_쿠팡_미리보기_run_dir_칸은_비고_폴더는_자기id(칠판):
    미리 = jobs.create_job("coupang_preview")
    폴더 = 칠판 / "coupang" / "runs" / f"web-{미리}"
    행 = jobs._row(미리)
    assert 행["run_dir"] is None
    av = json.loads(행["argv"])
    assert "preview" in av
    assert Path(av[av.index("--run-dir") + 1]) == 폴더
    assert jobs.result_path_of(미리) == 폴더 / "summary.json"
    assert "--limit" not in av and "--approved" not in av


def test_쿠팡잡에_회차를_주면_거부(칠판, tmp_run_dir):
    with pytest.raises(ValueError):
        jobs.create_job("coupang_preview", run_dir=tmp_run_dir.name)


def test_쿠팡_복사_argv_상한_승인목록(칠판):
    미리 = _쿠팡미리보기끝()
    복사 = jobs.create_job("coupang_commit", parent_job_id=미리,
                           coupang_approved=["zzp1", "zzp2"], copy_limit=10)
    폴더 = jobs.coupang_dir_of(미리)
    av = json.loads(jobs._row(복사)["argv"])
    assert "commit" in av
    assert av[av.index("--limit") + 1] == "10"
    승인 = Path(av[av.index("--approved") + 1])
    assert 승인 == 폴더 / f"approved_{복사}.json"
    assert json.loads(승인.read_text(encoding="utf-8")) == ["zzp1", "zzp2"]
    assert Path(av[av.index("--run-dir") + 1]) == 폴더
    assert jobs.result_path_of(복사) == 폴더 / f"commit_summary_{복사}.json"
    assert jobs._row(복사)["run_dir"] is None


@pytest.mark.parametrize("덮기", [
    dict(copy_limit=None), dict(copy_limit=0), dict(copy_limit=True), dict(copy_limit=-1),
    dict(coupang_approved=[]), dict(coupang_approved=None), dict(coupang_approved=[""]),
])
def test_쿠팡_복사는_상한_승인목록_없이_안_만들어진다(칠판, 덮기):
    """빈 값은 전량이 아니다 (D-13 · T-07-02)."""
    미리 = _쿠팡미리보기끝()
    인자 = dict(parent_job_id=미리, coupang_approved=["zzp1"], copy_limit=5)
    인자.update(덮기)
    전 = _행수()
    with pytest.raises(ValueError):
        jobs.create_job("coupang_commit", **인자)
    assert _행수() == 전


def test_쿠팡_복사_부모가_틀리면_거부(칠판, tmp_run_dir):
    # 부모 없음
    with pytest.raises(ValueError):
        jobs.create_job("coupang_commit", coupang_approved=["zzp1"], copy_limit=5)
    # 부모 미완(running)
    도는 = jobs.create_job("coupang_preview")
    with pytest.raises(ValueError):
        jobs.create_job("coupang_commit", parent_job_id=도는, coupang_approved=["zzp1"],
                        copy_limit=5)
    jobs._PROCS.pop(도는, None)
    # 부모 실패
    실패 = _쿠팡미리보기끝(code=2, status="failed")
    with pytest.raises(ValueError):
        jobs.create_job("coupang_commit", parent_job_id=실패, coupang_approved=["zzp1"],
                        copy_limit=5)
    # 부모 kind 가 다름
    썸 = jobs.create_job("thumb_estimate", run_dir=tmp_run_dir.name, thumb_inputs=_썸네일입력())
    _끝냄(썸)
    with pytest.raises(ValueError):
        jobs.create_job("coupang_commit", parent_job_id=썸, coupang_approved=["zzp1"],
                        copy_limit=5)


def test_copy_limit_은_다른_kind_에_못_준다(칠판):
    with pytest.raises(ValueError):
        jobs.create_job("coupang_preview", copy_limit=5)


def test_coupang_build_argv_상한_None_거부(tmp_path, 기대닉):
    with pytest.raises(ValueError, match="상한 없는 복사는 없다"):
        jobs._build_argv("coupang_commit", "zzjob", None, [], None, tmp_path / "s.json", False,
                         coupang_dir=tmp_path, approved_path=tmp_path / "a.json", copy_limit=None)


def test_폴더_유도는_잡id_모양만_받는다():
    for 나쁜 in ("../x", "zz", "", "a/b"):
        with pytest.raises(ValueError):
            jobs.coupang_dir_of(나쁜)
        with pytest.raises(ValueError):
            jobs.thumb_dir_of(나쁜)


def test_first_coupang_commit_done_은_디비를_만들지_않는다(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "없음.db"))
    assert jobs.first_coupang_commit_done() is False
    assert not (tmp_path / "없음.db").exists()


def test_first_coupang_commit_done_은_성공한_복사만_본다(잡판):
    assert jobs.first_coupang_commit_done() is False
    jobs.job_status(_도는행("coupang_commit", 2))        # failed
    assert jobs.first_coupang_commit_done() is False
    jobs.job_status(_도는행("coupang_preview", 0))       # 다른 kind done
    assert jobs.first_coupang_commit_done() is False
    jobs.job_status(_도는행("coupang_commit", 0))        # done/0
    assert jobs.first_coupang_commit_done() is True


class _가짜ps:
    def __init__(self, stat=None, 터짐=False):
        self.stat, self.터짐, self.불림 = stat, 터짐, []

    def __call__(self, cmd, **kw):
        self.불림.append(cmd)
        if self.터짐:
            raise OSError("ps 없음")
        return subprocess.CompletedProcess(cmd, 0, stdout=self.stat, stderr="")


@pytest.mark.parametrize("stat, 기대", [("Z+\n", False), ("Z\n", False), ("S\n", True),
                                        ("R+\n", True), ("", True)])
def test_좀비_판정(monkeypatch, stat, 기대):
    """좀비는 kill(0) 이 성공해도 죽은 것이다 — 가드를 영원히 잡지 않게(T-07-04)."""
    monkeypatch.setattr(jobs.os, "kill", lambda pid, sig: None)
    가짜 = _가짜ps(stat)
    monkeypatch.setattr(jobs.subprocess, "run", 가짜)
    assert jobs._alive(12345) is 기대
    assert 가짜.불림 and 가짜.불림[0][:3] == ["ps", "-o", "stat="]


def test_좀비_판정_ps_예외면_살아있다고_본다(monkeypatch):
    monkeypatch.setattr(jobs.os, "kill", lambda pid, sig: None)
    monkeypatch.setattr(jobs.subprocess, "run", _가짜ps(터짐=True))
    assert jobs._alive(12345) is True


def test_좀비_판정은_waitpid_를_쓰지_않는다():
    """거두면 Popen.poll 이 ECHILD → returncode 0 으로 오기록한다(RESEARCH A1)."""
    import inspect
    본문 = inspect.getsource(jobs._alive)
    코드줄 = [l for l in 본문.splitlines() if "waitpid" in l and "금지" not in l]
    assert not 코드줄


# ── Phase 2 · 02-02 — 꺼진 소재 정리 잡 2종 (prune_preview · prune_commit) ──────
# 자식을 **한 번도 띄우지 않는다**(`안띄운다`). prune_commit 은 진짜로 돌면 소재를 DELETE 한다.

def _prune미리보기끝(run_dir: str, code: int = 0, status: str = "done") -> str:
    """성공한 미리보기 잡 하나 + 그 산출물 파일(다음 --only-ads 입력)."""
    미리 = jobs.create_job("prune_preview", run_dir=run_dir, accounts=["zz1"])
    산출 = jobs.result_path_of(미리)
    산출.write_text(json.dumps({"adIds": ["nad-1", "nad-2"], "accounts": {}}), encoding="utf-8")
    import sqlite3
    jobs._PROCS.pop(미리, None)
    cx = sqlite3.connect(jobs.db_path())
    try:
        cx.execute("UPDATE jobs SET status=?, exit_code=? WHERE id=?", (status, code, 미리))
        cx.commit()
    finally:
        cx.close()
    return 미리


def test_prune_kind_가_등록돼_있다():
    for k in ("prune_preview", "prune_commit"):
        assert k in jobs.KINDS
        assert k in jobs.JobKind.__args__
        assert k not in jobs.BULSAJA_KINDS
    assert "prune_commit" in jobs.WRITE_KINDS
    assert "prune_preview" not in jobs.WRITE_KINDS
    assert "prune_preview" in jobs.SINGLETON_KINDS


def test_prune_수면방지_caffeinate(monkeypatch):
    monkeypatch.setattr(jobs.os.path, "exists", lambda p: True)
    assert jobs._수면방지_프리픽스("prune_commit") == [jobs.CAFFEINATE, "-i"]
    assert jobs._수면방지_프리픽스("prune_preview") == []


def test_prune_build_argv_대상_상한_없으면_거부(tmp_path):
    with pytest.raises(ValueError, match="대상 파일"):
        jobs._build_argv("prune_commit", "zzjob", "2026-08-30", [], None, tmp_path / "r.json",
                         True, prune_max_items=8000)
    with pytest.raises(ValueError, match="상한"):
        jobs._build_argv("prune_commit", "zzjob", "2026-08-30", [], tmp_path / "t.json",
                         tmp_path / "r.json", True, prune_max_items=None)


def test_prune_미리보기_argv(잡판, 안띄운다, tmp_run_dir):
    미리 = jobs.create_job("prune_preview", run_dir=tmp_run_dir.name, accounts=["zz1"])
    av = json.loads(jobs._row(미리)["argv"])
    산출 = tmp_run_dir / "web" / f"prune_preview_{미리}.json"
    assert jobs.result_path_of(미리) == 산출
    assert "prune" in av
    assert av[av.index("--preview-out") + 1] == str(산출)
    assert av[av.index("--backup-tag") + 1] == 미리
    assert ("--" + "commit") not in av
    assert "--only-ads" not in av and "--max-items" not in av
    assert av[0] != jobs.CAFFEINATE


def test_prune_커밋_argv_는_미리보기_산출물을_그대로_쓴다(잡판, 안띄운다, tmp_run_dir, monkeypatch):
    monkeypatch.setattr(jobs.os.path, "exists", lambda p: True)
    미리 = _prune미리보기끝(tmp_run_dir.name)
    커밋 = jobs.create_job("prune_commit", run_dir=tmp_run_dir.name, accounts=["zz1"],
                           parent_job_id=미리, prune_max_items=8000,
                           targets_path_override=jobs.result_path_of(미리))
    av = json.loads(jobs._row(커밋)["argv"])
    assert av[:2] == [jobs.CAFFEINATE, "-i"]
    assert ("--" + "commit") in av
    assert Path(av[av.index("--only-ads") + 1]) == jobs.result_path_of(미리).resolve()
    assert av[av.index("--max-items") + 1] == "8000"
    assert av[av.index("--backup-tag") + 1] == 커밋
    assert jobs.result_path_of(커밋) == tmp_run_dir / "web" / f"prune_result_{커밋}.json"
    assert jobs._row(커밋)["target_count"] == 2


def test_prune_재시도는_부분집합_파일을_쓴다(잡판, 안띄운다, tmp_run_dir):
    미리 = _prune미리보기끝(tmp_run_dir.name)
    커밋 = jobs.create_job("prune_commit", run_dir=tmp_run_dir.name, accounts=["zz1"],
                           parent_job_id=미리, prune_max_items=10,
                           only_ads=["a", "b"], prune_retry=True)
    av = json.loads(jobs._row(커밋)["argv"])
    대상 = Path(av[av.index("--only-ads") + 1])
    assert 대상 == tmp_run_dir / "web" / f"targets_{커밋}.json"
    assert json.loads(대상.read_text(encoding="utf-8")) == ["a", "b"]


@pytest.mark.parametrize("상한", [None, 0, -1, True, "8000"])
def test_prune_커밋은_상한_없이_안_만들어진다(잡판, 안띄운다, tmp_run_dir, 상한):
    미리 = _prune미리보기끝(tmp_run_dir.name)
    전 = _행수()
    with pytest.raises(ValueError):
        jobs.create_job("prune_commit", run_dir=tmp_run_dir.name, parent_job_id=미리,
                        prune_max_items=상한, targets_path_override=jobs.result_path_of(미리))
    assert _행수() == 전


def test_prune_커밋은_대상_없이_안_만들어진다(잡판, 안띄운다, tmp_run_dir):
    미리 = _prune미리보기끝(tmp_run_dir.name)
    with pytest.raises(ValueError):
        jobs.create_job("prune_commit", run_dir=tmp_run_dir.name, parent_job_id=미리,
                        prune_max_items=10)


def test_prune_커밋_부모가_틀리면_거부(잡판, 안띄운다, tmp_run_dir):
    좋은 = _prune미리보기끝(tmp_run_dir.name)
    대상 = jobs.result_path_of(좋은)
    인자 = dict(run_dir=tmp_run_dir.name, prune_max_items=10, targets_path_override=대상)
    with pytest.raises(ValueError):                                   # 부모 없음
        jobs.create_job("prune_commit", **인자)
    with pytest.raises(ValueError):                                   # 부모 실패
        jobs.create_job("prune_commit", parent_job_id=_prune미리보기끝(
            tmp_run_dir.name, code=2, status="failed"), **인자)
    다른 = jobs.create_job("bids_preview", run_dir=tmp_run_dir.name, only_ads=["x"])
    _끝냄(다른)
    with pytest.raises(ValueError):                                   # 부모 kind 다름
        jobs.create_job("prune_commit", parent_job_id=다른, **인자)


def test_prune_같은_미리보기_두번째_커밋은_409(잡판, 안띄운다, tmp_run_dir):
    """ENG-04 · D-09 — DB 트랜잭션 안에서 본다. 재시도 표시만 예외다."""
    미리 = _prune미리보기끝(tmp_run_dir.name)
    인자 = dict(run_dir=tmp_run_dir.name, parent_job_id=미리, prune_max_items=10)
    첫 = jobs.create_job("prune_commit", targets_path_override=jobs.result_path_of(미리), **인자)
    _끝냄(첫)
    with pytest.raises(jobs.BusyError, match="이미 삭제했다"):
        jobs.create_job("prune_commit", targets_path_override=jobs.result_path_of(미리), **인자)
    재시도 = jobs.create_job("prune_commit", only_ads=["nad-2"], prune_retry=True, **인자)
    assert jobs._row(재시도)["parent_job_id"] == 미리


def test_prune_재시도도_도는_쓰기잡이_있으면_409(잡판, 안띄운다, tmp_run_dir):
    미리 = _prune미리보기끝(tmp_run_dir.name)
    인자 = dict(run_dir=tmp_run_dir.name, parent_job_id=미리, prune_max_items=10)
    jobs.create_job("prune_commit", targets_path_override=jobs.result_path_of(미리), **인자)
    with pytest.raises(jobs.BusyError):
        jobs.create_job("prune_commit", only_ads=["nad-2"], prune_retry=True, **인자)


def test_prune_전용_인자는_다른_kind_에_못_준다(잡판, 안띄운다, tmp_run_dir):
    with pytest.raises(ValueError):
        jobs.create_job("bids_preview", run_dir=tmp_run_dir.name, only_ads=["x"],
                        prune_max_items=10)
    with pytest.raises(ValueError):
        jobs.create_job("bids_preview", run_dir=tmp_run_dir.name, only_ads=["x"],
                        prune_retry=True)
    with pytest.raises(ValueError):
        jobs.create_job("prune_preview", run_dir=tmp_run_dir.name, prune_max_items=10)
