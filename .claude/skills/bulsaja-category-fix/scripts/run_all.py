#!/usr/bin/env python3
"""불사자 카테고리 교정 대량 파이프라인 오케스트레이터.

파이프라인 중간에 Claude(정체판별+키워드 추출)가 끼므로 완전 원샷이 불가 → 2단계로 나눈다.

  [prep]   collect(G빈행) → workdata(카테고리+정체증거 4종) → 썸네일 전건 다운로드
           → products.json + names.json(정체판별용) 출력
      ↓  (Claude/서브에이전트가 증거 4종 → keywords.json:
      ↓   [{productId, name=대표검색어, 실물판정, 근거}] / 불명이면 상태='보류(정체불명)')
  [finish] sellha(보류 제외) → merge(products+keywords+sellha) → apply(실저장+시트기록)

재개: 시트 G열이 체크포인트. prep 는 항상 'G 빈 행'만 가져오므로, finish 로 저장돼
      G가 채워지면 다음 prep 는 자동으로 그다음 청크를 집는다. --limit 로 청크 크기 조절.

사용:
  # 1) 준비(다음 청크 50건)
  python run_all.py prep --limit 50 --run-dir runs/0713_c1
  # 2) (여기서 names.json → keywords.json 을 Claude 가 만든다)
  # 3) 마무리(실저장)
  python run_all.py finish --run-dir runs/0713_c1 --keywords runs/0713_c1/keywords.json
  #    미리보기만: --dry-run
"""
import argparse
import json
import os
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

# 경로·시트 id 는 workspace.toml 1벌에서 온다(없으면 DEFAULTS = 현행 값).
# `.claude` 앵커를 찾아 lib 를 sys.path 에 올린 뒤 eroomlib 를 든다.
_d = SCRIPT_DIR
while _d and _d != os.path.dirname(_d):
    _lib = os.path.join(_d, "lib")
    if os.path.isdir(os.path.join(_lib, "eroomlib")):
        if _lib not in sys.path:
            sys.path.insert(0, _lib)
        break
    _d = os.path.dirname(_d)
from eroomlib.config import cfg as _cfg  # noqa: E402

SHEET = _cfg("sheets.keyword_default")
TAB = "시트1"


# 셀하 조회는 sellha-category 스킬로 분리됨(Step4). 절대경로로 호출한다.
SELLHA_SCRIPT = os.path.normpath(os.path.join(
    SCRIPT_DIR, "..", "..", "sellha-category", "scripts", "sellha.py"))


def sh(script, *args):
    # script 가 절대경로(다른 스킬)면 그대로, 아니면 이 스킬 SCRIPT_DIR 에서 찾는다.
    path = script if os.path.isabs(script) else os.path.join(SCRIPT_DIR, script)
    label = os.path.basename(script)
    cmd = [PY, path, *[str(a) for a in args]]
    print(f"\n$ {label} {' '.join(str(a) for a in args)}\n{'-'*56}")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run(cmd, env=env)
    if proc.returncode != 0:
        raise RuntimeError(f"{label} 실패 (exit {proc.returncode})")


def _p(run_dir, name):
    return os.path.join(run_dir, name)


def _fetch_thumbs(run_dir, prods, refresh=False):
    """전건 대표 썸네일 다운로드 → {productId: 로컬경로}.

    fetch_thumbs.py 는 입력 순서대로 한 줄씩(성공=절대경로 / 실패='FAIL\\t..') 출력한다.
    """
    thumbs_json = _p(run_dir, "thumbs.json")
    thumbs_dir = _p(run_dir, "thumbs")
    items = [{"productId": p["productId"], "url": (p.get("썸네일") or [""])[0]}
             for p in prods if (p.get("썸네일") or [""])[0]]
    if not items:
        print("[3/4] 썸네일 URL 없음 — 건너뜀")
        return {}
    with open(thumbs_json, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    os.makedirs(thumbs_dir, exist_ok=True)
    print(f"[3/4] 썸네일 {len(items)}장 다운로드 중...")
    cmd = [PY, os.path.join(SCRIPT_DIR, "fetch_thumbs.py"),
           "--input", thumbs_json, "--out-dir", thumbs_dir] + (["--refresh"] if refresh else [])
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    out = {}
    for i, ln in enumerate([l for l in (proc.stdout or "").splitlines() if l.strip()]):
        if i < len(items) and not ln.startswith("FAIL"):
            out[items[i]["productId"]] = os.path.abspath(ln.strip())
    print(f"  로컬 확보: {len(out)}/{len(items)}장")
    return out


def cmd_prep(args):
    os.makedirs(args.run_dir, exist_ok=True)
    targets = _p(args.run_dir, "targets.json")
    products = _p(args.run_dir, "products.json")
    names = _p(args.run_dir, "names.json")

    # 1) 대상수집 (G 빈 행만, --limit 청크)
    collect_args = ["--sheet", args.sheet, "--tab", args.tab, "-o", targets]
    if args.limit and not args.ids:
        collect_args += ["--limit", args.limit]
    if args.ids and args.include_done:
        collect_args += ["--all"]  # 상태가 이미 찬 행도 대상에 넣는다(재작업)
    sh("collect_targets.py", *collect_args)

    # 1b) --ids: 특정 상품만 남긴다. 세로 러너(onestep)가 상품 1건을 지정하는 경로이자,
    #     보류 건 애드혹 재작업용. 수집 뒤에 거르는 이유 = 시트 행번호·원장 상태를
    #     collect_targets 가 붙여 주므로 그 산출물을 그대로 쓰는 게 안전하다.
    if args.ids:
        want = [i.strip() for i in args.ids if i.strip()]

        def _filter():
            with open(targets, encoding="utf-8") as f:
                allt = json.load(f)
            kept = [t for t in allt if t.get("productId") in want]
            miss = [i for i in want
                    if not any(t.get("productId") == i for t in kept)]
            return kept, miss

        kept, missing = _filter()

        # 시트1에 **행이 없는** 상품은 대상이 될 수 없다(collect_targets 가 시트를 읽으므로).
        # 현황판에는 있는데 여기엔 없는 상품이 그룹당 수백 건이다(용쌤1-1: 833/833).
        # → 현황판의 상품명으로 A·B열만 채워 행을 만들고 다시 수집한다. 그래야 대상 선정이
        #   "현황판 쿼리 1줄"이라는 계약과 실제가 맞는다.
        if missing and not args.no_seed:
            from eroomlib import matrix
            from eroomlib.gsheets import append_rows
            m = matrix.read(args.sheet)
            seed = [[pid, (m.get(pid) or {}).get("상품", "")]
                    for pid in missing if pid in m]
            if seed:
                append_rows(args.sheet, args.tab, seed)
                print(f"[1b] 시트1에 행 신설 {len(seed)}건 (현황판에는 있으나 원장에 없던 상품)")
                sh("collect_targets.py", *collect_args)
                kept, missing = _filter()

        with open(targets, "w", encoding="utf-8") as f:
            json.dump(kept, f, ensure_ascii=False, indent=2)
        print(f"[1b] --ids {len(want)}건 지정 → {len(kept)}건 매칭")
        if missing:
            print(f"  [경고] 대상에 못 넣음 {len(missing)}건: {missing[:5]}")
            print("   상태열이 이미 차 있거나(--include-done) 현황판에 없는 상품이다.")
        if not kept:
            print("[중단] 대상 0건.")
            sys.exit(2)   # 조용한 성공 금지 — 러너가 다음 단계로 넘어가면 안 된다

    # 2) workdata (현재 카테고리 + 정체증거 4종) — 대화 밖 직접 MCP.
    #    공용 스냅샷을 먼저 본다(상품명 스킬이 이미 받아둔 상품이면 MCP 0회).
    wd_args = ["workdata", "-i", targets, "-o", products, "--sleep", args.sleep]
    if args.refresh:
        wd_args.append("--refresh")
    sh("bulsaja_mcp.py", *wd_args)

    with open(products, encoding="utf-8") as f:
        prods = json.load(f)

    # 3) 썸네일 전건 다운로드 (2026-07-24: 폴백이 아니라 기본 경로)
    thumb_map = ({} if args.skip_thumbs
                 else _fetch_thumbs(args.run_dir, prods, refresh=args.refresh))

    # 4) 정체판별용 names.json — 증거 4종을 한 장에 모아 넘긴다.
    #    한국어 상품명은 '정답'이 아니라 '용의자'다. 원문명·옵션명은 가공 전 원본이라
    #    상품명·썸네일이 함께 틀어졌을 때 이것만이 실물을 가리킨다.
    names_list = [{
        "productId": p["productId"],
        "row": p.get("row"),
        "상품명": p.get("상품명", ""),
        "원문명": p.get("원문명", ""),
        "옵션명": p.get("옵션명", []),
        "썸네일경로": thumb_map.get(p["productId"], ""),
    } for p in prods]
    with open(names, "w", encoding="utf-8") as f:
        json.dump(names_list, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 56)
    print(f"[prep 완료] {len(names_list)}건 → {products}")
    print(f"다음: {names} 의 증거 4종(상품명·원문명·옵션명·썸네일)으로 keywords.json 생성")
    print("  [{productId, name=대표검색어, 실물판정, 근거}] "
          "/ 정체 불명이면 {productId, 상태:'보류(정체불명)', 실물판정, 근거}")
    print(f"그 후: python run_all.py finish --run-dir {args.run_dir} "
          f"--keywords {os.path.join(args.run_dir, 'keywords.json')}")


def cmd_finish(args):
    products = _p(args.run_dir, "products.json")
    sellha = _p(args.run_dir, "sellha.json")
    merged = _p(args.run_dir, "merged.json")
    decisions = _p(args.run_dir, "decisions.json")
    keywords = args.keywords or _p(args.run_dir, "keywords.json")

    # 4) 셀하 조회 (배치, 증분저장+재개). --force 면 처음부터 재조회
    #    '보류(정체불명)' 건은 정체가 안 잡힌 것이라 셀하를 아예 태우지 않는다
    #    (셀하 ~15초/건이 유일한 직렬 병목 — 어차피 2바퀴에서 재조회하므로 1회만 태운다).
    with open(keywords, encoding="utf-8") as f:
        kw_list = json.load(f)
    kw_map = {k.get("productId"): k for k in kw_list}
    held = {pid for pid, k in kw_map.items()
            if str(k.get("상태", "")).startswith("보류") or not k.get("name")}
    if held:
        askable = _p(args.run_dir, "keywords_askable.json")
        with open(askable, "w", encoding="utf-8") as f:
            json.dump([k for k in kw_list if k.get("productId") not in held],
                      f, ensure_ascii=False, indent=2)
        keywords_for_sellha = askable
        print(f"[보류] 정체불명 {len(held)}건은 셀하 조회 제외 → 2바퀴 큐")
    else:
        keywords_for_sellha = keywords

    if args.force and os.path.exists(sellha):
        os.remove(sellha)
    sh(SELLHA_SCRIPT, "--input", keywords_for_sellha, "--output", sellha,
       "--headless", "--resume")

    # 5) 병합 (products + keywords + sellha, productId 기준)
    with open(products, encoding="utf-8") as f:
        prods = {p["productId"]: p for p in json.load(f)}
    with open(sellha, encoding="utf-8") as f:
        sl = {r.get("productId"): r for r in json.load(f)}
    merged_list = []
    for pid, w in prods.items():
        s = sl.get(pid, {})
        k = kw_map.get(pid, {})
        thumbs = w.get("썸네일") or []
        merged_list.append({
            "productId": pid, "상품명": w.get("상품명", ""), "row": w.get("row"),
            "기존카테고리": w.get("기존카테고리", ""), "검색어": s.get("검색어", ""),
            "sellha경로": s.get("카테고리경로", ""), "최종차수": s.get("최종차수", ""),
            "확신도": s.get("확신도", ""),
            "sellha상태": "보류(정체불명)" if pid in held else s.get("상태", ""),
            # 시트 J·K (상품명 스킬이 재활용)
            "실물판정": k.get("실물판정", ""),
            "썸네일": thumbs[0] if thumbs else "",
        })
    with open(merged, "w", encoding="utf-8") as f:
        json.dump(merged_list, f, ensure_ascii=False, indent=2)
    print(f"\n병합 {len(merged_list)}건 → {merged}")

    # 6) 적용 (미리보기→비교→커밋 + 시트 건건 기록)
    apply_args = ["apply", "-i", merged, "-o", decisions,
                  "--threshold", args.threshold, "--sleep", args.sleep]
    if args.dry_run:
        apply_args.append("--dry-run")
    if args.no_sheet:
        apply_args.append("--no-sheet")
    else:
        apply_args += ["--sheet", args.sheet]
    sh("bulsaja_mcp.py", *apply_args)
    print("\n" + "=" * 56)
    print(f"[finish 완료] 결과 {decisions}"
          + ("  (DRY-RUN)" if args.dry_run else ""))


def cmd_recheck(args):
    """2바퀴 — 1바퀴에서 '보류(정체불명)'로 남은 건만 증거를 보강해 다시 판정한다.

    싼 것부터 올라가는 사다리: 남은 썸네일(2·3장, 이미 받아둔 URL이라 공짜) →
    옵션 이미지(실물 변형이라 정체가 드러남) → 그래도 불명이면 이룸님 보고.
    """
    products = _p(args.run_dir, "products.json")
    keywords = args.keywords or _p(args.run_dir, "keywords.json")
    out_dir = _p(args.run_dir, "recheck")
    os.makedirs(out_dir, exist_ok=True)

    with open(products, encoding="utf-8") as f:
        prods = {p["productId"]: p for p in json.load(f)}
    held = set(args.ids or [])
    if not held and os.path.exists(keywords):
        with open(keywords, encoding="utf-8") as f:
            held = {k["productId"] for k in json.load(f)
                    if str(k.get("상태", "")).startswith("보류") or not k.get("name")}
    if not held:
        print("[recheck] 대상 없음 (보류 건이 없거나 --ids 미지정)")
        return

    # 이미지 목록: 남은 썸네일(2·3장) + 옵션 이미지
    items, owner = [], []
    for pid in held:
        w = prods.get(pid, {})
        urls = (w.get("썸네일") or [])[1:3] + (w.get("옵션이미지") or [])[:3]
        for u in urls:
            items.append({"productId": pid, "url": u})
            owner.append(pid)
    manifest_in = _p(args.run_dir, "recheck_urls.json")
    with open(manifest_in, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    paths = {pid: [] for pid in held}
    if items:
        print(f"[recheck] {len(held)}건 / 이미지 {len(items)}장 다운로드 중...")
        cmd = [PY, os.path.join(SCRIPT_DIR, "fetch_thumbs.py"),
               "--input", manifest_in, "--out-dir", out_dir]
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        for i, ln in enumerate([l for l in (proc.stdout or "").splitlines() if l.strip()]):
            if i < len(owner) and not ln.startswith("FAIL"):
                paths[owner[i]].append(os.path.abspath(ln.strip()))

    pack = [{
        "productId": pid,
        "row": prods.get(pid, {}).get("row"),
        "상품명": prods.get(pid, {}).get("상품명", ""),
        "원문명": prods.get(pid, {}).get("원문명", ""),
        "옵션명": prods.get(pid, {}).get("옵션명", []),
        "옵션명원문": prods.get(pid, {}).get("옵션명원문", []),
        "추가이미지": paths.get(pid, []),
        "원본링크": prods.get(pid, {}).get("원본링크", ""),
    } for pid in held]
    out = _p(args.run_dir, "recheck.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(pack, f, ensure_ascii=False, indent=2)
    print("\n" + "=" * 56)
    print(f"[recheck 준비 완료] {len(pack)}건 → {out}")
    print("다음: 추가이미지를 Read 로 열어 실물 판정 → keywords.json 갱신 → finish 재실행")


def main():
    ap = argparse.ArgumentParser(description="불사자 카테고리 교정 대량 파이프라인")
    ap.add_argument("--sheet", default=SHEET)
    ap.add_argument("--tab", default=TAB)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prep", help="collect+workdata → products.json/names.json")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--limit", type=int, default=0, help="청크 크기(0=전체 남은 것)")
    p.add_argument("--ids", nargs="+", default=None,
                   help="특정 productId 만 대상으로(세로 러너·애드혹 1건 작업). --limit 무시")
    p.add_argument("--include-done", action="store_true",
                   help="--ids 와 함께. 상태열이 이미 찬 행도 대상에 넣는다(재작업)")
    p.add_argument("--no-seed", action="store_true",
                   help="--ids 와 함께. 시트1에 행이 없어도 새로 만들지 않는다")
    p.add_argument("--sleep", default="0.3")
    p.add_argument("--skip-thumbs", action="store_true",
                   help="썸네일 다운로드 생략(텍스트 증거만으로 판정할 때)")
    p.add_argument("--refresh", action="store_true",
                   help="공용 스냅샷 무시하고 불사자에서 다시 받는다")
    p.set_defaults(func=cmd_prep)

    f = sub.add_parser("finish", help="sellha→merge→apply(실저장)")
    f.add_argument("--run-dir", required=True)
    f.add_argument("--keywords", help="keywords.json 경로(기본 run-dir/keywords.json)")
    f.add_argument("--threshold", default="70")  # 2026-07-24 이룸님 90→70 하향
    f.add_argument("--sleep", default="0.4")
    f.add_argument("--dry-run", action="store_true", help="미리보기만")
    f.add_argument("--no-sheet", action="store_true")
    f.add_argument("--force", action="store_true", help="셀하 재조회")
    f.set_defaults(func=cmd_finish)

    r = sub.add_parser("recheck", help="2바퀴: 보류(정체불명) 건 증거 보강")
    r.add_argument("--run-dir", required=True)
    r.add_argument("--keywords", help="keywords.json 경로(기본 run-dir/keywords.json)")
    r.add_argument("--ids", nargs="+", help="대상 productId 직접 지정(기본=보류 전건)")
    r.set_defaults(func=cmd_recheck)

    # prep/finish 는 상위 --sheet/--tab 을 물려받도록 보정
    args = ap.parse_args()
    if not hasattr(args, "sheet"):
        args.sheet = SHEET
    args.func(args)


if __name__ == "__main__":
    main()
