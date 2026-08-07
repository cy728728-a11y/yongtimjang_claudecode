#!/usr/bin/env python3
"""onestep 상태머신 테스트 — 시트·불사자·파일시스템을 타지 않는다.

`next_action` 은 순수 함수(상태 dict 하나만 본다)라 그대로 검증할 수 있다.
실행 계층(do_prep/do_preview/do_commit)은 여기서 시뮬레이션으로 대체한다 —
이 테스트가 지키려는 것은 **어떤 순서로 무엇을 부르는가**이지 subprocess 동작이 아니다.

핵심 검증: 게이트 모드를 바꿔도 **부르는 명령 자체는 달라지지 않는다.**
이게 깨지면 나중에 자동으로 넘어갈 때 코드를 다시 써야 한다.
"""
import argparse
import os
import sys
import unittest
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from eroomlib.runner import onestep  # noqa: E402
from eroomlib.runner.onestep import (  # noqa: E402
    DONE, GATES, PREPPED, PREVIEWED, RAN, STEPS, TODO, next_action)

FAIL = []


def ok(cond, label):
    print(("  PASS  " if cond else "  FAIL  ") + label)
    if not cond:
        FAIL.append(label)


def new_state(gate="step", pid="U01test"):
    return {"productId": pid, "그룹": "1번_용쌤1-1", "sheet": "SHEET", "group_id": 1,
            "gate": gate, "단계": {s["name"]: {"상태": TODO} for s in STEPS}}


def simulate(gate, signals_on=(), max_steps=60):
    """모드 하나를 끝까지 돌려 (실행한 명령 시퀀스, 게이트가 뜬 지점들)을 돌려준다.

    `signals_on` = 이 단계들의 preview 에서 이상 신호가 났다고 가정.
    """
    st = new_state(gate)
    seq, gates = [], []
    for _ in range(max_steps):
        act = next_action(st)
        kind, step = act["종류"], act.get("단계")
        if kind == "완료":
            break
        if kind == "대기":
            seq.append(("대기", step))
            break
        if kind == "gate":
            gates.append((step, tuple(act.get("대상") or [step])))
            # 승인 처리 — 사람이 승인했다고 본다
            if step == "전체":
                st["승인"] = {"결과": "승인"}
                for n in (act.get("대상") or []):
                    st["단계"][n]["승인"] = {"결과": "승인"}
            else:
                st["단계"][step]["승인"] = {"결과": "승인"}
            continue
        seq.append((kind, step))
        if kind == "prep":
            st["단계"][step]["상태"] = PREPPED
        elif kind == "run":
            st["단계"][step]["상태"] = RAN
        elif kind == "preview":
            st["단계"][step]["상태"] = PREVIEWED
            st["단계"][step]["신호"] = ([{"코드": "x.test"}]
                                       if step in signals_on else [])
            if step == "카테고리":
                st["단계"][step]["가결정"] = "가구/인테리어 > 테이블 > 사이드테이블"
        elif kind == "commit":
            st["단계"][step]["상태"] = DONE
    else:
        raise AssertionError(f"{gate}: 수렴하지 않는다(무한 루프 의심)")
    return seq, gates, st


def main():
    print("== 1. 모든 모드가 전 단계를 완주한다 ==")
    runs = {}
    for g in GATES:
        seq, gates, st = simulate(g)
        runs[g] = (seq, gates, st)
        done = all(st["단계"][s["name"]]["상태"] == DONE for s in STEPS)
        ok(done, f"{g}: {len(STEPS)}단계 전부 완료")

    print("\n== 2. 부르는 명령의 구성은 모드와 무관하다 ==")
    base = Counter(runs["step"][0])
    for g in GATES:
        ok(Counter(runs[g][0]) == base, f"{g}: 명령 구성이 step 과 동일")
    expect = Counter()
    for s in STEPS:
        for k in ("prep", "run", "preview", "commit"):
            # run 이 없는 단계(상세)는 prep 다음 바로 preview 다 — Claude 차례가 없다.
            if k == "run" and not s.get("run"):
                continue
            expect[(k, s["name"])] += 1
    norun = [s["name"] for s in STEPS if not s.get("run")]
    ok(base == expect, f"명령 구성 = 단계 {len(STEPS)}개 × (prep·run·preview·commit), "
                       f"run 없는 단계 제외: {', '.join(norun) or '없음'}")

    print("\n== 3. 게이트를 안 쓰는 모드끼리는 순서까지 같다 ==")
    ok(runs["product"][0] == runs["none"][0], "product 와 none 의 명령 순서가 동일")
    ok(simulate("risky")[0] == runs["none"][0], "신호 없는 risky = none")

    print("\n== 4. 멈추는 지점만 다르다 ==")
    ok(len(runs["step"][1]) == len(STEPS),
       f"step: 게이트 {len(STEPS)}회 (실제 {len(runs['step'][1])})")
    ok(len(runs["product"][1]) == 1, f"product: 게이트 1회 (실제 {len(runs['product'][1])})")
    ok(runs["none"][1] == [], "none: 게이트 0회")
    ok(simulate("risky")[1] == [], "risky(신호 없음): 게이트 0회")
    ok(len(simulate("risky", signals_on=("옵션",))[1]) == 1, "risky(신호 있음): 게이트 1회")

    print("\n== 5. step 모드는 저장이 단계마다 즉시 일어난다 ==")
    seq = runs["step"][0]
    i_commit_cat = seq.index(("commit", "카테고리"))
    i_prep_name = seq.index(("prep", "상품명"))
    ok(i_commit_cat < i_prep_name, "step: 카테고리 저장 → 그 뒤에 상품명 prep")

    print("\n== 6. product 모드는 가공을 다 모은 뒤 저장한다 (썸네일만 옵션 저장 뒤) ==")
    # 2026-08-06: 썸네일 deps 에 옵션이 들어갔다 — 대표옵션은 옵션 commit 이 스냅샷에
    # 써야 생기므로, product 모드에서도 썸네일 preview 는 옵션 commit 뒤로 밀린다.
    seq = runs["product"][0]
    non_thumb_prev = max(i for i, x in enumerate(seq)
                         if x[0] == "preview" and x[1] != "썸네일")
    first_commit = min(i for i, x in enumerate(seq) if x[0] == "commit")
    ok(non_thumb_prev < first_commit, "product: 썸네일 외 모든 preview 뒤에 첫 commit")
    ok(seq.index(("commit", "옵션")) < seq.index(("preview", "썸네일")),
       "product: 옵션 commit 뒤에 썸네일 preview (deps 강제, 2026-08-06)")
    expected_gate = tuple(s["name"] for s in STEPS if s["name"] != "썸네일")
    ok(runs["product"][1][0][1] == expected_gate,
       f"product: 게이트가 썸네일 외 {len(expected_gate)}단계를 한꺼번에 올린다 "
       f"(썸네일은 전체 승인에 편승해 뒤에 자동 커밋)")

    print("\n== 7. DAG: 상품명은 카테고리보다 먼저 시작하지 않는다 ==")
    for g in GATES:
        seq = runs[g][0]
        ok(seq.index(("prep", "카테고리")) < seq.index(("prep", "상품명")),
           f"{g}: 카테고리 prep 이 상품명 prep 보다 앞")

    print("\n== 8. 가결정이 없으면 상품명이 막힌다 ==")
    st = new_state("product")
    st["단계"]["카테고리"]["상태"] = PREVIEWED      # 가결정 없음
    act = next_action(st)
    ok(act["종류"] == "gate" or act.get("단계") != "상품명",
       "가결정 없는 PREVIEWED 카테고리 뒤에 상품명이 진행되지 않는다")
    st["단계"]["카테고리"]["가결정"] = "A > B"
    ok(next_action(st) == {"종류": "prep", "단계": "상품명"},
       "가결정을 심으면 상품명이 진행된다")

    print("\n== 9. 이미 끝난 작업은 건너뛴다(멱등) ==")
    st = new_state("step")
    st["단계"]["카테고리"]["상태"] = DONE
    ok(next_action(st) == {"종류": "prep", "단계": "상품명"}, "완료 단계는 재처리하지 않는다")
    st["단계"]["상품명"]["상태"] = "해당없음"
    ok(next_action(st) == {"종류": "prep", "단계": "옵션"}, "해당없음도 건너뛴다")

    print("\n== 10. redo --from 이 되돌아갈 지점을 고른다 ==")
    from eroomlib.runner.onestep import PREPPED as _P, REDO_FROM
    ok(REDO_FROM == {"prep": TODO, "run": _P, "preview": RAN},
       "prep→미착수 / run→prep완료 / preview→run완료")
    st = new_state("step")
    st["단계"]["카테고리"] = {"상태": DONE, "run_dir": "R1"}
    # --from preview: run 산출물을 살리고 검증만 다시 → 다음 행동이 preview 여야 한다
    st["단계"]["카테고리"] = {"상태": RAN, "run_dir": "R1", "force_preview": True}
    ok(next_action(st) == {"종류": "preview", "단계": "카테고리"},
       "--from preview 뒤에는 prep/run 을 건너뛰고 preview 부터")
    # --from prep: 처음부터
    st["단계"]["카테고리"] = {"상태": TODO}
    ok(next_action(st) == {"종류": "prep", "단계": "카테고리"},
       "--from prep 뒤에는 prep 부터")

    print("\n== 11. 재시도해도 신호가 묻히지 않는다 ==")
    from eroomlib.runner.onestep import _all_signals, _attempts
    from eroomlib.runner.approval_log import codes_of
    d = {"상태": PREVIEWED, "신호": [],
         "신호이력": [{"회차": 1, "신호": [{"코드": "cat.no_result"}], "사유": "검색어 재선정"}]}
    ok([s["코드"] for s in _all_signals(d)] == ["cat.no_result"],
       "마지막 시도가 무신호여도 이전 시도 신호가 남는다")
    ok(_attempts(d) == 2, f"시도 횟수 2 (실제 {_attempts(d)})")
    d2 = {"신호": [{"코드": "x"}], "신호이력": [{"신호": [{"코드": "x"}, {"코드": "y"}]}]}
    ok(codes_of(_all_signals(d2)) == "x; y", "같은 코드는 접는다")
    ok(_all_signals({}) == [] and _attempts({}) == 1, "이력이 없으면 시도 1회")

    print("\n== 12. 보류는 자동 재처리하지 않는다 ==")
    st = new_state("step")
    st["단계"]["카테고리"]["상태"] = "보류(정체불명)"
    act = next_action(st)
    ok(act["종류"] in ("대기", "완료") or act.get("단계") == "옵션",
       f"보류된 카테고리 뒤에 상품명이 진행되지 않는다 (실제: {act})")

    print("\n" + "=" * 52)
    if FAIL:
        print(f"실패 {len(FAIL)}건:")
        for f in FAIL:
            print("  - " + f)
        sys.exit(1)
    print("전부 통과")


class DetailStepTest(unittest.TestCase):
    """Step6 — 상세가 5단계로 붙었는가."""

    def test_상세단계가_등록됐다(self):
        self.assertIn("상세", onestep.STEP_BY_NAME)
        self.assertEqual(len(onestep.STEPS), 5)

    def test_상세는_카테고리에만_의존한다(self):
        # 옵션·썸네일과 마찬가지로 카테고리 이후 아무때나 (마스터 계획서 §부품4 DAG)
        self.assertEqual(onestep.STEP_BY_NAME["상세"]["deps"], ["카테고리"])

    def test_상세는_썸네일_다음_순서다(self):
        names = [s["name"] for s in onestep.STEPS]
        self.assertEqual(names[-2:], ["썸네일", "상세"])

    def test_preview가_generate고_commit이_commit이다(self):
        # 썸네일과 같은 예외 — 승인 대상(생성 이미지) 자체가 생성을 돌려야 나온다
        c = {"rd": "/tmp/rd", "sheet": "S", "pid": "P1", "그룹": "G"}
        self.assertIn("--generate", onestep.STEP_BY_NAME["상세"]["preview"](c))
        self.assertIn("--commit", onestep.STEP_BY_NAME["상세"]["commit"](c))

    def test_prep이_ids로_1건만_돈다(self):
        c = {"rd": "/tmp/rd", "sheet": "S", "pid": "P1", "그룹": "G"}
        argv = onestep.STEP_BY_NAME["상세"]["prep"](c)
        self.assertIn("--ids", argv)
        self.assertIn("P1", argv)
        self.assertIn("run_detail.py", " ".join(argv))


class NoRunStepTest(unittest.TestCase):
    """C1 — run 이 없는 단계는 사람 손 없이 preview 로 넘어간다.

    상세는 '생성=접수→폴링'이라 판단할 것이 없다. 그런데 `output` 을 선언해 두면
    `record` 가 그 파일을 요구하고, 그 파일(generated.json)은 preview 가 만든다 —
    영영 못 넘어간다. 우회로(손으로 --generate 후 record)는 preview 에서 같은 상품을
    한 번 더 생성해 **40크레딧을 두 번** 태운다. 그래서 'run 없음'을 1급 개념으로 둔다.
    """

    def _prepped_detail(self):
        st = new_state()
        for n in ("카테고리", "상품명", "옵션", "썸네일"):
            st["단계"][n]["상태"] = DONE
        st["단계"]["상세"]["상태"] = PREPPED
        return st

    def test_상세는_run이_없다고_선언한다(self):
        self.assertIsNone(onestep.STEP_BY_NAME["상세"].get("run"))

    def test_PREPPED_상세의_다음_행동은_preview다(self):
        act = next_action(self._prepped_detail())
        self.assertEqual(act, {"종류": "preview", "단계": "상세"},
                         "record 없이 preview 로 가야 한다")

    def test_run이_있는_단계는_그대로_run을_요구한다(self):
        st = new_state()
        st["단계"]["카테고리"]["상태"] = PREPPED
        self.assertEqual(next_action(st), {"종류": "run", "단계": "카테고리"})

    def test_record_상세는_거부된다(self):
        st = self._prepped_detail()
        orig = onestep.load_state
        onestep.load_state = lambda pid: st
        try:
            with self.assertRaises(SystemExit) as cm:
                onestep.cmd_record(argparse.Namespace(pid="U01test", step="상세"))
        finally:
            onestep.load_state = orig
        # '산출물이 없다'(경로에 runs/ 가 들어 있어 우연히 'run' 을 품는다)가 아니라
        # **run 이 없는 단계라서** 거부됐다는 걸 못박는다.
        self.assertIn("run 이 없다", str(cm.exception))
        self.assertEqual(st["단계"]["상세"]["상태"], PREPPED, "거부인데 상태가 바뀌었다")

    def test_썸네일_산출물은_run이_실제로_쓰는_파일이다(self):
        # 썸네일 run 은 results/result_NNN.json 을 쓴다. generated.json 은 preview 산출물이라
        # 그걸 output 으로 두면 상세와 같은 교착이 난다(잠재 결함, 같은 뿌리).
        self.assertEqual(onestep.STEP_BY_NAME["썸네일"]["output"], "results/")


class ZeroTargetSentinelTest(unittest.TestCase):
    """I8 — prep 이 '대상 0건'을 알리는 sentinel 을 러너가 알아본다."""

    def test_sentinel_은_0건_완료로_읽힌다(self):
        self.assertEqual(onestep._zero_target({"대상": 0, "이유": "전부 기작업"}),
                         "전부 기작업")

    def test_배치_인덱스는_sentinel_이_아니다(self):
        self.assertIsNone(onestep._zero_target([{"batch": "batch_001.json",
                                                 "상품수": 3}]))
        self.assertIsNone(onestep._zero_target({"대상": 3}))
        self.assertIsNone(onestep._zero_target(None))


if __name__ == "__main__":
    main()
    unittest.main()
