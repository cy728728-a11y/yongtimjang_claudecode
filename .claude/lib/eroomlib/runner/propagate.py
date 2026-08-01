#!/usr/bin/env python3
"""전파 러너 — 대표(기작업 완료)의 확정 결과를 그룹 간 중복 짝에게 이식한다.

**왜**: 같은 실물이 52개 마켓그룹에 걸쳐 여러 번 수집되면(같은 타오바오 상품번호·불사자
코드 공유), 대표 1건만 카테고리·상품명·옵션·썸네일을 마치도 나머지는 그대로 미착수로
남는다. 이 러너는 대표의 확정값을 짝에게 옮겨 붙인다 — **작업을 다시 하지 않는다.**

**Task 4** 가 `plan` 단계(시트·MCP 쓰기 0회)를 완주했다. **이 파일(Task 5)** 이 나머지를 채운다:
`apply`(검증 게이트 통과분만 실제 반영, `--commit` 없으면 dry-run) · `status`(run-dir 집계) ·
`retry-held`(00_보류함 승인 재적용) · 카테고리·옵션·썸네일의 `load_plan`/`verify`/`apply`.

정본 문서:
  - `00-system/04-specs/2026-08-01-중복상품-처리-인계.md` §5 (타깃 판정 정책)
  - `00-system/04-specs/2026-07-28-불사자-대량다듬기-design.md` §전파 계약
  - `00-system/04-specs/2026-07-29-불사자-대량다듬기-plan-m3m5.md` Task 5 Step 3

CLI:
    python .claude/lib/eroomlib/runner/propagate.py plan
    python .claude/lib/eroomlib/runner/propagate.py apply --run-dir <R> [--task 카테고리] [--commit]
    python .claude/lib/eroomlib/runner/propagate.py status --run-dir <R>
    python .claude/lib/eroomlib/runner/propagate.py retry-held --run-dir <R> [--commit]
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from eroomlib import dedup, gsheets, matrix, snapshot  # noqa: E402
from eroomlib.config import cfg  # noqa: E402
from eroomlib.runner import approval_log  # noqa: E402

_ROOT_OVERRIDE = None  # 테스트가 갈아끼운다 (inventory.py 와 같은 관례)


def _root():
    return _ROOT_OVERRIDE or cfg("paths.dedup_root", required=True)


def _inventory_dir():
    return os.path.join(_root(), "inventory")


def _claude_dir():
    """`.claude` 앵커 경로 — 이 파일은 이미 `.claude/lib/eroomlib/runner/` 안에 있다."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _skill_scripts_dir(skill_name):
    return os.path.join(_claude_dir(), "skills", skill_name, "scripts")


# ---------------------------------------------------------------------------
# 타깃 판정 — 짝 pid 의 현황판 해당 작업 열 값 → 3분류 (순수 함수, 시트 무관)
# ---------------------------------------------------------------------------

TARGET_TRANSPLANT = "이식"
TARGET_HELD = "보류함"
TARGET_SKIP = "스킵"

# 자동화가 스스로 막혀 조회를 포기한 값들 — literal 로 아는 것만. "보류(" 로 시작하는
# 값은 뒤의 startswith 체크가 잡으므로 여기엔 괄호 없는 것만 둔다.
_AUTO_HELD_LITERALS = {"매칭불가", "sellha조회실패", "부분일치확인요"}


def classify_matrix_value(value):
    """짝 pid 의 현황판 해당 작업 열 값 → (판정, 사유).

    표(이룸님 확정, 2026-08-01)를 그대로 코드화한다 — 순서가 표의 행 순서와 같다.
    미분류 문자열은 조용히 버리지 않고 `보류함` + 원문을 실은 사유로 남긴다.
    """
    v = (value or "").strip()
    if not v or matrix.is_redo(v):
        return TARGET_TRANSPLANT, ""
    if v.startswith("보류(") or v in _AUTO_HELD_LITERALS:
        return TARGET_TRANSPLANT, ""
    if v == "승인보류":
        return TARGET_HELD, "승인보류-수동승인필요"
    if v == "진행중(미반영)":
        return TARGET_HELD, "미결-상품명A열충돌"
    if v in (matrix.DONE, matrix.NA):
        return TARGET_SKIP, ""
    return TARGET_HELD, f"미분류값:{v}"


# ---------------------------------------------------------------------------
# PropagateMCP — 확인키 2단계(preview→token→commit) 공용 헬퍼.
# run_options.py option_update / bulsaja_mcp.py category_preview·commit / run_thumbs.py
# update_thumbnails 가 각자 반복하던 패턴(2026-07-28~30)을 도구명 인자화로 일반화한다.
# ---------------------------------------------------------------------------

def _strip_falsy(payload):
    """None·빈 리스트·빈 문자열 키를 제거한다 — run_options.py OptionMCP.option_update
    (97~98줄)의 `payload.update({k: v for k, v in kw.items() if v not in (None, [], "")})`
    와 동일 규칙. 이게 없으면 "포함만 바꾸고 제외는 그대로" 같은 부분 갱신에서
    `includeSkuIds: []`/`mainSkuId: None` 을 그대로 실어 보내 서버가 "전부 제외"·
    "대표 해제"로 해석할 위험이 있다(피어리뷰 Critical #1)."""
    return {k: v for k, v in payload.items() if v not in (None, [], "")}


class PropagateMCP(snapshot.ProductMCP):
    """transport(eroomlib.bulsaja) + 확인키 2단계 공용 호출. 상품 조회는 ProductMCP 상속."""

    def _confirmed_call(self, tool, payload):
        """미리보기 → confirmationToken 수취 → confirm=True 로 재호출해 커밋.

        `run_options.py OptionMCP.option_update`(79~110줄)를 그대로 일반화한다 —
        **첫 호출에는 `confirm` 을 아예 싣지 않는다**(서버 기본값에 맡긴다. 피어리뷰
        Important #1 — 이전 버전은 `confirm: False` 를 명시했는데, 검증된 레퍼런스와
        다른 가정이라 되돌렸다). payload 는 falsy 키를 제거한 뒤(위 `_strip_falsy`)
        두 호출 모두에 재사용한다(레퍼런스와 동일하게 한 번만 필터링).
        토큰이 없는데 success 면 "확인 없이 바로 처리됨"(변경 없음 등)으로 보고 그대로 반환.
        토큰도 success 도 없으면 예외. 커밋 응답이 success:false 면 예외.
        """
        payload = _strip_falsy(payload)
        pv = self.call_tool(tool, payload)
        token = pv.get("confirmationToken")
        if not token:
            if pv.get("success"):
                return pv
            raise RuntimeError(f"확인키 미발급({tool}): {str(pv.get('message'))[:200]}")
        r = self.call_tool(tool, {**payload, "confirm": True, "confirmationToken": token})
        if not r.get("success"):
            raise RuntimeError(f"저장 실패({tool}): {str(r.get('message'))[:200]}")
        return r


def _norm_cat_path(p):
    """카테고리 경로 정규화 — '>' 둘레 공백 제거(bulsaja_mcp._norm_path 와 동일 규칙)."""
    if not p:
        return ""
    return ">".join(seg.strip() for seg in str(p).split(">"))


def _option_fingerprint(option):
    """옵션.차원 → 지문 — (원문이름, vid 튜플, _name 튜플) 을 차원 순서 그대로.

    대표/타깃 옵션 구조가 같은지 보는 유일한 근거(전파 계약 §옵션). 다르면 사람이 수동으로
    옵션을 고친 것이라 침묵 덮어쓰기 금지 — 보류로 보낸다.
    """
    dims = (option or {}).get("차원") or []
    out = []
    for d in dims:
        values = d.get("values") or []
        out.append((
            d.get("원문이름") or "",
            tuple(v.get("vid") for v in values),
            tuple(v.get("_name") or "" for v in values),
        ))
    return tuple(out)


def _fp_norm(fp):
    """지문 비교용 정규화 — plan.json 을 거치면(JSON 왕복) list, 직접 주입이면 tuple 이라
    둘 다 같은 형태(list of [원문이름, [vid...], [_name...]])로 맞춰야 비교가 안전하다."""
    return [[d[0], list(d[1]), list(d[2])] for d in (fp or [])]


# ---------------------------------------------------------------------------
# load_plan — 대표의 확정값을 회수한다. 4작업 전부 실구현(Task 5).
# ---------------------------------------------------------------------------

def _default_read_tab(sheet_id, tab):
    from eroomlib.gsheets import sheets_get
    return sheets_get(sheet_id, f"'{tab}'!A1:AZ")


def load_plan_상품명(rep_pid, rep_group_name, deps):
    """대표가 속한 그룹 시트의 상품명 탭에서 대표 pid 의 **마지막(최신) 반영완료** 행 →
    (확정값, 메모). 확정값 = {"새상품명": str, "키워드": [str, ...]} 또는 None.

    시트 접근·그룹 인덱스는 deps 로 주입 가능(테스트가 실제 시트 없이 검증하려고).
    키워드 열은 F열·G~U열처럼 위치를 고정하지 않고 **탭 헤더로** 찾는다 — 그룹마다
    키워드 열 개수가 다를 수 있어(MAX_KW_COLS 확장 이력) 위치 가정이 위험하다.
    """
    index_groups = deps.get("index_groups") or matrix.index_groups
    read_tab = deps.get("read_tab") or _default_read_tab

    sheets = dict(index_groups())
    sid = sheets.get(rep_group_name)
    if not sid:
        return None, f"시트없음:{rep_group_name}"

    rows = None
    for tab in matrix.NAME_TABS:
        try:
            r = read_tab(sid, tab)
        except Exception:  # noqa: BLE001 — 탭 하나 실패가 다음 후보 탐색을 막으면 안 됨
            r = None
        if r:
            rows = r
            break
    if not rows:
        return None, "상품명탭없음"

    header = [str(c).strip() for c in rows[0]]
    try:
        i_id = header.index("상품id")
        i_status = header.index("상태")
        i_new = header.index("새상품명")
    except ValueError:
        return None, "헤더불일치"
    # "키워드1".."키워드5" 만 (키워드1_상품수·키워드1_검색량 파생열은 제외).
    kw_names = [h for h in header if h.startswith("키워드") and h[len("키워드"):].isdigit()]

    found = None
    for r in rows[1:]:
        row = list(r) + [""] * (len(header) - len(r))
        if str(row[i_id]).strip() != rep_pid:
            continue
        if str(row[i_status]).strip() != "반영완료":
            continue
        found = row  # 뒤에서 덮어써 마지막(최신) 매치가 남는다
    if found is None:
        return None, "반영완료행없음"

    새상품명 = str(found[i_new]).strip()
    if not 새상품명:
        return None, "새상품명빈값"
    키워드 = [str(found[header.index(k)]).strip() for k in kw_names]
    키워드 = [k for k in 키워드 if k]
    return {"새상품명": 새상품명, "키워드": 키워드}, None


# 카테고리교정 원장 탭 — run_names.py CATFIX_TAB 과 같은 상수(bulsaja-category-fix SKILL.md
# §시트 스키마: A상품id·E검색어(사용)·G상태).
CATFIX_TAB = "시트1"
# 썸네일 스킬 원장 탭 — run_thumbs.py TAB 과 같은 상수(F열 생성본 URL).
THUMB_TAB = "썸네일"


def load_plan_카테고리(rep_pid, rep_group_name, deps):
    """대표 스냅샷의 `기존카테고리`(확정 경로) + 카테고리교정 원장(시트1)의 확정 keyword.

    확정 경로가 없거나(카테고리 미설정), 원장에서 저장 완료류(matrix.CATFIX_DONE) 행을
    못 찾거나, keyword 가 비어 있으면 확정값 없음 = 보류(브리핑 §만들 것 지시).
    """
    load_snapshot = deps.get("load_snapshot") or snapshot.load
    index_groups = deps.get("index_groups") or matrix.index_groups
    read_tab = deps.get("read_tab") or _default_read_tab

    rep_snap = load_snapshot(rep_pid) or {}
    경로 = (rep_snap.get("기존카테고리") or "").strip()
    if not 경로 or 경로 == "미설정":
        return None, "확정경로없음"

    sheets = dict(index_groups())
    sid = sheets.get(rep_group_name)
    if not sid:
        return None, f"시트없음:{rep_group_name}"
    try:
        rows = read_tab(sid, CATFIX_TAB)
    except Exception:  # noqa: BLE001 — 원장 조회 실패는 확정값 없음으로 처리
        rows = None
    if not rows:
        return None, "카테고리원장없음"

    header = [str(c).strip() for c in rows[0]]
    try:
        i_id = header.index("상품id")
        i_kw = header.index("검색어(사용)")
        i_status = header.index("상태")
    except ValueError:
        return None, "헤더불일치"

    found = None
    for r in rows[1:]:
        row = list(r) + [""] * (len(header) - len(r))
        if str(row[i_id]).strip() != rep_pid:
            continue
        if str(row[i_status]).strip() not in matrix.CATFIX_DONE:
            continue
        found = row  # 마지막(최신) 매치가 남는다 — load_plan_상품명 과 같은 관례
    if found is None:
        return None, "확정행없음"

    keyword = str(found[i_kw]).strip()
    if not keyword:
        return None, "확정keyword없음"
    return {"경로": 경로, "keyword": keyword}, None


def load_plan_옵션(rep_pid, rep_group_name, deps):
    """대표 옵션정리 run 의 plans.json(`apply --emit` 산출물) 항목 + 대표 스냅샷 지문.

    ⚠ 설계 문서·브리핑 어디에도 "rep_pid → 소스 run-dir" 를 자동으로 찾는 레지스트리
    경로 규약이 없다(Task 5 report §concerns 참조). `deps["find_option_plan"]`
    (callable: rep_pid -> (plan_entry, 사유))을 주입하지 않으면 확정값 없음으로 보류한다 —
    실전 배선(실제 run-dir 탐색)은 이 주입점을 채우는 것으로 확장 가능하다.
    """
    find_option_plan = deps.get("find_option_plan")
    load_snapshot = deps.get("load_snapshot") or snapshot.load
    if not find_option_plan:
        return None, "옵션런디렉토리규약미정"
    plan_entry, reason = find_option_plan(rep_pid)
    if not plan_entry:
        return None, reason or "옵션계획없음"
    rep_snap = load_snapshot(rep_pid) or {}
    rep_option = rep_snap.get("옵션") or {}
    if not rep_option:
        return None, "대표스냅샷옵션없음"
    return {"plan": plan_entry, "지문": _option_fingerprint(rep_option)}, None


def load_plan_썸네일(rep_pid, rep_group_name, deps):
    """대표 소속 그룹 시트 `썸네일` 탭 F열(생성본) — http 로 시작하는 마지막(최신) 값."""
    index_groups = deps.get("index_groups") or matrix.index_groups
    read_tab = deps.get("read_tab") or _default_read_tab

    sheets = dict(index_groups())
    sid = sheets.get(rep_group_name)
    if not sid:
        return None, f"시트없음:{rep_group_name}"
    try:
        rows = read_tab(sid, THUMB_TAB)
    except Exception:  # noqa: BLE001
        rows = None
    if not rows:
        return None, "썸네일탭없음"

    header = [str(c).strip() for c in rows[0]]
    try:
        i_id = header.index("상품id")
        i_url = header.index("생성본")
    except ValueError:
        return None, "헤더불일치"

    found = ""
    for r in rows[1:]:
        row = list(r) + [""] * (len(header) - len(r))
        if str(row[i_id]).strip() != rep_pid:
            continue
        url = str(row[i_url]).strip()
        if url.startswith("http"):
            found = url  # 마지막(최신) 매치
    if not found:
        return None, "생성본URL없음"
    return {"url": found}, None


# ---------------------------------------------------------------------------
# verify/apply — 작업별 전파 계약(설계 §전파 계약이 정본). verify 는 preview(읽기)만,
# 실제 반영(commit)은 apply 가 한다. verify 결과: (VERIFY_OK|VERIFY_SKIP|VERIFY_HELD, 사유, extra)
# ---------------------------------------------------------------------------

VERIFY_OK = "검증통과"
VERIFY_SKIP = "스킵"
VERIFY_HELD = "보류"


def verify_카테고리(pid, plan_value, target, ctx):
    """대표 확정 keyword 로 preview → 지정될 경로가 대표 확정 경로와 일치할 때만 통과."""
    if not plan_value or not plan_value.get("keyword") or not plan_value.get("경로"):
        return VERIFY_HELD, "대표확정값없음", {}
    target_path = _norm_cat_path(plan_value["경로"])
    snap = ctx["snapshot_load"](pid) or {}
    cur_path = _norm_cat_path(snap.get("기존카테고리") or "")
    if cur_path and cur_path == target_path:
        return VERIFY_SKIP, "이미확정경로", {}
    pv = ctx["mcp"].call_tool("bulsaja_product_category",
                              {"productId": pid, "keyword": plan_value["keyword"], "confirm": False})
    token = pv.get("confirmationToken")
    got = _norm_cat_path(((pv.get("지정될카테고리") or {}).get("ss_category") or {}).get("name") or "")
    if not token or got != target_path:
        return VERIFY_HELD, "증거불일치", {}
    return VERIFY_OK, "", {"token": token}


def apply_카테고리(pid, plan_value, extra, target, ctx, **kw):
    r = ctx["mcp"].call_tool("bulsaja_product_category",
                             {"productId": pid, "keyword": plan_value["keyword"],
                              "confirm": True, "confirmationToken": extra["token"]})
    if not r.get("success"):
        raise RuntimeError(f"카테고리 저장 실패: {str(r.get('message'))[:200]}")
    ctx["snapshot_update"](pid, 기존카테고리=plan_value["경로"])


def verify_옵션(pid, plan_value, target, ctx):
    """타깃 스냅샷 옵션.차원 지문이 대표 지문과 동일할 때만 통과 — 다르면 수동 수정본이라 보류."""
    if not plan_value or not plan_value.get("plan") or not plan_value.get("지문"):
        return VERIFY_HELD, "대표옵션계획없음", {}
    snap = ctx["snapshot_load"](pid) or {}
    tgt_option = snap.get("옵션") or {}
    if not tgt_option:
        return VERIFY_HELD, "타깃스냅샷옵션없음", {}
    if _fp_norm(_option_fingerprint(tgt_option)) != _fp_norm(plan_value["지문"]):
        return VERIFY_HELD, "지문불일치", {}
    return VERIFY_OK, "", {"target_option": tgt_option}


def _option_rules_module():
    d = _skill_scripts_dir("bulsaja-option-cleanup")
    if d not in sys.path:
        sys.path.insert(0, d)
    import option_rules
    return option_rules


def apply_옵션(pid, plan_value, extra, target, ctx, **kw):
    """대표 plans.json 항목을 타깃에 재생. 이름변경·순서(포함/제외/대표)는 별도 호출
    (run_options.py 의 "이름과 순서를 같은 호출에 넣지 않는다" 제약 준수).

    **부분실패 재시도 방어(피어리뷰 Important #3)**: 두 호출은 원자적이지 않다 — 이름변경이
    성공한 뒤 포함/제외 호출이 실패하면 예외가 올라가 이 타깃은 `보류`로 기록되지만, 서버
    상태는 이미 절반 바뀐 채다. 재시도 시 이름변경을 무조건 다시 보내면(멱등이라 무해하긴
    하지만) 그 사이 다른 경로로 이름이 또 바뀌었을 가능성을 못 본다. 그래서 이름변경 전에
    **서버 현재 상태를 다시 조회**해 이미 목표 이름인 항목은 `pending`에서 뺀다 —
    완전히 반영됐으면 이름변경 호출 자체를 건너뛴다.
    """
    entry = plan_value["plan"]
    tgt_option = extra["target_option"]
    changes = {c["키"]: c["교정"] for c in (entry.get("이름변경") or []) if c.get("변경")}
    if changes:
        R = _option_rules_module()
        fresh_now = ctx["mcp"].workdata(pid).get("옵션") or tgt_option
        cur_names = R.value_names(fresh_now)
        pending = {k: v for k, v in changes.items()
                  if str(cur_names.get(str(k), "")).strip() != str(v).strip()}
        if pending:
            items, missing = R.rename_targets(tgt_option, pending)
            if missing:
                raise RuntimeError(f"옵션명 위치를 못 찾았다: {missing[:5]}")
            if items:
                ctx["mcp"]._confirmed_call("bulsaja_option_update",
                                           {"productId": pid, "renameValues": items})
    keep = [row["id"] for row in (entry.get("순서상세") or [])]
    drop = [row["id"] for row in (entry.get("제외상세") or [])]
    main_id = entry.get("대표") or None
    # includeSkuIds:[] / mainSkuId:None 처럼 falsy 값은 `_confirmed_call` 안에서
    # `_strip_falsy` 가 제거한다(Critical #1) — 여기서는 "보낼 게 하나라도 있는가"만 본다.
    if keep or drop or main_id:
        ctx["mcp"]._confirmed_call("bulsaja_option_update",
                                   {"productId": pid, "includeSkuIds": keep,
                                    "excludeSkuIds": drop, "mainSkuId": main_id,
                                    "skuOrder": keep})
    fresh = ctx["mcp"].workdata(pid).get("옵션") or {}
    ctx["snapshot_update"](pid, 옵션=fresh)
    # 사후 verify(R.verify(before,after,plan), run_options.py:625-628) 는 의도적으로
    # 아직 안 붙였다(피어리뷰 Minor, "cheap하면") — R.verify 는 "판매행"·"기준가"·
    # "대표값키" 가 갖춰진 정상 케이스를 가정하는데, 전파의 plan_value 는 그 필드들이
    # 없거나(케이스에 따라) 대표가 0개인 "제외만" 계획(Critical #1 재현 케이스)처럼
    # R.verify 의 "대표 정확히 1개" 전제와 충돌하는 입력도 다뤄야 한다. 제대로 붙이려면
    # plan.json 스키마 확장(기준가·대표값키 보존) + 테스트 픽스처 전면 재작업이 필요해
    # 이번 라운드 범위를 벗어난다고 판단했다 — Task 5 report 참조.


def verify_썸네일(pid, plan_value, target, ctx):
    """대표 생성본 URL 존재 확인 — 타깃 현재 대표이미지가 이미 그 URL이면 스킵(멱등)."""
    url = (plan_value or {}).get("url") or ""
    if not url.startswith("http"):
        return VERIFY_HELD, "생성본URL없음", {}
    snap = ctx["snapshot_load"](pid) or {}
    cur = (snap.get("썸네일") or [""])[0] or ""
    if cur == url:
        return VERIFY_SKIP, "이미동일URL", {}
    return VERIFY_OK, "", {}


def apply_썸네일(pid, plan_value, extra, target, ctx, **kw):
    """`bulsaja_thumbnail_update`의 `thumbnails`는 **대표 1장이 아니라 전체 갤러리 교체
    계약**이다(run_thumbs.py `update_thumbnails`, 120~134줄 — `thumbnails[0]`이 대표가
    되고 리스트 전체가 저장된 갤러리를 이룬다). `[url]`만 보내면 타깃이 원래 갖고 있던
    나머지 후보 이미지가 통째로 잘려나간다(피어리뷰 Important #3) — 대표를 앞으로,
    기존 갤러리(같은 URL·빈 값 제외)를 뒤에 이어붙여 전체를 보존한다.
    """
    url = plan_value["url"]
    snap = ctx["snapshot_load"](pid) or {}
    gallery = [url] + [t for t in (snap.get("썸네일") or []) if t and t != url]
    ctx["mcp"]._confirmed_call("bulsaja_thumbnail_update", {"productId": pid, "thumbnails": gallery})
    ctx["snapshot_update"](pid, 썸네일=gallery)


def verify_상품명(pid, plan_value, target, ctx):
    """대표 확정값 존재 + 타깃 소속 시트 확인."""
    if not plan_value or not (plan_value.get("새상품명") or "").strip():
        return VERIFY_HELD, "대표확정값없음", {}
    sid = ctx["sheets_map"].get(target.get("그룹명", ""))
    if not sid:
        return VERIFY_HELD, f"시트없음:{target.get('그룹명', '')}", {}
    return VERIFY_OK, "", {"target_sheet": sid}


def propagated_name(확정값, code, group_id, rep_group_id):
    """상품명 확정값 → (셔플된 새 이름, 키워드 목록).

    대표가 속한 그룹(group_id == rep_group_id)이면 shuffle_name 계약대로 항등(원문 그대로).
    """
    name = (확정값 or {}).get("새상품명", "")
    keywords = list((확정값 or {}).get("키워드") or [])
    return dedup.shuffle_name(name, keywords, code, group_id, rep_group_id=rep_group_id), keywords


def _name_header_module():
    d = _skill_scripts_dir("product-name")
    if d not in sys.path:
        sys.path.insert(0, d)
    import run_names
    return run_names


def _build_name_row(header, pid, orig_name, new_name, keywords, group_name, code, rep_pid):
    """상품명 탭 1행 — 헤더 위치를 이름으로 찾는다(열 순서 드리프트에 안전)."""
    row = [""] * len(header)

    def _set(col, val):
        if col in header:
            row[header.index(col)] = val

    _set("상품id", pid)
    _set("작업일", date.today().isoformat())
    _set("마켓그룹", group_name)
    _set("원본상품명", orig_name)
    _set("새상품명", new_name)
    for i, kw in enumerate(keywords[:5], 1):
        _set(f"키워드{i}", kw)
    _set("상태", "생성완료")
    _set("메모", f"전파({code},{rep_pid})")
    return row


_RENAME_COUNTS_RE = re.compile(r"###RENAME###\s*반영\s*(\d+)건\s*/\s*불량\s*(\d+)건\s*/\s*오류\s*(\d+)건")


def _parse_rename_counts(stdout):
    """`###RENAME### 반영 N건 / 불량 M건 / 오류 K건` 파싱 → (반영,불량,오류) 정수 3개.

    못 찾으면 (None, None, None) — 옛 버전 출력이나 형식이 바뀐 경우 침묵 판단하지 않는다.
    """
    m = _RENAME_COUNTS_RE.search(stdout or "")
    if not m:
        return None, None, None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def _default_rename_runner(sheet, tab, ids, run_dir):
    """실제 반영 — `run_names.py rename --commit --ids <pid...>` (Task 3 필터, 자기
    append 분만 커밋). run_names.py 의 --run-dir 는 required 지만 rename 경로에서
    실제로 쓰이지 않는다(propagate run-dir 를 그대로 넘긴다).

    **피어리뷰 Important #2**: `run_names.py rename` 은 지정한 pid 가 불량(예: 이미
    상품삭제 처리된 상품)이어도 프로세스 자체는 rc=0 으로 끝난다 — "명령이 성공했다"와
    "실제로 반영됐다"가 다르다. rc=0 만 보고 `적용`으로 기록하면, 현황판에는 이미
    원장(run_names)이 써둔 `해당없음`을 propagate 가 `완료`로 덮어쓰고, ledger 멱등 때문에
    영영 재시도되지 않는 유령 성공이 남는다. stdout 의 `###RENAME### 반영 N / 불량 M / 오류 K`
    를 파싱해 반영이 0건이면 예외를 올려 이 타깃을 `보류`로 떨어뜨린다.
    """
    script = os.path.join(_skill_scripts_dir("product-name"), "run_names.py")
    venv_py = os.path.join(_claude_dir(), "..", ".venv", "Scripts", "python.exe")
    py = venv_py if os.path.exists(venv_py) else sys.executable
    args = [py, script, "rename", "--commit", "--sheet", sheet, "--tab", tab,
            "--run-dir", run_dir, "--ids", *ids]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", env=env)
    if r.returncode != 0:
        raise RuntimeError(f"run_names rename 실패: {(r.stderr or r.stdout)[:300]}")
    applied, bad, errored = _parse_rename_counts(r.stdout)
    if applied is not None and applied == 0:
        raise RuntimeError(
            f"run_names rename 이 반영 0건을 반환했다(불량 {bad}/오류 {errored}) — "
            f"성공 종료(rc=0)지만 실제 반영은 안 됐다: {(r.stdout or '')[-300:]}")
    return r.stdout


def _name_row_exists(ctx, sid, tab, pid, memo):
    """이미 같은 (상품id, 메모) 행이 시트에 있는가 — 부분실패 재시도 방어(피어리뷰 Important #3).

    행 append 는 성공했는데 뒤이은 `rename_runner`(subprocess) 가 실패하면 예외가 올라가
    이 타깃은 `보류`로 기록된다. 재시도 시 그대로 다시 append 하면 같은 메모의 행이
    중복으로 쌓인다 — append 직전에 시트를 조회해 이미 있으면 건너뛰고 rename 만 재시도한다.
    조회 자체가 실패하면(탭 없음 등) "없다"로 보고 평소대로 append 를 시도한다.
    """
    try:
        rows = ctx["read_tab"](sid, tab)
    except Exception:  # noqa: BLE001 — 조회 실패는 최초 실행과 동일하게 처리
        return False
    if not rows:
        return False
    header = [str(c).strip() for c in rows[0]]
    if "상품id" not in header or "메모" not in header:
        return False
    i_id, i_memo = header.index("상품id"), header.index("메모")
    for r in rows[1:]:
        row = list(r) + [""] * (len(header) - len(r))
        if str(row[i_id]).strip() == pid and str(row[i_memo]).strip() == memo:
            return True
    return False


def apply_상품명(pid, plan_value, extra, target, ctx, code=None, rep_pid=None,
                rep_group_id=None, **kw):
    """shuffle_name → 타깃 소속 시트 상품명 탭에 행 append → run_names.py rename --commit
    --ids <자기가 append 한 pid 만>."""
    sid = extra["target_sheet"]
    group_id = target.get("groupId")
    새이름, 키워드 = propagated_name(plan_value, code, group_id, rep_group_id)
    snap = ctx["snapshot_load"](pid) or {}
    원본 = snap.get("상품명", "")
    memo = f"전파({code},{rep_pid})"

    rn = ctx.get("name_header_module") or _name_header_module()
    header = list(rn.NAME_HEADER)

    if not _name_row_exists(ctx, sid, "상품명", pid, memo):
        row = _build_name_row(header, pid, 원본, 새이름, 키워드, target.get("그룹명", ""), code, rep_pid)
        ctx["ensure_tab"](sid, "상품명", header)
        ctx["append_rows"](sid, "상품명", [row])

    rename_runner = ctx["rename_runner"]
    rename_runner(sheet=sid, tab="상품명", ids=[pid], run_dir=ctx["run_dir"])


# ---------------------------------------------------------------------------
# 작업 레지스트리 — onestep 의 STEPS 구조 복제, matrix.TASKS 이름과 정렬.
# matrix_col = matrix 모듈에서 이 작업을 가리키는 열 이름(=matrix.TASKS 원소, Task4 design choice).
# ---------------------------------------------------------------------------

TASKS = {
    "카테고리": {"load_plan": load_plan_카테고리, "verify": verify_카테고리,
              "apply": apply_카테고리, "matrix_col": "카테고리"},
    "상품명":   {"load_plan": load_plan_상품명, "verify": verify_상품명,
              "apply": apply_상품명, "matrix_col": "상품명"},
    "옵션":     {"load_plan": load_plan_옵션, "verify": verify_옵션,
              "apply": apply_옵션, "matrix_col": "옵션"},
    "썸네일":   {"load_plan": load_plan_썸네일, "verify": verify_썸네일,
              "apply": apply_썸네일, "matrix_col": "썸네일"},
}


# ---------------------------------------------------------------------------
# plan — 읽기 전용. codes/reps/same_group_dups + 현황판 병합 → plan.json/held.json
# ---------------------------------------------------------------------------

def _load_inventory():
    base = _inventory_dir()
    codes = dedup.load_json(os.path.join(base, "codes.json"), {})
    reps = dedup.load_json(os.path.join(base, "reps.json"), {})
    dup_codes = set(dedup.load_json(os.path.join(base, "same_group_dups.json"), {}))
    return codes, reps, dup_codes


def _qualifying_codes(codes, dup_codes):
    """전파 대상 코드만: 인스턴스 ≥2 이고 서로 다른 groupId 에 걸치며, 동일그룹중복이 아닌 것.

    same_group_dups.json 에 있는 코드는 통째로 제외한다(그룹 내 중복은 삭제 트랙 —
    §5 인계문서. 이 코드가 동시에 다른 그룹에도 걸쳐 있더라도 예외 없이 뺀다).
    """
    out = {}
    for code, insts in codes.items():
        if code in dup_codes:
            continue
        if len(insts) < 2:
            continue
        if len({i.get("groupId") for i in insts}) < 2:
            continue
        out[code] = insts
    return out


def _new_run_dir():
    # 초 단위까지 찍는다(피어리뷰 Minor) — 분 단위면 같은 분에 두 번 plan 을 돌릴 때
    # run-dir 이 충돌해 앞선 run 의 plan.json/ledger 를 덮어쓸 위험이 있었다.
    return os.path.join(_root(), "propagate", "runs", time.strftime("%Y-%m-%d-%H%M%S"))


def _memoize0(fn):
    """인자 없는 콜러블(예: `index_groups()`)을 1회만 평가하고 캐시한다.

    피어리뷰 Important #4: `run_plan` 이 코드마다(그리고 코드당 작업 4개마다) `load_plan_*`
    를 부르는데, 각 `load_plan_*` 가 내부에서 `index_groups()` 를 다시 부르면 전건(수만 코드)
    규모에서 마스터 인덱스 시트를 수만 번 재조회해 쿼터를 태운다. `run_plan` 전체에서 딱
    1번만 평가되도록 감싼다.
    """
    cache = {}

    def wrapped():
        if "v" not in cache:
            cache["v"] = list(fn())
        return cache["v"]
    return wrapped


def _memoize_read_tab(fn):
    """`(sheet_id, tab)` 키로 결과를 캐시하는 `read_tab` 래퍼(피어리뷰 Important #4).

    여러 코드의 대표가 같은 그룹 시트에 몰려 있으면(흔한 경우) 같은 탭을 코드마다
    다시 읽던 낭비를 없앤다.
    """
    cache = {}

    def wrapped(sid, tab):
        key = (sid, tab)
        if key not in cache:
            cache[key] = fn(sid, tab)
        return cache[key]
    return wrapped


def run_plan(read_matrix=None, index_groups=None, read_tab=None, load_snapshot=None,
            find_option_plan=None, run_dir=None, log=print):
    """plan 단계 본체 — 시트/MCP 쓰기 0회.

    `read_matrix`/`index_groups`/`read_tab`/`load_snapshot`/`find_option_plan` 은 전부
    테스트 주입점(`run_targets` 관례). 미지정이면 실제 구현(`inventory._read_matrix_all` ·
    `matrix.index_groups` · 실제 시트 읽기 · `snapshot.load`)을 쓴다. `find_option_plan`
    은 production 기본값이 없다 — Task 5 concerns 참조(옵션 소스 run-dir 규약 미정).

    **옵션 작업은 `find_option_plan` 이 배선되지 않은 한 타깃을 전개하지 않는다**
    (피어리뷰 Important #5b) — 배선 없이 전개하면 확정값이 항상 없어 타깃 전부가
    매 plan/apply 재실행마다 `00_보류함`·ledger·승인로그에 똑같이 다시 쌓이는
    탈출불가 루프가 된다. 대신 코드당 요약 행 1개(targets=[])만 남긴다.
    """
    from eroomlib.runner import inventory as _inv

    codes, reps, dup_codes = _load_inventory()
    inst_by_pid = {i["productId"]: i for insts in codes.values() for i in insts}
    qualifying = _qualifying_codes(codes, dup_codes)
    # 정확히 "동일그룹중복이라 뺀 코드"만 센다 — 인스턴스<2·단일그룹이라 빠진 코드와
    # 섞으면(둘 다 len(codes)-len(qualifying)에 들어간다) 이름이 거짓말을 하게 된다.
    same_group_excluded = sum(1 for c in codes if c in dup_codes)

    sheets, mtx = (read_matrix() if read_matrix else _inv._read_matrix_all(log))

    cached_index_groups = _memoize0(index_groups or matrix.index_groups)
    cached_read_tab = _memoize_read_tab(read_tab or _default_read_tab)
    deps = {"index_groups": cached_index_groups, "read_tab": cached_read_tab,
            "load_snapshot": load_snapshot, "find_option_plan": find_option_plan}
    plan_entries = []
    held = []
    stats = {"대표미완료스킵": 0, TARGET_TRANSPLANT: 0, TARGET_HELD: 0, TARGET_SKIP: 0,
             "옵션미배선스킵": 0}

    for code in sorted(qualifying):
        insts = qualifying[code]
        rep_pid = reps.get(code)
        if not rep_pid:
            # reps.json 이 codes.json 과 어긋난 데이터 불일치 — 조용히 넘어가지 않되
            # 이 태스크 범위(재구성)는 아니므로 로그만 남기고 건너뛴다.
            if log:
                log(f"  [경고] 대표 없음(reps.json 누락) — 코드 {code} 건너뜀")
            continue
        rep_inst = inst_by_pid.get(rep_pid) or {}
        rep_rec = mtx.get(rep_pid) or {}
        target_insts = [i for i in insts if i["productId"] != rep_pid]

        for task in TASKS:
            spec = TASKS[task]
            rep_val = (rep_rec.get(task) or "").strip()
            if rep_val != matrix.DONE:
                stats["대표미완료스킵"] += 1
                continue  # 이 코드의 이 작업은 대표 자체가 미완료 — 옮길 값이 없다

            if task == "옵션" and not deps.get("find_option_plan"):
                stats["옵션미배선스킵"] += len(target_insts)
                plan_entries.append({
                    "코드": code, "대표pid": rep_pid, "대표groupId": rep_inst.get("groupId"),
                    "작업": task, "확정값": None,
                    "메모": f"옵션런디렉토리규약미정 — 타깃 {len(target_insts)}건 요약 생략"
                           f"(find_option_plan 배선 후 재생성 필요)",
                    "targets": [],
                })
                continue

            plan_value, memo = spec["load_plan"](rep_pid, rep_inst.get("그룹명", ""), deps)

            entry_targets = []
            for inst in target_insts:
                pid = inst["productId"]
                val = (mtx.get(pid) or {}).get(task) or ""
                verdict, reason = classify_matrix_value(val)
                entry_targets.append({
                    "productId": pid, "groupId": inst.get("groupId"),
                    "그룹명": inst.get("그룹명", ""), "현황판값": val, "판정": verdict,
                })
                stats[verdict] += 1
                if verdict == TARGET_HELD:
                    held.append({"코드": code, "productId": pid, "작업": task,
                                "현황판값": val, "사유": reason})

            plan_entries.append({
                "코드": code, "대표pid": rep_pid, "대표groupId": rep_inst.get("groupId"),
                "작업": task, "확정값": plan_value, "메모": memo,
                "targets": entry_targets,
            })

    run_dir = run_dir or _new_run_dir()
    os.makedirs(run_dir, exist_ok=True)
    out = {
        "생성일": time.strftime("%Y-%m-%d %H:%M"),
        "대상코드수": len(qualifying),
        "동일그룹중복제외코드수": same_group_excluded,
        "plan": plan_entries,
        "요약": stats,
    }
    dedup.save_json(os.path.join(run_dir, "plan.json"), out)
    dedup.save_json(os.path.join(run_dir, "held.json"), held)

    if log:
        log(f"대상 코드 {len(qualifying)} (동일그룹중복 제외 {same_group_excluded})")
        log(f"  이식 {stats[TARGET_TRANSPLANT]} · 보류함 {stats[TARGET_HELD]} · "
            f"스킵 {stats[TARGET_SKIP]} · 대표미완료스킵 {stats['대표미완료스킵']} · "
            f"옵션미배선스킵 {stats['옵션미배선스킵']}")
        log(f"  run-dir: {run_dir}")
    return out, held


# ---------------------------------------------------------------------------
# apply — plan.json 을 실제로 반영. --commit 없으면 dry-run(쓰기 0, 할 일만 출력).
# ---------------------------------------------------------------------------

HELD_TAB = "00_보류함"
HELD_HEADER = ["코드", "타깃pid", "그룹명", "작업", "현황판값", "사유", "기록일", "승인"]

_RESULT_TO_APPROVAL = {"적용": "승인", "보류": "보류", "스킵": "건너뜀"}


def _ledger_path(run_dir):
    return os.path.join(run_dir, "ledger.jsonl")


def _load_ledger_results(run_dir, result_filter=None):
    """ledger.jsonl 전체를 파싱된 레코드 리스트로. `result_filter` 로 결과값을 좁힌다."""
    path = _ledger_path(run_dir)
    out = []
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except (ValueError, TypeError):
                continue
            if result_filter is None or rec.get("결과") == result_filter:
                out.append(rec)
    return out


def _load_ledger_applied(run_dir):
    """ledger.jsonl 에서 이미 '적용' 완료된 (코드,타깃pid,작업) 집합. 파일 없으면 빈 집합.

    **멱등의 핵심**: 같은 plan 을 다시 apply 해도 이미 적용된 타깃은 재시도하지 않는다.
    """
    return {(r.get("코드"), r.get("타깃pid"), r.get("작업"))
           for r in _load_ledger_results(run_dir, "적용")}


def _load_ledger_held_keys(run_dir):
    """ledger.jsonl 에서 이미 '보류' 기록된 (코드,타깃pid,작업,사유) 집합.

    피어리뷰 Important #5a — 00_보류함 시트 append 를 재실행마다 중복시키지 않기 위한
    대조 키 중 하나(다른 하나는 시트 자체의 기존 행, `_existing_held_keys`).
    """
    return {(r.get("코드"), r.get("타깃pid"), r.get("작업"), r.get("사유"))
           for r in _load_ledger_results(run_dir, "보류")}


def _existing_held_keys(read_tab, master_sheet):
    """마스터 시트 `00_보류함` 탭에 이미 있는 (코드,타깃pid,작업,사유) 집합.

    조회 자체가 실패하면(탭 없음 등) 빈 집합 — 최초 실행과 동일하게 동작한다.
    """
    try:
        rows = read_tab(master_sheet, HELD_TAB)
    except Exception:  # noqa: BLE001
        rows = None
    if not rows:
        return set()
    header = [str(c).strip() for c in rows[0]]
    try:
        i_code = header.index("코드")
        i_pid = header.index("타깃pid")
        i_task = header.index("작업")
        i_reason = header.index("사유")
    except ValueError:
        return set()
    out = set()
    for r in rows[1:]:
        row = list(r) + [""] * (len(header) - len(r))
        out.add((str(row[i_code]).strip(), str(row[i_pid]).strip(),
                 str(row[i_task]).strip(), str(row[i_reason]).strip()))
    return out


def _append_ledger(run_dir, entries):
    if not entries:
        return
    path = _ledger_path(run_dir)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def run_apply(run_dir, task=None, codes=None, commit=False, plan_path=None, mcp=None,
             index_groups=None, read_tab=None, master_sheet=None,
             ensure_tab=None, append_rows=None, mark_many=None,
             approval_record=None, snapshot_load=None, snapshot_update=None,
             rename_runner=None, name_header_module=None, log=print):
    """plan.json 을 실제로 반영한다.

    **검증(verify)은 commit 여부와 무관하게 항상 수행**한다 — dry-run 도 "무엇이 될지"를
    정확히 보여줘야 하고, verify 의 MCP 호출은 전부 preview(서버에 아무것도 저장하지 않는
    조회)뿐이다. **실제 반영(계정 write: ledger·00_보류함·현황판·승인로그·apply 의
    confirm=True 커밋)만 commit 여부로 완전히 게이트**한다 — dry-run 은 쓰기 0.

    **멱등** 은 두 겹: ① 같은 run-dir 의 ledger.jsonl 에 이미 '적용' 기록이 있으면 즉시 스킵
    (재조회·재커밋 없음) ② verify 자체도 "타깃 현재 값이 이미 확정값과 같다" 를 스킵으로 판정.

    **verify 예외 방어(피어리뷰 Important #6)**: verify 도 preview MCP 콜이라 네트워크
    예외가 날 수 있다 — apply 와 같은 try 안에서 잡아 그 타깃만 `보류`로 떨어뜨린다
    (한 건의 검증 실패가 run 전체를 죽이면 안 된다). **ledger 는 타깃 1건을 처리할 때마다
    즉시 append** 한다(끝까지 모았다가 한 번에 쓰지 않는다) — 중간에 뭔가 죽어도 이미
    처리한 건들의 감사 기록은 남는다.

    **mcp 배선(피어리뷰 Critical #1)**: `mcp` 를 안 주면 `PropagateMCP()` 를 직접 만들어
    열고, 끝나면(예외가 나도) 닫는다 — run_options.py/run_thumbs.py 의 기존 관례
    (`mcp = OptionMCP(); mcp.open() ... finally: mcp.close()`)와 동일.

    `name_header_module` 은 `apply_상품명`이 쓰는 product-name 스킬 `NAME_HEADER` 를
    테스트가 대체 주입할 수 있게 하는 지점(미지정이면 실제 `run_names` 모듈을 교차 임포트).
    """
    run_dir = os.path.abspath(run_dir)
    plan = dedup.load_json(plan_path or os.path.join(run_dir, "plan.json"), None)
    if plan is None:
        raise RuntimeError(f"plan.json 이 없다: {run_dir} — plan 을 먼저 실행하라.")

    index_groups = index_groups or matrix.index_groups
    read_tab = read_tab or _default_read_tab
    ensure_tab = ensure_tab or gsheets.ensure_tab
    append_rows = append_rows or gsheets.append_rows
    mark_many = mark_many or matrix.mark_many
    approval_record = approval_record or approval_log.record
    snapshot_load = snapshot_load or snapshot.load
    snapshot_update = snapshot_update or snapshot.update
    rename_runner = rename_runner or _default_rename_runner
    master_sheet = master_sheet or cfg("sheets.master_index", required=True)
    codes = set(codes) if codes else None

    own_mcp = mcp is None
    if own_mcp:
        mcp = PropagateMCP()
        mcp.open()
    try:
        return _run_apply_body(
            plan, run_dir, task=task, codes=codes, commit=commit, mcp=mcp,
            index_groups=index_groups, read_tab=read_tab, master_sheet=master_sheet,
            ensure_tab=ensure_tab, append_rows=append_rows, mark_many=mark_many,
            approval_record=approval_record, snapshot_load=snapshot_load,
            snapshot_update=snapshot_update, rename_runner=rename_runner,
            name_header_module=name_header_module, log=log)
    finally:
        if own_mcp:
            mcp.close()


def _run_apply_body(plan, run_dir, task, codes, commit, mcp, index_groups, read_tab,
                    master_sheet, ensure_tab, append_rows, mark_many, approval_record,
                    snapshot_load, snapshot_update, rename_runner, name_header_module, log):
    """`run_apply` 의 본체 — mcp 수명(open/close)과 분리해 테스트하기 쉽게 뺐다."""
    sheets_map = dict(index_groups())
    already = _load_ledger_applied(run_dir)
    held_seen = set()
    if commit:
        # 재실행마다 00_보류함/승인로그에 같은 사유가 다시 쌓이는 걸 막는다(피어리뷰
        # Important #5a) — 기존 시트 행 + 이전 ledger 의 '보류' 기록을 합쳐 대조 키로 쓴다.
        held_seen = _existing_held_keys(read_tab, master_sheet) | _load_ledger_held_keys(run_dir)

    ctx = {
        "mcp": mcp, "snapshot_load": snapshot_load, "snapshot_update": snapshot_update,
        "sheets_map": sheets_map, "index_groups": index_groups, "read_tab": read_tab,
        "ensure_tab": ensure_tab, "append_rows": append_rows,
        "rename_runner": rename_runner, "run_dir": run_dir,
        "name_header_module": name_header_module,
    }

    held_rows, approvals = [], []
    matrix_updates = {}
    counts = {}

    for entry in plan.get("plan", []):
        e_code, e_task = entry["코드"], entry["작업"]
        rep_pid, rep_group_id = entry.get("대표pid"), entry.get("대표groupId")
        확정값, 메모 = entry.get("확정값"), entry.get("메모")
        if task and e_task != task:
            continue
        if codes and e_code not in codes:
            continue
        spec = TASKS[e_task]

        for target in entry.get("targets", []):
            pid, 판정 = target["productId"], target["판정"]
            결과 = 사유 = ""
            if 판정 == TARGET_SKIP:
                결과, 사유 = "스킵", target.get("현황판값") or "이미완료"
            elif 판정 == TARGET_HELD:
                _, reason = classify_matrix_value(target.get("현황판값"))
                결과, 사유 = "보류", reason
            elif 판정 == TARGET_TRANSPLANT:
                if (e_code, pid, e_task) in already:
                    결과, 사유 = "스킵", "이미적용(ledger)"
                elif 확정값 is None:
                    결과, 사유 = "보류", 메모 or "확정값없음"
                else:
                    try:
                        v_status, v_reason, extra = spec["verify"](pid, 확정값, target, ctx)
                    except Exception as e:  # noqa: BLE001 — 검증(프리뷰) 예외 1건이
                        # run 전체를 죽이면 안 된다(피어리뷰 Important #6) — 이 타깃만 보류.
                        결과, 사유 = "보류", f"검증실패:{type(e).__name__}:{str(e)[:150]}"
                    else:
                        if v_status == VERIFY_SKIP:
                            결과, 사유 = "스킵", v_reason
                        elif v_status == VERIFY_HELD:
                            결과, 사유 = "보류", v_reason
                        elif not commit:
                            결과, 사유 = "적용예정", "dry-run"
                        else:
                            try:
                                spec["apply"](pid, 확정값, extra, target, ctx,
                                              code=e_code, rep_pid=rep_pid,
                                              rep_group_id=rep_group_id)
                                결과, 사유 = "적용", ""
                            except Exception as e:  # noqa: BLE001 — 한 건 실패가 전체를 멈추면 안 된다
                                결과, 사유 = "보류", f"적용실패:{type(e).__name__}:{str(e)[:150]}"
            else:
                결과, 사유 = "보류", f"미분류판정:{판정}"

            counts[결과] = counts.get(결과, 0) + 1
            if log:
                log(f"  [{결과}] {e_code} {e_task} {pid} — {사유}")
            if not commit:
                continue  # dry-run — 여기서부터는 전부 쓰기라 건드리지 않는다

            grp_name = target.get("그룹명", "")
            sheet_id = sheets_map.get(grp_name)
            # ledger 는 타깃 1건 처리 직후 즉시 append(Important #6) — 뒤에서 다른 타깃이
            # 죽어도 이 건의 감사 기록은 이미 디스크에 있다.
            _append_ledger(run_dir, [{
                "시각": time.strftime("%Y-%m-%d %H:%M:%S"), "작업": e_task, "코드": e_code,
                "대표pid": rep_pid, "타깃pid": pid, "결과": 결과, "사유": 사유,
            }])

            if 결과 == "보류":
                held_key = (e_code, pid, e_task, 사유)
                if held_key not in held_seen:
                    held_rows.append({"코드": e_code, "productId": pid, "그룹명": grp_name,
                                      "작업": e_task, "현황판값": target.get("현황판값", ""),
                                      "사유": 사유})
                    if sheet_id:
                        approvals.append((sheet_id, pid, e_task, 결과, 사유))
                    held_seen.add(held_key)
                # 이미 있는 (코드,pid,작업,사유) 면 시트/승인로그에 또 안 남긴다 —
                # ledger 는 위에서 이미 기록됐다(감사 추적은 유지, 노이즈만 제거).
            else:
                if 결과 == "적용" and sheet_id:
                    matrix_updates.setdefault(sheet_id, {}).setdefault(e_task, {})[pid] = matrix.DONE
                elif 결과 == "적용" and log:
                    log(f"  [경고] {pid} 적용은 됐지만 그룹 '{grp_name}' 시트를 못 찾아 "
                        f"현황판·승인로그를 남기지 못한다 — index_groups 등록을 확인하라.")
                if sheet_id:
                    approvals.append((sheet_id, pid, e_task, 결과, 사유))

    if not commit:
        if log:
            log("\n미리보기다(dry-run) — 쓰기 0. 실제 반영하려면 --commit 을 붙여라.")
        return counts

    if held_rows:
        ensure_tab(master_sheet, HELD_TAB, HELD_HEADER)
        rows = [[h["코드"], h["productId"], h.get("그룹명", ""), h["작업"],
                h.get("현황판값", ""), h.get("사유", ""), time.strftime("%Y-%m-%d"), ""]
               for h in held_rows]
        append_rows(master_sheet, HELD_TAB, rows)
    for sheet_id, by_task in matrix_updates.items():
        for t, vals in by_task.items():
            try:
                mark_many(sheet_id, t, vals)
            except Exception as e:  # noqa: BLE001 — 현황판은 파생본, 실패해도 반영 결과는 유효
                if log:
                    log(f"  [경고] 현황판 갱신 실패({sheet_id}/{t}): {str(e)[:120]}")
    for sheet_id, pid, t, 결과, 사유 in approvals:
        try:
            approval_record(sheet_id, pid, step=f"전파-{t}",
                            result=_RESULT_TO_APPROVAL.get(결과, "보류"), memo=사유)
        except Exception as e:  # noqa: BLE001 — 승인로그는 파생본
            if log:
                log(f"  [경고] 승인로그 기록 실패({pid}): {str(e)[:120]}")

    if log:
        log(f"###PROPAGATE-APPLY### " + " / ".join(f"{k} {v}" for k, v in counts.items()))
    return counts


# ---------------------------------------------------------------------------
# status — run-dir 의 plan/ledger 집계 출력.
# ---------------------------------------------------------------------------

def run_status(run_dir, log=print):
    run_dir = os.path.abspath(run_dir)
    plan = dedup.load_json(os.path.join(run_dir, "plan.json"), None)
    if plan is None:
        raise RuntimeError(f"plan.json 이 없다: {run_dir}")

    ledger = []
    path = _ledger_path(run_dir)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ledger.append(json.loads(line))
                except (ValueError, TypeError):
                    continue

    by_result = {}
    for rec in ledger:
        k = rec.get("결과", "?")
        by_result[k] = by_result.get(k, 0) + 1
    total_targets = sum(len(e.get("targets", [])) for e in plan.get("plan", []))
    out = {"대상코드수": plan.get("대상코드수"), "타깃건수": total_targets,
          "ledger건수": len(ledger), "결과별": by_result}
    if log:
        log(f"run-dir: {run_dir}")
        log(f"대상 코드 {out['대상코드수']} · plan 타깃 {total_targets}건 · "
            f"ledger 기록 {len(ledger)}건")
        for k, v in sorted(by_result.items(), key=lambda kv: -kv[1]):
            log(f"  {k}: {v}")
    return out


# ---------------------------------------------------------------------------
# retry-held — 00_보류함 탭에서 이룸님이 '승인' 표시한 행만 다시 apply 경로로.
# ---------------------------------------------------------------------------

def _default_read_held_rows(master_sheet):
    header_len = len(HELD_HEADER)
    rows = gsheets.sheets_get(master_sheet, f"'{HELD_TAB}'!A2:{matrix._col_letter(header_len)}")
    out = []
    for r in rows or []:
        row = list(r) + [""] * (header_len - len(r))
        out.append(dict(zip(HELD_HEADER, row)))
    return out


def run_retry_held(run_dir, master_sheet=None, read_held_rows=None, commit=False, log=print,
                   **apply_kwargs):
    """00_보류함 탭의 `승인` 열이 정확히 '승인'인 행만 골라, plan.json 에서 그 (코드,타깃pid,
    작업) 엔트리만 뽑은 미니 plan(`retry_held_plan.json`)을 만들어 `run_apply` 의 verify/apply
    경로를 그대로 태운다(로직 중복 없음, 승인된 행은 이식 판정으로 승격).
    """
    run_dir = os.path.abspath(run_dir)
    master_sheet = master_sheet or cfg("sheets.master_index", required=True)
    read_held_rows = read_held_rows or _default_read_held_rows
    approved = [r for r in read_held_rows(master_sheet)
               if str(r.get("승인", "")).strip() == "승인"]
    if not approved:
        if log:
            log("00_보류함에 '승인' 표시된 행이 없다.")
        return {}

    plan = dedup.load_json(os.path.join(run_dir, "plan.json"), None)
    if plan is None:
        raise RuntimeError(f"plan.json 이 없다: {run_dir}")

    want = {(r.get("코드"), r.get("타깃pid"), r.get("작업")) for r in approved}
    matched = set()
    mini_entries = []
    for entry in plan.get("plan", []):
        targets = []
        for t in entry.get("targets", []):
            key = (entry["코드"], t["productId"], entry["작업"])
            if key in want:
                targets.append(dict(t, 판정=TARGET_TRANSPLANT))
                matched.add(key)
        if not targets:
            continue
        mini_entries.append({**entry, "targets": targets})

    # 승인은 됐는데 plan.json 어디에도 없는 행 — 다른 run-dir 것이거나 오탈자일 수 있다.
    # 조용히 사라지면 "승인했는데 왜 안 됐지"를 재구성할 방법이 없다(피어리뷰 Minor).
    unmatched = [r for r in approved
                if (r.get("코드"), r.get("타깃pid"), r.get("작업")) not in matched]
    if unmatched and log:
        preview = [(r.get("코드"), r.get("타깃pid"), r.get("작업")) for r in unmatched[:5]]
        log(f"  [경고] 승인됐지만 이 run-dir 의 plan.json 에 없는 행 {len(unmatched)}건 "
            f"— 무시됨: {preview}")

    mini_path = os.path.join(run_dir, "retry_held_plan.json")
    dedup.save_json(mini_path, {
        "생성일": time.strftime("%Y-%m-%d %H:%M"),
        "대상코드수": len(mini_entries), "동일그룹중복제외코드수": 0,
        "plan": mini_entries, "요약": {},
    })
    if log:
        log(f"승인된 보류 {len(approved)}건 → 재적용 대상 {sum(len(e['targets']) for e in mini_entries)}건")
    return run_apply(run_dir, plan_path=mini_path, commit=commit, master_sheet=master_sheet,
                     log=log, **apply_kwargs)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _not_implemented(cmd):
    raise SystemExit(f"propagate {cmd} — Task 5에서 구현. 지금은 plan만 완주합니다.")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="전파 러너 (그룹 간 중복 짝에 기작업 이식)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("plan", help="이식 계획 생성(쓰기 0)")
    p.add_argument("--run-dir", default=None)

    a = sub.add_parser("apply", help="plan.json 실제 반영(--commit 없으면 미리보기)")
    a.add_argument("--run-dir", required=True)
    a.add_argument("--task", default=None, choices=list(TASKS))
    a.add_argument("--codes", nargs="+", default=None)
    a.add_argument("--commit", action="store_true")

    s = sub.add_parser("status", help="run-dir 의 plan/ledger 집계")
    s.add_argument("--run-dir", required=True)

    r = sub.add_parser("retry-held", help="00_보류함 승인 행만 재적용")
    r.add_argument("--run-dir", required=True)
    r.add_argument("--commit", action="store_true")

    args = ap.parse_args()
    if args.cmd == "plan":
        run_plan(run_dir=args.run_dir)
        return
    if args.cmd == "apply":
        run_apply(args.run_dir, task=args.task,
                  codes=set(args.codes) if args.codes else None, commit=args.commit)
        return
    if args.cmd == "status":
        run_status(args.run_dir)
        return
    if args.cmd == "retry-held":
        run_retry_held(args.run_dir, commit=args.commit)
        return
    _not_implemented(args.cmd)  # 도달하지 않음(안전망)


if __name__ == "__main__":
    main()
