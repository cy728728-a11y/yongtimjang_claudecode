#!/usr/bin/env python3
"""작업 매트릭스 — 그룹 시트의 `00_진행` 탭. "어떤 상품에 어떤 작업이 끝났나" 현황판 1장.

**왜**: 지금은 "이번엔 뭘 대상으로 돌리지?"를 스킬마다 다른 방식으로 알아낸다
(카테고리교정=시트1 G열 빈칸 / 상품명=상품명 탭 A열에 없는 것). 스킬이 8개가 되면
그 방식이 8개가 된다. 매트릭스가 있으면 **대상 선정이 쿼리 1줄**로 통일된다.

    상품 1건  → 그 행의 빈 칸
    상품 1000건 → "옵션 열이 빈 행 전부"
    스킬 입력 인터페이스는 언제나 `productId 목록` 하나.

**열**: A=상품id, B=상품(이름 — 사람이 알아보라고), 그 뒤 작업 열 9개.
값: 빈칸(미착수) / `완료` / `해당없음` / 그 밖의 문자열(진행중·보류 사유 등 원장 값 그대로).

**매트릭스는 원장이 아니라 파생본이다.** 원장은 각 스킬의 상세 탭(시트1·상품명·…)이고
매트릭스는 그 요약이다. 그래서:
  - 쓰기는 **작업 단위로 열 하나를 통째로**(`mark_many`) — 건건 즉시 치면 시트 API 호출이
    2배가 되는데(1000건이면 +1000회) 얻는 게 없다. 중단돼도 원장이 남아 있다.
  - 깨지거나 뒤처지면 `rebuild()` 로 **원장에서 언제든 다시 만든다.** 그래서 매트릭스를
    믿지 못할 상황 자체가 없다.

CLI:
    python .claude/lib/eroomlib/matrix.py rebuild --sheet <id> --group "1번_용쌤1-1"
    python .claude/lib/eroomlib/matrix.py show    --sheet <id> [--task 옵션]
"""
import json
import os
import sys

try:  # 패키지로 import 될 때(`from eroomlib import matrix`)
    from .gsheets import ensure_tab, sheets_get, sheets_update
except ImportError:  # 파일을 직접 실행할 때(`python .../matrix.py`)
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from eroomlib.gsheets import ensure_tab, sheets_get, sheets_update

TAB = "00_진행"

# 작업 순서 = 실제 처리 순서(수집 → 카테고리 → 상품명 → … → 업로드).
# 스킬이 늘면 여기에 추가한다. 기존 시트는 `rebuild` 가 헤더를 확장한다.
TASKS = ("수집", "카테고리", "상품명", "옵션", "썸네일", "상세", "지재권", "배송비", "업로드")
HEADER = ("상품id", "상품") + TASKS

DONE = "완료"
NA = "해당없음"

# 다른 단계가 "여기 다시 해야 한다"고 넘긴 표시. 값 예: `재작업(옵션: 대표색 불일치)`
#
# **왜 별도 탭이 아니라 열 값인가**: "대상 선정 = 매트릭스 쿼리 1줄"이 계약이다.
# 이관 탭을 따로 두면 스킬마다 두 곳을 봐야 하고, 곧 어긋난다.
#
# 이게 없으면 발견이 자유 텍스트 메모로만 남아 받는 쪽이 읽을 경로가 없다
# (실측: 옵션정리 파일럿 5건 중 3건이 썸네일·상품명 이관 대상이었는데 전부 유실됐다).
# `완료` 인 단계는 `pending` 이 빈칸만 고르므로 영영 다시 잡히지 않는다는 문제도 함께 푼다
# (용쌤1-1 상품명 재시도 143건 = 카테고리가 바뀌어 다시 해야 하는데 손으로 목록을 만들던 건).
REDO = "재작업"

# 카테고리 교정 시트1 G열에서 "저장됨"으로 보는 값.
# (keyword-pick/sheet_io.DONE_STATUSES 와 같은 뜻이지만 '변경대상'은 뺐다 —
#  그건 확신도 미달로 **저장하지 않고** 사람 승인을 기다리는 상태다.)
CATFIX_DONE = {"자동저장완료", "저장완료", "이미정확"}
# 상품명 탭 상태열에서 "불사자에 실제 반영됨"으로 보는 값.
NAME_DONE = {"반영완료"}
# 어느 원장에서든 이 값이면 상품이 사라진 것 → 이후 작업 해당없음.
DELETED_PREFIX = "상품삭제"


def _col_letter(n):
    """1-based 열번호 → A1 열문자(27→AA)."""
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(ord("A") + r) + s
    return s


def task_col(task):
    """작업 이름 → A1 열문자. 모르는 작업이면 KeyError."""
    return _col_letter(HEADER.index(task) + 1)


# ---------------------------------------------------------------------------
# 읽기
# ---------------------------------------------------------------------------

def read(sheet, tab=TAB):
    """매트릭스 전체를 1회 읽는다 → {상품id: {"row":행번호, "상품":이름, 작업:값, ...}}.

    러너는 시작할 때 이것만 부르면 된다(계획서 §부품2: 읽기는 시작 시 1회).
    탭이 없으면 빈 dict — 최초 실행으로 본다.
    """
    try:
        rows = sheets_get(sheet, f"'{tab}'!A1:{_col_letter(len(HEADER))}")
    except Exception as e:
        print(f"  (매트릭스 읽기 생략 — {str(e)[:100]})")
        return {}
    if not rows:
        return {}
    header = [str(c).strip() for c in rows[0]]
    out = {}
    for i, r in enumerate(rows[1:], start=2):
        pid = str(r[0]).strip() if r else ""
        if not pid or pid in out:
            continue
        rec = {"row": i, "상품": str(r[1]).strip() if len(r) > 1 else ""}
        for j, name in enumerate(header):
            if name in TASKS:
                rec[name] = str(r[j]).strip() if len(r) > j else ""
        out[pid] = rec
    return out


def is_redo(value):
    """`재작업(...)` 표시인가."""
    return (value or "").strip().startswith(REDO)


def redo_reason(value):
    """`재작업(옵션: 대표색 불일치)` → `옵션: 대표색 불일치`. 아니면 빈 문자열."""
    v = (value or "").strip()
    if not is_redo(v):
        return ""
    i, j = v.find("("), v.rfind(")")
    return v[i + 1:j].strip() if 0 <= i < j else ""


def redo_value(reason, from_task=None):
    """표시 문자열 1벌 — 발신 단계를 앞에 둔다(누가 왜 넘겼는지가 사람에게 먼저 보인다)."""
    body = f"{from_task}: {reason}" if from_task else str(reason)
    return f"{REDO}({body})"[:200]


def pending(matrix, task, exclude_na=True, include_redo=True):
    """그 작업이 **아직 안 된** 상품id 목록 — 이게 "대상 선정" 그 자체다.

    빈칸(미착수)과 `재작업(...)` 을 고른다. `해당없음`(상품삭제 등)은 기본 제외.
    보류·진행중처럼 그 밖의 값이 있는 건 사람이 이미 판단한 것이라 자동 재처리하지 않는다.

    **재작업이 기본 포함인 이유**: 재작업은 다른 단계가 "여기 다시 해야 한다"고 명시한
    할 일이다. 빼면 조용히 잊힌다. 또 기본이 제외였을 때는 *빈칸에 사유를 실을 수 없다는*
    부작용이 있었다 — 빈칸을 재작업으로 덮는 순간 대상에서 빠져 버렸다.
    대상 여부와 사유 전달을 한 값에 묶었으면 **둘 다 켜져 있어야** 앞뒤가 맞는다.

    `include_redo=False` 는 "이번엔 신규 미착수만" 이 필요한 쪽의 옵트아웃이다.
    """
    out = []
    for pid, rec in matrix.items():
        v = (rec.get(task) or "").strip()
        if not v:
            out.append(pid)
        elif include_redo and is_redo(v):
            out.append(pid)
        elif not exclude_na and v == NA:
            out.append(pid)
    return out


def redo_pending(matrix, task):
    """재작업으로 넘어온 것만 {상품id: 사유}. 왜 다시 하는지를 워커에게 실어 보낼 때 쓴다."""
    return {pid: redo_reason(rec.get(task))
            for pid, rec in matrix.items() if is_redo(rec.get(task))}


# ---------------------------------------------------------------------------
# 쓰기
# ---------------------------------------------------------------------------

def _insert_header_row(sheet, tab):
    """1행에 빈 행을 끼워 넣고 헤더를 쓴다 — 헤더 없이 데이터가 1행부터 쌓인 탭 복구용.

    탭 생성 직후 헤더 쓰기가 실패하면(쿼터 등) append 가 1행부터 채워 버린다.
    그 상태로 두면 `read` 가 작업 열을 하나도 인식하지 못한다(헤더 이름으로 찾으므로).
    """
    from eroomlib.gsheets import _run_gws
    meta = _run_gws(["sheets", "spreadsheets", "get",
                     "--params", json.dumps({"spreadsheetId": sheet})])
    sid = next((s["properties"]["sheetId"] for s in meta.get("sheets", [])
                if s["properties"]["title"] == tab), None)
    if sid is None:
        raise RuntimeError(f"탭을 찾지 못했습니다: {tab}")
    _run_gws(["sheets", "spreadsheets", "batchUpdate",
              "--params", json.dumps({"spreadsheetId": sheet})],
             body={"requests": [{"insertDimension": {
                 "range": {"sheetId": sid, "dimension": "ROWS",
                           "startIndex": 0, "endIndex": 1}}}]})
    sheets_update(sheet, f"'{tab}'!A1", [list(HEADER)])


def ensure(sheet, tab=TAB):
    """탭이 없으면 만들고 헤더를 쓴다. 있으면 헤더가 짧을 때 **뒤에만** 확장한다.

    반환: 새로 만들었으면 True.
    """
    created = ensure_tab(sheet, tab, list(HEADER))
    if created:
        return True
    try:
        cur = (sheets_get(sheet, f"'{tab}'!1:1") or [[]])[0]
    except Exception as e:
        print(f"  [경고] 매트릭스 헤더 확인 실패: {str(e)[:100]}")
        return False
    cur = [str(c).strip() for c in cur]
    # 1행이 헤더가 아니라 상품 행이면(헤더 쓰기가 실패했던 탭) 헤더를 끼워 넣는다.
    if cur and cur[0] != HEADER[0]:
        print(f"  [복구] {tab} 1행이 헤더가 아닙니다 — 헤더 행을 삽입합니다.")
        _insert_header_row(sheet, tab)
        return False
    if len(cur) >= len(HEADER):
        return False
    # 겹치는 구간이 다르면 열 순서가 어긋난 시트다 — 손대지 않고 사람이 보게 한다.
    if cur != list(HEADER)[:len(cur)]:
        print(f"  [경고] {tab} 헤더가 예상과 다릅니다(기존 {len(cur)}열). 확장하지 않습니다.")
        return False
    missing = list(HEADER)[len(cur):]
    sheets_update(sheet, f"'{tab}'!{_col_letter(len(cur) + 1)}1", [missing])
    print(f"  헤더 확장: {tab} +{len(missing)}열 ({', '.join(missing)})")
    return False


def mark_many(sheet, task, values, tab=TAB, matrix=None, preserve_redo=False):
    """작업 열 하나를 통째로 되쓴다. values = {상품id: 값}. 반환: 바뀐 칸 수.

    대상이 아닌 행은 **기존 값을 그대로 실어** 보존한다(열 통짜 update 라
    빠뜨리면 지워진다). 값이 실제로 바뀐 게 없으면 시트를 건드리지 않는다.

    `preserve_redo=True` 면 이미 `재작업(...)` 인 칸은 덮어쓰지 않는다.
    **`rebuild` 전용이다** — 재작업 표시는 원장에서 되살릴 수 없는 정보라
    (원장은 '옛 작업을 완료했다'고만 말한다) 재구성이 지워 버리면 영영 사라진다.
    실제 재작업을 마친 스킬은 기본값(False)으로 `완료` 를 써서 표시를 지운다.
    """
    if task not in TASKS:
        raise KeyError(f"모르는 작업: {task} (가능: {', '.join(TASKS)})")
    m = read(sheet, tab) if matrix is None else matrix
    if not m:
        return 0
    last = max(rec["row"] for rec in m.values())
    col = [[""] for _ in range(last - 1)]  # 2행 ~ last
    changed = 0
    for pid, rec in m.items():
        cur = (rec.get(task) or "").strip()
        if preserve_redo and is_redo(cur):
            col[rec["row"] - 2] = [cur]
            continue
        new = str(values.get(pid, cur) or "").strip()
        col[rec["row"] - 2] = [new]
        if new != cur:
            changed += 1
    if not changed:
        return 0
    _update_column(sheet, tab, task_col(task), col)
    return changed


def flag(sheet, pid, task, reason, from_task=None, tab=TAB, matrix=None):
    """단계 A 가 단계 B 에 일감을 넘기는 **단일 창구**. 칸 하나만 쓴다.

        matrix.flag(sheet, pid, "썸네일", "대표색 불일치", from_task="옵션")

    받는 단계는 `pending(m, "썸네일")` 로 미착수분과 함께 잡는다(재작업은 기본 포함).
    빈칸이든 `완료`든 찍을 수 있다 — 빈칸에 찍으면 **대상은 그대로 유지한 채 사유만** 붙는다.
    이미 `해당없음`(삭제 상품)이면 넘기지 않는다 — 없는 상품에 일감을 만들지 않는다.
    """
    m = read(sheet, tab) if matrix is None else matrix
    rec = m.get(pid)
    if not rec:
        return False
    if (rec.get(task) or "").strip() == NA:
        return False
    return mark(sheet, pid, task, redo_value(reason, from_task), tab=tab, matrix=m)


def flag_many(sheet, task, items, from_task=None, tab=TAB, matrix=None):
    """가로(1000건)용 — 한 바퀴 도는 동안 모아둔 이관을 **열 통짜 1회**로 쓴다.

    items = {상품id: 사유}. 삭제 상품은 건너뛴다. 반환: 실제로 찍힌 칸 수.
    """
    m = read(sheet, tab) if matrix is None else matrix
    if not m:
        return 0
    vals = {}
    for pid, reason in (items or {}).items():
        rec = m.get(pid)
        if not rec or (rec.get(task) or "").strip() == NA:
            continue
        vals[pid] = redo_value(reason, from_task)
    if not vals:
        return 0
    return mark_many(sheet, task, vals, tab=tab, matrix=m)


def _update_column(sheet, tab, letter, values, first_row=2):
    """열 하나를 first_row 부터 순서대로 쓴다. 청크는 **실제 길이**로 끊는다."""
    from eroomlib.gsheets import chunk_by_size
    for i, part in chunk_by_size(values):
        r0 = first_row + i
        sheets_update(sheet, f"'{tab}'!{letter}{r0}:{letter}{r0 + len(part) - 1}", part)


def mark(sheet, pid, task, value, tab=TAB, matrix=None):
    """단건 갱신 — 칸 하나만 update. 러너 없이 애드혹으로 1건 처리할 때 쓴다.

    대량 처리에서는 `mark_many` 를 써라(호출 1회 vs N회).
    """
    m = read(sheet, tab) if matrix is None else matrix
    rec = m.get(pid)
    if not rec:
        return False
    sheets_update(sheet, f"'{tab}'!{task_col(task)}{rec['row']}", [[value]])
    return True


def sync_products(sheet, products, tab=TAB):
    """그룹 상품 목록을 A·B열에 반영 — **없는 상품만 아래에 추가**한다.

    products = [{"productId","상품명"}]. 기존 행은 절대 건드리지 않는다
    (작업 열 값이 날아가면 안 된다). 반환: 추가한 행 수.
    """
    from eroomlib.gsheets import append_rows, chunk_by_size
    m = read(sheet, tab)
    new = [p for p in products if str(p.get("productId", "")).strip()
           and p["productId"] not in m]
    if not new:
        return 0
    # 작업 열은 비워 둔 채 A·B만 넣는다(빈 문자열을 실어 보낼 이유가 없다).
    rows = [[p["productId"], p.get("상품명", "")] for p in new]
    for _, part in chunk_by_size(rows):
        append_rows(sheet, tab, part)
    return len(rows)


# ---------------------------------------------------------------------------
# rebuild — 원장(각 스킬 상세 탭)에서 역산
# ---------------------------------------------------------------------------

def _status_by_id(rows, id_col=0, status_col=None, status_name="상태", last_wins=True):
    """원장 탭 행들 → {상품id: 상태문자열}.

    상태 열은 헤더 이름으로 찾고, 못 찾으면 status_col 폴백.
    같은 상품이 여러 행이면(상품명 탭의 재작업·마커 행) **마지막 행이 최신**이다.
    """
    if not rows:
        return {}
    header = [str(c).strip() for c in rows[0]]
    idx = header.index(status_name) if status_name in header else status_col
    if idx is None:
        return {}
    out = {}
    for r in rows[1:]:
        pid = str(r[0]).strip() if r and len(r) > id_col else ""
        if not pid:
            continue
        val = str(r[idx]).strip() if len(r) > idx else ""
        if last_wins or pid not in out:
            out[pid] = val
    return out


def map_catfix(status):
    """시트1 G열 상태 → 매트릭스 `카테고리` 값."""
    s = (status or "").strip()
    if not s:
        return ""
    if s.startswith(DELETED_PREFIX):
        return NA
    return DONE if s in CATFIX_DONE else s


def map_name(status):
    """상품명 탭 상태 → 매트릭스 `상품명` 값."""
    s = (status or "").strip()
    if not s:
        return ""
    if s.startswith(DELETED_PREFIX):
        return NA
    if s in NAME_DONE:
        return DONE
    if s == "생성완료":
        return "진행중(미반영)"  # 만들었지만 불사자에 아직 안 올린 것
    return s


# 상품명 원장 탭 이름 후보 — 초기 그룹(25-2 등)은 '03-상품명' 을 쓴다.
NAME_TABS = ("상품명", "03-상품명")


def rebuild(sheet, products, catfix_tab="시트1", name_tab=None, tab=TAB,
            log=print):
    """그룹 상품 목록 + 원장 탭들 → 매트릭스를 처음부터/다시 만든다(멱등).

    products = [{"productId","상품명"}] (마켓그룹 전체).
    `수집` 은 이미 불사자에 수집된 상품이므로 전건 `완료`.
    나머지 작업 열은 담당 스킬이 아직 없으니 빈칸(미착수)으로 둔다.
    """
    created = ensure(sheet, tab)
    log(f"  탭 {'신설' if created else '확인'}: {tab}")
    added = sync_products(sheet, products, tab)
    log(f"  상품 행: +{added}건 (그룹 {len(products)}건)")

    m = read(sheet, tab)
    if not m:
        log("  [경고] 매트릭스가 비어 있습니다 — 상품 목록을 확인하세요.")
        return {}

    def _rows(t):
        try:
            return sheets_get(sheet, f"'{t}'!A1:AZ")
        except Exception as e:
            log(f"  ('{t}' 탭 읽기 생략 — {str(e)[:80]})")
            return []

    cat = {pid: map_catfix(v)
           for pid, v in _status_by_id(_rows(catfix_tab), status_col=6).items()}
    # 상품명 원장은 그룹마다 탭 이름이 다를 수 있다 — 후보를 순서대로 찾아본다.
    nam = {}
    for t in ([name_tab] if name_tab else NAME_TABS):
        found = _status_by_id(_rows(t))
        if found:
            nam = {pid: map_name(v) for pid, v in found.items()}
            log(f"  상품명 원장: '{t}' ({len(nam)}건)")
            break

    # 상품이 삭제됐다면 이후 작업은 전부 해당없음 — 어느 원장에서 알았든 동일하게 본다.
    deleted = {pid for pid, v in list(cat.items()) + list(nam.items()) if v == NA}

    # 담당 스킬이 있는 작업만 원장에서 채운다. 나머지는 빈칸(미착수)이 정답.
    # 단 **삭제된 상품은 전 작업이 `해당없음`** 이어야 한다 — 안 그러면 나중에
    # 옵션정리·썸네일을 돌릴 때 없는 상품이 대상으로 잡힌다.
    known = {"수집": {pid: DONE for pid in m}, "카테고리": cat, "상품명": nam}
    stats = {}
    for task in TASKS:
        vals = dict(known.get(task, {}))
        for pid in deleted:
            if pid in m:
                vals[pid] = NA
        if not vals:
            continue
        # 재작업 표시는 원장에서 되살릴 수 없다 → 재구성이 지우지 않게 한다.
        n = mark_many(sheet, task, vals, tab=tab, matrix=m, preserve_redo=True)
        stats[task] = n
        if n:
            log(f"  {task}: {n}칸 갱신")
    if deleted:
        log(f"  삭제 상품 {len(deleted)}건 → 전 작업 '{NA}'")
    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _group_products(group_name):
    """마켓그룹명 → [{productId, 상품명}] (불사자 목록 조회)."""
    from eroomlib.snapshot import ProductMCP
    mcp = ProductMCP()
    mcp.open()
    try:
        groups = mcp.call_tool("bulsaja_market_groups", {}).get("그룹", [])
        hit = [g for g in groups if g.get("그룹명") == group_name]
        if not hit:
            hit = [g for g in groups if group_name in str(g.get("그룹명", ""))]
        if len(hit) != 1:
            names = ", ".join(str(g.get("그룹명")) for g in hit[:5])
            raise RuntimeError(
                f"마켓그룹 '{group_name}' 을 특정하지 못했습니다(후보 {len(hit)}개: {names})")
        gid = hit[0]["groupId"]
        print(f"  마켓그룹 {hit[0]['그룹명']} (groupId={gid})")
        return mcp.collect_group(gid, log=lambda m: None)
    finally:
        mcp.close()


def index_groups(master_sheet=None):
    """마스터 인덱스 시트 → [(그룹명, spreadsheetId)]. 링크에서 id 를 뽑는다."""
    import re
    from eroomlib.config import cfg as _c
    sid = master_sheet or _c("sheets.master_index", required=True)
    out = []
    for r in sheets_get(sid, "A2:B200"):
        if not r or not str(r[0]).strip():
            continue
        mm = re.search(r"/d/([A-Za-z0-9_-]+)", str(r[1]) if len(r) > 1 else "")
        if mm:
            out.append((str(r[0]).strip(), mm.group(1)))
    return out


def sync_all(only=None, master_sheet=None, log=print):
    """마스터 인덱스의 전 그룹에 `rebuild` 를 돌린다(멱등 — 몇 번 돌려도 안전).

    한 그룹이 실패해도 나머지는 계속한다. 반환: [(그룹명, 상태, 메시지)].
    """
    rows = index_groups(master_sheet)
    if only:
        rows = [(g, s) for g, s in rows if only in g]
    log(f"대상 그룹 {len(rows)}개")
    results = []
    for i, (group, sid) in enumerate(rows, 1):
        log(f"\n[{i}/{len(rows)}] {group}")
        try:
            rebuild(sid, _group_products(group), log=log)
            results.append((group, "ok", ""))
        except Exception as e:  # noqa: BLE001 — 한 그룹 실패가 전체를 멈추면 안 된다
            msg = f"{type(e).__name__}: {e}"[:200]
            log(f"  [실패] {msg}")
            results.append((group, "fail", msg))
    ok = sum(1 for _, s, _ in results if s == "ok")
    log(f"\n###MATRIX### {ok}/{len(results)} 그룹 완료")
    for g, s, msg in results:
        if s != "ok":
            log(f"  실패: {g} — {msg}")
    return results


def main():
    import argparse
    ap = argparse.ArgumentParser(description="작업 매트릭스(00_진행)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("rebuild", help="탭 생성 + 원장에서 역산(멱등)")
    r.add_argument("--sheet", required=True)
    r.add_argument("--group", required=True, help="마켓그룹명 (예: 1번_용쌤1-1)")
    r.add_argument("--catfix-tab", default="시트1")
    # 기본값은 None — 그래야 NAME_TABS 후보를 순서대로 찾는다(초기 그룹은 '03-상품명').
    r.add_argument("--name-tab", default=None)

    a = sub.add_parser("sync-all", help="마스터 인덱스의 전 그룹에 rebuild")
    a.add_argument("--only", default=None, help="그룹명에 이 문자열이 든 것만")
    a.add_argument("--master-sheet", default=None)

    s = sub.add_parser("show", help="현황 요약")
    s.add_argument("--sheet", required=True)
    s.add_argument("--task", default=None, help="이 작업의 미착수 상품id를 찍는다")
    s.add_argument("--limit", type=int, default=20)

    args = ap.parse_args()
    if args.cmd == "rebuild":
        rebuild(args.sheet, _group_products(args.group),
                catfix_tab=args.catfix_tab, name_tab=args.name_tab)
        print(f"  https://docs.google.com/spreadsheets/d/{args.sheet}/edit")
        return
    if args.cmd == "sync-all":
        res = sync_all(only=args.only, master_sheet=args.master_sheet)
        sys.exit(0 if all(s == "ok" for _, s, _ in res) else 1)

    m = read(args.sheet)
    print(f"상품 {len(m)}건")
    for t in TASKS:
        c = {}
        for rec in m.values():
            v = (rec.get(t) or "").strip() or "(미착수)"
            c[v] = c.get(v, 0) + 1
        print(f"  {t:5s} " + " · ".join(f"{k} {n}" for k, n in
                                        sorted(c.items(), key=lambda x: -x[1])))
    if args.task:
        ids = pending(m, args.task)
        print(f"\n[{args.task}] 미착수 {len(ids)}건")
        print(json.dumps(ids[:args.limit], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
