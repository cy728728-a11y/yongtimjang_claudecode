#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""작업(잡) 라우터 — `webapp/jobs.py` 를 얇게 감싼다.

    POST /jobs/prep         새로 수집 (계정당 ~3분, 쓰기 가드를 탄다)   [쓰기 — 토큰 필요]
    POST /jobs/run          판정 다시 (디스크만, 초 단위)               [쓰기 — 토큰 필요]
    POST /jobs/bids/preview 입찰가 인상 미리보기 (dry-run, 0.066초)     [쓰기 — 토큰 필요]
    POST /jobs/bids/commit  입찰가 인상 실행                            [쓰기 — 토큰 필요]
    POST /jobs/revert/job   **이 작업분만** 되돌리기 (D-13)             [쓰기 — 토큰 필요]
    POST /jobs/revert/round **이 회차 전체** 되돌리기 (D-14)            [쓰기 — 토큰 필요]
    POST /jobs/bulsaja/profile  불사자 계정 확인 (0.14초, 읽기)         [쓰기 — 토큰 필요]
    POST /jobs/bulsaja/scan     회차 조인 스캔 (수 분, 읽기)            [쓰기 — 토큰 필요]
    POST /jobs/bulsaja/index    마켓그룹 인덱스 구축 (수 시간, 읽기)     [쓰기 — 토큰 필요]
    POST /jobs/banner/scan      배너 판정 스캔 (4분, MCP 0회·크레딧 0)   [쓰기 — 토큰 필요]
    POST /jobs/detail/estimate  상세 견적 (크레딧 0)                     [쓰기 — 토큰 필요]
    POST /jobs/detail/submit    상세 **접수** — 크레딧이 나간다          [쓰기 — 토큰 필요]
    POST /jobs/detail/poll      상세 이어서 확인 (--poll-only, 크레딧 0) [쓰기 — 토큰 필요]
    POST /jobs/market/preview   스마트스토어 반영 미리보기 (쓰기 0)       [쓰기 — 토큰 필요]
    POST /jobs/market/commit    스마트스토어 **반영** — 스토어가 바뀐다   [쓰기 — 토큰 필요]
    POST /jobs/market/poll      마켓 반영 이어서 확인 (--poll-only)       [쓰기 — 토큰 필요]
    GET  /jobs/revert/round/count  회차 전체 되돌리기 예상 건수         [읽기 — 쿠키]
    GET  /jobs/{id}         작업 상태 조각 (2초 폴링용)                 [읽기 — 쿠키]
    GET  /jobs/{id}/panel   작업 패널 조각 (SSE 배선 포함)              [읽기 — 쿠키]
    GET  /jobs/{id}/result  미리보기 표 조각 / JSON                     [읽기 — 쿠키]
    GET  /jobs/{id}/stream  진행 로그 SSE (전량 재생 + tail)            [읽기 — 쿠키]
    GET  /jobs              최근 작업 목록                              [읽기 — 쿠키]

**미리보기 라우트와 실행 라우트를 물리적으로 갈라 둔다** (T-1-06). 미리보기 경로에는
실행 플래그를 넘길 인자 자체가 없다 — 한 라우트가 플래그 하나로 갈리는 설계면,
그 플래그를 채우는 경로가 언젠가 생긴다. 실행은 Plan 01-08 의 **다른 라우트**다.

**모든 작업 생성은 POST 다 — GET 으로 만들면 Origin 방어가 통째로 무력화된다.**
교차 사이트 단순 GET(`<img src="http://127.0.0.1:.../jobs/bids/run">`)에는
`Origin` 헤더가 없어서 `security.guard` 가 아무것도 걸러내지 못한다. 즉 아무 웹페이지나
열어 두기만 해도 내 광고 입찰가가 올라갈 수 있다. 여기에 `@router.get` 으로
부수효과 있는 엔드포인트를 추가하는 순간 SAFE-01 이 죽는다(T-1-01b).
`webapp/tests/security_curl.sh` 의 V-SAFE-01d 가 이 파일의 GET 핸들러 본문을 실제로
훑어서 기계로 집행한다 — 그래서 **GET 핸들러는 이 파일 맨 아래**에 모아 둔다.

**불사자 잡 3종은 불사자에 아무것도 쓰지 않는데도 POST 이고 토큰이 필요하다.**
이유는 같다: 교차 사이트 단순 GET 에는 `Origin` 헤더가 없어 `security.guard` 가
아무것도 못 거른다. 남의 페이지를 열어 뒀다는 이유로 내 맥북에서 **수 시간짜리**
인덱스 잡이 뜨는 길을 만들 이유가 없다 (T-1-01b / T-3-25). "읽기니까 GET" 은
HTTP 의미론으로는 맞지만 이 앱의 방어 모델에서는 곧 무방비다.

**핸들러는 얇다.** 작업을 만드는 판단은 전부 `jobs.create_job` 안에 있다(D-17 / ENG-07):
회차 화이트리스트도, 쓰기 잡 전역 가드도, 대상 파일 쓰기도 거기다. 여기서 하는 일은
요청 모델을 풀고, 예외를 상태코드로 번역하고, 화면 조각이나 JSON 을 고르는 것뿐이다.
v2 의 APScheduler 는 이 라우터를 거치지 않고 같은 함수를 직접 부른다.

**클라이언트가 작업 종류를 문자열로 넘기지 못한다.** 경로마다 kind 가 고정이고,
임의 argv 를 태우는 `argv_override`(합성 잡)는 여기서 아예 닿지 않는다 (T-1-23).

**핸들러는 `async def` 가 아니라 `def` 다 — 스트림 하나만 빼고.** SQLite 와 파일 IO 가
동기라서 async 로 두면 이벤트 루프를 막고, 그러면 진행 로그 스트림이 같이 멈춘다(T-1-28).
스트림만 async 인 이유는 그게 **오래 살아 있는 커넥션**이라 스레드풀 자리를 몇 분씩
차지하면 안 되기 때문이다. 그 안에서도 sqlite 는 직접 만지지 않는다(`logtail` 이
스레드로 밀어낸다).
"""
import json
import shlex
import sqlite3
from datetime import date
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import (BaseModel, ConfigDict, Field, StringConstraints, ValidationError,
                      field_validator)
from sse_starlette import EventSourceResponse

from webapp import (banner, banner_store, board, flow, jobs, join, logtail,
                    market_gate_store, paths, security, settings)
from webapp.argv import Alias

router = APIRouter()

# 화면에 내보내는 상태 필드 **화이트리스트**. 행을 통째로 돌려주지 않는다 —
# argv·log_path 같은 내부 경로는 화면이 쓸 일이 없고, 새 컬럼이 생겼을 때
# 자동으로 밖으로 새는 설계를 만들지 않는다 (SAFE-03 의 투영 관례).
공개필드 = ("id", "kind", "status", "exit_code", "started_at", "ended_at",
            "run_dir", "target_count", "elapsed_sec")


class JobReq(BaseModel):
    """작업 요청. 회차와 계정만 받는다 — 경로도, 작업 종류도 받지 않는다.

    `run_dir` 은 여기서 검증하지 않는다. `jobs.create_job` 안의
    `paths.run_dir_path()` 화이트리스트가 본다 — 입구가 늘어나도 한 곳에서 막히게.
    `accounts` 는 `webapp/argv.py` 의 `Alias` 패턴을 그대로 쓴다(영숫자·`_`·`-`).
    """

    run_dir: str | None = None
    accounts: list[Alias] = []


async def 요청_풀기(request: Request) -> JobReq:
    """JSON 과 폼 인코딩을 **둘 다** 받아 `JobReq` 로 만든다.

    htmx 는 기본이 `application/x-www-form-urlencoded` 라 `hx-post` 가 JSON 을 안 보낸다.
    JSON 만 받으면 버튼이 422 로 튕기고, 폼만 받으면 v2 스케줄러·`curl` 이 불편해진다.
    입력 모양을 둘 받되 **검증은 한 곳(Pydantic)** 에서 한다 — 그게 진짜 관문이다.

    폼을 `request.form()` 으로 풀지 않는다. Starlette 은 urlencoded 폼에도
    `python-multipart` 를 요구해서(실측: `AssertionError: The python-multipart library
    must be installed`) 의존성이 하나 늘어난다. 파일 업로드가 없는 화면에 멀티파트
    파서를 깔 이유가 없다 — stdlib `parse_qsl` 로 충분하고, 이게 정확히 필요한 만큼이다.
    """
    본문 = await request.body()
    ctype = request.headers.get("content-type", "")

    if not 본문:
        값 = {}
    elif "application/json" in ctype:
        try:
            값 = json.loads(본문)
        except Exception:
            raise HTTPException(status_code=400, detail="요청 본문이 JSON 이 아니다")
        if not isinstance(값, dict):
            raise HTTPException(status_code=400, detail="요청 본문은 객체여야 한다")
    else:
        쌍 = parse_qsl(본문.decode("utf-8", "replace"))
        값 = {"run_dir": next((v for k, v in 쌍 if k == "run_dir" and v), None),
              "accounts": [v for k, v in 쌍 if k == "accounts" and v]}

    try:
        return JobReq(**값)
    except ValidationError as e:
        # 트레이스백·모델 내부 구조를 화면에 싣지 않는다 (ASVS V7). 건수만 알린다.
        raise HTTPException(status_code=400,
                            detail=f"요청 값이 잘못됐다 ({len(e.errors())}건)")


# adId 의 모양. `nad-` 로 시작하는 영숫자·`_`·`-` 만 (ASVS V5 / T-1-31).
# 길이 상한을 함께 둔다 — 패턴만 있으면 1MB 짜리 문자열이 그대로 통과한다.
# adId 는 **argv 에 직접 들어가지 않고 파일로** 건너간다(`_write_targets`).
# argv 길이 폭발과 `ps` 노출을 동시에 막는 구조다.
AdId = Annotated[str, StringConstraints(pattern=r"^nad-[A-Za-z0-9_-]{1,64}$")]

# 작업 id 의 모양(uuid4). 모양이 아니면 DB 를 만지기 전에 모델에서 걸린다.
JobId = Annotated[str, StringConstraints(
    pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")]


class BidsPreviewReq(BaseModel):
    """미리보기 요청. **경로도, 작업 종류도, 실행 플래그도 받지 않는다.**

    `run_dir` 검증은 `jobs.create_job` 안의 화이트리스트가 본다(입구가 늘어나도
    한 곳에서 막히게). 여기서는 모양만 본다.
    """

    run_dir: str
    ad_ids: list[AdId] = []

    @field_validator("ad_ids")
    @classmethod
    def _개수상한(cls, v):
        """리스트 길이 상한. **설정에서 읽는다** — 상수로 굳히면 설정을 고쳐도 안 따라온다.

        계정별 상한(D-08)의 계정 수만큼 여유를 둔다. 진짜 거부는 `flow.check_limits`
        가 계정별로 하고, 이건 그 앞단의 거친 방어선이다(본문 파싱 비용 제한).
        """
        한계 = settings.PER_ACCOUNT_LIMIT * 8
        if len(v) > 한계:
            raise ValueError(f"대상이 너무 많다 ({len(v)}건 > {한계}건)")
        return v


class BidsCommitReq(BaseModel):
    """실행 요청. **받는 것은 부모 미리보기 job_id 하나뿐이다.**

    `ad_ids` 를 받지 않는다 — 화면 상태에서 대상 목록을 다시 만드는 순간
    D-11 / FLOW-02 / T-1-06 이 깨지고, **본 것과 다른 게 실행된다.** 대상은
    부모 잡의 targets 파일에서만 온다. 모델에 그 필드가 아예 없는 것이
    "받지 않는다" 의 구조적 구현이다.
    """

    preview_job_id: JobId


class RevertJobReq(BaseModel):
    """**이 작업분만** 되돌리기 (D-13). 받는 것은 실행 잡의 id 하나뿐이다.

    `ad_ids` 를 받지 않는 이유는 `BidsCommitReq` 와 같다 — 대상은 그 실행 잡의
    **산출물**에서만 온다. 화면이 목록을 주면 "올라가지도 않은 소재를 내려라" 가
    성립해 버린다.
    """

    commit_job_id: JobId


class RevertRoundReq(BaseModel):
    """**이 회차 전체** 되돌리기 (D-14). 물리적으로 다른 라우트다.

    `confirmed_count` 는 화면이 **사용자에게 보여준 건수**다. 서버가 다시 세서 다르면
    409 — 사용자가 승인한 규모와 실제 규모가 갈라진 상태이기 때문이다. 타이핑을
    받지 않는 대신 이 대조가 확인 단계의 실효를 진다(FLOW-04 와 같은 판단).
    """

    run_dir: str
    confirmed_count: int


# 보드 행 키의 모양 — `"<계정alias>|<mallProductId>"` (board.js Tabulator index · `_스캔대상키`).
# 앞은 `Alias` 규칙(영숫자·`_`·`-`), 뒤는 스마트스토어 상품ID(숫자). 선행 하이픈은 막는다 —
# 이 값은 argv 로 안 가지만(파일로 건너간다) 모양 밖 값은 DB·파일 근처에도 안 보낸다.
보드키 = Annotated[str, StringConstraints(
    pattern=r"^[A-Za-z0-9_][A-Za-z0-9_-]{0,63}\|[0-9A-Za-z_]{1,40}$")]

# 한 번에 견적할 수 있는 상품 수 상한. 거친 방어선(본문 파싱 비용)이지 업무 규칙이 아니다 —
# 🔴 후보가 수십 건 규모다. 크레딧 상한은 견적 표가 사람에게 보여 주고 접수 때 `--max-credits` 가 진다.
상세견적_상한 = 200


class DetailEstimateReq(BaseModel):
    """상세 견적 요청. **받는 것은 회차와 보드 행 키뿐이다** (T-05-10).

    이미지 URL·productId·판매자상품코드를 받지 않는다 — 모델에 필드가 없는 것이 방어다.
    서버가 키로 보드 행을 다시 만들고, 관문(`banner.상세입력목록`)도 서버에서만 돈다.
    """

    run_dir: str
    keys: list[보드키]

    @field_validator("keys")
    @classmethod
    def _개수(cls, v):
        if not v:
            raise ValueError("고른 상품이 없다")
        if len(v) > 상세견적_상한:
            raise ValueError(f"한 번에 {상세견적_상한}건까지다 ({len(v)}건)")
        return v


class DetailSubmitReq(BaseModel):
    """상세 **접수** 요청. 받는 것은 **견적 잡 id 하나뿐이다** (D-14 · L-02 · T-05-15).

    대상도, 크레딧 상한도 받지 않는다 — 01-08 D-11(`BidsCommitReq`)과 같은 판단이다.
    대상은 부모 견적의 targets 파일, 상한은 부모 estimate.json 의 `집계.예상크레딧` 에서만 온다.
    화면이 숫자를 보내면 그 숫자를 고친 만큼 크레딧이 더 나간다 — 받을 필드 자체를 두지 않는다.
    모르는 필드는 Pydantic 기본대로 **무시**된다(`BidsCommitReq` 관례).
    """

    estimate_job_id: JobId


class DetailPollReq(BaseModel):
    """상세 **이어서 확인** 요청. 받는 것은 접수(또는 그 이전 이어서 확인) 잡 id 하나뿐이다.

    `--poll-only` 로만 돈다 — generate 0회 · 크레딧 0 (D-16 · L-03). 재접수 경로는 없다(D-18).
    """

    submit_job_id: JobId


# ── 마켓 수정업로드 요청 (Phase 6 / 06-03) ──────────────────────────────────
# 셋 다 **잡 id 하나만** 받는다. 상세 쪽(`DetailSubmitReq`)은 모르는 필드를 무시하지만, 여기는
# **거부(422)** 한다(extra=forbid) — 대상·상한·마켓을 실어 보내는 요청은 화면이 고장났거나 누가
# 게이트를 우회하려는 것이다. 조용히 무시하면 "보낸 대로 됐다" 고 오해한다(T-06-15 · T-06-16).

class MarketPreviewReq(BaseModel):
    """스마트스토어 반영 **미리보기** 요청 — 상세 접수(또는 그 이어서 확인) 잡 id 하나.

    대상 필드가 없는 이유(L-02): 대상은 그 상세 잡의 `detail_status.json` 에서 **완료** 항목만
    서버가 뽑는다. 화면이 목록을 보내면 AI 상세가 안 붙은 상품까지 반영 후보가 된다.
    마켓 필드가 없는 이유(L-07): CLI 가 SMARTSTORE 로 고정한다.
    """

    model_config = ConfigDict(extra="forbid")
    detail_job_id: JobId


class MarketCommitReq(BaseModel):
    """스마트스토어 **반영** 요청 — 미리보기 잡 id 하나. **버튼이 곧 승인이다.**

    대상도 상한도 받지 않는다(D-09 · L-02). 대상은 그 미리보기의 preview.json 반영가능 항목,
    상한은 서버의 `_마켓반영상한()` 이 정한다 — 게이트 판정 전엔 1이다. 화면이 숫자를 보내면
    그 숫자만큼 육안 확인 없이 스토어가 바뀐다.
    """

    model_config = ConfigDict(extra="forbid")
    preview_job_id: JobId


class MarketPollReq(BaseModel):
    """마켓 반영 **이어서 확인** 요청 — 반영(또는 그 이전 이어서 확인) 잡 id 하나.

    `--poll-only` 로만 돈다 — 새 접수 0회(D-08). 재반영 경로는 없다.
    """

    model_config = ConfigDict(extra="forbid")
    commit_job_id: JobId


class GateReq(BaseModel):
    """첫 1건 육안 확인 게이트 판정 (MARKET-02 · D-09 · D-10 · T-06-23).

    **판정 대상 상품 필드가 없다.** 판매자상품코드·productId 는 서버가 그 반영 잡의 체크포인트
    성공 항목에서 정한다 — 화면이 코드를 보내면 "본 적 없는 상품으로 게이트를 여는" 길이 생긴다.
    그래서 extra=forbid 로 실어 보내는 요청 자체를 422 로 거부한다.

    체크박스는 안 누르면 폼에서 빠진다 → 기본값 거짓. '정상' 은 셋 다 참일 때만 기록된다(라우트).
    """

    model_config = ConfigDict(extra="forbid")
    commit_job_id: JobId
    판정: Literal["정상", "이상"]
    체크_본문: bool = False
    체크_상하단: bool = False
    체크_기타필드: bool = False
    스토어교체여부: Literal["교체됨", "미교체", "모름"] = "모름"
    메모: str = Field(default="", max_length=500)


def _판정읽기(run_dir_name: str) -> dict:
    """회차의 판정 결과. **회차 이름은 화이트리스트를 통과한 것만** 경로가 된다.

    읽기 실패를 빈 dict 로 삼키지 않는다 — 그러면 "이 회차엔 대상이 없다" 가 되어
    사용자가 고른 것이 조용히 0건으로 바뀐다.
    """
    p = paths.run_dir_path(run_dir_name) / "result.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise ValueError(f"판정 결과를 못 읽었다 — 먼저 판정부터 해라: {type(e).__name__}")


def _투영(상태: dict) -> dict:
    return {k: 상태.get(k) for k in 공개필드}


def _산출물(상태: dict, 없을때: str) -> dict:
    """잡의 산출물 파일을 읽는다. **상태를 먼저 보고, 도는 중이면 읽지 않는다.**

    순서가 중요하다. 도는 중에는 `result_path` 파일이 아직 없어서 `read_preview` 가
    `FileNotFoundError` 를 `error` 에 채웠고, 템플릿은 `{% if error %}` 를 먼저 보므로
    **`running` 분기가 도달 불가능한 죽은 코드**였다. 화면에는 잘 돌고 있는 중에
    "산출물이 없거나 깨졌다" 와 내부 절대경로가 떴다.

    그게 왜 비싼가: `board.js` 의 폴링 한도가 끝나면(미리보기 150회=60초, 실행 3000회)
    아직 도는 중인데도 결과를 갈아끼운다. 사용자는 실패로 읽고 **다시 누른다** —
    409 로 막히긴 하지만 그 문구가 또 다른 오해를 만든다.

    `starting` 도 도는 중이다 (jobs.LIVE_STATUSES).
    """
    if (상태 or {}).get("status") in jobs.LIVE_STATUSES:
        return {"accounts": {}, "blind": [], "error": None, "running": True}
    경로 = 상태.get("result_path") if 상태 else None
    if not 경로:
        return {"accounts": {}, "blind": [], "error": 없을때, "running": False}
    읽은것 = flow.read_preview(Path(경로))
    읽은것.setdefault("running", False)
    return 읽은것


def _미리보기표ctx(상태: dict) -> dict:
    """미리보기 표 조각이 쓰는 값. 전부 CLI 산출물에서 읽어 **표시만** 한다."""
    미리보기 = _산출물(상태, "이 작업에는 산출물이 없다")
    return {
        "job": _투영(상태),
        "rows": flow.preview_rows(미리보기),
        "total": flow.total_rows(미리보기),
        "counts": flow.summarize_counts(미리보기),
        "raise_total": flow.raise_total(미리보기),
        "blind": 미리보기.get("blind") or [],
        "error": 미리보기.get("error"),
        # 도는 중인지를 **산출물 읽기가 아니라 잡 상태**에서 받는다 (_산출물 참조)
        "running": bool(미리보기.get("running")),
        "limit": flow.PREVIEW_ROW_LIMIT,
    }


def _상세견적ctx(상태: dict) -> dict:
    """견적 표 조각이 쓰는 값. **숫자는 전부 파일 값이다** — 템플릿에서 계산하지 않는다.

    CLI 의 estimate.json(항목·집계·계정·잔액) + 같은 잡 targets 파일의 `선택`·`제외`
    (웹앱 관문이 뺀 것). 도는 중이면 읽지 않는다(`_산출물` 규율).
    """
    기본 = {"job": _투영(상태 or {}), "running": False, "error": None,
            "항목": [], "집계": {}, "계정": None, "잔액": None, "per_credit": None,
            "선택": None, "관문제외": 0, "제외": []}
    if (상태 or {}).get("status") in jobs.LIVE_STATUSES:
        return {**기본, "running": True}
    try:
        대상 = json.loads(jobs.targets_path_of(상태["id"]).read_text(encoding="utf-8"))
        제외 = [x for x in (대상.get("제외") or []) if isinstance(x, dict)]
        기본.update({"선택": 대상.get("선택"), "제외": 제외, "관문제외": len(제외)})
    except Exception:
        pass                                  # 제외 목록이 없어도 견적 숫자는 보인다
    경로 = (상태 or {}).get("result_path")
    if not 경로:
        return {**기본, "error": "이 작업에는 산출물이 없다"}
    try:
        견적 = json.loads(Path(경로).read_text(encoding="utf-8"))
        if not isinstance(견적, dict):
            raise ValueError("모양이 dict 가 아니다")
    except Exception as e:
        # 종료코드 4(계정 불일치)·2(입력 오류)면 산출물이 없다. 로그를 보라고 안내한다.
        return {**기본, "error": f"견적 산출물이 없거나 깨졌다 — 진행 로그를 봐라 "
                                 f"(종료코드 {상태.get('exit_code')}, {type(e).__name__})"}
    기본.update({"항목": [x for x in (견적.get("항목") or []) if isinstance(x, dict)],
                "집계": 견적.get("집계") or {}, "계정": 견적.get("계정"),
                "잔액": 견적.get("잔액"), "per_credit": 견적.get("per_credit")})
    return 기본


def _상세폴더_of(상태: dict) -> Path | None:
    """상세 접수·이어서 확인 잡의 detail 폴더. **산출물 경로의 부모다** — 지어내지 않는다.

    `jobs._상세폴더` 가 부모 체인으로 푼 폴더에 `summary_<잡id>.json` 을 두므로(05-03),
    그 부모가 곧 `detail_status.json` 이 사는 곳이다.
    """
    경로 = (상태 or {}).get("result_path")
    return Path(경로).parent if 경로 else None


def _상세체크포인트(폴더: Path | None) -> dict | None:
    """`detail_status.json` — **결과의 정본**(D-16 · D-19). 없거나 깨졌으면 None."""
    if 폴더 is None:
        return None
    try:
        문서 = json.loads((폴더 / "detail_status.json").read_text(encoding="utf-8"))
    except Exception:
        return None
    return 문서 if isinstance(문서, dict) else None


def _완료말(s: str) -> bool:
    # detail_batch.is_done 과 같은 낱말 — CLI 의 체크포인트 어휘를 **읽기만** 한다
    return any(w in s for w in ("완료", "성공", "complete", "done", "success"))


def _실패말(s: str) -> bool:
    # detail_batch.is_failed 와 같은 낱말
    return any(w in s for w in ("실패", "오류", "취소", "fail", "error", "cancel"))


def _상세항목상태(v: dict | None) -> str:
    """체크포인트 한 항목 → 화면 상태. detail_batch `_요약상태` 와 같은 규칙이다.

    CLI 의 summary 를 두고 굳이 여기서 다시 읽는 이유: summary 는 **잡이 끝날 때만** 쓰인다.
    잡이 orphaned(서버 재시작)거나 폴링 도중이면 summary 가 없거나 낡았고, 그때도 사람은
    "무엇이 접수됐고 무엇이 남았나" 를 봐야 이어서 확인을 누를 수 있다.
    """
    v = v or {}
    st = str(v.get("status") or "")
    if st == "완료(기작업)":
        return "기작업스킵"
    if st in ("태그미조회", "입력부족", "장수불일치", "접수실패"):
        return st
    if v.get("taskId"):
        if _완료말(st):
            return "완료"
        if _실패말(st):
            return "실패"
        return "폴링중"
    return "미접수"


def _상세미종결(체크: dict | None) -> int:
    """taskId 가 있고 완료·실패·장수불일치가 아닌 건 수 — detail_batch `_미종결` 과 같은 규칙."""
    return sum(1 for v in (체크 or {}).values()
               if isinstance(v, dict) and _상세항목상태(v) == "폴링중")


_마켓잡이름 = {"market_preview": "반영 미리보기", "market_commit": "반영",
              "market_poll": "반영 이어서 확인"}


def _마켓잡들(detail_job_id: str | None, 최대: int = 5) -> list[dict]:
    """이 상세 작업에서 나온 최근 마켓 미리보기·반영·이어서 확인 (최신순, 최대 `최대`개).

    브라우저를 닫았다 다시 열어도 상세 결과 표 아래에서 반영 결과·게이트로 돌아오는 진입점이다
    (SC-1 · SC-2). 미리보기는 접수 잡에서도, 그 이어서 확인 잡에서도 뜰 수 있으므로 **같은 접수
    체인 전체**(접수 + 그 밑의 이어서 확인들)의 미리보기를 모은다. 조회 실패는 빈 목록이다 —
    이 목록 때문에 상세 결과 표 전체가 깨지면 안 된다.
    """
    if not detail_job_id:
        return []
    try:
        # 접수 뿌리까지 거슬러 올라간다(poll → poll → submit)
        뿌리 = jobs.job_status(detail_job_id)
        for _ in range(50):
            if not 뿌리 or 뿌리.get("kind") != "detail_poll" or not 뿌리.get("parent_job_id"):
                break
            뿌리 = jobs.job_status(뿌리["parent_job_id"])
        if not 뿌리 or 뿌리.get("kind") not in ("detail_submit", "detail_poll"):
            return []
        상세들, 큐 = [뿌리["id"]], [뿌리["id"]]
        while 큐 and len(상세들) < 200:
            for c in jobs.children_of(큐.pop(), "detail_poll"):
                상세들.append(c["id"])
                큐.append(c["id"])
        모음: list[dict] = []
        for d in 상세들:
            for 미리 in jobs.children_of(d, "market_preview"):
                모음.append(미리)
                큐 = [미리["id"]]
                while 큐 and len(모음) < 500:
                    for c in jobs.children_of(큐.pop()):
                        if c.get("kind") in ("market_commit", "market_poll"):
                            모음.append(c)
                            큐.append(c["id"])
        모음.sort(key=lambda j: str(j.get("started_at") or ""), reverse=True)
        return [{"id": j["id"], "kind": j["kind"], "이름": _마켓잡이름.get(j["kind"], j["kind"]),
                 "started_at": j.get("started_at"), "status": j.get("status"),
                 "exit_code": j.get("exit_code")} for j in 모음[:최대]]
    except Exception as e:
        print(f"[마켓잡들] 조회 실패 — 빈 목록으로 둔다: {type(e).__name__}: {e}", flush=True)
        return []


def _상세결과ctx(상태: dict) -> dict:
    """상세 접수·이어서 확인 결과 표 (D-19 · D-18 · DETAIL-05/06/07).

    **정본은 `detail_status.json` 이다.** 잡의 종료코드가 없어도(orphaned) 체크포인트로
    항목 상태·미종결 수를 센다. summary(있으면)는 사유 보충용이고, 견적 예상 크레딧은 부모
    견적의 estimate.json 에서 읽어 **실제 접수분 기준 크레딧**과 나란히 보인다.
    숫자는 전부 여기서 만든다 — 템플릿에서 계산하지 않는다.
    """
    기본 = {"job": _투영(상태 or {}), "running": False, "error": None, "항목": [],
            "집계": {}, "예상크레딧": None, "per_credit": None, "미종결": 0,
            "이어서확인가능": False, "종료코드": (상태 or {}).get("exit_code"),
            "마켓잡들": []}
    if (상태 or {}).get("status") in jobs.LIVE_STATUSES:
        return {**기본, "running": True}
    기본["마켓잡들"] = _마켓잡들((상태 or {}).get("id"))

    폴더 = _상세폴더_of(상태)
    try:
        대상 = json.loads(Path(상태.get("targets_path") or "").read_text(encoding="utf-8"))
        입력 = [x for x in (대상.get("items") or []) if isinstance(x, dict)]
    except Exception:
        입력 = []
    견적 = {}
    if 폴더 is not None:
        try:
            견적 = json.loads((폴더 / "estimate.json").read_text(encoding="utf-8")) or {}
        except Exception:
            견적 = {}
    per_credit = 견적.get("per_credit") if isinstance(견적.get("per_credit"), int) else 5
    예상 = (견적.get("집계") or {}).get("예상크레딧") if isinstance(견적, dict) else None

    체크 = _상세체크포인트(폴더)
    if 체크 is None:
        return {**기본, "예상크레딧": 예상, "per_credit": per_credit,
                "error": f"체크포인트(detail_status.json)가 없다 — 접수 전에 멈췄다. "
                         f"진행 로그를 봐라 (종료코드 {상태.get('exit_code')})"}

    요약사유 = {}
    try:
        요약 = json.loads(Path(상태.get("result_path")).read_text(encoding="utf-8"))
        for h in (요약.get("항목") or []):
            if isinstance(h, dict) and h.get("productId"):
                요약사유[h["productId"]] = str(h.get("사유") or "")
    except Exception:
        pass                                   # 요약이 없어도 체크포인트로 충분하다

    행들 = []
    for it in 입력:
        pid = it.get("productId")
        v = 체크.get(pid) if isinstance(체크.get(pid), dict) else {}
        try:
            장수 = int(v.get("pages") or 0)
        except (TypeError, ValueError):
            장수 = 0
        tid = str(v.get("taskId") or "")
        행들.append({"productId": pid, "판매자상품코드": it.get("판매자상품코드"),
                     "상태": _상세항목상태(v), "장수": 장수,
                     "크레딧": 장수 * per_credit if tid else 0,
                     "사유": str(v.get("사유") or v.get("error") or 요약사유.get(pid) or ""),
                     # taskId 는 끝 8자리만 — 전체 값은 화면이 쓸 일이 없다(T-05-20)
                     "taskId": tid[-8:] or None})
    셈: dict[str, int] = {}
    for h in 행들:
        셈[h["상태"]] = 셈.get(h["상태"], 0) + 1
    집계 = {"접수": sum(1 for h in 행들 if h["taskId"]),
            "완료": 셈.get("완료", 0),
            "실패": 셈.get("실패", 0) + 셈.get("접수실패", 0) + 셈.get("장수불일치", 0),
            "스킵": 셈.get("기작업스킵", 0) + 셈.get("태그미조회", 0) + 셈.get("입력부족", 0),
            "폴링미완": 셈.get("폴링중", 0),
            "미접수": 셈.get("미접수", 0),
            # 실제 접수분 기준 재보고 — taskId 를 받은 건의 장수 × 단가 (견적 대비)
            "접수크레딧": sum(h["크레딧"] for h in 행들),
            "완료크레딧": sum(h["크레딧"] for h in 행들 if h["상태"] == "완료")}
    미종결 = _상세미종결({h["productId"]: 체크.get(h["productId"]) for h in 행들})
    return {**기본, "항목": 행들, "집계": 집계, "예상크레딧": 예상, "per_credit": per_credit,
            "미종결": 미종결, "이어서확인가능": 미종결 > 0}


# ── 마켓 수정업로드 조각 (Phase 6 / 06-03) ──────────────────────────────────

def _마켓반영상한() -> int:
    """이번 반영 1회의 상한 — **서버가 정한다. 요청에는 이 값이 없다** (D-09 · T-06-16).

    이 플랜(06-03) 시점엔 게이트 판정 저장소가 없으므로 **게이트 닫힘 = 1** 이다. 판정 전 반영은
    1건 — 첫 1건을 사람이 스토어에서 눈으로 본 뒤에만 나머지가 열린다(상하단 안내이미지 모순).
    06-04: 게이트 판정(`market_gate`)의 **최신 줄이 '정상'** 이면 설정 `market_update_max_items`
    (기본 20 · D-12), 아니면 1. 게이트는 1회성이다(D-09) — 한 번 정상이면 이후 미리보기들도 N 이다.
    최신이 '이상' 이면 여기서는 1 이지만 반영 라우트가 따로 400 으로 막는다(D-11).
    판정을 못 읽으면(DB 없음·손상) `통과()` 가 거짓 = 1 — 닫힌 쪽으로 떨어진다(T-06-24).

    상한 결정을 이 한 곳에 모아 두는 이유: 라우트·미리보기 표·버튼 문구가 각자 상한을 계산하면
    셋이 어긋나 화면은 "1건" 이라는데 서버는 20건을 보내는 일이 생긴다.
    """
    if not market_gate_store.통과():
        return 1
    try:
        n = int(settings.cfg("market_update_max_items",
                             settings.DEFAULTS["market_update_max_items"]))
    except (TypeError, ValueError):
        n = int(settings.DEFAULTS["market_update_max_items"])
    return max(1, n)


def _게이트요약(판정: dict | None) -> dict | None:
    """최신 판정 → 화면에 실을 필드만 (행을 통째로 내보내지 않는다)."""
    if not 판정:
        return None
    return {k: 판정.get(k) for k in ("판정", "기록시각", "판매자상품코드", "productId",
                                    "commit_job_id", "스토어교체여부", "메모")}


def _마켓폴더_of(상태: dict) -> Path | None:
    """마켓 잡의 market 폴더 — **산출물 경로의 부모다** (preview.json · summary_<id>.json)."""
    경로 = (상태 or {}).get("result_path")
    return Path(경로).parent if 경로 else None


class _체크포인트깨짐(Exception):
    """market_status.json 이 있는데 못 읽는다 — 빈 값으로 읽으면 이중 반영이다(06-02 Deviation 2)."""


def _마켓체크포인트(폴더: Path | None, *, 없으면=None) -> dict | None:
    """`market_status.json` 의 `items` — **결과의 정본**(D-13 · L-05).

    파일이 없으면 `없으면`(기본 None). **있는데 깨졌으면 `_체크포인트깨짐`** — 빈 dict 로 삼키면
    taskId 를 가진 상품을 "아직 안 보냈다" 로 읽고 다시 반영한다.
    """
    if 폴더 is None:
        return 없으면
    p = 폴더 / "market_status.json"
    if not p.is_file():
        return 없으면
    try:
        문서 = json.loads(p.read_text(encoding="utf-8"))
        items = 문서.get("items") if isinstance(문서, dict) else None
        if not isinstance(items, dict):
            raise ValueError("items 가 dict 가 아니다")
    except Exception as e:
        raise _체크포인트깨짐(f"market_status.json 이 깨졌다 ({type(e).__name__})")
    return items


def _마켓미리보기문서(폴더: Path | None) -> dict | None:
    if 폴더 is None:
        return None
    try:
        문서 = json.loads((폴더 / "preview.json").read_text(encoding="utf-8"))
    except Exception:
        return None
    return 문서 if isinstance(문서, dict) else None


def _마켓손댐(v: dict | None) -> bool:
    """체크포인트 항목이 이미 반영 경로를 탔는가 — taskId 가 있거나 접수·대기·성공이면 참.

    참인 항목은 다시 대상에 넣지 않는다(재반영 0 · D-08). 스킵(쓰기 전 멈춤)은 거짓 — 다음 반영에서
    다시 시도할 수 있다(06-02: confirm:false 예외는 쓰기 전이므로 재시도 가능).
    """
    if not isinstance(v, dict):
        return False
    return bool(v.get("taskId")) or str(v.get("status") or "") in ("접수", "대기", "성공", "실패")


def _마켓체크포인트_합침(폴더: Path | None, 체크: dict | None) -> dict:
    """이 미리보기의 체크포인트 + **같은 회차 형제 market 폴더들의 '손댄' 항목** (Quick 260930-m3).

    미리보기마다 `market_<미리보기id>/` 폴더가 새로 생긴다. 이 폴더 체크포인트만 보면 옛 미리보기에서
    이미 반영(성공·접수·대기·실패)된 상품을 모르고 다시 '이번 반영' 으로 넣는다 → 스토어에 두 번 나간다
    (06-06 P1). 그래서 같은 `web/` 아래 **모든** `market_*/market_status.json` 을 합친다.

    - 이 폴더 항목이 손댄 상태면 그대로 둔다(자기 기록이 우선).
    - 형제 항목은 `_마켓손댐` 인 것만 이월한다 — 스킵(쓰기 전 멈춤)은 재시도 가능하니 옮기지 않는다.
      형제가 여럿이면 '성공' 을 우선한다. 이월 항목엔 `이월출처`(폴더명)를 붙인다.
    - 불사자 서버엔 "이 상세가 이미 마켓에 반영됐다" 는 신호가 없다(workdata 는 채널상품번호만 준다)
      → 로컬 체크포인트 합집합이 유일한 근거다.
    - **형제 체크포인트가 깨졌으면 `_체크포인트깨짐`** — 빈 값으로 삼키면 이중 반영이다.
    """
    합침 = dict(체크 or {})
    if 폴더 is None:
        return 합침
    try:
        형제들 = sorted((p for p in 폴더.parent.glob("market_*/market_status.json")
                       if p.parent != 폴더), key=lambda p: p.parent.name)
    except OSError:
        형제들 = []
    for p in 형제들:
        try:
            형제 = _마켓체크포인트(p.parent, 없으면={}) or {}
        except _체크포인트깨짐:
            raise _체크포인트깨짐(f"형제 미리보기 체크포인트({p.parent.name}/market_status.json)가 "
                             f"깨졌다 — 이미 반영된 상품을 가려낼 수 없다")
        for pid, v in 형제.items():
            if not _마켓손댐(v):
                continue                     # 스킵 등 쓰기 전 멈춤 — 이월하지 않는다
            기존 = 합침.get(pid)
            if _마켓손댐(기존) and not 기존.get("이월출처"):
                continue                     # 이 폴더 자기 기록이 우선
            if (_마켓손댐(기존) and str(기존.get("status") or "") == "성공"
                    and str(v.get("status") or "") != "성공"):
                continue                     # 이미 '성공' 을 이월했다 — 성공이 이긴다
            합침[pid] = {**v, "이월출처": p.parent.name}
    return 합침


def _마켓대기수(체크: dict | None) -> int:
    """아직 종결 안 된 건 — 접수·대기. 이어서 확인이 받을 몫이다."""
    return sum(1 for v in (체크 or {}).values()
               if isinstance(v, dict) and str(v.get("status") or "") in ("접수", "대기"))


def _경로표시(x) -> dict:
    """백업 경로 → {경로 텍스트, 있음}. **내용은 읽지 않는다** — 존재만 본다(D-04 · T-06-19)."""
    경로 = str(x or "")
    try:
        있음 = bool(경로) and Path(경로).is_file()
    except OSError:
        있음 = False
    return {"경로": 경로, "있음": 있음}


_마켓종료코드안내 = {
    2: "입력 오류·확인모드 거부·쓰기의심(P0) 중 하나로 멈췄다",
    3: "대기 미완 — 실패 아님",
    4: "계정 불일치 — 계정 확인부터 해라",
    5: "상한 초과 시도 — 쓰기 전에 멈췄다",
}


def _마켓미리보기ctx(상태: dict) -> dict:
    """미리보기 표 조각 — preview.json 을 **그대로** 옮긴다. 판정은 CLI 몫이다.

    ⓐ·ⓑ 백업은 경로 문자열 + 파일 존재만 본다(D-04). 반영가능 중 앞 `_마켓반영상한()` 건이
    '이번 반영', 나머지는 게이트 닫힘이면 '게이트 대기', 열렸으면 '다음 회차'(D-12).
    """
    상한 = _마켓반영상한()
    게이트 = _게이트요약(market_gate_store.최신판정())
    기본 = {"job": _투영(상태 or {}), "running": False, "error": None, "항목": [], "집계": {},
            "계정": None, "상한": 상한, "남은반영가능": 0, "버튼문구": None, "중단": None,
            "게이트": 게이트}
    if (상태 or {}).get("status") in jobs.LIVE_STATUSES:
        return {**기본, "running": True}
    폴더 = _마켓폴더_of(상태)
    문서 = _마켓미리보기문서(폴더)
    if 문서 is None:
        코드 = (상태 or {}).get("exit_code")
        return {**기본, "error": f"미리보기 산출물(preview.json)이 없거나 깨졌다 — 진행 로그를 봐라 "
                                 f"(종료코드 {코드}: {_마켓종료코드안내.get(코드, '알 수 없음')})"}
    try:
        # 형제 미리보기에서 이미 반영된 상품까지 '반영됨' 으로 본다 (Quick 260930-m3)
        체크 = _마켓체크포인트_합침(폴더, _마켓체크포인트(폴더, 없으면={}) or {})
    except _체크포인트깨짐 as e:
        return {**기본, "error": str(e)}

    행들, 남은 = [], 0
    for it in 문서.get("items") or []:
        if not isinstance(it, dict):
            continue
        pid = it.get("productId")
        판정 = str(it.get("판정") or "")
        표시 = ""
        if 판정 == "반영가능":
            v = 체크.get(pid)
            if _마켓손댐(v):
                표시 = f"반영됨({v.get('status')})"
            else:
                남은 += 1
                표시 = ("이번 반영" if 남은 <= 상한
                        else ("게이트 대기" if 상한 == 1 else "다음 회차"))
        행들.append({"productId": pid, "판매자상품코드": it.get("판매자상품코드"),
                     "판정": 판정, "사유": str(it.get("사유") or ""),
                     "backup_a": _경로표시(it.get("backup_a")),
                     "backup_b": _경로표시(it.get("backup_b")),
                     "채널상품번호": it.get("채널상품번호"),
                     "상하단날짜": it.get("상하단날짜"),
                     "미리보기요약": str(it.get("미리보기요약") or ""),
                     "반영표시": 표시})
    중단 = 문서.get("중단")
    정상 = (상태 or {}).get("status") == "done" and (상태 or {}).get("exit_code") == 0 and not 중단
    버튼 = None
    # 최신 게이트 판정이 '이상' 이면 버튼을 그리지 않는다 — 라우트도 400 이다(D-11 · T-06-26)
    if 정상 and 남은 > 0 and not (게이트 and 게이트.get("판정") == "이상"):
        버튼 = ("첫 1건만 반영 (육안 확인 게이트)" if 상한 == 1
                else f"반영 실행 (최대 {상한}건)")
    return {**기본, "항목": 행들, "집계": 문서.get("집계") or {}, "계정": 문서.get("계정"),
            "남은반영가능": 남은, "버튼문구": 버튼, "중단": 중단}


def _마켓결과ctx(상태: dict) -> dict:
    """반영·이어서 확인 결과 표 (D-13 · L-05 · MARKET-01).

    **정본은 `market_status.json` 이다.** 잡이 orphaned 여도 체크포인트로 항목·대기 수를 센다.
    summary 는 사유 보충만. 미리보기의 반영가능인데 체크포인트에 없는 항목은 '미반영(게이트 대기)'
    행으로 붙인다 — 안 붙이면 사람은 "나머지는 어디 갔나" 를 모른다.
    """
    기본 = {"job": _투영(상태 or {}), "running": False, "error": None, "항목": [], "집계": {},
            "대기수": 0, "이어서확인가능": False, "market_dir": None, "게이트패널": None}
    if (상태 or {}).get("status") in jobs.LIVE_STATUSES:
        return {**기본, "running": True}
    폴더 = _마켓폴더_of(상태)
    try:
        체크 = _마켓체크포인트(폴더)
    except _체크포인트깨짐 as e:
        return {**기본, "error": f"{e} — 빈 표를 결과로 읽지 않게 표를 그리지 않는다"}
    if 체크 is None:
        코드 = (상태 or {}).get("exit_code")
        return {**기본, "error": f"체크포인트(market_status.json)가 없다 — 반영 전에 멈췄다. "
                                 f"진행 로그를 봐라 (종료코드 {코드}: "
                                 f"{_마켓종료코드안내.get(코드, '알 수 없음')})"}

    요약사유 = {}
    try:
        요약 = json.loads(Path(상태.get("result_path")).read_text(encoding="utf-8"))
        for h in (요약.get("items") or []):
            if isinstance(h, dict) and h.get("productId"):
                요약사유[h["productId"]] = str(h.get("사유") or "")
    except Exception:
        pass                                   # 요약이 없어도 체크포인트로 충분하다

    미리보기 = _마켓미리보기문서(폴더) or {}
    순서 = [it for it in (미리보기.get("items") or []) if isinstance(it, dict)]
    본것 = set()
    행들 = []

    def _행(pid, v: dict):
        st = str(v.get("status") or "")
        tid = str(v.get("taskId") or "")
        return {"productId": pid, "판매자상품코드": v.get("판매자상품코드"),
                "상태": "대기" if st in ("접수", "대기") else (st or "?"),
                "사유": str(v.get("사유") or 요약사유.get(pid) or ""),
                "backup_a": _경로표시(v.get("backup_a")),
                "backup_b": _경로표시(v.get("backup_b")),
                # 작업번호는 끝 8자리만 — 전체 값은 화면이 쓸 일이 없다(T-06-20)
                "taskId": tid[-8:] or None,
                "확정시각": v.get("확정시각")}

    for it in 순서:
        pid = it.get("productId")
        if pid in 체크 and isinstance(체크[pid], dict):
            행들.append(_행(pid, 체크[pid]))
            본것.add(pid)
        elif str(it.get("판정") or "") == "반영가능":
            행들.append({"productId": pid, "판매자상품코드": it.get("판매자상품코드"),
                         "상태": "미반영(게이트 대기)", "사유": "",
                         "backup_a": _경로표시(it.get("backup_a")),
                         "backup_b": _경로표시(it.get("backup_b")),
                         "taskId": None, "확정시각": None})
    for pid, v in 체크.items():
        if pid not in 본것 and isinstance(v, dict):
            행들.append(_행(pid, v))

    셈: dict[str, int] = {}
    for h in 행들:
        셈[h["상태"]] = 셈.get(h["상태"], 0) + 1
    집계 = {"성공": 셈.get("성공", 0), "실패": 셈.get("실패", 0), "스킵": 셈.get("스킵", 0),
            "대기": 셈.get("대기", 0), "미반영": 셈.get("미반영(게이트 대기)", 0)}
    대기수 = _마켓대기수(체크)
    return {**기본, "항목": 행들, "집계": 집계, "대기수": 대기수,
            "이어서확인가능": 대기수 > 0, "market_dir": str(폴더) if 폴더 else None,
            "게이트패널": _게이트패널ctx(상태, 폴더, 체크, 미리보기)}


# ── 첫 1건 육안 확인 게이트 (Phase 6 / 06-04 · D-09 ~ D-12) ──────────────────

_MARKET_UPDATE_상대 = ".claude/skills/bulsaja-detail-page/scripts/market_update.py"
_스토어링크 = "https://smartstore.naver.com/main/products/{}"


def _첫성공(체크: dict | None, 미리보기: dict | None) -> tuple[str, dict] | None:
    """체크포인트의 성공 항목 첫 건 — **미리보기 순서 기준**. 게이트가 보는 상품은 이것 하나다.

    화면 값은 믿지 않는다(T-06-23). 미리보기 순서에 없으면 체크포인트 순서로 보충한다.
    """
    체크 = 체크 or {}
    순서 = [it.get("productId") for it in ((미리보기 or {}).get("items") or [])
            if isinstance(it, dict)]
    for pid in 순서 + [p for p in 체크 if p not in 순서]:
        v = 체크.get(pid)
        if isinstance(v, dict) and str(v.get("status") or "") == "성공":
            return str(pid), v
    return None


def _미리보기잡_of(상태: dict) -> dict | None:
    """반영·이어서 확인 잡 → 부모 체인을 올라가 미리보기 잡. 없으면 None (최대 10단)."""
    지금 = 상태
    for _ in range(10):
        부모id = (지금 or {}).get("parent_job_id")
        if not 부모id:
            return None
        지금 = jobs.job_status(부모id)
        if 지금 is None:
            return None
        if 지금.get("kind") == "market_preview":
            return 지금
    return None


def _복원명령(폴더: Path | None, backup_a: str) -> list[str]:
    """그 상품의 복원 절차(D-05) — **명령 텍스트만.** 웹 복원 버튼은 없다(D-05 Deferred).

    미리보기(쓰기 0) → 반영 1건 순서. 닉은 설정값, 경로는 체크포인트의 ⓐ. shlex 로 감싸 붙여넣기 안전.
    """
    if 폴더 is None or not backup_a:
        return []
    try:
        닉 = str(settings.cfg("expected_bulsaja_nick", "") or "<계정닉>")
    except Exception:
        닉 = "<계정닉>"
    앞 = [".venv/bin/python3", _MARKET_UPDATE_상대, "--run-dir", str(폴더),
         "--expect-nick", 닉, "--restore-backup", str(backup_a)]
    return [shlex.join(앞 + ["--preview"]),
            shlex.join(앞 + ["--commit", "--max-items", "1",
                             "--backup-dir", str(폴더 / "before_market")])]


def _게이트패널ctx(상태: dict, 폴더: Path | None, 체크: dict | None,
               미리보기: dict | None) -> dict | None:
    """결과 표 위 고정 패널(D-10). 체크포인트 성공 ≥1 일 때만 그린다 — 없으면 None.

    최신 판정이 없으면 **판정 폼**(체크 3 · 정상/이상), 있으면 **판정 요약**. 요약이 '이상' 이면
    그 판정 상품의 복원 명령 텍스트, '정상' 이면 같은 미리보기의 남은 반영 버튼 정보를 싣는다.
    """
    첫 = _첫성공(체크, 미리보기)
    if 첫 is None:
        return None
    pid, v = 첫
    원문 = next((it for it in ((미리보기 or {}).get("items") or [])
                if isinstance(it, dict) and it.get("productId") == pid), {})
    번호 = str(원문.get("채널상품번호") or "").strip()
    최신 = _게이트요약(market_gate_store.최신판정())
    패널 = {"판정전": 최신 is None, "commit_job_id": (상태 or {}).get("id"),
            "판매자상품코드": v.get("판매자상품코드") or 원문.get("판매자상품코드"),
            "productId": pid, "채널상품번호": 번호 or None,
            # 번호가 숫자일 때만 링크를 조립한다 — 아니면 코드만(RESEARCH A6)
            "링크": _스토어링크.format(번호) if 번호.isdigit() else None,
            "상단이미지": 원문.get("상단이미지"), "하단이미지": 원문.get("하단이미지"),
            "상하단날짜": 원문.get("상하단날짜"),
            "backup_a": str(v.get("backup_a") or ""),
            "복원명령": _복원명령(폴더, str(v.get("backup_a") or "")),
            "최신": 최신, "preview_job_id": None, "남은반영가능": 0, "상한": 1}
    if 최신 and 최신.get("판정") == "이상":
        # 판정한 상품이 이 표의 상품과 다를 수 있다 — 복원 명령은 **판정 상품** 기준으로 다시 짠다
        if 최신.get("productId") != pid:
            판정잡 = jobs.job_status(str(최신.get("commit_job_id") or ""))
            판정폴더 = _마켓폴더_of(판정잡) if 판정잡 else None
            try:
                판정체크 = _마켓체크포인트(판정폴더, 없으면={}) or {}
            except _체크포인트깨짐:
                판정체크 = {}
            a = str((판정체크.get(최신.get("productId")) or {}).get("backup_a") or "")
            패널.update({"판매자상품코드": 최신.get("판매자상품코드"),
                         "productId": 최신.get("productId"),
                         "backup_a": a, "복원명령": _복원명령(판정폴더, a)})
    elif 최신 and 최신.get("판정") == "정상":
        미리잡 = _미리보기잡_of(상태)
        if 미리잡 is not None:
            try:
                합침 = _마켓체크포인트_합침(폴더, 체크)
            except _체크포인트깨짐:
                합침 = None                   # 못 가리면 남은 수를 모른다 — 0 으로 두고 버튼 안 그림
            남은 = 0 if 합침 is None else sum(
                1 for it in ((미리보기 or {}).get("items") or [])
                if isinstance(it, dict) and str(it.get("판정") or "") == "반영가능"
                and not _마켓손댐(합침.get(it.get("productId"))))
            패널.update({"preview_job_id": 미리잡.get("id"), "남은반영가능": 남은,
                         "상한": _마켓반영상한()})
    return 패널


def _실행표ctx(상태: dict) -> dict:
    """실행 결과 표 조각이 쓰는 값 (FLOW-05 / D-10).

    **종료코드를 성공의 근거로 삼지 않는다.** 이 명령은 광고 API 쓰기가 전량 실패해도
    정상 종료한다(RESEARCH §1.1) — 그래서 여기서 보는 것은 결과 파일의 항목별
    `result`/`error` 뿐이다.

    diff 는 **부모 미리보기 잡의 산출물**과 대조해서 만든다. 부모를 못 읽으면 그
    사실을 따로 실어 보낸다 — 대조를 건너뛴 것을 "달라진 게 없다" 로 보여주면
    D-10 이 거짓말이 된다.
    """
    결과 = _산출물(상태, "이 작업에는 산출물이 없다")
    부모 = jobs.job_status(상태["parent_job_id"]) if 상태.get("parent_job_id") else None
    미리보기 = _산출물(부모, "부모 미리보기 잡이 없다")
    return {
        "job": _투영(상태),
        "rows": flow.result_rows(결과),
        "total": flow.total_rows(결과),
        "result_counts": flow.result_counts(결과),
        "cli_totals": flow.cli_totals(결과),
        "succeeded": len(flow.succeeded_ad_ids(결과)),
        # CLI 가 중단한 계정. "성공 0건" 과 "백업이 깨져서 아예 안 올렸다" 는 다른 화면이다.
        "aborted": flow.aborted_accounts(결과),
        "diff": flow.diff_preview(미리보기, 결과),
        "preview_error": 미리보기.get("error"),
        "blind": 결과.get("blind") or [],
        "error": 결과.get("error"),
        "running": bool(결과.get("running")),
        "limit": flow.PREVIEW_ROW_LIMIT,
        **_되돌리기배너(상태),
    }


def _되돌리기배너(상태: dict) -> dict:
    """Pitfall 4 / OQ-2 — 인상일과 오늘이 다르면 경고를 띄울 근거를 실어 보낸다.

    **실행을 막지 않는다.** 입찰가 복원(PUT)은 날짜와 무관하게 동작한다 — 날짜 조건은
    `ledger.record_reverted` 의 `reverted` 플래그에만 걸린다. 넘기면 이력에 되돌림이
    안 남아 쿨다운 6일 동안 **재인상이 막히는 것**이지, 돈을 되돌리는 능력을 잃는 게
    아니다. Phase 1 은 CLI 로직을 안 고치고 이 배너로만 다룬다(OQ-2 확정).

    날짜는 잡의 `started_at` 에서 온다 — 웹앱이 따로 기록하지 않는다.
    """
    시작 = (상태 or {}).get("started_at") or ""
    인상일 = 시작[:10] if len(시작) >= 10 else None
    오늘 = date.today().isoformat()
    return {"raise_date": 인상일, "today": 오늘,
            "date_mismatch": bool(인상일) and 인상일 != 오늘}


def _되돌리기표ctx(상태: dict) -> dict:
    """되돌리기 결과 표가 쓰는 값 (BID-04 / FLOW-05 연장).

    인상 결과 표를 재사용하지 않는다 — 그 표의 컬럼은 `현재가 → 인상 후` 인데
    되돌리기에는 "인상 후" 가 없다. 같은 표로 그리면 **복원값이 인상값으로 읽힌다.**

    `from`(되돌리기 직전의 실제 입찰가)은 산출물에 없다. 소재 스냅샷은 인상 전에
    찍힌 것이라 지금 값이 아니고, 없는 숫자를 웹앱이 만들지 않는다(T-1-07 과 같은 규칙).
    """
    결과 = _산출물(상태, "이 작업에는 산출물이 없다")
    부모 = jobs.job_status(상태["parent_job_id"]) if 상태.get("parent_job_id") else None
    return {
        "job": _투영(상태),
        "rows": flow.result_rows(결과),
        "total": flow.total_rows(결과),
        "result_counts": flow.result_counts(결과),
        "cli_totals": flow.cli_totals(결과),
        "succeeded": len(flow.succeeded_ad_ids(결과)),
        "aborted": flow.aborted_accounts(결과),
        "전체되돌리기": 상태.get("kind") == "revert_all",
        "blind": 결과.get("blind") or [],
        "error": 결과.get("error"),
        "running": bool(결과.get("running")),
        "limit": flow.PREVIEW_ROW_LIMIT,
        **_되돌리기배너(부모 or 상태),
    }


def _응답(request: Request, 상태: dict, 전체: bool = True):
    """htmx 요청이면 HTML 조각을, 아니면 JSON 을 돌려준다.

    같은 엔드포인트가 두 모양을 내는 이유: 화면은 HTML 조각을 그대로 갈아끼우면
    되고(JS 0줄), 스케줄러·`curl` 은 JSON 이 편하다. 판단 기준은 htmx 가 붙이는
    `HX-Request` 헤더 하나다.

    **`전체` 가 조각의 크기를 가른다. 이게 SSE 와 폴링이 안 싸우게 하는 장치다.**
    작업을 새로 만들 때(POST)는 패널 전체를 준다 — 그래야 새 작업의 스트림이 열린다.
    2초 폴링(GET)에는 **상태 문단만** 준다: 폴링이 패널 전체를 갈아끼우면 그 안의
    SSE 커넥션이 2초마다 끊기고 다시 붙어, 로그가 계속 처음부터 다시 그려지고
    커넥션이 쌓인다(T-1-24). 폴링은 경과시간만 갱신하면 된다.
    """
    if not request.headers.get("hx-request"):
        return _투영(상태)

    from webapp.main import templates  # 지연 import — main 이 이 모듈을 먼저 부른다

    조각 = "_job_panel.html" if 전체 else "_job_status.html"
    return templates.TemplateResponse(request, 조각, {"job": 상태})


def _작업만들기(request: Request, kind: str, req: JobReq, **더):
    """POST 핸들러 3줄의 공통부. **kind 는 호출부가 고정한다** — 요청에서 오지 않는다.

    예외 → 상태코드 표. **`except` 의 순서가 곧 동작이다** (상속 관계가 있다):

      | 예외                       | 코드 | 뜻                                   |
      |----------------------------|------|--------------------------------------|
      | `jobs.AccountMismatchError`| 409  | 붙어 있는 불사자 계정이 다르다 (ENG-08) |
      | `jobs.BusyError`           | 409  | 지금은 때가 아니다 (같은 kind 중복 포함) |
      | `ValueError`               | 400  | 요청이 틀렸다 (모르는 회차 등)         |
      | `KeyError`                 | 500  | 설정이 비었다                          |
      | `RuntimeError`             | 500  | 그 밖의 서버 문제                      |

    `AccountMismatchError` 는 `ValueError` 를 **상속**하므로 반드시 그보다 **먼저**
    와야 한다. 뒤에 두면 영원히 400 으로 새고 "때가 아니다(409)" 와 "요청이
    틀렸다(400)" 의 구분이 사라진다 — 화면은 "회차를 다시 골라라" 로 안내하는데
    진짜 원인은 계정이다. `SameKindBusyError` 는 `BusyError` 상속이라 아래에서 함께 잡힌다.
    """
    try:
        job_id = jobs.create_job(kind, run_dir=req.run_dir, accounts=req.accounts, **더)
    except jobs.AccountMismatchError as e:
        # 409 — 요청은 멀쩡하다. 지금 붙어 있는 계정이 기대와 다를 뿐이다 (ENG-08).
        # **기대 닉네임은 싣지 않는다.** `profile_ok` 가 준 사유를 그대로 쓴다 (T-3-29).
        raise HTTPException(status_code=409, detail=str(e))
    except jobs.BusyError as e:
        # 409 = "지금은 안 된다". 400 이 아닌 이유: 요청이 틀린 게 아니라 때가 아니다.
        raise HTTPException(status_code=409,
                            detail=f"이미 도는 작업이 있다 — 끝나고 다시 눌러라 ({e})")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KeyError:
        # `settings.cfg(..., required=True)` 가 던진다. 사유를 지어내지 않고 고칠
        # 자리를 말한다 — 가드가 없는 채로 도는 것보다 500 이 낫다 (T-1-12).
        raise HTTPException(status_code=500,
                            detail="설정 `webapp.expected_bulsaja_nick` 이 비었다 — "
                                   "workspace.toml 의 [webapp] 에 채워라")
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return _응답(request, jobs.job_status(job_id))


@router.post("/jobs/prep")
def post_prep(request: Request, req: JobReq = Depends(요청_풀기)):
    """새로 수집. 계정당 ~3분이 걸리지만 **호출은 즉시 돌아온다**.

    `prep` 은 광고를 바꾸지 않는다 — 소재·통계를 새로 받아올 뿐이다. 다만
    "광고 API 에 아무것도 쓰지 않는다" 라고 말하면 틀리다: 통계를 받으려고
    `POST /stat-reports` 로 리포트 잡을 만든다(OQ-4 확정). 광고 설정은 불변이다.
    """
    return _작업만들기(request, "prep", req)


@router.post("/jobs/run")
def post_run(request: Request, req: JobReq = Depends(요청_풀기)):
    """판정 다시. 이미 받아 둔 스냅샷으로 6규칙을 다시 매긴다 — 디스크만 만지고 초 단위다."""
    return _작업만들기(request, "run", req)


@router.post("/jobs/bids/preview")
def post_bids_preview(request: Request, req: BidsPreviewReq):
    """입찰가 인상 **미리보기**. dry-run 이라 광고 API 를 한 번도 안 부른다.

    `--commit` 을 넘길 인자가 이 경로에 **없다** — 실행은 Plan 01-08 의 다른
    라우트다(T-1-06 의 구조적 방어). 여기서 하는 일은 셋뿐이다:

      ① 회차의 판정 결과를 읽어 **대상이 정말 규칙① 소재인지 다시 확인** (T-1-30)
      ② 계정별 상한 검사 (D-08)
      ③ `jobs.create_job` 호출 — 대상 파일 쓰기·argv 조립·가드는 전부 거기 안에 있다

    브라우저 선택 상태는 신뢰 경계 밖이다. ①이 없으면 화면을 고친 사람이 ②③ 소재나
    남의 계정 소재를 섞어 보낼 수 있고, CLI 는 그걸 조용히 버린다(화면은 "N건 처리"
    라고 말하는데 실제로는 M건인 상태).
    """
    try:
        rows = board.fold_products(_판정읽기(req.run_dir))
        계정별 = flow.collect_targets(rows, req.ad_ids)
        flow.check_limits(계정별)
        대상 = [adId for ids in 계정별.values() for adId in ids]
        job_id = jobs.create_job("bids_preview", run_dir=req.run_dir,
                                 accounts=sorted(계정별), only_ads=대상)
    except jobs.BusyError as e:
        raise HTTPException(status_code=409,
                            detail=f"이미 도는 작업이 있다 — 끝나고 다시 눌러라 ({e})")
    except flow.LimitError as e:
        # 400 이고 사유를 그대로 싣는다. 숫자를 숨기면 사용자가 "왜 거부됐지" 를
        # 코드에서 찾아야 한다 — 상한은 설정에서 바꿀 수 있는 값이다(D-08).
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # 화면은 이 id 로 작업 패널과 미리보기 표를 갈아끼운다.
    return {"job_id": job_id}


@router.post("/jobs/bids/commit")
def post_bids_commit(request: Request, req: BidsCommitReq):
    """입찰가 인상 **실행**. 여기서 처음으로 진짜 광고 입찰가가 바뀐다.

    **대상을 받지 않는다.** 부모 미리보기 잡의 targets 파일을 그대로 재사용한다
    (D-11 / FLOW-02). 화면이 다시 목록을 만들면, 미리보기를 본 뒤 필터를 바꾼
    만큼 본 것과 다른 게 실행된다 — 그 경로를 아예 만들지 않는다.

    순서에 의미가 있다:
      ① 부모 잡이 **미리보기** 인가 (아니면 대상 파일의 의미가 다르다)
      ② 부모 잡이 **끝났는가** (도는 중이면 사용자가 본 산출물이 아직 없다)
      ③ 부모의 대상 파일이 **아직 있는가** — 없으면 거부한다.
         **빈 목록으로 폴백하지 않는다**: 폴백하면 "아무것도 안 했는데 성공" 이 된다
      ④ `create_job` — 쓰기 잡 전역 가드·회차 화이트리스트는 전부 거기 안에 있다

    `bids_commit` 은 `WRITE_KINDS` 라 다른 쓰기 잡이 도는 중이면 409 다 (Pitfall 3).
    """
    부모 = jobs.job_status(req.preview_job_id)
    if 부모 is None or 부모.get("kind") != "bids_preview":
        # 404 가 아니라 400 이다 — 요청한 자원이 없는 게 아니라 **요청이 성립하지 않는다**.
        raise HTTPException(status_code=400,
                            detail="미리보기 작업이 아니다 — 먼저 미리보기부터 해라")
    if 부모.get("status") == "running":
        raise HTTPException(status_code=400,
                            detail="미리보기가 아직 안 끝났다 — 끝나고 다시 눌러라")
    if 부모.get("status") != "done":
        raise HTTPException(
            status_code=400,
            detail=f"미리보기가 정상으로 안 끝났다({부모.get('status')}) — 다시 미리보기부터 해라")

    대상파일 = 부모.get("targets_path")
    if not 대상파일 or not Path(대상파일).is_file():
        raise HTTPException(status_code=400,
                            detail="미리보기의 대상 파일이 없다 — 다시 미리보기부터 해라")

    try:
        job_id = jobs.create_job(
            "bids_commit", run_dir=부모.get("run_dir"),
            accounts=json.loads(부모.get("accounts") or "[]"),
            commit=True, parent_job_id=req.preview_job_id,
            targets_path_override=대상파일)
    except jobs.BusyError as e:
        raise HTTPException(status_code=409,
                            detail=f"이미 도는 쓰기 작업이 있다 — 끝나고 다시 눌러라 ({e})")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"job_id": job_id}


@router.post("/jobs/revert/job")
def post_revert_job(request: Request, req: RevertJobReq):
    """**이 작업분만** 되돌리기 (D-13 / T-1-08). 화면의 되돌리기가 타는 경로다.

    `--revert` 에 그냥 연결하지 않는다. `bids.run_revert` 는 `only_ads` 가 없으면
    `before_bids_<alias>.json` **전량**을 되돌리는데 그 백업은 회차 안에서 누적
    병합된다 — 5건 올리고 눌렀는데 회차 인상분 전부가 풀린다(D-12. 실측으로
    2,242건이 들어 있던 백업이 있다).

    순서에 의미가 있다:
      ① 부모가 **실행 잡**인가 (미리보기 잡의 대상 파일은 의미가 다르다)
      ② 부모가 아직 **도는 중**이면 거부 — 무엇이 올라갔는지 산출물이 아직 확정 전이다.
         **`done` 은 요구하지 않는다** — `failed`·`orphaned` 야말로 되돌려야 하는
         상태다(중간에 끊긴 실행). 산출물에 성공으로 적힌 것만 대상이 된다
      ③ 산출물의 성공 adId 만 추려 `targets_revert_<job>.json` (D-13)
      ④ **dry-run 선행** — CLI 에게 범위를 물어 `check_revert_scope` 를 통과시킨다.
         생략하지 않는다: CLAUDE.md 제약이고, Pitfall 2 를 실행 전에 잡는 유일한
         방법이다(0.07초, 네트워크 0 — T-1-42)
      ⑤ `create_job` — 쓰기 잡 전역 가드는 거기 안에 있다(Pitfall 3)

    **백업 파일은 읽지도 쓰지도 않는다** (T-1-40).
    """
    부모 = jobs.job_status(req.commit_job_id)
    if 부모 is None or 부모.get("kind") != "bids_commit":
        raise HTTPException(status_code=400,
                            detail="실행 작업이 아니다 — 되돌리기는 실행한 작업에만 건다")
    if 부모.get("status") == "running":
        raise HTTPException(status_code=400,
                            detail="실행이 아직 안 끝났다 — 무엇이 올라갔는지 모르는 채로 되돌릴 수 없다")

    try:
        대상파일 = flow.revert_targets_for_job(req.commit_job_id)
        기대 = len(json.loads(대상파일.read_text(encoding="utf-8")))
        범위 = flow.revert_dry_run(부모.get("run_dir"),
                                 accounts=json.loads(부모.get("accounts") or "[]"),
                                 only_ads=대상파일)
        flow.check_revert_scope(기대, 범위["targets"], 범위.get("by_account"))
        job_id = jobs.create_job(
            "revert_only", run_dir=부모.get("run_dir"),
            accounts=json.loads(부모.get("accounts") or "[]"),
            commit=True, parent_job_id=req.commit_job_id,
            targets_path_override=대상파일)
    except flow.ScopeError as e:
        # **ValueError 보다 먼저 잡는다.** 순서가 뒤집히면 "범위가 2,242건이다" 가
        # 그냥 "잘못된 요청" 으로 뭉개져 사고의 모양이 화면에서 사라진다.
        raise HTTPException(status_code=409, detail=f"되돌리기를 막았다 — {e}")
    except jobs.BusyError as e:
        raise HTTPException(status_code=409,
                            detail=f"이미 도는 쓰기 작업이 있다 — 끝나고 다시 눌러라 ({e})")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"job_id": job_id}


@router.post("/jobs/revert/round")
def post_revert_round(request: Request, req: RevertRoundReq):
    """**이 회차 전체** 되돌리기 (D-14). 화면에서 물리적으로 떨어진 다른 버튼이다.

    여기는 대상을 좁히지 않는다 — `--only-ads` 없이 `--revert` 다. 그래서 세 가지를
    먼저 통과해야 한다:

      ① 서버가 백업을 다시 세서 `confirmed_count` 와 같은가 (다르면 409 —
         화면이 사용자에게 보여준 규모와 실제 규모가 갈라졌다)
      ② dry-run 이 센 수와도 같은가 (다르면 409 — 웹앱이 읽은 백업과 CLI 가 고른
         대상이 다르다는 뜻이고, 그 상태로 회차 전체를 풀 수는 없다)
      ③ 쓰기 잡 전역 가드 (`create_job` 안)

    ①과 ②는 겹쳐 보이지만 다른 것을 본다 — ①은 **화면 대 서버**, ②는 **웹앱 대 CLI** 다.
    """
    try:
        계정별 = flow.revert_round_targets(req.run_dir)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    서버가센수 = sum(계정별.values())
    if 서버가센수 != req.confirmed_count:
        raise HTTPException(
            status_code=409,
            detail=(f"화면이 본 건수({req.confirmed_count:,})와 지금 건수"
                    f"({서버가센수:,})가 다르다 — 다시 확인해라"))

    try:
        범위 = flow.revert_dry_run(req.run_dir)
        flow.check_revert_scope(서버가센수, 범위["targets"], 범위.get("by_account"))
        job_id = jobs.create_job("revert_all", run_dir=req.run_dir, commit=True)
    except flow.ScopeError as e:
        raise HTTPException(status_code=409, detail=f"되돌리기를 막았다 — {e}")
    except jobs.BusyError as e:
        raise HTTPException(status_code=409,
                            detail=f"이미 도는 쓰기 작업이 있다 — 끝나고 다시 눌러라 ({e})")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"job_id": job_id}


# ── 불사자 잡 3종 (Phase 3) ─────────────────────────────────────────────────
# 셋 다 불사자에 **아무것도 쓰지 않고** 크레딧도 0 이다. 그런데도 POST 인 이유는
# 파일 상단 docstring 에 있다 — GET 이면 교차 사이트에서 수 시간짜리 잡이 뜬다.
#
# 대상은 **전부 서버가 계산한다.** 클라이언트가 groupId 나 상품 키를 보내는 인자가
# 아예 없다 (D-11 / T-3-27) — `JobReq` 에 그런 필드가 없는 것이 그 방어의 전부다.

# 불사자 잡의 대상 규칙은 **두 원천으로 나뉜다** (quick 260929-j2, 07-CONTEXT 용팀장 확인).
#   · 조인 스캔 대상 = ②③⑤ — 스캔은 몇 분짜리 읽기라 ② 를 넣어도 싸다. ② 를 빼면
#     ② 행에 조인(불사자 코드)이 안 붙어 썸네일 웹 견적이 **항상 0건**이 된다(07-04 스모크).
#   · 인덱스 범위 = ③⑤ — 인덱스는 **수 시간**짜리라 범위를 넓히면 그만큼 비용이 붙는다.
#     ③⑤ 는 ROADMAP Phase 3 범위 정의이고 `03-CONTEXT.md` §domain 실측 모수(130 + 64 = 194행).
# 둘을 한 튜플로 두면 ② 를 스캔에 넣는 순간 인덱스도 조용히 넓어진다 — 그래서 쪼갰다.
# `board.RULE_ORDER` 에서 가져오지 않는다 — 그건 **표시 순서**라 뜻이 다르고,
# 거기에 규칙이 하나 추가되는 날 이 잡의 대상이 조용히 늘어난다.
조인스캔_대상규칙 = ("②썸네일교체", "③원인분석", "⑤효자확정")
인덱스_대상규칙 = ("③원인분석", "⑤효자확정")


def _규칙행키(판정: dict, 규칙들: tuple[str, ...]) -> list[str]:
    """지정 규칙 행 → `"<계정alias>|<mallProductId>"` 목록. **중복은 없애고 순서는 지킨다.**

    같은 상품이 여러 규칙에 동시에 있을 수 있다(규칙이 배타적이지 않다 — ②와 ③이
    겹치기도 한다). 중복을 그대로 넘기면 같은 상품을 두 번 조회해 레이트리밋 예산을 버린다.
    정렬하지 않는 이유는 진행 로그의 순서가 판정 결과의 순서와 같아야 사람이
    "어디쯤 돌고 있나" 를 읽을 수 있기 때문이다.
    판정값은 CLI 산출물에서 읽기만 한다 — 규칙을 여기서 재판정하지 않는다.
    """
    키들: list[str] = []
    본것: set[str] = set()
    try:
        계정들 = ((판정 or {}).get("accounts") or {}).items()
    except AttributeError:
        # 판정 파일 모양이 깨졌다 — 대상 0건으로 돌려 호출부가 400 을 낸다
        return []
    for alias, 계정 in 계정들:
        규칙표 = (계정 or {}).get("rules") or {}
        for 규칙 in 규칙들:
            for r in (규칙표.get(규칙) or []):
                if not isinstance(r, dict):
                    continue
                mall = r.get("mallProductId")
                if not mall:
                    continue
                키 = f"{alias}|{mall}"
                if 키 in 본것:
                    continue
                본것.add(키)
                키들.append(키)
    return 키들


def _스캔대상키(판정: dict) -> list[str]:
    """조인 스캔 대상 — ②③⑤ 행 키."""
    return _규칙행키(판정, 조인스캔_대상규칙)


def _인덱스범위키(판정: dict) -> list[str]:
    """인덱스 구축 범위 — ③⑤ 행 키. ② 는 **일부러 뺀다** (수 시간 비용)."""
    return _규칙행키(판정, 인덱스_대상규칙)


@router.post("/jobs/bulsaja/profile")
def post_bulsaja_profile(request: Request, req: JobReq = Depends(요청_풀기)):
    """불사자 **계정 확인**. `bulsaja_my_profile` 한 번(실측 0.14초, 크레딧 0).

    회차도 대상도 없다 — 회차가 하나도 없는 상태에서도 눌러야 하는 버튼이다.

    **이 잡만 ENG-08 계정 가드를 타지 않는다.** 닭·달걀이기 때문이다: 가드가 보는
    프로필 파일을 만드는 게 바로 이 잡이라, 여기에도 가드를 걸면 계정이 틀렸을 때
    고칠 방법이 화면에서 사라진다. 가드 제외는 `jobs.BULSAJA_KINDS` 가 정한다 —
    라우트가 아니다(v2 스케줄러가 같은 함수를 부른다).
    """
    # `req.run_dir` 을 일부러 버린다. 화면이 회차를 같이 보내와도(htmx 의
    # `hx-include` 가 그렇게 한다) 이 잡은 회차를 모르는 게 맞다.
    return _작업만들기(request, "bulsaja_profile", JobReq())


@router.post("/jobs/bulsaja/scan")
def post_bulsaja_scan(request: Request, req: JobReq = Depends(요청_풀기)):
    """회차 **조인 스캔**. ②③⑤ 행을 불사자에서 다시 읽어 산출물에 적는다 (읽기·크레딧 0).

    대상은 여기서 만든다 — 화면이 고른 행 목록을 받지 않는다. 회차의 판정 결과가
    정본이고, 그래야 "본 것과 다른 게 돈다" 가 성립하지 않는다 (D-11 / FLOW-02).

    **빈 대상으로 잡을 만들지 않는다.** `create_job` 은 빈 목록도 파일로 떨구고
    자식은 `exit 2` 로 거부하지만, 그 잡은 레지스트리에 `failed` 로 남아 화면이
    "인덱스가 비었나?" 로 오독한다. 원인은 회차에 ②③⑤ 행이 없는 것뿐이고, 그건
    사용자가 고칠 것(다른 회차를 고르거나 판정을 다시 돌린다)이다.
    """
    if not req.run_dir:
        raise HTTPException(status_code=400, detail="조인 스캔에는 회차가 필요하다")
    try:
        대상 = _스캔대상키(_판정읽기(req.run_dir))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not 대상:
        raise HTTPException(
            status_code=400,
            detail="이 회차에 ②썸네일교체·③원인분석·⑤효자확정 행이 없다 — 스캔할 대상이 0건이다. "
                   "다른 회차를 고르거나 판정을 다시 돌려라")

    return _작업만들기(request, "bulsaja_scan", req, only_ads=대상)


@router.post("/jobs/bulsaja/index")
def post_bulsaja_index(request: Request, req: JobReq = Depends(요청_풀기)):
    """마켓그룹 **인덱스 구축**. 수십 분~수 시간이 걸리지만 호출은 즉시 돌아온다.

    훑을 그룹을 **서버가 계산한다** (D-11 / T-3-27): 회차 판정 → 보드 투영 →
    직전 스캔 산출물의 마켓그룹 목록과 조인 → `join.index_targets` 가 번호 기준으로
    중복 제거한 `groupId` 목록. 클라이언트가 그룹을 지정하는 인자는 없다.

    거부 둘 다 이유가 다르다:
      · 스캔 산출물이 없다 → **409.** 요청은 멀쩡하고 순서가 아직 아니다.
        마켓그룹 목록 없이 돌리면 대상이 빈 목록이 되고, 빈 목록을 "전량" 으로 읽는
        경로가 하나라도 생기면 75,335 상품(5시간 39분)을 통째로 훑는다
      · 계산 결과가 빈 목록이다 → **400.** 이을 번호가 하나도 없다는 뜻이다
        (광고그룹 번호를 먼저 고쳐야 한다 — 보드의 청소 목록이 그걸 말해 준다)

    **빈 목록이 전량이 되는 길은 3층으로 막혀 있다:** 여기 400 ·
    `jobs._build_argv` 의 ValueError · CLI 의 `exit 2`.

    `caffeinate -i` 프리픽스는 `jobs._build_argv` 가 붙인다. 라우트는 kind 만 고른다.
    """
    if not req.run_dir:
        raise HTTPException(status_code=400, detail="인덱스 구축에는 회차가 필요하다")

    마지막스캔 = jobs.latest_done("bulsaja_scan", req.run_dir)
    산출물 = (마지막스캔 or {}).get("result_path")
    if not 산출물:
        raise HTTPException(
            status_code=409,
            detail="먼저 조인 스캔을 돌려라 — 마켓그룹 목록이 있어야 훑을 대상을 계산한다. "
                   "목록 없이 돌리면 전 그룹이 대상이 된다")
    try:
        조인 = json.loads(Path(산출물).read_text(encoding="utf-8"))
    except Exception as e:
        # 파일이 사라졌거나 깨졌다. **빈 dict 로 삼키지 않는다** — 그러면 대상이
        # 0건이 되고 그게 "전량" 으로 읽히는 길이 열린다.
        raise HTTPException(status_code=409,
                            detail=f"조인 산출물을 못 읽었다 — 스캔을 다시 돌려라 "
                                   f"({type(e).__name__})")

    try:
        판정 = _판정읽기(req.run_dir)      # 한 번만 읽는다 — 두 번 읽으면 두 스냅샷이 된다
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 🔴 **③⑤ 행으로 먼저 좁힌다.** `board.fold_products` 는 6규칙 전부를 접어
    #    실측 6,945행을 준다(③⑤ 는 194행이다). 안 좁히면 `index_targets` 가
    #    41그룹(제외 후 40)을 내는데, ③⑤ 만 보면 31그룹(제외 후 30)이다 —
    #    작업 대상이 하나도 없는 마켓그룹 10개를 **수 시간 동안** 더 훑는다.
    #    이 페이즈가 D-18 로 2시간 7분을 깎아 낸 바로 그 비용이 도로 붙는다.
    #    좁히는 기준은 `_인덱스범위키`(③⑤)다 — 스캔 대상(②③⑤)과 **일부러 다르다.**
    #    ③⑤ 는 스캔 대상의 부분집합이라 인덱스한 것은 전부 스캔돼 있다 (quick 260929-j2).
    대상키 = set(_인덱스범위키(판정))
    rows = [r for r in board.fold_products(판정)
            if f"{r.get('acct')}|{r.get('mallProductId')}" in 대상키]
    if not rows:
        raise HTTPException(
            status_code=400,
            detail="이 회차에 ③원인분석·⑤효자확정 행이 없다 — 훑을 대상이 0건이다")

    # 제외 설정(D-18)의 정본은 `settings` 한 곳이다. 스캔 산출물의 `제외그룹` 은
    # `null`(= 모른다)이라 여기서 읽으면 안 된다 (03-04 결정).
    제외 = settings.cfg("index_excluded_groups",
                       settings.DEFAULTS["index_excluded_groups"])
    붙임 = join.attach(rows, 판정, 조인,
                      excluded=제외,
                      done_tags=settings.cfg("done_tags", settings.DEFAULTS["done_tags"]))
    대상 = join.index_targets(붙임, 조인, excluded=제외)
    if not 대상:
        raise HTTPException(
            status_code=400,
            detail="훑을 마켓그룹이 0개다 — **빈 목록은 전량이 아니다.** "
                   "광고그룹 번호가 불사자 마켓그룹과 하나도 안 이어졌다는 뜻이다. "
                   "보드의 광고 청소 목록을 먼저 처리해라")

    return _작업만들기(request, "bulsaja_index", req, only_ads=대상)


@router.post("/jobs/banner/scan")
def post_banner_scan(request: Request, req: JobReq = Depends(요청_풀기)):
    """**배너 판정 스캔.** 실측 4분 12초, 불사자 MCP 0회 · 크레딧 0.

    **대상은 여기서 만든다 — 화면이 고른 행 목록을 받지 않는다** (D-11 / FLOW-02).
    입력은 직전 성공한 조인 스캔의 산출물 파일 하나이고, 그 파일을 고르는 근거는
    잡 레지스트리다(`jobs.latest_done`). `web/join_*.json` 을 glob 으로 뒤지지 않는다 —
    파일이 있다는 것과 그 잡이 성공했다는 것은 다르다(중간에 죽은 잡도 반쯤 쓴 파일을
    남긴다). 그리고 **새로 쓰지 않고 그 파일을 그대로 가리킨다**(`targets_path_override`):
    다시 만들면 조인 스캔이 본 것과 배너 스캔이 읽는 것이 갈라진다.

    산출물이 없으면 **409 다 — 400 이 아니다.** 요청은 멀쩡하고 **순서가 아직 아니다**
    (`post_bulsaja_index` 의 판단 그대로). 400 으로 내리면 화면이 "요청 값을 고쳐라" 로
    안내하는데 사용자가 할 일은 조인 스캔 버튼을 먼저 누르는 것뿐이다.

    **이 잡은 전역 쓰기 가드를 안 탄다** — 4분 동안 입찰가 인상이 409 가 되면 사람이
    가드를 끈다(`jobs.WRITE_KINDS` 주석 / T-4-19). 대신 `SINGLETON_KINDS` 로 같은 잡
    중복만 막는다(271MB 이중 다운로드). 그 판단은 전부 `jobs.py` 에 있고 여기엔 없다.

    쓰기 메서드이므로 `security.guard` 미들웨어의 Origin + `sec-fetch-site` + 부팅 토큰
    3층을 **자동으로** 탄다. 라우트에 추가 코드가 없고, **예외를 만들지 않는다**(ASVS V4).
    `kind` 는 호출부가 고정한다 — 요청에서 오지 않는다(T-1-23).
    """
    if not req.run_dir:
        raise HTTPException(status_code=400, detail="배너 스캔에는 회차가 필요하다")

    마지막스캔 = jobs.latest_done("bulsaja_scan", req.run_dir)
    산출물 = (마지막스캔 or {}).get("result_path")
    if not 산출물:
        raise HTTPException(
            status_code=409,
            detail="조인 스캔을 먼저 돌려라 — 배너 스캔은 그 산출물을 입력으로 쓴다")
    # 파일이 사라진 경우를 여기서 잡는다. 안 잡으면 `_override_targets` 의 ValueError 가
    # 400 + "미리보기부터 다시 해라" 로 번역되는데, 이 흐름에 미리보기는 없다 —
    # 사용자가 엉뚱한 버튼을 찾으러 간다. 사유가 틀린 안내는 사유가 없는 것보다 나쁘다.
    if not Path(산출물).is_file():
        raise HTTPException(
            status_code=409,
            detail="조인 산출물 파일이 사라졌다 — 조인 스캔을 다시 돌려라")

    # 조인 산출물을 **읽지 않는다.** 대상 계산이 필요한 인덱스 잡과 다르다 —
    # 여기서는 파일 경로 하나를 그대로 자식에게 넘기고, 모양 검증은 자식이 한 번만
    # 한다(`banner_scan.py` 의 exit 2). 웹앱이 같은 파싱을 또 하면 진실이 둘이 된다(S-1).
    return _작업만들기(request, "banner_scan", req, targets_path_override=산출물)


# ── 상세 견적 (Phase 5 / DETAIL-01·02·05) ───────────────────────────────────

def _직전산출물(kind: str, run_dir: str, 없을때: str) -> dict:
    """`latest_done(kind)` 의 산출물 JSON. 없거나 깨졌으면 **409** — 순서가 아직 아니다.

    glob 으로 `web/*.json` 을 뒤지지 않는다(`post_banner_scan` 과 같은 판단) — 파일이 있다는
    것과 그 잡이 성공했다는 것은 다르다. 빈 dict 로 삼키지 않는다 — 대상이 0건이 된다.
    """
    경로 = (jobs.latest_done(kind, run_dir) or {}).get("result_path")
    if not 경로:
        raise HTTPException(status_code=409, detail=없을때)
    try:
        문서 = json.loads(Path(경로).read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=409,
                            detail=f"{없을때} (산출물을 못 읽었다: {type(e).__name__})")
    if not isinstance(문서, dict):
        raise HTTPException(status_code=409, detail=f"{없을때} (산출물 모양이 다르다)")
    return 문서


@router.post("/jobs/detail/estimate")
def post_detail_estimate(request: Request, req: DetailEstimateReq):
    """**상세 견적** — 크레딧 0. 고른 상품을 관문에 태워 통과분만 견적 잡으로 넘긴다.

    대상은 **서버가 다시 만든다** (D-06 · D-08 · T-05-10):
      ① 직전 성공 배너 스캔 산출물(없으면 409) — 관문이 읽는 장 판정·생성시각
      ② 직전 성공 조인 스캔 산출물(없으면 409) — 보드 행 재구성 + 판매자상품코드
      ③ 회차 판정 → `board.fold_products` → `join.attach` 로 보드 행을 다시 만들고
         요청 키로 고른다. **보드에 없는 키는 400** — 클라이언트가 대상을 지어내지 못한다
      ④ 행마다 관문(`banner.상세입력목록`). 못 지나간 상품은 **사유와 함께 제외** 목록으로
      ⑤ 통과 0건이면 400(상품별 사유) — 빈 inputs 로 잡을 만들지 않는다

    **배너 산출물 ↔ 보드 행 매칭은 판매자상품코드다.** 배너 산출물 상품에는 productId 가
    없고(실측: 판매자상품코드·불사자코드·타오바오상품번호만), 조인 산출물 행이 (acct,
    mallProductId) → 판매자상품코드를 준다. 실측 회차에서 배너 상품 62건의 판매자상품코드가
    62개로 유일하다. 작업 대상은 조인된 **사본 1개**(그 판매자상품코드의 productId)다(D-06).

    기작업·⚪ 여부로 **여기서 빼지 않는다** (D-05) — 사람이 골랐으면 CLI 가 실시간 태그로
    다시 판정해 스킵한다(D-12). 여기서 또 판정하면 기작업 판단이 두 곳이 된다.
    """
    if not req.run_dir:
        raise HTTPException(status_code=400, detail="상세 견적에는 회차가 필요하다")
    try:
        paths.run_dir_path(req.run_dir)          # 화이트리스트 — 파일을 읽기 전에
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    배너문서 = _직전산출물("banner_scan", req.run_dir,
                        "배너 스캔을 먼저 돌려라 — 상세 입력 이미지는 배너 판정 산출물에서 온다")
    조인문서 = _직전산출물("bulsaja_scan", req.run_dir,
                        "조인 스캔을 먼저 돌려라 — 보드 행을 불사자 상품에 이어야 대상이 정해진다")
    생성시각 = 배너문서.get("생성시각")
    if not isinstance(생성시각, str) or not 생성시각:
        raise HTTPException(status_code=409,
                            detail="배너 산출물에 생성시각이 없다 — 배너 스캔을 다시 돌려라")

    try:
        판정 = _판정읽기(req.run_dir)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    붙임 = join.attach(board.fold_products(판정), 판정, 조인문서,
                      excluded=settings.cfg("index_excluded_groups",
                                            settings.DEFAULTS["index_excluded_groups"]),
                      done_tags=settings.cfg("done_tags", settings.DEFAULTS["done_tags"]))
    행색인 = {f"{r.get('acct')}|{r.get('mallProductId')}": r for r in 붙임}
    모르는것 = [k for k in req.keys if k not in 행색인]
    if 모르는것:
        raise HTTPException(status_code=400,
                            detail=f"보드에 없는 상품이다 — 새로고침하고 다시 골라라: "
                                   f"{', '.join(모르는것[:5])}")

    관측색인 = {(o.get("acct"), o.get("mallProductId")): o
                for o in (조인문서.get("행") or []) if isinstance(o, dict)}
    배너색인 = {}
    for 상품 in (배너문서.get("상품") or []):
        if isinstance(상품, dict) and 상품.get("판매자상품코드"):
            배너색인.setdefault(str(상품["판매자상품코드"]), 상품)
    라벨 = banner_store.라벨읽기(req.run_dir)
    확인 = banner_store.확인시각읽기(req.run_dir)
    하한 = int(settings.cfg("banner_skip_min_keep", settings.DEFAULTS["banner_skip_min_keep"]))

    items: list[dict] = []
    제외: list[dict] = []
    본상품: set[str] = set()
    for 키 in dict.fromkeys(req.keys):         # 같은 키 두 번은 한 번으로(순서 유지)
        행 = 행색인[키]
        관측 = 관측색인.get((행.get("acct"), 행.get("mallProductId"))) or {}
        코드 = 관측.get("판매자상품코드")
        표기 = str(코드) if 코드 else 키

        def 뺀다(사유: str):
            제외.append({"판매자상품코드": 표기, "사유": 사유})

        if not 행.get("해소"):
            뺀다(f"불사자 상품에 안 이어졌다 — {행.get('사유') or '미해소'}")
            continue
        pid = 행.get("productId")
        if not pid or not 코드:
            뺀다("조인 결과에 productId·판매자상품코드가 없다 — 조인 스캔을 다시 돌려라")
            continue
        if pid in 본상품:
            뺀다("같은 불사자 상품이 이미 대상에 있다")
            continue
        상품 = 배너색인.get(str(코드))
        if 상품 is None:
            뺀다("배너 판정 산출물에 없다 — 배너 스캔을 다시 돌려라")
            continue
        try:
            상품키 = banner.상품키(상품)
            결과 = banner.상세입력목록(상품, 라벨=라벨.get(상품키) or {},
                                   확인시각=확인.get(상품키), 생성시각=생성시각,
                                   잔여하한=하한)
        except ValueError as e:
            뺀다(str(e))
            continue
        본상품.add(pid)
        items.append({"productId": pid, "판매자상품코드": str(코드),
                      "imageUrls": 결과["urls"], "제품이미지총수": 결과["총수"],
                      "잘림": 결과["잘림"]})

    if not items:
        사유들 = " / ".join(f"{x['판매자상품코드']}: {x['사유']}" for x in 제외[:20])
        raise HTTPException(status_code=400,
                            detail=f"관문을 통과한 상품이 0건이다 — 견적을 만들지 않았다. {사유들}")

    문서 = {"items": items, "제외": 제외, "선택": len(req.keys)}
    try:
        job_id = jobs.create_job("detail_estimate", run_dir=req.run_dir, detail_inputs=문서)
    except jobs.AccountMismatchError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except jobs.BusyError as e:
        raise HTTPException(status_code=409,
                            detail=f"이미 도는 작업이 있다 — 끝나고 다시 눌러라 ({e})")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KeyError:
        raise HTTPException(status_code=500,
                            detail="설정 `webapp.expected_bulsaja_nick` 이 비었다 — "
                                   "workspace.toml 의 [webapp] 에 채워라")
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"job_id": job_id}


def _상세잡만들기(kind: str, **kw) -> dict:
    """상세 접수·이어서 확인의 `create_job` 호출과 예외 번역. 순서는 `_작업만들기` 와 같다.

    `AccountMismatchError` 는 `ValueError` 상속이라 반드시 먼저 잡는다(409 ≠ 400).
    """
    try:
        job_id = jobs.create_job(kind, **kw)
    except jobs.AccountMismatchError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except jobs.BusyError as e:
        raise HTTPException(status_code=409,
                            detail=f"이미 도는 쓰기 작업이 있다 — 끝나고 다시 눌러라 ({e})")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KeyError:
        raise HTTPException(status_code=500,
                            detail="설정 `webapp.expected_bulsaja_nick` 이 비었다 — "
                                   "workspace.toml 의 [webapp] 에 채워라")
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"job_id": job_id}


@router.post("/jobs/detail/submit")
def post_detail_submit(request: Request, req: DetailSubmitReq):
    """상세 **접수** — 여기서 처음으로 크레딧이 나간다. **버튼이 곧 승인이다** (D-14 · L-02).

    승인의 근거는 사람이 본 견적 표다. 그래서 대상·상한을 **그 견적에서만** 가져온다:
      ① 부모가 **견적** 인가 · ② 도는 중이 아닌가 · ③ **정상으로 끝났는가** (`post_bids_commit` 3단)
      ④ 부모 targets 파일이 아직 있는가 — 없으면 거부. **빈 목록으로 폴백하지 않는다**
      ⑤ 부모 estimate.json 의 `집계.예상크레딧` 이 **양의 정수**인가 — 아니면 "접수할 게 없다"
      ⑥ 이 견적으로 이미 접수했는가 — 했으면 거부(아래)
      ⑦ `create_job("detail_submit", max_credits=예상크레딧)` — CLI 가 누적이 넘으면 exit 5

    ⑥ 의 이유: 두 번째 접수는 체크포인트에 taskId 가 없는 건(접수실패 등)을 **다시 접수**한다.
    그건 MVP 가 미뤄 둔 실패분 재접수(D-18)와 같다. 폴링이 덜 끝났으면 '이어서 확인'이고,
    다시 하고 싶으면 **새 견적**이다. 단, 앞선 접수가 실패했는데 체크포인트에 taskId 가 하나도
    없으면(계정 불일치 exit 4 등 — 아무것도 안 나갔다) 다시 누를 수 있다.
    """
    부모 = jobs.job_status(req.estimate_job_id)
    if 부모 is None or 부모.get("kind") != "detail_estimate":
        raise HTTPException(status_code=400, detail="견적 작업이 아니다 — 먼저 상세 견적부터 해라")
    if 부모.get("status") in jobs.LIVE_STATUSES:
        raise HTTPException(status_code=400, detail="견적이 아직 안 끝났다 — 끝나고 다시 눌러라")
    if 부모.get("status") != "done":
        raise HTTPException(
            status_code=400,
            detail=f"견적이 정상으로 안 끝났다({부모.get('status')}) — 견적부터 다시 해라")

    대상파일 = 부모.get("targets_path")
    if not 대상파일 or not Path(대상파일).is_file():
        raise HTTPException(status_code=400, detail="견적의 대상 파일이 없다 — 견적부터 다시 해라")
    try:
        견적 = json.loads(Path(부모.get("result_path") or "").read_text(encoding="utf-8"))
        예상 = (견적.get("집계") or {}).get("예상크레딧")
    except Exception:
        raise HTTPException(status_code=400,
                            detail="견적 산출물(estimate.json)이 없거나 깨졌다 — 견적부터 다시 해라")
    # bool 은 int 의 하위형이라 따로 막는다 — True 가 상한 1 이 되면 안 된다
    if not isinstance(예상, int) or isinstance(예상, bool) or 예상 <= 0:
        raise HTTPException(status_code=400,
                            detail="접수할 게 없다 — 견적의 예상 크레딧이 0 이다(전부 스킵)")

    폴더 = Path(부모["result_path"]).parent
    체크 = _상세체크포인트(폴더) or {}
    돈나감 = any(isinstance(v, dict) and v.get("taskId") for v in 체크.values())
    for 자식 in jobs.children_of(req.estimate_job_id, "detail_submit"):
        if 자식.get("status") != "failed" or 돈나감:
            raise HTTPException(
                status_code=400,
                detail="이 견적으로 이미 접수했다 — 폴링이 남았으면 '이어서 확인', "
                       "다시 하려면 새 견적부터")

    return _상세잡만들기("detail_submit", run_dir=부모.get("run_dir"),
                        parent_job_id=req.estimate_job_id,
                        targets_path_override=대상파일, max_credits=예상)


@router.post("/jobs/detail/poll")
def post_detail_poll(request: Request, req: DetailPollReq):
    """상세 **이어서 확인** — `--poll-only`. 접수(generate) 0회 · 크레딧 0 (D-16 · L-03).

    부모는 접수(`detail_submit`) 또는 그 이전 이어서 확인(`detail_poll`)이다. 허용하는 경우:
      · done + exit 3 — 폴링이 시간 상한에 닿았다(정상 경로)
      · orphaned 또는 done — **체크포인트에 미종결 건이 있으면** (서버 재시작 · Pitfall 4)
    그 밖(failed — 2 장수불일치 · 5 견적초과 · 4 계정불일치)은 400 — 사람이 판단할 영역이다.
    **재접수 경로는 만들지 않는다** (D-17 · D-18).
    """
    부모 = jobs.job_status(req.submit_job_id)
    if 부모 is None or 부모.get("kind") not in ("detail_submit", "detail_poll"):
        raise HTTPException(status_code=400, detail="상세 접수 작업이 아니다")
    if 부모.get("status") in jobs.LIVE_STATUSES:
        raise HTTPException(status_code=400, detail="아직 도는 중이다 — 끝나고 다시 눌러라")
    미종결 = _상세미종결(_상세체크포인트(_상세폴더_of(부모)))
    허용 = ((부모.get("status") == "done" and 부모.get("exit_code") == 3)
            or (부모.get("status") in ("done", "orphaned") and 미종결 > 0))
    if not 허용:
        if 부모.get("status") == "failed":
            raise HTTPException(
                status_code=400,
                detail=f"이 작업은 실패로 멈췄다(종료코드 {부모.get('exit_code')}) — "
                       "이어서 확인으로 덮지 않는다. 로그를 봐라")
        raise HTTPException(status_code=400, detail="이어서 확인할 게 없다 — 미종결 0건")

    대상파일 = 부모.get("targets_path")
    if not 대상파일 or not Path(대상파일).is_file():
        raise HTTPException(status_code=400, detail="접수의 대상 파일이 없다")
    return _상세잡만들기("detail_poll", run_dir=부모.get("run_dir"),
                        parent_job_id=req.submit_job_id, targets_path_override=대상파일)


# ── 마켓 수정업로드 (Phase 6 / 06-03) ───────────────────────────────────────

def _마켓잡만들기(kind: str, **kw) -> dict:
    """마켓 잡의 `create_job` 호출과 예외 번역 — `_상세잡만들기` 를 그대로 쓴다(409 가 400 보다 먼저)."""
    return _상세잡만들기(kind, **kw)


# 미리보기가 이만큼 낡으면 반영을 거부한다(T-06-22). 그 사이 상품·상세가 바뀌었을 수 있다 —
# CLI 가 반영 직전 workdata 를 다시 보지만(D-02), 사람이 승인한 '본 것' 자체가 낡았다.
_미리보기유효시간 = 24 * 3600


def _경과초(시각: str | None) -> float | None:
    if not 시각:
        return None
    try:
        from datetime import datetime as _dt
        return (_dt.now().astimezone() - _dt.fromisoformat(시각)).total_seconds()
    except (TypeError, ValueError):
        return None


@router.post("/jobs/market/preview")
def post_market_preview(request: Request, req: MarketPreviewReq):
    """스마트스토어 반영 **미리보기** — 쓰기 0 (D-01 · D-07).

      ① 부모가 상세 접수 또는 그 이어서 확인인가 · ② 도는 중이 아닌가
      ③ 부모 detail_status.json 에서 **완료** 항목만 — 실패·폴링중·기작업스킵은 뺀다
         (exit 3 done 도 허용한다 — 완료분만 뽑으므로 안전하다)
      ④ 0건이면 400 · 판매자상품코드는 부모 대상 파일에서 보충
    """
    부모 = jobs.job_status(req.detail_job_id)
    if 부모 is None or 부모.get("kind") not in ("detail_submit", "detail_poll"):
        raise HTTPException(status_code=400, detail="상세 접수 작업이 아니다 — 상세 결과 표에서 눌러라")
    if 부모.get("status") in jobs.LIVE_STATUSES:
        raise HTTPException(status_code=400, detail="상세 작업이 아직 도는 중이다 — 끝나고 다시 눌러라")

    체크 = _상세체크포인트(_상세폴더_of(부모)) or {}
    try:
        대상 = json.loads(Path(부모.get("targets_path") or "").read_text(encoding="utf-8"))
        입력 = [x for x in (대상.get("items") or []) if isinstance(x, dict)]
    except Exception:
        raise HTTPException(status_code=400, detail="상세 작업의 대상 파일이 없다")
    items = []
    for it in 입력:
        pid = it.get("productId")
        v = 체크.get(pid)
        if pid and isinstance(v, dict) and _상세항목상태(v) == "완료":
            items.append({"productId": str(pid),
                          "판매자상품코드": str(it.get("판매자상품코드") or "")})
    if not items:
        raise HTTPException(status_code=400,
                            detail="반영할 완료 항목이 없다 — AI 상세가 완료된 상품만 반영한다")
    return _마켓잡만들기("market_preview", run_dir=부모.get("run_dir"),
                        parent_job_id=req.detail_job_id, detail_inputs={"items": items})


@router.post("/jobs/market/commit")
def post_market_commit(request: Request, req: MarketCommitReq):
    """스마트스토어 **반영** — 여기서 스토어가 바뀐다. **버튼이 곧 승인이다** (D-07 · D-09 · L-02).

      ① 부모가 미리보기인가 · 도는 중이 아닌가 · done + exit 0 인가(미리보기가 멀쩡히 끝났나)
      ② 미리보기가 24시간 안인가 — 아니면 "새 미리보기부터"(T-06-22)
      ③ 같은 미리보기의 반영이 도는 중이면 400 · 이미 2번이면 400(게이트 전 1 + 통과 후 1, Pitfall 5)
         · **게이트 닫힘(상한 1)인데 앞선 반영이 무언가를 남겼으면 400** — 두 번 누르면 2건이다
      ④ 대상 = preview.json 반영가능 중 체크포인트가 아직 손대지 않은 것, 미리보기 순서대로
      ⑤ 앞 `_마켓반영상한()` 건만 대상 파일로 · create_job(max_items=그 상한) — CLI 도 exit 5 로 이중
    """
    # 게이트 최신 판정이 '이상' 이면 어떤 미리보기로도 반영하지 않는다(D-11 · T-06-26).
    # 자동 진행 없음 — 복원·재판정은 사람이 정한다.
    최신 = market_gate_store.최신판정()
    if 최신 and 최신.get("판정") == "이상":
        raise HTTPException(status_code=400,
                            detail="게이트 이상 판정 — 멈춤. 반영 결과 표의 복원 절차를 봐라")
    부모 = jobs.job_status(req.preview_job_id)
    if 부모 is None or 부모.get("kind") != "market_preview":
        raise HTTPException(status_code=400, detail="반영 미리보기 작업이 아니다 — 미리보기부터 해라")
    if 부모.get("status") in jobs.LIVE_STATUSES:
        raise HTTPException(status_code=400, detail="미리보기가 아직 안 끝났다 — 끝나고 다시 눌러라")
    if 부모.get("status") != "done" or 부모.get("exit_code") != 0:
        raise HTTPException(
            status_code=400,
            detail=f"미리보기가 정상으로 안 끝났다({부모.get('status')}, 종료코드 "
                   f"{부모.get('exit_code')}) — 새 미리보기부터")
    경과 = _경과초(부모.get("started_at"))
    if 경과 is None or 경과 > _미리보기유효시간:
        raise HTTPException(status_code=400,
                            detail="미리보기가 24시간을 넘었다 — 새 미리보기부터 해라")

    상한 = _마켓반영상한()
    폴더 = _마켓폴더_of(부모)
    try:
        체크 = _마켓체크포인트(폴더, 없으면={}) or {}
    except _체크포인트깨짐 as e:
        raise HTTPException(status_code=400, detail=f"{e} — 손으로 확인하기 전엔 반영하지 않는다")

    자식들 = jobs.children_of(req.preview_job_id, "market_commit")
    if any(c.get("status") in jobs.LIVE_STATUSES for c in 자식들):
        raise HTTPException(status_code=400, detail="이 미리보기의 반영이 도는 중이다 — 끝나고 봐라")
    if len(자식들) >= 2:
        raise HTTPException(status_code=400,
                            detail="이 미리보기로 이미 두 번 반영했다 — 남은 건은 새 미리보기부터")
    # 게이트 닫힘에서 두 번째를 허용하면 "1건 → 육안 확인" 이 "1건 + 1건" 이 된다(D-09).
    # 앞선 반영이 아무것도 남기지 않았으면(쓰기 전 실패 — 계정 불일치 등) 다시 누를 수 있다.
    if 상한 == 1 and 자식들 and any(_마켓손댐(v) for v in 체크.values()):
        raise HTTPException(status_code=400,
                            detail="첫 1건 반영이 이미 나갔다 — 스토어에서 눈으로 확인하고 "
                                   "게이트 판정을 기록한 뒤에 나머지가 열린다")
    # 형제 미리보기에서 이미 반영된 상품은 대상에서 뺀다 — 새 폴더는 옛 반영을 모른다(Quick 260930-m3).
    try:
        합침 = _마켓체크포인트_합침(폴더, 체크)
    except _체크포인트깨짐 as e:
        raise HTTPException(status_code=400, detail=f"{e} — 손으로 확인하기 전엔 반영하지 않는다")
    # 게이트 닫힘인데 형제 미리보기가 이미 첫 1건을 내보냈다 → 여기서 또 1건이면 판정 전 2건이다(D-09)
    if 상한 == 1 and any(isinstance(v, dict) and v.get("이월출처") for v in 합침.values()):
        raise HTTPException(status_code=400,
                            detail="다른 미리보기에서 첫 1건 반영이 이미 나갔다 — 그 반영 결과 표에서 "
                                   "게이트 판정을 기록한 뒤에 나머지가 열린다")

    문서 = _마켓미리보기문서(폴더)
    if 문서 is None:
        raise HTTPException(status_code=400, detail="미리보기 산출물(preview.json)이 없다 — 새 미리보기부터")
    남은 = []
    for it in 문서.get("items") or []:
        if not isinstance(it, dict) or str(it.get("판정") or "") != "반영가능":
            continue
        pid = it.get("productId")
        if not pid or _마켓손댐(합침.get(pid)):
            continue
        남은.append({"productId": str(pid), "판매자상품코드": str(it.get("판매자상품코드") or "")})
    if not 남은:
        raise HTTPException(status_code=400, detail="반영할 게 없다 — 반영가능 항목이 다 나갔거나 0건이다")

    return _마켓잡만들기("market_commit", run_dir=부모.get("run_dir"),
                        parent_job_id=req.preview_job_id,
                        detail_inputs={"items": 남은[:상한]}, max_items=상한)


@router.post("/jobs/market/poll")
def post_market_poll(request: Request, req: MarketPollReq):
    """마켓 반영 **이어서 확인** — `--poll-only`. 새 접수 0회 (D-08).

    허용: done + exit 3(대기 미완) · 또는 done/orphaned 인데 체크포인트에 대기(접수·대기) 건이 있다.
    그 밖(failed — 2 쓰기의심·입력 · 4 계정 · 5 상한)은 400 — 사람이 판단할 영역이다. 재반영 경로는 없다.
    """
    부모 = jobs.job_status(req.commit_job_id)
    if 부모 is None or 부모.get("kind") not in ("market_commit", "market_poll"):
        raise HTTPException(status_code=400, detail="마켓 반영 작업이 아니다")
    if 부모.get("status") in jobs.LIVE_STATUSES:
        raise HTTPException(status_code=400, detail="아직 도는 중이다 — 끝나고 다시 눌러라")
    try:
        대기 = _마켓대기수(_마켓체크포인트(_마켓폴더_of(부모)))
    except _체크포인트깨짐 as e:
        raise HTTPException(status_code=400, detail=str(e))
    허용 = ((부모.get("status") == "done" and 부모.get("exit_code") == 3)
            or (부모.get("status") in ("done", "orphaned") and 대기 > 0))
    if not 허용:
        if 부모.get("status") == "failed":
            raise HTTPException(
                status_code=400,
                detail=f"이 작업은 실패로 멈췄다(종료코드 {부모.get('exit_code')}) — "
                       "이어서 확인으로 덮지 않는다. 로그를 봐라")
        raise HTTPException(status_code=400, detail="이어서 확인할 게 없다 — 대기 0건")
    대상파일 = 부모.get("targets_path")
    if not 대상파일 or not Path(대상파일).is_file():
        raise HTTPException(status_code=400, detail="반영의 대상 파일이 없다")
    return _마켓잡만들기("market_poll", run_dir=부모.get("run_dir"),
                        parent_job_id=req.commit_job_id, targets_path_override=대상파일)


async def _게이트요청(request: Request) -> GateReq:
    """폼·JSON 둘 다 → GateReq. 본문을 기다려야 해서 **의존성만** async 다 (`요청_풀기` 와 같은 자리).

    라우트 본문은 `def` 로 둔다 — sqlite·파일 IO 가 이벤트 루프를 세우지 않게(T-1-28).
    """
    from webapp.routes.banner import _요청_풀기   # 폼·JSON 둘 다 받는 관용구(422 번역 포함)

    return await _요청_풀기(request, GateReq)


@router.post("/market/gate")
def post_market_gate(request: Request, 요청: GateReq = Depends(_게이트요청)):
    """첫 1건 육안 확인 판정 기록 (MARKET-02 · SC-2 · D-09 · D-10 · D-11). **잡을 만들지 않는다.**

      ① 폼·JSON 둘 다 → GateReq(extra=forbid — 상품 필드를 실어 보내면 422)
      ② `jobs.job_status` 로 먼저 조회(유령 running 수거 — RESEARCH Pitfall 8)
         · kind ∈ {market_commit, market_poll} 아니면 400 · 도는 중이면 400
      ③ 판정 대상 = 그 market 폴더 체크포인트의 **성공 항목 첫 건** (없으면 400) — 화면 값 안 믿음
      ④ '정상' 은 체크 3개가 모두 참일 때만 — 하나라도 거짓이면 400(T-06-23)
      ⑤ INSERT(누적) → 기록된 상태의 게이트 패널 조각 + `#market-commit-next` oob 조각
    토큰·Origin 은 `security.guard` 가 이미 봤다.
    """
    잡 = jobs.job_status(요청.commit_job_id)
    if 잡 is None or 잡.get("kind") not in ("market_commit", "market_poll"):
        raise HTTPException(status_code=400, detail="마켓 반영 작업이 아니다 — 반영 결과 표에서 눌러라")
    if 잡.get("status") in jobs.LIVE_STATUSES:
        raise HTTPException(status_code=400, detail="반영이 아직 도는 중이다 — 끝나고 판정해라")
    폴더 = _마켓폴더_of(잡)
    try:
        체크 = _마켓체크포인트(폴더, 없으면={}) or {}
    except _체크포인트깨짐 as e:
        raise HTTPException(status_code=400, detail=str(e))
    미리보기 = _마켓미리보기문서(폴더)
    첫 = _첫성공(체크, 미리보기)
    if 첫 is None:
        raise HTTPException(status_code=400,
                            detail="이 반영에 성공한 상품이 없다 — 스토어에 바뀐 게 없으니 판정할 것도 없다")
    pid, v = 첫
    if 요청.판정 == "정상" and not (요청.체크_본문 and 요청.체크_상하단 and 요청.체크_기타필드):
        raise HTTPException(status_code=400,
                            detail="정상은 확인 체크 3개를 모두 눌러야 기록된다 — "
                                   "하나라도 아니면 '이상 있음' 이다")
    try:
        market_gate_store.판정기록(요청.판정, str(v.get("판매자상품코드") or ""), pid,
                              요청.commit_job_id, 요청.스토어교체여부, 요청.메모)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except sqlite3.OperationalError:
        raise HTTPException(status_code=500,
                            detail="게이트 판정 테이블이 없다 — 서버를 한 번 재시작해라")

    from webapp.main import templates  # 지연 import — main 이 이 모듈을 먼저 부른다

    # 패널 + 반영 버튼 자리(oob) — 버튼 자리는 hx-target 밖이라 oob 로 같이 갈아끼운다
    # (Quick 260929-g1). 버튼 유무·상한·대상은 `_게이트패널ctx` 가 서버에서 정한다.
    return templates.TemplateResponse(request, "_market_gate_response.html",
                                      {"게이트패널": _게이트패널ctx(잡, 폴더, 체크, 미리보기)})


# ── 여기서부터 읽기 전용 ─────────────────────────────────────────────────────
# 아래 GET 들은 작업을 **만들지 않는다.** 상태를 읽어 화면에 옮길 뿐이다.
# 이 파일에서 GET 핸들러를 맨 아래 모아 두는 이유는 V-SAFE-01d 스캐너가
# GET 데코레이터 뒤의 본문을 훑기 때문이다 — 위쪽 POST 들과 섞으면 오탐이 난다.

@router.get("/jobs")
def get_jobs(request: Request):
    """최근 작업 20건. 화면이 고장났을 때 "뭐가 돌았나" 를 보는 창이다."""
    if not security.page_cookie_ok(request):
        return PlainTextResponse("토큰이 필요하다", status_code=403)
    return {"jobs": [_투영(j) for j in jobs.recent_jobs(20)]}


@router.get("/jobs/{job_id}")
def get_job(job_id: str, request: Request):
    """작업 상태 하나. 작업 패널이 2초마다 이걸 때린다.

    `elapsed_sec` 이 같이 나온다 — `bids --commit` 에는 진행률이 없어서(항목 수는
    알아도 CLI 가 몇 번째인지 알려주지 않는다) 화면은 **경과시간**으로 덮는다(OQ-3).
    """
    if not security.page_cookie_ok(request):
        return PlainTextResponse("토큰이 필요하다", status_code=403)
    상태 = jobs.job_status(job_id)
    if 상태 is None:
        raise HTTPException(status_code=404, detail="그런 작업이 없다")
    return _응답(request, 상태, 전체=False)


@router.get("/jobs/{job_id}/panel")
def get_job_panel(job_id: str, request: Request):
    """작업 패널 조각(진행 로그 배선 포함). 화면이 새 작업을 띄울 때 갈아끼운다.

    **아무것도 만들지 않는다.** 이미 있는 작업의 상태를 읽어 조각으로 그릴 뿐이다.
    `fetch` 로 접수한 작업은 htmx 응답 조각을 못 받으므로(POST 는 JSON 을 준다)
    화면이 이 창으로 패널을 가져간다.
    """
    if not security.page_cookie_ok(request):
        return PlainTextResponse("토큰이 필요하다", status_code=403)
    상태 = jobs.job_status(job_id)
    if 상태 is None:
        raise HTTPException(status_code=404, detail="그런 작업이 없다")
    return _응답(request, 상태, 전체=True)


@router.get("/jobs/{job_id}/result")
def get_job_result(job_id: str, request: Request, format: str | None = None):
    """산출물 → 표 조각 (미리보기: BID-03/D-05 · 실행: FLOW-05/D-10). **읽기 전용이다.**

    값은 CLI 산출물에서 읽어 **그대로** 표시한다. 웹앱이 입찰가를 다시 계산하면
    진실이 둘이 되고, ①행의 92%가 그룹입찰이라 거의 전량이 틀린다(T-1-07).

    작업이 아직 도는 중이면 표 대신 "도는 중" 을 준다 — 없는 파일을 읽어
    "0건" 으로 보여주면 사용자가 그걸 결과로 읽는다.

    `format=json` 은 표가 잘렸을 때 전체를 받는 창이다. htmx 헤더 유무로 모양을
    가르는 규칙은 그대로 두고, 브라우저 주소창에서도 JSON 을 받을 길만 연다.
    """
    if not security.page_cookie_ok(request):
        return PlainTextResponse("토큰이 필요하다", status_code=403)
    상태 = jobs.job_status(job_id)
    if 상태 is None:
        raise HTTPException(status_code=404, detail="그런 작업이 없다")

    # 작업 종류마다 다른 표다. 되돌리기 결과를 인상 표로 그리면 "인상 후" 칸에
    # 복원값이 들어가 **내린 것을 올린 것처럼** 보여준다.
    kind = 상태.get("kind")
    결과표 = {
        "bids_commit": ("_result_table.html", _실행표ctx),
        "revert_only": ("_revert_table.html", _되돌리기표ctx),
        "revert_all": ("_revert_table.html", _되돌리기표ctx),
        "detail_estimate": ("_detail_estimate_table.html", _상세견적ctx),
        "detail_submit": ("_detail_result_table.html", _상세결과ctx),
        "detail_poll": ("_detail_result_table.html", _상세결과ctx),
        "market_preview": ("_market_preview_table.html", _마켓미리보기ctx),
        "market_commit": ("_market_result_table.html", _마켓결과ctx),
        "market_poll": ("_market_result_table.html", _마켓결과ctx),
    }
    # Phase 7 트랙 모듈의 결과표를 병합한다(D-19). **지연 import** — 트랙 모듈이 이 모듈을
    # import 해도 순환이 안 생기게. **기존 키가 우선이다**: 트랙 모듈이 실수로 `bids_commit` 같은
    # 기존 kind 를 등록해도 그 표를 덮지 못한다 — 되돌리기 결과가 인상 표로 그려지는 부류의 사고를
    # 트랙 파일 하나가 일으키지 못하게(T-07-06).
    from webapp.routes import coupang as _쿠팡트랙, thumb as _썸네일트랙
    for 트랙표 in (_썸네일트랙.결과표, _쿠팡트랙.결과표):
        for 키, 값 in 트랙표.items():
            결과표.setdefault(키, 값)
    조각, ctx = 결과표.get(kind, ("_preview_table.html", _미리보기표ctx))
    ctx = ctx(상태)
    if format == "json" or not request.headers.get("hx-request"):
        return ctx

    from webapp.main import templates  # 지연 import — main 이 이 모듈을 먼저 부른다

    return templates.TemplateResponse(request, 조각, ctx)


@router.get("/jobs/revert/round/count")
def get_revert_round_count(request: Request, run_dir: str):
    """이 회차를 통째로 되돌리면 몇 건인가 (D-14 의 확인 단계). **읽기 전용이다.**

    백업 파일을 **열어서 세기만** 한다 — 쓰지 않는다(T-1-40). 페이지 로드 때가 아니라
    버튼을 누른 그 순간에 세는 이유는, 그 사이 다른 작업이 인상을 더했으면 사용자가
    승인하는 규모가 달라지기 때문이다. 이 수가 그대로 `confirmed_count` 로 돌아온다.
    """
    if not security.page_cookie_ok(request):
        return PlainTextResponse("토큰이 필요하다", status_code=403)
    try:
        계정별 = flow.revert_round_targets(run_dir)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"run_dir": run_dir, "by_account": 계정별, "total": sum(계정별.values())}


@router.get("/jobs/{job_id}/stream")
async def get_job_stream(job_id: str, request: Request):
    """진행 로그 SSE. 붙을 때마다 **처음부터** 흘리고 그 뒤를 tail 한다 (SC-03).

    **이 파일에서 유일한 `async def` 라우트다.** 수 분씩 살아 있는 커넥션이라
    스레드풀 자리를 차지하면 안 된다. 대신 이 안에서 sqlite·파일을 직접 만지지
    않는다 — `logtail.sse_generator` 가 blocking 호출을 스레드로 밀어낸다(T-1-28).

    **아무것도 쓰지 않는다.** `security_curl.sh` 의 V-SAFE-01d 가 GET 핸들러 본문을
    훑어 이걸 기계로 집행한다. 여기에 작업 생성이 끼어들면 Origin 방어가 통째로
    무너진다(T-1-01b) — 교차 사이트 단순 GET 에는 Origin 헤더가 없기 때문이다.

    `ping=15` 는 keepalive, `send_timeout=30` 은 죽은 클라이언트를 30초 넘게
    붙잡지 않기 위함이다. `Cache-Control: no-cache` 가 없으면 중간 캐시가 스트림을
    통째로 삼킨다(로컬엔 중간 캐시가 없지만, 이 헤더는 SSE 의 관례다).
    """
    if not security.page_cookie_ok(request):
        return PlainTextResponse("토큰이 필요하다", status_code=403)
    if jobs.job_status(job_id) is None:
        raise HTTPException(status_code=404, detail="그런 작업이 없다")

    return EventSourceResponse(
        logtail.sse_generator(job_id, request),
        ping=15, send_timeout=30,
        headers={"Cache-Control": "no-cache"})
