# -*- coding: utf-8 -*-
"""시트 탭 구조와 행 조립. 수식 열은 값이 아니라 수식 문자열로 넣는다."""
import rules

SCAN_TAB = "카테고리스캔"
BENCH_TAB = "후보"

SCAN_HEADER = ["스캔일", "대", "중", "소", "세부", "카테고리코드", "리뷰1000+ 상품수", "상위 상품명 3개",
               "키워드", "검색량(참고)", "경쟁도(참고)", "상태", "벤치완료"]
SCAN_COL = {"키워드": 8, "검색량": 9, "경쟁도": 10, "벤치완료": 12}

BENCH_HEADER = ["대카테고리", "중카테고리", "소카테고리", "세부카테고리", "키워드", "마켓명", "상품 URL",
                "상품명", "옵션 개수", "각 옵션 가격", "180일 판매수량", "일 예상판매량", "일 예상매출",
                "월 예상매출", "1688 이미지검색 링크", "1688 위안가격", "원화환산(×210)",
                "추정 국내원가(×1.4)", "1개당 예상마진", "월 예상마진",
                "대표판매가", "수집일", "리뷰수", "상태"]


def _c(col):
    """현재 행의 해당 열 참조. append 위치를 몰라도 맞도록 ROW() 로 잡는다."""
    return f"INDEX({col}:{col},ROW())"


# 0-based 열 위치 → 수식 (K=180일 판매량, U=대표판매가, P=위안)
FORMULAS = {
    11: f'=IF({_c("K")}="","",{_c("K")}/180)',
    12: f'=IF({_c("L")}="","",{_c("L")}*{_c("U")})',
    13: f'=IF({_c("M")}="","",{_c("M")}*30)',
    16: f'=IF({_c("P")}="","",{_c("P")}*210)',
    17: f'=IF({_c("Q")}="","",{_c("Q")}*1.4)',
    18: f'=IF({_c("R")}="","",{_c("U")}-{_c("R")})',
    19: f'=IF(OR({_c("L")}="",{_c("S")}=""),"",{_c("L")}*30*{_c("S")})',
}


def scan_row(date, cat, summary):
    return [date, *cat["경로"], cat["코드"], summary["리뷰1000+"], summary["상위3"], "", "", "", "", ""]


def bench_row(date, keyword, product, options):
    """options=None 이면 옵션 수집 실패 → 9·10열 비우고 상태=옵션수동."""
    cats = (list(product.get("카테고리") or []) + ["", "", "", ""])[:4]
    fallback = rules.to_int(product.get("가격"))
    ok = options is not None
    row = [*cats, keyword, product.get("마켓명", ""), rules.norm_url(product.get("url", "")),
           product.get("상품명", ""),
           len(options) if ok else "", rules.options_text(options) if ok else "",
           "", "", "", "", "", "", "", "", "", ""]
    for idx, f in FORMULAS.items():
        row[idx] = f
    row += [rules.rep_price(options or [], fallback), date,
            rules.to_int(product.get("리뷰수")) or 0, "" if ok else "옵션수동"]
    return row
