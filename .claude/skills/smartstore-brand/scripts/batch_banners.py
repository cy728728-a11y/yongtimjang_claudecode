# -*- coding: utf-8 -*-
"""
마켓 목록(markets.tsv)을 읽어 사업자코드 폴더별로 모바일/PC 배너를 일괄 생성.

출력:
    50-resources/attachments/banners/<코드>_<마켓명>/<마켓명>_모바일배너_750x240.png
    50-resources/attachments/banners/<코드>_<마켓명>/<마켓명>_PC배너_1280x200.png

사용법:
    python batch_banners.py                 # 전체 실행
    python batch_banners.py --only 1-1,1-2,1-3   # 특정 코드만 (샘플용)
    python batch_banners.py --modes mobile       # 특정 모드만
    python batch_banners.py --dry-run            # 실제 호출 없이 계획만 출력

이미 파일이 있으면 건너뜀(재개 가능). 실패는 기록만 하고 계속 진행.
Windows: PYTHONIOENCODING=utf-8 PYTHONUTF8=1 로 실행.
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
GEN_SCRIPT = SCRIPT_DIR / "gen_asset.py"
MARKETS_TSV = SCRIPT_DIR / "markets.tsv"
OUT_ROOT = Path(r"C:\Users\workspace\50-resources\attachments\banners")

SUFFIX = {
    "mobile": "_모바일배너_750x240",
    "pc": "_PC배너_1280x200",
}


def load_markets(only=None):
    """markets.tsv 를 읽어 [(코드, 마켓명), ...] 반환."""
    rows = []
    try:
        for line in MARKETS_TSV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                print(f"[경고] 형식 오류로 건너뜀: {line}")
                continue
            code, name = parts[0].strip(), parts[1].strip()
            if only and code not in only:
                continue
            rows.append((code, name))
    except OSError as e:
        print(f"markets.tsv 읽기 실패: {e}")
        sys.exit(1)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="쉼표로 구분된 코드 목록 (예: 1-1,1-2)")
    ap.add_argument("--modes", default="mobile,pc", help="mobile,pc 중 선택")
    ap.add_argument("--sleep", type=float, default=2.0, help="호출 간 대기 초")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    only = {c.strip() for c in args.only.split(",")} if args.only else None
    modes = [m.strip() for m in args.modes.split(",") if m.strip() in SUFFIX]
    if not modes:
        print("유효한 mode 없음 (mobile|pc)")
        sys.exit(1)

    markets = load_markets(only)
    if not markets:
        print("대상 마켓 없음.")
        sys.exit(1)

    total = len(markets) * len(modes)
    print(f"대상: 마켓 {len(markets)}개 x {len(modes)}종 = {total}장\n")

    done, skipped, failed = 0, 0, []
    idx = 0

    for code, name in markets:
        folder = OUT_ROOT / f"{code}_{name}"
        for mode in modes:
            idx += 1
            out_path = folder / f"{name}{SUFFIX[mode]}.png"
            tag = f"[{idx}/{total}] {code} {name} ({mode})"

            if out_path.exists():
                print(f"{tag} - 이미 있음, 건너뜀")
                skipped += 1
                continue

            if args.dry_run:
                print(f"{tag} -> {out_path}")
                continue

            try:
                folder.mkdir(parents=True, exist_ok=True)
                res = subprocess.run(
                    [sys.executable, str(GEN_SCRIPT), mode, name, str(out_path)],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    timeout=420,
                )
                if res.returncode == 0 and out_path.exists():
                    print(f"{tag} - 완료")
                    done += 1
                else:
                    msg = (res.stdout or "").strip().splitlines()[-1:] or ["출력 없음"]
                    print(f"{tag} - 실패: {msg[0]}")
                    failed.append((code, name, mode, msg[0]))
            except subprocess.TimeoutExpired:
                print(f"{tag} - 타임아웃")
                failed.append((code, name, mode, "타임아웃"))
            except Exception as e:
                print(f"{tag} - 예외: {type(e).__name__}: {e}")
                failed.append((code, name, mode, f"{type(e).__name__}: {e}"))

            if args.sleep and not args.dry_run:
                time.sleep(args.sleep)

    print(f"\n=== 결과 ===\n생성 {done} / 건너뜀 {skipped} / 실패 {len(failed)}")
    if failed:
        print("\n실패 목록 (재실행하면 이것만 다시 시도됩니다):")
        for code, name, mode, err in failed:
            print(f"  {code} {name} ({mode}) - {err}")


if __name__ == "__main__":
    main()
