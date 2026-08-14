#!/usr/bin/env python3
"""경동택배 표준운임표 → `references/경동-표준운임.json` 의 구간 채우기.

  python fetch_kd_table.py [--url ...] [--out ...] [--dry-run]

**`택배` 열만** 담는다(기준 문서 §4-2 — 정기화물 열은 이룸님 기준에서 쓰지 않는다).
지역인상율(7×7)은 손으로 넣은 값이라 **덮어쓰지 않고 보존**한다.

이 스크립트는 배송비 스킬의 평시 흐름이 아니다 — 고시표가 바뀌었을 때만 돌린다.
"""
import argparse
import html as _html
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import requests

URL = "https://kdexp.com/service/charge/package_standard.do"
OUT = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "references", "경동-표준운임.json"))

_TAG = re.compile(r"<[^>]+>")
_NUM = re.compile(r"[\d,]+")

# 구간 행의 첫 칸은 정확히 이 모양이다: `20,000㎤ 이하` / `20,000㎤ 초과 ~ 30,000㎤ 이하`.
# 이 형태로 **한정하지 않으면** 페이지 상단의 계산 예시 행(`… 64,000㎤ x 25% = 6,900 …
# 60kg x 25% = 18,800`)이 구간으로 잡혀 표 맨 앞에 `[18,800 → 40원]` 같은 유령 구간이
# 생긴다. 그 한 줄이 모든 소형 화물의 운임을 40원으로 만든다.
_RANGE = re.compile(
    r"^\s*(?:[\d,]+\s*(?P<u1>㎤|kg)\s*초과\s*~\s*)?[\d,]+\s*(?P<u2>㎤|kg)\s*이하\s*$",
    re.I)


def _cells(row_html):
    """<tr> 안의 <td>/<th> 텍스트 목록.

    **엔티티를 반드시 푼다** — 이 페이지는 ㎤ 를 `&#13220;` 로 쓴다. 안 풀면 부피 행이
    단위를 잃고 무게 행만 잡혀 표의 절반이 조용히 사라진다(초판에서 실제로 그랬다).
    """
    out = []
    for m in re.finditer(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.S | re.I):
        txt = _html.unescape(_TAG.sub(" ", m.group(1)))
        out.append(txt.replace("\xa0", " ").strip())
    return out


def _int(s):
    m = _NUM.search(s or "")
    return int(m.group(0).replace(",", "")) if m else None


def _upper(head):
    """구간 문자열 → **상한**. `20,000㎤ 초과 ~ 30,000㎤ 이하` 는 30,000 이다.

    앞 숫자를 집으면 구간이 통째로 한 칸씩 밀린다(60kg 이 4,000kg 요금을 받는다).
    """
    nums = _NUM.findall(head or "")
    return int(nums[-1].replace(",", "")) if nums else None


def parse(html):
    """HTML → (부피구간, 무게구간). 각각 [[상한, 택배운임], ...] 오름차순.

    행 형태는 `<기준값> 이하 | 택배 | 정기화물` 이다. 기준이 ㎤ 인지 kg 인지는
    **행의 단위 표기**로 가른다 — 표가 둘로 나뉜 순서에 기대면 페이지 개편에 바로 깨진다.
    """
    vol, wt = [], []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
        cs = _cells(row)
        if len(cs) < 2:
            continue
        m = _RANGE.match(cs[0])
        if not m:
            continue   # 헤더·설명·예시 행
        head = cs[0]
        is_vol = (m.group("u2") == "㎤")
        upper = _upper(head)
        # 택배 = 기준값 바로 다음 열. 정기화물은 그 다음이라 쓰지 않는다.
        fare = _int(cs[1]) if len(cs) > 1 else None
        if upper is None or fare is None:
            continue
        (vol if is_vol else wt).append([upper, fare])

    def dedup(rows):
        seen, out = set(), []
        for u, f in sorted(rows):
            if u not in seen:
                seen.add(u)
                out.append([u, f])
        return out

    return dedup(vol), dedup(wt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=URL)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    r = requests.get(args.url, timeout=30,
                     headers={"User-Agent": "Mozilla/5.0 (eroom-studio shipfee)"})
    r.encoding = r.apparent_encoding or "utf-8"
    vol, wt = parse(r.text)
    print(f"부피구간 {len(vol)}개 · 무게구간 {len(wt)}개")
    for label, rows in (("부피", vol), ("무게", wt)):
        if rows:
            print(f"  {label}: 첫 {rows[0]} · 끝 {rows[-1]}")
    if not vol or not wt:
        print("[실패] 구간을 못 뽑았다 — 페이지 구조가 바뀌었을 수 있다. "
              "--dry-run 으로 원문을 확인할 것", file=sys.stderr)
        return 2
    if args.dry_run:
        return 0

    # 기존 파일의 지역인상율·설명은 보존한다(손으로 넣은 값이다).
    doc = {}
    if os.path.exists(args.out):
        with open(args.out, encoding="utf-8") as f:
            doc = json.load(f)
    doc["부피구간"] = vol
    doc["무게구간"] = wt
    doc["_출처"] = args.url
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print(f"기록: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
