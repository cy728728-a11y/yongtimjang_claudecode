---
phase: 4
slug: banner-detection
status: closed — 검증 계약 이행 · 🔴 게이트 불통과 · Phase 4 는 D-23(2026-09-25 용팀장)으로 불통과 상태 종료
nyquist_compliant: true
wave_0_complete: true
gate_passed: false
gate_blockers: ["오탐율_누락률 13.70% (10% 이하가 조건) — 2026-09-25 §17 재판정"]
gate_blockers_history: ["2026-09-22: 미탐 11 · 미검수상품 8", "2026-09-23: 미탐 11 (미검수 0 달성)", "2026-09-25: 누락률 13.70% (미탐 0 · 미검수 0)"]
remeasure_conditions_met: "3/4 — 미충족 #1(어휘군이 본 적 없는 상품 · 같은 회차 재사용)"
created: 2026-09-22
closed: 2026-09-22 (04-08 Task 3) · 재판정 2026-09-25 (04-12 · GATE §17)
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `04-RESEARCH.md` §Validation Architecture (2026-09-21 실측 기반)

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | `webapp/pytest.ini` |
| **Quick run command** | `.venv-web/bin/python3 -m pytest webapp/tests -q -p no:warnings` |
| **Full suite command** | `.venv-web/bin/python3 -m pytest webapp/tests -q` |
| **Estimated runtime** | ~12 seconds (**현재 446 passed**, 2026-09-22 마감 시점 확인) |

> ⚠️ **venv 가 둘이다.** 기존 스위트는 전부 `.venv-web` 으로 돈다. `test_ocr_determinism.py` 만
> `.venv`(CLI)로 돈다 — `pyobjc-framework-Vision` 과 Pillow 가 거기에만 있기 때문이다 (D-19 경계).
> 플래너는 이 이중 실행을 설계에 명시적으로 반영할 것.

---

## Sampling Rate

- **After every task commit:** `.venv-web/bin/python3 -m pytest webapp/tests -q -p no:warnings`
- **After every plan wave:** 위 + `.venv/bin/python3 -m pytest webapp/tests/cli/test_ocr_determinism.py`
  (04-04 가 경로를 `webapp/tests/cli/` 로 한 칸 내렸다 — `.venv` 로 도는 유일한 디렉터리다)
- **Before `/gsd:verify-work`:** 전 스위트 green + **사람 전수 검수 완료 + 미탐 0 확인**
  🔴 **2026-09-22: 이 조건이 충족되지 않았다.** 전수 검수는 52/60 상품에서 멈췄고 미탐 11장이다.
  숫자와 판정은 `04-GATE.md` 가 정본이다.
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

2026-09-22 마감: 실제 플랜 번호·테스트 파일·상태로 채웠다.
Task ID 는 `<플랜>-T<태스크번호>` 표기다. `—` 는 그 플랜의 여러 태스크에 걸쳐 있다는 뜻.

**Status 는 전부 ✅ green 이다. 그것과 게이트 통과는 다른 이야기다** —
여기 있는 건 "계약대로 자동 검증이 있고 돈다"이고, 게이트는 사람이 본 숫자로 닫힌다(D-03a).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-01-T1 | 04-01 | 1 | BANNER-01 | — | N/A | unit | `.venv-web/bin/python3 -m pytest webapp/tests/test_banner.py::test_렌더콘텐츠_이미지목록 -x` | ✅ | ✅ green |
| 04-01-T1 | 04-01 | 1 | BANNER-01 | — | 미조회를 0장으로 흡수하지 않는다 | unit | `.venv-web/bin/python3 -m pytest webapp/tests/test_banner.py::test_None_은_예외 -x` | ✅ | ✅ green |
| 04-01-T1 | 04-01 | 1 | BANNER-01 | — | N/A | unit | `.venv-web/bin/python3 -m pytest webapp/tests/test_banner.py::test_렌더콘텐츠_함정 -x` | ✅ | ✅ green |
| 04-04-T2 | 04-04 | 4 | BANNER-02b | T-4-14 | 한국어·중국어를 둘 다 건다 · 2글자 ASCII 금지 | unit | `.venv-web/bin/python3 -m pytest webapp/tests/test_banner.py::test_어휘군_한중 -x` | ✅ | ✅ green (**14군**) |
| 04-04-T1 | 04-04 | 4 | BANNER-02b | — | 판정이 회차마다 흔들리지 않는다 | integration | `.venv/bin/python3 -m pytest webapp/tests/cli/test_ocr_determinism.py -x` | ✅ (`.venv`) | ✅ green (4 passed) |
| 04-04-T2 | 04-04 | 4 | BANNER-02b | T-4-29 | 어휘군을 고치다 라벨 9장을 놓치면 CI 가 잡는다 (**회귀 방지지 게이트 근거 아님**) | unit | `.venv-web/bin/python3 -m pytest webapp/tests/test_banner.py::test_라벨픽스처_미탐0 -x` | ✅ | ✅ green |
| 04-02-T1 | 04-02 | 2 | BANNER-03b | T-4-01 | 빈 목록이 '전량'으로 읽히지 않는다 | unit | `.venv-web/bin/python3 -m pytest webapp/tests/test_banner.py::test_빈목록은_전량이_아니다 -x` | ✅ | ✅ green |
| 04-02-T1 | 04-02 | 2 | BANNER-03b | T-4-01 | 미판정 장을 '배너 아님'으로 흡수하지 않는다 | unit | `.venv-web/bin/python3 -m pytest webapp/tests/test_banner.py::test_미판정_흡수금지 -x` | ✅ | ✅ green |
| 04-02-T1 | 04-02 | 2 | BANNER-03b | — | N/A | unit | `.venv-web/bin/python3 -m pytest webapp/tests/test_banner.py::test_순서유지_상한없음 -x` | ✅ | ✅ green |
| 04-02-T2 | 04-02 | 2 | BANNER-04 | — | 분모 둘을 **모두** 낸다 (D-11) | unit | `.venv-web/bin/python3 -m pytest webapp/tests/test_banner.py::test_게이트집계_분모둘 -x` | ✅ | ✅ green |
| 04-02-T2 | 04-02 | 2 | BANNER-04 | T-4-28 | 미검수를 통과로 세지 않는다 — **2026-09-22 에 실제로 발동했다(미검수 8 → 게이트 false)** | unit | `.venv-web/bin/python3 -m pytest webapp/tests/test_banner.py::test_미검수_분모제외 -x` | ✅ | ✅ green |
| 04-02-T2 | 04-02 | 2 | BANNER-04 | — | 물갈이 사본이 분모를 부풀리지 않는다 (62상품 → 60 distinct 실측) | unit | `.venv-web/bin/python3 -m pytest webapp/tests/test_banner.py::test_타오바오distinct_집계 -x` | ✅ | ✅ green |
| 04-02-T3 | 04-02 | 2 | BANNER-05 | — | N/A (실측 1건 발동) | unit | `.venv-web/bin/python3 -m pytest webapp/tests/test_banner.py::test_D07_잔여부족 -x` | ✅ | ✅ green |
| 04-02-T3 | 04-02 | 2 | BANNER-05 | — | N/A (실측 1건 발동 · 제거율 82.4%) | unit | `.venv-web/bin/python3 -m pytest webapp/tests/test_banner.py::test_D08_제거율초과 -x` | ✅ | ✅ green |
| 04-02-T3 | 04-02 | 2 | BANNER-05 | — | 사람 판단 큐를 만들지 않는다 (D-09) | unit | `.venv-web/bin/python3 -m pytest webapp/tests/test_banner.py::test_사람큐_없음 -x` | ✅ | ✅ green |
| 04-03-T1 | 04-03 | 3 | D-19 (상속) | T-4-02 | `webapp/` 에 다운로더·`PIL` import 0건 (**순회형** — 파일 지정형이 아니다) | unit | `.venv-web/bin/python3 -m pytest webapp/tests/test_argv.py::test_웹앱에_다운로더도_Pillow도_없다 -x` | ✅ | ✅ green |
| 04-06-T1 | 04-06 | 6 | 보안 | T-4-03 | `GET /banner/review` 가 상태를 안 바꾼다 | unit | `.venv-web/bin/python3 -m pytest webapp/tests/test_routes_banner.py::test_GET_무부작용 -x` | ✅ | ✅ green |
| 04-06-T2 | 04-06 | 6 | 보안 | T-4-04 | 썸네일 라우트 경로 탈출 차단 | unit | `.venv-web/bin/python3 -m pytest webapp/tests/test_routes_banner.py::test_경로탈출 -x` | ✅ | ✅ green |
| 04-06-T3 | 04-06 | 6 | 보안 | T-4-05 | 라벨 기록이 POST 전용 + 토큰 필요 | unit | `.venv-web/bin/python3 -m pytest webapp/tests/test_routes_banner.py::test_라벨_POST_토큰 -x` | ✅ | ✅ green |
| 04-08-T3 | 04-08 | 8 | BANNER-02b · BANNER-04 | T-4-32 | **사람 라벨 34건이 증발하지 않는다** · 익명화 유지 · `게이트통과 False` 못박기 | unit | `.venv-web/bin/python3 -m pytest webapp/tests/test_banner.py -k 용팀장라벨` | ✅ | ✅ green (4건) |
| 04-07-T2 | 04-07 | 7 | BANNER-04 (D-03a) | T-4-28 | 전장이 실제로 깔리고 **스킵 줄도 클릭 가능**하다 | e2e (CDP) | `bash webapp/tests/banner_cdp.sh` | ✅ | ✅ exit 0 |
| 04-08-T1 | 04-08 | 8 | 보안 (상속) | — | 9종 전량 — 바인드·rebinding·CSRF·토큰·시크릿 누출 | e2e (curl) | `bash webapp/tests/security_curl.sh` | ✅ | ✅ exit 0 |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## 성공기준별 측정 장치

| ROADMAP 성공기준 | 어떻게 재는가 | 통과 조건 |
|---|---|---|
| 1. 아무 상품이나 골라 배너 순번과 남는 제품 목록을 눈으로 확인 | `/banner/review` 에서 상품 1건 열어 순번 표시와 제품 목록 개수가 산출물 JSON 과 일치하는지 대조 | 사람 1회 확인 |
| 2. **미탐 0%** | **D-03a 의 전장 노출이 측정 장치다.** 사람이 전 상품 전 장을 훑고, 기계가 '제품'이라 한 장을 '배너'로 뒤집은 클릭 수 = 미탐. 분모 = 사람이 '배너'라 한 장 전체 | **미탐 = 0** — 🔴 2026-09-22 실측 **11 / 31 = 35.5%** (95% CI 21.1~53.1%) **불통과** |
| 2. **오탐 10% 이하** | 사람이 '제품'이라 뒤집은 장 수. **분모 확정(D-11): (b) 사람이 제품이라 한 장 전체 = 누락률.** 근거는 D-05 — *"내용 누락이 크레딧 절약보다 나쁘다"* 가 묻는 숫자가 정확히 "전체 제품 이미지 중 몇 %를 잃었나"다. (a) 기계가 배너라 한 장 분모(**정밀도**)는 **같이 보고하되 판정에 안 쓴다** — 장 단위 폭주는 D-08 이 상품 단위로 이미 잡는다 | **누락률 ≤10%** — 🔴 2026-09-22 실측 **2.10%** (16/763) **통과**. 병기한 정밀도분모 오탐율은 **44.4%** (16/36) |
| 2. 게이트 통과 전엔 상세 생성 입력으로 안 쓰임 | 산출물 JSON 에 `게이트통과: false` 를 기본값으로 박고, Phase 5 의 `제품이미지목록()` 이 그 값을 보고 예외 | 자동 (unit test) |
| 3. 스킵 발동 관측 | 산출물 `집계.스킵상품` 과 `상품[].스킵사유`. 화면에 스킵 배지 + 사유. **실측 기대값 2건** (잔여부족 1 · 제거율초과 1) | ✅ 화면에 사유가 보인다. 실측 **8건** (D-07 1 · D-08 1 · **판정불가 6** — 리서치가 모델링 안 한 범주). 🔴 그런데 그 8건이 **미검수 8상품과 같은 집합**이다 — 배지가 "이미 처리됨"으로 읽혔다(`04-GATE.md` §9) |
| 3. 사람 판단 큐 없음 | `routes/banner.py` 에 "보류/대기" 상태나 큐 엔드포인트가 **없음**을 grep 가드로 확인 | 자동 |
| 4. 타오바오번호 distinct 기준 | 게이트 집계 함수에 사본 8건짜리 상품을 넣고 분모가 1 로 세어지는지 | 자동 (unit test) |

---

## Wave 0 Requirements

- [x] `webapp/tests/test_banner.py` — BANNER-01/02b/03b/04/05 순수 함수
- [x] `webapp/tests/test_routes_banner.py` — 라우트 3종 + 보안 3건
- [x] `webapp/tests/cli/test_ocr_determinism.py` — **`.venv` 로 도는 유일한 테스트** (04-04 가 `cli/` 로 한 칸 내렸다)
- [x] `webapp/tests/fixtures/render_content.json` — RESEARCH §Pattern 1 의 함정 6종
- [x] `webapp/tests/fixtures/banner_labels.json` — 리서치 라벨 16상품 308장 정답지 **+ 2026-09-22 `용팀장라벨` 34건**
- [x] `.venv/bin/pip install pyobjc-framework-Vision==12.2.2`
- [x] 프레임워크 설치 불필요 — pytest 기존

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions | 2026-09-22 결과 |
|----------|-------------|------------|-------------------|---|
| 실제 미탐 0% · 오탐 게이트 | BANNER-04 | **D-03a 가 측정 장치 그 자체다.** 기계가 자기 미탐을 셀 수 없다 | `/banner/review` 에서 전 상품 전 장을 훑고 틀린 장만 클릭. 집계 화면에서 미탐/오탐 숫자 확인 | 🟡 **부분 수행** — 52/60 상품 검수 · 라벨 34건. **미탐 11 · 오탐 16 · 미검수 8 → 게이트 불통과.** 미검수 8 = 스킵 8 |
| 배너 정의 경계 4장 확정 | BANNER-02b | 용팀장 기준이 정본. 기계가 대신 정할 수 없다 | 검수 화면 첫 화면에 RESEARCH Appendix A 의 경계 4장을 배치해 판정받는다 | ✅ **확정됐다.** 제품 3 · 배너 1. 규칙: **"제품이 사진에 나오면 제품, 안 나오면 배너"** — 🔴 시각 기준이라 글자 판정기로 직접 구현 불가(`04-GATE.md` §7) |
| 성공기준 1 육안 확인 | — | "눈으로 확인한다"가 기준 문구 | 임의 상품 1건에서 순번·제품목록이 산출물 JSON 과 일치 | ✅ 대조 좌표를 `04-GATE.md` §1-6 에 박았고 검수 중 확인됐다 |

---

## 🔴 재측정 조건 — 다음 회차 out-of-sample (T-4-29)

**2026-09-22 에 어휘군을 8군 → 14군으로 넓혔고, 그 키워드는 이 회차의 미탐 11장을 보고 만들었다.**
그러므로 **이 회차로 다시 잰 숫자는 통과 근거가 아니다.** in-sample 재측정 결과
(미탐 11→3 · 오탐 16→16)는 `04-GATE.md` §8-4 에 적혀 있고, 거기에도 같은 경고가 붙어 있다.

**진짜 측정이 성립하려면 넷이 동시에 참이어야 한다:**

| # | 조건 | 왜 |
|---|---|---|
| 1 | 세트에 **2026-09-22 어휘군이 본 적 없는 상품**이 들어 있다 | 과적합을 벗어난 구간이 있어야 측정이다. 다음 회차를 그대로 쓰거나(권장) 인덱스를 넓힌다(실측 2시간 7분) |
| 2 | **미검수상품 == 0** — 스킵 상품까지 전부 훑는다 | D-12. 안 본 것을 동의로 세면 미탐 0 이 거짓말이 된다. **이번 실패 원인의 절반이 이것이다** |
| 3 | 산출물 `판정규칙.어휘군버전` 이 **2026-09-22 이상**이다 | 어느 규칙으로 낸 숫자인지가 산출물에 남아야 한다(T-4-14) |
| 4 | 보고할 때 **분모를 같이 쓴다** — `0%` 를 분모 없이 쓰지 않는다 | 0/9 는 28.3% 이하, 0/50 은 5.8% 이하다. 같은 "0건"이 전혀 다른 주장이다 |

**2026-09-25 충족 현황 (04-12 재판정, GATE §17):** #1 🔴 미충족(같은 회차) · #2 ✅ · #3 ✅ · #4 ✅ → **3/4**. 그래서 이번 미탐 0 도 통과 근거가 아니다 — 게다가 누락률 13.70% 로 불통과다.

**보고 형식(강제):** `미탐 k/n — 상한 X%(95%)`. 예: `미탐 0/50 — 5.8% 이하(95%)`.
`04-GATE.md` §2-3 이 n 별 상한표를 들고 있다.

**어휘군을 또 고칠 거면 먼저 오탐 비용을 재라:**
`webapp/tests/fixtures/lexicon_ablation.py` 가 후보 키워드별로
새로잡음 / 미탐해소 / **새오탐** / 미검수를 센다. 2026-09-22 에 이 계측이 `맞춤 제작`
(미탐 해소 0 · 새 오탐 3)을 걸러 냈다.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s (전 스위트 ~12초)
- [x] 오탐 분모 확정됨 (Open Question 1) — **D-11: 누락률(사람이 제품이라 한 장 전체). 정밀도는 병기만**
- [x] `nyquist_compliant: true` set in frontmatter
- [x] 배너 정의 경계 4장 확정됨 — 용팀장 답 수신(제품 3 · 배너 1)
- [x] **✅ 미탐 0 — 2026-09-25 재판정에서 달성 (in-sample).** 미탐 **0/50 — 상한 5.8%(95%)**. 2026-09-23 1차 단독은 11/31(35.5%)이었다. 같은 회차라 일반 증명은 아니다(GATE §17-6)
- [x] **✅ 전수 검수(미검수 0) — 달성 (2026-09-23).** 60/60 상품. 남아 있던 스킵 8상품(115장)을 용팀장이 마저 훑었고, 그 안에 숨은 배너는 0장이었다 (04-GATE.md §9-1)
- [ ] **🔴 오탐율_누락률 ≤ 10% — 미달성 (2026-09-25).** 116/847 = **13.70%**. 비전 2차가 상품 정보 장(글자·치수표·도식)을 배너로 찍었다(GATE §17-4)
- [ ] **🔴 게이트 통과 — 미달성.** `gate_passed: false` = `regate.py` 계산값 `게이트통과: false` (2026-09-25, 산출물 `banner_232c3bb3`)
- **재측정 조건(T-4-29) 충족 3/4** — ✅ #2 미검수 0 · ✅ #3 어휘군버전 2026-09-22 · ✅ #4 분모 병기(`미탐 0/50 — 5.8% 이하`) · 🔴 **미충족 #1 — 어휘군이 본 적 없는 상품**(같은 회차 2026-09-20 재사용 = in-sample)
- **D-23 (2026-09-25 용팀장):** Phase 4 를 이 불통과 상태로 종료한다. 기준은 안 고쳤다. 재측정 조건은 Phase 5 이후 새 회차에서 다시 채울 대상으로 남긴다

**Approval:** **검증 계약 자체는 이행됐다 — 자동 검증 22행이 전부 green 이고 수동 항목 3건이
전부 수행됐다. 그 계약이 측정한 결과가 "불통과"다.**

이 둘을 섞지 마라. 검증 장치가 고장나서 못 잰 게 아니라, **제대로 잰 결과가 불합격**이다.
`nyquist_compliant: true` 는 "피드백 간격이 촘촘하다"는 뜻이지 "게이트를 통과했다"가 아니고,
게이트는 `gate_passed: false` 가 따로 들고 있다.

**다음에 이 문서를 여는 사람에게:** 남은 체크박스 셋을 채우는 길은 위 §재측정 조건이다.
그리고 그 전에 `04-GATE.md` §0 의 Q1·Q2·Q3 에 용팀장 답이 있어야 한다.
