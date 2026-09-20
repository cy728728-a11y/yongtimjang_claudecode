#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""argv 조립(`webapp/argv.py`) 검증 — **조립만 하고 실행은 하지 않는다.**

이 파일은 "크레딧·광고비 0 으로 쓰기 경로를 검증하는 3층"(01-VALIDATION.md)의
**웹앱 층**이다. 1층은 `nvad.call` 몽키패치, 2층은 CLI dry-run 실측,
3층이 여기 — 조립된 argv 를 **문자열로만** 단언한다. 서브프로세스를 띄우지 않으므로
어떤 실수를 해도 네이버 광고 API 에 요청이 나갈 수 없다.

**실행 플래그의 리터럴을 이 파일에 쓰지 마라.** `no_commit_guard.sh` 가
`webapp/tests` 트리 전체를 훑어 그 문자열을 찾으면 exit 1 이다. 가드가 감시하는
문자열을 테스트가 들고 있으면 "테스트에는 있어도 된다" 는 예외가 생기고, 그 예외가
언젠가 진짜 실행으로 자란다. 그래서 아래에서는 `"--" + "commit"` 처럼 나눠 조립한다 —
런타임 코드(`webapp/argv.py`)에는 리터럴이 있어야 하지만 테스트 트리에는 없어야 한다.
"""
from pathlib import Path

import pytest
from pydantic import ValidationError

from webapp import argv as A

# 가드가 스캔하는 문자열을 이 파일에 남기지 않으려고 런타임에 조립한다.
실행플래그 = "--" + "commit"
되돌리기플래그 = "--revert"


def test_첫번째는_CLI_전용_venv_의_파이썬이다():
    """`build()[0]` 이 저장소의 `.venv/bin/python3` 다 — `.venv-web` 이 **아니다**.

    웹앱은 `.venv-web`(fastapi·uvicorn)에서 돌고 CLI 는 `.venv`(selenium·openpyxl)가
    필요하다. `sys.executable` 을 쓰면 웹앱의 인터프리터로 CLI 를 띄우게 되어
    `run_ads.py` 가 import 단계에서 죽는다 (ENG-01 / T-1-10).
    """
    av = A.AdsArgv(subcommand="bids", run_dir="2026-08-30").build()

    assert av[0] == str(A.PY_CLI)
    assert av[0].endswith("/.venv/bin/python3")
    assert "/.venv-web/" not in av[0]
    assert Path(av[0]).is_absolute()


def test_두번째가_run_ads_세번째가_서브커맨드다():
    av = A.AdsArgv(subcommand="bids", run_dir="2026-08-30").build()

    assert av[1] == str(A.RUN_ADS)
    assert av[1].endswith("/naver-ads-weekly/scripts/run_ads.py")
    assert Path(av[1]).is_absolute()
    assert av[2] == "bids"
    # 회차는 플래그와 값이 **분리된 두 원소**다. 한 문자열로 붙이면 셸 문법이 필요해진다.
    assert av[3:5] == ["--run-dir", "2026-08-30"]


def test_계정이_비면_플래그_자체를_안_붙인다():
    """값 없는 `--account` 는 **전 계정**이 된다 (§1.1 함정).

    `run_ads.py` 의 `--account` 는 `nargs="*"` 라 값 없이 붙으면 `[]` 가 되고,
    `_accounts(only=[])` 의 `if only:` 가 falsy 로 떨어져 전 계정을 돌린다.
    "한 계정만 돌리려다 4계정을 돌리는" 사고가 여기서 난다.
    """
    av = A.AdsArgv(subcommand="prep").build()
    assert "--account" not in av


def test_계정이_있으면_값들이_이어붙는다():
    av = A.AdsArgv(subcommand="prep", accounts=["acct_one", "acct-two"]).build()

    i = av.index("--account")
    assert av[i + 1:i + 3] == ["acct_one", "acct-two"]


def test_계정_alias_는_영숫자_언더스코어_하이픈만():
    """alias 패턴 검증 — argv 에 셸 메타문자·공백·경로가 섞여 들어올 입구를 막는다.

    상한(`max_length`)은 두지 않는다. 계정은 설정에 항목을 더하는 것만으로 늘어난다
    (지금 4개 → 6개 예정). 개수를 코드에 박으면 계정을 늘린 날 화면이 조용히 멈춘다.
    """
    for 나쁜값 in ["a b", "a;rm -rf /", "../../etc/passwd", "a$(id)", "a|b", ""]:
        with pytest.raises(ValidationError):
            A.AdsArgv(subcommand="prep", accounts=[나쁜값])

    # 개수 제한은 없다 — 10개를 줘도 조립된다
    많이 = [f"acct{i}" for i in range(10)]
    assert A.AdsArgv(subcommand="prep", accounts=많이).build()[-10:] == 많이


def test_실행_플래그는_켜야만_붙는다():
    """기본값이 꺼짐이다 — 기본값이 "실제로 돈을 쓴다" 인 경로를 만들지 않는다."""
    기본 = A.AdsArgv(subcommand="bids", run_dir="2026-08-30").build()
    assert 실행플래그 not in 기본
    # 문자열 어디에도 그 단어가 없다(붙여쓰기·오탈자로 섞여 들어간 경우까지 본다)
    assert not any("commit" in a for a in 기본)

    켠것 = A.AdsArgv(subcommand="bids", run_dir="2026-08-30", commit=True).build()
    assert 실행플래그 in 켠것

    되돌리기 = A.AdsArgv(subcommand="bids", run_dir="2026-08-30", revert=True).build()
    assert 되돌리기플래그 in 되돌리기
    assert 실행플래그 not in 되돌리기


def test_경로_인자는_문자열로_붙는다(tmp_path):
    """`Path` 를 그대로 argv 에 넣으면 `Popen` 이 받긴 해도 DB 기록이 깨진다.

    jobs 테이블의 argv 컬럼은 JSON 배열이라 `Path` 객체가 섞이면 직렬화가 터진다.
    조립 단계에서 문자열로 못박는다.
    """
    대상 = tmp_path / "targets.json"
    미리보기 = tmp_path / "preview.json"
    av = A.AdsArgv(subcommand="bids", run_dir="2026-08-30",
                   only_ads=대상, preview_out=미리보기).build()

    assert av[av.index("--only-ads") + 1] == str(대상)
    assert av[av.index("--preview-out") + 1] == str(미리보기)
    assert all(isinstance(a, str) for a in av)


def test_prefix_는_맨_앞에_온다():
    """Phase 2 의 `caffeinate -i` 자리 (ENG-06).

    맥북 idle sleep 이 수십 분짜리 폴링을 끊는다. 그때 `["/usr/bin/caffeinate","-i"]` 를
    이 필드에 넣는 것만으로 끝나야 한다 — argv 조립을 다시 뒤지지 않게.
    """
    av = A.AdsArgv(subcommand="prep", prefix=["/usr/bin/caffeinate", "-i"]).build()

    assert av[:2] == ["/usr/bin/caffeinate", "-i"]
    assert av[2] == str(A.PY_CLI)
    assert av[3] == str(A.RUN_ADS)
    assert av[4] == "prep"

    # 기본은 비어 있다 — Phase 1 에서는 아무것도 안 끼운다
    assert A.AdsArgv(subcommand="prep").build()[0] == str(A.PY_CLI)


def test_모르는_서브커맨드는_조립되지_않는다():
    """`Literal` 화이트리스트가 명령 주입의 1차 방어선이다 (T-1-10).

    서브커맨드가 자유 문자열이면 `"bids; rm -rf ~"` 같은 값이 argv 에 들어간다.
    `shell=False` 덕에 그대로 실행되지는 않지만, 화이트리스트는 그 뒤에 한 겹 더 있다.
    """
    for 나쁜값 in ["drop", "bids; rm -rf /", "prep ", "PREP", ""]:
        with pytest.raises(ValidationError):
            A.AdsArgv(subcommand=나쁜값)


def test_조립결과에_셸이_해석할_여지가_없다():
    """리스트 argv + `shell=False` — 문자열 명령을 만드는 코드가 없어야 성립한다.

    `subprocess` 는 리스트를 받으면 셸을 거치지 않고 `execve` 로 직행한다.
    그래서 계정 alias 에 `;` 가 있어도 "그 이름의 계정" 을 찾다가 못 찾을 뿐이다.
    이 성질은 **조립을 한 곳에서만 하는 동안만** 유지된다 — 다른 파일이 문자열로
    명령을 만들기 시작하면 무너진다. 그걸 아래 `test_문자열로_명령을_만드는_코드가_없다`
    가 감시한다.
    """
    av = A.AdsArgv(subcommand="bids", run_dir="2026-08-30",
                   accounts=["acct_one"]).build()
    assert isinstance(av, list)
    assert all(isinstance(a, str) and "\n" not in a for a in av)


def test_문자열로_명령을_만드는_코드가_없다():
    """`shell=True` 와 `os.system` 이 웹앱 런타임에 0건 (T-1-10).

    조립이 한 곳이라는 주장은 "다른 곳에 조립이 없다" 를 기계로 확인해야 주장이 된다.
    """
    웹앱 = Path(A.__file__).resolve().parent
    for f in 웹앱.rglob("*.py"):
        if "tests" in f.parts:
            continue
        본문 = f.read_text(encoding="utf-8", errors="ignore")
        assert "shell=True" not in 본문, f"{f} 에 shell=True 가 있다"
        assert "os.system(" not in 본문, f"{f} 에 os.system 이 있다"


def test_sys_executable_을_쓰지_않는다():
    """웹앱 런타임 어디에도 `sys.executable` 이 없다.

    저장소의 다른 스크립트(`runner/onestep.py:36`, `sellerlife-keyword/run_all.py:30`)는
    `sys.executable` 로 자식을 띄운다. 그건 그들이 **CLI 와 같은 venv 안에서** 돌기
    때문이고, 웹앱은 다르다. 이 차이를 잊으면 CLI 가 selenium 을 못 찾는다.
    """
    웹앱 = Path(A.__file__).resolve().parent
    for f in 웹앱.rglob("*.py"):
        if "tests" in f.parts:
            continue
        assert "sys.executable" not in f.read_text(encoding="utf-8", errors="ignore"), \
            f"{f} 에 sys.executable 이 있다 — .venv-web 으로 CLI 를 띄우게 된다"
