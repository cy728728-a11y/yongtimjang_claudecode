#!/usr/bin/env python3
"""상품명 배치 오케스트레이터 — 파이프라인 ⑤ product-name.

마켓그룹 하나(≈1000 상품)를 받아 썸네일·카테고리·키워드 후보를 모아 청크로 내고,
Claude가 만든 상품명을 검증→시트기록→불사자 반영까지 잇는다.

흐름:
  prep   : 마켓그룹 → 상품목록 → workdata(카테고리+썸네일) → 썸네일 다운로드
           → 카테고리 프리필터 → 계단 후보 청크(candidates/chunk_*.json)
  [Claude] 청크별로 썸네일 Read + 후보 대조 → 키워드 2~3개 선택 → 상품명 조립
           → named/named_*.json
  append : name_check 검증 → 상품명 탭 append (보류/실패도 마커로 남김)
  rename : 시트 상태=생성완료 건을 불사자에 실제 반영 (--commit 없으면 미리보기)

기존 자산을 빌려 쓴다(신규 구현 없음):
  bulsaja-category-fix/scripts : collect_group.py · bulsaja_mcp.py · fetch_thumbs.py
  keyword-pick/scripts         : cat_prefilter.py · batch_candidates.py · sheet_io.py

설계: keyword-pick/references/상품명-설계결정.md + 2026-07-23 확정 6개 결정
Usage:
  python run_names.py prep   --group-id 1001115 --run-dir <R> --source-date 260712 [--limit 20]
  python run_names.py append --run-dir <R> [--dry-run]
  python run_names.py rename --run-dir <R> [--commit]
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import time
from datetime import date

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILLS_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", ".."))
BULSAJA_SCRIPTS = os.path.join(SKILLS_DIR, "bulsaja-category-fix", "scripts")
KEYWORD_SCRIPTS = os.path.join(SKILLS_DIR, "keyword-pick", "scripts")

sys.path.insert(0, KEYWORD_SCRIPTS)
sys.path.insert(0, BULSAJA_SCRIPTS)
sys.path.insert(0, SCRIPT_DIR)

# gws 시트 래퍼는 eroomlib.gsheets 1벌을 쓴다(구 gws_util 차용 제거).
# `.claude` 앵커(= lib/eroomlib)를 찾아 lib 를 1회 insert.
_d = SCRIPT_DIR
while _d and _d != os.path.dirname(_d):
    _lib = os.path.join(_d, "lib")
    if os.path.isdir(os.path.join(_lib, "eroomlib")):
        if _lib not in sys.path:
            sys.path.insert(0, _lib)
        break
    _d = os.path.dirname(_d)

import sheet_io  # noqa: E402  (keyword-pick 소유)
import name_check  # noqa: E402  (이 스킬 소유 — 키워드 열 파싱 공유)
from eroomlib import config as _cfg  # noqa: E402  (경로·폴더ID·시트ID 1벌)
from eroomlib import snapshot  # noqa: E402  (공용 상품 스냅샷 — rename 후 상품명 되쓰기)
from eroomlib import matrix  # noqa: E402  (현황판 00_진행 — 상품명 열 갱신)

# --- 고정 설정 -------------------------------------------------------------
# 출력은 **그룹별 카테고리교정 로그 시트의 '상품명' 탭**이다(2026-07-23 결정).
# 작업 단위(마켓그룹)와 파일 단위가 일치하고, 입력(검색어(사용))과 출력이 한 파일에 모인다.
# 고정 기본 시트를 두지 않는다 — 그룹이 바뀌는데 시트가 안 바뀌면 다른 그룹 로그에 섞인다.
# 드라이브 폴더 id 는 workspace.toml 로 뺐다(배포본 대비). 없으면 DEFAULTS = 현행 값.
CATFIX_FOLDER = _cfg.cfg("drive.category_folder", required=True)
SHEET_PREFIX = _cfg.cfg("naming.group_sheet", "카테고리교정_{group}").split("{")[0]
NAME_TAB = "상품명"
# 카테고리 교정이 기록하는 데이터 탭(A 상품id … J 실물판정 K 썸네일URL). 상품명 탭과 다르다.
# collect_targets.py·sheet_log.py 와 같은 기본값 '시트1' 을 쓴다.
CATFIX_TAB = "시트1"
# 2026-07-24: 키워드별 상품수·검색량을 남긴다(이룸님 요구). 나중에 어떤 키워드가 먹혔는지
# 되짚으려면 선택 당시의 좌표가 있어야 한다 — 통다운은 매번 갱신되므로 사후 복원이 안 된다.
# 같은 날 후속: term 목표를 6~7로 올리며 키워드를 5개까지 붙이게 돼 키워드4·5 열을 추가.
MAX_KW_COLS = 5
NAME_HEADER = (
    ["상품id", "작업일", "마켓그룹", "카테고리", "원본상품명", "새상품명"]
    + [f"키워드{i}{suf}" for i in range(1, MAX_KW_COLS + 1)
       for suf in ("", "_상품수", "_검색량")]
    + ["term분해", "term수", "중복어", "반증", "상태", "메모"]
    # 2026-07-27: term 7 상한에 밀린 검증 키워드를 폐기하지 않고 여기 남긴다(SKILL.md §3-6).
    # 불사자 MCP에 속성·태그 저장 API가 없어 자동 반영은 불가 — 이룸님이 스마트스토어
    # 센터에서 직접 입력하는 용도다. 기존 27열 뒤에 붙였으므로 앞 열의 위치는 그대로다.
    + ["속성제안", "태그제안"]
)

# 관련어 탭 — 채택하지 않은 것까지 남긴다. 재검수의 근거이자 "안 본 것"과
# "보고 버린 것"을 구분하는 유일한 기록이다(2026-07-24 결정).
REL_TAB = "관련어"
REL_HEADER = ["상품id", "작업일", "카테고리", "관련어", "상품수", "검색량", "채택", "사유"]

# 배치 크기 — 카테고리 1개 = 배치 1개. 단 이 수를 넘으면 쪼갠다.
# 카테고리교정 846건에서 검증된 청크 크기이고, 한 컨텍스트에서 상품을 너무 많이
# 순차 처리하면 뒤로 갈수록 앞의 판단에 끌려간다.
MAX_PER_BATCH = 10

_PROJECT_ROOT = os.path.normpath(os.path.join(SKILLS_DIR, "..", ".."))
VENV_PYTHON = os.path.join(_PROJECT_ROOT, ".venv", "Scripts", "python.exe")


def _py():
    return VENV_PYTHON if os.path.exists(VENV_PYTHON) else sys.executable


def _run(args, label, timeout=None):
    """서브 스크립트 실행. stdout은 흘려보내고, 실패 시 중단."""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        r = subprocess.run(args, env=env, capture_output=True, text=True,
                           encoding="utf-8", timeout=timeout)
    except OSError as e:
        raise RuntimeError(f"{label} 실행 실패(프로세스 시작 불가): {e}")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{label} 시간 초과({timeout}s)")
    if r.stdout:
        print(r.stdout)
    if r.returncode != 0:
        if r.stderr:
            print(r.stderr, file=sys.stderr)
        raise RuntimeError(f"{label} 실패 (returncode={r.returncode})")
    if r.stderr:
        print(r.stderr, file=sys.stderr)
    return r.stdout


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _dump(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def resolve_sheet(args):
    """기록 대상 스프레드시트 id를 확정한다.

    --sheet 를 직접 준 경우 그대로, 아니면 --group-name 으로 카테고리교정 폴더에서
    '카테고리교정_<그룹명>' 시트를 찾는다. 못 찾으면 즉시 중단 —
    엉뚱한 그룹 로그에 상품명이 섞이는 것보다 멈추는 게 낫다.
    """
    if getattr(args, "sheet", None):
        return args.sheet
    group_name = (getattr(args, "group_name", "") or "").strip()
    if not group_name:
        raise RuntimeError("--sheet 또는 --group-name 중 하나는 필요합니다 "
                           "(그룹명으로 '카테고리교정_<그룹>' 시트를 찾습니다).")

    name = f"{SHEET_PREFIX}{group_name}"

    def _find(clause):
        q = f"'{CATFIX_FOLDER}' in parents and {clause} and trashed = false"
        try:
            d = sheet_io._run_gws(["drive", "files", "list", "--params",
                                   json.dumps({"q": q, "fields": "files(id,name)"},
                                              ensure_ascii=False)])
        except Exception as e:
            raise RuntimeError(f"시트 조회 실패({name}): {e}")
        return d.get("files", [])

    # 정확일치 우선. 초기에 만든 시트 중 '25-2_카테고리교정_5번_용쌤25-2' 처럼
    # 접두가 붙은 예외가 있어 못 찾으면 부분일치로 한 번 더 찾는다.
    files = _find(f"name = '{name}'") or _find(f"name contains '{name}'")
    if not files:
        raise RuntimeError(
            f"'{name}' 시트를 카테고리교정 폴더에서 찾지 못했습니다. "
            f"그룹명을 확인하거나 --sheet 로 직접 지정하세요.")
    if len(files) > 1:
        names = ", ".join(f["name"] for f in files)
        raise RuntimeError(f"'{name}' 에 걸리는 시트가 {len(files)}개입니다({names}) "
                           f"— --sheet 로 직접 지정하세요.")
    print(f"  시트: {files[0]['name']} ({files[0]['id']})")
    return files[0]["id"]


def _done_ids(sheet, tab=None):
    """상품명 탭 A열의 처리완료 id 집합. 탭이 아직 없으면 빈 집합(최초 실행)."""
    try:
        return sheet_io.read_done_ids(sheet, tab or NAME_TAB)
    except Exception as e:
        print(f"  (재개 조회 생략 — 탭 미존재로 간주: {str(e)[:80]})")
        return set()


def _read_jk_map(sheet, tab=CATFIX_TAB):
    """카테고리교정 시트에서 productId별 J(실물판정)·K(썸네일URL)을 읽는다.

    A열=상품id, J열=실물판정, K열=썸네일URL. 카테고리 교정 v1.7.0~ 이 남긴 값이다.
    구버전 그룹은 J·K가 통째로 비어 있다(그 경우 상품명 스킬이 직접 판정 후 J열을 backfill).
    시트/탭이 없으면 빈 맵(치명적이지 않음 — 증거 4종으로 직접 판정하면 된다).
    """
    if not sheet:
        return {}
    from eroomlib.gsheets import sheets_get  # noqa: E402
    try:
        rows = sheets_get(sheet, f"'{tab}'!A2:K")
    except Exception as e:
        print(f"  (카테고리 J·K 조회 생략 — {str(e)[:80]})")
        return {}
    m = {}
    for r in rows:
        r = list(r) + [""] * (11 - len(r))  # A~K = 11열
        pid = str(r[0]).strip()
        if not pid:
            continue
        m[pid] = {"실물판정": str(r[9]).strip(), "썸네일URL": str(r[10]).strip()}
    return m


def _backfill_jcol(sheet, tab, updates):
    """구버전 그룹의 빈 J열에 상품명 스킬이 판정한 실물을 되쓴다.

    updates = {productId: 실물판정}. 카테고리 시트 A열에서 행번호를 찾아 J{row} 한 셀만
    update 한다 — sheet_log 의 B:K 통짜 덮어쓰기와 달리 다른 열(B~I·K)을 건드리지 않는다.
    """
    if not sheet or not updates:
        return 0
    from eroomlib.gsheets import sheets_get, sheets_update  # noqa: E402
    try:
        col_a = sheets_get(sheet, f"'{tab}'!A2:A")
    except Exception as e:
        print(f"  (J열 backfill 생략 — A열 조회 실패: {str(e)[:80]})")
        return 0
    row_of = {}
    for i, r in enumerate(col_a):
        pid = str(r[0]).strip() if r else ""
        if pid and pid not in row_of:
            row_of[pid] = i + 2  # 헤더 1행
    n = 0
    for pid, ident in updates.items():
        row = row_of.get(pid)
        if not row or not str(ident).strip():
            continue
        try:
            sheets_update(sheet, f"'{tab}'!J{row}", [[ident]])
            n += 1
        except Exception as e:
            print(f"  J열 backfill 실패({pid}): {str(e)[:80]}", file=sys.stderr)
    return n


def _load_pooled_targets(path):
    """targets_<작업>.json → pending 형식([{productId, 상품명}])으로 변환.
    상품명은 빈 문자열 — 3단계 workdata(스냅샷 적중)가 실명으로 채운다."""
    data = _load(path)
    return [{"productId": t["productId"], "상품명": ""} for t in data.get("targets", [])]


def _route_by_sheet(rows_by_pid, sheet_map):
    """{pid: 행} → {sheetId: [행...]}. sheet_map 에 없거나 시트가 빈 pid 는 즉시 중단
    (조용히 다른 시트로 가면 로그 오염 — SKILL.md '못 찾으면 즉시 중단'과 같은 계약)."""
    out = {}
    for pid, row in rows_by_pid.items():
        ent = sheet_map.get(pid) or {}
        sid = (ent.get("sheet") or "").strip()
        if not sid:
            raise RuntimeError(f"sheet_map 에 시트가 없는 상품: {pid}")
        out.setdefault(sid, []).append(row)
    return out


# ---------------------------------------------------------------------------
# prep
# ---------------------------------------------------------------------------

def cmd_prep(args):
    run_dir = os.path.abspath(args.run_dir)
    os.makedirs(run_dir, exist_ok=True)
    py = _py()

    # 뷰·배치만 다시 만든다 (cat_view 규칙을 고친 뒤 재생성할 때. MCP·통다운을 다시 안 탄다)
    if getattr(args, "views_only", False):
        targets_path = os.path.join(run_dir, "targets.json")
        if not os.path.exists(targets_path):
            raise RuntimeError(f"targets.json이 없습니다({targets_path}) — prep을 먼저 돌리세요.")
        targets = _load(targets_path)
        skipped = _load(os.path.join(run_dir, "skipped.json")) \
            if os.path.exists(os.path.join(run_dir, "skipped.json")) else []
        wd_path = os.path.join(run_dir, "workdata.json")
        wd_by_id = {w.get("productId"): w for w in _load(wd_path)} \
            if os.path.exists(wd_path) else {}
        jk_path = os.path.join(run_dir, "jk_map.json")
        jk_by_id = _load(jk_path) if os.path.exists(jk_path) else {}
        print(f"[views-only] 대상 {len(targets)}건으로 뷰·배치 재생성")
        _tm = _restore_thumb_map(run_dir)
        _shrink_thumbs(_tm.values(), args.thumb_px)  # 기존 원본 썸네일도 여기서 축소된다
        _build_views_and_batches(run_dir, targets, _tm,
                                 args.no_parent, len(skipped),
                                 wd_by_id=wd_by_id, jk_by_id=jk_by_id)
        return

    targets_json = getattr(args, "targets_json", None)
    if not targets_json and not args.group_id:
        raise RuntimeError("--group-id 또는 --targets-json 중 하나는 필요합니다.")
    if targets_json and (args.group_id or args.ids or args.redo):
        # 대표는 targets 산출이 이미 미착수로 골라낸 것이라 단건 애드혹 경로(--ids/--redo)와
        # 단일 그룹 경로(--group-id)가 조용히 뒤섞이면 안 된다(피어리뷰 지적: 무시되던 결함).
        raise RuntimeError("--targets-json 은 --group-id/--ids/--redo 와 함께 쓸 수 없습니다.")

    group_path = os.path.join(run_dir, "group.json")
    workdata_path = os.path.join(run_dir, "workdata.json")
    targets_path = os.path.join(run_dir, "targets.json")
    thumbs_json = os.path.join(run_dir, "thumbs.json")
    thumbs_dir = os.path.join(run_dir, "thumbs")

    sheet_map = {}
    if targets_json:
        # 유니크 풀링(대량다듬기 M3b): 단계 1(collect_group)·단계 2(done_ids 대조)를
        # 건너뛴다 — 대표는 targets 산출(inventory.py targets)이 이미 미착수로 골라낸
        # 것이라 시트 재개 판정이 불필요하다. 그룹 경계가 없어 여러 그룹의 대표가
        # 한 run-dir 에 풀링된다(배치 밀도 개선, 팬아웃-비용.md).
        sheet_map_path = getattr(args, "sheet_map", None)
        if not sheet_map_path:
            raise RuntimeError("--targets-json 은 --sheet-map 과 함께 써야 합니다.")
        sheet_map = _load(sheet_map_path)
        _dump(os.path.join(run_dir, "sheet_map.json"), sheet_map)  # append가 같은 파일을 쓰도록
        pending = _load_pooled_targets(targets_json)
        if args.limit:
            pending = pending[: args.limit]
            print(f"  --limit {args.limit} 적용 → {len(pending)}건")
        print(f"[1-2/6] 유니크 풀링 대상 {len(pending)}건 (targets-json)")
        if not pending:
            print("처리할 상품이 없습니다.")
            return
        _dump(os.path.join(run_dir, "pending.json"), pending)
    else:
        # 1) 마켓그룹 → 상품목록
        if os.path.exists(group_path) and not args.force:
            print(f"[1/6] group.json 재사용 ({group_path})")
        else:
            print(f"[1/6] 마켓그룹 {args.group_id} 상품목록 수집 중...")
            _run([py, os.path.join(BULSAJA_SCRIPTS, "collect_group.py"),
                  "--group-id", str(args.group_id), "-o", group_path], "collect_group.py")
        group = _load(group_path)

        # --ids: 특정 상품만. 1건~몇 건 애드혹 작업용(신규 상품 건별 등록·보류 재작업).
        want = set()
        if args.ids:
            want = {i.strip() for i in args.ids if i.strip()}
            group = [g for g in group if g.get("productId") in want]
            print(f"  --ids {len(want)}건 지정 → 그룹에서 {len(group)}건 매칭")
            missing = want - {g.get("productId") for g in group}
            if missing:
                print(f"  [경고] 마켓그룹에 없는 상품id {len(missing)}건: {', '.join(sorted(missing))}")

        if args.limit:
            group = group[: args.limit]
            print(f"  --limit {args.limit} 적용 → {len(group)}건")

        # 2) 이미 처리된 상품 제외 (상품명 탭 A열 = 상태 저장소)
        done_ids = set() if args.no_resume else _done_ids(args.sheet, args.tab)
        # --redo: 카테고리가 바뀌어 상품명을 다시 만들어야 하는 건. A열에 이미 있어도 재대상으로 넣는다.
        # 옛 행은 지우지 않는다 — E열 원본상품명이 되돌리기 경로다(SKILL.md §재교정).
        if args.redo:
            if not want:
                print("[중단] --redo 는 --ids 와 함께만 쓴다(전건 재작업 방지).")
                return
            redo_hit = want & done_ids
            done_ids = done_ids - want
            if redo_hit:
                print(f"  --redo: 이미 기록된 {len(redo_hit)}건을 재대상으로 넣습니다 "
                      f"→ {', '.join(sorted(redo_hit))}")
                print("  [필수] 시트의 옛 행 상태를 `재작업(카테고리변경)` 으로 바꿔두세요 — "
                      "안 그러면 rename이 옛 상품명도 함께 반영합니다.")
            _dump(os.path.join(run_dir, "redo.json"), sorted(want))

        pending = [g for g in group if g.get("productId") not in done_ids]
        print(f"[2/6] 그룹 {len(group)}건 / 이미처리 {len(done_ids)}건 / 대상 {len(pending)}건")
        if not pending:
            print("처리할 상품이 없습니다.")
            return
        _dump(os.path.join(run_dir, "pending.json"), pending)

    # 3) workdata — 현재 카테고리 + 썸네일 (대화 밖에서 소비)
    if os.path.exists(workdata_path) and not args.force:
        print(f"[3/6] workdata.json 재사용 ({workdata_path})")
    else:
        print(f"[3/6] 카테고리·썸네일 조회 중 ({len(pending)}건, 시간 소요)...")
        # 조회는 공용 스냅샷을 먼저 본다(카테고리 교정이 이미 받아둔 그룹이면 MCP 0회).
        # --force = 캐시 무시하고 재수집 → 스냅샷도 함께 무시한다.
        _run([py, os.path.join(BULSAJA_SCRIPTS, "bulsaja_mcp.py"), "workdata",
              "--input", os.path.join(run_dir, "pending.json"),
              "--output", workdata_path, "--sleep", str(args.sleep)]
             + (["--refresh"] if args.force else []),
             "bulsaja_mcp.py workdata")
    workdata = _load(workdata_path)
    wd_by_id = {w.get("productId"): w for w in workdata}

    # 3b) 카테고리교정 시트 J·K — 실물판정·썸네일URL. 있으면 배치에 실어 재활용,
    #     없으면(구버전 그룹) 상품명 스킬이 증거 4종으로 직접 판정한다.
    #     풀링 모드는 대표가 여러 그룹 시트에 흩어져 있으므로 시트별로 조회해 합친다.
    #     --limit 이후의 pending 에 실제 등장하는 시트만 읽는다(피어리뷰 지적 —
    #     sheet_map 전체를 읽으면 --limit 파일럿에서도 최대 52시트를 다 훑게 된다).
    if sheet_map:
        pending_sids = sorted({(sheet_map.get(p["productId"]) or {}).get("sheet")
                               for p in pending} - {None, ""})
        jk_by_id = {}
        for sid in pending_sids:
            jk_by_id.update(_read_jk_map(sid, CATFIX_TAB))
    else:
        jk_by_id = _read_jk_map(args.sheet, CATFIX_TAB)
    _dump(os.path.join(run_dir, "jk_map.json"), jk_by_id)
    n_ident = sum(1 for v in jk_by_id.values() if v.get("실물판정"))
    n_kurl = sum(1 for v in jk_by_id.values() if v.get("썸네일URL"))
    print(f"  카테고리 J·K: 실물판정 {n_ident}건 / 썸네일URL {n_kurl}건")

    # 4) targets.json 조립 — 카테고리 미설정은 대상에서 제외(스킵 마커로 남김)
    targets, skipped = [], []
    for g in pending:
        pid = g.get("productId")
        wd = wd_by_id.get(pid) or {}
        # 가결정 우선 — 세로 러너(onestep)가 상품 단위 게이트를 쓸 때, 카테고리는
        # 승인 전이라 불사자에 아직 저장되지 않았지만 키워드 선택은 그 값으로 해야 한다.
        # (스냅샷 `가결정카테고리`. 가로 배치에는 이 필드가 없으므로 동작 변화 없음)
        cat = (wd.get("가결정카테고리") or wd.get("기존카테고리") or "").strip()
        name = (wd.get("상품명") or g.get("상품명") or "").strip()
        if not cat or cat == "미설정":
            skipped.append({"productId": pid, "상품명": name, "사유": "카테고리미설정"})
            continue
        targets.append({
            "productId": pid,
            "상품명": name,
            "대표키워드": "",          # 마켓그룹 진입점에는 없음 (cat_prefilter는 카테고리만 사용)
            "카테고리": cat,
            "썸네일": (wd.get("썸네일") or [])[:1],
        })
    _dump(targets_path, targets)
    _dump(os.path.join(run_dir, "skipped.json"), skipped)
    print(f"[4/6] 대상 {len(targets)}건 / 카테고리미설정 스킵 {len(skipped)}건 -> {targets_path}")
    if not targets:
        print("카테고리가 설정된 상품이 없습니다. 카테고리 교정을 먼저 하세요.")
        return

    # 5) 썸네일 다운로드 — K열(썸네일URL)이 이미 있는 상품은 건너뛴다.
    #    신버전 그룹은 카테고리 교정이 이미 실물을 판정(J열)했으므로 썸네일은 확인용이고,
    #    필요할 때만 배치의 썸네일URL 로 받으면 된다(전건 다운로드 5~8분 절약).
    #    구버전 그룹은 K열이 비어 있어 그대로 전건 다운로드된다(직접 판정에 필요).
    thumb_items = [{"productId": t["productId"], "url": t["썸네일"][0]}
                   for t in targets
                   if t.get("썸네일")
                   and not jk_by_id.get(t["productId"], {}).get("썸네일URL")]
    _dump(thumbs_json, thumb_items)
    thumb_map = {}
    if args.skip_thumbs:
        print("[5/6] --skip-thumbs: 썸네일 다운로드 건너뜀")
    elif not thumb_items:
        print("[5/6] 썸네일 URL이 있는 상품이 없습니다.")
    else:
        print(f"[5/6] 썸네일 {len(thumb_items)}장 다운로드 중...")
        os.makedirs(thumbs_dir, exist_ok=True)
        out = _run([py, os.path.join(BULSAJA_SCRIPTS, "fetch_thumbs.py"),
                    "--input", thumbs_json, "--out-dir", thumbs_dir], "fetch_thumbs.py")
        # fetch_thumbs 는 입력 순서대로 한 줄씩(성공=절대경로 / 실패='FAIL\t...') 출력한다.
        # 파일명은 productId 를 24자로 잘라 쓰므로(불사자 id는 27자) 이름 매칭이 아니라
        # 출력 줄 순서로 매핑한다.
        lines = [ln for ln in (out or "").splitlines() if ln.strip()]
        for i, ln in enumerate(lines):
            if i >= len(thumb_items) or ln.startswith("FAIL"):
                continue
            if os.path.exists(ln.strip()):
                thumb_map[thumb_items[i]["productId"]] = os.path.abspath(ln.strip())
        print(f"  로컬 확보: {len(thumb_map)}/{len(thumb_items)}장")
        _shrink_thumbs(thumb_map.values(), args.thumb_px)

    # 6) 카테고리 프리필터 + 계단 후보 청크
    raw_dir = args.raw_dir
    if not raw_dir:
        if not args.source_date:
            raise RuntimeError("--raw-dir 또는 --source-date 중 하나는 필요합니다.")
        base = os.path.join(_cfg.cfg("paths.sellerlife_runs"), args.source_date)
        # 통다운 레이아웃이 회차마다 다르다: 예전 것은 `<날짜>/raw/`에 풀려 있고,
        # 셀러라이프 스킬이 받은 최근 것은 `<날짜>/` 바로 아래에 xlsx + zip 이 있다.
        # raw/ 가 없으면 날짜 폴더 자체를 쓴다(cat_prefilter 가 zip 을 자동 탐색한다).
        raw_dir = os.path.join(base, "raw")
        if not os.path.isdir(raw_dir) and os.path.isdir(base):
            raw_dir = base
    if not os.path.isdir(raw_dir):
        raise RuntimeError(f"통다운 raw-dir가 없습니다: {raw_dir}")

    print(f"[6/7] 카테고리 프리필터 (raw-dir={raw_dir}, 통다운 스캔이라 시간 소요)...")
    pf_args = [py, os.path.join(KEYWORD_SCRIPTS, "cat_prefilter.py"),
               "--targets", targets_path, "--out-dir", run_dir, "--raw-dir", raw_dir]
    if args.zip:
        pf_args += ["--zip", args.zip]
    if not args.no_parent:
        pf_args += ["--parent-fallback"]
    _run(pf_args, "cat_prefilter.py")

    _build_views_and_batches(run_dir, targets, thumb_map, args.no_parent, len(skipped),
                             wd_by_id=wd_by_id, jk_by_id=jk_by_id)


def _shrink_thumbs(paths, max_px):
    """썸네일을 긴 변 max_px 로 축소한다 (0 이하면 건너뜀).

    비전 토큰은 픽셀수에 비례한다(대략 W*H/750). 불사자 썸네일은 1000x1000 이
    많아 1장에 ~1,330토큰인데, 워커 컨텍스트에 한 번 들어가면 그 뒤 모든 턴에서
    다시 읽히므로 실질 비용은 수만 토큰이 된다. 512px 로 줄이면 ~350토큰 —
    실물 정체 판별(§Step 3-1)에는 충분하다.
    """
    if not max_px or max_px <= 0:
        return
    try:
        from PIL import Image  # Pillow 없으면 원본 유지
    except ImportError:
        print("  (Pillow 없음 — 썸네일 축소 건너뜀. pip install Pillow 권장)")
        return
    done = saved = 0
    for p in list(paths):
        try:
            before = os.path.getsize(p)
            with Image.open(p) as im:
                if max(im.size) <= max_px:
                    continue
                im = im.convert("RGB")
                im.thumbnail((max_px, max_px), Image.LANCZOS)
                im.save(p, "JPEG", quality=85)
            done += 1
            saved += before - os.path.getsize(p)
        except Exception as e:  # 한 장 실패가 prep 전체를 막지 않는다
            print(f"  썸네일 축소 실패({os.path.basename(p)}): {e}")
    if done:
        print(f"  썸네일 축소: {done}장 → 긴 변 {max_px}px ({saved/1e6:.1f}MB 절감)")


def _restore_thumb_map(run_dir):
    """views-only 재실행용 — thumbs/ 파일명(productId 앞 24자)으로 매핑을 복원한다."""
    thumbs_json = os.path.join(run_dir, "thumbs.json")
    thumbs_dir = os.path.join(run_dir, "thumbs")
    if not (os.path.exists(thumbs_json) and os.path.isdir(thumbs_dir)):
        return {}
    files = {}
    for fn in os.listdir(thumbs_dir):
        files[os.path.splitext(fn)[0]] = os.path.abspath(os.path.join(thumbs_dir, fn))
    out = {}
    for item in _load(thumbs_json):
        pid = item.get("productId", "")
        for stem, path in files.items():
            if pid.startswith(stem) or stem.startswith(pid[:24]):
                out[pid] = path
                break
    return out


def _same_price_options(pid, load=None):
    """판매 옵션이 **전부 같은 가격**인가 — 색상 예외 규칙(2026-07-30 이룸님)의 근거.

    이룸님 규칙: 옵션이 전부 추가금 0원이고 색상만 다르면 상품명에 컬러명을 안 넣어도 된다
    (대표옵션의 색은 썸네일이 보여주므로 대표상품 지칭이 깨지지 않는다).
    그런데 **워커는 이걸 판단할 수 없다** — 배치의 `옵션명`은 문자열 리스트뿐이고 가격이 없다
    (`snapshot.sku_evidence` 가 `text` 만 뽑는다). 그래서 여기서 계산해 배치에 싣는다.

    옵션 전량(`옵션`)은 workdata.json 투영(`snapshot.WD_FIELDS`)에서 파일 비대 때문에
    일부러 빠져 있다 → 스냅샷 레코드를 직접 읽는다(설계상 의도된 경로).

    보수적으로 판정한다 — 판매 가능한 행이 2개 미만이거나 가격이 하나라도 비면 False.
    (구분할 대상이 없거나 근거가 불완전하면 색상을 생략할 이유가 없다.)

    `load` 는 테스트 주입점(기본 `snapshot.load`).
    """
    if load is None:
        load = snapshot.load
    try:
        rec = load(pid) or {}
    except Exception:  # noqa: BLE001  스냅샷이 없거나 깨져도 prep 을 멈추지 않는다
        return False
    rows = [r for r in ((rec.get("옵션") or {}).get("판매행") or [])
            if not r.get("exclude")]
    prices = [r.get("sale_price") for r in rows]
    if len(rows) < 2 or not all(isinstance(p, (int, float)) for p in prices):
        return False
    return len(set(prices)) == 1


def _build_views_and_batches(run_dir, targets, thumb_map, no_parent, skipped_n=0,
                             wd_by_id=None, jk_by_id=None):
    """카테고리 뷰(D) 생성 + 카테고리 단위 배치.

    후보 생성기(batch_candidates)를 더 이상 쓰지 않는다 — 그 필터가 카테고리 전용어를
    죽여서 직결어가 경쟁 진입 전에 전멸했기 때문이다(2026-07-24, 상세는 SKILL.md).

    wd_by_id: workdata.json 맵(원문명·옵션명 = 가공 전 증거). jk_by_id: 카테고리교정 시트
    J·K 맵(실물판정·썸네일URL). 둘 다 배치 product dict 에 실어 상품명 스킬이 재활용한다.
    """
    wd_by_id = wd_by_id or {}
    jk_by_id = jk_by_id or {}
    manifest = _load(os.path.join(run_dir, "manifest.json"))
    print(f"[7/7] 카테고리 뷰 생성 ({len(manifest.get('categories', {}))}개)...")

    views_dir = os.path.join(run_dir, "views")
    batches_dir = os.path.join(run_dir, "batches")
    os.makedirs(views_dir, exist_ok=True)
    os.makedirs(batches_dir, exist_ok=True)

    import cat_view  # noqa: E402  (이 스킬 소유)

    tgt_by_id = {t["productId"]: t for t in targets}
    parents = manifest.get("parents", {})
    batches, view_fail = [], []

    for cat, info in sorted(manifest.get("categories", {}).items()):
        cat_xlsx = os.path.join(run_dir, info["file"].replace("/", os.sep))
        stem = os.path.splitext(os.path.basename(cat_xlsx))[0]
        view_path = os.path.join(views_dir, stem + ".txt")
        try:
            text = cat_view.render(cat_xlsx)
            with open(view_path, "w", encoding="utf-8") as f:
                f.write(text)
        except (OSError, ValueError) as e:
            view_fail.append(f"{cat}: {e}")
            continue

        # 상위 카테고리 뷰 — leaf에 직결어가 없을 때만 여는 구명줄. 항상 읽지 않는다
        parent_view = ""
        pinfo = None if no_parent else parents.get(info.get("parent") or "")
        if pinfo:
            p_xlsx = os.path.join(run_dir, pinfo["file"].replace("/", os.sep))
            p_stem = "상위_" + os.path.splitext(os.path.basename(p_xlsx))[0]
            p_path = os.path.join(views_dir, p_stem + ".txt")
            if not os.path.exists(p_path):
                try:
                    with open(p_path, "w", encoding="utf-8") as f:
                        f.write(cat_view.render(p_xlsx))
                except (OSError, ValueError):
                    p_path = ""
            parent_view = p_path

        prods = []
        for pid in info.get("productIds", []):
            t = tgt_by_id.get(pid)
            if not t:
                continue
            wd = wd_by_id.get(pid) or {}
            jk = jk_by_id.get(pid) or {}
            prods.append({
                "productId": pid,
                "원본상품명": t.get("상품명", ""),
                "카테고리": cat,
                "썸네일경로": thumb_map.get(pid, ""),      # 다운로드된 로컬(K열 있으면 비어 있음)
                # 카테고리교정이 넘긴 증거 — J열 있으면 믿고, 없으면 원문명·옵션명으로 직접 판정
                "실물판정": jk.get("실물판정", ""),          # J열. 있으면 이게 실물
                "썸네일URL": jk.get("썸네일URL", ""),        # K열. 로컬 없을 때 여기서 fetch
                "원문명": wd.get("원문명", ""),              # 중국어 원문(가공 전)
                "옵션명": wd.get("옵션명", []),              # 실제 판매 단위(가공 전)
                # 색상 예외 규칙(2026-07-30)의 유일한 기계적 근거 — 워커는 옵션 '가격'을
                # 볼 수 없으므로(배치의 `옵션명`은 문자열뿐) 여기서 계산해 넘긴다.
                "옵션동일가": _same_price_options(pid),
            })
        if not prods:
            continue

        # 카테고리 1개 = 배치 1개. 단 MAX_PER_BATCH 초과분은 쪼갠다
        def _kb(p):
            return f"{os.path.getsize(p) // 1024}KB" if p and os.path.exists(p) else ""

        for i in range(0, len(prods), MAX_PER_BATCH):
            batches.append({
                "카테고리": cat,
                "카테고리뷰": view_path,
                "카테고리파일": cat_xlsx,
                # 상위뷰는 leaf에 직결어가 없을 때만 여는 구명줄이고 leaf보다 훨씬 크다
                # (실측 평균 30KB · 최대 105KB) — 열기 전에 크기를 알 수 있게 적어둔다
                "상위뷰": parent_view,
                "뷰크기": {"leaf": _kb(view_path), "상위": _kb(parent_view)},
                "분할": f"{i // MAX_PER_BATCH + 1}/{(len(prods) - 1) // MAX_PER_BATCH + 1}",
                "products": prods[i:i + MAX_PER_BATCH],
            })

    for i, b in enumerate(batches, 1):
        _dump(os.path.join(batches_dir, f"batch_{i:03d}.json"), b)

    _dump(os.path.join(run_dir, "batches_index.json"),
          [{"batch": f"batch_{i:03d}.json", "카테고리": b["카테고리"],
            "상품수": len(b["products"]), "뷰": b["카테고리뷰"]}
           for i, b in enumerate(batches, 1)])

    covered = sum(len(b["products"]) for b in batches)
    print(f"\n###PREP### 배치 {len(batches)}개 / 대상 {len(targets)}건(배치 수록 {covered}건) / "
          f"카테고리미설정 {skipped_n}건 / 통다운밖 {len(manifest.get('not_found', []))}건")
    if view_fail:
        print(f"  뷰 생성 실패 {len(view_fail)}건:")
        for x in view_fail[:5]:
            print(f"    - {x}")
    if covered < len(targets):
        print(f"  주의: 배치에 안 실린 상품 {len(targets) - covered}건 "
              f"— 통다운에 카테고리가 없거나 뷰 생성 실패분입니다")
    print(f"  배치: {batches_dir}")
    print(f"  뷰:   {views_dir}")
    print(f"  썸네일: {os.path.join(run_dir, 'thumbs')} (배치 수록 "
          f"{sum(1 for b in batches for p in b['products'] if p.get('썸네일경로'))}건)")


# ---------------------------------------------------------------------------
# append
# ---------------------------------------------------------------------------

def _kw_stat(p, kw):
    """관련어 목록에서 그 키워드의 (상품수, 검색량)을 찾는다. 없으면 빈칸."""
    for r in p.get("관련어") or []:
        if str(r.get("키워드", "")).strip() == kw:
            return r.get("상품수", ""), r.get("검색량", "")
    return "", ""


def _build_row(p, group_name):
    """named 상품 1건 -> 상품명 탭 행 (NAME_HEADER 순서)."""
    terms = p.get("term분해") or []
    if isinstance(terms, list):
        terms = " / ".join(str(t) for t in terms)
    kws = list(name_check.collect_keywords(p)) + [""] * MAX_KW_COLS
    row = [
        p.get("productId", ""),
        date.today().isoformat(),
        group_name,
        p.get("카테고리", ""),
        p.get("원본상품명", ""),
        p.get("새상품명", ""),
    ]
    for k in kws[:MAX_KW_COLS]:
        pc, sv = _kw_stat(p, k) if k else ("", "")
        row += [k, pc, sv]
    row += [
        terms,
        p.get("term수", ""),
        p.get("중복어", ""),
        str(p.get("반증", ""))[:200],
        p.get("상태", ""),
        p.get("메모", ""),
        _joinlist(p.get("속성제안")),
        _joinlist(p.get("태그제안")),
    ]
    return row


def _extend_header(sheet, tab, header):
    """이미 있는 탭의 헤더가 짧으면 뒤에 빠진 열만 채운다.

    `ensure_tab` 은 탭이 없을 때만 헤더를 쓴다 — 기존 그룹 시트(27열)에 나중에 추가된
    속성제안·태그제안(28·29) 헤더가 안 생긴다. 값은 A:AC 통째로 append 되므로
    헤더만 맞춰주면 그 뒤로는 자동으로 채워진다. 앞 열은 절대 건드리지 않는다.
    """
    from eroomlib.gsheets import sheets_get, sheets_update  # noqa: E402
    try:
        cur = (sheets_get(sheet, f"'{tab}'!1:1") or [[]])[0]
    except Exception as e:
        print(f"  [경고] 헤더 확인 실패({tab}): {e} — 헤더 확장을 건너뜁니다")
        return
    if len(cur) >= len(header):
        return
    # 겹치는 구간이 다르면 열 순서가 어긋난 시트다 — 손대지 않고 사람이 보게 한다.
    if cur != header[:len(cur)]:
        print(f"  [경고] {tab} 헤더가 예상과 다릅니다(기존 {len(cur)}열). 확장하지 않습니다.")
        return
    start = _col_letter(len(cur) + 1)
    missing = header[len(cur):]
    try:
        sheets_update(sheet, f"'{tab}'!{start}1", [missing])
        print(f"  헤더 확장: {tab} +{len(missing)}열 ({', '.join(missing)})")
    except Exception as e:
        print(f"  [경고] 헤더 확장 실패({tab}): {e}")


def _joinlist(v):
    """워커가 리스트로 줄 수도, 문자열로 줄 수도 있다 — 둘 다 받는다."""
    if not v:
        return ""
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x) for x in v if str(x).strip())
    return str(v)[:500]


def _build_rel_rows(p):
    """관련어 탭 행 — 채택하지 않은 것까지 전부. 재검수의 근거."""
    rows = []
    today = date.today().isoformat()
    adopted = {k for k in name_check.collect_keywords(p)}
    for r in p.get("관련어") or []:
        kw = str(r.get("키워드", "")).strip()
        if not kw:
            continue
        rows.append([
            p.get("productId", ""), today, p.get("카테고리", ""),
            kw, r.get("상품수", ""), r.get("검색량", ""),
            "O" if kw in adopted else "",
            r.get("사유", ""),
        ])
    return rows


def _mark_matrix(sheet, status_by_id):
    """현황판(00_진행)의 `상품명` 열을 상태값으로 갱신한다.

    매트릭스는 원장(상품명 탭)의 파생본이라, 실패해도 작업 결과에 영향이 없다
    (`matrix.py rebuild` 로 언제든 원장에서 다시 만든다). 그래서 예외를 삼킨다.
    """
    vals = {pid: matrix.map_name(st) for pid, st in status_by_id.items() if pid}
    if not sheet or not vals:
        return 0
    try:
        n = matrix.mark_many(sheet, "상품명", vals)
        print(f"  현황판({matrix.TAB}) 상품명: {n}칸 갱신")
        return n
    except Exception as e:  # noqa: BLE001
        print(f"  [경고] 현황판 갱신 실패: {str(e)[:120]}", file=sys.stderr)
        return 0


def _handoff_base_suffix(sheet, ok_ids, load=None, flag=None):
    """상품명엔 `기본형` 이 붙었는데 대표옵션명엔 없는 상품을 옵션 단계로 넘긴다.

    왜 필요한가 (2026-07-30 이룸님 결정 3·6): 마커는 신규 처리분에만 적용하고 기존
    완료건은 소급하지 않는다. 그런데 두 스킬은 각자 다른 날 돈다 — **옵션은 이미 옛
    규칙으로 끝났고 상품명만 이번에 도는 상품**이 생긴다(용쌤1-1 등 실제로 많다).
    그 상품은 상품명만 `…기본형` 이고 옵션 목록에는 그 단어가 없어 **짝이 깨진다.**
    고객이 어느 옵션이 기본인지 못 찾는다.

    그래서 현황판 `옵션` 열에 재작업 플래그만 찍는다(기존 이관 메커니즘 재사용).
    나중에 옵션명만 가볍게 보완하면 된다.

    - **append 가 아니라 rename 성공 후**에 부른다 — append 시점의 상품명은 아직 불사자
      미반영이라, rename 이 실패하면 불필요한 플래그가 남는다.
    - **옵션이 아예 없는 상품(단일상품)은 제외** — 마커를 붙일 대상이 없다.
    - 현황판은 원장의 파생본이라 실패해도 반영 결과에 영향이 없다 → 예외를 삼킨다.

    `load`·`flag` 는 테스트 주입점(기본 `snapshot.load` / `matrix.flag_many`).
    """
    if not sheet or not ok_ids:
        return 0
    if load is None:
        load = snapshot.load
    if flag is None:
        flag = matrix.flag_many
    need = {}
    for pid in ok_ids:
        try:
            rec = load(pid) or {}
        except Exception:  # noqa: BLE001
            continue
        rows = (rec.get("옵션") or {}).get("판매행") or []
        if not rows:
            continue                      # 옵션 없는 단일상품 — 보완할 대상이 없다
        main = next((r for r in rows if r.get("main_product")), None)
        if main is None:
            # 대표가 아직 안 세워짐 = 옵션 단계를 안 거쳤다. 그 단계가 오면 마커를 붙인다.
            continue
        if not str(main.get("text") or "").strip().endswith(name_check.BASE_SUFFIX):
            need[pid] = f"상품명에 {name_check.BASE_SUFFIX} 부착 — 대표옵션명 보완 필요"
    if not need:
        return 0
    try:
        n = flag(sheet, "옵션", need, from_task="상품명")
        print(f"  현황판({matrix.TAB}) 옵션 재작업 플래그: {n}칸 "
              f"(상품명에만 {name_check.BASE_SUFFIX}이 붙은 상품)")
        return n
    except Exception as e:  # noqa: BLE001
        print(f"  [경고] 옵션 이관 플래그 실패: {str(e)[:120]}", file=sys.stderr)
        return 0


def _cmd_append_pooled(args, run_dir, checked_dir):
    """--sheet-map 지정 시: 행을 상품 소속 그룹 시트로 라우팅해 append(대량다듬기 M3b).

    name_check(1단계)는 호출자가 이미 실행했다. 여기는 시트별 ensure_tab·done_ids·append·
    J backfill·현황판 갱신을 그룹 시트 단위로 되풀이한다 — 기존 단일 시트 로직과 동등하게,
    시트가 여러 개일 뿐이다. 기존 단일 시트 경로(cmd_append 본체)는 이 함수와 무관하게
    그대로 남아 있다(회귀 byte 동일 보장).
    """
    sheet_map = _load(getattr(args, "sheet_map"))
    jk_path = os.path.join(run_dir, "jk_map.json")
    jk_map = _load(jk_path) if os.path.exists(jk_path) else {}
    redo_path = os.path.join(run_dir, "redo.json")
    redo_ids = set(_load(redo_path)) if os.path.exists(redo_path) else set()

    # 전 청크 + 스킵 마커에서 pid별 (행·관련어행·실물판정·그룹명·상태) 를 먼저 모은다.
    entries = {}
    for cf in sorted(glob.glob(os.path.join(checked_dir, "checked_*.json"))):
        data = _load(cf)
        for p in data.get("products", []):
            pid = p.get("productId", "")
            if not pid:
                continue
            group_name = (sheet_map.get(pid) or {}).get("그룹명", "")
            entries[pid] = {
                "row": _build_row(p, group_name),
                "rel_rows": _build_rel_rows(p),
                "ident": str(p.get("실물판정", "")).strip(),
                "상태": p.get("상태", ""),
            }

    skip_path = os.path.join(run_dir, "skipped.json")
    skipped = _load(skip_path) if os.path.exists(skip_path) else []
    for s in skipped:
        pid = s.get("productId", "")
        if not pid or pid in entries:
            continue
        group_name = (sheet_map.get(pid) or {}).get("그룹명", "")
        r = [""] * len(NAME_HEADER)
        r[0], r[1], r[2] = pid, date.today().isoformat(), group_name
        r[4] = s.get("상품명", "")
        i_status = NAME_HEADER.index("상태")
        r[i_status] = f"스킵({s.get('사유', '')})"
        entries[pid] = {"row": r, "rel_rows": [], "ident": "", "상태": r[i_status]}

    rows_by_pid = {pid: e["row"] for pid, e in entries.items()}
    grouped = _route_by_sheet(rows_by_pid, sheet_map)

    total, rel_total = 0, 0
    backfill_by_sheet, matrix_by_sheet = {}, {}
    for sid, _rows in grouped.items():
        # sid 는 _route_by_sheet 가 strip() 한 값이다 — 여기 비교도 strip 해야
        # sheet_map 값에 공백이 섞였을 때 조용히 0건으로 걸러지지 않는다(피어리뷰 지적).
        pids_here = [pid for pid in entries
                     if ((sheet_map.get(pid) or {}).get("sheet") or "").strip() == sid]
        if not args.dry_run:
            if sheet_io.ensure_tab(sid, args.tab, NAME_HEADER):
                print(f"  탭 신설: {args.tab} ({sid})")
            else:
                _extend_header(sid, args.tab, NAME_HEADER)
            if not args.no_related and sheet_io.ensure_tab(sid, REL_TAB, REL_HEADER):
                print(f"  탭 신설: {REL_TAB} ({sid})")

        done_ids = (_done_ids(sid, args.tab) - redo_ids) if not args.dry_run else set()
        rows_final, rel_rows_final = [], []
        for pid in pids_here:
            if pid in done_ids:
                print(f"  스킵(이미처리): {pid}")
                continue
            e = entries[pid]
            if e["ident"] and not (jk_map.get(pid) or {}).get("실물판정"):
                backfill_by_sheet.setdefault(sid, {})[pid] = e["ident"]
            rows_final.append(e["row"])
            rel_rows_final += e["rel_rows"]
            matrix_by_sheet.setdefault(sid, {})[pid] = e["상태"]

        if not rows_final:
            continue
        if args.dry_run:
            print(f"--- 시트 {sid} (dry-run, {len(rows_final)}행 / 관련어 {len(rel_rows_final)}행) ---")
            for r in rows_final:
                print(json.dumps(r, ensure_ascii=False))
        else:
            total += sheet_io.append_rows(sid, args.tab, rows_final)
            if rel_rows_final and not args.no_related:
                rel_total += sheet_io.append_rows(sid, REL_TAB, rel_rows_final)
            print(f"  시트 {sid}: {len(rows_final)}행 (관련어 {len(rel_rows_final)}행)")

    if not args.dry_run:
        for sid, updates in backfill_by_sheet.items():
            n = _backfill_jcol(sid, CATFIX_TAB, updates)
            print(f"  J열 backfill: {n}/{len(updates)}건 (시트 {sid})")
        for sid, updates in matrix_by_sheet.items():
            _mark_matrix(sid, updates)
        if redo_ids:
            try:
                os.replace(redo_path, redo_path + ".done")
                print(f"  재작업 면제 소진: redo.json → redo.json.done ({len(redo_ids)}건)")
            except OSError as e:
                print(f"  [경고] redo.json 소진 실패: {e}")
        print(f"###APPEND### 총 {total}행(풀링, {len(grouped)}개 시트) / 관련어 {rel_total}행")


def cmd_append(args):
    run_dir = os.path.abspath(args.run_dir)
    named_files = sorted(glob.glob(os.path.join(run_dir, "named", "named_*.json")))
    if not named_files:
        print(f"named 파일이 없습니다: {os.path.join(run_dir, 'named')}")
        return

    py = _py()
    checked_dir = os.path.join(run_dir, "checked")
    os.makedirs(checked_dir, exist_ok=True)

    # 1) 전 청크 규칙 검증
    print(f"[1/2] 규칙 검증 ({len(named_files)}청크)...")
    for nf in named_files:
        out = os.path.join(checked_dir, os.path.basename(nf).replace("named_", "checked_"))
        _run([py, os.path.join(SCRIPT_DIR, "name_check.py"),
              "--input", nf, "--output", out], f"name_check({os.path.basename(nf)})")

    if getattr(args, "sheet_map", None):
        _cmd_append_pooled(args, run_dir, checked_dir)
        return

    # 2) 시트 append
    group_name = args.group_name or ""
    if not args.dry_run:
        if sheet_io.ensure_tab(args.sheet, args.tab, NAME_HEADER):
            print(f"  탭 신설: {args.tab}")
        else:
            _extend_header(args.sheet, args.tab, NAME_HEADER)

    if not args.dry_run and not args.no_related:
        if sheet_io.ensure_tab(args.sheet, REL_TAB, REL_HEADER):
            print(f"  탭 신설: {REL_TAB}")

    # J열 backfill 준비 — prep 때 저장한 jk_map 으로 "원래 J가 비어 있던"(구버전) 건을 안다.
    # 상품명 스킬이 직접 판정한 실물을 그 빈 J열에 되쓴다(신버전 J는 덮지 않는다).
    jk_path = os.path.join(run_dir, "jk_map.json")
    jk_map = _load(jk_path) if os.path.exists(jk_path) else {}
    backfill = {}  # {productId: 실물판정}

    # prep 이 --redo 로 넣은 건은 A열에 이미 있어도 append 해야 한다(재작업 = 새 행 추가).
    redo_path = os.path.join(run_dir, "redo.json")
    redo_ids = set(_load(redo_path)) if os.path.exists(redo_path) else set()
    if redo_ids:
        print(f"  재작업 대상 {len(redo_ids)}건 — 이미처리 판정에서 제외합니다")

    total, rel_total = 0, 0
    print("[2/2] 시트 append...")
    for cf in sorted(glob.glob(os.path.join(checked_dir, "checked_*.json"))):
        data = _load(cf)
        done_ids = _done_ids(args.sheet, args.tab) - redo_ids  # 직전 재조회(이중실행 방어)
        rows, rel_rows = [], []
        for p in data.get("products", []):
            pid = p.get("productId", "")
            if pid in done_ids:
                print(f"  스킵(이미처리): {pid}")
                continue
            # 구버전(J열 비었던) 건이고 이번에 실물을 판정했으면 backfill 대상
            ident = str(p.get("실물판정", "")).strip()
            if ident and not (jk_map.get(pid) or {}).get("실물판정"):
                backfill[pid] = ident
            rows.append(_build_row(p, group_name))
            rel_rows += _build_rel_rows(p)
        if not rows:
            continue
        if args.dry_run:
            print(f"--- {os.path.basename(cf)} (dry-run, {len(rows)}행 / 관련어 {len(rel_rows)}행) ---")
            for r in rows:
                print(json.dumps(r, ensure_ascii=False))
        else:
            total += sheet_io.append_rows(args.sheet, args.tab, rows)
            if rel_rows and not args.no_related:
                rel_total += sheet_io.append_rows(args.sheet, REL_TAB, rel_rows)
            print(f"  {os.path.basename(cf)}: {len(rows)}행 (관련어 {len(rel_rows)}행)")

    # 3) 스킵 마커(카테고리미설정) — 재시도 루프 차단
    skip_path = os.path.join(run_dir, "skipped.json")
    if os.path.exists(skip_path):
        skipped = _load(skip_path)
        if skipped:
            done_ids = _done_ids(args.sheet, args.tab)
            i_status = NAME_HEADER.index("상태")
            rows = []
            for s in skipped:
                if s.get("productId") in done_ids:
                    continue
                r = [""] * len(NAME_HEADER)
                r[0] = s.get("productId", "")
                r[1] = date.today().isoformat()
                r[2] = group_name
                r[4] = s.get("상품명", "")
                r[i_status] = f"스킵({s.get('사유', '')})"
                rows.append(r)
            if rows and not args.dry_run:
                total += sheet_io.append_rows(args.sheet, args.tab, rows)
                print(f"  스킵 마커: {len(rows)}행")
            elif rows:
                print(f"--- 스킵 마커 (dry-run, {len(rows)}행) ---")

    # 4) 구버전 그룹 J열 backfill (카테고리 시트에 실물판정 되쓰기)
    if backfill:
        if args.dry_run:
            print(f"--- J열 backfill (dry-run, {len(backfill)}건) ---")
            for pid, ident in list(backfill.items())[:10]:
                print(f"  {pid} → {ident}")
            if len(backfill) > 10:
                print(f"  ... 외 {len(backfill) - 10}건")
        else:
            n = _backfill_jcol(args.sheet, CATFIX_TAB, backfill)
            print(f"  J열 backfill: {n}/{len(backfill)}건 (카테고리 시트 '{CATFIX_TAB}')")

    # 5) redo 소진 — 재작업 면제는 1회용이다. 남겨두면 append 를 다시 돌릴 때
    #    같은 상품이 또 append 되어 중복 행이 생긴다(이중실행 방어가 뚫린다).
    if redo_ids and not args.dry_run:
        try:
            os.replace(redo_path, redo_path + ".done")
            print(f"  재작업 면제 소진: redo.json → redo.json.done ({len(redo_ids)}건)")
        except OSError as e:
            print(f"  [경고] redo.json 소진 실패: {e} — append 재실행 전에 직접 지우세요")

    # 6) 현황판(00_진행) 상품명 열 갱신 — 자기 열 1개만.
    #    '생성완료'는 아직 불사자 미반영이므로 완료가 아니다(rename 이 완료로 바꾼다).
    if not args.dry_run:
        _mark_matrix(args.sheet, {
            p.get("productId", ""): p.get("상태", "")
            for cf in sorted(glob.glob(os.path.join(checked_dir, "checked_*.json")))
            for p in _load(cf).get("products", []) if p.get("productId")})

    if not args.dry_run:
        print(f"###APPEND### 총 {total}행 -> {args.tab} / 관련어 {rel_total}행 -> {REL_TAB}")
        print(f"  https://docs.google.com/spreadsheets/d/{args.sheet}/edit")


# ---------------------------------------------------------------------------
# rename
# ---------------------------------------------------------------------------

# 1-based 열번호 → A1 열문자(27→AA). 매트릭스도 같은 계산을 쓰므로 eroomlib 1벌에 둔다
# (2026-07-25 `chr('A'+26)='['` 버그가 났던 자리 — 두 벌로 두면 한쪽만 고쳐진다).
_col_letter = matrix._col_letter


# rename 호출 상한이 50건이고, 불사자는 배치 안에 '내 상품이 아닌 상품'이 1건이라도
# 있으면 배치 전체를 거부한다(2026-07-27 용쌤1-1: 불량 2건이 정상 98건을 같이 죽였다).
# 그래서 거부되면 청크를 잘게 쪼개 재시도하고, 1건 단위에서도 거부된 것만 불량으로 확정한다.
RENAME_SIZES = (50, 10, 1)


def _rename_cascade(targets, submit, sizes=RENAME_SIZES, log=None,
                    max_consecutive_errors=3):
    """계단식 분해 반영. 반환: (ok_ids, bad, errored).

    submit(chunk) -> (성공여부, 메시지). 예외를 던지면 통신 오류로 본다.
    거부(성공여부 False)된 청크는 더 작은 크기로 다시 던지고, 1건에서도 거부되면
    bad 로 확정한다. 예외는 errored 로 따로 모은다 — 통신 오류를 '상품삭제'로
    확정해버리면 멀쩡한 상품의 시트 상태를 망가뜨린다.

    예외도 분해한다(오류 원인이 특정 상품일 수 있고, 통째로 포기하면 그 배치는
    재실행마다 같은 자리에서 막힌다). 다만 통신 장애처럼 계속 터지는 상황에서
    재시도 폭풍이 되지 않도록, 오류가 max_consecutive_errors 회 연달아 나면
    남은 건은 호출 없이 errored 로 넘긴다(상태 보존 → 재실행에서 다시 잡힘).
    """
    ok, bad, errored = [], [], []
    state = {"consec": 0, "tripped": False}
    abort_msg = f"연속 오류 {max_consecutive_errors}회로 중단 — 미시도(재실행 대상)"

    def _emit(msg):
        if log:
            log(msg)

    def run(items, level):
        size = sizes[level]
        for i in range(0, len(items), size):
            chunk = items[i:i + size]
            if state["tripped"]:
                errored.extend((t["productId"], abort_msg) for t in chunk)
                continue
            try:
                success, msg = submit(chunk)
                is_err = False
            except Exception as e:                      # noqa: BLE001 (통신·MCP 오류 전부)
                success, msg, is_err = False, f"{type(e).__name__}: {e}", True
            if is_err:
                state["consec"] += 1
                if state["consec"] >= max_consecutive_errors:
                    state["tripped"] = True
                    _emit(f"  {abort_msg}")
            else:
                state["consec"] = 0
            if success:
                ok.extend(t["productId"] for t in chunk)
                _emit(f"  {len(chunk)}건 반영 (누적 {len(ok)})")
                continue
            # 같은 크기로 다시 던지지 않도록, 청크보다 작은 다음 단계를 고른다.
            # 차단이 걸린 직후면 더 쪼개지 않고, 실제 오류 메시지를 그대로 남긴다.
            nxt = None if state["tripped"] else next(
                (L for L in range(level + 1, len(sizes))
                 if sizes[L] < len(chunk)), None)
            if nxt is not None:
                _emit(f"  {len(chunk)}건 거부 → {sizes[nxt]}건씩 재시도: {str(msg)[:80]}")
                run(chunk, nxt)
            else:
                _emit(f"  {'오류' if is_err else '불량 확정'}: "
                      f"{chunk[0]['productId']} {str(msg)[:80]}")
                (errored if is_err else bad).extend(
                    (t["productId"], str(msg)) for t in chunk)

    if targets:
        run(targets, 0)
    return ok, bad, errored


def _build_status_col(rows, i_id, i_status, ok_ids, bad_ids):
    """상태열 전체를 메모리에서 고쳐 (2차원 값, 변경건수) 로 돌려준다.

    행 단위 update 를 수백 번 치지 않기 위해 열 하나를 통째로 write back 한다.
    대상이 아닌 행은 기존 값을 그대로 실어 보존한다(오류건 = 생성완료 유지 →
    재실행 시 다시 잡힌다. rename 은 멱등이라 재실행이 안전하다).

    바꾸는 건 상태='생성완료' 행뿐이다 — 반영 대상 선정 기준과 같게 둬야
    같은 상품id의 보류·스킵 행까지 덮어써 기록을 지우는 일이 없다.
    """
    col, changed = [], 0
    for r in rows:
        r = list(r)
        pid = str(r[i_id]).strip() if len(r) > i_id else ""
        cur = str(r[i_status]).strip() if len(r) > i_status else ""
        new = cur
        if pid and cur == "생성완료" and pid in ok_ids:
            new = "반영완료"
        elif pid and cur == "생성완료" and pid in bad_ids:
            new = "상품삭제(이룸님)"
        if new != cur:
            changed += 1
        col.append([new])
    return col, changed


def _writeback_status(sheet, tab, rows, ok_ids, bad_ids, update=None):
    """반영 결과를 상태열에 되쓴다. 반환: 변경된 행 수(실패 시 0).

    rows 는 cmd_rename 이 A2:{last} 로 읽은 그대로 — i번째가 시트 i+2행이다.
    update 는 테스트에서 갈아끼우기 위한 주입점(기본 eroomlib.gsheets.sheets_update).
    쓰기 실패로 반영 자체가 무효가 되진 않으므로 예외를 삼키고 0을 돌려준다.
    """
    if update is None:
        from eroomlib.gsheets import sheets_update as update  # noqa: E402
    i_id = NAME_HEADER.index("상품id")
    i_status = NAME_HEADER.index("상태")
    col_values, changed = _build_status_col(rows, i_id, i_status, ok_ids, bad_ids)
    if not changed:
        return 0
    letter = _col_letter(i_status + 1)
    rng = f"'{tab}'!{letter}2:{letter}{len(col_values) + 1}"
    try:
        update(sheet, rng, col_values)
    except Exception as e:  # noqa: BLE001
        print(f"  상태열 갱신 실패({rng}): {str(e)[:150]}", file=sys.stderr)
        return 0
    return changed


def cmd_check(args):
    """named 검증만 실행(append 1단계 분리) — Workflow 검증 스테이지가 부른다.

    시트를 전혀 안 건드린다 — name_check 만 돌려 checked/ 를 만들고 실패 요약을 찍는다.
    """
    run_dir = os.path.abspath(args.run_dir)
    named_files = sorted(glob.glob(os.path.join(run_dir, "named", "named_*.json")))
    if not named_files:
        print(f"named 파일이 없습니다: {os.path.join(run_dir, 'named')}")
        return
    py = _py()
    checked_dir = os.path.join(run_dir, "checked")
    os.makedirs(checked_dir, exist_ok=True)
    for nf in named_files:
        out = os.path.join(checked_dir, os.path.basename(nf).replace("named_", "checked_"))
        _run([py, os.path.join(SCRIPT_DIR, "name_check.py"),
              "--input", nf, "--output", out], f"name_check({os.path.basename(nf)})")

    # named_NNN 이 지워졌는데(재팬아웃으로 배치를 포기) 옛 checked_NNN 이 남아 있으면
    # 집계에서 뺀다 — 안 그러면 지워진 배치가 영원히 실패로 잡힌다(피어리뷰 지적).
    named_stems = {os.path.basename(nf)[len("named_"):-len(".json")] for nf in named_files}
    passed, failed, fail_batches = 0, 0, []
    for cf in sorted(glob.glob(os.path.join(checked_dir, "checked_*.json"))):
        stem = os.path.basename(cf)[len("checked_"):-len(".json")]
        if stem not in named_stems:
            continue
        data = _load(cf)
        has_fail = any(p.get("상태") == "검증실패" for p in data.get("products", []))
        if has_fail:
            failed += 1
            digits = "".join(c for c in os.path.basename(cf) if c.isdigit())
            fail_batches.append(int(digits) if digits else 0)
        else:
            passed += 1
    print(f"###CHECK### 통과 {passed} / 실패 {failed} / 실패배치 {fail_batches}")


def cmd_rename(args):
    """04-상품명 탭에서 상태=생성완료 건을 불사자에 실제 반영.

    --commit 없으면 대상만 출력(미리보기). rename은 50건/호출 상한.
    """
    from bulsaja_mcp import BulsajaMCP  # noqa: E402
    from eroomlib.gsheets import sheets_get  # noqa: E402

    ncol = len(NAME_HEADER)
    last = _col_letter(ncol)
    rows = sheets_get(args.sheet, f"'{args.tab}'!A2:{last}")
    i_status = NAME_HEADER.index("상태")
    i_id = NAME_HEADER.index("상품id")
    i_orig = NAME_HEADER.index("원본상품명")
    i_new = NAME_HEADER.index("새상품명")
    # --ids 지정 시 그 pid만 대상으로 좁힌다(전파가 자기 append 분만 커밋하도록 —
    # 미지정이면 필터 없이 기존 동작과 바이트 단위로 동일해야 한다).
    ids = set(getattr(args, "ids", None) or [])
    targets = []
    for r in rows:
        r = list(r) + [""] * (ncol - len(r))
        pid, orig, newname = r[i_id], r[i_orig], r[i_new]
        status = str(r[i_status]).strip()
        if not str(pid).strip() or status != "생성완료":
            continue
        if not str(newname).strip():
            continue
        if ids and str(pid).strip() not in ids:
            continue
        targets.append({"productId": str(pid).strip(),
                        "name": str(newname).strip(),
                        "원본": str(orig).strip()})

    print(f"반영 대상: {len(targets)}건 (상태=생성완료)")
    if args.limit:
        targets = targets[: args.limit]
        print(f"  --limit {args.limit} 적용 → {len(targets)}건")
    if not targets:
        return

    for t in targets[:5]:
        print(f"  {t['productId']}  {t['원본'][:28]} → {t['name']}")
    if len(targets) > 5:
        print(f"  ... 외 {len(targets) - 5}건")

    if not args.commit:
        print("\n미리보기 모드입니다. 실제 반영하려면 --commit 을 붙이세요.")
        return

    mcp = BulsajaMCP()
    mcp.open()

    def _submit(chunk):
        """청크 1개를 preview→confirm 2단계로 반영. (성공여부, 메시지)."""
        items = [{"productId": t["productId"], "name": t["name"]} for t in chunk]
        try:
            prev = mcp.call_tool("bulsaja_product_rename",
                                 {"items": items, "confirm": False})
            token = prev.get("confirmationToken")
            if not token:
                # 토큰 미발급 = 배치 거부(불량 상품 포함). 통신 오류가 아니다.
                return False, f"확인토큰 없음: {str(prev.get('message'))[:120]}"
            res = mcp.call_tool("bulsaja_product_rename",
                                {"items": items, "confirm": True,
                                 "confirmationToken": token})
            if res.get("success") is False:
                return False, str(res.get("message"))[:150]
            return True, ""
        finally:
            time.sleep(args.sleep)

    try:
        ok_ids, bad, errored = _rename_cascade(targets, _submit, log=print)
    finally:
        mcp.close()

    # 저장한 쪽이 스냅샷의 그 필드만 되쓴다 → 다음 스킬이 옛 상품명을 읽지 않는다.
    _name_by_id = {t["productId"]: t["name"] for t in targets}
    for pid in ok_ids:
        try:
            snapshot.update(pid, 상품명=_name_by_id.get(pid, ""))
        except Exception as e:  # 스냅샷 갱신 실패가 반영 결과를 뒤엎으면 안 된다
            print(f"  [경고] 스냅샷 갱신 실패({pid}): {str(e)[:80]}", file=sys.stderr)

    print(f"###RENAME### 반영 {len(ok_ids)}건 / 불량 {len(bad)}건 / 오류 {len(errored)}건")
    for pid, msg in bad:
        print(f"  불량(1건 단위에서도 거부): {pid} — {str(msg)[:100]}")
    for pid, msg in errored[:10]:
        print(f"  오류(상태 유지, 재실행 대상): {pid} — {str(msg)[:100]}", file=sys.stderr)
    if len(errored) > 10:
        print(f"  ... 외 오류 {len(errored) - 10}건", file=sys.stderr)

    # 상태열 되쓰기 — 성공=반영완료, 확정 불량=상품삭제(이룸님).
    # 오류건은 '생성완료'로 남겨 재실행에서 다시 잡히게 한다(rename 은 멱등).
    n = _writeback_status(args.sheet, args.tab, rows,
                          set(ok_ids), {pid for pid, _ in bad})
    print(f"  시트 상태열 갱신: {n}행")

    # 현황판 — 반영된 것만 완료. 불량(상품삭제)은 해당없음. 오류건은 손대지 않는다
    # (상태를 '생성완료'로 남겨 재실행에서 다시 잡히게 하는 위 원칙과 같게).
    _mark_matrix(args.sheet,
                 {**{pid: "반영완료" for pid in ok_ids},
                  **{pid: "상품삭제(이룸님)" for pid, _ in bad}})

    # 상품명엔 마커가 붙었는데 대표옵션명엔 없는 상품 → 옵션 단계로 이관(짝 복구용)
    _handoff_base_suffix(args.sheet, ok_ids)
    print(f"  https://docs.google.com/spreadsheets/d/{args.sheet}/edit")


# ---------------------------------------------------------------------------
# status — 남은 배치 나열 + 워커 분배표 (순수 파일 glob, LLM·MCP·시트 무관)
# ---------------------------------------------------------------------------

def cmd_status(args):
    """Step 3 진행 현황 — named/ 결과가 없는 배치(= 남은 일감)를 나열한다.

    `--chunks K` 를 주면 남은 배치를 K등분해 워커별 할당표(배치 파일 경로 목록)를 찍는다.
    서브에이전트가 없는 하네스(코덱스 등)에서 배치를 독립 프로세스로 나눌 때 쓴다.
    named_NNN.json 존재 = 그 배치 완료. 겹쳐 돌려도 멱등이라 안전(§SKILL Step 3 위임).
    """
    run_dir = os.path.abspath(args.run_dir)
    batches_dir = os.path.join(run_dir, "batches")
    named_dir = os.path.join(run_dir, "named")
    batch_files = sorted(glob.glob(os.path.join(batches_dir, "batch_*.json")))
    if not batch_files:
        print(f"배치가 없습니다: {batches_dir} — prep을 먼저 돌리세요.")
        return

    def _num(path):  # batch_007.json → "007"
        return os.path.splitext(os.path.basename(path))[0].split("_")[-1]

    done, pending = [], []
    for bf in batch_files:
        n = _num(bf)
        if os.path.exists(os.path.join(named_dir, f"named_{n}.json")):
            done.append(n)
        else:
            pending.append(n)

    print(f"배치 {len(batch_files)}개 / 완료 {len(done)}개 / 남음 {len(pending)}개")
    if not pending:
        print("남은 배치가 없습니다. append 로 진행하세요.")
        return
    print("남은 배치: " + ", ".join(pending))

    if args.chunks and args.chunks > 0:
        k = min(args.chunks, len(pending))
        base, rem = divmod(len(pending), k)  # 크기 차 ≤1 균등분할
        print(f"\n--chunks {args.chunks} → {k}등분 할당표 "
              f"(워커별 배치 파일 경로 — 각 워커에 references/배치-워커-프롬프트.md와 함께 준다):")
        idx = 0
        for i in range(k):
            size = base + (1 if i < rem else 0)
            grp = pending[idx:idx + size]
            idx += size
            if not grp:
                continue
            paths = [os.path.join(batches_dir, f"batch_{n}.json") for n in grp]
            print(f"  워커{i + 1} ({len(grp)}배치 {grp[0]}~{grp[-1]}):")
            for p in paths:
                print(f"    {p}")


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="상품명 배치 오케스트레이터 (파이프라인 ⑤)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("prep", help="마켓그룹 → 썸네일·카테고리·키워드후보 청크")
    p1.add_argument("--group-id", type=int, default=None,
                    help="--targets-json 과 상호배타 — 단일 그룹 진입점")
    p1.add_argument("--targets-json", default=None,
                    help="유니크 풀링 대표 목록(targets_<작업>.json). 지정하면 --group-id 불필요"
                         "(대량다듬기 M3b)")
    p1.add_argument("--sheet-map", default=None,
                    help="--targets-json 과 함께. pid→그룹시트 매핑(sheet_map.json)")
    p1.add_argument("--run-dir", required=True)
    p1.add_argument("--source-date", default=None, help="셀러라이프 통다운 YYMMDD")
    p1.add_argument("--raw-dir", default=None)
    p1.add_argument("--zip", default=None)
    p1.add_argument("--limit", type=int, default=None, help="상위 N건만 (파일럿용)")
    p1.add_argument("--ids", nargs="+", default=None,
                    help="특정 productId만 처리 (1건~몇 건 애드혹 작업용)")
    p1.add_argument("--redo", action="store_true",
                    help="--ids 와 함께. 시트에 이미 기록된 건도 재대상으로 (카테고리 변경 후 재작업)")
    p1.add_argument("--views-only", action="store_true",
                    help="기존 run-dir의 targets/manifest로 뷰·배치만 재생성 "
                         "(MCP·통다운 스캔을 다시 타지 않는다)")
    p1.add_argument("--no-parent", action="store_true",
                    help="상위 카테고리(2차 접두) 뷰를 만들지 않는다. leaf에 직결어가 없는 "
                         "상품의 구명줄이 사라지므로 평소엔 켜둔다")
    p1.add_argument("--sleep", type=float, default=0.3, help="workdata 호출 간격(초)")
    p1.add_argument("--skip-thumbs", action="store_true", help="썸네일 다운로드 생략")
    p1.add_argument("--thumb-px", type=int, default=512,
                    help="썸네일 긴 변 축소 px (0=원본 유지). 비전 토큰 ∝ 픽셀수")
    p1.add_argument("--no-resume", action="store_true", help="시트 기반 재개 무시(전건 처리)")
    p1.add_argument("--force", action="store_true", help="group/workdata 캐시 무시하고 재수집")
    p1.add_argument("--group-name", default="",
                    help="마켓그룹명. '카테고리교정_<그룹명>' 시트를 찾아 재개 판정에 쓴다")
    p1.add_argument("--sheet", default="", help="스프레드시트 id 직접 지정(그룹명 조회 대신)")
    p1.add_argument("--tab", default=NAME_TAB, help="기록할 탭 이름")
    p1.set_defaults(func=cmd_prep)

    p2 = sub.add_parser("append", help="named → 검증 → 상품명 탭 append")
    p2.add_argument("--run-dir", required=True)
    p2.add_argument("--group-name", default="",
                    help="마켓그룹명. 시트 '마켓그룹' 열에 쓰이고 대상 시트를 찾는 키")
    p2.add_argument("--dry-run", action="store_true")
    p2.add_argument("--no-related", action="store_true",
                    help="관련어 탭 기록을 생략한다(재검수 근거가 사라지므로 평소엔 쓰지 않는다)")
    p2.add_argument("--sheet", default="", help="스프레드시트 id 직접 지정(그룹명 조회 대신)")
    p2.add_argument("--sheet-map", default=None,
                    help="pid→그룹시트 매핑(sheet_map.json) — 지정하면 풀링 모드로 라우팅한다"
                         "(대량다듬기 M3b)")
    p2.add_argument("--tab", default=NAME_TAB, help="기록할 탭 이름")
    p2.set_defaults(func=cmd_append)

    p3 = sub.add_parser("rename", help="시트 생성완료 건을 불사자에 반영")
    p3.add_argument("--run-dir", required=True)
    p3.add_argument("--commit", action="store_true", help="실제 반영(없으면 미리보기)")
    p3.add_argument("--ids", nargs="+", default=None,
                    help="지정 시 이 상품id들만 대상(전파가 자기 append 분만 커밋할 때 사용)")
    p3.add_argument("--limit", type=int, default=None)
    p3.add_argument("--sleep", type=float, default=1.0)
    p3.add_argument("--group-name", default="", help="마켓그룹명(시트 조회 키)")
    p3.add_argument("--sheet", default="", help="스프레드시트 id 직접 지정(그룹명 조회 대신)")
    p3.add_argument("--tab", default=NAME_TAB, help="기록할 탭 이름")
    p3.set_defaults(func=cmd_rename)

    p4 = sub.add_parser("status", help="남은 배치 나열 + 워커 분배표(파일 glob, 시트 무관)")
    p4.add_argument("--run-dir", required=True)
    p4.add_argument("--chunks", type=int, default=None,
                    help="남은 배치를 K등분해 워커별 배치경로 할당표를 찍는다(코덱스 등 다중 프로세스용)")
    p4.set_defaults(func=cmd_status)

    p5 = sub.add_parser("check", help="named 검증만 실행(시트 무관) — Workflow 검증 스테이지용")
    p5.add_argument("--run-dir", required=True)
    p5.set_defaults(func=cmd_check)

    args = ap.parse_args()
    try:
        # dry-run 이어도 재개 판정에 시트를 읽으므로 먼저 확정한다.
        # (prep --no-resume/--views-only/--targets-json, append --sheet-map, status, check 는
        #  시트를 아예 안 읽으므로 예외 — 유니크 풀링(대량다듬기 M3b)이 후자 둘을 추가했다)
        skip_sheet = args.cmd in ("status", "check") or (
            args.cmd == "prep" and (args.no_resume or args.views_only or args.targets_json)) or (
            args.cmd == "append" and getattr(args, "sheet_map", None))
        if not skip_sheet:
            args.sheet = resolve_sheet(args)
        args.func(args)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
