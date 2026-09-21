---
phase: 03-join-detail-state
verified: 2026-09-21T06:22:05Z
status: passed
score: 10/10 must-have truths verified at code level + 1 human verification item CLOSED 2026-09-21 (JOIN-02 ④⑤ 둘 다 PASS — 03-HUMAN-UAT.md)
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 6/10
  gaps_closed:
    - "미해소 사유가 추출실패/번호없음/미조회로 서로 다른 값이고 광고청소·시스템이 분리된다 (JOIN-02 / CR-01) — 마켓그룹 조회 오류가 exit 2로 막히고, board.py::_load_join 이 빈 마켓그룹도 None으로 내린다"
    - "사본 N건이 보이고 기작업 상품이 기본 선택에서 빠진다 (JOIN-03 / STATE-05 / CR-02) — 팬아웃 조회 실패가 사본=None·팬아웃미조회=True로 행에 기록되고, selectable()이 그 행을 기본 선택에서 제외한다"
    - "인덱스 히트가 재검증 없이 쓰이지 않는다, 히트 원본이 정직하다 (JOIN-04 / CR-03) — workdata 오류가 unresolved=1(미조회)로 기록되어 ss_index_resume.처리완료()가 다시 조회한다"
  gaps_remaining: []
  regressions: []
human_verification_resolved: 2026-09-21
human_verification_result: "PASS(2/2) — ④ 용팀장이 `소형이동식오피스`(번호 없음·703행, 최난도)를 사유 문구만 들고 네이버에서 찾아 `25-2 소형이동식오피스` 로 수정 완료. 코드 실측으로 수정이 해소로 이어짐을 확인(market_number→25-2, 불사자 마켓그룹에 25-2 존재=5번_용쌤25-2/1001822, 인덱스 미보유→재스캔 시 빨강→파랑 이동). `판매상품_17-3_오운웨이컴퍼니` 도 함께 수정. ⑤ 진술 그대로: \"안헷갈려\"."
human_verification:
  - test: "보드의 미해소 청소 목록에서 광고그룹 1개를 골라, 거기 적힌 원문·번호만 들고 네이버 검색광고 화면에서 그 그룹을 실제로 찾을 수 있는지 확인한다. 두 배너('내가 지울 것' vs '시스템이 못 읽은 것')가 헷갈리는지도 함께 확인한다."
    expected: "미해소 사유 문구만으로 네이버 광고에서 해당 그룹을 특정할 수 있고, 두 배너의 소속이 구분된다 — 되든 안 되든 한 줄씩 진술이 남는다"
    why_human: "JOIN-02 의 쓸모는 화면 렌더링이 아니라 '용팀장이 실제로 그 사유를 보고 광고 화면에서 작업을 할 수 있는가'라는 사람 판단이다. 플랜(03-07 Task 3 ④⑤)이 명시적으로 요구했고 CDP/pytest로 대체 불가능하다. 이번 CR-01~03 수정은 이 항목을 건드리지 않았다 — 2026-09-21 현재도 '보드 확인했어, 승인' 한 줄만 있고 ④⑤ 항목별 진술은 없다(03-VALIDATION.md §미해결 2번, REQUIREMENTS.md JOIN-02 각주 `Complete ⚠️`)."
deferred:
  - truth: "그룹 목록 조회 단계의 HTTP 429 가 최종 요약에 반영되어 '완주'가 실제 완주를 의미한다"
    addressed_in: "이월 항목 (신규 Phase 아님) — 용팀장이 2026-09-21 'Phase 3 범위 밖, 그냥 두고 기록만'으로 명시적으로 보류"
    evidence: ".planning/todos/pending/429-group-stage-silent-completion.md — CR-01/02/03과는 다른 결함(요약이 실패를 숨기는 것 vs 실패를 성공으로 오판정하는 것)"
---

# Phase 3: 작업 대상 확정 — 엔티티 해소 + 상세 상태 판정 Verification Report (Re-verification)

**Phase Goal:** 광고 판정 행을 불사자 상품에 실제로 잇고 상세 상태를 3단계로 판정해, "유입은 있는데 상세가 중국어 원본인 상품" 목록을 화면에서 **정확히** 뽑아낸다.
**Verified:** 2026-09-21T06:22:05Z
**Status:** passed (2026-09-21 사람 검증 2/2 PASS 로 마감 — 아래 §Human Verification 참조)
**Re-verification:** Yes — after CR-01/CR-02/CR-03 critical code-review gap closure

## 결론 먼저

직전 검증(`gaps_found`, 6/10)이 잡은 3개 Critical 결함 — 마켓그룹 조회 오류의 "0개" 흡수(CR-01),
팬아웃 조회 실패의 "사본 0건·기작업 아님" 흡수(CR-02), workdata 오류의 "성공 관측"(unresolved=0)
기록(CR-03) — 을 이 검증 세션에서 **코드를 직접 읽고, 회귀 테스트를 직접 돌려** 확인했다.
셋 다 SUMMARY 주장과 실제 코드가 일치한다. `ss_index_calls.py`의 공통 본체 `목록꺼내기`가
`그룹꺼내기`·`항목꺼내기`·`워크데이터꺼내기` 세 얇은 껍데기로 3개 호출부 전부(`bulsaja_scan.py`
2곳 + `ss_index_build.py` 1곳)에 실제로 적용됐고("모양 아니면 예외" 규약이 1곳에서 3곳으로
확장), `webapp/join.py`·`webapp/routes/board.py`·`webapp/static/board.js`가 2층·3층 방어를
정확히 구현하고 있다. 신규 회귀 테스트 15건은 리뷰어가 재현했던 정확한 값
(`광고청소행 9·청소그룹 8`, `기본선택 대상 1`, `unresolved=0`)을 0/제외로 고정하는 실질적인
단언이었다 — 통과만 하고 아무것도 안 무는 껍데기 테스트가 아니다.

전체 스위트는 355개 테스트 모두 통과(exit 0, 이 검증 세션에서 직접 재실행), 340→355는
SUMMARY의 "+15" 주장과 일치한다. `no_commit_guard.sh` exit 0, D-19(웹앱에 requests/eroomlib
import 0건) 재확인, 신규/수정 파일에 TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER 0건.

**남은 것은 코드 결함이 아니라 사람 검증 미수령 하나뿐이다** — JOIN-02의 ④(미해소 사유만
보고 네이버 광고에서 그룹을 찾을 수 있는가)·⑤(두 배너가 헷갈리는가) 항목별 진술. 이건
이번 CR 수정의 범위 밖이고 이미 정직하게 기록돼 있다. 코드 레벨에서는 전 10개 must-have
truth가 VERIFIED이므로, 판정은 `gaps_found`가 아니라 `human_needed`다.

## Goal Achievement

### Observable Truths (재검증)

| # | Truth | 직전 판정 | 이번 판정 | Evidence |
|---|-------|-----------|-----------|----------|
| 1 | (STATE-01) `detail_batch.py --help` exit 0 | ✓ VERIFIED | ✓ VERIFIED (회귀 없음) | `test_cli_shim.py` green |
| 2 | (STATE-02) 타입 안전 불리언 정규화 | ✓ VERIFIED | ✓ VERIFIED (회귀 없음) | `webapp/state.py` · `test_state.py` |
| 3 | (STATE-03) 3단계 판정 + 우선순위 + 키 부재 안전 | ✓ VERIFIED | ✓ VERIFIED (회귀 없음) | `test_state.py` green |
| 4 | (STATE-04) 외부경로 `aiImageGenerated` 미기록 | ✓ VERIFIED | ✓ VERIFIED (회귀 없음) | `webapp/state.py:31-38` |
| 5 | (STATE-05) 기작업 스킵 절대 조건 | ✗ FAILED (에러 경로) | ✓ VERIFIED | CR-02 GREEN `1ee701a` — `join.selectable()`이 `팬아웃미조회` 행을 기본 선택에서 제외. `test_팬아웃_미조회는_기본선택에서_빠진다` 직접 읽고 로직·재현값(`기본선택 대상: 1`→`{"19000000003"}`) 확인 |
| 6 | (JOIN-01) 해상률 숫자 노출 | ✓ VERIFIED (기댓값 이탈 문서화) | ✓ VERIFIED (동일, 이번 수정과 무관) | `test_join.py:159` |
| 7 | (JOIN-02) 미해소 사유 3종 분리 + 광고청소/시스템 버킷 분리 | ✗ FAILED | ✓ VERIFIED (코드 레벨) / ? 사람 검증 미수령 | CR-01 GREEN `ec2d5e7` — `bulsaja_scan.py`가 `그룹꺼내기`로 해석 후 못 읽거나 0개면 exit 2·산출물 미기록. `board.py::_load_join`이 빈 마켓그룹 문서도 `None`+사유로 내려 전 행을 `미조회`/시스템으로 떨어뜨림. `test_마켓그룹이_빈_산출물은_광고청소를_만들지_않는다` 직접 읽고 확인 — 재현값(`광고청소행 9·청소그룹 8`)이 0으로 고정됨을 단언 |
| 8 | (JOIN-03) 사본 N건 팬아웃 표시 | ✗ FAILED (에러 경로) | ✓ VERIFIED | CR-02 GREEN `1ee701a` — `배치조회`가 `(항목들, 실패코드)` 반환, 행 기본값 `사본:None`+`팬아웃미조회` 필드. `join.attach`가 `사본N`을 빈칸(None)으로 두고 화면(`board.js`)도 `⚙ ?`로 표시. `test_팬아웃_미조회는_사본0건을_단언하지_않는다` 확인 |
| 9 | (JOIN-04) 인덱스 히트 재검증 + 히트 원본 정직성 | ✗ FAILED (인덱스 신뢰성) | ✓ VERIFIED | CR-03 GREEN `268b3dc` — `워크데이터꺼내기`가 `data` 키 부재·타입불일치를 예외로 올림. `ss_index_build.py`가 이 예외를 `unresolved=1`(미조회)로 적음. `test_빌더는_workdata_오류를_미조회로_적는다`가 3겹(DB 기록·재개 대상 포함·완결=False)을 직접 단언 |
| 10 | (ENG-08) 계정 불일치 시 쓰기 잡 거부 | ✓ VERIFIED | ✓ VERIFIED (회귀 없음) | `test_jobs.py`, `test_paths.py` |

**Score:** 10/10 truths verified at the code level. Truth 7(JOIN-02)은 코드 레벨은 VERIFIED이나 플랜이 요구한 사람 판단 항목(④·⑤)이 아직 없어 별도의 `human_needed` 항목으로 분리해 기록한다.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `.claude/skills/bulsaja-detail-page/scripts/ss_index_calls.py` | 오류/빈값 구분 공통 규약 | ✓ VERIFIED | 공통 본체 `목록꺼내기(r, 키들, 맥락, 이름)`를 `그룹꺼내기`·`항목꺼내기`·`워크데이터꺼내기`가 호출(코드 직접 확인). "키 부재·타입 불일치=예외, 키 있고 비었으면 정상"이 세 함수 모두 일관 |
| `.claude/skills/bulsaja-detail-page/scripts/bulsaja_scan.py` | 그룹/팬아웃 조회 오류 방어 | ✓ VERIFIED | `그룹꺼내기`(309-346행 부근) → 못 읽거나 0개면 `return 2` + 산출물 미기록. `배치조회`(211-246행) → `(항목들, 실패코드)` 반환, 호출부가 행별 `사본`/`팬아웃미조회` 기록(440-506행) |
| `.claude/skills/bulsaja-detail-page/scripts/ss_index_build.py` | workdata 오류 방어 | ✓ VERIFIED | `워크데이터꺼내기` 사용, 예외 시 `ss, unresolved = None, 1`로 기록(276-303행) |
| `webapp/routes/board.py::_load_join` | 빈 마켓그룹도 None 취급 (2층 방어) | ✓ VERIFIED | `if not (문서.get("마켓그룹") or []): return None, None, 사유` (158-163행) |
| `webapp/join.py` | `사본N`/`selectable`에서 팬아웃미조회 반영 | ✓ VERIFIED | `_기본값`에 `팬아웃미조회:None` 추가, `attach()`가 `state.불리언정규화`로 정규화, `사본N`은 `사본 is list and not 팬아웃미조회`일 때만 기록, `selectable()`이 `팬아웃미조회` 행 제외 |
| `webapp/static/board.js` | 화면이 팬아웃미조회를 빈칸+기본선택제외+배너분리로 표시 | ✓ VERIFIED | `고를수있는()`이 `!r.기작업 && !r.팬아웃미조회`, `팬아웃미조회표기="⚙ ?"`, `기작업제외`/`팬아웃제외` 카운터 분리(415-456행) |
| `webapp/tests/test_index.py`, `test_join.py`, `test_board.py` | CR-01/02/03 회귀 15건 | ✓ VERIFIED (실질 단언 확인) | 각 테스트를 직접 읽음 — 리뷰어 재현값을 정확히 반영한 assert (예: `해상["광고청소"]["행"] == 0`, `행["사본N"] is None`, `적힌값 == {pid: 1}`). 스텁성 테스트 아님 |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `bulsaja_scan.py` (마켓그룹 조회) | `board.py::_load_join` | `join_<job>.json` | ✓ WIRED | 1층(exit 2·산출물 미기록) + 2층(`None` 취급) 이중 방어 확인. 코드 직접 읽음 |
| `bulsaja_scan.py` (팬아웃) | `webapp/join.py::attach` | `사본`/`팬아웃미조회` 필드 | ✓ WIRED | 행 스키마 필드 → `attach()` 소비 → `selectable()` 필터 전체 경로 추적 확인 |
| `ss_index_build.py` | `ss_index_resume.처리완료()` | `unresolved` 컬럼 | ✓ WIRED | `test_빌더는_workdata_오류를_미조회로_적는다`가 `unresolved=1` → `완료()`가 그 pid를 안 세는 것까지 한 테스트에서 직접 단언 |
| `webapp/join.py::selectable` | `webapp/static/board.js::고를수있는` | 같은 규약(기작업 + 팬아웃미조회 제외) | ✓ WIRED | 서버·클라이언트 양쪽에서 동일 2조건 필터 확인. `test_화면도_팬아웃_미조회를_기본선택에서_뺀다`가 소스 문자열 검사로 규약 일치 확인 |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| 전체 테스트 스위트 재실행 | `.venv-web/bin/python -m pytest webapp/tests -q` | exit 0, 355 tests collected (전부 통과) | ✓ PASS |
| CR-01/02/03 수정 코드 실재 확인 | `sed -n` 으로 각 라인 직접 열람 | 리뷰가 제시한 패치안과 실제 코드가 일치(그룹꺼내기 exit 2·배치조회 실패코드 반환·워크데이터꺼내기 예외) | ✓ PASS |
| `그룹꺼내기`·`항목꺼내기`·`워크데이터꺼내기` 3곳 적용 범위 | `grep -n "그룹꺼내기\|항목꺼내기\|워크데이터꺼내기"` | `bulsaja_scan.py` 2회 호출(그룹·항목·워크데이터), `ss_index_build.py` 2회 호출(항목·워크데이터) — 이전 검증의 "1/3만 적용" 결함 해소 확인 | ✓ PASS |
| `no_commit_guard.sh` | `bash webapp/tests/no_commit_guard.sh` | `OK (webapp/tests 에 --commit 리터럴 0건)`, exit 0 | ✓ PASS |
| D-19 (웹앱에 requests/eroomlib import) | `grep -RnE "^\s*(import requests|import eroomlib...)" webapp` | 0건 | ✓ PASS |
| 디버트 마커 스캔 | `grep -n -E "TBD\|FIXME\|XXX\|TODO\|HACK\|PLACEHOLDER"` on 수정 파일 전체 | 0건 (매치된 2건은 `\uXXXX` 이스케이프 설명 주석, 마커 아님) | ✓ PASS |
| 커밋 해시 검증 | `git show --stat ec2d5e7/1ee701a/268b3dc` | 3개 커밋 모두 존재, 커밋 메시지가 SUMMARY/REVIEW 주장과 일치 | ✓ PASS |

### Probe Execution

해당 없음 — 이 페이즈는 `scripts/*/tests/probe-*.sh` 컨벤션 프로브를 선언하지 않는다. 이번 재검증에서는
pytest 전체 스위트 재실행 + 커밋 실재 확인 + 소스 직독으로 대체했다(직전 검증과 동일한 방식).

### Requirements Coverage (재검증)

| Requirement | 직전 판정 | 이번 판정 | Evidence |
|---|---|---|---|
| ENG-08 | ✓ SATISFIED | ✓ SATISFIED (회귀 없음) | `test_jobs.py`, `test_paths.py` |
| JOIN-01 | ✓ SATISFIED | ✓ SATISFIED (회귀 없음) | `test_join.py:159,187` |
| JOIN-02 | ✗ BLOCKED (에러 경로) + ? NEEDS HUMAN | ✓ SATISFIED (코드) + ? NEEDS HUMAN (④⑤ 미수령, 이번 수정 범위 밖) | CR-01 GREEN 확인. `03-VALIDATION.md` §미해결 2번 불변 |
| JOIN-03 | ✗ BLOCKED (에러 경로) | ✓ SATISFIED | CR-02 GREEN 확인 |
| JOIN-04 | ✗ BLOCKED (인덱스 신뢰성) | ✓ SATISFIED | CR-03 GREEN 확인 |
| STATE-01~04 | ✓ SATISFIED | ✓ SATISFIED (회귀 없음) | 동일 |
| STATE-05 | ✗ BLOCKED (에러 경로) | ✓ SATISFIED | CR-02 GREEN 확인 |

**Orphaned requirements:** 없음 (직전 검증과 동일 — REQUIREMENTS.md의 10개 ID가 전부 플랜에 등장).

### Anti-Patterns Found (재검증)

| File | Line | Pattern | Severity | 이번 판정 |
|------|------|---------|----------|-----------|
| `bulsaja_scan.py` | 309-346(구 309-313) | MCP 오류 dict `.get(...) or []` 흡수 | 🛑 BLOCKER (직전) | ✓ 해소 — `그룹꺼내기` 규약으로 대체, exit 2 |
| `bulsaja_scan.py` | 211-246, 440-506(구 213-222, 400-422) | 코드조회/팬아웃 오류 조용한 0건 흡수 | 🛑 BLOCKER (직전) | ✓ 해소 — `(항목들, 실패코드)` 반환 + 행별 `팬아웃미조회` 기록 |
| `ss_index_build.py` | 276-303(구 283-296) | workdata 오류 `unresolved=0` 영구 기록 | 🛑 BLOCKER (직전) | ✓ 해소 — `워크데이터꺼내기` 예외 → `unresolved=1` |
| `webapp/join.py` | 66 | 번호 정규식 숫자 경계 없음 | ⚠️ WARNING (WR-01, 직전) | ⚠️ 미해결 — 이번 CR 수정 범위 밖, `_번호패턴` 여전히 `r"(\d{1,2})-(\d{1,2})"`. 실데이터 미발현 (변화 없음, 새 갭으로 세지 않음 — 직전 판정과 동일하게 WARNING만) |

TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER: 이번 검증에서 다시 스캔, 수정 파일 전체 0건.

### Human Verification Required

#### 1. JOIN-02 항목별 수동 검증 (④·⑤) — 이월 (이번 CR 수정과 무관)

**Test:** 보드의 미해소 청소 목록에서 광고그룹 1개를 골라, 사유 문구(광고그룹명 원문+번호)만 들고 네이버 검색광고 화면에서 그 그룹을 실제로 찾을 수 있는지 확인한다. 광고청소 배너와 시스템 배너가 헷갈리는지도 확인한다.
**Expected:** 사유만으로 그룹을 특정할 수 있고, 두 배너가 명확히 구분된다.
**Why human:** 렌더링/데이터 일치는 CDP로 이미 확인됐지만(V-BOARD-20/21), "실제로 그 사유를 보고 사람이 작업할 수 있는가"는 기계로 볼 수 없다. 이번 CR-01~03 수정은 이 항목을 건드리지 않았고, 2026-09-21 현재 "보드 확인했어, 승인" 한 줄만 있고 항목별 진술은 없다(`03-VALIDATION.md` §미해결 2번).

### Gaps Summary

직전 검증이 지목한 3개 Critical 결함(CR-01/02/03)은 이 검증에서 **코드를 직접 읽고, 회귀
테스트를 직접 돌려서** 확인한 결과 전부 닫혔다. 세 결함의 공통 뿌리 — "불사자 MCP의 툴 레벨
오류가 예외가 아니라 평범한 dict로 온다"는 사실을 각 호출부가 각자 `.get(...) or []`로
안전하지 않게 해석하던 문제 — 가 `ss_index_calls.목록꺼내기`라는 단일 공통 본체로 통합되고
3개 호출부 전부(마켓그룹·팬아웃·workdata)에 실제로 적용됐다. 이전 검증에서 "규약이 1곳에만
적용됐다"고 확인했던 바로 그 갭이, 이번엔 `그룹꺼내기`·`항목꺼내기`·`워크데이터꺼내기` 세
호출부 전부에서 `grep`으로 직접 재확인됐다.

신규 회귀 테스트 15건(`test_index.py` 6건, `test_join.py` 3건, `test_board.py` 2건 등)은
리뷰어가 재현했던 정확한 값(`광고청소행 9·청소그룹 8`, `기본선택 대상 1`, `unresolved=0`)이
안전한 값으로 고정됐음을 실질적으로 단언한다 — 통과만 하고 아무것도 안 무는 테스트가
아니었다. 전체 스위트 355건이 이 검증 세션에서 직접 재실행되어 exit 0을 확인했다.

**남은 것은 코드 결함이 아니라 사람 검증 미수령이다.** JOIN-02가 플랜에서 요구한 ④·⑤
항목별 진술(용팀장이 실제로 광고 화면에서 그룹을 찾을 수 있는가)이 아직 없다 — 이건
이번 CR 수정의 범위 밖이고, 직전 검증에서도 이미 정직하게 human_needed로 기록돼 있던
항목이다. 이 항목 하나 때문에 전체 판정은 `passed`가 아니라 `human_needed`다.

**WR-01(번호 정규식 숫자 경계 없음)은 여전히 미해결이지만 WARNING 등급이고 실데이터에서
미발현이므로 새 갭으로 세지 않는다** — 직전 검증과 동일한 판단이다.

**이월(범위 밖, 새 갭 아님):** 그룹 목록 조회 429가 요약에 안 남는 문제는 용팀장이
2026-09-21 명시적으로 Phase 3 범위 밖으로 넘겼다.

---

_Verified: 2026-09-21T06:22:05Z_
_Verifier: Claude (gsd-verifier, re-verification)_


---

## Human Verification — 마감 (2026-09-21)

`human_needed` 를 만든 단 하나의 항목(JOIN-02 ④⑤)이 **둘 다 PASS** 로 닫혔다. 상세는
`03-HUMAN-UAT.md`(status: complete · passed 2/2).

### ④ 사유 문구만으로 네이버에서 그룹을 찾을 수 있는가 — PASS

용팀장이 19그룹 중 **최난도 케이스**(`소형이동식오피스` · 번호 `—` · 사유 `추출실패` · 703행,
전체 미해소 883행의 79.6%)를 골라, 보드가 준 광고그룹명 원문만 들고 네이버 검색광고에서
그 그룹을 찾아 **`25-2 소형이동식오피스` 로 이름을 고쳤다.** 캠페인명 컬럼이 없는 것도
장애가 되지 않았다. `판매상품_17-3_오운웨이컴퍼니` 도 같은 방식으로 수정.

수정이 실제로 해소로 이어지는지 메인 세션이 코드로 실측:

| 확인 | 결과 |
|---|---|
| `market_number("25-2 소형이동식오피스")` | `25-2` — `_번호패턴` 이 `search` 라 **접두+공백 형태도 통과**(기존 `판매상품_7-1_회사명` 언더스코어형과 모양이 달라도 됨) |
| `25-2` 가 불사자 마켓그룹에 있나 | **있다** — `5번_용쌤25-2` (groupId `1001822`), 조인 산출물 86그룹 중 번호 있는 54개에 포함 |
| groupId `1001822` 인덱스 보유 | **없다** — 인덱스 보유 30그룹에 미포함 |

→ 재스캔 시 703행은 `추출실패`(🔴 사람 몫)에서 `인덱스 미보유`(🔵 기계 몫)로 이동한다.
   빨강 883행/19그룹 → 약 180행/18그룹.

**이 항목이 증명한 것:** JOIN-02 의 미해소 사유는 화면 장식이 아니라 **실제로 광고 화면에서
작업을 완료시키는 정보**다. 번호조차 없는 최악의 행에서도 사유 문구에 더 필요한 것이 없었다.

### ⑤ 두 배너가 헷갈리는가 — PASS

용팀장 진술 그대로: **"안헷갈려"**. 행동으로도 뒷받침된다 — 빨강 배너를 "내 일"로 읽고
실제로 네이버에 가서 광고그룹 2건을 고쳤다. 구조 검증(uat-verifier 실측)도 PASS:
색·클래스·좌표 분리, 숫자 귀속 정확(883↔빨강 / 51↔파랑), 해소 필터 🛠/⚙ **혼입 0건**,
금지 표현 `미스` 0건.
