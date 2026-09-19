#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""합성 잡 — 실제 광고 API 를 한 번도 안 건드리고 잡 엔진을 검증하는 대역.

왜 필요한가: 잡 엔진이 증명해야 하는 것은 "수 분 걸리는 자식 프로세스의 진행 로그가
실시간으로 쌓이고, 서버가 죽어도 자식이 살고, 탭을 닫았다 열면 이어 보인다" 다.
그걸 `prep` 로 검증하면 한 번에 수 분 + 광고 API 호출이 필요하다. 이 스크립트는
같은 성질(장시간·줄 단위 출력·종료코드)을 2.4초에 재현한다.

**`flush=True` 를 일부러 안 쓴다.** 파이프로 연결된 stdout 은 블록 버퍼링이라,
`PYTHONUNBUFFERED=1` 없이 띄우면 잡이 끝날 때까지 로그가 한 줄도 안 쌓인다.
ENG-03("작업 중간 시점에 로그파일이 이미 커져 있다")은 잡 엔진이 그 환경변수를
제대로 주입할 때만 통과한다 — 이 스크립트가 그걸 거짓 통과시키지 않는 장치다.

사용: python3 synthetic_job.py [줄수=12] [줄당초=0.2] [종료코드=0]
"""
import sys
import time


def main(argv):
    lines = int(argv[0]) if len(argv) > 0 else 12
    delay = float(argv[1]) if len(argv) > 1 else 0.2
    rc = int(argv[2]) if len(argv) > 2 else 0

    for i in range(1, lines + 1):
        print(f"[{i}/{lines}] tick")   # flush 하지 않는다 — 위 주석 참조
        time.sleep(delay)

    if rc:
        print(f"합성 잡 실패로 끝낸다 (종료코드 {rc})", file=sys.stderr)
    else:
        print("합성 잡 완료")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
