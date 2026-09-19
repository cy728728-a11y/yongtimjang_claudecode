#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""naver-ads-weekly 진입점.

    prep   전 계정 수집 → run-dir
    run    수집분으로 6개 규칙 판정 → result.json
    apply  시트 기록 + 보고서
    bids   ① 입찰 인상. --revert 로 before_bids 백업에서 되돌린다
    prune  ⑥ 꺼진 소재 삭제
    accounts  설정된 계정 목록(alias/customer_id)을 JSON 으로 찍는다. 읽기 전용

주간 배치(prep/run/apply)는 광고 API 에 아무것도 쓰지 않는다.
"""
import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ads_rules
import bids
import collect
import nvad
import prune
import report_md
import sheets_out

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


def cmd_apply(args):
    run_dir = run_dir_of(args.run_dir)
    rp = run_dir / "result.json"
    if not rp.exists():
        print("판정 결과가 없다 — 먼저 run 을 돌려라")
        return 1
    try:
        result = json.loads(rp.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"result.json 읽기 실패: {type(e).__name__}: {e}")
        return 1
    md = report_md.build_report(result)
    out = run_dir / "report.md"
    try:
        out.write_text(md, encoding="utf-8")
    except Exception as e:
        print(f"보고서 쓰기 실패: {type(e).__name__}: {e}")
        return 1
    if args.sheet and not args.no_sheet:
        print("시트 기록:")
        sheets_out.write_sheet(args.sheet, result)
    print(f"보고서 → {out}")
    return 0


def cmd_accounts(args):
    """설정된 계정 목록을 stdout 에 JSON 으로 찍는다. 읽기 전용, 네트워크 0.

    웹앱이 `~/.eroom/naver-ads.json` 을 **두 번째로 갖지 않게** 하려고 존재한다 —
    자격증명 파일을 읽는 코드는 이 저장소에서 `nvad.load_accounts()` 하나뿐이어야 한다.
    시크릿은 절대 출력하지 않는다 (SAFE-03).

    블랙리스트가 아니라 **화이트리스트 투영**이다 — 자격증명 파일에 새 키가 생겨도
    여기서 만드는 dict 에는 alias/customer_id 말고는 아무것도 담기지 않는다.
    계정이 0개여도 `[]` 를 찍고 0 을 돌려준다(웹앱이 "설정이 비었다"를 구분할 수 있게).
    """
    목록 = [{"alias": a.get("alias"), "customer_id": str(a.get("customer_id"))}
           for a in nvad.load_accounts()]
    print(json.dumps(목록, ensure_ascii=False))
    return 0


def _load_only_ads(path):
    """대상 adId 목록 파일을 집합으로 읽는다. 경로가 없으면 None(=전량).

    배열 `["nad-..."]` 과 `{"adIds": [...]}` 두 모양을 받는다.
    **예외를 잡지 않는다** — 호출부가 잡아서 중단한다(전량 폴백 금지, T-1-05).
    """
    if not path:
        return None
    ids = json.loads(Path(path).read_text(encoding="utf-8"))
    return set(ids if isinstance(ids, list) else ids["adIds"])


def _dump_preview(path, outputs):
    """계정별 계획/결과를 JSON 파일로 쓴다. 경로가 없으면 아무것도 안 한다. (종료코드)

    원자적 쓰기(tmp → os.replace)다 — 반쪽 JSON 이 남으면 다음 회차가 그걸
    `--only-ads` 로 읽어 엉뚱한 범위를 실행한다(T-1-13).
    `ensure_ascii=False` 는 예외 없이 붙인다 — 한국어 상품명이 `\\uXXXX` 로 깨지면 사람이 못 읽는다.
    """
    if not path:
        return 0
    try:
        tmp = str(path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(outputs, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except Exception as e:
        # 조용히 성공으로 끝내면 화면이 "결과 0건" 을 정상으로 읽는다.
        print(f"--preview-out 쓰기 실패: {type(e).__name__}: {e}")
        return 1
    return 0


def cmd_bids(args):
    run_dir = run_dir_of(args.run_dir)
    accts = {a.get("alias"): a for a in _accounts(args.account)}

    # Important 10 과 같은 방어 수준 — 돈이 나가는 명령이다.
    # 대상 파일이 깨졌을 때 전량으로 폴백하면 5건인 줄 알았던 게 2,242건이 된다(T-1-05).
    try:
        only = _load_only_ads(args.only_ads)
    except Exception as e:
        print(f"--only-ads 읽기 실패 — 전량 실행으로 폴백하지 않는다: {type(e).__name__}: {e}")
        return 1

    # 리턴값을 더 이상 버리지 않는다 — dry-run stdout 은 10건만 찍고 접으므로
    # 미리보기 표는 이 산출물로만 만들 수 있다(D-02).
    outputs = {}

    # Important 4: --revert 는 result.json 이 필요 없다 — before_bids 백업만 있으면 된다.
    if args.revert:
        for alias, acct in accts.items():
            outputs[alias] = bids.run_revert(acct, run_dir, commit=args.commit, only_ads=only)
        return _dump_preview(args.preview_out, outputs)

    rp = run_dir / "result.json"
    if not rp.exists():
        print("판정 결과가 없다 — 먼저 run 을 돌려라")
        return 1
    # Important 10: cmd_apply 와 같은 수준으로 읽기를 보호한다 — 돈이 나가는 명령이다.
    try:
        result = json.loads(rp.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"result.json 읽기 실패: {type(e).__name__}: {e}")
        return 1
    for alias, v in result.get("accounts", {}).items():
        acct = accts.get(alias)
        if not acct:
            # Important 2: 돈이 나가는 명령이니 자격증명 없어 건너뛴 계정도 로그에 남긴다
            print(f"[{alias}] 자격증명 없음 — 건너뛴다")
            continue
        outputs[alias] = bids.run_bids(acct, run_dir, v.get("rules", {}).get("①노출0", []),
                                       commit=args.commit, only_ads=only)
    return _dump_preview(args.preview_out, outputs)


def cmd_prune(args):
    run_dir = run_dir_of(args.run_dir)
    accts = {a.get("alias"): a for a in _accounts(args.account)}
    acc_dir = run_dir / "accounts"
    prepped = set(d.name for d in acc_dir.iterdir() if d.is_dir()) if acc_dir.exists() else set()
    # Minor 7: prep 이 만든 계정 목록만 돌면, 자격증명은 있는데 prep 디렉터리가 없는
    # 계정이 완전 무음으로 빠진다(구코드는 최소한 "소재 읽기 실패"를 찍었다) — I2 의
    # 요지가 "빠진 게 안 보이는 것" 이었으므로 그 자체를 어기는 셈이다. prep 된 계정과
    # 자격증명 있는 계정의 합집합을 돌아, 어느 쪽이 빠졌는지 각각 다른 문구로 남긴다.
    expected = args.account or sorted(prepped | set(accts))
    for alias in expected:
        acct = accts.get(alias)
        if not acct:
            print(f"[{alias}] 자격증명 없음 — 건너뛴다")
            continue
        if alias not in prepped:
            print(f"[{alias}] prep 없음 — 건너뛴다")
            continue
        prune.run_prune(acct, run_dir, commit=args.commit)
    return 0


def main():
    ap = argparse.ArgumentParser(description="네이버 검색광고 주간 관리")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("prep", "run", "apply"):
        s = sub.add_parser(name)
        s.add_argument("--run-dir", help="회차 이름(기본: 오늘 날짜)")
        s.add_argument("--account", nargs="*", help="특정 계정 alias 만")
    ap_apply = sub.choices["apply"]
    ap_apply.add_argument("--sheet", help="구글시트 ID (없으면 마크다운만)")
    ap_apply.add_argument("--no-sheet", action="store_true", help="원장 탭 쓰기만 막는다")
    s = sub.add_parser("bids")
    s.add_argument("--run-dir")
    s.add_argument("--account", nargs="*")
    s.add_argument("--commit", action="store_true", help="실제로 입찰가를 바꾼다")
    s.add_argument("--revert", action="store_true",
                   help="직전 인상을 before_bids 백업으로 되돌린다(스펙 §4.3)")
    s.add_argument("--only-ads", help="대상 adId 목록 JSON 파일 — 이 목록에 있는 소재만 처리한다")
    s.add_argument("--preview-out", help="계정별 계획/결과를 이 JSON 파일에 쓴다")
    sub.add_parser("accounts")   # 인자 없음. 읽기 전용, 시크릿 미출력
    s = sub.add_parser("prune")
    s.add_argument("--run-dir")
    s.add_argument("--account", nargs="*")
    s.add_argument("--commit", action="store_true", help="실제로 삭제한다(되돌릴 수 없다)")
    args = ap.parse_args()
    return {"prep": cmd_prep, "run": cmd_run, "apply": cmd_apply, "bids": cmd_bids,
            "prune": cmd_prune, "accounts": cmd_accounts}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
