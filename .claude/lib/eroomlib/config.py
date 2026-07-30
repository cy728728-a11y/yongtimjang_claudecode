#!/usr/bin/env python3
"""워크스페이스 설정 1벌 — 경로·드라이브 폴더·시트·계정을 코드/문서 밖으로 뺀다.

**왜 필요한가**: 지금 run-dir 경로(`D:\\python_work\\...`)·드라이브 folderId·마스터 시트 id·
계정 주소가 SKILL.md 본문과 스크립트에 흩어져 박혀 있다. 배포판(개인정보 제거본)을 뽑으려면
그 전부를 손으로 찾아 지워야 한다. 여기로 모으면 **이 파일 하나만 갈아끼우면** 된다.

**호환 원칙**: `workspace.toml` 이 없어도 **현행 동작 그대로**다. 아래 DEFAULTS 가 지금
하드코딩돼 있는 값과 같으므로, 설정 파일을 안 만들면 아무것도 바뀌지 않는다.
(배포본은 DEFAULTS 를 빈 값으로 둔 `workspace.example.toml` 을 동봉한다.)

찾는 순서:
  1. 환경변수 `EROOM_WORKSPACE_TOML`
  2. 워크스페이스 루트(`.claude` 앵커의 부모)의 `workspace.toml`
  3. 없으면 DEFAULTS

사용:
    from eroomlib.config import cfg
    cfg("paths.category_fix_runs")               # -> "D:/python_work/data/category-fix/runs"
    cfg("drive.category_folder")                 # -> "1bVa3y72..."
    cfg("sheets.master_index", required=True)    # 없으면 KeyError
"""
import os

try:
    import tomllib  # py3.11+
except ImportError:  # pragma: no cover - 구버전 파이썬
    tomllib = None

# 현행 하드코딩 값 — workspace.toml 이 없을 때 쓰인다(= 지금 동작 유지).
# 배포본에서는 workspace.example.toml 로 덮어써 빈 값이 되게 한다.
DEFAULTS = {
    "paths": {
        "data_root": "D:/python_work/data",
        "category_fix_runs": "D:/python_work/data/category-fix/runs",
        "product_name_runs": "D:/python_work/data/product-name/runs",
        "sellerlife_runs": "D:/python_work/data/sellerlife/runs",
        "keyword_pick_runs": "D:/python_work/data/keyword-pick/runs",
        "snapshot_root": "D:/python_work/data/_snapshot",
        # 세로 러너(onestep) — 상품 1건이 여러 작업을 통과하는 진행 상태와 단계별 run-dir
        "onestep_runs": "D:/python_work/data/onestep/runs",
        # 대량 다듬기(Step 0 인벤토리·중복 맵·전파 장부)의 산출물 루트
        "dedup_root": "D:/python_work/data/_dedup",
    },
    "drive": {
        # 20-불사자-상품관리
        "bulsaja_root_folder": "1jvRWkt1L6UKHvLhsSbb8bpGjwumZg5HD",
        # 20-불사자-상품관리 > 카테고리교정  (그룹별 로그 시트가 여기 생성된다)
        "category_folder": "1bVa3y725YCCSrOtx_bqBylBpvaXvwm2w",
    },
    "sheets": {
        # 카테고리교정 그룹 시트들의 인덱스
        "master_index": "1R4XdWohipaYeR-0QOAyRiVYZlk6iDofGONEBzSymGqs",
        # keyword-pick / 초기 파일럿에서 쓰던 기본 시트(그룹 지정이 없을 때의 폴백)
        "keyword_default": "1DbR2upLX_DXjgjXpGPdide2SUifli_X6DTqhUTr9Syk",
    },
    "accounts": {
        # gws(구글 워크스페이스) 인증 계정 — 폴더·시트 생성 주체
        "gws": "chloe91727@gmail.com",
        # 외부 사이트(셀하 등) 로그인 계정
        "external": "cy728728@gmail.com",
    },
    "naming": {
        # 그룹 로그 시트 이름 규칙. {group} 이 마켓그룹명으로 치환된다
        "group_sheet": "카테고리교정_{group}",
    },
}

_cache = None
_source = None


def workspace_root(start=None):
    """`.claude` 디렉터리를 품은 조상 = 워크스페이스 루트. 못 찾으면 None."""
    d = os.path.dirname(os.path.abspath(start or __file__))
    while d and d != os.path.dirname(d):
        if os.path.isdir(os.path.join(d, ".claude")):
            return d
        d = os.path.dirname(d)
    return None


def _toml_path():
    p = os.environ.get("EROOM_WORKSPACE_TOML")
    if p:
        return p
    root = workspace_root()
    return os.path.join(root, "workspace.toml") if root else None


def _deep_merge(base, over):
    """over 가 base 를 덮어쓴다(중첩 dict 는 재귀). 원본은 안 건드린다."""
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load(force=False):
    """설정 dict 를 돌려준다(1회 로드 후 캐시). DEFAULTS 위에 workspace.toml 을 얹는다."""
    global _cache, _source
    if _cache is not None and not force:
        return _cache

    data, src = {}, "(defaults)"
    path = _toml_path()
    if path and os.path.exists(path):
        if tomllib is None:
            raise RuntimeError("tomllib 이 없다(파이썬 3.11+ 필요). workspace.toml 을 못 읽는다.")
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
            src = path
        except Exception as e:
            # 설정이 깨졌으면 조용히 넘어가지 않는다 — 엉뚱한 시트에 쓰는 사고가 난다.
            raise RuntimeError(f"workspace.toml 파싱 실패({path}): {e}")

    _cache = _deep_merge(DEFAULTS, data)
    _source = src
    return _cache


def cfg(dotted, default=None, required=False):
    """`"drive.category_folder"` 처럼 점 경로로 값 하나를 꺼낸다.

    required=True 인데 값이 없거나 빈 문자열이면 KeyError — 배포본처럼 값이 비워진 환경에서
    "조용히 기본값으로 돌다가 남의 시트에 쓰는" 사고를 막는다.
    """
    node = load()
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            node = None
            break
        node = node[part]
    if node is None or node == "":
        if required:
            raise KeyError(
                f"설정 '{dotted}' 이(가) 비어 있다. workspace.toml 에 채워라 "
                f"(현재 소스: {source()})"
            )
        return default
    return node


def source():
    """지금 쓰이는 설정 파일 경로(없으면 '(defaults)'). 로그·진단용."""
    load()
    return _source


def group_sheet_name(group):
    """마켓그룹명 → 그룹 로그 시트 이름."""
    return cfg("naming.group_sheet", "카테고리교정_{group}").format(group=group)


def run_dir(skill, name):
    """스킬별 run-dir 경로. skill 은 'category_fix' | 'product_name' | 'sellerlife' | 'keyword_pick'."""
    base = cfg(f"paths.{skill}_runs", required=True)
    return os.path.join(base, name).replace("\\", "/")


if __name__ == "__main__":
    import json
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(f"설정 소스: {source()}")
    print(json.dumps(load(), ensure_ascii=False, indent=2))
