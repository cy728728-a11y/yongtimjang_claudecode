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

# --- 고정 설정 -------------------------------------------------------------
# 출력은 **그룹별 카테고리교정 로그 시트의 '상품명' 탭**이다(2026-07-23 결정).
# 작업 단위(마켓그룹)와 파일 단위가 일치하고, 입력(검색어(사용))과 출력이 한 파일에 모인다.
# 고정 기본 시트를 두지 않는다 — 그룹이 바뀌는데 시트가 안 바뀌면 다른 그룹 로그에 섞인다.
CATFIX_FOLDER = "1bVa3y725YCCSrOtx_bqBylBpvaXvwm2w"  # 드라이브 20-불사자-상품관리 > 카테고리교정
SHEET_PREFIX = "카테고리교정_"
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
        _build_views_and_batches(run_dir, targets, _restore_thumb_map(run_dir),
                                 args.no_parent, len(skipped),
                                 wd_by_id=wd_by_id, jk_by_id=jk_by_id)
        return

    group_path = os.path.join(run_dir, "group.json")
    workdata_path = os.path.join(run_dir, "workdata.json")
    targets_path = os.path.join(run_dir, "targets.json")
    thumbs_json = os.path.join(run_dir, "thumbs.json")
    thumbs_dir = os.path.join(run_dir, "thumbs")

    # 1) 마켓그룹 → 상품목록
    if os.path.exists(group_path) and not args.force:
        print(f"[1/6] group.json 재사용 ({group_path})")
    else:
        print(f"[1/6] 마켓그룹 {args.group_id} 상품목록 수집 중...")
        _run([py, os.path.join(BULSAJA_SCRIPTS, "collect_group.py"),
              "--group-id", str(args.group_id), "-o", group_path], "collect_group.py")
    group = _load(group_path)
    if args.limit:
        group = group[: args.limit]
        print(f"  --limit {args.limit} 적용 → {len(group)}건")

    # 2) 이미 처리된 상품 제외 (상품명 탭 A열 = 상태 저장소)
    done_ids = set() if args.no_resume else _done_ids(args.sheet, args.tab)
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
        _run([py, os.path.join(BULSAJA_SCRIPTS, "bulsaja_mcp.py"), "workdata",
              "--input", os.path.join(run_dir, "pending.json"),
              "--output", workdata_path, "--sleep", str(args.sleep)],
             "bulsaja_mcp.py workdata")
    workdata = _load(workdata_path)
    wd_by_id = {w.get("productId"): w for w in workdata}

    # 3b) 카테고리교정 시트 J·K — 실물판정·썸네일URL. 있으면 배치에 실어 재활용,
    #     없으면(구버전 그룹) 상품명 스킬이 증거 4종으로 직접 판정한다.
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
        cat = (wd.get("기존카테고리") or "").strip()
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

    # 6) 카테고리 프리필터 + 계단 후보 청크
    raw_dir = args.raw_dir
    if not raw_dir:
        if not args.source_date:
            raise RuntimeError("--raw-dir 또는 --source-date 중 하나는 필요합니다.")
        raw_dir = os.path.join("D:\\python_work\\data\\sellerlife\\runs", args.source_date, "raw")
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
    ]
    return row


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

    # 2) 시트 append
    group_name = args.group_name or ""
    if not args.dry_run:
        if sheet_io.ensure_tab(args.sheet, args.tab, NAME_HEADER):
            print(f"  탭 신설: {args.tab}")

    if not args.dry_run and not args.no_related:
        if sheet_io.ensure_tab(args.sheet, REL_TAB, REL_HEADER):
            print(f"  탭 신설: {REL_TAB}")

    # J열 backfill 준비 — prep 때 저장한 jk_map 으로 "원래 J가 비어 있던"(구버전) 건을 안다.
    # 상품명 스킬이 직접 판정한 실물을 그 빈 J열에 되쓴다(신버전 J는 덮지 않는다).
    jk_path = os.path.join(run_dir, "jk_map.json")
    jk_map = _load(jk_path) if os.path.exists(jk_path) else {}
    backfill = {}  # {productId: 실물판정}

    total, rel_total = 0, 0
    print("[2/2] 시트 append...")
    for cf in sorted(glob.glob(os.path.join(checked_dir, "checked_*.json"))):
        data = _load(cf)
        done_ids = _done_ids(args.sheet, args.tab)  # 직전 재조회(이중실행 방어)
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

    if not args.dry_run:
        print(f"###APPEND### 총 {total}행 -> {args.tab} / 관련어 {rel_total}행 -> {REL_TAB}")
        print(f"  https://docs.google.com/spreadsheets/d/{args.sheet}/edit")


# ---------------------------------------------------------------------------
# rename
# ---------------------------------------------------------------------------

def cmd_rename(args):
    """04-상품명 탭에서 상태=생성완료 건을 불사자에 실제 반영.

    --commit 없으면 대상만 출력(미리보기). rename은 50건/호출 상한.
    """
    from bulsaja_mcp import BulsajaMCP  # noqa: E402
    from eroomlib.gsheets import sheets_get  # noqa: E402

    ncol = len(NAME_HEADER)

    def _col_letter(n):  # 1-based 열번호 → A1 열문자(27→AA 등, 26열 초과 대응)
        s = ""
        while n > 0:
            n, r = divmod(n - 1, 26)
            s = chr(ord("A") + r) + s
        return s

    last = _col_letter(ncol)
    rows = sheets_get(args.sheet, f"'{args.tab}'!A2:{last}")
    i_status = NAME_HEADER.index("상태")
    i_id = NAME_HEADER.index("상품id")
    i_orig = NAME_HEADER.index("원본상품명")
    i_new = NAME_HEADER.index("새상품명")
    targets = []
    for r in rows:
        r = list(r) + [""] * (ncol - len(r))
        pid, orig, newname = r[i_id], r[i_orig], r[i_new]
        status = str(r[i_status]).strip()
        if not str(pid).strip() or status != "생성완료":
            continue
        if not str(newname).strip():
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
    ok, fail = 0, 0
    try:
        for i in range(0, len(targets), 50):  # rename 상한 50건/호출
            batch = [{"productId": t["productId"], "name": t["name"]} for t in targets[i:i + 50]]
            try:
                prev = mcp.call_tool("bulsaja_product_rename",
                                     {"items": batch, "confirm": False})
                token = prev.get("confirmationToken")
                if not token:
                    print(f"  [{i // 50 + 1}] 확인토큰 없음 — 스킵: "
                          f"{str(prev.get('message'))[:120]}", file=sys.stderr)
                    fail += len(batch)
                    continue
                res = mcp.call_tool("bulsaja_product_rename",
                                    {"items": batch, "confirm": True,
                                     "confirmationToken": token})
                if res.get("success") is False:
                    print(f"  [{i // 50 + 1}] 실패: {str(res.get('message'))[:150]}",
                          file=sys.stderr)
                    fail += len(batch)
                else:
                    ok += len(batch)
                    print(f"  [{i // 50 + 1}] {len(batch)}건 반영")
            except Exception as e:
                print(f"  [{i // 50 + 1}] 오류: {type(e).__name__}: {e}", file=sys.stderr)
                fail += len(batch)
            time.sleep(args.sleep)
    finally:
        mcp.close()
    print(f"###RENAME### 반영 {ok}건 / 실패 {fail}건")
    if ok:
        print("  시트 상태 열을 '반영완료'로 갱신하려면 시트에서 직접 수정하거나 "
              "이룸님 확인 후 별도 처리하세요.")


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
    p1.add_argument("--group-id", type=int, required=True)
    p1.add_argument("--run-dir", required=True)
    p1.add_argument("--source-date", default=None, help="셀러라이프 통다운 YYMMDD")
    p1.add_argument("--raw-dir", default=None)
    p1.add_argument("--zip", default=None)
    p1.add_argument("--limit", type=int, default=None, help="상위 N건만 (파일럿용)")
    p1.add_argument("--views-only", action="store_true",
                    help="기존 run-dir의 targets/manifest로 뷰·배치만 재생성 "
                         "(MCP·통다운 스캔을 다시 타지 않는다)")
    p1.add_argument("--no-parent", action="store_true",
                    help="상위 카테고리(2차 접두) 뷰를 만들지 않는다. leaf에 직결어가 없는 "
                         "상품의 구명줄이 사라지므로 평소엔 켜둔다")
    p1.add_argument("--sleep", type=float, default=0.3, help="workdata 호출 간격(초)")
    p1.add_argument("--skip-thumbs", action="store_true", help="썸네일 다운로드 생략")
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
    p2.add_argument("--tab", default=NAME_TAB, help="기록할 탭 이름")
    p2.set_defaults(func=cmd_append)

    p3 = sub.add_parser("rename", help="시트 생성완료 건을 불사자에 반영")
    p3.add_argument("--run-dir", required=True)
    p3.add_argument("--commit", action="store_true", help="실제 반영(없으면 미리보기)")
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

    args = ap.parse_args()
    try:
        # dry-run 이어도 재개 판정에 시트를 읽으므로 먼저 확정한다.
        # (prep --no-resume, views-only, status 는 시트를 아예 안 읽으므로 예외)
        skip_sheet = args.cmd == "status" or (
            args.cmd == "prep" and (args.no_resume or args.views_only))
        if not skip_sheet:
            args.sheet = resolve_sheet(args)
        args.func(args)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
