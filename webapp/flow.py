#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""3단 계약(판정 → 미리보기 → 실행)을 **파일로** 잇는 곳이다.

화면 상태가 아니라 파일이 진실이다 (FLOW-02 / D-11):

    [판정]     run-dir/result.json              ← CLI 가 이미 써 둔 것
       ↓ 사용자가 상품 줄 선택 → 그 상품의 ①소재 adId 만 (D-06)
    [대상]     run-dir/web/targets_<job>.json   ← create_job 안에서 딱 한 번
       ↓ --only-ads targets_<job>.json
    [미리보기] run-dir/web/preview_<job>.json    ← CLI 가 --preview-out 으로
       ↓ 같은 targets 파일을 재사용 (Plan 01-08)
    [실행]     run-dir/web/result_<job>.json

**그리고 여기서 입찰가를 계산하지 않는다.** ①행의 92%(2,063/2,242)가 그룹입찰이라
재계산하면 올리려다 내린다 — 잠자던 `adAttr.bidAmt` 는 50 인데 실제 적용값은 그룹
기본가 70 이다. 재계산하면 50→60, 즉 **인하**다(실측). `plan_raise` 가 이미 그 해석을
끝내 `from`/`to` 에 담아 놨으므로 웹앱은 읽어서 표시만 한다 (위협 T-1-07 / BID-02).

`to - from` 을 빼는 것은 산술이 아니라 **표시**다. `bid + 10` 처럼 없던 값을
만들어내는 것과 구분해라 — 전자는 산출물 두 값의 차이고, 후자는 두 번째 정본이다.
"""
import json
from pathlib import Path

from webapp import settings

# `ledger.bid_decision` 이 내는 판정 5종. 집계 줄의 **표시 순서**로만 쓴다 —
# 여기 없는 판정이 생겨도 버리지 않고 뒤에 붙인다(스킵을 조용히 하지 않는다).
ACTION_ORDER = ("인상", "최근인상", "연속실패중단", "상한도달", "입찰가불명")

# 표를 통째로 그리면 1,195줄짜리 계정에서 브라우저가 멈춘다. 잘린 사실은 반드시
# 말한다 — `report_md._count_label` 관례(`2,242건 중 상위 200건`).
PREVIEW_ROW_LIMIT = 200


class LimitError(ValueError):
    """1회 실행 계정별 상한 초과 (D-08). 라우트가 400 으로 번역한다."""


def _키(row: dict) -> str:
    """보드 행의 접기 키. `board.js` 가 만드는 `acct + "|" + mallProductId` 와 같다."""
    return f"{row.get('acct')}|{row.get('mallProductId')}"


def collect_rule1_ads(rows: list[dict], selected_keys=None) -> dict[str, list[str]]:
    """선택된 상품 줄 → **계정별 ①소재 adId 목록** (BID-01 / D-06 / T-1-30).

    `rows` 는 `board.fold_products` 결과다. 거기서 `rule1_ads` 만 평탄화하므로
    ②③④⑤⑥ 소재는 **구조적으로** 못 들어온다 — `fold_products` 가 규칙별 adId 를
    이미 갈라 담아 뒀기 때문이다. `run_bids` 가 받는 rows 자체가 `①노출0` 이라,
    다른 규칙 소재를 보내면 CLI 쪽에서 조용히 사라진다(화면은 "6건" 이라 말하고
    실제로는 4건인 상태).

    `selected_keys=None` 이면 **전 상품**이다. 그 모양이 곧 "이 회차에서 인상 대상이
    될 수 있는 소재 전부" 의 정답지이고, `collect_targets` 가 그걸 관문으로 쓴다.

    모르는 키는 무시하지 않고 `ValueError` — 화면과 서버가 다른 회차를 보고 있다는
    신호라, 조용히 빼면 "고른 것보다 적게 처리됐다" 가 된다.
    """
    있는것 = {_키(r): r for r in rows}
    키들 = list(있는것) if selected_keys is None else list(selected_keys)

    모름 = [k for k in 키들 if k not in 있는것]
    if 모름:
        raise ValueError(f"보드에 없는 상품이 {len(모름)}건 섞였다 — 회차를 다시 열어라")

    계정별: dict[str, list[str]] = {}
    본것: set[str] = set()
    for k in 키들:
        r = 있는것[k]
        for adId in r.get("rule1_ads") or []:
            if adId in 본것:
                continue        # 같은 소재에 두 번 쏘지 않는다
            본것.add(adId)
            계정별.setdefault(r["acct"], []).append(adId)
    return 계정별


def collect_targets(rows: list[dict], ad_ids) -> dict[str, list[str]]:
    """화면이 보낸 adId 를 **서버가 다시 검증해** 계정별로 묶는다 (T-1-30).

    브라우저 선택 상태는 신뢰 경계 밖이다. 여기서 `collect_rule1_ads(rows)` 가 만든
    정답지 밖의 adId 는 거부한다 — 버리지 않고 거부하는 이유는, 버리면 "고른 N건" 과
    "처리된 M건" 이 조용히 갈라지기 때문이다.
    """
    허용 = {}
    for alias, ids in collect_rule1_ads(rows).items():
        for adId in ids:
            허용[adId] = alias

    계정별: dict[str, list[str]] = {}
    본것: set[str] = set()
    모름 = 0
    for adId in ad_ids:
        alias = 허용.get(adId)
        if alias is None:
            모름 += 1
            continue
        if adId in 본것:
            continue
        본것.add(adId)
        계정별.setdefault(alias, []).append(adId)
    if 모름:
        raise ValueError(f"규칙① 소재가 아닌 대상이 {모름}건 섞였다 — 보드를 새로고침해라")
    return 계정별


def check_limits(by_account: dict[str, list[str]]) -> None:
    """계정별 건수가 상한을 넘으면 `LimitError` (D-08 / T-1-29).

    **총합이 아니라 계정별이다.** 실측 최대가 ownway1 1,195 · pogeunae 1,028 이라
    평상시 마찰이 0 이고, 이 가드는 "계정이 이상하게 불어났다" 는 사고만 잡는다.
    숫자를 여기 박지 않는다 — `settings.PER_ACCOUNT_LIMIT` 에서 **매번 읽는다**.
    모듈 상수로 굳히면 설정을 고쳐도 동작이 안 따라와 가드가 있는 척만 한다.
    """
    한계 = settings.PER_ACCOUNT_LIMIT
    for alias, ids in by_account.items():
        if len(ids) > 한계:
            raise LimitError(f"{alias} 계정 {len(ids)}건 — 1회 상한 {한계}건을 넘었다")


def read_preview(path) -> dict:
    """CLI 산출물을 읽는다. **빈 dict 를 성공으로 보지 마라** (T-1-33).

    `run_bids` 는 소재 스냅샷을 못 읽으면 `{}` 를 리턴한다. 그게 그대로 산출물이 되면
    "대상 0건" 과 "측정조차 못 했다" 가 같은 화면이 된다 — 후자는 다시 수집해야 하는
    상태고, 전자는 정상이다.

    돌려주는 모양:
        {"accounts": {alias: {plans, counts, committed}}, "blind": [alias…], "error": None|"사유"}

    `error` 는 읽기 자체가 실패했거나 산출물이 통째로 비었을 때만 찬다.
    계정 하나만 `{}` 면 전체 실패가 아니라 그 계정만 `blind` 다.
    """
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as e:
        # 트레이스백을 화면에 싣지 않는다 (ASVS V7) — 이름과 메시지로 줄인다.
        return {"accounts": {}, "blind": [], "error": f"{type(e).__name__}: {e}"}

    if not isinstance(raw, dict) or not raw:
        return {"accounts": {}, "blind": [],
                "error": "산출물이 비어 있다 — 소재 스냅샷을 못 읽었을 수 있다. 새로 수집부터 해라"}

    계정들, 눈먼것 = {}, []
    for alias, v in raw.items():
        if isinstance(v, dict) and v.get("plans") is not None:
            계정들[alias] = v
        else:
            눈먼것.append(alias)
    return {"accounts": 계정들, "blind": sorted(눈먼것), "error": None}


def summarize_counts(preview: dict) -> dict[str, int]:
    """action 별 집계 — **CLI 가 준 `counts` 를 합산한다** (Pitfall 6 / T-1-32).

    plans 를 다시 세지 않는다. CLI 가 센 값과 화면이 센 값이 어긋나면, 어느 쪽이
    맞는지 사람이 판단할 근거가 화면에 없다.
    """
    합 = {}
    for v in (preview.get("accounts") or {}).values():
        for action, n in ((v or {}).get("counts") or {}).items():
            합[action] = 합.get(action, 0) + int(n)
    순서 = {a: i for i, a in enumerate(ACTION_ORDER)}
    return {k: 합[k] for k in sorted(합, key=lambda a: (순서.get(a, len(순서)), a))}


def raise_total(preview: dict) -> int:
    """`action == "인상"` 인 plan 의 `to - from` 합 (BOARD-04).

    입찰가는 크레딧이 0 이라 "예상 비용" 자리를 이 값이 대신한다.
    스킵 액션은 더하지 않는다 — `to` 가 None 이기도 하고, 더하면 "올릴 수 없는
    소재의 인상액" 이라는 없는 숫자가 생긴다.
    """
    합 = 0
    for v in (preview.get("accounts") or {}).values():
        for p in (v or {}).get("plans") or []:
            if p.get("action") != "인상":
                continue
            frm, to = p.get("from"), p.get("to")
            if frm is None or to is None:
                continue
            합 += to - frm
    return 합


def preview_rows(preview: dict, limit: int | None = PREVIEW_ROW_LIMIT) -> list[dict]:
    """미리보기 표의 줄 — **소재(adId) 단위** (D-05).

    보드 줄은 상품이고 여기는 소재다. 실제로 가격이 바뀌는 단위가 소재라,
    화면과 실행이 1:1 로 맞아야 "무엇이 바뀌는지" 를 사람이 셀 수 있다.
    `from`/`to`/`useGroupBid` 는 산출물 값 **그대로** 옮긴다.
    """
    줄 = []
    for alias, v in (preview.get("accounts") or {}).items():
        for p in (v or {}).get("plans") or []:
            줄.append({
                "acct": alias,
                "adId": p.get("adId"),
                "title": p.get("title") or "",
                "action": p.get("action"),
                "from": p.get("from"),
                "to": p.get("to"),
                "useGroupBid": p.get("useGroupBid"),
            })
    # 인상 먼저, 그 다음 판정 순서. 사용자가 제일 먼저 확인할 줄을 위로 올린다.
    순서 = {a: i for i, a in enumerate(ACTION_ORDER)}
    줄.sort(key=lambda r: (순서.get(r["action"], len(순서)), r["acct"], r["adId"] or ""))
    return 줄 if limit is None else 줄[:limit]


def total_rows(preview: dict) -> int:
    """잘리기 전 전체 소재 줄 수. 표가 잘렸으면 잘렸다고 말하려고 따로 센다."""
    return sum(len((v or {}).get("plans") or [])
               for v in (preview.get("accounts") or {}).values())


# ── 실행 결과 (Plan 01-08) ───────────────────────────────────────────────────
#
# 결과 파일의 모양은 `bids.run_bids` 의 commit 경로 리턴이 정본이다. plans[i] 에
# `result`("성공"/"실패"/"스킵")와 `error`(사유)가 붙는다 — Plan 01-02 가 CLI 에 심었다.
# **로그를 파싱하지 않는다** (D-03). 그리고 **종료코드로 성공을 판단하지 않는다** —
# `bids` 는 PUT 이 전량 실패해도 exit 0 이다(RESEARCH §1.1). 결과 파일이 유일한 근거다.

# 결과 바구니의 **표시 순서**다. 실패·스킵이 먼저다 — 사용자가 봐야 할 것은
# 성공이 아니라 안 된 것들이다.
RESULT_ORDER = ("실패", "스킵", "실행 안 됨", "성공")


def _계정들(d: dict) -> dict:
    """`read_preview` 결과든 CLI 산출물 원본이든 계정 dict 로 만든다.

    양쪽을 다 받는 이유: 라우트는 `read_preview` 를 거치고(빈 산출물을 성공으로 보지
    않으려고), 순수 함수 검증은 산출물을 손으로 만든다. 모양을 하나로 강제하면
    호출부마다 감싸는 코드가 생기고, 그 감싸기를 빠뜨린 곳이 조용히 빈 결과를 낸다.
    """
    안 = (d or {}).get("accounts")
    if isinstance(안, dict):
        return 안
    return {k: v for k, v in (d or {}).items()
            if isinstance(v, dict) and v.get("plans") is not None}


def _plans(d: dict):
    """(계정, plan) 쌍을 계정 순서대로 흘린다."""
    for alias, v in _계정들(d).items():
        for p in (v or {}).get("plans") or []:
            yield alias, p


def _결과줄(alias: str, p: dict) -> dict:
    """결과 표의 한 줄. 값은 산출물 그대로 옮긴다 — 여기서 만들지 않는다."""
    return {
        "acct": alias,
        "adId": p.get("adId"),
        "title": p.get("title") or "",
        "action": p.get("action"),
        "from": p.get("from"),
        "to": p.get("to"),
        "result": p.get("result") or "실행 안 됨",
        "error": p.get("error") or "",
    }


def classify_results(result: dict) -> dict[str, list[dict]]:
    """성공 / 실패 / 스킵 으로 갈라 담는다 (FLOW-05 / T-1-37).

    `result` 키가 없는 plan 은 **`실행 안 됨`** 이다. dry-run 산출물을 실수로 실행
    결과로 읽었을 때가 그 모양인데, 그걸 성공으로 세면 "1,200건 올렸다" 는 거짓말이
    화면에 뜬다. 성공으로 세지 않는다.

    스킵 사유는 `bids.run_bids` 가 넣은 action 그대로다(최근인상·연속실패중단·
    상한도달·입찰가불명). 웹앱이 사유를 지어내지 않는다.
    """
    갈래: dict[str, list[dict]] = {k: [] for k in RESULT_ORDER}
    for alias, p in _plans(result):
        줄 = _결과줄(alias, p)
        갈래.setdefault(줄["result"], []).append(줄)
    return 갈래


def result_counts(result: dict) -> dict[str, int]:
    """바구니별 건수. 표시 순서는 실패·스킵이 먼저다."""
    갈래 = classify_results(result)
    순서 = {k: i for i, k in enumerate(RESULT_ORDER)}
    return {k: len(v) for k, v in sorted(갈래.items(),
                                         key=lambda kv: (순서.get(kv[0], len(순서)), kv[0]))}


def cli_totals(result: dict) -> dict[str, int]:
    """CLI 가 스스로 센 `committed`/`failed` 합.

    화면이 센 값과 **대조하려고** 따로 둔다. 둘이 어긋나면 그 사실을 화면에 적는다 —
    어느 쪽이 맞는지 사람이 판단할 근거가 화면에 있어야 한다(Pitfall 6 와 같은 판단).
    """
    합 = {"committed": 0, "failed": 0}
    for v in _계정들(result).values():
        for k in 합:
            try:
                합[k] += int((v or {}).get(k) or 0)
            except (TypeError, ValueError):
                pass
    return 합


def result_rows(result: dict, limit: int | None = PREVIEW_ROW_LIMIT) -> list[dict]:
    """결과 표의 줄 — **실패·스킵이 위**다 (T-1-37).

    잘릴 때 성공만 남기면 안 된 것들이 화면 밖으로 밀린다. 정렬이 곧 안전장치다.
    """
    순서 = {k: i for i, k in enumerate(RESULT_ORDER)}
    줄 = [_결과줄(alias, p) for alias, p in _plans(result)]
    줄.sort(key=lambda r: (순서.get(r["result"], len(순서)), r["acct"], r["adId"] or ""))
    return 줄 if limit is None else 줄[:limit]


def succeeded_ad_ids(result: dict) -> list[str]:
    """실제로 올라간 adId 목록. Plan 01-09 의 되돌리기 대상이 여기서 나온다 (D-13).

    실패·스킵을 섞지 않는다 — 안 올라간 소재를 되돌리려 들면 백업에 없는 키를 찾다가
    "되돌릴 게 없다" 로 끝나거나, 더 나쁘면 남의 원본을 덮는다.
    """
    return [p.get("adId") for _, p in _plans(result)
            if p.get("result") == "성공" and p.get("adId")]


def diff_preview(preview: dict, result: dict) -> list[dict]:
    """미리보기와 실행이 어디서 갈라졌는지 사유와 함께 (D-10 / T-1-36).

    **갈라지는 건 정상이다.** D-09 로 실행 시점 재계산을 유지했기 때문이다 —
    쿨다운·연속실패중단·상한 가드가 실행 시점 기준으로 다시 도는 편이 안전하다.
    미리보기를 보고 커피를 한 잔 마시고 눌러도, 그 사이 다른 창에서 올린 소재는
    실행 시점에 스킵된다. 그게 맞는 동작이다.

    이 함수의 일은 **갈라졌다는 사실을 숨기지 않는 것**이다. **거부하지 않는다** —
    스테일 거부(FLOW-03 / SAFE-05)는 Phase 2 다. 거부를 여기서 흉내 내면 "미리보기와
    다르다" 는 이유로 정상 실행이 막히고, 사람은 곧 미리보기를 건너뛸 길을 찾는다.
    """
    본것 = {p.get("adId"): p for _, p in _plans(preview)}
    갈림 = []
    for _, r in _plans(result):
        adId = r.get("adId")
        p = 본것.get(adId)
        if p is None:
            갈림.append({"adId": adId, "why": "미리보기에 없던 소재"})
            continue
        if (p.get("action"), p.get("to")) != (r.get("action"), r.get("to")):
            갈림.append({
                "adId": adId,
                "why": "재계산으로 바뀜",
                "before": f'{p.get("action")} {p.get("from")}→{p.get("to")}',
                "after": f'{r.get("action")} {r.get("from")}→{r.get("to")}',
            })
    return 갈림
