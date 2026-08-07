#!/usr/bin/env python3
"""captcha_relay.py 회귀 테스트 (stdlib unittest — pytest 불필요).

실행: python test_captcha_relay.py

브라우저·Aside 없이 도는 부분만 본다. 실제 캡챠 화면 캡처와 입력·제출은
실물 캡챠가 있어야 검증되므로 여기 없다(SKILL.md '검증 상태' 참조).
"""
import json
import os
import sys
import tempfile
import threading
import time
import unittest

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _reload_with_dir(d):
    """RELAY_DIR 은 import 시점에 굳으므로 환경변수를 바꾸고 다시 읽는다."""
    os.environ["CAPTCHA_RELAY_DIR"] = d
    import importlib
    import captcha_relay
    return importlib.reload(captcha_relay)


class RelayBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cr = _reload_with_dir(self.tmp.name)
        self.cr._ensure_dirs()

    def tearDown(self):
        self.tmp.cleanup()


class TestId(RelayBase):
    def test_id_는_같은_초에_불려도_안_겹친다(self):
        ids = {self.cr.new_id() for _ in range(50)}
        self.assertEqual(len(ids), 50)


class TestQuestion(RelayBase):
    def test_물음표_줄을_질문으로_고른다(self):
        text = "보안 확인을 완료해 주세요\n영수증 이미지\n가게 전화번호의 앞에서 1번째 숫자는 무엇입니까?\n입력"
        self.assertEqual(self.cr.guess_question(text),
                         "가게 전화번호의 앞에서 1번째 숫자는 무엇입니까?")

    def test_물음표가_없으면_안내문구로_폴백(self):
        self.assertEqual(self.cr.guess_question("잠시만요\n보안 확인을 완료해 주세요\n확인"),
                         "보안 확인을 완료해 주세요")

    def test_못_고르면_빈_문자열(self):
        # 빈 문자열이어야 Aside 가 스크린샷에서 직접 읽는다. 억지 추정은 오답을 부른다.
        self.assertEqual(self.cr.guess_question("상품 목록\n가격순"), "")


class TestRequest(RelayBase):
    def test_요청_파일_스키마(self):
        rid = "20260806-120000-abcd"
        p = self.cr.write_request(rid, "https://x.test", "질문?", has_png=True)
        req = json.load(open(p, encoding="utf-8"))
        self.assertEqual(req["id"], rid)
        self.assertEqual(req["screenshot"], rid + ".png")
        self.assertEqual(req["site"], "https://x.test")
        self.assertTrue(req["createdAt"].startswith("2026") or req["createdAt"][:2] == "20")

    def test_png_없으면_screenshot_키를_안_넣는다(self):
        req = json.load(open(self.cr.write_request("no-png", "s", "q", False), encoding="utf-8"))
        self.assertNotIn("screenshot", req)

    def test_tmp_파일이_남지_않는다(self):
        # Aside 가 requests/ 를 훑을 때 .tmp 를 요청으로 오인하면 안 된다.
        self.cr.write_request("atomic-1", "s", "q", False)
        self.assertEqual(sorted(os.listdir(self.cr.REQ_DIR)), ["atomic-1.json"])


class TestWait(RelayBase):
    def test_반쯤_쓰인_JSON은_다음_폴링까지_기다린다(self):
        rid = "half"
        path = os.path.join(self.cr.RES_DIR, rid + ".json")
        with open(path, "w", encoding="utf-8") as f:
            f.write('{"id": "half", "stat')          # 깨진 상태
        self.assertIsNone(self.cr.read_response(rid))
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"id": rid, "status": "answered", "answer": "6"}, f)
        self.assertEqual(self.cr.read_response(rid)["answer"], "6")

    def test_늦게_도착한_응답도_집는다(self):
        rid = "late"

        def writer():
            time.sleep(0.6)
            with open(os.path.join(self.cr.RES_DIR, rid + ".json"), "w", encoding="utf-8") as f:
                json.dump({"id": rid, "status": "answered", "answer": "7"}, f)

        threading.Thread(target=writer, daemon=True).start()
        res = self.cr.wait_response(rid, timeout=5, poll=0.2, quiet=True)
        self.assertEqual(res["answer"], "7")

    def test_타임아웃이면_None(self):
        self.assertIsNone(self.cr.wait_response("nope", timeout=0.5, poll=0.2, quiet=True))


class TestFinish(RelayBase):
    def _finish(self, res):
        import contextlib, io  # noqa: E401
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = self.cr.finish("rid", res)
        return code, json.loads(buf.getvalue())

    def test_answered면_0(self):
        code, out = self._finish({"id": "rid", "status": "answered", "answer": "6"})
        self.assertEqual(code, self.cr.EXIT_ANSWERED)
        self.assertEqual(out["answer"], "6")

    def test_needs_human이면_3(self):
        code, _ = self._finish({"id": "rid", "status": "needs_human"})
        self.assertEqual(code, self.cr.EXIT_NEEDS_HUMAN)

    def test_answered인데_answer가_비면_사람에게_넘긴다(self):
        # 빈 답을 입력창에 넣고 제출하면 캡챠를 한 번 더 태우게 된다.
        code, out = self._finish({"id": "rid", "status": "answered", "answer": ""})
        self.assertEqual(code, self.cr.EXIT_NEEDS_HUMAN)
        self.assertIn("needs_human", out["note"])

    def test_타임아웃이면_4(self):
        code, out = self._finish(None)
        self.assertEqual(code, self.cr.EXIT_TIMEOUT)
        self.assertEqual(out["status"], "timeout")


class TestCaptureGuard(RelayBase):
    def test_aside_없으면_capture가_ok_False(self):
        old = self.cr.ASIDE_BIN
        self.cr.ASIDE_BIN = "/nonexistent/aside"
        try:
            r = self.cr.run_capture("/tmp/x.png", "naver")
            self.assertFalse(r["ok"])
            self.assertIn("aside CLI 없음", r["error"])
        finally:
            self.cr.ASIDE_BIN = old


if __name__ == "__main__":
    unittest.main(verbosity=2)
