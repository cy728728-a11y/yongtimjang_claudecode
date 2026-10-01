---
phase: 02-prune-ads
plan: 02
subsystem: webapp 잡 엔진 (jobs · argv · audit)
tags: [prune, safety, audit, idempotency, orphan-reap, eng-04, eng-05, flow-07, safe-07]
requires:
  - "02-01 run_ads prune --only-ads/--preview-out/--max-items/--backup-tag"
provides:
  - "JobKind/KINDS prune_preview · prune_commit (prune_commit ∈ WRITE_KINDS + caffeinate -i, prune_preview ∈ SINGLETON_KINDS)"
  - "create_job(prune_max_items, prune_retry) — 부모 done/0 · 대상 · 상한 ≥1 필수, 성공 자식 있으면 BusyError"
  - "jobs.reap_on_startup() -> int (CT_SKIP_STARTUP_REAP · DB 미생성 · PID 재사용 검사)"
  - "webapp/audit.py audit_path · summarize · record (append-only JSONL)"
  - "settings.DEFAULTS prune_max_items=8000 · audit_path=''"
  - "paths.data_root CT_DATA_ROOT 우선"
affects: [02-03, 02-04, 02-05, 02-06]
tech-stack:
  added: []
  patterns: ["커밋 후 감사(대기열 → commit → 재조회 → record)", "reap 을 가드 트랜잭션 밖 별도 커밋으로", "conftest autouse 환경변수 격리"]
key-files:
  created:
    - webapp/audit.py
    - webapp/tests/test_audit.py
  modified:
    - webapp/jobs.py
    - webapp/argv.py
    - webapp/main.py
    - webapp/settings.py
    - webapp/paths.py
    - webapp/tests/conftest.py
    - webapp/tests/test_jobs.py
    - webapp/tests/test_argv.py
decisions:
  - "starting 시한 초과(failed/-1)도 쓰기 잡 종료로 보고 감사 1줄 — 계획의 3곳 + 1곳"
  - "감사 대기열은 커밋 뒤 행을 다시 읽어 아직 LIVE 면 남겨 둔다(다른 스레드 미커밋 reap 대비) + 락"
  - "main.py 는 jobs 엔진을 job_engine 별칭으로 import — routes.jobs 가 같은 이름을 덮는다"
  - "_남의프로세스: lstart 초 단위라 1초 여유, ps 는 LC_ALL=C 로 호출"
  - "prune_preview 도 run_dir 필수(산출물이 web/ 밑이어야 커밋의 _override_targets 를 통과)"
metrics:
  duration: "약 30분"
  completed: 2026-10-01
  tasks: 3
  files: 10
---

# Phase 2 Plan 02: 공용 안전 계약 (prune kind · 멱등 · 기동 정리 · 감사) Summary

잡 엔진에 꺼진 소재 정리 잡 2종을 등록하고, 모든 쓰기 버튼이 공유하는 안전 계약 네 가지를 넣었다. 미리보기당 커밋 1회(409), 서버 기동 시 고아 정리, 쓰기 잡 감사 1줄, 상한 없는 삭제 거부. 그 과정에서 `create_job` 가 가드 트랜잭션 안에서 `_reap` 을 돌려 거부(롤백) 시 끝난 잡의 종료코드가 사라지던 잠복 버그를 고쳤다.

## 무엇이 바뀌었나

**webapp/argv.py**: `AdsArgv.subcommand` 에 `"prune"` 을 넣고 `max_items` · `backup_tag`(`^[A-Za-z0-9_-]{1,64}$`) 필드를 추가했다. 둘 다 None 이면 플래그를 붙이지 않는다.

**webapp/jobs.py**
- kind 등록: `prune_commit` 은 WRITE_KINDS 에 넣고 caffeinate 를 붙인다. `prune_preview` 는 SINGLETON_KINDS 에 넣는다. 둘 다 BULSAJA_KINDS 에는 넣지 않는다.
- `_build_argv`: 미리보기는 `--preview-out web/prune_preview_<id>.json --backup-tag <id>` 로 조립한다. 커밋은 대상 파일이나 상한이 없으면 ValueError 를 내고, 있으면 `caffeinate -i … prune --commit --only-ads --max-items --backup-tag` 로 조립한다.
- `create_job(prune_max_items, prune_retry)`: 두 인자를 prune_commit 이 아닌 kind 에 주면 ValueError 다. 상한은 1 이상 정수만 받는다(bool 은 거부). 대상(override 또는 only_ads), 부모, 회차가 하나라도 없으면 거부한다. 트랜잭션 안에서 부모가 prune_preview·done·0 인지 확인하고, 같은 부모의 성공 커밋 자식이 있으면 BusyError 를 낸다(prune_retry 일 때만 예외).
- 롤백 버그: `_reap` 을 가드 트랜잭션 **밖**의 별도 짧은 트랜잭션으로 옮겼다.
- 감사 훅: `_finish`, `_reap` 의 orphaned 분기, `_reap` 의 starting 시한 초과 분기, spawn 실패 분기에서 `_감사예약` 을 부른다. 파일 기록은 `_커밋후감사` 가 DB 커밋 뒤에만 한다. `_reap(cx)` 를 부르는 조회 함수 4곳과 create_job ⓪을 이걸로 바꿨다. 한 job_id 는 `_감사함` 집합으로 한 번만 기록한다.
- `reap_on_startup()` 과 `_남의프로세스()`: `ps -o lstart=` 시작시각이 잡 started_at 보다 늦으면 orphaned 로 바꾼다. ps 가 실패하거나 출력을 파싱하지 못하면 건드리지 않는다.

**webapp/main.py**: lifespan 의 URL print 앞에 `[기동] 고아 잡 N건 정리` 를 찍는다. 정리가 실패해도 서버는 뜬다.

**webapp/audit.py**(신규): `audit_path`(CT_AUDIT_PATH > 설정 > 데이터루트/control-tower/audit.jsonl), `summarize`(prune_commit·bids_commit·detail_* 별 요약, 모르면 None), `record`(실패는 삼킨다, argv 는 싣지 않는다).

**settings / paths / conftest**: `prune_max_items: 8000`, `audit_path: ""` 를 추가했다. `CT_DATA_ROOT` 를 우선하게 했다. autouse 픽스처 `_실데이터_격리` 를 추가했다(CT_SKIP_STARTUP_REAP=1, CT_AUDIT_PATH=tmp).

## 검증

- `.venv-web/bin/pytest webapp/tests -p no:warnings` → **1005 passed** (기존 952 + 신규 53)
- `.venv/bin/python3 -m pytest -q .claude/skills/naver-ads-weekly/scripts` → 129 passed
- `bash webapp/tests/no_commit_guard.sh` → OK
- 실 webapp.db 는 테스트 전후 `75|2026-09-30T20:07:13+09:00` 로 같다(DB_UNCHANGED). `~/python_work/data/control-tower/` 는 전후 모두 없다.
- 운영 :8765 서버는 재시작하지 않았다. 반영은 02-06 에서 한다.

## Commits

| Task | Gate | Commit | 내용 |
|------|------|--------|------|
| 1 | RED | 08cd74c | 감사·격리·설정키 실패 테스트 |
| 1 | GREEN | d10493f | audit.py · 설정 · CT_DATA_ROOT · conftest 격리 |
| 2 | RED | 976c7e0 | prune 잡 2종·멱등 실패 테스트 |
| 2 | GREEN | bed9610 | argv prune · jobs kind · create_job 검사·멱등 |
| 3 | RED | 9b2f178 | 롤백·기동 reap·감사 종료지점 실패 테스트 |
| 3 | GREEN | ce27995 | 롤백 수정 · 감사 훅 · reap_on_startup · lifespan |

## Deviations from Plan

**1. [Rule 2 - 누락 보완] starting 시한 초과도 감사 대상**
- 계획에는 종료 지점이 3곳으로 적혀 있다. 그런데 `_reap` 의 starting→failed/-1 분기도 쓰기 잡이 끝나는 지점이라, 여기서도 감사 1줄을 남기게 했다. 이게 없으면 "모든 WRITE_KINDS 잡은 끝날 때 정확히 1줄" 이 깨진다. (ce27995)

**2. [Rule 1 - 버그] main.py import 이름 충돌**
- `from webapp import jobs` 를 그대로 쓰면 아래의 `from webapp.routes import … jobs` 가 같은 이름을 덮는다. 그러면 lifespan 이 라우터 모듈의 `reap_on_startup` 을 찾다 실패한다. 그래서 `job_engine` 별칭으로 import 했다. 수용 grep 패턴 `reap_on_startup()` 은 그대로 맞는다. (ce27995)

**3. [Rule 2 - 동시성] 감사 대기열 락 + LIVE 행 보류**
- 계획은 모듈 리스트를 두라고만 했다. 그런데 스레드풀에서 다른 요청이 남의 미커밋 reap id 를 먼저 비우면, running 상태로 잘못 기록될 수 있다. 그래서 락을 두고, 커밋 뒤 다시 읽은 행이 아직 LIVE 면 대기열에 남겨 두게 했다.

**4. prune_preview 에도 run_dir 필수 검사**
- 계약표에서 미리보기 산출물은 `<run_dir>/web/` 이다. run_dir 이 없으면 경로를 만들 수 없으므로 명시적으로 ValueError 를 낸다.

## Known Stubs

없음.

## Threat Flags

없음. 새 표면은 audit.jsonl 쓰기 하나뿐이고 계획의 T-02-10/14 에 이미 들어 있다.

## TDD Gate Compliance

세 태스크 모두 `test(02-02)` 를 먼저 커밋하고 그다음 `feat/fix(02-02)` 를 커밋했다. RED 단계에서 신규 테스트가 실패하는 것을 확인했다. 롤백 회귀 테스트는 수정 전 코드에서 실제로 실패해 버그가 재현됐다. 격리 스위치·설정 기본값처럼 기존 동작을 고정하는 일부 테스트는 RED 에서 모듈 import 에러로 함께 실패했다.

## Self-Check: PASSED
