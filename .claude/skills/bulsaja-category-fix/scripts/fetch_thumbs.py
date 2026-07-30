#!/usr/bin/env python3
"""
썸네일 다운로더 — 불사자 상품 썸네일 URL을 로컬로 내려받아 경로를 출력.

Claude(비전)가 이 로컬 이미지를 Read 로 열어 "상품의 실제 정체"를 판단하고
셀하 검색용 핵심어를 바로잡는 데 쓴다(카테고리 교정 스킬 Step 3b).

실제 다운로드는 **공용 스냅샷 캐시**(eroomlib.snapshot)가 한다 — 같은 URL 을 다른 스킬이
이미 받아뒀으면 복사만 하고 네트워크를 타지 않는다. 출력 파일명·형식은 종전과 동일.
(alicdn / bulsaja S3 등이 헤더 없는 요청을 403 하므로 브라우저 UA/Referer 를 붙이는 것도
 그쪽에 있다.)

사용법:
  # URL 직접
  python fetch_thumbs.py --url "https://img.alicdn.com/....jpg" --out-dir <dir>
  # 여러 개
  python fetch_thumbs.py --url "<u1>" "<u2>" --out-dir <dir>
  # 배치(JSON: [{"productId":"..","url":".."}])
  python fetch_thumbs.py --input thumbs.json --out-dir <dir>

출력: 다운로드된 로컬 파일 절대경로(성공) 또는 'FAIL\t<url>\t<사유>'.
"""
import argparse
import json
import os
import sys


try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    import requests  # noqa: F401  (실제 요청은 eroomlib.snapshot 이 한다)
except ImportError:
    print("Error: requests 패키지가 필요합니다 (.venv). pip install requests")
    sys.exit(1)

# eroomlib 로드: 상위로 `.claude` 앵커(= lib/eroomlib)를 찾아 lib 를 1회 insert.
_d = os.path.dirname(os.path.abspath(__file__))
while _d and _d != os.path.dirname(_d):
    _lib = os.path.join(_d, "lib")
    if os.path.isdir(os.path.join(_lib, "eroomlib")):
        if _lib not in sys.path:
            sys.path.insert(0, _lib)
        break
    _d = os.path.dirname(_d)

from eroomlib import snapshot  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="불사자 썸네일 다운로더")
    ap.add_argument("--url", "-u", nargs="+", help="다운로드할 이미지 URL(들)")
    ap.add_argument("--input", "-i", help='배치 JSON: [{"productId","url"}]')
    ap.add_argument("--out-dir", "-o", required=True, help="저장 폴더")
    ap.add_argument("--refresh", action="store_true",
                    help="스냅샷 캐시 무시하고 원본 서버에서 다시 받는다")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    items = []  # (name_hint, url)
    if args.input:
        with open(args.input, encoding="utf-8") as f:
            for it in json.load(f):
                items.append((it.get("productId"), it.get("url") or it.get("thumb")))
    for u in (args.url or []):
        items.append((None, u))
    if not items:
        ap.error("--url 또는 --input 이 필요합니다.")

    for idx, (hint, url) in enumerate(items):
        if not url:
            print(f"FAIL\t(빈 URL)\t상품 {hint}")
            continue
        # 같은 URL 을 이미 받아둔 스킬이 있으면 스냅샷 캐시에서 복사만 한다(네트워크 0).
        path, err = snapshot.materialize_image(url, args.out_dir, hint, idx,
                                               refresh=args.refresh)
        if path:
            print(path)
        else:
            print(f"FAIL\t{url}\t{err}")


if __name__ == "__main__":
    main()
