#!/usr/bin/env python3
"""제외카테고리 삭제 대상을 **불사자에 보낼 요청 시트** 한 장으로 만든다.

왜 필요한가 (2026-08-09 실측): 삭제는 서버 대기열이 **한 번에 한 건씩** 처리한다.
한 그룹 293건을 밀어넣었더니 대기 148건이 쌓이고 새 제출은 `원자적 생성 실패로 전체 그룹
미접수` 로 튕겼다. 12,486건을 이 경로로는 못 넘긴다 → 불사자 쪽에 **일괄 처리를 요청**한다.

시트는 두 탭이다.
  `요청`  — 상품 1건 1행. 불사자가 그대로 처리할 수 있게 상품id·마켓그룹이 앞에 온다
  `요약`  — 그룹별·사유별 집계 + 이 요청이 뭔지 설명하는 머리말(사람이 먼저 읽는 곳)

`delete` 를 이미 돌린 run-dir 이면 `delete_progress.jsonl` 을 읽어 **시도 결과**를 함께 싣는다
(이미 지워진 건·잠금 건을 불사자가 다시 지우려 하지 않게).

CLI:
    python .claude/skills/bulsaja-category-fix/scripts/gate_request_sheet.py \
        --run-dir <R> [--title "..."] [--sheet <기존 시트id 에 탭 추가>]
"""
import argparse
import datetime
import json
import os
import sys

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

from eroomlib.gsheets import _run_gws, chunk_by_size, ensure_tab, sheets_update  # noqa: E402

TAB_REQ = "요청"
TAB_SUM = "요약"

HEADER = ["상품id", "마켓그룹", "상품명", "저장된 카테고리", "제외 사유(걸린 조각)",
          "카테고리 확정 방식", "이전 시도 결과", "비고"]

# `delete` 판정 → 불사자가 읽을 한국어. 내부 코드값을 그대로 내보내지 않는다.
TRIED = {
    "이미없음": "이미 휴지통에 있음 — 처리 불필요",
    "잠금": "삭제 잠금이 걸려 있음 — 잠금 해제 필요",
    "미접수": "대기열이 차서 접수되지 않음",
    "접수": "접수됐으나 완료 미확인",
    "실패": "실패",
}


def load_tried(run_dir):
    """delete_progress.jsonl → {productId: 한국어 결과}. 없으면 빈 dict."""
    p = os.path.join(run_dir, "delete_progress.jsonl")
    if not os.path.exists(p):
        return {}
    out = {}
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            for r in json.loads(line).get("결과", []):
                # 같은 상품이 재제출됐으면 **나중 줄이 최신**이다.
                out[r["productId"]] = TRIED.get(r["판정"], r["판정"])
    return out


def build_rows(targets, tried):
    rows = []
    for t in sorted(targets, key=lambda x: (x["그룹"], x["카테고리"])):
        near = "근접 저장(경로가 정확한 값이 아님)" if t.get("근접저장") else ""
        rows.append([
            t["productId"], t["그룹"], t.get("상품명", ""), t.get("카테고리", ""),
            t.get("조각", ""), t.get("상태", ""), tried.get(t["productId"], "미시도"),
            near,
        ])
    return rows


def build_summary(targets, tried, run_dir):
    from collections import Counter
    g = Counter(t["그룹"] for t in targets)
    f = Counter(t.get("조각", "") for t in targets)
    s = Counter(tried.get(t["productId"], "미시도") for t in targets)
    big = Counter(t.get("카테고리", "").split(">")[0] for t in targets)
    near = sum(1 for t in targets if t.get("근접저장"))

    L = [["제외 카테고리 상품 일괄 삭제 요청"], [],
         ["작성", datetime.date.today().isoformat()],
         ["대상 상품", len(targets)],
         ["마켓그룹", len(g)],
         [], ["■ 무엇을 요청하나"],
         ["`요청` 탭의 상품을 전부 삭제해 주세요. 마켓 전체(scope ALL) + 소싱 상품까지 함께 "
          "지우는 방식입니다."],
         ["판매하지 않기로 한 세부 카테고리에 속한 상품이라 가공(상품명·옵션·썸네일) 대상에서 "
          "이미 제외해 둔 것들입니다."],
         [], ["■ 왜 직접 못 지웠나"],
         ["삭제 대기열이 한 번에 한 건씩 처리돼, 한 그룹(293건)만 넣어도 대기가 쌓이고 "
          "이후 요청이 '원자적 생성 실패로 전체 그룹 미접수'로 반려됩니다."],
         ["그 속도로는 이 수량을 넘길 수 없어 일괄 처리를 요청드립니다."],
         [], ["■ 이미 시도해 본 결과"], ["결과", "건수"]]
    L += [[k, v] for k, v in s.most_common()]
    if near:
        L += [[], ["근접 저장분(저장된 경로가 정확한 값이 아닌 건)", near],
              ["오삭제 가능성을 알고 포함한 것입니다. `요청` 탭 비고란에 표시했습니다."]]
    L += [[], ["■ 마켓그룹별"], ["마켓그룹", "건수"]]
    L += [[k, v] for k, v in g.most_common()]
    L += [[], ["■ 대분류별"], ["대분류", "건수"]]
    L += [[k, v] for k, v in big.most_common()]
    L += [[], ["■ 제외 사유 상위 30"], ["걸린 조각", "건수"]]
    L += [[k, v] for k, v in f.most_common(30)]
    L += [[], ["산출 근거", os.path.basename(run_dir)]]
    return L


def create_sheet(title):
    d = _run_gws(["sheets", "spreadsheets", "create"],
                 body={"properties": {"title": title}})
    return d["spreadsheetId"]


def ensure_rows(sid, tab, need):
    """탭의 행 수를 최소 `need` 까지 늘린다.

    **새 스프레드시트는 기본 1,000행이다.** 그 너머로 쓰면 gws 가
    `Range ('요청'!A1069) exceeds grid limits` 로 막는다 — 조용히 잘리는 게 아니라
    거기서부터 통째로 안 써진다(실측 2026-08-09, 12,486행 중 1,068행에서 멈춤).
    """
    meta = _run_gws(["sheets", "spreadsheets", "get",
                     "--params", json.dumps({"spreadsheetId": sid})])
    props = next((s["properties"] for s in meta.get("sheets", [])
                  if s["properties"]["title"] == tab), None)
    if props is None:
        raise RuntimeError(f"탭을 찾지 못했습니다: {tab}")
    cur = (props.get("gridProperties") or {}).get("rowCount", 0)
    if cur >= need:
        return
    _run_gws(["sheets", "spreadsheets", "batchUpdate",
              "--params", json.dumps({"spreadsheetId": sid})],
             body={"requests": [{"appendDimension": {
                 "sheetId": props["sheetId"], "dimension": "ROWS",
                 "length": need - cur}}]})
    print(f"    {tab}: 행 확장 {cur} → {need}")


def write_tab(sid, tab, header, rows, sleep=1.1):
    """탭 하나를 채운다. `header` 가 비면 1행부터 rows 를 그대로 쓴다(요약 탭).

    청크마다 쉬는 이유: 쓰기 쿼터가 분당 60회인데 12,486행이면 청크가 200개 가까이 된다.
    `sheets_update` 에 백오프가 있지만 429 를 맞고 기다리는 것보다 안 맞는 게 싸다.
    """
    import time
    ensure_tab(sid, tab, list(header) if header else [tab])
    ensure_rows(sid, tab, len(rows) + (2 if header else 1))
    if header:
        sheets_update(sid, f"'{tab}'!A1", [header])
    first = 2 if header else 1
    for i, part in chunk_by_size(rows):
        sheets_update(sid, f"'{tab}'!A{first + i}", part)
        print(f"    {tab}: {i + len(part)}/{len(rows)}행", flush=True)
        time.sleep(sleep)


def main():
    ap = argparse.ArgumentParser(description="불사자 일괄 삭제 요청 시트 생성")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--title", default=None)
    ap.add_argument("--sheet", default=None,
                    help="기존 스프레드시트에 탭으로 추가(없으면 새로 만든다)")
    args = ap.parse_args()

    with open(os.path.join(args.run_dir, "targets.json"), encoding="utf-8") as f:
        targets = json.load(f)
    tried = load_tried(args.run_dir)
    print(f"대상 {len(targets)}건 · 시도 기록 {len(tried)}건")

    title = args.title or f"제외카테고리_일괄삭제요청_{datetime.date.today():%y%m%d}"
    sid = args.sheet or create_sheet(title)
    print(f"시트: {title}\n  https://docs.google.com/spreadsheets/d/{sid}/edit")

    write_tab(sid, TAB_SUM, [], build_summary(targets, tried, args.run_dir))
    write_tab(sid, TAB_REQ, HEADER, build_rows(targets, tried))

    print(f"\n###REQSHEET### " + json.dumps(
        {"sheetId": sid, "행": len(targets)}, ensure_ascii=False))
    print(f"  https://docs.google.com/spreadsheets/d/{sid}/edit")


if __name__ == "__main__":
    main()
