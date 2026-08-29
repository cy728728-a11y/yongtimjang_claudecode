#!/usr/bin/env python3
"""⑥ 꺼진 소재 삭제 회귀 테스트 — 네트워크 없이 돈다.

DELETE_REASONS 는 검수중·검수거부 소재가 영구 삭제되지 않게 막는 유일한 장치이고,
delete_ads 의 재개 로직(200/204/404 만 done)은 되돌릴 수 없는 삭제를 다루므로 가장
조심할 곳이다. Critical 3(오래된 스냅샷으로 삭제)도 여기서 재현·검증한다.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prune  # noqa: E402


def ad(ad_id, enable=True, reason=None, mall_id="m1", ref_key="ref1", group_id="g1"):
    return {"nccAdId": ad_id, "nccAdgroupId": group_id, "enable": enable,
            "statusReason": reason, "referenceKey": ref_key, "type": "SHOPPING_PRODUCT_AD",
            "adAttr": {"bidAmt": 100}, "status": "ELIGIBLE", "inspectStatus": "APPROVED",
            "regTm": "2026-01-01", "editTm": "2026-08-01",
            "referenceData": {"mallProductId": mall_id, "productTitle": "상품"}}


class TestDeletable(unittest.TestCase):
    def test_연동끊김_꺼짐만_통과한다(self):
        ads = [ad("a", enable=False, reason="AD_ABNORMAL_INTERLOCK")]
        self.assertEqual([a["nccAdId"] for a in prune.deletable(ads)], ["a"])

    def test_검수중은_제외한다(self):
        ads = [ad("a", enable=False, reason="AD_UNDER_REVIEW")]
        self.assertEqual(prune.deletable(ads), [])

    def test_검수거부는_제외한다(self):
        ads = [ad("a", enable=False, reason="AD_DISAPPROVED")]
        self.assertEqual(prune.deletable(ads), [])

    def test_켜져있으면_사유가_같아도_제외한다(self):
        ads = [ad("a", enable=True, reason="AD_ABNORMAL_INTERLOCK")]
        self.assertEqual(prune.deletable(ads), [])

    def test_섞여있으면_대상만_고른다(self):
        ads = [ad("a", enable=False, reason="AD_ABNORMAL_INTERLOCK"),
               ad("b", enable=False, reason="AD_UNDER_REVIEW"),
               ad("c", enable=True, reason=None),
               ad("d", enable=False, reason="AD_ABNORMAL_INTERLOCK")]
        self.assertEqual({a["nccAdId"] for a in prune.deletable(ads)}, {"a", "d"})


class TestBackup(unittest.TestCase):
    def test_백업_행이_재등록_키를_담는다(self):
        with tempfile.TemporaryDirectory() as t:
            ads = [ad("a", enable=False, reason="AD_ABNORMAL_INTERLOCK",
                      mall_id="mall-1", ref_key="ref-1", group_id="grp-1")]
            path = prune.backup_paused({"alias": "cy728"}, ads, Path(t))
            data = json.loads(path.read_text(encoding="utf-8"))
            row = data["ads"][0]
            self.assertEqual(row["referenceKey"], "ref-1")
            self.assertEqual(row["nccAdgroupId"], "grp-1")
            self.assertEqual(row["mallProductId"], "mall-1")

    def test_백업은_삭제대상만_담는다(self):
        with tempfile.TemporaryDirectory() as t:
            ads = [ad("a", enable=False, reason="AD_ABNORMAL_INTERLOCK"),
                   ad("b", enable=False, reason="AD_UNDER_REVIEW")]
            path = prune.backup_paused({"alias": "cy728"}, ads, Path(t))
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(len(data["ads"]), 1)
            self.assertEqual(data["ads"][0]["nccAdId"], "a")


class TestDeleteAdsResume(unittest.TestCase):
    """delete_ads 의 진행 파일 재개 로직 — 성공만 done, 하드에러는 재시도 대상."""

    def setUp(self):
        self._orig_call = prune.nvad.call
        self._orig_sleep = prune.time.sleep
        prune.time.sleep = lambda *_: None

    def tearDown(self):
        prune.nvad.call = self._orig_call
        prune.time.sleep = self._orig_sleep

    def test_성공_200_204_404는_done으로_건너뛴다(self):
        with tempfile.TemporaryDirectory() as t:
            progress = Path(t) / "progress.jsonl"
            progress.write_text(
                json.dumps({"nccAdId": "a", "status": 200}) + "\n" +
                json.dumps({"nccAdId": "b", "status": 404}) + "\n",
                encoding="utf-8")
            calls = []

            def fake_call(acct, method, path, params=None, body=None):
                calls.append(path)
                return 204, None

            prune.nvad.call = fake_call
            stat = prune.delete_ads({}, ["a", "b", "c"], progress)
            # a·b 는 이미 done 이라 다시 호출하지 않는다. c 만 새로 호출된다.
            self.assertEqual(len(calls), 1)
            self.assertIn("c", calls[0])

    def test_하드에러_400은_done이_아니라_재시도_대상이다(self):
        with tempfile.TemporaryDirectory() as t:
            progress = Path(t) / "progress.jsonl"
            # 이전 회차에 c 가 400 으로 실패해 기록됐다 — done 취급하면 영영 재시도 안 된다
            progress.write_text(json.dumps({"nccAdId": "c", "status": 400, "err": "bad"}) + "\n",
                                encoding="utf-8")
            calls = []

            def fake_call(acct, method, path, params=None, body=None):
                calls.append(path)
                return 204, None

            prune.nvad.call = fake_call
            stat = prune.delete_ads({}, ["c"], progress)
            self.assertEqual(len(calls), 1)  # c 가 다시 시도된다
            self.assertEqual(stat.get("ok"), 1)

    def test_429는_백오프후_재시도한다(self):
        with tempfile.TemporaryDirectory() as t:
            progress = Path(t) / "progress.jsonl"
            seq = [(429, "rate"), (204, None)]

            def fake_call(acct, method, path, params=None, body=None):
                return seq.pop(0)

            prune.nvad.call = fake_call
            stat = prune.delete_ads({}, ["a"], progress)
            self.assertEqual(stat.get("ok"), 1)


class TestRevivedFilter(unittest.TestCase):
    """Critical 3 — commit 직전 재확인으로 그새 되살아난 소재를 삭제 집합에서 뺀다."""

    def test_재확인에서도_여전히_삭제대상이면_그대로_남는다(self):
        stale = [ad("a", enable=False, reason="AD_ABNORMAL_INTERLOCK")]
        fresh = [ad("a", enable=False, reason="AD_ABNORMAL_INTERLOCK")]
        keep, excluded = prune.revived_filter(stale, fresh)
        self.assertEqual([a["nccAdId"] for a in keep], ["a"])
        self.assertEqual(excluded, 0)

    def test_그새_켜진_소재는_삭제_집합에서_빠진다(self):
        # 검토 기간 동안 사용자가 UI 에서 다시 켰다
        stale = [ad("a", enable=False, reason="AD_ABNORMAL_INTERLOCK")]
        fresh = [ad("a", enable=True, reason=None)]
        keep, excluded = prune.revived_filter(stale, fresh)
        self.assertEqual(keep, [])
        self.assertEqual(excluded, 1)

    def test_사유가_바뀐_소재도_빠진다(self):
        # 연동이 스스로 복구돼 사유가 바뀌었다 — 더 이상 AD_ABNORMAL_INTERLOCK 이 아니다
        stale = [ad("a", enable=False, reason="AD_ABNORMAL_INTERLOCK")]
        fresh = [ad("a", enable=False, reason="AD_UNDER_REVIEW")]
        keep, excluded = prune.revived_filter(stale, fresh)
        self.assertEqual(keep, [])
        self.assertEqual(excluded, 1)

    def test_섞여있으면_되살아난_것만_뺀다(self):
        stale = [ad("a", enable=False, reason="AD_ABNORMAL_INTERLOCK"),
                 ad("b", enable=False, reason="AD_ABNORMAL_INTERLOCK")]
        fresh = [ad("a", enable=True, reason=None),
                 ad("b", enable=False, reason="AD_ABNORMAL_INTERLOCK")]
        keep, excluded = prune.revived_filter(stale, fresh)
        self.assertEqual([a["nccAdId"] for a in keep], ["b"])
        self.assertEqual(excluded, 1)


class TestRunPruneCommitRechecks(unittest.TestCase):
    """Critical 3 재현: run_prune 이 오래된 prep 스냅샷만 보고 삭제하면 안 된다.

    prep 때는 꺼져 있던 소재가 사람 검토 기간 동안 되살아났는데, run_prune 이
    collect.fetch_ads 로 재조회 없이 스냅샷 그대로 삭제를 실행하면 되돌릴 수 없이
    지워진다 — 이 테스트는 그 사고가 재현되지 않음을 끝단(end-to-end)에서 검증한다.
    """

    def setUp(self):
        self._orig_call = prune.nvad.call
        self._orig_sleep = prune.time.sleep
        prune.time.sleep = lambda *_: None

    def tearDown(self):
        prune.nvad.call = self._orig_call
        prune.time.sleep = self._orig_sleep

    def test_그새_되살아난_소재는_delete_호출조차_안_받는다(self):
        with tempfile.TemporaryDirectory() as t:
            run_dir = Path(t) / "runs" / "2026-08-30"
            acc_dir = run_dir / "accounts" / "cy728"
            acc_dir.mkdir(parents=True)
            # prep 스냅샷: a·b 둘 다 꺼진 채(연동비정상)로 저장돼 있다
            stale_ads = [ad("a", enable=False, reason="AD_ABNORMAL_INTERLOCK"),
                        ad("b", enable=False, reason="AD_ABNORMAL_INTERLOCK")]
            (acc_dir / "ads.json").write_text(json.dumps({"ads": stale_ads}), encoding="utf-8")

            # 검토 기간 중 a 가 되살아났다(fetch_ads 재조회 결과)
            fresh_ads = [ad("a", enable=True, reason=None),
                        ad("b", enable=False, reason="AD_ABNORMAL_INTERLOCK")]
            orig_fetch = prune.collect.fetch_ads
            prune.collect.fetch_ads = lambda acct: (fresh_ads, {})

            deleted_ids = []

            def fake_call(acct, method, path, params=None, body=None):
                if method == "DELETE":
                    deleted_ids.append(path.rsplit("/", 1)[-1])
                    return 204, None
                return 200, {}

            prune.nvad.call = fake_call
            try:
                out = prune.run_prune({"alias": "cy728"}, run_dir, commit=True)
            finally:
                prune.collect.fetch_ads = orig_fetch

            # a 는 재확인 결과 살아있으니 DELETE 호출을 받으면 안 된다. b 만 지워진다.
            self.assertNotIn("a", deleted_ids)
            self.assertIn("b", deleted_ids)
            self.assertEqual(out.get("revived"), 1)

    def test_재확인_조회가_빈결과면_전량_되살아남으로_오판하지_않고_중단한다(self):
        # Minor 3 재현: collect.fetch_ads 는 예외를 던지지 않는다(nvad.call 이 모든
        # 예외를 흡수해 ([], {}) 를 돌려준다) — 인증 만료·방화벽 차단이면 이 경로로
        # 조용히 빈 리스트가 온다. 그걸 그대로 revived_filter 에 넘기면 삭제 대상
        # 전량이 "되살아나 제외"로 찍혀 운영자가 연동 문제가 저절로 풀렸다고 오독한다.
        with tempfile.TemporaryDirectory() as t:
            run_dir = Path(t) / "runs" / "2026-08-30"
            acc_dir = run_dir / "accounts" / "cy728"
            acc_dir.mkdir(parents=True)
            stale_ads = [ad("a", enable=False, reason="AD_ABNORMAL_INTERLOCK")]
            (acc_dir / "ads.json").write_text(json.dumps({"ads": stale_ads}), encoding="utf-8")

            orig_fetch = prune.collect.fetch_ads
            prune.collect.fetch_ads = lambda acct: ([], {})  # 인증 만료 등으로 빈 결과

            deleted_ids = []

            def fake_call(acct, method, path, params=None, body=None):
                if method == "DELETE":
                    deleted_ids.append(path.rsplit("/", 1)[-1])
                    return 204, None
                return 200, {}

            prune.nvad.call = fake_call
            try:
                out = prune.run_prune({"alias": "cy728"}, run_dir, commit=True)
            finally:
                prune.collect.fetch_ads = orig_fetch

            self.assertEqual(deleted_ids, [])
            self.assertEqual(out.get("aborted"), "recheck_failed")
            self.assertNotEqual(out.get("revived"), 1)  # "되살아나 제외" 로 둔갑하면 안 된다


if __name__ == "__main__":
    unittest.main(verbosity=2)
