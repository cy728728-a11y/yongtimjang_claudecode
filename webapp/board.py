#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""보드 투영 — 판정 결과를 상품 단위 표로 **모으기만** 한다.

**읽기 전용이다. CLI 를 실행하지 않고 판정값을 만들지 않는다.** `result.json` 만 읽는다.
회차 디렉터리의 `accounts/<alias>/` 밑 소재 원본 덤프는 2.6MB × 2 인데 보드가 필요로 하는
값이 하나도 없다 — 메모리와 응답만 불린다. **열지도 않는다**(Pitfall 8 / 위협 T-1-19).
그 파일 이름을 여기 적지도 않는다: grep 가드가 이 모듈을 감시한다.

이게 STACK.md 의 "세 번째 길" 이다. 보드 데이터는 CLI 를 실행해서도, CLI 모듈을 불러와서도
얻지 않는다. CLI 가 **이미 써 둔 산출물**을 읽을 뿐이다. 그래서 이 모듈은 네트워크도
크레딧도 광고비도 0 이고, 회차 파일이 없으면 빈 목록을 돌려줄 뿐 아무것도 고장내지 않는다.

이 모듈이 절대 하지 않는 것:
  - 입찰가 산술 (`bid + 10`) — `ledger.bid_decision` 이 정본이다. 진실이 둘이 되면
    쿨다운·상한·연속실패 가드를 우회하게 된다 (PROJECT.md 제약 / 위협 T-1-07)
  - 마진·ROAS·판정 재계산 — 전부 CLI 산출물에서 읽기만 한다
  - 계정 alias 를 리터럴로 쓰기 — 계정은 `~/.eroom/` 의 광고 계정 설정 파일에 항목을
    더하는 것만으로 4개에서 6개가 된다. 목록의 유일한 출처는 `result.json` 이다 (BOARD-02)

판정행 스키마 정본은 `.claude/skills/naver-ads-weekly/scripts/ads_rules.py` 의
`ad_info` / `_with_stat` 다:

    ①노출0 · ⑥삭제대상 : adId · adGroup · title · mallProductId · bid · useGroupBid · groupBid
    ②③④              : 위 + imp · clk · ctr · rank · cost
    ⑤효자확정          : 위 + purCnt · purAmt

**①·⑥ 행에는 `imp`/`clk`/`ctr`/`rank`/`cost` 키가 아예 없다.** 7일 통계에 행이 없는
것이 규칙①의 정의이기 때문이다. 실데이터에서 그런 행이 2,274개다 — `row["imp"]` 를
쓰면 거기서 통째로 깨진다. 이 파일은 `.get()` 으로만 만진다.
"""

# 규칙 기호 정렬 순서. `sorted()` 가 유니코드 코드포인트 순서(①U+2460 … ⑥U+2465)로
# 이미 ①②③④⑤⑥ 을 만들어 주지만, 의도를 코드에 남겨 둔다.
RULE_ORDER = "①②③④⑤⑥"

# 상품 줄에서 **소재끼리 더하는** 지표. 소재 단위 중복은 1단계 dedupe 에서 이미 없앴다.
# `ctr` 은 여기 없다 — 비율을 더하면 거짓말이 된다(0.23 + 0.23 = 0.46).
# `rank` 도 없다 — 평균 순위는 노출 가중 없이 못 합치고, 보드가 쓰지 않는다.
SUM_FIELDS = ("imp", "clk", "purCnt", "purAmt", "cost")


def _rule_key(name: str) -> tuple:
    """규칙 키를 `①②③④⑤⑥` 순서로 정렬하기 위한 정렬키."""
    head = name[:1]
    return (RULE_ORDER.index(head) if head in RULE_ORDER else len(RULE_ORDER), name)


def account_list(result: dict) -> list[str]:
    """계정 alias 목록 — `result.json` 에서만 온다 (BOARD-02).

    설정에 계정을 더하면 다음 회차의 `result.json` 에 그 계정이 생기고, 화면은
    아무것도 안 고쳐도 따라온다. 반대로 여기에 alias 를 박으면 계정을 늘린 사람이
    "왜 화면에 안 나오지" 를 코드에서 찾아야 한다.
    """
    if not isinstance(result, dict):
        return []
    return sorted((result.get("accounts") or {}).keys())


def rule_list(result: dict) -> list[str]:
    """**행이 실제로 하나라도 있는** 규칙 키를 `①②③④⑤⑥` 순서로.

    비어 있는 규칙을 필터 옵션에 넣으면 고르는 순간 항상 빈 표가 된다 —
    사용자는 그걸 "보드가 고장났다" 로 읽는다.
    """
    if not isinstance(result, dict):
        return []
    있는것 = set()
    for v in (result.get("accounts") or {}).values():
        for rule, rows in ((v or {}).get("rules") or {}).items():
            if rows:
                있는것.add(rule)
    return sorted(있는것, key=_rule_key)


def _dedupe_ads(account: dict) -> dict:
    """1단계 — 한 계정 안에서 소재(adId)를 먼저 합친다.

    `report_md.py:59` 의 경고를 그대로 옮긴다:
    **"규칙별 행을 합산하지 않는다 — 같은 소재가 ②와 ③에 동시에 들어가 두 번 세진다"**

    실제로 그렇다. ②썸네일교체와 ③원인분석은 서로 배타적이지 않아서 같은 `adId` 가
    양쪽에 같은 지표를 달고 들어온다. 규칙을 순회하며 더하면 노출·클릭·광고비가
    정확히 2배가 되고, 보드의 모든 숫자가 조용히 틀린다.

    그래서 규칙 기호만 set 에 모으고, 지표 필드는 **처음 본 값을 유지**한다
    (같은 소재의 지표는 어느 규칙에서 읽어도 같은 값이다).
    """
    ads: dict[str, dict] = {}
    for rule, rows in ((account or {}).get("rules") or {}).items():
        기호 = rule[:1]
        for r in rows or []:
            adId = r.get("adId")
            slot = ads.get(adId)
            if slot is None:
                # 처음 본 소재 — 행을 그대로 보관한다(지표 필드가 있으면 있는 대로)
                slot = ads[adId] = {"row": dict(r), "rules": set()}
            else:
                # 이미 본 소재 — 지표는 **더하지 않는다**. 다만 이 규칙 행에만 있는
                # 필드(예: ⑤의 purCnt/purAmt)는 채워 넣는다. 덮어쓰지는 않는다.
                for k, v in r.items():
                    slot["row"].setdefault(k, v)
            slot["rules"].add(기호)
    return ads


def fold_products(result: dict) -> list[dict]:
    """소재 행을 `(계정 alias, mallProductId)` 로 접는다. 보드 한 줄 = 상품 1개 (D-05).

    접기 키에 **계정을 반드시 포함**한다. `mallProductId` 는 스마트스토어 상품ID라
    계정 간 중복 가능성을 배제할 수 없고(RESEARCH Assumption A1), 뭉개지면 두 계정의
    실적이 한 줄에 섞인다. 계정을 넣어 두면 어느 쪽이든 안전하다.

    2단계 구조다:
      1. 계정 안에서 `adId` dedupe (`_dedupe_ads`) — 규칙 중복 계상 제거
      2. dedupe 된 소재를 상품으로 접고 지표를 **소재끼리만** 합산

    `bid`·`useGroupBid`·`groupBid` 는 **읽기만** 한다. `ads_rules.effective_bid` 가
    이미 "useGroupBidAmt=True 면 adAttr.bidAmt 는 잠자는 값이고 그룹 기본가가 적용된다 —
    헷갈리면 올리려다 내린다" 를 해석해 `bid` 에 담아 놨다. 실데이터 ①행의 92%가
    `useGroupBid=true` 라, 웹앱이 다시 계산하면 거의 전량이 틀린다
    (실측: 잠자던 값 50 vs 실제 적용 70). 위협 T-1-07.
    """
    if not isinstance(result, dict):
        return []

    prod: dict[tuple, dict] = {}
    for alias, account in (result.get("accounts") or {}).items():
        for adId, slot in _dedupe_ads(account).items():
            r = slot["row"]
            key = (alias, r.get("mallProductId"))
            p = prod.get(key)
            if p is None:
                p = prod[key] = {
                    "acct": alias,
                    "mallProductId": r.get("mallProductId"),
                    "title": r.get("title") or "",
                    "_rules": set(),
                    "rule1_ads": [],          # ← 버튼이 적용될 소재 (D-06)
                    "bid": None, "useGroupBid": None, "groupBid": None,
                    "_bid_from_rule1": False,
                    "imp": None, "clk": None, "ctr": None,
                    "purCnt": None, "purAmt": None, "cost": None,
                }
            p["_rules"] |= slot["rules"]
            if not p["title"]:
                p["title"] = r.get("title") or ""

            if "①" in slot["rules"]:
                p["rule1_ads"].append(adId)

            # 대표 입찰가: **그 상품의 ① 소재 중 첫 번째 것**을 쓴다. ① 소재가 없는
            # 상품(②③⑤만 있는 줄)은 화면에 현재가를 아예 안 띄우면 불친절하므로
            # 처음 본 소재 값으로 채우되, ① 이 나타나면 그쪽으로 한 번 덮는다.
            # 어느 경우든 **읽어 온 값 그대로**다 — 산술은 없다.
            첫_규칙1 = "①" in slot["rules"] and not p["_bid_from_rule1"]
            if 첫_규칙1 or p["bid"] is None and p["useGroupBid"] is None:
                p["bid"] = r.get("bid")
                p["useGroupBid"] = r.get("useGroupBid")
                p["groupBid"] = r.get("groupBid")
                if 첫_규칙1:
                    p["_bid_from_rule1"] = True

            # ①·⑥ 행에는 이 키들이 **아예 없다**. `.get()` 으로만 만진다.
            for f in SUM_FIELDS:
                v = r.get(f)
                if v is not None:
                    p[f] = (p[f] or 0) + v

    out = []
    for p in prod.values():
        p["rules"] = "".join(sorted(p.pop("_rules")))
        p["rule1_count"] = len(p["rule1_ads"])   # "이 버튼이 N건에 적용됩니다"
        p.pop("_bid_from_rule1", None)
        # CTR 은 합산하지 않고 **다시 낸다**. 노출이 없으면 비율도 없다(0 이 아니라 None) —
        # 0.00% 로 찍으면 "클릭이 0 이었다" 는 판정처럼 보이는데, 실제로는 분모가 없다.
        p["ctr"] = round(p["clk"] / p["imp"] * 100, 2) if p["imp"] else None
        out.append(p)
    return out
