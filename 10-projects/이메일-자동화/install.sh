#!/bin/zsh
# 자동 실행용 런타임을 ~/Documents 밖(~/.local/share/mail-triage)으로 설치한다.
#
# 왜: launchd 로 뜬 프로세스는 macOS TCC 때문에 ~/Documents 안의 파일을 읽지 못한다
# (stat 은 되고 open 은 거부). 그래서 매일 자동 실행되는 런타임만 밖에 둔다.
# 규칙(rules.py)을 고쳤으면 이 스크립트를 다시 돌려서 설치본을 갱신할 것.
set -eu
SRC="$(cd "$(dirname "$0")" && pwd)"
DST="$HOME/.local/share/mail-triage"
mkdir -p "$DST/logs"
cp "$SRC/rules.py" "$SRC/imap_triage.py" "$SRC/naver_pull.py" "$SRC/report_mail.py" "$SRC/run_daily.sh" "$DST/"
chmod +x "$DST/run_daily.sh"
echo "설치 완료: $DST"
