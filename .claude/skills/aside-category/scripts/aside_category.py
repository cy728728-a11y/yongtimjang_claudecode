#!/usr/bin/env python3
"""Aside 브라우저로 네이버 가격비교를 열어 상품명/키워드의 카테고리 경로 + 확신도를 뽑는다.

sellha-category(scripts/sellha.py)의 대체재. CLI·반환 스키마를 그대로 맞춰
bulsaja-category-fix 등 기존 호출부가 옵션만 바꿔 붙일 수 있게 했다.

    python aside_category.py --query "무선마우스" "낚시텐트"
    python aside_category.py --input targets.json --output result.json --resume
"""

import argparse
import json
import os
import subprocess
import sys
import threading
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DRIVER = os.path.join(SCRIPT_DIR, "driver.js")
ASIDE_BIN = os.environ.get("ASIDE_BIN") or os.path.expanduser("~/.local/bin/aside")

# 재시도해도 의미 없는(=사람이 손봐야 하는) 상태
DEAD = {"성공"}

# `aside repl` 은 호출당 ~120초에서 연결이 끊긴다(fetch failed: other side closed).
# 게다가 stdout 이 호출 종료 시 한꺼번에 나와서, 초과하면 그때까지 조회한 결과도
# 전부 유실된다(실측 2026-08-04: 40건·20건 모두 120.2초에 0건 반환).
# 그래서 한 호출에 넣는 건수를 벽 아래로 묶고, 청크마다 output 에 즉시 적는다.
REPL_WALL_SEC = 120
SEC_PER_ITEM = 9.0          # 확신도 계산 포함 실측 8.7초/건
CHUNK_MARGIN = 0.65         # 벽의 65%만 쓴다 — 느린 건이 섞여도 안 터지게


def _load_json(path, default):
    """읽기 실패를 조용히 기본값으로 흘린다 — resume 이 부분 결과 때문에 죽으면 안 된다."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def build_items(args):
    """--query / --input 을 [{productId, name}] 로 정규화."""
    if args.query:
        return [{"productId": None, "name": q} for q in args.query]
    if not args.input:
        sys.exit("--query 또는 --input 중 하나는 있어야 한다")
    raw = _load_json(args.input, None)
    if raw is None:
        sys.exit(f"입력 JSON 을 읽지 못했다: {args.input}")
    items = []
    for it in raw:
        if isinstance(it, str):
            items.append({"productId": None, "name": it})
        else:
            items.append({"productId": it.get("productId"), "name": it.get("name") or it.get("상품명") or ""})
    return items


def _auto_chunk(count, sleep_max):
    """120초 벽 아래로 들어가는 한 호출당 건수. 최소 1건은 보장한다."""
    per = (SEC_PER_ITEM if count else 2.5) + (sleep_max or 0) / 2
    return max(1, int(REPL_WALL_SEC * CHUNK_MARGIN / per))


def _save(path, results):
    """output 이 지정된 경우에만 쓴다(콘솔 출력 모드는 무시)."""
    if not path:
        return
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


def _run_repl(js_template, chunk, opts, timeout):
    """청크 하나를 aside repl 로 조회. 결과 리스트(실패 시 빈 리스트)를 돌려준다."""
    js = (js_template.replace("__ITEMS__", json.dumps(chunk, ensure_ascii=False))
                     .replace("__OPTS__", json.dumps(opts)))
    results = []
    try:
        proc = subprocess.Popen([ASIDE_BIN, "repl", js], stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, bufsize=1)
    except OSError as e:
        print(f"[warn] aside 실행 실패: {e}", flush=True)
        return []

    killer = threading.Timer(timeout, proc.kill)
    killer.start()
    try:
        for line in proc.stdout:
            line = line.rstrip("\n")
            if line.startswith("__R__ "):
                try:
                    results.append(json.loads(line[6:]))
                except ValueError:
                    print(f"[warn] 결과 줄 파싱 실패: {line[:120]}", flush=True)
            elif line.strip() and not line.startswith("__DONE__"):
                print(line, flush=True)
    finally:
        killer.cancel()
        proc.wait()
    return results


def main():
    ap = argparse.ArgumentParser(description="Aside + 불사자 확장으로 네이버 카테고리 조회")
    ap.add_argument("--query", "-q", nargs="+", help="조회할 상품명/키워드(들)")
    ap.add_argument("--input", "-i", help='배치 입력 JSON: [{"productId":"..","name":".."}]')
    ap.add_argument("--output", "-o", help="결과 JSON 저장 경로")
    ap.add_argument("--resume", action="store_true",
                    help="output 의 성공건은 건너뛰고 실패건만 재시도")
    ap.add_argument("--no-count", action="store_true",
                    help="확신도 계산 생략(스크롤 안 함). 건당 ~9초 → ~2초, 확신도는 null")
    ap.add_argument("--sleep", type=float, default=1.0, help="조회 간 최소 대기(초)")
    ap.add_argument("--sleep-max", type=float, default=None, help="조회 간 최대 대기(초). 기본 sleep×3")
    ap.add_argument("--panel-tries", type=int, default=24,
                    help="확장 패널 대기 횟수(×0.5초). 기본 24 = 12초")
    ap.add_argument("--scroll-rounds", type=int, default=20, help="확신도 집계 시 최대 스크롤 횟수")
    ap.add_argument("--scroll-wait", type=int, default=600, help="스크롤 간 대기(ms)")
    ap.add_argument("--timeout", type=float, default=None, help="청크 타임아웃(초). 기본 = 건당 40초")
    ap.add_argument("--chunk", type=int, default=None,
                    help="repl 호출 1회에 넣을 건수. 기본 = 120초 벽 아래로 자동 계산(~8건)")
    # ── sellha.py 호환용(이 엔진에선 의미 없음). 호출부를 안 고쳐도 되게 받아만 준다 ──
    ap.add_argument("--profile", help="(무시) sellha 호환")
    ap.add_argument("--headless", action="store_true", help="(무시) sellha 호환")
    ap.add_argument("--debugger", help="(무시) sellha 호환")
    ap.add_argument("--restart-every", type=int, help="(무시) sellha 호환")
    # ── 여기부터는 실제로 동작한다(2026-08-06, 캡챠 실측 후 추가) ──
    ap.add_argument("--rest-every", type=int, default=0,
                    help="N청크마다 쉰다(0=안 쉼). 간격이 아니라 누적 조회량에 반응하는 "
                         "차단을 늦춘다. 예: --rest-every 5 --rest-secs 120")
    ap.add_argument("--rest-secs", type=float, default=120.0,
                    help="휴식 길이(초). 기본 120")
    ap.add_argument("--block-wait", type=float, help="(무시) sellha 호환")
    args = ap.parse_args()

    if not os.path.exists(ASIDE_BIN):
        sys.exit(f"aside CLI 를 찾지 못했다: {ASIDE_BIN}\n"
                 f"ASIDE_BIN 환경변수로 경로를 지정하거나 Aside 를 설치한다.")

    items = build_items(args)

    # resume: 기존 결과의 성공건은 재조회하지 않는다
    prior = []
    if args.resume and args.output and os.path.exists(args.output):
        prior = _load_json(args.output, [])
        done = {(r.get("productId"), r.get("검색어")) for r in prior if r.get("상태") in DEAD}
        before = len(items)
        items = [it for it in items if (it["productId"], it["name"]) not in done]
        print(f"[resume] 성공 {len(done)}건 건너뜀 · 남은 {len(items)}/{before}건", flush=True)

    if not items:
        print("[skip] 조회할 항목이 없다")
        if args.output:
            print(json.dumps(prior, ensure_ascii=False, indent=2))
        return

    opts = {
        "sleep": args.sleep,
        "sleepMax": args.sleep_max if args.sleep_max else args.sleep * 3,
        "count": not args.no_count,
        "panelTries": args.panel_tries,
        "scrollRounds": args.scroll_rounds,
        "scrollWait": args.scroll_wait,
    }

    try:
        with open(DRIVER, encoding="utf-8") as f:
            js = f.read()
    except OSError as e:
        sys.exit(f"driver.js 를 읽지 못했다: {e}")

    per_item = 12 if args.no_count else 40
    chunk_size = args.chunk or _auto_chunk(opts["count"], opts["sleepMax"])
    chunks = [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]

    print(f"[run] {len(items)}건 · 확신도 {'계산' if opts['count'] else '생략'} · "
          f"청크 {chunk_size}건 × {len(chunks)}회", flush=True)

    key = lambda r: (r.get("productId"), r.get("검색어"))  # noqa: E731
    acc = {key(r): r for r in prior}   # 기존 성공건 + 이번 결과(같은 키는 새 결과로 덮어씀)
    got, failed = 0, []

    for n, chunk in enumerate(chunks, 1):
        timeout = args.timeout or max(120, per_item * len(chunk))
        res = []
        for attempt in (1, 2):
            res = _run_repl(js, chunk, opts, timeout)
            if res:
                break
            print(f"[warn] 청크 {n}/{len(chunks)} 실패 (시도 {attempt}/2) — "
                  f"Aside 데몬 응답 없음", flush=True)
        if not res:
            failed.append(n)
            continue
        acc.update({key(r): r for r in res})
        got += len(res)
        # 청크마다 즉시 적는다 — 다음 청크에서 죽어도 여기까지는 남는다
        _save(args.output, list(acc.values()))
        print(f"[chunk {n}/{len(chunks)}] {len(res)}/{len(chunk)}건 · 누적 {got}건", flush=True)

        # 캡챠가 뜨면 driver 가 그 청크를 즉시 끊는다(계속 두드릴수록 악화되므로).
        # 다음 청크로 넘어가면 같은 상태에서 또 두드리는 셈이라 여기서 멈춘다.
        if any(r.get("상태") in ("캡챠감지", "차단감지") for r in res):
            print(f"[stop] 캡챠·차단 감지 — 남은 청크 {len(chunks) - n}개를 돌지 않는다. "
                  f"캡챠는 captcha-relay 스킬(captcha_relay.py solve --submit)로 푼 뒤, "
                  f"차단은 시간을 두고 --resume 으로 이어서 돌린다.", flush=True)
            failed.extend(range(n + 1, len(chunks) + 1))
            break

        # 청크 사이 휴식 — 조회 **간격**이 아니라 누적 **총량**에 반응하는 차단을 늦춘다.
        # 간격(`--sleep`)만 늘리면 건당 시간만 길어지고 연속 조회는 그대로다.
        if args.rest_every and n % args.rest_every == 0 and n < len(chunks):
            print(f"[rest] {args.rest_every}청크마다 {args.rest_secs:.0f}초 휴식", flush=True)
            time.sleep(args.rest_secs)

    if not got:
        sys.exit("결과가 비어 있다. Aside 브라우저가 떠 있는지, 불사자 확장과 "
                 "네이버 로그인이 살아 있는지 확인한다.")

    results = list(acc.values())
    if args.output:
        _save(args.output, results)
        ok = sum(1 for r in results if r.get("상태") == "성공")
        multi = sum(1 for r in results if len(r.get("후보목록") or []) > 1)
        print(f"\n[done] {args.output} · 성공 {ok}/{len(results)}건 · 다순위 {multi}건")
    else:
        print("\n" + json.dumps(results, ensure_ascii=False, indent=2))

    if failed:
        print(f"[warn] 실패 청크 {len(failed)}개 — --resume 으로 다시 돌리면 그 건만 재조회한다",
              flush=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
