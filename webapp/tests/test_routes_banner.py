#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""검수 화면의 서버 절반 — 라벨 저장소(`banner_store.py`)와 라우트(`routes/banner.py`).

**이 페이즈에서 새로 생기는 보안 표면이 전부 여기 있다.** 디스크의 271MB 캐시에서 파생된
썸네일을 되서빙하고, 사람 라벨을 받아 DB 에 쓴다. 그래서 이 파일이 겨누는 것은 기능이
아니라 **경계**다:

  T-4-03  `GET /banner/review` 가 서버 상태를 한 글자도 안 바꾼다
          (GET 무부작용이 `security.guard` 의 Origin 방어를 성립시키는 전제다)
  T-4-04  썸네일 라우트가 파일명을 받지 않는다 — 경로 탈출이 **구조적으로** 불가능하다
  T-4-05  라벨 기록이 POST 전용이고 Origin + 부팅 토큰을 탄다
  D-09    사람 판단 큐를 만들지 않는다 — 상태값도 엔드포인트도 없다

**`엿듣기` 류의 픽스처를 쓰지 않는다.** `test_routes_jobs.py` 의 그 픽스처는 `create_job`
을 가로채 `kind` 를 바꿔치기하는데, 그러면 검증하려던 가드가 통째로 우회된다
(04-05-SUMMARY 이탈 5). 여기서 가짜로 바꾸는 것은 **가장 바깥의 부작용**(산출물 파일 위치를
가리키는 잡 레코드) 하나뿐이고, 라우트·저장소·순수층은 전부 진짜가 돈다.
"""
import json
import sqlite3

import pytest

from webapp import banner, banner_store, jobs, paths, security, settings

# ── 픽스처 ──────────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """잡 DB 를 tmp 로 돌리되 **`init_db()` 는 부르지 않는다**.

    파일이 없는 상태를 그대로 쓰는 테스트가 있기 때문이다 — 읽기 경로가 파일을
    만들지 않는다는 것이 `banner_store` 의 핵심 규율이고, 픽스처가 미리 만들어 버리면
    그 테스트는 아무것도 증명하지 못한다. 필요한 테스트가 직접 `jobs.init_db()` 를 부른다.
    """
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "webapp.db"))
    monkeypatch.setattr(settings, "JOB_LOG_DIR", str(tmp_path / "logs"))
    return tmp_path / "webapp.db"


# ── 1. 라벨 저장소 (Task 1) ─────────────────────────────────────────────────


def test_DB_파일이_없으면_읽기가_비고_파일을_만들지_않는다(tmp_db):
    """읽기 경로가 파일을 만들면 안 된다 (`bulsaja_index.lookup` 규율).

    만들면 두 가지가 동시에 깨진다: ① 스키마 없는 빈 파일이 생겨 다음 `init_db()`
    전까지 모든 쓰기가 `OperationalError` ② "아직 아무것도 안 돌렸다" 와 "라벨이 0건이다"
    가 파일 존재 여부로도 구분이 안 된다.
    """
    assert not tmp_db.exists()
    assert banner_store.라벨읽기("zz회차") == {}
    assert banner_store.확인읽기("zz회차") == set()
    assert not tmp_db.exists(), "읽기가 DB 파일을 만들었다"


def test_같은_장에_두_번_찍으면_최신이_이긴다(tmp_db):
    """사람이 눌렀다 고쳐 누르는 게 정상이다 — 누적하면 분모가 두 번 세어진다."""
    jobs.init_db()
    banner_store.라벨기록("zz회차", "tb-1", "zz01", 3, banner.배너)
    banner_store.라벨기록("zz회차", "tb-1", "zz01", 3, banner.제품)

    assert banner_store.라벨읽기("zz회차") == {"tb-1": {3: banner.제품}}

    cx = sqlite3.connect(tmp_db)
    try:
        수 = cx.execute("SELECT COUNT(*) FROM banner_label").fetchone()[0]
    finally:
        cx.close()
    assert 수 == 1, f"같은 장에 {수}행이 쌓였다 — 기본키가 안 먹는다"


def test_라벨읽기_모양이_게이트집계_입력과_같다(tmp_db):
    """`{상품키: {순번: 판정}}`. 이 모양이 어긋나면 `게이트집계` 가 라벨을 통째로 놓친다.

    놓친 라벨은 예외가 아니라 **"기계 판정에 동의"** 로 읽힌다 — 조용한 미탐 0% 다.
    그래서 모양만 보지 않고 `banner.게이트집계` 에 실제로 넣어 본다.
    """
    jobs.init_db()
    banner_store.라벨기록("zz회차", "tb-1", "zz01", 0, banner.배너)
    banner_store.라벨기록("zz회차", "tb-1", "zz01", 1, banner.제품)
    banner_store.라벨기록("zz회차", "tb-2", "zz02", 0, banner.무내용)
    banner_store.확인기록("zz회차", "tb-1")

    라벨 = banner_store.라벨읽기("zz회차")
    assert 라벨 == {"tb-1": {0: banner.배너, 1: banner.제품},
                  "tb-2": {0: banner.무내용}}
    assert banner_store.확인읽기("zz회차") == {"tb-1"}

    산출물 = {"상품": [
        {"타오바오상품번호": "tb-1", "장": [
            {"순번": 0, "판정": banner.제품},      # 사람이 배너로 뒤집었다 → 미탐 1
            {"순번": 1, "판정": banner.제품},
        ]},
        {"타오바오상품번호": "tb-2", "장": [{"순번": 0, "판정": banner.제품}]},
    ]}
    집계 = banner.게이트집계(산출물, 라벨, banner_store.확인읽기("zz회차"))
    assert 집계["미탐"] == 1, "라벨이 게이트집계에 안 닿았다"
    assert 집계["미검수상품"] == 1 and 집계["게이트통과"] is False


def test_회차가_섞이지_않는다(tmp_db):
    """`run_dir` 이 키의 첫 칸이다. 섞이면 지난 회차 라벨이 이번 게이트를 연다."""
    jobs.init_db()
    banner_store.라벨기록("zz회차A", "tb-1", "zz01", 0, banner.배너)
    banner_store.확인기록("zz회차A", "tb-1")

    assert banner_store.라벨읽기("zz회차B") == {}
    assert banner_store.확인읽기("zz회차B") == set()


def test_빈_run_dir_은_예외다(tmp_db):
    """회차 없이 묶으면 전 회차가 한 덩어리가 된다 — 빈 값이 '전량'이 되는 경로다."""
    jobs.init_db()
    for 부르기 in (lambda: banner_store.라벨읽기(""),
                 lambda: banner_store.확인읽기(""),
                 lambda: banner_store.라벨기록("", "tb-1", "zz01", 0, banner.배너),
                 lambda: banner_store.확인기록("", "tb-1")):
        with pytest.raises(ValueError):
            부르기()


def test_사람판정_허용값_밖은_저장소에서도_막힌다(tmp_db):
    """라우트의 `Literal` 이 1차선이고 여기가 2차선이다 — DB 에 아무 글자나 들어가면
    `게이트집계` 가 예외로 터지는데, 그때는 이미 사람의 클릭이 버려진 뒤다."""
    jobs.init_db()
    with pytest.raises(ValueError):
        banner_store.라벨기록("zz회차", "tb-1", "zz01", 0, banner.미판정)


def test_테이블이_없으면_조용히_비지_않는다(tmp_db):
    """스키마가 없는 것과 라벨이 0건인 것은 **다른 사실**이다.

    DB 파일은 있는데 테이블이 없으면 `OperationalError` 가 올라가야 한다 — 라우트가
    "서버를 한 번 재시작해라" 로 번역할 수 있는 유일한 신호다. `{}` 로 접으면
    사람이 아무리 클릭해도 저장이 안 되는데 화면은 멀쩡해 보인다.
    """
    tmp_db.parent.mkdir(parents=True, exist_ok=True)
    cx = sqlite3.connect(tmp_db)     # 빈 파일만 만든다 — 스키마 없음
    cx.close()
    assert tmp_db.is_file()

    with pytest.raises(sqlite3.OperationalError):
        banner_store.라벨읽기("zz회차")
    with pytest.raises(sqlite3.OperationalError):
        banner_store.라벨기록("zz회차", "tb-1", "zz01", 0, banner.배너)


def test_저장소는_스키마를_만들지_않는다():
    """`banner_store.py` 에 스키마를 바꾸는 문장이 0건 (T-4-23).

    **스키마 정본은 `jobs.DDL` 하나다.** 여기서 테이블을 만들면 컬럼이 갈라지는 날
    어느 쪽이 맞는지 아무도 모르게 되고, `test_jobs.py` 의 스키마 가드가 감시하는 범위
    밖에서 테이블이 늘어난다.

    금지 낱말을 이 파일에 글자로 남기지 않으려고 런타임에 조립한다
    (`test_argv.py:9-14` 규율 — 가드가 감시하는 문자열을 테스트가 들고 있으면
    "테스트에는 있어도 된다" 는 예외가 생기고 그 예외가 언젠가 진짜 코드로 자란다).
    """
    소스 = open(banner_store.__file__, encoding="utf-8").read()
    for 금지 in ("CRE" + "ATE", "DR" + "OP", "AL" + "TER"):
        assert 금지 not in 소스, f"banner_store.py 에 '{금지}' 가 있다 — DDL 정본은 jobs.py 다"
    assert "from webapp import " + "jobs" not in 소스, \
        "banner_store.py 가 jobs 를 import 한다 — import 그래프를 엉키게 하지 마라"
