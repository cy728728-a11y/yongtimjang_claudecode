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


# ── 비전 2차 판정 (D-22 · 전량) ──────────────────────────────────────────────
#
# **실제 API 를 한 번도 때리지 않는다.** 이음매 셋만 바꿔 끼운다:
#   `_비전열기`(가짜 응답 JSON bytes) · `비전이미지준비`(고정 bytes) · `이미지sha`(사본 흉내).
# urllib 전역 패치는 금지다 — 이음매가 하나라는 주장 자체가 검증 대상이다.
# `.venv-web` 에는 PIL 이 없으므로 `비전이미지준비` 는 반드시 바꿔 끼운다.

import base64 as _b64
import json as _json
import urllib.error as _urlerr

_가짜키 = "zz-FAKE-KEY-never-leak-9f3a"


def _장(순번, 판정, 사유=None):
    return {"순번": 순번, "url": f"https://cdn.bulsaja.com/{순번}.jpg", "w": 800, "h": 800,
            "판정": 판정, "사유": 사유, "썸네일": None}


class _가짜비전:
    """`_비전열기` 대역. 요청 바디의 이미지 bytes(= 원본 경로 문자열)로 답을 고른다."""

    def __init__(self, 답표=None, 기본="제품", 실패=(), 모델버전="gemini-3.6-flash-001"):
        self.답표 = dict(답표 or {})     # 경로 꼬리(예 "0000_01.bin") → "배너"/"제품"/예외
        self.기본 = 기본
        self.실패 = set(실패)            # 이 꼬리는 항상 URLError
        self.모델버전 = 모델버전
        self.호출 = []                   # (꼬리, 전체주소)

    def __call__(self, 요청, 타임아웃):
        바디 = _json.loads(요청.data)
        경로 = _b64.b64decode(바디["contents"][0]["parts"][0]["inline_data"]["data"]).decode()
        꼬리 = os.path.basename(경로)
        self.호출.append((꼬리, 요청.full_url))
        if 꼬리 in self.실패:
            raise _urlerr.URLError("가짜 연결 실패")
        답 = self.답표.get(꼬리, self.기본)
        if isinstance(답, Exception):
            raise 답
        return _json.dumps({
            "candidates": [{"content": {"parts": [{"text": _json.dumps(
                {"판정": 답, "상품보임": 답 == "제품", "근거": "가짜 근거 " * 10},
                ensure_ascii=False)}]}}],
            "usageMetadata": {"promptTokenCount": 1300, "candidatesTokenCount": 30,
                              "thoughtsTokenCount": 300},
            "modelVersion": self.모델버전,
        }, ensure_ascii=False).encode()


@pytest.fixture
def 비전목(스캐너, monkeypatch):
    """이음매 셋을 끼우고 가짜 비전을 돌려준다. 백오프·간격은 0 — 테스트가 잠들지 않게."""
    가짜 = _가짜비전()
    monkeypatch.setattr(스캐너, "_비전열기", 가짜)
    monkeypatch.setattr(스캐너, "비전이미지준비", lambda 경로, 최대=1024: str(경로).encode())
    monkeypatch.setattr(스캐너, "이미지sha", lambda 경로: "sha-" + os.path.basename(str(경로)))
    monkeypatch.setattr(스캐너, "비전_백오프", (0, 0, 0))
    return 가짜


def _2차(스캐너, 상품들, tmp_path, 상한=1000, **덮기):
    인자 = dict(키=_가짜키, 모델="gemini-3.6-flash", 타임아웃=5.0, 상한=상한, 간격=0)
    인자.update(덮기)
    return 스캐너.전부2차판정(상품들, str(tmp_path / "cache"), "zzrun", **인자)


def test_2차_대상은_판정된_장_전부_미판정은_0회(스캐너, 비전목, tmp_path):
    """배너·제품·무내용 장 **전부**에 건다(D-22 · 판정대상전량). 미판정+사유 장은 0회."""
    상품들 = [{"장": [_장(0, "제품"), _장(1, "배너", "어휘군:품질보증"), _장(2, "무내용", "무내용(종횡비) 1200x40"),
                    _장(3, "미판정", "HTTP 404 (재시도 무의미 — 영구)")]}]
    결과 = _2차(스캐너, 상품들, tmp_path)
    꼬리들 = sorted(c for c, _ in 비전목.호출)
    assert 꼬리들 == ["0000_00.bin", "0000_01.bin", "0000_02.bin"]
    assert 결과["판정대상장수"] == 3 and 결과["호출"] == 3
    미판정장 = 상품들[0]["장"][3]
    assert 미판정장["판정"] == "미판정" and "2차" not in 미판정장


def test_2차_합집합_비전배너가_1차비배너를_배너로(스캐너, 비전목, tmp_path):
    """1차 제품/무내용 + 비전 배너 → 배너. 1차 값은 `장["1차"]` 에 보존된다."""
    비전목.기본 = "배너"
    상품들 = [{"장": [_장(0, "제품"), _장(1, "무내용", "무내용(종횡비) 1200x40")]}]
    결과 = _2차(스캐너, 상품들, tmp_path)
    for 장, 원래 in zip(상품들[0]["장"], ("제품", "무내용")):
        assert 장["판정"] == "배너"
        assert 장["출처"] == "비전"
        assert 장["1차"]["판정"] == 원래
        assert 장["2차"]["판정"] == "배너" and 장["2차"]["실패"] is None
        assert 장["사유"].startswith("2차:배너(v3)")
    assert 결과["비전추가배너"] == 2


def test_2차_합집합이면_1차배너는_비전제품이어도_유지(스캐너, 비전목, tmp_path, monkeypatch):
    """합성규칙이 합집합일 때 1차 배너 + 비전 제품 → **배너 유지**. 어휘군 재현율을 버리지 않는다."""
    monkeypatch.setattr(스캐너, "합성규칙", "합집합")
    비전목.기본 = "제품"
    상품들 = [{"장": [_장(0, "배너", "어휘군:연락처"), _장(1, "배너", "어휘군:반품교환")]}]
    결과 = _2차(스캐너, 상품들, tmp_path)
    assert [장["판정"] for 장 in 상품들[0]["장"]] == ["배너", "배너"]
    assert all(장["출처"] == "어휘군" for 장 in 상품들[0]["장"])
    assert 결과["뒤집기"] == 0


def test_2차_뒤집기는_허용군만_걸린_장만(스캐너, 비전목, tmp_path, monkeypatch):
    """뒤집기 규칙이면 걸린군 ⊆ {연락처,공장직판} + 비전 제품 → 제품. 다른 군이 하나라도 있으면 배너."""
    monkeypatch.setattr(스캐너, "합성규칙", "합집합+뒤집기(연락처,공장직판)")
    비전목.기본 = "제품"
    상품들 = [{"장": [_장(0, "배너", "어휘군:연락처"),
                    _장(1, "배너", "어휘군:연락처,공장직판"),
                    _장(2, "배너", "어휘군:연락처,AS안내"),
                    _장(3, "배너", "어휘군:반품교환")]}]
    비전목.답표 = {}
    결과 = _2차(스캐너, 상품들, tmp_path)
    판정들 = [장["판정"] for 장 in 상품들[0]["장"]]
    assert 판정들 == ["제품", "제품", "배너", "배너"]
    assert 상품들[0]["장"][0]["출처"] == "뒤집기"
    assert "뒤집기" in 상품들[0]["장"][0]["사유"]
    assert 결과["뒤집기"] == 2
    # 1차 배너 + 비전 배너는 뒤집기 규칙에서도 배너(둘다)
    비전목.기본 = "배너"
    상품들2 = [{"장": [_장(0, "배너", "어휘군:연락처")]}]
    _2차(스캐너, 상품들2, tmp_path / "b")
    assert 상품들2[0]["장"][0]["판정"] == "배너" and 상품들2[0]["장"][0]["출처"] == "둘다"


def test_2차_실패는_결코_제품이_아니다(스캐너, 비전목, tmp_path):
    """호출 실패: 1차 제품/무내용 → 미판정+사유 · 1차 배너 → 배너 유지 + 실패 기록."""
    비전목.실패 = {"0000_00.bin", "0000_01.bin", "0000_02.bin"}
    상품들 = [{"장": [_장(0, "제품"), _장(1, "무내용", "무내용(종횡비) 1200x40"),
                    _장(2, "배너", "어휘군:연락처")]}]
    결과 = _2차(스캐너, 상품들, tmp_path)
    제품장, 무내용장, 배너장 = 상품들[0]["장"]
    for 장 in (제품장, 무내용장):
        assert 장["판정"] == "미판정"
        assert 장["사유"] == "2차 판정 실패: URLError"
        assert 장["2차"]["실패"] == "URLError"
    assert 배너장["판정"] == "배너" and 배너장["2차"]["실패"] == "URLError"
    assert 결과["실패"] == 3 and 결과["성공"] == 0
    # 미판정+사유 → 상품층에서 판정불가로 승격된다 (제거율 분모에서 빠진다)
    assert 스캐너.상품별미판정반영(상품들) == 1
    assert 상품들[0]["스킵사유"] == "판정불가"
    # 성공하지 못한 호출은 체크포인트에 없다 — 다음 실행이 다시 시도해야 한다
    경로 = 스캐너.체크포인트경로(str(tmp_path / "cache"), "zzrun", "gemini-3.6-flash")
    assert 스캐너.체크포인트읽기(경로) == {}


def test_2차_같은_sha는_1회만_호출되고_전_사본에_적용(스캐너, 비전목, tmp_path, monkeypatch):
    """물갈이 사본의 같은 이미지는 1회만 과금된다 — 결과는 모든 사본에 적용."""
    monkeypatch.setattr(스캐너, "이미지sha", lambda 경로: "sha-같음")
    비전목.기본 = "배너"
    상품들 = [{"장": [_장(0, "제품")]}, {"장": [_장(0, "제품"), _장(1, "제품")]}]
    결과 = _2차(스캐너, 상품들, tmp_path)
    assert len(비전목.호출) == 1
    assert 결과["고유이미지"] == 1 and 결과["판정대상장수"] == 3
    assert all(장["판정"] == "배너" for 상품 in 상품들 for 장 in 상품["장"])


def test_2차_체크포인트_적중은_호출_0회(스캐너, 비전목, tmp_path):
    """한 번 판정한 sha 는 재실행이 다시 부르지 않는다 (T-4-39)."""
    비전목.기본 = "배너"
    _2차(스캐너, [{"장": [_장(0, "제품"), _장(1, "제품")]}], tmp_path)
    assert len(비전목.호출) == 2
    경로 = 스캐너.체크포인트경로(str(tmp_path / "cache"), "zzrun", "gemini-3.6-flash")
    기록들 = 스캐너.체크포인트읽기(경로)
    assert set(기록들) == {"sha-0000_00.bin", "sha-0000_01.bin"}
    for r in 기록들.values():
        assert r["모델"] == "gemini-3.6-flash" and r["지시문sha256"] == 스캐너.지침_sha256
        assert r["응답모델"] == "gemini-3.6-flash-001"
    # 재실행 — 새 상품들 dict(1차 상태) · 상한 0 이어도 과금 대상 0 이면 정상 진행
    비전목.호출.clear()
    상품들 = [{"장": [_장(0, "제품"), _장(1, "제품")]}]
    결과 = _2차(스캐너, 상품들, tmp_path, 상한=0)
    assert 비전목.호출 == []
    assert 결과["체크포인트적중"] == 2 and 결과["호출"] == 0
    assert all(장["판정"] == "배너" for 장 in 상품들[0]["장"])
    # 모델이 다른 기록은 재사용하지 않는다
    assert 스캐너.체크포인트읽기(경로, 모델="다른-모델") == {}


def test_2차_과금대상이_상한을_넘으면_호출_0회로_거부(스캐너, 비전목, tmp_path):
    """자르지 않고 거부한다 — 기본 상한 0 = 승인 전 유료 호출 0."""
    상품들 = [{"장": [_장(0, "제품"), _장(1, "제품"), _장(2, "배너", "어휘군:연락처")]}]
    with pytest.raises(스캐너.비전2차불가) as 잡힘:
        _2차(스캐너, 상품들, tmp_path, 상한=2)
    assert 비전목.호출 == []
    assert "3" in str(잡힘.value) and "--vision2-estimate" in str(잡힘.value)
    # 장은 건드리지 않았다
    assert [장["판정"] for 장 in 상품들[0]["장"]] == ["제품", "제품", "배너"]
    with pytest.raises(스캐너.비전2차불가):
        _2차(스캐너, 상품들, tmp_path, 상한=0)
    assert 비전목.호출 == []


def test_2차_연속_10장_실패면_중단_성공분은_남는다(스캐너, 비전목, tmp_path):
    """쿼터 소진 패턴 → 비전2차불가. 그때까지 성공한 장은 체크포인트에 남아 재과금되지 않는다."""
    장들 = [_장(i, "제품") for i in range(14)]
    비전목.실패 = {f"0000_{i:02d}.bin" for i in range(2, 14)}
    with pytest.raises(스캐너.비전2차불가):
        _2차(스캐너, [{"장": 장들}], tmp_path)
    # 성공 2 + 연속 실패 10 장에서 멈춘다. 실패 장은 재시도 3회를 포함해 4번씩 두드린다.
    assert len({c for c, _ in 비전목.호출}) == 12
    assert len(비전목.호출) == 2 + 10 * 4
    경로 = 스캐너.체크포인트경로(str(tmp_path / "cache"), "zzrun", "gemini-3.6-flash")
    assert set(스캐너.체크포인트읽기(경로)) == {"sha-0000_00.bin", "sha-0000_01.bin"}


def test_2차_모르는_판정값과_429(스캐너, monkeypatch):
    """응답 판정이 배너/제품이 아니면 ValueError (제품으로 접지 않는다). 429 는 Retry-After 만큼 쉰다."""
    쉰것 = []
    monkeypatch.setattr(스캐너.time, "sleep", lambda s: 쉰것.append(s))
    가짜 = _가짜비전(답표={"x.bin": "워터마크제품"})
    monkeypatch.setattr(스캐너, "_비전열기", 가짜)
    with pytest.raises(ValueError):
        스캐너.비전한장(b"/zz/x.bin", 키=_가짜키, 모델="m", 타임아웃=1, 백오프=(0, 0, 0))

    응답들 = []

    def 한번429(요청, 타임아웃):
        if not 응답들:
            응답들.append(1)
            raise _urlerr.HTTPError(요청.full_url, 429, "Too Many", {"Retry-After": "7"}, None)
        return 가짜(요청, 타임아웃)
    monkeypatch.setattr(스캐너, "_비전열기", 한번429)
    판정, 근거, 사용량, 응답모델 = 스캐너.비전한장(b"/zz/y.bin", 키=_가짜키, 모델="m",
                                          타임아웃=1, 백오프=(0.5, 1.5, 3.0))
    assert 판정 == "제품" and len(근거) <= 40
    assert 사용량 == {"입력토큰": 1300, "출력토큰": 330}
    assert 응답모델 == "gemini-3.6-flash-001"
    assert 7.0 in 쉰것


def test_2차_지시문_v3가_evidence_원문과_바이트까지_같다(스캐너):
    """지시문은 파일럿 v3 원문 그대로다 — 낱말 목록을 더한 v2 는 26/30 → 17/30 으로 떨어졌다."""
    import hashlib
    원본경로_ = (저장소루트 / ".planning" / "phases" / "04-banner-detection" / "evidence"
              / "vision_pilot_v3.py")
    규격 = importlib.util.spec_from_file_location("_pilot_v3", 원본경로_)
    파일럿 = importlib.util.module_from_spec(규격)
    규격.loader.exec_module(파일럿)
    assert 스캐너.지침_v3.encode() == 파일럿.지침.encode()
    assert hashlib.sha256(스캐너.지침_v3.encode()).hexdigest() == 스캐너.지침_sha256
    assert 스캐너.지침_sha256 == "5ff5d8cc3a7fc55cc9666ffaae67c340cf3bc3f2e194d53c4b0e7b626ec3ea2e"
    # 합성규칙은 T1 실측 결정을 그대로 옮긴 값이다
    결과 = _json.loads((원본경로_.parent / "flip_rule_result.json").read_text(encoding="utf-8"))
    assert 스캐너.합성규칙 == 결과["결정"]


# ── main() 배선 — 서브프로세스 없이 in-process 로 돈다 ─────────────────────────

def _main준비(스캐너, monkeypatch, tmp_path, 첫판정, 추가인자=()):
    """조인 산출물 1상품 + 다운로드·특징·OCR 을 대역으로 바꾼 main() 실행 준비."""
    그림 = "".join(f'<img src="https://cdn.bulsaja.com/{i}.jpg">' for i in range(len(첫판정)))
    조인 = tmp_path / "join.json"
    조인.write_text(_json.dumps({"행": [{"판매자상품코드": "zzA", "불사자코드": "zzA",
                                      "타오바오상품번호": "1",
                                      "uploadDetailContents": {"renderContent": 그림}}]}),
                  encoding="utf-8")
    키파일 = tmp_path / ".env"
    키파일.write_text(f"OTHER=1\nGEMINI_API_KEY={_가짜키}\n", encoding="utf-8")

    def 가짜받기(상품들, 캐시루트, 회차, 작업자수):
        for 상품 in 상품들:
            for 장 in 상품["장"]:
                장.update({"w": 800, "h": 800, "사유": None})
        return len(첫판정), 0, {}

    def 가짜판정(상품들, 캐시루트, 회차, 종횡비상한, 짧은변하한, *, revision):
        for 장 in 상품들[0]["장"]:
            판정, 사유 = 첫판정[장["순번"]]
            장["판정"], 장["사유"] = 판정, 사유
        return len(첫판정), 0, 0, 0, 0

    monkeypatch.setattr(스캐너, "전부받기", 가짜받기)
    monkeypatch.setattr(스캐너, "전부특징", lambda *a, **k: (len(첫판정), 0, 0))
    monkeypatch.setattr(스캐너, "전부판정", 가짜판정)
    출력 = tmp_path / "out.json"
    argv = ["banner_scan.py", "--join", str(조인), "--out", str(출력),
            "--run-dir", "zzrun", "--cache", str(tmp_path / "cache"),
            "--thumbs", str(tmp_path / "thumbs"), "--vision2-key-file", str(키파일),
            "--vision2-interval", "0", *추가인자]
    monkeypatch.setattr(sys, "argv", argv)
    return 출력


_세장 = {0: ("제품", None), 1: ("배너", "어휘군:연락처"), 2: ("배너", "어휘군:반품교환")}


def test_2차_견적모드는_호출_0회_산출물_미작성(스캐너, 비전목, monkeypatch, tmp_path, capsys):
    """`--vision2-estimate` — Gemini 0회 · 산출물 없음 · stdout 에 기계용 한 줄."""
    출력 = _main준비(스캐너, monkeypatch, tmp_path, _세장, ["--vision2-estimate"])
    assert 스캐너.main() == 0
    assert 비전목.호출 == []
    assert not 출력.exists()
    줄들 = [줄 for 줄 in capsys.readouterr().out.splitlines()
          if 줄.startswith("###VISION2_ESTIMATE### ")]
    assert len(줄들) == 1
    견 = _json.loads(줄들[0].split(" ", 1)[1])
    assert 견["판정대상장수"] == 3 and 견["과금대상"] == 3
    assert 견["예상입력토큰"] == 3 * 1343 and 견["예상출력토큰"] == 3 * 378


def test_2차_지시문판이_다르면_비전2차불가(스캐너, 비전목, monkeypatch, tmp_path):
    """`--vision2-prompt` 가 스크립트의 지침판과 다르면 exit 5 경로 · 호출 0 · 산출물 없음."""
    출력 = _main준비(스캐너, monkeypatch, tmp_path, _세장,
                  ["--vision2-prompt", "v4", "--vision2-max-calls", "100"])
    with pytest.raises(스캐너.비전2차불가):
        스캐너.main()
    assert 비전목.호출 == [] and not 출력.exists()
    # `__main__` 이 이 예외를 exit 5 로 내린다 — 그 자리는 정확히 한 곳이다
    assert 스캐너경로.read_text(encoding="utf-8").count("sys.exit(5)") == 1


def test_2차_판정규칙_스탬프와_키_비노출(스캐너, 비전목, monkeypatch, tmp_path, capsys):
    """산출물 `판정규칙.2차판정` 에 모델·응답모델·지시문판·sha256·합성규칙·적용범위.
    키 문자열은 stdout·산출물·체크포인트 어디에도 없다 (요청 주소에만 있다)."""
    비전목.답표 = {"0000_00.bin": "배너", "0000_01.bin": "제품", "0000_02.bin": "제품"}
    출력 = _main준비(스캐너, monkeypatch, tmp_path, _세장, ["--vision2-max-calls", "3"])
    assert 스캐너.main() == 0
    assert len(비전목.호출) == 3
    assert all(_가짜키 in 주소 for _, 주소 in 비전목.호출)      # 키는 실제로 쓰였다
    본문 = 출력.read_text(encoding="utf-8")
    출력로그 = capsys.readouterr()
    체크 = Path(스캐너.체크포인트경로(str(tmp_path / "cache"), "zzrun", "gemini-3.6-flash"))
    for 어디, 글 in (("산출물", 본문), ("stdout", 출력로그.out), ("stderr", 출력로그.err),
                   ("체크포인트", 체크.read_text(encoding="utf-8"))):
        assert _가짜키 not in 글, f"키가 {어디} 에 샜다 (T-4-33)"
    문서 = _json.loads(본문)
    칸 = 문서["판정규칙"]["2차판정"]
    assert 칸["사용"] is True
    assert 칸["모델"] == "gemini-3.6-flash" and 칸["응답모델"] == "gemini-3.6-flash-001"
    assert 칸["지시문판"] == "v3" and 칸["지시문sha256"] == 스캐너.지침_sha256
    assert 칸["합성규칙"] == 스캐너.합성규칙 and 칸["적용범위"] == "판정대상전량"
    assert 칸["호출"] == 3 and 칸["성공"] == 3 and 칸["비전추가배너"] == 1
    assert 칸["입력토큰"] == 3 * 1300 and 칸["출력토큰"] == 3 * 330
    판정들 = [장["판정"] for 장 in 문서["상품"][0]["장"]]
    # 0: 제품→비전배너=배너 · 1: 연락처만+비전제품=뒤집기(제품) · 2: 반품교환=배너 유지
    assert 판정들 == ["배너", "제품", "배너"]


def test_2차_꺼진_회차도_판정규칙_칸을_싣는다(스캐너, 비전목, monkeypatch, tmp_path):
    """`--vision2-enabled off` — 호출 0 · 키 불필요 · `2차판정.사용: false` 가 옛 회차와 구별해 준다."""
    출력 = _main준비(스캐너, monkeypatch, tmp_path, _세장,
                  ["--vision2-enabled", "off", "--vision2-key-file", str(tmp_path / "없음.env")])
    assert 스캐너.main() == 0
    assert 비전목.호출 == []
    칸 = _json.loads(출력.read_text(encoding="utf-8"))["판정규칙"]["2차판정"]
    assert 칸["사용"] is False and 칸["호출"] == 0 and 칸["모델"] is None


def test_2차_키가_없으면_비전2차불가_경로만(스캐너, tmp_path):
    """키 파일에 GEMINI_API_KEY 가 없으면 비전2차불가 — 사유엔 경로만."""
    env = tmp_path / ".env"
    env.write_text("OTHER=1\n", encoding="utf-8")
    with pytest.raises(스캐너.비전2차불가) as 잡힘:
        스캐너.비전키읽기(str(env))
    assert str(env) in str(잡힘.value)
    env.write_text(f'GEMINI_API_KEY="{_가짜키}"\n', encoding="utf-8")
    assert 스캐너.비전키읽기(str(env)) == _가짜키
