# Phase 2: 되돌릴 수 없는 쓰기 — 꺼진 소재 정리 - Context

**Gathered:** 2026-10-01 (`--auto` — 용팀장 외출, 추천안 자동 선택. `[auto — 용팀장 확인 필요]` 표시는 돌아오면 확인)
**Status:** Ready for planning

<domain>
## Phase Boundary

보드에 **꺼진 소재 삭제(prune) 버튼**을 붙이고, 그 과정에서 모든 쓰기 버튼이 공유할 **안전 계약**을 완성한다.

- **삭제 트랙 (PRUNE-01~03 · SAFE-04~06 · FLOW-03/06):** 규칙⑥ 중 `AD_ABNORMAL_INTERLOCK` 소재만 전부 나열 → 건수 타이핑 확인 → 백업 성공 뒤에만 삭제 → 실행 직전 재조회로 살아난 소재 제외·보고 → 실패분만 재시도.
- **공용 안전 계약 (ENG-04 · ENG-05 · SAFE-07 · FLOW-07):** 같은 미리보기 중복 실행 차단 · 서버 기동 시 고아 잡 정리 · 건수 상한 · 모든 쓰기 잡 감사 로그(JSONL).
- **보드 (BOARD-05 · BOARD-06):** 정지 소재 실적을 현재 유입으로 안 보이게 증명·표시 · 1클릭 오판정 표시.

범위 밖: 물갈이 재업로드 뒤 광고에 소재를 새로 넣는 일(사람 몫 — 메모리 `naver-ads-interlock-mass-pause`) · 다른 버튼(입찰가·상세·마켓·썸네일·쿠팡)에 재조회·신선도 검사를 소급 적용 · 스케줄 자동화(3단계).

</domain>

<decisions>
## Implementation Decisions

### 🔒 잠긴 제약 (프로젝트·메모리·이전 페이즈 승계 — 플랜이 바꿀 수 없다)

- **L-01: 삭제 `--commit` 은 매번 플랜의 blocking human checkpoint 다** — 첫 회 실탄 실행은 용팀장이 건수·계정·샘플을 보고 승인한 뒤에만. `--auto` 체인·auto_advance 가 자동 승인하지 않는다. 화면에서도 매번 건수 타이핑(아래 D-04).
- **L-02: CLI 재작성 금지.** `naver-ads-weekly` 의 `run_ads.py prune` / `prune.py` 를 subprocess 로 부르고 필요한 건 **주입구 플래그 추가만**(`--preview-out`, `--only-ads`, `--limit` 등). 무플래그 동작 불변. 판정(`prune.deletable`)을 웹앱에 재구현하지 않는다.
- **L-03: 삭제 대상은 `statusReason == AD_ABNORMAL_INTERLOCK` 뿐**(`prune.DELETE_REASONS`). 검수중·거부는 목록에도 안 나온다. 물갈이 부산물이라 수천 건이 정상이다(메모리 — 4계정 7,340건 실적).
- **L-04: 계정은 `~/.eroom/naver-ads.json` 항목 그대로**(현재 4개). 웹앱이 계정을 하드코딩하지 않는다.
- **L-05: 쓰기 잡은 `WRITE_KINDS` 전역 1개 · `caffeinate -i` · 미리보기 잡 id 만 받는 커밋**(Phase 1/5/6/7 패턴). 커밋은 대상을 새로 받지 않는다.

### 삭제 미리보기 (PRUNE-01 · PRUNE-03 · SAFE-06)

- **D-01 [auto]: 미리보기 = `prune` dry-run 에 `--preview-out <json>` 주입구를 붙여 계정별 삭제 대상 전 목록(계정 · 캠페인 · 광고그룹 · 소재id · 상품명/채널상품id · 정지사유 · 정지일)을 쓰고, 웹은 그 파일만 읽어 표로 보인다.**
  · [auto] Q: "대상 목록을 어디서 만드나 — ⓐ CLI dry-run 산출물 ⓑ 웹앱이 ads.json + 규칙 재계산" → **ⓐ** (recommended — L-02, SAFE-06 같은 선정 함수)
  · 표: 계정별 접힘 + 건수 요약 + 전체 펼침. 수천 행이라 Tabulator 가상 렌더링 재사용
- **D-02 [auto]: 미리보기·커밋 모두 같은 `prune.deletable()` 을 탄다(SAFE-06). 커밋은 미리보기 잡 id 만 받고, 미리보기가 쓴 대상 파일을 `--only-ads <file>` 로 넘긴다** — 커밋 시점 CLI 는 그 목록 ∩ 재조회 결과만 지운다.
- **D-03 [auto]: 백업은 미리보기에서도 이미 쓰인다(현 CLI 동작). 커밋은 실행 직전에 백업을 다시 쓰고, 실패하면 그 계정은 0건 삭제 · 사유 `backup_failed` 를 결과 표에 보인다(SAFE-04 · PRUNE-02 · SC-2).**

### 실행 확인 · 신선도 · 재조회 (SAFE-05 · FLOW-03 · SC-1 · SC-3)

- **D-04 [auto]: 커밋은 건수 타이핑 확인 — 쿠팡 패턴 그대로(`typed_count: StrictInt`, 서버가 다시 센 값과 다르면 409).** 복사 영역처럼 접힘·다른 색·버튼 1회.
- **D-05 [auto]: 미리보기 유효기간 24시간 — 지나면 커밋 거부 + "다시 미리보기" 안내(FLOW-03).** 쿠팡 D-12 와 같은 값.
- **D-06 [auto]: 커밋 직전 CLI 가 재조회한다(현 `revived_filter`). 미리보기에 있었는데 지금은 아닌 소재(살아남·이미 삭제됨·사유 바뀜)는 빼고 소재별 사유와 함께 결과 표에 나열한다. 재조회 대상이 미리보기보다 늘면 0건 삭제 · exit 5("다시 미리보기")** — 본 것보다 많이 지우지 않는다.

### 상한 (SAFE-07)

- **D-07 `[auto — 용팀장 확인 필요]`: 1회 삭제 상한 = 설정 `prune_max_items` 기본 8000(전 계정 합), 계정별 상한 없음.** 넘으면 미리보기에서 "상한 초과" 로 표시하고 커밋 거부.
  · 이유: 물갈이 직후 한 계정에서 5,024건이 나온 적이 있다. 입찰가용 계정당 1500 을 재사용하면 정상 정리가 막힌다
  · 크레딧 상한은 이 버튼엔 해당 없음(삭제는 크레딧 0). SAFE-07 의 크레딧 축은 기존 상세·썸네일 `--max-credits` 로 이미 충족 — 감사 로그에 같이 남긴다

### 재시도 (FLOW-06)

- **D-08 [auto]: 결과 표에 실패 건이 있으면 `실패분만 재시도` 버튼 — 같은 미리보기 대상 파일로 커밋을 다시 돌리고, CLI 의 진행 파일(`delete_progress_<alias>.jsonl`)이 성공(200/204/404) 건을 건너뛴다.** 재시도도 건수 타이핑(실패 건수).

### 공용 안전 계약 (ENG-04 · ENG-05 · FLOW-07)

- **D-09 [auto]: 작업 잠금 = 기존 전역 쓰기 1개(`WRITE_KINDS`) 유지 + "같은 미리보기는 한 번만 커밋" 멱등 검사(성공 커밋 자식이 있으면 409, 재시도 경로만 예외).** 대상별 세밀 잠금은 안 만든다 — 사용자 1명 · 동시 쓰기 1개면 충분.
  · [auto] Q: "ENG-04 를 대상별 잠금 테이블로 갈까" → **아니다 — 전역 1개 + 미리보기 멱등** (recommended, 스택 결정 '테이블 3개' 유지)
- **D-10 [auto]: 서버 기동(lifespan) 시 `_reap` 를 한 번 돌려 고아 잡을 `orphaned` 로 정리한다(ENG-05).** 지금은 다음 잡 생성 때만 지연 실행된다.
- **D-11 [auto]: 감사 로그 = `<데이터루트>/control-tower/audit.jsonl` append-only. 모든 `WRITE_KINDS` 잡이 끝날 때 1줄: `{시각, 잡id, 종류, 부모잡id, 계정, 대상수, 성공, 실패, 제외, 크레딧, 종료코드}`.** 크레딧은 CLI 산출물에서 읽을 수 있는 잡만(상세·썸네일 등), 나머지 0. 웹 화면은 만들지 않는다 — 파일 + `sqlite3`/`jq` 로 본다.

### 보드 (BOARD-05 · BOARD-06)

- **D-12 [auto]: 규칙⑥ 행에 정지사유(`statusReason`)를 실어 보드에서 `연동끊김` / `검수중` / `거부` 를 구분해 보인다(`ad_info` 에 필드 추가 — 읽기 전용 보강).**
- **D-13 [auto]: BOARD-05 는 지금 규칙②~⑤가 `live_ads` 만 쓴다는 사실을 테스트로 고정하고, 소재가 전부 정지된 상품 행엔 `광고 정지` 표시를 붙여 과거 클릭을 현재 유입으로 읽지 않게 한다.**
- **D-14 [auto]: 오판정 표시 = 보드 행마다 버튼 1개 → `<회차 run-dir>/misjudged.jsonl` 에 `{시각, 규칙, 상품키, 메모}` append, 행에 표식. 다시 누르면 해제 줄 append(최신 줄이 이긴다).** 판정 결과 자체는 바꾸지 않는다 — 2단계 자동화의 승인 근거 데이터일 뿐.

### Claude's Discretion

- 미리보기 표 컬럼 배치 · 계정 접힘 UI · 결과 표 형식(입찰가 `_result_table.html` 계열 재사용 권장)
- `--preview-out` JSON 스키마 세부, 대상 파일 형식
- 감사 로그 기록 지점(잡 종료 훅 위치)
- 플랜 분할(MVP 수직 슬라이스 — 미리보기 → 커밋 → 재시도 → 공용 계약 → 보드 순 권장)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 요구사항 · 로드맵
- `.planning/ROADMAP.md` §Phase 2 — 목표 · 성공기준 6개
- `.planning/REQUIREMENTS.md` — ENG-04/05, SAFE-04~07, FLOW-03/06/07, BOARD-05/06, PRUNE-01~03
- `.planning/PROJECT.md` — 안전 제약(dry-run 선행 · 견적 · 사람 승인)

### 삭제 CLI (재사용 — 재작성 금지)
- `.claude/skills/naver-ads-weekly/SKILL.md` — prune 사용법 · 연동끊김 처리 원칙
- `.claude/skills/naver-ads-weekly/scripts/prune.py` — `DELETE_REASONS` · `deletable` · `backup` · `revived_filter` · `delete_ads`(진행 파일 재개) · `run_prune`
- `.claude/skills/naver-ads-weekly/scripts/run_ads.py` — `prune` 서브커맨드 인자
- `.claude/skills/naver-ads-weekly/scripts/ads_rules.py` — 규칙⑥ · `ad_info` · `live_ads`

### 웹 패턴 (재사용)
- `webapp/jobs.py` — `WRITE_KINDS` · `SINGLETON_KINDS` · `create_job` · `_build_argv` · `_reap` · `_alive`
- `webapp/routes/jobs.py` — 입찰가 미리보기/커밋(대상 파일 재사용) · 회차 되돌리기 건수 확인
- `webapp/routes/coupang.py` — `typed_count` 409 · 24h 신선도 · 재조회 늘어남 exit 5
- `webapp/flow.py` — `read_preview` · `classify_results` · `result_rows` · `aborted_accounts`
- `webapp/settings.py` — 상한 설정 키 패턴
- `webapp/main.py` — lifespan (D-10 기동 스캔 위치)
- `webapp/board.py` — `fold_products` · `RULE_ORDER`
- `.planning/phases/07-thumb-coupang/07-CONTEXT.md` — D-01(Phase 2 몫으로 남긴 것 목록) · D-12 재조회

### 메모리
- `naver-ads-interlock-mass-pause` — 연동끊김 대량정지는 정상 · 삭제가 정답
- `never-launch-without-watcher` — 장기 잡은 완료 감시 동반

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `prune.py`: 판정·백업·재조회·진행파일 재개가 이미 있다 — 주입구(`--preview-out`, `--only-ads`)만 붙이면 웹이 감싼다
- `flow.aborted_accounts`: 계정별 `aborted` 사유 표시 — `backup_failed`/`recheck_failed` 에 그대로 맞는다
- 쿠팡 커밋 라우트: 건수 타이핑 409 · 24h · 재조회 늘어남 거부 — 거의 복붙 수준
- `jobs._reap`: 고아 정리 로직 완성 — 기동 시 호출만 추가

### Established Patterns
- 미리보기 잡 → 커밋 잡은 부모 id 하나 · 부모 종류/완료/산출물 3단 검사
- 결과는 CLI 산출물 파일에서만 읽는다(종료코드로 추정 금지)
- 상한은 `settings.cfg` 로 매번 읽는다

### Integration Points
- `jobs.py` 에 `prune_preview` / `prune_commit` 종류 등록(`WRITE_KINDS` 에 commit)
- 보드 규칙⑥ 필터 행 → 삭제 미리보기 버튼
- 모든 쓰기 잡 종료 경로 → 감사 로그 1줄

</code_context>

<specifics>
## Specific Ideas

- 2026-08-29~30 수동 실행 실적: 4계정 7,340건 삭제(cy728 38 · cy7728 5,024 · ownway1 494 · pogeunae 1,784) — 상한·표 성능 기준
- 화면 문구는 "꺼진 소재(연동끊김) N건 삭제" — 검수중·거부는 "남김" 으로 따로 센다

</specifics>

<deferred>
## Deferred Ideas

- 다른 쓰기 버튼(입찰가·상세·마켓·썸네일·쿠팡)에 24h 신선도·재조회 소급 — 각 버튼 다음 손볼 때
- 감사 로그 열람 화면
- 대상별 세밀 잠금 테이블
- 물갈이 재업로드 뒤 새 소재 자동 등록
- 오판정 데이터로 규칙 임계치 자동 조정(2단계)

</deferred>

---

*Phase: 02-prune-ads*
*Context gathered: 2026-10-01*
