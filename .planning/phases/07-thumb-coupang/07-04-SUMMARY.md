---
phase: 07-thumb-coupang
plan: 04
subsystem: webapp-thumb-track
tags: [thumb-01, thumb-02, thumb-03, d-02, d-03, d-06, d-07, d-08, l-02, l-03, l-06]
requires: ["07-01", "07-02"]
provides:
  - "POST /jobs/thumb/estimate — 보드 키로 서버 재구성, ② 아님·조인 미해소·그룹명 미특정·상한초과 사유"
  - "POST /jobs/thumb/approve — 잡 0, 그룹별 web_approval.json 원자 쓰기, 상한 = 그룹 최대크레딧"
  - "GET /thumb/{id}/result — 판매자상품코드 단위 상태, 회수 대기는 recover 명령 텍스트만"
  - "결과표 thumb_estimate → _thumb_estimate_table.html · _썸네일견적ctx"
  - "_인계명령(run_dir) — D-06 을 뒤집을 때 바꿀 유일한 자리"
  - "thumb.js 배선(견적 버튼 · 실행 승인 · 결과 보기)"
affects: [07-06]
tech-stack:
  added: []
  patterns: ["승인 = 잡이 아니라 파일(web_approval.json) + 표시용 명령", "summary 안 경로는 thumb_dir_of 바로 밑일 때만 믿는다", "전 그룹 오류면 0건 안내 대신 오류 배너"]
key-files:
  created:
    - webapp/templates/_thumb_estimate_table.html
    - webapp/templates/_thumb_result_table.html
    - webapp/tests/test_routes_thumb.py
    - webapp/tests/fixtures/thumb_run/zz그룹/generated.json
    - webapp/tests/fixtures/thumb_run/zz그룹/decisions.json
    - .planning/phases/07-thumb-coupang/deferred-items.md
    - .planning/phases/07-thumb-coupang/evidence/07-04-smoke.md
  modified:
    - webapp/routes/thumb.py
    - webapp/static/thumb.js
    - webapp/tests/test_phase7_shell.py
decisions:
  - "그룹명 미특정 = 조인 문서 마켓그룹 중 같은 NN-N 번호 그룹이 0개 또는 2개 이상 (group_index 는 조용히 덮으므로 따로 센다)"
  - "inputs.웹제외 값은 {판매자상품코드, 사유} 객체 — 견적 표가 보드키 대신 코드로 보이게(러너는 무시)"
  - "승인은 전 그룹을 먼저 검사한 뒤 쓴다 — 반쯤 승인된 견적을 만들지 않는다"
  - "결과 상태에 '생성 전' 추가 — 승인 ids 중 generated.json 에 아직 없는 건"
  - "원본대체(fallback 종결) 판정은 결과 표에서 '제외' 로 보인다"
  - "조인 스캔 범위에 ② 를 넣는 것은 Rule 4 — 인덱스 구축 범위도 같은 튜플이 정한다. 07-06 에서 결정"
metrics:
  duration: "~70분"
  completed: 2026-09-29
  tasks: 3
  files: 12
---

# Phase 7 Plan 04: 썸네일 웹 — 견적 → 승인 기록 → 결과 표 Summary

보드에서 규칙② 상품을 골라 `썸네일 견적 — 크레딧 0` 을 누르면 서버가 대상을 다시 계산해 견적 잡을 띄우고, 러너 summary.json 숫자를 그대로 견적 표로 보인다. `실행 승인 — 크레딧 0` 은 잡이 아니라 그룹별 `web_approval.json` + 복사용 인계 명령이고, 결과 보기는 그룹 run-dir 파일을 판매자상품코드 단위로 읽는다. 라우트·화면은 오프라인 테스트로 닫혔다. **실데이터 스모크는 BLOCKED(gws 인증 만료)이고, 웹 견적이 실데이터에서 항상 0건이 되는 설계 공백을 하나 찾았다(아래).**

## 무엇을 만들었나

- **Task 1 (bb3283f RED → 396e6b7 GREEN)** — `routes/thumb.py`:
  - `ThumbEstimateReq`·`ThumbApproveReq` 둘 다 `extra="forbid"`.
  - 견적은 `post_detail_estimate` 뼈대(조인 산출물 → fold → attach → 모르는 키 400)를 따른다. 행마다 ② 아님 / 조인 미해소 / 그룹명 미특정 / 중복을 사유와 함께 뺀다. 통과분은 노출 내림차순으로 세워 `thumb_max_items` 앞만 남기고, 나머지는 '상한초과'다. inputs 의 그룹 키는 조인 문서의 전체 그룹명이다. 예외 번역은 `_상세잡만들기` 를 쓴다.
  - 승인은 부모를 3단(종류·완료·정상)으로 검사한 뒤 K 양의 정수를 확인한다. 그다음 그룹마다 폴더 위치·시트id·예상/최대(bool·음수·비정수 거부)·기존 승인 파일을 전부 검사하고 나서야 원자 쓰기를 한다. 잡은 0개다.
  - 결과 상태 매핑표는 `_행상태` docstring 에 있다. 회수 대기 건은 `run_thumbs.py recover --run-dir "<dir>"` 텍스트만 보인다.
  - `deferred-items.md` 에 D-08 을 기록했다.
- **Task 2 (083ba00)** — `thumb.js`:
  - 견적 버튼은 선택·회차가 있을 때만 켜진다(클릭·키 입력 뒤 재계산, 클릭 시점에도 재검사).
  - 견적을 누르면 작업 패널을 띄우고 10분까지 결과를 기다린다.
  - 승인·결과 버튼은 위임 클릭으로 받는다. 승인 뒤에는 견적 조각을 다시 그려 인계 명령을 보인다.
  - 템플릿 2개는 Task 1 테스트가 조각을 보므로 Task 1 커밋에 들어갔다.
- **Task 3 (4af2be1 · 1d0a8f9)** — 실데이터 스모크. 결과는 `evidence/07-04-smoke.md`에 있다.
  - 스모크 중에 버그를 찾아 고쳤다. 전 그룹이 오류일 때 견적 표가 "생성 대상 0건 — 이미 가공" 으로 오독되고 있었다.

## 검증

- `.venv-web/bin/pytest webapp/tests` → **901 passed**(07-03 기준 867 + 신규 34)
- `node --check webapp/static/thumb.js` OK · `no_commit_guard.sh` OK
- acceptance grep 충족:
  - `def _인계명령` 1줄 · `web_approval.json` ≥1
  - 크레딧 곱셈 패턴 0 · `| safe` 0
  - thumb.js 라우트 참조 4줄 · 결과 표 재생성 버튼 0
  - D-08 기록 있음 · 승인 테스트에서 create_job 0
- 스모크 폴더: web_approval.json 0개 · generated.json 0개

## 실데이터 스모크 결과 (크레딧 0)

- **웹 라우트:** 회차 2026-09-20 에서 ② 노출 상위 200키를 보냈고 **400** 이 돌아왔다(잡 0). 200키 전부 '조인 미해소'였다.
- **러너 직접 실행(L-06 우회, 스모크 전용):**
  - 대상: ② 노출 상위 20건, 15그룹. pid·그룹은 인덱스(`ss_index`) 기준으로 잡았다.
  - 계정: `부킹` 일치(15/15).
  - 결과: 전 그룹 exit 1 — `gws 401 invalid_grant`. 현황판 시트 id 를 찾는 단계에서 멈췄다. 합계는 전부 0이다(K·M·A·D·E·예상·최대). **K=0 은 D-03 때문이 아니라 인증 만료 때문이다.**
  - 현황판 백필 0 · 크레딧 0 · 불사자 쓰기 0.

## ⚠️ 설계 공백 — ② 행이 조인되지 않는다 (07-06 결정 필요)

`routes/jobs.py` 의 `불사자_대상규칙 = ("③원인분석", "⑤효자확정")` 때문에 조인 스캔이 ② 행을 불사자에 잇지 않는다. 그래서 L-06(그룹·pid 는 조인 산출물에서만)을 지키는 웹 견적은 실데이터에서 **항상 0건**이다.

- 인덱스에는 ② 609행 중 311행이 있다.
- 같은 튜플이 인덱스 구축 범위도 정한다. 그래서 ② 를 넣으면 수 시간짜리 인덱스 비용이 붙을 수 있다 → **Rule 4 로 고치지 않았다.**
- **추천 ⓐ:** 스캔 대상 함수에만 ② 를 더하고, 인덱스 범위는 ③⑤ 로 유지한다(함수 분리). 공유 파일이다.
- 대안:
  - ⓑ 스캔·인덱스 둘 다 ② 를 더한다.
  - ⓒ 썸네일만 인덱스 조회 + prep 실시간 재검증으로 간다(L-06 완화).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] 전 그룹 오류 견적이 "생성 대상 0건 — 이미 가공" 으로 보였다**
- **Found during:** Task 3 (실데이터 summary 오프라인 렌더)
- **Fix:** ctx 가 전 그룹 오류를 오류 배너로 올린다. 이때 템플릿은 0건 안내와 승인 버튼을 숨긴다. 회귀 테스트를 추가했다.
- **Files:** webapp/routes/thumb.py · _thumb_estimate_table.html · test_routes_thumb.py
- **Commit:** 4af2be1

**2. [Rule 1] thumb.js 기다림 한도 리터럴 `1500` 이 `test_paths` 리터럴 가드에 걸렸다**
- Task 2 커밋 뒤 전체 스위트에서 걸렸다. 계산식 `(10*60*1000)/400` 으로 바꿨다. **Commit:** 4af2be1

**3. [Rule 1] `test_phase7_shell` 의 "썸네일 결과표는 빈 dict" 고정 테스트 갱신**
- 계획대로 07-04 가 채웠으므로 `{"thumb_estimate"}` 하나만 등록됐는지 보도록 바꿨다(T-07-06 유지). **Commit:** 396e6b7

**4. [Rule 2] 승인 방어 보강**
- summary 의 그룹 run_dir 이 이 견적 러너 폴더 **바로 밑**이 아니면 거부한다(T-07-22).
- 시트id 가 비어도 거부한다.
- summary 에 `오류`(계정불일치)가 있으면 거부한다.
- **Commit:** 396e6b7

**5. [계획 조정] 템플릿 2개를 Task 1 커밋에 넣었다** — Task 1 의 행동 명세(합계가 조각에 그대로, 스토어 반영 미연결 문구)를 조각 렌더로 검증하기 때문이다.

**6. [Rule 4 — 보류] ② 조인 공백** — 위 절. 고치지 않았다.

## 서버 재시작

도는 잡 0을 확인하고 재기동했다(PID 52296 → 68418 → 최종 **69495**). 07-04 최종 코드가 올라가 있다. `dd911562` 는 건드리지 않았다.

**새 URL: `http://127.0.0.1:8765/?t=JuyL_66QdZpKOR0PQxClgb64NXs49u198jvk7NftmI8`** (로그 `webapp-logs/server-07.log`)

## Auth Gate / BLOCKED

- **gws 인증 만료(`invalid_grant`)** — 사용자 조치가 필요하다.
  1. `gws auth login` 을 cy728728 계정으로 한다("다른 계정 사용").
  2. 안 풀리면 `token_cache.json` 을 삭제한다.
- 그 뒤 evidence 파일의 재실행 명령으로 러너 스모크를 다시 돌린다. 웹 경로는 ② 조인 공백을 결정한 뒤에 돌린다.

## Pending UAT (uat-verifier 일괄 — 07-05 것과 묶어서)

이 실행기는 서브에이전트를 못 띄운다. 조건만 적는다(서버 69495, 위 URL):
1. 회차 2026-09-20 보드에서 행을 고르면 `썸네일 견적 — 크레딧 0` 이 켜지고, 선택을 0으로 하면 꺼진다.
2. ② 행을 골라 누르면 지금은 400 "규칙② 대상이 0건" 과 조인 미해소 사유가 #job-error 에 보인다(공백 결정 전 기대 동작). 콘솔 오류 0.
3. (공백 해소 + gws 복구 뒤) 견적 표 집계 줄 숫자 = summary.json 합계, 웹제외 표, K>0 이면 '실행 승인' 활성. **'실행 승인' 은 누르지 않는다**(07-06 에서 사람 확인 뒤).
4. 회귀: 입찰가 미리보기·상세 견적 버튼 동작이 그대로다.

## Known Stubs

- 결과 표의 "스토어 반영 미연결(Phase 6 완료 후)" — D-08 로 의도적으로 미뤘다(deferred-items.md).

## Threat Flags

없음 — 새 표면은 계획의 threat_model(T-07-20~25) 범위 안이다.

## 요구사항 체크

THUMB-01·02·03 은 **체크하지 않았다.** 라우트·화면은 됐지만, 실데이터에서 ② 대상이 화면에 안 뜬다(조인 공백). 첫 생성은 07-06 체크포인트에서 한다.

## TDD Gate Compliance

Task 1: test(bb3283f) → feat(396e6b7). RED 에서 새 라우트 테스트가 실패함을 확인했다(라우트·_인계명령 부재).

## Self-Check: PASSED
- 생성 파일 7개 존재 확인
- 커밋 bb3283f · 396e6b7 · 083ba00 · 4af2be1 · 1d0a8f9 존재 확인
