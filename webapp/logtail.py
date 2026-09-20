#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""진행 로그 — **파일을 오프셋부터 tail 한다. 파이프를 직접 읽지 않는다.**

저장소의 유일한 자식 프로세스 analog(`.claude/lib/eroomlib/runner/run_all.py:37-44`)는
자식의 출력 파이프를 직접 읽는다. 그 방식은 이 프로젝트의 성공기준 3
("탭을 닫았다 다시 열어도 진행 로그를 처음부터 이어서 본다")과 **양립하지 않는다** —
파이프는 읽는 사람이 없으면 버퍼에 고이다가 사라지고, 브라우저가 닫혀 있던 동안의
출력을 되살릴 방법이 없다. 자식 stdout 을 append-only 로그파일로 돌리고(Plan 01-05
`jobs.spawn`), 화면은 그 파일을 **오프셋부터 읽는다** — 이게 정답이다
(CLAUDE.md 핵심결정 3 / PATTERNS §C-3).

**매 접속마다 오프셋 0 부터 전량 재생한다.** 이어받기를 브라우저가 재연결 때 보내는
**마지막 이벤트 ID 헤더**에 맡기지 않는다: htmx-ext-sse 2.2.4 는 재연결할 때
`EventSource` 를 **새로 만들어** 이전 연결의 이벤트 ID 상태를 버린다(소스 확인).
sse-starlette 도 그 헤더를 읽지 않는다.
그 위에 이어받기를 세우면 "이어보기가 가끔 된다" 는 재현 불가 버그가 된다.
잡 로그는 실측 4.5KB / 53줄(`bids` dry-run 4계정)이라 전량 재생이 더 단순하고 더
정확하며, 요구사항의 문장("처음부터 이어서 본다")과 글자 그대로 맞는다.

**이벤트마다 '지금까지의 전체 로그'를 보낸다.** htmx 의 `sse-swap` 기본 swap 은
`innerHTML`(전량 교체)이다. 청크만 보내면 화면에 마지막 청크만 남아 로그가 한 줄씩
깜빡인다. 반대로 클라이언트가 `beforeend` 로 붙이게 하면 재연결 때 로그가 두 번
찍힌다(T-1-26). 그래서 **서버가 누적본을 보내고 클라이언트는 교체만 한다** —
20KB 를 초당 2.5회 보내는 비용은 127.0.0.1 에서 의미가 없다.

**로그 센티널을 새로 만들지 마라.** `detail_batch.py` 에는 `###DETAIL###` 이 있지만
광고 CLI 계열엔 없고, D-02/D-03 이 이미 "stdout 파싱 금지, CLI 가 파일로 쓴다"로
정했다. 여기서 흐르는 로그는 **사람이 보는 용도로만** 쓴다 — 값을 뽑아내지 않는다.
"""
import html

import anyio
from sse_starlette import ServerSentEvent

from webapp import jobs, security, settings

# 화면에 쓰는 작업 종류·상태 이름. 템플릿의 사전과 같은 내용을 두 번 적는 셈이지만,
# `done` 이벤트는 템플릿을 거치지 않고 여기서 조립되므로 여기에도 있어야 한다.
작업이름 = {
    "prep": "새로 수집", "run": "판정 다시",
    "bids_preview": "입찰가 미리보기", "bids_commit": "입찰가 인상",
    "revert_only": "이 작업분 되돌리기", "revert_all": "이 회차 전체 되돌리기",
    "synthetic": "합성 작업",
}
상태이름 = {"starting": "띄우는 중", "running": "도는 중", "done": "끝남",
        "failed": "실패", "orphaned": "결과 미상"}


def read_from(path, offset: int) -> tuple[str, int]:
    """오프셋(바이트)부터 읽고 `(텍스트, 새 오프셋)` 을 준다.

    **글자 수가 아니라 바이트다.** 한글 로그에서 둘은 다르고, 파일 오프셋은 바이트다.

    `errors="replace"` 인 이유: 0.4초마다 읽으므로 자식이 한글을 찍는 도중
    **멀티바이트 한가운데가 잘린다.** 정확히 하려면 불완전한 꼬리 바이트만큼
    오프셋을 되돌려 다음 회차로 미뤄야 하는데, 그 정교함이 사는 값은
    "0.4초 동안 글자 하나가 `�` 로 보였다가 제자리를 찾는다" 뿐이다.
    다음 회차에 나머지 바이트가 붙으면서 **누적본이 통째로 다시 그려지므로**
    깨진 글자는 화면에 남지 않는다. 전량 재생 설계가 이 트레이드오프를 공짜로 만든다.

    실패(파일 없음·디렉터리·권한)는 **예외 없이 `("", offset)` 으로 폴백한다.**
    로그를 못 읽는 것은 돈으로 이어지지 않는다(저장소 S-2 판별 기준). 여기서
    예외를 올리면 작업이 시작되자마자 스트림이 죽고, 사용자는 "작업이 멈췄다"로
    오독한다 — 실제로는 잘 돌고 있는데.
    """
    try:
        with open(path, "rb") as f:
            f.seek(offset)
            b = f.read()
    except Exception:
        return "", offset
    return b.decode("utf-8", errors="replace"), offset + len(b)


def 완료요약(상태: dict) -> str:
    """`done` 이벤트로 나갈 한 줄. **화이트리스트 필드로만 조립한다.**

    이 문자열은 템플릿 자동 이스케이프를 거치지 않고 브라우저에 그대로 꽂히므로,
    사용자 입력이 섞일 여지를 아예 만들지 않는다. `run_dir` 은 회차 화이트리스트를
    통과한 이름이지만 그래도 escape 한다 — 규칙에 예외를 두면 다음 사람이 늘린다.
    """
    st = 상태.get("status") or ""
    이름 = 상태이름.get(st, st)
    줄 = f"<strong>{html.escape(작업이름.get(상태.get('kind'), 상태.get('kind') or ''))}</strong> — {html.escape(이름)}"
    코드 = 상태.get("exit_code")
    if 코드 is not None:
        줄 += f" (종료코드 {int(코드)})"
    경과 = 상태.get("elapsed_sec")
    if 경과 is not None:
        줄 += f" · {int(경과) // 60}분 {int(경과) % 60}초"
    if 상태.get("run_dir"):
        줄 += f" · {html.escape(str(상태['run_dir']))} 회차"
    return f"<p>{줄}</p>"


async def sse_generator(job_id: str, request):
    """로그 전량을 재생하고 그 뒤를 tail 한다. 작업이 끝나면 `done` 을 내고 닫는다.

    루프 한 바퀴:
      ① 클라이언트가 끊겼으면 **즉시 빠져나온다** — 죽은 브라우저를 붙잡고 있으면
         제너레이터와 커넥션이 쌓인다(T-1-24). HTTP/1.1 은 호스트당 6 커넥션이다.
      ② 오프셋부터 새 바이트를 읽어 누적본에 붙인다
      ③ 새 것이 있으면 `event="log"` 로 **누적본 전체**를 보낸다
      ④ 새 것이 없고 작업도 끝났으면 `event="done"` 한 번 내고 종료
      ⑤ `anyio.sleep` — `time.sleep` 을 쓰면 이벤트 루프가 통째로 멈춘다(T-1-28)

    `id=str(off)` 는 **디버깅용 표식일 뿐이다.** 서버는 재연결 헤더를 읽지 않고,
    읽는 코드를 추가하지도 마라(모듈 docstring 참조). `curl -N` 으로 볼 때 지금까지
    몇 바이트를 흘렸는지 보이는 것이 값의 전부다.

    `jobs.job_status` 는 sqlite 를 만진다. 이 함수는 **이벤트 루프 위에서** 도는
    유일한 경로라 blocking IO 를 직접 하면 다른 요청이 전부 멈춘다 — 그래서
    스레드로 밀어낸다. 상태 조회는 새 로그가 없을 때만 한다(있으면 어차피 도는 중).
    """
    상태 = await anyio.to_thread.run_sync(jobs.job_status, job_id)
    if 상태 is None:
        # 없는 작업. 라우트가 먼저 404 로 막지만, 스트림 도중에 사라질 수도 있다.
        # 지어낸 `done` 을 보내지 않고 조용히 닫는다.
        return

    경로 = jobs.log_path_of(job_id)
    off = 0                      # ← 이 0 이 전량 재생이다. 이어받기로 바꾸지 마라.
    누적 = ""

    while True:
        if await request.is_disconnected():
            break

        덩어리, off = read_from(경로, off)
        if 덩어리:
            # scrub 먼저, escape 나중. 순서가 바뀌면 시크릿이 escape 된 모양으로
            # 어긋나 스크러버를 비켜 갈 수 있다.
            누적 += html.escape(security.scrub(덩어리))
            yield ServerSentEvent(data=누적, event="log", id=str(off))
            continue             # 아직 흐르는 중이면 상태를 물을 것도 없다

        상태 = await anyio.to_thread.run_sync(jobs.job_status, job_id)
        # `starting` 도 **아직 도는 중**이다 (jobs.LIVE_STATUSES). 여기서 끝난 것으로
        # 읽으면 자식이 뜨기도 전에 done 을 쏘고 스트림을 닫는다.
        if 상태 is None or 상태.get("status") not in jobs.LIVE_STATUSES:
            yield ServerSentEvent(data=완료요약(상태 or {}), event="done")
            break

        await anyio.sleep(settings.POLL_INTERVAL)
