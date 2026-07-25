# -*- coding: utf-8 -*-
"""카테고리 교정 결과를 구글시트에 일괄 동기화 (gws 재인증 후 실행).

targets 순서(=A열 순서)대로 decisions(메인)+vision+steer 를 병합해
B2:H101 을 한 번에 update. 마스터 인덱스 집계도 갱신.

사용: python sheet_sync.py <RUN_DIR>
"""
import datetime
import json
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SKILL_SCRIPTS = r"C:\Users\workspace\.claude\skills\bulsaja-category-fix\scripts"
sys.path.insert(0, SKILL_SCRIPTS)
from gws_util import _run_gws, sheets_get, sheets_update  # noqa: E402

FOLDER = "1bVa3y725YCCSrOtx_bqBylBpvaXvwm2w"
MASTER = "1R4XdWohipaYeR-0QOAyRiVYZlk6iDofGONEBzSymGqs"
NAME = "카테고리교정_1번_용쌤1-1"


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    run = sys.argv[1]
    targets = load(f"{run}/targets.json")
    products = {p["productId"]: p for p in load(f"{run}/products.json")}
    final = {}  # productId -> decision dict

    # 1) 메인 apply 결과
    for d in load(f"{run}/decisions.json"):
        final[d["productId"]] = d
    # 2) 비전 보정 결과 (덮어씀)
    try:
        for d in load(f"{run}/decisions_vision.json"):
            final[d["productId"]] = d
    except Exception:
        pass
    # 2b) 썸네일 불일치 3건 재교정 결과 (덮어씀)
    try:
        for d in load(f"{run}/decisions_fix3.json"):
            final[d["productId"]] = d
    except Exception:
        pass
    # 3) 조준 재시도 결과 (상태만 갱신)
    try:
        for r in load(f"{run}/steer_results.json"):
            pid = r["productId"]
            if pid in final:
                if r.get("hit_keyword"):
                    final[pid]["상태"] = "자동저장완료"
                    final[pid]["검색어저장"] = r["hit_keyword"]
                    final[pid]["변경카테고리"] = r.get("target", final[pid].get("변경카테고리", ""))
    except Exception:
        pass

    # 시트 찾기
    q = f"'{FOLDER}' in parents and name = '{NAME}' and trashed = false"
    d = _run_gws(["drive", "files", "list",
                  "--params", json.dumps({"q": q}, ensure_ascii=False),
                  "--format", "json"])
    files = d.get("files", [])
    if not files:
        print("[오류] 시트 없음 — 먼저 setup_sheet.py 실행 필요")
        sys.exit(1)
    sid = files[0]["id"]
    meta = _run_gws(["sheets", "spreadsheets", "get",
                     "--params", json.dumps({"spreadsheetId": sid,
                                             "fields": "sheets.properties.title"})])
    tab = meta["sheets"][0]["properties"]["title"]

    today = datetime.date.today().isoformat()
    rows = []
    for t in targets:
        pid = t["productId"]
        dec = final.get(pid, {})
        p = products.get(pid, {})
        kw = dec.get("검색어", "")
        if dec.get("검색어저장"):
            kw += f" [저장키워드: {dec['검색어저장']}]"
        rows.append([
            p.get("상품명", t.get("상품명", "")),
            p.get("기존카테고리", ""),
            dec.get("변경카테고리", ""),
            kw,
            str(dec.get("확신도", "")),
            dec.get("상태", ""),
            today,
        ])
    sheets_update(sid, f"{tab}!B2:H{1 + len(rows)}", rows)
    print(f"시트 동기화 {len(rows)}행 완료")

    # 마스터 인덱스 집계 갱신 (A열에서 마켓그룹 행 찾기)
    from collections import Counter
    stats = Counter(dec.get("상태", "") for dec in final.values())
    auto = stats.get("자동저장완료", 0) + stats.get("저장완료", 0)
    manual = stats.get("변경대상", 0) + stats.get("부분일치확인요", 0)
    unsaved = stats.get("매칭불가", 0) + stats.get("sellha조회실패", 0) + stats.get("이미정확", 0)
    acol = sheets_get(MASTER, "A2:A100")
    target_row = None
    for i, r in enumerate(acol):
        if r and r[0].strip() == "1번_용쌤1-1":
            target_row = i + 2
            break
    if target_row:
        sheets_update(MASTER, f"C{target_row}:G{target_row}",
                      [[len(rows), auto, manual, unsaved, today]])
        print(f"마스터 인덱스 갱신 (행 {target_row}): 자동 {auto} / 수동 {manual} / 미저장 {unsaved}")
    else:
        print("[주의] 마스터 인덱스에 1번_용쌤1-1 행 없음 (setup_sheet가 추가했는지 확인)")
    print(f"시트: https://docs.google.com/spreadsheets/d/{sid}")


if __name__ == "__main__":
    main()
