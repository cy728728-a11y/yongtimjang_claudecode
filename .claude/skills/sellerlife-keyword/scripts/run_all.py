#!/usr/bin/env python3
"""셀러라이프 키워드 파이프라인 원샷 실행.

  download -> ingest -> filter -> detect -> finalize

이룸님이 할 일은 끝난 뒤 검토_*.xlsx 의 '승인' 열에 O 를 찍는 것뿐이다.
블랙리스트 반영은 절대 자동으로 하지 않는다 (blacklist_update.py 를 따로 실행).

재실행 안전:
  - raw/ 가 이미 차 있으면 다운로드를 건너뛴다 (--force 로 강제 재다운로드)
  - detect 는 실패했던 행만 다시 처리한다

사용법:
  python run_all.py
  python run_all.py --force --ship-rate 0.5
  python run_all.py --skip-download        # 이미 받은 raw 로만 다시 돌리기
"""
import argparse
import glob
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from common import default_blacklist, load_env, run_dir  # noqa: E402

PY = sys.executable


def sh(script, *args):
    """스크립트를 실행하고 stdout 을 그대로 흘리며 전체 출력을 반환."""
    cmd = [PY, os.path.join(SCRIPT_DIR, script), *[str(a) for a in args]]
    print(f"\n$ {script} {' '.join(str(a) for a in args)}\n{'-'*60}")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace",
                            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    lines = []
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        lines.append(line.rstrip("\n"))
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"{script} 실패 (exit {proc.returncode})")
    return lines


def marker(lines, name):
    """###NAME### 다음 줄 값을 반환."""
    tag = f"###{name}###"
    for i, line in enumerate(lines):
        if line.strip() == tag and i + 1 < len(lines):
            return lines[i + 1].strip()
    return None


def main():
    ap = argparse.ArgumentParser(description="셀러라이프 키워드 파이프라인 원샷")
    ap.add_argument("--data-root", help="기본: .env DATA_ROOT 또는 d:\\python_work\\data\\sellerlife")
    ap.add_argument("--blacklist", help="기본: <DATA_ROOT>/keyword_blacklist/keyword_blacklist.xlsx")
    ap.add_argument("--force", action="store_true", help="raw 가 있어도 다시 다운로드")
    ap.add_argument("--skip-download", action="store_true", help="다운로드 건너뛰고 기존 raw 사용")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--ship-rate", type=float, default=0.1)
    ap.add_argument("--max-price", type=float, default=5_000_000)
    ap.add_argument("--max-products", type=float, default=30_000)
    ap.add_argument("--batch-size", type=int, default=60)
    args = ap.parse_args()

    cfg = load_env()
    data_root = args.data_root or cfg["DATA_ROOT"]
    paths = run_dir(data_root)
    blacklist = args.blacklist or default_blacklist(data_root)
    print(f"실행 폴더: {paths['base']}")
    print(f"블랙리스트: {blacklist}")

    existing_raw = [f for f in glob.glob(os.path.join(paths["raw"], "*.xlsx"))
                    if not os.path.basename(f).startswith("~$")]

    # ---- 1) 다운로드 + 정규화
    if args.skip_download or (existing_raw and not args.force):
        if existing_raw:
            print(f"\n[1/4] raw 에 이미 {len(existing_raw)}개 파일이 있어 다운로드를 건너뜁니다. "
                  f"(다시 받으려면 --force)")
        else:
            print("\n[1/4] --skip-download 지정 — raw 가 비어 있습니다.")
            sys.exit(1)
    else:
        dl_args = ["--out-dir", paths["raw"]]
        if args.headless:
            dl_args.append("--headless")
        lines = sh("download.py", *dl_args)
        artifact = marker(lines, "ARTIFACT")
        if not artifact:
            raise RuntimeError("download.py 가 ###ARTIFACT### 를 내지 않았습니다.")
        sh("ingest.py", "--artifact", artifact, "--out-dir", paths["raw"])

    # ---- 2) 필터
    sh("filter.py", "--in-dir", paths["raw"], "--out-dir", paths["filtered"],
       "--ship-rate", args.ship_rate, "--max-price", args.max_price,
       "--max-products", args.max_products)

    # detect 는 filtered 를 제자리에서 _AI검출 로 만든다 -> detected 로 복사해 원본 보존
    import shutil
    for f in glob.glob(os.path.join(paths["filtered"], "*.xlsx")):
        dest = os.path.join(paths["detected"], os.path.basename(f))
        if not os.path.exists(dest) and not os.path.basename(f).endswith("_AI검출.xlsx"):
            shutil.copy2(f, dest)

    # ---- 3) AI 판정
    sh("detect.py", "--in-dir", paths["detected"], "--blacklist", blacklist,
       "--batch-size", args.batch_size)

    # ---- 4) 최종/검토 분리
    lines = sh("finalize.py", "--in-dir", paths["detected"], "--out-dir", paths["base"])

    print("\n" + "=" * 60)
    print("완료. 다음 순서로 진행하세요:")
    print(f"  1. 최종_통합_*.xlsx  -> 3개 카테고리 합본, 바로 사용 가능한 안전 키워드")
    print(f"  2. 검토_*.xlsx  -> '승인' 열이 규칙대로 미리 채워져 있음. 오탐만 빈칸으로 지우고 저장")
    print(f"  3. python blacklist_update.py --review-dir \"{paths['base']}\"")
    print(f"\n산출물: {paths['base']}")

    s = marker(lines, "SUMMARY")
    if s:
        print("###SUMMARY###")
        print(s)


if __name__ == "__main__":
    main()
