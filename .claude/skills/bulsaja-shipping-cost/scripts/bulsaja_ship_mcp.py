#!/usr/bin/env python3
"""불사자 MCP — 배송비 스킬 고유 도구(shipping_cost_recommend·price_update)만 얹는다.

transport(open/list_tools/call_tool/close)와 상품 공통 조회(workdata)는
eroomlib.snapshot.ProductMCP 에서 상속한다 — 스킬-계약(_shared/스킬-계약.md) 그대로.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_d = _HERE
while _d and _d != os.path.dirname(_d):
    _lib = os.path.join(_d, "lib")
    if os.path.isdir(os.path.join(_lib, "eroomlib")):
        if _lib not in sys.path:
            sys.path.insert(0, _lib)
        break
    _d = os.path.dirname(_d)

from eroomlib.snapshot import ProductMCP as _BaseMCP  # noqa: E402


class ShippingMCP(_BaseMCP):
    """workdata()는 상속. 여기서는 배송비 추천·가격변경(overseaFee)만 얹는다."""

    def shipping_recommend(self, product_id):
        """읽기 전용 — 인공지능이 이미지·상품명으로 추천한 무게/포장/배송비.

        반환 원본을 그대로 준다(필드명은 도구 응답 그대로) — 스크립트는 이걸
        Claude(run 단계)에게 증거로 넘길 뿐, 여기서 임의 해석하지 않는다.
        """
        return self.call_tool("bulsaja_shipping_cost_recommend",
                              {"productId": product_id})

    def price_preview_oversea(self, product_id, new_fee):
        """confirm=False — 해외배송비 변경 미리보기(저장하지 않음, 확인 토큰 받기)."""
        return self.call_tool("bulsaja_price_update", {
            "mode": "overseaFee", "productId": product_id,
            "newFee": int(new_fee), "confirm": False,
        })

    def price_commit_oversea(self, product_id, new_fee, token):
        """confirm=True + 토큰 — 실제 저장(옵션 판매가 차액 자동 반영)."""
        return self.call_tool("bulsaja_price_update", {
            "mode": "overseaFee", "productId": product_id,
            "newFee": int(new_fee), "confirm": True,
            "confirmationToken": token,
        })


if __name__ == "__main__":
    import argparse
    import json

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="배송비 MCP 단건 점검")
    ap.add_argument("--pid", required=True)
    ap.add_argument("--recommend", action="store_true")
    args = ap.parse_args()

    mcp = ShippingMCP()
    mcp.open()
    try:
        if args.recommend:
            print(json.dumps(mcp.shipping_recommend(args.pid), ensure_ascii=False, indent=2))
    finally:
        mcp.close()
