#!/usr/bin/env python3
"""검수 페이지 렌더 테스트 — 파일 IO 없이 render() 문자열만 검사한다."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import review_html as H  # noqa: E402

SAMPLE = {
    "U01K...bar": {
        "상품명": "원목바텐의자 바체어",
        "기존대표": "https://cdn.bulsaja.com/mcp-assets/x/thumbnail/abc.jpg",
        "생성본": "https://cdn.bulsaja.com/ai-image/output/x/new.jpg",
        "후보": ["https://img.alicdn.com/a.jpg", "https://img.alicdn.com/b.jpg"],
        "재작업사유": "대표 썸네일이 검정인데 옵션에 검정 없음(호두색/원목색뿐)",
        "크레딧": 5,
    },
    "U01K...fail": {
        "상품명": "실패상품",
        "오류": "TimeoutError: 타임아웃(300s)",
    },
}


class RenderTest(unittest.TestCase):
    def test_상품별_이미지_3종이_포함된다(self):
        out = H.render(SAMPLE)
        self.assertIn("mcp-assets/x/thumbnail/abc.jpg", out)
        self.assertIn("ai-image/output/x/new.jpg", out)
        self.assertIn("img.alicdn.com/a.jpg", out)
        self.assertIn("img.alicdn.com/b.jpg", out)

    def test_재작업_사유가_보인다(self):
        out = H.render(SAMPLE)
        self.assertIn("대표 썸네일이 검정인데 옵션에 검정 없음", out)

    def test_실패건은_오류만_보이고_이미지_섹션이_없다(self):
        out = H.render(SAMPLE)
        idx = out.find("U01K...fail")
        segment = out[idx:idx + 400]
        self.assertIn("생성 실패", segment)
        self.assertIn("TimeoutError", segment)

    def test_HTML_이스케이프(self):
        data = {"pid": {"상품명": "<script>alert(1)</script>", "기존대표": "", "생성본": "",
                       "후보": []}}
        out = H.render(data)
        self.assertNotIn("<script>alert(1)</script>", out)
        self.assertIn("&lt;script&gt;", out)

    def test_빈_입력도_에러_없이_렌더된다(self):
        out = H.render({})
        self.assertIn("<html>", out)
        self.assertIn("0건", out)


class MainOptionRenderTest(unittest.TestCase):
    """대표옵션은 생성본 **바로 왼쪽**에 — 떨어져 있으면 대조가 안 된다(2026-07-30)."""

    ROW = {"상품명": "유압자키", "기존대표": "https://a/rep.jpg",
           "생성본": "https://a/gen.jpg", "후보": ["https://a/c1.jpg"],
           "대표옵션명": "3톤 기본형", "대표옵션이미지": "https://a/main.jpg"}

    def test_대표옵션_이미지와_이름이_렌더된다(self):
        out = H.render({"U01": dict(self.ROW)})
        self.assertIn("https://a/main.jpg", out)
        self.assertIn("3톤 기본형", out)

    def test_대표옵션이_생성본보다_앞에_온다(self):
        out = H.render({"U01": dict(self.ROW)})
        self.assertLess(out.index("https://a/main.jpg"), out.index("https://a/gen.jpg"),
                        "나란히 대조하려면 생성본 바로 앞이어야 한다")

    def test_대표옵션이_없으면_그_칸을_안_그린다(self):
        row = {k: v for k, v in self.ROW.items()
               if k not in ("대표옵션명", "대표옵션이미지")}
        out = H.render({"U01": row})
        self.assertNotIn("대표옵션", out)
        self.assertIn("https://a/gen.jpg", out)   # 나머지는 그대로 렌더된다

    def test_생성_실패해도_대표옵션명은_보인다(self):
        out = H.render({"U01": {"상품명": "유압자키", "대표옵션명": "3톤 기본형",
                                "오류": "타임아웃"}})
        self.assertIn("3톤 기본형", out)
        self.assertIn("타임아웃", out)

    def test_대표옵션명은_이스케이프된다(self):
        out = H.render({"U01": dict(self.ROW, 대표옵션명="<script>x</script>")})
        self.assertNotIn("<script>", out)


class BuildTest(unittest.TestCase):
    def test_파일로_저장하고_경로를_돌려준다(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            out_path = os.path.join(d, "sub", "review.html")
            result = H.build(SAMPLE, out_path)
            self.assertEqual(result, out_path)
            self.assertTrue(os.path.exists(out_path))
            with open(out_path, encoding="utf-8") as f:
                self.assertIn("바체어", f.read())


if __name__ == "__main__":
    unittest.main()
