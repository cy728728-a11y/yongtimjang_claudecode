# Phase 2: 되돌릴 수 없는 쓰기 — 꺼진 소재 정리 - Research

**Researched:** 2026-10-01
**Domain:** 기존 CLI(`naver-ads-weekly prune`) subprocess 래핑 · 파괴적 쓰기 안전 계약 · FastAPI/htmx/Tabulator 보드 확장
**Confidence:** HIGH (전부 로컬 코드·실데이터 실측. 외부 라이브러리 신규 도입 0)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### 🔒 잠긴 제약 (프로젝트·메모리·이전 페이즈 승계 — 플랜이 바꿀 수 없다)

- **L-01: 삭제 `--commit` 은 매번 플랜의 blocking human checkpoint 다** — 첫 회 실탄 실행은 용팀장이 건수·계정·샘플을 보고 승인한 뒤에만. `--auto` 체인·auto_advance 가 자동 승인하지 않는다. 화면에서도 매번 건수 타이핑(아래 D-04).
- **L-02: CLI 재작성 금지.** `naver-ads-weekly` 의 `run_ads.py prune` / `prune.py` 를 subprocess 로 부르고 필요한 건 **주입구 플래그 추가만**(`--preview-out`, `--only-ads`, `--limit` 등). 무플래그 동작 불변. 판정(`prune.deletable`)을 웹앱에 재구현하지 않는다.
- **L-03: 삭제 대상은 `statusReason == AD_ABNORMAL_INTERLOCK` 뿐**(`prune.DELETE_REASONS`). 검수중·거부는 목록에도 안 나온다. 물갈이 부산물이라 수천 건이 정상이다(메모리 — 4계정 7,340건 실적).
- **L-04: 계정은 `~/.eroom/naver-ads.json` 항목 그대로**(현재 4개). 웹앱이 계정을 하드코딩하지 않는다.
- **L-05: 쓰기 잡은 `WRITE_KINDS` 전역 1개 · `caffeinate -i` · 미리보기 잡 id 만 받는 커밋**(Phase 1/5/6/7 패턴). 커밋은 대상을 새로 받지 않는다.

#### 삭제 미리보기 (PRUNE-01 · PRUNE-03 · SAFE-06)

- **D-01 [auto]: 미리보기 = `prune` dry-run 에 `--preview-out <json>` 주입구를 붙여 계정별 삭제 대상 전 목록(계정 · 캠페인 · 광고그룹 · 소재id · 상품명/채널상품id · 정지사유 · 정지일)을 쓰고, 웹은 그 파일만 읽어 표로 보인다.**
  · [auto] Q: "대상 목록을 어디서 만드나 — ⓐ CLI dry-run 산출물 ⓑ 웹앱이 ads.json + 규칙 재계산" → **ⓐ** (recommended — L-02, SAFE-06 같은 선정 함수)
  · 표: 계정별 접힘 + 건수 요약 + 전체 펼침. 수천 행이라 Tabulator 가상 렌더링 재사용
- **D-02 [auto]: 미리보기·커밋 모두 같은 `prune.deletable()` 을 탄다(SAFE-06). 커밋은 미리보기 잡 id 만 받고, 미리보기가 쓴 대상 파일을 `--only-ads <file>` 로 넘긴다** — 커밋 시점 CLI 는 그 목록 ∩ 재조회 결과만 지운다.
- **D-03 [auto]: 백업은 미리보기에서도 이미 쓰인다(현 CLI 동작). 커밋은 실행 직전에 백업을 다시 쓰고, 실패하면 그 계정은 0건 삭제 · 사유 `backup_failed` 를 결과 표에 보인다(SAFE-04 · PRUNE-02 · SC-2).**

#### 실행 확인 · 신선도 · 재조회 (SAFE-05 · FLOW-03 · SC-1 · SC-3)

- **D-04 [auto]: 커밋은 건수 타이핑 확인 — 쿠팡 패턴 그대로(`typed_count: StrictInt`, 서버가 다시 센 값과 다르면 409).** 복사 영역처럼 접힘·다른 색·버튼 1회.
- **D-05 [auto]: 미리보기 유효기간 24시간 — 지나면 커밋 거부 + "다시 미리보기" 안내(FLOW-03).** 쿠팡 D-12 와 같은 값.
- **D-06 [auto]: 커밋 직전 CLI 가 재조회한다(현 `revived_filter`). 미리보기에 있었는데 지금은 아닌 소재(살아남·이미 삭제됨·사유 바뀜)는 빼고 소재별 사유와 함께 결과 표에 나열한다. 재조회 대상이 미리보기보다 늘면 0건 삭제 · exit 5("다시 미리보기")** — 본 것보다 많이 지우지 않는다.

#### 상한 (SAFE-07)

- **D-07 `[auto — 용팀장 확인 필요]`: 1회 삭제 상한 = 설정 `prune_max_items` 기본 8000(전 계정 합), 계정별 상한 없음.** 넘으면 미리보기에서 "상한 초과" 로 표시하고 커밋 거부.
  · 이유: 물갈이 직후 한 계정에서 5,024건이 나온 적이 있다. 입찰가용 계정당 1500 을 재사용하면 정상 정리가 막힌다
  · 크레딧 상한은 이 버튼엔 해당 없음(삭제는 크레딧 0). SAFE-07 의 크레딧 축은 기존 상세·썸네일 `--max-credits` 로 이미 충족 — 감사 로그에 같이 남긴다

#### 재시도 (FLOW-06)

- **D-08 [auto]: 결과 표에 실패 건이 있으면 `실패분만 재시도` 버튼 — 같은 미리보기 대상 파일로 커밋을 다시 돌리고, CLI 의 진행 파일(`delete_progress_<alias>.jsonl`)이 성공(200/204/404) 건을 건너뛴다.** 재시도도 건수 타이핑(실패 건수).

#### 공용 안전 계약 (ENG-04 · ENG-05 · FLOW-07)

- **D-09 [auto]: 작업 잠금 = 기존 전역 쓰기 1개(`WRITE_KINDS`) 유지 + "같은 미리보기는 한 번만 커밋" 멱등 검사(성공 커밋 자식이 있으면 409, 재시도 경로만 예외).** 대상별 세밀 잠금은 안 만든다 — 사용자 1명 · 동시 쓰기 1개면 충분.
  · [auto] Q: "ENG-04 를 대상별 잠금 테이블로 갈까" → **아니다 — 전역 1개 + 미리보기 멱등** (recommended, 스택 결정 '테이블 3개' 유지)
- **D-10 [auto]: 서버 기동(lifespan) 시 `_reap` 를 한 번 돌려 고아 잡을 `orphaned` 로 정리한다(ENG-05).** 지금은 다음 잡 생성 때만 지연 실행된다.
- **D-11 [auto]: 감사 로그 = `<데이터루트>/control-tower/audit.jsonl` append-only. 모든 `WRITE_KINDS` 잡이 끝날 때 1줄: `{시각, 잡id, 종류, 부모잡id, 계정, 대상수, 성공, 실패, 제외, 크레딧, 종료코드}`.** 크레딧은 CLI 산출물에서 읽을 수 있는 잡만(상세·썸네일 등), 나머지 0. 웹 화면은 만들지 않는다 — 파일 + `sqlite3`/`jq` 로 본다.

#### 보드 (BOARD-05 · BOARD-06)

- **D-12 [auto]: 규칙⑥ 행에 정지사유(`statusReason`)를 실어 보드에서 `연동끊김` / `검수중` / `거부` 를 구분해 보인다(`ad_info` 에 필드 추가 — 읽기 전용 보강).**
- **D-13 [auto]: BOARD-05 는 지금 규칙②~⑤가 `live_ads` 만 쓴다는 사실을 테스트로 고정하고, 소재가 전부 정지된 상품 행엔 `광고 정지` 표시를 붙여 과거 클릭을 현재 유입으로 읽지 않게 한다.**
- **D-14 [auto]: 오판정 표시 = 보드 행마다 버튼 1개 → `<회차 run-dir>/misjudged.jsonl` 에 `{시각, 규칙, 상품키, 메모}` append, 행에 표식. 다시 누르면 해제 줄 append(최신 줄이 이긴다).** 판정 결과 자체는 바꾸지 않는다 — 2단계 자동화의 승인 근거 데이터일 뿐.

### Claude's Discretion

- 미리보기 표 컬럼 배치 · 계정 접힘 UI · 결과 표 형식(입찰가 `_result_table.html` 계열 재사용 권장)
- `--preview-out` JSON 스키마 세부, 대상 파일 형식
- 감사 로그 기록 지점(잡 종료 훅 위치)
- 플랜 분할(MVP 수직 슬라이스 — 미리보기 → 커밋 → 재시도 → 공용 계약 → 보드 순 권장)

### Deferred Ideas (OUT OF SCOPE)

- 다른 쓰기 버튼(입찰가·상세·마켓·썸네일·쿠팡)에 24h 신선도·재조회 소급 — 각 버튼 다음 손볼 때
- 감사 로그 열람 화면
- 대상별 세밀 잠금 테이블
- 물갈이 재업로드 뒤 새 소재 자동 등록
- 오판정 데이터로 규칙 임계치 자동 조정(2단계)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ENG-04 | 같은 대상에 같은 작업이 동시에 두 번 돌지 않는다 | 기존 `WRITE_KINDS` 전역 가드(`jobs.create_job` ①) + 신규 "미리보기당 성공 커밋 1회" 멱등 검사. §패턴 5 |
| ENG-05 | 서버 재시작 시 고아 작업 정리 | `jobs._reap` 를 lifespan 에서 1회 호출. **단 테스트 클라이언트가 실DB 를 reap 하는 함정 + PID 재사용 함정** §함정 3·4 |
| ENG-06 | `caffeinate -i` | **이미 완료(Phase 3 선취)** — `jobs._수면방지_프리픽스` 실존 확인. 이 페이즈는 `prune_commit` 을 그 목록에 **추가만** 한다 |
| SAFE-04 | 백업 실패 시 쓰기 중단 | `prune.run_prune` 이 이미 `backup_paused()` None → `aborted:"backup_failed"` 로 0건. **단 백업 파일명이 날짜 단위라 같은 날 재실행 시 실제 삭제분 백업이 덮일 수 있다** §함정 1 |
| SAFE-05 | 커밋 직전 재조회 · 빠진 항목 보고 | `collect.fetch_ads` + `revived_filter` 실존. 소재별 제외 사유는 **없음** → 순수 함수 `excluded_reasons()` 추가 필요 §패턴 2 |
| SAFE-06 | 미리보기·실행이 같은 선정 함수 | 둘 다 `prune.run_prune → deletable()` 를 탄다. 커밋은 미리보기 산출물 파일을 `--only-ads` 로 그대로 넘긴다 |
| SAFE-07 | 건수 상한 · 크레딧 상한 | 설정 `prune_max_items`(8000) — 서버(미리보기 표시·커밋 400) + CLI `--max-items`(초과 시 전량 거부, 자르지 않음) 2겹. 크레딧 축은 기존 `--max-credits` |
| FLOW-03 | 낡은 미리보기 거부 · 재판정 안내 | 쿠팡 `_미리보기유효시간`(24h) 재사용 + 재조회가 그 사이 바뀐 소재를 뺀다 |
| FLOW-06 | 실패분만 재시도 | 커밋 산출물의 실패 adId ∩ 미리보기 adId 를 새 대상 파일로 → 같은 `prune_commit` 경로. 진행 파일이 2차 방어 §패턴 4 |
| FLOW-07 | 감사 로그 JSONL | `jobs._finish` + `_reap` orphaned 분기 = 유일한 종료 지점. **트랜잭션 롤백 시 중복 기록 함정** §함정 2 |
| BOARD-05 | 정지 소재 과거 실적을 현재 유입으로 안 보이기 | `ads_rules.classify` ②~⑤ 는 `live` 만 순회 — 테스트로 고정. 보드 `광고 정지` 배지 §패턴 7 |
| BOARD-06 | 1클릭 오판정 표시 | 새 POST 라우트 + `<run-dir>/misjudged.jsonl` append, `GET /` 가 최신 줄로 행에 표식 §패턴 8 |
| PRUNE-01 | `AD_ABNORMAL_INTERLOCK` 만 | `prune.DELETE_REASONS` + `deletable()` — 기존 테스트 5개가 고정 중 |
| PRUNE-02 | 백업 성공 뒤에만 삭제 | `run_prune` 순서: backup → (commit) → recheck → delete. 테스트로 순서 고정 필요 |
| PRUNE-03 | 실행 전 전부 나열 | `--preview-out` 이 계정별 전 대상 행을 쓴다 → Tabulator 가상 렌더링 |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- 웹앱은 기존 CLI 의 **래퍼**다 — 검증된 로직·테스트·가드레일 재작성 금지. 판정값은 CLI 산출물에서만 읽는다.
- 모든 쓰기 작업은 **dry-run 선행**. 크레딧 소모 작업은 접수 전 견적 보고(삭제는 크레딧 0).
- 진실의 원천은 서버 상태 — 로컬 대장을 정본으로 삼지 않는다(재조회가 정본).
- 광고 계정은 `~/.eroom/naver-ads.json` 항목 추가로만 늘어난다 — **실측 현재 7계정**(cy728·cy7728·dldmswl1986·level_up_ad·milky-way1992·ownway1·pogeunae). CLAUDE.md 의 "4개 → 6개 예정"은 낡았다 `[VERIFIED: runs/2026-09-20/accounts ls]`.
- 코드 주석 한국어, Python, try-except 포함.
- 스택: FastAPI 0.141.1 + htmx 2.0.10 + Tabulator 6.5.3 + stdlib sqlite3, `uvicorn --workers 1`, `.venv-web`(웹) / `.venv`(CLI) 분리, subprocess 경계.
- 안 쓰는 것: 태스크 큐, ORM, WebSocket, htmx 4, 빌드체인.
- 사용자 전역 규칙: 화면 동작 검증은 `uat-verifier`(Playwright) 에 맡긴다. 사람 몫은 ② 되돌릴 수 없는 실계정 작업의 **실행 승인**(= L-01 삭제 실탄).
- GSD 워크플로 경유 수정만.

## Summary

삭제 로직은 이미 `prune.py` 에 다 있다: `deletable()`(연동끊김만) → `backup_paused()`(실패 시 계정 중단) → 커밋이면 `collect.fetch_ads()` 재조회 + `revived_filter()` 교집합 → `delete_ads()`(진행 파일 재개·429 백오프·초당 ~12건). 2026-08-29~30 수동 실행으로 7,340건 전부 204 성공이 진행 파일에 남아 있다 `[VERIFIED: paused-backup/delete_progress*.jsonl]`. **웹이 감쌀 수 없는 이유는 단 하나 — `cmd_prune` 이 `run_prune` 반환값을 버리고 종료코드 0 만 낸다.** 그래서 이 페이즈의 CLI 작업은 `cmd_bids` 가 Phase 1 에서 받은 것과 같은 주입구(`--preview-out`, `--only-ads`) + `--max-items` + 백업 태그 + 소재별 결과/제외사유 수집이다. 무플래그 경로는 바이트 단위로 그대로 둔다.

웹 쪽은 Phase 7 쿠팡 트랙이 거의 그대로 틀이다: 트랙 소유 라우터(`routes/prune.py`) + 트랙 JS(`static/prune.js`) + 결과표 dict 를 `get_job_result` 가 병합 + 건수 타이핑 409 + 24h 신선도 + 성공 자식 멱등. 공용 계약(감사 로그·기동 reap·멱등)은 `jobs.py` 에 들어가므로 **공유 파일 수정을 한 플랜에 몰아라**(07-01 방식).

조사 중 발견한, CONTEXT 에 없는 위험 4가지가 플래닝에 결정적이다: ① 백업 파일명이 `paused_<alias>_<날짜>.json` 이라 같은 날 회차가 재수집되면 **이미 지운 소재의 백업이 덮여 사라진다** ② `create_job` 이 `_reap` 을 가드 트랜잭션 안에서 돌려, 그 트랜잭션이 409/400 으로 롤백되면 `_finish` 가 날아가고 잡이 `orphaned` 로 바뀐다(기존 잠복 버그) — 감사 로그를 `_finish` 에 걸면 **중복 기록**까지 생긴다 ③ lifespan reap 은 테스트 `client` 픽스처가 tmp DB 로 갈아끼우기 **전에** 돌아 **실제 `webapp.db` 를 건드린다** ④ D-06 의 "재조회가 늘면 exit 5" 는 `revived_filter` 가 교집합이라 **구조적으로 불가능** — 대신 "미리보기 이후 새로 꺼진 N건(안 지움)"을 보고하고 테스트로 고정하라.

**Primary recommendation:** CLI 주입구 5개(`--preview-out`·`--only-ads`·`--max-items`·`--backup-tag` + 소재별 결과/제외사유)를 먼저 `.venv` 단위테스트로 굳히고, 그 위에 쿠팡 트랙 복제로 `prune_preview`/`prune_commit` 두 kind 를 붙인 뒤, 공용 계약(감사·reap·멱등)은 `jobs.py` 한 플랜에서 롤백 버그를 같이 고쳐라.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| 삭제 대상 선정(`deletable`) | CLI (`prune.py`) | — | L-02 · SAFE-06. 웹은 산출물만 읽는다 |
| 백업 · 재조회 · DELETE 루프 | CLI | — | 되돌릴 수 없는 쓰기는 검증된 코드에서만 |
| 상한(8000) | API(웹 라우트) | CLI `--max-items` | 서버가 거부 + CLI 가 2차 거부(전량 거부, 자르지 않음) |
| 건수 타이핑 · 24h · 멱등 | API (`routes/prune.py`) | Browser(입력칸) | 서버가 다시 센 값과 대조 — 화면 값을 믿지 않는다 |
| 잡 잠금 · 고아 정리 · 감사 로그 | API (`webapp/jobs.py`) | Storage(SQLite·JSONL) | 모든 쓰기 kind 공용 |
| 미리보기/결과 표 렌더링 | Browser (Tabulator) | API(JSON 산출물 투영) | 수천 행 → 가상 DOM |
| 정지사유·정지배지 | CLI (`ads_rules.classify` 필드 보강) | API(`board.fold_products` 투영) | 판정값은 CLI 가 만든다 |
| 오판정 표시 | API (POST → JSONL append) | Browser(버튼) | 사람 판단 기록 — 재생성 불가라 캐시가 아니라 기록 |

## Standard Stack

### Core (전부 기존 — 신규 설치 0)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.141.1 | 라우트 | `.venv-web` 에 설치·확인 `[VERIFIED: .venv-web python -c]` |
| sse-starlette | 3.4.11 | 진행 로그 SSE | 기존 `get_job_stream` 재사용 |
| Tabulator | 6.5.3 (vendor) | 미리보기·결과 수천 행 | `webapp/static/vendor/tabulator-6.5.3.min.js` 실존 |
| htmx | 2.0.10 (vendor) | 조각 갈아끼우기 | 실존 |
| stdlib `sqlite3` / `json` | 3.12 | 잡 레지스트리 · JSONL | 스택 결정 |
| `/usr/bin/caffeinate` | macOS | 절전 방지 | 실존 `[VERIFIED: ls]` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | `.venv-web` / `.venv` 각각 | 테스트 | 웹(약 1,000개·15초) / CLI(37개·0.02초) |

**Installation:** 없음.

## Package Legitimacy Audit

이 페이즈는 외부 패키지를 **하나도 설치하지 않는다**. 모든 의존은 이미 `.venv-web`·`.venv`·`webapp/static/vendor/` 에 있다. slopcheck 대상 없음.

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
[보드: 회차 선택 + "꺼진 소재 정리 미리보기 — 쓰기 0" 버튼]
        │ POST /jobs/prune/preview {run_dir, accounts?}
        ▼
[routes/prune.py] ── prep 잡이 같은 회차에서 도는 중? → 409
        │ create_job("prune_preview")  (WRITE 아님 · SINGLETON)
        ▼
[subprocess] run_ads.py prune --run-dir R [--account …] --preview-out web/prune_preview_<id>.json --backup-tag <id>
        │  ads.json(스냅샷) → deletable() → backup_paused(태그) → (dry-run 종료)
        ▼
[web/prune_preview_<id>.json]  {accounts:{alias:{targets[],keep{},paused,deletable,backup,aborted?}}, adIds[], total}
        │ GET /jobs/<id>/result  → 계정별 접힘 요약 + Tabulator 전 행 + 상한초과 표시
        ▼
[사람: 건수 타이핑]  POST /jobs/prune/commit {preview_job_id, typed_count}
        │ 부모 kind/done·0 · 24h · 성공 커밋 자식 없음(409) · total ≤ prune_max_items · typed == total
        ▼
[create_job("prune_commit", targets_path_override = 미리보기 산출물)]  (WRITE_KINDS · caffeinate -i)
        ▼
[subprocess] caffeinate -i … prune --commit --only-ads <미리보기 산출물> --account <대상 있는 계정들>
             --max-items N --preview-out web/prune_result_<id>.json --backup-tag <id>
        │ 계정마다: deletable(ads) ∩ only → backup(실패→aborted, 0건) → fetch_ads 재조회
        │           (0건→recheck_failed) → revived_filter + excluded_reasons → delete_ads(items 수집)
        ▼
[web/prune_result_<id>.json]  계정별 items[성공/실패/이미없음] · excluded[{adId,사유}] · new_since_preview · aborted
        │                                   │
        ▼                                   ▼
[결과 표 + "실패분만 재시도" (실패 N 타이핑)]   [jobs._finish → audit.jsonl 1줄 (커밋 후)]
        │ POST /jobs/prune/retry {commit_job_id, typed_count}
        └─▶ 실패 adId ∩ 미리보기 adId → 새 targets 파일 → prune_commit (parent = 원 미리보기)
```

### Recommended Project Structure (신규·수정 파일)
```
.claude/skills/naver-ads-weekly/scripts/
├── prune.py          # 수정: only_ads·items·tag 인자, excluded_reasons(), 무플래그 불변
├── run_ads.py        # 수정: prune 서브파서에 --only-ads/--preview-out/--max-items/--backup-tag
├── ads_rules.py      # 수정: ⑥ 행에 statusReason·editTm·(선택) productLive
├── test_prune.py     # 확장
└── test_ads_rules.py # 확장 (BOARD-05 고정)
webapp/
├── jobs.py           # 수정(공유): KINDS·JobKind·WRITE_KINDS·SINGLETON·caffeinate·_build_argv·
│                     #   create_job(prune 분기·멱등)·_finish 감사훅·reap_on_startup·롤백 버그
├── argv.py           # 수정(공유): AdsArgv.subcommand 에 "prune", max_items·backup_tag 필드
├── audit.py          # 신규: append-only JSONL + kind 별 요약 추출
├── settings.py       # 수정: prune_max_items(8000)·audit_path 키
├── flow.py           # 수정: 중단사유에 recheck_failed 라벨
├── main.py           # 수정(공유): lifespan reap · prune 라우터 include
├── board.py          # 수정: ⑥ 사유 집계·광고정지 배지·오판정 표식 투영
├── routes/prune.py   # 신규(트랙): preview/commit/retry + 결과표 dict
├── routes/board.py   # 수정: misjudged POST 라우트 + GET / 에 표식 주입
├── routes/jobs.py    # 수정(공유): get_job_result 트랙 병합 목록에 prune 추가
├── templates/_prune_preview_table.html  # 신규
├── templates/_prune_result_table.html   # 신규
├── templates/board.html                  # 수정(공유): <section id="prune"> · 배지/오판정 컬럼은 board.js
├── static/prune.js   # 신규(트랙): window.관제탑 훅만 사용
└── tests/
    ├── test_prune_cli.py      # 신규: subprocess dry-run(네트워크 0) + in-process 커밋(monkeypatch)
    ├── test_routes_prune.py   # 신규: test_routes_coupang.py 복제
    ├── test_audit.py          # 신규
    ├── test_jobs.py           # 확장: 기동 reap · 멱등 · 롤백 버그 회귀
    └── test_board.py          # 확장: 배지 · 사유 · 오판정
```

### Pattern 1: CLI 주입구 — `cmd_bids` 의 쌍둥이로 (L-02)
**What:** `cmd_prune` 이 `run_prune` 반환값을 모아 `_dump_preview()`(이미 원자적 쓰기) 로 쓴다. `_load_only_ads()` 는 `{"adIds":[…]}` 모양을 이미 받으므로 **미리보기 산출물에 최상위 `adIds` 를 넣으면 그 파일 자체가 `--only-ads` 입력이 된다** — 커밋이 "미리보기가 쓴 바로 그 파일"을 넘긴다(SAFE-06·FLOW-02, 서버가 목록을 재가공하지 않음).
**무플래그 불변:** 플래그 없으면 `only_ads=None`, `items=None`, `tag=None` → 기존 경로 그대로, 종료코드 0 그대로.
**Example (설계 — 기존 시그니처 확장, 기본값으로 불변):**
```python
# prune.py — 기존 함수에 키워드 인자만 추가한다 (기본값 = 기존 동작)
def run_prune(acct, run_dir, commit=False, log=print, only_ads=None, tag=None, collect_items=False):
    ...
    tgt = deletable(ads)
    if only_ads is not None:                     # 미리보기 대상 ∩ (본 것보다 많이 지우지 않는다)
        tgt = [a for a in tgt if a["nccAdId"] in only_ads]
    ...
    bk = backup_paused(acct, ads, backup_root, tag=tag)   # tag 있으면 파일명에 붙인다

def excluded_reasons(target_ads, fresh_ads):
    """revived_filter 가 뺀 소재별 사유. 순수 함수 — revived_filter 반환형은 안 바꾼다(기존 테스트)."""
    fresh = {a["nccAdId"]: a for a in fresh_ads}
    out = {}
    for a in target_ads:
        f = fresh.get(a["nccAdId"])
        if f is None:
            out[a["nccAdId"]] = "재조회에_없음"      # 이미 삭제됐거나 그 광고그룹 조회가 실패했다 — 단정 금지
        elif f.get("enable"):
            out[a["nccAdId"]] = "다시_켜짐"
        elif f.get("statusReason") not in DELETE_REASONS:
            out[a["nccAdId"]] = f"사유_바뀜:{f.get('statusReason')}"
    return out
```
`delete_ads` 는 반환형(`dict(stat)`)을 바꾸지 말고 `items=None` 리스트 인자를 받아 `{"adId","status","결과":"성공|이미없음|실패|재시도소진","err"}` 를 append 하게 하라 — 기존 테스트가 `stat.get("ok")` 를 본다 `[VERIFIED: test_prune.py]`.

### Pattern 2: `--preview-out` 스키마 (권장)
```json
{
  "generated": "2026-10-01T…",
  "mode": "dry-run | commit",
  "limit": 8000,
  "total": 860,
  "adIds": ["nad-…", "…"],
  "accounts": {
    "<alias>": {
      "paused": 201, "deletable": 195, "keep": {"AD_DISAPPROVED": 5, "AD_UNDER_REVIEW": 1},
      "backup": "/…/paused-backup/paused_<alias>_<date>_<tag>.json",
      "aborted": null,
      "targets": [{"adId": "nad-…", "adgroupId": "grp-…", "adGroup": "판매상품_6-2_…",
                   "mallProductId": "…", "title": "…", "statusReason": "AD_ABNORMAL_INTERLOCK",
                   "editTm": "…", "regTm": "…"}],
      "result": {"ok": 0, "already": 0},          // commit 만
      "items": [{"adId": "…", "결과": "성공|이미없음|실패|재시도소진", "status": 204, "err": null}],
      "excluded": [{"adId": "…", "사유": "다시_켜짐|사유_바뀜:…|재조회에_없음"}],
      "new_since_preview": 3                         // 재조회 deletable 중 대상 파일에 없던 것 — 안 지움
    }
  }
}
```
- **캠페인명은 스냅샷에 없다** — `ads.json` 의 `groups` 는 `{name, bidAmt}` 뿐이고 소재에 캠페인 id 도 없다 `[VERIFIED: ads.json 키 목록]`. D-01 의 "캠페인" 컬럼은 빼거나(권장 — 광고그룹명의 `NN-N` 이 불사자 조인 키라 그것으로 충분) `collect.fetch_ads` 가 그룹에 캠페인명을 같이 저장하도록 확장해야 한다(prep 산출물 변경 → 다음 수집부터).
- **"정지일" 필드는 API 에 없다.** `editTm`(마지막 변경시각)이 연동끊김 시스템 변경 시각의 근사다. 컬럼명을 "마지막 변경"으로 정직하게 달아라.
- `adIds` 는 계정 경계를 넘어 하나의 목록이다. `--only-ads` 는 집합 필터라 계정 섞여도 안전하다(각 계정은 자기 deletable ∩ 집합만 본다).

### Pattern 3: 웹 kind 2종 + 트랙 라우터 (쿠팡 복제)
| kind | WRITE_KINDS | SINGLETON | caffeinate | result_path | targets_path |
|------|------|------|------|------|------|
| `prune_preview` | ✗ (광고 쓰기 0. 백업 파일만 씀) | ✓ (8MB×7 읽기 중복 방지) | ✗ (수 초) | `web/prune_preview_<id>.json` | 없음 |
| `prune_commit` | ✓ | — | ✓ (8,000건 ≈ 20~40분) | `web/prune_result_<id>.json` | 미리보기 산출물(override) 또는 재시도 대상 파일 |

- `JobKind` Literal 과 `KINDS` 튜플을 **같이** 고친다(주석 경고 `[VERIFIED: jobs.py:65-67]`).
- `_build_argv` 에 prune 분기: `prune_commit` 인데 `targets_path is None` 이면 **ValueError** — 빈 값이 전량으로 해석되는 경로를 여기서 터뜨리는 기존 관례(`revert_only` 와 같은 부류).
- `AdsArgv.subcommand` Literal 에 `"prune"` 추가, `max_items: int|None`·`backup_tag` 필드 추가(`build()` 가 조건부로 붙임). `test_모르는_서브커맨드는_조립되지_않는다` 는 그대로 통과한다.
- 라우트는 `routes/coupang.py` 의 `post_coupang_commit` 6단계를 그대로 따른다: ① 부모 kind/LIVE(409)/done·0(400) ② 24h(400) ③ 성공 자식 있음 → **409**(D-09; 쿠팡은 400 이었다 — 의도적 차이) ④ 산출물 읽기(깨짐 400) ⑤ `total > prune_max_items` → 400 ⑥ `typed_count != total` → 409 ⑦ `_상세잡만들기("prune_commit", run_dir=…, accounts=[대상>0 계정], parent_job_id=…, targets_path_override=산출물, max_items=…)`.
- **`--account` 를 대상 있는 계정으로 명시해라.** 안 주면 `cmd_prune` 이 `prepped ∪ 자격증명` 전부를 돌아 대상 0 계정도 백업을 다시 쓴다(무해하지만 소음·시간).
- 결과표 등록: `routes/prune.py` 에 `결과표 = {"prune_preview": (...), "prune_commit": (...)}` 를 두고, `routes/jobs.get_job_result` 의 트랙 병합 루프(`for 트랙표 in (_썸네일트랙.결과표, _쿠팡트랙.결과표)`)에 한 항목 추가 `[VERIFIED: routes/jobs.py:2119-2122]`.
- `create_job` 의 kind 별 파라미터 검사(`max_items 는 마켓 반영 전용이다` 등)가 있으니 **prune 용 인자는 새 이름**(`prune_max_items`)으로 받거나 검사 조건을 넓혀라 — 그대로 `max_items=` 를 넘기면 ValueError 로 400 이 난다 `[VERIFIED: jobs.py:1178]`.

### Pattern 4: 실패분만 재시도 (FLOW-06)
**권장:** `POST /jobs/prune/retry {commit_job_id, typed_count}` → 서버가 커밋 산출물 `items` 중 `결과 ∈ {실패, 재시도소진}` 인 adId ∩ 원 미리보기 `adIds` 를 `only_ads=` 로 새 targets 파일에 쓴다(CLI 산출물 두 개에서만 유도 — 브라우저 목록 아님). `typed_count == len(그 목록)`. 같은 `prune_commit` kind, `parent_job_id` = **원 미리보기 id**(24h·멱등 판정이 미리보기 기준으로 일관).
**D-08 문자 그대로(같은 미리보기 파일 재사용)도 안전하다** — 진행 파일이 성공 건을 건너뛴다. 다만 재조회가 진행 파일보다 **먼저** 돌기 때문에(이미 지운 소재는 재조회에 없음) 성공했던 수천 건이 전부 `excluded: 재조회에_없음` 으로 결과 표를 뒤덮는다. 그래서 부분집합 파일을 권장한다(진행 파일은 2차 방어로 그대로 남는다).
**멱등 예외:** 재시도 경로는 "성공 커밋 자식 있음" 409 를 건너뛰되, **재시도 잡이 도는 중이면 409**, 실패 0건이면 400.

### Pattern 5: 공용 안전 계약 (jobs.py)
- **멱등(ENG-04):** `create_job` 트랜잭션 안에서 `kind == "prune_commit"` 이고 재시도 표시가 없으면 `SELECT 1 FROM jobs WHERE parent_job_id=? AND kind=? AND status='done' AND exit_code=0` → 있으면 `BusyError` 계열(409). 라우트 검사만으로는 두 탭 동시 POST 창이 남는다 — DB 트랜잭션 안에서 봐야 한다(SINGLETON 가드와 같은 논리 `[VERIFIED: jobs.py:1254-1270 주석]`). 다른 커밋 kind 소급 여부는 Deferred("다른 버튼 소급") 와 충돌하므로 **prune 에만** 걸어라.
- **기동 reap(ENG-05):** `jobs.reap_on_startup()` — DB 파일이 없으면 아무것도 안 함(만들지 않음), 있으면 `BEGIN IMMEDIATE; _reap; COMMIT`, 정리 건수를 `print(..., flush=True)`. lifespan 의 `yield` 전에 호출. try/except 로 감싸 기동 실패로 번지지 않게.
- **감사 로그(FLOW-07):** 종료 지점은 정확히 3곳 — `_finish`(정상 종료), `_reap` 의 orphaned 분기, `create_job` 의 spawn 실패 분기(`failed/-1`). **롤백되는 트랜잭션 안에서 파일을 쓰지 마라**(§함정 2). 권장 구현: `_finish`/orphaned 에서 `_PENDING_AUDIT.append(job_id)` 만 하고, 각 호출부가 `cx.commit()` 직후 `audit.flush(pending)` 을 부른다. 또는 더 단순하게 — `create_job` 의 `_reap` 을 **별도 커밋된 짧은 트랜잭션으로 분리**해 롤백 경로를 없앤 뒤 `_finish` 안에서 바로 쓴다. 둘 다 `kind in WRITE_KINDS` 일 때만.
- 감사 줄 요약은 kind 별 추출 표(`audit.py`): `prune_commit` → 산출물 items 집계(성공/실패/제외), `bids_commit` → `flow.result_counts`, `detail_submit/poll` → summary `집계.실제크레딧`, 나머지 → 대상수만·성공/실패 `null`(**0 으로 지어내지 마라** — "0건 성공"과 "모름"은 다르다). 추출 실패는 삼키고 `{"요약오류": "예외이름"}` 만 남긴다.

### Pattern 6: 결과 표 (D-06 보고)
`flow.aborted_accounts` 재사용 + `중단사유` dict 에 `"recheck_failed": "재확인 조회가 0건/실패 — 인증 만료·방화벽 가능성. 이 계정은 지우지 않았다"` 추가 `[VERIFIED: flow.py:329-333 에 backup_* 만 있음]`. 정렬은 실패·제외가 위(`result_rows` 의 T-1-37 관례).

### Pattern 7: BOARD-05 — 정지사유·광고정지 배지
- `ads_rules.classify` 의 ⑥ 행만 `dict(info_of(a), statusReason=a.get("statusReason"), editTm=a.get("editTm"))` 로 보강. `ad_info` 자체를 바꾸면 ①~⑤ 행까지 커져 result.json(현재 2.2MB)이 불어난다.
- **"상품의 소재가 전부 정지"는 result.json 만으로 판정할 수 없다.** 규칙 어디에도 안 걸린 게재중 소재는 result.json 에 없기 때문이다. 2026-09-20 회차 실측에선 정지 소재를 가진 상품이 게재중 소재를 동시에 가진 경우가 4계정 0건이었다 `[VERIFIED: ads.json 교차 집계]` — 상품당 소재 1개 구조. 그래도 구조적 보장은 없으니 ⑥ 행에 `productLive: bool`(같은 계정·같은 mallProductId 의 게재중 소재 존재)을 CLI 가 실어라(`classify` 는 전 소재를 받으므로 순수 함수로 계산 가능). 보드 배지 = 상품이 ⑥ 소재를 갖고 그 ⑥ 행들이 전부 `productLive == false`. 필드가 없는 옛 result.json 이면 **배지를 안 붙이고 "판정 다시(run)" 안내** — 추정해서 붙이지 않는다.
- result.json 은 `run` 잡(디스크만, 초 단위)으로 재생성된다 — 새 필드는 그 뒤에야 보인다.
- 테스트 고정: 꺼진 소재에 30일 통계(clk≥20·imp≥100·구매)가 있어도 ②③④⑤ 어디에도 안 들어간다 — **현재 이 테스트가 없다** `[VERIFIED: test_ads_rules.py 테스트 목록]`.

### Pattern 8: BOARD-06 — 오판정 1클릭
- `POST /board/misjudged {run_dir, key, rule, memo?, on: bool}` (Pydantic `extra="forbid"`, `key` 는 기존 `보드키` 패턴, `rule` 은 `RULE_ORDER` 기호 1~6자, memo 길이 상한). 서버가 `board.fold_products(result)` 로 그 key 행이 실제로 있는지 확인 후 `<run-dir>/misjudged.jsonl` 에 `{"시각","규칙","상품키","메모","on"}` append(`open("a")` 한 줄 write — 1인·작은 줄이라 원자적 append 로 충분).
- `GET /` 는 파일을 읽어 key 별 **최신 줄**만 반영해 행에 `오판정: true|false` 를 싣는다(`join.attach` 와 같은 "투영에 얹기" 위치 `[VERIFIED: routes/board.py:354-360]`). `fold_products` 는 고치지 않는다.
- 클라이언트: Tabulator 컬럼 1개(버튼 formatter) → `window.관제탑.요청()` → 성공 시 `row.update({오판정: …})`. 서버 왕복 후에만 표식.
- **GET 에서 쓰지 않는다** — `security_curl.sh` V-SAFE-01d 가 GET 본문을 기계 검사한다.

### Anti-Patterns to Avoid
- **웹에서 `deletable` 재계산:** ads.json 을 웹이 열면 L-02·SAFE-06 위반이고, `board.py` 는 원본 덤프를 열지 않는다는 grep 가드가 있다 `[VERIFIED: board.py 독스트링]`.
- **상한 초과 시 앞에서 N건 자르기:** "본 것 ≠ 실행된 것"이 된다. 초과면 전량 거부 + 계정을 나눠 미리보기(`accounts` 필드)하게 안내.
- **`typed_count` 를 대상 파일 길이가 아닌 화면 수로 검증:** 서버가 산출물에서 다시 센다.
- **테스트에 `--commit` 리터럴:** `no_commit_guard.sh` 가 막는다. `"--" + "commit"` 간접 조립 또는 `commit=True` 키워드로.
- **subprocess 로 `prune` 커밋을 띄우는 테스트:** 실제 자격증명(`~/.eroom/naver-ads.json`)으로 진짜 DELETE 가 나간다. 커밋 경로 테스트는 반드시 **in-process + `prune.nvad.call`/`prune.collect.fetch_ads` monkeypatch**(기존 `test_prune.py` 방식).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| 삭제 대상 판정 | 웹 쪽 필터 | `prune.deletable()` | SAFE-06 · L-02 |
| 재조회·교집합 | 웹 재조회 | `collect.fetch_ads` + `revived_filter` | 빈 결과=인증만료 함정(Minor 3)까지 이미 처리 |
| DELETE 재시도·레이트리밋 | 새 루프 | `prune.delete_ads` | 429/5xx 4회 백오프, 진행 파일 재개, 5,062건 무429 실측 |
| 원자적 JSON 쓰기 | 새 헬퍼 | `run_ads._dump_preview` · `jobs._write_json_atomic` | tmp→os.replace 이미 있음 |
| 잡 가드·SSE·로그 tail | 새 엔진 | `jobs.create_job` · `logtail` | Phase 1~7 검증 |
| 건수 확인 409 · 24h | 새 규칙 | `routes/coupang.py` 패턴 · `_미리보기유효시간` · `_경과초` import | 이미 테스트 25개로 고정 |
| 계정 목록 | 하드코딩 | `run_ads.py accounts` / result.json | L-04 |

**Key insight:** 이 페이즈의 위험은 "삭제 로직이 틀리는 것"이 아니라 "검증된 로직 바깥의 접착부(파일명·트랜잭션·테스트 격리)가 조용히 틀리는 것"이다. 새 코드는 접착부에만 쓰고, 거기에 테스트를 집중하라.

## Runtime State Inventory

(리네임 페이즈는 아니지만 되돌릴 수 없는 쓰기라 런타임 상태를 점검했다)

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `~/python_work/data/naver-ads/paused-backup/` — 옛 수동 실행 파일(`delete_progress.jsonl` 5,062줄, `delete_progress_<alias>_20260830.jsonl`, `paused_<alias>_20260829.json`, `interlock_*.json`). 현행 코드 파일명(`delete_progress_<alias>.jsonl`)은 **아직 없음** — 첫 웹 실행이 새로 만든다 | 없음(옛 파일은 손대지 않는다. 현행 코드는 그것들을 읽지 않는다 — 이름이 다르다) |
| Live service config | 네이버 검색광고 7계정의 꺼진 소재. 2026-09-20 스냅샷 기준 연동끊김 860건(cy728 16 · cy7728 6 · dldmswl1986 18 · level_up_ad 236 · milky-way1992 353 · ownway1 36 · pogeunae 195) + 보존(거부 15·검수중 1) `[VERIFIED: ads.json 집계]` | 실탄 전 `prep` 로 새로 수집 권장(스냅샷 11일 경과) |
| OS-registered state | 운영 uvicorn 이 지금 떠 있다(pid 45857, `--reload` 없음, 127.0.0.1:8765) `[VERIFIED: lsof]` | 파이썬 변경 후 **수동 재시작 필수**(재시작해야 lifespan reap·새 라우트가 뜬다) |
| Secrets/env vars | `~/.eroom/naver-ads.json` — CLI 만 읽음. 웹은 `run_ads.py accounts` 로 alias 만 | 없음 |
| Build artifacts | `webapp.db` 현재: done 67 · failed 4 · orphaned 4 · running 0 `[VERIFIED: sqlite3]` | 기동 reap 은 현 상태에 영향 없음(running 0) |

## Common Pitfalls

### Pitfall 1: 같은 날 백업 파일 덮어쓰기 → 지운 소재의 백업 소실 (SAFE-04 구멍)
**What goes wrong:** `backup_paused` 는 `paused_<alias>_<오늘>.json` 을 **덮어쓴다**. 커밋으로 소재 A 를 지운 뒤, 같은 날 같은 회차 이름(웹 `prep` 기본 회차는 오늘 날짜)으로 재수집하면 새 ads.json 에 A 가 없다 → 같은 날 재시도/재미리보기가 백업을 A 없이 다시 쓴다 → **A 를 재등록할 정보가 사라진다.**
**Why:** 백업 단위가 날짜이고 병합이 없다(bids 는 `before_bids` 를 병합하는데 prune 은 안 한다) `[VERIFIED: prune.py:63]`.
**How to avoid:** `--backup-tag <잡id>` 주입구 → `paused_<alias>_<날짜>_<tag>.json`. 무플래그는 기존 이름 그대로. 웹은 항상 잡 id 를 넘긴다. 테스트: 같은 날 두 번 커밋해도 첫 백업 파일이 남는다.
**Warning signs:** paused-backup 에 같은 alias·날짜 파일이 1개뿐인데 진행 파일 성공 줄이 백업 행보다 많다.

### Pitfall 2: 롤백되는 가드 트랜잭션 안의 `_finish` (기존 잠복 버그 + 감사 중복)
**What goes wrong:** `create_job` 은 `BEGIN IMMEDIATE → _reap(cx) → 가드 → … → INSERT → commit`. `_reap` 이 끝난 잡을 `_finish`(UPDATE + `_PROCS.pop`) 한 뒤 가드가 `BusyError`/`ValueError` 를 던지면 **commit 없이 close → UPDATE 롤백**, 그런데 `_PROCS` 는 이미 비었고 `Popen.poll()` 이 자식을 거뒀으므로 다음 `_reap` 은 그 잡을 `orphaned`(종료코드 소실)로 찍는다. 감사 줄을 `_finish` 에서 바로 쓰면 첫 줄(done) + 다음 줄(orphaned) 이 **둘 다** 남는다.
**Why:** `[VERIFIED: jobs.py:1239-1252, 465-469]`.
**How to avoid:** `_reap` 을 가드 트랜잭션 **밖의 별도 커밋 트랜잭션**으로 먼저 돌리고(가드 안에서는 다시 안 부르거나, 불러도 그 사이 끝난 것만), 감사 기록은 커밋 이후에. 회귀 테스트: 끝난 쓰기 잡이 있는 상태에서 BusyError 로 거부된 `create_job` 뒤에도 그 잡이 `done/코드` 이고 감사 줄이 1개.

### Pitfall 3: lifespan reap 이 테스트 중 실제 `webapp.db` 를 건드린다
**What goes wrong:** `client` 픽스처가 `TestClient(app)` 에 들어가는 순간 lifespan 이 돈다. `화면` 픽스처는 **그 뒤에** `settings.DB_PATH` 를 tmp 로 바꾼다 `[VERIFIED: conftest.py:161-178, test_routes_jobs.py:29-34]`. 그래서 기동 reap 은 저장소 루트의 진짜 `webapp.db` 를 연다. 운영 서버가 잡을 막 끝낸 직후(아직 폴링 전)에 테스트를 돌리면 테스트 프로세스엔 `_PROCS` 가 없으므로 그 잡을 `orphaned` 로 찍어 종료코드를 지운다. 감사 로그도 진짜 데이터 루트에 쓰인다.
**How to avoid:** conftest 에 **autouse** 픽스처로 `CT_DB_PATH`·감사 경로를 tmp 로 고정(lifespan 이전) — 또는 `reap_on_startup` 이 `CT_SKIP_STARTUP_REAP=1` 이면 건너뛰게 하고 conftest 가 켠다. 감사 경로는 `settings` 키 + `CT_AUDIT_PATH` 환경변수 오버라이드로 만들어 테스트가 항상 tmp 를 쓰게. 검증: 테스트 전후 `sqlite3 webapp.db 'select count(*), max(ended_at) from jobs'` 불변, `~/python_work/data/control-tower/` 미생성.

### Pitfall 4: PID 재사용 — 재부팅 뒤 "영원히 running"
**What goes wrong:** 맥북 재부팅 후 옛 잡의 pid 를 다른 프로세스가 쓰면 `_alive()` 가 참 → 그 행이 `running` 으로 남아 **전역 쓰기 가드를 영원히 잡는다**("아무것도 안 도는데 409").
**How to avoid (권장):** `reap_on_startup` 에서만 추가 검사 — `ps -o lstart= -p pid` 의 프로세스 시작시각이 잡 `started_at` 보다 늦으면 남의 프로세스 → `orphaned`. 또는 `ps -o command=` 에 `run_ads.py`/잡 argv[실행파일]이 없으면 남의 것. 일반 `_alive` 는 건드리지 마라(좀비 규칙 등 이미 섬세하다). `[ASSUMED]` — 실제 발생 빈도는 미측정, 비용 대비 가치는 MEDIUM.

### Pitfall 5: D-06 "재조회가 늘면 exit 5" 는 발동할 수 없다
**What:** `revived_filter` 는 `target ∩ fresh_deletable` 이라 결과가 대상보다 커질 수 없다 `[VERIFIED: prune.py:31-41]`. 대신 새로 꺼진 소재(fresh deletable − 대상)는 **조용히 안 지워진다**.
**How to handle:** exit 5 를 구현하지 말고(죽은 코드) `new_since_preview` 건수를 결과 표에 "미리보기 이후 새로 꺼진 N건 — 이번엔 안 지움, 다음 미리보기에서" 로 보이고, "대상 파일에 없는 adId 에는 DELETE 가 0회" 를 테스트로 고정하라. 이게 D-06 의 의도("본 것보다 많이 지우지 않는다")의 실제 보장이다.

### Pitfall 6: "재조회에 없음" 을 "이미 삭제됨" 으로 단정
**What:** `fetch_ads` 는 광고그룹별 GET 이 실패해도 그 그룹을 조용히 건너뛴다 `[VERIFIED: collect.py:36-43]` → 그 그룹 소재가 전부 "재조회에 없음"이 된다. 삭제 0건이라 안전하지만 화면이 "이미 삭제됨"이라 말하면 오독이다.
**How to avoid:** 사유 문구를 "재조회에 없음(이미 삭제됐거나 조회 실패)"으로. 진행 파일에 성공 기록이 있는 adId 만 "이전 실행에서 삭제됨"으로 구분 가능.

### Pitfall 7: prep 이 같은 회차를 쓰는 동안 미리보기가 반쪽 ads.json 을 읽는다
**What:** `collect_account` 는 ads.json 을 `write_text` 로 직접 쓴다(원자적 아님) `[VERIFIED: collect.py:77]`. `prune_preview` 는 WRITE 가 아니라 전역 가드에 안 걸린다 → 반쪽 JSON → 그 계정 "소재 읽기 실패" → 미리보기에서 계정이 통째로 빠진다(대상이 적게 보임 — 안전 방향이지만 오독).
**How to avoid:** 미리보기 라우트가 같은 run_dir 의 `prep` 잡이 LIVE 면 409. 산출물에서 `{}` 계정은 `flow.read_preview` 의 `blind` 처럼 "못 읽음"으로 따로 표시.

### Pitfall 8: 수천 건 DELETE 시간 · 절전 · 감시
**What:** `0.08s` sleep + HTTP ≈ 건당 0.2~0.3초 → 8,000건 ≈ 25~40분 `[ASSUMED: 건당 지연 미측정, 2026-08-29 5,062건 성공 실적만 있음]`. 계정별 재조회도 광고그룹 수만큼 GET(수백 회).
**How to avoid:** `prune_commit` 을 `_수면방지_프리픽스` 목록에 추가(ENG-06 은 이 한 줄). 진행 로그는 250건마다 찍힌다 → SSE 로 보인다. 메모리 `never-launch-without-watcher`: 실탄 실행 시 완료 감시를 같이 띄워라(플랜의 human checkpoint 태스크에 명시).

### Pitfall 9: 서버 재시작 안 하면 새 코드가 안 뜬다
운영 uvicorn 은 `--reload` 없이 떠 있다. CLI(`prune.py`) 변경은 subprocess 라 즉시 반영되지만 `webapp/*.py`·템플릿 변경은 재시작 전까지 안 보인다(템플릿은 Jinja 캐시). UAT 전에 재시작 단계를 넣고, 재시작 직후 기동 reap 로그 한 줄을 확인하라.

### Pitfall 10: `cmd_prune` 종료코드
지금은 계정이 `aborted` 여도 0 이다. 웹은 "결과는 산출물에서만 읽는다" 원칙이라 문제는 아니지만, **`--preview-out` 쓰기 실패는 1**, **`--only-ads` 깨짐은 1(전량 폴백 금지 — bids 와 같은 문구)**, **`--max-items` 초과는 2(삭제 0, 백업 전 중단)** 를 새로 정해 테스트로 고정하라. 무플래그는 0 유지.

## Code Examples

### 커밋 라우트 뼈대 (쿠팡 복제)
```python
# Source: webapp/routes/coupang.py:139-189 (post_coupang_commit) 를 prune 으로 옮긴 형태
class PruneCommitReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preview_job_id: JobId
    typed_count: StrictInt = Field(ge=0)

@router.post("/jobs/prune/commit")
def post_prune_commit(request: Request, req: PruneCommitReq):
    부모 = jobs.job_status(req.preview_job_id)
    if 부모 is None or 부모.get("kind") != "prune_preview":
        raise HTTPException(400, "꺼진 소재 미리보기가 아니다 — 미리보기부터 해라")
    if 부모.get("status") in jobs.LIVE_STATUSES:
        raise HTTPException(409, "미리보기가 아직 도는 중이다")
    if 부모.get("status") != "done" or 부모.get("exit_code") != 0:
        raise HTTPException(400, "미리보기가 정상으로 안 끝났다 — 새 미리보기부터")
    경과 = _경과초(부모.get("started_at"))
    if 경과 is None or 경과 > _미리보기유효시간:
        raise HTTPException(400, "미리보기가 24시간을 넘었다 — 다시 미리보기부터 해라")
    if any(c.get("status") == "done" and c.get("exit_code") == 0
           for c in jobs.children_of(req.preview_job_id, "prune_commit")):
        raise HTTPException(409, "이 미리보기로 이미 삭제했다 — 실패분 재시도나 새 미리보기를 써라")
    문서 = _읽기(Path(부모.get("result_path") or ""))
    if not isinstance(문서, dict) or not isinstance(문서.get("adIds"), list):
        raise HTTPException(400, "미리보기 산출물이 없거나 깨졌다 — 새 미리보기부터")
    합계 = len(문서["adIds"])
    상한 = _삭제상한()                       # settings.cfg("prune_max_items", DEFAULTS[...]) — 한 곳
    if 합계 == 0: raise HTTPException(400, "지울 소재가 0건이다")
    if 합계 > 상한: raise HTTPException(400, f"{합계:,}건 > 상한 {상한:,}건 — 계정을 나눠 미리보기해라")
    if req.typed_count != 합계:
        raise HTTPException(409, f"화면이 본 건수({req.typed_count:,})와 지울 건수({합계:,})가 다르다")
    계정 = sorted(a for a, v in (문서.get("accounts") or {}).items() if (v or {}).get("targets"))
    return _상세잡만들기("prune_commit", run_dir=부모.get("run_dir"), accounts=계정,
                        parent_job_id=req.preview_job_id,
                        targets_path_override=부모.get("result_path"), prune_max_items=상한)
```

### lifespan 기동 reap
```python
# Source: webapp/main.py lifespan (기존 print 두 줄 옆)
try:
    n = jobs.reap_on_startup()          # DB 없으면 0, 있으면 BEGIN IMMEDIATE·_reap·COMMIT
    print(f"[기동] 고아 잡 {n}건 정리", flush=True)
except Exception as e:
    print(f"[기동] 고아 잡 정리 실패 — 서버는 뜬다: {type(e).__name__}", flush=True)
```

### CLI 커밋 경로 테스트 (네트워크 0 · `--commit` 리터럴 0)
```python
# Source: test_prune.py TestRunPruneCommitRechecks 방식
prune.collect.fetch_ads = lambda acct: (fresh_ads, {})
prune.nvad.call = fake_call                    # DELETE 호출 adId 를 모은다
out = prune.run_prune({"alias": "zz1"}, run_dir, commit=True,
                      only_ads={"a"}, tag="job1", collect_items=True)
assert deleted_ids == ["a"]                    # 대상 파일 밖(b·새로 꺼진 c)은 0회
assert out["new_since_preview"] == 1
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| 수동 스크립트로 삭제(`interlock_*.json`·`delete_progress_<alias>_<날짜>.jsonl`) | `prune.py` + `run_ads.py prune`(진행파일 `delete_progress_<alias>.jsonl`) | 2026-08-30 이후 | 옛 진행 파일은 현 코드가 안 읽는다 — 재개 근거로 쓰지 마라 |
| 고아 정리 = 다음 잡 생성 때 지연 | 기동 시 1회 + 지연 | 이 페이즈 | ENG-05 |
| Phase 7 쿠팡의 재커밋 = 400 | prune 은 409(D-09) | 이 페이즈 | 테스트 기대값 주의 |

**Deprecated/outdated:** CLAUDE.md 의 "계정 4개 → 6개 예정" — 실제 7개.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | DELETE 건당 0.2~0.3초 → 8,000건 25~40분 | 함정 8 | 더 길면 감시·caffeinate 필요성만 커짐(이미 붙임) |
| A2 | PID 재사용으로 running 고착이 실제로 일어날 수 있다 | 함정 4 | 안 일어나면 추가 검사가 낭비일 뿐(무해) |
| A3 | 재시도는 "실패 부분집합 파일"이 D-08 문자 그대로보다 낫다 | 패턴 4 | D-08 그대로 가도 안전 — 결과 표 소음만 차이 |
| A4 | 캠페인 컬럼은 빼도 된다(광고그룹명으로 충분) | 패턴 2 | 용팀장이 캠페인을 원하면 `collect.fetch_ads` 확장 + 재수집 필요 |
| A5 | 상한 8000(D-07, 용팀장 확인 필요) | SAFE-07 | 확인 전까지 설정값이라 바꾸기 쉬움 |

## Open Questions

1. **D-07 상한 8000 확정** — CONTEXT 가 이미 "용팀장 확인 필요" 표시. 설정 키라 플랜은 그대로 진행하고 L-01 실탄 checkpoint 에서 같이 묻는다.
2. **캠페인 컬럼(D-01)** — 스냅샷에 없음. 권장: 빼고 광고그룹명 표시. 원하면 prep 확장(별도 소태스크).
3. **오판정 버튼의 "규칙" 값** — 행에 규칙이 여러 개(예 `②③`)일 수 있다. 권장: 그 행의 `rules` 문자열 전체를 기록(판정 근거 데이터라 과기록이 누락보다 낫다). 필터로 고른 규칙을 쓰는 방식도 가능.
4. **ENG-04 멱등을 bids_commit 등에 소급할지** — Deferred("다른 버튼 소급")와 충돌 소지라 prune 만 권장.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `.venv` (CLI) | prune 실행·CLI 테스트 | ✓ | Python 3.12 | — |
| `.venv-web` | 웹·웹 테스트 | ✓ | FastAPI 0.141.1 | — |
| `/usr/bin/caffeinate` | prune_commit | ✓ | macOS | 없으면 안 붙임(기존 로직) |
| sqlite3 CLI | 감사·잡 조회 | ✓ | 3.51.0 | — |
| 네이버 검색광고 API 자격증명 | 실탄 커밋만 | ✓(7계정 설정) | — | 테스트는 전부 목 |
| Playwright CLI(`uat-verifier`) | 화면 UAT | 전역 규칙상 사용 | — | — |
| 운영 uvicorn | UAT | ✓ 실행 중(pid 45857) | — | 변경 후 재시작 필요 |

**Missing dependencies with no fallback:** 없음.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (웹: `.venv-web`, CLI: `.venv`) + CLI 쪽 unittest 스타일 호환 |
| Config file | `webapp/pytest.ini` (`cli/` 수집 제외) |
| Quick run command | `.venv-web/bin/pytest webapp/tests/test_routes_prune.py webapp/tests/test_prune_cli.py webapp/tests/test_audit.py -q -p no:warnings` · `.venv/bin/python3 -m pytest -q .claude/skills/naver-ads-weekly/scripts/test_prune.py .claude/skills/naver-ads-weekly/scripts/test_ads_rules.py` |
| Full suite command | `.venv-web/bin/pytest webapp/tests -q -p no:warnings && .venv/bin/python3 -m pytest -q .claude/skills/naver-ads-weekly/scripts && bash webapp/tests/no_commit_guard.sh && bash webapp/tests/security_curl.sh` (웹 ≈15초 · CLI <1초) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PRUNE-01 | 연동끊김만 · 검수중/거부 제외 · preview-out 대상에도 없음 | unit + CLI subprocess(dry-run) | `.venv/bin/python3 -m pytest -q …/test_prune.py` · `pytest webapp/tests/test_prune_cli.py -k 연동끊김` | test_prune ✅ / test_prune_cli ❌ Wave 0 |
| PRUNE-02 | 백업 실패 → DELETE 0회 · aborted backup_failed · 결과 표 문구 | unit(in-process monkeypatch) + route ctx | `pytest …/test_prune.py -k 백업실패` · `pytest webapp/tests/test_routes_prune.py -k backup` | ❌ Wave 0 |
| PRUNE-03 | preview-out 에 전 계정 전 행(접기 없음) · 한국어 그대로 | CLI subprocess | `pytest webapp/tests/test_prune_cli.py -k preview_out` | ❌ |
| SAFE-04 | 백업 태그로 같은 날 재실행에도 첫 백업 보존 | unit | `pytest …/test_prune.py -k 백업태그` | ❌ |
| SAFE-05 | 재조회 제외 소재별 사유(다시_켜짐/사유_바뀜/재조회에_없음) · 대상 밖 DELETE 0회 · new_since_preview | unit | `pytest …/test_prune.py -k excluded` | ❌ |
| SAFE-06 | 커밋 argv 의 `--only-ads` == 미리보기 result_path · 무플래그 동작 불변 | unit(argv) + CLI | `pytest webapp/tests/test_routes_prune.py -k only_ads` · `pytest webapp/tests/test_prune_cli.py -k 무플래그` | ❌ |
| SAFE-07 | 총계 > prune_max_items → 미리보기 "상한초과" · 커밋 400 · CLI --max-items 초과 exit 2 삭제 0 | route + unit | `pytest … -k 상한` | ❌ |
| FLOW-03 | 24h 초과 미리보기 커밋 400 | route | `pytest webapp/tests/test_routes_prune.py -k 24시간` | ❌ |
| FLOW-06 | 재시도 대상 = 실패 ∩ 미리보기 · typed=실패수 · 실패 0이면 400 | route | `pytest … -k 재시도` | ❌ |
| FLOW-07 | 모든 WRITE_KINDS 종료 1줄 · orphaned 도 1줄 · 롤백 경로 중복 0 · 테스트가 실데이터루트에 안 씀 | unit(jobs+audit) | `pytest webapp/tests/test_audit.py webapp/tests/test_jobs.py -k 감사` | ❌ |
| ENG-04 | 같은 미리보기 두 번째 커밋 409(트랜잭션 안) · 쓰기 잡 동시 409 | unit+route | `pytest webapp/tests/test_jobs.py -k 멱등` | ❌ |
| ENG-05 | 기동 시 죽은 running → orphaned · DB 없으면 미생성 · 테스트 실DB 불변 | unit | `pytest webapp/tests/test_jobs.py -k 기동` | ❌ |
| ENG-06 | prune_commit argv 가 caffeinate -i 로 시작 | unit(argv) | `pytest webapp/tests/test_argv.py -k caffeinate` | 기존 ✅(확장) |
| BOARD-05 | 꺼진 소재 통계는 ②~⑤ 미포함 · ⑥ 행 statusReason · 광고정지 배지(필드 없으면 미표시) | unit(ads_rules) + board | `pytest …/test_ads_rules.py -k 꺼진` · `pytest webapp/tests/test_board.py -k 정지` | ❌ |
| BOARD-06 | POST 오판정 append · 최신 줄 승 · 없는 key 400 · GET 은 쓰기 0 | route | `pytest webapp/tests/test_board.py -k 오판정` · `bash webapp/tests/security_curl.sh` | ❌ |
| UI | 미리보기 표 수천 행 · 접힘 · 타이핑 · 결과/재시도 | e2e(uat-verifier, 목 산출물) | `uat-verifier` 에 UAT 파일 전달 | manual-auto |
| 실탄 | 첫 실제 삭제(건수·계정·샘플 승인) | **사람 승인(L-01)** | — | human checkpoint |

### Sampling Rate
- **Per task commit:** 위 Quick run 두 줄 + `no_commit_guard.sh`
- **Per wave merge:** Full suite
- **Phase gate:** Full suite green + 실DB/실데이터루트 불변 확인(`sqlite3 webapp.db` 카운트 전후 동일, `control-tower/` 는 운영 서버만 생성) → `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `webapp/tests/test_prune_cli.py` — subprocess dry-run(격리 데이터루트, `_격리된_데이터루트` 재사용) + in-process 커밋
- [ ] `webapp/tests/test_routes_prune.py` — `test_routes_coupang.py` 의 `_행박기`·`쿠팡판` 픽스처 복제(`안띄운다` 로 spawn 가짜)
- [ ] `webapp/tests/test_audit.py`
- [ ] conftest autouse: DB·감사 경로 tmp 고정(lifespan 이전) — 함정 3
- [ ] `test_prune.py` 확장(only_ads·tag·items·excluded_reasons·max-items), `test_ads_rules.py` 확장(⑥ 필드·꺼진 소재 통계 배제)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no(로컬 1인, 부팅 토큰) | 기존 `security.guard` |
| V3 Session Management | yes(쿠키·토큰) | 기존 부팅 토큰 + Origin 검사 — 새 POST 3개도 자동 적용 |
| V4 Access Control | yes | 계정은 설정 파일에서만; 커밋은 미리보기 잡 id 만 받음(대상 주입 불가) |
| V5 Input Validation | yes | Pydantic `extra="forbid"`, `JobId`/`보드키`/`Alias` 패턴, `StrictInt`, memo 길이 상한, 경로는 `_override_targets`(web/ 부모 검사) |
| V6 Cryptography | no | — |
| V7 Errors/Logging | yes | 화면에 예외 이름까지만(`flow.read_preview` 관례), 감사 로그에 시크릿·argv 경로 외 비밀 없음 |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| 화면 조작으로 미리보기에 없던 소재 삭제 | Tampering | 커밋 요청에 대상 필드 없음 · CLI 가 `deletable ∩ only_ads ∩ fresh` |
| 교차 사이트 POST 로 삭제 유발 | Spoofing/CSRF | 기존 Origin + X-CT-Token guard |
| 낡은 스냅샷으로 되살아난 소재 삭제 | Tampering | 커밋 직전 재조회(Critical 3) |
| 백업 소실 후 삭제 | Repudiation/손실 | 백업 실패 중단 + 잡별 백업 태그 |
| 이중 클릭·두 탭 이중 실행 | Elevation(중복 쓰기) | WRITE_KINDS 전역 + 트랜잭션 내 멱등 |
| 감사 로그 위·변조 / 누락 | Repudiation | append-only, 종료 지점 3곳 전부 기록, 커밋 후 기록 |
| GET 부수효과로 Origin 우회 | CSRF | 오판정도 POST, `security_curl.sh` V-SAFE-01d |

## Sources

### Primary (HIGH confidence)
- 로컬 코드: `.claude/skills/naver-ads-weekly/scripts/{prune,run_ads,ads_rules,collect,nvad}.py`, `test_prune.py`, `test_ads_rules.py`
- 로컬 코드: `webapp/{jobs,argv,flow,board,settings,main}.py`, `webapp/routes/{jobs,coupang,board}.py`, `webapp/static/board.js`, `webapp/templates/board.html`, `webapp/tests/{conftest,test_cli_patch,test_routes_coupang,test_routes_jobs}.py`, `no_commit_guard.sh`, `pytest.ini`
- 실데이터: `~/python_work/data/naver-ads/runs/2026-09-20/accounts/*/ads.json`(사유 분포·필드·상품 겹침), `paused-backup/*`(5,062+494+1,784건 전부 204), `webapp.db` 상태, `lsof :8765`
- 테스트 실행: 웹 스위트 전부 통과(~15초), CLI 37 passed(0.02초), `no_commit_guard: OK`
- `.planning/phases/02-prune-ads/02-CONTEXT.md`, `REQUIREMENTS.md`, `ROADMAP.md`, `research/PITFALLS.md` §6, `07-thumb-coupang/07-CONTEXT.md` D-01

### Secondary / Tertiary
- 없음 — 이 페이즈는 외부 문서 조회가 필요한 신규 기술이 없다.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — 신규 의존 0, 전부 설치·실행 확인
- Architecture: HIGH — 쿠팡·입찰가 트랙의 실코드 경로를 그대로 따름
- Pitfalls: HIGH(1·2·3·5·6·7·9·10 은 코드 라인으로 확인) / MEDIUM(4·8 은 추정 포함)

**Research date:** 2026-10-01
**Valid until:** 2026-10-31 (코드베이스 내부 사실 — 다음 페이즈가 jobs.py 를 고치면 재확인)
