# -*- coding: utf-8 -*-
"""불사자 MCP 호출 레이트리밋 규율 — **stdlib `time` 말고는 아무것도 쓰지 않는다.**

실측 근거 (2026-09-21, 이 맥북에서 직접 호출):
  · 응답 헤더 원문 `RateLimit-Policy: 240;w=60`  → 60초에 240회 = **초당 4회**
  · 429 응답 헤더 원문 `Retry-After: 20`
  · 단일 세션 지속 처리량 3.7건/초 (그룹 하나 953건을 258초에 완주, 429 발생 0건)
  · 동시 세션 4개·8개 **모두 429** — 서버 정책이 토큰 단위라 세션을 늘려도 총량이 같다.
    그래서 프로세스를 늘려 빨라지는 길은 없다. 같은 잡 두 개를 동시에 못 돌게 막는 것은
    웹앱 쪽 `jobs.SINGLETON_KINDS` 가드이고, 이 모듈은 **자기 몫의 간격만** 지킨다.

왜 공용 라이브러리(`eroomlib.bulsaja._post`)의 백오프를 안 고치나:
  그 백오프는 `0.4 × 2^attempt` = 네 번 합쳐 6초인데 서버는 20초를 요구한다.
  고치면 이 저장소의 스킬 12개가 같이 바뀐다. 호출자가 애초에 초당 4회를 안 넘기는 쪽이
  싸고, 위 953건 완주로 이미 검증된 방법이다. (RESEARCH §Pitfall 2 / Open Question 3)

왜 이 파일에 MCP 를 import 하지 않나:
  웹앱 전용 `.venv-web` 에는 `requests` 가 없다(D-19). MCP 를 끌어오면 그 venv 의 pytest 가
  이 모듈을 import 조차 못 하고, 그러면 레이트리밋 규율이 **3시간 32분짜리 잡을 실제로
  돌려봐야만** 검증되는 물건이 된다. 시계를 주입 가능하게 둔 것도 같은 이유다.
"""
import time


class 호출간격:
    """호출과 호출 사이에 `최소간격` 초를 보장한다.

    `now_fn`/`sleep_fn` 을 **인자로 받는다** — 테스트가 가짜 시계를 꽂아 실제로 자지 않고
    간격을 재기 위해서다 (`eroomlib/snapshot.py:191-192` 의 `sleep_fn=time.sleep` 과 같은
    주입 관용구).

    ⚠️ 기본 시계가 `time.time` 이 아니라 `time.monotonic` 인 이유:
       이 루프는 3시간 넘게 돈다. 그 사이에 NTP 보정·서머타임·사용자의 시계 변경이 끼면
       `time.time` 기반 간격은 **음수가 되거나(=간격을 통째로 무시) 몇 시간을 잔다.**
       `monotonic` 은 뒤로 가지 않는 것이 보장된 시계라 그 사고가 구조적으로 없다.
    """

    def __init__(self, 최소간격: float, now_fn=time.monotonic, sleep_fn=time.sleep):
        self.최소간격 = float(최소간격)
        self._now = now_fn
        self._sleep = sleep_fn
        self._직전 = None          # None = 아직 한 번도 안 불렸다

    def 대기(self) -> float:
        """다음 호출을 내보내도 되는 시점까지 잔다. **실제로 잔 시간(초)** 을 돌려준다.

        첫 호출은 기다릴 이유가 없어서 0 이다. 반환값이 있는 이유는 테스트가 그걸 재고,
        진행 로그가 "얼마나 레이트리밋에 묶였나" 를 말할 수 있어야 하기 때문이다.
        """
        try:
            지금 = self._now()
            if self._직전 is None:
                self._직전 = 지금
                return 0.0

            남은 = self.최소간격 - (지금 - self._직전)
            if 남은 > 0:
                self._sleep(남은)
                # 잔 뒤의 시각을 다시 읽는다 — 잠든 사이 흐른 시간을 그대로 반영한다.
                self._직전 = self._now()
                return 남은

            self._직전 = 지금
            return 0.0
        except Exception:
            # 시계가 고장나도 루프를 죽이지 않는다. 단 **간격을 건너뛰지는 않는다** —
            # 안전한 쪽(한 박자 쉬기)으로 넘어가고 기준점을 다시 잡는다.
            try:
                self._sleep(self.최소간격)
            except Exception:
                pass
            self._직전 = None
            return self.최소간격


def 안전호출(fn, *, 재시도대기: float, 횟수: int = 6,
            sleep_fn=time.sleep, 로그=print):
    """`fn()` 을 부르고 **429 만** 재시도한다. 반환 `(결과, 미조회여부)`.

    · 성공          → `(결과, False)`
    · 끝까지 429    → `(None, True)`   ← **예외로 터뜨리지 않는다**
    · 그 밖의 예외  → 그대로 올린다     ← **삼키지 않는다**

    ⚠️ `(None, True)` 로 강제하는 이유 — 호출부가 미조회를 **반드시 기록하게** 만들려는 것이다.
       여기서 `continue` 로 조용히 넘어가는 경로를 만들면 그 상품이 인덱스에서 그냥 빠지고,
       화면에서는 "미해소 — 번호가 불사자에 없음(= 광고 쪽 오류)" 으로 보인다. 그러면
       용팀장이 멀쩡한 광고그룹을 지우러 간다. **되돌릴 수 없다** (RESEARCH §Pitfall 3).

    ⚠️ 429 가 아닌 예외를 잡지 않는 이유 — 모르는 실패를 미조회로 뭉개면 원인이 사라진다.
       미조회는 화면에서 "인덱스 불완전(시스템)" 으로 읽히는데, 진짜 원인이 응답 스키마
       변경이나 토큰 만료면 **사람이 고칠 수 없는 문제**가 된다. 터져서 로그에 남는 쪽이 낫다.

    429 판별은 `RuntimeError` 의 **문자열에 `429` 가 있는지**로 한다 — `eroomlib/bulsaja.py`
    의 `_post` 가 상태코드를 문자열에 실어 `RuntimeError` 로 올리기 때문이다(전용 예외 타입이
    없다). 공용 라이브러리에 예외 타입을 새로 파면 스킬 12개가 같이 바뀐다.
    """
    마지막 = ""
    for 시도 in range(1, max(1, int(횟수)) + 1):
        try:
            return fn(), False
        except RuntimeError as e:
            if "429" not in str(e):
                raise                     # 우리 소관이 아니다 — 그대로 올린다
            마지막 = str(e)[:200]
            if 시도 >= 횟수:
                break                     # 마지막 시도 뒤에는 자지 않는다 (21초 헛낭비)
            try:
                로그(f"[429] {시도}/{횟수}회 — {재시도대기}초 대기 후 재시도")
            except Exception:
                pass
            sleep_fn(재시도대기)

    # 무신호가 더 위험한 신호다 — 포기한 사실을 반드시 말한다.
    try:
        로그(f"[429 포기] {횟수}회 재시도 실패 — 미조회로 기록한다: {마지막}")
    except Exception:
        pass
    return None, True
