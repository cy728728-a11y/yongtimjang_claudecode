#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""경로 규약 한 곳 — 웹앱이 디스크를 만지는 유일한 관문.

**eroomlib 을 import 하지 않는다.** run_ads.py 는 `sys.path.insert` 로 스크립트 디렉터리를
최상위에 꽂는데(`collect`·`reports` 같은 흔한 이름이 전역이 된다), 그 경로를 웹앱 프로세스에
넣으면 stdlib 이 가려진다. 같은 결과를 stdlib `tomllib` 로 낸다 — CLI 와 규약만 공유하고
프로세스는 subprocess 경계로 갈라 둔다.

CLI 쪽 정본은 `.claude/skills/naver-ads-weekly/scripts/run_ads.py:39-57` 이다.
거기 주석대로 **절대경로를 박으면 다른 PC 에서 조용히 폴백해** workspace.toml 이 영영 안 읽힌다.
"""
import json
import tomllib
from datetime import date
from pathlib import Path


def repo_root() -> Path:
    """`.claude` 디렉터리를 품은 조상 = 저장소 루트.

    저장소 표준 while-loop 관례(`.claude/lib/eroomlib/config.py:82-97`)를 그대로 쓴다.
    못 찾으면 이 파일의 2단계 상위(= webapp/ 의 부모)를 쓴다.
    """
    d = Path(__file__).resolve().parent
    while d != d.parent:
        if (d / ".claude").is_dir():
            return d
        d = d.parent
    return Path(__file__).resolve().parents[1]


def read_workspace_toml() -> dict:
    """`workspace.toml` 을 dict 로 읽는다. 파일이 없으면 `{}`.

    **파싱 실패는 예외로 올린다** — 설정이 깨졌는데 조용히 기본값으로 도는 것이
    이 저장소가 막아 온 사고다(eroomlib/config.py:112-115 와 같은 판단).
    호출자가 "이 실패는 돈으로 이어지지 않는다" 고 판단하면 그쪽에서 삼킨다.
    """
    path = repo_root() / "workspace.toml"
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except Exception as e:
        raise RuntimeError(f"workspace.toml 파싱 실패({path}): {e}")


def data_root() -> Path:
    """데이터 루트. `workspace.toml [paths] data_root` → 없으면 홈 밑 폴백.

    여기서는 실패를 **삼킨다**. 경로를 못 읽어도 돈이 나가지 않고, 폴백 경로가
    이 저장소 모든 스킬의 기본값이라 CLI 와 결과가 같기 때문이다(PATTERNS §S-2 기준).
    """
    try:
        p = (read_workspace_toml().get("paths") or {}).get("data_root")
        if p:
            return Path(p).expanduser()
    except Exception:
        pass
    return Path.home() / "python_work" / "data"


def ads_root() -> Path:
    return data_root() / "naver-ads"


def runs_root() -> Path:
    return ads_root() / "runs"


def scan_run_dirs() -> list[str]:
    """`result.json` 이 있는 회차 **이름만** 최신순으로.

    `prep` 만 돌고 `run` 을 안 돌린 run-dir 은 판정이 없다 — 보드에 띄우면 빈 화면이 된다.
    그래서 목록의 조건은 "디렉터리가 있다" 가 아니라 "판정 결과가 있다" 다.
    """
    root = runs_root()
    if not root.is_dir():
        return []
    try:
        names = [p.name for p in root.iterdir()
                 if p.is_dir() and (p / "result.json").is_file()]
    except OSError:
        return []
    return sorted(names, reverse=True)


def run_dir_path(name: str) -> Path:
    """회차 이름 → 디렉터리. **화이트리스트를 통과한 이름만** 경로가 된다.

    사용자 입력으로 경로를 조합하지 않는다(ASVS V12 / 위협 T-1-11).
    `..` 를 거르는 식의 블랙리스트가 아니라, 실제로 존재하는 회차 목록에
    들어 있는 이름만 통과시킨다 — 이 함수가 run-dir 이름의 **유일한 관문**이고
    이후 모든 플랜이 여기를 통과한 뒤에만 파일을 만진다.
    """
    if name not in scan_run_dirs():
        raise ValueError(f"모르는 회차다: {name}")
    return runs_root() / name


def _windows_of(raw: dict):
    """`prep_summary.json` 에서 (window7, window30) 을 꺼낸다.

    실데이터는 계정 alias 로 한 겹 감싸져 있다(`{"cy728": {..., "window7": [...]}}`).
    `--account` 로 나눠 돌려도 통계기간은 같으므로 처음 찾은 것을 쓴다.
    평평한 모양도 받는다 — 테스트 픽스처와 미래의 요약 포맷 변화를 같이 견딘다.
    """
    if not isinstance(raw, dict):
        return None, None
    if "window7" in raw or "window30" in raw:
        return raw.get("window7"), raw.get("window30")
    for v in raw.values():
        if isinstance(v, dict) and ("window7" in v or "window30" in v):
            return v.get("window7"), v.get("window30")
    return None, None


def freshness(name: str) -> dict:
    """회차 신선도 — 경과일과 **실제 통계기간**을 같이 돌려준다 (D-16).

    회차명은 통계기간보다 항상 2일 이상 신선해 보인다 — `collect.window()` 가
    `until = today - 2일` 이라, 둘 다 보여줘야 정직하다. "2026-08-30 회차" 만 띄우면
    실제로는 08-22~08-28 자료로 입찰가를 올리면서 8월 30일 자료인 줄 알게 된다.
    """
    try:
        age_days = (date.today() - date.fromisoformat(name)).days
    except ValueError:
        # 복구용으로 날짜가 아닌 회차명을 쓸 수 있다 — 경과일을 지어내지 않는다
        age_days = None

    window7 = window30 = None
    try:
        raw = json.loads((run_dir_path(name) / "prep_summary.json").read_text(encoding="utf-8"))
        window7, window30 = _windows_of(raw)
    except Exception:
        pass

    from webapp import settings  # 순환 import 회피 — settings 가 paths 를 쓴다

    return {
        "run_dir": name,
        "age_days": age_days,
        "window7": window7,
        "window30": window30,
        "stale": age_days is not None and age_days > settings.STALE_DAYS,
    }
