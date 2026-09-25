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

    # ── Phase 4 (배너 판정) 에서 더한 키 ──────────────────────────────────
    # Phase 3 블록과 같은 규율이다 — **모듈 상수로 올리지 않는다.** 전부 아래로만 읽어라:
    #     settings.cfg("키", settings.DEFAULTS["키"])
    # `webapp/**` 런타임 소스에 이 숫자들을 리터럴로 베끼지 마라. 베끼면 workspace.toml 을
    # 고쳐도 동작이 안 바뀐다(있는 척만 하는 설정).
    "banner_cache_dir": "webapp-banner/cache",   # 원본 이미지 캐시 루트. .gitignore 대상
    "banner_thumb_dir": "webapp-banner/thumbs",  # 검수 스트립용 썸네일. .gitignore 대상
    "banner_workers": 8,           # 8스레드. 916장 271MB 를 50~75초에 받는 실측값
    "banner_vision_revision": 3,   # **박는 것이 요점이다**(D-10). 안 박으면 OS 업데이트가 기본
                                   # 리비전을 올리는 날 판정이 조용히 바뀐다 — D-02 가 걱정한
                                   # "회차마다 흔들린다"가 되살아나는 유일한 경로다.
                                   # 실측 지원 `[1,2,3]` (VNRecognizeTextRequest.supportedRevisions)
    "banner_blank_ar": 6.0,        # **배너 판정이 아니다**(D-10). 구분선·슬라이스 잔재를 빼는
                                   # '무내용 장' 규칙 전용. 종횡비로 배너를 잡으려 하지 마라 —
                                   # 실측상 정반대다(Pitfall 1: 배너는 오히려 세로로 길다, 중앙값 0.89)
    "banner_blank_short_px": 32,   # 같은 '무내용 장' 규칙의 짧은 변 하한(px). 위 주석과 한 쌍이다
    "banner_skip_min_keep": 2,     # D-07. 잔여 제품 이미지가 이보다 적으면 그 상품을 통째로 스킵
    "banner_skip_max_removal": 0.5,  # D-08. 제거율이 이를 넘으면 판정이 폭주한 신호 → 통째로 스킵.
                                   # D-07/D-08 둘 다 "애매하면 사람에게 묻는 게 아니라
                                   # 그 상품을 건너뛴다"(D-09)
    "banner_lexicon_version": "2026-09-22",  # 어휘군 **문자열 목록 자체는 `banner_scan.py` 에 산다**
                                   # (설정에 200개 문자열을 넣으면 회귀 픽스처와 버전이 어긋난다).
                                   # 여기 있는 것은 산출물 `판정규칙` 블록에 찍을 버전 표기뿐이다
    "banner_keep_runs": 2,         # 원본 캐시를 남길 회차 수. 회차당 약 271MB. 집행은 04-03
    # ── 비전 2차 판정 (D-22 · 판정 대상 전량) — CLI `폴백` 과 한 글자도 달라선 안 된다 ──
    # 기본 켜짐이 결정이다(D-22). 꺼져 있으면 게이트에서 실패한 1차(어휘군) 단독으로 조용히
    # 돌아간다 — 그래서 켜짐/꺼짐이 산출물 `판정규칙.2차판정.사용` 에 박힌다.
    "banner_vision2_enabled": True,
    "banner_vision2_model": "gemini-3.6-flash",  # 요청 모델. 응답 modelVersion 은 산출물에 따로
    "banner_vision2_prompt": "v3",  # 지시문 판. 스크립트의 지침판과 다르면 CLI 가 exit 5
    # 키 **값**이 아니라 파일 **경로**다. 값은 gitignore 된 `.env` 에만 산다.
    "banner_vision2_key_file": ".claude/skills/sellerlife-keyword/.env",
    "banner_vision2_timeout": 60.0,  # 호출 1회 타임아웃(초)
    # **0 = 유료 호출 미승인.** 견적(`--vision2-estimate`)을 보고 용팀장이 승인한 수를
    # `workspace.toml [webapp]` 에만 적는다. 과금 대상(체크포인트 적중분 제외 고유 이미지)이
    # 이 수를 넘으면 자르지 않고 거부한다(exit 5).
    "banner_vision2_max_calls": 0,
    "banner_vision2_interval": 0.3,  # 호출 사이 쉬는 초 (무료 티어 레이트리밋 여유)
    # 검수 화면 첫 화면에 **일부러** 배치할 경계 표본(RESEARCH Appendix A "경계 4장").
    # 용팀장 기준을 클릭으로 받는 자리다 — 미리 묻지 않는다.
    # ⚠️ 이 4개만 익명화되지 않은 **실제 판매자상품코드**다. `banner_labels.json` 은 `zzNN` 을
    #    쓰지만 여기는 실제 회차 산출물과 매칭돼야 기능하므로 익명화할 수 없다.
    # ⚠️ **다음 회차에는 반드시 낡는다** — 물갈이로 상품코드가 재발급된다. 04-07 의
    #    "못 찾았다" 폴백이 낡음을 부드럽게 처리하므로 기능은 안 깨지지만, 경계 4장 확인은
    #    그 회차에 조용히 빈다. 회차가 바뀌면 이 값을 다시 떠라.
    "banner_boundary_samples": [
        "dnb2lYw0omRnoG121KzBL:6",   # 수상·브랜드 배너지만 제품이 크게 나온다
        "fElaVlxOzkeSVkDotMrAJ:0",   # 첫 장 타이틀 히어로 — 제품인가 배너인가
        "sLix0885VmdKsGxunAznE:0",   # 장식 포스터. 제품(밥그릇)이 나온다
        "sLix0885VmdKsGxunAznE:4",   # 사용 장면 배너. 제품은 안 나온다
    ],

    # ── Phase 5 (상세페이지 작업) 에서 더한 키 ────────────────────────────
    # Phase 3·4 블록과 같은 규율이다 — 모듈 상수로 올리지 않는다. 전부 아래로만 읽어라:
    #     settings.cfg("키", settings.DEFAULTS["키"])
    # 폴링 상한은 넉넉하게 두지 않는다(연구 Open Q4). 넘기면 CLI 가 exit 3(폴링 미완)으로
    # 끝나고, "이어서 확인"(--poll-only)이 크레딧 0 으로 이어 받는다 — 길게 잡아 노트북을
    # 붙잡아 두는 것보다 싸다.
    "detail_max_poll_min": 60,     # 접수·폴링 잡 1회의 폴링 상한(분)
    "detail_poll_interval": 45,    # 폴링 간격(초)
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
