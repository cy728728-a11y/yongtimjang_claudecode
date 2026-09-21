---
phase: 03-join-detail-state
plan: 04
subsystem: bulsaja-cli
tags: [bulsaja-mcp, rate-limit, 429, ss-index, checkpoint, eng-08, join-03, join-04]

# Dependency graph
requires:
  - phase: 03-join-detail-state
    plan: 01
    provides: "settings 8키 + workspace.toml [webapp] · test_cli_shim.py · detail_batch.py 의 shim 관용구(윈도 경로 제거)"
  - phase: 03-join-detail-state
    plan: 02
    provides: "webapp/join.py 의 재검증판정·attach·strip_display_rules — 이 CLI 산출물을 읽는 쪽"
  - phase: 03-join-detail-state
    plan: 03
    provides: "webapp.db 의 ss_index DDL · BulsajaArgv 플래그 계약 · 잡 kind 3종 · SINGLETON_KINDS 가드"
provides:
  - ".claude/skills/bulsaja-detail-page/scripts/bulsaja_rate.py — 호출간격(주입 가능한 시계) · 안전호출(429 를 (None, True) 로 강제). stdlib time 하나만 import"
  - ".claude/skills/bulsaja-detail-page/scripts/ss_index_build.py — 그룹 단위 인덱스 구축 · productId 집합 체크포인트 · 미조회 명시 기록 · 종료코드 0/2/3/4"
  - ".claude/skills/bulsaja-detail-page/scripts/bulsaja_scan.py — 계정 확인(--profile-only) · 회차 조인 스캔 → join_<job>.json · 팬아웃 2단 배치"
  - "webapp/tests/test_index.py §8 — 레이트리밋·429 검증 8종 (가짜 시계, 실제 sleep 0)"
  - "webapp/tests/test_cli_shim.py — CLI 2종 --help 스모크 + 판정 금지·쓰기 금지·스키마 금지 가드"
affects: [03-05-routes, 03-06-board-ui, 03-07-실탄, phase-05-detail-page]

# Tech tracking
tech-stack:
  added: []   # 새 외부 패키지 0건
  patterns:
    - "레이트리밋 규율을 stdlib 전용 모듈로 떼어 두 venv 양쪽에서 검증 가능하게 만든다"
    - "실패를 예외가 아니라 `(값, 미조회여부)` 튜플로 강제해 호출부가 기록을 빠뜨릴 수 없게 한다"
    - "재개 기준은 순서가 아니라 집합 — 외부 목록의 정렬이 보장되지 않을 때의 체크포인트"
    - "CLI 는 관측만 적고 판정 어휘를 소스에 두지 않는다 (문자열 가드로 집행)"
    - "빈 대상은 전량이 아니다 — 자식이 스스로 exit 2 로 거부하는 2층 방어"

key-files:
  created:
    - .claude/skills/bulsaja-detail-page/scripts/bulsaja_rate.py
    - .claude/skills/bulsaja-detail-page/scripts/ss_index_build.py
    - .claude/skills/bulsaja-detail-page/scripts/bulsaja_scan.py
  modified:
    - webapp/tests/test_index.py
    - webapp/tests/test_cli_shim.py

key-decisions:
  - "`안전호출` 이 마지막 시도 뒤에는 자지 않는다 — 포기가 확정된 뒤 21초를 더 자면 그룹당 수십 분이 헛낭비다"
  - "미조회로 적힌 행은 **다음 실행이 다시 시도한다** — 성공행만 건너뛴다. 플랜은 '처리한 productId 집합'만 말했는데, 그대로면 429 로 빠진 상품이 영원히 미조회로 굳는다"
  - "산출물 요약을 이번 실행분이 아니라 **DB 의 현재 상태**로 낸다 — 재개 실행에서도 맞는 숫자여야 `group_health` 와 어긋나지 않는다"
  - "`제외그룹` 을 `null` 로 적었다 — 자식에게 그 설정을 주는 플래그가 없다. 빈 배열은 '제외 없음'이라는 거짓말이 된다"
  - "`eroomlib.snapshot.collect_group` 을 쓰지 않았다 — 자체 sleep 으로 간격의 주인이 둘이 되고, 그룹 전체 개수를 반환하지 않는다"
  - "스캔의 최종 로그가 미조회를 **행에서 다시 센다** — 429 카운터만 찍으면 인덱스 부재 시 '미조회 0' 이라는 거짓 안심 신호가 나간다"

patterns-established:
  - "주입 가능한 시계로 레이트리밋을 검증한다 — 3시간짜리 잡을 돌리지 않고도 규율이 증명된다"
  - "판정 어휘를 CLI 소스에서 문자열로 금지해 '두 번째 판정 구현'이 자라지 못하게 한다"
  - "치명적 사유는 stdout·stderr 양쪽에 flush 로 남긴다 (잡 레코드가 보관하는 건 stderr 꼬리다)"

requirements-completed: [ENG-08, JOIN-03, JOIN-04]

# Metrics
duration: 52min
completed: 2026-09-21
---

# Phase 3 Plan 04: 불사자 MCP CLI 3종 Summary

**불사자 MCP 를 만지는 코드 전부가 `.claude/skills/bulsaja-detail-page/scripts/` 아래 3개 파일로 섰다 — 그리고 `webapp/` 어디에도 없다(D-19). 초당 4회 상한과 429 미조회 기록이 가짜 시계로 검증되므로, 3시간 32분짜리 잡을 실제로 돌리지 않고도 이 페이즈 최대 위험 둘(Pitfall 2·3)이 막혔다는 걸 기계가 말한다.**

## Performance

- **Duration:** 약 52분
- **Tasks:** 3 / 3
- **Tests:** 284 → **293 passed** (신규 9: 레이트리밋 8 + 스모크·가드 4 중 일부는 기존 파일 확장)
- **Files:** 신규 3 · 수정 2
- **크레딧 소모:** **0** — 실제로 나간 MCP 호출은 `bulsaja_my_profile` 한 번뿐이다(스캔 가드 스모크가 계정이 다른 것을 확인하고 exit 3)

## 무엇이 생겼나

### 1. `bulsaja_rate.py` (117행) — 이 페이즈 최대 위험을 막는 60줄

| 이름 | 계약 |
|---|---|
| `호출간격(최소간격, now_fn, sleep_fn)` | `.대기()` → **실제로 잔 시간(초)**. 첫 호출은 0 |
| `안전호출(fn, *, 재시도대기, 횟수=6, sleep_fn, 로그)` | `(결과, 미조회여부)`. 429 가 아닌 예외는 **그대로 올린다** |

**`import time` 한 줄 말고는 아무것도 import 하지 않는다.** 그게 설계의 핵심이다 —
MCP 를 끌어오는 순간 `.venv-web` 의 pytest 가 이 모듈을 import 조차 못 하고(그 venv 에
`requests` 가 없다), 그러면 레이트리밋 규율이 **3시간 32분짜리 잡을 실제로 돌려야만**
검증되는 물건이 된다. `test_레이트모듈은_stdlib만_쓴다` 가 그 선을 기계로 지킨다.

`time.time` 이 아니라 `time.monotonic` 을 기본 시계로 둔 이유를 주석에 박았다:
3시간 넘게 도는 루프 중에 NTP 보정이 끼면 `time.time` 기반 간격은 **음수가 되거나
(= 상한을 통째로 무시) 몇 시간을 잔다.**

`(None, True)` 반환이 `continue` 대신인 이유도 주석에 있다 — 호출부가 미조회를 **기록하지
않고는 진행할 수 없게** 만드는 구조적 장치다. 조용히 건너뛰면 그 상품이 화면에서
"미해소(= 광고 쪽 오류)" 로 보이고, 용팀장이 멀쩡한 광고그룹을 지우러 간다.

### 2. `ss_index_build.py` (429행)

| 종료코드 | 뜻 | 언제 |
|---|---|---|
| 0 | 정상 | — |
| **2** | 훑을 대상 없음 | `--groups` 가 없거나 빈 배열. **MCP·SQLite 를 건드리기 전** |
| **3** | 기대 계정이 아니다 | 프로필 1회 조회 직후. **SQLite 에 한 글자도 쓰기 전** |
| **4** | `ss_index` 가 없다 | 테이블을 만들지 않고 죽는다 (정본은 `webapp/jobs.py`) |

**체크포인트는 페이지 번호가 아니라 처리한 `productId` 집합이다.** 그룹 시작마다
`SELECT product_id FROM ss_index WHERE market_group_id = ?` 로 집합을 만들고, 거기 없는
것만 조회한다. 건마다 `INSERT OR REPLACE` + `commit` — 28,000건짜리 그룹이 있어서
메모리에 쌓으면 중단 시 통째로 날아간다.

`mode="summary"` 이고 `call_tool` **원본**을 부른다. `ProductMCP` 의 workdata 헬퍼는
`uploadedSuccessUrl` 을 투영에서 버려서, 그걸 썼으면 인덱스 히트율이 0%가 됐다(Pitfall 1).

### 3. `bulsaja_scan.py` (445행)

산출물은 `03-01-PLAN.md` §interfaces 의 조인 잡 스키마 그대로다. **판정 어휘가 소스에
0건**이고, `test_스캔_CLI_는_판정을_하지_않는다` 가 그걸 문자열로 집행한다.

`uploadDetailContents` 를 **키 부재까지 그대로** 싣는다 — `aiImageGenerated` 는 값이
거짓이 되는 게 아니라 키가 통째로 없다(실측 34건). 여기서 기본값을 채우면 읽는 쪽의
상태 판정이 뒤집히고, ⚪ 상품이 🟡로 내려앉아 Phase 5 가 크레딧을 다시 태운다.

팬아웃은 2단 **배치** 조회다: `판매자상품코드` → 사본 묶음 키 → 사본 전체.
`uploadBulsajaCode` 가 묶음 키가 아니라 판매자상품코드라는 실측 정정이 그 2단의 이유다.

## 두 CLI 를 실제로 돌려 확인한 것 (가짜 MCP · 네트워크 0)

플랜의 수용 기준은 `--help` 와 `grep` 이 대부분이라 **루프가 진짜 도는지는 증명되지
않는다.** 그래서 가짜 MCP 를 꽂아 스크래치패드에서 두 스크립트의 `main()` 을 통째로 돌렸다:

**인덱스 빌더**
- 3상품(1 정상 · 1 항상 429 · 1 업로드 안 됨)에서 적재 결과가
  `[(P1, '1…1', 0), (P2, None, 1), (P3, None, 0)]` — 미조회가 **행으로 남는다**
- 같은 명령을 다시 돌리면 **성공행은 workdata 호출 0회**, 미조회행만 1회 재시도 →
  두 번째 실행에서 `완결=True` 로 뒤집힌다
- 계정이 다르면 exit 3 이고 `ss_index` 행 수가 그대로 · 산출물 미생성 · **프로필 파일은 생성**
- 스키마 없는 DB 에서 exit 4

**스캔 → 조인 통합 (03-02 와의 접합)**
산출물을 `.venv-web` 에서 `join.attach()` 에 그대로 먹였다:

| 행 | 상황 | 조인 결과 |
|---|---|---|
| 1 | 인덱스값 == 관측값 | 해소 · `단순번역만` · 기작업 True · 사본 2건 · 잠금혼재 True |
| 2 | 물갈이 재발급(값이 달라짐) | 미해소 / **시스템** 버킷 |
| 3 | 인덱스에 없음 | 미해소 / **시스템** 버킷 |

해상률 집계의 `광고청소` 가 **0행**이다 — 우리가 못 본 것이 광고 쪽 오류로 둔갑하지
않는다는 것이 이 페이즈 최대 오진(Pitfall 3)의 실증이다.

## Deviations from Plan

### 1. [Rule 2 - 누락된 필수 방어] 미조회 행을 다음 실행이 다시 시도한다

- **Found during:** Task 2
- **Issue:** 플랜은 재개 기준을 "이미 처리한 productId 집합" 으로만 적었다. 그대로 구현하면
  429 로 미조회가 된 행도 "처리됨" 에 들어가서 **영원히 미조회로 굳는다.** 그러면 잡을 몇 번
  다시 돌려도 그 행은 화면에서 계속 "인덱스 불완전" 이고, 사람이 고칠 방법이 없다.
- **Fix:** 재개 집합에서 `unresolved = 1` 인 행을 빼서 다시 시도하게 했다. 성공행만 건너뛴다.
  가짜 MCP 검증에서 두 번째 실행이 미조회 1건만 재조회하고 `완결` 이 뒤집히는 것을 확인했다.
- **Files:** `ss_index_build.py`
- **Commit:** `2f60b59`

### 2. [Rule 1 - 거짓 신호] 진행 요약을 이번 실행분이 아니라 DB 현재 상태로 낸다

- **Found during:** Task 2
- **Issue:** 이번 실행에서 처리한 건수로 요약을 내면, 재개 실행(이번에 1건만 처리)에서
  `행수=1 · 완결=False` 가 나온다. 그런데 DB 에는 3행이 다 있다. 웹앱의
  `bulsaja_index.group_health()` 와 **두 값이 어긋나고**, 화면은 DB 를 본다.
- **Fix:** 그룹 종료 시 DB 에서 다시 집계해 요약한다. `완결` 공식도 `group_health` 와
  글자 그대로 같게 맞췄다(`행수 > 0 and 미조회 == 0 and (총계 is None or 행수 >= 총계)`).
  "둘이 어긋나면 DB 가 정본" 이라는 사실을 주석에 적었다.
- **Files:** `ss_index_build.py`
- **Commit:** `2f60b59`

### 3. [Rule 1 - 거짓 안심 신호] 스캔 최종 로그의 미조회 수

- **Found during:** Task 3
- **Issue:** 미조회 카운터를 429 실패만으로 올렸더니, 인덱스가 아직 없어서 **전 행이
  미조회**인 실행에서 마지막 줄이 `미조회 0` 으로 찍혔다. SSE 화면에서 읽히는 그 한 줄이
  정확히 거짓 안심 신호다.
- **Fix:** 행에서 다시 센다. 레이트리밋 몫은 괄호로 따로 보인다.
- **Files:** `bulsaja_scan.py`
- **Commit:** `69c9f3b`

### 4. [계약 판단] `제외그룹` 을 `null` 로 적었다

- **Found during:** Task 3
- **Issue:** `03-01-PLAN.md` 의 산출물 스키마는 `"제외그룹": ["<마켓번호>", ...]` 로 적혀 있는데,
  **자식에게 그 설정을 주는 플래그가 없다.** `BulsajaArgv`(03-03 확정)에 없고, 03-03 이 이미
  "플래그 집합이 계약" 이라고 못박았으므로 여기서 새 플래그를 파면 계약이 갈라진다.
- **Fix:** 빈 배열 대신 `null` 을 적고 이유를 주석에 남겼다 — 빈 배열은 "제외 없음"이라는
  **거짓말**이고, `null` 은 "모른다"다. 실제 제외 설정은 웹앱이 `settings` 에서 읽어
  `join.attach(excluded=...)`·`join.index_targets(excluded=...)` 로 넘기며, 산출물의 이 키를
  읽는 코드는 03-02 어디에도 없다(확인함). 설정의 정본은 한 곳이다.
- **Files:** `bulsaja_scan.py`
- **Commit:** `69c9f3b`

### 5. [Rule 3 - 헛낭비] `안전호출` 이 마지막 시도 뒤에는 자지 않는다

- **Found during:** Task 1
- **Issue:** 재시도 루프를 곧이곧대로 쓰면 **포기가 이미 확정된 뒤에** `Retry-After` 만큼
  한 번 더 잔다. 6회 × 21초면 건당 21초 헛낭비고, 429 가 몰리는 구간에서는 그게 그룹당
  수십 분이 된다.
- **Fix:** 마지막 시도 뒤에는 자지 않고 곧바로 `(None, True)`. `test_429뒤_성공하면_결과를_준다`
  와 `test_재시도대기는_서버요구를_따른다` 가 대기 횟수·값을 양쪽으로 고정한다.
- **Files:** `bulsaja_rate.py`
- **Commit:** `161f633`

### 6. [범위 추가] 스캔 CLI 에 가드 테스트 3종을 더했다

플랜은 `test_스캔이_뜬다` 하나만 요구했다. 수용 기준의 `grep` 3개(판정 어휘 0건 ·
`mode=ro` 존재 · 테이블 생성문 0건)는 **사람이 한 번 돌리고 끝나는 검사**라, 다음 플랜이
소스를 고칠 때 아무도 안 본다. 그래서 같은 검사를 pytest 로 올렸다
(`test_스캔_CLI_는_판정을_하지_않는다` · `test_스캔은_인덱스를_읽기만_한다` ·
`test_인덱스빌더가_스키마를_만들지_않는다`). 이 저장소가 이미 쓰는 방식이다
(`test_cli_shim.test_윈도_경로가_남아있지_않다`).

## 인증 게이트

없었다. `bulsaja` MCP 토큰은 `~/.claude.json` 에 이미 있고 `bulsaja_mcp` 가 런타임에 읽는다 —
웹앱도 이 플랜도 토큰을 만지지 않는다(T-3-22).

## 검증

```
.venv-web/bin/pytest webapp/tests -q                          → 293 passed
.venv-web/bin/pytest webapp/tests/test_index.py -q            → 0.21s (실제 sleep 0)
.venv/bin/python3 ss_index_build.py --help                    → exit 0
.venv/bin/python3 bulsaja_scan.py --help                      → exit 0
.venv/bin/python3 detail_batch.py --help                      → exit 0 (03-01 회귀)
bash webapp/tests/no_commit_guard.sh                          → OK
빈 --groups → exit 2 · DB 미생성                               → PASS
빈 --targets / 계정 다름 → exit 2|3 · 산출물 미생성              → PASS (exit 3)

grep -cE '^(import|from) ' bulsaja_rate.py    → 1  (그 줄이 `import time`)
grep -c 'CREATE TABLE'   ss_index_build.py    → 0
grep -c 'INSERT OR REPLACE INTO ss_index' …   → 1
grep -c 'unresolved'     ss_index_build.py    → 7
grep -c 'mode.*summary'  ss_index_build.py    → 2
grep -c '\.workdata('    ss_index_build.py    → 0   (Pitfall 1)
grep -c 'flush=True'     ss_index_build.py    → 4
grep -cE '(용쌤|번_|13-2)' ss_index_build.py   → 0   (D-18 리터럴 0건)
grep -cE '(히트|불일치)'  bulsaja_scan.py       → 0   (판정을 안 한다)
grep -c '표시규칙'        bulsaja_scan.py       → 12
grep -c 'find_by_code'   bulsaja_scan.py       → 4   (배치 루프 안)
grep -c 'mode=ro'        bulsaja_scan.py       → 4
```

**네거티브 확인 (03-01·03-03 의 규율 승계):**
- `bulsaja_rate` 를 만들기 전 테스트 8종이 `ModuleNotFoundError` 로 **전부 빨개지는 것**을
  먼저 봤다(RED 커밋 `0e53a16`).
- throttle 을 끈 상태(`최소간격=0`)로 같은 계측을 돌려 최소 간격이 `0.0` 으로 떨어지는 것을
  확인했다 — `test_초당4회_상한` 이 실제로 문다.
- 판정 어휘 가드를 `webapp/join.py` 에 걸어 보면 걸린다(`히트`·`불일치` 둘 다 True).
  스키마 가드도 `webapp/jobs.py` 에 걸면 걸린다. **"FAIL 을 본 적 없는 검증은 검증이 아니다."**

## Known Stubs

없다. 세 파일 모두 가짜 MCP 로 `main()` 을 끝까지 돌려 적재·재개·미조회·팬아웃·
산출물 스키마를 확인했다. 다만 **실제 불사자 서버를 상대로 한 완주는 아직 없다** —
그건 스텁이 아니라 이 플랜의 명시적 범위 제한이다(실탄 인덱스는 03-07 이 사람 승인 아래 돈다).

실서버에서만 드러날 수 있는 것 둘을 기록해 둔다:
1. `bulsaja_market_group_products` 응답의 **전체 개수 필드 이름.** 실측 근거가 없어
   `전체개수 · 총상품수 · 총개수 · 전체` 네 이름을 순서대로 본다. 다 없으면 `group_total` 이
   `NULL` 이 되고, `group_health` 는 그 경우 `총상품수 is None` 으로 취급해 **`완결` 을
   행수만으로 판단**한다. 지어내지 않는 쪽을 골랐다.
2. `bulsaja_product_find_by_code` 의 **배치 인자 이름을 `codes` 로 가정**했다(A3 계열 가정).
   03-07 첫 실탄에서 1배치로 확인하고, 다르면 그 한 줄만 고치면 된다.

## Threat Flags

없다. 이 플랜이 만진 표면은 전부 `<threat_model>` 에 등록돼 있다(T-3-18 ~ T-3-24).
새 네트워크 엔드포인트·인증 경로·신뢰 경계는 0건이고, MCP 접촉면은 기존
`bulsaja_mcp.BulsajaMCP` 하나 그대로다.

| 위협 | 어디서 막혔나 |
|---|---|
| T-3-18 초당 4회 초과 | `호출간격` · `test_초당4회_상한` |
| T-3-19 429 를 성공으로 접기 | `안전호출` 이 `(None, True)` 강제 · `unresolved=1` 행 |
| T-3-20 `표시규칙` 저장 | 쓰기 직전 재귀 제거 (두 CLI 모두) + pytest 가드 |
| T-3-21 틀린 계정으로 적재 | 프로필 1회 → exit 3 (SQLite 쓰기 전) |
| T-3-22 토큰·이메일 유출 | 프로필 산출물에 닉네임·크레딧·확인시각만 |
| T-3-23 스키마 두 벌 | 테이블 생성문 0건 + exit 4 + pytest 가드 |
| T-3-24 페이지 기준 재개 | `productId` 집합 체크포인트 |

## 다음 플랜에 넘기는 것

- **03-05 (라우트):** CLI 종료코드를 화면 문구로 번역할 때 **2·3·4 를 한 칸에 담지 마라.**
  2 = "고를 대상이 없다(사람이 고칠 것)" · 3 = "계정이 다르다(연결을 바꿔라)" ·
  4 = "스키마가 없다(서버를 한 번 띄워라)" — 고치는 주체가 전부 다르다.
- **03-06 (보드):** 스캔 산출물의 `제외그룹` 은 `null` 이다. 화면의 제외 표시는
  `settings.cfg("index_excluded_groups")` 에서 읽어라 — 산출물에서 읽으면 안 된다.
  `사본` 의 `잠금` 이 섞이면 `join.attach` 가 `잠금혼재=True` 를 채운다(실증 확인).
- **03-07 (실탄):** 첫 실행은 **작은 그룹 하나에 `--limit` 을 걸고** 돌려라. 확인할 것 둘:
  ① 진행 로그의 `(서버 집계 N건)` 이 실제 숫자로 찍히는가(위 Known Stubs 1)
  ② `사본 조회 1단` 이 0건이 아닌가(위 Known Stubs 2 — 인자 이름 확인).
  둘 다 읽기 전용이라 크레딧은 0이다. `caffeinate -i` 프리픽스는 `BulsajaArgv.prefix` 가 붙인다.

## Self-Check: PASSED

- 파일 5종 존재 확인: `bulsaja_rate.py` · `ss_index_build.py` · `bulsaja_scan.py` ·
  `webapp/tests/test_index.py` · `webapp/tests/test_cli_shim.py`
- 커밋 4건 확인: `0e53a16`(RED) · `161f633`(T1) · `2f60b59`(T2) · `69c9f3b`(T3)
- 삭제된 추적 파일 0건 (`git diff --diff-filter=D 86b7de5..HEAD` 비어 있음)
- STATE.md · ROADMAP.md 미수정 (오케스트레이터 소유)
- `webapp/` 아래 `eroomlib`/`requests` import 0건 유지 — 이 플랜이 만진 `webapp/` 파일은
  테스트 2개뿐이고, 둘 다 `test_cli_patch.py:21-31` 이 허가한 **테스트 전용** `sys.path`
  삽입만 쓴다. 런타임 소스는 한 줄도 안 건드렸다.
- 워크트리에 심었던 `.venv`·`.venv-web`·`workspace.toml` 심볼릭 링크 제거 확인
