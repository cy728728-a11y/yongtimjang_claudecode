#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`detail_batch.py` 오프라인 테스트 (05-01).

## 여기서 지키는 것은 **크레딧이다**

상세페이지 1건 = 최대 10장 × 5크레딧. 이 파일은 불사자 MCP 를 **한 번도** 부르지 않는다 —
`BulsajaMCP` 를 호출만 기록하는 `가짜MCP` 로 갈아끼우고, `time` 도 가짜 시계로 바꾼다.

## 로드 방식 (가정 A1 — `.venv-web` 에서 뜬다)

`detail_batch.py` 는 최상위에서 `from bulsaja_mcp import BulsajaMCP` 만 한다. 그걸
`sys.modules` 스텁으로 먼저 채워 두면 `bulsaja_mcp` 가 끌고 오는 eroomlib·네트워크 코드를
안 탄다. 그래서 웹앱 스위트(`.venv-web`) 안에서 그대로 돈다 — 첫 테스트가 그걸 실측한다.

**웹앱 런타임은 이 CLI 를 import 하지 않는다.** 테스트 프로세스만 허용한다
(`test_cli_patch.py` 선례). 웹앱은 subprocess 경계로만 부른다.

## 골든 (L-04)

`fixtures/detail_golden_noflag.json` 은 **CLI 를 한 줄도 고치기 전** 커밋에서 만들었다.
플래그 없이 돌린 호출 순서·인자·출력·체크포인트가 그 파일과 한 글자라도 다르면
기존 사용자(스킬 문서대로 터미널에서 돌리는 사람)의 동작이 바뀐 것이다.
다시 만들 때만 `DETAIL_GOLDEN_WRITE=1` — 평소엔 비교만 한다.
"""
import copy
import importlib.util
import json
import os
import sys
import types
from pathlib import Path

import pytest

저장소루트 = Path(__file__).resolve().parents[2]
DETAIL_BATCH = (저장소루트 / ".claude" / "skills" / "bulsaja-detail-page"
                / "scripts" / "detail_batch.py")
FIXTURES = Path(__file__).resolve().parent / "fixtures"
골든경로 = FIXTURES / "detail_golden_noflag.json"


# ── 로더 · 가짜 MCP · 가짜 시계 ────────────────────────────────────────────

class _스텁MCP:
    """로드 시점에만 쓰는 자리표시. 실제 테스트는 `가짜MCP` 로 갈아끼운다."""

    def __init__(self, *a, **k):
        raise AssertionError("스텁 BulsajaMCP 가 호출됐다 — 가짜MCP 주입이 빠졌다")


@pytest.fixture
def cli(monkeypatch):
    """`detail_batch.py` 를 파일 경로에서 로드한다 (가정 A1 · L-04).

    - 로드 **전에** `bulsaja_mcp` 를 스텁으로 채운다 → 네트워크 코드 0
    - `detail_batch.py:51` 이 최상위에서 `sys.path.insert` 를 하므로 끝나면 원복한다
      (`test_banner_scan.py` 의 관용구)
    - `ss_index_calls` 는 inputs 모드가 지연 import 한다 — 캐시에 남으면 다른 테스트가
      그걸 쓰게 되니 끝날 때 원래 상태로 돌린다
    """
    스텁 = types.ModuleType("bulsaja_mcp")
    스텁.BulsajaMCP = _스텁MCP
    monkeypatch.setitem(sys.modules, "bulsaja_mcp", 스텁)
    이전경로 = list(sys.path)
    이전ss = sys.modules.get("ss_index_calls")
    try:
        규격 = importlib.util.spec_from_file_location("_detail_batch_under_test",
                                                    DETAIL_BATCH)
        모듈 = importlib.util.module_from_spec(규격)
        규격.loader.exec_module(모듈)
        yield 모듈
    finally:
        sys.path[:] = 이전경로
        if 이전ss is None:
            sys.modules.pop("ss_index_calls", None)
        else:
            sys.modules["ss_index_calls"] = 이전ss


class 가짜시계:
    """`time.time` / `time.sleep` 대체. sleep 은 기다리지 않고 시계만 민다.

    폴링 deadline 테스트가 이걸로 "4시간 뒤" 를 0초에 만든다.
    """

    def __init__(self, 시작=1_000_000.0):
        self.지금 = 시작
        self.잠 = []

    def time(self):
        return self.지금

    def sleep(self, 초):
        self.잠.append(초)
        self.지금 += float(초)


class 가짜MCP:
    """호출을 `(이름, args 사본)` 으로 기록하고 시나리오 함수로 응답한다.

    시나리오에 없는 도구가 불리면 **바로 실패**한다 — 예상 밖 쓰기 호출을 조용히
    흘려보내지 않기 위해서다.
    """

    def __init__(self, 시나리오):
        self.s = 시나리오
        self.호출 = []
        self.열림 = 0
        self.닫힘 = 0

    def open(self):
        self.열림 += 1

    def close(self):
        self.닫힘 += 1

    def call_tool(self, name, args):
        self.호출.append((name, copy.deepcopy(args)))
        if name not in self.s:
            raise AssertionError(f"시나리오에 없는 도구 호출: {name}")
        return self.s[name](args)

    def 이름들(self, 이름):
        return [a for n, a in self.호출 if n == 이름]


def 주입(monkeypatch, cli, 시나리오, 시계=None):
    """모듈의 `BulsajaMCP`·`time` 을 가짜로 바꾸고 (가짜MCP, 시계) 를 돌려준다."""
    mcp = 가짜MCP(시나리오)
    monkeypatch.setattr(cli, "BulsajaMCP", lambda *a, **k: mcp)
    시계 = 시계 or 가짜시계()
    monkeypatch.setattr(cli, "time", types.SimpleNamespace(time=시계.time,
                                                          sleep=시계.sleep))
    return mcp, 시계


def 실행(monkeypatch, cli, argv):
    """`main()` 을 argv 로 돌려 종료코드를 돌려준다 (정상 반환 = 0)."""
    monkeypatch.setattr(sys, "argv", ["detail_batch.py", *argv])
    try:
        cli.main()
        return 0
    except SystemExit as e:
        if e.code is None:
            return 0
        return e.code if isinstance(e.code, int) else 1


# ── 골든 시나리오 (플래그 없음) ────────────────────────────────────────────

def _이미지(접두, n):
    return [f"https://zzcdn.example/{접두}/{i:02d}.jpg" for i in range(n)]


def _골든_워크데이터():
    """products.json 3건의 workdata.

    (a) aiImageGenerated 없음 + 썸네일 5 + 옵션 7(하나는 제외) → 수집 11 → cap 10
    (b) aiImageGenerated 참 + 10장 → 기작업 스킵 (크레딧 0)
    (c) 옵션 이미지 3장만 → 3장 접수
    """
    옵션a = [{"imageUrl": u, "exclude": False} for u in _이미지("a-opt", 6)]
    옵션a.append({"imageUrl": "https://zzcdn.example/a-opt/excluded.jpg", "exclude": True})
    return {
        "zzpid-00000001": {
            "uploadThumbnails": _이미지("a-thumb", 5),
            "uploadSkuProps": {"mainOption": {"values": 옵션a}},
            "uploadDetailContents": {},
        },
        "zzpid-00000002": {
            "uploadThumbnails": _이미지("b-thumb", 4),
            "uploadDetailContents": {"aiImageGenerated": True,
                                     "aiImageOutputCount": 10,
                                     "aiImageGeneratedAt": "2026-09-01T10:00:00"},
        },
        "zzpid-00000003": {
            "uploadThumbnails": [],
            "uploadSkuProps": {"mainOption": {"values": [
                {"imageUrl": u} for u in _이미지("c-opt", 3)]}},
            "uploadDetailContents": {"aiImageGenerated": "0"},
        },
    }


def _기본시나리오(워크데이터, 예상장수=None, 상태응답=None):
    """generate 2단(토큰 → 확정) + status + workdata 응답 함수 묶음.

    `예상장수` 가 None 이면 요청 sectionCount 를 그대로 돌려준다(정상 접수).
    `상태응답` 은 `(taskId, 호출횟수) -> dict` — 없으면 첫 폴링에 완료.
    """
    작업번호 = {}
    폴링횟수 = {}

    def workdata(a):
        return {"data": copy.deepcopy(워크데이터[a["productId"]])}

    def generate(a):
        pid = a["productId"]
        if not a.get("confirm"):
            return {"confirmationToken": f"tok-{pid}", "예상장수": a["sectionCount"],
                    "예상크레딧": a["sectionCount"] * 5}
        tid = f"task-{pid[-4:]}"
        작업번호[pid] = tid
        exp = a["sectionCount"] if 예상장수 is None else 예상장수(a)
        응답 = {"taskId": tid}
        if exp is not _없음:
            응답["예상장수"] = exp
        return 응답

    def status(a):
        tid = a["taskId"]
        폴링횟수[tid] = 폴링횟수.get(tid, 0) + 1
        if 상태응답:
            return 상태응답(tid, 폴링횟수[tid])
        return {"status": "완료", "생성이미지": ["x"] * 3}

    return {"bulsaja_product_workdata": workdata,
            "bulsaja_detail_page_generate": generate,
            "bulsaja_detail_page_status": status}


_없음 = object()   # 예상장수 키 자체를 빼는 표시


def _골든_돌리기(monkeypatch, cli, tmp_path, capsys):
    run = tmp_path / "run"
    run.mkdir()
    (run / "products.json").write_text(json.dumps(
        ["zzpid-00000001", {"productId": "zzpid-00000002"}, "zzpid-00000003"]),
        encoding="utf-8")
    mcp, _ = 주입(monkeypatch, cli, _기본시나리오(_골든_워크데이터()))
    코드 = 실행(monkeypatch, cli, ["--run-dir", str(run)])
    출력 = capsys.readouterr().out.splitlines()
    return {
        "종료코드": 코드,
        "호출": [[n, a] for n, a in mcp.호출],
        "detail_status": json.loads((run / "detail_status.json").read_text(encoding="utf-8")),
        "출력": 출력,
        "open_close": [mcp.열림, mcp.닫힘],
    }


def test_로더_가_venv_web_에서_뜬다(cli):
    """가정 A1 실측 — 스텁 하나로 `.venv-web` 에서 로드된다(eroomlib 을 안 끈다)."""
    assert callable(cli.main)
    assert cli.BulsajaMCP is _스텁MCP
    # 실행 파이썬이 웹앱 venv 인지 기록 (다른 venv 로 돌면 A1 실측이 아니다)
    assert ".venv-web" in sys.executable or "venv" in sys.prefix


def test_플래그없음_골든_불변(monkeypatch, cli, tmp_path, capsys):
    """L-04 — 플래그 없는 실행이 패치 전 골든과 **완전히** 같다 (정규화 없음)."""
    실제 = _골든_돌리기(monkeypatch, cli, tmp_path, capsys)
    if os.environ.get("DETAIL_GOLDEN_WRITE") == "1":
        골든경로.write_text(json.dumps(실제, ensure_ascii=False, indent=1) + "\n",
                          encoding="utf-8")
    골든 = json.loads(골든경로.read_text(encoding="utf-8"))
    assert 실제 == 골든
