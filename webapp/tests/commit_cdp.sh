#!/usr/bin/env bash
# 실행 버튼 게이트(FLOW-01) 브라우저 검증 — 헤드리스 크롬에서 **실제 JS 를 실행**한다.
#
# security_curl.sh · board_cdp.sh · sse_cdp.sh · preview_cdp.sh 와 같은 계층이다:
# 자동 pytest 스위트에 안 들어가고, 살아 있는 서버에 대고 돌린다.
# board.js 의 실행 버튼 배선이나 board.html 의 경고 배너를 건드렸으면 이걸 돌려라.
#
# 쓰는 법 (터미널 2개):
#   A) CT_DEV_TOKEN=devtoken123 ./webapp/run-webapp.sh
#   B) CT_DEV_TOKEN=devtoken123 bash webapp/tests/commit_cdp.sh
#
# **광고비 0 이다.** 미리보기(dry-run)만 접수하고 실행 버튼은 누르지 않는다 —
# 이 스크립트가 보는 것은 "버튼이 언제 열리는가" 뿐이다. 실제 실행은 사람이
# 화면에서 누르는 것이고, 그건 자동화하지 않는다(그게 이 게이트의 존재 이유다).
#
# 왜 필요한가:
#   FLOW-01("미리보기 없이 실행할 수 없다")의 절반은 서버가, 절반은 화면이 진다.
#   서버 쪽은 pytest 가 본다(부모 잡의 kind·status 검사). 화면 쪽은 board.js 안에서만
#   살아서, 버튼이 언제 열리는지는 진짜 브라우저에서만 볼 수 있다. 그 절반이 깨지면
#   증상은 "버튼이 계속 눌린다" 이고, 그 다음은 본 적 없는 대상에 PUT 이다.
#
# 변수·함수 이름을 한글로 쓰지 않는다. macOS 기본 bash 는 3.2 라 비ASCII 식별자에서
# "command not found" 로 죽는다(security_curl.sh 에서 실측한 교훈). 설명만 한국어다.
set -uo pipefail

cd "$(dirname "$0")/../.."

PORT="${CT_PORT:-8765}"
T="${CT_DEV_TOKEN:-}"
B="http://127.0.0.1:$PORT"
CHROME="${CHROME_BIN:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
DEVPORT="${CT_CDP_PORT:-9224}"

# 회차는 환경변수로 뺀다 — 기본 회차가 바뀌어도 기준점이 흔들리지 않게.
# 숫자(건수·인상액)는 박지 않는다. 산출물에서 받아서 화면과 대조한다.
RUN_DIR="${CT_RUN_DIR:-2026-08-30}"

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

PROFILE="$(mktemp -d -t ct-chrome-cmt)"
CHROME_PID=""

cleanup() {
  [ -n "$CHROME_PID" ] && kill "$CHROME_PID" 2>/dev/null
  sleep 1
  [ -n "$CHROME_PID" ] && kill -9 "$CHROME_PID" 2>/dev/null
  case "$PROFILE" in
    /*/ct-chrome-cmt*) rm -rf "$PROFILE" ;;
  esac
}
trap cleanup EXIT

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

node webapp/tests/commit_cdp.mjs "$WSURL" "$B" "$RUN_DIR"
exit $?
