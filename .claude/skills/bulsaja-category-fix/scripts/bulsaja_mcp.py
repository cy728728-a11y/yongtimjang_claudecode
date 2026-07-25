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
import re
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

from eroomlib.bulsaja import BulsajaMCP as _BaseMCP  # 불사자 HTTP MCP transport(저수준)


class BulsajaMCP(_BaseMCP):
    """불사자 MCP — 저수준 transport(open/list_tools/call_tool/close 등)는
    eroomlib.bulsaja.BulsajaMCP 에서 상속하고, 여기서는 카테고리 교정 **도메인 헬퍼**
    (workdata/category_preview/category_commit)만 얹는다.
    """

    def workdata(self, product_id, mode="full"):
        """상품의 현재 카테고리 + **정체 판별 증거 4종**을 뽑아 반환(경량).

        증거 4종 (2026-07-24 개편). 한국어 상품명·썸네일은 불사자 가공 '후' 산출물이라
        같이 틀릴 수 있다 → 가공 '전' 원본(중국어 원문명·옵션명)을 독립 증거로 함께 넘긴다.
          ① 한국어 상품명  data.productName / uploadSmartStoreProductName  (용의자)
          ② 중국어 원문명  data.originalProductName                        (타오바오 원 리스팅)
          ③ 옵션명         data.uploadSkus[].text / ._text                 (실제 판매 단위)
          ④ 썸네일         data.uploadThumbnails[]                         (최대 6장)
        옵션 이미지(uploadSkus[].urlRef)는 2바퀴(정체불명 큐) 확인용으로만 보관.
        """
        raw = self.call_tool("bulsaja_product_workdata",
                             {"productId": product_id, "mode": mode})
        data = raw.get("data", raw) if isinstance(raw, dict) else {}
        cat = (data.get("uploadCategory") or {}).get("ss_category") or {}
        ss_name = cat.get("name") or ""
        thumbs = data.get("uploadThumbnails") or []
        if not isinstance(thumbs, list):
            thumbs = []
        name = (data.get("productName")
                or data.get("uploadSmartStoreProductName") or "")
        opt_ko, opt_cn, opt_img = _sku_evidence(data.get("uploadSkus"))
        return {
            "productId": product_id,
            "상품명": name,
            "원문명": data.get("originalProductName") or "",
            "옵션명": opt_ko,
            "옵션명원문": opt_cn,
            "옵션이미지": opt_img,
            "기존카테고리": ss_name if ss_name else "미설정",
            "썸네일": thumbs[:6],
            "원본링크": data.get("product_url") or "",
        }

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

    # close()·open()·call_tool() 등 transport 는 _BaseMCP(eroomlib.bulsaja) 에서 상속.


_OPT_MAX = 8      # 키워드 추출에 넘길 옵션명 최대 개수(이룸님 확정, 2026-07-24)
_OPT_IMG_MAX = 4  # 2바퀴(정체불명) 확인용 옵션 이미지 최대 장수
_OPT_PREFIX = re.compile(r"^\s*[A-Za-z가-힣]?\s*[.)]\s*")


def _sku_evidence(skus):
    """uploadSkus[] → (옵션명 한국어, 옵션명 원문, 옵션 이미지URL) 각각 중복제거·상한.

    옵션은 '실제 판매 단위'라 상품명이 왜곡돼도 정체가 드러난다
    (예 상품명 '자키 받침대' / 옵션 '3톤 세단 모델잭에어펌프' → 실제는 자키+에어펌프 세트).
    전건 22개씩 넘기면 토큰이 커지므로 중복 제거 후 앞 8개만 쓴다.
    exclude=True(판매 제외) 옵션은 실물이 아니므로 건너뛴다.
    """
    if not isinstance(skus, list):
        return [], [], []
    ko, cn, img = [], [], []
    for s in skus:
        if not isinstance(s, dict) or s.get("exclude"):
            continue
        t = _OPT_PREFIX.sub("", str(s.get("text") or "")).strip()
        if t and t not in ko and len(ko) < _OPT_MAX:
            ko.append(t)
        c = str(s.get("_text") or "").strip()
        if c and c not in cn and len(cn) < _OPT_MAX:
            cn.append(c)
        u = str(s.get("urlRef") or "").strip()
        if u and u not in img and len(img) < _OPT_IMG_MAX:
            img.append(u)
    return ko, cn, img


def _norm_path(p):
    """카테고리 경로 정규화: '>' 주변 공백 제거해 셀하/불사자 경로 비교 가능하게.
    (셀하 '생활/건강 > 공구 > 농기계' ↔ 불사자 '생활/건강>공구>농기계')
    """
    if not p:
        return ""
    return ">".join(seg.strip() for seg in str(p).split(">"))


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
    """
    targets = _load_json(args.input)
    mcp = BulsajaMCP()
    mcp.open()
    out = []
    for i, t in enumerate(targets, 1):
        pid = t.get("productId") or t.get("id")
        rec = {"productId": pid, "row": t.get("row")}
        try:
            wd = mcp.workdata(pid, mode=args.mode)
            if not wd.get("상품명"):
                wd["상품명"] = t.get("상품명", "")  # 시트 값 fallback
            rec.update(wd)
        except Exception as e:
            rec["상품명"] = t.get("상품명", "")
            rec["원문명"] = ""
            rec["옵션명"] = []
            rec["옵션명원문"] = []
            rec["옵션이미지"] = []
            rec["기존카테고리"] = "미설정"
            rec["썸네일"] = []
            rec["error"] = f"{type(e).__name__}: {e}"[:200]
        out.append(rec)
        if i % 20 == 0:
            print(f"  ...{i}/{len(targets)}", flush=True)
        time.sleep(args.sleep)
    mcp.close()
    _dump_json(args.output, out)
    ok = sum(1 for r in out if not r.get("error"))
    print(f"###WORKDATA### {ok}/{len(out)} OK -> {args.output}")


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

    # 시트 기반 재개: G열 채워진 행(이미 처리)은 건너뜀
    if args.resume_sheet and args.sheet:
        from eroomlib.gsheets import sheets_get
        tab = getattr(sheet_log, "DEFAULT_TAB", "시트1")
        gcol = sheets_get(args.sheet, f"{tab}!G2:G{2 + max((it.get('row') or 0) for it in items)}")
        done_rows = {i + 2 for i, r in enumerate(gcol) if r and r and r[0].strip()}
        before = len(items)
        items = [it for it in items if it.get("row") not in done_rows]
        print(f"[resume-sheet] 이미 처리 {before - len(items)}행 스킵 → 남은 {len(items)}건")

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
                   help="시트 G열 채워진 행(이미 처리)은 건너뜀")
    a.add_argument("--limit", type=int, default=0, help="이번 실행 N건만(청크). 0=전체")
    a.add_argument("--sleep", type=float, default=0.4, help="상품 간 대기(초)")
    a.set_defaults(func=cmd_apply)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
