#!/usr/bin/env python3
"""썸네일 웹 주입구 · 러너(thumb_web.py) 오프라인 테스트 (Phase 7 / 07-02).

## 여기서 지키는 것은 **크레딧이다**

불사자 MCP·현황판 시트·이미지 다운로드를 **한 번도** 부르지 않는다. `matrix` 의 시트
입출력(read/mark_many/note_many/flag_many/index_groups), `snapshot.ensure`,
`snapshot.materialize_image`, `run_thumbs.ThumbMCP` 를 가짜로 갈아끼운다.
`matrix.pending`·`redo_pending` 은 **진짜**를 쓴다 — 가짜 매트릭스 dict 로 현황판 규칙을
그대로 태워야 `--only-pending` 교집합이 실제 규칙과 같은지 볼 수 있다.

## 골든 (L-02 · ENG-01)

`fixtures/thumb_golden_noflag.json` 은 **run_thumbs.py 를 한 줄도 고치기 전** 커밋에서
만들었다(detail_golden_noflag 선례). 플래그 없이 돌린 prep 산출물·현황판 호출·stdout,
apply --generate 의 호출 순서가 그 파일과 한 글자라도 다르면 스킬 문서대로 터미널에서
돌리는 기존 사용자의 동작이 바뀐 것이다.
다시 만들 때만 `THUMB_GOLDEN_WRITE=1` — 평소엔 비교만 한다.

    .venv/bin/python3 -m pytest -q .claude/skills/bulsaja-thumbnail/scripts/test_thumb_web.py
"""
import argparse
import contextlib
import copy
import glob
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import run_thumbs                       # noqa: E402 — import 시 eroomlib 경로를 잡아준다
from eroomlib import matrix, snapshot   # noqa: E402

FIXTURES = os.path.join(SCRIPT_DIR, "fixtures")
GOLDEN = os.path.join(FIXTURES, "thumb_golden_noflag.json")
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))

SHEET = "SHEET_FAKE"

# ── 시나리오 픽스처 — 상품 5개 ─────────────────────────────────────────────
#   U01new  미가공 + 대표옵션 이미지 있음 → 생성 대상(확정 선기록)
#   U02new  미가공 + 옵션 없음            → 생성 대상(비전 배치)
#   U03back 가공됨 + 대표옵션 없음        → 완료 백필(이미가공)
#   U04aud  가공됨 + 대표옵션 있음        → 정합검사
#   U05err  스냅샷 조회 실패              → 조회실패
PIDS = ["U01new", "U02new", "U03back", "U04aud", "U05err"]


def _opt(url):
    return {"판매행": [{"text": "기본형", "main_product": True, "urlRef": url}]}


RECS = {
    "U01new": {"상품명": "유압자키", "썸네일": ["https://img.alicdn.com/a0.jpg",
                                              "https://img.alicdn.com/a1.jpg"],
               "옵션": _opt("https://img.alicdn.com/a-main.jpg")},
    "U02new": {"상품명": "캠핑의자", "썸네일": ["https://img.alicdn.com/b0.jpg",
                                              "https://img.alicdn.com/b1.jpg",
                                              "https://img.alicdn.com/b2.jpg"]},
    "U03back": {"상품명": "전기타카", "썸네일": ["https://cdn.bulsaja.com/c0.jpg"]},
    "U04aud": {"상품명": "풍속계", "썸네일": ["https://cdn.bulsaja.com/d0.jpg"],
               "옵션": _opt("https://img.alicdn.com/d-main.jpg")},
}
ERRORS = {"U05err": "RuntimeError: timeout"}

# 현황판 — 5개 전부 썸네일 빈칸 + 이미 완료인 U06done(무플래그 pending 경로에서 빠져야 한다)
MATRIX = {pid: {"row": i + 2, "상품": "", "썸네일": "", "옵션": "완료"}
          for i, pid in enumerate(PIDS)}
MATRIX["U06done"] = {"row": 7, "상품": "", "썸네일": "완료", "옵션": "완료"}


def _prep_args(run_dir, ids=None, **extra):
    ns = argparse.Namespace(run_dir=run_dir, sheet=SHEET, group_name="",
                            ids=ids, limit=0, batch_size=12, max_candidates=5,
                            sleep=0, max_px=512)
    for k, v in extra.items():
        setattr(ns, k, v)
    return ns


def _apply_args(run_dir, **extra):
    ns = argparse.Namespace(run_dir=run_dir, sheet=SHEET, group_name="", ids=None,
                            generate=True, commit=False, allow_missing=False,
                            no_sheet=True, no_matrix=True, sleep=0)
    for k, v in extra.items():
        setattr(ns, k, v)
    return ns


class _금지MCP:
    """테스트에서 MCP 를 여는 순간 터진다 — 크레딧·쓰기 경로가 새지 않게."""

    def __init__(self, *a, **k):
        raise AssertionError("진짜 ThumbMCP 가 호출됐다 — 가짜 주입이 빠졌다")


def _normalize(obj, run_dir):
    """tmp 경로 → `<RUN>`, 저장소 경로 → `<REPO>` 치환 (골든을 기계 독립으로)."""
    if isinstance(obj, str):
        return obj.replace(run_dir, "<RUN>").replace(REPO_ROOT, "<REPO>")
    if isinstance(obj, list):
        return [_normalize(v, run_dir) for v in obj]
    if isinstance(obj, tuple):
        return [_normalize(v, run_dir) for v in obj]
    if isinstance(obj, dict):
        return {k: _normalize(v, run_dir) for k, v in obj.items()}
    return obj


class Harness(unittest.TestCase):
    """시트·스냅샷·다운로드·MCP 를 전부 가짜로 — 현황판 호출은 self.calls 에 쌓인다."""

    def setUp(self):
        self.run_dir = tempfile.mkdtemp()
        self.calls = []
        self.read_count = 0
        self.matrix_data = copy.deepcopy(MATRIX)
        self._orig_matrix = {k: getattr(matrix, k) for k in
                             ("read", "mark_many", "note_many", "flag_many",
                              "index_groups")}
        self._orig_snap = {k: getattr(snapshot, k) for k in
                           ("ensure", "materialize_image")}
        self._orig_rt = {k: getattr(run_thumbs, k) for k in
                         ("ThumbMCP", "_guard_credits", "_generate", "_audit",
                          "_commit")}

        def _read(sheet, *a, **k):
            self.read_count += 1
            self.calls.append(["read", sheet])
            return copy.deepcopy(self.matrix_data)

        def _mark_many(sheet, task, values, *a, **k):
            self.calls.append(["mark_many", sheet, task, dict(sorted(values.items()))])
            return len(values)

        def _note_many(sheet, items, *a, **k):
            self.calls.append(["note_many", sheet, dict(sorted(items.items()))])
            return len(items)

        def _flag_many(sheet, task, items, *a, **k):
            self.calls.append(["flag_many", sheet, task, dict(sorted(items.items()))])
            return len(items)

        matrix.read = _read
        matrix.mark_many = _mark_many
        matrix.note_many = _note_many
        matrix.flag_many = _flag_many
        matrix.index_groups = lambda *a, **k: [("그룹A", SHEET)]

        def _ensure(pids, **kw):
            self.calls.append(["ensure", list(pids)])
            recs = {p: copy.deepcopy(RECS[p]) for p in pids if p in RECS}
            errs = {p: ERRORS[p] for p in pids if p in ERRORS}
            return recs, errs

        snapshot.ensure = _ensure
        # 실제 다운로드 대신 "받았다"고만 답한다 — 파일은 안 만든다.
        snapshot.materialize_image = (
            lambda url, d, stem, i, **kw: (os.path.join(d, f"{stem}_{i}.jpg"), url))
        run_thumbs.ThumbMCP = _금지MCP

    def tearDown(self):
        for k, v in self._orig_matrix.items():
            setattr(matrix, k, v)
        for k, v in self._orig_snap.items():
            setattr(snapshot, k, v)
        for k, v in self._orig_rt.items():
            setattr(run_thumbs, k, v)
        shutil.rmtree(self.run_dir, ignore_errors=True)

    # ── 도우미 ──
    def _run_prep(self, args):
        out = io.StringIO()
        err = io.StringIO()
        code = None
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                run_thumbs.cmd_prep(args)
            except SystemExit as e:
                code = e.code
        return code, out.getvalue(), err.getvalue()

    def _files(self):
        """run_dir 안의 json 산출물 전부 {상대경로: 내용}."""
        got = {}
        for path in sorted(glob.glob(os.path.join(self.run_dir, "**", "*.json"),
                                     recursive=True)):
            rel = os.path.relpath(path, self.run_dir)
            with open(path, encoding="utf-8") as f:
                got[rel] = json.load(f)
        return got

    def _snapshot_prep(self, args):
        code, out, _err = self._run_prep(args)
        return _normalize({"exit": code, "files": self._files(), "calls": self.calls,
                           "stdout": out.splitlines()}, self.run_dir)

    def _write_results(self, products, name="result_000.json"):
        path = os.path.join(self.run_dir, "results", name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"배치": 0, "선기록": True, "products": products}, f,
                      ensure_ascii=False)

    def _write_generated(self, obj):
        with open(os.path.join(self.run_dir, "generated.json"), "w",
                  encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)

    def _gen_products(self, pids):
        return [{"productId": p, "상품명": p, "기존썸네일": ["https://img.alicdn.com/x.jpg"],
                 "대표옵션이미지": "https://img.alicdn.com/m.jpg", "모드": "기본"}
                for p in pids]

    def _run_apply(self, args):
        seq = []
        run_thumbs._audit = lambda run_dir: ([], False)
        run_thumbs._guard_credits = lambda items: seq.append(
            ["_guard_credits", sorted(p["productId"] for p in items)])
        run_thumbs._generate = lambda sheet, run_dir, items, a: seq.append(
            ["_generate", sorted(p["productId"] for p in items)])
        out, err = io.StringIO(), io.StringIO()
        code = None
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                run_thumbs.cmd_apply(args)
            except SystemExit as e:
                code = e.code
        return code, seq, out.getvalue(), err.getvalue()


# ─────────────────────────────────────────────────────────────────────────
# 무플래그 골든
# ─────────────────────────────────────────────────────────────────────────

class NoFlagGoldenTest(Harness):

    def _current(self):
        doc = {}
        doc["prep_ids"] = self._snapshot_prep(_prep_args(self.run_dir, ids=list(PIDS)))
        # pending 경로는 새 run_dir 로 — 산출물이 섞이지 않게
        shutil.rmtree(self.run_dir, ignore_errors=True)
        self.run_dir = tempfile.mkdtemp()
        self.calls = []
        doc["prep_pending"] = self._snapshot_prep(_prep_args(self.run_dir, ids=None))
        # apply --generate: _guard_credits 다음 exit 없이 _generate 로 간다
        shutil.rmtree(self.run_dir, ignore_errors=True)
        self.run_dir = tempfile.mkdtemp()
        self._write_results(self._gen_products(["U01new", "U02new"]))
        code, seq, _out, _err = self._run_apply(_apply_args(self.run_dir))
        doc["apply_generate"] = {"exit": code, "seq": seq}
        return doc

    def test_플래그없음_골든_불변(self):
        cur = self._current()
        if os.environ.get("THUMB_GOLDEN_WRITE") == "1":
            os.makedirs(FIXTURES, exist_ok=True)
            with open(GOLDEN, "w", encoding="utf-8") as f:
                json.dump(cur, f, ensure_ascii=False, indent=2)
                f.write("\n")
        self.assertTrue(os.path.exists(GOLDEN),
                        "골든 파일이 없다 — THUMB_GOLDEN_WRITE=1 로 수정 전 CLI 에서 만든다")
        with open(GOLDEN, encoding="utf-8") as f:
            golden = json.load(f)
        self.assertEqual(golden, json.loads(json.dumps(cur, ensure_ascii=False)),
                         "무플래그 동작이 골든과 다르다 — 기존 사용자의 동작이 바뀌었다")

    def test_골든_시나리오가_네_갈래를_모두_탄다(self):
        with open(GOLDEN, encoding="utf-8") as f:
            golden = json.load(f)
        files = golden["prep_ids"]["files"]
        self.assertEqual(files["audit_targets.json"], ["U04aud"])
        self.assertIn(["mark_many", SHEET, "썸네일", {"U03back": "완료(기존 가공 확인)"}],
                      golden["prep_ids"]["calls"])
        self.assertEqual(golden["apply_generate"]["exit"], None)
        self.assertEqual([s[0] for s in golden["apply_generate"]["seq"]],
                         ["_guard_credits", "_generate"])
        # pending 경로는 완료건(U06done)을 집지 않는다
        ensure = [c for c in golden["prep_pending"]["calls"] if c[0] == "ensure"][0]
        self.assertNotIn("U06done", ensure[1])


# ─────────────────────────────────────────────────────────────────────────
# 주입구 — prep --estimate-out / --only-pending / --expect-nick
# ─────────────────────────────────────────────────────────────────────────

class _가짜MCP:
    """프로필 조회·대표 저장·재조회만 흉내 — 생성(크레딧) 도구가 불리면 터진다."""
    nick = "용팀장"
    profile_error = None
    log = []

    def __init__(self, *a, **k):
        pass

    def open(self):
        _가짜MCP.log.append(["open"])

    def close(self):
        _가짜MCP.log.append(["close"])

    def call_tool(self, name, payload):
        _가짜MCP.log.append(["call_tool", name])
        if name == "bulsaja_my_profile":
            if _가짜MCP.profile_error:
                raise _가짜MCP.profile_error
            return {"닉네임": _가짜MCP.nick, "크레딧": "1,000"}
        raise AssertionError(f"허용 안 된 도구 호출: {name}")

    def generate(self, *a, **k):
        raise AssertionError("생성(크레딧) 호출 — 절대 불리면 안 된다")

    def update_thumbnails(self, pid, thumbs):
        _가짜MCP.log.append(["update_thumbnails", pid])

    def workdata(self, pid):
        return {"썸네일": ["https://cdn.bulsaja.com/new.jpg"]}


class EstimateOutTest(Harness):

    def _estimate(self):
        path = os.path.join(self.run_dir, "estimate.json")
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _args(self, ids, **extra):
        return _prep_args(self.run_dir, ids=ids,
                          estimate_out=os.path.join(self.run_dir, "estimate.json"),
                          **extra)

    def test_시나리오_5개_견적(self):
        code, _out, _err = self._run_prep(self._args(list(PIDS)))
        self.assertIsNone(code)
        est = self._estimate()
        self.assertEqual(est["선택"], PIDS)
        self.assertEqual(sorted(est["대상"]), ["U01new", "U02new"])
        self.assertEqual(est["이미가공"], {"U03back": "완료(기존 가공 확인)"})
        self.assertEqual(est["정합검사"], ["U04aud"])
        self.assertEqual(list(est["조회실패"]), ["U05err"])
        self.assertEqual(est["삭제대상"], {})
        self.assertEqual(est["현황판제외"], {})
        self.assertEqual(est["예상크레딧"], 10)
        self.assertEqual(est["최대크레딧"], 20)
        self.assertEqual(est["시트id"], SHEET)
        self.assertIsNone(est["오류"])

    def test_대상_0건_조기반환에도_파일을_쓴다(self):
        self.matrix_data["U01new"]["썸네일"] = "완료"
        code, _o, _e = self._run_prep(self._args(["U01new"], only_pending=True))
        self.assertIsNone(code)
        est = self._estimate()
        self.assertEqual(est["대상"], [])
        self.assertEqual(est["예상크레딧"], 0)
        self.assertEqual(est["최대크레딧"], 0)
        self.assertEqual(est["현황판제외"], {"U01new": "완료"})

    def test_조회실패만_있어도_파일을_쓴다(self):
        self._run_prep(self._args(["U05err"]))
        est = self._estimate()
        self.assertIsNotNone(est, "조회실패 경로에서 견적 파일이 없다 — 고장과 0건을 못 가른다")
        self.assertEqual(est["대상"], [])
        self.assertEqual(list(est["조회실패"]), ["U05err"])
        # 무플래그 규칙 유지 — 조회실패 0건은 sentinel 을 안 남긴다
        self.assertFalse(os.path.exists(os.path.join(self.run_dir, "batches_index.json")))

    def test_기작업만이면_이미가공만_찬다(self):
        self._run_prep(self._args(["U03back"]))
        est = self._estimate()
        self.assertEqual(est["대상"], [])
        self.assertEqual(est["이미가공"], {"U03back": "완료(기존 가공 확인)"})


class OnlyPendingTest(Harness):

    def test_ids_와_현황판_pending_교집합(self):
        self.matrix_data["U02new"]["썸네일"] = "완료"
        self.matrix_data["U03back"]["썸네일"] = "보류(원본404·삭제대상)"
        est_path = os.path.join(self.run_dir, "estimate.json")
        self._run_prep(_prep_args(self.run_dir, ids=["U01new", "U02new", "U03back"],
                                  only_pending=True, estimate_out=est_path))
        ensure = [c for c in self.calls if c[0] == "ensure"]
        self.assertEqual(ensure, [["ensure", ["U01new"]]])
        with open(est_path, encoding="utf-8") as f:
            est = json.load(f)
        self.assertEqual(est["현황판제외"],
                         {"U02new": "완료", "U03back": "보류(원본404·삭제대상)"})
        self.assertEqual(est["대상"], ["U01new"])

    def test_재작업은_pending_이라_남는다(self):
        self.matrix_data["U02new"]["썸네일"] = "재작업(색 다름)"
        self._run_prep(_prep_args(self.run_dir, ids=["U02new"], only_pending=True))
        ensure = [c for c in self.calls if c[0] == "ensure"]
        self.assertEqual(ensure, [["ensure", ["U02new"]]])

    def test_플래그_없으면_교집합_안_한다(self):
        self.matrix_data["U02new"]["썸네일"] = "완료"
        self._run_prep(_prep_args(self.run_dir, ids=["U01new", "U02new"]))
        ensure = [c for c in self.calls if c[0] == "ensure"]
        self.assertEqual(ensure, [["ensure", ["U01new", "U02new"]]])


class ExpectNickTest(Harness):

    def setUp(self):
        super().setUp()
        _가짜MCP.nick = "용팀장"
        _가짜MCP.profile_error = None
        _가짜MCP.log = []
        run_thumbs.ThumbMCP = _가짜MCP

    def test_닉_불일치면_시트_읽기_전에_exit4(self):
        _가짜MCP.nick = "용쌤"
        code, _o, err = self._run_prep(_prep_args(self.run_dir, ids=list(PIDS),
                                                  expect_nick="용팀장"))
        self.assertEqual(code, 4)
        self.assertEqual(self.read_count, 0)
        self.assertIn("[계정]", err)
        self.assertIn(["close"], _가짜MCP.log)

    def test_프로필_조회_예외도_exit4(self):
        _가짜MCP.profile_error = RuntimeError("503")
        code, _o, _e = self._run_prep(_prep_args(self.run_dir, ids=list(PIDS),
                                                 expect_nick="용팀장"))
        self.assertEqual(code, 4)
        self.assertEqual(self.read_count, 0)

    def test_닉_일치면_진행한다(self):
        code, _o, _e = self._run_prep(_prep_args(self.run_dir, ids=list(PIDS),
                                                 expect_nick="용팀장"))
        self.assertIsNone(code)
        self.assertGreaterEqual(self.read_count, 1)


# ─────────────────────────────────────────────────────────────────────────
# 주입구 — apply --generate --max-credits · apply --commit --summary-out
# ─────────────────────────────────────────────────────────────────────────

class MaxCreditsTest(Harness):

    def setUp(self):
        super().setUp()
        self._write_results(self._gen_products(["U01new", "U02new"]))

    def test_누적0_계획10_상한10_통과(self):
        code, seq, _o, _e = self._run_apply(_apply_args(self.run_dir, max_credits=10))
        self.assertIsNone(code)
        self.assertEqual([s[0] for s in seq], ["_guard_credits", "_generate"])

    def test_재생성_누적이_상한을_넘기면_exit5(self):
        self._write_generated({"U09x": {"생성본": "https://cdn.bulsaja.com/g.jpg",
                                        "재생성횟수": 1}})
        code, seq, _o, err = self._run_apply(_apply_args(self.run_dir, max_credits=10))
        self.assertEqual(code, 5)
        self.assertEqual(seq, [], "상한 초과인데 잔액조회·생성이 불렸다")
        self.assertIn("승인 상한 초과", err)

    def test_미회수_taskId_도_누적에_든다(self):
        self._write_generated({"U09y": {"taskId": "t-1",
                                        "오류": "접수함 — 결과 미확인"}})
        code, seq, _o, _e = self._run_apply(_apply_args(self.run_dir, max_credits=14))
        self.assertEqual(code, 5)
        self.assertEqual(seq, [])
        code, seq, _o, _e = self._run_apply(_apply_args(self.run_dir, max_credits=15))
        self.assertIsNone(code)
        self.assertEqual([s[0] for s in seq], ["_guard_credits", "_generate"])

    def test_재생성_호출도_누적으로_막힌다(self):
        # 1회차 2건 생성 완료(누적 10) → --ids 로 1건 재생성하려면 10 + 5 = 15
        self._write_generated({
            "U01new": {"생성본": "https://cdn.bulsaja.com/1.jpg", "재생성횟수": 1},
            "U02new": {"생성본": "https://cdn.bulsaja.com/2.jpg", "재생성횟수": 1}})
        code, seq, _o, _e = self._run_apply(
            _apply_args(self.run_dir, max_credits=10, ids=["U01new"]))
        self.assertEqual(code, 5)
        self.assertEqual(seq, [])


class CommitSummaryTest(Harness):

    def setUp(self):
        super().setUp()
        _가짜MCP.log = []
        run_thumbs.ThumbMCP = _가짜MCP
        self._orig_update = snapshot.update
        snapshot.update = lambda pid, **kw: None
        self._write_results(self._gen_products(["U01new", "U02new"]))
        self._write_generated({
            "U01new": {"상품명": "유압자키", "생성본": "https://cdn.bulsaja.com/1.jpg",
                       "후보": [], "재생성횟수": 1},
            "U02new": {"상품명": "캠핑의자", "오류": "TimeoutError", "taskId": "t-2"}})
        with open(os.path.join(self.run_dir, "decisions.json"), "w",
                  encoding="utf-8") as f:
            json.dump({}, f)

    def tearDown(self):
        snapshot.update = self._orig_update
        super().tearDown()

    def _commit(self, **extra):
        run_thumbs._audit = lambda run_dir: ([], False)
        args = _apply_args(self.run_dir, generate=False, commit=True, **extra)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            run_thumbs.cmd_apply(args)
        return out.getvalue()

    def test_summary_out_에_완료_보류(self):
        path = os.path.join(self.run_dir, "commit_summary.json")
        out = self._commit(summary_out=path)
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        self.assertEqual(doc["완료"], ["U01new"])
        self.assertEqual(doc["보류"], {"U02new": "보류(생성실패)"})
        commit_lines = [ln for ln in out.splitlines() if ln.startswith("###COMMIT###")]
        self.assertEqual(commit_lines, ["###COMMIT### 반영 1건 / 보류·실패 0건"])
        # 원자 쓰기 — 임시 파일이 남지 않는다
        self.assertEqual([n for n in os.listdir(self.run_dir) if n.endswith(".tmp")], [])

    def test_플래그_없으면_요약_파일을_안_쓴다(self):
        out = self._commit()
        self.assertFalse(os.path.exists(os.path.join(self.run_dir, "commit_summary.json")))
        self.assertIn("###COMMIT### 반영 1건 / 보류·실패 0건", out)


class ArgparseFlagsTest(unittest.TestCase):
    """새 플래그 5개가 파서에 있고, 기본값이 무플래그 경로를 고른다."""

    def _parse(self, argv):
        import unittest.mock as mock
        captured = {}
        with mock.patch.object(sys, "argv", ["run_thumbs.py", *argv]), \
                mock.patch.object(run_thumbs, "cmd_prep",
                                  lambda a: captured.setdefault("a", a)), \
                mock.patch.object(run_thumbs, "cmd_apply",
                                  lambda a: captured.setdefault("a", a)):
            # set_defaults 가 main() 안에서 함수 객체를 잡으므로 여기서 다시 읽힌다
            run_thumbs.main()
        return captured["a"]

    def test_prep_기본값(self):
        a = self._parse(["prep", "--run-dir", "/tmp/x", "--sheet", "S"])
        self.assertIsNone(a.estimate_out)
        self.assertFalse(a.only_pending)
        self.assertEqual(a.expect_nick, "")

    def test_prep_플래그(self):
        a = self._parse(["prep", "--run-dir", "/tmp/x", "--sheet", "S", "--ids", "a",
                         "--only-pending", "--expect-nick", "용팀장",
                         "--estimate-out", "/tmp/x/e.json"])
        self.assertTrue(a.only_pending)
        self.assertEqual(a.expect_nick, "용팀장")
        self.assertEqual(a.estimate_out, "/tmp/x/e.json")

    def test_apply_플래그(self):
        a = self._parse(["apply", "--run-dir", "/tmp/x", "--sheet", "S"])
        self.assertIsNone(a.max_credits)
        self.assertIsNone(a.summary_out)
        a = self._parse(["apply", "--run-dir", "/tmp/x", "--sheet", "S", "--generate",
                         "--max-credits", "30", "--summary-out", "/tmp/x/s.json"])
        self.assertEqual(a.max_credits, 30)
        self.assertEqual(a.summary_out, "/tmp/x/s.json")


if __name__ == "__main__":
    unittest.main()
