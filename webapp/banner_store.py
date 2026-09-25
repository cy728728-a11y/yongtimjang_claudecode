#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""사람 라벨 저장소 — `banner_label` · `banner_confirm` 을 읽고 쓴다 (BANNER-04 / BANNER-05).

**이 웹앱에서 사람의 시간이 들어간 유일한 기록이다.** 기계 판정은 `banner_scan.py` 를
다시 돌리면 몇 분에 다시 나오는 투영이지만, 사람이 전 장을 훑고 뒤집은 라벨은 재생성이
불가능하다 — 재생성이 공짜가 아니면 그건 캐시가 아니라 **기록**이다(`jobs.DDL` 의 판별
기준을 그대로 쓴다). 그래서 SQLite 에 남고, 그래서 이 모듈이 따로 있다.

읽기와 쓰기를 **커넥션 수준에서 가른다**:
  · 읽기(`라벨읽기`·`확인읽기`) → `_ro_conn()` (`mode=ro` URI). 파일이 없으면 **만들지 않는다**
  · 쓰기(`라벨기록`·`확인기록`) → `_conn()` + `INSERT OR REPLACE`

`bulsaja_index.py`(읽기 전용 모듈)와 `jobs.py`(쓰기 모듈)의 관용구를 합친 것이고,
둘 중 어느 쪽 규율도 느슨하게 만들지 않았다.

## 이 모듈이 절대 하지 않는 것

  ① **기계 판정(배너/제품/무내용)을 복사하지 않는다.** 판정의 정본은 `banner_scan.py` 가
     쓴 산출물 JSON 하나다(S-1). 복사하는 순간 진실이 둘이 되고, 어휘군을 고쳐 다시 돌린
     회차에서 화면과 산출물이 다른 말을 한다. 여기 적히는 `사람판정` 은 **사람이 화면에서
     뒤집은 것 하나뿐**이다.
  ② **DDL 을 하지 않는다.** 테이블을 만들거나 고치거나 지우는 문장이 이 파일에 0건이고,
     그 사실을 `test_routes_banner.py` 의 grep 가드가 집행한다 — 그래서 그 낱말들을
     주석에도 글자로 남기지 않는다(`test_argv.py:9-14` 의 규율). 스키마 정본은
     `jobs.DDL` 이고 `init_db()` 가 만든다. 테이블이 없으면 `sqlite3.OperationalError` 가
     그대로 올라가고, 라우트가 그것을 "라벨 테이블이 없다 — 서버를 한 번 재시작해라" 로
     번역한다. `ss_index_build.py` 가 스키마를 만들지 않고 확인만 하고 죽는 것과 같은 선이다.
  ③ **네트워크·이미지 라이브러리를 만지지 않는다** (D-19). `webapp/**` 트리 가드가 집행한다.
  ④ **라벨과 확인 표시를 한 테이블에 합치지 않는다.** "이 장을 뒤집었다"(`banner_label`)와
     "이 줄을 다 봤다"(`banner_confirm`)는 **다른 사실**이다. 합치면 확인 표시가 라벨로
     둔갑해 `banner.게이트집계` 의 분모가 조용히 틀어진다.
"""
import sqlite3
from datetime import datetime
from pathlib import Path

from webapp import paths, settings


def db_path() -> Path:
    """라벨이 사는 파일. `jobs.db_path()` 와 **같은 파일**이다.

    `jobs` 를 import 하지 않고 세 줄을 복제한다 — `bulsaja_index.db_path()` 와 같은 이유다.
    이 모듈은 라우트에서 불리고 라우트는 `jobs` 도 부르는데, 여기서 `jobs` 를 들이면
    import 그래프가 한 겹 더 엉킨다(그리고 `jobs` 는 이미 `bulsaja_index` 를 부른다).
    계산이 세 줄뿐이라 복제가 싸다 — 대신 `settings.DB_PATH` 라는 **같은 출처**를 보므로
    둘이 어긋날 길이 없다.
    """
    p = Path(settings.DB_PATH).expanduser()
    return p if p.is_absolute() else paths.repo_root() / p


def _ro_conn() -> sqlite3.Connection:
    """읽기 전용 커넥션. `mode=ro` URI 라 쓰기는 `OperationalError` 로 터진다.

    호출 전에 파일 존재를 확인해야 한다 — `mode=ro` 는 파일이 없으면 열기 자체가 실패한다.
    **그게 의도다: 읽기 경로가 파일을 만들지 않는다.**
    """
    cx = sqlite3.connect(f"file:{db_path()}?mode=ro", uri=True, timeout=5)
    cx.row_factory = sqlite3.Row
    return cx


def _conn() -> sqlite3.Connection:
    """쓰기 커넥션. `timeout=5` 로 잠깐의 경합은 기다린다 (`jobs._conn` 과 같다)."""
    cx = sqlite3.connect(db_path(), timeout=5)
    cx.row_factory = sqlite3.Row
    return cx


def _now() -> str:
    """로컬 시각 + 오프셋. 오프셋을 빼면 서머타임·시차에서 순서가 틀어진다."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


# ── 읽기 ────────────────────────────────────────────────────────────────────

def 라벨읽기(run_dir: str) -> dict:
    """`{상품키: {이미지순번: 사람판정}}`. `banner.게이트집계` 가 그대로 받는 모양이다.

    상품키는 `banner.상품키()` 가 내는 값과 같은 것(타오바오상품번호)이어야 한다 —
    키가 어긋나면 사람이 뒤집은 라벨이 통째로 미아가 되고, 게이트집계는 그걸
    **"기계 판정에 동의"** 로 읽는다. 조용한 미탐 0% 가 그렇게 만들어진다.

    **DB 파일이 없으면 `{}` 이고 만들지 않는다.** 파일이 있어도 못 열면(권한·손상) 역시
    `{}` 다 — 화면이 통째로 500 이 되는 것보다 "아직 라벨이 없다" 로 보이는 쪽이 낫다.
    게이트는 라벨이 없으면 어차피 닫혀 있으므로(미검수상품 > 0) **안전한 쪽으로 떨어진다**.

    ⚠️ 테이블이 없을 때의 `sqlite3.OperationalError` 는 **삼키지 않는다** — 그건
    "라벨이 없다"가 아니라 "스키마가 없다"이고, 사람이 할 일이 다르다(서버 재시작).
    """
    키 = str(run_dir or "").strip()
    if not 키:
        raise ValueError("run_dir 이 비었다 — 회차 없이 라벨을 묶으면 회차가 섞인다")
    if not db_path().is_file():
        return {}
    try:
        cx = _ro_conn()
    except sqlite3.Error:
        return {}
    try:
        행들 = cx.execute(
            "SELECT 타오바오상품번호, 이미지순번, 사람판정 FROM banner_label "
            "WHERE run_dir = ?", (키,)).fetchall()
    finally:
        cx.close()

    나온것: dict = {}
    for r in 행들:
        나온것.setdefault(str(r["타오바오상품번호"]), {})[int(r["이미지순번"])] = r["사람판정"]
    return 나온것


def 확인읽기(run_dir: str) -> set:
    """"이 줄 다 봤다" 를 누른 상품키 집합. `banner.게이트집계` 의 `검수완료` 인자다.

    **`라벨읽기` 와 합치지 않는다** (모듈 docstring ④). 라벨이 0개인 상품도 "다 봤고
    기계 판정에 전부 동의한다" 일 수 있고, 그게 정상적인 다수다(D-03a).

    파일이 없으면 `set()` 이고 만들지 않는다 — `라벨읽기` 와 같은 규율이다.
    **빈 집합이 "전수 검수 완료" 로 접히지 않는다**: `게이트집계` 가 확인 없는 상품을
    `미검수상품` 으로 세고, 하나라도 있으면 게이트가 안 열린다(D-12).
    """
    키 = str(run_dir or "").strip()
    if not 키:
        raise ValueError("run_dir 이 비었다 — 회차 없이 확인 표시를 묶으면 회차가 섞인다")
    if not db_path().is_file():
        return set()
    try:
        cx = _ro_conn()
    except sqlite3.Error:
        return set()
    try:
        행들 = cx.execute(
            "SELECT 타오바오상품번호 FROM banner_confirm WHERE run_dir = ?", (키,)).fetchall()
    finally:
        cx.close()
    return {str(r["타오바오상품번호"]) for r in 행들}



def 확인시각읽기(run_dir: str) -> dict:
    """`{상품키: 확인시각 ISO}`. Phase 5 관문(`banner.상세입력목록`) 과 검수 화면이 쓴다 (D-02/D-03).

    `확인읽기` 와 같은 규율이다 — 빈 run_dir 은 예외, DB 파일이 없거나 못 열면 `{}` 이고
    파일을 만들지 않는다. 시각을 함께 내는 이유: 재스캔으로 산출물이 새로 나오면
    그 전 확인은 **낡은 확인**이고, 그걸 가르려면 존재 여부가 아니라 시각이 필요하다.
    """
    키 = str(run_dir or "").strip()
    if not 키:
        raise ValueError("run_dir 이 비었다 — 회차 없이 확인 표시를 묶으면 회차가 섞인다")
    if not db_path().is_file():
        return {}
    try:
        cx = _ro_conn()
    except sqlite3.Error:
        return {}
    try:
        행들 = cx.execute(
            "SELECT 타오바오상품번호, 확인시각 FROM banner_confirm WHERE run_dir = ?",
            (키,)).fetchall()
    finally:
        cx.close()
    return {str(r["타오바오상품번호"]): str(r["확인시각"]) for r in 행들}

# ── 쓰기 ────────────────────────────────────────────────────────────────────

def 라벨기록(run_dir: str, 타오바오상품번호: str, 판매자상품코드: str,
          이미지순번: int, 사람판정: str) -> None:
    """장 하나의 사람 판정을 적는다. **같은 장에 다시 찍으면 최신 1건이 이긴다.**

    사람이 눌렀다 고쳐 누르는 게 정상이다 — 누적하면 같은 장이 게이트 분모에 두 번
    들어가고, 뒤집었다가 되돌린 클릭이 영원히 미탐으로 남는다. 그래서
    `INSERT OR REPLACE` 이고 기본키가 `(run_dir, 타오바오상품번호, 이미지순번)` 이다.

    `판매자상품코드` 는 **사람이 앱에서 검색할 때 쓰는 표시값**이지 키가 아니다 —
    물갈이로 재발급되므로 키로 쓰면 다음 회차에서 라벨이 미아가 된다(D-01a).

    값 검증(`사람판정` 화이트리스트·순번 범위)은 **라우트의 Pydantic 이 한다.**
    여기서 다시 검사하지 않는 이유는 관문을 둘로 만들지 않기 위해서다 — 다만
    `사람판정` 만은 `banner.사람판정허용값` 으로 한 번 더 본다. DB 에 아무 글자나
    들어가면 `게이트집계` 가 예외로 터지는데, 그때는 이미 사람의 클릭이 버려진 뒤다.
    """
    from webapp import banner      # 지연 import — 순수 모듈이라 순환은 없지만 결이 같다

    키 = str(run_dir or "").strip()
    if not 키:
        raise ValueError("run_dir 이 비었다 — 회차 없이 라벨을 적으면 회차가 섞인다")
    상품 = str(타오바오상품번호 or "").strip()
    if not 상품:
        raise ValueError("타오바오상품번호가 비었다 — 빈 키로 묶으면 전 상품이 한 덩어리가 된다")
    if 사람판정 not in banner.사람판정허용값:
        raise ValueError(f"사람판정 값이 허용값 {banner.사람판정허용값} 밖이다: {사람판정!r}")
    순번 = int(이미지순번)
    if 순번 < 0:
        raise ValueError(f"이미지순번이 음수다: {순번}")

    cx = _conn()
    try:
        cx.execute(
            "INSERT OR REPLACE INTO banner_label "
            "(run_dir, 타오바오상품번호, 판매자상품코드, 이미지순번, 사람판정, 기록시각) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (키, 상품, str(판매자상품코드 or ""), 순번, 사람판정, _now()))
        cx.commit()
    finally:
        cx.close()


def 확인기록(run_dir: str, 타오바오상품번호: str) -> None:
    """"이 줄 다 봤다" 를 적는다. 같은 상품을 또 눌러도 최신 1건이 이긴다.

    **되돌리는 길을 여기 두지 않는다.** "다 봤다" 를 취소하는 버튼은 D-09 가 금지한
    상태 관리의 입구다 — 다시 보면 그만이고, 라벨을 고치면 집계가 따라 움직인다.
    """
    키 = str(run_dir or "").strip()
    if not 키:
        raise ValueError("run_dir 이 비었다 — 회차 없이 확인 표시를 적으면 회차가 섞인다")
    상품 = str(타오바오상품번호 or "").strip()
    if not 상품:
        raise ValueError("타오바오상품번호가 비었다 — 빈 키로 묶으면 전 상품이 한 덩어리가 된다")

    cx = _conn()
    try:
        cx.execute(
            "INSERT OR REPLACE INTO banner_confirm "
            "(run_dir, 타오바오상품번호, 확인시각) VALUES (?, ?, ?)",
            (키, 상품, _now()))
        cx.commit()
    finally:
        cx.close()
