#!/usr/bin/env python3
"""nvad 서명 회귀 테스트 — 네트워크 없이 돈다.

    .venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/test_nvad.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nvad  # noqa: E402


class TestSign(unittest.TestCase):
    def test_서명은_고정입력에_고정출력을_낸다(self):
        # 서명 규칙이 바뀌면 여기가 제일 먼저 깨져야 한다
        got = nvad.sign("mysecret", "1700000000000", "GET", "/ncc/campaigns")
        self.assertEqual(got, "B/g1y7zbf6v+kL+q5PyU+ptJz2bJud+PF+oGpEi4xBk=")

    def test_서명대상에_쿼리스트링이_들어가면_안된다(self):
        a = nvad.sign("s", "1", "GET", "/stats")
        b = nvad.sign("s", "1", "GET", "/stats?ids=x")
        self.assertNotEqual(a, b, "path 를 그대로 서명하므로 둘은 달라야 한다")

    def test_메서드가_다르면_서명이_다르다(self):
        self.assertNotEqual(
            nvad.sign("s", "1", "GET", "/ncc/ads"),
            nvad.sign("s", "1", "PUT", "/ncc/ads"),
        )


class TestChunks(unittest.TestCase):
    def test_100개씩_자른다(self):
        self.assertEqual([len(c) for c in nvad.chunks(list(range(250)), 100)], [100, 100, 50])

    def test_빈리스트는_아무것도_내지_않는다(self):
        self.assertEqual(list(nvad.chunks([], 100)), [])


class TestCall(unittest.TestCase):
    def test_call은_자격증명_키_누락시_예외가_아니라_0을_반환한다(self):
        # 자격증명에 api_key 키가 없음 → KeyError 발생 → (0, "KeyError: ...") 반환
        incomplete_acct = {"customer_id": 12345, "secret_key": "secret"}
        status, result = nvad.call(incomplete_acct, "GET", "/ncc/campaigns")
        self.assertEqual(status, 0)
        self.assertIsInstance(result, str)
        self.assertIn("KeyError", result)

    def test_call은_직렬화_불가능한_body에_예외가_아니라_0을_반환한다(self):
        # set은 JSON 직렬화 불가능 → TypeError 발생 → (0, "TypeError: ...") 반환
        acct = {"customer_id": 12345, "api_key": "key", "secret_key": "secret"}
        status, result = nvad.call(acct, "POST", "/test", body={"x": {1, 2}})
        self.assertEqual(status, 0)
        self.assertIsInstance(result, str)
        self.assertIn("TypeError", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
