#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""주간 총괄 보고서(마크다운).

보고서에는 구매완료 기준 숫자만 싣는다(2026-08-28 용팀장).
결제 완료 이전 단계의 전환 수치는 착시라 나란히 놓으면 헷갈리기만 한다.

2026-10-16 ⑦ 체계: 계정별 ②·④ 섹션은 뺐다(⑦b/⑦c 가 전 계정 1풀로 대체). ⑦ 은 계정별 섹션 뒤
합산 섹션 하나로 싣는다.

Important 5: ①③·⑦b 표는 top_n 으로 잘린다 — 실측 ①만 1,195행이라 자르지 않으면
보고서가 298KB 로 불어나 아무도 안 읽는다. 실제 실행 대상 전량은 result.json·시트에
그대로 있다(bids·prune 은 이 보고서가 아니라 result.json 을 읽는다). ⑤는 계정당 20건
미만이라 그대로 둔다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ads_rules  # noqa: E402

TOP_N = 20   # ①③·⑦b 는 주당 이만큼만 표에 싣는다(전량 처리·전량 시트 기록엔 영향 없음)


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
    lines.append("| 계정 | 게재중 | 광고비 | 구매완료 매출 | ROAS | 노출0 | ③구매0 | ⑤효자 |")
    lines.append("|---|---|---|---|---|---|---|---|")
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
                     f"{len(r.get('①노출0', []))} | {len(r.get('③원인분석', []))} | "
                     f"{len(r.get('⑤효자확정', []))} |")
    roas_all = f"{tot_pur / tot_cost * 100:.0f}%" if tot_cost else "—"
    lines.append(f"| **합계** | | **{tot_cost:,}원** | **{tot_pur:,}원** | **{roas_all}** | | | |\n")
    # 주의: 여기서 금칙어 자체를 언급하면 안 된다 — Step 4 grep 이 이 문장까지 잡아낸다
    lines.append("> 매출은 **구매완료 기준**이다. 결제 완료 이전 단계는 세지 않는다.\n")

    for alias, v in result.get("accounts", {}).items():
        r = v["rules"]
        lines.append(f"\n## {alias}\n")

        lines.append(f"### ① 노출 0 (⑦a) — 입찰 인상 대상 {_count_label(len(r['①노출0']), top_n)}\n")
        lines.append("`bids --commit` 으로 실행한다(전량 처리 — 이 표는 상위 미리보기일 뿐이다). "
                     "그룹입찰 상품은 개별 전환 후 `그룹기본가+10원`으로 시작한다.\n")
        lines.append(_table(r["①노출0"], [("상품", "title"), ("광고그룹", "adGroup"),
                                          ("현재입찰", "bid"), ("그룹입찰따름", "useGroupBid")],
                            limit=top_n))

        lines.append(f"\n### ③ 클릭 20+ 인데 구매완료 0 — {_count_label(len(r['③원인분석']), top_n)}\n")
        lines.append(_table(r["③원인분석"], [("상품", "title"), ("클릭", "clk"), ("CTR %", "ctr"),
                                            ("광고비", "cost")], limit=top_n))

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

    lines.extend(_section7(result, top_n))
    return "\n".join(lines)


def _gather(result, key):
    """전 계정의 규칙 행을 acct 를 붙여 한 목록으로."""
    out = []
    for alias, v in (result.get("accounts") or {}).items():
        for row in ((v or {}).get("rules") or {}).get(key, []) or []:
            out.append(dict(row, acct=row.get("acct") or alias))
    return out


def _label(rows):
    """표기용 사본 — 불사자매칭 미조회 표시, 판매자상품코드 빈칸."""
    out = []
    for r in rows:
        x = dict(r)
        x["불사자매칭"] = ads_rules.match_label(r)
        if x.get("판매자상품코드") is None:
            x["판매자상품코드"] = ""
        out.append(x)
    return out


def _section7(result, top_n):
    """⑦ 전 계정 합산 섹션 — ⑦b·⑦c(final_7c)·⑦d(정비판정)."""
    pool = result.get("pool7") or {}
    size = pool.get("size", "?")
    lines = [f"\n## ⑦ 전 계정 합산 (7일 노출 {ads_rules.POP_IMP_MIN}+ 모집단 {size}건)\n"]

    b = sorted(_gather(result, "⑦b썸네일변형"), key=lambda r: (r.get("ctr") or 0.0, -(r.get("imp") or 0)))
    lines.append(f"### ⑦b 썸네일 변형 — CTR 하위 {int(ads_rules.CTR_TAIL_PCT * 100)}% "
                 f"{_count_label(len(b), top_n)}\n")
    lines.append(_table(b, [("상품", "title"), ("계정", "acct"), ("노출", "imp"), ("클릭", "clk"),
                            ("CTR %", "ctr"), ("광고그룹", "adGroup"), ("스토어상품ID", "mallProductId")],
                        limit=top_n))

    c = _label(ads_rules.final_7c(_gather(result, "⑦c상세꾸미기후보")))
    lines.append(f"\n### ⑦c 상세 꾸미기 — CTR 상위 {int(ads_rules.CTR_TAIL_PCT * 100)}% 중 상세 미가공 "
                 f"{len(c)}건\n")
    lines.append(_table(c, [("상품", "title"), ("판매자상품코드", "판매자상품코드"), ("상세상태", "상세상태"),
                            ("CTR %", "ctr"), ("노출", "imp"), ("불사자매칭", "불사자매칭")]))

    d_rows = _gather(result, "⑦d정비점검후보")
    d = _label([dict(r, 정비판정=ads_rules.maintenance_verdict(r)) for r in d_rows])
    counts = {}
    for r in d:
        counts[r["정비판정"]] = counts.get(r["정비판정"], 0) + 1
    todo = [r for r in d if r["정비판정"] != "정비완료"]
    lines.append(f"\n### ⑦d 정비 점검 — 30일 클릭 {ads_rules.MAINT_CLICK_MIN}+ {len(d)}건\n")
    if counts:
        lines.append(" · ".join(f"{k} {v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])) + "\n")
    lines.append(_table(todo, [("상품", "title"), ("판매자상품코드", "판매자상품코드"), ("클릭", "clk"),
                               ("상세상태", "상세상태"), ("옵션상태", "옵션상태"), ("정비판정", "정비판정")]))
    return lines
