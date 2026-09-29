---
phase: 07-thumb-coupang
plan: 01
subsystem: webapp-jobs / webapp-argv / board-shell
tags: [thumb-02, cp-01, cp-02, cp-03, cp-04, d-19, d-13, l-04, zombie]
requires: []
provides:
  - "argv.THUMB_WEB · COUPANG_WEB · ThumbArgv · CoupangArgv (extra=forbid, 기준·skip·strict 필드 없음)"
  - "settings: thumb_max_items 20 · coupang_copy_max_items 20 · coupang_first_max_items 10"
  - "paths.thumb_runs_root() · coupang_runs_root()"
  - "jobs: kind 3종(thumb_estimate · coupang_preview · coupang_commit) · thumb_dir_of · coupang_dir_of · first_coupang_commit_done · _alive 좀비 판정"
  - "create_job kwargs: thumb_inputs · coupang_approved · copy_limit"
  - "routes/thumb.py · routes/coupang.py (router + 빈 결과표) · get_job_result 병합(기존 키 우선)"
  - "board.html #thumb-estimate-btn(disabled) · #thumb-estimate · #coupang 패널(회차 무관) · thumb.js/coupang.js 태그"
  - "window.관제탑 = {선택키, 회차, 결과기다리기, 오류표시, 요청}"
affects: [07-02, 07-03, 07-04, 07-05]
tech-stack:
  added: []
  patterns: ["트랙 결과표 지연 병합 + setdefault(기존 키 우선)", "잡 id 모양 검증 후 러너 뿌리 밑에만 폴더 유도", "ps stat Z = 죽음 (waitpid 금지)"]
key-files:
  created:
    - webapp/routes/thumb.py
    - webapp/routes/coupang.py
    - webapp/static/thumb.js
    - webapp/static/coupang.js
    - webapp/tests/test_phase7_shell.py
  modified:
    - webapp/argv.py
    - webapp/settings.py
    - webapp/paths.py
    - webapp/jobs.py
    - webapp/routes/jobs.py
    - webapp/main.py
    - webapp/templates/board.html
    - webapp/templates/_job_status.html
    - webapp/static/board.js
    - webapp/tests/test_argv.py
    - webapp/tests/test_paths.py
    - webapp/tests/test_jobs.py
decisions:
  - "thumb_estimate 는 광고 회차(run_dir) 필수 — 보드 재구성 근거. 그룹 목록이 비거나 그룹의 pid 목록이 비어도 ValueError"
  - "coupang_commit 의 부모 검사(done/0 coupang_preview)는 create_job 트랜잭션 안에서 — 가드와 같은 창"
  - "coupang_commit 행의 targets_path 는 approved_<잡id>.json — target_count 가 승인 건수로 자동 기록"
  - "window.관제탑 에 오류표시도 노출 — 트랙 JS 가 같은 #job-error 칸을 쓰게(새 동작 없음)"
  - "copy_limit 은 bool 을 정수로 받지 않는다(True=1 로 미끄러지는 길 차단)"
metrics:
  duration: "~35분"
  completed: 2026-09-29
  tasks: 3
  files: 17
---

# Phase 7 Plan 01: 공유 파일 집중 — 잡 엔진·argv·보드 자리 Summary

썸네일 견적 · 쿠팡 후보/복사 세 kind 를 잡 엔진·argv 모델·설정·경로·잡 상태 문구·결과표 디스패치·보드 자리에 한 번에 등록했다. 이후 07-04(썸네일 웹)·07-05(쿠팡 웹)는 `routes/thumb.py`·`routes/coupang.py`·트랙 JS·트랙 템플릿만 만지면 된다(D-19). 크레딧 0 · 불사자/네이버 접속 0 · 오프라인 테스트만.

## 무엇을 만들었나

- **Task 1 (f0f4d9a)** — `ThumbArgv`(estimate) · `CoupangArgv`(preview/commit), 둘 다 `extra="forbid"`. CoupangArgv 에는 게이트 기준·skip·strict 필드가 아예 없다(L-04 · D-15). commit 은 승인 목록·상한(≥1) 없으면 `ValueError("상한 없는 복사는 없다…")`. 설정 3키, 러너 뿌리 경로 2개. `webapp/**`(.py/.html/.js, 테스트 포함)에 금지 플래그 4종이 0회임을 트리 가드로 고정.
- **Task 2 (665986b)** — `JobKind`·`KINDS` 에 3종, `coupang_commit` 만 `WRITE_KINDS`, 셋 다 `BULSAJA_KINDS`·caffeinate, `thumb_estimate`·`coupang_preview` 는 `SINGLETON_KINDS`, `POLL_INCOMPLETE_OK_KINDS` 는 그대로(exit 3 = failed). `thumb_dir_of`/`coupang_dir_of`(uuid 모양 검증) + `_write_json_atomic`. `create_job` 이 `thumb_inputs`/`coupang_approved`/`copy_limit` 을 kind 전용으로 받고, 쿠팡 kind 에 run_dir 을 주면 거부, 복사는 상한·승인목록·부모(done/0 preview) 셋 중 하나라도 없으면 행을 만들지 않는다. `first_coupang_commit_done()` 은 레지스트리만 본다(DB 없으면 만들지 않고 False). `_alive` 는 `ps -o stat=` 첫 글자 Z 면 False, ps 예외면 True, waitpid 는 안 쓴다.
- **Task 3 (255f178)** — 트랙 라우터 2개(빈 `결과표`)를 main 에 등록하고 `get_job_result` 가 지연 import 뒤 `setdefault` 로 병합해 기존 kind 표를 덮지 못하게 했다. 보드에 `썸네일 견적 — 크레딧 0` 버튼(disabled, `{% if run_dir %}` 안), `#thumb-estimate` 자리, 회차와 무관한 `<section id="coupang">`(쿠팡 후보 뽑기 버튼 disabled)을 넣고 board.js 뒤에 thumb.js/coupang.js 를 붙였다. board.js 끝에 `window.관제탑` 훅을 노출했다(기존 함수를 참조만 한다). `_job_status.html` 에 세 kind 이름, 도는 중 문구, 종료코드 2/3/4/5 문구, gws 403 안내를 넣었다.

## 검증

- `.venv-web/bin/pytest webapp/tests -q` → **867 passed, 0 failed**(기준선 ~808 이상)
- `node --check` board.js · thumb.js · coupang.js OK · `no_commit_guard.sh` OK
- acceptance grep 전부 충족(`coupang_commit` 16회 · waitpid 코드 사용 0 · `id="coupang"` 1줄이고 run_dir 블록 밖 · 썸네일 버튼 문구에 "쓰기 0" 없음)
- 실제 `~/python_work/data/{thumbnail,coupang}/runs` 에 `web-*` 폴더 0개 — 테스트가 러너 뿌리를 tmp 로 돌린다

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] 기존 BULSAJA_KINDS 고정 테스트 갱신**
- **Found during:** Task 3 전체 스위트
- **Issue:** `test_argv.py::test_불사자잡은_전역_쓰기가드에_안_들어간다` 가 BULSAJA_KINDS 멤버를 통째로 고정해 둬서, 계획대로 3종을 더하자 실패했다
- **Fix:** 고정 집합에 Phase 7 3종을 더하고 주석에 L-05 를 적었다(의도된 변경)
- **Files modified:** webapp/tests/test_argv.py
- **Commit:** 255f178

**2. [Rule 2 - 방어] 입력 검증 보강**
- `thumb_inputs` 는 그룹 0개뿐 아니라 그룹의 pid 목록이 비었을 때도 ValueError로 막는다(빈 값 ≠ 전량)
- `copy_limit` 에 bool 은 받지 않는다
- 승인 목록에 빈 문자열이 있으면 거부한다
- 쿠팡 kind 에는 대상 인자(only_ads 등)를 받지 않는다
- `coupang_preview` 에는 부모 잡을 받지 않는다
- **Commit:** 665986b

**3. [Rule 2] `window.관제탑.오류표시` 추가 노출** — 인터페이스 4개에 더해, 트랙 JS 가 같은 `#job-error` 칸에 오류를 띄울 수 있게 기존 함수를 하나 더 넘겼다. 새 동작은 없다.

**4. [상태 기록] 요구사항 완료 표시 보류.** 프론트매터에는 THUMB-02 · CP-01~04 가 적혀 있다. 하지만 이 플랜은 자리만 깐 수평 레이어라 어느 요구도 아직 사용자에게 동작하지 않는다. 그래서 `requirements.mark-complete` 를 되돌렸다. 07-04 · 07-05 가 끝날 때 표시한다. `state.advance-plan` 이 STATE 를 "Phase complete — verifying" 으로 잘못 적어서 executing 으로 바로잡았다.

## 서버 반영 주의

사용자 서버(PID 52296, :8765, `--reload` 없음)는 이 코드를 아직 모른다. 재시작 전에는 새 kind 와 보드 자리가 뜨지 않는다. 서버는 재시작하지 않았고 POST 도 하지 않았다. 대기 중인 마켓 미리보기 잡 dd911562 도 건드리지 않았다. 재시작은 도는 잡이 0개일 때 오케스트레이터가 판단해서 한다.

## Pending UAT (uat-verifier 일괄 — 오케스트레이터 몫)

서브에이전트를 띄울 수 없어 조건만 적는다. 서버를 재시작한 뒤 확인할 것:
1. 회차를 고른 보드: 선택 바에 `썸네일 견적 — 크레딧 0` 버튼이 disabled 로 보인다. 상단에는 "쿠팡 복사" 패널과 disabled 된 `쿠팡 후보 뽑기 — 쓰기 0` 버튼이 보인다.
2. 회차가 없는 보드(또는 run_dir 없는 `/`): 쿠팡 패널은 뜨고 썸네일 버튼은 없다.
3. 브라우저 콘솔: `window.관제탑` 이 객체이고 `선택키()` 가 배열을 돌려준다. thumb.js·coupang.js 로드 오류가 없다.
4. 기존 버튼(입찰가 미리보기·상세 견적·되돌리기)은 동작이 달라지지 않았다(회귀).
- 버튼을 눌러 보는 검증은 07-04/07-05 배선 뒤에 한다. 지금은 disabled 라 누를 수 없다.

## Known Stubs

- `webapp/routes/thumb.py` · `webapp/routes/coupang.py` — `결과표 = {}` 이고 라우트가 없다. 07-04 · 07-05 가 채운다(계획된 자리).
- `webapp/static/thumb.js` · `coupang.js` — 훅 확인만 하는 IIFE 다. 배선은 07-04 · 07-05 에서 한다.
- 두 트랙 버튼은 disabled 로 렌더된다. 트랙 JS 가 배선하면서 켠다.
- 러너 `thumb_web.py` · `coupang_web.py` 는 아직 없다(07-02 · 07-03). argv 만 조립하고, 잡은 트랙 라우트가 생기기 전까지 만들어지지 않는다.

## Self-Check: PASSED
- 생성 파일 5개 존재 확인
- 커밋 f0f4d9a · 665986b · 255f178 존재 확인
