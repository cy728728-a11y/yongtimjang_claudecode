# -*- coding: utf-8 -*-
"""option_rules 단위 테스트 — 네트워크 없음.  python -m unittest test_option_rules -v"""
import unittest

import option_rules as R

WD = {
    "uploadSkuProps": {"mainOption": {"prop_name": "색상", "values": [
        {"vid": 2, "name": "실버", "_name": "银色", "exclude": False,
         "imageUrl": "https://img.alicdn.com/bao/x.jpg"},
        {"vid": 3, "name": "골드", "_name": "金色", "exclude": False,
         "imageUrl": "https://cdn.bulsaja.com/mcp-assets/1/U01/option/abc.jpg"},
        {"vid": 4, "name": "번역본", "_name": "x", "exclude": False,
         "imageUrl": "https://cdn.bulsaja.com/sourcing-product/translated-images/U01/option-image/a.jpeg"},
        {"vid": 5, "name": "제외", "_name": "y", "exclude": True, "imageUrl": "https://img.alicdn.com/z.jpg"},
    ]}, "subOption": []},
    "uploadSkus": [{"id": "2", "urlRef": "https://img.alicdn.com/bao/tab.jpg"}, {"id": "3"}, {"id": "4"}, {"id": "5"}],
    "uploadDetailContents": {"renderContent": '<div><img src="https://cdn.bulsaja.com/a.jpg"> <img src="https://cdn.bulsaja.com/b.jpg"></div>'},
}
SPEC = {
    "product_desc": "stainless steel beverage dispenser",
    "common_texts": ['Left side vertical measurement line: "높이 58CM"'],
    "options": {"2": {"banner": "단일 헤드 8리터 - 실버"}, "3": {"banner": "단일 헤드 8리터 - 골드"}},
}


class SaleOptions(unittest.TestCase):
    def test_판매제외는_빠지고_상태가_분류된다(self):
        opts = R.sale_options(WD)
        self.assertEqual([o["vid"] for o in opts], ["2", "3", "4"])
        self.assertEqual([o["status"] for o in opts], ["원본", "기작업", "번역본"])

    def test_가격탭_주소와_상세이미지를_뽑는다(self):
        opts = R.sale_options(WD)
        self.assertEqual(opts[0]["price_tab_url"], "https://img.alicdn.com/bao/tab.jpg")
        self.assertEqual(opts[1]["price_tab_url"], "")
        self.assertEqual(R.detail_image_urls(WD), ["https://cdn.bulsaja.com/a.jpg", "https://cdn.bulsaja.com/b.jpg"])

    def test_size_기본과_허용밖(self):
        self.assertEqual(R.image_size({}), "1024x1024")
        self.assertEqual(R.image_size({"size": "1024x1536"}), "1024x1536")
        self.assertTrue(any("size" in p for p in R.validate_spec({**SPEC, "size": "512x512"}, R.sale_options(WD))))

    def test_복합옵션은_거부(self):
        wd = {"uploadSkuProps": {"mainOption": {"values": []}, "subOption": [{"x": 1}]}}
        with self.assertRaises(ValueError):
            R.sale_options(wd)


class Spec(unittest.TestCase):
    def setUp(self):
        self.opts = R.sale_options(WD)

    def test_정상_spec_통과(self):
        self.assertEqual(R.validate_spec(SPEC, self.opts), [])

    def test_없는_옵션_한자_빈_banner_잡는다(self):
        bad = {"product_desc": "x", "options": {"9": {"banner": ""}, "2": {"banner": "加厚 실버"}}}
        p = R.validate_spec(bad, self.opts)
        self.assertTrue(any("9" in x and "없다" in x for x in p))
        self.assertTrue(any("banner" in x and "비어" in x for x in p))
        self.assertTrue(any("한자" in x for x in p))

    def test_프롬프트에_banner와_공통문구와_금지문이_들어간다(self):
        pr = R.build_prompt(SPEC, "2")
        self.assertIn('1) Bottom banner: "단일 헤드 8리터 - 실버"', pr)
        self.assertIn('2) Left side vertical measurement line: "높이 58CM"', pr)
        self.assertIn("no Chinese text", pr)
        self.assertIn("stainless steel beverage dispenser", pr)
        self.assertNotIn("just photographed", pr)  # angle 미지정이면 앵글 지시 없음

    def test_angle_지정시_문구_추가(self):
        pr = R.build_prompt({**SPEC, "angle": "from a slightly higher angle"}, "2")
        self.assertIn("just photographed from a slightly higher angle", pr)

    def test_source_기본은_현재이미지_지정시_그것(self):
        o2 = self.opts[0]
        self.assertEqual(R.source_for(SPEC, o2), "https://img.alicdn.com/bao/x.jpg")
        spec = {**SPEC, "options": {"2": {"banner": "b", "source": "C:/tmp/a.jpg"}}}
        self.assertEqual(R.source_for(spec, o2), "C:/tmp/a.jpg")

    def test_기작업은_건너뛰고_force나_source면_대상(self):
        t, s = R.plan_targets(SPEC, self.opts)
        self.assertEqual([o["vid"] for o, _ in t], ["2"])
        self.assertEqual([o["vid"] for o, _ in s], ["3"])
        t, _ = R.plan_targets(SPEC, self.opts, force=True)
        self.assertEqual([o["vid"] for o, _ in t], ["2", "3"])
        spec = {**SPEC, "options": {"3": {"banner": "b", "source": "https://img.alicdn.com/orig.jpg"}}}
        t, _ = R.plan_targets(spec, self.opts)
        self.assertEqual([o["vid"] for o, _ in t], ["3"])


if __name__ == "__main__":
    unittest.main()
