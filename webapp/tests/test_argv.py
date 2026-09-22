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


def test_웹앱에_다운로더도_Pillow도_없다():
    """`webapp/**` 런타임 전체에 다운로더·이미지 라이브러리 import 0건 (D-19 / T-4-02).

    **왜 파일 지정형이 아니라 트리 순회인가.** `test_join.py` 의 가드는 파일 이름을
    나열한다 — 지금은 `join.py`·`state.py`·`banner.py` 셋이다. 그건 그 셋만 지킨다.
    다음 사람이 `routes/banner.py` 에 썸네일 생성을 한 줄 넣으면 파일 지정형은 그냥
    통과한다. D-19 가 대상으로 삼는 것은 **`webapp/` 전체**이므로, 순회형이어야
    "웹앱은 네트워크와 이미지에 손대지 않는다" 는 주장이 기계로 성립한다.
    바로 위 두 가드(`shell=True`·`sys.executable`)가 같은 논리로 서 있다.

    Phase 4 가 이걸 처음 필요하게 만들었다 — 이미지 891장을 받아 OCR 을 돌리는 코드가
    저장소에 생겼기 때문이다(`banner_scan.py`). 그건 **CLI 자식**이고 `.venv` 에서 돈다.
    `.venv-web` 에는 그 패키지들이 아예 없어서, 웹앱이 부르면 ImportError 다 —
    이 테스트는 그 물리적 사실이 **우연이 아니라 설계**임을 고정한다.

    **금지 문자열을 이 파일에 글자로 남기지 않는다.** 이 파일 맨 위 docstring 의
    규율과 같다 — 가드가 감시하는 문자열을 테스트가 들고 있으면 "테스트에는 있어도
    된다" 는 예외가 생기고, 그 예외가 언젠가 진짜 코드로 자란다. 런타임에 조립한다.
    """
    금지목록 = ("from " + "PIL", "import " + "PIL", "urllib" + ".request",
              "import " + "requests", "httpx" + ".", "urlopen" + "(")
    웹앱 = Path(A.__file__).resolve().parent
    본것 = 0
    for f in 웹앱.rglob("*.py"):
        if "tests" in f.parts:
            continue
        본문 = f.read_text(encoding="utf-8", errors="ignore")
        본것 += 1
        for 금지 in 금지목록:
            assert 금지 not in 본문, (
                f"{f} 에 '{금지}' 가 있다 (D-19) — 이미지 다운로드·OCR 은 전부 "
                "CLI 자식(banner_scan.py) 몫이다")
    # 순회가 실제로 무언가를 훑었는가. 0개를 훑고 통과하면 있는 척만 하는 가드다(T-1-12).
    assert 본것 >= 5, f"런타임 파일을 {본것}개밖에 안 훑었다 — 순회가 고장났다"


# ── 불사자 argv (Phase 3) ───────────────────────────────────────────────────
#
# 여기서도 서브프로세스를 띄우지 않는다. 불사자 MCP 는 **조회만** 하는 잡이지만
# 레이트리밋 예산(240;w=60)은 공유 자원이라, 테스트가 실수로 자식을 띄우면 그 예산을 갉아먹는다.

from webapp import jobs as J          # noqa: E402
from webapp import settings as S      # noqa: E402


def _불사자(하위="index", **덮기):
    """`BulsajaArgv` 를 최소 인자로 만든다.

    설정값은 **테스트가 직접 넘긴다** — 모델에 기본값이 없다는 게 검증 대상이라,
    여기서 기본값을 흉내 내면 그 성질이 가려진다.
    """
    기본 = dict(subcommand=하위, db=Path("/tmp/zz.db"), out=Path("/tmp/zz-out.json"),
                profile_out=Path("/tmp/zz-profile.json"), expect_nick="zz닉",
                min_interval=0.26, retry_after=21, batch_size=50)
    기본.update(덮기)
    return A.BulsajaArgv(**기본)


def test_불사자_argv_도_cli_인터프리터를_쓴다():
    """웹앱 venv 로 불사자 CLI 를 띄우면 import 단계에서 죽는다 (ENG-01 / T-1-10)."""
    av = _불사자().build()

    assert av[0] == str(A.PY_CLI)
    assert av[0].endswith("/.venv/bin/python3")
    assert "/.venv-web/" not in av[0]
    assert av[1] == str(A.SS_INDEX_BUILD)
    assert Path(av[1]).is_absolute()


def test_서브커맨드가_스크립트를_고른다():
    """`profile` 과 `scan` 은 **같은 스크립트의 두 모드**다."""
    assert _불사자("index").build()[1] == str(A.SS_INDEX_BUILD)
    assert _불사자("scan").build()[1] == str(A.BULSAJA_SCAN)

    계정확인 = _불사자("profile").build()
    assert 계정확인[1] == str(A.BULSAJA_SCAN)
    assert "--profile-only" in 계정확인
    # 계정 확인에는 산출물이 없다 — 자식은 `--profile-out` 만 갱신한다
    assert "--out" not in 계정확인
    assert "--profile-out" in 계정확인


def test_caffeinate_프리픽스가_앞에_붙는다():
    """3시간 32분짜리 인덱스가 맥북 idle sleep 에 끊기지 않게 (ENG-06).

    자리는 `AdsArgv.prefix` 와 같다 — 프리픽스 다음이 인터프리터, 그 다음이 스크립트다.
    """
    av = _불사자(prefix=["/usr/bin/caffeinate", "-i"]).build()

    assert av[:2] == ["/usr/bin/caffeinate", "-i"]
    assert av[2] == str(A.PY_CLI)
    assert av[3] == str(A.SS_INDEX_BUILD)

    assert _불사자().build()[0] == str(A.PY_CLI)      # 기본은 비어 있다


def test_인덱스_잡만_caffeinate_로_감싸진다(tmp_path, monkeypatch):
    """**`prefix` 필드가 있는 것과 실제로 붙는 것은 다르다** (ENG-06 / T-3-37).

    위 `test_caffeinate_프리픽스가_앞에_붙는다` 는 조립 계층만 본다 — `prefix` 를
    넘기면 앞에 붙는다는 것. 그런데 03-05 가 `jobs._build_argv` 에서 그걸 **안 넘겨서**,
    3시간 32분짜리 인덱스가 맥북 idle sleep 에 무방비인 채로 돌 뻔했다(03-07 실측 발견).
    조립 테스트만으로는 그 구멍이 안 보인다. 그래서 잡 계층에서 한 번 더 문다.

    계정 확인(0.14초)·조인 스캔(18초)에는 안 붙는 것도 같이 고정한다 — 수 초짜리 잡에
    전력 assertion 을 거는 건 비용만 있고 얻는 게 없다.
    """
    from webapp import paths as P

    (tmp_path / "workspace.toml").write_text(
        '[webapp]\nexpected_bulsaja_nick = "zz기대계정"\n', encoding="utf-8")
    monkeypatch.setattr(P, "repo_root", lambda: tmp_path)
    S.reload()
    try:
        인덱스 = J._build_argv("bulsaja_index", "zzjob", None, [],
                             tmp_path / "zzg.json", tmp_path / "zzout.json", False)
        스캔 = J._build_argv("bulsaja_scan", "zzjob", "2026-09-20", [],
                           tmp_path / "zzt.json", tmp_path / "zzout.json", False)
        계정 = J._build_argv("bulsaja_profile", "zzjob", None, [],
                           None, None, False)
    finally:
        monkeypatch.undo()
        S.reload()

    assert 인덱스[:2] == [J.CAFFEINATE, "-i"]
    assert 인덱스[2] == str(A.PY_CLI)          # 프리픽스 다음이 인터프리터
    assert 인덱스[3] == str(A.SS_INDEX_BUILD)
    assert 스캔[0] == str(A.PY_CLI)            # 짧은 잡에는 안 붙는다
    assert 계정[0] == str(A.PY_CLI)


def test_caffeinate_가_없는_기계에서는_안_붙인다(monkeypatch):
    """바이너리가 없으면 **잡이 안 뜨는 것보다 절전 방지를 포기하는 쪽**이다.

    끊기면 재개(`ss_index` productId 집합)가 복구한다. 그런데 자식이 아예 안 뜨면
    복구할 것도 없다 — 바꿔치기의 방향이 한쪽으로 분명하다.
    """
    monkeypatch.setattr(J.os.path, "exists", lambda p: False)
    assert J._수면방지_프리픽스("bulsaja_index") == []


def test_limit_0_이면_플래그가_없다():
    """0 은 "상한 없음" 이다. `--limit 0` 을 넘기면 자식이 "0건만" 으로 읽을 수 있다."""
    assert "--limit" not in _불사자().build()
    assert "--limit" in _불사자(limit=5).build()


def test_groups_None_이면_플래그가_없다():
    """조립 단계는 그냥 안 붙인다.

    **터뜨리는 자리는 `jobs._build_argv` 한 곳**이다 — 같은 규칙이 두 곳에 있으면
    둘이 어긋났을 때 어느 쪽이 진짜 가드인지 모른다.
    """
    assert "--groups" not in _불사자().build()
    assert "--targets" not in _불사자("scan").build()

    붙은것 = _불사자(groups=Path("/tmp/zz-groups.json")).build()
    assert 붙은것[붙은것.index("--groups") + 1] == "/tmp/zz-groups.json"


def test_닉네임에_플래그모양은_거부된다():
    """닉네임이 `--force` 모양이면 자식의 argparse 가 그걸 **옵션으로** 파싱한다 (T-3-13).

    리스트 argv 라 셸은 안 거치지만, 셸을 안 거치는 것과 파서를 안 거치는 것은 다르다.
    """
    for 나쁜값 in ["--force", "-x", "닉 네임", "닉\t네임", "", " "]:
        with pytest.raises(ValidationError):
            _불사자(expect_nick=나쁜값)

    # 한글은 통과한다 — `Alias` 의 영숫자 화이트리스트를 그대로 쓸 수 없는 이유다
    통과 = _불사자(expect_nick="가나다라").build()
    assert 통과[통과.index("--expect-nick") + 1] == "가나다라"


def test_불사자_경로_인자도_문자열로_붙는다():
    """`Path` 가 섞이면 jobs 테이블의 argv 컬럼(JSON 배열) 직렬화가 터진다."""
    av = _불사자(groups=Path("/tmp/zz-groups.json"), limit=3).build()
    assert all(isinstance(a, str) for a in av)


# ── jobs 쪽 계약 ────────────────────────────────────────────────────────────

def test_불사자_kind_3종이_등록돼_있다():
    """`JobKind` 만 고치고 `KINDS` 를 빠뜨리면 런타임이 거부한다 — 둘 다 본다."""
    for k in ("bulsaja_profile", "bulsaja_index", "bulsaja_scan"):
        assert k in J.KINDS
        assert k in J.JobKind.__args__


def test_불사자잡은_전역_쓰기가드에_안_들어간다():
    """넣으면 3시간 32분 동안 입찰가 인상·되돌리기가 전부 409 다."""
    assert not (set(J.WRITE_KINDS) & {"bulsaja_index", "bulsaja_scan", "bulsaja_profile"})
    # 계정 확인 잡은 ENG-08 가드 대상이 **아니다** — 프로필을 만드는 잡이라 닭·달걀이 된다
    assert "bulsaja_profile" not in J.BULSAJA_KINDS
    assert J.BULSAJA_KINDS == frozenset({"bulsaja_index", "bulsaja_scan"})


def test_인덱스잡은_그룹파일이_없으면_터진다():
    """빈 값이 '전 그룹' 으로 해석되는 경로를 예외로 터뜨린다 (T-3-12).

    `revert_only` 와 **똑같은 모양**이다 — 그쪽은 회차 전체 2,242건이 풀리는 사고였고,
    이쪽은 다섯 시간 넘게 타는 사고다.
    """
    with pytest.raises(ValueError) as 터진것:
        J._build_argv("bulsaja_index", "zzjob", None, [], None,
                      Path("/tmp/zz-out.json"), False)
    assert "그룹" in str(터진것.value)


def test_스캔잡은_대상파일이_없으면_터진다():
    """대상 파일은 하나이고, 없으면 만들지 않는다 (FLOW-02 / D-11)."""
    with pytest.raises(ValueError) as 터진것:
        J._build_argv("bulsaja_scan", "zzjob", "2026-08-30", [], None,
                      Path("/tmp/zz-out.json"), False)
    assert "대상" in str(터진것.value)


def test_계정확인잡은_대상파일이_필요없다():
    """계정 확인에 대상이 없다 — 여기까지 필수로 만들면 첫 확인을 영영 못 한다."""
    av = J._build_argv("bulsaja_profile", "zzjob", None, [], None,
                       Path("/tmp/zz-profile.json"), False)
    assert "--profile-only" in av
    assert "--groups" not in av and "--targets" not in av


def test_설정값이_argv_로_흐른다(tmp_path, monkeypatch):
    """`workspace.toml` 을 고치면 자식에게 가는 값이 **실제로** 바뀐다.

    모델이나 CLI 에 기본값이 있으면 이 테스트가 빨개진다 — 그게 "있는 척만 하는 설정" 이다.
    """
    from webapp import paths as P

    (tmp_path / "workspace.toml").write_text(
        '[webapp]\n'
        'expected_bulsaja_nick = "zz기대계정"\n'
        'mcp_min_interval = 1.5\n'
        'mcp_retry_after = 99\n'
        'mcp_batch_size = 7\n',
        encoding="utf-8")
    monkeypatch.setattr(P, "repo_root", lambda: tmp_path)
    S.reload()
    try:
        av = J._build_argv("bulsaja_index", "zzjob", None, [], tmp_path / "zzg.json",
                           tmp_path / "zzout.json", False)
    finally:
        monkeypatch.undo()
        S.reload()

    assert av[av.index("--min-interval") + 1] == "1.5"
    assert av[av.index("--retry-after") + 1] == "99"
    assert av[av.index("--batch-size") + 1] == "7"
    assert av[av.index("--expect-nick") + 1] == "zz기대계정"


def test_기대닉네임이_비면_argv_조립이_터진다(tmp_path, monkeypatch):
    """`required=True` — 값이 비면 KeyError 다. 조용히 폴백하면 ENG-08 가드가 사라진다."""
    from webapp import paths as P

    (tmp_path / "workspace.toml").write_text('[webapp]\n', encoding="utf-8")
    monkeypatch.setattr(P, "repo_root", lambda: tmp_path)
    S.reload()
    try:
        with pytest.raises(KeyError):
            J._build_argv("bulsaja_index", "zzjob", None, [], tmp_path / "zzg.json",
                          tmp_path / "zzout.json", False)
    finally:
        monkeypatch.undo()
        S.reload()


# ── 배너 argv (Phase 4) ─────────────────────────────────────────────────────
#
# 여기서도 서브프로세스를 띄우지 않는다. 배너 스캔은 크레딧 0 · MCP 0회지만 실측
# 4분 12초 · 271MB 다운로드짜리다 — 테스트가 실수로 자식을 띄우면 CDN 에 실제 요청이
# 나가고 그 회차 캐시가 통째로 다시 받아진다.

def _배너(**덮기):
    """`BannerArgv` 를 최소 인자로 만든다.

    설정값은 **테스트가 직접 넘긴다** — 모델에 기본값이 없다는 게 검증 대상이라,
    여기서 기본값을 흉내 내면 그 성질이 가려진다 (`_불사자` 와 같은 규율).
    """
    기본 = dict(join=Path("/tmp/zz-join.json"), out=Path("/tmp/zz-banner.json"),
                run_dir="2026-09-20", cache=Path("/tmp/zz-cache"),
                thumbs=Path("/tmp/zz-thumbs"), workers=8, vision_revision=3,
                blank_ar=6.0, blank_short_px=32, skip_min_keep=2,
                skip_max_removal=0.5, lexicon_version="2026-09-22", keep_runs=2)
    기본.update(덮기)
    return A.BannerArgv(**기본)


def test_배너_argv_도_cli_인터프리터를_쓴다():
    """Pillow 와 Vision 이 `.venv` 에만 있다 — 여기선 취향이 아니라 물리적 요구사항이다.

    `.venv-web` 으로 띄우면 이미지 한 장을 열기도 전에 ImportError 다 (D-19 / ENG-01).
    프리픽스가 붙으면 그 다음이 인터프리터, 그 다음이 스크립트다 (`AdsArgv` 와 같은 자리).
    """
    av = _배너().build()

    assert av[0] == str(A.PY_CLI)
    assert av[0].endswith("/.venv/bin/python3")
    assert "/.venv-web/" not in av[0]
    assert av[1] == str(A.BANNER_SCAN)
    assert av[1].endswith("/bulsaja-detail-page/scripts/banner_scan.py")
    assert Path(av[1]).is_absolute()

    감싼것 = _배너(prefix=["/usr/bin/caffeinate", "-i"]).build()
    assert 감싼것[:2] == ["/usr/bin/caffeinate", "-i"]
    assert 감싼것[2] == str(A.PY_CLI)
    assert 감싼것[3] == str(A.BANNER_SCAN)


def test_배너_argv_는_전부_문자열이다():
    """`Path` 나 `int` 가 섞이면 jobs 테이블의 argv 컬럼(JSON 배열) 직렬화가 터진다.

    숫자 플래그가 많아서(`--workers`·`--blank-ar`·`--skip-max-removal` …) 이 파일의
    다른 모델보다 미끄러지기 쉬운 자리다.
    """
    av = _배너(prefix=["/usr/bin/caffeinate", "-i"]).build()

    assert all(isinstance(a, str) and "\n" not in a for a in av), av
    # 필수 5개가 실제로 다 실렸는가 — 하나라도 빠지면 자식이 exit 2 다 (04-03 계약)
    for 플래그 in ("--join", "--out", "--run-dir", "--cache", "--thumbs"):
        assert 플래그 in av, f"{플래그} 가 빠졌다 — 자식이 exit 2 로 거부한다"
    assert av[av.index("--run-dir") + 1] == "2026-09-20"
    assert av[av.index("--blank-ar") + 1] == "6.0"


def test_배너_임계값에_모델_기본값이_없다():
    """🔴 가짜 설정 방지 회귀 (T-1-12 / S-4).

    모델이나 CLI 에 기본값을 두면 `workspace.toml` 을 고쳐도 동작이 안 바뀐다.
    배너 쪽은 한 겹 더 나쁘다 — 넘긴 값이 그대로 산출물 `판정규칙` 블록에 찍히므로,
    모델 기본값으로 때우면 **"무슨 규칙으로 판정했나" 의 출처가 둘**이 된다.
    그러면 회차 간 비교가 거짓말이 되고, 그게 D-10 이 경고한 바로 그 상황이다.

    빠뜨릴 수 있는 인자를 **하나씩 전부** 확인한다 — 한 필드만 보면 다음 사람이
    다른 필드에 기본값을 넣었을 때 이 테스트가 통과하는 척만 한다.
    """
    필수 = ("join", "out", "run_dir", "cache", "thumbs", "workers", "vision_revision",
           "blank_ar", "blank_short_px", "skip_min_keep", "skip_max_removal",
           "lexicon_version", "keep_runs")
    온전 = dict(join=Path("/tmp/zz-join.json"), out=Path("/tmp/zz-banner.json"),
                run_dir="2026-09-20", cache=Path("/tmp/zz-cache"),
                thumbs=Path("/tmp/zz-thumbs"), workers=8, vision_revision=3,
                blank_ar=6.0, blank_short_px=32, skip_min_keep=2,
                skip_max_removal=0.5, lexicon_version="2026-09-22", keep_runs=2)

    for 뺄것 in 필수:
        모자란것 = {k: v for k, v in 온전.items() if k != 뺄것}
        with pytest.raises(ValidationError):
            A.BannerArgv(**모자란것)

    # `prefix` 는 반대다 — 기본값(빈 리스트)이 있어야 한다. 프리픽스를 붙일지는
    # 잡 종류가 정하는 판단이라 모델이 강요하면 그 판단이 두 곳으로 갈린다.
    assert A.BannerArgv(**온전).prefix == []


def test_어휘군_버전이_플래그_모양이면_거부된다():
    """설정값이 `--force` 모양이면 자식의 argparse 가 그걸 **옵션으로** 파싱한다 (T-4-17).

    `expect_nick` 과 같은 계열의 방어다 — 리스트 argv 라 셸은 안 거치지만,
    셸을 안 거치는 것과 파서를 안 거치는 것은 다르다.
    """
    for 나쁜값 in ["--force", "-x", "2026 09 21", "", " "]:
        with pytest.raises(ValidationError):
            _배너(lexicon_version=나쁜값)
