#!/usr/bin/env bash
# 되돌리기 버튼(BID-04 / D-14 / T-1-43) 브라우저 검증 — 헤드리스 크롬에서 **실제 JS 를 실행**한다.
#
# security_curl.sh · board_cdp.sh · sse_cdp.sh · preview_cdp.sh · commit_cdp.sh 와 같은
# 계층이다: 자동 pytest 스위트에 안 들어가고, 살아 있는 서버에 대고 돌린다.
# board.js 의 되돌리기 배선이나 board.html 의 위험 구역을 건드렸으면 이걸 돌려라.
#
# 쓰는 법 (터미널 2개):
#   A) CT_DEV_TOKEN=devtoken123 ./webapp/run-webapp.sh
#   B) CT_DEV_TOKEN=devtoken123 bash webapp/tests/revert_cdp.sh
#
# **되돌리기 요청이 서버에 한 건도 안 나간다.** 버튼 배선과 요청 본문을 확인해야 하는데
# 진짜로 보내면 실제 광고 입찰가가 내려간다 — 그래서 페이지 안에서 `window.fetch` 를
# 가로채고, **가로채기가 실제로 걸렸는지 프로브로 먼저 확인한 뒤에만** 버튼을 누른다.
# 마지막에 /jobs 를 다시 읽어 `revert_*` 잡이 0건인지 사후 확인까지 한다.
#
# 왜 필요한가:
#   D-14 의 요지는 "두 버튼이 떨어져 있다" 인데, 그건 pytest 로 못 잰다. 조각이 다르다는
#   것까지는 서버가 보장하지만(test_revert.py), **화면에서 실제로 몇 픽셀 떨어져 있는지**와
#   위험 구역이 접혀 있는지는 진짜 렌더링에만 있다. 이 화면의 최대 위험이 오클릭이다.
#
# 변수·함수 이름을 한글로 쓰지 않는다. macOS 기본 bash 는 3.2 라 비ASCII 식별자에서
# "command not found" 로 죽는다(security_curl.sh 에서 실측한 교훈). 설명만 한국어다.
set -uo pipefail

cd "$(dirname "$0")/../.."

PORT="${CT_PORT:-8765}"
T="${CT_DEV_TOKEN:-}"
B="http://127.0.0.1:$PORT"
CHROME="${CHROME_BIN:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
DEVPORT="${CT_CDP_PORT:-9225}"

# 회차는 환경변수로 뺀다 — 기본 회차가 바뀌어도 기준점이 흔들리지 않게.
# 건수는 박지 않는다. 서버에서 받아서 화면과 대조한다.
RUN_DIR="${CT_RUN_DIR:-2026-09-20}"

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

PROFILE="$(mktemp -d -t ct-chrome-rvt)"
CHROME_PID=""

cleanup() {
  [ -n "$CHROME_PID" ] && kill "$CHROME_PID" 2>/dev/null
  sleep 1
  [ -n "$CHROME_PID" ] && kill -9 "$CHROME_PID" 2>/dev/null
  case "$PROFILE" in
    /*/ct-chrome-rvt*) rm -rf "$PROFILE" ;;
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

node webapp/tests/revert_cdp.mjs "$WSURL" "$B" "$RUN_DIR"
exit $?
