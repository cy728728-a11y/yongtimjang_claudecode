#!/usr/bin/env python3
"""상품명 모델 A/B 대조 — 두 run-dir 의 checked/ 를 상품별로 맞춰 본다.

정본: ../../skills/product-name/references/팬아웃-비용.md §모델 A/B

썸네일 verdict A/B 가 무너진 이유는 **정답이 없었기 때문**이다(대조군이 옳다고 가정했다가
Sonnet 환각 5건이 나왔다). 상품명은 다르다 — `name_check.py` 의 R1~R9 가 **정답이 있는
산술 검증**이라 각 군을 독립적으로 채점할 수 있다. 그래서 이 스크립트의 1차 지표는
일치율이 아니라 **군별 통과율**이다. 일치율은 참고로만 찍는다.

단 R1~R9 가 재지 못하는 것도 분명히 있다 — 키워드 선택이 상품에 맞는지, 실물판정이 옳은지,
보류가 타당한지. 그래서 **상태가 갈린 상품**과 **키워드가 하나도 안 겹치는 상품**을
목록으로 뽑는다. 그 목록은 사람이 직접 본다.

    python3 ab_pname.py <A run-dir> <B run-dir> [--labels 대조군,실험군]
"""
import collections
import json
import os
import re
import sys


def load_checked(run_dir):
    """checked/checked_NNN.json → {상품id: {...}}. 배치별 파일을 상품 단위로 편다."""
    out = {}
    cdir = os.path.join(run_dir, "checked")
    if not os.path.isdir(cdir):
        return out
    for fn in sorted(os.listdir(cdir)):
        if not fn.endswith(".json"):
            continue
        try:
            data = json.load(open(os.path.join(cdir, fn), encoding="utf-8"))
        except Exception as e:
            print(f"   ⚠ {fn} 파싱실패: {e}")
            continue
        for p in data.get("products", []):
            pid = p.get("productId")
            if not pid:
                continue
            chk = p.get("검증") or {}
            out[pid] = {
                "원본": p.get("원본상품명", ""),
                "새이름": p.get("새상품명", ""),
                "상태": p.get("상태", ""),
                "실물": p.get("실물판정", ""),
                "키워드": [k for k in (p.get("키워드1"), p.get("키워드2"),
                                       p.get("키워드3"), p.get("키워드4"),
                                       p.get("키워드5")) if k],
                "통과": bool(chk.get("통과")),
                "위반": list(chk.get("위반") or []),
                "경고": list(chk.get("경고") or []),
                "배치": data.get("batch"),
            }
    return out


def batch_products(run_dir):
    """배치(정본)에 실린 상품 전체 — 결과 누락은 이쪽을 기준으로 잡는다."""
    out = {}
    bdir = os.path.join(run_dir, "batches")
    for fn in sorted(os.listdir(bdir)):
        if not fn.endswith(".json"):
            continue
        data = json.load(open(os.path.join(bdir, fn), encoding="utf-8"))
        for p in data.get("products", []):
            out[p["productId"]] = {"원본": p.get("원본상품명", ""),
                                   "카테고리": data.get("카테고리", "")}
    return out


def rule_of(v):
    """위반 문자열 앞머리의 R번호만 뽑는다 ('R4 사용 키워드가 …' → 'R4')."""
    m = re.match(r"R\d+", v)
    return m.group(0) if m else v[:12]


def summarize(label, chk, expected):
    got = len(chk)
    st = collections.Counter(v["상태"] for v in chk.values())
    passed = sum(1 for v in chk.values() if v["통과"])
    failed = sum(1 for v in chk.values() if not v["통과"] and v["상태"] == "검증실패")
    held = sum(1 for v in chk.values()
               if v["상태"].startswith("보류") or v["상태"].startswith("스킵"))
    rules = collections.Counter(rule_of(x) for v in chk.values() for x in v["위반"])
    warns = collections.Counter(rule_of(x) for v in chk.values() for x in v["경고"])
    print(f"\n■ {label}  (배치 상품 {expected} · 결과 {got}"
          + (f" · **누락 {expected - got}**" if got < expected else "") + ")")
    print(f"   통과 {passed} / 검증실패 {failed} / 보류 {held}"
          f"   → 명명대상 대비 통과율 "
          f"{(passed / (passed + failed) * 100) if passed + failed else 0:.1f}%"
          f" · 전체 대비 {passed * 100 / expected:.1f}%")
    print(f"   상태: {dict(st)}")
    if rules:
        print(f"   위반 규칙: {dict(rules.most_common())}")
    if warns:
        print(f"   경고 규칙: {dict(warns.most_common())}")
    return {"passed": passed, "failed": failed, "held": held, "got": got}


def main():
    argv = sys.argv[1:]
    labels = ["A", "B"]
    if "--labels" in argv:
        i = argv.index("--labels")
        labels = argv[i + 1].split(",")
        del argv[i:i + 2]          # 값까지 걷어내야 위치인자로 새지 않는다
    argv = [a for a in argv if not a.startswith("--")]
    if len(argv) != 2:
        print(__doc__)
        sys.exit(1)
    a_dir, b_dir = argv
    a, b = load_checked(a_dir), load_checked(b_dir)
    bp = batch_products(a_dir)

    print("=" * 78)
    print(f"상품명 모델 A/B — 배치 {len(set(v['배치'] for v in a.values()))}개 · "
          f"정본 상품 {len(bp)}건")
    summarize(labels[0], a, len(bp))
    summarize(labels[1], b, len(bp))

    both = [pid for pid in bp if pid in a and pid in b]
    print("\n" + "=" * 78)
    print(f"■ 상태 대조 (양쪽 다 결과 있는 {len(both)}건)")
    diff_state = [pid for pid in both if a[pid]["상태"] != b[pid]["상태"]]
    print(f"   상태 일치 {len(both) - len(diff_state)}/{len(both)} "
          f"({(len(both) - len(diff_state)) * 100 / max(len(both), 1):.0f}%)")
    for pid in diff_state:
        print(f"\n   · {bp[pid]['원본'][:40]}  [{bp[pid]['카테고리'].split('>')[-1]}]")
        for lab, d in ((labels[0], a[pid]), (labels[1], b[pid])):
            print(f"       {lab:8} {d['상태']:16} {d['새이름'] or '—'}")
            if d["실물"]:
                print(f"       {'':8} 실물: {d['실물'][:70]}")

    # 키워드 선택은 R1~R9 가 재지 못한다 — 겹침 0 인 건만 사람이 본다
    print("\n" + "=" * 78)
    print("■ 키워드 선택 (R 규칙이 못 재는 축 — 겹침 0 인 건만)")
    named_both = [pid for pid in both
                  if a[pid]["새이름"] and b[pid]["새이름"]]
    ov = [len(set(a[pid]["키워드"]) & set(b[pid]["키워드"])) for pid in named_both]
    print(f"   양쪽 명명 {len(named_both)}건 · 키워드 완전일치 "
          f"{sum(1 for pid in named_both if set(a[pid]['키워드']) == set(b[pid]['키워드']))}"
          f" · 겹침 0 {sum(1 for x in ov if x == 0)}")
    for pid in named_both:
        if set(a[pid]["키워드"]) & set(b[pid]["키워드"]):
            continue
        print(f"\n   · {bp[pid]['원본'][:40]}  [{bp[pid]['카테고리'].split('>')[-1]}]")
        for lab, d in ((labels[0], a[pid]), (labels[1], b[pid])):
            print(f"       {lab:8} {'/'.join(d['키워드']):28} → {d['새이름']}")

    missing = [pid for pid in bp if pid not in a or pid not in b]
    if missing:
        print("\n" + "=" * 78)
        print(f"■ 결과 누락 {len(missing)}건")
        for pid in missing:
            side = labels[0] if pid not in a else labels[1]
            print(f"   · [{side} 없음] {bp[pid]['원본'][:50]}")


if __name__ == "__main__":
    main()
