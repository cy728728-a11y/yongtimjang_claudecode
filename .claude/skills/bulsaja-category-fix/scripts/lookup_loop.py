#!/usr/bin/env python3
"""캡챠 자동 릴레이 루프 — 카테고리 조회를 캡챠에 걸려도 끝까지 끌고 간다.

**왜 필요한가**: `aside_category.py` 는 `캡챠감지` 를 만나면 그 자리에서 멈춘다(옳다 —
계속 두드리면 차단이 깊어진다). 그런데 캡챠는 조회 **간격**이 아니라 **누적 총량**에
반응해서, 수백 건 그룹이면 밤새 여러 번 만난다. 그때마다 사람이 붙어 `solve` →
`--resume` 을 손으로 잇고 있었다(2026-08-11 25-2 야간 작업에서 2건 만에 멈췄다).

이 루프가 그 두 명령을 잇는다:
    조회(--resume) → 캡챠면 relay solve → 다시 조회(--resume) → …

**멈추는 조건** (조용히 계속 두드리지 않는다):
  - 전건 조회 완료
  - `needs_human`·`timeout` (릴레이가 못 푼 것 — 사람만 답할 수 있다)
  - 같은 검색어 캡챠 2회 연속 실패 (스킬 §레드 플래그의 "2회가 상한")
  - `--max-solves` 소진 (기본 20 — 폭주 방지 백스톱)
  - `차단감지` (캡챠가 아니다. 쉬었다 재개해야 한다)

사용:
    python lookup_loop.py --run-dir <R> [--max-solves 20] [--rest-every 5]
"""
import argparse
import json
import os
import subprocess
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILLS = os.path.dirname(os.path.dirname(SCRIPT_DIR))
ROOT = os.path.dirname(os.path.dirname(SKILLS))
PY = os.path.join(ROOT, ".venv", "bin", "python")
CAT = os.path.join(SKILLS, "aside-category", "scripts", "aside_category.py")
RELAY = os.path.join(SKILLS, "captcha-relay", "scripts", "captcha_relay.py")

# captcha_relay 종료코드 — 스킬 §종료코드 = 다음 행동
RELAY_OK, RELAY_HUMAN, RELAY_TIMEOUT = 0, 3, 4


def _log(msg):
    print(msg, flush=True)


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _blocked(results):
    """결과에서 캡챠·차단 건을 뽑는다 → (캡챠 레코드 | None, 차단여부)."""
    cap, blk = None, False
    for r in results:
        st = str(r.get("상태") or "")
        if st == "캡챠감지" and cap is None:
            cap = r
        elif st == "차단감지":
            blk = True
    return cap, blk


def _remaining(askable, results):
    done = {r.get("productId") for r in results if r.get("상태") == "성공"}
    return [a for a in askable if a.get("productId") not in done]


def run_lookup(inp, out, rest_every, rest_secs, sleep, sleep_max):
    cmd = [PY, CAT, "--input", inp, "--output", out, "--resume",
           "--sleep", str(sleep), "--sleep-max", str(sleep_max)]
    if rest_every:
        cmd += ["--rest-every", str(rest_every), "--rest-secs", str(rest_secs)]
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run(cmd, env=env).returncode


def solve(url):
    """릴레이로 캡챠 1건. 반환 = 종료코드."""
    # --match 는 검색어 인코딩까지 넣어 좁힌다 — 넓게 주면 옛 검색결과 탭을 찍어 보낸다
    # (captcha-relay SKILL.md ★2026-08-10 실측).
    match = url.split("?", 1)[1] if "?" in url else url
    match = match[:40]
    cmd = [PY, RELAY, "solve", "--url", url, "--match", match, "--submit"]
    return subprocess.run(cmd).returncode


def main():
    ap = argparse.ArgumentParser(description="캡챠 자동 릴레이 조회 루프")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--input", default=None, help="기본 <run-dir>/keywords_askable.json")
    ap.add_argument("--output", default=None, help="기본 <run-dir>/sellha.json")
    ap.add_argument("--max-solves", type=int, default=20, help="캡챠 릴레이 상한(폭주 방지)")
    ap.add_argument("--rest-every", type=int, default=5, help="N청크마다 휴식(누적 총량 완화)")
    ap.add_argument("--rest-secs", type=int, default=120)
    ap.add_argument("--sleep", default="1")
    ap.add_argument("--sleep-max", default="3")
    ap.add_argument("--cooldown", type=int, default=60, help="캡챠 푼 뒤 재개 전 대기(초)")
    args = ap.parse_args()

    inp = args.input or os.path.join(args.run_dir, "keywords_askable.json")
    out = args.output or os.path.join(args.run_dir, "sellha.json")
    askable = _load(inp)

    solves, last_url, same = 0, None, 0
    for rnd in range(1, args.max_solves + 2):
        _log(f"\n{'=' * 56}\n[조회 {rnd}회차] 남은 {len(_remaining(askable, _load(out) if os.path.exists(out) else []))}건")
        run_lookup(inp, out, args.rest_every, args.rest_secs, args.sleep, args.sleep_max)

        results = _load(out) if os.path.exists(out) else []
        left = _remaining(askable, results)
        if not left:
            _log(f"\n[루프 종료] 전건 조회 완료 ({len(results)}건)")
            return 0

        cap, blk = _blocked(results)
        if blk:
            _log("\n[루프 중단] `차단감지` — 캡챠가 아니다. 시간을 두고 --resume 으로 재개할 것")
            return 6
        if not cap:
            _log(f"\n[루프 중단] 캡챠가 아닌 사유로 {len(left)}건이 남았다 "
                 "(조회실패·파싱실패). 재조회로는 안 풀린다")
            return 0   # 실패 사유가 캡챠가 아니면 남은 건 그대로 두고 다음 단계로 간다

        url = cap.get("url") or ""
        same = same + 1 if url == last_url else 1
        last_url = url
        if same > 2:
            _log(f"\n[루프 중단] 같은 캡챠 {same}회 실패 — 이룸님 판단 필요\n  {url}")
            return 3
        if solves >= args.max_solves:
            _log(f"\n[루프 중단] 캡챠 릴레이 상한 {args.max_solves}회 소진 · 남은 {len(left)}건")
            return 7

        solves += 1
        _log(f"\n[캡챠 {solves}/{args.max_solves}] {cap.get('검색어')} — 릴레이 요청")
        rc = solve(url)
        if rc == RELAY_HUMAN:
            _log("\n[루프 중단] `needs_human` — Aside 도 확신 못 했다. 재시도하지 않는다")
            return 3
        if rc == RELAY_TIMEOUT:
            _log("\n[루프 중단] `timeout` — 릴레이 루프 생존을 `ping` 으로 확인할 것")
            return 4
        if rc != RELAY_OK:
            _log(f"\n[루프 중단] 릴레이 실패 (exit {rc})")
            return 5
        _log(f"  풀림 — {args.cooldown}초 쉬고 재개")
        time.sleep(args.cooldown)

    _log("\n[루프 중단] 라운드 소진")
    return 7


if __name__ == "__main__":
    sys.exit(main())
