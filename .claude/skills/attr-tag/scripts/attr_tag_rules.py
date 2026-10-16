#!/usr/bin/env python3
"""attr-tag 순수 로직 — 네트워크 없음. 단위테스트 대상.

  · 상세 HTML → 텍스트
  · 카테고리 속성 표(attributes + attribute-values) 정리
  · 태그 검증(사전 정확일치 → 제한 제외 → 10개 상한)
  · 속성 이름/값 텍스트 → seq 매핑(선택형·복수선택형만, 범위형은 건너뜀)
  · keep_existing 병합
  · 저장 본문 조립 · 전/후 diff · 불변 검사 · 반영 확인
"""
import copy
import html
import re

MAX_TAGS = 10
SELECT_TYPES = ("SINGLE_SELECT", "MULTI_SELECT")
DETAIL_TEXT_MAX = 3000


# ---------------------------------------------------------------------------
# 상세 텍스트
# ---------------------------------------------------------------------------
def html_to_text(src, limit=DETAIL_TEXT_MAX):
    """HTML 태그·스크립트 제거 → 엔티티 복원 → 공백 정리 → limit 자 이내."""
    try:
        s = str(src or "")
        s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", s)
        s = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h\d>", "\n", s)
        s = re.sub(r"(?s)<[^>]+>", " ", s)
        s = html.unescape(s)
        s = re.sub(r"[ \t\r\f\v ]+", " ", s)
        s = re.sub(r"\s*\n\s*", "\n", s).strip()
        return s[:limit]
    except Exception:
        return ""


def detail_image_urls(src, limit=5):
    """상세 HTML 안의 <img src> 앞쪽 몇 개."""
    try:
        return re.findall(r"""(?i)<img[^>]+src=["']([^"']+)["']""", str(src or ""))[:limit]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# 상품 본문 접근
# ---------------------------------------------------------------------------
def _detail_attr(product):
    return ((product or {}).get("originProduct") or {}).get("detailAttribute") or {}


def current_tags(product):
    """[{code, text}] — code 가 없거나 빈 태그도 그대로 (사전 미등록 평문 태그)."""
    return list(((_detail_attr(product).get("seoInfo") or {}).get("sellerTags")) or [])


def current_attributes(product):
    return list(_detail_attr(product).get("productAttributes") or [])


def option_names(product):
    """조합형·단독형 옵션명 목록(중복 제거, 순서 유지)."""
    out = []
    try:
        oi = _detail_attr(product).get("optionInfo") or {}
        for c in oi.get("optionCombinations") or []:
            name = " / ".join(str(c.get(k)) for k in ("optionName1", "optionName2", "optionName3", "optionName4")
                              if c.get(k))
            if name and name not in out:
                out.append(name)
        for c in oi.get("optionSimple") or []:
            name = str(c.get("name") or c.get("groupName") or "")
            if name and name not in out:
                out.append(name)
    except Exception:
        pass
    return out


def invariants(product):
    """저장 전후로 바뀌면 안 되는 값 묶음."""
    o = (product or {}).get("originProduct") or {}
    oi = _detail_attr(product).get("optionInfo") or {}
    return {
        "name": o.get("name"),
        "salePrice": o.get("salePrice"),
        "stockQuantity": o.get("stockQuantity"),
        "detailContent_len": len(o.get("detailContent") or ""),
        "statusType": o.get("statusType"),
        "leafCategoryId": o.get("leafCategoryId"),
        "option_count": len(oi.get("optionCombinations") or []),
        "option_prices": [c.get("price") for c in oi.get("optionCombinations") or []],
    }


def invariant_diff(before, after):
    """불변값 비교 → 달라진 항목 [{field, before, after}]. 빈 리스트면 통과."""
    a, b = invariants(before), invariants(after)
    return [{"field": k, "before": a[k], "after": b[k]} for k in a if a[k] != b[k]]


# ---------------------------------------------------------------------------
# 카테고리 속성 표
# ---------------------------------------------------------------------------
def _value_text(v):
    """선택지 표시 텍스트. 단위코드가 붙은 값(예 '5' A02069)은 텍스트는 값만 쓴다."""
    lo = v.get("minAttributeValue")
    hi = v.get("maxAttributeValue")
    if hi not in (None, "") and str(hi) != str(lo):
        return f"{lo}~{hi}"
    return str(lo if lo is not None else "")


def build_attr_table(attributes, values):
    """API 원본 2개 → {attributeSeq: {seq, name, type, kind, max, values:[{seq,text,unit}]}}."""
    table = {}
    for a in attributes or []:
        try:
            seq = int(a["attributeSeq"])
        except (KeyError, TypeError, ValueError):
            continue
        table[seq] = {
            "seq": seq,
            "name": str(a.get("attributeName") or ""),
            "type": a.get("attributeClassificationType") or "",
            "type_name": a.get("attributeClassificationCodeName") or "",
            "kind": a.get("attributeTypeCodeName") or a.get("attributeType") or "",
            "max": int(a.get("attributeValueMaxMatchingCount") or 0),
            "values": [],
        }
    for v in sorted(values or [], key=lambda x: (x.get("attributeSeq") or 0, x.get("exposureOrder") or 0)):
        try:
            t = table.get(int(v["attributeSeq"]))
        except (KeyError, TypeError, ValueError):
            continue
        if t is None:
            continue
        item = {"seq": v.get("attributeValueSeq"), "text": _value_text(v)}
        if v.get("minAttributeValueUnitCode"):
            item["unit"] = v.get("minAttributeValueUnitCode")
        t["values"].append(item)
    return table


def attr_table_for_prompt(table):
    """판단 재료용 — 입력 가능 속성 목록(이름·유형·주요/부가·선택지 텍스트)."""
    out = []
    for t in table.values():
        row = {"name": t["name"], "type": t["type_name"] or t["type"], "kind": t["kind"],
               "choices": [v["text"] for v in t["values"]]}
        if t["max"]:
            row["max_select"] = t["max"]
        if t["type"] not in SELECT_TYPES:
            row["note"] = "범위형 — 이 도구는 입력하지 않는다"
        out.append(row)
    return out


def describe_attributes(attrs, table):
    """현재 productAttributes → [{name, value}] (이름=값으로 풀어서)."""
    out = []
    for a in attrs or []:
        t = table.get(_int(a.get("attributeSeq")))
        name = t["name"] if t else f"#{a.get('attributeSeq')}"
        val = None
        if t:
            for v in t["values"]:
                if v["seq"] == a.get("attributeValueSeq"):
                    val = v["text"]
                    break
        if val is None:
            # 범위형 등 — 원본 값 필드를 그대로 보여준다
            raw = {k: v for k, v in a.items() if k not in ("attributeSeq",)}
            val = raw
        out.append({"name": name, "value": val})
    return out


def _int(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 태그 검증
# ---------------------------------------------------------------------------
def resolve_tags(texts, recommend, restricted):
    """태그 텍스트 → ([{code, text}], dropped[{text, reason}]).

    recommend(text) → [{code, text}]  (접두 자동완성 — text 정확일치만 채택)
    restricted(list_of_text) → {text: bool}
    순서: 정리·중복제거 → 사전 정확일치 → 제한 제외 → 10개 상한.
    """
    dropped, cands, seen = [], [], set()
    for raw in texts or []:
        t = str(raw or "").strip()
        if not t:
            continue
        if t in seen:
            dropped.append({"text": t, "reason": "duplicate"})
            continue
        seen.add(t)
        if "," in t:
            dropped.append({"text": t, "reason": "invalid_char"})
            continue
        try:
            hits = recommend(t) or []
        except Exception as e:
            dropped.append({"text": t, "reason": f"lookup_error:{type(e).__name__}"})
            continue
        code = None
        for h in hits:
            if str(h.get("text") or "") == t and h.get("code") not in (None, ""):
                code = h.get("code")
                break
        if code is None:
            dropped.append({"text": t, "reason": "not_in_dictionary"})
            continue
        cands.append({"code": code, "text": t})

    if cands:
        try:
            rmap = restricted([c["text"] for c in cands]) or {}
        except Exception as e:
            # 제한 여부를 모르면 넣지 않는다 (제한 태그는 저장 400 원인)
            for c in cands:
                dropped.append({"text": c["text"], "reason": f"restricted_check_error:{type(e).__name__}"})
            return [], dropped
        ok = []
        for c in cands:
            if c["text"] not in rmap:
                dropped.append({"text": c["text"], "reason": "restricted_unknown"})
            elif rmap[c["text"]]:
                dropped.append({"text": c["text"], "reason": "restricted"})
            else:
                ok.append(c)
        cands = ok

    for c in cands[MAX_TAGS:]:
        dropped.append({"text": c["text"], "reason": "over_limit"})
    return cands[:MAX_TAGS], dropped


# ---------------------------------------------------------------------------
# 속성 매핑
# ---------------------------------------------------------------------------
def resolve_attributes(wanted, table):
    """plan 의 [{name, values}] → ([{attributeSeq, attributeValueSeq}], dropped[{name, value?, reason}]).

    선택지에 **정확히 있는 텍스트만** seq 로. 선택형은 1개, 복수선택형은 여러 개(max 있으면 상한).
    범위형은 건너뛰고 기록.
    """
    by_name = {}
    for t in table.values():
        by_name.setdefault(t["name"], t)
    out, dropped, used = [], [], set()
    for w in wanted or []:
        name = str((w or {}).get("name") or "").strip()
        vals = (w or {}).get("values")
        if vals is None and (w or {}).get("value") is not None:
            vals = [w.get("value")]
        if isinstance(vals, str):
            vals = [vals]
        vals = [str(v).strip() for v in (vals or []) if str(v or "").strip()]
        t = by_name.get(name)
        if t is None:
            dropped.append({"name": name, "reason": "unknown_attribute"})
            continue
        if t["seq"] in used:
            dropped.append({"name": name, "reason": "duplicate_attribute"})
            continue
        if t["type"] not in SELECT_TYPES:
            dropped.append({"name": name, "reason": "range_type_unsupported"})
            continue
        picked = []
        for v in vals:
            hit = next((x for x in t["values"] if x["text"] == v), None)
            if hit is None:
                dropped.append({"name": name, "value": v, "reason": "value_not_in_choices"})
            elif hit["seq"] in [p["attributeValueSeq"] for p in picked]:
                dropped.append({"name": name, "value": v, "reason": "duplicate_value"})
            else:
                picked.append({"attributeSeq": t["seq"], "attributeValueSeq": hit["seq"], "_text": v})
        limit = 1 if t["type"] == "SINGLE_SELECT" else (t["max"] or len(picked))
        for p in picked[limit:]:
            dropped.append({"name": name, "value": p["_text"], "reason": "over_select_limit"})
        picked = picked[:limit]
        if not picked:
            if vals:
                continue  # 값 사유는 위에서 기록
            dropped.append({"name": name, "reason": "no_values"})
            continue
        used.add(t["seq"])
        out.extend({"attributeSeq": p["attributeSeq"], "attributeValueSeq": p["attributeValueSeq"]}
                   for p in picked)
    return out, dropped


def merge_attributes(existing, new, keep_existing=True):
    """keep_existing 이면 new 에 나온 attributeSeq 만 통째로 교체하고 나머지(범위형 포함)는 보존."""
    if not keep_existing:
        return [dict(a) for a in new]
    replaced = {a["attributeSeq"] for a in new}
    kept = [dict(a) for a in existing or [] if _int(a.get("attributeSeq")) not in replaced]
    return kept + [dict(a) for a in new]


# ---------------------------------------------------------------------------
# 본문 조립 · 비교 · 확인
# ---------------------------------------------------------------------------
def build_body(product, tags=None, attributes=None):
    """조회 응답 전체를 깊은복사해 태그·속성만 바꾼다. None 이면 그 항목은 그대로."""
    body = copy.deepcopy(product)
    da = body.setdefault("originProduct", {}).setdefault("detailAttribute", {})
    if tags is not None:
        seo = da.get("seoInfo") or {}
        # 원본에 없던 키는 만들지 않는다 (code 없는 평문 태그를 되돌릴 때 code:null 을 보내지 않게)
        seo["sellerTags"] = [{k: t[k] for k in ("code", "text") if k in t} for t in tags]
        da["seoInfo"] = seo
    if attributes is not None:
        da["productAttributes"] = [dict(a) for a in attributes]
    return body


def _attr_key(a):
    return (_int(a.get("attributeSeq")), _int(a.get("attributeValueSeq")))


def change_summary(before, after_body):
    """태그·속성 변경 전/후 요약."""
    bt, at = current_tags(before), current_tags(after_body)
    ba, aa = current_attributes(before), current_attributes(after_body)
    bset, aset = {_attr_key(a) for a in ba}, {_attr_key(a) for a in aa}
    return {
        "tags_before": bt, "tags_after": at,
        "tags_changed": [(t.get("code"), t.get("text")) for t in bt] != [(t.get("code"), t.get("text")) for t in at],
        "attributes_before": ba, "attributes_after": aa,
        "attributes_added": [a for a in aa if _attr_key(a) not in bset],
        "attributes_removed": [a for a in ba if _attr_key(a) not in aset],
    }


def verify_applied(after_fetch, intended_body):
    """재조회 결과에 의도한 태그 code·속성 seq 가 들어갔는지. 문제 목록(빈 리스트=확인)."""
    problems = []
    want_codes = {str(t.get("code")) for t in current_tags(intended_body) if t.get("code") not in (None, "")}
    got_codes = {str(t.get("code")) for t in current_tags(after_fetch) if t.get("code") not in (None, "")}
    missing = want_codes - got_codes
    if missing:
        problems.append({"what": "tags_missing", "codes": sorted(missing)})
    want_attr = {_attr_key(a) for a in current_attributes(intended_body)}
    got_attr = {_attr_key(a) for a in current_attributes(after_fetch)}
    miss_a = want_attr - got_attr
    if miss_a:
        problems.append({"what": "attributes_missing", "pairs": sorted(miss_a, key=str)})
    return problems


def summary_memo(results):
    """업무판 메모 — '상품 N · 태그 평균 t개 · 속성 a개 · 실패 f'."""
    ok = [r for r in results if r.get("status") == "ok"]
    fail = [r for r in results if r.get("status") != "ok"]
    avg = (sum(r.get("tag_count", 0) for r in ok) / len(ok)) if ok else 0
    attrs = sum(r.get("attributes_added", 0) for r in ok)
    return f"상품 {len(ok)} · 태그 평균 {avg:.1f}개 · 속성 {attrs}개 · 실패 {len(fail)}"
