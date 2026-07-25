#!/usr/bin/env python3
"""텍스트 정규화 1벌 — 헤더/카테고리 매칭·파일명 슬러그.

기존 4벌 중복(kwlib._nows · cat_prefilter.nows · sellerlife common.norm ·
bdz track_delivery.norm)을 여기 1벌로 통합한다. 소비자는 Step 3 에서 직전환.
"""
import re


def nows(s):
    """공백·줄바꿈 전부 제거 (헤더/카테고리 정확일치 비교용). None -> ''.

    셀러라이프 헤더 '네이버\\n해외배송비율' 같은 줄바꿈 섞인 헤더를 매칭하기 위함.
    (kwlib._nows · cat_prefilter.nows 와 동일 동작. common.norm/bdz.norm 도 실입력에선 등가.)
    """
    return re.sub(r"\s+", "", str(s)) if s is not None else ""


def cat_key(name):
    """카테고리 표기 흡수: '가구&인테리어' / '가구/인테리어' / '생활&건강2' -> '가구인테리어' / '생활건강'.

    - & 와 / 를 제거해 동일 키로 만든다
    - 20만행 export 상한 때문에 붙는 꼬리 숫자('생활&건강2')를 떼어 분할 파일을 같은 카테고리로 묶는다
    - '>' 이후 하위 카테고리는 버리고 1차만 본다
    """
    s = str(name or "").split(">")[0]
    s = s.replace("&", "").replace("/", "").replace(" ", "").strip()
    while s and s[-1].isdigit():
        s = s[:-1]
    return s


def sanitize_part(s):
    """카테고리 조각을 파일명 안전 문자열로. 슬래시·공백·특수문자 제거."""
    s = str(s).strip()
    s = s.replace("/", "").replace("\\", "")
    s = re.sub(r'[<>:"|?*]', "", s)
    s = s.replace(" ", "")
    return s
