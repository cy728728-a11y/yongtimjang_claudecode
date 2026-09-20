#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""웹앱 설정 한 곳 — 숫자를 코드·템플릿에 박지 않기 위한 파일.

`DEFAULTS` 위에 `workspace.toml` 의 `[webapp]` 테이블을 **얕게** 덮는다.
모양은 `.claude/lib/eroomlib/config.py` 의 `cfg(dotted, default, required)` 를 따른다 —
저장소를 오가는 사람이 두 규약을 외우지 않게 하려는 것이다.

여기 있는 숫자 중 `per_account_limit` 은 안전장치다(D-08). 1회 실행에서 한 계정에
몇 건까지 쓰기를 허용할지. 실측 최대가 1,195 라 평상시 마찰은 0 이고,
"계정이 이상하게 불어났다" 는 사고만 잡는다. **다른 파일에 이 숫자를 복사하지 마라** —
설정을 고쳐도 동작이 안 바뀌면 가드가 있는 척만 하는 것이다.
"""
import os

from webapp import paths

DEFAULTS = {
    "port": 8765,                  # 127.0.0.1 전용. 인증이 없으므로 외부 바인드 금지
    "per_account_limit": 1500,     # D-08 — 1회 실행 계정별 쓰기 상한
    "stale_days": 8,               # 회차가 이보다 오래되면 보드에서 경고 (D-16)
    "poll_interval": 0.4,          # 로그 tail 폴링 간격(초)
    "job_log_dir": "webapp-logs",  # 잡 로그 루트 (.gitignore 대상)
    "db_path": "webapp.db",        # 잡 레지스트리 (.gitignore 대상)
}

_cache = None


def load(force: bool = False) -> dict:
    """설정 dict(1회 로드 후 캐시). `[webapp]` 테이블이 DEFAULTS 를 덮는다."""
    global _cache
    if _cache is not None and not force:
        return _cache
    over = {}
    try:
        table = paths.read_workspace_toml().get("webapp")
        if isinstance(table, dict):
            over = table
    except FileNotFoundError:
        pass
    # 파싱 실패(RuntimeError)는 일부러 안 삼킨다 — 상한이 조용히 사라지면 D-08 가드가 죽는다
    _cache = {**DEFAULTS, **over}
    return _cache


def cfg(dotted: str, default=None, required: bool = False):
    """`"per_account_limit"` 처럼 점 경로로 값 하나를 꺼낸다.

    required=True 인데 비어 있으면 KeyError — 배포본처럼 값이 비워진 환경에서
    "조용히 기본값으로 돌다가 가드가 없는 채로 쓰는" 사고를 막는다 (위협 T-1-12).
    """
    node = load()
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            node = None
            break
        node = node[part]
    if node is None or node == "":
        if required:
            raise KeyError(f"설정 'webapp.{dotted}' 이(가) 비어 있다. workspace.toml 에 채워라")
        return default
    return node


def reload() -> dict:
    """설정을 다시 읽고 모듈 상수를 갱신한다.

    모듈 최상위 상수는 import 시점에 한 번 굳는다. 테스트가 workspace.toml 을
    바꿔 끼운 뒤 이걸 부르면 상수도 같이 따라온다(원복도 이걸로 한다).
    """
    global PORT, PER_ACCOUNT_LIMIT, STALE_DAYS, POLL_INTERVAL, JOB_LOG_DIR, DB_PATH
    load(force=True)
    # CT_PORT 가 workspace.toml 보다 우선한다. 기동 스크립트가 이 환경변수로 포트를
    # 바꾸는데, 그때 settings.PORT 가 따라오지 않으면 **바인드 포트와 Origin 화이트리스트·
    # 기동 URL 이 어긋난다** — 서버는 9999 에 떠 있는데 8765 를 허용하고 8765 를 안내하는
    # 상태가 되어, 모든 쓰기가 403 이 되거나 방어가 엉뚱한 포트를 지킨다.
    PORT = int(os.environ.get("CT_PORT") or cfg("port", DEFAULTS["port"]))
    PER_ACCOUNT_LIMIT = int(cfg("per_account_limit", DEFAULTS["per_account_limit"]))
    STALE_DAYS = int(cfg("stale_days", DEFAULTS["stale_days"]))
    POLL_INTERVAL = float(cfg("poll_interval", DEFAULTS["poll_interval"]))
    JOB_LOG_DIR = str(cfg("job_log_dir", DEFAULTS["job_log_dir"]))
    DB_PATH = str(cfg("db_path", DEFAULTS["db_path"]))
    return load()


reload()
