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

# 불사자 CLI 두 개. **기존 스킬 디렉터리 밑에 둔다** — 그 자리의 스크립트는 `bulsaja_mcp`
# 를 `__file__` 기준 상대 shim 으로 이미 찾는다(`run_names.py:40-46` 관용구).
# 새 디렉터리를 파면 그 shim 경로 계산을 새로 해야 하고, 그게 STATE-01 에서 이미 한 번
# 고장났던 지점이다(윈도 절대경로 하드코딩).
SS_INDEX_BUILD = (paths.repo_root() / ".claude" / "skills" / "bulsaja-detail-page"
                  / "scripts" / "ss_index_build.py")
BULSAJA_SCAN = (paths.repo_root() / ".claude" / "skills" / "bulsaja-detail-page"
                / "scripts" / "bulsaja_scan.py")

# 배너 판정 스캐너 (Phase 4). **같은 스킬 디렉터리다** — 위 두 개와 같은 이유로 그 자리다.
# `PY_CLI` 를 쓰는 것이 여기서는 취향이 아니라 **물리적 요구사항**이다: Pillow 와
# pyobjc-framework-Vision 이 `.venv` 에만 있고 `.venv-web` 에는 아예 없다. 웹앱 인터프리터로
# 띄우면 이미지 한 장을 열기도 전에 ImportError 다.
BANNER_SCAN = (paths.repo_root() / ".claude" / "skills" / "bulsaja-detail-page"
               / "scripts" / "banner_scan.py")

# 상세페이지 배치 (Phase 5). **같은 스킬 디렉터리다** — 위 스크립트들과 같은 이유로 그 자리다.
# 05-01 이 `--inputs` 모드를 붙였다. 웹앱은 그 모드로만 부른다(products.json 경로를 안 탄다).
DETAIL_BATCH = (paths.repo_root() / ".claude" / "skills" / "bulsaja-detail-page"
                / "scripts" / "detail_batch.py")

# 계정 alias 의 모양. 상한(개수)은 두지 않는다 — 계정은 `~/.eroom/naver-ads.json` 에
# 항목을 더하는 것만으로 늘어난다(지금 4개, 6개 예정). 개수를 코드에 박으면
# 계정을 늘린 날 화면이 조용히 멈춘다 (BOARD-02 와 같은 이유).
Alias = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]+$", min_length=1)]

# 불사자 계정 닉네임의 모양. `Alias` 와 **같은 계열의 방어이고 한 군데만 다르다**:
# 닉네임은 한글이라 문자 화이트리스트(`[A-Za-z0-9_-]`)를 못 쓴다. 그래서 막는 것을
# 뒤집었다 — **선행 하이픈과 공백만 거부**한다.
#   · 선행 하이픈: 닉네임이 `--force` 같은 모양이면 argv 에서 **플래그로 읽힌다.**
#     리스트 argv 라 셸은 안 거치지만, 자식의 argparse 는 그걸 옵션으로 파싱한다.
#   · 공백: 한 값이 두 인자로 갈라지지는 않지만(리스트다), 눈으로 읽는 로그에서
#     경계가 사라져 "어디까지가 닉네임인가" 를 못 본다.
# 길이 상한 40 은 값의 성격(사람이 지은 계정 이름)에서 온다 — 계정 **개수** 상한이
# 아니므로 BOARD-02 의 "개수를 박지 마라" 와 충돌하지 않는다.
Nick = Annotated[str, StringConstraints(pattern=r"^[^-\s][^\s]*$",
                                        min_length=1, max_length=40)]

# 설정에서 온 **자유 문자열**이 자식 argparse 에 플래그로 읽히지 않는 모양.
# `Nick` 과 글자 그대로 같은 제약이지만 이름을 따로 둔다 — 뜻이 다른 두 값이 한 타입을
# 공유하면 한쪽 규칙을 고칠 때 다른 쪽이 소리 없이 따라 바뀐다(`BULSAJA_KINDS` 와
# `SINGLETON_KINDS` 를 합치지 않는 것과 같은 규율).
# 지금 쓰는 곳은 어휘군 버전(`2026-09-21`)이다. `workspace.toml` 에서 오므로 클라이언트가
# 못 만지지만, 값이 `--force` 모양이면 **리스트 argv 라도** 자식의 파서가 옵션으로 읽는다 —
# 셸을 안 거치는 것과 파서를 안 거치는 것은 다르다(T-3-13 / T-4-17).
PlainArg = Annotated[str, StringConstraints(pattern=r"^[^-\s][^\s]*$",
                                            min_length=1, max_length=40)]


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


class BulsajaArgv(BaseModel):
    """불사자 CLI 호출 한 번을 표현하는 모델. `AdsArgv` 와 **같은 파일**에 둔다.

    `AdsArgv` 를 재사용하지 않는 이유: 저쪽은 `run_ads.py` 전용이고 플래그 집합이
    겹치는 게 하나도 없다. 그렇다고 다른 파일로 빼면 "조립은 한 곳" 이 깨진다 —
    `test_argv.py` 의 마지막 두 테스트가 웹앱 런타임 전체를 훑어 그걸 기계로 집행한다.

    스크립트는 `subcommand` 로 고른다:
      · `index`           → `ss_index_build.py`
      · `profile`/`scan`  → `bulsaja_scan.py` (같은 스크립트의 두 모드).
        `profile` 은 `--profile-only` 를 붙인다 — `detail_batch.py` 의
        `--submit-only`/`--poll-only` 와 같은 관용구다.

    `min_interval`·`retry_after`·`batch_size`·`expect_nick` 에 **기본값이 없다.**
    호출부(`jobs._build_argv`)가 `settings.cfg()` 로 읽어 넘긴다. 기본값을 모델이나
    CLI 에 두면 `workspace.toml` 을 고쳐도 동작이 안 바뀌는 **가짜 설정**이 된다
    (T-1-12 와 같은 부류).
    """

    subcommand: Literal["profile", "index", "scan"]
    db: Path                 # --db          잡 레지스트리(=`ss_index` 가 사는 파일)
    out: Path                # --out         산출물. **profile 모드에선 안 붙인다**
    profile_out: Path        # --profile-out 세 모드 공통. 자식이 계정 확인 결과를 갱신한다
    expect_nick: Nick        # --expect-nick ENG-08 — 자식이 스스로 한 번 더 확인한다
    min_interval: float      # --min-interval
    retry_after: int         # --retry-after
    batch_size: int          # --batch-size
    run_dir: str | None = None    # --run-dir  (scan 전용)
    groups: Path | None = None    # --groups   (index 전용, 사실상 필수 — 아래 주석)
    targets: Path | None = None   # --targets  (scan 전용, 사실상 필수 — 아래 주석)
    limit: int = 0                # --limit    (0 이면 플래그 자체를 안 붙인다)
    # `AdsArgv.prefix` 와 같은 규약의 `caffeinate -i` 자리 (ENG-06).
    # **인덱스 잡이 이걸 실제로 쓰는 첫 자리다** — 3시간 32분짜리 폴링을 노트북에서
    # 돌리는데 맥북 idle sleep 이 그걸 끊는다. `man caffeinate` 기준 utility 를 지정하면
    # 그 프로세스 수명 동안만 assertion 이 유지되므로 따로 해제할 일이 없다.
    prefix: list[str] = []

    def build(self) -> list[str]:
        """argv 리스트. 셸을 거치지 않으므로 따옴표·이스케이프가 필요 없다."""
        스크립트 = SS_INDEX_BUILD if self.subcommand == "index" else BULSAJA_SCAN
        av: list[str] = [*self.prefix, str(PY_CLI), str(스크립트)]

        if self.subcommand == "profile":
            av += ["--profile-only"]

        # 경로는 전부 `str()` 로 못박는다 — `Path` 를 두면 jobs 테이블의 argv 컬럼
        # (JSON 배열) 직렬화가 터진다 (`AdsArgv.build()` 와 같은 이유).
        av += ["--db", str(self.db)]
        if self.subcommand != "profile":
            # 계정 확인에는 산출물이 없다. 자식은 `--profile-out` 만 갱신한다.
            av += ["--out", str(self.out)]
        av += ["--profile-out", str(self.profile_out)]
        av += ["--expect-nick", self.expect_nick]
        av += ["--min-interval", str(self.min_interval)]
        av += ["--retry-after", str(self.retry_after)]
        av += ["--batch-size", str(self.batch_size)]

        if self.run_dir:
            av += ["--run-dir", self.run_dir]

        # **`groups` 가 None 이면 `--groups` 를 안 붙이는데, 그 상태로 인덱스를 돌리면
        # 전 그룹(실측 75,335건 · 5시간 39분)이다.** 그래서 여기서 터뜨리지 않고
        # `jobs._build_argv` 가 **먼저** ValueError 를 던진다 — 빈 값이 '전량' 으로
        # 해석되는 경로를 막는 자리는 한 곳이어야 한다(`revert_only` 와 같은 모양).
        # 조립 단계에서도 터뜨리면 같은 규칙이 두 곳이 되고, 둘이 어긋나면 어느 쪽이
        # 진짜 가드인지 모르게 된다.
        if self.groups:
            av += ["--groups", str(self.groups)]
        if self.targets:
            av += ["--targets", str(self.targets)]

        # 0 은 "상한 없음" 이다. 플래그를 붙여 `--limit 0` 을 넘기면 자식이 그걸
        # "0건만 처리" 로 읽을 수도 있어서, 빈 리스트 규율과 같이 **아예 안 붙인다.**
        if self.limit:
            av += ["--limit", str(self.limit)]

        return av


class BannerArgv(BaseModel):
    """`banner_scan.py` 호출 한 번을 표현하는 모델 (Phase 4 / BANNER-01).

    `AdsArgv`·`BulsajaArgv` 와 **같은 파일**에 둔다. 다른 파일로 빼면 "조립은 한 곳" 이
    깨지고, `test_argv.py` 의 트리 순회 가드가 지키는 주장이 통째로 헐거워진다.

    **임계값·리비전·워커 수·어휘군 버전에 기본값이 없다.** 호출부(`jobs._build_argv`)가
    `settings.cfg()` 로 읽어 넘긴다 — `BulsajaArgv` 가 세운 규율 그대로다. 기본값을
    모델이나 CLI 에 두면 `workspace.toml` 을 고쳐도 동작이 안 바뀌는 **가짜 설정**이
    된다(T-1-12). 여기엔 한 겹 더 있다: 넘긴 값이 그대로 산출물의 `판정규칙` 블록에
    찍히므로, 모델 기본값으로 때우면 **"무슨 규칙으로 판정했나" 의 출처가 둘**이 되고
    회차 간 비교가 거짓말이 된다(D-10 이 경고한 바로 그 상황).

    플래그 이름은 04-03 이 확정한 CLI 계약 그대로다. 필수 5개(`--join`·`--out`·
    `--run-dir`·`--cache`·`--thumbs`)가 빠지면 자식이 **exit 2** 로 거부한다 — 그래서
    전부 `| None` 이 아닌 필수 필드다.

    `--keep-runs` 에 0 을 넘기지 마라. 자식이 그걸 "캐시 전량 삭제" 가 아니라 **오류**로
    보고 exit 2 한다(의도된 가드). 막는 자리는 CLI 한 곳이다 — 여기에 같은 규칙을 또 두면
    둘이 어긋났을 때 어느 쪽이 진짜 가드인지 모르게 된다(`--groups` 와 같은 판단).
    """

    join: Path               # --join       직전 성공 bulsaja_scan 의 조인 산출물
    out: Path                # --out        배너 판정 산출물 JSON
    run_dir: str             # --run-dir    회차 이름 (캐시·썸네일 하위 디렉터리)
    cache: Path              # --cache      원본 이미지 캐시 **루트** (회차 하위는 자식이 만든다)
    thumbs: Path             # --thumbs     썸네일 **루트**
    workers: int             # --workers
    vision_revision: int     # --vision-revision  (D-10 — 박는 것이 요점이다)
    blank_ar: float          # --blank-ar         무내용 장 규칙. **배너 판정이 아니다**
    blank_short_px: int      # --blank-short-px   위와 한 쌍
    skip_min_keep: int       # --skip-min-keep    D-07
    skip_max_removal: float  # --skip-max-removal D-08
    lexicon_version: PlainArg  # --lexicon-version 산출물 `판정규칙` 에 찍을 표기
    keep_runs: int           # --keep-runs  남길 원본 캐시 회차 수 (회차당 약 271MB)
    # ── 비전 2차 판정 (04-09 계약 / D-22) ── 전부 기본값 없음. 위 규율 그대로다.
    # `--vision2-estimate` 는 CLI 전용(사람이 터미널에서 견적만 볼 때)이라 여기 없다.
    vision2_enabled: bool      # --vision2-enabled on|off
    vision2_model: PlainArg    # --vision2-model    요청 모델 (응답 모델은 산출물에 따로 찍힌다)
    vision2_prompt: PlainArg   # --vision2-prompt   지시문 판. 스크립트 상수와 다르면 자식이 exit 5
    # --vision2-key-file  🔴 **경로만** 싣는다. 이 argv 는 `jobs.argv` 컬럼에 JSON 으로
    # 영구 저장된다(감사·재현) — 키 값이 들어가면 영구 유출이다(T-4-40).
    # 웹앱은 이 파일을 **열지 않는다.** 여는 건 CLI 자식 한 곳뿐이다.
    vision2_key_file: Path
    vision2_timeout: float     # --vision2-timeout  호출 1회 타임아웃(초)
    vision2_max_calls: int     # --vision2-max-calls 승인 상한. 0 = 유료 호출 미승인(초과 시 exit 5)
    vision2_interval: float    # --vision2-interval 호출 사이 쉬는 초
    # `AdsArgv.prefix`·`BulsajaArgv.prefix` 와 같은 규약의 `caffeinate -i` 자리 (ENG-06).
    # **무엇에 붙일지는 잡 종류가 정한다** — `jobs._수면방지_프리픽스` 가 그 판단을 들고 있다.
    prefix: list[str] = []

    def build(self) -> list[str]:
        """argv 리스트. 셸을 거치지 않으므로 따옴표·이스케이프가 필요 없다."""
        av: list[str] = [*self.prefix, str(PY_CLI), str(BANNER_SCAN)]

        # 경로는 전부 `str()` 로 못박는다 — `Path` 를 두면 jobs 테이블의 argv 컬럼
        # (JSON 배열) 직렬화가 터진다 (`AdsArgv.build()` 와 같은 이유).
        av += ["--join", str(self.join)]
        av += ["--out", str(self.out)]
        av += ["--run-dir", self.run_dir]
        av += ["--cache", str(self.cache)]
        av += ["--thumbs", str(self.thumbs)]

        # 숫자도 `str()` 이다. 같은 이유(JSON 배열에 int 가 섞이면 argv 가 아니다).
        # **조건부로 붙이지 않는다** — 전부 언제나 붙인다. 하나라도 빠지면 자식이
        # 자기 폴백 기본값으로 돌면서 산출물 `판정규칙` 에는 그 폴백을 찍는데,
        # 그건 `workspace.toml` 이 말하는 값과 다를 수 있다(S-4 드리프트가 조용히 산다).
        av += ["--workers", str(self.workers)]
        av += ["--vision-revision", str(self.vision_revision)]
        av += ["--blank-ar", str(self.blank_ar)]
        av += ["--blank-short-px", str(self.blank_short_px)]
        av += ["--skip-min-keep", str(self.skip_min_keep)]
        av += ["--skip-max-removal", str(self.skip_max_removal)]
        av += ["--lexicon-version", self.lexicon_version]
        av += ["--keep-runs", str(self.keep_runs)]

        # 비전 2차 7개도 **조건 없이** 붙인다 — 꺼짐도 `off` 로 명시한다. 빠지면 자식이
        # 자기 폴백으로 돌면서 산출물 `판정규칙.2차판정` 에 그 폴백을 찍는다(S-4 드리프트).
        av += ["--vision2-enabled", "on" if self.vision2_enabled else "off"]
        av += ["--vision2-model", self.vision2_model]
        av += ["--vision2-prompt", self.vision2_prompt]
        av += ["--vision2-key-file", str(self.vision2_key_file)]
        av += ["--vision2-timeout", str(self.vision2_timeout)]
        av += ["--vision2-max-calls", str(self.vision2_max_calls)]
        av += ["--vision2-interval", str(self.vision2_interval)]

        return av


class DetailArgv(BaseModel):
    """`detail_batch.py --inputs` 호출 한 번을 표현하는 모델 (Phase 5 / DETAIL-01·05).

    `BannerArgv` 와 같은 파일에 둔다 — 조립은 한 곳이다(`test_argv.py` 트리 가드).

    세 모드가 **한 모델**이다. 같은 CLI 의 세 모드(`--estimate-only` / 접수 / `--poll-only`)라
    공통 플래그(`--run-dir` · `--inputs` · `--done-tag` · `--expect-nick` · 폴링 두 개)가
    같고, 모델을 셋으로 쪼개면 공통 플래그 규칙이 셋으로 갈라진다.

    **기본값이 없다** — 폴링 상한·간격·기작업 태그·기대 닉네임은 호출부
    (`jobs._build_argv`)가 `settings.cfg()` 로 읽어 넘긴다(T-1-12 가짜 설정 방지).
    화질·장수 플래그는 **아예 없다**(D-11) — CLI 기본(일반화질 · 입력 장수 그대로)만 탄다.
    """

    mode: Literal["estimate", "submit", "poll"]
    run_dir: Path            # --run-dir   detail_<견적잡id>/ — detail_status.json 이 여기 산다
    inputs: Path             # --inputs    웹앱이 관문을 통과시킨 대상 파일
    done_tags: list[PlainArg]  # --done-tag (반복) D-12 기작업 태그
    expect_nick: Nick        # --expect-nick 자식이 계정을 한 번 더 확인한다(exit 4)
    max_poll_min: int        # --max-poll-min
    poll_interval: int       # --poll-interval
    estimate_out: Path | None = None   # estimate 전용
    summary_out: Path | None = None    # submit/poll 전용
    max_credits: int | None = None     # submit 전용 — 견적이 준 상한(exit 5)
    # `caffeinate -i` 자리. 무엇에 붙일지는 `jobs._수면방지_프리픽스` 가 정한다.
    prefix: list[str] = []

    def build(self) -> list[str]:
        """argv 리스트. 셸을 거치지 않으므로 따옴표·이스케이프가 필요 없다."""
        # 태그 0개면 CLI 가 exit 2 로 거부하지만, 조립에서 먼저 막는다 — 기작업 판정 없이
        # 접수되는 길은 크레딧 이중 지불로 이어진다(D-12 절대조건).
        if not self.done_tags:
            raise ValueError("기작업 태그(done_tags)가 비었다 — 기작업 판정 없이 상세 잡을 못 띄운다")

        av: list[str] = [*self.prefix, str(PY_CLI), str(DETAIL_BATCH)]
        av += ["--run-dir", str(self.run_dir)]
        av += ["--inputs", str(self.inputs)]
        for 태그 in self.done_tags:
            av += ["--done-tag", 태그]
        av += ["--expect-nick", self.expect_nick]
        av += ["--max-poll-min", str(self.max_poll_min)]
        av += ["--poll-interval", str(self.poll_interval)]

        if self.mode == "estimate":
            if self.estimate_out is None:
                raise ValueError("견적 모드에는 estimate_out 이 필요하다")
            av += ["--estimate-only", "--estimate-out", str(self.estimate_out)]
        else:
            if self.summary_out is None:
                raise ValueError("접수·이어서 확인 모드에는 summary_out 이 필요하다")
            if self.mode == "submit":
                if self.max_credits is None:
                    raise ValueError("접수 모드에는 max_credits 가 필요하다 — 상한 없는 접수는 없다")
                av += ["--max-credits", str(self.max_credits)]
            else:
                av += ["--poll-only"]
            av += ["--summary-out", str(self.summary_out)]
        return av
