#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""구글시트 원장 기록 — eroomlib.gsheets 의 검증된 헬퍼를 쓴다.

**gws 를 subprocess 로 직접 부르지 않는다.** 이 저장소에는 이미
`eroomlib.gsheets.append_rows`(429 백오프 재시도 7회 포함)와 `ensure_tab`
(탭 자동 생성·헤더 관리)이 있고 다른 스킬 두 개가 쓴다. 직접 부르면 호출
형식을 틀리기 쉽다 — 실제로 params 안에 body 를 넣어 100% 실패한 적이 있다.

탭 구성: ①노출0 / ②썸네일교체 / ③원인분석 / ④효자후보 / ⑤효자확정 (규칙 5개)
회차마다 append 한다 — 덮어쓰면 과거 회차를 잃는다.
"""
import sys
from pathlib import Path

# eroomlib 찾기 — 이 모듈을 단독으로 import 하는 테스트에서도 돌아야 한다
_d = str(Path(__file__).resolve().parent)
while _d and _d != str(Path(_d).parent):
    _lib = str(Path(_d) / "lib")
    if (Path(_lib) / "eroomlib").is_dir():
        if _lib not in sys.path:
            sys.path.insert(0, _lib)
        break
    _d = str(Path(_d).parent)

from eroomlib.gsheets import append_rows, chunk_by_size, ensure_tab  # noqa: E402

# 모든 탭의 앞 두 열은 회차·계정으로 고정한다. 코드가 붙이지 데이터가 정하지 않는다
PREFIX = ("회차", "계정")

# 규칙별 열 정의 (헤더, 접근키) — PREFIX 뒤에 붙는 것들만 적는다
COLS = {
    "①노출0": [("상품", "title"), ("광고그룹", "adGroup"),
               ("현재입찰", "bid"), ("그룹입찰따름", "useGroupBid"), ("소재ID", "adId")],
    "②썸네일교체": [("상품", "title"), ("노출", "imp"), ("클릭", "clk"),
                 ("CTR %", "ctr"), ("순위", "rank"), ("스토어상품ID", "mallProductId"), ("소재ID", "adId")],
    "③원인분석": [("상품", "title"), ("노출", "imp"), ("클릭", "clk"),
                ("CTR %", "ctr"), ("광고비", "cost"), ("스토어상품ID", "mallProductId")],
    "④효자후보": [("상품", "title"), ("노출", "imp"), ("CTR %", "ctr"),
                ("순위", "rank"), ("스토어상품ID", "mallProductId")],
    "⑤효자확정": [("상품", "title"), ("구매수", "purCnt"),
                ("구매매출", "purAmt"), ("광고비", "cost"), ("스토어상품ID", "mallProductId")],
}


def header_for(rule_name):
    """탭 헤더 = PREFIX + 규칙별 열 이름."""
    return list(PREFIX) + [h for h, _ in COLS.get(rule_name, [])]


def rows_for(rule_name, rows, alias, generated):
    """규칙 1개를 시트 행 목록으로 바꾼다. 회차·계정을 앞에 고정으로 붙인다.

    앞 두 값을 '지금까지 채운 게 없으면 회차' 식으로 판단하지 않는다 —
    그렇게 하면 COLS 순서를 한 번만 바꿔도 회차가 사라지고 계정이 중복되는데,
    append 전용 시트라 실패하지 않고 틀린 행이 조용히 쌓인다.
    """
    cols = COLS.get(rule_name)
    if not cols:
        return []
    out = []
    for r in rows:
        line = [generated, alias]
        for _, key in cols:
            v = r.get(key, "")
            line.append("" if v is None else v)
        out.append(line)
    return out


def write_sheet(sheet_id, result, log=print):
    """전 계정·전 규칙을 각 탭에 append 한다.

    탭이 없으면 ensure_tab 이 헤더와 함께 만든다 — 사람이 미리 만들어 둘 필요가 없다.
    한 규칙이 실패해도 나머지는 계속 간다. 매주 도는 배치라 한 탭의 실패가
    그 회차 전체를 날리면 안 된다.
    """
    generated = result.get("generated", "")
    for rule_name in COLS:
        all_rows = []
        for alias, v in result.get("accounts", {}).items():
            rules = v.get("rules") or {}
            all_rows.extend(rows_for(rule_name, rules.get(rule_name, []), alias, generated))
        if not all_rows:
            continue
        try:
            ensure_tab(sheet_id, rule_name, header_for(rule_name))
            sent = 0
            # 요청 크기 상한은 라이브러리가 아는 값으로 나눈다.
            # chunk_by_size 는 (시작 인덱스, 행들) 순서쌍을 내준다 — 두 번째 값만 쓴다
            # (튜플째로 append_rows 에 넘기면 행 수·바디 모양이 조용히 틀어진다).
            for _, batch in chunk_by_size(all_rows):
                sent += append_rows(sheet_id, rule_name, batch)
            log(f"  {rule_name:<12} {sent:>5}행 기록 OK")
        except Exception as e:
            log(f"  {rule_name:<12} ✗ {type(e).__name__}: {str(e)[:200]}")
