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

# **저장소 루트에서 돈다.** 다른 하네스는 전부 이렇게 하는데 여기만 빠져 있어서,
# 딴 데서 부르면 상대경로 검사(webapp-logs · webapp/*.py 스캔)가 조용히 건너뛰어졌다.
cd "$(dirname "$0")/../.."
ROOT="$(pwd)"

PORT="${CT_PORT:-8765}"
T="${CT_DEV_TOKEN:-}"
B="http://127.0.0.1:$PORT"
# **실재하는 회차를 아예 안 쓴다.** 예전엔 2026-08-30 이 박혀 있어서 그 회차가
# 사라지면(정리했거나 다른 PC) 보안 검증이 보안과 무관한 이유로 빨개졌다 — 빨개진
# 보안 스크립트는 곧 안 돌리는 스크립트가 된다. 환경변수로 빼는 것도 생각했지만,
# 그러면 다른 하네스용으로 그 변수를 export 해 둔 세션에서 **실재 회차가 들어와
# 부수효과가 되살아나고**(실측: 그 상태로 돌리면 c2 가 400 인데 사유가 회차가 아니라
# 대상 검증이라 FAIL 한다) 검사의 뜻도 달라진다. 회차 의존 자체를 없애는 쪽이 맞다.
# PID 를 붙여 실재 회차(ISO 날짜)와 절대 겹치지 않게 한다.
NOSUCH_RUN="없는회차-$$"
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
#   ※ 역사: VALIDATION.md 원문은 grep 하나로 줄바꿈을 건너뛰려 했는데 grep 은 줄
#      단위라 그 패턴이 **영원히 매치되지 않아 항상 PASS** 했다(빈 통과 1세대).
#      그 다음 판은 "GET 데코레이터 아래 60줄에서 위험 이름을 직접 찾는" 방식이었는데
#      ① **래퍼 한 겹이면 통과**했고(이 저장소엔 이미 `_작업만들기` 라는 래퍼가 있다 —
#      GET 핸들러가 그걸 부르면 스캐너는 통과시켰다) ② docstring 이 긴 핸들러에서는
#      60줄 상한 너머가 아예 안 보였다. 문구("상태를 바꾸는 GET 0건")가 증명한 것보다
#      셌다 — 빈 통과 2세대다.
#
#      지금 판은 **ast 로 호출 관계를 따라간다**: GET 핸들러에서 도달 가능한 함수
#      집합을 전부 펼쳐서 그 안에 위험 이름이 있는지 본다. 줄 수 상한이 없고
#      (함수 경계를 ast 가 정확히 안다), 래퍼를 몇 겹 끼워도 뚫리지 않는다.
python3 - <<'PY'
import ast, sys
from pathlib import Path

# 쓰기를 일으키는 이름들. 여기에 CLI 플래그 리터럴은 넣지 않는다 —
# webapp/tests 트리에 그 문자열이 있으면 no_commit_guard.sh 가 막는다(그게 맞다).
RISK = {"create_job", "spawn", "Popen", "run_bids", "run_revert"}

정의 = {}          # 함수이름 → 그 본문이 건드리는 이름 집합 (모듈을 가로질러 합친다)
GET핸들러 = []      # (파일, 함수이름, 줄)


def 건드리는이름(node) -> set:
    """이 함수 본문이 언급하는 모든 이름. **호출만 보지 않는다** — 함수를 변수에
    담아 넘기는 경로도 위험으로 본다. 보안 스캐너는 넘치게 잡는 쪽이 옳다."""
    이름 = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            이름.add(n.id)
        elif isinstance(n, ast.Attribute):
            이름.add(n.attr)
    return 이름


def GET인가(fn) -> bool:
    for d in fn.decorator_list:
        f = d.func if isinstance(d, ast.Call) else d
        if isinstance(f, ast.Attribute) and f.attr == "get" \
                and isinstance(f.value, ast.Name) and f.value.id in ("app", "router"):
            return True
    return False


파일들 = [f for f in sorted(Path("webapp").rglob("*.py")) if "tests" not in f.parts]
if not 파일들:
    print("스캔할 파일이 0개다 — 저장소 루트에서 돌려라")
    sys.exit(1)

for f in 파일들:
    tree = ast.parse(f.read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        정의.setdefault(n.name, set()).update(건드리는이름(n))
        if GET인가(n):
            GET핸들러.append((str(f), n.name, n.lineno))

if not GET핸들러:
    print("GET 핸들러를 0개 찾았다 — 스캐너가 눈이 멀었다")
    sys.exit(1)

bad = []
for 파일, 이름, 줄 in GET핸들러:
    본것, 남은것 = set(), list(정의.get(이름, ()))
    while 남은것:
        n = 남은것.pop()
        if n in 본것:
            continue
        본것.add(n)
        남은것.extend(정의.get(n, ()))
    걸린것 = sorted(본것 & RISK)
    if 걸린것:
        bad.append(f"{파일}:{줄} {이름}() → {' · '.join(걸린것)}")

for b in bad:
    print("상태를 바꾸는 GET 의심:", b)
print(f"(GET 핸들러 {len(GET핸들러)}개를 호출관계로 훑었다)")
sys.exit(1 if bad else 0)
PY
check V-SAFE-01d "상태를 바꾸는 GET 엔드포인트 0건 (호출관계 추적)" $?

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
     -H 'Content-Type: application/json' -d "{\"run_dir\":\"$NOSUCH_RUN\"}" "$B/jobs/run")
c1_code=$(printf '%s' "$c1" | tail -1)
c1_body=$(printf '%s' "$c1" | sed '$d')
ok=1
if [ "$c1_code" = "400" ]; then
  printf '%s' "$c1_body" | grep -q '회차' && ok=0
fi
check V-SAFE-02c1 "정상 쓰기가 가드 3층을 통과해 앱 로직에 닿는다 (400 + 사유, 현재 $c1_code)" "$ok"

#   ※ c2 는 **부수효과가 0 이어야 한다.** 예전 판은 실재하는 회차에 빈 ad_ids 로
#      쐈는데, 그건 진짜로 bids_preview 잡을 만들고 CLI 자식을 띄웠다
#      (ad_ids:[] → accounts=[] → --account 없음 → 전 계정 dry-run). 광고비는 0 이지만
#      보안 검증을 돌릴 때마다 회차 web/ 에 targets_*·preview_* 가 쌓이고 잡
#      레지스트리에 유령 작업이 남았다 — c1 주석이 "부수효과 0" 이라고 적어 둔
#      원칙을 c2 만 안 지켰다. 그리고 회차 `2026-08-30` 이 박혀 있어 그 회차가
#      사라지면 보안 검증이 보안과 무관한 이유로 빨개졌다.
#      지금 판은 **없는 회차 + 모양이 맞는 ad_ids** 를 보낸다. 가드 3층(Host·Origin·
#      토큰)을 통과해 앱 로직이 400 + 사유로 답하는 것까지 똑같이 증명하면서,
#      회차 화이트리스트에서 거부되므로 잡도 파일도 안 생긴다.
c2=$(curl -s --max-time 10 -w '\n%{http_code}' -X POST -H "Origin: $B" -H "X-CT-Token: $T" \
     -H 'Content-Type: application/json' \
     -d "{\"run_dir\":\"$NOSUCH_RUN\",\"ad_ids\":[\"nad-a001-02-000000495390006\"]}" \
     "$B/jobs/bids/preview")
c2_code=$(printf '%s' "$c2" | tail -1)
c2_body=$(printf '%s' "$c2" | sed '$d')
ok=1
if [ "$c2_code" = "400" ]; then
  printf '%s' "$c2_body" | grep -q '회차' && ok=0
fi
check V-SAFE-02c2 "미리보기 라우트가 가드 3층을 통과해 앱 로직에 닿는다 (400 + 사유, 현재 $c2_code · 부수효과 0)" "$ok"

# ── SAFE-03 ─────────────────────────────────────────────────────────────────

# V-SAFE-03  응답 본문·로그 어디에도 광고 시크릿이 없다. 값은 절대 출력하지 않는다.
S=$(python3 -c "import json,pathlib
p=pathlib.Path.home()/'.eroom/naver-ads.json'
print(json.loads(p.read_text())['accounts'][0]['secret_key'] if p.is_file() else '')" 2>/dev/null)
if [ -z "$S" ]; then
  echo "SKIP V-SAFE-03  광고 계정 설정이 없는 환경이다"
else
  # **먼저 "이게 진짜 보드다" 를 못박는다.** 예전 판은 응답 내용을 안 봤다 —
  # 쿠키가 안 맞으면 본문이 403 안내문이고, 서버를 뽑아 놓으면 빈 문자열이다.
  # 어느 쪽이든 시크릿이 없으니 **초록**이었다. CT_DEV_TOKEN 과 서버 토큰이
  # 어긋난 채로 돌리면 "시크릿 0건" 이 거짓으로 통과한다. 검사가 성립하지
  # 않는 상태와 검사를 통과한 상태를 같은 화면으로 두지 않는다.
  # **파이프로 넘기지 않고 파일로 받는다.** `set -o pipefail` 이 켜져 있는데
  # `printf '%s' "$body" | grep -q` 는 grep 이 먼저 끝나면 printf 가 SIGPIPE 로 죽어
  # 파이프라인 종료코드가 141 이 된다 — 보드를 멀쩡히 받았는데 "못 받았다" 로
  # 빨개진다. 보드가 2.4MB(6,945행)라 이 경합이 실제로 난다(실측: 8회 중 2회 141).
  # 보안과 무관한 이유로 빨개지는 스크립트는 곧 안 돌리는 스크립트가 된다(WR-11).
  BODY_FILE="$(mktemp -t ct-sec-body)"
  curl -s --max-time 30 -o "$BODY_FILE" -H "Cookie: ct_session=$T" "$B/"
  if ! grep -q 'id="board-rows"' "$BODY_FILE"; then
    # 못 받은 걸 초록으로 넘기지 않는다 — 검사가 성립하지 않는 상태와 검사를
    # 통과한 상태를 같은 화면으로 두지 않는 것이 이 항목의 요지다.
    check V-SAFE-03 "보드를 못 받았다 — 시크릿 검사가 성립하지 않는다 (토큰·서버 확인)" 1
  else
    leaked=0
    grep -q -- "$S" "$BODY_FILE" && leaked=1
    # 상대경로 금지 — 저장소 루트가 아닌 데서 부르면 조용히 건너뛰어졌다.
    LOGDIR="$ROOT/webapp-logs"
    if [ -d "$LOGDIR" ]; then
      grep -rq -- "$S" "$LOGDIR"/ 2>/dev/null && leaked=1
      check V-SAFE-03 "응답 본문(보드 확인됨)·webapp-logs 에 광고 시크릿 0건" "$leaked"
    else
      # 로그 디렉터리가 없으면 "로그에 0건" 을 증명한 게 아니다 — 그렇다고 말한다.
      check V-SAFE-03 "응답 본문(보드 확인됨)에 광고 시크릿 0건 · webapp-logs 없음(로그 검사 못 했다)" "$leaked"
    fi
  fi
  rm -f "$BODY_FILE"
fi

echo "----"
if [ "$fails" -eq 0 ]; then
  echo "보안 9종 전량 PASS"
else
  echo "FAIL 이 있다 — 여기서 멈춰라"
fi
exit "$fails"
