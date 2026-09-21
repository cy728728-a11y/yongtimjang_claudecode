#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI 가 **이 맥북에서 import 단계를 통과하는지**만 본다 — 크레딧 0, 쓰기 0, 네트워크 0.

STATE-01 회귀. `detail_batch.py` 는 모듈 최상위에서 `bulsaja_mcp` 를 import 하는데,
그 경로가 윈도 절대경로(`C:\\…`)로 박혀 있어서 맥에서는 `sys.path.insert` 가 no-op 이 되고
import 가 `ModuleNotFoundError` 로 죽었다. 그래서 **`--help` 하나로 증명이 끝난다** —
argparse 가 usage 를 찍었다는 건 최상위 import 가 전부 통과했다는 뜻이다.
접수도 폴링도 일어나지 않으므로 크레딧이 나갈 여지가 없다.

⚠️ 인터프리터는 `webapp.argv.PY_CLI`(= `.venv/bin/python3`) 를 쓴다.
   이 테스트를 돌리는 `.venv-web` 으로 CLI 를 띄우면 검증이 무의미하다 —
   두 venv 를 subprocess 경계로 갈라 둔 것이 설계고, CLI 는 `.venv` 에서 돈다.
"""
import subprocess

import pytest

from webapp import argv, paths

DETAIL_BATCH = (paths.repo_root() / ".claude" / "skills" / "bulsaja-detail-page"
                / "scripts" / "detail_batch.py")


def _꼬리(텍스트: bytes, 줄수: int = 20) -> str:
    """실패 메시지에 실을 stderr 마지막 N줄. 원인이 안 보이면 테스트가 쓸모없다."""
    try:
        줄들 = 텍스트.decode("utf-8", errors="replace").splitlines()
    except Exception:
        return "<stderr 를 디코드하지 못했다>"
    return "\n".join(줄들[-줄수:]) or "<stderr 비어 있음>"


def test_상세배치가_이_맥북에서_뜬다():
    """`detail_batch.py --help` 가 exit 0 이고 usage 를 찍는다 (STATE-01).

    Core Value 경로(유입은 있는데 상세가 중국어 원본인 상품을 고친다)의 첫 관문이다.
    여기가 막혀 있으면 Phase 5 의 버튼이 아무리 잘 만들어져도 아무 일도 안 일어난다.
    """
    assert DETAIL_BATCH.is_file(), f"CLI 가 없다: {DETAIL_BATCH}"
    assert argv.PY_CLI.is_file(), (
        f"CLI 인터프리터가 없다: {argv.PY_CLI} — `.venv` 가 만들어져 있어야 한다")

    try:
        p = subprocess.run([str(argv.PY_CLI), str(DETAIL_BATCH), "--help"],
                           capture_output=True, timeout=60)
    except subprocess.TimeoutExpired:                       # pragma: no cover - 방어
        pytest.fail("--help 가 60초 안에 안 끝났다 — 최상위에서 네트워크를 타고 있다")

    assert p.returncode == 0, (
        f"exit={p.returncode}\n--- stderr 끝 20줄 ---\n{_꼬리(p.stderr)}")

    나온것 = p.stdout.decode("utf-8", errors="replace")
    assert "--run-dir" in 나온것, f"usage 에 --run-dir 이 없다:\n{나온것[:500]}"


def test_윈도_경로가_남아있지_않다():
    """소스에 드라이브 문자 절대경로가 0건이다 — **경로 리터럴 재발 방지**다.

    보통은 문자열 검사를 피하지만(주석에도 걸리니까), 이건 반대다. 여기서 막고 싶은 게
    정확히 "소스에 박힌 경로 문자열" 이라서, 문자열 검사가 맞는 도구다.
    주석에 예시로라도 다시 적히면 다음 사람이 그걸 복사한다.
    """
    본문 = DETAIL_BATCH.read_text(encoding="utf-8", errors="ignore")
    드라이브 = ":" + "\\"          # 'C:\' 를 이 파일에 리터럴로 남기지 않으려고 조립한다
    걸린줄 = [f"{i}: {줄}" for i, 줄 in enumerate(본문.splitlines(), 1) if 드라이브 in 줄]
    assert not 걸린줄, "윈도 절대경로가 남아 있다:\n" + "\n".join(걸린줄)


def test_죽은_래퍼_안내가_남아있지_않다():
    """이 맥북에 없는 MCP 항목을 전제한 안내를 지웠다.

    `run_yong.py` 는 `bulsaja-yongssaem` MCP 항목을 전제하는데 이 맥북에는 그 항목이 없다
    (등록된 건 `aside`·`bulsaja` 둘뿐이고, 지금 붙은 `bulsaja` 가 곧 그 계정이다).
    docstring 의 안내를 그대로 따라 하면 실패한다 — SKILL.md 는 이미 '죽은 경로'로 적어 뒀다.
    """
    본문 = DETAIL_BATCH.read_text(encoding="utf-8", errors="ignore")
    죽은래퍼 = "run_" + "yong.py"   # 문자열 검사 대상을 이 파일에 통째로 남기지 않는다
    assert 죽은래퍼 not in 본문, f"{DETAIL_BATCH.name} 에 죽은 래퍼 안내가 남아 있다"


def _도움말(스크립트):
    """`--help` 를 돌려 `(returncode, stdout)` 을 준다 — 크레딧 0, 쓰기 0, 네트워크 0.

    argparse 가 usage 를 찍었다는 건 **모듈 최상위 import 가 전부 통과했다**는 뜻이다.
    두 CLI 다 최상위에서 `bulsaja_mcp` 를 import 하므로, shim 경로가 틀어지면 여기서 죽는다.
    """
    assert 스크립트.is_file(), f"CLI 가 없다: {스크립트}"
    assert argv.PY_CLI.is_file(), (
        f"CLI 인터프리터가 없다: {argv.PY_CLI} — `.venv` 가 만들어져 있어야 한다")
    try:
        p = subprocess.run([str(argv.PY_CLI), str(스크립트), "--help"],
                           capture_output=True, timeout=60)
    except subprocess.TimeoutExpired:                       # pragma: no cover - 방어
        pytest.fail(f"{스크립트.name} --help 가 60초 안에 안 끝났다 — "
                    "최상위에서 네트워크를 타고 있다")
    assert p.returncode == 0, (
        f"exit={p.returncode}\n--- stderr 끝 20줄 ---\n{_꼬리(p.stderr)}")
    return p.stdout.decode("utf-8", errors="replace")


def test_인덱스빌더가_뜬다():
    """`ss_index_build.py --help` 가 exit 0 이고 `--groups` 를 보여준다 (03-04).

    `--groups` 가 usage 에 있는지 보는 이유: 웹앱의 `BulsajaArgv` 가 조립하는 플래그와
    자식의 argparse 가 **한 글자라도 다르면 잡이 즉시 죽는다.** 그 계약을 여기서 못박는다.
    """
    나온것 = _도움말(argv.SS_INDEX_BUILD)
    assert "--groups" in 나온것, f"usage 에 --groups 가 없다:\n{나온것[:600]}"
    for 플래그 in ("--db", "--out", "--profile-out", "--expect-nick",
                  "--min-interval", "--retry-after", "--batch-size", "--limit"):
        assert 플래그 in 나온것, f"usage 에 {플래그} 가 없다 — argv 계약이 깨졌다"


def test_스캔이_뜬다():
    """`bulsaja_scan.py --help` 가 exit 0 이고 두 모드의 플래그를 다 보여준다 (03-04).

    `--profile-only` 가 usage 에 있어야 `bulsaja_profile` 잡이 뜬다 — 그 잡이 없으면
    계정 확인 산출물이 안 생기고, ENG-08 사전 점검이 **영원히 거부**로 굳는다.
    """
    나온것 = _도움말(argv.BULSAJA_SCAN)
    for 플래그 in ("--targets", "--profile-only", "--expect-nick", "--run-dir",
                  "--out", "--db", "--profile-out", "--min-interval",
                  "--retry-after", "--batch-size"):
        assert 플래그 in 나온것, f"usage 에 {플래그} 가 없다 — argv 계약이 깨졌다"


def test_스캔_CLI_는_판정을_하지_않는다():
    """조인 판정 어휘가 스캔 CLI 소스에 **한 글자도 없다.**

    보통은 문자열 검사를 피하지만 여기서 막고 싶은 게 정확히 "두 번째 판정 구현" 이다.
    판정이 CLI 와 `webapp/join.py` 두 곳에 있으면 화면과 산출물이 다른 말을 하고,
    그때 어느 쪽이 맞는지 아무도 모른다. 주석에라도 적히면 다음 사람이 그걸 구현한다.
    """
    본문 = argv.BULSAJA_SCAN.read_text(encoding="utf-8", errors="ignore")
    for 판정어 in ("히트", "불일치"):
        assert 판정어 not in 본문, (
            f"{argv.BULSAJA_SCAN.name} 에 판정 어휘 '{판정어}' 가 있다 — "
            "판정은 webapp/join.재검증판정 한 곳이다")


def test_스캔은_인덱스를_읽기만_한다():
    """스캔 CLI 가 `ss_index` 에 쓰지 않는다 — 인덱스를 고치는 건 인덱스 잡뿐이다.

    `mode=ro` 로 열면 SQLite 가 막아 주지만, 쓰기 SQL 이 소스에 등장하는 순간
    누군가 커넥션을 바꿔 열면 곧바로 뚫린다. 그래서 SQL 자체가 없는 것을 고정한다.
    """
    본문 = argv.BULSAJA_SCAN.read_text(encoding="utf-8", errors="ignore")
    assert "mode=ro" in 본문, "스캔이 인덱스를 읽기 전용으로 열지 않는다"
    for 쓰기 in ("INSERT", "UPDATE", "DELETE ", "DROP"):
        assert 쓰기 not in 본문, f"스캔 CLI 에 {쓰기} 가 있다 — 인덱스를 고치면 안 된다"


def test_인덱스빌더가_스키마를_만들지_않는다():
    """`ss_index` DDL 정본은 `webapp/jobs.py` 하나다 (D-20 / 위협 T-3-23).

    CLI 가 테이블을 만들면 스키마가 두 벌이 되고, 컬럼이 조용히 갈라진다.
    그때 인덱스 잡은 3시간 반을 멀쩡히 돌고도 웹앱이 못 읽는 테이블을 채운다.
    """
    본문 = argv.SS_INDEX_BUILD.read_text(encoding="utf-8", errors="ignore")
    생성문 = "CREATE " + "TABLE"     # 이 파일 자신이 검사 대상 문자열이 되지 않게 조립한다
    assert 생성문 not in 본문, f"{argv.SS_INDEX_BUILD.name} 에 테이블 생성문이 있다"
    assert "INSERT OR REPLACE INTO ss_index" in 본문, "인덱스를 적는 SQL 이 없다"
