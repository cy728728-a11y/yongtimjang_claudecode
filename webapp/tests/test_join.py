#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""광고↔불사자 조인(`webapp/join.py`) 검증 — 파일 IO 없이 순수 함수만 때린다.

`result_traps` · `bulsaja_groups_traps` · `join_traps` · `result_join_real` 픽스처
(Plan 03-01)가 주는 dict 로 전부 끝난다. 네트워크도 크레딧도 0 이다.

픽스처에 일부러 심어 둔 함정을 각각 하나씩 겨눈다:
  (a) 번호 추출 포맷 3종 — `판매상품_15-2_` 언더바 · `20-3 ` 공백 · `1000개_22-1_` 숫자 접두
      (`1000` 이 마켓번호로 오탐되면 안 된다)
  (b) 번호가 아예 없는 광고그룹 → 사유 `추출실패` (**광고 쪽 오류**)
  (c) 번호는 있는데 불사자에 그 번호가 없다 → 사유 `번호없음` (**광고 쪽 오류**)
  (d) D-18 제외 마켓번호 → 사유 `미조회` (**우리가 안 본 것**). (b)(c)와 절대 같은 칸에 담지 마라
  (e) 같은 번호(`17-3`)를 쓰는 광고그룹 2개 → 인덱스 대상에서 groupId 1개로 접힌다
  (f) 사본 3건 팬아웃(그중 1건 잠금) → `사본N` · `잠금혼재`
  (g) `표시규칙` 이 최상위와 행 안쪽 양쪽에 있다 → 반환값 전문에서 0건이어야 한다

🔴 이 파일이 지키는 제일 중요한 것: **미해소를 한 통에 담지 않는다.**
사유가 뭉개지면 시스템 고장(우리가 안 본 것)이 사람 할 일 목록(광고 청소)으로 둔갑하고,
용팀장이 멀쩡한 광고그룹을 지우러 간다. 이 페이즈 최대 오진이다 (Pitfall 3).

⚠️ `03-VALIDATION.md` 는 `test_히트도_재검증한다`·`test_불일치는_미해소` 를 `test_index.py`
행에 적어 뒀지만, 판정 함수(`재검증판정`)가 조인 의미론이라 `join.py` 에 산다.
그래서 **같은 이름으로 여기** 둔다 — 검증 내용은 그대로다.
"""
import inspect
import json
from pathlib import Path

from webapp import board, join, state

WEBAPP = Path(__file__).resolve().parents[1]

# 픽스처의 기작업 태그. 런타임 기본값은 `settings.DEFAULTS["done_tags"]` 이고,
# 여기서는 호출부가 설정을 읽어 넘긴다는 계약을 흉내 낸다.
기작업태그들 = ["구매_가공완료"]


def _붙인다(result_traps, join_traps, join_doc=..., **kw):
    """`board.fold_products` → `join.attach` 를 한 번에. 테스트 본문을 짧게 유지한다."""
    rows = board.fold_products(result_traps)
    doc = join_traps if join_doc is ... else join_doc
    kw.setdefault("excluded", tuple(join_traps.get("제외그룹") or ()))
    kw.setdefault("done_tags", 기작업태그들)
    return join.attach(rows, result_traps, doc, **kw)


def _표시규칙_키가_남았나(obj, 경로="$"):
    """중첩 구조 어디에도 `표시규칙` **키**가 없는지 재귀로 훑는다.

    값(설명 문장)이 아니라 키를 본다 — 지워야 할 것은 모델 대상 지시문이 담긴 필드다.
    """
    남은 = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "표시규칙":
                남은.append(f"{경로}.{k}")
            남은 += _표시규칙_키가_남았나(v, f"{경로}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            남은 += _표시규칙_키가_남았나(v, f"{경로}[{i}]")
    return 남은


def _행(rows, mpid):
    """붙인 행 하나를 `mallProductId` 로 집어 온다. 없으면 테스트를 세운다."""
    found = [r for r in rows if r.get("mallProductId") == mpid]
    assert len(found) == 1, f"{mpid} 가 {len(found)}줄이다 (1줄이어야 한다)"
    return found[0]


# ── 번호 추출 ──────────────────────────────────────────────────────────────

def test_번호추출_전수(result_traps, bulsaja_groups_traps, result_join_real):
    """광고그룹명에서 `NN-N` 을 뽑는다 — 접두사 포맷 3종 + 오탐 함정 (D-02 / JOIN-02).

    접두사 목록을 만들지 않고 **번호 패턴만** 찾는다. 계정마다 포맷이 다르다.
    """
    assert join.market_number("판매상품_15-2_zzfakecompany") == "15-2"
    assert join.market_number("20-3 zzfakecompany2") == "20-3"
    # `1000개_` 의 1000 은 뒤에 '-' 가 없어 매치되지 않는다. "10" 이나 "00" 이 나오면 오탐이다
    assert join.market_number("1000개_22-1_zzfakecompany3") == "22-1"
    # 불사자 그룹명의 `NN번_` 접두는 번호가 **아니다** — 진짜 번호는 접미사의 NN-N
    assert join.market_number("15번_zzfake15-2") == "15-2"
    assert join.market_number("13번_zzfake13-2") == "13-2"
    # 하이픈이 하나도 없는 그룹 / 숫자가 아예 없는 그룹
    assert join.market_number("1번_zzfake곰3") is None
    assert join.market_number("zzfake쿠팡전용") is None
    assert join.market_number("zzfake이동식오피스") is None
    assert join.market_number("") is None
    assert join.market_number(None) is None

    # 트랩 픽스처의 모든 광고그룹명 — 뽑힌 번호는 반드시 그 이름 안에 실제로 들어 있다
    이름들 = set()
    for v in result_traps["accounts"].values():
        for 행들 in v["rules"].values():
            for r in 행들:
                이름들.add(r["adGroup"])
    for 이름 in 이름들:
        n = join.market_number(이름)
        if n is not None:
            assert n in 이름, f"'{이름}' 에서 지어낸 번호 '{n}' 이 나왔다"

    # 불사자 그룹 목록도 같은 규약이다
    for g in bulsaja_groups_traps["그룹"]:
        n = join.market_number(g["그룹명"])
        if n is not None:
            assert n in g["그룹명"]

    # ── 실회차 46개 광고그룹명 전수 ──
    # ⚠️ 이 픽스처는 용팀장이 광고그룹을 정리하기 **전** 회차다 (03-01-SUMMARY 참조).
    # 정리 후에는 번호 없는 그룹이 0개지만, 이 스냅샷에는 1개가 남아 있고 그 1개가
    # 57행(29%)을 미해소로 만든다 — 그게 JOIN-02 가 화면에 띄워야 할 바로 그 모습이다.
    실이름들 = set()
    for v in result_join_real["accounts"].values():
        for 행들 in (v.get("rules") or {}).values():
            for r in 행들:
                실이름들.add(r.get("adGroup"))
    실패 = sorted(n for n in 실이름들 if join.market_number(n) is None)
    assert len(실이름들) == 46, f"실회차 고유 광고그룹이 {len(실이름들)}개다"
    assert len(실패) == 1, f"추출 실패가 {len(실패)}개다: {실패}"
    # 실패한 그 이름에는 정말로 NN-N 이 없다 (정규식이 게을러서 놓친 게 아니다)
    assert "-" not in 실패[0], f"'{실패[0]}' 에 하이픈이 있는데 번호를 못 뽑았다"
    for 이름 in 실이름들 - set(실패):
        n = join.market_number(이름)
        assert n and n in 이름, f"'{이름}' → '{n}' 이 이름 안에 없다"


def test_같은번호_중복제거(result_traps, join_traps):
    """같은 번호를 쓰는 광고그룹 2개가 `index_targets` 에서 groupId 1개로 접힌다 (비용).

    실측으로 같은 번호를 쓰는 광고그룹이 7쌍 있다. 안 접으면 같은 마켓그룹을
    두 번 훑어 **몇 시간을 버린다.**
    """
    붙임 = _붙인다(result_traps, join_traps)
    색인 = join.group_index(join_traps["마켓그룹"])

    # 픽스처 전제: 17-3 을 쓰는 광고그룹이 서로 다른 계정에 2개 있다
    열일곱 = [r for r in 붙임 if r.get("번호") == "17-3"]
    assert len(열일곱) == 2, f"17-3 행이 {len(열일곱)}개다 (2개여야 한다)"
    assert len({r["acct"] for r in 열일곱}) == 2
    assert len({g for r in 열일곱 for g in r["adGroups"]}) == 2   # 광고그룹명은 서로 다르다

    대상 = join.index_targets(붙임, join_traps, excluded=join_traps["제외그룹"])
    assert 대상.count(str(색인["17-3"]["groupId"])) == 1, \
        f"같은 번호의 마켓그룹이 {대상} 에 두 번 들어갔다 — 같은 그룹을 두 번 훑는다"
    assert len(대상) == len(set(대상))
    # 15-2 도 두 행(19000000001 / 19000000009)이 쓰지만 groupId 는 1개다
    assert 대상.count(str(색인["15-2"]["groupId"])) == 1
    # 제외 번호의 groupId 는 목록에 없다 (D-18)
    assert str(색인["13-2"]["groupId"]) not in 대상
    # 번호가 불사자에 없는 9-9 도 훑을 대상이 아니다
    assert 대상 == sorted(대상)
    assert len(대상) == 4, f"훑을 그룹이 {len(대상)}개다: {대상}"


# ── 해상률 · 미해소 사유 ────────────────────────────────────────────────────

def test_해상률(result_traps, join_traps):
    """`resolution()` 이 전체/번호해소/번호미해소/상품해소를 낸다 (JOIN-01).

    ⚠️ **광고청소 버킷과 시스템 버킷을 절대 한 숫자로 합치지 않는다** (Pitfall 3).
    "미해소 5행" 만 띄우면 그게 광고 쪽 청소 대상인지 우리가 안 본 것인지 알 수 없다.
    """
    붙임 = _붙인다(result_traps, join_traps)
    집계 = join.resolution(붙임)

    assert 집계["전체"] == 9
    assert 집계["번호해소"] == 7        # 추출실패 1 + 번호없음 1 을 뺀 값
    assert 집계["번호미해소"] == 2
    assert 집계["번호해소"] + 집계["번호미해소"] == 집계["전체"]
    assert 집계["상품해소"] == 4        # 히트만. 미스·불일치·미조회는 해소가 아니다

    # 두 버킷이 **따로** 있고 사유가 겹치지 않는다
    assert 집계["광고청소"]["행"] == 2
    assert 집계["광고청소"]["그룹"] == 2
    assert 집계["광고청소"]["사유별"] == {"추출실패": 1, "번호없음": 1}
    assert 집계["시스템"]["행"] == 3
    assert 집계["시스템"]["사유별"] == {"미조회": 1, "미스": 1, "불일치": 1}
    assert set(집계["광고청소"]["사유별"]) & set(집계["시스템"]["사유별"]) == set()

    # 합친 숫자를 내보내는 키가 아예 없다 — 있으면 화면이 그걸 집어 쓴다
    for 금지 in ("미해소", "미해소행", "미해소계", "해상률", "비율"):
        assert 금지 not in 집계, f"'{금지}' 가 두 버킷을 한 숫자로 합친다 (Pitfall 3)"


def test_실회차_해상률(result_join_real, bulsaja_groups_real):
    """실회차 ③⑤ 194행의 **번호층 해상률을 실측으로 고정**한다 (JOIN-01).

    🔴 **VALIDATION 기댓값은 179/194 · 실측은 92/194 다.**
    차이 사유: `result_join_real.json` 은 2026-09-20 회차, 즉 용팀장이 광고그룹을
    **정리하기 전** 스냅샷이다. CONTEXT 의 179 는 정리(69→58그룹, 번호 9건 정정)를
    끝낸 뒤 그 이름을 같은 회차에 다시 입혀 재판정한 값이라, 이 디스크 픽스처로는
    재현되지 않는다. 179 를 보려면 **정리 후 광고 회차를 새로 떠야 한다** —
    그건 네이버 광고 API 를 다시 도는 일이고 이 플랜의 범위가 아니다.
    숫자를 맞추려고 픽스처를 고치는 순간 이 테스트는 아무것도 지키지 않는다.

    그래서 이 테스트가 실제로 지키는 것은 "92 가 맞다"가 아니라 **"92 를 만드는
    계산이 안 바뀐다"** 이다. 정리 후 회차로 픽스처를 갈아끼우면 이 숫자는 179 로
    올라야 하고, 그때 이 docstring 을 같이 고쳐라.

    분자는 불사자 마켓그룹 목록이 정한다 — 그래서 픽스처가 둘이다.
    """
    doc = {
        "run_dir": "2026-09-20",
        "마켓그룹": bulsaja_groups_real["그룹"],
        "제외그룹": None,     # 설정의 정본은 settings 한 곳 (03-04 결정)
        "행": [],             # 인덱스 구축 전 — 상품층 관측이 하나도 없다
    }
    rows = board.fold_products(result_join_real)
    # `excluded=()` 로 고정한다. workspace.toml 의 D-18 설정을 읽으면 이 회귀가
    # **PC 설정에 따라 숫자가 흔들린다** — 설정 연동은 라우트 테스트가 따로 본다.
    붙임 = join.attach(rows, result_join_real, doc,
                      excluded=(), done_tags=기작업태그들)
    집계 = join.resolution(붙임)

    # ── 모수 ──
    assert 집계["전체"] == 194, "③⑤ 행수가 194 가 아니다 — 픽스처가 바뀌었다"
    assert len(bulsaja_groups_real["그룹"]) == 86
    assert sum(1 for g in bulsaja_groups_real["그룹"]
               if join.market_number(g["그룹명"])) == 54

    # ── 번호층 해상률: 실측 92/194 (47%) ──
    # 179 가 나오면 픽스처를 **정리 후** 회차로 갈아끼운 것이다 — docstring 을 같이 고쳐라.
    # 0 이 나오면 마켓그룹 픽스처에서 번호가 지워진 것이다(익명화가 번호까지 바꿨다).
    assert 집계["번호해소"] == 92
    assert 집계["번호미해소"] == 102
    assert 집계["번호해소"] + 집계["번호미해소"] == 집계["전체"]

    # ── 상품층은 0 이다. 인덱스를 아직 한 번도 안 훑었다 ──
    # **이건 실패가 아니라 정확한 상태다.** 여기가 0 이 아니게 되는 건 03-07 실탄 뒤다.
    assert 집계["상품해소"] == 0

    # ── 두 버킷을 따로 단언한다 (Pitfall 3) ──
    # 광고청소 = 번호를 못 이은 102행. 이게 용팀장의 광고 청소 목록이고,
    # 실제로 2026-09-21 에 이 목록으로 69→58그룹 정리가 돌았다.
    assert 집계["광고청소"]["행"] == 102
    assert 집계["광고청소"]["그룹"] == 14       # 지울 대상은 그룹이고 행은 부산물이다
    assert 집계["광고청소"]["사유별"] == {"추출실패": 57, "번호없음": 45}
    # 57 = 번호가 통째로 없던 그룹 하나가 만든 행수(전체의 29%). 정리 후엔 0 이 된다.

    # 시스템 = 번호는 이었는데 **우리가 아직 안 본** 92행. 광고는 멀쩡하다.
    assert 집계["시스템"]["행"] == 92
    assert 집계["시스템"]["사유별"] == {"미조회": 92, "미스": 0, "불일치": 0}

    # 🔴 두 버킷의 합이 전체가 된다 — 그런데 **그 합을 내보내는 키는 없어야 한다.**
    assert 집계["광고청소"]["행"] + 집계["시스템"]["행"] == 집계["전체"]
    for 금지 in ("미해소", "해상률", "비율"):
        assert 금지 not in 집계

    # 청소 목록이 그룹 단위로 접힌다 — 102행을 그대로 띄우면 할 일 목록으로 못 쓴다
    청소 = join.cleanup_groups(붙임)
    assert len(청소) == 14
    assert sum(g["행수"] for g in 청소) >= 집계["광고청소"]["행"]
    assert 청소 == sorted(청소, key=lambda g: (-g["행수"], g["adGroup"]))

    # 인덱스 대상은 번호 기준 중복제거 뒤 31그룹이다 (RESEARCH 의 31 과 같은 수 —
    # 그 측정도 정리 전 회차였다). D-18 제외를 태우면 하나가 빠진다.
    assert len(join.index_targets(붙임, doc, excluded=())) == 31
    assert len(join.index_targets(붙임, doc, excluded=("13-2",))) == 30


def test_실회차_그룹픽스처에_실물이름이_없다(bulsaja_groups_real):
    """마켓그룹 픽스처가 진짜 이름을 담지 않는다 — 리터럴 가드와 같은 선이다.

    이름이 하나라도 새면 저장소가 공개될 때 영업 정보가 같이 나가고,
    `test_board.py::test_계정을_코드에_박지_않는다` 와도 충돌한다.
    """
    이름들 = [g["그룹명"] for g in bulsaja_groups_real["그룹"]]
    assert 이름들, "그룹이 비었다"
    새는것 = [n for n in 이름들 if "zzfake" not in n]
    assert not 새는것, f"실물 이름이 남았다: {새는것[:5]}"
    assert len(set(이름들)) == len(이름들), "익명화가 서로 다른 그룹을 같은 이름으로 접었다"
    # groupId 도 실물이 아니다 — 연번 가짜값이라 전부 같은 길이·같은 접두다
    ids = [g["groupId"] for g in bulsaja_groups_real["그룹"]]
    assert all(i.startswith("9") and len(i) == 7 for i in ids), ids[:5]
    assert len(set(ids)) == len(ids)


def test_미해소_사유_3종(result_traps, join_traps):
    """`추출실패` / `번호없음` / `미조회` 가 **서로 다른 값**이고 버킷이 갈린다 (JOIN-02 / D-18)."""
    붙임 = _붙인다(result_traps, join_traps)

    추출실패행 = _행(붙임, "19000000004")   # 광고그룹명에 번호가 없다
    번호없음행 = _행(붙임, "19000000005")   # 9-9 가 불사자에 없다
    미조회행 = _행(붙임, "19000000006")     # D-18 제외 그룹

    assert 추출실패행["사유코드"] == "추출실패"
    assert 번호없음행["사유코드"] == "번호없음"
    assert 미조회행["사유코드"] == "미조회"
    assert len({추출실패행["사유코드"], 번호없음행["사유코드"], 미조회행["사유코드"]}) == 3

    # 앞 둘은 **광고 쪽 오류** — 용팀장이 네이버 광고에서 지운다
    assert 추출실패행["버킷"] == "광고청소"
    assert 번호없음행["버킷"] == "광고청소"
    # 제외 그룹은 **우리가 안 본 것** — 광고는 멀쩡하다. 같은 칸에 담으면 멀쩡한 그룹을 지운다
    assert 미조회행["버킷"] == "시스템"
    assert 미조회행["사유코드"] != "번호없음", \
        "D-18 제외 그룹이 '번호없음'(광고 오류)으로 둔갑했다 — 이 페이즈 최대 오진이다"
    # 제외 그룹은 번호 자체는 멀쩡히 풀렸다 (불사자에 13-2 그룹이 실제로 있다)
    assert 미조회행["번호해소"] is True
    assert 번호없음행["번호해소"] is False

    # 미해소 행은 전부 해소가 아니고 상태 판정도 안 붙는다
    for r in (추출실패행, 번호없음행, 미조회행):
        assert r["해소"] is False
        assert r["상세상태"] is None
        assert r["productId"] is None


def test_사유에_광고그룹명(result_traps, join_traps):
    """미해소 사유 문자열에 **광고그룹명 원문**이 들어간다 (JOIN-02 설계요구 2).

    용팀장이 네이버 광고 화면에서 그 이름으로 찾아 지운다. 이름이 없으면
    "어딘가 잘못됐다" 는 사실만 남고 할 일이 안 된다.
    """
    붙임 = _붙인다(result_traps, join_traps)

    추출실패행 = _행(붙임, "19000000004")
    assert "zzfake이동식오피스" in 추출실패행["사유"], 추출실패행["사유"]

    번호없음행 = _행(붙임, "19000000005")
    assert "판매상품_9-9_zzfakecompany4" in 번호없음행["사유"]
    assert "9-9" in 번호없음행["사유"]        # 번호도 같이 — 불사자에서 찾을 때 쓴다

    미조회행 = _행(붙임, "19000000006")
    assert "판매상품_13-2_zzfakecompany5" in 미조회행["사유"]
    assert "13-2" in 미조회행["사유"]
    # 시스템 문제임이 드러나야 한다 — 광고를 고치라는 말로 읽히면 안 된다
    assert "제외" in 미조회행["사유"], 미조회행["사유"]

    # 해소된 행은 사유가 없다 (빈 문자열이 아니라 None)
    assert _행(붙임, "19000000001")["사유"] is None
    assert _행(붙임, "19000000001")["사유코드"] is None
    assert _행(붙임, "19000000001")["버킷"] is None


def test_청소목록은_그룹단위다(result_traps, join_traps):
    """`cleanup_groups()` 가 행이 아니라 **광고그룹** 단위로 접는다 (JOIN-02 설계요구 3).

    지울 대상은 그룹이고 행은 그 부산물이다. 실측에서 14개 그룹이 102행을 만들었다.
    """
    붙임 = _붙인다(result_traps, join_traps)
    목록 = join.cleanup_groups(붙임)

    assert len(목록) == 2
    이름들 = {g["adGroup"] for g in 목록}
    assert 이름들 == {"zzfake이동식오피스", "판매상품_9-9_zzfakecompany4"}

    for g in 목록:
        assert set(g) == {"adGroup", "번호", "사유코드", "행수", "계정들"}
        assert g["행수"] >= 1
        assert isinstance(g["계정들"], list) and g["계정들"]

    번호없음 = [g for g in 목록 if g["adGroup"].endswith("zzfakecompany4")][0]
    assert 번호없음["번호"] == "9-9"
    assert 번호없음["사유코드"] == "번호없음"
    assert 번호없음["계정들"] == ["zzbb"]

    추출실패 = [g for g in 목록 if g["adGroup"] == "zzfake이동식오피스"][0]
    assert 추출실패["번호"] is None
    assert 추출실패["사유코드"] == "추출실패"

    # 행수 내림차순 (지울 값어치 순)
    assert [g["행수"] for g in 목록] == sorted((g["행수"] for g in 목록), reverse=True)
    # 시스템 버킷은 청소 목록에 안 들어간다 — 광고는 멀쩡하다
    assert "판매상품_13-2_zzfakecompany5" not in 이름들


# ── 재검증 (JOIN-04) ────────────────────────────────────────────────────────

def test_히트도_재검증한다():
    """인덱스 히트를 **재검증 없이** 해소로 접지 않는다 (JOIN-04 / D-04).

    `mallProductId` 는 20일 물갈이로 재발급된다. 인덱스에 적힌 값만 보고 해소로
    접으면 **틀린 상품을 집는다.** 지금 관측한 값과 같아야만 히트다.
    """
    assert join.재검증판정("19000000001", "19000000001", False) == "히트"
    # 관측값이 없으면 히트가 나오지 않는다 — 재검증 자체를 못 한 것이다
    assert join.재검증판정("19000000001", None, False) != "히트"
    assert join.재검증판정("19000000001", None, False) == "미조회"
    assert join.재검증판정("19000000001", "", False) == "미조회"


def test_불일치는_미해소(result_traps, join_traps):
    """인덱스값과 관측값이 다르면 `불일치` 이고 해소가 아니다 (물갈이 재발급)."""
    assert join.재검증판정("19000000008", "19000000888", False) == "불일치"

    붙임 = _붙인다(result_traps, join_traps)
    행 = _행(붙임, "19000000008")
    assert 행["상품조회"] == "불일치"
    assert 행["해소"] is False
    assert 행["버킷"] == "시스템"          # 광고는 멀쩡하다 — 번호는 제대로 풀렸다
    assert 행["번호해소"] is True
    assert 행["상세상태"] is None          # 어느 상품인지 모르는데 상태를 붙이면 거짓말이다


def test_미조회는_미조회다():
    """`미조회=True` 면 값이 무엇이든 `미조회` 다 — **429 를 성공으로 접지 않는다.**"""
    assert join.재검증판정("19000000001", "19000000001", True) == "미조회"
    assert join.재검증판정(None, None, True) == "미조회"
    assert join.재검증판정(None, "19000000001", True) == "미조회"


def test_인덱스에_없으면_미스():
    """인덱스값이 없고 미조회도 아니면 `미스` — `미조회` 와 **다른 값**이다."""
    assert join.재검증판정(None, "19000000007", False) == "미스"
    assert join.재검증판정("", "19000000007", False) == "미스"
    assert join.재검증판정(None, None, False) == "미스"
    assert "미스" != "미조회"


def test_인덱스없음이_광고오류로_둔갑하지_않는다(result_traps):
    """`join_doc=None`(스캔 전)이면 **광고청소 버킷이 0** 이다 (Pitfall 3 의 핵심).

    그룹 목록을 아직 모르는 것과 그룹이 없는 것은 다르다. 조인을 안 돌린 상태에서
    청소 목록을 띄우면, 시스템이 놀고 있다는 사실이 "광고를 고쳐라" 로 둔갑한다.
    """
    rows = board.fold_products(result_traps)
    붙임 = join.attach(rows, result_traps, None)

    assert len(붙임) == 9
    assert {r["사유코드"] for r in 붙임} == {"미조회"}
    assert {r["버킷"] for r in 붙임} == {"시스템"}
    assert all(r["해소"] is False for r in 붙임)

    집계 = join.resolution(붙임)
    assert 집계["광고청소"]["행"] == 0, "스캔 전인데 광고 청소 대상이 생겼다 (Pitfall 3)"
    assert 집계["광고청소"]["그룹"] == 0
    assert 집계["광고청소"]["사유별"] == {"추출실패": 0, "번호없음": 0}
    assert 집계["시스템"]["행"] == 9
    assert join.cleanup_groups(붙임) == []
    assert join.index_targets(붙임, None) == []

    # 번호 자체는 채워 둔다 — 화면이 "무엇을 훑을 것인지" 를 보여줄 수 있어야 한다
    assert _행(붙임, "19000000001")["번호"] == "15-2"
    assert _행(붙임, "19000000004")["번호"] is None


# ── 팬아웃 · 기작업 · 프롬프트 인젝션 ──────────────────────────────────────

def test_팬아웃_N건(result_traps, join_traps):
    """사본 N건을 센다 — "이 버튼이 N건에 적용됩니다" 의 재료다 (JOIN-03 / D-06)."""
    붙임 = _붙인다(result_traps, join_traps)

    팬아웃 = _행(붙임, "19000000003")
    assert 팬아웃["사본N"] == 3
    assert 팬아웃["잠금혼재"] is True       # 사본 중 잠긴 것과 안 잠긴 것이 섞여 있다

    단일 = _행(붙임, "19000000001")
    assert 단일["사본N"] == 1               # 3 이면 다른 행의 사본을 긁어 왔다
    assert 단일["잠금혼재"] is False

    # 조인이 안 된 행은 **None 이다 (0 이 아니다)** — 0 은 "사본이 없다" 는 판정처럼 보인다
    미해소 = _행(붙임, "19000000004")
    assert 미해소["사본N"] is None
    assert 미해소["잠금혼재"] is None


def test_기작업은_기본선택에서_빠진다(result_traps, join_traps):
    """기작업 상품이 **기본 선택에서만** 빠지고 목록에는 그대로 남는다 (D-08 / STATE-05).

    숨기면 용팀장이 "왜 이 상품이 안 보이지" 를 코드에서 찾아야 한다.
    회색으로 보이고 태그가 보이고, 직접 체크하면 대상이 된다.
    """
    붙임 = _붙인다(result_traps, join_traps)
    고를것 = join.selectable(붙임)

    태그기작업 = _행(붙임, "19000000009")   # `구매_가공완료` 태그 (사람 손자국)
    AI기작업 = _행(붙임, "19000000001")     # aiImageGenerated (기계 기록)

    # ① 목록에는 **남아 있다**
    assert 태그기작업["기작업"] is True
    assert 태그기작업["기작업태그"] == "구매_가공완료"
    assert 태그기작업["상세상태"] == state.단순번역만   # 태그를 상태에 섞지 않았다 (Pitfall 8)
    assert AI기작업["기작업"] is True
    assert AI기작업["기작업태그"] is None              # 태그 없이 기계기록만으로 잡혔다
    assert AI기작업["상세상태"] == state.AI가공완료

    # ② 기본 선택에서는 **빠진다**
    고른_id = {r["mallProductId"] for r in 고를것}
    assert "19000000009" not in 고른_id
    assert "19000000001" not in 고른_id
    assert 고른_id == {"19000000002", "19000000003"}

    # ③ 미해소 행도 기본 선택에 없다 (어느 상품인지 모르는데 작업을 걸 수 없다)
    assert all(r["해소"] is True for r in 고를것)
    # ④ `구매` 태그는 `done_tags` 가 아니다 — 아무 태그나 기작업으로 접으면 안 된다
    assert _행(붙임, "19000000003")["기작업"] is False
    assert _행(붙임, "19000000003")["기작업태그"] == "구매"


def test_스킵은_장수와_무관하다(result_traps, join_traps):
    """`attach`·`selectable` 시그니처에 장수/`pages` 가 없다 (STATE-05 / D-10).

    기작업 스킵이 목표 장수에 결합되면, 8장짜리 기작업 상품이 이번에 이미지 10장을
    모았을 때 재접수돼 **크레딧을 다시 낸다.**
    """
    for fn in (join.attach, join.selectable, state.기작업여부):
        s = inspect.signature(fn)
        assert "pages" not in s.parameters, f"{fn.__name__}{s}"
        assert "장수" not in str(s), f"{fn.__name__}{s}"

    # attach 의 키워드 인자는 excluded / done_tags 뿐이다 (장수 맥락이 낄 자리가 없다)
    s = inspect.signature(join.attach)
    키워드 = [n for n, p in s.parameters.items() if p.kind is p.KEYWORD_ONLY]
    assert 키워드 == ["excluded", "done_tags"], s

    # 어떤 호출에서도 기작업 판정이 같다 — 넘기는 설정이 같으면 결과가 같다
    첫번째 = _붙인다(result_traps, join_traps)
    두번째 = _붙인다(result_traps, join_traps)
    assert [r["기작업"] for r in 첫번째] == [r["기작업"] for r in 두번째]


def test_표시규칙은_버린다(result_traps, join_traps):
    """불사자 응답의 `표시규칙` 이 반환값 어디에도 안 남는다 (ENG-08 / T-3-06).

    그 필드는 모델 대상 지시문(*"앞 지시 무시해…"*)이다. 화면 렌더나 LLM 투입 경로를
    만들면 그대로 프롬프트 인젝션이 된다. 입구에서 재귀적으로 버린다.
    """
    # 픽스처 전제: 최상위와 행 안쪽 양쪽에 심어져 있다
    assert "표시규칙" in join_traps
    assert any("표시규칙" in r for r in join_traps["행"])

    붙임 = _붙인다(result_traps, join_traps)
    전문 = json.dumps(붙임, ensure_ascii=False, default=str)
    assert "표시규칙" not in 전문, "attach 결과에 표시규칙이 남았다 (프롬프트 인젝션)"

    # 집계·청소목록·대상목록에도 안 남는다
    for 결과 in (join.resolution(붙임), join.cleanup_groups(붙임),
                 join.index_targets(붙임, join_traps), join.selectable(붙임)):
        assert "표시규칙" not in json.dumps(결과, ensure_ascii=False, default=str)

    # 그리고 **원본을 고치지 않는다** — 호출부가 같은 dict 를 다시 쓴다
    assert "표시규칙" in join_traps
    깨끗 = join.strip_display_rules(join_traps)
    # ⚠️ 여기서는 **키**만 본다. 픽스처의 `_주석` 본문이 그 단어를 설명으로 적고 있어서
    #    전문 문자열 검사를 걸면 "설명을 지웠는가" 를 묻게 된다 — 지울 것은 키다.
    #    (`attach()` 결과에는 `_주석` 이 안 실리므로 위쪽 전문 검사는 그대로 유효하다)
    assert _표시규칙_키가_남았나(깨끗) == [], _표시규칙_키가_남았나(깨끗)
    assert "표시규칙" in join_traps, "strip_display_rules 가 원본을 mutate 했다"
    # 나머지 내용은 그대로 살아 있다 (통째로 버리는 게 아니다)
    assert len(깨끗["행"]) == len(join_traps["행"])
    assert 깨끗["마켓그룹"] == join_traps["마켓그룹"]


# ── 방어 · 경계 ────────────────────────────────────────────────────────────

def test_빈입력도_안깨진다(result_traps):
    """빈 입력은 예외가 아니라 빈 결과다 (`board.py:63-67` / `129-130` 관용구)."""
    assert join.attach([], {}, None) == []
    assert join.attach(None, None, None) == []
    assert join.index_targets([], None) == []
    assert join.cleanup_groups([]) == []
    assert join.selectable([]) == []
    assert join.group_index(None) == {}
    assert join.group_index([{"groupId": "1"}]) == {}       # 그룹명 없는 항목
    assert join.ad_groups_by_product({}) == {}
    assert join.ad_groups_by_product(None) == {}
    assert join.strip_display_rules(None) is None
    assert join.strip_display_rules([]) == []

    집계 = join.resolution([])
    assert 집계["전체"] == 0
    assert 집계["광고청소"]["행"] == 0
    assert 집계["시스템"]["행"] == 0

    # result 만 있고 조인 산출물이 없어도 행 수는 유지된다 (화면이 통째로 비면 안 된다)
    rows = board.fold_products(result_traps)
    assert len(join.attach(rows, result_traps, None)) == len(rows)


def test_원본_행을_고치지_않는다(result_traps, join_traps):
    """`attach` 가 `fold_products` 결과를 **복사해서** 돌려준다.

    원본을 mutate 하면 같은 rows 를 두 번 쓰는 호출부(보드 + 집계)가 조용히 어긋난다.
    """
    rows = board.fold_products(result_traps)
    원본키 = [set(r) for r in rows]
    붙임 = join.attach(rows, result_traps, join_traps, excluded=join_traps["제외그룹"])

    assert [set(r) for r in rows] == 원본키, "attach 가 원본 행에 키를 더했다"
    assert all("사유코드" not in r for r in rows)
    assert 붙임 is not rows
    for a, b in zip(rows, 붙임):
        assert a is not b


def test_조인은_네트워크도_파일도_안_연다():
    """`join.py`·`state.py` 는 dict 만 받는다 — MCP·DB·파일 접촉 0 (D-19 / T-3-10).

    웹앱 전용 venv 에는 불사자 클라이언트가 쓰는 HTTP 패키지가 없다. import 하는 순간
    ImportError 이고, 그게 이 설계의 물리적 근거다. 문자열 검사로 그 선을 고정한다.
    """
    for 파일 in ("join.py", "state.py"):
        src = (WEBAPP / 파일).read_text(encoding="utf-8")
        for 금지 in ("eroomlib", "requests", "fastapi", "starlette",
                     "APIRouter", "sqlite3", "subprocess", "httpx", "urllib"):
            assert 금지 not in src, f"{파일} 에 '{금지}' 가 있다 (D-19)"
        assert "open(" not in src, f"{파일} 이 파일을 연다 — dict 만 받아야 한다"


# ── 팬아웃 미조회 — "사본 0건" 과 "못 물어봤다" 를 구분한다 (CR-02 / D-08) ──────

def _팬아웃실패로_바꾼다(join_traps, mpid):
    """조인 산출물 사본을 만들어 한 행만 **팬아웃 조회 실패** 모양으로 바꾼다.

    CLI(`bulsaja_scan.배치조회`)가 `find_by_code` 를 못 받았을 때 적는 모양 그대로다:
    사본은 `[]` 가 아니라 `None`(못 물어봤다), 그룹태그는 `None`, 그리고 그 사실을
    `팬아웃미조회` 로 남긴다. 번호층 관측(`관측_smartstore`)은 멀쩡하다 —
    팬아웃만 조용히 실패한 경우가 이 고장의 본체다.
    """
    문서 = json.loads(json.dumps(join_traps, ensure_ascii=False))
    for 행 in 문서["행"]:
        if 행.get("mallProductId") == mpid:
            행["사본"] = None
            행["그룹태그"] = None
            행["팬아웃미조회"] = True
            return 문서
    raise AssertionError(f"픽스처에 {mpid} 행이 없다")


def test_팬아웃_미조회는_사본0건을_단언하지_않는다(result_traps, join_traps):
    """조회 실패 행의 `사본N` 은 **`0` 이 아니라 빈칸(None)** 이다 (JOIN-03 / CR-02).

    `0` 은 "사본이 없다" 는 **판정처럼** 보이는데 실제로는 안 본 것이다
    (`join.py:68-70` 의 "분모가 없으면 비율도 없다" 와 같은 정신).
    """
    문서 = _팬아웃실패로_바꾼다(join_traps, "19000000002")
    붙임 = _붙인다(result_traps, join_traps, join_doc=문서)
    행 = _행(붙임, "19000000002")

    assert 행["해소"] is True, "팬아웃 실패가 번호층 해소까지 죽였다 — 과잉 방어다"
    assert 행["팬아웃미조회"] is True
    assert 행["사본N"] is None, f"못 물어본 것을 '사본 0건' 으로 단언했다: {행['사본N']}"
    assert 행["잠금혼재"] is None

    # 멀쩡히 물어본 행은 그대로다 — 한 행의 실패가 다른 행을 오염시키지 않는다
    정상 = _행(붙임, "19000000003")
    assert 정상["사본N"] == 3 and 정상["팬아웃미조회"] is False


def test_팬아웃_미조회는_기본선택에서_빠진다(result_traps, join_traps):
    """태그를 못 읽은 행에 크레딧을 태우지 않는다 (D-08 / STATE-05 / CR-02).

    `그룹태그` 가 비어 `기작업 = False` 가 되는 것이 이 고장의 값비싼 얼굴이다 —
    `구매_가공완료` 가 붙은 상품이 조회 실패 **한 번**으로 기본 선택에 들어가고,
    Phase 5 가 크레딧을 재지불한다. 기작업과 **같은 수법**으로 막는다:
    목록에는 남고(사람이 직접 체크하면 대상이 된다) 기본 선택에서만 빠진다.
    """
    문서 = _팬아웃실패로_바꾼다(join_traps, "19000000002")
    붙임 = _붙인다(result_traps, join_traps, join_doc=문서)

    # ① 목록에는 남는다 — 숨기면 "왜 이 상품이 안 보이지" 를 코드에서 찾아야 한다
    assert _행(붙임, "19000000002")["해소"] is True

    # ② 기본 선택에서는 빠진다
    고른_id = {r["mallProductId"] for r in join.selectable(붙임)}
    assert "19000000002" not in 고른_id, "팬아웃을 못 읽은 행에 기본으로 크레딧을 태운다"
    assert 고른_id == {"19000000003"}

    # ③ 팬아웃이 멀쩡한 회차는 아무것도 안 바뀐다 (과잉 방어로 대상이 사라지지 않는다)
    정상선택 = {r["mallProductId"] for r in join.selectable(_붙인다(result_traps, join_traps))}
    assert 정상선택 == {"19000000002", "19000000003"}


def test_옛_산출물은_팬아웃미조회가_없어도_안깨진다(result_traps, join_traps):
    """`팬아웃미조회` 키가 없는 옛 조인 산출물도 그대로 읽힌다 (하위호환).

    디스크에 이미 남아 있는 산출물에는 이 키가 없다. 없으면 `False` 로 읽어
    **예전과 같은 판정**을 낸다 — 새 키가 없다는 이유로 전 행이 기본 선택에서
    빠지면 화면이 통째로 못 쓰게 된다.
    """
    붙임 = _붙인다(result_traps, join_traps)
    assert all(r["팬아웃미조회"] is False or r["팬아웃미조회"] is None for r in 붙임)
    assert _행(붙임, "19000000003")["사본N"] == 3
