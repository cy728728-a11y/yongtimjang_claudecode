#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""보드 투영(`webapp/board.py`) 검증 — 파일 IO 없이 순수 함수만 때린다.

`fake_result_json` 픽스처(Plan 01-01)가 주는 dict 하나로 전부 끝난다.
실제 `~/python_work/data` 를 열지 않으므로 회차 파일이 없어도 돌고, 빠르다.

픽스처에 일부러 심어 둔 함정 4종을 각각 하나씩 겨눈다:
  (a) ①·⑥ 행에 `imp`/`clk`/`ctr`/`rank`/`cost` 가 **아예 없다** (BOARD-01)
  (b) 설정에 없는 가짜 5번째 계정 `zzfake` (BOARD-02)
  (c) 같은 `adId` 가 ②와 ③에 동시에 들어 있다 (PATTERNS §C-2 / T-1-21)
  (d) 한 상품에 ①소재 2개 + ③소재 1개 (D-06 의 rule1_count)
"""
import json
from pathlib import Path

import pytest

from webapp import board

WEBAPP = Path(__file__).resolve().parents[1]

# 이 플랜이 만드는 **런타임 경로** 전부. 계정 alias 가 여기 한 글자라도 박히면
# `~/.eroom/naver-ads.json` 에 계정을 더해도 화면이 안 따라온다 (BOARD-02).
# 테스트 파일 자신은 대상이 아니다 — 픽스처를 단언하려면 alias 를 적어야 한다.
런타임_파일들 = [
    WEBAPP / "board.py",
    WEBAPP / "routes" / "board.py",
    WEBAPP / "templates" / "board.html",
    WEBAPP / "static" / "board.js",
]


def _행(rows, acct, mpid):
    """접힌 행 하나를 (계정, 상품) 으로 집어 온다. 없으면 테스트를 세운다."""
    found = [r for r in rows if r["acct"] == acct and r["mallProductId"] == mpid]
    assert len(found) == 1, f"{acct}/{mpid} 가 {len(found)}줄이다 (1줄이어야 한다)"
    return found[0]


def test_imp_없는_행도_접힌다(fake_result_json):
    """①행만 있는 상품이 예외 없이 접히고 `imp` 가 None 이다 (BOARD-01).

    `row["imp"]` 를 쓰면 실데이터 2,274행에서 KeyError 로 터진다.
    빈 값이 0 이 아니라 **None** 인 것도 의미가 있다 — 0 이면 "노출 0 이었다" 는
    판정처럼 보이는데, 실제로는 "7일 통계에 행이 없다" 라서 숫자가 존재하지 않는다.
    """
    rows = board.fold_products(fake_result_json)

    only1 = _행(rows, "cy728", "13111983902")
    assert only1["rules"] == "①"
    assert only1["imp"] is None
    assert only1["clk"] is None
    assert only1["ctr"] is None
    assert only1["cost"] is None
    assert only1["purCnt"] is None
    assert only1["purAmt"] is None

    # ⑥ 행도 같다 — imp/clk 가 없는 두 번째 규칙이다
    only6 = _행(rows, "cy7728", "12999000111")
    assert only6["rules"] == "⑥"
    assert only6["imp"] is None

    # 지표가 있는 행은 정상적으로 실린다 (빈칸 처리가 전부를 빈칸으로 만들지 않았다)
    good = _행(rows, "cy728", "12610054809")
    assert good["imp"] == 17122
    assert good["clk"] == 240
    assert good["purCnt"] == 1
    assert good["purAmt"] == 240560
    assert good["cost"] == 23721


def test_계정을_코드에_박지_않는다(fake_result_json):
    """계정 목록이 `result.json` 에서만 온다 (BOARD-02).

    픽스처의 `zzfake` 는 `~/.eroom/naver-ads.json` 에 **없는** 계정이다.
    코드나 템플릿에 alias 를 박았다면 이 계정이 목록에서도 보드에서도 사라진다.
    """
    accounts = board.account_list(fake_result_json)
    assert accounts == sorted(fake_result_json["accounts"].keys())
    assert "zzfake" in accounts
    assert len(accounts) == 5

    rows = board.fold_products(fake_result_json)
    assert {r["acct"] for r in rows} == set(accounts)
    assert _행(rows, "zzfake", "19999999999")["rules"] == "①"

    # 런타임 경로에 alias 리터럴 0건. 픽스처의 계정 이름 전부로 훑는다.
    for alias in fake_result_json["accounts"]:
        for f in 런타임_파일들:
            if not f.is_file():
                continue
            assert alias not in f.read_text(encoding="utf-8"), \
                f"{f.name} 에 계정 alias '{alias}' 가 박혀 있다 (BOARD-02)"

    # 계정이 하나도 없어도 안 깨진다 — 빈 result 는 예외가 아니라 빈 목록이다
    assert board.account_list({}) == []
    assert board.fold_products({}) == []


def test_같은_소재가_두_규칙에_있어도_노출이_두번_세지지_않는다(fake_result_json):
    """adId 를 먼저 dedupe 한다 (PATTERNS §C-2 / 위협 T-1-21).

    `report_md.py:59` 의 경고가 그대로 적용된다:
    "규칙별 행을 합산하지 않는다 — 같은 소재가 ②와 ③에 동시에 들어가 두 번 세진다".
    픽스처의 `nad-a001-02-000000502308153` 이 ②·③ 양쪽에 imp 25,850 으로 들어 있다.
    """
    rows = board.fold_products(fake_result_json)
    dup = _행(rows, "ownway1", "13149034429")

    assert dup["rules"] == "②③"          # 규칙 기호는 둘 다 실린다
    assert dup["imp"] == 25850            # 51,700 이면 두 번 셌다
    assert dup["clk"] == 60               # 120 이면 두 번 셌다
    assert dup["cost"] == 10087           # 20,174 면 두 번 셌다

    # CTR 은 합산하면 거짓말이 된다(0.23 + 0.23 = 0.46). clk/imp 로 다시 낸다.
    assert dup["ctr"] == pytest.approx(60 / 25850 * 100, abs=0.01)

    # ③·④ 에 동시에 든 소재도 같다 — 한 상품에 ①2개 + ③④ 중복 1개가 섞인 경우
    mixed = _행(rows, "ownway1", "12610054809")
    assert mixed["rules"] == "①③④"
    assert mixed["imp"] == 327            # 654 면 ③④ 를 두 번 셌다
    assert mixed["clk"] == 40
    assert mixed["cost"] == 3215


def test_대표_입찰가는_읽기만_한다(fake_result_json):
    """웹앱은 입찰가를 계산하지 않는다 (위협 T-1-07 / BID-02 의 선행 방어).

    `useGroupBidAmt=True` 면 `adAttr.bidAmt` 는 잠자는 값이고 그룹 기본가가 적용된다
    (`ads_rules.effective_bid`). 판정 단계에서 이미 그 해석을 끝내 `bid` 에 담아 놨다.
    웹앱이 `bid + 10` 같은 산술을 하면 진실이 둘이 된다.
    """
    rows = board.fold_products(fake_result_json)

    그룹입찰행 = _행(rows, "ownway1", "12610054809")
    assert 그룹입찰행["useGroupBid"] is True
    assert 그룹입찰행["groupBid"] == 70
    assert 그룹입찰행["bid"] == 70          # 80 이면 웹앱이 +10 을 했다
    assert 그룹입찰행["bid"] == 그룹입찰행["groupBid"]

    개별입찰행 = _행(rows, "pogeunae", "13222000555")
    assert 개별입찰행["useGroupBid"] is False
    assert 개별입찰행["bid"] == 90          # 개별가는 그룹가(70)로 덮이지 않는다

    # 어떤 행의 bid 도 **픽스처에 실제로 있던 값**이어야 한다.
    # 계산해서 만든 숫자가 하나라도 있으면 여기서 걸린다.
    원본_bid = set()
    for v in fake_result_json["accounts"].values():
        for 행들 in v["rules"].values():
            for r in 행들:
                원본_bid.add(r.get("bid"))
    for r in rows:
        assert r["bid"] in 원본_bid, f"{r['acct']}/{r['mallProductId']} 의 bid 가 지어낸 값이다"


def test_접기_키는_계정과_상품이다(fake_result_json):
    """접기 키는 `(계정 alias, mallProductId)` 다 (D-05).

    `mallProductId` 는 스마트스토어 상품ID라 계정 간 중복 가능성을 배제할 수 없다.
    픽스처의 `12610054809` 가 cy728(⑤)과 ownway1(①③④) 양쪽에 있다 —
    계정을 키에서 빼면 두 계정 실적이 한 줄로 뭉개진다.
    """
    rows = board.fold_products(fake_result_json)

    같은상품 = [r for r in rows if r["mallProductId"] == "12610054809"]
    assert len(같은상품) == 2
    assert {r["acct"] for r in 같은상품} == {"cy728", "ownway1"}

    # 키가 유일하다 (같은 (계정, 상품) 이 두 줄로 새지 않는다)
    키들 = [(r["acct"], r["mallProductId"]) for r in rows]
    assert len(키들) == len(set(키들))
    assert len(rows) == 9


def test_rule1_count_는_규칙1_소재수다(fake_result_json):
    """버튼이 적용될 대상은 그 상품의 **규칙① 소재만**이다 (D-06).

    ownway1/12610054809 은 ①소재 2개 + ③④소재 1개다. rule1_count 는 3이 아니라 2다.
    이 숫자가 화면의 "이 버튼이 N건에 적용됩니다" 가 된다.
    """
    rows = board.fold_products(fake_result_json)

    mixed = _행(rows, "ownway1", "12610054809")
    assert mixed["rule1_count"] == 2
    assert mixed["rule1_ads"] == ["nad-a001-02-000000495390006",
                                  "nad-a001-02-000000495390007"]

    # ① 이 없는 상품은 0 건이다 (None 이 아니라 0 — 화면에서 빈칸이 되면 안 된다)
    없음 = _행(rows, "cy728", "12610054809")
    assert 없음["rule1_count"] == 0
    assert 없음["rule1_ads"] == []

    # 픽스처 전체의 ①소재 합계 = result.json 의 ①행 수와 같다
    실제_1 = sum(len(v["rules"]["①노출0"]) for v in fake_result_json["accounts"].values())
    assert sum(r["rule1_count"] for r in rows) == 실제_1 == 6


def test_mallProductId_없어도_안_깨진다(fake_result_json):
    """`mallProductId` 결측 행(이론상)도 KeyError 없이 한 줄이 된다.

    실데이터 2,726행에는 결측이 0건이지만, 판정행 스키마상
    `referenceData.mallProductId` 는 없을 수 있다(`ads_rules.ad_info`).
    보드가 거기서 터지면 회차 하나가 통째로 안 뜬다.
    """
    깨진 = json.loads(json.dumps(fake_result_json))  # 픽스처를 오염시키지 않는다
    깨진["accounts"]["pogeunae"]["rules"]["①노출0"][0].pop("mallProductId")
    깨진["accounts"]["pogeunae"]["rules"]["①노출0"][0].pop("title")

    rows = board.fold_products(깨진)
    없는행 = [r for r in rows if r["acct"] == "pogeunae"]
    assert len(없는행) == 1
    assert 없는행[0]["mallProductId"] is None
    assert 없는행[0]["title"] == ""
    assert 없는행[0]["rule1_count"] == 1


def test_규칙목록은_실제_등장한_것만(fake_result_json):
    """규칙 필터 옵션도 `result.json` 에서 온다 — 순서는 ①②③④⑤⑥."""
    rules = board.rule_list(fake_result_json)
    assert rules == ["①노출0", "②썸네일교체", "③원인분석",
                     "④효자후보", "⑤효자확정", "⑥삭제대상"]

    # 행이 하나도 없는 규칙은 필터에 안 나온다 — 항상 빈 결과를 주는 옵션은 함정이다
    빈것 = json.loads(json.dumps(fake_result_json))
    for v in 빈것["accounts"].values():
        v["rules"]["⑥삭제대상"] = []
    assert "⑥삭제대상" not in board.rule_list(빈것)
    assert board.rule_list({}) == []


def test_보드는_ads_json_을_열지_않는다():
    """소재 원본(`accounts/*/ads.json`, 2.6MB × 2)을 열지도 보내지도 않는다 (T-1-19).

    Pitfall 8. 보드가 필요로 하는 건 판정 결과뿐인데, 원본을 읽기 시작하면
    메모리와 응답이 같이 불어나고 브라우저가 멈춘다.
    """
    src = (WEBAPP / "board.py").read_text(encoding="utf-8")
    assert "ads.json" not in src
    assert "subprocess" not in src      # 보드는 CLI 를 실행하지 않는다 (세 번째 길)
