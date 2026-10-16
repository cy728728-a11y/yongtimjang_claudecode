---
phase: quick-261016-lct
plan: 01
subsystem: bulsaja-automation
tags: [sold-lock, commerce-api, bulsaja-mcp, launchd]
requires: [verify_creds.issue_token, eroomlib.snapshot.ProductMCP, eroomlib.gsheets, ss_index_calls]
provides: [sold-lock skill, run_sold_lock.run()]
affects: [workspace.toml (sheets.work_board — orchestrator 몫)]
tech-stack:
  added: []
  patterns: [의존성 주입 run(), safe_json 시크릿 마스킹, hide 2단계 + 재조회 확인]
key-files:
  created:
    - .claude/skills/sold-lock/scripts/sold_lock_rules.py
    - .claude/skills/sold-lock/scripts/test_sold_lock_rules.py
    - .claude/skills/sold-lock/scripts/commerce_orders.py
    - .claude/skills/sold-lock/scripts/run_sold_lock.py
    - .claude/skills/sold-lock/scripts/test_run_sold_lock.py
    - .claude/skills/sold-lock/SKILL.md
    - .claude/skills/sold-lock/launchd/com.eroom.sold-lock.plist
  modified: []
decisions:
  - "hide 인자명은 list_tools 실측(productIds·hide·confirm·confirmationToken)과 같고, 실행 시에도 스키마로 재확인한다"
  - "workdata 의 smartstore 값이 비어 있으면(미업로드) ss_lookup_failed 가 아니라 productno_mismatch 로 본다. 호출 예외만 ss_lookup_failed"
  - "키가 시트에 없는 마켓은 no_credentials 상태(실패마켓 '키없음')로 기록한다"
  - "상품번호 폴백 find_by_code 는 코드 1개씩 호출하고, 응답 항목을 전부 그 코드에 붙인다"
metrics:
  completed: 2026-10-16
  tasks: 3
  tests: 28
---

# Quick 261016-lct: 판매상품 자동잠금(sold-lock) 요약

전날(KST) 결제완료 주문을 52개 마켓 커머스API로 모으는 sold-lock 스킬을 만들었다. 정확히 1건, 스스 상품번호 일치, `용쌤{번호}` 숫자 경계 마켓그룹 일치라는 3중 가드를 통과한 상품만 불사자 hide 2단계로 잠그고, 재조회해서 잠금이 확인된 것만 신규잠금으로 센다. 매일 00:01 launchd 템플릿도 포함한다(로드는 안 했다).

## 커밋

| 태스크 | 커밋 | 내용 |
|---|---|---|
| 1 RED | f7870c7 | 규칙 실패 테스트 |
| 1 GREEN | c12b4f9 | sold_lock_rules.py (표준라이브러리만) |
| 2 | 9b83e01 | commerce_orders.py, run_sold_lock.py, test_run_sold_lock.py |
| 3 | 750252d | SKILL.md, launchd plist 템플릿 |

## 검증

- `.venv/bin/python3 -m unittest test_sold_lock_rules test_run_sold_lock`: 28개 전부 통과
- `run_sold_lock.py --help`에 --date, --dry-run, --markets가 나온다
- `plutil -lint` OK이고 `launchctl list`에는 없다(미로드)
- 코드와 SKILL.md에서 시트 ID와 `python_work`가 검출되지 않는다(주석 제외)
- 실제 네트워크 호출은 읽기 전용 `list_tools()` 1회뿐이다(hide/find_by_code/workdata 스키마 확인용). 쓰기 API는 한 번도 부르지 않았다

## 계획과 달라진 점

1. **[Rule 3 - Blocking] workspace.toml에 `sheets.work_board`를 추가하지 못했다.** 이 파일은 .gitignore 대상이라 메인 체크아웃 루트에만 있고, 워크트리 격리 때문에 그 바깥 파일은 쓸 수 없었다. **orchestrator가 메인의 `workspace.toml` `[sheets]`에 다음 한 줄을 넣어야 한다:**
   `work_board = "1kuw0kpqT5gjgx5KiOIkDrOfVWmUu7O0k-Dnbq4yspAg"   # 업무판`
   이 줄이 없으면 실제 실행이 `cfg("sheets.work_board", required=True)`에서 KeyError로 멈춘다. 다른 시트에 엉뚱하게 쓰는 일은 없다.
2. **[Rule 2] 실패 상태 `no_credentials`를 추가했다.** 키 시트에 해당 마켓 행이나 키가 없는 경우를 token_failed와 구분하려고 넣었다. 업무판 메모에는 '키없음'으로 찍힌다.
3. **[TDD 순서] Task 2는 구현을 먼저 쓰고 테스트를 나중에 써서 둘을 한 커밋에 넣었다.** 이전 세션이 중단된 뒤 이어서 작업했기 때문이다. Task 1은 RED 커밋 후 GREEN 커밋 순서를 지켰다.

## TDD 게이트 준수

- Task 1: test(f7870c7)가 feat(c12b4f9)보다 먼저 들어갔다. 준수.
- Task 2: 별도 RED 커밋이 없다(위 3번). 테스트는 behavior 7개 항목과 키 로드/캐시 0600/폴백을 모두 다룬다.

## 남은 일 (orchestrator)

- 위 workspace.toml 한 줄 추가
- 실제 API로 `run_sold_lock.py --dry-run --markets 1-1` 한 번 돌리기. 커머스 `sellerProductCode` 필드명과 find_by_code `그룹`·`숨김` 키를 실측으로 확인해야 한다. 키가 다르면 가드 때문에 전부 skip으로 빠질 뿐 잘못 잠그지는 않는다
- launchd 설치는 SKILL.md에 적은 sed → bootstrap 순서로 한다

## Known Stubs

없음.

## Threat Flags

없음. 새로 생긴 접점(커머스 읽기, 불사자 hide, 키 캐시 파일)은 모두 계획의 threat_model T-lct-01~05 범위 안이고, 완화 조치를 구현했다.

## Self-Check: PASSED

- 파일 7개 모두 있음
- 커밋 f7870c7, c12b4f9, 9b83e01, 750252d 모두 있음

## 오케스트레이터 실측 후 수정 (2026-10-16)
- 주문 수집: `lastChangedType=PAYED` 필터가 결제 뒤 상태가 넘어간 주문을 전부 빠뜨림(52마켓 0건) → 대상일~지금 변경분 전수 + 결제일 필터로 교체.
- 마켓 대조: find_by_code '그룹' 이 null → 워크데이터 `uploadSelectedMarketGroupId` → 그룹명으로 대조.
- 실 실행: 10-15 신규잠금 2(13-2·14-2), 10-13 신규잠금 1(19-1), 10-14 0. 재조회로 잠금 확인.
- launchd `com.eroom.sold-lock` 로드 완료(매일 00:01).
