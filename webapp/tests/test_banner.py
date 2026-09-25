#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""배너 판정 접근자(`webapp/banner.py`) 검증 — 파일 IO 없이 순수 함수만 때린다.

`render_content_traps`·`banner_labels` 픽스처(Plan 04-01)가 주는 dict 둘로 끝난다.
네트워크도 크레딧도 0 이고, 이미지를 한 장도 내려받지 않는다.

`render_content.json` 에 일부러 심어 둔 실측 함정 6종을 각각 겨눈다
(04-RESEARCH §Pattern 1 "실측 함정 표본"):
  ① `uploadDetailContents` 자체가 None (194행 중 137행) — **미조회다. 0장이 아니다**
  ② `renderContent` 가 `&nbsp;`·개행만 (18건) — 이건 진짜 0장이다. 예외가 아니다
  ③ 같은 URL 이 한 상품에 두 번 (57건 중 3건) + `src` 없는 `<img>` —
     **중복 제거도 건너뛰기도 하지 마라.** 순번이 밀리면 사람 라벨이 통째로 어긋난다
  ④ 이미지 1장짜리 상품 (1건, ri=5) — D-07 이 즉시 발동한다
  ⑤ 20장 전부 404 (1건, ri=39) — **"배너 0장"이 아니라 판정 불가**다
  ⑥ `imageTranslated` 타입 4종 (`'0'` 33 / `'1'` 19 / `False` 4 / `True` 1) —
     `state.불리언정규화` 를 쓴다. `bool()` 금지 (`bool('0')` 은 True 다)

그리고 이 페이즈 고유의 두 가지를 따로 겨눈다:
  · **게이트를 통과하기 전에는 제품 이미지가 Phase 5 입력이 될 수 없다** (BANNER-04).
    기본값이 False 라 실수로 빼먹으면 못 쓴다 — `test_게이트전에는_입력이_아니다`
  · **미검수 상품은 분모에서 빠진다** (D-03a). 안 본 것을 동의로 세면 미탐 0% 가
    거짓말이 된다 — `test_미검수_분모제외`
"""
import importlib.util
import re
import sys
from pathlib import Path

import pytest

from webapp import banner, state

WEBAPP = Path(banner.__file__).resolve().parent

# 어휘군은 **`banner_scan.py` 에 산다**(설정도 `banner.py` 도 아니다). 회귀가 그 정본을
# 직접 때려야 의미가 있어서 파일 경로로 로드한다 — 스킬 스크립트라 `import` 문으로는
# 못 가져온다(`test_banner_scan.py` 와 같은 관용구).
#
# ⚠️ 이 로드가 `.venv-web` 에서 살아 있으려면 `banner_scan.py` 의 `Vision`·`PIL` import 가
#    **함수 안쪽 지연 import** 여야 한다. 최상단에 올라가는 순간 이 파일 전체가 collect
#    단계에서 죽는다. `test_banner_scan.py` 헤더가 그 제약의 정본이다.
스캐너경로 = (Path(__file__).resolve().parents[2] / ".claude" / "skills"
          / "bulsaja-detail-page" / "scripts" / "banner_scan.py")


@pytest.fixture(scope="module")
def 스캐너():
    assert 스캐너경로.exists(), f"스캐너가 없다: {스캐너경로}"
    이전 = list(sys.path)
    try:
        규격 = importlib.util.spec_from_file_location("_banner_scan_어휘군", 스캐너경로)
        모듈 = importlib.util.module_from_spec(규격)
        규격.loader.exec_module(모듈)
        yield 모듈
    finally:
        sys.path[:] = 이전


# ── 산출물 상품 만들기 헬퍼 ─────────────────────────────────────────────────
#
# 04-RESEARCH §산출물 계약의 상품 모양을 최소로 흉내 낸다. 코드·URL 은 전부 가짜다
# (`zz*` · `zzcdn.example` — Phase 3 익명화 관례 승계).

def _장(순번, 판정=banner.제품, 사유=None):
    return {"순번": 순번, "url": f"https://zzcdn.example/zz/upload/{순번:04d}.jpg",
            "w": 790, "h": 1278, "판정": 판정, "사유": 사유, "썸네일": None}


def _상품(코드="zz01", 타오="700001", 장=None, 제품이미지=None,
          스킵사유=None, 제거율=0.0):
    """`장` 을 주면 `제품이미지` 는 판정이 `제품` 인 장에서 자동으로 만든다."""
    장 = [] if 장 is None else 장
    if 제품이미지 is None:
        제품이미지 = [{"순번": c["순번"], "url": c["url"]}
                    for c in 장 if c["판정"] == banner.제품]
    return {"판매자상품코드": 코드, "불사자코드": f"bul-{코드}",
            "타오바오상품번호": 타오, "상세상태": "중국어원본",
            "장수": len(장), "스킵사유": 스킵사유, "제거율": 제거율,
            "제품이미지": 제품이미지, "장": 장}


def _정상상품(n=4, **덮기):
    """스킵도 미판정도 없는 평범한 상품. 제품 이미지 n 장."""
    return _상품(장=[_장(i) for i in range(n)], **덮기)


# ── ① ② ③ renderContent 파싱 (BANNER-01) ──────────────────────────────────

def test_렌더콘텐츠_이미지목록():
    """`<img src>` 를 **문서 순서대로** 뽑는다 (BANNER-01).

    정규식이 아니라 `HTMLParser` 여야 하는 이유는 `banner.py` docstring 에 있다 —
    마크업이 바뀌면 정규식은 **조용히 덜 집는다**. 조용히 덜 집는 것이 이 저장소가
    CR-01~03 에서 가장 비싸게 배운 실패 모양이다.
    """
    assert banner.상세이미지목록("<div><img src='a'><img src='b'></div>") == ["a", "b"]
    # 태그 밖 텍스트는 전부 무시한다 — 실측상 `&nbsp;`/개행뿐이다.
    assert banner.상세이미지목록("머리말<img src='a'>꼬리말") == ["a"]
    # `<img>` 가 아닌 태그는 세지 않는다 (실측 950 div / 916 img).
    assert banner.상세이미지목록("<div></div><p></p>") == []


def test_None_은_예외():
    """`None`(미조회) 과 `[]`(0장) 을 **같은 값으로 접지 않는다** (BANNER-01).

    `ss_index_calls.목록꺼내기` 의 규약 그대로다. 실측 194행 중 137행이 `None` 이라,
    이걸 0장으로 흡수하면 "못 물어봤다" 가 "물어봤더니 없더라" 가 된다.
    """
    with pytest.raises(ValueError) as e1:
        banner.상세이미지목록(None)
    assert "미조회" in str(e1.value)          # 메시지가 이유를 들고 와야 가드가 안 지워진다

    with pytest.raises(ValueError):           # 모양이 아니면 예외 — 판이 바뀐 것이다
        banner.상세이미지목록(123)
    with pytest.raises(ValueError):
        banner.상세이미지목록(["<img src='a'>"])

    # 빈 문자열·공백만은 **예외가 아니다.** 이건 진짜 0장이다.
    assert banner.상세이미지목록("") == []
    assert banner.상세이미지목록("&nbsp;\n") == []


def test_렌더콘텐츠_함정(render_content_traps):
    """04-01 픽스처의 실측 함정 6종 + 정상 1종을 한 번에 훑는다.

    픽스처의 `기대` 는 test oracle 이지 CLI 산출물 필드가 아니다 (`join_traps.json` 규약).
    """
    함정 = render_content_traps["함정"]

    # ① 상세 미조회 — `uploadDetailContents` 자체가 None 이다.
    행 = 함정["1_상세미조회"]["행"]
    assert 행["uploadDetailContents"] is None
    with pytest.raises(ValueError):
        banner.상세이미지목록((행["uploadDetailContents"] or {}).get("renderContent"))

    # ② 공백만 — 0장이 정답이고 예외가 아니다.
    f2 = 함정["2_공백만"]
    assert banner.상세이미지목록(f2["행"]["uploadDetailContents"]["renderContent"]) == []
    assert f2["기대"]["장수"] == 0

    # ③ 순번 보존 — 중복 URL 은 **두 번 다 남고**, src 없는 `<img>` 는 빈 문자열로 자리를 남긴다.
    f3 = 함정["3_순번보존"]
    뽑힌것 = banner.상세이미지목록(f3["행"]["uploadDetailContents"]["renderContent"])
    assert 뽑힌것 == f3["기대"]["URL"]
    assert len(뽑힌것) == f3["기대"]["장수"] == 5
    중복 = f3["기대"]["중복순번"]
    assert 뽑힌것[중복[0]] == 뽑힌것[중복[1]], "중복 URL 을 지웠다 — 순번이 밀린다"
    for i in f3["기대"]["src없는순번"]:
        assert 뽑힌것[i] == "", "src 없는 <img> 를 건너뛰었다 — 순번이 밀린다"

    # ④ 1장짜리 — 파싱은 성공한다. D-07 발동은 `제품이미지목록` 의 몫이다.
    f4 = 함정["4_한장짜리"]
    assert len(banner.상세이미지목록(f4["행"]["uploadDetailContents"]["renderContent"])) == 1

    # ⑤ 전 장 404 — **파싱은 20장을 그대로 낸다.** "배너 0장"으로 줄어들지 않는다.
    f5 = 함정["5_전장404"]
    assert len(banner.상세이미지목록(f5["행"]["uploadDetailContents"]["renderContent"])) == 20
    assert f5["기대"]["판정"] == "미판정" and f5["기대"]["판정아님"] == "배너 0장"

    # ⑥ `imageTranslated` 타입 4종 — Phase 3 의 `불리언정규화` 를 재사용한다.
    #    여기서 `bool()` 을 쓰면 `bool('0')` 이 True 라 🔴 상품이 통째로 🟡 로 뒤집힌다.
    for 행 in 함정["6_번역플래그4종"]["행"]:
        assert state.불리언정규화(행["imageTranslated"]) is 행["기대_정규화"]

    # 정상 상품 — `&nbsp;` 가 섞여 있어도 URL 4장만 나온다.
    정상 = render_content_traps["정상"]
    assert banner.상세이미지목록(
        정상["행"]["uploadDetailContents"]["renderContent"]) == 정상["기대"]["URL"]


def test_순서유지_상한없음(render_content_traps):
    """원래 순서를 유지하고 **개수 제한이 없다** (D-06 / BANNER-03b).

    10장으로 줄이는 규칙은 Phase 5 몫이다(D-06). 여기서 잘라 버리면 그게 진짜 누락이 된다 —
    D-05 가 *"내용 누락이 크레딧 절약보다 나쁘다"* 고 못박은 그 누락이다.
    """
    # 파싱층: 중복 포함 순서 그대로.
    f3 = render_content_traps["함정"]["3_순번보존"]["행"]["uploadDetailContents"]["renderContent"]
    assert banner.상세이미지목록(f3) == render_content_traps["함정"]["3_순번보존"]["기대"]["URL"]

    # 접근자층: 실측 최대 32장보다 많은 29장 제품 이미지도 **한 장도 안 잘린다**.
    큰상품 = _정상상품(29)
    나온것 = banner.제품이미지목록(큰상품, 게이트통과=True)
    assert len(나온것) == 29
    assert 나온것 == [c["url"] for c in 큰상품["제품이미지"]], "순서가 바뀌었다"


# ── ④ ⑤ 빈 목록·미판정·스킵 — 전부 예외다 (BANNER-03b / T-4-01) ─────────────

def test_빈목록은_전량이_아니다():
    """제품 이미지 0장은 **'전량'이 아니다** (T-4-01 · `jobs._build_argv` 규율).

    `jobs.py:523-536`·`545-552` 가 세운 규율의 네 번째 적용이다 — 빈 값이 '전량'으로
    해석되는 경로는 조립부가 아니라 여기서 터뜨린다.
    """
    with pytest.raises(ValueError) as e:
        banner.제품이미지목록(_상품(장=[_장(0, banner.배너)]), 게이트통과=True)
    assert "전량" in str(e.value), "메시지가 이유를 안 들고 왔다 — 다음 사람이 가드를 지운다"

    # `제품이미지` 키 자체가 없는 것도 0장으로 흡수하지 않는다. 산출물 모양이 다른 것이다.
    상품 = _정상상품()
    del 상품["제품이미지"]
    with pytest.raises(ValueError):
        banner.제품이미지목록(상품, 게이트통과=True)


def test_미판정_흡수금지():
    """`미판정` 장이 하나라도 있으면 그 상품은 Phase 5 입력이 될 수 없다 (T-4-01).

    실측 404 는 25장(2.7%)인데 **그 중 20장이 한 상품(ri=39)에 몰려 있다.**
    흡수하면 그 상품은 "제품 이미지 0장"인데 화면에는 "배너 없음"으로 보인다 —
    Phase 3 의 CR-01~03 과 같은 병이다.
    """
    전장404 = _상품(장=[_장(i, banner.미판정, "HTTP 404 (3회 재시도)") for i in range(20)],
                 제품이미지=[])
    with pytest.raises(ValueError) as e:
        banner.제품이미지목록(전장404, 게이트통과=True)
    본문 = str(e.value)
    assert "미판정" in 본문 or "흡수" in 본문
    assert "20" in 본문, "몇 장이 미판정인지 안 적혀 있다"

    # 한 장만 미판정이어도 같다. "나머지는 멀쩡하니까" 로 넘어가지 않는다.
    섞임 = _상품(장=[_장(0), _장(1), _장(2, banner.미판정, "HTTP 404")])
    assert len(섞임["제품이미지"]) == 2      # 2장이라 D-07 하한은 통과한다
    with pytest.raises(ValueError):
        banner.제품이미지목록(섞임, 게이트통과=True)


def test_D07_잔여부족():
    """잔여 제품 이미지가 2장 미만이면 쓸 수 없다 (D-07 / BANNER-05).

    실측 1건(ri=5)이 1장짜리다. 배너를 하나도 못 빼도 D-07 이 즉시 발동한다.
    """
    with pytest.raises(ValueError) as e:
        banner.제품이미지목록(_정상상품(1), 게이트통과=True)
    assert "D-07" in str(e.value), "결정 번호가 없으면 다음 사람이 하한을 지운다"

    # 2장은 통과한다 — 하한이 '미만'이지 '이하'가 아니다.
    assert len(banner.제품이미지목록(_정상상품(2), 게이트통과=True)) == 2

    # CLI 가 이미 스킵으로 찍었으면 그 사유를 그대로 읽어서 막는다.
    스킵됨 = _상품(장=[_장(0)], 제품이미지=[], 스킵사유=banner.잔여부족)
    assert banner.스킵사유읽기(스킵됨) == banner.잔여부족
    with pytest.raises(ValueError) as e2:
        banner.제품이미지목록(스킵됨, 게이트통과=True)
    assert banner.잔여부족 in str(e2.value)


def test_D08_제거율초과():
    """제거율이 50% 를 넘은 상품은 판정이 폭주한 신호다 — 통째로 스킵 (D-08 / BANNER-05).

    **규칙을 여기서 재현하지 않는다.** 제거율 임계 판정은 `banner_scan.py` 에만 살고
    (S-1), 이 모듈은 산출물의 `스킵사유` 를 **읽기만** 한다.
    """
    폭주 = _상품(장=[_장(i, banner.배너) for i in range(9)] + [_장(9)],
               제품이미지=[{"순번": 9, "url": "https://zzcdn.example/zz/upload/0009.jpg"}],
               스킵사유=banner.제거율초과, 제거율=0.9)
    assert banner.스킵사유읽기(폭주) == banner.제거율초과

    with pytest.raises(ValueError) as e:
        banner.제품이미지목록(폭주, 게이트통과=True)
    assert banner.제거율초과 in str(e.value)

    # 스킵이 아닌 상품은 `None` 을 돌려준다 — 없는 것과 못 읽은 것을 가른다.
    assert banner.스킵사유읽기(_정상상품()) is None

    # `스킵사유` 키가 **통째로 없으면** 예외다. 산출물 모양이 다르다는 뜻이다.
    모양다름 = _정상상품()
    del 모양다름["스킵사유"]
    with pytest.raises(ValueError):
        banner.스킵사유읽기(모양다름)


def test_게이트전에는_입력이_아니다():
    """게이트를 통과하기 전에는 제품 이미지 목록이 Phase 5 입력이 될 수 없다 (BANNER-04).

    스킵도 미판정도 빈 목록도 없는 **완전히 정상인 상품**에서도 막힌다. 이게 요점이다 —
    게이트는 데이터 품질 검사가 아니라 **사람이 전수를 봤다는 사실**을 요구한다(D-03a).
    기본값이 False 라 호출부가 실수로 빼먹으면 못 쓴다. 그 값의 출처는
    `게이트집계(...)["게이트통과"]` 뿐이다 — 새 상태를 만들지 않는다.
    """
    정상 = _정상상품(4)
    assert banner.스킵사유읽기(정상) is None
    assert all(c["판정"] != banner.미판정 for c in 정상["장"])
    assert len(정상["제품이미지"]) == 4      # 스킵·미판정·빈목록 어느 쪽도 아니다

    with pytest.raises(ValueError) as e:
        banner.제품이미지목록(정상)          # 게이트통과 를 빼먹었다
    assert "게이트" in str(e.value)

    with pytest.raises(ValueError):
        banner.제품이미지목록(정상, 게이트통과=False)

    # True 를 **명시**했을 때만 URL 리스트가 나온다.
    나온것 = banner.제품이미지목록(정상, 게이트통과=True)
    assert 나온것 == [c["url"] for c in 정상["제품이미지"]]

    # 파이썬의 참같은 값으로는 열리지 않는다 — `게이트통과=1` 같은 실수를 막는다.
    with pytest.raises(ValueError):
        banner.제품이미지목록(정상, 게이트통과=1)


# ── 게이트 집계 (BANNER-04 · D-11 · D-12) ───────────────────────────────────

def _게이트입력():
    """정밀도와 누락률이 **서로 다른 값**이 되게 만든 산출물.

    기계 배너 10장 중 2장을 사람이 '제품'으로 뒤집었고(오탐 2), 기계 제품은 100장이다.
      · 정밀도 = 2 / 10       = 0.20   → 10% 를 넘는다
      · 누락률 = 2 / (2+100)  ≈ 0.0196 → 10% 이하다
    D-11 이 채택한 것은 **누락률**이므로 게이트는 통과해야 한다.
    """
    장들 = [_장(i, banner.배너) for i in range(10)]
    장들 += [_장(10 + i) for i in range(100)]
    상품 = _상품(코드="zz01", 타오="700001", 장=장들)
    라벨 = {"700001": {0: banner.제품, 1: banner.제품}}   # 2장만 뒤집었다
    return {"상품": [상품]}, 라벨, {"700001"}


def test_게이트집계_분모둘():
    """분모 둘을 **모두** 내고, 게이트 판정은 누락률로 한다 (D-11).

    기각한 대안은 정밀도(실측 15.6%)다. 같은 오류를 더 엄격하게 읽는 값이고,
    폭주 방지는 D-08 이 상품 단위로 이미 잡는다. 두 숫자를 모두 화면에 띄우되
    **게이트 판정만** 누락률로 한다 — 그게 D-11 의 본문이다.
    """
    산출물, 라벨, 검수 = _게이트입력()
    r = banner.게이트집계(산출물, 라벨, 검수)

    assert r["기계배너"] == 10
    assert r["사람제품"] == 102
    assert r["오탐"] == 2
    assert r["미탐"] == 0

    assert r["오탐율_정밀도"] == pytest.approx(2 / 10)
    assert r["오탐율_누락률"] == pytest.approx(2 / 102)
    assert r["오탐율_정밀도"] != r["오탐율_누락률"], "둘을 한 칸에 담았다 (§1(f))"

    # 정밀도는 10% 를 넘는데도 통과한다 — 게이트가 누락률로 돌고 있다는 증거다.
    assert r["오탐율_정밀도"] > 0.10
    assert r["게이트통과"] is True

    # 분모가 0 이면 `None` 이다. 0 으로 나누지도, 0.0 으로 접지도 않는다 —
    # **0건은 관측이 아니다.** 그리고 관측이 없으면 게이트는 닫혀 있어야 한다.
    빈것 = banner.게이트집계({"상품": [_상품(장=[])]}, {}, {"700001"})
    assert 빈것["오탐율_정밀도"] is None
    assert 빈것["오탐율_누락률"] is None
    assert 빈것["게이트통과"] is False


def test_미검수_분모제외():
    """확인하지 않은 상품은 분모에서 빠지고 따로 보고된다 (D-03a · Pitfall 8).

    *"클릭 안 함 = 기계 판정에 동의"* 는 **그 줄을 실제로 봤을 때만** 성립한다.
    안 본 것을 동의로 세면 미탐 0% 가 거짓말이 된다.
    """
    본것 = _상품(코드="zz01", 타오="700001", 장=[_장(0), _장(1)])
    안본것 = _상품(코드="zz02", 타오="700002",
                장=[_장(0, banner.제품), _장(1, banner.제품)])
    # 안 본 상품에는 **미탐이 될 라벨**이 달려 있다. 그래도 세면 안 된다.
    라벨 = {"700002": {0: banner.배너}}

    r = banner.게이트집계({"상품": [본것, 안본것]}, 라벨, {"700001"})

    assert r["검수상품"] == 1
    assert r["미검수상품"] == 1
    assert r["미탐"] == 0, "미검수 상품의 라벨을 분자에 넣었다"
    assert r["사람제품"] == 2, "미검수 상품의 장이 분모에 들어갔다"
    assert r["게이트통과"] is False, "미검수가 남았는데 통과했다 — 전수가 전제다(D-12)"

    # 전수를 다 보면 그제서야 열린다.
    r2 = banner.게이트집계({"상품": [본것, 안본것]}, {}, {"700001", "700002"})
    assert r2["미검수상품"] == 0
    assert r2["게이트통과"] is True

    # 미탐이 하나라도 있으면 미검수가 0 이어도 닫힌다 (미탐 0% 가 게이트의 본체다).
    r3 = banner.게이트집계({"상품": [본것, 안본것]}, 라벨, {"700001", "700002"})
    assert r3["미탐"] == 1
    assert r3["게이트통과"] is False


def test_타오바오distinct_집계():
    """집계가 타오바오상품번호 distinct 로 돈다 (성공기준 4 · `dedup.code_of` 규약).

    사본(팬아웃)이 실측 230건이다. 다 세면 라벨링 세트와 미탐율 분모가 8배까지 부푼다.
    """
    사본들 = [_상품(코드=f"zz{i:02d}", 타오="700001", 장=[_장(0), _장(1)])
            for i in range(8)]
    r = banner.게이트집계({"상품": 사본들}, {}, {"700001"})

    assert r["검수상품"] == 1, "물갈이 사본 8건이 8상품으로 세어졌다"
    assert r["미검수상품"] == 0
    assert r["사람제품"] == 2, "사본의 장이 8배로 세어졌다"

    # 번호가 없으면 불사자코드로 폴백한다 — URL 이나 판매자상품코드가 아니다.
    번호없음 = _상품(코드="zz09", 타오=None, 장=[_장(0), _장(1)])
    assert banner.상품키(번호없음) == "bul-zz09"
    assert banner.상품키(_상품(코드="zz09", 타오="")) == "bul-zz09"   # 빈 문자열도 폴백이다
    assert banner.상품키(사본들[0]) == "700001"

    # 둘 다 없으면 예외다. 빈 키로 묶으면 전 상품이 한 덩어리가 된다 — 그게 '전량' 버그다.
    with pytest.raises(ValueError):
        banner.상품키({"판매자상품코드": "zz09"})

    # 폴백 키도 집계에서 한 상품으로 선다.
    r2 = banner.게이트집계({"상품": [번호없음]}, {}, {"bul-zz09"})
    assert r2["검수상품"] == 1 and r2["미검수상품"] == 0


# ── 조인 산출물 → 상세 보유 행 (BANNER-01) ──────────────────────────────────

def test_상세보유행들(render_content_traps):
    """`행` 194개 중 상세를 **실제로 들고 있는** 행만 고른다 (실측 57행).

    `행` 키가 없거나 리스트가 아니면 예외다 — 0건과 모양 불일치를 가른다.
    """
    함정 = render_content_traps["함정"]
    문서 = {"행": [함정["1_상세미조회"]["행"],          # None — 보유가 아니다
                 함정["2_공백만"]["행"],              # 공백뿐이어도 **보유는 보유다**
                 함정["3_순번보존"]["행"]]}
    보유 = banner.상세보유행들(문서)
    assert len(보유) == 2
    assert [r["판매자상품코드"] for r in 보유] == ["zz02", "zz03"]

    assert banner.상세보유행들({"행": []}) == []      # 0건은 0건이다. 예외가 아니다

    for 나쁜것 in ({}, {"행": None}, {"행": "abc"}, [], None):
        with pytest.raises(ValueError):
            banner.상세보유행들(나쁜것)


# ── 규율 가드 (VALIDATION §성공기준 3 · Pitfall 4) ───────────────────────────

def test_사람큐_없음():
    """스킵은 **배지 + 사유 문자열**로 끝난다. 사람 판단 큐를 만들지 않는다 (D-09).

    D-07·D-08 은 "애매하면 사람에게 묻는다"가 아니라 **"애매하면 그 상품을 건너뛴다"**이다.
    Phase 3 이 지킨 원칙(`minimize-user-queues`)과 같은 선이다.

    금지 문자열을 이 파일에 글자로 남기지 않으려고 런타임에 조립한다 —
    `test_argv.py:9-14` 의 "가드가 감시하는 문자열을 테스트가 들고 있으면 예외가 생긴다".
    """
    # 판정의 정본은 `banner_scan.py` 다 — 화면(`banner.py`)만 깨끗하고 산출물에
    # 새 상태값이 들어가면 큐는 그대로 생긴다. **둘 다** 본다.
    for 대상 in (WEBAPP / "banner.py", 스캐너경로):
        소스 = 대상.read_text(encoding="utf-8")
        for 금지 in ("보" + "류", "대" + "기", "검토" + "요청"):
            assert 금지 not in 소스, (
                f"{대상.name} 에 '{금지}' 가 있다 — 사람 판단 큐다 (D-09)")

    # 스킵사유는 셋뿐이고 서로 다른 값이다 (`join.py:36-48` 의 사유코드 규율).
    assert len({banner.잔여부족, banner.제거율초과, banner.판정불가}) == 3


def test_어휘군_한중(banner_labels, 스캐너):
    """어휘군 8군이 **한국어와 중국어를 둘 다** 들고 있는지 못박는다 (BANNER-02b).

    `pytest.skip`·`xfail` 로 덮지 않는다 — 덮으면 한국어 패스 하나만 만들어도
    초록으로 보인다(Pitfall 4).

    ⚠️ **플랜의 전제를 실측으로 정정했다.** 플랜은 *"배너 9장 중 한국어 표기와 중국어
    표기가 함께 있다"* 고 적었지만, 실제 `banner_labels.json` 의 배너 9장 OCR 첫 줄에는
    **한자가 한 글자도 없다.** 전부 한국어·라틴 표기다. 한자 표본은 `경계본문` 에만 있다
    (`zz13:0` 의 `壽司`, `zz13:4` 의 `味`).

    그래서 이 테스트가 고정하는 사실은 세 가지다:
      ① 배너 9장은 전부 한글을 담는다 — 어휘군의 한국어 절반은 이 정답지로 검증된다
      ② 배너 9장에 한자가 **0건**이다 — 어휘군의 중국어 절반(`厂家直销` 등)은
         **이 정답지로 검증되지 않는다.** 04-04 는 중국어 패스가 통과했다고 주장할 근거를
         여기서 얻을 수 없다
      ③ 한자 표본은 경계 4장에 살아 있다 — 중국어 표기가 코퍼스에 실재한다는 사실 자체는
         지워지지 않는다. 어휘군의 중국어 절반을 "필요 없다"며 지우는 것도 막는다
    """
    한글 = re.compile(r"[가-힣]")
    한자 = re.compile(r"[一-鿿]")

    배너본문 = banner_labels["배너본문"]
    assert len(배너본문) == 9, "배너 분자가 9장이 아니다 — 어휘군 회귀의 분모가 흔들린다"

    for e in 배너본문:
        첫줄 = e["ocr_첫줄"]
        assert 첫줄.strip(), f"{e['코드']}:{e['순번']} 의 OCR 첫 줄이 비었다"
        assert 한글.search(첫줄), f"{e['코드']}:{e['순번']} 에 한글이 없다"

    # ② 배너 9장에 한자 0건 — 중국어 어휘군은 이 정답지 **밖**에서 증명돼야 한다.
    한자섞인배너 = [f"{e['코드']}:{e['순번']}" for e in 배너본문 if 한자.search(e["ocr_첫줄"])]
    assert 한자섞인배너 == [], (
        f"배너 9장에 한자 표본이 생겼다: {한자섞인배너} — 픽스처가 바뀌었다면 "
        "04-04 의 중국어 어휘군 회귀를 여기로 옮겨라")

    # ③ 한자 표본은 경계 4장에 실재한다.
    한자경계 = [f"{e['코드']}:{e['순번']}" for e in banner_labels["경계본문"]
              if 한자.search(e["내용"])]
    assert len(한자경계) >= 2, (
        "경계 표본에서 한자가 사라졌다 — 중국어 어휘군을 '필요 없다'며 지우는 길이 열린다")

    # ── 여기부터가 어휘군 자체의 검사다 (04-04 가 채운 뒤 살아난 부분) ──────
    #
    # 2026-09-22: 8군 → **14군**. 04-08 전수 검수에서 용팀장이 찍은 미탐 11장의 OCR 을
    # 보고 6군(구매안내·가격안내·인증검사·랭킹수상·공익기부·브랜드소개)을 더했다.
    # 숫자를 여기 박는 이유는 "군이 조용히 늘거나 줄었다"를 CI 가 말해 주기 위해서다 —
    # 어휘군이 바뀌면 산출물 숫자도 같이 바뀌고, 그건 `--lexicon-version` 을 올려야 하는 일이다.
    어휘군 = 스캐너.어휘군
    assert len(어휘군) == 14, f"어휘군이 14군이 아니다: {sorted(어휘군)}"

    # ④ 8군 **전부**가 한국어 항목과 중국어 항목을 둘 다 갖는다.
    #    한쪽만 있는 군이 생기면 그 군은 한 언어의 상세에서만 도는 반쪽 규칙이 된다.
    for 군, 항목들 in 어휘군.items():
        assert any(한글.search(x) for x in 항목들), f"{군} 에 한국어 항목이 없다"
        assert any(한자.search(x) for x in 항목들), (
            f"{군} 에 중국어 항목이 없다 — 🔴 중국어원본 상품의 배너를 통째로 "
            "놓치는 경로다(Pitfall 4)")

    # ⑤ 2글자 이하 ASCII 토큰 0개. OCR 잡음에 우연히 걸린다
    #    (개발 중 `"qr"` 이 `PANPAN physical shooting` 에 실제로 오탐).
    짧은ASCII = [(군, x) for 군, 항목들 in 어휘군.items() for x in 항목들
              if x.isascii() and len(x.strip()) <= 2]
    assert 짧은ASCII == [], (
        f"2글자 이하 ASCII 토큰이 있다: {짧은ASCII} — 최소 3글자이거나 "
        "단어 경계를 강제해라")


def test_라벨픽스처_미탐0(banner_labels, 스캐너):
    """라벨 배너 9장이 어휘군에 **전부** 걸린다 — 미탐 0 (BANNER-02b 회귀).

    ⚠️ **한계를 먼저 적는다.** 이 9장은 리서처(Claude)의 시각 판단이고, 어휘군은
    바로 그 9장의 OCR 텍스트를 보고 만들었다 — **과적합이다**(Pitfall 3).
    이건 **회귀 방지**이지 게이트 통과 근거가 아니다. 어휘군을 고치다 9장 중
    하나를 놓치면 CI 가 잡는다, 그게 전부다.
    증명은 04-08 의 전수 검수(D-12)가 하고, 게이트 세트는 리서처가 보지 않은
    상품을 반드시 포함한다.

    ⚠️ **이 9장으로 검증되는 것은 어휘군의 한국어 절반뿐이다.** 배너 9장의 OCR 첫 줄에
    한자가 0건이기 때문이다(위 `test_어휘군_한중` ②가 그 사실을 고정한다). 중국어 절반은
    `webapp/tests/cli/test_ocr_determinism.py::test_2패스가_한쪽_언어를_놓치지_않는다`
    가 **합성 이미지**로 따로 건다 — 실제 코퍼스 근거는 아직 없다.
    """
    미탐 = []
    for e in banner_labels["배너본문"]:
        if not 스캐너.어휘군걸림([e["ocr_첫줄"]]):
            미탐.append(f"{e['코드']}:{e['순번']} — {e['ocr_첫줄']!r}")
    assert 미탐 == [], (
        f"어휘군이 배너 {len(미탐)}/9 장을 놓쳤다:\n  " + "\n  ".join(미탐) +
        "\n\n⚠️ 놓친 장을 보고 키워드를 추가했다면, **같은 세트로 다시 잰 숫자는 "
        "게이트 통과 근거가 못 된다**(Pitfall 3). 게이트는 새 상품으로 재라")

    # 경계 4장에는 걸리지 않아야 한다 — 어휘군이 "글자만 있으면 배너" 로 번지는 것을 막는다.
    # (경계 4장은 용팀장이 판정할 몫이고, 기계가 미리 배너로 접으면 그 판단이 사라진다)
    오탐 = [f"{e['코드']}:{e['순번']} → {스캐너.어휘군걸림([e['내용']])}"
          for e in banner_labels["경계본문"] if 스캐너.어휘군걸림([e["내용"]])]
    assert 오탐 == [], (
        f"어휘군이 경계 표본에 걸렸다: {오탐} — 경계 판정은 용팀장 몫이다(D-12)")


def test_용팀장라벨_절이_살아있다(banner_labels):
    """픽스처에 **사람의 판단**이 들어 있고, 그것이 게이트를 닫은 채로 남아 있다.

    이 테스트가 지키는 것은 어휘군이 아니라 **기록**이다. 2026-09-22 전수 검수는
    사람 한 명이 52상품을 눈으로 훑어 만든 34건이고, 다시 만들려면 사람을 또
    앉혀야 한다. `anonymize_labels.py` 를 다시 돌려 이 절이 증발하는 사고를
    CI 가 잡는다(그쪽 `main()` 이 보존하지만, 보존이 깨졌는지는 여기서 안다).

    ⚠️ **이 절을 게이트 통과 근거로 쓰지 마라 — 게이트는 닫혀 있다.**
    `게이트집계.게이트통과 == False` 를 여기서 못 박는 이유가 그것이다.
    """
    절 = banner_labels.get("용팀장라벨")
    assert 절, ("`용팀장라벨` 절이 사라졌다 — `anonymize_labels.py` 가 덮었을 것이다. "
               "`.venv/bin/python3 webapp/tests/fixtures/anonymize_user_labels.py` 로 되살려라")

    집계 = 절["게이트집계"]
    assert 집계["게이트통과"] is False, (
        "픽스처가 게이트를 통과했다고 말한다 — 2026-09-22 실측은 불통과다. "
        "게이트는 산출물과 사람 라벨로 다시 계산해야 하지 픽스처로 선언하는 게 아니다")
    assert 절["게이트판정"] == "불통과"

    합 = 절["합계"]
    assert 합["라벨행"] == 34, f"라벨 34건이 아니다: {합['라벨행']}"
    # 분자 셋이 `게이트집계` 와 같은 수여야 한다. 어긋나면 물갈이 사본 대표 선택이 틀린 것이다.
    for 칸 in ("미탐", "오탐", "무내용뒤집기"):
        assert 합[칸] == 집계[칸], f"{칸} 이 합계({합[칸]})와 게이트집계({집계[칸]})에서 다르다"
    assert 집계["미탐"] == 11 and 집계["오탐"] == 16, "2026-09-22 실측 숫자가 바뀌었다"
    assert 집계["미검수상품"] == 8, "미검수 8상품(=스킵 8상품)이 실측이다"

    # 익명화 — 실코드가 새면 T-4-32 다. 실코드는 21자 nanoid 라 길이로 잡는다.
    코드들 = [x["코드"] for x in 절["미탐"] + 절["오탐"] + 절["경계4장"] + 절["미검수상품"]]
    샌것 = [c for c in 코드들 if not re.fullmatch(r"(zz|yy)\d{2}", c)]
    assert 샌것 == [], f"익명화 안 된 코드가 있다: {샌것}"


def test_용팀장라벨_경계4장에_사람의_답이_있다(banner_labels):
    """경계 4장은 **용팀장 기준이 정본이다**(A1 가정의 실측 답).

    기계는 넷 다 `제품` 으로 뒀고, 용팀장은 셋을 `제품`, 하나(`사용 장면 배너 —
    제품이 안 나옴`)를 `배너` 라 했다. 넷이 한 규칙으로 설명된다:
    **제품이 사진에 나오면 제품, 안 나오면 배너.**

    🔴 그 규칙은 **시각 기준**이고 판정기는 **글자 기준**(D-10)이다. 어휘군을 아무리
    넓혀도 이 기준을 직접 구현하지 못한다. 그래서 이 테스트는 "어휘군이 경계 4장을
    맞춘다"를 단언하지 않는다 — 맞출 수 없기 때문이다. 단언하는 것은 **답이 기록돼
    있다**는 사실뿐이고, 그 긴장은 `04-GATE.md` §7 이 글로 들고 있다.
    """
    경계 = banner_labels["용팀장라벨"]["경계4장"]
    assert len(경계) == 4, f"경계 4장이 아니다: {len(경계)}"
    for e in 경계:
        assert e["용팀장"] in (banner.배너, banner.제품), (
            f"{e['코드']}:{e['순번']} 에 용팀장 답이 없다 — 추측해 채우지 마라")
    배너답 = [f"{e['코드']}:{e['순번']}" for e in 경계 if e["용팀장"] == banner.배너]
    assert len(배너답) == 1, (
        f"배너로 본 경계 표본이 1장이 아니다: {배너답} — 2026-09-22 실측은 1장이다")


def test_용팀장라벨_미탐을_확장어휘군이_잡는다(banner_labels, 스캐너):
    """미탐 11장 중 **8장**을 2026-09-22 어휘군이 잡는다 — 그리고 3장은 못 잡는다.

    ⚠️ **이건 in-sample 이다.** 키워드를 바로 이 11장의 OCR 을 보고 만들었다
    (T-4-29 · Pitfall 3). 따라서 이 테스트가 증명하는 것은 **"어휘군을 고치다
    이 8장을 다시 놓치면 CI 가 말해 준다"** 뿐이고, 게이트 통과 근거가 아니다.
    진짜 측정은 다음 회차 out-of-sample 이다(`04-VALIDATION.md` §재측정 조건).

    🔴 **못 잡는 3장을 테스트에서 지우지 마라.** 못 잡는다는 사실이 빚이고,
    빚이 안 보이면 갚을 일도 없어진다:
      · OCR 이 깨진 1장 (`정못 / "#; / 품질 / 가정용 / TIEL / ASt`)
      · 점포 브랜드 슬로건 1장 — 반복되는 어휘가 없다
      · 제품 스펙 설명에 가까운 1장 — 배너인지 자체가 논쟁적이다
    셋 다 **글자로는 못 가르고 그림으로만 갈린다.** 이 빚을 푸는 길은 어휘군이
    아니라 CONTEXT §Deferred 의 비전 AI 1회 판정이고, 그건 용팀장 승인 사항이다(T-4-31).
    """
    미탐 = banner_labels["용팀장라벨"]["미탐"]
    assert len(미탐) == 11, f"미탐이 11장이 아니다: {len(미탐)}"

    잡힘, 못잡음 = [], []
    for e in 미탐:
        앞줄 = e.get("ocr_앞줄")
        assert 앞줄 or e.get("ocr_실패사유"), (
            f"{e['코드']}:{e['순번']} 에 OCR 도 실패사유도 없다 — 빈 값을 분자로 쓰면 "
            "이 테스트가 공집합을 통과한다")
        걸린군 = 스캐너.어휘군걸림([앞줄]) if 앞줄 else []
        # 픽스처에 적힌 기대와 지금 어휘군의 실제 동작이 같아야 한다.
        assert 걸린군 == e["어휘군_확장후"], (
            f"{e['코드']}:{e['순번']} — 픽스처는 {e['어휘군_확장후']} 를 기대하는데 "
            f"어휘군은 {걸린군} 를 냈다. 어휘군을 고쳤다면 "
            "`anonymize_user_labels.py` 를 다시 돌리고 `--lexicon-version` 도 올려라")
        (잡힘 if 걸린군 else 못잡음).append(f"{e['코드']}:{e['순번']}")

    assert len(잡힘) == 8, f"확장 어휘군이 잡는 미탐이 8장이 아니다: {잡힘}"
    assert sorted(못잡음) == ["zz13:4", "zz16:0", "zz16:1"], (
        f"못 잡는 미탐 목록이 바뀌었다: {못잡음} — 줄었다면 좋은 일이지만 "
        "숫자를 여기서도 고쳐라. 늘었다면 회귀다")


def test_용팀장라벨_오탐은_전부_어휘군이_낸_것이다(banner_labels):
    """오탐 16장이 **왜** 났는지 사유가 남아 있다 (D-11 §오탐 대응의 입력).

    16장 전부 `어휘군:...` 이다 — 무내용 규칙(종횡비·짧은변)이 낸 오탐은 0장이다.
    즉 **정밀도 문제는 전적으로 어휘군 문제**이고, 치수 기준을 건드릴 이유가 없다.

    가장 많이 오탐을 낸 군은 `공장직판`(7장)이다. 그런데 그 7장은 전부 사람이
    `제품` 이라 한 장이다 — **공장직판 문구가 박힌 제품 사진**이라는 뜻이고,
    이건 어휘군을 깎아서 고칠 수 있는 종류가 아니다(깎으면 진짜 배너를 놓친다).
    `04-GATE.md` §7 의 "글자 기준 vs 시각 기준" 긴장이 숫자로 나타난 자리다.
    """
    오탐 = banner_labels["용팀장라벨"]["오탐"]
    assert len(오탐) == 16, f"오탐이 16장이 아니다: {len(오탐)}"
    사유없음 = [f"{e['코드']}:{e['순번']}" for e in 오탐
             if not str(e.get("기계사유") or "").startswith("어휘군:")]
    assert 사유없음 == [], (
        f"어휘군이 아닌 사유로 난 오탐이 있다: {사유없음} — 무내용 규칙(치수)이 "
        "오탐을 내기 시작했다면 종횡비·짧은변 기준을 다시 봐야 한다")

    군별 = {}
    for e in 오탐:
        for 군 in str(e["기계사유"]).split(":", 1)[1].split(","):
            군별[군] = 군별.get(군, 0) + 1
    assert 군별.get("공장직판") == 7, (
        f"오탐 1위 군이 바뀌었다: {sorted(군별.items(), key=lambda x: -x[1])}")


def test_배너는_네트워크도_파일도_안_연다():
    """`banner.py` 는 dict 만 받는다 — 다운로더·이미지 라이브러리 접촉 0 (D-19 / T-4-02).

    이미지 다운로드·치수 프로브·OCR 은 전부 CLI 자식(`banner_scan.py`) 몫이다.
    `.venv-web` 에는 그 패키지들이 없고, 그게 이 설계의 물리적 근거다.
    금지 문자열은 런타임에 조립한다 (§9 (c) 의 주의).
    """
    소스 = (WEBAPP / "banner.py").read_text(encoding="utf-8")
    for 금지 in ("from " + "PIL", "import " + "PIL", "urllib" + ".request",
                 "import " + "requests", "httpx" + ".", "urlopen" + "(",
                 "sql" + "ite3", "sub" + "process"):
        assert 금지 not in 소스, f"banner.py 에 '{금지}' 가 있다 (D-19)"


# ── Phase 5 D-02 관문 — 상세입력목록 (DETAIL-01/02) ────────────────────────
#
# 전역 게이트 대신 "확인시각 ≥ 산출물 생성시각 + 라벨 우선 판정" 으로 연다.
# 기본값으로 열리는 길이 없어야 한다 — 키워드 인자 누락은 TypeError 다.

_생성시각 = "2026-09-25T00:14:00+09:00"
_확인후 = "2026-09-25T09:00:00+09:00"
_확인전 = "2026-09-24T23:00:00+09:00"


def _입력(상품, **덮기):
    """정상 인자 묶음에 덮어쓰기만 해서 부른다."""
    인자 = {"라벨": {}, "확인시각": _확인후, "생성시각": _생성시각, "잔여하한": 2}
    인자.update(덮기)
    return banner.상세입력목록(상품, **인자)


def test_상세입력_낡은확인은_막는다():
    with pytest.raises(ValueError) as e:
        _입력(_정상상품(4), 확인시각=_확인전)
    assert "다시 확인" in str(e.value) and "D-02" in str(e.value)


def test_상세입력_확인없음은_막는다():
    with pytest.raises(ValueError):
        _입력(_정상상품(4), 확인시각=None)


def test_상세입력_오프셋다른_시각도_바르게_비교():
    # 문자열로는 "2026-09-24T16:00:00+00:00" < "2026-09-25T00:14:00+09:00" 이지만
    # 실제 시각은 2026-09-25T01:00+09:00 — 생성 뒤다. 통과해야 한다.
    나온것 = _입력(_정상상품(4), 확인시각="2026-09-24T16:00:00+00:00")
    assert 나온것["총수"] == 4
    # 생성 1분 전(15:13Z = 00:13+09:00)은 막힌다.
    with pytest.raises(ValueError):
        _입력(_정상상품(4), 확인시각="2026-09-24T15:13:00+00:00")


def test_상세입력_스킵상품은_막는다():
    상품 = _정상상품(4, 스킵사유="D-07 잔여 1장")
    with pytest.raises(ValueError):
        _입력(상품)
    # 사람 라벨로 되살리지 않는다 (D-04)
    with pytest.raises(ValueError):
        _입력(상품, 라벨={0: banner.제품, 1: banner.제품, 2: banner.제품})


def test_상세입력_라벨우선():
    장 = [_장(0, banner.배너), _장(1), _장(2), _장(3)]
    기본 = _입력(_상품(장=장))
    assert 기본["urls"] == [장[1]["url"], 장[2]["url"], 장[3]["url"]]
    # 기계 '배너' 를 사람이 '제품' 으로 → 포함, 기계 '제품' 을 '무내용' 으로 → 제외
    나온것 = _입력(_상품(장=장), 라벨={"0": banner.제품, "2": banner.무내용})
    assert 나온것["urls"] == [장[0]["url"], 장[1]["url"], 장[3]["url"]]


def test_상세입력_미판정은_라벨로만_풀린다():
    장 = [_장(0), _장(1, banner.미판정), _장(2)]
    with pytest.raises(ValueError):
        _입력(_상품(장=장))
    나온것 = _입력(_상품(장=장), 라벨={1: banner.제품})
    assert 나온것["urls"] == [장[0]["url"], 장[1]["url"], 장[2]["url"]]


def test_상세입력_기계_제품이미지_필드는_안쓴다():
    # 기계 필드가 비어 있어도 장 판정 + 라벨이 정본이다 (D-23 ①)
    장 = [_장(0), _장(1)]
    나온것 = _입력(_상품(장=장, 제품이미지=[]))
    assert len(나온것["urls"]) == 2


def test_상세입력_중복URL제거_순서유지():
    장 = [_장(0), _장(1), _장(2), _장(3)]
    장[2]["url"] = 장[0]["url"]
    나온것 = _입력(_상품(장=장))
    assert 나온것["urls"] == [장[0]["url"], 장[1]["url"], 장[3]["url"]]
    assert 나온것["총수"] == 3 and 나온것["잘림"] == 0


def test_상세입력_10장자르기():
    상품 = _정상상품(14)
    나온것 = _입력(상품)
    assert 나온것["urls"] == [c["url"] for c in 상품["장"][:10]]
    assert 나온것["총수"] == 14 and 나온것["잘림"] == 4


def test_상세입력_하한미만():
    장 = [_장(0), _장(1)]
    장[1]["url"] = 장[0]["url"]
    with pytest.raises(ValueError):
        _입력(_상품(장=장))


def test_상세입력_키워드누락은_TypeError():
    상품 = _정상상품(4)
    정상 = {"라벨": {}, "확인시각": _확인후, "생성시각": _생성시각, "잔여하한": 2}
    for 뺄것 in 정상:
        인자 = {k: v for k, v in 정상.items() if k != 뺄것}
        with pytest.raises(TypeError):
            banner.상세입력목록(상품, **인자)


def test_확인시각읽기(tmp_path, monkeypatch):
    from webapp import banner_store, jobs, settings
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "webapp.db"))
    monkeypatch.setattr(settings, "JOB_LOG_DIR", str(tmp_path / "logs"))
    # DB 없으면 {} — 파일을 만들지 않는다
    assert banner_store.확인시각읽기("zz-run") == {}
    assert not (tmp_path / "webapp.db").exists()
    with pytest.raises(ValueError):
        banner_store.확인시각읽기("  ")
    jobs.init_db()
    banner_store.확인기록("zz-run", "700001")
    banner_store.확인기록("zz-other", "700002")
    나온것 = banner_store.확인시각읽기("zz-run")
    assert list(나온것) == ["700001"]
    from datetime import datetime
    datetime.fromisoformat(나온것["700001"])     # ISO 여야 한다
