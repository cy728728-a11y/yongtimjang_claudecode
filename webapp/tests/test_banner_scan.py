#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`banner_scan.py` 의 **순수 부분** 단위 테스트 (04-03).

## 이 파일이 `.venv-web` 으로 돈다는 제약이 무엇을 강제하는가

웹앱 스위트는 `.venv-web/bin/python3 -m pytest webapp/tests` 하나로 돈다. 그런데
`banner_scan.py` 가 쓰는 `PIL`·`Vision` 은 **`.venv-web` 에 없다**(D-19 — 없는 것이
설계다. `test_argv.py::test_웹앱에_다운로더도_Pillow도_없다` 가 그 경계를 집행한다).

→ **`banner_scan.py` 의 `PIL`·`Vision` import 는 모듈 최상단에 두지 마라.**
   쓰는 함수 안쪽 **지연 import** 여야 한다. 최상단에 두는 순간 아래
   `_스캐너()` 의 모듈 로드가 ImportError 로 죽고, 이 파일 전체가 collect 단계에서
   빨갛게 된다. 04-04 가 Vision OCR 을 얹을 때도 같은 제약이다 —
   `ocr()` 함수 안쪽에서 import 해라.

이 파일이 검사하는 것은 **네트워크도 이미지도 안 타는 부분**뿐이다:
URL 화이트리스트(SSRF 관문) · 캐시 회차 정리 · 무내용 장 규칙 · CLI 폴백 기본값.
실제 다운로드·OCR 회귀는 04-08 이 `.venv` 로 따로 돌린다.

**서브프로세스를 띄우지 않는다.** `test_argv.py:227-229` 와 같은 규율이다 —
테스트가 자식을 띄우면 271MB 를 진짜로 받으러 나간다.
"""
import importlib.util
import os
import sys
import time
from pathlib import Path

import pytest

from webapp import settings

# `banner_scan.py` 는 `webapp` 패키지가 아니라 스킬 스크립트다. 경로를 박지 않고
# 이 파일 위치에서 저장소 루트를 거슬러 올라가 찾는다(`conftest.py` 와 같은 관용구).
저장소루트 = Path(__file__).resolve().parents[2]
스캐너경로 = (저장소루트 / ".claude" / "skills" / "bulsaja-detail-page"
          / "scripts" / "banner_scan.py")


def _스캐너():
    """파일 경로에서 모듈을 로드한다 (sys.modules 에 남기지 않는다).

    `importlib` 을 쓰는 이유는 하나다 — 이 스크립트가 패키지가 아니라서
    `import` 문으로는 못 가져온다. 새 패키지를 만들지 않는 것이 저장소 관례다
    (`argv.py:43-50` — 새 디렉터리를 파면 STATE-01 에서 고장났던 지점을 다시 만든다).
    """
    assert 스캐너경로.exists(), f"스캐너가 없다: {스캐너경로}"
    규격 = importlib.util.spec_from_file_location("_banner_scan_under_test", 스캐너경로)
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


# ── SSRF 관문 (T-4-06) ──────────────────────────────────────────────────────

def test_허용URL인가_거부(스캐너):
    """`https` 아닌 것 · IP 리터럴 · 사설 대역 · 빈 문자열을 **전부** 거부한다.

    **URL 출처가 외부 서비스(불사자)다.** 상세 HTML 은 타오바오에서 긁어온 마크업이고,
    거기 내부망 주소가 섞여 들어오는 것을 우리가 막을 방법이 없다. 그래서 다운로드
    직전 한 관문에서 건다. 실측 916장은 전부 공인 https 였지만 그건 오늘의 사실이다.
    """
    거부대상 = [
        "http://cdn.bulsaja.com/a.jpg",          # 스킴
        "ftp://cdn.bulsaja.com/a.jpg",
        "data:image/png;base64,AAAA",
        "//cdn.bulsaja.com/a.jpg",               # 스킴 없는 상대경로
        "/images/a.jpg",
        "",
        "   ",
        None,
        "https://127.0.0.1/a.jpg",               # 루프백
        "https://localhost/a.jpg",
        "https://10.0.0.5/a.jpg",                # 사설
        "https://192.168.1.10/a.jpg",
        "https://169.254.169.254/latest/meta-data/",   # 클라우드 메타데이터
        "https://172.16.0.9/a.jpg",
        "https://172.31.255.254/a.jpg",
        "https://8.8.8.8/a.jpg",                 # 공인이라도 IP 리터럴은 거부
        "https://cdn.bulsaja.com@127.0.0.1/a.jpg",     # 자격증명으로 눈속임
        "https:///a.jpg",                        # 호스트 없음
    ]
    for url in 거부대상:
        허용, 사유 = 스캐너.허용URL인가(url)
        assert 허용 is False, f"{url!r} 를 통과시켰다 (SSRF)"
        assert 사유, f"{url!r} 를 거부하면서 사유를 안 남겼다 — 실패는 사유를 들고 온다"


def test_허용URL인가_통과(스캐너):
    """실측 CDN 두 곳은 통과한다 — 가드가 회차를 통째로 막으면 그것도 고장이다."""
    for url in ("https://cdn.bulsaja.com/upload/2026/a.jpg",
                "https://img.alicdn.com/imgextra/i3/x/b.jpg",
                "https://i.tosoiot.com/x/c.png",
                "https://zzcdn.example/a.jpg?v=1#frag"):
        허용, 사유 = 스캐너.허용URL인가(url)
        assert 허용 is True, f"{url!r} 를 막았다: {사유}"
        assert 사유 == ""


def test_허용URL인가_거부는_예외가_아니다(스캐너):
    """거부가 `raise` 면 URL 한 개가 회차 전체를 죽인다 — `(False, 사유)` 여야 한다."""
    결과 = 스캐너.허용URL인가("http://127.0.0.1/a.jpg")
    assert isinstance(결과, tuple) and len(결과) == 2
    assert 결과[0] is False


# ── 캐시 회차 정리 (T-4-07) ─────────────────────────────────────────────────

def _회차만들기(뿌리: Path, 이름: str, mtime: float):
    d = 뿌리 / 이름
    d.mkdir(parents=True, exist_ok=True)
    (d / "0000_00.bin").write_bytes(b"x")
    os.utime(d, (mtime, mtime))
    return d


def test_회차정리_오래된것만_지운다(스캐너, tmp_path):
    """`keep_runs=2` 면 최신 2개만 남고 나머지가 사라진다 (회차당 약 271MB)."""
    뿌리 = tmp_path / "cache"
    지금 = time.time()
    _회차만들기(뿌리, "2026-09-10", 지금 - 3000)
    _회차만들기(뿌리, "2026-09-15", 지금 - 2000)
    _회차만들기(뿌리, "2026-09-20", 지금 - 1000)
    (뿌리 / "메모.txt").write_text("디렉터리가 아닌 것은 건드리지 않는다", encoding="utf-8")

    지운것 = 스캐너.회차정리(str(뿌리), 2)

    assert 지운것 == ["2026-09-10"]
    assert not (뿌리 / "2026-09-10").exists()
    assert (뿌리 / "2026-09-15").exists()
    assert (뿌리 / "2026-09-20").exists()
    assert (뿌리 / "메모.txt").exists(), "파일까지 지우면 캐시 루트를 청소기로 민 것이다"


def test_회차정리_지금_회차는_안_지운다(스캐너, tmp_path):
    """돌고 있는 회차가 가장 오래됐어도(재실행) 지우지 않는다 — 자기 발을 쏘는 경로."""
    뿌리 = tmp_path / "cache"
    지금 = time.time()
    _회차만들기(뿌리, "옛날회차", 지금 - 5000)
    _회차만들기(뿌리, "중간회차", 지금 - 4000)
    _회차만들기(뿌리, "새회차", 지금 - 100)

    지운것 = 스캐너.회차정리(str(뿌리), 1, 보호="옛날회차")

    assert "옛날회차" not in 지운것
    assert (뿌리 / "옛날회차").exists()
    # 보호분이 남길 1개를 차지하므로 나머지는 전부 지워진다.
    assert sorted(지운것) == ["새회차", "중간회차"]


def test_회차정리_0은_전부_지워라가_아니다(스캐너, tmp_path):
    """`--keep-runs 0` 은 설정이 비었다는 신호다. 전량 삭제로 읽으면 안 된다.

    이 저장소가 네 번 막은 "빈 값이 전량이 되는 경로"의 **삭제판**이다
    (`jobs._build_argv` · `bulsaja_scan` · `ss_index_build` · `banner.제품이미지목록`).
    """
    뿌리 = tmp_path / "cache"
    _회차만들기(뿌리, "회차A", time.time())
    with pytest.raises(ValueError) as e:
        스캐너.회차정리(str(뿌리), 0)
    assert "전부 지워라" in str(e.value)
    assert (뿌리 / "회차A").exists()


def test_회차정리_캐시루트가_없으면_조용히_0건(스캐너, tmp_path):
    """첫 실행이다. 없는 디렉터리를 오류로 올리면 첫 회차가 못 돈다."""
    assert 스캐너.회차정리(str(tmp_path / "아직없음"), 2) == []


# ── 설정의 정본이 한 곳인가 (S-4) ───────────────────────────────────────────

def test_CLI_폴백이_settings와_같다(스캐너):
    """CLI 폴백 기본값이 `settings.DEFAULTS` 와 **한 글자도 다르지 않다**.

    숫자의 정본은 `webapp/settings.py` 다. 웹앱 잡(04-05 `BannerArgv`)은 임계값을 항상
    명시적으로 넘기므로 폴백은 터미널 실행에서만 쓰이는데, 바로 그래서 조용히 어긋난다 —
    설정을 고쳐도 터미널 실행만 옛날 값으로 도는 상태가 되고, 그때 둘 중 어느 쪽이
    산출물을 만들었는지 아무도 모른다. **어긋남을 사람 기억이 아니라 여기서 잡는다.**
    """
    for 키, 값 in 스캐너.폴백.items():
        설정키 = "banner_" + 키
        assert 설정키 in settings.DEFAULTS, (
            f"CLI 폴백 '{키}' 에 대응하는 설정 키 '{설정키}' 가 없다 — "
            "숫자의 정본은 settings.DEFAULTS 다")
        assert 값 == settings.DEFAULTS[설정키], (
            f"'{설정키}' 가 어긋났다: CLI {값!r} vs settings "
            f"{settings.DEFAULTS[설정키]!r}")


# ── 무내용 장 규칙 (Pitfall 1 · D-10) ───────────────────────────────────────

def test_무내용인가_경계값(스캐너):
    """종횡비 6.0 · 짧은 변 32px 경계에서 **정확히** 갈린다 (경계 포함 여부까지).

    규칙은 `긴변/짧은변 >= 상한` **또는** `짧은변 <= 하한` 이다. 부등호가 한 칸
    밀리면 멀쩡한 장이 통째로 버려지거나 구분선이 제품으로 남는다.
    """
    무내용인가 = 스캐너.무내용인가
    # 종횡비 경계 — 긴변/짧은변 으로 재므로 가로·세로 구분선이 같은 규칙에 걸린다.
    assert 무내용인가(1200, 200, 6.0, 32) is True, "6.0 정확히 = 무내용 (경계 포함)"
    assert 무내용인가(1199, 200, 6.0, 32) is False, "5.995 = 무내용 아님"
    assert 무내용인가(200, 1200, 6.0, 32) is True, "세로로 긴 구분선도 같은 규칙"
    # 짧은 변 경계 — 종횡비가 6 미만인 모양으로 짧은 변만 본다.
    assert 무내용인가(160, 32, 6.0, 32) is True, "32px 정확히 = 무내용 (경계 포함)"
    assert 무내용인가(150, 33, 6.0, 32) is False, "33px · 종횡비 4.5 = 무내용 아님"
    # 치수를 모르면 무내용이 아니다 — **미판정**이다. 못 본 것을 버려도 되는 것으로
    # 접으면 404 흡수와 같은 병이 된다.
    assert 무내용인가(None, 880, 6.0, 32) is False
    assert 무내용인가(0, 880, 6.0, 32) is False
    assert 무내용인가("이상한값", 880, 6.0, 32) is False


def test_무내용인가_실측_배너모양을_안_잡는다(스캐너):
    """실측 배너 9장(중앙 종횡비 0.89, 세로로 긴 장)이 무내용에 **안** 걸린다.

    ⚠️ Pitfall 1 · D-10 회귀다. "넓고 납작하면 배너" 는 실측상 **정반대**다 —
    배너는 오히려 세로로 길고, 넓고 납작한 것은 상세 원본을 자른 슬라이스·구분선이다.
    이 규칙으로 배너를 잡으려 들면 실측 코퍼스에서 전원 미탐이 난다.
    """
    배너모양 = [(790, 880), (790, 1278), (790, 1449), (750, 1000), (800, 750)]
    for w, h in 배너모양:
        assert 스캐너.무내용인가(w, h, 6.0, 32) is False, (
            f"{w}x{h} 를 무내용으로 접었다 — 실측 배너의 모양이다 (Pitfall 1)")
