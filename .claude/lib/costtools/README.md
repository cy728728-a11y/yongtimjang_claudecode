# costtools — 비용 계측 도구

근거 문서는 [`../../skills/product-name/references/팬아웃-비용.md`](../../skills/product-name/references/팬아웃-비용.md).
여기 있는 건 그 문서의 수치를 **다시 재는** 도구다.

## `wtel.py` — 워커 텔레메트리 집계

`.output` JSONL 에서 **usage 필드만** 읽는다. 본문은 절대 안 읽는다 — 서브에이전트 전체
트랜스크립트라 통째로 열면 호출자 컨텍스트가 넘친다.

```bash
python3 .claude/lib/costtools/wtel.py 대조군=<agentId> 실험군=<agentId>   # 두 군 비교
python3 .claude/lib/costtools/wtel.py --turns <agentId>                    # 턴별 과금
python3 .claude/lib/costtools/wtel.py --scan --minutes 90                  # 팬아웃 한 판 전체
```

`--scan` 은 최근 N분 안에 끝난 워커를 **전부** 합산하고 가중 총합($ 환산 포함)까지 낸다.
팬아웃은 워커가 수십 명이라 agentId 를 손으로 모을 수 없어서 만든 모드다. 기본 120분.
실측 직후에 부른다 — 창을 넓게 잡으면 관계없는 워커가 섞인다.

두 곳을 본다: `tasks/*.output`(Agent 도구 서브에이전트)와
`<프로젝트>/<세션id>/subagents/**/agent-*.jsonl`(**Workflow 팬아웃 워커**).
전에는 앞쪽만 봐서 팬아웃 한 판을 통째로 놓쳤다(2026-08-07 실측: 워커 23명 누락).

**기본은 현재 세션(`CLAUDE_CODE_SESSION_ID`)만** 집계한다 — 같은 프로젝트에서 다른 세션이
동시에 돌면 그 워커가 조용히 섞여 값이 부풀기 때문이다(실측 +16%).

```bash
python3 wtel.py --scan --minutes 50                  # 현재 세션만(기본)
python3 wtel.py --scan --minutes 50 --session <id>   # 다른 세션
python3 wtel.py --scan --minutes 50 --all-sessions   # 전부(섞이면 경고 + 세션별 내역)
```

한 턴이 스트리밍 스냅샷으로 여러 줄 기록되므로 `(cache_read, cache_creation)` 이 같은 연속
줄을 한 턴으로 접는다. 그냥 세면 턴도 토큰도 몇 배가 된다(실측 29줄 = 8턴).

agentId 로 tasks 디렉터리를 자동으로 찾는다. 못 찾으면 `EROOM_TASKS` 로 직접 지정.

## `pack_curve.py` — 워커 패킹 곡선

"워커 1명에게 몇 건을 맡기는 게 싼가". 워커 로그에서 **파생행만** 뽑아
`~/eroom-data/_telemetry/worker_packing.csv` 에 쌓는다. 워커 컨텍스트는 안 건드린다(비용 0).

```bash
python3 .claude/lib/costtools/pack_curve.py --collect            # 로그 → CSV (멱등)
python3 .claude/lib/costtools/pack_curve.py --curve              # 축별 곡선
python3 .claude/lib/costtools/pack_curve.py --curve --axis product-name
```

**팬아웃이 끝나면 바로 `--collect`.** 로그는 오래 안 남는다 — 구 `tasks/*.output` 은
/private/tmp 라 스캔 도중에도 사라졌다. 한 번 CSV 가 되면 영구다.

워커당 상품 수는 **distinct 상품id** 로 센다(배치 경로가 아니다 — 지시서의 예시 경로를 집는
사고가 있었고, 워커 1명이 배치를 3~8개 맡는다). 축·런도 로그의 eroom-data 경로에서 뽑는다.

`--curve` 는 워커 3명 미만 구간에 `(표본부족)` 을 붙인다. **그 구간으로 판단하지 마라** —
양 끝 1~2명짜리를 그대로 읽어 "6배 차이"로 오독한 전례가 있다(실제 3~6건 구간은 1.44배 안).

`items` 합이 런 상품 수를 넘는 건 정상이다(썸네일 run·audit·verdict 3패스 + 재팬아웃).

## `desc_check.py` — 스킬 description 안전장치

description 을 줄일 때 **트리거 어구가 사라지지 않았는지** HEAD 와 집합 비교한다.
큰따옴표 어구가 하나라도 빠지면 FAIL(exit 1). 작은따옴표·백틱은 WARN 만.

```bash
python3 .claude/lib/costtools/desc_check.py          # 전후 분량표 + 유실 검사
python3 .claude/lib/costtools/desc_check.py --list   # 현재 크기 순위
```

기준선은 `git show HEAD:<path>` 다 — **커밋 전에** 돌려야 전후 비교가 나온다.
커밋 후에 돌리면 전후가 같게 나오고 유실 검사만 유효하다.

토큰 수는 근사치다(한글 1자 ≈ 1토큰, ASCII 3.2자 ≈ 1토큰). 실제 토크나이저보다 한글에서
약 20% 적게 나온다 — **절대값이 아니라 증감을 보는 용도.**
