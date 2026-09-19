#!/usr/bin/env bash
# 자동 테스트가 실제 광고비를 태우는 것을 막는 마지막 방어선.
#
# 왜 필요한가:
#   run_ads.py bids 는 --commit 이 붙는 순간 네이버 광고 API 에 PUT 을 날린다.
#   테스트가 실수로 그 플래그를 조립하면 CI 도 리뷰도 못 잡는다 — 돈이 먼저 나간다.
#   그래서 "테스트 트리에 --commit 이라는 글자 자체가 없다" 를 기계로 증명한다.
#   (01-VALIDATION.md § 크레딧·광고비 0 으로 쓰기 경로를 검증하는 3층 / 위협 T-1-SC2)
#
# 쓰기 경로를 검증해야 하는 테스트는 리터럴 대신 상수·간접 조립을 써라.
# 리터럴이 필요하다고 느껴지면, 그건 테스트가 진짜 실행에 너무 가까워졌다는 신호다.
#
# 사용: bash webapp/tests/no_commit_guard.sh   (exit 0 = 깨끗함)
set -u

# 저장소 루트 어디서 불러도 같은 곳을 본다 — 호출 위치에 의존하지 않는다.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 자기 자신은 제외한다. 이 파일은 설명을 위해 그 글자를 담고 있다.
# grep 의 `--` 뒤에는 옵션을 둘 수 없다(전부 파일 이름으로 읽힌다) — 그래서 패턴은 -e 로 준다.
HITS="$(grep -rn \
        --exclude="$(basename "${BASH_SOURCE[0]}")" \
        --exclude-dir=__pycache__ \
        --exclude-dir=.pytest_cache \
        -e '--commit' "$HERE" 2>/dev/null || true)"

if [ -n "$HITS" ]; then
  echo "테스트에 --commit 이 있다 — 실제 광고비가 나갈 수 있다. 아래를 지워라:" >&2
  echo "$HITS" >&2
  exit 1
fi

echo "no_commit_guard: OK (webapp/tests 에 --commit 리터럴 0건)"
exit 0
