#!/usr/bin/env python3
"""썸네일 검수 페이지 — 이미지가 승인 대상이라 텍스트 검수표가 안 통한다(2026-07-28 실전 교훈).

`render()` 는 순수 함수(문자열만 만든다, 파일 IO 없음) — 그래서 테스트가 된다.
`build()` 만 파일을 쓴다. 상품마다 [기존대표 | 생성본 | 후보] 를 나란히 놓고
재작업사유·크레딧을 병기한다. 이미지는 전부 불사자/타오바오 공개 https 주소라
로컬 다운로드 없이 그대로 임베드한다(업로드 불필요 — 이게 이 방식의 이유다).

CSS·이미지 태그·페이지 셸은 상세 검수 페이지와 공유한다(eroomlib.review_page) —
본문 구조(가로 3열 비교)만 이 스킬 고유.

판정(사용가능/주의/제외)은 이 페이지에서 **입력받지 않는다** — 이룸님이 보고 결정한 것을
decisions.json 에 별도로 적어 apply --commit 이 읽는다. 이 페이지는 순수 표시용이다.
"""
import html
import os
import sys

_d = os.path.dirname(os.path.abspath(__file__))
while _d and _d != os.path.dirname(_d):
    _lib = os.path.join(_d, "lib")
    if os.path.isdir(os.path.join(_lib, "eroomlib")):
        if _lib not in sys.path:
            sys.path.insert(0, _lib)
        break
    _d = os.path.dirname(_d)

from eroomlib import review_page as P  # noqa: E402


def render(generated, title="썸네일 검수"):
    """{productId: {상품명, 기존대표, 생성본, 후보, 재작업사유, 크레딧, 오류,
                    대표옵션명, 대표옵션이미지}} → HTML 문자열.

    **대표옵션을 생성본 바로 왼쪽에 놓는다** — 이룸님이 승인할 때 판단해야 하는 것이
    "생성본이 대표옵션과 같은 물건인가"이기 때문이다(2026-07-30). 네이버는 추가금 0원인
    대표옵션을 상품명으로 쓰라고 요구하므로 썸네일도 그 옵션이어야 한다.
    """
    parts = []
    for pid, g in generated.items():
        parts.append('<div class="card">')
        parts.append(f"<h2>{html.escape(g.get('상품명', ''))}</h2>")
        parts.append(f"<div class='pid'>{html.escape(pid)}</div>")
        if g.get("대표옵션명"):
            parts.append(f"<div class='meta'>대표옵션: "
                         f"{html.escape(g['대표옵션명'])}</div>")
        if g.get("재작업사유"):
            parts.append(f"<div class='reason'>재작업 사유: {html.escape(g['재작업사유'])}</div>")
        if "오류" in g:
            parts.append(f"<div class='error'>생성 실패: {html.escape(g['오류'])}</div>")
            parts.append("</div>")
            continue
        parts.append('<div class="row">')
        parts.append(P.img_tag(g.get("기존대표"), "기존 대표"))
        # 대표옵션 이미지가 있으면 생성본 **바로 앞**에 — 나란히 놓아야 대조가 된다
        if g.get("대표옵션이미지"):
            parts.append(P.img_tag(g.get("대표옵션이미지"),
                                   f"대표옵션 = 기준 ({g.get('대표옵션명') or '이름없음'})"))
        parts.append(P.img_tag(g.get("생성본"), "생성본(미승인)", cls="gen"))
        for i, u in enumerate(g.get("후보") or [], 1):
            parts.append(P.img_tag(u, f"원본 후보 {i}"))
        parts.append("</div>")
        if g.get("크레딧"):
            parts.append(f"<div class='meta'>사용 크레딧: {g['크레딧']}</div>")
        parts.append("</div>")
    return P.shell(title, parts, count_label=f"{len(generated)}건")


def build(generated, out_path, title="썸네일 검수"):
    """render() 결과를 파일로 쓰고 경로를 반환한다."""
    return P.write(render(generated, title=title), out_path)
