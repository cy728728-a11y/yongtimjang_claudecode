#!/usr/bin/env python3
"""run 모드 A/B 대조 — 두 run-dir 의 results/ 를 상품별로 맞춰 본다.

정본: ../../skills/product-name/references/팬아웃-비용.md
**일치율만으로는 어느 쪽이 옳은지 모른다.** 이 스크립트는 불일치 목록을 뽑는 데까지고,
어느 쪽이 맞는지는 메인이 이미지를 직접 열어 판정한다.

    python3 ab_compare.py <대조군 run-dir> <실험군 run-dir>              # run 모드(기준이미지)
    python3 ab_compare.py --verdict <대조군 run-dir> <실험군 run-dir>    # verdict 모드(3축 판정)

**verdict 오답은 방향에 따라 무게가 다르다** — 한 숫자로 뭉뚱그리지 않는다:
  거짓 통과(제외→사용가능) = 불량이 대표로 반영된다.  치명
  거짓 제외(사용가능→제외) = 멀쩡한 걸 버리고 재생성(크레딧).  낭비
  사유 오분류              = 후속 처리 갈래가 달라진다.  중간
"""
import json
import os
import sys


def load_results(run_dir):
    """results/result_NNN.json 전부를 {상품id: {기준이미지, 경로, 배치}} 로 편다."""
    out, missing = {}, []
    rdir = os.path.join(run_dir, "results")
    if not os.path.isdir(rdir):
        return out, missing
    for fn in sorted(os.listdir(rdir)):
        if not fn.endswith(".json"):
            continue
        try:
            data = json.load(open(os.path.join(rdir, fn), encoding="utf-8"))
        except Exception as e:                       # 워커가 깨진 JSON 을 쓴 경우
            missing.append(f"{fn} 파싱실패: {e}")
            continue
        for p in data.get("products", []):
            pid = p.get("productId")
            if not pid:
                continue
            out[pid] = {"기준이미지": p.get("기준이미지"),
                        "경로": p.get("기준이미지경로", ""),
                        "상태": p.get("상태", ""),
                        "배치": data.get("배치")}
    return out, missing


def batch_products(run_dir):
    """배치(정본)에 실린 상품 전체 — 결과 누락을 잡으려면 이쪽이 기준이다."""
    out = {}
    bdir = os.path.join(run_dir, "batches")
    if not os.path.isdir(bdir):
        return out
    for fn in sorted(os.listdir(bdir)):
        if not fn.endswith(".json"):
            continue
        data = json.load(open(os.path.join(bdir, fn), encoding="utf-8"))
        for p in data.get("products", []):
            out[p["productId"]] = {"상품명": p.get("상품명", ""),
                                   "배치": data.get("배치"),
                                   "후보수": len(p.get("후보이미지") or [])}
    return out


def load_verdicts(run_dir):
    """verdict/results/vresult_NNN.json → {상품id: {판정, 사유, 배치}}."""
    out = {}
    rdir = os.path.join(run_dir, "verdict", "results")
    if not os.path.isdir(rdir):
        return out
    for fn in sorted(os.listdir(rdir)):
        if not fn.endswith(".json"):
            continue
        try:
            data = json.load(open(os.path.join(rdir, fn), encoding="utf-8"))
        except Exception as e:
            print(f"   ⚠ {fn} 파싱실패: {e}")
            continue
        for p in data.get("products", []):
            if p.get("productId"):
                out[p["productId"]] = {"판정": p.get("판정", ""),
                                       "사유": p.get("사유", ""),
                                       "배치": data.get("배치")}
    return out


def verdict_batch_products(run_dir):
    """verdict/batches/ 의 상품 — 결과 누락을 잡는 기준(정본)."""
    out = {}
    bdir = os.path.join(run_dir, "verdict", "batches")
    if not os.path.isdir(bdir):
        return out
    for fn in sorted(os.listdir(bdir)):
        if not fn.endswith(".json"):
            continue
        data = json.load(open(os.path.join(bdir, fn), encoding="utf-8"))
        for p in data.get("products", []):
            out[p["productId"]] = {
                "상품명": p.get("상품명", ""),
                "배치": data.get("배치"),
                "이미지": {k: p.get(k) for k in
                          ("기존대표경로", "대표옵션경로", "생성본경로") if p.get(k)},
            }
    return out


def _passes(v):
    """`사용가능` 계열인가 — 즉 commit 이 대표로 반영하는가."""
    return (v or "").startswith("사용가능")


def cmd_verdict(ref_dir, exp_dir):
    ref, exp = load_verdicts(ref_dir), load_verdicts(exp_dir)
    batch = verdict_batch_products(exp_dir) or verdict_batch_products(ref_dir)

    exp_miss = [p for p in batch if p not in exp]
    ref_miss = [p for p in batch if p not in ref]
    common = [p for p in batch if p in ref and p in exp]

    print(f"배치 상품 {len(batch)}건 | 대조군 판정 {len(ref)} · 실험군 판정 {len(exp)}")
    print(f"누락 — 대조군 {len(ref_miss)} · 실험군 {len(exp_miss)}")
    for p in exp_miss:
        print(f"   실험군 누락: {p} {batch[p]['상품명'][:30]}")
    if not common:
        print("겹치는 상품이 없다 — 결과 파일을 확인할 것")
        return 1

    same, false_pass, false_reject, misclass = [], [], [], []
    for p in common:
        a, b = ref[p]["판정"], exp[p]["판정"]
        if a == b:
            same.append(p)
        elif not _passes(a) and _passes(b):
            false_pass.append(p)          # 제외/주의 → 사용가능. 치명
        elif _passes(a) and not _passes(b):
            false_reject.append(p)        # 사용가능 → 제외. 낭비
        else:
            misclass.append(p)            # 둘 다 제외 계열인데 세부가 다름

    n = len(common)
    print(f"\n판정 일치 {len(same)}/{n} ({len(same) / n * 100:.0f}%)")
    print(f"  ★ 거짓 통과   {len(false_pass):>3}   (대조군 제외 → 실험군 사용가능) — 치명")
    print(f"    거짓 제외   {len(false_reject):>3}   (대조군 사용가능 → 실험군 제외) — 낭비")
    print(f"    사유 오분류 {len(misclass):>3}   (제외 계열끼리 다름)")

    for title, ids in (("거짓 통과 — 전건 이미지 확인 대상", false_pass),
                       ("거짓 제외", false_reject),
                       ("사유 오분류", misclass)):
        if not ids:
            continue
        print(f"\n=== {title} ===")
        for p in ids:
            print(f"\n[{p}] {batch[p]['상품명'][:40]}  (배치 {batch[p]['배치']})")
            print(f"  대조군: {ref[p]['판정']}  {ref[p]['사유'][:90]}")
            print(f"  실험군: {exp[p]['판정']}  {exp[p]['사유'][:90]}")
            for k, v in batch[p]["이미지"].items():
                print(f"    {k}: {v}")
    return 0


def main():
    argv = sys.argv[1:]
    if argv[:1] == ["--verdict"]:
        if len(argv) < 3:
            print(__doc__)
            return 1
        return cmd_verdict(argv[1], argv[2])
    if len(argv) < 2:
        print(__doc__)
        return 1
    ref_dir, exp_dir = argv[0], argv[1]
    ref, ref_bad = load_results(ref_dir)
    exp, exp_bad = load_results(exp_dir)
    batch = batch_products(exp_dir) or batch_products(ref_dir)

    # 배치에 있는데 결과에 없는 것 = 누락. 미판정이 통과로 둔갑하는 경로라 따로 센다.
    ref_miss = [p for p in batch if p not in ref]
    exp_miss = [p for p in batch if p not in exp]

    common = [p for p in batch if p in ref and p in exp]
    same = [p for p in common if ref[p]["기준이미지"] == exp[p]["기준이미지"]]
    diff = [p for p in common if ref[p]["기준이미지"] != exp[p]["기준이미지"]]

    print(f"배치 상품 {len(batch)}건 | 대조군 결과 {len(ref)} · 실험군 결과 {len(exp)}")
    print(f"누락 — 대조군 {len(ref_miss)} · 실험군 {len(exp_miss)}")
    for p in exp_miss:
        print(f"   실험군 누락: {p} {batch[p]['상품명'][:30]}")
    for m in ref_bad + exp_bad:
        print(f"   ⚠ {m}")
    if not common:
        print("겹치는 상품이 없다 — 결과 파일을 확인할 것")
        return 1
    print(f"\n일치 {len(same)}/{len(common)} ({len(same) / len(common) * 100:.0f}%)"
          f" · 불일치 {len(diff)}")

    if diff:
        print("\n=== 불일치 (메인이 이미지를 직접 열어 재판정할 목록) ===")
        for p in diff:
            b = batch[p]
            print(f"\n[{p}] {b['상품명'][:40]}  (배치 {b['배치']} · 후보 {b['후보수']}장)")
            print(f"  대조군 기준이미지 {ref[p]['기준이미지']}  {ref[p]['경로']}")
            print(f"  실험군 기준이미지 {exp[p]['기준이미지']}  {exp[p]['경로']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
