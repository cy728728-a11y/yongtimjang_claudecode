# UAT 검증 결과: Phase 7 (07-01 · 07-04 · 07-05) — 썸네일 웹 · 쿠팡 웹 슬라이스

- 판정: **FAIL** (항목 9건 중 pass 8 · fail 1 — P1 발견 1건, 나머지는 명세대로 동작)
- 검증한 흐름: (썸네일) 보드 ② 선택 → 견적(크레딧 0) → 실행 승인(web_approval.json) → 결과 표(사용가능·회수대기·제외) / (쿠팡) 후보 뽑기(prep 실패·성공 두 경로) → 접힌 복사 영역 건수 타이핑 → 409(불일치) → 복사 실행 → 결과 표(재조회·중복0·잠금안내) / 보드 버튼·패널 노출 규칙(07-01) / 기존 입찰가·상세 버튼 회귀
- 운영체제: darwin · 브라우저 도구: Playwright CLI (`playwright-cli` 0.1.20, headless, 세션 `uat-07thumbcoupang`)

## 검증 방법 (환경 격리)

`webapp/tests/banner_cdp.sh`·`06-04-uat.md`의 격리 런처 패턴을 따랐다. 실서버(:8765, PID 72246)·실 `webapp.db`·실 `~/python_work/data`·`webapp-banner/*`·실 `workspace.toml`에는 어떤 시점에도 쓰기가 가지 않았다(검증 전/후 diff·mtime으로 확인).

- 포트: 53114(사전 확인 결과 비어 있었음, 종료 후 다시 비어 있음 확인)
- 런처: 세션 scratchpad의 `launcher.py`(1회성, 검증 종료 후 삭제) — 같은 인터프리터 안에서 `webapp.paths.data_root`를 임시 디렉터리로, `webapp.bulsaja_index.profile_path`를 임시 파일로, `settings.cfg("expected_bulsaja_nick", …)`를 가짜 닉으로 교체한 뒤 `uvicorn.run()`을 직접 호출
- **`webapp.jobs.spawn` 완전 대체**: 실제 CLI(`thumb_web.py`·`coupang_web.py`·`run_ads.py`)를 단 한 번도 실행하지 않았다. argv(`--summary-out`·`--inputs`·`--approved`·`--limit`·`--preview-out`)를 파싱해 07-02/07-03/01-08 계약 모양의 summary/commit_summary/preview JSON을 합성해 즉시 쓰고, 항상 즉시 종료하는 가짜 `Popen`(poll()이 바로 exit code를 반환)을 돌려줬다 — 자식 프로세스 0개, 불사자·gws·네이버 호출 0회, 크레딧 0, 쓰기 0(전부 임시 디렉터리에만)
- 회차 `2026-09-20`을 임시 `data_root`에 시드(②행 3개 · ①행 1개 · 가짜 `bulsaja_scan` 완료 잡 + 조인 산출물 1건). 실제 저장소의 `2026-09-20` 등 실회차와 무관한 합성 데이터(`zz*`)
- 시드 원본: `webapp/tests/test_routes_thumb.py`·`test_routes_coupang.py`·`test_routes_jobs.py`의 픽스처 모양을 그대로 재사용(계정·그룹명·상품코드 전부 zz 가짜)

## UAT 항목별 판정 (07-01/04/05 Pending UAT 조건 기준)

- **07-01 #1** (회차 선택 보드 — 썸네일 견적 버튼 disabled, 쿠팡 패널 + 버튼): pass — 라운드 선택 시 `#thumb-estimate-btn` disabled(선택 전) · `#coupang` 패널 노출 + `#coupang-preview-btn` 활성(코드로 확인)
- **07-01 #2** (회차 없는 보드 — 쿠팡 패널만): pass — 회차를 임시로 치워 재현. 쿠팡 패널·버튼(활성)만 보이고 `#thumb-estimate-btn`·`#preview-btn`·`#detail-estimate-btn`·회차 선택기 전부 DOM에 없음
- **07-01 #3** (`window.관제탑` 훅): pass — `{선택키, 회차, 결과기다리기, 오류표시, 요청}` 5개 키 확인, `선택키()`가 배열 반환, `회차()`가 `"2026-09-20"` 반환
- **07-01 #4** (기존 버튼 회귀): **fail** — 아래 발견 [P1] 참조. 입찰가 미리보기(`#preview-btn`)는 정상 회귀(견적 생성 200·표 렌더). 상세 견적(`#detail-estimate-btn`)은 "배너 스캔을 먼저 돌려라"(409) — 이건 내 픽스처에 배너 스캔이 없어서 나는 **정상 가드**(회귀 아님)
- **THUMB 견적 표**: pass — 선택 3 → 이미가공/정합검사/삭제대상/조회실패/현황판제외 0 → 생성 3, 예상 15·최대 30(K×5/×10, 러너 값 그대로 표시)
- **THUMB 승인 기록**: pass — `실행 승인` 클릭 → 잡 생성 없이 `web_approval.json`만 임시 러너 폴더에 원자 쓰기(승인시각·견적잡id·계정·그룹명·시트id·ids 3개·예상/승인상한크레딧) · 인계 명령 `썸네일 작업 이어서"<임시경로>"` 노출. 실 `~/python_work/data`에는 어떤 파일도 안 생김(확인)
- **THUMB 결과 표**: pass — zz01=사용가능(5크레딧) · zz02=**회수 대기**(recover 명령 텍스트만, 버튼 0개 — `document.querySelectorAll('button').length === 0`) · zz03=제외(원본대체). 재생성 버튼 없음(L-03 확인)
- **COUPANG 미리보기(성공)**: pass — 기준 문구 CLI 원문 그대로, 게이트 통과 3 · 쿠팡그룹에이미있음 2 · 탈락사유별, 배송비과소 행은 "(과소)" **표시만**(차단 없음, D-10), `#coupang-commit-details`가 `open` 속성 없이 접힘 · 버튼 `class="contrast"`(다른 색) · 표 맨 아래(다른 위치)
- **COUPANG prep 실패**: pass — "'prep' 단계에서 멈췄다(종료코드 1)" · "정지단계: prep (주문시트 집계(gws))" · `gws auth login` 안내 문구 정확히 일치 · 복사 영역 없음
- **COUPANG 건수 불일치 409**: pass — 승인목록 3건에 "2" 입력 → 409 "화면이 본 건수(2)와 지금 복사할 건수(3)가 다르다" · DB 확인 결과 `coupang_commit` 행 생성 **0건**(체크가 create_job 이전에 있어 잡 자체가 안 만들어짐 확인)
- **COUPANG 복사 성공 결과 표**: pass — 정확한 건수(3) 입력 → 재조회 3→3 · 복사 3건(zz01~03 → newp-zzp0N) · **중복 0**(녹색) · 잠금안내 문구 노출

## 발견 (심각도순)

- **[P1] 썸네일 견적 버튼이 체크박스 클릭만으로는 활성화되지 않는다** — 재현: 라운드 선택 후 보드에서 ② 행 3개의 "Select Row" 체크박스만 클릭(다른 요소는 건드리지 않음) → `window.관제탑.선택키()`는 정확히 3개를 돌려주는데 `#thumb-estimate-btn.disabled`는 계속 `true`. 체크박스가 아닌 임의 요소(예: `<h1>`)를 한 번 더 클릭하면 그제서야 `disabled=false`로 바뀐다(같은 선택값으로). / 근거: `webapp/static/thumb.js` 43~48행 — 선택 변화 감지를 `document.addEventListener("click"/"keyup", …)` 버블링에만 의존한다("선택 변화 이벤트는 board.js 의 Tabulator 가 갖고 있고 훅으로 안 넘어온다 — 그래서 보드 위 클릭·키 입력 뒤에 선택 수를 다시 본다" 주석대로 설계된 동작이지만, Tabulator의 내장 `formatter:"rowSelection"` 체크박스는 자체 클릭 핸들러가 이벤트를 `document`까지 버블링시키지 않는다 — 실측: `cb.click()`을 DOM에서 직접 호출하고 50ms 대기해도 갱신 안 됨, 반면 같은 대기 뒤 무관한 요소를 클릭하면 즉시 갱신됨). 대조: `webapp/static/board.js` 490행은 기존 `preview-btn`/`detail-estimate-btn`을 위해 Tabulator 자체 이벤트 `table.on("rowSelectionChanged", …)`를 쓰고 있어 이 문제가 없다(실측: 체크박스만 클릭해도 즉시 활성화됨) — 07-01/04가 `thumb.js`에서 같은 패턴을 재사용하지 않아 생긴 차이. / 영향: 사용자가 체크박스만으로 상품을 고르고 바로 `썸네일 견적` 버튼을 누르면 비활성 상태라 아무 반응이 없다(고장으로 오인 가능). 워크어라운드는 있음(보드 아무 곳이나 한 번 더 클릭) — 그래서 완전 불가(P0)는 아니지만 THUMB-02의 최초 진입 동작이라 P1으로 올린다. / 근거 명세: 07-04-SUMMARY THUMB-02 · 07-01-SUMMARY "선택 변화 이벤트는 … 훅으로 안 넘어온다" 주석 / 오탐 가능성: 낮음 — Tabulator·board.js 소스를 직접 대조해 원인을 확정했다(shared 파일 board.js는 07-01에서만 고치는 규칙이라 thumb.js가 board.js의 검증된 패턴을 그대로 못 가져온 구조적 결과로 보인다)

없음 (그 외 P0/P2/P3)

## 회귀 대상

- `webapp/routes/jobs.py`(create_job 공유 가드·`_상세잡만들기`) ← 07-01이 Phase 7 3종 kind를 추가하며 전역 로직을 공유
- `webapp/jobs.py`(KINDS·WRITE_KINDS·BULSAJA_KINDS·SINGLETON_KINDS·`_build_argv`) ← 07-01 key-files
- `webapp/templates/board.html`(선택 바·`#thumb-estimate`·`#coupang` 신설 섹션) ← 07-01 key-files
- `webapp/static/board.js`(`window.관제탑` 훅 노출부만 수정, 기존 로직 불변 확인) ← 07-01 key-files
- 입찰가 미리보기(`bids_preview`, 기존 기능) — 셋 다 같은 `create_job`/`_build_argv`를 지나므로 회귀 대상에 포함, 실제 클릭까지 실행해 200/표 렌더 확인
- 제외한 것: 상세 접수(`detail_submit`)·마켓 반영(`market_*`) — 각각 배너 스캔·상세 완료 데이터가 선행돼야 하는데 이번 격리 시드 범위 밖이다(최대 5개 제한 안에서 Phase 7이 직접 건드린 공유 파일 위주로 선정). `detail_estimate`는 사전조건 409(배너 스캔 없음)까지만 확인 — 이는 정상 가드이지 크래시가 아니므로 회귀는 아니라고 판단

## 사람 몫 (4가지만)

- 심미: 쿠팡 미리보기 표의 접힌 복사 영역(`#coupang-commit-details`, `class="contrast"` 버튼) 스크린샷을 남기지 않았다(이번 검증은 값·DOM 속성 확인 위주였음). 배치·색 대비를 눈으로 보고 싶으면 재요청 시 `uat-artifacts`에 스크린샷 첨부 가능
- 승인 필요: 없음 — 전 과정 실제 불사자·gws·쿠팡 호출 0건, 크레딧 0, 실 데이터 쓰기 0건
- 네이버 확인: 필요 없음 — 이 흐름은 네이버에 직접 접속하지 않는다(불사자 대표이미지·쿠팡 사본까지만, 스토어 반영은 D-08로 이연되어 이번 범위 밖)
- 법적 문구: 없음

## 노이즈 후보

- `Failed to load resource: the server responded with a status of 404 (Not Found) @ .../favicon.ico` — 기존 무해 목록과 동일 패턴(06-04-uat.md에서도 동일 관찰). 이미 반영돼 있다면 추가 제안 없음
- `Failed to load resource: … 409 (Conflict) @ /jobs/coupang/commit` — **의도된 검증 실패 경로**(건수 타이핑 불일치 테스트)에서만 발생. 일반 흐름(정확한 건수 입력)에서는 안 남. 조건부 노이즈 후보로 제안(원문 위 그대로) — "쿠팡 복사 건수 확인 실패 테스트 시에만"이라는 조건 필요

## 정리 결과

- 종료한 프로세스: 격리 uvicorn PID 74116 — `kill` 후 `lsof -iTCP:53114` 결과 비어 있음 확인. 실서버 PID 72246/:8765는 검증 전후 모두 `LISTEN` 유지, 무접촉 확인
- Playwright 세션: `uat-07thumbcoupang` `close` 후 `playwright-cli list` 결과 "(no browsers)"
- 시드: 전부 세션 scratchpad 임시 디렉터리(`$CT_WORK/data`, `$CT_WORK/jobs.db`, `$CT_WORK/profile.json`)에만 기록 — 저장소의 실 `webapp.db`·`~/python_work/data`는 시작·종료 시점 mtime 비교로 무변경 확인(공유 dev DB가 아니라 매 실행 새로 만든 임시 파일이라 시드 기록장 `.uat-seed-ledger.jsonl` 등록 대상 자체가 아니었음). 검증 종료 후 `$CT_WORK` 통째로 삭제
- 부수 발견 정리: Playwright CLI가 명령 실행 시 cwd(저장소 루트) 기준 상대경로로 `.playwright-cli/page-*.yml` 17개를 저장소 안에 남겼다 — `git status`로 발견해 검증 종료 시 `.playwright-cli/` 디렉터리를 통째로 삭제, `git status --porcelain -uall` 재확인 결과 깨끗함(저장소 변경 0)
- 준비 수정: 0회(시드 스크립트가 첫 시도에 의도대로 재현됨) — 단, 09-29 11:37경 "체크박스만으로 썸네일 버튼이 안 켜지는" 현상을 발견한 뒤 "보드 아무 곳 클릭" 워크어라운드로 흐름을 이어갔다(이건 버그 발견이지 내 시드 실수가 아니므로 준비 수정으로 세지 않음)
- 소스 변경 감지: `git status --porcelain -uall` 검증 전후 동일(clean) — 변경 없음
- 남은 것 없음

## 선행조건·환경 메모

- 포트 53114는 검증 시작 전 비어 있었고 종료 후에도 비어 있음
- 실서버 PID 72246(:8765)은 검증 시작·종료 시점 모두 `LISTEN` 유지 — 전 과정 무접촉
- `workspace.toml`은 읽기만 했다(격리 프로세스가 `expected_bulsaja_nick`을 함수 교체로 가짜 값으로 덮었을 뿐, 파일 자체는 안 건드림)
- gws 인증 만료(07-04/07-05 evidence의 BLOCKED)는 이번 검증과 무관 — 전부 fake spawn으로 대체했으므로 gws·불사자 실호출 자체가 없다. 실제 gws 복구 뒤 실데이터 스모크(07-06/07-07 몫)는 이 리포트 범위 밖이다
- 07-01 SUMMARY "② 조인 공백"(실데이터에서 웹 견적이 항상 0건 — routes/jobs.py의 `불사자_대상규칙`이 ③⑤만 스캔) 이슈는 이번 격리 검증에서는 재현되지 않는다 — 조인 산출물을 직접 합성해 넣었기 때문이다. 이 항목은 07-06 결정 대기 중인 별개의 설계 공백이며 이번 UAT 판정에는 포함하지 않는다(이미 07-04-smoke.md에 실측·기록됨)

## 해결 기록

- 2026-09-29 quick 260929-t1: P1 "② 체크박스만으로 `#thumb-estimate-btn` 이 안 켜짐" 해결 — thumb.js 가 `Tabulator.findTable("#board")` 로 같은 표의 `rowSelectionChanged` 를 구독(board.js 무수정). 격리 헤드리스 크롬에서 수정 전 FAIL 재현·수정 후 체크 시 켜짐/해제 시 꺼짐 PASS. 서버 재시작 불필요, 브라우저 새로고침만.
