#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""배너 판정 스캐너 — 조인 산출물의 상세 이미지를 **장 단위로** 훑는다 (BANNER-01/03b/04).

이미지에 손대는 코드는 전부 여기에 산다. `webapp/` 은 HTTP 도 Pillow 도 OCR 도 만지지
않는다(D-19) — 웹앱 전용 venv(`.venv-web`)에는 그 패키지가 아예 없고,
`webapp/tests/test_argv.py::test_웹앱에_다운로더도_Pillow도_없다` 가 매 실행 그 사실을
`webapp/**` 전체에 집행한다. 이 스크립트는 CLI venv(`.venv`)에서 돈다.

**MCP 를 한 번도 부르지 않는다 — 크레딧 0 · 불사자 호출 0회.** 입력은 직전 성공한
`bulsaja_scan` 의 조인 산출물 JSON 하나뿐이고, 거기 이미 들어 있는
`uploadDetailContents.renderContent` 에서 이미지 URL 을 뽑는다. 그래서 불사자 MCP 클라이언트
모듈을 import 하지 않는다 — 불러오는 순간 레이트리밋 모듈과 MCP 세션이 끌려와 그 주장이
코드로 깨진다. **그 모듈 이름을 이 파일에 글자로 남기지도 않는다**(`test_argv.py:205-207` 의
규율): 가드가 찾는 문자열을 감시 대상이 들고 있으면 "주석에는 있어도 된다" 는 예외가 생기고,
그 예외가 언젠가 진짜 import 로 자란다.

파싱 규칙은 **여기에 복제하지 않는다.** `webapp/banner.py` 의 `상세이미지목록` ·
`상세보유행들` 을 그대로 쓴다(S-1: 진실이 둘이 되면 화면과 산출물이 다른 말을 한다).
`banner.py` 는 import 가 stdlib 뿐이라 `.venv` 에서도 안전하게 들어온다.

종료코드
  0  정상 (**부분 미판정은 정상이다** — 산출물의 `집계.미판정` 과 그 상품의
     `스킵사유: "판정불가"` 로 드러난다)
  2  훑을 대상이 없다 (`--join` 파일이 없거나, 상세 보유 행이 0건)
  3  **판정완료 장이 0이다** (전량 미판정 — 네트워크가 통째로 죽었거나 CDN 이 막혔다)
  4  `pyobjc-framework-Vision` 미설치

  ⚠️ **exit 3 의 경계를 여기서 못박는다.** "미판정이 한 장이라도 남으면 3" 이 아니다.
  실측 404 25장(916장의 2.7%)은 3회 재시도 후에도 **영구 404** 라, 그 규칙이면 매 실행이
  실패로 기록되고 `jobs.latest_done("banner_scan")` 이 영영 비어 **검수 화면이 산출물을
  못 찾는다.** RESEARCH §산출물 계약의 예시 자체가 `집계.미판정: 25` 를 담은 성공
  산출물이다. 그래서:
    · 부분 미판정 → exit 0 + 장별 `판정: "미판정"` + 사유 + 그 상품 `스킵사유: "판정불가"`
    · 전량 미판정 → exit 3
  **흡수는 여전히 금지다** — `webapp.banner.제품이미지목록` 이 미판정 장을 가진 상품을
  Phase 5 입력으로 쓰지 못하게 예외로 막는다. 404 를 "배너 아님" 으로 접으면 그 상품은
  제품 이미지가 0장인데 화면에는 멀쩡해 보인다(Phase 3 CR-01~03 과 같은 병).

캐시 파일 이름 규약 (04-04 · 04-06 이 같이 쓴다)
  원본   `<cache>/<run_dir>/<상품순번 4자리>_<장순번 2자리>.bin`
  썸네일 `<thumbs>/<run_dir>/<상품순번 4자리>_<장순번 2자리>.webp`
  산출물의 `장[].썸네일` 에는 **파일명만** 싣는다. 경로를 싣지 마라 — 04-06 의 경로 탈출
  방어가 "서버가 인덱스로 경로를 만든다"에 기대고 있다.

중단 (Ctrl-C)
  산출물을 쓰지 않는다(`bulsaja_scan.py` 규약). 크레딧 0 · 4분짜리라 부분 산출물을 남길
  이유가 없다. **단 다운로드 캐시는 남긴다** — 271MB 재다운로드를 막는 것이고,
  캐시는 산출물이 아니다.

사용:
  python3 banner_scan.py --join <조인산출물.json> --out <산출물.json>
        --run-dir <회차> --cache <원본캐시디렉터리> --thumbs <썸네일디렉터리>
        [--workers 8] [--vision-revision 3]
        [--blank-ar 6.0] [--blank-short-px 32]
        [--skip-min-keep 2] [--skip-max-removal 0.5]
        [--lexicon-version 2026-09-22] [--keep-runs 2]
"""
import argparse
import concurrent.futures
import ipaddress
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError) as _인코딩오류:
    # 재설정이 안 되는 스트림(특수 파이프 등). 한글이 깨질 수는 있어도 진행은 막지 않는다.
    # **`pass` 로 삼키지 않는다** — 왜 깨졌는지 모르는 로그가 제일 비싸다.
    sys.stderr.write(f"[경고] stdout 인코딩 재설정 실패: {_인코딩오류}\n")

# **경로를 박지 않는다** — 이 파일 위치에서 거슬러 올라가 찾는다.
# (같은 관용구: `ss_index_build.py:62-74` · `product-name/scripts/run_names.py:40-46`)
#
# `ss_index_build.py` 와 달리 **`SKILL_SCRIPTS`(bulsaja-category-fix) 줄이 없다.**
# 이 스크립트는 MCP 를 한 번도 안 부르므로 그 스킬의 클라이언트 모듈을 들일 이유가 없다.
# 대신 저장소 루트를 넣어 `webapp.banner` 의 파싱 규칙을 **재사용**한다.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from webapp import banner, state  # noqa: E402


# ── CLI 폴백 기본값 ─────────────────────────────────────────────────────────
#
# **숫자의 정본은 `webapp/settings.py` 의 `DEFAULTS` 다** (S-4). 웹앱 잡(04-05 `BannerArgv`)은
# 이 값들을 **항상 명시적으로** 넘긴다 — 그래야 `workspace.toml` 을 고쳤을 때 동작이 바뀐다.
# 아래 숫자는 **터미널에서 직접 돌릴 때만** 쓰이는 폴백이고, `settings.DEFAULTS` 와
# 어긋나면 `webapp/tests/test_banner_scan.py::test_CLI_폴백이_settings와_같다` 가 터진다.
# (설정 모듈을 여기서 import 하지 않는 이유: `webapp.settings` 는 `webapp.paths` 를 끌고
#  오고 그건 `workspace.toml` 에 묶인다. 순수 파싱만 쓰는 이 스크립트를 PC별 설정 파일에
#  묶어 두면 터미널 실행이 환경 문제로 죽는다. 어긋남은 위 테스트가 기계로 잡는다.)
폴백 = {
    "workers": 8,               # settings `banner_workers`
    "vision_revision": 3,       # settings `banner_vision_revision` (D-10 — 박는 것이 요점)
    "blank_ar": 6.0,            # settings `banner_blank_ar`
    "blank_short_px": 32,       # settings `banner_blank_short_px`
    "skip_min_keep": 2,         # settings `banner_skip_min_keep` (D-07)
    "skip_max_removal": 0.5,    # settings `banner_skip_max_removal` (D-08)
    "lexicon_version": "2026-09-22",   # settings `banner_lexicon_version`
    "keep_runs": 2,             # settings `banner_keep_runs` — 원본 캐시를 남길 회차 수
}


# ── 공용 유틸 (`ss_index_build.py:80-138` 에서 그대로 복사) ──────────────────
#
# 스크립트 간 공유 모듈이 없다 — 저장소 관례가 복사다. 공유 모듈을 새로 파면
# 스킬 스크립트들이 서로의 릴리스에 묶인다.

def 말하기(줄):
    """진행 출력. **`flush=True` 가 협상 불가다.**

    잡 로그가 0바이트로 머물면 사람이 "멈췄나" 를 판단할 수 없다. 잡으로 띄울 때는
    `PYTHONUNBUFFERED` 가 주입되지만(`webapp/jobs.py`), 터미널에서 직접 돌릴 때는
    그게 없으므로 **둘 다** 필요하다.
    """
    try:
        print(줄, flush=True)
    except Exception:
        pass


def 오류말하기(줄):
    """치명적 사유는 stderr 로도 남긴다 — 잡 레코드가 보관하는 게 stderr 꼬리다.

    stdout 과 **따로** 흘러서 버퍼도 따로다. 여기도 `flush=True` 가 필요하다.
    """
    try:
        print(줄, file=sys.stderr, flush=True)
    except Exception:
        pass


def 원자적쓰기(경로, obj):
    """`tmp → os.replace` — 반쯤 쓴 JSON 을 읽는 쪽이 보지 않게 한다.

    (`webapp/jobs.py:340-350` 의 `_write_targets` 와 같은 관용구)
    """
    try:
        경로 = str(경로)
        os.makedirs(os.path.dirname(경로) or ".", exist_ok=True)
        tmp = 경로 + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        os.replace(tmp, 경로)
    except Exception as e:
        말하기(f"[경고] 파일 저장 실패({경로}): {e}")


def 지금():
    """로컬 시각 + 오프셋 (`webapp/jobs._now()` 와 같은 모양)."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


# ── 캐시 · 썸네일 이름 (04-04 · 04-06 이 같이 쓴다) ─────────────────────────

def 장이름(상품순번: int, 장순번: int) -> str:
    """`<상품순번 4자리>_<장순번 2자리>` — 확장자 없는 공통 줄기.

    **파일명은 인덱스에서만 만든다.** 외부에서 받은 URL 의 basename 을 쓰면 그 순간
    경로 탈출(`../../.ssh/id_rsa`)의 입구가 된다 — 04-06 의 썸네일 라우트 방어가
    "서버가 정수 인덱스로 경로를 만든다"는 이 규약 위에 서 있다.
    """
    return f"{int(상품순번):04d}_{int(장순번):02d}"


def 원본경로(캐시루트: str, 회차: str, 상품순번: int, 장순번: int) -> str:
    return os.path.join(캐시루트, 회차, 장이름(상품순번, 장순번) + ".bin")


def 썸네일이름(상품순번: int, 장순번: int) -> str:
    return 장이름(상품순번, 장순번) + ".webp"


def 썸네일경로(썸루트: str, 회차: str, 상품순번: int, 장순번: int) -> str:
    return os.path.join(썸루트, 회차, 썸네일이름(상품순번, 장순번))


# ── SSRF 관문 · 다운로드 · 캐시 정리 (T-4-06 / T-4-07 / T-4-01) ─────────────

# 재시도 사이에 쉬는 시간(초). 지수 백오프 3회 — 실측 404 25장은 3회 뒤에도 영구 404였다.
# (D-09 가드가 찾는 낱말을 이 파일에 글자로 남기지 않는다 — `test_사람큐_없음` 이
#  `banner.py` 와 이 파일을 같이 훑는다. 가드 대상이 그 낱말을 들고 있으면
#  "주석에는 있어도 된다" 는 예외가 생기고, 그 예외가 언젠가 진짜 상태값으로 자란다.)
기본_백오프 = (0.3, 0.6, 0.9)
기본_타임아웃 = 20.0

# 브라우저 UA 를 싣는다. 불사자 앞단 방화벽이 stdlib 기본 UA(`Python-urllib/…`)를
# 403 으로 끊은 실측이 있다 — 크레딧이 아니라 **이미지 한 장도 못 받는** 문제라
# 여기서 미리 막는다. 위조가 아니라 "차단 회피용 최소 표기"다.
사용자에이전트 = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Safari/537.36")


def 허용URL인가(url) -> tuple:
    """다운로드 직전 **단일 관문**. `(허용여부, 사유)` (SSRF · ASVS V5 · T-4-06).

    **URL 의 출처가 외부 서비스(불사자)라 신뢰할 수 없다.** 상세 HTML 은 타오바오에서
    긁어온 마크업이고, 거기에 `http://169.254.169.254/...`(클라우드 메타데이터) 나
    `https://127.0.0.1:8765/...`(자기 웹앱) 이 섞여 들어오는 것을 막을 방법이 우리에게 없다.
    실측 916장은 전부 `https://` + 공인 호스트였지만, 그건 **오늘의 사실**이지 계약이 아니다.

    거부는 **예외가 아니다.** 그 장을 `판정: "미판정"` + 사유로 남긴다 — 예외로 올리면
    URL 한 개가 회차 전체를 죽이고, 조용히 건너뛰면 "배너 아님" 으로 흡수된다(T-4-01).

    DNS 를 풀지 않는다. 푼 값과 실제 접속이 같다는 보장이 없고(TOCTOU), 1인 로컬에서
    얻는 것보다 매 URL 에 붙는 지연이 크다. 스킴·호스트 모양 검사로 충분하다.
    """
    if not isinstance(url, str) or not url.strip():
        # `src` 가 없는 `<img>` 자리. 빈 문자열을 통과시키면 urlopen 이 이상한 곳을 본다.
        return False, "허용되지 않는 URL (비어 있다)"
    try:
        조각 = urllib.parse.urlsplit(url.strip())
    except ValueError as e:
        return False, f"허용되지 않는 URL (파싱 실패: {e})"

    if 조각.scheme.lower() != "https":
        # `http`·`data:`·상대경로 전부 여기서 걸린다. 실측 0건이지만 미래 방어다.
        return False, f"허용되지 않는 URL (스킴 {조각.scheme or '없음'})"
    if "@" in 조각.netloc:
        # `https://cdn.bulsaja.com@127.0.0.1/…` 처럼 사람 눈을 속이는 모양.
        return False, "허용되지 않는 URL (자격증명이 박힌 호스트)"

    try:
        호스트 = 조각.hostname
    except ValueError as e:
        return False, f"허용되지 않는 URL (호스트 파싱 실패: {e})"
    if not 호스트:
        return False, "허용되지 않는 URL (호스트가 없다)"
    호스트 = 호스트.lower()

    if 호스트 == "localhost" or 호스트.endswith(".localhost"):
        return False, "허용되지 않는 URL (localhost)"

    try:
        주소 = ipaddress.ip_address(호스트)
    except ValueError:
        # IP 리터럴이 아니다 = 보통의 도메인. 통과.
        return True, ""
    # IP 리터럴은 **전부** 거부한다. 사설 대역만 막으면 `https://1.2.3.4/…` 같은
    # 공인 IP 직접 지정이 남는데, 그건 CDN 이 하는 모양이 아니다(실측 0건).
    if (주소.is_private or 주소.is_loopback or 주소.is_link_local
            or 주소.is_reserved or 주소.is_multicast):
        # 127. / 10. / 192.168. / 169.254. / 172.16~31. 이 전부 여기 들어온다.
        return False, f"허용되지 않는 URL (사설·루프백 대역 {호스트})"
    return False, f"허용되지 않는 URL (IP 리터럴 {호스트})"


def 회차정리(캐시루트, 남길회차: int, 보호=None) -> list:
    """원본 캐시에서 오래된 회차 디렉터리를 지운다 → 지운 회차 이름 목록 (T-4-07).

    회차당 약 271MB 다. 안 지우면 디스크가 단조증가한다 — 1인 로컬이라 아무도
    안 보다가 어느 날 맥북이 꽉 찬다.

    **`남길회차` 가 0 이하면 예외다.** `0` 은 "전부 지워라" 가 아니라 설정이 비었다는
    뜻일 가능성이 훨씬 높다 — 이 저장소가 네 번 막은 "빈 값이 전량이 되는 경로"의
    삭제판이다. `보호` 로 지정한 회차(지금 돌고 있는 회차)는 절대 지우지 않는다.
    """
    남길회차 = int(남길회차)
    if 남길회차 < 1:
        raise ValueError(f"--keep-runs 는 1 이상이어야 한다 (받은 값 {남길회차}) — "
                         "0 은 '전부 지워라' 가 아니다")
    if not os.path.isdir(캐시루트):
        return []

    항목 = []
    for 이름 in os.listdir(캐시루트):
        경로 = os.path.join(캐시루트, 이름)
        # 심링크는 따라가지 않는다 — 링크를 지우면 링크 대상이 사라질 수 있다.
        if os.path.islink(경로) or not os.path.isdir(경로):
            continue
        항목.append((os.path.getmtime(경로), 이름, 경로))
    항목.sort(key=lambda t: t[0], reverse=True)   # 최신 먼저

    보호세트 = {보호} if 보호 else set()
    남긴수 = sum(1 for _, 이름, _ in 항목 if 이름 in 보호세트)
    지운것 = []
    for _, 이름, 경로 in 항목:
        if 이름 in 보호세트:
            continue
        if 남긴수 < 남길회차:
            남긴수 += 1
            continue
        try:
            shutil.rmtree(경로)
            지운것.append(이름)
        except OSError as e:
            # 지우기 실패는 회차를 죽일 일이 아니다. 다만 **조용히 넘기지 않는다** —
            # 디스크가 왜 안 줄었는지 나중에 알 수 있어야 한다.
            말하기(f"[경고] 오래된 캐시 회차를 못 지웠다({이름}): {type(e).__name__}: {e}")
    return 지운것


def 한장받기(url, 저장경로, *, 백오프=기본_백오프, 타임아웃=기본_타임아웃) -> tuple:
    """한 장을 받아 캐시에 쓴다 → `(성공여부, 사유)`.

    이미 캐시에 있으면 **받지 않는다** — 271MB 재다운로드를 막는 것이 캐시의 존재 이유다.

    재시도는 지수 백오프 3회(0.3 / 0.6 / 0.9초). **404 는 즉시 포기한다** — 실측 25장이
    3회 뒤에도 영구 404 라 재시도가 시간만 먹는다. 실패는 사유를 들고 돌아온다.
    **예외를 조용히 삼키지 않는다** — 잡은 예외는 전부 사유 문자열이 되어 장에 적힌다.
    Phase 3 의 CR-01~03 이 전부 "못 본 것을 0건으로 적은" 같은 계열의 병이었다.
    """
    try:
        if os.path.exists(저장경로) and os.path.getsize(저장경로) > 0:
            return True, "캐시"
    except OSError as e:
        말하기(f"[경고] 캐시 확인 실패({저장경로}): {type(e).__name__}: {e}")

    허용, 거부사유 = 허용URL인가(url)
    if not 허용:
        return False, 거부사유

    마지막사유 = "알 수 없는 실패"
    총시도 = len(백오프) + 1
    for 시도 in range(총시도):
        try:
            요청 = urllib.request.Request(url, headers={"User-Agent": 사용자에이전트})
            with urllib.request.urlopen(요청, timeout=타임아웃) as 응답:
                본문 = 응답.read()
            if not 본문:
                마지막사유 = f"응답이 0바이트다 ({len(백오프)}회 재시도)"
            else:
                os.makedirs(os.path.dirname(저장경로) or ".", exist_ok=True)
                tmp = 저장경로 + ".tmp"
                with open(tmp, "wb") as f:
                    f.write(본문)
                os.replace(tmp, 저장경로)
                return True, ""
        except urllib.error.HTTPError as e:
            if e.code == 404:
                # 영구다. "3회 재시도" 라고 적으면 안 한 일을 했다고 적는 것이다.
                return False, "HTTP 404 (재시도 무의미 — 영구)"
            마지막사유 = f"HTTP {e.code} ({len(백오프)}회 재시도)"
        except urllib.error.URLError as e:
            마지막사유 = f"연결 실패: {e.reason} ({len(백오프)}회 재시도)"
        except OSError as e:
            마지막사유 = f"{type(e).__name__}: {e} ({len(백오프)}회 재시도)"
        if 시도 < len(백오프):
            time.sleep(백오프[시도])
    return False, 마지막사유


def 호스트이름(url) -> str:
    """실패 집계용 호스트. 못 뽑으면 `(알수없음)` — 빈 문자열로 접지 않는다."""
    try:
        return (urllib.parse.urlsplit(str(url)).hostname or "(알수없음)").lower()
    except ValueError:
        return "(알수없음)"


def 전부받기(상품들: list, 캐시루트: str, 회차: str, 작업자수: int) -> tuple:
    """장 전체를 병렬로 받는다 → `(성공수, 실패수, 호스트별실패)`.

    실패한 장은 `판정: "미판정"` + 사유로 남는다. **빈 값으로 접지 않는다** —
    404 20장이 한 상품(실측 ri=39)에 몰려 있어서, 흡수하면 그 상품이
    "제품 0장 + 배너 0장" 으로 조용히 보인다.
    """
    일감 = []
    for 상품순번, 상품 in enumerate(상품들):
        for 장 in 상품.get("장") or []:
            일감.append((상품, 장,
                        원본경로(캐시루트, 회차, 상품순번, 장["순번"])))
    if not 일감:
        return 0, 0, {}

    성공, 실패, 호스트별 = 0, 0, {}
    작업자수 = max(1, int(작업자수))
    with concurrent.futures.ThreadPoolExecutor(max_workers=작업자수) as 풀:
        미래 = {풀.submit(한장받기, 장["url"], 경로): (상품, 장)
              for 상품, 장, 경로 in 일감}
        for f in concurrent.futures.as_completed(미래):
            상품, 장 = 미래[f]
            try:
                받음, 사유 = f.result()
            except Exception as e:
                # 스레드에서 올라온 예상 밖 예외도 **사유를 들고** 장에 적힌다.
                받음, 사유 = False, f"{type(e).__name__}: {e}"
            if 받음:
                성공 += 1
                장["사유"] = None
                continue
            실패 += 1
            장["판정"] = banner.미판정
            장["사유"] = 사유
            호스트 = 호스트이름(장["url"])
            호스트별[호스트] = 호스트별.get(호스트, 0) + 1
    return 성공, 실패, 호스트별


def 상품별미판정반영(상품들: list) -> int:
    """미판정 장을 가진 상품에 `스킵사유: "판정불가"` 를 적는다 → 그런 상품 수.

    **흡수 금지의 상품층 집행이다.** 장에만 사유를 적고 상품을 건드리지 않으면,
    화면은 그 상품을 멀쩡한 상품으로 보여 준다. `webapp.banner.제품이미지목록` 이
    미판정 장으로 한 번 더 막지만, 두 층이 같이 서야 "조용히 통과"가 안 생긴다.

    **판정 실패의 기준은 `미판정` 이 아니라 `미판정 + 사유` 다.** 판정 자체는 04-04 가
    얹으므로, 그 전까지는 멀쩡히 내려받은 장도 `미판정` 이다(사유는 `None`). 사유 없는
    미판정을 실패로 세면 04-03 단계에서 전 상품이 '판정불가' 가 된다 — 실패는 **사유를
    들고 오는 것**이라는 이 파일의 규약이 그대로 판별식이 된다.
    """
    센것 = 0
    for 상품 in 상품들:
        if 상품.get("스킵사유"):
            센것 += 1
            continue
        미판정장 = [장 for 장 in (상품.get("장") or [])
                 if 장.get("판정") == banner.미판정 and 장.get("사유")]
        if not 미판정장:
            continue
        상품["스킵사유"] = "판정불가"
        상품["사유"] = (f"판정 못 한 장 {len(미판정장)}/{len(상품.get('장') or [])} — "
                     f"첫 사유: {미판정장[0].get('사유')}")
        센것 += 1
    return 센것


# ── Pillow 특징 · 썸네일 · 무내용 장 규칙 (T-4-08 / Pitfall 1) ──────────────

# 썸네일은 **높이**를 고정한다. 가로폭 고정이 아니다 — 검수 스트립에서 한 줄의 세로
# 크기가 일정해야 "3초 훑기" 가 성립한다(`stitch.py` 의 `resize_to_width` 와 반대 축).
썸네일높이 = 200


def 무내용인가(w, h, 종횡비상한, 짧은변하한) -> bool:
    """구분선·슬라이스 잔재인가. `긴변/짧은변 >= 상한` **또는** `짧은변 <= 하한`.

    ⚠️ **이것은 배너 판정이 아니다** (D-10 · Pitfall 1). 세로로 긴 상세 원본을 잘라
    만든 슬라이스와 구분선을 빼는 규칙이고, 그게 전부다.

    **배너는 오히려 세로로 길다** — 실측 배너 9장의 중앙 종횡비가 0.89 다. "넓고
    납작하면 배너" 는 실측상 **정반대**이고, 그 직관으로 임계를 잡으면 실측 코퍼스에서
    전원 미탐이 난다. 이 규칙으로 배너를 잡으려 들지 마라. 배너/제품 판정은 04-04 의
    OCR + 어휘군이 한다.

    종횡비를 `긴변/짧은변` 으로 잰다(`w/h` 가 아니다) — 그래야 가로 구분선과 세로
    구분선이 같은 규칙에 걸린다. 배너(0.89 → 1.12)는 어느 쪽으로 재도 6.0 근처에도
    못 간다.

    **치수를 모르면 무내용이 아니다.** 그건 `미판정` 이다 — 못 본 것을 "버려도 되는
    것" 으로 접는 순간 404 흡수와 같은 병이 된다.
    """
    try:
        w = int(w or 0)
        h = int(h or 0)
    except (TypeError, ValueError):
        return False
    if w <= 0 or h <= 0:
        return False
    짧은변, 긴변 = min(w, h), max(w, h)
    if 짧은변 <= int(짧은변하한):
        return True
    return (긴변 / 짧은변) >= float(종횡비상한)


def 무내용사유(w, h, 종횡비상한, 짧은변하한):
    """무내용이면 **어느 규칙이 걸렸는지** 문자열로, 아니면 `None`.

    `무내용인가` 와 **같은 순서**로 본다(짧은변 먼저, 종횡비 나중). 두 함수가 다른
    순서를 보면 "무내용이라는데 사유가 딴소리" 가 된다 — 사유가 거짓이 되는 순간
    사람이 화면을 안 믿는다.

    사유 문자열의 정본이 여기 하나다. `전부특징` 과 `전부판정` 이 둘 다 이 함수를
    부른다 — 같은 판정에 두 가지 문구가 남으면 04-06 화면이 둘을 다른 것으로 센다.
    """
    if not 무내용인가(w, h, 종횡비상한, 짧은변하한):
        return None
    if int(w or 0) and int(h or 0) and min(int(w), int(h)) <= int(짧은변하한):
        return f"무내용(짧은변) {w}x{h}"
    return f"무내용(종횡비) {w}x{h}"


def 특징과썸네일(원본경로, 썸네일저장경로, *, 썸높이=썸네일높이) -> tuple:
    """원본 한 장 → `(특징 dict | None, 사유)`.

    **`PIL` 은 여기서 지연 import 한다.** 모듈 최상단에 두면 `.venv-web` 으로 도는
    `webapp/tests/test_banner_scan.py` 가 이 파일을 로드할 때 ImportError 로 죽는다
    (웹앱 venv 에는 Pillow 가 없는 것이 설계다 — D-19). 04-04 의 Vision import 도
    같은 이유로 `ocr()` 안쪽이어야 한다.

    **`Image.MAX_IMAGE_PIXELS` 기본 제한을 끄지 않는다** (decompression bomb ·
    ASVS V12 · T-4-08). 외부 CDN 바이트를 디코딩하는 자리다. `DecompressionBombError`
    는 잡아서 **그 장만** 미판정으로 남기고 프로세스는 계속 간다 — 한 장 때문에
    회차 전체가 죽으면 안 된다. 실측 최대가 4096x3072(12.6M px)라 기본 한계
    (89M px)까지 여유가 크므로 평상시 마찰은 0 이다.

    numpy 를 쓰지 않는다 — `.venv` 에 없고 Pillow 내장으로 전부 된다
    (`entropy()` · `histogram()`).
    """
    from PIL import Image, UnidentifiedImageError   # noqa: PLC0415 (지연 import 는 의도다)

    try:
        with Image.open(원본경로) as im:
            # **`draft()` 보다 먼저 치수를 읽는다.** draft 는 `im.size` 를 바꾼다 —
            # 순서가 뒤집히면 산출물의 w·h 가 축소본 치수가 되고, 무내용 규칙이
            # 엉뚱한 숫자로 돌아간다.
            원본w, 원본h = im.size
            # JPEG 디코딩 **단계에서** 축소한다. 891장 5.7초 vs draft 없이 수 배
            # (RESEARCH §Don't Hand-Roll). resize 앞에 두는 것이 요점이다.
            im.draft("RGB", (400, 400))
            작업본 = im.convert("RGB")
    except Image.DecompressionBombError as e:
        return None, f"이미지가 너무 크다: {e}"
    except UnidentifiedImageError:
        return None, "이미지를 알아볼 수 없다 (디코딩 실패)"
    except (OSError, ValueError) as e:
        return None, f"이미지 디코딩 실패: {type(e).__name__}: {e}"

    특징 = {"w": int(원본w), "h": int(원본h),
          "엔트로피": None, "단색비율": None, "썸네일": None}
    try:
        특징["엔트로피"] = round(float(작업본.entropy()), 4)
        히스 = 작업본.convert("L").histogram()
        총합 = sum(히스)
        특징["단색비율"] = round(max(히스) / 총합, 4) if 총합 else None
    except (OSError, ValueError) as e:
        # 치수는 읽었는데 픽셀 통계가 안 나온 경우. **빈 값으로 접지 않는다.**
        return None, f"특징 계산 실패: {type(e).__name__}: {e}"

    try:
        # **키우지 않는다.** 구분선(실측 1200x40)을 높이 200 에 맞추면 6000x200 으로
        # **원본보다 커진다** — 정보는 하나도 안 늘고 바이트만 는다. 원본보다 낮으면
        # 원본 높이를 그대로 쓴다. 검수 스트립의 "한 줄 높이 일정" 은 상한선 얘기다.
        실제높이 = max(1, min(int(썸높이), 작업본.height))
        폭 = max(1, round(작업본.width * 실제높이 / max(1, 작업본.height)))
        썸 = 작업본.resize((폭, 실제높이), Image.LANCZOS)
        os.makedirs(os.path.dirname(썸네일저장경로) or ".", exist_ok=True)
        tmp = 썸네일저장경로 + ".tmp"
        썸.save(tmp, "WEBP")
        os.replace(tmp, 썸네일저장경로)
        # **파일명만 싣는다.** 경로를 실으면 04-06 의 경로 탈출 방어가 무너진다 —
        # 그 방어는 "서버가 정수 인덱스로 경로를 만든다"에 기대고 있다.
        특징["썸네일"] = os.path.basename(썸네일저장경로)
    except (OSError, ValueError) as e:
        # 썸네일 실패는 **판정 불가가 아니다.** 치수·통계는 이미 읽었고 판정은 돈다.
        # 검수 화면의 그 칸만 빈다. 그래서 미판정으로 내리지 않고 경고만 남긴다.
        말하기(f"[경고] 썸네일 생성 실패({원본경로}): {type(e).__name__}: {e}")
    return 특징, ""


def 전부특징(상품들: list, 캐시루트: str, 썸루트: str, 회차: str,
          종횡비상한, 짧은변하한) -> tuple:
    """받아 둔 원본에서 특징·썸네일을 만든다 → `(특징수, 썸네일수, 무내용수)`.

    이미 사유를 들고 있는 장(다운로드 실패·URL 거부)은 원본이 없으므로 건너뛴다.

    **여기서 내리는 판정은 `무내용` 하나뿐이다.** 배너/제품은 04-04 의 OCR +
    어휘군이 한다 — 그래서 04-04 가 올라오기 전까지 이 스크립트는 정상 실행에서도
    `판정완료` 가 무내용 장 수만큼만 나오고, 무내용이 한 장도 없으면 exit 3 이다.
    **그게 정직한 신호다** — 파이프라인이 아직 미완이라는 뜻이고, 그 상태의 산출물로
    Phase 5 를 돌리면 안 된다.
    """
    특징수, 썸수, 무내용수 = 0, 0, 0
    for 상품순번, 상품 in enumerate(상품들):
        for 장 in 상품.get("장") or []:
            if 장.get("사유"):
                continue        # 못 받은 장. 원본이 없다
            특징, 사유 = 특징과썸네일(
                원본경로(캐시루트, 회차, 상품순번, 장["순번"]),
                썸네일경로(썸루트, 회차, 상품순번, 장["순번"]))
            if 특징 is None:
                장["판정"] = banner.미판정
                장["사유"] = 사유
                continue
            장["w"], 장["h"] = 특징["w"], 특징["h"]
            # 04-04 의 판정이 쓸 값. 산출물 계약에 없던 칸이지만 **더하는 것은 안전하다**
            # (`banner.py` 는 필요한 키만 읽는다). 여기서 계산해 두면 04-04 가 891장을
            # 다시 디코딩하지 않는다.
            장["엔트로피"] = 특징["엔트로피"]
            장["단색비율"] = 특징["단색비율"]
            장["썸네일"] = 특징["썸네일"]
            특징수 += 1
            if 특징["썸네일"]:
                썸수 += 1
            사유_무내용 = 무내용사유(특징["w"], 특징["h"], 종횡비상한, 짧은변하한)
            if 사유_무내용:
                장["판정"] = banner.무내용
                장["사유"] = 사유_무내용
                무내용수 += 1
    return 특징수, 썸수, 무내용수


# ── OCR 2패스 (D-10 · Pitfall 4 · T-4-13) ───────────────────────────────────
#
# **배너를 배너이게 하는 것은 픽셀 모양이 아니라 글자다**(D-10). 위 `무내용인가` 는
# 구분선을 빼는 기하 규칙이고, 배너/제품을 가르는 것은 여기서 읽는 글자다.
#
# 네트워크 0 · 토큰 0 · 크레딧 0 — macOS 온디바이스 Vision 이 전부 로컬에서 돈다.


class Vision미설치(RuntimeError):
    """`pyobjc-framework-Vision` 이 없다. `main` 이 잡아 **exit 4** 로 내린다.

    조용히 넘어가지 않는다. 미설치를 "OCR 결과 0줄" 로 접으면 전 장이 `제품` 으로
    판정되고, 그 목록이 그대로 Phase 5 입력이 된다 — 중국 점포 워터마크가 붙은
    이미지가 스마트스토어에 올라간다. **미설치는 실패여야 한다**(04-01 이 세운 규율:
    `pytest.importorskip` 으로 덮지 않는 것과 같은 선이다).
    """


def _비전():
    """`Vision` · `Quartz` · `NSURL` 을 **지연 import** 한다 → `(Vision, Quartz, NSURL)`.

    **모듈 최상단에 두지 마라.** `.venv-web` 에는 이 패키지들이 없는 것이 설계이고
    (D-19), `webapp/tests/test_banner_scan.py` 가 이 파일을 `importlib` 로 로드하므로
    최상단 import 는 그 파일 전체를 collect 단계에서 죽인다. 04-03 이 `PIL` 에서
    똑같은 일을 실제로 겪었다(그 플랜의 Deviations 1).
    """
    try:
        import Vision                      # noqa: N813  (pyobjc 모듈명 그대로)
        import Quartz
        from Foundation import NSURL
    except ImportError as e:
        raise Vision미설치(
            "⛔ pyobjc-framework-Vision 이 없다 — .venv 에 설치해라 "
            f"(.venv/bin/pip install pyobjc-framework-Vision==12.2.2) [{e}]") from e
    return Vision, Quartz, NSURL


# 2패스 정의 — **순서가 결과를 바꾼다**(Pitfall 4). 두 번째 값이 그대로
# `setUsesLanguageCorrection_` 에 들어간다.
OCR_패스 = (
    # 한국어 패스: setUsesLanguageCorrection_(True) — 번역된 상세가 대다수다
    (("ko-KR", "en-US"), True),
    # 중국어 패스: setUsesLanguageCorrection_(False)
    #   **켜면 한자를 한글로 보정해 버린다**(실측). 끄는 것이 이 패스의 존재 이유다.
    (("zh-Hans", "en-US"), False),
)


def ocr(경로: str, 언어: tuple, 교정: bool = True, *, revision: int) -> list:
    """이미지 1장 → 인식된 문자열 줄 목록.

    **`revision` 에 기본값을 두지 않는다 — 부르는 쪽이 반드시 준다.** 정본은
    `settings.banner_vision_revision` 이고 `--vision-revision` 으로 들어온다. 기본값을
    여기 박으면 산출물의 `판정규칙.vision_revision` 과 실제 동작의 출처가 갈라진다.

    **`setRevision_` 을 반드시 건다**(T-4-13 · D-10 · D-02). 현재 기본 리비전은 3이고
    지원은 [1,2,3] 이다(macOS 26.5.1 실측). 안 박으면 OS 업데이트가 기본 리비전을
    올리는 날 판정이 **조용히** 바뀐다 — D-02 가 걱정한 "회차마다 흔들린다"가
    되살아날 수 있는 **유일한 경로**다. 그래서 값이 산출물에도 같이 실린다.

    **실패는 예외로 올린다. 빈 리스트로 접지 마라** — 빈 OCR 결과("글자가 없다")와
    OCR 실패("못 읽었다")는 다른 사실이다. 접는 순간 못 읽은 배너가 `제품` 이 된다
    (Pitfall 2 와 같은 계열의 흡수다).
    """
    Vision, Quartz, NSURL = _비전()
    url = NSURL.fileURLWithPath_(os.path.abspath(경로))
    src = Quartz.CGImageSourceCreateWithURL(url, None)
    if src is None:
        raise ValueError(f"이미지를 열 수 없다: {경로}")
    img = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)
    if img is None:
        raise ValueError(f"이미지 디코딩 실패: {경로}")

    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRevision_(int(revision))          # ← 협상 불가 (T-4-13)
    req.setRecognitionLanguages_(list(언어))
    req.setRecognitionLevel_(0)              # 0 = accurate (1 = fast)
    req.setUsesLanguageCorrection_(bool(교정))
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(img, None)
    ok, err = handler.performRequests_error_([req], None)
    if not ok:
        raise RuntimeError(f"Vision 요청 실패: {err}")
    줄들 = []
    for obs in (req.results() or []):
        후보 = obs.topCandidates_(1)
        if 후보 and len(후보):
            줄들.append(str(후보[0].string()))
    return 줄들


def ocr_2패스(경로: str, *, revision: int) -> list:
    """한국어 패스 + 중국어 패스. **둘 다 필요하다**(Pitfall 4).

    `recognitionLanguages` 는 우선순위 목록이고 **첫 언어가 강하게 지배한다.**
    실측 4줄 — 같은 이미지를 언어 순서만 바꿔 읽은 결과다:

      ko-KR 먼저  → `3층 대형 69`      (정답)
      zh-Hans 먼저 → `3 ［H 69`         (한글을 못 읽는다)
      ko-KR 먼저  → `t0&⅞35cm`         (한자를 못 읽는다)
      zh-Hans 먼저 → `加深35cm`          (정답)

    **중국어 패스는 언어교정을 끈다.** 켜면 한자를 한글로 보정해 버린다(실측).

    한 패스로 끝내면 🔴 중국어원본 상품의 배너를 통째로 놓친다. 그 미탐은 화면에
    "배너 0장" 으로 보여서 눈에 띄지도 않는다.

    ⚠️ **한자 개수를 신호로 쓰지 마라.** 중국어 패스를 한국어 이미지에 돌리면 한글을
    한자로 오인식한다(실측 891장 중 446장에서 잡음 한자 검출, 상위 글자가
    `人米早号亼日厘些`). 판정에 쓰는 것은 **키워드 문자열 매칭뿐**이다 — 잡음이
    `品质保证` 같은 정확한 다자 구절을 만들 확률은 매우 낮다.
    """
    줄들 = []
    for 언어, 교정 in OCR_패스:
        줄들 += ocr(경로, 언어, 교정, revision=revision)
    return 줄들


# ── 어휘군 14군 — 배너 판정의 본체 (D-10 · Pattern 4 · T-4-14) ──────────────
#
# **어휘 목록 자체는 설정이 아니라 이 파일에 산다.** `settings` 에 200개 문자열을
# 넣으면 `workspace.toml` 이 회귀 픽스처와 다른 버전을 들고 돌 수 있고, 그러면
# "어느 규칙으로 낸 숫자인가"를 산출물만 보고는 영영 모른다. 대신 버전 표기를
# `--lexicon-version` 으로 받아 산출물 `판정규칙.어휘군버전` 에 싣는다(T-4-14) —
# 규칙이 바뀌면 숫자도 같이 바뀌었다는 사실이 남는다.
#
# ⚠️ **과적합이다**(Pitfall 3). 앞 8군은 리서처 라벨 배너 9장의 OCR 을 보고 골랐고,
#    2026-09-22 에 더한 6군은 **용팀장이 전수 검수에서 찍은 미탐 11장의 OCR** 을 보고
#    골랐다. 둘 다 "놓친 장을 보고 키워드를 만든" 것이라 **같은 세트로 다시 잰 숫자는
#    게이트 통과 근거가 아니다**(T-4-29). 진짜 측정은 다음 회차(out-of-sample)다.
#    `04-GATE.md` §8 에 in-sample 재측정 숫자와 그 한계를 같이 적어 뒀다.
#
# ⚠️ **한국어와 중국어를 항상 둘 다 건다.** `imageTranslated='0'` 을 "이미지가
#    중국어다"로 읽지 마라(Pitfall 6) — 실측상 `'0'` 인 10상품의 상세 이미지가
#    거의 전부 한국어였다. 불사자가 수집 시점에 이미 번역해 CDN 에 올린다.
#
#    🔴 2026-09-22 실측이 이 경고를 훨씬 세게 만들었다. 944장 전량을 OCR 해 세 보니
#    **중국어 항목 35개 중 실제로 발화한 것은 3개**(`客服`·`使用说明`·`淘宝`)뿐이고,
#    그 3개가 맞춘 "사람이 배너라 한 장"은 **0장**이다(`淘宝` 11발화는 전부
#    D-08 로 스킵된 워터마크 상품 안이다). `상세상태=중국어원본` 상품이 세트의 68%인데도
#    그렇다 — 불사자가 CDN 에 올리는 시점에 이미 번역해 두기 때문이다.
#    **중국어 절반은 여전히 실제 코퍼스로 검증되지 않았다.** 그렇다고 지우지 마라 —
#    번역 전 원본이 걸리는 회차가 언제든 올 수 있고, 지우면 그때 통째로 놓친다.
#
# ⚠️ **2글자 이하 ASCII 토큰을 넣지 마라.** OCR 잡음 문자열에 우연히 걸린다
#    (개발 중 `"qr"` 이 `PANPAN physical shooting` 에 실제로 오탐). 최소 3글자다.
#    `test_어휘군_한중` 이 이 규칙을 기계로 집행한다.
#    (한글 2글자는 이 규칙 밖이다. `티몰` 같은 고유명사는 OCR 잡음이 우연히 만들 확률이
#     매우 낮고, 실측 944장에서 오탐 0이었다.)
어휘군 = {
    "공장직판": ["공장 직판", "공장직판", "factory direct", "제조업체", "직접 판매", "직접판매",
               "공장 직접", "직공구", "厂家直销", "厂家直供", "源头工厂", "工厂直销"],
    "품질보증": ["품질 보증", "품질보증", "품질 보장", "품질보장", "정품 보증", "정품보증",
               "quality guarantee", "고품질의 재료", "양심적",
               "品质保证", "质量保证", "正品保证", "假一赔十"],
    "배송":    ["무료 배송", "무료배송", "즉시 배송", "즉시배송", "당일 발송", "빠른 배송",
               "free shipping", "영업일 이내에 발송", "包邮", "顺丰包邮", "当天发货", "48小时发货"],
    "반품교환": ["반품", "교환 할", "환불", "이유가 없습니다", "무이자 할부",
               "七天无理由", "无理由退换", "退换货", "退款", "分期免息"],
    "경품이벤트": ["경품", "사은품", "이벤트", "활동 시간", "활동 규칙", "참여방식", "위안",
                "선물을 드립니다", "인기 판매", "赠品", "活动时间", "限时", "秒杀", "优惠券", "满减"],
    # 2026-09-22: `방문 서비스`·`24시간 서비스`·`전국 방문` 을 더했다.
    # 근거 = 용팀장 미탐 `zz…:14` "전국 방문 서비스 / 현지 24시간 서비스, 지역 밖 48시간".
    "AS안내":  ["애프터서비스", "after sale", "고객센터", "구매 안내", "사용 및 유지", "유지 보수",
               "방문 서비스", "방문서비스", "24시간 서비스", "전국 방문", "출장 수리",
               "售后服务", "客服", "购买须知", "使用说明", "上门服务", "全国联保"],
    "핵심셀링": ["핵심 판매 포인트", "core selling point", "selling point", "서비스 보장",
               "우리를 선택", "核心卖点", "为什么选择我们", "服务保障"],
    "연락처":  ["위챗", "微信", "淘宝", "taobao", "aliexpress", "扫码", "关注", "公众号", "1688"],

    # ── 여기부터 2026-09-22 신설 6군. 전부 용팀장 미탐 11장의 OCR 이 근거다 ──────
    # 각 군 옆의 `근거:` 는 `banner_labels.json` 의 `용팀장라벨.미탐본문` 을 가리킨다.
    # **in-sample 이다** — 이 군들이 잡는 장은 지금 코퍼스에서 각각 1장(자기 근거)뿐이다.

    # 근거: "NOTICE / 구매자 안내 / 01 구매에 관해", "사용자 정의 지침 / 다음을 자세히 읽어주십시오"
    "구매안내": ["구매자 안내", "구매에 관해", "구매 전 안내", "주문 전 안내", "자세히 읽어",
               "꼭 읽어보", "notice",
               "购买前必读", "下单须知", "温馨提示", "注意事项"],

    # 근거: "표시가격은 한 마리의 가격입니다. 한 쌍이 필요하다면 수량 2를 찍으세요"
    "가격안내": ["표시가격", "표시 가격", "개당 가격", "가격입니다", "가격 안내",
               "单价说明", "拍下前"],

    # 근거: "특허인증은 검사인증이 있어야 안전하다 / 검사보고서 / TEST ROPORT"
    "인증검사": ["검사보고서", "검사 보고서", "시험성적서", "특허인증", "특허 인증", "test report",
               "质检报告", "检测报告", "专利认证", "认证证书"],

    # 근거: "티몰 라스트 / 더블 TOP1 / 데이터로 말하다 / 티몰 리스트"
    "랭킹수상": ["티몰", "베스트셀러", "best seller", "top1", "판매 1위", "판매량 1위",
               "天猫", "排行榜", "热销榜", "销量第一", "爆款"],

    # 근거: "공익의 아기 / 매 거래마다 공익 프로그램에 기부금이 송금된다"
    "공익기부": ["공익 프로그램", "공익 활동", "기부금", "기부합니다",
               "公益项目", "捐赠", "爱心"],

    # 근거: "페인팅 프로젝터 / 우리는 전문가입니다 / 그림 프로젝터의 개척자"
    "브랜드소개": ["우리는 전문가", "전문가입니다", "개척자", "브랜드 이야기", "브랜드 스토리",
                "旗舰店", "专卖店", "品牌故事", "专业制造", "工厂实力"],
}

# 🔴 **버린 후보를 여기 남긴다 — 다시 발명하지 않으려고.**
# 944장 전량 OCR 위에서 항목별로 재 봤더니(`04-GATE.md` §8-2) 아래 셋은
# **미탐을 하나도 못 풀면서 오탐만 늘렸다.** 어휘군은 넓힐수록 좋은 게 아니다.
#   · `맞춤 제작`   → 새로 3장 잡고 미탐 해소 0 (전부 사람이 제품이라 한 장)
#   · `주문 제작`   → 새로 2장 잡고 미탐 해소 0
#   · `사용자 정의` → 새로 2장 잡아 미탐 1 해소 · 새 오탐 1. `자세히 읽어` 가
#                    같은 장을 오탐 0 으로 잡으므로 이쪽을 골랐다
_버린후보_2026_09_22 = ("맞춤 제작", "주문 제작", "사용자 정의", "맞춤제작", "주문제작",
                     "定制", "定做", "量身定制")

# 매칭용 소문자 사본. 대소문자만 다른 실측 표본이 있다 —
# 라벨 배너 `zz12:1` 의 OCR 첫 줄이 `Core selling point ... FACTORY DIRECT SALES` 다.
_어휘군소문자 = {군: tuple(항목.lower() for 항목 in 항목들)
              for 군, 항목들 in 어휘군.items()}


def 어휘군걸림(줄들) -> list:
    """OCR 줄 목록 → 걸린 어휘군 이름들(정의 순서). 안 걸리면 빈 리스트.

    줄을 `" / "` 로 잇고 한 번에 본다. 구분자에 `/` 를 쓰는 이유는 어휘군 항목 중
    `/` 를 담은 것이 하나도 없어서다 — 줄 경계를 넘는 우연한 매칭이 구조적으로
    생기지 않는다.

    **한자 개수를 세지 않는다.** 중국어 패스를 한국어 이미지에 돌리면 한글을
    한자로 오인식한다(실측 891장 중 446장). 판정에 쓰는 것은 키워드 문자열
    매칭뿐이고, 잡음이 `品质保证` 같은 정확한 다자 구절을 만들 확률은 매우 낮다.
    """
    본문 = " / ".join(str(줄) for 줄 in (줄들 or [])).lower()
    if not 본문.strip():
        return []
    return [군 for 군, 항목들 in _어휘군소문자.items()
            if any(항목 in 본문 for 항목 in 항목들)]


# ── 장별 판정 · 상품별 스킵 (D-06 · D-07 · D-08 · D-09 · BANNER-05) ─────────

def 판정대상인가(장: dict) -> bool:
    """이 장을 OCR 해서 판정할 것인가.

    **못 받은 장은 건드리지 않는다.** 판별식은 `미판정` 이 아니라 **`미판정 + 사유`**
    다(04-03 규약) — 사유를 들고 오는 미판정이 실패다. 실패한 장을 여기서 다시
    판정하면 404 가 `제품` 으로 흡수된다(Pitfall 2).

    반대로 `무내용` 으로 이미 찍힌 장은 **판정 대상이다.** 어휘군이 무내용보다
    먼저 보기 때문이다 — 글자가 박힌 납작한 배너를 "구분선" 으로 접으면 사유가
    거짓이 되고, 그 장이 제거 대상에서 빠지는 게 아니라 **잘못된 이유로** 빠진다.
    """
    if 장.get("판정") == banner.미판정 and 장.get("사유"):
        return False
    return bool(장.get("w")) and bool(장.get("h"))


def 장판정(장: dict, 줄들, 종횡비상한, 짧은변하한) -> str:
    """OCR 줄을 받아 장 dict 의 `판정`·`사유` 를 확정한다 → 판정값.

    **순서가 중요하다** — 어휘군이 무내용보다 **먼저**다:
      ① 어휘군 1개 이상 → `배너`, 사유 `"어휘군:공장직판,품질보증"`
      ② 무내용 규칙     → `무내용`, 사유 `"무내용(종횡비) 1200x40"`
      ③ 나머지          → `제품`, 사유 `None`

    사유에 **OCR 원문을 싣지 않는다**(T-4-15). 어느 군에 걸렸는지만 적는다 —
    사람이 "왜 배너로 봤나" 를 읽기에 충분하고, 상세 텍스트가 로그·산출물로
    새지 않는다.
    """
    걸린군 = 어휘군걸림(줄들)
    if 걸린군:
        장["판정"] = banner.배너
        장["사유"] = "어휘군:" + ",".join(걸린군)
        return banner.배너
    사유_무내용 = 무내용사유(장.get("w"), 장.get("h"), 종횡비상한, 짧은변하한)
    if 사유_무내용:
        장["판정"] = banner.무내용
        장["사유"] = 사유_무내용
        return banner.무내용
    장["판정"] = banner.제품
    장["사유"] = None
    return banner.제품


def 전부판정(상품들: list, 캐시루트: str, 회차: str, 종횡비상한, 짧은변하한,
          *, revision: int) -> tuple:
    """받아 둔 원본을 OCR 해 장별 판정을 찍는다 → `(OCR한 장수, 배너, 제품, 무내용, OCR실패)`.

    **891장을 다시 디코딩하지 않는다** — 원본은 `원본경로(...)` 에 그대로 있고
    `w`·`h`·`엔트로피`·`단색비율` 은 04-03 이 이미 재 뒀다. 여기서는 글자만 읽는다.

    OCR 실패는 그 장만 `미판정` + 사유로 내린다. **빈 결과로 접지 마라** — 못 읽은
    장을 "글자가 없다" 로 접으면 그대로 `제품` 이 되고 Phase 5 입력이 된다.
    `Vision미설치` 는 여기서 잡지 않는다(그건 회차 전체의 실패다 → exit 4).
    """
    한장수, 배너수, 제품수, 무내용수, 실패수 = 0, 0, 0, 0, 0
    for 상품순번, 상품 in enumerate(상품들):
        for 장 in 상품.get("장") or []:
            if not 판정대상인가(장):
                continue
            원본 = 원본경로(캐시루트, 회차, 상품순번, 장["순번"])
            try:
                줄들 = ocr_2패스(원본, revision=revision)
            except Vision미설치:
                raise
            except Exception as e:
                장["판정"] = banner.미판정
                장["사유"] = f"OCR 실패: {type(e).__name__}: {e}"
                실패수 += 1
                continue
            한장수 += 1
            판정 = 장판정(장, 줄들, 종횡비상한, 짧은변하한)
            if 판정 == banner.배너:
                배너수 += 1
            elif 판정 == banner.제품:
                제품수 += 1
            else:
                무내용수 += 1
    return 한장수, 배너수, 제품수, 무내용수, 실패수


def 제품이미지채우기(상품: dict) -> int:
    """`제품` 으로 판정된 장을 **원래 순서 그대로** Phase 5 입력 목록에 싣는다 → 장수.

    **개수 제한을 여기서 걸지 마라**(D-06). "10장을 넘으면 무엇을 버릴까" 는
    Phase 5 의 결정이고, 여기서 잘라 버리면 그 결정이 영영 불가능해진다.
    정렬도 하지 않는다 — 상세페이지는 위에서 아래로 읽는 하나의 문서다.

    스킵된 상품에도 채운다. 접근을 막는 것은 `webapp.banner.제품이미지목록` 의
    일이고(예외로 막는다), **목록을 비워서 막는 것이 아니다** — 빈 목록은
    "제품 이미지가 0장" 이라는 **다른 사실**을 말하게 된다.
    """
    상품["제품이미지"] = [{"순번": 장["순번"], "url": 장["url"]}
                     for 장 in (상품.get("장") or [])
                     if 장.get("판정") == banner.제품]
    return len(상품["제품이미지"])


def 제거율계산(상품: dict):
    """`(배너 + 무내용) / 판정완료`. 판정완료가 0이면 `None`("아직 모른다").

    **분모에 미판정을 넣지 마라.** 못 본 장이다. 넣으면 404 가 20장 몰린 상품
    (실측 ri=39)의 제거율이 인위적으로 낮아져 D-08 스킵을 빠져나간다.
    """
    배너무내용, 판정완료 = 0, 0
    for 장 in 상품.get("장") or []:
        판정 = 장.get("판정")
        if 판정 not in (banner.배너, banner.제품, banner.무내용):
            continue
        판정완료 += 1
        if 판정 in (banner.배너, banner.무내용):
            배너무내용 += 1
    if 판정완료 == 0:
        상품["제거율"] = None
        return None
    상품["제거율"] = round(배너무내용 / 판정완료, 3)
    return 상품["제거율"]


def 스킵규칙적용(상품들: list, 잔여하한: int, 제거율상한: float) -> dict:
    """D-07 · D-08 을 상품 단위로 건다 → 사유별 건수 dict.

    **이미 `스킵사유` 가 있는 상품을 덮지 않는다.** 먼저 들어간 것은 `판정불가`
    (미판정 장이 남았다 · 상세 미조회)이고, 그건 "배너를 빼고 나니 부족하다" 보다
    **더 강한 사실**이다 — 판정 자체를 못 했는데 제거율을 사유로 적으면 거짓말이다.

    **사람 판단 큐를 만들지 않는다**(D-09). 스킵은 사유 문자열 하나로 끝나고, 새
    상태값도 큐 파일도 없다. D-07·D-08 은 "애매하면 사람에게 묻는다" 가 아니라
    **"애매하면 그 상품을 건너뛴다"** 이다.
    """
    센것 = {banner.잔여부족: 0, banner.제거율초과: 0}
    for 상품 in 상품들:
        잔여 = 제품이미지채우기(상품)
        제거율 = 제거율계산(상품)
        if 상품.get("스킵사유"):
            continue                      # 판정불가가 더 강한 사실이다
        if 잔여 < int(잔여하한):
            상품["스킵사유"] = banner.잔여부족
            상품["사유"] = (f"배너를 빼고 남은 제품 이미지가 {잔여}장 — "
                         f"D-07 하한 {int(잔여하한)}장 미만")
            센것[banner.잔여부족] += 1
            continue
        if 제거율 is not None and 제거율 > float(제거율상한):
            상품["스킵사유"] = banner.제거율초과
            상품["사유"] = (f"제거율 {제거율:.1%} — D-08 상한 "
                         f"{float(제거율상한):.0%} 초과. 판정이 폭주한 신호다")
            센것[banner.제거율초과] += 1
    return 센것


# ── ① 조인 산출물 → 상품 · 장 골격 ──────────────────────────────────────────

def 상품골격(행: dict) -> dict:
    """조인 행 하나 → 산출물 상품 dict (RESEARCH §산출물 계약).

    **모르는 값은 `None` 이다.** 빈 문자열로 채우지 않는다 — `""` 는 "번호가 없다"는
    관측이고 `None` 은 "못 물어봤다"다(`bulsaja_scan.py` 의 `"사본": None` 규율).
    `스킵사유` 는 스킵이 아니어도 **반드시 키로 넣는다** — `banner.스킵사유읽기` 는
    키 부재를 예외로 본다(없는 것과 못 읽은 것을 같은 값으로 접지 마라).
    """
    dc = 행.get("uploadDetailContents")
    dc = dc if isinstance(dc, dict) else {}
    return {
        "판매자상품코드": 행.get("판매자상품코드"),
        "불사자코드": 행.get("불사자코드"),
        # 물갈이 사본이 게이트 분모를 부풀리지 않는 근거다(성공기준 4).
        # `bulsaja_scan.py` 가 `mode=full` 응답의 `productNo` 를 실어 준다.
        "타오바오상품번호": 행.get("타오바오상품번호"),
        # 판정 규칙을 여기서 재현하지 않는다 — Phase 3 `state.상세상태` 가 정본이다.
        "상세상태": state.상세상태(dc),
        "장수": 0,
        # null | "잔여부족" | "제거율초과" | "판정불가"
        "스킵사유": None,
        "사유": None,
        "제거율": None,
        "제품이미지": [],
        "장": [],
    }


def 장골격(장순번: int, url: str) -> dict:
    """아직 내려받기 전의 장. `판정` 은 `미판정` 에서 출발한다.

    **`제품` 에서 출발하지 않는다.** 기본값이 `제품` 이면 다운로드가 통째로 실패한
    회차가 "전부 제품 이미지" 로 보이고, 그 목록이 Phase 5 입력이 된다.
    """
    return {
        "순번": int(장순번),
        "url": url,
        "w": None,
        "h": None,
        "판정": banner.미판정,
        "사유": "아직 내려받지 않았다",
        "썸네일": None,
    }


def URL추출(행들: list) -> tuple:
    """조인 행 목록 → (상품 리스트, 총 장수, 상세 미조회 상품 수).

    `renderContent` 가 `None` 이면 `banner.상세이미지목록` 이 ValueError 를 올린다.
    그건 **미조회**(실측 194행 중 137행)이지 0장이 아니다 — 그 행을 통째로
    `스킵사유: "판정불가"` 로 적고 사유를 남긴다. **0장으로 접지 마라.**
    """
    상품들, 총장수, 미조회 = [], 0, 0
    for 행 in 행들:
        상품 = 상품골격(행)
        상품들.append(상품)
        dc = 행.get("uploadDetailContents")
        rc = (dc if isinstance(dc, dict) else {}).get("renderContent")
        try:
            urls = banner.상세이미지목록(rc)
        except ValueError as e:
            상품["스킵사유"] = "판정불가"
            상품["사유"] = "상세 미조회" if rc is None else f"상세를 읽지 못했다: {e}"
            미조회 += 1
            continue
        상품["장수"] = len(urls)
        상품["장"] = [장골격(i, u) for i, u in enumerate(urls)]
        총장수 += len(urls)
    return 상품들, 총장수, 미조회


# ── 집계 ────────────────────────────────────────────────────────────────────

def 집계내기(상품들: list) -> dict:
    """산출물 `집계` 칸. **판정별 수를 세기만 한다 — 규칙을 적용하지 않는다.**"""
    칸 = {"상품": len(상품들), "장": 0, "판정완료": 0, "미판정": 0,
         banner.배너: 0, banner.제품: 0, banner.무내용: 0, "스킵상품": 0}
    for 상품 in 상품들:
        if 상품.get("스킵사유"):
            칸["스킵상품"] += 1
        for 장 in 상품.get("장") or []:
            칸["장"] += 1
            판정 = 장.get("판정")
            if 판정 == banner.미판정:
                # **`미판정` 을 판정별 칸에도 더하지 않는다.** `banner.미판정` 의 값이
                # 문자열 "미판정" 이라 `칸[판정] += 1` 을 같이 돌리면 한 장이 두 번 세어진다
                # (실측: 장 2개인데 미판정 4). 미판정은 판정이 아니라 판정의 **부재**다.
                칸["미판정"] += 1
                continue
            칸["판정완료"] += 1
            if 판정 in (banner.배너, banner.제품, banner.무내용):
                칸[판정] += 1
    return 칸


def 인자만들기():
    """`argparse required=True` 를 쓰지 않는다 (`bulsaja_scan.py:291-299` 규약).

    argparse 가 직접 죽으면 사유가 stderr 로만 나가고 stdout 로그(=잡 로그·SSE 화면)에
    한 글자도 안 남는다. 사람이 화면에서 "왜 멈췄나" 를 읽을 수 있어야 한다.
    """
    ap = argparse.ArgumentParser(
        description="배너 판정 스캐너 — 크레딧 0 · 불사자 MCP 0회")
    ap.add_argument("--join", default="", help="직전 성공 bulsaja_scan 의 조인 산출물 JSON")
    ap.add_argument("--out", default="", help="산출물 JSON 경로")
    ap.add_argument("--run-dir", default="", help="회차 이름 (캐시·썸네일 하위 디렉터리)")
    ap.add_argument("--cache", default="", help="원본 이미지 캐시 루트")
    ap.add_argument("--thumbs", default="", help="썸네일 디렉터리 루트")
    ap.add_argument("--workers", type=int, default=폴백["workers"],
                    help="다운로드 스레드 수. 정본은 settings `banner_workers`")
    ap.add_argument("--vision-revision", type=int, default=폴백["vision_revision"],
                    help="Vision OCR revision. 정본은 settings `banner_vision_revision`")
    ap.add_argument("--blank-ar", type=float, default=폴백["blank_ar"],
                    help="무내용 장 종횡비 하한. **배너 판정이 아니다**")
    ap.add_argument("--blank-short-px", type=int, default=폴백["blank_short_px"],
                    help="무내용 장 짧은 변 상한(px). 위와 한 쌍이다")
    ap.add_argument("--skip-min-keep", type=int, default=폴백["skip_min_keep"],
                    help="D-07 잔여 제품 이미지 하한")
    ap.add_argument("--skip-max-removal", type=float, default=폴백["skip_max_removal"],
                    help="D-08 제거율 상한")
    ap.add_argument("--lexicon-version", default=폴백["lexicon_version"],
                    help="어휘군 버전 표기. 산출물 `판정규칙` 에 실린다")
    ap.add_argument("--keep-runs", type=int, default=폴백["keep_runs"],
                    help="원본 캐시를 남길 회차 수. 회차당 약 271MB")
    return ap


def main() -> int:
    인자 = 인자만들기().parse_args()
    시작 = time.time()

    # ① 필수 인자 — **네트워크도 디스크도 건드리기 전에** 본다.
    #    빈 대상이 조용히 '전량' 으로 미끄러지는 경로를 여기서 끊는다
    #    (웹앱 `jobs._build_argv` 의 ValueError 와 짝을 이루는 2층 방어).
    for 필수, 이름 in ((인자.join, "--join"), (인자.out, "--out"),
                      (인자.run_dir, "--run-dir"), (인자.cache, "--cache"),
                      (인자.thumbs, "--thumbs")):
        if not 필수:
            사유 = f"⛔ 배너 스캔에는 {이름} 이 반드시 있어야 한다"
            말하기(사유)
            오류말하기(사유)
            return 2

    # ② 조인 산출물 읽기
    try:
        with open(인자.join, encoding="utf-8") as f:
            조인문서 = json.load(f)
    except FileNotFoundError:
        사유 = f"⛔ 조인 산출물이 없다: {인자.join} — 빈 목록은 전량이 아니다"
        말하기(사유)
        오류말하기(사유)
        return 2
    except Exception as e:
        사유 = f"⛔ 조인 산출물을 읽지 못했다({인자.join}): {type(e).__name__}: {e}"
        말하기(사유)
        오류말하기(사유)
        return 2

    try:
        행들 = banner.상세보유행들(조인문서)
    except ValueError as e:
        사유 = f"⛔ 조인 산출물의 모양이 다르다: {e}"
        말하기(사유)
        오류말하기(사유)
        return 2

    if not 행들:
        사유 = ("⛔ 상세 보유 행이 0건이다 — **빈 목록은 전량이 아니다.** "
               "조인 스캔을 먼저 돌려라")
        말하기(사유)
        오류말하기(사유)
        return 2

    # ③ URL 추출 — 여기까지가 순수 파싱이다. 아직 네트워크에 한 바이트도 안 나간다.
    상품들, 총장수, 미조회상품 = URL추출(행들)
    말하기(f"[1/5] URL 추출 {총장수}장 (상품 {len(상품들)} · 상세 미조회 {미조회상품})")
    if 미조회상품:
        말하기(f"※ 상세 미조회 {미조회상품}상품 — **0장이 아니라 판정불가다.** "
              "조인 스캔이 그 행의 상세를 못 물어봤다는 뜻이고, 그 상품은 "
              "Phase 5 입력에서 예외로 막힌다")

    # ④ 캐시 회차 정리 → 병렬 다운로드. **받기 전에 지운다** (T-4-07).
    회차캐시 = os.path.join(인자.cache, 인자.run_dir)
    os.makedirs(회차캐시, exist_ok=True)
    try:
        지운회차 = 회차정리(인자.cache, 인자.keep_runs, 보호=인자.run_dir)
    except ValueError as e:
        사유 = f"⛔ {e}"
        말하기(사유)
        오류말하기(사유)
        return 2
    if 지운회차:
        말하기(f"오래된 원본 캐시 회차 {len(지운회차)}개를 지웠다 "
              f"(--keep-runs {인자.keep_runs}): {', '.join(지운회차)}")

    성공수, 실패수, 호스트별실패 = 전부받기(상품들, 인자.cache, 인자.run_dir, 인자.workers)
    말하기(f"[2/5] 다운로드 {성공수}장 (실패 {실패수})")
    if 호스트별실패:
        줄 = " · ".join(f"{호스트} {수}"
                      for 호스트, 수 in sorted(호스트별실패.items(),
                                             key=lambda kv: -kv[1]))
        말하기(f"    실패 호스트별: {줄}")

    # ⑤ 특징 + 썸네일. 여기서 내리는 판정은 `무내용` 하나뿐이다 — 배너/제품은 04-04.
    특징수, 썸수, 무내용수 = 전부특징(상품들, 인자.cache, 인자.thumbs, 인자.run_dir,
                                인자.blank_ar, 인자.blank_short_px)
    말하기(f"[3/5] 특징 {특징수}장 (무내용 후보 {무내용수})")

    # ⑥ OCR 2패스 + 어휘군 판정. **판정의 정본이 여기서 나온다**(D-10).
    #    `Vision미설치` 는 잡지 않는다 — 회차 전체의 실패라 `__main__` 이 exit 4 로 받는다.
    #    실측 891장 × 2패스 = 156초.
    (OCR장수, 배너수, 제품수, 무내용확정,
     OCR실패수) = 전부판정(상품들, 인자.cache, 인자.run_dir,
                       인자.blank_ar, 인자.blank_short_px,
                       revision=인자.vision_revision)
    말하기(f"[4/5] OCR {OCR장수}장 (Vision revision {인자.vision_revision}"
          f"{f' · 실패 {OCR실패수}' if OCR실패수 else ''})")

    # ⑦ 상품층 집행. **판정불가가 먼저다** — D-07/D-08 이 그 위를 덮으면 거짓말이 된다.
    판정불가상품 = 상품별미판정반영(상품들)
    스킵센것 = 스킵규칙적용(상품들, 인자.skip_min_keep, 인자.skip_max_removal)
    스킵상품수 = 판정불가상품 + sum(스킵센것.values())

    말하기(f"[5/5] 썸네일 {썸수}장 · 판정 배너 {배너수} / 제품 {제품수} / "
          f"무내용 {무내용확정} / 미판정 {총장수 - OCR장수} · 스킵상품 {스킵상품수} "
          f"(어휘군 {인자.lexicon_version})")

    if 판정불가상품:
        말하기(f"※ 판정불가 상품 {판정불가상품}건 — 그 상품은 Phase 5 입력에서 "
              "예외로 막힌다. **'배너 없음' 이 아니다**")
    if 스킵센것[banner.잔여부족] or 스킵센것[banner.제거율초과]:
        말하기(f"※ 스킵 — 잔여부족 {스킵센것[banner.잔여부족]}건 (D-07) · "
              f"제거율초과 {스킵센것[banner.제거율초과]}건 (D-08). "
              "사유는 산출물과 화면에 남는다 — **사람에게 묻지 않는다**(D-09)")

    집계 = 집계내기(상품들)
    산출물 = {
        "run_dir": 인자.run_dir,
        "생성시각": 지금(),
        # `jobs.ended_at` 을 쓰지 마라 — "끝난 시각"이 아니라 "눈치챈 시각"이다
        # (실측: 실제 60초 → 기록 2,421초). CLI 가 자기 경과시간을 직접 찍는다 (S-5).
        "소요초": round(time.time() - 시작, 1),
        "판정규칙": {
            "어휘군버전": 인자.lexicon_version,
            "vision_revision": 인자.vision_revision,
            "무내용_종횡비": 인자.blank_ar,
            "무내용_짧은변px": 인자.blank_short_px,
            "스킵_잔여하한": 인자.skip_min_keep,
            "스킵_제거율상한": 인자.skip_max_removal,
        },
        # **기본값으로 박는다** (VALIDATION §성공기준 2). 게이트는 새 상태가 아니라
        # 산출물 + 라벨 + 확인에서 매번 계산되는 값이다 — 여기 `true` 가 들어가면
        # 낡은 통과 표시로 크레딧이 탄다.
        "게이트통과": False,
        "집계": 집계,
        "상품": 상품들,
    }
    원자적쓰기(인자.out, 산출물)

    말하기(f"끝 — 상품 {집계['상품']} · 장 {집계['장']} · 판정완료 {집계['판정완료']} · "
          f"미판정 {집계['미판정']} · {산출물['소요초']}초 (크레딧 0 · MCP 0회)")

    # ④ 전량 미판정만 실패다. **부분 미판정은 0 이다** (위 docstring 의 경계).
    if 집계["판정완료"] == 0:
        사유 = ("⛔ 판정완료 장이 0이다 — 전량 미판정. 네트워크가 통째로 죽었거나 "
               "CDN 이 막혔다. 산출물은 사유와 함께 남겼으니 그대로 읽어라")
        말하기(사유)
        오류말하기(사유)
        return 3
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Vision미설치 as _비전없음:
        # **exit 4 는 여기 한 곳에서만 난다.** 미설치를 "OCR 0줄" 로 접으면 전 장이
        # `제품` 으로 판정되고 그 목록이 Phase 5 입력이 된다 — 조용한 실패가
        # 크레딧으로 바뀌는 경로다. 산출물도 쓰지 않는다(판정이 전부 거짓이므로).
        말하기(str(_비전없음))
        오류말하기(str(_비전없음))
        sys.exit(4)
    except KeyboardInterrupt:
        # `bulsaja_scan.py:544-548` 규약. 부분 산출물을 남기지 않는다 —
        # **다만 다운로드 캐시는 남는다**(271MB 재다운로드 방지. 캐시는 산출물이 아니다).
        말하기("\n중단됨 — 산출물을 쓰지 않았다. 다시 돌려라 (크레딧 0). "
              "받아 둔 원본 캐시는 남아 있어 다음 실행이 이어서 쓴다.")
        sys.exit(130)
