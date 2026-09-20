#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""작업(잡) 엔진 — CLI 를 자식 프로세스로 띄우고 그 생사를 SQLite 에 적는다.

**이 모듈은 HTTP 를 모른다.** 웹 프레임워크를 import 하지 않고, 요청 객체도 받지 않는다.
`create_job()` 은 그냥 부를 수 있는 함수고, 라우트는 그걸 얇게 감싸기만 한다 (D-17 / ENG-07).
v2 의 APScheduler 가 **같은 함수**를 부를 것이기 때문이다 — 스케줄러가 자기 서버에
HTTP 요청을 쏘는 모양이 되면 그때 다시 짜야 한다.

작업 종류와 위험도:

| kind           | 서브커맨드        | 디스크 쓰기 | 광고 API 쓰기 | 전역 가드 |
|----------------|-------------------|-------------|---------------|-----------|
| `prep`         | `prep`            | run-dir 생성 | 없음(리포트 잡 접수는 한다) | **탄다** |
| `run`          | `run`             | result.json | 없음          | 안 탄다   |
| `bids_preview` | `bids`(dry-run)   | 미리보기 파일만 | 없음        | 안 탄다   |
| `bids_commit`  | `bids --commit`   | 백업·ledger | **PUT**       | **탄다** |
| `revert_only`  | `bids --revert`   | ledger      | **PUT**       | **탄다** |
| `revert_all`   | `bids --revert`   | ledger      | **PUT**       | **탄다** |
| `synthetic`    | (없음)            | 로그만      | 없음          | 안 탄다   |

불사자 작업 3종 (Phase 3). **광고 API 가 아니라 불사자 MCP 를 부르고, 셋 다 읽기 전용이다:**

| kind              | 스크립트            | 디스크 쓰기        | 불사자 쓰기 | 전역 가드 |
|-------------------|---------------------|--------------------|-------------|-----------|
| `bulsaja_profile` | `--profile-only`    | 프로필 파일        | 없음(조회) | 안 탄다   |
| `bulsaja_index`   | `ss_index_build.py` | `ss_index` 테이블  | 없음(조회) | 안 탄다   |
| `bulsaja_scan`    | `bulsaja_scan.py`   | `join_*.json`      | 없음(조회) | 안 탄다   |

셋이 전역 가드를 **안 타는** 이유는 `WRITE_KINDS` 주석에 있다. 대신 `bulsaja_index`·
`bulsaja_scan` 은 `SINGLETON_KINDS` 로 **같은 kind 끼리만** 겹치는 걸 막는다(레이트리밋).

`prep` 이 가드를 타는 이유: 같은 회차 디렉터리에 스냅샷을 통째로 다시 쓰는데,
그 사이에 `bids` 가 돌면 읽는 스냅샷이 발밑에서 바뀐다.

**자격증명을 자식에게 넘기지 않는다.** CLI 의 `nvad.py` 가 설정 파일을 직접 읽으므로
넘길 이유가 없다. env 로 넘기는 설계는 `ps -E` 한 줄에 다 뜬다 (T-1-03c).
"""
import json
import os
import sqlite3
import subprocess
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from webapp import argv as argv_mod
from webapp import bulsaja_index, paths, settings

# 모듈 이름을 짧게 한 번 더 노출한다 — 테스트·라우트가 `jobs.argv.PY_CLI` 로 집는다.
argv = argv_mod

# **`JobKind` 와 `KINDS` 는 항상 같이 고친다.** 하나만 고치면 타입 검사는 통과하는데
# `create_job` 첫 줄의 `kind not in KINDS` 가 런타임에 거부한다 — "코드상 맞는데 화면에서만
# 안 되는" 부류의 고장이다.
JobKind = Literal["prep", "run", "bids_preview", "bids_commit",
                  "revert_only", "revert_all", "synthetic",
                  "bulsaja_profile", "bulsaja_index", "bulsaja_scan"]

KINDS: tuple[str, ...] = ("prep", "run", "bids_preview", "bids_commit",
                          "revert_only", "revert_all", "synthetic",
                          "bulsaja_profile", "bulsaja_index", "bulsaja_scan")

# 전역 1개 가드의 대상. **왜 전역인가:**
# ENG-04(대상별 잠금)는 Phase 2 지만 **위험은 Phase 1 에 있다.** `run_bids` 가
# `before_bids_<alias>.json` 과 `ledger/<alias>.json` 을 읽고-병합하고-통째로 다시
# 쓰는데 락이 없다(bids.py:182-193). 쓰기 잡 두 개가 겹치면 백업 항목이 사라지고
# **그 소재는 영영 되돌릴 수 없다.** 되돌릴 수 없는 손실이라 넓게, 그리고 지금 막는다.
# Phase 2 가 이걸 대상별 락으로 좁힌다. 미리보기·판정은 아무것도 안 쓰므로 뺀다 —
# 쓰기가 아닌 것까지 막는 가드는 사람이 가드를 끄게 만든다.
WRITE_KINDS: frozenset[str] = frozenset({"prep", "bids_commit", "revert_only", "revert_all"})
# **불사자 잡 3종을 여기 넣지 마라.** 셋 다 불사자에 아무것도 안 쓴다(workdata·프로필 조회는
# 읽기 전용이다). 넣으면 3시간 32분짜리 인덱스가 도는 동안 입찰가 인상·되돌리기가 전부
# 409 가 된다 — 위 "쓰기가 아닌 것까지 막는 가드는 사람이 가드를 끄게 만든다" 가 바로 이 경우다.

# ENG-08 사전 점검 대상. **불사자 MCP 를 부르는 잡**이다.
# `bulsaja_profile` 은 **일부러 뺐다** — 그 잡이 프로필을 만드는 잡이라, 가드 대상에 넣으면
# 프로필이 없을 때 프로필을 만들 수 없다(닭·달걀). 계정 확인은 그 자체로 읽기 조회 1회다.
BULSAJA_KINDS: frozenset[str] = frozenset({"bulsaja_index", "bulsaja_scan"})

# **살아 있는 잡의 상태 두 가지.** `starting` 은 "행은 들어갔는데 자식이 아직 안 떴다" 다.
# 왜 둘로 쪼갰나: 예전에는 INSERT 가 바로 `running` 이었는데, 그 행의 `pid` 는 spawn 뒤에야
# 채워진다. 그 수~수십 ms 창에서 `_reap`(SSE 가 0.4초마다 부른다)이 `pid=NULL` 을 보고
# **멀쩡히 뜰 잡을 `orphaned` 로 찍었다.** 그러면 ① 전역 쓰기 가드(`status='running'` 조회)가
# 그 잡을 못 봐서 두 번째 쓰기 잡이 들어가고(백업 병합이 깨져 그 소재는 영영 못 되돌린다),
# ② `post_revert_job` 이 일부러 허용하는 `orphaned` 에 **살아서 PUT 을 날리는 중인 잡**이
# 섞인다. 재현된 경합이다.
#
# 그래서 spawn 전 구간을 `starting` 으로 두고 **가드는 둘 다 본다**(LIVE_STATUSES).
# `_reap` 은 `running` 만 건드리므로 그 창이 통째로 사라진다.
LIVE_STATUSES: tuple[str, ...] = ("running", "starting")

# `starting` 인 채로 이 시간을 넘기면 "띄우다 죽은 것" 으로 보고 닫는다.
# 이게 없으면 INSERT 와 spawn 사이에 프로세스가 통째로 죽었을 때 그 행이 **영원히**
# 전역 가드를 잡는다 — `_reap` 이 원래 막으려던 바로 그 고장이 이름만 바뀌어 돌아온다.
# spawn 은 실측 수~수십 ms 라 60초면 오탐이 날 여지가 없다.
STARTING_TIMEOUT_SEC = 60

DDL = """
CREATE TABLE IF NOT EXISTS jobs (
  id            TEXT PRIMARY KEY,
  kind          TEXT NOT NULL,
  run_dir       TEXT,
  accounts      TEXT,
  argv          TEXT NOT NULL,
  pid           INTEGER,
  status        TEXT NOT NULL,
  exit_code     INTEGER,
  log_path      TEXT NOT NULL,
  targets_path  TEXT,
  result_path   TEXT,
  parent_job_id TEXT,
  target_count  INTEGER,
  started_at    TEXT NOT NULL,
  ended_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_parent ON jobs(parent_job_id);

CREATE TABLE IF NOT EXISTS ss_index (
  product_id      TEXT PRIMARY KEY,
  smartstore      TEXT,
  market_group_id TEXT NOT NULL,
  group_total     INTEGER,
  unresolved      INTEGER NOT NULL DEFAULT 0,
  observed_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ss_index_smartstore ON ss_index(smartstore);
CREATE INDEX IF NOT EXISTS idx_ss_index_group ON ss_index(market_group_id);
"""
# ※ RESEARCH §5.7 의 DDL 에서 `run_dir` 만 NOT NULL 을 뺐다. `prep` 은 회차 이름을
#    **CLI 가 오늘 날짜로 정한다** — 웹앱이 미리 지어내면 진실이 둘이 된다.
# ※ 보드용 캐시 테이블은 만들지 않는다. 보드는 매번 `result.json` 을 투영한다(수십 ms).
#    캐시는 최적화이고, 지금 넣으면 "진실이 둘" 위험만 는다.
# ※ 대상별 잠금 테이블은 Phase 2(ENG-04) 다. 안 쓰는 스키마를 미리 굳히지 않는다.
#
# ── ss_index (Phase 3 / D-20) ───────────────────────────────────────────────
# ※ observed_at 이 있어야 D-04 를 안 어긴다. "채널상품ID 를 영구 키로 저장하는 것" 과
#    "관측 기록을 관측시각과 함께 보관하는 것" 은 다르다. 20일 물갈이로 번호가 재발급되므로
#    적힌 값을 그대로 믿으면 조용히 틀린 상품을 가리킨다 — 쓰기 직전 재검증이 그 선을 지킨다
#    (JOIN-04). 관측시각이 없으면 "언제 본 값인가" 를 물을 수 없어 재검증이 성립하지 않는다.
# ※ 이건 보드 캐시가 아니다. 보드 캐시는 `result.json` 에서 언제든 재생성되는 투영이라
#    두는 순간 진실이 둘이 되지만, 이건 **3시간 반을 태워야 다시 얻는 외부 관측 기록**이다
#    (36그룹 / 47,105 상품). 재생성이 공짜가 아니면 그건 캐시가 아니라 기록이다.
#    위 "보드용 캐시 테이블은 만들지 않는다" 는 여전히 유효하고, 대상별 잠금도 여전히 Phase 2 다.
# ※ `smartstore` 에 NOT NULL 을 걸지 않는다. 업로드 안 된 상품이 **정상적으로** NULL 이다
#    (전체 수집상품 97만 건 중 대부분). 걸면 인덱스 잡이 그 그룹 중간에서 통째로 죽는다.
# ※ `unresolved` 는 429·타임아웃으로 **못 본 것**이다. 0 으로 접지 마라 — 미조회를 성공으로
#    적으면 그 행이 화면에서 "미해소(광고 쪽 오류)" 로 둔갑한다(Pitfall 3).
# ※ `group_total` 은 관측 시점의 그룹 전체 상품수다. 행수와 비교해야 "중간에 끊긴 잡" 을
#    "다 훑었다" 와 구분할 수 있다 (`bulsaja_index.group_health`).


class BusyError(RuntimeError):
    """이미 도는 쓰기 작업이 있다. 라우트가 409 로 번역한다."""


# 인메모리 `Popen` 맵. **`--workers 1` 전제다** (Pitfall 9 / T-1-22).
# 자식은 `start_new_session=True` 라 세션이 갈라져 있어서, 종료코드를 읽는 길은
# 이 객체의 `poll()` 뿐이다. 워커가 둘 이상이면 잡을 띄운 워커와 상태를 묻는 워커가
# 달라져 이 맵이 비어 보이고, 멀쩡히 끝난 잡이 `orphaned` 로 찍힌다.
# `run-webapp.sh` 가 `--workers 1` 을 고정하고 `main.py` 가 기동 때 경고한다.
_PROCS: dict[str, subprocess.Popen] = {}


# ── 경로 ────────────────────────────────────────────────────────────────────

def db_path() -> Path:
    """잡 레지스트리 파일. 상대경로면 저장소 루트 기준."""
    p = Path(settings.DB_PATH).expanduser()
    return p if p.is_absolute() else paths.repo_root() / p


def log_dir() -> Path:
    d = Path(settings.JOB_LOG_DIR).expanduser()
    d = d if d.is_absolute() else paths.repo_root() / d
    d.mkdir(parents=True, exist_ok=True)
    return d


def log_path_of(job_id: str) -> Path:
    """진행 로그 파일. append-only 로 쌓이고 Plan 01-06 의 SSE 가 여기를 tail 한다."""
    return log_dir() / f"{job_id}.log"


def _web_dir(run_dir: str) -> Path:
    """회차 안의 웹앱 산출물 폴더. 회차 이름은 **화이트리스트를 통과한 것만** 온다."""
    d = paths.run_dir_path(run_dir) / "web"
    d.mkdir(parents=True, exist_ok=True)
    return d


def targets_path_of(job_id: str) -> Path | None:
    """이 작업이 지목한 대상 목록 파일 (FLOW-02 의 '그 파일'). 없으면 None."""
    row = _row(job_id)
    return Path(row["targets_path"]) if row and row["targets_path"] else None


def result_path_of(job_id: str) -> Path | None:
    """이 작업의 산출물 파일(미리보기/실행 결과). 없으면 None."""
    row = _row(job_id)
    return Path(row["result_path"]) if row and row["result_path"] else None


# ── DB ──────────────────────────────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    """커넥션은 작업마다 새로 연다. `timeout=5` 로 잠깐의 경합은 기다린다."""
    cx = sqlite3.connect(db_path(), timeout=5)
    cx.row_factory = sqlite3.Row
    return cx


def init_db() -> None:
    """테이블·인덱스를 만들고 WAL 을 켠다. 여러 번 불러도 안전하다.

    WAL 인 이유: 상태 폴링(읽기)과 잡 생성·종료 기록(쓰기)이 겹친다.
    기본 저널 모드면 읽는 동안 쓰기가 막혀 버튼이 잠깐씩 먹통이 된다.
    """
    db_path().parent.mkdir(parents=True, exist_ok=True)
    cx = _conn()
    try:
        cx.execute("PRAGMA journal_mode = WAL")
        cx.executescript(DDL)
        cx.commit()
    finally:
        cx.close()


def _row(job_id: str) -> sqlite3.Row | None:
    cx = _conn()
    try:
        return cx.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    finally:
        cx.close()


def _now() -> str:
    """로컬 시각 + 오프셋. 오프셋을 빼면 경과시간 계산이 서머타임·시차에서 틀어진다."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _alive(pid: int | None) -> bool:
    """시그널 0 = 존재 확인만. 프로세스에 아무 영향이 없다."""
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _finish(cx: sqlite3.Connection, job_id: str, code: int) -> None:
    cx.execute("UPDATE jobs SET status = ?, exit_code = ?, ended_at = ? WHERE id = ?",
               ("done" if code == 0 else "failed", code, _now(), job_id))
    _PROCS.pop(job_id, None)


def _reap(cx: sqlite3.Connection) -> None:
    """`running` 으로 남아 있는 행들의 실제 생사를 확인해 상태를 맞춘다.

    가드가 이걸 먼저 돌려야 한다 — 안 그러면 이미 끝난 쓰기 잡의 행이 계속
    `running` 으로 남아 다음 작업을 영원히 막는다("아무것도 안 도는데 409").

    프로세스 메모리에 `Popen` 이 없는데 pid 도 죽었으면 종료코드를 알 길이 없다.
    그때는 **지어내지 않고** `orphaned` 로 둔다 — 복구는 Phase 2(ENG-05)다.

    **`starting` 은 생사를 묻지 않는다.** 그 상태의 행은 아직 pid 가 없는 게 정상이라,
    `_alive(None)` 을 물으면 무조건 거짓이고 멀쩡히 뜰 잡이 `orphaned` 가 된다
    (재현된 경합 — LIVE_STATUSES 주석 참조). 대신 **시간으로만** 판정한다:
    `STARTING_TIMEOUT_SEC` 을 넘겼으면 띄우다 죽은 것이니 `failed` 로 닫아 전역 가드를
    풀어 준다. 시간 이전의 `starting` 은 건드리지 않는다.
    """
    for r in cx.execute("SELECT id, pid FROM jobs WHERE status = 'running'").fetchall():
        proc = _PROCS.get(r["id"])
        if proc is not None:
            code = proc.poll()
            if code is not None:
                _finish(cx, r["id"], code)
            continue
        if not _alive(r["pid"]):
            cx.execute("UPDATE jobs SET status = 'orphaned', ended_at = ? WHERE id = ?",
                       (_now(), r["id"]))

    한계 = datetime.now().astimezone() - timedelta(seconds=STARTING_TIMEOUT_SEC)
    for r in cx.execute("SELECT id, started_at FROM jobs WHERE status = 'starting'").fetchall():
        try:
            시작 = datetime.fromisoformat(r["started_at"])
        except (TypeError, ValueError):
            시작 = None            # 시각을 못 읽으면 살려 두지 않는다 — 가드를 영원히 잡는 쪽이 더 나쁘다
        if 시작 is None or 시작 < 한계:
            cx.execute("UPDATE jobs SET status = 'failed', exit_code = -1, ended_at = ? "
                       "WHERE id = ? AND status = 'starting'", (_now(), r["id"]))


# ── 자식 띄우기 ─────────────────────────────────────────────────────────────

def spawn(argv_list: list[str], log_path) -> subprocess.Popen:
    """CLI 자식을 띄우고 `Popen` 을 돌려준다. **호출부를 블로킹하지 않는다.**

    인자 하나하나가 실측으로 정해졌다 (RESEARCH §5.1~5.3):

    · `env` 의 `PYTHONUNBUFFERED=1` — 없으면 0.5초 시점 로그파일이 **0바이트**고
      종료 시 한꺼번에 떨어진다(실측). CLI 전체에 `flush=True` 가 `prune.py:115`
      한 줄뿐이라 CLI 를 고쳐서는 못 푼다. 10분짜리 `prep` 의 진행 로그가 10분 내내
      빈 화면이 된다 — "SSE 가 고장났다" 로 오진하기 딱 좋은 종류다.
    · `env` 는 **병합**이다(`{**os.environ, ...}`). 통째로 갈아치우면 PATH·HOME 이
      사라져 CLI 가 죽는다. 그리고 **자격증명을 여기 심지 않는다** — `ps -E` 에 뜨고,
      CLI 가 설정 파일을 직접 읽으므로 넘길 이유도 없다 (T-1-03c).
    · `start_new_session=True` — 자식을 새 세션·새 프로세스 그룹으로 보낸다.
      `uvicorn --reload` 재시작과 서버 종료에서 자식이 살아남는다(실측 2회:
      부모 그룹에 SIGTERM 을 쏴도 그룹이 분리된 자식만 생존). ENG-02 의 절반이
      이 한 인자다. 부수효과로 서버가 죽어도 자식이 계속 도는데, 그래서
      jobs 행에 `pid` 와 `started_at` 을 남긴다 — Phase 2 의 고아 정리(ENG-05)가
      끼워 넣을 자리다.
    · `stdin=DEVNULL` — 자식이 입력을 기다리며 영원히 멈추는 사고를 막는다.
    · `cwd=repo_root()` — `run_ads.py` 의 `lib/eroomlib` 탐색이 여기 의존한다.
    · `stdout`/`stderr` 를 같은 파일로 합친다 — 파이프로 직접 흘리지 **않는다.**
      파이프는 읽는 쪽이 붙어 있어야만 살아서 "브라우저를 닫았다 다시 열기" 가
      성립하지 않는다(ENG-03). 파일이면 오프셋부터 다시 읽으면 그만이다.
    """
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fh = open(log_path, "ab", buffering=0)     # append-only · 버퍼 없음
    except OSError as e:
        raise RuntimeError(f"로그 파일을 못 연다: {e}")

    try:
        return subprocess.Popen(
            argv_list,
            cwd=str(paths.repo_root()),
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
            stdout=fh,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except Exception:
        # Popen 이 터지면 핸들이 새는 것도 막는다. 로그 파일은 남겨 둔다 —
        # 실패 사유를 쓸 자리이기도 하다.
        fh.close()
        raise
    finally:
        # 부모는 이 핸들이 더 필요 없다. 자식이 복제본을 쥐고 있다.
        # 안 닫으면 서버가 도는 동안 잡 개수만큼 fd 가 쌓인다.
        try:
            if not fh.closed:
                fh.close()
        except Exception:
            pass


# ── 작업 생성 ───────────────────────────────────────────────────────────────

def _write_targets(job_id: str, run_dir: str, ad_ids: list[str]) -> Path:
    """대상 adId 목록을 **원자적으로** 떨군다 (FLOW-02 의 '그 파일').

    tmp → `os.replace` 로 쓰는 이유: 자식이 읽는 도중에 반쪽 파일이 보이면
    `--only-ads` 가 깨진 파일로 판단해 exit 1 한다(그게 맞는 동작이다).
    `run_coupang.py:68-74` 의 원자적 쓰기 관례를 그대로 쓴다.
    """
    path = _web_dir(run_dir) / f"targets_{job_id}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(ad_ids, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return path


def _override_targets(run_dir: str | None, path: str | Path) -> Path:
    """이미 있는 대상 파일을 **그대로** 가리킨다 — 새로 쓰지 않는다 (D-11 / FLOW-02).

    실행(`bids_commit`)·되돌리기(`revert_only`)가 미리보기가 만든 그 파일을 재사용하는
    통로다. 새로 쓰면 그 순간 '같은 파일' 이 아니게 되고, 미리보기와 실행 사이에
    화면 필터가 바뀐 만큼 **본 것과 다른 게 실행된다.**

    받은 경로를 그대로 믿지 않는다. 회차의 `web/` 밑인지 · 실제로 있는지 두 가지를
    보고, 아니면 `ValueError` 다. **빈 목록으로 폴백하지 않는다** — 폴백하면
    "아무것도 안 했는데 성공" 이 되어 사용자는 올라간 줄 안다.
    """
    if not run_dir:
        raise ValueError("대상 파일을 재사용하려면 회차가 필요하다")
    p = Path(path).expanduser()
    if not p.is_absolute():
        raise ValueError("대상 파일 경로가 절대경로가 아니다")
    p = p.resolve()
    # 부모 디렉터리 비교다. 접두 비교(`startswith`)로 하면 `web-남의것/` 같은
    # 형제 디렉터리가 통과한다 — 경계를 글자가 아니라 경로로 본다.
    if p.parent != _web_dir(run_dir).resolve():
        raise ValueError("회차 밖 대상 파일은 쓸 수 없다")
    if not p.is_file():
        raise ValueError("대상 파일이 사라졌다 — 미리보기부터 다시 해라")
    return p


def _count_targets(path: Path) -> int | None:
    """대상 파일을 **읽어서** 센다. 화면이 준 수를 믿지 않는다.

    모양 두 가지를 받는다(`run_ads._load_only_ads` 와 같은 계약):
    배열 `["nad-…"]` 과 `{"adIds": [...]}`. 못 읽으면 지어내지 않고 `None` 이다 —
    0 으로 적으면 "대상이 없다" 와 "못 셌다" 가 같은 화면이 된다.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    ids = raw if isinstance(raw, list) else raw.get("adIds")
    return len(ids) if isinstance(ids, list) else None


def _build_argv(kind: str, job_id: str, run_dir: str | None, accounts: list[str],
                targets_path: Path | None, result_path: Path | None,
                commit: bool) -> list[str]:
    """kind → `AdsArgv`. **조립은 `webapp/argv.py` 한 곳에서만** 일어난다 (T-1-10)."""
    if kind in ("prep", "run"):
        return argv_mod.AdsArgv(subcommand=kind, run_dir=run_dir,
                                accounts=accounts).build()

    if kind == "bids_preview":
        return argv_mod.AdsArgv(subcommand="bids", run_dir=run_dir, accounts=accounts,
                                only_ads=targets_path, preview_out=result_path).build()

    if kind == "bids_commit":
        return argv_mod.AdsArgv(subcommand="bids", run_dir=run_dir, accounts=accounts,
                                commit=True, only_ads=targets_path,
                                preview_out=result_path).build()

    if kind in ("revert_only", "revert_all"):
        # `revert_only` 는 대상 목록으로 좁힌다(D-13 — 이 작업분만).
        # `revert_all` 은 좁히지 않는다(회차 전체). 대상 파일 유무가 그 차이의 전부다.
        #
        # **그래서 대상 파일이 없는 `revert_only` 는 존재할 수 없다.** 없으면
        # `AdsArgv` 가 `--only-ads` 를 안 붙이고 CLI 는 그걸 "백업 전량" 으로 읽는다
        # (`bids.run_revert` — `only_ads is None or ...`). kind 이름은 `revert_only`
        # 인데 동작은 `revert_all` 이 된다. 지금 운영 라우트는 항상 대상 파일을
        # 넘기므로 안 나지만, v2 의 APScheduler 가 인자 하나를 빼먹는 순간 회차
        # 전체(실측 2,242건)가 풀린다. **빈 값이 '전량' 으로 해석되는 경로는 예외로
        # 터뜨린다** — 이 페이즈에서 같은 부류가 두 번 사고 직전까지 갔다.
        if kind == "revert_only" and targets_path is None:
            raise ValueError("revert_only 에는 대상 파일이 반드시 있어야 한다 — "
                             "대상 없는 되돌리기는 회차 전체다(D-12)")
        return argv_mod.AdsArgv(subcommand="bids", run_dir=run_dir, accounts=accounts,
                                revert=True, commit=commit,
                                only_ads=targets_path if kind == "revert_only" else None,
                                preview_out=result_path).build()

    if kind in ("bulsaja_profile", "bulsaja_index", "bulsaja_scan"):
        # 대상 파일 규약은 광고 쪽과 같다 — `_write_targets` 가 쓰는 **JSON 배열** 하나다.
        # 담기는 내용만 다르다:
        #   · 인덱스 → groupId 문자열 리스트
        #   · 스캔   → "<계정alias>|<mallProductId>" 문자열 리스트 (`board.js` 의 Tabulator
        #     index 와 같은 모양이라 화면이 고른 행을 그대로 담을 수 있다)
        #
        # **둘 다 대상 파일이 필수다.** `revert_only` 와 **똑같은 이유**로 그렇다:
        # 없으면 자식이 그걸 "전량" 으로 읽는다. 빈 값이 전량으로 해석되는 경로는
        # 조립이 아니라 여기서 터뜨린다 (`BulsajaArgv.build()` 주석이 이 자리를 가리킨다).
        if kind == "bulsaja_index" and targets_path is None:
            raise ValueError("인덱스 잡에는 그룹 목록 파일이 반드시 있어야 한다 — "
                             "없으면 전 그룹(실측 75,335건 · 5시간 39분)이다")
        if kind == "bulsaja_scan" and targets_path is None:
            raise ValueError("스캔 잡에는 대상 목록 파일이 반드시 있어야 한다 (FLOW-02 / D-11)")

        하위 = {"bulsaja_profile": "profile", "bulsaja_index": "index",
                "bulsaja_scan": "scan"}[kind]
        # 설정값은 **전부 호출부에서 읽어 넘긴다.** 모델·CLI 에 기본값을 두면
        # workspace.toml 을 고쳐도 동작이 안 바뀌는 가짜 설정이 된다 (T-1-12).
        return argv_mod.BulsajaArgv(
            subcommand=하위,
            db=db_path(),
            out=result_path if result_path else bulsaja_index.profile_path(),
            profile_out=bulsaja_index.profile_path(),
            expect_nick=settings.cfg("expected_bulsaja_nick", required=True),
            min_interval=float(settings.cfg("mcp_min_interval",
                                            settings.DEFAULTS["mcp_min_interval"])),
            retry_after=int(settings.cfg("mcp_retry_after",
                                         settings.DEFAULTS["mcp_retry_after"])),
            batch_size=int(settings.cfg("mcp_batch_size",
                                        settings.DEFAULTS["mcp_batch_size"])),
            run_dir=run_dir if kind == "bulsaja_scan" else None,
            groups=targets_path if kind == "bulsaja_index" else None,
            targets=targets_path if kind == "bulsaja_scan" else None,
        ).build()

    raise ValueError(f"argv 를 조립할 수 없는 작업 종류다: {kind}")


def create_job(kind: str, *, run_dir: str | None = None,
               accounts: list[str] | None = None,
               only_ads: list[str] | None = None,
               commit: bool = False,
               parent_job_id: str | None = None,
               targets_path_override: str | Path | None = None,
               argv_override: list[str] | None = None) -> str:
    """작업을 만들고 자식을 띄운 뒤 `job_id` 를 즉시 돌려준다. **블로킹하지 않는다.**

    **이 함수는 HTTP 를 모른다** (D-17 / ENG-07). 요청 객체를 받지 않고 상태코드를
    모른다. v2 의 APScheduler 가 이 함수를 그대로 부른다 — 그때 라우트를 통해
    자기 서버에 요청을 쏘는 모양이 되지 않게 지금 경계를 그어 둔다.

    순서에 의미가 있다:
      ① 쓰기 잡 전역 가드 (BusyError) — 자식을 띄우기 **전에** 막는다
      ② 회차 화이트리스트 — 라우트가 깜빡해도 여기서 막힌다 (T-1-11)
      ③ 대상 목록을 파일로 (FLOW-02)
      ④ argv 조립 (webapp/argv.py 한 곳)
      ⑤ jobs 행 INSERT (status='starting' — **아직 running 이 아니다**)
      ⑥ spawn → pid 와 status='running' 을 **같이** UPDATE

    `only_ads` 와 `targets_path_override` 는 **상호배타**다. 전자는 목록을 받아 파일을
    새로 쓰고, 후자는 이미 있는 파일을 그대로 가리킨다 — 둘을 같이 주면 어느 쪽이
    진짜 대상인지 모르는 상태가 된다. 대상 파일은 하나다 (D-11 / FLOW-02 / T-1-06).

    `argv_override` 는 **테스트 전용**이다. 합성 잡(`kind="synthetic"`)처럼 임의 argv 를
    태우는 유일한 경로라, 운영 라우트에는 절대 노출하지 않는다 (T-1-23).
    라우트는 kind 가 경로마다 고정이고 클라이언트가 kind 를 문자열로 넘기지 못한다.
    """
    if kind not in KINDS:
        raise ValueError(f"모르는 작업 종류다: {kind}")
    # 상호배타 가드. 이 한 줄이 "대상 파일은 하나" 를 코드로 강제한다 —
    # 주석이나 관례가 아니라 호출하는 순간 터지는 규칙이어야 한다.
    if only_ads is not None and targets_path_override is not None:
        raise ValueError("only_ads 와 targets_path_override 를 같이 줄 수 없다 — 대상 파일은 하나다")
    if kind == "synthetic" and not argv_override:
        raise ValueError("합성 잡은 argv_override 가 필요하다 (테스트 전용 경로)")

    accounts = list(accounts or [])
    init_db()
    job_id = str(uuid.uuid4())
    log_path = log_path_of(job_id)
    BIDS_KINDS = ("bids_preview", "bids_commit", "revert_only", "revert_all")
    # 불사자 산출물 파일명 접두. `BIDS_KINDS` 와 **나란히** 둔다 (아래 result_path 분기).
    BULSAJA_접두 = {"bulsaja_scan": "join", "bulsaja_index": "index",
                    "bulsaja_profile": "profile"}

    cx = _conn()
    try:
        # ① 가드 ~ ⑤ INSERT 를 한 트랜잭션에 묶는다. 두 요청이 스레드풀에서
        #    겹쳐도 "둘 다 비었네" 를 보고 둘 다 들어가는 일이 없다.
        #    가드를 **맨 먼저** 본다 — 어차피 거부될 작업 때문에 회차에 대상 파일을
        #    떨구고 나서 409 를 내면 run-dir/web 에 쓰레기가 쌓인다.
        cx.execute("BEGIN IMMEDIATE")
        _reap(cx)
        if kind in WRITE_KINDS:
            표시 = ",".join("?" * len(WRITE_KINDS))
            상태표시 = ",".join("?" * len(LIVE_STATUSES))
            # **`starting` 도 본다.** 안 보면 자식을 띄우는 중인 쓰기 잡을 가드가 못 잡아
            # 두 번째 쓰기 잡이 들어간다 — 고치려던 구멍이 이름만 바뀐다.
            막는것 = cx.execute(
                f"SELECT id, kind FROM jobs WHERE status IN ({상태표시}) AND kind IN ({표시}) "
                "ORDER BY rowid LIMIT 1",
                tuple(LIVE_STATUSES) + tuple(sorted(WRITE_KINDS))).fetchone()
            if 막는것:
                raise BusyError(
                    f"이미 도는 쓰기 작업이 있다: {막는것['id']} ({막는것['kind']})")

        # ② 회차 화이트리스트. `..` 를 거르는 블랙리스트가 아니라 "실재하는 회차 목록에
        #    있는 이름만" 통과시킨다. 실패는 ValueError → 라우트가 400 으로 번역한다.
        if run_dir:
            paths.run_dir_path(run_dir)
        elif kind in BIDS_KINDS and not argv_override:
            # `argv_override` 가 있으면 argv 를 통째로 받으므로 회차 요구가 의미 없다.
            # 그 경로는 테스트 전용이다(운영 라우트는 argv_override 를 넘기지 않는다).
            raise ValueError("입찰가 작업에는 회차가 필요하다")

        # ③ 대상 목록 → 파일. **경로는 웹앱이 만든다** — 사용자 입력에서 경로를 받지
        #    않는다(ASVS V12 / T-1-11).
        #    **`is not None` 이다 — 빈 목록도 파일로 떨군다.** `if only_ads:` 로 두면
        #    "아무것도 안 골랐다" 가 argv 에서 `--only-ads` 자체를 없애고, CLI 는
        #    그걸 "전량" 으로 읽는다(`_load_only_ads` 가 None 이면 전량이다).
        #    0건이 조용히 2,242건이 되는 길이라, 대상 파일 없이 입찰가 명령을
        #    만들지 않는다 (T-1-05 와 같은 종류의 사고).
        #
        #    `targets_path_override` 는 그 반대다 — **새로 쓰지 않고** 미리보기가 만든
        #    파일을 그대로 가리킨다(D-11). 실행이 화면 상태에서 목록을 다시 만들면,
        #    미리보기와 실행 사이에 필터가 바뀐 만큼 본 것과 다른 게 실행된다.
        targets_path = None
        if only_ads is not None:
            if not run_dir:
                raise ValueError("대상 목록을 쓰려면 회차가 필요하다")
            targets_path = _write_targets(job_id, run_dir, list(only_ads))
        elif targets_path_override is not None:
            targets_path = _override_targets(run_dir, targets_path_override)

        result_path = None
        if run_dir and kind in BIDS_KINDS:
            접두 = "preview" if kind == "bids_preview" else "result"
            result_path = _web_dir(run_dir) / f"{접두}_{job_id}.json"
        elif kind in BULSAJA_접두:
            # `BIDS_KINDS` 를 건드리지 않고 나란한 집합을 하나 더 둔다 — 두 계열의
            # 산출물 규칙이 한 조건문에 섞이면 한쪽을 고칠 때 다른 쪽이 따라 바뀐다.
            #
            # **`bulsaja_profile` 은 `run_dir` 이 없어도 돌아야 한다.** 계정 확인은 회차와
            # 무관하고, 오히려 회차를 고르기 전에 눌러야 하는 버튼이다. 그 산출물은
            # 설정이 정한 프로필 파일 한 자리다(`bulsaja_index.profile_path()` — 읽는 쪽과
            # 같은 계산을 본다).
            #
            # 인덱스·스캔은 회차가 있으면 회차의 `web/` 밑에, 없으면 잡 로그 옆에 둔다.
            # 인덱스는 회차를 넘어 사는 기록이라 회차가 없는 호출이 정상이고, 그때 새
            # 디렉터리를 파지 않는다 — 로그 루트는 이미 있고 이미 `.gitignore` 대상이다.
            if kind == "bulsaja_profile":
                result_path = bulsaja_index.profile_path()
            elif run_dir:
                result_path = _web_dir(run_dir) / f"{BULSAJA_접두[kind]}_{job_id}.json"
            else:
                result_path = log_dir() / f"{BULSAJA_접두[kind]}_{job_id}.json"

        # ④ argv
        if argv_override:
            cmd = list(argv_override)
        else:
            cmd = _build_argv(kind, job_id, run_dir, accounts,
                              targets_path, result_path, commit)

        cx.execute(
            "INSERT INTO jobs (id, kind, run_dir, accounts, argv, status, log_path, "
            "targets_path, result_path, parent_job_id, target_count, started_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (job_id, kind, run_dir,
             json.dumps(accounts, ensure_ascii=False),
             json.dumps(cmd, ensure_ascii=False),      # 재현·감사용. 시크릿 없음
             # **`running` 이 아니라 `starting` 이다.** pid 는 spawn 뒤에야 들어오는데,
             # 그 전에 `running` 으로 적으면 `_reap` 이 `pid=NULL` 을 죽음으로 읽고
             # 멀쩡한 잡을 `orphaned` 로 찍어 전역 쓰기 가드가 풀린다(LIVE_STATUSES 주석).
             "starting", str(log_path),
             str(targets_path) if targets_path else None,
             str(result_path) if result_path else None,
             parent_job_id,
             # 대상 수: 목록을 받았으면 그 길이, 파일을 가리켰으면 **그 파일을 읽어** 센다.
             # 화면이 "5건" 이라고 말해도 파일에 2,242건이 들어 있으면 실행되는 건 2,242건이다.
             (len(only_ads) if only_ads is not None
              else (_count_targets(targets_path) if targets_path else None)),
             _now()))
        cx.commit()
    finally:
        cx.close()

    # ⑥ 자식 띄우기. 실패하면 행을 failed 로 닫는다 — starting 으로 남겨 두면
    #    전역 가드가 `STARTING_TIMEOUT_SEC` 동안 걸린다.
    try:
        proc = spawn(cmd, log_path)
    except Exception as e:
        cx = _conn()
        try:
            cx.execute("UPDATE jobs SET status='failed', exit_code=-1, ended_at=? WHERE id=?",
                       (_now(), job_id))
            cx.commit()
        finally:
            cx.close()
        raise RuntimeError(f"작업을 띄우지 못했다: {type(e).__name__}: {e}")

    # 자식이 떴다. **pid 와 status 를 한 UPDATE 로 같이 올린다** — pid 만 먼저 쓰고
    # status 를 나중에 쓰면 그 사이가 또 창이 된다. `_PROCS` 등록을 UPDATE 보다 먼저
    # 하는 것도 같은 이유다: `running` 으로 보이는 순간에는 `poll()` 할 객체가 이미 있어야
    # `_reap` 이 종료코드를 지어내지 않는다.
    _PROCS[job_id] = proc
    cx = _conn()
    try:
        cx.execute("UPDATE jobs SET pid = ?, status = 'running' WHERE id = ?",
                   (proc.pid, job_id))
        cx.commit()
    finally:
        cx.close()

    return job_id


# ── 조회 ────────────────────────────────────────────────────────────────────

def _as_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["elapsed_sec"] = _elapsed(d.get("started_at"), d.get("ended_at"))
    return d


def _elapsed(started: str | None, ended: str | None) -> float | None:
    """시작부터의 경과초. 진행률이 없는 작업(`bids --commit`)의 유일한 진행 표시다(OQ-3).

    끝난 작업은 총 소요시간, 도는 작업은 지금까지의 경과시간이다.
    """
    if not started:
        return None
    try:
        t0 = datetime.fromisoformat(started)
        t1 = datetime.fromisoformat(ended) if ended else datetime.now().astimezone()
        return round((t1 - t0).total_seconds(), 1)
    except ValueError:
        return None


def job_status(job_id: str) -> dict | None:
    """jobs 행 + 살아있는지 확인한 최신 상태. 없으면 None.

    **상태를 바꾸지 않는다** 는 뜻이 아니다 — 죽은 자식을 발견하면 그 사실을 적는다.
    적지 않으면 전역 가드가 유령 작업에 영원히 걸린다. 다만 광고 API·run-dir 산출물은
    건드리지 않으므로 읽기 라우트에서 불러도 된다.
    """
    cx = _conn()
    try:
        cx.execute("BEGIN IMMEDIATE")
        _reap(cx)
        cx.commit()
        row = cx.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    finally:
        cx.close()
    return _as_dict(row) if row else None


def active_job() -> dict | None:
    """지금 도는 작업 하나. 없으면 None.

    **화면이 스트림을 하나만 열게 하는 장치다** (T-1-24). 페이지를 새로 그릴 때
    "무엇을 보여줄까" 를 여기서 한 번에 정한다 — 목록에서 running 을 골라내는
    판단이 템플릿·라우트 두 곳에 흩어지면 둘이 어긋난다.

    끝난 작업은 돌려주지 않는다. 새로고침할 때마다 지난 작업 패널이 되살아나면
    "아직 도는 중인가?" 로 읽힌다 — 이 화면에서 제일 비싼 오해다.

    레지스트리가 아직 없으면 **만들지 않고** None 을 준다. 이 함수를 부르는 건
    `GET /` 인데, 읽기 라우트가 파일을 만들기 시작하면 "GET 은 상태를 안 바꾼다"는
    방어의 전제가 흐려진다(T-1-01b). 첫 작업을 누르는 순간 `create_job` 이 만든다.
    """
    if not db_path().is_file():
        return None
    try:
        도는것 = [j for j in recent_jobs(50) if j.get("status") == "running"]
    except sqlite3.Error:
        return None
    return 도는것[0] if 도는것 else None


def latest_done(kind: str, run_dir: str | None = None) -> dict | None:
    """그 종류의 **가장 최근 성공 잡** 1건. 없으면 None.

    03-05·03-06 이 "마지막 조인 산출물" 을 찾는 **유일한 길**이다.
    `web/join_*.json` 을 glob 으로 뒤지지 마라 — 파일이 있다는 것과 그 잡이 성공했다는 것은
    다르다(중간에 죽은 잡도 반쯤 쓴 파일을 남긴다). 어느 잡이 성공했는지는 레지스트리가 정본이다.

    `run_dir` 을 주면 그 회차로 좁힌다. 인덱스 잡처럼 회차를 넘어 사는 종류는 안 주면 된다.

    레지스트리가 아직 없으면 **만들지 않고** None 이다 — `active_job()` 과 같은 규율(T-1-01b).
    """
    if kind not in KINDS:
        raise ValueError(f"모르는 작업 종류다: {kind}")
    if not db_path().is_file():
        return None
    cx = _conn()
    try:
        cx.execute("BEGIN IMMEDIATE")
        _reap(cx)
        cx.commit()
        조건 = "kind = ? AND status = 'done'"
        인자: tuple = (kind,)
        if run_dir:
            조건 += " AND run_dir = ?"
            인자 = (kind, run_dir)
        row = cx.execute(
            f"SELECT * FROM jobs WHERE {조건} ORDER BY started_at DESC, rowid DESC LIMIT 1",
            인자).fetchone()
    except sqlite3.Error:
        return None
    finally:
        cx.close()
    return _as_dict(row) if row else None


def recent_jobs(limit: int = 20) -> list[dict]:
    """최근 작업 목록(최신순). 같은 초에 만들어진 것끼리는 입력 순서의 역순이다."""
    cx = _conn()
    try:
        cx.execute("BEGIN IMMEDIATE")
        _reap(cx)
        cx.commit()
        rows = cx.execute(
            "SELECT * FROM jobs ORDER BY started_at DESC, rowid DESC LIMIT ?",
            (int(limit),)).fetchall()
    finally:
        cx.close()
    return [_as_dict(r) for r in rows]
