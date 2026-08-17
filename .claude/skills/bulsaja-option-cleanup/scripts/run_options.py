#!/usr/bin/env python3
"""옵션 정리 오케스트레이터 — 스킬 계약(`prep`/`run`/`apply`)의 첫 사용자.

  prep  : 현황판에서 대상 확정 → 스냅샷(옵션 포함) → 옵션 이미지 → 배치 파일
  run   : **Claude 워커**가 배치를 읽고 판단 → results/result_*.json (스크립트 아님)
  apply : 계산·검증 → 시트 기록 → (승인 후) 저장 → 재조회 검증 → 스냅샷·현황판 갱신

판단(무엇이 메인상품인가·이 옵션이 비상품인가·이름을 뭐라 지을까)은 Claude 가,
계산(대표·1.5배 상한·순서·검증)은 `option_rules.py` 가 한다. 규칙 전문은 SKILL.md.

사용:
  python run_options.py prep    --group-name "1번_용쌤1-1" --run-dir <R> --limit 5
  python run_options.py pending --run-dir <R>          # Workflow(optclean-fanout) args 출력
  python run_options.py apply   --run-dir <R>          # 미리보기(승인 게이트)
  python run_options.py apply   --run-dir <R> --commit # 실제 저장
"""
import argparse
import glob
import hashlib
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

import option_rules as R  # noqa: E402
from eroomlib import matrix, snapshot  # noqa: E402
from eroomlib.config import cfg  # noqa: E402
from eroomlib.gsheets import (append_rows, chunk_by_size,  # noqa: E402
                              sheets_batch_update,
                              ensure_tab,
                              sheets_get, sheets_update)
from eroomlib.matrix import _col_letter  # noqa: E402

TASK = "옵션"          # 현황판 열 이름
TAB = "옵션"           # 상세 로그 탭
# `옵션명변경` 은 뒤에 붙인다 — 기존 탭에 이미 쌓인 행의 열이 밀리지 않게(ensure_tab 이 꼬리만 잇는다).
HEADER = ["상품id", "작업일", "상품명", "메인상품", "옵션수", "유지", "제외",
          "대표옵션", "기준가", "상한", "순서", "상태", "메모", "옵션명변경"]

# 옵션 축(선택 항목) 이름 원장 — 규칙 18(2026-08-04 이룸님).
#
# **2026-08-17부터 저장한다.** MCP 에 `renameGroups`(`[{groupIndex, name}]`)가 생겼다.
# 그전까지 이 탭은 '앱에서 수동 반영할 목록'이었고, 이제는 **무엇을 왜 바꿨나의 원장**이다.
#   `반영`      — 이번 회차가 MCP 로 저장했다
#   `대기`      — 기계 신호만 있고 워커 제안이 없다. 대체 이름은 사람만 지을 수 있다
#   `보류(사유)` — 제안이 있었지만 안 보냈거나 저장이 거부됐다
# `상태` 를 이룸님이 `반영`·`무시` 로 바꾼 행은 재실행이 **덮지 않는다**.
AXIS_TAB = "옵션축"
AXIS_HEADER = ["상품id", "기록일", "상품명", "차원", "원문축명", "현재축명",
               "제안축명", "사유", "값예시", "신호", "상태"]
AXIS_PENDING = "대기"
AXIS_APPLIED = "반영"
# 제안이 없어 **지금 이름을 그대로 둔** 축. `무시` 와 같은 뜻(= 다시 안 잡는다)이지만
# 사람이 판단한 `무시` 와 구분해 적는다 — 원장을 읽을 때 누가 정했는지가 보여야 한다.
AXIS_KEEP = "무시(제안 없음 — 현재 이름 유지)"

# **부분저장** — 이름 규칙만 어긴 상태는 ②(판매·대표·순서)를 저장한다 (2026-08-06 이룸님).
#
# 저장이 상품 단위로 전부-아니면-전무였다. 그래서 표기 규칙 하나(`기본형` 마커)가
# **무엇을 파느냐**까지 같이 막았다 — 3-1 워터건은 워커가 뒤집힘(본품 19행 제외·부속
# 예비배터리 1행만 판매·대표)을 정확히 복구해 놨는데 마커가 없다는 이유로 통째로
# 미저장돼, 스마트스토어에 배터리만 팔리는 채로 남아 있었다(69건 중 12건이 이렇게 빠졌다).
# 마커는 ①(이름)에 붙는 표시라 ②와 무관하다 → ①만 건너뛰고 ②는 저장한다.
#
# 대신 **완료로 끝내지 않는다**: 현황판 `옵션` 열에 `재작업(...)` 으로 남겨
# `pending(..., include_redo=True)` 이 다음 회차에 자동으로 다시 집어가게 한다.
# 빈칸으로 두면 사유가 사라지고, `보류(...)` 로 두면 영영 안 잡힌다.
PARTIAL_SAVE = ("보류(기본형)",)
PARTIAL_REASON = "기본형 마커 누락/오부착 — 판매·대표·순서만 저장, 옵션명은 미저장"

# 배치당 상품 수. 상품 1건에 옵션이 4~28개라 5건이면 워커 한 턴에 들어간다
# (카테고리교정 10건/배치보다 작다 — 옵션은 건당 정보량이 훨씬 크다).
BATCH_SIZE = 5

# 워커에게 주는 이미지의 긴 변 px. 2026-08-07 실측(표본 9건·17장, 512/768/원본 블라인드
# 판독): 512 판독 85건 · 768 84건 · 원본 93건 — 512 가 원본의 91% 를 유지하면서 비전
# 토큰을 3.3배 줄인다. 옵션 축이 읽어야 하는 치수 숫자(`45*39`·`19cm`)는 512 에서 원본과
# 동일하게 읽혔다. 768 은 512 보다 나은 게 없어 중간값을 두지 않는다.
MAX_PX = 512

# 팬아웃용 고정 경로 — 규칙 정본과 워커 지시서(run_all.py 의 RULES_DOC 패턴).
RULES_DOC = os.path.normpath(os.path.join(
    SCRIPT_DIR, "..", "references", "옵션명-규칙.md"))
WORKER_PROMPT = os.path.normpath(os.path.join(
    SCRIPT_DIR, "..", "references", "옵션-워커-프롬프트.md"))


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


def _promote_main(mcp, pid, plan, sleep=0.0):
    """제외 청크를 보내기 **전에** 새 대표를 판매중·대표로 먼저 세운다 (2026-08-15).

    `excludeSkuIds` 는 200개 상한이라 제외가 많은 상품은 앞 덩어리를 따로 보내는데,
    그 덩어리에 **현재 대표행**이 섞여 있으면 서버가 "대표 옵션을 판매 제외하거나 대표
    상태가 올바르지 않습니다"로 저장을 통째로 거부한다 — 그 호출에는 대표를 실을 수
    없기 때문이다(순서를 함께 실으면 아직 안 뺀 행 때문에 또 거부당한다).
    25-2 신규 958건 실측: 저장 실패 10건 중 **9건이 전부 제외 200 초과 상품**이었고,
    팬아웃을 다시 돌려도 같은 자리에서 같은 이유로 또 실패했다.

    대표를 먼저 옮겨 두면 그 뒤로 옛 대표가 어느 덩어리에 들어가든 상관없다.
    `includeSkuIds` 로 새 대표를 함께 판매중으로 올린다 — 이미 제외돼 있어도 통과한다.
    이름·순서는 싣지 않는다(이름+순서 금지 조합 · 미완 제외 상태에서의 순서 거부 회피).
    """
    mcp.option_update(pid, includeSkuIds=[plan["대표"]], mainSkuId=plan["대표"])
    if sleep:
        time.sleep(sleep)


class OptionMCP(snapshot.ProductMCP):
    """transport + workdata 는 상속하고, 이 스킬 고유 도구만 얹는다."""

    def option_update(self, product_id, **kw):
        """bulsaja_option_update — **미리보기 → 확인키로 커밋** 2단계(카테고리 저장과 같다).

        1번만 부르면 `success:false` + `confirmationToken` 만 오고 **아무것도 저장되지 않는다**
        (2026-07-28: 이걸 놓쳐 파일럿 5건이 전부 '저장한 줄 알았는데 무변경'이었다.
         재조회 검증이 막아줘서 손상은 0이었다).

        **renameValues 와 정렬은 같은 호출에 넣지 않는다** — 쿠팡 기존 옵션 연결 보호.
        반환: 커밋 응답. 실패면 예외.
        """
        if kw.get("renameValues") and (kw.get("sortOrder") or kw.get("skuOrder")):
            raise ValueError("이름 변경과 순서 변경은 같은 호출에 넣을 수 없다")
        # 축 이름(`renameGroups`)은 순서와 같은 호출에 넣어도 되지만 **넣지 않는다**.
        # 축 이름이 하나라도 거부되면 그 호출이 통째로 실패해서, 표기 문제 하나가
        # **무엇을 파느냐**(포함/제외·대표)까지 같이 막는다 — 3-1 워터건에서 `기본형`
        # 마커가 그랬던 것과 똑같은 구조다(→ SKILL.md §부분저장). 그래서 축은 항상 단독이다.
        if kw.get("renameGroups") and len(
                [k for k, v in kw.items() if v not in (None, [], "")]) > 1:
            raise ValueError("축 이름 변경은 단독 호출로만 보낸다")
        payload = {"productId": product_id}
        payload.update({k: v for k, v in kw.items() if v not in (None, [], "")})

        pv = self.call_tool("bulsaja_option_update", payload)
        token = pv.get("confirmationToken")
        if not token:
            if pv.get("success"):
                return pv  # 확인이 필요 없는 응답(변경 없음 등)
            # MCP 스키마 위반(예: 배열 200개 상한)은 `message` 가 아니라 `_text` 로 온다.
            # 그걸 안 보면 '확인키 미발급: None' 이 되어 원인이 안 보인다(용쌤1-2 4건).
            why = pv.get("message") or pv.get("_text") or pv
            raise RuntimeError(f"확인키 미발급: {str(why)[:200]}")
        r = self.call_tool("bulsaja_option_update",
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
    # 이관 사유 — 배치에 실어 워커에게 넘긴다(§2-10 이미지 판정 조항이 이걸 본다).
    redo = matrix.redo_pending(m, TASK)
    if args.limit:
        pids = pids[:args.limit]
        print(f"  --limit {args.limit} 적용 → {len(pids)}건")
    if not pids:
        print("처리할 상품이 없다.")
        return

    # 2) 스냅샷 — `옵션` 이 없는 옛 캐시는 자동 재조회된다
    print(f"[2/4] 스냅샷 확보 {len(pids)}건")
    recs, errors = snapshot.ensure(pids, sleep=args.sleep, require=("옵션",))
    if errors:
        # **조용히 버리지 않는다** — 예전엔 아래 배치 조립에서 `recs.get(pid)` 가 None 인
        # 상품을 `continue` 로 흘려보내, "대상 973건 중 681건만 처리됨"이 보고 어디에도
        # 남지 않았다(2026-08-05 실측: 1-2 그룹 292건이 이렇게 통째로 누락됐고, 나중에
        # 재조회하니 전부 정상이었다 — 당시 통신 실패였다).
        # 현황판에 남겨야 다음 run 이 집어가고, 사람이 "왜 빠졌나"를 물을 수 있다.
        print(f"  조회 실패 {len(errors)}건 — 현황판에 '보류(조회실패)' 로 남긴다")
        _dump(os.path.join(run_dir, "fetch_errors.json"),
              {pid: str(e)[:300] for pid, e in errors.items()})
        try:
            matrix.mark_many(sheet, TASK,
                             {pid: "보류(조회실패)" for pid in errors}, matrix=m)
        except Exception as e:  # noqa: BLE001
            print(f"  [경고] 조회실패 현황판 기재 실패: {str(e)[:120]}", file=sys.stderr)
        for pid in list(errors)[:5]:
            print(f"    {pid}: {str(errors[pid])[:80]}")

    # 3) 이미지 — 대표 썸네일 1장 + 옵션값 이미지(차원별). 실물·구성 판별의 근거다.
    thumbs_dir = os.path.join(run_dir, "thumbs")
    img = {}
    if not args.skip_thumbs:
        n = 0
        for pid, rec in recs.items():
            paths = {}
            rep = (rec.get("썸네일") or [""])[0]
            if rep:
                p, _ = snapshot.materialize_image(rep, thumbs_dir, pid + "_rep", 0,
                                                  max_px=args.max_px)
                if p:
                    paths["대표"] = p
            for gi, d in enumerate(rec.get("옵션", {}).get("차원") or []):
                for vi, v in enumerate((d.get("values") or [])[:args.max_option_images]):
                    if not v.get("imageUrl"):
                        continue
                    # 옵션값 이미지는 사이즈표·치수 도면 판별에 쓰이지만, 실측상 512 에서
                    # 치수 숫자(`45*39`·`19cm`)가 원본과 동일하게 읽혔다.
                    p, _ = snapshot.materialize_image(
                        v["imageUrl"], thumbs_dir, f"{pid}_{gi}", vi, max_px=args.max_px)
                    if p:
                        paths[f"{gi}:{v.get('vid')}"] = p
            img[pid] = paths
            n += len(paths)
        print(f"[3/4] 이미지 {n}장 확보(캐시 적중분은 복사만)")
    _dump(os.path.join(run_dir, "images.json"), img)

    # 4) 배치 — 워커가 파일 하나로 완주할 수 있게 자기완결형으로 담는다
    products = []
    dropped = []
    for pid in pids:
        rec = recs.get(pid)
        if not rec:
            # 조회 실패는 위에서 이미 현황판에 남겼다. 그 밖의 이유로 빠지는 건이
            # 있으면 여기서 잡아 §대상 대조에 드러낸다 — 침묵 누락 재발 방지.
            dropped.append(pid)
            continue
        o = rec.get("옵션") or {}
        products.append({
            "productId": pid,
            "상품명": rec.get("상품명", ""),
            "원문명": rec.get("원문명", ""),
            "카테고리": rec.get("기존카테고리", ""),
            # 다른 단계가 넘긴 이관 사유. **워커의 판단을 바꾼다** — 썸네일이
            # `기준이미지없음`·`대표옵션의심` 으로 되돌린 건은 대표를 세울 때 옵션 이미지가
            # 실물인지까지 봐야 한다(§2-10). 안 실어 보내면 워커가 그 사실을 모른다.
            "재작업사유": redo.get(pid, ""),
            "대표썸네일": img.get(pid, {}).get("대표", ""),
            "vid고유": o.get("vid고유"),
            "차원": [{
                "index": gi, "이름": d.get("이름"), "원문이름": d.get("원문이름"),
                "values": [{
                    "vid": v.get("vid"), "현재이름": v.get("name"),
                    "원문": v.get("_name"), "제외됨": v.get("exclude"),
                    "이미지": img.get(pid, {}).get(f"{gi}:{v.get('vid')}", ""),
                } for v in (d.get("values") or [])],
            } for gi, d in enumerate(o.get("차원") or [])],
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
        # imgs = 배치에 실린 **실제 이미지 파일 수**(대표+옵션값) — 팬아웃 빈패킹의 예산 축.
        index.append({"n": i, "path": path, "imgs": _batch_imgs(b),
                      "count": len(b),
                      "옵션수": sum(len(p["판매행"]) for p in b)})
    _dump(os.path.join(run_dir, "batches_index.json"), index)
    print(f"\n###PREP### 배치 {len(batches)}개 / 상품 {len(products)}건 / "
          f"옵션 {sum(len(p['판매행']) for p in products)}개 / "
          f"이미지 {sum(x['imgs'] for x in index)}장")
    # 대상 대조 — 대상과 배치가 어긋나면 반드시 눈에 띄게 찍는다. 이 한 줄이 없어서
    # 973건 중 681건만 돈 사실이 드러나지 않았다(2026-08-05).
    print(f"  §대상 대조: 대상 {len(pids)}건 = 배치 {len(products)}건 "
          f"+ 조회실패 {len(errors)}건" + (f" + 기타누락 {len(dropped) - len(errors)}건"
                                      if len(dropped) > len(errors) else ""))
    if len(products) + len(dropped) != len(pids):
        print(f"  [경고] 대상 수가 맞지 않는다 — 확인 필요", file=sys.stderr)
    print(f"  배치: {os.path.join(run_dir, 'batches')}")
    print(f"  다음(Workflow 모드): python {os.path.basename(__file__)} pending "
          f"--run-dir <R> → optclean-fanout 호출 → apply")
    print(f"  다음(수동 폴백): 워커가 배치를 읽고 results/result_NNN.json 생성 → apply")


def _batch_imgs(products):
    """배치 products 에 실린 이미지 파일 수 — 대표썸네일 + 옵션값 이미지(경로가 찬 것만)."""
    n = 0
    for p in products:
        if p.get("대표썸네일"):
            n += 1
        for d in (p.get("차원") or []):
            n += sum(1 for v in (d.get("values") or []) if v.get("이미지"))
    return n


def _pending_batches(run_dir):
    """results/result_NNN.json 이 없는 배치 = 아직 안 된 것. 디스크가 정본이다."""
    idx_path = os.path.join(run_dir, "batches_index.json")
    if not os.path.exists(idx_path):
        return []
    index = _load(idx_path)
    out = []
    for b in index:
        if "n" not in b:
            # 구형 index(파일명·상품수만) 폴백 — 배치 파일에서 재계산한다.
            n = int(str(b.get("batch", "")).replace("batch_", "").replace(".json", "") or 0)
            path = os.path.abspath(os.path.join(run_dir, "batches", b.get("batch", "")))
            imgs = _batch_imgs(_load(path).get("products", [])) if os.path.exists(path) else 0
            b = {"n": n, "path": path, "imgs": imgs, "count": b.get("상품수", 0)}
        if not os.path.exists(os.path.join(
                run_dir, "results", f"result_{b['n']:03d}.json")):
            out.append(b)
    return out


def cmd_pending(args):
    """남은 배치를 JSON 한 줄로 찍는다 — Workflow(optclean-fanout) args 에 그대로 넣는다.

    기본은 압축형 `compact: [[배치번호, 이미지수, 상품수], …]`. 경로는 runDir 과 배치번호로
    정해지므로 args 에 실을 필요가 없다 — 152배치에서 인라인 args 가 25KB 까지 부풀던 것을
    없앤다(2026-08-09 용쌤2-1). 경로가 템플릿과 다른 옛 run-dir 만 완전형으로 떨어뜨린다.
    """
    run_dir = os.path.abspath(args.run_dir)
    pending = _pending_batches(run_dir)
    out = {"runDir": run_dir, "promptPath": WORKER_PROMPT}
    if all(b.get("path") == os.path.join(run_dir, "batches", f"batch_{b['n']:03d}.json")
           for b in pending):
        out["compact"] = [[b["n"], b.get("imgs", 0), b.get("count", 0)] for b in pending]
    else:
        out["batches"] = pending
    print(json.dumps(out, ensure_ascii=False))


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------

def _expected_by_batch(run_dir):
    """batches/batch_NNN.json → {배치번호: [productId, ...]}. 없으면 빈 dict(구형 run-dir)."""
    exp = {}
    for bf in sorted(glob.glob(os.path.join(run_dir, "batches", "batch_*.json"))):
        doc = _load(bf)
        n = doc.get("배치") or int(os.path.basename(bf)[6:9])
        exp[n] = [p.get("productId") for p in doc.get("products", []) if p.get("productId")]
    return exp


def _batch_products(run_dir):
    """batches/batch_NNN.json → {productId: 배치상품}. **로컬 이미지 경로가 여기 있다.**"""
    out = {}
    for bf in sorted(glob.glob(os.path.join(run_dir, "batches", "batch_*.json"))):
        for p in _load(bf).get("products", []):
            if p.get("productId"):
                out[p["productId"]] = p
    return out


def _md5(path):
    try:
        with open(path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except OSError:
        return ""


def _thumb_prefer_id(bp, option, keep_ids):
    """대표썸네일과 **바이트가 같은** 옵션 이미지를 쓰는 최저가 판매행 id (2026-08-06 이룸님).

    최저가 동률에서 "어느 게 대표썸네일과 같은 물건이냐"는 시각 판단이라 워커가 자주
    비워 두고, 그러면 상태가 `확인요` 가 되어 저장이 통째로 멈춘다(3-1 w1 5건).
    그런데 **파일이 아예 같으면 판단이 아니라 사실이다** — 불사자가 그 옵션 이미지를
    대표썸네일로 쓴 것이다. prep 이 대표썸네일·옵션 이미지를 이미 받아 두므로 비용 0이고,
    남는 것만 사람이 눈으로 본다(옵션 이미지 1장 ≈ 800~1,300 토큰).

    **동률군 밖이면 빈 문자열을 돌려준다** — 더 비싼 걸 지목하면 `plan` 이 무시하면서
    경고를 하나 더 달아 오히려 `확인요` 를 만든다(대표는 최저가라는 규칙이 우선).
    """
    rep = _md5(bp.get("대표썸네일") or "")
    if not rep:
        return ""
    hit = {}                                     # 차원 index → vid(문자열)
    for d in (bp.get("차원") or []):
        for v in (d.get("values") or []):
            if v.get("이미지") and _md5(v["이미지"]) == rep:
                hit.setdefault(int(d.get("index") or 0), str(v.get("vid")))
    if not hit:
        return ""
    keep = set(keep_ids or ())
    cands = [r for r in (option.get("판매행") or [])
             if r.get("id") in keep and R.sellable(r)]
    if not cands:
        return ""
    lowest = min((r.get("sale_price") or 0) for r in cands)
    matched = [r for r in cands
               if all(gi < len(str(r.get("id", "")).split(":"))
                      and str(r["id"]).split(":")[gi] == vid
                      for gi, vid in hit.items())]
    best = next((r for r in matched if (r.get("sale_price") or 0) == lowest), None)
    return best["id"] if best else ""


def _repair_pid(pid, allow):
    """워커가 잘라 쓴 상품id를 배치 정본으로 되살린다. 못 살리면 원본 그대로 돌려준다.

    상품id는 27자다. 워커가 앞부분만 복사해 오는 사고가 실제로 났고(2026-08-09 용쌤2-1
    옵션정리 6건), 감사가 그걸 `미지의 상품id`(환각)로 보고 버려 **상품이 통째로 유실**됐다.
    환각과 절단은 다르다 — 절단은 정본의 접두사라 되살릴 근거가 있다.

    **접두사로 정확히 하나만 걸릴 때만** 되살린다. 둘 이상이면 추정이 되므로 버린다.
    12자 미만은 접두사가 너무 짧아(앞자리가 공통인 id가 많다) 손대지 않는다.
    """
    if not allow or not pid or pid in allow or len(pid) < 12:
        return pid
    cands = [x for x in allow if x.startswith(pid)]
    return cands[0] if len(cands) == 1 else pid


def _audit_results(run_dir):
    """워커 산출물을 배치 대비 대조 — 누락·환각·번호 불일치를 apply 전에 잡는다.

    catfix `merge_named` 와 같은 역할이다. 워커가 상품을 빠뜨리면 그대로 조용히
    사라지던 결함(팬아웃 도입 전에는 메인이 직접 결과를 만들어 없던 문제)의 방어선.
    반환: (경고 문자열 리스트, 누락 여부 bool)
    """
    exp = _expected_by_batch(run_dir)
    if not exp:
        return [], False          # 구형 run-dir — 대조할 정본이 없다
    want = {pid for pids in exp.values() for pid in pids}
    got, files, repaired = set(), {}, []
    for rf in sorted(glob.glob(os.path.join(run_dir, "results", "result_*.json"))):
        doc = _load(rf)
        n_file = int(os.path.basename(rf)[7:10])
        n_doc = doc.get("배치")
        if n_doc is not None and n_doc != n_file and n_file != 0:
            files.setdefault("번호불일치", []).append(
                f"{os.path.basename(rf)} 내부 배치={n_doc}")
        for p in doc.get("products", []):
            pid = p.get("productId")
            if not pid:
                continue
            fixed = _repair_pid(pid, want)
            if fixed != pid:
                repaired.append(f"{pid}→{fixed}")
            got.add(fixed)
    missing = sorted(want - got)
    unknown = sorted(got - want)
    warns = []
    done_batches = {n for n, pids in exp.items() if all(p in got for p in pids)}
    miss_batches = sorted(set(exp) - done_batches)
    if miss_batches:
        warns.append(f"미완 배치 {len(miss_batches)}개: {miss_batches[:10]}")
    if missing:
        warns.append(f"누락 상품 {len(missing)}건: {missing[:5]}")
    if repaired:
        warns.append(f"잘린 상품id {len(repaired)}건(접두사로 복원 — 워커 프롬프트 점검): "
                     f"{repaired[:5]}")
    if unknown:
        warns.append(f"미지의 상품id {len(unknown)}건(워커 환각 — 버린다): {unknown[:5]}")
    for msg in files.get("번호불일치", []):
        warns.append(f"파일명↔내부 배치번호 불일치: {msg}")
    return warns, bool(missing)


SPEC_TAB = "상품명"        # 상품명 스킬의 원장 탭
SPEC_COL = "대표지정"      # 그 탭의 규격어 대표 지정 열 — `<판매행id> | <근거키워드>`


def read_spec_main(sheet):
    """상품명 탭의 `대표지정` 열 → {상품id: (판매행id, 근거키워드)}.

    상품명 스킬이 규격어 키워드(`3단서빙카트`)를 쓸 때, 그 규격에 해당하는 옵션을
    지정해 넘긴다(2026-08-05 이룸님). 옵션정리는 그걸 대표로 세운다 — 최저가가 아니어도.
    카테고리 시트 J·K 열을 상품명 prep 이 읽는 것과 같은 방식이다.

    탭이나 열이 없으면 빈 dict — 옛 그룹 시트에서도 그냥 돌아야 한다.
    같은 pid 가 여러 행이면(재작업) **마지막 행이 이긴다** — 상품명 탭은 append 원장이다.
    """
    try:
        # `sheets_get` 은 2차원 배열을 **그대로** 돌려준다(`{"values": ...}` 가 아니다).
        # 여기서 `.get("values")` 를 부르는 바람에 AttributeError 가 나고, 그걸 아래
        # except 가 삼켜 **대표지정을 한 번도 못 읽은 채** 조용히 빈 dict 로 돌았다
        # (2026-08-05 실측: 1-2 그룹 292건 run 에서 최저가 동률 23건의 대표가
        #  상품명 지정 대신 원본 순서로 정해졌다).
        rows = sheets_get(sheet, SPEC_TAB) or []
    except Exception as e:  # noqa: BLE001  원장이 없다고 옵션 정리를 멈추지 않는다
        print(f"  [경고] '{SPEC_TAB}' 탭을 못 읽었다 — 대표지정 없이 진행: {str(e)[:100]}",
              file=sys.stderr)
        return {}
    if not rows:
        return {}
    hdr = rows[0]
    if "상품id" not in hdr or SPEC_COL not in hdr:
        return {}
    ci, cs = hdr.index("상품id"), hdr.index(SPEC_COL)
    out = {}
    for r in rows[1:]:
        pid = (r[ci] if ci < len(r) else "").strip()
        cell = (r[cs] if cs < len(r) else "").strip()
        if not pid:
            continue
        if not cell:
            out.pop(pid, None)     # 재작업이 지정을 지웠다 → 지정 없음으로 되돌린다
            continue
        rid, _, kw = cell.partition("|")
        out[pid] = (rid.strip(), kw.strip())
    return out


# 품목대조에서 무시할 낱말 — 어느 상품명에나 붙는 수식어라 겹쳐도 근거가 못 된다.
_ITEM_STOPWORDS = frozenset((
    "기본형", "업소용", "가정용", "가정", "휴대용", "다용도", "고급", "고급형", "대형",
    "소형", "중형", "미니", "이동식", "접이식", "무선", "유선", "세트", "정품", "신상",
    "인기", "추천", "특가", "국내", "수입", "전용", "겸용", "자동", "수동", "전동",
))


def _item_words(text):
    """품목대조용 낱말 집합 — 2자 이상 조각만, 흔한 수식어는 뺀다."""
    out = set()
    for w in re.split(r"[^0-9A-Za-z가-힣]+", text or ""):
        if len(w) >= 2 and w.lower() not in _ITEM_STOPWORDS:
            out.add(w.lower())
    return out


def _item_mismatch(상품명, 메인상품):
    """상품명과 워커의 `메인상품` 이 **한 낱말도 안 겹치면** 품목 불일치 의심.

    워커의 `삭제후보`/`이관` 판정만으로는 놓치는 게 있다 — 2026-08-09 용쌤2-1 에서
    워커가 27건을 잡았는데 사람이 검수표를 기계적으로 대조하니 13건이 더 나왔다
    (평판프레스 인쇄기→퀵클램프 지그 · 회전간판→LED 라이트박스 · 갯벌삽→낙양삽 …).
    한 건씩 보는 워커는 "이 정도면 비슷한가" 로 흐르는데, 전수 대조는 안 흐른다.

    판단이 아니라 **신호**다 — 저장을 막지 않고 상품명 재작업으로 넘긴다(위양성이
    섞이는 게 정상이다. 개집↔도그하우스처럼 같은 물건을 달리 부른 건도 걸린다).
    상품명은 키워드 나열이라 붙여쓴 낱말이 많다 → 2자 연속 조각까지 본다
    (`베란다인조잔디` ↔ `인조잔디`). 실측 725건에 24건(3.3%)이 걸렸다.
    """
    words = _item_words(상품명)
    main = (메인상품 or "").lower()
    if not words or not main:
        return False
    if words & _item_words(메인상품):
        return False
    return not any(w[i:i + 2] in main for w in words for i in range(len(w) - 1))


def _plans(run_dir, spec_main=None):
    """results/*.json + 스냅샷 → [(상품, 계획, 결과)]. 불사자를 부르지 않는다.

    같은 pid 가 여러 파일에 있으면(재팬아웃 잔재) **마지막 파일이 이긴다.**
    배치 정본이 있으면 거기 없는 pid(워커 환각)는 버린다 — 원장 오염 방지.

    spec_main = {상품id: (판매행id, 근거키워드)} — 상품명이 규격어로 지정한 대표.
    """
    spec_main = spec_main or {}
    bprod = _batch_products(run_dir)
    exp = _expected_by_batch(run_dir)
    allow = {pid for pids in exp.values() for pid in pids} if exp else None
    by_pid, order = {}, []
    for rf in sorted(glob.glob(os.path.join(run_dir, "results", "result_*.json"))):
        for p in _load(rf).get("products", []):
            pid = _repair_pid(p.get("productId"), allow)
            if not pid:
                continue
            if allow is not None and pid not in allow:
                continue          # 환각 — _audit_results 가 경고로 집계한다
            p = {**p, "productId": pid}   # 되살린 id를 계획·저장 경로까지 끌고 간다
            if pid not in by_pid:
                order.append(pid)
            by_pid[pid] = p       # 마지막 파일 승리
    out = []
    for pid in order:
        p = by_pid[pid]
        rec = snapshot.load(pid) if pid else None
        # 워커 결과에 상품명이 없으면 스냅샷에서 채운다 — 없으면 시트 C열과
        # 검수표 머리글이 통째로 빈칸이 된다(어느 상품을 승인하는지 알 수 없다).
        if not p.get("상품명") and rec:
            p["상품명"] = rec.get("상품명", "")
        # 품목대조(2026-08-10) — 워커가 놓친 품목 불일치를 전수 기계대조로 줍는다.
        # 이미 삭제후보로 잡힌 건은 더 볼 것이 없고, 워커가 상품명 이관을 이미 넣었으면
        # 같은 말을 두 번 하지 않는다. **스냅샷이 없어 보류로 빠지는 건도 통과시킨다** —
        # 상품명 이관은 옵션 저장과 무관하고, 하필 이런 건이 이상할 확률이 높다.
        if (not str(p.get("삭제후보") or "").strip()
                and not any((h or {}).get("단계") == "상품명" for h in (p.get("이관") or []))
                and _item_mismatch(p.get("상품명"), p.get("메인상품"))):
            p["품목대조"] = True
            p["이관"] = list(p.get("이관") or []) + [{
                "단계": "상품명",
                "사유": f"품목대조: 상품명과 메인상품이 한 낱말도 겹치지 않는다 "
                        f"(메인상품 '{str(p.get('메인상품'))[:60]}')",
            }]
        if not rec or not rec.get("옵션"):
            out.append((pid, None, {**p, "상태": "보류(스냅샷 없음)"}))
            continue
        # 규칙 11(정렬용 접두사 제거)은 기계적이라 검사 전에 강제한다. 워커 결과에
        # 되써서 저장 경로(`_commit`)도 같은 이름을 쓰게 한다 — 두 벌이면 어긋난다.
        names = R.normalize_names(p.get("이름"))
        p["이름"] = names
        sm, sk = spec_main.get(pid, ("", ""))
        # 워커가 대표를 못 정했으면 **대표썸네일과 바이트가 같은 옵션**을 찾아 쓴다.
        # 판단이 아니라 사실이고 이미 받아둔 파일이라 비용이 0이다(2026-08-06 이룸님).
        prefer = p.get("대표후보")
        if not prefer and not sm:
            prefer = _thumb_prefer_id(bprod.get(pid) or {}, rec["옵션"],
                                      p.get("유지") or ())
            if prefer:
                p["대표썸네일일치"] = prefer      # 검수표·시트 메모에 근거를 남긴다
        plan = R.plan(rec["옵션"],
                      keep_ids=set(p.get("유지") or ()),
                      names=names,
                      prefer_id=prefer,
                      spec_main=sm or None, spec_keyword=sk,
                      # 워커가 쓴 제외 사유를 그대로 넘긴다 (2026-08-15). 안 넘기면
                      # 제외행 전부가 고정 문자열로 덮여 **왜 뺐는지가 원장에서 사라진다**
                      # (4-1 실측: 상세 사유 2,772건이 매 런마다 버려졌다).
                      drop_reasons={str(e.get("id")): e.get("사유", "")
                                    for e in (p.get("제외") or [])
                                    if isinstance(e, dict) and e.get("id")})
        # 워커가 지시서를 지켰는지 재 둔다 — 사유가 비면 표본검수가 판정을 못 한다.
        plan["워커준수"] = R.worker_qc(rec["옵션"], p)
        # 규격어 지정으로 대표가 옮겨지면 `기본형` 마커도 따라 옮겨진다. 저장 경로
        # (`_commit` 은 `w["이름"]` 을 쓴다)가 같은 이름을 보게 워커 결과에 되쓴다 —
        # 두 벌이면 검사는 통과하고 저장은 옛 이름으로 나간다.
        if plan.get("마커이동"):
            names = R.apply_base_suffix(rec["옵션"], names, plan["마커이동"])
            p["이름"] = names
        # 계산은 id 로 하고, 승인은 이름으로 본다. 라벨을 여기서 한 번 만들어
        # 시트·--emit·미리보기 표가 같은 문자열을 쓰게 한다(어긋나면 두 벌이 된다).
        plan["라벨"] = R.row_labels(rec["옵션"], names)
        plan["이름변경"] = R.name_changes(rec["옵션"], names)
        plan["가격"] = {str(r["id"]): r.get("sale_price")
                      for r in (rec["옵션"].get("판매행") or [])}
        # 축 이름 감사(규칙 18). 워커 제안이 있는 축은 `_commit` 이 `renameGroups` 로
        # 저장하고(2026-08-17), 제안 없이 기계 신호만 있는 축은 원장에 `대기` 로 남는다.
        # **상태에는 영향을 주지 않는다** — 축은 표기고, 축 때문에 옵션 저장을 막지 않는다.
        plan["축감사"] = R.axis_audit(rec["옵션"], p.get("축교정"))
        # (2026-08-05 이룸님) 마지막 차원 값이 1개인 경우를 '수동 판단'으로 멈추던 자리다.
        # 기준이 정해져서 `main_value_key` 가 **값 2개 이상인 마지막 차원**을 고르게 됐고,
        # 그러면 오염이 없어 멈출 이유가 사라졌다(용쌤1-3 49건이 이 모양이었다).
        out.append((pid, plan, p))
    return out


def _lab(plan, rid):
    """판매행 id → 사람이 읽을 이름(없으면 id 그대로)."""
    return ((plan or {}).get("라벨") or {}).get(str(rid), str(rid))


def _price(plan, rid):
    return ((plan or {}).get("가격") or {}).get(str(rid))


# 저장을 막지 **않는** 경고 (2026-08-07 이룸님). 나머지 경고는 종전대로 `확인요`.
#
# `경고가 하나라도 있으면 확인요` 는 너무 뭉툭했다 — **최저가 동률**은 규칙이 이미 답을
# 내는 상황(원본 순서)인데도 저장을 통째로 막아 사람 큐로 갔다. 3-2 에서 4건이 그렇게
# 쌓였고, 이룸님 판정: "대표를 원본 순서로 해도 상관 없고, 썸네일 단계에서 썸네일만
# 대표옵션과 동일하면 된다." → 저장하고 **썸네일 열에 재작업을 찍어** 넘긴다(_handoff_tie).
NONBLOCKING_WARNINGS = ("최저가 동률",)


def _status_of(plan, worker):
    # **상품명이 가리키는 물건과 옵션 실물이 아예 다른 품목** = 삭제 건이다
    # (2026-08-06 이룸님). 이름을 다시 짓는 게 아니라 상품을 지운다 — 옵션을 정리해 봐야
    # 팔 수 없는 물건이므로 저장 대상에서 뺀다. 실제 삭제는 메인이 `bulsaja_market_delete`
    # 로 수행하고, 여기서는 `deletion_candidates.json` + 현황판 표시까지만 한다.
    if str(worker.get("삭제후보") or "").strip():
        return "보류(삭제대상)"
    if plan is None:
        return worker.get("상태") or "보류(스냅샷 없음)"
    # 상품명이 규격어로 지정한 대표를 워커가 '메인상품 아님'으로 뺐다 — 판단이 갈린다.
    # 규칙으로 정할 수 없어(제외 8분류는 '다른모델이 맞다'와 '잘못 뺐다'가 사유 문자열만
    # 으론 구분 안 된다) 사람에게 올린다. 용쌤1-3 실측 2건 = 1,000건당 2~3건 규모.
    if plan.get("대표충돌"):
        return "보류(대표충돌)"
    if not plan.get("대표"):
        return "보류(남길 옵션 없음)"
    chk = plan.get("이름검사") or {}
    if chk.get("위반") or chk.get("중복"):
        return "보류(이름규칙)"
    # `마커수동` 은 폐지됐다(2026-08-05) — 값 1개짜리 차원을 건너뛰게 되어 오염이 없다.
    # 옛 run-dir 의 계획에 남아 있을 수 있어 키는 읽지 않는다.
    # 대표옵션 마커('기본형')는 상품명 끝의 같은 단어와 짝을 이루는 유일한 표식이다 —
    # 없거나 대표 아닌 옵션에 붙어 있으면 저장 전에 멈춘다(2026-07-30 이룸님).
    mark = chk.get("마커") or {}
    if mark.get("누락") or mark.get("오부착"):
        return "보류(기본형)"
    blocking = [w for w in (plan.get("경고") or [])
                if not str(w).startswith(NONBLOCKING_WARNINGS)]
    if blocking:
        return "확인요"
    return "정리대상"


def _print_table(rows):
    print(f"\n{'상품id':<28} {'상태':<14} {'대표':<24} {'기준가':>9} {'상한':>9} 유지/전체")
    print("-" * 104)
    for pid, plan, w, st in rows:
        if plan:
            rep = f"{_lab(plan, plan['대표'])}({plan['대표']})"
            print(f"{pid:<28} {st:<14} {rep[:23]:<24} "
                  f"{(plan['기준가'] or 0):>9,} {(plan['상한'] or 0):>9,} "
                  f"{len(plan['유지'])}/{len(plan['유지']) + len(plan['제외'])}")
        else:
            print(f"{pid:<28} {st:<14}")


def _print_worker_qc(rows, run_dir):
    """워커 준수 수치를 **표본검수보다 먼저** 찍는다 (2026-08-15).

    순서가 핵심이다. 사유가 없으면 표본을 봐도 판정이 안 된다 — 4-1 표본검수에서
    제외 0건인 상품 2건을 "제외 과다"로 의심하는 오판이 실제로 났다.

    저장은 막지 않는다(제외 목록 자체는 여집합이라 완전하다). 대신 재실행 대상 상품id를
    `worker_qc.json` 으로 떨어뜨려 재팬아웃을 기계적으로 만든다 — 4-2 가 손으로 79건을
    뽑던 목록이다. 손으로 하면 다음 사람이 안 한다.
    """
    qc = [(pid, plan.get("워커준수") or {}) for pid, plan, _w, _st in rows if plan]
    if not qc:
        return
    unsaid = [(pid, q) for pid, q in qc if q.get("미언급")]
    state = [(pid, q) for pid, q in qc if q.get("상태근거")]
    uncat = sum(q.get("무분류수") or 0 for _pid, q in qc)
    drops = sum(q.get("제외수") or 0 for _pid, q in qc)
    print(f"\n[워커준수] 상품 {len(qc)}건 · 워커가 사유를 쓴 제외행 {drops}개 "
          f"· 무분류 {uncat}개")
    if unsaid:
        n = sum(len(q["미언급"]) for _pid, q in unsaid)
        print(f"  ⚠ 미언급 {len(unsaid)}건({n}행) — 유지·제외 어디에도 안 적힌 판매행이 있다. "
              f"그 행들은 사유 없이 제외로 떨어진다")
        for pid, q in sorted(unsaid, key=lambda x: -len(x[1]["미언급"]))[:5]:
            print(f"    {pid} {len(q['미언급'])}/{q['판매행수']}행")
    if state:
        print(f"  ⚠ 상태근거 {len(state)}건 — `현재제외`·`현재대표` 를 제외 근거로 썼다"
              f"(뒤집혀 있는 게 흔해 근거가 못 된다)")
        for pid, q in state[:5]:
            print(f"    {pid} {q['상태근거'][0]['사유'][:70]}")
    if unsaid or state:
        path = os.path.join(run_dir, "worker_qc.json")
        _dump(path, {"재실행대상": sorted({pid for pid, _q in unsaid + state}),
                     "상세": {pid: q for pid, q in qc if q.get("위반")}})
        print(f"  → 재실행 대상 {len({pid for pid, _q in unsaid + state})}건: {path}")


def _print_review(rows):
    """승인 검수표 — 승인해야 할 **옵션명 그 자체**를 보여준다.

    신호(⚠)는 "이상하다"를 가리킬 뿐 무엇을 승인하는지 알려주지 않는다. 실전 1건에서
    이룸님이 지적한 결함: 교정된 옵션명이 표·시트·plans.json 어디에도 없었다.
    """
    for pid, plan, w, st in rows:
        if not plan:
            continue
        print(f"\n── 검수표 {pid} · {w.get('상품명', '')[:40]}")
        if w.get("메인상품"):
            print(f"   메인상품: {w['메인상품']}")
        if w.get("품목대조"):
            print("   ⚠ 품목대조: 상품명과 메인상품이 한 낱말도 겹치지 않는다 "
                  "— 상품명 재작업으로 넘겼다(저장은 막지 않음)")
        print(f"   대표 {_lab(plan, plan['대표'])} · 기준가 {(plan['기준가'] or 0):,} "
              f"→ 상한 {(plan['상한'] or 0):,}")
        if w.get("대표썸네일일치"):
            print(f"   [대표근거] 대표썸네일과 파일이 동일한 옵션 "
                  f"{_lab(plan, w['대표썸네일일치'])}({w['대표썸네일일치']}) — 동률 자동 해소")

        chg = [c for c in (plan.get("이름변경") or []) if c["변경"]]
        same = len(plan.get("이름변경") or []) - len(chg)
        if chg:
            print(f"   [옵션명 교정 {len(chg)}건 · 유지 {same}건]")
            for c in chg:
                pre = f"{c['차원']}·" if c["차원"] else ""
                print(f"     {pre}{c['키']:>4} {c['기존']}  →  {c['교정']}")
        elif plan.get("이름변경"):
            print(f"   [옵션명 교정 0건 — {same}건 그대로]")

        # 축 이름은 이번 저장에서 안 바뀐다(MCP 미지원) — 시트 원장으로만 넘어간다.
        if plan.get("축감사"):
            print(f"   [옵션 축 {len(plan['축감사'])}건 — 저장 안 함, '{AXIS_TAB}' 탭 기록]")
            for a in plan["축감사"]:
                tail = f"  → 제안 '{a['제안']}'" if a["제안"] else ""
                print(f"     차원{a['차원']} '{a['현재']}'(원문 {a['원문'] or '-'})"
                      f"{tail}  [{'; '.join(a['신호']) or '워커 제안'}]")
                print(f"       값: {' / '.join(v for v in a['값예시'] if v)[:70]}")

        print(f"   [판매 {len(plan['유지'])}건 · 업로드 순서(판매가 오름차순)]")
        for i, rid in enumerate(plan.get("순서") or [], 1):
            mark = "★" if str(rid) == str(plan["대표"]) else " "
            print(f"     {mark}{i:>2}. {_lab(plan, rid):<26} {(_price(plan, rid) or 0):>9,}")
        if plan.get("제외"):
            print(f"   [제외 {len(plan['제외'])}건]")
            for e in plan["제외"]:
                print(f"      - {_lab(plan, e['id'])} — {e['사유']}")


def cmd_apply(args):
    run_dir = os.path.abspath(args.run_dir)
    sheet = _resolve_sheet(args)
    # 감사 — 워커 산출물을 배치 정본과 대조. 미리보기는 경고만, --commit 은 누락 시 차단.
    warns, has_missing = _audit_results(run_dir)
    for w in warns:
        print(f"  [감사] {w}")
    if args.commit and has_missing and not getattr(args, "allow_missing", False):
        print("\n누락 상품이 있어 --commit 을 차단한다. "
              "pending 재계산 → 재팬아웃으로 채우거나, 의도된 것이면 --allow-missing.",
              file=sys.stderr)
        sys.exit(3)
    # 상품명이 규격어로 지정한 대표(2026-08-05) — 없으면 종전대로 최저가가 대표다
    spec_main = read_spec_main(sheet)
    if spec_main:
        print(f"  대표지정(상품명 규격어) {len(spec_main)}건 반영")
    items = _plans(run_dir, spec_main=spec_main)
    if not items:
        print(f"results 가 없다: {os.path.join(run_dir, 'results')}")
        return
    rows = [(pid, plan, w, _status_of(plan, w)) for pid, plan, w in items]
    # --ids: 재저장(부분 재시도) 전용. 대량 run 에서 일부만 실패했을 때 전건을 다시
    # 돌리지 않고 그 상품만 다시 태운다(용쌤1-2: 540건 중 57건 실패).
    if getattr(args, "ids", None):
        want = {i.strip() for i in args.ids if i.strip()}
        unknown = want - {r[0] for r in rows}
        if unknown:
            print(f"  [경고] results 에 없는 상품 {len(unknown)}건: {sorted(unknown)[:3]}")
        rows = [r for r in rows if r[0] in want]
        print(f"  --ids 적용 → {len(rows)}건")
        if not rows:
            return
    _print_table(rows)
    # 표본검수 **앞**이다 — 사유를 믿어도 되는지 먼저 알아야 표본 판정이 성립한다.
    _print_worker_qc(rows, run_dir)
    if not args.no_review:
        _print_review(rows)

    for pid, plan, w, st in rows:
        # 판매행 상한으로 자른 건 — 경고가 아니라 정책 적용 기록이라 상태를 낮추지 않는다.
        if plan and plan.get("행제한"):
            print(f"  [행제한] {pid}: {plan['행제한']}")
        if plan and plan.get("경고"):
            for x in plan["경고"]:
                print(f"  [경고] {pid}: {x}")
        if plan and (plan.get("이름검사") or {}).get("위반"):
            print(f"  [이름] {pid}: {plan['이름검사']['위반']}")
        mark = ((plan or {}).get("이름검사") or {}).get("마커") or {}
        if mark.get("누락"):
            print(f"  [기본형] {pid}: 대표옵션 이름이 '{R.BASE_SUFFIX}'로 끝나지 않는다 "
                  f"(대표값키 {plan.get('대표값키') or '없음'})")
        if mark.get("오부착"):
            print(f"  [기본형] {pid}: 대표가 아닌 옵션에 붙었다 {mark['오부착'][:3]}")

    # 삭제 건 — 상품명이 가리키는 물건과 옵션 실물이 아예 다른 품목(2026-08-06 이룸님).
    # 파일로 남기지 않으면 표에 한 줄 찍히고 끝나 아무도 안 지운다. 실제 삭제는 메인이
    # `bulsaja_market_delete` 로 한다(썸네일 §404 자동삭제와 같은 경로).
    dels = {pid: {"상품명": (w or {}).get("상품명", ""),
                  "사유": str((w or {}).get("삭제후보") or "").strip()[:200]}
            for pid, _plan, w, st in rows if st == "보류(삭제대상)"}
    if dels:
        _dump(os.path.join(os.path.abspath(args.run_dir), "deletion_candidates.json"), dels)
        print(f"\n  [삭제대상] {len(dels)}건 — deletion_candidates.json "
              f"(저장하지 않는다. 메인이 bulsaja_market_delete 로 처리)")
        for pid, d in list(dels.items())[:5]:
            print(f"    {pid} {d['상품명'][:28]} — {d['사유'][:60]}")

    # 품목대조 — 워커가 못 잡은 품목 불일치. 저장은 막지 않고 상품명 재작업으로 넘겼지만,
    # **몇 건인지는 반드시 눈에 띄어야 한다**(2026-08-09 에는 사람이 손으로 찾아냈다).
    mism = [(pid, w) for pid, _plan, w, _st in rows if (w or {}).get("품목대조")]
    if mism:
        print(f"\n  [품목대조] {len(mism)}건 — 상품명과 메인상품이 한 낱말도 안 겹친다. "
              f"상품명 재작업으로 넘겼다(저장은 그대로 진행)")
        for pid, w in mism[:8]:
            print(f"    {pid} {str(w.get('상품명', ''))[:26]} ↔ {str(w.get('메인상품', ''))[:40]}")
        if len(mism) > 8:
            print(f"    ... 외 {len(mism) - 8}건")

    ok = [r for r in rows if r[3] == "정리대상"]
    print(f"\n정리대상 {len(ok)}건 / 확인요·보류 {len(rows) - len(ok)}건")
    part = [r for r in rows if r[3] in PARTIAL_SAVE]
    if part:
        print(f"  그중 부분저장 {len(part)}건 — 옵션명만 건너뛰고 판매·대표·순서는 저장한다"
              f"(현황판 {TASK} 열에 재작업으로 남아 다음 회차가 다시 집는다)")

    # --emit: 계획 요약을 JSON 으로 남긴다. 세로 러너(onestep)의 이상 신호 판정이 읽는다.
    # 표는 사람용이라 파싱 대상이 아니고, plan 객체는 내부 구조라 그대로 노출하지 않는다.
    if args.emit:
        _dump(args.emit, [{
            "productId": pid,
            "상태": st,
            "메인상품": (w or {}).get("메인상품", ""),
            "유지수": len((plan or {}).get("유지") or []),
            "제외수": len((plan or {}).get("제외") or []),
            "판매행수": len((plan or {}).get("순서") or []),
            "대표": (plan or {}).get("대표") or "",
            # 이름 3종은 **승인 자료**다. id 만 있으면 게이트에서 무엇을 승인하는지 알 수 없다.
            "대표이름": _lab(plan, (plan or {}).get("대표")) if plan else "",
            "순서이름": [_lab(plan, i) for i in ((plan or {}).get("순서") or [])],
            "순서상세": [{"id": i, "이름": _lab(plan, i), "판매가": _price(plan, i),
                      "대표": str(i) == str((plan or {}).get("대표"))}
                     for i in ((plan or {}).get("순서") or [])],
            "이름변경": [c for c in ((plan or {}).get("이름변경") or []) if c["변경"]],
            "제외상세": [{"id": e["id"], "이름": _lab(plan, e["id"]), "사유": e["사유"]}
                     for e in ((plan or {}).get("제외") or [])],
            # 워커 준수(2026-08-15) — 세로 러너가 "이 사유를 믿어도 되나"를 판정하는 재료.
            "미언급": list(((plan or {}).get("워커준수") or {}).get("미언급") or []),
            "상태근거": list(((plan or {}).get("워커준수") or {}).get("상태근거") or []),
            "기준가": (plan or {}).get("기준가") or "",
            "상한": (plan or {}).get("상한") or "",
            "경고": list((plan or {}).get("경고") or []),
            "이름위반": list(((plan or {}).get("이름검사") or {}).get("위반") or []),
            # 대표옵션 마커 — 게이트에서 "썸네일=대표옵션=상품명"이 맞는지 보는 재료
            "대표값키": (plan or {}).get("대표값키") or "",
            "기본형누락": bool((((plan or {}).get("이름검사") or {}).get("마커")
                           or {}).get("누락")),
            "기본형오부착": list((((plan or {}).get("이름검사") or {}).get("마커")
                             or {}).get("오부착") or []),
            # 축 이름(규칙 18) — 제안이 있는 축은 이번 저장에 함께 나간다(2026-08-17).
            # 세로 러너 게이트가 "이 상품은 축도 바뀐다"를 사람에게 보여주는 재료.
            "축감사": list((plan or {}).get("축감사") or []),
        } for pid, plan, w, st in rows])
        print(f"  계획 요약: {args.emit}")

    if not args.no_sheet:
        _log_sheet(sheet, rows)
        # 저장까지 가는 회차면 여기서 안 쓴다 — `_commit` 이 **실제 결과**로 한 번에 쓴다.
        # 두 번 쓰면 원장이 `대기` → `반영` 으로 두 번 왕복해 쿼터만 먹는다.
        if not args.commit:
            _log_axis_sheet(sheet, rows)

    # 현황판은 **`--no-sheet` 와 무관하게** 쓴다 (2026-08-14, 2-2 에서 밟았다).
    # 원장 탭 쓰기(느리다·쿼터를 먹는다)를 끄려고 `--no-sheet` 를 붙이면 현황판까지
    # 같이 막혀서, 저장은 664건 다 됐는데 `00_진행` 은 `재작업` 그대로였다.
    # 그 상태로 두면 다음 회차가 같은 상품을 통째로 다시 집는다.
    if not args.no_matrix:
        if dels and args.commit:
            # 아직 안 지웠어도 다음 회차가 헛돌지 않게 표시해 둔다(삭제되면 `해당없음`).
            try:
                n = matrix.mark_many(sheet, TASK,
                                     {pid: "보류(삭제대상)" for pid in dels})
                print(f"  현황판({matrix.TAB}) {TASK}: 삭제대상 {n}칸")
            except Exception as e:  # noqa: BLE001
                print(f"  [경고] 삭제대상 표시 실패: {str(e)[:120]}", file=sys.stderr)

    if not args.commit:
        print("\n미리보기다. 실제 반영하려면 이룸님 승인 후 --commit 을 붙여라.")
        return

    _commit(sheet, rows, args)


def _commit_targets(rows):
    """저장 대상 = `정리대상` + **부분저장 대상**(이름 규칙만 어긴 건).

    `보류(대표충돌)`·`보류(남길 옵션 없음)`·`확인요` 는 그대로 저장하지 않는다 —
    그건 **무엇을 팔지**가 아직 안 정해진 상태라, 저장하면 틀린 구성을 밀어 넣는다.
    `보류(기본형)` 만 다르다: 어긴 건 이름 표기 하나뿐이고 판매 구성은 확정돼 있다.
    """
    return [r for r in rows if r[3] == "정리대상" or r[3] in PARTIAL_SAVE]


def _names_to_save(w, before, partial):
    """저장할 옵션명. 부분저장이면 **빈 dict** — ①(이름) 단계를 통째로 건너뛴다.

    `기본형` 마커는 이름에 붙는 표시라 위반한 이름을 그대로 밀어 넣으면 틀린 마커가
    남는다. 저장 후 검증(`R.verify`)도 `names` 가 비면 이름·마커 항목을 건너뛴다.
    """
    if partial:
        return {}
    names = {str(k): v for k, v in (w.get("이름") or {}).items()}
    # 워커가 안 준 값에 남은 정렬용 접두사를 기계적으로 메운다 — 그 한 값 때문에
    # 이름 저장 후 검사가 상품을 통째로 떨어뜨린다(용쌤1-3: 실패 36건 중 32건).
    names = R.with_prefix_cleanup(before, names)
    # 제외행까지 포함한 **전 옵션**의 이름 중복을 기계적으로 갈라 놓는다 — 서버는 판매
    # 여부를 안 가리고 겹치면 저장을 거부한다(25-2 실측 1건, §with_dedup_cleanup).
    return R.with_dedup_cleanup(before, names)


def _memo(plan, w):
    """시트 `메모` — 대표충돌이면 사람이 판단할 재료를 먼저 적는다.

    `보류(대표충돌)` 은 상품명이 지정한 대표를 워커가 뺀 상태다. 규칙으로 못 정하므로
    (제외 8분류는 '다른모델이 맞다'와 '잘못 뺐다'가 사유 문자열만으론 구분 안 된다)
    지정 옵션·근거 키워드·제외 사유 셋을 남겨 이룸님이 보고 정한다.
    """
    c = (plan or {}).get("대표충돌")
    if c:
        return (f"대표충돌 — 상품명이 '{c.get('근거키워드', '')}' 근거로 "
                f"{_lab(plan, c.get('지정'))}({c.get('지정')})를 대표로 지정했으나 "
                f"옵션정리가 제외함: {c.get('사유', '')}")[:400]
    return "; ".join((plan or {}).get("경고") or [])[:400] or w.get("메모", "")


def _row_values(pid, plan, w, st):
    """시트 1행. **id 가 아니라 이름으로 적는다** — 사람이 이걸 보고 승인한다."""
    chg = [c for c in ((plan or {}).get("이름변경") or []) if c["변경"]]
    return [
        pid, _today(), w.get("상품명", ""), w.get("메인상품", ""),
        (len(plan["유지"]) + len(plan["제외"])) if plan else "",
        len(plan["유지"]) if plan else "",
        "; ".join(f"{_lab(plan, e['id'])}:{e['사유']}"
                  for e in (plan["제외"] if plan else []))[:900],
        f"{_lab(plan, plan['대표'])} ({plan['대표']})" if plan and plan.get("대표") else "",
        (plan or {}).get("기준가") or "", (plan or {}).get("상한") or "",
        " > ".join(_lab(plan, i) for i in ((plan or {}).get("순서") or []))[:900],
        st, _memo(plan, w),
        "; ".join(f"{c['기존']}→{c['교정']}" for c in chg)[:900],
    ]


# gws 는 요청 바디를 명령줄 인자로 넘긴다 → 한 호출의 상한은 OS 의 인자 길이다.
# 윈도우 CreateProcess 는 32,767자, macOS/리눅스는 ARG_MAX(맥 1MB)라 자릿수가 다르다.
# 윈도우 기준(12k)을 맥에 그대로 쓰면 호출이 수십 번으로 쪼개져 **쓰기 쿼터**에 걸린다.
_ARG_BUDGET = 12000 if os.name == "nt" else 200000


def _row_runs(sorted_upd, budget=None):
    """(행번호, 값) 오름차순 목록 → 연속 구간 [(시작행, [값...]), ...].

    행 번호가 끊기거나 길이 예산을 넘으면 구간을 끊는다.
    """
    budget = budget or _ARG_BUDGET
    runs = []
    for r, vals in sorted_upd:
        n = len(json.dumps(vals, ensure_ascii=False)) + 1
        if runs and r == runs[-1][0] + len(runs[-1][1]) and runs[-1][2] + n <= budget:
            runs[-1][1].append(vals)
            runs[-1][2] += n
        else:
            runs.append([r, [vals], n])
    return [(r, block) for r, block, _ in runs]


def _log_sheet(sheet, rows):
    """탭에 기록한다. **이미 있는 상품id 는 건너뛰지 않고 그 행을 갱신한다** —
    되돌려 다시 돌렸을 때 옛 계획이 시트에 남아 있으면 승인 자료가 거짓이 된다."""
    if ensure_tab(sheet, TAB, HEADER):
        print(f"  탭 신설: {TAB}")
    try:
        col_a = [str(r[0]).strip() if r else "" for r in sheets_get(sheet, f"'{TAB}'!A2:A")]
    except Exception:
        col_a = []
    at = {pid: i + 2 for i, pid in enumerate(col_a) if pid}   # 상품id → 시트 행번호
    last = _col_letter(len(HEADER))

    add, upd = [], []
    for pid, plan, w, st in rows:
        vals = _row_values(pid, plan, w, st)
        r = at.get(pid)
        if r:
            upd.append((r, vals))
        else:
            add.append(vals)

    # 갱신 — **연속 구간으로 묶고, 그 구간들을 다시 batchUpdate 한 호출에 싣는다.**
    # 건건 update 하면 쓰기 호출이 행수만큼 나가 분당 쿼터(60)에 즉사한다
    # (용쌤1-2 676행에서 실측). 연속 묶기만으로는 **재작업처럼 대상이 흩어진 경우**를
    # 못 줄인다 — 92행이 92호출이 되어 또 429 가 났다(용쌤1-3 기본형 재작업).
    ranges = [(f"'{TAB}'!A{start}:{last}{start + len(block) - 1}", block)
              for start, block in _row_runs(sorted(upd))]
    for _, part in chunk_by_size(ranges, budget=_ARG_BUDGET):
        sheets_batch_update(sheet, part, value_input="USER_ENTERED")
    if upd:
        print(f"  시트 갱신: {len(upd)}행 / 구간 {len(ranges)}개 → '{TAB}'")

    if add:
        # gws 는 요청 바디를 명령줄 인자로 넘긴다 → 행이 많으면 ARG_MAX 를 넘겨
        # `[Errno 7] Argument list too long` 으로 죽는다(용쌤1-2 678행에서 실측).
        # 길이 기준 청크는 라이브러리가 갖고 있고, 분할은 호출자 책임이다.
        for _, part in chunk_by_size(add, budget=_ARG_BUDGET):
            append_rows(sheet, TAB, part)
        print(f"  시트 기록: {len(add)}행 → '{TAB}'")


def _log_axis_sheet(sheet, rows, status=None):
    """옵션 축 이름 원장(`옵션축` 탭) — 규칙 18.

    `status` = {(상품id, 차원문자열): 상태}. `_commit` 이 실제 저장 결과를 넘긴다
    (`반영` / `보류(사유)`). 안 넘기면 전부 `대기` 로 쌓인다(= 미리보기 회차).

    **2026-08-17부터 이 탭은 '수동 반영 목록'이 아니라 '무엇을 왜 바꿨나의 원장'이다.**
    MCP 에 `renameGroups` 가 생겨 축 이름을 코드가 직접 저장한다. 워커 제안이 없어
    코드가 이름을 지어낼 수 없는 축만 종전대로 `대기` 로 남아 사람 몫이 된다.

    키는 (상품id, 차원 index) — 상품 하나에 축이 여럿이라 상품id 만으로는 못 찍는다.
    **상태가 `대기` 가 아닌 행은 건드리지 않는다** — 이룸님이 `반영`·`무시` 로 바꿔둔 판단을
    재실행이 되돌리면 원장이 거짓이 된다(카테고리 finish 가 밟았던 덮어쓰기 결함과 같은 함정).
    """
    status = status or {}
    entries = [(pid, w, a) for pid, plan, w, _st in rows
               for a in ((plan or {}).get("축감사") or [])]
    if not entries:
        return
    if ensure_tab(sheet, AXIS_TAB, AXIS_HEADER):
        print(f"  탭 신설: {AXIS_TAB}")
    last = _col_letter(len(AXIS_HEADER))
    try:
        cur = sheets_get(sheet, f"'{AXIS_TAB}'!A2:{last}")
    except Exception:
        cur = []
    at, state = {}, {}
    for i, r in enumerate(cur):
        pid = str(r[0]).strip() if r else ""
        if not pid:
            continue
        key = (pid, str(r[3]).strip() if len(r) > 3 else "")
        at[key] = i + 2
        state[key] = str(r[10]).strip() if len(r) > 10 else ""

    add, upd, kept = [], [], 0
    for pid, w, a in entries:
        key = (pid, str(a["차원"]))
        # **`대기` 는 이제 거의 안 쓴다** (2026-08-17 이룸님 — 사람 손 최소화).
        # 제안이 없는 축은 둘 중 하나로 닫는다: 이름이 객관적으로 깨졌으면 코드가 지어
        # 저장했고(`axis_fallback`), 휴리스틱 신호뿐이면 지금 이름을 유지한다.
        # 어느 쪽도 사람이 할 일이 아니라, 원장에 할 일로 쌓아두면 그게 거짓이 된다.
        기본 = AXIS_PENDING if a["제안"] else AXIS_KEEP
        vals = [pid, _today(), w.get("상품명", ""), str(a["차원"]),
                a["원문"], a["현재"], a["제안"], a["사유"][:400],
                " / ".join(v for v in a["값예시"] if v)[:300],
                "; ".join(a["신호"])[:200], status.get(key, 기본)]
        r = at.get(key)
        if r is None:
            add.append(vals)
        elif key in status:
            # 이번 회차가 **실제로 손댄 축**이다 — 원장은 실제와 같아야 한다.
            # (`무시` 로 판단된 축은 `_axis_ignored` 가 제안 단계에서 걸러내므로
            #  여기 `status` 에 아예 안 들어온다. 그래서 이 분기가 판단을 덮지 않는다.)
            upd.append((r, vals))
        elif state.get(key, AXIS_PENDING) not in ("", AXIS_PENDING):
            kept += 1                      # 사람이 판단한 행 — 그대로 둔다
        else:
            upd.append((r, vals))

    for start, block in _row_runs(sorted(upd)):
        sheets_update(sheet, f"'{AXIS_TAB}'!A{start}:{last}{start + len(block) - 1}",
                      block, value_input="USER_ENTERED")
    if add:
        for _, part in chunk_by_size(add, budget=_ARG_BUDGET):
            append_rows(sheet, AXIS_TAB, part)
    n_ap = sum(1 for v in status.values() if v == AXIS_APPLIED)
    print(f"  옵션 축: 신규 {len(add)} / 갱신 {len(upd)} / 판단완료 유지 {kept} "
          f"→ '{AXIS_TAB}'"
          + (f" (반영 {n_ap}축)" if status else " (대기 — 제안이 있으면 저장 회차가 태운다)"))


def _axis_ignored(sheet):
    """이룸님이 `옵션축` 탭에서 `무시`·`반영` 으로 판단해둔 (상품id, 차원) 집합.

    **저장 전에 제안에서 걸러낸다.** 이 탭은 원래 '앱에서 수동 반영할 목록'이었고
    `무시` 는 "이 축은 지금 이름이 맞다"는 판단이다. 코드가 축을 저장하게 된 뒤에도
    그 판단이 이겨야 한다 — 안 그러면 재실행이 사람이 내린 결론을 매번 되돌린다.
    `반영` 도 같이 뺀다(앱에서 이미 손으로 고친 축을 워커 제안으로 다시 덮지 않는다).
    """
    try:
        cur = sheets_get(sheet, f"'{AXIS_TAB}'!A2:{_col_letter(len(AXIS_HEADER))}")
    except Exception:
        return set()                        # 탭이 아직 없다 = 판단도 없다
    out = set()
    for r in cur or []:
        pid = str(r[0]).strip() if r else ""
        st = str(r[10]).strip() if len(r) > 10 else ""
        if pid and st and st not in (AXIS_PENDING,) and not st.startswith("보류"):
            out.add((pid, str(r[3]).strip() if len(r) > 3 else ""))
    return out


# ---------------------------------------------------------------------------
# axis — 원장에 쌓인 `대기` 축을 태운다
# ---------------------------------------------------------------------------

def cmd_axis(args):
    """`옵션축` 탭의 `대기` 행을 읽어 실제로 `renameGroups` 로 저장한다.

    **왜 별도 명령인가.** `_commit` 이 축을 저장하는 건 **이번 run 에 든 상품**뿐이다.
    그런데 원장에 쌓인 축들은 전부 **이미 옵션이 `완료` 인 상품**의 것이라 현황판
    `pending` 에 안 잡힌다 — MCP 에 축 필드가 없던 시절에 판정만 해서 쌓아둔 것이기
    때문이다. 이 명령이 없으면 `_commit` 을 고쳐도 그 backlog 는 영영 안 나간다
    (1-2 실측 278행 중 제안이 있는 200행). 옵션을 통째로 다시 돌릴 이유는 없다 —
    바뀌는 건 축 **표기 하나**고, 무엇을 파느냐는 이미 정해져 있다.

    **원장이 현재 상태와 어긋나면 보내지 않는다.** 제안은 그때의 축 이름을 보고 지은
    것이라, 그 사이 축이 달라졌으면 제안의 근거가 사라진 것이다. 세 갈래로 가른다:
      · 현재 축 == 제안        → `반영`  (이미 그렇게 돼 있다. 호출하지 않는다)
      · 현재 축 != 원장의 현재축명 → `보류(축이 바뀌었다…)`  (사람이 다시 본다)
      · 그 밖                  → 저장 대상

    저장 자체의 검증(금지문자·축끼리 겹침·결함)은 `axis_saveable` 이, 반영 확인은
    `axis_verify` 가 한다 — `_commit` 과 **같은 함수**다. 경로가 둘이어도 판정은 하나다.
    """
    sheet = _resolve_sheet(args)
    print(f"  시트: {sheet}")
    rows = sheets_get(sheet, f"'{AXIS_TAB}'!A2:{_col_letter(len(AXIS_HEADER))}") or []

    # 1) 대상 — 제안이 있고 상태가 `대기` 이거나 `보류(…)` 인 행.
    #    행 번호를 같이 들고 다닌다 — 결과를 그 행의 `상태` 칸에 되써야 한다.
    #
    #    **`보류` 를 같이 집는 이유**: 그건 사람의 판단이 아니라 **코드가 못 한 것**이다
    #    (금지문자·이름 겹침·저장 거부·검증 실패). 안 집으면 한 번 막힌 축은 영영 재시도
    #    되지 않는다 — 실제로 `/` 하나 때문에 25축이 그 상태로 남았다(1-2, 2026-08-17).
    #    사람이 내린 판단(`무시`·`반영`)만 건드리지 않는다. `_axis_ignored` 가 `보류` 를
    #    빼는 것과 **같은 기준**이다 — 두 자리가 어긋나면 한쪽이 반드시 거짓말을 한다.
    #    (제안 없는 행 = 사람 몫이라 그대로 둔다)
    todo = {}                                   # pid → [(행번호, 차원, 현재축명, 제안)]
    repaired = []                               # [(행번호, 고친 제안)] — G열에 되쓴다
    n_noprop = 0
    for i, r in enumerate(rows, start=2):
        def _c(j):
            return str(r[j]).strip() if len(r) > j else ""
        pid, st, prop = _c(0), _c(10), _c(6)
        if not pid or not (st == AXIS_PENDING or st.startswith("보류")):
            continue
        if not prop:
            n_noprop += 1
            continue
        try:
            gi = int(_c(3))
        except ValueError:
            continue
        # 구분자 `/` 만 `·` 로 고친다 — 축 저장이 없던 시절에 지은 제안이라 금지문자
        # 규칙을 몰랐다(1-2 실측 200축 중 25축). 고친 값은 원장 G열에도 되써서
        # **원장에 적힌 제안과 실제로 보낸 값이 같게** 한다.
        fixed = R.axis_repair(prop)
        if fixed != prop:
            repaired.append((i, fixed))
            prop = fixed
        todo.setdefault(pid, []).append((i, gi, _c(5), prop))
    if args.ids:
        want = set(args.ids)
        todo = {p: v for p, v in todo.items() if p in want}
        keep = {i for v in todo.values() for i, *_ in v}
        repaired = [(i, v) for i, v in repaired if i in keep]
    print(f"[1/3] 원장 {len(rows)}행 → 대상 {sum(len(v) for v in todo.values())}축 "
          f"/ {len(todo)}상품 (제안 없어 사람 몫 {n_noprop}축)")
    if repaired:
        print(f"  구분자 교정 {len(repaired)}축: `/` → `·` (원장에도 되쓴다)")
    if args.limit:
        todo = dict(list(todo.items())[:args.limit])
        print(f"  --limit {args.limit} 적용 → {len(todo)}상품")
    if not todo:
        print("처리할 축이 없다.")
        return

    # 2) 상품별로 현재 축 이름을 확인하고 저장한다.
    mcp = OptionMCP()
    mcp.open()
    updates, n_ok, n_skip, n_bad = [], 0, 0, 0
    try:
        for k, (pid, items) in enumerate(sorted(todo.items()), start=1):
            try:
                before = mcp.workdata(pid).get("옵션") or {}
            except Exception as e:  # noqa: BLE001
                for row, gi, _cur, _new in items:
                    updates.append((row, f"보류(조회실패: {str(e)[:100]})"))
                    n_bad += 1
                print(f"  [{k}/{len(todo)}] {pid} 조회 실패: {str(e)[:80]}", file=sys.stderr)
                continue
            dims = before.get("차원") or []
            audit, row_of = [], {}
            for row, gi, cur, new in items:
                live = str(dims[gi].get("이름") or "") if gi < len(dims) else ""
                if not (0 <= gi < len(dims)):
                    updates.append((row, f"보류(차원 {gi} 이 이 상품에 없다)"))
                    n_bad += 1
                elif R.axis_norm(live) == R.axis_norm(new):
                    updates.append((row, AXIS_APPLIED))   # 이미 그 이름이다
                    n_skip += 1
                elif cur and R.axis_norm(live) != R.axis_norm(cur):
                    updates.append((row, f"보류(축이 바뀌었다: 원장 '{cur}' → 현재 '{live}')"[:200]))
                    n_bad += 1
                else:
                    audit.append({"차원": gi, "제안": new})
                    row_of[gi] = row
            if not audit:
                continue

            send, rejects = R.axis_saveable(before, audit)
            for rj in rejects:
                row = row_of.get(rj["차원"])
                if row:
                    updates.append((row, f"보류({rj['사유']})"[:200]))
                    n_bad += 1
            if not send:
                continue
            names = " · ".join(f"{dims[i['groupIndex']].get('이름')}→{i['name']}" for i in send)
            if not args.commit:
                print(f"  [{k}/{len(todo)}] {pid} (미리보기) {names}")
                continue
            try:
                mcp.option_update(pid, renameGroups=send)
                time.sleep(args.sleep)
            except Exception as e:  # noqa: BLE001
                for it in send:
                    updates.append((row_of[it["groupIndex"]],
                                    f"보류(저장실패: {str(e)[:120]})"[:200]))
                    n_bad += 1
                print(f"  [{k}/{len(todo)}] {pid} 저장 실패: {str(e)[:80]}", file=sys.stderr)
                continue

            # 3) 재조회 검증 — 보냈다고 박힌 게 아니다. 검증분만 `반영` 으로 적는다.
            after = mcp.workdata(pid).get("옵션") or {}
            fails = {f["차원"] for f in R.axis_verify(after, send)}
            for f in R.axis_verify(after, send):
                updates.append((row_of[f["차원"]], f"보류(검증실패: {f['사유']})"[:200]))
                n_bad += 1
            for it in send:
                if it["groupIndex"] not in fails:
                    updates.append((row_of[it["groupIndex"]], AXIS_APPLIED))
                    n_ok += 1
            # 스냅샷도 새 축 이름으로 되쓴다 — 안 하면 다음 회차 워커가 옛 축을 보고
            # 같은 제안을 또 낸다(= 이 원장이 다시 부푼다).
            snapshot.update(pid, 옵션=after)
            print(f"  [{k}/{len(todo)}] {pid} 반영 {len(send) - len(fails)}축: {names}")
    finally:
        mcp.close()

    # 4) 원장 되쓰기 — 연속 구간으로 묶어 batchUpdate 한 호출에 싣는다.
    #    행마다 update 하면 쓰기 호출이 행수만큼 나가 분당 쿼터(60)에 즉사한다.
    #    **미리보기 회차는 안 쓴다** — 원장은 실제로 한 일의 기록이지 예정표가 아니다.
    if (updates or repaired) and args.commit:
        ranges = []
        for name, cells in (("상태", updates), ("제안축명", repaired)):
            col = _col_letter(AXIS_HEADER.index(name) + 1)
            ranges += [(f"'{AXIS_TAB}'!{col}{start}:{col}{start + len(block) - 1}", block)
                       for start, block in _row_runs(sorted((r, [v]) for r, v in cells))]
        for _, part in chunk_by_size(ranges, budget=_ARG_BUDGET):
            sheets_batch_update(sheet, part, value_input="USER_ENTERED")
        print(f"  원장 갱신: 상태 {len(updates)}행 · 제안 {len(repaired)}행 "
              f"/ 구간 {len(ranges)}개 → '{AXIS_TAB}'")
    print(f"\n###AXIS### 반영 {n_ok}축 / 이미반영 {n_skip}축 / 보류 {n_bad}축"
          + ("" if args.commit else "  (미리보기 — 저장하려면 --commit)"))


def _commit(sheet, rows, args):
    """분리 저장 — ①이름 → 재조회·검증 → ②포함/제외·대표·순서 → 재조회·검증 6항목.

    이름과 순서를 **한 호출에 넣지 않는다**(쿠팡 옵션 연결 보호). 그래서 2단계다.
    """
    targets = _commit_targets(rows)
    # 재개 — 이미 저장된 상품은 MCP 를 다시 치지 않는다 (2026-08-14 구현).
    # SKILL.md 에는 예전부터 적혀 있었는데 코드에 없었다. 그래서 현황판을 채우려고
    # `--no-sheet` 없이 한 번 더 치면 700건을 처음부터 다시 저장했다(2-2 실측 1시간).
    # `done` 에 실어 두므로 **재실행이 MCP 0회로 현황판만 채운다.**
    committed_path = os.path.join(args.run_dir, "committed.json")
    committed = {} if getattr(args, "ignore_committed", False) else (
        _load(committed_path) if os.path.exists(committed_path) else {})
    if committed:
        targets = [t for t in targets if t[0] not in committed]
        print(f"  재개: 이미 저장 {len(committed)}건 건너뜀 → 남은 {len(targets)}건 "
              f"({os.path.basename(committed_path)})")
    if not targets:
        print("정리대상이 없다." if not committed else "새로 저장할 것이 없다(전건 재개 대상).")
        # 저장할 게 없어도 **현황판·이관은 넘긴다.**
        # - 이관: 상품명 이관은 옵션 저장과 무관한데 여기서 return 하면 전건 보류인
        #   회차(대표충돌이 몰린 회차)의 신호가 통째로 사라진다. 그 회차가 곧 상품명
        #   이상이 가장 많은 회차다(2026-08-06 이룸님).
        # - 현황판: 재개로 전건이 걸러진 회차가 바로 "저장은 끝났는데 현황판이 빈"
        #   상태를 고치러 온 회차다. 여기서 안 쓰면 고치러 온 실행이 아무것도 안 한다.
        if not args.no_matrix:
            try:
                m = matrix.read(sheet)
                if committed:
                    n = matrix.mark_many(sheet, TASK, dict(committed), matrix=m)
                    print(f"  현황판({matrix.TAB}) {TASK}: {n}칸 갱신(재개분)")
                _handoff(sheet, rows, dict(committed), m, args.run_dir)
            except Exception as e:  # noqa: BLE001
                print(f"  [경고] 현황판·이관 실패: {str(e)[:120]}", file=sys.stderr)
        return
    # 저장 직전 상태를 run-dir 에 남긴다(헤르메스 12 단계6 "저장 직전 스냅샷 기록").
    # 스냅샷은 저장 성공 시 새 값으로 덮어쓰므로, 되돌리려면 이 백업이 유일한 원본이다.
    backup_path = os.path.join(args.run_dir, "before_commit.json")
    backup = {pid: (snapshot.load(pid) or {}).get("옵션") or {}
              for pid, _, _, _ in targets}
    # 재개 회차는 **남은 건만** 백업 대상이다. 통째로 덮어쓰면 앞 회차에서 이미 저장된
    # 상품의 원본이 날아가 `restore` 가 그 건들을 못 되돌린다 → 기존 파일에 합친다.
    # (합칠 때 기존 값이 이긴다 — 스냅샷은 저장 성공 시 새 값으로 덮이므로, 지금 읽은
    #  값은 이미 '저장 후' 상태다. 그걸로 덮으면 백업이 원본이 아니게 된다.)
    if os.path.exists(backup_path):
        prev = _load(backup_path) or {}
        merged = dict(backup)
        merged.update(prev)
        backup = merged
    _dump(backup_path, backup)
    print(f"  저장 전 상태 백업: {backup_path} ({len(backup)}건)")
    print(f"  되돌리기: python {os.path.basename(__file__)} restore --run-dir {args.run_dir}")

    mcp = OptionMCP()
    mcp.open()
    done, failed, partial_ids = {}, {}, []
    axis_status, axis_n = {}, 0        # (pid, 차원) → 원장 상태 · 반영 축 수
    # 사람이 `무시`·`반영` 으로 판단해둔 축은 제안에서 뺀다(원장 조회 1회).
    try:
        axis_skip = _axis_ignored(sheet)
    except Exception as e:  # noqa: BLE001
        axis_skip = set()
        print(f"  [경고] 옵션축 판단 조회 실패 — 전 축을 후보로 본다: {str(e)[:120]}",
              file=sys.stderr)
    if axis_skip:
        print(f"  옵션축: 사람이 판단해둔 {len(axis_skip)}축은 건드리지 않는다")
    try:
        for pid, plan, w, st in targets:
            before = backup.get(pid) or {}
            partial = st in PARTIAL_SAVE
            names = _names_to_save(w, before, partial)
            keep = list(plan["유지"])
            drop = [e["id"] for e in plan["제외"]]
            # `excludeSkuIds` 는 MCP 스키마 상한이 200이라, 조합이 많은 상품은 제외 목록만으로
            # 저장이 통째로 막힌다(용쌤1-1 실측: 제외가 200을 넘는 상품 12건).
            # **include/exclude 는 화이트리스트가 아니라 '적용' 이다** — 안 보낸 행은 현재 상태를
            # 유지한다. 그래서 제외를 생략하면 '이미 제외된 행' 만 우연히 맞고, 지금 판매중인
            # 행은 그대로 팔린다(검증이 '판매 포함 초과' 로 잡았다).
            # → 생략하지 말고 **200개씩 나눠 먼저 보낸다.** 마지막 호출에 대표·순서를 싣는다.
            drop_chunks = []
            if len(drop) > 200:
                drop_chunks = [drop[i:i + 200] for i in range(0, len(drop), 200)]
                drop = drop_chunks.pop()      # 마지막 덩어리는 본 호출에 실어 보낸다
            try:
                # ① 이름 먼저 (정렬과 같은 호출 금지)
                if names:
                    items, missing = R.rename_targets(before, names)
                    if missing:
                        raise RuntimeError(f"옵션값을 못 찾았다: {missing[:5]}")
                    # `renameValues` 도 `excludeSkuIds` 와 같은 200개 상한이 걸린다
                    # (2026-08-14 3-2 차광막 297개에서 실측: "한 번에 보낼 수 있는 옵션
                    # 이름 변경은 200개까지입니다"). 상한은 스키마라 나눠 보내는 것 말고는
                    # 방법이 없다 — 옵션이 200을 넘는 상품이 통째로 미저장되던 자리다.
                    name_chunks = [items[i:i + 200] for i in range(0, len(items), 200)]
                    items = name_chunks.pop()   # 마지막 덩어리는 아래 본 호출이 보낸다
                    try:
                        for chunk in name_chunks:
                            mcp.option_update(pid, renameValues=chunk)
                            time.sleep(args.sleep)
                        mcp.option_update(pid, renameValues=items)
                    except RuntimeError as e:
                        # 기존 대표 상태가 무효면(대표행이 2개거나 대표가 판매제외) 불사자는
                        # **이름 변경조차** 거부한다 — "판매중인 새 대표 옵션 ID를 함께
                        # 지정해 주세요". 이름만으로는 못 빠져나오므로 대표·포함/제외를
                        # 같은 호출에 실어 상태를 함께 바로잡는다. 금지 조합은 이름+**순서**뿐이라
                        # 순서만 빼면 된다(용쌤1-2 10건에서 실측·검증).
                        if "대표" not in str(e):
                            raise
                        # 제외가 200을 넘어 나눠 보내야 하는 상품이면 여기서도 앞 덩어리를
                        # 먼저 흘려보내야 한다 — 마지막 덩어리만 실으면 대표 상태가 그대로라
                        # 같은 이유로 또 거부당한다(용쌤1-1 1,000행 상품에서 실측).
                        _promote_main(mcp, pid, plan, args.sleep)
                        for chunk in drop_chunks:
                            mcp.option_update(pid, excludeSkuIds=chunk)
                            time.sleep(args.sleep)
                        drop_chunks = []
                        # 이름이 200을 넘어 나눠야 하는 상품이면 여기서도 앞 덩어리를 먼저
                        # 보낸다 — 대표를 실어야 통과하므로 덩어리마다 같이 싣는다(멱등).
                        for chunk in name_chunks:
                            mcp.option_update(pid, renameValues=chunk,
                                              mainSkuId=plan["대표"],
                                              includeSkuIds=keep, excludeSkuIds=drop)
                            time.sleep(args.sleep)
                        mcp.option_update(pid, renameValues=items, mainSkuId=plan["대표"],
                                          includeSkuIds=keep, excludeSkuIds=drop)
                    time.sleep(args.sleep)
                    mid = mcp.workdata(pid).get("옵션") or {}
                    # 위치 지정 키로 본다 — vid 로 dict 를 만들면 복합옵션에서 차원끼리
                    # vid 가 겹쳐 서로를 덮어써서 검사에서 조용히 빠진다.
                    bad = R.check_names(R.effective_names(mid),
                                        groups=R.pos_groups(mid))
                    if bad["위반"] or bad["중복"]:
                        raise RuntimeError(f"이름 저장 후 검증 실패: {bad}")

                # ②-0 제외가 200을 넘으면 앞 덩어리들을 먼저 흘려보낸다(순서 없이).
                #     순서를 여기 실으면 아직 빼지 않은 행이 순서에 남아 거부당한다.
                #     대표는 **청크를 보내기 전에 먼저 옮겨 둔다**(_promote_main) — 앞 덩어리에
                #     현재 대표행이 섞여 있으면 서버가 "대표를 판매 제외한다"며 통째로 거부한다.
                if drop_chunks:
                    _promote_main(mcp, pid, plan, args.sleep)
                for chunk in drop_chunks:
                    mcp.option_update(pid, excludeSkuIds=chunk)
                    time.sleep(args.sleep)

                # ② 포함/제외 · 대표 · 순서
                mcp.option_update(pid, includeSkuIds=keep, excludeSkuIds=drop,
                                  mainSkuId=plan["대표"], skuOrder=plan["순서"])
                time.sleep(args.sleep)

                # ③ 축(선택 항목) 이름 — 규칙 18. **단독 호출 · 실패해도 상품을 안 죽인다.**
                # 고객이 보는 건 `색상: 블랙` 처럼 축+값이라 값만 고치면 절반만 고친 것이다.
                # 다만 축은 표기고 ②는 무엇을 파느냐라, 축이 거부돼도 ②는 이미 저장됐고
                # 상품은 `완료` 다 — 축만 원장에 `보류(…)` 로 남아 다음에 사람이 본다.
                # 재조회 **앞**에 둔다: 아래 `after` 한 번으로 검증까지 끝난다(추가 조회 0).
                ax_audit = [a for a in (plan.get("축감사") or [])
                            if (pid, str(a.get("차원"))) not in axis_skip]
                ax_items, ax_rej = R.axis_saveable(before, ax_audit)
                for r in ax_rej:
                    axis_status[(pid, str(r["차원"]))] = f"보류({r['사유']})"[:200]
                if ax_items:
                    try:
                        mcp.option_update(pid, renameGroups=ax_items)
                        time.sleep(args.sleep)
                    except Exception as e:  # noqa: BLE001
                        why = f"보류(저장실패: {str(e)[:120]})"
                        for it in ax_items:
                            axis_status[(pid, str(it["groupIndex"]))] = why
                        ax_items = []
                        print(f"    (축 이름 저장 실패 — 옵션은 저장됨: {str(e)[:100]})",
                              file=sys.stderr)

                after = mcp.workdata(pid).get("옵션") or {}
                for f in R.axis_verify(after, ax_items):
                    # 보냈는데 안 박힌 축 — 조용히 '반영'으로 적으면 원장이 거짓이 된다.
                    gi = str(f["차원"])
                    axis_status[(pid, gi)] = f"보류(검증실패: {f['사유']})"[:200]
                    ax_items = [i for i in ax_items if str(i["groupIndex"]) != gi]
                    print(f"    (축 검증 실패: 차원 {gi} — {f['사유']})", file=sys.stderr)
                for it in ax_items:
                    axis_status[(pid, str(it["groupIndex"]))] = AXIS_APPLIED
                    axis_n += 1
                fails = R.verify(before, after, plan, names=names or None)
                if fails:
                    raise RuntimeError("; ".join(fails)[:300])
                snapshot.update(pid, 옵션=after)
                if partial:
                    # 완료가 아니다 — 이름이 남았다. 재작업으로 남겨 다음 회차가 집어간다.
                    done[pid] = matrix.redo_value(PARTIAL_REASON, from_task=TASK)
                    partial_ids.append(pid)
                    print(f"  [부분저장] {pid} 유지 {len(keep)} / 제외 {len(drop)} / "
                          f"대표 {plan['대표']} — 옵션명 미저장(기본형 마커)")
                else:
                    done[pid] = "완료"
                    print(f"  [완료] {pid} 유지 {len(keep)} / 제외 {len(drop)} / 대표 {plan['대표']}")
                # **건별 즉시 기록.** 저장은 되돌리기 어려운 방향이라 "어디까지 했나"를
                # 메모리에만 두지 않는다(catfix `delete_progress.jsonl` 과 같은 이유).
                # 중단돼도 다음 실행이 여기서부터 이어간다.
                committed[pid] = done[pid]
                _dump(committed_path, committed)
            except Exception as e:  # noqa: BLE001
                failed[pid] = f"{type(e).__name__}: {e}"[:200]
                print(f"  [실패] {pid}: {failed[pid]}", file=sys.stderr)
                # **실패해도 스냅샷은 실제 상태로 되맞춘다** (2026-08-14).
                # 저장은 2단계다. ①(이름)이 넘어간 뒤 ②나 검증에서 죽으면 불사자에는
                # 새 이름이 남는데 스냅샷은 옛 이름 그대로다 — 그러면 **다음 회차 prep 이
                # 낡은 상태로 계획을 세워** 이미 옮긴 `기본형` 을 또 옮기려 들고, 살아 있는
                # 옛 마커와 겹쳐 같은 상품이 매 회차 같은 사유로 실패한다.
                # 2-2 실측: 1회차 실패 18건 중 9건이 마커 사유였고 2회차에 4건이 같은
                # 사유로 또 실패했다. 실패분에만 도는 조회 1회라 비용은 무시할 만하다.
                try:
                    live = mcp.workdata(pid).get("옵션") or {}
                    if live:
                        snapshot.update(pid, 옵션=live)
                except Exception as e2:  # noqa: BLE001
                    print(f"    (스냅샷 되맞추기 실패 — 다음 회차가 낡은 값을 본다: "
                          f"{str(e2)[:80]})", file=sys.stderr)
    finally:
        mcp.close()

    # 이번 회차에 새로 저장한 것과 앞 회차 재개분을 합친 게 "지금 저장돼 있는 것"이다.
    # 현황판·이관은 그 전체를 기준으로 찍어야 한다(재개분을 빼면 앞 회차 저장분의
    # 현황판이 영영 안 채워진다 — 이 재개 기능을 만든 이유 그 자체다).
    saved = dict(committed)
    saved.update(done)
    print(f"\n###OPTIONS### 반영 {len(done)}건 / 부분저장 {len(partial_ids)}건 "
          f"/ 실패 {len(failed)}건"
          + (f" (재개분 포함 누적 {len(saved)}건)" if len(saved) != len(done) else ""))
    ax_bad = sum(1 for v in axis_status.values() if v != AXIS_APPLIED)
    if axis_status:
        print(f"  옵션 축 이름(규칙 18): 반영 {axis_n}축 / 보류 {ax_bad}축")
    # 축 원장은 **`--no-sheet` 와 무관하게** 쓴다 — 현황판과 같은 이유다.
    # 실제로 바꿔놓고 원장에 `대기` 로 남기면, 이미 반영된 축을 앱에서 또 손보게 된다.
    # (`--no-sheet` 가 막는 건 미리보기 회차의 원장 쓰기다 — 그건 아래 cmd_apply 에서 건다.)
    if not args.no_matrix:
        try:
            _log_axis_sheet(sheet, rows, status=axis_status)
        except Exception as e:  # noqa: BLE001
            print(f"  [경고] 옵션축 원장 기록 실패: {str(e)[:120]}", file=sys.stderr)
    if partial_ids:
        print(f"  부분저장(옵션명 미저장, 현황판 {TASK} 열 재작업): "
              f"{', '.join(partial_ids[:5])}{' 외 %d건' % (len(partial_ids) - 5) if len(partial_ids) > 5 else ''}")
    # 현황판·이관은 `--no-sheet` 로 막히지 않는다 (2026-08-14 — 위 §현황판 주석 참조).
    if not args.no_matrix:
        vals = dict(saved)
        vals.update({pid: f"보류(저장실패)" for pid in failed})
        try:
            m = matrix.read(sheet)
            n = matrix.mark_many(sheet, TASK, vals, matrix=m)
            print(f"  현황판({matrix.TAB}) {TASK}: {n}칸 갱신")
            _handoff(sheet, rows, saved, m, args.run_dir)
        except Exception as e:  # noqa: BLE001
            print(f"  [경고] 현황판 갱신 실패: {str(e)[:120]}", file=sys.stderr)


# 저장 성공 여부와 **무관하게** 넘기는 단계 (2026-08-06 이룸님).
#
# 종전엔 `done`(저장 성공)만 넘겼다. 썸네일 이관은 그게 맞다 — 대표가 확정돼야 대조할
# 대상이 생긴다. 그런데 **상품명 이관은 옵션 저장과 무관**하고, 하필 상품명 이상이 가장
# 잘 보이는 자리가 `보류(대표충돌)`(상품명이 규격어로 지정한 대표를 워커가 본품이 아니라고
# 뺀 상태)이다. 저장이 안 된다는 이유로 그 신호를 통째로 버리고 있었다.
HANDOFF_ALWAYS = ("상품명",)


TASK_THUMB = "썸네일"      # 현황판에서 되찍을 상대 열
# 썸네일이 "대표옵션 쪽이 뿌리다"라며 되돌릴 때 쓰는 낱말 2종(`thumb_rules.TO_OPTION_VERDICTS`).
# **둘은 뿌리가 다르다** — 아래 `_recover_orphans` 가 이 차이로 갈래를 나눈다.
NO_BASE_IMAGE = "기준이미지없음"   # 대표옵션 이미지가 비제품(도면·배너) = 기준이 아예 없다
MAIN_SUSPECT = "대표옵션의심"      # 대표옵션 이미지는 실물인데 그게 본품이냐가 쟁점이다
FROM_THUMB_MARKS = (NO_BASE_IMAGE, MAIN_SUSPECT)
# 그 되돌림을 **끝내는** 낱말(`thumb_rules.NO_REAL_BASE`). 이게 붙어 가면 썸네일 prep 이
# 선기록하지 않고 비전 배치로 보내, 워커가 후보 이미지에서 직접 고른다.
NO_REAL_BASE = "실물기준없음"


def _close_roundtrip(reason, redo_reason):
    """썸네일로 되돌려 보내는 사유에 `실물기준없음` 을 강제로 붙여야 하는가.

    **왜 필요한가** (2026-08-15 용쌤2-1 §9): 옵션 57건을 고쳐 31건을 썸네일로 돌려보냈는데
    2회전에서 `대표옵션의심` 8건 · `기준이미지없음` 1건이 **또** 나왔다. 옵션 이미지가
    전부 배너·풀세트·도면인 상품이 실재해서, 옵션이 대표를 몇 번 다시 세워도 썸네일이
    같은 이유로 또 되돌린다 — 무한 왕복이다.

    끊는 낱말(`실물기준없음`)은 이미 있고 워커 프롬프트(§2-10)도 그걸 넣으라고 시킨다.
    그런데 **워커가 안 붙였다** — 잘린 productId 와 같은 부류의 지시 불이행이라
    지시문으로는 안 막힌다. 그래서 왕복 2회차부터는 코드가 붙인다.

    판정 근거는 `재작업사유`(썸네일이 현황판에 찍어 배치에 실려 온 값)다. 그게 이미
    썸네일발 되돌림이면 **이번이 최소 2회차** — 옵션이 한 번 손보고 넘긴 걸 썸네일이
    거절했다는 뜻이다. 이때 붙여도 손해가 없다: 썸네일이 후보에서 고르는 경로로 갈 뿐,
    크레딧도 안 들고 새로 세운 대표도 후보에 그대로 들어 있다.
    """
    if NO_REAL_BASE in str(reason or ""):
        return False
    return any(k in str(redo_reason or "") for k in FROM_THUMB_MARKS)


def _prev_main(bp):
    """배치에 실린 **저장 전 대표** 판매행 id (없으면 None)."""
    for r in (bp or {}).get("판매행") or []:
        if r.get("현재대표"):
            return str(r.get("id"))
    return None


def _recover_orphans(rows, done, m, bprod, by_task):
    """옵션이 저장했는데 **워커가 이관을 안 남긴** 건을 썸네일로 되돌려 보낸다.

    **왜 필요한가 — 썸네일 보류는 미아가 된다** (2026-08-15 용쌤2-1 3회차 실측).
    썸네일 `prep` 의 대상은 현황판 썸네일 열의 **빈칸 + 재작업**(`matrix.pending`)이라
    `보류(...)` 는 안 집는다. 그런데 옵션정리는 워커가 `이관` 을 남길 때만 썸네일 열을
    되찍는다 — 대표가 이미 맞다고 판단하면 아무것도 안 찍는다. 그 결과 옵션이 48건을
    저장했는데 썸네일로 배턴이 간 건 20건뿐이고 **26건이 `보류` 인 채 어느 축도 안 집는
    상태**로 남았다(옵션이 아예 안 건드린 보류까지 더해 51건). 에러도 경고도 없다.

    여기서 되찍으면 `보류` 가 `재작업` 이 되어 다음 썸네일 `prep` 이 자동으로 집는다.

    **세 갈래로 나눠 보낸다** — 안 나누면 왕복이 그대로 또 돌거나, 멀쩡한 기준을 버린다:

    | 대표가 | 원래 보류가 | 보내는 값 | 왜 |
    |---|---|---|---|
    | 바뀌었다 | (무관) | 재판단 | 기준이 실제로 달라졌으니 대조하면 풀릴 수 있다 |
    | 그대로다 | `기준이미지없음` | **`실물기준없음`** | 대표옵션 이미지가 비제품인데 옵션이 못 고쳤다 = 기준이 아예 없다. 후보에서 직접 고르게 해 왕복을 끝낸다 |
    | 그대로다 | `대표옵션의심` | 재판단 | **대표옵션 이미지는 실물이다.** 쟁점은 "그게 본품이냐"였고 옵션이 "맞다"고 확인했다 — 그 이미지를 기준으로 대조해야 풀린다 |

    **셋째 줄이 처음엔 빠져 있었다** (2026-08-17 실측으로 갈랐다). 대표가 안 바뀌면 전부
    `실물기준없음` 으로 닫았는데, 그러면 `prep` 이 **멀쩡한 대표옵션 기준을 빼버린다.**
    실내분수가 그 사례다 — 대표옵션은 흰색 연꽃형 3단 분수라는 **또렷한 실물 사진**인데
    기준에서 빠졌고, 워커가 후보(전부 파란색)에서 고를 수밖에 없어 파란 계단형이 나왔다.
    원래 문제(대표옵션과 대표 썸네일의 색·형태 불일치)가 **그대로 남고 크레딧만 나갔다.**
    "대표가 안 바뀐 것"과 "기준이 없는 것"은 다른 얘기다.
    """
    fresh, closed = {}, {}
    for pid, plan, _w, _st in rows:
        if pid not in done or pid in by_task.get("썸네일", {}):
            continue
        cur = ((m.get(pid) or {}).get(TASK_THUMB) or "").strip()
        if not cur.startswith("보류"):
            continue          # 완료·빈칸·재작업은 이미 제 갈 길이 있다
        mark = next((k for k in FROM_THUMB_MARKS if k in cur), None)
        if not mark:
            continue          # 보류(생성실패)·보류(주의) 등은 옵션이 풀 수 있는 게 아니다
        prev, new = _prev_main(bprod.get(pid)), str((plan or {}).get("대표") or "")
        if new and prev and new != prev:
            fresh[pid] = f"대표 재지정 완료 — 재판단({mark})"
        elif mark == NO_BASE_IMAGE:
            closed[pid] = f"{NO_REAL_BASE}: 대표 확인 완료(변경 없음) — 재판단({mark})"
        else:
            fresh[pid] = f"대표 확인 완료(변경 없음) — 재판단({mark})"
    if fresh or closed:
        by_task.setdefault("썸네일", {}).update({**fresh, **closed})
        print(f"  [미아회수] 썸네일 보류 {len(fresh) + len(closed)}건을 되찍었다 — "
              f"대표 바뀜 {len(fresh)}건(재판단) · 대표 그대로 {len(closed)}건"
              f"('{NO_REAL_BASE}' 로 종결)")


def _handoff(sheet, rows, done, m, run_dir=""):
    """워커가 남긴 `이관` 을 다른 단계의 현황판 칸으로 넘긴다.

    옵션을 보다 보면 옵션 범위 **밖**의 문제가 보인다 — 썸네일에 없는 색, 상품명 오표기.
    전에는 이걸 자유 텍스트 메모로만 남겨서 받는 쪽이 읽을 경로가 없었다
    (파일럿 5건 중 3건이 그렇게 유실됐다). 이제 현황판 칸으로 넘겨
    받는 단계가 `pending(..., include_redo=True)` 로 한꺼번에 집어간다.
    상품명은 원장이 `상품명` 탭이라 prep 이 현황판 재작업을 따로 편입한다(`_matrix_redo`).

    결과 JSON 형식:  "이관": [{"단계": "썸네일", "사유": "대표색 불일치"}]
    """
    by_task = {}
    # 최저가 동률로 원본 순서 대표를 세운 건은 **썸네일 쪽에 알린다** (2026-08-07 이룸님).
    # 대표를 무엇으로 정하든 상관없되 "썸네일이 그 대표옵션과 같은 물건"이면 되므로,
    # 판단을 사람에게 올리지 않고 썸네일 단계가 대표옵션 이미지를 기준으로 맞추게 넘긴다.
    for pid, plan, _w, _st in rows:
        if pid not in done or not plan:
            continue
        tie = next((str(x) for x in (plan.get("경고") or [])
                    if str(x).startswith("최저가 동률")), None)
        if tie:
            by_task.setdefault("썸네일", {}).setdefault(
                pid, f"대표 동률로 원본 순서 지정 — 썸네일을 대표옵션과 맞출 것({tie[:40]})")
    bprod = _batch_products(run_dir) if run_dir else {}
    closed = []
    for pid, _plan, w, _st in rows:
        for h in (w.get("이관") or []):
            if pid not in done and (h.get("단계") or "").strip() not in HANDOFF_ALWAYS:
                continue          # 저장 못 한 건의 옵션-의존 이관은 넘기지 않는다
            task, reason = (h.get("단계") or "").strip(), (h.get("사유") or "").strip()
            if task not in matrix.TASKS or not reason:
                print(f"  [경고] 이관 무시({pid}): 단계 '{task}'")
                continue
            # 왕복 2회차인데 워커가 끊는 낱말을 안 붙였으면 코드가 붙인다(`_close_roundtrip`).
            if task == "썸네일" and _close_roundtrip(
                    reason, (bprod.get(pid) or {}).get("재작업사유")):
                reason = f"{NO_REAL_BASE}: {reason}"[:200]
                closed.append(pid)
            by_task.setdefault(task, {})[pid] = reason
    if closed:
        print(f"  [왕복종결] 썸네일이 이미 되돌린 건 {len(closed)}건에 "
              f"'{NO_REAL_BASE}' 를 붙였다 — 썸네일이 후보에서 직접 고른다: {closed[:5]}")
    _recover_orphans(rows, done, m, bprod, by_task)
    for task, items in by_task.items():
        k = matrix.flag_many(sheet, task, items, from_task=TASK, matrix=m)
        print(f"  {task} 재작업 표시: {k}건")


def cmd_restore(args):
    """`before_commit.json` 으로 저장 전 상태를 되돌린다.

    이름 → 포함/제외·대표·순서 순서로 되돌리되, **이름과 순서는 같은 호출에 넣지 않는다**
    (저장 때와 같은 제약). 완전 복구는 백업이 있을 때만 가능하다.
    """
    path = os.path.join(os.path.abspath(args.run_dir), "before_commit.json")
    if not os.path.exists(path):
        print(f"백업이 없다: {path} — 되돌릴 수 없다.")
        return
    backup = _load(path)
    only = set(args.ids or ())
    mcp = OptionMCP()
    mcp.open()
    ok, bad = 0, {}
    try:
        for pid, before in backup.items():
            if only and pid not in only:
                continue
            rows = before.get("판매행") or []
            if not rows:
                bad[pid] = "백업에 판매행이 없다"
                continue
            try:
                names = {str(v.get("vid")): v.get("name")
                         for d in (before.get("차원") or [])
                         for v in (d.get("values") or []) if v.get("name")}
                if names:
                    items, _ = R.rename_targets(before, names)
                    if items:
                        mcp.option_update(pid, renameValues=items)
                        time.sleep(args.sleep)
                keep = [r["id"] for r in rows if not r.get("exclude")]
                drop = [r["id"] for r in rows if r.get("exclude")]
                main_id = next((r["id"] for r in rows if r.get("main_product")), None)
                mcp.option_update(pid, includeSkuIds=keep, excludeSkuIds=drop,
                                  mainSkuId=main_id,
                                  skuOrder=[r["id"] for r in rows])
                time.sleep(args.sleep)
                # 축(선택 항목) 이름도 되돌린다 (2026-08-17 — 축 저장이 생기면서 같이 들어왔다).
                # 이게 없으면 값·판매구성만 옛것으로 가고 축 이름만 새것으로 남아,
                # 되돌렸다고 믿는 상품이 실제로는 어느 회차와도 다른 상태가 된다.
                groups = [{"groupIndex": gi, "name": str(d.get("이름") or "").strip()}
                          for gi, d in enumerate(before.get("차원") or [])
                          if str(d.get("이름") or "").strip()]
                if groups:
                    try:
                        mcp.option_update(pid, renameGroups=groups)
                        time.sleep(args.sleep)
                    except Exception as e:  # noqa: BLE001
                        # 축 복구 실패로 상품 복구 전체를 실패로 적지 않는다 —
                        # 판매 구성은 이미 되돌아갔고, 남은 건 표기뿐이다.
                        print(f"    (축 이름 복구 실패 — 옵션은 복구됨: {str(e)[:100]})",
                              file=sys.stderr)
                snapshot.update(pid, 옵션=mcp.workdata(pid).get("옵션") or {})
                ok += 1
                print(f"  [복구] {pid}")
            except Exception as e:  # noqa: BLE001
                bad[pid] = f"{type(e).__name__}: {e}"[:200]
                print(f"  [실패] {pid}: {bad[pid]}", file=sys.stderr)
    finally:
        mcp.close()
    print(f"\n###RESTORE### 복구 {ok}건 / 실패 {len(bad)}건")


def main():
    ap = argparse.ArgumentParser(description="불사자 옵션 정리")
    sub = ap.add_subparsers(dest="cmd", required=True)

    # 하위 명령 뒤에 써도 먹히게 각 파서에 붙인다(`prep --group-name ...`).
    def _common(x):
        x.add_argument("--sheet", default="", help="그룹 시트 id(직접 지정)")
        x.add_argument("--group-name", default="", help="마켓그룹명 (예: 1번_용쌤1-1)")

    p = sub.add_parser("prep", help="대상 확정 → 스냅샷 → 이미지 → 배치")
    _common(p)
    p.add_argument("--run-dir", required=True)
    p.add_argument("--ids", nargs="+", default=None)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    p.add_argument("--sleep", type=float, default=0.3)
    p.add_argument("--skip-thumbs", action="store_true")
    p.add_argument("--max-option-images", type=int, default=12,
                   help="차원당 내려받을 옵션 이미지 수(전 옵션이 필요하면 늘려라)")
    p.add_argument("--max-px", type=int, default=MAX_PX,
                   help=f"이미지를 긴 변 N px 로 축소(0=원본 유지). 기본 {MAX_PX}. "
                        "비전 토큰 ∝ 픽셀수")
    p.set_defaults(func=cmd_prep)

    q = sub.add_parser("pending", help="results 없는 배치를 Workflow args JSON 으로 출력")
    q.add_argument("--run-dir", required=True)
    q.set_defaults(func=cmd_pending)

    a = sub.add_parser("apply", help="계산·검증 → 시트 → (승인 후) 저장")
    _common(a)
    a.add_argument("--run-dir", required=True)
    a.add_argument("--ids", nargs="+", default=None,
                   help="이 상품들만 처리(부분 재시도). 없으면 results 전체")
    a.add_argument("--commit", action="store_true", help="실제 저장(없으면 미리보기)")
    a.add_argument("--allow-missing", action="store_true",
                   help="감사에서 누락 상품이 있어도 --commit 강행(의도된 부분 처리)")
    a.add_argument("--emit", default="", help="계획 요약 JSON 저장 경로(세로 러너 신호 판정용)")
    a.add_argument("--no-sheet", action="store_true",
                   help="**원장 탭(`옵션`·`옵션축`)만** 안 쓴다. 현황판·이관은 그대로 나간다 "
                        "— 그 둘까지 막으려면 --no-matrix (2026-08-14)")
    a.add_argument("--no-matrix", action="store_true",
                   help="현황판(00_진행)·이관 flag 를 쓰지 않는다(검증·재현용). "
                        "평상시 쓰지 마라 — 저장은 됐는데 다음 회차가 같은 상품을 또 집는다")
    a.add_argument("--ignore-committed", action="store_true",
                   help="committed.json 을 무시하고 전건 다시 저장한다(멱등이라 안전)")
    a.add_argument("--no-review", action="store_true",
                   help="검수표(옵션명 대조·순서·제외)를 찍지 않는다")
    a.add_argument("--sleep", type=float, default=0.5)
    a.set_defaults(func=cmd_apply)

    x = sub.add_parser("axis", help="`옵션축` 탭의 대기 축을 실제로 저장한다(규칙 18)")
    _common(x)
    x.add_argument("--ids", nargs="+", default=None, help="이 상품들만")
    x.add_argument("--limit", type=int, default=0, help="상품 N건만(파일럿용)")
    x.add_argument("--commit", action="store_true", help="실제 저장(없으면 미리보기)")
    x.add_argument("--sleep", type=float, default=0.5)
    x.set_defaults(func=cmd_axis)

    s = sub.add_parser("restore", help="저장 전 상태로 되돌린다(before_commit.json 필요)")
    _common(s)
    s.add_argument("--run-dir", required=True)
    s.add_argument("--ids", nargs="+", default=None, help="일부만 되돌릴 때")
    s.add_argument("--sleep", type=float, default=0.5)
    s.set_defaults(func=cmd_restore)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
