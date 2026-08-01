#!/usr/bin/env python3
"""sellerlife-keyword 스킬 최초 설치 — 대화형으로 .env 를 만들고 데이터 폴더를 잡는다.

PC마다 다른 것(저장 경로·구글 계정·Gemini 키)만 물어보고 나머지는 그대로 쓴다.

  python install.py                      # 대화형 (권장)
  python install.py --data-root D:\\data  # 경로만 지정, 나머지는 기존값 유지
  python install.py --yes                # 전부 기본값으로, 묻지 않음

기존 .env 가 있으면 그 값이 기본값이 되므로, 다시 돌려도 안전하다.
"""
import argparse
import os
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
ENV_PATH = os.path.join(SKILL_DIR, ".env")
ASSET_BLACKLIST = os.path.join(SKILL_DIR, "assets", "keyword_blacklist.xlsx")

DEFAULT_DATA_ROOT = os.path.join(os.path.expanduser("~"), "sellerlife-data")


def read_env(path):
    """기존 .env 를 dict 로. 없으면 빈 dict. (주석·빈 줄 무시)"""
    cfg = {}
    if not os.path.exists(path):
        return cfg
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip()
    except OSError as e:
        print(f"[경고] 기존 .env 를 읽지 못했습니다({e}). 새로 만듭니다.")
    return cfg


def ask(prompt, default, auto=False, secret=False):
    """엔터=기본값 유지. --yes 면 묻지 않고 기본값."""
    shown = default or "(비어 있음)"
    if secret and default:
        shown = default[:6] + "…" + default[-4:] if len(default) > 12 else "설정됨"
    if auto:
        print(f"{prompt}: {shown}")
        return default
    got = input(f"{prompt}\n  [엔터 = {shown}] > ").strip()
    return got or default


def main():
    ap = argparse.ArgumentParser(description="sellerlife-keyword 설치")
    ap.add_argument("--data-root", help="결과 파일 저장 루트 (묻지 않고 이 값 사용)")
    ap.add_argument("--email", help="셀러라이프 구글 로그인 이메일")
    ap.add_argument("--gemini-key", help="Gemini API 키")
    ap.add_argument("--yes", action="store_true", help="전부 기본값으로, 묻지 않음")
    args = ap.parse_args()

    old = read_env(ENV_PATH)
    auto = args.yes

    print("=" * 62)
    print("  셀러라이프 키워드 스킬 설치")
    print("=" * 62)
    print()

    # ---- 1) 저장 경로 (PC마다 다른 유일한 필수 항목)
    if args.data_root:
        data_root = args.data_root
        print(f"저장 경로: {data_root}")
    else:
        print("[1/3] 다운로드·가공 결과를 어디에 저장할까요?")
        print("      · 카테고리소싱 원본 ZIP 이 ~205MB, 압축 풀면 카테고리당 100~260MB 입니다.")
        print("      · 여유 있는 드라이브를 권합니다 (예: D:\\sellerlife-data)")
        data_root = ask("      저장 루트 경로",
                        old.get("DATA_ROOT") or DEFAULT_DATA_ROOT, auto)
    data_root = os.path.abspath(os.path.expandvars(os.path.expanduser(data_root.strip('"'))))
    print()

    # ---- 2) 구글 계정
    if args.email:
        email = args.email
    else:
        print("[2/3] 셀러라이프 구글 로그인 이메일")
        print("      (비밀번호는 저장하지 않습니다. 최초 1회 브라우저에서 직접 로그인)")
        email = ask("      이메일", old.get("SELLERLIFE_GOOGLE_EMAIL", ""), auto)
    print()

    # ---- 3) Gemini 키
    if args.gemini_key:
        key = args.gemini_key
    else:
        print("[3/3] Gemini API 키 (브랜드/상표 키워드 AI 판정용)")
        print("      새로 받으려면 https://aistudio.google.com/apikey")
        key = ask("      API 키", old.get("GEMINI_API_KEY", ""), auto, secret=True)
    print()

    # ---- 폴더 생성
    try:
        bl_dir = os.path.join(data_root, "keyword_blacklist")
        os.makedirs(os.path.join(data_root, "runs"), exist_ok=True)
        os.makedirs(bl_dir, exist_ok=True)
    except OSError as e:
        print(f"[오류] 폴더를 만들 수 없습니다: {data_root}\n       {e}")
        sys.exit(1)

    # ---- 블랙리스트 배치 (있으면 건드리지 않는다 — 누적 자산이라 덮으면 손실)
    bl_path = os.path.join(bl_dir, "keyword_blacklist.xlsx")
    if os.path.exists(bl_path):
        print(f"블랙리스트: 이미 있음 — 그대로 둡니다 ({bl_path})")
    elif os.path.exists(ASSET_BLACKLIST):
        try:
            shutil.copy2(ASSET_BLACKLIST, bl_path)
            print(f"블랙리스트: 동봉본을 복사했습니다 -> {bl_path}")
        except OSError as e:
            print(f"[경고] 블랙리스트 복사 실패: {e}")
    else:
        print(f"[경고] 블랙리스트가 없습니다: {bl_path}")
        print("       제외키워드/제외카테고리/제외브랜드 시트를 가진 엑셀을 이 경로에 두세요.")

    # ---- .env 쓰기
    body = f"""# 셀러라이프(sellochomes.co.kr) 구글 로그인 계정
# 비밀번호는 저장하지 않는다. 최초 1회 `download.py --setup` 으로 사람이 직접 로그인하면
# _chrome_profile/ 에 구글 세션이 남아 이후 실행은 자동으로 통과한다.
SELLERLIFE_GOOGLE_EMAIL={email}

# Gemini API 키 (브랜드/상표 키워드 AI 판정용). AIza... 또는 AQ... 둘 다 지원.
GEMINI_API_KEY={key}

# 결과 저장 루트 (install.py 가 기록)
DATA_ROOT={data_root}
"""
    try:
        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.write(body)
    except OSError as e:
        print(f"[오류] .env 저장 실패: {e}")
        sys.exit(1)

    print(f".env 저장: {ENV_PATH}")
    print()
    print("=" * 62)
    print("설치 완료. 다음 순서로 진행하세요.")
    print()
    print("  1) 구글 로그인 (최초 1회, 사람이 직접):")
    print(f'     python "{os.path.join(SCRIPT_DIR, "download.py")}" --setup --wait 600')
    print()
    print("  2) 파이프라인 실행 (매번 이것만):")
    print(f'     python "{os.path.join(SCRIPT_DIR, "run_all.py")}"')
    print()
    print(f"  결과는 {os.path.join(data_root, 'runs')}\\<YYMMDD>\\ 에 쌓입니다.")
    print("=" * 62)

    if not email or not key:
        print()
        print("[주의] 비어 있는 항목이 있습니다. .env 를 직접 채우거나 install.py 를 다시 실행하세요.")


if __name__ == "__main__":
    main()
