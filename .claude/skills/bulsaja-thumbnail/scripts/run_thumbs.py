#!/usr/bin/env python3
"""썸네일 오케스트레이터 — 스킬 계약(`prep`/`run`/`apply`)을 그대로 따른다.

  prep    : 현황판 대상 확정 → 스냅샷 → **기작업(이미 가공됨) 자동 완료 처리** →
            후보 이미지 확보 → 배치 파일
  run     : **Claude** 가 배치를 읽고 기준 이미지 선택(+레시피 모드면 배경 전략·프롬프트
            작성) → results/result_*.json (스크립트 아님)
  apply   : 게이트가 2번 있다 — 생성 자체가 크레딧을 쓰고, 생성 후 자동반영이 실측
            확인됐기 때문이다(2026-07-28 파일럿).
      apply                 미리보기(대상+기준이미지+예상크레딧). 쓰기 0.
      apply --generate      (게이트1 승인 후) 실제 생성 → 폴링 → **자동반영 방어**
                            (대표가 바뀌었으면 승인 전까지 원래 순서로 복원) →
                            review.html 생성. 여기서 크레딧이 실제로 든다.
      apply --commit        (검수 페이지로 게이트2 승인 후) decisions.json 을 읽어
                            최종 대표 순서로 반영 → 재조회 확인 → 시트·스냅샷·현황판
  restore : before_generate.json 으로 생성 전 순서로 되돌린다.

사용:
  python run_thumbs.py prep    --group-name "1번_용쌤1-1" --run-dir <R> --limit 5
  python run_thumbs.py pending --run-dir <R>            # Workflow(thumb-fanout) args 출력
  python run_thumbs.py apply   --run-dir <R>            # 미리보기
  python run_thumbs.py apply   --run-dir <R> --generate # 실제 생성(크레딧 소모)
  python run_thumbs.py apply   --run-dir <R> --commit   # decisions.json 대로 반영
"""
import argparse
import glob
import json
import os
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

_d = SCRIPT_DIR
while _d and _d != os.path.dirname(_d):
    _lib = os.path.join(_d, "lib")
    if os.path.isdir(os.path.join(_lib, "eroomlib")):
        if _lib not in sys.path:
            sys.path.insert(0, _lib)
        break
    _d = os.path.dirname(_d)

import review_html                                    # noqa: E402
import thumb_rules as R                                # noqa: E402
from eroomlib import matrix, snapshot                  # noqa: E402
from eroomlib.gsheets import (append_rows, ensure_tab,  # noqa: E402
                              sheets_get, sheets_update)
from eroomlib.matrix import _col_letter                # noqa: E402

TASK = "썸네일"        # 현황판 열 이름
TAB = "썸네일"         # 상세 로그 탭
HEADER = ["상품id", "작업일", "상품명", "모드", "기존대표", "생성본",
          "판정", "사유", "크레딧", "상태"]

BATCH_SIZE = 10
MAX_CANDIDATES = 5     # 배치에 실을 후보(대표 제외) 이미지 상한
POLL_INTERVAL = 10
POLL_TIMEOUT = 300

# 팬아웃용 고정 경로 — 규칙 정본과 워커 지시서.
RULES_DOC = os.path.normpath(os.path.join(
    SCRIPT_DIR, "..", "references", "배경생성-기본.md"))
WORKER_PROMPT = os.path.normpath(os.path.join(
    SCRIPT_DIR, "..", "references", "썸네일-워커-프롬프트.md"))


def _dump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _today():
    import datetime
    return datetime.date.today().isoformat()


class ThumbMCP(snapshot.ProductMCP):
    """transport + workdata 는 상속하고, 썸네일 전용 도구만 얹는다."""

    def generate(self, product_id, prompt=None, rendering_speed="TURBO"):
        """AI 썸네일 생성 접수 — confirm 2단계(카테고리 저장과 같은 패턴).

        prompt 를 생략하면 불사자에 저장된 기본 프롬프트가 쓰인다(2026-07-28 실측 확인).
        반환: {"taskId", "expectedCredits"}.
        """
        payload = {"productId": product_id, "renderingSpeed": rendering_speed}
        if prompt:
            payload["prompt"] = prompt
        pv = self.call_tool("bulsaja_thumbnail_ai_generate", payload)
        token = pv.get("confirmationToken")
        if not token:
            raise RuntimeError(f"확인키 미발급: {str(pv.get('message'))[:200]}")
        r = self.call_tool("bulsaja_thumbnail_ai_generate",
                           {**payload, "confirm": True, "confirmationToken": token})
        if not r.get("success"):
            raise RuntimeError(f"생성 접수 실패: {str(r.get('message'))[:200]}")
        return {"taskId": r.get("taskId") or r.get("작업번호"),
                "expectedCredits": r.get("expectedCredits") or r.get("필요크레딧") or 0}

    def poll(self, task_id, interval=POLL_INTERVAL, timeout=POLL_TIMEOUT):
        """완료까지 폴링. 반환: (생성이미지[], 사용크레딧). 실패/타임아웃이면 예외.

        본체는 `ProductMCP.poll_ai_task` — 상세 스킬과 같은 도구를 쓴다(Step6에서 공용화).
        """
        return self.poll_ai_task(task_id, target="thumbnail",
                                 interval=interval, timeout=timeout)

    def update_thumbnails(self, product_id, thumbnails):
        """대표이미지 확정 — confirm 2단계. thumbnails[0] 이 대표가 된다."""
        pv = self.call_tool("bulsaja_thumbnail_update",
                            {"productId": product_id, "thumbnails": thumbnails})
        token = pv.get("confirmationToken")
        if not token:
            if pv.get("success"):
                return pv
            raise RuntimeError(f"확인키 미발급: {str(pv.get('message'))[:200]}")
        r = self.call_tool("bulsaja_thumbnail_update",
                           {"productId": product_id, "thumbnails": thumbnails,
                            "confirm": True, "confirmationToken": token})
        if not r.get("success"):
            raise RuntimeError(f"저장 실패: {str(r.get('message'))[:200]}")
        return r


# ---------------------------------------------------------------------------
# prep
# ---------------------------------------------------------------------------

def _resolve_sheet(args):
    if getattr(args, "sheet", None):
        return args.sheet
    name = (getattr(args, "group_name", "") or "").strip()
    if not name:
        raise RuntimeError("--sheet 또는 --group-name 중 하나는 필요하다")
    for g, sid in matrix.index_groups():
        if g == name:
            return sid
    hits = [(g, sid) for g, sid in matrix.index_groups() if name in g]
    if len(hits) != 1:
        raise RuntimeError(f"'{name}' 으로 그룹 시트를 특정하지 못했다(후보 {len(hits)}개)")
    return hits[0][1]


def cmd_prep(args):
    run_dir = os.path.abspath(args.run_dir)
    os.makedirs(run_dir, exist_ok=True)
    sheet = _resolve_sheet(args)
    print(f"  시트: {sheet}")

    m = matrix.read(sheet)
    if args.ids:
        pids = [i for i in args.ids if i.strip()]
    else:
        pids = matrix.pending(m, TASK)
        print(f"[1/4] 현황판 '{TASK}' 대상(미착수+재작업) {len(pids)}건")
    if args.limit:
        pids = pids[:args.limit]
        print(f"  --limit {args.limit} 적용 → {len(pids)}건")
    if not pids:
        # 0건도 정상 완료다 — 산출물이 없으면 호출자가 'prep 실패'와 구분하지 못한다.
        _dump(os.path.join(run_dir, "batches_index.json"),
              {"대상": 0, "이유": "현황판 대상 0건"})
        print("처리할 상품이 없다.")
        return

    print(f"[2/4] 스냅샷 확보 {len(pids)}건")
    recs, errors = snapshot.ensure(pids, sleep=args.sleep)
    if errors:
        print(f"  조회 실패 {len(errors)}건: {list(errors)[:3]}")

    # 기작업 필터 — 대표가 이미 가공됐으면 대상에서 빼고 즉시 완료 처리한다.
    # 단 **재작업 flag 가 있으면 절대 빼지 않는다** — 이미 가공됐다는 사실 자체가
    # 재작업 사유(예: 잘못된 색을 대표로 씀)일 수 있다. URL 판별은 "손을 아예 안 댄
    # 상품"만 걸러내려는 것이지, "이미 손댔지만 잘못됐다"를 걸러내려는 게 아니다.
    redo = matrix.redo_pending(m, TASK)
    already, targets = {}, []
    for pid in pids:
        rec = recs.get(pid)
        if not rec:
            continue
        if pid in redo:
            targets.append(pid)
            continue
        thumbs = rec.get("썸네일") or []
        if R.is_already_done(thumbs):
            already[pid] = "완료(기존 가공 확인)"
        else:
            targets.append(pid)
    if already:
        n = matrix.mark_many(sheet, TASK, already, matrix=m)
        print(f"[3/4] 기작업 백필 {n}건(대표가 이미 cdn.bulsaja.com)")
    print(f"  실제 대상 {len(targets)}건")
    if not targets:
        if errors:
            # 조회 실패로 대상이 빈 것까지 '전부 기작업' sentinel 로 남기면, 세로
            # 러너가 이 단계를 DONE 으로 기록해버린다(onestep._zero_target). 유료·
            # 자동반영 파이프라인에서 "데이터를 못 봤다"가 "볼 필요 없었다"로
            # 둔갑하는 셈이라, sentinel 을 아예 안 남기고 예전처럼 prep_out 산출물
            # 누락으로 러너가 멈추게(fail-closed) 둔다.
            print(f"  실제 대상 0건이지만 조회 실패 {len(errors)}건이 섞여 있다 — "
                  f"'전부 기작업'으로 기록하지 않고 산출물 없이 중단한다.")
            return
        # 산출물을 안 남기면 onestep(세로 러너)의 prep 산출물 확인이 실패로 본다
        # ("exit 0 이어도 대상 0건은 정상"이라는 규칙과 별개로, 파일 자체가 없으면
        # 구분을 못 한다). 대상 0건도 **정상 완료**임을 알 수 있게 인덱스를 남긴다.
        # (빈 배열 `[]`은 2바이트라 "산출물 없음" 크기 검사(<3바이트)에 걸리므로 dict로 쓴다.)
        _dump(os.path.join(run_dir, "batches_index.json"),
              {"대상": 0, "이유": "전부 기작업(대표가 이미 cdn.bulsaja.com)"})
        print("실제 생성이 필요한 상품이 없다(전부 기작업).")
        return

    thumbs_dir = os.path.join(run_dir, "thumbs")
    products = []
    dead = {}    # 대표 원본이 404 = 타오바오에서 이미지가 내려감 → 삭제 대상(이룸님 판단 대기)
    for pid in targets:
        rec = recs[pid]
        why = matrix.redo_pending(m, TASK).get(pid, "")
        thumbs = rec.get("썸네일") or []
        rep_path = ""
        if thumbs:
            p, err = snapshot.materialize_image(thumbs[0], thumbs_dir, pid + "_rep", 0)
            rep_path = p or ""
            # 원본 404 = 소싱 원본 이미지가 내려갔다는 신호 — 썸네일을 새로 만들 대상이
            # 아니라 **삭제 대상**으로 기재한다(2026-08-01 이룸님). 워커에 보내지 않는다.
            if not p and "404" in str(err or ""):
                dead[pid] = rec.get("상품명", "")
                continue
        cand_paths = []
        for i, url in enumerate(thumbs[1:1 + args.max_candidates], 1):
            p, _ = snapshot.materialize_image(url, thumbs_dir, pid + "_cand", i)
            if p:
                cand_paths.append({"index": i, "url": url, "path": p})
        # 대표옵션 — 있으면 **이게 기준 이미지다**(Claude 가 후보 중에서 고르지 않는다).
        # 네이버는 '대표상품'(추가금 0원 옵션)을 상품명으로 쓰라고 요구하므로
        # 썸네일=대표옵션=상품명이 한 옵션을 지칭해야 한다(2026-07-30 이룸님).
        # None = 옵션정리 미완료(대표 미지정) 또는 옵션 없는 단일상품 → 종전 비전 판단.
        mo = R.main_option_of(rec.get("옵션"))
        mo_path = ""
        if mo and mo.get("이미지"):
            p, _ = snapshot.materialize_image(mo["이미지"], thumbs_dir, pid + "_main", 0)
            mo_path = p or ""
        products.append({
            "productId": pid,
            "상품명": rec.get("상품명", ""),
            "재작업사유": R.redo_reason_from_flag(why) if why else "",
            "기존썸네일": thumbs,
            "대표이미지": rep_path,
            "후보이미지": cand_paths,
            "대표옵션명": (mo or {}).get("이름", ""),
            "대표옵션이미지": (mo or {}).get("이미지", ""),
            "대표옵션이미지경로": mo_path,
        })

    # 원본 404 삭제 대상 — 파일·현황판에 기재하고 이룸님께 보고한다. 현황판 값이
    # 보류라 pending 에서 자동으로 빠진다(재작업 루프 차단). 실제 삭제는 이룸님 몫.
    if dead:
        _dump(os.path.join(run_dir, "deletion_candidates.json"), dead)
        try:
            matrix.mark_many(sheet, TASK,
                             {pid: "보류(원본404·삭제대상)" for pid in dead}, matrix=m)
        except Exception as e:  # noqa: BLE001
            print(f"  [경고] 삭제대상 현황판 기재 실패: {str(e)[:120]}", file=sys.stderr)
        print(f"\n  ★★ 삭제 대상 {len(dead)}건 — 타오바오 원본 이미지 404 ★★")
        for pid, name in dead.items():
            print(f"    {pid}  {name[:40]}")
        print(f"    기록: {os.path.join(run_dir, 'deletion_candidates.json')} + 현황판 '{TASK}' 열")
    if not products:
        _dump(os.path.join(run_dir, "batches_index.json"),
              {"대상": 0, "이유": f"원본404 삭제대상 {len(dead)}건 기재" if dead
               else "대상 0건"})
        print("생성 대상이 없다.")
        return

    # 확정건 선기록 — 대표옵션이미지경로가 있으면 규칙 0("고르지 않는다")이라 판단이 0이다.
    # prep 이 직접 results/result_000.json 에 기록하고 배치에서 뺀다 → 워커 비용이 정확히
    # 0장이 되고, 워커 환각이 이 건들의 pass-through 필드를 훼손할 표면 자체가 사라진다.
    fixed = [p for p in products if p.get("대표옵션이미지경로")]
    vision = [p for p in products if not p.get("대표옵션이미지경로")]
    if fixed:
        _dump(os.path.join(run_dir, "results", "result_000.json"),
              {"배치": 0, "선기록": True,
               "products": [{**p, "기준이미지경로": p["대표옵션이미지경로"],
                             "모드": "기본"} for p in fixed]})

    batches = [vision[i:i + args.batch_size]
               for i in range(0, len(vision), args.batch_size)]
    index = []
    for i, b in enumerate(batches, 1):
        path = os.path.abspath(os.path.join(run_dir, "batches", f"batch_{i:03d}.json"))
        _dump(path, {"배치": i, "규칙문서": RULES_DOC, "products": b})
        # imgs = 워커가 열 수 있는 이미지 상한(대표 1 + 후보 ≤5) — 팬아웃 빈패킹의 예산 축.
        index.append({"n": i, "path": path,
                      "imgs": sum((1 if p.get("대표이미지") else 0)
                                  + len(p.get("후보이미지") or []) for p in b),
                      "count": len(b)})
    if index:
        _dump(os.path.join(run_dir, "batches_index.json"), index)
    else:
        # 전건 확정 선기록 — 배치가 0개여도 prep 은 정상 완료다. sentinel(`대상`)과
        # 다른 dict 를 남긴다(러너 _zero_target 은 `대상` 키만 sentinel 로 본다).
        _dump(os.path.join(run_dir, "batches_index.json"),
              {"배치": 0, "확정선기록": len(fixed)})
    print(f"\n###PREP### 배치 {len(batches)}개 / 대상 {len(products)}건")
    # 기준 이미지가 정해진 건 vs 비전 판단으로 골라야 하는 건을 미리 알린다
    print(f"  대표옵션 확정 선기록 {len(fixed)}건 / 비전 판단 {len(vision)}건"
          f"(옵션정리 미완료·단일상품)")
    print(f"  배치: {os.path.join(run_dir, 'batches')}")
    if index:
        print(f"  다음(Workflow 모드): python {os.path.basename(__file__)} pending "
              f"--run-dir <R> → thumb-fanout 호출 → apply")
    print("  다음(수동 폴백): Claude 가 배치를 읽고 기준이미지·모드·(레시피면)프롬프트를 "
          "정해 results/result_NNN.json 생성 → apply")


def _pending_batches(run_dir):
    """results/result_NNN.json 이 없는 배치 = 아직 안 된 것. 디스크가 정본이다.

    index 가 dict(sentinel·전건 선기록)이면 남은 배치가 없다.
    """
    idx_path = os.path.join(run_dir, "batches_index.json")
    if not os.path.exists(idx_path):
        return []
    index = _load(idx_path)
    if isinstance(index, dict):
        return []
    out = []
    for b in index:
        if "n" not in b:
            # 구형 index(파일명·상품수만) 폴백 — 배치 파일에서 재계산한다.
            n = int(str(b.get("batch", "")).replace("batch_", "").replace(".json", "") or 0)
            path = os.path.abspath(os.path.join(run_dir, "batches", b.get("batch", "")))
            prods = _load(path).get("products", []) if os.path.exists(path) else []
            b = {"n": n, "path": path,
                 "imgs": sum((1 if p.get("대표이미지") else 0)
                             + len(p.get("후보이미지") or []) for p in prods),
                 "count": len(prods)}
        if not os.path.exists(os.path.join(
                run_dir, "results", f"result_{b['n']:03d}.json")):
            out.append(b)
    return out


def cmd_pending(args):
    """남은 배치를 JSON 한 줄로 찍는다 — Workflow(thumb-fanout) args 에 그대로 넣는다."""
    run_dir = os.path.abspath(args.run_dir)
    print(json.dumps({"runDir": run_dir, "promptPath": WORKER_PROMPT,
                      "batches": _pending_batches(run_dir)}, ensure_ascii=False))


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------

def _batch_products(run_dir):
    """batches/batch_NNN.json → {pid: product}. 배치가 pass-through 필드의 정본이다."""
    by_pid = {}
    for bf in sorted(glob.glob(os.path.join(run_dir, "batches", "batch_*.json"))):
        for p in _load(bf).get("products", []):
            if p.get("productId"):
                by_pid[p["productId"]] = p
    return by_pid


# 워커가 채워야 하는 판단 필드 — 이것만 results 에서 취한다. 나머지(기존썸네일·후보·
# 대표옵션명 등 pass-through)는 배치(정본)에서 조인한다. 워커 환각이 백업·복원 경로
# (`_generate` 의 before_generate.json)에 들어가는 것을 원천 차단한다.
_JUDGE_FIELDS = ("기준이미지", "기준이미지경로", "모드", "프롬프트", "상태")


def _results(run_dir):
    """results/*.json → 상품 리스트. 배치 정본과 조인하고, 마지막 파일이 이긴다.

    result_000(`선기록`)은 prep 이 직접 쓴 것이라 그대로 신뢰한다.
    배치에 없는 pid(워커 환각)는 버린다 — 크레딧·자동반영이 걸린 경로라 fail-closed.
    """
    batch_pids = _batch_products(run_dir)
    by_pid, order = {}, []
    for rf in sorted(glob.glob(os.path.join(run_dir, "results", "result_*.json"))):
        doc = _load(rf)
        trusted = bool(doc.get("선기록"))
        for p in doc.get("products", []):
            pid = p.get("productId")
            if not pid:
                continue
            if trusted:
                merged = p                     # prep 산출 — 전 필드 신뢰
            elif pid in batch_pids:
                merged = dict(batch_pids[pid])  # 배치가 정본, 판단 필드만 워커 것
                merged.update({k: p[k] for k in _JUDGE_FIELDS if k in p})
            elif batch_pids:
                continue                        # 환각 — _audit 가 경고로 집계
            else:
                merged = p                      # 구형 run-dir(배치 정본 없음) 폴백
            if pid not in by_pid:
                order.append(pid)
            by_pid[pid] = merged                # 마지막 파일 승리
    return [by_pid[pid] for pid in order]


def _audit(run_dir):
    """워커 산출물을 배치 대비 대조. 반환: (경고 리스트, 누락 여부)."""
    batch_pids = set(_batch_products(run_dir))
    if not batch_pids:
        return [], False                        # 구형 run-dir 또는 전건 선기록
    got = set()
    for rf in sorted(glob.glob(os.path.join(run_dir, "results", "result_*.json"))):
        doc = _load(rf)
        if doc.get("선기록"):
            continue
        got |= {p.get("productId") for p in doc.get("products", []) if p.get("productId")}
    missing = sorted(batch_pids - got)
    unknown = sorted(got - batch_pids)
    warns = []
    if missing:
        warns.append(f"누락 상품 {len(missing)}건: {missing[:5]}")
    if unknown:
        warns.append(f"미지의 상품id {len(unknown)}건(워커 환각 — 버린다): {unknown[:5]}")
    return warns, bool(missing)


def cmd_apply(args):
    run_dir = os.path.abspath(args.run_dir)
    sheet = _resolve_sheet(args)
    warns, has_missing = _audit(run_dir)
    for w in warns:
        print(f"  [감사] {w}")
    items = _results(run_dir)
    if not items:
        print(f"results 가 없다: {os.path.join(run_dir, 'results')}")
        return
    # 워커 보류(`상태: 보류(…)`)는 생성 대상이 아니다 — 크레딧 계산·--generate 에서 뺀다.
    # (2026-08-01 스모크 실측: 안 빼면 보류 2건이 예상 크레딧에 합산되고 생성까지 간다)
    held = [p for p in items if str(p.get("상태", "")).startswith("보류")]
    if held:
        print(f"\n  [보류 {len(held)}건 — 생성 대상에서 제외]")
        for p in held:
            print(f"    {p['productId']}: {p.get('상태')}")
        items = [p for p in items if not str(p.get("상태", "")).startswith("보류")]
    if not items:
        print("생성 대상이 없다(전부 보류).")
        return

    if args.commit:
        _commit(sheet, run_dir, args)
        return
    if args.generate:
        # 크레딧 게이트라 fail-closed — 누락이 있으면 무조건 차단. 부분 생성을 의도할 때만
        # --allow-missing(그 판단 자체가 이룸님 승인 사항이다).
        if has_missing and not getattr(args, "allow_missing", False):
            print("\n누락 상품이 있어 --generate 를 차단한다. "
                  "pending 재계산 → 재팬아웃으로 채우거나, 의도된 것이면 --allow-missing.",
                  file=sys.stderr)
            sys.exit(3)
        _generate(sheet, run_dir, items, args)
        return

    # 미리보기(게이트1 자료) — 쓰기 0.
    total_credits = R.credit_estimate(len(items))
    print(f"\n{'상품id':<28} {'모드':<8} {'기준이미지'}")
    print("-" * 70)
    for p in items:
        print(f"{p['productId']:<28} {p.get('모드', '기본'):<8} "
              f"{p.get('기준이미지경로', p.get('기준이미지', ''))[:40]}")
    print(f"\n대상 {len(items)}건 · 예상 크레딧 {total_credits:,} "
          f"(장당 {R.CREDITS_PER_IMAGE})")
    print("\n미리보기다. 실제 생성하려면 이룸님 승인 후 --generate 를 붙여라.")


def _generate(sheet, run_dir, items, args):
    """게이트1 승인 후 — 실제 생성 → 폴링 → 자동반영 방어 → review.html."""
    # 복구 파일은 생성 전에 미리 쓴다 — 이게 없으면 중간에 끊겼을 때 이미 대표로
    # 자동반영된 건들을 되돌릴 방법이 없다. items 는 배치 파일에서 오는 로컬 데이터라
    # 네트워크를 안 탄다(상세 스킬에서 검증된 패턴).
    backup = {p["productId"]: list(p.get("기존썸네일") or []) for p in items}
    _dump(os.path.join(run_dir, "before_generate.json"), backup)

    mcp = ThumbMCP()
    mcp.open()
    generated = {}
    gen_path = os.path.join(run_dir, "generated.json")
    try:
        try:
            for p in items:
                pid = p["productId"]
                before = list(p.get("기존썸네일") or [])
                prompt = p.get("프롬프트") or None   # 레시피 모드만 채운다. 기본 모드는 None(디폴트 사용).
                try:
                    task = mcp.generate(pid, prompt=prompt)
                    imgs, credits = mcp.poll(task["taskId"])
                    if not imgs:
                        raise RuntimeError("생성 완료인데 이미지가 비어있다")

                    # 자동반영 방어 — 생성 직후 재조회해 대표가 바뀌었으면 승인 전까지 복원한다
                    # (2026-07-28 파일럿 실측: 복원 없이 두면 미승인 이미지가 대표로 노출된다).
                    after = mcp.workdata(pid).get("썸네일") or []
                    if R.representative_changed(before, after) and before:
                        mcp.update_thumbnails(pid, before)
                        print(f"  [방어] {pid}: 자동반영 감지 → 원래 순서로 복원")

                    generated[pid] = {"상품명": p.get("상품명", ""), "생성본": imgs[0],
                                      "기존대표": before[0] if before else "",
                                      "후보": before[1:], "크레딧": credits,
                                      "재작업사유": p.get("재작업사유", ""), "판정": None,
                                      # 승인 화면에서 "생성본이 대표옵션과 같은 물건인가"를
                                      # 대조할 재료(2026-07-30). 없으면 판단 근거가 빠진다.
                                      "대표옵션명": p.get("대표옵션명", ""),
                                      "대표옵션이미지": p.get("대표옵션이미지", "")}
                    print(f"  [생성] {pid}: {imgs[0][:60]}... ({credits}크레딧)")
                except Exception as e:  # noqa: BLE001
                    generated[pid] = {"상품명": p.get("상품명", ""),
                                      "대표옵션명": p.get("대표옵션명", ""),
                                      "오류": f"{type(e).__name__}: {e}"[:200]}
                    print(f"  [실패] {pid}: {generated[pid]['오류']}", file=sys.stderr)
        finally:
            # Ctrl-C(KeyboardInterrupt)는 Exception 이 아니라 위 except 를 그냥 지나친다 —
            # 중단돼도 그 시점까지 생성된 결과가 파일로 남도록 여기서 무조건 기록한다.
            _dump(gen_path, generated)
    finally:
        mcp.close()

    review_path = review_html.build(generated, os.path.join(run_dir, "review.html"))
    ok = len([v for v in generated.values() if "생성본" in v])
    print(f"\n###GENERATE### 성공 {ok}건 / 실패 {len(generated) - ok}건")
    print(f"  검수 페이지: {review_path}")
    print("  다음: review.html 확인 → apply --commit(전부 승인) "
          "또는 일부만 거르려면 decisions.json 작성 후 --commit")


def _commit(sheet, run_dir, args):
    """게이트2 승인 후 — 최종 반영.

    `--commit` 을 부르는 행위 자체가 이미 review.html 을 보고 난 뒤의 승인이다
    (onestep 등 러너에서는 게이트 통과가 곧 이 호출이다). 그래서 `decisions.json`
    이 없으면 생성 성공분 전부를 **사용가능**으로 본다 — 매번 파일을 요구하면
    "review.html 보고 --commit 친 것" 자체가 승인인데 또 승인 파일을 만들라는
    중복 마찰이 된다. 일부만 거를 때만 `decisions.json` 으로 그 건만 재정의한다.
    """
    gen_path = os.path.join(run_dir, "generated.json")
    dec_path = os.path.join(run_dir, "decisions.json")
    if not os.path.exists(gen_path):
        print(f"generated.json 이 없다: {gen_path} — 먼저 apply --generate 를 돌려라.")
        return
    generated = _load(gen_path)
    decisions = _load(dec_path) if os.path.exists(dec_path) else {}
    if decisions:
        print(f"  decisions.json 반영: {len(decisions)}건 재정의")
    else:
        print("  decisions.json 없음 — 생성 성공분 전부 '사용가능'으로 반영")

    mcp = ThumbMCP()
    mcp.open()
    done, held = {}, {}
    sheet_rows = []
    try:
        for pid, g in generated.items():
            dec = decisions.get(pid) or {}
            verdict = dec.get("판정", "사용가능")
            reason = dec.get("사유", "")
            if "생성본" not in g:
                sheet_rows.append((pid, g.get("상품명", ""), "", g.get("오류", ""),
                                  "", "", 0, "보류(생성실패)"))
                continue
            if verdict != "사용가능":
                held[pid] = f"보류({verdict})"
                sheet_rows.append((pid, g.get("상품명", ""), g["생성본"],
                                  verdict, reason, 0, held[pid]))
                continue
            try:
                final = [g["생성본"]] + list(g.get("후보") or [])
                mcp.update_thumbnails(pid, final)
                time.sleep(args.sleep)
                after = (mcp.workdata(pid).get("썸네일") or [""])[0]
                if not after.startswith("https://"):
                    raise RuntimeError(f"재조회 결과가 https 가 아니다: {after[:80]}")
                snapshot.update(pid, 썸네일=[g["생성본"]] + list(g.get("후보") or []))
                done[pid] = "완료"
                sheet_rows.append((pid, g.get("상품명", ""), g["생성본"], verdict,
                                  reason, g.get("크레딧", 0), "완료"))
                print(f"  [완료] {pid}")
            except Exception as e:  # noqa: BLE001
                held[pid] = f"보류(저장실패)"
                sheet_rows.append((pid, g.get("상품명", ""), g.get("생성본", ""),
                                  verdict, f"{type(e).__name__}: {e}"[:150], 0, held[pid]))
                print(f"  [실패] {pid}: {e}", file=sys.stderr)
    finally:
        mcp.close()

    print(f"\n###COMMIT### 반영 {len(done)}건 / 보류·실패 {len(held)}건")
    if not args.no_sheet:
        _log_sheet(sheet, sheet_rows)
    if not args.no_matrix:
        vals = dict(done)
        vals.update(held)
        m = matrix.read(sheet)
        n = matrix.mark_many(sheet, TASK, vals, matrix=m)
        print(f"  현황판({matrix.TAB}) {TASK}: {n}칸 갱신")


def _log_sheet(sheet, rows):
    if ensure_tab(sheet, TAB, HEADER):
        print(f"  탭 신설: {TAB}")
    try:
        col_a = [str(r[0]).strip() if r else "" for r in sheets_get(sheet, f"'{TAB}'!A2:A")]
    except Exception:
        col_a = []
    at = {pid: i + 2 for i, pid in enumerate(col_a) if pid}
    last = _col_letter(len(HEADER))
    add = []
    for pid, name, gen, verdict, reason, credits, status in rows:
        vals = [pid, _today(), name, "기본", "", gen, verdict, reason, credits, status]
        r = at.get(pid)
        if r:
            sheets_update(sheet, f"'{TAB}'!A{r}:{last}{r}", [vals], value_input="USER_ENTERED")
        else:
            add.append(vals)
    if add:
        append_rows(sheet, TAB, add)
        print(f"  시트 기록: {len(add)}행 → '{TAB}'")


def cmd_restore(args):
    run_dir = os.path.abspath(args.run_dir)
    path = os.path.join(run_dir, "before_generate.json")
    if not os.path.exists(path):
        print(f"백업이 없다: {path}")
        return
    backup = _load(path)
    only = set(args.ids or ())
    mcp = ThumbMCP()
    mcp.open()
    ok, bad = 0, {}
    try:
        for pid, before in backup.items():
            if only and pid not in only:
                continue
            if not before:
                bad[pid] = "백업이 비어있다"
                continue
            try:
                mcp.update_thumbnails(pid, before)
                snapshot.update(pid, 썸네일=before)
                ok += 1
                print(f"  [복구] {pid}")
            except Exception as e:  # noqa: BLE001
                bad[pid] = f"{type(e).__name__}: {e}"[:200]
                print(f"  [실패] {pid}: {bad[pid]}", file=sys.stderr)
    finally:
        mcp.close()
    print(f"\n###RESTORE### 복구 {ok}건 / 실패 {len(bad)}건")


def main():
    ap = argparse.ArgumentParser(description="불사자 썸네일")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def _common(x):
        x.add_argument("--sheet", default="")
        x.add_argument("--group-name", default="")

    p = sub.add_parser("prep")
    _common(p)
    p.add_argument("--run-dir", required=True)
    p.add_argument("--ids", nargs="+", default=None)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    p.add_argument("--max-candidates", type=int, default=MAX_CANDIDATES)
    p.add_argument("--sleep", type=float, default=0.3)
    p.set_defaults(func=cmd_prep)

    q = sub.add_parser("pending", help="results 없는 배치를 Workflow args JSON 으로 출력")
    q.add_argument("--run-dir", required=True)
    q.set_defaults(func=cmd_pending)

    a = sub.add_parser("apply")
    _common(a)
    a.add_argument("--run-dir", required=True)
    a.add_argument("--generate", action="store_true", help="게이트1 승인 후 실제 생성(크레딧 소모)")
    a.add_argument("--commit", action="store_true", help="게이트2 승인 후 최종 반영")
    a.add_argument("--allow-missing", action="store_true",
                   help="감사 누락이 있어도 --generate 강행(의도된 부분 생성 전용)")
    a.add_argument("--no-sheet", action="store_true")
    a.add_argument("--no-matrix", action="store_true")
    a.add_argument("--sleep", type=float, default=0.5)
    a.set_defaults(func=cmd_apply)

    s = sub.add_parser("restore")
    _common(s)
    s.add_argument("--run-dir", required=True)
    s.add_argument("--ids", nargs="+", default=None)
    s.set_defaults(func=cmd_restore)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
