#!/usr/bin/env python3
"""이중 키 그룹핑 테스트 — 지키려는 계약:
  1. 타오바오 상품번호가 1순위 병합 키(복사본도 재수집분도 같은 번호를 공유)
  2. 번호가 없으면 불사자코드, 둘 다 없으면 solo(자기 혼자 유니크)
  3. 필드가 결측이어도 다른 필드로 이어지면 union 병합된다(단일 키였다면 유니크가 부풀어
     M2 분기 게이트가 편향된다 — 2026-07-28 피어리뷰 지적)
  4. 대표 선정은 결정적(완료수 → 그룹명 → pid) — 같은 입력이면 항상 같은 대표
  5. 같은 그룹 안의 중복은 전파 대상이 아니라 보류 대상으로 따로 드러난다
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eroomlib import dedup  # noqa: E402


def _rec(pid, code="", pno=""):
    return {"productId": pid, "불사자코드": code, "타오바오상품번호": pno}


MEMB = {
    "P1": {"groupId": 11, "그룹명": "1번_용쌤1-1", "상태코드": 1},
    "P2": {"groupId": 22, "그룹명": "2번_용쌤2-1", "상태코드": 1},
    "P3": {"groupId": 33, "그룹명": "3번_용쌤3-1", "상태코드": 1},
    "P4": {"groupId": 11, "그룹명": "1번_용쌤1-1", "상태코드": 1},
    "P5": {"groupId": 44, "그룹명": "4번_용쌤4-1", "상태코드": 1},
}


class CodeOfTest(unittest.TestCase):
    def test_상품번호가_1순위_불사자코드가_2순위_없으면_solo(self):
        self.assertEqual(dedup.code_of(_rec("P1", "C1", "700")), "tb:700")
        self.assertEqual(dedup.code_of(_rec("P1", "C1", "")), "C1")
        self.assertEqual(dedup.code_of(_rec("P1")), "solo:P1")


class BuildTest(unittest.TestCase):
    def test_같은_번호는_코드가_달라도_한_그룹으로_묶인다(self):
        recs = {"P1": _rec("P1", "C1", "700"), "P2": _rec("P2", "C2", "700"),
                "P3": _rec("P3", "", "")}
        m = dedup.build_code_map(recs, MEMB)
        self.assertEqual({i["productId"] for i in m["tb:700"]}, {"P1", "P2"})
        self.assertIn("solo:P3", m)

    def test_번호가_결측이어도_같은_불사자코드면_병합된다(self):
        # 반례 방어(피어리뷰): 단일 키였다면 tb:700 과 C1 로 갈라져 유니크가 부풀고
        # 분기 게이트가 "중복 없음" 쪽으로 편향된다.
        recs = {"P1": _rec("P1", "C1", "700"), "P2": _rec("P2", "C1", "")}
        m = dedup.build_code_map(recs, MEMB)
        self.assertEqual({i["productId"] for i in m["tb:700"]}, {"P1", "P2"})

    def test_2단계_연쇄도_하나로_묶인다(self):
        # 전이(transitive) 병합 — union-find 의 존재 이유. 단순 "번호 버킷+코드 1회 병합"으로는
        # 이 케이스를 놓친다(피어리뷰 지적: 기존 테스트는 전부 1-hop이라 이 구멍을 못 잡았다).
        # A-B 는 코드로, B-C 는 번호로 이어지고 A-C 는 아무 키도 공유하지 않는다.
        recs = {"P1": _rec("P1", "C1", ""),      # A: 코드만
                "P2": _rec("P2", "C1", "900"),    # B: 코드+번호 — 다리
                "P3": _rec("P3", "", "900")}       # C: 번호만
        m = dedup.build_code_map(recs, MEMB)
        self.assertEqual({i["productId"] for i in m["tb:900"]}, {"P1", "P2", "P3"})

    def test_같은_그룹_내_중복이_따로_드러난다(self):
        recs = {"P1": _rec("P1", "", "700"), "P4": _rec("P4", "", "700")}
        dups = dedup.same_group_dups(dedup.build_code_map(recs, MEMB))
        self.assertEqual(dups["tb:700"][11], ["P1", "P4"])


class RepTest(unittest.TestCase):
    def test_대표는_완료수_그룹명_pid_순으로_결정적이다(self):
        recs = {"P1": _rec("P1", "", "700"), "P2": _rec("P2", "", "700"),
                "P3": _rec("P3", "", "700")}
        insts = dedup.build_code_map(recs, MEMB)["tb:700"]
        self.assertEqual(dedup.choose_representative(insts, {"P3": 2}), "P3")
        self.assertEqual(dedup.choose_representative(insts, None), "P1")


class IoTest(unittest.TestCase):
    def test_저장_후_다시_읽으면_같다(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "codes.json")
            dedup.save_json(p, {"tb:700": [1, 2]})
            self.assertEqual(dedup.load_json(p, None), {"tb:700": [1, 2]})


class ShuffleTest(unittest.TestCase):
    NAME = "이발의자 전동미용의자 업소용 높이조절 고급"
    KWS = ["이발의자", "전동미용의자"]

    def test_같은_입력은_항상_같은_결과다(self):
        a = dedup.shuffle_name(self.NAME, self.KWS, "tb:1", 22)
        b = dedup.shuffle_name(self.NAME, self.KWS, "tb:1", 22)
        self.assertEqual(a, b)

    def test_그룹이_다르면_대체로_다른_순서다(self):
        outs = {dedup.shuffle_name(self.NAME, self.KWS, "tb:1", g) for g in range(2, 30)}
        self.assertGreater(len(outs), 1)   # 순열이 갈리는지(전부 같으면 셔플이 아님)

    def test_키워드는_연속_문자열로_보존된다(self):
        out = dedup.shuffle_name(self.NAME, self.KWS, "tb:1", 23)
        for kw in self.KWS:
            self.assertIn(kw, out.replace(" ", ""))

    def test_토큰_집합은_변하지_않는다(self):
        out = dedup.shuffle_name(self.NAME, self.KWS, "tb:1", 24)
        self.assertEqual(sorted(out.split()), sorted(self.NAME.split()))

    def test_대표_그룹은_원문_그대로다(self):
        self.assertEqual(
            dedup.shuffle_name(self.NAME, self.KWS, "tb:1", 22, rep_group_id=22), self.NAME)

    def test_여러_토큰에_걸친_키워드도_인접_순서가_보존된다(self):
        # 피어리뷰 #4: 단일 토큰 픽스처만으로는 블록 매칭 루프를 지우고
        # 토큰 단위 셔플로 짜도 전부 통과한다 — 멀티토큰 키워드가 진짜 그물이다.
        name = "자바라 조립식 캐노피천막 원터치 접이식"
        kws = ["조립식 캐노피천막"]          # 토큰 2개에 걸친 키워드
        for g in range(2, 20):
            out = dedup.shuffle_name(name, kws, "tb:9", g)
            self.assertIn("조립식 캐노피천막", out,
                          f"g={g}: 키워드 블록이 쪼개졌다 → {out}")
            self.assertEqual(sorted(out.split()), sorted(name.split()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
