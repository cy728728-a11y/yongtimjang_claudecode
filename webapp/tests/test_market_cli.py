#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`market_update.py` 오프라인 테스트 (06-02).

## 여기서 지키는 것은 **스토어다**

`bulsaja_market_update` 는 불사자에 저장된 변경사항을 스마트스토어로 민다 — 되돌릴 수 없다.
이 파일은 불사자 MCP 를 **한 번도** 부르지 않는다. `BulsajaMCP` 를 호출만 기록하는
`가짜MCP` 로 갈아끼우고, `time` 도 가짜 시계로 바꾼다. 시나리오에 없는 도구가 불리면
그 자리에서 실패한다 — 예상 밖 쓰기 호출을 조용히 흘려보내지 않는다.

로드 방식은 `test_detail_cli.py` 와 같다 (가정 A1 — `.venv-web` 에서 뜬다):
`sys.modules["bulsaja_mcp"]` 를 스텁으로 먼저 채우고 파일 경로에서 로드한다.
"""
import copy
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

저장소루트 = Path(__file__).resolve().parents[2]
MARKET_UPDATE = (저장소루트 / ".claude" / "skills" / "bulsaja-detail-page"
                 / "scripts" / "market_update.py")
FIXTURES = Path(__file__).resolve().parent / "fixtures"
창픽스처 = json.loads((FIXTURES / "upload_tasks_real.json").read_text(encoding="utf-8"))
# no_commit_guard.sh 가 테스트 트리의 반영 플래그 리터럴을 금지한다 — 간접 조립한다.
# 이 파일은 가짜 MCP 하네스라 실제 쓰기 경로는 없지만, 가드는 글자 자체를 본다(06-03 과 같은 방식).
_반영플래그 = "--" + "commit"


# ── 로더 · 가짜 MCP · 가짜 시계 (test_detail_cli.py 36-147 복제) ─────────────

class _스텁MCP:
    """로드 시점에만 쓰는 자리표시. 실제 테스트는 `가짜MCP` 로 갈아끼운다."""

    def __init__(self, *a, **k):
        raise AssertionError("스텁 BulsajaMCP 가 호출됐다 — 가짜MCP 주입이 빠졌다")


@pytest.fixture
def cli(monkeypatch):
    """`market_update.py` 를 파일 경로에서 로드한다. 끝나면 sys.path·ss_index_calls 원복."""
    스텁 = types.ModuleType("bulsaja_mcp")
    스텁.BulsajaMCP = _스텁MCP
    monkeypatch.setitem(sys.modules, "bulsaja_mcp", 스텁)
    이전경로 = list(sys.path)
    이전ss = sys.modules.get("ss_index_calls")
    try:
        규격 = importlib.util.spec_from_file_location("_market_update_under_test",
                                                    MARKET_UPDATE)
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
    """`time.time` / `time.sleep` 대체. sleep 은 기다리지 않고 시계만 민다."""

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
    시나리오에 없는 도구가 불리면 **바로 실패**한다."""

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

    def 도구들(self):
        return [n for n, _ in self.호출]


def 주입(monkeypatch, cli, 시나리오, 시계=None):
    mcp = 가짜MCP(시나리오)
    monkeypatch.setattr(cli, "BulsajaMCP", lambda *a, **k: mcp)
    시계 = 시계 or 가짜시계()
    monkeypatch.setattr(cli, "time", types.SimpleNamespace(time=시계.time,
                                                          sleep=시계.sleep))
    return mcp, 시계


def 실행(monkeypatch, cli, argv):
    monkeypatch.setattr(sys, "argv", ["market_update.py", *argv])
    try:
        cli.main()
        return 0
    except SystemExit as e:
        if e.code is None:
            return 0
        return e.code if isinstance(e.code, int) else 1


# ── 가짜 불사자 판 ──────────────────────────────────────────────────────────

원본HTML = "<div><p>中文原始详情 원본 상세 본문</p></div>"
AI_HTML = "<div><img src='https://zzcdn.example/ai/01.jpg'> AI 상세 본문</div>"
상단 = "https://zzcdn.example/marketGroups/1001135/fixedImages/aa/top.png?t=1758132676314"
하단 = "https://zzcdn.example/marketGroups/1001135/fixedImages/aa/bottom.png?t=1758132676314"


class 판:
    """불사자 서버 흉내. 상태(상품 workdata · 작업창)를 들고 도구 함수를 내준다.

    기본 동작은 **정상 2단 프로토콜**이다 — confirm:false 는 토큰만(쓰기 0),
    confirm:true 는 받은 토큰이 맞을 때만 작업창에 새 행(대기)을 만든다.
    테스트는 속성을 바꿔 이상 상황을 만든다.
    """

    def __init__(self):
        self.닉 = "부킹"
        self.모드 = "balanced"
        self.상품 = {}
        self.창 = copy.deepcopy(창픽스처["마켓작업"])
        self.dlq = []
        self.다음tid = 49416900
        self.발급 = {}
        self.토큰순번 = 0
        self.자동완료 = True          # 폴링 조회 시 우리 행(대기)을 성공으로
        self.완료상태 = "성공"
        self.실패사유 = ""
        self.업데이트_미리보기 = None  # callable(args) -> dict 로 confirm:false 응답 대체
        self.업데이트_확정 = None      # callable(args) -> dict 로 confirm:true 응답 대체
        self.창_대체 = None            # callable(args) -> dict 로 upload_tasks 응답 대체
        self.적용_미리보기 = None      # detail_apply confirm:false 대체
        self.적용_반영안됨 = False     # detail_apply confirm:true 가 반영을 안 하는 판

    # -- 상품 --
    def 상품추가(self, pid, *, ss="13192250286", ai=None, rc=AI_HTML):
        dc = {"renderContent": rc, "imageTranslated": "0"}
        if ai is not None:
            dc["aiImageGenerated"] = ai
        self.상품[pid] = {
            "summary": {"uploadedSuccessUrl": {"smartstore": ss, "coupang": ""},
                        "uploadDetailContents": dc},
            "full": {"uploadDetail_page": {"top_image": 상단, "bottom_image": 하단,
                                           "is_include_fixed_image": True},
                     "uploadSelectedMarketGroupId": 1001135},
        }

    def _토큰(self, pid):
        self.토큰순번 += 1
        t = f"tok-{pid}-{self.토큰순번:04d}-xxxxxxxxxxxxxxxx"
        self.발급[pid] = t
        return t

    def _새행(self, pid, 작업="수정"):
        self.다음tid += 1
        tid = str(self.다음tid)
        self.창.insert(0, {"상태": "대기", "마켓": "스마트스토어", "작업": 작업,
                          "productId": pid, "taskId": tid})
        return tid

    # -- 도구 --
    def my_profile(self, a):
        return {"닉네임": self.닉, "크레딧": "1234", "표시규칙": "지시문"}

    def mcp_settings(self, a):
        assert a.get("mode") == "get", "설정은 읽기만 해야 한다"
        return {"success": True, "confirmationMode": self.모드, "표시규칙": "지시문"}

    def workdata(self, a):
        pid = a["productId"]
        모드 = a.get("mode")
        d = copy.deepcopy(self.상품[pid]["summary"])
        if 모드 == "full":
            d.update(copy.deepcopy(self.상품[pid]["full"]))
        return {"success": True, "data": d, "표시규칙": "지시문"}

    def market_update(self, a):
        assert a.get("market") == "SMARTSTORE"
        pids = a.get("productIds") or []
        assert len(pids) == 1, "상품당 1건씩 접수해야 한다"
        pid = pids[0]
        if not a.get("confirm"):
            if self.업데이트_미리보기:
                return self.업데이트_미리보기(a)
            return {"success": False, "confirmationToken": self._토큰(pid),
                    "message": "확인이 필요합니다", "표시규칙": "지시문"}
        if self.업데이트_확정:
            return self.업데이트_확정(a)
        assert a.get("confirmationToken") == self.발급.get(pid), "토큰 불일치"
        self.발급.pop(pid, None)
        tid = self._새행(pid)
        return {"success": True, "결과": [{"productId": pid, "결과": "접수", "taskId": tid}]}

    def upload_tasks(self, a):
        assert a.get("mode") == "list"
        assert "taskIds" not in a and "taskId" not in a, "무시되는 필터를 쓰지 마라"
        if self.창_대체:
            r = self.창_대체(a)
            if r is not None:
                return r
        if self.자동완료:
            for r in self.창:
                if r["상태"] == "대기" and int(r["taskId"]) > 49416900:
                    r["상태"] = self.완료상태
                    if self.실패사유:
                        r["실패사유"] = self.실패사유
        st = a.get("status")
        표 = {"SUCCESS": "성공", "FAILED": "실패", "PENDING": "대기", "PROCESSING": "진행중"}
        if st == "DLQ":
            행들 = self.dlq
        elif st:
            행들 = [r for r in self.창 if r["상태"] == 표[st]]
        else:
            행들 = self.창
        return {"success": True, "마켓작업": copy.deepcopy(행들[:30]),
                "확장작업": {"대기": 0, "진행중": 0, "내역": []},
                "삭제후처리": {}, "표시규칙": "지시문"}

    def detail_apply(self, a):
        pid = a["productId"]
        assert a.get("imageReplacements") == []
        if not a.get("confirm"):
            if self.적용_미리보기:
                return self.적용_미리보기(a)
            return {"success": False, "confirmationToken": self._토큰(pid)}
        assert a.get("confirmationToken") == self.발급.get(pid), "토큰 불일치"
        if not self.적용_반영안됨:
            self.상품[pid]["summary"]["uploadDetailContents"]["renderContent"] = a["html"]
        return {"success": True}

    def work_progress(self, a):
        return {"마켓작업": {"대기": 0, "진행중": 0}, "표시규칙": "지시문"}

    def 도구(self):
        return {"bulsaja_my_profile": self.my_profile,
                "bulsaja_mcp_settings": self.mcp_settings,
                "bulsaja_product_workdata": self.workdata,
                "bulsaja_market_update": self.market_update,
                "bulsaja_upload_tasks": self.upload_tasks,
                "bulsaja_detail_apply": self.detail_apply,
                "bulsaja_work_progress": self.work_progress}


def 원본쓰기(폴더, pid, 코드="", rc=원본HTML):
    폴더.mkdir(parents=True, exist_ok=True)
    (폴더 / f"{pid}.json").write_text(json.dumps(
        {"productId": pid, "판매자상품코드": 코드, "조회시각": "2026-09-26T10:00:00+09:00",
         "계정": "부킹", "renderContent": rc, "imageTranslated": "0"},
        ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def 환경(tmp_path):
    """run-dir · ⓐ · ⓑ · targets 를 만든다. 기본 상품 2건(둘 다 반영가능)."""
    run = tmp_path / "run"
    run.mkdir()
    a폴더 = tmp_path / "detail_1" / "before_detail"
    b폴더 = tmp_path / "market_1" / "before_market"
    p = 판()
    p.상품추가("zzmk-00000001", ai=True)                 # AI 플래그 참
    p.상품추가("zzmk-00000002")                           # 플래그 없음 + rc ≠ ⓐ → OR 규칙
    원본쓰기(a폴더, "zzmk-00000001", "ZZ-CODE-0001")
    원본쓰기(a폴더, "zzmk-00000002", "ZZ-CODE-0002")
    targets = tmp_path / "targets.json"

    def 대상(pids):
        targets.write_text(json.dumps({"items": [
            {"productId": pid, "판매자상품코드": f"ZZ-CODE-{pid[-4:]}"} for pid in pids]},
            ensure_ascii=False), encoding="utf-8")
        return targets

    대상(["zzmk-00000001", "zzmk-00000002"])
    return types.SimpleNamespace(run=run, a=a폴더, b=b폴더, 판=p, targets=targets,
                                 대상=대상, tmp=tmp_path,
                                 preview=tmp_path / "preview.json",
                                 summary=tmp_path / "summary.json")


def 미리보기_argv(e):
    return ["--run-dir", str(e.run), "--expect-nick", "부킹", "--preview",
            "--targets", str(e.targets), "--detail-backup-dir", str(e.a),
            "--backup-dir", str(e.b), "--summary-out", str(e.preview)]


def 반영_argv(e, max_items=5):
    a = ["--run-dir", str(e.run), "--expect-nick", "부킹", _반영플래그,
         "--targets", str(e.targets), "--detail-backup-dir", str(e.a),
         "--backup-dir", str(e.b), "--summary-out", str(e.summary),
         "--poll-interval", "20", "--max-poll-min", "5"]
    if max_items is not None:
        a += ["--max-items", str(max_items)]
    return a


def 마지막줄(capsys):
    줄들 = [x for x in capsys.readouterr().out.splitlines() if x.strip()]
    return 줄들[-1] if 줄들 else "", "\n".join(줄들)


# ════════════════════════════════════════════════════════════════════════════
# Task 1 — 미리보기 경로
# ════════════════════════════════════════════════════════════════════════════

def test_로더_가_venv_web_에서_뜬다(cli):
    assert callable(cli.main)
    assert cli.BulsajaMCP is _스텁MCP
    assert cli.MARKET == "SMARTSTORE"


def test_미리보기_confirm_true_0회(monkeypatch, cli, 환경, capsys):
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    코드 = 실행(monkeypatch, cli, 미리보기_argv(환경))
    assert 코드 == 0
    업 = mcp.이름들("bulsaja_market_update")
    assert len(업) == 2
    assert all(a["confirm"] is False for a in 업)
    assert all("confirmationToken" not in a for a in 업)
    assert all("marketGroupId" not in a for a in 업)
    문서 = json.loads(환경.preview.read_text(encoding="utf-8"))
    assert 문서["집계"]["반영가능"] == 2
    assert 문서["모드"] == "preview" and 문서["확인모드"] == "balanced"
    # 토큰은 저장하지 않는다 (T-06-12)
    assert "tok-" not in 환경.preview.read_text(encoding="utf-8")
    assert mcp.열림 == 1 and mcp.닫힘 == 1


def test_미리보기_토큰없는_성공은_P0(monkeypatch, cli, 환경, capsys):
    환경.판.업데이트_미리보기 = lambda a: {"success": True, "message": "수정 요청 완료"}
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    코드 = 실행(monkeypatch, cli, 미리보기_argv(환경))
    assert 코드 == 2
    assert len(mcp.이름들("bulsaja_market_update")) == 1      # 이후 상품 0회
    끝, 전체 = 마지막줄(capsys)
    assert "쓰기의심" in 전체
    assert 끝.startswith("###MARKET### ")


def test_미리보기_토큰없는_taskId도_P0(monkeypatch, cli, 환경, capsys):
    환경.판.업데이트_미리보기 = lambda a: {"success": False, "taskId": "49416999"}
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    assert 실행(monkeypatch, cli, 미리보기_argv(환경)) == 2
    assert len(mcp.이름들("bulsaja_market_update")) == 1


def test_미리보기_사후창_새행은_P0(monkeypatch, cli, 환경, capsys):
    """토큰은 줬는데 실제로는 작업창에 새 행이 생겼다 → 쓰기가 난 것이다."""
    p = 환경.판
    p.자동완료 = False

    def 몰래쓰기(a):
        p._새행(a["productIds"][0])
        return {"success": False, "confirmationToken": p._토큰(a["productIds"][0])}

    p.업데이트_미리보기 = 몰래쓰기
    mcp, _ = 주입(monkeypatch, cli, p.도구())
    코드 = 실행(monkeypatch, cli, 미리보기_argv(환경))
    assert 코드 == 2
    assert len(mcp.이름들("bulsaja_market_update")) == 1
    _, 전체 = 마지막줄(capsys)
    assert "쓰기의심" in 전체


def test_모드_fast_는_exit2(monkeypatch, cli, 환경, capsys):
    환경.판.모드 = "fast"
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    assert 실행(monkeypatch, cli, 미리보기_argv(환경)) == 2
    assert set(mcp.도구들()) == {"bulsaja_my_profile", "bulsaja_mcp_settings"}


def test_모드_못읽으면_exit2(monkeypatch, cli, 환경, capsys):
    p = 환경.판
    도구 = p.도구()
    도구["bulsaja_mcp_settings"] = lambda a: {"_text": "MCP error -32602"}
    mcp, _ = 주입(monkeypatch, cli, 도구)
    assert 실행(monkeypatch, cli, 미리보기_argv(환경)) == 2
    assert "bulsaja_market_update" not in mcp.도구들()


def test_계정_불일치_exit4(monkeypatch, cli, 환경, capsys):
    환경.판.닉 = "용팀장"
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    assert 실행(monkeypatch, cli, 미리보기_argv(환경)) == 4
    assert mcp.도구들() == ["bulsaja_my_profile"]


def test_스킵_미업로드(monkeypatch, cli, 환경, capsys):
    환경.판.상품["zzmk-00000001"]["summary"]["uploadedSuccessUrl"]["smartstore"] = ""
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    assert 실행(monkeypatch, cli, 미리보기_argv(환경)) == 0
    문서 = json.loads(환경.preview.read_text(encoding="utf-8"))
    첫 = 문서["items"][0]
    assert 첫["판정"] == "스킵" and 첫["사유"].startswith("미업로드")
    assert [a["productIds"] for a in mcp.이름들("bulsaja_market_update")] == [["zzmk-00000002"]]


def test_스킵_AI상세없음(monkeypatch, cli, 환경, capsys):
    """aiImageGenerated 없음 + 현재 renderContent == ⓐ → AI 가 안 붙었다."""
    환경.판.상품["zzmk-00000002"]["summary"]["uploadDetailContents"]["renderContent"] = 원본HTML
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    assert 실행(monkeypatch, cli, 미리보기_argv(환경)) == 0
    문서 = json.loads(환경.preview.read_text(encoding="utf-8"))
    둘 = 문서["items"][1]
    assert 둘["판정"] == "스킵" and 둘["사유"].startswith("AI상세없음")
    assert 문서["집계"] == {"반영가능": 1, "스킵": 1, "실패": 0, "전체": 2}


def test_AI판정_OR규칙(monkeypatch, cli, 환경, capsys):
    """플래그가 '0' 이어도 renderContent 가 ⓐ 와 다르면 반영가능 (Pitfall 6)."""
    환경.판.상품["zzmk-00000002"]["summary"]["uploadDetailContents"]["aiImageGenerated"] = "0"
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    assert 실행(monkeypatch, cli, 미리보기_argv(환경)) == 0
    문서 = json.loads(환경.preview.read_text(encoding="utf-8"))
    assert [x["판정"] for x in 문서["items"]] == ["반영가능", "반영가능"]


def test_AI판정_플래그참이면_rc같아도_반영가능(monkeypatch, cli, 환경, capsys):
    환경.판.상품["zzmk-00000001"]["summary"]["uploadDetailContents"]["renderContent"] = 원본HTML
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    assert 실행(monkeypatch, cli, 미리보기_argv(환경)) == 0
    문서 = json.loads(환경.preview.read_text(encoding="utf-8"))
    assert 문서["items"][0]["판정"] == "반영가능"


@pytest.mark.parametrize("망가뜨리기", ["부재", "깨짐", "rc없음"])
def test_백업_원본없으면_backup_failed(monkeypatch, cli, 환경, capsys, 망가뜨리기):
    경로 = 환경.a / "zzmk-00000001.json"
    if 망가뜨리기 == "부재":
        경로.unlink()
    elif 망가뜨리기 == "깨짐":
        경로.write_text("{깨진", encoding="utf-8")
    else:
        경로.write_text(json.dumps({"productId": "zzmk-00000001"}), encoding="utf-8")
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    assert 실행(monkeypatch, cli, 미리보기_argv(환경)) == 0
    문서 = json.loads(환경.preview.read_text(encoding="utf-8"))
    첫 = 문서["items"][0]
    assert 첫["판정"] == "스킵" and 첫["사유"].startswith("backup_failed")
    assert 첫["backup_a_있음"] is False
    assert ["zzmk-00000001"] not in [a["productIds"] for a in mcp.이름들("bulsaja_market_update")]


def test_백업_반영전_기록(monkeypatch, cli, 환경, capsys):
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    assert 실행(monkeypatch, cli, 미리보기_argv(환경)) == 0
    for pid in ("zzmk-00000001", "zzmk-00000002"):
        b = json.loads((환경.b / f"{pid}.json").read_text(encoding="utf-8"))
        assert {"productId", "판매자상품코드", "조회시각", "계정", "renderContent",
                "imageTranslated", "상단이미지", "하단이미지", "마켓그룹"} <= set(b)
        assert b["상단이미지"] == 상단 and b["마켓그룹"] == 1001135
        assert b["renderContent"] == AI_HTML and b["계정"] == "부킹"
    문서 = json.loads(환경.preview.read_text(encoding="utf-8"))
    첫 = 문서["items"][0]
    assert 첫["채널상품번호"] == "13192250286"
    assert 첫["상하단날짜"].startswith("2025-09-")
    assert 첫["backup_b"].endswith("zzmk-00000001.json")


def test_백업_반영전_쓰기실패면_backup_failed(monkeypatch, cli, 환경, capsys):
    환경.b.parent.mkdir(parents=True, exist_ok=True)
    환경.b.write_text("폴더 자리에 파일", encoding="utf-8")       # mkdir 실패 유도
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    assert 실행(monkeypatch, cli, 미리보기_argv(환경)) == 0
    문서 = json.loads(환경.preview.read_text(encoding="utf-8"))
    assert all(x["사유"].startswith("backup_failed") for x in 문서["items"])
    assert mcp.이름들("bulsaja_market_update") == []


def test_이미진행중_스킵(monkeypatch, cli, 환경, capsys):
    환경.판.업데이트_미리보기 = lambda a: {"success": False,
                                         "message": "이미 마켓 작업이 진행 중인 상품입니다"}
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    assert 실행(monkeypatch, cli, 미리보기_argv(환경)) == 0
    문서 = json.loads(환경.preview.read_text(encoding="utf-8"))
    assert [x["사유"][:5] for x in 문서["items"]] == ["이미진행중", "이미진행중"]
    assert 문서["집계"]["실패"] == 0


@pytest.mark.parametrize("망가뜨리기", ["빈items", "깨짐", "모드없음", "모드둘", "pid없음"])
def test_입력오류_exit2(monkeypatch, cli, 환경, capsys, 망가뜨리기):
    argv = 미리보기_argv(환경)
    if 망가뜨리기 == "빈items":
        환경.targets.write_text('{"items": []}', encoding="utf-8")
    elif 망가뜨리기 == "깨짐":
        환경.targets.write_text("{깨진", encoding="utf-8")
    elif 망가뜨리기 == "모드없음":
        argv.remove("--preview")
    elif 망가뜨리기 == "모드둘":
        argv.append("--poll-only")
    else:
        환경.targets.write_text('{"items": [{"판매자상품코드": "X"}]}', encoding="utf-8")
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    assert 실행(monkeypatch, cli, argv) == 2
    assert mcp.열림 == 0 and mcp.호출 == []


def test_입력오류_원본폴더_없으면_exit2(monkeypatch, cli, 환경, capsys):
    argv = 미리보기_argv(환경)
    i = argv.index("--detail-backup-dir")
    del argv[i:i + 2]
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    assert 실행(monkeypatch, cli, argv) == 2
    assert mcp.열림 == 0


def test_입력오류_market_인자_없음(monkeypatch, cli, 환경, capsys):
    """L-07 — 마켓은 SMARTSTORE 상수. --market 을 받지 않는다."""
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    assert 실행(monkeypatch, cli, 미리보기_argv(환경) + ["--market", "COUPANG"]) == 2
    assert mcp.열림 == 0


def test_센티널_마지막줄(monkeypatch, cli, 환경, capsys):
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    assert 실행(monkeypatch, cli, 미리보기_argv(환경)) == 0
    끝, _ = 마지막줄(capsys)
    assert 끝 == "###MARKET### 성공 2 / 실패 0 / 스킵 0 / 대기 0 / 전체 2"


def test_미리보기_표시규칙_저장안함(monkeypatch, cli, 환경, capsys):
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    assert 실행(monkeypatch, cli, 미리보기_argv(환경)) == 0
    assert "지시문" not in 환경.preview.read_text(encoding="utf-8")


# ════════════════════════════════════════════════════════════════════════════
# Task 2 — 반영(commit) + 이어서 확인(poll-only)
# ════════════════════════════════════════════════════════════════════════════

def 체크포인트(e):
    return json.loads((e.run / "market_status.json").read_text(encoding="utf-8"))


def test_max_items_없으면_exit2(monkeypatch, cli, 환경, capsys):
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    assert 실행(monkeypatch, cli, 반영_argv(환경, max_items=None)) == 2
    assert mcp.열림 == 0 and mcp.호출 == []


def test_max_items_0이면_exit2(monkeypatch, cli, 환경, capsys):
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    assert 실행(monkeypatch, cli, 반영_argv(환경, max_items=0)) == 2
    assert mcp.열림 == 0


def test_초과_exit5(monkeypatch, cli, 환경, capsys):
    환경.판.상품추가("zzmk-00000003", ai=True)
    원본쓰기(환경.a, "zzmk-00000003")
    환경.대상(["zzmk-00000001", "zzmk-00000002", "zzmk-00000003"])
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    assert 실행(monkeypatch, cli, 반영_argv(환경, max_items=1)) == 5
    assert mcp.이름들("bulsaja_market_update") == []
    assert mcp.이름들("bulsaja_product_workdata") == []
    끝, _ = 마지막줄(capsys)
    assert 끝.startswith("###MARKET### ")


def test_접수_2단_새토큰(monkeypatch, cli, 환경, capsys):
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    assert 실행(monkeypatch, cli, 반영_argv(환경)) == 0
    업 = mcp.이름들("bulsaja_market_update")
    assert [a["confirm"] for a in 업] == [False, True, False, True]
    assert all(len(a["productIds"]) == 1 for a in 업)
    토큰들 = [a["confirmationToken"] for a in 업 if a["confirm"]]
    assert len(set(토큰들)) == 2
    assert all(a["market"] == "SMARTSTORE" for a in 업)


def test_접수_taskId_선저장(monkeypatch, cli, 환경, capsys):
    """confirm:true 직후 폴링 전에 체크포인트에 taskId 가 있다 — 폴링이 터져도 남는다."""
    p = 환경.판
    원래 = p.upload_tasks
    본 = {"접수후": 0}

    def 폴링에서_터짐(a):
        if any(r["productId"].startswith("zzmk") for r in p.창):
            본["접수후"] += 1
            raise RuntimeError("폴링 중 네트워크 끊김")
        return 원래(a)

    도구 = p.도구()
    도구["bulsaja_upload_tasks"] = 폴링에서_터짐
    환경.대상(["zzmk-00000001"])
    mcp, _ = 주입(monkeypatch, cli, 도구)
    코드 = 실행(monkeypatch, cli, 반영_argv(환경))
    assert 코드 == 3                            # 폴링 미완 — 실패 아님
    체 = 체크포인트(환경)
    항목 = 체["items"]["zzmk-00000001"]
    assert 항목["taskId"] == "49416901"
    assert 항목["status"] == "대기"
    assert 체["워터마크"] == "49416818"
    assert 본["접수후"] >= 1


def test_접수_재실행_재접수0(monkeypatch, cli, 환경, capsys):
    환경.대상(["zzmk-00000001"])
    p = 환경.판
    p.자동완료 = False
    mcp, _ = 주입(monkeypatch, cli, p.도구())
    assert 실행(monkeypatch, cli, 반영_argv(환경)) == 3
    assert len(mcp.이름들("bulsaja_market_update")) == 2
    # 다시 반영 → 이미접수 · market_update 0회
    mcp2, _ = 주입(monkeypatch, cli, p.도구())
    assert 실행(monkeypatch, cli, 반영_argv(환경)) == 3
    assert mcp2.이름들("bulsaja_market_update") == []
    assert 체크포인트(환경)["items"]["zzmk-00000001"]["taskId"] == "49416901"


def test_접수_응답유실은_재접수하지_않는다(monkeypatch, cli, 환경, capsys):
    """confirm:true 가 예외 → 대기(taskId 없음) · 다음 실행도 재접수 0 · 창에서 워터마크로 찾는다."""
    p = 환경.판
    환경.대상(["zzmk-00000001"])

    def 유실(a):
        p._새행(a["productIds"][0])            # 서버엔 접수됐지만 응답이 안 왔다
        raise RuntimeError("read timeout")

    p.업데이트_확정 = 유실
    p.자동완료 = False
    mcp, _ = 주입(monkeypatch, cli, p.도구())
    assert 실행(monkeypatch, cli, 반영_argv(환경)) == 3
    항목 = 체크포인트(환경)["items"]["zzmk-00000001"]
    assert 항목["status"] == "대기"
    assert 항목["taskId"] == "49416901"         # 워터마크 대체 매칭으로 찾았다
    mcp2, _ = 주입(monkeypatch, cli, p.도구())
    실행(monkeypatch, cli, 반영_argv(환경))
    assert mcp2.이름들("bulsaja_market_update") == []


def test_접수_토큰없는_성공은_P0(monkeypatch, cli, 환경, capsys):
    환경.판.업데이트_미리보기 = lambda a: {"success": True}
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    assert 실행(monkeypatch, cli, 반영_argv(환경)) == 2
    업 = mcp.이름들("bulsaja_market_update")
    assert len(업) == 1 and 업[0]["confirm"] is False
    _, 전체 = 마지막줄(capsys)
    assert "쓰기의심" in 전체


@pytest.mark.parametrize("상황", ["미업로드", "AI상세없음", "원본없음"])
def test_접수_재조회_스킵(monkeypatch, cli, 환경, capsys, 상황):
    p = 환경.판
    if 상황 == "미업로드":
        p.상품["zzmk-00000002"]["summary"]["uploadedSuccessUrl"]["smartstore"] = None
    elif 상황 == "AI상세없음":
        p.상품["zzmk-00000002"]["summary"]["uploadDetailContents"]["renderContent"] = 원본HTML
    else:
        (환경.a / "zzmk-00000002.json").unlink()
    mcp, _ = 주입(monkeypatch, cli, p.도구())
    assert 실행(monkeypatch, cli, 반영_argv(환경)) == 0
    assert {a["productIds"][0] for a in mcp.이름들("bulsaja_market_update")} == {"zzmk-00000001"}
    항목 = 체크포인트(환경)["items"]["zzmk-00000002"]
    assert 항목["status"] == "스킵"
    기대 = {"미업로드": "미업로드", "AI상세없음": "AI상세없음", "원본없음": "backup_failed"}[상황]
    assert 항목["사유"].startswith(기대)


def test_폴링_taskId_매칭_성공(monkeypatch, cli, 환경, capsys):
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    assert 실행(monkeypatch, cli, 반영_argv(환경)) == 0
    체 = 체크포인트(환경)["items"]
    assert [체[p]["status"] for p in ("zzmk-00000001", "zzmk-00000002")] == ["성공", "성공"]
    assert all(체[p]["확정시각"] for p in 체)
    for 인자 in mcp.이름들("bulsaja_upload_tasks"):
        assert "taskIds" not in 인자


def test_폴링_실패사유(monkeypatch, cli, 환경, capsys):
    p = 환경.판
    p.완료상태 = "실패"
    p.실패사유 = "[스마트스토어] 판매 중지 상품"
    환경.대상(["zzmk-00000001"])
    mcp, _ = 주입(monkeypatch, cli, p.도구())
    assert 실행(monkeypatch, cli, 반영_argv(환경)) == 0
    항목 = 체크포인트(환경)["items"]["zzmk-00000001"]
    assert 항목["status"] == "실패" and "판매 중지" in 항목["사유"]


def test_폴링_DLQ창은_실패(monkeypatch, cli, 환경, capsys):
    p = 환경.판
    p.자동완료 = False
    환경.대상(["zzmk-00000001"])
    원래 = p.upload_tasks

    def dlq로(a):
        for r in list(p.창):
            if r["productId"] == "zzmk-00000001":
                p.창.remove(r)
                p.dlq.append(dict(r, 상태="재시도초과"))
        return 원래(a)

    도구 = p.도구()
    mcp, _ = 주입(monkeypatch, cli, 도구)
    # 접수 뒤 첫 폴링부터 DLQ 로 옮긴다
    p.업데이트_확정 = None
    기존확정 = p.market_update

    def 확정후dlq(a):
        r = 기존확정(a)
        if a.get("confirm"):
            도구["bulsaja_upload_tasks"] = dlq로
        return r

    도구["bulsaja_market_update"] = 확정후dlq
    assert 실행(monkeypatch, cli, 반영_argv(환경)) == 0
    assert 체크포인트(환경)["items"]["zzmk-00000001"]["status"] == "실패"


def test_폴링_워터마크_대체매칭(monkeypatch, cli, 환경, capsys):
    """confirm:true 응답에 taskId 가 없다 → 창에서 pid · 스마트스토어 · > 워터마크 · 삭제 아님."""
    p = 환경.판
    환경.대상(["zzmk-00000001"])
    p.창.insert(0, {"상태": "성공", "마켓": "스마트스토어", "작업": "삭제",
                   "productId": "zzmk-00000001", "taskId": "49416850"})   # 옛 행·삭제 — 무시

    def taskId없음(a):
        p._새행(a["productIds"][0])
        return {"success": True, "message": "요청 접수"}

    p.업데이트_확정 = taskId없음
    mcp, _ = 주입(monkeypatch, cli, p.도구())
    assert 실행(monkeypatch, cli, 반영_argv(환경)) == 0
    항목 = 체크포인트(환경)["items"]["zzmk-00000001"]
    assert 항목["taskId"] == "49416901" and 항목["status"] == "성공"


def test_폴링_대체매칭_삭제행은_제외(monkeypatch, cli, 환경, capsys):
    p = 환경.판
    p.자동완료 = False
    환경.대상(["zzmk-00000001"])

    def 삭제만(a):
        p._새행(a["productIds"][0], 작업="삭제")
        return {"success": True}

    p.업데이트_확정 = 삭제만
    mcp, _ = 주입(monkeypatch, cli, p.도구())
    assert 실행(monkeypatch, cli, 반영_argv(환경)) == 3
    assert 체크포인트(환경)["items"]["zzmk-00000001"]["taskId"] is None


def test_폴링_미발견은_대기_exit3(monkeypatch, cli, 환경, capsys):
    p = 환경.판
    p.자동완료 = False
    mcp, 시계 = 주입(monkeypatch, cli, p.도구())
    assert 실행(monkeypatch, cli, 반영_argv(환경)) == 3
    체 = 체크포인트(환경)["items"]
    assert {v["status"] for v in 체.values()} == {"대기"}
    assert 시계.지금 - 1_000_000.0 >= 5 * 60          # deadline 까지 기다렸다
    끝, _ = 마지막줄(capsys)
    assert 끝 == "###MARKET### 성공 0 / 실패 0 / 스킵 0 / 대기 2 / 전체 2"


def test_폴링_조회실패는_실패아님(monkeypatch, cli, 환경, capsys):
    p = 환경.판
    환경.대상(["zzmk-00000001"])
    원래 = p.upload_tasks
    상태 = {"접수됨": False}

    def 고장(a):
        if 상태["접수됨"]:
            return {"_text": "MCP error -32000: upstream"}
        return 원래(a)

    기존 = p.market_update

    def 표시(a):
        r = 기존(a)
        if a.get("confirm"):
            상태["접수됨"] = True
        return r

    도구 = p.도구()
    도구["bulsaja_upload_tasks"] = 고장
    도구["bulsaja_market_update"] = 표시
    mcp, _ = 주입(monkeypatch, cli, 도구)
    assert 실행(monkeypatch, cli, 반영_argv(환경)) == 3
    항목 = 체크포인트(환경)["items"]["zzmk-00000001"]
    assert 항목["status"] == "대기"
    _, 전체 = 마지막줄(capsys)
    assert "조회" in 전체


def test_이어서_poll_only(monkeypatch, cli, 환경, capsys):
    p = 환경.판
    p.자동완료 = False
    mcp, _ = 주입(monkeypatch, cli, p.도구())
    assert 실행(monkeypatch, cli, 반영_argv(환경)) == 3
    p.자동완료 = True
    mcp2, _ = 주입(monkeypatch, cli, p.도구())
    argv = ["--run-dir", str(환경.run), "--expect-nick", "부킹", "--poll-only",
            "--targets", str(환경.targets), "--summary-out", str(환경.summary),
            "--poll-interval", "20", "--max-poll-min", "5"]
    assert 실행(monkeypatch, cli, argv) == 0
    assert mcp2.이름들("bulsaja_market_update") == []
    assert mcp2.이름들("bulsaja_product_workdata") == []
    assert {v["status"] for v in 체크포인트(환경)["items"].values()} == {"성공"}


def test_이어서_poll_only_계정가드(monkeypatch, cli, 환경, capsys):
    환경.판.닉 = "다른사람"
    (환경.run / "market_status.json").write_text(json.dumps(
        {"워터마크": "49416818", "items": {"zzmk-00000001": {"status": "대기", "taskId": None}}}),
        encoding="utf-8")
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    argv = ["--run-dir", str(환경.run), "--expect-nick", "부킹", "--poll-only",
            "--targets", str(환경.targets)]
    assert 실행(monkeypatch, cli, argv) == 4
    assert mcp.도구들() == ["bulsaja_my_profile"]


def test_요약_파일_센티널(monkeypatch, cli, 환경, capsys):
    환경.판.상품["zzmk-00000002"]["summary"]["uploadedSuccessUrl"]["smartstore"] = ""
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    assert 실행(monkeypatch, cli, 반영_argv(환경, max_items=2)) == 0
    끝, _ = 마지막줄(capsys)
    assert 끝 == "###MARKET### 성공 1 / 실패 0 / 스킵 1 / 대기 0 / 전체 2"
    요약 = json.loads(환경.summary.read_text(encoding="utf-8"))
    assert 요약["모드"] == "commit" and 요약["max_items"] == 2 and 요약["계정"] == "부킹"
    assert 요약["집계"] == {"성공": 1, "실패": 0, "스킵": 1, "대기": 0, "전체": 2}
    assert [x["productId"] for x in 요약["items"]] == ["zzmk-00000001", "zzmk-00000002"]
    assert "tok-" not in 환경.summary.read_text(encoding="utf-8")
    assert "tok-" not in (환경.run / "market_status.json").read_text(encoding="utf-8")


def test_접수_게이트후_두번째_commit(monkeypatch, cli, 환경, capsys):
    """게이트 1건 commit(max 1) 뒤 같은 체크포인트로 나머지 commit — 이미 종결된 건 대상이 아니다."""
    환경.대상(["zzmk-00000001"])
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    assert 실행(monkeypatch, cli, 반영_argv(환경, max_items=1)) == 0
    환경.대상(["zzmk-00000001", "zzmk-00000002"])
    mcp2, _ = 주입(monkeypatch, cli, 환경.판.도구())
    assert 실행(monkeypatch, cli, 반영_argv(환경, max_items=1)) == 0
    assert {a["productIds"][0] for a in mcp2.이름들("bulsaja_market_update")} == {"zzmk-00000002"}
    assert 체크포인트(환경)["워터마크"] == "49416818"        # 첫 commit 값 유지


@pytest.mark.parametrize("상황", ["없음", "깨짐"])
def test_이어서_체크포인트_없거나_깨지면_exit2(monkeypatch, cli, 환경, capsys, 상황):
    if 상황 == "깨짐":
        (환경.run / "market_status.json").write_text("{깨진", encoding="utf-8")
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    argv = ["--run-dir", str(환경.run), "--expect-nick", "부킹", "--poll-only",
            "--targets", str(환경.targets)]
    assert 실행(monkeypatch, cli, argv) == 2
    assert mcp.열림 == 0


def test_접수_깨진_체크포인트면_exit2(monkeypatch, cli, 환경, capsys):
    """깨진 체크포인트를 빈 값으로 읽으면 taskId 가진 상품을 다시 접수한다 — 거부."""
    (환경.run / "market_status.json").write_text("{깨진", encoding="utf-8")
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    assert 실행(monkeypatch, cli, 반영_argv(환경)) == 2
    assert mcp.열림 == 0


# ════════════════════════════════════════════════════════════════════════════
# Task 3 — 복원(--restore-backup) + 작업창 스냅샷(--tasks-snapshot)
# ════════════════════════════════════════════════════════════════════════════

def 복원_argv(e, 모드="--preview", max_items=1):
    a = ["--run-dir", str(e.run), "--expect-nick", "부킹", 모드,
         "--restore-backup", str(e.a / "zzmk-00000001.json"),
         "--summary-out", str(e.summary), "--poll-interval", "20", "--max-poll-min", "5"]
    if 모드 == _반영플래그:
        a += ["--backup-dir", str(e.b)]
        if max_items is not None:
            a += ["--max-items", str(max_items)]
    return a


def test_복원_미리보기_confirm_true_0회(monkeypatch, cli, 환경, capsys):
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    assert 실행(monkeypatch, cli, 복원_argv(환경)) == 0
    적용 = mcp.이름들("bulsaja_detail_apply")
    assert len(적용) == 1 and 적용[0]["confirm"] is False
    assert "confirmationToken" not in 적용[0]
    assert 적용[0]["html"] == 원본HTML and 적용[0]["imageReplacements"] == []
    assert mcp.이름들("bulsaja_market_update") == []
    전 = json.loads((환경.run / "before_restore_zzmk-00000001.json").read_text(encoding="utf-8"))
    assert 전["renderContent"] == AI_HTML
    assert {"productId", "판매자상품코드", "조회시각", "계정", "renderContent",
            "imageTranslated"} <= set(전)
    문서 = json.loads((환경.run / "restore_preview.json").read_text(encoding="utf-8"))
    assert 문서["토큰받음"] is True and 문서["전후동일"] is True
    assert 문서["productId"] == "zzmk-00000001"
    assert "tok-" not in (환경.run / "restore_preview.json").read_text(encoding="utf-8")
    끝, _ = 마지막줄(capsys)
    assert 끝.startswith("###MARKET### 성공 1 ")


def test_복원_미리보기_renderContent_변하면_P0(monkeypatch, cli, 환경, capsys):
    p = 환경.판

    def 몰래적용(a):
        p.상품[a["productId"]]["summary"]["uploadDetailContents"]["renderContent"] = a["html"]
        return {"success": False, "confirmationToken": p._토큰(a["productId"])}

    p.적용_미리보기 = 몰래적용
    mcp, _ = 주입(monkeypatch, cli, p.도구())
    assert 실행(monkeypatch, cli, 복원_argv(환경)) == 2
    _, 전체 = 마지막줄(capsys)
    assert "쓰기의심" in 전체
    assert mcp.이름들("bulsaja_market_update") == []


def test_복원_미리보기_토큰없는_성공은_P0(monkeypatch, cli, 환경, capsys):
    환경.판.적용_미리보기 = lambda a: {"success": True}
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    assert 실행(monkeypatch, cli, 복원_argv(환경)) == 2
    _, 전체 = 마지막줄(capsys)
    assert "쓰기의심" in 전체


def test_복원_미리보기_전상태_못쓰면_호출0(monkeypatch, cli, 환경, capsys):
    (환경.run / "before_restore_zzmk-00000001.json").mkdir()      # 파일 자리에 폴더
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    assert 실행(monkeypatch, cli, 복원_argv(환경)) == 2
    assert mcp.이름들("bulsaja_detail_apply") == []


def test_복원_실행(monkeypatch, cli, 환경, capsys):
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    assert 실행(monkeypatch, cli, 복원_argv(환경, _반영플래그)) == 0
    적용 = mcp.이름들("bulsaja_detail_apply")
    assert [a["confirm"] for a in 적용] == [False, True]
    assert 적용[1]["confirmationToken"].startswith("tok-zzmk-00000001")
    assert 환경.판.상품["zzmk-00000001"]["summary"]["uploadDetailContents"]["renderContent"] \
        == 원본HTML
    업 = mcp.이름들("bulsaja_market_update")
    assert [a["confirm"] for a in 업] == [False, True]
    # 순서 — detail_apply 확정 → (재조회) → market_update
    이름 = mcp.도구들()
    assert 이름.index("bulsaja_market_update") > max(
        i for i, n in enumerate(이름) if n == "bulsaja_detail_apply")
    b = json.loads((환경.b / "zzmk-00000001.json").read_text(encoding="utf-8"))
    assert b["renderContent"] == 원본HTML
    체 = json.loads((환경.run / "market_status.json").read_text(encoding="utf-8"))
    assert 체["items"]["zzmk-00000001"]["status"] == "성공"
    요약 = json.loads(환경.summary.read_text(encoding="utf-8"))
    assert 요약["모드"] == "restore"
    assert "복원후_aiImageGenerated" in 요약 and 요약["복원후_aiImageGenerated"] is True
    assert "--force" in 요약["비고"]


def test_복원_실행_재조회불일치는_마켓반영0(monkeypatch, cli, 환경, capsys):
    환경.판.적용_반영안됨 = True
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    assert 실행(monkeypatch, cli, 복원_argv(환경, _반영플래그)) == 2
    assert mcp.이름들("bulsaja_market_update") == []


def test_복원_실행_미업로드면_반영0(monkeypatch, cli, 환경, capsys):
    환경.판.상품["zzmk-00000001"]["summary"]["uploadedSuccessUrl"]["smartstore"] = ""
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    실행(monkeypatch, cli, 복원_argv(환경, _반영플래그))
    assert mcp.이름들("bulsaja_detail_apply") == []
    assert mcp.이름들("bulsaja_market_update") == []


def test_복원_max_items_없으면_exit2(monkeypatch, cli, 환경, capsys):
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    assert 실행(monkeypatch, cli, 복원_argv(환경, _반영플래그, max_items=None)) == 2
    assert mcp.열림 == 0


@pytest.mark.parametrize("망가뜨리기", ["부재", "깨짐", "rc없음"])
def test_복원_원본파일_이상이면_exit2(monkeypatch, cli, 환경, capsys, 망가뜨리기):
    경로 = 환경.a / "zzmk-00000001.json"
    if 망가뜨리기 == "부재":
        경로.unlink()
    elif 망가뜨리기 == "깨짐":
        경로.write_text("{깨진", encoding="utf-8")
    else:
        경로.write_text(json.dumps({"productId": "zzmk-00000001"}), encoding="utf-8")
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    assert 실행(monkeypatch, cli, 복원_argv(환경)) == 2
    assert mcp.열림 == 0


def test_복원은_poll_only와_못쓴다(monkeypatch, cli, 환경, capsys):
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    argv = ["--run-dir", str(환경.run), "--expect-nick", "부킹", "--poll-only",
            "--restore-backup", str(환경.a / "zzmk-00000001.json")]
    assert 실행(monkeypatch, cli, argv) == 2
    assert mcp.열림 == 0


def test_스냅샷_읽기전용(monkeypatch, cli, 환경, capsys):
    out = 환경.tmp / "snap.json"
    mcp, _ = 주입(monkeypatch, cli, 환경.판.도구())
    argv = ["--run-dir", str(환경.run), "--expect-nick", "부킹", "--tasks-snapshot", str(out)]
    assert 실행(monkeypatch, cli, argv) == 0
    assert set(mcp.도구들()) == {"bulsaja_my_profile", "bulsaja_mcp_settings",
                                 "bulsaja_upload_tasks", "bulsaja_work_progress"}
    s = json.loads(out.read_text(encoding="utf-8"))
    assert s["계정"] == "부킹" and s["확인모드"] == "balanced"
    assert s["최대taskId"] == "49416818"
    assert s["PENDING행수"] == 0 and s["PROCESSING행수"] == 0
    assert s["기본창행수"] == 30
    assert "work_progress_마켓작업" in s
    assert "지시문" not in out.read_text(encoding="utf-8")


def test_스냅샷_조회실패는_exit2(monkeypatch, cli, 환경, capsys):
    도구 = 환경.판.도구()
    도구["bulsaja_upload_tasks"] = lambda a: {"_text": "MCP error"}
    out = 환경.tmp / "snap.json"
    mcp, _ = 주입(monkeypatch, cli, 도구)
    argv = ["--run-dir", str(환경.run), "--expect-nick", "부킹", "--tasks-snapshot", str(out)]
    assert 실행(monkeypatch, cli, argv) == 2
    assert not out.exists()
