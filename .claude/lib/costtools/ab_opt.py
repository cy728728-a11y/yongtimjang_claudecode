#!/usr/bin/env python3
"""옵션정리 모델 A/B 대조 — N개 run-dir 을 상품별로 맞춰 본다.

정본: ../../skills/product-name/references/팬아웃-비용.md §모델 A/B

**옵션에는 상품명의 `name_check` 같은 독립 채점기가 없다.** 그래서 지표를 두 층으로 나눈다.

  ① 채점 가능한 것 — `apply` 가 붙인 **상태**. `apply` 는 시트·저장 없이도 계획을 끝까지
     계산하고(±50% 상한 · 순서 · `기본형` 마커 자동 부착 · `retarget_base_suffix`),
     그 결과가 `정리대상`(=저장 가능) 이냐 `확인요`·`보류(…)` 냐를 정한다.
     **이건 상품명의 `fix-r9` 와 같은 자리다 — 비용 0의 기계 교정 뒤에서 재는 값이라
     여기가 통과율이다.** 게이트 = 실비 / `정리대상` 건수(= 쓸 수 있는 결과물 하나당).

  ② 채점 불가능한 것 — 무엇이 메인상품인가, 어느 행이 비상품인가, 이름이 원문에 맞는가.
     정답이 없다. **그래서 여기서는 일치율만 재고 어느 쪽이 옳은지는 말하지 않는다.**
     대신 갈린 건을 목록으로 뽑아 사람이 원문·가격으로 직접 판정한다
     (verdict A/B 가 무너진 이유 = 대조군을 정답으로 가정한 것).

파싱 실패·상품 누락도 본다 — 워커 반환값에는 안 잡히고 `apply` 전까지 성공으로 보인다
(상품명 A/B 에서 Haiku 가 깨진 JSON 으로 배치 하나를 통째로 잃었다).

    python3 ab_opt.py <run-dir> <run-dir> [...] --labels A,B,... [--cost 4.37,1.92,...]
    # 각 run-dir 에 `plan_ab.json` 이 있어야 한다:
    #   run_options.py apply --run-dir <R> --sheet <id> --no-sheet --no-review \
    #                        --emit <R>/plan_ab.json
"""
import collections
import json
import os
import sys


def load_plans(run_dir):
    """apply --emit 산출 → {상품id: 계획요약}. 없으면 빈 dict."""
    path = os.path.join(run_dir, "plan_ab.json")
    if not os.path.exists(path):
        print(f"   ⚠ {path} 없음 — apply --emit 을 먼저 돌려라")
        return {}
    return {p["productId"]: p for p in json.load(open(path, encoding="utf-8"))}


def load_results(run_dir):
    """results/result_NNN.json 원본 → ({상품id: 워커출력}, 파싱실패 배치 목록).

    `apply` 는 깨진 파일을 만나면 죽거나 건너뛴다 — 어느 배치가 깨졌는지는 여기서만 보인다.
    """
    out, broken = {}, []
    rdir = os.path.join(run_dir, "results")
    if not os.path.isdir(rdir):
        return out, broken
    for fn in sorted(os.listdir(rdir)):
        if not fn.endswith(".json"):
            continue
        try:
            data = json.load(open(os.path.join(rdir, fn), encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            broken.append(f"{fn}: {str(e)[:60]}")
            continue
        for p in data.get("products", []):
            if p.get("productId"):
                out[p["productId"]] = p
    return out, broken


def batch_products(run_dir):
    """배치(정본)에 실린 상품 전체 — 누락은 이쪽을 기준으로 잡는다."""
    out = {}
    bdir = os.path.join(run_dir, "batches")
    for fn in sorted(os.listdir(bdir)):
        if not fn.endswith(".json"):
            continue
        doc = json.load(open(os.path.join(bdir, fn), encoding="utf-8"))
        for p in doc.get("products", []):
            out[p["productId"]] = {
                "상품명": p.get("상품명", ""),
                "원문명": p.get("원문명", ""),
                "판매행": len(p.get("판매행") or []),
                "배치": doc.get("배치"),
            }
    return out


def summarize(label, plans, res, broken, expected, cost=None):
    st = collections.Counter(v.get("상태", "") for v in plans.values())
    ok = st.get("정리대상", 0)
    got = len(res)
    print(f"\n■ {label}  (정본 {expected}건 · 워커 결과 {got}건"
          + (f" · **누락 {expected - got}**" if got < expected else "") + ")")
    if broken:
        print(f"   ⚠ 파싱실패 배치 {len(broken)}개: {broken}")
    print(f"   정리대상(저장 가능) {ok}/{expected} = **{ok * 100 / max(expected, 1):.1f}%**")
    print(f"   상태: {dict(st.most_common())}")
    if cost is not None:
        print(f"   실비 ${cost:.4f} → 상품당 ${cost / max(expected, 1):.4f} · "
              f"**통과건당 ${cost / ok:.4f}**" if ok else
              f"   실비 ${cost:.4f} → 통과 0건이라 통과건당 계산 불가")
    # 무엇이 통과를 막았나 — 상태 문자열만으론 원인이 안 보이는 것들
    warn = collections.Counter(w.split(":")[0][:24]
                               for v in plans.values() for w in (v.get("경고") or []))
    viol = collections.Counter(str(w)[:24]
                               for v in plans.values() for w in (v.get("이름위반") or []))
    if warn:
        print(f"   경고: {dict(warn.most_common(6))}")
    if viol:
        print(f"   이름위반: {dict(viol.most_common(6))}")
    hand = sum(1 for v in res.values() if v.get("이관"))
    dele = sum(1 for v in res.values() if v.get("삭제후보"))
    held = sum(1 for v in res.values() if str(v.get("상태", "")).startswith("보류"))
    print(f"   워커 자체 보류 {held} · 이관 {hand} · 삭제후보 {dele}")
    return {"ok": ok, "got": got}


def keeps(res_p):
    return frozenset(str(x) for x in (res_p.get("유지") or []))


def main():
    argv = sys.argv[1:]
    labels, costs = None, None
    for flag in ("--labels", "--cost"):
        if flag in argv:
            i = argv.index(flag)
            val = argv[i + 1]
            if flag == "--labels":
                labels = val.split(",")
            else:
                costs = [float(x) for x in val.split(",")]
            del argv[i:i + 2]
    dirs = [a for a in argv if not a.startswith("--")]
    if len(dirs) < 2:
        print(__doc__)
        sys.exit(1)
    labels = labels or [os.path.basename(d.rstrip("/")) for d in dirs]
    costs = costs or [None] * len(dirs)

    bp = batch_products(dirs[0])
    plans = [load_plans(d) for d in dirs]
    loaded = [load_results(d) for d in dirs]
    res = [x[0] for x in loaded]
    broken = [x[1] for x in loaded]

    print("=" * 78)
    print(f"옵션정리 모델 A/B — 정본 상품 {len(bp)}건 · 군 {len(dirs)}개")
    for i, lab in enumerate(labels):
        summarize(lab, plans[i], res[i], broken[i], len(bp), costs[i])

    both = [pid for pid in bp if all(pid in r for r in res)]
    print("\n" + "=" * 78)
    print(f"■ 이산값 대조 (모든 군에 결과가 있는 {len(both)}건)")

    def agree(fn):
        return sum(1 for pid in both if len({fn(r[pid]) for r in res}) == 1)

    n = max(len(both), 1)
    a_keep = agree(keeps)
    a_rep = agree(lambda p: str(p.get("대표후보") or ""))
    print(f"   `유지` 집합 완전일치 {a_keep}/{len(both)} ({a_keep * 100 / n:.0f}%)")
    print(f"   `대표후보` 일치     {a_rep}/{len(both)} ({a_rep * 100 / n:.0f}%)")
    for i, lab in enumerate(labels):
        k = [len(keeps(res[i][pid])) for pid in both]
        x = [len(res[i][pid].get("제외") or []) for pid in both]
        print(f"   {lab:10} 유지 평균 {sum(k) / n:.1f} · 제외 평균 {sum(x) / n:.1f}"
              f" · 이름 지정 평균 {sum(len(res[i][pid].get('이름') or {}) for pid in both) / n:.1f}")

    # 상태(=저장 가능 여부)가 갈린 건 — 통과율 차이의 실체
    print("\n" + "=" * 78)
    print("■ 상태가 갈린 상품 (통과율 차이가 어디서 나오나)")
    for pid in both:
        sts = [plans[i].get(pid, {}).get("상태", "—") for i in range(len(dirs))]
        if len(set(sts)) == 1:
            continue
        print(f"\n   · {bp[pid]['상품명'][:44]}  (판매행 {bp[pid]['판매행']} · b{bp[pid]['배치']})")
        for i, lab in enumerate(labels):
            p = plans[i].get(pid, {})
            print(f"       {lab:10} {sts[i]:16} 유지 {p.get('유지수', '—')}"
                  f"/제외 {p.get('제외수', '—')}  대표 {str(p.get('대표이름') or '—')[:26]}")
            for w in (p.get("경고") or [])[:2]:
                print(f"       {'':10} ⚠ {str(w)[:70]}")
            for w in (p.get("이름위반") or [])[:2]:
                print(f"       {'':10} ✗ {str(w)[:70]}")

    # 정답이 없는 축 — 사람이 원문으로 직접 판정할 목록
    print("\n" + "=" * 78)
    print("■ 판단이 갈린 상품 — `유지` 집합 불일치 (정답 없음: 사람이 원문으로 판정)")
    split = [pid for pid in both if len({keeps(r[pid]) for r in res}) > 1]
    print(f"   {len(split)}/{len(both)}건")
    for pid in split:
        print(f"\n   · {bp[pid]['상품명'][:44]}")
        print(f"     원문 {bp[pid]['원문명'][:56]}  (판매행 {bp[pid]['판매행']} · {pid})")
        base = keeps(res[0][pid])
        for i, lab in enumerate(labels):
            k = keeps(res[i][pid])
            mark = "" if i == 0 else f"  (기준 대비 +{len(k - base)}/-{len(base - k)})"
            print(f"       {lab:10} 유지 {len(k):>2} · 제외 {len(res[i][pid].get('제외') or []):>2}"
                  f"{mark}  {str(res[i][pid].get('메인상품') or '')[:40]}")

    missing = [pid for pid in bp if any(pid not in r for r in res)]
    if missing:
        print("\n" + "=" * 78)
        print(f"■ 결과 누락 {len(missing)}건")
        for pid in missing:
            side = [labels[i] for i, r in enumerate(res) if pid not in r]
            print(f"   · [{','.join(side)} 없음] {bp[pid]['상품명'][:50]}")


if __name__ == "__main__":
    main()
