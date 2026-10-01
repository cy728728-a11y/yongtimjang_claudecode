---
phase: 02-prune-ads
plan: 01
subsystem: naver-ads-weekly CLI (prune · ads_rules)
tags: [prune, cli-contract, safety, board-05]
requires: []
provides:
  - "run_ads.py prune --only-ads/--preview-out/--max-items/--backup-tag"
  - "prune 산출물 스키마 {generated, mode, limit, total, adIds, accounts{…targets/items/excluded/new_since_preview}}"
  - "prune.excluded_reasons · prune.count_targets · prune.TAG_RE"
  - "result.json ⑥ 행 statusReason · editTm · productLive"
affects: [02-02, 02-03, 02-04, 02-05]
tech-stack:
  added: []
  patterns: ["cmd_bids 쌍둥이 주입구", "키워드 인자 기본값 = 기존 동작(L-02)", "쓰기 경로는 in-process 몽키패치, subprocess 는 dry-run 만"]
key-files:
  created:
    - webapp/tests/test_prune_cli.py
  modified:
    - .claude/skills/naver-ads-weekly/scripts/prune.py
    - .claude/skills/naver-ads-weekly/scripts/run_ads.py
    - .claude/skills/naver-ads-weekly/scripts/ads_rules.py
    - .claude/skills/naver-ads-weekly/scripts/test_prune.py
    - .claude/skills/naver-ads-weekly/scripts/test_ads_rules.py
decisions:
  - "D-06 exit 5 미구현 — revived_filter 교집합이라 발동 불가. new_since_preview 보고 + 목록 밖 DELETE 0회 테스트로 대체"
  - "백업은 only_ads 로 좁히지 않고 계정 deletable 전량(상위집합) 유지 — 넓은 백업은 무해"
  - "커밋 산출물 targets 는 재조회 전 대상(미리보기와 대조용), 실제 시도는 items · total/adIds 는 items 기준"
  - "count_targets 를 Task 1(prune.py)에서 함께 구현 — 판정을 deletable 한 곳에 둠"
metrics:
  duration: "약 25분"
  completed: 2026-10-01
  tasks: 3
  files: 6
---

# Phase 2 Plan 01: prune CLI 주입구 + ⑥ 행 보강 Summary

`run_ads.py prune` 에 웹이 감쌀 4플래그(대상 목록·산출물·상한·백업 태그)를 붙이고, 반환값을 버리던 `cmd_prune` 이 계정별 대상 행·소재별 결과·재조회 제외 사유를 원자적 JSON 으로 남기게 했다. 규칙⑥ 행에는 정지사유·마지막 변경·상품 게재 여부를 실었다. 무플래그 동작·종료코드·백업 파일명은 그대로다.

## 무엇이 바뀌었나

**prune.py**
- `excluded_reasons(target, fresh)` — `재조회에_없음` / `다시_켜짐` / `사유_바뀜:<reason>`. "재조회에 없음"을 "이미 삭제됨"으로 단정하지 않는다는 주석(Pitfall 6)
- `backup_paused(..., tag=None)` — `paused_<alias>_<날짜>_<tag>.json`, 태그는 `^[A-Za-z0-9_-]{1,64}$` 아니면 ValueError
- `delete_ads(..., items=None)` — 소재별 `{adId,status,결과,err}` (성공/이미없음/실패/재시도소진). 진행 파일 재개로 건너뛴 건은 "성공"+기록 status. 반환 `dict(stat)` 불변
- `run_prune(..., only_ads=None, tag=None, collect_items=False)` — 대상 = `deletable ∩ only_ads`, 커밋 시 `excluded`·`new_since_preview`·`items` 추가. 무키워드 반환 키 집합 불변(테스트 고정)
- `count_targets(run_dir, alias, only_ads)` — `--max-items` 사전 집계용

**run_ads.py**
- prune 서브파서 `--only-ads` · `--preview-out` · `--max-items` · `--backup-tag`
- 종료코드: 0 정상 · 1 only-ads 깨짐(폴백 금지 문구)/태그 불량/산출물 쓰기 실패 · 2 상한 초과(백업 전 중단)
- 건너뛴 계정도 `skipped: "자격증명 없음"|"prep 없음"` 으로 산출물에 남김
- `_prune_document` 가 최상위 `adIds` 를 싣는다 → 그 파일 자체가 다음 `--only-ads` 입력(테스트로 왕복 확인)

**ads_rules.py**
- ⑥ 행에만 `statusReason` · `editTm` · `productLive` 덧붙임(`ad_info` 불변). ②~⑤ 가 `live` 만 순회한다는 BOARD-05 주석

## 검증

- `.venv/bin/python3 -m pytest -q .claude/skills/naver-ads-weekly/scripts` → 129 passed (기존 104 + 신규 25)
- `.venv-web/bin/pytest webapp/tests -p no:warnings` → 952 passed (신규 test_prune_cli 11개 포함)
- `bash webapp/tests/no_commit_guard.sh` → OK
- 네이버 API 호출 0 — subprocess 테스트는 dry-run 만, 쓰기 경로는 `cmd_prune` in-process + `prune.nvad.call`/`collect.fetch_ads`/`time.sleep`/`run_ads._accounts`/`run_ads.data_root` 몽키패치. 실데이터는 `ads.json` 키 목록만 읽기 전용으로 확인

## Commits

| Task | Gate | Commit | 내용 |
|------|------|--------|------|
| 1 | RED | 0dd1f53 | prune 주입구 실패 테스트 |
| 1 | GREEN | b661bc2 | prune.py 주입구 구현 |
| 2 | RED | d288430 | test_prune_cli.py |
| 2 | GREEN | 4125f99 | run_ads prune 4플래그 + 덤프 |
| 3 | RED | e86104c | ⑥ 행·BOARD-05 실패 테스트 |
| 3 | GREEN | c0b00c7 | ads_rules ⑥ 보강 |

## Deviations from Plan

**1. [Rule 2 - 계획 보정] count_targets 를 Task 1 에서 구현**
- 계획은 Task 2 에서 prune.py 에 추가하도록 했지만 prune.py 단위 테스트와 함께 두는 게 자연스러워 Task 1 커밋에 포함. 계약은 동일.

**2. [Rule 1 - 안전] 백업 범위는 only_ads 로 좁히지 않음**
- 구현 중 tgt(목록 교집합)만 백업하는 안을 검토했으나, 기존처럼 계정 deletable 전량을 백업하도록 유지. 상위집합 백업은 무해하고 무플래그 동작과 같다.

**3. 커밋 산출물 targets 의미 명시**
- 커밋 모드 `targets` = 재조회 전 대상(미리보기와 1:1 대조), `total`/`adIds` = 실제 DELETE 시도(items) 기준. 인터페이스 블록의 "commit 이면 재조회 후 실제 DELETE 시도 수" 와 일치.

D-06 exit 5 는 계획대로 구현하지 않았다(Pitfall 5 — 구조적으로 발동 불가). `run_prune` 독스트링에 이유를 적었다.

## Known Stubs

없음.

## TDD Gate Compliance

세 태스크 모두 `test(02-01)` → `feat(02-01)` 순서로 커밋. RED 단계에서 신규 테스트가 실패하는 것을 확인했다(무플래그·skip 경로처럼 기존 동작을 고정하는 테스트는 RED 에서도 통과 — 의도된 회귀 고정).

## Self-Check: PASSED
