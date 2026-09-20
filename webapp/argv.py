#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI argv 조립 — **argv 를 조립하는 곳은 여기 하나다.**

다른 파일에서 문자열로 명령을 만들지 마라 — 명령 주입 경로가 거기서 생긴다.
여기서만 조립하는 한 세 가지가 구조로 보장된다:

  1. `subcommand` 가 `Literal` 화이트리스트를 통과한다 (T-1-10 1차 방어선)
  2. 계정 alias 가 영숫자·언더스코어·하이픈만 담는다
  3. 결과가 **리스트**라 `subprocess` 가 셸을 거치지 않고 곧장 execve 로 간다

그래서 계정 이름에 `;rm -rf ~` 가 들어와도 "그런 이름의 계정을 못 찾았다" 로 끝난다.
이 성질은 조립이 한 곳일 때만 산다. `webapp/tests/test_argv.py` 의
`test_문자열로_명령을_만드는_코드가_없다` 가 웹앱 런타임 전체에 셸 경유 실행이
0건임을 상시 확인한다 — 그 테스트가 찾는 문자열을 이 파일에도 적지 않는 이유다.

**웹앱은 CLI 의 래퍼다** (PROJECT.md 제약). 판정·입찰가 계산을 여기서 다시 하지 않는다.
이 파일이 아는 것은 "어떤 명령을 어떤 플래그로 부르는가" 뿐이다.
"""
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints

from webapp import paths

# CLI 전용 인터프리터. **지금 이 코드를 돌리고 있는 인터프리터를 쓰지 마라.**
#
# 웹앱은 `.venv-web`(fastapi·uvicorn·pydantic)에서 돌고, CLI 는
# `.venv`(selenium·openpyxl·pillow·requests)가 필요하다. 저장소의 다른 스크립트들
# (`.claude/lib/eroomlib/runner/onestep.py:36`, `sellerlife-keyword/scripts/run_all.py:30`)
# 은 "현재 인터프리터" 로 자식을 띄우는데, 그건 **그들이 CLI 와 같은 venv 안에서 돌기
# 때문**이다. 웹앱은 다르다 — 현재 인터프리터로 `run_ads.py` 를 띄우면 `.venv-web` 에
# 없는 selenium 을 찾다가 import 단계에서 죽는다. 두 venv 를 subprocess 경계로 갈라
# 두는 것이 설계다(STACK.md §핵심결정 1).
# 그 안티패턴은 `webapp/tests/test_argv.py` 의 마지막 테스트가 웹앱 런타임 전체에서
# 감시한다. 그래서 이 파일에는 그 속성 이름을 주석으로도 적지 않는다.
PY_CLI = paths.repo_root() / ".venv" / "bin" / "python3"

RUN_ADS = (paths.repo_root() / ".claude" / "skills" / "naver-ads-weekly"
           / "scripts" / "run_ads.py")

# 계정 alias 의 모양. 상한(개수)은 두지 않는다 — 계정은 `~/.eroom/naver-ads.json` 에
# 항목을 더하는 것만으로 늘어난다(지금 4개, 6개 예정). 개수를 코드에 박으면
# 계정을 늘린 날 화면이 조용히 멈춘다 (BOARD-02 와 같은 이유).
Alias = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]+$", min_length=1)]


class AdsArgv(BaseModel):
    """`run_ads.py` 호출 한 번을 표현하는 모델. `build()` 가 argv 리스트를 낸다.

    필드는 `run_ads.py main()` 의 서브파서와 1:1 이다(그쪽이 계약의 반대편).
    `accounts`·`prefix` 의 기본값이 빈 리스트인 것에 의미가 있다 — 아래 `build()` 주석.
    """

    subcommand: Literal["prep", "run", "apply", "bids", "accounts"]
    run_dir: str | None = None
    accounts: list[Alias] = []
    commit: bool = False
    revert: bool = False
    only_ads: Path | None = None
    preview_out: Path | None = None
    # Phase 2 의 `caffeinate -i` 자리 (ENG-06). 예: ["/usr/bin/caffeinate", "-i"]
    # 맥북 idle sleep 이 수십 분짜리 폴링을 끊는다. `man caffeinate` 기준
    # utility 를 지정하면 그 프로세스 수명 동안만 assertion 이 유지된다 —
    # 자식이 끝나면 저절로 풀리므로 따로 해제할 일이 없다.
    # Phase 1 에서는 항상 비어 있지만 **필드가 존재해야** Phase 2 가 한 줄로 끝난다.
    prefix: list[str] = []

    def build(self) -> list[str]:
        """argv 리스트. 셸을 거치지 않으므로 따옴표·이스케이프가 필요 없다."""
        av: list[str] = [*self.prefix, str(PY_CLI), str(RUN_ADS), self.subcommand]

        if self.run_dir:
            av += ["--run-dir", self.run_dir]

        # **빈 리스트면 플래그 자체를 안 붙인다.**
        # `run_ads.py` 의 `--account` 는 `nargs="*"` 라 값 없이 붙으면 `[]` 가 되고,
        # `_accounts(only=[])` 의 `if only:` 가 falsy 로 떨어져 **전 계정**을 돈다.
        # 한 계정만 돌리려다 4계정(=수 분 × 4)을 돌리는 사고가 여기서 난다.
        if self.accounts:
            av += ["--account", *self.accounts]

        if self.commit:
            av += ["--commit"]
        if self.revert:
            av += ["--revert"]

        # 경로는 `str()` 로 못박는다. `Path` 를 그대로 두면 `Popen` 은 받아도
        # jobs 테이블의 argv 컬럼(JSON 배열) 직렬화가 터진다.
        if self.only_ads:
            av += ["--only-ads", str(self.only_ads)]
        if self.preview_out:
            av += ["--preview-out", str(self.preview_out)]

        return av
