# -*- coding: utf-8 -*-
"""
원천세 신고 자동화 엔진
- 급여 지급 엑셀을 읽어 3.3% 원천세(소득세 3% + 지방소득세 0.3%) 신고에 필요한
  화면별 입력값과 근거자료를 생성한다.
- 실제 홈택스/위택스 제출은 하지 않음. "입력값 + 검산 + 근거 문서"만 만든다.

사용법:
    python generate_filing.py "<급여엑셀.xlsx>" [--base "<근거자료 루트폴더>"]

출력:
    - stdout : JSON 요약 (스킬이 읽어서 가이드 진행에 사용)
    - 파일   : {base}\\지급명세서\\{N}월지급분\\ 에 신고진행시트.md + 근거_원천세신고.html 저장
"""

import sys
import os
import json
import math
import argparse
from datetime import datetime

# Windows 콘솔 기본 인코딩(cp949)에서 이모지/한글 출력 깨짐 방지
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# 노션 문서 기준 근거자료 루트 (원천세신고관련 폴더)
DEFAULT_BASE = r"C:\Users\woori\OneDrive\바탕 화면\최용's 폴더\구매대행\근로사업소득원천세신고\원천세신고관련"

# 엑셀 헤더 → 표준 키 매핑 (헤더 표기가 조금 달라도 잡히도록 부분일치 사용)
HEADER_ALIASES = {
    "귀속": "accrual",       # 귀속월 (일한 달)
    "지급": "paid",          # 지급월일 (지급한 날)
    "이름": "name",
    "주민": "rrn",           # 주민번호
    "총액": "gross",         # 총지급액(세전)
    "소득세": "income_tax",  # 소득세 3%
    "지방": "local_tax",     # 지방소득세 0.3%
    "실": "net",             # 실 지급액
    "은행": "bank",
    "계좌": "account",
}


def won_floor(value, unit=1):
    """원단위 절사(버림). unit=10 이면 10원 미만 절사."""
    return int(math.floor(value / unit) * unit)


def to_ym(v):
    """엑셀 셀(datetime/문자열)을 'YYYY-MM' 으로 변환."""
    if isinstance(v, datetime):
        return v.strftime("%Y-%m")
    if v is None:
        return None
    s = str(v)
    return s[:7] if len(s) >= 7 else s


def next_month_10th(ym):
    """지급연월(YYYY-MM) 기준 신고·납부 기한(다음달 10일) 계산."""
    try:
        y, m = int(ym[:4]), int(ym[5:7])
        y2, m2 = (y + 1, 1) if m == 12 else (y, m + 1)
        return f"{y2:04d}-{m2:02d}-10"
    except Exception:
        return None


def parse_excel(path):
    """엑셀에서 인별 지급내역을 파싱한다."""
    try:
        import openpyxl
    except ImportError:
        raise SystemExit("openpyxl 미설치. `pip install openpyxl` 후 다시 실행하세요.")

    try:
        wb = openpyxl.load_workbook(path, data_only=True)
    except Exception as e:
        raise SystemExit(f"엑셀을 열 수 없습니다: {e}")

    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise SystemExit("엑셀이 비어 있습니다.")

    # 1) 헤더 행 찾기 (이름 + 총액 컬럼이 모두 있는 행)
    header_idx, colmap = None, {}
    for i, r in enumerate(rows):
        labels = [str(c).strip() if c is not None else "" for c in r]
        tmp = {}
        for ci, lab in enumerate(labels):
            for alias, key in HEADER_ALIASES.items():
                if alias in lab and key not in tmp:
                    tmp[key] = ci
        if "name" in tmp and "gross" in tmp:
            header_idx, colmap = i, tmp
            break
    if header_idx is None:
        raise SystemExit("헤더(이름/총액)를 찾지 못했습니다. 엑셀 양식을 확인하세요.")

    def cell(r, key):
        ci = colmap.get(key)
        return r[ci] if ci is not None and ci < len(r) else None

    # 2) 인별 데이터 행 수집 (이름이 있고 '합계'가 아닌 행)
    people = []
    for r in rows[header_idx + 1:]:
        name = cell(r, "name")
        if name is None:
            continue
        name = str(name).strip()
        if not name or "합" in name and "계" in name:
            continue
        gross = cell(r, "gross")
        if gross is None:
            continue
        try:
            gross = int(round(float(gross)))
        except (TypeError, ValueError):
            continue

        def as_int(key):
            v = cell(r, key)
            try:
                return int(round(float(v)))
            except (TypeError, ValueError):
                return None

        people.append({
            "name": name,
            "rrn": str(cell(r, "rrn") or "").strip(),
            "gross": gross,
            "income_tax": as_int("income_tax"),
            "local_tax": as_int("local_tax"),
            "net": as_int("net"),
            "accrual": to_ym(cell(r, "accrual")),
            "paid": to_ym(cell(r, "paid")),
            "bank": str(cell(r, "bank") or "").strip(),
            "account": str(cell(r, "account") or "").strip(),
        })

    if not people:
        raise SystemExit("인별 지급내역(이름+총액)을 찾지 못했습니다.")
    return people


def validate(people):
    """각 인별로 표준 절사 규칙과 엑셀 값을 대조. 불일치는 flag로 남김."""
    flags = []
    for p in people:
        exp_income = won_floor(p["gross"] * 0.03, 10)       # 소득세 3%, 원천징수세액 10원 미만 절사
        exp_local = won_floor(p["gross"] * 0.003, 10)       # 지방세 0.3%, 10원 미만 절사
        p["expected_income_tax"] = exp_income
        p["expected_local_tax"] = exp_local
        if p["income_tax"] is None:
            p["income_tax"] = exp_income
        elif p["income_tax"] != exp_income:
            flags.append(f"⚠️ {p['name']} 소득세 엑셀={p['income_tax']:,} / 계산={exp_income:,} 불일치")
        if p["local_tax"] is None:
            p["local_tax"] = exp_local
        elif p["local_tax"] != exp_local:
            flags.append(f"⚠️ {p['name']} 지방세 엑셀={p['local_tax']:,} / 계산={exp_local:,} 불일치")
    return flags


def build_summary(people, flags):
    total_gross = sum(p["gross"] for p in people)
    total_income = sum(p["income_tax"] for p in people)
    total_local = sum(p["local_tax"] for p in people)
    # 대표 귀속/지급연월 = 첫 사람 기준 (보통 전원 동일)
    accrual = people[0]["accrual"]
    paid = people[0]["paid"]
    paid_month = int(paid[5:7]) if paid else None
    return {
        "count": len(people),
        "accrual_ym": accrual,
        "paid_ym": paid,
        "paid_month": paid_month,
        "deadline": next_month_10th(paid) if paid else None,
        "total_gross": total_gross,
        "total_income_tax": total_income,
        "total_local_tax": total_local,
        "people": people,
        "flags": flags,
    }


def render_sheet_md(s):
    """화면별 입력값 시트 (마크다운)."""
    L = []
    L.append(f"# 원천세 신고 진행 시트 — {s['paid_ym']} 지급분\n")
    L.append(f"- 귀속연월: **{s['accrual_ym']}** (일한 달)")
    L.append(f"- 지급연월: **{s['paid_ym']}** (지급한 달)")
    L.append(f"- 신고·납부 기한: **{s['deadline']}**")
    L.append(f"- 대상 인원: **{s['count']}명**\n")
    if s["flags"]:
        L.append("## ⚠️ 검산 경고 (확인 필요)")
        for f in s["flags"]:
            L.append(f"- {f}")
        L.append("")
    else:
        L.append("> ✅ 검산 통과 — 3%·0.3% 절사, 인별·합계 일치\n")

    L.append("## ① 홈택스 — 사업소득 원천세 신고")
    L.append(f"- 인원: **{s['count']}명**")
    L.append(f"- 총지급액: **{s['total_gross']:,}원**")
    L.append(f"- 소득세(징수세액): **{s['total_income_tax']:,}원**")
    L.append("- (지방세는 홈택스에서 입력하지 않음 → 위택스에서)\n")

    L.append("## ② 위택스 — 지방소득세 특별징수")
    L.append(f"- 지방소득세: **{s['total_local_tax']:,}원**\n")

    L.append("## ③ 간이지급명세서(사업소득) — 인별")
    L.append("| 이름 | 주민번호 | 귀속연월 | 지급연월 | 지급총액 |")
    L.append("|------|----------|----------|----------|----------|")
    for p in s["people"]:
        L.append(f"| {p['name']} | {p['rrn']} | {p['accrual']} | {p['paid']} | {p['gross']:,} |")
    L.append("")
    return "\n".join(L)


def render_evidence_html(s):
    """근거자료 (인쇄용 HTML). 검산표 + 제출 요약."""
    rows = "\n".join(
        f"<tr><td>{p['name']}</td><td>{p['rrn']}</td>"
        f"<td class='n'>{p['gross']:,}</td><td class='n'>{p['income_tax']:,}</td>"
        f"<td class='n'>{p['local_tax']:,}</td><td class='n'>{(p['net'] or 0):,}</td></tr>"
        for p in s["people"]
    )
    flag_html = ""
    if s["flags"]:
        items = "".join(f"<li>{f}</li>" for f in s["flags"])
        flag_html = f"<div class='warn'><b>검산 경고</b><ul>{items}</ul></div>"
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>원천세 신고 근거 {s['paid_ym']}</title>
<style>
body{{font-family:'Malgun Gothic',sans-serif;margin:32px;color:#111}}
h1{{font-size:20px}} .meta{{color:#444;font-size:13px;line-height:1.7}}
table{{border-collapse:collapse;width:100%;margin-top:16px;font-size:13px}}
th,td{{border:1px solid #999;padding:6px 8px;text-align:left}}
th{{background:#f0f0f0}} td.n{{text-align:right;font-variant-numeric:tabular-nums}}
tfoot td{{font-weight:bold;background:#fafafa}}
.warn{{margin-top:16px;padding:10px 14px;border:1px solid #c00;color:#c00;font-size:13px}}
.foot{{margin-top:24px;color:#666;font-size:12px}}
</style></head><body>
<h1>원천세 신고 근거자료 — {s['paid_ym']} 지급분</h1>
<div class="meta">
귀속연월 {s['accrual_ym']} · 지급연월 {s['paid_ym']} · 신고기한 {s['deadline']} · 대상 {s['count']}명<br>
<b>홈택스 소득세(징수세액) {s['total_income_tax']:,}원</b> · <b>위택스 지방소득세 {s['total_local_tax']:,}원</b>
</div>
{flag_html}
<table>
<thead><tr><th>이름</th><th>주민번호</th><th>총지급액</th><th>소득세 3%</th><th>지방세 0.3%</th><th>실지급액</th></tr></thead>
<tbody>
{rows}
</tbody>
<tfoot><tr><td colspan="2">합계</td>
<td class="n">{s['total_gross']:,}</td><td class="n">{s['total_income_tax']:,}</td>
<td class="n">{s['total_local_tax']:,}</td>
<td class="n">{sum((p['net'] or 0) for p in s['people']):,}</td></tr></tfoot>
</table>
<div class="foot">생성: 원천세 신고 자동화 스킬 · 이 문서는 신고 근거 보관용입니다.</div>
</body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("excel")
    ap.add_argument("--base", default=DEFAULT_BASE)
    args = ap.parse_args()

    if not os.path.exists(args.excel):
        raise SystemExit(f"파일을 찾을 수 없습니다: {args.excel}")

    people = parse_excel(args.excel)
    flags = validate(people)
    s = build_summary(people, flags)

    # 근거자료 폴더 생성: {base}\지급명세서\{N}월지급분
    out_dir = None
    if s["paid_month"]:
        out_dir = os.path.join(args.base, "지급명세서", f"{s['paid_month']}월지급분")
        try:
            os.makedirs(out_dir, exist_ok=True)
            with open(os.path.join(out_dir, f"신고진행시트_{s['paid_ym']}.md"), "w", encoding="utf-8") as f:
                f.write(render_sheet_md(s))
            with open(os.path.join(out_dir, f"근거_원천세신고_{s['paid_ym']}.html"), "w", encoding="utf-8") as f:
                f.write(render_evidence_html(s))
        except Exception as e:
            s["flags"].append(f"⚠️ 근거자료 저장 실패: {e}")
            out_dir = None

    s["out_dir"] = out_dir
    print(json.dumps(s, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
