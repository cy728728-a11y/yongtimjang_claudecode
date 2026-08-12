#!/usr/bin/env python3
"""해운 특가 요율 계산 — 순수 함수. `references/rate-table.md` 규칙의 코드화.

규칙(2026-08 요금표 실측 199구간 전수검증):
  청구무게 정규화 = 최소 1.0kg, 그 외 0.5kg 단위로 올림
  배송비(원) = 4,000 + 1,600 * 정규화된_청구무게(kg)

100kg 초과에도 같은 식이 그대로 연장된다(실측: 101.0kg → 165,600원과 일치).
그래서 100kg 여부는 계산식을 바꾸지 않고 **경고 표시 여부만** 바꾼다.
"""
import argparse
import json
import math
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

MIN_KG = 1.0
STEP_KG = 0.5
BASE = 4000
PER_KG = 1600
OVER_LIMIT_KG = 100.0


def normalize_weight(kg):
    """실무게·부피무게 중 이미 고른 값을 청구무게로 정규화한다.

    최소 1.0kg, 그 외에는 다음 0.5kg 구간으로 올림.
    """
    if kg is None:
        raise ValueError("무게가 없다")
    kg = float(kg)
    if kg <= 0:
        raise ValueError(f"무게는 양수여야 한다: {kg}")
    if kg <= MIN_KG:
        return MIN_KG
    steps = math.ceil(round(kg / STEP_KG, 6) - 1e-9)
    return round(steps * STEP_KG, 1)


def fee_for_weight(kg):
    """정규화 전 원시 무게 → (정규화무게, 배송비원, 100kg초과여부)."""
    norm = normalize_weight(kg)
    fee = round(BASE + PER_KG * norm)
    return norm, fee, norm > OVER_LIMIT_KG


def billing_weight(actual_kg, volumetric_kg=None):
    """청구무게 = 실무게와 부피무게 중 큰 값. 부피무게 없으면 실무게만 쓴다.

    반환: (청구무게_원시, 판정근거) — 판정근거는 "실무게"/"부피무게"/"실무게(부피무게 미반영)".
    """
    if actual_kg is None:
        raise ValueError("실무게가 없다")
    actual_kg = float(actual_kg)
    if volumetric_kg is None:
        return actual_kg, "실무게(부피무게 미반영)"
    volumetric_kg = float(volumetric_kg)
    if volumetric_kg > actual_kg:
        return volumetric_kg, "부피무게"
    return actual_kg, "실무게"


def quote(actual_kg, volumetric_kg=None):
    """상품 1건의 견적 dict — prep/apply·onestep 이 공통으로 쓰는 산출 형태."""
    raw, basis = billing_weight(actual_kg, volumetric_kg)
    norm, fee, over100 = fee_for_weight(raw)
    return {
        "실무게": round(float(actual_kg), 3),
        "부피무게": round(float(volumetric_kg), 3) if volumetric_kg is not None else None,
        "판정근거": basis,
        "판정무게": round(raw, 3),
        "청구구간": norm,
        "예상배송비": fee,
        "100kg초과": over100,
    }


# ---------------------------------------------------------------------------
# 검증 — 주요 구간이 요금표(references/rate-table.md)와 일치하는지 코드로 고정한다.
# ---------------------------------------------------------------------------
_KNOWN = {
    1.0: 5600, 1.5: 6400, 2.0: 7200, 5.0: 12000, 10.0: 20000, 20.0: 36000,
    30.0: 52000, 40.0: 68000, 50.0: 84000, 60.0: 100000, 70.0: 116000,
    80.0: 132000, 90.0: 148000, 100.0: 164000,
    100.5: 164800, 101.0: 165600, 105.0: 172000,
}


def self_check():
    bad = []
    for kg, expected in _KNOWN.items():
        _, fee, _ = fee_for_weight(kg)
        if fee != expected:
            bad.append((kg, expected, fee))
    return bad


def main():
    ap = argparse.ArgumentParser(description="해운 특가 요율 계산(단건)")
    ap.add_argument("--weight", type=float, required=False, help="실무게(kg)")
    ap.add_argument("--volumetric", type=float, default=None, help="부피무게(kg, 선택)")
    ap.add_argument("--self-check", action="store_true", help="요금표 주요 구간 대조만 하고 종료")
    args = ap.parse_args()

    if args.self_check:
        bad = self_check()
        if bad:
            print("불일치:")
            for kg, exp, got in bad:
                print(f"  {kg}kg: 기대 {exp:,}원, 계산 {got:,}원")
            raise SystemExit(1)
        print(f"OK — {len(_KNOWN)}개 구간 전부 일치")
        return

    if args.weight is None:
        raise SystemExit("--weight 가 필요하다 (또는 --self-check)")
    print(json.dumps(quote(args.weight, args.volumetric), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
