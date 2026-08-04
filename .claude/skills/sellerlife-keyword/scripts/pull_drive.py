#!/usr/bin/env python3
"""구글 드라이브 `51-셀러라이프-통다운` 폴더에서 통다운 raw 를 로컬 DATA_ROOT 로 내려받는다.

셀러라이프에 로그인해 새로 받는 대신(download.py), 이미 받아 드라이브에 올려둔 통다운을
가져오는 경로. PC 를 옮겨도 같은 데이터로 상품명/키워드 작업을 이어갈 수 있다.

사용:
    python pull_drive.py --list                 # 드라이브에 있는 날짜 폴더 목록
    python pull_drive.py                        # 최신 날짜 raw 를 로컬로
    python pull_drive.py --date 260731          # 특정 날짜
    python pull_drive.py --blacklist            # 블랙리스트도 같이

전제: `gws` CLI 인증 완료. gws 는 현재 작업 디렉토리 밖으로 파일을 못 쓰므로
      다운로드는 대상 폴더를 cwd 로 잡고 실행한다.
"""
import argparse
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_env  # noqa: E402

# 드라이브 `51-셀러라이프-통다운` 폴더. 이 스킬의 통다운 단일 원본.
DRIVE_FOLDER_ID = "1PwNXIpxV-n3pdCuT-3Tu4nqDIGmyvnOK"


def _gws(params, cwd=None, output=None):
    """gws drive 호출. 실패하면 stderr 를 그대로 올려 원인을 감추지 않는다."""
    cmd = ["gws", "drive", "files", "list" if "q" in params else "get",
           "--params", json.dumps(params, ensure_ascii=False), "--format", "json"]
    if output:
        cmd += ["-o", output]
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", shell=True)
    except OSError as e:
        raise SystemExit(f"gws 실행 실패: {e}")
    if r.returncode != 0:
        raise SystemExit(f"gws 오류:\n{r.stderr or r.stdout}")
    # 'Using keyring backend: ...' 같은 잡음이 앞에 붙는다 → 첫 '{' 부터 파싱
    body = r.stdout[r.stdout.find("{"):] if "{" in r.stdout else "{}"
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {}


def _children(folder_id):
    params = {"q": f"'{folder_id}' in parents and trashed=false",
              "fields": "files(id,name,mimeType,size)", "pageSize": 200,
              "supportsAllDrives": True, "includeItemsFromAllDrives": True}
    return _gws(params).get("files", [])


def _date_folders():
    """이름이 6자리 숫자(YYMMDD)인 하위 폴더만. 최신순."""
    kids = _children(DRIVE_FOLDER_ID)
    dates = [f for f in kids
             if f["mimeType"].endswith(".folder") and f["name"].isdigit() and len(f["name"]) == 6]
    return sorted(dates, key=lambda f: f["name"], reverse=True)


def _download(files, dest):
    """dest 를 cwd 로 잡고 파일별 다운로드. 같은 크기면 건너뛴다(재실행 안전)."""
    os.makedirs(dest, exist_ok=True)
    done, skipped = [], []
    for f in files:
        if f["mimeType"].endswith(".folder"):
            continue
        local = os.path.join(dest, f["name"])
        remote_size = int(f.get("size") or 0)
        if os.path.exists(local) and remote_size and os.path.getsize(local) == remote_size:
            skipped.append(f["name"])
            continue
        print(f"  받는 중: {f['name']} ({remote_size / 1048576:.0f}MB)", flush=True)
        _gws({"fileId": f["id"], "alt": "media", "supportsAllDrives": True},
             cwd=dest, output=f["name"])
        done.append(f["name"])
    return done, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYMMDD. 기본: 드라이브 최신")
    ap.add_argument("--list", action="store_true", help="날짜 폴더 목록만 출력")
    ap.add_argument("--blacklist", action="store_true", help="keyword_blacklist 도 함께")
    ap.add_argument("--data-root", help="기본: .env DATA_ROOT")
    args = ap.parse_args()

    root = args.data_root or load_env()["DATA_ROOT"]
    dates = _date_folders()
    if not dates:
        raise SystemExit("드라이브 통다운 폴더에 날짜 폴더가 없습니다.")

    if args.list:
        print("드라이브 통다운 날짜:")
        for d in dates:
            print(f"  {d['name']}")
        return

    target = next((d for d in dates if d["name"] == args.date), None) if args.date else dates[0]
    if target is None:
        raise SystemExit(f"드라이브에 {args.date} 폴더가 없습니다. --list 로 확인하세요.")

    kids = _children(target["id"])
    raw = next((f for f in kids if f["name"] == "raw" and f["mimeType"].endswith(".folder")), None)
    # 구버전 레이아웃은 raw/ 없이 날짜 폴더에 xlsx 가 바로 있다.
    src_files = _children(raw["id"]) if raw else [f for f in kids if not f["mimeType"].endswith(".folder")]
    if not src_files:
        raise SystemExit(f"{target['name']} 에 받을 파일이 없습니다.")

    dest = os.path.join(root, "runs", target["name"], "raw")
    print(f"[통다운] {target['name']} → {dest}")
    done, skipped = _download(src_files, dest)
    print(f"  완료 {len(done)}개 · 이미있음 {len(skipped)}개")

    if args.blacklist:
        bl = next((f for f in _children(DRIVE_FOLDER_ID) if f["name"] == "keyword_blacklist"), None)
        if bl:
            bdest = os.path.join(root, "keyword_blacklist")
            print(f"[블랙리스트] → {bdest}")
            d2, s2 = _download(_children(bl["id"]), bdest)
            print(f"  완료 {len(d2)}개 · 이미있음 {len(s2)}개")
        else:
            print("  드라이브에 keyword_blacklist 폴더가 없습니다.")

    print(f"\n--source-date {target['name']} 로 쓰면 됩니다.")


if __name__ == "__main__":
    main()
