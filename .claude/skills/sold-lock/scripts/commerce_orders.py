#!/usr/bin/env python3
"""네이버 커머스API — 마켓별 키 로드 + 토큰 + 전날 결제완료 주문 수집 (읽기 전용).

보안 원칙:
  · 시크릿은 load_stores 가 돌려주는 dict 안에만 있다. 이 모듈은 시크릿·토큰을 print 하지 않는다.
  · 토큰 발급 오류문(응답 본문 앞 200자)은 호출부가 sold_lock_rules.redact 로 거른 뒤 저장한다.
  · 시트에서 읽은 키는 ~/.eroom/naver-commerce-stores.json 에 0600 으로 캐시한다(시트 장애 대비).

토큰 발급은 새로 짜지 않고 naver-ads-thumbnail/scripts/verify_creds.issue_token 을 재사용한다.
"""
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta

import sold_lock_rules as R

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILLS_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
CACHE_PATH = os.path.join(os.path.expanduser("~"), ".eroom", "naver-commerce-stores.json")
KEY_RANGE = "'사업자정리'!A48:L120"   # A=마켓번호 C=마켓명 G=애플리케이션ID H=시크릿
BASE = "https://api.commerce.naver.com/external"
_RETRY_STATUS = {429, 500, 502, 503, 504}


class StoresUnavailable(RuntimeError):
    """시트도 캐시도 못 읽음 → 종료코드 2."""


def _load_eroomlib():
    """스크립트 위치에서 위로 올라가며 lib/eroomlib 를 찾아 sys.path 에 1회 넣는다."""
    d = SCRIPT_DIR
    while d and d != os.path.dirname(d):
        lib = os.path.join(d, "lib")
        if os.path.isdir(os.path.join(lib, "eroomlib")):
            if lib not in sys.path:
                sys.path.insert(0, lib)
            return
        d = os.path.dirname(d)


def _atomic_write_private(path, text):
    """0600 으로 원자적 쓰기 — 다른 사용자가 읽을 수 있는 순간이 없게 임시파일부터 0600."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=os.path.dirname(path))
    try:
        os.chmod(tmp, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def parse_key_rows(rows):
    """시트 2차원 값 → {마켓번호: {name, client_id, client_secret}} (대상 52마켓만, 키 빈 행 제외)."""
    allowed = set(R.target_markets())
    out = {}
    for row in rows or []:
        cells = list(row) + [""] * (8 - len(row))
        no = str(cells[0] or "").strip()
        if no not in allowed:
            continue
        cid, sec = str(cells[6] or "").strip(), str(cells[7] or "").strip()
        if not cid or not sec:
            continue
        out[no] = {"name": str(cells[2] or "").strip(), "client_id": cid, "client_secret": sec}
    return out


class CommerceClient:
    """실제 커머스 연동. run_sold_lock.run(commerce=...) 에 가짜를 꽂을 수 있게 메서드 3개로 고정:
    load_stores(markets) · issue_token(store) · fetch_paid_orders(token, market, date)."""

    def __init__(self, sheet_id, sheets_get=None, cache_path=CACHE_PATH, http=None,
                 sleep=time.sleep, min_interval=0.2):
        self.sheet_id = sheet_id
        self._sheets_get = sheets_get
        self.cache_path = cache_path
        self._http = http
        self._sleep = sleep
        self.min_interval = min_interval
        self._last_call = 0.0

    # ---- 키 -----------------------------------------------------------
    def load_stores(self, markets):
        """(stores, source). 시트 → 성공 시 캐시 갱신. 시트 실패 → 캐시 폴백. 둘 다 없으면 StoresUnavailable."""
        stores, source, sheet_err = None, None, None
        try:
            getter = self._sheets_get
            if getter is None:
                _load_eroomlib()
                from eroomlib.gsheets import sheets_get as getter
            stores = parse_key_rows(getter(self.sheet_id, KEY_RANGE))
            if not stores:
                raise RuntimeError("시트에서 대상 마켓 키를 하나도 못 읽었다")
            source = "sheet"
            try:
                _atomic_write_private(self.cache_path, json.dumps(stores, ensure_ascii=False))
            except Exception as e:  # 캐시 실패는 치명적이지 않다
                print(f"[경고] 키 캐시 저장 실패: {type(e).__name__}", flush=True)
        except Exception as e:
            sheet_err = type(e).__name__
            try:
                with open(self.cache_path, encoding="utf-8") as f:
                    stores = json.load(f)
                source = "cache"
            except Exception:
                raise StoresUnavailable(f"키 시트({sheet_err})·캐시 모두 실패")
        want = set(markets)
        return {k: v for k, v in stores.items() if k in want}, source

    # ---- 토큰 ---------------------------------------------------------
    def issue_token(self, store):
        """(token|None, err|None). verify_creds.issue_token 재사용 — 경로는 스크립트 기준 상대."""
        p = os.path.join(SKILLS_DIR, "naver-ads-thumbnail", "scripts")
        if p not in sys.path:
            sys.path.insert(0, p)
        from verify_creds import issue_token  # 지연 import (bcrypt 의존)
        return issue_token(store["client_id"], store["client_secret"])

    # ---- 주문 ---------------------------------------------------------
    def _request(self, method, url, token, **kw):
        """레이트 간격 + 429/5xx 지수백오프(최대 4회)."""
        if self._http is None:
            import requests
            self._http = requests.Session()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        last = None
        for attempt in range(4):
            gap = time.monotonic() - self._last_call
            if gap < self.min_interval:
                self._sleep(self.min_interval - gap)
            self._last_call = time.monotonic()
            r = self._http.request(method, url, headers=headers, timeout=30, **kw)
            if r.status_code in _RETRY_STATUS:
                last = f"HTTP {r.status_code}"
                self._sleep(1.0 * (2 ** attempt))
                continue
            if r.status_code >= 400:
                raise RuntimeError(f"HTTP {r.status_code} {r.text[:200]}")
            return r.json()
        raise RuntimeError(f"재시도 초과: {last}")

    def fetch_paid_orders(self, token, market, date_str):
        """그날(KST) 결제된 상품주문 → 주문 행 dict 리스트 (sold_lock_rules 형식).

        ⚠️ lastChangedType=PAYED 필터는 쓰지 않는다 — '마지막 변경'이 결제인 주문만 오므로,
        결제 뒤 발주확인·발송으로 넘어간 주문이 전부 빠진다(2026-10-16 실측: 52마켓 0건).
        그래서 대상일 00:00 ~ 지금까지 변경된 주문을 24시간 창으로 전부 모은 뒤,
        상세의 결제일(paymentDate)로 대상일 결제분만 고른다.
        """
        frm, _ = R.day_range_kst(date_str)
        start = datetime.fromisoformat(frm)
        end = datetime.now(start.tzinfo)
        ids = []
        while start < end:
            w_end = min(start + timedelta(hours=24) - timedelta(milliseconds=1), end)
            params = {"lastChangedFrom": start.isoformat(timespec="milliseconds"),
                      "lastChangedTo": w_end.isoformat(timespec="milliseconds")}
            for _ in range(1000):  # 페이지 상한(무한루프 방지)
                d = self._request("GET", f"{BASE}/v1/pay-order/seller/product-orders/last-changed-statuses",
                                  token, params=params)
                data = (d or {}).get("data") or {}
                for s in data.get("lastChangeStatuses") or []:
                    poid = s.get("productOrderId")
                    if poid and poid not in ids:
                        ids.append(poid)
                more = data.get("more")
                if not more or not more.get("moreFrom"):
                    break
                params = dict(params, lastChangedFrom=more["moreFrom"])
                if more.get("moreSequence"):
                    params["moreSequence"] = more["moreSequence"]
            start = w_end + timedelta(milliseconds=1)

        rows = []
        for i in range(0, len(ids), 300):
            d = self._request("POST", f"{BASE}/v1/pay-order/seller/product-orders/query", token,
                              json={"productOrderIds": ids[i:i + 300]})
            for e in (d or {}).get("data") or []:
                po, od = e.get("productOrder") or {}, e.get("order") or {}
                row = {
                    "market": market,
                    "product_order_id": str(po.get("productOrderId") or ""),
                    "product_id": str(po.get("productId") or ""),
                    "seller_code": str(po.get("sellerProductCode") or ""),
                    "product_name": po.get("productName") or "",
                    "payment_date": od.get("paymentDate"),
                }
                if R.is_paid_on(row["payment_date"], date_str):
                    rows.append(row)
        return rows
