#!/usr/bin/env python3
"""배송비 계산 — 오픈차이나 VIP 기본요금 · 국내 할증 · 경동비(택배 기준).

**여기가 요금 산식의 정본이다.** 워커는 무게·부피만 추정하고 금액은 만들지 않는다
(사람이 승인하는 건 금액인데, 금액을 판단이 만들면 같은 무게가 매번 다른 요금이 된다).

규칙 원문 = `references/배송비-기준.md`.
"""
import json
import math
import os

# ---------------------------------------------------------------------------
# 오픈차이나 무게 요율 — **실측으로 교정된 값이다** (2026-08-12, 표본 60건 불일치 0)
# ---------------------------------------------------------------------------
# 요금은 1kg 부터 시작하고 0.5kg 단위로 올림한다. 올림은 오픈차이나가 직접 하고
# (실무게 6.6kg → 측정무게 7.0kg), **그 `측정무게`가 과금 기준**이다.
#
# 이룸님 가이드 문서는 `5,600 + 800/0.5kg` 이었는데 실측은 `5,500 + 750/0.5kg` 이다.
# 26개 무게(1.0~38.0kg) 전부가 아래 식으로 재현된다 — `오픈차이나-실측.json` 참조.
# 가이드 값으로 두면 10kg 에서 1,000원이 과대 계상된다.
BASE_KG = 1.0
BASE_FEE = 5500
STEP_KG = 0.5
STEP_FEE = 750

# 부대비용(포장비·할증) — **요율에 더한다.** 이게 실제 청구액의 19%(중앙)를 차지한다.
#
# 이룸님 지적(2026-08-12): "포장비가 붙는다. **파손 위험이 높을수록 포장비가 커진다.**"
# 실측이 그걸 확인했다 — 60건 중 52건(87%)에 부대비용이 붙었고, 항목이 곧 파손 대비다:
# 외부포장(48건·중앙 3,600) · 한진택배 할증료(27건) · 박스교체(6건·중앙 5,000) ·
# 멀티포장 · 모서리 보호대 · 내부포장 · 돼지코.
#
# 무게↔부대비용 상관 r=0.82 라 **무게가 1차 예측자**이고, 파손위험이 같은 무게 안에서
# 갈리는 축이다. 그래서 무게 구간별 실측 분위수를 위험도에 매핑한다(회귀식 대신 분위수를
# 쓰는 이유: 표본 60건에서 잔차가 ±2,400원이라 구간 안 분포를 그대로 쓰는 편이 정직하다).
#
#   (구간 상한kg(미만), (낮음=25%, 중간=중앙, 높음=75%))
PACKING = (
    (2.0, (0, 0, 1500)),
    (5.0, (2500, 3100, 3100)),
    (10.0, (3600, 3700, 4000)),
    (20.0, (4800, 5900, 11200)),
    (None, (11400, 13700, 13800)),
)
RISK_LEVELS = ("낮음", "중간", "높음")
DEFAULT_RISK = "중간"

# 국내 추가 할증(이룸님 가이드 §5 표) — **금액으로 쓰지 않는다.**
# 실측에서 `한진택배 할증료` 는 위 부대비용에 이미 섞여 들어와 있어, 여기 값을 또 더하면
# 이중 계상이다. 검수표에 "이 무게면 할증 구간이 여기다"를 보여주는 설명용으로만 남긴다.
# (무게하한kg, 무게상한kg, 세변합하한cm, 세변합상한cm, 금액)
SURCHARGE = (
    (2.0, 4.5, 80, 100, 600),
    (5.0, 9.5, 100, 120, 1200),
    (10.0, 14.5, 120, 140, 2800),
    (15.0, 20.0, 140, 160, 3000),
)

# 세변합(가로+세로+높이)이 이 값을 넘으면 일반 택배 규격 밖 → 경동/화물 인계 가능성.
CARGO_GIRTH_CM = 160

# 지역이 안 정해졌을 때 쓰는 보수적 인상율(기준 문서 §7).
DEFAULT_REGION_RATE = 0.25

RATE_TABLE_PATH = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "references", "경동-표준운임.json"))


def billable_kg(kg):
    """청구무게 = max(1.0kg, 실제무게를 0.5kg 단위로 올림).

    부동소수 오차 방지로 나눈 몫을 6자리에서 반올림한 뒤 올린다
    (`2.0/0.5` 는 정확히 4.0 이지만 `1.1/0.5` 는 2.2000000000000006 이다).
    """
    if kg is None:
        return None
    kg = float(kg)
    if kg <= BASE_KG:
        return BASE_KG
    steps = math.ceil(round(kg / STEP_KG, 6))
    return round(steps * STEP_KG, 1)


def rate_fee(kg):
    """무게 요율만(부대비용 제외). 실측 60건이 이 식으로 재현된다. 무게 없으면 None."""
    b = billable_kg(kg)
    if b is None:
        return None
    return int(BASE_FEE + round((b - BASE_KG) / STEP_KG) * STEP_FEE)


# 옛 이름. 요율에 부대비용이 안 들어간다는 걸 이름이 숨겨서 바꿨다(2026-08-12).
vip_fee = rate_fee


def packing_fee(kg, risk=DEFAULT_RISK):
    """부대비용(포장·할증) 예상액. 무게 구간 × 파손위험 → 실측 분위수.

    `risk` 가 셋 중 하나가 아니면 `중간` 으로 본다 — 워커가 낯선 값을 내도 계획이
    멈추지 않아야 하고, 중간은 실측 중앙값이라 가장 덜 틀리는 기본값이다.

    2kg 미만 `낮음`·`중간` 이 0원인 건 오타가 아니다 — 실측 12건 중 절반 이상이
    부대비용 0원이었다(소형·가벼운 물건은 그냥 봉투로 나간다).
    """
    if kg is None:
        return None
    idx = RISK_LEVELS.index(risk) if risk in RISK_LEVELS else RISK_LEVELS.index(DEFAULT_RISK)
    kg = float(kg)
    for upper, tiers in PACKING:
        if upper is None or kg < upper:
            return tiers[idx]
    return PACKING[-1][1][idx]


def total_fee(kg, risk=DEFAULT_RISK):
    """제안 배송비 = 무게 요율 + 부대비용 예상."""
    r = rate_fee(kg)
    if r is None:
        return None
    return r + (packing_fee(kg, risk) or 0)


def surcharge(kg=None, girth_cm=None):
    """국내 추가 할증 (금액, 근거). 해당 없으면 (0, "").

    무게 구간과 세변합 구간 중 **높은 쪽**을 쓴다 — 택배사가 둘 중 큰 기준으로 매긴다.
    반환 금액은 안내용이다. `vip_fee` 에 더하지 않는다.
    """
    best, why = 0, []
    for lo_kg, hi_kg, lo_cm, hi_cm, amount in SURCHARGE:
        hit = []
        if kg is not None and lo_kg <= float(kg) <= hi_kg:
            hit.append(f"{lo_kg}~{hi_kg}kg")
        if girth_cm is not None and lo_cm <= float(girth_cm) <= hi_cm:
            hit.append(f"{lo_cm}~{hi_cm}cm")
        if hit and amount > best:
            best, why = amount, hit
    # 표 상한을 넘는 건 표에 없다 — 0 으로 두면 "할증 없음"으로 읽히므로 구분해 적는다.
    if not best and ((kg is not None and float(kg) > 20)
                     or (girth_cm is not None and float(girth_cm) > 160)):
        return 0, "할증표 범위 밖(20kg/160cm 초과) — 배대지 실측 확인"
    return best, (" · ".join(why) if best else "")


def girth(dims):
    """[가로, 세로, 높이] → 세변합(cm). 셋이 다 있어야 계산한다."""
    if not dims or len(dims) != 3:
        return None
    try:
        vals = [float(d) for d in dims]
    except (TypeError, ValueError):
        return None
    return round(sum(vals), 1) if all(v > 0 for v in vals) else None


def volume_cm3(dims):
    """[가로, 세로, 높이] → 부피(㎤)."""
    if not dims or len(dims) != 3:
        return None
    try:
        vals = [float(d) for d in dims]
    except (TypeError, ValueError):
        return None
    if not all(v > 0 for v in vals):
        return None
    return round(vals[0] * vals[1] * vals[2])


def load_rate_table(path=None):
    """경동 택배 표준운임표. 없거나 비어 있으면 None.

    기준 문서 §8 — 구간표가 길어 md 에 박제하지 않는다. 이 JSON 이 있으면 금액을
    계산하고, 없으면 **판정만** 하고 금액 자리에 `확인필요` 를 남긴다.
    """
    p = path or RATE_TABLE_PATH
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            t = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if not (t.get("부피구간") or t.get("무게구간")):
        return None
    return t


def _bracket(table, value):
    """[[상한, 운임], ...] 오름차순에서 value 이하의 첫 구간 운임. 없으면 None."""
    for upper, fare in table:
        if value <= upper:
            return fare
    return None


def kyungdong(kg=None, dims=None, region_rate=DEFAULT_REGION_RATE, table=None):
    """경동비(화물택배 인계 예상) — **택배 표 기준**. 정기화물 열은 쓰지 않는다.

        A운임 = 부피구간 택배 표준운임 × (1 + 지역인상율)
        B운임 = 무게구간 택배 표준운임 × (1 + 지역인상율)
        경동비 = max(A, B), 100원 단위 반올림

    반환 (금액 또는 None, 근거문자열).
    """
    table = table if table is not None else load_rate_table()
    if not table:
        return None, "표준운임표 미보유 — 배대지 최신 고시표 확인 필요"
    vol = volume_cm3(dims)
    # **부피가 없으면 금액을 만들지 않는다** (2026-08-13). 무게 기준(B운임)만으로는
    # 장척을 못 잡는다 — 1.9m 정원 풍차가 3kg 이라 3,800원이 나왔는데, 실제 경동비
    # 중앙값은 13,000원이다. 화물로 넘어가는 이유가 대개 **길이·부피**라서, 무게만
    # 있는 상태의 계산은 "모른다"가 아니라 **틀린 금액을 자신 있게 내놓는 것**이다.
    if vol is None:
        return None, "부피 미상 — 무게 기준만으로는 장척을 못 잡는다(세 변 필요)"
    a = _bracket(table.get("부피구간") or [], vol)
    b = _bracket(table.get("무게구간") or [], float(kg)) if kg is not None else None
    if a is None and b is None:
        return None, "부피·무게 모두 구간 밖 — 실측 확인 필요"
    picks = []
    if a is not None:
        picks.append(("A(부피)", a * (1 + region_rate)))
    if b is not None:
        picks.append(("B(무게)", b * (1 + region_rate)))
    label, amount = max(picks, key=lambda x: x[1])
    # 100원 단위 반올림. `round()` 는 은행가 반올림이라 11,250 을 11,200 으로 내린다 —
    # 돈은 half-up 이 상식이므로 floor(x+0.5) 로 올린다.
    return int(math.floor(amount / 100.0 + 0.5) * 100), \
        f"{label} 채택 · 인상율 {int(region_rate * 100)}%"


# ---------------------------------------------------------------------------
# 워커 결과 → 상품 1건의 배송비 계획
# ---------------------------------------------------------------------------

# 상태값. `완료`·`변경없음` 만 저장 대상이고 나머지는 사람 큐다.
S_OK = "완료"
S_SAME = "변경없음"
S_NO_WEIGHT = "보류(무게없음)"
S_LOW_CONF = "보류(신뢰도)"
S_DELTA = "보류(변경폭)"


def _weight_groups(entry):
    """워커의 `무게군` 을 [(kg, [판매행id...]), ...] 로 정규화. 잘못된 항목은 버린다."""
    out = []
    for g in (entry.get("무게군") or []):
        if not isinstance(g, dict):
            continue
        try:
            kg = float(g.get("kg"))
        except (TypeError, ValueError):
            continue
        if kg <= 0:
            continue
        rows = [str(r) for r in (g.get("행") or []) if str(r).strip()]
        out.append((kg, rows))
    return out


def plan_product(entry, current_fee=0, main_sku_id=None, max_delta=None,
                 region_rate=DEFAULT_REGION_RATE, table=None):
    """워커 결과 1건 → 계획 dict.

    `적용무게` 는 **판매 옵션 중 최대**다(2026-08-11 기본값 — 무거운 옵션이 팔릴 때
    마진이 깎이는 사고를 막는다). `대표기준` 도 같이 계산해 시트에 병기하므로,
    이룸님이 대표 기준으로 바꾸고 싶으면 시트에서 바로 대조할 수 있다.
    """
    groups = _weight_groups(entry)
    risk = str(entry.get("파손위험") or "").strip()
    if risk not in RISK_LEVELS:
        risk = DEFAULT_RISK
    p = {
        "productId": entry.get("productId", ""),
        "실물": str(entry.get("실물") or "")[:80],
        "무게근거": str(entry.get("무게근거") or "")[:200],
        "신뢰도": str(entry.get("신뢰도") or ""),
        "파손위험": risk,
        "메모": str(entry.get("메모") or "")[:200],
        "현재배송비": int(current_fee or 0),
        "적용무게": None, "청구무게": None, "제안배송비": None, "차액": None,
        "요율": None, "포장비": None,
        "대표무게": None, "대표배송비": None,
        "할증": 0, "할증근거": "", "세변합": None, "화물": "",
        "경동비": None, "경동근거": "",
        "상태": S_NO_WEIGHT,
    }
    if not groups:
        return p

    # 적용 = 최대 무게. 대표 = 대표 판매행이 속한 군(없으면 최소 무게군 = 통상 최저가 옵션).
    p["적용무게"] = max(kg for kg, _ in groups)
    rep = None
    if main_sku_id:
        for kg, rows in groups:
            if str(main_sku_id) in rows:
                rep = kg
                break
    if rep is None:
        rep = min(kg for kg, _ in groups)
    p["대표무게"] = rep
    p["대표배송비"] = total_fee(rep, risk)

    p["청구무게"] = billable_kg(p["적용무게"])
    p["요율"] = rate_fee(p["적용무게"])
    p["포장비"] = packing_fee(p["적용무게"], risk)
    p["제안배송비"] = p["요율"] + p["포장비"]
    p["차액"] = p["제안배송비"] - p["현재배송비"]

    dims = entry.get("부피cm")
    g = girth(dims)
    if g is None:
        try:
            g = float(entry.get("세변합")) if entry.get("세변합") else None
        except (TypeError, ValueError):
            g = None
    p["세변합"] = g
    p["할증"], p["할증근거"] = surcharge(p["적용무게"], g)

    # 화물 판정 — 워커 신고와 세변합을 OR 로 본다. 둘 중 하나만 걸려도 확인 대상이다.
    worker_cargo = str(entry.get("화물가능성") or "").strip()
    if worker_cargo in ("높음", "의심") or (g is not None and g >= CARGO_GIRTH_CM):
        p["화물"] = worker_cargo or f"세변합 {g}cm"
        p["경동비"], p["경동근거"] = kyungdong(p["적용무게"], dims, region_rate, table)

    # 게이트 — 순서가 곧 우선순위다. 신뢰도가 낮으면 금액을 못 믿으므로 변경폭보다 먼저 본다.
    if p["신뢰도"] == "낮음":
        p["상태"] = S_LOW_CONF
    elif p["제안배송비"] == p["현재배송비"]:
        p["상태"] = S_SAME
    elif max_delta is not None and abs(p["차액"]) > max_delta:
        p["상태"] = S_DELTA
    else:
        p["상태"] = S_OK
    return p


def savable(p):
    """불사자에 저장할 계획인가. `변경없음` 은 저장할 게 없으므로 제외한다."""
    return p.get("상태") == S_OK
