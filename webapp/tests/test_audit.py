#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""감사 기록기(`webapp/audit.py`) · 테스트 격리 · 상한 설정 키 검증 (FLOW-07 · SAFE-07 · Pitfall 3).

전부 tmp 파일과 가짜 행 dict 로만 돈다. 실제 데이터루트(`~/python_work/data/control-tower/`)
에는 한 글자도 쓰지 않는다 — conftest 의 autouse 픽스처가 `CT_AUDIT_PATH` 를 tmp 로 돌린다.
"""
import json
import os
from pathlib import Path

import pytest

from webapp import audit, paths, settings


# ── 격리 · 설정 키 ──────────────────────────────────────────────────────────

def test_conftest_가_감사경로와_기동reap_을_격리한다(tmp_path):
    """autouse 픽스처가 client 보다 먼저 돈다 — lifespan 이 실 webapp.db 를 못 연다(Pitfall 3)."""
    assert os.environ.get("CT_SKIP_STARTUP_REAP") == "1"
    assert os.environ.get("CT_AUDIT_PATH") == str(tmp_path / "audit.jsonl")


def test_상한_설정키_기본값():
    assert settings.DEFAULTS["prune_max_items"] == 8000
    assert settings.DEFAULTS["audit_path"] == ""


def test_CT_DATA_ROOT_가_우선한다(monkeypatch, tmp_path):
    monkeypatch.delenv("CT_DATA_ROOT", raising=False)
    기본 = paths.data_root()
    monkeypatch.setenv("CT_DATA_ROOT", str(tmp_path / "격리"))
    assert paths.data_root() == tmp_path / "격리"
    monkeypatch.delenv("CT_DATA_ROOT")
    assert paths.data_root() == 기본


# ── audit_path ─────────────────────────────────────────────────────────────

def test_audit_path_환경변수가_최우선(monkeypatch, tmp_path):
    monkeypatch.setenv("CT_AUDIT_PATH", str(tmp_path / "x.jsonl"))
    assert audit.audit_path() == tmp_path / "x.jsonl"


def test_audit_path_설정값_다음은_데이터루트(monkeypatch, tmp_path):
    monkeypatch.delenv("CT_AUDIT_PATH", raising=False)
    monkeypatch.setattr(paths, "data_root", lambda: tmp_path / "루트")
    monkeypatch.setattr(settings, "_cache", {**settings.load(), "audit_path": ""})
    assert audit.audit_path() == tmp_path / "루트" / "control-tower" / "audit.jsonl"
    monkeypatch.setattr(settings, "_cache", {**settings.load(), "audit_path": str(tmp_path / "s.jsonl")})
    assert audit.audit_path() == tmp_path / "s.jsonl"


# ── record ─────────────────────────────────────────────────────────────────

def _행(**덮기) -> dict:
    기본 = {"id": "job-1", "kind": "prep", "parent_job_id": None, "accounts": '["zz1"]',
            "target_count": None, "result_path": None, "exit_code": 0, "status": "done",
            "argv": '["비밀아님"]'}
    기본.update(덮기)
    return 기본


def test_record_는_한줄씩_append_하고_디렉터리를_만든다(monkeypatch, tmp_path):
    경로 = tmp_path / "깊은" / "곳" / "audit.jsonl"
    monkeypatch.setenv("CT_AUDIT_PATH", str(경로))
    audit.record(_행(id="j1"))
    audit.record(_행(id="j2", status="failed", exit_code=2))
    줄 = 경로.read_text(encoding="utf-8").splitlines()
    assert len(줄) == 2
    a, b = (json.loads(x) for x in 줄)
    assert a["잡id"] == "j1" and b["잡id"] == "j2"
    assert b["상태"] == "failed" and b["종료코드"] == 2
    assert "종류" in a and "시각" in a and "계정" in a and "부모잡id" in a
    for k in ("대상수", "성공", "실패", "제외", "크레딧"):
        assert k in a
    # 한국어 그대로 (ensure_ascii=False)
    assert "잡id" in 줄[0]
    # argv 는 싣지 않는다 (T-02-14)
    assert "비밀아님" not in 줄[0]
    assert a["계정"] == ["zz1"]


def test_record_는_쓰기_예외를_삼킨다(monkeypatch, tmp_path):
    막힌곳 = tmp_path / "파일임"
    막힌곳.write_text("x", encoding="utf-8")
    monkeypatch.setenv("CT_AUDIT_PATH", str(막힌곳 / "audit.jsonl"))   # 부모가 파일이라 mkdir 실패
    audit.record(_행())                                                 # 예외가 안 올라온다


# ── summarize ──────────────────────────────────────────────────────────────

def _prune결과(경로: Path) -> Path:
    경로.write_text(json.dumps({
        "mode": "commit", "total": 6, "adIds": [],
        "accounts": {
            "zz1": {"items": [{"adId": "a", "결과": "성공"}, {"adId": "b", "결과": "이미없음"},
                              {"adId": "c", "결과": "실패"}],
                    "excluded": [{"adId": "d", "사유": "다시_켜짐"}]},
            "zz2": {"items": [{"adId": "e", "결과": "재시도소진"}, {"adId": "f", "결과": "성공"}],
                    "excluded": [{"adId": "g", "사유": "재조회에_없음"},
                                 {"adId": "h", "사유": "다시_켜짐"}]},
            "zz3": {"skipped": "자격증명 없음"},
        }}, ensure_ascii=False), encoding="utf-8")
    return 경로


def test_summarize_prune_commit(tmp_path):
    p = _prune결과(tmp_path / "prune_result_x.json")
    s = audit.summarize(_행(kind="prune_commit", result_path=str(p), target_count=8))
    assert s["성공"] == 3 and s["실패"] == 2 and s["제외"] == 3 and s["크레딧"] == 0
    assert s["대상수"] == 8
    assert "요약오류" not in s


@pytest.mark.parametrize("내용", [None, "{깨짐"])
def test_summarize_prune_결과파일_없거나_깨짐(tmp_path, 내용):
    p = tmp_path / "r.json"
    if 내용 is not None:
        p.write_text(내용, encoding="utf-8")
    s = audit.summarize(_행(kind="prune_commit", result_path=str(p)))
    assert s["성공"] is None and s["실패"] is None
    assert "요약오류" in s


def test_summarize_bids_commit(tmp_path):
    p = tmp_path / "result_x.json"
    p.write_text(json.dumps({"accounts": {"zz1": {"plans": [
        {"adId": "a", "result": "성공"}, {"adId": "c", "result": "성공"},
        {"adId": "b", "result": "실패"},
    ]}}}, ensure_ascii=False), encoding="utf-8")
    from webapp import flow
    기대 = flow.result_counts(json.loads(p.read_text(encoding="utf-8")))
    s = audit.summarize(_행(kind="bids_commit", result_path=str(p)))
    assert s["성공"] == 기대["성공"] == 2 and s["실패"] == 기대["실패"] == 1
    assert s["크레딧"] == 0


def test_summarize_detail_크레딧(tmp_path):
    p = tmp_path / "summary_x.json"
    p.write_text(json.dumps({"집계": {"완료": 4, "실패": 1, "스킵": 2, "실제크레딧": 40}},
                            ensure_ascii=False), encoding="utf-8")
    s = audit.summarize(_행(kind="detail_submit", result_path=str(p)))
    assert s["크레딧"] == 40 and s["성공"] == 4 and s["실패"] == 1


def test_summarize_detail_못읽으면_크레딧_None(tmp_path):
    s = audit.summarize(_행(kind="detail_poll", result_path=str(tmp_path / "없음.json")))
    assert s["크레딧"] is None


def test_summarize_그밖의_쓰기잡은_모른다(tmp_path):
    s = audit.summarize(_행(kind="prep", target_count=None))
    assert s["성공"] is None and s["실패"] is None and s["크레딧"] == 0


def test_테스트는_실데이터루트_감사파일을_만들지_않는다():
    """실 데이터루트 control-tower/ 에 감사 파일이 생기면 격리가 뚫린 것이다."""
    assert audit.audit_path() != Path.home() / "python_work" / "data" / "control-tower" / "audit.jsonl"
