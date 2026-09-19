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
