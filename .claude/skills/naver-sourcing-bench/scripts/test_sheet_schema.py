# -*- coding: utf-8 -*-
import sheet_schema as S

PROD = {"순위": 1, "상품명": "압축봉 120cm", "url": "https://smartstore.naver.com/s/products/9?NaPm=1",
        "마켓명": "가나상점", "가격": "15,000", "리뷰수": 812, "광고": False,
        "카테고리": ["생활/건강", "수납/정리", "압축봉", ""]}


def test_headers():
    assert len(S.BENCH_HEADER) == 26
    assert S.BENCH_HEADER[:5] == ["대카테고리", "중카테고리", "소카테고리", "세부카테고리", "키워드"]
    assert S.BENCH_HEADER[8:10] == ["옵션 개수", "180일 판매수량"]
    assert "각 옵션 가격" not in S.BENCH_HEADER and "1688 이미지검색 링크" not in S.BENCH_HEADER
    assert S.BENCH_HEADER[12:15] == ["월 예상매출", "1688 링크", "1688 위안가격"]
    assert S.BENCH_HEADER[18:21] == ["월 예상마진", "쿠팡포함 월 예상마진(×2)", "쿠팡포함 월 투자금"]
    assert S.BENCH_HEADER[21:] == ["대표판매가", "수집일", "리뷰수", "원산지", "상태"]
    assert (S.COL_REP, S.COL_ORIGIN, S.COL_STATUS) == (21, 24, 25)
    assert S.SCAN_HEADER[S.SCAN_COL["키워드"]] == "키워드"
    assert S.SCAN_HEADER[S.SCAN_COL["벤치완료"]] == "벤치완료"


def test_bench_row_status_store_expand():
    opts = [{"이름": "흰", "가격": 13900}]
    assert S.bench_row("d", "k", PROD, opts, status="스토어확장")[S.COL_STATUS] == "스토어확장"
    assert S.bench_row("d", "k", PROD, None, status="스토어확장")[S.COL_STATUS] == "스토어확장·옵션수동"
    assert S.bench_row("d", "k", PROD, opts)[S.COL_STATUS] == ""
    assert S.bench_row("d", "k", PROD, None)[S.COL_STATUS] == "옵션수동"


def test_bench_row_origin_unknown():
    opts = [{"이름": "흰", "가격": 13900}]
    assert S.bench_row("d", "k", PROD, opts, origin_unknown=True)[S.COL_STATUS] == "원산지미확인"
    assert S.bench_row("d", "k", PROD, None, origin_unknown=True)[S.COL_STATUS] == "옵션수동·원산지미확인"
    assert S.bench_row("d", "k", PROD, None, status="스토어확장", origin_unknown=True)[S.COL_STATUS] == \
        "스토어확장·옵션수동·원산지미확인"


def test_bench_row_with_options():
    opts = [{"이름": "흰", "가격": 13900}, {"이름": "검", "가격": 12900}]
    r = S.bench_row("2026-10-02", "압축봉", PROD, opts)
    assert len(r) == 26
    assert r[:9] == ["생활/건강", "수납/정리", "압축봉", "", "압축봉", "가나상점",
                     "https://smartstore.naver.com/s/products/9", "압축봉 120cm", 2]
    assert r[9] == "" and r[13] == "" and r[14] == ""          # 수동 칸(180일·1688 링크·위안)
    assert r[10] == '=IF(INDEX(J:J,ROW())="","",INDEX(J:J,ROW())/180)'
    assert r[11] == '=IF(INDEX(K:K,ROW())="","",INDEX(K:K,ROW())*INDEX(V:V,ROW()))'
    assert r[12] == '=IF(INDEX(L:L,ROW())="","",INDEX(L:L,ROW())*30)'
    assert r[15] == '=IF(INDEX(O:O,ROW())="","",INDEX(O:O,ROW())*210)'
    assert r[16] == '=IF(INDEX(P:P,ROW())="","",INDEX(P:P,ROW())*1.4)'
    assert r[17] == '=IF(INDEX(Q:Q,ROW())="","",INDEX(V:V,ROW())-INDEX(Q:Q,ROW()))'
    assert r[18] == '=IF(OR(INDEX(K:K,ROW())="",INDEX(R:R,ROW())=""),"",INDEX(K:K,ROW())*30*INDEX(R:R,ROW()))'
    assert r[19] == '=IF(INDEX(S:S,ROW())="","",INDEX(S:S,ROW())*2)'
    assert r[20] == '=IF(OR(INDEX(K:K,ROW())="",INDEX(Q:Q,ROW())=""),"",INDEX(Q:Q,ROW())*INDEX(K:K,ROW())*30*2)'
    assert r[21:] == [12900, "2026-10-02", 812, "", ""]


def test_bench_row_options_failed_marks_manual():
    r = S.bench_row("2026-10-02", "압축봉", PROD, None)
    assert r[8] == ""
    assert r[S.COL_REP] == 15000          # 검색 가격으로 대체
    assert r[S.COL_STATUS] == "옵션수동"


def test_scan_row():
    cat = {"코드": "3", "경로": ["생활/건강", "수납/정리", "압축봉", ""]}
    r = S.scan_row("2026-10-02", cat, {"리뷰1000+": 4, "상위3": "a / b / c"})
    assert r == ["2026-10-02", "생활/건강", "수납/정리", "압축봉", "", "3", 4, "a / b / c", "", "", "", "", ""]


def test_formulas_row_relative_only():
    # 행 삭제 안전성: 모든 수식이 ROW() 기준이고 A1 고정 셀 참조가 없다
    import re
    for f in S.FORMULAS.values():
        assert "ROW()" in f
        assert not re.search(r"[A-Z]+\d+", f), f
