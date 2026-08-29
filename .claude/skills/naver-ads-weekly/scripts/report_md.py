#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""주간 총괄 보고서(마크다운).

보고서에는 구매완료 기준 숫자만 싣는다(2026-08-28 용팀장).
총전환·장바구니는 착시라 나란히 놓으면 헷갈리기만 한다.
"""

TOP_N = 20   # ② 는 주당 이만큼만 처리한다


def _table(rows, cols, limit=None):
    """(헤더, 접근키) 목록으로 마크다운 표를 만든다."""
    rows = rows[:limit] if limit else rows
    if not rows:
        return "_해당 없음_\n"
    head = "| " + " | ".join(h for h, _ in cols) + " |\n"
    sep = "|" + "|".join("---" for _ in cols) + "|\n"
    body = ""
    for r in rows:
        cells = []
        for _, k in cols:
            v = r.get(k, "")
            # bool 을 int 보다 먼저 본다 — 파이썬에서 bool 은 int 의 하위 타입이라
            # 순서를 바꾸면 True/False 가 1/0 으로 찍혀 사람이 못 읽는다
            if isinstance(v, bool):
                cells.append("예" if v else "아니오")
            elif isinstance(v, int):
                cells.append(f"{v:,}")
            elif isinstance(v, float):
                cells.append(f"{v:.2f}")
            else:
                cells.append(str(v))
        body += "| " + " | ".join(cells) + " |\n"
    return head + sep + body


def _count_label(n, limit):
    """헤더에 쓸 건수 표기. 표가 잘렸으면 잘렸다고 반드시 말한다."""
    return f"{n}건 중 상위 {limit}건" if limit and n > limit else f"{n}건"


def build_report(result, top_n=TOP_N):
    """result.json 을 사람이 읽는 보고서로 바꾼다."""
    lines = [f"# 네이버 광고 주간 보고 — {result.get('generated','')}\n"]

    # 계정 총괄 — 구매완료 기준만
    lines.append("## 총괄\n")
    lines.append("| 계정 | 게재중 | 광고비 | 구매완료 매출 | ROAS | 노출0 | 썸네일교체 | 구매0 | 효자 |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    tot_cost = tot_pur = 0
    for alias, v in result.get("accounts", {}).items():
        r = v["rules"]
        # 규칙별 행을 합산하지 않는다 — 같은 소재가 ②와 ③에 동시에 들어가 두 번 세진다
        s = v.get("summary") or {}
        cost = s.get("cost", 0)
        pur = s.get("purAmt", 0)
        tot_cost += cost
        tot_pur += pur
        roas = f"{pur / cost * 100:.0f}%" if cost else "—"
        lines.append(f"| {alias} | {s.get('live', 0)} | {cost:,}원 | {pur:,}원 | {roas} | "
                     f"{len(r['①노출0'])} | {len(r['②썸네일교체'])} | {len(r['③원인분석'])} | {len(r['⑤효자확정'])} |")
    roas_all = f"{tot_pur / tot_cost * 100:.0f}%" if tot_cost else "—"
    lines.append(f"| **합계** | | **{tot_cost:,}원** | **{tot_pur:,}원** | **{roas_all}** | | | | |\n")
    # 주의: 여기서 금칙어 자체를 언급하면 안 된다 — Step 4 grep 이 이 문장까지 잡아낸다
    lines.append("> 매출은 **구매완료 기준**이다. 결제 완료 이전 단계는 세지 않는다.\n")

    for alias, v in result.get("accounts", {}).items():
        r = v["rules"]
        lines.append(f"\n## {alias}\n")

        lines.append(f"### ① 노출 0 — 입찰 인상 대상 {len(r['①노출0'])}건\n")
        lines.append("`bids --commit` 으로 실행한다. 그룹입찰 상품은 개별 전환 후 `그룹기본가+10원`으로 시작한다.\n")
        lines.append(_table(r["①노출0"], [("상품", "title"), ("광고그룹", "adGroup"),
                                          ("현재입찰", "bid"), ("그룹입찰따름", "useGroupBid")]))

        lines.append(f"\n### ② 썸네일 교체 — {_count_label(len(r['②썸네일교체']), top_n)}\n")
        lines.append("노출 100회 이상인데 CTR 1% 미만. 노출 많은 순.\n")
        lines.append(_table(r["②썸네일교체"], [("상품", "title"), ("노출", "imp"), ("클릭", "clk"),
                                              ("CTR %", "ctr"), ("순위", "rank"), ("상품ID", "mallProductId")],
                            limit=top_n))

        lines.append(f"\n### ③ 클릭 20+ 인데 구매완료 0 — {len(r['③원인분석'])}건\n")
        lines.append(_table(r["③원인분석"], [("상품", "title"), ("클릭", "clk"), ("CTR %", "ctr"),
                                            ("광고비", "cost")]))

        lines.append(f"\n### ④ CTR 2% 이상 — 효자 후보 {_count_label(len(r['④효자후보']), top_n)}\n")
        lines.append(_table(r["④효자후보"], [("상품", "title"), ("노출", "imp"), ("CTR %", "ctr"),
                                            ("순위", "rank")], limit=top_n))

        lines.append(f"\n### ⑤ 구매완료 발생 — 효자 확정 {len(r['⑤효자확정'])}건\n")
        lines.append(_table(r["⑤효자확정"], [("상품", "title"), ("구매", "purCnt"), ("매출", "purAmt"),
                                            ("광고비", "cost")]))

        off = len(r["⑥삭제대상"])
        lines.append(f"\n### ⑥ 꺼진 소재 — {off}건\n")
        if off:
            lines.append(f"`prune --commit` 으로 삭제한다(백업 선행). "
                         f"**꺼진 사유가 `AD_ABNORMAL_INTERLOCK`(연동 비정상)이면 원인 규명이 먼저다** — "
                         f"매주 삭제만 하면 광고 소재가 줄어들기만 한다.\n")
        else:
            lines.append("_해당 없음_\n")

    return "\n".join(lines)
