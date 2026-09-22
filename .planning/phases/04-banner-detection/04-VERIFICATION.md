---
phase: 04-banner-detection
verified: 2026-09-22T23:50:00Z
status: gaps_found
score: 7/9 must-haves verified
overrides_applied: 0
gaps:
  - truth: "현 회차 연결 전량 전수 검수로 미탐 0%를 증명한다 (phase goal · BANNER-04 · ROADMAP SC2)"
    status: failed
    reason: >
      실측 미탐 11/31 = 35.5% (95% CI 21.1~53.1%). 게이트 판정 기준(미탐==0)을 명백히 못 채웠다.
      04-08 executor가 밤에 어휘군을 8군→14군으로 확장해 같은 세트로 재측정하니 미탐 3/31=9.7%까지
      낮아졌지만, 이 숫자는 미탐 11장의 OCR을 보고 만든 키워드로 그 11장을 채점한 in-sample
      결과라고 04-GATE.md·04-VALIDATION.md 양쪽이 스스로 명시했다 — 통과 근거로 쓸 수 없다.
      out-of-sample 세트로 재측정된 적이 없다. 미탐 3장 중 최소 1장(zz13:4)은 구조적으로
      글자 기준 판정기가 못 잡는 장(경계 4장 중 용팀장과 불일치했던 바로 그 장)이라는 사실도
      04-GATE.md §8-5가 스스로 기록해 뒀다.
    artifacts:
      - path: ".planning/phases/04-banner-detection/04-GATE.md"
        issue: "§5-3 · §8-4 — 미탐 11(검수 시점 어휘군) / 3(in-sample 확장 후, 통과 근거 아님)"
    missing:
      - "out-of-sample 세트(다음 회차 또는 확장된 인덱스)로 재측정 — 04-VALIDATION.md §재측정 조건 4개 동시 충족"
      - "용팀장 Q1(스킵 8상품 검수)·Q2(재측정 세트)·Q3(비전 AI 승인 여부) 결정"
  - truth: "미검수 상품 0 — 전수 검수가 실제로 전수다 (D-12)"
    status: failed
    reason: >
      52/60 상품만 검수됐다. 미검수 8상품(115장)의 집합이 ⏭ 스킵 배지가 붙은 8상품과 정확히
      일치한다 — "기계가 Phase 5 입력에서 뺐다"는 배지 의미를 사람이 "내가 볼 필요 없다"로
      읽은 구조적 함정이다(04-GATE.md §9). 검수 화면(04-07)은 스킵 상품도 전장을 깔도록
      설계·회귀(V-BANNER-02)까지 갖췄는데도 실제 사용에서 건너뛰어졌다 — 화면이 "이 줄도
      봐야 한다"를 말해주지 않는다.
    artifacts:
      - path: "webapp/templates/banner_review.html"
        issue: "스킵 배지가 '이미 처리됨'으로 오인되는 것을 막는 시각적 강조가 없다 (완화 후보만 적혀 있고 미구현)"
    missing:
      - "8개 스킵 상품 실제 검수 완료"
      - "미검수 카운트를 강조하고 남은 상품으로 스크롤하는 UI (04-GATE.md §9 완화 후보, 아직 파일 범위 밖)"
---

# Phase 4: 홍보배너 식별 Verification Report

**Phase Goal:** 기존 상세 이미지에서 중국 판매사 홍보배너만 골라내고, 실제 작업에 쓰기 전에 현 회차 연결 전량 전수 검수로 미탐 0% 를 증명한다
**Verified:** 2026-09-22
**Status:** gaps_found
**Re-verification:** No — initial verification

## 중요 — 04-GATE.md가 이미 정본이다

이 검증은 04-GATE.md의 측정을 재발견한 것이 아니다. `.planning/phases/04-banner-detection/04-GATE.md`(§0 아침 브리핑·§5 게이트 판정)와 `04-VALIDATION.md`(Sign-Off)가 이미 **불통과**를 스스로 기록·서명해 뒀다. 이 문서의 역할은 그 기록이 코드베이스의 실제 상태와 일치하는지, 그리고 "게이트 불통과가 실제로 무언가를 막고 있는지"를 독립적으로 재현·검증하는 것이다.

**결론: 04-GATE.md의 자기 판정은 정직하고 정확하다.** 실행된 테스트 3종(446 + 4 + CDP)을 이 세션에서 직접 재실행해 동일한 결과를 재현했고, `게이트통과 is not True` 구조적 차단이 실제 코드에 존재하며 단위 테스트가 그것을 집행하는 것을 확인했다. 문제는 인프라가 아니라 **판정기의 정확도(미탐 35.5%)와 검수의 완전성(52/60)** 두 가지이며, 둘 다 04-08 SUMMARY와 04-GATE.md가 스스로 "불통과"라 적었다.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|---|---|---|
| 1 | `renderContent` 에서 상세 이미지 URL을 문서 순서대로 뽑고 `None`(미조회)과 0장을 구분한다 (BANNER-01) | ✓ VERIFIED | `webapp/banner.py::상세이미지목록` · `webapp/tests/test_banner.py` 21개 함수 중 다수가 이를 검증, 전체 스위트 446 passed (직접 재실행 확인) |
| 2 | 배너 판정이 상품 내부에서 끝나는 신호(macOS 온디바이스 Vision OCR + 어휘군)로 이뤄지고 토큰·크레딧·네트워크 0 (BANNER-02b) | ✓ VERIFIED | `.claude/skills/bulsaja-detail-page/scripts/banner_scan.py::ocr_2패스`·`어휘군걸림` · `setRevision_(3)` 확인 · 04-GATE.md §1-8 "토큰/크레딧/MCP 0/0/0" 실측(잔액 스캔 전후 932,377 동일) |
| 3 | 산출물이 제품 이미지 목록을 원래 순서·개수 제한 없이 싣는다 (BANNER-03b) | ✓ VERIFIED | `webapp/banner.py::제품이미지목록` 반환이 원본 순서 리스트, 상한 로직 없음(코드 확인) · `test_banner.py:236-240`에서 순서 보존 단언 |
| 4 | 제거율 50% 초과 또는 잔여 2장 미만 상품이 통째로 스킵되고 사유가 산출물에 남는다 (BANNER-05) | ✓ VERIFIED | `banner_scan.py::스킵규칙적용` · 실스캔에서 D-07 1건·D-08 1건 정확히 발생(04-GATE.md §1-5), 계획 기대와 일치 |
| 5 | 라벨링 세트·게이트 집계가 타오바오상품번호 distinct 기준으로 돌아 물갈이 사본이 분모를 부풀리지 않는다 (성공기준 4) | ✓ VERIFIED | `webapp/banner.py::게이트집계`의 대표/순서 dedup 로직 확인 · 실측 62상품 → 60 distinct (04-GATE.md §5) |
| 6 | 검수 화면이 상품의 전 이미지를 전부 깐다 — 배너로 판정한 장만 보여주지 않는다 (D-03a, 측정 장치 그 자체) | ✓ VERIFIED | `bash webapp/tests/banner_cdp.sh` 직접 재실행 → exit 0, V-BANNER-00~04 전량 PASS. `figure` 수 == 산출물 `집계.장`(19==19), 스킵 상품도 전장 노출 확인 |
| 7 | 게이트를 통과하기 전에는 제품 이미지 목록이 Phase 5 입력이 될 수 없다 — 구조로 막는다 (BANNER-04 구조적 절반) | ✓ VERIFIED | `webapp/banner.py::제품이미지목록`의 `게이트통과 is not True` 가드를 코드로 직접 확인 — 인자 누락·`False`·truthy값(`1`) 전부 `ValueError`. `webapp/tests/test_banner.py:276-301`이 세 경로 전부 단위 테스트로 집행. `.planning/phases/05-*` 폴더가 존재하지 않아(구조 확인) 이 페이즈가 실제로 아무것도 하위 단계에 흘리지 않았다는 것도 별도로 확인됨 |
| 8 | **현 회차 연결 전량 전수 검수로 미탐 0% 를 증명한다 (phase goal 자체 · BANNER-04 실질적 절반)** | ✗ **FAILED** | 실측 미탐 11/31 = 35.5% (95% CI 21.1~53.1%). 04-GATE.md §5-3 "🔴 불통과(0이 조건)". 야간 어휘군 확장으로 in-sample 3/31=9.7%까지 낮췄으나 04-GATE.md·04-VALIDATION.md 양쪽이 "통과 근거 아니다(in-sample/overfit)"라고 스스로 명시 |
| 9 | 미검수 상품 0 — 전수(全數)가 실제로 전수다 (D-12) | ✗ **FAILED** | 52/60 상품만 검수. 미검수 8상품 = 스킵 8상품 집합과 정확히 일치(04-GATE.md §9) — "이미 처리됨"으로 오인된 구조적 함정 |

**Score:** 7/9 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `webapp/banner.py` | 순수 판정 접근자 — 파싱·스킵읽기·게이트집계 (min 120줄) | ✓ VERIFIED | 377줄. import는 `html.parser` 하나뿐(순수성 확인). `게이트집계`·`제품이미지목록`·`상세이미지목록` 등 6개 함수 존재 |
| `.claude/skills/bulsaja-detail-page/scripts/banner_scan.py` | CLI 스캐너 — 다운로드·OCR·판정·산출물 (min 250줄) | ✓ VERIFIED | 1268줄. `허용URL인가`(SSRF 단일관문) · `ocr_2패스` · `setRevision_(3)` 확인 |
| `webapp/banner_store.py` | 사람 라벨 read/write | ✓ VERIFIED | 207줄. sqlite3 접근이 이 모듈에만 있음(코드 확인) |
| `webapp/routes/banner.py` | GET review · GET thumb · POST label · POST confirm | ✓ VERIFIED | 680줄. `get_thumb`이 정수 인덱스(`product_i`/`chap_i`)만 받음 — 경로탈출 구조적 차단 확인 |
| `webapp/templates/banner_review.html` / `_banner_strip.html` | 검수 화면 — 전장 스트립 + 경계4장 | ✓ VERIFIED | CDP 브라우저 회귀로 실제 렌더링·클릭·서버 조각 교체 확인 |
| `.planning/phases/04-banner-detection/04-GATE.md` | 게이트 실측 기록 | ✓ VERIFIED | 726줄. 미탐/오탐 두 분모, 경계 4장 기준, 대응 이력 모두 존재. 스스로 "불통과" 명시 |
| `.planning/phases/04-banner-detection/04-VALIDATION.md` | Per-Task Verification Map 마감 + Sign-Off | ✓ VERIFIED | `nyquist_compliant: true` · `gate_passed: false` · 재측정 조건 4개 명시 |
| `webapp/tests/fixtures/banner_labels.json` | 리서치 라벨 308장 + 용팀장라벨 34건 | ✓ VERIFIED | 픽스처 존재, `test_banner_fixtures.py` 회귀 통과 |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `webapp/routes/jobs.py` | `banner_scan.py` | `POST /jobs/banner/scan` → `argv.BannerArgv` | ✓ WIRED | 04-GATE.md §1-1 실스캔이 HTTP 경로로 접수·완주(잡 `97c3578d`, exit 0) 실측 |
| `webapp/routes/banner.py` | `jobs.latest_done('banner_scan')` | 산출물 조회, glob 미사용 | ✓ WIRED | 04-GATE.md "산출물을 찾은 길 = latest_done, glob 0회" 명시 및 실행 로그로 확인 |
| 검수 화면 클릭 | `banner_label` / `banner_confirm` DB | `POST /banner/label`·`/banner/confirm` | ✓ WIRED | CDP 회귀로 실제 POST→DB행 확인(라벨 1·확인 1), `webapp.db` 실측 34/52건 일치 확인 |
| `webapp/banner.py::게이트집계` | `제품이미지목록` 게이트 가드 | `게이트통과` bool 전달 | ✓ WIRED | 코드상 `게이트집계(...)["게이트통과"]`가 유일한 출처로 문서화되고, `제품이미지목록`이 그 값이 아니면 예외 — **미통과 상태에서 Phase 5로 데이터가 흘러갈 구조적 경로가 없음을 확인** |
| `_장조각`(라벨 POST 응답) | `_화면투영` | `run_dir` 인자 | ✓ WIRED (회귀 후) | 실제로 깨졌던 이력 있음 — `3144df8`에서 `run_dir` 기본값 `""` 버그를 수정하고 왕복 회귀(`test_돌려받은_조각을_또_누를_수_있다`)로 고정. 재실행해 PASS 확인 |

### 회귀·보안 재실행 결과 (이 세션에서 직접 재현)

| 검증 | 04-GATE.md 주장 | 이 세션 재실행 | 일치 |
|---|---|---|---|
| `.venv-web/bin/pytest webapp/tests -q` | 446 passed | **446 passed, exit 0** | ✓ |
| `.venv/bin/pytest webapp/tests/cli -q` | 4 passed | **4 passed, exit 0** | ✓ |
| `bash webapp/tests/banner_cdp.sh` | exit 0, V-BANNER-00~04 PASS | **exit 0, 전량 PASS** (실제 서버 기동·종료까지 확인) | ✓ |
| `webapp.db` 의 `banner_label`/`banner_confirm` 행 수 | 34 / 52 | **34 / 52** (직접 sqlite3 조회) | ✓ |
| 포트 8765 서버 | 떠 있음 | `lsof` 로 LISTEN 확인, 건드리지 않고 유지 | ✓ |

`security_curl.sh`는 실제 서버를 대상으로 하는 스크립트라 이번 세션에서는 재실행하지 않았다(안내에 없던 항목, 상태 변경 위험 회피). GATE.md의 9종 PASS 기록은 코드 검토(가드 3층·경로탈출 불가능 구조·GET 상태변경 0건)로 교차 확인했다.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| BANNER-01 | 04-02, 04-05 | renderContent 상세 이미지 목록 추출 | ✓ SATISFIED | `webapp/banner.py::상세이미지목록` + 잡 배선(04-05) 둘 다 실동작 확인 |
| BANNER-02b | 04-01, 04-04 | 상품 내부 신호(OCR 어휘군)로만 판정, 토큰·크레딧 0 | ✓ SATISFIED | `banner_scan.py` OCR 2패스 + 어휘군, 실스캔 크레딧/토큰/MCP 0 실측 |
| BANNER-03b | 04-02 | 제품 이미지 목록 원순서·무제한 | ✓ SATISFIED | `제품이미지목록` 코드 확인 |
| BANNER-04 | 04-02(partial), 04-06, 04-08 | 라벨링 검증으로 미탐 0% 통과해야 실사용 | 🔴 **BLOCKED (구조는 있으나 실질 미달성)** | 구조적 차단(게이트=false→예외)은 완전히 동작. 그러나 **정의된 목적인 "미탐 0% 달성"은 미달**(35.5%). REQUIREMENTS.md 자체도 이 항목을 여전히 "Pending"으로 남겨둠(211-217행) — 05-06/08 SUMMARY의 "requirements-completed: [BANNER-04]"는 구조 이행만을 뜻하고, REQUIREMENTS.md 마스터 표와 충돌하지 않는다(SUMMARY가 실질 달성을 주장하지 않음) |
| BANNER-05 | 04-02, 04-04, 04-06, 04-07, 04-08 | 제거율/잔여 스킵 규칙 | ✓ SATISFIED | D-07·D-08 실측 각 1건, 계획과 일치 |

**Orphaned requirements:** 없음. REQUIREMENTS.md의 Phase 4 매핑(BANNER-01/02b/03b/04/05)이 8개 플랜의 `requirements:` 필드에 전부 포함됨. (BANNER-02·03은 대체됨으로 이미 명시적으로 처리됨.)

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| (없음) | — | TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER grep 결과 0건 — 페이즈가 만든 8개 핵심 파일 전수 스캔 | — | 디버트 마커 없음 |

**실제로 발견된 결함(이미 수정·회귀 고정됨, anti-pattern이 아니라 참고용):** `webapp/routes/banner.py::_화면투영`의 `run_dir` 기본값 `""`이 라벨 POST 응답 조각의 `hx-vals`를 비워 같은 장의 두 번째 클릭부터 422를 유발했다. 441개 테스트가 초록인 상태에서 실사용(전수 검수) 중에 사람이 직접 발견했다 — **htmx 조각 교체 경로가 왕복(요청→응답 조각→재요청)으로 검증되지 않으면 단위 테스트 그린이 실사용 결함을 못 잡는다는 것을 보여준 사례.** `3144df8`에서 수정하고 `test_돌려받은_조각을_또_누를_수_있다`로 고정, 이 세션에서 재실행해 PASS 확인. 이 결함은 이제 닫혔지만, **같은 패턴(서버가 응답 조각에 숨은 필수 컨텍스트를 흘리는 것)이 다른 htmx 조각 교체 경로에도 남아 있을 가능성**은 이번 검증 범위에서 전수 조사하지 않았다 — Phase 5가 유사한 htmx 조각 패턴을 새로 만들 때 참고할 사항으로 남긴다.

### Human Verification Required

없음. 남은 것은 "테스트해서 알려달라"는 항목이 아니라 **용팀장이 이미 04-GATE.md §0에서 직접 답해야 할 것으로 지목된 전략적 결정 3건**이다(재검수 여부, 재측정 세트, 비전 AI 승인 여부). 검증자가 대신 판단할 수 없고, 확인 절차가 아니라 의사결정이라 human_verification 형식에 넣지 않았다 — 04-GATE.md §0 표를 그대로 사용자에게 보여주면 된다.

### Gaps Summary

**헤드라인: 이 페이즈가 만든 배너 판정 기계·잡 배선·검수 화면·게이트 차단 장치는 전부 실재하고 실제로 동작한다. 그러나 페이즈의 목표 문장 자체("미탐 0%를 증명한다")는 달성되지 않았고, 이것은 은폐된 것이 아니라 04-GATE.md와 04-VALIDATION.md가 스스로 기록·서명한 사실이다.**

1. **미탐 35.5%** — 용팀장이 배너라 표시한 31장 중 11장을 기계가 놓쳤다. 밤사이 어휘군을 8→14군으로 넓혀 같은 세트에서 3/31(9.7%)까지 낮췄지만, 이 숫자는 미탐 장의 실제 OCR을 보고 만든 키워드로 그 장들을 채점한 **in-sample/과적합 숫자**라고 실행자 스스로 두 문서에서 강조했다. 이 검증도 그 판단에 동의한다 — 통과 근거로 인정하지 않았다.
2. **미검수 8상품(115장)** — 전수(D-12)가 전제인데 8개가 안 보였다. 우연이 아니라 스킵 배지를 사람이 "이미 끝난 줄"로 잘못 읽는 구조적 함정이다(검수 화면은 스킵 상품도 전장을 깔도록 이미 설계·테스트돼 있다 — 화면의 문제가 아니라 배지 강조의 문제).
3. **구조적 안전장치는 진짜다.** `webapp/banner.py::제품이미지목록`의 `게이트통과 is not True` 가드는 코드로 실재하고, 단위 테스트 3종(인자 누락·False·truthy 1)이 그것을 직접 집행하며, Phase 5 폴더가 아직 존재하지 않는다는 사실로 "이 차단이 실제로 무언가를 막았다"는 것이 이 세션에서 별도로 확인됐다. 게이트가 실패했다고 해서 이 안전장치가 허수인 것은 아니다.
4. **정직성 감사 결과 이상 없음.** 8개 SUMMARY의 `requirements-completed`·`Deviations`·in-sample 경고 문구는 코드·테스트 재실행과 전부 일치했다. 과장이나 은폐를 찾지 못했다.
5. **문서 정합성 주의 (검증 범위 밖이지만 반드시 알려야 함):** `.planning/ROADMAP.md` 26행이 "Phase 4: 홍보배너 식별 ... (completed 2026-09-22)"로 **`[x]` 완료 표시**돼 있다. 그러나 이 페이즈 자신의 게이트는 "불통과"이고 `.planning/STATE.md`도 `completed_phases: 2`(Phase 4 미포함)·`Current focus: Phase 04`로 남아 있다. ROADMAP의 체크박스가 "8개 플랜 실행 완료"와 "게이트 통과"를 구분하지 못하고 있다면, 다음에 이 파일만 보는 사람은 페이즈가 성공했다고 오해할 수 있다. `/gsd-verify-work` 이후 이 체크박스를 게이트 결과에 맞게 정정할 것을 권한다.

---

*Verified: 2026-09-22*
*Verifier: Claude (gsd-verifier)*
