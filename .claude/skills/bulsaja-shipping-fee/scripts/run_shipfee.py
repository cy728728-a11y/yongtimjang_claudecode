#!/usr/bin/env python3
"""배송비 추천 오케스트레이터 — 스킬 계약(`prep`/`run`/`apply`).

  prep  : 현황판에서 대상 확정 → 스냅샷 → 이미지(대표·상세·옵션) → 배치 파일
  run   : **Claude 워커**가 배치를 읽고 무게·치수 추정 → results/result_*.json (스크립트 아님)
  apply : 요금 계산·게이트 → 시트 기록 → (--commit) 불사자 해외배송비 저장 → 현황판 갱신

판단(이게 몇 kg 인가)은 Claude 가, 계산(청구무게·요금·할증·경동비)은 `shipfee_rules.py` 가
한다. 규칙 전문은 `references/배송비-기준.md`.

사용:
  python run_shipfee.py prep    --group-name "1번_용쌤1-1" --run-dir <R> [--limit 5]
  python run_shipfee.py pending --run-dir <R>            # Workflow(shipfee-fanout) args 출력
  python run_shipfee.py apply   --run-dir <R>            # 미리보기 = 표본검수 입력
  python run_shipfee.py apply   --run-dir <R> --commit   # 실제 저장
  python run_shipfee.py restore --run-dir <R>            # 저장 전 배송비로 되돌림
"""
import argparse
import glob
import json
import os
import re
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

# `.claude` 앵커를 찾아 lib 를 sys.path 에 올린다.
_d = SCRIPT_DIR
while _d and _d != os.path.dirname(_d):
    _lib = os.path.join(_d, "lib")
    if os.path.isdir(os.path.join(_lib, "eroomlib")):
        if _lib not in sys.path:
            sys.path.insert(0, _lib)
        break
    _d = os.path.dirname(_d)

import shipfee_rules as R  # noqa: E402
from eroomlib import matrix, snapshot  # noqa: E402
from eroomlib.gsheets import (append_rows, chunk_by_size,  # noqa: E402
                              ensure_tab, sheets_batch_update,
                              sheets_get, sheets_update)
from eroomlib.matrix import _col_letter  # noqa: E402

TASK = "배송비"        # 현황판 열 이름 (matrix.TASKS 에 이미 있다)
TAB = "배송비"         # 상세 로그 탭
# `요율`·`포장비`·`파손위험` 은 **맨 뒤에 붙인다** — 이미 쌓인 행의 열이 밀리지 않게
# (`ensure_tab` 이 꼬리만 잇는다. 중간 삽입은 사람이 손으로 판단할 일이다 —
#  option-cleanup `옵션명변경` 과 같은 선례, 2026-08-13).
HEADER = ["상품id", "작업일", "상품명", "실물", "무게근거", "적용무게kg", "청구무게kg",
          "현재배송비", "제안배송비", "차액", "대표기준무게kg", "대표기준배송비",
          "할증안내", "세변합cm", "화물", "경동비", "신뢰도", "상태", "메모",
          "요율", "포장비", "파손위험"]

# 배치당 상품 수. 상품 1건에 이미지가 최대 5장(대표1+상세2+옵션2)이라 3건이면
# 워커 한 턴에 15장 — 팬아웃 예산(16장)과 맞는다.
BATCH_SIZE = 3

# 워커에게 주는 이미지 긴 변 px — 계약 §이미지 해상도(2026-08-07 실측). 치수 숫자
# (`45*39`·`19cm`)가 512 에서 원본과 동일하게 읽혔다. 이 축이 읽는 게 정확히 그 숫자다.
MAX_PX = 512

# 변경폭 게이트 — **기본 꺼짐**(2026-08-12 이룸님). 산식이 맞으면 큰 차액도 정답이다:
# 12kg 왜건은 5,600 → 23,200 이 맞는 값인데, 3,000원 상한을 걸면 그런 건이 전부 보류로
# 빠져 정작 고쳐야 할 상품이 안 고쳐진다. 신뢰도·무게없음 게이트가 오판 방어를 맡는다.
# `--max-delta N` 으로 필요할 때만 켠다.
MAX_DELTA = None

_ARG_BUDGET = 12000   # gws 명령줄 인자 상한 대비(gsheets.chunk_by_size 예산)

RULES_DOC = os.path.normpath(os.path.join(
    SCRIPT_DIR, "..", "references", "배송비-기준.md"))
WORKER_PROMPT = os.path.normpath(os.path.join(
    SCRIPT_DIR, "..", "references", "배송비-워커-프롬프트.md"))


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


class FeeMCP(snapshot.ProductMCP):
    """transport + workdata 는 상속하고, 이 스킬 고유 도구만 얹는다."""

    def set_oversea_fee(self, product_id, new_fee):
        """bulsaja_price_update(overseaFee) — **미리보기 → 확인키로 커밋** 2단계.

        1번만 부르면 `confirmationToken` 만 오고 **아무것도 저장되지 않는다**
        (옵션정리 파일럿에서 이걸 놓쳐 5건이 '저장한 줄 알았는데 무변경'이었다).
        반환: 커밋 응답. 실패면 예외.
        """
        payload = {"mode": "overseaFee", "productId": product_id,
                   "newFee": int(new_fee)}
        pv = self.call_tool("bulsaja_price_update", payload)
        token = pv.get("confirmationToken")
        if not token:
            if pv.get("success"):
                return pv   # 변경 없음 등 확인이 필요 없는 응답
            why = pv.get("message") or pv.get("_text") or pv
            raise RuntimeError(f"확인키 미발급: {str(why)[:200]}")
        r = self.call_tool("bulsaja_price_update",
                           {**payload, "confirm": True, "confirmationToken": token})
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


_IMG_SRC = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.I)


def detail_image_urls(html, want=2):
    """상세 HTML → 이미지 URL 을 균등 간격으로 `want` 장 고른다.

    앞에서 자르면 대표 이미지 반복분만 잡히고, 뒤에서 자르면 배너·안내만 잡히는 경우가
    있다. 치수표·스펙표가 어디 있는지는 판매자마다 달라서, **한쪽 끝을 고르는 대신
    전체에서 고르게 뽑는다**(중간 지점 우선).
    """
    if not html or want <= 0:
        return []
    urls = []
    for u in _IMG_SRC.findall(html):
        u = u.strip()
        if u.startswith("http") and u not in urls:
            urls.append(u)
    if len(urls) <= want:
        return urls
    # 균등 표본 — want=2 면 1/2·3/4 지점(앞머리 반복분을 피한다)
    idx = sorted({int(len(urls) * (i + 1) / (want + 1)) for i in range(want)})
    picked = [urls[min(i, len(urls) - 1)] for i in idx]
    return list(dict.fromkeys(picked))[:want]


def cmd_prep(args):
    run_dir = os.path.abspath(args.run_dir)
    os.makedirs(run_dir, exist_ok=True)
    sheet = _resolve_sheet(args)
    print(f"  시트: {sheet}")

    # 1) 대상 확정 — 현황판 쿼리 1줄(계약 §대상 선정). --ids 면 그것만.
    m = matrix.read(sheet)
    if args.ids:
        pids = [i for i in args.ids if i.strip()]
        missing = [i for i in pids if i not in m]
        if missing:
            print(f"  [경고] 현황판에 없는 상품 {len(missing)}건: {missing[:3]}")
    else:
        pids = matrix.pending(m, TASK)
        print(f"[1/4] 현황판 '{TASK}' 미착수 {len(pids)}건")
    redo = matrix.redo_pending(m, TASK)
    if args.limit:
        pids = pids[:args.limit]
        print(f"  --limit {args.limit} 적용 → {len(pids)}건")
    if not pids:
        print("처리할 상품이 없다.")
        return

    # 2) 스냅샷 — `해외배송비` 가 없는 옛 캐시는 자동 재조회된다(ensure(require=))
    print(f"[2/4] 스냅샷 확보 {len(pids)}건")
    recs, errors = snapshot.ensure(pids, sleep=args.sleep,
                                   require=("해외배송비", "옵션", "상세"))
    if errors:
        # 조용히 버리지 않는다 — 현황판에 남겨야 다음 run 이 집어간다(옵션정리 선례).
        print(f"  조회 실패 {len(errors)}건 — 현황판에 '보류(조회실패)' 로 남긴다")
        _dump(os.path.join(run_dir, "fetch_errors.json"),
              {pid: str(e)[:300] for pid, e in errors.items()})
        try:
            matrix.mark_many(sheet, TASK,
                             {pid: "보류(조회실패)" for pid in errors}, matrix=m)
        except Exception as e:  # noqa: BLE001
            print(f"  [경고] 조회실패 현황판 기재 실패: {str(e)[:120]}", file=sys.stderr)

    # 3) 이미지 — 대표썸네일 1 + 상세 2 + 옵션값 2. 무게 근거의 우선순위와 같은 순서다
    #    (규칙문서 §2: 텍스트 → 상세 → 대표 → 옵션).
    thumbs_dir = os.path.join(run_dir, "thumbs")
    img = {}
    if not args.skip_thumbs:
        n = 0
        for pid, rec in recs.items():
            paths = {"상세": []}
            rep = (rec.get("썸네일") or [""])[0]
            if rep:
                p, _ = snapshot.materialize_image(rep, thumbs_dir, pid + "_rep", 0,
                                                  max_px=args.max_px)
                if p:
                    paths["대표"] = p
            html = ((rec.get("상세") or {}).get("HTML")) or ""
            for i, u in enumerate(detail_image_urls(html, args.max_detail_images)):
                p, _ = snapshot.materialize_image(u, thumbs_dir, pid + "_det", i,
                                                  max_px=args.max_px)
                if p:
                    paths["상세"].append(p)
            # 옵션값 이미지는 옵션마다 크기가 다른 상품에서만 쓸모가 있다 → 소수만.
            got = 0
            for gi, d in enumerate(rec.get("옵션", {}).get("차원") or []):
                for v in (d.get("values") or []):
                    if got >= args.max_option_images:
                        break
                    if not v.get("imageUrl"):
                        continue
                    p, _ = snapshot.materialize_image(
                        v["imageUrl"], thumbs_dir, f"{pid}_{gi}", got, max_px=args.max_px)
                    if p:
                        paths[f"{gi}:{v.get('vid')}"] = p
                        got += 1
            img[pid] = paths
            n += (1 if paths.get("대표") else 0) + len(paths["상세"]) + got
        print(f"[3/4] 이미지 {n}장 확보(캐시 적중분은 복사만)")
    _dump(os.path.join(run_dir, "images.json"), img)

    # 4) 배치 — 워커가 파일 하나로 완주할 수 있게 자기완결형으로 담는다
    products, dropped = [], []
    for pid in pids:
        rec = recs.get(pid)
        if not rec:
            dropped.append(pid)
            continue
        o = rec.get("옵션") or {}
        paths = img.get(pid, {})
        products.append({
            "productId": pid,
            "상품명": rec.get("상품명", ""),
            "원문명": rec.get("원문명", ""),
            "카테고리": rec.get("기존카테고리", ""),
            "현재배송비": rec.get("해외배송비", 0),
            "재작업사유": redo.get(pid, ""),
            "대표썸네일": paths.get("대표", ""),
            "상세이미지": paths.get("상세", []),
            # 옵션값 이미지는 **상품 단위 목록**으로 준다. 판매행에 1:1 로 붙이지 않는다 —
            # 복합옵션은 판매행 id 가 `1:1:1:4` 같은 조합 키라 vid 와 대응이 안 되고,
            # 1차원이어도 부분 문자열 매칭은 `1` 이 `1949…` 에 걸리는 오매칭을 낳는다.
            # 이 축이 이미지에서 얻는 건 "옵션마다 크기가 다른가"뿐이라 목록이면 충분하다.
            "옵션이미지": [v for k, v in paths.items() if ":" in k],
            "판매행": [{
                "id": r["id"], "표시명": r.get("text"), "원문": r.get("_text"),
                "판매가": r.get("sale_price"), "재고": r.get("stock"),
                "현재제외": r.get("exclude"), "현재대표": r.get("main_product"),
            } for r in (o.get("판매행") or [])],
        })

    batches = [products[i:i + args.batch_size]
               for i in range(0, len(products), args.batch_size)]
    index = []
    for i, b in enumerate(batches, 1):
        path = os.path.abspath(os.path.join(run_dir, "batches", f"batch_{i:03d}.json"))
        _dump(path, {"배치": i, "규칙문서": RULES_DOC, "products": b})
        index.append({"n": i, "path": path, "imgs": _batch_imgs(b), "count": len(b)})
    _dump(os.path.join(run_dir, "batches_index.json"), index)

    print(f"\n###PREP### 배치 {len(batches)}개 / 상품 {len(products)}건 / "
          f"이미지 {sum(x['imgs'] for x in index)}장")
    # 대상 대조 — 대상과 배치가 어긋나면 반드시 눈에 띄게 찍는다(침묵 누락 재발 방지).
    print(f"  §대상 대조: 대상 {len(pids)}건 = 배치 {len(products)}건 "
          f"+ 조회실패 {len(errors)}건"
          + (f" + 기타누락 {len(dropped) - len(errors)}건"
             if len(dropped) > len(errors) else ""))
    if len(products) + len(dropped) != len(pids):
        print("  [경고] 대상 수가 맞지 않는다 — 확인 필요", file=sys.stderr)
    print(f"  배치: {os.path.join(run_dir, 'batches')}")
    print(f"  다음(Workflow 모드): python {os.path.basename(__file__)} pending "
          f"--run-dir <R> → shipfee-fanout 호출 → apply")


def _batch_imgs(products):
    """배치에 실린 이미지 파일 수 — 대표 + 상세 + 옵션값(경로가 찬 것만)."""
    n = 0
    for p in products:
        if p.get("대표썸네일"):
            n += 1
        n += len(p.get("상세이미지") or [])
        n += len(p.get("옵션이미지") or [])
    return n


def _pending_batches(run_dir):
    """results/result_NNN.json 이 없는 배치 = 아직 안 된 것. 디스크가 정본이다."""
    idx_path = os.path.join(run_dir, "batches_index.json")
    if not os.path.exists(idx_path):
        return []
    out = []
    for b in _load(idx_path):
        if not os.path.exists(os.path.join(
                run_dir, "results", f"result_{b['n']:03d}.json")):
            out.append(b)
    return out


def cmd_pending(args):
    """남은 배치를 JSON 한 줄로 — Workflow(shipfee-fanout) args 에 그대로 넣는다."""
    run_dir = os.path.abspath(args.run_dir)
    print(json.dumps({"runDir": run_dir, "promptPath": WORKER_PROMPT,
                      "batches": _pending_batches(run_dir)}, ensure_ascii=False))


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------

def _expected_by_batch(run_dir):
    """batches/batch_NNN.json → {배치번호: [productId, ...]}."""
    exp = {}
    for bf in sorted(glob.glob(os.path.join(run_dir, "batches", "batch_*.json"))):
        doc = _load(bf)
        n = doc.get("배치") or int(os.path.basename(bf)[6:9])
        exp[n] = [p.get("productId") for p in doc.get("products", []) if p.get("productId")]
    return exp


def _batch_products(run_dir):
    """batches/batch_NNN.json → {productId: 배치상품}. 현재배송비·대표행이 여기 있다."""
    out = {}
    for bf in sorted(glob.glob(os.path.join(run_dir, "batches", "batch_*.json"))):
        for p in _load(bf).get("products", []):
            if p.get("productId"):
                out[p["productId"]] = p
    return out


def _results(run_dir):
    """results/result_NNN.json → {productId: 워커결과}. 같은 pid 는 마지막 파일 채택."""
    out = {}
    for rf in sorted(glob.glob(os.path.join(run_dir, "results", "result_*.json"))):
        try:
            doc = _load(rf)
        except (OSError, json.JSONDecodeError) as e:
            print(f"  [경고] 결과 파일 파손: {os.path.basename(rf)} ({e})", file=sys.stderr)
            continue
        for p in doc.get("products", []):
            if p.get("productId"):
                out[p["productId"]] = p
    return out


def _main_sku(bp):
    """배치 상품의 대표 판매행 id. 없으면 None(그러면 최소 무게군이 대표 기준이 된다)."""
    for r in (bp.get("판매행") or []):
        if r.get("현재대표"):
            return str(r.get("id"))
    return None


def _row_values(p, name):
    def num(v):
        return "" if v is None else v
    return [p["productId"], _today(), name, p["실물"], p["무게근거"],
            num(p["적용무게"]), num(p["청구무게"]),
            num(p["현재배송비"]), num(p["제안배송비"]), num(p["차액"]),
            num(p["대표무게"]), num(p["대표배송비"]),
            # 할증은 **포장비 예상에 이미 섞여 있다**(실측 `한진택배 할증료`).
            # 금액을 또 더하지 않고 "이 무게면 할증 구간이 여기다"만 적는다.
            (f"{p['할증']}원 구간 (포장비에 포함)" if p["할증"] else p["할증근거"]),
            num(p["세변합"]), p["화물"],
            ("확인필요 — " + p["경동근거"] if p["화물"] and p["경동비"] is None
             else (num(p["경동비"]) if p["화물"] else "")),
            p["신뢰도"], p["상태"], p["메모"],
            num(p["요율"]), num(p["포장비"]), p["파손위험"]]


def _row_runs(pairs):
    """[(행번호, 값)] 정렬본 → 연속 구간 [(시작행, [값...])]. 건건 update 는 쿼터에 즉사한다."""
    runs = []
    for r, vals in pairs:
        if runs and r == runs[-1][0] + len(runs[-1][1]):
            runs[-1][1].append(vals)
        else:
            runs.append((r, [vals]))
    return runs


def _log_sheet(sheet, rows):
    """`배송비` 탭 기록. **이미 있는 상품id 는 그 행을 갱신한다** — 되돌려 다시 돌렸을 때
    옛 계획이 남아 있으면 검수 자료가 거짓이 된다."""
    if ensure_tab(sheet, TAB, HEADER):
        print(f"  탭 신설: {TAB}")
    try:
        col_a = [str(r[0]).strip() if r else "" for r in sheets_get(sheet, f"'{TAB}'!A2:A")]
    except Exception:
        col_a = []
    at = {pid: i + 2 for i, pid in enumerate(col_a) if pid}
    last = _col_letter(len(HEADER))

    add, upd = [], []
    for p, name in rows:
        vals = _row_values(p, name)
        r = at.get(p["productId"])
        (upd.append((r, vals)) if r else add.append(vals))

    ranges = [(f"'{TAB}'!A{start}:{last}{start + len(block) - 1}", block)
              for start, block in _row_runs(sorted(upd, key=lambda x: x[0]))]
    for _, part in chunk_by_size(ranges, budget=_ARG_BUDGET):
        sheets_batch_update(sheet, part, value_input="USER_ENTERED")
    if upd:
        print(f"  시트 갱신: {len(upd)}행 / 구간 {len(ranges)}개 → '{TAB}'")
    if add:
        for _, part in chunk_by_size(add, budget=_ARG_BUDGET):
            append_rows(sheet, TAB, part)
        print(f"  시트 기록: {len(add)}행 → '{TAB}'")


def _review(plans, bps):
    """검수표 — 표본검수의 입력이다. 금액이 판매가를 움직이므로 차액 큰 순으로 세운다."""
    print("\n=== 검수표 (차액 큰 순) ===")
    print(f"{'상품id':22} {'현재':>7} {'제안':>7} {'차액':>7} "
          f"{'= 요율':>7} {'+ 포장':>7} {'무게':>6} {'파손':4} {'신뢰':4} 상태")
    for p in sorted(plans, key=lambda x: -abs(x["차액"] or 0)):
        name = (bps.get(p["productId"], {}).get("상품명") or "")[:18]
        print(f"{p['productId'][:22]:22} {p['현재배송비']:>7,} "
              f"{(p['제안배송비'] or 0):>7,} {(p['차액'] or 0):>+7,} "
              f"{(p['요율'] or 0):>7,} {(p['포장비'] or 0):>7,} "
              f"{(p['적용무게'] or 0):>5}kg {p['파손위험'][:2]:4} {p['신뢰도'][:2]:4} {p['상태']}")
        print(f"    {name} | {p['실물'][:34]} | {p['무게근거'][:70]}")
        if p["화물"]:
            print(f"    ⚠ 화물 {p['화물']} · 경동비 "
                  f"{p['경동비'] if p['경동비'] is not None else '확인필요'} ({p['경동근거']})")


def cmd_apply(args):
    run_dir = os.path.abspath(args.run_dir)
    # `--no-sheet` 면 그룹 시트가 필요 없다 — 여기서 특정하려 들면 시트 없이 계산만
    # 확인하려는 실행(테스트·재계산)이 인자 부족으로 죽는다.
    sheet = None if args.no_sheet else _resolve_sheet(args)
    bps = _batch_products(run_dir)
    res = _results(run_dir)
    exp = _expected_by_batch(run_dir)

    # 감사 — 배치 대비 누락·환각. 누락이 있으면 --commit 을 막는다(옵션정리 선례).
    want = {pid for ids in exp.values() for pid in ids}
    missing = sorted(want - set(res))
    ghost = sorted(set(res) - want)
    print(f"[감사] 배치 {len(want)}건 / 결과 {len(res)}건 / "
          f"누락 {len(missing)}건 / 배치에 없는 결과 {len(ghost)}건")
    if ghost:
        print(f"  [경고] 배치에 없는 상품이 결과에 있다(환각 의심): {ghost[:5]}",
              file=sys.stderr)
    if missing and args.commit and not args.allow_missing:
        print(f"  누락 {len(missing)}건 — --commit 차단. pending 재계산 후 재팬아웃하거나 "
              f"의도된 부분 처리면 --allow-missing", file=sys.stderr)
        return 2

    table = R.load_rate_table()
    if table is None:
        print("  (경동 표준운임표 미보유 — 화물 대상은 금액 없이 '확인필요'로만 남긴다)")

    plans = []
    for pid, entry in res.items():
        bp = bps.get(pid, {})
        entry = dict(entry, productId=pid)
        plans.append(R.plan_product(
            entry,
            current_fee=bp.get("현재배송비", 0),
            main_sku_id=_main_sku(bp),
            max_delta=args.max_delta,
            region_rate=args.region_rate,
            table=table))

    by_state = {}
    for p in plans:
        by_state.setdefault(p["상태"], []).append(p)
    print("  상태: " + " · ".join(f"{k} {len(v)}건" for k, v in sorted(by_state.items())))

    _review(plans, bps)

    # 시트는 **저장 전에** 남긴다 — 계약 §시트 기록 의무(자동 반영도 원장부터).
    if not args.no_sheet:
        _log_sheet(sheet, [(p, bps.get(p["productId"], {}).get("상품명", "")) for p in plans])

    _dump(os.path.join(run_dir, "plans.json"), plans)

    if not args.commit:
        n = sum(1 for p in plans if R.savable(p))
        print(f"\n[미리보기] 저장 대상 {n}건 (변경없음 {len(by_state.get(R.S_SAME, []))}건 · "
              f"보류 {len(plans) - n - len(by_state.get(R.S_SAME, []))}건)")
        print(f"  표본검수 통과 후: {os.path.basename(__file__)} apply --run-dir <R> --commit")
        return 0

    # ---- 저장 --------------------------------------------------------------
    todo = [p for p in plans if R.savable(p)]
    if not todo:
        print("\n저장할 것이 없다.")
    else:
        # 저장 직전 백업 — 스냅샷은 성공 시 새 값으로 덮이므로 **이게 유일한 원본**이다.
        _dump(os.path.join(run_dir, "before_commit.json"),
              {p["productId"]: p["현재배송비"] for p in todo})
        mcp = FeeMCP()
        mcp.open()
        ok, fail = [], {}
        try:
            for i, p in enumerate(todo, 1):
                try:
                    mcp.set_oversea_fee(p["productId"], p["제안배송비"])
                    snapshot.update(p["productId"], 해외배송비=p["제안배송비"])
                    ok.append(p["productId"])
                except Exception as e:  # noqa: BLE001
                    fail[p["productId"]] = f"{type(e).__name__}: {e}"[:200]
                if i % 20 == 0:
                    print(f"  ...{i}/{len(todo)}")
                time.sleep(args.sleep)
        finally:
            mcp.close()
        print(f"\n반영 {len(ok)}건 / 실패 {len(fail)}건")
        if fail:
            _dump(os.path.join(run_dir, "commit_errors.json"), fail)
            for pid, why in list(fail.items())[:5]:
                print(f"    {pid}: {why[:90]}")

    # 현황판 — 자기 열 1개만, 열 통짜 1회(계약 §대상 선정)
    vals = {}
    for p in plans:
        pid = p["productId"]
        if p["상태"] in (R.S_OK, R.S_SAME):
            vals[pid] = "완료"
        else:
            vals[pid] = p["상태"]
    if todo:
        for pid, why in (fail or {}).items():
            vals[pid] = "보류(저장실패)"
    if not args.no_sheet and vals:
        m = matrix.read(sheet)
        n = matrix.mark_many(sheet, TASK, vals, matrix=m)
        print(f"  현황판({matrix.TAB}) {TASK}: {n}칸 갱신")
    return 0


def cmd_restore(args):
    """before_commit.json 의 배송비로 되돌린다. 옵션 판매가도 같이 되돌아간다."""
    run_dir = os.path.abspath(args.run_dir)
    path = os.path.join(run_dir, "before_commit.json")
    if not os.path.exists(path):
        print("before_commit.json 이 없다 — 되돌릴 대상이 없다.", file=sys.stderr)
        return 2
    before = _load(path)
    if args.ids:
        before = {k: v for k, v in before.items() if k in set(args.ids)}
    mcp = FeeMCP()
    mcp.open()
    ok, fail = 0, {}
    try:
        for pid, fee in before.items():
            try:
                mcp.set_oversea_fee(pid, int(fee))
                snapshot.update(pid, 해외배송비=int(fee))
                ok += 1
            except Exception as e:  # noqa: BLE001
                fail[pid] = f"{type(e).__name__}: {e}"[:200]
            time.sleep(args.sleep)
    finally:
        mcp.close()
    print(f"복원 {ok}건 / 실패 {len(fail)}건")
    for pid, why in list(fail.items())[:5]:
        print(f"    {pid}: {why[:90]}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="배송비 추천 — prep / pending / apply / restore")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prep", help="대상 확정 → 스냅샷 → 이미지 → 배치")
    p.add_argument("--group-name")
    p.add_argument("--sheet")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--ids", nargs="*", default=[])
    p.add_argument("--limit", type=int)
    p.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    p.add_argument("--max-px", type=int, default=MAX_PX, help="0 이면 원본")
    p.add_argument("--max-detail-images", type=int, default=2)
    p.add_argument("--max-option-images", type=int, default=2)
    p.add_argument("--skip-thumbs", action="store_true")
    p.add_argument("--sleep", type=float, default=0.3)
    p.set_defaults(func=cmd_prep)

    q = sub.add_parser("pending", help="results 없는 배치를 Workflow args JSON 으로 출력")
    q.add_argument("--run-dir", required=True)
    q.set_defaults(func=cmd_pending)

    a = sub.add_parser("apply", help="계산·게이트 → 시트 → (--commit) 저장")
    a.add_argument("--run-dir", required=True)
    a.add_argument("--group-name")
    a.add_argument("--sheet")
    a.add_argument("--commit", action="store_true")
    a.add_argument("--allow-missing", action="store_true",
                   help="누락 배치가 있어도 --commit 진행(의도된 부분 처리 전용)")
    a.add_argument("--max-delta", type=int, default=MAX_DELTA,
                   help="|제안-현재| 상한(원). 주면 초과분을 저장하지 않는다. "
                        "기본은 상한 없음 — 산식이 맞으면 큰 차액도 정답이다")
    a.add_argument("--region-rate", type=float, default=R.DEFAULT_REGION_RATE,
                   help="경동비 지역 인상율(0.25 = 25%%)")
    a.add_argument("--no-sheet", action="store_true")
    a.add_argument("--sleep", type=float, default=0.3)
    a.set_defaults(func=cmd_apply)

    s = sub.add_parser("restore", help="저장 전 배송비로 되돌린다(before_commit.json 필요)")
    s.add_argument("--run-dir", required=True)
    s.add_argument("--ids", nargs="*", default=[])
    s.add_argument("--sleep", type=float, default=0.3)
    s.set_defaults(func=cmd_restore)

    args = ap.parse_args()
    sys.exit(args.func(args) or 0)


if __name__ == "__main__":
    main()
