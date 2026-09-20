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
import sys
import time
import uuid
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


def test_보드캐시와_대상별락_테이블을_만들지_않는다(잡판):
    """스키마는 jobs 하나뿐이다.

    보드는 매번 `result.json` 을 투영한다(캐시를 두면 진실이 둘이 된다).
    대상별 잠금 테이블은 Phase 2(ENG-04) — 지금 만들면 안 쓰는 스키마가 굳는다.
    """
    import sqlite3
    cx = sqlite3.connect(jobs.db_path())
    이름들 = {r[0] for r in cx.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    cx.close()
    assert "jobs" in 이름들
    assert 이름들 - {"jobs"} == set(), f"예상 밖 테이블: {이름들}"


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
