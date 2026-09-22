#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""어휘군을 넓히기 **전에** 오탐 비용을 재는 도구 (04-08 에서 태어났다).

왜 있는가
---------
2026-09-22 전수 검수에서 미탐 11장이 나왔다. 그 11장의 OCR 을 보고 키워드를 더하는
것은 쉽다 — 어려운 건 **그 키워드가 멀쩡한 제품 이미지를 몇 장이나 배너로 접는지**다.
그걸 안 재고 어휘군을 넓히면 정밀도가 조용히 무너진다(검수 시점 실측 44.4%가 이미
오탐이었다). 이 도구가 재는 것이 정확히 그 비용이다.

무엇을 하는가
-------------
  ① 회차 캐시 원본 전량을 **한 번** OCR 해 줄 목록을 덤프한다 (944장 약 170초).
     덤프는 재사용한다 — 어휘군 변형을 열 번 시험해도 OCR 은 한 번이다
  ② 후보 키워드 하나하나에 대해 in-sample 로 센다:
       · 새로잡음 — 현행 어휘군이 배너라 안 한 장 중 이 키워드가 잡는 장
       · 미탐해소 — 그중 **사람이 배너라 한 장** (얻는 것)
       · 새오탐   — 그중 **사람이 제품이라 한 장** (치르는 값)
       · 미검수   — 사람이 그 줄을 안 본 상품의 장 (잴 수 없는 구간)
  ③ `--gate` 를 주면 현행/확장 어휘군으로 `게이트집계` 를 각각 다시 낸다

🔴 **여기서 나오는 숫자는 전부 in-sample 이다.** 놓친 장을 보고 만든 키워드를 그
   장으로 채점하는 것이라 게이트 통과 근거가 못 된다(T-4-29 · Pitfall 3).
   쓰임은 하나다 — **후보들 사이의 상대 비교.** "A 는 미탐 1을 풀고 오탐 0,
   B 는 미탐 0을 풀고 오탐 3" 은 in-sample 에서도 유효한 비교다.
   절대 판정은 다음 회차 out-of-sample 이 한다.

비용
----
크레딧 0 · 네트워크 0 · MCP 0. 디스크에 이미 있는 원본만 읽는다.
OCR 이므로 **`.venv`** 로 돌려야 한다(`pyobjc-framework-Vision` 이 거기에만 있다).

사용
----
    # 산출물 경로는 잡 레지스트리에서 얻는다 — glob 금지
    RP=$(.venv-web/bin/python3 -c \\
        "from webapp import jobs; print(jobs.latest_done('banner_scan')['result_path'])")

    # 후보 JSON: {"군이름": ["키워드", ...], ...}
    .venv/bin/python3 webapp/tests/fixtures/lexicon_ablation.py \\
        --result-path "$RP" --candidates /tmp/cand.json --dump /tmp/ocr_all.json

    # 어휘군을 실제로 고친 뒤 게이트가 어떻게 움직이는지
    .venv/bin/python3 webapp/tests/fixtures/lexicon_ablation.py \\
        --result-path "$RP" --dump /tmp/ocr_all.json --gate

⚠️ `--dump` 파일에는 **OCR 원문이 들어간다**(T-4-15 — 산출물·로그에는 안 싣는 것).
   저장소 밖(`/tmp` 등)에 두고, 커밋하지 마라. `.gitignore` 에 기대지 말고 경로를 밖에 둬라.
"""
import argparse
import copy
import json
import os
import sys
import time
from pathlib import Path

루트 = Path(__file__).resolve().parents[3]
if str(루트) not in sys.path:
    sys.path.insert(0, str(루트))
스캐너디렉터리 = 루트 / ".claude" / "skills" / "bulsaja-detail-page" / "scripts"
if str(스캐너디렉터리) not in sys.path:
    sys.path.insert(0, str(스캐너디렉터리))

import banner_scan as bs                                    # noqa: E402
from webapp import banner, banner_store, settings           # noqa: E402


def 캐시루트() -> str:
    """`jobs.banner_dir()` 과 같은 규칙. `webapp.jobs` 는 pydantic 을 끌고 와 `.venv` 에서 못 쓴다."""
    p = Path(settings.cfg("banner_cache_dir",
                          settings.DEFAULTS["banner_cache_dir"])).expanduser()
    return str(p if p.is_absolute() else 루트 / p)


def ocr덤프(문서: dict, 덤프경로: str) -> dict:
    """`{"<상품순번>:<장순번>": [줄, ...]}`. 이미 있으면 다시 안 뜬다.

    **판정 대상만 뜬다** — 못 받은 장(404 등)을 여기서 OCR 하면 실패가 `제품` 으로
    흡수된다(Pitfall 2). 판별은 `banner_scan.판정대상인가` 하나로 통일한다.
    """
    if os.path.exists(덤프경로):
        결과 = json.loads(Path(덤프경로).read_text(encoding="utf-8"))
        print(f"OCR 덤프 재사용: {덤프경로} ({len(결과)}장)")
        return 결과

    회차 = 문서["run_dir"]
    루트경로 = 캐시루트()
    revision = int(문서["판정규칙"]["vision_revision"])
    결과, 시작, 총 = {}, time.time(), 0
    for 상품순번, p in enumerate(문서["상품"]):
        for 장 in p["장"]:
            if not bs.판정대상인가(장):
                continue
            경로 = bs.원본경로(루트경로, 회차, 상품순번, 장["순번"])
            if not os.path.exists(경로):
                continue
            키 = f"{상품순번}:{장['순번']}"
            try:
                결과[키] = bs.ocr_2패스(경로, revision=revision)
            except Exception as e:               # noqa: BLE001 — 도구라 원인만 보이면 된다
                결과[키] = None
                print(f"  OCR실패 {키}: {type(e).__name__}", flush=True)
            총 += 1
            if 총 % 200 == 0:
                print(f"  {총}장 {time.time() - 시작:.0f}s", flush=True)
    Path(덤프경로).write_text(json.dumps(결과, ensure_ascii=False), encoding="utf-8")
    print(f"OCR 덤프 {총}장 {time.time() - 시작:.1f}s → {덤프경로}")
    return 결과


def 장목록(문서: dict, 줄들맵: dict, 라벨: dict, 확인) -> list:
    """집계에 쓸 장들. 물갈이 사본은 **대표 하나만** 센다 (성공기준 4 · 게이트집계와 같은 규약)."""
    확인됨 = {str(k) for k in 확인}
    본 = []
    대표 = set()
    for 상품순번, p in enumerate(문서["상품"]):
        키 = banner.상품키(p)
        if 키 in 대표:
            continue
        대표.add(키)
        라 = {int(k): v for k, v in (라벨.get(키) or {}).items()}
        for 장 in p["장"]:
            if not bs.판정대상인가(장):
                continue
            기계 = 장.get("판정")
            본.append({
                "본문": " / ".join(str(x) for x in
                                 (줄들맵.get(f"{상품순번}:{장['순번']}") or [])).lower(),
                "기계": 기계,
                "사람": 라.get(장["순번"], 기계),
                "검수": 키 in 확인됨,
                "이름": f"{p['판매자상품코드'][:6]}:{장['순번']}",
            })
    return 본


def 후보표(장들: list, 후보: dict) -> None:
    print(f"\n{'키워드':32s} {'새로잡음':>7s} {'미탐해소':>7s} {'새오탐':>7s} {'미검수':>6s}")
    print("-" * 70)
    for 군, 항목들 in 후보.items():
        print(f"[{군}]")
        for kw in 항목들:
            k = kw.lower()
            새 = [c for c in 장들 if k in c["본문"] and c["기계"] != banner.배너]
            해소 = [c for c in 새 if c["검수"] and c["사람"] == banner.배너]
            오탐 = [c for c in 새 if c["검수"] and c["사람"] != banner.배너]
            미검 = [c for c in 새 if not c["검수"]]
            if not 새:
                continue                          # 발화 0 은 줄을 안 먹는다
            줄 = f"  {kw:30s} {len(새):7d} {len(해소):7d} {len(오탐):7d} {len(미검):6d}"
            if 오탐:
                줄 += "  ← " + ", ".join(c["이름"] for c in 오탐[:4])
            print(줄)
        발화0 = [kw for kw in 항목들
               if not any(kw.lower() in c["본문"] for c in 장들)]
        if 발화0:
            print(f"  (발화 0 — 이 코퍼스에서는 검증 안 됨): {', '.join(발화0)}")


def 재판정(문서: dict, 줄들맵: dict, 어휘군: dict) -> dict:
    """주어진 어휘군으로 전 장을 다시 판정한 산출물 **사본**. 원본은 안 건드린다."""
    소문자 = {군: tuple(a.lower() for a in 항목) for 군, 항목 in 어휘군.items()}
    규칙 = 문서["판정규칙"]
    사본 = copy.deepcopy(문서)
    for 상품순번, p in enumerate(사본["상품"]):
        for 장 in p["장"]:
            if not bs.판정대상인가(장):
                continue
            줄 = 줄들맵.get(f"{상품순번}:{장['순번']}")
            if 줄 is None:
                continue
            본문 = " / ".join(str(x) for x in 줄).lower()
            걸린 = [군 for 군, 항목 in 소문자.items()
                   if 본문.strip() and any(a in 본문 for a in 항목)]
            if 걸린:
                장["판정"] = banner.배너
                장["사유"] = "어휘군:" + ",".join(걸린)
                continue
            사유 = bs.무내용사유(장.get("w"), 장.get("h"),
                             규칙["무내용_종횡비"], 규칙["무내용_짧은변px"])
            장["판정"] = banner.무내용 if 사유 else banner.제품
            장["사유"] = 사유
    return 사본


def main() -> int:
    ap = argparse.ArgumentParser(description="어휘군 확장의 오탐 비용을 in-sample 로 잰다")
    ap.add_argument("--result-path", required=True,
                    help="배너 스캔 산출물 JSON. jobs.latest_done('banner_scan') 에서 얻어라")
    ap.add_argument("--dump", required=True,
                    help="OCR 줄 덤프 경로. **저장소 밖에 둬라** (OCR 원문이 들어간다)")
    ap.add_argument("--candidates", help="후보 키워드 JSON: {\"군\": [\"키워드\", ...]}")
    ap.add_argument("--gate", action="store_true",
                    help="현행 산출물과 현재 어휘군으로 게이트집계를 각각 다시 낸다")
    인자 = ap.parse_args()

    if not 인자.candidates and not 인자.gate:
        print("--candidates 나 --gate 중 하나는 줘야 한다", file=sys.stderr)
        return 2

    try:
        문서 = json.loads(Path(인자.result_path).read_text(encoding="utf-8"))
        회차 = 문서["run_dir"]
        라벨 = banner_store.라벨읽기(회차)
        확인 = banner_store.확인읽기(회차)
        줄들맵 = ocr덤프(문서, 인자.dump)
    except Exception as e:                        # noqa: BLE001 — 도구라 원인만 보이면 된다
        print(f"준비 실패: {e}", file=sys.stderr)
        return 1

    if not 라벨:
        print(f"경고: {회차} 회차에 사람 라벨이 0건이다 — "
              "미탐해소·새오탐 칸이 전부 0으로 보인다(측정이 아니라 공집합이다)",
              file=sys.stderr)

    if 인자.candidates:
        후보 = json.loads(Path(인자.candidates).read_text(encoding="utf-8"))
        후보표(장목록(문서, 줄들맵, 라벨, 확인), 후보)

    if 인자.gate:
        print("\n=== 게이트집계 (🔴 in-sample — 통과 근거 아님) ===")
        print(f"  산출물 그대로 (어휘군 {문서['판정규칙']['어휘군버전']}):")
        print(f"    {banner.게이트집계(문서, 라벨, 확인)}")
        재 = 재판정(문서, 줄들맵, bs.어휘군)
        print("  현재 어휘군으로 재판정:")
        print(f"    {banner.게이트집계(재, 라벨, 확인)}")
        분포 = {}
        for p in 재["상품"]:
            for 장 in p["장"]:
                분포[장["판정"]] = 분포.get(장["판정"], 0) + 1
        print(f"    전체 판정 분포: {분포}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
