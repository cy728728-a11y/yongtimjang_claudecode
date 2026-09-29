---
phase: 07-thumb-coupang
plan: 03
subsystem: coupang-candidates CLI / 웹 러너
tags: [cp-01, cp-02, cp-03, cp-04, d-09, d-11, d-12, d-13, d-14, d-17, l-02, l-04, golden]
requires: []
provides:
  - "run_coupang.py --expect-nick (CoupangMCP.open 한 곳, exit 4)"
  - "run_coupang.py apply --pids-file (done 뒤·limit 앞 필터, 깨지면 exit 2)"
  - "run_coupang.py gate fail-closed (collect_group_strict · snaps, errs → exit 3 · 불사자코드 2차 키 · 그룹읽기 진단 줄)"
  - "coupang_web.py preview / commit (###STAGE### · ###COUPANG### · summary.json · commit_summary)"
affects: [07-05, 07-07]
tech-stack:
  added: []
  patterns: ["무플래그 골든을 CLI 수정 전 커밋에 고정", "러너는 CLI 를 import 하지 않고 subprocess 로만", "gate·apply 만 PIPE 로 받아 그대로 다시 찍으며 캡처", "verify 는 종료코드가 아니라 verified.json 중복0 으로 판정"]
key-files:
  created:
    - .claude/skills/coupang-candidates/scripts/coupang_web.py
    - .claude/skills/coupang-candidates/scripts/test_coupang_web.py
    - .claude/skills/coupang-candidates/scripts/fixtures/coupang_golden_noflag.json
  modified:
    - .claude/skills/coupang-candidates/scripts/run_coupang.py
    - .claude/skills/coupang-candidates/SKILL.md
decisions:
  - "workspace.toml min_margin 은 15.0 그대로 둔다 — 20.0 전환은 07-07 첫 체크포인트에서 용팀장 결정(오케스트레이터 지시). 러너는 기준 인자를 안 넘기므로 설정 한 줄만 바꾸면 20% 로 돈다"
  - "A3(총상품수 == 그룹 전건) 는 실측하지 않고 collect_group_strict 를 넣었다 — 틀려도 fail-closed(exit 3, 숫자 출력)라 07-07 첫 실행 로그가 곧 A3 실측이 된다"
  - "gate 그룹 목록 조기종료도 exit 3 (다시 돌리면 됨) 으로 묶었다"
  - "commit 은 apply 가 비0 이어도 copied.jsonl 차분을 요약에 싣는다(중간까지 복사됐을 수 있다)"
  - "verify 도 snaps, errs — 스냅샷 실패 시 중복0=false (증명 못 함)"
metrics:
  duration: "~35분"
  completed: 2026-09-29
  tasks: 3
  files: 5
---

# Phase 7 Plan 03: 쿠팡 CLI 주입구 · D-17 구멍 수리 · 웹 러너 Summary

쿠팡 CLI(`run_coupang.py`)에 계정 가드(`--expect-nick`)와 승인목록 필터(`apply --pids-file`)를 달고, gate 가 덜 읽힌 쿠팡 그룹으로 후보를 내던 fail-open 구멍(D-17)을 막았고, 웹 버튼이 부를 6단계 미리보기·재조회 커밋 러너 `coupang_web.py` 를 만들었다. 무플래그 동작은 수정 전 골든과 같다. 불사자 접속 0 · 쓰기 0 · 크레딧 0 — 전부 가짜 MCP/가짜 subprocess 오프라인 테스트.

## 무엇을 만들었나

- **Task 1 (0ac2f07)** — CLI 를 고치기 전에 골든 고정. 합성 run-dir 대표 6개(통과 A·B · 주문수부족 C · 마진미달 D · 쿠팡그룹에이미있음 E · 마진미상 F)로 무플래그 `gate` 의 candidates.json·rejected.json 바이트·stdout·불사자 호출, 무플래그 `apply`(미리보기) stdout 을 `fixtures/coupang_golden_noflag.json` 에 저장. 가짜 불사자는 `BulsajaMCP` transport(init/open/close/call_tool)만 갈아끼워 `CoupangMCP.open` 오버라이드까지 실제로 탄다. `snapshot.ensure` 도 가짜(스냅샷 캐시 쓰기 0). 기준은 cfg 로 15.0 명시 주입.
- **Task 2 (3bc8273 RED → 91eb058 GREEN)** — D-17 · D-14 · D-12:
  - `CoupangMCP.collect_group_strict` — 첫 페이지 `총상품수` 기억, 끝에 읽은 수가 적으면 RuntimeError → gate `exit 3`, 후보 파일 미작성.
  - `snaps, errs = snapshot.ensure(...)` — errs 1건이라도 `[gate] 쿠팡 그룹 스냅샷 N건 실패 — 부분 대조 금지. 다시 돌려라` + exit 3, 기존 후보 파일도 안 건드림.
  - 2차 키 — 그룹 스냅샷 불사자코드 집합 `already_codes`, 이미있음 분기에 `or row["불사자코드"] in already_codes`. `[gate] 그룹 상품 타오바오번호 결측 N건 — 불사자코드로 대조` · `[gate] 그룹읽기 총상품수 X · 읽음 Y · 타오바오결측 Z` 출력.
  - `--skip-group-check` 경로 불변(MCP 호출 0 테스트).
  - `--expect-nick` — `common()` 에 추가, main 이 모듈 전역 `_EXPECT_NICK` 에 넣고 `CoupangMCP.open()` 이 super().open() 직후 `bulsaja_my_profile` 1회 → 불일치·조회실패면 stderr `[계정] 기대 X · 실제 Y — 중단` · close · exit 4. resolve/ship/gate/apply(커밋)/verify 5단계 모두 프로필 외 호출 0 확인.
  - `apply --pids-file` — done 필터 뒤·limit 앞. 파싱 실패·배열 아님·파일 없음 → `전량 복사로 넘어가지 않는다` + exit 2(MCP 호출 0). 후보에 없는 승인 pid 는 `승인됐지만 재조회 후보에 없음: …`.
- **Task 3 (48f9ce7 RED → cdcc6c0 GREEN)** — `coupang_web.py`:
  - `preview`: prep→resolve→build→ship→gate→apply(미리보기)를 한 run-dir 에서. `--expect-nick` 은 resolve·ship·gate·apply 에만(verify 는 commit 에서). 비0 즉시 정지(정지단계 기록, 코드 전달). summary.json = interfaces 스키마(기준 줄 그대로 · 통과 행 · 탈락사유별 · 이미있음 · 그룹읽기 · apply미리보기.대상).
  - `commit`: approved(없음/깨짐/빈 배열/플래그 모양 pid)·limit<1·미리보기 요약 없음 → exit 2, 자식 0 → gate 재조회 → 새−옛 있으면 복사 0 · exit 5 (옛 ≥ 100 이면 `상한경계` true) → 승인∩새 (공집합 exit 2), 빠짐 {pid: 새 사유} → `approved_pids_<시각>_<pid>.json` → `apply --commit --limit L --pids-file … --expect-nick N` → `verify --only all` → verified.json `중복0` 이 True 가 아니면 exit 1. 복사 = 이번 잡이 copied.jsonl 에 더한 행, 신pid없음 집계.
  - 금지 4종 플래그 문자열 0회 · run_coupang import 0 · 커밋 플래그는 `_COMMIT_FLAG` 상수 1회 — 테스트 가드.
  - SKILL.md: S5 행을 `gate --limit 100`(기준은 workspace.toml 정본 · min_margin 20 목표 · 현재 15.0 · min_orders 3), §재개·안전에 D-17 exit 3 과 러너용 주입구 2줄.

## D-17 수리 상세 (CP-04)

| 구멍 | 전 | 후 |
|---|---|---|
| 그룹 상품 스냅샷 실패 | `snaps, _` 로 버림 → 그 상품 타오바오번호가 대조에서 빠짐 → **재복사** | errs 있으면 exit 3, 후보 파일 미작성 |
| 그룹 목록 빈 페이지 조기종료 | `if not items: break` 조용히 종료 | `총상품수` 대비 덜 읽힘 → exit 3 |
| 타오바오번호 결측 그룹 상품 | `already.discard("")` 로 대조 불가 | 불사자코드 2차 키 + 결측 건수 출력 |
| (추가) verify 스냅샷 실패 | 못 읽은 상품 빼고 중복 0 "통과" | 중복0=false |

## 검증

- `.venv/bin/python3 -m pytest -q .claude/skills/coupang-candidates/scripts/` → **87 passed** (기준선 36 + 신규 51), 골든 green(재생성 플래그 없이)
- `.venv-web/bin/pytest webapp/tests` → 867 passed (회귀 없음)
- `grep "snaps, errs"` 2 · `grep "snaps, _ ="` 0 · `--expect-nick`/`--pids-file` 있음 · 러너 금지 문자열 0 · `###COUPANG###` 2 · `중복0` 7 · SKILL.md `min_margin 20` 1
- 사용자 서버(:8765, PID 52296)·webapp.db·실제 run-dir·잡 dd911562 무접촉. 불사자 호출 0.

## A3 실측

**실측 안 함.** 오케스트레이터 지시(“No real-data runs in this plan”)로 불사자 읽기 1회도 하지 않았다. 대신:
- `collect_group_strict` 는 넣었다. `총상품수` 가 숫자가 아니면 대조를 건너뛰고(None), 숫자인데 덜 읽혔으면 exit 3 에 `총상품수 X · 읽음 Y` 를 찍는다 — **틀리면 fail-closed(복사 0) 쪽으로만 틀린다.**
- 07-07 첫 실제 preview 의 gate 로그 `[gate] 그룹읽기 총상품수 X · 읽음 Y` 가 곧 A3 실측이다. RESEARCH 예시값은 87/87. 만약 X>Y 로 계속 exit 3 이 나면 `총상품수` 의미가 다르다는 뜻 — 그땐 strict 대조를 빼고 b·c 만 남기면 된다.

## Deviations from Plan

### 오케스트레이터 제약으로 건너뜀

**1. workspace.toml `[coupang] min_margin = 20.0` 미적용**
- 계획은 toml 을 15.0 → 20.0 으로 바꾸라 했지만, 오케스트레이터가 실제 toml 변경은 07-07 용팀장 결정이라고 금지. 15.0 그대로.
- 영향: 러너는 기준 인자를 안 넘기므로 **지금 웹 경로는 15% 로 돈다.** 07-07 에서 toml 한 줄(`min_margin = 20.0`)만 바꾸면 CP-03 20% 가 된다.
- 계획의 `cfg("coupang.min_margin") == 20.0` 실제 설정 읽기 테스트 대신, cfg 에 20.0 을 주입하면 기준 줄이 20.0 이 되고 B(보정 18.7)가 마진미달로 빠지는지 확인하는 테스트(`test_gate_기준은_cfg_를_따른다`)로 바꿨다.

**2. A3 실측 미수행** — 위 절 참조.

### Auto-fixed Issues

**3. [Rule 2 - 정확성] verify 도 스냅샷 오류를 버리고 있었다**
- **Found during:** Task 2 (acceptance `snaps, _ =` 0회)
- **Issue:** `cmd_verify` 가 `snaps, _` 로 오류를 버려, 못 읽은 상품을 빼고 "중복 0 통과"를 낼 수 있었다 — 러너가 이 파일로 커밋 성공을 판정하므로 D-17 과 같은 구멍.
- **Fix:** errs 있으면 경고 + `중복0=False`. 정상 경로 불변.
- **Commit:** 91eb058

**4. [Rule 2 - 보안] commit 승인 pid 모양 검사**
- approved 배열에 선행 하이픈·공백 pid 가 있으면 exit 2 (thumb_web `_pid_ok` 선례). pids-file 로 넘어가 argv 로 해석되진 않지만, 웹앱이 쓴 파일이 깨졌다는 신호라 멈춘다.

**5. [Rule 1] gate 목록 조기종료를 exit 3 으로 통일**
- 계획은 "비0" 만 요구. 스냅샷 실패와 같은 "다시 돌리면 됨" 부류라 exit 3 으로 묶었다(러너 종료 계약 3 = gate 부분읽기).

## TDD Gate Compliance

- Task 2: `test(07-03)` 3bc8273 (RED, 19 failed) → `feat(07-03)` 91eb058 (GREEN)
- Task 3: `test(07-03)` 48f9ce7 (러너 파일 없이 24 errors + 2 failed) → `feat(07-03)` cdcc6c0 (GREEN)

## 요구사항 체크

REQUIREMENTS.md 에는 **CP-04 만** 완료 표시했다. CP-01·CP-02 는 웹 쪽(07-05 버튼·승인 화면)이 붙어야, CP-03 은 toml 20.0 전환(07-07)이 돼야 닫힌다.

## Known Stubs

없음.

## Self-Check: PASSED
