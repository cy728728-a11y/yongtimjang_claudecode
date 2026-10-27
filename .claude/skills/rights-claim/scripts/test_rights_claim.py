#!/usr/bin/env python3
"""rights-claim 단위테스트 — 네트워크 0. 실제 IMAP·Aside·커머스·불사자·카톡에 붙지 않는다.

픽스처(메일 본문·소명페이지 신고대상)는 2026-10-27 실측본을 이 파일에 리터럴로 옮겨 두어
스킬이 .planning 폴더 없이도 자립한다.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import run_rights_claim as RC  # noqa: E402

# ---------------------------------------------------------------------------
# 픽스처 — 2026-10-26 수신 메일 (Gmail 화면 복사본)
# ---------------------------------------------------------------------------
MAIL_TEXT = """[권리보호센터]권리침해로 인한 소명요청
Inbox

네이버 권리보호센터 <nv_shopping_ips@navercorp.com>
Oct 26, 2026, 11:19 AM (23 hours ago)
to yjzcompany


소명요청 안내 드립니다.


안녕하세요. 네이버 권리보호센터입니다.

판매자님의 상품을 대상으로 아래와 같이 지식재산권 침해신고가 접수되었습니다.

신고내용
신고자    [원일산업]
침해를 주장하는 권리
(권리번호)
대한민국 등록권리 (물레방아MULLEBANGA)(400231875)
해당 권리에 대한 상세한 정보는 http://www.kipris.or.kr/khome/main.jsp 에서 조회 가능 합니다.
대표접수번호    [261022S506292]
소명 페이지


OTP 코드
https://right.naver.com/otp?code=t_U3ZKnfIPWD2ATcCkEbfiV5NcBUBcY0x2khwPI6XqQ=

463355

상세한 신고에 대한 내용은 위 소명페이지에서 확인 부탁드리며,
소명메일 수신 후 "3일" 내 미소명 시 상품 조치될 수 있으며, 몰에 대한 폐쇄 조치가 진행될 수 있습니다.

상품의 수정/삭제시에도 소명요청시 이에 대한 내용 기재하시어 전달 부탁드립니다.


이상입니다. 감사합니다.
본 메일은 발신전용입니다. 서비스관련 궁금하신 사항은 고객센터를 이용해 주세요.
Copyright ⓒ NAVER Corp. All Rights Reserved.
"""

LINK = "https://right.naver.com/otp?code=t_U3ZKnfIPWD2ATcCkEbfiV5NcBUBcY0x2khwPI6XqQ="

# 같은 내용의 HTML 판 — 링크는 href 에만 있고 &amp; 이스케이프·<br>·<p> 로 감싼다
MAIL_HTML = """<html><head><style>p{color:red}</style></head><body>
<p>소명요청 안내 드립니다.</p>
<table><tr><td>신고자</td><td>[원일산업]</td></tr>
<tr><td>침해를 주장하는 권리<br>(권리번호)</td><td>대한민국 등록권리 (물레방아MULLEBANGA)(400231875)</td></tr>
<tr><td>대표접수번호</td><td>[261022S506292]</td></tr>
<tr><td>소명 페이지</td><td><a href="https://right.naver.com/otp?code=t_U3ZKnfIPWD2ATcCkEbfiV5NcBUBcY0x2khwPI6XqQ=&amp;x=1">소명 페이지 바로가기</a></td></tr>
<tr><td>OTP 코드</td><td><b>463355</b></td></tr></table>
<p>상세한 신고에 대한 내용은 위 소명페이지에서 확인 부탁드리며,<br>&quot;3일&quot; 내 미소명 시</p>
</body></html>"""

# 소명페이지(/explains/261026X309964?type=PAY) 신고대상 6건 — repl 이 내보내는 원자료 모양
TARGET_TEXTS = [
    ("13738816405", "1. 소형이동식오피스 원형회전식 물레방아커터기 산업용 자동테이프커터기 칼날"),
    ("13768713084", "2. 소형이동식오피스 양면 테이프물레방아커터기 오토 자동테이프컷팅기"),
    ("13768716294", "3. 소형이동식오피스 고온 테이프자동컷팅기 수입 물레방아커터기"),
    ("13774827166", "4. 소형이동식오피스 자동 물레방아테이프커터기 회전원판 고온 ZCUT5"),
    ("13794578944", "5. 소형이동식오피스 자동 물레방아테이프커터기 양면 테이프컷팅기 고온"),
    ("13801357968", "6. 소형이동식오피스 회전형 양면테이프기계 업소용 테이프물레방아커터기"),
]
EXPLAIN_URL = "https://right.naver.com/explains/261026X309964?type=PAY"


def lookup_output(targets=TARGET_TEXTS, url=EXPLAIN_URL):
    """repl 결과 텍스트 흉내 — 안내 줄이 섞이고 센티널 줄에만 JSON 이 있다."""
    payload = {"ok": True, "url": url, "explainNo": "261026X309964",
               "targets": [{"no": n, "text": t} for n, t in targets]}
    return "✔︎ Opened a new tab (id 7)\nsome log line\n" + RC.SENTINEL + json.dumps(payload, ensure_ascii=False) + "\n"


STORES = {"25-1": {"name": "다른스토어"}, "25-2": {"name": "소형이동식오피스"}}


# ---------------------------------------------------------------------------
# 순수함수
# ---------------------------------------------------------------------------
class ParseMailTest(unittest.TestCase):
    def check(self, d):
        self.assertNotIn("error", d)
        self.assertEqual(d["reporter"], "원일산업")
        self.assertEqual(d["right_name"], "물레방아MULLEBANGA")
        self.assertEqual(d["right_no"], "400231875")
        self.assertEqual(d["receipt"], "261022S506292")
        self.assertTrue(d["link"].startswith("https://right.naver.com/otp?code="))
        self.assertEqual(d["otp"], "463355")

    def test_텍스트판(self):
        d = RC.parse_mail(MAIL_TEXT, to="yjzcompany", date="Mon, 26 Oct 2026 11:19:00 +0900")
        self.check(d)
        self.assertEqual(d["link"], LINK)
        self.assertTrue(d["link"].endswith("="))
        self.assertEqual(d["to"], "yjzcompany")

    def test_HTML판(self):
        d = RC.parse_mail(MAIL_HTML)
        self.check(d)
        self.assertIn("&x=1", d["link"])          # &amp; 언이스케이프

    def test_필수값_누락(self):
        d = RC.parse_mail(MAIL_TEXT.replace("463355", ""))
        self.assertIn("error", d)
        self.assertIn("otp", d["error"])
        d = RC.parse_mail("아무 내용 없음")
        self.assertIn("error", d)

    def test_다른도메인_링크는_거부(self):
        bad = MAIL_TEXT.replace("https://right.naver.com/otp?code=", "https://right-naver.evil.com/otp?code=")
        d = RC.parse_mail(bad)
        self.assertIn("error", d)

    def test_html_to_text(self):
        t = RC.html_to_text("<p>a&amp;b</p><div>c<br>d</div><script>x()</script>")
        self.assertIn("a&b", t)
        self.assertIn("c\nd", t)
        self.assertNotIn("x()", t)


class IsClaimMailTest(unittest.TestCase):
    def test_판정(self):
        self.assertTrue(RC.is_claim_mail("네이버 권리보호센터 <nv_shopping_ips@navercorp.com>",
                                         "[권리보호센터]권리침해로 인한 소명요청"))
        self.assertTrue(RC.is_claim_mail("NV_SHOPPING_IPS@navercorp.com", "소명요청"))
        self.assertFalse(RC.is_claim_mail("nv_shopping_ips@navercorp.com", "[권리보호센터] 소명 접수 결과 안내"))
        self.assertFalse(RC.is_claim_mail("evil <nv_shopping_ips@navercorp.com.evil.kr>", "소명요청"))


class ParseTargetsTest(unittest.TestCase):
    def test_센티널(self):
        d = RC.parse_targets(lookup_output())
        self.assertIsNone(d["error"])
        self.assertEqual(len(d["targets"]), 6)
        self.assertEqual(d["targets"][0]["no"], "13738816405")
        self.assertEqual(d["targets"][0]["store"], "소형이동식오피스")
        self.assertTrue(d["targets"][0]["title"].startswith("원형회전식"))
        self.assertEqual(d["explain_no"], "261026X309964")

    def test_같은줄_URL_제거_중복제거(self):
        t = [("13738816405", "1. 소형이동식오피스 칼날 https://smartstore.naver.com/main/products/13738816405"),
             ("13738816405", "1. 소형이동식오피스 칼날")]
        d = RC.parse_targets(lookup_output(t))
        self.assertEqual(len(d["targets"]), 1)
        self.assertEqual(d["targets"][0]["title"], "칼날")

    def test_센티널_없음(self):
        d = RC.parse_targets("✔︎ Opened a new tab\n그냥 로그")
        self.assertEqual(d["targets"], [])
        self.assertTrue(d["error"])

    def test_repl_오류(self):
        d = RC.parse_targets(RC.SENTINEL + json.dumps({"ok": False, "error": "OTP 실패"}))
        self.assertEqual(d["targets"], [])
        self.assertIn("OTP 실패", d["error"])


class TokensCopiesTest(unittest.TestCase):
    def test_right_tokens(self):
        self.assertEqual(RC.right_tokens("물레방아MULLEBANGA"), ["물레방아", "MULLEBANGA"])
        self.assertEqual(RC.right_tokens("A 물 2024 BRAND"), ["BRAND"])

    def test_filter_copies(self):
        items = [
            {"productId": "p1", "상품명": "물레방아 커터기"},        # 원본(제외)
            {"productId": "p2", "상품명": "자동 테이프 물레 방아 컷팅기"},  # 공백 무시 → 해당
            {"productId": "p3", "상품명": "Mullebanga cutter"},     # 대소문자 무시 → 해당
            {"productId": "p3", "상품명": "Mullebanga cutter"},     # 중복
            {"productId": "p4", "상품명": "자동 테이프 컷팅기"},       # 상표명 없음 → 둔다
        ]
        out = RC.filter_copies(items, ["물레방아", "MULLEBANGA"], {"p1"})
        self.assertEqual([x["productId"] for x in out], ["p2", "p3"])

    def test_store_market(self):
        self.assertEqual(RC.store_market("소형이동식오피스", STORES), "25-2")
        self.assertEqual(RC.store_market(" 소형이동식오피스 ", {"25-2": "소형이동식오피스"}), "25-2")
        self.assertIsNone(RC.store_market("없는스토어", STORES))


class LedgerAppealReportTest(unittest.TestCase):
    def test_ledger_should_skip(self):
        rows = [{"receipt": "A", "status": "failed"}, {"receipt": "A", "status": "done"},
                {"receipt": "B", "status": "done"}, {"receipt": "B", "status": "partial"}]
        self.assertTrue(RC.ledger_should_skip(rows, "A"))
        self.assertFalse(RC.ledger_should_skip(rows, "B"))   # 마지막 행이 partial
        self.assertFalse(RC.ledger_should_skip(rows, "C"))

    def test_load_appeal_text(self):
        s = RC.load_appeal_text()
        self.assertEqual(len(s), 424)
        self.assertLessEqual(len(s), RC.APPEAL_MAX)

    def test_appeal_500자_초과(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("가" * 501)
        try:
            with self.assertRaises(AssertionError):
                RC.load_appeal_text(f.name)
        finally:
            os.unlink(f.name)

    def base(self, **kw):
        r = {"receipt": "261022S506292", "reporter": "원일산업", "right_name": "물레방아MULLEBANGA",
             "status": "done", "deleted": 6, "copies": 2, "locked": 1, "already_deleted": 0,
             "market_confirmed": True, "appeal_ok": True, "fail_stage": "", "otp": "463355", "link": LINK}
        r.update(kw)
        return r

    def test_report_성공(self):
        text, link = RC.build_report(self.base())
        for s in ("261022S506292", "원일산업", "물레방아MULLEBANGA", "삭제 6", "복사본 2", "잠금 1", "소명 완료"):
            self.assertIn(s, text)
        self.assertNotIn("463355", text)
        self.assertLessEqual(len(text), 200)

    def test_report_부분(self):
        text, _ = RC.build_report(self.base(status="partial", market_confirmed=False))
        self.assertIn("소명 완료", text)
        self.assertIn("마켓삭제 미확인", text)
        self.assertLessEqual(len(text), 200)

    def test_report_실패(self):
        text, link = RC.build_report(self.base(status="failed", appeal_ok=False, fail_stage="appeal",
                                               right_name="아주긴권리명" * 40))
        self.assertIn("수동 처리 필요", text)
        self.assertIn("appeal", text)
        self.assertIn("463355", text)
        self.assertNotIn("otp?code=", text)       # 링크는 본문이 아니라 link 인자로
        self.assertEqual(link, LINK)
        self.assertLessEqual(len(text), 200)


if __name__ == "__main__":
    unittest.main()
