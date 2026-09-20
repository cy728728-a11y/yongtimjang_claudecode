#!/usr/bin/env bash
# 진행 로그 SSE 브라우저 검증 — 헤드리스 크롬에서 **실제 탭을 닫았다 다시 연다.**
#
# security_curl.sh · board_cdp.sh 와 같은 계층이다: pytest 밖, 살아 있는 서버 대상.
# `_job_panel.html` 이나 `logtail.py` 를 건드렸으면 이걸 돌려라.
#
# 쓰는 법:
#   bash webapp/tests/sse_cdp.sh
#
# **광고 API 를 한 번도 안 부른다. 광고비·크레딧 0.**
#   · 서버를 임시 포트에 따로 띄우고, 잡 레지스트리·로그를 mktemp 디렉터리로 돌린다
#     (CT_DB_PATH / CT_JOB_LOG_DIR). 저장소 루트의 webapp.db 를 건드리지 않는다.
#   · 태우는 작업은 합성 잡(fixtures/synthetic_job.py)이다. 네트워크 0.
#   · 보드 데이터는 실데이터를 읽기만 한다.
#
# 왜 pytest 가 아닌가: `_job_panel.html` 의 sse-swap 배선과 "탭을 닫았다 여는" 동작은
# **브라우저 JS 와 커넥션 생명주기**다. TestClient 는 JS 를 한 줄도 안 돌리고,
# ASGI 앱을 끝까지 돌린 뒤 본문을 통째로 준다(실측). pytest 로 흉내 내면
# "우리가 짠 가짜 htmx" 를 검증하게 된다.
#
# 변수·함수 이름을 한글로 쓰지 않는다. macOS 기본 bash 는 3.2 라 비ASCII 식별자에서
# "command not found" 로 죽는다(security_curl.sh 에서 실측한 교훈). 설명만 한국어다.
set -uo pipefail

cd "$(dirname "$0")/../.."

CHROME="${CHROME_BIN:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
DEVPORT="${CT_CDP_PORT:-9333}"
T="ct-sse-$$"
PY=".venv-web/bin/python"

# 합성 잡 모양. 40줄 × 0.4초 = 16초 — 붙었다 끊었다 다시 붙는 데 필요한 최소 길이다.
LINES="${CT_SSE_LINES:-40}"
DELAY="${CT_SSE_DELAY:-0.4}"

for need in "$CHROME" "$PY"; do
  [ -x "$need" ] || { echo "없다: $need" >&2; exit 2; }
done
command -v node >/dev/null 2>&1 || { echo "node 가 없다 (CDP 드라이버가 내장 WebSocket 을 쓴다)" >&2; exit 2; }

PORT=$("$PY" -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()')
B="http://127.0.0.1:$PORT"
WORK="$(mktemp -d -t ct-sse)"
PROFILE="$(mktemp -d -t ct-chrome)"
SERVER_PID=""
CHROME_PID=""
JOB_ID=""

cleanup() {
  # 합성 잡의 자식은 세션이 분리돼 있어 부모를 죽여도 산다 — pid 로 직접 끈다.
  if [ -n "$JOB_ID" ] && [ -f "$WORK/jobs.db" ]; then
    kid=$(sqlite3 "$WORK/jobs.db" "select pid from jobs where id='$JOB_ID'" 2>/dev/null)
    [ -n "$kid" ] && kill "$kid" 2>/dev/null
  fi
  [ -n "$CHROME_PID" ] && kill "$CHROME_PID" 2>/dev/null
  [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null
  sleep 1
  [ -n "$CHROME_PID" ] && kill -9 "$CHROME_PID" 2>/dev/null
  [ -n "$SERVER_PID" ] && kill -9 "$SERVER_PID" 2>/dev/null
  case "$PROFILE" in /*/ct-chrome*) rm -rf "$PROFILE" ;; esac
  case "$WORK" in /*/ct-sse*) rm -rf "$WORK" ;; esac
}
trap cleanup EXIT

export CT_PORT="$PORT"
export CT_DEV_TOKEN="$T"
export CT_DB_PATH="$WORK/jobs.db"
export CT_JOB_LOG_DIR="$WORK/logs"

./webapp/run-webapp.sh >"$WORK/server.log" 2>&1 &
SERVER_PID=$!

for _ in $(seq 1 40); do
  sleep 0.25
  [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "$B/healthz")" = "200" ] && break
done
if [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "$B/healthz")" != "200" ]; then
  echo "임시 서버가 안 떴다:" >&2; cat "$WORK/server.log" >&2; exit 2
fi

# 합성 잡을 **이 프로세스에서** 만든다. 운영 라우트는 합성 잡을 못 만든다(T-1-23) —
# 그게 맞고, 그래서 검증 스크립트가 엔진 함수를 직접 부른다. 서버는 같은
# 레지스트리 파일을 읽어 이 작업을 본다.
JOB_ID=$("$PY" - "$LINES" "$DELAY" <<'PY'
import sys
from webapp import jobs
from webapp.tests.conftest import SYNTHETIC_JOB
jobs.init_db()
print(jobs.create_job("synthetic", argv_override=[
    sys.executable, str(SYNTHETIC_JOB), sys.argv[1], sys.argv[2], "0"]))
PY
)
[ -n "$JOB_ID" ] || { echo "합성 잡을 못 만들었다" >&2; exit 2; }
echo "임시 서버 $B · 합성 잡 $JOB_ID (${LINES}줄 × ${DELAY}초)"
# 참고: 이 잡의 자식은 서버가 아니라 **이 스크립트**가 띄웠다. 그래서 서버의 인메모리
# Popen 맵에 없고, 끝나면 상태가 `done` 이 아니라 `orphaned`("결과 미상")로 잡힌다.
# 버그가 아니라 이 검증 방식의 부산물이다 — 여기서 보는 건 로그 흐름이지 종료코드가 아니다.

"$CHROME" \
  --headless \
  --disable-gpu \
  --no-sandbox \
  --no-first-run \
  --window-size=1600,1000 \
  --remote-debugging-port="$DEVPORT" \
  --user-data-dir="$PROFILE" \
  about:blank >/dev/null 2>&1 &
CHROME_PID=$!

for _ in $(seq 1 40); do
  sleep 0.5
  curl -s --max-time 2 "http://127.0.0.1:$DEVPORT/json/version" >/dev/null 2>&1 && break
done
if ! curl -s --max-time 2 "http://127.0.0.1:$DEVPORT/json/version" >/dev/null 2>&1; then
  echo "크롬 CDP 에 붙지 못했다 (포트 $DEVPORT)" >&2; exit 2
fi

node webapp/tests/sse_cdp.mjs "$DEVPORT" "$B" "$T" "$JOB_ID" "$LINES"
exit $?
