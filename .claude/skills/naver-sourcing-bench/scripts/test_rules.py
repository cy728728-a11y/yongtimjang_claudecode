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
        P(8, "카탈로그", 5000, "20000", url="https://search.shopping.naver.com/catalog/123"),
        dict(P(9, "한샘", 5000, "20000"), 마켓명="한샘몰"),
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


def test_norm_url_keeps_product_id_query_on_other_malls():
    a = rules.norm_url("https://www.daisomall.co.kr/pd/pdr/SCR_PDR_0001?pdNo=1030782&utm_source=naver")
    b = rules.norm_url("https://www.daisomall.co.kr/pd/pdr/SCR_PDR_0001?pdNo=1078943")
    assert a != b
    assert a == "https://www.daisomall.co.kr/pd/pdr/SCR_PDR_0001?pdNo=1030782"
    assert rules.norm_url("https://search.shopping.naver.com/catalog/123?query=x") == \
        "https://search.shopping.naver.com/catalog/123"


# ---- 옵션 파싱 (2026-10-02) ----

def test_parse_option_item_number_and_extra():
    r = rules.parse_option_item("5. 찝게형 바지걸이 - 화이트 (+200원)")
    assert r == {"이름": "찝게형 바지걸이 - 화이트", "추가금": 200, "품절": False}


def test_parse_option_item_plus_without_paren_is_not_extra():
    assert rules.parse_option_item("블랙 10+10개") == {"이름": "블랙 10+10개", "추가금": 0, "품절": False}


def test_parse_option_item_comma_minus_soldout():
    assert rules.parse_option_item("대형 (+1,200원)")["추가금"] == 1200
    assert rules.parse_option_item("소형 (-500원)")["추가금"] == -500
    r = rules.parse_option_item("레드 (품절)")
    assert r["품절"] is True and r["이름"] == "레드"


def test_parse_option_item_strips_formula_lead():
    # T-mbo-01: USER_ENTERED 로 들어가므로 수식 시작 문자를 뗀다
    assert rules.parse_option_item("=HYPERLINK(1)")["이름"] == "HYPERLINK(1)"
    assert rules.parse_option_item("@화이트")["이름"] == "화이트"


def test_parse_base_price():
    assert rules.parse_base_price("상품 가격\n할인가\n12,900원\n정가 18,000원") == 12900
    assert rules.parse_base_price("가격 정보 없음") is None
    assert rules.parse_base_price(None) is None


def test_is_catalog():
    assert rules.is_catalog("https://search.shopping.naver.com/catalog/123") is True
    assert rules.is_catalog("https://smartstore.naver.com/s/products/1") is False


def _probe(**kw):
    d = {"kind": "options", "key": "u", "상태": "성공", "priceText": "상품 가격\n12,900원", "combos": []}
    d.update(kw)
    return d


def test_build_options_single_item():
    r = rules.build_options(_probe(상태="단품"), 15000)
    assert r == {"판정": "성공", "options": [{"이름": "단품", "가격": 12900}]}
    assert rules.options_text(r["options"]) == "단품:12,900" and len(r["options"]) == 1


def test_build_options_multi_axis_join_and_sum():
    r = rules.build_options(_probe(combos=[["화이트", "10개 (+3,000원)"], ["블랙 (+500원)", "20개 (+1,000원)"]]), None)
    assert r["판정"] == "성공"
    assert r["options"] == [{"이름": "화이트-10개", "가격": 15900}, {"이름": "블랙-20개", "가격": 14400}]


def test_build_options_soldout_included_with_mark():
    r = rules.build_options(_probe(combos=[["레드 (품절)"], ["블루"]]), None)
    assert [o["이름"] for o in r["options"]] == ["레드(품절)", "블루"]


def test_build_options_over_limit():
    assert rules.build_options(_probe(상태="옵션초과"), 1) == {"판정": "옵션초과", "options": None}
    many = [[f"o{i}"] for i in range(16)]
    assert rules.build_options(_probe(combos=many), 1)["판정"] == "옵션초과"
    assert rules.build_options(_probe(combos=many[:15]), 1)["판정"] == "성공"     # 정확히 15 는 통과


def test_build_options_fallback_price():
    r = rules.build_options(_probe(priceText="", combos=[["a"]]), 11000)
    assert r["options"] == [{"이름": "a", "가격": 11000}]
    assert rules.build_options(_probe(priceText="", combos=[["a"]]), None)["판정"] == "실패"


def test_build_options_failures():
    assert rules.build_options(None, 1) == {"판정": "실패", "options": None}
    assert rules.build_options(_probe(상태="읽기실패"), 1)["판정"] == "실패"
    assert rules.build_options(_probe(combos=[]), 1)["판정"] == "실패"
    assert rules.build_options(_probe(combos="garbage"), 1)["판정"] == "실패"


# ---- 스토어 확장 · 원산지 (quick-261008-0qx) ----

def test_store_base():
    assert rules.store_base("https://smartstore.naver.com/piachang/products/123?NaPm=x") == \
        "https://smartstore.naver.com/piachang"
    assert rules.store_base("https://brand.naver.com/jinsimgamsung/products/9") == "https://brand.naver.com/jinsimgamsung"
    assert rules.store_base("https://m.smartstore.naver.com/piachang/products/1") == "https://smartstore.naver.com/piachang"
    assert rules.store_base("https://smartstore.naver.com/main/products/123") is None
    assert rules.store_base("https://www.coupang.com/vp/products/1") is None
    assert rules.store_base("") is None
    assert rules.store_base(None) is None


def test_product_key():
    a = rules.product_key("https://smartstore.naver.com/main/products/123")
    assert a == rules.product_key("https://smartstore.naver.com/piachang/products/123") == \
        rules.product_key("https://m.smartstore.naver.com/x/products/123?a=1") == "nv:123"
    assert rules.product_key("https://brand.naver.com/jin/products/77") == "nv:77"
    assert rules.product_key("https://www.daisomall.co.kr/pd?pdNo=1&utm_source=x") == \
        rules.norm_url("https://www.daisomall.co.kr/pd?pdNo=1&utm_source=x")
    assert rules.product_key("https://search.shopping.naver.com/catalog/555") == \
        "https://search.shopping.naver.com/catalog/555"


SB = "https://smartstore.naver.com/piachang"


def _sitem(i, review=800, price=12900, **kw):
    d = {"id": i, "name": f"n{i}", "price": price, "review": review,
         "category": "생활/건강>수납/정리용품>옷걸이>바지걸이", "display": "ON"}
    d.update(kw)
    return d


def test_store_products_basic():
    r = rules.store_products({"base": SB, "items": [_sitem(5, name="n")]}, mall="스토리행거")
    assert r == [{"순위": 1, "상품명": "n", "url": SB + "/products/5", "마켓명": "스토리행거", "가격": 12900,
                  "리뷰수": 800, "광고": False, "카테고리": ["생활/건강", "수납/정리용품", "옷걸이", "바지걸이"]}]


def test_store_products_padding_saleprice_display_origin():
    items = [_sitem(1, price=None, salePrice=15000, category="A>B"),
             _sitem(2, display="SUSPENSION"),
             _sitem(3, origin="중국")]
    r = rules.store_products({"base": SB, "items": items}, mall="m")
    assert [p["url"] for p in r] == [SB + "/products/1", SB + "/products/3"]
    assert r[0]["가격"] == 15000 and r[0]["카테고리"] == ["A", "B", "", ""]
    assert "원산지" not in r[0] and r[1]["원산지"] == "중국"
    assert [p["순위"] for p in r] == [1, 2]


def test_store_products_bad_input():
    assert rules.store_products(None, "m") == []
    assert rules.store_products({"base": SB, "items": "x"}, "m") == []
    assert rules.store_products({"items": [_sitem(1)]}, "m") == []        # base 없음


def _sp(i, review=800, price=12900, mall="m", url=None, **kw):
    d = {"순위": i, "상품명": f"n{i}", "url": url or f"{SB}/products/{i}", "마켓명": mall, "가격": price,
         "리뷰수": review, "광고": False, "카테고리": ["a", "b", "c", "d"]}
    d.update(kw)
    return d


def test_store_filter():
    ps = [_sp(1, review=3000), _sp(2, review=2000, price=9000), _sp(3, review=1500, price=None),
          _sp(4, review=1200, mall="한샘몰"), _sp(5, review=1100, url="https://search.shopping.naver.com/catalog/9"),
          _sp(6, review=1000), _sp(7, review=900), _sp(8, review=499),
          _sp(9, review=800, url="https://m.smartstore.naver.com/x/products/7"),
          _sp(10, review=700, 원산지="국산"), _sp(11, review=650, 원산지="중국"), _sp(12, review=600, 원산지="")]
    out = rules.store_filter(ps, {"nv:6"})
    assert [p["순위"] for p in out] == [1, 7, 11, 12]


def test_origin_verdict():
    for t in ("중국", "중국산", "China", "Made in CHINA", "CN", "수입산(중국)", "수입산 / 중국"):
        assert rules.origin_verdict(t) == "중국", t
    for t in ("국산", "대한민국", "베트남", "한국", "CNC가공"):
        assert rules.origin_verdict(t) == "제외", t
    for t in ("", None, "   ", "상세설명에 표시", "상품상세 참조", "기타", "상세설명참조"):
        assert rules.origin_verdict(t) == "미확인", t
