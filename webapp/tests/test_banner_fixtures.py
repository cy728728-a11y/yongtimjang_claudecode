#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 4 픽스처 **모양** 회귀.

이 파일은 배너 판정을 검증하지 않는다 — 판정은 04-02 이후가 만든다.
여기서 지키는 것은 하나다: **정답지가 조용히 비거나 실코드를 흘리지 않는 것.**

왜 이게 따로 필요한가:
    04-04 의 `test_라벨픽스처_미탐0` 은 `배너본문` 9건의 OCR 텍스트를 분자로 쓴다.
    그 리스트가 비면 그 테스트는 **공집합을 통과**한다 — 어휘군이 아무것도 못 잡아도
    초록으로 보인다는 뜻이다. 이 저장소가 CR-01~03 에서 가장 비싸게 배운 실패 모양이라
    분자가 비지 않았다는 사실 자체를 별도로 단언한다.
"""
import re

# 실 판매자상품코드의 모양 — 21자 영숫자 랜덤 토큰 (`qaC4Rh3eDXQcRd4Hq76P1`).
# 대소문자가 섞여 있어야 한다: 순수 소문자/숫자 문자열(`join_323b1918` 같은 것)은 코드가 아니다.
_실코드모양 = re.compile(r"(?=[A-Za-z0-9]{21}\b)(?=[^ ]*[a-z])(?=[^ ]*[A-Z])[A-Za-z0-9]{21}")

# 04-RESEARCH.md Appendix A 합계. 픽스처를 다시 떠도 이 숫자가 바뀌면 사람이 봐야 한다.
기대_배너 = 9
기대_무내용 = 21
기대_경계 = 4
기대_상품수 = 16


def test_함정_6종이_전부_있다(render_content_traps):
    """`renderContent` 파싱 함정이 6종 그대로 있는가 (04-RESEARCH §Pattern 1).

    키를 하나 지우면 04-02 의 파서 회귀가 그만큼 덜 지킨다 — 조용히.
    """
    함정 = render_content_traps["함정"]
    assert set(함정) == {
        "1_상세미조회",      # uploadDetailContents 가 None — 미조회지 0장이 아니다
        "2_공백만",          # &nbsp; 와 개행만 — 빈 리스트가 정답
        "3_순번보존",        # 같은 URL 2번 + src 없는 <img>
        "4_한장짜리",        # D-07 즉시 발동
        "5_전장404",         # 판정 불가 — "배너 0장"이 아니다
        "6_번역플래그4종",   # '0'/'1'/False/True — bool() 금지
    }
    for 이름, 항목 in 함정.items():
        assert 항목["설명"].strip(), f"{이름} 의 설명이 비었다"
        assert 항목["행"], f"{이름} 의 행이 비었다"

    # 3_순번보존 은 **중복 제거도 건너뛰기도 하지 말라**는 규약을 담는다.
    # 기대 URL 이 5칸(중복 2 + 빈칸 1 포함)이 아니면 그 규약이 사라진 것이다.
    순번보존 = 함정["3_순번보존"]["기대"]
    assert 순번보존["장수"] == 5
    assert 순번보존["URL"][0] == 순번보존["URL"][2], "중복 URL 표본이 사라졌다"
    assert 순번보존["URL"][3] == "", "src 없는 <img> 의 빈 자리가 사라졌다 — 순번이 밀린다"

    assert render_content_traps["정상"]["기대"]["장수"] == 4


def test_라벨_합계가_리서치_실측과_같다(banner_labels):
    """배너 9 · 무내용 21 · 경계 4 · 상품 16 (04-RESEARCH.md Appendix A).

    합계 필드와 상품별 리스트를 **따로 센 값이 일치**하는지도 본다 —
    둘이 어긋나면 어느 쪽이 정답인지 아무도 모른다.
    """
    합계 = banner_labels["합계"]
    assert 합계["배너"] == 기대_배너
    assert 합계["무내용"] == 기대_무내용
    assert 합계["경계"] == 기대_경계
    assert len(banner_labels["상품"]) == 기대_상품수
    assert 합계["상품"] == 기대_상품수

    assert sum(len(p["배너"]) for p in banner_labels["상품"]) == 기대_배너
    assert sum(len(p["무내용"]) for p in banner_labels["상품"]) == 기대_무내용
    assert sum(len(p["경계"]) for p in banner_labels["상품"]) == 기대_경계

    # 제품 274 는 라벨 모수 308 에서 뺀 값이다. 장수합계(312)에서 빼면 278 이 나와
    # 조용히 4장이 틀린다 — 치수를 못 얻은 4장은 판정 모수가 아니다.
    assert 합계["라벨모수"] == 기대_배너 + 기대_무내용 + 기대_경계 + 합계["제품"]
    assert 합계["제품"] == 274
    assert 합계["장수합계"] > 합계["라벨모수"], "치수 미확보분이 사라졌다"

    # 순번은 그 상품의 장수 범위 안에 있어야 한다. 밀리면 라벨이 통째로 어긋난다.
    for p in banner_labels["상품"]:
        for 키 in ("배너", "무내용", "경계"):
            for 순번 in p[키]:
                assert 0 <= 순번 < p["장수"], f"{p['코드']} 의 {키} 순번 {순번} 이 장수 밖이다"


def test_라벨픽스처에_실코드가_없다(banner_labels):
    """T-4-09: 저장소가 공개돼도 판매자상품코드가 같이 나가지 않는다.

    익명화를 사람 기억이 아니라 기계가 집행한다 (Phase 3 과 같은 규율).
    """
    코드들 = [p["코드"] for p in banner_labels["상품"]]
    코드들 += [b["코드"] for b in banner_labels["배너본문"]]
    코드들 += [b["코드"] for b in banner_labels["경계본문"]]
    for 코드 in 코드들:
        assert 코드.startswith("zz"), f"실코드가 남아 있다: {코드}"

    assert len(set(p["코드"] for p in banner_labels["상품"])) == 기대_상품수, "코드가 겹친다"

    # `코드` 칸만 보면 주석·출처 필드로 새는 경로를 놓친다. 문서 전체의 문자열을 훑어
    # **실코드 모양(21자 대소문자 혼합 랜덤 토큰)** 이 하나도 없는지 본다.
    def _문자열들(노드):
        if isinstance(노드, str):
            yield 노드
        elif isinstance(노드, dict):
            for k, v in 노드.items():
                yield k
                yield from _문자열들(v)
        elif isinstance(노드, list):
            for v in 노드:
                yield from _문자열들(v)

    for 값 in _문자열들(banner_labels):
        m = _실코드모양.search(값)
        assert not m, f"실코드로 보이는 토큰이 남아 있다: {m.group(0)!r} (in {값!r})"


def test_배너본문_9건이_비어있지_않다(banner_labels):
    """04-04 의 미탐 0 회귀가 이 텍스트를 분자로 쓴다.

    비면 그 테스트가 **공집합을 통과**한다 — 어휘군이 0장을 잡아도 초록이 된다.
    분자가 존재한다는 사실 자체를 여기서 못 박는다.
    """
    본문 = banner_labels["배너본문"]
    assert len(본문) == 기대_배너
    for 항목 in 본문:
        assert 항목["ocr_첫줄"].strip(), f"{항목['코드']}:{항목['순번']} 의 OCR 첫 줄이 비었다"
        assert 항목["왜배너로봤나"].strip()

    # 배너본문의 (코드, 순번) 이 상품별 `배너` 리스트와 정확히 같은 집합인가.
    라벨 = {(p["코드"], s) for p in banner_labels["상품"] for s in p["배너"]}
    assert {(b["코드"], b["순번"]) for b in 본문} == 라벨

    경계 = banner_labels["경계본문"]
    assert len(경계) == 기대_경계
    for 항목 in 경계:
        assert 항목["내용"].strip()
        assert 항목["물어볼것"].strip(), "경계 4장은 용팀장에게 물을 질문이 본체다"
    라벨_경계 = {(p["코드"], s) for p in banner_labels["상품"] for s in p["경계"]}
    assert {(b["코드"], b["순번"]) for b in 경계} == 라벨_경계


def test_라벨은_사람라벨이_아니라고_적혀있다(banner_labels):
    """A1: 이 정답지는 리서처의 시각 판단이다.

    게이트(BANNER-04 미탐 0%)를 이걸로 닫으면 **어휘군이 자기가 만든 답지를 채점**한다.
    경고문을 지우는 것이 그 사고의 첫 단추라 파일 안에 남아 있는지 본다.
    """
    주의 = banner_labels["주의"]
    assert "용팀장의 라벨이 아니다" in 주의
    assert "게이트 통과 근거로 쓰지 마라" in 주의
