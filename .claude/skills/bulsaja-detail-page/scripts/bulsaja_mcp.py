#!/usr/bin/env python3
"""
불사자 원격 HTTP MCP 직접 호출 클라이언트 (대화 밖 대량처리용).

불사자 MCP는 로컬이 아니라 원격 Streamable HTTP MCP 서버다
(url + Bearer 토큰이 ~/.claude.json 의 mcpServers.bulsaja 에 있음).
따라서 무거운 도구(workdata ~40KB/건, category 후보/저장)를 파이썬에서
JSON-RPC 로 직접 호출하면, 응답을 스크립트 안에서 소비하고 요약만 남겨
Claude 대화 컨텍스트를 태우지 않고 수백~수천 건을 처리할 수 있다.

보안: Bearer 토큰은 하드코딩하지 않고 ~/.claude.json 에서 런타임 로드한다.
      토큰 값은 절대 stdout/로그로 출력하지 않는다.

서브커맨드:
  probe                      initialize→initialized→tools/list. 실동작 1순위 검증.
  workdata --input a.json    productId 목록 → 현재 카테고리 + 정체증거 4종 요약(경량)
  match ...                  (다음 단계에서 구현)
  save ...                   (다음 단계에서 구현)

사용법:
  python bulsaja_mcp.py probe
  python bulsaja_mcp.py probe --tool bulsaja_product_workdata --args '{"productId":"UB.."}'
"""
import argparse
import json
import os
import sys
import time
import urllib.parse

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# eroomlib 로드: 상위로 `.claude` 앵커(= lib/eroomlib)를 찾아 lib 를 1회 insert.
_d = SCRIPT_DIR
while _d and _d != os.path.dirname(_d):
    _lib = os.path.join(_d, "lib")
    if os.path.isdir(os.path.join(_lib, "eroomlib")):
        if _lib not in sys.path:
            sys.path.insert(0, _lib)
        break
    _d = os.path.dirname(_d)

from eroomlib import snapshot  # 공용 상품 스냅샷(workdata 캐시)  # noqa: E402
from eroomlib.snapshot import ProductMCP as _BaseMCP  # transport + workdata  # noqa: E402
# '이미 끝난 행' 정의는 eroomlib.matrix 한 곳에만 둔다 — 여기서 다시 나열하면 두 벌이 어긋난다.
from eroomlib.matrix import CATFIX_DONE, DELETED_PREFIX  # noqa: E402


class BulsajaMCP(_BaseMCP):
    """불사자 MCP — transport(open/list_tools/call_tool/close)는 eroomlib.bulsaja,
    `workdata` 등 상품 공통 조회는 eroomlib.snapshot.ProductMCP 에서 상속하고,
    여기서는 카테고리 교정 **고유 도구**(category_preview/category_commit)만 얹는다.
    """

    def category_preview(self, product_id, keyword):
        """confirm=False 로 저장 미리보기. 저장하지 않고 '지정될카테고리'+토큰 반환.
        반환: {ok, ss_name, token, message, 지정될카테고리}
        """
        r = self.call_tool("bulsaja_product_category",
                           {"productId": product_id, "keyword": keyword,
                            "confirm": False})
        target = r.get("지정될카테고리") or {}
        ss = target.get("ss_category") or {}
        return {
            "ok": bool(r.get("confirmationToken")),
            "ss_name": ss.get("name") or "",
            "ss_code": ss.get("code") or "",
            "token": r.get("confirmationToken") or "",
            "message": r.get("message") or "",
            "지정될카테고리": target,
        }

    def category_commit(self, product_id, keyword, token):
        """confirm=True + 토큰으로 실제 저장(전 마켓 동시 반영, 멱등)."""
        r = self.call_tool("bulsaja_product_category",
                           {"productId": product_id, "keyword": keyword,
                            "confirm": True, "confirmationToken": token})
        return {"success": bool(r.get("success")), "raw_message": r.get("message", "")}

    # close()·open()·call_tool()·workdata() 는 _BaseMCP(eroomlib.snapshot.ProductMCP) 에서 상속.
    # workdata 와 옵션 증거 추출(_sku_evidence)은 스킬 2개 이상이 쓰므로 eroomlib 로 옮겼다.


def _norm_path(p):
    """카테고리 경로 정규화: '>' 주변 공백 제거해 셀하/불사자 경로 비교 가능하게.
    (셀하 '생활/건강 > 공구 > 농기계' ↔ 불사자 '생활/건강>공구>농기계')
    """
    if not p:
        return ""
    return ">".join(seg.strip() for seg in str(p).split(">"))


def is_already_correct(prev_path, target_path):
    """이전 카테고리 == 조회 카테고리(정규화 비교) → 저장할 게 없다.

    한쪽이라도 비어 있으면 '같다'로 보지 않는다('미설정' 상품이 전부 이미정확이 되면 안 됨).
    """
    a, b = _norm_path(prev_path), _norm_path(target_path)
    return bool(a) and bool(b) and a == b


def is_done_status(status):
    """시트 G열 값이 '이미 끝난 행'인가.

    Step 1(collect_targets)의 재개 규칙과 apply 의 원장 보호가 **같은 정의**를 쓰게 한다.
    `저장완료`/`자동저장완료`/`이미정확` + `상품삭제…`(상품이 사라진 행).
    """
    s = (status or "").strip()
    return bool(s) and (s in CATFIX_DONE or s.startswith(DELETED_PREFIX))


def rows_to_skip(statuses, resume_all=False, force=False):
    """{시트행: G열상태} → 이번 apply 가 건드리면 안 되는 행 집합.

    - 기본: 완료 상태만 보호(저장완료·자동저장완료·이미정확·상품삭제*)
    - resume_all(--resume-sheet): 상태가 있기만 하면 전부 스킵(중단 후 이어달리기)
    - force(--force): 아무것도 스킵하지 않는다(예전 전건 덮어쓰기 동작)
    """
    if force:
        return set()
    if resume_all:
        return {r for r, v in statuses.items() if (v or "").strip()}
    return {r for r, v in statuses.items() if is_done_status(v)}


def _read_status_col(spreadsheet_id, tab, max_row):
    """시트 G열(상태)을 1회 읽어 {행번호: 상태}. 헤더가 1행이라 2행부터."""
    from eroomlib.gsheets import sheets_get
    if not max_row or max_row < 2:
        return {}
    rows = sheets_get(spreadsheet_id, f"{tab}!G2:G{max_row}")
    return {i + 2: ((r[0] or "").strip() if r else "") for i, r in enumerate(rows)}


# ---- CLI ------------------------------------------------------------
def cmd_probe(args):
    mcp = BulsajaMCP()
    init = mcp.open()
    print("=== initialize OK ===")
    print("  protocolVersion:", init.get("protocolVersion"))
    si = init.get("serverInfo", {})
    print("  serverInfo:", si.get("name"), si.get("version"))
    print("  session_id_present:", bool(mcp.session_id))
    tools = mcp.list_tools()
    names = [t.get("name") for t in tools]
    print(f"=== tools/list OK ({len(names)}개) ===")
    for n in names:
        print("  -", n)
    for need in ("bulsaja_product_workdata", "bulsaja_product_category"):
        print(f"  [{'OK' if need in names else 'MISSING'}] {need}")

    if args.tool:
        arguments = json.loads(args.args) if args.args else {}
        print(f"\n=== call_tool: {args.tool} args={arguments} ===")
        out = mcp.call_tool(args.tool, arguments)
        s = json.dumps(out, ensure_ascii=False)
        print("  (응답 요약, 앞 800자)")
        print("  " + s[:800])
        print(f"  ... [전체 {len(s)}자]")
    mcp.close()


def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _dump_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def cmd_workdata(args):
    """targets.json([{productId,..}]) → 현재 카테고리+썸네일 요약(workdata.json).
    무거운 workdata 응답을 대화 밖에서 소비하고 경량 요약만 남긴다.

    실제 조회는 **공용 스냅샷**(eroomlib.snapshot)이 한다 — 이미 다른 스킬이 받아둔
    상품이면 MCP 를 타지 않는다. 출력 형식은 종전과 동일.
    """
    targets = _load_json(args.input)
    pids = [t.get("productId") or t.get("id") for t in targets]
    recs, errors = snapshot.ensure(pids, refresh=args.refresh,
                                   sleep=args.sleep, mode=args.mode)
    out = []
    for t in targets:
        pid = t.get("productId") or t.get("id")
        rec = {"productId": pid, "row": t.get("row")}
        got = recs.get(pid)
        if got is not None:
            wd = snapshot.as_workdata(got)
            if not wd.get("상품명"):
                wd["상품명"] = t.get("상품명", "")  # 시트 값 fallback
            rec.update(wd)
        else:
            rec["상품명"] = t.get("상품명", "")
            rec["원문명"] = ""
            rec["옵션명"] = []
            rec["옵션명원문"] = []
            rec["옵션이미지"] = []
            rec["기존카테고리"] = "미설정"
            rec["썸네일"] = []
            rec["error"] = errors.get(pid, "조회 실패")
        out.append(rec)
    _dump_json(args.output, out)
    ok = sum(1 for r in out if not r.get("error"))
    print(f"###WORKDATA### {ok}/{len(out)} OK -> {args.output}")


def _run_gate(args, decisions, m):
    """제외카테고리 붙박이 게이트 — 확정분만 태우고 걸린 상품id 집합을 돌려준다.

    **태우는 건 `CATFIX_DONE` 3종뿐이다**(여기서는 `자동저장완료`·`이미정확`).
    `변경대상`·`매칭불가`·`부분일치확인요`·`보류(정체불명)` 같은 의심 건은 삭제하지
    않는다(2026-08-08 이룸님) — 어차피 재교정을 돌게 되어 있고 거기서 확정되면 그때
    걸린다. 스스로 풀린다.

    **실패해도 저장을 되돌리지 않는다.** 여기 도달한 시점에 불사자 저장·시트 원장은
    이미 끝났다. 블랙리스트를 못 읽었다고 죽이면 잃는 게 더 크고, 못 잡은 재고는
    `category_gate.py scan` 이 나중에 통째로 훑는다(그 스캔이 존재하는 이유 그대로).
    다만 조용히 넘어가지는 않는다 — 경고를 남긴다.
    """
    recs = [{"productId": d.get("productId"), "상품명": d.get("상품명", ""),
             "카테고리": d.get("변경카테고리") or "", "상태": d.get("상태", "")}
            for d in decisions
            if d.get("productId") and d.get("상태") in CATFIX_DONE]
    if not recs:
        return set()
    try:
        sys.path.insert(0, SCRIPT_DIR)
        import category_gate  # noqa: E402  (같은 스킬 폴더)
        # 게이트 산출물은 catfix run-dir 아래 `gate/` 로 간다. run-dir = decisions.json 의
        # 자리다(run_all 이 그렇게 넘긴다). --output 이 딴 데면 큐 없이 시트 표시만 하고,
        # 그건 `retry` 가 잡는다.
        run_dir = os.path.dirname(os.path.abspath(args.output)) or None
        targets, _stats = category_gate.gate_records(
            args.sheet, recs, run_dir=run_dir, m=m)
        return {t["productId"] for t in targets}
    except Exception as e:  # noqa: BLE001
        print(f"  [경고] 제외카테고리 게이트 실패: {type(e).__name__}: {str(e)[:140]}\n"
              "    저장은 정상이다. 놓친 건은 `category_gate.py scan` 으로 훑는다.",
              file=sys.stderr)
        return set()


def cmd_apply(args):
    """match + save 를 상품별 1패스로 처리(토큰 신선도 유지 + 건건 체크포인트).

    각 상품: category_preview(confirm=False) → 지정 ss 경로를 셀하 경로와 비교 →
      - 정확일치 & 확신도≥임계 → (실행모드면) category_commit 저장 → 상태=자동저장완료
      - 정확일치 & 확신도<임계 → 상태=변경대상(수동)
      - 최종차수 같고 상위경로 다름 → 부분일치확인요
      - 후보없음/토큰없음 → 매칭불가
    입력: merged.json [{productId, 상품명, row, 기존카테고리, 검색어, sellha경로, 최종차수, 확신도, sellha상태}]
    """
    items = _load_json(args.input)
    sheet = None
    if args.sheet and not args.no_sheet:
        sys.path.insert(0, SCRIPT_DIR)
        import sheet_log  # noqa
        sheet = sheet_log.SheetLogger(args.sheet)

    # 시트 원장 보호(+재개): G열(상태)을 1회 읽어 건드리면 안 되는 행을 뺀다.
    # ★2026-08-04 결함: apply 는 decisions 전건의 B:K 를 무조건 덮어썼다. decisions 는
    #   조회 결과 기준이라 후처리(steer·근접저장·consensus)로 `저장완료`가 된 행을
    #   `매칭불가`로 되돌린다. 불사자 저장은 멀쩡한데 원장만 거짓이 되므로 재개 판단·
    #   상품명 연계가 전부 틀어진다. Step 1 의 재개 규칙을 apply 에도 적용해 막는다.
    if sheet and items and not args.force:
        max_row = max((it.get("row") or 0) for it in items)
        try:
            statuses = _read_status_col(args.sheet, sheet.tab, max_row)
        except Exception as e:  # noqa: BLE001
            # 조용히 진행하면 원장을 덮어쓴다 — 못 읽으면 아예 하지 않는다.
            print(f"[중단] 시트 상태열 조회 실패: {str(e)[:200]}", file=sys.stderr)
            print("  강행하려면 --force(전건 덮어쓰기) 또는 --no-sheet", file=sys.stderr)
            sys.exit(4)
        skip = rows_to_skip(statuses, resume_all=args.resume_sheet, force=args.force)
        if skip:
            before = len(items)
            items = [it for it in items if it.get("row") not in skip]
            kinds = sorted({statuses.get(r, "") for r in skip} - {""})
            print(f"[apply] 시트 기저장 {before - len(items)}건 건너뜀 "
                  f"({'·'.join(kinds)[:120]}) → 남은 {len(items)}건. 덮어쓰려면 --force")
    elif args.force:
        print("[apply] --force: 시트 상태 무시하고 전건 덮어쓴다")

    if args.limit and args.limit > 0:
        items = items[:args.limit]
        print(f"[limit] 이번 실행 {len(items)}건만 처리")

    mcp = BulsajaMCP()
    mcp.open()
    decisions = []
    stats = {"자동저장완료": 0, "변경대상": 0, "부분일치확인요": 0,
             "매칭불가": 0, "sellha조회실패": 0, "보류(정체불명)": 0,
             "MCP오류": 0, "이미정확": 0}
    for i, it in enumerate(items, 1):
        pid = it.get("productId")
        keyword = it.get("최종차수") or ""
        conf = _to_float(it.get("확신도"))
        sell_path = _norm_path(it.get("sellha경로") or "")
        d = {
            "productId": pid, "상품명": it.get("상품명", ""), "row": it.get("row"),
            "기존카테고리": it.get("기존카테고리", ""), "검색어": it.get("검색어", ""),
            "확신도": it.get("확신도", ""), "변경카테고리": "", "상태": "", "token": "",
            # 시트 J·K열 — 상품명 스킬이 재활용한다(썸네일 재판독 생략용)
            "실물판정": it.get("실물판정", ""), "썸네일": it.get("썸네일", ""),
        }
        try:
            if (it.get("sellha상태") or "") == "보류(정체불명)":
                # 1바퀴에서 정체 판별 실패 → 셀하를 태우지 않고 2바퀴 큐로 넘긴 건
                d["상태"] = "보류(정체불명)"
            elif (it.get("sellha상태") or "") not in ("성공", "") or not keyword:
                d["상태"] = "sellha조회실패"
            elif is_already_correct(it.get("기존카테고리"), sell_path):
                # 이전 == 조회 카테고리 → 저장할 게 없다. preview·commit 둘 다 태우지 않는다.
                # (확신도와 무관: 어느 쪽이든 카테고리는 그대로다. 상태표 정의 그대로)
                d["상태"] = "이미정확"
                d["변경카테고리"] = it.get("기존카테고리", "")
            else:
                pv = mcp.category_preview(pid, keyword)
                applied = _norm_path(pv["ss_name"])
                d["변경카테고리"] = pv["ss_name"]
                d["token"] = pv["token"]
                if not applied or not pv["token"]:
                    d["상태"] = "매칭불가"
                    d["변경카테고리"] = ""  # 후보 없음 — 오해 방지 위해 비움
                elif applied != sell_path and applied.split(">")[-1] != sell_path.split(">")[-1]:
                    # 최종차수도 다름 = 불사자가 엉뚱하게 매칭 → 거부. 셀하 경로만 참고로.
                    d["상태"] = "매칭불가"
                    d["변경카테고리"] = ""
                    d["참고_셀하경로"] = it.get("sellha경로", "")
                elif applied == sell_path:
                    # 정확일치
                    if conf is not None and conf >= args.threshold:
                        if args.dry_run:
                            d["상태"] = "변경대상"  # 커밋 안 함(미리보기만)
                        else:
                            cm = mcp.category_commit(pid, keyword, pv["token"])
                            d["상태"] = "자동저장완료" if cm["success"] else "변경대상"
                            if cm["success"]:
                                # 저장한 쪽이 스냅샷의 그 필드만 되쓴다 → 다른 스킬이
                                # 옛 카테고리를 읽는 일이 없다(재조회·TTL 불필요).
                                snapshot.update(pid, 기존카테고리=pv["ss_name"])
                    else:
                        d["상태"] = "변경대상"
                elif applied.split(">")[-1] == sell_path.split(">")[-1]:
                    d["상태"] = "부분일치확인요"
                else:
                    d["상태"] = "매칭불가"
        except Exception as e:
            d["상태"] = "MCP오류"
            d["error"] = f"{type(e).__name__}: {e}"[:200]
        # 위험 플래그: 대분류(첫 차수)가 바뀌는 변경 = 나중에 우선 검토용
        prev, new = d.get("기존카테고리", ""), d.get("변경카테고리", "")
        if (d["상태"] in ("변경대상", "자동저장완료") and prev and new
                and prev not in ("미설정",)
                and _norm_path(prev).split(">")[0] != _norm_path(new).split(">")[0]):
            d["위험"] = "대분류변경"
        else:
            d["위험"] = ""
        stats[d["상태"]] = stats.get(d["상태"], 0) + 1
        decisions.append(d)
        if sheet and d.get("row"):
            try:
                sheet.update_row(d["row"], d)
            except Exception as e:
                d["sheet_error"] = str(e)[:120]
        if i % 10 == 0:
            print(f"  ...{i}/{len(items)} " + json.dumps(stats, ensure_ascii=False), flush=True)
            _dump_json(args.output, decisions)  # 증분 저장(중단 대비)
        time.sleep(args.sleep)
    mcp.close()
    _dump_json(args.output, decisions)

    # 현황판(00_진행) 카테고리 열 갱신 — 자기 열 1개만, 열 통짜 1회 호출.
    # 매트릭스는 파생본이라 실패해도 저장 결과에 영향이 없다(rebuild 로 언제든 복구).
    if sheet and not args.dry_run:
        try:
            from eroomlib import matrix
            m = matrix.read(args.sheet)
            n = matrix.mark_many(
                args.sheet, "카테고리",
                {d["productId"]: matrix.map_catfix(d.get("상태", ""))
                 for d in decisions if d.get("productId")},
                matrix=m)
            print(f"  현황판({matrix.TAB}) 카테고리: {n}칸 갱신")

            # ── 제외카테고리 게이트 (2026-08-09) ────────────────────────────
            # **이 자리가 "저장 직후"가 아니라 decisions 루프의 출구인 이유**:
            # `이미정확` 은 저장을 하지 않는다(위 :285). 그런데 카테고리는 확정이고
            # 현황판엔 `완료` 가 찍힌다. 저장 자리에 달면 그 건이 통째로 빠진다.
            # 여기(현황판 쓰는 자리)에 달아야 `자동저장완료` + `이미정확` 이 함께 잡힌다.
            gated = set()
            if not getattr(args, "no_gate", False):
                gated = _run_gate(args, decisions, m)
            # 카테고리 열은 건드리지 않는다 — 카테고리는 실제로 확정된 사실이다.

            # 카테고리가 실제로 바뀌면 그 상품의 상품명은 폐기 대상이다
            # (SKILL 계약: "카테고리 재교정 = 그 상품 상품명 전부 폐기, 부분회수 금지").
            # 이미 `완료`인 건은 이걸로 다시 대상이 되고, 미착수는 사유만 붙는다.
            #
            # **게이트가 재작업 플래그 앞에 선다**(원안 2026-08-08): 제외 대상이면
            # 재작업이 아니라 삭제다. 재작업을 찍으면 `pending` 이 다시 집어가 막으려던
            # 상품명 비용이 그대로 나간다.
            redo = {}
            for d in decisions:
                pid = d.get("productId")
                if not pid or d.get("상태") != "자동저장완료" or pid in gated:
                    continue
                prev, new = (d.get("기존카테고리") or ""), (d.get("변경카테고리") or "")
                if not new or _norm_path(prev) == _norm_path(new):
                    continue
                redo[pid] = "카테고리 변경 — 키워드 재선정 필요"
            if redo:
                k = matrix.flag_many(args.sheet, "상품명", redo,
                                     from_task="카테고리", matrix=m)
                print(f"  상품명 재작업 표시: {k}건 (카테고리가 바뀐 상품)")
        except Exception as e:  # noqa: BLE001
            print(f"  [경고] 현황판 갱신 실패: {str(e)[:120]}", file=sys.stderr)

    print("###APPLY### " + json.dumps(stats, ensure_ascii=False))
    print(f"결과 -> {args.output} ({'DRY-RUN(저장안함)' if args.dry_run else '실저장'})")


def _to_float(v):
    try:
        return float(str(v).replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser(description="불사자 원격 HTTP MCP 직접 호출")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("probe", help="initialize→tools/list 실동작 검증")
    p.add_argument("--tool", help="추가로 호출해볼 도구 이름")
    p.add_argument("--args", help="그 도구의 arguments JSON")
    p.set_defaults(func=cmd_probe)

    w = sub.add_parser("workdata", help="현재 카테고리+썸네일 요약(대화 밖)")
    w.add_argument("--input", "-i", required=True, help="targets.json [{productId,..}]")
    w.add_argument("--output", "-o", required=True, help="workdata.json 저장 경로")
    w.add_argument("--mode", default="full", choices=["full", "summary"])
    w.add_argument("--sleep", type=float, default=0.3, help="호출 간 대기(초)")
    w.add_argument("--refresh", action="store_true",
                   help="스냅샷 무시하고 불사자에서 다시 받는다")
    w.set_defaults(func=cmd_workdata)

    a = sub.add_parser("apply", help="match+저장 1패스(미리보기→비교→커밋)")
    a.add_argument("--input", "-i", required=True, help="merged.json")
    a.add_argument("--output", "-o", required=True, help="decisions.json 저장 경로")
    a.add_argument("--threshold", type=float, default=70.0,
                   help="자동저장 확신도 임계(%%). 기본 70 (2026-07-24 90→70 하향)")
    a.add_argument("--dry-run", action="store_true", help="미리보기만, 실제 저장 안 함")
    a.add_argument("--sheet", help="구글시트 spreadsheetId(건건 기록)")
    a.add_argument("--no-sheet", action="store_true", help="시트 기록 비활성(테스트)")
    a.add_argument("--resume-sheet", action="store_true",
                   help="시트 G열 채워진 행(이미 처리)은 전부 건너뜀(중단 후 이어달리기)")
    a.add_argument("--force", action="store_true",
                   help="시트에 이미 완료로 기록된 행도 재조회·재저장하고 덮어쓴다(기본 off)")
    a.add_argument("--no-gate", action="store_true",
                   help="제외카테고리 게이트를 끈다(검증·재현용). 기본은 켬")
    a.add_argument("--limit", type=int, default=0, help="이번 실행 N건만(청크). 0=전체")
    a.add_argument("--sleep", type=float, default=0.4, help="상품 간 대기(초)")
    a.set_defaults(func=cmd_apply)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
