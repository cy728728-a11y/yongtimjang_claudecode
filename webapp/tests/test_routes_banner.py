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


# ── 2. 라우트 픽스처 ────────────────────────────────────────────────────────


def _산출물(썸네일="0000_00.webp"):
    """배너 스캔 산출물 최소본. `banner_scan.집계내기`·`상품골격` 의 키를 그대로 쓴다."""
    return {
        "소요초": 252.4,
        "판정규칙": {"어휘군버전": "2026-09-21", "vision_revision": 3},
        "게이트통과": False,
        "집계": {"상품": 1, "장": 2, "판정완료": 2, "미판정": 0,
               banner.배너: 1, banner.제품: 1, banner.무내용: 0, "스킵상품": 0},
        "상품": [{
            "판매자상품코드": "zz01", "불사자코드": "zzb01", "타오바오상품번호": "tb-1",
            "상세상태": "중국어원본", "장수": 2, "스킵사유": None, "사유": None,
            "제거율": 0.5,
            "제품이미지": [{"순번": 1, "url": "https://zzcdn.example/b.jpg"}],
            "장": [
                {"순번": 0, "url": "https://zzcdn.example/a.jpg", "w": 800, "h": 900,
                 "판정": banner.배너, "사유": "어휘군:공장직판", "썸네일": 썸네일},
                {"순번": 1, "url": "https://zzcdn.example/b.jpg", "w": 800, "h": 900,
                 "판정": banner.제품, "사유": None, "썸네일": None},
            ],
        }],
    }


@pytest.fixture
def 화면(client, tmp_run_dir, tmp_path, monkeypatch):
    """쿠키까지 붙인 클라이언트 + tmp 회차 + tmp 잡 DB + 라벨 스키마.

    `jobs.init_db()` 가 **반드시 먼저** 돌아야 한다 — `banner_label`·`banner_confirm`
    DDL 이 거기 있다(04-05). 안 돌리면 라벨 POST 가 전부 500 이고, 그 500 을
    "가드가 막았다" 로 오독하게 된다.
    """
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "webapp.db"))
    monkeypatch.setattr(settings, "JOB_LOG_DIR", str(tmp_path / "logs"))
    jobs.init_db()
    client.cookies.set(security.COOKIE_NAME, security.BOOT_TOKEN)
    return client


@pytest.fixture
def 돌린척(tmp_run_dir, tmp_path):
    """배너 스캔이 **성공한 것처럼** 레지스트리에 기록하고 산출물 파일을 깐다.

    `create_job` 을 가로채지 않는다. 그건 `kind` 를 바꿔치기해 가드를 통째로 우회하는
    픽스처가 되고(04-05-SUMMARY 이탈 5), 여기서는 `latest_done("banner_scan", ...)`
    자체가 검증 대상이라 그 우회가 테스트를 무의미하게 만든다.

    대신 **가장 바깥의 부작용 하나**(자식이 실제로 돌았다는 사실)만 가짜로 만든다 —
    잡 행을 직접 넣고 산출물 JSON 을 디스크에 둔다. 라우트가 타는 경로
    (`latest_done` → `result_path` → JSON 읽기 → 투영)는 전부 진짜다.
    """
    def _깔기(문서=None, 회차=None):
        회차 = 회차 or tmp_run_dir.name
        web = tmp_run_dir / "web"
        web.mkdir(parents=True, exist_ok=True)
        out = web / "banner_zz.json"
        out.write_text(json.dumps(문서 if 문서 is not None else _산출물(),
                                  ensure_ascii=False), encoding="utf-8")
        cx = jobs._conn()
        try:
            cx.execute(
                "INSERT INTO jobs (id, kind, run_dir, argv, status, log_path, "
                "result_path, started_at) VALUES (?,?,?,?,?,?,?,?)",
                ("zzjob-0001", "banner_scan", 회차, "[]", "done",
                 str(tmp_path / "logs" / "zz.log"), str(out), "2026-09-22T10:00:00+09:00"))
            cx.commit()
        finally:
            cx.close()
        return out
    return _깔기


def _행수(db_path, 테이블):
    cx = sqlite3.connect(db_path)
    try:
        return cx.execute(f"SELECT COUNT(*) FROM {테이블}").fetchone()[0]
    finally:
        cx.close()


# ── 3. T-4-03 — GET 이 상태를 안 바꾼다 ─────────────────────────────────────


def test_GET_무부작용(화면, 돌린척, tmp_path, tmp_run_dir):
    """`GET /banner/review` 를 두 번 불러도 DB 행 수·mtime·산출물 mtime 이 불변이다.

    **이게 `security.guard` 의 Origin 방어를 성립시키는 전제다** (T-4-03 / T-1-01b).
    교차 사이트 단순 GET(`<img src>`)에는 Origin 헤더가 없어서, 부수효과가 있는 GET 을
    하나라도 만들면 그 층이 통째로 뚫린다. 여기가 빨개지면 고칠 것은 이 테스트가
    아니라 라우트다.
    """
    산출물 = 돌린척()
    db = tmp_path / "webapp.db"

    전_db = db.stat().st_mtime_ns
    전_산출물 = 산출물.stat().st_mtime_ns
    전_라벨 = _행수(db, "banner_label")
    전_확인 = _행수(db, "banner_confirm")

    for _ in range(2):
        응답 = 화면.get(f"/banner/review?run_dir={tmp_run_dir.name}")
        assert 응답.status_code == 200
        assert "배너 검수" in 응답.text

    assert _행수(db, "banner_label") == 전_라벨 == 0
    assert _행수(db, "banner_confirm") == 전_확인 == 0
    assert db.stat().st_mtime_ns == 전_db, "GET 이 잡 DB 를 건드렸다"
    assert 산출물.stat().st_mtime_ns == 전_산출물, "GET 이 산출물 파일을 건드렸다"


def test_스캔_전에는_실패가_아니다(화면, tmp_run_dir):
    """한 번도 안 돌린 것은 고장이 아니다 (S-3). 사유 배너 없이 "아직 안 돌렸다" 다."""
    응답 = 화면.get(f"/banner/review?run_dir={tmp_run_dir.name}")
    assert 응답.status_code == 200
    assert "아직 배너 스캔을 안 돌렸다" in 응답.text


def test_상품_0건은_사유를_들고_온다(화면, 돌린척, tmp_run_dir):
    """0건은 관측이 아니라 조회 실패일 수 있다 — 빈 화면을 "대상 없음" 으로 읽게 두지 않는다."""
    돌린척({"집계": {}, "상품": []})
    응답 = 화면.get(f"/banner/review?run_dir={tmp_run_dir.name}")
    assert 응답.status_code == 200
    assert "상품이 0건이다" in 응답.text


def test_트레이스백이_화면에_안_실린다(화면, 돌린척, tmp_run_dir, tmp_path):
    """산출물이 깨져도 사유는 한 줄 요약이다 (ASVS V7 / T-4-21)."""
    경로 = 돌린척()
    경로.write_text("{이건 JSON 이 아니다", encoding="utf-8")
    응답 = 화면.get(f"/banner/review?run_dir={tmp_run_dir.name}")
    assert 응답.status_code == 200
    assert "Traceback" not in 응답.text
    assert "JSONDecodeError" in 응답.text and str(tmp_path) not in 응답.text


def test_쿠키_없으면_403(client, tmp_run_dir):
    """읽기 라우트의 유일한 문이다. 썸네일에도 같은 문이 걸린다."""
    client.cookies.clear()
    assert client.get(f"/banner/review?run_dir={tmp_run_dir.name}").status_code == 403
    assert client.get(f"/banner/thumb/{tmp_run_dir.name}/0/0").status_code == 403


# ── 4. T-4-04 — 썸네일 경로 탈출 ────────────────────────────────────────────


def test_경로탈출(화면, 돌린척, tmp_run_dir, tmp_path, monkeypatch):
    """썸네일 라우트는 **파일명을 받지 않는다** — 정수 인덱스만 받는다 (T-4-04).

    경로 탈출이 막히는 게 아니라 **구조적으로 불가능하다.** 그래도 변형을 전부
    쏴 보고, 어느 것도 파일 내용을 흘리지 않는지 확인한다.
    """
    돌린척()
    썸루트 = tmp_path / "thumbs"
    (썸루트 / tmp_run_dir.name).mkdir(parents=True)
    (썸루트 / tmp_run_dir.name / "0000_00.webp").write_bytes(b"RIFFzzWEBP")
    monkeypatch.setattr(jobs, "banner_dir", lambda 키: 썸루트)

    # 정상 경로가 실제로 200 이어야 한다 — 전부 404 인 서버에서도 아래 단언은 통과한다.
    좋은것 = 화면.get(f"/banner/thumb/{tmp_run_dir.name}/0/0")
    assert 좋은것.status_code == 200 and 좋은것.content == b"RIFFzzWEBP"

    비밀 = tmp_path / "secret.txt"
    비밀.write_text("zz-비밀-내용", encoding="utf-8")

    변형 = [
        f"/banner/thumb/{tmp_run_dir.name}/../../etc/passwd",
        f"/banner/thumb/{tmp_run_dir.name}/%2e%2e%2f%2e%2e%2fetc%2fpasswd",
        f"/banner/thumb/{tmp_run_dir.name}/-1/-1",          # 음수는 파이썬 리스트가 받는다
        f"/banner/thumb/{tmp_run_dir.name}/0/{비밀}",        # 절대경로 문자열
        f"/banner/thumb/{tmp_run_dir.name}/99/0",           # 범위 밖
        "/banner/thumb/../0/0",                             # 회차 자리에 ..
        "/banner/thumb/모르는회차/0/0",                       # 화이트리스트 밖
    ]
    for 길 in 변형:
        응답 = 화면.get(길)
        assert 응답.status_code in (400, 404, 422), f"{길} → {응답.status_code}"
        assert "root:" not in 응답.text
        assert "zz-비밀-내용" not in 응답.text


def test_썸네일이_회차_밖을_가리키면_거부한다(화면, 돌린척, tmp_run_dir, tmp_path, monkeypatch):
    """2층 방어 — 산출물이 파일명 대신 경로를 들고 있어도 열리지 않는다.

    **접두 비교가 아니라 경로 비교다.** `startswith` 로 하면 `thumbs-남의것/` 같은
    형제 디렉터리가 통과한다(`jobs.py:437-444` 의 규율).
    """
    돌린척(_산출물(썸네일="../../secret.txt"))
    썸루트 = tmp_path / "thumbs"
    (썸루트 / tmp_run_dir.name).mkdir(parents=True)
    (tmp_path / "secret.txt").write_text("zz-비밀-내용", encoding="utf-8")
    monkeypatch.setattr(jobs, "banner_dir", lambda 키: 썸루트)

    응답 = 화면.get(f"/banner/thumb/{tmp_run_dir.name}/0/0")
    assert 응답.status_code == 404
    assert "zz-비밀-내용" not in 응답.text


def test_썸네일_없는_장은_404(화면, 돌린척, tmp_run_dir, tmp_path, monkeypatch):
    """미판정·다운로드 실패 장은 썸네일이 `null` 이다. 500 이 아니라 404 다."""
    돌린척()
    monkeypatch.setattr(jobs, "banner_dir", lambda 키: tmp_path / "thumbs")
    assert 화면.get(f"/banner/thumb/{tmp_run_dir.name}/0/1").status_code == 404


# ── 5. T-4-05 — 라벨 쓰기는 POST 전용 ───────────────────────────────────────


def test_라벨_POST_토큰(화면, tmp_path, tmp_run_dir):
    """토큰 없음 403 · 타 사이트 Origin 403 · GET 405 · 허용값 밖 422 (T-4-05).

    전부 **DB 에 한 행도 안 들어간다** — 403 만 확인하면 "거부됐다" 와
    "거부는 됐는데 그 전에 썼다" 를 구분하지 못한다.
    """
    db = tmp_path / "webapp.db"
    몸통 = {"run_dir": tmp_run_dir.name, "타오바오상품번호": "tb-1",
          "판매자상품코드": "zz01", "이미지순번": 0, "사람판정": banner.배너}

    assert 화면.post("/banner/label", json=몸통,
                    headers={"X-CT-Token": "wrong-token"}).status_code == 403
    assert 화면.post("/banner/label", json=몸통,
                    headers={"Origin": "https://evil.com"}).status_code == 403
    assert 화면.get("/banner/label").status_code == 405
    assert 화면.get("/banner/confirm").status_code == 405

    # `사람판정` 화이트리스트 회귀. 자유 문자열이면 DB 에 아무 값이나 들어가
    # `게이트집계` 분모가 조용히 틀어진다 — Literal 이 그 1차선이다.
    assert 화면.post("/banner/label",
                    json=dict(몸통, 사람판정="보" + "류")).status_code == 422
    assert 화면.post("/banner/label", json=dict(몸통, 사람판정=banner.미판정)).status_code == 422
    assert 화면.post("/banner/label", json=dict(몸통, 이미지순번=-1)).status_code == 422
    assert 화면.post("/banner/label",
                    json=dict(몸통, 타오바오상품번호="../../x")).status_code == 422

    assert _행수(db, "banner_label") == 0, "거부된 요청이 DB 에 남았다"


def test_라벨과_확인이_실제로_저장된다(화면, tmp_path, tmp_run_dir):
    """403 만 확인하는 검증은 서버를 뽑아 놔도 통과한다 — 정상 경로를 같이 본다."""
    db = tmp_path / "webapp.db"
    몸통 = {"run_dir": tmp_run_dir.name, "타오바오상품번호": "tb-1",
          "판매자상품코드": "zz01", "이미지순번": 0, "사람판정": banner.배너}

    응답 = 화면.post("/banner/label", json=몸통)
    assert 응답.status_code == 200 and "figure" in 응답.text
    # htmx 폼 인코딩도 받는다 — hx-post 가 JSON 을 안 보낸다.
    assert 화면.post("/banner/confirm",
                    data={"run_dir": tmp_run_dir.name,
                          "타오바오상품번호": "tb-1"}).status_code == 200

    assert _행수(db, "banner_label") == 1
    assert _행수(db, "banner_confirm") == 1
    assert banner_store.라벨읽기(tmp_run_dir.name) == {"tb-1": {0: banner.배너}}
    assert banner_store.확인읽기(tmp_run_dir.name) == {"tb-1"}


def test_라벨_테이블이_없으면_고칠_자리를_말한다(client, tmp_run_dir, tmp_path, monkeypatch):
    """테이블 부재는 400(요청 잘못)이 아니라 500 + "서버를 한 번 재시작해라" 다.

    400 으로 번역하면 사용자가 자기 클릭을 탓하며 계속 누른다 — 실제로 필요한 것은
    `init_db()` 를 한 번 더 태우는 재시작이다.
    """
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "webapp.db"))
    monkeypatch.setattr(settings, "JOB_LOG_DIR", str(tmp_path / "logs"))
    sqlite3.connect(tmp_path / "webapp.db").close()      # 빈 파일 — 스키마 없음
    client.cookies.set(security.COOKIE_NAME, security.BOOT_TOKEN)

    응답 = client.post("/banner/label", json={
        "run_dir": tmp_run_dir.name, "타오바오상품번호": "tb-1",
        "판매자상품코드": "zz01", "이미지순번": 0, "사람판정": banner.배너})
    assert 응답.status_code == 500
    assert "재시작" in 응답.text


# ── 6. D-09 — 사람 판단 큐가 없다 ───────────────────────────────────────────


def test_사람큐_엔드포인트_없음():
    """`routes/banner.py` 에 새 상태값도 큐 경로도 없다 (D-09 / 성공기준 3).

    D-07·D-08 은 "애매하면 사람에게 묻는다" 가 아니라 **"애매하면 그 상품을 건너뛴다"** 다.
    사람이 하는 일은 "뒤집기" 와 "다 봤다" 둘뿐이고 둘 다 즉시 확정된다 —
    중간 상태가 하나라도 생기면 그게 곧 사람 판단 큐다(`minimize-user-queues`).

    금지 문자열을 이 파일에 글자로 남기지 않으려고 런타임에 조립한다.
    """
    from webapp.routes import banner as 라우트

    소스 = open(라우트.__file__, encoding="utf-8").read()
    for 금지 in ("보" + "류", "대" + "기", "검토" + "요청"):
        assert 금지 not in 소스, f"routes/banner.py 에 '{금지}' 가 있다 — 사람 판단 큐다 (D-09)"
    for 큐경로 in ("/qu" + "eue", "/pen" + "ding"):
        assert 큐경로 not in 소스, f"routes/banner.py 에 '{큐경로}' 경로가 있다 (D-09)"

    # 실제로 붙은 경로도 본다 — 소스 문자열만 보면 데코레이터로 붙인 다섯 번째 경로를
    # 놓친다. `app.routes` 가 아니라 라우터를 보는 이유: FastAPI 0.137 부터
    # `app.routes` 가 리스트가 아니라 포함관계 트리라서 `_IncludedRouter` 가 나온다.
    경로들 = sorted(r.path for r in 라우트.router.routes)
    assert 경로들 == ["/banner/confirm", "/banner/label", "/banner/review",
                    "/banner/thumb/{run_dir}/{product_i}/{chap_i}"], 경로들


def test_라우트가_정적마운트도_ended_at_도_안_쓴다():
    """썸네일을 정적 마운트로 대신하면 271MB 원본이 토큰 없이 열린다 (Pitfall 7).

    D-19(이미지 라이브러리 금지)는 `test_argv.py` 의 트리 순회 가드가 이미 집행한다 —
    여기서는 이 페이즈가 새로 만든 유혹 둘만 따로 못박는다.
    """
    from webapp.routes import banner as 라우트

    소스 = open(라우트.__file__, encoding="utf-8").read()
    assert "Static" + "Files" not in 소스
    assert "ended" + "_at" not in 소스, "소요시간은 산출물의 `소요초` 를 읽는다 (S-5)"


def test_템플릿이_표도_safe_도_안_쓴다():
    """행 확장 표로 만들면 100상품 = 100클릭이다 — D-03 의 "훑기" 가 "클릭" 이 된다.

    `| safe` 는 자동 이스케이프를 끄는 필터다. 사유 문자열에 중국어 원문이 섞여 온다.
    """
    from pathlib import Path as _P

    from webapp import main as _main

    소스 = (_P(_main.BASE) / "templates" / "banner_review.html").read_text(encoding="utf-8")
    assert "tabul" + "ator" not in 소스.lower()
    assert "| " + "safe" not in 소스
    assert "토큰 0 · 크레딧 0" in 소스
    assert 'hx-headers=\'{"X-CT-Token": "{{ token }}"}\'' in 소스


# ── 7. D-03a — 전장 노출 (04-07) ────────────────────────────────────────────
#
# **이 절이 이 페이즈의 측정 장치 그 자체다.** 배너로 판정한 장만 깔린 화면은 오탐만
# 잡고 미탐을 구조적으로 증명할 수 없다(D-03a). 그래서 "배너가 보인다" 가 아니라
# **"전장이 보인다"** 를 단언한다 — 배너 수와 같으면 실패다.


def _산출물_여러상품(코드들=("zz01", "zz02"), 장수=(16, 3), 배너들=((0, 5), (1,)),
                스킵들=(None, banner.제거율초과)):
    """상품 여러 건 · 장 여럿. `_산출물()` 은 장이 2개뿐이라 전장을 못 센다.

    **장 수와 배너 수가 다르게** 만드는 것이 요점이다 — 둘이 같으면 "배너만 깔렸다"
    는 버그가 통과한다.
    """
    상품들 = []
    총장 = 총배너 = 0
    for 코드, n, 배너순번, 스킵 in zip(코드들, 장수, 배너들, 스킵들):
        장 = []
        for i in range(n):
            판정 = banner.배너 if i in 배너순번 else banner.제품
            장.append({"순번": i, "url": f"https://zzcdn.example/{코드}-{i}.jpg",
                       "w": 800, "h": 900, "판정": 판정,
                       "사유": ("어휘군:공장직판" if 판정 == banner.배너 else None),
                       "썸네일": f"{코드}_{i:02d}.webp"})
        총장 += n
        총배너 += len(배너순번)
        상품들.append({
            "판매자상품코드": 코드, "불사자코드": "b" + 코드,
            "타오바오상품번호": "tb-" + 코드, "상세상태": "중국어원본",
            "장수": n, "스킵사유": 스킵, "사유": ("제거율 82%" if 스킵 else None),
            "제거율": 0.82 if 스킵 else 0.1, "제품이미지": [], "장": 장,
        })
    return {
        "소요초": 252.4,
        "판정규칙": {"어휘군버전": "2026-09-21", "vision_revision": 3},
        "집계": {"상품": len(상품들), "장": 총장, "판정완료": 총장, "미판정": 0,
               banner.배너: 총배너, banner.제품: 총장 - 총배너,
               banner.무내용: 0, "스킵상품": sum(1 for s in 스킵들 if s)},
        "상품": 상품들,
    }


def test_전장이_다_깔린다(화면, 돌린척, tmp_run_dir):
    """`figure` 개수 == 산출물 `집계.장`. **배너 수와 같으면 실패다** (D-03a).

    판정된 것만 접으면 "기계가 자신있게 틀린" 장을 사람이 볼 기회 자체가 없어진다 —
    그러면 미탐 0% 는 측정한 적 없는 숫자가 된다. 경계선 구간만 더 보여주는 절충안도
    같은 이유로 이미 기각됐다(04-CONTEXT D-03a).

    `data-slot="strip"` 만 센다 — 같은 장이 기준 확인 섹션에도 다시 나오기 때문이다
    (그쪽은 `sample` 이다). 둘을 안 가르면 전장 수가 부풀어 보인다.
    """
    문서 = _산출물_여러상품()
    돌린척(문서)
    본문 = 화면.get(f"/banner/review?run_dir={tmp_run_dir.name}").text

    깔린장 = 본문.count('data-slot="strip"')
    assert 깔린장 == 문서["집계"]["장"] == 19, (
        f"전장 노출이 깨졌다 — figure {깔린장}개 / 산출물 장 {문서['집계']['장']}개. "
        "배너만 깔면 미탐을 구조적으로 못 본다(D-03a)")
    assert 깔린장 != 문서["집계"][banner.배너], "배너 수만큼만 깔렸다 (D-03a)"


def test_스킵_상품도_전장을_깐다(화면, 돌린척, tmp_run_dir):
    """스킵 **판단 자체가 틀렸을 수 있다.** 줄은 흐려지되 전장은 그대로 깔린다 (D-09).

    그리고 못 누르게 막지 않는다 — `pointer-events` 를 막는 순간 스킵 오판정을
    영원히 못 잡는다(`board.html` 의 `.ct-done` 과 같은 판단).
    """
    돌린척(_산출물_여러상품())
    본문 = 화면.get(f"/banner/review?run_dir={tmp_run_dir.name}").text

    assert "⏭ 스킵" in 본문 and banner.제거율초과 in 본문, "스킵 사유가 화면에 없다"
    # 스킵 상품(zz02)의 장 3개가 전부 깔렸다 — 썸네일 경로로 센다.
    깔림 = [i for i in range(3)
          if f'/banner/thumb/{tmp_run_dir.name}/1/{i}"' in 본문]
    assert 깔림 == [0, 1, 2], f"스킵 상품의 장이 {깔림} 만 깔렸다 (D-03a)"
    # 스킵 줄의 장에도 라벨 POST 가 걸려 있어야 한다 — 흐리게만 하고 클릭은 산다.
    스킵줄 = 본문.split('id="p-1"', 1)[1]
    assert 'hx-post="/banner/label"' in 스킵줄, "스킵 줄에서 클릭이 사라졌다 (D-09)"
    # 클릭을 죽이는 CSS 도 없다. 금지 낱말을 이 파일에 글자로 안 남긴다(런타임 조립).
    assert ("pointer" + "-events") not in 본문, "스킵 줄의 클릭을 막았다 — 오판정을 못 잡는다"


def test_장_클릭이_hx_post_다(화면, 돌린척, tmp_run_dir):
    """`hx-get` 으로 바꾸면 Origin 층이 통째로 무력화된다 (T-1-01b / T-4-05).

    교차 사이트 단순 GET 에는 Origin 헤더가 없다 — 쓰기를 GET 으로 만드는 순간
    `security.guard` 의 첫 층이 아무것도 못 거른다.
    """
    돌린척(_산출물_여러상품())
    본문 = 화면.get(f"/banner/review?run_dir={tmp_run_dir.name}").text

    assert 'hx-post="/banner/label"' in 본문
    assert 'hx-post="/banner/confirm"' in 본문
    assert "hx-" + "get" not in 본문, "쓰기를 GET 으로 걸었다 (T-1-01b)"
    assert 'hx-swap="outerHTML"' in 본문
    assert 'loading="lazy"' in 본문, "891개 <img> 를 한 번에 로드하게 뒀다"


def test_토글이_기계판정으로_되돌아온다():
    """클릭 순환: 기계 → 반대 → 무내용 → **기계**. 되돌리기 버튼을 따로 두지 않는다.

    상태를 하나 더 만들면 그게 곧 사람 판단 큐의 입구다(D-09). 원래 판정을 다시
    찍는 것이 되돌리기다.
    """
    from webapp.routes import banner as 라우트

    # 기계가 배너라 한 장
    assert 라우트._다음판정(banner.배너, None) == banner.제품
    assert 라우트._다음판정(banner.배너, banner.제품) == banner.무내용
    assert 라우트._다음판정(banner.배너, banner.무내용) == banner.배너      # 복귀
    # 기계가 제품이라 한 장 — 한 번 누르면 배너다(미탐을 찍는 동선이 가장 짧아야 한다)
    assert 라우트._다음판정(banner.제품, None) == banner.배너
    assert 라우트._다음판정(banner.제품, banner.배너) == banner.무내용
    assert 라우트._다음판정(banner.제품, banner.무내용) == banner.제품      # 복귀
    # 기계가 미판정인 장은 복귀 자리가 없다 — 사람은 '모르겠다'를 찍지 못한다(D-09).
    순환 = []
    현재 = None
    for _ in range(3):
        현재 = 라우트._다음판정(banner.미판정, 현재)
        순환.append(현재)
    assert set(순환) == set(banner.사람판정허용값)
    assert banner.미판정 not in 순환


def test_라벨_응답이_그_장_하나의_조각이다(화면, 돌린척, tmp_run_dir):
    """응답은 `<figure>` 하나다 — 줄 전체를 돌려주면 가로 스크롤이 매 클릭마다 초기화된다.

    그리고 조각의 테두리·글자는 **서버가 산출물을 다시 읽어** 정한다. 요청이 보낸
    값으로 그리면 화면이 DB 가 아니라 자기 자신을 비추게 되고, 그 순간 "미탐 0%" 의
    근거가 사라진다.
    """
    돌린척(_산출물_여러상품())
    응답 = 화면.post("/banner/label", data={
        "run_dir": tmp_run_dir.name, "타오바오상품번호": "tb-zz01",
        "판매자상품코드": "zz01", "이미지순번": 3, "사람판정": banner.배너})

    assert 응답.status_code == 200
    조각 = 응답.text
    assert 조각.count("<figure") == 1, "조각이 장 하나가 아니다"
    assert 'data-i="3"' in 조각 and "ct-banner" in 조각 and "배너" in 조각
    assert "✋" in 조각, "사람이 찍은 장과 기계 판정이 구분되지 않는다"
    # 기계는 `제품` 이라 한 장이다 — 다음 클릭은 `무내용` 이어야 순환이 성립한다.
    assert banner.무내용 in 조각
    # 썸네일은 정수 인덱스 둘로만 부른다 (T-4-04). 파일명이 조각에 실리면 안 된다.
    assert f"/banner/thumb/{tmp_run_dir.name}/0/3" in 조각
    assert "zz01_03.webp" not in 조각


def test_모르는_회차로는_라벨이_안_들어간다(화면, tmp_path, tmp_run_dir):
    """회차 화이트리스트 밖 라벨은 **DB 에 남는데 어느 화면에도 안 보인다.**

    사람은 클릭이 먹혔다고 믿고 게이트는 그 라벨을 영원히 못 센다 — 저장은 됐는데
    화면이 거짓말을 하는 그 모양이다. 400 으로 끊는다.
    """
    db = tmp_path / "webapp.db"
    for 길, 몸통 in (("/banner/label",
                    {"run_dir": "2099-01-01", "타오바오상품번호": "tb-1",
                     "판매자상품코드": "zz01", "이미지순번": 0, "사람판정": banner.배너}),
                   ("/banner/confirm",
                    {"run_dir": "2099-01-01", "타오바오상품번호": "tb-1"})):
        assert 화면.post(길, json=몸통).status_code == 400
    assert _행수(db, "banner_label") == 0 and _행수(db, "banner_confirm") == 0


def test_확인함이_라벨과_섞이지_않는다(화면, 돌린척, tmp_path, tmp_run_dir):
    """"뒤집었다" 와 "다 봤다" 는 **다른 사실**이라 테이블도 다르다 (Pitfall 8).

    안 본 상품을 "기계 판정에 동의" 로 세면 미탐 0% 가 거짓말이 된다. 그래서 확인은
    라벨 수를 건드리지 않는다.
    """
    돌린척(_산출물_여러상품())
    db = tmp_path / "webapp.db"

    응답 = 화면.post("/banner/confirm", data={"run_dir": tmp_run_dir.name,
                                          "타오바오상품번호": "tb-zz01"})
    assert 응답.status_code == 200 and "확인함" in 응답.text
    assert _행수(db, "banner_confirm") == 1
    assert _행수(db, "banner_label") == 0, "확인이 라벨 테이블을 건드렸다"

    본문 = 화면.get(f"/banner/review?run_dir={tmp_run_dir.name}").text
    assert "ct-done" in 본문, "확인한 줄이 화면에서 안 바뀐다"


def test_판정이_색만으로_갈리지_않는다(화면, 돌린척, tmp_run_dir):
    """흑백 출력·색맹에서도 살아야 한다 — **테두리 스타일과 글자까지** 다르다.

    `board.html:22-46` 이 세운 규율이다. 색 하나로 가르면 화면이 절반의 사람에게
    아무 말도 안 한다.
    """
    from pathlib import Path as _P

    from webapp import main as _main

    css = (_P(_main.BASE) / "templates" / "banner_review.html").read_text(encoding="utf-8")
    for 스타일 in ("border-style: solid", "border-style: dashed", "border-style: double"):
        assert 스타일 in css, f"{스타일} 이 없다 — 색만으로 가르고 있다"

    돌린척(_산출물_여러상품())
    본문 = 화면.get(f"/banner/review?run_dir={tmp_run_dir.name}").text
    assert "ct-banner" in 본문 and "ct-product" in 본문
    assert "0 배너" in 본문, "테두리 옆에 글자가 없다"
