#!/usr/bin/env python3
"""Step 0 인벤토리 CLI 테스트 — 지키려는 계약:
  1. collect 는 이미 받은 그룹 파일을 건너뛴다(재시작 = 이어서)
  2. ensure 는 청크 단위로 돌고, 연속 전멸 청크가 이어지면 중단한다(서버 장애 방어)
  3. build 산출물(codes/reps/no_code/stats)이 dedup 결과와 일치한다
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from eroomlib.runner import inventory  # noqa: E402
from eroomlib import dedup, snapshot  # noqa: E402


class FakeMCP:
    def __init__(self):
        self.groups = [{"groupId": 11, "그룹명": "1번_테스트"}]
        self.items = {11: [{"productId": "P1", "상품명": "가", "상태코드": 1},
                           {"productId": "P2", "상품명": "나", "상태코드": 1},
                           {"productId": "P3", "상품명": "다", "상태코드": 1}]}
        # P3 이 있어야 chunk=1 로 청크 3개가 생겨 연속전멸 3회 중단 테스트가 성립
        self.collect_calls = []

    def open(self):
        pass

    def close(self):
        pass

    def call_tool(self, name, payload):
        assert name == "bulsaja_market_groups"
        return {"그룹": self.groups}

    def collect_group(self, gid, page_size=50, sleep=0.3, log=None):
        self.collect_calls.append(gid)
        return self.items[gid]

    def workdata(self, pid, mode="full"):
        return {"productId": pid, "상품명": "x", "원문명": "", "옵션명": [],
                "옵션명원문": [], "옵션이미지": [], "기존카테고리": "미설정",
                "썸네일": [], "원본링크": "", "불사자코드": f"C-{pid}",
                "타오바오상품번호": "700"}


class InvBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="inv-test-")
        self._root, inventory._ROOT_OVERRIDE = inventory._ROOT_OVERRIDE, self.tmp
        self._snap, snapshot.root = snapshot.root, lambda: os.path.join(self.tmp, "_snap")

    def tearDown(self):
        inventory._ROOT_OVERRIDE = self._root
        snapshot.root = self._snap


class CollectTest(InvBase):
    def test_이미_받은_그룹은_건너뛴다(self):
        mcp = FakeMCP()
        inventory.run_collect(mcp, filter_=None, force=False, sleep=0, log=None, all_groups=True)
        inventory.run_collect(mcp, filter_=None, force=False, sleep=0, log=None, all_groups=True)
        self.assertEqual(mcp.collect_calls, [11], "재시작인데 다시 수집했다")


class ScopeTest(InvBase):
    """실측(2026-07-28)으로 드러난 gap: 불사자 계정엔 85개 그룹이 있지만 마스터 인덱스
    (00_진행 시트, 54마켓 관리 대상)엔 52개뿐이다. 필터 없이 collect 를 돌리면 엔잡곰·열·
    송·엽 같은 테스트/레거시 그룹까지 전부 수집돼 Step 0 통계가 오염된다."""

    def test_기본은_마스터인덱스_등록_그룹만_수집한다(self):
        class MultiGroupMCP(FakeMCP):
            def __init__(self):
                super().__init__()
                self.groups = [{"groupId": 11, "그룹명": "1번_테스트"},
                              {"groupId": 99, "그룹명": "9번_레거시테스트"}]
                self.items[99] = [{"productId": "X1", "상품명": "z", "상태코드": 1}]
        mcp = MultiGroupMCP()
        orig = inventory._tracked_group_names
        inventory._tracked_group_names = lambda: {"1번_테스트"}
        try:
            inventory.run_collect(mcp, filter_=None, force=False, sleep=0, log=None)
        finally:
            inventory._tracked_group_names = orig
        self.assertEqual(mcp.collect_calls, [11],
                         "마스터 인덱스에 없는 그룹까지 수집했다")

    def test_all_groups_옵션이면_마스터인덱스와_무관하게_전체를_수집한다(self):
        class MultiGroupMCP(FakeMCP):
            def __init__(self):
                super().__init__()
                self.groups = [{"groupId": 11, "그룹명": "1번_테스트"},
                              {"groupId": 99, "그룹명": "9번_레거시테스트"}]
                self.items[99] = [{"productId": "X1", "상품명": "z", "상태코드": 1}]
        mcp = MultiGroupMCP()
        orig = inventory._tracked_group_names
        inventory._tracked_group_names = lambda: {"1번_테스트"}
        try:
            inventory.run_collect(mcp, filter_=None, force=False, sleep=0, log=None,
                                  all_groups=True)
        finally:
            inventory._tracked_group_names = orig
        self.assertEqual(set(mcp.collect_calls), {11, 99})


class EnsureTest(InvBase):
    def test_연속_전멸_청크_3회면_중단한다(self):
        class DeadMCP(FakeMCP):
            def workdata(self, pid, mode="full"):
                raise RuntimeError("서버 다운")
        mcp = DeadMCP()
        inventory.run_collect(mcp, filter_=None, force=False, sleep=0, log=None, all_groups=True)
        with self.assertRaises(inventory.ConsecutiveFailure):
            inventory.run_ensure(mcp, chunk=1, sleep=0, log=None, max_dead_chunks=3)

    def test_캐시적중이_섞여도_전멸_판정이_무력화되지_않는다(self):
        # 피어리뷰 지적 재현: 청크마다 캐시 적중 1건(네트워크 시도 0) + 실패 1건이 섞이면,
        # 실제 네트워크 신호는 매 청크 "100% 전멸"인데 len(errs)==len(part) 로만 판정하면
        # 1==2 라 전멸로 안 잡힌다. 3청크 연속으로 이 패턴이 반복돼도 dead_streak 이
        # 안 오르면 서버 장애를 영영 못 잡는다.
        class HalfDeadMCP:
            def __init__(self):
                self.groups = [{"groupId": 11, "그룹명": "1번_테스트"}]
                self.items = {11: [{"productId": f"P{i}", "상품명": "x", "상태코드": 1}
                                   for i in range(1, 7)]}  # P1..P6

            def open(self):
                pass

            def close(self):
                pass

            def call_tool(self, name, payload):
                return {"그룹": self.groups}

            def collect_group(self, gid, page_size=50, sleep=0.3, log=None):
                return self.items[gid]

            def workdata(self, pid, mode="full"):
                if int(pid[1:]) % 2 == 0:  # 짝수 pid 는 매번 실패
                    raise RuntimeError("서버 다운")
                return {"productId": pid, "상품명": "x", "원문명": "", "옵션명": [],
                        "옵션명원문": [], "옵션이미지": [], "기존카테고리": "미설정",
                        "썸네일": [], "원본링크": "", "불사자코드": f"C-{pid}",
                        "타오바오상품번호": "700"}

        mcp = HalfDeadMCP()
        inventory.run_collect(mcp, filter_=None, force=False, sleep=0, log=None, all_groups=True)
        # 홀수 pid(P1,P3,P5) 를 미리 캐시시켜, 이후 chunk=2 순회마다
        # "캐시 적중 1(홀수) + 매번 실패 1(짝수)" 패턴이 반복되게 만든다
        snapshot.ensure(["P1", "P3", "P5"], mcp=mcp, sleep=0, log=None)
        with self.assertRaises(inventory.ConsecutiveFailure):
            inventory.run_ensure(mcp, chunk=2, sleep=0, log=None, max_dead_chunks=3)


class BuildTest(InvBase):
    def test_build_산출물이_계약대로_나온다(self):
        mcp = FakeMCP()
        inventory.run_collect(mcp, filter_=None, force=False, sleep=0, log=None, all_groups=True)
        inventory.run_ensure(mcp, chunk=10, sleep=0, log=None)
        out = inventory.run_build(done_counts={}, log=None)
        codes = dedup.load_json(
            os.path.join(inventory._root(), "inventory", "codes.json"), None)
        self.assertEqual({i["productId"] for i in codes["tb:700"]}, {"P1", "P2", "P3"})
        self.assertEqual(out["stats"]["유니크수"], 1)
        reps = dedup.load_json(
            os.path.join(inventory._root(), "inventory", "reps.json"), None)
        self.assertEqual(reps["tb:700"], "P1")


class TargetsTest(InvBase):
    def test_targets는_카테고리완료이고_상품명미착수인_대표만_고른다(self):
        base = os.path.join(inventory._root(), "inventory")
        dedup.save_json(os.path.join(base, "reps.json"),
                        {"tb:1": "P1", "tb:2": "P2", "tb:3": "P3"})
        dedup.save_json(os.path.join(base, "codes.json"), {
            "tb:1": [{"productId": "P1", "groupId": 11, "그룹명": "1번_테스트",
                      "상태코드": 1, "불사자코드": ""}],
            "tb:2": [{"productId": "P2", "groupId": 11, "그룹명": "1번_테스트",
                      "상태코드": 1, "불사자코드": ""}],
            "tb:3": [{"productId": "P3", "groupId": 11, "그룹명": "1번_테스트",
                      "상태코드": 1, "불사자코드": ""}]})
        dedup.save_json(os.path.join(base, "same_group_dups.json"), {"tb:3": {"11": ["P3", "P9"]}})
        fake_matrix = {
            "P1": {"카테고리": "완료", "상품명": ""},        # 대상
            "P2": {"카테고리": "", "상품명": ""},            # 카테고리 미완 → 제외
            "P3": {"카테고리": "완료", "상품명": ""},        # 동일그룹중복 → 제외
        }
        out = inventory.run_targets(
            "상품명",
            read_matrix=lambda: ({"1번_테스트": "SHEET1"}, fake_matrix),
            log=None)
        self.assertEqual([t["productId"] for t in out["targets"]], ["P1"])
        sm = dedup.load_json(os.path.join(base, "sheet_map.json"), {})
        self.assertEqual(sm["P1"]["sheet"], "SHEET1")
        exc = dedup.load_json(os.path.join(base, "targets_excluded.json"), [])
        self.assertEqual({e["productId"] for e in exc}, {"P2", "P3"})

    def test_시트를_못_찾은_대상은_targets에서_제외되고_사유가_남는다(self):
        # 피어리뷰 지적: 경고만 찍고 targets 에 남기면, 판단 비용을 다 쓴 뒤
        # append 단계에서야 전체가 막힌다 — 여기서 걸러야 싸다.
        base = os.path.join(inventory._root(), "inventory")
        dedup.save_json(os.path.join(base, "reps.json"), {"tb:1": "P1"})
        dedup.save_json(os.path.join(base, "codes.json"), {
            "tb:1": [{"productId": "P1", "groupId": 99, "그룹명": "개명된그룹",
                      "상태코드": 1, "불사자코드": ""}]})
        dedup.save_json(os.path.join(base, "same_group_dups.json"), {})
        out = inventory.run_targets(
            "상품명",
            # 마스터 인덱스에 "개명된그룹"이 없다(그룹명 불일치) → sheet="" 가 된다
            read_matrix=lambda: ({}, {"P1": {"카테고리": "완료", "상품명": ""}}),
            log=None)
        self.assertEqual(out["targets"], [])
        exc = dedup.load_json(os.path.join(base, "targets_excluded.json"), [])
        self.assertEqual(exc[0]["productId"], "P1")
        self.assertIn("시트없음", exc[0]["사유"])
        sm = dedup.load_json(os.path.join(base, "sheet_map.json"), {})
        self.assertNotIn("P1", sm)

    def test_모르는_작업이름은_거부한다(self):
        with self.assertRaises(KeyError):
            inventory.run_targets("옵션정리", read_matrix=lambda: ({}, {}), log=None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
