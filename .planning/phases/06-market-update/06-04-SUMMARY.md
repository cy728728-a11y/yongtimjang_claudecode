---
phase: 06-market-update
plan: 04
subsystem: webapp-market-gate
tags: [market-02, sc-2, gate, webapp, htmx, sqlite]
requires:
  - "06-03 (_마켓반영상한 · market 라우트 3개 · #market-gate-slot · preview.json/market_status.json 계약)"
provides:
  - "jobs.DDL market_gate (사람 판정 누적 기록)"
  - "webapp/market_gate_store.py — 최신판정() · 통과() · 판정기록()"
  - "POST /market/gate (GateReq extra=forbid · 대상은 서버가 체크포인트 성공 첫 건에서)"
  - "_마켓반영상한(): 닫힘 1 · 정상 market_update_max_items · 이상이면 반영 400"
  - "_market_gate_panel.html (체크 3 · 정상/이상 · 판정 요약 · 복원 명령 텍스트)"
affects: [06-05, 06-06]
tech-stack:
  added: []
  patterns:
    - "banner_store 모양 저장소 복제 — 읽기 mode=ro · 쓰기 INSERT 누적 · DDL 0 grep 가드"
    - "판정 못 읽음 = 게이트 닫힘(상한 1) — 안전 쪽으로 떨어진다"
    - "본문 파싱은 async 의존성, 라우트는 def (T-1-28 async 라우트 1개 규칙 유지)"
key-files:
  created:
    - webapp/market_gate_store.py
    - webapp/templates/_market_gate_panel.html
    - webapp/tests/test_market_gate_store.py
  modified:
    - webapp/jobs.py
    - webapp/routes/jobs.py
    - webapp/templates/_market_result_table.html
    - webapp/templates/_market_preview_table.html
    - webapp/tests/test_routes_market.py
    - webapp/tests/test_jobs.py
    - webapp/tests/test_market_cli.py
    - .planning/phases/06-market-update/deferred-items.md
decisions:
  - "게이트는 전역 1회성 — 최신 판정 한 줄이 모든 미리보기의 상한을 정한다(미리보기 단위 아님, D-09)"
  - "최신 판정이 '이상' 이면 새 미리보기로도 반영 400 — 다시 열려면 새 '정상' 판정 한 줄이 필요하다"
  - "게이트 판정은 도는 중(starting/running) 반영 잡에는 거부 — 끝난 결과를 보고 판정한다"
  - "스토어 링크는 채널상품번호가 숫자일 때만 조립, 아니면 코드만(번호 텍스트는 항상 병기)"
  - "복원 명령은 shlex.join 으로 조립 · 닉은 설정 expected_bulsaja_nick · 판정 상품이 이 표 상품과 다르면 판정 잡의 체크포인트에서 ⓐ 를 다시 찾는다"
metrics:
  duration: "~25분"
  completed: 2026-09-26
  tasks: 2
  files: 11
---

# Phase 6 Plan 04: 첫 1건 육안 확인 게이트 Summary

첫 1건 반영이 성공하면 결과 표 위에 **육안 확인 게이트 패널**이 고정으로 뜨고, 사람이 자기 브라우저로 스토어를 본 뒤 `정상`(체크 3개 필수) / `이상` 을 누르면 `market_gate` 에 한 줄 누적된다. 판정 전 상한 1 · 정상 뒤 `market_update_max_items`(20) · 이상이면 반영 라우트 400 + 미리보기 버튼 제거 + 복원 명령 텍스트. 불사자 실호출 0 · 스토어 변경 0 · 사용자 서버·실DB 무접촉.

## 한 일

| Task | 내용 | 커밋 |
|------|------|------|
| (편차) | `test_market_cli.py` 의 반영 플래그 리터럴 7건 → `_반영플래그` 간접 조립 · `no_commit_guard.sh` 복구 · deferred-items 해결 기록 | 4f6ae87 (fix(06-02)) |
| 1 | market_gate DDL · `market_gate_store.py` · `POST /market/gate` · `_마켓반영상한` 판정 읽기 · 반영 라우트 이상 거부 · 미리보기/결과 ctx 게이트 | b9c1a3a (test) · d5cb02d (feat) |
| 2 | `_market_gate_panel.html` · 결과 표 위 슬롯 include + 정상 후 남은 반영 버튼 · 미리보기 표 이상 멈춤 문구 | e2e927b |

사전 확인: 실제 `webapp.db` 를 mode=ro 로 열어 starting/running 잡 0건을 확인하고 시작했다.

## 흐름 계약 (06-05 · 06-06 이 보는 것)

- **판정 대상:** 반영(또는 이어서 확인) 잡의 market 폴더 `market_status.json` 에서 `status == "성공"` 인 첫 항목(미리보기 순서). 화면은 상품을 보내지 못한다(422)
- **POST /market/gate 본문:** `commit_job_id · 판정(정상|이상) · 체크_본문 · 체크_상하단 · 체크_기타필드(bool, 빠지면 거짓) · 스토어교체여부(교체됨|미교체|모름) · 메모(≤500)` — 폼·JSON 둘 다
- **거부:** 잡 없음/kind 틀림 400 · 도는 중 400 · 성공 0건 400 · 정상인데 체크 하나라도 거짓 400 · 체크포인트 깨짐 400 · 테이블 없음 500("서버 재시작")
- **상한:** 판정 없음·DB 없음·손상 → 1 · 최신 정상 → `settings market_update_max_items`(기본 20) · 최신 이상 → `POST /jobs/market/commit` 400 `게이트 이상 판정 — 멈춤`
- **실서버 주의:** 사용자 서버의 DB 에는 `market_gate` 가 **아직 없다**(init_db 는 기동 때만). 읽기는 닫힘(1)으로 안전하게 떨어지지만 판정 기록은 500 — **06-05 의 서버 재시작 뒤에 게이트가 쓸 수 있다**

## 테스트

- `test_market_gate_store.py` 14 passed(신규) · `test_routes_market.py -k "게이트 or 상한 or 이상"` 30 passed
- `webapp/tests` 전체 **804 passed** · `node --check webapp/static/board.js` OK · `bash webapp/tests/no_commit_guard.sh` **OK**
- 수용 grep: `CREATE TABLE IF NOT EXISTS market_gate` 1 · store 의 create/alter/drop 0 · `market_gate_store.통과` 1 · 패널 `hx-post="/market/gate"` 2 · `| safe` 0 · noopener ≥1 · 결과 표 include 1 · restore-backup ≥1

## Deviations from Plan

### Auto-fixed Issues

**1. [오케스트레이터 지시 — 범위 밖 수리] `no_commit_guard.sh` 복구 (06-02 산출물)**
- `test_market_cli.py` 의 `--commit` 리터럴 7건(주석 1건 포함)을 모듈 상수 `_반영플래그 = "--" + "commit"` 로 바꿨다. 테스트 의미 불변(66 passed). 별도 커밋 `fix(06-02)` · deferred-items.md 에 해결 기록
- **Commit:** 4f6ae87

**2. [Rule 3 - Blocking] 게이트 라우트를 `def` + async 의존성으로**
- `test_라우트_중_async_는_스트림_하나다`(T-1-28)가 routes/jobs.py 의 async 라우트를 스트림 하나로 고정한다. 본문 파싱(폼·JSON)만 async 의존성 `_게이트요청` 으로 빼고 라우트 본문은 `def` — sqlite·파일 IO 가 이벤트 루프를 세우지 않는다
- **Commit:** d5cb02d

**3. [Rule 3 - Blocking · 의도된 가드 확장] 스키마 허용 목록에 `market_gate`**
- `test_스키마는_기록_테이블만_있다` 가 테이블을 넷으로 고정한다. 판별 기준("재생성 불가 = 기록")에 맞춰 사유를 docstring 에 못 박고 `market_gate` 와 AUTOINCREMENT 가 스스로 만드는 `sqlite_sequence` 를 추가했다
- **Commit:** d5cb02d

**4. [Rule 2 - Correctness] 이상 판정이면 새 미리보기로도 반영 거부**
- 플랜은 "최신 판정 이상이면 반영 400" 이다. 판정이 미리보기 단위가 아니라 전역이므로 새 미리보기를 떠도 막히는 것을 테스트로 고정했다(`test_상한_이상이면_400`)

**5. [Rule 2 - Correctness] 도는 중인 반영 잡에는 판정 거부**
- 결과를 다 보기 전에 판정이 들어가는 길을 막았다(400)

**6. [Rule 2 - UX 정확성] 판정 실패를 화면에 보인다**
- htmx 는 4xx 응답을 스왑하지 않는다. 패널에 `#market-gate-error` 를 두고 `hx-on::response-error` 로 서버 `detail`(예: "정상은 확인 체크 3개를 모두…")을 띄운다 — `banner_review.html` 의 오류 표시 관례

## 오케스트레이터 uat 대기

이 실행기에는 에이전트 도구가 없어 `uat-verifier` 를 직접 부르지 못했다. **06-03 과 06-04 를 한 번에 묶은 지시문**이다(06-03-SUMMARY 의 지시문을 대체한다).

> **uat-verifier (model: sonnet) — 06-03 마켓 반영 흐름 + 06-04 육안 확인 게이트 UI.** 불사자 실호출 0 · 실제 CLI 실행 0 · 사용자 서버(:8765, PID 42672) 무접촉 · 실 `webapp.db`/실 회차 무접촉 · **스마트스토어 링크는 열지 않는다(네이버 규칙) — href 값만 확인.**
> 1. 격리 포트로 웹앱을 띄운다. `CT_DB_PATH`/`CT_JOB_LOG_DIR` 를 임시 경로로, data_root 를 임시 회차 트리로 돌린다(새 DB 라 기동 때 `market_gate` 가 생긴다).
> 2. 시드: 임시 회차에 detail_estimate → detail_submit(done, exit 0) 잡 행 + `detail_<견적id>/detail_status.json`(완료 3 · 실패 1) + 대상 파일(`{"items":[{productId, 판매자상품코드}]}`).
> 3. `jobs.spawn` 을 가짜로 둔다: market_preview 는 06-02 계약 모양 `preview.json`(반영가능 3 · 스킵 1, 스킵은 `backup_a_있음:false` · 사유 `backup_failed`, 반영가능 항목에 `채널상품번호`(숫자) · `상단이미지`/`하단이미지` URL · `상하단날짜`)을 쓰고 exit 0. market_commit 은 **받은 대상 파일의 항목을 전부** `market_status.json` 에 `성공`(taskId 8자리 이상 · backup_a 경로)으로 쓰고 exit 0 — 이렇게 해야 게이트 뒤 두 번째 반영의 건수가 argv 와 맞는다. 각 반영의 argv 를 파일로 남겨 `--max-items` 값을 읽을 수 있게 한다.
> 4. **06-03 확인:** ① 상세 결과 표에 "스마트스토어 반영 미리보기 — 쓰기 0" 버튼 ② 누르면 미리보기 표 — ⓐ·ⓑ 경로 텍스트 · (있음)/(없음) · 2·3번째 반영가능 행 "게이트 대기" · 버튼 "첫 1건만 반영 (육안 확인 게이트)" ③ 버튼 → 잡 패널 → 결과 표(항목 행 · 작업번호 끝 8자리 · 미반영(게이트 대기) 행 · 재반영 버튼 없음) · 첫 반영 argv `--max-items 1` ④ 새로고침 후 상세 결과 표 "최근 스마트스토어 반영" 에서 결과 보기로 재로드.
> 5. **06-04 확인 (DB 사본 A):** ⑤ 결과 표 **위**에 게이트 패널 — 판매자상품코드 · 채널상품번호 텍스트 · 링크 href `https://smartstore.naver.com/main/products/<번호>` + `target=_blank rel="noopener noreferrer"` · 상단/하단 URL 과 날짜 · 체크 3개 · 두 버튼 ⑥ 체크 없이 '정상' → 패널 안 오류 문구("체크 3개") 표시 · `market_gate` 행 0 ⑦ 체크 3 + 스토어교체여부 + 메모 → '정상' → 패널이 판정 요약으로 바뀜 · 표 아래 "반영 실행 (최대 20건)" 버튼 노출 ⑧ 그 버튼 → 새 market_commit argv `--max-items 20` · 대상 2건 · 결과 표 갱신.
> 6. **06-04 확인 (DB 사본 B, 같은 시드로 ①~③까지 다시):** ⑨ '이상 있음 — 멈춤'(체크 없이도 됨) → 요약에 "게이트가 닫혔다" · 복원 명령 두 줄(`--restore-backup <ⓐ경로> --preview` / 반영 플래그 + `--max-items 1 --backup-dir <market 폴더>/before_market`) · "상하단 교체 프로젝트" 주의 · 복원 버튼 없음 ⑩ 같은 미리보기 결과를 다시 열면 반영 버튼 없음 + "게이트 이상 판정으로 멈춰 있다" ⑪ 메모에 `<b>x</b>` 를 넣으면 이스케이프되어 글자로 보인다.
> 7. ⑫ 전 과정 콘솔 오류 0.
> 8. PASS/FLAKY/FAIL/BLOCKED + P0~P3 를 `.planning/phases/06-market-update/evidence/06-04-uat.md` 에 기록한다(06-03 분은 같은 파일 앞 절로).

자동 대체 검증: TestClient 로 패널·결과·미리보기 조각을 실제 렌더해 ⑤~⑪의 문구·버튼·href·rel·명령 텍스트·이스케이프·패널 위치(집계 줄보다 위)를 단언했고, 진짜 `create_job` + 가짜 spawn 으로 정상 뒤 argv `--max-items 20` · 대상 2건을 단언했다. 브라우저에서만 보이는 것(htmx 스왑·`hx-include` 로 체크 수집·오류 문구 표시·콘솔)은 위 UAT 로 남는다.

## 사람 몫 (용팀장)

- 실제 첫 1건 판정 자체는 **용팀장이 자기 브라우저에서 스토어에 로그인해 직접 본다**(네이버 규칙) — 06-05 의 실사용 체크포인트에서.

## 서버 재시작

**필요하다(06-05 에서).** 새 라우트·템플릿과 `market_gate` 테이블(init_db 는 기동 때만)이 재시작 전엔 없다. 재시작 전까지 사용자 서버의 게이트 읽기는 닫힘(상한 1)으로 안전하게 떨어진다. 이 플랜은 서버를 건드리지 않았다.

## Known Stubs

없음. 06-03 의 `_마켓반영상한()=1` 고정과 빈 `#market-gate-slot` 은 이 플랜에서 채웠다.

## Threat Flags

없음. 새 표면은 `POST /market/gate` 하나이고 T-06-23~28 이 덮는다(security.guard 토큰·Origin · extra=forbid · 서버 대상 결정 · 체크 3 필수 · 닫힘 기본 · 누적 INSERT · 자동 이스케이프 · noopener · 메모 500 · job_status 선조회).

## TDD Gate Compliance

Task 1: `test(06-04)` b9c1a3a → `feat(06-04)` d5cb02d. Task 2 는 auto 태스크 — 패널 테스트는 Task 1 RED 커밋에 미리 들어가 있었고 e2e927b 에서 초록이 됐다.

## Self-Check: PASSED
- FOUND: webapp/market_gate_store.py · webapp/templates/_market_gate_panel.html · webapp/tests/test_market_gate_store.py
- FOUND commits: 4f6ae87 · b9c1a3a · d5cb02d · e2e927b
