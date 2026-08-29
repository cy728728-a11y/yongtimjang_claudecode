#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""입찰 인상 이력 — 3주 연속 실패·상한도달 판정의 근거.

이 파일이 없으면 "3주 연속 올렸는데도 노출 0" 규칙이 아예 작동하지 않는다.
회차마다 갱신되며 run-dir 이 아니라 계정별 고정 위치에 쌓인다.
"""
import json
from datetime import date

BID_CAP = 200       # 2026-08-28 용팀장 확정. 도달분은 상한도달-무노출 리스트로 뺀다
BID_STEP = 10
FAIL_STREAK = 3     # 3주 연속 인상했는데 여전히 노출 0이면 중단
RAISE_COOLDOWN_DAYS = 6   # 주 1회 케이던스 — 6일 안에 이미 올렸으면 이번 회차 몫은 끝났다


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


def record_reverted(data, ad_id, date_str):
    """되돌림 사실을 기록한다(Important 4 — bids --revert).

    인상 기록을 지우지 않고 마지막 인상 항목에 `reverted` 플래그를 남긴다 — 삭제하면
    다음 회차가 "이 소재를 언제 얼마로 올렸었는지" 를 잃는다. `bid_decision` 은 `reverted`
    가 붙은 항목을 "최근 인상" 판정에서 제외한다 — 되돌렸으면 곧바로 다시 인상할 수
    있어야 한다.

    Minor 5: `run_revert` 는 백업의 모든 키를 되돌리는데, 그중엔 이번 회차 인상 시도가
    실패해 새 이력이 없는 소재도 섞여 있다. 무조건 `raises[-1]` 에 플래그를 찍으면
    이력이 아예 없는 소재엔 없던 인상을 지어내고, 지난 회차 인상만 있는 소재엔 실제로
    되돌려지지 않은 그 인상을 되돌린 것으로 오염시킨다. 마지막 인상 날짜가 이번
    되돌림 날짜와 같을 때만(=이번 회차에 실제로 성공한 인상일 때만) 플래그를 찍는다.
    """
    e = _entry(data, ad_id)
    if e["raises"] and e["raises"][-1].get("date") == date_str:
        e["raises"][-1]["reverted"] = True
        e["raises"][-1]["revertedDate"] = date_str
    # else: 이번 회차에 성공한 인상 이력이 없다 — 없는 인상을 지어내거나 엉뚱한
    # (지난 회차) 인상에 플래그를 붙이지 않는다.


def last_raise_date(entry):
    """되돌리지 않은 마지막 인상 날짜. 없으면 None (raises 는 날짜순으로 append 된다)."""
    last = None
    for r in entry.get("raises", []):
        if r.get("reverted"):
            continue
        if r.get("date"):
            last = r["date"]
    return last


def bid_decision(data, ad_id, current_bid, today=None):
    """이 소재를 올릴지 정한다. (사유, 새 입찰가) 를 돌려준다.

    Important 2 가드(룩백 창): `today` 가 주어지면 이력의 마지막 (되돌리지 않은) 인상
    날짜와 `today` 의 차이가 `RAISE_COOLDOWN_DAYS` 미만일 때 다시 올리지 않는다.
    이전엔 `날짜 == today` 단순 비교였다 — `bids --commit` 이 밤에 죽고 다음날 복구하면
    날짜가 달라져 이 체크를 그냥 통과해 100→110→120 처럼 같은 주 몫을 두 번 올리는
    사고가 났다. 룩백 창으로 바꾸면 자정을 넘긴 복구도 막힌다.
    날짜 파싱에 실패하면 막지 않고 통과시킨다(이력이 깨졌다고 인상을 영영 못 하면 안 된다).
    """
    if current_bid is None:
        return ("입찰가불명", None)
    e = data.get(ad_id) or {}
    if today:
        last = last_raise_date(e)
        if last:
            try:
                delta = abs((date.fromisoformat(today) - date.fromisoformat(last)).days)
            except Exception:
                delta = None
            if delta is not None and delta < RAISE_COOLDOWN_DAYS:
                return ("최근인상", None)
    if e.get("streak", 0) >= FAIL_STREAK:
        return ("연속실패중단", None)
    new = current_bid + BID_STEP
    if new > BID_CAP:
        return ("상한도달", None)
    return ("인상", new)
