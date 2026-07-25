#!/usr/bin/env python3
"""키워드→상품명 파이프라인 공용 로직 모음.

keyword-filter.py 등 여러 스크립트가 공유하는 상수/함수를 이 모듈에 둔다.
(keyword-filter.py는 파일명에 하이픈이 있어 다른 스크립트가 import할 수 없으므로,
 하이픈 없는 이 모듈로 공용 로직을 분리했다.)
"""

import os
import re
import sys
from collections import Counter
from datetime import date

try:
    import openpyxl
except ImportError:
    print("ERROR: openpyxl not installed. Run: pip install openpyxl>=3.1.0", file=sys.stderr)
    sys.exit(1)

# 텍스트 정규화(_nows/sanitize_part)는 eroomlib.textnorm 1벌을 재수출한다.
# `.claude` 앵커(= lib/eroomlib)를 찾아 lib 를 1회 insert.
_d = os.path.dirname(os.path.abspath(__file__))
while _d and _d != os.path.dirname(_d):
    _lib = os.path.join(_d, "lib")
    if os.path.isdir(os.path.join(_lib, "eroomlib")):
        if _lib not in sys.path:
            sys.path.insert(0, _lib)
        break
    _d = os.path.dirname(_d)
from eroomlib.textnorm import nows as _nows  # noqa: E402,F401
from eroomlib.textnorm import sanitize_part  # noqa: E402,F401


# 아이템스카우트 헤더(한글) → 내부 키 매핑. 부분일치로 유연하게 잡는다.
# (헤더의 줄바꿈/공백은 매칭 시 무시 — 셀러라이프 헤더가 "네이버\n해외배송비율" 처럼 줄바꿈 포함)
COLUMN_ALIASES = {
    "keyword": ["키워드"],
    "category": ["대표 카테고리", "카테고리"],
    "classification": ["키워드 분류", "분류"],
    "total_search": ["총 검색수", "총검색수", "총 검색량", "총검색량", "최근1개월검색량", "최근 1개월 검색량", "총 검색"],
    "product_count": ["상품수", "상품 수"],
    "competition": ["경쟁강도"],
    # 셀러라이프 rawdata 전용 열 — 아이템스카우트 익스포트엔 없음(→ 빈칸으로 출력)
    "naver_overseas_ship": ["네이버해외배송비율"],
    "coupang_overseas_ship": ["쿠팡해외배송비율"],
    "new_entry": ["신규진입키워드"],
}


def find_header_index(headers):
    """헤더 행에서 각 내부 키의 컬럼 인덱스를 찾는다. 정확일치 우선, 없으면 부분일치.
    공백·줄바꿈은 무시하고 비교한다."""
    norm = [_nows(h) for h in headers]
    idx = {}
    for key, aliases in COLUMN_ALIASES.items():
        found = None
        # 정확 일치 우선 (긴 별칭부터)
        for alias in aliases:
            a = _nows(alias)
            for i, h in enumerate(norm):
                if h == a:
                    found = i
                    break
            if found is not None:
                break
        # 부분 일치 fallback
        if found is None:
            for alias in aliases:
                a = _nows(alias)
                for i, h in enumerate(norm):
                    if a in h:
                        found = i
                        break
                if found is not None:
                    break
        idx[key] = found
    return idx


def to_number(value):
    """'-', 콤마, 공백 섞인 셀을 정수로. 실패 시 None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip().replace(",", "")
    if s in ("", "-"):
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def is_informational(classification):
    """키워드 분류가 '정보성'이면 True."""
    if classification is None:
        return False
    return "정보" in str(classification)


def extract_roots(*texts):
    """상품명·대표키워드에서 매칭용 어근 토큰을 뽑는다. 2글자 이상 토큰만.

    '자동차 전동 자키 받침대' -> {자동차, 전동, 자키, 받침대}
    한국어 복합어 특성상 부분일치로 쓰므로 토큰 원형만 쓴다(과분해하면 오탐).
    """
    roots = set()
    for t in texts:
        if not t:
            continue
        for tok in re.split(r"[\s/,·\-_()\[\]]+", str(t)):
            tok = tok.strip()
            if len(tok) >= 2 and not tok.isdigit():
                roots.add(tok)
    return roots


def representative_category(idx, data):
    """대표 카테고리 컬럼에서 전체 행의 최빈(mode) 경로를 반환. 예: '생활/건강 > 청소용품 > 휴지통 > 다용도휴지통'."""
    ci = idx.get("category")
    if ci is None:
        return None
    paths = []
    for row in data:
        if ci < len(row) and row[ci] is not None and str(row[ci]).strip():
            paths.append(str(row[ci]).strip())
    if not paths:
        return None
    return Counter(paths).most_common(1)[0][0]


def suggested_filename(rep_category):
    """오늘날짜6자리_1차_2차_3차_4차 형식 파일명(확장자 제외)을 만든다."""
    ymd = date.today().strftime("%y%m%d")
    if not rep_category:
        return f"{ymd}_미분류"
    parts = [sanitize_part(p) for p in rep_category.split(">")]
    parts = [p for p in parts if p]
    return "_".join([ymd] + parts)


def load_rows(xlsx_path):
    """xlsx의 첫 시트를 읽어 헤더 인덱스와 데이터 행을 반환."""
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        return {}, []
    # 첫 번째 비어있지 않은 행을 헤더로
    header_row_idx = 0
    for i, r in enumerate(rows):
        if any(c is not None and str(c).strip() for c in r):
            header_row_idx = i
            break
    idx = find_header_index(rows[header_row_idx])
    data = rows[header_row_idx + 1:]
    return idx, data


def build_candidates(idx, data, max_products, exclude_info):
    """상품수 <= max_products 이고 (옵션) 정보성 제외한 후보 목록을 만든다."""
    if idx.get("keyword") is None or idx.get("product_count") is None:
        raise ValueError("필수 컬럼(키워드/상품수)을 찾지 못했습니다. 아이템스카우트 익스포트가 맞는지 확인하세요.")

    candidates = []
    for row in data:
        def cell(key):
            i = idx.get(key)
            return row[i] if (i is not None and i < len(row)) else None

        keyword = cell("keyword")
        if keyword is None or not str(keyword).strip():
            continue

        classification = cell("classification")
        if exclude_info and is_informational(classification):
            continue

        product_count = to_number(cell("product_count"))
        if product_count is None or product_count > max_products:
            continue

        def blank(key):
            """셀러라이프 전용 열 — 열이 없으면(아이템스카우트) None → 빈 문자열."""
            v = cell(key)
            return "" if v is None else v

        candidates.append({
            "키워드": str(keyword).strip(),
            "대표카테고리": (str(cell("category")).strip() if cell("category") is not None else ""),
            "총검색수": to_number(cell("total_search")),
            "상품수": product_count,
            "분류": (str(classification).strip() if classification is not None else ""),
            "경쟁강도": cell("competition"),
            # 셀러라이프 rawdata 전용 (아이템스카우트는 빈칸)
            "네이버해외배송비율": blank("naver_overseas_ship"),
            "쿠팡해외배송비율": blank("coupang_overseas_ship"),
            "신규진입키워드": blank("new_entry"),
        })
    return candidates
