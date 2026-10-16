#!/usr/bin/env python3
"""판매상품 자동잠금(sold-lock) — 순수 판정 규칙.

네트워크·시트·MCP 를 전혀 모른다(표준라이브러리만). 그래서 단위테스트로 전부 고정된다.
run_sold_lock.py 가 이 함수들만 조합해 판정하고, 쓰기는 거기서만 한다.

주문 행 형식 (commerce_orders.fetch_paid_orders 가 이 모양으로 채운다):
    {"market": "1-1",                 # 마켓번호
     "product_order_id": "2026...",    # 커머스 상품주문번호
     "product_id": "12345678",         # 스마트스토어 상품번호(문자열)
     "seller_code": "ABC123" | "",     # 판매자상품코드(없을 수 있음)
     "product_name": "...",
     "payment_date": "2026-10-15T10:12:33.0+09:00"}

사유 코드(result.json 집계 키 — 영문 고정, 바꾸지 마라):
    not_found · multiple · ss_lookup_failed · productno_mismatch · market_mismatch ·
    lock_state_unknown · lookup_error · lock_unverified · lock_failed
"""
import json
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

# 사유 코드 → 한국어 설명 (SKILL.md 판정표와 같은 내용)
REASONS = {
    "not_found": "불사자에서 코드로 조회 안 됨",
    "multiple": "같은 코드 상품이 2건 이상 (어느 것인지 모름)",
    "ss_lookup_failed": "스마트스토어 상품번호 조회 실패",
    "productno_mismatch": "불사자에 기록된 스스 상품번호가 주문 상품번호와 다름",
    "market_mismatch": "불사자 마켓그룹이 주문 마켓과 다름",
    "lock_state_unknown": "잠금 상태를 읽을 수 없음",
    "lookup_error": "불사자 조회 호출 오류",
    "lock_unverified": "잠금 호출 후 재조회에서 잠금이 확인 안 됨",
    "lock_failed": "잠금 호출 자체가 실패",
}

# 실패 마켓 상태 → 업무판 메모용 한국어
_MARKET_FAIL_LABEL = {
    "token_failed": "정지/토큰실패",
    "orders_failed": "주문조회실패",
}


# ---------------------------------------------------------------------------
# 대상 마켓
# ---------------------------------------------------------------------------
def target_markets():
    """잠금 대상 52마켓 = 1-1~4-3(12) + 11-1~11-3(3) + 13-1~24-3(36) + 25-1(1).

    5~10번·12번·25-2 는 용쌤(부킹) 계정 스마트스토어가 아니라서 뺀다.
    """
    out = []
    for n in list(range(1, 5)) + [11] + list(range(13, 25)):
        for s in (1, 2, 3):
            out.append(f"{n}-{s}")
    out.append("25-1")
    return out


def parse_markets_arg(text):
    """'--markets 1-1,2-1' → ['1-1','2-1']. 대상 밖 번호가 섞이면 ValueError."""
    allowed = set(target_markets())
    out = []
    for part in str(text or "").split(","):
        p = part.strip()
        if not p:
            continue
        if p not in allowed:
            raise ValueError(f"대상 마켓이 아니다: {p}")
        if p not in out:
            out.append(p)
    if not out:
        raise ValueError("마켓 번호가 비었다")
    return out


# ---------------------------------------------------------------------------
# 날짜 (전부 KST)
# ---------------------------------------------------------------------------
def day_range_kst(date_str):
    """'2026-10-15' → (그날 00:00:00.000+09:00, 23:59:59.999+09:00) — 커머스API 형식."""
    datetime.strptime(date_str, "%Y-%m-%d")  # 형식 검증(틀리면 ValueError)
    return (f"{date_str}T00:00:00.000+09:00", f"{date_str}T23:59:59.999+09:00")


def default_target_date(now_kst=None):
    """기본 대상 = 실행 시각(KST)의 전날. 00:01 실행이면 어제 하루치."""
    now = now_kst or datetime.now(KST)
    if now.tzinfo is None:
        now = now.replace(tzinfo=KST)
    return (now.astimezone(KST) - timedelta(days=1)).strftime("%Y-%m-%d")


def _parse_dt(s):
    """ISO 문자열 → aware datetime. 'Z' 는 UTC, 시간대 없으면 KST 로 본다. 실패 시 None."""
    if not s or not isinstance(s, str):
        return None
    t = s.strip()
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(t)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return dt


def is_paid_on(payment_date_str, date_str):
    """결제일시를 KST 로 환산한 날짜가 date_str 이면 True. 읽을 수 없으면 False."""
    dt = _parse_dt(payment_date_str)
    if dt is None:
        return False
    return dt.astimezone(KST).strftime("%Y-%m-%d") == date_str


# ---------------------------------------------------------------------------
# 중복 제거
# ---------------------------------------------------------------------------
def dedup_orders(rows):
    """같은 마켓 안에서 판매자상품코드(없으면 상품번호) 기준으로 1건으로 묶는다.

    다른 마켓의 같은 코드는 별개 상품(마켓마다 사본)이라 따로 둔다.
    반환 행에 order_count(묶인 주문 수)·product_order_ids 를 붙인다. 입력 순서 유지.
    """
    out = {}
    for r in rows:
        code = (r.get("seller_code") or "").strip()
        key = (r.get("market"), "code:" + code if code else "pid:" + str(r.get("product_id") or ""))
        if key not in out:
            row = dict(r)
            row["seller_code"] = code
            row["order_count"] = 0
            row["product_order_ids"] = []
            out[key] = row
        out[key]["order_count"] += 1
        poid = r.get("product_order_id")
        if poid is not None and poid not in out[key]["product_order_ids"]:
            out[key]["product_order_ids"].append(poid)
    return list(out.values())


# ---------------------------------------------------------------------------
# 판정
# ---------------------------------------------------------------------------
def extract_ss_no(value):
    """uploadedSuccessUrl.smartstore 값(URL 또는 숫자) → 상품번호 문자열. 없으면 None."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.isdigit():
        return s
    m = re.search(r"/products/(\d+)", s)
    if m:
        return m.group(1)
    m = re.search(r"(\d{5,})\D*$", s)
    return m.group(1) if m else None


def lock_state(item):
    """find_by_code 항목의 잠금상태. '숨김' bool → 그것, 아니면 '잠금' bool, 둘 다 아니면 None.

    문서마다 키 이름이 달라서(lock 스킬='숨김', bulsaja_scan='잠금') 둘 다 받는다.
    문자열 'false' 같은 건 bool 이 아니므로 불명(None)으로 본다 — 추측하지 않는다.
    """
    for k in ("숨김", "잠금"):
        v = item.get(k) if isinstance(item, dict) else None
        if isinstance(v, bool):
            return v
    return None


def market_matches(group_name, market_no):
    """마켓그룹명에 '용쌤{마켓번호}' 가 숫자 경계로 들어 있으면 True.

    '용쌤1-1' 이 '용쌤11-1'·'용쌤1-12' 에 걸리면 안 된다 → 앞뒤 숫자 경계.
    """
    if not group_name:
        return False
    pat = r"(?<![\d])용쌤" + re.escape(str(market_no)) + r"(?!\d)"
    return re.search(pat, str(group_name)) is not None


def decide(order, found_items, ss_no_by_pid, market_no):
    """주문 1건 → (verdict, reason).

    verdict: "lock" | "already_locked" | "skip". skip 이면 reason 은 사유 코드, 아니면 None.
    3중 가드: 정확히 1건 + 스스 상품번호 일치 + 마켓그룹 일치. 불명은 전부 skip(변경 없음).
    ss_no_by_pid: {불사자 productId: 스스번호 문자열 | None(조회실패)}.
    """
    items = found_items or []
    if len(items) == 0:
        return "skip", "not_found"
    if len(items) > 1:
        return "skip", "multiple"
    item = items[0]
    pid = item.get("productId")
    ss = (ss_no_by_pid or {}).get(pid)
    if ss is None:
        return "skip", "ss_lookup_failed"
    if str(ss) != str(order.get("product_id") or ""):
        return "skip", "productno_mismatch"
    if not market_matches(item.get("그룹"), market_no):
        return "skip", "market_mismatch"
    st = lock_state(item)
    if st is None:
        return "skip", "lock_state_unknown"
    if st:
        return "already_locked", None
    return "lock", None


# ---------------------------------------------------------------------------
# 요약
# ---------------------------------------------------------------------------
def _failed_markets(result):
    return [(no, m.get("status")) for no, m in (result.get("markets") or {}).items()
            if (m or {}).get("status") in _MARKET_FAIL_LABEL]


def summary_memo(result):
    """업무판 메모 1줄. 예: '주문 10 · 신규잠금 3 · 기존잠금 4 · 스킵 3(not_found 2, multiple 1) · 실패마켓 15-3(정지/토큰실패)'."""
    t = result.get("totals") or {}
    skipped = t.get("skipped") or {}
    n_skip = sum(skipped.values())
    parts = [f"주문 {t.get('orders', 0)}",
             f"신규잠금 {t.get('locked_new', 0)}",
             f"기존잠금 {t.get('already_locked', 0)}"]
    if t.get("would_lock"):
        parts.append(f"잠금예정 {t['would_lock']}")
    if n_skip:
        detail = ", ".join(f"{k} {v}" for k, v in skipped.items() if v)
        parts.append(f"스킵 {n_skip}({detail})")
    else:
        parts.append("스킵 0")
    failed = _failed_markets(result)
    if failed:
        parts.append("실패마켓 " + ", ".join(f"{no}({_MARKET_FAIL_LABEL[s]})" for no, s in failed))
    return " · ".join(parts)


def checked_flag(result):
    """스킵 0 이고 실패마켓 0 일 때만 True — 업무판 '확인' 체크."""
    skipped = ((result.get("totals") or {}).get("skipped") or {})
    return sum(skipped.values()) == 0 and not _failed_markets(result)


# ---------------------------------------------------------------------------
# 시크릿 마스킹
# ---------------------------------------------------------------------------
def redact(text, secrets):
    """text 안의 시크릿 원문(과 JSON 이스케이프형)을 '***' 로. 빈 값은 무시."""
    if text is None:
        return ""
    s = str(text)
    for sec in secrets or []:
        if not sec or not isinstance(sec, str) or len(sec) < 4:
            continue
        s = s.replace(sec, "***")
        esc = json.dumps(sec)[1:-1]
        if esc != sec:
            s = s.replace(esc, "***")
    return s


def safe_json(obj, secrets):
    """obj 를 JSON 문자열로 직렬화한 뒤 시크릿을 마스킹. 산출물은 반드시 이것으로만 쓴다."""
    return redact(json.dumps(obj, ensure_ascii=False, indent=2, default=str), secrets)
