# -*- coding: utf-8 -*-
"""워터마크 스크립트 점검 — 추가 설치 없이 `python tests/test_watermark.py` 로 돌린다."""
import sys
import tempfile
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import watermark as wm  # noqa: E402


def _sample(folder, name, size=(800, 800), mode="RGB", color=(230, 230, 230)):
    """테스트용 단색 사진 한 장 만들기"""
    p = folder / name
    Image.new(mode, size, color).save(p)
    return p


def test_size_same_and_original_untouched():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        src = _sample(d, "a.jpg")
        before = src.read_bytes()
        outs = wm.process(src, "오네이")
        assert len(outs) == 1
        assert Image.open(outs[0]).size == (800, 800)
        assert src.read_bytes() == before, "원본이 바뀌면 안 됨"
        # 글자가 실제로 들어갔는지: 결과가 단색이 아니어야 함
        assert Image.open(outs[0]).convert("L").getextrema()[0] < 225


def test_broken_file_does_not_stop_others():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        _sample(d, "ok1.png")
        (d / "broken.jpg").write_bytes(b"not an image")
        _sample(d, "ok2.webp")
        outs = wm.process(d, "오네이")
        assert sorted(p.name for p in outs) == ["ok1.png", "ok2.webp"]


def test_transparent_png_to_jpg_white_background():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        src = _sample(d, "t.png", mode="RGBA", color=(0, 0, 0, 0))
        out = wm.add_watermark(Image.open(src), "오네이")
        assert out.mode == "RGB"
        assert out.getpixel((2, 2)) == (255, 255, 255), "투명 부분은 흰색이어야 함"


def test_result_folder_not_reprocessed():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        _sample(d, "a.jpg")
        wm.process(d, "오네이")
        outs = wm.process(d, "오네이")   # 두 번째 실행
        assert [p.name for p in outs] == ["a.jpg"], "결과 폴더 사진은 다시 처리하지 않음"


def test_tiny_image_long_text_and_corner():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        src = _sample(d, "tiny.jpg", size=(100, 60))
        for pos in ("center", "corner"):
            out = wm.add_watermark(Image.open(src), "아주아주긴상호명스마트스토어공식몰", position=pos)
            assert out.size == (100, 60)


def test_compare_image():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        _sample(d, "a.jpg", size=(400, 300))
        wm.process(d, "오네이", compare=True)
        cmp_ = d / wm.OUT_DIR_NAME / "비교" / "a.jpg"
        assert cmp_.exists() and Image.open(cmp_).size[0] > 800


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print(f"통과  {name}")
            except Exception as e:
                fails += 1
                print(f"실패  {name}: {e!r}")
    sys.exit(1 if fails else 0)
