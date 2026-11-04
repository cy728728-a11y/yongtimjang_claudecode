#!/bin/zsh
# 고퀄 상세 한 줄(LANE=a|b|…) — 20건씩 쉬지 않고 순환. 여러 줄을 동시에 띄운다(2026-11-04 용팀장: 6줄).
# - 다른 줄이 잡은 상품은 targets.py 가 뺀다(진행 중 배치 = summary.md 없음·하루 이내).
# - 시작할 때 이 줄의 끝나지 않은 배치가 있으면 그것부터 이어서 끝낸다(세션 종료 등으로 끊긴 경우).
# - 한 라운드의 절반 이상이 실패면 60분 쉬고 다시, 연속 6번이면 멈춘다(한도 대기는 batch.py 가 상품 단위로 한다).
# - 후보 0이면 끝.
# 띄우기: LANE=a nohup zsh sheet_lane.sh >> ~/python_work/data/detail-opus/batches/lane-a.log 2>&1 &
cd "$(dirname "$0")"
B=~/python_work/data/detail-opus/batches; PY=../../../../.venv/bin/python3; export PYTHONIOENCODING=utf-8
: ${LANE:?LANE 필요}

run_batch() {   # $1 = 배치 이름
  caffeinate -i $PY -u batch.py --batch $1 >> $B/$1/batch.log 2>&1
  sed -n 3,4p $B/$1/summary.md 2>/dev/null
}

# 1) 끊긴 배치 이어서
for d in $B/sheet-*-${LANE}[0-9][0-9](N); do
  [ -f $d/summary.md ] && continue
  echo "[이어서] $(basename $d) $(date '+%m-%d %H:%M')"
  run_batch $(basename $d)
done

# 2) 새 라운드 — 번호는 같은 날짜 이 줄의 마지막 다음부터
bad=0
for k in $(seq 1 200); do
  day=$(date +%m%d)
  last=$(ls -d $B/sheet-$day-${LANE}[0-9][0-9](N) 2>/dev/null | sed -E 's/.*([0-9]{2})$/\1/' | sort -n | tail -1)
  N=sheet-$day-${LANE}$(printf %02d $(( ${last:-0} + 1 )))
  $PY -u targets.py --limit 20 --out $N > $B/targets-$N.log 2>&1
  n=$(python3 -c "import json;print(len(json.load(open('$B/$N/targets.json'))['targets']))" 2>/dev/null || echo 0)
  echo "[$k] $N 대상 $n $(date '+%m-%d %H:%M')"
  [ "$n" -eq 0 ] && { echo "후보 소진"; break; }
  run_batch $N
  f=$(python3 -c "
import json;s=json.load(open('$B/$N/state.json'))
print($n-sum(1 for v in s.values() if v.get('stage') in ('sent','held','inspect_drop')))" 2>/dev/null || echo $n)
  if [ $((f*2)) -ge $n ]; then
    bad=$((bad+1)); echo "  실패 $f/$n — 60분 쉼 (연속 $bad)"; [ $bad -ge 6 ] && { echo "연속 실패로 멈춤"; break; }; sleep 3600
  else bad=0; fi
done
echo "== 끝 $(date '+%m-%d %H:%M')"
