#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`run_coupang.py` 주입구 · `coupang_web.py` 러너 오프라인 테스트 (07-03).

## 여기서 지키는 것은 **되돌릴 수 없는 쿠팡 복사다**

`bulsaja_market_group_copy` 는 중복 방지 옵션이 없다. 이 파일은 불사자 MCP 를 **한 번도**
부르지 않는다 — `BulsajaMCP` transport 의 open/close/call_tool 을 호출만 기록하는
`가짜불사자` 로 갈아끼우고, `snapshot.ensure` 도 가짜로 바꾼다(스냅샷 캐시 쓰기 0).
시나리오에 없는 도구가 불리면 바로 실패한다 — 예상 밖 쓰기 호출을 흘려보내지 않는다.

## 골든 (L-02)

`fixtures/coupang_golden_noflag.json` 은 **CLI 를 한 줄도 고치기 전** 커밋에서 만들었다.
무플래그 gate 의 candidates.json·rejected.json 바이트, 무플래그 apply(미리보기) stdout 이
그 파일과 다르면 스킬 문서대로 터미널에서 돌리는 기존 사용자의 동작이 바뀐 것이다.
gate stdout 은 옛 줄이 새 출력 안에 **순서대로** 다 있으면 통과다(D-17 이 진단 줄을 더한다).
다시 만들 때만 `COUPANG_GOLDEN_WRITE=1` — 평소엔 비교만 한다.

기준값은 테스트가 cfg 로 **명시 주입**한다(min_margin 15.0) — workspace.toml 이 바뀌어도
골든이 흔들리지 않게.

    .venv/bin/python3 -m pytest -q .claude/skills/coupang-candidates/scripts/test_coupang_web.py
"""
import copy
import importlib.util
import json
import os
import sys
import types
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent
RUN_COUPANG = SCRIPTS / "run_coupang.py"
FIXTURES = SCRIPTS / "fixtures"
골든경로 = FIXTURES / "coupang_golden_noflag.json"
GID = 1003308


# ── 로더 · 가짜 불사자 · 가짜 설정 ─────────────────────────────────────────

@pytest.fixture
def cli():
    """`run_coupang.py` 를 파일 경로에서 로드한다. 최상위 sys.path 삽입은 끝나면 원복."""
    이전경로 = list(sys.path)
    try:
        규격 = importlib.util.spec_from_file_location("_run_coupang_under_test", RUN_COUPANG)
        모듈 = importlib.util.module_from_spec(규격)
        규격.loader.exec_module(모듈)
        yield 모듈
    finally:
        sys.path[:] = 이전경로


class 가짜불사자:
    """transport 자리에 들어가는 호출 기록기.

    - 그룹 상품 목록은 `그룹` 을 pageSize 로 잘라 준다. `총상품수` 는 따로 줄 수 있다
      (조기 종료 시나리오 — 빈 페이지로 덜 읽힌 채 끝나는 경우).
    - `스냅샷` = {pid: {타오바오상품번호, 불사자코드}} · `스냅샷실패` = 오류로 돌려줄 pid 집합
    """

    def __init__(self, 그룹=(), 스냅샷=None, 닉="용팀장", 총상품수=None, 끊김=None):
        self.그룹 = list(그룹)
        self.스냅샷 = dict(스냅샷 or {})
        self.스냅샷실패 = set()
        self.닉 = 닉
        self.총상품수 = 총상품수
        self.끊김 = 끊김          # 이 페이지부터 빈 항목(조기 종료 재현)
        self.호출 = []
        self.열림 = 0
        self.닫힘 = 0
        self.복사 = []

    def call_tool(self, name, args):
        self.호출.append((name, copy.deepcopy(args)))
        if name == "bulsaja_my_profile":
            if self.닉 is None:
                raise RuntimeError("프로필 조회 실패")
            return {"닉네임": self.닉}
        if name == "bulsaja_market_group_products":
            size, page = int(args["pageSize"]), int(args["page"])
            if self.끊김 and page >= self.끊김:
                items = []
            else:
                items = self.그룹[(page - 1) * size: page * size]
            total = len(self.그룹) if self.총상품수 is None else self.총상품수
            return {"항목": copy.deepcopy(items), "더있음": page * size < len(self.그룹),
                    "총상품수": total}
        raise AssertionError(f"시나리오에 없는 도구 호출: {name}")

    def 이름들(self):
        return [n for n, _ in self.호출]


def 주입(monkeypatch, cli, 불사자, 설정=None):
    """transport · snapshot.ensure · cfg 를 가짜로 바꾼다."""
    base = next(c for c in cli.CoupangMCP.__mro__ if c.__name__ == "BulsajaMCP")

    def _init(self, *a, **k):
        self.session_id = None

    def _open(self):
        불사자.열림 += 1

    def _close(self):
        불사자.닫힘 += 1

    def _call(self, name, args):
        return 불사자.call_tool(name, args)

    monkeypatch.setattr(base, "__init__", _init)
    monkeypatch.setattr(base, "open", _open)
    monkeypatch.setattr(base, "close", _close)
    monkeypatch.setattr(base, "call_tool", _call)

    def _ensure(pids, mcp=None, log=None, **k):
        recs, errs = {}, {}
        for p in pids:
            if p in 불사자.스냅샷실패:
                errs[p] = "RuntimeError: 429"
            elif p in 불사자.스냅샷:
                recs[p] = dict(불사자.스냅샷[p])
        return recs, errs

    monkeypatch.setattr(cli, "snapshot", types.SimpleNamespace(ensure=_ensure))
    값 = {"coupang.group_id": GID, "coupang.min_margin": 15.0, "coupang.min_orders": 3}
    값.update(설정 or {})

    def _cfg(dotted, default=None, required=False):
        v = 값.get(dotted)
        if v is None:
            if required:
                raise KeyError(dotted)
            return default
        return v

    monkeypatch.setattr(cli, "cfg", _cfg)
    return 불사자


def 실행(monkeypatch, cli, argv):
    """`main()` 을 argv 로 돌려 종료코드를 돌려준다 (정상 반환 = 0)."""
    monkeypatch.setattr(sys, "argv", ["run_coupang.py", *argv])
    try:
        return cli.main() or 0
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1


# ── 합성 run-dir (대표 6개) ──────────────────────────────────────────────
#
#   A 통과(보정 24.7)     B 통과(보정 18.7 — 20% 기준이면 탈락)   C 주문수부족
#   D 마진미달           E 쿠팡그룹에이미있음(타오바오번호 일치)      F 마진미상
#   카테고리 가구/인테리어 → 쿠팡수수료 10.8 · 스마트스토어 평균 5.5 → 보정 = 가중 − 5.3

CAT = "가구/인테리어>거실가구>테이블>사이드테이블"
_대표 = [
    # 키, 주문, 가중마진, 유효행수, 타오바오
    ("A", 5, 30.0, 5, "tbA"),
    ("B", 4, 24.0, 4, "tbB"),
    ("C", 2, 40.0, 2, "tbC"),
    ("D", 6, 18.0, 6, "tbD"),
    ("E", 7, 35.0, 7, "tbE"),
    ("F", 3, None, 0, "tbF"),
]


def 대표pid(k):
    return f"U0{k}rep"


def 판매코드(k):
    return f"S{k}code"


def 불사자코드(k):
    return f"B{k}code"


def 런디렉터리_만들기(root):
    reps, sales, diffs = {}, {"실적": {}}, {}
    for k, n, m, valid, tb in _대표:
        reps[불사자코드(k)] = {
            "불사자코드": 불사자코드(k), "대표pid": 대표pid(k), "판매자상품코드": 판매코드(k),
            "상품명": f"상품{k} 합성 테이블", "그룹명": "구매_가공완료", "잠금": True,
            "상태": "업로드 완료", "판매가": "40,400원~", "사본수": 1,
            "사본pid": [대표pid(k)], "합산주문수": n, "합산매출": 100000.0 * n,
        }
        sales["실적"][판매코드(k)] = {
            "판매자상품코드": 판매코드(k), "주문수": n, "유효행수": valid,
            "가중마진": m, "최소마진": m, "적자건수": 0,
            "평균수수료율": 5.5 if m is not None else None,
            "배송비P75": 7000, "배송비편차": 10.0,
        }
        diffs[대표pid(k)] = {"교정필요": False, "방향": "", "차액": 0, "대표pid": 대표pid(k),
                            "카테고리": CAT, "타오바오상품번호": tb}
    os.makedirs(root, exist_ok=True)
    for name, obj in (("reps.json", reps), ("sales.json", sales), ("ship_diff.json", diffs)):
        with open(os.path.join(root, name), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
    return root


def 기본불사자(**k):
    """쿠팡 그룹에 기존 2건 — E 의 복사본(타오바오 일치) · 무관한 상품 1건."""
    그룹 = [{"productId": "Gcopy_E", "상품명": "상품E 복사본", "판매가": 40400},
          {"productId": "Gother", "상품명": "무관", "판매가": 10000}]
    스냅샷 = {"Gcopy_E": {"타오바오상품번호": "tbE", "불사자코드": 불사자코드("E")},
            "Gother": {"타오바오상품번호": "tbZ", "불사자코드": "BZcode"}}
    return 가짜불사자(그룹=그룹, 스냅샷=스냅샷, **k)


def _읽기(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _골든_돌리기(monkeypatch, cli, tmp_path, capsys):
    R = 런디렉터리_만들기(str(tmp_path / "run"))
    불사자 = 주입(monkeypatch, cli, 기본불사자())
    capsys.readouterr()
    code = 실행(monkeypatch, cli, ["gate", "--run-dir", R])
    gate_out = capsys.readouterr().out
    gate = {"exit": code,
            "candidates": _읽기(os.path.join(R, "candidates.json")),
            "rejected": _읽기(os.path.join(R, "rejected.json")),
            "stdout": gate_out.splitlines(),
            "calls": [[n, a] for n, a in 불사자.호출]}
    불사자.호출.clear()
    code = 실행(monkeypatch, cli, ["apply", "--run-dir", R])
    apply_out = capsys.readouterr().out
    apply = {"exit": code, "stdout": apply_out.splitlines(),
             "calls": [[n, a] for n, a in 불사자.호출]}
    return {"gate": gate, "apply_preview": apply}


def _부분열(옛, 새):
    """옛 줄이 새 줄 안에 순서대로 모두 있는가."""
    it = iter(새)
    return all(any(x == y for y in it) for x in 옛)


# ── Task 1: 무플래그 골든 ────────────────────────────────────────────────

def test_플래그없음_골든_불변(monkeypatch, cli, tmp_path, capsys):
    실제 = _골든_돌리기(monkeypatch, cli, tmp_path, capsys)
    if os.environ.get("COUPANG_GOLDEN_WRITE") == "1":
        FIXTURES.mkdir(exist_ok=True)
        골든경로.write_text(json.dumps(실제, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")
    assert 골든경로.exists(), "골든 없음 — COUPANG_GOLDEN_WRITE=1 로 수정 전 CLI 에서 만든다"
    골든 = json.loads(골든경로.read_text(encoding="utf-8"))
    g, a = 골든["gate"], 골든["apply_preview"]
    assert 실제["gate"]["exit"] == g["exit"] == 0
    assert 실제["gate"]["candidates"] == g["candidates"], "candidates.json 바이트가 바뀌었다"
    assert 실제["gate"]["rejected"] == g["rejected"], "rejected.json 바이트가 바뀌었다"
    assert _부분열(g["stdout"], 실제["gate"]["stdout"]), "gate 옛 출력 줄이 사라졌다"
    assert 실제["gate"]["calls"] == g["calls"], "gate 의 불사자 호출이 바뀌었다"
    assert 실제["apply_preview"] == a, "apply 미리보기가 바뀌었다"


def test_골든_시나리오가_갈래를_모두_탄다():
    골든 = json.loads(골든경로.read_text(encoding="utf-8"))
    통과 = [r["대표pid"] for r in json.loads(골든["gate"]["candidates"])]
    사유 = {r["대표pid"]: r["사유"].split("(")[0]
          for r in json.loads(골든["gate"]["rejected"])}
    assert 통과 == [대표pid("A"), 대표pid("B")]
    assert 사유 == {대표pid("C"): "주문수부족", 대표pid("D"): "마진미달",
                  대표pid("E"): "쿠팡그룹에이미있음", 대표pid("F"): "마진미상"}
    assert "[gate] 기준: 주문 3회 이상 AND 쿠팡보정마진 15.0% 이상" in 골든["gate"]["stdout"]
    # 미리보기는 불사자를 열지 않는다
    assert 골든["apply_preview"]["calls"] == []


# ── Task 2: D-17 gate fail-closed ───────────────────────────────────────

def _후보(R):
    return [r["대표pid"] for r in json.loads(_읽기(os.path.join(R, "candidates.json")))]


def _탈락사유(R):
    return {r["대표pid"]: r["사유"] for r in json.loads(_읽기(os.path.join(R, "rejected.json")))}


def test_gate_스냅샷_실패면_후보파일을_안_쓰고_exit3(monkeypatch, cli, tmp_path, capsys):
    R = 런디렉터리_만들기(str(tmp_path / "run"))
    # 지난 회차 파일이 남아 있어도 손대지 않는다
    for n in ("candidates.json", "rejected.json"):
        with open(os.path.join(R, n), "w", encoding="utf-8") as f:
            f.write("옛파일")
    불사자 = 기본불사자()
    불사자.스냅샷실패 = {"Gcopy_E"}
    주입(monkeypatch, cli, 불사자)
    code = 실행(monkeypatch, cli, ["gate", "--run-dir", R])
    out = capsys.readouterr().out
    assert code == 3
    assert "부분 대조 금지" in out
    assert _읽기(os.path.join(R, "candidates.json")) == "옛파일"
    assert _읽기(os.path.join(R, "rejected.json")) == "옛파일"


def test_gate_스냅샷_실패면_새_run_dir_에_후보파일이_생기지_않는다(monkeypatch, cli, tmp_path):
    R = 런디렉터리_만들기(str(tmp_path / "run"))
    불사자 = 기본불사자()
    불사자.스냅샷실패 = {"Gother"}
    주입(monkeypatch, cli, 불사자)
    assert 실행(monkeypatch, cli, ["gate", "--run-dir", R]) == 3
    assert not os.path.exists(os.path.join(R, "candidates.json"))
    assert not os.path.exists(os.path.join(R, "rejected.json"))


def test_gate_그룹목록이_총상품수보다_적으면_실패(monkeypatch, cli, tmp_path, capsys):
    R = 런디렉터리_만들기(str(tmp_path / "run"))
    불사자 = 기본불사자(총상품수=5)      # 서버는 5건이라는데 2건만 받고 끝났다
    주입(monkeypatch, cli, 불사자)
    code = 실행(monkeypatch, cli, ["gate", "--run-dir", R])
    assert code != 0
    assert not os.path.exists(os.path.join(R, "candidates.json"))
    assert "덜 읽힘" in capsys.readouterr().out


def test_gate_빈_페이지로_조기종료해도_실패(monkeypatch, cli, tmp_path):
    R = 런디렉터리_만들기(str(tmp_path / "run"))
    그룹 = [{"productId": f"G{i:03d}", "상품명": "x"} for i in range(60)]
    불사자 = 가짜불사자(그룹=그룹, 끊김=2,
                    스냅샷={g["productId"]: {"타오바오상품번호": f"t{i}", "불사자코드": ""}
                         for i, g in enumerate(그룹)})
    주입(monkeypatch, cli, 불사자)
    assert 실행(monkeypatch, cli, ["gate", "--run-dir", R]) != 0
    assert not os.path.exists(os.path.join(R, "candidates.json"))


def test_gate_타오바오_결측이면_불사자코드로_대조(monkeypatch, cli, tmp_path, capsys):
    R = 런디렉터리_만들기(str(tmp_path / "run"))
    불사자 = 기본불사자()
    불사자.그룹.append({"productId": "Gcopy_A", "상품명": "상품A 복사본"})
    불사자.스냅샷["Gcopy_A"] = {"타오바오상품번호": "", "불사자코드": 불사자코드("A")}
    주입(monkeypatch, cli, 불사자)
    assert 실행(monkeypatch, cli, ["gate", "--run-dir", R]) == 0
    out = capsys.readouterr().out
    assert _후보(R) == [대표pid("B")]
    assert _탈락사유(R)[대표pid("A")] == "쿠팡그룹에이미있음"
    assert "타오바오번호 결측 1건" in out
    assert "[gate] 그룹읽기 총상품수 3 · 읽음 3 · 타오바오결측 1" in out


def test_gate_skip_group_check_경로는_불변(monkeypatch, cli, tmp_path):
    R = 런디렉터리_만들기(str(tmp_path / "run"))
    불사자 = 기본불사자()
    주입(monkeypatch, cli, 불사자)
    assert 실행(monkeypatch, cli, ["gate", "--run-dir", R, "--skip-group-check"]) == 0
    assert 불사자.호출 == []
    assert _후보(R) == [대표pid("E"), 대표pid("A"), 대표pid("B")]


def test_gate_기준은_cfg_를_따른다(monkeypatch, cli, tmp_path, capsys):
    """CP-03 — 기준 인자를 안 넘기면 설정값(20.0)으로 돈다. B(보정 18.7)가 떨어진다."""
    R = 런디렉터리_만들기(str(tmp_path / "run"))
    주입(monkeypatch, cli, 기본불사자(), 설정={"coupang.min_margin": 20.0})
    assert 실행(monkeypatch, cli, ["gate", "--run-dir", R]) == 0
    assert "[gate] 기준: 주문 3회 이상 AND 쿠팡보정마진 20.0% 이상" in capsys.readouterr().out
    assert _후보(R) == [대표pid("A")]
    assert _탈락사유(R)[대표pid("B")].startswith("마진미달")


# ── Task 2: --expect-nick (D-14) ────────────────────────────────────────

def _전단계_준비(R):
    """resolve·ship·gate·apply(커밋)·verify 가 모두 MCP 를 여는 지점까지 가게 한다."""
    런디렉터리_만들기(R)
    with open(os.path.join(R, "candidates.json"), "w", encoding="utf-8") as f:
        json.dump([{"대표pid": "U0Arep", "판매자상품코드": "SAcode", "불사자코드": "BAcode",
                    "상품명": "상품A", "합산주문수": 5, "쿠팡보정마진": 24.7}], f)
    with open(os.path.join(R, "copied.jsonl"), "w", encoding="utf-8") as f:
        f.write(json.dumps({"원본pid": "U0Xrep", "신pid": "Gx"}) + "\n")


COMMIT = "--" + "commit"


@pytest.mark.parametrize("stage,extra", [
    ("resolve", []), ("ship", []), ("gate", []), ("apply", [COMMIT]), ("verify", []),
])
def test_expect_nick_불일치면_exit4_프로필외_호출0(monkeypatch, cli, tmp_path, capsys,
                                           stage, extra):
    R = str(tmp_path / "run")
    _전단계_준비(R)
    불사자 = 주입(monkeypatch, cli, 기본불사자(닉="다른계정"))
    code = 실행(monkeypatch, cli, [stage, "--run-dir", R, *extra, "--expect-nick", "용팀장"])
    assert code == 4
    assert 불사자.이름들() == ["bulsaja_my_profile"]
    assert "[계정] 기대 용팀장 · 실제 다른계정" in capsys.readouterr().err


def test_expect_nick_조회실패도_exit4(monkeypatch, cli, tmp_path):
    R = 런디렉터리_만들기(str(tmp_path / "run"))
    불사자 = 주입(monkeypatch, cli, 기본불사자(닉=None))
    assert 실행(monkeypatch, cli, ["gate", "--run-dir", R, "--expect-nick", "용팀장"]) == 4
    assert 불사자.이름들() == ["bulsaja_my_profile"]


def test_expect_nick_일치면_그대로_진행(monkeypatch, cli, tmp_path):
    R = 런디렉터리_만들기(str(tmp_path / "run"))
    불사자 = 주입(monkeypatch, cli, 기본불사자())
    assert 실행(monkeypatch, cli, ["gate", "--run-dir", R, "--expect-nick", "용팀장"]) == 0
    assert 불사자.이름들()[0] == "bulsaja_my_profile"
    assert _후보(R) == [대표pid("A"), 대표pid("B")]


def test_expect_nick_무플래그면_프로필_조회_안함(monkeypatch, cli, tmp_path):
    R = 런디렉터리_만들기(str(tmp_path / "run"))
    불사자 = 주입(monkeypatch, cli, 기본불사자())
    assert 실행(monkeypatch, cli, ["gate", "--run-dir", R]) == 0
    assert "bulsaja_my_profile" not in 불사자.이름들()


# ── Task 2: apply --pids-file (D-12) ────────────────────────────────────

def _gate_끝낸_런(monkeypatch, cli, tmp_path):
    R = 런디렉터리_만들기(str(tmp_path / "run"))
    불사자 = 주입(monkeypatch, cli, 기본불사자())
    assert 실행(monkeypatch, cli, ["gate", "--run-dir", R]) == 0
    불사자.호출.clear()
    return R, 불사자


def _승인파일(R, 내용):
    p = os.path.join(R, "approved_pids.json")
    with open(p, "w", encoding="utf-8") as f:
        f.write(내용 if isinstance(내용, str) else json.dumps(내용))
    return p


def test_apply_pids_file_승인분만_대상(monkeypatch, cli, tmp_path, capsys):
    R, 불사자 = _gate_끝낸_런(monkeypatch, cli, tmp_path)
    capsys.readouterr()
    p = _승인파일(R, [대표pid("A")])
    assert 실행(monkeypatch, cli, ["apply", "--run-dir", R, "--pids-file", p]) == 0
    out = capsys.readouterr().out
    assert "[apply] 대상 1건" in out
    assert 판매코드("A") in out and 판매코드("B") not in out


def test_apply_pids_file_후보에_없는_승인은_보고(monkeypatch, cli, tmp_path, capsys):
    R, _ = _gate_끝낸_런(monkeypatch, cli, tmp_path)
    capsys.readouterr()
    p = _승인파일(R, ["Zgone"])
    assert 실행(monkeypatch, cli, ["apply", "--run-dir", R, "--pids-file", p]) == 0
    out = capsys.readouterr().out
    assert "승인됐지만 재조회 후보에 없음: Zgone" in out
    assert "[apply] 대상 0건" in out


@pytest.mark.parametrize("내용", ["{깨짐", '{"a": 1}', '"U0Arep"', None])
def test_apply_pids_file_깨지면_exit2_전량폴백없음(monkeypatch, cli, tmp_path, capsys, 내용):
    R, 불사자 = _gate_끝낸_런(monkeypatch, cli, tmp_path)
    p = os.path.join(R, "없는파일.json") if 내용 is None else _승인파일(R, 내용)
    code = 실행(monkeypatch, cli, ["apply", "--run-dir", R, COMMIT, "--pids-file", p])
    assert code == 2
    assert 불사자.호출 == []
    assert "전량 복사로 넘어가지 않는다" in capsys.readouterr().err


def test_apply_pids_file_과_limit_순서(monkeypatch, cli, tmp_path, capsys):
    """승인 필터가 limit 보다 먼저 — 승인 B 만 있으면 limit 1 은 B 를 집는다."""
    R, _ = _gate_끝낸_런(monkeypatch, cli, tmp_path)
    capsys.readouterr()
    p = _승인파일(R, [대표pid("B")])
    assert 실행(monkeypatch, cli, ["apply", "--run-dir", R, "--pids-file", p,
                                "--limit", "1"]) == 0
    out = capsys.readouterr().out
    assert "[apply] 대상 1건" in out and 판매코드("B") in out


def test_verify_스냅샷_실패면_중복0_을_증명하지_않는다(monkeypatch, cli, tmp_path):
    R = str(tmp_path / "run")
    _전단계_준비(R)
    불사자 = 기본불사자()
    불사자.스냅샷실패 = {"Gother"}
    주입(monkeypatch, cli, 불사자)
    실행(monkeypatch, cli, ["verify", "--run-dir", R])
    assert json.loads(_읽기(os.path.join(R, "verified.json")))["중복0"] is False
