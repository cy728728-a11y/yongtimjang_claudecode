# -*- coding: utf-8 -*-
"""산출물 + 사람 라벨 + 확인 → 게이트 숫자 (04-11 Task 1).

**산식을 재구현하지 않는다.** `webapp.banner.게이트집계` · `banner_store.라벨읽기` ·
`banner_store.확인읽기` 를 import 해서 그 결과 dict 를 JSON 한 줄로 찍기만 한다.
재측정 전후(옛 산출물 / 새 산출물)를 같은 라벨·같은 확인 위에서 나란히 재려고 만든 도구다.

⚠️ 사람 재검수 전의 숫자다 — 새 산출물에서 바뀐 장을 `게이트집계` 는 기존 `확인함` 으로
"자동 동의" 로 읽는다. 그 동의의 근거는 `recheck_list.py` 목록을 사람이 본 뒤에야 생긴다.

실행: `.venv-web/bin/python3 .planning/phases/04-banner-detection/evidence/regate.py \
         --out <산출물.json> --run-dir 2026-09-20`
"""
import argparse
import json
import os
import sys

# 저장소 루트를 import 경로에 올린다 (cwd 와 무관하게 `webapp` 을 찾도록)
_루트 = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "..", "..", "..", ".."))
if _루트 not in sys.path:
    sys.path.insert(0, _루트)

from webapp import banner, banner_store  # noqa: E402


def 재기(산출물경로: str, 회차: str, 누락률상한: float | None = None) -> dict:
    """산출물 파일 하나를 읽어 `게이트집계` 결과 dict 를 돌려준다."""
    try:
        with open(산출물경로, encoding="utf-8") as f:
            산출물 = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise SystemExit(f"⛔ 산출물을 못 읽었다: {산출물경로} — {e}")
    # 회차가 다른 산출물을 이 회차 라벨로 재면 라벨이 통째로 미아가 된다
    if str(산출물.get("run_dir") or "") != 회차:
        raise SystemExit(f"⛔ 산출물 회차 {산출물.get('run_dir')!r} ≠ --run-dir {회차!r}")
    라벨 = banner_store.라벨읽기(회차)
    확인 = banner_store.확인읽기(회차)
    결과 = banner.게이트집계(산출물, 라벨, 확인, 누락률상한=누락률상한)
    결과["_입력"] = {"산출물": os.path.abspath(산출물경로), "run_dir": 회차,
                  "라벨상품": len(라벨), "라벨장": sum(len(v) for v in 라벨.values()),
                  "확인상품": len(확인)}
    return 결과


def main() -> int:
    ap = argparse.ArgumentParser(description="산출물+라벨+확인 → 게이트 숫자 (게이트집계 import)")
    ap.add_argument("--out", required=True, help="배너 스캔 산출물 JSON 경로")
    ap.add_argument("--run-dir", required=True, help="회차 (예: 2026-09-20)")
    ap.add_argument("--max-miss-rate", type=float, default=None,
                    help="누락률 상한 (생략 시 banner.기본_누락률상한 — 바꾸지 마라)")
    인자 = ap.parse_args()
    try:
        결과 = 재기(인자.out, 인자.run_dir, 인자.max_miss_rate)
    except ValueError as e:
        print(f"⛔ 게이트집계 실패: {e}", file=sys.stderr)
        return 2
    print(json.dumps(결과, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
