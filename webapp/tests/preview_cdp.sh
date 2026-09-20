#!/usr/bin/env bash
# 선택 → 미리보기 브라우저 검증 — 헤드리스 크롬에서 **실제 JS 를 실행**한다.
#
# security_curl.sh · board_cdp.sh · sse_cdp.sh 와 같은 계층이다: 자동 pytest 스위트에
# 안 들어가고, 살아 있는 서버에 대고 돌린다. 보드 선택 JS(webapp/static/board.js)나
# 미리보기 표(_preview_table.html)를 건드렸으면 이걸 돌려라.
#
# 쓰는 법 (터미널 2개):
#   A) CT_DEV_TOKEN=devtoken123 ./webapp/run-webapp.sh
#   B) CT_DEV_TOKEN=devtoken123 bash webapp/tests/preview_cdp.sh
#
# 왜 필요한가:
#   Tabulator 의 행 선택은 **브라우저 JS 안에서만** 산다. TestClient 는 JS 를 한 줄도
#   실행하지 않아 "헤더 체크박스가 무엇을 고르는가" 를 못 본다. 그런데 거기에
#   증상 없는 사고가 있다 — 헤더 체크박스에 rowRange 를 안 주면 Tabulator 가
#   **필터를 무시하고 전체 행**을 고른다(벤더 소스 실측). 화면엔 걸러진 행만 보이는데
#   선택은 전체다. 육안으로는 영원히 안 잡힌다.
#
#   그리고 이 스크립트는 **실제로 미리보기를 접수한다.** dry-run 이라 광고 API 를
#   한 번도 안 부르고 크레딧도 광고비도 0 이다 — 대신 `run-dir/web/` 에 대상·미리보기
#   파일이 잡마다 한 쌍씩 생긴다(그게 FLOW-02 의 증거다).
#
# 변수·함수 이름을 한글로 쓰지 않는다. macOS 기본 bash 는 3.2 라 비ASCII 식별자에서
# "command not found" 로 죽는다(security_curl.sh 에서 실측한 교훈). 설명만 한국어다.
set -uo pipefail

cd "$(dirname "$0")/../.."

PORT="${CT_PORT:-8765}"
T="${CT_DEV_TOKEN:-}"
B="http://127.0.0.1:$PORT"
CHROME="${CHROME_BIN:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
DEVPORT="${CT_CDP_PORT:-9223}"

# 실데이터 기준점. 이 소재는 useGroupBid=true 라 **그룹 기본가 70 에서 출발해 80** 이다.
# 웹앱이 재계산하면 잠자던 bidAmt 50 에서 출발해 50→60 이 된다 — 즉 올리려다 내린다.
# 회차·소재를 바꿀 수 있게 환경변수로 뺀다(숫자는 CLI 산출물에서 읽으므로 안 박는다).
RUN_DIR="${CT_RUN_DIR:-2026-08-30}"
TARGET_AD="${CT_TARGET_AD:-nad-a001-02-000000495390006}"

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

PROFILE="$(mktemp -d -t ct-chrome-pre)"
CHROME_PID=""

cleanup() {
  [ -n "$CHROME_PID" ] && kill "$CHROME_PID" 2>/dev/null
  sleep 1
  [ -n "$CHROME_PID" ] && kill -9 "$CHROME_PID" 2>/dev/null
  case "$PROFILE" in
    /*/ct-chrome-pre*) rm -rf "$PROFILE" ;;
  esac
}
trap cleanup EXIT

# 회차를 쿼리로 못박고 들어간다 — 기본 회차가 바뀌어도 기준점이 흔들리지 않게.
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

node webapp/tests/preview_cdp.mjs "$WSURL" "$B" "$RUN_DIR" "$TARGET_AD"
exit $?
