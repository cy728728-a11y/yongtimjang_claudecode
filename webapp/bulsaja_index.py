#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""스마트스토어번호 → 불사자 productId 인덱스를 **읽기만** 하는 관문.

**읽기 전용이다. 불사자를 부르지 않고 판정값을 만들지 않는다.** `webapp.db` 의
`ss_index` 테이블과 계정 확인 산출물(JSON) 두 개만 읽는다. 그래서 이 모듈은
네트워크도 크레딧도 0 이고, 인덱스가 아직 없으면 빈 결과를 줄 뿐 아무것도 고장내지 않는다.

이게 `board.py` 와 같은 "세 번째 길" 이다. 인덱스 데이터는 CLI 를 실행해서도, CLI 모듈을
불러와서도 얻지 않는다. CLI 자식이 **이미 써 둔 기록**을 읽을 뿐이다.

이 모듈이 절대 하지 않는 것:
  - 불사자 MCP 호출 (D-19) — 웹앱 venv 에는 CLI 가 쓰는 HTTP 라이브러리가 없어서
    CLI 쪽 공용 라이브러리를 import 하는 순간 ImportError 다. 인덱스를 **채우는** 것은
    CLI 자식 몫이고 여기는 꺼내 주기만 한다. `paths.py:4-10` 이 같은 결론을 이미 적어 뒀다.
    (그 라이브러리 이름을 여기 적지도 않는다 — `test_index.py` 의 grep 가드가 이 파일을
    훑어 import 경로가 주석으로도 스며들지 않게 지킨다.)
  - 쓰기 — 질의는 전부 `mode=ro` URI 로 연다. 읽기 경로가 인덱스를 오염시키면
    3시간 반을 다시 태워야 한다 (위협 T-3-17).
  - DB 파일 생성 — `jobs.active_job()` 과 같은 규율이다. 읽기 라우트가 파일을 만들기
    시작하면 "GET 은 상태를 안 바꾼다" 는 방어의 전제가 흐려진다 (T-1-01b).
  - 인덱스 히트를 **해소로 접기** — 재검증 없는 히트는 물갈이 뒤 틀린 상품을 가리킨다
    (JOIN-04 / D-04). 판정 어휘(`히트`/`미스`/`미조회`/`불일치`)는 `webapp/join.py` 가
    정본이다. 판정이 두 곳에 있으면 화면과 산출물이 다른 말을 한다.

향후 — 인덱스 비용이 다시 아플 때 여기부터 읽어라 (RESEARCH Open Question 5):
    네이버 **커머스API** 로 `channelProductNo → sellerManagementCode` 를 역조회해
    `find_by_code` 배치로 가면 **약 30초**다. 지금 경로(전 그룹 workdata 스캔)의
    **3시간 32분** 대비 500배. 막는 것은 오직 자격증명 — `~/.eroom/naver-commerce.json`
    이 없고, 예시 파일이 "스토어당 앱 1개가 상한" 이라 이 회차 광고에 걸친 몰 50개에
    앱 50개 등록이 선행된다. **v1 범위 밖이고, 이 페이즈에서 하지 않는다.**
    (이 메모가 없으면 다음 사람이 같은 조사를 처음부터 다시 한다.)
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from webapp import paths, settings

# 불사자 MCP 응답 전부에 붙어 오는 **모델 대상 지시문** 필드. 화면에도 LLM 에도 닿게 두지
# 않는다(프롬프트 인젝션). CLI 가 이미 떼고 쓰지만 이 파일은 손으로 편집될 수 있어서
# 여기서도 한 번 더 버린다 — 방어적 이중화다.
_버릴필드 = ("표시규칙",)


def db_path() -> Path:
    """인덱스가 사는 파일. `jobs.db_path()` 와 **같은 파일**이다.

    `jobs` 를 import 하지 않고 세 줄을 복제한다. ENG-08 가드가 `jobs.create_job` 에서
    이 모듈의 `profile_ok` 를 부르므로, 여기서 `jobs` 를 import 하면
    `jobs → bulsaja_index → jobs` 순환이 된다. 계산이 세 줄뿐이라 복제가 싸다 —
    대신 `settings.DB_PATH` 라는 **같은 출처**를 보므로 둘이 어긋날 길은 없다.
    """
    p = Path(settings.DB_PATH).expanduser()
    return p if p.is_absolute() else paths.repo_root() / p


def _ro_conn() -> sqlite3.Connection:
    """읽기 전용 커넥션. `mode=ro` URI 라 쓰기는 `OperationalError` 로 터진다.

    호출 전에 파일 존재를 확인해야 한다 — `mode=ro` 는 파일이 없으면 열기 자체가 실패한다
    (그게 의도다: 읽기 경로가 파일을 만들지 않는다).
    """
    cx = sqlite3.connect(f"file:{db_path()}?mode=ro", uri=True, timeout=5)
    cx.row_factory = sqlite3.Row
    return cx


def _묶음크기() -> int:
    """`IN (...)` 플레이스홀더를 쪼갤 단위. SQLite 변수 상한 방어다."""
    try:
        return max(1, int(settings.cfg("mcp_batch_size",
                                       settings.DEFAULTS["mcp_batch_size"])))
    except (TypeError, ValueError):
        return max(1, int(settings.DEFAULTS["mcp_batch_size"]))


# ── 인덱스 조회 ─────────────────────────────────────────────────────────────

def lookup(smartstores) -> dict:
    """`{smartstore: {product_id, market_group_id, observed_at, unresolved}}`.

    **적힌 값을 꺼내 줄 뿐 판정하지 않는다.** 여기 나왔다고 해소가 아니다 —
    `join.py` 의 재검증을 거쳐야 비로소 `히트` 다 (JOIN-04).

    DB 파일이 없으면 `{}` 다. **만들지 않는다.**
    같은 번호가 여러 번 관측됐으면 **최신 관측이 이긴다** — 물갈이로 재발급된 번호가
    옛 상품을 가리키면 안 된다 (D-04).
    """
    키들 = [str(s).strip() for s in (smartstores or []) if s and str(s).strip()]
    if not 키들:
        return {}
    if not db_path().is_file():
        return {}

    나온것: dict = {}
    묶음 = _묶음크기()
    try:
        cx = _ro_conn()
    except sqlite3.Error:
        # 파일이 있어도 못 열 수 있다(권한·손상). 화면이 통째로 500 이 되는 것보다
        # "인덱스가 아직 없다" 로 보이는 쪽이 낫다 — 그 상태도 미조회로 떠야 맞다.
        return {}
    try:
        for i in range(0, len(키들), 묶음):
            조각 = 키들[i:i + 묶음]
            자리 = ",".join("?" * len(조각))
            # 오름차순으로 훑어 **뒤에 온 최신 관측이 앞을 덮게** 한다.
            행들 = cx.execute(
                "SELECT smartstore, product_id, market_group_id, group_total, "
                f"unresolved, observed_at FROM ss_index WHERE smartstore IN ({자리}) "
                "ORDER BY observed_at ASC", tuple(조각)).fetchall()
            for r in 행들:
                나온것[r["smartstore"]] = {
                    "product_id": r["product_id"],
                    "market_group_id": r["market_group_id"],
                    "group_total": r["group_total"],
                    "unresolved": int(r["unresolved"] or 0),
                    "observed_at": r["observed_at"],
                }
    except sqlite3.Error:
        return {}
    finally:
        cx.close()
    return 나온것


def indexed_group_ids() -> set:
    """인덱스에 한 줄이라도 있는 마켓그룹 ID 집합. 없으면 빈 집합."""
    if not db_path().is_file():
        return set()
    try:
        cx = _ro_conn()
    except sqlite3.Error:
        return set()
    try:
        return {r[0] for r in cx.execute(
            "SELECT DISTINCT market_group_id FROM ss_index") if r[0]}
    except sqlite3.Error:
        return set()
    finally:
        cx.close()


def group_health(group_ids) -> dict:
    """`{gid: {"행수", "미조회", "총상품수", "완결"}}` — 그룹이 **얼마나 훑렸는지**.

    `완결` 은 세 조건을 다 만족할 때만 참이다:
      · 행이 하나라도 있다 (인덱스에 없는 그룹을 "다 훑었다" 로 읽지 않는다)
      · `미조회` 가 0 이다 (429·타임아웃으로 못 본 상품이 없다)
      · 행수가 관측 시점의 `총상품수` 이상이다 (중간에 끊긴 잡을 걸러낸다)

    **이 값이 거짓인 그룹의 행은 화면에서 "인덱스 불완전"(시스템 사정)으로 떠야 한다.**
    "번호없음"(광고 쪽 오류)과 같은 칸에 담으면 용팀장이 멀쩡한 광고그룹을 지우러 간다 —
    이 페이즈 최대 오진 지점이다 (Pitfall 3 / D-18).

    D-18 로 인덱스에서 뺀 그룹은 여기서 `행수=0 · 완결=False` 로 나온다. 그게 정확하다 —
    "안 훑었다" 와 "훑었는데 못 찾았다" 는 다른 사실이다.
    """
    기대 = [str(g) for g in (group_ids or []) if g]
    if not 기대:
        return {}
    빈칸 = {"행수": 0, "미조회": 0, "총상품수": None, "완결": False}
    결과 = {g: dict(빈칸) for g in 기대}
    if not db_path().is_file():
        return 결과

    try:
        cx = _ro_conn()
    except sqlite3.Error:
        return 결과
    try:
        묶음 = _묶음크기()
        for i in range(0, len(기대), 묶음):
            조각 = 기대[i:i + 묶음]
            자리 = ",".join("?" * len(조각))
            행들 = cx.execute(
                "SELECT market_group_id, COUNT(*) AS 행수, "
                "SUM(unresolved) AS 미조회, MAX(group_total) AS 총상품수 "
                f"FROM ss_index WHERE market_group_id IN ({자리}) "
                "GROUP BY market_group_id", tuple(조각)).fetchall()
            for r in 행들:
                행수 = int(r["행수"] or 0)
                미조회 = int(r["미조회"] or 0)
                총상품수 = r["총상품수"]
                총상품수 = int(총상품수) if 총상품수 is not None else None
                결과[r["market_group_id"]] = {
                    "행수": 행수,
                    "미조회": 미조회,
                    "총상품수": 총상품수,
                    "완결": bool(행수 > 0 and 미조회 == 0
                                 and (총상품수 is None or 행수 >= 총상품수)),
                }
    except sqlite3.Error:
        return 결과
    finally:
        cx.close()
    return 결과


# ── 계정 확인 (ENG-08) ──────────────────────────────────────────────────────

def _프로필경로() -> Path:
    p = Path(str(settings.cfg("profile_path",
                              settings.DEFAULTS["profile_path"]))).expanduser()
    return p if p.is_absolute() else paths.repo_root() / p


def profile() -> dict | None:
    """계정 확인 산출물. 없거나 깨졌으면 `None` — **예외를 올리지 않는다.**

    올리면 보드가 통째로 500 이 되어 "계정 확인을 먼저 눌러라" 로 안내할 자리가 사라진다.
    읽은 dict 에서 `표시규칙` 은 버린다(프롬프트 인젝션 — 모듈 상단 주석).
    """
    경로 = _프로필경로()
    if not 경로.is_file():
        return None
    try:
        받은것 = json.loads(경로.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(받은것, dict):
        return None
    return {k: v for k, v in 받은것.items() if k not in _버릴필드}


def profile_ok(expected_nick, max_age_min) -> tuple:
    """`(통과여부, 사유)`. 불사자 잡을 만들기 **전에** 보는 사전 점검이다 (ENG-08).

    **사유에 기대 닉네임을 싣지 마라.** 이 문자열은 화면에 그대로 뜨고, 그 순간 기대
    닉네임이 사실상 리터럴이 된다(위협 T-3-16). 붙어 있는 계정 닉네임도 싣지 않는다 —
    "다른 값이 왔다" 는 사실까지만 말한다. 어느 계정인지는 보드 상단의 계정 표시가 답한다.

    막히는 경우 넷 — 전부 거부다:
      · 계정 확인을 한 번도 안 했다 (파일 없음·깨짐)
      · 기대 닉네임이 비어 있다 (`settings.cfg(..., required=True)` 가 먼저 터지는 게
        정상이지만, 여기도 닫아 둔다 — "비교할 값이 없으니 통과" 하는 가드는 없는 것이다)
      · 닉네임이 다르다
      · 확인시각이 없거나 `max_age_min` 을 넘겼다 (그 사이에 계정을 바꿨을 수 있다)
    """
    기대 = str(expected_nick or "").strip()
    if not 기대:
        return (False, "기대 계정이 설정에 없다 — workspace.toml 을 채워라")

    받은것 = profile()
    if not 받은것:
        return (False, "계정 확인 결과가 없다 — 계정 확인을 먼저 실행해라")

    붙은닉 = str(받은것.get("닉네임") or "").strip()
    if not 붙은닉:
        return (False, "계정 확인 결과에 닉네임이 없다 — 계정 확인을 다시 실행해라")
    if 붙은닉 != 기대:
        return (False, "붙어 있는 불사자 계정이 기대와 다르다 — "
                       "계정을 바꾼 뒤 계정 확인을 다시 실행해라")

    확인시각 = 받은것.get("확인시각")
    try:
        본때 = datetime.fromisoformat(str(확인시각))
    except (TypeError, ValueError):
        # 시각을 못 읽으면 통과시키지 않는다. **지어내지도 않는다** —
        # "언제 본 값인지 모른다" 는 "방금 봤다" 가 아니다.
        return (False, "계정 확인 시각을 읽을 수 없다 — 계정 확인을 다시 실행해라")

    지금 = datetime.now().astimezone()
    if 본때.tzinfo is None:
        본때 = 본때.astimezone()
    try:
        상한 = float(max_age_min)
    except (TypeError, ValueError):
        상한 = float(settings.DEFAULTS["profile_max_age_min"])
    if (지금 - 본때).total_seconds() > 상한 * 60:
        return (False, "계정 확인이 오래됐다 — 계정 확인을 다시 실행해라")

    return (True, "")
