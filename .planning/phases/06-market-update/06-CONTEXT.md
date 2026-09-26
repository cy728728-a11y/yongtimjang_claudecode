# Phase 6: 마켓 수정업로드 - Context

**Gathered:** 2026-09-26 (`/gsd-discuss-phase 6 --auto` — 용팀장 부재, 전 항목 추천안 자동 선택, single pass)
**Status:** Ready for planning

> ⚠️ **이 문서의 결정은 전부 `[auto]` 다.** 사람이 답한 게 아니라 추천안을 고른 것이다.
> **`[auto — 용팀장 확인 필요]`** 는 2건(D-03 · D-09)뿐이다. 플랜이 짜여도 **첫 실제 마켓 쓰기 체크포인트 전에**
> 한 줄씩 확인받는다. 단 **D-03 은 05-06(첫 크레딧 실탄) 전에** 답이 필요하다 — 순서를 바꾸는 결정이라서.

<domain>
## Phase Boundary

Phase 5 에서 AI 상세 생성이 **완료**된 상품(불사자 상세에는 자동 반영됨)을 보드에서 골라 →
**미리보기(쓰기 0)** → **원본 상세 백업 확인** → **첫 1건만 스마트스토어 반영** → **용팀장 스토어 육안 확인 게이트** →
**나머지 반영** → **항목 단위 결과**까지를 터미널 없이 완주한다. 쓰기는 불사자 MCP `bulsaja_market_update`(market=SMARTSTORE)
하나이며, 새 CLI 를 subprocess 로 감싼다.

**린 MVP 조각:** 대상 고르기 → 미리보기 → (백업) → 1건 반영 → 게이트 → 나머지 반영 → 결과 표. SC 1~3 에 필요 없는 것은 Deferred.

**이 페이즈가 아닌 것:** 쿠팡·11번가 등 다른 마켓(Phase 7) · 상하단 안내이미지 교체 자체(옆 프로젝트 — 커머스API, 윈도우 데스크탑) ·
AI 상세 생성(Phase 5) · 스토어 쪽 HTML 자동 대조(맥북은 커머스API IP 허용목록 밖) · 무인 스케줄.

</domain>

<decisions>
## Implementation Decisions

### 🔒 잠긴 제약 (auto 아님 — 프로젝트·메모리·Phase 5 에서 승계)

- **L-01: 모든 실제 `market_update(confirm:true)` 는 플랜의 blocking human checkpoint 다.** 첫 1건(게이트) · 나머지 일괄 · 복원 실행 전부.
  `autonomous: false` 이고 `--auto` 체인·`workflow.auto_advance` 도 이 체크포인트를 자동 승인하지 않는다. 체크포인트 앞에 **대상 건수 · 판매자상품코드 · 계정 · 백업 경로**를 보여 준다.
- **L-02: dry-run 선행.** 실제 쓰기 전에 반드시 같은 대상으로 미리보기 잡(`confirm:false` — 쓰기 0)이 `done` 이어야 하고, 실행 라우트는 **미리보기 잡 id 하나만** 받는다(대상을 새로 받지 않는다 — Phase 1 01-08 D-11 · Phase 5 05-04 선례).
- **L-03: 백업 없으면 쓰기 없음.** 대상 상품의 원본 상세 HTML 백업 파일이 없거나 읽히지 않으면 그 건은 쓰지 않는다(`backup_failed` 로 스킵/중단, 폴백 없음) — MARKET-03 · PITFALLS Pitfall 10.
- **L-04: 기존 CLI 재작성 금지 · 웹앱은 MCP 를 직접 부르지 않는다.** 마켓 반영은 새 CLI 스크립트를 subprocess 로, 기존 `detail_batch.py` 는 **주입구 플래그 추가만**(Phase 5 L-04 · Phase 3 D-19 · ENG-01).
- **L-05: 진실의 원천은 불사자 서버.** "반영했음" 로컬 대장을 새로 만들지 않는다. 잡 산출물(summary)은 그 회차 기록일 뿐이고 반영 상태는 불사자 `upload_tasks` 가 정본(PROJECT.md).
- **L-06: 계정 가드(ENG-08) 그대로** — 기대 계정(부킹/용쌤) 아니면 미리보기·반영 모두 exit 4 로 거부.
- **L-07: 마켓은 SMARTSTORE 고정.** 화면에 마켓 선택지를 두지 않는다. 같은 상품이 쿠팡에도 올라가 있어도 이 버튼은 스마트스토어만 친다.

### 대상 — 무엇을 반영하나 (MARKET-01)

- **D-01 [auto]: 대상은 Phase 5 상세 잡 결과에서 `완료` 인 항목뿐이다.** 보드의 "최근 상세 작업" 결과 표(`_detail_result_table.html`)에 `스마트스토어 반영` 미리보기 버튼을 단다.
  · [auto] Q: "대상 출처 — ⓐ 상세 잡 완료분 ⓑ 보드에서 아무 상품이나" → Selected: **ⓐ 상세 잡 완료분** (recommended — Phase 1 부모 잡 체인 패턴 그대로, 엉뚱한 상품 반영 차단)
  · 미리보기 잡 = `parent_job_id` 가 detail_submit/detail_poll 잡. 서버는 그 잡의 `detail_status.json`(Phase 5 결과 정본) 에서 `완료` 만 뽑아 targets 파일로 쓴다
  · 사본 1개 원칙(Phase 5 D-06) 그대로 — 표기는 **판매자상품코드**
- **D-02 [auto]: CLI 는 반영 직전 workdata 를 실시간 재조회해 "AI 상세가 실제로 붙어 있는지"(Phase 5 D-12 와 같은 `기작업` 규칙)를 확인한다.** 아니면 그 건은 `AI상세없음` 으로 스킵. 스마트스토어 업로드 흔적이 없는 상품(미업로드)은 `미업로드` 로 스킵.

### 원본 백업 (MARKET-03 · SC-3)

- **D-03 `[auto — 용팀장 확인 필요]`: "원본 상세 HTML" = AI 생성 직전의 불사자 상세(`uploadDetailContents.renderContent` + `imageTranslated`). 이 스냅샷은 Phase 5 접수 순간에 떠야 하므로, `detail_batch.py` 에 `--backup-out <dir>` 주입구를 추가하고 05-06 첫 실탄 전에 들어가게 한다.**
  · [auto] Q: "백업 시점 — ⓐ AI 접수 직전(원본) ⓑ 마켓 반영 직전(이미 AI 버전)" → Selected: **ⓐ + ⓑ 둘 다, 복원 기준은 ⓐ** (recommended)
  · 근거(실측): AI 생성 결과는 **완료 시 불사자 상세를 자동으로 덮는다**(bulsaja-detail-page SKILL · `detail_apply` 도구 설명). 지금 코드에 renderContent 원문 백업은 **어디에도 없다**(detail_batch·banner_scan 모두 URL 만 뽑고 버림). 마켓 반영 시점에 뜨면 원본은 이미 사라진 뒤다. 스마트스토어 쪽 원문은 맥북에서 커머스API 로 못 읽는다(IP 허용목록 — 00-inbox 인계 확정사실 6)
  · 비용 0: `_판정` 이 이미 접수 전 `get_workdata` 를 부른다 — 같은 응답에서 원문을 파일로 떨군다. 추가 호출 없음. 백업 쓰기 실패 = 그 건 generate 하지 않음(L-03 을 AI 접수에도 적용)
  · 파일: `<회차>/web/detail_<견적잡id>/before_detail/<productId>.json` = `{productId, 판매자상품코드, 조회시각, 계정, renderContent, imageTranslated}`
  · ⓑ 마켓 반영 직전 스냅샷도 같은 모양으로 `market_<잡id>/before_market/` 에 남긴다(무엇을 밀었는지의 증거, 비용 0)
  · 플래그 없는 기존 동작은 불변(골든 테스트 유지). 웹앱 `DetailArgv` submit 이 이 플래그를 항상 붙인다
  · **확인이 필요한 이유:** Phase 5 실행 순서를 바꾼다 — 06-01(백업 플래그, 크레딧 0)이 05-06 실탄보다 먼저 머지돼야 첫 5건의 원본이 남는다. 이미 백업 없이 생성된 상품이 생기면 그 건은 ⓑ 만 있고 **원본 복원 불가**로 표시한다
- **D-04 [auto]: 화면은 결과 표와 미리보기 표에 상품별 백업 파일 경로(ⓐ·ⓑ)와 존재 여부를 보인다.** 경로는 텍스트(복사 가능)로. 파일 뷰어는 만들지 않는다 — SC-3 은 "위치를 화면에서 확인"까지다.
- **D-05 [auto]: 복원은 CLI 서브커맨드로만 만든다(웹 버튼 없음).** `restore --backup <before_detail/…json>` = `detail_apply(html=ⓐ원문, confirm:false→true)` 후 `market_update`. 미리보기(confirm:false)까지 오프라인+실제 MCP 크레딧 0 로 검증하고, **실제 복원 실행은 게이트 실패 등 필요할 때만 L-01 체크포인트로**.
  · [auto] Q: "복원을 이 페이즈에 넣나" → Selected: **CLI 만 넣는다** (recommended — Pitfall 10 "백업만 있고 복원 경로가 없으면 위안", 웹 버튼은 Deferred)

### 미리보기 → 반영 (쓰기 경로)

- **D-06 [auto]: 새 CLI `market_update.py`(bulsaja-detail-page/scripts, 기존 MCP 클라이언트·`ss_index_calls` 호출 규약 재사용)를 만든다.** 인자: `--targets` · `--expect-nick` · `--preview`(confirm:false 만, 쓰기 0) · `--commit` · `--max-items N` · `--backup-dir` · `--summary-out` · `--run-dir`. 마지막 줄 센티널 `###MARKET### 성공 a / 실패 f / 스킵 s / 대기 p / 전체 t`, `flush=True`.
  · 종료코드는 Phase 5 계약을 따른다: 0 전부 종결 · 2 입력 오류 · 3 서버 작업 대기 미완(실패 아님) · 4 계정 불일치 · 5 `--max-items` 초과 시도
  · `--commit` 은 `--max-items` 없으면 exit 2(Phase 5 `--max-credits` 와 같은 규율 — 빈 값이 "전량"이 되지 않는다)
- **D-07 [auto]: 웹앱 잡 kind 2종 — `market_preview`(BULSAJA_KINDS · 쓰기 아님) · `market_commit`(WRITE_KINDS · `caffeinate -i`).** 버튼 흐름은 Phase 1/5 와 같다: 결과 표 → `반영 미리보기 — 쓰기 0` → 미리보기 표 → `반영 실행` (미리보기 잡 id 만 전송).
- **D-08 [auto]: 반영 결과 확인은 `bulsaja_upload_tasks(list)` 폴링으로 한다** — 접수 응답만 믿지 않는다(불사자 안전규칙 ⑤). 시간 상한에 닿으면 `대기 미완` exit 3 · 실패 아님 · `이어서 확인` 만(재반영 버튼 없음 — Phase 5 D-17 과 같은 규율). 서버 `FAILED/DLQ` 만 `실패`.
  · 같은 상품·마켓 작업이 진행 중이면 서버가 자동 차단한다(도구 설명) → 그 응답은 `실패` 가 아니라 `이미진행중` 스킵

### 첫 1건 육안 게이트 (MARKET-02 · SC-2 · STATE Blocker)

- **D-09 `[auto — 용팀장 확인 필요]`: 게이트는 1회성이다 — 상하단 안내이미지 모순을 깨는 용도. 판명 전까지 `market_commit` 은 코드로 `--max-items 1` 로만 나가고, 판정이 기록된 뒤에는 이 강제 1건 정지가 풀린다.**
  · [auto] Q: "매 실행마다 첫 1건 정지 ⓐ vs 모순 판명 1회 ⓑ" → Selected: **ⓑ 1회** (recommended — 처리량 우선 · 사람 큐 최소화. 모순은 한 번 보면 끝나는 사실 문제)
  · 게이트 상태는 웹앱 SQLite 한 줄(`market_gate`: 판정 · 시각 · 확인한 상품코드 · 메모). 이건 "작업 완료 대장"이 아니라 사람 판정 기록이라 L-05 와 충돌하지 않는다
  · 판정 전: 미리보기 표의 실행 버튼은 `첫 1건만 반영 (육안 확인 게이트)` 한 가지뿐. 대상이 N건이어도 1건만 나간다(나머지는 표에 `게이트 대기`)
  · **확인이 필요한 이유:** SC-2 문구("첫 1건이 반영된 뒤 … 나머지가 나가지 않는다")를 매 실행 규칙으로 읽을 수도 있다. 1회로 풀면 이후 대량 반영이 사람 개입 없이 나간다(단 L-01 실행 체크포인트는 그대로)
- **D-10 [auto]: 게이트 화면 = 1건 반영 성공 후 결과 표 위에 고정 패널.** 내용: 판매자상품코드 · 스마트스토어 상품 링크(조인 산출물의 채널상품번호로 조립, 없으면 코드만) · 확인 체크 3개 ① 본문이 AI 상세로 바뀌었다 ② 상단·하단 안내이미지가 **현재 불사자 설정** 것이다 ③ 가격·상품명·옵션 등 다른 곳이 의도치 않게 바뀌지 않았다 → 버튼 `정상 — 나머지 진행 허용` / `이상 있음 — 멈춤`.
  · ③ 을 넣은 이유: `market_update` 는 "가격/상품명/상세 등 변경사항"을 통째로 다시 민다(도구 설명). 다른 스킬(option-cleanup·product-name)이 불사자에만 저장해 둔 변경이 이 버튼으로 같이 나갈 수 있다 — 첫 1건에서 눈으로 본다
  · 에이전트는 네이버·스마트스토어에 접속하지 않는다(CLAUDE.md 네이버 규칙) — 육안 확인은 용팀장 브라우저 몫
- **D-11 [auto]: `이상 있음` 이면 게이트는 닫힌 채(나머지 0건) 그 상품의 복원 절차(D-05)와 증상 메모를 보여 주고 끝.** 옛 안내이미지로 판명되면 PROJECT.md `[!contradiction]` 을 전자로 확정 기록하고, **"상하단 교체 프로젝트는 관제탑 반영 뒤에 돌리거나 재실행"** 순서 제약을 STATE Blockers 에 올린다. 진행 여부는 그때 용팀장이 정한다(자동 진행 없음). `정상` 이면 contradiction 을 후자로 확정 기록.

### 규모 · 기타

- **D-12 [auto]: 게이트 통과 후 1회 반영 상한은 설정값 `market_update_max_items`(기본 20).** 상한 초과 선택은 미리보기에서 앞 N건 + 나머지 표시. 첫 실사용 대상은 어차피 05-06 의 🔴 5건 이하.
- **D-13 [auto]: 결과 표 = 항목 단위**(판매자상품코드 · 성공/실패/스킵/대기 · 사유 · 백업 경로 · 서버 작업 시각). Phase 5 결과 표 레이아웃 재사용.

### Claude's Discretion

- `market_update.py` 내부 구조 · 폴링 간격/상한 기본값 · `upload_tasks` 응답에서 상품별 매칭 방법(연구에서 실측 스키마 확인)
- 미리보기(confirm:false) 응답에 무엇이 실리는지에 따라 미리보기 표 컬럼 구성
- `market_gate` 테이블 스키마 · 게이트 패널 문구
- 스마트스토어 상품 링크 조립 가능 여부(조인 산출물 필드 실측)
- run-dir 파일 배치(권장: `<회차>/web/market_<미리보기잡id>/`)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 범위·요구사항
- `.planning/ROADMAP.md` §Phase 6 — Goal · SC 1~3
- `.planning/REQUIREMENTS.md` §버튼 4 MARKET-01~03
- `.planning/PROJECT.md` — 안전 제약 · **`[!contradiction]` 상하단 안내이미지(§Key facts)** · 진실의 원천
- `.planning/STATE.md` §Blockers — `[Phase 6 게이트]`
- `.planning/research/PITFALLS.md` §Pitfall 10(되돌릴 수 없는 마켓 쓰기 — 백업·restore 같은 페이즈·파일럿 상한·재조회) · §Pitfall 11(계정 라우팅)
- `.planning/research/SUMMARY.md` — 마켓쓰기/크레딧쓰기 분리 근거
- `00-inbox/2026-09-19-스마트스토어-상하단이미지-교체-인계.md` — 모순의 한쪽 출처(확정사실 1) · 맥북 커머스API 불가(확정사실 6) · 옆 프로젝트 상태

### Phase 5 에서 넘어온 것 (직접 의존)
- `.planning/phases/05-core-value/05-CONTEXT.md` — L-01~L-06 · D-06(사본 1개) · D-12(기작업 규칙) · D-17(타임아웃≠실패)
- `.planning/phases/05-core-value/05-01-SUMMARY.md` — detail_batch 인자·종료코드·센티널 계약(06 CLI 가 따를 모양)
- `.planning/phases/05-core-value/05-03-SUMMARY.md` — detail kind 3종 · `_상세폴더` · run-dir 배치
- `.planning/phases/05-core-value/05-04-SUMMARY.md` — submit/poll 라우트 · `_상세결과ctx` · `_detail_result_table.html` · exit 3=done 처리
- `.planning/phases/05-core-value/05-05-PLAN.md` · `05-06-PLAN.md` — **아직 미실행.** D-03 백업 플래그가 05-06 앞에 들어가야 한다

### 감쌀/참고할 CLI·도구
- `.claude/skills/bulsaja-detail-page/scripts/detail_batch.py` — `_판정`(접수 전 get_workdata — 백업 주입 지점) · `_입력모드` · `main`
- `.claude/skills/bulsaja-detail-page/scripts/ss_index_calls.py` — 불사자 응답 꺼내기 규약(오류를 0건으로 접지 않기)
- `.claude/skills/bulsaja-detail-page/SKILL.md` — "완료 시 불사자가 자동 반영" · 계정 라우팅
- `.claude/skills/bulsaja-detail-remix/scripts/bulsaja_client.py` — `detail_apply` 2단계(confirm:false→token→confirm:true) 실측 호출 모양 → 복원(D-05)에 재사용
- MCP 도구 `bulsaja_market_update`(productIds · market · marketGroupId · confirm · confirmationToken) · `bulsaja_upload_tasks`(list/retry) · `bulsaja_detail_apply` — 스키마는 이 세션 ToolSearch 로 확인(2026-09-26)

### 관련 대기 todo (접지 않음)
- `.planning/todos/pending/job-reap-depends-on-polling.md` — 브라우저 닫힌 채 끝난 WRITE 잡이 전역 가드를 붙잡을 수 있음 → 게이트 1건 반영 뒤 확인

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `webapp/jobs.py` — `create_job` · `WRITE_KINDS` · `BULSAJA_KINDS` · `_수면방지_프리픽스` · `_finish`(exit 3 → done 분기, `POLL_INCOMPLETE_OK_KINDS` 에 market_commit 추가) · `children_of`
- `webapp/argv.py` — `DetailArgv` 모양 그대로 `MarketArgv`(preview/commit) 추가
- `webapp/routes/jobs.py` — detail submit/poll 라우트(부모 잡 id 하나 받기) 패턴
- `webapp/templates/_detail_result_table.html` · `_detail_estimate_table.html` · `_job_panel.html` · `_job_status.html` — 결과·미리보기·SSE 재사용
- `webapp/tests/test_detail_cli.py` — 가짜 MCP 하네스(sys.modules 스텁 + importlib) → `market_update.py` 오프라인 테스트에 재사용
- `webapp/tests/fixtures/detail_golden_noflag.json` — `--backup-out` 추가 후에도 플래그 없는 동작 불변 증명

### Established Patterns
- 미리보기 잡 → 실행 잡은 부모 targets 파일만 참조 · 실행 라우트는 대상을 받지 않는다
- 빈 목록·빈 설정 = "전량" 금지(예외) · 상한 인자 필수
- CLI 주입구 플래그만 추가, 무플래그 동작 바이트 불변(골든)
- 장시간 CLI `flush=True` · 마지막 줄 센티널
- `webapp/**` 에 `requests`·`eroomlib` import 0건 (트리 가드)
- 실탄 도는 동안 웹앱 코드 수정 금지(`--reload` 가 `_PROCS` 를 비움 — 05-06 Pitfall 4)

### Integration Points
- 보드 `#detail-result`(최근 상세 작업) → `반영 미리보기` → `market_preview` → 미리보기 표(+백업 경로) → `market_commit`(게이트 전 1건 강제) → 게이트 패널 → `market_gate` 기록 → 나머지 `market_commit`
- `DetailArgv` submit → `--backup-out` 항상 부착 (D-03)

### 비용 0 으로 먼저 끝낼 수 있는 것 (첫 실제 마켓 쓰기 전)
1. `detail_batch.py --backup-out` + 골든/오프라인 테스트 (→ 05-06 전에 머지)
2. `market_update.py` preview/commit/restore 전 경로 — 가짜 MCP 오프라인 테스트
3. 웹앱 kind·라우트·미리보기/결과/게이트 화면 · `market_gate` — TestClient + uat-verifier(격리 포트·DB)
4. **실제 MCP `market_update(confirm:false)` 스모크** — 쓰기 0 확인(연구에서 confirm:false 가 부작용 없는지 먼저 확인, Phase 5 05-04 Task 3 스모크와 같은 방식)
5. 실제 MCP `detail_apply(confirm:false)` 복원 미리보기 스모크
→ 그 뒤에야 **실제 쓰기 1건(게이트)** — 05-06 완료분이 생긴 다음

</code_context>

<specifics>
## Specific Ideas

- 첫 실제 반영 = 05-06 의 🔴 완료분 중 **1건**. 용팀장이 자기 브라우저로 스토어를 열어 3가지(본문·상하단·기타 필드)를 본다
- 옆 프로젝트(상하단 교체)는 2026-09-19 기준 브레인스토밍 단계 — 아직 교체가 안 된 스토어라면 "옛 이미지로 올라감"이 곧 손해는 아니다. 판정 기록 때 그 스토어의 교체 여부를 같이 적는다
- 용팀장 성향: 진도 우선 · 사람 큐 최소화 · 추천이면 진행 — 단 **마켓 쓰기 실행은 예외 없이 사람 체크포인트**

</specifics>

<deferred>
## Deferred Ideas

- 웹 화면 `복원` 버튼 (D-05 — MVP 는 CLI)
- 스토어 쪽 HTML 자동 대조(커머스API — 맥북 IP 불가, 데스크탑 전용)
- 매 실행 첫 1건 정지 (D-09 대안 ⓐ — 용팀장이 원하면 설정 플래그로)
- 쿠팡·다른 마켓 반영 (Phase 7 이후)
- 반영 실패분 재시도 버튼 (`upload_tasks retry`) — MVP 는 결과 표만
- 백업 없이 이미 생성된 상품의 원본 복구 수단 탐색(불사자 이력 API 등)

### Reviewed Todos (not folded)
- `todo.match-phase 6` 결과 0건. `job-reap-depends-on-polling.md` 는 위험 인지용으로 canonical refs 에만 올림

</deferred>

---

*Phase: 06-market-update*
*Context gathered: 2026-09-26 (--auto, single pass)*
