#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""꺼진 소재 정리 CLI(`run_ads.py prune`) 주입구 계약 테스트.

여기서 지키는 것은 **되돌릴 수 없는 삭제다.** 웹(02-03)과 보드(02-04)가 읽을 산출물
스키마와 종료코드를 기계로 못박는다:
  PRUNE-01/03  dry-run 산출물이 전 계정 전 행 + 최상위 adIds·total 을 쓴다
  SAFE-06      그 산출물 파일 자체가 다음 실행의 대상 목록 입력이 된다
  SAFE-07      상한 초과는 백업 전에 exit 2 로 전량 거부(자르지 않는다)
  SAFE-04      잡별 백업 태그 · 태그 경로 조작 거부

**subprocess 는 dry-run 만 띄운다.** 쓰기 경로를 subprocess 로 띄우면 실제 자격증명으로
DELETE 가 나간다(RESEARCH Anti-Patterns). 쓰기 경로는 in-process 로 `cmd_prune` 을 직접
부르고 네트워크 함수를 전부 몽키패치한다. 쓰기 플래그 리터럴은 이 파일에 없다 —
`no_commit_guard.sh` 가 훑는다. Namespace 키워드로만 켠다.
"""
import argparse
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
SCRIPTS_DIR = Path(__file__).resolve().parents[2] / ".claude" / "skills" / "naver-ads-weekly" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import prune  # noqa: E402
import run_ads  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
CLI_PY = REPO / ".venv" / "bin" / "python3"          # CLI 는 언제나 자기 venv 로 돈다
RUN_ADS = SCRIPTS_DIR / "run_ads.py"
회차명 = "2026-08-30"
오늘 = date.today().isoformat()


def 소재(ad_id, enable=False, reason="AD_ABNORMAL_INTERLOCK", title="상품", mall="m1", group="g1"):
    """ads.json 의 소재 1건 — 실측 키 모양 그대로(referenceData.productTitle/mallProductId)."""
    return {"nccAdId": ad_id, "nccAdgroupId": group, "enable": enable, "statusReason": reason,
            "referenceKey": f"ref-{ad_id}", "type": "SHOPPING_PRODUCT_AD",
            "adAttr": {"bidAmt": 100}, "status": "PAUSED", "inspectStatus": "APPROVED",
            "regTm": "2026-01-01T00:00:00Z", "editTm": "2026-08-01T00:00:00Z",
            "referenceData": {"mallProductId": mall, "productTitle": title}}


def 기본소재():
    """연동끊김 3 · 검수중 1 · 거부 1 — 대상은 3건, 남김 2건."""
    return [소재("a1", title="한국어상품하나"), 소재("a2", title="한국어상품둘"),
            소재("a3", title="한국어상품셋"),
            소재("r1", reason="AD_UNDER_REVIEW"), 소재("d1", reason="AD_DISAPPROVED")]


def _격리된_데이터루트(tmp_path):
    """`data_root` 를 tmp 로 돌린다. 실제 `~/python_work/data` 를 안 만진다(test_cli_patch 와 같은 방식)."""
    toml = tmp_path / "workspace.toml"
    toml.write_text(f'[paths]\ndata_root = "{tmp_path}"\n', encoding="utf-8")
    env = dict(os.environ, EROOM_WORKSPACE_TOML=str(toml))
    return env, tmp_path


def _cli(env, *argv):
    return subprocess.run([str(CLI_PY), str(RUN_ADS), *argv],
                          capture_output=True, text=True, env=env, cwd=str(REPO))


def _회차박기(root, alias, ads_list):
    acc = root / "naver-ads" / "runs" / 회차명 / "accounts" / alias
    acc.mkdir(parents=True)
    (acc / "ads.json").write_text(json.dumps(
        {"ads": ads_list, "groups": {"g1": {"name": "판매상품_6-2_테스트", "bidAmt": 70}}},
        ensure_ascii=False), encoding="utf-8")
    return acc


def _백업들(root):
    d = root / "naver-ads" / "paused-backup"
    return sorted(p.name for p in d.glob("paused_*")) if d.exists() else []


@pytest.fixture
def 격리(tmp_path):
    """격리 데이터루트 + 첫 계정 alias(계정을 하드코딩하지 않는다 — L-04)."""
    env, root = _격리된_데이터루트(tmp_path)
    계정 = json.loads(_cli(env, "accounts").stdout)
    if not 계정:
        pytest.skip("자격증명이 없으면 이 테스트는 의미가 없다")
    alias = 계정[0]["alias"]
    _회차박기(root, alias, 기본소재())
    return env, root, alias


def test_preview_out_연동끊김만_전행을_쓴다(격리, tmp_path):
    env, root, alias = 격리
    out = tmp_path / "prune_preview.json"
    p = _cli(env, "prune", "--run-dir", 회차명, "--account", alias, "--preview-out", str(out))
    assert p.returncode == 0, p.stdout + p.stderr
    문서 = json.loads(out.read_text(encoding="utf-8"))
    assert 문서["mode"] == "dry-run"
    assert 문서["total"] == 3
    assert sorted(문서["adIds"]) == ["a1", "a2", "a3"]
    assert 문서["limit"] is None
    계 = 문서["accounts"][alias]
    assert [t["adId"] for t in 계["targets"]] == ["a1", "a2", "a3"]
    assert 계["keep"] == {"AD_UNDER_REVIEW": 1, "AD_DISAPPROVED": 1}
    assert 계["aborted"] is None and 계["skipped"] is None
    assert 계["targets"][0]["adGroup"] == "판매상품_6-2_테스트"
    assert "한국어상품셋" in out.read_text(encoding="utf-8"), "한국어가 \\uXXXX 로 깨지지 않는다"


def test_preview_out_산출물이_그대로_only_ads_입력이_된다(격리, tmp_path):
    env, root, alias = 격리
    첫 = tmp_path / "p1.json"
    둘 = tmp_path / "p2.json"
    assert _cli(env, "prune", "--run-dir", 회차명, "--account", alias,
                "--preview-out", str(첫)).returncode == 0
    p = _cli(env, "prune", "--run-dir", 회차명, "--account", alias,
             "--only-ads", str(첫), "--preview-out", str(둘))
    assert p.returncode == 0, p.stdout + p.stderr
    a = json.loads(첫.read_text(encoding="utf-8"))["accounts"][alias]["targets"]
    b = json.loads(둘.read_text(encoding="utf-8"))["accounts"][alias]["targets"]
    assert a == b


def test_only_ads_깨지면_exit1_폴백없음(격리, tmp_path):
    env, root, alias = 격리
    깨짐 = tmp_path / "broken.json"
    깨짐.write_text("{not json", encoding="utf-8")
    p = _cli(env, "prune", "--run-dir", 회차명, "--account", alias, "--only-ads", str(깨짐))
    assert p.returncode == 1
    assert "폴백하지 않는다" in p.stdout
    assert _백업들(root) == [], "한 계정도 백업 단계에 들어가면 안 된다"


def test_상한_초과면_exit2_백업도_산출물도_없다(격리, tmp_path):
    env, root, alias = 격리
    out = tmp_path / "p.json"
    p = _cli(env, "prune", "--run-dir", 회차명, "--account", alias,
             "--max-items", "2", "--preview-out", str(out))
    assert p.returncode == 2, p.stdout + p.stderr
    assert "전량 거부" in p.stdout
    assert _백업들(root) == []
    assert not out.exists()


def test_상한_이내면_limit_이_실린다(격리, tmp_path):
    env, root, alias = 격리
    out = tmp_path / "p.json"
    p = _cli(env, "prune", "--run-dir", 회차명, "--account", alias,
             "--max-items", "3", "--preview-out", str(out))
    assert p.returncode == 0, p.stdout + p.stderr
    assert json.loads(out.read_text(encoding="utf-8"))["limit"] == 3


def test_백업태그_경로조작은_exit1(격리):
    env, root, alias = 격리
    p = _cli(env, "prune", "--run-dir", 회차명, "--account", alias, "--backup-tag", "../x")
    assert p.returncode == 1
    assert _백업들(root) == []


def test_백업태그가_백업_파일명에_붙는다(격리):
    env, root, alias = 격리
    p = _cli(env, "prune", "--run-dir", 회차명, "--account", alias, "--backup-tag", "job1")
    assert p.returncode == 0, p.stdout + p.stderr
    assert _백업들(root) == [f"paused_{alias}_{오늘}_job1.json"]


def test_무플래그_dry_run_은_기존_동작(격리):
    env, root, alias = 격리
    p = _cli(env, "prune", "--run-dir", 회차명, "--account", alias)
    assert p.returncode == 0, p.stdout + p.stderr
    assert _백업들(root) == [f"paused_{alias}_{오늘}.json"]


def test_자격증명_없는_계정은_skipped(격리, tmp_path):
    env, root, alias = 격리
    out = tmp_path / "p.json"
    p = _cli(env, "prune", "--run-dir", 회차명, "--account", "없는계정zz",
             "--preview-out", str(out))
    assert p.returncode == 0, p.stdout + p.stderr
    문서 = json.loads(out.read_text(encoding="utf-8"))
    assert 문서["accounts"]["없는계정zz"]["skipped"] == "자격증명 없음"
    assert 문서["total"] == 0 and 문서["adIds"] == []


# ─────────────────────────────────────────────────────────────────────────────
# 쓰기 경로 — in-process. 자격증명·네트워크·sleep 을 전부 가짜로 바꾼다.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def 가짜쓰기(tmp_path, monkeypatch):
    """data_root·계정·DELETE·재조회를 가짜로 바꾼다. 실제 API 호출 0."""
    alias = "zz1"
    monkeypatch.setattr(run_ads, "data_root", lambda: tmp_path)
    monkeypatch.setattr(run_ads, "_accounts",
                        lambda only=None: [{"alias": alias, "customer_id": "1"}])
    지운것 = []

    def fake_call(acct, method, path, params=None, body=None, raw=False):
        if method == "DELETE":
            지운것.append(path.rsplit("/", 1)[-1])
            return 204, None
        return 200, {}

    monkeypatch.setattr(prune.nvad, "call", fake_call)
    monkeypatch.setattr(prune.time, "sleep", lambda *_: None)
    _회차박기(tmp_path, alias, 기본소재())
    return alias, 지운것


def _ns(**kw):
    base = dict(run_dir=회차명, account=None, commit=False, only_ads=None,
                preview_out=None, max_items=None, backup_tag=None)
    base.update(kw)
    return argparse.Namespace(**base)


def test_preview_out_커밋_산출물에_items_excluded_new_since_preview(가짜쓰기, tmp_path, monkeypatch):
    alias, 지운것 = 가짜쓰기
    목록 = tmp_path / "only.json"
    목록.write_text(json.dumps({"adIds": ["a1", "a2"]}), encoding="utf-8")
    # 재조회: a1 여전히 연동끊김 · a2 다시 켜짐 · n9 새로 꺼짐(목록 밖)
    monkeypatch.setattr(prune.collect, "fetch_ads", lambda acct: (
        [소재("a1"), 소재("a2", enable=True, reason=None), 소재("n9")], {}))
    out = tmp_path / "result.json"
    rc = run_ads.cmd_prune(_ns(account=[alias], commit=True, only_ads=str(목록),
                               preview_out=str(out), max_items=10, backup_tag="job9"))
    assert rc == 0
    assert 지운것 == ["a1"], "목록 밖(n9)·되살아난(a2) 소재에는 DELETE 가 0회다"
    문서 = json.loads(out.read_text(encoding="utf-8"))
    assert 문서["mode"] == "commit" and 문서["limit"] == 10
    assert 문서["total"] == 1 and 문서["adIds"] == ["a1"]
    계 = 문서["accounts"][alias]
    assert 계["items"] == [{"adId": "a1", "status": 204, "결과": "성공", "err": None}]
    assert 계["excluded"] == [{"adId": "a2", "사유": "다시_켜짐"}]
    assert 계["new_since_preview"] == 1
    assert 계["result"] == {"ok": 1}
    assert 계["backup"].endswith(f"paused_{alias}_{오늘}_job9.json")


def test_상한_초과_커밋은_DELETE_0회_exit2(가짜쓰기, monkeypatch):
    alias, 지운것 = 가짜쓰기
    monkeypatch.setattr(prune.collect, "fetch_ads", lambda acct: (기본소재(), {}))
    rc = run_ads.cmd_prune(_ns(account=[alias], commit=True, max_items=2))
    assert rc == 2
    assert 지운것 == []
