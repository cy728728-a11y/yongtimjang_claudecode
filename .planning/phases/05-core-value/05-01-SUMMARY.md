---
phase: 05-core-value
plan: 01
subsystem: detail-cli
tags: [detail_batch, cli, inputs-mode, offline-test, golden, credit-safety]
requires: []
provides:
  - "detail_batch.py --inputs/--done-tag/--expect-nick/--estimate-only/--estimate-out/--max-credits/--summary-out"
  - "종료코드 계약 0/2/3/4/5 + 센티널 ###DETAIL### 완료/실패/스킵/폴링미완/전체"
  - "webapp/tests/test_detail_cli.py 가짜MCP 하네스 (05-03/04 재사용 가능)"
affects: [05-03, 05-04, 05-05]
tech-stack:
  added: []
  patterns: ["sys.modules 스텁 + importlib 파일 로드", "가짜MCP/가짜시계", "패치 전 골든 박제"]
key-files:
  created:
    - webapp/tests/test_detail_cli.py
    - webapp/tests/fixtures/detail_golden_noflag.json
    - webapp/tests/fixtures/detail_inputs_min.json
  modified:
    - .claude/skills/bulsaja-detail-page/scripts/detail_batch.py
decisions:
  - "inputs 모드 접수는 submit_one 에 imgs_override 를 붙이지 않고 별도 _입력접수 로 분리 — taskId 선저장(Pitfall 2)을 위해 검증을 호출부로 빼야 해서"
  - "장수불일치 건은 폴링 대상·재접수 대상 모두에서 제외하고 summary 집계상 실패로 센다"
  - "--inputs 모드는 --force 를 적용하지 않는다 (D-12 절대조건)"
  - "견적 모드는 --expect-nick 없이도 my_profile 을 1회 불러 잔액을 싣는다(조회 실패 시 null 로 진행)"
metrics:
  duration: "~7분"
  completed: 2026-09-25
  tasks: 3
  files: 4
---

# Phase 5 Plan 01: detail_batch 주입구 플래그 Summary

기존 `detail_batch.py` 에 `--inputs` 모드(견적 · 접수+폴링 · 이어서 확인)를 붙이고, 연구가 찾은 버그 2개(폴링 조기종료 · 장수불일치 taskId 유실)를 그 모드 안에서 고쳤다. 플래그 없는 동작은 패치 전 골든과 한 글자도 다르지 않다. 크레딧·네트워크 사용 0 — 전부 가짜 MCP.

## A1 실측 결과

**통과.** `sys.modules["bulsaja_mcp"]` 스텁 + `importlib.util.spec_from_file_location` 로 `.venv-web` 에서 바로 로드된다(`test_로더_가_venv_web_에서_뜬다`). `webapp/tests/cli/` 로 옮길 필요 없음 — 웹앱 스위트 안에서 돈다. inputs 모드의 `ss_index_calls` 지연 import 도 `SCRIPT_DIR` 를 sys.path 에 넣고 불러서 파일 로드 환경에서 동작한다(fixture 가 sys.path·sys.modules 원복).

## 최종 CLI 인자 (추가분)

| 인자 | 의미 |
|------|------|
| `--inputs <path>` | `{"items":[{productId,판매자상품코드,imageUrls,제품이미지총수,잘림}],"제외":[...]}`. 주면 products.json·collect_images 안 씀. `제외` 무시. 깨지면 exit 2 (폴백 없음) |
| `--done-tag <태그>` | append, inputs 모드 필수(0개 = exit 2) |
| `--expect-nick <닉>` | my_profile 1회, 불일치 또는 조회 실패 = exit 4 (workdata·generate 전) |
| `--estimate-only` | generate 0회. `--estimate-out` 필수 |
| `--estimate-out <path>` | `{생성시각,계정,잔액,per_credit,항목[{productId,판매자상품코드,판정,사유,장수,제품이미지총수,잘림,크레딧}],집계{선택,스킵,접수,총장수,예상크레딧,잘린상품}}` |
| `--max-credits N` | 접수 모드 필수(없으면 exit 2). 누적+이번 건 > N 이면 generate 전 exit 5 |
| `--summary-out <path>` | `{항목[{productId,판매자상품코드,상태,장수,크레딧,사유,taskId}],집계{접수,완료,실패,스킵,폴링미완,실제크레딧},종료코드}` |

기존 `--poll-only`·`--submit-only`·`--retry-failed`·`--pages`·`--quality`·`--poll-interval`·`--max-poll-min`·`--dup-wait`·`--dup-rounds`·`--sleep` 은 inputs 모드에서도 같은 의미로 쓴다. `--force` 는 inputs 모드에서 무시된다.

판정 값: `접수 | 기작업 | 태그미조회 | 입력부족`. summary 상태 값: `완료 | 실패 | 폴링중 | 기작업스킵 | 태그미조회 | 입력부족 | 장수불일치 | 접수실패 | 미접수`.

## 종료코드 표

| 코드 | 의미 | 발생 지점 |
|------|------|-----------|
| 0 | 전부 종결(견적 완료 포함) | 미종결 0건 |
| 2 | 입력 오류 / 장수 불일치 | --inputs 깨짐 · done-tag 없음 · estimate-out 없음 · max-credits 없음 · 예상장수 비정수/불일치(taskId 선저장 후) |
| 3 | 폴링 미완(실패 아님) | deadline 도달 시 taskId 보유 미종결 ≥ 1 |
| 4 | 계정 불일치 | --expect-nick ≠ 붙은 계정 |
| 5 | 견적 초과 | 누적 크레딧이 --max-credits 를 넘기려는 건의 generate 직전 |
| 1 | (기존) --pages 범위 밖 | 변경 없음 |

센티널(inputs 접수/폴링 모드, 마지막 줄): `###DETAIL### 완료 a / 실패 f / 스킵 s / 폴링미완 p / 전체 t`. 견적 모드는 `###ESTIMATE### 선택 … / 접수 … / 스킵 … / 총장수 … / 예상크레딧 … / 잘린상품 …`.

## Tasks

| # | 이름 | 커밋 |
|---|------|------|
| 1 | 오프라인 하네스 + 플래그 없는 골든 박제 (detail_batch.py diff 0) | 55b0039 |
| 2 | 견적 경로 RED / GREEN | 25d9e16 / 7457809 |
| 3 | 접수·폴링 경로 RED / GREEN | 2656725 / 076fca8 |

## 테스트

- `webapp/tests/test_detail_cli.py`: **45 passed** (골든·D-12 교차 7표본 포함)
- 웹앱 전체 `.venv-web/bin/pytest webapp/tests`: **520 passed** (기존 475 + 45)
- CLI 스위트 `.venv/bin/python3 -m pytest webapp/tests/cli`: **4 passed** (변화 없음)
- `.venv/bin/python3 detail_batch.py --help` exit 0, `--done-tag` 출력
- 골든 커밋(55b0039)이 detail_batch.py 첫 수정 커밋(7457809)보다 앞선다

## Deviations from Plan

### Auto-fixed / 설계 조정

**1. [Rule 3 - 설계] inputs 접수를 `submit_one(imgs_override=)` 대신 별도 `_입력접수` 로 분리**
- **이유:** 플랜은 `submit_one` 에 `imgs_override` 키워드를 붙이라 했지만, Pitfall 2 수정(taskId 를 검증 **전에** 체크포인트에 저장)과 비정수 예상장수 fail-closed 를 하려면 검증을 호출부로 빼야 한다. `submit_one` 을 건드리면 플래그 없는 경로 줄이 바뀐다(L-04). 그래서 같은 2단 프로토콜(imageUrls+sectionCount 동시, confirm False→토큰→True)을 새 함수로 두고 `submit_one` 은 무수정. 또한 `_판정` 에서 이미 부른 workdata 를 재호출하지 않는다.
- **Commit:** 076fca8

**2. [Rule 1 - 테스트 오류] `test_요약_파일[초과]` 상한값 60 → 50**
- 7장(35) + 4장(20) = 55 ≤ 60 이라 초과가 안 났다. 테스트 산술 실수 — 구현은 정상.
- **Commit:** 076fca8

**3. [TDD 참고] RED 단계에서 `test_입력_깨진파일은_exit2`·`test_입력_done_tag_없으면_exit2` 가 통과**
- 당시 플래그가 없어서 argparse 가 exit 2 를 냈기 때문(우연 통과). GREEN 이후에는 `mcp.호출 == []` 단언과 함께 실제 경로로 통과한다.

**4. 장수불일치 건 처리 명시** — 폴링·재접수 대상에서 모두 제외, summary 에서 실패로 집계. 플랜에 명시가 없어 보수적으로 정했다(서버 결과가 틀린 장수라 사람이 봐야 함).

**5. REQUIREMENTS.md 체크 보류** — DETAIL-01~07 은 05-02~06 도 같이 들고 있고(웹앱 슬라이스·실탄 미완), 이 플랜은 CLI 측만 끝냈다. `requirements.mark-complete` 결과를 되돌려 Pending 유지.

## TDD Gate Compliance

Task 2: test(25d9e16) → feat(7457809). Task 3: test(2656725) → feat(076fca8). 두 게이트 모두 충족.

## Known Stubs

없음.

## Threat Flags

없음 — 새 외부 호출은 `bulsaja_my_profile`·`bulsaja_product_find_by_code`(읽기)뿐이고 threat_model T-05-01~06 이 전부 테스트로 집행된다.

## 크레딧·네트워크

0크레딧 · 네트워크 0. 불사자 MCP 실호출 없음(모든 테스트 가짜MCP, `--help` 만 실제 .venv 로 실행). 사용자 웹앱 서버(:8765) 미접촉.

## Self-Check: PASSED
