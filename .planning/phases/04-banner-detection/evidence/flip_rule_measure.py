# -*- coding: utf-8 -*-
"""D-22 합성 규칙 실측 — `배너→제품` 뒤집기를 켜도 미탐이 늘지 않는가 (04-09 Task 1).

뒤집기 = 1차(어휘군)가 `배너` 인데 걸린 군이 전부 알려진 오탐 축(`연락처`·`공장직판`)이고
비전 v3 가 `제품` 이라 한 장을 `제품` 으로 되돌리는 것. 워터마크(D-21)·공장직판 오탐을 거르려는 규칙이다.

**새 호출 0 · 크레딧 0.** 이미 있는 증거만 쓴다:
  - `vision_pilot_result.json` 실험[2](v3 불일치 30) ∪ 실험[3](v3 합의표본 82) — 비전 v3 판정
  - 실험[4](워터마크 3분류 18) — D-21 진실값 재구성
  - 04-08 산출물의 `판매자상품코드` 로 상품순번을 찾고, 캐시 원본을 **현 어휘군(14군)** 으로 다시 OCR → 걸린군
  - 사람 라벨 DB(`라벨읽기`) — 명시 `배너` 는 무조건 진짜 배너

결정 규칙(기계적): 새미탐 == 0 이고 진실값 재구성이 확실(실험[4] 배너 == 3)하면 뒤집기 채택, 아니면 합집합.
애매하면 합집합이다 — 오탐은 누락률만 건드리지만 미탐은 게이트를 닫는다.

실행: 저장소 루트에서 `.venv/bin/python3 .planning/phases/04-banner-detection/evidence/flip_rule_measure.py`
"""
import json
import os
import sys

sys.path.insert(0, ".claude/skills/bulsaja-detail-page/scripts")
sys.path.insert(0, ".")

import banner_scan as bs  # noqa: E402
from webapp import banner_store  # noqa: E402

여기 = os.path.dirname(os.path.abspath(__file__))
파일럿 = os.path.join(여기, "vision_pilot_result.json")
결과파일 = os.path.join(여기, "flip_rule_result.json")
산출물 = os.path.expanduser(
    "~/python_work/data/naver-ads/runs/2026-09-20/web/"
    "banner_97c3578d-eee3-4c56-ab37-0006de292932.json")
캐시루트, 회차 = "webapp-banner/cache", "2026-09-20"
허용군 = {"연락처", "공장직판"}
뒤집기결정 = "합집합+뒤집기(연락처,공장직판)"


def 비전값(r):
    """실험 결과의 `비전` 필드 → 문자열 판정. 옛 실험은 dict 로 남아 있을 수 있다."""
    v = r.get("비전")
    if isinstance(v, dict):
        v = v.get("판정")
    return str(v) if v is not None else None


def main():
    try:
        파 = json.load(open(파일럿, encoding="utf-8"))
        문서 = json.load(open(산출물, encoding="utf-8"))
    except Exception as e:
        print(f"⛔ 입력을 못 읽었다: {type(e).__name__}: {e}")
        return 1

    실험 = 파["실험"]
    # ① 표본 — 실험[2] ∪ 실험[3], (코드, 장) 중복 제거
    표본 = {}
    for 번호 in (2, 3):
        for r in 실험[번호]["결과"]:
            키 = (r["코드"], int(r["장"]))
            if 키 not in 표본:
                표본[키] = {**r, "실험": 번호}

    # ③ 진실값 재료 — 실험[4](D-21) · 사람 라벨
    워터마크 = {(r["코드"], int(r["장"])): 비전값(r) for r in 실험[4]["결과"]}
    워터마크배너수 = sum(1 for v in 워터마크.values() if v == "배너")
    재구성확실 = (워터마크배너수 == 3)          # §11-4 의 12·3·3 재현 여부

    try:
        라벨 = banner_store.라벨읽기(회차)
    except Exception as e:
        print(f"[경고] 라벨을 못 읽었다 — 명시 라벨 없이 진행: {type(e).__name__}: {e}")
        라벨 = {}

    # 파일럿 `코드`(21자) → (상품순번, 타오바오상품번호).
    # 실측: 파일럿 `코드` 는 산출물의 `판매자상품코드` 와 맞는다(45상품) · `불사자코드` 와는 0건.
    # 둘 다 21자라 헷갈린다 — 판매자상품코드를 먼저 보고 불사자코드는 보조로만 본다.
    코드표 = {}
    for 필드 in ("판매자상품코드", "불사자코드"):
        for i, p in enumerate(문서["상품"]):
            c = p.get(필드)
            if c and c not in 코드표:
                코드표[c] = (i, str(p.get("타오바오상품번호")))
    매칭 = sum(1 for (c, _) in 표본 if c in 코드표)
    if 매칭 == 0:
        print("⛔ 불사자코드 매칭 0건 — 필드명이 다르다. 상품 dict 키:",
              list(문서["상품"][0].keys()))
        return 1

    # ② 현 어휘군 걸린군 재측정 + ④ 후보 집계
    행들, 측정불가, 후보 = [], [], []
    for (c, 장), r in sorted(표본.items()):
        if c not in 코드표:
            측정불가.append({"코드": c[:8], "장": 장, "사유": "상품 매칭 없음"})
            continue
        순번, 상품키 = 코드표[c]
        경로 = bs.원본경로(캐시루트, 회차, 순번, 장)
        if not os.path.exists(경로):
            측정불가.append({"코드": c[:8], "장": 장, "사유": "캐시 없음"})
            continue
        try:
            걸린군 = bs.어휘군걸림(bs.ocr_2패스(경로, revision=3))
        except Exception as e:
            측정불가.append({"코드": c[:8], "장": 장, "사유": f"OCR 실패: {type(e).__name__}"})
            continue

        # 진실값 — 보수적으로
        진실 = r.get("정답")
        출처 = "정답"
        if (c, 장) in 워터마크:
            진실 = "배너" if 워터마크[(c, 장)] == "배너" else "제품"
            출처 = "D-21(실험4)"
        if 라벨.get(상품키, {}).get(장) == "배너":
            진실, 출처 = "배너", "사람라벨"

        비전 = 비전값(r)
        행 = {"코드": c[:8], "장": 장, "걸린군": 걸린군, "비전": 비전,
             "진실": 진실, "진실출처": 출처, "실험": r["실험"]}
        행들.append(행)
        if 걸린군 and set(걸린군) <= 허용군 and 비전 == "제품":
            후보.append(행)

    새미탐 = sum(1 for h in 후보 if h["진실"] == "배너")
    줄어들오탐 = sum(1 for h in 후보 if h["진실"] == "제품")
    # ⑤ 결정 — 기계적으로
    결정 = 뒤집기결정 if (새미탐 == 0 and 재구성확실) else "합집합"

    결과 = {
        "일시": bs.지금(),
        "표본수": len(표본),
        "측정수": len(행들),
        "측정불가": len(측정불가),
        "측정불가목록": 측정불가,
        "워터마크실험_배너수": 워터마크배너수,
        "진실값재구성확실": 재구성확실,
        "1차배너수": sum(1 for h in 행들 if h["걸린군"]),
        "후보수": len(후보),
        "새미탐": 새미탐,
        "줄어들오탐": 줄어들오탐,
        "후보": 후보,
        "결정": 결정,
        "결정규칙": "새미탐==0 이고 실험[4] 배너==3 이면 뒤집기, 아니면 합집합",
    }
    json.dump(결과, open(결과파일, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"표본 {len(표본)} · 측정 {len(행들)} · 측정불가 {len(측정불가)} · "
          f"1차배너 {결과['1차배너수']}")
    print(f"뒤집기 후보 {len(후보)} — 진짜 배너(새 미탐) {새미탐} · 진짜 제품(줄어들 오탐) {줄어들오탐}")
    for h in 후보:
        print(f"  {h['코드']}:{h['장']:>2} 군={','.join(h['걸린군'])} 비전={h['비전']} "
              f"진실={h['진실']}({h['진실출처']})")
    print(f"실험[4] 배너 {워터마크배너수} (재구성 {'확실' if 재구성확실 else '불확실'})")
    print(f"결정: {결정}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"⛔ 실측 실패: {type(e).__name__}: {e}")
        sys.exit(1)
