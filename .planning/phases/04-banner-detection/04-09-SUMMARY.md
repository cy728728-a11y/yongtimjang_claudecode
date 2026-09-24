---
phase: 04-banner-detection
plan: 09
subsystem: banner-vision2
tags: [banner, d22, vision2, gemini, 합성규칙, 뒤집기, 체크포인트, 견적, 목테스트, gap-closure]
status: 완료 — Task 1·2·3 실행. 실제 Gemini 호출 0회 · 불사자 크레딧 0.

requires:
  - phase: 04-banner-detection
    plan: 08
    provides: "2026-09-20 회차 산출물 · 원본 캐시 · 사람 라벨 · 어휘군 14군 · vision_pilot_result.json"
provides:
  - "`evidence/flip_rule_measure.py` + `flip_rule_result.json` — 뒤집기 채택 실측(네트워크 0)"
  - "04-GATE §15 — 합성 규칙 결정: `합집합+뒤집기(연락처,공장직판)` (후보 13 · 새 미탐 0 · 줄어들 오탐 13)"
  - "`banner_scan.py` 비전 2차 판정 — 판정 대상 전량 · sha256 체크포인트 · 견적 모드 · 승인 상한 · exit 5"
  - "산출물 `판정규칙.2차판정` — 사용·모델·응답모델·지시문판·sha256·합성규칙·적용범위·호출/토큰 집계"
  - "`settings.DEFAULTS` banner_vision2_* 7키 (max_calls 기본 0 = 유료 호출 미승인)"
affects: [04-10, 04-11, 04-12, 05]

tech-stack:
  added: []
  patterns:
    - "네트워크 이음매 한 곳(`_비전열기`) — 목 테스트는 이것만 바꿔 끼운다"
    - "과금 상한 초과 시 자르지 않고 호출 0회로 거부(exit 5)"
    - "성공만 기록하는 fsync jsonl 체크포인트, 키 = 원본 바이트 sha256"

key-files:
  created:
    - .planning/phases/04-banner-detection/evidence/flip_rule_measure.py
    - .planning/phases/04-banner-detection/evidence/flip_rule_result.json
    - .planning/phases/04-banner-detection/04-09-SUMMARY.md
  modified:
    - .claude/skills/bulsaja-detail-page/scripts/banner_scan.py
    - webapp/settings.py
    - webapp/tests/test_banner_scan.py
    - .planning/phases/04-banner-detection/04-GATE.md
    - .planning/REQUIREMENTS.md

decisions:
  - "D-22 합성 규칙 = 합집합+뒤집기(연락처,공장직판) — 04-GATE §15 실측(후보 13 중 진짜 배너 0). in-sample 이라 out-of-sample 회차에서 재확인"
  - "비전 2차는 판정 대상 전량(배너·제품·무내용) · 고유 이미지 sha 기준 1회 과금 · 기본 승인 상한 0"
  - "2차 실패는 제품이 되지 않는다 — 1차 비배너는 미판정(→판정불가 상품), 1차 배너는 배너 유지"

metrics:
  duration: 9min
  completed: 2026-09-24
  tasks: 3
  files: 8
---

# Phase 4 Plan 09: 비전 2차 판정(D-22 · 판정 대상 전량) Summary

온디바이스 OCR 어휘군(1차) 위에 Gemini 비전 v3 2차 판정을 판정 대상 전량에 합집합으로 붙였다. `연락처`·`공장직판` 만 걸린 장은 비전이 제품이라 하면 제품으로 뒤집는다(실측 후보 13장 · 새 미탐 0). 유료 호출은 견적과 승인 상한(기본 0) 뒤에만 나간다. 이 플랜에서 실제 API 호출은 0회다.

## T1 결정 — 뒤집기 채택 (04-GATE §15)

| 항목 | 값 |
|---|---|
| 표본 (v3 불일치 30 ∪ 합의표본 82) | 112 (측정불가 0) |
| 1차 배너 (현 14군 재OCR) | 57 |
| 뒤집기 후보 (걸린군 ⊆ {연락처,공장직판} ∧ v3 제품) | **13** (연락처 7 = 전부 `EnIxqg_S` 워터마크 · 공장직판 6) |
| 새 미탐 (후보 중 진짜 배너) | **0** |
| 줄어들 오탐 (후보 중 진짜 제품) | 13 |
| 실험[4] 배너 수 (재구성 확실성 조건 = 3) | 3 → 확실 |
| **결정** | **`합집합+뒤집기(연락처,공장직판)`** |

실험[4] 의 진짜 배너 3장(v3 가 놓친 장)은 `핵심셀링`·`경품이벤트`·`반품교환` 군에 걸려 있어서 뒤집기 대상이 아니다. 그래서 배너로 남는다.
한계: 같은 회차 in-sample 이고 v3 지시문도 이 표본을 보고 골랐다.

## 만든 것

- **Task 1** (`0109d91`): `flip_rule_measure.py`는 캐시 원본을 현 어휘군으로 다시 OCR하고, 보수적 진실값(정답 → D-21 실험[4] → 사람 `배너` 라벨 순으로 덮어씀)을 세운 뒤 채택 여부를 기계적으로 결정한다. 결과는 04-GATE §15에 넣었다.
- **Task 2** (`d59cdd1`): `지침_v3`(sha256 `5ff5d8cc…` 바이트 일치), `비전2차불가`, `비전키읽기`, `비전이미지준비`(PIL 지연 import), `_비전열기`, `비전한장`(재시도 0.5/1.5/3.0초, 429는 Retry-After 최대 60초, 그 밖의 4xx는 즉시 포기, 모르는 판정값은 ValueError), 체크포인트 3종, `이미지sha`, `이차대상모으기`, `견적`, `--vision2-*` 8개 인자, 폴백과 settings 7키.
- **Task 3** (RED `e793fff` → GREEN `e53f04f`): `전부2차판정`과 `_합성` 추가. `main`에서 `전부판정` 직후, `상품별미판정반영` 이전에 배선했다. `--vision2-estimate`는 `###VISION2_ESTIMATE### {json}`만 찍고 return 0 한다(호출 0, 산출물 없음). `판정규칙.2차판정`은 꺼진 회차에도 `사용:false`로 싣는다. `__main__`에서 exit 5로 끝나고, REQUIREMENTS BANNER-02b에 개정 문단을 붙였다.

## 테스트

- `.venv-web` `webapp/tests`: 446 → **462 passed** (+16, 비전 2차 절 전부 네트워크 0)
- `.venv` `webapp/tests/cli`: 4 passed (main 을 돌리는 테스트가 없어 `--vision2-enabled off` 주입 불필요)
- D-19 가드(`test_argv`)와 D-09 가드(`test_사람큐_없음`)도 통과했다. 테스트 파일에 `generativelanguage` 문자열은 0개다.
- 실데이터 스모크 테스트(`.venv`, 네트워크 0): `비전이미지준비(0001_01.bin)`가 JPEG 59,751바이트를 냈다.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] 파일럿 `코드`는 불사자코드가 아니라 판매자상품코드였다**
- **Found during:** Task 1
- **Issue:** 플랜은 파일럿 `코드`를 04-08 산출물의 `불사자코드`와 대조하라고 했지만 매칭이 0건이었다. 실제로는 `판매자상품코드`와 45상품이 맞았다. 둘 다 21자라 헷갈린다.
- **Fix:** `판매자상품코드`를 먼저 보고 `불사자코드`는 보조로 본다. 그 사실을 주석과 §15에 적었다.
- **Commit:** 0109d91

**2. [Rule 3 - Blocking] `2차대상모으기`는 파이썬 식별자가 될 수 없다**
- **Found during:** Task 2
- **Fix:** 이름을 `이차대상모으기`로 바꾸고 docstring에 플랜 이름을 적었다. 테스트 인자 `1차판정`도 같은 이유로 `첫판정`으로 바꿨다.
- **Commit:** d59cdd1 / e53f04f

**3. [Rule 1 - Bug] RED 테스트의 호출 수 기대값이 재시도를 세지 않았다**
- **Found during:** Task 3 GREEN
- **Fix:** 연속 실패 테스트가 이제 고유 장 12개와 HTTP 시도 2 + 10×4 = 42회를 따로 단언한다. 구현은 바꾸지 않았다.
- **Commit:** e53f04f

**4. [계획 보강] `체크포인트읽기`에 `모델=` 키워드 인자를 더했다.** 모델이 다른 줄을 무시한다는 요구를 파일명과 줄 단위 양쪽에서 지킨다.

**5. [판단] 요구사항 완료 표시를 되돌렸다.** `requirements.mark-complete`가 BANNER-02b·BANNER-04를 `[x]`로 찍었지만, 게이트(미탐 0%)가 아직 불통과이고 실탄은 04-11이라 되돌렸다. 개정 문단만 남는다.

`webapp/banner.py`는 바꾸지 않았다(게이트 산식 불변). `BannerArgv`에 vision2 인자를 배선하는 일은 이 플랜 범위 밖이다(04-10).

## Threat Flags

없음 — 새 외부 경계(Gemini)는 플랜 threat_model T-4-33~39가 이미 다룬다. 키는 argv에 들어가지 않고 경로만 넘어간다. 사유에는 예외 타입명만 적는다. 체크포인트에는 키 필드가 없다. 목 테스트가 stdout·stderr·산출물·체크포인트 전부에서 키가 없음을 확인한다.

## Known Stubs

없음.

## TDD Gate Compliance

RED `test(04-09)` e793fff → GREEN `feat(04-09)` e53f04f 순서를 지켰다. 리팩터 커밋은 없다.

## Self-Check: PASSED
