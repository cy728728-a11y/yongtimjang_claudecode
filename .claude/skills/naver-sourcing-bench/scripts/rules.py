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


def norm_url(url):
    """추적 파라미터를 떼어 같은 상품이면 같은 문자열이 되게 한다."""
    try:
        s = urlsplit(str(url).strip())
    except ValueError:
        return str(url).strip()
    host = s.netloc.lower()
    if host.startswith("m.smartstore."):
        host = host[2:]
    return f"https://{host}{s.path.rstrip('/')}"


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


def bench_filter(products, top_n=40, min_review=500, min_price=10000):
    """광고 제외 → 순위 상위 top_n → 리뷰·가격 필터 → URL 중복 제거."""
    organic = sorted((p for p in products if not p.get("광고")),
                     key=lambda p: p.get("순위") or 0)[:top_n]
    seen, out = set(), []
    for p in organic:
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
