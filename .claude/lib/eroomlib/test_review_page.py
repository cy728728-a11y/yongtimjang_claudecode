#!/usr/bin/env python3
"""검수 페이지 공용 부품 테스트 — 파일 IO 없이 문자열만 검사한다."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eroomlib import review_page as P  # noqa: E402


class ImgTagTest(unittest.TestCase):
    def test_url과_라벨이_들어간다(self):
        out = P.img_tag("https://x/a.jpg", "기존 대표")
        self.assertIn("https://x/a.jpg", out)
        self.assertIn("기존 대표", out)

    def test_빈_url은_빈_문자열(self):
        self.assertEqual(P.img_tag("", "라벨"), "")
        self.assertEqual(P.img_tag(None, "라벨"), "")

    def test_따옴표를_이스케이프한다(self):
        out = P.img_tag('https://x/a.jpg?q="1"', '제품 "A"')
        self.assertNotIn('?q="1"', out, "URL 의 따옴표가 그대로 새어나갔다")
        self.assertIn("&quot;", out)

    def test_클래스가_붙는다(self):
        self.assertIn("gen", P.img_tag("https://x/a.jpg", "생성본", cls="gen"))


class ShellTest(unittest.TestCase):
    def test_제목과_본문이_들어간다(self):
        out = P.shell("상세 검수", ["<div>본문</div>"])
        self.assertIn("<!doctype html>", out)
        self.assertIn("<title>상세 검수</title>", out)
        self.assertIn("<div>본문</div>", out)
        self.assertIn("</html>", out)

    def test_CSS가_인라인된다(self):
        self.assertIn(P.CSS, P.shell("t", []))

    def test_카운트_라벨이_제목줄에_붙는다(self):
        self.assertIn("5건", P.shell("상세 검수", [], count_label="5건"))

    def test_뼈대_구조가_고정이다(self):
        # 스킬 둘(썸네일·상세)이 이 셸을 공유한다 — 첫 줄·마지막 줄·이음매가 바뀌면
        # 양쪽 검수 페이지가 동시에 깨진다. 그래서 구조 자체를 못박는다.
        lines = P.shell("t", ["<div>A</div>", "<div>B</div>"]).split("\n")
        self.assertTrue(lines[0].startswith("<!doctype html><html>"))
        self.assertEqual(lines[-1], "</body></html>")
        # (CSS 자체가 여러 줄이라 머리 부분의 줄 수는 세지 않는다 — 꼬리에서 센다)
        self.assertEqual(lines[-3:-1], ["<div>A</div>", "<div>B</div>"],
                         "본문 조각은 줄바꿈으로 이어붙인다")


class WriteTest(unittest.TestCase):
    def test_없는_디렉터리도_만들어_쓴다(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "sub", "review.html")
            self.assertEqual(P.write("<html></html>", path), path)
            with open(path, encoding="utf-8") as f:
                self.assertEqual(f.read(), "<html></html>")


if __name__ == "__main__":
    unittest.main()
