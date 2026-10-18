#!/usr/bin/env python3
"""소싱 검수 기계 판정 — 금지 카테고리 번호 + 금지 키워드.

AI 에 보내기 전에 비용 0 으로 확실한 탈락만 걸러낸다.
반환이 None 이면 '기계로는 못 정함' → AI 판정 대상.
"""
import json
import os
import re

RULES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rules")
CATS_PATH = os.path.join(RULES_DIR, "banned_cats.txt")
KWS_PATH = os.path.join(RULES_DIR, "banned_keywords.json")


def load_banned_cats(path=None):
    """금지 카테고리 번호 집합(문자열). 파일 없으면 빈 집합 + 경고."""
    try:
        with open(path or CATS_PATH, encoding="utf-8") as f:
            return {t.strip() for t in f.read().split() if t.strip()}
    except FileNotFoundError:
        print(f"[경고] 금지 카테고리 파일 없음: {path or CATS_PATH}")
        return set()


def load_keywords(path=None):
    """사유코드 → 키워드 목록. '_' 로 시작하는 키는 설명이라 뺀다."""
    try:
        with open(path or KWS_PATH, encoding="utf-8") as f:
            raw = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[경고] 금지 키워드 로드 실패: {e}")
        return {}
    return {k: [_norm(w) for w in v] for k, v in raw.items() if not k.startswith("_")}


def _norm(s):
    return "".join(str(s or "").split()).lower()


# 3000W 이상은 한국 가정 전기(보통 3kW 계약·멀티탭 한계)에서 쓰기 어렵다 (2026-10-18 사용자 지정)
WATT_LIMIT = 3000
_WATT = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kw|w|와트|킬로와트)(?![a-z])", re.I)


def max_watt(text):
    """문자열 속 와트 표기 중 최댓값(W). 없으면 0. '3kW'=3000, '3,000W'=3000."""
    best = 0.0
    for num, unit in _WATT.findall(str(text or "")):
        try:
            v = float(num.replace(",", "")) if "," in num and len(num.split(",")[-1]) == 3 else float(num.replace(",", "."))
        except ValueError:
            continue
        if unit.lower() in ("kw", "킬로와트"):
            v *= 1000
        best = max(best, v)
    return best


def taobao_item(item):
    """화면 오른쪽에 보이는 대표 매칭(첫 항목). 없으면 None."""
    try:
        res = item.get("taobaoResult") or []
        first = res[0] if res else None
        return (first or {}).get("item") or None
    except Exception:
        return None


def machine_judge(item, stage, cats, kws):
    """확실한 탈락이면 {'verdict':'drop','reason','note'}, 아니면 None."""
    try:
        cat = str(item.get("catId") or "").strip()
        if cat and cat in cats:
            return {"verdict": "drop", "reason": "BANNED_CAT", "note": f"금지 카테고리 {cat}"}

        if stage == 2:
            if item.get("taobao_match_status") == "match_failed" or not taobao_item(item):
                return {"verdict": "drop", "reason": "NO_MATCH", "note": "타오바오 매칭 실패/없음"}

        # 와트는 네이버 상품명(사용자 기준) + 2차면 타오바오 제목도 본다
        texts = [item.get("productName")]
        if stage == 2:
            texts.append((taobao_item(item) or {}).get("title"))
        w = max(max_watt(t) for t in texts)
        if w >= WATT_LIMIT:
            return {"verdict": "drop", "reason": "WATT", "note": f"{int(w)}W 표기 (3000W 이상)"}

        # 판매자 태그는 SEO 잡태그라 오탐이 많다(호이스트에 '레고') → 키워드는 상품명만 본다.
        # 2차에서 팔 물건은 타오바오 상품이라 네이버 상품명으로 자르지 않는다 → 타오바오 제목만.
        if stage == 2:
            text = (taobao_item(item) or {}).get("title")
        else:
            text = item.get("productName")
        # 공백을 지우면 '안장 검정'이 '장검'에 걸린다 → 공백은 하나로만 접는다
        hay = " ".join(str(text or "").split()).lower()
        for code, words in kws.items():
            for w in words:
                if w and w in hay:
                    return {"verdict": "drop", "reason": f"KEYWORD_{code}", "note": f"키워드 '{w}'"}
        return None
    except Exception as e:
        # 판정 중 예외는 AI 로 넘긴다 — 기계가 확실하지 않으면 탈락시키지 않는다
        print(f"[경고] 기계 판정 예외 id={item.get('id')}: {e}")
        return None
