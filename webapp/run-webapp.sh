#!/usr/bin/env bash
# 셀러 관제탑 기동. 127.0.0.1 전용 · 워커 1개.
#
# 기동하면 마지막 줄에 이런 URL 이 찍힌다. 그걸 브라우저에 붙여넣어라:
#   → http://127.0.0.1:<포트>/?t=<토큰>
#
# 토큰은 서버 재시작마다 바뀐다. 그게 의도다 — 어디 적어 두지 마라.
# 개발 중 --reload 로 돌릴 때만 CT_DEV_TOKEN 으로 고정해라:
#   CT_DEV_TOKEN=devtoken123 ./webapp/run-webapp.sh --reload
set -euo pipefail

cd "$(dirname "$0")/.."

PY=".venv-web/bin/python"
if [ ! -x "$PY" ]; then
  echo "웹앱 가상환경이 없다. 먼저 만들어라:" >&2
  echo "  uv venv .venv-web --python 3.12" >&2
  echo "  uv pip install --python .venv-web/bin/python fastapi uvicorn jinja2 sse-starlette pytest httpx" >&2
  exit 1
fi

# 포트를 여기 박지 않는다 — settings 가 유일한 출처다(workspace.toml [webapp] port 로 바뀐다).
# 포트를 두 곳에 적으면 한쪽만 고쳤을 때 Origin 화이트리스트가 조용히 깨진다.
PORT="${CT_PORT:-$("$PY" -c 'from webapp import settings; print(settings.PORT)')}"

# --host 127.0.0.1 : 인증이 없는 앱이다. 0.0.0.0 으로 열면 같은 와이파이의 아무나
#                    내 광고 입찰가를 올릴 수 있다.
# --workers 1      : 협상 불가다. 워커가 갈라지면 잡 레지스트리와 SSE 구독자 집합이
#                    프로세스별로 나뉜다. 잡을 띄운 워커와 스트림 요청을 받은 워커가
#                    다르면 진행 로그가 안 뜬다 — "가끔 로그가 안 보인다" 는
#                    재현 안 되는 버그로 나타난다 (Pitfall 9).
exec "$PY" -m uvicorn webapp.main:app \
  --host 127.0.0.1 \
  --port "$PORT" \
  --workers 1 \
  "$@"
