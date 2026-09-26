# -*- coding: utf-8 -*-
"""불사자 마켓 수정업로드 (스마트스토어 고정) — 미리보기 · 반영 · 이어서 확인 · 복원 · 작업창 스냅샷.

불사자 `bulsaja_market_update` 는 **불사자에 저장된 변경사항 전부**(상세·가격·상품명·옵션)를
스마트스토어로 민다. 되돌릴 수 없다. 그래서 이 CLI 는 쓰기 0 미리보기를 두 겹으로 지킨다:
  ① 구조 — 미리보기 함수에는 confirm:true 를 부르는 코드 경로가 없다
  ② 사후 확인 — confirm:false 한 건마다 upload_tasks 창을 다시 읽어 그 상품의 새 행이
     생겼으면(taskId > 워터마크) P0 로 전량 중단한다
그리고 계정 확인모드(mcp_settings)가 strict|balanced 가 아니면 아예 시작하지 않는다
(fast = 고위험만 확인 → confirm:false 가 곧 쓰기가 될 수 있다).

**실제 쓰기(--commit)는 사람 체크포인트 뒤에서만 돈다 (L-01).** 웹앱이 게이트를 통과시킨
뒤 subprocess 로 부르고, 상한은 --max-items 로 CLI 도 한 번 더 강제한다.

모드 (상호배타, 하나 필수):
  --preview                  미리보기 — 상품마다 confirm:false 만. 토큰은 저장하지 않는다
  --commit                   반영 — 상품당 confirm:false → 새 토큰 → confirm:true, taskId 선저장 후 폴링
  --poll-only                이어서 확인 — 체크포인트의 대기 항목만 upload_tasks 창에서 확인
  --tasks-snapshot <out>     작업창 스냅샷 — 읽기 전용 증거 (라이브 스모크 전후 diff 용)
  --restore-backup <ⓐ> + --preview|--commit
                             복원 — detail_apply 2단으로 원본 상세를 되돌리고 스토어로 재반영

종료코드: 0 전부 종결/미리보기 완료 · 2 입력오류·확인모드 거부·P0 쓰기의심 · 3 대기 미완(실패 아님)
         · 4 계정 불일치 · 5 --max-items 초과 시도
센티널 (마지막 줄, flush=True): ###MARKET### 성공 a / 실패 f / 스킵 s / 대기 p / 전체 t
  (preview 에선 성공 = 반영가능 수, 대기 = 0)

파일:
  <run-dir>/market_status.json        체크포인트(정본은 불사자 서버, 이 파일은 재개용)
  <backup-dir>/<productId>.json       ⓑ 반영 직전 상태 (무엇을 밀었는지 증거)
  <detail-backup-dir>/<productId>.json ⓐ AI 접수 직전 원본 (06-01 detail_batch --backup-out 이 씀)

사용:
  .venv/bin/python3 market_update.py --run-dir <RUN> --expect-nick <닉> --preview
        --targets <json> --detail-backup-dir <ⓐ폴더> --backup-dir <ⓑ폴더> [--summary-out <json>]
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 불사자 MCP 클라이언트는 카테고리 교정 스킬의 것을 재사용 (detail_batch.py 40-52 관용구).
# **경로를 박지 않는다** — 이 파일 위치에서 스킬 루트를 거슬러 올라가 찾는다.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILLS_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", ".."))
SKILL_SCRIPTS = os.path.join(SKILLS_DIR, "bulsaja-category-fix", "scripts")
sys.path.insert(0, SKILL_SCRIPTS)
from bulsaja_mcp import BulsajaMCP  # noqa: E402

MARKET = "SMARTSTORE"            # L-07 — 마켓 인자를 받지 않는다
EXIT_OK, EXIT_INPUT, EXIT_POLL, EXIT_NICK, EXIT_BUDGET = 0, 2, 3, 4, 5
허용확인모드 = {"strict", "balanced"}
TOOL_UPDATE = "bulsaja_market_update"
TOOL_TASKS = "bulsaja_upload_tasks"
TOOL_APPLY = "bulsaja_detail_apply"
종결상태 = ("성공", "실패")
_FALSY = {"0", "false", "no", "n", "", "none", "null"}


class 쓰기의심(Exception):
    """confirm:false 인데 쓰기가 났을 수 있다 — P0. 전량 중단한다."""


class 조회실패(Exception):
    """응답 모양이 아니다 — '0건' 으로 접지 않는다."""


# ── 유틸 (detail_batch.py 55-90 · 272-290 · 323-334 와 같은 동작) ──────────────

def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _원자쓰기(path, obj):
    """임시파일 → os.replace. 실패는 **예외로** 올린다 (백업 쓰기는 실패를 알아야 한다)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    본문 = json.dumps(obj, ensure_ascii=False, indent=1)
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(본문)
    os.replace(tmp, path)


def save_json(path, obj):
    """체크포인트·요약 저장 — 실패는 경고만 (detail_batch 와 같은 동작)."""
    try:
        _원자쓰기(path, obj)
    except Exception as e:
        print(f"[경고] 저장 실패 {path}: {e}", flush=True)


def sanitize(obj, depth=0):
    """응답 구조 확인용 (값 축약)."""
    if depth > 3:
        return "..."
    if isinstance(obj, dict):
        return {k: sanitize(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(v, depth + 1) for v in obj[:3]] + (["..."] if len(obj) > 3 else [])
    s = str(obj)
    return s[:60] + ("..." if len(s) > 60 else "")


def extract_task_id(r):
    """접수 응답에서 작업번호 추출 (형태 유연)."""
    if not isinstance(r, dict):
        return None
    for k in ("taskId", "task_id", "작업번호", "작업id", "id"):
        v = r.get(k)
        if v:
            return str(v)
    for k in ("task", "작업", "data"):
        v = r.get(k)
        if isinstance(v, dict):
            t = extract_task_id(v)
            if t:
                return t
    return None


def _표시규칙제거(obj):
    """불사자 응답의 모델 대상 지시문(`표시규칙`)을 버린 사본 — 산출물에 남기지 않는다."""
    if isinstance(obj, dict):
        return {k: _표시규칙제거(v) for k, v in obj.items() if k != "표시규칙"}
    if isinstance(obj, list):
        return [_표시규칙제거(v) for v in obj]
    return obj


def _토큰마스킹(obj):
    """확인 토큰 값을 가린 사본 (T-06-12). 원문 보존용."""
    if isinstance(obj, dict):
        return {k: ("***" if "token" in str(k).lower() else _토큰마스킹(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [_토큰마스킹(v) for v in obj]
    return obj


def _지금():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def 불리언정규화(v):
    """'0' '1' False 1 None 을 같은 규약으로 읽는다 (detail_batch 와 같은 규칙)."""
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    return str(v).strip().lower() not in _FALSY


def _꼬리(tid):
    """taskId 는 로그에 끝 8자리만 (기존 관용)."""
    return str(tid)[-8:] if tid else "-"


def _계정확인(mcp, 기대닉):
    """`bulsaja_my_profile` 1회 → (닉, 통과). 조회 실패 = 불통과 (확인 못 한 계정으로 진행 안 함)."""
    try:
        p = _표시규칙제거(mcp.call_tool("bulsaja_my_profile", {}) or {})
        닉 = str(p.get("닉네임") or "")
    except Exception as e:
        print(f"[경고] 계정 조회 실패: {str(e)[:120]}", flush=True)
        return None, False
    return 닉, 닉 == str(기대닉)


def _확인모드찾기(r, depth=0):
    """mcp_settings 응답에서 confirmationMode 문자열을 찾는다. 못 찾으면 None (= 거부)."""
    if depth > 3 or not isinstance(r, dict):
        return None
    v = r.get("confirmationMode")
    if isinstance(v, str) and v:
        return v.strip()
    for x in r.values():
        if isinstance(x, dict):
            t = _확인모드찾기(x, depth + 1)
            if t:
                return t
    return None


def _연결과가드(mcp, args):
    """L-06 계정 확인 → 확인모드 확인. 반환 (종료코드|None, 계정, 확인모드).

    계정이 다르면 다른 도구를 한 번도 부르지 않고 exit 4.
    확인모드가 strict|balanced 가 아니거나 못 읽으면 쓰기 도구를 부르기 전에 exit 2.
    """
    닉, 통과 = _계정확인(mcp, args.expect_nick)
    if not 통과:
        print(f"⛔ 붙어 있는 불사자 계정({닉})이 기대 계정({args.expect_nick})이 아니다 "
              f"— 아무것도 조회·반영하지 않는다", flush=True)
        return EXIT_NICK, 닉, None
    try:
        r = _표시규칙제거(mcp.call_tool("bulsaja_mcp_settings", {"mode": "get"}) or {})
        모드 = _확인모드찾기(r)
    except Exception as e:
        print(f"[경고] 확인모드 조회 실패: {str(e)[:120]}", flush=True)
        모드 = None
    if 모드 not in 허용확인모드:
        print(f"⛔ 확인 모드가 {모드} — 미리보기가 쓰기가 될 수 있어 거부 "
              f"(strict|balanced 만 허용)", flush=True)
        return EXIT_INPUT, 닉, 모드
    return None, 닉, 모드


# ── 응답 해석 (ss_index_calls 규약 — 지연 import, 오류를 0건으로 접지 않는다) ──

def _규약():
    if SCRIPT_DIR not in sys.path:
        sys.path.insert(0, SCRIPT_DIR)
    import ss_index_calls  # 지연 import
    return ss_index_calls


def _창목록(mcp, 상태):
    """upload_tasks list 한 창. 상태 '기본' = 필터 없음. `마켓작업` 이 리스트가 아니면 조회실패."""
    인자 = {"mode": "list"}
    if 상태 != "기본":
        인자["status"] = 상태
    try:
        r = _표시규칙제거(mcp.call_tool(TOOL_TASKS, 인자))
        return _규약().목록꺼내기(r, ("마켓작업",), f" (창 {상태})", "마켓작업")
    except Exception as e:
        raise 조회실패(f"upload_tasks {상태}: {str(e)[:200]}") from e


def _창읽기(mcp, 상태들):
    """여러 창을 합친다 → (taskId→행, DLQ taskId 집합). **taskIds 필터는 쓰지 않는다**(무시됨)."""
    행들, dlq = {}, set()
    for 상태 in 상태들:
        for x in _창목록(mcp, 상태):
            if not isinstance(x, dict):
                continue
            tid = str(x.get("taskId") or "")
            if not tid:
                continue
            행들[tid] = x
            if 상태 == "DLQ":
                dlq.add(tid)
    return 행들, dlq


def _숫자(tid):
    try:
        return int(str(tid))
    except (TypeError, ValueError):
        return None


def _워터마크(행들):
    """숫자 taskId 최댓값 (문자열). 없으면 None."""
    값들 = [n for n in (_숫자(t) for t in 행들) if n is not None]
    return str(max(값들)) if 값들 else None


def _새행들(행들, pid, 워터마크):
    """그 상품의 행 중 taskId > 워터마크 (워터마크 None 이면 전부)."""
    기준 = _숫자(워터마크) if 워터마크 else None
    out = []
    for tid, x in 행들.items():
        if str(x.get("productId") or "") != pid:
            continue
        n = _숫자(tid)
        if n is None:
            continue
        if 기준 is None or n > 기준:
            out.append(tid)
    return sorted(out, key=_숫자)


def _workdata(mcp, pid, 모드):
    r = _표시규칙제거(mcp.call_tool("bulsaja_product_workdata",
                                   {"productId": pid, "mode": 모드}))
    return _규약().워크데이터꺼내기(r, f" ({pid[-8:]} {모드})")


# ── 상품 판정 (D-02 재조회 · ⓐ 확인 · ⓑ 기록) ────────────────────────────────

def _원본읽기(폴더, pid):
    """ⓐ `<폴더>/<pid>.json` → (문서|None, 사유)."""
    try:
        경로 = Path(폴더) / f"{pid}.json"
        with open(경로, encoding="utf-8") as f:
            doc = json.load(f)
        rc = doc.get("renderContent") if isinstance(doc, dict) else None
        if not isinstance(rc, str) or not rc:
            return None, "renderContent 없음"
        return doc, ""
    except Exception as e:
        return None, f"{type(e).__name__}"


def _날짜(url):
    """`?t=<밀리초>` → YYYY-MM-DD. 못 읽으면 None."""
    try:
        if not isinstance(url, str) or "t=" not in url:
            return None
        값 = url.split("t=", 1)[1].split("&", 1)[0]
        return datetime.fromtimestamp(int(값) / 1000).astimezone().strftime("%Y-%m-%d")
    except Exception:
        return None


def _상품판정(mcp, it, 원본폴더, 반영전폴더, 계정, AI판정=True):
    """한 상품 → preview 문서 항목. 판정 = 반영가능|스킵|실패.

    순서: workdata summary → 미업로드 → ⓐ 원본(없으면 backup_failed, L-03)
          → AI 판정(OR 규칙, Pitfall 6 — 복원은 AI판정=False) → workdata full(상하단·그룹)
          → ⓑ 반영 직전 상태 기록(실패면 backup_failed).
    개별 오류는 그 항목만 격리하고 전체를 죽이지 않는다.
    """
    pid = it["productId"]
    a경로 = str(Path(원본폴더) / f"{pid}.json")
    결과 = {"productId": pid, "판매자상품코드": it.get("판매자상품코드", ""),
            "판정": "실패", "사유": "", "backup_a": a경로, "backup_a_있음": False,
            "backup_b": None, "채널상품번호": None, "상단이미지": None, "하단이미지": None,
            "상하단날짜": None, "마켓그룹": None, "미리보기요약": ""}
    try:
        data = _workdata(mcp, pid, "summary")
    except Exception as e:
        결과["사유"] = f"workdata 조회 실패: {str(e)[:120]}"
        return 결과
    ss = (data.get("uploadedSuccessUrl") or {}).get("smartstore")
    if not ss or not str(ss).strip():
        결과.update({"판정": "스킵", "사유": "미업로드: 스마트스토어 채널상품번호 없음"})
        return 결과
    결과["채널상품번호"] = str(ss).strip()
    원본, 왜 = _원본읽기(원본폴더, pid)
    if 원본 is None:
        결과.update({"판정": "스킵", "사유": f"backup_failed: 원본 복원 불가(ⓐ 없음 · {왜})"})
        return 결과
    결과["backup_a_있음"] = True
    dc = data.get("uploadDetailContents") or {}
    현재rc = dc.get("renderContent")
    if AI판정:
        달라짐 = isinstance(현재rc, str) and 현재rc != 원본["renderContent"]
        if not (불리언정규화(dc.get("aiImageGenerated")) or 달라짐):
            결과.update({"판정": "스킵",
                         "사유": f"AI상세없음: aiImageGenerated="
                                 f"{dc.get('aiImageGenerated')!r} · 상세가 원본과 같음"})
            return 결과
    try:
        full = _workdata(mcp, pid, "full")
        쪽 = full.get("uploadDetail_page") or {}
        결과["상단이미지"] = 쪽.get("top_image")
        결과["하단이미지"] = 쪽.get("bottom_image")
        결과["상하단날짜"] = _날짜(쪽.get("top_image")) or _날짜(쪽.get("bottom_image"))
        결과["마켓그룹"] = full.get("uploadSelectedMarketGroupId")
    except Exception as e:
        결과.update({"판정": "스킵",
                     "사유": f"backup_failed: workdata(full) 조회 실패 {str(e)[:100]}"})
        return 결과
    b경로 = Path(반영전폴더) / f"{pid}.json"
    try:
        _원자쓰기(b경로, {"productId": pid, "판매자상품코드": 결과["판매자상품코드"],
                          "조회시각": _지금(), "계정": 계정, "renderContent": 현재rc,
                          "imageTranslated": dc.get("imageTranslated"),
                          "상단이미지": 결과["상단이미지"], "하단이미지": 결과["하단이미지"],
                          "마켓그룹": 결과["마켓그룹"]})
    except Exception as e:
        결과.update({"판정": "스킵",
                     "사유": f"backup_failed: 반영 전 상태(ⓑ) 쓰기 실패 {type(e).__name__}"})
        return 결과
    결과.update({"판정": "반영가능", "backup_b": str(b경로)})
    return 결과


# ── 쓰기 도구 1차 호출 (confirm:false) 해석 ───────────────────────────────────

def _결과행(r, pid):
    """confirm 응답의 `결과[]` 에서 그 상품 행 (category_gate.delete_batch 해석 모양)."""
    for k in ("결과", "results", "items"):
        v = r.get(k) if isinstance(r, dict) else None
        if isinstance(v, list):
            for x in v:
                if isinstance(x, dict) and str(x.get("productId") or "") == pid:
                    return x
    return None


def _작업번호(r, pid):
    행 = _결과행(r, pid)
    if 행 and 행.get("taskId"):
        return str(행["taskId"])
    return extract_task_id(r) if isinstance(r, dict) else None


def _메시지(r):
    if not isinstance(r, dict):
        return str(r)[:150]
    for k in ("message", "메시지", "_text", "error", "사유"):
        v = r.get(k)
        if v:
            return str(v)[:150]
    return json.dumps(sanitize(r), ensure_ascii=False)[:150]


def _1차해석(pre, pid):
    """confirm:false 응답 → (토큰|None, 스킵사유). 토큰 없는 성공/작업번호 = 쓰기의심 예외.

    `option_update` 식 "확인 불필요 성공" 으로 **읽지 않는다** (RESEARCH Q1).
    """
    pre = pre if isinstance(pre, dict) else {}
    토큰 = pre.get("confirmationToken")
    if 토큰:
        return 토큰, ""
    if 불리언정규화(pre.get("success")) or _작업번호(pre, pid):
        raise 쓰기의심(json.dumps(sanitize(_토큰마스킹(pre)), ensure_ascii=False)[:300])
    msg = _메시지(pre)
    if "진행" in msg:
        return None, f"이미진행중: {msg}"
    return None, msg


def _미리보기요약(pre):
    r = {k: v for k, v in (pre or {}).items() if "token" not in str(k).lower()}
    return json.dumps(sanitize(r), ensure_ascii=False)[:200]


# ── 마무리 · 센티널 ──────────────────────────────────────────────────────────

def _센티널(a, f, s, p, t):
    print(f"###MARKET### 성공 {a} / 실패 {f} / 스킵 {s} / 대기 {p} / 전체 {t}", flush=True)


def _미리보기문서(args, 계정, 모드, 워터마크, 항목들, 중단=None):
    집계 = {"반영가능": sum(1 for x in 항목들 if x["판정"] == "반영가능"),
            "스킵": sum(1 for x in 항목들 if x["판정"] == "스킵"),
            "실패": sum(1 for x in 항목들 if x["판정"] == "실패"),
            "전체": len(항목들)}
    문서 = {"모드": "preview", "계정": 계정, "확인모드": 모드, "워터마크": 워터마크,
            "생성시각": _지금(), "items": 항목들, "집계": 집계}
    if 중단:
        문서["중단"] = 중단
    save_json(args.summary_out or (Path(args.run_dir) / "preview.json"), 문서)
    return 집계


def _미리보기(mcp, args, items, 계정, 모드):
    """쓰기 0 미리보기. **이 함수에는 confirm:true 를 부르는 코드가 없다** (L-02)."""
    try:
        행들, _ = _창읽기(mcp, ["기본"])
    except Exception as e:
        print(f"⛔ 작업창을 못 읽어 쓰기 0 을 사후 확인할 수 없다 — 미리보기 거부: {e}",
              flush=True)
        _센티널(0, 0, 0, 0, len(items))
        return EXIT_INPUT
    워터마크 = _워터마크(행들)
    print(f"미리보기 {len(items)}건 · 계정 {계정} · 확인모드 {모드} · 워터마크 "
          f"{_꼬리(워터마크)}", flush=True)
    항목들 = []

    def 중단(항목, 이유):
        print(f"⛔ 쓰기의심 — {이유} · 전량 중단", flush=True)
        항목.update({"판정": "실패", "사유": f"쓰기의심: {이유}"[:300]})
        집계 = _미리보기문서(args, 계정, 모드, 워터마크, 항목들, 중단=f"쓰기의심: {이유}"[:300])
        _센티널(집계["반영가능"], 집계["실패"], 집계["스킵"], 0, len(items))
        return EXIT_INPUT

    for i, it in enumerate(items, 1):
        pid = it["productId"]
        r = _상품판정(mcp, it, args.detail_backup_dir, args.backup_dir, 계정)
        항목들.append(r)
        if r["판정"] == "반영가능":
            try:
                pre = _표시규칙제거(mcp.call_tool(
                    TOOL_UPDATE, {"productIds": [pid], "market": MARKET,
                                  "confirm": False}) or {})
                토큰, 사유 = _1차해석(pre, pid)
                if 토큰:
                    r["미리보기요약"] = _미리보기요약(pre)
                else:
                    r.update({"판정": "스킵", "사유": 사유})
                토큰 = None           # 저장·재사용하지 않는다 (실행 잡이 새로 받는다)
            except 쓰기의심 as e:
                return 중단(r, f"토큰 없이 성공/작업번호 {e}")
            except Exception as e:
                msg = str(e)[:150]
                r.update({"판정": "스킵" if "진행" in msg else "실패",
                          "사유": f"이미진행중: {msg}" if "진행" in msg
                          else f"미리보기 호출 실패: {msg}"})
            # 매 건 사후 증명 — 그 상품의 새 행이 생겼으면 쓰기가 난 것이다
            try:
                사후, _ = _창읽기(mcp, ["기본", "PENDING", "PROCESSING"])
            except Exception as e:
                return 중단(r, f"사후 작업창 확인 불가 {str(e)[:120]}")
            새 = _새행들(사후, pid, 워터마크)
            if 새:
                return 중단(r, f"미리보기 뒤 작업창에 새 행 {[_꼬리(t) for t in 새]}")
        print(f"[{i}/{len(items)}] {pid[-8:]} {r['판정']}"
              f"{' — ' + r['사유'] if r['사유'] else ''}", flush=True)
        time.sleep(args.sleep)
    집계 = _미리보기문서(args, 계정, 모드, 워터마크, 항목들)
    _센티널(집계["반영가능"], 집계["실패"], 집계["스킵"], 0, len(items))
    return EXIT_OK


# ── 입력 · 진입점 ────────────────────────────────────────────────────────────

def _대상읽기(path):
    """--targets → items. 문제가 있으면 (None, 사유). 빈 값 ≠ 전량 — 폴백하지 않는다."""
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        return None, f"--targets 읽기 실패: {type(e).__name__}: {e}"
    if not isinstance(raw, dict) or not isinstance(raw.get("items"), list):
        return None, "--targets 에 items 리스트가 없다"
    if not raw["items"]:
        return None, "--targets items 가 비었다 (빈 값은 전량이 아니다)"
    items, 본 = [], set()
    for i, it in enumerate(raw["items"]):
        if not isinstance(it, dict) or not str(it.get("productId") or "").strip():
            return None, f"--targets items[{i}] 에 productId 가 없다"
        pid = str(it["productId"]).strip()
        if pid in 본:
            continue
        본.add(pid)
        items.append({"productId": pid,
                      "판매자상품코드": str(it.get("판매자상품코드") or "").strip()})
    return items, None


def _인자():
    ap = argparse.ArgumentParser(description="불사자 스마트스토어 수정업로드")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--expect-nick", required=True)
    모드 = ap.add_mutually_exclusive_group(required=True)
    모드.add_argument("--preview", action="store_true")
    모드.add_argument("--commit", action="store_true")
    모드.add_argument("--poll-only", action="store_true")
    모드.add_argument("--tasks-snapshot", metavar="OUT_JSON")
    ap.add_argument("--targets")
    ap.add_argument("--detail-backup-dir", help="ⓐ 원본 상세 백업 폴더 (before_detail)")
    ap.add_argument("--backup-dir", help="ⓑ 반영 직전 상태 폴더 (before_market)")
    ap.add_argument("--max-items", type=int)
    ap.add_argument("--summary-out")
    ap.add_argument("--poll-interval", type=float, default=20)
    ap.add_argument("--max-poll-min", type=float, default=30)
    ap.add_argument("--restore-backup", metavar="A_JSON",
                    help="ⓐ 원본 파일 — --preview|--commit 과 함께 복원 모드")
    ap.add_argument("--sleep", type=float, default=0.3)
    return ap


def _실행(args):
    """모드 분기. 입력 검증은 BulsajaMCP() 생성 **전에** 끝낸다."""
    복원 = bool(args.restore_backup)
    if 복원 or args.commit or args.poll_only or args.tasks_snapshot:
        # Task 1 시점: 쓰기 경로가 반쯤 열린 채 나가지 않게 거부한다
        print("⛔ 이 모드는 아직 준비되지 않았다", flush=True)
        return EXIT_INPUT
    items, 사유 = _대상읽기(args.targets) if args.targets else (None, "--targets 가 필요하다")
    if items is None:
        print(f"⛔ {사유}", flush=True)
        return EXIT_INPUT
    if not args.detail_backup_dir or not args.backup_dir:
        print("⛔ --detail-backup-dir(ⓐ) 와 --backup-dir(ⓑ) 가 필요하다 (L-03)", flush=True)
        return EXIT_INPUT
    Path(args.run_dir).mkdir(parents=True, exist_ok=True)
    mcp = BulsajaMCP()
    mcp.open()
    try:
        rc, 계정, 모드 = _연결과가드(mcp, args)
        if rc is not None:
            _센티널(0, 0, 0, 0, len(items))
            return rc
        return _미리보기(mcp, args, items, 계정, 모드)
    finally:
        mcp.close()


def main():
    args = _인자().parse_args()
    try:
        코드 = _실행(args)
    except SystemExit:
        raise
    except Exception as e:
        print(f"⛔ 예외: {type(e).__name__}: {str(e)[:300]}", flush=True)
        _센티널(0, 0, 0, 0, 0)
        코드 = EXIT_INPUT
    sys.exit(코드)


if __name__ == "__main__":
    main()
