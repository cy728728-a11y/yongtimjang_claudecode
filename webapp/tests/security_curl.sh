#!/usr/bin/env bash
# 보안 9종 검증 — **실행 중인 서버**에 대고 쏜다.
# (V-SAFE-02c 가 Plan 01-06 에서 c1/c2 두 갈래로 쪼개져 8 → 9 가 됐다.)
#
# TestClient 는 ASGI 앱을 직접 부르므로 "실제로 127.0.0.1 에만 떴는지", "uvicorn 이
# Host 헤더를 어떻게 넘기는지" 를 증명하지 못한다. 그 구멍을 이 스크립트가 메운다.
#
# 쓰는 법 (터미널 2개):
#   A) CT_DEV_TOKEN=devtoken123 ./webapp/run-webapp.sh
#   B) CT_DEV_TOKEN=devtoken123 bash webapp/tests/security_curl.sh
#
# 토큰은 **환경변수로만** 받는다. `.boot-token-for-test` 같은 파일을 만들지 마라 —
# 토큰을 디스크에 남기지 않는 것이 T-1-16 의 절반이다.
# 광고 시크릿은 읽기만 하고 stdout 에 **절대** 찍지 않는다.
#
# 변수·함수 이름을 한글로 쓰지 않는다. macOS 기본 bash 는 3.2 라 비ASCII 식별자에서
# "command not found" 로 죽는다(실측). 설명은 주석으로 한국어를 쓴다.
set -uo pipefail

PORT="${CT_PORT:-8765}"
T="${CT_DEV_TOKEN:-}"
B="http://127.0.0.1:$PORT"
fails=0

if [ -z "$T" ]; then
  echo "CT_DEV_TOKEN 이 없다. 서버를 그 값으로 띄우고 같은 값을 여기에도 줘라:" >&2
  echo "  CT_DEV_TOKEN=devtoken123 ./webapp/run-webapp.sh" >&2
  exit 2
fi

# check <ID> <설명> <0이면 통과인 결과코드>
check() {
  if [ "$3" -eq 0 ]; then
    echo "PASS $1  $2"
  else
    echo "FAIL $1  $2"
    fails=1
  fi
}

code() { curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$@"; }

# 서버가 안 떠 있으면 아래가 전부 000 으로 FAIL 한다 — 먼저 크게 알려준다.
if [ "$(code "$B/healthz")" = "000" ]; then
  echo "서버가 $B 에 없다. 터미널 A 에서 ./webapp/run-webapp.sh 를 먼저 띄워라" >&2
  exit 2
fi

# ── SAFE-01 ─────────────────────────────────────────────────────────────────

# V-SAFE-01a  127.0.0.1 에만 바인드 (0.0.0.0 이면 같은 와이파이의 아무나 들어온다)
listen=$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null)
bind_ok=1
echo "$listen" | grep -q "127.0.0.1:$PORT" && bind_ok=0
echo "$listen" | grep -q '0\.0\.0\.0' && bind_ok=1
check V-SAFE-01a "127.0.0.1 에만 바인드 (0.0.0.0 없음)" "$bind_ok"

# V-SAFE-01b  Host 화이트리스트 (DNS rebinding) → 400
test "$(code -H "Host: evil.com" "$B/")" = 400
check V-SAFE-01b "Host: evil.com → 400 (DNS rebinding 차단)" $?

# V-SAFE-01c  타 사이트 Origin 의 쓰기는 토큰이 맞아도 → 403
test "$(code -X POST -H "Origin: https://evil.com" -H "X-CT-Token: $T" \
        "$B/jobs/bids/preview")" = 403
check V-SAFE-01c "Origin: evil.com + 올바른 토큰 → 403 (CSRF 차단)" $?

# V-SAFE-01d  상태를 바꾸는 GET 이 없다 — Origin 방어의 전제
#   ※ VALIDATION.md 원문은 grep 하나로 줄바꿈을 건너뛰려 했는데, grep 은 줄 단위라
#      그 패턴은 **영원히 매치되지 않아 항상 PASS** 한다(빈 통과). 여기서는 GET 데코레이터
#      아래 본문을 실제로 훑는 방식으로 바꿨다 — "전부 통과"를 성공으로 오독하지 않으려고.
python3 - <<'PY'
import re, sys
from pathlib import Path

DEC = re.compile(r'^\s*@(?:app|router)\.get\(')
NEXT = re.compile(r'^\s*@|^\s*(?:async\s+)?def\s')
# 쓰기를 일으키는 호출들. 여기에 CLI 플래그 리터럴은 넣지 않는다 —
# webapp/tests 트리에 그 문자열이 있으면 no_commit_guard.sh 가 막는다(그게 맞다).
RISK = re.compile(r'\b(create_job|spawn|Popen|run_bids|run_revert)\b')

bad = []
for f in sorted(Path('webapp').rglob('*.py')):
    if 'tests' in f.parts:
        continue
    lines = f.read_text(encoding='utf-8', errors='ignore').splitlines()
    for i, l in enumerate(lines):
        if not DEC.match(l):
            continue
        # 데코레이터 다음 def 부터, 다음 데코레이터/최대 60줄까지가 그 핸들러 본문이다
        j = i + 1
        while j < len(lines) and not NEXT.match(lines[j]):
            j += 1
        end = min(j + 60, len(lines))
        for k in range(j + 1, end):
            if DEC.match(lines[k]) or lines[k].startswith('@'):
                break
            if RISK.search(lines[k]):
                bad.append(f"{f}:{k+1}")
for b in bad:
    print("상태를 바꾸는 GET 의심:", b)
sys.exit(1 if bad else 0)
PY
check V-SAFE-01d "상태를 바꾸는 GET 엔드포인트 0건" $?

# ── SAFE-02 ─────────────────────────────────────────────────────────────────

# V-SAFE-02a  토큰 없는 쓰기 → 403
test "$(code -X POST "$B/jobs/bids/preview")" = 403
check V-SAFE-02a "토큰 없는 POST → 403" $?

# V-SAFE-02b  틀린 토큰 → 403
test "$(code -X POST -H "Origin: $B" -H "X-CT-Token: wrong" "$B/jobs/bids/preview")" = 403
check V-SAFE-02b "틀린 토큰 POST → 403" $?

# V-SAFE-02c  정상 쓰기는 통과한다 — **두 갈래로 확인한다** (Plan 01-06 에서 조였다)
#
#   이게 없으면 "전부 막힘" 을 성공으로 오독한다. 403 만 확인하는 검증은
#   서버를 뽑아 놔도 똑같이 통과한다.
#
#   (1) 실재하는 쓰기 라우트에 올바른 Origin·토큰으로 쏜다. 가드 3층을 통과해
#       **앱 로직이 답했다는 것**까지 본다: 없는 회차 → 400 + 몸통에 "회차".
#       403 이면 가드가 정상 쓰기를 막은 것이고, 000/500 이면 서버가 이상한 것이다.
#       부수효과 0 — create_job 이 회차 화이트리스트에서 거부하므로 자식이 안 뜬다.
#   (2) Plan 01-07 이 만들 POST /jobs/bids/preview. 라우트가 **생기는 순간**
#       기준이 `-lt 400` 으로 자동으로 조여진다. 그 전에는 "정확히 404" 를 요구한다
#       ("403 이 아닐 것" 은 000·500 도 통과시켜서 느슨했다).
c1=$(curl -s --max-time 10 -w '\n%{http_code}' -X POST -H "Origin: $B" -H "X-CT-Token: $T" \
     -H 'Content-Type: application/json' -d '{"run_dir":"그런회차없음"}' "$B/jobs/run")
c1_code=$(printf '%s' "$c1" | tail -1)
c1_body=$(printf '%s' "$c1" | sed '$d')
ok=1
if [ "$c1_code" = "400" ]; then
  printf '%s' "$c1_body" | grep -q '회차' && ok=0
fi
check V-SAFE-02c1 "정상 쓰기가 가드 3층을 통과해 앱 로직에 닿는다 (400 + 사유, 현재 $c1_code)" "$ok"

ok_code=$(code -X POST -H "Origin: $B" -H "X-CT-Token: $T" \
          -H 'Content-Type: application/json' \
          -d '{"run_dir":"2026-08-30","ad_ids":[]}' "$B/jobs/bids/preview")
if grep -q '/jobs/bids/preview' webapp/routes/jobs.py 2>/dev/null; then
  test "$ok_code" -lt 400
  check V-SAFE-02c2 "입찰가 미리보기 POST → 2xx/3xx (현재 $ok_code)" $?
else
  test "$ok_code" = "404"
  check V-SAFE-02c2 "입찰가 미리보기 라우트는 아직 없다 → 정확히 404 (현재 $ok_code) · Plan 01-07 이 만들면 -lt 400 으로 자동 강화" $?
fi

# ── SAFE-03 ─────────────────────────────────────────────────────────────────

# V-SAFE-03  응답 본문·로그 어디에도 광고 시크릿이 없다. 값은 절대 출력하지 않는다.
S=$(python3 -c "import json,pathlib
p=pathlib.Path.home()/'.eroom/naver-ads.json'
print(json.loads(p.read_text())['accounts'][0]['secret_key'] if p.is_file() else '')" 2>/dev/null)
if [ -z "$S" ]; then
  echo "SKIP V-SAFE-03  광고 계정 설정이 없는 환경이다"
else
  leaked=0
  curl -s --max-time 10 -H "Cookie: ct_session=$T" "$B/" | grep -q -- "$S" && leaked=1
  if [ -d webapp-logs ]; then
    grep -rq -- "$S" webapp-logs/ 2>/dev/null && leaked=1
  fi
  check V-SAFE-03 "응답 본문·webapp-logs 에 광고 시크릿 0건" "$leaked"
fi

echo "----"
if [ "$fails" -eq 0 ]; then
  echo "보안 9종 전량 PASS"
else
  echo "FAIL 이 있다 — 여기서 멈춰라"
fi
exit "$fails"
