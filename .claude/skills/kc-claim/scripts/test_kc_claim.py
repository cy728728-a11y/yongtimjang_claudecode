"""kc-claim 순수함수 테스트."""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_kc_claim as K

BODY = ("<html><body><p>KC인증 민원이 접수되어 안내 드립니다</p><table><tr><td>상품번호</td><td>13809792787</td></tr>"
        "<tr><td>상품URL</td><td><a href='https://smartstore.naver.com/main/products/13809792787'>"
        "https://smartstore.naver.com/main/products/13809792787</a></td></tr>"
        "<tr><td>소명기간</td><td>2026년 11월 19일 목요일</td></tr></table></body></html>")


class T(unittest.TestCase):
    def test_parse(self):
        r = K.parse_kc_mail(BODY)
        self.assertEqual(r["nos"], ["13809792787"])
        self.assertEqual(r["deadline"], "2026년 11월 19일")

    def test_parse_empty(self):
        self.assertEqual(K.parse_kc_mail("안녕하세요")["nos"], [])

    def test_is_kc(self):
        self.assertTrue(K.is_kc_mail('"네이버" <help_safety_shopping@navercorp.com>', "[네이버 쇼핑 안전거래센터] KC인증 소명접수 안내"))
        self.assertFalse(K.is_kc_mail("x@navercorp.com", "KC인증"))

    def test_siblings_all_except_originals(self):
        items = [{"productId": "a", "상품명": "x"}, {"productId": "b", "상품명": "y"}, {"productId": "a"}]
        self.assertEqual([i["productId"] for i in K.all_siblings(items, [], {"b"})], ["a"])

    def test_last_status(self):
        rows = [{"no": "1", "status": "failed"}, {"no": "1", "status": "done"}]
        self.assertEqual(K.last_status(rows, "1"), "done")
        self.assertEqual(K.last_status(rows, "2"), "")


if __name__ == "__main__":
    unittest.main()
