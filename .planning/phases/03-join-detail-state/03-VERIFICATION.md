---
phase: 03-join-detail-state
verified: 2026-09-21T05:49:33Z
status: gaps_found
score: 6/10 must-have truths verified (3 requirement-level truths FAILED at the error-path level, 1 human verification item still open)
overrides_applied: 0
gaps:
  - truth: "미해소 사유가 추출실패 / 번호없음 / 미조회로 서로 다른 값이고, 광고 쪽 청소 대상과 시스템 문제가 다른 버킷에 담긴다 (JOIN-02 / Pitfall 3)"
    status: failed
    reason: >
      마켓그룹 목록 조회가 불사자 MCP 의 툴 레벨 오류(dict 로 반환, 예외 아님)를 받으면
      `bulsaja_scan.py:309-313` 가 그 dict 를 `.get("그룹") or .get("항목") or []` 로 읽어
      "마켓그룹 0개"로 흡수한다. 스캔은 exit 0 으로 계속되고, 웹앱은 그 산출물을 정상
      성공으로 읽는다(`webapp/routes/board.py::_load_join` 은 `join_doc is None` 만 막고
      `마켓그룹: []` 은 통과시킨다 — 주석에 이 함정을 정확히 적어 두고도 막지 않았다).
      결과: 그룹색인이 비어 **번호가 있는 모든 행이 "번호없음"(=광고청소)** 으로 떨어진다.
      코드 리뷰가 `result_traps.json` 으로 재현: 정상 광고그룹 8개가 "네이버 광고에서
      찾아 지워라" 로 화면에 뜬다. 이게 이 페이즈가 정의한 최대 오진(Pitfall 3)이고
      JOIN-02 가 막겠다고 약속한 바로 그 실패 모드가 에러 경로에서 실제로 열려 있다.
    artifacts:
      - path: ".claude/skills/bulsaja-detail-page/scripts/bulsaja_scan.py"
        issue: "309-313행 — 마켓그룹 응답 해석에 ss_index_calls.항목꺼내기 같은 '모양이 아니면 예외' 규약이 없다. 오류·빈 목록을 구분하지 않는다"
      - path: "webapp/routes/board.py"
        issue: "116-150행 _load_join 이 join_doc is None 만 막는다. 마켓그룹이 빈 리스트인 성공 산출물은 그대로 통과한다"
    missing:
      - "bulsaja_scan.py 에 그룹꺼내기() 같은 '모양 검증 후 예외' 함수를 추가하고, 마켓그룹이 0개면 exit 2로 산출물을 쓰지 않는다 (REVIEW CR-01 제안 패치)"
      - "board.py::_load_join 에 2층 방어 — 마켓그룹이 빈 리스트인 문서는 None 취급"
  - truth: "사본이 여러 개인 항목에 사본 N건이 보인다 (JOIN-03 / 성공기준 3) — 그리고 기작업(구매_가공완료 태그) 상품이 기본 선택에서 빠진다 (D-08 / STATE-05)"
    status: failed
    reason: >
      `bulsaja_scan.py::배치조회` 의 코드 조회(find_by_code)가 툴 레벨 오류 dict 를 받으면
      `미조회` 플래그가 안 서고(`미조회=False`, dict 이므로) `.get("항목") or []` 로 조용히
      0건 취급된다(경고 로그도 없음). 429 소진 시에도 경고는 찍히지만 행 스키마에
      "팬아웃을 못 물어봤다"를 적을 칸이 없다. 두 경우 모두 행은 `사본=[]` ·
      `그룹태그=None` 으로 확정 저장되고, 웹앱은 그걸 "사본 0건" · "기작업 아님" 으로
      읽는다(`join.py:307-312`). 코드 리뷰 재현: 팬아웃만 실패한 행 1개가
      `기작업=False, 사본N=0` 으로 확정되어 **기본 선택 대상에 들어간다.**
      `구매_가공완료` 태그가 붙은 상품이 조회 실패 한 번으로 Phase 5 의 크레딧 재지불
      대상이 될 수 있다 — STATE-05 가 막으려던 "동적 조건이 스킵을 무력화" 와 같은
      결과가 "조회 실패가 스킵을 무력화" 라는 새 경로로 발생한다.
    artifacts:
      - path: ".claude/skills/bulsaja-detail-page/scripts/bulsaja_scan.py"
        issue: "213-222행 배치조회() 및 400-422행 팬아웃 결과 저장부 — 오류 dict를 빈 결과로 흡수, 실패를 행에 기록하는 칸이 없다"
    missing:
      - "배치조회를 ss_index_calls.항목꺼내기 규약으로 올려 오류와 빈 결과를 구분한다"
      - "행 스키마에 팬아웃미조회 필드를 추가하고, join.attach가 사본 is None을 팬아웃 실패로 구분해 기본 선택에서 제외한다 (REVIEW CR-02 제안 패치)"
  - truth: "인덱스 히트를 재검증 없이 쓰지 않는다 — 그리고 첫 인덱스 구축이 설정된 범위에서 완주하고 제외 그룹만 미조회로 남는다 (JOIN-04 / D-18)"
    status: failed
    reason: >
      `ss_index_build.py:283-296` 의 workdata 조회가 툴 레벨 오류 dict 를 받으면
      `안전호출` 의 미조회 플래그는 안 서고(429만 미조회로 잡는다), `(r or {}).get("data") or {}`
      가 오류 dict 를 빈 dict 로 접어 **unresolved=0(성공 관측)으로 영구 기록**한다.
      파급: ① `ss_index_resume.처리완료()` 가 그 상품을 성공으로 보고 재개에서 영원히
      건너뛴다(같은 잡을 몇 번 다시 돌려도 재조회 안 됨) ② 그룹 `완결` 판정이 참이 되어
      화면이 "인덱스 다 훑었다"로 표기한다 ③ 그 상품은 Phase 5 대상에서 조용히 빠진다.
      JOIN-04 가 약속한 "재검증 로직 자체"는 코드로 검증되고 테스트도 green 이지만,
      그 로직이 참조하는 인덱스 원본이 에러 경로에서 조용히 오염될 수 있어 "히트를
      재검증 없이 안 쓴다"는 안전판의 전제(인덱스가 최소한 정직하게 미조회를 기록한다)가
      깨진다. 동일 문제가 `bulsaja_scan.py:363-372`에도 같은 패턴으로 존재한다(그쪽은
      결과적으로 안전한 미조회로 떨어지긴 하지만 같은 미검증 파싱이다).
    artifacts:
      - path: ".claude/skills/bulsaja-detail-page/scripts/ss_index_build.py"
        issue: "283-296행 — workdata 오류 응답이 unresolved=0(성공)으로 기록된다. 모양 검증이 없다"
    missing:
      - "워크데이터꺼내기() 같은 '모양이 아니면 예외' 헬퍼를 추가해 오류를 unresolved=1로 명시 기록한다 (REVIEW CR-03 제안 패치)"
human_verification:
  - test: "보드의 미해소 청소 목록에서 광고그룹 1개를 골라, 거기 적힌 원문·번호만 들고 네이버 검색광고 화면에서 그 그룹을 실제로 찾을 수 있는지 확인한다. 두 배너('내가 지울 것' vs '시스템이 못 읽은 것')가 헷갈리는지도 함께 확인한다."
    expected: "미해소 사유 문구만으로 네이버 광고에서 해당 그룹을 특정할 수 있고, 두 배너의 소속이 구분된다 — 되든 안 되든 한 줄씩 진술이 남는다"
    why_human: "JOIN-02 의 쓸모는 화면 렌더링이 아니라 '용팀장이 실제로 그 사유를 보고 광고 화면에서 작업을 할 수 있는가'라는 사람 판단이다. 플랜(03-07 Task 3 ④⑤)이 명시적으로 요구했고 CDP/pytest로 대체 불가능하다고 문서가 스스로 밝히고 있다. 2026-09-21 용팀장은 '보드 확인했어, 승인' 한 줄만 주었고 ④⑤ 항목별 진술은 아직 없다(03-VALIDATION.md §미해결 2번, REQUIREMENTS.md JOIN-02 각주에 동일하게 기록됨)."
deferred:
  - truth: "그룹 목록 조회 단계의 HTTP 429 가 최종 요약에 반영되어 '완주'가 실제 완주를 의미한다"
    addressed_in: "이월 항목 (신규 Phase 아님) — 용팀장이 2026-09-21 'Phase 3 범위 밖, 그냥 두고 기록만'으로 명시적으로 보류"
    evidence: ".planning/todos/pending/429-group-stage-silent-completion.md — 이미 알려진 이월 항목으로, 이번 검증에서 새 갭으로 세지 않았다. CR-01/02/03과는 다른 결함(요약이 실패를 숨기는 것 vs 실패를 성공으로 오판정하는 것)임을 REVIEW.md WR-02가 명시적으로 구분한다."
---

# Phase 3: 작업 대상 확정 — 엔티티 해소 + 상세 상태 판정 Verification Report

**Phase Goal:** 광고 판정 행을 불사자 상품에 실제로 잇고 상세 상태를 3단계로 판정해, "유입은 있는데 상세가 중국어 원본인 상품" 목록을 화면에서 **정확히** 뽑아낸다.
**Verified:** 2026-09-21
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### 결론 먼저

이 페이즈는 **정상 경로에서는** 목표를 달성한다 — 340개 테스트 green, 실서버 1회 완주(2시간 8분,
30,546행/30그룹, 미조회 0, 보드 상품 연결 0→51, 🔴31·🟡20·⚪0), 제외 그룹(`13-2`)이 정확히
`미조회`로 분류됨(T-3-38 PASS)까지 전부 실물로 확인된다.

그런데 방금 나온 코드 리뷰(`03-REVIEW.md`, Critical 3건)가 이 검증에서 직접 코드를 읽고
재확인한 바로는 — 불사자 MCP의 **오류 응답이 예외가 아니라 평범한 dict로 온다**는 사실을
CLI 3곳 중 1곳에서만 방어하고 있다. 나머지 2~3개 호출부는 오류를 "빈 결과"로 흡수해
① 정상 광고그룹을 "지워라"로 오판정하거나(CR-01, JOIN-02 핵심 안전장치 무력화)
② 사본/기작업 태그를 조용히 지워 크레딧 재지불 경로를 열거나(CR-02, STATE-05·JOIN-03 무력화)
③ 조회 실패를 "성공"으로 영구 기록해 그 상품이 인덱스에서 영원히 빠지게 한다(CR-03, JOIN-04
신뢰성 훼손). 세 경로 모두 실측 재현(`result_traps.json`, 코드 흐름 추적)으로 확인됐고,
이 검증 세션에서 grep으로 재확인해도 `항목꺼내기` 규약이 3개 호출부 중 1개(`ss_index_build.py:203`)
에만 적용돼 있다.

**첫 실탄 1회가 성공한 것은 그 회차에 MCP 오류 응답이 안 났기 때문이지, 오류가 나도
안전하기 때문이 아니다.** "정확히 뽑아낸다"는 목표는 정상 경로에서만 성립하고, 이 페이즈가
스스로 최대 오진으로 정의한 Pitfall 3의 에러 경로 변종이 코드에 그대로 열려 있다.
이건 잠재적 결함이 아니라 **직접 읽은 코드에 실재하는, 재현된 결함**이다 — FAILED로 판정한다.

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | (STATE-01) `detail_batch.py --help` 가 exit 0 | ✓ VERIFIED | `test_cli_shim.py::test_상세배치가_이_맥북에서_뜬다` green. VALIDATION 표 실측 |
| 2 | (STATE-02) `imageTranslated` 타입 안전 정규화 (`'0'`/`'1'`/`False`/`1`/`None`) | ✓ VERIFIED | `webapp/state.py`, `test_state.py:32,51` green |
| 3 | (STATE-03) 3단계 판정 + AI가공 우선순위 + 키 부재 안전 | ✓ VERIFIED | `test_state.py:65,80,96` green. 실서버 상태 분포 🔴31·🟡20·⚪0 (CDP V-BOARD-12 교차 확인) |
| 4 | (STATE-04) 외부 반영 경로는 `aiImageGenerated` 를 안 찍는다 — 결론이 소스·실측에 남는다 | ✓ VERIFIED | `webapp/state.py:31-38` docstring + 실서버 해소 51행 중 ⚪ 0건, `uploadDetailContents` 키 `{imageTranslated, renderContent}` 뿐 |
| 5 | (STATE-05) 기작업 상품이 기본 선택에서 빠지되 목록에 남는다 (절대 조건) | ✗ FAILED (에러 경로) | `test_join.py:460,493` 은 green 이지만, `bulsaja_scan.py` 의 팬아웃 조회 실패가 `그룹태그=None`을 만들어 **동일 상품이 조회 실패 한 번으로 기작업 스킵에서 빠질 수 있다** (CR-02, 코드 직접 확인) |
| 6 | (JOIN-01) 해상률 = 해소/전체, 숫자로 노출 | ✓ VERIFIED (기댓값 이탈은 문서화됨) | `test_join.py:159` green. 실데이터 회귀 기댓값이 179가 아니라 92 — 픽스처가 그룹 정리 전 스냅샷이라 구조적으로 재현 불가함이 VALIDATION §①에 명시. 이번 검증에서는 새 갭으로 세지 않음(테스트 자체는 내적 일관성 유지, 회귀 안전판으로 기능) |
| 7 | (JOIN-02) 미해소 사유 3종이 서로 다른 값이고 광고청소/시스템 버킷이 분리된다 | ✗ FAILED | 정상 경로 pytest/CDP는 green(19그룹 883행 원본 일치)이지만, 마켓그룹 조회 오류가 흡수되면 **전 행이 번호없음(광고청소)으로 확정**된다(CR-01, `bulsaja_scan.py:309-313` + `board.py:_load_join` 코드 직접 확인·재현됨) |
| 8 | (JOIN-03) 사본 N건 팬아웃 표시 | ✗ FAILED (에러 경로) | 정상 경로는 green(`test_join.py:442`)이지만, 팬아웃 조회 실패가 "사본 0건"으로 조용히 확정된다(CR-02, `bulsaja_scan.py:213-222` 코드 직접 확인) |
| 9 | (JOIN-04) 인덱스 히트가 재검증 없이 쓰이지 않는다, 재검증 불일치는 미해소로 떨어진다 | ✗ FAILED (인덱스 신뢰성 경로) | 재검증 로직 자체는 `test_join.py:372,385` green이지만, workdata 오류가 `unresolved=0`(성공)으로 영구 기록돼(CR-03) 재검증이 대상으로 삼는 인덱스 원본이 조용히 오염될 수 있다. `ss_index_build.py:283-296` 코드 직접 확인 |
| 10 | (ENG-08) 계정 불일치 시 쓰기 잡 생성 거부, 기대 계정 리터럴 미노출 | ✓ VERIFIED | `test_jobs.py:865`, `test_paths.py:277,313,326` green. 리뷰도 이 경계는 구멍 없음으로 확인 |

**Score:** 6/10 truths fully verified. 4개는 정상 경로는 green 이나 에러(MCP 오류 응답) 경로에서 코드로 직접 확인·재현된 결함이 있어 FAILED로 판정.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `webapp/state.py` | 순수 함수 3단계 판정 | ✓ VERIFIED | 존재·테스트·실측 일치 |
| `webapp/join.py` | 번호추출·해상률·미해소·청소목록 | ✓ VERIFIED (구조), ⚠️ 상류 데이터 오염 가능 | 함수 자체는 정확하다. 입력이 되는 CLI 산출물이 CR-01/02로 오염될 수 있음 |
| `webapp/bulsaja_index.py` | lookup·재검증·profile | ✓ VERIFIED | 읽기 전용, 네트워크 0, 테스트 green |
| `.claude/skills/bulsaja-detail-page/scripts/bulsaja_scan.py` | 계정 확인 + 조인 스캔 산출물 | ⚠️ STUB한 방어(오류 해석 미검증) | CR-01, CR-02 — 존재·동작하지만 오류 dict를 빈 결과로 흡수하는 미검증 파싱이 2곳 |
| `.claude/skills/bulsaja-detail-page/scripts/ss_index_build.py` | 인덱스 구축 + 체크포인트 | ⚠️ 부분 방어 | 페이지 조회(203행)는 `항목꺼내기`로 방어됨(VERIFIED). workdata 조회(283-296행)는 미방어(CR-03) |
| `.claude/skills/bulsaja-detail-page/scripts/ss_index_calls.py` | 항목꺼내기 — 오류/빈값 구분 규약 | ✓ VERIFIED (존재) / ✗ 미채택 (적용 범위) | 함수는 올바르게 구현됐으나 3개 호출부 중 1개에서만 실제로 쓰인다 (grep 직접 확인) |
| `webapp/routes/jobs.py`, `webapp/routes/board.py`, `webapp/templates/board.html` | 버튼·배너·청소목록 화면 | ✓ VERIFIED (렌더링) | CDP 38 PASS / 0 FAIL. `_load_join`의 `None` 방어는 있으나 `마켓그룹: []` 방어는 없음(CR-01의 2층 방어 부재) |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `bulsaja_scan.py` (마켓그룹 조회) | `board.py::_load_join` | `join_<job>.json` | ⚠️ PARTIAL | 링크는 배선돼 있으나 중간 값(빈 마켓그룹 리스트)에 대한 검증이 한쪽(`_load_join`)에만 있고 그마저 `None`만 걸러 `[]`는 통과 |
| `webapp/join.py` | `webapp/state.py` | `attach()` 내 `상세상태()`·`기작업여부()` 호출 | ✓ WIRED | 코드 직접 확인, 판정 진실 단일화 |
| `ss_index_build.py` | `webapp.db ss_index` | `INSERT OR REPLACE` 건마다 커밋 | ⚠️ PARTIAL | 배선은 정확하나, 기록되는 값(`unresolved`) 자체가 workdata 오류 경로에서 잘못 계산될 수 있음(CR-03) |
| `webapp/routes/jobs.py create_job` | `webapp/bulsaja_index.py profile_ok` | ENG-08 사전 점검 | ✓ WIRED | 코드·테스트 확인, 리뷰도 구멍 없음으로 확인 |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| 전체 테스트 스위트 | `.venv-web/bin/pytest webapp/tests -q` | 340 passed, 0 failed (11.4초) | ✓ PASS |
| CR-01/02/03 코드 존재 확인 | `sed -n` 으로 해당 라인 직접 열람 | 리뷰가 지목한 정확한 패턴(`.get(...) or []`, `(r or {}).get("data") or {}`) 실재 확인 | ✗ FAIL (결함 실재) |
| `항목꺼내기` 적용 범위 | `grep -rn "항목꺼내기" .claude/skills/bulsaja-detail-page/scripts/*.py` | 정의 1곳(`ss_index_calls.py`) + 호출 1곳(`ss_index_build.py:203`) 뿐 — `bulsaja_scan.py`(그룹/팬아웃), `ss_index_build.py`(workdata)는 미적용 | ✗ FAIL (방어 범위 부족 확인) |
| `_번호패턴` 경계 확인 (WR-01) | `sed -n '60,70p' webapp/join.py` | `re.compile(r"(\d{1,2})-(\d{1,2})")` — 숫자 경계 없음, 픽스처 생성기(`anonymize_join.py:44`)와 다른 규칙 | ⚠️ WARNING (실데이터에서 미발현, 잠재 리스크) |

### Probe Execution

해당 없음 — 이 페이즈는 `scripts/*/tests/probe-*.sh` 컨벤션 프로브를 선언하지 않았고, PLAN/SUMMARY/VALIDATION 어디에도 프로브 언급이 없다. `03-VALIDATION.md`의 "Manual-Only Verifications" + 실서버 완주가 그 역할을 대신하며, 이 검증에서 별도로 실행했다(pytest 전체 스위트).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| ENG-08 | 03-03, 03-04, 03-05 | 기대 계정 확인 후 거부 | ✓ SATISFIED | `test_jobs.py:865`, 리뷰 확인 구멍 없음 |
| JOIN-01 | 03-02, 03-05, 03-07 | 해상률 숫자 노출 | ✓ SATISFIED (기댓값 이탈은 기록됨, 갭 아님) | `test_join.py:159,187` |
| JOIN-02 | 03-02, 03-06 | 미해소 항목 숨기지 않고 사유 구분 | ✗ BLOCKED (에러 경로) + ? NEEDS HUMAN (④⑤ 미수령) | CR-01 재현, `03-VALIDATION.md` §미해결 2번, `REQUIREMENTS.md` JOIN-02 각주 `Complete ⚠️` |
| JOIN-03 | 03-04, 03-06 | 팬아웃 N건 표시 | ✗ BLOCKED (에러 경로) | CR-02 재현 |
| JOIN-04 | 03-03, 03-04, 03-05, 03-07 | 채널상품ID 영구키 미사용, 재검증 | ✗ BLOCKED (인덱스 신뢰성) | CR-03 재현. 재개 로직 자체는 실서버 증명됨(전수 실증) |
| STATE-01 | 03-01 | 맥북에서 CLI 실행 가능 | ✓ SATISFIED | `test_cli_shim.py` |
| STATE-02 | 03-02 | 타입 안전 불리언 정규화 | ✓ SATISFIED | `test_state.py` |
| STATE-03 | 03-02, 03-06 | 3단계 상태 판정 | ✓ SATISFIED | `test_state.py` + 실측 |
| STATE-04 | 03-02, 03-07 | 외부경로 aiImageGenerated 미기록 실측 | ✓ SATISFIED | 실측 51행 중 ⚪ 0건 |
| STATE-05 | 03-02, 03-06 | 기작업 스킵 절대조건 | ✗ BLOCKED (에러 경로) | CR-02 재현 — 조회 실패가 스킵을 무력화할 수 있음 |

**Orphaned requirements:** 없음 — REQUIREMENTS.md의 10개 ID(ENG-08, JOIN-01~04, STATE-01~05)가 전부 어느 플랜의 `requirements`에 등장함 (VALIDATION.md Sign-Off에서도 grep으로 확인됨, 이 검증에서 재확인 완료).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `bulsaja_scan.py` | 309-313 | MCP 오류 dict를 `.get(...) or []`로 흡수, 모양 검증 없음 | 🛑 BLOCKER (CR-01) | 정상 광고그룹을 삭제 대상으로 오판정 |
| `bulsaja_scan.py` | 213-222, 400-422 | 코드 조회/팬아웃 오류를 조용히 0건으로 흡수, 실패 표시 칸 없음 | 🛑 BLOCKER (CR-02) | 기작업 스킵 무력화 → 크레딧 재지불 |
| `ss_index_build.py` | 283-296 | workdata 오류가 `unresolved=0`(성공)으로 영구 기록 | 🛑 BLOCKER (CR-03) | 인덱스가 조용히 상품을 영구 누락 |
| `webapp/join.py` | 66 | 번호 정규식에 숫자 경계 없음, 픽스처 생성기와 규칙 불일치 | ⚠️ WARNING (WR-01) | 실데이터 미발현이나 광고그룹명이 바뀌면 엉뚱한 그룹에 붙을 위험 |
| 기타 6건(WR-02~09) | — | 429 재시도 누락(목록 단계), 배너 분자 불일치, 폴링 상태 누락 등 | ⚠️ WARNING/ℹ️ INFO | `03-REVIEW.md` 원문 참조. 이번 phase goal 판정에는 직접 영향 낮음으로 판단(개별 UX/견고성 이슈) |

TBD/FIXME/XXX 계열 미해결 마커: 이번 페이즈 수정 파일에서 grep 0건 (기존 주석은 모두 "known deferred"로 todos/pending에 정식 연결됨).

### Human Verification Required

#### 1. JOIN-02 항목별 수동 검증 (④·⑤)

**Test:** 보드의 미해소 청소 목록에서 광고그룹 1개를 골라, 사유 문구(광고그룹명 원문+번호)만 들고 네이버 검색광고 화면에서 그 그룹을 실제로 찾을 수 있는지 확인한다. 광고청소 배너와 시스템 배너가 헷갈리는지도 확인한다.
**Expected:** 사유만으로 그룹을 특정할 수 있고, 두 배너가 명확히 구분된다.
**Why human:** 렌더링/데이터 일치는 CDP로 이미 확인됐지만(V-BOARD-20/21), "실제로 그 사유를 보고 사람이 작업할 수 있는가"는 기계로 볼 수 없다. 플랜이 명시적으로 요구했고 2026-09-21 현재 "보드 확인했어, 승인" 한 줄만 있고 항목별 진술은 없다(`03-VALIDATION.md` §미해결 2번).

### Gaps Summary

이 페이즈의 **정상 경로**(MCP가 정상 응답하는 경우)는 목표를 달성한다 — 판정 로직 3종은
순수 함수로 전수 테스트됐고, 실서버 완주 1회로 실물 증명됐다. 그러나 **이 페이즈가 스스로
정의한 최대 위험(Pitfall 3: 시스템 오류가 사람의 삭제 작업으로 둔갑)이, 그 위험을 막으려고
만든 방어 규약(`ss_index_calls.항목꺼내기`)의 적용 범위가 3개 호출부 중 1개뿐이라서 여전히
열려 있다.** 코드 리뷰가 제시한 재현(`result_traps.json`)과 이 검증에서 직접 읽은 코드가
일치한다 — CR-01(광고청소 오탐), CR-02(기작업 스킵 무력화 → 크레딧 재지불 위험), CR-03(인덱스
영구 누락)은 전부 가상의 우려가 아니라 지금 저장소에 실재하는 코드 경로다.

이 결함들은 "화면에서 정확히 뽑아낸다"는 목표 문장의 핵심어("정확히")를 정상 경로에서만
지키고 에러 경로에서는 못 지킨다. 특히 CR-01·CR-02는 **되돌릴 수 없는 피해**(멀쩡한 광고
삭제, 크레딧 재지불)로 이어지는 경로라 페이즈가 스스로 세운 안전 기준(Pitfall 3, D-08,
STATE-05 "절대 조건")에 미달한다. 첫 실탄 1회가 우연히 이 경로를 밟지 않았을 뿐이다.

부가적으로 JOIN-02의 사람 검증(④⑤)이 아직 항목별로 닫히지 않았다 — 이건 이미
VALIDATION.md와 REQUIREMENTS.md에 `Complete ⚠️`로 정직하게 기록돼 있으므로 새 발견은
아니지만, 위 코드 결함과 같은 뿌리(JOIN-02 신뢰성)를 가리키므로 함께 닫는 것을 권장한다.

**이월(새 갭 아님):** 그룹 목록 조회 429가 요약에 안 남는 문제는 용팀장이 명시적으로
Phase 3 범위 밖으로 넘겼다(`todos/pending/429-group-stage-silent-completion.md`). 그대로 이월.

**권장:** CR-01·CR-02·CR-03은 `03-REVIEW.md`에 구체적인 패치안까지 제시돼 있다(그룹꺼내기,
팬아웃미조회 필드, 워크데이터꺼내기 헬퍼). Phase 4 진입 전 짧은 정정 플랜으로 닫는 것을
권장한다 — Phase 5(Core Value: 상세페이지 크레딧 작업)가 이 페이즈의 산출물을 그대로
신뢰하고 쓰기 때문에, 여기서 안 닫으면 Phase 5에서 실제 크레딧 손실로 나타난다.

---

_Verified: 2026-09-21T05:49:33Z_
_Verifier: Claude (gsd-verifier)_
