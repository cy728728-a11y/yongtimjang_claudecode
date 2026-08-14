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
# 판매행(조합) 상한 — 이보다 많으면 싼 것부터 남기고 자른다(2026-08-05 이룸님).
# 조합이 200개를 넘는 상품은 팔지 않기로 한 정책이다. MCP 배열 상한(200)과도 맞는다.
MAX_SKU_ROWS = 199

# 판매 범위 — 네이버 옵션가는 **기준가(대표가) ±50%** 다(2026-08-05 이룸님 확인).
# 상한 ×1.5 는 그 +50% 쪽이고, 하한 ×0.5 가 -50% 쪽이다.
PRICE_MULTIPLE = 1.5
# 하한은 대표가 최저가이던 시절엔 구조적으로 못 건드렸다(유지 행이 전부 기준가 이상).
# 규격어 대표 지정으로 기준가가 올라갈 수 있게 되면서 실제 가드가 필요해졌다.
PRICE_MULTIPLE_LOW = 0.5
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


# ---------------------------------------------------------------------------
# 옵션 축(선택 항목) 이름 — 규칙 18 (2026-08-04 이룸님)
#
# 축 이름(`prop_name`)은 **불사자 MCP 로 바꿀 수 없다** — `renameValues` 는 값 전용이고
# 축을 가리키는 필드 자체가 없다(불사자 앱 UI 에서 수동으로만 가능. MCP 추가 요청함).
# 그래서 여기서는 **판정만** 하고 저장은 하지 않는다. 결과는 시트 `옵션축` 탭에
# '반영 대기' 원장으로 쌓이고, MCP 가 생기면 그 원장을 그대로 태운다.
#
# 왜 필요한가(용쌤1-2 실측, 681상품·881축):
#   · 축 이름 번역 잔재 25건 — "색상별로 정렬하십시오" / "용량별 정렬" / "제품명"
#   · 축↔값 종류 불일치 90건(10.2%) — 축 "색상"인데 값이 "고속도로 모델 / 철도 모델"
# 원인은 타오바오 `颜色分类` 가 실제로는 **범용 SKU 축**이라 모델·규격·구성이 다 들어오는데
# 기계번역이 "색상"으로 굳혀버리는 것. 마켓에 그대로 나가면 구매자가
# "색상: 고속도로 모델"을 보게 된다.
# ---------------------------------------------------------------------------

# 축 이름 상한 — 값(25자)보다 짧게 잡는다. 축은 속성 이름이라 한두 단어면 끝난다.
AXIS_MAX = 20
# 기계번역 잔재 패턴. `颜色分类`(색상 분류)를 불사자가 문장으로 풀어버린 흔적들.
_AXIS_JUNK = re.compile(r"정렬|하십시오|하세요|하시오|선택하")
# 값이 뭐든 아무 정보가 없는 축 이름 — 완전 일치할 때만 잡는다
# ('종류'·'유형'은 실제로 쓸 만한 축 이름이라 넣지 않는다).
_AXIS_VAGUE = {"옵션", "상품", "제품", "제품명", "분류", "기타", "선택", "옵션명"}
# 색 이름 사전 — 축이 '색'인데 값에 색이 하나도 없는 걸 잡는 **휴리스틱** 용도다.
# 사전에 없는 색(카멜·라벤더 등)이면 헛신호가 날 수 있는데, 이 신호는 기록용이지
# 저장을 막지 않는다. 최종 판단은 워커가 원문을 보고 한다.
_COLOR_WORDS = re.compile(
    r"블랙|화이트|검정|검은|흰|블루|그린|레드|핑크|옐로|그레이|회색|베이지|브라운|퍼플|"
    r"카키|네이비|실버|골드|오렌지|주황|보라|초록|파랑|빨강|노랑|남색|아이보리|버건디|"
    r"민트|투명|무광|유광|은색|금색|하늘색|연두|살구|와인|색")


def axis_problems(name):
    """축 이름 1개의 **기계** 신호 목록. 비어 있으면 기계적으로는 이상 없음."""
    n = str(name or "").strip()
    out = []
    if not n:
        return ["빈 축 이름"]
    if len(n) > AXIS_MAX:
        out.append(f"{len(n)}자(상한 {AXIS_MAX})")
    if re.search(r"[一-鿿]", n):
        out.append("중국어 잔존")
    if _AXIS_JUNK.search(n):
        out.append("번역 잔재")
    if n in _AXIS_VAGUE:
        out.append("의미 없는 축 이름")
    return out


def axis_color_mismatch(dim):
    """축 이름이 '색'인데 값에 색이 하나도 없는가 — `颜色分类` 함정 탐지(휴리스틱).

    타오바오의 범용 SKU 축이 "색상"으로 번역돼 굳는 경우를 잡는다. 값이 하나도 없으면
    판단할 근거가 없으므로 False.
    """
    name = str(dim.get("이름") or "")
    if "색" not in name:
        return False
    vals = [str(v.get("name") or "") for v in (dim.get("values") or [])]
    if not vals:
        return False
    return not any(_COLOR_WORDS.search(v) for v in vals)


def axis_audit(option, proposals=None):
    """축 이름 감사 — [{차원, 현재, 원문, 값예시, 신호[], 제안, 사유}].

    `proposals` = 워커의 `축교정` [{"차원": 0, "제안": "모델", "사유": "…"}].
    **신호가 있거나 제안이 있는 축만** 돌려준다(멀쩡한 축까지 원장에 쌓지 않는다).

    기계가 잡는 것 = 축 이름 자체의 결함(번역 잔재·중국어·길이·무의미) + 색 함정.
    사람(워커)이 잡는 것 = 축 이름이 값의 속성 종류를 실제로 가리키는가.
    """
    prop = {}
    for p in (proposals or ()):
        if not isinstance(p, dict):
            continue
        try:
            gi = int(p.get("차원"))
        except (TypeError, ValueError):
            continue
        prop[gi] = {"제안": str(p.get("제안") or "").strip(),
                    "사유": str(p.get("사유") or "").strip()}

    out = []
    for gi, d in enumerate(option.get("차원") or []):
        cur = str(d.get("이름") or "").strip()
        sig = axis_problems(cur)
        if axis_color_mismatch(d):
            sig.append("색상 축인데 값에 색이 없다")
        pr = prop.get(gi) or {}
        new = pr.get("제안", "")
        if new:
            if new == cur:
                new = ""                       # 같은 이름이면 제안이 아니다
            else:
                sig += [f"제안 축 이름 {p}" for p in axis_problems(new)]
        if not sig and not new:
            continue
        out.append({
            "차원": gi,
            "현재": cur,
            "원문": str(d.get("원문이름") or "").strip(),
            "값예시": [str(v.get("name") or "") for v in (d.get("values") or [])[:4]],
            "신호": sig,
            "제안": new,
            "사유": pr.get("사유", ""),
        })
    return out


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


def normalize_names(names):
    """워커가 준 {키: 이름} 에 규칙 11(정렬용 접두사 제거)을 **강제**한다.

    워커는 기존 이름을 최소 편집하는 경향이 있어서 `A. 750W` 에 마커만 붙여
    `A. 750W 기본형` 을 낸다 — 검사만 하면 사람이 승인할 수 없는 보류만 쌓인다
    (기본형 재작업 92건 중 27건이 이것). 접두사 제거는 판단이 아니라 기계적 변환이라
    검사 전에 여기서 끝낸다. 중복이 생기면 `check_names` 가 잡아 표면에 남는다.
    """
    return {str(k): strip_prefix(v) for k, v in (names or {}).items()}


def with_prefix_cleanup(option, names):
    """`names` 에 빠진 값 중 **정렬용 접두사가 남는 것**만 접두사를 떼어 채운다.

    워커 지시서는 "바꿀 값만 넣어도 된다"인데 저장 후 검사는 표시명 **전체**를 본다.
    그래서 워커가 손댈 이유가 없던 값(값이 하나뿐인 차원 등)에 남은 `A. ` 하나 때문에
    상품이 통째로 실패했다 — 용쌤1-3 실측: 저장 실패 36건 중 32건이 이것.
    접두사 제거는 판단이 아니라 기계적 변환이라(규칙 2) 여기서 메운다.

    키는 위치 지정 키(`@차원:vid`)로 낸다 — vid 는 차원끼리 겹칠 수 있다.
    **`names` 가 비어 있으면 아무것도 하지 않는다** — 이름을 아예 안 바꾸는 상품까지
    쓰기를 늘리지 않으려는 의도적인 범위 제한이다.
    """
    if not names:
        return dict(names or {})
    out = dict(names)
    have = {normalize_key(option, k) for k in names}
    for key, _gi, _vid, cur in value_entries(option):
        if key in have:
            continue
        stripped = strip_prefix(cur)
        if stripped and stripped != str(cur or "").strip():
            out[key] = stripped
    return out


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

    **단 값이 1개뿐인 차원은 건너뛴다**(2026-08-05 이룸님). 고객이 고를 게 없으면 선택
    항목이 아니고, 거기 붙이면 **전 조합**이 그 값을 공유해 마커가 어디서나 보인다.
    타오바오가 `전력 1개(750W)`·`크기 1개(기타)` 같은 빈 축을 달아두는 탓에 흔하다
    (용쌤1-3 재작업 92건 중 49건). 그래서 **값이 2개 이상인 마지막 차원**을 고른다.
    전 차원이 1개짜리면 조합이 하나뿐이라 오염이 성립하지 않아 마지막 차원을 쓴다.
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
    gi = max((i for i, d in enumerate(dims) if len(d.get("values") or []) > 1),
             default=len(dims) - 1)
    key = normalize_key(option, pos_key(gi, parts[gi]))
    if not key:
        return "", f"차원 {gi} 에 vid={parts[gi]} 값이 없다"
    return key, ""


def retarget_base_suffix(option, names, main_key):
    """`기본형` 마커를 확정된 대표로 옮긴다. 바뀐 이름만 담은 dict 를 돌려준다.

    **규격어 대표 지정 전용**(2026-08-05). 워커는 판정 시점에 대표가 누군지 모른다 —
    상품명이 지정한 대표는 최저가가 아닐 수 있고, 그 지정은 `apply` 단계에서야 읽힌다.
    그래서 워커는 종전대로 "유지 중 최저가"에 마커를 붙이고, 대표가 바뀌면 여기서 옮긴다.
    안 옮기면 마커가 옛 대표에 남아 **`보류(기본형)` 으로 전건이 멈춘다**(실측 8건).

    옮기는 것은 기계적이라 판단이 아니다 — 붙일 자리는 이미 `main_key` 로 정해져 있다.
    25자를 넘기면 그대로 두고 `check_names` 가 위반으로 잡게 한다(줄이는 건 사람 몫).
    """
    if not main_key:
        return {}
    eff = effective_names(option, names)
    out = {}
    for k, v in eff.items():
        if k == main_key:
            continue
        if has_base_suffix(v):
            out[k] = str(v).strip()[:-len(BASE_SUFFIX)].strip()
    cur = str(eff.get(main_key, "")).strip()
    if cur and not has_base_suffix(cur):
        # 규칙 16 — 수식어와 붙여쓰지 않는다(`블랙기본형` ✕ / `블랙 기본형` ○)
        out[main_key] = f"{cur} {BASE_SUFFIX}"
    return out


def auto_base_suffix(option, names, main_key):
    """마커를 **기계적으로** 맞춘다 — 대표에 붙이고(누락), 나머지에서 뗀다(오부착).

    붙일 자리는 `main_key` 로 이미 정해져 있다. 그래서 이건 판단이 아니라 기계 작업인데,
    예전엔 규격어 지정이 있는 상품에서만 옮겨서 **워커가 마커를 빠뜨리면 그 상품이 통째로
    `보류(기본형)`** 이 됐다(3-1 w1: 12건 중 5건이 이 사유. 붙일 자리는 스크립트가 아는데
    사람·워커를 한 바퀴 더 돌린 셈이다).

    **못 맞추면 빈 dict** — 25자를 넘기거나 같은 차원에 같은 이름이 생기는 경우다.
    줄이는 건 사람 몫이라 `보류(기본형)` 으로 남겨 부분저장 + 재작업 경로로 보낸다.
    """
    if not main_key:
        return {}
    moved = retarget_base_suffix(option, names or {}, main_key)
    if not moved:
        return {}
    if check_names(moved, groups=pos_groups(option))["위반"]:
        return {}      # 25자 초과 등 — 본문을 줄여야 하고 그건 기계가 못 한다
    # 마커를 떼면 다른 값과 같아질 수 있다(대표 '블랙' + 다른 값 '블랙 기본형').
    # 안 바꾸는 이름까지 합쳐서 같은 차원 안 중복을 본다.
    eff = effective_names(option, apply_base_suffix(option, names, moved))
    if check_names(eff, groups=pos_groups(option))["중복"]:
        return {}
    return moved


def apply_base_suffix(option, names, moved):
    """`names` 에 마커 교정을 병합한다 — **워커가 쓰던 키 자리에 쓴다.**

    교정은 위치키(`@0:1`)로 나오는데 워커는 vid 키(`"1"`)를 쓰기도 한다. 그냥 합치면
    같은 값이 두 키로 들어가 ①`rename_targets` 가 같은 값에 두 번 쓰고
    ②`row_labels`·`name_changes` 는 vid 키만 읽어 **교정 전 이름을 검수표에 보여준다.**
    그래서 같은 값을 가리키는 기존 키가 있으면 그 자리에 덮어쓴다.
    """
    out = dict(names or {})
    by_norm = {}
    for k in out:
        nk = normalize_key(option, k)
        if nk:
            by_norm.setdefault(nk, k)
    for nk, v in moved.items():
        out[by_norm.get(nk, nk)] = v
    return out


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
         multiple=PRICE_MULTIPLE, spec_main=None, spec_keyword=""):
    """정리안을 계산한다. 불사자를 부르지 않는다.

    option    = 스냅샷의 `옵션` (차원·판매행·vid고유)
    keep_ids  = Claude 가 '메인상품'으로 판정해 남긴 판매행 id 집합
    names     = {판매행 id 또는 vid 키: 새 이름} (선택 — 검사에만 쓴다)
    prefer_id = 최저가 동률일 때 Claude 가 고른 id(썸네일 최유사). 없으면 원본 순서.
    spec_main = **상품명 스킬이 규격어로 지정한 대표 판매행 id**(2026-08-05 이룸님).
                최저가가 아니어도 수용한다 — 상품명에 `3단` 이 들어갔으면 대표도 3단이어야
                `상품명 = 대표옵션 = 썸네일` 이 한 물건을 가리킨다. 지정 옵션이 유지 집합에
                없으면 계산하지 않고 `대표충돌` 을 세워 돌려준다(저장 금지).
    spec_keyword = 그 지정의 근거 키워드 — 원장에 남길 용도.

    반환: {대표, 기준가, 상한, 하한, 유지[], 제외[{id,사유}], 순서[], 경고[],
           이름검사, 대표충돌}
    """
    rows = list(option.get("판매행") or [])
    order_of = {r["id"]: i for i, r in enumerate(rows)}
    keep = set(keep_ids or ())
    warn = []

    # ① 메인상품이면서 실제로 팔 수 있는 행만 후보
    cands = [r for r in rows if r["id"] in keep and sellable(r, require_stock)]
    dropped_unsellable = [r for r in rows if r["id"] in keep and not sellable(r, require_stock)]

    result = {"대표": None, "기준가": None, "상한": None, "하한": None, "대표값키": "",
              "유지": [], "제외": [], "순서": [], "경고": warn, "이름검사": None,
              "대표충돌": None}

    for r in rows:
        if r["id"] not in keep:
            result["제외"].append({"id": r["id"], "사유": "비상품/메인상품 아님"})
    for r in dropped_unsellable:
        result["제외"].append({"id": r["id"], "사유": "판매불가(가격 없음 또는 재고 0)"})

    if not cands:
        warn.append("메인상품으로 남길 판매 가능한 옵션이 없다 — 저장하면 안 된다")
        return result

    # ②-a 상품명이 규격어로 지정한 대표가 있으면 그것이 우선이다 — 최저가가 아니어도.
    #      상품명에 `3단` 이 들어갔는데 대표가 2단이면 세 축(상품명·대표옵션·썸네일)이
    #      다른 물건을 가리킨다(발단 = U01KR7VXBA7SF37GR6XHZ9VTVGH).
    main = None
    if spec_main is not None:
        main = next((r for r in cands if r["id"] == str(spec_main)), None)
        if main is None:
            # 워커가 그 옵션을 메인상품이 아니라고 뺐다 → 판단이 갈린다. 규칙으로 못 정한다
            # (제외 8분류는 사유 문자열만으론 '다른모델이 맞다'와 '잘못 뺐다'가 구분 안 된다).
            # 저장하지 않고 사람에게 올린다.
            reason = next((e["사유"] for e in result["제외"]
                           if e["id"] == str(spec_main)), "유지 집합에 없다")
            result["대표충돌"] = {"지정": str(spec_main), "근거키워드": spec_keyword,
                               "사유": reason}
            return result

    # ② 지정이 없으면 최저가 후보 → 동률이면 Claude 가 고른 것 → 그래도 없으면 원본 순서
    if main is None:
        low = min(_price(r) for r in cands)
        tied = [r for r in cands if _price(r) == low]
        if prefer_id and any(r["id"] == prefer_id for r in tied):
            main = next(r for r in tied if r["id"] == prefer_id)
        else:
            if prefer_id and any(r["id"] == prefer_id for r in cands):
                # 더 비싼데 썸네일이 닮았다는 이유로 대표를 올리지 않는다(헤르메스 12 단계4).
                # 규격어 지정(`spec_main`)과 달리 썸네일 유사도는 근거가 약하다.
                warn.append(f"지정한 대표({prefer_id})가 최저가가 아니라 무시했다")
            if len(tied) > 1 and not prefer_id:
                warn.append(f"최저가 동률 {len(tied)}건 — 썸네일 최유사 판단 없이 원본 순서로 정했다")
            main = min(tied, key=lambda r: order_of[r["id"]])

    # ③ 네이버 옵션가 범위 = 기준가 ±50% → 상한 ×1.5 · 하한 ×0.5 (같은 값 포함)
    base = _price(main)
    cap = base * multiple
    floor = base * PRICE_MULTIPLE_LOW

    # ③-b 워커가 미리 뺀 행에 **가격 근거를 되살린다** (2026-08-14 3-2 실측).
    #     `유지` 에는 메인상품 판매행 전부를 넣고 상한 걸러내기는 여기서 하는 게 규칙인데
    #     (워커 프롬프트 §2), 워커가 상한 초과분을 손으로 먼저 빼 오는 일이 잦다. 그러면
    #     사유가 전부 `비상품/메인상품 아님` 으로 뭉개져 **왜 안 파는지가 사라진다**
    #     (실측: 150cm 공원벤치·3x3m 갠트리크레인·270mm 감압지가 전부 '비상품'으로 찍혔다).
    #     무엇을 파느냐는 안 바뀌므로 저장을 막지 않고, 사유에 가격 사실만 덧붙인다.
    #
    #     **상한 초과만 붙인다.** 하한 미만은 붙이지 않는다 — 부속품·사은품은 원래 싸서
    #     하한 아래인 게 정상이고(그래서 ±50% 를 메인상품 확정 뒤에만 적용한다), 거기에
    #     가격 사유를 붙이면 정상 제외를 '워커가 잘못 뺐다'로 읽히게 만든다.
    #     상한 초과는 반대다 — 본품보다 비싼 행은 대개 **같은 제품의 큰 규격**이라,
    #     그게 '비상품' 으로만 적히면 왜 안 파는지가 실제로 사라진다.
    for e in result["제외"]:
        if e["사유"] != "비상품/메인상품 아님":
            continue
        r = next((x for x in rows if x["id"] == e["id"]), None)
        if r is None or _price(r) is None or _price(r) <= cap:
            continue
        e["사유"] += f" · 가격도 1.5배 상한 초과({_price(r):,}원 > {int(cap):,}원)"

    # ④ 범위 안만 유지. 하한은 대표가 최저가가 아닐 때만 실제로 발동한다
    kept = [r for r in cands if floor <= _price(r) <= cap]
    for r in cands:
        if _price(r) > cap:
            result["제외"].append({
                "id": r["id"],
                "사유": f"1.5배 상한 초과({_price(r):,}원 > {int(cap):,}원)"})
        elif _price(r) < floor:
            result["제외"].append({
                "id": r["id"],
                "사유": f"±50% 범위 미만({_price(r):,}원 < {int(floor):,}원)"})

    # ⑤ 판매가 오름차순 (동가는 원본 순서)
    # ⑥ 단 **대표가 전체 맨 앞**이다 — 대표는 고객이 처음 보는 옵션이라
    #    "대표가 정렬 첫 번째"(헤르메스 12 단계4-⑥)가 확인이 아니라 요구사항이다.
    #    규격어 지정으로 대표가 최저가가 아닐 수 있게 되면서(2026-08-05 이룸님) 이 규칙이
    #    "동가 그룹 안에서 맨 앞"에서 "전체 맨 앞"으로 바뀌었다 — 목록 첫 항목의 가격이
    #    튀는 것은 감수한다(유리한 키워드가 우선).
    kept.sort(key=lambda r: (0 if r["id"] == main["id"] else 1, _price(r),
                             order_of[r["id"]]))

    if kept and kept[0]["id"] != main["id"]:
        warn.append(f"대표({main['id']})가 정렬 첫 번째가 아니다 — 계산을 확인해라")

    # ⑦ 판매행 상한 — 조합이 이보다 많으면 싼 것부터 남기고 자른다 (2026-08-05 이룸님).
    #    옵션값이 몇 개 안 돼도 조합은 곱셈으로 불어난다(값 45개 → 조합 464개). 그렇게
    #    많은 조합은 애초에 팔 생각이 없다는 판단이라, 판단이 아니라 정책으로 자른다.
    #    **정렬 뒤에 자른다** — 대표(최저가)가 맨 앞이라 절대 잘려나가지 않는다.
    if len(kept) > MAX_SKU_ROWS:
        for r in kept[MAX_SKU_ROWS:]:
            result["제외"].append({
                "id": r["id"],
                "사유": f"판매행 {MAX_SKU_ROWS}개 제한 초과(가격순 {MAX_SKU_ROWS}개까지)"})
        # **`경고` 가 아니라 별도 필드다.** 경고에 넣으면 상태가 '확인요' 로 떨어져 저장이
        # 막히는데, 자르기는 사람이 볼 문제가 아니라 이미 정해진 정책이다. 잘린 행은 각각
        # `제외` 에 사유가 남고, 미리보기 표의 `유지/전체` 에도 199/1000 로 드러난다.
        result["행제한"] = f"판매행 {len(kept)}개 → {MAX_SKU_ROWS}개로 잘랐다(싼 것부터 유지)"
        kept = kept[:MAX_SKU_ROWS]

    # 대표옵션 마커('기본형')를 붙일 차원 값 — 못 찾으면 경고로 표면화한다(추측 금지)
    main_key, key_err = main_value_key(option, main["id"])
    if key_err:
        warn.append(f"대표옵션 마커를 붙일 값을 못 찾았다 — {key_err}")

    # 마커를 확정된 대표로 맞춘다 — 붙일 자리(main_key)는 이미 정해져 있어 판단이 아니다.
    # 워커는 판정 시점에 규격어 지정을 볼 수 없어 "유지 중 최저가"에 붙여 놓고, 아예
    # 빠뜨리기도 한다. 안 맞추면 그 상품이 통째로 `보류(기본형)` 이 된다(실측 8건 + 5건).
    # 25자를 넘기거나 이름이 겹쳐 기계가 못 맞추는 경우만 보류로 남는다(→ 부분저장·재작업).
    if main_key:
        moved = auto_base_suffix(option, names or {}, main_key)
        if moved:
            names = apply_base_suffix(option, names, moved)
            result["마커이동"] = moved

    result.update({
        "대표": main["id"], "기준가": base, "상한": int(cap), "하한": int(floor),
        "대표값키": main_key,
        "유지": [r["id"] for r in kept], "순서": [r["id"] for r in kept],
    })
    # **이름을 안 바꿔도 마커는 본다.** 예전엔 `if names:` 라 워커가 이름을 하나도 주지
    # 않으면 검사가 통째로 생략됐고, `기본형` 이 아예 없는 상품이 '정리대상'으로 통과해
    # 저장됐다(용쌤1-3 실측 1건). 마커는 상품명과 짝을 이루는 유일한 표식이라 이름 변경
    # 여부와 무관하게 성립해야 한다 — `check_base_suffix` 는 저장된 현재 이름을 본다.
    chk = check_names(names or {}, groups=dim_of(option))
    chk["마커"] = check_base_suffix(option, names or {}, main_key)
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

    # ④ ±50% 범위 재계산 — 저장된 값으로 다시 계산해도 벗어나는 게 없어야 한다
    base = plan_result.get("기준가")
    if base and want_in == got_in:
        over = [i for i in got_in
                if (a_rows[i].get("sale_price") or 0) > base * PRICE_MULTIPLE]
        if over:
            fails.append(f"상한 초과가 판매 중이다: {sorted(over)[:5]}")
        under = [i for i in got_in
                 if (a_rows[i].get("sale_price") or 0) < base * PRICE_MULTIPLE_LOW]
        if under:
            fails.append(f"하한 미만이 판매 중이다: {sorted(under)[:5]}")

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
