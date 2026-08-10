#!/usr/bin/env python3
"""규격어 ↔ 옵션 정합 판정 — 상품명이 쓴 규격이 어느 옵션을 가리키는가.

## 왜 있나

상품명 스킬은 **상품수 낮은 직결어**를 먼저 고른다(product-name SKILL.md). 그러다 보면
`3단서빙카트` · `3인용리클라이너소파` · `스텐사이드테이블` 처럼 **규격어가 붙은** 키워드를
채택한다(용쌤1-3 실측: 706건 중 152건 = 21.5%). 규격어를 붙이면 상품수가 중앙값 1/11로
떨어지니 상위노출에 유리하다.

문제는 **그 규격이 실제로 팔릴 대표옵션의 규격과 다를 수 있다**는 것이다.
발단 = `U01KR7VXBA7SF37GR6XHZ9VTVGH` — 상품명은 `3단`인데 대표옵션은 2단 퇴식카트.
리스팅 제목(`包邮加厚酒店餐车三层不锈钢…`)의 `三层` 은 옵션 44개 중 한 갈래일 뿐인데
그걸 상품 전체의 규격으로 읽었다.

## 3갈래 판정

규격어가 옵션 차원에서 어떤 위치인가로 갈린다(2026-08-05 이룸님 확정).

  (가) **갈리는 값** — 일부 옵션만 해당. 2층 옵션과 3층 옵션이 따로 있다.
       → 규격은 "어느 옵션을 사느냐"의 문제. 그 옵션을 대표로 세워야 한다.
  (나) **공통 속성** — 전 옵션이 해당하거나, 옵션엔 없고 제목에만 있다.
       → 규격은 상품 전체의 성질. 대표는 최저가 그대로.
  (다) **근거 없음** — 옵션에도 제목에도 없다. → 규격어 키워드를 버린다.

(나)의 "옵션엔 없고 제목에만"이 중요하다. `옵션명-규칙.md` 규칙 6이 **전 옵션이 공유하는
정보를 이름에서 일부러 뺀다** — 3단 선반인데 옵션이 색상뿐이면 어느 옵션명에도 3단이
없다. 한국어 옵션명만 보면 정당한 규격어를 (다)로 오판한다. 그래서 **중국어 원문
(`_name`)과 제목을 함께** 본다. 용쌤1-3 실측 81건: (가) 28 · (나) 53 · (다) 0.

설계: `00-system/04-specs/2026-08-05-상품명-대표옵션-규격어-design.md`
"""
import re

# 배치에 실을 옵션 목록 상한. `snapshot._OPT_MAX = 8`(정체판별용 요약)과 **별개**다 —
# 규격 판단은 전량을 봐야 한다. 발단 사례에서 실물 라인 `收碗车` 11개가 앞 8개에
# 하나도 없어서 워커가 텍스트 증거만으로 3단이라 결론냈다.
OPT_LIST_MAX = 60

# ── 규격어 정의 (2026-08-05 이룸님) ────────────────────────────────────────
# 수량+단위 · 소재어 · 치수. **크기어(대형·중형·소형·미니)는 제외** — 상대 표현이라
# 같은 `大号` 가 상품마다 다른 크기를 가리켜 옵션 매칭이 불안정하다.
_UNIT_KO = r"인용|인치|개입|세트|리터|단|층|겹|구|칸|매|인|호"
# `m`(미터)은 **맨 뒤**에 둔다 — 앞에 두면 `mm`·`ml` 이 `m` 으로 먼저 잘린다.
# 없어서 `인조잔디2m`·`인조잔디25m` 의 규격어가 통째로 안 잡혔다 (2026-08-10 용쌤2-1)
_UNIT_EN = r"(?:cm|mm|ml|kg|l|m)(?![a-z0-9])"
_MATERIALS = ("스테인리스", "스테인레스", "알루미늄", "플라스틱", "실리콘",
              "스텐", "원목", "우드", "가죽", "라탄", "철제")

_SPEC = re.compile(
    rf"(?:\d+\s*(?:{_UNIT_KO}|{_UNIT_EN}))|(?:{'|'.join(_MATERIALS)})", re.I)
_NUM_UNIT = re.compile(rf"^(\d+)\s*({_UNIT_KO}|cm|mm|ml|kg|l|m)$", re.I)

# 숫자 경계 — `3단` 이 `13단` 에, `三层` 이 `十三层` 에 걸리면 안 된다
_LEAD = r"(?<![0-9一二三四五六七八九十百千零〇])"
_CN_DIGIT = "〇一二三四五六七八九"

# 단위별 한중 대응. 같은 값을 가리키는 다른 표기를 한 묶음으로 본다
_UNIT_KO_ALIAS = {"단": ("단", "층", "겹"), "층": ("단", "층", "겹"),
                  "겹": ("단", "층", "겹"),
                  "인": ("인", "인용"), "인용": ("인", "인용")}
_UNIT_CN = {"단": ("层", "段"), "층": ("层", "段"), "겹": ("层", "段"),
            "인": ("人",), "인용": ("人",),
            "구": ("口", "孔"), "칸": ("格",), "매": ("张",), "세트": ("套",),
            "리터": ("升",), "호": ("号",), "인치": ("寸",), "m": ("米",)}
_MAT_KO = {"스텐": ("스텐", "스테인리스", "스테인레스"),
           "스테인리스": ("스텐", "스테인리스", "스테인레스"),
           "스테인레스": ("스텐", "스테인리스", "스테인레스"),
           "원목": ("원목", "우드"), "우드": ("원목", "우드")}
_MAT_CN = {"스텐": ("不锈钢",), "스테인리스": ("不锈钢",), "스테인레스": ("不锈钢",),
           "원목": ("实木", "原木", "橡木", "松木"),
           "우드": ("实木", "原木", "橡木", "松木"),
           "알루미늄": ("铝",), "플라스틱": ("塑料",), "실리콘": ("硅胶",),
           "가죽": ("皮",), "라탄": ("藤",), "철제": ("铁",)}


def _cn_num(n):
    """1~99 아라비아 → 한자. 범위 밖이면 None(변환을 지어내지 않는다)."""
    if not 0 < n < 100:
        return None
    if n < 10:
        return _CN_DIGIT[n]
    if n < 20:
        return "十" + (_CN_DIGIT[n - 10] if n > 10 else "")
    return _CN_DIGIT[n // 10] + "十" + (_CN_DIGIT[n % 10] if n % 10 else "")


def extract(keyword):
    """키워드에서 규격어를 등장 순서대로 뽑는다(중복 제거). 없으면 빈 리스트."""
    out, seen = [], set()
    for m in _SPEC.finditer(keyword or ""):
        tok = m.group(0).lower().replace(" ", "")
        if tok not in seen:
            seen.add(tok)
            out.append(tok)
    return out


def variants(token):
    """규격어 → (한국어 이형 집합, 중국어 이형 집합).

    규칙 6이 한국어 옵션명에서 공통 정보를 지우므로 중국어 원문을 반드시 함께 본다.
    """
    tok = (token or "").lower().replace(" ", "")
    ko, cn = {tok}, set()
    m = _NUM_UNIT.match(tok)
    if m:
        num, unit = m.group(1), m.group(2).lower()
        if unit in _UNIT_KO_ALIAS:                       # 단↔층 · 인↔인용
            ko |= {num + u for u in _UNIT_KO_ALIAS[unit]}
        cn_num = _cn_num(int(num))
        for cu in _UNIT_CN.get(unit, ()):                # 3단 → 3层 · 三层
            cn.add(num + cu)
            if cn_num:
                cn.add(cn_num + cu)
        # 2는 한자로 `二` 말고 **`双`(쌍)** 으로 더 자주 쓴다 — `双层`·`双段`.
        # 한국어 기계번역도 `2단` 을 `이중` 으로 흘린다. 이게 없어서 옵션에 双层/三层/四层
        # 이 나란히 있는 상품(3-2 클린룸 대차)의 `2단` 이 (다)=근거없음으로 떨어졌다.
        # `双` 단독은 넣지 않는다 — `双人`·`双色` 처럼 층수와 무관한 말에 걸린다 (2026-08-07)
        if num == "2" and unit in _UNIT_KO_ALIAS and unit != "인" and unit != "인용":
            ko.add("이중")
            for cu in _UNIT_CN.get(unit, ()):
                cn.add("双" + cu)
        # 원문에 라틴 단위가 그대로 박힌 경우가 흔하다(`长度2m`) — 한자 대응이 있어도
        # 원표기를 같이 넣는다. 한글 단위(`3단`)를 중국어 쪽에 넣어봐야 걸릴 일이 없어 무해.
        cn.add(tok)
    else:
        ko |= set(_MAT_KO.get(tok, ()))
        cn |= set(_MAT_CN.get(tok, ()))
    return ko, cn


def _search(needle, haystack):
    """숫자·한자숫자가 앞에 붙은 경우는 다른 값이다 — `3단` ≠ `13단`."""
    if not haystack:
        return False
    pat = _LEAD + re.escape(needle) if needle[0].isdigit() or needle[0] in _CN_DIGIT + "十" \
        else re.escape(needle)
    # 뒤 경계는 **글자만** 막는다(`2m` ≠ `2mode`). 숫자를 같이 막으면 안 된다 —
    # 호출부가 공백을 지우고 넘기므로 `500kg 7.6m` 이 `500kg7.6m` 으로 붙어,
    # 다음 치수의 첫 숫자가 경계로 오인돼 **멀쩡한 매칭이 통째로 죽는다**.
    # 그래서 500kg 윈치가 (가)가 아니라 (나)로 떨어졌다 (2026-08-10 용쌤2-1).
    # 앞자리 오인(`5kg` ⊂ `25kg`)은 위 `_LEAD` 가 이미 막는다.
    if re.match(r"^\d", needle) and re.search(r"(cm|mm|ml|kg|l|m)$", needle, re.I):
        pat += r"(?![a-z])"
    return re.search(pat, haystack, re.I) is not None


def hit(token, name_ko, name_cn):
    """이 규격어가 이 옵션(또는 이 텍스트)에 해당하나."""
    ko, cn = variants(token)
    k = (name_ko or "").lower().replace(" ", "")
    c = (name_cn or "").replace(" ", "")
    return (any(_search(t, k) for t in ko) or any(_search(t, c) for t in cn))


def classify(token, dims, 상품명="", 원문명=""):
    """규격어가 옵션 차원에서 어떤 위치인가 → ("가"|"나"|"다", 매칭 값키 목록).

    dims: [{"이름":…, "values":[{vid,name,_name}, …]}, …]
    값키는 `option_rules` 와 같은 `@차원인덱스:vid` 규약을 쓴다 — 복합옵션의 판매행 id가
    `3:1`(차원0 vid 3 × 차원1 vid 1) 형태라 vid 하나만으로는 행을 못 찾는다.

    **차원별로** 판정한다. 한 차원 안에서 일부 값만 걸리면 그게 '갈리는 값'(가)이고,
    그 차원의 값 전부가 걸리면 선택지가 아니라 공통 속성(나)이다.
    (값이 1개뿐인 차원은 애초에 선택지가 아니다 — 규칙 17과 같은 취급.)
    """
    split, whole = [], False
    for di, d in enumerate(dims or []):
        vals = d.get("values") or []
        if not vals:
            continue
        m = [f"@{di}:{v.get('vid')}" for v in vals
             if hit(token, str(v.get("name", "")), str(v.get("_name", "")))]
        if not m:
            continue
        if len(m) == len(vals):
            whole = True                        # 이 차원 전체 → 변별값이 아니다
        else:
            split.extend(m)                     # 이 차원을 가르는 값
    if split:
        return "가", split
    if whole or hit(token, 상품명, 원문명):
        # 옵션에 없어도 제목에 있으면 공통 속성 — 규칙 6이 이름에서 지웠을 수 있다
        return "나", []
    return "다", []


def rows_for(keys, rows):
    """`@차원:vid` 값키들에 해당하는 판매행 id 목록.

    판매행 id 는 단일차원이면 `10`, 복합이면 `3:1`(차원0 vid 3 × 차원1 vid 1)이다.
    값키가 가리키는 차원 자리의 vid 가 일치하는 행을 전부 고른다.
    """
    want = set()
    for k in keys or []:
        di, _, vid = str(k).lstrip("@").partition(":")
        if vid:
            want.add((int(di), vid))
    out = []
    for r in rows or []:
        parts = str(r.get("id", "")).split(":")
        if any(di < len(parts) and parts[di] == vid for di, vid in want):
            out.append(r)
    return out


def pick_main(keys, rows, keep=None):
    """(가)일 때 대표 = 매칭 옵션 중 최저가. 가격 없는 행은 후보가 아니다.

    `keep` 을 주면 **유지 집합과 교집합**만 후보로 본다. 규격어 하나에 여러 옵션이
    걸리기 때문이다 — 발단 사례에서 `3단` 은 3층 식기수거카트(35, 유지)에도
    3층 훠궈카트(44, 다른모델로 제외)에도 걸리고, 훠궈 쪽이 더 싸다.
    유지를 모른 채 최저가를 고르면 멀쩡한 상품이 훠궈카트를 대표로 달게 된다.

    교집합이 비면 None — 호출부가 `보류(대표충돌)` 로 처리한다.
    """
    cands = rows_for(keys, rows)
    if keep is not None:
        kept = set(map(str, keep))
        cands = [r for r in cands if str(r.get("id")) in kept]
    cands = [r for r in cands if isinstance(r.get("sale_price"), (int, float))]
    if not cands:
        return None
    return str(min(cands, key=lambda r: r["sale_price"])["id"])


def analyze(keywords, dims, rows, 상품명="", 원문명=""):
    """배치에 실을 `규격후보` 를 만든다 — 스크립트가 계산하고 워커는 확인만 한다.

    `_same_price_options`(run_names.py)와 같은 패턴이다. 워커가 옵션 '가격'과 '전량'을
    볼 수 없으므로 여기서 계산해 넘긴다.
    """
    # 복합옵션은 판매행 id 가 `3:1` 이라 차원별로 vid → 값 을 따로 찾아야 한다
    by_dim = [{str(v.get("vid")): v for v in (d.get("values") or [])} for d in (dims or [])]
    prices = [r.get("sale_price") for r in (rows or [])
              if isinstance(r.get("sale_price"), (int, float))]

    tokens, seen = [], set()
    for kw in (keywords or []):
        for t in extract(kw):
            if t not in seen:
                seen.add(t)
                tokens.append(t)

    축 = []
    for t in tokens:
        판정, keys = classify(t, dims, 상품명, 원문명)
        축.append({"규격": t, "판정": 판정, "값키": keys})

    옵션 = []
    for r in (rows or [])[:OPT_LIST_MAX]:
        parts = str(r.get("id", "")).split(":")
        vs = [by_dim[i].get(p, {}) if i < len(by_dim) else {} for i, p in enumerate(parts)]
        옵션.append({"id": str(r.get("id")),
                     "원문": " · ".join(str(v.get("_name", "")) for v in vs if v),
                     "이름": " · ".join(str(v.get("name", "")) for v in vs if v),
                     "가격": r.get("sale_price"),
                     "제외": bool(r.get("exclude"))})

    return {
        "축분포": " / ".join(f"{d.get('이름', '?')}({len(d.get('values') or [])})"
                          for d in (dims or [])),
        "가격범위": [min(prices), max(prices)] if prices else [],
        "규격축": 축,
        "옵션전량": 옵션,
        # 조용한 절단 금지 — 몇 개를 못 실었는지 워커가 알아야 한다
        "생략": max(0, len(rows or []) - OPT_LIST_MAX),
    }
