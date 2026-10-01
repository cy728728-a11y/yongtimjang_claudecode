---
phase: 02-prune-ads
plan: 03
subsystem: webapp 삭제 트랙 (routes/prune · 템플릿 · prune.js)
tags: [prune, web-slice, typed-confirm, idempotency, retry, safe-04, safe-05, safe-06, safe-07, flow-03, flow-06, eng-04]
requires:
  - "02-01 run_ads prune --only-ads/--preview-out/--max-items/--backup-tag · 산출물 스키마"
  - "02-02 prune_preview/prune_commit kind · create_job(prune_max_items, prune_retry) · 성공 자식 BusyError"
provides:
  - "POST /jobs/prune/preview {run_dir, accounts} · /jobs/prune/commit {preview_job_id, typed_count} · /jobs/prune/retry {commit_job_id, typed_count}"
  - "routes/prune.결과표 — prune_preview · prune_commit 조각 (get_job_result 트랙 병합)"
  - "_삭제상한() (설정 prune_max_items 한 곳) · _재시도대상() (실패 ∩ 미리보기 adIds 한 곳)"
  - "flow.중단사유 recheck_failed"
  - "board.html #prune 섹션(회차 블록 안) · static/prune.js"
affects: [02-06]
tech-stack:
  added: []
  patterns: ["쿠팡 트랙 1:1 복제(라우트·조각·위임 JS)", "산출물만 읽는 ctx", "4중 마찰(맨 아래·접힘·contrast·건수 타이핑)", "서버 유도 부분집합 재시도"]
key-files:
  created:
    - webapp/routes/prune.py
    - webapp/templates/_prune_preview_table.html
    - webapp/templates/_prune_result_table.html
    - webapp/static/prune.js
    - webapp/tests/test_routes_prune.py
  modified:
    - webapp/main.py
    - webapp/routes/jobs.py
    - webapp/flow.py
    - webapp/templates/board.html
    - webapp/templates/_job_status.html
decisions:
  - "재시도는 같은 미리보기 파일 재사용 대신 실패 adId ∩ 미리보기 adId 부분집합 파일로 보낸다(D-08 변형 — 이미 지운 수천 건이 '재조회에 없음'으로 결과 표를 덮지 않게). 진행 파일 재개는 2차 방어"
  - "커밋 재요청은 409(쿠팡은 400 — D-09 의 의도적 차이)"
  - "미리보기 산출물의 최상위 adIds 와 계정별 targets 집합이 다르면 커밋 400 — 본 표와 --only-ads 가 어긋나는 산출물 차단"
  - "같은 회차 prep 도는 중 판정: prep run_dir 이 비면(CLI 가 오늘 날짜로 정함) 오늘 회차로 본다"
  - "결과 화면의 backup_failed 는 flow 공용 문구(입찰가 기준 '광고비') 대신 prune 전용 문구로 덮는다"
  - "D-06 exit 5 는 구조적으로 발동 불가(02-01) → 결과 표에 new_since_preview 를 '미리보기 이후 새로 꺼진 N건 — 이번엔 안 지움' 으로 보인다"
metrics:
  duration: "약 40분"
  completed: 2026-10-01
  tasks: 3
  files: 10
---

# Phase 2 Plan 03: 꺼진 소재 정리 웹 슬라이스 Summary

보드 회차 화면에 꺼진 소재 정리를 미리보기 → 삭제 → 실패분 재시도 3단계로 붙였다. 틀은 쿠팡 트랙을 그대로 복제했다. 브라우저가 보내는 건 잡 id와 사람이 타이핑한 건수뿐이다. 무엇을 지울지는 서버가 CLI 산출물에서만 정한다.

## 무엇이 바뀌었나

**routes/prune.py (신규 · 트랙 소유)**
- `POST /jobs/prune/preview`: 회차 화이트리스트 밖이면 400, 같은 회차 prep 이 도는 중이면 409(Pitfall 7), 같은 미리보기가 도는 중이면 409(SINGLETON). 요청 모델은 `extra=forbid` 이고 대상 필드가 없다.
- `POST /jobs/prune/commit`: 아래 순서로 검사한 뒤 create_job 을 부른다.
  1. 부모 종류·상태 검사: 종류가 다르면 400, 도는 중이면 409, 실패했으면 400.
  2. 24시간 넘은 미리보기는 400.
  3. 산출물이 깨졌거나 adIds 와 targets 가 어긋나면 400.
  4. 같은 미리보기의 삭제가 도는 중이거나 이미 성공했으면 409.
  5. 대상 0건이거나 상한을 넘으면 400.
  6. 타이핑한 건수가 서버가 센 수와 다르면 409.
  7. `create_job("prune_commit", targets_path_override=부모 result_path, prune_max_items=_삭제상한())` — `--account` 에는 대상이 있는 계정만 정렬해서 넣는다.
- `POST /jobs/prune/retry`: 커밋 잡이 done 이어야 한다. 그다음 원 미리보기 검사(24h)와 LIVE 커밋 409 를 본다. 대상은 `_재시도대상` 으로 정한다(커밋 산출물의 실패·재시도소진 ∩ 미리보기 adIds). 0건·상한 초과면 400, 타이핑 불일치면 409. 통과하면 `only_ads=부분집합, prune_retry=True, parent=원 미리보기` 로 잡을 만든다.
- `_삭제미리보기ctx`: 계정별 요약(삭제 대상 · 남김 검수중/거부 · 백업 파일명 · 중단/건너뜀)과 전 행 표, 상태 플래그(`이미삭제`/`삭제중`/`만료`/`상한초과`/`삭제예정`)를 만든다.
- `_삭제결과ctx`: 계정별 성공/이미없음/실패/제외/새로 꺼짐/중단 수, 실패 표와 제외 표(사유는 한국어 라벨), `재시도건수`·`재시도가능` 을 만든다. 정렬은 중단 계정이 맨 위, 그다음 실패 계정, 마지막이 깨끗한 계정이다.

**공유 파일**: `main.py` 라우터 등록 · `routes/jobs.get_job_result` 병합에 `_삭제트랙`(기존 키 우선) · `flow.중단사유` 에 `recheck_failed` · `_job_status.html` 작업이름 2종 + 진행 문구 + 종료코드 1/2 문구 · `board.html` `{% if run_dir %}` 안 `#prune` 섹션(계정 체크박스는 서버 `accounts` 로 렌더) + `prune.js` 스크립트 태그(coupang.js 뒤).

**템플릿·JS**
- `_prune_preview_table.html`: 계정 요약 표 → `#prune-preview-grid` + `tojson` 데이터 블록 → 분기(이미삭제/삭제중/상한초과/만료/삭제예정). 삭제예정일 때만 접힌 `details` 안에 건수 입력칸과 contrast 버튼을 그린다.
- `_prune_result_table.html`: 합계 → 새로 꺼짐 경고 → 계정 표 → 실패 표 → 제외 표 → 접힌 "실패분만 재시도 (N건)".
- `prune.js`: 미리보기 버튼을 켜서 `htmx:afterSwap` 때 Tabulator 를 마운트한다(groupBy 계정 · 접힘 · 480px 가상 렌더링). 삭제·재시도 버튼은 위임으로 받는다. 정수 검증 → 입력 비우기 → `{잡 id, typed_count}` 만 POST 한다.

## 검증

- `.venv-web/bin/pytest webapp/tests -p no:warnings` → **1061 passed** (02-02 의 1005 + 신규 56)
- `node --check webapp/static/prune.js` OK · `bash webapp/tests/no_commit_guard.sh` OK
- `security_curl.sh`: 운영 :8765 를 건드리지 않으려고 격리 서버(CT_PORT=8799, CT_DB_PATH·CT_DATA_ROOT·CT_AUDIT_PATH 를 scratchpad 로, CT_SKIP_STARTUP_REAP=1)를 띄워 돌렸다. **보안 9종 전량 PASS**. 새 POST 3개도 직접 쳐 봤다. 토큰이 없으면 403, Origin 이 evil 이면 403, 정상 토큰이면 422(앱 로직 도달)다. 끝나고 서버를 내렸고, :8765 는 PID 45857 그대로다.
- 모든 테스트는 가짜 spawn(`안띄운다`)으로 돌렸다. 네이버 광고 API 호출 0, 실제 삭제 0.

## Commits

| Task | Gate | Commit | 내용 |
|------|------|--------|------|
| 1 | RED | e1c232e | 미리보기 라우트·조각·보드 자리 테스트 |
| 1 | GREEN | bdc30d9 | 미리보기 슬라이스 |
| 2 | RED | bb3238b | 커밋 라우트·결과 조각 테스트 |
| 2 | GREEN | 22a4fa2 | 커밋 슬라이스 + flow recheck_failed |
| 3 | RED | 8d10311 | 재시도 라우트·조각 테스트 |
| 3 | GREEN | a42e00d | 재시도 슬라이스 + 가드 403 테스트 |

## Deviations from Plan

**1. [Rule 2 - 안전] 미리보기 산출물의 adIds ↔ targets 일치 검사 추가**
- 커밋은 최상위 `adIds` 를 `--only-ads` 로 쓰고, 화면과 타이핑 건수는 계정별 `targets` 로 센다. 두 집합이 다르면 사람이 본 것과 다른 게 지워진다. 그래서 어긋나면 400 을 낸다. (22a4fa2)

**2. [Rule 1 - 정합] 재시도 건수 안내를 교집합 기준으로**
- 처음엔 결과 조각이 실패 행 전체 수를 안내했다. 그런데 라우트는 실패 ∩ 미리보기 수를 세므로, 미리보기 밖 실패가 섞이면 화면 숫자를 그대로 쳐도 409 가 난다. 그래서 `_재시도대상()` 하나를 조각과 라우트가 같이 쓰게 했다. (a42e00d)

**3. [Rule 2 - 보안 검증] 새 POST 3개 가드 회귀 테스트 추가 · security_curl 은 격리 포트로**
- security_curl.sh 는 실행 중인 서버가 있어야 돈다. 운영 :8765 재시작이 금지라 격리 서버로 돌렸다. TestClient 수준의 403 테스트도 함께 넣었다.

## Known Stubs

없음. 계정 체크박스·표 행·결과는 전부 서버 값이나 산출물에서 온다.

## Threat Flags

없음. 새 표면은 POST 3개뿐이고 계획의 T-02-16~24 에 이미 들어 있다. 가드는 security_curl 과 테스트로 확인했다.

## TDD Gate Compliance

세 태스크 모두 `test(02-03)` 를 먼저 커밋하고 그다음 `feat(02-03)` 를 커밋했다. RED 단계에서 신규 테스트가 실패하는 것을 확인했다(모듈·라우트·템플릿 부재). 가드 403 테스트는 GREEN 커밋에 같이 넣었다. 기존 미들웨어 동작을 고정하는 회귀 테스트라 RED 가 성립하지 않는다.

## Self-Check: PASSED
