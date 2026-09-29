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


if __name__ == "__main__":
    unittest.main()
