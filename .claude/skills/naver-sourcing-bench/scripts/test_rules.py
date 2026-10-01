# -*- coding: utf-8 -*-
import pytest

import rules


def test_to_int_variants():
    assert rules.to_int("12,900원") == 12900
    assert rules.to_int(12900) == 12900
    assert rules.to_int("12900") == 12900
    assert rules.to_int(None) is None
    assert rules.to_int("") is None
    assert rules.to_int("가격문의") is None


def test_norm_url_strips_tracking():
    a = rules.norm_url("https://smartstore.naver.com/abc/products/123?NaPm=ct%3Dx&nl-au=1#rev")
    b = rules.norm_url("https://smartstore.naver.com/abc/products/123")
    assert a == b == "https://smartstore.naver.com/abc/products/123"
    assert rules.norm_url("https://m.smartstore.naver.com/abc/products/123?x=1") == b


MASTER = {"카테고리": [
    {"id": "1", "last": False, "경로정규화": "생활/건강"},
    {"id": "2", "last": False, "경로정규화": "생활/건강 > 수납/정리"},
    {"id": "3", "last": True,  "경로정규화": "생활/건강 > 수납/정리 > 압축봉"},
    {"id": "4", "last": False, "경로정규화": "생활/건강 > 수납/정리 > 선반"},
    {"id": "5", "last": True,  "경로정규화": "생활/건강 > 수납/정리 > 선반 > 벽선반"},
    {"id": "6", "last": True,  "경로정규화": "생활/건강 > 수납/정리비슷 > 엉뚱"},
]}


def test_leaf_categories_includes_3level_leaf_and_pads():
    got = rules.leaf_categories(MASTER, "생활/건강>수납/정리")
    assert got == [
        {"코드": "3", "경로": ["생활/건강", "수납/정리", "압축봉", ""]},
        {"코드": "5", "경로": ["생활/건강", "수납/정리", "선반", "벽선반"]},
    ]


def test_leaf_categories_root_itself_leaf_returns_it():
    got = rules.leaf_categories(MASTER, "생활/건강 > 수납/정리 > 선반 > 벽선반")
    assert got == [{"코드": "5", "경로": ["생활/건강", "수납/정리", "선반", "벽선반"]}]


def test_leaf_categories_unknown_root_raises():
    with pytest.raises(ValueError):
        rules.leaf_categories(MASTER, "없는>경로")


def P(rank, name, review, price, ad=False, url=None):
    return {"순위": rank, "상품명": name, "리뷰수": review, "가격": price, "광고": ad,
            "url": url or f"https://smartstore.naver.com/s/products/{rank}", "마켓명": "s",
            "카테고리": ["a", "b", "c", "d"]}


def test_scan_summary_counts_and_handles_bad_review():
    ps = [P(1, "가", 3000, "10000"), P(2, "나", "1,200", "1"), P(3, "다", None, "1"), P(4, "라", 999, "1")]
    assert rules.scan_summary(ps) == {"리뷰1000+": 2, "상위3": "가 / 나 / 다"}


def test_bench_filter_rules_and_dedup():
    ps = [
        P(1, "광고", 9999, "20000", ad=True),
        P(2, "통과", 800, "15,000원"),
        P(3, "리뷰부족", 499, "15000"),
        P(4, "싸다", 900, "9,900"),
        P(5, "가격없음", 900, None),
        P(6, "중복", 700, "12000", url="https://smartstore.naver.com/s/products/2?NaPm=1"),
        P(7, "경계", 500, "10000"),
    ]
    got = [p["상품명"] for p in rules.bench_filter(ps)]
    assert got == ["통과", "경계"]


def test_bench_filter_top_n_after_ads_removed():
    ps = [P(i, f"p{i}", 600, "20000") for i in range(1, 51)]
    assert len(rules.bench_filter(ps, top_n=40)) == 40


def test_rep_price_and_options_text():
    opts = [{"이름": "흰", "가격": 13900}, {"이름": "검", "가격": 12900}]
    assert rules.rep_price(opts, 15000) == 12900
    assert rules.rep_price([], 15000) == 15000
    assert rules.options_text(opts) == "흰:13,900 / 검:12,900"
    assert rules.options_text([]) == ""
