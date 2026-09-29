#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""썸네일 트랙 라우터 (Phase 7 / THUMB-01·02·03) — **트랙 소유 파일이다.**

    POST /jobs/thumb/estimate     썸네일 견적 잡 접수 (크레딧 0)           [쓰기 — 토큰 필요]
    POST /jobs/thumb/approve      견적 승인 → 그룹 run-dir 에 승인 파일    [쓰기 — 토큰 필요]
    GET  /thumb/{id}/result       결과 조각 (읽기 전용)                    [읽기 — 쿠키]

공유 파일(jobs.py · routes/jobs.py · main.py · board.html · board.js · _job_status.html)은
07-01 에서만 고친다(D-19). 여기서는 routes/jobs.py 의 도우미를 **import 해서 쓰기만** 한다.

흐름 (크레딧은 이 파일 어디에서도 나가지 않는다):
  ① 견적 — 보드 키로 서버가 행을 다시 만들고 규칙②·조인·그룹명·상한을 거른 뒤
     `create_job("thumb_estimate")`. 러너(`thumb_web.py estimate`)가 그룹별 prep 을 돌려
     summary.json 을 쓴다. **숫자는 전부 그 파일 값이다 — 여기서 곱하지 않는다(L-02).**
  ② 승인 — **잡이 아니다.** 그룹 run-dir 마다 `web_approval.json` 을 원자 쓰기하고 복사용 인계
     명령을 보여 줄 뿐이다(D-06). 첫 생성은 사람이 그 명령으로 Claude 세션을 열어서 한다.
     승인 상한 = 그 그룹 견적의 최대크레딧(D-07) — CLI 가 `--max-credits` 누적 검사로 지킨다.
  ③ 결과 — 그룹 run-dir 의 generated/decisions/commit_summary 를 읽어 판매자상품코드 단위로.
     taskId 가 남은 건은 '회수 대기' + recover 명령 **텍스트**만. 재생성 버튼은 없다(L-03).
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, field_validator

from webapp import board, jobs, join, paths, security, settings
from webapp.routes.jobs import (JobId, _경로표시, _상세잡만들기, _직전산출물, _투영, _판정읽기,
                                보드키, 상세견적_상한)

router = APIRouter()

# 규칙② 기호 — board.fold_products 가 규칙 이름 첫 글자를 모아 `rules` 문자열로 만든다.
_규칙2 = "②"


class ThumbEstimateReq(BaseModel):
    """썸네일 견적 요청 — **회차와 보드 행 키뿐이다** (T-07-20).

    그룹명·productId·판매자상품코드를 받지 않는다. 그룹명은 서버가 조인 산출물에서만 뽑는다
    (L-06). 모르는 필드는 422 — 대상을 실어 보내는 요청은 화면이 고장났거나 우회 시도다.
    """

    model_config = ConfigDict(extra="forbid")
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


class ThumbApproveReq(BaseModel):
    """실행 승인 — **견적 잡 id 하나뿐이다** (T-07-21).

    대상·상한을 받지 않는다. 대상은 부모 summary.json 의 그룹별 `대상`, 상한은 같은 파일의
    그룹 `최대크레딧` 을 서버가 읽는다. 화면이 숫자를 보내면 그 숫자만큼 크레딧이 더 나간다.
    """

    model_config = ConfigDict(extra="forbid")
    estimate_job_id: JobId


# ── 공통 도우미 ─────────────────────────────────────────────────────────────

def _인계명령(run_dir) -> str:
    """승인된 그룹 run-dir → Claude 세션에 붙여 넣을 한 줄.

    **D-06 을 뒤집을 때(서버가 직접 생성을 도는 헤드리스 실행으로 바꿀 때) 고칠 유일한 자리다.**
    지금은 표시 텍스트일 뿐이고 서버는 이 명령을 실행하지 않는다(T-07-22). 경로는 따옴표로
    감싼다 — 그룹명 폴더에 공백이 섞여도 한 인자로 읽힌다(SKILL.md '웹 승인 인계' 트리거).
    """
    return f'썸네일 작업 이어서 "{run_dir}"'


def _양의정수(v) -> bool:
    # bool 은 int 의 하위형이라 따로 막는다 — True 가 상한 1 이 되면 안 된다
    return isinstance(v, int) and not isinstance(v, bool) and v > 0


def _그룹폴더(job_id: str, 항목: dict) -> Path | None:
    """summary 의 그룹 run_dir → 실제 폴더. **이 견적 러너 폴더 바로 밑일 때만** 돌려준다.

    summary.json 은 러너가 쓴 파일이지만 그 안의 경로를 그대로 믿고 쓰기를 하면, 파일 하나가
    승인 파일을 아무 데나 떨구게 만든다(T-07-22). 폴더는 `thumb_dir_of` 에서만 유도한다.
    """
    try:
        뿌리 = jobs.thumb_dir_of(job_id).resolve()
        폴더 = Path(str(항목.get("run_dir") or "")).resolve()
    except (ValueError, OSError):
        return None
    if not 항목.get("run_dir") or 폴더.parent != 뿌리:
        return None
    return 폴더


def _읽기(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _원자쓰기(p: Path, 문서: dict) -> None:
    """tmp → os.replace. Claude 세션이 반쯤 쓴 승인 파일을 읽지 않게."""
    tmp = p.with_name(f"{p.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(문서, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, p)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _견적부모(job_id: str) -> dict:
    """승인·결과가 기대는 부모 견적 — 종류·완료·정상 3단 검사(post_detail_submit 모양)."""
    부모 = jobs.job_status(job_id)
    if 부모 is None or 부모.get("kind") != "thumb_estimate":
        raise HTTPException(status_code=400, detail="썸네일 견적 작업이 아니다 — 먼저 견적부터 해라")
    if 부모.get("status") in jobs.LIVE_STATUSES:
        raise HTTPException(status_code=400, detail="견적이 아직 안 끝났다 — 끝나고 다시 눌러라")
    if 부모.get("status") != "done":
        raise HTTPException(
            status_code=400,
            detail=f"견적이 정상으로 안 끝났다({부모.get('status')}) — 견적부터 다시 해라")
    return 부모


def _요약읽기(부모: dict) -> dict:
    문서 = _읽기(Path(부모.get("result_path") or ""))
    if not isinstance(문서, dict):
        raise HTTPException(status_code=400,
                            detail="견적 산출물(summary.json)이 없거나 깨졌다 — 견적부터 다시 해라")
    return 문서


def _그룹들(요약: dict) -> list[dict]:
    return [g for g in (요약.get("그룹") or []) if isinstance(g, dict)]


# ── ① 견적 ──────────────────────────────────────────────────────────────────

@router.post("/jobs/thumb/estimate")
def post_thumb_estimate(request: Request, req: ThumbEstimateReq):
    """**썸네일 견적** — 크레딧 0. 고른 보드 행 중 규칙② 대상만 견적 잡으로 넘긴다.

    대상은 **서버가 다시 만든다** (D-02 · L-06 · T-07-20) — `post_detail_estimate` 와 같은 뼈대:
      ① 직전 성공 조인 스캔 산출물(없으면 409) — 보드 행 재구성 + 판매자상품코드 + 마켓그룹
      ② 회차 판정 → `board.fold_products` → `join.attach`, 요청 키로 고른다(보드에 없는 키 400)
      ③ 행마다 뺀다(사유): 규칙② 아님 · 조인 미해소 · 그룹명 미특정 · 같은 불사자 상품 중복
      ④ 통과분을 노출 내림차순으로 세워 `thumb_max_items` 앞만 — 뒤는 '상한초과'
      ⑤ 통과 0건이면 400(사유 목록) — 빈 inputs 로 잡을 만들지 않는다

    **그룹명은 NN-N 번호가 아니라 조인 문서의 전체 이름이다**(RESEARCH D-04) — prep 은
    `--group-name` 으로 불사자 그룹을 이름으로 찾는다. 같은 번호의 그룹이 둘 이상이면
    `join.group_index` 는 조용히 하나로 덮으므로, 여기서 따로 세어 모호하면 뺀다.

    기작업(이미가공) 여부로 여기서 빼지 않는다 — prep 이 현황판·실시간 조회로 다시 판정한다(D-03).
    """
    if not req.run_dir:
        raise HTTPException(status_code=400, detail="썸네일 견적에는 회차가 필요하다")
    try:
        paths.run_dir_path(req.run_dir)          # 화이트리스트 — 파일을 읽기 전에
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    조인문서 = _직전산출물("bulsaja_scan", req.run_dir,
                        "조인 스캔을 먼저 돌려라 — 보드 행을 불사자 상품·마켓그룹에 이어야 대상이 정해진다")
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
    # 번호 → 그 번호를 가진 그룹명 전부. 둘 이상이면 모호하다(group_index 는 덮어쓴다).
    번호별그룹: dict[str, list[str]] = {}
    for g in (조인문서.get("마켓그룹") or []):
        if not isinstance(g, dict):
            continue
        이름 = str(g.get("그룹명") or "").strip()
        n = join.market_number(이름)
        if n and 이름:
            번호별그룹.setdefault(n, []).append(이름)

    통과: list[dict] = []
    제외: list[dict] = []
    웹제외: dict[str, dict] = {}
    본상품: set[str] = set()
    for 키 in dict.fromkeys(req.keys):         # 같은 키 두 번은 한 번으로(순서 유지)
        행 = 행색인[키]
        관측 = 관측색인.get((행.get("acct"), 행.get("mallProductId"))) or {}
        코드 = 관측.get("판매자상품코드")
        표기 = str(코드) if 코드 else 키

        def 뺀다(사유: str, 키=키, 표기=표기):
            제외.append({"판매자상품코드": 표기, "사유": 사유})
            웹제외[키] = {"판매자상품코드": 표기, "사유": 사유}

        if _규칙2 not in str(행.get("rules") or ""):
            뺀다("규칙② 아님 — 썸네일 교체 대상(노출 100+ & CTR<1%)이 아니다")
            continue
        if not 행.get("해소"):
            뺀다(f"조인 미해소 — {행.get('사유') or '불사자 상품에 안 이어졌다'}")
            continue
        pid = 행.get("productId")
        if not pid or not 코드:
            뺀다("조인 미해소 — 조인 결과에 productId·판매자상품코드가 없다. 조인 스캔을 다시 돌려라")
            continue
        후보 = 번호별그룹.get(str(행.get("번호") or ""), [])
        if len(후보) != 1:
            뺀다(f"그룹명 미특정 — 번호 '{행.get('번호')}' 에 맞는 불사자 그룹이 {len(후보)}개다")
            continue
        if pid in 본상품:
            뺀다("같은 불사자 상품이 이미 대상에 있다")
            continue
        본상품.add(pid)
        통과.append({"키": 키, "pid": str(pid), "코드": str(코드), "그룹명": 후보[0],
                    "imp": 행.get("imp") or 0, "표기": 표기})

    # 노출 내림차순 — 스킬의 "상위 N" 관례(D-02). 정렬은 안정적이라 동률이면 고른 순서다.
    통과.sort(key=lambda x: -(x["imp"] if isinstance(x["imp"], (int, float)) else 0))
    상한 = int(settings.cfg("thumb_max_items", settings.DEFAULTS["thumb_max_items"]))
    for x in 통과[상한:]:
        사유 = f"상한초과 — 노출 상위 {상한}건만 견적한다(thumb_max_items)"
        제외.append({"판매자상품코드": x["표기"], "사유": 사유})
        웹제외[x["키"]] = {"판매자상품코드": x["표기"], "사유": 사유}
    통과 = 통과[:상한]

    if not 통과:
        사유들 = " / ".join(f"{x['판매자상품코드']}: {x['사유']}" for x in 제외[:20])
        raise HTTPException(status_code=400,
                            detail=f"규칙② 대상이 0건이다 — 견적을 만들지 않았다. {사유들}")

    그룹: dict[str, list[str]] = {}
    for x in 통과:
        그룹.setdefault(x["그룹명"], []).append(x["pid"])
    문서 = {"그룹": 그룹, "코드": {x["pid"]: x["코드"] for x in 통과},
            "웹제외": 웹제외, "선택": len(req.keys)}
    결과 = _상세잡만들기("thumb_estimate", run_dir=req.run_dir, thumb_inputs=문서)
    return {"job_id": 결과["job_id"], "제외": 제외}


# ── 견적 표 ctx (GET /jobs/{id}/result 가 결과표로 부른다) ──────────────────

# summary 그룹 항목의 분류 칸 — (필드, 화면 이름). 대상은 따로(생성 대상).
_분류칸 = (("이미가공", "이미가공"), ("정합검사", "정합검사"), ("삭제대상", "삭제대상"),
          ("조회실패", "조회실패"), ("현황판제외", "현황판제외"))


def _썸네일견적ctx(상태: dict) -> dict:
    """견적 표 조각 값. **숫자는 전부 러너 summary.json 값이다** — 곱하지 않는다(L-02).

    뼈대는 `_상세견적ctx`: 도는 중이면 읽지 않고, 산출물이 없거나 깨졌으면 종료코드와 함께
    오류로 — 빈 표를 결과로 읽지 않게.
    """
    상태 = 상태 or {}
    기본 = {"job": _투영(상태), "running": False, "error": None, "합계": {}, "계정": None,
            "그룹행": [], "웹제외": [], "선택": None, "승인됨": False, "인계": []}
    try:
        입력 = json.loads(Path(상태.get("targets_path") or "").read_text(encoding="utf-8"))
        웹제외 = 입력.get("웹제외") or {}
        기본["웹제외"] = [
            {"판매자상품코드": (v or {}).get("판매자상품코드") or k, "사유": (v or {}).get("사유")}
            if isinstance(v, dict) else {"판매자상품코드": k, "사유": str(v)}
            for k, v in 웹제외.items()]
        기본["선택"] = 입력.get("선택")
    except Exception:
        pass                                   # 웹 제외 목록이 없어도 견적 숫자는 보인다
    if 상태.get("status") in jobs.LIVE_STATUSES:
        return {**기본, "running": True}
    요약 = _읽기(Path(상태.get("result_path") or "")) if 상태.get("result_path") else None
    if not isinstance(요약, dict):
        return {**기본, "error": f"견적 산출물(summary.json)이 없거나 깨졌다 — 진행 로그를 봐라 "
                                 f"(종료코드 {상태.get('exit_code')})"}
    코드 = 요약.get("코드") if isinstance(요약.get("코드"), dict) else {}
    그룹행 = []
    인계 = []
    승인수 = 0
    for g in _그룹들(요약):
        행 = [{"판매자상품코드": 코드.get(p, p), "분류": "생성 대상", "사유": ""}
              for p in (g.get("대상") or [])]
        for 필드, 이름 in _분류칸:
            v = g.get(필드) or {}
            if isinstance(v, dict):
                행 += [{"판매자상품코드": 코드.get(p, p), "분류": 이름, "사유": str(s or "")}
                       for p, s in v.items()]
            elif isinstance(v, list):
                행 += [{"판매자상품코드": 코드.get(p, p), "분류": 이름, "사유": ""} for p in v]
        폴더 = _그룹폴더(상태.get("id") or "", g)
        승인 = bool(폴더 and (폴더 / "web_approval.json").is_file())
        if 승인:
            승인수 += 1
            인계.append({"그룹명": g.get("그룹명"), "명령": _인계명령(폴더)})
        그룹행.append({"그룹명": g.get("그룹명"), "오류": g.get("오류"), "시트id": g.get("시트id"),
                     "예상크레딧": g.get("예상크레딧"), "최대크레딧": g.get("최대크레딧"),
                     "승인됨": 승인, "행": 행})
    기본.update({"합계": 요약.get("합계") if isinstance(요약.get("합계"), dict) else {},
                "계정": 요약.get("계정"), "그룹행": 그룹행, "승인됨": 승인수 > 0, "인계": 인계,
                "error": ("계정 불일치 — 계정 확인부터 해라" if 요약.get("오류") == "계정불일치"
                          else None)})
    return 기본


# kind → (템플릿 조각 이름, ctx 함수). routes/jobs.get_job_result 가 병합한다(기존 키 우선).
결과표: dict[str, tuple[str, Callable[[dict], dict]]] = {
    "thumb_estimate": ("_thumb_estimate_table.html", _썸네일견적ctx),
}


# ── ② 실행 승인 ─────────────────────────────────────────────────────────────

@router.post("/jobs/thumb/approve")
def post_thumb_approve(request: Request, req: ThumbApproveReq):
    """**실행 승인 — 크레딧 0.** 잡을 만들지 않는다. 그룹별 `web_approval.json` 만 쓴다(D-06).

      ① 부모가 썸네일 견적 · 끝났다 · 정상이다 (3단)
      ② summary.json 이 읽힌다 · 계정 불일치로 끝난 견적이 아니다
      ③ 합계 K 가 양의 정수 — 0 이면 "생성 대상 0건"
      ④ 대상이 있는 그룹마다: 폴더가 이 견적 러너 폴더 밑 · 시트id 있음 ·
         예상/최대크레딧이 양의 정수(bool·음수·비정수 거부) · 승인 파일이 아직 없음
         — **전 그룹을 먼저 검사하고 나서** 쓴다(반쯤 승인된 견적을 만들지 않는다)
      ⑤ 원자 쓰기. 승인 상한 = 그 그룹 최대크레딧(D-07) — 재생성 1회까지가 사람이 본 최대치다

    응답: htmx 면 견적 표 조각(인계 명령이 보이는), 아니면 JSON `{승인: [{그룹명, run_dir, 명령, …}]}`.
    """
    부모 = _견적부모(req.estimate_job_id)
    요약 = _요약읽기(부모)
    if 요약.get("오류"):
        raise HTTPException(status_code=400,
                            detail=f"견적이 오류로 끝났다({요약.get('오류')}) — 견적부터 다시 해라")
    K = (요약.get("합계") or {}).get("K")
    if not _양의정수(K):
        raise HTTPException(status_code=400,
                            detail="생성 대상 0건 — 승인할 게 없다(이미 가공된 상품은 재작업 flag 가 필요, D-03)")

    쓸것: list[tuple[Path, dict]] = []
    for g in _그룹들(요약):
        ids = [p for p in (g.get("대상") or []) if isinstance(p, str) and p]
        if g.get("오류") or not ids:
            continue
        이름 = g.get("그룹명")
        폴더 = _그룹폴더(req.estimate_job_id, g)
        if 폴더 is None or not 폴더.is_dir():
            raise HTTPException(status_code=400,
                                detail=f"그룹 '{이름}' 의 run-dir 이 이 견적 폴더 밖이거나 없다 — 견적부터 다시 해라")
        예상, 최대 = g.get("예상크레딧"), g.get("최대크레딧")
        if not _양의정수(예상) or not _양의정수(최대):
            raise HTTPException(status_code=400,
                                detail=f"그룹 '{이름}' 의 예상/최대 크레딧이 양의 정수가 아니다 — "
                                       f"견적 산출물이 이상하다. 견적부터 다시 해라")
        시트 = g.get("시트id")
        if not isinstance(시트, str) or not 시트:
            raise HTTPException(status_code=400,
                                detail=f"그룹 '{이름}' 의 현황판 시트id 가 없다 — 견적부터 다시 해라")
        if (폴더 / "web_approval.json").exists():
            raise HTTPException(status_code=400,
                                detail=f"그룹 '{이름}' 은 이미 승인했다 — 다시 하려면 새 견적부터")
        쓸것.append((폴더, {"승인시각": datetime.now().astimezone().isoformat(timespec="seconds"),
                           "견적잡id": req.estimate_job_id, "계정": 요약.get("계정"),
                           "그룹명": 이름, "시트id": 시트, "ids": ids,
                           "예상크레딧": 예상, "승인상한크레딧": 최대}))
    if not 쓸것:
        raise HTTPException(status_code=400, detail="생성 대상 0건 — 승인할 그룹이 없다")

    승인 = []
    for 폴더, 문서 in 쓸것:
        _원자쓰기(폴더 / "web_approval.json", 문서)
        승인.append({"그룹명": 문서["그룹명"], "run_dir": str(폴더), "명령": _인계명령(폴더),
                    "예상크레딧": 문서["예상크레딧"], "승인상한크레딧": 문서["승인상한크레딧"]})

    if request.headers.get("hx-request"):
        from webapp.main import templates  # 지연 import — main 이 이 모듈을 먼저 부른다
        return templates.TemplateResponse(request, "_thumb_estimate_table.html",
                                          _썸네일견적ctx(jobs.job_status(req.estimate_job_id)))
    return {"승인": 승인}


# ── ③ 결과 보기 ─────────────────────────────────────────────────────────────

def _recover명령(폴더: Path) -> str:
    """회수 대기 건의 명령 **텍스트**. 서버는 실행하지 않는다 — 크레딧 0 이지만 불사자 조회다."""
    return (f'.venv/bin/python3 .claude/skills/bulsaja-thumbnail/scripts/run_thumbs.py recover '
            f'--run-dir "{폴더}"')


def _행상태(pid: str, 생성: dict, 판정: dict, 커밋: dict | None) -> tuple[str, str]:
    """pid 한 건의 (상태, 사유). 위에서부터 먼저 맞는 것이 이긴다 — 실측 필드 기준:

      commit_summary.완료 에 있음            → 반영완료   (불사자 저장까지 끝남 — 정본)
      commit_summary.보류 에 있음            → 보류       (사유 = 그 값)
      commit_summary.기존대표유지 에 있음     → 제외       (기존 대표 유지로 종결)
      generated: taskId 있고 생성본 없음      → 회수대기   (크레딧 이미 나감 — recover, 재생성 금지)
      generated: 생성본 없음(오류만)          → 보류       (생성 실패)
      decisions.판정 == 사용가능             → 사용가능
      decisions.판정 에 '제외' 또는 원본대체   → 제외       (fallback 종결 포함)
      decisions.판정 그 밖                   → 보류
      generated: 생성본 있고 판정 없음        → 생성
      generated 에 없음                     → 생성 전
    """
    if isinstance(커밋, dict):
        if pid in (커밋.get("완료") or []):
            return "반영완료", ""
        보류 = 커밋.get("보류") if isinstance(커밋.get("보류"), dict) else {}
        if pid in 보류:
            return "보류", str(보류[pid] or "")
        if pid in (커밋.get("기존대표유지") or []):
            return "제외", "기존 대표 유지로 종결"
    rec = 생성.get(pid)
    if not isinstance(rec, dict):
        return "생성 전", ""
    if "생성본" not in rec:
        if rec.get("taskId"):
            return "회수대기", str(rec.get("오류") or "결과 미수신")
        return "보류", f"생성 실패 — {rec.get('오류') or ''}".rstrip(" —")
    d = 판정.get(pid)
    if isinstance(d, dict) and d.get("판정"):
        v = str(d.get("판정"))
        사유 = str(d.get("사유") or "")
        if v == "사용가능":
            return "사용가능", 사유
        if "제외" in v or "원본대체" in v:
            return "제외", f"{v} {사유}".strip()
        return "보류", f"{v} {사유}".strip()
    return "생성", ""


def _썸네일결과ctx(job_id: str) -> dict:
    """결과 표 값. 그룹 run-dir 파일을 **읽기만** 한다. review.html 은 경로 텍스트만(T-07-23)."""
    부모 = jobs.job_status(job_id)
    if 부모 is None or 부모.get("kind") != "thumb_estimate":
        raise HTTPException(status_code=404, detail="그런 썸네일 견적이 없다")
    기본 = {"job": _투영(부모), "error": None, "행": [], "그룹": []}
    요약 = _읽기(Path(부모.get("result_path") or "")) if 부모.get("result_path") else None
    if not isinstance(요약, dict):
        return {**기본, "error": "견적 산출물(summary.json)이 없거나 깨졌다 — 결과를 읽을 근거가 없다"}
    코드 = 요약.get("코드") if isinstance(요약.get("코드"), dict) else {}
    for g in _그룹들(요약):
        폴더 = _그룹폴더(job_id, g)
        if 폴더 is None:
            기본["그룹"].append({"그룹명": g.get("그룹명"), "오류": "run-dir 이 견적 폴더 밖이다",
                               "review": {"경로": "", "있음": False}, "파일": {}})
            continue
        생성 = _읽기(폴더 / "generated.json")
        판정 = _읽기(폴더 / "decisions.json")
        커밋 = _읽기(폴더 / "commit_summary.json")
        승인 = _읽기(폴더 / "web_approval.json")
        생성 = 생성 if isinstance(생성, dict) else {}
        판정 = 판정 if isinstance(판정, dict) else {}
        # 대상 = 승인된 ids(있으면) → 견적 대상 → 생성 기록에만 있는 것 순서로, 중복 없이
        ids = list(dict.fromkeys(
            [p for p in ((승인 or {}).get("ids") or g.get("대상") or []) if isinstance(p, str)]
            + [p for p in 생성 if isinstance(p, str)]))
        기본["그룹"].append({
            "그룹명": g.get("그룹명"), "오류": g.get("오류"), "run_dir": str(폴더),
            "review": _경로표시(폴더 / "review.html"),
            "파일": {"generated": bool(생성), "decisions": bool(판정),
                    "commit_summary": isinstance(커밋, dict), "승인": isinstance(승인, dict)}})
        for pid in ids:
            상태, 사유 = _행상태(pid, 생성, 판정, 커밋 if isinstance(커밋, dict) else None)
            rec = 생성.get(pid) if isinstance(생성.get(pid), dict) else {}
            기본["행"].append({
                "판매자상품코드": 코드.get(pid, pid), "그룹명": g.get("그룹명"), "상태": 상태,
                "크레딧": rec.get("크레딧"), "사유": 사유,
                "명령": _recover명령(폴더) if 상태 == "회수대기" else ""})
    return 기본


@router.get("/thumb/{job_id}/result")
def get_thumb_result(job_id: str, request: Request):
    """결과 조각 — **읽기 전용.** 부수효과가 없다(GET 규율 — routes/jobs.py 머리 주석).

    htmx 요청이면 조각, 아니면 JSON(같은 ctx). 재생성·반영 버튼은 그리지 않는다(L-03 · D-08).
    """
    if not security.page_cookie_ok(request):
        return PlainTextResponse("토큰이 필요하다", status_code=403)
    try:
        jobs.thumb_dir_of(job_id)                # 잡 id 모양 검사 — 모양 밖이면 404
    except ValueError:
        raise HTTPException(status_code=404, detail="그런 썸네일 견적이 없다")
    ctx = _썸네일결과ctx(job_id)
    if not request.headers.get("hx-request"):
        return ctx

    from webapp.main import templates  # 지연 import — main 이 이 모듈을 먼저 부른다

    return templates.TemplateResponse(request, "_thumb_result_table.html", ctx)
