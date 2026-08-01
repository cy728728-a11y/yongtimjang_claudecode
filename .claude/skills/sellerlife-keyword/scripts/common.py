#!/usr/bin/env python3
"""sellerlife-keyword 스킬 공용 유틸.

- .env 로더 (환경변수 우선)
- 엑셀 헤더 정규화/매칭 (헤더에 줄바꿈이 섞여 있음: '브랜드\\n키워드')
- 실행 폴더(runs/<YYMMDD>/...) 생성
- 크롬 드라이버 생성 (eroomlib.webdriver.make_driver 위임, PROFILE_DIR 기본값 보존)

드라이버(make_driver/close_driver)는 eroomlib.webdriver 를 쓴다.
norm/cat_key/find_col/run_dir 등 sellerlife 업무 유틸은 이 모듈에 잔류.
"""
import os
import sys
from datetime import date

sys.stdout.reconfigure(encoding="utf-8")

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_DIR = os.path.dirname(SKILL_DIR)

# 봇우회 크롬 드라이버는 eroomlib.webdriver 로 이동. `.claude` 앵커를 찾아 lib 를 1회 insert.
_d = SKILL_DIR
while _d and _d != os.path.dirname(_d):
    _lib = os.path.join(_d, "lib")
    if os.path.isdir(os.path.join(_lib, "eroomlib")):
        if _lib not in sys.path:
            sys.path.insert(0, _lib)
        break
    _d = os.path.dirname(_d)
from eroomlib.webdriver import close_driver  # noqa: E402,F401
from eroomlib.webdriver import make_driver as _lib_make_driver  # noqa: E402
from eroomlib.envload import load_env as _envload  # noqa: E402

PROFILE_DIR = os.path.join(SKILL_DIR, "_chrome_profile")
DL_TMP_DIR = os.path.join(SKILL_DIR, "_dl_tmp")
DEFAULT_DATA_ROOT = r"d:\python_work\data\sellerlife"

# 수집 대상 카테고리 (1차/대분류). 데이터는 '가구/인테리어', 파일명은 '가구&인테리어'.
KEEP_CATEGORIES = ["가구/인테리어", "디지털/가전", "생활/건강"]

# 어린이용(KC 인증 회피) 판정 토큰. 검토 자동승인 시 '어린이용' 분류는
# 아래 표현이 키워드에 명시된 것만 제외 대상으로 본다(성인 겸용 오탐 방지).
KID_TOKENS = ("어린이", "유아", "키즈", "아동", "주니어", "초등", "고학년", "아기", "공주", "남매", "아이")

_ENV_KEYS = ("SELLERLIFE_GOOGLE_EMAIL", "GEMINI_API_KEY", "DATA_ROOT")


def load_env():
    """SKILL_DIR/.env 로드(환경변수 우선). eroomlib.envload 사용.

    호출부 호환: _ENV_KEYS 전 키가 항상 존재하고(없으면 None), DATA_ROOT 는 기본값 보장.
    """
    cfg = _envload(os.path.join(SKILL_DIR, ".env"), _ENV_KEYS)
    for k in _ENV_KEYS:
        cfg.setdefault(k, None)
    cfg["DATA_ROOT"] = cfg.get("DATA_ROOT") or DEFAULT_DATA_ROOT
    return cfg


def default_blacklist(data_root=None):
    """블랙리스트 기본 경로. 상수가 아니라 함수인 이유는 .env 의 DATA_ROOT 를 따라가야 하기 때문.

    (PC마다 데이터 루트가 다르므로 import 시점에 고정하면 안 된다.)
    """
    root = data_root or load_env()["DATA_ROOT"]
    return os.path.join(root, "keyword_blacklist", "keyword_blacklist.xlsx")


def norm(text):
    """헤더 비교용 정규화: 줄바꿈·공백 제거. '브랜드\\n키워드' -> '브랜드키워드'"""
    if text is None:
        return ""
    return str(text).replace("\n", "").replace(" ", "").strip()


def find_col(headers, target):
    """정규화 헤더 목록에서 target 의 0-based 인덱스를 찾는다. 없으면 None."""
    t = norm(target)
    for i, h in enumerate(headers):
        if norm(h) == t:
            return i
    return None


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


KEEP_KEYS = {cat_key(c) for c in KEEP_CATEGORIES}


def is_kid_keyword(kw):
    """키워드에 아동 표현이 명시돼 있으면 True (검토 '어린이용' 자동승인 판정용)."""
    s = str(kw or "")
    return any(t in s for t in KID_TOKENS)


def run_dir(data_root=None, ymd=None):
    """runs/<YYMMDD>/{raw,filtered,detected} 생성 후 경로 dict 반환."""
    root = data_root or DEFAULT_DATA_ROOT
    ymd = ymd or date.today().strftime("%y%m%d")
    base = os.path.join(root, "runs", ymd)
    paths = {
        "base": base,
        "raw": os.path.join(base, "raw"),
        "filtered": os.path.join(base, "filtered"),
        "detected": os.path.join(base, "detected"),
        "ymd": ymd,
    }
    for k in ("raw", "filtered", "detected"):
        os.makedirs(paths[k], exist_ok=True)
    return paths


def make_driver(headless=False, profile_dir=None, download_dir=None):
    """[shim] 전용 프로필 Chrome — 실체는 eroomlib.webdriver.make_driver.

    profile_dir 미지정 시 이 스킬의 PROFILE_DIR 을 기본값으로 채워 기존 동작을 보존한다
    (eroomlib 기본값은 CWD 기반이라 여기서 명시적으로 넘긴다).
    """
    return _lib_make_driver(headless=headless,
                            profile_dir=profile_dir or PROFILE_DIR,
                            download_dir=download_dir)
