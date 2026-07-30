#!/usr/bin/env python3
"""Step 0 인벤토리 — 54그룹 전건 목록·스냅샷·이중 키 중복 맵 (LLM 0, 재시작 가능).

전부 멱등: collect 는 그룹 파일이 있으면 스킵, ensure 는 스냅샷 캐시 적중이 곧
체크포인트(끊겨도 다시 돌리면 이어서), build 는 로컬 재계산이라 몇 번 돌려도 같다.

CLI:
    python .claude/lib/eroomlib/runner/inventory.py collect [--filter 그룹명일부] [--force]
    python .claude/lib/eroomlib/runner/inventory.py ensure  [--chunk 500] [--retry-errors]
    python .claude/lib/eroomlib/runner/inventory.py build   [--no-matrix]
    python .claude/lib/eroomlib/runner/inventory.py verify  [--sample 100]
    python .claude/lib/eroomlib/runner/inventory.py report
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from eroomlib import dedup, snapshot  # noqa: E402
from eroomlib.config import cfg  # noqa: E402

REQUIRE = ("불사자코드", "타오바오상품번호")
_ROOT_OVERRIDE = None  # 테스트가 갈아끼운다


class ConsecutiveFailure(RuntimeError):
    """청크가 연속으로 전멸 — 서버 장애로 보고 멈춘다(재시도 폭풍 방지)."""


def _root():
    return _ROOT_OVERRIDE or cfg("paths.dedup_root", required=True)


def _groups_dir():
    d = os.path.join(_root(), "inventory", "groups")
    os.makedirs(d, exist_ok=True)
    return d


def _load_groups():
    """수집된 그룹 파일 전부 → [{groupId, 그룹명, items}]"""
    out = []
    for fn in sorted(os.listdir(_groups_dir())):
        if fn.endswith(".json"):
            out.append(dedup.load_json(os.path.join(_groups_dir(), fn), {}))
    return out


def _membership():
    """그룹 파일들 → {pid: {groupId, 그룹명, 상태코드}}. 뒤에 나온 그룹이 이기지 않게
    먼저 본 것을 유지한다(같은 pid 가 두 그룹에 있을 수 없지만 방어)."""
    memb = {}
    for g in _load_groups():
        for it in g.get("items", []):
            memb.setdefault(it["productId"], {
                "groupId": g["groupId"], "그룹명": g["그룹명"],
                "상태코드": it.get("상태코드")})
    return memb


def _tracked_group_names():
    """마스터 인덱스(00_진행 시트)에 등록된 그룹명 집합 — "54마켓 전체" 관리 대상 범위.

    실측(2026-07-28): 불사자 계정에는 그룹이 85개 있지만 마스터 인덱스엔 52개뿐이다.
    나머지 33개는 엔잡곰·열·송·엽 같은 테스트/레거시 그룹 — 기본은 이 목록으로 좁혀
    Step 0 통계가 오염되지 않게 한다. `--all` 로 원본 전체를 쓸 수 있다.
    """
    from eroomlib import matrix
    return {g for g, _ in matrix.index_groups()}


def run_collect(mcp, filter_, force, sleep, log=print, all_groups=False):
    groups = mcp.call_tool("bulsaja_market_groups", {}).get("그룹", [])
    if not all_groups:
        tracked = _tracked_group_names()
        groups = [g for g in groups if str(g.get("그룹명", "")) in tracked]
    if filter_:
        groups = [g for g in groups if filter_ in str(g.get("그룹명", ""))]
    done = skipped = 0
    for g in groups:
        path = os.path.join(_groups_dir(), f"{g['groupId']}.json")
        if os.path.exists(path) and not force:
            skipped += 1
            continue
        items = mcp.collect_group(g["groupId"], sleep=sleep,
                                  log=log if log else None)
        dedup.save_json(path, {"groupId": g["groupId"], "그룹명": g.get("그룹명", ""),
                               "수집일": time.strftime("%Y-%m-%d %H:%M:%S"),
                               "items": items})
        done += 1
        if log:
            log(f"[{done}] {g.get('그룹명')} — {len(items)}건")
    if log:
        log(f"collect 완료: 신규 {done} · 스킵 {skipped} · 총 그룹 {len(groups)}")


def _pending_pids(pids):
    """require 필드가 갖춰진 캐시가 없는 pid만 — 이번 청크가 실제로 네트워크를 탈 대상.
    이게 없으면 청크에 캐시 적중이 섞였을 때 "전멸" 판정이 무력화된다(피어리뷰 지적) —
    재실행 중 서버가 죽어도 청크마다 캐시 적중이 한둘 섞이면 dead_streak 이 계속 0으로
    리셋돼 연속전멸 3회 중단이 영영 안 걸린다."""
    out = []
    for pid in pids:
        rec = snapshot.load(pid)
        if rec is None or any(k not in rec for k in REQUIRE):
            out.append(pid)
    return out


def run_ensure(mcp, chunk, sleep, log=print, max_dead_chunks=3, only_pids=None):
    """only_pids = --retry-errors 경로(직전 errors.json 의 실패건만).
    errors.json 은 **실행 단위** 스냅샷이다(실행 내 누적·실행 간 덮어씀) — 실패는
    스냅샷에 캐시되지 않으므로 어차피 다음 ensure 가 다시 시도한다."""
    pids = list(only_pids) if only_pids is not None else list(_membership())
    errors, dead_streak = {}, 0
    for i in range(0, len(pids), chunk):
        part = pids[i:i + chunk]
        pending = _pending_pids(part)  # 캐시 적중만 있는 청크는 네트워크 신호가 없다
        recs, errs = snapshot.ensure(part, mcp=mcp, sleep=sleep,
                                     require=REQUIRE, log=None)
        errors.update(errs)
        if pending:
            dead_streak = dead_streak + 1 if len(errs) == len(pending) else 0
        dedup.save_json(os.path.join(_root(), "inventory", "errors.json"), errors)
        if log:
            log(f"  {min(i + chunk, len(pids))}/{len(pids)} (누적 오류 {len(errors)})")
        if dead_streak >= max_dead_chunks:
            raise ConsecutiveFailure(
                f"청크 {max_dead_chunks}개 연속 전멸 — 서버 상태 확인 후 재실행")
    if log:
        log(f"ensure 완료: {len(pids)}건 · 오류 {len(errors)}건")
    return errors


def run_build(done_counts, log=print):
    memb = _membership()
    recs = {}
    missing = []
    for pid in memb:
        rec = snapshot.load(pid)
        if rec is None:
            missing.append(pid)
        else:
            # 필요한 3필드만 남긴다 — 전 레코드(옵션 전체 포함)를 54K건 상주시키면
            # GB 단위가 된다
            recs[pid] = {"productId": pid,
                         "불사자코드": rec.get("불사자코드", ""),
                         "타오바오상품번호": rec.get("타오바오상품번호", "")}
    code_map = dedup.build_code_map(recs, memb)
    reps = {c: dedup.choose_representative(v, done_counts)
            for c, v in code_map.items()}
    stats = dedup.stats_of(code_map)
    stats["스냅샷없음"] = len(missing)
    base = os.path.join(_root(), "inventory")
    dedup.save_json(os.path.join(base, "codes.json"), code_map)
    dedup.save_json(os.path.join(base, "reps.json"), reps)
    dedup.save_json(os.path.join(base, "no_code.json"),
                    sorted(c[5:] for c in code_map if c.startswith("solo:")))
    dedup.save_json(os.path.join(base, "same_group_dups.json"),
                    dedup.same_group_dups(code_map))
    dedup.save_json(os.path.join(base, "stats.json"), stats)
    if log:
        log(json.dumps(stats, ensure_ascii=False, indent=2))
    return {"stats": stats, "missing": missing}


def _read_matrix_all(log=print):
    """52그룹 현황판을 전부 읽어 (그룹명→시트id, {pid: {작업: 값}}) 로 합친다."""
    from eroomlib import matrix
    sheets, merged = {}, {}
    for group, sid in matrix.index_groups():
        sheets[group] = sid
        try:
            m = matrix.read(sid)
        except Exception as e:  # noqa: BLE001 — 시트 하나 실패가 전체를 멈추면 안 됨
            if log:
                log(f"  (현황판 생략 {group}: {str(e)[:80]})")
            continue
        for pid, rec in m.items():
            merged.setdefault(pid, rec)
    return sheets, merged


def run_targets(task, read_matrix=None, log=print):
    """작업별 대상 산출 — 대표 pid × 현황판 상태. 지금은 '상품명'만 규칙이 있다.

    상품명 규칙: 카테고리 열=완료 AND 상품명 열이 빈칸/재작업.
    동일그룹중복 코드는 제외(전파·노출 정책을 사람이 정하기 전엔 건드리지 않는다).
    """
    from eroomlib import matrix
    if task not in matrix.TASKS:
        raise KeyError(f"알 수 없는 작업 '{task}' — matrix.TASKS 중 하나여야 합니다: {matrix.TASKS}")
    base = os.path.join(_root(), "inventory")
    reps = dedup.load_json(os.path.join(base, "reps.json"), {})
    codes = dedup.load_json(os.path.join(base, "codes.json"), {})
    dup_codes = set(dedup.load_json(os.path.join(base, "same_group_dups.json"), {}))
    sheets, m = (read_matrix() if read_matrix else _read_matrix_all(log))
    inst_by_pid = {i["productId"]: i for insts in codes.values() for i in insts}

    targets, excluded = [], []
    for code, pid in sorted(reps.items()):
        inst = inst_by_pid.get(pid) or {}
        rec = m.get(pid) or {}
        cat_done = (rec.get("카테고리") or "").strip() == matrix.DONE
        name_v = (rec.get(task) or "").strip()
        name_pending = (not name_v) or matrix.is_redo(name_v)
        if code in dup_codes:
            excluded.append({"productId": pid, "코드": code, "사유": "동일그룹중복"})
        elif not cat_done:
            excluded.append({"productId": pid, "코드": code, "사유": "카테고리미완료"})
        elif not name_pending:
            excluded.append({"productId": pid, "코드": code, "사유": f"{task}={name_v}"})
        else:
            targets.append({"productId": pid, "그룹명": inst.get("그룹명", ""),
                            "groupId": inst.get("groupId"), "코드": code})
    sheet_map = {t["productId"]: {"sheet": sheets.get(t["그룹명"], ""), "그룹명": t["그룹명"]}
                 for t in targets}
    # 시트를 못 찾은 대상은 targets 에서 뺀다(피어리뷰 지적) — 남겨두면 판단 비용을
    # 전부 쓴 뒤 append 단계에서야 sheet_map 부재로 전체가 막힌다. 여기서 잡아야 싸다.
    no_sheet = {pid for pid, e in sheet_map.items() if not e["sheet"]}
    if no_sheet:
        code_by_pid = {t["productId"]: t["코드"] for t in targets}
        for pid in sorted(no_sheet):
            excluded.append({"productId": pid, "코드": code_by_pid.get(pid, ""),
                             "사유": "시트없음(그룹명 불일치 의심)"})
        targets = [t for t in targets if t["productId"] not in no_sheet]
        sheet_map = {pid: e for pid, e in sheet_map.items() if pid not in no_sheet}
        if log:
            log(f"  [경고] 시트를 못 찾아 대상에서 제외 {len(no_sheet)}건: "
                f"{', '.join(sorted(no_sheet)[:5])}...")
    out = {"작업": task, "생성일": time.strftime("%Y-%m-%d %H:%M"), "targets": targets}
    dedup.save_json(os.path.join(base, f"targets_{task}.json"), out)
    dedup.save_json(os.path.join(base, "sheet_map.json"), sheet_map)
    dedup.save_json(os.path.join(base, "targets_excluded.json"), excluded)
    if log:
        log(f"targets({task}): 대상 {len(targets)} · 제외 {len(excluded)}")
    return out


def load_done_counts(log=print):
    """그룹 시트 00_진행에서 pid별 완료 작업 수 — 대표 선정 입력. 시트 없으면 0."""
    from eroomlib import matrix
    dc = {}
    for group, sid in matrix.index_groups():
        try:
            m = matrix.read(sid)
        except Exception as e:  # noqa: BLE001 — 시트 하나 실패가 전체를 멈추면 안 됨
            if log:
                log(f"  (현황판 생략 {group}: {str(e)[:80]})")
            continue
        for pid, rec in m.items():
            # `완료`(matrix.DONE)만 센다 — 보류·진행중을 세면 보류투성이 인스턴스가
            # 진짜 완료 인스턴스를 이겨 대표가 된다
            n = sum(1 for t in matrix.TASKS
                    if (rec.get(t) or "").strip() == matrix.DONE)
            dc[pid] = max(dc.get(pid, 0), n)
    return dc


def run_verify(mcp, sample, sleep=0.3, log=print):
    """find_by_code 표본 대조 — **코드 1개당 1콜**로 양방향 확인.

    수집누락 = 불사자는 아는데 우리 목록에 없음(found - ours) ← 스펙이 verify 에 준 목적.
    과잉귀속 = 우리는 그 코드로 아는데 응답에 없음(ours - found).
    배치(50개/콜)로 합치면 pid 가 엉뚱한 코드에 귀속돼도 통과해 버려서 코드별로 대조한다.
    """
    import re
    code_map = dedup.load_json(os.path.join(_root(), "inventory", "codes.json"), {})
    ours = {}
    for insts in code_map.values():
        for i in insts:
            if i["불사자코드"]:
                ours.setdefault(i["불사자코드"], set()).add(i["productId"])
    # 복사본 2개 이상인 코드 위주로 표본
    cand = sorted(c for c, pids in ours.items() if len(pids) >= 2)[:sample]
    issues = []
    for c in cand:
        raw = mcp.call_tool("bulsaja_product_find_by_code", {"codes": [c]})
        text = json.dumps(raw, ensure_ascii=False)
        found = set(re.findall(r"U[A-Z0-9]{20,}", text)) - {c}
        miss, extra = found - ours[c], ours[c] - found
        if miss or extra:
            issues.append({"code": c, "수집누락": sorted(miss),
                           "과잉귀속": sorted(extra)})
        time.sleep(sleep)
    dedup.save_json(os.path.join(_root(), "inventory", "verify.json"),
                    {"표본": len(cand), "불일치": issues})
    if log:
        log(f"verify: 표본 {len(cand)}개 · 불일치 {len(issues)}건")
    return issues


def run_report(log=print):
    from eroomlib.gsheets import append_rows, ensure_tab
    sid = cfg("sheets.master_index", required=True)
    s = dedup.load_json(os.path.join(_root(), "inventory", "stats.json"), {})
    ensure_tab(sid, "00_중복통계",
               ["날짜", "인스턴스수", "유니크수", "solo수", "최대복사본수",
                "동일그룹중복", "스냅샷없음"])
    append_rows(sid, "00_중복통계", [[
        time.strftime("%Y-%m-%d %H:%M"), s.get("인스턴스수"), s.get("유니크수"),
        s.get("solo수"), s.get("최대복사본수"), s.get("동일그룹중복_코드수"),
        s.get("스냅샷없음")]])
    if log:
        log("00_중복통계 1행 기록 완료")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Step 0 인벤토리")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("collect")
    p.add_argument("--filter")
    p.add_argument("--force", action="store_true")
    p.add_argument("--sleep", type=float, default=0.3)
    p.add_argument("--all", action="store_true", dest="all_groups",
                   help="마스터 인덱스 밖(테스트/레거시 포함) 계정 전체 그룹")
    p = sub.add_parser("ensure")
    p.add_argument("--chunk", type=int, default=500)
    p.add_argument("--sleep", type=float, default=0.3)
    p.add_argument("--retry-errors", action="store_true",
                   help="직전 errors.json 의 실패건만 다시")
    p = sub.add_parser("build")
    p.add_argument("--no-matrix", action="store_true",
                   help="현황판 완료수 없이 대표 선정(그룹명·pid 순)")
    p = sub.add_parser("verify")
    p.add_argument("--sample", type=int, default=100)
    sub.add_parser("report")
    p = sub.add_parser("targets")
    p.add_argument("--task", default="상품명")
    args = ap.parse_args()

    if args.cmd == "build":
        dc = {} if args.no_matrix else load_done_counts()
        run_build(dc)
        return
    if args.cmd == "report":
        run_report()
        return
    if args.cmd == "targets":
        run_targets(args.task)
        return
    from eroomlib.snapshot import ProductMCP
    mcp = ProductMCP()
    mcp.open()
    try:
        if args.cmd == "collect":
            run_collect(mcp, args.filter, args.force, args.sleep,
                       all_groups=args.all_groups)
        elif args.cmd == "ensure":
            only = None
            if args.retry_errors:
                only = list(dedup.load_json(
                    os.path.join(_root(), "inventory", "errors.json"), {}))
                if not only:
                    print("재시도 대상 없음 (errors.json 이 비어 있음)")
                    return
            run_ensure(mcp, args.chunk, args.sleep, only_pids=only)
        elif args.cmd == "verify":
            run_verify(mcp, args.sample)
    finally:
        mcp.close()


if __name__ == "__main__":
    main()
