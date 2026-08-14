#!/usr/bin/env python3
"""category_gate.py 순수 함수 회귀 테스트 (pytest 불필요 — 그냥 실행).

대상: 붙박이 게이트·재고 스캔이 **함께 쓰는** 판정부 —
  gate_select(무엇을 삭제 대상으로 고르나) · already_gone(무엇을 이미 없는 걸로 보나) ·
  _make_queue(배치가 그룹 경계를 넘지 않나) · pending_delete_ids(미삭제분을 다시 잡나) ·
  final_category(D냐 C냐) · is_near_save(구분 표기 대상인가).

시트·MCP·블랙리스트 다운로드를 건드리지 않는다(조각은 손으로 만든 CategoryGate).
    .venv/bin/python .claude/skills/bulsaja-category-fix/scripts/test_category_gate.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# category_gate 를 먼저 든다 — 그게 `.claude/lib` 를 sys.path 에 올린다(eroomlib 앵커).
from category_gate import (  # noqa: E402
    GATED_TASKS, V_PENDING, _is_gone, _make_queue, _merge_targets, already_gone,
    final_category, gate_select, is_near_save, pending_delete_ids,
)
from eroomlib import matrix  # noqa: E402
from eroomlib.exclusion import CategoryGate  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

FAILED = []

GATE = CategoryGate(["생활/건강>공구>안전용품", ">펌프", "여성의류"])


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        FAILED.append(name)


def R(pid, cat, **kw):
    d = {"productId": pid, "상품명": "가", "카테고리": cat}
    d.update(kw)
    return d


def MROW(**kw):
    """현황판 행 1개 — 지정 안 한 작업 열은 빈칸."""
    rec = {"row": 2, "상품": "가"}
    for t in matrix.TASKS:
        rec[t] = kw.get(t, "")
    return rec


# ── gate_select ─────────────────────────────────────────────────────────────
def test_select():
    print("\n[gate_select]")
    m = {"P1": MROW(카테고리="완료"), "P2": MROW(카테고리="완료"),
         "P3": MROW(카테고리="완료")}
    recs = [R("P1", "생활/건강>공구>안전용품>기타안전용품"),
            R("P2", "생활/건강>공구>원예공구>농기계"),
            R("P3", "생활/건강>공구>펌프>수중펌프")]
    t, s = gate_select(recs, GATE, m)
    check("걸린 것만 고른다", [x["productId"] for x in t] == ["P1", "P3"],
          str([x["productId"] for x in t]))
    check("판정 수", s["판정"] == 3 and s["제외대상"] == 2, str(s))
    check("걸린 조각 기재", t[1]["조각"] == ">펌프", t[1]["조각"])
    check("조각 전체 보존", t[0]["조각전체"] == ["생활/건강>공구>안전용품"],
          str(t[0]["조각전체"]))

    # 카테고리가 경로가 아닌 것 — 구버전 D열의 `(현행유지)` 리터럴·미설정
    t, s = gate_select([R("P1", "(현행유지)"), R("P2", "미설정"), R("P3", "")],
                       GATE, m)
    check("경로 아닌 값은 판정 안 함", not t and s["카테고리없음"] == 3, str(s))

    # 이미 없는 상품 — 해당없음 / 상품삭제 / 삭제대기
    for label, val in (("해당없음", matrix.NA),
                       ("상품삭제", "상품삭제(제외카테고리·자동)"),
                       ("삭제대기", V_PENDING)):
        mm = {"P1": MROW(**{GATED_TASKS[0]: val})}
        t, s = gate_select([R("P1", "생활/건강>공구>펌프>수중펌프")], GATE, mm)
        check(f"이미 없는 상품 제외({label})", not t and s["이미삭제"] == 1, str(s))

    # 현황판에 행이 없는 상품 — 표시는 못 하지만 **삭제 대상에서 빼지 않는다**
    t, s = gate_select([R("PX", "생활/건강>공구>펌프>수중펌프")], GATE, {"P1": MROW()})
    check("현황판 없어도 대상 유지", len(t) == 1 and t[0]["현황판없음"] is True, str(t))
    check("현황판없음 집계", s["현황판없음"] == 1, str(s))

    # 현황판을 아예 안 주면(m=None) 표시 판단을 하지 않는다
    t, _ = gate_select([R("PX", "여성의류>원피스")], GATE, None)
    check("m 없으면 현황판없음 아님", len(t) == 1 and t[0]["현황판없음"] is False)

    # 근접저장 플래그는 그대로 실린다(종합보고 구분 표기용)
    t, _ = gate_select([R("P1", "여성의류>원피스", 근접저장=True)], GATE, None)
    check("근접저장 전달", t[0]["근접저장"] is True)

    check("빈 입력", gate_select([], GATE, m)[0] == [])
    check("productId 없는 행 무시", gate_select([{"카테고리": "여성의류>원피스"}],
                                             GATE, m)[0] == [])


# ── already_gone ────────────────────────────────────────────────────────────
def test_already_gone():
    print("\n[already_gone]")
    check("빈칸은 살아있음", not already_gone(MROW()))
    check("완료는 살아있음", not already_gone(MROW(상품명="완료")))
    check("재작업은 살아있음", not already_gone(MROW(상품명="재작업(카테고리: …)")))
    check("해당없음", already_gone(MROW(옵션=matrix.NA)))
    check("상품삭제 접두", already_gone(MROW(썸네일="상품삭제(실물불명·자동)")))
    check("삭제대기 접두", already_gone(MROW(업로드=V_PENDING)))
    check("게이트 밖 열은 안 본다", not already_gone(MROW(수집=matrix.NA)))


# ── _is_gone (삭제 응답 판독) ────────────────────────────────────────────────
def test_is_gone():
    """③ "휴지통에 있다" 계열 응답을 성공으로 읽는가 (2026-08-14).

    발단: 마커가 `이미 휴지통` 하나뿐이라 형제 문구인
    `업로드된 마켓이 없어 소싱 상품을 휴지통으로 이동함` 이 실패로 집계됐다.
    실제로는 지워진 건데 `삭제대기` 로 남아 잔여 건수가 계속 부풀었다.
    """
    print("\n[_is_gone]")
    g = _is_gone
    check("③ 이미 휴지통", g("업로드된 마켓이 없고 이미 휴지통인 상품을 확인함"))
    check("③ 방금 휴지통으로 이동", g("업로드된 마켓이 없어 소싱 상품을 휴지통으로 이동함"))
    check("실패 접두가 붙어도 잡는다", g("실패: 업로드된 마켓이 없어 소싱 상품을 휴지통으로 이동함"))
    check("부정형은 성공이 아니다", not g("소싱 상품 휴지통으로 이동 실패"))
    check("접수는 아니다", not g("삭제 대기열 접수됨"))
    check("잠금은 아니다", not g("잠금된 상품은 삭제 불가"))
    check("미접수는 아니다", not g("삭제 작업 원자적 생성 실패로 전체 그룹 미접수"))
    check("빈 응답", not g("") and not g(None))


# ── _make_queue ─────────────────────────────────────────────────────────────
def test_queue():
    print("\n[_make_queue]")
    ts = ([{"productId": f"A{i}", "그룹": "G1", "sheetId": "s1", "상품명": "가",
            "카테고리": "c", "조각": "f", "근접저장": False} for i in range(5)]
          + [{"productId": f"B{i}", "그룹": "G2", "sheetId": "s2", "상품명": "나",
              "카테고리": "c", "조각": "f", "근접저장": True} for i in range(3)])
    q = _make_queue(ts, batch_size=2)
    check("그룹 경계를 넘지 않는다", all(len({x for x in b["productIds"]}) and
                                 b["그룹"] in ("G1", "G2") for b in q))
    check("G1 3배치 · G2 2배치", [len(b["productIds"]) for b in q] == [2, 2, 1, 2, 1],
          str([len(b["productIds"]) for b in q]))
    check("한 배치는 한 그룹뿐",
          all(len({t["productId"][0] for t in b["상품"]}) == 1 for b in q))
    check("sheetId 동행", q[0]["sheetId"] == "s1" and q[-1]["sheetId"] == "s2")
    check("근접저장 실림", q[-1]["상품"][0]["근접저장"] is True)
    check("빈 입력", _make_queue([]) == [])


# ── _merge_targets ──────────────────────────────────────────────────────────
def test_merge_targets():
    print("\n[_merge_targets]")
    old = [{"productId": "P1", "조각": "old"}, {"productId": "P2", "조각": "x"}]
    new = [{"productId": "P1", "조각": "new"}, {"productId": "P3", "조각": "y"}]
    got = _merge_targets(old, new)
    check("합집합 3건", len(got) == 3, str(len(got)))
    check("같은 상품은 나중 것", [g for g in got if g["productId"] == "P1"][0]["조각"] == "new")
    check("한 상품이 배치에 두 번 들지 않는다",
          len({g["productId"] for g in got}) == len(got))


# ── pending_delete_ids ──────────────────────────────────────────────────────
def test_pending_ids():
    print("\n[pending_delete_ids]")
    m = {
        "P1": MROW(**{t: V_PENDING for t in GATED_TASKS}),      # 전 열 표시
        "P2": MROW(**{GATED_TASKS[0]: V_PENDING}),              # 부분 표시(중간 실패)
        "P3": MROW(상품명="완료"),
        "P4": MROW(**{t: "상품삭제(제외카테고리·자동)" for t in GATED_TASKS}),
    }
    got = pending_delete_ids(m)
    check("부분 표시도 잡는다", sorted(got) == ["P1", "P2"], str(got))
    check("삭제 완료분은 안 잡는다", "P4" not in got)


# ── final_category · is_near_save (스캔 쪽 판정 회귀) ────────────────────────
def test_final_category():
    print("\n[final_category]")
    check("D 우선", final_category(
        {"변경카테고리": "가>나", "이전카테고리": "다>라", "상태": "자동저장완료"}) == "가>나")
    check("D 비면 C", final_category(
        {"변경카테고리": "", "이전카테고리": "다>라", "상태": "이미정확"}) == "다>라")
    check("D 가 리터럴이면 C", final_category(
        {"변경카테고리": "(현행유지)", "이전카테고리": "다>라", "상태": "저장완료"}) == "다>라")
    check("기존유지는 C 만", final_category(
        {"변경카테고리": "가>나", "이전카테고리": "다>라", "상태": "기존유지"}) == "다>라")
    check("둘 다 없으면 빈값", final_category(
        {"변경카테고리": "미설정", "이전카테고리": "", "상태": "이미정확"}) == "")

    print("\n[is_near_save]")
    check("I열 플래그", is_near_save({"플래그": "근접저장(셀하≠불사자)", "상태": "저장완료"}))
    check("구버전 G열 상태", is_near_save({"플래그": "", "상태": "근사매칭저장"}))
    check("정규 경로는 아님", not is_near_save({"플래그": "", "상태": "자동저장완료"}))
    check("유도저장은 아님", not is_near_save({"플래그": "유도저장(1단계)",
                                          "상태": "저장완료"}))


# ── gate_records — 시트 쓰기 계약(캐시 동기화)·큐 파일 ───────────────────────
def test_gate_records():
    """시트·블랙리스트를 가짜로 갈아끼우고 **캐시 동기화**를 확인한다.

    이게 이 파일에서 제일 중요한 검증이다. `matrix.mark_many` 는 열을 통짜로 되쓰면서
    **넘겨받은 캐시를 정본으로** 본다. 게이트가 찍은 값을 캐시에 반영하지 않으면,
    바로 뒤에 도는 상품명 재작업 이관(`flag_many`)이 옛 값으로 열을 되써서 방금 찍은
    `삭제대기` 를 지운다 — 그러면 그 상품이 다시 상품명 대상이 된다(막으려던 것과 정반대).
    """
    print("\n[gate_records]")
    import json
    import shutil
    import tempfile
    import category_gate as G

    writes = []

    def fake_mark_many(sheet, task, values, tab=None, matrix=None,
                       preserve_redo=False):
        # 실제 mark_many 계약 재현: 대상 외 행은 **캐시 값**을 그대로 실어 되쓴다.
        col = {pid: str(values.get(pid, rec.get(task) or "")).strip()
               for pid, rec in matrix.items()}
        writes.append((task, col))
        return sum(1 for pid, v in col.items()
                   if v != (matrix[pid].get(task) or "").strip())

    orig_mark, orig_gate = G.matrix.mark_many, G.category_gate
    G.matrix.mark_many, G.category_gate = fake_mark_many, (lambda path=None: GATE)
    run_dir = tempfile.mkdtemp(prefix="gatetest-")
    try:
        m = {"P1": MROW(카테고리="완료"), "P2": MROW(카테고리="완료")}
        targets, stats = G.gate_records(
            "sheet1", [R("P1", "생활/건강>공구>펌프>수중펌프"),
                       R("P2", "생활/건강>공구>원예공구>농기계")],
            run_dir=run_dir, m=m, group="G1", col_sleep=0, log=lambda *a: None)
        check("걸린 것만 대상", [t["productId"] for t in targets] == ["P1"], str(targets))
        check("찍은 열 = 뒤 7개", [t for t, _ in writes] == list(GATED_TASKS),
              str([t for t, _ in writes]))
        check("대상만 삭제대기", all(c["P1"] == V_PENDING and c["P2"] == ""
                                for _, c in writes))
        check("★캐시 동기화", all(m["P1"][t] == V_PENDING for t in GATED_TASKS),
              str(m["P1"]))
        check("카테고리 열은 안 건드린다", m["P1"]["카테고리"] == "완료"
              and "카테고리" not in [t for t, _ in writes])
        check("그룹·시트 실림", targets[0]["그룹"] == "G1"
              and targets[0]["sheetId"] == "sheet1")

        # 뒤이어 도는 재작업 이관이 게이트 표시를 지우지 않는가(같은 캐시를 쓴다)
        writes.clear()
        fake_mark_many("sheet1", "상품명", {"P2": "재작업(카테고리: …)"}, matrix=m)
        check("★재작업 이관이 삭제대기를 덮지 않는다",
              writes[0][1]["P1"] == V_PENDING and writes[0][1]["P2"].startswith("재작업"),
              str(writes[0][1]))

        with open(os.path.join(run_dir, "gate", "delete_queue.json"),
                  encoding="utf-8") as f:
            q = json.load(f)
        check("삭제 큐 생성", len(q) == 1 and q[0]["productIds"] == ["P1"], str(q))

        # 같은 run-dir 에 두 번째 게이트(apply → steer) — 합쳐지고 중복되지 않는다
        m2 = {"P3": MROW(카테고리="완료")}
        G.gate_records("sheet1", [R("P3", "여성의류>원피스", 근접저장=True)],
                       run_dir=run_dir, m=m2, group="G1", col_sleep=0,
                       log=lambda *a: None)
        with open(os.path.join(run_dir, "gate", "targets.json"), encoding="utf-8") as f:
            allt = json.load(f)
        check("두 번째 게이트가 누적된다",
              sorted(t["productId"] for t in allt) == ["P1", "P3"], str(allt))

        # 대상 0건이면 시트를 건드리지 않는다
        writes.clear()
        t0, _ = G.gate_records("sheet1", [R("P9", "가전>주방>냄비")], run_dir=run_dir,
                               m={"P9": MROW()}, col_sleep=0, log=lambda *a: None)
        check("0건이면 쓰기 없음", not t0 and not writes)
    finally:
        G.matrix.mark_many, G.category_gate = orig_mark, orig_gate
        shutil.rmtree(run_dir, ignore_errors=True)


if __name__ == "__main__":
    test_select()
    test_already_gone()
    test_is_gone()
    test_queue()
    test_merge_targets()
    test_pending_ids()
    test_final_category()
    test_gate_records()
    print("\n" + "=" * 52)
    if FAILED:
        print(f"실패 {len(FAILED)}건: {FAILED}")
        sys.exit(1)
    print("전부 통과")
