"""특정 마켓의 유입 상위 미가공 상품만 뽑는다(검수 생략). 사용: targets_market.py --market 25-2 --limit 100 --out 배치이름
다른 줄(sheet_lane)과 안 겹치게 targets.py 의 진행 중 배치 제외·파일 잠금을 그대로 쓴다. 2026-11-13 용팀장 지시."""
import os, sys
from pathlib import Path
import targets as T
if os.environ.get("TRAFFIC_DIR"):   # 마켓 전용 유입 분석 폴더(다른 줄이 쓰는 전체 목록과 분리)
    T.TRAFFIC_DIR = Path(os.environ["TRAFFIC_DIR"]).expanduser()

mk = sys.argv[sys.argv.index("--market") + 1]
i = sys.argv.index("--market"); del sys.argv[i:i + 2]
_orig = T.collect_traffic
def only_market(exclude):
    rows = [dict(x, noInspect=True) for x in _orig(exclude) if mk == "ALL" or x.get("market") == mk]
    rows.sort(key=lambda x: -x["clk"])
    for n, x in enumerate(rows): x["rank"] = n
    return rows
T.collect_traffic = only_market
T.collect_priority = lambda: ([], "없음(마켓 지정 모드)")
T.collect_sheet = lambda ex: []
T.collect_sold = lambda ex: []
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
T.locked_main()
