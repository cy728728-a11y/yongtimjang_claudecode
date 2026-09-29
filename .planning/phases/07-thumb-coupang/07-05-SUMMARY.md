---
phase: 07-thumb-coupang
plan: 05
subsystem: webapp coupang track
tags: [cp-01, cp-02, cp-03, cp-04, d-09, d-10, d-11, d-12, d-13, d-16, l-02, l-04]
requires: ["07-01", "07-03"]
provides:
  - "POST /jobs/coupang/preview (빈 본문 · extra=forbid)"
  - "POST /jobs/coupang/commit {preview_job_id, typed_count} — 건수 불일치 409"
  - "_쿠팡복사상한() (첫 성공 전 10 / 이후 20) · _승인목록() (통과 상위순, D-16 한 곳)"
  - "결과표 coupang_preview → _coupang_preview_table.html · coupang_commit → _coupang_result_table.html"
  - "coupang.js 배선 (후보 버튼 켜기 · 위임 복사 버튼 · starting 재폴링)"
affects: [07-07]
tech-stack:
  added: []
  patterns: ["타이핑 확인값은 대상이 아니라 대조값 — 서버가 다시 세서 다르면 409", "복사 영역 4중 마찰(위치·접힘·색·건수)", "요약 파일값만 표시 — 중복0 을 종료코드로 추정하지 않음"]
key-files:
  created:
    - webapp/templates/_coupang_preview_table.html
    - webapp/templates/_coupang_result_table.html
    - webapp/tests/test_routes_coupang.py
    - .planning/phases/07-thumb-coupang/evidence/07-05-smoke.md
  modified:
    - webapp/routes/coupang.py
    - webapp/static/coupang.js
    - webapp/tests/test_phase7_shell.py
decisions:
  - "건수 불일치 409 (post_revert_round 선례) · 부모 종류/실패/24h/재커밋 400 · 부모 도는 중·같은 복사 도는 중 409"
  - "승인목록은 gate 정렬 그대로 상위 상한 건 — 상세완료 필터 없음(D-16 확인 대기, _승인목록 한 곳만 바꾸면 됨)"
  - "만료(24h)·이미복사·복사중이면 후보 표에 복사 영역 대신 안내 1줄"
  - "orphaned(exit None) 정지는 요약의 마지막 단계 코드를 보인다"
metrics:
  duration: "~10분"
  completed: 2026-09-29
  tasks: 3
  files: 7
---

# Phase 7 Plan 05: 쿠팡 웹 슬라이스 Summary

보드 상단 `쿠팡 후보 뽑기 — 쓰기 0` 한 번으로 6단계 미리보기 잡을 띄우고, 후보 표 맨 아래 접힌·다른 색·건수 타이핑 영역에서만 복사가 나가며, 결과 표가 재조회 차분·신pid 없음·중복0·잠금 승계 안내를 파일에서 읽어 보인다. 실데이터 미리보기 1회는 prep 단계 gws 401 로 BLOCKED — 쓰기 0.

## 무엇을 만들었나

- **Task 1 (41e36b4 RED → ebb2b53 GREEN)** — `routes/coupang.py`
  - `CoupangPreviewReq` 필드 0개(extra=forbid) — `{"min_margin":15}` 422. 예외 번역은 `_상세잡만들기` 재사용(같은 미리보기 도는 중·계정 불일치 409).
  - `CoupangCommitReq{preview_job_id: JobId, typed_count: StrictInt ≥0}` — 문자열·bool·음수 422.
  - 커밋 검사 순서: 부모 kind(400) → 도는 중(409) → done/0(400) → 24h(400) → 자식 복사 도는 중(409) · 성공 복사 있음(400 "이미 복사했다 — 새 미리보기부터") → 요약(깨짐 400) → `_쿠팡복사상한()` → `_승인목록()`(빈 400) → **typed_count ≠ len → 409** → create_job(쓰기 가드 409).
  - ctx 2: `_쿠팡미리보기ctx`(기준 원문 · 통과 6칸 + 상한초과 · 탈락사유별 · 이미있음 · 그룹읽기 · 복사예정 · 정지단계/gws 안내 · 이미복사/복사중/만료) · `_쿠팡결과ctx`(재조회 옛/새/빠짐(코드 표기)/늘어남 · 복사 행 · 신pid없음 · 중복0 파일값 · exit5 · 잠금 안내).
  - `test_phase7_shell` 의 "쿠팡 결과표 빈 dict" 자리 단언을 두 kind 등록으로 갱신(07-04 가 썸네일 쪽을 같은 식으로 갱신한 선례).
- **Task 2 (0b8b905)** — 후보 표·결과 표 템플릿, `coupang.js`. 복사 영역은 표 맨 아래 `<details id="coupang-commit-details">`(open 없음) · `class="contrast"` 버튼 · `#coupang-typed-count`. JS 는 정수가 아니면 요청을 안 보내고, 요청 뒤 입력칸을 비우며, 몸통은 `{preview_job_id, typed_count}` 뿐. 409 두 종류(건수 불일치 / 도는 작업·계정)를 주석으로.
- **Task 3 (f9f2263 fix · 826434a evidence)** — 실데이터 미리보기 1회. 아래 절.

## 검증

- `.venv-web/bin/pytest webapp/tests` → **932 passed** (07-04 뒤 기준선 901 + 쿠팡 31)
- `node --check webapp/static/coupang.js` OK · `no_commit_guard.sh` OK · 템플릿 `| safe` 0
- acceptance grep: `def _쿠팡복사상한`/`def _승인목록` 2줄 · `status_code=409` 3 · 금지 플래그 4종 0 · `<details … open` 0 · `class="contrast"` 1 · `typed_count` 2 · 결과표 `잠금` 2

## 실데이터 미리보기 — BLOCKED (gws 401)

잡 `f54afee0-3f7a-4df1-9ca2-9f49e1b43667` · 11:25:44→11:25:47 · prep 에서 `gws API 오류 401 … invalid_grant` → `정지단계: prep`. run-dir 에 summary.json 만 있고 copied.jsonl 없음, coupang_commit 0개 — **쓰기 0**. 화면 조각은 정지단계 이름 + gws 재로그인 안내를 보이고 복사 영역을 안 그린다(D-09 실측). 재로그인은 하지 않았다(사용자 몫). 상세: `evidence/07-05-smoke.md`.

미측정(gws 복구 + toml 20.0 전환 뒤 07-07 에서): 기준 문구 20% · 통과/이미있음 · 그룹읽기 총상품수==읽음 · 파일럿(copied.jsonl 85행) 교집합 0 · 복사예정 목록.
⚠️ workspace.toml `min_margin = 15.0` 그대로 — 지금 돌리면 기준 문구가 15.0 으로 찍힌다(계획의 "15 면 FAIL" 은 toml 전환 뒤에 적용).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] orphaned 정지에 '종료코드 None' 표시**
- **Found during:** Task 3 (실데이터 미리보기)
- **Issue:** 검증용 외부 파이썬 프로세스가 `job_status` 를 폴링하다 자식 종료 순간 `_reap` 으로 행을 orphaned(exit None)로 적었고, 조각이 "종료코드 None" 을 보였다.
- **Fix:** 행 종료코드가 없으면 요약 `단계` 마지막 exit 를 보인다 + 테스트 1.
- **Commit:** f9f2263

**2. [Rule 2] 후보 표 안전 분기 추가** — 계획의 "이미 복사했으면 안내" 에 더해 복사 도는 중·24h 만료일 때도 복사 영역 대신 안내 1줄(서버도 409/400 이지만 버튼을 안 그리는 쪽이 맞다).

**3. [Rule 2] coupang.js starting 재폴링** — board.js `결과기다리기` 는 `running` 만 붙잡아 막 뜬 잡(starting)이면 "도는 중" 조각에 멈춘다. board.js 를 안 고치고(D-19) 끝났을때 콜백에서 starting 이면 1초 뒤 다시 붙잡는다(최대 30회).

### 오케스트레이터 제약

- 서버 재기동 2회(도는 잡 0 확인 후): PID 69495 → 71781 → **72246**. 새 URL 은 아래.
- uat-verifier 호출 불가(서브에이전트 도구 없음) → Pending UAT 로 넘김.
- toml min_margin 무변경 · 마켓 미리보기 dd911562 무접촉 · 쓰기/복사 0.

## 서버

`http://127.0.0.1:8765/?t=cK-kZJx2x5YAtDb4_9CA8_SjxJDBHU5L2URvVaFAJig` (PID 72246, 로그: 세션 scratchpad `webapp-server.log`)

## Pending UAT (uat-verifier 일괄 — 오케스트레이터 몫)

**복사 버튼 누르지 말 것 · 건수 입력칸에 아무것도 입력하지 말 것.**
1. 보드 상단 `쿠팡 후보 뽑기 — 쓰기 0` 버튼이 **활성**이다(coupang.js 가 켠다).
2. 잡 `f54afee0…` 결과(또는 새로 누른 결과 — gws 복구 전이면 prep 정지): `#coupang-body` 에 "'prep' 단계에서 멈췄다(종료코드 1)" · "정지단계: prep (주문시트 집계(gws))" · gws 재로그인 안내 · 복사 영역 없음.
3. gws 복구 뒤(07-07): 기준 문구 원문(toml 전환 후 "20"), 통과 표 6칸(판매자상품코드·상품명·합산주문수·쿠팡보정마진·배송비차액·사유), 쿠팡그룹에이미있음 건수, 그룹읽기 줄, `#coupang-commit-details` 가 **접혀 있고** 버튼이 contrast(다른 색).
4. 브라우저 콘솔 오류 0 · 기존 버튼 회귀 없음.

## Known Stubs

없음. (쿠팡 그룹 표시명 `1번_용쌤쿠팡cy1728` 은 경고문 표시용 상수 — 실제 대상 그룹은 CLI 설정이 정본.)

## TDD Gate Compliance

- Task 1: `test(07-05)` 41e36b4 (07-01 뼈대로 돌려 실패 확인) → `feat(07-05)` ebb2b53 (GREEN)

## 요구사항

CP-01 · CP-02 완료 표시(버튼·확인 흐름·서버 검사 테스트 고정). CP-03 은 toml 20.0 전환(07-07), CP-04 는 07-03 에서 표시됨 — 실데이터 교집합 0 실측은 07-07.

## Self-Check: PASSED
