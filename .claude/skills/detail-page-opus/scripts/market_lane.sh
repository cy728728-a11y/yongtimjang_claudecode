#!/bin/zsh
# 마켓 지정 고퀄 상세 한 줄(검수 생략) — MARKET=25-2 TAG=m1 LIMIT=100 zsh market_lane.sh
cd "$(dirname "$0")"
B=~/python_work/data/detail-opus/batches; PY=../../../../.venv/bin/python3; export PYTHONIOENCODING=utf-8
: ${MARKET:?} ${TAG:?} ${LIMIT:?}
N=mk-$(date +%m%d)-${MARKET}-${TAG}
if [ ! -f $B/$N/targets.json ]; then
  $PY -u targets_market.py --market $MARKET --limit $LIMIT --out $N > $B/targets-$N.log 2>&1
fi
n=$(python3 -c "import json;print(len(json.load(open('$B/$N/targets.json'))['targets']))" 2>/dev/null || echo 0)
echo "$N 대상 $n $(date '+%m-%d %H:%M')"
[ "$n" -eq 0 ] && exit 0
# 다른 줄이 24시간 지난 배치로 오해하지 않게 targets.json 을 주기적으로 갱신
( while [ ! -f $B/$N/summary.md ]; do touch $B/$N/targets.json; sleep 3000; done ) &
caffeinate -i $PY -u batch.py --batch $N >> $B/$N/batch.log 2>&1
echo "== 끝 $N $(date '+%m-%d %H:%M')"
