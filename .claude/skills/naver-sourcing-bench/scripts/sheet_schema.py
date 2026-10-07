# -*- coding: utf-8 -*-
"""시트 탭 구조와 행 조립. 수식 열은 값이 아니라 수식 문자열로 넣는다."""
import rules

SCAN_TAB = "카테고리스캔"
BENCH_TAB = "후보"

SCAN_HEADER = ["스캔일", "대", "중", "소", "세부", "카테고리코드", "리뷰1000+ 상품수", "상위 상품명 3개",
               "키워드", "검색량(참고)", "경쟁도(참고)", "상태", "벤치완료"]
SCAN_COL = {"키워드": 8, "검색량": 9, "경쟁도": 10, "벤치완료": 12}

BENCH_HEADER = ["대카테고리", "중카테고리", "소카테고리", "세부카테고리", "키워드", "마켓명", "상품 URL",
                "상품명", "옵션 개수", "180일 판매수량", "일 예상판매량", "일 예상매출",
                "월 예상매출", "1688 링크", "1688 위안가격", "원화환산(×210)",
                "추정 국내원가(×1.4)", "1개당 예상마진", "월 예상마진",
                "쿠팡포함 월 예상마진(×2)", "쿠팡포함 월 투자금",
                "대표판매가", "수집일", "리뷰수", "원산지", "상태"]
# 수식이 아닌 보조 열 위치(0-based). 열을 끼워 넣으면 여기만 고친다.
COL_REP = BENCH_HEADER.index("대표판매가")     # V
COL_ORIGIN = BENCH_HEADER.index("원산지")      # Y — 상세 상품정보의 원산지 원문 (2026-10-08)
COL_STATUS = BENCH_HEADER.index("상태")       # Y


def _c(col):
    """현재 행의 해당 열 참조. append 위치를 몰라도 맞도록 ROW() 로 잡는다."""
    return f"INDEX({col}:{col},ROW())"


def _L(name):
    """헤더 이름 → 열 문자. 열을 넣고 빼도 수식이 따라오도록 문자를 하드코딩하지 않는다."""
    i = BENCH_HEADER.index(name)
    return chr(ord("A") + i) if i < 26 else "A" + chr(ord("A") + i - 26)


def _r(name):
    return _c(_L(name))


_K, _L1, _M = _r("180일 판매수량"), _r("일 예상판매량"), _r("일 예상매출")
_P, _Q, _R = _r("1688 위안가격"), _r("원화환산(×210)"), _r("추정 국내원가(×1.4)")
_S, _T, _W = _r("1개당 예상마진"), _r("월 예상마진"), _r("대표판매가")

# 헤더 이름 → 수식
_FORMULAS_BY_NAME = {
    "일 예상판매량": f'=IF({_K}="","",{_K}/180)',
    "일 예상매출": f'=IF({_L1}="","",{_L1}*{_W})',
    "월 예상매출": f'=IF({_M}="","",{_M}*30)',
    "원화환산(×210)": f'=IF({_P}="","",{_P}*210)',
    "추정 국내원가(×1.4)": f'=IF({_Q}="","",{_Q}*1.4)',
    "1개당 예상마진": f'=IF({_R}="","",{_W}-{_R})',
    "월 예상마진": f'=IF(OR({_L1}="",{_S}=""),"",{_L1}*30*{_S})',
    "쿠팡포함 월 예상마진(×2)": f'=IF({_T}="","",{_T}*2)',                       # 쿠팡 포함(스마트스토어와 동일 판매 가정)
    "쿠팡포함 월 투자금": f'=IF(OR({_L1}="",{_R}=""),"",{_R}*{_L1}*30*2)',  # 국내원가×30일 판매량×2(쿠팡 동일 판매 가정)
}
# 0-based 열 위치 → 수식
FORMULAS = {BENCH_HEADER.index(n): f for n, f in _FORMULAS_BY_NAME.items()}


def scan_row(date, cat, summary):
    return [date, *cat["경로"], cat["코드"], summary["리뷰1000+"], summary["상위3"], "", "", "", "", ""]


def bench_row(date, keyword, product, options, status="", origin_unknown=False, origin=""):
    """options=None 이면 옵션 수집 실패 → 9열 비우고 상태=옵션수동.
    status='스토어확장' 이면 상태 앞에 붙고, origin_unknown 이면 '원산지미확인' 을 병기한다."""
    cats = (list(product.get("카테고리") or []) + ["", "", "", ""])[:4]
    fallback = rules.to_int(product.get("가격"))
    ok = options is not None
    row = [*cats, keyword, product.get("마켓명", ""), rules.norm_url(product.get("url", "")),
           product.get("상품명", ""),
           len(options) if ok else ""]
    row += [""] * (COL_REP - len(row))
    for idx, f in FORMULAS.items():
        row[idx] = f
    row += [rules.rep_price(options or [], fallback), date,
            rules.to_int(product.get("리뷰수")) or 0, str(origin or ""),
            "·".join(x for x in (status, "" if ok else "옵션수동", "원산지미확인" if origin_unknown else "") if x)]
    return row
