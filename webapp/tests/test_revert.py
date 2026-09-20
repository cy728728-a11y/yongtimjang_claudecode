#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""되돌리기 CLI 계약 회귀 테스트 (BID-04 / D-12~D-14 / T-1-08 / T-1-40).

여기서 지키는 것은 **되돌릴 수 있는 능력** 이다. 세 가지를 기계로 못박는다:

  D-13  `only_ads` 로 넘긴 **그 작업분만** 되돌린다
  D-13  `before_bids_<alias>.json` 은 되돌리기 전후로 **바이트 단위로 같다**
        (bids.py Important 1 — 같은 키는 먼저 것을 유지. 웹앱이 이걸 깨면 그 소재는
        영영 못 되돌린다)
  D-12  `only_ads` 를 안 주면 **백업 전량**이다 — 그래서 화면의 되돌리기를 `--revert`
        에 그냥 연결하면 안 된다. 실측으로 2,242건이 들어 있던 백업이 있다

네트워크를 타지 않는다 — `bids.nvad.call` 을 전부 몽키패치한다.
쓰기 플래그는 파이썬 kwarg(`commit=True`)로만 넘긴다. `no_commit_guard.sh` 가 찾는 것은
**argv 문자열 리터럴**이라 kwarg 는 걸리지 않는다 — 가드의 요지가 "테스트가 CLI 플래그를
조립해 실제 PUT 을 내보내는 일" 을 막는 것이고, 여기서는 몽키패치가 PUT 을 먼저 끊는다.
"""
import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

# `.claude/skills/naver-ads-weekly/scripts` 를 import 경로에 넣는다.
#
# **이 sys.path 삽입은 테스트 프로세스에만 허용된다.** 웹앱 런타임(`webapp/*.py`)은
# 절대 이걸 하지 않는다 — `bids`·`collect`·`nvad` 는 네임스페이스 없는 최상위 이름이라
# stdlib 을 가릴 수 있다(RESEARCH §5.6). 웹앱은 subprocess 경계로만 CLI 를 부른다.
SCRIPTS_DIR = Path(__file__).resolve().parents[2] / ".claude" / "skills" / "naver-ads-weekly" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import bids  # noqa: E402
import ledger  # noqa: E402

ALIAS = "revtest"

# 백업에 심는 건수. **이 수가 "회차 전체" 다.** 작업분(3건)과 확실히 다른 수여야
# "그 작업분만" 이 증명된다 — 둘이 같으면 무엇을 확인한 건지 알 수 없다.
백업건수 = 10
작업분 = ("ad00", "ad01", "ad02")


def _adattr(bid, group=False):
    return {"bidAmt": bid, "useGroupBidAmt": group}


@pytest.fixture
def 회차(tmp_path):
    """`tmp/runs/<회차>` **2단 구조** + 백업 10건 + 같은 10건의 소재 스냅샷.

    `bids.py:130` 이 ledger 를 `run_dir.parent.parent/"ledger"` 로 찾는다 —
    한 단이라도 빠뜨리면 테스트가 tmp 밖(실제 ledger)을 오염시킨다.
    """
    run_dir = tmp_path / "runs" / "2026-08-30"
    acc = run_dir / "accounts" / ALIAS
    acc.mkdir(parents=True)

    아이디들 = [f"ad{i:02d}" for i in range(백업건수)]
    (acc / "ads.json").write_text(json.dumps({"ads": [
        {"nccAdId": i, "nccAdgroupId": "g", "adAttr": _adattr(120),
         "referenceData": {"productTitle": f"상품{i}"}} for i in 아이디들
    ]}, ensure_ascii=False), encoding="utf-8")

    (run_dir / f"before_bids_{ALIAS}.json").write_text(
        json.dumps({i: _adattr(70, group=True) for i in 아이디들},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    return run_dir


@pytest.fixture
def 네트워크차단(monkeypatch):
    """PUT 을 한 번도 안 내보낸다. `time.sleep` 도 끈다(0.08초 × 다건이면 실제로 기다린다)."""
    보낸것 = []

    def fake_call(acct, method, path, params=None, body=None, raw=False):
        보낸것.append((method, path, body))
        return 200, {}

    monkeypatch.setattr(bids.nvad, "call", fake_call)
    monkeypatch.setattr(bids.time, "sleep", lambda *_: None)
    return 보낸것


def 백업경로(회차):
    return 회차 / f"before_bids_{ALIAS}.json"


def 조용히(*a, **k):
    return None


# ── D-13: 그 작업분만 ────────────────────────────────────────────────────────

def test_그_작업분만_되돌린다(회차, 네트워크차단):
    """T-1-08 — 백업에 10건이 있어도 `only_ads` 3건이면 대상은 정확히 3건이다.

    이 단언이 깨지는 순간 화면의 "되돌리기" 한 번이 회차 전체를 푼다.
    """
    out = bids.run_revert({"alias": ALIAS}, 회차, log=조용히, only_ads=set(작업분))
    assert out["targets"] == 3


def test_백업_파일은_바뀌지_않는다(회차, 네트워크차단):
    """T-1-40 / D-13 — 되돌리기 **전후로 백업 파일이 바이트 단위로 같다**.

    `before_bids_<alias>.json` 은 최초 원본이 담긴 유일한 복원 근거다. 되돌렸다고
    키를 지우면 같은 회차의 다른 작업분을 되돌릴 근거가 사라지고, 중간에 죽었을 때
    재시도할 원본도 함께 날아간다.

    dry-run 과 실제 쓰기 **양쪽 다** 본다 — 쓰기 경로에서만 지우는 구현이면
    dry-run 만 확인하는 테스트는 초록으로 거짓말을 한다.
    """
    bk = 백업경로(회차)
    원본바이트 = bk.read_bytes()

    bids.run_revert({"alias": ALIAS}, 회차, log=조용히, only_ads=set(작업분))
    assert bk.read_bytes() == 원본바이트, "dry-run 이 백업을 건드렸다"

    bids.run_revert({"alias": ALIAS}, 회차, commit=True, log=조용히, only_ads=set(작업분))
    assert bk.read_bytes() == 원본바이트, "되돌리기가 백업을 지웠다 — 재시도 근거가 사라진다"


def test_only_ads_없으면_전량이다(회차, 네트워크차단):
    """D-12 — 기존 동작 불변. `only_ads` 를 안 주면 백업 전량이 대상이다.

    이게 곧 "화면의 되돌리기를 `--revert` 에 그냥 연결하면 안 되는" 이유다.
    """
    out = bids.run_revert({"alias": ALIAS}, 회차, log=조용히)
    assert out["targets"] == 백업건수
    assert out["targets"] != len(작업분), "회차 전체와 작업분이 같은 수면 이 테스트가 무의미하다"


def test_백업에_없는_adId_는_조용히_빠진다(회차, 네트워크차단):
    """교집합만 대상이 된다 — 예외로 터지지 않는다.

    부모 작업에서 성공했는데 백업에 없는 소재는 있을 수 없지만(성공 = 백업이 먼저
    쓰인 것), 있더라도 되돌리기가 통째로 실패하면 나머지 진짜 대상까지 못 되돌린다.
    """
    out = bids.run_revert({"alias": ALIAS}, 회차, log=조용히,
                          only_ads={"ad00", "없는소재", "ad01"})
    assert out["targets"] == 2


def test_쓰기플래그_없이는_PUT_을_안_낸다(회차, 네트워크차단):
    """T-1-42 — dry-run 은 네트워크를 한 번도 안 탄다. 범위 확인이 공짜인 근거다."""
    out = bids.run_revert({"alias": ALIAS}, 회차, log=조용히, only_ads=set(작업분))
    assert out["targets"] == 3
    assert len(네트워크차단) == 0
    assert out.get("committed") == 0


def test_되돌리기가_원본_adAttr_그대로_되쓴다(회차, 네트워크차단):
    """복원값은 백업 그대로다 — 웹앱도 CLI 도 여기서 숫자를 만들지 않는다.

    `useGroupBidAmt` 까지 원본대로 돌아가므로 인상이 만든 그룹→개별 전환도 함께
    취소된다(`build_revert_body`).
    """
    bids.run_revert({"alias": ALIAS}, 회차, commit=True, log=조용히, only_ads={"ad00"})
    assert len(네트워크차단) == 1
    method, path, body = 네트워크차단[0]
    assert method == "PUT"
    assert path.endswith("/ad00")
    assert body["adAttr"] == _adattr(70, group=True)


# ── FLOW-05 연장: 항목 단위 결과 ─────────────────────────────────────────────

def test_되돌리기_결과도_항목단위다(회차, monkeypatch):
    """FLOW-05 / T-1-37 — 무엇이 되돌려졌고 무엇이 실패했는지 **항목별로** 남는다.

    건수만 돌려주면 "469 성공 / 3 실패" 에서 그 3건이 어느 소재인지 화면이 말할 수
    없다. 되돌리기는 사고 대응 경로라 다시 겨눌 대상을 알아야 한다.
    """
    def fake_call(acct, method, path, params=None, body=None, raw=False):
        return (200, {}) if path.endswith("/ad00") else (400, "거부됨")

    monkeypatch.setattr(bids.nvad, "call", fake_call)
    monkeypatch.setattr(bids.time, "sleep", lambda *_: None)

    out = bids.run_revert({"alias": ALIAS}, 회차, commit=True, log=조용히,
                          only_ads={"ad00", "ad01"})

    결과 = {p["adId"]: (p["result"], p["error"]) for p in out["plans"]}
    assert 결과["ad00"] == ("성공", "")
    assert 결과["ad01"][0] == "실패"
    assert "400" in 결과["ad01"][1]
    assert (out["committed"], out["failed"]) == (1, 1)


def test_dry_run_산출물은_결과를_말하지_않는다(회차, 네트워크차단):
    """아직 안 되돌렸는데 "성공" 이라고 적으면 거짓말이다 (D-02 와 같은 규칙)."""
    out = bids.run_revert({"alias": ALIAS}, 회차, log=조용히, only_ads={"ad00"})
    assert len(out["plans"]) == 1
    assert "result" not in out["plans"][0]
    # 무엇으로 되돌릴지는 dry-run 에서도 말한다 — 그게 미리보기의 내용이다.
    assert out["plans"][0]["to"] == 70


def test_스냅샷에_소재가_없으면_실패로_남는다(회차, 네트워크차단):
    """prep 이후 소재가 삭제된 경우(Pitfall 7) — 조용히 건너뛰지 않는다."""
    bk = 백업경로(회차)
    백업 = json.loads(bk.read_text(encoding="utf-8"))
    백업["유령소재"] = _adattr(70, group=True)
    bk.write_text(json.dumps(백업, ensure_ascii=False, indent=1), encoding="utf-8")

    out = bids.run_revert({"alias": ALIAS}, 회차, commit=True, log=조용히,
                          only_ads={"유령소재"})
    assert out["plans"][0]["result"] == "실패"
    assert out["plans"][0]["error"] == "스냅샷에 소재 없음"
    assert len(네트워크차단) == 0


# ── Pitfall 4 / OQ-2: 현재 동작을 문서화한다 ────────────────────────────────

def test_날짜를_넘기면_되돌림_플래그가_안_찍힌다(회차, 네트워크차단):
    """Pitfall 4 / T-1-38 — **이건 버그를 고치는 테스트가 아니라 현재 동작을 적는 테스트다.**

    `ledger.record_reverted` 는 `raises[-1]["date"] == 오늘` 일 때만 플래그를 찍는다.
    어제 올린 것을 오늘 되돌리면 입찰가는 **정상적으로 복원되지만**(PUT 은 날짜와
    무관하다) 이력에는 되돌림이 안 남는다 → `last_raise_date` 가 어제를 계속 가리켜
    쿨다운 6일 동안 재인상이 막힌다.

    **Phase 1 은 이걸 고치지 않는다(OQ-2 확정).** 화면 경고 배너로만 다룬다.
    Phase 2 가 로직을 바꾸면 이 테스트가 **뒤집혀야 한다** — 그때 여기가 빨개지는 게
    "몰래 바뀌지 않았다" 의 증거다.
    """
    어제 = (date.today() - timedelta(days=1)).isoformat()
    led_path = 회차.parent.parent / "ledger" / f"{ALIAS}.json"
    ledger.save(led_path, {"ad00": {"raises": [{"date": 어제, "from": 70, "to": 80}],
                                    "streak": 0, "capped": False}})

    out = bids.run_revert({"alias": ALIAS}, 회차, commit=True, log=조용히, only_ads={"ad00"})

    assert out["committed"] == 1, "입찰가 복원(PUT) 자체는 날짜와 무관하게 성공한다"
    led = ledger.load(led_path)
    assert "reverted" not in led["ad00"]["raises"][-1], (
        "Phase 1 의 알려진 동작이다. 여기가 빨개졌다면 CLI 로직이 바뀐 것이고, "
        "그러면 화면의 Pitfall 4 경고 배너도 같이 걷어야 한다")
    assert ledger.last_raise_date(led["ad00"]) == 어제, "쿨다운이 그대로 남는다"


def test_같은_날_되돌리면_플래그가_찍힌다(회차, 네트워크차단):
    """위 테스트의 대조군. 당일이면 정상적으로 이력에 남고 쿨다운도 풀린다.

    대조군이 없으면 위 테스트는 "record_reverted 가 아예 안 도는" 상태에서도 통과한다.
    """
    오늘 = date.today().isoformat()
    led_path = 회차.parent.parent / "ledger" / f"{ALIAS}.json"
    ledger.save(led_path, {"ad00": {"raises": [{"date": 오늘, "from": 70, "to": 80}],
                                    "streak": 0, "capped": False}})

    bids.run_revert({"alias": ALIAS}, 회차, commit=True, log=조용히, only_ads={"ad00"})

    led = ledger.load(led_path)
    assert led["ad00"]["raises"][-1]["reverted"] is True
    assert ledger.last_raise_date(led["ad00"]) is None, "되돌린 인상은 쿨다운 기준에서 빠진다"


# ─────────────────────────────────────────────────────────────────────────────
# 여기부터는 **실제 프로세스**를 띄운다. "이 작업분만" 과 "이 회차 전체" 가 다른 수를
# 낸다는 것은 함수 호출로도 보이지만, 화면이 실제로 타는 경로는 argv → argparse →
# cmd_bids → run_revert 다. 그 사슬 전체를 한 번은 태워 봐야 D-12/D-13 이 증명된다.
# ─────────────────────────────────────────────────────────────────────────────

REPO = Path(__file__).resolve().parents[2]
CLI_PY = REPO / ".venv" / "bin" / "python3"          # CLI 는 언제나 자기 venv 로 돈다
RUN_ADS = SCRIPTS_DIR / "run_ads.py"


def _격리된_데이터루트(tmp_path):
    """`data_root` 를 tmp 로 돌린다. 실제 `~/python_work/data` 를 안 만진다.

    `run_ads.run_dir_of()` 는 회차 폴더를 **만든다**. tmp 회차 이름을 그냥 주면 실제
    데이터 루트에 쓰레기 폴더가 남는다 — `EROOM_WORKSPACE_TOML` 을 갈아끼워 그 경로
    자체를 tmp 로 옮긴다.
    """
    toml = tmp_path / "workspace.toml"
    toml.write_text(f'[paths]\ndata_root = "{tmp_path}"\n', encoding="utf-8")
    return dict(os.environ, EROOM_WORKSPACE_TOML=str(toml))


def _cli(env, *argv):
    return subprocess.run([str(CLI_PY), str(RUN_ADS), *argv],
                          capture_output=True, text=True, env=env, cwd=str(REPO))


def _샌드박스_회차(tmp_path, alias, 백업키들):
    """진짜 CLI 가 읽을 수 있는 회차를 tmp 안에 세운다. 광고 API 는 안 탄다(dry-run)."""
    run_dir = tmp_path / "naver-ads" / "runs" / "2026-08-30"
    acc = run_dir / "accounts" / alias
    acc.mkdir(parents=True)
    (acc / "ads.json").write_text(json.dumps({"ads": [
        {"nccAdId": k, "nccAdgroupId": "g", "adAttr": _adattr(120),
         "referenceData": {"productTitle": f"상품{k}"}} for k in 백업키들
    ]}, ensure_ascii=False), encoding="utf-8")
    (run_dir / f"before_bids_{alias}.json").write_text(
        json.dumps({k: _adattr(70, group=True) for k in 백업키들},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    return run_dir


def test_회차전체와_작업분은_다른_수다(tmp_path):
    """D-12 / D-13 의 핵심 — 같은 회차에서 **두 번 인상**했을 때를 실데이터로 못 만든다.

    실제 회차(2026-09-20)에는 인상이 한 번뿐이라 "작업분" 과 "회차 전체" 가 우연히
    같은 수다 — 그 데이터로는 분기를 증명할 수 없다. 그래서 **가짜 작업분 두 개가
    누적된 회차**를 샌드박스로 세워 진짜 CLI 를 태운다.

    백업 7건 = 작업분A 3건 + 작업분B 4건 (bids.py Important 1 의 누적 병합 결과).
      · `--only-ads <A>`  → 3건   (D-13 — 그 작업분만)
      · `--only-ads <B>`  → 4건
      · 플래그 없음       → 7건   (D-12 — 회차 전체가 풀린다)

    셋이 전부 다른 수여야 분기가 증명된다. 광고 API 는 한 번도 안 탄다(dry-run).
    """
    env = _격리된_데이터루트(tmp_path)

    계정 = json.loads(_cli(env, "accounts").stdout)
    assert 계정, "자격증명이 없으면 이 테스트는 의미가 없다"
    alias = 계정[0]["alias"]

    작업분A = ["ad00", "ad01", "ad02"]
    작업분B = ["ad03", "ad04", "ad05", "ad06"]
    _샌드박스_회차(tmp_path, alias, 작업분A + 작업분B)

    def 대상수(only=None):
        out = tmp_path / "rv.json"
        argv = ["bids", "--run-dir", "2026-08-30", "--revert",
                "--account", alias, "--preview-out", str(out)]
        if only is not None:
            대상파일 = tmp_path / "only.json"
            대상파일.write_text(json.dumps(only), encoding="utf-8")
            argv += ["--only-ads", str(대상파일)]
        p = _cli(env, *argv)
        assert p.returncode == 0, p.stdout + p.stderr
        return json.loads(out.read_text(encoding="utf-8"))[alias]["targets"]

    a, b, 전체 = 대상수(작업분A), 대상수(작업분B), 대상수()

    assert a == 3, "작업분 A 만 되돌려야 한다"
    assert b == 4, "작업분 B 만 되돌려야 한다"
    assert 전체 == 7, "플래그 없이 부르면 회차 누적분 전체가 풀린다 — 이게 D-12 의 위험이다"
    assert len({a, b, 전체}) == 3, "셋이 같은 수면 분기를 증명하지 못한 것이다"


def test_되돌리기_dry_run_은_판정결과가_없어도_돈다(tmp_path):
    """Important 4 — `--revert` 는 `result.json` 을 요구하지 않는다.

    사고 대응 경로라 판정이 깨져 있어도 되돌릴 수 있어야 한다. 위 샌드박스에는
    `result.json` 이 없는데 그대로 도는 것이 그 증거이고, 이 테스트가 그 사실을 못박는다.
    """
    env = _격리된_데이터루트(tmp_path)
    계정 = json.loads(_cli(env, "accounts").stdout)
    alias = 계정[0]["alias"]
    run_dir = _샌드박스_회차(tmp_path, alias, ["ad00"])
    assert not (run_dir / "result.json").exists()

    p = _cli(env, "bids", "--run-dir", "2026-08-30", "--revert", "--account", alias)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "판정 결과가 없다" not in p.stdout


# ─────────────────────────────────────────────────────────────────────────────
# 웹앱 쪽 (Plan 01-09 Task 2) — flow 함수 · 라우트 · 범위 가드
#
# **여기서는 진짜 CLI 를 `--revert` 쓰기로 태우지 않는다.** 자식 프로세스는 in-process
# monkeypatch 를 상속하지 않으므로, 회차 이름을 그대로 넘기면 자식이 **실제 데이터
# 루트**의 회차를 짚는다. 그래서 두 가지로 갈라 둔다:
#   · dry-run 검증 → `EROOM_WORKSPACE_TOML` 을 env 로 갈아끼워 자식도 tmp 를 보게 한다
#   · 쓰기 경로 검증 → `jobs.spawn` 을 가짜로 바꿔 **아무것도 안 띄운다**
# ─────────────────────────────────────────────────────────────────────────────
import sqlite3  # noqa: E402

from webapp import flow, jobs, paths, security, settings  # noqa: E402

회차이름 = "2026-08-30"


@pytest.fixture
def 웹회차(tmp_path, monkeypatch):
    """웹앱과 **자식 프로세스가 같은 tmp 회차를 보게** 세운다.

    `paths.data_root` 만 바꾸면 in-process 만 tmp 를 보고 자식은 실제 루트를 본다 —
    그 상태로 되돌리기를 태우면 실제 회차의 백업을 읽는다. `EROOM_WORKSPACE_TOML` 을
    같이 갈아끼워 그 간극을 없앤다.
    """
    toml = tmp_path / "workspace.toml"
    toml.write_text(f'[paths]\ndata_root = "{tmp_path}"\n', encoding="utf-8")
    monkeypatch.setenv("EROOM_WORKSPACE_TOML", str(toml))
    monkeypatch.setattr(paths, "data_root", lambda: tmp_path)
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.setattr(settings, "JOB_LOG_DIR", str(tmp_path / "logs"))

    run_dir = tmp_path / "naver-ads" / "runs" / 회차이름
    acc = run_dir / "accounts" / ALIAS
    acc.mkdir(parents=True)
    아이디들 = [f"ad{i:02d}" for i in range(백업건수)]
    (acc / "ads.json").write_text(json.dumps({"ads": [
        {"nccAdId": i, "nccAdgroupId": "g", "adAttr": _adattr(120),
         "referenceData": {"productTitle": f"상품{i}"}} for i in 아이디들
    ]}, ensure_ascii=False), encoding="utf-8")
    (run_dir / f"before_bids_{ALIAS}.json").write_text(
        json.dumps({i: _adattr(70, group=True) for i in 아이디들},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    # `paths.scan_run_dirs` 는 result.json 이 있어야 회차로 친다(화이트리스트 관문).
    (run_dir / "result.json").write_text(json.dumps(
        {"generated": 회차이름, "accounts": {ALIAS: {"summary": {}, "rules": {"①노출0": []}}}},
        ensure_ascii=False), encoding="utf-8")
    return run_dir


def _실행잡(run_dir, 성공들, 실패들=()):
    """끝난 `bids_commit` 잡 하나를 레지스트리에 세우고 산출물을 써 둔다.

    실제 CLI 를 띄우지 않는다 — `argv_override` 로 아무것도 안 하는 명령을 태운다.
    이 잡의 **산출물**이 되돌리기 대상의 유일한 근거다(D-13).
    """
    job_id = jobs.create_job("bids_commit", run_dir=회차이름, accounts=[ALIAS],
                             argv_override=[sys.executable, "-c", ""])
    상태 = jobs.job_status(job_id)
    plans = ([{"adId": i, "action": "인상", "from": 70, "to": 80, "result": "성공", "error": ""}
              for i in 성공들]
             + [{"adId": i, "action": "인상", "from": 70, "to": 80,
                 "result": "실패", "error": "500"} for i in 실패들])
    Path(상태["result_path"]).write_text(json.dumps(
        {ALIAS: {"plans": plans, "counts": {"인상": len(plans)},
                 "committed": len(성공들), "failed": len(실패들)}},
        ensure_ascii=False), encoding="utf-8")
    return job_id


# ── flow: 대상 추리기 (D-13) ────────────────────────────────────────────────

def test_되돌리기_대상은_성공한_소재만이다(웹회차):
    """D-13 — 실패한 소재를 되돌리려 들면 안 올라간 것을 내리려는 것이다."""
    job_id = _실행잡(웹회차, ["ad00", "ad01"], 실패들=["ad02"])

    대상파일 = flow.revert_targets_for_job(job_id)
    담긴것 = json.loads(대상파일.read_text(encoding="utf-8"))

    assert 담긴것 == ["ad00", "ad01"]
    assert "ad02" not in 담긴것, "실패한 소재가 되돌리기 대상에 들었다"


def test_되돌리기_대상파일은_회차_web_밑이다(웹회차):
    """`jobs._override_targets` 가 회차 밖 파일을 거부한다 — 같은 규약을 지킨다."""
    job_id = _실행잡(웹회차, ["ad00"])
    대상파일 = flow.revert_targets_for_job(job_id)
    assert 대상파일.parent == (웹회차 / "web").resolve()
    assert 대상파일.name == f"targets_revert_{job_id}.json"


def test_성공이_0건이면_되돌릴_게_없다(웹회차):
    """전량 실패한 실행에는 되돌릴 대상이 없다. 빈 파일을 만들어 '전량' 이 되게 두지 않는다."""
    job_id = _실행잡(웹회차, [], 실패들=["ad00", "ad01"])
    with pytest.raises(ValueError, match="되돌릴 게 없다"):
        flow.revert_targets_for_job(job_id)


def test_결과가_안_적힌_항목은_되돌리기_대상이_아니다(웹회차):
    """T-1-35 연장 — 실행 안 된 소재를 내리려 들면 남의 원본을 덮는다."""
    job_id = jobs.create_job("bids_commit", run_dir=회차이름, accounts=[ALIAS],
                             argv_override=[sys.executable, "-c", ""])
    상태 = jobs.job_status(job_id)
    Path(상태["result_path"]).write_text(json.dumps(
        {ALIAS: {"plans": [{"adId": "ad00", "action": "인상", "from": 70, "to": 80}],
                 "counts": {"인상": 1}}}, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="되돌릴 게 없다"):
        flow.revert_targets_for_job(job_id)


# ── flow: 회차 전체 건수 (D-14 / T-1-40) ────────────────────────────────────

def test_회차전체_건수는_백업의_키수다(웹회차):
    """D-14 — 버튼을 누르기 전에 사용자에게 보여줄 수. 계정별로 센다."""
    assert flow.revert_round_targets(회차이름) == {ALIAS: 백업건수}


def test_회차전체_건수는_백업을_읽기만_한다(웹회차):
    """T-1-40 — 건수를 세려고 연 파일을 쓰지 않는다."""
    bk = 웹회차 / f"before_bids_{ALIAS}.json"
    원본 = bk.read_bytes()
    flow.revert_round_targets(회차이름)
    assert bk.read_bytes() == 원본


def test_되돌릴_수_없는_항목은_안_센다(웹회차):
    """백업 값이 `None` 인 키는 원본을 못 남긴 소재다 — 되돌릴 수 없으니 건수에서 뺀다."""
    bk = 웹회차 / f"before_bids_{ALIAS}.json"
    백업 = json.loads(bk.read_text(encoding="utf-8"))
    백업["ad00"] = None
    bk.write_text(json.dumps(백업, ensure_ascii=False), encoding="utf-8")
    assert flow.revert_round_targets(회차이름) == {ALIAS: 백업건수 - 1}


def test_백업이_깨졌으면_건수를_지어내지_않는다(웹회차):
    """0 으로 돌려주면 '되돌릴 게 없다' 와 '못 셌다' 가 같은 화면이 된다."""
    (웹회차 / f"before_bids_{ALIAS}.json").write_text("{깨짐", encoding="utf-8")
    with pytest.raises(ValueError):
        flow.revert_round_targets(회차이름)


def test_백업이_없는_회차는_0건이다(웹회차):
    (웹회차 / f"before_bids_{ALIAS}.json").unlink()
    assert flow.revert_round_targets(회차이름) == {}


# ── flow: 범위 가드 (Pitfall 2 / T-1-08) ────────────────────────────────────

def test_범위가_다르면_막는다():
    """Pitfall 2 의 마지막 방어선. 조기 신호는 '대상 수가 방금 실행한 건수보다 크다' 다."""
    flow.check_revert_scope(3, 3)
    with pytest.raises(flow.ScopeError) as e:
        flow.check_revert_scope(3, 2242)
    assert "2,242" in str(e.value) or "2242" in str(e.value)
    assert isinstance(e.value, ValueError), "라우트가 ValueError 로도 잡을 수 있어야 한다"


def test_dry_run_이_진짜_CLI_에게_범위를_물어본다(tmp_path, monkeypatch):
    """T-1-42 — 쓰기 전에 **CLI 가 직접 센 수**를 받는다. 웹앱이 추정하지 않는다.

    여기만 계정 alias 를 진짜로 쓴다 — `--account` 는 자격증명 파일에 있는 이름만
    통과하고, 없는 이름을 주면 계정이 0개가 되어 **targets 0 이 조용히 나온다**.
    그 0 을 "되돌릴 게 없다" 로 읽으면 이 가드는 있는 척만 한다. 이름은 박지 않고
    `run_ads.py accounts` 에게 물어본다(BOARD-02).

    자식이 tmp 회차를 보도록 `EROOM_WORKSPACE_TOML` 을 갈아끼운다. 광고 API 는
    안 탄다 — dry-run 이다.
    """
    toml = tmp_path / "workspace.toml"
    toml.write_text(f'[paths]\ndata_root = "{tmp_path}"\n', encoding="utf-8")
    monkeypatch.setenv("EROOM_WORKSPACE_TOML", str(toml))
    monkeypatch.setattr(paths, "data_root", lambda: tmp_path)

    계정 = json.loads(_cli(dict(os.environ), "accounts").stdout)
    assert 계정, "자격증명이 없으면 이 테스트는 의미가 없다"
    alias = 계정[0]["alias"]
    run_dir = _샌드박스_회차(tmp_path, alias, [f"ad{i:02d}" for i in range(백업건수)])

    대상파일 = run_dir / "web" / "targets_revert_test.json"
    대상파일.parent.mkdir(parents=True, exist_ok=True)
    대상파일.write_text(json.dumps(["ad00", "ad01", "ad02"]), encoding="utf-8")

    좁힘 = flow.revert_dry_run(회차이름, accounts=[alias], only_ads=대상파일)
    전체 = flow.revert_dry_run(회차이름, accounts=[alias])

    assert 좁힘["targets"] == 3
    assert 전체["targets"] == 백업건수
    assert 좁힘["by_account"][alias] == 3
    # 이 대비가 D-12 다 — 같은 명령에 대상 파일 하나 차이로 3 과 10 이 갈린다.
    flow.check_revert_scope(3, 좁힘["targets"])
    with pytest.raises(flow.ScopeError):
        flow.check_revert_scope(3, 전체["targets"])


# ── 라우트 (D-13 / D-14 / Pitfall 3) ────────────────────────────────────────

@pytest.fixture
def 자식금지(monkeypatch):
    """`jobs.spawn` 을 막는다. **되돌리기 쓰기를 테스트에서 절대 띄우지 않는다.**

    자식은 in-process monkeypatch 를 상속하지 않아서, 한 번 새면 실제 회차의 백업을
    읽고 실제 광고 API 에 PUT 을 낸다. 여기가 이 파일에서 제일 중요한 한 줄이다.
    """
    띄운것 = []

    class 가짜프로세스:
        pid = 999999

        def poll(self):
            return 0

    def 가짜spawn(argv_list, log_path):
        띄운것.append(list(argv_list))
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        Path(log_path).write_text("", encoding="utf-8")
        return 가짜프로세스()

    monkeypatch.setattr(jobs, "spawn", 가짜spawn)
    return 띄운것


def _되돌리기가_떴나(띄운것):
    """**되돌리기** 자식이 떴는지만 본다.

    `자식금지` 는 픽스처 준비용 잡(실행 잡·미리보기 잡)까지 전부 기록한다 —
    "아무것도 안 떴다" 로 단언하면 준비 단계 때문에 늘 빨갛다. 여기서 막고 싶은 것은
    되돌리기 명령이 나가는 것뿐이다.
    """
    return any("--revert" in av for av in 띄운것)


def _argv(job_id):
    cx = sqlite3.connect(jobs.db_path())
    try:
        return json.loads(cx.execute("SELECT argv FROM jobs WHERE id=?", (job_id,)).fetchone()[0])
    finally:
        cx.close()


def test_작업분_되돌리기는_대상파일을_싣는다(웹회차, 자식금지, client, monkeypatch):
    """D-13 — argv 에 되돌리기 플래그와 **그 작업분 대상 파일**이 둘 다 있다."""
    monkeypatch.setattr(flow, "revert_dry_run",
                        lambda *a, **k: {"targets": 2, "by_account": {ALIAS: 2}})
    부모 = _실행잡(웹회차, ["ad00", "ad01"])

    r = client.post("/jobs/revert/job", json={"commit_job_id": 부모})
    assert r.status_code == 200, r.text

    av = _argv(r.json()["job_id"])
    assert "--revert" in av
    assert "--only-ads" in av
    대상 = av[av.index("--only-ads") + 1]
    assert 대상.endswith(f"targets_revert_{부모}.json")
    assert json.loads(Path(대상).read_text(encoding="utf-8")) == ["ad00", "ad01"]


def test_회차전체_되돌리기는_대상파일이_없다(웹회차, 자식금지, client, monkeypatch):
    """D-12/D-14 — 이쪽은 좁히지 않는다. 대상 파일 유무가 두 버튼의 차이 전부다."""
    monkeypatch.setattr(flow, "revert_dry_run",
                        lambda *a, **k: {"targets": 백업건수, "by_account": {ALIAS: 백업건수}})

    r = client.post("/jobs/revert/round",
                    json={"run_dir": 회차이름, "confirmed_count": 백업건수})
    assert r.status_code == 200, r.text

    av = _argv(r.json()["job_id"])
    assert "--revert" in av
    assert "--only-ads" not in av


def test_화면이_본_건수와_다르면_거부한다(웹회차, 자식금지, client, monkeypatch):
    """D-14 — 화면이 9건을 보여줬는데 서버가 10건을 세면 그 클릭은 무효다.

    **범위 가드를 일부러 통과시켜 놓고 본다.** dry-run 을 실제 값으로 고정하지 않으면
    이 테스트는 "confirmed_count 대조" 가 아니라 그 **뒤의** `check_revert_scope` 가
    내는 409 를 보고 초록이 된다 — 대조를 통째로 지워도 통과하는 가짜 초록이다
    (음성 대조군에서 실제로 걸렸다).
    """
    부른적 = []
    monkeypatch.setattr(flow, "revert_dry_run",
                        lambda *a, **k: 부른적.append(1) or
                        {"targets": 백업건수, "by_account": {ALIAS: 백업건수}})

    r = client.post("/jobs/revert/round",
                    json={"run_dir": 회차이름, "confirmed_count": 백업건수 - 1})

    assert r.status_code == 409
    assert "화면이 본 건수" in r.json()["detail"]
    assert str(백업건수) in r.json()["detail"]
    assert 부른적 == [], "대조에서 막혔어야 하는데 dry-run 까지 갔다"
    assert not _되돌리기가_떴나(자식금지)


def test_범위가_안_맞으면_실행_전에_막힌다(웹회차, 자식금지, client, monkeypatch):
    """Pitfall 2 — dry-run 이 부모 성공 건수보다 큰 수를 내면 접수 자체를 거부한다."""
    monkeypatch.setattr(flow, "revert_dry_run",
                        lambda *a, **k: {"targets": 2242, "by_account": {ALIAS: 2242}})
    부모 = _실행잡(웹회차, ["ad00", "ad01"])

    r = client.post("/jobs/revert/job", json={"commit_job_id": 부모})
    assert r.status_code == 409
    assert "2,242" in r.json()["detail"] or "2242" in r.json()["detail"]
    assert not _되돌리기가_떴나(자식금지), "범위가 안 맞는데 되돌리기가 떴다"


def test_미리보기_잡은_되돌릴_수_없다(웹회차, 자식금지, client):
    """되돌리기는 **실행한 작업**에만 건다. 미리보기 잡의 대상 파일은 의미가 다르다."""
    job_id = jobs.create_job("bids_preview", run_dir=회차이름, accounts=[ALIAS],
                             only_ads=["ad00"])
    r = client.post("/jobs/revert/job", json={"commit_job_id": job_id})
    assert r.status_code == 400
    assert not _되돌리기가_떴나(자식금지)


def test_실행이_아직_도는데_되돌리면_거부한다(웹회차, 자식금지, client):
    """무엇이 올라갔는지 아직 모르는 상태다 — 산출물이 확정되기 전이다."""
    job_id = jobs.create_job("bids_commit", run_dir=회차이름, accounts=[ALIAS],
                             argv_override=[sys.executable, "-c", ""])
    r = client.post("/jobs/revert/job", json={"commit_job_id": job_id})
    assert r.status_code == 400
    assert not _되돌리기가_떴나(자식금지), "도는 중인데 되돌리기가 떴다"


def test_되돌리기_도는_중엔_다른_쓰기가_409다(웹회차, 자식금지, client, monkeypatch):
    """Pitfall 3 / T-1-09 — 되돌리기도 쓰기 잡이라 전역 가드를 탄다.

    겹치면 `before_bids_*.json` 과 ledger 가 read-modify-write 레이스로 서로를 덮는다.
    백업 항목이 사라지면 **그 소재는 영영 되돌릴 수 없다.**
    """
    monkeypatch.setattr(flow, "revert_dry_run",
                        lambda *a, **k: {"targets": 백업건수, "by_account": {ALIAS: 백업건수}})

    r1 = client.post("/jobs/revert/round",
                     json={"run_dir": 회차이름, "confirmed_count": 백업건수})
    assert r1.status_code == 200

    # 가짜 자식은 끝나지 않는다(poll()=0 을 주지만 _PROCS 에 없는 상태를 만든다).
    # 실제로 도는 상태를 만들려고 pid 를 살아 있는 이 프로세스로 바꾼다 —
    # `_reap` 이 "죽었다" 고 판단해 가드를 풀어 버리면 이 테스트가 의미를 잃는다.
    cx = sqlite3.connect(jobs.db_path())
    try:
        cx.execute("UPDATE jobs SET status='running', pid=? WHERE id=?",
                   (os.getpid(), r1.json()["job_id"]))
        cx.commit()
    finally:
        cx.close()
    jobs._PROCS.pop(r1.json()["job_id"], None)

    r2 = client.post("/jobs/revert/round",
                     json={"run_dir": 회차이름, "confirmed_count": 백업건수})
    assert r2.status_code == 409, r2.text

    r3 = client.post("/jobs/prep", json={"run_dir": 회차이름})
    assert r3.status_code == 409, "되돌리기 중에 새로 수집이 떴다 — 백업이 깨진다"


def test_되돌리기_결과는_되돌리기_표로_그린다(웹회차, 자식금지, client, monkeypatch):
    """FLOW-05 연장 — 되돌리기 잡의 산출물을 인상 표로 그리면 '인상 후' 칸이 거짓말이 된다."""
    monkeypatch.setattr(flow, "revert_dry_run",
                        lambda *a, **k: {"targets": 백업건수, "by_account": {ALIAS: 백업건수}})
    r = client.post("/jobs/revert/round",
                    json={"run_dir": 회차이름, "confirmed_count": 백업건수})
    job_id = r.json()["job_id"]

    상태 = jobs.job_status(job_id)
    Path(상태["result_path"]).write_text(json.dumps({ALIAS: {
        "targets": 2, "committed": 1, "failed": 1,
        "plans": [{"adId": "ad00", "action": "되돌리기", "to": 70, "useGroupBid": True,
                   "result": "성공", "error": ""},
                  {"adId": "ad01", "action": "되돌리기", "to": 70, "useGroupBid": True,
                   "result": "실패", "error": "500 서버 오류"}]}},
        ensure_ascii=False), encoding="utf-8")

    client.cookies.set(security.COOKIE_NAME, security.BOOT_TOKEN)   # 읽기 창은 쿠키 게이트다
    ctx = client.get(f"/jobs/{job_id}/result?format=json").json()
    assert ctx["result_counts"]["성공"] == 1
    assert ctx["result_counts"]["실패"] == 1
    assert ctx["succeeded"] == 1

    조각 = client.get(f"/jobs/{job_id}/result", headers={"HX-Request": "true"}).text
    assert "되돌" in 조각
    assert "인상 후" not in 조각, "되돌리기 결과에 인상 표를 그리면 안 된다"


# ── 화면 (D-14 / T-1-43) ────────────────────────────────────────────────────

def test_두_버튼은_같은_화면조각에_없다(웹회차, 자식금지, client):
    """D-14 / T-1-43 — 실수로 옆 버튼을 누르는 게 이 화면의 최대 위험이다.

    서버가 보장할 수 있는 절반: **두 버튼이 다른 조각에서 온다.** 보드 페이지에는
    "이 작업분만" 버튼이 없고, 결과 표 조각에는 "회차 전체" 버튼이 없다.
    화면상의 실제 거리는 `webapp/tests/revert_cdp.sh` 가 픽셀로 잰다.
    """
    client.cookies.set(security.COOKIE_NAME, security.BOOT_TOKEN)
    보드 = client.get(f"/?run_dir={회차이름}").text

    assert 'id="revert-round-btn"' in 보드
    assert 'id="revert-job-btn"' not in 보드, "회차 전체 버튼 옆에 작업분 버튼이 있다"
    # 기본 접힘 — 한 번 더 펼쳐야 보인다.
    assert "<details" in 보드.split('id="danger-zone"')[1].split("</section>")[0]


def test_회차전체_버튼은_확인단계를_거친다(웹회차, 자식금지, client):
    """D-14 — 누르는 즉시 접수되지 않는다. 건수를 보여주고 승인을 받는다."""
    client.cookies.set(security.COOKIE_NAME, security.BOOT_TOKEN)
    위험구역 = client.get(f"/?run_dir={회차이름}").text.split('id="danger-zone"')[1]

    assert 'id="revert-round-confirm"' in 위험구역
    assert 'id="revert-round-ok"' in 위험구역
    assert 'id="revert-round-cancel"' in 위험구역
    # 건수를 템플릿에 박지 않는다 — 누르는 순간 서버에 물어본다.
    assert str(백업건수) not in 위험구역.split("</section>")[0]


def test_건수_조회는_읽기전용이다(웹회차, 자식금지, client):
    """확인 단계가 쓰는 수. 백업을 **열어서 세기만** 한다 (T-1-40)."""
    client.cookies.set(security.COOKIE_NAME, security.BOOT_TOKEN)
    bk = 웹회차 / f"before_bids_{ALIAS}.json"
    원본 = bk.read_bytes()

    j = client.get(f"/jobs/revert/round/count?run_dir={회차이름}").json()

    assert j["total"] == 백업건수
    assert j["by_account"] == {ALIAS: 백업건수}
    assert bk.read_bytes() == 원본
    assert 자식금지 == [], "읽기 창이 작업을 만들었다"


def test_결과표에_되돌리기_버튼과_건수가_있다(웹회차, 자식금지, client):
    """화면이 보여주는 수 == 서버가 되돌릴 수. 둘이 갈라지면 사람이 규모를 오독한다."""
    client.cookies.set(security.COOKIE_NAME, security.BOOT_TOKEN)
    job_id = _실행잡(웹회차, ["ad00", "ad01"], 실패들=["ad02"])

    조각 = client.get(f"/jobs/{job_id}/result", headers={"HX-Request": "true"}).text

    assert 'id="revert-job-btn"' in 조각
    assert f'data-n="2"' in 조각, "실패 1건까지 세면 안 된다"
    assert 'id="revert-round-btn"' not in 조각, "결과 표에 회차 전체 버튼을 두면 안 된다"


def test_성공이_0건이면_버튼이_잠긴다(웹회차, 자식금지, client):
    """되돌릴 게 없는데 열려 있으면 누르고 나서야 400 을 본다."""
    client.cookies.set(security.COOKIE_NAME, security.BOOT_TOKEN)
    job_id = _실행잡(웹회차, [], 실패들=["ad00"])

    조각 = client.get(f"/jobs/{job_id}/result", headers={"HX-Request": "true"}).text

    assert "disabled" in 조각.split('id="revert-job-btn"')[1].split(">")[0]
    assert "되돌릴 게 없다" in 조각


def test_인상일이_어제면_경고배너가_뜬다(웹회차, 자식금지, client, monkeypatch):
    """Pitfall 4 / OQ-2 — 날짜를 넘겼다는 사실을 **누르기 전에** 말한다."""
    client.cookies.set(security.COOKIE_NAME, security.BOOT_TOKEN)
    job_id = _실행잡(웹회차, ["ad00"])

    어제 = (date.today() - timedelta(days=1)).isoformat()
    cx = sqlite3.connect(jobs.db_path())
    try:
        cx.execute("UPDATE jobs SET started_at=? WHERE id=?", (어제 + "T21:00:00+09:00", job_id))
        cx.commit()
    finally:
        cx.close()

    조각 = client.get(f"/jobs/{job_id}/result", headers={"HX-Request": "true"}).text
    assert "날짜를 넘겼다" in 조각
    assert 어제 in 조각
    assert "쿨다운" in 조각


def test_인상일이_오늘이면_배너가_없다(웹회차, 자식금지, client):
    """대조군 — 배너가 **늘 떠 있으면** 경고가 아니라 배경이 된다."""
    client.cookies.set(security.COOKIE_NAME, security.BOOT_TOKEN)
    job_id = _실행잡(웹회차, ["ad00"])
    조각 = client.get(f"/jobs/{job_id}/result", headers={"HX-Request": "true"}).text
    assert "날짜를 넘겼다" not in 조각
