# -*- coding: utf-8 -*-
"""불사자 AI 상세페이지 배치 생성 (기본 10장, 일반화질).

⚠️ 핵심 (2026-07-23 실측): 10장짜리 상세페이지가 되려면
   imageUrls(상품 이미지 목록, 최대 10장) + sectionCount(장수) 를 **동시에** 보내야 한다.
   - productId만 / sectionCount만 / imageUrls만 → 전부 1장짜리로 접수됨.
   - 접수 확정 응답의 '예상장수'로 즉시 검증하고, 불일치 시 전량 중단.

기작업 스킵 (2026-07-23): 접수 전 workdata의 uploadDetailContents에서
   aiImageGenerated / aiImageOutputCount / aiImageGeneratedAt 을 확인해
   이미 이번 목표 장수 이상으로 생성·반영된 상품은 접수하지 않는다 (크레딧 0).
   - 서버 기록이 진실의 원천 — 별도 로컬 대장 불필요 (썸네일과 다른 점).
   - 기존 장수 < 목표 장수(예: 1장 사고분)는 스킵하지 않고 재작업 대상.
   - 이미지 수집용 workdata 조회를 그대로 재사용하므로 추가 API 호출 없음.
   - 강제 재생성은 --force (용팀장님 명시 요청 시만).

상품별 흐름:
  workdata 조회 → 기작업 스킵 판정 → 이미지 수집(썸네일 + 옵션 이미지, 중복 제거,
  최대 --pages 장) → generate(confirm=False→토큰→confirm=True,
  imageUrls+sectionCount) 접수 → 응답 '예상장수' 검증 → 전체 폴링
  → 완료 시 불사자가 자동 반영.

- 체크포인트: <run-dir>/detail_status.json {pid: {taskId, status, pages, ...}}
- 재개: taskId 있는 상품은 접수 스킵, 미완료만 폴링 (--poll-only)
- 작업 중복(해당 상품에 AI 작업 진행 중): 대기열로 미뤘다가 말미에 재시도
- 크레딧: 일반화질 장당 5 / 고화질 장당 10 (성공분만 과금)

사용:
  python detail_batch.py --run-dir <RUN> [--pages 10] [--quality standard]
        [--limit N] [--submit-only] [--poll-only] [--retry-failed] [--force]
  불사자 MCP 항목이 하나뿐인 환경에서는 래퍼 없이 그대로 돌린다.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 불사자 MCP 클라이언트는 카테고리 교정 스킬의 것을 재사용.
# **경로를 박지 않는다** — 이 파일 위치에서 스킬 루트를 거슬러 올라가 찾는다.
# (같은 관용구: product-name/scripts/run_names.py:40-46)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILLS_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", ".."))
SKILL_SCRIPTS = os.path.join(SKILLS_DIR, "bulsaja-category-fix", "scripts")
sys.path.insert(0, SKILL_SCRIPTS)
from bulsaja_mcp import BulsajaMCP  # noqa: E402


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, obj):
    try:
        tmp = str(path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except Exception as e:
        print(f"[경고] 체크포인트 저장 실패: {e}")


def sanitize(obj, depth=0):
    """응답 구조 확인용 (값 축약, 토큰류 노출 방지)."""
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


def extract_status(r):
    """상태 응답에서 진행 상태 문자열 추출."""
    for k in ("status", "상태", "진행상태", "state"):
        v = r.get(k)
        if isinstance(v, str) and v:
            return v
    return json.dumps(sanitize(r), ensure_ascii=False)[:100]


def is_done(s):
    return any(w in s for w in ("완료", "성공", "complete", "done", "success"))


def is_failed(s):
    return any(w in s for w in ("실패", "오류", "취소", "fail", "error", "cancel"))


def is_duplicate_error(e):
    """해당 상품에 AI 작업이 이미 진행 중이라 접수가 막힌 경우."""
    s = str(e)
    return ("작업 중복" in s) or ("이미 AI 이미지 작업이 진행" in s)


SKIP_STATUS = "완료(기작업)"  # is_done 매칭되어 재접수·폴링 대상에서 빠짐


class AlreadyDone(Exception):
    """이미 목표 장수 이상으로 AI 상세페이지가 생성·반영된 상품."""

    def __init__(self, pages, at):
        self.pages = pages
        self.at = at or ""
        super().__init__(f"기작업 {pages}장 ({self.at[:10]})")


def get_workdata(mcp, pid):
    wd = mcp.call_tool("bulsaja_product_workdata",
                       {"productId": pid, "mode": "summary"})
    return wd.get("data") or {}


def existing_ai_detail(data):
    """이미 생성·반영된 AI 상세페이지 정보. 없으면 None.

    판별은 aiImageGenerated 플래그 기준 — '상세페이지있음'은 원본 번역
    이미지만 있어도 true 라서 기준이 못 됨 (2026-07-23 실측).
    """
    dc = data.get("uploadDetailContents") or {}
    if not dc.get("aiImageGenerated"):
        return None
    try:
        pages = int(dc.get("aiImageOutputCount") or 0)
    except (TypeError, ValueError):
        pages = 0
    return {"pages": pages, "at": dc.get("aiImageGeneratedAt") or ""}


def collect_images(data, cap):
    """workdata에서 상세페이지 입력 이미지 수집: 썸네일 + 옵션 이미지 (중복 제거, cap장)."""
    urls = []

    def add(u):
        if isinstance(u, str) and u.startswith("http") and u not in urls:
            urls.append(u)

    for u in (data.get("uploadThumbnails") or []):
        add(u)
    # 옵션(색상 등) 이미지 — 제외 처리된 옵션은 건너뜀
    try:
        props = data.get("uploadSkuProps") or {}
        main = props.get("mainOption") or {}
        for v in (main.get("values") or []):
            if not v.get("exclude"):
                add(v.get("imageUrl"))
    except Exception:
        pass
    return urls[:cap]


def submit_one(mcp, pid, pages, quality, force=False):
    """이미지 수집 → imageUrls+sectionCount 동시 지정 2단계 접수 → (작업번호, 장수) 반환.

    기작업(기존 장수 >= 이번 목표 장수)이면 AlreadyDone — 접수·크레딧 없음.
    접수 확정 응답의 '예상장수'가 요청 장수와 다르면 RuntimeError("장수 불일치").
    """
    data = get_workdata(mcp, pid)
    imgs = collect_images(data, pages)
    if not imgs:
        raise RuntimeError("입력 이미지 없음 (썸네일/옵션 이미지 0장)")
    sc = max(2, min(pages, len(imgs)))  # 장수 하한 2 (도구 제약)
    if not force:
        prev = existing_ai_detail(data)
        if prev and prev["pages"] >= sc:
            raise AlreadyDone(prev["pages"], prev["at"])
    base = {"productId": pid, "imageUrls": imgs, "sectionCount": sc,
            "quality": quality, "confirm": False}
    pre = mcp.call_tool("bulsaja_detail_page_generate", base)
    token = pre.get("confirmationToken")
    if not token:
        raise RuntimeError(f"확인토큰 없음: {str(sanitize(pre))[:150]}")
    fin = mcp.call_tool("bulsaja_detail_page_generate",
                        {**base, "confirm": True, "confirmationToken": token})
    tid = extract_task_id(fin)
    if not tid:
        raise RuntimeError(f"작업번호 없음: {str(sanitize(fin))[:200]}")
    # ⚠️ 즉시 검증: 서버가 접수한 예상 장수 확인 (2026-07-23 1장 사고 재발 방지)
    exp = fin.get("예상장수")
    if isinstance(exp, int) and exp != sc:
        raise RuntimeError(
            f"장수 불일치: 요청 {sc}장인데 서버 접수는 {exp}장 (작업 {tid}). "
            f"전량 접수 중단 — 접수 파라미터 확인 필요.")
    return tid, sc


# ════════════════════════════════════════════════════════════════════════════
# --inputs 모드 (05-01) — 웹앱이 argv 로 부르는 주입구
#
# ⚠️ 여기 아래 함수들은 **--inputs 를 줬을 때만** 탄다. 플래그 없는 실행은 위의
#    submit_one / main 본문을 그대로 타고, 그 동작은 골든 테스트
#    (webapp/tests/test_detail_cli.py::test_플래그없음_골든_불변) 가 한 글자 단위로 집행한다 (L-04).
#
# 종료코드: 0 전부 종결 · 2 입력 오류/장수 불일치 · 3 폴링 미완(실패 아님)
#           · 4 계정 불일치 · 5 견적(--max-credits) 초과
# ════════════════════════════════════════════════════════════════════════════

# main 이 `sys.exit(_입력모드(args))` 로 내보낸다 — 폴링미완이면 sys.exit(3).
EXIT_OK, EXIT_INPUT, EXIT_POLL, EXIT_NICK, EXIT_BUDGET = 0, 2, 3, 4, 5
TAG_BATCH = 50          # find_by_code 배치 크기 (bulsaja_scan 실측: 50코드 0.53초)

# 정본은 webapp/state.py 의 `불리언정규화` · `기작업여부` 다 (D-12).
# CLI 는 웹앱을 import 하지 않으므로 **복제**하고, 교차 테스트
# (test_detail_cli.py::test_기작업_규칙_일치) 가 두 벌의 일치를 집행한다.
_FALSY = {"0", "false", "no", "n", "", "none", "null"}


def 불리언정규화(v):
    """'0' '1' False 1 None 을 같은 규약으로 읽는다 — 문자열 '0' 은 파이썬에서 참이다.
    bool 분기가 int 분기보다 먼저여야 한다(bool 은 int 의 하위타입)."""
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    return str(v).strip().lower() not in _FALSY


def 기작업(태그, dc, done_tags):
    """이미 상세가 가공된 상품인가 — 태그 ∈ done_tags OR aiImageGenerated (D-12).

    **목표 장수와 무관한 절대조건이다.** 플래그 없는 경로의 `prev["pages"] >= sc` 는
    그대로 두고(L-04), inputs 모드만 이 규칙을 쓴다 — 8장 기작업 상품이 10장 목표로
    재접수돼 크레딧을 다시 내는 경로를 막는다.
    """
    t = (태그 or "").strip()
    if t and t in {str(x).strip() for x in (done_tags or ())}:
        return True
    dc = dc if isinstance(dc, dict) else {}
    return 불리언정규화(dc.get("aiImageGenerated"))


def 장수계산(n, cap=10):
    """D-10 — 장수 = max(2, min(n, cap)). 입력 이미지 2장 미만이면 None(입력부족)."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return None
    if n < 2:
        return None
    return max(2, min(n, cap))


def _표시규칙제거(obj):
    """불사자 응답의 모델 대상 지시문(`표시규칙`)을 버린 사본 (bulsaja_scan 과 같은 규칙).
    산출물(estimate/summary)에 남으면 나중에 LLM 에 먹일 때 프롬프트 인젝션이 된다."""
    if isinstance(obj, dict):
        return {k: _표시규칙제거(v) for k, v in obj.items() if k != "표시규칙"}
    if isinstance(obj, list):
        return [_표시규칙제거(v) for v in obj]
    return obj


def _지금():
    from datetime import datetime
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _입력읽기(path):
    """--inputs 파일 → items 리스트. 문제가 있으면 (None, 사유).

    T-05-01: 깨진 파일·items 누락·리스트 아님·productId 없는 항목 = 입력 오류.
    **products.json 이나 전량으로 폴백하지 않는다** (run_ads.py `--only-ads` 와 같은 규율).
    `제외` 키는 웹앱 표시용이라 읽지 않는다. imageUrls 는 순서 유지 중복 제거.
    """
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        return None, f"--inputs 읽기 실패: {type(e).__name__}: {e}"
    if not isinstance(raw, dict) or not isinstance(raw.get("items"), list):
        return None, "--inputs 에 items 리스트가 없다"
    items = []
    for i, it in enumerate(raw["items"]):
        if not isinstance(it, dict) or not str(it.get("productId") or "").strip():
            return None, f"--inputs items[{i}] 에 productId 가 없다"
        urls = []
        for u in (it.get("imageUrls") or []):
            if isinstance(u, str) and u.startswith("http") and u not in urls:
                urls.append(u)
        try:
            총수 = int(it.get("제품이미지총수", len(urls)))
        except (TypeError, ValueError):
            총수 = len(urls)
        try:
            잘림 = int(it.get("잘림") or 0)
        except (TypeError, ValueError):
            잘림 = 0
        items.append({"productId": str(it["productId"]).strip(),
                      "판매자상품코드": str(it.get("판매자상품코드") or "").strip(),
                      "imageUrls": urls, "제품이미지총수": 총수, "잘림": 잘림})
    return items, None


def _계정확인(mcp, 기대닉):
    """`bulsaja_my_profile` 1회 → (닉, 크레딧, 통과). bulsaja_scan.계정확인 관용구 (L-06).
    조회 자체가 실패하면 닉 None · 통과 False — 확인 못 한 계정으로 진행하지 않는다."""
    try:
        p = _표시규칙제거(mcp.call_tool("bulsaja_my_profile", {}) or {})
        닉 = str(p.get("닉네임") or "")
        크레딧 = str(p.get("크레딧") or "")
    except Exception as e:
        print(f"[경고] 계정 조회 실패: {str(e)[:120]}", flush=True)
        # 기대닉을 줬는데 확인을 못 했으면 불통과. 안 줬으면(견적 참고용 조회) 진행.
        return None, None, 기대닉 is None
    return 닉, 크레딧, (기대닉 is None or 닉 == str(기대닉))


def _태그조회(mcp, 코드들, done_tags):
    """판매자상품코드 → 그룹태그. 반환 (태그맵, 실패코드집합).

    CR-02 fail-closed: 조각 호출이 실패하거나 응답 모양이 아니면 그 조각 코드 전부
    '태그미조회' — **못 물어본 것을 "태그 없음" 으로 읽지 않는다** (접수 안 함).
    같은 코드로 사본이 여럿 오면 done_tags 에 걸리는 태그를 우선한다(스킵 쪽으로 기운다).
    응답 해석은 ss_index_calls.항목꺼내기 한 곳 — 플래그 없는 실행의 import 그래프를
    바꾸지 않으려고 여기서 지연 import 한다.
    """
    if SCRIPT_DIR not in sys.path:
        sys.path.insert(0, SCRIPT_DIR)
    from ss_index_calls import 항목꺼내기  # 지연 import (L-04)

    완료 = {str(t).strip() for t in (done_tags or ())}
    태그들, 실패 = {}, set()
    코드들 = [c for c in dict.fromkeys(코드들) if c]
    for i in range(0, len(코드들), TAG_BATCH):
        조각 = 코드들[i:i + TAG_BATCH]
        try:
            r = mcp.call_tool("bulsaja_product_find_by_code", {"codes": 조각})
            항목들 = 항목꺼내기(_표시규칙제거(r), 맥락=f" (코드 {len(조각)}건)")
        except Exception as e:
            print(f"[경고] 태그 조회 {len(조각)}건 실패 — 태그미조회 처리: "
                  f"{str(e)[:120]}", flush=True)
            실패.update(조각)
            continue
        for it in 항목들:
            코드 = str((it or {}).get("판매자상품코드") or "")
            if 코드 in 조각:
                태그들.setdefault(코드, []).append((it or {}).get("그룹"))
        time.sleep(0.3)
    태그맵 = {}
    for 코드, 목록 in 태그들.items():
        값들 = [str(t).strip() for t in 목록 if t and str(t).strip()]
        걸림 = [t for t in 값들 if t in 완료]
        태그맵[코드] = (걸림 or 값들 or [None])[0]
    return 태그맵, 실패


def _판정(mcp, item, 태그맵, 실패코드, done_tags, cap, per_credit):
    """한 항목 → {판정, 사유, 장수, 크레딧, imgs}. 판정 = 접수|기작업|태그미조회|입력부족.

    순서: 태그 못 물어봄(fail-closed) → workdata → 기작업 절대조건(D-12) → 입력부족 → 접수.
    개별 오류는 그 항목만 '태그미조회' + 사유로 격리하고 전체를 죽이지 않는다.
    """
    pid, 코드 = item["productId"], item["판매자상품코드"]
    결과 = {"판정": "태그미조회", "사유": "", "장수": 0, "크레딧": 0, "imgs": []}
    if not 코드:
        결과["사유"] = "판매자상품코드 없음 — 태그를 물어볼 수 없다"
        return 결과
    if 코드 in 실패코드:
        결과["사유"] = "태그 조회 실패 (fail-closed)"
        return 결과
    태그 = 태그맵.get(코드)
    try:
        data = get_workdata(mcp, pid)
    except Exception as e:
        결과["사유"] = f"workdata 조회 실패: {str(e)[:120]}"
        return 결과
    dc = data.get("uploadDetailContents") or {}
    if 기작업(태그, dc, done_tags):
        결과["판정"] = "기작업"
        t = (태그 or "").strip()
        if t and t in {str(x).strip() for x in done_tags}:
            결과["사유"] = f"태그 {t}"
        else:
            결과["사유"] = (f"aiImageGenerated={dc.get('aiImageGenerated')!r} "
                          f"({dc.get('aiImageOutputCount')}장, "
                          f"{str(dc.get('aiImageGeneratedAt') or '')[:10]})")
        return 결과
    imgs = item["imageUrls"]
    sc = 장수계산(len(imgs), cap)
    if sc is None:
        결과["판정"] = "입력부족"
        결과["사유"] = f"제품 이미지 {len(imgs)}장 (2장 미만)"
        return 결과
    # "dc" = 이미 받은 원본 상세 — --backup-out 이 추가 호출 없이 쓴다 (06-01 · D-03 ⓐ).
    # _견적 은 결과에서 키를 골라 담으므로 이 키가 estimate.json 에 새지 않는다.
    결과.update({"판정": "접수", "사유": "", "장수": sc,
                 "크레딧": sc * per_credit, "imgs": imgs[:sc], "dc": dc})
    return 결과


def _원본백업(폴더, it, dc, 계정):
    """AI 접수 직전 원본 불사자 상세를 `<폴더>/<productId>.json` 으로 남긴다 (06-01 · D-03 ⓐ).

    AI 생성은 완료 시 불사자 상세를 자동으로 덮는다 → 원본은 접수 순간에만 뜰 수 있다.
    반환 (성공, 사유). 실패면 호출부가 generate 를 부르지 않는다 (L-03).

    첫 기록이 원본 — 재시도·중복대기열 재접수가 AI 반영 뒤 값으로 덮는 사고 방지.
    그래서 이미 있으면 성공으로 치고 건드리지 않으며, 쓰기는 O_EXCL("x") 로 연다.
    """
    try:
        폴더 = Path(폴더)
        폴더.mkdir(parents=True, exist_ok=True)
        경로 = 폴더 / f"{it['productId']}.json"
        if 경로.exists():
            return True, "기존 원본 유지"
        rc = dc.get("renderContent") if isinstance(dc, dict) else None
        if not isinstance(rc, str) or len(rc) < 10:
            return False, "renderContent 없음"
        문서 = {"productId": it["productId"], "판매자상품코드": it["판매자상품코드"],
               "조회시각": _지금(), "계정": 계정, "renderContent": rc,
               "imageTranslated": dc.get("imageTranslated")}
        # 직렬화를 먼저 끝내 둔다 — 파일을 연 뒤 실패해 반쪽 파일이 "원본"으로 남지 않게
        본문 = json.dumps(문서, ensure_ascii=False, indent=1)
        try:
            with open(경로, "x", encoding="utf-8") as f:     # O_EXCL — 불덮음
                f.write(본문)
        except FileExistsError:
            # 여기서만 "이미 있음" 으로 친다 — 폴더 자리에 파일이 있어 mkdir 이 내는
            # FileExistsError 를 성공으로 삼키면 백업 없이 접수된다
            return True, "기존 원본 유지"
        return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"[:160]


def _견적(mcp, args, items, done_tags, per_credit, 계정, 잔액):
    """D-14 · DETAIL-05 — generate 를 **한 번도** 부르지 않는 견적. estimate.json 을 쓴다."""
    태그맵, 실패 = _태그조회(mcp, [it["판매자상품코드"] for it in items], done_tags)
    행들 = []
    for i, it in enumerate(items, 1):
        r = _판정(mcp, it, 태그맵, 실패, done_tags, args.pages, per_credit)
        행들.append({"productId": it["productId"], "판매자상품코드": it["판매자상품코드"],
                     "판정": r["판정"], "사유": r["사유"], "장수": r["장수"],
                     "제품이미지총수": it["제품이미지총수"], "잘림": it["잘림"],
                     "크레딧": r["크레딧"]})
        print(f"[{i}/{len(items)}] {it['productId'][-8:]} {r['판정']}"
              f"{' ' + str(r['장수']) + '장' if r['장수'] else ''}"
              f"{' — ' + r['사유'] if r['사유'] else ''}", flush=True)
        time.sleep(args.sleep)
    접수 = [h for h in 행들 if h["판정"] == "접수"]
    집계 = {"선택": len(행들), "스킵": len(행들) - len(접수), "접수": len(접수),
            "총장수": sum(h["장수"] for h in 접수),
            "예상크레딧": sum(h["크레딧"] for h in 접수),
            "잘린상품": sum(1 for h in 접수 if h["잘림"] > 0)}
    save_json(args.estimate_out, {"생성시각": _지금(), "계정": 계정, "잔액": 잔액,
                                  "per_credit": per_credit, "항목": 행들, "집계": 집계})
    print(f"###ESTIMATE### 선택 {집계['선택']} / 접수 {집계['접수']} / "
          f"스킵 {집계['스킵']} / 총장수 {집계['총장수']} / "
          f"예상크레딧 {집계['예상크레딧']} / 잘린상품 {집계['잘린상품']}", flush=True)
    return EXIT_OK


def _입력접수(mcp, pid, imgs, sc, quality):
    """2단계 접수 — submit_one 194-204 와 **같은 프로토콜**(imageUrls+sectionCount 동시,
    confirm False → 토큰 → confirm True). 반환 (taskId, 서버 예상장수 원값).

    submit_one 을 고치지 않고 따로 둔 이유: 예상장수 검증을 호출부로 넘겨야
    taskId 를 체크포인트에 **먼저** 적을 수 있다 (Pitfall 2). submit_one 은 검증 실패 시
    taskId 없이 예외를 던지고, 그 경로는 플래그 없는 실행이 그대로 쓴다 (L-04).
    """
    base = {"productId": pid, "imageUrls": imgs, "sectionCount": sc,
            "quality": quality, "confirm": False}
    pre = mcp.call_tool("bulsaja_detail_page_generate", base) or {}
    token = pre.get("confirmationToken")
    if not token:
        raise RuntimeError(f"확인토큰 없음: {str(sanitize(pre))[:150]}")
    fin = mcp.call_tool("bulsaja_detail_page_generate",
                        {**base, "confirm": True, "confirmationToken": token}) or {}
    tid = extract_task_id(fin)
    if not tid:
        raise RuntimeError(f"작업번호 없음: {str(sanitize(fin))[:200]}")
    return tid, fin.get("예상장수")


def _상태키(r):
    """폴링 응답의 status 문자열. 못 찾으면 None — extract_status 처럼 응답 JSON 을
    상태로 삼지 않는다 (Pitfall 6: 'error' 부분문자열 하나로 영구 실패가 되던 경로)."""
    if not isinstance(r, dict):
        return None
    for k in ("status", "상태", "진행상태", "state"):
        v = r.get(k)
        if isinstance(v, str) and v:
            return v
    return None


def _미종결(items, status):
    """taskId 가 있고 완료/실패/장수불일치가 아닌 pid — 폴링 종료 조건을 직접 센다 (Pitfall 1)."""
    남음 = []
    for it in items:
        v = status.get(it["productId"]) or {}
        st = v.get("status", "")
        if v.get("taskId") and st != "장수불일치" and not is_done(st) and not is_failed(st):
            남음.append(it["productId"])
    return 남음


def _요약상태(v):
    """체크포인트 한 항목 → summary 상태 (화면이 읽는 이름)."""
    v = v or {}
    st = v.get("status", "")
    if st == SKIP_STATUS:
        return "기작업스킵"
    if st in ("태그미조회", "입력부족", "장수불일치", "접수실패"):
        return st
    if v.get("taskId"):
        if is_done(st):
            return "완료"
        if is_failed(st):
            return "실패"
        return "폴링중"
    return "미접수"


def _마무리(args, items, status, per_credit, rc):
    """summary 저장 + 센티널 마지막 줄. 정상·2·3·5 모두 여기를 지난다."""
    행들 = []
    for it in items:
        v = status.get(it["productId"]) or {}
        상태 = _요약상태(v)
        try:
            장수 = int(v.get("pages") or 0)
        except (TypeError, ValueError):
            장수 = 0
        행들.append({"productId": it["productId"], "판매자상품코드": it["판매자상품코드"],
                     "상태": 상태, "장수": 장수,
                     "크레딧": 장수 * per_credit if v.get("taskId") else 0,
                     "사유": str(v.get("사유") or v.get("error") or ""),
                     "taskId": v.get("taskId")})
    셈 = {}
    for h in 행들:
        셈[h["상태"]] = 셈.get(h["상태"], 0) + 1
    집계 = {"접수": sum(1 for h in 행들 if h["taskId"]),
            "완료": 셈.get("완료", 0),
            "실패": 셈.get("실패", 0) + 셈.get("접수실패", 0) + 셈.get("장수불일치", 0),
            "스킵": 셈.get("기작업스킵", 0) + 셈.get("태그미조회", 0) + 셈.get("입력부족", 0),
            "폴링미완": 셈.get("폴링중", 0),
            "실제크레딧": sum(h["장수"] for h in 행들 if h["상태"] == "완료") * per_credit}
    if args.summary_out:
        save_json(args.summary_out, {"항목": 행들, "집계": 집계, "종료코드": rc})
    print(f"###DETAIL### 완료 {집계['완료']} / 실패 {집계['실패']} / 스킵 {집계['스킵']}"
          f" / 폴링미완 {집계['폴링미완']} / 전체 {len(items)}", flush=True)
    return rc


def _접수와폴링(mcp, args, items, done_tags, per_credit):
    """inputs 접수(+폴링) 또는 --poll-only 이어서 확인. 종료코드를 돌려준다.

    체크포인트는 같은 run-dir 의 detail_status.json 하나다 (D-16 · 정본은 불사자 서버,
    이 파일은 재개용). taskId 가 있는 건은 절대 다시 접수하지 않는다 (L-03 이중 지불).
    """
    run = Path(args.run_dir)
    run.mkdir(parents=True, exist_ok=True)
    status_path = run / "detail_status.json"
    status = load_json(status_path, {})

    # 1) 접수 — --poll-only 면 건너뛴다 (generate 금지)
    if not args.poll_only:
        def 필요(it):
            v = status.get(it["productId"]) or {}
            st = v.get("status", "")
            if st == "장수불일치":          # taskId 보유 — 재접수 = 이중 지불
                return False
            if args.retry_failed and (st == "접수실패" or (is_failed(st) and v.get("taskId"))):
                return True
            return not v.get("taskId") and not is_done(st)

        todo = [it for it in items if 필요(it)]
        print(f"접수 대상 {len(todo)}건 (상한 {args.max_credits}크레딧, "
              f"장당 {per_credit})", flush=True)
        태그맵, 실패코드 = ({}, set())
        if todo:
            태그맵, 실패코드 = _태그조회(mcp, [it["판매자상품코드"] for it in todo], done_tags)
        누적 = [0]

        def 시도(it, tag):
            pid = it["productId"]
            # D-12 — 접수 직전 실시간 판정 (견적 이후 생긴 기작업도 여기서 걸린다)
            r = _판정(mcp, it, 태그맵, 실패코드, done_tags, args.pages, per_credit)
            if r["판정"] != "접수":
                status[pid] = {"status": SKIP_STATUS if r["판정"] == "기작업" else r["판정"],
                               "사유": r["사유"], "pages": 0}
                print(f"{tag} {pid[-8:]} {r['판정']} — {r['사유']}", flush=True)
                return "skip"
            # D-14 — 늘어나는 방향이면 generate 전에 멈춘다
            if 누적[0] + r["크레딧"] > args.max_credits:
                print(f"⛔ {tag} {pid[-8:]} 접수하면 누적 {누적[0] + r['크레딧']}크레딧 > "
                      f"상한 {args.max_credits} — 여기서 멈춘다", flush=True)
                return "budget"
            # 06-01 · L-03 — 백업 없으면 generate 없음 (D-03). 원본은 지금만 뜰 수 있다
            if getattr(args, "backup_out", None):
                ok, why = _원본백업(Path(args.backup_out), it, r.get("dc") or {},
                                  getattr(args, "계정", None))
                if not ok:
                    status[pid] = {"status": "접수실패", "사유": f"backup_failed: {why}"}
                    save_json(status_path, status)
                    print(f"{tag} {pid[-8:]} 원본 백업 실패 — 접수 안 함 ({why})", flush=True)
                    return "fail"
            try:
                tid, exp = _입력접수(mcp, pid, r["imgs"], r["장수"], args.quality)
            except Exception as e:
                if is_duplicate_error(e):
                    print(f"{tag} {pid[-8:]} 작업 중복 — 말미 재시도", flush=True)
                    return "dup"
                status[pid] = {"status": "접수실패", "error": str(e)[:200]}
                print(f"{tag} {pid[-8:]} 접수 FAIL {str(e)[:100]}", flush=True)
                return "fail"
            # Pitfall 2 — taskId 를 **검증보다 먼저** 체크포인트에 남긴다
            sc = r["장수"]
            status[pid] = {"taskId": tid, "status": "접수", "pages": sc}
            save_json(status_path, status)
            누적[0] += r["크레딧"]
            # DETAIL-04 — 예상장수가 int 가 아니거나(문자열·누락·bool) 다르면 전량 중단
            if not (isinstance(exp, int) and not isinstance(exp, bool) and exp == sc):
                서버 = exp if isinstance(exp, (int, float, str, bool)) or exp is None \
                    else str(exp)[:40]
                status[pid].update({"status": "장수불일치", "요청장수": sc, "서버장수": 서버,
                                    "사유": f"요청 {sc}장 ≠ 서버 {서버!r}"})
                save_json(status_path, status)
                print(f"⛔ 장수 불일치: 요청 {sc}장인데 서버 접수는 {서버!r} (작업 {tid}). "
                      f"전량 접수 중단 — 접수 파라미터 확인 필요.", flush=True)
                return "mismatch"
            print(f"{tag} {pid[-8:]} 접수 OK ({tid}, {sc}장)", flush=True)
            return "ok"

        def 중단(결과):
            save_json(status_path, status)
            return _마무리(args, items, status, per_credit,
                           EXIT_BUDGET if 결과 == "budget" else EXIT_INPUT)

        dup_queue = []
        for i, it in enumerate(todo, 1):
            결과 = 시도(it, f"[{i}/{len(todo)}]")
            if 결과 in ("budget", "mismatch"):
                return 중단(결과)
            if 결과 == "dup":
                dup_queue.append(it)
            save_json(status_path, status)
            time.sleep(args.sleep)

        # 작업 중복 대기열 — 플래그 없는 경로와 같은 인자(--dup-wait/--dup-rounds)·같은 방식
        for rnd in range(args.dup_rounds):
            if not dup_queue:
                break
            print(f"중복 대기열 {len(dup_queue)}건 — {args.dup_wait}초 후 "
                  f"재시도 ({rnd + 1}/{args.dup_rounds})", flush=True)
            time.sleep(args.dup_wait)
            remain = []
            for it in dup_queue:
                결과 = 시도(it, "[중복재시도]")
                if 결과 in ("budget", "mismatch"):
                    return 중단(결과)
                if 결과 == "dup":
                    remain.append(it)
                save_json(status_path, status)
                time.sleep(args.sleep)
            dup_queue = remain
        for it in dup_queue:
            status[it["productId"]] = {"status": "접수실패",
                                       "error": "작업 중복 지속 (기존 작업 미종료)"}
        save_json(status_path, status)

    # 2) 폴링 — 종료 조건 = 미종결 0건 (Pitfall 1). 시간 상한 도달은 exit 3 (D-17)
    if not args.submit_only:
        deadline = time.time() + args.max_poll_min * 60
        while True:
            남음 = _미종결(items, status)
            if not 남음 or time.time() >= deadline:
                break
            print(f"폴링: 미완료 {len(남음)}건", flush=True)
            for pid in 남음:
                tid = status[pid]["taskId"]
                try:
                    st = mcp.call_tool("bulsaja_detail_page_status",
                                       {"taskId": tid, "target": "detail"})
                    s = _상태키(st)
                    if s is None:
                        # Pitfall 6 · D-18 — 서버가 확정한 실패만 실패. 오류 dict 는 상태 불변
                        status[pid]["poll_error"] = json.dumps(
                            sanitize(_표시규칙제거(st)), ensure_ascii=False)[:120]
                    else:
                        status[pid]["status"] = s
                        n = len((st or {}).get("생성이미지") or [])
                        if n:
                            status[pid]["images"] = n
                except Exception as e:
                    status[pid]["poll_error"] = str(e)[:120]
                time.sleep(0.4)
            save_json(status_path, status)
            남음 = _미종결(items, status)
            print(f"  미종결 {len(남음)} / 전체 {len(items)}", flush=True)
            if not 남음:
                break
            time.sleep(args.poll_interval)

    rc = EXIT_POLL if _미종결(items, status) else EXIT_OK
    return _마무리(args, items, status, per_credit, rc)


def _입력모드(args):
    """--inputs 진입점. 종료코드를 돌려준다 (main 이 sys.exit 한다)."""
    done_tags = [str(t).strip() for t in (args.done_tag or []) if str(t).strip()]
    if not done_tags:
        print("⛔ --inputs 모드는 --done-tag 가 최소 1개 필요하다 "
              "(비면 태그 기작업 판정이 죽어 크레딧을 다시 낸다)", flush=True)
        return EXIT_INPUT
    items, 사유 = _입력읽기(args.inputs)
    if items is None:
        print(f"⛔ {사유} — 전량 실행으로 폴백하지 않는다", flush=True)
        return EXIT_INPUT
    if args.estimate_only and not args.estimate_out:
        print("⛔ --estimate-only 는 --estimate-out 이 필요하다", flush=True)
        return EXIT_INPUT
    # T-05-05 — 상한 없는 접수 경로를 만들지 않는다. 이어서 확인(--poll-only)은 접수가 없어 예외
    if not args.estimate_only and not args.poll_only:
        if args.max_credits is None or args.max_credits < 0:
            print("⛔ --inputs 접수 모드는 --max-credits(0 이상)가 필요하다 (D-14)", flush=True)
            return EXIT_INPUT
    per_credit = 5 if args.quality == "standard" else 10

    mcp = BulsajaMCP()
    mcp.open()
    try:
        # L-06 — 계정 확인은 workdata·generate 보다 먼저. 불일치 = exit 4
        # (bulsaja_scan 은 3 이지만 여기서 3 은 폴링미완에 배정됐다)
        계정, 잔액 = None, None
        if args.expect_nick or args.estimate_only:
            계정, 잔액, 통과 = _계정확인(mcp, args.expect_nick)
            if not 통과:
                print(f"⛔ 붙어 있는 불사자 계정({계정})이 기대 계정"
                      f"({args.expect_nick})이 아니다 — 아무것도 조회·접수하지 않는다",
                      flush=True)
                return EXIT_NICK
        args.계정 = 계정      # 06-01 — 원본 백업 문서의 계정 값
        if args.estimate_only:
            return _견적(mcp, args, items, done_tags, per_credit, 계정, 잔액)
        return _접수와폴링(mcp, args, items, done_tags, per_credit)
    finally:
        mcp.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--pages", type=int, default=10,
                    help="상세페이지 장수 (기본 10, 허용 2~10)")
    ap.add_argument("--quality", default="standard",
                    choices=["standard", "high"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--submit-only", action="store_true")
    ap.add_argument("--poll-only", action="store_true")
    ap.add_argument("--retry-failed", action="store_true",
                    help="실패/접수실패 건을 다시 접수")
    ap.add_argument("--force", action="store_true",
                    help="기작업 스킵 무시하고 강제 재생성 (명시 요청 시만)")
    ap.add_argument("--poll-interval", type=int, default=45)
    ap.add_argument("--max-poll-min", type=int, default=240)
    ap.add_argument("--sleep", type=float, default=1.0)
    ap.add_argument("--dup-wait", type=int, default=60,
                    help="작업 중복 시 재시도 대기(초)")
    ap.add_argument("--dup-rounds", type=int, default=8,
                    help="작업 중복 재시도 최대 회수")
    # ── 05-01 주입구 (웹앱이 argv 로 부른다). 안 주면 위 동작 그대로 (L-04) ──
    ap.add_argument("--inputs",
                    help="대상 JSON {items:[{productId,판매자상품코드,imageUrls,...}]}. "
                         "주면 products.json·collect_images 를 쓰지 않는다 (D-08)")
    ap.add_argument("--done-tag", action="append",
                    help="기작업으로 칠 그룹태그 (반복 가능, inputs 모드 필수 — D-12)")
    ap.add_argument("--expect-nick",
                    help="기대 불사자 계정 닉네임. 다르면 exit 4 (L-06)")
    ap.add_argument("--estimate-only", action="store_true",
                    help="견적만: generate 0회, --estimate-out 에 저장 (D-14)")
    ap.add_argument("--estimate-out", help="견적 JSON 경로")
    ap.add_argument("--max-credits", type=int,
                    help="접수 누적 크레딧 상한. 넘기려 하면 generate 전 exit 5 "
                         "(inputs 접수 모드 필수)")
    ap.add_argument("--summary-out", help="접수/폴링 결과 요약 JSON 경로")
    ap.add_argument("--backup-out",
                    help="AI 접수 직전 원본 상세 백업 폴더 (MARKET-03 · D-03)")
    args = ap.parse_args()

    if not (2 <= args.pages <= 10):
        print("⛔ --pages 는 2~10 범위여야 함 (기본 10)")
        sys.exit(1)

    if args.inputs:
        sys.exit(_입력모드(args))

    run = Path(args.run_dir)
    status_path = run / "detail_status.json"
    raw = load_json(run / "products.json", [])
    pids = [p if isinstance(p, str) else p.get("productId")
            for p in raw]
    pids = [p for p in pids if p]
    status = load_json(status_path, {})
    per_credit = 5 if args.quality == "standard" else 10

    mcp = BulsajaMCP()
    mcp.open()
    try:
        # 1) 접수 (작업번호 없는 상품만; --retry-failed 면 실패 건도 재접수)
        if not args.poll_only:
            def need_submit(pid):
                v = status.get(pid, {})
                if args.force and v.get("status") == SKIP_STATUS:
                    return True
                if args.retry_failed and (is_failed(v.get("status", ""))
                                          or v.get("status") == "접수실패"):
                    return True
                return not v.get("taskId") and not is_done(v.get("status", ""))

            todo = [pid for pid in pids if need_submit(pid)]
            if args.limit:
                todo = todo[:args.limit]
            est = len(todo) * args.pages * per_credit
            print(f"접수 대상 {len(todo)}건 × 최대 {args.pages}장 "
                  f"× {per_credit}크레딧 = 예상 최대 {est}크레딧")

            dup_queue = []

            def try_submit(pid, tag):
                try:
                    tid, sc = submit_one(mcp, pid, args.pages, args.quality,
                                         force=args.force)
                    status[pid] = {"taskId": tid, "status": "접수", "pages": sc}
                    print(f"{tag} {pid[-8:]} 접수 OK ({tid}, {sc}장)",
                          flush=True)
                    return "ok"
                except AlreadyDone as e:
                    status[pid] = {"status": SKIP_STATUS, "pages": e.pages,
                                   "generated_at": e.at}
                    print(f"{tag} {pid[-8:]} 기작업 스킵 "
                          f"({e.pages}장, {e.at[:10]})", flush=True)
                    return "skip"
                except RuntimeError as e:
                    if "장수 불일치" in str(e):
                        print("⛔", str(e))
                        save_json(status_path, status)
                        sys.exit(2)
                    if is_duplicate_error(e):
                        print(f"{tag} {pid[-8:]} 작업 중복 — 말미 재시도",
                              flush=True)
                        return "dup"
                    status[pid] = {"status": "접수실패", "error": str(e)[:200]}
                    print(f"{tag} {pid[-8:]} 접수 FAIL {str(e)[:100]}",
                          flush=True)
                    return "fail"
                except Exception as e:
                    if is_duplicate_error(e):
                        print(f"{tag} {pid[-8:]} 작업 중복 — 말미 재시도",
                              flush=True)
                        return "dup"
                    status[pid] = {"status": "접수실패", "error": str(e)[:200]}
                    print(f"{tag} {pid[-8:]} 접수 FAIL {str(e)[:100]}",
                          flush=True)
                    return "fail"

            for i, pid in enumerate(todo, 1):
                r = try_submit(pid, f"[{i}/{len(todo)}]")
                if r == "dup":
                    dup_queue.append(pid)
                save_json(status_path, status)
                time.sleep(args.sleep)

            # 작업 중복 대기열: 기존 작업이 끝날 때까지 간격을 두고 재시도
            for rnd in range(args.dup_rounds):
                if not dup_queue:
                    break
                print(f"중복 대기열 {len(dup_queue)}건 — {args.dup_wait}초 후 "
                      f"재시도 ({rnd + 1}/{args.dup_rounds})", flush=True)
                time.sleep(args.dup_wait)
                remain = []
                for pid in dup_queue:
                    r = try_submit(pid, "[중복재시도]")
                    if r == "dup":
                        remain.append(pid)
                    save_json(status_path, status)
                    time.sleep(args.sleep)
                dup_queue = remain
            for pid in dup_queue:
                status[pid] = {"status": "접수실패",
                               "error": "작업 중복 지속 (기존 작업 미종료)"}
            save_json(status_path, status)

        # 2) 폴링 (완료/실패 아닌 작업번호 전부)
        if not args.submit_only:
            deadline = time.time() + args.max_poll_min * 60
            while time.time() < deadline:
                pending = [(pid, v["taskId"]) for pid, v in status.items()
                           if v.get("taskId") and not is_done(v.get("status", ""))
                           and not is_failed(v.get("status", ""))]
                if not pending:
                    break
                print(f"폴링: 미완료 {len(pending)}건", flush=True)
                for pid, tid in pending:
                    try:
                        st = mcp.call_tool("bulsaja_detail_page_status",
                                           {"taskId": tid, "target": "detail"})
                        status[pid]["status"] = extract_status(st)
                        n = len(st.get("생성이미지") or [])
                        if n:
                            status[pid]["images"] = n
                    except Exception as e:
                        status[pid]["poll_error"] = str(e)[:120]
                    time.sleep(0.4)
                save_json(status_path, status)
                done = sum(1 for v in status.values()
                           if is_done(v.get("status", "")))
                fail = sum(1 for v in status.values()
                           if is_failed(v.get("status", "")))
                print(f"  완료 {done} / 실패 {fail} / 전체 {len(status)}",
                      flush=True)
                if done + fail >= sum(1 for v in status.values()
                                      if v.get("taskId")):
                    break
                time.sleep(args.poll_interval)

        done = sum(1 for v in status.values() if is_done(v.get("status", "")))
        fail = sum(1 for v in status.values() if is_failed(v.get("status", "")))
        skip = sum(1 for v in status.values()
                   if v.get("status") == SKIP_STATUS)
        print(f"###DETAIL### 완료 {done} (신규 {done - skip} + 기작업스킵 {skip})"
              f" / 실패 {fail} / 전체 {len(status)}")
    finally:
        mcp.close()


if __name__ == "__main__":
    main()
