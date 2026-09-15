# -*- coding: utf-8 -*-
"""불사자 상세페이지 리믹스 — 1회 실행 = 1상품.

GPTs로 스마트스토어용으로 이미 가공된 상세페이지 이미지 zip + 불사자 판매자상품
코드를 받아, zip 안 이미지들을 파일명 순서 그대로 가로 860px 기준 세로 이어붙여
기존 상세페이지를 교체한다.

Fatkun 다운로드·GPTs 작업 자체는 계속 수동 — 이 스크립트는 완성된 zip을 받은
이후 단계(이어붙이기 → 불사자 반영)만 자동화한다. 이미지 추가 생성 없음.

사용법:
  python run.py --code <판매자상품코드> --zip <GPTs 결과 zip 경로> [--out <출력폴더>]

Windows 콘솔: PYTHONIOENCODING=utf-8 PYTHONUTF8=1 로 실행 권장.
"""
import argparse
import hashlib
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image

import bulsaja_client
import stitch

TARGET_WIDTH = 860
MAX_BYTES = 8 * 1024 * 1024
# 실측(2026-09-04): 업로드 자체는 높이 18000까지 통과하지만(19000부터
# IMAGE_PIXEL_LIMIT 거부), 서버가 저장하는 실제 이미지는 높이 2400px 초과 시
# **조용히** 비율유지 축소해버린다(예: 860x11349 -> 182x2400, 화질 크게 저하).
# 이 축소는 에러 없이 일어나서 실측 전엔 알아챌 수 없었다 — 조각 높이를 이 축소가
# 절대 걸리지 않는 값으로 낮춰서 원본 해상도를 지킨다.
MAX_CHUNK_HEIGHT = 2300


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_final_images(zip_path, out_dir):
    """zip 안 이미지(파일명 자연정렬)를 860px 폭 세로 스티칭 → 필요시 여러 조각으로
    나눠 저장하고 경로 리스트를 순서대로 반환.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    zip_items = stitch.list_zip_images_sorted(zip_path)
    if not zip_items:
        raise RuntimeError(f"zip 안에 이미지가 없습니다: {zip_path}")

    print(f"[구성] GPTs 이미지 {len(zip_items)}장: " + ", ".join(n for n, _ in zip_items))

    resized = []
    for name, data in zip_items:
        img = Image.open(BytesIO(data)).convert("RGB")
        resized.append(stitch.resize_to_width(img, TARGET_WIDTH))

    chunks = stitch.chunk_by_height(resized, MAX_CHUNK_HEIGHT)
    final_paths = []
    for i, chunk_imgs in enumerate(chunks, 1):
        canvas = stitch.stitch_vertical(chunk_imgs)
        path, ext = stitch.save_under_size_limit(
            canvas, out_dir / f"detail_final_{i}", max_bytes=MAX_BYTES)
        print(f"[조각 {i}/{len(chunks)}] {path} ({ext}, {canvas.size[0]}x{canvas.size[1]})")
        final_paths.append(path)
    return final_paths


def main():
    ap = argparse.ArgumentParser(description="불사자 상세페이지 리믹스 (1상품)")
    ap.add_argument("--code", required=True, help="불사자 판매자상품코드")
    ap.add_argument("--zip", required=True, help="GPTs 결과(스마트스토어용) zip 파일 경로")
    ap.add_argument("--out", help="출력 폴더 (기본: zip과 같은 폴더의 _remix)")
    args = ap.parse_args()

    zip_path = Path(args.zip)
    if not zip_path.exists():
        print(f"[오류] zip 파일 없음: {zip_path}")
        sys.exit(1)
    out_dir = Path(args.out) if args.out else zip_path.parent / f"{zip_path.stem}_remix"

    mcp = bulsaja_client.DetailRemixMCP()
    mcp.open()
    try:
        print(f"[조회] 상품코드 '{args.code}' → productId 확인 중...")
        product_id = mcp.find_product_id(args.code)
        print("[조회 완료] productId 확보")

        final_paths = build_final_images(zip_path, out_dir)

        files_req = []
        for i, p in enumerate(final_paths, 1):
            files_req.append({
                "clientId": f"detail_final_{i}",
                "sha256": sha256_of(p),
                "sizeBytes": Path(p).stat().st_size,
            })
        print(f"[업로드 티켓 요청] {len(files_req)}개 파일")
        ticket = mcp.request_upload_ticket(product_id, files_req)

        print("[업로드 중]")
        uploaded_urls = []
        for f, p in zip(files_req, final_paths):
            url = bulsaja_client.upload_file_with_ticket(ticket, f["clientId"], p)
            print(f"  - {p} -> {url}")
            uploaded_urls.append(url)

        html = "".join(
            f'<img src="{p}" style="width:100%;display:block;">' for p in final_paths)
        image_replacements = [
            {"source": p, "url": u} for p, u in zip(final_paths, uploaded_urls)]
        print("[상세페이지 반영 중]")
        result = mcp.apply_detail(product_id, html, image_replacements)
        print(f"[반영 완료] {str(result)[:300]}")

        print("\n=== 요약 ===")
        print(f"상품코드: {args.code}")
        print(f"최종 이미지 조각 수: {len(final_paths)}")
        for p, u in zip(final_paths, uploaded_urls):
            print(f"  {p} -> {u}")
    finally:
        mcp.close()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
