#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""쿠팡 트랙 라우터 (Phase 7 / CP-01~04) — **트랙 소유 파일이다.**

    POST /jobs/coupang/preview    쿠팡 후보 뽑기 잡 접수 (쓰기 0)             [쓰기 — 토큰 필요]
    POST /jobs/coupang/commit     쿠팡 복사 잡 접수 (잡 id + 타이핑 건수)      [쓰기 — 토큰 필요]
    결과 조각은 GET /jobs/{id}/result 가 아래 `결과표` 로 그린다(coupang_preview · coupang_commit).

공유 파일(jobs.py · routes/jobs.py · main.py · board.html · board.js · _job_status.html)은
07-01 에서만 고친다(D-19). 여기서는 routes/jobs.py 의 도우미를 **import 해서 쓰기만** 한다.

흐름:
  ① 후보 뽑기 — 요청 본문이 비어 있다. `create_job("coupang_preview")` 한 번이면 러너
     (`coupang_web.py preview`)가 prep→resolve→build→ship→gate→apply(무커밋) 6단계를 돌아
     summary.json 을 쓴다. **기준·마진은 전부 그 파일 값이다 — 여기서 다시 계산하지 않는다(L-02 · CP-03).**
  ② 복사 — 본문은 미리보기 잡 id + 사람이 타이핑한 건수뿐이다(D-11). 승인목록(`_승인목록`)과
     상한(`_쿠팡복사상한`)은 **서버가** 미리보기 요약에서 정한다. 건수가 다르면 409.
  ③ 결과 — 러너 commit_summary 를 읽어 재조회 차분·복사 행·중복0·잠금 승계 안내를 보인다.

요청 모델에 게이트 기준·skip·strict 필드를 두지 마라(L-04 · D-15) — 기준은 CLI 기본값이 정본이다.
"""
import json
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from webapp import jobs, settings
from webapp.routes.jobs import JobId, _경과초, _미리보기유효시간, _상세잡만들기, _투영

router = APIRouter()

# 쿠팡 복사 대상 그룹 — 러너(run_coupang.py) 설정이 정본이다. 화면 경고문에 이름만 보인다.
쿠팡그룹표시 = "1번_용쌤쿠팡cy1728"

# 잠금 승계 안내 — 결과 표에 항상 1줄. 복사본이 원본 잠금을 물려받아 삭제가 막히는 사고(메모리
# delete-blocked-by-product-lock)를 미리 알린다.
잠금안내 = "쿠팡 복사본은 원본 잠금을 물려받는다 — 잘못 복사했으면 지우기 전에 잠금부터 푼다"


class CoupangPreviewReq(BaseModel):
    """쿠팡 후보 뽑기 요청 — **필드가 하나도 없다** (T-07-26 · L-04).

    게이트 기준(마진·주문수)·그룹확인 건너뛰기·배송비 엄격 모드를 받지 않는다. 필드가 없는 것이
    방어다 — `{"min_margin": 15}` 처럼 실어 보내면 422 다.
    """

    model_config = ConfigDict(extra="forbid")


class CoupangCommitReq(BaseModel):
    """쿠팡 복사 요청 — 미리보기 잡 id + **사람이 타이핑한 건수** (D-11 · T-07-27).

    대상·상한을 받지 않는다. `typed_count` 는 대상이 아니라 확인값이다 — 서버가 지금 센
    승인목록 길이와 다르면 409(`post_revert_round` 와 같은 판단: 화면이 본 규모 ≠ 실제 규모).
    StrictInt 라 문자열 "10"·true 는 422 다(습관적 자동 채움을 막는다).
    """

    model_config = ConfigDict(extra="forbid")
    preview_job_id: JobId
    typed_count: StrictInt = Field(ge=0)


# ── 상한 · 승인목록 — 결정은 각각 이 한 곳 ─────────────────────────────────

def _쿠팡복사상한() -> int:
    """이번 복사 1회의 상한 — **서버가 정한다. 요청에는 이 값이 없다** (D-13 · T-07-29).

    D-13 — 첫 실행 10 은 여기 한 곳. 이 웹 경로로 성공(done/0)한 쿠팡 복사가 한 번도 없으면
    `coupang_first_max_items`(10), 있으면 `coupang_copy_max_items`(20). 첫 실행 판정은
    잡 레지스트리가 정본이다(L-07 — 대장 파일을 새로 두지 않는다). 러너에 `--limit` 로 항상 붙는다.
    설정이 깨졌으면 기본값으로, 그래도 최소 1 — 0 을 '전량' 으로 읽는 길은 없다.
    """
    키 = "coupang_copy_max_items" if jobs.first_coupang_commit_done() else "coupang_first_max_items"
    try:
        n = int(settings.cfg(키, settings.DEFAULTS[키]))
    except (TypeError, ValueError):
        n = int(settings.DEFAULTS[키])
    return max(1, n)


def _승인목록(요약: dict, 상한: int) -> list[str]:
    """미리보기 통과 행 → 이번에 복사할 대표pid 목록 (D-16).

    D-16 [용팀장 확인 대기] — 상세완료 필터를 더하기로 뒤집으면 이 함수만 바꾼다(조인 필요).
    지금은 gate 가 세운 순서(candidates.json 정렬) 그대로 상위 `상한` 건이다. 같은 pid 는 한 번만.
    """
    본것: list[str] = []
    for r in 요약.get("통과") or []:
        if not isinstance(r, dict):
            continue
        pid = str(r.get("대표pid") or "").strip()
        if pid and pid not in 본것:
            본것.append(pid)
        if len(본것) >= 상한:
            break
    return 본것


# ── 공통 도우미 ─────────────────────────────────────────────────────────────

def _읽기(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _미리보기요약(상태: dict) -> dict | None:
    """미리보기 잡의 summary.json. 경로는 행의 result_path — create_job 이 coupang_dir_of 밑에 둔다."""
    경로 = (상태 or {}).get("result_path")
    문서 = _읽기(Path(경로)) if 경로 else None
    return 문서 if isinstance(문서, dict) else None


def _성공복사(자식들: list[dict]) -> bool:
    return any(c.get("status") == "done" and c.get("exit_code") == 0 for c in 자식들)


def _정수(v):
    return v if isinstance(v, int) and not isinstance(v, bool) else None


# ── ① 후보 뽑기 ─────────────────────────────────────────────────────────────

@router.post("/jobs/coupang/preview")
def post_coupang_preview(request: Request, req: CoupangPreviewReq):
    """**쿠팡 후보 뽑기 — 쓰기 0** (CP-01 · D-09). 6단계 미리보기 잡 하나를 띄운다.

    같은 미리보기가 도는 중이면 409(SINGLETON · 레이트리밋), 계정 불일치 409 — 둘 다
    `_상세잡만들기` 의 예외 번역(409 가 400 보다 먼저)을 그대로 쓴다.
    """
    return _상세잡만들기("coupang_preview")


# ── ② 복사 ──────────────────────────────────────────────────────────────────

@router.post("/jobs/coupang/commit")
def post_coupang_commit(request: Request, req: CoupangCommitReq):
    """**쿠팡 복사 — 되돌릴 수 없다.** 버튼 + 건수 타이핑이 승인이다 (CP-02 · D-11 · D-13).

      ① 부모가 쿠팡 후보 뽑기인가(400) · 도는 중이 아닌가(409) · done/0 인가(400)
      ② 미리보기가 24시간 안인가(400 — T-07-30. 러너가 gate 를 다시 조회하지만 사람이 본 것 자체가 낡았다)
      ③ 이 미리보기로 성공한 복사가 이미 있나(400 — T-07-28). 복사가 도는 중이면 409
      ④ 요약 읽기(깨짐 400) → 상한 `_쿠팡복사상한()` → 승인목록 `_승인목록()` (빈 목록 400)
      ⑤ typed_count ≠ 승인목록 길이 → **409** (화면이 본 수와 서버가 지금 센 수가 다르다)
      ⑥ create_job — 쓰기 잡 전역 가드·계정 가드는 그 안에서(409)
    """
    부모 = jobs.job_status(req.preview_job_id)
    if 부모 is None or 부모.get("kind") != "coupang_preview":
        raise HTTPException(status_code=400, detail="쿠팡 후보 뽑기 작업이 아니다 — 후보 뽑기부터 해라")
    if 부모.get("status") in jobs.LIVE_STATUSES:
        raise HTTPException(status_code=409, detail="후보 뽑기가 아직 도는 중이다 — 끝나고 다시 눌러라")
    if 부모.get("status") != "done" or 부모.get("exit_code") != 0:
        raise HTTPException(
            status_code=400,
            detail=f"후보 뽑기가 정상으로 안 끝났다({부모.get('status')}, 종료코드 "
                   f"{부모.get('exit_code')}) — 새 미리보기부터")
    경과 = _경과초(부모.get("started_at"))
    if 경과 is None or 경과 > _미리보기유효시간:
        raise HTTPException(status_code=400, detail="미리보기가 24시간을 넘었다 — 새 미리보기부터 해라")

    자식들 = jobs.children_of(req.preview_job_id, "coupang_commit")
    if any(c.get("status") in jobs.LIVE_STATUSES for c in 자식들):
        raise HTTPException(status_code=409, detail="이 미리보기의 복사가 도는 중이다 — 끝나고 결과를 봐라")
    if _성공복사(자식들):
        raise HTTPException(status_code=400, detail="이 미리보기로 이미 복사했다 — 새 미리보기부터")

    요약 = _미리보기요약(부모)
    if 요약 is None or not isinstance(요약.get("통과"), list):
        raise HTTPException(status_code=400,
                            detail="미리보기 산출물(summary.json)이 없거나 깨졌다 — 새 미리보기부터")
    상한 = _쿠팡복사상한()
    승인 = _승인목록(요약, 상한)
    if not 승인:
        raise HTTPException(status_code=400, detail="복사할 후보가 0건이다 — 게이트 통과 후보가 없다")
    if req.typed_count != len(승인):
        raise HTTPException(
            status_code=409,
            detail=(f"화면이 본 건수({req.typed_count:,})와 지금 복사할 건수"
                    f"({len(승인):,})가 다르다 — 다시 확인해라"))

    결과 = _상세잡만들기("coupang_commit", parent_job_id=req.preview_job_id,
                        coupang_approved=승인, copy_limit=상한)
    return {"job_id": 결과["job_id"], "건수": len(승인), "상한": 상한}


# ── 결과 조각 ctx (GET /jobs/{id}/result 가 결과표로 부른다) ────────────────

# 정지단계 → 사람 말. gws(주문시트)는 prep 이 읽는다 — 401/403 이면 재로그인이 원인이다.
_단계설명 = {"prep": "주문시트 집계(gws)", "resolve": "불사자코드 풀이", "build": "대표 선정",
            "ship": "배송비 대조", "gate": "게이트 판정", "apply": "복사 미리보기",
            "재조회": "재조회", "verify": "중복 검증"}


def _통과행(r: dict, 순번: int, 상한: int) -> dict:
    return {"판매자상품코드": r.get("판매자상품코드") or r.get("대표pid") or "",
            "상품명": r.get("상품명") or "",
            "합산주문수": r.get("합산주문수"),
            "쿠팡보정마진": r.get("쿠팡보정마진"),
            "배송비차액": r.get("배송비차액"),
            "배송비과소": bool(r.get("배송비과소")),
            "사유": r.get("사유") or "",
            "상한초과": 순번 >= 상한}


def _쿠팡미리보기ctx(상태: dict) -> dict:
    """후보 표 조각 값. **정본은 러너 summary.json** — 기준·마진을 다시 계산하지 않는다(L-02 · CP-03).

    뼈대는 `_상세견적ctx`: 도는 중이면 읽지 않고, 산출물이 없거나 깨졌으면 종료코드와 함께
    오류로 — 빈 표를 '후보 0건' 으로 읽지 않게. 정지단계가 있으면 그 이름을 보인다(D-09).
    """
    상태 = 상태 or {}
    기본 = {"job": _투영(상태), "running": False, "error": None, "정지단계": None,
            "정지설명": "", "gws": False, "기준": "", "통과": [], "탈락사유별": {}, "이미있음": 0,
            "그룹읽기": None, "단계": [], "상한": None, "복사예정": 0, "이미복사": False,
            "복사중": False, "만료": False, "쿠팡그룹": 쿠팡그룹표시}
    if 상태.get("status") in jobs.LIVE_STATUSES:
        return {**기본, "running": True}
    요약 = _미리보기요약(상태)
    if 요약 is None:
        return {**기본, "error": f"후보 산출물(summary.json)이 없거나 깨졌다 — 진행 로그를 봐라 "
                                 f"(종료코드 {상태.get('exit_code')})"}
    정지 = 요약.get("정지단계")
    기본.update({"기준": str(요약.get("기준") or ""),
                "탈락사유별": 요약.get("탈락사유별") if isinstance(요약.get("탈락사유별"), dict) else {},
                "이미있음": _정수(요약.get("이미있음")) or 0,
                "그룹읽기": 요약.get("그룹읽기") if isinstance(요약.get("그룹읽기"), dict) else None,
                "단계": [s for s in (요약.get("단계") or []) if isinstance(s, dict)]})
    if 정지 or 상태.get("status") != "done" or 상태.get("exit_code") != 0:
        return {**기본, "정지단계": 정지 or "?", "정지설명": _단계설명.get(str(정지), ""),
                "gws": 정지 == "prep",
                "error": f"'{정지 or '?'}' 단계에서 멈췄다(종료코드 {상태.get('exit_code')}) — "
                         f"복사 버튼을 그리지 않는다"}
    상한 = _쿠팡복사상한()
    통과원본 = [r for r in 요약.get("통과") or [] if isinstance(r, dict)]
    자식들 = jobs.children_of(상태.get("id") or "", "coupang_commit")
    경과 = _경과초(상태.get("started_at"))
    기본.update({"통과": [_통과행(r, i, 상한) for i, r in enumerate(통과원본)],
                "상한": 상한, "복사예정": len(_승인목록(요약, 상한)),
                "이미복사": _성공복사(자식들),
                "복사중": any(c.get("status") in jobs.LIVE_STATUSES for c in 자식들),
                "만료": 경과 is None or 경과 > _미리보기유효시간})
    return 기본


def _쿠팡결과ctx(상태: dict) -> dict:
    """복사 결과 표 값 — commit_summary 를 **읽기만** 한다 (D-12 · CP-04 · Pitfall 5).

    중복0 은 summary 값(러너가 verified.json 에서 옮긴 값)에서만 읽는다 — 종료코드로 추정하지
    않는다. None 이면 '증명 못 함' 이지 '통과' 가 아니다.
    """
    상태 = 상태 or {}
    기본 = {"job": _투영(상태), "running": False, "error": None, "정지단계": None,
            "정지설명": "", "재조회": None, "빠짐": [], "늘어남": 0, "복사": [], "신pid없음": 0,
            "중복0": None, "verify": None, "잠금안내": 잠금안내, "exit5": False}
    if 상태.get("status") in jobs.LIVE_STATUSES:
        return {**기본, "running": True}
    요약 = _읽기(Path(상태.get("result_path") or "")) if 상태.get("result_path") else None
    if not isinstance(요약, dict):
        return {**기본, "error": f"복사 산출물이 없거나 깨졌다 — 진행 로그를 봐라 "
                                 f"(종료코드 {상태.get('exit_code')}). 불사자 쿠팡 그룹을 직접 확인해라"}
    # 판매자상품코드 표기 — 부모 미리보기 통과 행에서 pid → 코드
    부모 = jobs.job_status(상태.get("parent_job_id") or "") if 상태.get("parent_job_id") else None
    부모요약 = _미리보기요약(부모) if 부모 else None
    코드 = {str(r.get("대표pid")): r.get("판매자상품코드")
            for r in ((부모요약 or {}).get("통과") or []) if isinstance(r, dict)}
    재 = 요약.get("재조회") if isinstance(요약.get("재조회"), dict) else {}
    빠짐 = 재.get("빠짐") if isinstance(재.get("빠짐"), dict) else {}
    복사 = [r for r in (요약.get("복사") or []) if isinstance(r, dict)]
    정지 = 요약.get("정지단계")
    기본.update({
        "재조회": {"옛": 재.get("옛"), "새": 재.get("새"), "상한경계": bool(재.get("상한경계"))},
        "빠짐": [{"판매자상품코드": 코드.get(p) or p, "사유": str(s or "")} for p, s in 빠짐.items()],
        "늘어남": len(재.get("늘어남") or []),
        "복사": [{"판매자상품코드": r.get("판매자상품코드") or 코드.get(str(r.get("원본pid"))) or "",
                 "상품명": r.get("상품명") or "", "신pid": r.get("신pid") or "",
                 "원본판매가": r.get("원본판매가")} for r in 복사],
        "신pid없음": _정수(요약.get("신pid없음")) or 0,
        "중복0": 요약.get("중복0"),
        "verify": 요약.get("verify") if isinstance(요약.get("verify"), dict) else None,
        "exit5": 상태.get("exit_code") == 5 or 정지 == "재조회" and bool(재.get("늘어남")),
    })
    if 정지:
        기본.update({"정지단계": 정지, "정지설명": _단계설명.get(str(정지), "")})
    return 기본


# kind → (템플릿 조각 이름, ctx 함수). routes/jobs.get_job_result 가 병합한다(기존 키 우선).
결과표: dict[str, tuple[str, Callable[[dict], dict]]] = {
    "coupang_preview": ("_coupang_preview_table.html", _쿠팡미리보기ctx),
    "coupang_commit": ("_coupang_result_table.html", _쿠팡결과ctx),
}
