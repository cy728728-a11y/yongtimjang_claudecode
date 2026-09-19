# Phase 1: 첫 왕복 — 보드 + 입찰가 인상 버튼 - Research

**Researched:** 2026-09-19
**Domain:** 로컬 단일사용자 FastAPI 웹앱이 기존 Python CLI 를 subprocess 로 래핑 — 작업 엔진 · SSE 로그 tail · localhost 보안 3종
**Confidence:** HIGH (거의 전부 이 맥북에서 직접 실행·실측했다. 아래 각 절에 측정값과 명령을 남겼다)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**기존 CLI 래핑 경계**

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

**보드**

- **D-04:** 보드에 **6규칙 전부** 싣는다. 버튼은 ① 하나만 연다.
- **D-05:** 보드 한 줄 = **상품**(`mallProductId` 기준 접기). 미리보기 표는 **소재(adId) 줄**.
  상품 줄을 고를 때 **"이 버튼이 N건에 적용됩니다"를 먼저 표시**한다.
- **D-06:** 상품 줄을 골랐을 때 대상은 **그 상품의 규칙① 소재만**이다. 같은 상품의 ②③ 소재는 입찰가 인상 대상이 아니다.
- **D-07:** **필터 전체 선택을 허용**한다. 헤더 체크박스는 보이는 페이지만, "필터 전체 N건 선택"은 **별도 배너로 한 번 더 확인**.
  입찰가는 되돌릴 수 있으므로 **건수 타이핑은 받지 않는다** (FLOW-04).
- **D-08:** 대신 **1회 실행 계정별 상한 1,500건**을 둔다. **설정파일로 조정 가능**하게 하고 화면·코드에 박지 않는다.

**미리보기 ↔ 실행 결합**

- **D-09:** 실행은 **CLI 의 재계산을 그대로 유지**한다. `run_bids(commit=True)` 가 plans 를 다시 계산하는 현재 동작을 바꾸지 않는다.
- **D-10:** 대신 웹앱이 `preview.json` 과 실행 결과를 대조해 **"미리보기와 달라진 N건"을 사유와 함께 보고**한다.
- **D-11:** 미리보기·실행·되돌리기가 지목하는 대상 파일은 **하나**다. 미리보기 시점에 확정한 adId 목록을
  jobs DB 에 묶어두고 실행·되돌리기가 그걸 재사용한다. 화면 상태에서 목록을 다시 만들지 않는다 (FLOW-02).

**되돌리기**

- **D-12:** 화면의 "되돌리기"를 `--revert` 에 **그냥 연결하지 않는다.**
- **D-13:** 웹앱이 작업 단위로 **"이번에 인상 성공한 adId 목록"** 을 jobs DB 에 남기고,
  되돌리기는 그 목록을 `--only-ads` 로 넘겨 **그 작업분만** 되돌린다.
  **백업 파일(`before_bids_*.json`)은 손대지 않는다.**
- **D-14:** 화면에 **"이 작업분만 되돌리기"** 와 **"이 회차 전체 되돌리기"** 를 **따로** 둔다.

**수집·판정 실행**

- **D-15:** 화면에 **"새로 수집" 버튼을 연다.** `prep` → `run` 이 입찰가 버튼과 **같은 작업 엔진**을 타고 돌고, 끝나면 보드가 새 run-dir 로 갈아탄다.
- **D-16:** 보드 상단에 **회차 신선도를 항상 표시**한다 (예: `2026-08-30 회차 · 20일 전`).
- **D-17:** `prep`/`run`/`bids` 어느 것이든 **작업 생성은 호출 가능한 함수**에 두고 HTTP 핸들러는 얇게 감싸기만 한다 (ENG-07).

### Claude's Discretion

- 미리보기·타깃·결과 파일의 **정확한 이름과 스키마**, jobs DB 테이블 컬럼 — planner/executor 재량
- Tabulator 컬럼 구성·정렬 기본값·필터 위젯 배치
- `--only-ads` 플래그의 정확한 이름 (`--only-ads` / `--targets` 등)과 파일 포맷(JSON 배열 vs JSONL)
- SSE 엔드포인트 경로, 로그 오프셋 전달 방식(`Last-Event-ID` 활용)
- 부팅 토큰 전달 방식(쿠키 vs 헤더 vs htmx `hx-headers`)
- 신선도 표시의 임계값(며칠부터 경고색인지)

### Deferred Ideas (OUT OF SCOPE)

- **작업 잠금(ENG-04) · 고아 작업 정리(ENG-05) · `caffeinate -i`(ENG-06)** — Phase 2.
  단 Phase 1 의 잡 레지스트리 스키마가 이걸 나중에 끼워 넣을 수 있는 모양이어야 한다
- **실행 직전 재조회 · 미리보기 스테일 거부(SAFE-05·FLOW-03)** — Phase 2.
- **감사 로그 JSONL(FLOW-07) · 실패분 재시도(FLOW-06) · 오판정 표시(BOARD-06) · 정지 소재 과거실적 방어(BOARD-05)** — Phase 2
- **불사자 계정 확인 게이트(ENG-08)** — Phase 3.
- **APScheduler 스케줄 자동화** — v2.
- **서버사이드 페이징·가상 스크롤** — Out of Scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | 요구 | 이 리서치의 어느 발견이 이걸 가능하게 하나 |
|----|------|---|
| ENG-01 | CLI 를 서브프로세스로 실행 | §1.1 `run_ads.py` 가 `sys.path.insert` 로 **네임스페이스 없는 최상위 모듈**(`bids`·`nvad`·`collect`·`ledger`)을 import 한다 — 실측으로 이름 충돌을 재현했다(§5.6) |
| ENG-02 | 브라우저 닫아도 계속 돌고 재접속하면 처음부터 이어본다 | §5.2 `start_new_session=True` 자식이 `uvicorn --reload` 재시작에서 생존함을 실측 · §5.4 로그 전량 재생 설계 |
| ENG-03 | append-only 로그파일 + 오프셋 재생 | §5.1 **`PYTHONUNBUFFERED=1` 없이는 로그가 종료 시점에 한꺼번에 떨어진다**(실측) · §5.3 로그 4.5KB 실측 |
| ENG-07 | 작업 생성이 호출 가능한 함수 | §5.5 `create_job()` 시그니처 제안 |
| SAFE-01 | 127.0.0.1 바인드 + Host + Origin | §4.1~4.3 `TrustedHostMiddleware(allowed_hosts=["127.0.0.1","localhost"])` · Origin 가드 — curl 로 6케이스 실측 통과 |
| SAFE-02 | 부팅 토큰이 있어야 쓰기 통과 | §4.4 `secrets.token_urlsafe` + `compare_digest` — 실측 403/200 |
| SAFE-03 | 자격증명이 화면·로그·에러에 안 나온다 | §4.5 누출 지점 4곳 전수조사 결과 + 화이트리스트 투영 규칙 |
| FLOW-01 | 판정→미리보기→실행 3단 | §1.3 `--only-ads`/`--preview-out` 이 3단을 파일로 잇는다 |
| FLOW-02 | 미리보기가 run-dir 파일로 저장되고 실행이 그 파일을 지목 | §1.3 `--preview-out` · §1.4 대상 파일 단일화 |
| FLOW-04 | 확인 강도 차등 | D-07 — 입찰가는 모달 없이 되돌리기 버튼만 |
| FLOW-05 | 항목 단위 성공/실패/스킵 + 사유 | §1.5 **현재 `run_bids` 는 항목 단위 성공/실패를 리턴하지 않는다**(ok/fail 카운트만) — plan dict 에 `result`/`error` 추가 필요 |
| BOARD-01 | 한 줄 = 상품 1개 | §2.2 `mallProductId` 결측 0건 · §2.3 접기 후 2,637행 |
| BOARD-02 | 계정·규칙·상태 필터 (계정 수 안 박기) | §3 `~/.eroom/naver-ads.json` + `result.json["accounts"]` 키 |
| BOARD-03 | 보이는 것 vs 필터 전체 구분 | Tabulator `getSelectedData()` vs `getData("active")` (§Code Examples) |
| BOARD-04 | 선택 건수 + 예상 비용 상시 노출 | §2.4 `plans[].from/to` 합계 = 예상 인상액 |
| BID-01 | 규칙① 판정 표시 | §2.1 `①노출0` 2,242행 실측 |
| BID-02 | 현재가 → 인상 후 가격 미리보기 | §1.3 `--preview-out` 의 `plans[].from`/`to` |
| BID-03 | 그룹입찰 출발점 = 그룹 기본입찰가 | §2.5 `useGroupBid=true` 가 **①행의 92%**(2,063/2,242) — 이걸 틀리면 거의 전량이 틀린다 |
| BID-04 | 실행 후 화면에서 되돌리기 | §1.6 `run_revert` 에 `only_ads` 1줄 추가 |
</phase_requirements>

---

## Summary

이 단계는 **새 기술을 배우는 단계가 아니라 기존 CLI 의 표면을 정확히 읽고 최소 주입구를 뚫는 단계**다. 스택은 CLAUDE.md 에서 이미 잠겼고, 이 문서는 그 스택을 이 맥북에 실제로 깔아서(`.venv-probe`) 시그니처·동작을 전부 확인한 뒤, 래핑 대상 CLI 2,432줄을 읽고 실측한 결과다.

**핵심 발견 5개 (전부 실측):**

1. **`PYTHONUNBUFFERED=1` 이 없으면 ENG-03 이 조용히 깨진다.** `print()` 출력이 파일로 갈 때 블록 버퍼링돼, 0.5초 시점 로그파일 크기가 **0바이트**였다가 프로세스 종료 시 한꺼번에 떨어진다. 10분짜리 `prep` 의 진행 로그가 10분 동안 빈 화면이 된다는 뜻이다. CLI 소스에 `flush=True` 는 `prune.py` 한 줄뿐이다.
2. **`start_new_session=True` 는 실제로 효과가 있다.** `uvicorn --reload` 로 서버를 재시작시켰는데 자식(pgid 분리)이 계속 틱을 찍었다. 같은 세션 자식은 그룹 시그널에 죽었다.
3. **htmx-ext-sse 의 재연결은 새 `EventSource` 를 만든다** → **`Last-Event-ID` 가 유실된다.** 그러므로 "오프셋부터 재개"를 `Last-Event-ID` 에 의존시키면 안 된다. 다행히 잡 로그가 **4.5KB / 53줄**(bids 실측)이라 **매 접속마다 전량 재생**이 압도적으로 단순하고 정확하다. `Last-Event-ID` 는 있으면 쓰는 최적화로만 둔다.
4. **`run_bids` 는 항목 단위 결과를 리턴하지 않는다.** `{"plans","counts","committed","failed"}` 뿐이고 개별 PUT 실패 사유는 `log()` 로만 나간다. FLOW-05 를 충족하려면 plan dict 에 `result`/`error` 를 **추가**해야 한다(기존 필드는 안 건드린다 — 테스트 100개가 특정 키만 검사하므로 안전).
5. **`--only-ads` 를 `run_bids` **바깥**에서 필터하면 `update_streaks` 가 오염된다.** `update_streaks` 는 `zero_ids = {r["adId"] for r in rows}` 로 "이번에도 노출 0" 을 판정한다. `cmd_bids` 에서 미리 걸러 5건만 넘기면 나머지 2,237건의 연속실패 카운팅이 이번 회차에 통째로 빠지고, `led["_last_streak_update"]=today` 는 찍혀서 같은 날 도는 전량 실행이 streak 갱신을 건너뛴다. → **필터는 `run_bids` 안에서 `update_streaks` 뒤에** 걸어야 한다. (§1.3)

**Primary recommendation:**
`run_ads.py` bids 서브파서에 `--only-ads` · `--preview-out` 2개를 붙이고, `bids.run_bids`/`run_revert` 에 `only_ads=None` 기본인자 1개씩 + plan dict 에 `result`/`error` 키를 추가한다(총 **15줄 미만**). 웹앱은 `subprocess.Popen(..., env={"PYTHONUNBUFFERED":"1"}, start_new_session=True, stdout=<append-only 로그파일>)` 로 띄우고, SSE 는 **매 접속마다 로그 전량을 재생한 뒤 tail** 한다. 보안은 `TrustedHostMiddleware` + 쓰기 메서드 전용 Origin 가드 + 부팅 토큰 헤더 3층(§4 에 실측 검증된 코드가 있다).

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| 6규칙 판정 · 입찰가 계산 · 쿨다운/상한/연속실패 가드 | **CLI 서브프로세스** | — | 검증된 로직. 웹앱이 재계산하면 진실이 둘이 된다 (PROJECT.md 제약) |
| 백업(`before_bids_*.json`) 생성·병합 | **CLI 서브프로세스** | — | `Important 1` 병합 규칙이 CLI 안에 있다. 웹앱이 이 파일을 쓰면 최초 원본이 날아간다 (D-13) |
| ledger 갱신 (`raises`/`streak`/`reverted`) | **CLI 서브프로세스** | — | run-dir 바깥 누적 상태. 웹앱은 읽지도 쓰지도 않는다 |
| 광고 API 호출 · 자격증명 소지 | **CLI 서브프로세스** | — | `nvad.py` 가 `~/.eroom/naver-ads.json` 을 직접 읽는다. **웹앱은 시크릿을 손에 쥐지 않는다** (SAFE-03) |
| 보드 데이터 (판정 결과 표시) | **웹앱 서버 (읽기 전용)** | — | `run-dir/result.json` 을 읽어 투영만. CLI 를 실행하지 않는다 (STACK.md "세 번째 길") |
| 상품 단위 접기 (`mallProductId` 그룹핑) | **웹앱 서버** | 브라우저 | 순수 표현 변환. 판정값을 만들지 않는다 |
| 대상 목록 확정 (adId 집합) | **웹앱 서버 → 파일** | 브라우저(선택 UI) | FLOW-02: 화면 상태가 아니라 파일이 진실. 미리보기·실행·되돌리기가 같은 파일을 지목 (D-11) |
| 잡 레지스트리 · 로그 오프셋 · 진행 상태 | **웹앱 서버 (SQLite + 로그파일)** | — | `--workers 1` 이라 프로세스 안에 둬도 되지만, 서버 재시작 생존을 위해 SQLite |
| 정렬 · 필터 · 검색 · 다중선택 | **브라우저 (Tabulator)** | — | 2,637행 / 547KB. 클라이언트 사이드 한계 안 (§2.3) |
| 진행 로그 렌더 | **브라우저 (htmx-ext-sse)** | 웹앱 서버(전량 재생) | JS 0줄. 단 재연결 시 EventSource 가 새로 만들어지므로 서버가 전량 재생 책임을 진다 (§5.4) |
| 인증 · 권한 | **없음 (Out of Scope)** | — | 1인 로컬. 대신 SAFE-01~03 으로 공격면만 막는다 |

---

## Project Constraints (from CLAUDE.md)

planner 는 아래를 locked decision 과 같은 권위로 다뤄라.

| 지시 | 이 단계에 어떻게 걸리나 |
|---|---|
| **코드 주석 한국어, Python 기반, try-except 포함** | 모든 신규 `.py` 파일. CLI 패치 주석도 한국어 |
| **사용자에게 반말** | UI 문구·에러 메시지·로그 톤 |
| **웹앱은 CLI 래퍼다. 검증된 로직·테스트·가드레일을 재작성하지 않는다** | §1 의 패치가 **필터/출력 주입구**에 한정되는 이유 |
| **모든 쓰기 작업은 dry-run 선행** | `bids --commit` 전에 반드시 `bids`(dry-run) 를 통과한 preview 파일이 있어야 한다 |
| **진실의 원천: 로컬 대장을 정본으로 삼지 않는다** | jobs DB 의 `board_cache` 는 언제든 `result.json` 에서 재생성 가능한 캐시. 판정값의 정본이 아니다 |
| **광고 계정은 `~/.eroom/naver-ads.json` 에 항목 추가로만 늘어난다 (4→6)** | 계정 alias 를 코드·템플릿·SQL 어디에도 리터럴로 쓰지 마라 (§3) |
| **`uvicorn --workers 1` 협상 불가** | 실행 스크립트·launchd plist 에 고정 |
| **npm 빌드체인 금지 / Docker 금지 / 태스크 큐 금지 / WebSocket 금지** | 스택 재검토 금지 |
| **htmx 4.0.0 쓰지 마라 — 2.0.10 고정** | npm dist-tags 실측 확인: `latest=2.0.10`, `next=4.0.0` (§Standard Stack) |
| **GSD Workflow Enforcement** | 이 단계 구현은 `/gsd-execute-phase` 로 들어간다 |

---

## 1. 래핑 대상 CLI 의 실제 표면 (전부 소스 실측)

읽은 파일: `.claude/skills/naver-ads-weekly/scripts/` 의 `run_ads.py`(224줄) · `bids.py`(282) · `ads_rules.py`(123) · `ledger.py`(114) · `nvad.py`(90) · `collect.py`(96) · `reports.py`(88) + 테스트 6종.

### 1.1 서브커맨드 · argv · 종료코드 [VERIFIED: 소스 + 실행]

`run_ads.py` 진입점 (`main()` 224줄):

| 서브커맨드 | 공통 플래그 | 전용 플래그 | 광고 API 쓰기 | 소요(실측) |
|---|---|---|---|---|
| `prep` | `--run-dir <이름>` `--account <alias...>` | — | 소재/통계 **GET** + `POST /stat-reports`(리포트 잡 생성. 광고를 바꾸지 않는다) | **~3분/계정** (accounts/ mtime 간격: 00:31→00:34→00:36→00:39) |
| `run` | `--run-dir` `--account` | — | 없음 (디스크만) | 초 단위 |
| `apply` | `--run-dir` `--account` | `--sheet <ID>` `--no-sheet` | 없음 (구글시트는 별개) | 초~분 |
| `bids` | `--run-dir` `--account` | `--commit` `--revert` | **PUT /ncc/ads/{adId}** (`--commit` 일 때만) | dry-run **0.066초** · commit ≈ 12건/초 |
| `prune` | `--run-dir` `--account` | `--commit` | DELETE (Phase 2) | — |

> `--account` 는 `nargs="*"` 다. 즉 `--account a b c` 형태이고, **`--account` 를 아예 안 주면 `None` → 전 계정**이다. `--account`(값 없이)만 주면 `[]` → falsy → `_accounts(None)` 과 같아져 **전 계정**이 된다. 웹앱은 계정을 좁힐 때 반드시 값을 함께 넘겨라.

**종료코드 — 이게 함정이다** [VERIFIED: 소스 읽기 + `bids` 실행 exit=0]

```
prep  : 계정 0개면 1. 그 외 항상 0 (계정별 수집 실패는 로그만 찍고 계속)
run   : accounts/ 없으면 1. 그 외 항상 0
apply : result.json 없거나 report 쓰기 실패면 1. 그 외 0
bids  : result.json 없거나 못 읽으면 1. 그 외 항상 0 ← PUT 이 전량 실패해도 0
prune : 항상 0
argparse 오류 : 2
```

→ **작업 성공 여부를 종료코드로 판단하면 안 된다.** 반드시 `--preview-out` 결과 파일을 읽어서 판단해라. 이게 D-02/D-03 이 파일 출력을 요구하는 진짜 이유다.

### 1.2 stdout 줄 포맷 — 센티널이 없다 [VERIFIED: 실행 출력]

```
  이력 갱신: 인상 뒤에도 노출0 9건 · 노출 회복 0건
[cy728] 대상 9건 → 인상 9
    인상           70→80   까스통 실린더 산소통트롤리 이동 운반기 거치대 손수레
    …(최대 10줄)
    … 외 1185건
  (dry-run — --commit 을 주면 실제로 바꾼다)
```

- **`###DETAIL###` 같은 센티널이 없다.** `detail_batch.py` 에는 있지만 `run_ads.py` 계열엔 없다.
- **`flush=True` 가 전 소스에 `prune.py:115` 단 한 줄뿐이다.** → §5.1 의 `PYTHONUNBUFFERED=1` 이 필수다.
- 진행률이 없다. `bids --commit` 은 1,195건을 100초 동안 도는데 그동안 실패 줄(`    ✗ {adId} {err}`) 외엔 아무것도 안 찍는다. **화면에 "진행 중"을 보여주려면 로그가 아니라 경과시간 + 스피너로 가야 한다.** (진행률 주입은 CLI 로직 변경이므로 Phase 1 범위 밖으로 권고)
- 로그 총량 실측: `bids` dry-run 4계정 = **53줄 / 4,551바이트**.

### 1.3 `--only-ads` · `--preview-out` — 지금 없다. 붙일 자리와 정확한 diff

**현재 `cmd_bids` (run_ads.py:129-157) 의 실제 코드:**

```python
for alias, v in result.get("accounts", {}).items():
    acct = accts.get(alias)
    if not acct:
        print(f"[{alias}] 자격증명 없음 — 건너뛴다")
        continue
    bids.run_bids(acct, run_dir, v.get("rules", {}).get("①노출0", []), commit=args.commit)
    #  ↑ 리턴값을 버린다 (D-02 가 지적한 그대로)
```

**권고 패치 (총 15줄 미만). 판정·계산·백업·ledger 는 한 줄도 안 건드린다.**

`run_ads.py` — 서브파서:
```python
s = sub.add_parser("bids")
s.add_argument("--run-dir")
s.add_argument("--account", nargs="*")
s.add_argument("--commit", action="store_true", help="실제로 입찰가를 바꾼다")
s.add_argument("--revert", action="store_true", help="...")
s.add_argument("--only-ads", help="대상 adId 목록 JSON 파일 — 이 목록에 있는 소재만 처리한다")
s.add_argument("--preview-out", help="계정별 계획/결과를 이 JSON 파일에 쓴다")
```

`run_ads.py` — `cmd_bids` 안:
```python
def _load_only_ads(path):
    """대상 adId 집합을 읽는다.

    ⚠ 읽기 실패를 '전량' 으로 폴백하면 안 된다 — 5건 고른 줄 알았는데 2,242건이
    올라가는 게 이 명령에서 가장 비싼 실수다. 실패는 그냥 실패다.
    """
    if not path:
        return None
    ids = json.loads(Path(path).read_text(encoding="utf-8"))
    return set(ids if isinstance(ids, list) else ids["adIds"])
```
```python
    try:
        only = _load_only_ads(args.only_ads)
    except Exception as e:
        print(f"--only-ads 읽기 실패 — 전량 실행으로 폴백하지 않는다: {type(e).__name__}: {e}")
        return 1

    outputs = {}
    if args.revert:
        for alias, acct in accts.items():
            outputs[alias] = bids.run_revert(acct, run_dir, commit=args.commit, only_ads=only)
        _dump_preview(args.preview_out, outputs)   # try-except 로 감싼다
        return 0
    ...
        outputs[alias] = bids.run_bids(
            acct, run_dir, v.get("rules", {}).get("①노출0", []),
            commit=args.commit, only_ads=only)
    _dump_preview(args.preview_out, outputs)
    return 0
```

`bids.py` — **필터는 반드시 `update_streaks` 뒤에 건다** (§Summary 발견 5):
```python
def run_bids(acct, run_dir, rows, commit=False, log=print, only_ads=None):
    ...
    # update_streaks 는 rows 전량을 봐야 한다 — 여기를 거르면 연속실패 카운팅이 조용히 빠진다
    update_streaks(led, {r["adId"] for r in rows}, recovered_ids, today, log=log)
    ...
    if only_ads is not None:
        rows = [r for r in rows if r["adId"] in only_ads]   # ← 딱 이 자리
    plans = [plan_raise(r, led, today=today) for r in rows]
```

`bids.py` — `run_revert`:
```python
def run_revert(acct, run_dir, commit=False, log=print, only_ads=None):
    ...
    targets = [ad_id for ad_id, attr in backup.items()
               if attr is not None and (only_ads is None or ad_id in only_ads)]
```

**회귀 안전성** [VERIFIED: 기존 테스트 100개 전량 통과 확인]
`test_bids.py:166,200` 은 `run_revert(acct, run_dir, commit=...)` 로, `:248,262` 는 `run_bids(acct, run_dir, rows, commit=True, log=...)` 로 부른다 → `only_ads` 기본값 `None` → 동작 불변.

### 1.4 `--preview-out` 이 담아야 하는 것 — `run_bids` 는 이미 다 계산해 놨다

`run_bids` 현재 리턴값 (bids.py:173, 196, 221):

| 경로 | 리턴 |
|---|---|
| ads.json 읽기 실패 | `{}` ← **빈 dict 를 성공으로 보면 안 된다** |
| dry-run | `{"plans": [...], "counts": {...}, "committed": 0}` |
| 백업 실패 | `{"plans","counts","committed":0,"aborted":"backup_failed"}` |
| commit | `{"plans","counts","committed":ok,"failed":fail}` |

`plans[i]` (bids.py `plan_raise:32`):
```json
{"adId":"nad-a001-02-000000495390006","title":"전기 옥외 분전함…",
 "action":"인상","from":70,"to":80,"useGroupBid":true}
```
`action` 5종 (`ledger.bid_decision`): `인상` · `최근인상`(쿨다운 6일) · `연속실패중단`(streak≥3) · `상한도달`(>200) · `입찰가불명`(bid None).

→ **BID-02(현재가→인상 후) 와 BID-03(그룹 출발점) 은 `from`/`to`/`useGroupBid` 로 그대로 충족된다.** 웹앱이 계산할 게 없다.

### 1.5 FLOW-05(항목 단위 성공/실패/스킵) — **현재 리턴값으로는 불가능하다** [VERIFIED: 소스]

`run_bids` commit 루프(bids.py:199-221)는 `ok`/`fail` **카운트만** 세고, 실패 사유는 `log(f"    ✗ {p['adId']} {err}")` 로 stdout 에만 나간다. D-03 은 "로그 파싱으로 FLOW-05 를 충족시키지 않는다" 고 못박았다.

**최소 추가 (plan dict 에 키를 더하기만 한다 — 기존 필드 불변):**
```python
    for p in plans:
        if p["action"] != "인상":
            p["result"], p["error"] = "스킵", p["action"]   # 스킵 사유 = action
            continue
        ad_obj = ad_by_id.get(p["adId"])
        if not ad_obj:
            fail += 1
            p["result"], p["error"] = "실패", "스냅샷에 소재 없음"
            continue
        good, err = apply_raise(acct, ad_obj, p["to"])
        if good:
            ok += 1; p["result"], p["error"] = "성공", ""
            ledger.record_raise(led, p["adId"], today, p["from"], p["to"])
        else:
            fail += 1; p["result"], p["error"] = "실패", err
            log(f"    ✗ {p['adId']} {err}")
```
테스트는 `p["action"]`/`p["from"]`/`p["to"]` 와 `out["committed"]`/`out["targets"]` 만 검사하므로(§1.3 근거) 키 추가는 안전하다.

이 한 덩어리가 **D-03 · D-10(미리보기 diff) · D-13(인상 성공 adId 목록) 세 개를 동시에 푼다.**

### 1.6 `run_revert` 가 왜 위험한지 — 지금 디스크 상태가 증거다 [VERIFIED: 실제 파일]

```
runs/2026-08-30/before_bids_cy728.json      9건
runs/2026-08-30/before_bids_cy7728.json    10건
runs/2026-08-30/before_bids_ownway1.json  1,195건
runs/2026-08-30/before_bids_pogeunae.json 1,028건   합계 2,242건
```
`ledger/*.json` 도 같은 수(2,242건)가 `{"raises":[{"date":"2026-08-30","from":70,"to":80}],"streak":0}` 로 찍혀 있고 `reverted` 는 **0건**이다.

→ 이 run-dir 에서 `bids --revert --commit` 을 그냥 누르면 **2,242건이 전부 풀린다.** D-12 가 정확히 맞다.

**추가로 발견한 함정 — 날짜를 넘긴 되돌리기** [VERIFIED: `ledger.record_reverted:69`]
```python
if e["raises"] and e["raises"][-1].get("date") == date_str:
    e["raises"][-1]["reverted"] = True
```
`run_revert` 의 `date_str` 은 `date.today()` 다. **월요일에 올리고 화요일에 되돌리면 `reverted` 플래그가 안 찍힌다.** 그러면 `last_raise_date` 가 그 인상을 살아있는 것으로 보고 → 쿨다운 6일 동안 재인상 차단 + `update_streaks` 가 연속실패를 쌓는다.
Phase 1 범위에서 이건 **로직 변경이라 고치지 않는다.** 대신 화면에 **"되돌리기는 인상한 당일에 눌러야 이력에 정확히 반영된다"** 를 안내하고, 날짜가 다르면 경고 배너를 띄워라. (Open Question Q2)

### 1.7 웹앱이 절대 하면 안 되는 것 (CLI 가 이미 하고 있어서)

| 하지 마라 | 이유 (근거 줄) |
|---|---|
| `before_bids_<alias>.json` 을 웹앱이 쓰기 | `bids.py:176-181` Important 1 — 같은 키는 **먼저 것 유지**. 덮으면 최초 원본이 사라져 영영 못 되돌린다 |
| 입찰가를 웹앱이 계산 | `plan_raise:30` 의 `base = groupBid if useGroupBid else bid` — 재구현하면 92%가 틀린다 (§2.5) |
| `ledger/*.json` 을 웹앱이 쓰기 | run-dir **바깥**(`run_dir.parent.parent/ledger`)에 회차를 넘어 누적. 웹앱이 끼면 회차 간 상태가 깨진다 |
| 미리보기 값을 실행에 강제 주입 | D-09 — 쿨다운/상한/연속실패 가드가 실행 시점에 다시 돌아야 안전 |
| dry-run 을 여러 번 눌렀다고 걱정 | `update_streaks` 는 dry-run 에서 **메모리만** 갱신하고 `ledger.save` 는 commit 경로의 `finally` 에서만 돈다 — 미리보기는 이력을 오염시키지 않는다 [VERIFIED] |

---

## 2. run-dir 산출물 JSON 의 실제 스키마 (실데이터 실측)

측정 대상: `~/python_work/data/naver-ads/runs/2026-08-30/` (최신 회차, **20일 전**)

### 2.1 파일 목록과 크기 [VERIFIED: ls]

```
runs/2026-08-30/
├── accounts/<alias>/
│   ├── ads.json        ← 소재 전량 + groups. ownway1 2.6MB · pogeunae 2.7MB  ※ 브라우저로 보내지 마라
│   ├── stats_7d.json   ← {adId: stat}  17KB
│   ├── stats_30d.json  ← {adId: stat}  18KB
│   └── purchase.json   ← {adId:{cnt,amt}}  521B
├── result.json         ← 판정 결과. 879KB  ★ 보드의 유일한 입력
├── prep_summary.json   ← 계정별 수집 요약 + window7/window30  923B
├── report.md           ← 41KB
└── before_bids_<alias>.json  ← 인상 직전 원본 adAttr
```

### 2.2 `result.json` 스키마 [VERIFIED: 직접 파싱]

```json
{ "generated": "2026-08-30",
  "accounts": {
    "cy728": { "summary": {"ads":223,"live":223,"cost":205056,"purAmt":656150,"purCnt":6},
               "rules": { "①노출0":[...], "②썸네일교체":[...], "③원인분석":[...],
                          "④효자후보":[...], "⑤효자확정":[...], "⑥삭제대상":[...] } },
    "cy7728": {...}, "ownway1": {...}, "pogeunae": {...} } }
```
계정 alias 는 **`result.json["accounts"]` 의 키**다 — 보드 계정 필터를 여기서 뽑으면 하드코딩이 0이다.

**규칙별 행 수 (총 2,726 — CONTEXT.md 실측과 일치):**

| 계정 | ① | ② | ③ | ④ | ⑤ | ⑥ |
|---|---|---|---|---|---|---|
| cy728 | 9 | 39 | 22 | 30 | 6 | 0 |
| cy7728 | 10 | 23 | 15 | 19 | 4 | 0 |
| ownway1 | **1,195** | 33 | 13 | 20 | 9 | 20 |
| pogeunae | **1,028** | 103 | 28 | 69 | 19 | 12 |
| **합계** | **2,242** | 198 | 78 | 138 | 38 | 32 |

**행 필드 — 규칙마다 다르다.** [VERIFIED: 전 계정 전 규칙 키 집합 추출]

| 규칙 | 필드 |
|---|---|
| **①노출0 · ⑥삭제대상** | `adId · adGroup · title · mallProductId · bid · useGroupBid · groupBid` — **`imp`/`clk`/`ctr`/`rank`/`cost` 가 없다** |
| ②③④ | 위 + `imp · clk · ctr · rank · cost` |
| ⑤효자확정 | 위 + `purCnt · purAmt` |

실제 행:
```json
// ① (ownway1)
{"adId":"nad-a001-02-000000495390006","adGroup":"판매상품_11-1_와이제이스컴퍼니",
 "title":"전기 옥외 분전함 스텐 단자함 방수 노출 컨트롤 야외",
 "mallProductId":"12898250989","bid":70,"useGroupBid":true,"groupBid":70}
// ⑤ (ownway1)
{"adId":"nad-a001-02-000000424263795","adGroup":"판매상품_14-1_와이제이크컴퍼니",
 "title":"대형테이블 작업다이 …","mallProductId":"12471298375",
 "bid":140,"useGroupBid":false,"groupBid":100,
 "imp":5119,"clk":84,"ctr":1.64,"rank":5.7,"cost":14221,"purCnt":2,"purAmt":548200}
```

> ⚠ **CONTEXT.md `<code_context>` 위험 1이 실데이터로 확인됐다.** 보드 렌더가 `row.imp` 를 무조건 읽으면 **①+⑥ 2,274행**에서 `undefined` 가 된다. Tabulator 컬럼에 `formatter` 를 쓰든 서버 투영에서 `None` 으로 채우든 명시적으로 처리해라.
> `cost` 는 **광고비**지 매출이 아니다 (`ads_rules._with_stat:50` 주석 + SKILL.md "반드시 지킬 것 2"). 컬럼 헤더를 "매출"로 쓰면 안 된다.

### 2.3 D-05(상품 단위 접기)는 실제로 가능한가 — **가능하다** [VERIFIED: 집계]

| 측정 | 값 |
|---|---|
| `mallProductId` 결측 (①노출0 2,242행) | **0건** |
| ① 안에서 distinct `(alias, mallProductId)` | **2,241** → 팬아웃 최대 **2**, 2개 이상인 상품 **1개**. **사실상 1:1** |
| 6규칙 전체 distinct `(alias, mallProductId)` | **2,637** → 팬아웃 최대 3, 2개 이상 **88개** |
| 상품이 속한 규칙 수 분포 | 1규칙 2,550 · 2규칙 86 · 3규칙 1 |
| 소재(adId) 가 속한 규칙 수 | 1규칙 2,562 · 2규칙 82 (예: ②와 ③에 동시에 뜬다) |
| distinct adId | 2,644 (총행 2,726) |

→ **D-06 이 구조적으로 옳다.** 상품 줄 하나에 ①과 ③ 소재가 섞여 있을 수 있으므로, "이 버튼이 N건에 적용됩니다"의 N 은 **그 상품의 ①행 개수**여야 한다 (전체 소재 수가 아니다).
→ `adId` 는 계정 간 충돌이 없지만(prefix 가 다르다), 접기 키는 **반드시 `(alias, mallProductId)`** 로 해라. `mallProductId` 는 스마트스토어 상품ID라 다른 계정에서 같은 값이 나올 수 있다고 가정하는 편이 안전하다. [ASSUMED — 이번 데이터에선 계정 간 중복을 확인하지 못했다]

### 2.4 보드 페이로드 크기 — 클라이언트 사이드로 충분 [VERIFIED: 측정]

| 형태 | 행 | JSON | gzip |
|---|---|---|---|
| 소재 단위 (필요 컬럼만 투영) | 2,726 | 734KB | **109KB** |
| **상품 단위 접기 (권장)** | **2,637** | **547KB** | **95KB** |
| 원본 `result.json` 그대로 | — | 879KB | — |

→ Tabulator 클라이언트 사이드 한계(≈5,000행) 안. **서버사이드 페이징 불필요** (Out of Scope 확정).
→ 단 **`GZipMiddleware` 를 반드시 켜라** — 547KB → 95KB. 안 켜면 로컬이라도 파싱·전송이 체감된다.
→ `accounts/*/ads.json`(2.6MB×2)은 절대 브라우저로 보내지 마라. 웹앱도 읽을 일이 없다.

### 2.5 그룹 기본입찰가 (Success Criteria 2 / BID-03) — **산출물에 이미 있다** [VERIFIED]

`ads_rules.ad_info:38-46` 이 모든 판정행에 `bid`(= `effective_bid` 결과) · `useGroupBid` · `groupBid` 를 함께 싣는다. `groupBid` 의 출처는 `collect.fetch_ads:40` 의 `g.get("bidAmt")` (광고그룹 객체).

**실측 — 이게 왜 결정적인지:**

| 측정 (①노출0 2,242행) | 값 |
|---|---|
| `useGroupBid == true` | **2,063건 (92.0%)** |
| `bid` 가 `None` | **0건** |

→ **92%가 그룹입찰이다.** 웹앱이 `adAttr.bidAmt`(잠자는 값)로 미리보기를 그리면 거의 전량이 틀린다. 실제 백업 파일 샘플이 그 증거다:
```json
"nad-a001-02-000000495390006": {"bidAmt": 50, "useGroupBidAmt": true}
```
잠자던 값은 **50**인데 `result.json` 의 `bid`(= groupBid) 는 **70**이고 인상 목표는 **80**이다. 재계산했으면 50→60 으로 **내렸을** 것이다.

→ **결론: 미리보기 값은 `--preview-out` 의 `from`/`to` 를 그대로 표시해라. 웹앱은 산술을 하지 않는다.**

### 2.6 신선도 (D-16) [VERIFIED]

```
회차 목록: ['2026-08-29', '2026-08-30']
최신 회차 2026-08-30 · 20일 전 · result.json 존재
```
- 회차 목록 = `data_root/naver-ads/runs/*` 디렉터리명(ISO 날짜)을 정렬. `result.json` 이 있는 것만 보드에 띄워라 (`prep` 만 돌고 `run` 을 안 돌린 run-dir 이 있을 수 있다).
- 경과일 = `date.today() - date.fromisoformat(dirname)`.
- `prep_summary.json` 의 `window7`/`window30` 에 **실제 통계 기간**이 있다(`["2026-08-22","2026-08-28"]`). 디렉터리 날짜보다 이게 더 정직하다 — `collect.window()` 가 `until = today - 2일` 이라 회차명보다 항상 2일 더 낡다. **신선도 배너에 둘 다 보여줘라**: `2026-08-30 회차 · 20일 전 · 통계 기간 08-22~08-28`.

---

## 3. 계정 설정의 확장 경로 (4 → 6) [VERIFIED]

### 3.1 실제 파일

```
-rw-------  /Users/choiyongsmacbook/.eroom/naver-ads.json   984B
{"accounts": [
  {"alias":"cy728",   "customer_id":"4158478","api_key":"…","secret_key":"…"},
  {"alias":"cy7728",  "customer_id":"3415467","api_key":"…","secret_key":"…"},
  {"alias":"ownway1", "customer_id":"3406540","api_key":"…","secret_key":"…"},
  {"alias":"pogeunae","customer_id":"3307029","api_key":"…","secret_key":"…"}]}
```
`nvad.load_accounts()` (nvad.py:26-32) — `dict` 면 `d["accounts"]`, `list` 면 그대로. 실패하면 `[]`.
경로는 `nvad.py:21` 에 `CRED = Path.home()/".eroom"/"naver-ads.json"` 로 **상수로 박혀 있다**.

### 3.2 웹앱이 하드코딩하면 안 되는 것

| 절대 박지 마라 | 대신 |
|---|---|
| 계정 alias 리터럴 (`"cy728"` 등) | 보드 필터: `result.json["accounts"]` 의 키. 계정 순서는 `sorted()` |
| 계정 개수 (4) | 어디에도 쓰지 마라. 상한(D-08)은 **계정별** 1,500이지 총합이 아니다 |
| `data_root` 절대경로 | `workspace.toml [paths] data_root` → 없으면 `~/python_work/data` (§3.3) |
| run-dir 이름 | 디렉터리 스캔 |
| `~/.eroom/naver-ads.json` 경로 (가급적) | §3.4 |

### 3.3 `data_root` 발견 — CLI 와 같은 규약, import 없이 [VERIFIED: 실행]

`run_ads.data_root()` 는 `eroomlib.config.cfg("paths.data_root")` → 실패하면 `~/python_work/data`. 웹앱은 `eroomlib` 를 import 할 필요 없이 stdlib 로 같은 결과를 낸다(Python 3.11+ `tomllib`):

```python
def data_root() -> Path:
    """CLI 의 run_ads.data_root() 와 같은 규약. 절대경로를 박지 않는다."""
    try:
        import tomllib
        cfg = tomllib.loads((REPO / "workspace.toml").read_text(encoding="utf-8"))
        p = cfg.get("paths", {}).get("data_root")
        if p:
            return Path(p).expanduser()
    except Exception:
        pass
    return Path.home() / "python_work" / "data"
```
실행 확인: `data_root = /Users/choiyongsmacbook/python_work/data` · 회차 2개 발견.

### 3.4 "자격증명 있는 계정" 목록이 필요할 때

`cmd_bids` 는 자격증명이 없는 계정을 `[alias] 자격증명 없음 — 건너뛴다` 로 **조용히 스킵**한다(stdout 에만). 보드가 "이 계정은 실행 못 한다"를 미리 보여주려면 목록이 필요하다. 선택지 둘:

| 방안 | 장 | 단 |
|---|---|---|
| **(권장) `run_ads.py` 에 `accounts` 서브커맨드 추가 (~8줄, 읽기 전용)**<br>`print(json.dumps([{"alias":a.get("alias"),"customer_id":str(a.get("customer_id"))} for a in nvad.load_accounts()]))` | 시크릿이 웹앱 프로세스에 **한 번도 안 들어온다**. 경로 상수가 한 곳 | D-01 의 문구("입력 필터 플래그")를 약간 넘는다 — 다만 쓰기가 0이라 위험도 0 |
| 웹앱이 `~/.eroom/naver-ads.json` 직접 읽고 `alias`/`customer_id` 만 투영 | CLI 무변경 | 경로 상수가 두 곳. 시크릿이 웹앱 메모리에 잠깐 들어온다 (화이트리스트 투영 필수) |

→ **`accounts` 서브커맨드를 권장**한다. SAFE-03 을 구조적으로 보장한다.
→ 보드 필터 자체는 `result.json` 만으로 충분하므로, 이 목록은 **"실행 가능 여부 뱃지"** 용도로만 쓴다.

---

## 4. 로컬 웹앱 보안 3종 — 실측 검증된 구현

이 절의 코드는 이 맥북에서 실제로 띄워 `curl` 로 6케이스를 통과시킨 것이다.

### 4.1 검증 결과 [VERIFIED: 실행]

```
1) 정상 GET                                      → 200
2) Host: evil.com (DNS rebinding 모사)           → 400 "Invalid host header"
3) 토큰 없는 POST                                 → 403 "토큰 거부"
4) Origin: https://evil.com + 올바른 토큰          → 403 "origin 거부"
5) Origin: http://127.0.0.1:8765 + 올바른 토큰     → 200 "wrote"
6) 올바른 Origin + 틀린 토큰                       → 403 "토큰 거부"
8) lsof → TCP 127.0.0.1:8765 (LISTEN)  ※ 0.0.0.0 아님
```

### 4.2 Host 헤더 (SAFE-01 전반) [VERIFIED: 시그니처 + 소스]

```python
from starlette.middleware.trustedhost import TrustedHostMiddleware
app.add_middleware(TrustedHostMiddleware,
                   allowed_hosts=["127.0.0.1", "localhost"], www_redirect=False)
```
- 실측 시그니처: `(self, app, allowed_hosts: Sequence[str] | None = None, www_redirect: bool = True)` (starlette 1.6.0)
- **포트를 떼고 매칭한다** → `Host: 127.0.0.1:8765` 통과, `allowed_hosts` 에 포트를 적으면 안 된다. [CITED: github.com/Kludex/starlette/blob/main/starlette/middleware/trustedhost.py]
- 실패 시 `PlainTextResponse("Invalid host header", status_code=400)`
- `www_redirect=False` 를 **반드시 명시**해라. 기본값 `True` 는 쓸모없는 리다이렉트 분기를 남긴다.
- `allowed_hosts=["*"]` 는 미들웨어를 끄는 것과 같다 — 절대 쓰지 마라.

**이게 막는 것:** DNS rebinding. 공격자가 `evil.com` 을 `127.0.0.1` 로 재바인딩해도 브라우저가 보내는 `Host` 는 `evil.com` 이라 400 에서 멈춘다.

### 4.3 Origin/Referer (SAFE-01 후반, CSRF)

```python
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
ALLOWED_ORIGINS = {"http://127.0.0.1:8765", "http://localhost:8765"}

@app.middleware("http")
async def guard(request: Request, call_next):
    if request.method not in SAFE_METHODS:
        origin = request.headers.get("origin")
        if origin is not None and origin not in ALLOWED_ORIGINS:
            return PlainTextResponse("origin 거부", status_code=403)
        # Origin 이 없는 쓰기 요청(일부 구형 폼·비브라우저)은 Sec-Fetch-Site 로 한 번 더 본다
        if origin is None and request.headers.get("sec-fetch-site") not in (None, "same-origin"):
            return PlainTextResponse("sec-fetch-site 거부", status_code=403)
        ...토큰 검사...
    return await call_next(request)
```

**"GET 은 안전하고 쓰기 메서드만 막으면 되는가?"에 대한 정확한 답:**

- 브라우저는 **모든 POST/PUT/DELETE 에 `Origin` 헤더를 붙인다.** 교차 사이트 `<form>` POST 도 마찬가지다. → 쓰기 메서드 차단은 성립한다.
- **단순 교차 사이트 GET(`<img src>`, `<script src>`, 링크)은 `Origin` 이 없다.** 따라서 **부수효과가 있는 엔드포인트를 GET 으로 만들면 이 방어가 통째로 무력화된다.**
  → **규칙: 상태를 바꾸는 엔드포인트는 절대 GET 으로 만들지 마라.** htmx 에서 `hx-post`/`hx-delete` 만 쓴다.
- 포트가 바뀌면(`8765` 고정 안 하면) `ALLOWED_ORIGINS` 가 깨진다 → 포트를 설정값 하나로 두고 미들웨어가 거기서 읽게 해라.

### 4.4 부팅 토큰 (SAFE-02) — 실제 코드 형태

```python
import secrets
BOOT_TOKEN = secrets.token_urlsafe(32)      # 서버 기동 시 1회
COOKIE = "ct_session"

# 기동 로그 (이 URL 을 브라우저에 붙여넣는다)
print(f"→ http://127.0.0.1:{PORT}/?t={BOOT_TOKEN}")

@app.get("/")
def home(request: Request, t: str | None = None):
    """?t= 로 들어오면 쿠키를 심고 깨끗한 URL 로 리다이렉트한다 — 주소창·히스토리에
    토큰이 남지 않게. 쿠키가 이미 맞으면 그냥 보드를 그린다."""
    cookie_ok = secrets.compare_digest(request.cookies.get(COOKIE, ""), BOOT_TOKEN)
    if t and secrets.compare_digest(t, BOOT_TOKEN):
        r = RedirectResponse("/", status_code=303)
        r.set_cookie(COOKIE, BOOT_TOKEN, httponly=True, samesite="strict", path="/")
        return r
    if not cookie_ok:
        return PlainTextResponse("토큰이 필요하다 — 서버 기동 로그의 URL 로 들어와라", 403)
    # 쓰기용 토큰을 페이지에 심는다 → htmx 가 모든 요청에 헤더로 붙인다
    return templates.TemplateResponse("board.html", {"request": request, "token": BOOT_TOKEN})
```
```html
<body hx-headers='{"X-CT-Token": "{{ token }}"}'>
```
```python
# 쓰기 가드 (§4.3 미들웨어 안)
tok = request.headers.get("x-ct-token") or ""
if not secrets.compare_digest(tok, BOOT_TOKEN):
    return PlainTextResponse("토큰 거부", status_code=403)
```

**왜 쿠키가 아니라 헤더로 검사하나:** 쿠키는 브라우저가 자동으로 붙여서 CSRF 방어가 되지 않는다(`SameSite=Strict` 가 도와주지만 한 겹뿐이다). 커스텀 헤더는 **교차 오리진에서 붙일 수 없다** — CORS preflight 가 필요한데 우리는 CORS 를 아예 안 열었다. 쿠키는 "페이지 접근", 헤더는 "쓰기 인가" 로 역할을 나눈다.

**세 가지 주의:**
- `secrets.compare_digest` 를 써라 (`==` 금지 — 타이밍 공격). 로컬이라 과해 보여도 비용이 0이다.
- `BOOT_TOKEN` 은 **서버 재시작마다 바뀐다.** 이게 의도다. `--reload` 로 개발 중엔 매 리로드마다 바뀌니 개발 편의를 위해 `CT_DEV_TOKEN` 환경변수로 고정할 수 있게 해라(운영 기본은 랜덤).
- 토큰을 **쿼리스트링에 남기지 마라.** 위 코드처럼 303 리다이렉트로 즉시 털어낸다.

### 4.5 시크릿 비노출 (SAFE-03) — 누출 지점 전수조사 [VERIFIED: grep]

시크릿이 나타나는 지점은 **소스 전체에서 3줄뿐**이다:
```
nvad.py:46   "X-API-KEY": acct["api_key"],
nvad.py:47   "X-Customer": str(acct["customer_id"]),
nvad.py:48   "X-Signature": sign(acct["secret_key"], ts, method, path),
```
`acct` 전체를 `print`/`log` 하는 코드는 **없다** (grep 결과 alias 추출 4곳뿐). 즉 **정상 경로에서 CLI stdout 으로 시크릿이 새지 않는다.**

**그럼에도 웹앱이 지켜야 할 것:**

| 지점 | 규칙 |
|---|---|
| **자식 프로세스 env** | 자격증명을 env 로 넘기지 마라. `nvad.py` 가 파일을 직접 읽으므로 **넘길 필요가 없다.** env 로 넘기면 `ps -E` 에 뜬다 |
| **웹앱이 계정 JSON 을 읽을 때** | 블랙리스트 금지. **화이트리스트 투영**: `{"alias":…, "customer_id":…}` 만 새 dict 로 만든다. 키가 추가돼도 안 샌다 |
| **로그파일 → SSE 경계** | 자식이 예기치 않게 시크릿을 찍을 가능성에 대비해 **쓰기 시점 스크러버** 하나를 둬라: 기동 시 계정 JSON 에서 `api_key`/`secret_key` 값을 모아두고, 로그 라인에 포함돼 있으면 `***` 로 치환 후 기록. 비용 ≈ 문자열 replace |
| **예외 핸들러** | `debug=False` (기본). 500 응답에 트레이스백을 넣지 마라. FastAPI 기본이 그렇다 |
| **템플릿** | 계정 객체를 통째로 템플릿에 넘기지 마라. Pydantic 모델(`alias`/`customer_id` 만)로 통과시켜라 |
| **jobs DB** | argv 를 저장할 때 `--only-ads <경로>` 는 괜찮지만, 혹시라도 시크릿이 argv 에 들어가는 설계를 만들지 마라 |

> Phase 1 은 **불사자 토큰을 아예 안 탄다** (CONTEXT `<deferred>` ENG-08 → Phase 3). SAFE-03 의 "불사자 토큰" 부분은 이 단계에서 "웹앱이 불사자 자격증명을 로드하지 않는다"로 충족된다. 그렇게 명시해라.

---

## 5. 작업 엔진의 구체 형태 (전부 이 맥북에서 실측)

### 5.1 🔴 `PYTHONUNBUFFERED=1` — 없으면 ENG-03 이 조용히 깨진다 [VERIFIED: 실측]

```
기본:                0.5초 시점 로그파일 크기 = 0B,  종료 후 = 21B
PYTHONUNBUFFERED=1:  0.5초 시점 로그파일 크기 = 14B, 종료 후 = 21B
```
자식 stdout 이 파이프/파일이면 Python 은 블록 버퍼링(기본 8KB)을 쓴다. CLI 는 `flush=True` 를 거의 안 쓴다(`prune.py:115` 하나뿐). → **10분짜리 `prep` 의 로그가 10분 내내 빈 화면이다가 마지막에 한꺼번에 떨어진다.**

**반드시:** `env={**os.environ, "PYTHONUNBUFFERED": "1"}` (또는 `[python, "-u", script, ...]`). 둘 다 넣어도 무해하다.

### 5.2 🟢 `start_new_session=True` 가 `uvicorn --reload` 를 견딘다 [VERIFIED: 실측]

실험 1 — 프로세스 그룹 시그널:
```
parent pgid 6442 | 같은세션 자식 pgid 6442 | start_new_session 자식 pgid 6444
→ os.killpg(부모그룹, SIGTERM) 후 생존: pgid 6444 자식만
```
실험 2 — 진짜 `uvicorn --reload`:
```
/spawn → pid=6890 pgid=6890 server_pgid=6871
touch reload_app.py → "WatchFiles detected changes… Reloading" → "Started server process [6896]"
→ 자식 6890 살아있음(STAT=SNs), tick 계속 증가
```
→ **ENG-02 의 절반("브라우저를 닫아도" 는 물론이고 "서버가 리로드돼도")이 이 한 인자로 성립한다.**

부수효과: 자식이 서버와 분리되므로 **서버가 죽어도 자식이 계속 돈다.** 이건 Phase 2 의 고아 작업 정리(ENG-05)가 필요한 이유이고, Phase 1 에서는 최소한 **jobs 테이블에 `pid` 와 `started_at` 을 남겨야** Phase 2 가 끼워 넣을 수 있다 (CONTEXT `<deferred>` 요구).

### 5.3 로그파일 append-only + 오프셋 (ENG-03)

```python
log_path = job_dir / f"{job_id}.log"
fh = open(log_path, "ab", buffering=0)        # append-only, 버퍼 없음
proc = subprocess.Popen(
    argv,
    cwd=REPO,                                  # run_ads.py 의 lib/eroomlib 탐색이 여기 의존
    env={**os.environ, "PYTHONUNBUFFERED": "1"},
    stdout=fh, stderr=subprocess.STDOUT,       # stderr 를 같은 파일로 합친다
    stdin=subprocess.DEVNULL,                  # 자식이 입력을 기다리며 영원히 멈추지 않게
    start_new_session=True,
    close_fds=True,
)
```

실측 로그 크기: `bids` dry-run 4계정 = **53줄 / 4,551바이트**. `prep` 도 계정당 ~35줄(구매완료 리포트 30일치 실패 줄 포함)이라 6계정이어도 **20KB 미만**이다.

### 5.4 🔴 SSE 재개 — `Last-Event-ID` 에 의존하지 마라

**발견:** htmx-ext-sse 2.2.4 의 재연결은 지수 백오프로 **`htmx.createEventSource(url)` 를 새로 호출한다** → 이전 `EventSource` 의 last event ID 상태가 **버려진다.** [CITED: github.com/bigskysoftware/htmx-extensions/blob/main/src/sse/sse.js]
sse-starlette 도 `Last-Event-ID` 를 **읽지 않는다** — 읽으려면 앱이 직접 `request.headers.get("last-event-id")` 해야 한다. 실측:
```
$ curl -sN -H "Last-Event-ID: 2" http://127.0.0.1:8765/sse
id: 1
event: log
data: last-event-id='2'     ← 헤더는 도착한다. 다만 자동 처리는 없다
```

**그래서 권장 설계 — 매 접속마다 전량 재생:**

```python
@app.get("/jobs/{job_id}/stream")
async def stream(job_id: str, request: Request):
    """접속할 때마다 로그 전량을 먼저 흘리고 그 뒤를 tail 한다.

    Last-Event-ID 로 오프셋을 이어받는 설계는 htmx-ext-sse 가 재연결 시 EventSource 를
    새로 만들어 버려서 성립하지 않는다. 로그가 20KB 미만이라 전량 재생이 더 단순하고
    더 정확하다 — '탭을 닫았다 열어도 처음부터' 라는 요구와도 글자 그대로 맞는다.
    """
    path = log_path_of(job_id)

    async def gen():
        off = 0
        while True:
            if await request.is_disconnected():
                break
            chunk, off = read_from(path, off)          # 오프셋부터 바이트 읽기
            if chunk:
                yield ServerSentEvent(
                    data=html_escape(chunk), event="log", id=str(off))
            if job_finished(job_id) and not chunk:
                yield ServerSentEvent(data=job_summary_html(job_id), event="done")
                break
            await anyio.sleep(0.4)

    return EventSourceResponse(gen(), ping=15, send_timeout=30,
                               headers={"Cache-Control": "no-cache"})
```

**실측 시그니처 (sse-starlette 3.4.11, 이 맥북 설치본):**
```python
EventSourceResponse(content, status_code=200, headers=None, media_type='text/event-stream',
                    background=None, ping=None, sep=None, ping_message_factory=None,
                    data_sender_callable=None, send_timeout=None,
                    client_close_handler_callable=None, shutdown_event=None,
                    shutdown_grace_period=0)
ServerSentEvent(data=None, *, event=None, id=None, retry=None, comment=None, sep=None)
```
`starlette.responses` 에 SSE 클래스는 **없다** (실측: `[n for n in dir(R) if 'vent' in n] == []`) → sse-starlette 가 필요하다는 STACK.md 근거 재확인.

**htmx 쪽 — swap 모드가 중요하다:**
```html
<div hx-ext="sse" sse-connect="/jobs/{{ job_id }}/stream">
  <pre id="joblog" sse-swap="log"></pre>        <!-- 기본 innerHTML = 전량 교체 -->
  <div sse-swap="done" sse-close="done"></div>
</div>
```
`sse-swap` 의 기본 swap 은 `innerHTML`(전량 교체)이다. **`hx-swap="beforeend"` 를 쓰면 재연결 때 로그가 두 번 찍힌다.** 전량 재생 설계에서는 기본값(교체)을 그대로 써라.
전송 페이로드를 줄이고 싶으면 서버가 "전체 로그 HTML" 을 매번 보내되 변경이 없으면 이벤트를 안 보내면 된다 — 20KB 를 초당 2.5회 보내도 로컬에선 무의미한 비용이다.

**대안(후퇴 경로):** SSE 구현이 막히면 `GET /jobs/{id}/log` 를 htmx `hx-trigger="every 2s"` 로 폴링해라. 20줄이고 로컬 1인에선 실질 차이가 없다 (STACK.md 가 이미 허용한 후퇴).

### 5.5 작업 생성은 호출 가능한 함수 (D-17 / ENG-07)

```python
# jobs.py — HTTP 를 모른다. APScheduler 가 v2 에서 이걸 그대로 부른다.
def create_job(kind: JobKind, *, run_dir: str, accounts: list[str] | None = None,
               only_ads: list[str] | None = None, commit: bool = False,
               parent_job_id: str | None = None) -> str:
    """작업을 만들고 자식을 띄운 뒤 job_id 를 돌려준다.

    kind: prep | run | bids_preview | bids_commit | revert_only | revert_all
    only_ads 가 있으면 targets 파일로 먼저 떨군 뒤 argv 에 --only-ads 로 태운다 (FLOW-02).
    """
```
HTTP 핸들러는 딱 이만큼:
```python
@app.post("/jobs/bids/preview")
def post_bids_preview(req: BidsPreviewReq):        # def → Starlette 이 스레드풀에서 돌린다
    return {"job_id": create_job("bids_preview", run_dir=req.run_dir, only_ads=req.ad_ids)}
```

**argv 조립은 Pydantic 모델 한 곳에서** (STACK.md "타입 안전성 완화"):
```python
class AdsArgv(BaseModel):
    subcommand: Literal["prep","run","bids","accounts"]
    run_dir: str | None = None
    accounts: list[str] = []
    commit: bool = False
    revert: bool = False
    only_ads: Path | None = None
    preview_out: Path | None = None
    def build(self) -> list[str]:
        av = [str(PY_CLI), str(RUN_ADS), self.subcommand]
        if self.run_dir:    av += ["--run-dir", self.run_dir]
        if self.accounts:   av += ["--account", *self.accounts]   # 빈 리스트면 붙이지 마라
        if self.commit:     av += ["--commit"]
        if self.revert:     av += ["--revert"]
        if self.only_ads:   av += ["--only-ads", str(self.only_ads)]
        if self.preview_out:av += ["--preview-out", str(self.preview_out)]
        return av
```
`PY_CLI = REPO/".venv/bin/python3"` — **웹앱의 `.venv-web` 이 아니라 CLI 의 `.venv` 다.** 섞이면 CLI 가 selenium/openpyxl 을 못 찾는다.

### 5.6 왜 import 가 아니라 subprocess 인지 — 이번 세션에서 실제로 재현됨 [VERIFIED: 사고]

`run_ads.py:22` 가 `sys.path.insert(0, scripts_dir)` 후 `import ads_rules, bids, collect, nvad, prune, report_md, sheets_out` 을 한다 — **전부 네임스페이스 없는 최상위 이름**이다.
이번 리서치 중 스크래치패드에 `inspect.py` 라는 파일을 두고 그 디렉터리에서 `python -c` 를 돌렸더니 `anyio` 가 죽었다:
```
AttributeError: module 'inspect' has no attribute 'getsource'
```
stdlib `inspect` 가 가려진 것이다. `bids`·`collect`·`reports` 같은 이름이 웹앱 프로세스에 들어오면 같은 종류의 사고가 난다. **ENG-01 은 이론이 아니라 실측된 위험이다.**

### 5.7 SQLite 잡 레지스트리 — 구체 형태

```sql
PRAGMA journal_mode = WAL;    -- 읽기(SSE 상태 폴링)와 쓰기가 겹친다

CREATE TABLE IF NOT EXISTS jobs (
  id            TEXT PRIMARY KEY,          -- uuid4
  kind          TEXT NOT NULL,             -- prep|run|bids_preview|bids_commit|revert_only|revert_all
  run_dir       TEXT NOT NULL,
  accounts      TEXT,                      -- JSON 배열
  argv          TEXT NOT NULL,             -- JSON 배열 (재현·감사용. 시크릿 없음)
  pid           INTEGER,                   -- ENG-05(Phase 2) 고아 감지용
  status        TEXT NOT NULL,             -- running|done|failed|orphaned
  exit_code     INTEGER,
  log_path      TEXT NOT NULL,
  targets_path  TEXT,                      -- --only-ads 로 넘긴 파일 (FLOW-02 의 '그 파일')
  result_path   TEXT,                      -- --preview-out 산출물
  parent_job_id TEXT,                      -- 미리보기 → 실행 → 되돌리기 사슬 (D-11)
  target_count  INTEGER,
  started_at    TEXT NOT NULL,
  ended_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_parent ON jobs(parent_job_id);
```

- **`board_cache` 테이블은 Phase 1 에 만들지 마라.** 보드는 `result.json` 을 읽어 그때 투영하면 된다(547KB 파싱 ≈ 수십 ms). 캐시는 최적화이고, 지금 넣으면 "진실이 둘" 위험만 늘린다.
- **`job_locks` 는 Phase 2(ENG-04).** 다만 §Pitfall 3 의 이유로 Phase 1 에도 **최소 가드 하나**는 필요하다.
- 커넥션: 작업마다 새로 열고 `timeout=5`. FastAPI 핸들러를 `async def` 가 아니라 **`def` 로 선언**하면 Starlette 이 스레드풀에서 돌려 이벤트 루프를 막지 않는다. [CITED: fastapi.tiangolo.com/async/ — "When you declare a path operation function with normal `def` instead of `async def`, it is run in an external threadpool"]
  → **SSE 엔드포인트만 `async def`, 나머지는 전부 `def`.**

### 5.8 `caffeinate -i` (ENG-06 — Phase 2 지만 형태만 기록)

`man caffeinate` (이 맥북) 확인:
> `-i` Create an assertion to prevent the system from idle sleeping.
> If a utility is specified, caffeinate creates the assertions on the utility's behalf, and those assertions will persist for the duration of the utility's execution.

→ `argv = ["/usr/bin/caffeinate", "-i", str(PY_CLI), str(RUN_ADS), ...]`. 자식이 끝나면 assertion 이 자동으로 풀린다.
→ **Phase 1 에서 argv 조립기(`AdsArgv.build`)가 맨 앞에 프리픽스를 끼울 수 있는 모양이면 Phase 2 가 한 줄로 끝난다.** 지금 그 모양으로 만들어라.

---

## 6. Walking Skeleton — 후보와 근거

이 단계는 MVP 모드 + 선행 phase 0 → 가장 얇은 end-to-end 한 줄을 먼저 세워야 한다.

### 6.1 후보 비교 (전부 실측 기반)

| 후보 | 소요 | 광고 API | 프레임 커버리지 | 판정 |
|---|---|---|---|---|
| 보드만 (`result.json` → Tabulator) | ms | 없음 | 보안 3종 GET 만. **작업 엔진 0** | ❌ 너무 얇다. 틀을 안 건드린다 |
| **`bids` dry-run 미리보기 버튼** | **0.066초** | **없음** | 보안 3종(쓰기 포함) · `create_job` · subprocess · 로그파일 · SSE · 종료 감지 · `--preview-out` 읽어 표시. **`--only-ads`/`--preview-out` 패치까지 강제** | ✅ **1차 스켈레톤** |
| `run` (판정) 버튼 | 초 | 없음 | 위와 같으나 CLI 패치를 강제하지 않는다 | 🟡 대안 |
| `prep --account cy728` | **~3분** | GET + `POST /stat-reports` (광고 불변) | 위 전부 + **"탭 닫았다 이어보기"** | ✅ **2차 스켈레톤** |
| `prep` 전 계정 | ~12~15분 | 위와 같음 | 위와 같음 | 🟡 2차의 확장. 개발 루프엔 너무 느리다 |
| `bids --commit` | 100초/1,200건 | **PUT — 진짜 쓰기** | 전부 | ❌ 스켈레톤이 아니다. 틀이 굳은 뒤 |

### 6.2 권고 — 2단 스켈레톤

**Skeleton A — 프레임 (0.07초 피드백 루프)**
> 브라우저에서 **한 상품 줄을 골라 "입찰가 인상 미리보기"** 를 누르면
> `create_job("bids_preview", only_ads=[adId…])` → targets 파일 기록 → `subprocess` → 로그가 SSE 로 흐르고 → `--preview-out` 을 읽어 `70 → 80` 표가 뜬다.

이 한 줄이 통과하면 다음이 전부 증명된다: 보안 3종(쓰기 메서드 + 토큰 + Origin) · D-17 함수 경계 · ENG-01 subprocess · ENG-03 로그파일 · SSE 배선 · D-01/D-02 CLI 패치 · FLOW-02 대상 파일 단일화 · BID-02/BID-03 미리보기. **광고 API 를 한 번도 안 부르고, 크레딧도 광고비도 0이다.**

**Skeleton B — 지속시간 (3분)**
> 같은 엔진으로 **"새로 수집(`prep --account cy728`)"** 을 돌리고, 중간에 **탭을 닫았다 다시 열어** 로그가 처음부터 이어 보이는지 확인한다 (ENG-02 · Success Criteria 3).

A 가 너무 빨라서(0.07초) "이어보기"를 증명할 수 없기 때문에 B 가 **반드시 따라붙어야** 한다. D-15 가 `prep` 을 여기 끌어들인 이유가 정확히 이것이다.

**정직한 단서:** `prep` 은 `POST /stat-reports` 로 리포트 잡을 만든다. 광고(소재/입찰가/예산)를 바꾸지는 않지만 "HTTP POST 가 0" 은 아니다. SKILL.md 의 "광고 API 에 아무것도 쓰지 않는다" 는 **광고 자체를 안 바꾼다**는 뜻으로 읽어야 정확하다. [VERIFIED: `reports._build_and_download:49`]

**Skeleton C — 자동화용 합성 잡 (Validation Architecture 의 핵심)**
`prep` 3분을 CI 에서 돌릴 수는 없다. **같은 `create_job` 함수를 타는 5초짜리 합성 잡**(`python3 -u -c "…print+sleep…"`)을 테스트 픽스처로 하나 두면, SSE 재접속·로그 전량 재생·종료 감지·고아 pid 를 **네트워크 0 · 결정적**으로 검증할 수 있다. 이게 없으면 Success Criteria 3 은 영원히 수동 확인으로 남는다.

---

## Standard Stack

> CLAUDE.md 에서 **이미 확정**됐다. 아래는 **이 맥북에서 실제로 설치해 시그니처까지 확인한 검증 기록**이다 (`/private/tmp/.../scratchpad/.venv-probe`).

### Core

| Library | Version | 확인 방법 | 상태 |
|---|---|---|---|
| Python | 3.12.13 | `.venv/bin/python3 --version` | ✅ 기존 CLI venv 와 동일 메이저 |
| FastAPI | **0.141.1** (2026-07-29) | PyPI JSON + 설치 후 `fastapi.__version__` | ✅ `requires_python >=3.10` |
| Starlette | **1.6.0** (2026-08-08) | fastapi 가 끌고 옴. `starlette.__version__` | ✅ **직접 pin 하지 마라** |
| Pydantic | **2.13.5** (2026-08-28) | fastapi 가 끌고 옴 | ✅ |
| Uvicorn | **0.53.0** (2026-09-14) | PyPI + 설치 | ✅ `--workers 1` 고정 |
| Jinja2 | **3.1.6** (2025-03-05) | PyPI + 설치 | ✅ |
| sse-starlette | **3.4.11** (2026-09-05) | PyPI + 설치 + 시그니처 추출 | ✅ `starlette.responses` 에 SSE 없음을 재확인 |
| sqlite3 | stdlib (라이브러리 3.53.1) | `sqlite3.sqlite_version` | ✅ 시스템 CLI 는 3.51.0 |
| anyio | 4.15.1 | fastapi 의존 | ✅ `anyio.sleep`/`to_thread` 를 그대로 쓸 수 있다 |

**설치 확인 명령 (실제로 통과했다):**
```bash
uv venv .venv-web --python 3.12
uv pip install --python .venv-web/bin/python \
  "fastapi==0.141.1" "uvicorn[standard]==0.53.0" "jinja2==3.1.6" "sse-starlette==3.4.11"
```

### Frontend (npm dist-tags 실측 2026-09-19)

| 패키지 | 버전 | dist-tags 실측 | 배포일 |
|---|---|---|---|
| htmx.org | **2.0.10** | `{latest: 2.0.10, next: 4.0.0}` | 2026-04-21 |
| htmx-ext-sse | **2.2.4** | `{latest: 2.2.4}` | 2025-10-18 |
| tabulator-tables | **6.5.3** | `{latest: 6.5.3, alpha: 5.0.0-alpha.0}` | 2026-09-15 |
| @picocss/pico | **2.1.1** | `{latest: 2.1.1, next: 2.1.1}` | 2025-03-15 |

→ CLAUDE.md 의 "htmx 4.0.0 을 `latest` 로 안 옮겼다" 가 **레지스트리에서 그대로 확인된다.**

**권고 — CDN 대신 로컬 vendoring:**
```
webapp/static/vendor/{htmx.min.js, sse.js, tabulator.min.js, tabulator.min.css, pico.min.css}
```
이유 3개: ① 1인 로컬 도구가 인터넷 없으면 화면이 안 뜨는 건 말이 안 된다 ② 부팅 토큰이 심긴 페이지에 서드파티 스크립트를 매번 불러오는 건 불필요한 공급망 노출이다 ③ 버전이 파일로 고정돼 "어느 날 갑자기 다르게 동작" 이 사라진다.
CDN 을 고집한다면 **SRI 필수**. htmx-ext-sse 2.2.4 의 공식 integrity:
```html
<script src="https://cdn.jsdelivr.net/npm/htmx-ext-sse@2.2.4"
        integrity="sha384-A986SAtodyH8eg8x8irJnYUk7i9inVQqYigD6qZ9evobksGNIXfeFvDwLSHcp31N"
        crossorigin="anonymous"></script>
```
[CITED: htmx.org/extensions/sse/]

### Supporting (Phase 1 에 추가로 켤 것)

| 항목 | 이유 |
|---|---|
| `starlette.middleware.gzip.GZipMiddleware(minimum_size=1000)` | 보드 547KB → **95KB** (실측). 안 켜면 체감된다 |
| `fastapi.staticfiles.StaticFiles` | vendoring 한 JS/CSS 서빙 |
| `fastapi.templating.Jinja2Templates` | 서버 렌더 |
| stdlib `tomllib` | `workspace.toml` 에서 `data_root` (§3.3). 외부 의존 0 |
| stdlib `secrets` | 부팅 토큰 + `compare_digest` |

**Phase 1 에 넣지 마라:** APScheduler(v2) · Alpine.js(필요해지면) · httpx(테스트에 `TestClient` 가 이미 끌고 온다) · SQLAlchemy/Alembic.

---

## Package Legitimacy Audit

slopcheck 실행 (probe venv, 2026-09-19):

| Package | Registry | 다운로드/성숙도 | Source Repo | slopcheck | Disposition |
|---|---|---|---|---|---|
| fastapi | PyPI | 대규모, 2018~ | github.com/fastapi/fastapi | **[OK]** | Approved |
| uvicorn | PyPI | 대규모, 2017~ | github.com/encode/uvicorn | **[OK]** | Approved |
| jinja2 | PyPI | 대규모, 2008~ | github.com/pallets/jinja | **[OK]** | Approved |
| sse-starlette | PyPI | 중규모, 2020~ | github.com/sysid/sse-starlette | **[OK]** | Approved |
| starlette | PyPI | fastapi 전이 의존 | github.com/encode/starlette | (전이) | Approved |
| pydantic | PyPI | fastapi 전이 의존 | github.com/pydantic/pydantic | (전이) | Approved |
| htmx.org | npm | dist-tags 확인됨 | github.com/bigskysoftware/htmx | **[OK]** | Approved |
| htmx-ext-sse | npm | dist-tags 확인됨 | github.com/bigskysoftware/htmx-extensions | **[OK]** | Approved |
| tabulator-tables | npm | dist-tags 확인됨 | github.com/olifolkerd/tabulator | **[OK]** | Approved |
| @picocss/pico | npm | dist-tags 확인됨 | github.com/picocss/pico | **[OK]** | Approved |

```
slopcheck install fastapi uvicorn jinja2 sse-starlette      → scanned 5 packages, 5 OK
slopcheck install -e npm htmx.org htmx-ext-sse tabulator-tables @picocss/pico → scanned 4 packages, 4 OK
```

**[SLOP] 판정으로 제거된 패키지:** 없음
**[SUS] 로 플래그된 패키지:** 없음

> ⚠ 리서치 중 `slopcheck install -e npm …` 이 실제로 `npm install` 까지 실행해 저장소 루트에 `node_modules/`·`package.json`·`package-lock.json` 을 만들었다. **즉시 삭제했고 `git status` 로 워킹트리가 깨끗함을 확인했다.** executor 가 이 도구를 쓸 일이 있으면 `--dry-run` 성격의 `slopcheck scan --pkg <name>` 을 써라. 그리고 **이 프로젝트는 npm 을 쓰지 않는다** — vendoring 은 `curl` 로 파일만 받아라.

---

## Architecture Patterns

### System Architecture Diagram

```
 [브라우저 · 127.0.0.1:8765]
   │  (1) GET /?t=<boot token>  ── 최초 1회, 기동 로그의 URL
   │  (2) 303 → 쿠키 심고 깨끗한 /
   ▼
┌──────────────────────────────────────────────── uvicorn --workers 1 ───┐
│  TrustedHostMiddleware(allowed_hosts=["127.0.0.1","localhost"])         │ ← Host 400
│  GZipMiddleware(minimum_size=1000)                                      │
│  guard(): 쓰기 메서드만 → Origin 검사 → X-CT-Token 검사                  │ ← 403
│                                                                         │
│   GET /                  ──► 보드 렌더                                   │
│      └─ result.json 읽기 ──► (alias, mallProductId) 접기 ──► 상품 2,637행 │
│         run-dir 스캔     ──► 신선도 배너 (회차 · 경과일 · 통계기간)       │
│                                                                         │
│   POST /jobs/bids/preview ─┐                                            │
│   POST /jobs/bids/commit   │                                            │
│   POST /jobs/revert/job    ├─► create_job(kind, run_dir, only_ads, …)   │ ← D-17
│   POST /jobs/revert/round  │      │  ENG-07: HTTP 를 모르는 순수 함수     │
│   POST /jobs/prep          │      │  (v2 에서 APScheduler 가 같은 걸 부른다)│
│   POST /jobs/run          ─┘      │                                     │
│                                   ├─► targets.json 기록 (FLOW-02 의 '그 파일')│
│                                   ├─► jobs 테이블 INSERT (SQLite WAL)    │
│                                   └─► subprocess.Popen                  │
│                                          PYTHONUNBUFFERED=1  ← ENG-03    │
│                                          start_new_session=True ← ENG-02 │
│                                          stdout+stderr → <job>.log (ab) │
│                                                                         │
│   GET /jobs/{id}/stream (async def)                                     │
│      └─ 로그 전량 재생 → 오프셋 tail → EventSourceResponse(ping=15)      │
│         ※ Last-Event-ID 에 의존하지 않는다 (htmx 가 EventSource 를 새로 만듦)│
│   GET /jobs/{id}/result ──► --preview-out JSON 읽어 항목단위 표 (FLOW-05) │
└─────────────────────────────────────────────────────────────────────────┘
                     │ argv: .venv/bin/python3 run_ads.py <sub> …
                     ▼
┌──────────────── CLI 서브프로세스 (자격증명 소지자) ─────────────────────┐
│  run_ads.py  ──► bids.run_bids / run_revert / collect / ads_rules       │
│     읽기: ~/.eroom/naver-ads.json (600)  ← 웹앱은 시크릿을 안 쥔다       │
│     쓰기: run-dir/{result.json, before_bids_*.json, preview/result JSON} │
│           ledger/<alias>.json  ← run-dir 바깥, 회차 누적                 │
│     네트워크: api.searchad.naver.com  (bids --commit 일 때만 PUT)        │
└─────────────────────────────────────────────────────────────────────────┘
                     │
                     ▼ (다음 접속 때 웹앱이 읽기만 한다)
        ~/python_work/data/naver-ads/runs/<회차>/result.json  ← 보드의 유일한 진실
```

### Recommended Project Structure

```
webapp/                          # 새 최상위 디렉터리 (.claude/skills 를 건드리지 않는다)
├── main.py                      # FastAPI 앱 조립 + 미들웨어 3층 + 라우터 등록
├── settings.py                  # 포트·상한(D-08 1500)·경로 — 설정파일에서 읽는다
├── security.py                  # 부팅토큰 · Origin 가드 · 시크릿 스크러버
├── paths.py                     # data_root() · run_dir 스캔 · 신선도 계산 (tomllib)
├── argv.py                      # AdsArgv Pydantic 모델 — argv 조립의 유일한 곳
├── jobs.py                      # create_job() · SQLite 스키마 · Popen · 상태 조회 (ENG-07)
├── logtail.py                   # 오프셋 읽기 · SSE 제너레이터
├── board.py                     # result.json → 상품 단위 투영 (읽기 전용)
├── routes/
│   ├── board.py                 # GET /
│   ├── jobs.py                  # POST /jobs/* · GET /jobs/{id}/stream · /result
│   └── health.py
├── templates/                   # board.html · _job_panel.html · _preview_table.html
├── static/vendor/               # htmx · sse ext · tabulator · pico (vendoring)
└── tests/
    ├── test_security.py         # curl 6케이스의 TestClient 판
    ├── test_jobs.py             # 합성 잡으로 subprocess/로그/SSE
    ├── test_board.py            # result.json 픽스처 → 접기 결과
    └── fixtures/                # result.json 축소본 · targets.json
webapp.db                        # jobs SQLite (gitignore)
webapp-logs/<job_id>.log         # append-only (gitignore)
```

> **CLI 패치는 원위치에서 한다.** `.claude/skills/naver-ads-weekly/scripts/{run_ads.py,bids.py}` 를 직접 고치고, 같은 커밋에 기존 테스트 100개 통과를 남겨라. 복사본을 만들면 진실이 둘이 된다.

### Pattern 1: 3단 계약을 파일로 잇기 (FLOW-01 / FLOW-02 / D-11)

```
[판정]   run-dir/result.json                      ← CLI 가 이미 만들어 둔 것
   ↓  사용자가 상품 줄 선택 → 그 상품의 ①행 adId 만 (D-06)
[대상]   run-dir/web/targets_<job>.json           ← 웹앱이 딱 한 번 쓴다
   ↓  --only-ads targets_<job>.json
[미리보기] run-dir/web/preview_<job>.json          ← CLI 가 --preview-out 으로 쓴다
   ↓  같은 targets 파일을 재사용 (D-11: 화면 상태에서 다시 만들지 않는다)
[실행]   run-dir/web/result_<job>.json            ← CLI 가 --preview-out 으로 쓴다
   ↓  result 에서 p["result"]=="성공" 인 adId 만 추려 새 targets 파일
[되돌리기] run-dir/web/targets_revert_<job>.json   ← --only-ads + --revert (D-13)
```
`jobs.parent_job_id` 로 이 사슬을 잇는다. 화면의 "되돌리기" 버튼은 `job_id` 하나만 알면 된다.

### Pattern 2: 상품 단위 접기 (D-05)

```python
def fold_products(result: dict) -> list[dict]:
    """소재 행을 (계정, mallProductId) 로 접는다. 판정값을 새로 만들지 않는다 — 모으기만."""
    prod: dict[tuple, dict] = {}
    for alias, v in result.get("accounts", {}).items():
        for rule, rows in v.get("rules", {}).items():
            for r in rows:
                key = (alias, r.get("mallProductId"))
                p = prod.setdefault(key, {
                    "acct": alias, "mallProductId": r.get("mallProductId"),
                    "title": r.get("title"), "rules": set(),
                    "rule1_ads": [],          # ← 버튼이 적용될 소재 (D-06)
                    "imp": None, "clk": None, "purCnt": None, "purAmt": None,
                })
                p["rules"].add(rule[0])                       # '①'~'⑥'
                if rule.startswith("①"):
                    p["rule1_ads"].append(r["adId"])
                # ①·⑥ 행에는 imp/clk/ctr 가 아예 없다 — .get() 으로만 만져라
                for f in ("imp", "clk", "purCnt", "purAmt"):
                    if r.get(f) is not None:
                        p[f] = (p[f] or 0) + r[f]
    out = []
    for p in prod.values():
        p["rules"] = "".join(sorted(p["rules"]))
        p["rule1_count"] = len(p["rule1_ads"])                # "이 버튼이 N건에 적용됩니다"
        out.append(p)
    return out
```

### Anti-Patterns to Avoid

- **`row.imp` 를 무조건 읽기** — ①+⑥ **2,274행**에 그 필드가 없다. `.get()` / Tabulator formatter 로 명시 처리.
- **웹앱이 `bid + 10` 을 계산** — 92%가 그룹입찰이라 거의 전량이 틀린다 (§2.5).
- **"되돌리기" → `--revert` 직결** — 지금 백업에 2,242건이 들어 있다 (§1.6).
- **`--only-ads` 읽기 실패 시 전량 폴백** — 5건인 줄 알았던 게 2,242건이 된다.
- **`hx-swap="beforeend"` 로 SSE 로그 붙이기** — 재연결 때 중복.
- **상태를 바꾸는 GET 엔드포인트** — Origin 방어가 통째로 무력화된다 (§4.3).
- **`async def` 핸들러에서 sqlite/파일 blocking IO** — 이벤트 루프를 막는다. SSE 외엔 전부 `def`.
- **`--account` 를 값 없이 붙이기** — `[]` → falsy → **전 계정**이 된다 (§1.1).
- **`.venv-web/bin/python` 으로 CLI 실행** — CLI 는 `.venv/bin/python3` 다.

---

## Don't Hand-Roll

| 문제 | 직접 만들지 마라 | 대신 | 이유 |
|---|---|---|---|
| Host 헤더 검증 | 직접 파싱 | `TrustedHostMiddleware` | 포트 분리·websocket scope·www 리다이렉트를 이미 처리 (소스 확인) |
| SSE 프레이밍·keepalive·끊김 감지 | 수동 `yield f"data: …"` | `sse-starlette` `EventSourceResponse` | `starlette.responses` 에 SSE 가 **없음을 실측 확인**. ping·send_timeout·`http.disconnect` 리스닝이 전부 들어 있다 |
| 테이블 정렬/필터/다중선택/검색 | 직접 JS | Tabulator 6.5.3 | 2,637행 가상 DOM·다중 필터·행 선택 내장 |
| 토큰 비교 | `==` | `secrets.compare_digest` | 타이밍 공격. 비용 0 |
| 랜덤 토큰 | `random`/`uuid4` | `secrets.token_urlsafe(32)` | CSPRNG |
| 작업 내구성·재개 | 브로커/큐 | CLI 의 run-dir 체크포인트 + SQLite jobs 테이블 | 진실이 둘이 되는 순간 크레딧 이중 지불 (STACK.md §핵심결정 2) |
| 입찰가 산정·쿨다운·상한·연속실패 | 재구현 | `ledger.bid_decision` (CLI) | 검증된 가드 4개. 재구현은 PROJECT.md 제약 위반 |
| 백업 병합 규칙 | 재구현 | `bids.run_bids` 의 Important 1 | "같은 키는 먼저 것 유지" — 틀리면 원본이 영영 사라진다 |
| TOML 파싱 | 정규식 | stdlib `tomllib` (3.11+) | 외부 의존 0 |
| 응답 압축 | 수동 gzip | `GZipMiddleware` | 547KB → 95KB |

**핵심 통찰:** 이 단계에서 "직접 만들지 마라"의 압도적 다수는 **라이브러리가 아니라 기존 CLI** 다. 웹앱이 새로 짜야 하는 건 작업 엔진(≈150줄) · 보안 3층(≈40줄) · 보드 투영(≈60줄) 정도다.

---

## Common Pitfalls

### Pitfall 1: 진행 로그가 10분 동안 빈 화면 (블록 버퍼링)
**무엇이 잘못되나:** `prep` 을 눌렀는데 SSE 가 아무것도 안 뿜다가 끝날 때 한 번에 쏟아진다. "SSE 가 안 된다"로 오진하기 딱 좋다.
**왜:** `print()` → 파일/파이프 = 블록 버퍼링. CLI 에 `flush=True` 가 1줄뿐.
**막는 법:** `env={**os.environ, "PYTHONUNBUFFERED":"1"}` + `[python, "-u", ...]`.
**조기 신호:** `wc -c <job>.log` 가 작업 중 내내 0.
**검증:** §Validation V-ENG-03.

### Pitfall 2: 되돌리기가 회차 전체를 푼다
**무엇이 잘못되나:** 5건 올리고 "되돌리기"를 눌렀는데 2,242건이 풀린다.
**왜:** `before_bids_<alias>.json` 이 회차 안에서 **누적 병합**된다. 지금 디스크에 실제로 2,242건이 들어 있다.
**막는 법:** D-13 — jobs DB 의 "이번에 성공한 adId" 를 `--only-ads` 로 넘긴다. 백업 파일은 읽기만.
**조기 신호:** revert dry-run 의 `targets` 수가 방금 실행한 건수보다 크다. **웹앱이 이걸 실행 전에 비교해서 막아라.**

### Pitfall 3: 🔴 동시 실행이 백업과 ledger 를 깨뜨린다 (ENG-04 는 Phase 2 인데 위험은 Phase 1)
**무엇이 잘못되나:** 쓰기 잡 두 개가 같은 run-dir 에서 겹치면 `before_bids_<alias>.json` 과 `ledger/<alias>.json` 이 **read-modify-write 레이스**로 서로를 덮는다. 백업 항목이 사라지면 그 소재는 영영 되돌릴 수 없다.
**왜:** `run_bids` 는 파일을 읽고 → 병합하고 → 통째로 다시 쓴다(bids.py:182-193). 락이 없다.
**막는 법 (Phase 1 최소 가드, ENG-04 전체가 아니라 한 줄):**
```sql
-- 쓰기 잡은 전역 1개만. Phase 2 가 이걸 대상별 락으로 넓힌다.
SELECT COUNT(*) FROM jobs WHERE status='running' AND kind IN ('bids_commit','revert_only','revert_all','prep');
-- > 0 이면 409 "이미 도는 작업이 있다"
```
미리보기(`bids_preview`)·판정(`run`)은 쓰기가 없으니 이 가드에서 빼도 된다.
**이건 planner 가 반드시 태스크로 넣어야 한다** — CONTEXT 의 deferred 는 ENG-04(대상별 잠금)를 Phase 2 로 미뤘지 "Phase 1 에서 동시 쓰기를 허용하라"가 아니다.

### Pitfall 4: 날짜를 넘긴 되돌리기가 ledger 를 어긋나게 한다
**무엇이 잘못되나:** 월요일 인상 → 화요일 되돌리기 → `reverted` 플래그가 안 찍힘 → 6일 쿨다운 동안 재인상 차단 + streak 누적.
**왜:** `ledger.record_reverted:69` 가 `raises[-1]["date"] == today` 일 때만 플래그를 찍는다.
**막는 법:** Phase 1 은 **고치지 않는다**(로직 변경). 화면에 경고를 띄운다: 되돌리기 버튼 옆에 `인상일 2026-09-19 · 오늘 2026-09-20 → 이력 반영 안 됨` 배너.
**조기 신호:** revert 후 다음 미리보기에서 그 소재가 `최근인상` 으로 뜬다.

### Pitfall 5: `--only-ads` 필터를 `run_bids` 바깥에 걸면 streak 이 조용히 멈춘다
**무엇이 잘못되나:** 5건만 실행했는데 나머지 2,237건의 "3주 연속 실패" 카운팅이 이번 회차에 통째로 빠진다. 게다가 `led["_last_streak_update"]=today` 가 찍혀서 같은 날 도는 전량 CLI 실행도 건너뛴다.
**왜:** `update_streaks(led, {r["adId"] for r in rows}, …)` 가 `rows` 를 곧이곧대로 믿는다.
**막는 법:** §1.3 대로 **`update_streaks` 뒤에** 필터. 위치가 전부다.
**조기 신호:** 회차를 몇 번 돌려도 `ledger/*.json` 의 `streak` 이 전부 0.

### Pitfall 6: 같은 날 두 번째 미리보기가 빈 표를 준다
**무엇이 잘못되나:** 실행 직후 다시 미리보기를 누르면 전부 `최근인상` 이 되어 대상이 0건이다.
**왜:** `RAISE_COOLDOWN_DAYS=6` 이 정상 작동하는 것. 버그가 아니다.
**막는 법:** 미리보기 표에 `action` 별 집계를 **항상** 보여라 — `인상 0 · 최근인상 5`. 빈 표만 띄우면 고장으로 읽힌다. `counts` 가 `run_bids` 리턴에 이미 있다.

### Pitfall 7: 3주 묵은 판정으로 입찰가를 올린다
**무엇이 잘못되나:** 최신 run-dir 이 **2026-08-30, 20일 전**이다. 그 사이 물갈이가 돌아 소재 구성이 바뀌었을 수 있다.
**막는 법:** D-16 신선도 배너 + `prep` 이후 `run` 이 안 돌아간 run-dir 을 보드 목록에서 빼라. 경과일이 임계값(예: 8일)을 넘으면 실행 버튼 옆에 경고색.
**참고:** `run_bids` 는 실시간 재조회를 하지 않고 **prep 시점 `ads.json` 스냅샷**을 읽는다(bids.py:148-150 주석). 소재가 그 사이 삭제됐으면 `ad_by_id.get()` 이 None → `fail += 1`. 스냅샷 기반 실패는 §1.5 의 `"실패"/"스냅샷에 소재 없음"` 으로 사용자에게 보여야 한다.

### Pitfall 8: 보드가 `accounts/*/ads.json` 을 읽는다
**무엇이 잘못되나:** 2.6MB × 2 를 파싱하거나 브라우저로 보낸다.
**막는 법:** 보드는 `result.json` **만** 읽는다. `ads.json` 은 CLI 만의 것이다.

### Pitfall 9: `uvicorn --workers 2` 가 조용히 다 깨뜨린다
**왜:** jobs 상태와 SSE 구독자가 프로세스별로 갈라진다. "가끔 로그가 안 뜬다" 로 나타난다.
**막는 법:** 기동 스크립트·launchd plist·문서에 `--workers 1` 을 못박고, `main.py` 부팅 시 `os.environ.get("WEB_CONCURRENCY")` 가 1 이 아니면 경고 로그를 찍어라.

---

## Code Examples

### 보안 3층 조립 (실측 통과본)
```python
# main.py — 이 배치 그대로 curl 6케이스를 통과했다
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.gzip import GZipMiddleware
import secrets

BOOT_TOKEN = secrets.token_urlsafe(32)
PORT = settings.port                                  # 하드코딩 금지
ALLOWED_ORIGINS = {f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

app = FastAPI(docs_url=None, redoc_url=None)          # 1인 로컬 도구에 OpenAPI UI 는 공격면만 늘린다
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(TrustedHostMiddleware,
                   allowed_hosts=["127.0.0.1", "localhost"], www_redirect=False)

@app.middleware("http")
async def guard(request: Request, call_next):
    """쓰기 메서드만 검사한다. 상태를 바꾸는 GET 을 만들지 않는 것이 이 방어의 전제다."""
    if request.method not in SAFE_METHODS:
        origin = request.headers.get("origin")
        if origin is not None and origin not in ALLOWED_ORIGINS:
            return PlainTextResponse("origin 거부", status_code=403)
        if origin is None and request.headers.get("sec-fetch-site") not in (None, "same-origin"):
            return PlainTextResponse("sec-fetch-site 거부", status_code=403)
        if not secrets.compare_digest(request.headers.get("x-ct-token") or "", BOOT_TOKEN):
            return PlainTextResponse("토큰 거부", status_code=403)
    return await call_next(request)
```
기동:
```bash
.venv-web/bin/python -m uvicorn webapp.main:app --host 127.0.0.1 --port 8765 --workers 1
```

### 자식 띄우기 (ENG-01/02/03 동시 충족)
```python
def spawn(argv: list[str], log_path: Path) -> subprocess.Popen:
    """CLI 를 서브프로세스로 띄운다.

    PYTHONUNBUFFERED: 없으면 진행 로그가 종료 시점까지 안 보인다(실측).
    start_new_session: uvicorn --reload 재시작·서버 종료에서 자식을 살린다(실측).
    stdin=DEVNULL: 자식이 입력을 기다리며 영원히 멈추는 사고를 막는다.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fh = open(log_path, "ab", buffering=0)
    except OSError as e:
        raise RuntimeError(f"로그 파일을 못 연다: {e}") from e
    try:
        return subprocess.Popen(
            argv, cwd=REPO,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
            stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            start_new_session=True, close_fds=True,
        )
    except Exception:
        fh.close()
        raise
```

### 오프셋 tail (ENG-03)
```python
def read_from(path: Path, offset: int) -> tuple[str, int]:
    """오프셋부터 읽고 (텍스트, 새 오프셋) 을 준다. 파일이 아직 없으면 빈 값."""
    try:
        with open(path, "rb") as f:
            f.seek(offset)
            b = f.read()
        # UTF-8 멀티바이트가 잘릴 수 있다 — errors='replace' 로 버티고 다음 회차에 붙는다
        return b.decode("utf-8", errors="replace"), offset + len(b)
    except FileNotFoundError:
        return "", offset
    except Exception:
        return "", offset
```
> 한글 로그라 **멀티바이트 경계 절단이 실제로 난다.** 정확히 하려면 마지막 불완전 바이트를 버퍼에 남기고 오프셋을 그만큼 되돌려라. Phase 1 에선 `errors="replace"` + 0.4초 폴링이면 사실상 안 보인다.

### Tabulator — "보이는 것만" vs "필터 전체" (BOARD-03)
```javascript
// 헤더 체크박스로 고른 것 = 보이는 페이지의 선택분
const visible = table.getSelectedData();
// 현재 필터를 통과한 전체 (정렬·필터 적용, 페이지 무관)
const filtered = table.getData("active");
// D-07: filtered.length > visible.length 이면 배너를 띄워 한 번 더 확인받는다
```

### 미리보기 ↔ 실행 diff (D-10)
```python
def diff_preview(preview: dict, result: dict) -> list[dict]:
    """미리보기와 실행이 어디서 갈라졌는지 사유와 함께 돌려준다.

    D-09 로 실행 시점 재계산을 유지했으므로 갈라지는 건 정상이다 —
    '갈라졌다는 사실' 을 숨기지 않는 게 이 함수의 일이다.
    """
    pv = {p["adId"]: p for al in preview.values() for p in (al.get("plans") or [])}
    out = []
    for al in result.values():
        for r in (al.get("plans") or []):
            p = pv.get(r["adId"])
            if p is None:
                out.append({"adId": r["adId"], "why": "미리보기에 없던 소재"})
            elif (p["action"], p["to"]) != (r["action"], r["to"]):
                out.append({"adId": r["adId"], "why": "재계산으로 바뀜",
                            "before": f'{p["action"]} {p["from"]}→{p["to"]}',
                            "after":  f'{r["action"]} {r["from"]}→{r["to"]}'})
    return out
```

---

## Runtime State Inventory

> 이 단계는 rename/refactor 가 아니라 신규 웹앱 추가다. 그래도 **기존 CLI 의 런타임 상태를 웹앱이 건드릴 수 있어서** 확인했다.

| 범주 | 발견 | 필요한 조치 |
|---|---|---|
| 저장 데이터 | `ledger/<alias>.json` 4개 (ownway1 187KB · pogeunae 161KB) — **회차를 넘어 누적**. `before_bids_<alias>.json` 4개, 합계 2,242건 | **웹앱은 읽지도 쓰지도 않는다.** CLI 만 만진다 (D-13) |
| 라이브 서비스 설정 | 네이버 검색광고 4계정의 실제 입찰가 — **2026-08-30 에 2,242건이 이미 올라가 있고 되돌려지지 않았다** | Phase 1 첫 `--commit` 전에 사용자에게 이 사실을 알려라. 쿨다운 20일 경과라 또 +10 된다 |
| OS 등록 상태 | launchd LaunchAgent **없음** (확인: 이 리포에 plist 없음). tmux/pm2 등록 없음 | Phase 1 은 수동 기동으로 충분. 상시 기동은 별도 결정 |
| 시크릿·환경변수 | `~/.eroom/naver-ads.json` (600, git 밖). `workspace.toml` (gitignore). 웹앱용 신규 시크릿 **없음** | 부팅 토큰은 메모리에만. 파일로 떨구지 마라 |
| 빌드 산출물 | `.venv-web` **아직 없음**. `node_modules` 없음(리서치 중 생긴 것 삭제 완료) | `.gitignore` 에 `.venv-web/` · `webapp.db*` · `webapp-logs/` 추가 |
| 포트 | 8765 를 점유하는 상주 프로세스 **없음** (lsof 확인) | 충돌 없음 |

---

## Environment Availability

| 의존 | 필요한 이유 | 있나 | 버전 | 폴백 |
|---|---|---|---|---|
| Python 3.12 (`.venv`) | CLI 실행 | ✓ | 3.12.13 | — |
| `uv` | `.venv-web` 생성 | ✓ | 0.12.2 | `python -m venv` + pip |
| `sqlite3` (stdlib) | jobs DB | ✓ | lib 3.53.1 / CLI 3.51.0 | — |
| `sqlite3` CLI | 화면 고장 시 직접 조회 | ✓ | /usr/bin/sqlite3 | — |
| `caffeinate` | Phase 2 (ENG-06) | ✓ | /usr/bin/caffeinate (`-i` 확인) | — |
| `curl` | 보안 검증 | ✓ | /usr/bin/curl | — |
| `node` | **안 쓴다** (npm 빌드체인 금지) | ✓ 24 설치됨 | — | 무관 |
| FastAPI/Uvicorn/Jinja2/sse-starlette | 웹앱 | ✗ (미설치) | 설치 테스트 **통과** | 없음 — 설치가 Wave 0 |
| htmx/Tabulator/Pico 정적파일 | UI | ✗ | — | `curl` 로 vendoring |
| `~/.eroom/naver-ads.json` | 광고 API | ✓ | 4계정, 600 | 없음 (블로커) |
| `workspace.toml` | data_root | ✓ | `paths.data_root` 확인 | `~/python_work/data` |
| run-dir `2026-08-30` | 보드 데이터 | ✓ | result.json 879KB, **20일 전** | `prep`+`run` 재실행 |
| `.claude/lib/eroomlib` | CLI 의 `data_root()` | ✓ | 존재 | CLI 자체 폴백 |
| 인터넷 (api.searchad.naver.com) | `prep` · `bids --commit` | 미검증 | — | 없음 |

**폴백 없는 미설치 항목:** 웹앱 파이썬 의존 4종 → Wave 0 의 첫 태스크.
**폴백 있는 미설치 항목:** 프론트 정적파일 → `curl` vendoring (§Standard Stack).

---

## Validation Architecture

### Test Framework

| 항목 | 값 |
|---|---|
| **기존 CLI (회귀 방어)** | stdlib `unittest`. 러너는 파일 직접 실행 (`python3 test_bids.py`) |
| CLI 테스트 위치 | `.claude/skills/naver-ads-weekly/scripts/test_{nvad,reports,ads_rules,ledger,bids,prune}.py` |
| CLI 현재 상태 | **100 tests, 6 파일 전부 exit=0 OK** (2026-09-19 실측: 7+7+21+21+28+16) |
| **신규 웹앱** | **pytest** — `fastapi.testclient.TestClient` 가 pytest 관례를 전제하고, `tmp_path`/`monkeypatch` 픽스처가 subprocess·파일 테스트에 필수 |
| 웹앱 설정 파일 | **없음 — Wave 0 에서 만든다** (`webapp/pytest.ini` 또는 `pyproject.toml [tool.pytest.ini_options]`) |
| 빠른 실행 | `.venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/test_bids.py` (0.003초) |
| 전체 실행 | 아래 §Sampling Rate |

> **프레임워크를 섞는 이유:** CLI 테스트를 pytest 로 옮기면 그 자체가 회귀 위험이다. CLI 는 `unittest` 그대로 두고 웹앱만 pytest 로 간다. pytest 는 `unittest.TestCase` 를 그대로 수집할 수 있으므로, 원하면 나중에 한 명령으로 합칠 수 있다.

### Phase Requirements → Test Map

| Req ID | 증명할 동작 | 유형 | 자동 실행 명령 | 파일 있나 |
|---|---|---|---|---|
| **회귀** | CLI 패치 후 기존 가드 100개 불변 | unit | `for t in nvad reports ads_rules ledger bids prune; do .venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/test_$t.py \|\| exit 1; done` | ✅ 존재 (100 OK) |
| **회귀** | `--only-ads` 없이 부르면 필터 전과 동일 | unit | `pytest webapp/tests/test_cli_patch.py::test_only_ads_none_은_전량과_같다 -x` | ❌ Wave 0 |
| **회귀** | `--only-ads` 가 `update_streaks` **뒤에** 걸린다 | unit | `pytest webapp/tests/test_cli_patch.py::test_필터해도_streak_은_전량기준 -x` | ❌ Wave 0 |
| **회귀** | `--only-ads` 파일 손상 시 exit 1 (전량 폴백 금지) | unit | `pytest webapp/tests/test_cli_patch.py::test_only_ads_깨지면_실패한다 -x` | ❌ Wave 0 |
| ENG-01 | argv 가 `.venv/bin/python3` + `run_ads.py` 로 조립된다 | unit | `pytest webapp/tests/test_argv.py -x` | ❌ Wave 0 |
| ENG-02 | 서버가 죽어도 자식이 산다 | integration | `pytest webapp/tests/test_jobs.py::test_자식은_서버_종료를_견딘다 -x` (합성 잡 5초) | ❌ Wave 0 |
| ENG-03 | 작업 중간 시점에 로그파일이 **이미 커져 있다** | integration | `pytest webapp/tests/test_jobs.py::test_로그가_실시간으로_쌓인다 -x` | ❌ Wave 0 |
| ENG-07 | `create_job` 이 HTTP 없이 호출된다 | unit | `pytest webapp/tests/test_jobs.py::test_create_job_은_http_없이_돈다 -x` | ❌ Wave 0 |
| SAFE-01 | Host `evil.com` → 400 / Origin `evil.com` → 403 | unit | `pytest webapp/tests/test_security.py -x` | ❌ Wave 0 |
| SAFE-02 | 토큰 없음·틀림 → 403, 맞음 → 200 | unit | `pytest webapp/tests/test_security.py -x` | ❌ Wave 0 |
| SAFE-03 | 응답·로그·템플릿 어디에도 시크릿 문자열이 없다 | unit | `pytest webapp/tests/test_security.py::test_시크릿이_새지_않는다 -x` | ❌ Wave 0 |
| FLOW-02 | 실행이 미리보기와 **같은 targets 파일**을 지목 | unit | `pytest webapp/tests/test_flow.py::test_targets_파일이_하나다 -x` | ❌ Wave 0 |
| FLOW-05 | 결과 JSON 이 항목별 성공/실패/스킵+사유를 담는다 | unit | `pytest webapp/tests/test_cli_patch.py::test_항목단위_결과 -x` | ❌ Wave 0 |
| BOARD-01 | ①행에 `imp` 가 없어도 접기가 안 깨진다 | unit | `pytest webapp/tests/test_board.py::test_imp_없는_행도_접힌다 -x` | ❌ Wave 0 |
| BOARD-02 | 계정 alias 가 `result.json` 에서만 온다 | unit | `pytest webapp/tests/test_board.py::test_계정을_코드에_박지_않는다 -x` (가짜 5번째 계정 픽스처) | ❌ Wave 0 |
| BOARD-03 | 보이는 선택 vs 필터 전체가 다른 수를 준다 | manual | 브라우저 확인 (Tabulator API 는 JS) | — |
| BOARD-04 | 선택 건수·예상 인상액 합계가 맞는다 | unit | `pytest webapp/tests/test_board.py::test_예상_인상액_합계 -x` | ❌ Wave 0 |
| BID-01 | ①만 대상으로 잡힌다 (②③ 소재 제외) | unit | `pytest webapp/tests/test_board.py::test_대상은_규칙1_소재만 -x` | ❌ Wave 0 |
| BID-02/03 | 그룹입찰 행의 `from` 이 `groupBid` 다 | unit | **기존 `test_bids.py::test_그룹입찰은_그룹기본가에_10원이다` 가 이미 지킨다** + 웹앱은 계산 안 함을 보장 | ✅ 존재 |
| BID-04 | 되돌리기가 그 작업분만 | unit | `pytest webapp/tests/test_revert.py -x` | ❌ Wave 0 |

### 크레딧·광고비를 쓰지 않고 쓰기 경로를 검증하는 방법

프로젝트 제약이 "모든 쓰기는 dry-run 선행" 이다. 쓰기 경로를 **돈 없이** 증명할 층이 세 개 있다:

1. **`nvad.call` 몽키패치** — 기존 `test_bids.py` 가 이미 쓰는 방식이다 (`bids.nvad.call = fake`). `--only-ads`/`--preview-out` 패치 테스트도 같은 방식으로 PUT 을 한 번도 안 내보내고 `committed`/`failed`/`result` 를 검증한다.
2. **CLI dry-run 실측 회귀** — `bids --run-dir 2026-08-30 --preview-out /tmp/p.json` 은 **0.066초, 네트워크 0**이다. 실데이터로 `--only-ads` 필터가 제대로 먹는지 초 단위로 확인할 수 있다:
   ```bash
   echo '["nad-a001-02-000000495390006"]' > /tmp/t.json
   .venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/run_ads.py bids \
     --run-dir 2026-08-30 --only-ads /tmp/t.json --preview-out /tmp/p.json
   python3 -c "import json;d=json.load(open('/tmp/p.json'));print({k:len(v.get('plans',[])) for k,v in d.items()})"
   # 기대: {'cy728':0,'cy7728':0,'ownway1':1,'pogeunae':0}
   ```
3. **웹앱 레벨** — `create_job` 이 조립한 argv 를 실행하지 않고 문자열로만 검증(`test_argv.py`). `--commit` 이 안 붙는 경로를 못박는다.

**절대 하지 마라:** 자동 테스트에서 `--commit` 을 실행하기. 테스트 코드에 `--commit` 리터럴이 있으면 안 된다 — grep 가드를 하나 두는 것도 좋다:
```bash
! grep -rn '"--commit"' webapp/tests/ || { echo "테스트에 --commit 이 있다"; exit 1; }
```

### 되돌리기가 "그 작업분만" 되돌렸다는 관측 지점

```python
def test_그_작업분만_되돌린다(tmp_path, monkeypatch):
    """백업에 10건이 있고 작업이 3건만 성공했으면 되돌리기 대상은 정확히 3건이다."""
    # 1) before_bids_test.json 에 10건, ads.json 에 같은 10건을 심는다
    # 2) run_revert(acct, run_dir, commit=False, only_ads={"a","b","c"})
    out = bids.run_revert(acct, run_dir, commit=False, only_ads={"a", "b", "c"})
    assert out["targets"] == 3          # ← 관측 지점 1: 대상 수
    # 3) 관측 지점 2: 백업 파일이 바뀌지 않았다 (D-13 — 최초 원본 보존)
    assert json.loads(bk.read_text()) == before_snapshot
    # 4) 관측 지점 3: only_ads=None 이면 10건 (기존 동작 불변)
    assert bids.run_revert(acct, run_dir, commit=False)["targets"] == 10
```
**화면 레벨 가드(런타임):** revert 작업을 만들 때 `len(targets) == len(부모 작업의 성공 adId)` 를 비교해, 다르면 실행을 막고 사유를 보여라. 이게 Pitfall 2 의 마지막 방어선이다.

### SSE 재접속 이어보기를 자동으로 확인하는 방법

합성 잡(Skeleton C)으로 결정적으로 돌린다 — 네트워크 0, 3초.

```python
def test_재접속하면_처음부터_이어본다(client, tmp_path):
    """SSE 를 끊었다 다시 붙여도 끊기기 전 줄이 전부 다시 보여야 한다."""
    job = create_job("synthetic", script="import time\nfor i in range(12):\n print(i); time.sleep(0.2)\n")
    with client.stream("GET", f"/jobs/{job}/stream") as s1:
        first = read_events(s1, seconds=0.8)       # 1차 접속: 0~3 정도
    assert "0" in first
    time.sleep(0.8)                                # 끊긴 사이에 4~7 이 찍힌다
    with client.stream("GET", f"/jobs/{job}/stream") as s2:
        second = read_events(s2, seconds=0.8)      # 2차 접속
    # 관측 지점: 2차 접속의 첫 페이로드에 '0' 이 다시 들어 있다 = 전량 재생
    assert "0" in second and "4" in second
```
**curl 로 손 확인:**
```bash
curl -sN -H "Last-Event-ID: 999" http://127.0.0.1:8765/jobs/<id>/stream | head -20
# 기대: Last-Event-ID 와 무관하게 로그 전량이 다시 흐른다
```

### 보안 3종을 curl 로 검증하는 구체 명령 (전부 실측 통과함)

```bash
PORT=8765; T="$(cat .boot-token-for-test)"     # 개발 중엔 CT_DEV_TOKEN 로 고정
B=http://127.0.0.1:$PORT

# V-SAFE-01a  127.0.0.1 에만 바인드 — 0.0.0.0 이 나오면 실패
lsof -nP -iTCP:$PORT -sTCP:LISTEN | grep -q '127.0.0.1:'"$PORT" && echo PASS || echo FAIL

# V-SAFE-01b  Host 화이트리스트 (DNS rebinding)
test "$(curl -s -o /dev/null -w '%{http_code}' -H "Host: evil.com" $B/)" = 400 && echo PASS || echo FAIL

# V-SAFE-01c  타 사이트 Origin 의 쓰기 (토큰이 있어도)
test "$(curl -s -o /dev/null -w '%{http_code}' -X POST \
        -H "Origin: https://evil.com" -H "X-CT-Token: $T" $B/jobs/bids/preview)" = 403 && echo PASS || echo FAIL

# V-SAFE-02a  토큰 없는 쓰기
test "$(curl -s -o /dev/null -w '%{http_code}' -X POST $B/jobs/bids/preview)" = 403 && echo PASS || echo FAIL

# V-SAFE-02b  틀린 토큰
test "$(curl -s -o /dev/null -w '%{http_code}' -X POST \
        -H "Origin: $B" -H "X-CT-Token: wrong" $B/jobs/bids/preview)" = 403 && echo PASS || echo FAIL

# V-SAFE-02c  정상 쓰기는 통과해야 한다 (403 만 확인하면 '전부 막힘' 을 성공으로 오독한다)
test "$(curl -s -o /dev/null -w '%{http_code}' -X POST -H "Origin: $B" -H "X-CT-Token: $T" \
        -H 'Content-Type: application/json' -d '{"run_dir":"2026-08-30","ad_ids":[]}' \
        $B/jobs/bids/preview)" -lt 400 && echo PASS || echo FAIL

# V-SAFE-03  응답 어디에도 시크릿이 없다
S=$(python3 -c "import json,pathlib;print(json.loads((pathlib.Path.home()/'.eroom/naver-ads.json').read_text())['accounts'][0]['secret_key'])")
curl -s -H "Cookie: ct_session=$T" $B/ | grep -q "$S" && echo FAIL || echo PASS
grep -rq "$S" webapp-logs/ && echo FAIL || echo PASS

# V-SAFE-01d  상태를 바꾸는 GET 이 없다 (Origin 방어의 전제)
! grep -rnE '@app\.get\(.*\)\s*\n\s*def .*(create_job|spawn)' webapp/ && echo PASS
```

### Sampling Rate

- **태스크 커밋마다:** `.venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/test_bids.py` (0.003초) + `pytest webapp/tests -x -q` (합성 잡 제외 시 수 초)
- **웨이브 병합마다:**
  ```bash
  for t in nvad reports ads_rules ledger bids prune; do \
    .venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/test_$t.py || exit 1; done
  .venv-web/bin/pytest webapp/tests -q
  ```
- **Phase 게이트 (`/gsd:verify-work` 전):** 위 전체 + 보안 curl 8종 전량 PASS + Skeleton B 수동 1회(`prep --account cy728` 중 탭 닫았다 열기)

### Wave 0 Gaps

- [ ] `.venv-web` 생성 + 의존 4종 설치 — **모든 웹앱 테스트의 전제** (설치 성공은 이미 실측 확인)
- [ ] `webapp/pytest.ini` (또는 `pyproject.toml [tool.pytest.ini_options]`) + `.venv-web` 에 `pytest` 설치
- [ ] `webapp/tests/conftest.py` — `client`(TestClient with 토큰 픽스처) · `tmp_run_dir` · `fake_result_json` · `synthetic_job`
- [ ] `webapp/tests/fixtures/result_min.json` — 계정 **5개**(가짜 하나 추가해 BOARD-02 를 진짜로 검증) × 6규칙, ①은 `imp` 없이
- [ ] `webapp/tests/fixtures/targets_*.json`
- [ ] 합성 잡 러너 (Skeleton C) — `create_job(kind="synthetic", …)` 을 테스트 전용으로 열어두되 **운영 라우트에는 노출하지 마라**
- [ ] `.gitignore`: `.venv-web/` · `webapp.db*` · `webapp-logs/` · `node_modules/` · `package*.json`
- [ ] 테스트에 `--commit` 리터럴 금지 grep 가드

---

## Security Domain

### Applicable ASVS Categories

| ASVS | 적용 | 표준 통제 |
|---|---|---|
| V1 아키텍처 | yes | 신뢰경계 1개: 브라우저 ↔ 로컬서버. 자격증명은 **CLI 서브프로세스에만** 존재 (§4.5) |
| V2 인증 | **no (Out of Scope)** | 1인 로컬. 대신 부팅 토큰이 "이 서버를 띄운 사람" 을 증명하는 약한 소유 증명으로 선다 |
| V3 세션 | partial | `ct_session` 쿠키 = 부팅 토큰. `HttpOnly` · `SameSite=Strict` · 서버 재시작마다 무효화 |
| V4 접근통제 | partial | 역할 없음. 쓰기 메서드 전용 게이트 3층(Host/Origin/토큰) |
| V5 입력검증 | **yes** | **Pydantic** 으로 모든 요청 바디. 특히 `ad_ids: list[str]` 에 길이 상한(D-08 1500)과 패턴(`^nad-`) |
| V6 암호 | partial | `secrets.token_urlsafe` · `compare_digest`. **HMAC 서명은 CLI 의 `nvad.sign` — 재구현 금지** |
| V7 에러/로깅 | **yes** | `debug=False` · 트레이스백 비노출 · **로그 쓰기 시점 시크릿 스크러버** (§4.5) |
| V8 데이터보호 | yes | `~/.eroom/naver-ads.json` 600 유지. 웹앱이 이 파일을 복사·캐시하지 않는다 |
| V12 파일 | **yes** | `--only-ads`/`--preview-out` 경로는 **웹앱이 생성**한다. 사용자 입력에서 경로를 받지 마라 (path traversal) |
| V13 API | yes | `docs_url=None, redoc_url=None` — 스키마 노출 불필요 |
| V14 설정 | **yes** | `--workers 1` · `--host 127.0.0.1` 을 기동 경로 한 곳에 고정 |

### Known Threat Patterns (로컬 단일사용자 웹앱 + subprocess)

| 패턴 | STRIDE | 표준 완화 | 이 단계 적용 |
|---|---|---|---|
| **DNS rebinding** — 악성 사이트가 자기 도메인을 127.0.0.1 로 재바인딩 | Spoofing / Elevation | Host 헤더 화이트리스트 | `TrustedHostMiddleware` — 실측 400 |
| **교차 사이트 CSRF** — 다른 탭이 POST 를 쏜다 | Tampering | Origin 검증 + 커스텀 헤더 토큰 | §4.3/4.4 — 실측 403 |
| **부수효과 GET** — `<img src>` 로 작업을 트리거 | Tampering | 쓰기는 절대 GET 으로 두지 않는다 | 설계 규칙 + grep 가드 |
| **명령 주입** — 사용자 입력이 argv/셸로 | Elevation | `shell=False` + 리스트 argv + Pydantic 검증 | `AdsArgv.build()` 가 유일한 조립부 |
| **경로 조작** — `run_dir=../../etc` | Tampering | 화이트리스트: 실제 존재하는 run-dir 디렉터리명만 허용 | `run_dir in scan_run_dirs()` 검사 |
| **시크릿 로그 유출** | Info Disclosure | 스크러버 + 화이트리스트 투영 + env 미전달 | §4.5 |
| **argv 를 통한 시크릿 노출 (`ps`)** | Info Disclosure | 시크릿을 argv/env 에 절대 안 넣는다 | CLI 가 파일을 직접 읽는다 |
| **의도치 않은 대량 쓰기** (필터 실패 → 전량) | Tampering (자해) | `--only-ads` 실패 시 exit 1 · 계정별 1,500 상한 | §1.3 · D-08 |
| **동시 쓰기로 백업 손실** | Tampering | 쓰기 잡 전역 1개 가드 | Pitfall 3 |
| **SSE 커넥션 고갈** (HTTP/1.1 호스트당 6) | DoS (자해) | 잡마다 스트림을 열지 마라 — **활성 잡 하나만** 스트림, 나머지는 상태 폴링 | STACK.md 경고 반영 |
| **공급망 (CDN 스크립트 변조)** | Tampering | vendoring 또는 SRI | §Standard Stack |

---

## State of the Art

| 옛 방식 | 지금 방식 | 언제 바뀜 | 의미 |
|---|---|---|---|
| `starlette.responses` 에 SSE 가 있을 거라 가정 | 없다 → `sse-starlette` 필요 | 계속 없었음 (1.6.0 에서 실측 확인) | 손으로 짜면 keepalive·끊김 감지를 직접 관리 |
| `Last-Event-ID` 로 SSE 재개 | **htmx-ext-sse 와는 성립 안 한다** (재연결 = 새 EventSource) | htmx sse ext 2.x | 서버가 전량 재생 책임을 진다 |
| htmx 는 `latest` 를 따라간다 | htmx 4.0.0 이 나왔지만 **`latest` 는 2.0.10** | 2026-08-28 (4.0 출시), 전환 예정 2027 | 확장 생태계가 2.x 기준. 버전을 명시 고정 |
| TrustedHostMiddleware 에 포트를 적어야 한다? | **포트를 떼고 매칭한다** | 소스 확인 | `allowed_hosts=["127.0.0.1"]` 로 충분 |
| APScheduler 4.x | 4.0.0a6(2025-04-27) 이후 정체 → **3.11.3** | — | v2 진입 시에만. Phase 1 무관 |

**폐기/피할 것:**
- htmx 4.0.0 (생태계 분리) · APScheduler 4.x (알파) · `uvicorn --workers N>1` · Celery/RQ/Redis · Docker · WebSocket · npm 빌드체인 — 전부 CLAUDE.md 확정.

---

## Assumptions Log

| # | 주장 | 절 | 틀렸을 때의 영향 |
|---|---|---|---|
| A1 | `mallProductId` 가 계정 간에 겹칠 수 있다 | §2.3 | 접기 키를 `(alias, mpid)` 대신 `mpid` 로 하면 다른 계정 상품이 한 줄로 합쳐진다. **지금 데이터에선 계정 간 중복을 확인하지 못했다** — `(alias, mpid)` 를 쓰면 어느 쪽이든 안전하다 |
| A2 | `prep` 6계정은 ~15분이다 | §1.1 | 4계정 mtime 간격(~3분/계정)에서 선형 외삽했다. 계정 규모에 따라 달라진다 |
| A3 | 웹앱 테스트 프레임워크는 pytest 가 낫다 | §Validation | CLI 가 unittest 라 섞인다. `unittest` 로 통일해도 되지만 `TestClient`/픽스처 편의를 잃는다 — planner 가 뒤집어도 큰 손해 없음 |
| A4 | 프론트 정적파일 vendoring 이 CDN 보다 낫다 | §Standard Stack | CLAUDE.md 는 CDN 을 전제한다. 파일만 로컬로 옮기는 것이라 스택 변경은 아니지만, 버전 갱신이 수동이 된다 |
| A5 | `accounts` 서브커맨드 추가가 D-01 안에 든다 | §3.4 | D-01 은 "입력 필터 플래그"라고 썼다. 읽기 전용 서브커맨드는 위험 0이지만 **문자 그대로는 범위 밖**이다 — planner 가 사용자 확인을 받아라 |
| A6 | 로그 전량 재생이 오프셋 재개보다 낫다 | §5.4 | 로그가 20KB 미만이라는 실측(bids 4.5KB)에 기댄다. 나중에 진행률 출력이 붙어 로그가 MB 급이 되면 재검토 |
| A7 | 신선도 경고 임계값 8일 | §Pitfall 7 | Claude's Discretion 항목이다. 주 1회 케이던스(`RAISE_COOLDOWN_DAYS=6`)에서 유도한 값일 뿐 사용자 확인이 필요하다 |
| A8 | 인터넷 연결 · 광고 API 도달성 | §Environment | 이번 리서치에서 광고 API 를 **한 번도 호출하지 않았다**(돈/부작용 회피). Skeleton B 첫 실행 전에 확인이 필요하다 |

---

## Open Questions (RESOLVED 2026-09-20)

> 여섯 개 전부 **계획 단계에서 확정됐다.** 아래 `권고:` 줄은 리서치 당시의 근거 서술이고, 그 밑의
> **확정:** 줄이 오케스트레이터가 내린 결론과 그 결론을 실제로 실행하는 플랜 ID 다.
> 플랜들은 이미 본문에서 `OQ-N 확정` 으로 이걸 인용하고 있다.

1. **`--only-ads` 필터를 `run_bids` 안쪽에 넣는 게 D-01 을 어기나?**
   - 아는 것: D-01 은 "`cmd_bids` 가 rows 를 거르기만 한다"고 썼다.
   - 불분명: `cmd_bids` 에서 거르면 `update_streaks` 가 오염된다(§Summary 발견 5, 실측 근거 있음).
   - 권고: **`run_bids(…, only_ads=None)` 기본인자 1개 + `update_streaks` 뒤 1줄 필터.** 판정·계산·백업·ledger 는 여전히 무변경이므로 D-01 의 **의도**는 지킨다. planner 가 사용자에게 한 줄로 확인받아라.
   - **확정:** 어기지 않는다. 필터는 `cmd_bids` 가 아니라 **`run_bids` 안쪽, `update_streaks` 호출 뒤** 1줄이다 — `cmd_bids` 에서 거르면 `zero_ids` 가 축소돼 나머지 상품의 연속실패 카운팅이 통째로 빠진다.
   - **실행 플랜:** `01-02` Task 3 (CLI 패치) · 방어선은 `test_cli_patch.py::test_필터해도_streak_은_전량기준` (VALIDATION 회귀-02/03/04)

2. **인상일과 되돌리기 날짜가 다를 때 ledger 불일치 (Pitfall 4)**
   - 아는 것: `record_reverted` 가 당일에만 플래그를 찍는다. 의도된 방어(Minor 5 주석)다.
   - 불분명: 실사용에서 "다음날 되돌리기"가 얼마나 흔한가.
   - 권고: Phase 1 은 **경고 배너만**. 고치려면 Phase 2 로 올려라(로직 변경 + ledger 테스트 재작성).
   - **확정:** Phase 1 은 `record_reverted` 를 **고치지 않는다.** 인상일 vs 오늘을 비교해 다르면 경고 배너를 띄우되 **실행은 막지 않는다.** 현재 동작을 문서화하는 테스트를 남겨 Phase 2 가 뒤집을 때 알아채게 한다.
   - **실행 플랜:** `01-08` Task 1 (실행 버튼 위 경고 (b)) · `01-09` Task 2 (되돌리기 버튼 2개 위 배너) · `01-09` Task 1 (현재 동작 문서화 테스트) · 위협 `T-1-38` disposition = accept

3. **`bids --commit` 진행률이 없다 (1,200건 100초 동안 무음)**
   - 아는 것: `run_bids` 루프에 진행 출력이 없다. 실패 줄만 나온다.
   - 불분명: 사용자가 "멈춘 건가" 를 참을 수 있는지.
   - 권고: Phase 1 은 **경과시간 + "진행 중" 표시**로 간다(로그 무변경). 진행률 주입은 로직 변경이라 별도 결정.
   - **확정:** CLI 에 진행률을 주입하지 않는다. 화면의 **경과시간**으로 덮는다 — `GET /jobs/{id}` 가 `elapsed_sec` 을 주고, 작업 패널이 "멈춘 게 아니다 — 초당 12건씩 돈다. N건이면 약 M초" 를 계산해 띄운다.
   - **실행 플랜:** `01-05` Task 3 (`elapsed_sec` 공급) · `01-06` Task 2 (작업 패널 경과시간) · `01-08` Task 1 (실행 중 안내 문구)

4. **`prep` 의 `POST /stat-reports` 를 "쓰기 없음" 으로 부를 수 있나?**
   - 아는 것: 광고(소재/입찰가/예산)를 바꾸지 않는다. 리포트 잡만 만든다.
   - 권고: 문구를 **"광고를 바꾸지 않는다"** 로 정확히 써라. "API 에 아무것도 쓰지 않는다" 는 부정확하다.
   - **확정:** 부를 수 없다. 화면 문구는 **"광고를 바꾸지는 않는다 — 소재·통계를 새로 받아올 뿐이다"** 로 고정한다. "API 에 아무것도 쓰지 않는다" 는 금지 문구다(`prep` 은 `POST /stat-reports` 로 리포트 잡을 만든다).
   - **실행 플랜:** `01-05` Task 3 ("새로 수집" 버튼 옆 안내 문구)

5. **서버 상시 기동(launchd)을 Phase 1 에 넣나?**
   - 아는 것: "브라우저 닫아도 살아있게" 는 **서버가 살아 있어야** 성립한다. 현재 LaunchAgent 가 없다.
   - 불분명: CONTEXT.md 에 상시 기동 결정이 없다.
   - 권고: Phase 1 은 **수동 기동 + 기동 스크립트 1개**. launchd 는 Phase 2 의 ENG-05/06 과 묶어라.
   - **확정:** Phase 1 에 launchd 를 넣지 않는다. **수동 기동 + 기동 스크립트 1개**(`webapp/run-webapp.sh`, `--workers 1` 고정)로 간다. 상시 기동은 Phase 2 의 ENG-05/06 과 묶는다 — CONTEXT.md 에 상시 기동 결정이 없어 Phase 1 이 임의로 만들지 않는다.
   - **실행 플랜:** `01-03` Task 2 (`webapp/run-webapp.sh`) · Phase 1 범위에 launchd 태스크 **없음**

6. **광고 API 도달성 (A8)**
   - 리서치에서 광고 API 를 한 번도 안 불렀다(의도적). `~/.eroom/naver-ads.json` 의 키가 아직 유효한지 미확인.
   - 권고: Skeleton B 의 첫 태스크를 `prep --account cy728` 로 잡고, 실패하면 자격증명 갱신을 먼저 처리해라.
   - **확정:** Skeleton B 체크포인트의 **첫 단계**가 `run_ads.py prep --account cy728` 완주 확인이다. 401/403 이면 거기서 멈추고 자격증명 갱신을 먼저 처리한다 — 이후 모든 실행이 이 키 위에 선다.
   - **실행 플랜:** `01-06` Task 3 (2번 단계) · VALIDATION § Manual-Only Verifications 의 `(OQ-6)` 행

---

## Sources

### Primary (HIGH — 이 맥북에서 직접 실행/측정)
- `.claude/skills/naver-ads-weekly/scripts/*.py` (2,432줄 전량 읽음) — 서브커맨드 표면 · 종료코드 · 리턴 스키마 · 가드 상수
- `~/python_work/data/naver-ads/runs/2026-08-30/` 실데이터 파싱 — 규칙별 행 수 · 필드 집합 · 팬아웃 · `useGroupBid` 92% · 페이로드 크기
- `~/python_work/data/naver-ads/ledger/*.json` · `before_bids_*.json` — 2,242건 누적 백업 확인 (D-12 근거)
- `~/.eroom/naver-ads.json` (600) · `workspace.toml` — 계정 구조 · `data_root`
- 회귀 테스트 6파일 실행 — **100 tests, 전부 exit=0 OK**
- `run_ads.py bids --run-dir 2026-08-30` 실행 — 0.066초 · stdout 포맷 · exit=0
- 버퍼링 실험 — `PYTHONUNBUFFERED` 유무로 0.5초 시점 0B vs 14B
- 프로세스 그룹 실험 2회 — `start_new_session=True` 가 그룹 SIGTERM 과 `uvicorn --reload` 재시작을 견딤
- `.venv-probe` 실제 설치 — fastapi 0.141.1 / starlette 1.6.0 / pydantic 2.13.5 / uvicorn 0.53.0 / jinja2 3.1.6 / sse-starlette 3.4.11 / anyio 4.15.1 · 시그니처 추출 · `starlette.responses` 에 SSE 부재
- 보안 프로브 앱 + curl 6케이스 — 400/403/403/200/403 + `lsof` 127.0.0.1 바인드
- `man caffeinate` (로컬) — `-i` idle sleep 방지 · utility 수명
- `slopcheck install` — PyPI 5 OK · npm 4 OK
- PyPI JSON API · npm registry — 버전·배포일·dist-tags 직접 조회

### Secondary (HIGH-MEDIUM — 공식 소스)
- github.com/Kludex/starlette `starlette/middleware/trustedhost.py` — 포트 분리 · 400 응답 · websocket scope
- github.com/sysid/sse-starlette `sse.py` · `event.py` — `EventSourceResponse`/`ServerSentEvent` 시그니처 · `Last-Event-ID` 미처리 · `http.disconnect` 감지
- github.com/bigskysoftware/htmx-extensions `src/sse/sse.js` — 재연결이 `createEventSource` 를 새로 호출 (Last-Event-ID 유실)
- htmx.org/extensions/sse/ — `sse-connect`/`sse-swap`/`sse-close` · CDN SRI
- fastapi.tiangolo.com/async/ — `def` 핸들러의 외부 스레드풀 실행
- `.claude/skills/naver-ads-weekly/SKILL.md` — 운영 규칙 · 6규칙 요약 · 자격증명 위치 · 연동끊김의 정체

### Tertiary (MEDIUM — 검증 필요)
- `prep` 소요시간 6계정 추정 (4계정 mtime 간격에서 외삽)
- Tabulator 클라이언트 사이드 한계 ≈5,000행 (STACK.md 의 경험 기반 판단을 승계)

---

## Metadata

**확신도 분해:**
- 래핑 대상 CLI 표면 (§1): **HIGH** — 소스 전량 읽음 + 실행으로 확인
- run-dir 스키마 (§2): **HIGH** — 실데이터 전수 집계
- 계정 확장 경로 (§3): **HIGH** — 실파일 + `load_accounts` 소스
- 보안 3종 (§4): **HIGH** — 이 맥북에서 6케이스 curl 통과
- 작업 엔진 (§5): **HIGH** — 버퍼링·세션분리·reload 생존·SSE 를 전부 실측
- Walking Skeleton (§6): **HIGH** — 후보별 소요시간을 실측
- 검증 아키텍처: **MEDIUM-HIGH** — 기존 100개는 실행 확인. 신규 테스트는 아직 존재하지 않는 설계
- 광고 API 실제 동작 (`--commit` 경로): **미확인** — 의도적으로 안 불렀다

**Research date:** 2026-09-19
**Valid until:** 2026-10-19 (약 30일). 단 **run-dir 이 새로 생기면 §2 의 숫자는 전부 다시 재라.** `2026-08-30` 회차는 이미 20일 묵었고 D-15 의 "새로 수집" 이 돌면 즉시 낡는다.
