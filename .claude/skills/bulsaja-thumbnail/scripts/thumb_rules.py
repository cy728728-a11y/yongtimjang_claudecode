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

# 가공(불사자 AI 처리) 완료로 보는 호스트. 여기 없으면(주로 alicdn.com) 미가공 원본.
#   · cdn.bulsaja.com — 불사자가 저장한 가공물
#   · fal.media       — 불사자 AI 생성 엔진이 직접 내주는 출력. **서브도메인으로 온다**
#                       (관측: `v3b.fal.media`). 2026-08-15 25-2 에서 101건이 "미가공
#                       원본"으로 분류돼 재생성 대상이 됐다 — 실제로는 이미 AI 생성본이라
#                       505크레딧을 헛쓸 뻔했다. 게다가 이 군의 정합검사 불일치율은
#                       42.6%(43/101)로 cdn 군 35.3%(65/184)보다 **나쁘다** — 놓치면
#                       불량한 생성본이 audit 없이 통과한다.
PROCESSED_HOSTS = ("cdn.bulsaja.com", "fal.media")

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
    """이 URL 1장이 불사자 가공물인가. **서브도메인도 인정한다**(`v3b.fal.media`)."""
    host = host_of(url)
    return any(host == h or host.endswith("." + h) for h in PROCESSED_HOSTS)


def product_status(thumbnails):
    """상품의 현재 대표(0번) 기준 가공 여부. 빈 목록은 '미확인'."""
    if not thumbnails:
        return "미확인"
    return "가공됨" if is_processed_url(thumbnails[0]) else "미가공"


def is_already_done(thumbnails):
    """prep 필터용 — 대표가 이미 가공됐으면 True(대상에서 뺀다)."""
    return product_status(thumbnails) == "가공됨"


# 정합검사(audit) 판정값. 대조불가는 재작업이 아니다 — 별도 집계만.
AUDIT_MATCH = "일치"
AUDIT_MISMATCH = "불일치"
AUDIT_UNCOMPARABLE = "대조불가"
# 대표옵션 쪽이 실물(본품)이 아닌 것으로 보일 때 — 썸네일이 아니라 옵션 단계로 되돌린다
# (2026-08-06 캠핑박스/걸이판 실증: 옵션정리가 부속을 본품으로 오인해 대표를 세웠고,
#  썸네일 재생성·원본 fallback 은 둘 다 부속 기준이라 교정이 아니다).
AUDIT_MAIN_SUSPECT = "대표옵션의심"
# 대표옵션 이미지가 **제품 사진이 아니라서**(치수도면·경고배너·색상칩) 대조 기준 자체가
# 안 서는 것 — 생성본이 맞는지 틀린지 판정할 근거가 없다. 이것도 뿌리는 옵션이다:
# 대표옵션을 **실물 사진이 있는 값으로 다시 세워야** 풀린다. 재생성·fallback 은 둘 다
# 같은 비제품 기준을 다시 쓰는 것이라 교정이 아니다.
# (2026-08-07 이룸님: "아예 대표옵션 새로 정하는 걸로, 옵션 단계로 돌아가서 다시 하는 걸로
#  자동화하자" — 3-2 실측 2건: 식탁조명=치수도면 · 통기타='假' 경고배너)
VERDICT_NO_BASE = "기준이미지없음"
# 썸네일이 아니라 **옵션 단계로 되돌릴** 판정값 2종. 둘 다 대표옵션 자체가 뿌리다.
TO_OPTION_VERDICTS = (AUDIT_MAIN_SUSPECT, VERDICT_NO_BASE)

# 옵션이 **되돌려 보낸** 신호 — "실물 이미지가 있는 옵션이 하나도 없다"(2026-08-07 이룸님).
# 옵션 워커가 이관 사유에 이 낱말을 넣는다(`옵션-워커-프롬프트.md` §2-10).
#
# **왜 필요한가 — 이게 왕복의 종결 상태다.** 썸네일→옵션 이관(`기준이미지없음`·`실물없음`)은
# 옵션이 대표를 실물로 다시 세우면 풀린다. 그런데 **옵션 이미지가 전부 비제품인 상품이
# 실재한다**(3-2 실측 57건 중 고유 옵션이미지 1장짜리 3건). 그 상품은 옵션이 아무리 다시
# 세워도 실물이 없어서 `prescreen` 이 또 `실물없음` 을 내고 → 무한 왕복이 된다.
# 이 낱말이 붙어 오면 prep 이 **선기록하지 않고 비전 배치로 보낸다** — 썸네일 워커가
# 후보 이미지에서 고르게 해서 왕복을 **1회로 끝낸다**. 카운터가 따로 필요 없다.
NO_REAL_BASE = "실물기준없음"


def no_real_base(redo_reason):
    """재작업사유가 '옵션에 실물 이미지가 없다'는 되돌림인가."""
    return NO_REAL_BASE in str(redo_reason or "")


# `fallback`(대표옵션 원본대체)이 **이미 종결한** 상품의 판정값. 이후 `apply --commit`
# 이 이 값을 보면 손대지 않고 지나간다.
#
# **왜 필요한가** (2026-08-15 용쌤2-1 실측 — 조용한 되감기): 판정 큐를 `fallback` →
# `apply --commit` 순서로 처리했더니 현황판 완료가 **658 → 628 로 떨어졌다.**
# `완료(원본대체·대표옵션)` 19건이 `보류(제외)` 로 되돌아간 것이다. 원인은
# `fallback` 이 현황판만 고치고 `decisions.json` 의 판정은 `제외` 인 채로 남긴 것 —
# 나중에 커밋이 돌면 `decisions.json` 을 정본으로 현황판을 되쓰므로 그 `제외` 가
# 다시 이긴다. **에러도 경고도 없다.** 그래서 fallback 이 판정을 이 값으로 덮어쓰고,
# 커밋은 이 값을 종결로 인정한다 — 순서가 어느 쪽이든 되감기지 않는다.
VERDICT_FALLBACK = "원본대체"
FINAL_VERDICTS = (VERDICT_FALLBACK,)


def is_final(verdict):
    """`apply --commit` 이 손대면 안 되는, 이미 종결된 판정인가."""
    return any(v in str(verdict or "") for v in FINAL_VERDICTS)


def heal_pid(pid, valid):
    """워커가 **이미지 파일명에서 베낀** 상품코드를 정본으로 되돌린다. 못 고치면 None.

    `materialize_image` 가 파일명을 24자로 자르고 뒤에 장 번호를 붙인다
    (`U01KSD7D7Y3338WQQKZWT0XT_2.jpg`) — productId 는 27자다. 워커가 눈앞의 파일명에서
    상품코드를 옮겨 적으면 정본과 어긋나 판정이 통째로 버려진다.

    두 형태를 다 받는다:
      · 잘리기만 한 것       `U01KSD7D7Y3338WQQKZWT0XT`
      · 파일명 접미까지 벤 것 `U01KSD7D7Y3338WQQKZWT0XT_2` / `..._9` / `..._Y`

    ULID 는 Crockford base32 라 `_` 가 절대 안 들어간다 — 첫 `_` 앞까지만 남기면
    안전하게 접미를 벗길 수 있다(2026-08-15 용쌤2-1: 접미까지 벤 2건을 손으로 고쳤다).

    복구 조건은 **접두 후보가 정확히 1개**일 때뿐이다. 잘린 id 는 정본의 접두사이고
    27자 ULID 라 24자 접두가 한 상품만 가리키면 그게 정답이다. 0개·2개 이상은
    고치지 않는다(fail-closed — 남의 판정을 엉뚱한 상품에 붙이느니 버린다).
    """
    pid = str(pid or "")
    if not pid or not valid or pid in valid:
        return None
    for stem in (pid, pid.split("_")[0]):
        if not stem or stem in valid:
            continue
        cand = [x for x in valid if x.startswith(stem)]
        if len(cand) == 1:
            return cand[0]
    return None


# `reference_url` 이 기준을 어디서 가져왔는지 — 미리보기·생성 로그의 경고 근거다.
REF_WORKER = "워커선택"        # 워커가 후보에서 고른 것
REF_MAIN_OPTION = "대표옵션"   # prep 선기록(규칙 0)
REF_EXISTING = "기존대표"      # 아무것도 없어 기존 0번으로 떨어진 것 — **맹목 배경교체**


def reference_source(product):
    """`reference_url` 이 어느 우선순위에서 나왔는지. 값은 `REF_*` 셋 중 하나.

    **왜 필요한가** (2026-08-15 용쌤2-1 광집게·크레인): 생성 로그에 `[기준] … 대표(0번)
    로 올림` 줄이 이 두 건만 없었다. 기준이 이미 0번이라 올릴 게 없었던 것인데, 그러면
    불사자는 **기존 대표를 그대로 배경교체한다** — 용팀장이 "원래 있던 썸네일이 새로
    생성됐다"고 지적한 그대로다. 재생성해도 같은 증상이라 원본대체로 종결했다.

    `REF_EXISTING` 은 그중에서도 위험하다: 워커 판단도 대표옵션도 없이 기존 대표로
    떨어진 것이라, 그 대표가 딴 물건이면 딴 물건이 그대로 예쁘게 재생성된다.
    """
    idx = product.get("기준이미지")
    if isinstance(idx, int) and not isinstance(idx, bool):
        return REF_WORKER
    if str(product.get("대표옵션이미지") or "").strip():
        return REF_MAIN_OPTION
    return REF_EXISTING


def generate_plan(items, prev=None, only_ids=None):
    """이번 `--generate` 에서 **실제로 태울** 목록과 건너뛸 목록을 가른다.

    **왜 필요한가** (2026-08-05 실측): 1-3 회차에서 DNS 단절로 128건 중 64번째에
    생성이 fail-closed 로 멈췄다(성공 63). 그런데 `--generate` 를 다시 부르면 빈
    상태로 시작해 **이미 태운 63건을 또 태운다** — 315크레딧 중복 과금이고, 결과
    이미지가 새것으로 바뀌어 이미 끝낸 검수도 무효가 된다.

    규칙:
      · `only_ids` 없음  = **재개**. `prev` 에 성공 기록(`생성본`)이 있으면 건너뛴다.
        실패 기록만 있는 건은 다시 시도한다(실패 원인이 대개 일시적 네트워크다).
      · `only_ids` 있음  = **부분 재실행(재생성)**. 지목한 상품만 대상으로 삼고,
        성공 기록이 있어도 다시 태운다 — 검수 불합격분을 다시 만드는 경로다.
        단 재생성 상한(`MAX_REGEN`)을 넘긴 건은 태우지 않는다.

    반환: (태울 items, [(상품id, 사유), ...] 건너뛴 것)
    """
    prev = prev or {}
    todo, skipped = [], []
    only = set(only_ids or ())
    for p in items:
        pid = p.get("productId")
        rec = prev.get(pid) or {}
        done = "생성본" in rec
        if only:
            if pid not in only:
                skipped.append((pid, "--ids 대상 아님"))
                continue
            # 재생성 상한 — 이미 만든 횟수가 상한에 닿으면 더 태우지 않는다.
            attempts = int(rec.get("재생성횟수") or 0)
            if done and not can_regenerate(attempts):
                skipped.append((pid, f"재생성 상한 {MAX_REGEN}회 도달"))
                continue
            todo.append(p)
            continue
        if done:
            skipped.append((pid, "이미 생성됨(재개)"))
            continue
        todo.append(p)
    return todo, skipped


def needs_audit(thumbnails, main_option):
    """가공됨 + 대표옵션 이미지 있음 → 완료 백필 금지, **정합검사(audit) 대상**.

    `가공됨(cdn.bulsaja.com)` 은 "손을 댔다"는 뜻이지 "맞게 됐다"는 뜻이 아니다 —
    2026-08-05 실측(1-3 그룹 백필 419건 표본 30): 대조 가능 28건 중 19건(68%)이
    대표옵션과 다른 물건이었다(스펙 오표기·색 변조·없는 것 추가·다른 제품).
    대표옵션 이미지가 없으면 대조할 근거 자체가 없으므로 종전대로 백필한다.
    """
    return is_already_done(thumbnails) and bool((main_option or {}).get("이미지"))


def audit_partition(products):
    """audit 결과 → ({불일치pid: 사유}, [일치pid], {대조불가pid: 사유}, {대표옵션의심pid: 사유}).

    **대조불가(404·판단 불가)는 재작업 flag 대상이 아니다** — flag 하면 다음 prep 이
    다시 집어가고 audit 이 또 대조불가를 내는 무한 재작업 루프가 된다. 별도 집계만.
    모르는 판정값·판정 누락도 대조불가로 본다(fail-safe — 함부로 재작업을 만들지 않는다).
    **대표옵션의심은 썸네일 재작업이 아니라 옵션 재작업이다**(2026-08-06) — 대표옵션 자체가
    본품이 아니면 그 기준으로 재생성·fallback 해봐야 부속 이미지만 나온다.
    """
    mismatch, match, uncomparable, main_suspect = {}, [], {}, {}
    for p in products or []:
        pid = str(p.get("productId") or "").strip()
        if not pid:
            continue
        v = str(p.get("판정") or "").strip()
        why = str(p.get("사유") or "").strip()
        if v == AUDIT_MISMATCH:
            mismatch[pid] = why or "대표옵션 불일치"
        elif v == AUDIT_MATCH:
            match.append(pid)
        elif v == AUDIT_MAIN_SUSPECT:
            main_suspect[pid] = why or "대표옵션이 본품이 아님(부속 의심)"
        else:
            uncomparable[pid] = why or f"판정 불가({v or '판정 누락'})"
    return mismatch, match, uncomparable, main_suspect


# 기준이미지 적격성(prescreen) 판정값 — 생성 **전에** 묻는다.
# 질문은 "도면이냐"가 아니라 **"이 한 장에서 만들 제품이 하나로 특정되나"** 다
# (2026-08-07 실측: 치수 도면을 기준으로 태운 3건이 전부 깨끗하게 생성됐다 —
#  그릇진열장·신발장·핀조명. 도면 자체는 사고 원인이 아니었다).
PRE_SINGLE = "단일특정"        # 실물 단독컷 + 치수선·텍스트만 얹힌 것 포함 → 그대로 태운다
PRE_MIXED = "다중혼재"         # 구성품 그리드·A/B/C款·2분할 비교 → run 팬아웃이 후보에서 고른다
PRE_NOPRODUCT = "실물없음"     # 순수 치수도면·색상칩·로고카드 → 보류(기준이미지없음)


def prescreen_partition(products):
    """prescreen 결과 → ({다중혼재pid: 사유}, {실물없음pid: 사유}, [단일특정pid]).

    **모르는 판정값·판정 누락은 `다중혼재`로 본다(fail-closed).** audit 의 대조불가와
    반대 방향인데, 두 축의 비용이 반대라서다:
      · 놓침(다중혼재 → 그대로 생성) = 사고. 무엇을 그릴지 정해지지 않은 기준은 생성도
        검수도 갈린다 — 갈매기조명(`A款/B款/C款`)은 검수에서 Sonnet 과 Haiku 가 서로 다르게
        오독해 사유 오분류로 남았다(2026-08-07 실측).
      · 과잉(단일특정 → 승격)       = run 워커 1회 추가. **크레딧 0.**
    무한 루프 위험도 없다 — 승격은 현황판이 아니라 배치를 건드리고, 승격된 건은 워커가
    기준을 새로 골라 `results/` 에 쓰면 그걸로 끝난다.
    """
    mixed, noproduct, single = {}, {}, []
    for p in products or []:
        pid = str(p.get("productId") or "").strip()
        if not pid:
            continue
        v = str(p.get("판정") or "").strip()
        why = str(p.get("사유") or "").strip()
        if v == PRE_SINGLE:
            single.append(pid)
        elif v == PRE_NOPRODUCT:
            noproduct[pid] = why or "대표옵션 이미지에 제품 실물이 없다"
        else:
            mixed[pid] = why or f"판정 불가({v or '판정 누락'}) — fail-closed 로 승격"
    return mixed, noproduct, single


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


def reference_url(product):
    """이 상품을 생성할 때 **실제로 써야 하는 기준 이미지 URL**. 없으면 빈 문자열.

    우선순위:
      1. 워커가 고른 `기준이미지`(정수 index) — 후보이미지[].index 또는 기존썸네일[index]
      2. `대표옵션이미지` — prep 선기록(규칙 0: 대표옵션이 있으면 그게 기준이다)
      3. 기존 대표(0번)

    1을 2보다 앞에 두는 이유: 대표옵션 이미지 **다운로드가 실패**하면 prep 이 그 상품을
    비전 판단으로 넘긴다(`대표옵션이미지경로` 만 비고 `대표옵션이미지` URL 은 남는다).
    그때 2를 먼저 보면 워커의 판단을 덮어써 버린다.
    """
    idx = product.get("기준이미지")
    thumbs = [str(u) for u in (product.get("기존썸네일") or [])]
    if isinstance(idx, int) and not isinstance(idx, bool):
        for c in (product.get("후보이미지") or []):
            if c.get("index") == idx:
                return str(c.get("url") or "")
        return thumbs[idx] if 0 <= idx < len(thumbs) else ""
    mo = str(product.get("대표옵션이미지") or "").strip()
    if mo:
        return mo
    return thumbs[0] if thumbs else ""


def staged_thumbnails(existing, ref_url):
    """생성 직전에 기준 이미지를 대표(0번)로 올린 **임시** 배열. 바꿀 필요 없으면 None.

    **왜 필요한가** (2026-08-05 실측): 불사자 생성 도구는 넘겨받은 이미지를 쓰는 게
    아니라 그 상품의 **첫 번째 대표이미지**를 배경교체한다(`mode` 기본값 `first`).
    그래서 기준 이미지를 0번에 올려놓고 생성해야 팬아웃의 판단·대표옵션 확정(규칙 0)이
    결과에 반영된다. 이 단계가 없으면 359건 전부 기존 대표만 배경교체된다(실측 사고).

    기준이 배열에 아예 없는 경우(대표옵션 이미지가 썸네일 목록 밖 — 실측 303/311건)도
    맨 앞에 끼워 넣는다. `indexes` 파라미터로는 배열 안의 자리만 지목할 수 있어서
    이 경우를 다룰 수 없다. 호출부는 생성 후 반드시 원래 배열로 되돌린다.
    """
    ref = str(ref_url or "").strip()
    if not ref:
        return None
    cur = [str(u) for u in (existing or [])]
    if not cur or cur[0] == ref:
        return None
    return [ref] + [u for u in cur if u != ref]


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


# 회수(recover) — 접수는 됐는데 폴링이 타임아웃한 건을 나중에 되찾는다.
#
# **타임아웃은 실패가 아니라 "아직"이다** (2026-08-06 실측): 재개분 6건이 전부 300초
# 타임아웃으로 실패 기록됐는데, 그 taskId 를 나중에 조회하니 전부 `대기 중`으로 살아
# 있었다. 큐가 밀린 것뿐이라 결과는 곧 나오는데, 회수 경로가 없어서 크레딧 30이
# 그대로 버려질 뻔했다. taskId 만 있으면 `bulsaja_detail_page_status` 로 언제든
# 되찾을 수 있다.
_TASKID_IN_ERROR = re.compile(r"taskId=(\d+)")


def task_id_of(record):
    """생성 기록에서 회수용 taskId 를 꺼낸다. 없으면 None.

    **`taskId` 의 뜻은 "결과를 아직 못 받은 접수 번호"다.** 접수 직후에 쓰고, 결과를
    받으면 성공 기록이 통째로 새 dict 로 갈리면서 사라진다. 그래서 이 필드가 남아
    있다는 것 자체가 "회수할 게 있다"는 신호다.

    `오류` 문자열 안의 `taskId=15652` 는 그 필드를 남기기 전에 만들어진 기록용
    폴백이다(실측 5건) — 옛 run-dir 을 나중에 회수하려면 필요하다.
    """
    rec = record or {}
    tid = rec.get("taskId")
    if tid not in (None, ""):
        return str(tid)
    m = _TASKID_IN_ERROR.search(str(rec.get("오류") or ""))
    return m.group(1) if m else None


def recover_targets(generated, only_ids=None):
    """회수 대상 {상품id: taskId}. 순서는 입력 순서를 지킨다.

    **`생성본` 이 있어도 뺀 만한 이유가 없다** — 결과를 받은 기록에는 taskId 가 아예
    없기 때문이다(위 참조). 반대로 재생성이 타임아웃한 건은 옛 생성본이 남아 있으면서
    taskId 도 있는데, 그건 **회수해야 맞다**(옛 이미지는 이미 불합격 판정된 것이라
    새 결과로 덮는 게 목적이다).
    """
    only = set(only_ids or [])
    out = {}
    for pid, rec in (generated or {}).items():
        if only and pid not in only:
            continue
        tid = task_id_of(rec)
        if tid:
            out[pid] = tid
    return out
