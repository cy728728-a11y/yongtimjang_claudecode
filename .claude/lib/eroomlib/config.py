#!/usr/bin/env python3
"""워크스페이스 설정 1벌 — 경로·드라이브 폴더·시트·계정을 코드/문서 밖으로 뺀다.

**왜 필요한가**: run-dir 경로·드라이브 folderId·시트 id·계정 주소를 코드/문서에 박지 않고
여기 한 곳에 모은다. 환경이 바뀌면 **이 파일(또는 workspace.toml) 하나만 갈아끼우면** 된다.

**이 사본은 배포본이다** — DEFAULTS 가 전부 비어 있으므로 `workspace.toml` 을 만들어야
동작한다. 동봉된 `workspace.example.toml` 을 워크스페이스 루트에 복사해 값을 채워라.

찾는 순서:
  1. 환경변수 `EROOM_WORKSPACE_TOML`
  2. 워크스페이스 루트(`.claude` 앵커의 부모)의 `workspace.toml`
  3. 없으면 DEFAULTS

사용:
    from eroomlib.config import cfg
    cfg("paths.category_fix_runs")               # -> workspace.toml 의 값
    cfg("drive.category_folder")                 # -> workspace.toml 의 값
    cfg("sheets.master_index", required=True)    # 없으면 KeyError
"""
import os

try:
    import tomllib  # py3.11+
except ImportError:  # pragma: no cover - 구버전 파이썬
    tomllib = None

# 배포본 — 값은 전부 비어 있다. 워크스페이스 루트의 `workspace.toml` 에 채워 넣어라
# (동봉된 `workspace.example.toml` 을 복사해서 쓴다). required=True 인 항목은 비어 있으면
# KeyError 를 내므로, "조용히 남의 시트에 쓰는" 사고는 나지 않는다.
DEFAULTS = {
    "paths": {
        "data_root": "",
        "category_fix_runs": "",
        "product_name_runs": "",
        "sellerlife_runs": "",
        "keyword_pick_runs": "",
        "snapshot_root": "",
        # 세로 러너(onestep) — 상품 1건이 여러 작업을 통과하는 진행 상태와 단계별 run-dir
        "onestep_runs": "",
        # 대량 다듬기(Step 0 인벤토리·중복 맵·전파 장부)의 산출물 루트
        "dedup_root": "",
        # 셀러라이프 드라이브 캐시 — 통다운·블랙리스트 원본을 내려받는 로컬 경로
        "sellerlife_cache": "~/.eroom/sellerlife-cache",
    },
    "drive": {
        # 불사자 상품관리 루트 폴더 ID
        "bulsaja_root_folder": "",
        # 카테고리교정 폴더 ID (그룹별 로그 시트가 여기 생성된다)
        "category_folder": "",
        # 셀러라이프 통다운 폴더 ID
        "sellerlife_folder": "",
    },
    "sheets": {
        # 카테고리교정 그룹 시트들의 인덱스
        "master_index": "",
        # keyword-pick 기본 시트(그룹 지정이 없을 때의 폴백)
        "keyword_default": "",
    },
    "accounts": {
        # gws(구글 워크스페이스) 인증 계정 — 폴더·시트 생성 주체
        "gws": "",
        # 외부 사이트(셀하 등) 로그인 계정
        "external": "",
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
