#!/usr/bin/env python3
"""불사자 카테고리 저장 '유도' — 목표 셀하경로로 저장되게 keyword를 조정.

배경: bulsaja_product_category 는 keyword 자동매칭만 지원(카테고리 code 직접지정 불가).
동명 최종차수(leaf)를 그대로 넣으면 자동매칭이 엉뚱한 상위경로를 고른다
(예: '미용가위'→반려동물>미용가위, '기타튜닝용품'→PC부품, '피규어'→모형).
자동매칭 = keyword 검색 스마트스토어 후보의 1순위. 따라서 leaf 앞에 상위 분야 한정어를
붙인 keyword(예 '헤어 미용가위', '자동차 기타튜닝용품')로 검색하면 원하는 경로가 1순위가 되어
자동선택된다. preview(confirm=False) 경로가 목표 셀하경로와 **정확일치**할 때만 commit → 안전.

이 스크립트가 '저장 4단계 폴백'의 1단계(유도)와 3단계(근접)를 담당한다.
  exact 모드: gen_candidates(목표경로) 를 순서대로 preview → 정확일치 시 commit
  near  모드: 주어진 keyword 로 preview → (정확일치 무시) commit, I열에 '근접저장' 플래그

**현황판(00_진행) 후처리도 여기서 한다** (2026-08-09 이 자리로 내림).
전에는 `run_all.py _post_steer_matrix` 가 했는데, 그건 `cmd_steer`·`cmd_consensus` 에서만
불린다. **3단계 근접 저장은 Claude 가 입력 JSON 을 손으로 만들어 이 스크립트를 직접
호출**하므로(`steer_items` 는 mode:"exact" 만 만든다) 그 경로가 후처리를 통째로 건너뛰었다
— 현황판 카테고리 열이 안 써지던 기존 버그이자, 제외카테고리 게이트의 구멍이었다.
저장하는 자리에 후처리를 붙이면 어느 호출자로 들어와도 같은 일이 일어난다.

입력 JSON: [{"productId","row","target","keyword"(선택),"mode"(선택)}]
  target  = 목표 셀하경로(필수, exact 비교 기준)
  keyword = candidate 시드(재검색어). near 모드에선 이 keyword(들)로 바로 저장
  mode    = "exact"(기본) | "near"

사용:
  python category_steer.py --input steer.json --sheet <id> [--dry-run]
"""
import argparse
import json
import os
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from bulsaja_mcp import BulsajaMCP, _norm_path  # noqa
from eroomlib import snapshot  # noqa  (bulsaja_mcp 가 .claude/lib 를 sys.path 에 올린 뒤)
import sheet_log  # noqa

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SUFFIX = ["용품", "소품", "가전", "가구", "기기"]


def core_variants(seg):
    seg = seg.strip()
    vs = []
    if "/" in seg:
        vs.append(seg.split("/")[0])
    vs.append(seg)
    for suf in SUFFIX:
        if seg.endswith(suf) and len(seg) > len(suf) + 1:
            vs.append(seg[:-len(suf)])
    out = []
    for v in vs:
        if v and v not in out:
            out.append(v)
    return out


def gen_candidates(path, keyword=""):
    """목표경로 A>B>C>D 에서 유도 keyword 후보를 생성.
    우선순위: 가까운 상위(C,B,A) 핵심어 + leaf, 검색어 첫단어 + leaf, leaf 단독.
    leaf 에 '/'가 있으면 각 조각도 leaf 후보로.
    """
    segs = [s.strip() for s in path.split(">")]
    leaf = segs[-1]
    leaf_vars = [leaf]
    if "/" in leaf:
        for part in leaf.split("/"):
            if part and part not in leaf_vars:
                leaf_vars.append(part)
    cands = []
    for seg in reversed(segs[:-1]):
        for cv in core_variants(seg):
            for lv in leaf_vars:
                if cv and cv not in lv:
                    cands.append(f"{cv} {lv}")
    kw0 = (keyword.split() or [""])[0] if keyword else ""
    for lv in leaf_vars:
        if kw0 and kw0 not in lv:
            cands.append(f"{kw0} {lv}")
    cands += leaf_vars
    out = []
    for c in cands:
        c = c.strip()
        if c and len(c) <= 58 and c not in out:
            out.append(c)
    return out


def post_matrix(sheet, results, meta, run_dir=None, no_gate=False, log=print):
    """저장분 현황판 후처리 — ① 카테고리 완료 ② 제외카테고리 게이트 ③ 상품명 재작업 이관.

    `bulsaja_mcp.py apply` 가 자동저장분에 하는 일과 **같은 계약**이다. 순서가 뜻이 있다:
    게이트가 재작업 플래그 **앞**에 선다(원안 2026-08-08). 제외 대상이면 재작업이 아니라
    삭제이고, 재작업을 찍으면 `matrix.pending` 이 다시 집어가 막으려던 상품명 비용이
    그대로 나간다.

    results = 이 스크립트의 out 레코드, meta = {productId: 입력항목}(상품명 등).
    반환: 저장된 pid set.
    """
    saved = [r for r in results if r.get("saved")]
    if not saved:
        log("  저장 0건 — 현황판 변경 없음")
        return set()
    from eroomlib import matrix
    m = matrix.read(sheet)
    n = matrix.mark_many(sheet, "카테고리",
                         {r["productId"]: matrix.DONE for r in saved}, matrix=m)
    for r in saved:                       # 캐시 동기화(아래 게이트·이관이 같은 m 을 쓴다)
        if r["productId"] in m:
            m[r["productId"]]["카테고리"] = matrix.DONE

    gated = set()
    if not no_gate:
        try:
            import category_gate  # noqa: E402  (같은 스킬 폴더 — SCRIPT_DIR 이 sys.path 에 있다)
            recs = [{"productId": r["productId"],
                     "상품명": (meta.get(r["productId"]) or {}).get("상품명", ""),
                     "카테고리": r.get("ss", ""),
                     "근접저장": r.get("mode") == "near"} for r in saved]
            targets, _s = category_gate.gate_records(sheet, recs, run_dir=run_dir, m=m)
            gated = {t["productId"] for t in targets}
        except Exception as e:  # noqa: BLE001 — 저장은 이미 끝났다. 죽이면 잃는 게 더 크다.
            log(f"  [경고] 제외카테고리 게이트 실패: {type(e).__name__}: {str(e)[:140]}")
            log("    저장은 정상이다. 놓친 건은 `category_gate.py scan` 이 훑는다.")

    redo = {r["productId"]: "카테고리 변경 — 키워드 재선정 필요"
            for r in saved if r["productId"] not in gated}
    k = matrix.flag_many(sheet, "상품명", redo, from_task="카테고리", matrix=m) if redo else 0
    log(f"  현황판 카테고리 {n}칸 · 상품명 재작업 {k}건"
        + (f" · 제외카테고리 게이트 {len(gated)}건" if gated else ""))
    return {r["productId"] for r in saved}


def main():
    ap = argparse.ArgumentParser(description="불사자 카테고리 유도 저장")
    ap.add_argument("--input", "-i", required=True, help="steer.json [{productId,row,target,keyword?,mode?}]")
    ap.add_argument("--output", "-o", help="결과 JSON 저장 경로")
    ap.add_argument("--sheet", help="구글시트 spreadsheetId(건건 기록)")
    ap.add_argument("--dry-run", action="store_true", help="preview만, 저장 안 함")
    ap.add_argument("--sleep", type=float, default=0.3)
    ap.add_argument("--no-gate", action="store_true",
                    help="제외카테고리 게이트를 끈다(검증·재현용). 기본은 켬")
    ap.add_argument("--run-dir", default=None,
                    help="게이트 삭제 큐 자리(기본: --output 의 폴더)")
    args = ap.parse_args()

    items = json.load(open(args.input, encoding="utf-8"))
    logger = sheet_log.SheetLogger(args.sheet) if args.sheet else None
    mcp = BulsajaMCP()
    mcp.open()
    out = []
    saved = 0
    for it in items:
        pid = it["productId"]
        row = it.get("row")
        target = _norm_path(it.get("target", ""))
        mode = it.get("mode", "exact")
        seed = it.get("keyword", "")
        hit = None
        if mode == "near":
            kws = seed if isinstance(seed, list) else [seed]
            for kw in kws:
                try:
                    pv = mcp.category_preview(pid, kw)
                except Exception:
                    continue
                if pv["token"] and pv["ss_name"]:
                    hit = {"kw": kw, "ss": pv["ss_name"], "token": pv["token"], "near": True}
                    break
                time.sleep(0.2)
        else:  # exact
            for kw in gen_candidates(it.get("target", ""), seed if isinstance(seed, str) else ""):
                try:
                    pv = mcp.category_preview(pid, kw)
                except Exception:
                    continue
                if _norm_path(pv["ss_name"]) == target and pv["token"]:
                    hit = {"kw": kw, "ss": pv["ss_name"], "token": pv["token"], "near": False}
                    break
                time.sleep(0.2)
        rec = {"row": row, "productId": pid, "target": it.get("target", ""),
               "hit": hit["kw"] if hit else None, "ss": hit["ss"] if hit else "", "mode": mode}
        if hit and not args.dry_run:
            cm = mcp.category_commit(pid, hit["kw"], hit["token"])
            rec["saved"] = cm["success"]
            if cm["success"]:
                saved += 1
                # ★ 저장한 쪽이 스냅샷의 그 필드만 되쓴다 (2026-07-31 추가).
                # 이게 없으면 로컬 캐시에 옛 카테고리가 남아, 다음 단계(상품명)가
                # **방금 고친 이유였던 그 옛 카테고리로 뷰를 만든다.**
                # 2026-07-30 에 이 경로로 상품명 76건이 통째로 무효가 됐다.
                try:
                    snapshot.update(pid, 기존카테고리=hit["ss"])
                except Exception as e:  # noqa: BLE001
                    rec["snapshot_err"] = str(e)[:100]
            if logger and row:
                d = {"상품명": it.get("상품명", ""), "기존카테고리": it.get("기존카테고리", ""),
                     "변경카테고리": hit["ss"], "검색어": hit["kw"], "확신도": it.get("확신도", ""),
                     "상태": "저장완료" if cm["success"] else "저장실패",
                     # I열은 '어떤 경로로 맞췄나'를 사후에 되짚는 유일한 단서다.
                     # 입력이 지정하면 그걸 쓴다(예 consensus(2/3)·수동지정(이룸님)).
                     "위험": it.get("위험") or ("근접저장(셀하≠불사자)" if hit["near"] else "")}
                try:
                    logger.update_row(row, d)
                except Exception as e:
                    rec["sheet_err"] = str(e)[:100]
        mark = f"OK({hit['kw']}{'·근접' if hit and hit['near'] else ''})" if hit else "미발견"
        print(f"row{row} [{mark}] {it.get('target','')}" + (f" → {hit['ss']}" if hit else ""), flush=True)
        out.append(rec)
        time.sleep(args.sleep)
    mcp.close()
    if args.output:
        json.dump(out, open(args.output, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # 현황판 후처리 — 어느 호출자로 들어와도(run_all steer/consensus, Claude 의 근접 저장
    # 직접 호출) 같은 일이 일어나야 한다. 파생본이라 실패해도 저장 결과엔 영향이 없다.
    if args.sheet and not args.dry_run:
        run_dir = args.run_dir or (os.path.dirname(os.path.abspath(args.output))
                                   if args.output else None)
        try:
            post_matrix(args.sheet, out, {it["productId"]: it for it in items},
                        run_dir=run_dir, no_gate=args.no_gate)
        except Exception as e:  # noqa: BLE001
            print(f"  [경고] 현황판 갱신 실패: {str(e)[:140]}", file=sys.stderr)

    found = sum(1 for r in out if r["hit"])
    print(f"###STEER### 일치 {found}/{len(items)}  저장 {saved}  (dry_run={args.dry_run})")


if __name__ == "__main__":
    main()
