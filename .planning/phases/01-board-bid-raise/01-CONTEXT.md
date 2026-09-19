# Phase 1: 첫 왕복 — 보드 + 입찰가 인상 버튼 - Context

**Gathered:** 2026-09-19
**Status:** Ready for planning

<domain>
## Phase Boundary

터미널을 열지 않고 브라우저에서:
1. 광고 판정 결과를 **상품 단위 보드**로 보고 (계정·규칙·상태로 거르고 정렬·검색)
2. 규칙①(노출 0) 대상을 골라 **입찰가 인상 미리보기 → 실행 → 되돌리기** 를 완주한다
3. 그 과정에서 **이후 버튼 5개가 전부 올라탈 3단 실행 틀과 안전 뼈대**를 굳힌다
   (subprocess 실행 · append-only 로그 tail · SSE 재접속 이어보기 · 127.0.0.1 + Origin/Host + 부팅토큰 · 자격증명 비노출)

**이 단계가 진짜로 만드는 것은 버튼이 아니라 틀이다.** 입찰가는 되돌릴 수 있고 크레딧을 안 쓰고 조인이 필요 없어서,
틀에 결함이 드러나도 손해가 0인 대상으로 고른 것이다.

**이 단계에서 하지 않는 것** (다른 Phase 소관):
- 광고↔불사자 조인, 상세 상태 판정 (Phase 3)
- 꺼진 소재 삭제 · 작업 잠금 · 고아 작업 정리 · caffeinate · 감사 로그 JSONL · 재조회 스테일 거부 · 오판정 표시 (Phase 2)
- 상세페이지·썸네일·쿠팡 버튼 (Phase 4~7)

</domain>

<decisions>
## Implementation Decisions

### 기존 CLI 래핑 경계

- **D-01:** 기존 CLI 에 **입력 필터 플래그를 추가하는 것은 허용**한다 (예: `run_ads.py bids --only-ads targets.json`).
  `cmd_bids` 가 `result.json` 의 `①노출0` rows 를 그 파일의 adId 목록으로 **거르기만** 한다.
  **판정·입찰가 계산·백업·ledger 로직은 한 줄도 건드리지 않는다.**
  근거: 지금 `bids` 는 계정 전량을 돌 수밖에 없어 Success Criteria 2("행을 골라 미리보기")가 구조적으로 성립하지 않는다.
  필터된 `result.json` 사본으로 임시 run-dir 을 만드는 우회는 `before_bids_<alias>.json` 백업이 임시 run-dir 에 생겨
  되돌리기 근거가 회차마다 흩어지므로 채택하지 않았다.

- **D-02:** 미리보기 산출물도 **CLI 가 파일로 쓴다** (예: `--preview-out preview.json`, plans 전량).
  근거: 현재 dry-run 은 stdout 에 **10건만** 찍고 `… 외 N건` 으로 접으며(`bids.py` `run_bids`),
  `run_ads.py cmd_bids` 는 `run_bids` 의 리턴값을 **버린다**. stdout 파싱으로는 미리보기 표를 만들 수 없다.
  웹앱이 입찰가를 자체 계산하는 것은 **금지**(진실이 둘이 된다 — PROJECT.md 제약).

- **D-03:** 실행 결과도 같은 방식으로 **CLI 가 항목 단위 결과 파일을 쓴다** (성공/실패/스킵 + 사유).
  로그 파싱으로 FLOW-05 를 충족시키지 않는다.

### 보드

- **D-04:** 보드에 **6규칙 전부** 싣는다. 버튼은 ① 하나만 연다.
  근거: ①행에는 `imp`/`clk`/`ctr` 필드가 **아예 없다**(7일 통계에 행이 없는 것이 규칙① 정의).
  ①만 실으면 BOARD-01 이 요구하는 노출·클릭·구매완료 열이 전부 빈칸이 되어 BOARD-01·BOARD-02 를 검증할 수 없다.
  ③⑤ 행은 노출·클릭·CTR·구매완료를 갖고 있다. 규모(총 2,726행)도 Tabulator 클라이언트 사이드 한계 안이다.

- **D-05:** 보드 한 줄 = **상품**(`mallProductId` 기준 접기). 미리보기 표는 **소재(adId) 줄**.
  근거: 실제로 가격이 바뀌는 단위가 소재라 화면과 실행이 1:1 로 맞는다.
  실측상 팬아웃이 거의 없다(상품 2,637개 중 소재 2~3개인 것 88개, 최대 3).
  상품 줄을 고를 때 **"이 버튼이 N건에 적용됩니다"를 먼저 표시**한다 (Phase 3 의 JOIN-03 패턴을 여기서 미리 연습).

- **D-06:** 상품 줄을 골랐을 때 대상은 **그 상품의 규칙① 소재만**이다. 같은 상품의 ②③ 소재는 입찰가 인상 대상이 아니다.
  (규칙①이 곧 대상 정의 — `run_bids` 가 받는 rows 가 `①노출0` 이다)

- **D-07:** **필터 전체 선택을 허용**한다. 헤더 체크박스는 보이는 페이지만, "필터 전체 N건 선택"은 **별도 배너로 한 번 더 확인**.
  입찰가는 되돌릴 수 있으므로 **건수 타이핑은 받지 않는다** (FLOW-04 — 타이핑은 Phase 2 삭제 버튼 몫).

- **D-08:** 대신 **1회 실행 계정별 상한 1,500건**을 둔다. **설정파일로 조정 가능**하게 하고 화면·코드에 박지 않는다.
  근거: 실측 최대가 ownway1 1,195 · pogeunae 1,028 이라 평상시 작업엔 마찰 0,
  상한은 "계정이 이상하게 불어났다"는 사고 방지선으로만 산다. (SAFE-07 은 Phase 2 요구지만 여기서 선행 적용)

### 미리보기 ↔ 실행 결합

- **D-09:** 실행은 **CLI 의 재계산을 그대로 유지**한다. `run_bids(commit=True)` 가 plans 를 다시 계산하는 현재 동작을 바꾸지 않는다.
  근거: 쿨다운(`RAISE_COOLDOWN_DAYS=6`)·연속실패중단(`FAIL_STREAK=3`)·상한(`BID_CAP=200`) 가드가
  **실행 시점 기준으로 살아 있는 편이 안전하다.** 미리보기 값을 강제하면 검증된 방어를 우회하게 된다.

- **D-10:** 대신 웹앱이 `preview.json` 과 실행 결과를 대조해 **"미리보기와 달라진 N건"을 사유와 함께 보고**한다.
  (SAFE-06 은 "같은 대상 선정 함수" — `--only-ads` 파일을 미리보기와 실행이 **같이 지목**하는 것으로 충족한다)

- **D-11:** 미리보기·실행·되돌리기가 지목하는 대상 파일은 **하나**다. 미리보기 시점에 확정한 adId 목록을
  jobs DB 에 묶어두고 실행·되돌리기가 그걸 재사용한다. 화면 상태에서 목록을 다시 만들지 않는다 (FLOW-02).

### 되돌리기

- **D-12:** 화면의 "되돌리기"를 `--revert` 에 **그냥 연결하지 않는다.**
  `run_revert` 는 `before_bids_<alias>.json` **전체**를 되돌리는데, 이 백업은 회차 안에서 **누적 병합**된다
  (`bids.py` Important 1 — 같은 키는 먼저 것을 유지하며 merge). 그대로 연결하면
  **방금 누른 작업이 아니라 그 회차 인상분 전부가 풀린다.**

- **D-13:** 웹앱이 작업 단위로 **"이번에 인상 성공한 adId 목록"** 을 jobs DB 에 남기고,
  되돌리기는 그 목록을 `--only-ads` 로 넘겨 **그 작업분만** 되돌린다.
  **백업 파일(`before_bids_*.json`)은 손대지 않는다** — 최초 원본 보존 규칙(Important 1)을 그대로 지킨다.

- **D-14:** 화면에 **"이 작업분만 되돌리기"** 와 **"이 회차 전체 되돌리기"** 를 **따로** 둔다.

### 수집·판정 실행

- **D-15:** 화면에 **"새로 수집" 버튼을 연다.** `prep` → `run` 이 입찰가 버튼과 **같은 작업 엔진**
  (subprocess + append-only 로그 + 오프셋 tail + SSE)을 타고 돌고, 끝나면 보드가 새 run-dir 로 갈아탄다.
  근거: prep/run 은 **광고 API 에 아무것도 쓰지 않는 읽기 전용**이라 위험이 0인데 수 분이 걸린다 →
  "장시간 작업 · 진행 로그 · 브라우저 닫았다 이어보기"를 **안전한 대상으로 먼저 검증**할 수 있다.
  입찰가 버튼은 그렇게 검증된 엔진 위에 올라탄다.

- **D-16:** 보드 상단에 **회차 신선도를 항상 표시**한다 (예: `2026-08-30 회차 · 20일 전`).
  현재 마지막 run-dir 이 `2026-08-30` 이라 3주 묵어 있다 — 낡은 판정으로 입찰가를 올리는 게 이 단계의 실질 위험이다.

- **D-17:** `prep`/`run`/`bids` 어느 것이든 **작업 생성은 호출 가능한 함수**에 두고 HTTP 핸들러는 얇게 감싸기만 한다 (ENG-07).

### Claude's Discretion

- 미리보기·타깃·결과 파일의 **정확한 이름과 스키마**, jobs DB 테이블 컬럼 — planner/executor 재량
- Tabulator 컬럼 구성·정렬 기본값·필터 위젯 배치
- `--only-ads` 플래그의 정확한 이름 (`--only-ads` / `--targets` 등)과 파일 포맷(JSON 배열 vs JSONL)
- SSE 엔드포인트 경로, 로그 오프셋 전달 방식(`Last-Event-ID` 활용)
- 부팅 토큰 전달 방식(쿠키 vs 헤더 vs htmx `hx-headers`)
- 신선도 표시의 임계값(며칠부터 경고색인지)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 프로젝트 정본
- `.planning/PROJECT.md` — Core Value, 제약(래퍼 원칙·진실의 원천·확장성), Key Decisions, 조용한 실패 경로 7종, 실측 숫자
- `.planning/REQUIREMENTS.md` — Phase 1 요구사항 19개(ENG-01·02·03·07, SAFE-01·02·03, FLOW-01·02·04·05, BOARD-01~04, BID-01~04)와 Out of Scope
- `.planning/ROADMAP.md` — Phase 1 Success Criteria 5개 · Sequencing Notes(단계 순서 제약)
- `.planning/STATE.md` — Blockers/Concerns (Phase 1 에는 해당 없음, Phase 3·4·6 게이트 확인용)

### 기술 스택 리서치 (이미 확정된 결정 — 재논의 금지)
- `.planning/research/STACK.md` — subprocess vs import(§핵심결정 1) · 큐 미사용(§핵심결정 2) · SSE 로그파일 tail(§핵심결정 3) · `--workers 1` · 버전 핀
- `.planning/research/ARCHITECTURE.md` — 실행 엔진·잡 레지스트리 구조
- `.planning/research/PITFALLS.md` — 조용한 실패 경로
- `.planning/research/FEATURES.md` · `.planning/research/SUMMARY.md`

### 래핑 대상 CLI (읽기 필수 — 이 단계는 이 코드의 래퍼다)
- `.claude/skills/naver-ads-weekly/SKILL.md` — 서브커맨드 사용법·운영 규칙
- `.claude/skills/naver-ads-weekly/references/규칙-판정기준.md` — 6규칙 판정 기준 정본
- `.claude/skills/naver-ads-weekly/scripts/run_ads.py` — 진입점. `cmd_prep`/`cmd_run`/`cmd_bids` · run-dir 규약 · `data_root()` · `sys.path.insert` (subprocess 가 필수인 이유)
- `.claude/skills/naver-ads-weekly/scripts/bids.py` — `plan_raise`/`run_bids`/`run_revert`/`build_body`/`apply_raise`. **`--only-ads`·`--preview-out` 이 붙을 자리**
- `.claude/skills/naver-ads-weekly/scripts/ads_rules.py` — `classify` 가 만드는 판정행 스키마(보드 컬럼의 정본). `ad_info`·`_with_stat`·`effective_bid`
- `.claude/skills/naver-ads-weekly/scripts/ledger.py` — `bid_decision` 액션 5종 · `BID_CAP=200` · `BID_STEP=10` · `RAISE_COOLDOWN_DAYS=6` · `FAIL_STREAK=3`
- `.claude/skills/naver-ads-weekly/scripts/nvad.py` — `load_accounts()` · API 호출. **계정 수를 코드에 박지 않는 근거(BOARD-02)**
- `.claude/skills/naver-ads-weekly/scripts/collect.py` — `collect_account`. "새로 수집" 버튼이 거는 대상

### 회귀 방어 (로직 무변경을 증명하는 수단)
- `.claude/skills/naver-ads-weekly/scripts/test_bids.py` · `test_ads_rules.py` · `test_ledger.py` · `test_nvad.py`
  — **`--only-ads`/`--preview-out` 추가 후 이 테스트가 전부 그대로 통과해야 한다**

### 런타임 설정 (경로를 코드에 박지 말 것)
- `workspace.toml` — `[paths] data_root = /Users/choiyongsmacbook/python_work/data` (gitignore 대상, PC별)
- `~/.eroom/naver-ads.json` — 광고 계정 목록(`{"accounts": [...]}`). **여기에 항목을 더하는 것만으로 계정이 늘어난다**
- `~/python_work/data/naver-ads/runs/<회차>/` — run-dir. `accounts/<alias>/{ads,stats_7d,stats_30d,purchase}.json` · `result.json` · `prep_summary.json` · `report.md` · `before_bids_<alias>.json`
- `~/python_work/data/naver-ads/ledger/<alias>.json` — 인상 이력. **run-dir 바깥**(`run_dir.parent.parent/ledger`)이라 회차를 넘어 누적된다

</canonical_refs>

<code_context>
## Existing Code Insights

### 실측 (2026-09-19, run-dir `2026-08-30`)

| 항목 | 값 |
|---|---|
| 총 판정행 | **2,726** (4계정 × 6규칙) |
| **①노출0** | **2,242** (cy728 9 · cy7728 10 · ownway1 1,195 · pogeunae 1,028) |
| distinct (계정, mallProductId) | **2,637** — `mallProductId` 결측 0건 |
| 상품당 소재 수 | 최대 **3** · 2개 이상인 상품 **88개**뿐 → 보드 접기 팬아웃은 사실상 1:1 |
| `plan_raise` 오늘 기준 시뮬 | **전량 "인상"** (상한도달·연속실패중단 0 — 쿨다운 만료) |
| 마지막 run-dir | `2026-08-30` (그 전은 `2026-08-29`) — **약 3주 묵음** |
| CLI 페이싱 | `time.sleep(0.08)` → 초당 12건. 1,200건 ≈ 100초 |
| 재시도 | `apply_raise` 는 429/5xx 를 최대 4회 지수 백오프 |

> ⚠ **"주당 약 120행"은 규칙③(78)+⑤(38) 얘기다.** Phase 1 이 다루는 ①은 **2,242건**이다.
> 다만 Tabulator 클라이언트 사이드 한계(≈5,000행) 안이라 서버사이드 페이징은 여전히 불필요하다.

### Reusable Assets

- **`run_ads.py` 서브커맨드 5종** (`prep`/`run`/`apply`/`bids`/`prune`) — 웹앱이 부르는 argv 를 Pydantic 모델 한 곳에서 조립
- **`ads_rules.classify` 출력 스키마** = 보드 컬럼의 정본:
  `adId · adGroup · title · mallProductId · bid · useGroupBid · groupBid` (+ ②③④⑤ 는 `imp · clk · ctr · rank · cost`, ⑤ 는 `purCnt · purAmt`)
- **`nvad.load_accounts()`** — 계정 목록의 유일한 출처. 화면·코드에 계정 수를 박지 않는 근거
- **`run_dir` 규약** — 판정·백업·산출물이 이미 한 디렉터리에 모여 있다. 보드 데이터는 여기 JSON 을 **읽기만** 한다 (STACK.md "세 번째 길")

### Established Patterns (건드리면 안 되는 것)

- **`effective_bid`** — `useGroupBidAmt=True` 면 `adAttr.bidAmt` 는 잠자는 값이고 **그룹 기본가가 출발점**이다 (BID-03). 웹앱이 이 값을 다시 계산하면 올리려다 내린다
- **백업 병합 규칙** (`bids.py` Important 1) — 같은 키는 **먼저 것을 유지**한다. 최초 원본이 진짜 원본이다. 웹앱이 백업 파일을 다시 쓰면 안 된다
- **`ledger` 는 run-dir 바깥** — `run_dir.parent.parent / "ledger" / f"{alias}.json"`. 임시 run-dir 을 만들어도 ledger 는 공유된다
- **`update_streaks` 는 dry-run 에서 메모리만 갱신**하고 파일에 안 쓴다. commit 때만 저장 → 미리보기를 여러 번 눌러도 이력이 오염되지 않는다
- **`data_root()` 는 `workspace.toml` 을 먼저 본다** — 웹앱도 절대경로를 박지 말고 같은 규약을 따른다

### Integration Points

| 붙는 자리 | 내용 |
|---|---|
| `run_ads.py` `cmd_bids` | `--only-ads` 로 rows 필터 · `--preview-out` 으로 `run_bids` 리턴값 저장 (**현재 리턴값을 버리고 있다**) |
| `bids.py` `run_bids` | 이미 `{"plans", "counts", "committed", "failed", "aborted"}` 를 리턴한다 — **계산은 이미 다 되어 있고 쓰는 곳만 없다** |
| `bids.py` `run_revert` | `--only-ads` 로 되돌릴 adId 를 좁힌다 (백업 파일은 불변) |
| 보드 데이터 | `run-dir/result.json` 을 읽어 `mallProductId` 로 접는다. **CLI 를 실행하지 않는다** |
| 신선도 | run-dir 디렉터리명(ISO 날짜) + `prep_summary.json` mtime |

### 이 단계에서 드러난 위험

1. **`①노출0` 행에는 `imp`/`clk`/`ctr` 가 없다** — 보드 렌더가 `row.imp` 를 무조건 읽으면 ① 행 2,242개에서 깨진다
2. **`before_bids_<alias>.json` 누적 병합** — "되돌리기"를 `--revert` 에 직결하면 회차 전체가 풀린다 (D-12~D-14 로 해소)
3. **3주 묵은 run-dir** — 낡은 판정으로 입찰가를 올리는 것이 이 단계의 실질 위험 (D-15·D-16 으로 해소)
4. **`run_bids` 가 commit 때 plans 를 재계산** — 미리보기와 어긋날 수 있다 (D-09·D-10 으로 해소: 재계산 유지 + diff 보고)

</code_context>

<specifics>
## Specific Ideas

- 보드 상단 신선도 표시는 **회차 날짜 + 경과일**을 같이 (`2026-08-30 회차 · 20일 전`)
- 상품 줄 선택 시 **"이 버튼이 N건에 적용됩니다"** 를 실행 전에 노출 — Phase 3 JOIN-03 의 팬아웃 표시를 여기서 같은 모양으로 먼저 만든다
- 되돌리기는 버튼 **두 개**: `이 작업분만 되돌리기` / `이 회차 전체 되돌리기`
- 실행 버튼 옆에 선택 건수 + 예상 비용이 **항상** 보인다 (BOARD-04). 입찰가는 크레딧 0 이므로 "예상 인상액 합계"로 대신한다

</specifics>

<deferred>
## Deferred Ideas

- **작업 잠금(ENG-04) · 고아 작업 정리(ENG-05) · `caffeinate -i`(ENG-06)** — Phase 2.
  단 Phase 1 의 잡 레지스트리 스키마가 이걸 나중에 끼워 넣을 수 있는 모양이어야 한다
- **실행 직전 재조회 · 미리보기 스테일 거부(SAFE-05·FLOW-03)** — Phase 2.
  Phase 1 은 D-10 의 diff 보고로 "달라졌다는 사실"만 보여주고 거부는 하지 않는다
- **감사 로그 JSONL(FLOW-07) · 실패분 재시도(FLOW-06) · 오판정 표시(BOARD-06) · 정지 소재 과거실적 방어(BOARD-05)** — Phase 2
- **불사자 계정 확인 게이트(ENG-08)** — Phase 3. Phase 1 은 광고 API 만 건드리고 불사자를 안 탄다
- **APScheduler 스케줄 자동화** — v2. 단 D-17(작업 생성이 호출 가능한 함수)이 그 전제를 미리 깔아둔다
- **서버사이드 페이징·가상 스크롤** — Out of Scope (REQUIREMENTS.md). 2,726행은 Tabulator 클라이언트 사이드로 충분

</deferred>

---

*Phase: 1-첫 왕복 — 보드 + 입찰가 인상 버튼*
*Context gathered: 2026-09-19*
