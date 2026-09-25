---
phase: 05-core-value
plan: 03
subsystem: webapp/detail
tags: [detail, estimate, job-engine, board, DETAIL-01, DETAIL-02, DETAIL-05]
requires: ["05-01 detail_batch --inputs 계약", "05-02 banner.상세입력목록 · 확인시각읽기"]
provides:
  - "DetailArgv (estimate/submit/poll) · DETAIL_BATCH"
  - "detail_estimate/detail_submit/detail_poll kind + 가드 집합 + detail 폴더 규칙(_상세폴더)"
  - "POST /jobs/detail/estimate · _상세견적ctx · _detail_estimate_table.html"
  - "보드 🔴 기본 선택 · 상세 견적 버튼 · #detail-estimate 자리 · hidden detail-estimate-job (05-04 접수 버튼이 가리킬 견적 잡 id)"
affects: [05-04, 05-05]
tech-stack:
  added: []
  patterns: ["부모 체인으로 폴더 해석(지어내지 않음)", "서버가 보드 행 재구성 → 키 매칭 → 관문", "견적 표 숫자는 파일 값만"]
key-files:
  created:
    - webapp/templates/_detail_estimate_table.html
  modified:
    - webapp/settings.py
    - webapp/argv.py
    - webapp/jobs.py
    - webapp/routes/jobs.py
    - webapp/templates/board.html
    - webapp/templates/_job_status.html
    - webapp/static/board.js
    - webapp/tests/test_argv.py
    - webapp/tests/test_jobs.py
    - webapp/tests/test_routes_jobs.py
    - webapp/tests/test_board.py
decisions:
  - "배너 산출물↔보드 행 매칭 키는 판매자상품코드다 — 배너 산출물 상품엔 productId 가 없다(실측 키: 판매자상품코드·불사자코드·타오바오상품번호). 조인 산출물 행 (acct,mallProductId) → 판매자상품코드 → 배너 상품. 실측 2026-09-20 회차 배너 상품 62건의 판매자상품코드 62개 유일"
  - "라벨·확인시각 조회 키는 banner.상품키(상품)(타오바오상품번호 우선) — 05-02 저장 규약 그대로"
  - "detail_poll 도 WRITE_KINDS — 같은 detail_status.json 을 읽고-고치고-쓴다(연구 Open Q3)"
  - "detail_estimate 는 BULSAJA_KINDS(태그·잔액 조회라 계정이 틀리면 스킵 수가 남의 계정 기준) + SINGLETON(레이트리밋)"
  - "_상세폴더 는 부모 체인(submit→estimate, poll→submit→estimate)과 회차 일치를 검사하고 틀리면 ValueError — 폴더를 지어내지 않는다"
  - "같은 productId 가 두 키로 오면 두 번째는 제외('같은 불사자 상품이 이미 대상에 있다') — 사본 1개 원칙(D-06)"
  - "기작업·⚪ 여부로 서버에서 빼지 않는다 — CLI 실시간 D-12 판정에 맡긴다(이중 판정 금지)"
  - "_build_argv detail 분기는 settings.load(force=True) — 배너 잡과 같은 재시작 불필요 규율"
metrics:
  duration: "~35분"
  completed: 2026-09-25
  tasks: 3
  files: 12
---

# Phase 5 Plan 03: 상세 견적 슬라이스 Summary

보드에서 🔴 상품을 골라 `상세 견적 — 크레딧 0` 을 누르면, 서버가 보드 행을 다시 만들어 관문(`banner.상세입력목록`)을 통과한 상품만 inputs 파일로 떨구고 `detail_estimate` 잡(`detail_batch.py --inputs … --estimate-only`)을 띄운 뒤, 견적 표(선택 → 관문 제외 → 기작업 스킵 → 접수 · 총 장수 · 예상 크레딧 · 잘린 상품 · 계정 · 잔액)를 보여 준다. 잡 엔진에는 submit/poll 까지 세 kind 가 계약째 등록됐다. 크레딧 0 · 실제 잡 0회 (테스트는 spawn 몽키패치).

## 완료 태스크

| Task | 내용 | 커밋 |
|------|------|------|
| 1 RED | DetailArgv · detail kind 가드 · 폴더 규칙 실패 테스트 | efd28ac |
| 1 GREEN | DetailArgv · kind 3종 · WRITE/BULSAJA/SINGLETON · caffeinate · inputs writer · _상세폴더 · settings 2키 | d038906 |
| 2 RED | 견적 라우트·결과 조각 실패 테스트 | eda3aa6 |
| 2 GREEN | POST /jobs/detail/estimate · _상세견적ctx · _detail_estimate_table.html | 519fd6d |
| 3 | 보드 🔴 기본 선택 · 상세 견적 버튼 · 견적 자리 · _job_status 이름/문구 | babbc2c |

## 파일 배치 (확정)

- inputs: `<회차>/web/targets_<견적잡id>.json` — `{"items":[{productId,판매자상품코드,imageUrls,제품이미지총수,잘림}], "제외":[{판매자상품코드,사유}], "선택":N}`
- CLI `--run-dir`: `<회차>/web/detail_<견적잡id>/`
- 견적 결과: `detail_<견적잡id>/estimate.json` · 접수/이어서 확인: `detail_<견적잡id>/summary_<잡id>.json`
- 05-04 호출 모양: `jobs.create_job("detail_submit", run_dir=…, parent_job_id=<견적>, targets_path_override=<견적 targets>, max_credits=N)` · `jobs.create_job("detail_poll", run_dir=…, parent_job_id=<접수>, targets_path_override=<같은 파일>)`

## 검증

- `webapp/tests` 전체: **563 passed** (시작 시 535 → +28: argv 4 · jobs 10 · routes 13 · board 1)
- `node --check webapp/static/board.js` OK
- `no_commit_guard.sh` OK
- `| safe` 0건 (새 템플릿·board.html·_job_status.html)
- acceptance grep: `class DetailArgv`=1 · jobs.py `detail_estimate` 18 · `detail_max_poll_min`=1 · `"/jobs/detail/estimate"`=1 · `상세입력목록(`=1 · 견적 표 `예상 크레딧` 2 · board.js `/jobs/detail/estimate` 1 · `detail-estimate-btn` 1 · `상세 견적` 2
- `security_curl.sh` 는 실행 중 서버(:8765)를 때리므로 **돌리지 않았다** (사용자 서버 POST 금지 제약). 같은 방어(토큰·Origin·GET 405)는 TestClient 테스트 3종으로 고정

## Deviations from Plan

**1. [Rule 1 - 테스트 정합] 기존 `test_불사자잡은_전역_쓰기가드에_안_들어간다` 의 BULSAJA_KINDS 등식 갱신**
- 계획대로 detail 3종을 BULSAJA_KINDS 에 넣으면 멤버를 통째로 고정한 등식이 깨진다. 의도된 변경이라 등식을 5멤버로 갱신(주석으로 Phase 5 추가 명시). 커밋 d038906

**2. [Rule 2 - 정확성] `_상세폴더` 가 부모 잡의 회차 일치도 검사**
- 계획은 kind 체인만 요구. 다른 회차의 견적을 부모로 주면 그 회차의 detail 폴더를 이 회차 잡이 쓰게 된다 → 회차 불일치 ValueError 추가

**3. [Rule 2 - 정확성] 같은 productId 중복 제외 · 요청 키 중복 제거**
- 두 계정 행이 같은 불사자 상품으로 해소되면 같은 상품을 두 번 접수(크레딧 이중)할 수 있어 두 번째를 제외 사유와 함께 뺀다

**4. [Rule 2 - UX] `_job_status.html` failed 문구를 detail 종료코드(2/3/4/5)로 가름**
- 기존 "광고 설정이 바뀐 건 없다" 문구가 상세 잡에선 틀린 안내라 kind 로 갈랐다. 특히 exit 3 은 실패가 아니라 "이어서 확인" 안내

**5. [추가 테스트] `test_board.py::test_상세견적_버튼과_자리가_보드에_있다`** — 보드 렌더에 버튼·자리가 있고 화질/장수 칸이 없음을 고정

## UI 자동 검증 (uat-verifier) — 오케스트레이터 대기

이 실행기는 에이전트를 띄울 수 없어 **uat-verifier 는 pending** 이다(05-02·05-04 UAT 와 묶어 실행). 조건:
- 사용자 서버(PID 41865, :8765) 재시작·POST 금지 → **격리 DB·격리 포트 인스턴스**에서 확인
- 🔴 **견적 버튼을 실데이터로 누르면 불사자 MCP 조회(my_profile · workdata 태그)가 나간다 — 크레딧은 0 이지만 외부 호출이다.** 격리 인스턴스에서도 불사자 호출을 막으려면 `jobs.spawn` 을 가짜로 두거나, 견적 산출물(estimate.json)을 미리 깔고 결과 조각만 확인
- 확인 항목: ① 보드에 `🔴 기본 선택`·`상세 견적 — 크레딧 0` 버튼이 보이고 화질·장수 입력이 없다 ② `🔴 기본 선택` 이 필터 통과·기작업 아님·팬아웃 조회됨 행 중 🔴 만 고르고 요약 줄에 🔴/🟡 수가 뜬다 ③ 🟡 를 수동 체크하면 요약에 🟡 가 늘어난다 ④ 선택 0개면 상세 견적 버튼이 비활성 ⑤ 관문 전부 제외 시 `#job-error` 에 400 사유(상품별)가 문자열로 보인다 ⑥ 견적 조각이 선택→관문 제외→기작업 스킵→접수, 총 장수·예상 크레딧·잘린 상품·계정·잔액(참고)을 보여 준다
- 참고: 실운영 2026-09-20 회차는 산출물(2026-09-25T00:14) 이후 확인이 0건이라(05-02) 지금 누르면 **전부 관문 제외 → 400** 이 정상이다. 검수 화면에서 `다시 확인` 을 눌러야 열린다

## Known Stubs

없음. (접수 버튼은 계획상 05-04 몫이다 — `detail-estimate-job` hidden input 은 견적 잡이 done 이면 채워진다.)

## Threat Flags

없음 — 새 표면(POST /jobs/detail/estimate)은 계획 threat_model T-05-10~14 에 있고 전부 반영됐다(서버 재구성·모르는 키 400 · Nick/PlainArg · BULSAJA 사전점검 409 + --expect-nick · security.guard 토큰/Origin · inputs 경로는 웹앱이 web/ 아래 생성).

## Self-Check: PASSED

## uat-verifier 결과 (2026-09-25 · 05-02/03/04 통합 1회 · 오케스트레이터 실행)

- **판정: PASS** — 항목 ①~⑮ 전부 pass · P0~P2 없음 · P3 1건(배너 검수 스트립 figure 접근성 이름 — Phase 4 기존 마크업, 스캐너 오탐 가능)
- 격리 인스턴스(DB 복사본·별도 포트)만 사용 · 사용자 서버(:8765)·실 webapp.db·실 run-dir 미접촉 · 불사자 호출 0 · 크레딧 0 · 소스 변경 0
- 사람 몫: 심미만 — `~/.claude/uat/uat-artifacts/20260925-seller-control-tower/board-detail-result.png`, `banner-review.png`
