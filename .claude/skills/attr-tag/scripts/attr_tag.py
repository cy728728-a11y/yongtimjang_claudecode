#!/usr/bin/env python3
"""판매상품 속성·공식 태그 입력 도구 (attr-tag) CLI.

sold-lock 이 남긴 new_locks.json 상품에 스마트스토어 속성과 공식 태그(태그사전 code 포함)를
커머스API 로 넣는다. 판단(어떤 태그·속성 값)은 Claude 가 하고, 이 도구는
① 판단 재료 수집(prep) ② 판단 결과 검증·저장·확인(apply) ③ 되돌리기(revert) 만 한다.

    PY=.venv/bin/python3; S=.claude/skills/attr-tag/scripts/attr_tag.py
    $PY $S prep --date 2026-10-16                         # new_locks.json 전체
    $PY $S prep --date 2026-10-16 --market 13-2 --channel-no 13265084103
    $PY $S apply --plan plan.json                         # dry-run (기본, 쓰기 0)
    $PY $S apply --plan plan.json --commit                # 백업 → PUT → 재조회 확인
    $PY $S revert --market 13-2 --channel-no 13265084103  # dry-run
    $PY $S revert --market 13-2 --channel-no 13265084103 --commit

run-dir: <data_root>/attr-tag/<날짜>/  (data_root = workspace.toml paths.data_root)
시크릿·토큰은 stdout·산출물 어디에도 남기지 않는다(sold-lock 의 safe_json/redact 경유).
"""
import argparse
import glob
import json
import os
import sys
import tempfile
import time
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILLS_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
SOLD_LOCK_DIR = os.path.join(SKILLS_DIR, "sold-lock", "scripts")
for _p in (SCRIPT_DIR, SOLD_LOCK_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import attr_tag_rules as A  # noqa: E402
import sold_lock_rules as SR  # noqa: E402  (redact · safe_json · KST)
from commerce_orders import BASE, StoresUnavailable, _load_eroomlib  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

MIN_INTERVAL = 1.0          # 커머스API GW.RATE_LIMIT — 호출 간 ≥1초
_RETRY_STATUS = {429, 500, 502, 503, 504}


# ---------------------------------------------------------------------------
# 보조
# ---------------------------------------------------------------------------
class _Log:
    """진행로그 — 항상 시크릿을 마스킹해서 찍는다."""

    def __init__(self, secrets):
        self.secrets = secrets

    def __call__(self, msg):
        print(SR.redact(msg, self.secrets), flush=True)


def _write_json(path, obj, secrets, overwrite=True):
    """safe_json(시크릿 마스킹) 으로만 원자적 쓰기. overwrite=False 면 이미 있으면 안 쓴다(False 반환)."""
    if not overwrite and os.path.exists(path):
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = SR.safe_json(obj, secrets)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return True


def _read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _key(market, no):
    return f"{market}_{no}"


def today_kst():
    return datetime.now(SR.KST).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# 커머스API — 마켓별 토큰 + 레이트 간격 + 백오프
# ---------------------------------------------------------------------------
class CommerceApi:
    """실제 커머스 연동. 테스트는 같은 메서드를 가진 가짜를 run_* 에 꽂는다.

    메서드: get_product · put_product · category · attributes · attribute_values ·
            recommend_tags · restricted_tags  (전부 첫 인자 market)
    키 로딩·토큰 발급은 sold-lock CommerceClient(load_stores · issue_token) 재사용.
    """

    def __init__(self, client, secrets, http=None, sleep=time.sleep, min_interval=MIN_INTERVAL):
        self.client = client
        self.secrets = secrets          # 공유 리스트 — 시크릿·토큰을 넣어 로그 마스킹
        self._http = http
        self._sleep = sleep
        self.min_interval = min_interval
        self._last = 0.0
        self._tokens = {}
        self._stores = None

    def load(self, markets):
        """대상 마켓 키 로드 → 출처('sheet'|'cache')."""
        self._stores, src = self.client.load_stores(sorted(set(markets)))
        self.secrets.extend(s.get("client_secret") for s in self._stores.values())
        return src

    def _token(self, market):
        if market in self._tokens:
            return self._tokens[market]
        if self._stores is None:
            self.load([market])
        st = (self._stores or {}).get(market)
        if not st:
            raise RuntimeError(f"{market} 커머스 키 없음")
        tok, err = self.client.issue_token(st)
        if not tok:
            raise RuntimeError(f"{market} 토큰 실패: {SR.redact(err, self.secrets)[:200]}")
        self.secrets.append(tok)
        self._tokens[market] = tok
        return tok

    def _request(self, market, method, path, **kw):
        if self._http is None:
            import requests
            self._http = requests.Session()
        tok = self._token(market)
        headers = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json;charset=UTF-8"}
        last = None
        for attempt in range(5):
            gap = time.monotonic() - self._last
            if gap < self.min_interval:
                self._sleep(self.min_interval - gap)
            self._last = time.monotonic()
            r = self._http.request(method, f"{BASE}{path}", headers=headers, timeout=60, **kw)
            body = r.text or ""
            if r.status_code in _RETRY_STATUS or "RATE_LIMIT" in body[:500]:
                last = f"HTTP {r.status_code}"
                self._sleep(2.0 * (2 ** attempt))
                continue
            if r.status_code >= 400:
                raise RuntimeError(f"HTTP {r.status_code} {SR.redact(body[:400], self.secrets)}")
            return r.json() if body.strip() else {}
        raise RuntimeError(f"재시도 초과: {last}")

    def get_product(self, market, no):
        return self._request(market, "GET", f"/v2/products/channel-products/{no}")

    def put_product(self, market, no, body):
        return self._request(market, "PUT", f"/v2/products/channel-products/{no}", json=body)

    def category(self, market, cat_id):
        return self._request(market, "GET", f"/v1/categories/{cat_id}")

    def attributes(self, market, cat_id):
        return self._request(market, "GET", "/v1/product-attributes/attributes", params={"categoryId": cat_id})

    def attribute_values(self, market, cat_id):
        return self._request(market, "GET", "/v1/product-attributes/attribute-values",
                             params={"categoryId": cat_id})

    def recommend_tags(self, market, keyword):
        return self._request(market, "GET", "/v2/tags/recommend-tags", params={"keyword": keyword})

    def restricted_tags(self, market, tags):
        d = self._request(market, "GET", "/v2/tags/restricted-tags", params={"tags": ",".join(tags)})
        return {str(x.get("tag")): bool(x.get("restricted")) for x in d or []}


class _Cache:
    """카테고리 속성 표·태그 사전 조회를 실행 1회 동안 캐시 (레이트리밋 절약)."""

    def __init__(self, api):
        self.api = api
        self.tables = {}
        self.cat_names = {}
        self.rec = {}

    def table(self, market, cat):
        if cat not in self.tables:
            self.tables[cat] = A.build_attr_table(self.api.attributes(market, cat),
                                                  self.api.attribute_values(market, cat))
        return self.tables[cat]

    def cat_name(self, market, cat):
        if cat not in self.cat_names:
            try:
                d = self.api.category(market, cat) or {}
                self.cat_names[cat] = d.get("wholeCategoryName") or d.get("name")
            except Exception:
                self.cat_names[cat] = None
        return self.cat_names[cat]

    def recommend(self, market, text):
        if text not in self.rec:
            self.rec[text] = self.api.recommend_tags(market, text) or []
        return self.rec[text]


# ---------------------------------------------------------------------------
# 의존성 기본값
# ---------------------------------------------------------------------------
def _cfg(key):
    _load_eroomlib()
    from eroomlib.config import cfg
    return cfg(key, required=True)


def _data_root():
    return os.path.expanduser(_cfg("paths.data_root"))


def _default_api(secrets):
    from commerce_orders import CommerceClient
    return CommerceApi(CommerceClient(_cfg("sheets.orders")), secrets)


def _processed(attr_root, market, no):
    """어느 날짜 run-dir 에든 after 백업이 있으면 이미 처리된 상품."""
    return bool(glob.glob(os.path.join(attr_root, "*", f"after_{_key(market, no)}.json")))


# ---------------------------------------------------------------------------
# prep — 판단 재료 수집
# ---------------------------------------------------------------------------
def load_targets(args, data_root):
    """대상 [(market, channel_no)] — --market/--channel-no 직접 지정 또는 new_locks.json."""
    if args.market and args.channel_no:
        return [(args.market, str(args.channel_no))]
    path = args.input or os.path.join(data_root, "sold-lock", args.date, "new_locks.json")
    rows = _read_json(path)
    if rows is None:
        raise FileNotFoundError(f"new_locks.json 없음/깨짐: {path}")
    out = []
    for r in rows:
        m, no = str(r.get("마켓번호") or "").strip(), str(r.get("스스상품번호") or "").strip()
        if m and no and (m, no) not in out:
            if args.market and m != args.market:
                continue
            out.append((m, no))
    return out


def prep_one(api, cache, market, no):
    """상품 1건 → prep dict."""
    p = api.get_product(market, no)
    o = p.get("originProduct") or {}
    cat = str(o.get("leafCategoryId") or "")
    table = cache.table(market, cat) if cat else {}
    imgs = o.get("images") or {}
    urls = [(imgs.get("representativeImage") or {}).get("url")]
    urls += [x.get("url") for x in (imgs.get("optionalImages") or [])[:3]]
    urls += A.detail_image_urls(o.get("detailContent"), 3)
    return {
        "market": market, "channel_no": no,
        "product_name": o.get("name"),
        "category_id": cat,
        "category_path": cache.cat_name(market, cat) if cat else None,
        "options": A.option_names(p),
        "current_tags": [{"text": t.get("text"), "code": t.get("code"),
                          "has_code": t.get("code") not in (None, "")} for t in A.current_tags(p)],
        "current_attributes": A.describe_attributes(A.current_attributes(p), table),
        "available_attributes": A.attr_table_for_prompt(table),
        "detail_text": A.html_to_text(o.get("detailContent")),
        "image_urls": [u for u in urls if u],
    }


def run_prep(args, api=None, data_root=None, log=None):
    secrets = []
    log = log or _Log(secrets)
    data_root = data_root or _data_root()
    api = api or _default_api(secrets)
    attr_root = os.path.join(data_root, "attr-tag")
    run_dir = os.path.join(attr_root, args.date)
    try:
        targets = load_targets(args, data_root)
    except Exception as e:
        log(f"[중단] 대상 로드 실패: {e}")
        return 1
    if hasattr(api, "load"):
        try:
            api.load([m for m, _ in targets])
        except StoresUnavailable as e:
            log(f"[중단] 커머스 키 로드 불가: {e}")
            return 2
    cache = _Cache(api)
    todo = _read_json(os.path.join(run_dir, "todo.json"), []) or []
    have = {_key(t["market"], t["channel_no"]) for t in todo}
    n_ok = n_skip = n_fail = 0
    for market, no in targets:
        if not args.force and _processed(attr_root, market, no):
            log(f"  {market} {no} 이미 처리됨 → 건너뜀 (--force 로 재처리)")
            n_skip += 1
            continue
        try:
            d = prep_one(api, cache, market, no)
            fname = f"prep_{_key(market, no)}.json"
            _write_json(os.path.join(run_dir, fname), d, secrets)
            if _key(market, no) not in have:
                todo.append({"market": market, "channel_no": no, "product_name": d["product_name"],
                             "prep_file": fname, "status": "pending"})
                have.add(_key(market, no))
            n_ok += 1
            log(f"  {market} {no} 준비 ✅ 태그 {len(d['current_tags'])} · 입력가능속성 "
                f"{len(d['available_attributes'])}")
        except Exception as e:
            n_fail += 1
            log(f"  {market} {no} 준비 실패: {SR.redact(f'{type(e).__name__}: {e}', secrets)[:300]}")
    _write_json(os.path.join(run_dir, "todo.json"), todo, secrets)
    log(f"[완료] 준비 {n_ok} · 건너뜀 {n_skip} · 실패 {n_fail}  →  {run_dir}")
    return 0


# ---------------------------------------------------------------------------
# apply — 판단 결과 검증·저장·확인
# ---------------------------------------------------------------------------
def plan_item(api, cache, entry):
    """plan 1건 → (product, body, report). 쓰기 없음."""
    market, no = str(entry["market"]), str(entry["channel_no"])
    p = api.get_product(market, no)
    cat = str(((p.get("originProduct") or {}).get("leafCategoryId")) or "")
    rep = {"market": market, "channel_no": no,
           "product_name": (p.get("originProduct") or {}).get("name")}

    tags = None
    if entry.get("tags") is not None:
        tags, dropped = A.resolve_tags(entry.get("tags"),
                                       lambda t: cache.recommend(market, t),
                                       lambda ts: api.restricted_tags(market, ts))
        rep["dropped_tags"] = dropped
        if not tags:
            # 전부 탈락하면 기존 태그를 지우지 않는다
            rep["tags_note"] = "검증 통과 태그 0 → 기존 태그 유지"
            tags = None

    attrs = None
    if entry.get("attributes") is not None:
        table = cache.table(market, cat) if cat else {}
        new, dropped_a = A.resolve_attributes(entry.get("attributes"), table)
        rep["dropped_attributes"] = dropped_a
        keep = entry.get("keep_existing_attributes", True)
        if new or not keep:
            attrs = A.merge_attributes(A.current_attributes(p), new, keep_existing=bool(keep))
        rep["attributes_set"] = A.describe_attributes(new, table)

    body = A.build_body(p, tags=tags, attributes=attrs)
    rep["diff"] = A.change_summary(p, body)
    rep["changed"] = bool(rep["diff"]["tags_changed"] or rep["diff"]["attributes_added"]
                          or rep["diff"]["attributes_removed"])
    return p, body, rep


def _board_append(memo, date, board_append, board_get, work_board_id, ok_all, secrets):
    """업무판 '오늘' 탭 1행 — sold-lock 과 같은 행 형식. 실패해도 본작업 유지."""
    try:
        col = board_get(work_board_id, "'오늘'!A:A") or []
        nums = []
        for r in col:
            try:
                nums.append(int(str(r[0]).strip()))
            except (ValueError, IndexError, TypeError):
                pass
        row = [max(nums, default=0) + 1, today_kst(), bool(ok_all), f"⑥ 속성·태그 {date}",
               "⑥", "Claude", "자동", memo, ""]
        board_append(work_board_id, "오늘", [row])
        return {"status": "ok"}
    except Exception as e:
        return {"status": "failed", "error": SR.redact(f"{type(e).__name__}: {e}", secrets)[:300]}


def run_apply(args, api=None, data_root=None, board_append=None, board_get=None, work_board_id=None,
              log=None):
    secrets = []
    log = log or _Log(secrets)
    plan = _read_json(args.plan)
    if not isinstance(plan, list):
        log(f"[중단] plan 이 리스트가 아니거나 못 읽음: {args.plan}")
        return 1
    data_root = data_root or _data_root()
    api = api or _default_api(secrets)
    run_dir = os.path.join(data_root, "attr-tag", args.date)
    if hasattr(api, "load"):
        try:
            api.load([str(e.get("market")) for e in plan if isinstance(e, dict)])
        except StoresUnavailable as e:
            log(f"[중단] 커머스 키 로드 불가: {e}")
            return 2
    cache = _Cache(api)
    reports = []
    for entry in plan:
        if not isinstance(entry, dict) or not entry.get("market") or not entry.get("channel_no"):
            reports.append({"status": "failed", "error": "plan 항목에 market/channel_no 없음", "entry": entry})
            continue
        market, no = str(entry["market"]), str(entry["channel_no"])
        k = _key(market, no)
        try:
            before, body, rep = plan_item(api, cache, entry)
        except Exception as e:
            reports.append({"market": market, "channel_no": no, "status": "failed",
                            "error": SR.redact(f"plan: {type(e).__name__}: {e}", secrets)[:400]})
            log(f"  {market} {no} 검증 실패")
            continue
        d = rep["diff"]
        log(f"  {market} {no} 태그 {len(d['tags_before'])}→{len(d['tags_after'])} · 속성 +"
            f"{len(d['attributes_added'])}/-{len(d['attributes_removed'])} · 탈락 태그 "
            f"{len(rep.get('dropped_tags', []))} 속성 {len(rep.get('dropped_attributes', []))}")
        rep["tag_count"] = len(d["tags_after"])
        rep["attributes_added"] = len(d["attributes_added"])
        if not args.commit:
            rep["status"] = "dry_run"
            reports.append(rep)
            continue
        if not rep["changed"]:
            rep["status"] = "ok"
            rep["note"] = "변경 없음 — 저장 생략"
            try:  # 처리 표시(after) — prep 이 다시 집지 않게
                _write_json(os.path.join(run_dir, f"after_{k}.json"), before, secrets)
            except Exception:
                pass
            reports.append(rep)
            continue
        try:
            _write_json(os.path.join(run_dir, f"before_{k}.json"), before, secrets, overwrite=False)
            api.put_product(market, no, body)
            after = api.get_product(market, no)
            problems = A.verify_applied(after, body)
            inv = A.invariant_diff(before, after)
            if inv:
                problems.append({"what": "invariant_changed", "fields": inv})
            _write_json(os.path.join(run_dir, f"after_{k}.json"), after, secrets)
            rep["status"] = "ok" if not problems else "unverified"
            if problems:
                rep["problems"] = problems
            log(f"  {market} {no} 저장 {'✅' if not problems else '⚠️ 확인 실패'}")
        except Exception as e:
            rep["status"] = "failed"
            rep["error"] = SR.redact(f"{type(e).__name__}: {e}", secrets)[:400]
            log(f"  {market} {no} 저장 실패: {rep['error'][:200]}")
        reports.append(rep)

    if not args.commit:
        _write_json(os.path.join(run_dir, "apply_dryrun.json"),
                    {"plan": os.path.abspath(args.plan), "at": datetime.now(SR.KST).isoformat(),
                     "items": reports}, secrets)
        log(f"[dry-run] {len(reports)}건 · 쓰기 0  →  {os.path.join(run_dir, 'apply_dryrun.json')}")
        return 0

    # result.json 누적 — 같은 상품은 최신 결과로 교체
    res_path = os.path.join(run_dir, "result.json")
    res = _read_json(res_path, {}) or {}
    items = {(_key(r.get("market"), r.get("channel_no"))): r for r in res.get("items", [])}
    for r in reports:
        items[_key(r.get("market"), r.get("channel_no"))] = dict(r, at=datetime.now(SR.KST).isoformat())
    memo = A.summary_memo(reports)
    res = {"date": args.date, "items": list(items.values()), "last_summary": memo}
    if board_append is None or board_get is None or work_board_id is None:
        try:
            _load_eroomlib()
            from eroomlib import gsheets
            board_append = board_append or gsheets.append_rows
            board_get = board_get or gsheets.sheets_get
            work_board_id = work_board_id or _cfg("sheets.work_board")
        except Exception as e:
            res["board"] = {"status": "failed", "error": type(e).__name__}
    if "board" not in res:
        ok_all = all(r.get("status") == "ok" for r in reports)
        res["board"] = _board_append(memo, args.date, board_append, board_get, work_board_id, ok_all, secrets)
    if res["board"]["status"] != "ok":
        log("[경고] 업무판 기록 실패 (result.json 은 남김)")
    _write_json(res_path, res, secrets)
    log(f"[완료] {memo}  →  {run_dir}")
    return 0


# ---------------------------------------------------------------------------
# revert — before 백업의 태그·속성만 되돌림
# ---------------------------------------------------------------------------
def find_backup(attr_root, market, no, date=None):
    """before 백업 경로. date 없으면 가장 이른 날짜(= 최초 원본)."""
    pat = os.path.join(attr_root, date or "*", f"before_{_key(market, no)}.json")
    hits = sorted(glob.glob(pat))
    return hits[0] if hits else None


def run_revert(args, api=None, data_root=None, log=None):
    secrets = []
    log = log or _Log(secrets)
    data_root = data_root or _data_root()
    attr_root = os.path.join(data_root, "attr-tag")
    no = str(args.channel_no)
    path = find_backup(attr_root, args.market, no, args.date if args.date_given else None)
    if not path:
        log(f"[중단] before 백업 없음: {args.market} {no}")
        return 1
    backup = _read_json(path)
    if not isinstance(backup, dict):
        log(f"[중단] 백업 깨짐: {path}")
        return 1
    api = api or _default_api(secrets)
    try:
        cur = api.get_product(args.market, no)
        body = A.build_body(cur, tags=A.current_tags(backup), attributes=A.current_attributes(backup))
        diff = A.change_summary(cur, body)
        log(f"  되돌림 원본: {path}")
        log(f"  태그 {len(diff['tags_before'])}→{len(diff['tags_after'])} · 속성 +"
            f"{len(diff['attributes_added'])}/-{len(diff['attributes_removed'])}")
        out_dir = os.path.join(attr_root, today_kst())
        if not args.commit:
            _write_json(os.path.join(out_dir, f"revert_dryrun_{_key(args.market, no)}.json"),
                        {"backup": path, "diff": diff}, secrets)
            log("[dry-run] 쓰기 0")
            return 0
        api.put_product(args.market, no, body)
        after = api.get_product(args.market, no)
        problems = A.verify_applied(after, body)
        inv = A.invariant_diff(cur, after)
        if inv:
            problems.append({"what": "invariant_changed", "fields": inv})
        _write_json(os.path.join(out_dir, f"reverted_{_key(args.market, no)}.json"),
                    {"backup": path, "diff": diff, "problems": problems, "after": after}, secrets)
        log(f"[완료] 되돌림 {'✅' if not problems else '⚠️ 확인 실패'}")
        return 0 if not problems else 4
    except Exception as e:
        log(f"[실패] 되돌림: {SR.redact(f'{type(e).__name__}: {e}', secrets)[:300]}")
        return 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser():
    ap = argparse.ArgumentParser(description="판매상품 속성·공식 태그 입력 (prep → apply → revert)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prep", help="판단 재료 수집")
    p.add_argument("--date", default=None, help="new_locks 날짜 YYYY-MM-DD (기본: KST 어제)")
    p.add_argument("--input", default=None, help="new_locks.json 경로 직접 지정")
    p.add_argument("--market", default=None)
    p.add_argument("--channel-no", default=None)
    p.add_argument("--force", action="store_true", help="이미 처리된 상품도 다시 준비")

    a = sub.add_parser("apply", help="plan 검증·저장 (기본 dry-run)")
    a.add_argument("--plan", required=True)
    a.add_argument("--date", default=None, help="run-dir 날짜 (기본: plan 이 run-dir 안이면 그 날짜, 아니면 오늘)")
    a.add_argument("--commit", action="store_true", help="실제 저장")

    r = sub.add_parser("revert", help="before 백업의 태그·속성으로 되돌림 (기본 dry-run)")
    r.add_argument("--market", required=True)
    r.add_argument("--channel-no", required=True)
    r.add_argument("--date", default=None, help="백업 날짜 (기본: 가장 이른 백업)")
    r.add_argument("--commit", action="store_true")
    return ap


def _plan_date(plan_path):
    """plan 이 attr-tag/<날짜>/ 안에 있으면 그 날짜."""
    d = os.path.basename(os.path.dirname(os.path.abspath(plan_path)))
    try:
        datetime.strptime(d, "%Y-%m-%d")
        return d
    except ValueError:
        return None


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "prep":
            if args.date is None:
                args.date = SR.default_target_date()
            SR.day_range_kst(args.date)
            if bool(args.market) != bool(args.channel_no) and not args.market:
                print("[오류] --channel-no 는 --market 과 함께", flush=True)
                return 1
            return run_prep(args)
        if args.cmd == "apply":
            args.date = args.date or _plan_date(args.plan) or today_kst()
            SR.day_range_kst(args.date)
            return run_apply(args)
        args.date_given = args.date is not None
        if args.date_given:
            SR.day_range_kst(args.date)
        return run_revert(args)
    except ValueError as e:
        print(f"[오류] 인자: {e}", flush=True)
        return 1
    except Exception as e:
        print(f"[오류] 예기치 못한 실패: {type(e).__name__}", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
