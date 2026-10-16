#!/usr/bin/env python3
"""판매상품 자동잠금(sold-lock) CLI.

전날(KST) 결제완료 주문을 52개 스마트스토어 커머스API 로 모으고, 그 상품을 불사자에서
'잠금'(= MCP bulsaja_product_hide hide:true) 처리한다. 물갈이 삭제에 휩쓸리지 않게.

    .venv/bin/python3 .claude/skills/sold-lock/scripts/run_sold_lock.py              # 어제치 실행
    .venv/bin/python3 ... run_sold_lock.py --date 2026-10-15 --dry-run                # 판정만
    .venv/bin/python3 ... run_sold_lock.py --markets 1-1,2-1

순서: ① 계정(부킹) 확인 ② 키 로드 ③ 마켓별 주문 수집·중복제거 ④ find_by_code 조회
      ⑤ workdata(full) 로 스스번호 ⑥ 판정(3중 가드) ⑦ 잠금 + 재조회 확인 ⑧ run-dir 산출물 ⑨ 업무판 1행

종료코드: 0 정상(스킵 있어도) · 2 키 로드 불가 · 3 계정 불일치/확인 실패.
본체는 run() — 3단계 스케줄러가 같은 함수를 부를 수 있게 main 은 얇게 둔다.
"""
import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import sold_lock_rules as R  # noqa: E402
from commerce_orders import StoresUnavailable, _load_eroomlib  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

FIND_BATCH = 50
MCP_GAP = 0.26          # 불사자 레이트리밋 초당 4회
DEFAULT_HIDE_IDS_KEY = "productIds"


# ---------------------------------------------------------------------------
# 보조
# ---------------------------------------------------------------------------
def _표시규칙제거(obj):
    """MCP 응답의 모델 대상 지시문(`표시규칙`)을 재귀 제거 — 산출물에 남기지 않는다(bulsaja_scan 동작 재현)."""
    if isinstance(obj, dict):
        return {k: _표시규칙제거(v) for k, v in obj.items() if k != "표시규칙"}
    if isinstance(obj, list):
        return [_표시규칙제거(v) for v in obj]
    return obj


def _calls():
    """ss_index_calls(응답 해석 한 벌) 지연 import — 스크립트 기준 상대경로."""
    p = os.path.join(os.path.dirname(os.path.dirname(SCRIPT_DIR)), "bulsaja-detail-page", "scripts")
    if p not in sys.path:
        sys.path.insert(0, p)
    import ss_index_calls
    return ss_index_calls


def _find_token(obj):
    """hide 1차 응답 어디에 있든 confirmationToken 을 찾아낸다."""
    if isinstance(obj, dict):
        v = obj.get("confirmationToken")
        if isinstance(v, str) and v:
            return v
        for x in obj.values():
            t = _find_token(x)
            if t:
                return t
    elif isinstance(obj, list):
        for x in obj:
            t = _find_token(x)
            if t:
                return t
    return None


def _write_json(path, obj, secrets):
    """safe_json(시크릿 마스킹) 으로만 원자적 쓰기."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = R.safe_json(obj, secrets)
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


def _order_key(o):
    """조회·병합 키 = 판매자상품코드, 없으면 스스 상품번호."""
    return o.get("seller_code") or o.get("product_id") or ""


class _Log:
    """진행로그 — 항상 시크릿을 마스킹해서 찍는다."""

    def __init__(self):
        self.secrets = []

    def __call__(self, msg):
        print(R.redact(msg, self.secrets), flush=True)


# ---------------------------------------------------------------------------
# 불사자 단계
# ---------------------------------------------------------------------------
class _Bulsaja:
    """MCP 호출을 레이트 간격과 표시규칙 제거로 감싼다."""

    def __init__(self, mcp, sleep):
        self.mcp = mcp
        self.sleep = sleep
        self._last = 0.0
        self.group_id_by_pid = {}
        self._group_names = None

    def call(self, name, arguments):
        gap = time.monotonic() - self._last
        if gap < MCP_GAP:
            self.sleep(MCP_GAP - gap)
        try:
            return _표시규칙제거(self.mcp.call_tool(name, arguments) or {})
        finally:
            self._last = time.monotonic()

    def find(self, codes):
        """코드 리스트 → ({코드: [항목...]}, 오류난 코드 집합). 50개 배치.

        배치 응답은 항목의 판매자상품코드/불사자코드로 코드에 되붙인다. 코드 1개짜리 배치는
        (상품번호 폴백 조회처럼 필드가 안 맞을 수 있으므로) 돌아온 항목을 전부 그 코드에 붙인다.
        """
        calls = _calls()
        found, errors = {}, set()
        for i in range(0, len(codes), FIND_BATCH):
            chunk = codes[i:i + FIND_BATCH]
            try:
                items = calls.항목꺼내기(self.call("bulsaja_product_find_by_code", {"codes": chunk}),
                                     f" (find_by_code {len(chunk)}건)")
            except Exception:
                errors.update(chunk)
                continue
            for c in chunk:
                found[c] = []
            for it in items:
                if not isinstance(it, dict):
                    continue
                if len(chunk) == 1:
                    found[chunk[0]].append(it)
                    continue
                for c in chunk:
                    if str(it.get("판매자상품코드") or "") == c or str(it.get("불사자코드") or "") == c:
                        found[c].append(it)
        return found, errors

    def ss_no(self, pid):
        """불사자 상품 → 스스 상품번호. 업로드 안 됨이면 '' (불일치로 판정), 조회 실패면 None."""
        try:
            data = _calls().워크데이터꺼내기(
                self.call("bulsaja_product_workdata", {"productId": pid, "mode": "full"}), f" ({pid})")
        except Exception:
            return None
        v = (data.get("uploadedSuccessUrl") or {}).get("smartstore") if isinstance(data, dict) else None
        # 목록 조회의 '그룹' 필드는 null 로 오는 일이 많아(실측) 업로드 마켓그룹ID를 따로 남긴다
        if isinstance(data, dict) and data.get("uploadSelectedMarketGroupId"):
            self.group_id_by_pid[pid] = data.get("uploadSelectedMarketGroupId")
        return R.extract_ss_no(v) or ""

    def group_name_of(self, pid):
        """업로드 마켓그룹ID → 그룹명(예 '13번_용쌤13-2'). 모르면 None."""
        gid = self.group_id_by_pid.get(pid)
        if gid is None:
            return None
        if self._group_names is None:
            self._group_names = {}
            try:
                d = self.call("bulsaja_market_groups", {})
                for g in (d or {}).get("그룹") or []:
                    self._group_names[str(g.get("groupId"))] = g.get("그룹명")
            except Exception:
                pass
        return self._group_names.get(str(gid))

    def hide_ids_key(self):
        """bulsaja_product_hide 의 상품ID 배열 인자명을 list_tools inputSchema 에서 확인."""
        for t in self.mcp.list_tools() or []:
            if t.get("name") != "bulsaja_product_hide":
                continue
            props = ((t.get("inputSchema") or {}).get("properties") or {})
            if DEFAULT_HIDE_IDS_KEY in props:
                return DEFAULT_HIDE_IDS_KEY
            for k, v in props.items():
                if isinstance(v, dict) and v.get("type") == "array":
                    return k
        raise RuntimeError("bulsaja_product_hide 스키마에서 상품ID 배열 인자를 못 찾았다")

    def hide(self, ids_key, pids):
        """잠금: 1차 → confirmationToken → confirm:true 재제출(이미 동의한 작업의 2단계 확인)."""
        args = {ids_key: list(pids), "hide": True}
        first = self.call("bulsaja_product_hide", args)
        tok = _find_token(first)
        if tok:
            self.call("bulsaja_product_hide", dict(args, confirm=True, confirmationToken=tok))


# ---------------------------------------------------------------------------
# 본체
# ---------------------------------------------------------------------------
def _defaults(args, commerce, mcp_factory, board_append, board_get, run_dir, work_board_id):
    """주입 안 된 의존성을 실제 구현으로 채운다(설정값은 workspace.toml 에서만)."""
    if commerce is None or mcp_factory is None or board_append is None or board_get is None \
            or run_dir is None or work_board_id is None:
        _load_eroomlib()
        from eroomlib.config import cfg
        if commerce is None:
            from commerce_orders import CommerceClient
            commerce = CommerceClient(cfg("sheets.orders", required=True))
        if mcp_factory is None:
            from eroomlib.snapshot import ProductMCP
            mcp_factory = ProductMCP
        if board_append is None or board_get is None:
            from eroomlib import gsheets
            board_append = board_append or gsheets.append_rows
            board_get = board_get or gsheets.sheets_get
        if work_board_id is None:
            work_board_id = cfg("sheets.work_board", required=True)
        if run_dir is None:
            run_dir = os.path.join(os.path.expanduser(cfg("paths.data_root", required=True)),
                                   "sold-lock", args.date)
    return commerce, mcp_factory, board_append, board_get, run_dir, work_board_id


def run(args, commerce=None, mcp_factory=None, board_append=None, board_get=None,
        run_dir=None, work_board_id=None, sleep=time.sleep, now_kst=None):
    """sold-lock 1회 실행. 종료코드를 돌려준다."""
    log = _Log()
    commerce, mcp_factory, board_append, board_get, run_dir, work_board_id = _defaults(
        args, commerce, mcp_factory, board_append, board_get, run_dir, work_board_id)
    markets = R.parse_markets_arg(args.markets) if args.markets else R.target_markets()
    now = now_kst or datetime.now(R.KST)
    log(f"[sold-lock] 대상날짜 {args.date} · 마켓 {len(markets)}개 · {'dry-run' if args.dry_run else '실행'}")

    mcp = mcp_factory()
    mcp.open()
    try:
        b = _Bulsaja(mcp, sleep)
        # ① 계정 확인 — 불일치·조회실패면 아무것도 하지 않는다
        try:
            nick = str((b.call("bulsaja_my_profile", {}) or {}).get("닉네임") or "")
        except Exception as e:
            log(f"[중단] 불사자 계정 조회 실패: {type(e).__name__}")
            return 3
        if nick != args.expect_nick:
            log(f"[중단] 불사자 계정이 '{args.expect_nick}' 가 아니다 (현재 '{nick}')")
            return 3

        # ② 키 로드
        try:
            stores, source = commerce.load_stores(markets)
        except StoresUnavailable as e:
            log(f"[중단] 커머스 키 로드 불가: {e}")
            return 2
        log.secrets.extend(s.get("client_secret") for s in stores.values())

        result = {"date": args.date, "dry_run": bool(args.dry_run), "markets_source": source,
                  "started_at": now.isoformat(), "markets": {}, "items": [],
                  "totals": {"orders": 0, "lock_targets": 0, "locked_new": 0, "already_locked": 0,
                             "would_lock": 0, "skipped": {}}}

        # ③ 마켓별 주문 수집 — 한 마켓 실패가 다른 마켓을 막지 않는다
        raw = []
        for no in markets:
            st = stores.get(no)
            m = {"name": (st or {}).get("name", ""), "status": "ok", "orders": 0}
            result["markets"][no] = m
            if not st:
                m["status"] = "no_credentials"
                log(f"  {no} 키 없음 → 건너뜀")
                continue
            try:
                tok, err = commerce.issue_token(st)
            except Exception as e:
                tok, err = None, f"{type(e).__name__}: {e}"
            if not tok:
                m["status"], m["error"] = "token_failed", R.redact(err, log.secrets)[:300]
                log(f"  {no} 토큰 실패 → 건너뜀")
                continue
            log.secrets.append(tok)
            try:
                rows = commerce.fetch_paid_orders(tok, no, args.date)
            except Exception as e:
                m["status"], m["error"] = "orders_failed", R.redact(f"{type(e).__name__}: {e}", log.secrets)[:300]
                log(f"  {no} 주문 조회 실패 → 건너뜀")
                continue
            m["orders"] = len(rows)
            raw.extend(rows)
            log(f"  {no} 결제완료 {len(rows)}건")
        orders = R.dedup_orders(raw)
        result["totals"]["orders"] = len(raw)
        _write_json(os.path.join(run_dir, "orders.json"),
                    {"date": args.date, "raw_count": len(raw), "orders": orders}, log.secrets)

        # ④ 불사자 조회 — 판매자상품코드, 코드 없는 주문은 상품번호로 폴백(코드 1개씩)
        codes = sorted({o["seller_code"] for o in orders if o.get("seller_code")})
        found, lookup_err = b.find(codes) if codes else ({}, set())
        for pidno in sorted({o["product_id"] for o in orders if not o.get("seller_code") and o.get("product_id")}):
            f1, e1 = b.find([pidno])
            found.update(f1)
            lookup_err |= e1

        # ⑤⑥ 스스번호 + 판정
        ss_cache, targets = {}, []
        skipped = result["totals"]["skipped"]
        for o in orders:
            key = _order_key(o)
            entry = {"market": o["market"], "seller_code": o.get("seller_code", ""),
                     "product_id": o.get("product_id", ""), "order_count": o.get("order_count", 1),
                     "product_name": o.get("product_name", "")}
            if key in lookup_err:
                verdict, reason = "skip", "lookup_error"
                items = []
            else:
                items = found.get(key, [])
                if len(items) == 1:
                    pid = items[0].get("productId")
                    if pid not in ss_cache:
                        ss_cache[pid] = b.ss_no(pid)
                    # 마켓 대조는 업로드 마켓그룹(워크데이터) 기준 — 목록의 '그룹'은 null·폴더명일 수 있다
                    gname = b.group_name_of(pid)
                    if gname:
                        items = [dict(items[0], 그룹=gname)]
                verdict, reason = R.decide(o, items, ss_cache, o["market"])
            if len(items) == 1:
                entry["bulsaja_id"] = items[0].get("productId")
                entry["group"] = items[0].get("그룹")
            entry["verdict"], entry["reason"] = verdict, reason
            if verdict == "skip":
                skipped[reason] = skipped.get(reason, 0) + 1
            elif verdict == "already_locked":
                result["totals"]["already_locked"] += 1
            else:
                targets.append(entry)
            result["items"].append(entry)
        result["totals"]["lock_targets"] = len(targets)

        # ⑦ 잠금 — dry-run 은 판정만 남긴다
        new_locks = []
        if args.dry_run:
            for e in targets:
                e["verdict"] = "would_lock"
            result["totals"]["would_lock"] = len(targets)
        elif targets:
            try:
                ids_key = b.hide_ids_key()
            except Exception as ex:
                ids_key = None
                log(f"[경고] 잠금 도구 스키마 확인 실패 → 잠금 안 함: {type(ex).__name__}")
            for i in range(0, len(targets), FIND_BATCH):
                chunk = targets[i:i + FIND_BATCH]
                ok_call = False
                if ids_key:
                    try:
                        b.hide(ids_key, [e["bulsaja_id"] for e in chunk])
                        ok_call = True
                    except Exception as ex:
                        log(f"[경고] 잠금 호출 실패({len(chunk)}건): {type(ex).__name__}")
                if not ok_call:
                    for e in chunk:
                        e["verdict"], e["reason"] = "skip", "lock_failed"
                        skipped["lock_failed"] = skipped.get("lock_failed", 0) + 1
                    continue
                # 재조회로 잠금 확인된 것만 신규잠금으로 센다
                vf, ve = b.find([_order_key(e) for e in chunk])
                for e in chunk:
                    k = _order_key(e)
                    hit = [it for it in vf.get(k, []) if it.get("productId") == e["bulsaja_id"]]
                    if k not in ve and len(hit) == 1 and R.lock_state(hit[0]) is True:
                        e["verdict"], e["reason"] = "locked_new", None
                        result["totals"]["locked_new"] += 1
                        new_locks.append({"마켓번호": e["market"], "마켓명": result["markets"][e["market"]]["name"],
                                          "판매자상품코드": e["seller_code"], "스스상품번호": e["product_id"],
                                          "불사자ID": e["bulsaja_id"]})
                        log(f"  잠금 ✅ {e['market']} {e['seller_code'] or e['product_id']}")
                    else:
                        e["verdict"], e["reason"] = "skip", "lock_unverified"
                        skipped["lock_unverified"] = skipped.get("lock_unverified", 0) + 1

        # ⑧ 산출물
        result["finished_at"] = datetime.now(R.KST).isoformat()
        memo = R.summary_memo(result)
        result["summary"] = memo
        nl_path = os.path.join(run_dir, "new_locks.json")
        merged = []
        try:
            with open(nl_path, encoding="utf-8") as f:
                merged = json.load(f) or []
        except (OSError, ValueError):
            merged = []
        have = {(x.get("마켓번호"), x.get("판매자상품코드") or x.get("스스상품번호")) for x in merged}
        for x in new_locks:
            k = (x["마켓번호"], x["판매자상품코드"] or x["스스상품번호"])
            if k not in have:
                merged.append(x)
                have.add(k)
        _write_json(nl_path, merged, log.secrets)

        # ⑨ 업무판 '오늘' 탭 1행 — 실패해도 result.json 은 남긴다
        try:
            col = board_get(work_board_id, "'오늘'!A:A") or []
            nums = []
            for r in col:
                try:
                    nums.append(int(str(r[0]).strip()))
                except (ValueError, IndexError, TypeError):
                    pass
            todo = f"⑥ 판매상품 잠금 {args.date}"
            if args.dry_run:
                todo = "[dry-run] " + todo
            row = [max(nums, default=0) + 1, now.strftime("%Y-%m-%d"), R.checked_flag(result),
                   todo, "⑥", "Claude", "자동", memo, ""]
            board_append(work_board_id, "오늘", [row])
            result["board"] = {"status": "ok"}
        except Exception as e:
            result["board"] = {"status": "failed",
                               "error": R.redact(f"{type(e).__name__}: {e}", log.secrets)[:300]}
            log("[경고] 업무판 기록 실패 (result.json 은 남김)")
        _write_json(os.path.join(run_dir, "result.json"), result, log.secrets)
        log(f"[완료] {memo}")
        log(f"  산출물: {run_dir}")
        return 0
    finally:
        try:
            mcp.close()
        except Exception:
            pass


def build_parser():
    ap = argparse.ArgumentParser(description="판매상품 자동잠금 — 전날 결제완료 주문 상품을 불사자에서 잠금")
    ap.add_argument("--date", default=None, help="대상 날짜 YYYY-MM-DD (기본: KST 어제)")
    ap.add_argument("--dry-run", action="store_true", help="판정만 하고 불사자에 쓰지 않는다")
    ap.add_argument("--markets", default=None, help="쉼표 구분 마켓번호(예 1-1,2-1). 기본 52마켓 전체")
    ap.add_argument("--expect-nick", default="부킹", help="기대 불사자 계정 닉네임")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.date is None:
            args.date = R.default_target_date()
        R.day_range_kst(args.date)
        if args.markets:
            R.parse_markets_arg(args.markets)
    except ValueError as e:
        print(f"[오류] 인자: {e}", flush=True)
        return 1
    try:
        return run(args)
    except Exception as e:
        print(f"[오류] 예기치 못한 실패: {type(e).__name__}", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
