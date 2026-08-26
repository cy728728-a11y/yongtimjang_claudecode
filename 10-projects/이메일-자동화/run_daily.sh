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

OUT="$(/usr/bin/python3 "$DIR/imap_triage.py" $ARGS 2>&1)"
STAMP="$(date '+%Y-%m-%d %H:%M')"

# 요약 두 줄만 리포트에 누적한다 (상세는 logs/*.json)
SUMMARY="$(printf '%s\n' "$OUT" | grep -E '삭제 대상|대상 [0-9]+건|완료\.' | tr '\n' ' ')"
{
  echo "- **$STAMP** [$MODE] ${SUMMARY:-실행 실패}"
  if printf '%s\n' "$OUT" | grep -q '실패\|Traceback'; then
    echo "    - ⚠️ $(printf '%s\n' "$OUT" | tail -3 | tr '\n' ' ')"
  fi
} >> "$REPORT"
