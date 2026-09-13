#!/usr/bin/env python3
"""쿠팡 후보 판정 — 순수 계산. 네트워크 0, LLM 판단 0.

`bulsaja-option-cleanup/scripts/option_rules.py` 와 같은 자리다: **스크립트가 계산하고
워커(LLM)는 판단만 한다.** 이 파이프라인은 LLM 판단이 아예 없으므로 전부 여기서 끝난다.

**왜 마진 정의를 여기 고정하는가**: 마진을 어떻게 세느냐로 결과가 20%p 갈린다.
실측에서 한 코드가 `마진률` 산술평균 31.4% vs 가중평균 11.6% 였다. 정의가 흔들리면
게이트가 무의미해지므로 공식을 한 곳에 박고 단위테스트로 묶는다.
"""

# 스마트스토어 실측 수수료율(주문시트 `마켓수수료율` 열). 결측 행의 기본값.
DEFAULT_SS_FEE = 7.0

# 쿠팡 판매수수료 상한. **모르는 카테고리는 전부 이 값으로 잡는다** — 게이트가
# 낙관하면 적자 상품이 통과한다.
MAX_FEE = 10.8

# 쿠팡 카테고리별 판매수수료(%) — 경로 접두사 → 요율.
# ⚠️ **이 표는 검증 전이다.** 불사자 카테고리는 네이버 체계라 쿠팡으로의 자동 매핑이
# 없다. 파일럿 규모(70여 건)에서는 사람이 한 번 훑는 게 맞고, 훑기 전까지는
# 미등록 = MAX_FEE 라 **보수적으로만 틀린다**(후보가 줄지, 적자가 통과하진 않는다).
# 갱신 근거는 references/쿠팡-수수료율.md 에 날짜와 함께 남긴다.
FEE_TABLE = {}


def coupang_fee(category_path, table=None):
    """네이버 카테고리 경로 → 쿠팡 판매수수료(%). 미등록은 `MAX_FEE`.

    더 구체적인(긴) 접두사가 이긴다.
    """
    t = FEE_TABLE if table is None else table
    path = str(category_path or "").strip()
    if not path or not t:
        return MAX_FEE
    best, best_len = MAX_FEE, -1
    for prefix, rate in t.items():
        if path.startswith(prefix) and len(prefix) > best_len:
            best, best_len = rate, len(prefix)
    return best


def adjust_margin(가중마진, 쿠팡수수료, 평균ss수수료=None):
    """스마트스토어 실적 마진 → 쿠팡 예상 마진.

        쿠팡보정마진 = 가중마진 − (쿠팡수수료 − 스마트스토어수수료)

    `가중마진` 은 스마트스토어 수수료가 이미 반영된 값이다. 쿠팡은 수수료가 다르므로
    그 차이만큼 빼준다. 이 보정은 **수수료 차이만** 다룬다 — 반품비·품절취소 비용은
    게이트 하한선(`min_margin`)이 흡수한다.
    """
    if 가중마진 is None:
        return None
    ss = DEFAULT_SS_FEE if 평균ss수수료 is None else float(평균ss수수료)
    return float(가중마진) - (float(쿠팡수수료) - ss)


def passes(rec, min_margin=15.0, min_orders=3, category_fee=None):
    """후보 1건 판정 → `(통과여부, 사유)`.

    게이트는 **하나뿐**(마진 하한선)이고 주문수 컷은 그 앞의 선별자다.
    나머지 지표(최소마진·적자건수·배송비편차)는 기록만 하고 자동 탈락시키지 않는다 —
    표본이 몇 건뿐이라 최솟값은 운에 좌우된다.
    """
    orders = int(rec.get("주문수") or 0)
    if orders < min_orders:
        return False, f"주문수부족({orders} < {min_orders})"

    가중 = rec.get("가중마진")
    if 가중 is None or not rec.get("유효행수"):
        # fail-closed: 모르는 것을 통과시키면 게이트의 존재 이유가 사라진다.
        return False, "마진미상(유효행 0)"

    fee = coupang_fee(rec.get("카테고리")) if category_fee is None else category_fee
    보정 = adjust_margin(가중, fee, rec.get("평균수수료율"))
    if 보정 is None:
        return False, "마진미상"
    if 보정 + 1e-9 < min_margin:
        return False, f"마진미달({보정:.1f}% < {min_margin}%)"
    return True, f"통과({보정:.1f}%)"


# 정상으로 보는 불사자 상태. 판매중지·삭제 계열은 쿠팡에 올리면 품절취소로 이어진다.
NORMAL_STATES = {"수집됨", "가공 중", "검토 완료", "업로드 완료", "업로드 실패"}


def choose_top_seller(insts, done_counts=None, exclude_groups=None):
    """사본 목록에서 쿠팡에 올릴 대표 1건을 고른다. 후보가 없으면 None.

    **`dedup.choose_representative()` 를 쓰지 않는 이유**: 그쪽 정렬 키는
    `(-완료작업수, 그룹명, pid)` 라 "가장 많이 가공된 사본"을 고른다. 목적함수가
    "스마트스토어 전파 시 작업 재사용 극대화"다. 쿠팡의 목적함수는 다르다 —
    우리가 아는 유일한 쿠팡 성공 예측 변수는 **스마트스토어 실적**이고, 그 실적은
    사본별로 갈라져 있다. 완료작업수로 뽑으면 "잘 다듬어졌지만 안 팔린 사본"을 올린다.

    또 `choose_representative` 는 도크스트링이 스스로 적어 둔 공백이 있다 —
    **상태코드를 보지 않는다.** 쿠팡은 품절취소가 계정정지 사유라 치명적이다.
    그래서 상태 필터를 0순위 하드 필터로 둔다.

    정렬 키(전부 결정적):
      0) 하드 필터 — 상태 정상 AND 대상 그룹(쿠팡) 사본 아님
      1) -주문수        사본별 실판매
      2) -매출
      3) -완료작업수    ← choose_representative 의 기존 키를 tie-break 로 흡수
      4) 잠금 우선      ← 잠긴 사본 = 판매 실적이 있어 사람이 지킨 사본
      5) 그룹명, pid    ← 결정성 보장
    """
    done = done_counts or {}
    ex = exclude_groups or set()
    pool = [i for i in (insts or [])
            if str(i.get("상태") or "") in NORMAL_STATES
            and str(i.get("그룹명") or i.get("그룹") or "") not in ex]
    if not pool:
        return None
    return sorted(pool, key=lambda i: (
        -float(i.get("주문수") or 0),
        -float(i.get("매출") or 0.0),
        -float(done.get(i.get("productId"), 0)),
        0 if i.get("잠금") else 1,
        str(i.get("그룹명") or i.get("그룹") or ""),
        str(i.get("productId") or ""),
    ))[0]


def group_by_bulsaja_code(resolved, sales):
    """`{판매자상품코드: 조회레코드}` + `{판매자상품코드: 실적}` → `{불사자코드: 묶음}`.

    불사자코드는 **한 원본에서 복사된 사본 전체가 공유하는 키**다(실측: 코드 1개에
    사본 27건). 이걸로 묶으면 같은 상품이 쿠팡에 중복 등록되는 걸 막는다.

    ⚠️ 스냅샷 파일의 `불사자코드` **필드**는 이름이 잘못 붙어 있어 실제로는
    판매자상품코드다. 여기서 쓰는 건 MCP 응답의 `불사자코드` — 서로 다른 값이다.

    불사자코드가 비어 있으면 `solo:{productId}` 로 혼자 둔다(병합하지 않는다).
    """
    groups = {}
    for code, rec in (resolved or {}).items():
        key = str(rec.get("불사자코드") or "").strip()
        if not key:
            key = f"solo:{rec.get('productId')}"
        s = (sales or {}).get(code) or {}
        g = groups.get(key)
        if g is None:
            g = groups[key] = {"불사자코드": key, "사본": [],
                               "합산주문수": 0, "합산매출": 0.0}
        g["사본"].append({
            "productId": rec.get("productId"),
            "판매자상품코드": code,
            "상태": rec.get("상태"),
            "잠금": rec.get("잠금"),
            "그룹명": rec.get("그룹"),
            "판매가": rec.get("판매가"),
            "업로드된마켓": rec.get("업로드된마켓"),
            "주문수": s.get("주문수") or 0,
            "매출": s.get("매출") or 0.0,
        })
        g["합산주문수"] += int(s.get("주문수") or 0)
        g["합산매출"] += float(s.get("매출") or 0.0)
    return groups


def shipping_diff(실측P75, 불사자현재, tolerance_pct=10.0):
    """실측 배송비(P75)와 불사자 입력값을 비교해 교정 필요 여부를 낸다.

    **왜 중앙값이 아니라 P75 인가**: 같은 상품인데 주문마다 배송비 편차가 크다
    (실측 중앙값 34%, 후보 154개 중 98개가 20% 초과). 스마트스토어에서는 과소책정을
    고객 추가금으로 흡수해 왔지만 쿠팡에는 그 수단이 없다 — 보수적으로 잡는다.
    """
    if 실측P75 is None:
        return {"교정필요": False, "방향": "측정없음", "차액": None,
                "실측P75": None, "현재": 불사자현재}
    if 불사자현재 is None:
        return {"교정필요": True, "방향": "미상", "차액": None,
                "실측P75": round(float(실측P75)), "현재": None}
    실측, 현재 = float(실측P75), float(불사자현재)
    차액 = round(실측 - 현재)
    한계 = abs(현재) * tolerance_pct / 100.0
    return {
        "교정필요": abs(실측 - 현재) > 한계,
        "방향": "인상" if 차액 > 0 else ("인하" if 차액 < 0 else "동일"),
        "차액": 차액,
        "실측P75": round(실측),
        "현재": round(현재),
    }
