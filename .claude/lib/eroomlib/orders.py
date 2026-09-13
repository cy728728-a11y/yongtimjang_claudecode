#!/usr/bin/env python3
"""주문 시트(★마진율계산기★) 읽기·정규화·집계 1벌.

**왜 eroomlib 인가**: 소비자가 스킬 경계를 넘는다. 쿠팡 후보 선별뿐 아니라
`naver-ads-weekly`(구매0·효자상품 분류)와 `bulsaja-product-lock`("판매된 상품을
잠근다" 의 목록)도 같은 실적 원장을 필요로 하는데, 지금은 어느 쪽도 갖고 있지 않다.

**이 시트의 함정 4가지** (2026-09-13 21개 탭 전수 실측):
1. `판매자 상품 코드` 열은 **`2025 10` 탭부터만 존재한다.** 그 앞 9개 탭에는 아예 없다.
2. 열 구성이 월마다 다르다(47~67열). **열 위치를 박으면 반드시 어긋난다** — 3행 헤더로 찾는다.
3. 헤더에 줄바꿈이 섞여 있다(`A+B+C+D\\n지출계`, `마켓\\n주문번호`).
4. 결측은 빈칸이 아니라 `"  - "`(좌우 공백 포함) 또는 `"입력하기"` 다.

**헤더 매칭 규칙**: 공백·개행을 전부 없앤 뒤 **정확일치 우선, 없으면 부분일치**.
`배송비` 는 7개 열에 부분일치하므로(`A배대지배송비`·`실제 배대지 배송비`·
`배송비 차이(예상-실제)`...) 정확일치가 이겨야 I열을 집는다. 반대로 `지출계` 는
정확일치가 없어서 부분일치로 `A+B+C+D지출계` 에 떨어져야 한다.
"""
import re
import statistics

# 집계에 쓰는 표준 필드명 → 시트 헤더에서 이 이름으로 찾는다.
FIELDS = (
    "판매자상품코드", "판매처", "상품명", "수량", "결제금액", "마켓수수료율",
    "이익", "마진률", "주문일자", "사업자명의", "배송비",
)

HEADER_ROW = 3          # 헤더가 있는 행(1부터)
FIRST_DATA_ROW = 4
LAST_DATA_ROW = 2100    # 최대 탭이 2,004행. 여유를 둔다.

# 불사자 판매자상품코드는 21자 nanoid. base64형(`PTk/PT0/...`)은 다른 소스라 제외한다.
BULSAJA_CODE_LEN = 21
_CODE_RE = re.compile(r"^[A-Za-z0-9_-]{21}$")
_MONTH_TAB_RE = re.compile(r"^(\d{4}) (\d{2})$")
_MARKET_RE = re.compile(r"스마트스토어\s*\((\d+)-(\d+)\)")
_MISSING = {"", "-", "입력하기", "#N/A", "#REF!", "#VALUE!", "#DIV/0!"}


# ---------------------------------------------------------------- 순수 헬퍼

def norm_header(s):
    """헤더 비교용 정규화 — 공백·개행을 전부 없앤다."""
    return re.sub(r"\s+", "", str(s or ""))


def col_letter(idx0):
    """0-기반 열 인덱스 → 시트 열 문자('A', 'R', 'AY')."""
    s, n = "", idx0 + 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def header_map(header_row, fields=FIELDS):
    """3행 헤더 리스트 → `{표준필드명: 0기반 열인덱스}`. 없는 열은 키가 없다.

    정확일치 우선, 없으면 부분일치. 둘 다 여러 개면 **가장 왼쪽**을 집는다
    (2025 06 탭처럼 같은 헤더가 두 번 나오는 경우가 있다).
    """
    norm = [norm_header(h) for h in (header_row or [])]
    out = {}
    for f in fields:
        key = norm_header(f)
        hit = next((i for i, h in enumerate(norm) if h and h == key), None)
        if hit is None:
            hit = next((i for i, h in enumerate(norm) if h and key in h), None)
        if hit is not None:
            out[f] = hit
    return out


def parse_money(s):
        """`"16,161"` / `"  - "` / `"(3,500)"` → float 또는 None."""
        t = str(s if s is not None else "").strip()
        if t in _MISSING or not t:
            return None
        neg = t.startswith("(") and t.endswith(")")
        t = t.strip("()").replace(",", "").replace("₩", "").replace("원", "").strip()
        if t in _MISSING or not t:
            return None
        try:
            v = float(t)
        except ValueError:
            return None
        return -v if neg else v


def parse_pct(s):
    """`"18%"` → 18.0, `"0.18"` → 18.0, 결측 → None.

    소수 표기를 %로 환산하는 이유: 같은 열에 `7%` 와 `0.07` 이 섞여 들어온다
    (수식 열과 수기 입력 열이 다르다).
    """
    t = str(s if s is not None else "").strip()
    if t in _MISSING or not t:
        return None
    had_sign = t.endswith("%")
    v = parse_money(t.rstrip("%"))
    if v is None:
        return None
    if not had_sign and -1.0 < v < 1.0 and v != 0:
        return v * 100.0
    return v


def code_kind(s):
    """`"bulsaja"`(21자 nanoid) / `"other"`(base64형 등) / `"none"`(빈칸)."""
    t = str(s or "").strip()
    if not t:
        return "none"
    return "bulsaja" if _CODE_RE.match(t) else "other"


def market_number_of(판매처):
    """`"스마트스토어(13-2)"` → `"13-2"`. 쿠팡·기타는 None."""
    m = _MARKET_RE.search(str(판매처 or ""))
    return f"{m.group(1)}-{m.group(2)}" if m else None


def market_group_of(판매처):
    """`"스마트스토어(20-1)"` → `"20번_용쌤20-1"`. 쿠팡·기타는 None.

    ⚠️ 앞번호는 1~20 순환이라 충돌한다(`1번_용쌤21-1` 존재). 이 함수가 만드는 이름은
    **마켓번호가 앞번호와 같은 일반형**이고, 실제 그룹명 매칭은 `용쌤` 뒤 번호로 해야 한다.
    """
    n = market_number_of(판매처)
    if not n:
        return None
    return f"{n.split('-')[0]}번_용쌤{n}"


def month_tab_names(tab_titles):
    """탭 이름 목록 → `"YYYY MM"` 형식만 걸러 정렬 반환.

    `"2026 08 정인호"` 처럼 꼬리가 붙은 탭은 **별도 장부**다. 본 탭과 같이 집계하면
    이중 계상되므로 제외한다.
    """
    return sorted(t for t in (tab_titles or []) if _MONTH_TAB_RE.match(str(t or "").strip()))


def p75(values):
    """상위 25% 분위값(선형보간). 배송비 채택값 — 중앙값을 쓰면 과소책정된다."""
    v = sorted(float(x) for x in (values or []))
    if not v:
        return None
    if len(v) == 1:
        return v[0]
    pos = 0.75 * (len(v) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


def spread_pct(values):
    """`(최대-최소)/최소 × 100`. 값이 없으면 None, 1개면 0."""
    v = [float(x) for x in (values or []) if x]
    if not v:
        return None
    lo, hi = min(v), max(v)
    return 0.0 if lo <= 0 else (hi - lo) / lo * 100.0


# ---------------------------------------------------------------- 집계

def aggregate(rows):
    """정규화된 주문행 목록 → `{판매자상품코드: 실적레코드}`.

    **가중마진을 쓴다**(산술평균 금지). `마진률` 들의 단순 평균은 소액 주문 1건이
    대형 주문 10건과 같은 가중치를 갖는다 — 실측에서 한 코드가 단순평균 31.4% vs
    가중 11.6% 로 20%p 벌어졌다.

    **유효행 조건은 결제금액·이익·마진률 셋 다**. 이익만 있고 마진률이 없는 행을 섞으면
    분모와 분자가 서로 다른 모집단이 된다.

    결측 마진 행도 `주문수`·`매출` 에는 남긴다 — 실적은 실적이다.
    """
    out = {}
    for r in rows or []:
        code = str(r.get("판매자상품코드") or "").strip()
        if code_kind(code) != "bulsaja":
            continue
        rec = out.get(code)
        if rec is None:
            rec = out[code] = {
                "판매자상품코드": code, "상품명": "", "주문수": 0, "수량": 0,
                "매출": 0.0, "유효행수": 0, "유효매출": 0.0, "유효이익": 0.0,
                "가중마진": None, "최소마진": None, "적자건수": 0,
                "마진들": [], "수수료율들": [], "배송비단위": [],
                "마켓그룹": {}, "사업자명의": {},
                "최초주문일": "", "최근주문일": "",
            }

        rec["주문수"] += 1
        if not rec["상품명"]:
            rec["상품명"] = str(r.get("상품명") or "").strip()

        qty = parse_money(r.get("수량")) or 0
        qty = int(qty) if qty and qty > 0 else 1
        rec["수량"] += qty

        amt = parse_money(r.get("결제금액"))
        if amt is not None:
            rec["매출"] += amt

        profit = parse_money(r.get("이익"))
        margin = parse_pct(r.get("마진률"))
        if amt is not None and profit is not None and margin is not None:
            rec["유효행수"] += 1
            rec["유효매출"] += amt
            rec["유효이익"] += profit
            rec["마진들"].append(margin)
            if margin < 0:
                rec["적자건수"] += 1

        fee = parse_pct(r.get("마켓수수료율"))
        if fee is not None:
            rec["수수료율들"].append(fee)

        ship = parse_money(r.get("배송비"))
        if ship is not None and ship > 0:
            rec["배송비단위"].append(ship / qty)

        num = market_number_of(r.get("판매처"))
        if num:
            rec["마켓그룹"][num] = rec["마켓그룹"].get(num, 0) + 1

        owner = str(r.get("사업자명의") or "").strip()
        if owner:
            rec["사업자명의"][owner] = rec["사업자명의"].get(owner, 0) + 1

        day = str(r.get("주문일자") or "").strip()
        if day:
            if not rec["최초주문일"] or day < rec["최초주문일"]:
                rec["최초주문일"] = day
            if day > rec["최근주문일"]:
                rec["최근주문일"] = day

    for rec in out.values():
        if rec["유효행수"] and rec["유효매출"]:
            rec["가중마진"] = rec["유효이익"] / rec["유효매출"] * 100.0
        if rec["마진들"]:
            rec["최소마진"] = min(rec["마진들"])
        rec["평균수수료율"] = (statistics.mean(rec["수수료율들"])
                          if rec["수수료율들"] else None)
        rec["배송비P75"] = p75(rec["배송비단위"])
        rec["배송비중앙"] = (statistics.median(rec["배송비단위"])
                        if rec["배송비단위"] else None)
        rec["배송비편차"] = spread_pct(rec["배송비단위"])
    return out


# ---------------------------------------------------------------- 네트워크

def month_tabs(sheet_id):
    """주문 시트의 월별 탭 이름 목록(정렬). gws 1콜."""
    from . import gsheets
    return month_tab_names(gsheets.sheets_tabs(sheet_id))


def read_months(sheet_id, tabs, fields=FIELDS, log=None):
    """여러 월 탭을 batchGet 으로 한 번에 읽어 정규화된 행 목록을 반환.

    헤더(3행)를 먼저 전 탭 한 번에 받고, 탭마다 **실제로 존재하는 열만** 골라
    두 번째 batchGet 으로 데이터를 받는다. gws 콜은 총 2회.

    `판매자상품코드` 열이 없는 탭(2025 09 이전)은 **통째로 건너뛴다** —
    코드가 없으면 어떤 상품의 실적인지 결합할 방법이 없다.
    """
    from . import gsheets
    tabs = list(tabs)
    if not tabs:
        return [], {}

    heads = gsheets.sheets_batch_get(
        sheet_id, [f"'{t}'!A{HEADER_ROW}:CZ{HEADER_ROW}" for t in tabs])

    plans, skipped = [], {}
    for tab, h in zip(tabs, heads):
        hm = header_map(h[0] if h else [], fields)
        if "판매자상품코드" not in hm:
            skipped[tab] = "판매자상품코드 열 없음"
            continue
        plans.append((tab, hm))

    ranges, meta = [], []
    for tab, hm in plans:
        for f, idx in sorted(hm.items(), key=lambda kv: kv[1]):
            c = col_letter(idx)
            ranges.append(f"'{tab}'!{c}{FIRST_DATA_ROW}:{c}{LAST_DATA_ROW}")
            meta.append((tab, f))

    cols = gsheets.sheets_batch_get(sheet_id, ranges) if ranges else []

    by_tab = {}
    for (tab, f), vals in zip(meta, cols):
        by_tab.setdefault(tab, {})[f] = [(v[0] if v else "") for v in vals]

    rows = []
    for tab, _ in plans:
        cm = by_tab.get(tab) or {}
        n = max((len(v) for v in cm.values()), default=0)
        for i in range(n):
            rec = {f: (vs[i] if i < len(vs) else "") for f, vs in cm.items()}
            if code_kind(rec.get("판매자상품코드")) == "none":
                continue
            rec["_탭"] = tab
            rows.append(rec)
        if log:
            log(f"  {tab}: {n}행")
    return rows, skipped


def load(sheet_id, tabs=None, log=None):
    """주문 시트 → `({코드: 실적}, 건너뛴탭)`. 전체 흐름 1줄 진입점."""
    tabs = tabs if tabs is not None else month_tabs(sheet_id)
    rows, skipped = read_months(sheet_id, tabs, log=log)
    return aggregate(rows), skipped
