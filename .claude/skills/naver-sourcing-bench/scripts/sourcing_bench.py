# -*- coding: utf-8 -*-
"""네이버 사입 소싱 벤치마크 CLI.

    PY=.venv/bin/python; S=.claude/skills/naver-sourcing-bench/scripts/sourcing_bench.py
    $PY $S init --title "사입 소싱 후보"
    $PY $S login-check
    $PY $S scan --category "생활/건강>수납/정리용품"
    $PY $S bench --keyword "바지걸이"          # 또는 --from-scan. 옵션(9·10열) 자동 수집, --no-options 로 끔
                                              # 원산지 중국만 · 스토어 확장 기본, --no-expand 로 확장 끔
    $PY $S options --keyword "바지걸이"        # 기존 후보 행에 옵션 채우기, 15조합 초과 행 삭제
    $PY $S expand --keyword "바지걸이"         # 기존 후보 행에 스토어 확장 소급 (--all, --dry-run, --no-options)
    $PY $S origin --all --dry-run             # 기존 후보 행 원산지 리포트(시트 불변). --dry-run 없으면 비중국 행 삭제
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
SEC_STORE = 10.0                    # 스토어 목록 1페이지(상품 열기 포함) 소요(초) — 2026-10-08 실측 3~6초, 2배 여유
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


def _origin_of(ck, url):
    """옵션 수집 때 같은 방문에서 읽은 원산지 원문 → 중국 | 제외 | 미확인."""
    return rules.origin_verdict((ck["details"].get(url) or {}).get("origin"))


def do_bench(sheet, keyword, ckpt_path, run, date, opts, with_options=True,
             expand=False, check_origin=False, expanded=None):
    """키워드 재검색 → 벤치 필터 → (옵션 수집) → (원산지 판정) → (스토어 확장) → 후보 탭 추가.
    expand·check_origin 의 함수 기본값은 False(기존 동작) — CLI 는 기본으로 둘 다 켠다.
    expanded = 이번 실행에서 이미 확장한 스토어 base 집합(bench_from_scan 이 키워드 사이에 공유)."""
    ck = _load(ckpt_path, {"page": None, "details": {}})
    ck.setdefault("details", {})
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
    # 중복은 상품번호 기준 — 검색은 main/products/<id>, 스토어 목록은 <slug>/products/<id> 라서
    have = {rules.product_key(r[6]) for r in sheet.read(S.BENCH_TAB) if len(r) > 6}
    picks = [p for p in picks if rules.product_key(p["url"]) not in have]
    if with_options and _read_options([p["url"] for p in picks], ck, run, opts, ckpt_path):
        # 행을 하나도 추가하기 전에 멈춘다 — 재실행하면 체크포인트부터 이어간다
        print("상세 옵션 조회 중 캡챠/차단으로 중단했다. Aside 창에서 확인 후 같은 명령을 다시 실행하면 이어서 한다.",
              flush=True)
        raise SystemExit(4)
    originals, over, not_cn = [], 0, 0
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
        unknown = False
        if check_origin:
            # 상세를 안 열었으면(--no-options·미수집) 원산지를 모른다 → 제외하지 않고 미확인 병기 (D-ORIGIN)
            v = _origin_of(ck, p["url"]) if d is not None else "미확인"
            if v == "제외":
                not_cn += 1
                continue
            unknown = v == "미확인"
        # 카탈로그·실패·미수집 → options=None → bench_row 가 옵션수동 (D-03)
        originals.append((p, S.bench_row(date, keyword, p, options, origin_unknown=unknown)))
    if over:
        print(f"옵션 {MAX_COMBOS}조합 초과 {over}건은 후보에서 뺐다.", flush=True)
    if not_cn:
        print(f"원산지가 중국이 아닌 {not_cn}건은 후보에서 뺐다.", flush=True)
    ext = {}
    if expand and originals:
        taken = have | {rules.product_key(p["url"]) for p in picks}
        stopped, ext = _expand_rows([(p, keyword) for p, _ in originals], ck, run, opts, ckpt_path, date,
                                    taken, expanded if expanded is not None else set(), with_options,
                                    check_origin)
        if stopped:
            print("스토어 확장 중 캡챠/차단으로 중단했다. Aside 창에서 확인 후 같은 명령을 다시 실행하면 이어서 한다.",
                  flush=True)
            raise SystemExit(4)
        n_ext = sum(len(v) for v in ext.values())
        if n_ext:
            print(f"스토어 확장 {n_ext}행", flush=True)
    rows = []
    for p, row in originals:
        rows.append(row)                       # 원 상품 → 그 스토어 확장 행 → 다음 원 상품
        rows += ext.get(p["url"], [])
    return sheet.append(S.BENCH_TAB, rows)


def _fetch_stores(jobs, ck, run, opts, ckpt_path):
    """jobs=[(url, base)] 의 스토어 목록을 ck['stores'][url] 에 모은다. 캡챠/차단이면 True(중단 신호).
    성공·미지원만 저장(확정), 파싱실패는 다음 실행에 다시 연다. Aside 실패는 경고 후 확장만 건너뛴다."""
    stores = ck.setdefault("stores", {})
    todo = [(u, b) for u, b in jobs if u not in stores]
    if not todo:
        return False
    n = aside_bridge.auto_chunk(len(todo), SEC_STORE, opts.get("sleepMax", 0))
    while todo:
        chunk, todo = todo[:n], todo[n:]
        try:
            res = run("store", [{"url": u, "base": b} for u, b in chunk], opts, 115)
        except RuntimeError as e:
            print(f"[warn] 스토어 확장 불가: {e} — 확장만 건너뛴다", flush=True)
            return False
        got = 0
        for r in res or []:
            st = r.get("상태")
            if st in STOP:
                _save(ckpt_path, ck)
                return True
            if not r.get("key"):
                continue
            got += 1
            if st in ("성공", "미지원"):
                stores[r["key"]] = r
            else:
                print(f"[warn] 스토어 {r.get('key')} {st}: {r.get('error') or ''} — 재실행 시 다시 시도", flush=True)
        _save(ckpt_path, ck)
        if not got:
            print(f"[warn] 스토어 조회 응답 없음 — 남은 {len(chunk) + len(todo)}건은 확장 생략(재실행 시 다시 시도)",
                  flush=True)
            return False
        # repl 벽으로 응답을 못 받은 것만 다시 넣는다(파싱실패는 다음 실행 몫)
        answered = {x.get("key") for x in res or []}
        todo = [(u, b) for u, b in chunk if u not in answered] + todo
    return False


def _expand_rows(origins, ck, run, opts, ckpt_path, date, taken, expanded, with_options, check_origin=False):
    """원 상품들의 판매자 스토어를 훑어 확장 행을 만든다. 반환 (stopped, {원 url: [확장 행]}).
    origins=[(원 product dict, keyword)] — 이미 추가가 확정된 원 행만. 확장 행은 다시 확장하지 않는다(재귀 금지).
    taken(product_key 집합)과 expanded(스토어 base 집합)는 호출부와 공유하며 여기서 갱신된다."""
    ck.setdefault("details", {})
    ck.setdefault("stores", {})
    jobs, seen_base = [], set()
    for p, kw in origins:
        url = p["url"]
        base = (rules.store_base((ck["details"].get(url) or {}).get("href")) or rules.store_base(url) or "")
        if base and (base in expanded or base in seen_base):
            continue                           # 스토어당 1회
        if base:
            seen_base.add(base)
        jobs.append((p, kw, url, base))
    if _fetch_stores([(u, b) for _, _, u, b in jobs], ck, run, opts, ckpt_path):
        return True, {}

    plan = []                                   # [(원 url, keyword, 후보 product 들)]
    for p, kw, url, base in jobs:
        res = ck["stores"].get(url)
        if not res:
            continue
        if res.get("상태") != "성공":
            print(f"[warn] 스토어 확장 건너뜀({res.get('상태')}): {p.get('마켓명', '')} {res.get('error') or ''}",
                  flush=True)
            continue
        b = res.get("base") or base
        if b and b in expanded:                 # 드라이버가 base 를 새로 구한 경우 다시 확인
            continue
        if b:
            expanded.add(b)
        cands = rules.store_filter(rules.store_products(res, p.get("마켓명", "")), taken)
        for c in cands:
            taken.add(rules.product_key(c["url"]))
        plan.append((url, kw, cands))

    # 목록 단계 원산지로 이미 걸러진 상품은 상세를 열지 않는다(store_filter) — 남은 것만 연다
    if with_options and _read_options([c["url"] for _, _, cs in plan for c in cs], ck, run, opts, ckpt_path):
        return True, {}

    out = {}
    for url, kw, cands in plan:
        rows = []
        for c in cands:
            d = ck["details"].get(c["url"]) if with_options else None
            v = rules.origin_verdict((d or {}).get("origin") or c.get("원산지"))
            if check_origin and v == "제외":
                continue
            options = None
            if d is not None:
                j = rules.build_options(d, rules.to_int(c.get("가격")))
                if j["판정"] == "옵션초과":
                    continue
                if j["판정"] == "성공":
                    options = j["options"]
            rows.append(S.bench_row(date, kw, c, options, status="스토어확장",
                                    origin_unknown=check_origin and v == "미확인"))
        if rows:
            out[url] = rows
    return False, out


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


def _pad(r):
    return list(r) + [""] * (len(S.BENCH_HEADER) - len(r))


def _is_store_url(url):
    return rules.product_key(url).startswith("nv:")


def do_expand(sheet, keyword, ckpt_path, run, date, opts, with_options=True, check_origin=True, dry_run=False):
    """기존 후보 행에 스토어 확장을 소급 적용한다. keyword=None 이면 전 키워드.
    대상 = 키워드 일치 · 상태에 스토어확장 없음 · 카탈로그 아님 · 네이버 스토어 URL, 마켓명당 1건.
    이미 그 마켓명으로 스토어확장 행이 있으면 건너뛴다. 결과는 시트 끝에 원 행 순서대로 블록 append
    (Sheet 에 행 삽입 API 가 없고 수식은 ROW() 상대참조라 위치와 무관).
    원 행 자체의 원산지는 여기서 판정하지 않는다 — origin 명령 몫. 반환 {스토어, 추가, 건너뜀, 내역}."""
    ck = _load(ckpt_path, {"details": {}, "stores": {}})
    ck.setdefault("details", {})
    ck.setdefault("stores", {})
    rows = [_pad(r) for r in sheet.read(S.BENCH_TAB)]
    taken = {rules.product_key(r[6]) for r in rows if str(r[6]).strip()}
    done_malls = {str(r[5]).strip() for r in rows if "스토어확장" in str(r[S.COL_STATUS])}
    origins, seen_malls, skipped = [], set(), 0
    for r in rows:
        if keyword is not None and str(r[4]).strip() != keyword:
            continue
        url, mall = str(r[6]).strip(), str(r[5]).strip()
        if "스토어확장" in str(r[S.COL_STATUS]) or not url or rules.is_catalog(url) or not _is_store_url(url) \
                or mall in done_malls or mall in seen_malls:
            skipped += 1
            continue
        seen_malls.add(mall)
        origins.append(({"url": url, "마켓명": mall, "상품명": r[7]}, str(r[4]).strip()))
    stopped, ext = _expand_rows(origins, ck, run, opts, ckpt_path, date, taken, set(), with_options, check_origin)
    if stopped:
        print("스토어 확장 중 캡챠/차단으로 중단했다. Aside 창에서 확인 후 같은 명령을 다시 실행하면 이어서 한다.",
              flush=True)
        raise SystemExit(4)
    out, detail = [], {}
    for p, _ in origins:
        got = ext.get(p["url"], [])
        out += got
        if got:
            detail[p["마켓명"]] = detail.get(p["마켓명"], 0) + len(got)
    n = len(out) if dry_run else sheet.append(S.BENCH_TAB, out)
    return {"스토어": len(origins), "추가": n, "건너뜀": skipped, "내역": detail}


def _print_origin_report(res):
    print(f"중국 {res['중국']} · 제외 {len(res['제외'])} · 미확인 {len(res['미확인'])}", flush=True)
    for kind in ("제외", "미확인"):
        for x in res[kind]:
            print(f"{x['행']} | {x['마켓명']} | {x['상품명']} | {x['원산지']}", flush=True)


def do_origin_check(sheet, keyword, ckpt_path, run, opts, dry_run=True):
    """기존 후보 행의 원산지를 상세에서 읽어 판정한다(D-ORIGIN). keyword=None 이면 전 키워드.
    dry_run 이면 리포트만 출력(시트 호출 0회). 아니면 미확인 행에 '원산지미확인' 을 병기하고,
    시트를 다시 읽어 상품번호로 현재 위치를 찾아 중국 아닌 행을 삭제한다(T-mbo-02).
    반환 {중국: n, 제외: [{행, 마켓명, 상품명, url, 원산지}], 미확인: [...]} — 행은 헤더=1 기준."""
    ck = _load(ckpt_path, {"details": {}})
    ck.setdefault("details", {})
    targets = []
    for i, r in enumerate(_pad(x) for x in sheet.read(S.BENCH_TAB)):
        url = str(r[6]).strip()
        if keyword is not None and str(r[4]).strip() != keyword:
            continue
        if not url or rules.is_catalog(url):
            continue
        targets.append((i, url, r))
    stopped = _read_options([u for _, u, _ in targets], ck, run, opts, ckpt_path)
    res = {"중국": 0, "제외": [], "미확인": []}
    for i, url, r in targets:
        d = ck["details"].get(url)
        if d is None:
            continue                            # 아직 못 읽음 — 판정 보류(재실행 시 다시 연다)
        v = rules.origin_verdict(d.get("origin"))
        if v == "중국":
            res["중국"] += 1
            continue
        res[v].append({"행": i + 2, "마켓명": r[5], "상품명": r[7], "url": url, "원산지": d.get("origin") or "",
                       "_i": i, "_status": str(r[S.COL_STATUS])})
    if not dry_run:
        # 1) 읽은 시점 인덱스가 유효할 때 미확인 병기부터 (중국 행은 bench 와 같은 규칙 — 상태를 안 바꾼다)
        cells = [(x["_i"], S.COL_STATUS, "·".join(s for s in (x["_status"], "원산지미확인") if s))
                 for x in res["미확인"] if "원산지미확인" not in x["_status"]]
        if cells:
            sheet.update_cells(S.BENCH_TAB, cells)
        # 2) 삭제는 시트를 다시 읽어 상품번호로 현재 위치를 찾는다 (T-mbo-02)
        drop = {rules.product_key(x["url"]) for x in res["제외"]}
        if drop:
            idx = [i for i, r in enumerate(sheet.read(S.BENCH_TAB))
                   if len(r) > 6 and (keyword is None or str(r[4]).strip() == keyword)
                   and rules.product_key(r[6]) in drop]
            sheet.delete_rows(S.BENCH_TAB, idx)
    for kind in ("제외", "미확인"):
        for x in res[kind]:
            x.pop("_i", None)
            x.pop("_status", None)
    _print_origin_report(res)
    if stopped:
        print("원산지 조회 중 캡챠/차단으로 중단했다" + ("" if dry_run else " (판정된 행까지만 반영)") +
              ". Aside 창에서 확인 후 같은 명령을 다시 실행하면 이어서 한다.", flush=True)
        raise SystemExit(4)
    return res


def bench_from_scan(sheet, ckpt_dir, run, date, opts, with_options=True, expand=False, check_origin=False):
    """카테고리스캔 탭에서 키워드가 있고 벤치완료가 빈 행을 일괄 처리.
    expanded 를 실행 전체가 공유해 키워드가 달라도 같은 스토어를 다시 확장하지 않는다."""
    total = 0
    expanded = set()
    kc, dc = S.SCAN_COL["키워드"], S.SCAN_COL["벤치완료"]
    for i, row in enumerate(sheet.read(S.SCAN_TAB)):
        row = row + [""] * (len(S.SCAN_HEADER) - len(row))
        kw = str(row[kc]).strip()
        if not kw or str(row[dc]).strip():
            continue
        n = do_bench(sheet, kw, Path(ckpt_dir) / f"bench-{_slug(kw)}.json", run, date, opts, with_options,
                     expand=expand, check_origin=check_origin, expanded=expanded)
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
    # 2026-10-08: 후보 판매자 스토어의 리뷰 500+ 상품도 이어 붙인다(기본 켬)
    p.add_argument("--no-expand", action="store_true", help="스토어 확장을 끈다")
    p = sub.add_parser("options", help="기존 후보 행에 옵션(9·10열) 채우기, 15조합 초과 행 삭제")
    p.add_argument("--keyword", required=True)
    p = sub.add_parser("expand", help="기존 후보 행에 스토어 확장 소급 (시트 끝에 블록 append)")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--keyword")
    g.add_argument("--all", action="store_true")
    p.add_argument("--no-options", action="store_true", help="확장 상품의 상세 옵션 수집을 건너뛴다")
    p.add_argument("--dry-run", action="store_true", help="시트에 쓰지 않고 추가될 행 수만 출력")
    p = sub.add_parser("origin", help="기존 후보 행 원산지 판정 — 중국 아닌 행 삭제(--dry-run 이면 리포트만)")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--keyword")
    g.add_argument("--all", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="시트를 바꾸지 않고 리포트만 출력")
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
            expand = not args.no_expand
            if args.from_scan:
                n = bench_from_scan(sh, RUNS, aside_bridge.run_driver, date, opts, with_options,
                                    expand=expand, check_origin=True)
            else:
                n = do_bench(sh, args.keyword, RUNS / f"bench-{_slug(args.keyword)}.json",
                             aside_bridge.run_driver, date, opts, with_options,
                             expand=expand, check_origin=True)
                if n is None:
                    sys.exit(1)
            print(f"후보 {n}행 추가")
        elif args.cmd == "options":
            require_login()
            r = do_refill(_sheet(args), args.keyword, RUNS / f"options-{_slug(args.keyword)}.json",
                          aside_bridge.run_driver, opts)
            print(f"옵션 채움 {r['채움']} · 삭제 {r['삭제']}({MAX_COMBOS}초과) · 수동 {r['수동']} · 건너뜀 {r['건너뜀']}")
        elif args.cmd == "expand":
            require_login()
            kw = None if args.all else args.keyword
            r = do_expand(_sheet(args), kw, RUNS / f"expand-{_slug(kw or 'all')}.json", aside_bridge.run_driver,
                          date, opts, with_options=not args.no_options, check_origin=True, dry_run=args.dry_run)
            head = "[dry-run] 추가 예정" if args.dry_run else "스토어확장 추가"
            print(f"{head} {r['추가']}행 · 스토어 {r['스토어']} · 건너뜀 {r['건너뜀']}")
            for mall, cnt in r["내역"].items():
                print(f"  {mall}: {cnt}")
        elif args.cmd == "origin":
            require_login()
            kw = None if args.all else args.keyword
            do_origin_check(_sheet(args), kw, RUNS / f"origin-{_slug(kw or 'all')}.json", aside_bridge.run_driver,
                            opts, dry_run=args.dry_run)
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
