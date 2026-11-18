# -*- coding: utf-8 -*-
"""상품 사진(썸네일)에 글자 워터마크를 넣는 스크립트.

- 원본은 절대 건드리지 않고, '워터마크_결과' 폴더에 같은 이름으로 따로 저장한다.
- 사진 한 장 또는 폴더 하나(jpg·jpeg·png·webp)를 한 번에 처리한다.

사용법:
  python watermark.py <사진 또는 폴더> [--text 오네이] [--position center|corner]
                      [--opacity 0.18] [--compare]
"""
import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageStat

# ── 기본 설정 ─────────────────────────────────────────────
FONT = Path(__file__).resolve().parents[1] / "assets" / "NanumPenScript-Regular.ttf"  # 펜글씨체(무료 폰트)
OUT_DIR_NAME = "워터마크_결과"             # 결과가 저장될 폴더 이름
EXTS = {".jpg", ".jpeg", ".png", ".webp"}  # 처리할 사진 종류
ANGLE = 18                                 # 가운데 워터마크 기울기(도)
DEFAULT_OPACITY = {"center": 0.18, "corner": 0.5}  # 가운데는 연하게, 구석은 작으니 진하게
DARK, LIGHT = (40, 38, 34), (250, 248, 244)        # 글자색 후보: 진갈색 / 아이보리


def _text_mask(text, size, angle=0):
    """글자 모양만 흰색으로 그린 흑백 그림(마스크)을 만든다. angle 만큼 돌린다."""
    font = ImageFont.truetype(str(FONT), size)
    l, t, r, b = font.getbbox(text)
    mask = Image.new("L", (r - l + 20, b - t + 20), 0)
    ImageDraw.Draw(mask).text((10 - l, 10 - t), text, font=font, fill=255)
    if angle:
        mask = mask.rotate(angle, resample=Image.BICUBIC, expand=True)
    return mask.crop(mask.getbbox() or (0, 0, 1, 1))


def add_watermark(im, text, position="center", opacity=None):
    """사진 한 장에 워터마크를 얹어 새 사진으로 돌려준다(원본 객체는 그대로)."""
    im = ImageOps.exif_transpose(im)  # 폰 사진이 옆으로 누운 채 나오지 않게 회전 정보 반영
    # 투명 배경 PNG 는 흰 배경 위에 올려서 RGB 로 바꾼다(JPG 저장 시 검게 변하는 것 방지)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        im = bg
    else:
        im = im.convert("RGB")
    W, H = im.size
    if opacity is None:
        opacity = DEFAULT_OPACITY.get(position, 0.18)

    if position == "corner":
        # 오른쪽 아래 작은 글씨: 사진 폭의 6% 크기, 여백 3%
        size = max(8, int(W * 0.06))
        mask = _text_mask(text, size)
        while (mask.width > W * 0.6 or mask.height > H * 0.3) and size > 8:  # 너무 길면 줄인다
            size -= 1
            mask = _text_mask(text, size)
        margin = int(min(W, H) * 0.03)
        x, y = max(0, W - mask.width - margin), max(0, H - mask.height - margin)
    else:
        # 가운데 대각선: 글자 크기는 사진 폭의 최대 15%, 사진 밖으로 나가면 줄인다
        size = max(8, int(W * 0.15))
        mask = _text_mask(text, size, ANGLE)
        while (mask.width > W * 0.82 or mask.height > H * 0.9) and size > 8:
            size = max(8, int(size * 0.92))
            mask = _text_mask(text, size, ANGLE)
        x, y = (W - mask.width) // 2, (H - mask.height) // 2

    # 사진 밖으로 삐져나가는 부분은 잘라낸다(아주 작은 사진 대비)
    mask = mask.crop((0, 0, min(mask.width, W - x), min(mask.height, H - y)))

    # 글자가 놓일 자리의 밝기를 보고, 더 잘 보이는 글자색을 고른다
    under = im.crop((x, y, x + mask.width, y + mask.height)).convert("L")
    brightness = ImageStat.Stat(under, mask).mean[0] if mask.getbbox() else 128
    color = DARK if brightness > 128 else LIGHT
    halo_color = LIGHT if color == DARK else DARK

    # 1) 반대색 테두리를 옅게 깔고  2) 그 위에 글자를 얹는다 → 무늬 많은 배경에서도 읽힌다
    halo = mask.filter(ImageFilter.MaxFilter(5))
    im.paste(Image.new("RGB", mask.size, halo_color), (x, y), halo.point(lambda v: round(v * opacity * 0.8)))
    im.paste(Image.new("RGB", mask.size, color), (x, y), mask.point(lambda v: round(v * opacity)))
    return im


def _targets(path):
    """처리할 사진 목록. 폴더면 바로 아래 사진만(결과 폴더는 제외)."""
    if path.is_file():
        return [path]
    return sorted(p for p in path.iterdir() if p.is_file() and p.suffix.lower() in EXTS)


def process(path, text="오네이", position="center", opacity=None, compare=False):
    """사진/폴더를 받아 워터마크 사진을 저장하고, 저장된 파일 목록을 돌려준다."""
    path = Path(path)
    base = path.parent if path.is_file() else path
    out_dir = base / OUT_DIR_NAME
    out_dir.mkdir(exist_ok=True)
    saved = []
    for src in _targets(path):
        try:
            with Image.open(src) as im:
                result = add_watermark(im, text, position, opacity)
                dst = out_dir / src.name
                result.save(dst, quality=92)
                saved.append(dst)
                if compare:  # 원본|결과 나란히 붙인 비교 이미지
                    orig = ImageOps.exif_transpose(im).convert("RGB")
                    pair = Image.new("RGB", (orig.width + result.width + 20, max(orig.height, result.height)), "white")
                    pair.paste(orig, (0, 0))
                    pair.paste(result, (orig.width + 20, 0))
                    (out_dir / "비교").mkdir(exist_ok=True)
                    pair.save(out_dir / "비교" / src.name, quality=90)
            print(f"완료  {src.name}")
        except Exception as e:  # 한 장이 깨져 있어도 나머지는 계속 처리
            print(f"건너뜀 {src.name}: {e}")
    print(f"\n총 {len(saved)}장 저장 → {out_dir}")
    return saved


def main():
    ap = argparse.ArgumentParser(description="상품 사진 글자 워터마크")
    ap.add_argument("path", help="사진 파일 또는 사진이 든 폴더")
    ap.add_argument("--text", default="오네이", help="넣을 글자(상호·상표명)")
    ap.add_argument("--position", choices=["center", "corner"], default="center",
                    help="center=가운데 대각선(기본), corner=오른쪽 아래 작은 글씨")
    ap.add_argument("--opacity", type=float, default=None, help="진하기 0~1 (기본 가운데 0.18, 구석 0.5)")
    ap.add_argument("--compare", action="store_true", help="원본|결과 비교 이미지도 저장")
    a = ap.parse_args()
    try:
        if not Path(a.path).exists():
            raise FileNotFoundError(f"경로가 없어요: {a.path}")
        process(a.path, a.text, a.position, a.opacity, a.compare)
    except Exception as e:
        print(f"오류: {e}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # 윈도우에서 한글 출력 깨짐 방지
    except Exception:
        pass
    main()
