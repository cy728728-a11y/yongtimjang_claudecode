#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""naver-ads-weekly 진입점.

    prep   전 계정 수집 → run-dir
    run    수집분으로 6개 규칙 판정 → result.json
    apply  시트 기록 + 보고서 (Task 7·8 에서 채운다)
    bids   ① 입찰 인상 (Task 9)
    prune  ⑥ 꺼진 소재 삭제 (Task 10)

주간 배치(prep/run/apply)는 광고 API 에 아무것도 쓰지 않는다.
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ads_rules
import collect
import nvad

# eroomlib 찾기 — 스크립트 위치에서 위로 올라가며 lib/eroomlib 를 찾는다.
# 절대경로를 박으면 다른 PC·배포본에서 조용히 폴백돼 workspace.toml 이 영영 안 읽힌다
# (bulsaja-thumbnail·sellerlife-keyword 가 쓰는 저장소 관례).
_d = str(Path(__file__).resolve().parent)
while _d and _d != str(Path(_d).parent):
    _lib = str(Path(_d) / "lib")
    if (Path(_lib) / "eroomlib").is_dir():
        if _lib not in sys.path:
            sys.path.insert(0, _lib)
        break
    _d = str(Path(_d).parent)


def data_root():
    """경로를 코드에 박지 않는다 — workspace.toml 을 먼저 본다."""
    try:
        from eroomlib.config import cfg
        p = cfg("paths.data_root")
        if p:
            return Path(p).expanduser()
    except Exception:
        pass
    return Path.home() / "python_work" / "data"


def run_dir_of(name=None):
    d = data_root() / "naver-ads" / "runs" / (name or date.today().isoformat())
    d.mkdir(parents=True, exist_ok=True)
    return d


def _accounts(only=None):
    accts = nvad.load_accounts()
    if only:
        accts = [a for a in accts if a.get("alias") in only]
    return accts


def cmd_prep(args):
    run_dir = run_dir_of(args.run_dir)
    accts = _accounts(args.account)
    if not accts:
        print("계정이 없다 — ~/.eroom/naver-ads.json 을 확인해라")
        return 1
    summaries = {}
    for a in accts:
        try:
            summaries[a.get("alias")] = collect.collect_account(a, run_dir)
        except Exception as e:
            print(f"[{a.get('alias')}] 수집 실패: {type(e).__name__}: {e}")
    # --account 로 계정을 나눠 여러 번 돌릴 수 있다 — 덮어쓰면 마지막 것만 남는다
    sp = run_dir / "prep_summary.json"
    try:
        merged = json.loads(sp.read_text(encoding="utf-8"))
    except Exception:
        merged = {}
    merged.update(summaries)
    sp.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n수집 완료 → {run_dir}")
    return 0


def cmd_run(args):
    run_dir = run_dir_of(args.run_dir)
    acc_dir = run_dir / "accounts"
    if not acc_dir.exists():
        print("수집 결과가 없다 — 먼저 prep 을 돌려라")
        return 1
    out = {"generated": date.today().isoformat(), "accounts": {}}
    for d in sorted(acc_dir.iterdir()):
        if not d.is_dir():
            continue
        try:
            adsdata = json.loads((d / "ads.json").read_text(encoding="utf-8"))
            s7 = json.loads((d / "stats_7d.json").read_text(encoding="utf-8"))
            s30 = json.loads((d / "stats_30d.json").read_text(encoding="utf-8"))
            pur = json.loads((d / "purchase.json").read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[{d.name}] 읽기 실패: {type(e).__name__}: {e}")
            continue
        rules = ads_rules.classify(adsdata["ads"], adsdata["groups"], s7, s30, pur)
        # 요약을 규칙과 형제로 분리한다 — 규칙 dict 안에 규칙 아닌 키가 섞여 있으면
        # 순회하는 쪽마다 밑줄 가드를 기억해야 하고, 한 번만 잊어도 조용히 틀린다
        summary = rules.pop("_summary", {})
        out["accounts"][d.name] = {"summary": summary, "rules": rules}
        print(f"[{d.name}] " + " · ".join(f"{k} {len(v)}" for k, v in rules.items()))
    (run_dir / "result.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n판정 완료 → {run_dir / 'result.json'}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="네이버 검색광고 주간 관리")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("prep", "run"):
        s = sub.add_parser(name)
        s.add_argument("--run-dir", help="회차 이름(기본: 오늘 날짜)")
        s.add_argument("--account", nargs="*", help="특정 계정 alias 만")
    args = ap.parse_args()
    return {"prep": cmd_prep, "run": cmd_run}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
