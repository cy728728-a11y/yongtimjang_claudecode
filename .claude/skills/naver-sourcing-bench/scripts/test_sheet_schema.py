# -*- coding: utf-8 -*-
import sheet_schema as S

PROD = {"순위": 1, "상품명": "압축봉 120cm", "url": "https://smartstore.naver.com/s/products/9?NaPm=1",
        "마켓명": "가나상점", "가격": "15,000", "리뷰수": 812, "광고": False,
        "카테고리": ["생활/건강", "수납/정리", "압축봉", ""]}


def test_headers():
    assert len(S.BENCH_HEADER) == 24
    assert S.BENCH_HEADER[:5] == ["대카테고리", "중카테고리", "소카테고리", "세부카테고리", "키워드"]
    assert S.BENCH_HEADER[10] == "180일 판매수량"
    assert S.BENCH_HEADER[20:] == ["대표판매가", "수집일", "리뷰수", "상태"]
    assert S.SCAN_HEADER[S.SCAN_COL["키워드"]] == "키워드"
    assert S.SCAN_HEADER[S.SCAN_COL["벤치완료"]] == "벤치완료"


def test_bench_row_with_options():
    opts = [{"이름": "흰", "가격": 13900}, {"이름": "검", "가격": 12900}]
    r = S.bench_row("2026-10-02", "압축봉", PROD, opts)
    assert len(r) == 24
    assert r[:9] == ["생활/건강", "수납/정리", "압축봉", "", "압축봉", "가나상점",
                     "https://smartstore.naver.com/s/products/9", "압축봉 120cm", 2]
    assert r[9] == "흰:13,900 / 검:12,900"
    assert r[10] == "" and r[14] == "" and r[15] == ""        # 수동 칸
    assert r[11] == '=IF(INDEX(K:K,ROW())="","",INDEX(K:K,ROW())/180)'
    assert r[12] == '=IF(INDEX(L:L,ROW())="","",INDEX(L:L,ROW())*INDEX(U:U,ROW()))'
    assert r[13] == '=IF(INDEX(M:M,ROW())="","",INDEX(M:M,ROW())*30)'
    assert r[16] == '=IF(INDEX(P:P,ROW())="","",INDEX(P:P,ROW())*210)'
    assert r[17] == '=IF(INDEX(Q:Q,ROW())="","",INDEX(Q:Q,ROW())*1.4)'
    assert r[18] == '=IF(INDEX(R:R,ROW())="","",INDEX(U:U,ROW())-INDEX(R:R,ROW()))'
    assert r[19] == '=IF(OR(INDEX(L:L,ROW())="",INDEX(S:S,ROW())=""),"",INDEX(L:L,ROW())*30*INDEX(S:S,ROW()))'
    assert r[20:] == [12900, "2026-10-02", 812, ""]


def test_bench_row_options_failed_marks_manual():
    r = S.bench_row("2026-10-02", "압축봉", PROD, None)
    assert r[8] == "" and r[9] == ""
    assert r[20] == 15000          # 검색 가격으로 대체
    assert r[23] == "옵션수동"


def test_scan_row():
    cat = {"코드": "3", "경로": ["생활/건강", "수납/정리", "압축봉", ""]}
    r = S.scan_row("2026-10-02", cat, {"리뷰1000+": 4, "상위3": "a / b / c"})
    assert r == ["2026-10-02", "생활/건강", "수납/정리", "압축봉", "", "3", 4, "a / b / c", "", "", "", "", ""]
