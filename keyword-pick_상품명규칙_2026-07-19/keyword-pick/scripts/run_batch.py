#!/usr/bin/env python3
"""키워드→상품명 배치 오케스트레이터 — prep-kw / append-kw 서브커맨드.

이미 완성된 4개 스크립트(kwlib.py / cat_prefilter.py / batch_candidates.py / sheet_io.py)를
순서대로 호출하는 배치A(④ 키워드) 오케스트레이터. prep-name/append-name(배치B)은 별도 작업.

설계문서: .claude/skills/keyword-pick/references/키워드-상품명-배치설계.md (§배치흐름, §상태관리)

Usage:
  python run_batch.py prep-kw --run-dir <R> [--limit N] [--raw-dir ...] [--zip ...] [--source-date 260712]
  python run_batch.py append-kw --run-dir <R> [--dry-run]
"""
import argparse
import glob
import json
import os
import subprocess
import sys
from datetime import date

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import sheet_io  # noqa: E402

SHEET = "1DbR2upLX_DXjgjXpGPdide2SUifli_X6DTqhUTr9Syk"
KEYWORD_TAB = "02-키워드"
KEYWORD_HEADER = [
    "상품id", "작업일", "상품명", "대표키워드", "카테고리", "구분",
    "키워드", "총검색수", "상품수", "선정근거", "기준", "원본파일링크",
    "네이버해외배송비율", "쿠팡해외배송비율", "신규진입키워드",
]
# 통다운 날짜폴더(원본파일링크 fallback) — picked에 원본파일링크가 없을 때만 사용
DEFAULT_DRIVE_LINK = "https://drive.google.com/drive/folders/1EgIOFqgcabiSZwEactXFo4X3uWN9A_c8"

# 워크스페이스 표준 venv (scripts -> keyword-pick -> skills -> .claude -> 프로젝트 루트)
_PROJECT_ROOT = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))
VENV_PYTHON = os.path.join(_PROJECT_ROOT, ".venv", "Scripts", "python.exe")


def _venv_python():
    """워크스페이스 venv 파이썬 경로. 없으면 현재 인터프리터로 폴백."""
    return VENV_PYTHON if os.path.exists(VENV_PYTHON) else sys.executable


def _run_subprocess(args, label):
    """서브 스크립트 subprocess 실행. 실패 시 명확한 에러로 중단."""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        result = subprocess.run(args, env=env, capture_output=True, text=True, encoding="utf-8")
    except OSError as e:
        raise RuntimeError(f"{label} 실행 실패(프로세스 시작 불가): {e}")

    if result.stdout:
        print(result.stdout)
    if result.returncode != 0:
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"{label} 실패 (returncode={result.returncode})")
    if result.stderr:
        # returncode 0이어도 경고성 stderr(예: manifest 미매칭 경고)는 그대로 노출
        print(result.stderr, file=sys.stderr)
    return result.stdout


# ---------------------------------------------------------------------------
# prep-kw
# ---------------------------------------------------------------------------

def cmd_prep_kw(args):
    run_dir = os.path.abspath(args.run_dir)
    os.makedirs(run_dir, exist_ok=True)

    print("[1/4] 시트에서 대상 읽는 중...")
    all_targets = sheet_io.read_targets(SHEET)
    done_ids = sheet_io.read_done_ids(SHEET, KEYWORD_TAB)
    pending = [t for t in all_targets if t["productId"] not in done_ids]
    if args.limit:
        pending = pending[: args.limit]

    print(
        f"  교정완료 {len(all_targets)}건 / 이미처리(02-키워드) {len(done_ids)}건 / "
        f"미처리 {len(pending)}건" + (f" (--limit {args.limit} 적용)" if args.limit else "")
    )

    targets_path = os.path.join(run_dir, "targets.json")
    with open(targets_path, "w", encoding="utf-8") as f:
        json.dump(pending, f, ensure_ascii=False, indent=2)
    print(f"  -> {targets_path}")

    if not pending:
        print("미처리 대상이 없습니다. 종료합니다.")
        return

    # raw-dir 결정: 명시값 우선, 없으면 --source-date로 표준 경로 조립
    raw_dir = args.raw_dir
    if not raw_dir:
        if not args.source_date:
            raise RuntimeError("--raw-dir 또는 --source-date 중 하나는 반드시 지정해야 합니다.")
        raw_dir = os.path.join(
            "D:\\python_work\\data\\sellerlife\\runs", args.source_date, "raw"
        )
    if not os.path.isdir(raw_dir):
        raise RuntimeError(f"raw-dir가 존재하지 않습니다: {raw_dir}")

    py = _venv_python()

    print(f"[2/4] 카테고리 프리필터 실행 중 (raw-dir={raw_dir}, 통다운 스캔이라 시간 소요)...")
    prefilter_args = [
        py, os.path.join(SCRIPT_DIR, "cat_prefilter.py"),
        "--targets", targets_path, "--out-dir", run_dir, "--raw-dir", raw_dir,
    ]
    if args.zip:
        prefilter_args += ["--zip", args.zip]
    _run_subprocess(prefilter_args, "cat_prefilter.py")

    print("[3/4] 후보 청크 생성 중...")
    candidates_args = [py, os.path.join(SCRIPT_DIR, "batch_candidates.py"), run_dir]
    _run_subprocess(candidates_args, "batch_candidates.py")

    print("[4/4] 요약")
    manifest_path = os.path.join(run_dir, "manifest.json")
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    chunk_dir = os.path.join(run_dir, "candidates")
    chunk_files = sorted(glob.glob(os.path.join(chunk_dir, "chunk_*.json")))
    print(f"  미처리 상품: {len(pending)}건")
    print(f"  청크: {len(chunk_files)}개 -> {chunk_dir}")
    print(f"  manifest.not_found (append-kw에서 스킵 마커로 처리 예정): {len(manifest.get('not_found', []))}건")


# ---------------------------------------------------------------------------
# append-kw
# ---------------------------------------------------------------------------

def _build_kw_row(product, gubun, kw, drive_link):
    """추천/소싱후보 키워드 1개 -> 02-키워드 15열 행."""
    return [
        product.get("productId", ""),
        date.today().isoformat(),
        product.get("상품명", ""),
        product.get("대표키워드", ""),
        product.get("카테고리", ""),
        gubun,
        kw.get("키워드", ""),
        kw.get("총검색수", ""),
        kw.get("상품수", ""),
        kw.get("선정근거", ""),
        kw.get("기준", ""),
        drive_link,
        kw.get("네이버해외배송비율", ""),
        kw.get("쿠팡해외배송비율", ""),
        kw.get("신규진입키워드", ""),
    ]


def _build_product_rows(product):
    """picked 상품 1개 -> 02-키워드 행 목록. 추천/소싱후보 모두 없으면 결과없음 마커 1행."""
    # picked의 원본파일링크가 로컬 경로(prefiltered placeholder)면 Drive 링크로 대체
    _link = product.get("원본파일링크") or ""
    drive_link = _link if str(_link).startswith("http") else DEFAULT_DRIVE_LINK
    rows = []
    for kw in (product.get("추천") or []):
        rows.append(_build_kw_row(product, "추천", kw, drive_link))
    for kw in (product.get("소싱후보") or []):
        rows.append(_build_kw_row(product, "소싱후보", kw, drive_link))
    if not rows:
        reason = product.get("사유", "")
        rows.append([
            product.get("productId", ""), date.today().isoformat(),
            product.get("상품명", ""), product.get("대표키워드", ""),
            product.get("카테고리", ""), "결과없음",
            "", "", "", reason, "", drive_link, "", "", "",
        ])
    return rows


def _build_skip_row(item, targets_by_id):
    """manifest.not_found 항목 1개 -> 02-키워드 스킵 마커 1행. 상품명/대표키워드는 targets.json에서 보강."""
    pid = item.get("productId", "")
    t = targets_by_id.get(pid, {})
    reason = item.get("사유", "")
    if reason == "통다운밖":
        gubun = "스킵(통다운밖)"
    elif reason == "표기불일치의심":
        gubun = "스킵(표기불일치의심)"
    elif reason:
        gubun = f"스킵({reason})"
    else:
        gubun = "스킵"
    return [
        pid, date.today().isoformat(),
        t.get("상품명", ""), t.get("대표키워드", ""),
        item.get("카테고리", ""), gubun,
        "", "", "", reason, "", "", "", "", "",
    ]


def cmd_append_kw(args):
    run_dir = os.path.abspath(args.run_dir)
    picked_dir = os.path.join(run_dir, "picked")
    picked_files = sorted(glob.glob(os.path.join(picked_dir, "picked_*.json")))

    if not picked_files:
        print(f"picked 파일이 없습니다: {picked_dir}")

    if not args.dry_run and picked_files:
        created = sheet_io.ensure_tab(SHEET, KEYWORD_TAB, KEYWORD_HEADER)
        if created:
            print(f"  탭 신설: {KEYWORD_TAB}")

    total_appended = 0

    # 1) picked 청크별 처리 — 상품 경계 유지(한 상품의 모든 행 = 한 append 호출 안)
    for pf in picked_files:
        with open(pf, encoding="utf-8") as f:
            picked = json.load(f)

        done_ids = sheet_io.read_done_ids(SHEET, KEYWORD_TAB)  # append 직전 재조회(이중실행 방어)
        rows = []
        for product in picked.get("products", []):
            pid = product.get("productId", "")
            if pid in done_ids:
                print(f"  스킵(이미처리): {pid}")
                continue
            rows.extend(_build_product_rows(product))

        if not rows:
            print(f"{os.path.basename(pf)}: 추가할 행 없음(전부 이미처리)")
            continue

        if args.dry_run:
            print(f"--- {os.path.basename(pf)} (dry-run, {len(rows)}행) ---")
            for r in rows:
                print(json.dumps(r, ensure_ascii=False))
        else:
            n = sheet_io.append_rows(SHEET, KEYWORD_TAB, rows)
            total_appended += n
            print(f"{os.path.basename(pf)}: {n}행 append 완료")

    # 2) 스킵 마커(manifest.not_found) — 별도 배치로 append
    manifest_path = os.path.join(run_dir, "manifest.json")
    targets_path = os.path.join(run_dir, "targets.json")
    if os.path.exists(manifest_path) and os.path.exists(targets_path):
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
        with open(targets_path, encoding="utf-8") as f:
            targets = json.load(f)
        targets_by_id = {t["productId"]: t for t in targets}
        not_found = manifest.get("not_found", [])

        if not_found:
            done_ids = sheet_io.read_done_ids(SHEET, KEYWORD_TAB)
            skip_rows = [
                _build_skip_row(item, targets_by_id)
                for item in not_found
                if item.get("productId", "") not in done_ids
            ]
            if args.dry_run:
                print(f"--- 스킵 마커 (dry-run, {len(skip_rows)}행) ---")
                for r in skip_rows:
                    print(json.dumps(r, ensure_ascii=False))
            elif skip_rows:
                n = sheet_io.append_rows(SHEET, KEYWORD_TAB, skip_rows)
                total_appended += n
                print(f"스킵 마커: {n}행 append 완료")

    if not args.dry_run:
        print(f"총 {total_appended}행 append 완료")


# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="키워드→상품명 배치 오케스트레이터 (배치A: ④ 키워드)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("prep-kw", help="미처리 대상 추출 + 프리필터 + 후보청크 생성")
    p1.add_argument("--run-dir", required=True, help="targets.json/manifest.json/candidates/ 를 둘 작업 디렉토리")
    p1.add_argument("--limit", type=int, default=None, help="미처리 상위 N개만 처리(파일럿용)")
    p1.add_argument("--raw-dir", default=None, help="통다운 raw xlsx 폴더 (미지정시 --source-date로 조립)")
    p1.add_argument("--zip", default=None, help="통다운 전체카테고리 zip 경로")
    p1.add_argument("--source-date", default=None, help="YYMMDD, --raw-dir 미지정시 표준경로 조립에 사용")
    p1.set_defaults(func=cmd_prep_kw)

    p2 = sub.add_parser("append-kw", help="picked 결과 + 스킵마커를 02-키워드 탭에 append")
    p2.add_argument("--run-dir", required=True, help="picked/manifest.json/targets.json 이 있는 디렉토리")
    p2.add_argument("--dry-run", action="store_true", help="실제 append 없이 변환된 15열 행만 stdout 출력")
    p2.set_defaults(func=cmd_append_kw)

    args = parser.parse_args()
    try:
        args.func(args)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
