#!/usr/bin/env python3
"""오픈차이나 **실측 배송비**를 긁어 요율 교정용 데이터셋을 만든다. 읽기 전용.

  python fetch_oc_actuals.py [--pages 6] [--limit 60] [--out <json>]

주문내역 목록에는 `5,500원(1.00 KG)` 처럼 **측정무게**가 찍혀 있고, 그 금액을 클릭하면
열리는 결제금액 모달에 **항목별 내역**이 있다:

    실무게 : 3kg, 측정무게 : 3kg · 부피무게 : 0kg ( 0 * 0 * 0 cm)
    - 배송비 8,500 · 기본검수 0 · 외부포장(실비) 2,500 · 한진택배 할증료 600  →  합계 11,600

**`배송비` 항목만이 무게 요율이다.** 나머지(외부포장·할증·돼지코 등)는 실비라 무게로
예측할 수 없다 — 그래서 엑셀 다운로드(`bdz-openchina-order-excel`)의 `배송비` 열로는
요율을 못 잡는다. 그 열은 합계이기 때문이다(2026-08-12 이 혼동으로 한 바퀴 돌았다).

로그인은 `bdz-openchina-order-excel` 스킬의 `download_orders.py` 를 그대로 재사용한다
(.env 의 OPENCHINA_ID/PW). 이 스크립트는 아무것도 쓰지 않는다.
"""
import argparse
import html as _html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_d = SCRIPT_DIR
while _d and _d != os.path.dirname(_d):
    _sk = os.path.join(_d, "skills", "bdz-openchina-order-excel", "scripts")
    if os.path.isdir(_sk):
        sys.path.insert(0, _sk)
        break
    _d = os.path.dirname(_d)

import download_orders as D  # noqa: E402

LIST_URL = D.BASE + "/Front/Member/MyPage.asp?gMnu1=206&gMnu2=20601"
DETAIL_URL = D.BASE + "/Admin/Acting/OrdCha_A.asp?sOrdSeq="
TAG = re.compile(r"<[^>]+>")

# 목록의 금액 링크 = 결제금액 모달 rel + 주문번호(ordTit) + `금액원(무게 KG)`
_ROW = re.compile(
    r'rel="/Admin/Acting/OrdCha_A\.asp\?sOrdSeq=(\d+)"[^>]*ordTit="[^"]*?(\d{10})\)"'
    r'.*?([\d,]+)원\((\d+\.\d+)\s*KG\)', re.S | re.I)
# 상품명은 금액 셀보다 **앞**에 있어 위 정규식으로는 못 잡는다. 행 단위로 따로 찾는다.
# 이게 있어야 "이 물건이 실제로 몇 kg 이었나"를 워커 교정에 쓸 수 있다(2026-08-13).
_PRONAME = re.compile(r'class="proNameArea"[^>]*>(.*?)</span>', re.S | re.I)


def _text(body):
    return [ln.strip() for ln in _html.unescape(TAG.sub("\n", body)).split("\n") if ln.strip()]


def _won(s):
    m = re.search(r"([\d,]+)\s*원", s or "")
    return int(m.group(1).replace(",", "")) if m else None


def parse_detail(body):
    """결제금액 모달 → {실무게, 측정무게, 부피무게, 부피, 합계, 항목:{이름: 금액}}."""
    lines = _text(body)
    out = {"항목": {}}
    joined = " ".join(lines)
    m = re.search(r"실무게\s*:\s*([\d.]+)\s*kg\s*,\s*측정무게\s*:\s*([\d.]+)\s*kg", joined, re.I)
    if m:
        out["실무게"] = float(m.group(1))
        out["측정무게"] = float(m.group(2))
    m = re.search(r"부피무게\s*:\s*([\d.]+)\s*kg\s*\(\s*([\d.]+)\s*\*\s*([\d.]+)\s*\*\s*([\d.]+)\s*cm",
                  joined, re.I)
    if m:
        out["부피무게"] = float(m.group(1))
        dims = [float(m.group(i)) for i in (2, 3, 4)]
        out["부피"] = dims if all(d > 0 for d in dims) else None
    # 항목 = `- 이름` 다음 줄의 `N 원`. 합계는 항목 앞에 단독으로 나오는 첫 금액.
    for i, ln in enumerate(lines):
        if ln.startswith("-") and i + 1 < len(lines):
            name = ln.lstrip("- ").strip()
            v = _won(lines[i + 1])
            if v is not None and name:
                out["항목"][name] = v
    for ln in lines:
        v = _won(ln)
        if v is not None and not ln.startswith("-"):
            out.setdefault("합계", v)
    return out


def collect(op, pages, limit, sleep):
    """목록 페이지를 돌며 (ordSeq, 주문번호, 합계, 측정무게) 수집."""
    seen, rows = set(), []
    for page in range(1, pages + 1):
        form = {"shTabTy": "1", "shGo": str(page), "shStatSeq": "0",
                "shPageSize": "100", "SearchYn": "Y"}
        req = urllib.request.Request(
            LIST_URL, urllib.parse.urlencode(form).encode(),
            headers={"Referer": LIST_URL})
        body = op.open(req, timeout=40).read().decode("utf-8", "replace")
        found = 0
        # 행(<tr>) 단위로 끊어야 상품명과 금액을 **같은 주문**끼리 묶을 수 있다.
        for block in re.split(r"<tr[^>]*>", body, flags=re.I):
            m = _ROW.search(block)
            if not m or m.group(1) in seen:
                continue
            seen.add(m.group(1))
            nm = _PRONAME.search(block)
            name = _html.unescape(TAG.sub(" ", nm.group(1))).strip() if nm else ""
            rows.append((m.group(1), m.group(2), int(m.group(3).replace(",", "")),
                         float(m.group(4)), name))
            found += 1
        print(f"  page {page}: +{found}건 (누적 {len(rows)})", flush=True)
        if not found or len(rows) >= limit:
            break
        time.sleep(sleep)
    return rows[:limit]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=8)
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--sleep", type=float, default=0.4)
    ap.add_argument("--out", default=os.path.join(
        SCRIPT_DIR, "..", "references", "오픈차이나-실측.json"))
    args = ap.parse_args()

    creds = D.load_env(D.find_env(os.getcwd()))
    op = D.build_opener()
    D.login(op, creds["OPENCHINA_ID"], creds["OPENCHINA_PW"])
    print("로그인 OK")

    rows = collect(op, args.pages, args.limit, args.sleep)
    print(f"목록에서 무게가 찍힌 주문 {len(rows)}건")

    out = []
    for i, (seq, ordno, total, kg, name) in enumerate(rows, 1):
        try:
            body = op.open(DETAIL_URL + seq, timeout=30).read().decode("utf-8", "replace")
            d = parse_detail(body)
        except Exception as e:  # noqa: BLE001
            print(f"  [경고] {ordno} 상세 실패: {str(e)[:60]}", file=sys.stderr)
            continue
        d.update({"주문번호": ordno, "상품명": name, "목록합계": total, "목록무게": kg})
        out.append(d)
        if i % 10 == 0:
            print(f"  ...{i}/{len(rows)}", flush=True)
        time.sleep(args.sleep)

    path = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n기록 {len(out)}건 → {path}")

    # 요약 — `배송비` 항목만 뽑아 무게별로 세운다(이게 요율의 정본이다)
    pure = [(r.get("측정무게"), r["항목"].get("배송비"))
            for r in out if r.get("측정무게") and r["항목"].get("배송비")]
    pure = sorted(set(pure))
    print(f"\n(측정무게, 순수 배송비) {len(pure)}쌍")
    for kg, fee in pure:
        print(f"  {kg:>6}kg  {fee:>8,}원")
    extras = {}
    for r in out:
        for k, v in r["항목"].items():
            if k != "배송비" and v:
                extras.setdefault(k, []).append(v)
    print("\n부대비용 항목(무게로 예측 불가 — 배송비에 넣지 않는다)")
    for k, vs in sorted(extras.items(), key=lambda x: -len(x[1])):
        print(f"  {k:<22} {len(vs):>3}건 · 중앙 {sorted(vs)[len(vs)//2]:,}원 · 최대 {max(vs):,}원")

    # 품목별 실측무게 — 워커의 무게 추정을 교정하는 유일한 실물 근거다.
    named = sorted(((r.get("실무게"), r.get("상품명") or "") for r in out
                    if r.get("실무게") and r.get("상품명")), reverse=True)
    print(f"\n(실무게, 상품명) {len(named)}건 — 무거운 순")
    for kg, nm in named:
        print(f"  {kg:>6}kg  {nm[:52]}")


if __name__ == "__main__":
    import urllib.request  # noqa: F401  (collect 에서 사용)
    main()
