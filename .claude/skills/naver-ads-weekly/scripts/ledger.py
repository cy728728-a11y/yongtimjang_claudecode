#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""입찰 인상 이력 — 3주 연속 실패·상한도달 판정의 근거.

이 파일이 없으면 "3주 연속 올렸는데도 노출 0" 규칙이 아예 작동하지 않는다.
회차마다 갱신되며 run-dir 이 아니라 계정별 고정 위치에 쌓인다.
"""
import json

BID_CAP = 200       # 2026-08-28 용팀장 확정. 도달분은 상한도달-무노출 리스트로 뺀다
BID_STEP = 10
FAIL_STREAK = 3     # 3주 연속 인상했는데 여전히 노출 0이면 중단


def load(path):
    """이력을 읽는다. 없거나 깨졌으면 빈 dict — 첫 회차도 그냥 돈다."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save(path, data):
    """이력을 쓴다. 부모 폴더가 없으면 만든다."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:
        print(f"이력 저장 실패 {path}: {type(e).__name__}: {e}")


def _entry(data, ad_id):
    return data.setdefault(ad_id, {"raises": [], "streak": 0, "capped": False})


def record_raise(data, ad_id, date_str, old_bid, new_bid):
    """인상 사실을 기록한다."""
    _entry(data, ad_id)["raises"].append({"date": date_str, "from": old_bid, "to": new_bid})


def record_still_zero(data, ad_id):
    """인상했는데 다음 회차에도 노출 0 — 연속 실패를 쌓는다."""
    e = _entry(data, ad_id)
    e["streak"] = e.get("streak", 0) + 1


def record_recovered(data, ad_id):
    """노출이 생겼다 — 연속을 끊는다."""
    _entry(data, ad_id)["streak"] = 0


def bid_decision(data, ad_id, current_bid):
    """이 소재를 올릴지 정한다. (사유, 새 입찰가) 를 돌려준다."""
    if current_bid is None:
        return ("입찰가불명", None)
    e = data.get(ad_id) or {}
    if e.get("streak", 0) >= FAIL_STREAK:
        return ("연속실패중단", None)
    new = current_bid + BID_STEP
    if new > BID_CAP:
        return ("상한도달", None)
    return ("인상", new)
