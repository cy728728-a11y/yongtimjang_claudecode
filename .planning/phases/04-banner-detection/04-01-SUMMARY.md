---
phase: 04-banner-detection
plan: 01
subsystem: testing
tags: [pyobjc, vision-ocr, pytest, fixtures, settings, macos, gitignore]

# Dependency graph
requires:
  - phase: 03-join-detail-state
    provides: "조인 산출물(`join_*.json`) 안의 `uploadDetailContents.renderContent` · 익명화 픽스처 관례(`anonymize_join.py`) · D-19 venv 경계 · 리터럴 가드 3종"
provides:
  - "`.venv`(CLI)에서 도는 Vision OCR + pytest 실행 경로 (저장소 최초)"
  - "`webapp/tests/fixtures/banner_labels.json` — 리서치 라벨 16상품 308장 정답지(익명화)"
  - "`webapp/tests/fixtures/render_content.json` — renderContent 파싱 함정 6종 + 정상 1종"
  - "`webapp/tests/fixtures/anonymize_labels.py` — 라벨 픽스처 결정적 재생성 경로"
  - "`settings.DEFAULTS` Phase 4 키 11개 (임계값·경로·버전 표기 한 곳)"
  - "`webapp-banner/` gitignore — 원본 캐시 271MB/회차가 git 밖"
affects: [04-02, 04-03, 04-04, 04-05, 04-06, 04-07, 04-08]

# Tech tracking
tech-stack:
  added:
    - "pyobjc-framework-Vision==12.2.2 (+ pyobjc-core / cocoa / coreml / quartz 12.2.2) — `.venv` 만"
    - "pytest 9.1.1 (+ iniconfig 2.3.0 / packaging 26.3 / pluggy 1.6.0 / pygments 2.21.0) — `.venv` 만"
  patterns:
    - "픽스처 재생성 스크립트가 **문서를 파싱**한다 — 실코드를 스크립트에 박지 않는다"
    - "정답지의 분자(배너본문 9건)가 비지 않았다는 사실 자체를 별도 테스트로 단언한다"

key-files:
  created:
    - webapp/tests/fixtures/banner_labels.json
    - webapp/tests/fixtures/render_content.json
    - webapp/tests/fixtures/anonymize_labels.py
    - webapp/tests/test_banner_fixtures.py
  modified:
    - webapp/settings.py
    - webapp/tests/conftest.py
    - .gitignore

key-decisions:
  - "`supportedRevisions()` 는 **클래스 메서드**다 — 플랜의 인스턴스 호출 검증 명령이 실측에서 AttributeError. 정정해서 실행했다"
  - "라벨 픽스처 재생성 스크립트는 `04-RESEARCH.md` Appendix A 표를 **파싱**한다. 실코드를 스크립트에 하드코딩하면 익명화가 무의미해진다"
  - "`합계.제품 = 274` 는 라벨모수 308 에서 뺀 값이다. 장수합계 312 에서 빼면 278 — 치수 미확보 4장을 픽스처가 명시적으로 기록한다"
  - "Phase 4 설정 키는 **11개**다 (플랜 본문의 '10개'·'9개'는 열거와 불일치. 열거·acceptance 기준을 따랐다)"
  - "`banner_boundary_samples` 4건만 익명화하지 않는다 — 실제 회차 산출물과 매칭돼야 기능한다"

patterns-established:
  - "Phase 4 픽스처 익명화: 판매자상품코드 `zzNN` · 이미지 URL `zzcdn.example` (Phase 3 `zz*` 관례 승계)"
  - "픽스처 `기대` 필드는 test oracle 이지 CLI 산출물 필드가 아니다 (`join_traps.json` 규약 승계)"
  - "실코드 유출 가드를 `코드` 칸이 아니라 **문서 전체 문자열 훑기**로 집행 (21자 대소문자 혼합 토큰 정규식)"

requirements-completed: [BANNER-02b, BANNER-04]

# Metrics
duration: 8min
completed: 2026-09-22
---

# Phase 4 Plan 01: Wave 0 — 배너 판정이 설 자리 Summary

**`.venv` 에 Vision OCR(revision 3 고정 가능)과 pytest 를 깔고, 리서치 라벨 308장을 문서 파싱으로 재생성되는 익명 정답지로 못 박고, Phase 4 임계값 11키를 `settings.DEFAULTS` 한 곳에 모았다.**

## Performance

- **Duration:** 약 8분
- **Started:** 2026-09-22T01:32 (KST)
- **Completed:** 2026-09-22T01:40 (KST)
- **Tasks:** 3/3
- **Files modified:** 7 (생성 4 · 수정 3)

## Accomplishments

- **`.venv` 로 도는 테스트 경로가 뚫렸다.** 저장소에 `.venv` 로 도는 테스트는 0건이었다(PATTERNS §11). 이제 `pytest 9.1.1` 이 있고 `Vision`·`Quartz` 가 잡힌다 — 04-08 의 `test_ocr_determinism.py` 가 설 자리다.
- **어휘군 회귀의 정답지가 저장소에 있다.** 16상품 308장(배너 9 · 무내용 21 · 경계 4 · 제품 274). 어휘군을 고칠 때 무엇이 깨졌는지 사람 기억이 아니라 기계가 말한다 — 이 페이즈의 1순위 리스크(어휘군 과적합)에 대한 유일한 기계적 방어다.
- **정답지가 문서에서 재생성된다.** `anonymize_labels.py` 가 `04-RESEARCH.md` Appendix A 표 3개를 파싱한다. 실코드를 스크립트에 박지 않으므로 익명화가 유지되고, 다음 회차에 표만 갈면 픽스처가 따라온다.
- **임계값이 한 곳에 있다.** 11키 전부 `settings.DEFAULTS`. `webapp/**` 런타임 소스에 이 숫자들이 리터럴로 없다.
- **원본 캐시 271MB/회차가 git 밖으로 나갔다.**

## Task Commits

1. **Task 1: `.venv` 에 Vision·pytest 설치 + 캐시 경로 gitignore** — `f2ee8ed` (chore)
2. **Task 2: 픽스처 2종 + 재생성 스크립트 + conftest 등록** — `204f23c` (test)
3. **Task 3: `settings.py` Phase 4 키 블록** — `c7403f4` (feat)

## Files Created/Modified

- `webapp/tests/fixtures/banner_labels.json` — 리서치 라벨 정답지. 상품 16 · 배너본문 9(OCR 첫 줄 원문) · 경계본문 4(용팀장에게 물을 질문 원문). 코드는 `zz01`~`zz16`
- `webapp/tests/fixtures/render_content.json` — 파싱 함정 6종(`1_상세미조회` · `2_공백만` · `3_순번보존` · `4_한장짜리` · `5_전장404` · `6_번역플래그4종`) + `정상` 1종. URL 은 전부 `zzcdn.example`
- `webapp/tests/fixtures/anonymize_labels.py` — Appendix A 표 파싱 → 익명 JSON. 매핑은 정렬된 실코드 목록의 인덱스라 결정적
- `webapp/tests/test_banner_fixtures.py` — 픽스처 모양 회귀 5건
- `webapp/settings.py` — `# ── Phase 4 (배너 판정) 에서 더한 키 ───` 블록 11키
- `webapp/tests/conftest.py` — `render_content_traps` · `banner_labels` 픽스처 + 상수 2개 + Phase 4 익명화 규율 문단
- `.gitignore` — `webapp-banner/`

## 설치 실측 (A7 가정의 근거)

```
$ uv pip install --python .venv/bin/python3 "pyobjc-framework-Vision==12.2.2" pytest
Installed 10 packages
 + pyobjc-core==12.2.2  + pyobjc-framework-cocoa==12.2.2  + pyobjc-framework-coreml==12.2.2
 + pyobjc-framework-quartz==12.2.2  + pyobjc-framework-vision==12.2.2
 + pytest==9.1.1  + iniconfig==2.3.0  + packaging==26.3  + pluggy==1.6.0  + pygments==2.21.0

$ .venv/bin/python3 -c "..."
class supportedRevisions: [1, 2, 3]
revision(default): 3
revision(after set): 3          # setRevision_(3) 이 먹는다
CGImageSourceCreateWithURL: True
Pillow: 12.3.0                  # 이미 있던 것. 재설치 안 함

$ .venv/bin/python3 -m pytest --version
pytest 9.1.1

$ .venv-web/bin/python3 -c "find_spec('Vision') is None"   → exit 0   # D-19 경계 유지
```

`.venv` 에서 `from webapp import paths, settings` 도 확인했다(PATTERNS §11 ②의 전제) —
`banner_vision_revision = 3` 이 CLI 인터프리터에서도 읽힌다.

**기본 revision 이 이미 3 이다.** 그래서 `setRevision_(3)` 을 빼도 **오늘은** 같은 결과가 나온다 —
이게 D-10 이 "박는 것이 요점"이라고 말한 이유 그대로다. 안 박으면 OS 가 기본값을 4로 올리는 날
아무 코드도 안 바뀐 채 판정만 조용히 달라진다. 04-02/04-08 은 반드시 명시적으로 박아라.

## Decisions Made

- **`supportedRevisions()` 는 클래스 메서드다.** 인스턴스에는 없다. 플랜의 `<verify>` 명령을 정정했다(아래 Deviations 1).
- **재생성 스크립트가 문서를 파싱한다.** 대안은 실코드 16개를 스크립트에 박는 것인데, 그러면 `banner_labels.json` 만 익명이고 그 옆 파일이 원본을 들고 있는 우스운 상태가 된다. Appendix A 표를 읽으면 실코드가 저장소에 새로 늘지 않는다(RESEARCH.md 에 이미 있는 것 하나뿐).
- **`제품 274` 를 빼기로 구하지 않는다.** 장수합계 312 − (9+21+4) = 278 이라 조용히 4장이 틀린다. 라벨 모수 308(치수 확보 기준)을 픽스처에 명시하고 차이 4장을 `_모수주석` 에 남겼다.
- **실코드 유출 가드를 `코드` 칸이 아니라 문서 전체로 확장했다.** 주석·출처 필드로 새는 경로가 남아 있었다(Rule 2, 아래 Deviations 3).
- **픽스처 모양 회귀를 4개가 아니라 5개 썼다.** 플랜의 4개는 그대로 있고, "라벨이 사람 라벨이 아니라는 경고문이 살아 있는가"를 5번째로 더했다 — 그 문장을 지우는 것이 "어휘군이 자기 답지를 채점하는" 사고의 첫 단추다(A1).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] 플랜의 `supportedRevisions()` 검증 명령이 실측에서 터진다**
- **Found during:** Task 1
- **Issue:** 플랜 `<verify><automated>` 가 `r = VNRecognizeTextRequest.alloc().init(); r.supportedRevisions()` 형태다. 실제로는 `AttributeError: 'VNRecognizeTextRequest' object has no attribute 'supportedRevisions'` — Vision 프레임워크에서 이건 **클래스 메서드**(`+[VNRequest supportedRevisions]`)다.
- **Fix:** 클래스 호출(`Vision.VNRecognizeTextRequest.supportedRevisions()`)로 검증했다. 추가로 `revision()` 기본값과 `setRevision_(3)` 이후 값도 같이 찍어 D-10 이 요구한 "박는 것"이 실제로 먹는지 확인했다.
- **Files modified:** 없음(검증 명령만). 04-02/04-08 이 같은 실수를 하지 않도록 이 SUMMARY 에 실행 형태를 남긴다.
- **Verification:** `class supportedRevisions: [1, 2, 3]` · `revision(after set): 3`
- **Committed in:** `f2ee8ed` (커밋 메시지에 실측 출력 기록)

**2. [Rule 3 - Blocking] 워크트리에 `.venv`/`.venv-web`/`workspace.toml` 이 없어 아무것도 검증할 수 없었다**
- **Found during:** Task 1
- **Issue:** 셋 다 `.gitignore` 대상이라 병렬 실행 워크트리에 존재하지 않는다. `.venv-web/bin/pytest` 가 없고, `workspace.toml` 이 없으면 `test_불사자_기대닉네임이_리터럴로_박혀있지_않다` 가 `required=True` KeyError 로 실패한다(가드가 의도한 대로).
- **Fix:** 워크트리 안에 `.venv` · `.venv-web` 심링크(본 저장소 것을 가리킴)와 `workspace.toml` 사본을 만들었다. 셋 다 gitignore 대상이라 **커밋되지 않았다** — 매 커밋 전 `git diff --cached --name-only` 로 확인했다. 워크트리가 제거되면 같이 사라진다.
- **Files modified:** 없음(커밋된 것 0건)
- **Verification:** 3개 커밋 전부 의도한 파일만 담겼다. `git diff --diff-filter=D fe457c09..HEAD` → 삭제 0건
- **Committed in:** 해당 없음

**3. [Rule 2 - Missing critical] 실코드 유출 가드가 `코드` 칸만 봤다 (T-4-09)**
- **Found during:** Task 2
- **Issue:** 플랜의 단언은 "모든 `코드` 값이 `zz` 로 시작한다"다. 그러면 `출처`·`조인산출물`·`ocr_첫줄` 같은 자유 문자열 필드로 실코드가 새는 경로가 그대로 열려 있다 — 익명화의 목적(T-4-09: 저장소 공개 시 영업 정보 동반 유출)을 절반만 막는다.
- **Fix:** 문서 전체의 문자열(키 포함)을 재귀로 훑어 **21자 대소문자 혼합 영숫자 토큰**이 하나도 없음을 단언한다. 정규식 민감도도 확인했다: 실코드 2종 → 탐지, `zz01`·`join_323b1918`·`2026-09-20`·OCR 한글 문장 → 비탐지(오탐 0).
- **Files modified:** `webapp/tests/test_banner_fixtures.py`
- **Verification:** `test_라벨픽스처에_실코드가_없다` green
- **Committed in:** `204f23c`

**4. [Rule 2 - Missing critical] 배너본문/경계본문이 상품별 라벨과 어긋나도 아무도 몰랐다**
- **Found during:** Task 2
- **Issue:** 플랜의 단언은 "`배너본문` 9건이 비어 있지 않은 `ocr_첫줄` 을 갖는다"까지다. 9건이 **어느 장인지**는 안 본다 — `배너본문` 이 상품별 `배너` 리스트와 다른 장을 가리켜도 통과한다. 04-04 의 미탐 0 회귀는 두 리스트가 같은 9장을 가리킨다는 전제 위에 선다.
- **Fix:** `{(코드, 순번)}` 집합이 상품별 `배너`/`경계` 리스트와 **정확히 같은지** 단언했다. 순번이 장수 범위 안인지도 같이 본다(순번이 밀리면 라벨이 통째로 어긋난다는 규약).
- **Files modified:** `webapp/tests/test_banner_fixtures.py`
- **Verification:** `test_배너본문_9건이_비어있지_않다` · `test_라벨_합계가_리서치_실측과_같다` green
- **Committed in:** `204f23c`

---

**Total deviations:** 4 auto-fixed (Rule 1 ×1 · Rule 2 ×2 · Rule 3 ×1)
**Impact on plan:** 범위 확장 없음. 1은 플랜의 검증 명령 오류 정정, 2는 워크트리 환경 복구(커밋 0건), 3·4는 플랜이 세운 단언이 목적(T-4-09 / 04-04 의 분자)을 절반만 지키던 것을 메운 것이다.

## Issues Encountered

- **플랜 안에서 Phase 4 키 개수가 세 번 다르게 적혀 있다** — `must_haves.truths` 는 "임계값 9개", `artifacts` 는 "설정 키 10개", `<action>` 은 11개를 열거하고 `acceptance_criteria` 는 11개를 전부 검사한다. 열거·acceptance 를 정본으로 보고 **11키**를 넣었다. 플래너가 `banner_boundary_samples`(임계값이 아니라 표본 목록)를 세다 말았거나 `banner_cache_dir`/`banner_thumb_dir`(경로라 '임계값'이 아니다)를 뺀 것으로 보인다. 04-02 이후가 키 이름으로 읽으므로 개수 표기 차이는 기능에 영향이 없다.
- `.venv` 설치는 본 저장소의 공유 자원을 바꾼다(워크트리 밖). `.venv` 는 gitignore 대상이라 병합 충돌은 없지만, **이 설치는 워크트리가 제거돼도 남는다.** 의도된 것이다(플랜 Task 1).

## Known Stubs

없다. 이 플랜은 실행 코드를 만들지 않는다 — 도구·픽스처·설정값뿐이다.

## Threat Flags

없다. 새로 생긴 네트워크 엔드포인트·인증 경로·스키마 변경이 0건이다.

위협 등록부 4건 처리 결과:
- **T-4-SC** (PyPI → `.venv`): `==12.2.2` 로 못박아 설치. RESEARCH §Package Legitimacy Audit 3/3 `[OK]` 그대로 — 설치가 1회에 성공했고 대체 패키지를 찾는 일이 없었다
- **T-4-02** (`.venv-web` 오염): `--python .venv/bin/python3` 명시 + `.venv-web` 에서 `find_spec('Vision') is None` 단언 통과
- **T-4-07** (캐시 271MB): `.gitignore` `webapp-banner/` + `banner_keep_runs=2`. 집행은 04-03
- **T-4-09** (픽스처 실코드): `zzNN` 익명화 + 문서 전체 훑기 가드(Deviations 3)

## ⚠️ 다음 회차에 낡는 값

`settings.DEFAULTS["banner_boundary_samples"]` 4건은 **익명화되지 않은 실제 판매자상품코드**이고 git 에 커밋됐다.

```
dnb2lYw0omRnoG121KzBL:6 · fElaVlxOzkeSVkDotMrAJ:0 · sLix0885VmdKsGxunAznE:0 · sLix0885VmdKsGxunAznE:4
```

- **익명화할 수 없는 이유:** 검수 화면이 실제 회차 산출물에서 이 장들을 찾아 첫 화면에 배치해야 한다. `zzNN` 으로 바꾸면 영원히 못 찾는다.
- **다음 회차에는 반드시 낡는다.** 물갈이로 상품코드가 재발급된다. 04-07 의 "못 찾았다" 폴백이 낡음을 부드럽게 처리하므로 **기능은 안 깨지지만, 경계 4장 확인 기능은 그 회차에 조용히 빈다.**
- 회차가 바뀌면 이 값을 다시 떠라. `banner_labels.json` 과 달리 `workspace.toml [webapp]` 로 덮을 수 있다.

## Next Phase Readiness

04-02(순수 모듈 `webapp/banner.py`)가 바로 쓸 수 있는 것:

- `render_content_traps` 픽스처 — 파서가 지켜야 할 6종이 `기대` oracle 과 함께 있다
- `banner_labels` 픽스처 — 어휘군·스킵 규칙 회귀의 정답지
- `settings.DEFAULTS` 11키 — 임계값을 `banner.py` 나 `banner_scan.py` 에 박지 마라. `settings.cfg("키", settings.DEFAULTS["키"])` 로만 읽는다

04-08(`test_ocr_determinism.py`)이 바로 쓸 수 있는 것:

- `.venv/bin/python3 -m pytest webapp/tests/test_ocr_determinism.py` — **파일 하나만 지목해 돌린다**(`.venv` 에 fastapi 가 없어 `webapp/tests` 전체 수집은 collect 에러)
- `pytest.importorskip("Vision")` 을 쓰지 마라. 미설치는 **실패**여야 한다(conftest 136-138 의 같은 함정)
- `supportedRevisions()` 는 **클래스 메서드**다

**막는 것 없음.** 전 스위트 360 green (기존 355 + 신규 5).

---
*Phase: 04-banner-detection*
*Completed: 2026-09-22*
