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
from pydantic import BaseModel, ConfigDict

from webapp import flow, jobs, paths, settings
from webapp.argv import Alias
from webapp.routes.jobs import _경과초, _미리보기유효시간, _상세잡만들기, _투영

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


# kind → (템플릿 조각 이름, ctx 함수). routes/jobs.get_job_result 가 병합한다(기존 키 우선).
결과표: dict[str, tuple[str, Callable[[dict], dict]]] = {
    "prune_preview": ("_prune_preview_table.html", _삭제미리보기ctx),
}
