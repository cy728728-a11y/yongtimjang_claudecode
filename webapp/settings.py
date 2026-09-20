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

    # ── Phase 3 (조인 · 상세 상태) 에서 더한 키 ───────────────────────────
    # **이 8키는 일부러 모듈 상수로 올리지 않는다.** 상수를 늘리면 아래 reload() 의
    # `global` 목록을 같이 고쳐야 하는데, 그걸 빠뜨리면 테스트가 workspace.toml 을
    # 갈아끼워도 값이 안 따라온다(있는 척만 하는 설정). 전부 아래 형태로만 읽어라:
    #     settings.cfg("키", settings.DEFAULTS["키"])
    "expected_bulsaja_nick": "",   # ENG-08 기대 불사자 계정 닉네임. **빈 문자열이 정답이다** —
                                   # cfg(..., required=True) 가 ""을 "비었다"로 보고 KeyError 를
                                   # 던지는 게 가드의 작동 원리다. 실값은 workspace.toml [webapp] 에만
    "profile_path": "webapp-profile.json",  # 계정 확인 산출물(저장소 루트 상대). .gitignore 대상
    "profile_max_age_min": 120,    # 이보다 오래된 계정 확인은 안 믿는다 (ENG-08 사전점검)
    "mcp_min_interval": 0.26,      # 불사자 MCP 호출 최소 간격(초). RateLimit-Policy 240;w=60 실측 = 초당 4회
    "mcp_retry_after": 21,         # 429 뒤 대기(초). 서버가 Retry-After: 20 을 준다 — 1초 여유
    "mcp_batch_size": 50,          # find_by_code 배치 상한 · 목록 페이지 크기 (실측 상한)
    "index_excluded_groups": [],   # D-18 인덱스에서 뺄 **마켓번호 문자열** 리스트.
                                   # **빈 리스트 = 제외 없음** (전량 제외가 아니다). 실값은 workspace.toml 에만
    "done_tags": ["구매_가공완료"],  # D-08 기작업 태그. 늘어날 수 있으므로 리스트로 둔다
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
    # 잡 레지스트리·로그 경로도 환경변수를 먼저 본다. 이유는 하나다:
    # **스트리밍은 진짜 서버를 띄워야만 검증된다.** `TestClient` 는 ASGI 앱을
    # 끝까지 돌린 뒤 통째로 돌려주므로(실측: testclient.py 가 BytesIO 에 모은다)
    # "0.8초 받고 끊는다" 를 흉내조차 못 낸다. 그 서버는 별도 프로세스라
    # monkeypatch 가 닿지 않고, 저장소 루트의 진짜 webapp.db 를 쓰면 테스트가
    # 화면에 유령 작업을 남긴다. env 가 유일한 통로다.
    # 부수효과로 두 번째 인스턴스를 나란히 띄우는 것도 공짜가 된다.
    JOB_LOG_DIR = str(os.environ.get("CT_JOB_LOG_DIR") or cfg("job_log_dir", DEFAULTS["job_log_dir"]))
    DB_PATH = str(os.environ.get("CT_DB_PATH") or cfg("db_path", DEFAULTS["db_path"]))
    return load()


reload()
