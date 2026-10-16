#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⑦c 후보·⑦d 후보 → 불사자 상품 조인 + 상세/옵션 상태 보강 (`run_ads.py enrich`). 읽기 전용.

조인 경로 (2026-10-16 오케스트레이터 확정 — 상품명 매칭 금지, webapp/join.py D-03 유지):
  광고 소재의 스토어상품ID(= 스마트스토어 채널상품번호) + 광고그룹명의 `NN-N` 마켓번호
  → 그 마켓의 커머스API 키(sold-lock/commerce_orders.CommerceClient 의 키 로딩·토큰 재사용)
  → GET /v2/products/channel-products/{채널상품번호}
  → originProduct.detailAttribute.sellerCodeInfo.sellerManagementCode (= 판매자상품코드)
  → 불사자 bulsaja_product_find_by_code 정확히 1건
  → 워크데이터 uploadedSuccessUrl.smartstore 가 채널상품번호와 같으면 '히트'
상품명 폴백은 **넣지 않는다** — 실측 6건 중 2건이 깨졌다(D-03).

미매칭 사유 (`불사자매칭` = "미매칭: <사유>"):
  번호추출실패 · 키없음 · 커머스조회실패 · 판매자코드없음 · 불사자미매칭 · 다건 · 번호불일치 · 조회실패

재사용 (로직 복제 금지):
  webapp.join   market_number · 재검증판정 · strip_display_rules
  webapp.state  상세상태
  sold-lock     commerce_orders.CommerceClient · sold_lock_rules.extract_ss_no / redact
  detail-page   ss_index_calls.항목꺼내기 / 워크데이터꺼내기
  eroomlib      snapshot.ProductMCP · matrix(현황판 '옵션' 열)

옵션명 미정리 판정 원천 = 그룹 현황판(eroomlib.matrix `00_진행` 탭 `옵션` 열). option-cleanup 이
저장 뒤 `완료` 를 찍는 기존 기록이다. 기록이 없으면 '판정 불가' — 옵션명을 재채점해 추측하지 않는다.

시크릿 원칙: 커머스 키·토큰은 CommerceClient 안에만 있다. 이 모듈은 출력·캐시에 싣지 않고,
오류 문자열은 redact 로 거른 뒤 앞 200자만 남긴다.
"""
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILLS_DIR = SCRIPT_DIR.parent.parent

# 저장소 루트(webapp/ 와 .claude/lib/eroomlib 가 있는 곳) 찾기 — run_ads.py 의 _d 루프 관용구
_d = str(SCRIPT_DIR)
_root = None
while _d and _d != str(Path(_d).parent):
    _lib = str(Path(_d) / "lib")
    if (Path(_lib) / "eroomlib").is_dir() and _lib not in sys.path:
        sys.path.insert(0, _lib)
    if (Path(_d) / "webapp" / "join.py").is_file():
        _root = _d
        break
    _d = str(Path(_d).parent)
if _root and _root not in sys.path:
    sys.path.insert(0, _root)
for _p in (SKILLS_DIR / "sold-lock" / "scripts", SKILLS_DIR / "bulsaja-detail-page" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from webapp import join, state  # noqa: E402
import sold_lock_rules as SL  # noqa: E402

MCP_GAP = 0.26            # 불사자 레이트리밋 초당 4회
MATCH_HIT = "히트"
PREFIX = "미매칭: "
COMMERCE_PRODUCT_URL = "https://api.commerce.naver.com/external/v2/products/channel-products/{no}"

# 미매칭 사유 — 문자열을 한 곳에만 둔다
R_NO_MARKET = "번호추출실패"
R_NO_KEY = "키없음"
R_COMMERCE = "커머스조회실패"
R_NO_CODE = "판매자코드없음"
R_NOT_FOUND = "불사자미매칭"
R_MULTI = "다건"
R_MISMATCH = "번호불일치"
R_LOOKUP = "조회실패"

ENRICH_KEYS = ("⑦c상세꾸미기후보", "⑦d정비점검후보")


class KeyMissing(Exception):
    """그 마켓의 커머스 키가 없다."""


class CommerceFailed(Exception):
    """커머스 토큰·조회 실패."""


# ---------------------------------------------------------------------------
# 순수 함수
# ---------------------------------------------------------------------------
def seller_code_of(channel_product):
    """채널상품 응답 → 판매자상품코드(sellerManagementCode). 없으면 None."""
    try:
        v = (((channel_product or {}).get("originProduct") or {}).get("detailAttribute") or {}) \
            .get("sellerCodeInfo", {}) or {}
        code = str(v.get("sellerManagementCode") or "").strip()
        return code or None
    except Exception:
        return None


def pick_items(items, code):
    """find_by_code 응답 항목 중 그 코드에 정확히 맞는 것만.

    항목에 판매자상품코드/불사자코드 필드가 하나도 없으면(응답 모양이 다를 때) 그대로 둔다 —
    거르지 못한 채 0건으로 만들면 '불사자미매칭' 으로 둔갑한다.
    """
    items = [it for it in (items or []) if isinstance(it, dict)]
    keyed = [it for it in items if "판매자상품코드" in it or "불사자코드" in it]
    if not keyed:
        return items
    return [it for it in keyed
            if str(it.get("판매자상품코드") or "") == code or str(it.get("불사자코드") or "") == code]


def option_status(matrix_value, found):
    """현황판 '옵션' 값 → (옵션상태, 옵션미정리)."""
    if not found:
        return "판정 불가", None
    v = str(matrix_value or "").strip()
    if v in ("완료", "해당없음"):
        return "정리완료", False
    return "미정리", True


def unmatched(row, reason, **extra):
    """미매칭 행 — 보강 필드를 계약대로 채운다(판정 못 한 칸은 None)."""
    out = dict(row)
    out.update({"불사자매칭": PREFIX + reason, "productId": None, "판매자상품코드": None,
                "상세상태": None, "상세미가공": None, "옵션상태": "판정 불가", "옵션미정리": None,
                "번호검증": join.미조회})
    out.update(extra)
    return out


def _safe_name(s):
    return re.sub(r"[^0-9A-Za-z가-힣_-]", "_", str(s))[:80]


# ---------------------------------------------------------------------------
# 보강 본체 — lookup 은 주입 가능(테스트는 가짜를 꽂는다)
# ---------------------------------------------------------------------------
def enrich_rows(rows, lookup):
    """행 목록 → 보강된 사본 목록. 원본을 바꾸지 않는다. 행 하나의 실패가 다른 행을 막지 않는다.

    lookup 인터페이스:
      seller_code(market, channel_no) -> str|None   (KeyMissing / CommerceFailed 예외)
      find(code) -> [항목]                           (예외 → 조회실패)
      workdata(pid) -> dict                          (예외 → 조회실패)
      group_name(gid) -> str|None
      matrix_option(group_name, market, pid) -> (값, found)
    """
    code_memo, find_memo, wd_memo = {}, {}, {}
    out = []
    for row in rows:
        try:
            out.append(_enrich_one(row, lookup, code_memo, find_memo, wd_memo))
        except Exception as e:  # 예상 못 한 실패도 그 행만 조회실패로
            out.append(unmatched(row, R_LOOKUP, 보강오류=f"{type(e).__name__}"[:100]))
    return out


def _enrich_one(row, lookup, code_memo, find_memo, wd_memo):
    market = join.market_number(row.get("adGroup") or "")
    channel_no = str(row.get("mallProductId") or "").strip()
    if not market or not channel_no:
        return unmatched(row, R_NO_MARKET, 마켓번호=market)

    # ① 커머스: 채널상품번호 → 판매자상품코드
    ck = (market, channel_no)
    if ck not in code_memo:
        try:
            code_memo[ck] = ("ok", lookup.seller_code(market, channel_no))
        except KeyMissing:
            code_memo[ck] = ("err", R_NO_KEY)
        except Exception:
            code_memo[ck] = ("err", R_COMMERCE)
    kind, val = code_memo[ck]
    if kind == "err":
        return unmatched(row, val, 마켓번호=market)
    code = val
    if not code:
        return unmatched(row, R_NO_CODE, 마켓번호=market)

    # ② 불사자: 판매자상품코드 → 정확히 1건
    if code not in find_memo:
        try:
            find_memo[code] = ("ok", pick_items(lookup.find(code), code))
        except Exception:
            find_memo[code] = ("err", None)
    kind, items = find_memo[code]
    if kind == "err":
        return unmatched(row, R_LOOKUP, 마켓번호=market, 판매자상품코드=code)
    if not items:
        return unmatched(row, R_NOT_FOUND, 마켓번호=market, 판매자상품코드=code)
    if len(items) > 1:
        return unmatched(row, R_MULTI, 마켓번호=market, 판매자상품코드=code)
    pid = items[0].get("productId")
    if not pid:
        return unmatched(row, R_LOOKUP, 마켓번호=market, 판매자상품코드=code)

    # ③ 워크데이터: 스스번호 재검증 + 상세 상태
    if pid not in wd_memo:
        try:
            wd_memo[pid] = ("ok", lookup.workdata(pid) or {})
        except Exception:
            wd_memo[pid] = ("err", None)
    kind, wd = wd_memo[pid]
    if kind == "err":
        return unmatched(row, R_LOOKUP, 마켓번호=market, 판매자상품코드=code, productId=pid)
    ss_no = SL.extract_ss_no((wd.get("uploadedSuccessUrl") or {}).get("smartstore")
                             if isinstance(wd.get("uploadedSuccessUrl"), dict) else None)
    검증 = join.재검증판정(channel_no, ss_no, False)
    if 검증 != join.히트:
        return unmatched(row, R_MISMATCH, 마켓번호=market, 판매자상품코드=code, productId=pid,
                         번호검증=검증)

    상세 = state.상세상태(wd.get("uploadDetailContents"))
    out = dict(row)
    out.update({"마켓번호": market, "불사자매칭": MATCH_HIT, "productId": pid,
                "판매자상품코드": str(wd.get("uploadBulsajaCode") or code),
                "상세상태": 상세, "상세미가공": 상세 != "AI가공완료", "번호검증": 검증})

    # ④ 옵션 — 현황판 기록. 못 읽으면 판정 불가(추측 금지)
    try:
        gname = lookup.group_name(wd.get("uploadSelectedMarketGroupId"))
        value, found = lookup.matrix_option(gname, market, pid)
    except Exception:
        value, found = None, False
    out["옵션상태"], out["옵션미정리"] = option_status(value, found)
    return out


# ---------------------------------------------------------------------------
# 실제 I/O — 커머스API + 불사자 MCP + 현황판, run-dir 캐시
# ---------------------------------------------------------------------------
def _atomic_json(path, obj, indent=1):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=indent)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


class BulsajaLookup:
    """enrich_rows 의 실제 lookup. 성공한 조회만 run-dir/bulsaja_cache 에 남긴다(재실행 비용 0)."""

    def __init__(self, cache_dir, mcp=None, commerce=None, sleep=time.sleep, log=print):
        self.cache = Path(cache_dir)
        self.mcp = mcp
        self.commerce = commerce
        self.sleep = sleep
        self.log = log
        self._last = 0.0
        self._stores = None
        self._tokens = {}
        self._secrets = []
        self._groups = None
        self._matrix_index = None
        self._matrix = {}

    # ---- 불사자 MCP --------------------------------------------------
    def call(self, name, args):
        gap = time.monotonic() - self._last
        if gap < MCP_GAP:
            self.sleep(MCP_GAP - gap)
        try:
            return join.strip_display_rules(self.mcp.call_tool(name, args) or {})
        finally:
            self._last = time.monotonic()

    def profile_nick(self):
        return str((self.call("bulsaja_my_profile", {}) or {}).get("닉네임") or "")

    def find(self, code):
        p = self.cache / f"find_{_safe_name(code)}.json"
        c = _read_json(p)
        if isinstance(c, list):
            return c
        import ss_index_calls as calls
        items = calls.항목꺼내기(self.call("bulsaja_product_find_by_code", {"codes": [code]}),
                              " (find_by_code)")
        items = [it for it in items if isinstance(it, dict)]
        _atomic_json(p, items)
        return items

    def workdata(self, pid):
        p = self.cache / f"wd_{_safe_name(pid)}.json"
        c = _read_json(p)
        if isinstance(c, dict):
            return c
        import ss_index_calls as calls
        data = calls.워크데이터꺼내기(
            self.call("bulsaja_product_workdata", {"productId": pid, "mode": "full"}), f" ({pid})")
        keep = {k: data.get(k) for k in ("uploadDetailContents", "uploadBulsajaCode",
                                          "uploadedSuccessUrl", "uploadSelectedMarketGroupId")}
        # 상세 HTML 은 판정에 안 쓰고 캐시만 불린다 — 플래그만 남긴다
        dc = keep.get("uploadDetailContents")
        if isinstance(dc, dict):
            keep["uploadDetailContents"] = {k: dc.get(k) for k in ("aiImageGenerated", "imageTranslated")}
        _atomic_json(p, keep)
        return keep

    def group_name(self, gid):
        if gid in (None, ""):
            return None
        if self._groups is None:
            p = self.cache / "market_groups.json"
            c = _read_json(p)
            if isinstance(c, dict):
                self._groups = c
            else:
                import ss_index_calls as calls
                gs = calls.그룹꺼내기(self.call("bulsaja_market_groups", {}), " (market_groups)")
                self._groups = {str(g.get("groupId")): g.get("그룹명") for g in gs if isinstance(g, dict)}
                _atomic_json(p, self._groups)
        return self._groups.get(str(gid))

    # ---- 현황판 ------------------------------------------------------
    def matrix_option(self, group_name, market, pid):
        """(현황판 '옵션' 값, found). 그룹 시트·행이 없거나 읽기 실패면 found False."""
        from eroomlib import matrix
        if self._matrix_index is None:
            try:
                self._matrix_index = matrix.index_groups()
            except Exception as e:
                self.log(f"  [경고] 현황판 인덱스 읽기 실패: {type(e).__name__}")
                self._matrix_index = []
        sid = None
        names = dict(self._matrix_index)
        if group_name and group_name in names:
            sid = names[group_name]
        else:
            # 그룹명이 표기만 다를 때 — 마켓번호가 같은 용쌤 그룹이 정확히 1개면 그것
            cands = [s for n, s in self._matrix_index
                     if "용쌤" in n and join.market_number(n) == market]
            sid = cands[0] if len(cands) == 1 else None
        if not sid:
            return None, False
        if sid not in self._matrix:
            p = self.cache / f"matrix_{_safe_name(sid)}.json"
            c = _read_json(p)
            if isinstance(c, dict):
                self._matrix[sid] = c
            else:
                m = matrix.read(sid)
                # {상품id: 옵션값} 만 남긴다 — 그룹 시트가 수만 행이라 나머지 열까지 담으면 캐시가 불어난다
                self._matrix[sid] = {k: str((v or {}).get("옵션", "")) for k, v in (m or {}).items()}
                if self._matrix[sid]:
                    _atomic_json(p, self._matrix[sid], indent=None)
        if str(pid) not in self._matrix[sid]:
            return None, False
        return self._matrix[sid][str(pid)], True

    # ---- 커머스API ---------------------------------------------------
    def _token(self, market):
        if market in self._tokens:
            tok = self._tokens[market]
            if tok is None:
                raise CommerceFailed("토큰 실패(이전)")
            return tok
        if self._stores is None:
            try:
                self._stores, _src = self.commerce.load_stores(SL.target_markets())
            except Exception as e:
                self.log(f"  [경고] 커머스 키 로드 실패: {type(e).__name__}")
                self._stores = {}
            self._secrets.extend(s.get("client_secret") for s in self._stores.values())
        st = self._stores.get(market)
        if not st:
            raise KeyMissing(market)
        try:
            tok, err = self.commerce.issue_token(st)
        except Exception as e:
            tok, err = None, type(e).__name__
        if not tok:
            self._tokens[market] = None
            self.log(f"  [경고] {market} 커머스 토큰 실패: {SL.redact(err, self._secrets)[:200]}")
            raise CommerceFailed(market)
        self._secrets.append(tok)
        self._tokens[market] = tok
        return tok

    def seller_code(self, market, channel_no):
        p = self.cache / f"channel_{_safe_name(market)}_{_safe_name(channel_no)}.json"
        c = _read_json(p)
        if isinstance(c, dict) and "sellerManagementCode" in c:
            return c["sellerManagementCode"]
        tok = self._token(market)
        try:
            d = self.commerce._request("GET", COMMERCE_PRODUCT_URL.format(no=channel_no), tok)
        except Exception as e:
            raise CommerceFailed(SL.redact(str(e), self._secrets)[:200])
        code = seller_code_of(d)
        # 캐시엔 코드 하나만 — 응답 전체(가격·재고 등)나 토큰을 남기지 않는다
        _atomic_json(p, {"sellerManagementCode": code})
        return code


# ---------------------------------------------------------------------------
# CLI 진입 — run_ads.py enrich 가 부른다
# ---------------------------------------------------------------------------
def _default_lookup(run_dir, log):
    """실제 lookup 을 만든다 (MCP 는 호출부가 open/close)."""
    from eroomlib.config import cfg
    from eroomlib.snapshot import ProductMCP
    from commerce_orders import CommerceClient
    mcp = ProductMCP()
    commerce = CommerceClient(cfg("sheets.orders", required=True))
    return BulsajaLookup(Path(run_dir) / "bulsaja_cache", mcp=mcp, commerce=commerce, log=log)


def apply_enrich(result, lookup):
    """result dict 의 ⑦c후보·⑦d후보 행만 보강해 제자리에 넣는다. (acct, adId) 중복은 1회 조회.

    반환 (hit, unmatched, rows). result 를 제자리에서 바꾼다.
    """
    uniq, order = {}, []
    for alias, v in (result.get("accounts") or {}).items():
        rules = (v or {}).get("rules") or {}
        for key in ENRICH_KEYS:
            for r in rules.get(key) or []:
                k = (alias, r.get("adId"))
                if k not in uniq:
                    uniq[k] = r
                    order.append(k)
    enriched = enrich_rows([uniq[k] for k in order], lookup)
    by = dict(zip(order, enriched))
    bulsaja_fields = ("마켓번호", "불사자매칭", "productId", "판매자상품코드", "상세상태", "상세미가공",
                      "옵션상태", "옵션미정리", "번호검증", "보강오류")
    for alias, v in (result.get("accounts") or {}).items():
        rules = (v or {}).get("rules") or {}
        for key in ENRICH_KEYS:
            new = []
            for r in rules.get(key) or []:
                e = by.get((alias, r.get("adId")))
                # 같은 소재라도 규칙별 지표(7일/30일)는 다르다 — 보강 필드만 얹는다
                new.append(dict(r, **{f: e[f] for f in bulsaja_fields if e and f in e}))
            if key in rules:
                rules[key] = new
    hit = sum(1 for e in enriched if e.get("불사자매칭") == MATCH_HIT)
    return hit, len(enriched) - hit, len(enriched)


def cmd_enrich(run_dir, expect_nick="부킹", lookup=None, log=print):
    """종료코드: 0 정상 · 3 계정 불일치/확인 실패 · 1 그 밖 실패(result.json 원본 유지)."""
    rp = Path(run_dir) / "result.json"
    try:
        result = json.loads(rp.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"result.json 읽기 실패: {type(e).__name__}: {e}")
        return 1
    own_mcp = lookup is None
    try:
        if own_mcp:
            lookup = _default_lookup(run_dir, log)
            lookup.mcp.open()
    except Exception as e:
        log(f"[중단] 불사자/설정 준비 실패: {type(e).__name__}")
        return 1
    try:
        try:
            nick = lookup.profile_nick()
        except Exception as e:
            log(f"[중단] 불사자 계정 조회 실패: {type(e).__name__}")
            return 3
        if nick != expect_nick:
            log(f"[중단] 불사자 계정이 '{expect_nick}' 가 아니다 (현재 '{nick}') — 조회 0건")
            return 3
        try:
            hit, un, n = apply_enrich(result, lookup)
        except Exception as e:
            log(f"[중단] 보강 실패: {type(e).__name__}: {str(e)[:200]}")
            return 1
        result["enrich"] = {"status": "ok", "rows": n, "hit": hit, "unmatched": un,
                            "at": datetime.now().isoformat(timespec="seconds")}
        try:
            _atomic_json(rp, result)
        except Exception as e:
            log(f"result.json 쓰기 실패: {type(e).__name__}")
            return 1
        log(f"보강 완료 — 대상 {n}건 · 히트 {hit} · 미매칭 {un}")
        return 0
    finally:
        if own_mcp:
            try:
                lookup.mcp.close()
            except Exception:
                pass
