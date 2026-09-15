# -*- coding: utf-8 -*-
"""stitch.py 단위 테스트 (네트워크·MCP 없이 로컬 실행). 실행: python -m unittest test_stitch -v"""
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

import stitch


class NaturalSortTests(unittest.TestCase):
    def test_numeric_order(self):
        names = ["10.jpg", "2.jpg", "1.jpg", "a.png"]
        names.sort(key=lambda n: stitch._natural_key(n))
        self.assertEqual(names, ["1.jpg", "2.jpg", "10.jpg", "a.png"])


class ZipFilterTests(unittest.TestCase):
    def test_images_only_and_sorted(self):
        with TemporaryDirectory() as td:
            zip_path = Path(td) / "sample.zip"
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("10.jpg", b"fake10")
                zf.writestr("2.jpg", b"fake2")
                zf.writestr("1.jpg", b"fake1")
                zf.writestr("notes.txt", b"not an image")
                zf.writestr("__MACOSX/._1.jpg", b"junk")
            items = stitch.list_zip_images_sorted(zip_path)
            self.assertEqual([n for n, _ in items], ["1.jpg", "2.jpg", "10.jpg"])


class ResizeTests(unittest.TestCase):
    def test_keeps_aspect_ratio(self):
        img = Image.new("RGB", (1200, 1600), "white")
        out = stitch.resize_to_width(img, 860)
        self.assertEqual(out.width, 860)
        # 1200x1600 -> 860 폭이면 높이는 약 1147
        self.assertTrue(abs(out.height - 1147) <= 1)


class ChunkByHeightTests(unittest.TestCase):
    def test_splits_on_image_boundaries(self):
        imgs = [Image.new("RGB", (860, h)) for h in (5000, 6000, 7000, 4000)]
        chunks = stitch.chunk_by_height(imgs, max_height=15000)
        # 5000+6000=11000(ok), +7000=18000>15000 이라 여기서 끊고,
        # 7000+4000=11000 은 15000 이내라 한 묶음
        self.assertEqual([len(c) for c in chunks], [2, 2])
        self.assertEqual([sum(im.height for im in c) for c in chunks], [11000, 11000])

    def test_single_oversized_image_is_its_own_chunk(self):
        imgs = [Image.new("RGB", (860, 20000)), Image.new("RGB", (860, 1000))]
        chunks = stitch.chunk_by_height(imgs, max_height=15000)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(len(chunks[0]), 1)


class StitchVerticalTests(unittest.TestCase):
    def test_canvas_size(self):
        imgs = [
            Image.new("RGB", (860, 300), "red"),
            Image.new("RGB", (860, 500), "green"),
            Image.new("RGB", (860, 200), "blue"),
        ]
        canvas = stitch.stitch_vertical(imgs)
        self.assertEqual(canvas.size, (860, 1000))
        # 이어붙인 순서대로 y좌표에 색이 있는지 샘플 확인
        self.assertEqual(canvas.getpixel((0, 0)), (255, 0, 0))
        self.assertEqual(canvas.getpixel((0, 300)), (0, 128, 0))
        self.assertEqual(canvas.getpixel((0, 800)), (0, 0, 255))


class SizeClampTests(unittest.TestCase):
    def test_small_image_stays_png(self):
        with TemporaryDirectory() as td:
            img = Image.new("RGB", (100, 100), "white")
            out_path, ext = stitch.save_under_size_limit(
                img, Path(td) / "out", max_bytes=8 * 1024 * 1024)
            self.assertEqual(ext, "png")
            self.assertTrue(Path(out_path).exists())

    def test_falls_back_to_jpeg_when_png_too_big(self):
        with TemporaryDirectory() as td:
            # 압축이 잘 안 되는 랜덤 노이즈 이미지로 PNG 용량을 강제로 키운다
            import random
            random.seed(0)
            w, h = 500, 500
            img = Image.new("RGB", (w, h))
            img.putdata([
                (random.randrange(256), random.randrange(256), random.randrange(256))
                for _ in range(w * h)
            ])
            out_path, ext = stitch.save_under_size_limit(
                img, Path(td) / "out", max_bytes=120_000)  # PNG로는 절대 안 들어가는 크기
            self.assertEqual(ext, "jpg")
            self.assertLessEqual(Path(out_path).stat().st_size, 120_000)

    def test_raises_when_even_min_quality_too_big(self):
        with TemporaryDirectory() as td:
            img = Image.new("RGB", (500, 500), "white")
            with self.assertRaises(RuntimeError):
                stitch.save_under_size_limit(img, Path(td) / "out", max_bytes=10)


if __name__ == "__main__":
    unittest.main()
