# -*- coding: utf-8 -*-
"""zip 안 이미지 자연정렬 + 리사이즈(가로 고정폭) + 세로 이어붙이기 + 용량/픽셀 클램프.

네트워크·MCP 없는 순수 로직만 담는다 — 유일하게 로컬 단위테스트 가능한 부분(test_stitch.py).
"""
import io
import re
import zipfile
from pathlib import Path

from PIL import Image

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def _natural_key(name):
    """숫자 부분은 수치로, 나머지는 소문자로 비교 — '2.jpg' < '10.jpg' 가 되도록."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def list_zip_images_sorted(zip_path):
    """zip 안 이미지 파일만(확장자 필터, __MACOSX/·숨김파일 제외) 파일명 자연정렬로 반환.

    반환: [(이름, bytes), ...] — 정렬된 순서 그대로.
    """
    with zipfile.ZipFile(zip_path) as zf:
        names = [
            n for n in zf.namelist()
            if not n.endswith("/")
            and "__MACOSX" not in n
            and not Path(n).name.startswith(".")
            and Path(n).suffix.lower() in IMAGE_EXTS
        ]
        names.sort(key=lambda n: _natural_key(Path(n).name))
        return [(n, zf.read(n)) for n in names]


def resize_to_width(img, width):
    """비율을 유지한 채 가로폭을 width 로 맞춘다."""
    w, h = img.size
    if w == width:
        return img
    new_h = max(1, round(h * width / w))
    return img.resize((width, new_h), Image.LANCZOS)


def chunk_by_height(images, max_height):
    """이미지를 순서를 유지한 채, 묶음별 높이 합이 max_height 를 넘지 않게 나눈다.

    두 가지 서버 제약이 있다(실측 2026-09-01/09-04):
    1) 업로드 자체 거부: 높이 18000(폭 860 기준)까지 통과, 19000부터
       `IMAGE_PIXEL_LIMIT`으로 업로드 거부.
    2) **조용한 강제 축소**: 저장되는 실제 이미지는 높이 2400px 초과 시 에러 없이
       비율유지 축소된다(예: 860x11349 -> 182x2400 — 화질이 크게 나빠짐). 이건
       업로드가 "성공"했다고 뜨기 때문에 실제 다운로드해서 해상도를 확인하기
       전엔 알아챌 수 없다.
    실질적으로 화질을 지키려면 max_height 를 2)의 2400보다 낮게 잡아야 한다
    (run.py 는 2300 사용). 한 이미지 자체가 max_height 를 넘으면 그 이미지
    혼자 묶음이 된다(개별 이미지를 잘라 쪼개지는 않음).
    """
    if not images:
        return []
    chunks = []
    current = []
    current_h = 0
    for im in images:
        if current and current_h + im.height > max_height:
            chunks.append(current)
            current = []
            current_h = 0
        current.append(im)
        current_h += im.height
    if current:
        chunks.append(current)
    return chunks


def stitch_vertical(images):
    """폭이 같은 PIL 이미지 리스트를 위에서부터 순서대로 세로로 이어붙인다."""
    if not images:
        raise ValueError("이어붙일 이미지가 없습니다")
    width = images[0].width
    total_h = sum(im.height for im in images)
    canvas = Image.new("RGB", (width, total_h), "white")
    y = 0
    for im in images:
        canvas.paste(im.convert("RGB"), (0, y))
        y += im.height
    return canvas


def save_under_size_limit(img, out_path, max_bytes=8 * 1024 * 1024,
                           qualities=(90, 80, 70, 60, 50, 40)):
    """PNG로 먼저 시도하고, max_bytes 를 넘으면 JPEG 품질을 단계적으로 낮춰 저장한다.

    최저 품질에서도 넘으면 RuntimeError — 폭 자동 축소나 이미지 분할 같은 폴백은
    하지 않는다(YAGNI, 이례적 상황이라 사람 판단). 세로 픽셀 분할은 chunk_by_height
    가 이 함수를 부르기 전에 이미 처리한다.

    반환: (저장경로, "png"|"jpg")
    """
    out_path = Path(out_path)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    if buf.tell() <= max_bytes:
        out_path = out_path.with_suffix(".png")
        out_path.write_bytes(buf.getvalue())
        return str(out_path), "png"

    jpg_path = out_path.with_suffix(".jpg")
    for q in qualities:
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "JPEG", quality=q)
        if buf.tell() <= max_bytes:
            jpg_path.write_bytes(buf.getvalue())
            return str(jpg_path), "jpg"

    raise RuntimeError(
        f"최저 품질(q={qualities[-1]})에서도 {max_bytes}바이트를 초과합니다 "
        f"(마지막 시도 {buf.tell()}바이트). 소스 이미지 수를 줄이거나 재실행하세요."
    )
