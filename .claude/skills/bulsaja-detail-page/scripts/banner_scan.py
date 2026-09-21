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
        [--lexicon-version 2026-09-21] [--keep-runs 2]
"""
import argparse
import json
import os
import sys
import time
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
    "lexicon_version": "2026-09-21",   # settings `banner_lexicon_version`
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
    except KeyboardInterrupt:
        # `bulsaja_scan.py:544-548` 규약. 부분 산출물을 남기지 않는다 —
        # **다만 다운로드 캐시는 남는다**(271MB 재다운로드 방지. 캐시는 산출물이 아니다).
        말하기("\n중단됨 — 산출물을 쓰지 않았다. 다시 돌려라 (크레딧 0). "
              "받아 둔 원본 캐시는 남아 있어 다음 실행이 이어서 쓴다.")
        sys.exit(130)
