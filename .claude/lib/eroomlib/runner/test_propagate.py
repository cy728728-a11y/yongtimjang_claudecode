#!/usr/bin/env python3
"""propagate.py plan 단계 테스트 — 실제 시트·MCP 없이 전부 페이크 주입.

지키려는 계약:
  1. classify_matrix_value 가 이룸님 확정 표(§5) 6행을 정확히 따른다.
  2. plan 통합: 동일그룹중복 제외 · 대표미완료 스킵 · 승인보류→held ·
     이식 대상 산정 · plan.json/held.json 형식 · 쓰기 함수 0회 호출.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from eroomlib.runner import propagate  # noqa: E402
from eroomlib import dedup, matrix  # noqa: E402


# ---------------------------------------------------------------------------
# classify_matrix_value — 표(이룸님 확정, 2026-08-01) 6행 전부
# ---------------------------------------------------------------------------

class ClassifyTest(unittest.TestCase):
    def test_빈칸은_이식이다(self):
        self.assertEqual(propagate.classify_matrix_value(""), (propagate.TARGET_TRANSPLANT, ""))
        self.assertEqual(propagate.classify_matrix_value(None), (propagate.TARGET_TRANSPLANT, ""))
        self.assertEqual(propagate.classify_matrix_value("   "), (propagate.TARGET_TRANSPLANT, ""))

    def test_재작업은_이식이다(self):
        self.assertEqual(
            propagate.classify_matrix_value("재작업(옵션: 대표색 불일치)"),
            (propagate.TARGET_TRANSPLANT, ""))

    def test_자동화_보류값은_이식이다(self):
        for v in ("매칭불가", "sellha조회실패", "부분일치확인요", "보류(정체불명)"):
            with self.subTest(v=v):
                self.assertEqual(propagate.classify_matrix_value(v),
                                 (propagate.TARGET_TRANSPLANT, ""))

    def test_승인보류는_보류함이다(self):
        self.assertEqual(
            propagate.classify_matrix_value("승인보류"),
            (propagate.TARGET_HELD, "승인보류-수동승인필요"))

    def test_진행중_미반영은_보류함이다(self):
        self.assertEqual(
            propagate.classify_matrix_value("진행중(미반영)"),
            (propagate.TARGET_HELD, "미결-상품명A열충돌"))

    def test_완료와_해당없음은_스킵이다(self):
        self.assertEqual(propagate.classify_matrix_value("완료"), (propagate.TARGET_SKIP, ""))
        self.assertEqual(propagate.classify_matrix_value("해당없음"), (propagate.TARGET_SKIP, ""))

    def test_미분류_문자열은_조용히_버리지_않고_보류함으로_남는다(self):
        verdict, reason = propagate.classify_matrix_value("이상한상태값")
        self.assertEqual(verdict, propagate.TARGET_HELD)
        self.assertEqual(reason, "미분류값:이상한상태값")


# ---------------------------------------------------------------------------
# load_plan_상품명 — 대표의 마지막(최신) 반영완료 행 회수
# ---------------------------------------------------------------------------

NAME_HEADER = ["상품id", "작업일", "마켓그룹", "카테고리", "원본상품명", "새상품명",
              "키워드1", "키워드1_상품수", "키워드1_검색량",
              "키워드2", "키워드2_상품수", "키워드2_검색량",
              "term분해", "term수", "중복어", "반증", "상태", "메모"]


def _name_row(pid, new_name, kw1="", status="반영완료"):
    r = [""] * len(NAME_HEADER)
    r[NAME_HEADER.index("상품id")] = pid
    r[NAME_HEADER.index("새상품명")] = new_name
    r[NAME_HEADER.index("키워드1")] = kw1
    r[NAME_HEADER.index("상태")] = status
    return r


class LoadPlanNameTest(unittest.TestCase):
    def test_마지막_반영완료_행을_고른다(self):
        rows = [NAME_HEADER,
                _name_row("P1", "옛이름", status="생성완료"),
                _name_row("P1", "이름A", kw1="키워드A"),
                _name_row("P1", "이름B(최신)", kw1="키워드B"),
                _name_row("P9", "다른상품", kw1="다른키워드")]
        value, memo = propagate.load_plan_상품명(
            "P1", "1번_그룹",
            {"index_groups": lambda: [("1번_그룹", "SID1")],
             "read_tab": lambda sid, tab: rows if tab == "상품명" else []})
        self.assertIsNone(memo)
        self.assertEqual(value["새상품명"], "이름B(최신)")
        self.assertEqual(value["키워드"], ["키워드B"])

    def test_시트를_못_찾으면_메모를_남긴다(self):
        value, memo = propagate.load_plan_상품명(
            "P1", "없는그룹",
            {"index_groups": lambda: [("1번_그룹", "SID1")], "read_tab": lambda s, t: []})
        self.assertIsNone(value)
        self.assertIn("시트없음", memo)

    def test_반영완료_행이_없으면_메모를_남긴다(self):
        rows = [NAME_HEADER, _name_row("P1", "이름", status="생성완료")]
        value, memo = propagate.load_plan_상품명(
            "P1", "1번_그룹",
            {"index_groups": lambda: [("1번_그룹", "SID1")],
             "read_tab": lambda s, t: rows})
        self.assertIsNone(value)
        self.assertEqual(memo, "반영완료행없음")


# ---------------------------------------------------------------------------
# plan 통합 — tmpdir 가짜 inventory + 가짜 read_matrix/index_groups/read_tab
# ---------------------------------------------------------------------------

class PlanBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="propagate-test-")
        self._root, propagate._ROOT_OVERRIDE = propagate._ROOT_OVERRIDE, self.tmp
        self.base = os.path.join(self.tmp, "inventory")
        os.makedirs(self.base, exist_ok=True)
        self.run_dir = os.path.join(self.tmp, "propagate", "runs", "test")

    def tearDown(self):
        propagate._ROOT_OVERRIDE = self._root

    def _write_inventory(self, codes, reps, same_group_dups):
        dedup.save_json(os.path.join(self.base, "codes.json"), codes)
        dedup.save_json(os.path.join(self.base, "reps.json"), reps)
        dedup.save_json(os.path.join(self.base, "same_group_dups.json"), same_group_dups)


# 공통 픽스처: tb:1 = 전파 대상(대표 P1, 짝 P2) · tb:2 = 동일그룹중복(제외) ·
# tb:5 = 대표 카테고리 미완료(그 작업만 스킵)
def _base_codes():
    return {
        "tb:1": [
            {"productId": "P1", "groupId": 11, "그룹명": "1번_그룹", "상태코드": 1, "불사자코드": ""},
            {"productId": "P2", "groupId": 12, "그룹명": "2번_그룹", "상태코드": 1, "불사자코드": ""},
        ],
        "tb:2": [
            {"productId": "P3", "groupId": 11, "그룹명": "1번_그룹", "상태코드": 1, "불사자코드": ""},
            {"productId": "P4", "groupId": 11, "그룹명": "1번_그룹", "상태코드": 1, "불사자코드": ""},
        ],
        "tb:5": [
            {"productId": "P8", "groupId": 13, "그룹명": "3번_그룹", "상태코드": 1, "불사자코드": ""},
            {"productId": "P9", "groupId": 14, "그룹명": "4번_그룹", "상태코드": 1, "불사자코드": ""},
        ],
    }


_BASE_REPS = {"tb:1": "P1", "tb:2": "P3", "tb:5": "P8"}
_BASE_DUPS = {"tb:2": {"11": ["P3", "P4"]}}


def _fake_index_groups():
    """상품명 load_plan 이 실제 gws 를 타지 않게 하는 기본 페이크(빈 인덱스) —
    load_plan_상품명 은 대표의 상품명 열이 완료면 항상 호출되므로, 그 내용을 직접
    검증하지 않는 테스트에서도 반드시 주입해야 한다(안 하면 진짜 시트 호출을 시도한다)."""
    return []


def _fake_read_tab(sid, tab):
    return []


def _fake_read_matrix():
    sheets = {"1번_그룹": "SID1", "2번_그룹": "SID2", "3번_그룹": "SID3", "4번_그룹": "SID4"}
    merged = {
        "P1": {"카테고리": "완료", "상품명": "완료", "옵션": "완료", "썸네일": "완료"},
        "P2": {"카테고리": "", "상품명": "재작업(카테고리 변경)", "옵션": "승인보류", "썸네일": "매칭불가"},
        "P8": {"카테고리": "", "상품명": "완료", "옵션": "완료", "썸네일": "완료"},
        "P9": {"카테고리": "", "상품명": "", "옵션": "", "썸네일": ""},
    }
    return sheets, merged


class SameGroupExclusionTest(PlanBase):
    def test_동일그룹중복_코드는_대상에서_통째로_제외된다(self):
        self._write_inventory(_base_codes(), _BASE_REPS, _BASE_DUPS)
        out, held = propagate.run_plan(read_matrix=_fake_read_matrix,
                                       index_groups=_fake_index_groups, read_tab=_fake_read_tab,
                                       run_dir=self.run_dir, log=None)
        codes_in_plan = {e["코드"] for e in out["plan"]}
        self.assertNotIn("tb:2", codes_in_plan)
        self.assertFalse(any(h["코드"] == "tb:2" for h in held))
        self.assertEqual(out["동일그룹중복제외코드수"], 1)


class RepNotDoneTest(PlanBase):
    def test_대표미완료_작업은_스킵되고_대표완료_작업만_plan에_남는다(self):
        self._write_inventory(_base_codes(), _BASE_REPS, _BASE_DUPS)
        out, _ = propagate.run_plan(read_matrix=_fake_read_matrix,
                                    index_groups=_fake_index_groups, read_tab=_fake_read_tab,
                                    run_dir=self.run_dir, log=None)
        tb5_tasks = {e["작업"] for e in out["plan"] if e["코드"] == "tb:5"}
        # P8(대표)은 카테고리만 미완료 — 나머지 3작업(상품명·옵션·썸네일)만 plan에 남는다
        self.assertEqual(tb5_tasks, {"상품명", "옵션", "썸네일"})
        self.assertGreaterEqual(out["요약"]["대표미완료스킵"], 1)


class HeldTest(PlanBase):
    def test_승인보류는_held에_사유와_함께_남는다(self):
        self._write_inventory(_base_codes(), _BASE_REPS, _BASE_DUPS)
        # find_option_plan 을 주입해 옵션 작업의 타깃 전개를 켠다 — 미주입 기본값은
        # Important #5b(옵션 축약) 때문에 옵션 작업을 통째로 건너뛴다(별도 테스트로 검증).
        _, held = propagate.run_plan(read_matrix=_fake_read_matrix,
                                     index_groups=_fake_index_groups, read_tab=_fake_read_tab,
                                     find_option_plan=lambda pid: (None, "test-stub"),
                                     run_dir=self.run_dir, log=None)
        rec = next(h for h in held if h["productId"] == "P2" and h["작업"] == "옵션")
        self.assertEqual(rec["코드"], "tb:1")
        self.assertEqual(rec["현황판값"], "승인보류")
        self.assertEqual(rec["사유"], "승인보류-수동승인필요")


class OptionUnwiredCollapseTest(PlanBase):
    """피어리뷰 Important #5b — find_option_plan 미배선이면 옵션은 코드 단위 1행으로
    축약되고(타깃 전개 없음), held.json 에도 옵션 관련 항목이 전혀 안 생겨야 한다
    (그래야 매 재실행마다 00_보류함이 옵션 미배선건으로 무한히 쌓이는 루프가 안 생긴다)."""

    def test_find_option_plan_미배선이면_옵션은_코드단위_1행으로_축약된다(self):
        self._write_inventory(_base_codes(), _BASE_REPS, _BASE_DUPS)
        out, held = propagate.run_plan(read_matrix=_fake_read_matrix,
                                       index_groups=_fake_index_groups, read_tab=_fake_read_tab,
                                       run_dir=self.run_dir, log=None)  # find_option_plan 미주입
        opt_entries = [e for e in out["plan"] if e["코드"] == "tb:1" and e["작업"] == "옵션"]
        self.assertEqual(len(opt_entries), 1)
        self.assertEqual(opt_entries[0]["targets"], [])
        self.assertIsNone(opt_entries[0]["확정값"])
        self.assertIn("옵션런디렉토리규약미정", opt_entries[0]["메모"])
        self.assertFalse(any(h["작업"] == "옵션" for h in held))
        self.assertGreater(out["요약"]["옵션미배선스킵"], 0)


class TransplantTargetTest(PlanBase):
    def test_이식_대상이_판정과_함께_산정된다(self):
        self._write_inventory(_base_codes(), _BASE_REPS, _BASE_DUPS)
        out, _ = propagate.run_plan(read_matrix=_fake_read_matrix,
                                    index_groups=_fake_index_groups, read_tab=_fake_read_tab,
                                    run_dir=self.run_dir, log=None)
        cat_entry = next(e for e in out["plan"] if e["코드"] == "tb:1" and e["작업"] == "카테고리")
        self.assertEqual(len(cat_entry["targets"]), 1)
        t = cat_entry["targets"][0]
        self.assertEqual(t["productId"], "P2")
        self.assertEqual(t["groupId"], 12)
        self.assertEqual(t["그룹명"], "2번_그룹")
        self.assertEqual(t["판정"], propagate.TARGET_TRANSPLANT)

        name_entry = next(e for e in out["plan"] if e["코드"] == "tb:1" and e["작업"] == "상품명")
        self.assertEqual(name_entry["targets"][0]["판정"], propagate.TARGET_TRANSPLANT)  # 재작업(...)

        thumb_entry = next(e for e in out["plan"] if e["코드"] == "tb:1" and e["작업"] == "썸네일")
        self.assertEqual(thumb_entry["targets"][0]["판정"], propagate.TARGET_TRANSPLANT)  # 매칭불가


class LoadPlanIntegrationTest(PlanBase):
    def test_상품명_확정값이_대표_반영완료_행에서_채워진다(self):
        self._write_inventory(_base_codes(), _BASE_REPS, _BASE_DUPS)
        rows = [NAME_HEADER, _name_row("P1", "확정상품명", kw1="키워드1")]

        def _read_tab(sid, tab):
            return rows if tab == "상품명" else []

        out, _ = propagate.run_plan(
            read_matrix=_fake_read_matrix,
            index_groups=lambda: [("1번_그룹", "SID1")],
            read_tab=_read_tab,
            run_dir=self.run_dir, log=None)
        name_entry = next(e for e in out["plan"] if e["코드"] == "tb:1" and e["작업"] == "상품명")
        self.assertEqual(name_entry["확정값"]["새상품명"], "확정상품명")
        self.assertIsNone(name_entry["메모"])

        cat_entry = next(e for e in out["plan"] if e["코드"] == "tb:1" and e["작업"] == "카테고리")
        self.assertIsNone(cat_entry["확정값"])
        # Task5: 카테고리 load_plan 이 실구현으로 교체됨(스텁 "load_plan Task5" 소멸).
        # 이 픽스처는 대표 P1 의 스냅샷을 주입하지 않으므로(실제 snapshot.load 는 파일이
        # 없어 None) 확정 경로를 못 얻어 "확정경로없음"으로 보류한다.
        self.assertEqual(cat_entry["메모"], "확정경로없음")


class PlanShapeTest(PlanBase):
    def test_plan_json과_held_json_형식(self):
        self._write_inventory(_base_codes(), _BASE_REPS, _BASE_DUPS)
        out, held = propagate.run_plan(read_matrix=_fake_read_matrix,
                                       index_groups=_fake_index_groups, read_tab=_fake_read_tab,
                                       run_dir=self.run_dir, log=None)

        plan_path = os.path.join(self.run_dir, "plan.json")
        held_path = os.path.join(self.run_dir, "held.json")
        self.assertTrue(os.path.exists(plan_path))
        self.assertTrue(os.path.exists(held_path))

        with open(plan_path, encoding="utf-8") as f:
            saved_plan = json.load(f)
        with open(held_path, encoding="utf-8") as f:
            saved_held = json.load(f)
        self.assertEqual(saved_plan, out)
        self.assertEqual(saved_held, held)

        for key in ("생성일", "대상코드수", "동일그룹중복제외코드수", "plan", "요약"):
            self.assertIn(key, out)
        entry = out["plan"][0]
        for key in ("코드", "대표pid", "대표groupId", "작업", "확정값", "메모", "targets"):
            self.assertIn(key, entry)
        if entry["targets"]:
            t = entry["targets"][0]
            for key in ("productId", "groupId", "그룹명", "현황판값", "판정"):
                self.assertIn(key, t)
        for h in held:
            for key in ("코드", "productId", "작업", "현황판값", "사유"):
                self.assertIn(key, h)


class NoWriteTest(PlanBase):
    def test_plan은_시트_쓰기_함수를_전혀_부르지_않는다(self):
        from eroomlib import gsheets

        def _boom(*a, **k):
            raise AssertionError("plan 단계에서 쓰기 함수가 호출됐다 — 계약 위반")

        orig_update, orig_append = gsheets.sheets_update, gsheets.append_rows
        gsheets.sheets_update = _boom
        gsheets.append_rows = _boom
        try:
            self._write_inventory(_base_codes(), _BASE_REPS, _BASE_DUPS)
            propagate.run_plan(
                read_matrix=_fake_read_matrix,
                index_groups=lambda: [("1번_그룹", "SID1")],
                read_tab=lambda s, t: [NAME_HEADER, _name_row("P1", "이름")],
                run_dir=self.run_dir, log=None)
        finally:
            gsheets.sheets_update = orig_update
            gsheets.append_rows = orig_append


class CliStubTest(unittest.TestCase):
    def test_not_implemented_헬퍼는_여전히_동작한다(self):
        # Task5 에서 apply/status/retry-held 를 실구현했지만, main() 의 최종 안전망으로
        # _not_implemented 자체는 그대로 남겨둔다(Task4 테스트 계약 유지).
        for cmd in ("apply", "status", "retry-held"):
            with self.subTest(cmd=cmd):
                with self.assertRaises(SystemExit) as ctx:
                    propagate._not_implemented(cmd)
                self.assertIn("Task 5", str(ctx.exception))


# =============================================================================
# Task 5 — load_plan_카테고리/옵션/썸네일, verify/apply, ledger, 멱등, dry-run
# =============================================================================

def _fake_snapshot(store):
    return lambda pid: store.get(pid)


def _fake_snapshot_update(store):
    def _upd(pid, **fields):
        rec = store.setdefault(pid, {})
        rec.update(fields)
        return rec
    return _upd


def _read_ledger(run_dir):
    path = os.path.join(run_dir, "ledger.jsonl")
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _target(pid, group_id, group_name, val, verdict):
    return {"productId": pid, "groupId": group_id, "그룹명": group_name,
           "현황판값": val, "판정": verdict}


class _FakeMCP:
    """call_tool 호출을 기록하는 페이크 — 실제 MCP·네트워크 0.

    responses = {tool명: dict(매 호출 동일 응답) 또는 list(호출 순서대로 소비)}.
    """

    def __init__(self, responses):
        self.responses = responses
        self.calls = []
        self._idx = {}

    def call_tool(self, name, args):
        self.calls.append((name, dict(args)))
        r = self.responses.get(name)
        if isinstance(r, list):
            i = self._idx.get(name, 0)
            self._idx[name] = i + 1
            return r[min(i, len(r) - 1)]
        return r or {}

    def _confirmed_call(self, tool, payload):
        # propagate.PropagateMCP._confirmed_call 과 동일 계약(피어리뷰 반영 후):
        # 첫 호출에 confirm 을 싣지 않고, falsy 키는 제거한다.
        payload = propagate._strip_falsy(payload)
        pv = self.call_tool(tool, payload)
        token = pv.get("confirmationToken")
        if not token:
            if pv.get("success"):
                return pv
            raise RuntimeError(f"확인키 미발급({tool})")
        r = self.call_tool(tool, {**payload, "confirm": True, "confirmationToken": token})
        if not r.get("success"):
            raise RuntimeError(f"저장 실패({tool})")
        return r

    def workdata(self, pid, mode="full"):
        return {"옵션": {}}


class ApplyBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="propagate-apply-test-")
        self.run_dir = os.path.join(self.tmp, "run")
        os.makedirs(self.run_dir, exist_ok=True)

    def _write_plan(self, entries):
        dedup.save_json(os.path.join(self.run_dir, "plan.json"),
                        {"생성일": "t", "대상코드수": len(entries),
                         "동일그룹중복제외코드수": 0, "plan": entries, "요약": {}})

    @staticmethod
    def _run_apply(*args, **kwargs):
        """`propagate.run_apply` 래퍼 — Important #5a(00_보류함 대조) 가 commit=True 일 때
        `read_tab(master_sheet, "00_보류함")` 을 호출한다. 테스트가 `read_tab` 을 안 주면
        실제 `gsheets.sheets_get`(진짜 마스터 시트!)를 타 버리므로, 기본값을 빈 결과로
        고정해 명시적으로 오버라이드하지 않는 모든 호출을 네트워크 0으로 지킨다."""
        kwargs.setdefault("read_tab", lambda *a, **k: [])
        return propagate.run_apply(*args, **kwargs)

    @staticmethod
    def _run_retry_held(*args, **kwargs):
        kwargs.setdefault("read_tab", lambda *a, **k: [])
        return propagate.run_retry_held(*args, **kwargs)

    @staticmethod
    def _boom_ensure_tab(*a, **k):
        raise AssertionError("dry-run 인데 ensure_tab 이 호출됐다 — 계약 위반")

    @staticmethod
    def _boom_append_rows(*a, **k):
        raise AssertionError("dry-run 인데 append_rows 가 호출됐다 — 계약 위반")

    @staticmethod
    def _boom_mark_many(*a, **k):
        raise AssertionError("dry-run 인데 mark_many 가 호출됐다 — 계약 위반")

    @staticmethod
    def _boom_approval(*a, **k):
        raise AssertionError("dry-run 인데 approval_log.record 가 호출됐다 — 계약 위반")

    @staticmethod
    def _boom_snapshot_update(*a, **k):
        raise AssertionError("dry-run 인데 snapshot.update 가 호출됐다 — 계약 위반")


# ---------------------------------------------------------------------------
# ① 옵션 지문 불일치 → 보류 기록·apply 0회
# ---------------------------------------------------------------------------

class OptionFingerprintMismatchTest(ApplyBase):
    def test_지문_불일치는_보류로_기록되고_옵션_MCP_호출이_없다(self):
        rep_option = {"차원": [{"원문이름": "颜色", "values": [
            {"vid": 1, "_name": "红色"}, {"vid": 2, "_name": "蓝色"}]}]}
        target_option = {"차원": [{"원문이름": "颜色", "values": [
            {"vid": 1, "_name": "红色"}, {"vid": 2, "_name": "绿色"}]}]}  # 수동수정 가정(_name 다름)
        plan_value = {"plan": {"이름변경": [], "순서상세": [], "제외상세": [], "대표": None},
                     "지문": propagate._option_fingerprint(rep_option)}
        entry = {"코드": "tb:1", "대표pid": "P1", "대표groupId": 11, "작업": "옵션",
                "확정값": plan_value, "메모": None,
                "targets": [_target("P2", 12, "2번_그룹", "", propagate.TARGET_TRANSPLANT)]}
        self._write_plan([entry])
        snap_store = {"P2": {"옵션": target_option}}
        mcp = _FakeMCP({})

        counts = self._run_apply(
            self.run_dir, commit=True, mcp=mcp,
            index_groups=lambda: [("2번_그룹", "SID2")],
            snapshot_load=_fake_snapshot(snap_store),
            snapshot_update=_fake_snapshot_update(snap_store),
            ensure_tab=lambda *a, **k: False, append_rows=lambda *a, **k: 0,
            mark_many=lambda *a, **k: 0, approval_record=lambda *a, **k: True, log=None)

        self.assertEqual(counts.get("보류"), 1)
        self.assertEqual(mcp.calls, [])  # 옵션 MCP 호출 0회
        ledger = _read_ledger(self.run_dir)
        self.assertEqual(len(ledger), 1)
        self.assertEqual(ledger[0]["결과"], "보류")
        self.assertEqual(ledger[0]["사유"], "지문불일치")


# ---------------------------------------------------------------------------
# ② 멱등 — 같은 plan 재실행 시 이미 적용분 스킵
# ---------------------------------------------------------------------------

class IdempotenceTest(ApplyBase):
    def test_이미_적용된_타깃은_두번째_실행에서_ledger로_스킵된다(self):
        entry = {"코드": "tb:2", "대표pid": "P1", "대표groupId": 11, "작업": "썸네일",
                "확정값": {"url": "http://img/1.jpg"}, "메모": None,
                "targets": [_target("P2", 12, "2번_그룹", "", propagate.TARGET_TRANSPLANT)]}
        self._write_plan([entry])
        snap_store = {"P2": {"썸네일": [""]}}
        common = dict(index_groups=lambda: [("2번_그룹", "SID2")],
                      snapshot_load=_fake_snapshot(snap_store),
                      snapshot_update=_fake_snapshot_update(snap_store),
                      ensure_tab=lambda *a, **k: False, append_rows=lambda *a, **k: 0,
                      mark_many=lambda *a, **k: 0, approval_record=lambda *a, **k: True, log=None)

        mcp1 = _FakeMCP({"bulsaja_thumbnail_update": [
            {"confirmationToken": "tok"}, {"success": True}]})
        c1 = self._run_apply(self.run_dir, commit=True, mcp=mcp1, **common)
        self.assertEqual(c1.get("적용"), 1)
        self.assertEqual(len(mcp1.calls), 2)

        mcp2 = _FakeMCP({})
        c2 = self._run_apply(self.run_dir, commit=True, mcp=mcp2, **common)
        self.assertEqual(c2.get("스킵"), 1)
        self.assertEqual(mcp2.calls, [])  # 두번째 실행은 MCP 호출 0

        ledger = _read_ledger(self.run_dir)
        self.assertEqual(len(ledger), 2)
        self.assertEqual(ledger[1]["결과"], "스킵")
        self.assertEqual(ledger[1]["사유"], "이미적용(ledger)")


# ---------------------------------------------------------------------------
# ③ ledger.jsonl 기록 형식
# ---------------------------------------------------------------------------

class LedgerFormatTest(ApplyBase):
    def test_ledger_기록_형식(self):
        entry = {"코드": "tb:9", "대표pid": "P1", "대표groupId": 11, "작업": "썸네일",
                "확정값": {"url": "http://img/x.jpg"}, "메모": None,
                "targets": [_target("P2", 12, "2번_그룹", "", propagate.TARGET_TRANSPLANT)]}
        self._write_plan([entry])
        snap_store = {"P2": {"썸네일": [""]}}
        mcp = _FakeMCP({"bulsaja_thumbnail_update": [{"confirmationToken": "t"}, {"success": True}]})
        self._run_apply(
            self.run_dir, commit=True, mcp=mcp,
            index_groups=lambda: [("2번_그룹", "SID2")],
            snapshot_load=_fake_snapshot(snap_store),
            snapshot_update=_fake_snapshot_update(snap_store),
            ensure_tab=lambda *a, **k: False, append_rows=lambda *a, **k: 0,
            mark_many=lambda *a, **k: 0, approval_record=lambda *a, **k: True, log=None)

        ledger = _read_ledger(self.run_dir)
        self.assertEqual(len(ledger), 1)
        rec = ledger[0]
        for key in ("시각", "작업", "코드", "대표pid", "타깃pid", "결과", "사유"):
            self.assertIn(key, rec)
        self.assertEqual(rec["결과"], "적용")
        self.assertEqual(rec["코드"], "tb:9")
        self.assertEqual(rec["대표pid"], "P1")
        self.assertEqual(rec["타깃pid"], "P2")


# ---------------------------------------------------------------------------
# ④ dry-run(--commit 없음)은 쓰기 0
# ---------------------------------------------------------------------------

class DryRunTest(ApplyBase):
    def test_commit_없으면_쓰기가_0이다(self):
        entry = {"코드": "tb:3", "대표pid": "P1", "대표groupId": 11, "작업": "썸네일",
                "확정값": {"url": "http://img/same.jpg"}, "메모": None,
                "targets": [_target("P2", 12, "2번_그룹", "", propagate.TARGET_TRANSPLANT)]}
        self._write_plan([entry])
        # verify_썸네일 이 URL 동일로 스킵 판정하므로 MCP 조차 필요 없다(가장 단순한 dry-run 픽스처).
        snap_store = {"P2": {"썸네일": ["http://img/same.jpg"]}}
        mcp = _FakeMCP({})
        self._run_apply(
            self.run_dir, commit=False, mcp=mcp,
            index_groups=lambda: [("2번_그룹", "SID2")],
            snapshot_load=_fake_snapshot(snap_store),
            snapshot_update=self._boom_snapshot_update,
            ensure_tab=self._boom_ensure_tab, append_rows=self._boom_append_rows,
            mark_many=self._boom_mark_many, approval_record=self._boom_approval, log=None)

        self.assertFalse(os.path.exists(os.path.join(self.run_dir, "ledger.jsonl")))
        self.assertEqual(mcp.calls, [])


# ---------------------------------------------------------------------------
# ⑤ 카테고리 preview 경로 불일치 → 보류
# ---------------------------------------------------------------------------

class CategoryMismatchTest(ApplyBase):
    def test_카테고리_preview_경로_불일치는_보류로_기록된다(self):
        entry = {"코드": "tb:4", "대표pid": "P1", "대표groupId": 11, "작업": "카테고리",
                "확정값": {"경로": "생활/건강>공구>농기계", "keyword": "농기계"}, "메모": None,
                "targets": [_target("P2", 12, "2번_그룹", "", propagate.TARGET_TRANSPLANT)]}
        self._write_plan([entry])
        snap_store = {"P2": {"기존카테고리": "디지털/가전>주변기기"}}  # 스킵(이미확정경로) 방지용
        mcp = _FakeMCP({"bulsaja_product_category": {
            "confirmationToken": "tok",
            "지정될카테고리": {"ss_category": {"name": "완전히 다른 경로"}}}})

        counts = self._run_apply(
            self.run_dir, commit=True, mcp=mcp,
            index_groups=lambda: [("2번_그룹", "SID2")],
            snapshot_load=_fake_snapshot(snap_store),
            snapshot_update=_fake_snapshot_update(snap_store),
            ensure_tab=lambda *a, **k: False, append_rows=lambda *a, **k: 0,
            mark_many=lambda *a, **k: 0, approval_record=lambda *a, **k: True, log=None)

        self.assertEqual(counts.get("보류"), 1)
        self.assertEqual(len(mcp.calls), 1)  # preview 1회만 — commit 호출은 없다
        ledger = _read_ledger(self.run_dir)
        self.assertEqual(ledger[0]["사유"], "증거불일치")


class CategoryApplySuccessTest(ApplyBase):
    """행복 경로 — 경로 일치 시 실제로 적용되고 현황판·승인로그가 함께 갱신되는지."""

    def test_카테고리_경로_일치시_적용되고_현황판_승인로그가_불린다(self):
        entry = {"코드": "tb:6", "대표pid": "P1", "대표groupId": 11, "작업": "카테고리",
                "확정값": {"경로": "생활/건강>공구>농기계", "keyword": "농기계"}, "메모": None,
                "targets": [_target("P2", 12, "2번_그룹", "", propagate.TARGET_TRANSPLANT)]}
        self._write_plan([entry])
        snap_store = {"P2": {"기존카테고리": "미설정"}}
        mcp = _FakeMCP({"bulsaja_product_category": [
            {"confirmationToken": "tok",
             "지정될카테고리": {"ss_category": {"name": "생활/건강 > 공구 > 농기계"}}},
            {"success": True}]})
        marked, approvals = {}, []

        counts = self._run_apply(
            self.run_dir, commit=True, mcp=mcp,
            index_groups=lambda: [("2번_그룹", "SID2")],
            snapshot_load=_fake_snapshot(snap_store),
            snapshot_update=_fake_snapshot_update(snap_store),
            ensure_tab=lambda *a, **k: False, append_rows=lambda *a, **k: 0,
            mark_many=lambda sid, task, vals: marked.setdefault((sid, task), vals),
            approval_record=lambda sid, pid, **kw: approvals.append((sid, pid, kw)),
            log=None)

        self.assertEqual(counts.get("적용"), 1)
        self.assertEqual(len(mcp.calls), 2)
        self.assertEqual(marked.get(("SID2", "카테고리")), {"P2": matrix.DONE})
        self.assertEqual(len(approvals), 1)
        self.assertEqual(snap_store["P2"]["기존카테고리"], "생활/건강>공구>농기계")


# ---------------------------------------------------------------------------
# 피어리뷰 반영 — 옵션/상품명 happy path + falsy 키 제거 + 부분실패 재시도
# ---------------------------------------------------------------------------

class OptionApplySuccessTest(ApplyBase):
    """행복 경로 + Critical #1 재현 — 제외만 있는 계획(순서상세 없음)에서 페이로드에
    falsy 키(includeSkuIds:[]·mainSkuId:None)가 실제로 빠지는지 직접 확인한다."""

    def test_옵션_적용_시_페이로드에서_falsy_키가_제거된다(self):
        rep_option = {"차원": [{"원문이름": "颜色", "values": [
            {"vid": 1, "_name": "红色"}, {"vid": 2, "_name": "蓝色"}]}]}
        target_option = {"차원": [{"원문이름": "颜色", "values": [
            {"vid": 1, "_name": "红色"}, {"vid": 2, "_name": "蓝色"}]}]}  # 지문 동일
        plan_entry = {
            "이름변경": [{"키": "1", "차원": "颜色", "기존": "红色", "교정": "레드", "변경": True}],
            "순서상세": [],   # keep 없음 — Critical #1 재현 지점(제외만 있는 계획)
            "제외상세": [{"id": "2", "이름": "블루", "사유": "품절"}],
            "대표": None,
        }
        plan_value = {"plan": plan_entry, "지문": propagate._option_fingerprint(rep_option)}
        entry = {"코드": "tb:20", "대표pid": "P1", "대표groupId": 11, "작업": "옵션",
                "확정값": plan_value, "메모": None,
                "targets": [_target("P2", 12, "2번_그룹", "", propagate.TARGET_TRANSPLANT)]}
        self._write_plan([entry])
        snap_store = {"P2": {"옵션": target_option}}
        mcp = _FakeMCP({"bulsaja_option_update": [
            {"confirmationToken": "t1"}, {"success": True},   # 이름변경
            {"confirmationToken": "t2"}, {"success": True},   # 포함/제외
        ]})

        counts = self._run_apply(
            self.run_dir, commit=True, mcp=mcp,
            index_groups=lambda: [("2번_그룹", "SID2")],
            snapshot_load=_fake_snapshot(snap_store),
            snapshot_update=_fake_snapshot_update(snap_store),
            ensure_tab=lambda *a, **k: False, append_rows=lambda *a, **k: 0,
            mark_many=lambda *a, **k: 0, approval_record=lambda *a, **k: True, log=None)

        self.assertEqual(counts.get("적용"), 1)
        option_calls = [a for n, a in mcp.calls if n == "bulsaja_option_update"]
        self.assertEqual(len(option_calls), 4)
        incl_excl_preview = option_calls[2]  # 이름변경(2콜) 다음이 포함/제외 프리뷰
        self.assertNotIn("includeSkuIds", incl_excl_preview)   # [] 는 제거돼야 한다
        self.assertNotIn("mainSkuId", incl_excl_preview)       # None 은 제거돼야 한다
        self.assertIn("excludeSkuIds", incl_excl_preview)
        self.assertEqual(incl_excl_preview["excludeSkuIds"], ["2"])
        # 첫 호출(이름변경 프리뷰)에도 confirm 키를 명시적으로 싣지 않는다(Important #1)
        self.assertNotIn("confirm", option_calls[0])


class OptionPartialFailureRetryTest(ApplyBase):
    """Important #3 — 이름변경 성공·포함/제외 실패 후 재시도가 이름변경을 다시 보내지 않는지."""

    def test_이름변경_성공_포함제외_실패_후_재시도는_이름변경을_다시_보내지_않는다(self):
        rep_option = {"차원": [{"원문이름": "颜色", "values": [
            {"vid": 1, "_name": "红色", "name": "빨강"}]}]}
        target_option = {"차원": [{"원문이름": "颜色", "values": [
            {"vid": 1, "_name": "红色", "name": "빨강"}]}], "vid고유": True}
        plan_entry = {
            "이름변경": [{"키": "1", "차원": "颜色", "기존": "빨강", "교정": "레드", "변경": True}],
            "순서상세": [{"id": "1", "이름": "레드", "판매가": 1000, "대표": True}],
            "제외상세": [], "대표": "1",
        }
        plan_value = {"plan": plan_entry, "지문": propagate._option_fingerprint(rep_option)}
        entry = {"코드": "tb:21", "대표pid": "P1", "대표groupId": 11, "작업": "옵션",
                "확정값": plan_value, "메모": None,
                "targets": [_target("P2", 12, "2번_그룹", "", propagate.TARGET_TRANSPLANT)]}
        self._write_plan([entry])
        snap_store = {"P2": {"옵션": target_option}}
        # 서버는 1차 시도의 이름변경까지만 실제로 반영된 상태를 흉내(재조회 시 "레드").
        renamed_option = {"차원": [{"원문이름": "颜色", "values": [
            {"vid": 1, "_name": "红色", "name": "레드"}]}], "vid고유": True}

        class _McpRenameThenBreak:
            """1차 시도 — 이름변경(preview+confirm)은 성공해 서버 상태가 실제로 바뀌지만,
            바로 이어지는 포함/제외 호출에서 예외가 난다(부분 실패)."""

            def __init__(self):
                self.calls = []
                self.renamed_on_server = False

            def workdata(self, pid, mode="full"):
                return {"옵션": renamed_option if self.renamed_on_server else target_option}

            def call_tool(self, name, args):
                self.calls.append((name, dict(args)))
                if name == "bulsaja_option_update":
                    if "renameValues" in args:
                        if not args.get("confirm"):
                            return {"confirmationToken": "t1"}
                        self.renamed_on_server = True
                        return {"success": True}
                    if "includeSkuIds" in args or "excludeSkuIds" in args:
                        raise RuntimeError("네트워크 끊김(포함/제외)")
                return {}

            def _confirmed_call(self, tool, payload):
                payload = propagate._strip_falsy(payload)
                pv = self.call_tool(tool, payload)
                token = pv.get("confirmationToken")
                if not token:
                    if pv.get("success"):
                        return pv
                    raise RuntimeError(f"확인키 미발급({tool})")
                r = self.call_tool(tool, {**payload, "confirm": True, "confirmationToken": token})
                if not r.get("success"):
                    raise RuntimeError(f"저장 실패({tool})")
                return r

        mcp1 = _McpRenameThenBreak()
        c1 = self._run_apply(
            self.run_dir, commit=True, mcp=mcp1,
            index_groups=lambda: [("2번_그룹", "SID2")],
            snapshot_load=_fake_snapshot(snap_store),
            snapshot_update=_fake_snapshot_update(snap_store),
            ensure_tab=lambda *a, **k: False, append_rows=lambda *a, **k: 0,
            mark_many=lambda *a, **k: 0, approval_record=lambda *a, **k: True, log=None)
        self.assertEqual(c1.get("보류"), 1)
        self.assertTrue(mcp1.renamed_on_server)   # 서버 쪽은 실제로 이름이 바뀐 채 남았다
        # 스냅샷은 실패 시 갱신되지 않으므로 여전히 옛 옵션(이름 "빨강") — verify 는 지문
        # (원문이름·vid·_name) 만 보므로 재시도에서도 통과한다(이름 필드는 지문 대상이 아님).
        self.assertEqual(snap_store["P2"]["옵션"], target_option)

        # 2차 시도(재시도) — 서버는 여전히 renamed_option(이미 "레드"). 이번엔 포함/제외가
        # 성공한다. 이름변경 호출이 다시 나가면 안 된다(이미 반영돼 있으므로).
        mcp2 = _FakeMCP({"bulsaja_option_update": [{"confirmationToken": "t2"}, {"success": True}]})
        mcp2.workdata = lambda pid, mode="full": {"옵션": renamed_option}
        c2 = self._run_apply(
            self.run_dir, commit=True, mcp=mcp2,
            index_groups=lambda: [("2번_그룹", "SID2")],
            snapshot_load=_fake_snapshot(snap_store),
            snapshot_update=_fake_snapshot_update(snap_store),
            ensure_tab=lambda *a, **k: False, append_rows=lambda *a, **k: 0,
            mark_many=lambda *a, **k: 0, approval_record=lambda *a, **k: True, log=None)
        self.assertEqual(c2.get("적용"), 1)
        option_calls = [a for n, a in mcp2.calls if n == "bulsaja_option_update"]
        self.assertTrue(all("renameValues" not in a for a in option_calls),
                        "이미 서버에 반영된 이름변경을 재시도가 또 보냈다")
        self.assertEqual(len(option_calls), 2)  # 포함/제외(순서상세=["1"])만 2콜(preview+confirm)


class _FakeNameHeaderModule:
    NAME_HEADER = ["상품id", "작업일", "마켓그룹", "원본상품명", "새상품명",
                  "키워드1", "키워드2", "키워드3", "키워드4", "키워드5",
                  "상태", "메모"]


class NameApplySuccessTest(ApplyBase):
    def test_상품명_적용_시_시트_append와_rename_runner가_호출된다(self):
        entry = {"코드": "tb:22", "대표pid": "P1", "대표groupId": 11, "작업": "상품명",
                "확정값": {"새상품명": "확정이름 키워드1", "키워드": ["키워드1"]}, "메모": None,
                "targets": [_target("P2", 12, "2번_그룹", "", propagate.TARGET_TRANSPLANT)]}
        self._write_plan([entry])
        snap_store = {"P2": {"상품명": "옛이름"}}
        appended, rename_calls = [], []

        counts = self._run_apply(
            self.run_dir, commit=True, mcp=_FakeMCP({}),
            index_groups=lambda: [("2번_그룹", "SID2")],
            read_tab=lambda sid, tab: [],  # 상품명 탭이 비어있다(최초 실행) — 네트워크 0
            snapshot_load=_fake_snapshot(snap_store),
            snapshot_update=_fake_snapshot_update(snap_store),
            ensure_tab=lambda *a, **k: False,
            append_rows=lambda sid, tab, rows: appended.extend(rows) or len(rows),
            mark_many=lambda *a, **k: 0, approval_record=lambda *a, **k: True,
            rename_runner=lambda **kw: rename_calls.append(kw),
            name_header_module=_FakeNameHeaderModule(), log=None)

        self.assertEqual(counts.get("적용"), 1)
        self.assertEqual(len(appended), 1)
        row = dict(zip(_FakeNameHeaderModule.NAME_HEADER, appended[0]))
        self.assertEqual(row["상품id"], "P2")
        self.assertEqual(row["원본상품명"], "옛이름")
        self.assertEqual(row["상태"], "생성완료")
        self.assertEqual(row["메모"], "전파(tb:22,P1)")
        self.assertEqual(len(rename_calls), 1)
        self.assertEqual(rename_calls[0]["ids"], ["P2"])
        self.assertEqual(rename_calls[0]["sheet"], "SID2")
        self.assertEqual(rename_calls[0]["tab"], "상품명")


class NamePartialFailureRetryTest(ApplyBase):
    """Important #3 — 시트 append 후 rename_runner(subprocess) 실패 시, 재시도가
    같은 (상품id, 메모) 행을 중복으로 append 하지 않는지."""

    def test_append_후_rename_실패시_재시도는_행을_중복_추가하지_않는다(self):
        entry = {"코드": "tb:23", "대표pid": "P1", "대표groupId": 11, "작업": "상품명",
                "확정값": {"새상품명": "확정이름 키워드1", "키워드": ["키워드1"]}, "메모": None,
                "targets": [_target("P2", 12, "2번_그룹", "", propagate.TARGET_TRANSPLANT)]}
        self._write_plan([entry])
        snap_store = {"P2": {"상품명": "옛이름"}}
        appended_rows = []

        def _boom_rename(**kw):
            raise RuntimeError("subprocess 실패")

        def _append(sid, tab, rows):
            # 이 시나리오는 rename_runner 실패로 실패 판정(보류)이 나서 00_보류함 시트에도
            # append 가 걸린다 — "상품명" 탭 행만 골라 센다(둘을 안 가르면 개수가 헷갈린다).
            if tab == "상품명":
                appended_rows.extend(rows)
            return len(rows)

        c1 = self._run_apply(
            self.run_dir, commit=True, mcp=_FakeMCP({}),
            index_groups=lambda: [("2번_그룹", "SID2")],
            read_tab=lambda sid, tab: [],  # 1차 시도 — 아직 빈 탭
            snapshot_load=_fake_snapshot(snap_store),
            snapshot_update=_fake_snapshot_update(snap_store),
            ensure_tab=lambda *a, **k: False,
            append_rows=_append,
            mark_many=lambda *a, **k: 0, approval_record=lambda *a, **k: True,
            rename_runner=_boom_rename, name_header_module=_FakeNameHeaderModule(), log=None)
        self.assertEqual(c1.get("보류"), 1)
        self.assertEqual(len(appended_rows), 1)  # 1차 시도에서 append 는 이미 됐다(상품명 탭만)

        # 2차 시도(재시도) — read_tab 이 1차에서 이미 append 된 행을 돌려주게 페이크.
        # ensure_tab/append_rows 는 다시 호출되면 즉시 실패하는 붐 함수로 방어해
        # "중복 추가가 실제로 일어나지 않는다"를 구조적으로 검증한다.
        existing_rows = [_FakeNameHeaderModule.NAME_HEADER,
                         ["P2", "2026-08-01", "2번_그룹", "옛이름", "확정이름", "", "", "", "", "",
                          "생성완료", "전파(tb:23,P1)"]]
        rename_calls = []
        c2 = self._run_apply(
            self.run_dir, commit=True, mcp=_FakeMCP({}),
            index_groups=lambda: [("2번_그룹", "SID2")],
            read_tab=lambda sid, tab: existing_rows,
            snapshot_load=_fake_snapshot(snap_store),
            snapshot_update=_fake_snapshot_update(snap_store),
            ensure_tab=self._boom_ensure_tab, append_rows=self._boom_append_rows,
            mark_many=lambda *a, **k: 0, approval_record=lambda *a, **k: True,
            rename_runner=lambda **kw: rename_calls.append(kw),
            name_header_module=_FakeNameHeaderModule(), log=None)
        self.assertEqual(c2.get("적용"), 1)
        self.assertEqual(len(rename_calls), 1)


# ---------------------------------------------------------------------------
# ⑥ 썸네일 동일 URL → 스킵
# ---------------------------------------------------------------------------

class ThumbnailSameUrlTest(ApplyBase):
    def test_썸네일_URL_동일하면_스킵되고_MCP_호출이_없다(self):
        entry = {"코드": "tb:5", "대표pid": "P1", "대표groupId": 11, "작업": "썸네일",
                "확정값": {"url": "http://img/same.jpg"}, "메모": None,
                "targets": [_target("P2", 12, "2번_그룹", "", propagate.TARGET_TRANSPLANT)]}
        self._write_plan([entry])
        snap_store = {"P2": {"썸네일": ["http://img/same.jpg"]}}
        mcp = _FakeMCP({})

        counts = self._run_apply(
            self.run_dir, commit=True, mcp=mcp,
            index_groups=lambda: [("2번_그룹", "SID2")],
            snapshot_load=_fake_snapshot(snap_store),
            snapshot_update=_fake_snapshot_update(snap_store),
            ensure_tab=lambda *a, **k: False, append_rows=lambda *a, **k: 0,
            mark_many=lambda *a, **k: 0, approval_record=lambda *a, **k: True, log=None)

        self.assertEqual(counts.get("스킵"), 1)
        self.assertEqual(mcp.calls, [])
        ledger = _read_ledger(self.run_dir)
        self.assertEqual(ledger[0]["사유"], "이미동일URL")


# ---------------------------------------------------------------------------
# ⑦ 상품명 shuffle이 rep_group_id 항등 유지
# ---------------------------------------------------------------------------

class PropagatedNameInvarianceTest(unittest.TestCase):
    def test_대표와_같은_그룹이면_이름이_항등이다(self):
        확정값 = {"새상품명": "이발의자 전동미용의자 업소용", "키워드": ["이발의자", "전동미용의자"]}
        새이름, kws = propagate.propagated_name(확정값, "tb:1", 11, 11)
        self.assertEqual(새이름, 확정값["새상품명"])
        self.assertEqual(kws, 확정값["키워드"])

    def test_다른_그룹이면_shuffle_name에_위임한다(self):
        확정값 = {"새상품명": "이발의자 전동미용의자 업소용", "키워드": ["이발의자", "전동미용의자"]}
        새이름, _ = propagate.propagated_name(확정값, "tb:1", 12, 11)
        expected = dedup.shuffle_name(확정값["새상품명"], 확정값["키워드"], "tb:1", 12, rep_group_id=11)
        self.assertEqual(새이름, expected)


# ---------------------------------------------------------------------------
# 추가 — load_plan_카테고리/옵션/썸네일 (Task5 가 채운 자리) 단위 테스트
# ---------------------------------------------------------------------------

CATFIX_HEADER = ["상품id", "상품명", "이전카테고리", "변경카테고리", "검색어(사용)",
                 "확신도", "상태", "기록일", "위험", "실물판정", "썸네일URL"]

THUMB_HEADER = ["상품id", "작업일", "상품명", "모드", "기존대표", "생성본",
               "판정", "사유", "크레딧", "상태"]


class LoadPlanCategoryTest(unittest.TestCase):
    def test_확정경로와_keyword를_읽는다(self):
        rows = [CATFIX_HEADER, ["P1", "", "", "", "농기계", "90", "자동저장완료", "", "", "", ""]]
        snap_store = {"P1": {"기존카테고리": "생활/건강>공구>농기계"}}
        value, memo = propagate.load_plan_카테고리(
            "P1", "1번_그룹",
            {"load_snapshot": _fake_snapshot(snap_store),
             "index_groups": lambda: [("1번_그룹", "SID1")],
             "read_tab": lambda sid, tab: rows if tab == propagate.CATFIX_TAB else []})
        self.assertIsNone(memo)
        self.assertEqual(value["경로"], "생활/건강>공구>농기계")
        self.assertEqual(value["keyword"], "농기계")

    def test_확정경로가_없으면_보류_사유를_남긴다(self):
        value, memo = propagate.load_plan_카테고리(
            "P9", "1번_그룹", {"load_snapshot": _fake_snapshot({})})
        self.assertIsNone(value)
        self.assertEqual(memo, "확정경로없음")

    def test_저장완료류_행이_없으면_확정행없음(self):
        rows = [CATFIX_HEADER, ["P1", "", "", "", "농기계", "50", "승인보류", "", "", "", ""]]
        snap_store = {"P1": {"기존카테고리": "생활/건강>공구>농기계"}}
        value, memo = propagate.load_plan_카테고리(
            "P1", "1번_그룹",
            {"load_snapshot": _fake_snapshot(snap_store),
             "index_groups": lambda: [("1번_그룹", "SID1")],
             "read_tab": lambda sid, tab: rows})
        self.assertIsNone(value)
        self.assertEqual(memo, "확정행없음")


class LoadPlanThumbnailTest(unittest.TestCase):
    def test_생성본_URL을_읽는다(self):
        rows = [THUMB_HEADER, ["P1", "", "", "", "", "http://img/a.jpg", "", "", "", ""]]
        value, memo = propagate.load_plan_썸네일(
            "P1", "1번_그룹",
            {"index_groups": lambda: [("1번_그룹", "SID1")],
             "read_tab": lambda sid, tab: rows if tab == propagate.THUMB_TAB else []})
        self.assertIsNone(memo)
        self.assertEqual(value["url"], "http://img/a.jpg")

    def test_생성본_URL이_없으면_보류_사유를_남긴다(self):
        rows = [THUMB_HEADER, ["P1", "", "", "", "", "", "", "", "", ""]]
        value, memo = propagate.load_plan_썸네일(
            "P1", "1번_그룹",
            {"index_groups": lambda: [("1번_그룹", "SID1")],
             "read_tab": lambda sid, tab: rows})
        self.assertIsNone(value)
        self.assertEqual(memo, "생성본URL없음")


class LoadPlanOptionTest(unittest.TestCase):
    def test_주입이_없으면_규약미정으로_보류한다(self):
        value, memo = propagate.load_plan_옵션("P1", "1번_그룹", {})
        self.assertIsNone(value)
        self.assertEqual(memo, "옵션런디렉토리규약미정")

    def test_주입되면_지문과_계획을_함께_반환한다(self):
        rep_option = {"차원": [{"원문이름": "颜色", "values": [{"vid": 1, "_name": "红色"}]}]}
        value, memo = propagate.load_plan_옵션(
            "P1", "1번_그룹",
            {"find_option_plan": lambda pid: ({"이름변경": []}, None),
             "load_snapshot": _fake_snapshot({"P1": {"옵션": rep_option}})})
        self.assertIsNone(memo)
        self.assertEqual(value["지문"], propagate._option_fingerprint(rep_option))


class OptionFingerprintTest(unittest.TestCase):
    def test_차원_순서와_vid_name이_같으면_지문이_같다(self):
        a = {"차원": [{"원문이름": "颜色", "values": [{"vid": 1, "_name": "红"}, {"vid": 2, "_name": "蓝"}]}]}
        b = {"차원": [{"원문이름": "颜色", "values": [{"vid": 1, "_name": "红"}, {"vid": 2, "_name": "蓝"}]}]}
        self.assertEqual(propagate._option_fingerprint(a), propagate._option_fingerprint(b))

    def test_name이_하나라도_다르면_지문이_다르다(self):
        a = {"차원": [{"원문이름": "颜色", "values": [{"vid": 1, "_name": "红"}]}]}
        b = {"차원": [{"원문이름": "颜色", "values": [{"vid": 1, "_name": "绿"}]}]}
        self.assertNotEqual(propagate._option_fingerprint(a), propagate._option_fingerprint(b))


# ---------------------------------------------------------------------------
# status / retry-held — 가벼운 구조 검증
# ---------------------------------------------------------------------------

class StatusTest(ApplyBase):
    def test_status는_plan과_ledger를_집계한다(self):
        entry = {"코드": "tb:7", "대표pid": "P1", "대표groupId": 11, "작업": "썸네일",
                "확정값": {"url": "http://img/s.jpg"}, "메모": None,
                "targets": [_target("P2", 12, "2번_그룹", "", propagate.TARGET_TRANSPLANT)]}
        self._write_plan([entry])
        snap_store = {"P2": {"썸네일": ["http://img/s.jpg"]}}  # 스킵 유도(동일 URL)
        self._run_apply(
            self.run_dir, commit=True, mcp=_FakeMCP({}),
            index_groups=lambda: [("2번_그룹", "SID2")],
            snapshot_load=_fake_snapshot(snap_store),
            snapshot_update=_fake_snapshot_update(snap_store),
            ensure_tab=lambda *a, **k: False, append_rows=lambda *a, **k: 0,
            mark_many=lambda *a, **k: 0, approval_record=lambda *a, **k: True, log=None)

        out = propagate.run_status(self.run_dir, log=None)
        self.assertEqual(out["타깃건수"], 1)
        self.assertEqual(out["ledger건수"], 1)
        self.assertEqual(out["결과별"].get("스킵"), 1)


class RetryHeldTest(ApplyBase):
    def test_승인_열이_승인인_행만_미니plan에_들어간다(self):
        entry = {"코드": "tb:8", "대표pid": "P1", "대표groupId": 11, "작업": "썸네일",
                "확정값": {"url": "http://img/r.jpg"}, "메모": None,
                "targets": [
                    _target("P2", 12, "2번_그룹", "승인보류", propagate.TARGET_HELD),
                    _target("P3", 13, "3번_그룹", "승인보류", propagate.TARGET_HELD),
                ]}
        self._write_plan([entry])
        held_rows = [
            {"코드": "tb:8", "타깃pid": "P2", "작업": "썸네일", "승인": "승인"},
            {"코드": "tb:8", "타깃pid": "P3", "작업": "썸네일", "승인": ""},
        ]
        snap_store = {"P2": {"썸네일": [""]}}
        counts = self._run_retry_held(
            self.run_dir, master_sheet="MASTER",
            read_held_rows=lambda sheet: held_rows,
            commit=True, log=None,
            mcp=_FakeMCP({"bulsaja_thumbnail_update": [{"confirmationToken": "t"}, {"success": True}]}),
            index_groups=lambda: [("2번_그룹", "SID2"), ("3번_그룹", "SID3")],
            snapshot_load=_fake_snapshot(snap_store),
            snapshot_update=_fake_snapshot_update(snap_store),
            ensure_tab=lambda *a, **k: False, append_rows=lambda *a, **k: 0,
            mark_many=lambda *a, **k: 0, approval_record=lambda *a, **k: True)
        self.assertEqual(counts.get("적용"), 1)  # P2만 승인 → 재적용, P3는 빠진다

    def test_승인된_행이_없으면_아무일도_하지_않는다(self):
        out = self._run_retry_held(
            self.run_dir, master_sheet="MASTER",
            read_held_rows=lambda sheet: [{"코드": "tb:8", "타깃pid": "P2",
                                          "작업": "썸네일", "승인": ""}],
            log=None)
        self.assertEqual(out, {})


# =============================================================================
# 최종 브랜치 리뷰(Fable) 반영 — Critical #1 + Important #2·#3·#4·#5·#6 + Minors
# =============================================================================

# ---------------------------------------------------------------------------
# Critical #1 — mcp 미지정시 run_apply 가 PropagateMCP 를 생성·open·close 하는지
# ---------------------------------------------------------------------------

class _McpForWiringTest:
    """`propagate.PropagateMCP` 를 통째로 갈아끼우는 클래스 몽키패치 타깃 — 실제 transport
    (open()의 HTTP initialize)는 절대 타지 않고, open()/close() 호출 여부만 기록한다."""

    instances = []

    def __init__(self):
        self.opened = False
        self.closed = False
        _McpForWiringTest.instances.append(self)

    def open(self):
        self.opened = True

    def close(self):
        self.closed = True

    def call_tool(self, name, args):
        return {}

    def _confirmed_call(self, tool, payload):
        return {"success": True}

    def workdata(self, pid, mode="full"):
        return {"옵션": {}}


class MCPWiringTest(ApplyBase):
    def test_mcp_미지정시_PropagateMCP를_생성하고_open_close_한다(self):
        entry = {"코드": "tb:40", "대표pid": "P1", "대표groupId": 11, "작업": "썸네일",
                "확정값": {"url": "http://img/w.jpg"}, "메모": None,
                "targets": [_target("P2", 12, "2번_그룹", "", propagate.TARGET_TRANSPLANT)]}
        self._write_plan([entry])
        snap_store = {"P2": {"썸네일": [""]}}
        _McpForWiringTest.instances = []
        orig_cls = propagate.PropagateMCP
        propagate.PropagateMCP = _McpForWiringTest
        try:
            counts = self._run_apply(
                self.run_dir, commit=True,  # mcp= 를 아예 안 준다 — 이게 핵심
                index_groups=lambda: [("2번_그룹", "SID2")],
                snapshot_load=_fake_snapshot(snap_store),
                snapshot_update=_fake_snapshot_update(snap_store),
                ensure_tab=lambda *a, **k: False, append_rows=lambda *a, **k: 0,
                mark_many=lambda *a, **k: 0, approval_record=lambda *a, **k: True, log=None)
        finally:
            propagate.PropagateMCP = orig_cls
        self.assertEqual(len(_McpForWiringTest.instances), 1)
        inst = _McpForWiringTest.instances[0]
        self.assertTrue(inst.opened)
        self.assertTrue(inst.closed)
        self.assertEqual(counts.get("적용"), 1)

    def test_예외가_나도_close는_호출된다(self):
        """apply 도중 예외가 나도(타깃은 보류로 떨어질 뿐이지만) mcp.close() 는 finally 로
        보장돼야 한다 — 세션이 열린 채 남으면 다음 실행이 토큰을 새로 못 받는다."""
        entry = {"코드": "tb:41", "대표pid": "P1", "대표groupId": 11, "작업": "카테고리",
                "확정값": {"경로": "A>B", "keyword": "kw"}, "메모": None,
                "targets": [_target("P2", 12, "2번_그룹", "", propagate.TARGET_TRANSPLANT)]}
        self._write_plan([entry])

        class _McpBoom(_McpForWiringTest):
            def call_tool(self, name, args):
                raise RuntimeError("네트워크 끊김")

        _McpForWiringTest.instances = []
        orig_cls = propagate.PropagateMCP
        propagate.PropagateMCP = _McpBoom
        try:
            counts = self._run_apply(
                self.run_dir, commit=True,
                index_groups=lambda: [("2번_그룹", "SID2")],
                snapshot_load=lambda pid: {"기존카테고리": "미설정"},
                snapshot_update=lambda pid, **f: None,
                ensure_tab=lambda *a, **k: False, append_rows=lambda *a, **k: 0,
                mark_many=lambda *a, **k: 0, approval_record=lambda *a, **k: True, log=None)
        finally:
            propagate.PropagateMCP = orig_cls
        self.assertEqual(counts.get("보류"), 1)  # verify 예외 → 보류(Important #6)
        self.assertTrue(_McpForWiringTest.instances[0].closed)


class PropagateMCPConfirmedCallTest(unittest.TestCase):
    """페이크(`_FakeMCP`)가 아니라 진짜 `PropagateMCP._confirmed_call` 을 직접 검증한다 —
    페이크는 로직을 손으로 복제한 것이라 프로덕션 코드가 바뀌어도 드리프트를 못 잡는다
    (피어리뷰 Minor). transport(`__init__`/`open`)는 타지 않고 `call_tool` 만 스텁한다."""

    def test_falsy_키_제거와_confirm_흐름을_실물_클래스로_확인한다(self):
        mcp = propagate.PropagateMCP.__new__(propagate.PropagateMCP)
        calls = []

        def _call_tool(name, args):
            calls.append((name, dict(args)))
            if "confirm" not in args:
                return {"confirmationToken": "tok"}
            return {"success": True}
        mcp.call_tool = _call_tool

        r = mcp._confirmed_call("bulsaja_option_update",
                                {"productId": "P1", "includeSkuIds": [], "mainSkuId": None,
                                 "excludeSkuIds": ["2"]})
        self.assertTrue(r["success"])
        self.assertEqual(len(calls), 2)
        self.assertNotIn("confirm", calls[0][1])         # 첫 호출엔 confirm 이 없다(Important #1)
        self.assertNotIn("includeSkuIds", calls[0][1])   # falsy 제거(Critical #1)
        self.assertNotIn("mainSkuId", calls[0][1])
        self.assertEqual(calls[0][1]["excludeSkuIds"], ["2"])
        self.assertEqual(calls[1][1]["confirm"], True)
        self.assertEqual(calls[1][1]["confirmationToken"], "tok")

    def test_토큰도_success도_없으면_예외를_올린다(self):
        mcp = propagate.PropagateMCP.__new__(propagate.PropagateMCP)
        mcp.call_tool = lambda name, args: {"message": "거부됨"}
        with self.assertRaises(RuntimeError):
            mcp._confirmed_call("bulsaja_product_category", {"productId": "P1"})


# ---------------------------------------------------------------------------
# Important #2 — rename rc=0 인데 반영 0건이면 예외(보류)로 취급
# ---------------------------------------------------------------------------

class _FakeCompletedProcess:
    def __init__(self, stdout, returncode=0):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = ""


class RenameRunnerParsesCountsTest(unittest.TestCase):
    def test_반영_0건이면_rc0이어도_예외를_던진다(self):
        orig_run = propagate.subprocess.run
        propagate.subprocess.run = lambda *a, **k: _FakeCompletedProcess(
            "###RENAME### 반영 0건 / 불량 1건 / 오류 0건\n")
        try:
            with self.assertRaises(RuntimeError) as ctx:
                propagate._default_rename_runner("SID2", "상품명", ["P2"], "/tmp/run")
            self.assertIn("반영 0건", str(ctx.exception))
        finally:
            propagate.subprocess.run = orig_run

    def test_반영_1건_이상이면_그대로_반환한다(self):
        orig_run = propagate.subprocess.run
        propagate.subprocess.run = lambda *a, **k: _FakeCompletedProcess(
            "###RENAME### 반영 1건 / 불량 0건 / 오류 0건\n")
        try:
            out = propagate._default_rename_runner("SID2", "상품명", ["P2"], "/tmp/run")
            self.assertIn("반영 1건", out)
        finally:
            propagate.subprocess.run = orig_run

    def test_파싱_실패시_None_3개를_반환한다(self):
        self.assertEqual(propagate._parse_rename_counts("아무 상관 없는 출력"),
                        (None, None, None))


class NameApplyRenameZeroAppliedTest(ApplyBase):
    """실제 `_default_rename_runner` 를 태워(subprocess.run 만 스텁), rc=0 인데 반영
    0건이면 그 타깃이 `보류`로 기록되는지 end-to-end 로 확인한다."""

    def test_rename이_반영_0건이면_해당_타깃은_보류로_기록된다(self):
        entry = {"코드": "tb:42", "대표pid": "P1", "대표groupId": 11, "작업": "상품명",
                "확정값": {"새상품명": "확정이름 키워드1", "키워드": ["키워드1"]}, "메모": None,
                "targets": [_target("P2", 12, "2번_그룹", "", propagate.TARGET_TRANSPLANT)]}
        self._write_plan([entry])
        snap_store = {"P2": {"상품명": "옛이름"}}

        orig_run = propagate.subprocess.run
        propagate.subprocess.run = lambda *a, **k: _FakeCompletedProcess(
            "###RENAME### 반영 0건 / 불량 1건 / 오류 0건\n")
        try:
            counts = self._run_apply(
                self.run_dir, commit=True, mcp=_FakeMCP({}),
                index_groups=lambda: [("2번_그룹", "SID2")],
                snapshot_load=_fake_snapshot(snap_store),
                snapshot_update=_fake_snapshot_update(snap_store),
                ensure_tab=lambda *a, **k: False, append_rows=lambda *a, **k: 0,
                mark_many=lambda *a, **k: 0, approval_record=lambda *a, **k: True,
                name_header_module=_FakeNameHeaderModule(), log=None)
        finally:
            propagate.subprocess.run = orig_run
        self.assertEqual(counts.get("보류"), 1)


# ---------------------------------------------------------------------------
# Important #3 — 썸네일 갤러리 보존(대표 1장으로 자르지 않는다)
# ---------------------------------------------------------------------------

class ThumbnailGalleryPreservedTest(ApplyBase):
    def test_기존_갤러리가_유지된채_대표만_앞으로_온다(self):
        entry = {"코드": "tb:43", "대표pid": "P1", "대표groupId": 11, "작업": "썸네일",
                "확정값": {"url": "http://img/new.jpg"}, "메모": None,
                "targets": [_target("P2", 12, "2번_그룹", "", propagate.TARGET_TRANSPLANT)]}
        self._write_plan([entry])
        snap_store = {"P2": {"썸네일": ["http://img/old1.jpg", "http://img/old2.jpg"]}}
        mcp = _FakeMCP({"bulsaja_thumbnail_update": [{"confirmationToken": "t"}, {"success": True}]})
        self._run_apply(
            self.run_dir, commit=True, mcp=mcp,
            index_groups=lambda: [("2번_그룹", "SID2")],
            snapshot_load=_fake_snapshot(snap_store),
            snapshot_update=_fake_snapshot_update(snap_store),
            ensure_tab=lambda *a, **k: False, append_rows=lambda *a, **k: 0,
            mark_many=lambda *a, **k: 0, approval_record=lambda *a, **k: True, log=None)
        sent = [a for n, a in mcp.calls if n == "bulsaja_thumbnail_update"][0]
        self.assertEqual(sent["thumbnails"],
                        ["http://img/new.jpg", "http://img/old1.jpg", "http://img/old2.jpg"])
        self.assertEqual(snap_store["P2"]["썸네일"],
                        ["http://img/new.jpg", "http://img/old1.jpg", "http://img/old2.jpg"])


# ---------------------------------------------------------------------------
# Important #4 — plan 단계 index_groups/read_tab 캐시
# ---------------------------------------------------------------------------

class MemoizeHelpersTest(unittest.TestCase):
    def test_memoize0은_한번만_평가한다(self):
        calls = []

        def fn():
            calls.append(1)
            return [("g", "sid")]
        wrapped = propagate._memoize0(fn)
        self.assertEqual(wrapped(), [("g", "sid")])
        self.assertEqual(wrapped(), [("g", "sid")])
        self.assertEqual(len(calls), 1)

    def test_memoize_read_tab은_같은_키를_한번만_조회한다(self):
        calls = []

        def fn(sid, tab):
            calls.append((sid, tab))
            return [["h"]]
        wrapped = propagate._memoize_read_tab(fn)
        wrapped("S1", "탭A")
        wrapped("S1", "탭A")
        wrapped("S1", "탭B")
        self.assertEqual(len(calls), 2)  # (S1,탭A) 1회 + (S1,탭B) 1회


class PlanCachingTest(PlanBase):
    def test_run_plan은_index_groups를_전체에서_1회만_부른다(self):
        self._write_inventory(_base_codes(), _BASE_REPS, _BASE_DUPS)
        calls = {"index_groups": 0}

        def _ig():
            calls["index_groups"] += 1
            return [("1번_그룹", "SID1"), ("3번_그룹", "SID3"), ("4번_그룹", "SID4")]

        propagate.run_plan(read_matrix=_fake_read_matrix, index_groups=_ig,
                           read_tab=_fake_read_tab, run_dir=self.run_dir, log=None)
        # tb:1(대표 P1, 그룹 1번)·tb:5(대표 P8, 그룹 3번) 각각 대표완료 작업이 여럿이라
        # load_plan_* 이 여러 번 불리지만, index_groups() 캐시가 없던 예전 버전이면
        # 호출마다 다시 불렸을 것 — 캐시가 있으면 전체에서 1회다.
        self.assertEqual(calls["index_groups"], 1)


# ---------------------------------------------------------------------------
# Important #5a — 재실행마다 00_보류함/승인로그 중복 append 방지
# ---------------------------------------------------------------------------

class HeldDedupeTest(ApplyBase):
    def test_기존_00_보류함_행과_같은_사유는_다시_append_되지_않는다(self):
        entry = {"코드": "tb:44", "대표pid": "P1", "대표groupId": 11, "작업": "카테고리",
                "확정값": None, "메모": "확정경로없음",
                "targets": [_target("P2", 12, "2번_그룹", "", propagate.TARGET_TRANSPLANT)]}
        self._write_plan([entry])
        existing_held_rows = [propagate.HELD_HEADER,
                              ["tb:44", "P2", "2번_그룹", "카테고리", "", "확정경로없음",
                               "2026-08-01", ""]]
        appended = []
        approvals = []

        counts = self._run_apply(
            self.run_dir, commit=True, mcp=_FakeMCP({}),
            index_groups=lambda: [("2번_그룹", "SID2")],
            read_tab=lambda sid, tab: existing_held_rows if tab == propagate.HELD_TAB else [],
            ensure_tab=lambda *a, **k: False,
            append_rows=lambda sid, tab, rows: appended.append((tab, rows)) or len(rows),
            mark_many=lambda *a, **k: 0,
            approval_record=lambda sid, pid, **kw: approvals.append((sid, pid, kw)), log=None)

        self.assertEqual(counts.get("보류"), 1)
        self.assertEqual(appended, [])       # 이미 있는 (코드,pid,작업,사유) — append 안 함
        self.assertEqual(approvals, [])      # 승인로그도 같은 이유로 중복 기록 안 함
        # ledger 는 그래도 매번 기록된다(감사 추적 유지) — Important #6 참조
        ledger = _read_ledger(self.run_dir)
        self.assertEqual(len(ledger), 1)
        self.assertEqual(ledger[0]["결과"], "보류")

    def test_기존_행이_없으면_평소대로_append된다(self):
        entry = {"코드": "tb:45", "대표pid": "P1", "대표groupId": 11, "작업": "카테고리",
                "확정값": None, "메모": "확정경로없음",
                "targets": [_target("P2", 12, "2번_그룹", "", propagate.TARGET_TRANSPLANT)]}
        self._write_plan([entry])
        appended = []
        counts = self._run_apply(
            self.run_dir, commit=True, mcp=_FakeMCP({}),
            index_groups=lambda: [("2번_그룹", "SID2")],
            read_tab=lambda sid, tab: [],  # 00_보류함 탭이 비어있다(최초 실행)
            ensure_tab=lambda *a, **k: False,
            append_rows=lambda sid, tab, rows: appended.append((tab, rows)) or len(rows),
            mark_many=lambda *a, **k: 0, approval_record=lambda *a, **k: True, log=None)
        self.assertEqual(counts.get("보류"), 1)
        held_appends = [r for tab, r in appended if tab == propagate.HELD_TAB]
        self.assertEqual(len(held_appends), 1)
        self.assertEqual(len(held_appends[0]), 1)


class OptionCollapsedEntryApplyTest(ApplyBase):
    """Important #5b 의 apply 측 확인 — targets=[] 인 옵션 요약 엔트리는 commit=True 여도
    아무 것도 쓰지 않는다(탈출불가 루프의 진짜 탈출 지점)."""

    def test_targets가_빈_옵션_요약_엔트리는_apply에서_아무것도_쓰지_않는다(self):
        entry = {"코드": "tb:46", "대표pid": "P1", "대표groupId": 11, "작업": "옵션",
                "확정값": None, "메모": "옵션런디렉토리규약미정 — 타깃 3건 요약 생략",
                "targets": []}
        self._write_plan([entry])
        counts = self._run_apply(
            self.run_dir, commit=True, mcp=_FakeMCP({}),
            index_groups=lambda: [],
            ensure_tab=self._boom_ensure_tab, append_rows=self._boom_append_rows,
            mark_many=self._boom_mark_many, approval_record=self._boom_approval, log=None)
        self.assertEqual(counts, {})
        self.assertFalse(os.path.exists(os.path.join(self.run_dir, "ledger.jsonl")))


# ---------------------------------------------------------------------------
# Important #6 — verify 예외 방어 + 타깃 1건 처리 직후 ledger 즉시 기록
# ---------------------------------------------------------------------------

class VerifyExceptionMidRunTest(ApplyBase):
    """앞 타깃(카테고리)이 정상 적용된 뒤, 다음 타깃(또 다른 카테고리)의 verify 가
    예외를 던져도 — ① 전체 run 이 죽지 않고 ② 앞서 적용된 건의 ledger 기록이
    이미 디스크에 남아 있어야 한다(피어리뷰 Important #6)."""

    def test_뒤_타깃_verify_예외가_앞_타깃_ledger_기록을_지우지_않는다(self):
        entry1 = {"코드": "tb:47", "대표pid": "P1", "대표groupId": 11, "작업": "카테고리",
                 "확정값": {"경로": "A>B", "keyword": "kw1"}, "메모": None,
                 "targets": [_target("P2", 12, "2번_그룹", "", propagate.TARGET_TRANSPLANT)]}
        entry2 = {"코드": "tb:48", "대표pid": "P1", "대표groupId": 11, "작업": "카테고리",
                 "확정값": {"경로": "A>B", "keyword": "kw2"}, "메모": None,
                 "targets": [_target("P3", 13, "3번_그룹", "", propagate.TARGET_TRANSPLANT)]}
        self._write_plan([entry1, entry2])
        snap_store = {"P2": {"기존카테고리": "미설정"}, "P3": {"기존카테고리": "미설정"}}

        class _McpFlaky(_FakeMCP):
            def call_tool(self, name, args):
                if args.get("keyword") == "kw2":
                    raise RuntimeError("네트워크 끊김(2번째 타깃)")
                return super().call_tool(name, args)

        mcp = _McpFlaky({"bulsaja_product_category": [
            {"confirmationToken": "tok",
             "지정될카테고리": {"ss_category": {"name": "A > B"}}},
            {"success": True}]})

        counts = self._run_apply(
            self.run_dir, commit=True, mcp=mcp,
            index_groups=lambda: [("2번_그룹", "SID2"), ("3번_그룹", "SID3")],
            snapshot_load=_fake_snapshot(snap_store),
            snapshot_update=_fake_snapshot_update(snap_store),
            ensure_tab=lambda *a, **k: False, append_rows=lambda *a, **k: 0,
            mark_many=lambda *a, **k: 0, approval_record=lambda *a, **k: True, log=None)

        self.assertEqual(counts.get("적용"), 1)
        self.assertEqual(counts.get("보류"), 1)
        ledger = _read_ledger(self.run_dir)
        self.assertEqual(len(ledger), 2)
        applied = next(r for r in ledger if r["타깃pid"] == "P2")
        held = next(r for r in ledger if r["타깃pid"] == "P3")
        self.assertEqual(applied["결과"], "적용")
        self.assertEqual(held["결과"], "보류")
        self.assertIn("검증실패", held["사유"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
