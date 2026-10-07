# -*- coding: utf-8 -*-
"""소싱 벤치마크 판정 규칙. 네트워크·파일 접근 없는 순수 함수만 둔다."""
import re
from urllib.parse import urlsplit


def to_int(v):
    """'12,900원' / 12900 / '12900' → 12900. 숫자가 없으면 None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    digits = re.sub(r"[^\d]", "", str(v))
    return int(digits) if digits else None


_PATH_ID_HOSTS = ("smartstore.naver.com", "brand.naver.com", "search.shopping.naver.com")
_TRACKING = re.compile(r"^(utm_|nl-|NaPm$|n_|nv_|cr_|fbclid$|gclid$)", re.I)


def norm_url(url):
    """추적 파라미터를 떼어 같은 상품이면 같은 문자열이 되게 한다.
    상품ID가 경로에 있는 네이버 계열만 쿼리를 통째로 버리고, 다른 몰은 쿼리에 ID 가 있어
    (예: daisomall ?pdNo=) 추적 파라미터만 뗀다."""
    try:
        s = urlsplit(str(url).strip())
    except ValueError:
        return str(url).strip()
    host = s.netloc.lower()
    if host.startswith("m.smartstore."):
        host = host[2:]
    base = f"https://{host}{s.path.rstrip('/')}"
    if host in _PATH_ID_HOSTS or not s.query:
        return base
    keep = [kv for kv in s.query.split("&") if kv and not _TRACKING.match(kv.split("=", 1)[0])]
    return base + ("?" + "&".join(keep) if keep else "")


def _split(path):
    return [p.strip() for p in str(path).split(">") if p.strip()]


def leaf_categories(master, root_path):
    """root_path(대·대>중·…·리프) 하위의 리프 카테고리. 경로는 4칸으로 맞춘다.
    root_path 자체가 리프면 그 하나만 돌려준다."""
    root = _split(root_path)
    rows = master.get("카테고리", [])
    if not any(_split(c.get("경로정규화", "")) == root for c in rows):
        raise ValueError(f"카테고리 마스터에 없는 경로: {root_path}")
    out = []
    for c in rows:
        parts = _split(c.get("경로정규화", ""))
        if c.get("last") and parts[:len(root)] == root:
            out.append({"코드": str(c.get("id")), "경로": (parts + ["", "", "", ""])[:4]})
    return out


def _review(p):
    return to_int(p.get("리뷰수")) or 0


def scan_summary(products, min_review=1000):
    """리뷰 많은 순 목록에서 기준 이상 상품 수와 상위 3개 이름."""
    n = sum(1 for p in products if _review(p) >= min_review)
    top3 = " / ".join(str(p.get("상품명", "")) for p in products[:3])
    return {"리뷰1000+": n, "상위3": top3}


# 후보에서 빼는 마켓(마켓명 부분일치). 사용자가 지시할 때마다 추가한다.
EXCLUDED_MALLS = ("한샘",)   # 2026-10-08 용팀장: 한샘몰은 리스트업 금지


def is_excluded_mall(name):
    return any(k in str(name or "") for k in EXCLUDED_MALLS)


def bench_filter(products, top_n=40, min_review=500, min_price=10000):
    """광고 제외 → 순위 상위 top_n → 가격비교(카탈로그) 제외 → 리뷰·가격 필터 → URL 중복 제거.
    가격비교 묶음은 여러 몰 합산이라 한 판매자 실적이 아니다 — 2026-10-07 용팀장 지시로 패스."""
    organic = sorted((p for p in products if not p.get("광고")),
                     key=lambda p: p.get("순위") or 0)[:top_n]
    seen, out = set(), []
    for p in organic:
        if is_catalog(p.get("url")) or str(p.get("마켓명", "")).startswith("가격비교") \
                or is_excluded_mall(p.get("마켓명")):
            continue
        price = to_int(p.get("가격"))
        if price is None or price < min_price or _review(p) < min_review:
            continue
        key = norm_url(p.get("url", ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def rep_price(options, fallback):
    """대표 판매가 = 옵션 최저가. 옵션이 없으면 fallback."""
    prices = [to_int(o.get("가격")) for o in options or []]
    prices = [x for x in prices if x]
    return min(prices) if prices else fallback


def options_text(options):
    """'옵션명:가격 / …' 한 셀 문자열."""
    return " / ".join(f"{o.get('이름', '')}:{to_int(o.get('가격')) or 0:,}" for o in options or [])


# ---- 상세페이지 옵션 판정 (2026-10-02 실측 기반) ----

OPTION_JOIN = "-"          # 다단 조합명 구분자 (D-02, 예 '화이트-10개')
MAX_COMBOS = 15            # 이 개수를 넘으면 소싱 대상 아님. 정확히 15 는 통과 (2026-10-08 용팀장: 50→15)
_LEAD_NO = re.compile(r"^\s*\d+\.\s*")                       # '5. ' 같은 앞 번호
_EXTRA = re.compile(r"\(\s*([+-])\s*([\d,]+)\s*원\s*\)")       # '(+1,200원)' / '(-500원)'
_SOLDOUT = re.compile(r"\(\s*품절\s*\)|\s품절$")
_FORMULA_LEAD = re.compile(r"^[\s=+@\-]+")                   # 시트가 수식으로 읽는 시작 문자 (T-mbo-01)


def parse_option_item(text):
    """옵션 목록 항목 텍스트 → {이름, 추가금, 품절}.
    괄호로 감싼 (+N원)/(-N원) 만 추가금이다. '10+10개' 처럼 괄호 없는 + 는 이름의 일부."""
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    s = _LEAD_NO.sub("", s)
    extra = 0
    m = _EXTRA.search(s)
    if m:
        extra = int(m.group(2).replace(",", "")) * (-1 if m.group(1) == "-" else 1)
        s = _EXTRA.sub("", s)
    soldout = bool(_SOLDOUT.search(s))
    s = _SOLDOUT.sub("", s)
    s = _FORMULA_LEAD.sub("", re.sub(r"\s+", " ", s).strip())
    return {"이름": s, "추가금": extra, "품절": soldout}


def parse_base_price(text):
    """'상품 가격' 이후 텍스트에서 첫 'N원' (= 할인가가 있으면 할인가). 없으면 None."""
    m = re.search(r"(\d[\d,]*)\s*원", str(text or ""))
    return int(m.group(1).replace(",", "")) if m else None


def is_catalog(url):
    """가격비교(카탈로그) 상품 — 상세 옵션을 읽지 않는다 (D-03)."""
    return "/catalog/" in str(url or "")


_FAIL = {"판정": "실패", "options": None}


def build_options(probe, fallback, max_combos=MAX_COMBOS):
    """options 드라이버 원시 결과 → {판정: 성공|옵션초과|실패, options}.

    - 가격 = 페이지 기본가 + 조합 각 부분 추가금의 합 (D-02).
      네이버 조합형은 마지막 축에만 금액이 붙어 합 = 마지막 축 금액이고, 독립형은 합이 그대로 맞다.
    - 품절 조합도 판매자가 운영하는 조합이라 개수에 넣고 이름 끝에 '(품절)' 을 붙인다(재량 결정).
    - 페이지 기본가를 못 읽으면 검색 대표가(fallback)로 대신한다 — 사람 큐를 늘리지 않기 위한 재량 결정.
    - 이상 입력은 예외 대신 '실패' 판정 → 호출부가 옵션수동으로 남긴다 (D-03).
    """
    try:
        if not isinstance(probe, dict):
            return dict(_FAIL)
        st = probe.get("상태")
        if st == "옵션초과":
            return {"판정": "옵션초과", "options": None}
        base = parse_base_price(probe.get("priceText"))
        if base is None:
            base = to_int(fallback)
        if st == "단품":
            if base is None:
                return dict(_FAIL)
            return {"판정": "성공", "options": [{"이름": "단품", "가격": base}]}    # D-04
        combos = probe.get("combos")
        if st != "성공" or not isinstance(combos, list) or not combos:
            return dict(_FAIL)
        if len(combos) > max_combos:
            return {"판정": "옵션초과", "options": None}
        if base is None:
            return dict(_FAIL)
        out = []
        for combo in combos:
            parts = [combo] if isinstance(combo, str) else combo
            if not isinstance(parts, list) or not parts:
                return dict(_FAIL)
            items = [parse_option_item(p) for p in parts]
            name = OPTION_JOIN.join(i["이름"] for i in items if i["이름"])
            if not name:
                return dict(_FAIL)
            if any(i["품절"] for i in items):
                name += "(품절)"
            out.append({"이름": name, "가격": base + sum(i["추가금"] for i in items)})
        return {"판정": "성공", "options": out}
    except (TypeError, ValueError, AttributeError):
        return dict(_FAIL)
