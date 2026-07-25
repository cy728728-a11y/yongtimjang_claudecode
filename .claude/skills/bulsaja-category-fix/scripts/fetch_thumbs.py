#!/usr/bin/env python3
"""
썸네일 다운로더 — 불사자 상품 썸네일 URL을 로컬로 내려받아 경로를 출력.

Claude(비전)가 이 로컬 이미지를 Read 로 열어 "상품의 실제 정체"를 판단하고
셀하 검색용 핵심어를 바로잡는 데 쓴다(카테고리 교정 스킬 Step 3b).

alicdn / bulsaja S3 등이 헤더 없는 요청을 403 하는 경우가 있어
브라우저 User-Agent/Referer 를 붙여 받는다.

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
import urllib.parse

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    import requests
except ImportError:
    print("Error: requests 패키지가 필요합니다 (.venv). pip install requests")
    sys.exit(1)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.taobao.com/",
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}

EXT_BY_CT = {
    "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png",
    "image/webp": ".webp", "image/gif": ".gif", "image/avif": ".avif",
}


def _ext_from(url, content_type):
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct in EXT_BY_CT:
        return EXT_BY_CT[ct]
    path = urllib.parse.urlparse(url).path
    _, dot, ext = path.rpartition(".")
    if dot and 1 <= len(ext) <= 5:
        return "." + ext.lower()
    return ".jpg"


def download(url, out_dir, name_hint, idx):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200 or not r.content:
            return None, f"HTTP {r.status_code}"
        ext = _ext_from(url, r.headers.get("Content-Type"))
        safe = "".join(c for c in (name_hint or "thumb") if c.isalnum() or c in "-_")[:24] or "thumb"
        fn = os.path.join(out_dir, f"{safe}_{idx}{ext}")
        with open(fn, "wb") as f:
            f.write(r.content)
        return os.path.abspath(fn), None
    except Exception as e:
        return None, str(e)


def main():
    ap = argparse.ArgumentParser(description="불사자 썸네일 다운로더")
    ap.add_argument("--url", "-u", nargs="+", help="다운로드할 이미지 URL(들)")
    ap.add_argument("--input", "-i", help='배치 JSON: [{"productId","url"}]')
    ap.add_argument("--out-dir", "-o", required=True, help="저장 폴더")
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
        path, err = download(url, args.out_dir, hint, idx)
        if path:
            print(path)
        else:
            print(f"FAIL\t{url}\t{err}")


if __name__ == "__main__":
    main()
