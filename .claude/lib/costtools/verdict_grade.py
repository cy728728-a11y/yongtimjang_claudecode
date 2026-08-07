#!/usr/bin/env python3
"""verdict A/B 채점 — 모델끼리가 아니라 **사람이 판정한 라벨**에 대고 잰다.

정본: ../../skills/product-name/references/팬아웃-비용.md §모델 A/B ⑥

**왜 이렇게 재나** (2026-08-07): 첫 verdict A/B 가 무효였던 이유가 대조군(Sonnet)을 정답으로
가정한 것이었다. 일치율은 두 모델이 **같은 답을 내는가**만 재지 어느 쪽이 옳은지는 못 잰다.
그래서 정답지를 사람으로 바꿨다 — 메인이 이미지를 직접 열어 판정한 15건(`labels.json`).

    python3 verdict_grade.py <구run-dir> <A run-dir> <B run-dir>
    # 라벨 기본 위치는 이 스크립트 옆의 labels.json —
    # 실측 라벨 정본은 ~/eroom-data/thumbnail/runs/ab-verdict-v2/labels.json

⚠ **라벨이 `사용가능` 14 : `제외` 1 로 치우쳐 있다.** 표본이 원래 "두 모델이 과잉제외한 건"
이라 구조상 그렇다. 이 표본이 재는 것은 전건 정확도가 아니라 **과잉제외율**(=낭비 크레딧)과
진짜 결함을 잡는가다. "전부 사용가능"이 14/15 라는 걸 잊지 마라.
"""
import json
import glob
import os
import sys


def verdicts(run_dir):
    """verdict/results/vresult_*.json → {pid: (판정, 사유)}."""
    out = {}
    for f in sorted(glob.glob(os.path.join(run_dir, "verdict", "results", "*.json"))):
        try:
            doc = json.load(open(f, encoding="utf-8"))
        except Exception as e:                      # 깨진 JSON = 그 배치 통째 유실
            print(f"  ⚠ {os.path.basename(f)} 파싱 실패: {str(e)[:60]}")
            continue
        for p in doc.get("products", []):
            if p.get("productId"):
                out[p["productId"]] = (str(p.get("판정", "")).strip(),
                                       str(p.get("사유", "")).strip())
    return out


def bucket(v):
    """제외 계열은 한 덩어리로 본다 — 낭비 방향이 같다(재생성·이관)."""
    return "제외" if v.startswith("제외") else v


def resolve(labels, pids):
    """라벨 키는 썸네일 파일명(24자 절단)에서 딴 것이라 실제 상품id(27자)의 **접두**다."""
    out = {}
    for k, meta in labels.items():
        full = [p for p in pids if p.startswith(k)]
        if len(full) == 1:
            out[full[0]] = meta
        else:
            print(f"  ⚠ 라벨 키 매칭 실패({len(full)}건): {k} {meta['상품']}")
    return out


def grade(name, got, labels, batch_pids):
    hit = miss_real = over = unjudged = 0
    lines = []
    for pid, meta in labels.items():
        want = meta["정답"]
        v = got.get(pid)
        if v is None:
            unjudged += 1
            lines.append(f"    [미판정] {meta['상품']}")
            continue
        b = bucket(v[0])
        if b == want or (want == "사용가능" and b == "주의"):
            hit += 1                                 # 주의는 반영되므로 통과로 센다
        elif want == "사용가능":
            over += 1
            lines.append(f"    [과잉제외] {meta['상품']:16} ← {v[0]} · {v[1][:60]}")
        else:
            miss_real += 1
            lines.append(f"    [진짜결함 놓침] {meta['상품']:16} ← {v[0]}")
    print(f"\n== {name}  판정 {len(got)}/{len(batch_pids)}건")
    print(f"   라벨 {len(labels)}건 중 일치 {hit} · 과잉제외 {over} · 진짜결함 놓침 {miss_real}"
          + (f" · 미판정 {unjudged}" if unjudged else ""))
    for l in lines:
        print(l)
    return hit, over, miss_real


def main():
    old_dir, son_dir, hai_dir = sys.argv[1], sys.argv[2], sys.argv[3]
    L = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "labels.json"), encoding="utf-8"))["labels"]
    old, son, hai = verdicts(old_dir), verdicts(son_dir), verdicts(hai_dir)
    pids = set(old) | set(son) | set(hai)
    L = resolve(L, pids)
    print(f"상품 {len(pids)}건 · 라벨 {len(L)}건")
    for nm, g in (("Sonnet(신)", son), ("Haiku(신)", hai)):
        grade(nm, g, L, pids)

    # 두 신 판정 사이의 불일치 — 라벨 밖은 채점할 수 없으니 목록만 낸다.
    both = [p for p in pids if p in son and p in hai
            and bucket(son[p][0]) != bucket(hai[p][0])]
    print(f"\n== 신 Sonnet vs 신 Haiku 불일치 {len(both)}건"
          f" (라벨 밖 {len([p for p in both if p not in L])}건은 미채점)")
    for p in both:
        mark = "★라벨" if p in L else "     "
        print(f"  {mark} {p[-12:]}  S={son[p][0]:18} H={hai[p][0]}")
        if p not in L:
            print(f"          S사유: {son[p][1][:70]}")
            print(f"          H사유: {hai[p][1][:70]}")

    # 옛 Sonnet 대비 이동 — 지시서 정정이 실제로 판정을 바꿨는가
    for nm, g in (("Sonnet", son), ("Haiku", hai)):
        moved = [p for p in pids if p in old and p in g
                 and bucket(old[p][0]) != bucket(g[p][0])]
        print(f"\n옛 Sonnet 대비 {nm} 이동: {len(moved)}건")


if __name__ == "__main__":
    main()
