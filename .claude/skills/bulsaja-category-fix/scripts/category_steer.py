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


def main():
    ap = argparse.ArgumentParser(description="불사자 카테고리 유도 저장")
    ap.add_argument("--input", "-i", required=True, help="steer.json [{productId,row,target,keyword?,mode?}]")
    ap.add_argument("--output", "-o", help="결과 JSON 저장 경로")
    ap.add_argument("--sheet", help="구글시트 spreadsheetId(건건 기록)")
    ap.add_argument("--dry-run", action="store_true", help="preview만, 저장 안 함")
    ap.add_argument("--sleep", type=float, default=0.3)
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
    found = sum(1 for r in out if r["hit"])
    print(f"###STEER### 일치 {found}/{len(items)}  저장 {saved}  (dry_run={args.dry_run})")


if __name__ == "__main__":
    main()
