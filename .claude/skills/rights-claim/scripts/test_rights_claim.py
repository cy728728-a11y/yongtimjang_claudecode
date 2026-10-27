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


# ===========================================================================
# 오케스트레이션 — 가짜 어댑터 주입
# ===========================================================================
import fcntl  # noqa: E402
import tempfile  # noqa: E402
import textwrap  # noqa: E402

ALLOWED_TOOLS = {"bulsaja_product_find_by_code", "bulsaja_market_delete", "bulsaja_my_profile"}
NOS = [n for n, _ in TARGET_TEXTS]


def good_mail(**kw):
    d = RC.parse_mail(MAIL_TEXT, to="yjzcompany", date="Mon, 26 Oct 2026 11:19:00 +0900")
    d.update(kw)
    return d


class FakeMail:
    def __init__(self, mails):
        self.mails = mails
        self.calls = 0

    def fetch(self, since_days):
        self.calls += 1
        return list(self.mails)


class FakeAside:
    def __init__(self, appeal_ok=True, lookup_text=None):
        self.appeal_ok = appeal_ok
        self.lookup_text = lookup_text
        self.calls = []
        self.closed = False

    def repl(self, title, code):
        if title == "rc-cleanup":
            self.cleaned = True
            return RC.SENTINEL + '{"ok":true}'
        self.calls.append(title)
        if title == "rc-lookup":
            return self.lookup_text if self.lookup_text is not None else lookup_output()
        if title == "rc-appeal":
            return RC.SENTINEL + json.dumps({"ok": self.appeal_ok, "url": EXPLAIN_URL, "shot": ""})
        raise AssertionError(title)

    def close(self):
        self.closed = True


class FakeCommerce:
    """상품번호 → 판매자코드 SC1..SC6. 첫 조회는 SALE, 이후(확인 폴링)는 gone 이면 사라짐."""

    def __init__(self, gone=True, missing=()):
        self.gone = gone
        self.missing = set(missing)
        self.calls = []
        self.seen = set()

    def get_product(self, market, no):
        self.calls.append((market, no))
        if no in self.missing or (no in self.seen and self.gone):
            raise RuntimeError(f"원상품번호를 찾지 못함 ({no})")
        self.seen.add(no)
        return {"originProduct": {"statusType": "SALE", "detailAttribute": {
            "sellerCodeInfo": {"sellerManagementCode": f"SC{NOS.index(no) + 1}"}}}}


class FakeBulsaja:
    """원본 P1..P6 (P6 잠금) + 같은 불사자코드 B1 의 복사본 P7(상표명)·P8(상표명, 잠금)·P9(상표명 없음)."""

    def __init__(self, nick="부킹"):
        self.nick = nick
        self.calls = []
        self.opened = self.closed = False

    def open(self):
        self.opened = True

    def close(self):
        self.closed = True

    def _item(self, i, name, lock=False, sc=None):
        return {"productId": f"P{i}", "판매자상품코드": sc or f"COPY{i}", "불사자코드": "B1",
                "상품명": name, "숨김": lock}

    def call_tool(self, name, args):
        self.calls.append((name, args))
        if name not in ALLOWED_TOOLS:
            raise AssertionError(f"허용 안 된 불사자 tool: {name}")
        if "keyword" in json.dumps(args):
            raise AssertionError("keyword 검색 금지")
        if name == "bulsaja_my_profile":
            return {"닉네임": self.nick}
        if name == "bulsaja_product_find_by_code":
            items = []
            for c in args["codes"]:
                if c.startswith("SC"):
                    i = int(c[2:])
                    items.append(self._item(i, f"물레방아 커터기 {i}", lock=(i == 6), sc=c))
                elif c == "B1":
                    items += [self._item(i, f"물레방아 커터기 {i}", lock=(i == 6), sc=f"SC{i}")
                              for i in range(1, 7)]
                    items += [self._item(7, "MULLEBANGA 테이프컷터"),
                              self._item(8, "물레방아 컷터 판매됨", lock=True),
                              self._item(9, "자동 테이프 컷팅기")]
            return {"항목": items}
        if name == "bulsaja_market_delete":
            if args.get("confirmationToken"):
                raise AssertionError("dry-run 미리보기에서 재제출 금지")
            return {"confirmationToken": "TOKEN-XYZ-123", "message": "6건 삭제 예정"}
        raise AssertionError(name)


def fake_delete_factory(fail=()):
    calls = []

    def delete_batch(mcp, pids, log=print):
        calls.append(list(pids))
        return [{"productId": p, "판정": ("실패" if p in fail else "접수"), "사유": "", "taskId": "t"}
                for p in pids]
    delete_batch.calls = calls
    return delete_batch


class Kakao:
    def __init__(self):
        self.sent = []

    def __call__(self, text, link=None):
        self.sent.append((text, link))


class OrchestrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rc-test-")
        self.aside = FakeAside()
        self.commerce = FakeCommerce()
        self.bulsaja = FakeBulsaja()
        self.delete = fake_delete_factory()
        self.kakao = Kakao()
        self.mail = FakeMail([good_mail()])

    def deps(self, **kw):
        d = dict(mail=self.mail, aside_factory=lambda: self.aside, commerce_factory=lambda: self.commerce,
                 bulsaja_factory=lambda: self.bulsaja, delete_batch=self.delete, kakao=self.kakao,
                 stores=STORES, data_root=self.tmp, sleep=lambda s: None, appeal_text="문구",
                 confirm_rounds=3, confirm_interval=0)
        d.update(kw)
        return RC.Deps(**d)

    def run_cli(self, argv, **kw):
        return RC.run(RC.build_parser().parse_args(argv), self.deps(**kw))

    def ledger(self):
        return RC.read_ledger(self.tmp)

    def test_dry_run_무쓰기(self):
        code = self.run_cli(["--dry-run"])
        self.assertEqual(code, 0)
        self.assertEqual(self.delete.calls, [])
        self.assertEqual(self.kakao.sent, [])
        self.assertEqual(self.ledger(), [])
        self.assertEqual(self.aside.calls, ["rc-lookup"])           # 조회만, 제출 X
        names = [n for n, _ in self.bulsaja.calls]
        self.assertEqual(names.count("bulsaja_market_delete"), 1)   # 미리보기 1회(재제출 X)

    def test_인자없으면_dry_run(self):
        self.assertEqual(self.run_cli([]), 0)
        self.assertEqual(self.delete.calls, [])
        self.assertEqual(self.ledger(), [])

    def test_apply_정상(self):
        code = self.run_cli(["--apply"])
        self.assertEqual(code, 0)
        self.assertEqual(len(self.delete.calls), 1)
        self.assertEqual(sorted(self.delete.calls[0]), ["P1", "P2", "P3", "P4", "P5", "P7"])
        self.assertEqual(self.aside.calls, ["rc-lookup", "rc-appeal"])
        self.assertEqual(len(self.kakao.sent), 1)
        text, link = self.kakao.sent[0]
        self.assertIn("소명 완료", text)
        self.assertIn("잠금 2", text)
        self.assertIn("복사본 1", text)
        rows = self.ledger()
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual((r["status"], r["receipt"], r["explain_no"]), ("done", "261022S506292", "261026X309964"))
        self.assertEqual((r["deleted"], r["copies"], r["locked"]), (6, 1, 2))
        self.assertTrue(r["market_confirmed"])
        self.assertNotIn("otp?code", json.dumps(r))                 # 대장엔 링크 저장 안 함
        self.assertNotIn("463355", json.dumps(r))
        self.assertTrue(self.aside.closed and self.bulsaja.closed)
        self.assertTrue(getattr(self.aside, "cleaned", False))       # 남은 소명 탭 정리

    def test_소명실패(self):
        import base64
        self.aside = FakeAside(appeal_ok=False)
        png = base64.b64encode(b"\x89PNG fake").decode()
        orig = self.aside.repl

        def repl(title, code):
            if title == "rc-appeal":
                self.aside.calls.append(title)
                return RC.SENTINEL + json.dumps({"ok": False, "error": "성공 문구 없음", "shot": png})
            return orig(title, code)
        self.aside.repl = repl
        code = self.run_cli(["--apply"])
        self.assertEqual(code, 1)
        r = self.ledger()[-1]
        self.assertEqual(r["status"], "failed")
        self.assertEqual(r["fail_stage"], "appeal")
        self.assertTrue(r["shot"].endswith(".png"))
        with open(r["shot"], "rb") as f:
            self.assertEqual(f.read(), b"\x89PNG fake")                # 스크린샷은 파이썬이 저장
        text, link = self.kakao.sent[0]
        self.assertIn("수동 처리 필요", text)
        self.assertIn("463355", text)
        self.assertEqual(link, LINK)

    def test_마켓삭제_미확인_partial(self):
        self.commerce = FakeCommerce(gone=False)
        code = self.run_cli(["--apply"])
        r = self.ledger()[-1]
        self.assertEqual(r["status"], "partial")
        self.assertFalse(r["market_confirmed"])
        self.assertTrue(r["appeal_ok"])
        self.assertIn("마켓삭제 미확인", self.kakao.sent[0][0])
        self.assertEqual(code, 1)

    def test_삭제일부실패_partial(self):
        self.delete = fake_delete_factory(fail={"P7"})
        self.run_cli(["--apply"])
        r = self.ledger()[-1]
        self.assertEqual(r["status"], "partial")
        self.assertEqual(r["deleted"], 5)

    def test_partial_재시도는_소명_재제출_안함(self):
        self.commerce = FakeCommerce(gone=False)
        self.run_cli(["--apply"])
        self.assertEqual(self.ledger()[-1]["status"], "partial")
        # 다음날: 마켓 삭제 반영됨 → 저장된 대상으로 처리, Aside 안 띄움
        self.aside = FakeAside()
        self.commerce = FakeCommerce(gone=True)
        self.run_cli(["--apply"])
        self.assertEqual(self.aside.calls, [])
        self.assertEqual(self.ledger()[-1]["status"], "done")

    def test_done_건너뜀(self):
        RC.ledger_append(self.tmp, {"receipt": "261022S506292", "status": "done"})
        code = self.run_cli(["--apply"])
        self.assertEqual(code, 0)
        self.assertEqual(self.aside.calls, [])
        self.assertEqual(self.kakao.sent, [])
        self.assertEqual(len(self.ledger()), 1)

    def test_receipt_지정은_done_무시(self):
        RC.ledger_append(self.tmp, {"receipt": "261022S506292", "status": "done"})
        self.mail = FakeMail([good_mail(), good_mail(receipt="999999X000001")])
        code = self.run_cli(["--dry-run", "--receipt", "261022S506292"])
        self.assertEqual(code, 0)
        self.assertEqual(self.aside.calls, ["rc-lookup"])            # 지정 건 1건만

    def test_mark_done_외부호출0(self):
        def boom():
            raise AssertionError("외부 호출 금지")
        code = self.run_cli(["--mark-done", "261022S506292"], mail=None, aside_factory=boom,
                            commerce_factory=boom, bulsaja_factory=boom, kakao=boom)
        self.assertEqual(code, 0)
        r = self.ledger()[-1]
        self.assertEqual((r["receipt"], r["status"], r["source"]), ("261022S506292", "done", "manual"))

    def test_원상품번호없음_기삭제(self):
        self.commerce = FakeCommerce(missing={NOS[0]})
        self.run_cli(["--apply"])
        r = self.ledger()[-1]
        self.assertEqual(r["already_deleted"], 1)
        find_codes = [a["codes"] for n, a in self.bulsaja.calls if n == "bulsaja_product_find_by_code"][0]
        self.assertNotIn("SC1", find_codes)
        self.assertIn("rc-appeal", self.aside.calls)

    def test_no_browser_dry_run_은_불사자_커머스_미호출(self):
        code = self.run_cli(["--dry-run", "--no-browser"])
        self.assertEqual(code, 0)
        self.assertEqual(self.aside.calls, [])
        self.assertEqual(self.commerce.calls, [])
        self.assertEqual(self.bulsaja.calls, [])

    def test_계정불일치(self):
        self.bulsaja = FakeBulsaja(nick="용팀장")
        code = self.run_cli(["--apply"])
        self.assertEqual(code, 3)
        self.assertEqual(self.delete.calls, [])
        self.assertNotIn("rc-appeal", self.aside.calls)               # 삭제 못 했으면 소명 안 함
        self.assertEqual(self.ledger()[-1]["status"], "failed")
        self.assertEqual(len(self.kakao.sent), 1)

    def test_스토어명_불일치_폴백(self):
        self.run_cli(["--dry-run"], stores={"25-1": {"name": "다른스토어"}, "25-9": {"name": "또다른"}})
        self.assertGreaterEqual(len(self.commerce.calls), 6)

    def test_메일0건(self):
        self.mail = FakeMail([])
        self.assertEqual(self.run_cli(["--apply"]), 0)
        self.assertEqual(self.kakao.sent, [])

    def test_파싱실패_메일은_실패보고(self):
        self.mail = FakeMail([RC.parse_mail(MAIL_TEXT.replace("463355", ""))])
        code = self.run_cli(["--apply"])
        self.assertEqual(code, 1)
        self.assertEqual(self.aside.calls, [])
        self.assertEqual(self.ledger()[-1]["fail_stage"], "mail")

    def test_동시실행_락(self):
        d = os.path.join(self.tmp, "rights-claim")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, ".lock"), "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual(self.run_cli(["--dry-run"]), 4)

    def test_js_는_json_이스케이프(self):
        js = RC.js_appeal(LINK, "463355", '줄1\n"따옴표"', "/tmp/x.png")
        self.assertIn(json.dumps('줄1\n"따옴표"', ensure_ascii=False), js)
        self.assertIn("###RC###", js)
        self.assertNotIn("ref=", js)
        self.assertNotIn("getByPlaceholder", js)                      # Aside Playwright 판에 없음
        self.assertIn("globalThis.rcLink === LINK", js)               # 다른 건 페이지 재사용 금지
        self.assertIn(json.dumps(LINK), RC.js_lookup(LINK, "463355"))


class AsideClientTest(unittest.TestCase):
    """가짜 stdio MCP 서버로 핸드셰이크·id 매칭·통지/로그 줄 무시를 확인."""

    SERVER = textwrap.dedent(r"""
        import json, sys
        for line in sys.stdin:
            msg = json.loads(line)
            if msg.get("method") == "initialize":
                print(json.dumps({"jsonrpc": "2.0", "method": "notifications/message", "params": {}}), flush=True)
                print(json.dumps({"jsonrpc": "2.0", "id": msg["id"],
                                  "result": {"protocolVersion": "2025-06-18"}}), flush=True)
            elif msg.get("method") == "notifications/initialized":
                open(sys.argv[1], "w").write("init")
            elif msg.get("method") == "tools/call":
                a = msg["params"]["arguments"]
                print("not json log line", flush=True)
                print(json.dumps({"jsonrpc": "2.0", "id": 999, "result": {}}), flush=True)
                err = a["title"] == "bad"
                print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": {"isError": err, "content": [
                    {"type": "text", "text": "Opened a new tab"},
                    {"type": "text", "text": "###RC###" + json.dumps({"echo": a["code"]})}]}}), flush=True)
    """)

    def test_핸드셰이크와_호출(self):
        d = tempfile.mkdtemp()
        srv = os.path.join(d, "srv.py")
        flag = os.path.join(d, "flag")
        with open(srv, "w") as f:
            f.write(self.SERVER)
        c = RC.AsideMCP(cmd=[sys.executable, "-I", srv, flag], timeout=10)
        try:
            c.open()
            out = c.repl("t", "1+1")
            self.assertEqual(RC._sentinel_payload(out), {"echo": "1+1"})
            with open(flag) as f:
                self.assertEqual(f.read(), "init")
            with self.assertRaises(RuntimeError):
                c.repl("bad", "x")
        finally:
            c.close()


if __name__ == "__main__":
    unittest.main()
