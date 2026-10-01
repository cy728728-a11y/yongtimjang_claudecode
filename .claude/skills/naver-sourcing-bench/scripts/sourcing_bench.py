# -*- coding: utf-8 -*-
"""네이버 사입 소싱 벤치마크 CLI.

    PY=.venv/bin/python; S=.claude/skills/naver-sourcing-bench/scripts/sourcing_bench.py
    $PY $S init --title "사입 소싱 후보"
    $PY $S login-check
    $PY $S scan --category "생활/건강>수납/정리용품"
    $PY $S bench --keyword "바지걸이"          # 또는 --from-scan
    $PY $S annotate --row 3 --volume 12000 --competition 낮음
"""
import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

import aside_bridge
import rules
import sheet_schema as S
from gws_sheet import GwsError, Sheet

HERE = Path(__file__).resolve().parent
RUNS = HERE.parent / "runs"
CONFIG = RUNS / "config.json"
MASTER = HERE.parents[3] / "30-knowledge" / "39-naver-category" / "naver-category-master.json"
SEC_LIST, SEC_DETAIL = 6.0, 5.0     # 페이지당 대략 소요(초) — 청크 계산용
STOP = ("캡챠감지", "차단감지")
LOGIN_MSG = ("네이버 로그인이 안 돼 있다. Aside 브라우저 창에서 네이버에 직접 로그인한 뒤 다시 실행해 줘.\n"
             "(아이디·비밀번호는 여기에 입력하지 않는다)")


def _load(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _save(path, data):
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError as e:
        print(f"[warn] 체크포인트 저장 실패: {e}", flush=True)


def _slug(s):
    return re.sub(r"[^\w가-힣]+", "_", s).strip("_")[:60]


def _chunks(items, n):
    for i in range(0, len(items), n):
        yield items[i:i + n]


def require_login(run=aside_bridge.run_driver):
    """Aside 의 네이버 로그인 여부. 미로그인이면 안내 후 종료코드 3."""
    try:
        res = run("login", [], {}, 60)
    except RuntimeError as e:
        print(f"Aside 실행 실패: {e}", flush=True)
        raise SystemExit(3)
    if not res or not res[0].get("loggedIn"):
        print(LOGIN_MSG, flush=True)
        raise SystemExit(3)


def do_scan(sheet, master, root_path, ckpt_path, run, date, opts):
    """세부 카테고리별 리뷰1000+ 상품 수를 세어 카테고리스캔 탭에 쓴다."""
    cats = rules.leaf_categories(master, root_path)
    ck = _load(ckpt_path, {"done": {}})
    todo = [c for c in cats if c["코드"] not in ck["done"]]
    stopped = False
    for chunk in _chunks(todo, aside_bridge.auto_chunk(len(todo), SEC_LIST, opts["sleepMax"])):
        for r in run("scan", [{"코드": c["코드"]} for c in chunk], opts, 115):
            if r.get("상태") in STOP:
                stopped = True
                break
            # 성공·결과없음만 확정. 파싱실패는 재실행 때 다시 연다.
            if r.get("상태") in ("성공", "조회실패"):
                ck["done"][r["key"]] = r
            else:
                print(f"[warn] {r.get('key')} {r.get('상태')}: {r.get('error') or ''} — 재실행 시 다시 시도", flush=True)
        _save(ckpt_path, ck)
        if stopped:
            break
    # 시트에 아직 없는 카테고리만, 리뷰1000+ 많은 순으로 기록
    have = {row[5] for row in sheet.read(S.SCAN_TAB) if len(row) > 5}
    rows = []
    for c in cats:
        page = ck["done"].get(c["코드"])
        if not page or c["코드"] in have:
            continue
        row = S.scan_row(date, c, rules.scan_summary(page.get("products") or []))
        if page.get("상태") != "성공":
            row[11] = f"{page.get('상태')}: {page.get('error') or ''}"
        rows.append(row)
    rows.sort(key=lambda r: r[6], reverse=True)
    n = sheet.append(S.SCAN_TAB, rows)
    if stopped:
        print("캡챠/차단으로 중단했다. Aside 창에서 확인 후 같은 명령을 다시 실행하면 이어서 한다.", flush=True)
        raise SystemExit(4)
    return n


def do_bench(sheet, keyword, ckpt_path, run, date, opts, with_options=True):
    """키워드 재검색 → 벤치 필터 → (옵션 수집) → 후보 탭 추가."""
    ck = _load(ckpt_path, {"page": None, "details": {}})
    if not ck["page"] or ck["page"].get("상태") != "성공":
        res = run("search", [{"키워드": keyword}], opts, 115)
        page = res[0] if res else {"상태": "파싱실패", "products": []}
        if page.get("상태") in STOP:
            print("캡챠/차단으로 중단했다.", flush=True)
            raise SystemExit(4)
        ck["page"] = page
        _save(ckpt_path, ck)
    if ck["page"].get("상태") != "성공":
        print(f"[warn] '{keyword}' 검색 {ck['page'].get('상태')}: {ck['page'].get('error') or ''} — 재실행 시 다시 검색",
              flush=True)
        return None
    picks = rules.bench_filter(ck["page"].get("products") or [])
    have = {rules.norm_url(r[6]) for r in sheet.read(S.BENCH_TAB) if len(r) > 6}
    picks = [p for p in picks if rules.norm_url(p["url"]) not in have]
    if with_options:
        need = [{"url": p["url"]} for p in picks if p["url"] not in ck["details"]]
        for chunk in _chunks(need, aside_bridge.auto_chunk(len(need), SEC_DETAIL, opts["sleepMax"])):
            stop = False
            try:
                details = run("detail", chunk, opts, 115)
            except RuntimeError as e:
                # 상세 드라이버가 없거나 Aside 실패 → 남은 상품은 옵션수동
                print(f"[warn] 옵션 수집 불가: {e} — 9·10열은 수동", flush=True)
                break
            for d in details:
                if d.get("상태") in STOP:
                    stop = True
                    break
                ck["details"][d["key"]] = d
            _save(ckpt_path, ck)
            if stop:
                print("상세 조회 중 캡챠/차단 — 남은 상품은 옵션수동으로 기록한다.", flush=True)
                break
    rows = []
    for p in picks:
        d = ck["details"].get(p["url"]) if with_options else None
        opts_ = d.get("options") if d and d.get("상태") == "성공" else None
        rows.append(S.bench_row(date, keyword, p, opts_))
    return sheet.append(S.BENCH_TAB, rows)


def bench_from_scan(sheet, ckpt_dir, run, date, opts, with_options=True):
    """카테고리스캔 탭에서 키워드가 있고 벤치완료가 빈 행을 일괄 처리."""
    total = 0
    kc, dc = S.SCAN_COL["키워드"], S.SCAN_COL["벤치완료"]
    for i, row in enumerate(sheet.read(S.SCAN_TAB)):
        row = row + [""] * (len(S.SCAN_HEADER) - len(row))
        kw = str(row[kc]).strip()
        if not kw or str(row[dc]).strip():
            continue
        n = do_bench(sheet, kw, Path(ckpt_dir) / f"bench-{_slug(kw)}.json", run, date, opts, with_options)
        if n is None:          # 검색 실패 — 벤치완료를 찍지 않아 다음 실행에 다시 잡힌다
            continue
        total += n
        sheet.set_cell(S.SCAN_TAB, i, dc, "Y")
    return total


def _sheet(args):
    sid = args.sheet or _load(CONFIG, {}).get("sheet_id")
    if not sid:
        sys.exit("시트 ID 가 없다. 먼저 `init` 을 실행하거나 --sheet 를 준다.")
    return Sheet(sid)


def build_parser():
    ap = argparse.ArgumentParser(description="네이버 사입 소싱 벤치마크")
    ap.add_argument("--sheet", help="스프레드시트 ID (기본: runs/config.json)")
    ap.add_argument("--sleep", type=float, default=3.0)
    ap.add_argument("--sleep-max", type=float, default=9.0)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    p.add_argument("--title", default="사입 소싱 후보")
    sub.add_parser("login-check")
    p = sub.add_parser("scan")
    p.add_argument("--category", required=True)
    p = sub.add_parser("bench")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--keyword")
    g.add_argument("--from-scan", action="store_true")
    # 2026-10-01 실측: 스마트스토어 옵션 데이터를 읽을 수 없어 기본은 끈다(9·10열 수동).
    p.add_argument("--options", action="store_true", help="상세 옵션 수집 시도(drivers/detail.js 필요)")
    p = sub.add_parser("annotate")
    p.add_argument("--row", type=int, required=True, help="카테고리스캔 탭의 시트 행 번호(헤더=1)")
    p.add_argument("--volume", default="")
    p.add_argument("--competition", default="")
    return ap


def main():
    args = build_parser().parse_args()

    opts = {"sleep": args.sleep, "sleepMax": args.sleep_max}
    date = dt.date.today().isoformat()
    try:
        if args.cmd == "init":
            sh = Sheet.create(args.title)
            _save(CONFIG, {"sheet_id": sh.sid})
            print(f"https://docs.google.com/spreadsheets/d/{sh.sid}")
        elif args.cmd == "login-check":
            require_login()
            print("네이버 로그인 확인됨")
        elif args.cmd == "scan":
            require_login()
            master = _load(MASTER, None)
            if not master:
                sys.exit(f"카테고리 마스터 없음: {MASTER} (naver-category-master 스킬로 갱신)")
            n = do_scan(_sheet(args), master, args.category,
                        RUNS / f"scan-{_slug(args.category)}.json", aside_bridge.run_driver, date, opts)
            print(f"카테고리스캔 {n}행 추가")
        elif args.cmd == "bench":
            require_login()
            sh = _sheet(args)
            if args.from_scan:
                n = bench_from_scan(sh, RUNS, aside_bridge.run_driver, date, opts, args.options)
            else:
                n = do_bench(sh, args.keyword, RUNS / f"bench-{_slug(args.keyword)}.json",
                             aside_bridge.run_driver, date, opts, args.options)
                if n is None:
                    sys.exit(1)
            print(f"후보 {n}행 추가")
        elif args.cmd == "annotate":
            sh = _sheet(args)
            sh.set_cell(S.SCAN_TAB, args.row - 2, S.SCAN_COL["검색량"], args.volume)
            sh.set_cell(S.SCAN_TAB, args.row - 2, S.SCAN_COL["경쟁도"], args.competition)
    except ValueError as e:
        print(f"입력 오류: {e}", flush=True)
        sys.exit(2)
    except (GwsError, RuntimeError) as e:
        print(f"실패: {e}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
