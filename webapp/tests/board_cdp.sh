#!/usr/bin/env bash
# 보드 브라우저 동작 검증 — 헤드리스 크롬을 띄워 **실제 JS 를 실행**하고 확인한다.
#
# security_curl.sh 와 같은 계층이다: 자동 pytest 스위트에 안 들어가고,
# 살아 있는 서버에 대고 손으로 돌린다. 보드 JS(webapp/static/board.js)를
# 건드렸으면 이걸 돌려라.
#
# 쓰는 법 (터미널 2개):
#   A) CT_DEV_TOKEN=devtoken123 ./webapp/run-webapp.sh
#   B) CT_DEV_TOKEN=devtoken123 bash webapp/tests/board_cdp.sh
#
# 왜 필요한가: 2026-09-20 에 "건수 배지가 필터보다 한 스텝 뒤처지는" 버그가 있었다.
# 필터를 바꾸면 숫자가 *움직이긴 해서* 육안 확인으로는 PASS 가 나왔다.
# 두 번 연속 바꿔 직전 값과 대조해야만 드러나는 종류다 — 그래서 기계가 본다.
#
# 변수·함수 이름을 한글로 쓰지 않는다. macOS 기본 bash 는 3.2 라 비ASCII 식별자에서
# "command not found" 로 죽는다(security_curl.sh 에서 실측한 교훈). 설명만 한국어다.
set -uo pipefail

cd "$(dirname "$0")/../.."

PORT="${CT_PORT:-8765}"
T="${CT_DEV_TOKEN:-}"
B="http://127.0.0.1:$PORT"
CHROME="${CHROME_BIN:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
DEVPORT="${CT_CDP_PORT:-9222}"

if [ -z "$T" ]; then
  echo "CT_DEV_TOKEN 이 없다. 서버를 그 값으로 띄우고 같은 값을 여기에도 줘라:" >&2
  echo "  CT_DEV_TOKEN=devtoken123 ./webapp/run-webapp.sh" >&2
  exit 2
fi

if [ ! -x "$CHROME" ]; then
  echo "크롬을 못 찾았다: $CHROME" >&2
  echo "CHROME_BIN 으로 경로를 넘겨라." >&2
  exit 2
fi

if ! command -v node >/dev/null 2>&1; then
  echo "node 가 없다. CDP 드라이버가 node 의 내장 WebSocket 을 쓴다." >&2
  exit 2
fi

if [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$B/healthz")" = "000" ]; then
  echo "서버가 $B 에 없다. 터미널 A 에서 ./webapp/run-webapp.sh 를 먼저 띄워라" >&2
  exit 2
fi

PROFILE="$(mktemp -d -t ct-chrome)"
CHROME_PID=""

cleanup() {
  [ -n "$CHROME_PID" ] && kill "$CHROME_PID" 2>/dev/null
  sleep 1
  [ -n "$CHROME_PID" ] && kill -9 "$CHROME_PID" 2>/dev/null
  # mktemp -d 가 만든 것만 지운다. 경로가 비었거나 / 면 아무것도 안 한다.
  case "$PROFILE" in
    /*/ct-chrome*) rm -rf "$PROFILE" ;;
  esac
}
trap cleanup EXIT

# --headless 로 띄우고 CDP 를 연다. 토큰이 붙은 URL 로 들어가면 서버가 303 으로
# 쿠키를 심고 깨끗한 / 로 털어낸다 — 실제 사용자 동선과 같다.
"$CHROME" \
  --headless \
  --disable-gpu \
  --no-sandbox \
  --no-first-run \
  --window-size=1600,1000 \
  --remote-debugging-port="$DEVPORT" \
  --user-data-dir="$PROFILE" \
  "$B/?t=$T" >/dev/null 2>&1 &
CHROME_PID=$!

# CDP 가 열릴 때까지 기다린다
WSURL=""
for _ in $(seq 1 40); do
  sleep 0.5
  WSURL=$(curl -s --max-time 2 "http://127.0.0.1:$DEVPORT/json" 2>/dev/null \
    | node -e '
      let s="";
      process.stdin.on("data",d=>s+=d).on("end",()=>{
        try{
          const t=JSON.parse(s).find(x=>x.type==="page"&&/127\.0\.0\.1/.test(x.url||""));
          if(t&&t.webSocketDebuggerUrl) process.stdout.write(t.webSocketDebuggerUrl);
        }catch(e){}
      });' 2>/dev/null)
  [ -n "$WSURL" ] && break
done

if [ -z "$WSURL" ]; then
  echo "크롬 CDP 에 붙지 못했다 (포트 $DEVPORT)." >&2
  exit 2
fi

node webapp/tests/board_cdp.mjs "$WSURL"
exit $?
