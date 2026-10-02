---
phase: quick-261002-mbo
plan: 01
status: complete
subsystem: naver-sourcing-bench
tags: [options, aside, dom-scraping, gws, sheet]
requires: []
provides:
  - drivers/options.js (상세페이지 옵션 펼쳐 읽기)
  - rules.parse_option_item / parse_base_price / is_catalog / build_options
  - gws_sheet.Sheet.update_cells / delete_rows
  - sourcing_bench `options --keyword` 서브커맨드, `bench --no-options`
affects: [후보 탭 9·10·U·X열, 후보 탭 행 삭제]
tech-stack:
  added: []
  patterns: [Aside repl 드라이버 + Python 판정 분리, 체크포인트 재개, 재조회 후 URL 로 행 위치 재확인]
key-files:
  created:
    - .claude/skills/naver-sourcing-bench/scripts/drivers/options.js
  modified:
    - .claude/skills/naver-sourcing-bench/scripts/rules.py
    - .claude/skills/naver-sourcing-bench/scripts/gws_sheet.py
    - .claude/skills/naver-sourcing-bench/scripts/sourcing_bench.py
    - .claude/skills/naver-sourcing-bench/scripts/test_rules.py
    - .claude/skills/naver-sourcing-bench/scripts/test_gws_sheet.py
    - .claude/skills/naver-sourcing-bench/scripts/test_sheet_schema.py
    - .claude/skills/naver-sourcing-bench/scripts/test_cli.py
    - .claude/skills/naver-sourcing-bench/SKILL.md
    - .claude/skills/naver-sourcing-bench/evidence/probe-2026-10.md
decisions:
  - 품절 조합은 개수에 포함하고 이름 끝에 "(품절)" (판매자가 운영하는 조합 수 기준)
  - 페이지 기본가를 못 읽으면 검색 대표가로 대체 (사람 큐 최소화)
  - 고를 수 없는(aria-disabled) 앞 축 값은 하위 축을 못 열므로 품절 조합 1개로 센다
  - 옵션명 앞 = + @ - 는 제거 (USER_ENTERED 수식 주입 방지, T-mbo-01)
  - 드라이버는 105초 벽 전에 남은 상품을 넘기고, Python 이 응답 없는 URL 을 다음 호출에 재투입. 한 건도 못 받으면 무한 반복 대신 중단(남은 건 옵션수동)
metrics:
  duration: ~35분
  completed: 2026-10-02
---

# Quick 261002-mbo: bench 옵션 자동 기입 Summary

상세페이지 옵션 드롭다운을 Aside 로 재귀 펼침(3축까지 실측)해서 후보 탭 9·10열을 자동 기입하고, 50조합 초과 상품은 후보에서 빼거나(bench) 행을 삭제(options)한다.

## 완료한 태스크

| Task | 내용 | 커밋 |
|---|---|---|
| 1 RED | 옵션 파싱·update_cells·delete_rows·수식 행상대참조 테스트 | 306bcfa |
| 1 GREEN | rules 옵션 파싱 함수 + gws_sheet 일괄갱신·행삭제 | b3e4678 |
| 2 RED | bench 옵션수집·options 재적용 CLI 테스트 | c584ef8 |
| 2 GREEN | drivers/options.js + bench 연동 + `options` 명령 | 8379701 |
| 3 | SKILL.md·probe-2026-10.md 갱신 (라이브 결과 표 포함) | 921f7c0 |

## 검증

- pytest: **57 passed** (기존 32 + 신규 25)
- `load_driver("options")` 조립본 `node --check` 통과, 페이지 안에서 eval 되는 helper 문자열도 별도로 파싱 확인
- `sourcing_bench.py options --help` 동작, `bench --no-options` 파서에 있음

## 라이브 드라이버 확인 (시트 쓰기 없음)

`login-check` 통과(종료코드 0). 바지걸이 체크포인트의 스마트스토어 후보 + 단품 기준 상품으로 run_driver 를 3번 호출:

| 상품 | 드라이버 상태 | build_options 판정 | 9열 / 10열 | 소요 |
|---|---|---|---|---|
| 3942331141 스토리행거 | 단품 | 성공 | 1 / `단품:28,000` | 3.2~3.6s |
| 11814963533 한평한뼘 (3축) | 성공 | 성공 | 20 / `1번 집게형-(20개+10개)-블랙:17,800 / …` (−8,000·+10,000 추가금 반영, 품절 표기 포함) | 29.3s |
| 10377153595 살림의기술 (2축) | 성공 | 성공 | 7 / `01_집게형 바지 치마 걸이 20개-블랙 10+10개:11,900 / …` | 9.1s |
| 101640774 후기검증 20P (3축) | 옵션초과 | 옵션초과 | 행 제외 (51번째 조합에서 중단) | 52s |
| 11061451782, 12628479166 | 읽기실패(표준그룹상품) | 실패 | 빈칸 + 옵션수동 | ~4s |

캡챠 0회. 두 번째 호출에서 3축 상품 2건 뒤 3번째 상품이 105초 벽 처리로 빠졌고(설계대로), 다음 호출에서 따로 읽힘(9.1s 성공).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - 정확성] repl 타임아웃 부분 결과 재투입**
- **Found during:** Task 2
- **Issue:** `_run_repl` 은 타임아웃 시 프로세스를 죽이고 그때까지 결과만 돌려준다. 다단 상품(30~50초)이 섞이면 청크 뒤쪽 상품이 조용히 빠져 옵션수동이 된다.
- **Fix:** 드라이버가 105초 전에 다음 상품을 시작하지 않고 멈추며, `_read_options` 가 응답 없는 URL 을 다음 호출에 재투입. 한 건도 못 받은 호출이면 중단(무한 반복 방지). 테스트 `test_read_options_requeues_missing_and_stops_on_empty`.
- **Commit:** 8379701

**2. [Rule 2 - 정확성] 판매 종료/삭제 상품을 단품으로 오판하지 않게**
- **Found during:** Task 2
- **Fix:** 본문 앞부분에 판매종료·삭제 문구가 있으면 읽기실패. 단품 판정은 `상품 가격` 텍스트가 있을 때만.
- **Commit:** 8379701

기타: `_read_options` 시그니처에 체크포인트 경로 인자 추가(저장용). `do_refill` 의 `건너뜀` = 키워드 일치 행 중 이미 9열이 채워졌거나 카탈로그인 행 수로 정의.

## Known Stubs

없음.

## Threat Flags

없음 — 새 표면(행 삭제)은 계획의 T-mbo-02 로 이미 다뤄짐(삭제 직전 재조회 + 키워드·norm_url 일치 + 내림차순 단일 batchUpdate).

## 남은 일 (오케스트레이터)

- 실제 시트에 `options --keyword 바지걸이` 전체 재적용 (이 실행에서는 하지 않음).

## Self-Check: PASSED

- options.js, SKILL.md, probe-2026-10.md 존재 확인
- 커밋 306bcfa, b3e4678, c584ef8, 8379701, 921f7c0 모두 git log 에 있음
