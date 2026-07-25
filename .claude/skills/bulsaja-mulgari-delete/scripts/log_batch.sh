#!/usr/bin/env bash
# 물갈이 삭제 한 배치를 구글시트 '물갈이로그' 탭에 append.
# 사용: bash log_batch.sh <targets_tsv> <batch_idx> <taskId> <group_name> <YYYY-MM-DD> <spreadsheetId>
# - targets_tsv: "productId\t상품명" 줄들 (배치순, 20개씩)
# - 한글 깨짐 방지: emit_log_body.py가 \uXXXX ASCII로 인코딩해 넘김
set -o pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

TSV="$1"; IDX="$2"; TASKID="$3"; GROUP="$4"; DATE="$5"; SID="$6"

if [ -z "$SID" ]; then
  echo "ERR: 인자 부족 — 사용: log_batch.sh <tsv> <idx> <taskId> <group> <date> <spreadsheetId>"
  exit 1
fi

BODY="${TSV%.tsv}_body_${IDX}.json"
python "$DIR/emit_log_body.py" "$TSV" "$IDX" "$TASKID" "$GROUP" "$DATE" > "$BODY" || { echo "ERR: body 생성 실패 batch $IDX"; exit 1; }

gws sheets spreadsheets values append \
  --params "{\"spreadsheetId\":\"$SID\",\"range\":\"물갈이로그!A1\",\"valueInputOption\":\"USER_ENTERED\",\"insertDataOption\":\"INSERT_ROWS\"}" \
  --json "$(cat "$BODY")" --format json 2>&1 | grep -o '"updatedRows"[: ]*[0-9]*' || echo "ERR batch $IDX (append 응답 확인 필요)"
