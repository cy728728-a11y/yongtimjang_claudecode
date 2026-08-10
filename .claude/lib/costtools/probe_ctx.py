#!/usr/bin/env python3
"""탐침 에이전트의 **첫 턴 컨텍스트**(cache_read + cache_creation)를 찍는다.

고정비 A/B 전용. 워커가 배치도 지시서도 읽기 전에 지고 시작하는 양이 이 값이다.

    python3 .claude/lib/costtools/probe_ctx.py <transcriptDir>

⚠️ 규율 두 가지 (근거: product-name/references/팬아웃-비용.md §⑤, §143~152)
  1) 파일을 고친 뒤에는 **새 세션**에서 재야 한다. 스킬 레지스트리는 디스크가 밖에서
     바뀌었다고 즉시 다시 읽지 않는다 — 같은 세션 안의 값은 참고값이다.
  2) **같은 에이전트 타입끼리만** 비교한다. 탐침(general-purpose)과 워크플로 워커는
     타입이 달라 ~2,400 차이가 나고, 섞으면 그게 절감으로 둔갑한다.
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wtel  # noqa: E402


def first_turn_context(path):
    """첫 턴의 cache_read + cache_creation. 못 읽으면 None."""
    try:
        turns, usages = wtel.usages_path(path)
    except Exception as exc:  # 로그 형식이 바뀌었거나 파일이 깨진 경우
        print(f"  ! {os.path.basename(path)} 읽기 실패: {exc}", file=sys.stderr)
        return None
    if not turns or not usages:
        return None
    u = usages[0]
    return (u.get("cache_read_input_tokens") or 0) + (
        u.get("cache_creation_input_tokens") or 0
    )


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    tdir = sys.argv[1]
    if not os.path.isdir(tdir):
        print(f"디렉터리가 없다: {tdir}", file=sys.stderr)
        return 1

    paths = sorted(glob.glob(os.path.join(tdir, "**", "agent-*.jsonl"), recursive=True))
    if not paths:
        print(f"agent-*.jsonl 이 없다: {tdir}", file=sys.stderr)
        return 1

    rows = []
    for p in paths:
        v = first_turn_context(p)
        if v is not None:
            rows.append((os.path.basename(p), v))

    if not rows:
        print("첫 턴을 읽을 수 있는 로그가 없다", file=sys.stderr)
        return 1

    print(f"{'파일':<44} {'첫 턴 컨텍스트':>14}")
    for name, v in rows:
        print(f"{name:<44} {v:>14,}")

    if len(rows) == 2:
        a, b = rows[0][1], rows[1][1]
        diff = a - b
        pct = (diff / a * 100) if a else 0.0
        print()
        print(f"차이: {diff:,} ({pct:+.1f}%)")
        # 재현 실측 노이즈는 0.3% (33,342 vs 33,237). 그 10배를 유의 기준으로 둔다.
        if abs(pct) < 3:
            print("→ 측정 노이즈(0.3%) 범위를 크게 벗어나지 않는다. 효과 없음으로 읽는다.")
        else:
            print("→ 노이즈의 10배를 넘는다. 실제 차이로 읽는다.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
