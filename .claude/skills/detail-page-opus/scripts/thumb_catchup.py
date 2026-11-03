# -*- coding: utf-8 -*-
"""상세는 이미 돼 있는데 대표 썸네일 워터마크가 없는 상품 → 워터마크 넣고 스마트스토어 수정 전송.

대상(2026-11-03 용팀장 지시):
  ① 고퀄 상세를 불사자에 반영한 상품(로컬 *_opus/_apply/before_apply.* 있음)
  ② 대상 뽑기에서 '이미 가공됨(불사자 기록)'으로 빠진 상품(불사자 AI 상세·직접 업로드 흔적) — targets.json 의 skipped
워터마크가 이미 대표에 있으면 thumb_wm 이 건너뛴다(기록 주소 == 현재 대표). 반영 안 한 보류·탈락 상품은 대상 아님.
진행 기록: batches/thumb_catchup.jsonl(처리분 재실행 시 건너뜀).

사용법:
  python thumb_catchup.py [--targets <targets.json> ...] [--dry-run] [--limit N]
"""
import argparse
import glob
import json
import sys
import time
from pathlib import Path

import common
import thumb_wm

PAGES = Path.home() / ".aside/u/0/detail-pages"
LOG = common.BATCH_ROOT / "thumb_catchup.jsonl"


def local_applied():
    """반영까지 한 고퀄 상세 → {pid: (market, 최신 _opus 폴더)}"""
    out = {}
    for d in sorted(glob.glob(str(PAGES / "*/*/*_opus"))):
        if glob.glob(d + "/_apply/before_apply.*"):
            p = Path(d)
            out[p.parts[-2]] = (p.parts[-3], p)
    return out


def from_targets(paths):
    """targets.json 의 '이미 가공됨' 건 → [{code, productId, market}]"""
    rows = []
    for t in paths:
        try:
            d = json.loads(Path(t).read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  [경고] {t} 읽기 실패 {e}", flush=True); continue
        rows += [x for x in d.get("skipped") or [] if str(x.get("skip", "")).startswith("이미 가공됨")]
    return rows


def done_codes():
    try:
        return {json.loads(l)["productId"] for l in LOG.read_text(encoding="utf-8").splitlines() if l.strip()}
    except Exception:
        return set()


def main():
    ap = argparse.ArgumentParser(description="썸네일 워터마크 따라잡기")
    ap.add_argument("--targets", nargs="*", default=[])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    loc = local_applied()
    items = {pid: {"code": None, "productId": pid, "market": mk, "outdir": od} for pid, (mk, od) in loc.items()}
    for x in from_targets(a.targets):
        pid = x.get("productId")
        if pid and pid not in items:
            items[pid] = {"code": x.get("code"), "productId": pid, "market": x.get("market"), "outdir": None}
    seen = done_codes()
    todo = [v for k, v in items.items() if k not in seen]
    if a.limit:
        todo = todo[:a.limit]
    print(f"[대상] 고퀄 반영 {len(loc)} + 불사자 가공 {len(items) - len(loc)} · 이미 처리 {len(items) - len([k for k in items if k not in seen])} · 이번 {len(todo)}", flush=True)

    import batch   # market_send 재사용
    sent = []
    for i, x in enumerate(todo, 1):
        pid = x["productId"]
        try:
            m = common.mcp()
            try:
                wd = common.call(m, "bulsaja_product_workdata", {"productId": pid, "mode": "full"}).get("data") or {}
                gid = wd.get("uploadSelectedMarketGroupId")
                mk = x["market"]
                if not mk and gid:
                    mk = common.market_no(common.call(m, "bulsaja_market_groups", {"groupId": int(gid)}).get("그룹명"))
            finally:
                m.close()
            if not wd:
                res, note = "failed", "불사자에서 상품 못 찾음"
            elif not mk or not gid:
                res, note = "failed", f"마켓번호·그룹 불명 ({mk}, {gid})"
            else:
                od = x["outdir"] or PAGES / mk / pid / "thumb-only"
                od.mkdir(parents=True, exist_ok=True)
                res, note = thumb_wm.run(x["code"], pid, mk, od, dry=a.dry_run)
                if res == "applied":
                    tid, r = batch.market_send({"productId": pid, "marketGroupId": int(gid)})
                    note += f" · 전송 {r}"
                    if tid:
                        sent.append(str(tid))
                    else:
                        res = "applied_send_failed"
        except Exception as e:
            res, note = "failed", f"예외 {e}"
        print(f"  ({i}/{len(todo)}) {x['code'] or ''} {pid} {res} — {note}", flush=True)
        if not a.dry_run and res in ("applied", "skipped", "applied_send_failed"):
            with LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"productId": pid, "code": x["code"], "res": res, "note": note,
                                    "at": time.strftime("%Y-%m-%d %H:%M")}, ensure_ascii=False) + "\n")
    print(f"[끝] 전송 접수 {len(sent)}건", flush=True)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    try:
        main()
    except Exception as e:
        print(f"[오류] {e}")
        sys.exit(1)
