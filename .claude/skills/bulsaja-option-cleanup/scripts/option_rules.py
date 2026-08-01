#!/usr/bin/env python3
"""옵션 정리 — **순수 계산** 부분. 불사자도 시트도 부르지 않는다(그래서 테스트가 된다).

역할 분담:
  · 사람/Claude 가 판단 — 메인상품이 무엇인가, 이 옵션이 비상품인가, 이름을 뭐라 지을까,
    최저가가 동률일 때 어느 쪽이 썸네일과 더 닮았나 (전부 증거를 봐야 아는 것)
  · 이 모듈이 계산 — 대표옵션 후보·1.5배 상한·상한 초과 제외·오름차순 순서·이름 규칙 검사·
    저장 후 검증 6항목 (전부 정해진 규칙이라 사람이 다시 판단할 이유가 없다)

핵심 규칙(헤르메스 12 단계4, 이룸님 채택):
  ① 메인상품 **완전 판매 옵션**만 대상으로 판매가 비교
  ② 최저가 후보 중 대표 썸네일과 가장 닮은 것을 대표로 (동률 → 원본 순서)
  ③ **기준가격(대표가) × 1.5 = 판매 상한** (같은 값 포함)
  ④ 상한 이하 메인상품 옵션만 유지
  ⑤ 판매가 오름차순 정렬 (동가는 원본 순서)
  ⑥ 대표가 정렬 첫 번째여야 한다

**1.5배 상한은 메인상품 후보를 확정한 뒤에만 적용한다** — 비상품(부속품·보증금 등)이
섞인 채로 계산하면 기준가격 자체가 틀린다.
"""
import re

# 옵션명 상한 — 공백 포함 25자(헤르메스 12 단계3).
NAME_MAX = 25
# 판매 상한 배수 — 대표가의 1.5배까지 같은 상품으로 본다.
PRICE_MULTIPLE = 1.5
# 대표옵션 마커 (2026-07-30 이룸님) — 네이버는 '대표상품'(추가금 0원 옵션)을 상품명으로
# 쓰라고 요구한다. 그래서 **상품명 끝과 대표옵션명 끝에 같은 단어**를 붙여 짝을 지목한다
# (상품명 쪽은 product-name/name_check.py R8). 마커라 규칙 7('형' 군더더기 제거)의 예외다.
# 25자 상한은 그대로 — 자리는 규칙 6(전 옵션 공통 정보 제거)으로 만든다.
BASE_SUFFIX = "기본형"
# rename 키가 (차원, 값) 위치 지정임을 나타내는 접두사. 판매행 id("1:1")와 구분하려고 붙인다.
POS_KEY_PREFIX = "@"
# 정렬용 접두사: 'A. ' 'B) ' '가. ' 등. 실제 사이즈 S/M/L/XL 은 보존해야 하므로
# **한 글자 + 구두점** 형태만 벗긴다(뒤에 반드시 공백 아닌 내용이 남아야 한다).
_PREFIX = re.compile(r"^\s*[A-Za-z0-9가-힣]\s*[.)]\s+(?=\S)")


def strip_prefix(name):
    """정렬용 접두사만 제거. 'A. 블랙 수트' → '블랙 수트', 'S/M/L' 같은 값은 그대로."""
    return _PREFIX.sub("", str(name or "")).strip()


def name_problems(name):
    """옵션명 1개의 규칙 위반 목록. 비어 있으면 통과."""
    n = str(name or "")
    out = []
    if not n.strip():
        out.append("빈 이름")
        return out
    if len(n) > NAME_MAX:
        out.append(f"{len(n)}자(상한 {NAME_MAX})")
    if re.search(r"[一-鿿]", n):
        out.append("중국어 잔존")
    if _PREFIX.match(n):
        out.append("정렬용 접두사 잔존")
    return out


def check_names(names, groups=None):
    """{키: 새이름} → {"위반": {키: [사유]}, "중복": {이름: [키...]}}.

    `groups` = {키: 그룹} 이면 **그룹 안에서만** 중복을 본다. 복합 옵션은 차원이 다르면
    같은 이름이 정상이다(색상 '블랙' 과 테두리색 '블랙'은 충돌이 아니다) —
    전체에서 중복을 잡으면 멀쩡한 이름을 비틀게 된다.
    """
    viol = {k: p for k, p in ((k, name_problems(v)) for k, v in names.items()) if p}
    bykey = {}
    for k, v in names.items():
        g = (groups or {}).get(k, 0)
        bykey.setdefault((g, str(v).strip()), []).append(k)
    dup = {v: ks for (_, v), ks in bykey.items() if len(ks) > 1}
    return {"위반": viol, "중복": dup}


def dim_of(option):
    """{vid(str): 차원 index} — 이름 중복을 차원별로 보기 위한 매핑."""
    out = {}
    for gi, d in enumerate(option.get("차원") or []):
        for v in (d.get("values") or []):
            out.setdefault(str(v.get("vid")), gi)
    return out


# ---------------------------------------------------------------------------
# 대표옵션 마커 ('기본형') — 2026-07-30 이룸님
#
# 네이버는 '대표상품'(추가금 0원 옵션)을 상품명으로 쓰라고 요구한다. 그래서 상품명 끝과
# **대표옵션명 끝**에 같은 단어를 붙여 짝을 지목한다. 스킬 간 데이터 계약을 새로 만들지
# 않아도 되는 게 이 방식의 요점이다 — 상품명 스킬은 대표옵션이 뭔지 몰라도 되고,
# 이 스킬은 자기가 정한 대표에 붙이면 된다.
#
# **위치 지정 키가 왜 필요한가**: 워커는 `이름` 을 vid 로 키를 준다(배치에 vid 가 보인다).
# 그런데 복합옵션은 vid 가 차원마다 1부터 다시 시작해서, vid 만으로는 어느 차원인지 알 수
# 없다. 기존 `rename_targets` 는 `setdefault(vid)` 라 **첫 차원이 키를 선점** —
# 2번째 이후 차원 값은 이름을 바꿀 방법이 아예 없었다(기존 결함). 그래서 `@차원:vid`
# 형식을 더한다. 배치의 옵션 이미지 키가 이미 `"{gi}:{vid}"` 라 관례가 같다.
# ---------------------------------------------------------------------------

def pos_key(gi, vid):
    """(차원 index, vid) → 위치 지정 키 `@0:3`."""
    return f"{POS_KEY_PREFIX}{gi}:{vid}"


def _parse_pos_key(key):
    """`@0:3` → (0, '3'). 형식이 아니면 (None, '')."""
    k = str(key or "")
    if not k.startswith(POS_KEY_PREFIX):
        return None, ""
    gi_s, sep, vid = k[len(POS_KEY_PREFIX):].partition(":")
    if not sep or not gi_s.isdigit() or not vid:
        return None, ""
    return int(gi_s), vid


def value_entries(option):
    """[(위치키, 차원index, vid, 현재이름)] — 차원 값 전체를 원본 순서대로."""
    out = []
    for gi, d in enumerate(option.get("차원") or []):
        for v in (d.get("values") or []):
            vid = str(v.get("vid"))
            out.append((pos_key(gi, vid), gi, vid, v.get("name") or ""))
    return out


def pos_groups(option):
    """{위치키: 차원 index} — `check_names(groups=)` 용. 차원 안에서만 중복을 본다."""
    return {k: gi for k, gi, _vid, _n in value_entries(option)}


def ambiguous_vids(option):
    """2개 이상 차원에 나타나는 vid 집합 — 이 vid 는 위치 지정 키로만 찍을 수 있다."""
    seen, dup = {}, set()
    for _k, gi, vid, _n in value_entries(option):
        if vid in seen and seen[vid] != gi:
            dup.add(vid)
        seen.setdefault(vid, gi)
    return dup


def normalize_key(option, key):
    """`이름` 의 키를 위치 지정 키로 정규화한다. 못 찾거나 모호하면 ""."""
    gi, vid = _parse_pos_key(key)
    entries = value_entries(option)
    if gi is not None:
        for k, g, v, _n in entries:
            if g == gi and v == vid:
                return k
        return ""
    k0 = str(key or "")
    if k0 in ambiguous_vids(option):
        return ""          # 어느 차원인지 알 수 없다 — @차원:vid 로 줘야 한다
    for k, _g, v, _n in entries:
        if v == k0:
            return k
    return ""


def effective_names(option, names=None):
    """{위치키: 저장 후 이름} — `names` 에 있으면 그것, 없으면 현재 이름.

    안 바꾸는 옵션의 현재 이름까지 봐야 한다 — 마커가 대표를 지목하는 유일한 수단이라,
    대표 아닌 옵션에 남아 있으면 상품명이 어느 옵션을 가리키는지 흐려진다.
    """
    eff = {k: cur for k, _gi, _vid, cur in value_entries(option)}
    for key, new in (names or {}).items():
        nk = normalize_key(option, key)
        if nk:
            eff[nk] = str(new)
    return eff


def has_base_suffix(name):
    """이름이 `기본형` 으로 끝나는가."""
    return str(name or "").strip().endswith(BASE_SUFFIX)


def main_value_key(option, main_row_id):
    """대표 판매행 → `기본형` 을 붙일 차원 값의 위치 지정 키. 반환 (키, 오류메시지).

    1차원 : 판매행 id 가 곧 vid 다.
    복합   : id 는 차원 순서대로 vid 를 ':' 로 이은 조합키(`"1:1"`). 결정 7(2026-07-30)에
             따라 **마지막 차원**의 값에 붙인다. 한 차원 값은 여러 판매행에 공유되므로
             어디에 붙여도 대표가 아닌 조합에도 마커가 보인다 — 구조적으로 우회할 수
             없어서 오염을 감수한 결정이다.
    """
    dims = option.get("차원") or []
    rid = str(main_row_id or "")
    if not rid:
        return "", "대표 판매행이 없다"
    if not dims:
        return "", "차원이 없다 — 마커를 붙일 옵션값이 없다"
    parts = rid.split(":")
    if len(parts) != len(dims):
        return "", (f"판매행 id 조각 {len(parts)}개가 차원 {len(dims)}개와 다르다({rid})")
    gi = len(dims) - 1
    key = normalize_key(option, pos_key(gi, parts[-1]))
    if not key:
        return "", f"마지막 차원({gi})에 vid={parts[-1]} 값이 없다"
    return key, ""


def check_base_suffix(option, names, main_key):
    """대표옵션만 `기본형` 으로 끝나야 한다. 반환 {"누락": bool, "오부착": [위치키...]}."""
    eff = effective_names(option, names)
    return {
        "누락": not (main_key and has_base_suffix(eff.get(main_key, ""))),
        "오부착": sorted(k for k, v in eff.items()
                       if k != main_key and has_base_suffix(v)),
    }


# ---------------------------------------------------------------------------
# 사람이 읽는 이름 — 승인 자료의 재료
#
# 계산은 전부 **id** 로 한다(대표·유지·제외·순서). 그런데 승인은 사람이 하고, 사람은
# `1 > 2 > 3 > 13` 을 읽지 못한다. 실전 1건에서 이룸님이 "뭘 보고 승인하냐"고 지적한 지점 —
# 승인해야 할 옵션명이 시트·게이트·plans.json 어디에도 없었다. 아래 두 함수가 그 재료다.
# ---------------------------------------------------------------------------

def value_names(option):
    """{vid(str): 현재 옵션값 이름}."""
    return {str(v.get("vid")): (v.get("name") or "")
            for d in (option.get("차원") or []) for v in (d.get("values") or [])}


def name_changes(option, names):
    """[{키, 차원, 기존, 교정, 변경}] — 기존→교정 대조표.

    `names` 의 키는 옵션값 vid(1차원 상품은 판매행 id 와 같다).
    `변경=False` 인 항목도 남긴다 — "안 바꿨다"도 승인 대상이다.
    """
    cur = value_names(option)
    dim_label = {}
    for gi, d in enumerate(option.get("차원") or []):
        for v in (d.get("values") or []):
            dim_label[str(v.get("vid"))] = d.get("이름") or f"차원{gi}"
    out = []
    for k, new in (names or {}).items():
        k, new = str(k), str(new)
        old = cur.get(k, "")
        out.append({"키": k, "차원": dim_label.get(k, ""), "기존": old,
                    "교정": new, "변경": new.strip() != old.strip()})
    return out


def row_labels(option, names=None):
    """판매행 id → 사람이 읽을 이름. 교정 이름이 있으면 그것, 없으면 현재 표시명.

    1차원 상품은 판매행 id 가 곧 vid 라 교정 이름이 그대로 붙는다. 복합 옵션의 표시명은
    차원 값 이름을 이어 붙인 문자열이라, 그 안의 옛 이름을 교정 이름으로 바꿔 끼운다.
    (긴 이름부터 치환한다 — 짧은 이름이 긴 이름의 일부일 때 먼저 먹어버리지 않게.)
    """
    n = {str(k): str(v) for k, v in (names or {}).items()}
    cur = value_names(option)
    subs = sorted(((cur.get(k, ""), v) for k, v in n.items() if cur.get(k)),
                  key=lambda t: -len(t[0]))
    out = {}
    for r in (option.get("판매행") or []):
        rid = str(r.get("id"))
        if rid in n:
            out[rid] = n[rid]
            continue
        text = r.get("text") or ""
        for old, new in subs:
            if old in text:
                text = text.replace(old, new)
        out[rid] = text or rid
    return out


def _price(row):
    p = row.get("sale_price")
    return p if isinstance(p, (int, float)) else None


def sellable(row, require_stock=True):
    """'완전 판매 옵션'인가 — 가격이 있고 재고가 있는 행."""
    if _price(row) is None:
        return False
    if require_stock:
        st = row.get("stock")
        if isinstance(st, (int, float)) and st <= 0:
            return False
    return True


def plan(option, keep_ids, names=None, prefer_id=None, require_stock=True,
         multiple=PRICE_MULTIPLE):
    """정리안을 계산한다. 불사자를 부르지 않는다.

    option    = 스냅샷의 `옵션` (차원·판매행·vid고유)
    keep_ids  = Claude 가 '메인상품'으로 판정해 남긴 판매행 id 집합
    names     = {판매행 id 또는 vid 키: 새 이름} (선택 — 검사에만 쓴다)
    prefer_id = 최저가 동률일 때 Claude 가 고른 id(썸네일 최유사). 없으면 원본 순서.

    반환: {대표, 기준가, 상한, 유지[], 제외[{id,사유}], 순서[], 경고[], 이름검사}
    """
    rows = list(option.get("판매행") or [])
    order_of = {r["id"]: i for i, r in enumerate(rows)}
    keep = set(keep_ids or ())
    warn = []

    # ① 메인상품이면서 실제로 팔 수 있는 행만 후보
    cands = [r for r in rows if r["id"] in keep and sellable(r, require_stock)]
    dropped_unsellable = [r for r in rows if r["id"] in keep and not sellable(r, require_stock)]

    result = {"대표": None, "기준가": None, "상한": None, "대표값키": "",
              "유지": [], "제외": [], "순서": [], "경고": warn, "이름검사": None}

    for r in rows:
        if r["id"] not in keep:
            result["제외"].append({"id": r["id"], "사유": "비상품/메인상품 아님"})
    for r in dropped_unsellable:
        result["제외"].append({"id": r["id"], "사유": "판매불가(가격 없음 또는 재고 0)"})

    if not cands:
        warn.append("메인상품으로 남길 판매 가능한 옵션이 없다 — 저장하면 안 된다")
        return result

    # ② 최저가 후보 → 동률이면 Claude 가 고른 것 → 그래도 없으면 원본 순서
    low = min(_price(r) for r in cands)
    tied = [r for r in cands if _price(r) == low]
    if prefer_id and any(r["id"] == prefer_id for r in tied):
        main = next(r for r in tied if r["id"] == prefer_id)
    else:
        if prefer_id and any(r["id"] == prefer_id for r in cands):
            # 더 비싼데 썸네일이 닮았다는 이유로 대표를 올리지 않는다(헤르메스 12 단계4)
            warn.append(f"지정한 대표({prefer_id})가 최저가가 아니라 무시했다")
        if len(tied) > 1 and not prefer_id:
            warn.append(f"최저가 동률 {len(tied)}건 — 썸네일 최유사 판단 없이 원본 순서로 정했다")
        main = min(tied, key=lambda r: order_of[r["id"]])

    # ③ 기준가격 × 1.5 = 상한 (같은 값 포함)
    base = _price(main)
    cap = base * multiple

    # ④ 상한 이하만 유지
    kept = [r for r in cands if _price(r) <= cap]
    for r in cands:
        if _price(r) > cap:
            result["제외"].append({
                "id": r["id"],
                "사유": f"1.5배 상한 초과({_price(r):,}원 > {int(cap):,}원)"})

    # ⑤ 판매가 오름차순 (동가는 원본 순서)
    # ⑥ 단 **대표는 동가 그룹 안에서 맨 앞**이다 — 대표는 고객이 처음 보는 옵션이라
    #    "대표가 정렬 첫 번째"(헤르메스 12 단계4-⑥)가 확인이 아니라 요구사항이다.
    #    동가 동률에서 썸네일 최유사로 대표를 골랐는데 원본 순서가 뒤면 밀려버린다.
    kept.sort(key=lambda r: (_price(r), 0 if r["id"] == main["id"] else 1,
                             order_of[r["id"]]))

    if kept and kept[0]["id"] != main["id"]:
        warn.append(f"대표({main['id']})가 정렬 첫 번째가 아니다 — 계산을 확인해라")

    # 대표옵션 마커('기본형')를 붙일 차원 값 — 못 찾으면 경고로 표면화한다(추측 금지)
    main_key, key_err = main_value_key(option, main["id"])
    if key_err:
        warn.append(f"대표옵션 마커를 붙일 값을 못 찾았다 — {key_err}")

    result.update({
        "대표": main["id"], "기준가": base, "상한": int(cap), "대표값키": main_key,
        "유지": [r["id"] for r in kept], "순서": [r["id"] for r in kept],
    })
    if names:
        chk = check_names(names, groups=dim_of(option))
        chk["마커"] = check_base_suffix(option, names, main_key)
        result["이름검사"] = chk
    return result


def rename_targets(option, names):
    """{키: 새이름} → bulsaja_option_update 의 `renameValues` 항목들.

    이름을 바꾸는 대상은 **옵션값(차원)** 이지 판매행이 아니다.
    `vid고유`가 아니면(복합 옵션은 차원마다 vid 가 1부터 다시 시작한다)
    vid 로 지정하면 엉뚱한 차원이 바뀌므로 `groupIndex`/`valueIndex` 로 찍는다.

    키는 두 형식을 받는다:
      · `"3"`      vid. **2개 이상 차원에 같은 vid 가 있으면 모호해서 거부한다**(→ missing).
                   예전엔 첫 차원으로 조용히 붙어서 엉뚱한 차원이 바뀔 수 있었다.
      · `"@1:3"`   차원 1의 vid 3. 복합옵션에서 2번째 이후 차원을 찍는 유일한 방법.
    반환: (항목[], 못 찾은/모호한 키[])  — 호출부는 missing 이 있으면 저장을 멈춘다.
    """
    dims = option.get("차원") or []
    vi_of = {}   # (gi, vid) → valueIndex
    for gi, d in enumerate(dims):
        for vi, v in enumerate(d.get("values") or []):
            vi_of[(gi, str(v.get("vid")))] = vi
    dup = ambiguous_vids(option)
    out, missing = [], []
    for key, new in names.items():
        gi, vid = _parse_pos_key(key)
        if gi is None:
            k = str(key)
            if k in dup:
                missing.append(key)      # 어느 차원인지 알 수 없다
                continue
            gi = next((g for _k, g, v, _n in value_entries(option) if v == k), None)
            vid = k
        if gi is None or (gi, vid) not in vi_of:
            missing.append(key)
            continue
        vi = vi_of[(gi, vid)]
        if option.get("vid고유"):
            out.append({"vid": dims[gi]["values"][vi]["vid"], "name": new})
        else:
            out.append({"groupIndex": gi, "valueIndex": vi, "name": new})
    return out, missing


def verify(before, after, plan_result, names=None):
    """저장 후 재조회한 옵션(after)이 정리안대로인지 검사한다 — 헤르메스 12 단계7.

    before = 저장 전 스냅샷의 `옵션`, after = 재조회한 `옵션`.
    반환: [실패 사유]. 비어 있으면 통과.
    """
    fails = []
    a_rows = {r["id"]: r for r in (after.get("판매행") or [])}
    b_rows = {r["id"]: r for r in (before.get("판매행") or [])}
    keep = list(plan_result.get("유지") or [])

    # ① 옵션 수가 그대로인가 (정리는 포함/제외를 바꿀 뿐 옵션을 지우지 않는다)
    if len(a_rows) != len(b_rows):
        fails.append(f"옵션 수가 바뀌었다 {len(b_rows)} → {len(a_rows)}")

    # ② 대표옵션 정확히 1개 · 판매 포함 · 계획한 그것
    mains = [r["id"] for r in a_rows.values() if r.get("main_product")]
    if len(mains) != 1:
        fails.append(f"대표옵션이 {len(mains)}개다(정확히 1개여야 한다)")
    elif mains[0] != plan_result.get("대표"):
        fails.append(f"대표옵션이 다르다 계획={plan_result.get('대표')} 실제={mains[0]}")
    elif a_rows[mains[0]].get("exclude"):
        fails.append("대표옵션이 판매 제외 상태다")

    # ③ 포함/제외가 계획과 같은가
    want_in = set(keep)
    got_in = {r["id"] for r in a_rows.values() if not r.get("exclude")}
    if want_in != got_in:
        fails.append(f"판매 포함이 다르다 (누락 {sorted(want_in - got_in)[:5]} / "
                     f"초과 {sorted(got_in - want_in)[:5]})")

    # ④ 1.5배 상한 재계산 — 저장된 값으로 다시 계산해도 넘는 게 없어야 한다
    base = plan_result.get("기준가")
    if base and want_in == got_in:
        over = [i for i in got_in
                if (a_rows[i].get("sale_price") or 0) > base * PRICE_MULTIPLE]
        if over:
            fails.append(f"상한 초과가 판매 중이다: {sorted(over)[:5]}")

    # ⑤ 가격·재고가 무단으로 바뀌지 않았는가 (정리는 가격을 건드리지 않는다)
    moved = [i for i in (set(a_rows) & set(b_rows))
             if a_rows[i].get("sale_price") != b_rows[i].get("sale_price")]
    if moved:
        fails.append(f"판매가가 바뀐 옵션이 있다: {sorted(moved)[:5]}")

    # ⑥ 유지 옵션의 최종 표시명이 서로 모두 달라야 한다
    disp = {}
    for i in got_in:
        disp.setdefault((a_rows[i].get("text") or "").strip(), []).append(i)
    dup = {t: ids for t, ids in disp.items() if len(ids) > 1}
    if dup:
        fails.append(f"표시명이 겹친다: {list(dup)[:3]}")
    if names:
        # 복합 옵션의 표시명은 차원 이름을 이어 붙인 것이라 25자를 넘을 수 있다 —
        # 상한은 **차원 값 이름**에 거는 규칙이므로 여기서는 차원 쪽을 검사한다.
        # 위치 지정 키로 본다 — vid 로 키를 만들면 복합옵션에서 차원끼리 vid 가 겹쳐
        # dict 가 서로를 덮어써서(같은 vid 2개 → 1칸) 검사에서 조용히 빠진다.
        vals = effective_names(after)
        chk = check_names(vals, groups=pos_groups(after))
        if chk["위반"]:
            fails.append(f"이름 규칙 위반이 남아 있다: {list(chk['위반'])[:5]}")
        if chk["중복"]:
            fails.append(f"같은 차원에 같은 이름이 있다: {list(chk['중복'])[:3]}")

        # ⑦ 대표옵션 마커 — `기본형` 이 대표 값 하나에만 있어야 한다.
        #    상품명 끝의 `기본형` 과 짝을 이루는 유일한 표식이라, 대표 아닌 옵션에 붙어
        #    있으면 상품명이 어느 옵션을 가리키는지 흐려진다.
        mkey = plan_result.get("대표값키")
        if not mkey:
            fails.append(f"대표옵션 마커를 붙일 값을 못 찾았다('{BASE_SUFFIX}' 검사 불가)")
        else:
            mark = check_base_suffix(after, None, mkey)
            if mark["누락"]:
                fails.append(f"대표옵션 이름이 '{BASE_SUFFIX}'로 끝나지 않는다")
            if mark["오부착"]:
                fails.append(f"대표가 아닌 옵션에 '{BASE_SUFFIX}'가 붙어 있다: "
                             f"{mark['오부착'][:3]}")
    return fails
