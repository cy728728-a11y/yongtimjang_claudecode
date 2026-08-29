#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""① 노출 0 소재의 입찰가를 10원 올린다. 이 스킬에서 돈이 나가는 유일한 곳이다.

가드레일(2026-08-28~29 확정):
  1. enable=true 인 소재만            — 꺼진 광고 입찰가를 올리지 않는다
  2. 7일 노출 0 만                    — 30일 노출0 은 포기 후보이지 인상 대상이 아니다
  3. 그룹입찰이면 개별 전환 + 그룹기본가+10원
  4. 상한 200원 — 도달분은 상한도달-무노출 리스트
  5. 3주 연속 인상 실패면 중단
  6. 실행 전 원본 adAttr 전량 백업
  7. 결과를 이력에 기록
쓰기 방법(실측): PUT /ncc/ads/{adId}?fields=adAttr, body = 조회한 소재 객체 전체
"""
import json
import time
from datetime import date

import ledger
import nvad


def plan_raise(row, ledger_data, today=None):
    """이 소재를 어떻게 할지 정한다. 네트워크를 타지 않는다.

    `today` 를 넘기면 ledger.bid_decision 이 "오늘 이미 인상한 소재" 를 걸러낸다(Critical 1) —
    안 넘기면(기존 호출부 호환) 그 체크는 건너뛴다.
    """
    # 그룹입찰을 따르는 상품은 '잠자던 bidAmt' 가 아니라 그룹 기본가가 출발점이다
    base = row.get("groupBid") if row.get("useGroupBid") else row.get("bid")
    action, new = ledger.bid_decision(ledger_data, row["adId"], base, today=today)
    return {"adId": row["adId"], "title": row.get("title", ""), "action": action,
            "from": base, "to": new, "useGroupBid": bool(row.get("useGroupBid"))}


def build_body(ad_obj, new_bid):
    """PUT 본문. 조회한 소재 객체 전체에 adAttr 만 갈아끼운다.

    useGroupBidAmt 는 False 로 바꾼다 — 개별 입찰가를 적용하려면 필수다.
    가역적이므로(실측 확인) 되돌릴 수 있다.
    """
    body = dict(ad_obj)
    body["adAttr"] = dict(ad_obj.get("adAttr") or {})
    body["adAttr"]["bidAmt"] = new_bid
    body["adAttr"]["useGroupBidAmt"] = False
    return body


def apply_raise(acct, ad_obj, new_bid):
    """실제로 입찰가를 바꾼다. (성공여부, 메시지).

    Important 9: prune.delete_ads 와 회복력을 맞춘다 — 429/5xx 는 최대 4회 재시도(지수
    백오프)한다. 2,242건 연속 PUT 중 429 하나로 그 소재가 그 주 인상에서 빠지면 안 된다.
    """
    body = build_body(ad_obj, new_bid)
    st, res = 0, ""
    for attempt in range(4):
        st, res = nvad.call(acct, "PUT", f"/ncc/ads/{ad_obj['nccAdId']}",
                            params={"fields": "adAttr"}, body=body)
        if st in (200, 201):
            return True, ""
        if st in (429, 500, 502, 503, 0):
            time.sleep(2 * (attempt + 1))
            continue
        return False, f"{st} {str(res)[:150]}"
    return False, f"{st} {str(res)[:150]} (재시도 소진)"


def build_revert_body(ad_obj, original_attr):
    """되돌리기 PUT 본문 — adAttr 를 백업된 원본 그대로 되쓴다(Important 4).

    `useGroupBidAmt` 도 원본 값 그대로 복원되므로 개별 전환도 함께 취소된다
    (2026-08-27 실측: 이 전환은 가역적이다).
    """
    body = dict(ad_obj)
    body["adAttr"] = dict(original_attr)
    return body


def apply_revert(acct, ad_obj, original_attr):
    """백업된 원본 adAttr 로 되돌린다. (성공여부, 메시지)."""
    st, res = nvad.call(acct, "PUT", f"/ncc/ads/{ad_obj['nccAdId']}",
                        params={"fields": "adAttr"}, body=build_revert_body(ad_obj, original_attr))
    if st in (200, 201):
        return True, ""
    return False, f"{st} {str(res)[:150]}"


def update_streaks(led, zero_ids, recovered_ids, run_date, log=print):
    """지난 회차에 올린 소재가 이번에도 노출 0인지 보고 연속 실패를 갱신한다.

    **이 함수가 없으면 streak 이 영원히 0 이라 "3주 연속 올렸는데도 노출 0이면 중단"
    규칙이 실전에서 절대 발동하지 않는다.** ledger 에 record_still_zero·record_recovered
    가 있어도 부르는 곳이 없으면 죽은 코드다.

    Critical 2: `zero_ids` 에 없다고 무조건 "노출이 회복됐다" 로 보면 안 된다 — 규칙 ①은
    검수중·비활성 소재를 제외하므로, 상품명만 고쳐 검수에 들어가도 `zero_ids` 에서 빠져
    streak 이 조용히 리셋된다(ownway1 실측: 검수중 988건). 그래서 "실제로 노출이 생긴
    소재" 집합(`recovered_ids` = 이번 회차 stats_7d 에 행이 있는 소재)을 별도로 받아,
    `record_recovered` 는 **그 집합에 있는 소재에만** 부른다. ①에서도 빠지고 노출도
    없는 소재(검수중 등)는 streak 을 건드리지 않는다(유지).

    같은 회차를 두 번 돌려도 streak 이 두 번 오르지 않도록 날짜를 기록한다.
    """
    if led.get("_last_streak_update") == run_date:
        return 0, 0
    still = rec = 0
    for ad_id, e in list(led.items()):
        # 밑줄 키는 메타값이고, 한 번도 안 올린 소재는 연속 판정 대상이 아니다
        if ad_id.startswith("_") or not isinstance(e, dict) or not e.get("raises"):
            continue
        if ad_id in zero_ids:
            ledger.record_still_zero(led, ad_id)
            still += 1
        elif ad_id in recovered_ids:
            ledger.record_recovered(led, ad_id)
            rec += 1
        # else: 검수중·비활성 등으로 ①에서도 빠지고 노출도 없다 — streak 을 건드리지 않는다
    led["_last_streak_update"] = run_date
    log(f"  이력 갱신: 인상 뒤에도 노출0 {still}건 · 노출 회복 {rec}건")
    return still, rec


def run_bids(acct, run_dir, rows, commit=False, log=print):
    """규칙 ① 대상 전체를 처리한다. commit 이 False 면 계획만 세운다."""
    alias = acct.get("alias") or str(acct.get("customer_id"))
    led_path = run_dir.parent.parent / "ledger" / f"{alias}.json"
    led = ledger.load(led_path)
    today = date.today().isoformat()

    # 이번 회차 7일 통계에 실제로 행이 있는 소재 = 노출이 실제로 생긴 소재(Critical 2).
    # "①노출0 에 없음" 만으로 회복을 판단하면 검수중 등으로 빠진 것까지 회복으로 오인한다.
    stats7_path = run_dir / "accounts" / alias / "stats_7d.json"
    try:
        recovered_ids = set(json.loads(stats7_path.read_text(encoding="utf-8")).keys())
    except Exception as e:
        log(f"[{alias}] 7일 통계 읽기 실패(회복 판정 생략): {type(e).__name__}: {e}")
        recovered_ids = set()

    # 지난 회차 인상의 결과를 먼저 반영한다 — 이게 판정보다 앞서야
    # "3주 연속 실패" 가 이번 회차 판정에 반영된다.
    # dry-run 은 메모리에서만 갱신하고 파일에 쓰지 않는다.
    update_streaks(led, {r["adId"] for r in rows}, recovered_ids, today, log=log)

    # 저장된 소재 스냅샷(prep 시점 ads.json)을 다시 읽는다 — 실시간 재조회가 아니라
    # 디스크에 있는 같은 스냅샷이다. PUT 본문에 필요한 소재 객체 전체(adAttr 외 필드
    # 포함)를 얻으려는 목적이고, 스테일 위험은 build_body 가 adAttr 만 덮어써서 크지 않다.
    ad_by_id = {}
    ads_path = run_dir / "accounts" / alias / "ads.json"
    try:
        for a in json.loads(ads_path.read_text(encoding="utf-8"))["ads"]:
            ad_by_id[a["nccAdId"]] = a
    except Exception as e:
        log(f"[{alias}] 소재 읽기 실패: {type(e).__name__}: {e}")
        return {}

    plans = [plan_raise(r, led, today=today) for r in rows]
    counts = {}
    for p in plans:
        counts[p["action"]] = counts.get(p["action"], 0) + 1

    log(f"[{alias}] 대상 {len(plans)}건 → " + " · ".join(f"{k} {v}" for k, v in counts.items()))
    for p in plans[:10]:
        log(f"    {p['action']:<10} {str(p['from']):>4}→{str(p['to']):<4} {p['title'][:30]}")
    if len(plans) > 10:
        log(f"    … 외 {len(plans)-10}건")

    if not commit:
        log("  (dry-run — --commit 을 주면 실제로 바꾼다)")
        return {"plans": plans, "counts": counts, "committed": 0}

    # 백업 먼저 — 실행 전 원본 adAttr 전량. 되돌릴 수단 없이 광고비를 건드리면 안 된다.
    bk = run_dir / f"before_bids_{alias}.json"
    try:
        bk.write_text(json.dumps(
            {p["adId"]: (ad_by_id.get(p["adId"], {}).get("adAttr")) for p in plans if p["action"] == "인상"},
            ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:
        log(f"  ✗ 백업 실패 — 인상을 중단한다: {type(e).__name__}: {e}")
        return {"plans": plans, "counts": counts, "committed": 0, "aborted": "backup_failed"}
    log(f"  백업 → {bk.name}")

    ok = fail = 0
    try:
        for p in plans:
            if p["action"] != "인상":
                continue
            ad_obj = ad_by_id.get(p["adId"])
            if not ad_obj:
                fail += 1
                continue
            good, err = apply_raise(acct, ad_obj, p["to"])
            if good:
                ok += 1
                ledger.record_raise(led, p["adId"], today, p["from"], p["to"])
            else:
                fail += 1
                log(f"    ✗ {p['adId']} {err}")
            time.sleep(0.08)   # prune.delete_ads 와 같은 페이싱 — 초당 12건
    finally:
        # 중간에 끊겨도 이미 올린 것은 반드시 남긴다.
        # 안 남기면 다음 회차가 같은 상품 입찰가를 또 올린다.
        ledger.save(led_path, led)
    log(f"  인상 완료 {ok}건 / 실패 {fail}건 · 이력 → {led_path}")
    return {"plans": plans, "counts": counts, "committed": ok, "failed": fail}


def run_revert(acct, run_dir, commit=False, log=print):
    """Important 4 — 인상을 되돌린다.

    `before_bids_<alias>.json` 백업(run_bids 가 인상 직전 원본 adAttr 전량을 남긴 것)을
    읽어 각 소재의 원본 adAttr 그대로 되쓴다. `--commit` 없이는 무엇을 되돌릴지만 보여준다.
    """
    alias = acct.get("alias") or str(acct.get("customer_id"))
    bk_path = run_dir / f"before_bids_{alias}.json"
    try:
        backup = json.loads(bk_path.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"[{alias}] 백업 파일 읽기 실패({bk_path}): {type(e).__name__}: {e}")
        return {}
    if not backup:
        log(f"[{alias}] 되돌릴 항목 없음")
        return {"targets": 0}

    ad_by_id = {}
    ads_path = run_dir / "accounts" / alias / "ads.json"
    try:
        for a in json.loads(ads_path.read_text(encoding="utf-8"))["ads"]:
            ad_by_id[a["nccAdId"]] = a
    except Exception as e:
        log(f"[{alias}] 소재 읽기 실패: {type(e).__name__}: {e}")
        return {}

    targets = [ad_id for ad_id, attr in backup.items() if attr is not None]
    log(f"[{alias}] 되돌릴 대상 {len(targets)}건")
    for ad_id in targets[:10]:
        log(f"    {ad_id} → {backup[ad_id]}")
    if len(targets) > 10:
        log(f"    … 외 {len(targets)-10}건")

    if not commit:
        log("  (dry-run — --commit 을 주면 실제로 되돌린다)")
        return {"targets": len(targets), "committed": 0}

    led_path = run_dir.parent.parent / "ledger" / f"{alias}.json"
    led = ledger.load(led_path)
    today = date.today().isoformat()
    ok = fail = 0
    try:
        for ad_id in targets:
            ad_obj = ad_by_id.get(ad_id)
            if not ad_obj:
                fail += 1
                continue
            good, err = apply_revert(acct, ad_obj, backup[ad_id])
            if good:
                ok += 1
                ledger.record_reverted(led, ad_id, today)
            else:
                fail += 1
                log(f"    ✗ {ad_id} {err}")
            time.sleep(0.08)
    finally:
        ledger.save(led_path, led)
    log(f"  되돌리기 완료 {ok}건 / 실패 {fail}건 · 이력 → {led_path}")
    return {"targets": len(targets), "committed": ok, "failed": fail}
