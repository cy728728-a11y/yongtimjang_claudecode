# -*- coding: utf-8 -*-
"""
상세페이지 검수 준비 스크립트 (읽기 전용 — 원본 이미지는 절대 수정하지 않는다)

하는 일
1. 검수 폴더 안 이미지를 파일명 자연정렬(숫자 인식) 순서로 나열
2. 세로로 긴 이미지(860x5000 같은 것)는 그대로 읽으면 글씨가 뭉개지므로
   일정 높이(기본 1400px)씩 겹치게 잘라 작업 폴더에 저장
3. 폴더 안에 상품정보 파일(product.json / meta.json / *.txt)이 있으면 경로를 알려줌
4. 결과 목록을 JSON 으로 출력 → Claude 가 이 순서대로 한 장씩 Read 한다

사용법
  python prep.py "<검수 폴더>" [--out "<작업 폴더>"] [--tile 1400]
  (조각 기본 저장 위치: 임시폴더/detail_inspect_tiles/<폴더명>/)
"""
import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print(json.dumps({"error": "Pillow 가 없습니다. pip install pillow"}, ensure_ascii=False))
    sys.exit(1)

# 큰 이미지 경고 끄기 (상세페이지는 원래 세로로 매우 길다)
Image.MAX_IMAGE_PIXELS = None

IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
INFO_NAMES = {"product.json", "meta.json", "info.json", "product.txt", "상품정보.txt"}


def natural_key(p: Path):
    """파일명 속 숫자를 숫자로 비교 (2.jpg 가 10.jpg 보다 앞에 오도록)"""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.name)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--out", default=None, help="잘린 이미지 저장 폴더 (기본: 검수폴더/_inspect_tiles)")
    ap.add_argument("--tile", type=int, default=1400, help="자를 높이(px, 가로 860 기준)")
    ap.add_argument("--overlap", type=int, default=120, help="조각끼리 겹치는 높이 — 경계에 걸친 글씨 보호")
    args = ap.parse_args()

    folder = Path(args.folder).expanduser()
    if not folder.is_dir():
        print(json.dumps({"error": f"폴더가 없습니다: {folder}"}, ensure_ascii=False))
        sys.exit(1)

    # 잘린 조각은 검수 폴더 밖(임시 폴더)에 둔다 — 검수 폴더를 건드리지 않기 위해
    out = Path(args.out).expanduser() if args.out else Path(tempfile.gettempdir()) / "detail_inspect_tiles" / folder.name
    if out.exists():
        shutil.rmtree(out, ignore_errors=True)  # 지난번 조각이 섞이지 않게 비움

    # 하위 폴더 originals/ _apply/ _inspect_tiles/ 등은 검수 대상이 아니다 → 최상위 이미지만
    images = sorted([p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMG_EXT], key=natural_key)
    if not images:
        print(json.dumps({"error": f"이미지가 없습니다: {folder}"}, ensure_ascii=False))
        sys.exit(1)

    info_files = [str(p) for p in folder.iterdir() if p.is_file() and p.name in INFO_NAMES]

    result = {"folder": str(folder), "tile_dir": str(out), "info_files": info_files, "pages": []}

    for idx, img_path in enumerate(images, 1):
        page = {"no": idx, "file": img_path.name, "path": str(img_path), "read": []}
        try:
            with Image.open(img_path) as im:
                im.load()
                w, h = im.size
                page["size"] = f"{w}x{h}"
                # 가로를 860 으로 맞췄을 때의 높이 기준으로 자를지 판단
                scale = 860 / w if w > 860 else 1.0
                h_scaled = int(h * scale)
                if h_scaled <= args.tile + args.overlap:
                    page["read"].append(str(img_path))  # 짧으면 원본 그대로 읽음
                else:
                    out.mkdir(parents=True, exist_ok=True)
                    rgb = im.convert("RGB")
                    if scale != 1.0:
                        rgb = rgb.resize((860, h_scaled), Image.LANCZOS)
                    top, part = 0, 1
                    while top < h_scaled:
                        bottom = min(top + args.tile, h_scaled)
                        tile = rgb.crop((0, top, rgb.width, bottom))
                        tp = out / f"{idx:02d}_{img_path.stem}_{part:02d}.jpg"
                        tile.save(tp, "JPEG", quality=90)
                        page["read"].append(str(tp))
                        if bottom >= h_scaled:
                            break
                        top = bottom - args.overlap
                        part += 1
        except Exception as e:  # 깨진 파일도 목록엔 남겨 표에 '열기 실패'로 적게 한다
            page["error"] = f"열기 실패: {e}"
        result["pages"].append(page)

    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
