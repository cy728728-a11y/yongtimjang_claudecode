#!/usr/bin/env python3
"""키워드→상품명 배치 스킬 — 시트 IO 순수 모듈.

진입점 시트 read(완료판정 포함) / 출력탭 완료id set / 청크 append(429 백오프)만 담당.
gws CLI 호출은 eroomlib.gsheets 를 쓴다
(node run.js 직접 호출로 cmd.exe '>' 리다이렉트 우회하는 검증된 패턴 그대로).

설계문서: .claude/skills/keyword-pick/references/키워드-상품명-배치설계.md (§상태관리, §시트출력)
"""
import json
import os
import sys
import time

# eroomlib 로드: 상위로 `.claude` 앵커(= lib/eroomlib)를 찾아 lib 를 1회 insert.
_d = os.path.dirname(os.path.abspath(__file__))
while _d and _d != os.path.dirname(_d):
    _lib = os.path.join(_d, "lib")
    if os.path.isdir(os.path.join(_lib, "eroomlib")):
        if _lib not in sys.path:
            sys.path.insert(0, _lib)
        break
    _d = os.path.dirname(_d)
from eroomlib.gsheets import _run_gws, sheets_get  # noqa: E402
from eroomlib.gsheets import append_rows as _gs_append_rows  # noqa: E402
from eroomlib.gsheets import ensure_tab as _gs_ensure_tab  # noqa: E402
from eroomlib.config import cfg as _cfg  # noqa: E402

# 그룹 지정이 없을 때의 폴백 시트. workspace.toml 로 뺐다(없으면 DEFAULTS = 현행 값).
DEFAULT_SHEET = _cfg("sheets.keyword_default")
ENTRY_TAB = "시트1"

# 카테고리교정 "완료"로 간주하는 상태값 (시트1 G열)
DONE_STATUSES = {"자동저장완료", "저장완료", "이미정확", "변경대상"}

# 429/쿼터 초과로 판단할 오류 메시지 키워드
_RETRY_HINTS = ("429", "quota", "RESOURCE_EXHAUSTED", "rateLimitExceeded")


def read_targets(spreadsheet_id=DEFAULT_SHEET, tab=ENTRY_TAB):
    """진입점 시트1 A2:H 를 읽어 카테고리교정 완료행만 추출.

    완료 판정: 상품명(B) 있고 & 상태(G) ∈ DONE_STATUSES & 대표키워드(E) 있음.
    카테고리 = 변경카테고리(D). 단 D가 '(동일)'이거나 빈 값이면 이전카테고리(C).
    A열만 있고 B~H 가 빈 행(미교정)은 자동으로 제외된다.

    반환: [{"productId", "상품명", "대표키워드", "카테고리", "상태"}, ...]
    """
    rng = f"{tab}!A2:H"
    try:
        rows = sheets_get(spreadsheet_id, rng)
    except Exception as e:
        raise RuntimeError(f"read_targets 실패(시트 read): {e}")

    targets = []
    for r in rows:
        r = list(r) + [""] * (8 - len(r))  # 부족한 셀 패딩
        product_id, name, prev_cat, new_cat, keyword, confidence, status, recorded = r[:8]
        product_id = str(product_id).strip()
        if not product_id:
            continue
        name = str(name).strip()
        keyword = str(keyword).strip()
        status = str(status).strip()
        if not name or not keyword or status not in DONE_STATUSES:
            continue
        new_cat = str(new_cat).strip()
        prev_cat = str(prev_cat).strip()
        category = new_cat if (new_cat and new_cat != "(동일)") else prev_cat
        targets.append({
            "productId": product_id,
            "상품명": name,
            "대표키워드": keyword,
            "카테고리": category,
            "상태": status,
        })
    return targets


def read_done_ids(spreadsheet_id=DEFAULT_SHEET, tab="02-키워드"):
    """출력 탭(02-키워드 또는 03-상품명) A열에서 이미 처리된 상품id 집합을 반환.

    헤더(1행) 제외. 마커행(스킵/보류)도 A열에 상품id가 있으므로 "처리됨"으로 침 —
    재시도 루프 차단이 목적.
    """
    rng = f"'{tab}'!A2:A"
    try:
        rows = sheets_get(spreadsheet_id, rng)
    except Exception as e:
        raise RuntimeError(f"read_done_ids 실패(시트 read, tab={tab}): {e}")
    return {str(r[0]).strip() for r in rows if r and str(r[0]).strip()}


# append_rows · ensure_tab 는 eroomlib.gsheets 로 승격했다(스킬 2개 이상이 쓴다).
# 여기서는 이름만 다시 내보낸다 — 기존 호출부(`sheet_io.append_rows(...)`)를 그대로 둔다.
append_rows = _gs_append_rows
ensure_tab = _gs_ensure_tab


if __name__ == "__main__":
    # 스모크 테스트(읽기만, append는 실행하지 않음)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ts = read_targets()
    print(f"read_targets: {len(ts)}건")
    for t in ts[:3]:
        print(" ", t)

    for tab in ("02-키워드", "03-상품명"):
        ids = read_done_ids(tab=tab)
        print(f"read_done_ids({tab}): {len(ids)}건 -> {sorted(ids)}")

    print("append_rows: 스모크에서는 호출하지 않음 (시트 오염 방지)")
