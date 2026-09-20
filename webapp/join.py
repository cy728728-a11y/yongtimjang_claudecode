#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""광고 판정행 ↔ 불사자 상품 조인 — dict 두 개를 받아 **투영만** 한다 (JOIN-01/02/03/04).

**읽기 전용이다. 네트워크도 크레딧도 0 이고, 파일도 DB 도 열지 않는다.**
`board.py` 와 같은 성질이다 — CLI 가 이미 써 둔 산출물(`result.json` · 조인 잡의
`join_<job_id>.json`)을 받아 화면이 쓸 모양으로 접을 뿐이다. MCP 접촉은 전부 CLI
자식 프로세스 몫이다(D-19). 그래서 조인 산출물이 없으면 빈 결과를 돌려줄 뿐
아무것도 고장내지 않는다.

이 모듈이 절대 하지 않는 것:
  - **상품명 매칭** (D-03). 실측 6건 중 2건이 깨졌다 — 조용히 틀린 상품을 집는 길이다.
    폴백으로도 쓰지 않는다
  - **별칭표·몰이름 2차 키·폴백 매핑** (D-02b). 번호와 불사자 마켓그룹은 1:1 이 정상이고,
    짝이 없는 번호는 **광고 쪽 오등록**이다. 사람이 네이버 광고에서 고친다.
    코드가 억지로 이어 붙이면 그 오등록이 영원히 안 고쳐진다
  - **`mallProductId` 영구 캐시** (D-04). 20일 물갈이로 재발급된다.
    회차 스냅샷 안에서만 조인 키다 — 그래서 인덱스 히트도 매번 재검증한다(JOIN-04)
  - **불사자 MCP 호출** (D-19). 불사자 클라이언트 라이브러리를 import 하지 않는다 —
    웹앱 전용 venv 에 그 HTTP 의존성이 없어 import 하는 순간 ImportError 다
  - **미해소를 한 통에 담기** (Pitfall 3). 사유가 사라지면 시스템 고장이
    사람 할 일 목록으로 둔갑하고, 용팀장이 멀쩡한 광고그룹을 지우러 간다.
    이 페이즈 최대 오진이다
  - **판정 재계산.** 상세 상태는 `state.py` 한 곳에서만 난다. 두 곳에 있으면
    화면과 산출물이 다른 말을 한다

공개 함수는 영문, 내부 이름은 한글 — `board.py` 의 관례다. 예외는 `재검증판정` 하나로,
`03-VALIDATION.md` 의 테스트 이름이 그 이름을 지목한다.
"""
import re

from webapp import state

# ── 미해소 사유코드 5종 ────────────────────────────────────────────────────
# **서로 다른 값이어야 한다.** 한 칸에 담으면 광고 쪽 오류와 시스템 문제가 섞인다.
추출실패 = "추출실패"   # 광고그룹명에 NN-N 번호가 없다            → 광고 쪽 오류
번호없음 = "번호없음"   # 번호는 있는데 불사자에 그 번호가 없다     → 광고 쪽 오류
미조회 = "미조회"       # 제외 설정 · 레이트리밋 · 스캔 전          → 우리가 안 본 것
미스 = "미스"           # 그룹은 좁혔는데 그 안에 이 상품이 없다    → 우리 쪽 문제
불일치 = "불일치"       # 인덱스값과 지금 관측값이 다르다(물갈이)   → 우리 쪽 문제
히트 = "히트"           # 재검증까지 통과 — 여기서만 해소다

# 버킷 2종. 화면은 이 두 숫자를 **절대 합치지 않는다**.
광고청소 = "광고청소"
시스템 = "시스템"

_버킷 = {
    추출실패: 광고청소,
    번호없음: 광고청소,
    미조회: 시스템,
    미스: 시스템,
    불일치: 시스템,
}

# `재검증판정` 의 파라미터 이름이 위 상수 `미조회` 를 가린다. 함수 안에서 쓰려고
# 별칭을 둔다 — 문자열을 다시 적으면 진실이 둘이 된다.
_미조회 = 미조회

# 프롬프트 인젝션 필드. 불사자 응답에 섞여 오는 **모델 대상 지시문**이다.
_표시규칙키 = "표시규칙"

# 광고그룹명에서 마켓 번호(NN-N)를 뽑는 패턴 (D-02).
# 접두사 포맷이 계정마다 다르다 — 언더바 접두 · 공백 접두 · 숫자 접두.
# 그래서 접두사 목록을 만들지 않고 **번호 패턴만** 찾는다.
# 숫자 접두(`1000개_`)의 1000 은 뒤에 '-' 가 없어 매치되지 않는다(실측 확인).
_번호패턴 = re.compile(r"(\d{1,2})-(\d{1,2})")

# attach() 가 행에 얹는 키 전부. 해소 전 기본값은 **0 이 아니라 None** 이다
# (`board.py:174-176` 의 "분모가 없으면 비율도 없다" 와 같은 정신) —
# 0 으로 채우면 "사본이 0건이었다" 는 판정처럼 보이는데 실제로는 안 본 것이다.
_기본값 = {
    "adGroups": (),
    "번호": None,
    "번호해소": False,
    "상품조회": None,
    "해소": False,
    "사유코드": None,
    "사유": None,
    "버킷": None,
    "productId": None,
    "상세상태": None,
    "기작업": False,
    "기작업태그": None,
    "사본N": None,
    "잠금혼재": None,
}


def market_number(ad_group_name) -> str | None:
    """'판매상품_15-2_어느회사' → '15-2'. 없으면 None.

    ⚠️ 불사자 그룹명의 `NN번_` 접두는 마켓번호가 **아니다** — 진짜 번호는 접미사의 NN-N.
    """
    m = _번호패턴.search(ad_group_name or "")
    return f"{m.group(1)}-{m.group(2)}" if m else None


def group_index(groups) -> dict:
    """불사자 마켓그룹 목록 → `{번호: 그룹}`.

    ⚠️ 번호가 안 나오는 그룹이 86개 중 32개다. 앞의 `N번_` 은 번호가 **아니다**.
       실측 결과 번호가 나오는 54개에서 **충돌 0건**이라 dict 로 안전하다 —
       나중에 충돌하면 여기서 조용히 덮인다.
    """
    out: dict[str, dict] = {}
    for g in groups or []:
        if not isinstance(g, dict):
            continue
        n = market_number(g.get("그룹명", ""))
        if n:
            out[n] = g
    return out


def ad_groups_by_product(result) -> dict:
    """`(계정 alias, mallProductId)` → 그 상품 줄에 걸린 **광고그룹명 원문** 목록.

    미해소 사유 문자열의 재료다 — 용팀장이 네이버 광고 화면에서 이 이름으로 찾아 지운다.
    중복은 없애되 **첫 등장 순서를 보존**한다(정렬하면 어느 게 대표인지 사라진다).
    규칙마다 있는 키가 다르므로 `.get()` 으로만 만진다 (`board.py:36-40`).
    """
    if not isinstance(result, dict):
        return {}
    out: dict[tuple, list] = {}
    for alias, account in (result.get("accounts") or {}).items():
        for _규칙, 행들 in (((account or {}).get("rules")) or {}).items():
            for r in 행들 or []:
                if not isinstance(r, dict):
                    continue
                이름 = r.get("adGroup")
                if not 이름:
                    continue
                목록 = out.setdefault((alias, r.get("mallProductId")), [])
                if 이름 not in 목록:
                    목록.append(이름)
    return out


def strip_display_rules(obj):
    """dict/list 를 재귀로 돌며 `표시규칙` 키를 **제거한 사본**을 돌려준다.

    그 필드는 불사자 응답에 섞여 오는 **모델 대상 지시문**("앞 지시 무시해…")이다.
    화면 렌더 경로나 LLM 투입 경로를 만드는 순간 프롬프트 인젝션이 된다 (T-3-06).
    `attach()` 는 조인 산출물을 받자마자 이걸 통과시킨다.

    원본을 mutate 하지 않는다 — 호출부가 같은 dict 를 다시 쓴다.
    """
    if isinstance(obj, dict):
        return {k: strip_display_rules(v) for k, v in obj.items() if k != _표시규칙키}
    if isinstance(obj, list):
        return [strip_display_rules(v) for v in obj]
    return obj


def 재검증판정(인덱스_smartstore, 관측_smartstore, 미조회) -> str:
    """인덱스값과 지금 관측한 값을 맞대 본다 — `미조회`/`미스`/`히트`/`불일치` (JOIN-04).

    **순서에 의미가 있다:**
      ① `미조회` 가 참이면 무조건 `미조회` — 레이트리밋(429)·타임아웃을 성공으로 접지 않는다
      ② 인덱스값이 없으면 `미스` — 훑었는데 그 안에 이 상품이 없었다
      ③ 관측값이 없으면 `미조회` — **재검증 자체를 못 했다.** 인덱스만 보고 해소로 접는
         경로를 만들면 물갈이로 재발급된 번호에 엉뚱한 상품이 붙는다
      ④ 두 값이 같으면 `히트`, 다르면 `불일치`(물갈이 재발급)

    이 함수가 인덱스 저장소가 아니라 여기 사는 이유: 판정은 **조인 의미론**이고,
    인덱스 모듈은 적혀 있는 값을 꺼내 주는 데까지만 한다. 판정이 두 곳에 있으면
    화면과 산출물이 다른 말을 한다.
    """
    if state.불리언정규화(미조회):
        return _미조회
    if not 인덱스_smartstore:
        return 미스
    if not 관측_smartstore:
        return _미조회
    return 히트 if str(인덱스_smartstore) == str(관측_smartstore) else 불일치


def _인용(광고그룹들) -> str:
    """사유 문자열에 넣을 광고그룹명 원문. 이름이 곧 용팀장의 할 일 목록이다.

    ⚠️ 실제 광고그룹명을 이 파일에 예시로 적지 마라 — 주석에 남은 그룹명은
       다음 사람에게 별칭표로 읽힌다(Pitfall 5). f-string 으로만 끼워 넣는다.
    """
    if not 광고그룹들:
        return "(광고그룹 정보 없음)"
    return " · ".join(f"'{g}'" for g in 광고그룹들)


def _미해소(행, 사유코드, 사유):
    """행에 사유코드·사유·버킷을 한 번에 박는다. 버킷은 사유코드가 정한다."""
    행["사유코드"] = 사유코드
    행["사유"] = 사유
    행["버킷"] = _버킷.get(사유코드, 시스템)
    return 행


def attach(rows, result, join_doc, *, excluded=(), done_tags=()):
    """`board.fold_products` 결과에 조인 결과를 얹는다. **원본을 고치지 않는다.**

    `rows` 는 보드 행이고, `result` 는 광고 판정 결과, `join_doc` 은 조인 잡이 써 둔
    산출물 dict 다. 파일을 직접 열지 않는다 — dict 를 인자로 받는다.

    판정 순서:
      0. `join_doc` 이 없다(아직 조인을 안 돌렸다) → **전 행이 `미조회`/`시스템`.**
         번호 추출은 조인 없이도 되지만, 그 결과를 청소 목록으로 내보내는 순간
         "스캔 안 함" 이 "광고 오류" 로 둔갑한다 (Pitfall 3). 번호 자체는 채워 둔다
      1. 광고그룹명에서 번호를 못 뽑으면 `추출실패`/`광고청소`
      2. 번호가 불사자 마켓그룹에 없으면 `번호없음`/`광고청소`
      3. 번호가 제외 설정(D-18)에 있으면 `미조회`/`시스템` — 광고는 멀쩡하다
      4. 관측이 없거나 `재검증판정` 이 히트가 아니면 그 사유로 미해소
      5. 히트면 상태·기작업·팬아웃을 붙인다

    `done_tags` 는 인자로 받는다 — 이 모듈은 설정을 직접 읽지 않는다.
    **장수(`pages`) 인자는 없다.** 기작업 스킵은 목표 장수와 무관한 절대 조건이다
    (STATE-05 / D-10).
    """
    문서 = strip_display_rules(join_doc) if isinstance(join_doc, dict) else None
    그룹색인 = group_index((문서 or {}).get("마켓그룹")) if 문서 is not None else None

    관측색인: dict[tuple, dict] = {}
    if 문서 is not None:
        for 관측 in 문서.get("행") or []:
            if isinstance(관측, dict):
                관측색인[(관측.get("acct"), 관측.get("mallProductId"))] = 관측

    광고색인 = ad_groups_by_product(result)
    제외 = {str(n) for n in (excluded or ())}
    태그들 = [str(t) for t in (done_tags or ())]

    out = []
    for r in rows or []:
        행 = dict(r)                      # **복사한다.** 원본을 mutate 하면 호출부가 어긋난다
        행.update(_기본값)
        키 = (행.get("acct"), 행.get("mallProductId"))
        광고그룹들 = list(광고색인.get(키) or [])
        행["adGroups"] = 광고그룹들
        out.append(행)

        # 번호는 조인 여부와 무관하게 채운다 — 화면이 "무엇을 훑을 것인지" 를 보여준다
        번호 = None
        for 이름 in 광고그룹들:
            번호 = market_number(이름)
            if 번호:
                break
        행["번호"] = 번호

        if 그룹색인 is None:
            _미해소(행, 미조회,
                   f"조인을 아직 안 돌렸다 — 불사자 마켓그룹 목록이 없다. "
                   f"조인 잡을 먼저 실행해라 (광고그룹 {_인용(광고그룹들)})")
            continue

        if not 번호:
            _미해소(행, 추출실패,
                   f"번호 추출 실패 — 광고그룹명 {_인용(광고그룹들)} 에 NN-N 번호가 없다")
            continue

        if 번호 not in 그룹색인:
            _미해소(행, 번호없음,
                   f"번호 '{번호}' 가 불사자 마켓그룹에 없다 — 광고그룹 {_인용(광고그룹들)}")
            continue

        행["번호해소"] = True

        if 번호 in 제외:
            _미해소(행, 미조회,
                   f"제외 설정으로 이번 인덱스에서 안 훑은 마켓그룹이다 — "
                   f"번호 '{번호}' · 광고그룹 {_인용(광고그룹들)}. 광고 쪽은 멀쩡하다")
            continue

        관측 = 관측색인.get(키)
        if 관측 is None:
            _미해소(행, 미조회,
                   f"불사자 인덱스에 아직 없다 — 인덱스 구축이 필요하다. "
                   f"번호 '{번호}' · 광고그룹 {_인용(광고그룹들)}")
            continue

        판정 = 재검증판정(관측.get("인덱스_smartstore"),
                        관측.get("관측_smartstore"),
                        관측.get("미조회"))
        행["상품조회"] = 판정

        if 판정 == 미스:
            _미해소(행, 미스,
                   f"마켓그룹은 좁혀졌는데 그 안에 이 상품이 없다 — "
                   f"번호 '{번호}' · 광고그룹 {_인용(광고그룹들)}")
            continue
        if 판정 == 불일치:
            _미해소(행, 불일치,
                   f"인덱스에 적힌 상품번호와 지금 관측한 값이 다르다 — 물갈이 재발급으로 보인다. "
                   f"번호 '{번호}' · 광고그룹 {_인용(광고그룹들)}. 인덱스를 다시 훑어야 한다")
            continue
        if 판정 != 히트:
            _미해소(행, 미조회,
                   f"재검증을 못 했다(레이트리밋·타임아웃) — "
                   f"번호 '{번호}' · 광고그룹 {_인용(광고그룹들)}")
            continue

        # ── 여기서만 해소다 ──
        행["해소"] = True
        행["productId"] = 관측.get("productId")
        dc = 관측.get("uploadDetailContents")
        행["상세상태"] = state.상세상태(dc)
        행["기작업태그"] = 관측.get("그룹태그")       # 상태와 **별개 값**이다 (Pitfall 8)
        행["기작업"] = state.기작업여부(관측.get("그룹태그"), dc, 태그들)

        사본 = 관측.get("사본")
        if isinstance(사본, list):
            행["사본N"] = len(사본)
            잠금들 = {state.불리언정규화((c or {}).get("잠금"))
                     for c in 사본 if isinstance(c, dict)}
            행["잠금혼재"] = len(잠금들) > 1

    return out


def resolution(attached_rows) -> dict:
    """해상률 집계 — **두 버킷을 한 숫자로 합치지 않는다** (JOIN-01 / Pitfall 3).

    "미해소 15행" 만 띄우면 그게 광고 쪽 청소 대상인지 우리가 안 본 것인지 알 수 없다.
    비율은 화면이 만든다 — 분모가 0 이면 비율을 지어내지 않는다(`board.py:174-178`).
    """
    행들 = list(attached_rows or [])
    광고사유 = {추출실패: 0, 번호없음: 0}
    시스템사유 = {미조회: 0, 미스: 0, 불일치: 0}
    광고행 = 시스템행 = 0

    for r in 행들:
        코드 = (r or {}).get("사유코드")
        if 코드 in 광고사유:
            광고사유[코드] += 1
            광고행 += 1
        elif 코드 in 시스템사유:
            시스템사유[코드] += 1
            시스템행 += 1

    번호해소 = sum(1 for r in 행들 if (r or {}).get("번호해소"))
    return {
        "전체": len(행들),
        "번호해소": 번호해소,
        "번호미해소": len(행들) - 번호해소,
        "상품해소": sum(1 for r in 행들 if (r or {}).get("해소")),
        "광고청소": {
            "행": 광고행,
            "그룹": len(cleanup_groups(행들)),
            "사유별": 광고사유,
        },
        "시스템": {
            "행": 시스템행,
            "사유별": 시스템사유,
        },
    }


def cleanup_groups(attached_rows) -> list[dict]:
    """광고 청소 목록 — **지울 대상은 그룹이고 행은 그 부산물이다** (JOIN-02 설계요구 3).

    실측에서 14개 그룹이 102행을 만들었다. 행 단위로 띄우면 같은 그룹이 57번 나와
    할 일 목록으로 못 쓴다. 정렬은 행수 내림차순(지울 값어치 순).

    `버킷 == "광고청소"` 인 행만 접는다 — 시스템 문제는 광고를 고쳐서 풀리지 않는다.
    """
    묶음: dict[str, dict] = {}
    for r in attached_rows or []:
        r = r or {}
        if r.get("버킷") != 광고청소:
            continue
        for 이름 in r.get("adGroups") or ():
            g = 묶음.get(이름)
            if g is None:
                g = 묶음[이름] = {
                    "adGroup": 이름,
                    "번호": market_number(이름),
                    "사유코드": r.get("사유코드"),
                    "행수": 0,
                    "계정들": [],
                }
            g["행수"] += 1
            acct = r.get("acct")
            if acct and acct not in g["계정들"]:
                g["계정들"].append(acct)
    return sorted(묶음.values(), key=lambda g: (-g["행수"], g["adGroup"]))


def index_targets(attached_rows, join_doc, excluded=()) -> list[str]:
    """훑어야 할 불사자 `groupId` 목록 — **번호 기준으로 중복 제거**한다.

    같은 번호를 쓰는 광고그룹이 실측으로 7쌍 있다. 안 접으면 같은 마켓그룹을 두 번
    훑어 **몇 시간을 버린다.** 제외 설정(D-18)의 번호는 뺀다.

    ⚠️ **빈 리스트 = 훑을 대상 없음.** "전량" 이 아니다. 이걸 전량으로 읽는 호출부가
       생기면 47,105 상품을 통째로 다시 훑는다.
    """
    문서 = strip_display_rules(join_doc) if isinstance(join_doc, dict) else None
    if 문서 is None:
        return []
    색인 = group_index(문서.get("마켓그룹"))
    제외 = {str(n) for n in (excluded or ())}

    ids = set()
    for r in attached_rows or []:
        번호 = (r or {}).get("번호")
        if not 번호 or 번호 in 제외:
            continue
        그룹 = 색인.get(번호)
        gid = (그룹 or {}).get("groupId")
        if gid:
            ids.add(str(gid))
    return sorted(ids)


def selectable(attached_rows) -> list[dict]:
    """기본 선택 대상 — 해소됐고 기작업이 아닌 행만 (D-08 / STATE-05).

    ⚠️ **화면에서 숨기는 장치가 아니다.** 기작업 상품은 목록에 회색으로 남고 태그가
       보이며, 용팀장이 직접 체크하면 대상이 된다. 숨기면 "왜 이 상품이 안 보이지" 를
       코드에서 찾아야 한다. 여기서 빼는 것은 **기본 선택**뿐이다.
    """
    return [r for r in attached_rows or []
            if (r or {}).get("해소") and not (r or {}).get("기작업")]
