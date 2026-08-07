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


# 카테고리 조회 엔진은 별도 스킬로 분리돼 있다(Step4). 절대경로로 호출한다.
#
# 2026-08-04: 셀하 → Aside 전환. 셀하가 막혀 못 쓴다.
# Aside 는 이룸님 브라우저 세션에 붙으므로 크롬 프로필·셀레늄·자격증명이 필요 없다.
# 반환 스키마(카테고리경로·최종차수·확신도·상태)가 같아 아래 병합부는 그대로다.
# 조회 전제: Aside 앱이 떠 있고 · 불사자 확장이 깔려 있고 · 네이버 로그인이 살아 있을 것.
CAT_SCRIPT = os.path.normpath(os.path.join(
    SCRIPT_DIR, "..", "..", "aside-category", "scripts", "aside_category.py"))

# 파일명(sellha.json)·시트열(sellha경로)·플래그(--skip-sellha)는 이름을 유지한다.
# 기존 run-dir 의 --resume 과 시트 재개 로직이 그 이름에 물려 있어 바꾸면 깨진다.


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

    # 4) 카테고리 조회 (배치, 증분저장+재개). --force 면 처음부터 재조회
    #    '보류(정체불명)' 건은 정체가 안 잡힌 것이라 조회를 아예 태우지 않는다
    #    (조회 ~10초/건이 유일한 직렬 병목 — 어차피 2바퀴에서 재조회하므로 1회만 태운다).
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
        print(f"[보류] 정체불명 {len(held)}건은 카테고리 조회 제외 → 2바퀴 큐")
    else:
        keywords_for_sellha = keywords

    if args.force and os.path.exists(sellha):
        os.remove(sellha)
    # ★ 조회 전제(하나라도 빠지면 전건 파싱실패): Aside 앱 실행중 · 불사자 확장 설치 ·
    # 네이버 로그인 유지. 준비 → aside-category/SKILL.md §준비
    if getattr(args, "skip_sellha", False):
        # 조회를 못 하는 환경에서 **이미 조회된 것만** 저장한다.
        # 미조회 건은 아래 병합에서 제외한다 — merged 에 남기면 apply 가 빈 검색어를
        # 'sellha조회실패'로 시트 G열에 찍고, 그러면 재개 로직이 그 행을 영영 건너뛴다.
        print("[skip-sellha] 카테고리 조회 생략 — sellha.json 에 이미 있는 건만 저장한다")
    else:
        # --sleep/--sleep-max 는 이전엔 파싱만 하고 안 넘겨 죽은 옵션이었다. 이제 실제로 넘긴다.
        sh(CAT_SCRIPT, "--input", keywords_for_sellha, "--output", sellha, "--resume",
           "--sleep", args.sellha_sleep, "--sleep-max", args.sellha_sleep_max)

    # 5) 병합 (products + keywords + sellha, productId 기준)
    with open(products, encoding="utf-8") as f:
        prods = {p["productId"]: p for p in json.load(f)}
    with open(sellha, encoding="utf-8") as f:
        sl = {r.get("productId"): r for r in json.load(f)}
    merged_list = []
    skipped_unqueried = 0
    for pid, w in prods.items():
        s = sl.get(pid, {})
        k = kw_map.get(pid, {})
        if getattr(args, "skip_sellha", False) and not s and pid not in held:
            skipped_unqueried += 1
            continue
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
    if skipped_unqueried:
        print(f"[skip-sellha] 미조회 {skipped_unqueried}건은 병합 제외 "
              f"(시트 G열을 비워 둬야 다음 실행이 이어받는다)")

    # 6) 적용 (미리보기→비교→커밋 + 시트 건건 기록)
    apply_args = ["apply", "-i", merged, "-o", decisions,
                  "--threshold", args.threshold, "--sleep", args.sleep]
    if args.dry_run:
        apply_args.append("--dry-run")
    if args.no_sheet:
        apply_args.append("--no-sheet")
    else:
        apply_args += ["--sheet", args.sheet]
    # 기본은 시트에 이미 `저장완료`인 행을 건드리지 않는다(후처리 결과 보호).
    # 전건 재조회·덮어쓰기가 필요할 때만 --overwrite-done.
    if getattr(args, "overwrite_done", False):
        apply_args.append("--force")
    sh("bulsaja_mcp.py", *apply_args)
    print("\n" + "=" * 56)
    print(f"[finish 완료] 결과 {decisions}"
          + ("  (DRY-RUN)" if args.dry_run else ""))


# ── 팬아웃 3종(batch / merge / steer)의 계산부 ───────────────────────────────
# 순수 함수로 떼어 둔다 — MCP·시트·조회 없이 test_run_all.py 가 검증한다.

def make_batches(names_list, size, rules):
    """names.json → 자기완결형 배치. 워커는 배치 파일 경로 하나로 완주할 수 있어야 한다."""
    size = max(1, int(size or 1))
    out = []
    for i in range(0, len(names_list), size):
        chunk = names_list[i:i + size]
        out.append({
            "batch": len(out) + 1,
            "규칙문서": rules,
            "이미지수": sum(1 for p in chunk if p.get("썸네일경로")),
            "products": chunk,
        })
    return out


def merge_named(named_docs, expected):
    """워커 산출물(named_*.json) → keywords.json + 감사 리포트.

    디스크가 정본이므로 같은 상품이 두 번 와도(재팬아웃) 마지막이 이긴다.
    모르는 상품id 는 버린다 — 워커 환각이 원장에 들어가면 되돌릴 경로가 없다.
    name 도 상태도 없는 결과는 **보류로 강등**한다. 그대로 두면 조회를 태워
    빈 검색어로 조회하고 '조회실패'가 되어 원인이 지워진다.
    """
    want = list(dict.fromkeys(expected))
    allow = set(want)
    by_pid, order, dups, unknown = {}, [], 0, []
    for doc in named_docs:
        for r in (doc.get("results") or []):
            pid = r.get("productId")
            if not pid:
                continue
            if pid not in allow:
                unknown.append(pid)
                continue
            if pid in by_pid:
                dups += 1
            else:
                order.append(pid)
            rec = dict(r)
            if not rec.get("name") and not str(rec.get("상태", "")).startswith("보류"):
                rec["상태"] = "보류(정체불명)"
                rec.setdefault("근거", "")
                rec["근거"] = (rec["근거"] + " [자동강등: 검색어 없음]").strip()
            by_pid[pid] = rec
    kw = [by_pid[p] for p in order]
    held = [p for p in order if str(by_pid[p].get("상태", "")).startswith("보류")]
    return kw, {
        "missing": [p for p in want if p not in by_pid],
        "unknown": unknown,
        "dups": dups,
        "held": held,
        "named": len(kw) - len(held),
    }


def steer_items(decisions, merged, threshold=70):
    """저장 4단계 폴백 1단계(유도)의 대상 산출.

    자동 유도는 **확신도가 임계 이상인 것만** 한다. 미달은 이룸님 수동 큐로 남긴다
    (확신도는 '키워드↔카테고리' 신뢰도라, 낮은 걸 유도 저장하면 확신에 찬 오답이 굳는다).
    """
    mg = {m.get("productId"): m for m in merged}
    items, skipped = [], {"확신도미달": [], "경로없음": []}
    for d in decisions:
        if d.get("상태") not in ("매칭불가", "부분일치확인요"):
            continue
        pid = d.get("productId")
        m = mg.get(pid) or {}
        target = (m.get("sellha경로") or "").strip()
        if not target:
            skipped["경로없음"].append(pid)
            continue
        conf = _conf(d.get("확신도"))
        if conf is None or conf < float(threshold):
            skipped["확신도미달"].append(pid)
            continue
        items.append({
            "productId": pid, "row": d.get("row"), "target": target,
            "keyword": m.get("최종차수", ""), "mode": "exact",
            "상품명": d.get("상품명", ""), "기존카테고리": d.get("기존카테고리", ""),
            "확신도": d.get("확신도", ""),
        })
    return items, skipped


def _conf(v):
    try:
        return float(str(v).replace("%", "").strip())
    except (TypeError, ValueError):
        return None


# ── consensus(2/3) — 저확신·매칭불가 잔여의 자동 승격 (2026-08-05 이룸님 확정) ──
# 원검색어 1표 + Claude 가 만든 변형 2표. 전체 경로가 2표 이상 일치하면 저장을
# 승격한다(통과분만 자동, 실패분은 건드리지 않고 종합보고). 규칙 원문은
# SKILL.md §검색어 변형 consensus — 변형 도출 자체는 Claude 가 한다(분야 한정어 유지).

def _norm_cat(p):
    """경로 정규화 — '>' 둘레 공백 차이로 같은 경로가 다른 표가 되는 걸 막는다."""
    return ">".join(s.strip() for s in str(p or "").split(">") if s.strip())


def consensus_targets(decisions, merged, kw_map, steer_saved):
    """consensus 대상 = 미저장 잔여.

    - `변경대상`: 정확일치인데 확신도<임계라 apply 가 커밋하지 않은 건
    - `매칭불가`·`부분일치확인요`: steer(유도)로도 저장 안 된 건
    sellha조회실패·보류·이미정확은 제외 — 원경로(1표)가 없거나 저장이 필요 없다.
    원경로가 빈 건도 제외한다(1표가 없으면 2/3 자체가 성립 불가 → 수동 큐).
    """
    mg = {m.get("productId"): m for m in merged}
    out = []
    for d in decisions:
        st, pid = d.get("상태"), d.get("productId")
        if st == "변경대상":
            pass
        elif st in ("매칭불가", "부분일치확인요"):
            if pid in steer_saved:
                continue
        else:
            continue
        m = mg.get(pid) or {}
        path = _norm_cat(m.get("sellha경로"))
        if not path:
            continue
        out.append({
            "productId": pid, "row": d.get("row"), "상품명": d.get("상품명", ""),
            "기존카테고리": d.get("기존카테고리", ""),
            "실물판정": (kw_map.get(pid) or {}).get("실물판정", ""),
            "원검색어": m.get("검색어", ""), "원경로": path,
            "원최종차수": m.get("최종차수", "") or path.split(">")[-1],
            "원확신도": m.get("확신도", ""), "원상태": st,
        })
    return out


def consensus_vote(votes_in):
    """3표(원검색어+변형2)의 전체 경로 일치 판정 — 순수 함수(test_run_all.py 대상).

    입력: [{"경로", "확신도", "최종차수", "검색어"}] (경로 빈 표는 무효표로 버린다)
    - 같은 경로 2표 이상        → `채택` (확신도 = 일치 표 중 최고, keyword = 그 표의 최종차수)
    - 유효 3표가 전부 다른 경로 → `실물판정의심` (검색어가 아니라 실물 판정이 흔들린다
                                   — 기존 규칙의 '변형끼리 불일치 = recheck 신호')
    - 그 외(유효표 부족·불일치)  → `합의없음`
    """
    from collections import Counter
    votes = []
    for r in votes_in:
        p = _norm_cat(r.get("경로"))
        if p:
            votes.append({"경로": p, "확신도": _conf(r.get("확신도")) or 0.0,
                          "최종차수": r.get("최종차수") or p.split(">")[-1],
                          "검색어": r.get("검색어", "")})
    cnt = Counter(v["경로"] for v in votes)
    if cnt:
        top, n = cnt.most_common(1)[0]
        if n >= 2:
            best = max((v for v in votes if v["경로"] == top),
                       key=lambda v: v["확신도"])
            return {"판정": "채택", "target": top, "확신도": best["확신도"],
                    "keyword": best["최종차수"], "표": votes}
    if len(votes) >= 3 and len(cnt) == len(votes):
        return {"판정": "실물판정의심", "표": votes}
    return {"판정": "합의없음", "표": votes}


def _post_steer_matrix(sheet, result_path, label="유도"):
    """steer 계열(유도·consensus) 저장 후 공통 후처리 — 현황판 카테고리 완료 표시
    + 상품명 재작업 이관. (bulsaja_mcp.py apply 가 자동저장분에 하는 일과 같은 계약)

    반환: 저장된 pid set (호출자가 집계·보고에 쓴다)
    """
    try:
        with open(result_path, encoding="utf-8") as f:
            res = json.load(f)
    except OSError:
        return set()
    saved = {r["productId"] for r in res if r.get("saved")}
    if not saved:
        print(f"  {label} 저장 0건 — 현황판 변경 없음")
        return saved
    try:
        from eroomlib import matrix
        m = matrix.read(sheet)
        n = matrix.mark_many(sheet, "카테고리",
                             {p: "완료" for p in saved}, matrix=m)
        k = matrix.flag_many(sheet, "상품명",
                             {p: "카테고리 변경 — 키워드 재선정 필요" for p in saved},
                             from_task="카테고리", matrix=m)
        print(f"  현황판 카테고리 {n}칸 · 상품명 재작업 {k}건")
    except Exception as e:  # noqa: BLE001
        print(f"  [경고] 현황판 갱신 실패: {str(e)[:120]}", file=sys.stderr)
    return saved


def cmd_consensus(args):
    """consensus 2단계 — prep(대상 추출) / run(변형 조회→2/3 판정→유도 저장).

    Claude 판단(변형 도출)이 중간에 끼므로 catfix 본체(prep→finish)와 같은 2단계다.
      prep: 미저장 잔여 → consensus_targets.json + 변형 작성 안내
      (Claude 가 consensus_variants.json 작성: [{productId, 변형: ["v1","v2"]}])
      run : 변형만 조회(원검색어 1표는 이미 있다) → 2/3 판정 → 통과분 category_steer
            (위험 라벨 consensus(2/3)) → 현황판 후처리. 실패분은 consensus_fail.json.
    """
    tpath = _p(args.run_dir, "consensus_targets.json")

    if args.stage == "prep":
        with open(_p(args.run_dir, "decisions.json"), encoding="utf-8") as f:
            decisions = json.load(f)
        with open(_p(args.run_dir, "merged.json"), encoding="utf-8") as f:
            merged = json.load(f)
        kw_path = _p(args.run_dir, "keywords.json")
        kw_map = {}
        if os.path.exists(kw_path):
            with open(kw_path, encoding="utf-8") as f:
                kw_map = {k.get("productId"): k for k in json.load(f)}
        steer_saved = set()
        sr_path = _p(args.run_dir, "steer_result.json")
        if os.path.exists(sr_path):
            with open(sr_path, encoding="utf-8") as f:
                steer_saved = {r["productId"] for r in json.load(f) if r.get("saved")}
        targets = consensus_targets(decisions, merged, kw_map, steer_saved)
        with open(tpath, "w", encoding="utf-8") as f:
            json.dump(targets, f, ensure_ascii=False, indent=2)
        by_st = {}
        for t in targets:
            by_st[t["원상태"]] = by_st.get(t["원상태"], 0) + 1
        print(f"[consensus prep] 대상 {len(targets)}건 "
              + json.dumps(by_st, ensure_ascii=False) + f" → {tpath}")
        if targets:
            print("다음: 각 건의 실물판정·원검색어로 **변형 2개**를 만들어 "
                  f"{_p(args.run_dir, 'consensus_variants.json')} 작성")
            print('  형식: [{"productId": "...", "변형": ["변형1", "변형2"]}]')
            print("  규칙: SKILL.md §검색어 변형 consensus (분야 한정어 유지, 실물판정 불변)")
            print(f"그 후: python run_all.py consensus run --run-dir {args.run_dir}")
        return

    # ── run ──
    with open(tpath, encoding="utf-8") as f:
        targets = json.load(f)
    if not targets:
        print("[consensus run] 대상 0건")
        return
    vpath = _p(args.run_dir, "consensus_variants.json")
    with open(vpath, encoding="utf-8") as f:
        variants = {v.get("productId"): [s for s in (v.get("변형") or []) if s]
                    for v in json.load(f)}

    # 변형만 조회한다 — 원검색어 1표는 sellha.json(=merged 원경로)에 이미 있다.
    queries = [{"productId": t["productId"], "name": v}
               for t in targets for v in variants.get(t["productId"], [])]
    qpath = _p(args.run_dir, "consensus_queries.json")
    rpath = _p(args.run_dir, "consensus_result.json")
    if queries:
        with open(qpath, "w", encoding="utf-8") as f:
            json.dump(queries, f, ensure_ascii=False, indent=2)
        # 캡챠·차단이면 aside 가 비정상 종료 → sh 가 예외로 멈춘다(수동 해제 후 재실행,
        # --resume 이라 조회분은 보존된다).
        sh(CAT_SCRIPT, "--input", qpath, "--output", rpath, "--resume",
           "--sleep", args.sellha_sleep, "--sleep-max", args.sellha_sleep_max)
    rows = []
    if os.path.exists(rpath):
        with open(rpath, encoding="utf-8") as f:
            rows = json.load(f)
    by_pid = {}
    for r in rows:
        by_pid.setdefault(r.get("productId"), []).append(r)

    steer_in, fails = [], {"합의없음": [], "실물판정의심": [], "변형없음": []}
    for t in targets:
        pid = t["productId"]
        if not variants.get(pid):
            fails["변형없음"].append({"productId": pid, "원검색어": t["원검색어"]})
            continue
        votes = [{"경로": t["원경로"], "확신도": t["원확신도"],
                  "최종차수": t["원최종차수"], "검색어": t["원검색어"]}]
        votes += [{"경로": r.get("카테고리경로", ""), "확신도": r.get("확신도", ""),
                   "최종차수": r.get("최종차수", ""), "검색어": r.get("검색어", "")}
                  for r in by_pid.get(pid, [])]
        v = consensus_vote(votes)
        if v["판정"] == "채택":
            steer_in.append({
                "productId": pid, "row": t.get("row"), "target": v["target"],
                "keyword": v["keyword"], "mode": "exact",
                "상품명": t.get("상품명", ""), "기존카테고리": t.get("기존카테고리", ""),
                "확신도": v["확신도"], "위험": "consensus(2/3)",
            })
        else:
            fails[v["판정"]].append({"productId": pid, "원검색어": t["원검색어"],
                                     "표": v["표"]})
    fpath = _p(args.run_dir, "consensus_fail.json")
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(fails, f, ensure_ascii=False, indent=2)
    print(f"[consensus run] 채택 {len(steer_in)} · 합의없음 {len(fails['합의없음'])} "
          f"· 실물판정의심 {len(fails['실물판정의심'])} · 변형없음 {len(fails['변형없음'])}")

    if not steer_in:
        print("###CONSENSUS### 저장 0건 (전건 수동 큐 → 종합보고)")
        return
    sin = _p(args.run_dir, "consensus_steer.json")
    sout = _p(args.run_dir, "consensus_steer_result.json")
    with open(sin, "w", encoding="utf-8") as f:
        json.dump(steer_in, f, ensure_ascii=False, indent=2)
    steer_args = ["--input", sin, "--output", sout, "--sleep", args.sleep]
    if args.dry_run:
        steer_args.append("--dry-run")
    if not args.no_sheet:
        steer_args += ["--sheet", args.sheet]
    sh("category_steer.py", *steer_args)
    if args.dry_run or args.no_sheet:
        return
    saved = _post_steer_matrix(args.sheet, sout, label="consensus")
    print(f"###CONSENSUS### 채택 {len(steer_in)} / 저장 {len(saved)} / "
          f"수동잔여 {len(fails['합의없음']) + len(fails['실물판정의심']) + len(fails['변형없음'])}")


RULES_DOC = os.path.normpath(os.path.join(
    SCRIPT_DIR, "..", "references", "대표검색어-도출.md"))
WORKER_PROMPT = os.path.normpath(os.path.join(
    SCRIPT_DIR, "..", "references", "판정-워커-프롬프트.md"))


def cmd_batch(args):
    """names.json → batches/batch_NNN.json + batches_index.json.

    Workflow 스크립트는 파일시스템이 없다 — pending·이미지수를 여기서 미리 계산해
    index 에 박아 두면 호출자가 그대로 args 로 넘길 수 있다.
    """
    names = _p(args.run_dir, "names.json")
    with open(names, encoding="utf-8") as f:
        names_list = json.load(f)
    bdir = _p(args.run_dir, "batches")
    os.makedirs(bdir, exist_ok=True)
    os.makedirs(_p(args.run_dir, "named"), exist_ok=True)
    batches = make_batches(names_list, args.size, RULES_DOC)
    index = []
    for b in batches:
        path = os.path.abspath(os.path.join(bdir, f"batch_{b['batch']:03d}.json"))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(b, f, ensure_ascii=False, indent=2)
        index.append({"n": b["batch"], "path": path, "imgs": b["이미지수"],
                      "count": len(b["products"])})
    idx_path = _p(args.run_dir, "batches_index.json")
    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print(f"[batch] {len(names_list)}건 → 배치 {len(index)}개 (건당 {args.size}) → {bdir}")
    print(f"  index: {idx_path}")
    print(f"  워커 지시서: {WORKER_PROMPT}")


def _pending_batches(run_dir):
    """named/named_NNN.json 이 없는 배치 = 아직 안 된 것. 디스크가 정본이다."""
    idx_path = _p(run_dir, "batches_index.json")
    if not os.path.exists(idx_path):
        return []
    with open(idx_path, encoding="utf-8") as f:
        index = json.load(f)
    ndir = _p(run_dir, "named")
    return [b for b in index
            if not os.path.exists(os.path.join(ndir, f"named_{b['n']:03d}.json"))]


def cmd_pending(args):
    """남은 배치를 JSON 한 줄로 찍는다 — Workflow args 에 그대로 넣는다."""
    pend = _pending_batches(args.run_dir)
    print(json.dumps({"runDir": os.path.abspath(args.run_dir),
                      "promptPath": WORKER_PROMPT,
                      "batches": pend}, ensure_ascii=False))


def cmd_merge(args):
    """named/*.json → keywords.json. 누락·중복·환각을 여기서 잡는다."""
    with open(_p(args.run_dir, "names.json"), encoding="utf-8") as f:
        expected = [n["productId"] for n in json.load(f)]
    ndir = _p(args.run_dir, "named")
    docs = []
    for fn in sorted(os.listdir(ndir)) if os.path.isdir(ndir) else []:
        if not fn.startswith("named_") or not fn.endswith(".json"):
            continue
        with open(os.path.join(ndir, fn), encoding="utf-8") as f:
            docs.append(json.load(f))
    kw, rep = merge_named(docs, expected)
    out = args.keywords or _p(args.run_dir, "keywords.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(kw, f, ensure_ascii=False, indent=2)
    print(f"[merge] 워커산출 {len(docs)}파일 → {len(kw)}건 → {out}")
    print(f"  생성 {rep['named']} · 보류 {len(rep['held'])} · 중복덮어씀 {rep['dups']}")
    if rep["unknown"]:
        print(f"  [경고] 미지의 상품id {len(rep['unknown'])}건 버림: {rep['unknown'][:5]}")
    if rep["missing"]:
        print(f"  [경고] 누락 {len(rep['missing'])}건 — 해당 배치 재팬아웃 필요: "
              f"{rep['missing'][:5]}")
        if not args.allow_missing:
            print("###MERGE### 미완 — 재팬아웃 후 다시 실행 (강행은 --allow-missing)")
            sys.exit(3)
    print("###MERGE### " + json.dumps(
        {k: (len(v) if isinstance(v, list) else v) for k, v in rep.items()},
        ensure_ascii=False))


def cmd_steer(args):
    """저장 폴백 1단계(유도) 자동 실행 — 매칭불가·부분일치를 목표 경로로 밀어 넣는다."""
    dec_path = _p(args.run_dir, "decisions.json")
    mg_path = _p(args.run_dir, "merged.json")
    if not os.path.exists(dec_path):
        print("[steer] decisions.json 이 없다 — finish 를 먼저 돌린다.")
        return
    with open(dec_path, encoding="utf-8") as f:
        decisions = json.load(f)
    with open(mg_path, encoding="utf-8") as f:
        merged = json.load(f)
    items, skipped = steer_items(decisions, merged, threshold=float(args.threshold))
    print(f"[steer] 대상 {len(items)}건 · 확신도미달 {len(skipped['확신도미달'])} "
          f"· 경로없음 {len(skipped['경로없음'])}")
    if not items:
        return
    sin = _p(args.run_dir, "steer.json")
    sout = _p(args.run_dir, "steer_result.json")
    with open(sin, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    steer_args = ["--input", sin, "--output", sout, "--sleep", args.sleep]
    if args.dry_run:
        steer_args.append("--dry-run")
    if not args.no_sheet:
        steer_args += ["--sheet", args.sheet]
    sh("category_steer.py", *steer_args)
    if args.dry_run or args.no_sheet:
        return
    # 저장된 건은 카테고리가 실제로 바뀐 것 → 현황판 갱신 + 상품명 재작업 이관.
    _post_steer_matrix(args.sheet, sout, label="유도")


def cmd_auto(args):
    """merge → finish → steer 를 한 프로세스로. **백그라운드로 띄우는 진입점.**

    조회가 ~10초/건이라 수백 건이면 몇 시간이 걸린다. 대화 세션이 이걸 붙잡고 있으면
    턴이 쌓여 컨텍스트가 차고, 그래서 지금까지 세션이 쪼개졌다. 한 프로세스로 묶어
    백그라운드에 두면 메인은 시작·확인 두 턴이면 된다.
    """
    class A:  # 서브커맨드 인자 재사용용 얇은 어댑터
        pass

    a = A()
    a.run_dir, a.keywords, a.allow_missing = args.run_dir, args.keywords, args.allow_missing
    cmd_merge(a)

    a.threshold, a.sleep, a.dry_run = args.threshold, args.sleep, args.dry_run
    a.no_sheet, a.sheet, a.force = args.no_sheet, args.sheet, args.force
    a.sellha_sleep = args.sellha_sleep
    a.sellha_sleep_max = args.sellha_sleep_max
    a.sellha_rest_every = args.sellha_rest_every
    a.skip_sellha = getattr(args, "skip_sellha", False)
    a.overwrite_done = getattr(args, "overwrite_done", False)
    cmd_finish(a)

    a.sleep = "0.3"
    cmd_steer(a)
    print("\n" + "=" * 56)
    print("[auto 완료] 남은 것 = 확신도 미달·유도 실패 건의 수동 판정")


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
    f.add_argument("--force", action="store_true", help="카테고리 재조회")
    f.add_argument("--overwrite-done", action="store_true",
                   help="시트에 이미 `저장완료`인 행도 덮어쓴다(기본은 보호·건너뜀)")
    f.add_argument("--skip-sellha", action="store_true",
                   help="카테고리 조회 생략 — sellha.json 에 이미 있는 건만 저장(미조회분은 병합 제외)")
    f.add_argument("--sellha-sleep", default="1",
                   help="카테고리 조회 간 최소 대기(초). Aside 전환으로 3→1")
    f.add_argument("--sellha-sleep-max", default="3",
                   help="카테고리 조회 간 최대 대기(초). 실제는 최소~최대 난수")
    f.add_argument("--sellha-rest-every", default="25",
                   help="(현 엔진에선 미사용) 평균 N건마다 긴 휴식")
    f.set_defaults(func=cmd_finish)

    b = sub.add_parser("batch", help="names.json → batches/ (팬아웃 단위)")
    b.add_argument("--run-dir", required=True)
    b.add_argument("--size", type=int, default=8, help="배치당 상품 수(기본 8)")
    b.set_defaults(func=cmd_batch)

    pd = sub.add_parser("pending", help="남은 배치를 Workflow args JSON 으로 출력")
    pd.add_argument("--run-dir", required=True)
    pd.set_defaults(func=cmd_pending)

    mg = sub.add_parser("merge", help="named/*.json → keywords.json")
    mg.add_argument("--run-dir", required=True)
    mg.add_argument("--keywords", help="출력 경로(기본 run-dir/keywords.json)")
    mg.add_argument("--allow-missing", action="store_true",
                    help="누락이 있어도 강행(기본은 exit 3)")
    mg.set_defaults(func=cmd_merge)

    st = sub.add_parser("steer", help="저장 폴백 1단계(유도) 자동 실행")
    st.add_argument("--run-dir", required=True)
    st.add_argument("--threshold", default="70")
    st.add_argument("--sleep", default="0.3")
    st.add_argument("--dry-run", action="store_true")
    st.add_argument("--no-sheet", action="store_true")
    st.set_defaults(func=cmd_steer)

    au = sub.add_parser("auto", help="merge→finish→steer (백그라운드 진입점)")
    au.add_argument("--run-dir", required=True)
    au.add_argument("--keywords")
    au.add_argument("--allow-missing", action="store_true")
    au.add_argument("--threshold", default="70")
    au.add_argument("--sleep", default="0.4")
    au.add_argument("--dry-run", action="store_true")
    au.add_argument("--no-sheet", action="store_true")
    au.add_argument("--force", action="store_true", help="카테고리 재조회")
    au.add_argument("--overwrite-done", action="store_true",
                    help="시트에 이미 `저장완료`인 행도 덮어쓴다(기본은 보호·건너뜀)")
    au.add_argument("--skip-sellha", action="store_true",
                    help="카테고리 조회 생략 — sellha.json 에 이미 있는 건만 저장")
    au.add_argument("--sellha-sleep", default="1",
                   help="카테고리 조회 간 최소 대기(초). Aside 전환으로 3→1")
    au.add_argument("--sellha-sleep-max", default="3",
                   help="카테고리 조회 간 최대 대기(초). 실제는 최소~최대 난수")
    au.add_argument("--sellha-rest-every", default="25",
                   help="(현 엔진에선 미사용) 평균 N건마다 긴 휴식")
    au.set_defaults(func=cmd_auto)

    r = sub.add_parser("recheck", help="2바퀴: 보류(정체불명) 건 증거 보강")
    r.add_argument("--run-dir", required=True)
    r.add_argument("--keywords", help="keywords.json 경로(기본 run-dir/keywords.json)")
    r.add_argument("--ids", nargs="+", help="대상 productId 직접 지정(기본=보류 전건)")
    r.set_defaults(func=cmd_recheck)

    cs = sub.add_parser("consensus",
                        help="저확신·매칭불가 잔여의 검색어 변형 2/3 자동 승격 (prep→run)")
    cs.add_argument("stage", choices=["prep", "run"])
    cs.add_argument("--run-dir", required=True)
    cs.add_argument("--sleep", default="0.3", help="steer 저장 간격(초)")
    cs.add_argument("--sellha-sleep", default="1")
    cs.add_argument("--sellha-sleep-max", default="3")
    cs.add_argument("--dry-run", action="store_true")
    cs.add_argument("--no-sheet", action="store_true")
    cs.set_defaults(func=cmd_consensus)

    # prep/finish 는 상위 --sheet/--tab 을 물려받도록 보정
    args = ap.parse_args()
    if not hasattr(args, "sheet"):
        args.sheet = SHEET
    args.func(args)


if __name__ == "__main__":
    main()
