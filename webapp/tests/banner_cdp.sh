#!/usr/bin/env bash
# 전장 노출 브라우저 회귀 — **D-03a 를 사람의 기억이 아니라 기계가 지킨다.**
#
# sse_cdp.sh 와 같은 계층이다: pytest 밖, 살아 있는 서버 대상. 헤드리스 크롬을 띄워
# 실제 htmx 클릭을 하고, 그 클릭이 DB 에 남았는지 sqlite3 로 확인한다.
# `banner_review.html` · `_banner_strip.html` · `routes/banner.py` 를 건드렸으면 돌려라.
#
# 쓰는 법:
#   bash webapp/tests/banner_cdp.sh
#
# **배너 스캔을 실제로 돌리지 않는다. 크레딧 0 · 네트워크 0 · 4분 기다림 0.**
#   · 서버를 임시 포트에 따로 띄우고 잡 레지스트리·로그를 mktemp 로 돌린다
#     (CT_DB_PATH / CT_JOB_LOG_DIR). 저장소 루트의 webapp.db 를 건드리지 않는다.
#   · 산출물은 이 스크립트가 만든 **합성 JSON** 이고, 잡 행을 `done` 으로 직접 넣어
#     `jobs.latest_done` 이 그걸 가리키게 한다. 자식 프로세스는 하나도 안 띄운다.
#   · 회차는 실제 목록에서 최신 하나를 **읽기만** 한다 (화이트리스트를 통과해야 하므로).
#
# ⚠️ 썸네일만은 저장소의 썸네일 루트(`banner_thumb_dir`)에 실제로 쓴다 — 그 경로는
#    설정에서만 오고 환경변수로 못 바꾼다. 그래서 `zzcdp_` 접두 파일만 만들고
#    cleanup 에서 그것만 지운다. 그 디렉터리는 .gitignore 대상이다.
#
# 변수·함수 이름을 한글로 쓰지 않는다. macOS 기본 bash 는 3.2 라 비ASCII 식별자에서
# "command not found" 로 죽는다(security_curl.sh 에서 실측한 교훈). 설명만 한국어다.
set -uo pipefail

cd "$(dirname "$0")/../.."

CHROME="${CHROME_BIN:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
DEVPORT="${CT_CDP_PORT:-9334}"
T="ct-banner-$$"
PY=".venv-web/bin/python"

for need in "$CHROME" "$PY"; do
  [ -x "$need" ] || { echo "없다: $need" >&2; exit 2; }
done
command -v node >/dev/null 2>&1 || { echo "node 가 없다 (CDP 드라이버가 내장 WebSocket 을 쓴다)" >&2; exit 2; }
command -v sqlite3 >/dev/null 2>&1 || { echo "sqlite3 가 없다 (라벨이 DB 에 남았는지 봐야 한다)" >&2; exit 2; }

PORT=$("$PY" -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()')
B="http://127.0.0.1:$PORT"
WORK="$(mktemp -d -t ct-banner)"
PROFILE="$(mktemp -d -t ct-chrome)"
SERVER_PID=""
CHROME_PID=""
THUMB_DIR=""

cleanup() {
  [ -n "$CHROME_PID" ] && kill "$CHROME_PID" 2>/dev/null
  [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null
  sleep 1
  [ -n "$CHROME_PID" ] && kill -9 "$CHROME_PID" 2>/dev/null
  [ -n "$SERVER_PID" ] && kill -9 "$SERVER_PID" 2>/dev/null
  # 우리가 만든 접두 파일만 지운다. 디렉터리째 지우면 실제 스캔 결과를 날린다.
  if [ -n "$THUMB_DIR" ] && [ -d "$THUMB_DIR" ]; then
    rm -f "$THUMB_DIR"/zzcdp_*.webp
    rmdir "$THUMB_DIR" 2>/dev/null
  fi
  case "$PROFILE" in /*/ct-chrome*) rm -rf "$PROFILE" ;; esac
  case "$WORK" in /*/ct-banner*) rm -rf "$WORK" ;; esac
}
trap cleanup EXIT

export CT_PORT="$PORT"
export CT_DEV_TOKEN="$T"
export CT_DB_PATH="$WORK/jobs.db"
export CT_JOB_LOG_DIR="$WORK/logs"

# ── 합성 산출물 + 썸네일 + `done` 잡 행 ─────────────────────────────────────
# 배너 스캔 자식을 안 띄운다. 여기서 만드는 것은 그 CLI 가 썼을 모양의 JSON 이고,
# (그 스크립트 파일 이름을 주석에도 안 남긴다 — 이 파일이 자식을 띄우지 않는다는
#  사실을 acceptance 가 글자로 확인한다),
# **장 수와 배너 수를 일부러 다르게** 만든다 — 둘이 같으면 "배너만 깔렸다" 는 버그가
# 통과한다. 판매자상품코드는 전부 zz* 가짜다(conftest 의 익명화 규율).
SETUP=$("$PY" - "$WORK" <<'PY'
import json
import sys
from pathlib import Path

from webapp import banner, jobs, paths

work = Path(sys.argv[1])
회차들 = paths.scan_run_dirs()
if not 회차들:
    print("NORUN", flush=True)
    raise SystemExit(0)
회차 = 회차들[0]

썸루트 = jobs.banner_dir("banner_thumb_dir") / 회차
썸루트.mkdir(parents=True, exist_ok=True)

# 1x1 WebP(VP8L). 실제 바이트여야 `FileResponse` 가 200 을 내고 브라우저가 그린다.
WEBP = bytes.fromhex(
    "52494646 1a000000 57454250 5650384c 0d000000 2f000000 00071011 11888888 fe07"
    .replace(" ", ""))

def 상품(코드, 장수, 배너순번, 스킵=None):
    장 = []
    for i in range(장수):
        판정 = banner.배너 if i in 배너순번 else banner.제품
        이름 = f"zzcdp_{코드}_{i:02d}.webp"
        (썸루트 / 이름).write_bytes(WEBP)
        장.append({"순번": i, "url": f"https://zzcdn.example/{코드}-{i}.jpg",
                   "w": 800, "h": 900, "판정": 판정,
                   "사유": ("어휘군:공장직판" if 판정 == banner.배너 else None),
                   "썸네일": 이름})
    return {"판매자상품코드": 코드, "불사자코드": "b" + 코드,
            "타오바오상품번호": "tb-" + 코드, "상세상태": "중국어원본",
            "장수": 장수, "스킵사유": 스킵, "사유": ("제거율 82%" if 스킵 else None),
            "제거율": 0.82 if 스킵 else 0.1, "제품이미지": [], "장": 장}

상품들 = [상품("zzcdp01", 16, (0, 5)),
        상품("zzcdp02", 3, (1,), 스킵=banner.제거율초과)]
총장 = sum(len(p["장"]) for p in 상품들)
총배너 = sum(1 for p in 상품들 for c in p["장"] if c["판정"] == banner.배너)

문서 = {"소요초": 252.4,
      "판정규칙": {"어휘군버전": "zzcdp", "vision_revision": 3},
      "집계": {"상품": len(상품들), "장": 총장, "판정완료": 총장, "미판정": 0,
              banner.배너: 총배너, banner.제품: 총장 - 총배너,
              banner.무내용: 0, "스킵상품": 1},
      "상품": 상품들}
산출물 = work / "banner_zzcdp.json"
산출물.write_text(json.dumps(문서, ensure_ascii=False), encoding="utf-8")

# 잡 행을 직접 넣는다. `create_job` 은 자식을 띄우는데, 이 검증은 스캔을 안 돌린다.
jobs.init_db()
cx = jobs._conn()
try:
    cx.execute(
        "INSERT INTO jobs (id, kind, run_dir, argv, status, log_path, result_path, "
        "started_at) VALUES (?,?,?,?,?,?,?,?)",
        ("zzcdp-0001", "banner_scan", 회차, "[]", "done",
         str(work / "logs" / "zzcdp.log"), str(산출물), "2026-01-01T00:00:00+09:00"))
    cx.commit()
finally:
    cx.close()

# 셸이 쓸 값. **한 줄에 하나씩** 찍는다 — 저장소 경로에 공백이 있을 수 있어서
# 한 줄을 단어로 쪼개는 방식은 쓰지 않는다.
for 값 in ("OK", 회차, 총장, 총배너, 1, len(상품들[1]["장"]), 썸루트):
    print(값, flush=True)
PY
)

STATUS=$(printf '%s\n' "$SETUP" | sed -n '1p')
case "$STATUS" in
  NORUN)
    echo "판정된 회차가 하나도 없다 — 보드에서 새로 수집부터 돌려라 (읽기만 한다)." >&2
    exit 2 ;;
  OK) : ;;
  *)
    echo "합성 산출물을 못 깔았다:" >&2; echo "$SETUP" >&2; exit 2 ;;
esac

RUNDIR=$(printf '%s\n' "$SETUP" | sed -n '2p')
TOTAL=$(printf '%s\n' "$SETUP" | sed -n '3p')
BANNERS=$(printf '%s\n' "$SETUP" | sed -n '4p')
SKIP_I=$(printf '%s\n' "$SETUP" | sed -n '5p')
SKIP_N=$(printf '%s\n' "$SETUP" | sed -n '6p')
THUMB_DIR=$(printf '%s\n' "$SETUP" | sed -n '7p')
echo "회차 $RUNDIR · 장 $TOTAL (배너 $BANNERS) · 스킵 상품 순번 $SKIP_I (${SKIP_N}장)"

# ── 임시 서버 ───────────────────────────────────────────────────────────────
./webapp/run-webapp.sh >"$WORK/server.log" 2>&1 &
SERVER_PID=$!

for _ in $(seq 1 40); do
  sleep 0.25
  [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "$B/healthz")" = "200" ] && break
done
if [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "$B/healthz")" != "200" ]; then
  echo "임시 서버가 안 떴다:" >&2; cat "$WORK/server.log" >&2; exit 2
fi

# ── 헤드리스 크롬 ───────────────────────────────────────────────────────────
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

# ── 화면 검사 ① ② + 클릭 ───────────────────────────────────────────────────
node webapp/tests/banner_cdp.mjs "$DEVPORT" "$B" "$T" "$RUNDIR" \
  "$TOTAL" "$BANNERS" "$SKIP_I" "$SKIP_N"
SCREEN_RC=$?

# ── 검사 ③ ④ — 클릭이 **DB 에 실제로 남았나** ───────────────────────────────
# 테두리 클래스만 바뀌고 DB 가 비면 실패다. 그게 "미탐 0%" 를 거짓말로 만드는 모양이다.
count() { sqlite3 "$WORK/jobs.db" "select count(*) from $1" 2>/dev/null; }
LABELS=$(count banner_label)
CONFIRMS=$(count banner_confirm)

DB_RC=0
if [ "$LABELS" = "1" ]; then
  echo "PASS V-BANNER-03  장 클릭이 banner_label 에 1행으로 남았다  (${LABELS}행)"
else
  echo "FAIL V-BANNER-03  장 클릭이 DB 에 안 남았다 — 테두리만 바뀌고 저장이 안 됐다  (banner_label ${LABELS:-읽기실패}행, 기대 1)"
  DB_RC=1
fi

if [ "$CONFIRMS" = "1" ] && [ "$LABELS" = "1" ]; then
  echo "PASS V-BANNER-04  확인함은 banner_confirm 에만 쓴다 (라벨 증가 없음)  (confirm $CONFIRMS · label $LABELS)"
else
  echo "FAIL V-BANNER-04  확인이 라벨과 섞였다 — '뒤집었다' 와 '다 봤다' 는 다른 사실이다  (confirm ${CONFIRMS:-읽기실패} 기대 1 · label ${LABELS:-읽기실패} 기대 1)"
  DB_RC=1
fi

echo "----"
if [ "$SCREEN_RC" -eq 0 ] && [ "$DB_RC" -eq 0 ]; then
  echo "배너 CDP 검증 전량 PASS — 전장 노출이 기계로 고정됐다 (D-03a)"
  exit 0
fi
echo "FAIL 이 있다 — 여기서 멈춰라 (화면 rc=$SCREEN_RC · DB rc=$DB_RC)"
exit 1
