#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI 패치(`--only-ads` · `--preview-out` · 항목단위 결과) 회귀 테스트.

여기서 지키는 것은 **광고비다.** 세 가지를 기계로 못박는다:
  회귀-02  `--only-ads` 를 안 주면 패치 전과 똑같이 돈다
  회귀-03  필터를 걸어도 `update_streaks` 는 rows 전량을 본다 (T-1-04)
  FLOW-05  실행 결과가 항목 단위로 성공/실패/스킵 + 사유를 갖는다 (T-1-15)

네트워크를 타지 않는다 — `bids.nvad.call` 을 전부 몽키패치한다.
"""
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

# `.claude/skills/naver-ads-weekly/scripts` 를 import 경로에 넣는다.
#
# **이 sys.path 삽입은 테스트 프로세스에만 허용된다.** 웹앱 런타임(`webapp/*.py`)은
# 절대 이걸 하지 않는다 — `bids`·`collect`·`nvad` 는 네임스페이스 없는 최상위 이름이라
# stdlib 을 가릴 수 있다(RESEARCH §5.6 에서 `inspect` 로 실제 재현됨). 웹앱은 subprocess
# 경계로만 CLI 를 부른다. 여기서만, 테스트 격리 목적으로 허용한다.
# (`bids.py` 는 stdlib + `ledger` + `nvad` 만 import 하므로 `.venv-web` 에서도 돈다)
SCRIPTS_DIR = Path(__file__).resolve().parents[2] / ".claude" / "skills" / "naver-ads-weekly" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import bids  # noqa: E402
import ledger  # noqa: E402

ALIAS = "cy728"


def row(ad_id, bid=100, title="상품"):
    """`result.json` 의 `①노출0` 한 줄 모양. test_bids.py:19 의 헬퍼와 같은 계약이다."""
    return {"adId": ad_id, "bid": bid, "useGroupBid": False, "groupBid": 70, "title": title}


@pytest.fixture
def 회차(tmp_path):
    """`tmp/runs/<회차>` **2단 구조**를 만든다.

    `bids.py:130` 이 ledger 를 `run_dir.parent.parent/"ledger"` 로 찾는다 —
    한 단이라도 빠뜨리면 테스트가 tmp 밖(실제 ledger)을 오염시킨다.
    """
    run_dir = tmp_path / "runs" / "2026-08-30"
    acc = run_dir / "accounts" / ALIAS
    acc.mkdir(parents=True)
    (acc / "stats_7d.json").write_text("{}", encoding="utf-8")
    (acc / "ads.json").write_text(json.dumps({"ads": [
        {"nccAdId": "a", "adAttr": {"bidAmt": 100, "useGroupBidAmt": False}},
        {"nccAdId": "b", "adAttr": {"bidAmt": 100, "useGroupBidAmt": False}},
        {"nccAdId": "c", "adAttr": {"bidAmt": 100, "useGroupBidAmt": False}},
    ]}), encoding="utf-8")
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


def test_only_ads_none_은_전량과_같다(회차, 네트워크차단):
    """회귀-02 — 새 인자를 안 주는 기존 호출부가 패치 전과 바이트 단위로 같아야 한다."""
    rows = [row("a"), row("b"), row("c")]
    조용히 = lambda *a, **k: None  # noqa: E731

    기존 = bids.run_bids({"alias": ALIAS}, 회차, rows, log=조용히)
    명시 = bids.run_bids({"alias": ALIAS}, 회차, rows, log=조용히, only_ads=None)

    assert 기존["plans"] == 명시["plans"]
    assert 기존["counts"] == 명시["counts"]
    assert len(기존["plans"]) == 3


def test_필터해도_streak_은_전량기준(회차, 네트워크차단, monkeypatch):
    """회귀-03 / T-1-04 — 필터를 `update_streaks` **뒤**에 걸었는지 검사한다.

    이 테스트 하나가 OQ-1 확정(필터를 `cmd_bids` 나 `update_streaks` 앞이 아니라
    `run_bids` 안쪽·`plan_raise` 직전에 건다)의 **유일한 자동 방어선**이다.
    앞에서 거르면 나머지 소재의 연속실패 카운팅이 이번 회차에 통째로 빠지고,
    `_last_streak_update=today` 가 찍혀 같은 날 도는 전량 실행마저 건너뛴다 (Pitfall 5).
    """
    본것 = {}

    def fake_update_streaks(led, zero_ids, recovered_ids, run_date, log=print):
        본것["zero_ids"] = set(zero_ids)
        return 0, 0

    monkeypatch.setattr(bids, "update_streaks", fake_update_streaks)

    rows = [row("a"), row("b"), row("c")]
    out = bids.run_bids({"alias": ALIAS}, 회차, rows, log=lambda *a, **k: None, only_ads={"a"})

    assert len(out["plans"]) == 1, "필터가 plan_raise 앞에서 걸려야 한다"
    assert out["plans"][0]["adId"] == "a"
    assert 본것["zero_ids"] == {"a", "b", "c"}, "update_streaks 는 rows 전량을 봐야 한다"


def test_항목단위_결과(회차, monkeypatch):
    """FLOW-05 / T-1-15 — 실행 결과가 항목별 성공·실패·스킵 + 사유를 갖는다.

    로그 파싱이 아니라 `plans[i]["result"]` / `plans[i]["error"]` 로 남는다.
    `c` 는 오늘 이미 올린 이력이 있어 쿨다운(`RAISE_COOLDOWN_DAYS=6`)에 걸려 "최근인상" 스킵이다.
    """
    today = date.today().isoformat()
    led_path = 회차.parent.parent / "ledger" / f"{ALIAS}.json"
    ledger.save(led_path, {"c": {"raises": [{"date": today, "from": 90, "to": 100}],
                                 "streak": 0, "capped": False}})

    # 소재별로 응답을 가른다. `seq.pop(0)` 을 쓰지 않는 이유: 500 은 Important 9 의
    # 재시도 대상이라 한 소재가 응답을 4개 소비한다 — 순번 방식은 IndexError 로 터진다.
    def fake_call(acct, method, path, params=None, body=None, raw=False):
        return (200, {}) if path.endswith("/a") else (500, "서버 오류")

    monkeypatch.setattr(bids.nvad, "call", fake_call)
    monkeypatch.setattr(bids.time, "sleep", lambda *_: None)

    rows = [row("a"), row("b"), row("c")]
    out = bids.run_bids({"alias": ALIAS}, 회차, rows, commit=True, log=lambda *a, **k: None)

    결과 = {p["adId"]: (p["result"], p["error"]) for p in out["plans"]}
    assert 결과["a"] == ("성공", "")
    assert 결과["b"][0] == "실패"
    assert "500" in 결과["b"][1]
    assert 결과["c"] == ("스킵", "최근인상")
    assert (out["committed"], out["failed"]) == (1, 1)


def test_dry_run_은_결과를_말하지_않는다(회차, 네트워크차단):
    """아직 실행하지 않았으므로 "성공"이라고 말하면 거짓말이다."""
    out = bids.run_bids({"alias": ALIAS}, 회차, [row("a")], log=lambda *a, **k: None)
    assert "result" not in out["plans"][0]
    assert len(네트워크차단) == 0


def test_스냅샷에_소재가_없으면_실패로_남는다(회차, 네트워크차단):
    """prep 이후 소재가 삭제된 경우(Pitfall 7) — 스냅샷 기반 실행의 정상적 실패다."""
    out = bids.run_bids({"alias": ALIAS}, 회차, [row("zzz")], commit=True,
                        log=lambda *a, **k: None)
    assert out["plans"][0]["result"] == "실패"
    assert out["plans"][0]["error"] == "스냅샷에 소재 없음"
    assert len(네트워크차단) == 0


def test_revert_도_고른것만_되돌린다(회차, 네트워크차단):
    """D-13 — `only_ads` 로 대상이 좁혀지고, 백업 파일 자체는 **바뀌지 않는다**."""
    bk = 회차 / f"before_bids_{ALIAS}.json"
    백업원본 = {k: {"bidAmt": 100, "useGroupBidAmt": False} for k in ("a", "b", "c")}
    bk.write_text(json.dumps(백업원본, ensure_ascii=False, indent=1), encoding="utf-8")

    out = bids.run_revert({"alias": ALIAS}, 회차, log=lambda *a, **k: None,
                          only_ads={"a", "b", "c"})
    assert out["targets"] == 3

    좁힘 = bids.run_revert({"alias": ALIAS}, 회차, log=lambda *a, **k: None, only_ads={"a"})
    assert 좁힘["targets"] == 1

    전량 = bids.run_revert({"alias": ALIAS}, 회차, log=lambda *a, **k: None)
    assert 전량["targets"] == 3, "only_ads 를 안 주면 백업 전량이 대상이다(기존 동작 불변)"

    assert json.loads(bk.read_text(encoding="utf-8")) == 백업원본, "run_revert 는 백업을 쓰지 않는다"


# ─────────────────────────────────────────────────────────────────────────────
# 여기부터는 **실제 프로세스**를 띄운다. CLI 계약(종료코드·산출물 파일)은
# 함수 호출로는 증명할 수 없다 — argparse·main()·종료코드가 그 계약의 일부다.
# ─────────────────────────────────────────────────────────────────────────────

REPO = Path(__file__).resolve().parents[2]
CLI_PY = REPO / ".venv" / "bin" / "python3"          # CLI 는 언제나 자기 venv 로 돈다
RUN_ADS = SCRIPTS_DIR / "run_ads.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _격리된_데이터루트(tmp_path):
    """`data_root` 를 tmp 로 돌리는 환경을 만든다. 실제 `~/python_work/data` 를 안 만진다.

    `run_ads.run_dir_of()` 는 회차 폴더를 **만든다**(`mkdir(parents=True, exist_ok=True)`).
    tmp 회차 이름을 그냥 주면 실제 데이터 루트에 쓰레기 폴더가 남는다. `eroomlib.config`
    가 보는 `EROOM_WORKSPACE_TOML` 을 갈아끼워 그 경로 자체를 tmp 로 옮긴다.
    """
    toml = tmp_path / "workspace.toml"
    toml.write_text(f'[paths]\ndata_root = "{tmp_path}"\n', encoding="utf-8")
    env = dict(os.environ, EROOM_WORKSPACE_TOML=str(toml))
    return env, tmp_path


def _cli(env, *argv):
    return subprocess.run([str(CLI_PY), str(RUN_ADS), *argv],
                          capture_output=True, text=True, env=env, cwd=str(REPO))


def test_only_ads_깨지면_실패한다(tmp_path):
    """회귀-04 / T-1-05 — 대상 파일이 깨지면 **exit 1**. 전량 실행으로 번지지 않는다.

    5건인 줄 알았던 게 2,242건이 되는 게 이 명령의 가장 비싼 실수다.
    실제 프로세스를 띄우는 이유: 종료코드가 CLI 계약의 일부라 함수 호출로는 증명이 안 된다.
    """
    env, _ = _격리된_데이터루트(tmp_path)
    p = _cli(env, "bids", "--run-dir", "2026-08-30",
             "--only-ads", str(FIXTURES / "targets_broken.json"))

    assert p.returncode == 1, f"깨진 대상 파일은 중단이어야 한다: {p.stdout}{p.stderr}"
    assert "폴백하지 않는다" in p.stdout
    assert "대상" not in p.stdout, "한 계정도 처리에 들어가면 안 된다"


def test_only_ads_파일이_없어도_실패한다(tmp_path):
    """파일 부재도 같은 취급이다 — 없는 대상 파일을 '전량' 으로 읽지 않는다."""
    env, _ = _격리된_데이터루트(tmp_path)
    p = _cli(env, "bids", "--run-dir", "2026-08-30", "--only-ads", str(tmp_path / "없다.json"))
    assert p.returncode == 1
    assert "폴백하지 않는다" in p.stdout


def test_preview_out_이_전량을_쓴다(tmp_path):
    """D-02 — stdout 은 10건에서 접지만 산출물은 전량이다.

    dry-run 이라 네트워크를 타지 않는다 — 쓰기 플래그를 안 주면 run_bids 는 계획만 세우고
    돌아온다. 그 플래그 이름을 여기 적지 않는 이유는 `no_commit_guard.sh` 가 이 파일도
    훑기 때문이다(주석이든 코드든 글자 자체가 없어야 한다 — 그게 이 가드의 요지다).
    계정 alias 는 `run_ads.py accounts` 에서 받아온다 — 테스트에도 계정을 박지 않는다(BOARD-02).
    """
    env, root = _격리된_데이터루트(tmp_path)

    계정 = json.loads(_cli(env, "accounts").stdout)
    assert 계정, "자격증명이 없으면 이 테스트는 의미가 없다"
    alias = 계정[0]["alias"]

    run_dir = root / "naver-ads" / "runs" / "2026-08-30"
    acc = run_dir / "accounts" / alias
    acc.mkdir(parents=True)
    행 = [row(f"ad{i:02d}", bid=100, title=f"상품{i}") for i in range(12)]
    (run_dir / "result.json").write_text(json.dumps(
        {"generated": "2026-08-30", "accounts": {alias: {"summary": {}, "rules": {"①노출0": 행}}}},
        ensure_ascii=False), encoding="utf-8")
    (acc / "stats_7d.json").write_text("{}", encoding="utf-8")
    (acc / "ads.json").write_text(json.dumps({"ads": [
        {"nccAdId": r["adId"], "adAttr": {"bidAmt": 100, "useGroupBidAmt": False}} for r in 행
    ]}), encoding="utf-8")

    out = tmp_path / "preview.json"
    p = _cli(env, "bids", "--run-dir", "2026-08-30", "--preview-out", str(out))

    assert p.returncode == 0, p.stdout + p.stderr
    assert "… 외 2건" in p.stdout, "stdout 은 여전히 10건에서 접는다(기존 동작 불변)"
    산출 = json.loads(out.read_text(encoding="utf-8"))
    assert len(산출[alias]["plans"]) == 12, "산출물은 stdout 접기와 무관하게 전량이다"
    assert 산출[alias]["counts"] == {"인상": 12}
    assert "result" not in 산출[alias]["plans"][0], "dry-run 은 아직 결과를 말하지 않는다"
    assert "상품11" in out.read_text(encoding="utf-8"), "한국어가 \\uXXXX 로 깨지지 않는다"


def test_accounts_는_시크릿을_찍지_않는다(tmp_path):
    """SAFE-03 / T-1-03b — 웹앱이 자격증명 파일을 두 번째로 갖지 않게 하는 통로."""
    env, _ = _격리된_데이터루트(tmp_path)
    p = _cli(env, "accounts")
    assert p.returncode == 0
    목록 = json.loads(p.stdout)
    assert isinstance(목록, list)
    for a in 목록:
        assert set(a) == {"alias", "customer_id"}, f"화이트리스트 밖의 키가 샜다: {a}"
