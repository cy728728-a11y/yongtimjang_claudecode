#!/usr/bin/env python3
"""캠페인 수집 완료 감지 — 상품 수가 더 늘지 않으면 완료로 보고 스냅샷을 저장한다.

  campaign_watch.py --campaign ID --run-dir R [--interval 600] [--stable 3] [--max-hours 48]

완료 기준: 조회한 상품 수가 1건 이상이고 마지막 --stable 번 연속 같을 때.
완료되면 <R>/snapshot.json · run_meta.json({campaign,count,completed_at}) 저장 후 종료코드 0.
  종료코드 2 = 웹 토큰 만료(401) → web_token.py 다시 실행 / 3 = --max-hours 초과.
조회마다 <R>/watch.log 에 시각·건수를 적는다. 네트워크 실패는 로그만 남기고 다음 주기에 다시 본다.
무인 실행 때는 caffeinate -i 와 완료 감시(watcher)를 같이 건다(메모리 never-launch-without-watcher).
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_inspect import resolve_run_dir, _save, _p  # noqa: E402


def is_complete(history, stable):
    """history = 조회한 상품 수 목록(시간순). 마지막 stable 개가 모두 같고 0보다 크면 완료."""
    if stable < 1 or len(history) < stable:
        return False
    tail = history[-stable:]
    return tail[0] > 0 and all(x == tail[0] for x in tail)


def _log(run, msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(f"[watch] {line}", flush=True)
    try:
        os.makedirs(run, exist_ok=True)
        with open(_p(run, "watch.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError as e:
        print(f"[watch] 로그 기록 실패: {e}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description="캠페인 수집 완료 감지")
    ap.add_argument("--campaign", required=True)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--interval", type=int, default=600, help="조회 간격(초)")
    ap.add_argument("--stable", type=int, default=3, help="연속 같은 횟수")
    ap.add_argument("--max-hours", type=float, default=48)
    a = ap.parse_args()
    from sourcing_api import fetch_products, load_token
    run = resolve_run_dir(a.run_dir)
    history, started = [], time.time()
    items = None
    while True:
        try:
            tok = load_token()
            items = fetch_products(a.campaign, tok)
            history.append(len(items))
            _log(run, f"{a.campaign} 상품 {len(items)}건")
        except RuntimeError as e:
            if "401" in str(e):
                _log(run, f"토큰 만료: {e}")
                sys.exit(2)
            _log(run, f"조회 실패(다음 주기 재시도): {e}")
        except Exception as e:  # 네트워크 등
            _log(run, f"조회 오류(다음 주기 재시도): {e}")
        if items is not None and is_complete(history, a.stable):
            _save(_p(run, "snapshot.json"), items)
            _save(_p(run, "run_meta.json"), {"campaign": a.campaign, "count": len(items),
                                             "completed_at": time.strftime("%Y-%m-%d %H:%M:%S")})
            _log(run, f"완료 — snapshot.json {len(items)}건 저장")
            return 0
        if (time.time() - started) > a.max_hours * 3600:
            _log(run, f"{a.max_hours}시간 넘어도 완료 안 됨 — 종료")
            sys.exit(3)
        time.sleep(a.interval)


if __name__ == "__main__":
    sys.exit(main())
