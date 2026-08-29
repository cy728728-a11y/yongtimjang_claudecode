#!/bin/zsh
# 매일 자동 실행 래퍼. 기본은 미리보기(삭제 안 함).
# 실삭제로 바꾸려면 MODE=apply 로 두거나 plist 의 환경변수를 바꾼다.
set -u

DIR="$(cd "$(dirname "$0")" && pwd)"
MODE="${MODE:-preview}"
REPORT="$DIR/logs/daily-report.md"
mkdir -p "$DIR/logs"

if [ "$MODE" = "apply" ]; then
  ARGS="--apply"
else
  ARGS=""
fi

# 네이버는 자동전달이 없어 IMAP 으로 직접 끌어온다 (수집이 먼저, 그 다음 정리)
NAVER="$(/usr/bin/python3 "$DIR/naver_pull.py" --apply 2>&1 | grep -E "^네이버수집:|Error|Traceback" | tail -1)"
OUT="$(/usr/bin/python3 "$DIR/imap_triage.py" $ARGS 2>&1)"
STAMP="$(date '+%Y-%m-%d %H:%M')"

# 요약 두 줄만 리포트에 누적한다 (상세는 logs/*.json)
SUMMARY="$(printf '%s\n' "$OUT" | grep -E '삭제 대상|대상 [0-9]+건|완료\.' | tr '\n' ' ')"

# 보고서 발송 — 새 메일도 삭제도 없으면 스크립트가 알아서 안 보낸다
DEL_N="$(printf '%s\n' "$OUT"   | grep -oE '삭제 대상 [0-9]+' | grep -oE '[0-9]+' | head -1)"
NAV_N="$(printf '%s\n' "$NAVER" | grep -oE '[0-9]+' | head -1)"
MAILRPT="$(/usr/bin/python3 "$DIR/report_mail.py" --send \
            --deleted "${DEL_N:-0}" --naver "${NAV_N:-0}" 2>&1 | tail -1)"
{
  echo "- **$STAMP** [$MODE] ${SUMMARY:-실행 실패}"
  echo "    - 네이버: ${NAVER:-없음}"
  echo "    - 보고서: ${MAILRPT:-없음}"
  if printf '%s\n' "$OUT" | grep -q '실패\|Traceback'; then
    echo "    - ⚠️ $(printf '%s\n' "$OUT" | tail -3 | tr '\n' ' ')"
  fi
} >> "$REPORT"
