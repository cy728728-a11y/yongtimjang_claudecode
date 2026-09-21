#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""보드를 **실제로 한 번 그려 보고** 새 요소가 HTML 에 있는지 확인한다.

왜 pytest 가 아니라 여기인가: pytest 로도 같은 검사를 하지만(`test_board.py`),
이 스크립트는 "지금 내 손에서 화면이 뜨는가" 를 한 줄로 확인하는 용도다.
회차를 tmp 에 깔고 조인 산출물까지 붙여 **스캔을 한 번 돌린 뒤의 상태**를 만든다 —
그래야 시스템 배너가 "상품 연결 N/M" 을 말하는 경로까지 지나간다.

실제 `~/python_work/data` 도 저장소 루트의 `webapp.db` 도 건드리지 않는다.

    .venv-web/bin/python3 webapp/tests/fixtures/render_check.py
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent
WEBAPP = FIXTURES.parents[1]
ROOT = WEBAPP.parent
sys.path.insert(0, str(ROOT))

# **import 보다 먼저** 환경변수를 심는다. `settings` 는 import 시점에 reload() 하면서
# 이 값을 읽는다 — 나중에 바꾸면 저장소 루트의 진짜 webapp.db 를 쓰게 된다.
_TMP = Path(tempfile.mkdtemp(prefix="ct-render-"))
os.environ["CT_DB_PATH"] = str(_TMP / "jobs.db")
os.environ["CT_JOB_LOG_DIR"] = str(_TMP / "logs")

from fastapi.testclient import TestClient  # noqa: E402

from webapp import jobs, paths, security, settings  # noqa: E402

RUN = "2026-09-20"

# 보드 데이터 블록. 사람이 읽는 마크업과 기계가 읽는 데이터를 가르는 경계다.
_데이터시작 = '<script type="application/json" id="board-rows">'
_데이터끝 = "</script>"


def 마크업만(html: str) -> str:
    """보드 데이터 블록을 덜어 낸 나머지 — **사람이 실제로 읽는 부분**."""
    i = html.find(_데이터시작)
    if i == -1:
        return html
    j = html.find(_데이터끝, i)
    return html[:i] + (html[j:] if j != -1 else "")


def _깔기() -> None:
    """tmp 에 회차 + 조인 산출물 + 성공한 스캔 잡 1건을 만든다."""
    회차 = _TMP / "naver-ads" / "runs" / RUN
    회차.mkdir(parents=True)
    shutil.copyfile(FIXTURES / "result_traps.json", 회차 / "result.json")

    # 조인 산출물. `표시규칙`(프롬프트 인젝션)이 일부러 들어 있는 픽스처다 —
    # 이 글자가 렌더된 HTML 에 0건이어야 한다.
    산출물 = _TMP / "join_render_check.json"
    shutil.copyfile(FIXTURES / "join_traps.json", 산출물)

    paths.data_root = lambda: _TMP        # 실제 데이터 루트를 안 만진다

    jobs.init_db()
    때 = "2026-09-21T10:00:00+09:00"
    cx = jobs._conn()
    try:
        cx.execute(
            "INSERT INTO jobs (id, kind, run_dir, argv, status, exit_code, log_path, "
            "result_path, started_at, ended_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("render-check-scan", "bulsaja_scan", RUN, "[]", "done", 0,
             str(_TMP / "scan.log"), str(산출물), 때, 때))
        cx.commit()
    finally:
        cx.close()


def main() -> int:
    _깔기()
    from webapp.main import app

    c = TestClient(app, base_url=f"http://127.0.0.1:{settings.PORT}")
    c.cookies.set(security.COOKIE_NAME, security.BOOT_TOKEN)
    r = c.get("/")
    본문 = r.text

    있어야 = ['id="cleanup"', "번호 해소", "상품 연결", "인덱스 불완전",
              'id="f-state"', 'id="f-join"', 'id="resolution-ads"',
              'id="resolution-system"', "system-warn"]
    없어야 = ["표시규칙", "undefined"]

    실패 = 0
    if r.status_code != 200:
        print(f"FAIL  GET / → {r.status_code}")
        return 1
    print(f"PASS  GET / → 200 ({len(본문):,} bytes)")

    for 조각 in 있어야:
        ok = 조각 in 본문
        print(f"{'PASS' if ok else 'FAIL'}  본문에 {조각!r}")
        실패 |= 0 if ok else 1
    for 조각 in 없어야:
        n = 본문.count(조각)
        print(f"{'PASS' if n == 0 else 'FAIL'}  {조각!r} {n}건 (0이어야 한다)")
        실패 |= 0 if n == 0 else 1

    # `미스` 는 **마크업에 0건**이어야 한다 (03-05 가 넘긴 숙제 / Pitfall 3).
    # 데이터 블록(`#board-rows`)의 판정값까지 지우지는 않는다 — 거기 있는 건
    # 기계의 판정 기록이고, 소스 보기로 "왜 이렇게 떴나" 를 되짚는 유일한 통로다.
    # 사람이 읽는 자리(셀·배너·툴팁·필터 옵션)에 한 글자도 없으면 된다.
    n = 마크업만(본문).count("미스")
    print(f"{'PASS' if n == 0 else 'FAIL'}  마크업에 '미스' {n}건 (0이어야 한다 · 데이터 블록은 제외)")
    실패 |= 0 if n == 0 else 1

    # 화면이 실제로 무엇을 말하는지 눈으로도 남긴다.
    for 줄 in 본문.splitlines():
        if "번호 해소" in 줄 or "상품 연결" in 줄:
            print("  화면:", 줄.strip())

    print("----")
    print("렌더 확인 전량 PASS" if not 실패 else "FAIL 이 있다 — 여기서 멈춰라")
    return 실패


if __name__ == "__main__":
    try:
        코드 = main()
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(코드)
