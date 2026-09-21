#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OCR 결정성 — **`.venv`(CLI venv)로 도는 유일한 테스트** (BANNER-02b · D-10 · T-4-13).

실행:

    .venv/bin/python3 -m pytest webapp/tests/cli/test_ocr_determinism.py

`.venv-web` 으로 돌리면 `Vision`·`PIL` 이 없어서 **collect 단계에서 죽는다.** 그게
설계다(D-19). 그래서 `webapp/pytest.ini` 의 `norecursedirs` 가 이 디렉터리를 기본
수집에서 뺀다.

⚠️ **미설치를 skip 으로 덮는 pytest 헬퍼를 쓰지 마라.** 덮으면 미설치가 초록으로 보이고,
"OCR 이 안 돌았다" 가 "통과" 로 기록된다. `conftest.py` 가 Wave 1 라우트 부재에 대해
세운 규율과 같은 선이다 — **미설치는 실패여야 한다.**

(그 헬퍼 이름을 이 파일에 글자로 남기지 않는다. 04-04 플랜의 acceptance 가 이 파일에서
 그 낱말이 0줄인지를 grep 으로 확인한다 — 가드가 찾는 문자열을 감시 대상이 들고 있으면
 "주석에는 있어도 된다" 는 예외가 생기고, 그 예외가 언젠가 진짜 호출로 자란다.
 `test_argv.py:205-207` 이 이미 세운 규율이다.)

이 파일이 지키는 것은 하나다: **판정이 회차마다 흔들리지 않는다**(D-02 의 걱정).
흔들릴 수 있는 경로가 둘뿐이고 둘 다 여기서 막는다.
  ① OS 가 Vision 기본 리비전을 올린다 → `setRevision_` 이 소스에 박혀 있는지 본다
  ② 같은 이미지가 실행마다 다르게 읽힌다 → 3회 반복 출력이 완전히 같은지 본다

네트워크 0 · 크레딧 0 · 토큰 0. 이미지는 테스트가 `tmp_path` 에 직접 그린다.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

저장소루트 = Path(__file__).resolve().parents[3]
스캐너경로 = (저장소루트 / ".claude" / "skills" / "bulsaja-detail-page"
          / "scripts" / "banner_scan.py")

# 한국어·중국어를 **각각 제대로 그리는** 폰트가 따로 필요하다. 한글 폰트 하나로
# 한자를 그리면 두부(`冈`)가 나와서 2패스 검증이 통째로 헛돈다 — 개발 중 실제로
# `厂家直销` 가 `冈家直` 으로 읽혔다.
한글폰트 = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
한자폰트 = "/System/Library/Fonts/Supplemental/Songti.ttc"

한국어본문 = "공장 직판 품질 보증"
중국어본문 = "厂家直销 品质保证"


def _스캐너():
    """`banner_scan.py` 를 파일 경로로 로드한다 (`test_banner_scan.py` 와 같은 관용구).

    스킬 스크립트라 패키지가 아니다 — `import` 문으로는 못 가져온다. 새 패키지를
    만들지 않는 것이 저장소 관례다.
    """
    assert 스캐너경로.exists(), f"스캐너가 없다: {스캐너경로}"
    규격 = importlib.util.spec_from_file_location("_banner_scan_ocr_test", 스캐너경로)
    모듈 = importlib.util.module_from_spec(규격)
    규격.loader.exec_module(모듈)
    return 모듈


@pytest.fixture(scope="module")
def 스캐너():
    이전 = list(sys.path)
    try:
        yield _스캐너()
    finally:
        sys.path[:] = 이전


@pytest.fixture(scope="module")
def 한중이미지(tmp_path_factory):
    """한국어 줄 + 중국어 줄이 같이 있는 PNG 1장 → 경로.

    **실제 상세 이미지를 쓰지 않는다.** 코퍼스 이미지는 271MB 캐시에 있고 저장소에
    들어오지 않는다. 여기서 재는 것은 "OCR 이 같은 입력에 같은 답을 내는가" 라
    합성 이미지로 충분하다 — 오히려 정답을 우리가 알고 있어서 더 낫다.
    """
    from PIL import Image, ImageDraw, ImageFont

    경로 = tmp_path_factory.mktemp("ocr") / "한중.png"
    im = Image.new("RGB", (900, 300), "white")
    그리개 = ImageDraw.Draw(im)
    그리개.text((40, 40), 한국어본문,
              font=ImageFont.truetype(한글폰트, 64), fill="black")
    그리개.text((40, 160), 중국어본문,
              font=ImageFont.truetype(한자폰트, 64), fill="black")
    im.save(경로)
    return str(경로)


def test_Vision_이_있고_리비전3을_지원한다():
    """미설치는 **실패**다. skip 으로 덮지 않는다.

    ⚠️ `supportedRevisions()` 는 **클래스 메서드**다(04-01 실측).
    `alloc().init().supportedRevisions()` 는 `AttributeError` 다 — 인스턴스에는 없다.
    """
    import Vision

    지원 = Vision.VNRecognizeTextRequest.supportedRevisions()
    assert 지원.containsIndex_(3), (
        f"Vision 이 revision 3 을 지원하지 않는다: {지원} — "
        "OS 가 바뀌었다. 산출물 `판정규칙.vision_revision` 과 함께 재검토해라")


def test_같은_이미지_3회_출력이_동일하다(스캐너, 한중이미지):
    """3회 반복 출력 완전 일치 (실측 5/5 동일).

    이게 D-02 의 "회차마다 흔들린다" 를 직접 재는 자리다. 흔들리면 사람이 어제 검수한
    결과가 오늘 다른 장을 가리키고, 미탐 0% 라는 숫자 자체가 의미를 잃는다.

    **비어 있지 않은지도 같이 본다.** 3회 전부 `[]` 여도 "동일"은 동일이다 —
    그 통과는 아무것도 증명하지 않는다.
    """
    결과들 = [스캐너.ocr_2패스(한중이미지, revision=3) for _ in range(3)]

    assert 결과들[0], "OCR 이 한 줄도 못 읽었다 — 동일성만 보면 빈 결과도 '통과'다"
    assert 결과들[0] == 결과들[1] == 결과들[2], (
        f"3회 반복 출력이 갈렸다:\n{결과들[0]}\n{결과들[1]}\n{결과들[2]}")


def test_2패스가_한쪽_언어를_놓치지_않는다(스캐너, 한중이미지):
    """한국어 패스와 중국어 패스가 **각각 자기 몫**을 읽는다 (Pitfall 4).

    한 패스로 끝내면 반대쪽 언어를 통째로 놓치는데, 그 미탐은 화면에 "배너 0장" 으로
    보여서 눈에 띄지도 않는다. 실측:
      `ko-KR` 만  → `加深35cm` 을 `t0&⅞35cm` 로 읽는다
      `zh-Hans` 만 → `3층 대형 69` 를 `3 ［H 69` 로 읽는다
    """
    한국어패스 = 스캐너.ocr(한중이미지, ("ko-KR", "en-US"), True, revision=3)
    중국어패스 = 스캐너.ocr(한중이미지, ("zh-Hans", "en-US"), False, revision=3)

    assert any(한국어본문 in 줄 for 줄 in 한국어패스), (
        f"한국어 패스가 한국어를 못 읽었다: {한국어패스}")
    assert any(중국어본문 in 줄 for 줄 in 중국어패스), (
        f"중국어 패스가 중국어를 못 읽었다: {중국어패스}")

    # 이게 2패스가 필요한 이유의 실물이다 — 한 패스는 반대쪽을 못 본다.
    assert not any(중국어본문 in 줄 for 줄 in 한국어패스), (
        "한국어 패스가 중국어까지 다 읽었다 — 사실이라면 2패스 근거를 재확인해라")

    # 어휘군은 **양쪽 다** 걸어야 한다. 중국어 절반이 실제로 동작한다는 근거가 여기다
    # (라벨 픽스처 배너 9장에는 한자가 0건이라 그 정답지로는 증명되지 않는다).
    assert "공장직판" in 스캐너.어휘군걸림(한국어패스)
    assert "공장직판" in 스캐너.어휘군걸림(중국어패스)


def test_리비전이_소스에_박혀_있다():
    """`setRevision_` 이 소스에 실재하는지 **글자로** 확인한다 (T-4-13).

    위 두 테스트는 "오늘의 동작" 을 재고, 이건 "내일의 동작" 을 지킨다. 기본 리비전이
    이미 3이라 `setRevision_` 을 지워도 오늘은 같은 결과가 나온다 — **그게 D-10 이
    경고한 바로 그 상황이다.** OS 업데이트 날 조용히 갈린다.
    """
    소스 = 스캐너경로.read_text(encoding="utf-8")
    assert "setRevision_" in 소스, (
        "banner_scan.py 에 setRevision_ 이 없다 — OS 업데이트가 판정을 "
        "조용히 바꿀 수 있는 유일한 경로가 열렸다 (D-10 · T-4-13)")

    # 지연 import 규율도 같이 지킨다. 최상단 import 는 `.venv-web` 스위트를 죽인다.
    for 줄 in 소스.splitlines():
        assert not 줄.startswith(("import Vision", "import Quartz", "from Foundation")), (
            f"Vision 계열 import 가 모듈 최상단에 있다: {줄!r} — "
            "`.venv-web` 이 이 파일을 로드할 때 collect 가 깨진다")
