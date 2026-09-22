#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""배너 검수 화면 — 산출물 투영 · 썸네일 서빙 · 사람 라벨 기록.

    POST /banner/label                              장 하나를 뒤집는다     [쓰기 — 토큰 필요]
    POST /banner/confirm                            "이 줄 다 봤다"        [쓰기 — 토큰 필요]
    GET  /banner/review?run_dir=<회차>               검수 화면 렌더          [읽기 — 쿠키]
    GET  /banner/thumb/{회차}/{상품i}/{장i}            썸네일 1장             [읽기 — 쿠키]

**GET 둘은 서버 상태를 한 글자도 바꾸지 않는다.** 이건 취향이 아니라 방어의 전제다 —
교차 사이트 단순 GET(`<img src>`·`<script src>`·링크)에는 `Origin` 헤더가 없어서,
부수효과가 있는 GET 을 하나라도 만들면 `security.guard` 의 Origin 층이 통째로
무력화된다(T-1-01b / T-4-03). 라벨 기록을 `hx-get` 으로 바꾸지 마라.
`security_curl.sh` 의 V-SAFE-01d 가 이 파일의 GET 핸들러를 **호출관계로** 훑어 집행하고,
`test_routes_banner.py::test_GET_무부작용` 이 DB 행 수·mtime 불변을 기계로 확인한다.
그래서 **POST 를 위, GET 을 아래**에 모아 둔다 (`routes/jobs.py:31-42` 와 같은 규율).

**핸들러는 전부 `def` 다 — `async def` 가 아니다.** 썸네일 `FileResponse` 와 산출물 JSON
읽기가 blocking 파일 IO 이고, async 안에서 하면 이벤트 루프가 멈춰 SSE 진행 로그가 같이
끊긴다(T-1-28).

**판정을 여기서 재현하지 않는다** (S-1). 어휘군 매칭도 D-07/D-08 임계도 게이트 산식도
정본이 따로 있다 — 판정은 `banner_scan.py` 의 산출물 JSON, 게이트는 `banner.게이트집계`.
이 파일이 하는 일은 **읽어서 화이트리스트로 투영하는 것**뿐이다.

**CLI 를 실행하지 않는다.** 배너 스캔 접수는 `routes/jobs.py` 의 `POST /jobs/banner/scan`
이 한다 — 잡 생성을 여기 복제하지 마라.

**사람 판단 큐를 만들지 않는다** (D-09 / `minimize-user-queues`). 스킵은 배지 + 사유
문자열로 끝나고, 새 상태값도 큐 엔드포인트도 두지 않는다. 사람이 하는 일은 "뒤집기" 와
"다 봤다" 둘뿐이고 둘 다 즉시 확정된다.
"""
import json
import sqlite3
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import parse_qsl

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field, StringConstraints, ValidationError

from webapp import banner, banner_store, jobs, paths, security, settings

router = APIRouter()

# ── 입력 모양 ───────────────────────────────────────────────────────────────
#
# 패턴과 **길이 상한을 함께** 둔다 (`routes/jobs.py:126-137` 의 `AdId` 규율) —
# 패턴만 있으면 1MB 짜리 문자열이 그대로 통과해 DB 로 간다.
# 두 값은 제약이 같지만 **타입을 따로 둔다**: 뜻이 다른 두 값이 한 타입을 공유하면
# 한쪽 규칙을 고칠 때 다른 쪽이 소리 없이 따라 바뀐다(`argv.PlainArg` 와 같은 판단).
타오바오번호 = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
판매코드 = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$")]

# 한 상품의 상세 이미지 장수 상한. 실측 최대 60장대라 넉넉하다 — 이건 튜닝값이 아니라
# **입력 모양 제약**이라서 `settings` 로 빼지 않는다(`AdId` 의 길이 64 와 같은 성질).
이미지순번상한 = 999

# 사람이 찍을 수 있는 값. **정본은 `banner.사람판정허용값` 이다** — 여기서 문자열을 다시
# 적으면 순수층과 라우트가 다른 화이트리스트를 갖게 되고, 그 어긋남은 `게이트집계` 가
# 예외로 터질 때에야 드러난다(그때는 이미 사람의 클릭이 버려진 뒤다).
# `미판정` 이 여기 없는 것이 요점이다 — 사람은 "모르겠다"를 찍지 않는다(D-09).
사람판정타입 = Literal[banner.배너, banner.제품, banner.무내용]


class LabelReq(BaseModel):
    """장 하나의 사람 판정.

    `run_dir` 은 여기서 검증하지 않는다 — `paths.run_dir_path()` 화이트리스트가 본다.
    입구가 늘어나도 한 곳에서 막히게 하는 것이 이 저장소의 관례다(`JobReq` 와 같다).
    """

    run_dir: str
    타오바오상품번호: 타오바오번호
    판매자상품코드: 판매코드
    이미지순번: int = Field(ge=0, le=이미지순번상한)
    사람판정: 사람판정타입


class ConfirmReq(BaseModel):
    """"이 줄 다 봤다". 장 단위가 아니라 **상품 단위**다 (D-03a / D-12)."""

    run_dir: str
    타오바오상품번호: 타오바오번호


async def _요청_풀기(request: Request, 모델):
    """JSON 과 htmx 폼(`application/x-www-form-urlencoded`)을 **둘 다** 받는다.

    htmx 는 기본이 urlencoded 라 JSON 만 받으면 버튼이 422 로 튕기고, 폼만 받으면
    `curl`·v2 스케줄러가 불편해진다. 입력 모양을 둘 받되 **검증은 한 곳(Pydantic)**
    에서 한다 — 그게 진짜 관문이다 (`routes/jobs.py:요청_풀기` 와 같은 관용구).

    `request.form()` 을 쓰지 않는다. Starlette 은 urlencoded 폼에도 `python-multipart`
    를 요구한다 — 파일 업로드가 없는 화면에 멀티파트 파서를 깔 이유가 없다.
    """
    본문 = await request.body()
    ctype = request.headers.get("content-type", "")

    if not 본문:
        값: dict = {}
    elif "application/json" in ctype:
        try:
            값 = json.loads(본문)
        except Exception:
            raise HTTPException(status_code=400, detail="요청 본문이 JSON 이 아니다")
        if not isinstance(값, dict):
            raise HTTPException(status_code=400, detail="요청 본문은 객체여야 한다")
    else:
        값 = dict(parse_qsl(본문.decode("utf-8", "replace")))

    try:
        return 모델(**값)
    except ValidationError as e:
        # 422 다 — 400 이 아니다. 값의 모양이 화이트리스트 밖이라는 뜻이고, 화면은
        # "다시 눌러라" 가 아니라 "버튼이 보내는 값이 틀렸다" 로 읽어야 한다.
        # 트레이스백·모델 내부 구조는 싣지 않는다 (ASVS V7). 건수만 알린다.
        raise HTTPException(status_code=422, detail=f"요청 값이 잘못됐다 ({len(e.errors())}건)")


def _회차확인(run_dir: str) -> None:
    """회차 이름이 **실제로 존재하는 회차**인지 본다. 아니면 400.

    쓰기 경로에도 이 관문을 둔다. 경로를 조합하지 않으므로 탈출 위험은 없지만,
    모르는 회차로 들어온 라벨은 **DB 에 남는데 어느 화면에도 안 보인다** — 사람은
    클릭이 먹혔다고 믿고, 게이트는 그 라벨을 영원히 못 센다. 저장은 됐는데 화면이
    거짓말을 하는 그 모양이 이 저장소가 가장 싫어하는 실패다.
    """
    try:
        paths.run_dir_path(run_dir)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"{e}")


def _쓰기예외(e: Exception) -> HTTPException:
    """저장소 예외 → 상태코드. **사유를 지어내지 않고 고칠 자리를 말한다.**

      | 예외                      | 코드 | 뜻                                    |
      |---------------------------|------|---------------------------------------|
      | `ValueError`              | 400  | 요청이 틀렸다 (빈 회차·허용값 밖)       |
      | `sqlite3.OperationalError`| 500  | 라벨 테이블이 없다 → 서버를 다시 띄워라  |
      | 그 밖                      | 500  | 서버 문제                              |

    테이블 부재를 400 으로 번역하면 사용자가 자기 클릭을 탓하며 계속 누른다 —
    실제로 필요한 것은 `init_db()` 를 한 번 더 태우는 **서버 재시작**이다.
    """
    if isinstance(e, ValueError):
        return HTTPException(status_code=400, detail=str(e))
    if isinstance(e, sqlite3.OperationalError):
        return HTTPException(status_code=500,
                             detail="라벨 테이블이 없다 — 서버를 한 번 재시작해라")
    return HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


# ── 장 표시 규약 — **색만으로 가르지 않는다** (흑백 출력·색맹) ────────────────
#
# 테두리 스타일과 글자까지 다르다. CSS 는 `banner_review.html` 에 있고 여기서는
# 클래스 이름만 정한다 — 화면이 판정값 문자열을 직접 클래스로 쓰면 어휘가 바뀌는 날
# 스타일이 조용히 사라진다.
_판정클래스 = {
    banner.배너: "ct-banner",      # 빨강 실선
    banner.무내용: "ct-blank",     # 회색 점선
    banner.미판정: "ct-unjudged",  # 주황 이중선
    banner.제품: "ct-product",     # 테두리 없음
}
# 제품만 빈 문자열이다 — 894장 중 대부분이 제품이라, 거기까지 글자를 붙이면 줄이
# 글자로 덮여 3초 훑기가 안 된다. **눈에 걸려야 하는 것은 제품이 아닌 장**이다.
_판정글자 = {
    banner.배너: "배너",
    banner.무내용: "무내용",
    banner.미판정: "⚠ 미판정",
    banner.제품: "",
}


def _토글순환(기계판정) -> tuple:
    """그 장을 눌렀을 때 도는 값의 순환. **마지막 칸이 기계 판정이다.**

    기계가 `배너` 라 한 장은 `제품` → `무내용` → `배너`(= 기계 판정으로 복귀) 를 돈다.
    복귀 자리가 있는 것이 요점이다 — 되돌리기 버튼을 따로 두면 그게 곧 상태가 하나
    더 생기는 길이고, 새 상태는 사람 판단 큐의 입구다(D-09). 원래 판정을 다시 찍는
    것이 되돌리기다(`post_label` docstring).

    기계가 `미판정` 인 장은 복귀 자리가 없다 — 사람은 "모르겠다"를 찍지 못하므로
    (`banner.사람판정허용값` 에 `미판정` 이 없다) 세 값만 돈다. 그 장은 누군가 반드시
    값을 정해야 하고, 그게 `게이트집계` 가 미판정 장을 분모에서 빼는 이유다.
    """
    반대 = {banner.배너: banner.제품, banner.제품: banner.배너}
    if 기계판정 in 반대:
        return (반대[기계판정], banner.무내용, 기계판정)
    if 기계판정 == banner.무내용:
        return (banner.배너, banner.제품, banner.무내용)
    return tuple(banner.사람판정허용값)


def _다음판정(기계판정, 사람판정) -> str:
    """이 장을 지금 누르면 기록될 값. **계산은 서버에서 한다.**

    템플릿에 순환 규칙을 넣으면 판정의 정본이 둘이 되고, 화면과 DB 가 다른 말을 하는
    날 어느 쪽이 맞는지 아무도 모르게 된다(S-1).
    """
    순환 = _토글순환(기계판정)
    현재 = 사람판정 or 기계판정
    try:
        i = 순환.index(현재)
    except ValueError:
        # 기계 판정이 허용값 밖이거나 `미판정` 이다 — 순환의 첫 칸에서 출발한다.
        return 순환[0]
    return 순환[(i + 1) % len(순환)]


def _장투영(상품키, 판매자상품코드, run_dir: str, 장: dict, 사람판정) -> dict:
    """장 하나 → 템플릿이 쓸 값만. `_화면투영` 과 라벨 POST 응답이 **같은 함수**를 쓴다.

    두 곳이 각자 조립하면 클릭 전후로 테두리 규약이 어긋난다 — 그러면 사람이 "눌렀는데
    색이 이상해졌다" 로 읽고, 그건 저장 실패와 구분되지 않는다.

    `라벨요청` 은 htmx 가 그대로 보낼 `hx-vals` dict 다. 상품키나 판매자상품코드가
    없으면 `None` 이고, 화면은 대신 `라벨불가` 사유를 말한다 — 버튼을 조용히 빼면
    그 줄은 영원히 검수가 안 되는데 화면에는 멀쩡해 보인다.
    """
    기계 = 장.get("판정")
    표시 = 사람판정 or 기계
    코드 = 판매자상품코드 if isinstance(판매자상품코드, str) and 판매자상품코드.strip() else None

    못하는이유 = None
    if not 상품키:
        못하는이유 = "타오바오상품번호도 불사자코드도 없어 라벨을 묶을 키가 없다"
    elif not 코드:
        못하는이유 = "판매자상품코드가 없어 라벨을 기록할 수 없다"

    요청 = None
    if 못하는이유 is None:
        요청 = {
            "run_dir": run_dir,
            "타오바오상품번호": 상품키,
            "판매자상품코드": 코드,
            "이미지순번": 장.get("순번"),
            "사람판정": _다음판정(기계, 사람판정),
        }

    return {
        "순번": 장.get("순번"),
        "판정": 기계,
        "사유": 장.get("사유"),
        # 사람이 뒤집었으면 그 값, 아니면 None. **기계 판정으로 채우지 않는다** —
        # 화면이 "사람이 찍었다" 와 "기계가 그랬다" 를 구분해 보여야 한다.
        "사람판정": 사람판정,
        "사람이찍음": bool(사람판정),
        "표시판정": 표시,
        # 모르는 판정값은 조용히 제품으로 접지 않는다 — 눈에 걸리게 미판정 모양으로 그린다.
        "판정클래스": _판정클래스.get(표시, "ct-unjudged"),
        "판정글자": _판정글자.get(표시, "⚠ 모르는 판정"),
        "다음판정": _다음판정(기계, 사람판정),
        # 파일명을 싣지 않는다. 화면은 순번으로만 썸네일을 부른다 (T-4-04).
        "썸네일있음": bool(장.get("썸네일")),
        "라벨요청": 요청,
        "라벨불가": 못하는이유,
    }


def _장조각(run_dir: str, 타오바오상품번호: str, 판매자상품코드: str,
          이미지순번: int, 사람판정값: str) -> str:
    """방금 찍은 장 하나의 조각 HTML — `_banner_strip.html` 을 그대로 렌더한다.

    **응답이 그 장 하나여야 한다** — 줄 전체나 페이지를 돌려주면 htmx 가 스트립을
    통째로 다시 그리고, 사람이 훑던 가로 스크롤 위치가 매 클릭마다 처음으로 돌아간다.
    891장 전장을 훑는 화면에서 그건 검수를 불가능하게 만든다(D-03a).

    **기계 판정·사유·썸네일 유무를 요청에서 받지 않는다.** 산출물을 다시 읽어 서버가
    꺼낸다 — 클라이언트가 보낸 값으로 테두리를 그리면 화면이 DB 가 아니라 자기 자신을
    비추게 되고, 그 순간 "미탐 0%" 의 근거가 사라진다.

    산출물을 못 읽어도 **저장은 이미 끝났다.** 그 사실을 조각이 말한다 — 조용히 옛
    모양을 돌려주면 사람이 같은 장을 또 누른다.
    """
    from webapp.main import templates      # 지연 import — main 이 이 모듈을 먼저 부른다

    문서, _작업id, _사유 = _load_banner(run_dir)
    상품 = None
    if 문서 is not None:
        라벨 = {타오바오상품번호: {이미지순번: 사람판정값}}
        for 줄 in _화면투영(문서, 라벨, set(), run_dir):
            if 줄["상품키"] == 타오바오상품번호:
                상품 = 줄
                break

    장 = None
    if 상품 is not None:
        장 = next((c for c in 상품["장"] if c["순번"] == 이미지순번), None)

    if 장 is None:
        상품 = {"순번": None, "상품키": 타오바오상품번호,
              "판매자상품코드": 판매자상품코드}
        장 = _장투영(타오바오상품번호, 판매자상품코드, run_dir,
                  {"순번": 이미지순번, "판정": None, "사유": None, "썸네일": None},
                  사람판정값)
        장["라벨요청"] = None
        장["라벨불가"] = "저장은 됐다 — 산출물에서 이 장을 다시 못 찾았다. 새로고침해라"

    return templates.get_template("_banner_strip.html").render(
        {"run_dir": run_dir, "상품": 상품, "장": 장, "자리": "strip", "큰것": False})


# ── 쓰기 (POST) ─────────────────────────────────────────────────────────────
#
# `security.guard` 미들웨어가 Origin · `sec-fetch-site` · 부팅 토큰 3층을 이미 검사한다.
# **라우트에 추가 코드가 필요 없고, 예외를 만들지도 않는다** (RESEARCH §ASVS V4).


@router.post("/banner/label")
async def post_label(request: Request):
    """장 하나를 뒤집는다. 같은 장을 다시 찍으면 최신 1건이 이긴다.

    **되돌리기 버튼을 따로 두지 않는다** — 원래 판정을 다시 찍으면 그게 되돌리기다.
    상태를 하나 더 만들면 그게 곧 사람 판단 큐의 입구다(D-09).
    """
    요청 = await _요청_풀기(request, LabelReq)
    _회차확인(요청.run_dir)
    try:
        banner_store.라벨기록(요청.run_dir, 요청.타오바오상품번호, 요청.판매자상품코드,
                          요청.이미지순번, 요청.사람판정)
    except Exception as e:
        raise _쓰기예외(e)
    return HTMLResponse(_장조각(요청.run_dir, 요청.타오바오상품번호, 요청.판매자상품코드,
                             요청.이미지순번, 요청.사람판정))


@router.post("/banner/confirm")
async def post_confirm(request: Request):
    """"이 줄 다 봤다". 게이트는 이 표시가 **전 상품에 다 있어야** 열린다 (D-12).

    안 본 상품을 "기계 판정에 동의" 로 세면 미탐 0% 가 거짓말이 된다(Pitfall 8).
    그래서 이건 라벨과 **다른 테이블**이다 — "뒤집었다" 와 "다 봤다" 는 다른 사실이다.
    """
    요청 = await _요청_풀기(request, ConfirmReq)
    _회차확인(요청.run_dir)
    try:
        banner_store.확인기록(요청.run_dir, 요청.타오바오상품번호)
    except Exception as e:
        raise _쓰기예외(e)
    return HTMLResponse(
        f'<span class="ct-confirmed" data-p="{요청.타오바오상품번호}">확인함</span>')


# ── 읽기 (GET) — 여기부터 아래는 서버 상태를 바꾸지 않는다 ────────────────────


def _load_banner(run_dir_name: str) -> tuple:
    """마지막 성공 배너 스캔의 산출물 — `(문서, 작업id, 사유)`.

    `routes/board.py:_load_join` 과 **같은 모양**이다: 실패하면 값을 지어내지 않고
    사유를 들고 온다.

    어느 잡이 성공했는지는 **레지스트리가 정본**이다. `web/banner_*.json` 을 glob 으로
    뒤지지 마라 — 파일이 있다는 것과 그 잡이 성공했다는 것은 다르다(중간에 죽은 잡도
    반쯤 쓴 파일을 남긴다). `jobs.latest_done` 이 그 질문에 답하려고 있는 함수다.

    **스캔을 한 번도 안 돌린 것은 실패가 아니다** — 사유 없이 `(None, None, None)` 이고
    화면이 "아직 배너 스캔을 안 돌렸다" 를 말한다. 사유를 채우면 고장으로 읽힌다(S-3).

    `상품` 이 0건이면 `None` + 사유다. 0건은 관측이 아니라 조회 실패일 수 있다 —
    `_load_join` 이 `마켓그룹: []` 에 대해 내린 것과 같은 판단(CR-01)이고,
    빈 화면을 "판정할 게 없다" 로 읽게 두는 것이 이 저장소가 가장 비싸게 배운 실패다.

    예외는 `f"{type(e).__name__}: {e}"` 로 축약한다 — 트레이스백을 화면에 실으면
    경로·내부 구조가 그대로 나간다(ASVS V7).
    """
    try:
        잡 = jobs.latest_done("banner_scan", run_dir_name)
    except Exception as e:
        return None, None, f"{type(e).__name__}: {e}"
    if not 잡:
        return None, None, None

    경로 = 잡.get("result_path")
    작업id = 잡.get("id")
    if not 경로:
        return None, None, "배너 스캔 작업에 산출물 경로가 없다 — 배너 스캔을 다시 돌려라"
    try:
        문서 = json.loads(Path(경로).read_text(encoding="utf-8"))
    except Exception as e:
        return None, None, f"{type(e).__name__}: {e}"
    if not isinstance(문서, dict):
        return None, None, "배너 산출물의 모양이 다르다 — 배너 스캔을 다시 돌려라"
    if not isinstance(문서.get("상품"), list) or not 문서["상품"]:
        return None, None, ("산출물에 상품이 0건이다 — 배너 스캔을 다시 돌려라 "
                            "(0건은 관측이 아니라 조회 실패일 수 있다)")
    return 문서, 작업id, None


def _썸네일이름(문서: dict, 상품순번: int, 장순번: int) -> str | None:
    """산출물에서 **서버가** 파일명을 꺼낸다. 사용자 입력은 정수 둘뿐이다 (T-4-04).

    범위 밖이거나 그 장에 썸네일이 없으면(미판정·다운로드 실패) `None` 이다.
    음수를 명시적으로 막는다 — 파이썬 리스트는 `[-1]` 을 조용히 받아 **마지막 장**을
    내주고, 그러면 범위 검사가 있는 척만 하는 가드가 된다.
    """
    if 상품순번 < 0 or 장순번 < 0:
        return None
    상품들 = 문서.get("상품") or []
    if 상품순번 >= len(상품들):
        return None
    장들 = (상품들[상품순번] or {}).get("장") or []
    if 장순번 >= len(장들):
        return None
    이름 = (장들[장순번] or {}).get("썸네일")
    return 이름 if isinstance(이름, str) and 이름 else None


def _화면투영(문서: dict, 라벨: dict, 확인: set, run_dir: str) -> list:
    """산출물 → 템플릿이 쓸 **값만** (S-2 화이트리스트 투영).

    산출물 dict 를 통째로 넘기지 않는다. 이유 둘: ① `url` 같은 CDN 주소가 템플릿에
    실리면 브라우저가 외부 CDN 에 직접 붙어 Referer 가 샌다(T-4-22) — 서버 썸네일을
    쓰므로 실을 이유가 없다 ② 산출물에 새 필드가 생겼을 때 자동으로 화면 밖으로
    새는 설계를 만들지 않는다.

    `상품키` 는 `banner.상품키()` 가 낸다 — 라벨 키와 **같은 함수**에서 와야 한다.
    키가 어긋나면 사람이 찍은 라벨이 화면에 안 보이는데 게이트집계는 그걸 세고 있다.
    키를 못 만드는 상품(번호가 둘 다 없다)은 사유를 들고 남는다 — 빼면 전장을 깐다는
    D-03a 가 조용히 깨진다.
    """
    나온것 = []
    for 순번, 상품 in enumerate(문서.get("상품") or []):
        if not isinstance(상품, dict):
            continue
        try:
            키 = banner.상품키(상품)
        except ValueError as e:
            키, 키사유 = None, f"{e}"
        else:
            키사유 = None
        내라벨 = (라벨.get(키) or {}) if 키 else {}
        코드 = 상품.get("판매자상품코드")

        장들 = []
        for 장 in 상품.get("장") or []:
            if not isinstance(장, dict):
                continue
            try:
                장순번 = int(장.get("순번"))
            except (TypeError, ValueError):
                continue
            장 = dict(장, 순번=장순번)
            장들.append(_장투영(키, 코드, run_dir, 장, 내라벨.get(장순번)))

        # 줄 머리에 띄울 `제품 N / 배너 M`. **사람이 뒤집은 값(`표시판정`)으로 센다** —
        # 기계 판정으로 세면 클릭해도 숫자가 안 움직여서 "안 눌렸나" 로 읽힌다.
        줄집계 = {v: 0 for v in (banner.배너, banner.제품, banner.무내용, banner.미판정)}
        for 장 in 장들:
            if 장["표시판정"] in 줄집계:
                줄집계[장["표시판정"]] += 1

        나온것.append({
            "순번": 순번,
            "상품키": 키,
            "키사유": 키사유,
            "판매자상품코드": 코드,
            "상세상태": 상품.get("상세상태"),
            "장수": 상품.get("장수"),
            "제거율": 상품.get("제거율"),
            "스킵사유": 상품.get("스킵사유"),
            "사유": 상품.get("사유"),
            "확인됨": bool(키 and 키 in 확인),
            "라벨수": len(내라벨),
            # "이 줄 다 봤다" 요청. 키가 없으면 누를 수 없다 — 그 사유는 `키사유` 다.
            "확인요청": ({"run_dir": run_dir, "타오바오상품번호": 키} if 키 else None),
            "줄집계": 줄집계,
            "장": 장들,
        })
    return 나온것


# RESEARCH Appendix A §경계 4장 의 "물어볼 것" 한 줄씩. **순서가 계약이다** —
# `settings.DEFAULTS["banner_boundary_samples"]` 와 같은 자리끼리 짝이다.
#
# 왜 설정이 아니라 여기 있나: 설정에는 `"코드:순번"` 만 있고 질문 문장이 없다. 질문을
# 설정으로 옮기면 실제 판매자상품코드가 한 벌 더 생기고(익명화 불가 값이 둘), 여기에
# 코드를 다시 적으면 정본이 둘이 된다. 그래서 **코드를 한 글자도 다시 적지 않고**
# `DEFAULTS` 의 자리(index)로 join 한다 — `workspace.toml` 이 표본을 갈아 끼우면
# 그 표본은 질문 없이(`None`) 뜨고, 자리가 밀려 엉뚱한 질문이 붙는 일은 없다.
_경계질문 = (
    "수상·브랜드 배너지만 제품이 크게 나온다. 뺄까?",
    "첫 장 타이틀 이미지는 제품인가 배너인가?",
    "장식 포스터. 제품(밥그릇)이 나온다",
    "사용 장면 배너. 제품은 안 나온다",
)


def _기준표본(상품목록: list) -> tuple[list, list, int]:
    """경계 4장을 이 회차 산출물에서 찾는다 — `(찾음, 못찾음, 전체)`.

    **표본을 못 찾아도 섹션을 조용히 감추지 않는다.** 물갈이가 한 번 돌면 판매자상품
    코드가 재발급돼 이 값은 반드시 낡는다(`settings.py` 의 ⚠️ 주석). 그때 섹션이
    사라지면 다음 사람은 **기준 확인이 끝난 줄 안다** — 없는 것과 끝난 것은 다른
    사실이다. 그래서 못 찾은 것은 "무엇을 못 찾았는지"까지 들고 화면으로 간다.

    숫자·코드를 이 함수에 박지 않는다. 정본은 `settings.DEFAULTS` 다(S-4).
    """
    토큰들 = settings.cfg("banner_boundary_samples",
                       settings.DEFAULTS["banner_boundary_samples"]) or []
    기본 = list(settings.DEFAULTS["banner_boundary_samples"])

    찾음: list = []
    못찾음: list = []
    for 토큰 in 토큰들:
        토큰 = str(토큰)
        try:
            질문 = _경계질문[기본.index(토큰)]
        except (ValueError, IndexError):
            # 설정이 표본을 갈아 끼웠다. 질문을 지어내지 않는다 — 없는 것은 없다고 둔다.
            질문 = None

        코드, 구분, 순번글자 = 토큰.partition(":")
        if not 구분:
            못찾음.append({"토큰": 토큰, "물어볼것": 질문,
                        "사유": "모양이 '판매자상품코드:순번' 이 아니다"})
            continue
        try:
            순번 = int(순번글자)
        except ValueError:
            못찾음.append({"토큰": 토큰, "물어볼것": 질문,
                        "사유": f"순번이 정수가 아니다: {순번글자!r}"})
            continue

        상품 = next((p for p in 상품목록 if p["판매자상품코드"] == 코드), None)
        if 상품 is None:
            못찾음.append({"토큰": 토큰, "물어볼것": 질문,
                        "사유": "이 회차에 그 판매자상품코드가 없다 (물갈이로 재발급됐을 수 있다)"})
            continue
        장 = next((c for c in 상품["장"] if c["순번"] == 순번), None)
        if 장 is None:
            못찾음.append({"토큰": 토큰, "물어볼것": 질문,
                        "사유": f"그 상품에 {순번}번 장이 없다 (장수 {len(상품['장'])})"})
            continue

        찾음.append({"토큰": 토큰, "물어볼것": 질문, "상품": 상품, "장": 장})

    return 찾음, 못찾음, len(토큰들)


@router.get("/banner/review")
def get_review(request: Request, run_dir: str | None = None):
    """검수 화면. **읽기만 한다** — 디스크·DB·잡 레지스트리에 아무것도 쓰지 않는다.

    회차 이름은 `paths.run_dir_path()` 화이트리스트를 탄다. `..` 를 거르는 블랙리스트가
    아니라 실제로 존재하는 회차 목록에 든 이름만 통과한다(T-1-11 / ASVS V12).
    """
    if not security.page_cookie_ok(request):
        return PlainTextResponse(
            "토큰이 필요하다 — 서버 기동 로그의 URL 로 들어와라", status_code=403)

    회차들 = paths.scan_runs()
    선택 = run_dir or (회차들[0]["name"] if 회차들 else None)
    if run_dir is not None:
        try:
            paths.run_dir_path(run_dir)
        except ValueError as e:
            return PlainTextResponse(f"{e}", status_code=400)

    from webapp.main import templates      # 지연 import — main 이 이 모듈을 먼저 부른다

    ctx = {
        # 템플릿의 `hx-headers` 가 모든 쓰기 요청에 붙인다. 쿠키가 아니라 헤더인 이유:
        # 커스텀 헤더는 교차 오리진에서 붙일 수 없다(CORS 미개방).
        "token": security.BOOT_TOKEN,
        "runs": 회차들,
        "run_dir": 선택,
        "job_id": None,
        "load_error": None,
        "집계": None,
        "게이트": None,
        "판정규칙": None,
        "소요초": None,
        "라벨수": 0,
        "상품": [],
        # 기준 확인 섹션(경계 4장). 산출물을 읽은 뒤에 채운다.
        "기준표본": [],
        "기준못찾음": [],
        "기준전체": 0,
        # 진행 패널. **활성 잡 하나만** 스트림을 연다 — 잡마다 열면 HTTP/1.1 의
        # 호스트당 6커넥션을 다 먹고 페이지의 나머지 요청이 굶는다(T-1-24).
        "job": jobs.active_job(),
        # 줄집계를 꺼낼 키. 판정값 문자열을 템플릿에 박지 않는다 — 어휘가 바뀌는 날
        # 화면이 조용히 0 을 띄우게 된다(`banner.py` 의 상수가 정본이다).
        "배너값": banner.배너,
        "제품값": banner.제품,
        "미판정값": banner.미판정,
    }
    if 선택 is None:
        # 회차가 하나도 없다. 빈 표를 띄우지 않는다 — 빈 표는 "대상이 없다" 로 읽히는데
        # 실제로는 "아직 아무것도 안 돌렸다" 다.
        return templates.TemplateResponse(request, "banner_review.html", ctx)

    문서, 작업id, 사유 = _load_banner(선택)
    ctx["load_error"] = 사유
    ctx["job_id"] = 작업id
    if 문서 is None:
        return templates.TemplateResponse(request, "banner_review.html", ctx)

    try:
        라벨 = banner_store.라벨읽기(선택)
        확인 = banner_store.확인읽기(선택)
    except Exception as e:
        # 라벨을 못 읽는 것과 산출물을 못 읽는 것은 **다른 실패**다. 한 칸에 담으면
        # 사용자가 배너 스캔을 다시 돌리는데 진짜 원인은 스키마다.
        ctx["load_error"] = (f"라벨을 읽지 못했다: {type(e).__name__} — "
                             "서버를 한 번 재시작해라")
        라벨, 확인 = {}, set()

    ctx["상품"] = _화면투영(문서, 라벨, 확인, 선택)
    ctx["기준표본"], ctx["기준못찾음"], ctx["기준전체"] = _기준표본(ctx["상품"])
    ctx["집계"] = 문서.get("집계")
    ctx["판정규칙"] = 문서.get("판정규칙")
    # **소요시간은 산출물의 `소요초` 다** (S-5). 잡 레코드의 시각 차이로 계산하지 마라 —
    # 실측 60초짜리 작업이 2,421초로 기록된 적이 있다(자식이 세션 분리로 살아 있으면
    # 레지스트리의 종료 시각이 실제 작업 시간을 말하지 않는다).
    ctx["소요초"] = 문서.get("소요초")

    try:
        ctx["게이트"] = banner.게이트집계(문서, 라벨, 확인)
    except ValueError as e:
        # 게이트 숫자가 없다고 화면을 통째로 500 으로 만들지 않는다. **대신 게이트는
        # 닫혀 있다** — 숫자가 없으면 통과 근거도 없다(fail-closed).
        ctx["게이트"] = None
        ctx["load_error"] = ctx["load_error"] or f"게이트 집계를 못 했다: {e}"

    ctx["라벨수"] = sum(len(v) for v in 라벨.values())
    return templates.TemplateResponse(request, "banner_review.html", ctx)


@router.get("/banner/thumb/{run_dir}/{product_i}/{chap_i}")
def get_thumb(request: Request, run_dir: str, product_i: int, chap_i: int):
    """썸네일 1장. **파일명을 받지 않는다 — 정수 인덱스만 받는다** (T-4-04).

    ⚠️ **경로 파라미터 이름만 영문이다.** 저장소 관례는 내부 이름을 한글로 쓰는 것이지만,
    이 FastAPI/Starlette 조합은 한글 경로 파라미터를 **조용히 라우팅하지 못한다**
    (실측: `/t/{상품순번}` 은 404, 같은 모양의 `/t/{pi}` 는 200). 404 라서 "아직 안
    만들었나" 로 읽히지 예외가 나지 않는다 — 그래서 여기만 영문이고, 이 주석이 이유다.

    경로 탈출이 막히는 게 아니라 **구조적으로 불가능하다**: 사용자가 보내는 것은
    회차 이름(화이트리스트)과 정수 둘뿐이고, 파일명은 서버가 산출물 JSON 의
    `장[].썸네일` 에서 꺼낸다. 그래도 방어를 2층으로 둔다 — 만든 경로의 **부모
    디렉터리**가 썸네일 루트와 같은지 본다. 접두 비교(`startswith`)로 하면
    `thumbs-남의것/` 같은 형제 디렉터리가 통과한다. 경계를 글자가 아니라 경로로 본다.

    **쿠키 게이트를 여기에도 건다.** 안 걸면 271MB 캐시에서 파생된 이미지가 토큰 없이
    열린다. 그리고 이 라우트를 정적 파일 마운트로 대신하지 마라 — `main.py` 의
    `/static` 처럼 캐시 디렉터리를 통째로 마운트하면 원본 디렉터리 **전체**가 토큰 없이
    열린다(Pitfall 7 / ASVS V12). 그 금지를 `test_routes_banner.py` 가 이 파일에 대해
    글자로 집행하므로, 그 클래스 이름을 주석에도 남기지 않는다.
    """
    if not security.page_cookie_ok(request):
        return PlainTextResponse("토큰이 필요하다", status_code=403)

    try:
        paths.run_dir_path(run_dir)
    except ValueError as e:
        return PlainTextResponse(f"{e}", status_code=400)

    문서, _작업id, _사유 = _load_banner(run_dir)
    if 문서 is None:
        return PlainTextResponse("배너 산출물이 없다", status_code=404)

    이름 = _썸네일이름(문서, product_i, chap_i)
    if not 이름:
        # 범위 밖이거나 그 장에 썸네일이 없다(미판정·다운로드 실패). 둘 다 404 다 —
        # 사유를 몸통에 싣지 않는다. 존재 여부를 세밀하게 알려 주는 것도 정보 노출이다.
        return PlainTextResponse("썸네일이 없다", status_code=404)

    루트 = (jobs.banner_dir("banner_thumb_dir") / run_dir).resolve()
    p = (루트 / 이름).resolve()
    if p.parent != 루트:
        # 산출물이 파일명 대신 경로를 들고 있다 — 04-03 규약 위반이거나 손댄 파일이다.
        return PlainTextResponse("썸네일 경로가 회차 밖이다", status_code=404)
    if not p.is_file():
        return PlainTextResponse("썸네일이 없다", status_code=404)
    return FileResponse(p, media_type="image/webp")
