#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⑥ 꺼진 소재(enable=false) 삭제. 되돌릴 수 없으므로 백업이 선행 조건이다.

2026-08-29 첫 회차로 5,062건을 삭제했다(실패 0). 꺼진 사유는 거의 전부
AD_ABNORMAL_INTERLOCK(연동 비정상) — 사용자가 끈 게 아니라 시스템 자동 일시중지다.
원인은 미규명이고 지금도 발생 중이라, 신규 발생 건수를 매주 보고해야 한다.
"""
import json
import time
from collections import Counter
from datetime import date

import nvad

# 재등록에 필요한 최소 필드 + 원본 통째로
BACKUP_KEYS = ("nccAdId", "nccAdgroupId", "referenceKey", "type", "adAttr",
               "status", "statusReason", "inspectStatus", "regTm", "editTm")

# 삭제하는 사유는 이것뿐이다 — 연동 비정상.
# 검수중(AD_UNDER_REVIEW)·검수거부(AD_DISAPPROVED)는 **지우지 않는다**:
# 검수중은 곧 살아나고, 거부는 고쳐서 재검수할 수 있다. 지우면 둘 다 재등록 노동이 된다.
# (2026-08-30 실측: ownway1 잔여 20건 = 검수중 17·거부 3, pogeunae 12건 = 거부 11·검수중 1)
DELETE_REASONS = ("AD_ABNORMAL_INTERLOCK",)


def deletable(ads):
    """삭제 대상만 고른다 — 꺼져 있고 사유가 DELETE_REASONS 인 것."""
    return [a for a in ads if not a.get("enable") and a.get("statusReason") in DELETE_REASONS]


def backup_paused(acct, ads, out_dir):
    """삭제 대상을 백업한다. referenceKey·mallProductId 가 있어야 재등록이 가능하다.

    실패하면 None 을 돌려준다 — 호출자가 그 계정의 삭제를 건너뛴다.
    되돌릴 수단 없이 지우지 않는다.
    """
    alias = acct.get("alias") or str(acct.get("customer_id"))
    rows = []
    for a in deletable(ads):
        rd = a.get("referenceData") or {}
        row = {k: a.get(k) for k in BACKUP_KEYS}
        row.update({
            "mallProductId": rd.get("mallProductId"),
            "productTitle": rd.get("productTitle"),
            "referenceData": rd,
        })
        rows.append(row)
    path = out_dir / f"paused_{alias}_{date.today().isoformat()}.json"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"account": alias, "customer_id": acct.get("customer_id"),
                                    "reason": list(DELETE_REASONS), "count": len(rows), "ads": rows},
                                   ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:
        print(f"  ✗ 백업 실패 — 이 계정은 삭제하지 않는다: {type(e).__name__}: {e}")
        return None
    return path


def delete_ads(acct, ad_ids, progress_path, log=print):
    """소재를 삭제한다. 진행 파일로 재개 가능하고, 404 는 이미 없는 것으로 성공 처리한다."""
    done = set()
    if progress_path.exists():
        try:
            for line in progress_path.read_text(encoding="utf-8").splitlines():
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                # **성공한 것만 건너뛴다.** 하드 에러(400·403 등)까지 done 에 넣으면
                # 실제로는 안 지워졌는데 영영 재시도하지 않고 매주 조용히 스킵된다
                if r.get("status") in (200, 204, 404):
                    done.add(r.get("nccAdId"))
        except Exception as e:
            print(f"  진행 파일 읽기 실패(처음부터 진행한다): {type(e).__name__}: {e}")
            done = set()
    todo = [i for i in ad_ids if i not in done]
    log(f"  삭제 대상 {len(todo)}건 (이미 처리 {len(done)})")

    stat = Counter()
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    with progress_path.open("a", encoding="utf-8") as fp:
        for n, aid in enumerate(todo, 1):
            for attempt in range(4):
                st, res = nvad.call(acct, "DELETE", f"/ncc/ads/{aid}")
                if st in (200, 204, 404):
                    stat["ok" if st != 404 else "already"] += 1
                    fp.write(json.dumps({"nccAdId": aid, "status": st}) + "\n")
                    break
                if st in (429, 500, 502, 503, 0):
                    time.sleep(2 * (attempt + 1))
                    continue
                stat[f"err{st}"] += 1
                fp.write(json.dumps({"nccAdId": aid, "status": st, "err": str(res)[:200]},
                                    ensure_ascii=False) + "\n")
                break
            else:
                stat["retry_exhausted"] += 1
            if n % 250 == 0:
                fp.flush()
                log(f"    {n}/{len(todo)} {dict(stat)}")
            time.sleep(0.08)   # 초당 12건 — 5,062건 실측에서 429 가 없었다
    return dict(stat)


def run_prune(acct, run_dir, commit=False, log=print):
    """계정 1개의 꺼진 소재를 백업하고 삭제한다."""
    alias = acct.get("alias") or str(acct.get("customer_id"))
    try:
        ads = json.loads((run_dir / "accounts" / alias / "ads.json").read_text(encoding="utf-8"))["ads"]
    except Exception as e:
        log(f"[{alias}] 소재 읽기 실패: {type(e).__name__}: {e}")
        return {}

    off = [a for a in ads if not a.get("enable")]
    reasons = Counter(a.get("statusReason") or "?" for a in off)
    tgt = deletable(ads)
    keep = Counter(a.get("statusReason") or "?" for a in off
                   if a.get("statusReason") not in DELETE_REASONS)
    log(f"[{alias}] 꺼진 소재 {len(off)}건 · 삭제대상 {len(tgt)} · 보존 {dict(keep)}")
    if tgt:
        log(f"  ⚠ 연동 비정상 {len(tgt)}건 — 원인 미규명. 매주 삭제만 하면 소재가 줄어들기만 한다")

    if not tgt:
        return {"paused": len(off), "deletable": 0, "reasons": dict(reasons)}

    backup_root = run_dir.parent.parent / "paused-backup"
    bk = backup_paused(acct, ads, backup_root)
    if bk is None:
        # 백업이 없으면 되돌릴 수단이 없다 — 이 계정은 지우지 않고 넘어간다
        return {"paused": len(off), "deletable": len(tgt), "reasons": dict(reasons),
                "aborted": "backup_failed"}
    log(f"  백업 {len(tgt)}건 → {bk}")

    if not commit:
        log("  (dry-run — --commit 을 주면 실제로 지운다)")
        return {"paused": len(off), "deletable": len(tgt), "reasons": dict(reasons),
                "backup": str(bk), "deleted": 0}

    stat = delete_ads(acct, [a["nccAdId"] for a in tgt],
                      backup_root / f"delete_progress_{alias}.jsonl", log=log)
    log(f"  삭제 결과 {stat}")
    return {"paused": len(off), "deletable": len(tgt), "reasons": dict(reasons),
            "backup": str(bk), "result": stat}
