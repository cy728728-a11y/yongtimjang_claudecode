#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""꺼진 소재 정리 라우터 (Phase 2 / PRUNE-01~03) — **트랙 소유 파일이다.**

    POST /jobs/prune/preview    꺼진 소재 정리 미리보기 접수 (광고 쓰기 0)      [쓰기 — 토큰 필요]
    POST /jobs/prune/commit     꺼진 소재 삭제 (미리보기 잡 id + 타이핑 건수)  [쓰기 — 토큰 필요]
    POST /jobs/prune/retry      실패분만 재시도 (커밋 잡 id + 실패 건수 타이핑) [쓰기 — 토큰 필요]
    결과 조각은 GET /jobs/{id}/result 가 아래 `결과표` 로 그린다(prune_preview · prune_commit).

틀은 Phase 7 쿠팡 트랙(routes/coupang.py) 통째 복제다. 공유 파일(jobs.py · routes/jobs.py ·
main.py · board.html · _job_status.html · flow.py)은 02-02/02-03 에서만 고친다.

**판정을 재구현하지 않는다 — 산출물만 읽는다.** 무엇이 삭제 대상인지(규칙⑥ 중 연동끊김만)는
CLI(`run_ads.py prune` → prune.deletable)가 정하고, 이 모듈은 그 산출물 JSON 을 옮겨 보이기만
한다. 대상 목록을 브라우저에서 받지도, 서버에서 다시 걸러 만들지도 않는다(SAFE-06 · D-02).
"""
import json
from datetime import date
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from webapp import flow, jobs, paths, settings
from webapp.argv import Alias
from webapp.routes.jobs import JobId, _경과초, _미리보기유효시간, _상세잡만들기, _투영

router = APIRouter()

# 남김 사유 → 화면 라벨. 모르는 사유는 원문 그대로(지어내지 않는다).
_남김라벨 = {"AD_UNDER_REVIEW": "검수중", "AD_DISAPPROVED": "거부"}
# 삭제 대상 사유 — CLI 의 deletable 이 고르는 유일한 사유. 화면 라벨만 여기 있다.
_정지사유라벨 = {"AD_ABNORMAL_INTERLOCK": "연동끊김", **_남김라벨}


class PrunePreviewReq(BaseModel):
    """미리보기 요청 — 회차 + (선택) 계정. **대상 목록 필드가 없다** (T-02-16).

    아무 계정도 안 고르면 전 계정이다(빈 --account 함정은 argv.py 가 막는다).
    """

    model_config = ConfigDict(extra="forbid")
    run_dir: str
    accounts: list[Alias] = []


class PruneCommitReq(BaseModel):
    """삭제 요청 — 미리보기 잡 id + **사람이 타이핑한 건수** (L-01 · L-05 · D-04 · T-02-20).

    대상·상한을 받지 않는다(T-02-16). `typed_count` 는 대상이 아니라 확인값이다 — 서버가
    미리보기 산출물에서 다시 센 수와 다르면 409. StrictInt 라 문자열 "5"·true 는 422 다.
    """

    model_config = ConfigDict(extra="forbid")
    preview_job_id: JobId
    typed_count: StrictInt = Field(ge=0)


# ── 상한 — 결정은 이 한 곳 ──────────────────────────────────────────────────

def _삭제상한() -> int:
    """이번 삭제 1회의 상한 — **서버가 정한다. 요청에는 이 값이 없다** (SAFE-07).

    설정 `prune_max_items` 가 정본. 깨졌으면 기본값, 그래도 최소 1 — 0 을 '전량' 으로 읽는 길은
    없다. 라우트가 400 으로 한 번, CLI 가 `--max-items` exit 2 로 한 번 더 막는다(2겹).
    """
    키 = "prune_max_items"
    try:
        n = int(settings.cfg(키, settings.DEFAULTS[키]))
    except (TypeError, ValueError):
        n = int(settings.DEFAULTS[키])
    return max(1, n)


# ── 공통 도우미 ─────────────────────────────────────────────────────────────

def _읽기(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _산출물(상태: dict | None) -> dict | None:
    """잡의 result_path JSON. `accounts` 가 dict 가 아니면 깨진 것으로 본다."""
    경로 = (상태 or {}).get("result_path")
    문서 = _읽기(Path(경로)) if 경로 else None
    if not isinstance(문서, dict) or not isinstance(문서.get("accounts"), dict):
        return None
    return 문서


def _계정들(문서: dict) -> dict[str, dict]:
    return {str(k): (v if isinstance(v, dict) else {}) for k, v in (문서.get("accounts") or {}).items()}


def _대상(v: dict) -> list[dict]:
    return [r for r in (v.get("targets") or []) if isinstance(r, dict) and r.get("adId")]


def _합계(문서: dict) -> int:
    """삭제 예정 건수 — 계정별 targets 합. 최상위 adIds 와 같아야 한다(CLI 가 같은 곳에서 모은다)."""
    return sum(len(_대상(v)) for v in _계정들(문서).values())


def _성공커밋(자식들: list[dict]) -> bool:
    return any(c.get("status") == "done" and c.get("exit_code") == 0 for c in 자식들)


def _라벨(사유) -> str:
    return _정지사유라벨.get(str(사유), str(사유 or ""))


def _파일명(경로) -> str:
    return Path(str(경로)).name if 경로 else ""


# ── ① 미리보기 ──────────────────────────────────────────────────────────────

def _수집중(run_dir: str) -> bool:
    """같은 회차를 새로 수집(prep)하는 중인가 (Pitfall 7).

    prep 이 도는 중이면 ads.json 이 반쪽일 수 있다 — 그걸로 미리보기하면 본 적 없는 범위가
    대상이 된다. prep 의 run_dir 이 비어 있으면 CLI 가 오늘 날짜로 정하므로 오늘 회차로 본다.
    """
    오늘 = date.today().isoformat()
    for j in jobs.recent_jobs(200):
        if j.get("kind") != "prep" or j.get("status") not in jobs.LIVE_STATUSES:
            continue
        if j.get("run_dir") == run_dir or (not j.get("run_dir") and run_dir == 오늘):
            return True
    return False


@router.post("/jobs/prune/preview")
def post_prune_preview(request: Request, req: PrunePreviewReq):
    """**꺼진 소재 정리 미리보기 — 광고 쓰기 0** (PRUNE-01 · D-01).

    회차 화이트리스트(400) → 같은 회차 prep 도는 중(409) → create_job. 같은 미리보기가 도는
    중이면 SINGLETON 가드가 409 — `_상세잡만들기` 의 예외 번역을 그대로 쓴다.
    """
    try:
        paths.run_dir_path(req.run_dir)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if _수집중(req.run_dir):
        raise HTTPException(status_code=409,
                            detail="이 회차를 새로 수집하는 중이다 — 끝나고 미리보기해라")
    return _상세잡만들기("prune_preview", run_dir=req.run_dir, accounts=list(req.accounts))


# ── ② 삭제(커밋) ────────────────────────────────────────────────────────────

def _미리보기검사(부모: dict | None) -> dict:
    """부모 미리보기 → 그 산출물. 실패면 HTTPException. 커밋·재시도가 같은 검사를 쓴다.

      ① 꺼진 소재 미리보기인가(400) · 도는 중이 아닌가(409) · done/0 인가(400)
      ② 24시간 안인가(400 — FLOW-03 · T-02-18. CLI 가 커밋 직전 재조회하지만 사람이 본 것 자체가 낡았다)
    """
    if 부모 is None or 부모.get("kind") != "prune_preview":
        raise HTTPException(status_code=400, detail="꺼진 소재 미리보기 작업이 아니다 — 미리보기부터 해라")
    if 부모.get("status") in jobs.LIVE_STATUSES:
        raise HTTPException(status_code=409, detail="미리보기가 아직 도는 중이다 — 끝나고 다시 눌러라")
    if 부모.get("status") != "done" or 부모.get("exit_code") != 0:
        raise HTTPException(
            status_code=400,
            detail=f"미리보기가 정상으로 안 끝났다({부모.get('status')}, 종료코드 "
                   f"{부모.get('exit_code')}) — 다시 미리보기부터")
    경과 = _경과초(부모.get("started_at"))
    if 경과 is None or 경과 > _미리보기유효시간:
        raise HTTPException(status_code=400, detail="미리보기가 24시간을 넘었다 — 다시 미리보기부터 해라")
    문서 = _산출물(부모)
    if 문서 is None or not isinstance(문서.get("adIds"), list):
        raise HTTPException(status_code=400,
                            detail="미리보기 산출물이 없거나 깨졌다 — 다시 미리보기부터")
    # 최상위 adIds(= CLI 가 --only-ads 로 읽는 값)와 계정별 targets(= 사람이 본 표)가 다르면
    # 본 것과 다른 게 지워진다 — 깨진 산출물로 본다.
    본것 = {r["adId"] for v in _계정들(문서).values() for r in _대상(v)}
    if set(map(str, 문서["adIds"])) != 본것:
        raise HTTPException(status_code=400,
                            detail="미리보기 산출물의 대상 목록과 표가 어긋난다 — 다시 미리보기부터")
    return 문서


def _자식검사(preview_job_id: str, *, 성공도_막기: bool) -> None:
    """같은 미리보기의 삭제가 도는 중이면 409. 성공한 삭제가 있으면 409(D-09 — 쿠팡은 400)."""
    자식들 = jobs.children_of(preview_job_id, "prune_commit")
    if any(c.get("status") in jobs.LIVE_STATUSES for c in 자식들):
        raise HTTPException(status_code=409, detail="이 미리보기의 삭제가 도는 중이다 — 끝나고 결과를 봐라")
    if 성공도_막기 and _성공커밋(자식들):
        raise HTTPException(status_code=409,
                            detail="이 미리보기로 이미 삭제했다 — 실패분 재시도나 새 미리보기를 써라")


@router.post("/jobs/prune/commit")
def post_prune_commit(request: Request, req: PruneCommitReq):
    """**꺼진 소재 삭제 — 되돌릴 수 없다.** 버튼 + 건수 타이핑이 승인이다 (PRUNE-01 · D-04).

      ①② 부모 미리보기 검사(`_미리보기검사`) — 종류·상태·24시간·산출물
      ③ 이 미리보기의 삭제가 도는 중(409) · 이미 성공(409 — ENG-04 · D-09)
      ④ 합계 0 → 400 · 합계 > `_삭제상한()` → 400 (자르지 않고 전량 거부 — SAFE-07)
      ⑤ typed_count ≠ 합계 → **409** (화면이 본 수와 서버가 지금 센 수가 다르다)
      ⑥ create_job — `--only-ads` 는 **부모 산출물 파일 그대로**(SAFE-06 · D-02). 쓰기 잡 전역 가드는 그 안(409)

    두 탭이 동시에 ③을 통과해도 엔진(02-02)이 트랜잭션 안에서 성공 자식을 다시 봐 최종 차단한다.
    """
    부모 = jobs.job_status(req.preview_job_id)
    문서 = _미리보기검사(부모)
    _자식검사(req.preview_job_id, 성공도_막기=True)

    합계 = _합계(문서)
    if 합계 == 0:
        raise HTTPException(status_code=400, detail="지울 꺼진 소재가 0건이다")
    상한 = _삭제상한()
    if 합계 > 상한:
        raise HTTPException(status_code=400,
                            detail=f"삭제 대상 {합계:,}건 > 상한 {상한:,}건 — 계정을 골라 나눠 미리보기해라")
    if req.typed_count != 합계:
        raise HTTPException(
            status_code=409,
            detail=(f"화면이 본 건수({req.typed_count:,})와 지금 지울 건수"
                    f"({합계:,})가 다르다 — 다시 확인해라"))

    계정 = sorted(a for a, v in _계정들(문서).items() if _대상(v))
    결과 = _상세잡만들기("prune_commit", run_dir=부모.get("run_dir"), accounts=계정,
                        parent_job_id=req.preview_job_id,
                        targets_path_override=부모.get("result_path"),
                        prune_max_items=_삭제상한())
    return {"job_id": 결과["job_id"], "건수": 합계, "상한": 상한}


# ── 결과 조각 ctx (GET /jobs/{id}/result 가 결과표로 부른다) ────────────────

def _표행(alias: str, r: dict) -> dict:
    return {"계정": alias, "광고그룹": str(r.get("adGroup") or ""),
            "소재id": str(r.get("adId") or ""), "상품id": str(r.get("mallProductId") or ""),
            "상품명": str(r.get("title") or ""), "정지사유": _라벨(r.get("statusReason")),
            "마지막 변경": str(r.get("editTm") or "")}


def _삭제미리보기ctx(상태: dict) -> dict:
    """미리보기 조각 값. **정본은 CLI 산출물** — 대상을 다시 고르지 않는다(D-02).

    뼈대는 `_쿠팡미리보기ctx`: 도는 중이면 읽지 않고, 산출물이 없거나 깨졌으면 종료코드와 함께
    오류로 — 빈 표를 '지울 것 0건' 으로 읽지 않게.
    """
    상태 = 상태 or {}
    기본 = {"job": _투영(상태), "running": False, "error": None, "계정요약": [], "rows": [],
            "합계": 0, "상한": None, "삭제예정": 0, "이미삭제": False, "삭제중": False,
            "만료": False, "상한초과": False}
    if 상태.get("status") in jobs.LIVE_STATUSES:
        return {**기본, "running": True}
    문서 = _산출물(상태)
    if 문서 is None or 상태.get("status") != "done" or 상태.get("exit_code") != 0:
        return {**기본, "error": f"미리보기 산출물이 없거나 깨졌다 — 진행 로그를 봐라 "
                                 f"(종료코드 {상태.get('exit_code')}). 삭제 버튼을 그리지 않는다"}
    요약, 행 = [], []
    for alias, v in sorted(_계정들(문서).items()):
        대상 = _대상(v)
        남김 = {}
        for 사유, n in (v.get("keep") or {}).items():
            라벨 = _남김라벨.get(str(사유), str(사유))
            try:
                남김[라벨] = 남김.get(라벨, 0) + int(n)
            except (TypeError, ValueError):
                continue
        중단 = v.get("aborted")
        요약.append({"계정": alias, "삭제대상": len(대상), "남김": 남김,
                     "백업": _파일명(v.get("backup")),
                     "중단": flow.중단사유.get(str(중단), str(중단)) if 중단 else "",
                     "건너뜀": str(v.get("skipped") or "")})
        행.extend(_표행(alias, r) for r in 대상)
    합계 = len(행)
    상한 = _삭제상한()
    자식들 = jobs.children_of(상태.get("id") or "", "prune_commit")
    경과 = _경과초(상태.get("started_at"))
    기본.update({"계정요약": 요약, "rows": 행, "합계": 합계, "상한": 상한,
                "삭제예정": 합계 if 0 < 합계 <= 상한 else 0,
                "상한초과": 합계 > 상한,
                "이미삭제": _성공커밋(자식들),
                "삭제중": any(c.get("status") in jobs.LIVE_STATUSES for c in 자식들),
                "만료": 경과 is None or 경과 > _미리보기유효시간})
    return 기본


_제외라벨 = {"다시_켜짐": "다시 켜짐",
            "재조회에_없음": "재조회에 없음(이미 삭제됐거나 조회 실패)"}
_실패결과 = ("실패", "재시도소진")
# prune 결과 화면의 backup_failed 는 flow 공용 문구(입찰가 기준 "광고비") 대신 이걸 쓴다.
_백업실패문구 = "백업을 못 써서 이 계정은 한 건도 지우지 않았다"
_종료코드문구 = {1: "입력/산출물 파일 문제 — 삭제 0", 2: "상한 초과 — 백업 전에 멈췄다, 삭제 0"}


def _제외사유(사유) -> str:
    사유 = str(사유 or "")
    if 사유.startswith("사유_바뀜:"):
        return f"사유 바뀜: {_라벨(사유.split(':', 1)[1])} (지금은 연동끊김이 아니다)"
    return _제외라벨.get(사유, 사유)


def _정수(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _삭제결과ctx(상태: dict) -> dict:
    """삭제 결과 표 값 — 커밋 산출물을 **읽기만** 한다 (SAFE-04 · SAFE-05 · PRUNE-02 · D-03 · D-06).

    종료코드로 성공을 추정하지 않는다 — CLI 는 계정이 중단돼도 0 이다. 계정별 결과·제외 사유·
    새로 꺼진 건수·중단 사유는 전부 산출물에서만 온다.
    """
    상태 = 상태 or {}
    기본 = {"job": _투영(상태), "running": False, "error": None, "계정행": [], "제외행": [],
            "실패행": [], "실패목록": [], "새로꺼짐": 0, "합": {}, "재시도가능": False}
    if 상태.get("status") in jobs.LIVE_STATUSES:
        return {**기본, "running": True}
    문서 = _산출물(상태)
    if 문서 is None:
        코드 = 상태.get("exit_code")
        사유 = _종료코드문구.get(코드) if isinstance(코드, int) else None
        return {**기본, "error": (사유 or "삭제 산출물이 없거나 깨졌다 — 진행 로그를 봐라")
                                 + f" (종료코드 {코드})"}
    계정행, 제외행, 실패행 = [], [], []
    합 = {"성공": 0, "이미없음": 0, "실패": 0, "재시도소진": 0, "제외": 0}
    for alias, v in _계정들(문서).items():
        항목 = [x for x in (v.get("items") or []) if isinstance(x, dict)]
        셈 = {k: sum(1 for x in 항목 if x.get("결과") == k) for k in ("성공", "이미없음", "실패", "재시도소진")}
        제외 = [x for x in (v.get("excluded") or []) if isinstance(x, dict)]
        중단 = v.get("aborted")
        중단말 = ""
        if 중단 == "backup_failed":
            중단말 = _백업실패문구
        elif 중단:
            중단말 = flow.중단사유.get(str(중단), str(중단))
        새로 = _정수(v.get("new_since_preview"))
        계정행.append({"계정": alias, **셈, "제외": len(제외), "새로꺼짐": 새로,
                       "대상": len(_대상(v)), "중단": 중단말,
                       "건너뜀": str(v.get("skipped") or ""), "백업": _파일명(v.get("backup"))})
        for k in 셈:
            합[k] += 셈[k]
        합["제외"] += len(제외)
        기본["새로꺼짐"] += 새로
        제외행.extend({"계정": alias, "adId": str(x.get("adId") or ""),
                       "사유": _제외사유(x.get("사유"))} for x in 제외)
        실패행.extend({"계정": alias, "adId": str(x.get("adId") or ""), "결과": x.get("결과"),
                       "status": x.get("status"), "err": str(x.get("err") or "")}
                      for x in 항목 if x.get("결과") in _실패결과)
    # 안 된 것이 위다(flow.result_rows 관례) — 잘리거나 스크롤 밖으로 밀리지 않게.
    계정행.sort(key=lambda r: (0 if r["중단"] or r["건너뜀"] else
                               1 if r["실패"] or r["재시도소진"] else 2, r["계정"]))
    실패목록 = [r["adId"] for r in 실패행 if r["adId"]]
    재시도가능 = False
    if 실패목록 and 상태.get("status") == "done":
        부모 = jobs.job_status(상태.get("parent_job_id") or "") if 상태.get("parent_job_id") else None
        경과 = _경과초((부모 or {}).get("started_at"))
        재시도가능 = bool(부모 and 경과 is not None and 경과 <= _미리보기유효시간
                         and not any(c.get("status") in jobs.LIVE_STATUSES
                                     for c in jobs.children_of(부모["id"], "prune_commit")))
    기본.update({"계정행": 계정행, "제외행": 제외행, "실패행": 실패행, "실패목록": 실패목록,
                "합": 합, "재시도가능": 재시도가능})
    return 기본


# kind → (템플릿 조각 이름, ctx 함수). routes/jobs.get_job_result 가 병합한다(기존 키 우선).
결과표: dict[str, tuple[str, Callable[[dict], dict]]] = {
    "prune_preview": ("_prune_preview_table.html", _삭제미리보기ctx),
    "prune_commit": ("_prune_result_table.html", _삭제결과ctx),
}
