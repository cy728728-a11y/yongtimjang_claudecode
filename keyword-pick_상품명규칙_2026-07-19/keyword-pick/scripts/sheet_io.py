#!/usr/bin/env python3
"""키워드→상품명 배치 스킬 — 시트 IO 순수 모듈.

진입점 시트 read(완료판정 포함) / 출력탭 완료id set / 청크 append(429 백오프)만 담당.
gws CLI 호출은 bulsaja-category-fix/scripts/gws_util.py 를 sys.path 로 차용
(node run.js 직접 호출로 cmd.exe '>' 리다이렉트 우회하는 검증된 패턴 그대로 사용).

설계문서: .claude/skills/keyword-pick/references/키워드-상품명-배치설계.md (§상태관리, §시트출력)
"""
import json
import os
import sys
import time

# bulsaja-category-fix/scripts/gws_util.py 차용
_BULSAJA_SCRIPTS = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "bulsaja-category-fix", "scripts",
))
sys.path.insert(0, _BULSAJA_SCRIPTS)
from gws_util import _run_gws, sheets_get  # noqa: E402

DEFAULT_SHEET = "1DbR2upLX_DXjgjXpGPdide2SUifli_X6DTqhUTr9Syk"
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


def append_rows(spreadsheet_id, tab, rows, max_retries=4):
    """rows(2차원 리스트)를 탭 끝에 append (USER_ENTERED, INSERT_ROWS).

    429/쿼터 초과 오류는 지수 백오프(2·4·8·16초) 후 최대 max_retries 회 재시도.
    그 외 오류(4xx 등)는 즉시 예외를 올린다.
    rows 가 크면 그대로 한 호출로 보낸다 — 청크 분할(상품 10개 단위)은 호출자 책임.

    반환: 추가된 행수(len(rows)). 실패 시 RuntimeError.
    """
    if not rows:
        return 0

    rng = f"'{tab}'!A1"
    args = [
        "sheets", "spreadsheets", "values", "append",
        "--params", json.dumps({
            "spreadsheetId": spreadsheet_id,
            "range": rng,
            "valueInputOption": "USER_ENTERED",
            "insertDataOption": "INSERT_ROWS",
        }, ensure_ascii=False),
    ]
    body = {"values": rows}

    last_err = None
    for attempt in range(max_retries):
        try:
            _run_gws(args, body=body)
            return len(rows)
        except Exception as e:
            msg = str(e)
            last_err = e
            if any(h.lower() in msg.lower() for h in _RETRY_HINTS) and attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"[sheet_io] append 429/쿼터 오류, {wait}초 대기 후 재시도 "
                      f"({attempt + 1}/{max_retries}): {msg[:150]}", file=sys.stderr)
                time.sleep(wait)
                continue
            raise RuntimeError(f"append_rows 실패(tab={tab}, {len(rows)}행): {msg}")
    raise RuntimeError(f"append_rows 최대 재시도 초과(tab={tab}): {last_err}")


def ensure_tab(spreadsheet_id, tab, header):
    """탭이 없으면 addSheet + 헤더(1행) 기록. 있으면 아무것도 하지 않는다."""
    try:
        meta = _run_gws(["sheets", "spreadsheets", "get",
                          "--params", json.dumps({"spreadsheetId": spreadsheet_id})])
    except Exception as e:
        raise RuntimeError(f"ensure_tab 실패(메타 조회): {e}")

    existing = {s["properties"]["title"] for s in meta.get("sheets", [])}
    if tab in existing:
        return False  # 이미 존재

    try:
        _run_gws(["sheets", "spreadsheets", "batchUpdate",
                   "--params", json.dumps({"spreadsheetId": spreadsheet_id})],
                  body={"requests": [{"addSheet": {"properties": {"title": tab}}}]})
        rng = f"'{tab}'!A1"
        _run_gws(["sheets", "spreadsheets", "values", "update",
                   "--params", json.dumps({"spreadsheetId": spreadsheet_id,
                                           "range": rng,
                                           "valueInputOption": "RAW"})],
                  body={"values": [header]})
    except Exception as e:
        raise RuntimeError(f"ensure_tab 실패(탭 생성, tab={tab}): {e}")
    return True


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
