# -*- coding: utf-8 -*-
"""네이버 사입 소싱 벤치마크 CLI.

    PY=.venv/bin/python; S=.claude/skills/naver-sourcing-bench/scripts/sourcing_bench.py
    $PY $S init --title "사입 소싱 후보"
    $PY $S login-check
    $PY $S scan --category "생활/건강>수납/정리용품"
    $PY $S bench --keyword "바지걸이"          # 또는 --from-scan. 옵션(9·10열) 자동 수집, --no-options 로 끔
    $PY $S options --keyword "바지걸이"        # 기존 후보 행에 옵션 채우기, 15조합 초과 행 삭제
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
SEC_LIST = 6.0                      # 목록 페이지당 대략 소요(초) — 청크 계산용
SEC_OPTIONS = 20.0                  # 상세 옵션 읽기 상품당(초). 다단 클릭을 감안 (2026-10-02 실측 10~15초)
MAX_COMBOS = rules.MAX_COMBOS       # 15 초과 = 소싱 대상 아님
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
    if with_options and _read_options([p["url"] for p in picks], ck, run, opts, ckpt_path):
        # 행을 하나도 추가하기 전에 멈춘다 — 재실행하면 체크포인트부터 이어간다
        print("상세 옵션 조회 중 캡챠/차단으로 중단했다. Aside 창에서 확인 후 같은 명령을 다시 실행하면 이어서 한다.",
              flush=True)
        raise SystemExit(4)
    rows, over = [], 0
    for p in picks:
        options = None
        d = ck["details"].get(p["url"]) if with_options and not rules.is_catalog(p["url"]) else None
        if d is not None:
            j = rules.build_options(d, rules.to_int(p.get("가격")))
            if j["판정"] == "옵션초과":
                over += 1                      # D-01: 후보에 넣지 않는다
                continue
            if j["판정"] == "성공":
                options = j["options"]
        # 카탈로그·실패·미수집 → options=None → bench_row 가 옵션수동 (D-03)
        rows.append(S.bench_row(date, keyword, p, options))
    if over:
        print(f"옵션 {MAX_COMBOS}조합 초과 {over}건은 후보에서 뺐다.", flush=True)
    return sheet.append(S.BENCH_TAB, rows)


def _read_options(urls, ck, run, opts, ckpt_path):
    """상세페이지 옵션 원시 결과를 ck['details'] 에 모은다. 캡챠/차단이면 True(중단 신호).
    카탈로그·이미 받은 URL 은 건너뛴다. repl 타임아웃으로 일부만 돌아오면 나머지를 다시 넣고,
    한 건도 못 받으면 무한 반복하지 않도록 멈춘다(남은 건 미수집 = 옵션수동)."""
    todo, seen = [], set()
    for u in urls:
        if not u or rules.is_catalog(u) or u in ck["details"] or u in seen:
            continue
        seen.add(u)
        todo.append(u)
    if not todo:
        return False
    dopts = {**opts, "maxCombos": MAX_COMBOS}
    n = aside_bridge.auto_chunk(len(todo), SEC_OPTIONS, opts.get("sleepMax", 0))
    while todo:
        chunk, todo = todo[:n], todo[n:]
        try:
            res = run("options", [{"url": u} for u in chunk], dopts, 115)
        except RuntimeError as e:
            print(f"[warn] 옵션 수집 불가: {e} — 남은 상품은 9·10열 수동", flush=True)
            return False
        got = 0
        for d in res or []:
            if d.get("상태") in STOP:
                _save(ckpt_path, ck)
                return True
            if d.get("key"):
                ck["details"][d["key"]] = d
                got += 1
        _save(ckpt_path, ck)
        if not got:
            print(f"[warn] 옵션 조회 응답 없음 — 남은 {len(chunk) + len(todo)}건은 9·10열 수동(재실행 시 다시 시도)",
                  flush=True)
            return False
        todo = [u for u in chunk if u not in ck["details"]] + todo
    return False


def do_refill(sheet, keyword, ckpt_path, run, opts):
    """기존 후보 행에 옵션(9·10열)을 다시 채운다. 15조합 초과 행은 삭제.
    대상 = 키워드 일치 + 9열 빈칸 + 카탈로그 아님. 반환 {채움, 삭제, 수동, 건너뜀}."""
    ck = _load(ckpt_path, {"details": {}})
    ck.setdefault("details", {})
    width = len(S.BENCH_HEADER)
    targets, skipped = [], 0
    for i, r in enumerate(sheet.read(S.BENCH_TAB)):
        r = list(r) + [""] * (width - len(r))
        if str(r[4]).strip() != keyword:
            continue
        url = str(r[6]).strip()
        if str(r[8]).strip() or not url or rules.is_catalog(url):
            skipped += 1
            continue
        targets.append((i, url, r))
    stopped = _read_options([u for _, u, _ in targets], ck, run, opts, ckpt_path)

    cells, over_urls, manual = [], set(), 0
    for i, url, r in targets:
        d = ck["details"].get(url)
        j = rules.build_options(d, rules.to_int(r[S.COL_REP])) if d is not None else {"판정": "실패"}
        if j["판정"] == "성공":
            o = j["options"]
            cells += [(i, 8, len(o)),
                      (i, S.COL_REP, rules.rep_price(o, rules.to_int(r[S.COL_REP]))), (i, S.COL_STATUS, "")]
        elif j["판정"] == "옵션초과":
            over_urls.add(rules.norm_url(url))
        else:
            manual += 1                        # 옵션수동 유지 (D-03)
    # 1) 읽은 시점 인덱스가 유효할 때 칸부터 채운다
    sheet.update_cells(S.BENCH_TAB, cells)
    # 2) 삭제는 시트를 다시 읽어 URL 로 현재 위치를 찾는다 — 그 사이 행이 밀렸어도 엉뚱한 행을 지우지 않게 (T-mbo-02)
    deleted = 0
    if over_urls:
        idx = [i for i, r in enumerate(sheet.read(S.BENCH_TAB))
               if len(r) > 6 and str(r[4]).strip() == keyword and rules.norm_url(r[6]) in over_urls]
        sheet.delete_rows(S.BENCH_TAB, idx)
        deleted = len(idx)
    result = {"채움": len(cells) // 3, "삭제": deleted, "수동": manual, "건너뜀": skipped}
    if stopped:
        print(f"옵션 채움 {result['채움']} · 삭제 {deleted} 까지 반영하고 캡챠/차단으로 중단했다. "
              "Aside 창에서 확인 후 같은 명령을 다시 실행하면 이어서 한다.", flush=True)
        raise SystemExit(4)
    return result


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
    # 2026-10-02 실측: 상세페이지 DOM 에서 옵션을 펼쳐 읽을 수 있어 기본으로 켠다.
    p.add_argument("--no-options", action="store_true", help="상세 옵션 수집을 건너뛴다(9·10열 수동)")
    p = sub.add_parser("options", help="기존 후보 행에 옵션(9·10열) 채우기, 15조합 초과 행 삭제")
    p.add_argument("--keyword", required=True)
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
            with_options = not args.no_options
            if args.from_scan:
                n = bench_from_scan(sh, RUNS, aside_bridge.run_driver, date, opts, with_options)
            else:
                n = do_bench(sh, args.keyword, RUNS / f"bench-{_slug(args.keyword)}.json",
                             aside_bridge.run_driver, date, opts, with_options)
                if n is None:
                    sys.exit(1)
            print(f"후보 {n}행 추가")
        elif args.cmd == "options":
            require_login()
            r = do_refill(_sheet(args), args.keyword, RUNS / f"options-{_slug(args.keyword)}.json",
                          aside_bridge.run_driver, opts)
            print(f"옵션 채움 {r['채움']} · 삭제 {r['삭제']}({MAX_COMBOS}초과) · 수동 {r['수동']} · 건너뜀 {r['건너뜀']}")
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
