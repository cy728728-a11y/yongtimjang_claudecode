# -*- coding: utf-8 -*-
"""옵션 이미지 스킬의 순수 규칙 (네트워크 없음 — 테스트 대상).

- 판매 중 옵션 추리기 (exclude=false 만)
- 기작업 판별 (우리가 올린 이미지인지: cdn.bulsaja.com 의 mcp-assets 경로)
- spec.json 검증 + 옵션별 프롬프트 조립
"""
import re

# 우리가 업로드 티켓으로 올린 이미지는 항상 이 경로 조각을 갖는다 (실측 2026-09-16)
DONE_MARKER = "/mcp-assets/"
# 불사자가 자동 번역해 둔 옵션 이미지 (글자가 깨져 있을 수 있어 소스로 쓰기 전 눈으로 본다)
TRANSLATED_MARKER = "/translated-images/"

PROMPT_HEAD = (
    "Use the attached product photo as the exact reference. "
    "Do NOT redesign, restyle, or change the product's shape, proportions, parts, colors, or materials "
    "in any way - this must remain the identical physical {product_desc}{angle_clause}. "
    "Keep it a clean e-commerce studio product shot on a {background} background, no clutter, "
    "no Chinese brand logo, no watermark, and no Chinese text anywhere. "
    "Overlay clean Korean sans-serif text only (no Chinese characters): "
)
PROMPT_TAIL = "All Korean text spelling must be exactly correct and crisp."
DEFAULT_BACKGROUND = "soft light blue gradient"
DEFAULT_ANGLE = ""   # 빈 문자열 = 앵글 지시 없음 (원본 앵글 유지)


def classify_image(url):
    """옵션 이미지 주소 → '기작업' | '번역본' | '원본' | '없음'."""
    if not url:
        return "없음"
    if DONE_MARKER in url:
        return "기작업"
    if TRANSLATED_MARKER in url:
        return "번역본"
    return "원본"


def sale_options(workdata):
    """workdata(bulsaja_product_workdata 응답의 data) → 판매 중 옵션 목록.

    1차원 옵션만 다룬다(복합옵션은 vid 가 차원마다 겹쳐 이 스킬 범위 밖 — SKILL.md 참조).
    반환: [{vid, name, name_cn, image_url, sku_id, status}]
    """
    props = (workdata or {}).get("uploadSkuProps") or {}
    main = props.get("mainOption") or {}
    sub = props.get("subOption") or []
    if sub:
        raise ValueError("복합옵션(선택 항목 2개 이상) 상품은 이 스킬이 다루지 않는다")
    skus = {str(s.get("id")): s for s in ((workdata or {}).get("uploadSkus") or [])}
    out = []
    for v in main.get("values") or []:
        if v.get("exclude"):
            continue
        vid = str(v.get("vid"))
        url = v.get("imageUrl") or ""
        sku = skus.get(vid, {})
        out.append({
            "vid": vid,
            "name": v.get("name") or "",
            "name_cn": v.get("_name") or "",
            "image_url": url,
            "price_tab_url": sku.get("urlRef") or "",   # 가격탭 이미지 (vid 교체 시 같이 바뀜)
            "sku_id": sku.get("id") or vid,
            "status": classify_image(url),
        })
    return out


def detail_image_urls(workdata):
    """상세페이지 HTML 에서 이미지 주소만 뽑는다 (스펙 근거 확인용)."""
    html = ((workdata or {}).get("uploadDetailContents") or {}).get("renderContent") or ""
    return re.findall(r'src="([^"]+)"', html)


VALID_SIZES = ("1024x1024", "1024x1536", "1536x1024")


def image_size(spec):
    """spec.size — 없으면 정방형. 허용 밖 값은 ValueError."""
    s = (spec.get("size") or "1024x1024").strip()
    if s not in VALID_SIZES:
        raise ValueError(f"size 는 {', '.join(VALID_SIZES)} 중 하나여야 한다: {s}")
    return s


def validate_spec(spec, options):
    """spec.json 구조 검증. 문제 목록(빈 리스트면 통과) 반환.

    spec = {
      "product_desc": "stainless steel beverage dispenser",   # 필수, 영어 한 구절
      "background": "...",                                     # 선택
      "angle": "...",                                          # 선택 (영어 지시문)
      "common_texts": ["Left side vertical measurement line: \"높이 58CM\"", ...],  # 선택
      "options": {"2": {"banner": "단일 헤드 8리터 - 두꺼운 유형 - 실버", "source": "<url|path>"}}  # 필수
    }
    """
    problems = []
    if not isinstance(spec, dict):
        return ["spec 이 객체가 아니다"]
    if not (spec.get("product_desc") or "").strip():
        problems.append("product_desc(제품 영어 설명) 가 비어 있다")
    opts = spec.get("options")
    if not isinstance(opts, dict) or not opts:
        problems.append("options 가 비어 있다 — 최소 1개 옵션(vid) 필요")
        return problems
    known = {o["vid"] for o in options}
    for vid, o in opts.items():
        if str(vid) not in known:
            problems.append(f"옵션 {vid}: 판매 중 옵션 목록에 없다 (판매 제외거나 없는 번호)")
        if not isinstance(o, dict) or not (o.get("banner") or "").strip():
            problems.append(f"옵션 {vid}: banner(하단 띠 문구) 가 비어 있다")
        if o and re.search(r"[一-鿿]", o.get("banner") or ""):
            problems.append(f"옵션 {vid}: banner 에 한자가 들어 있다")
    for t in spec.get("common_texts") or []:
        if re.search(r"[一-鿿]", t):
            problems.append(f"common_texts 에 한자가 들어 있다: {t[:30]}")
    try:
        image_size(spec)
    except ValueError as e:
        problems.append(str(e))
    return problems


def build_prompt(spec, vid):
    """spec + 옵션 번호 → gpt-image-2 편집 프롬프트 한 줄."""
    o = spec["options"][str(vid)]
    angle = (spec.get("angle") or DEFAULT_ANGLE).strip()
    angle_clause = f", just photographed {angle}" if angle else ""
    head = PROMPT_HEAD.format(
        product_desc=spec["product_desc"].strip(),
        angle_clause=angle_clause,
        background=(spec.get("background") or DEFAULT_BACKGROUND).strip(),
    )
    items = [f'Bottom banner: "{o["banner"].strip()}"'] + [t.strip() for t in spec.get("common_texts") or []]
    body = " ".join(f"{i}) {t}" for i, t in enumerate(items, 1))
    return f"{head}{body} {PROMPT_TAIL}"


def source_for(spec, option):
    """옵션의 생성 소스(원본 이미지) — spec 에 source 가 있으면 그것, 없으면 현재 옵션 이미지."""
    return (spec["options"][option["vid"]].get("source") or "").strip() or option["image_url"]


def plan_targets(spec, options, force=False):
    """spec 에 적힌 옵션 중 실제로 생성할 대상과 건너뛸 대상을 나눈다.

    기작업(이미 우리가 올린 이미지)은 force 가 아니면 건너뛴다.
    반환: (targets, skipped) — 각 원소는 (option, 사유)
    """
    by_vid = {o["vid"]: o for o in options}
    targets, skipped = [], []
    for vid in spec["options"]:
        o = by_vid.get(str(vid))
        if not o:
            skipped.append(({"vid": str(vid), "name": ""}, "판매 중 옵션 아님"))
            continue
        if o["status"] == "기작업" and not force and not spec["options"][str(vid)].get("source"):
            skipped.append((o, "기작업(이미 교체됨) — 다시 하려면 --force 또는 source 지정"))
            continue
        targets.append((o, ""))
    return targets, skipped
