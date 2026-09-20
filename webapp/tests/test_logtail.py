#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""로그 오프셋 tail + SSE 제너레이터(`webapp/logtail.py`) 검증 — 합성 잡으로만 돈다.

이 파일이 증명하는 것은 넷이다:

  · 오프셋부터 바이트로 읽고, 없는 파일·깨진 경로·멀티바이트 절단을 **예외 없이** 버틴다
  · SSE 제너레이터가 **매 접속마다 오프셋 0 부터** 전량 재생한다 (SC-03 의 뿌리)
  · 로그가 `security.scrub()` → `html.escape()` 를 통과한 뒤에야 화면으로 나간다 (T-1-03d / T-1-17b)
  · 끊긴 클라이언트를 붙잡고 있지 않는다 (T-1-24)

`Last-Event-ID` 를 읽는 코드가 **없다는 것** 도 여기서 기계로 감시한다 (T-1-27).
htmx-ext-sse 2.2.4 가 재연결 때 `EventSource` 를 새로 만들어 last event ID 를
버리기 때문에, 그 헤더에 기대면 "이어보기가 가끔 된다" 는 재현 불가 버그가 된다.

pytest-asyncio 를 깔지 않는다. `anyio.run()` 으로 동기 테스트 안에서 코루틴을 돌린다 —
의존성 하나를 아끼는 것이 아니라, 이 파일이 **웹앱 전체와 같은 이벤트 루프 규약**
(anyio) 위에서 도는 게 맞기 때문이다.
"""
import sys
import time
from pathlib import Path

import anyio
import pytest

from webapp import jobs, logtail, security, settings

합성 = Path(__file__).resolve().parent / "fixtures" / "synthetic_job.py"


# ── 도우미 ──────────────────────────────────────────────────────────────────

class 가짜요청:
    """`Request` 대역 — 제너레이터가 쓰는 건 `is_disconnected()` 하나뿐이다."""

    def __init__(self, 끊김: bool = False):
        self.끊김 = 끊김

    async def is_disconnected(self) -> bool:
        return self.끊김


def 받기(job_id: str, 초: float = 3.0, 끊김: bool = False) -> list:
    """제너레이터를 `초` 동안(또는 스스로 끝날 때까지) 돌려 이벤트를 모은다."""

    async def 본체():
        받은 = []
        요청 = 가짜요청(끊김)
        with anyio.move_on_after(초):
            async for ev in logtail.sse_generator(job_id, 요청):
                받은.append(ev)
        return 받은

    return anyio.run(본체)


def 로그이벤트(받은: list) -> list:
    return [e for e in 받은 if e.event == "log"]


def 마지막로그(받은: list) -> str:
    logs = 로그이벤트(받은)
    return logs[-1].data if logs else ""


# ── 픽스처 ──────────────────────────────────────────────────────────────────

@pytest.fixture
def 잡판(tmp_path, monkeypatch):
    """잡 DB·로그 디렉터리를 tmp 로 돌린다. 저장소 루트의 webapp.db 를 안 건드린다."""
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.setattr(settings, "JOB_LOG_DIR", str(tmp_path / "logs"))
    jobs.init_db()
    yield tmp_path
    for proc in list(jobs._PROCS.values()):
        try:
            proc.kill()
        except Exception:
            pass
    jobs._PROCS.clear()


def 찍는잡(코드: str) -> str:
    """한 줄 찍고 바로 끝나는 합성 잡을 띄우고 job_id 를 준다."""
    return jobs.create_job("synthetic", argv_override=[sys.executable, "-c", 코드])


def 끝날때까지(job_id: str, 초=8.0) -> dict:
    한계 = time.time() + 초
    while time.time() < 한계:
        상태 = jobs.job_status(job_id)
        if 상태 and 상태["status"] != "running":
            return 상태
        time.sleep(0.05)
    pytest.fail(f"{초}초 안에 안 끝났다: {jobs.job_status(job_id)}")


# ── read_from ───────────────────────────────────────────────────────────────

def test_없는_파일은_빈값과_같은_오프셋이다(tmp_path):
    """잡이 막 뜨고 아직 아무것도 안 찍었을 때 — 예외가 아니라 빈 값이다.

    여기서 예외를 던지면 작업이 시작되자마자 화면이 500 으로 죽는다. 이 실패는
    돈으로 이어지지 않으므로(저장소 S-2 판별 기준) 폴백이 맞다.
    """
    assert logtail.read_from(tmp_path / "없다.log", 0) == ("", 0)
    assert logtail.read_from(tmp_path / "없다.log", 99) == ("", 99)


def test_오프셋0은_전체와_파일크기를_준다(tmp_path):
    p = tmp_path / "a.log"
    p.write_text("첫줄\n둘째줄\n", encoding="utf-8")

    텍스트, 오프셋 = logtail.read_from(p, 0)
    assert 텍스트 == "첫줄\n둘째줄\n"
    assert 오프셋 == p.stat().st_size          # 바이트 기준이다 — 글자 수가 아니다
    assert 오프셋 > len(텍스트), "한글은 글자보다 바이트가 많다 — 바이트로 세야 한다"


def test_오프셋_이후만_읽는다(tmp_path):
    p = tmp_path / "b.log"
    p.write_bytes("하나\n".encode("utf-8"))
    _, 오프셋 = logtail.read_from(p, 0)

    with open(p, "ab") as f:
        f.write("둘\n".encode("utf-8"))

    텍스트, 새오프셋 = logtail.read_from(p, 오프셋)
    assert 텍스트 == "둘\n"
    assert 새오프셋 == p.stat().st_size

    # 더 읽을 게 없으면 빈 문자열 + 오프셋 불변
    assert logtail.read_from(p, 새오프셋) == ("", 새오프셋)


def test_멀티바이트_한가운데서_잘려도_예외가_없다(tmp_path):
    """한글 로그라 **실제로 난다.** 0.4초 뒤 다음 회차에 붙으므로 사실상 안 보인다.

    중요한 건 여기서 `UnicodeDecodeError` 가 나지 않는 것이다 — 그러면 그 순간
    스트림이 죽고, 사용자는 "로그가 멈췄다" 로 읽는다.
    """
    p = tmp_path / "c.log"
    바이트 = "가나다\n".encode("utf-8")           # '가' = 3바이트
    p.write_bytes(바이트)

    텍스트, 오프셋 = logtail.read_from(p, 1)      # '가' 한가운데
    assert "�" in 텍스트                     # 치환 문자로 버틴다
    assert 오프셋 == len(바이트)

    # 잘린 조각을 이어 붙여도 파일 전체 바이트 수와 맞는다
    앞, _ = logtail.read_from(p, 0)
    assert 앞.endswith("가나다\n")


def test_읽기_실패는_폴백한다(tmp_path):
    """디렉터리를 줘도(IsADirectoryError) 빈 값으로 떨어진다 — 예외가 안 샌다."""
    assert logtail.read_from(tmp_path, 0) == ("", 0)


# ── sse_generator ───────────────────────────────────────────────────────────

def test_재접속해도_오프셋0부터_전량재생한다(잡판):
    """**SC-03 의 뿌리.** 두 번째 접속에서도 첫 줄이 다시 나온다.

    `Last-Event-ID` 로 이어받는 설계였다면 두 번째 접속은 끊긴 지점부터 시작해
    첫 줄이 안 보인다. htmx-ext-sse 는 재연결 때 EventSource 를 새로 만들어
    그 헤더를 아예 안 보내므로, 그 설계는 "가끔 이어진다" 로 무너진다.
    """
    job_id = jobs.create_job(
        "synthetic", argv_override=[sys.executable, str(합성), "12", "0.2", "0"])

    첫접속 = 받기(job_id, 초=0.9)
    앞 = 마지막로그(첫접속)
    assert "[1/12]" in 앞, "1차 접속에서 첫 줄을 못 봤다"
    assert "[12/12]" not in 앞, "1차 접속이 너무 오래 붙어 있었다 — 측정이 무의미"

    time.sleep(0.9)                                # 끊겨 있는 동안에도 자식은 돈다

    둘째접속 = 받기(job_id, 초=0.9)
    뒤 = 마지막로그(둘째접속)
    assert "[1/12]" in 뒤, "재접속했더니 첫 줄이 사라졌다 (전량 재생이 아니다)"
    assert "[5/12]" in 뒤, "끊긴 사이에 찍힌 줄이 없다 — 파이프를 읽고 있다"
    assert 뒤.count("[1/12]") == 1, "한 이벤트 안에 같은 줄이 두 번 있다"
    assert len(뒤) > len(앞), "재접속 페이로드가 1차보다 짧다"


def test_이벤트마다_지금까지의_전체로그를_보낸다(잡판):
    """`sse-swap` 기본 swap 이 innerHTML(전량 교체)이라 **누적본**을 보내야 맞다.

    청크만 보내면 화면에 마지막 청크만 남는다 — 로그가 한 줄씩 깜빡이는 화면이 된다.
    """
    job_id = jobs.create_job(
        "synthetic", argv_override=[sys.executable, str(합성), "6", "0.2", "0"])
    받은 = 받기(job_id, 초=4.0)
    logs = 로그이벤트(받은)

    assert len(logs) >= 2, "이벤트가 한 번만 왔다 — 실시간이 아니다"
    길이 = [len(e.data) for e in logs]
    assert 길이 == sorted(길이), f"누적본이 아니다 (길이가 줄었다): {길이}"
    assert "[1/6]" in logs[-1].data and "[6/6]" in logs[-1].data


def test_끝난_잡은_done_이벤트로_닫힌다(잡판):
    """전량 재생 후 `done` 한 번 → 제너레이터 종료. 무한히 돌지 않는다."""
    job_id = 찍는잡("print('끝')")
    끝날때까지(job_id)

    받은 = 받기(job_id, 초=3.0)
    assert [e.event for e in 받은].count("done") == 1
    assert 받은[-1].event == "done", "done 뒤에 더 보냈다"
    assert "끝" in 마지막로그(받은), "닫기 전에 로그를 다 못 흘렸다"


def test_로그가_스크러버를_통과한다(잡판):
    """T-1-03d — 자식이 예기치 않게 시크릿을 찍어도 화면 직전에 가려진다."""
    비밀 = "SECRETVALUE1234567890"
    security.register_secret(비밀)
    try:
        job_id = 찍는잡(f"print('토큰은 {비밀} 이다')")
        끝날때까지(job_id)
        본문 = 마지막로그(받기(job_id, 초=3.0))
        assert 비밀 not in 본문
        assert "***" in 본문
    finally:
        security._SECRETS.discard(비밀)


def test_로그가_escape_되어_나간다(잡판):
    """T-1-17b — 상품명에 HTML 스러운 문자열이 섞여 들어온다. `<pre>` 에 날로 넣지 않는다."""
    job_id = 찍는잡(r"print('<script>alert(1)</script> & <b>')")
    끝날때까지(job_id)

    본문 = 마지막로그(받기(job_id, 초=3.0))
    assert "<script>" not in 본문
    assert "&lt;script&gt;" in 본문
    assert "&amp;" in 본문


def test_끊긴_클라이언트는_즉시_놓는다(잡판):
    """T-1-24 — 죽은 브라우저를 붙잡고 있으면 커넥션·제너레이터가 쌓인다."""
    job_id = jobs.create_job(
        "synthetic", argv_override=[sys.executable, str(합성), "40", "0.2", "0"])

    시작 = time.time()
    받은 = 받기(job_id, 초=3.0, 끊김=True)
    걸린시간 = time.time() - 시작

    assert 걸린시간 < 1.0, f"끊긴 걸 알고도 {걸린시간:.1f}초를 붙잡고 있었다"
    assert 받은 == [], "끊긴 클라이언트에 이벤트를 보냈다"


def test_모르는_잡은_done_없이_조용히_끝난다(잡판):
    """없는 job_id 는 로그도 상태도 없다. 여기서 예외를 던지면 스트림이 500 이 된다."""
    받은 = 받기("그런-잡-없음", 초=2.0)
    assert 받은 == []


# ── 설계 가드 ───────────────────────────────────────────────────────────────

def test_last_event_id_를_읽지_않는다():
    """T-1-27 — 이 헤더에 기대는 순간 "가끔 이어진다" 는 재현 불가 버그가 된다.

    문자열 감시라 주석에도 걸린다. 그게 맞다 — 주석의 예시가 내일의 복붙 코드다.
    """
    본문 = Path(logtail.__file__).read_text(encoding="utf-8").lower()
    assert "last-event-id" not in 본문
    assert "last_event_id" not in 본문


def test_파이프를_읽지_않는다():
    """ENG-03 — 파이프 직독은 "탭 닫았다 재접속" 과 양립하지 않는다 (PATTERNS §C-3)."""
    본문 = Path(logtail.__file__).read_text(encoding="utf-8")
    for 금지 in ("Popen", "stdout.read", "communicate("):
        assert 금지 not in 본문, f"logtail 이 {금지} 를 쓴다 — 파일을 tail 해라"
    assert 'errors="replace"' in 본문
