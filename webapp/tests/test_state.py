#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""상세 상태 판정(`webapp/state.py`) 검증 — 파일 IO 없이 순수 함수만 때린다.

`join_traps` 픽스처(Plan 03-01)가 주는 dict 하나로 끝난다. 네트워크도 크레딧도 0 이다.

픽스처에 일부러 심어 둔 함정 4종을 각각 하나씩 겨눈다:
  (a) `{aiImageGenerated: true, imageTranslated: "1"}` — **판정 순서 역전 탐지** (STATE-03)
  (b) `{imageTranslated: "0"}` 이고 `aiImageGenerated` **키 자체가 없다** — 내장 캐스팅 함정 (STATE-02)
  (c) `{imageTranslated: false}` — 불리언 거짓 (STATE-02)
  (d) `{imageTranslated: 1}` — 정수 1. 문자열 '1' 과 같은 규약으로 정규화해야 한다 (STATE-02)

그리고 Pitfall 8 을 따로 겨눈다: `구매_가공완료` 태그(사람 손자국)와
`aiImageGenerated`(기계 기록)는 **같은 값이 아니다.** 한 값으로 합치면 D-08 이 요구하는
"사용자가 인지하고 직접 판단" 이 불가능해진다.
"""
import inspect

import pytest

from webapp import state

# 픽스처의 기대 판정(이모지)을 판정값 문자열로 옮기는 표.
# **이모지는 화면에서 붙인다** — 판정값 자체는 문자열이다 (interfaces).
_기대표 = {
    "⚪": state.AI가공완료,
    "🟡": state.단순번역만,
    "🔴": state.중국어원본,
}


def test_불리언정규화():
    """`'0'` `'1'` `False` `1` `None` 5종이 전부 같은 규약으로 읽힌다 (STATE-02).

    실측 타입이 제각각이다 — 문자열 `'1'`/`'0'`, 불리언 `False`, 키 부재(None).
    요구사항이 예고한 정수 `1` 도 같이 받는다.
    """
    assert state.불리언정규화("0") is False      # True 면 내장 캐스팅을 그대로 쓴 것이다
    assert state.불리언정규화("1") is True
    assert state.불리언정규화(False) is False
    assert state.불리언정규화(True) is True
    assert state.불리언정규화(1) is True
    assert state.불리언정규화(0) is False
    assert state.불리언정규화(None) is False     # 키 부재 — 실측 34건 중 26건이 이 모양이다
    assert state.불리언정규화("") is False
    assert state.불리언정규화("false") is False
    assert state.불리언정규화("False") is False  # 대소문자를 섞어 보내도 같다
    assert state.불리언정규화("true") is True


def test_문자열0은_거짓이다():
    """문자열 `'0'` 은 **거짓**이다.

    파이썬 내장 캐스팅에서 비어 있지 않은 문자열은 전부 참이라, `'0'` 을 그대로
    태우면 🔴 상품이 전부 🟡 로 뒤집힌다. 실측에서 `imageTranslated` 가
    문자열 `'0'` 으로 오는 상품이 있었다.
    """
    assert state.불리언정규화("0") is False, \
        "문자열 '0' 이 참으로 읽혔다 — 내장 캐스팅에서 '0' 은 True 다. _FALSY 를 거쳐야 한다"
    # 그리고 그 값이 판정까지 그대로 살아야 한다
    assert state.상세상태({"imageTranslated": "0"}) == state.중국어원본, \
        "문자열 '0' 이 참으로 읽혀 🔴 가 🟡 로 뒤집혔다"


def test_상세상태_3단계():
    """⚪ AI가공완료 / 🟡 단순번역만 / 🔴 중국어원본 (STATE-03)."""
    assert state.상세상태({"aiImageGenerated": True}) == state.AI가공완료
    assert state.상세상태({"imageTranslated": "1"}) == state.단순번역만
    assert state.상세상태({"imageTranslated": "0"}) == state.중국어원본

    # 정수 1 도 문자열 '1' 과 같은 규약이다
    assert state.상세상태({"imageTranslated": 1}) == state.단순번역만
    # 불리언 false 는 🔴
    assert state.상세상태({"imageTranslated": False}) == state.중국어원본

    # 세 값은 서로 다르다 — 한 칸에 뭉개면 화면이 구분을 못 한다
    assert len({state.AI가공완료, state.단순번역만, state.중국어원본}) == 3


def test_AI생성이_번역보다_우선():
    """`aiImageGenerated` 를 **먼저** 본다 (Pitfall 4 / 크레딧 이중지불).

    AI 생성분에도 `imageTranslated` 가 '1' 로 남아 있다 (실측 8건 중 5건).
    번역 여부를 먼저 보면 ⚪가 🟡로 내려앉고, Phase 5 가 이미 가공된 상품에
    크레딧을 다시 태운다. 되돌릴 수 없다.
    """
    dc = {"aiImageGenerated": True, "imageTranslated": "1"}
    assert state.상세상태(dc) == state.AI가공완료   # "단순번역만" 이면 판정 순서가 뒤집혔다

    # 번역이 '0' 이어도 AI 가 찍혀 있으면 ⚪ 다
    assert state.상세상태({"aiImageGenerated": True, "imageTranslated": "0"}) == state.AI가공완료
    # 반대로 AI 가 거짓이면 번역 값이 판정을 정한다
    assert state.상세상태({"aiImageGenerated": False, "imageTranslated": "1"}) == state.단순번역만


def test_키가_없어도_안터진다():
    """`aiImageGenerated` 키가 **통째로 없다** — 실측 34건 중 26건이 그 상태다 (STATE-03).

    `dc["aiImageGenerated"]` 를 쓰면 회차 하나가 통째로 안 뜬다. `.get()` 만 쓴다.
    """
    assert state.상세상태({}) == state.중국어원본
    assert state.상세상태(None) == state.중국어원본
    assert state.상세상태({"renderContent": "<div>...</div>"}) == state.중국어원본
    # dict 가 아닌 것이 와도 예외가 아니다 (board.py:129-130 관용구)
    assert state.상세상태([]) == state.중국어원본
    assert state.상세상태("") == state.중국어원본


def test_불리언순서가_int보다_먼저다():
    """정규화 결과가 **진짜 `bool` 객체**다 — `1`/`0` 이 새지 않는다.

    파이썬에서 `bool` 은 `int` 의 하위타입이라, 숫자 분기를 앞에 두면 입력값이
    그대로 흘러나가기 쉽다. 그러면 화면에서 `예/아니오` 대신 `1/0` 이 찍힌다
    (`board.js:68-72` 가 같은 함정을 JS 쪽에 적어 뒀다).

    `is True` / `is False` 는 `==` 과 다르다 — `1 == True` 는 참이지만 `1 is True` 는 거짓이다.
    그래서 이 단언은 "입력을 그대로 돌려주는" 구현을 잡아낸다.
    """
    for v in (True, 1, 2, 1.5, "1", "yes"):
        결과 = state.불리언정규화(v)
        assert 결과 is True, f"{v!r} → {결과!r} — 입력이 그대로 새어 나왔다 (bool 이 아니다)"
        assert type(결과) is bool
    for v in (False, 0, 0.0, "0", "", None, "false"):
        결과 = state.불리언정규화(v)
        assert 결과 is False, f"{v!r} → {결과!r} — 입력이 그대로 새어 나왔다 (bool 이 아니다)"
        assert type(결과) is bool


def test_기작업은_태그와_기계기록_둘다본다():
    """기작업 = `done_tags` 태그(사람 손자국) **OR** AI 가공 완료(기계 기록) — STATE-04/05.

    외부 반영 경로는 `aiImageGenerated` 를 찍지 않는다 (양성대조 8 / 음성대조 26 실측).
    그래서 태그만 보면 불사자 AI 생성분을 놓치고, 기계기록만 보면 외부 경로 기작업분을
    놓쳐 **크레딧을 다시 태운다.** 둘 다 봐야 한다.
    """
    태그들 = ["구매_가공완료"]

    # ① 태그만 있고 AI 흔적은 없다 (외부 경로 기작업 — 실측 6건 전부 이 모양)
    assert state.기작업여부("구매_가공완료", {"imageTranslated": "1"}, 태그들) is True
    # ② AI 흔적만 있고 태그는 없다 (불사자 AI 생성분)
    assert state.기작업여부(None, {"aiImageGenerated": True}, 태그들) is True
    # ③ 둘 다 없다
    assert state.기작업여부(None, {"imageTranslated": "1"}, 태그들) is False
    assert state.기작업여부("구매", {"imageTranslated": "0"}, 태그들) is False
    # ④ 태그 목록이 비면 기계기록만 본다 (설정이 비었다고 전량 기작업이 되면 안 된다)
    assert state.기작업여부("구매_가공완료", {}, []) is False
    assert state.기작업여부("구매_가공완료", {}, None) is False
    # ⑤ dc 가 None 이어도 태그는 산다
    assert state.기작업여부("구매_가공완료", None, 태그들) is True


def test_스킵은_목표장수를_모른다():
    """`기작업여부` 가 장수/`pages` 를 **인자로 받지 않는다** (STATE-05 / D-10).

    현행 CLI 는 `prev["pages"] >= min(목표장수, 수집이미지수)` 로 스킵을 판정한다.
    그러면 8장짜리 기작업 상품이 이번에 이미지 10장을 모았을 때 재접수돼 크레딧을
    다시 낸다. 기작업 스킵은 **목표 장수와 무관한 절대 조건**이다.
    """
    s = inspect.signature(state.기작업여부)
    assert "pages" not in s.parameters, s
    assert "장수" not in s.parameters, s
    assert "장수" not in str(s), s
    assert list(s.parameters) == ["그룹태그", "dc", "done_tags"], s


def test_상태와_태그를_한값으로_합치지_않는다(join_traps):
    """`구매_가공완료` 태그가 붙은 상품의 `상세상태` 는 ⚪가 **아니다** (Pitfall 8).

    실측 6건 전부 `aiImageGenerated` 키 부재다. 태그는 용팀장의 손자국이고
    상태는 불사자의 기계 기록이라 **같은 걸 뜻하지 않는다.**
    둘을 한 값으로 합치면 D-08 의 "회색으로 보이되 직접 선택 가능" 이 불가능해진다.
    """
    태그행 = [r for r in join_traps["행"] if r.get("그룹태그") == "구매_가공완료"]
    assert len(태그행) == 1, f"픽스처의 기작업 태그 행이 {len(태그행)}개다 (1개여야 한다)"
    행 = 태그행[0]
    dc = 행["uploadDetailContents"]

    상태 = state.상세상태(dc)
    assert 상태 == state.단순번역만, f"{상태} — 태그를 상태 판정에 섞었다 (Pitfall 8)"
    assert 상태 != state.AI가공완료
    # 그런데 기작업으로는 잡힌다 — 두 값이 **별개**라는 증거다
    assert state.기작업여부(행["그룹태그"], dc, ["구매_가공완료"]) is True


@pytest.mark.parametrize("이름", ["AI가공완료", "단순번역만", "중국어원본"])
def test_판정값은_문자열_상수다(이름):
    """판정값은 이모지가 아니라 문자열이다 — 이모지는 화면에서 붙인다 (interfaces)."""
    값 = getattr(state, 이름)
    assert isinstance(값, str) and 값 == 이름


def test_픽스처_함정_전수(join_traps):
    """`join_traps.json` 의 각 행을 돌려 기대 판정이 그대로 나온다 (함정과 1:1).

    픽스처의 `기대_상태` 는 **기대 판정(test oracle)** 이고 CLI 산출물 필드가 아니다.
    """
    본_행 = 0
    for 행 in join_traps["행"]:
        기대 = 행.get("기대_상태")
        if 기대 is None:
            continue           # 미해소 행은 상태 판정 대상이 아니다 (조인이 먼저다)
        본_행 += 1
        얻음 = state.상세상태(행["uploadDetailContents"])
        assert 얻음 == _기대표[기대], (
            f"{행['mallProductId']} 기대 {기대}({_기대표[기대]}) 인데 {얻음} 이 나왔다. "
            f"함정: {행.get('_함정')}"
        )
    assert 본_행 == 4, f"상태 판정 대상 행이 {본_행}개다 (함정 4종이어야 한다)"
