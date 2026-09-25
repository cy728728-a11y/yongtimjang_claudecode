#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""스모크 전용: D-02 ① 우회. --estimate-only 외 사용 금지. 산출물은 web/ 밖에 두어 접수 라우트가 가리킬 수 없다.

Plan 05-04 Task 3-A — 실제 불사자 MCP 로 `detail_batch.py --estimate-only` 를 크레딧 0 으로
돌려 보기 위한 inputs 파일을 만든다.

왜 우회가 필요한가: 회차 2026-09-20 의 최신 배너 산출물(232c3bb3, 생성 2026-09-25T00:14)보다
모든 `확인함` 시각이 앞선다(연구 §실데이터 · Pitfall 3). 그래서 관문 `banner.상세입력목록` 의
①(확인시각 ≥ 생성시각)이 지금 전부 막는다 — 사람 재확인은 05-05 실탄 전 단계다.
**이 스크립트만** `확인시각=산출물 생성시각` 을 명시적으로 넘겨 ①을 통과시킨다. ②③(라벨우선
판정 · 잔여 하한 · 10장 자르기)은 그대로 탄다.

안전 경계:
  · 출력은 `evidence/smoke/inputs.json` — 회차의 `web/` 밖이다. `jobs._override_targets` 가
    부모 디렉터리 == `<회차>/web` 만 받으므로 이 파일은 접수 잡의 대상이 될 수 없다(T-05-19).
  · 웹앱 잡 DB(webapp.db)는 **읽기 전용(mode=ro)** 으로만 연다. `jobs.latest_done` 을 부르지
    않는다 — 그 함수는 `_reap` 으로 DB 를 고친다(사용자 서버가 쓰는 파일이다).
  · 네트워크 0 — 파일·DB 만 읽는다. 불사자 호출은 다음 단계의 CLI(`--estimate-only`)가 한다.

실행: `.venv-web/bin/python .planning/phases/05-core-value/evidence/smoke_inputs.py`
"""
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from webapp import banner, banner_store, board, join, jobs, paths, settings  # noqa: E402

회차 = "2026-09-20"
출력 = Path(__file__).resolve().parent / "smoke" / "inputs.json"


def 최신성공산출물(kind: str) -> dict:
    """잡 DB 를 **읽기 전용**으로 열어 그 kind 의 최신 성공 잡 산출물 경로를 찾는다."""
    db = jobs.db_path()
    try:
        cx = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
        cx.row_factory = sqlite3.Row
        try:
            r = cx.execute("SELECT id, result_path FROM jobs WHERE kind = ? AND status = 'done' "
                           "AND run_dir = ? ORDER BY started_at DESC, rowid DESC LIMIT 1",
                           (kind, 회차)).fetchone()
        finally:
            cx.close()
    except sqlite3.Error as e:
        raise SystemExit(f"잡 DB 를 못 읽었다: {e}")
    if r is None or not r["result_path"]:
        raise SystemExit(f"{kind} 성공 잡이 없다 — 회차 {회차}")
    try:
        문서 = json.loads(Path(r["result_path"]).read_text(encoding="utf-8"))
    except Exception as e:
        raise SystemExit(f"{kind} 산출물을 못 읽었다: {type(e).__name__}: {e}")
    return {"id": r["id"], "path": r["result_path"], "doc": 문서}


def main() -> int:
    try:
        배너 = 최신성공산출물("banner_scan")
        조인 = 최신성공산출물("bulsaja_scan")
        생성시각 = 배너["doc"].get("생성시각")
        if not 생성시각:
            raise SystemExit("배너 산출물에 생성시각이 없다")

        판정 = json.loads((paths.run_dir_path(회차) / "result.json").read_text(encoding="utf-8"))
        붙임 = join.attach(board.fold_products(판정), 판정, 조인["doc"],
                          excluded=settings.cfg("index_excluded_groups",
                                                settings.DEFAULTS["index_excluded_groups"]),
                          done_tags=settings.cfg("done_tags", settings.DEFAULTS["done_tags"]))
        # 보드의 "🔴 기본 선택" 과 같은 기준 — 고를 수 있는 행(해소 · 기작업 아님 · 팬아웃 읽음) 중 🔴
        후보 = [r for r in join.selectable(붙임) if r.get("상세상태") == "중국어원본"]

        관측색인 = {(o.get("acct"), o.get("mallProductId")): o
                    for o in (조인["doc"].get("행") or []) if isinstance(o, dict)}
        배너색인 = {}
        for 상품 in (배너["doc"].get("상품") or []):
            if isinstance(상품, dict) and 상품.get("판매자상품코드"):
                배너색인.setdefault(str(상품["판매자상품코드"]), 상품)
        라벨 = banner_store.라벨읽기(회차)
        하한 = int(settings.cfg("banner_skip_min_keep", settings.DEFAULTS["banner_skip_min_keep"]))

        items, 제외, 본상품 = [], [], set()
        for 행 in 후보:
            관측 = 관측색인.get((행.get("acct"), 행.get("mallProductId"))) or {}
            코드, pid = 관측.get("판매자상품코드"), 행.get("productId")
            if not 코드 or not pid:
                제외.append({"판매자상품코드": str(코드 or 행.get("mallProductId")),
                             "사유": "조인에 productId·판매자상품코드 없음"})
                continue
            if pid in 본상품:
                제외.append({"판매자상품코드": str(코드), "사유": "같은 불사자 상품 중복"})
                continue
            상품 = 배너색인.get(str(코드))
            if 상품 is None:
                제외.append({"판매자상품코드": str(코드), "사유": "배너 산출물에 없음"})
                continue
            try:
                키 = banner.상품키(상품)
                # ⚠️ 스모크 전용 우회 — 확인시각을 산출물 생성시각으로 넘긴다(D-02 ①)
                결과 = banner.상세입력목록(상품, 라벨=라벨.get(키) or {}, 확인시각=생성시각,
                                       생성시각=생성시각, 잔여하한=하한)
            except ValueError as e:
                제외.append({"판매자상품코드": str(코드), "사유": str(e)})
                continue
            본상품.add(pid)
            items.append({"productId": pid, "판매자상품코드": str(코드),
                          "imageUrls": 결과["urls"], "제품이미지총수": 결과["총수"],
                          "잘림": 결과["잘림"]})

        출력.parent.mkdir(parents=True, exist_ok=True)
        출력.write_text(json.dumps({"items": items, "제외": 제외, "선택": len(후보),
                                   "_스모크": {"배너잡": 배너["id"], "조인잡": 조인["id"],
                                              "생성시각": 생성시각,
                                              "주의": "D-02 ① 우회 · --estimate-only 전용"}},
                                  ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"🔴 후보 {len(후보)} · inputs {len(items)} · 제외 {len(제외)} → {출력}")
        for x in 제외:
            print(f"  제외 {x['판매자상품코드']}: {x['사유']}")
        return 0
    except SystemExit:
        raise
    except Exception as e:
        print(f"스모크 inputs 생성 실패: {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
