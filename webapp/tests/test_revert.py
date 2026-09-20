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
