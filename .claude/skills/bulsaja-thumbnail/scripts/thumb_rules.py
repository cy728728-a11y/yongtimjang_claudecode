#!/usr/bin/env python3
"""썸네일 스킬 — **순수 계산** 부분. 불사자도 시트도 부르지 않는다(그래서 테스트가 된다).

역할 분담:
  · 사람/Claude 가 판단 — 어느 후보 이미지를 기준으로 삼을까, 레시피 모드일 때 배경 전략,
    생성본이 제품을 정확히 보존했는가(비전 검수) — 전부 이미지를 봐야 아는 것
  · 이 모듈이 계산 — URL 로 가공 여부 판별·크레딧 예상액·자동반영 여부 감지·재생성 상한·
    검수 페이지에 실을 데이터 조립 (전부 정해진 규칙이라 사람이 다시 판단할 이유가 없다)

핵심 규칙(캘리브레이션 실측, 2026-07-28):
  대표이미지 호스트가 `cdn.bulsaja.com` 이면 가공됨(AI썸네일/AI상세 생성 완료),
  그 외(주로 `img.alicdn.com`)면 미가공 원본. 수집 방식(직접 URL/MCP)은 URL 에 영향 없음
  (동일 원본상품을 두 방식으로 재수집해 대조 확인). 가공됨 판정의 세부 경로(mcp-assets/
  sourcing-product/products/ai-image 등 4종 관측)는 구분하지 않는다 — 호스트만 본다.
"""
import re
from urllib.parse import urlparse

# 가공(불사자 AI 처리) 완료로 보는 호스트. 이 호스트가 아니면(주로 alicdn.com) 미가공 원본.
PROCESSED_HOST = "cdn.bulsaja.com"

# 재생성 상한 — 안(경우)당 최대 2회, 헤르메스 06/07 공통 규칙.
MAX_REGEN = 2

CREDITS_PER_IMAGE = 5

VERDICTS = ("사용가능", "주의", "제외")


def host_of(url):
    """URL 의 호스트(소문자). 빈 값/파싱 실패는 빈 문자열."""
    try:
        return (urlparse(str(url or "")).netloc or "").lower()
    except Exception:
        return ""


def is_processed_url(url):
    """이 URL 1장이 불사자 가공물인가."""
    return host_of(url) == PROCESSED_HOST


def product_status(thumbnails):
    """상품의 현재 대표(0번) 기준 가공 여부. 빈 목록은 '미확인'."""
    if not thumbnails:
        return "미확인"
    return "가공됨" if is_processed_url(thumbnails[0]) else "미가공"


def is_already_done(thumbnails):
    """prep 필터용 — 대표가 이미 가공됐으면 True(대상에서 뺀다)."""
    return product_status(thumbnails) == "가공됨"


def credit_estimate(count, per_image=CREDITS_PER_IMAGE):
    """생성 장수 → 예상 크레딧."""
    return int(count) * per_image


def representative_changed(before, after):
    """자동반영 감지 — 생성 후 재조회한 대표(0번)가 생성 전과 다른가.

    헤르메스 06 §7 경고("생성 완료분이 대표 순서에 자동 반영될 수 있음")의 실측 확인 지점.
    True 면 apply 가 승인 전까지 `before` 순서로 복원해야 한다.
    """
    b0 = before[0] if before else None
    a0 = after[0] if after else None
    return b0 != a0


def can_regenerate(attempts, max_regen=MAX_REGEN):
    """재생성 가능 횟수가 남았는가."""
    return attempts < max_regen


def main_option_of(option):
    """스냅샷 `옵션` → 대표옵션 {이름, 이미지}. 없으면 None. (2026-07-30 이룸님)

    **왜 썸네일이 대표옵션을 알아야 하나**: 네이버는 '대표상품'(추가금 0원인 대표옵션)을
    상품명으로 쓰라고 요구한다 → **썸네일 = 대표옵션 = 상품명**이 한 옵션을 지칭해야 한다.
    상품명·옵션명은 `기본형` 이라는 같은 단어로 짝을 맞추지만(글자), 썸네일은 글자가 없어서
    이 함수로 **대표옵션의 이미지를 기준 이미지로 못박는다.**

    데이터는 이미 있다 — `snapshot.option_model()` 이 `판매행[]` 에 `main_product`(대표
    여부)와 `urlRef`(그 옵션 이미지)를 함께 담고, 옵션정리가 저장 직후 스냅샷을 되쓴다.

    None 을 돌려주는 경우 = 아직 옵션정리를 안 거친 상품(대표 미지정) 또는 옵션 없는
    단일상품. 그때는 호출부가 종전대로 비전 판단으로 폴백한다.
    """
    rows = (option or {}).get("판매행") or []
    main = next((r for r in rows if r.get("main_product")), None)
    if main is None:
        return None
    return {"이름": str(main.get("text") or "").strip(),
            "이미지": str(main.get("urlRef") or "").strip()}


def review_row(pid, name, existing, candidates, generated_url=None, verdict=None,
               reason="", main_option=None):
    """검수 페이지(review.html) 1행 데이터.

    existing   = 재작업 사유 등 반영 전 현재 대표(재조회 값)
    candidates = 원본 후보 목록(existing 제외, alicdn 등 원본들)
    generated_url = 이번에 생성한 결과(아직 미승인)
    verdict    = "사용가능"/"주의"/"제외"/None(대기)
    main_option = `main_option_of()` 결과. **이룸님이 "생성본이 대표옵션과 같은 물건인가"를
                  한눈에 대조하는 재료다** — 없으면 승인 화면에 판단 근거가 빠진다.
    """
    mo = main_option or {}
    return {
        "productId": pid,
        "상품명": name or "",
        "기존대표": existing or "",
        "후보": list(candidates or []),
        "생성본": generated_url or "",
        "판정": verdict,
        "사유": reason or "",
        "대표옵션명": mo.get("이름", ""),
        "대표옵션이미지": mo.get("이미지", ""),
    }


def redo_reason_from_flag(matrix_value):
    """현황판 '재작업(썸네일: 사유)' 값에서 사유만 뽑는다. 못 찾으면 원문 그대로."""
    m = re.match(r"^재작업\(썸네일:\s*(.+)\)$", str(matrix_value or "").strip())
    return m.group(1) if m else str(matrix_value or "")
