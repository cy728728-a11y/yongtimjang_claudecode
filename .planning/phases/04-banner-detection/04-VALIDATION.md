---
phase: 4
slug: banner-detection
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-09-22
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
| **Estimated runtime** | ~20 seconds (현재 355 passed, 2026-09-21 확인) |

> ⚠️ **venv 가 둘이다.** 기존 스위트는 전부 `.venv-web` 으로 돈다. `test_ocr_determinism.py` 만
> `.venv`(CLI)로 돈다 — `pyobjc-framework-Vision` 과 Pillow 가 거기에만 있기 때문이다 (D-19 경계).
> 플래너는 이 이중 실행을 설계에 명시적으로 반영할 것.

---

## Sampling Rate

- **After every task commit:** `.venv-web/bin/python3 -m pytest webapp/tests -q -p no:warnings`
- **After every plan wave:** 위 + `.venv/bin/python3 -m pytest webapp/tests/test_ocr_determinism.py`
- **Before `/gsd:verify-work`:** 전 스위트 green + **사람 전수 검수 완료 + 미탐 0 확인**
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

플랜이 아직 없어 Task ID 는 플래닝 시점에 채운다. 요구사항 단위 계약은 아래가 정본이다.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | 1 | BANNER-01 | — | N/A | unit | `pytest webapp/tests/test_banner.py::test_렌더콘텐츠_이미지목록 -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1 | BANNER-01 | — | 미조회를 0장으로 흡수하지 않는다 | unit | `pytest webapp/tests/test_banner.py::test_None_은_예외 -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1 | BANNER-01 | — | N/A | unit | `pytest webapp/tests/test_banner.py::test_렌더콘텐츠_함정 -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 2 | BANNER-02b | — | N/A | unit | `pytest webapp/tests/test_banner.py::test_어휘군_한중 -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 2 | BANNER-02b | — | 판정이 회차마다 흔들리지 않는다 | integration | `.venv/bin/python3 -m pytest webapp/tests/test_ocr_determinism.py -x` | ❌ W0 (`.venv`) | ⬜ pending |
| TBD | TBD | 2 | BANNER-02b | — | N/A | unit | `pytest webapp/tests/test_banner.py::test_라벨픽스처_미탐0 -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1 | BANNER-03b | T-4-01 | 빈 목록이 '전량'으로 읽히지 않는다 | unit | `pytest webapp/tests/test_banner.py::test_빈목록은_전량이_아니다 -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1 | BANNER-03b | T-4-01 | 미판정 장을 '배너 아님'으로 흡수하지 않는다 | unit | `pytest webapp/tests/test_banner.py::test_미판정_흡수금지 -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1 | BANNER-03b | — | N/A | unit | `pytest webapp/tests/test_banner.py::test_순서유지_상한없음 -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 5 | BANNER-04 | — | N/A | unit | `pytest webapp/tests/test_banner.py::test_게이트집계_분모둘 -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 5 | BANNER-04 | — | 미검수를 통과로 세지 않는다 | unit | `pytest webapp/tests/test_banner.py::test_미검수_분모제외 -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 5 | BANNER-04 | — | N/A | unit | `pytest webapp/tests/test_banner.py::test_타오바오distinct_집계 -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1 | BANNER-05 | — | N/A | unit | `pytest webapp/tests/test_banner.py::test_D07_잔여부족 -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1 | BANNER-05 | — | N/A | unit | `pytest webapp/tests/test_banner.py::test_D08_제거율초과 -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1 | BANNER-05 | — | 사람 판단 큐를 만들지 않는다 | unit | `pytest webapp/tests/test_banner.py::test_사람큐_없음 -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1 | D-19 (상속) | T-4-02 | `webapp/` 에 `requests`·`urllib` 다운로더·`PIL` import 0건 | unit | `pytest webapp/tests/test_argv.py -k import가드 -x` | ⚠️ 기존 가드 확장 | ⬜ pending |
| TBD | TBD | 4 | 보안 | T-4-03 | `GET /banner/review` 가 상태를 안 바꾼다 | unit | `pytest webapp/tests/test_routes_banner.py::test_GET_무부작용 -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 4 | 보안 | T-4-04 | 썸네일 라우트 경로 탈출 차단 | unit | `pytest webapp/tests/test_routes_banner.py::test_경로탈출 -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 4 | 보안 | T-4-05 | 라벨 기록이 POST 전용 + 토큰 필요 | unit | `pytest webapp/tests/test_routes_banner.py::test_라벨_POST_토큰 -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## 성공기준별 측정 장치

| ROADMAP 성공기준 | 어떻게 재는가 | 통과 조건 |
|---|---|---|
| 1. 아무 상품이나 골라 배너 순번과 남는 제품 목록을 눈으로 확인 | `/banner/review` 에서 상품 1건 열어 순번 표시와 제품 목록 개수가 산출물 JSON 과 일치하는지 대조 | 사람 1회 확인 |
| 2. **미탐 0%** | **D-03a 의 전장 노출이 측정 장치다.** 사람이 전 상품 전 장을 훑고, 기계가 '제품'이라 한 장을 '배너'로 뒤집은 클릭 수 = 미탐. 분모 = 사람이 '배너'라 한 장 전체 | **미탐 = 0** |
| 2. **오탐 10% 이하** | 사람이 '제품'이라 뒤집은 장 수. **분모 미확정 — 용팀장 확인 대기** (a) 판정된 장 / (b) 제품 이미지 전체. 실측 최종안은 (a) 15.6% / (b) 1.8% | 확정된 분모 기준 ≤10% |
| 2. 게이트 통과 전엔 상세 생성 입력으로 안 쓰임 | 산출물 JSON 에 `게이트통과: false` 를 기본값으로 박고, Phase 5 의 `제품이미지목록()` 이 그 값을 보고 예외 | 자동 (unit test) |
| 3. 스킵 발동 관측 | 산출물 `집계.스킵상품` 과 `상품[].스킵사유`. 화면에 스킵 배지 + 사유. **실측 기대값 2건** (잔여부족 1 · 제거율초과 1) | 화면에 사유가 보인다 |
| 3. 사람 판단 큐 없음 | `routes/banner.py` 에 "보류/대기" 상태나 큐 엔드포인트가 **없음**을 grep 가드로 확인 | 자동 |
| 4. 타오바오번호 distinct 기준 | 게이트 집계 함수에 사본 8건짜리 상품을 넣고 분모가 1 로 세어지는지 | 자동 (unit test) |

---

## Wave 0 Requirements

- [ ] `webapp/tests/test_banner.py` — BANNER-01/02b/03b/04/05 순수 함수
- [ ] `webapp/tests/test_routes_banner.py` — 라우트 3종 + 보안 3건
- [ ] `webapp/tests/test_ocr_determinism.py` — **`.venv` 로 도는 유일한 테스트**
- [ ] `webapp/tests/fixtures/render_content.json` — RESEARCH §Pattern 1 의 함정 6종
- [ ] `webapp/tests/fixtures/banner_labels.json` — **리서치 라벨 16상품 308장 정답지** (RESEARCH Appendix A). 어휘군 회귀를 CI 가 잡는 근거
- [ ] `.venv/bin/pip install pyobjc-framework-Vision==12.2.2`
- [x] 프레임워크 설치 불필요 — pytest 기존

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 실제 미탐 0% · 오탐 게이트 | BANNER-04 | **D-03a 가 측정 장치 그 자체다.** 기계가 자기 미탐을 셀 수 없다 | `/banner/review` 에서 전 상품 전 장을 훑고 틀린 장만 클릭. 집계 화면에서 미탐/오탐 숫자 확인 |
| 배너 정의 경계 4장 확정 | BANNER-02b | 용팀장 기준이 정본. 기계가 대신 정할 수 없다 | 검수 화면 첫 화면에 RESEARCH Appendix A 의 경계 4장(상품 3-6 · 9-0 · 11-0 · 11-4)을 배치해 판정받는다 |
| 성공기준 1 육안 확인 | — | "눈으로 확인한다"가 기준 문구 | 임의 상품 1건에서 순번·제품목록이 산출물 JSON 과 일치 |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] 오탐 분모 확정됨 (Open Question 1)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
