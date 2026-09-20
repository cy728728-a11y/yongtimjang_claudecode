---
phase: 03-join-detail-state
plan: 02
subsystem: join-state
tags: [pure-functions, join, detail-state, resolution, fan-out, prompt-injection, tdd]

# Dependency graph
requires:
  - phase: 01-board-bid-raise
    provides: "webapp/board.py 의 fold_products 행 모양 · `.get()` 만 쓰는 규율 · '0 이 아니라 None' 규율 · test_board.py 의 _행 헬퍼/리터럴 가드 관용구"
  - phase: 03-join-detail-state
    plan: 01
    provides: "픽스처 4종(result_traps · bulsaja_groups_traps · join_traps · result_join_real) + conftest 픽스처 · settings.DEFAULTS 의 done_tags/index_excluded_groups · test_board.py 런타임_파일들 선등록"
provides:
  - "webapp/state.py — 불리언정규화 · 상세상태(⚪🟡🔴) · 기작업여부. 순수 함수, 네트워크 0"
  - "webapp/join.py — market_number · group_index · ad_groups_by_product · strip_display_rules · 재검증판정 · attach · resolution · cleanup_groups · index_targets · selectable"
  - "attach() 가 행에 얹는 키 14종 (adGroups · 번호 · 번호해소 · 상품조회 · 해소 · 사유코드 · 사유 · 버킷 · productId · 상세상태 · 기작업 · 기작업태그 · 사본N · 잠금혼재)"
  - "미해소 사유코드 5종 + 버킷 2종 규약 — 03-05 라우트 ctx · 03-06 보드 열이 이 이름으로 쓴다"
  - "검증 31종 (state 13 · join 18). 전량 회귀 205 → 236"
affects: [03-04-index-cli, 03-05-ss-index, 03-06-board-ui, phase-05-detail-page]

# Tech tracking
tech-stack:
  added: []   # 새 외부 패키지 0건
  patterns:
    - "판정 진실은 한 곳 — join.attach 가 state.상세상태/기작업여부를 호출한다. 판정 코드를 복제하지 않는다"
    - "미해소는 사유코드 5종 + 버킷 2종으로 갈라 낸다. 합친 숫자를 내보내는 키를 만들지 않는다"
    - "순서가 의미인 판정에는 '뒤집히면 무슨 일이 나는지'를 단언 옆 주석으로 남긴다"
    - "프롬프트 인젝션 필드는 입구에서 재귀 제거하되 원본을 mutate 하지 않는다"
    - "가드의 문자열 검사는 키 기준으로 — 값(설명문)까지 훑으면 문서를 지우라는 뜻이 된다"

key-files:
  created:
    - webapp/state.py
    - webapp/join.py
    - webapp/tests/test_state.py
    - webapp/tests/test_join.py
  modified: []   # test_board.py 는 03-01 이 이미 선등록해 둬서 건드릴 게 없었다

key-decisions:
  - "join_doc=None 검사를 번호 추출보다 **앞에** 뒀다 — 스캔 전 상태가 광고 청소 목록으로 둔갑하지 않게"
  - "실회차 픽스처의 추출실패 기댓값을 0 이 아니라 1 로 잡았다 (정리 전 스냅샷이 정본)"
  - "state.py docstring 에서 금지 단어(bool( · eroomlib · requests)를 우회 표현으로 바꿨다 — 수용 기준의 grep 이 주석까지 훑는다"
  - "불리언 분기 순서는 순수 동작으로 구분 불가라, `is True`/`type is bool` 로 '입력이 그대로 새는' 실구현을 잡는다"
  - "재검증판정을 join.py 에 뒀다 — 판정은 조인 의미론이고 인덱스 모듈은 값만 꺼낸다"

requirements-completed: [STATE-02, STATE-03, STATE-04, STATE-05, JOIN-01, JOIN-02, JOIN-03, JOIN-04]

# Metrics
duration: 14min
completed: 2026-09-21
---

# Phase 3 Plan 02: 조인 · 상세 상태 판정 Summary

**이 페이즈의 새 판정 로직 전부가 순수 함수 두 모듈로 섰다 — 상세 상태 3단계(⚪🟡🔴)와 미해소 사유 5종/버킷 2종. 둘 다 네트워크·크레딧·파일 접근 0 이고, 판정 순서 역전과 사유 뭉개기를 기계가 막는다.**

## Performance

- **Duration:** 약 14분 (08:36 ~ 08:50)
- **Tasks:** 2 / 2
- **Files created:** 4 (런타임 2 · 테스트 2, 1,257행)
- **Tests:** 31종 신규 (state 13 · join 18). 전량 회귀 **205 → 236 passed**

## Accomplishments

- **판정 순서 역전을 기계가 막는다.** `aiImageGenerated` 를 `imageTranslated` 보다 먼저 본다. 뒤집히면 ⚪가 🟡로 내려앉고 Phase 5 가 이미 가공된 상품에 크레딧을 다시 태운다 — `test_AI생성이_번역보다_우선` 이 그 케이스를 고정한다.
- **`bool('0')` 함정이 소스에서 물리적으로 불가능하다.** `grep -v '^#' webapp/state.py | grep -c 'bool('` 가 **0** 이다. 주석 문구까지 우회 표현으로 바꿔 수용 기준을 실제로 만족시켰다 — 기존 `snapshot.py:184-189` 가 이 실수를 하고 있는 실물이다.
- **이 페이즈 최대 오진(Pitfall 3)이 두 겹으로 막혔다.** ① 사유코드 5종이 서로 다른 값이고 버킷 2종으로 갈린다 ② `resolution()` 에 두 버킷을 합친 숫자를 내보내는 키가 **아예 없다**(`test_해상률` 이 `미해소`·`해상률`·`비율` 같은 키의 부재를 단언한다). 화면이 실수로 집어 쓸 값이 없다.
- **스캔 전이 광고 오류로 둔갑하지 않는다.** `join_doc=None` 이면 전 행이 `미조회`/`시스템` 이고 `광고청소` 버킷이 0 이다. `cleanup_groups()` 도 빈 리스트다.
- **인덱스 히트를 재검증 없이 접는 경로가 없다.** `재검증판정` 은 관측값이 비면 `히트` 를 절대 안 낸다. 429/타임아웃(`미조회`)을 제일 먼저 보므로 **레이트리밋을 성공으로 접지 않는다.**
- **같은 번호 중복제거가 비용을 지킨다.** `index_targets` 가 번호 기준으로 접어, 같은 번호를 쓰는 광고그룹 2개가 groupId 1개가 된다. 트랩 픽스처에서 7행 → 4그룹.
- **프롬프트 인젝션 필드가 반환값 전문에서 0건.** `표시규칙` 을 최상위·행 안쪽 양쪽에서 재귀 제거하고, 원본은 mutate 하지 않는다. 제거 전 원본에 키가 2개(`$.표시규칙`, `$.행[2].표시규칙`) 남아 있음을 직접 확인한 뒤 0건이 되는 것을 봤다.
- **기작업 상품이 숨지 않고 기본 선택에서만 빠진다 (D-08).** `구매_가공완료` 행과 AI 가공 완료 행 둘 다 `attach()` 결과에 `기작업=True` 로 남아 있고 `selectable()` 에만 없다.
- **리터럴 가드가 새 파일을 실제로 훑기 시작했다.** 03-01 이 선등록해 둔 `런타임_파일들` 의 `join.py`·`state.py` 가 이제 `f.is_file() → True` 다. 계정 alias 0건.

## Task Commits

1. **Task 1 RED: 상세 상태 판정 실패 테스트** — `3433d95` (test)
2. **Task 1 GREEN: `webapp/state.py`** — `270cb3a` (feat)
3. **Task 2 RED: 조인 실패 테스트** — `1c9e65f` (test)
4. **Task 2 GREEN: `webapp/join.py`** — `aea4186` (feat)

## Files Created

- `webapp/state.py` (122행) — `AI가공완료`/`단순번역만`/`중국어원본` 상수 + `불리언정규화` · `상세상태` · `기작업여부`. 모듈 docstring 에 "절대 하지 않는 것" 6항목과 **STATE-04 결론**(양성대조 8 전부 True / 음성대조 26 전부 키 부재, 그래서 외부 경로 기작업의 유일한 신호는 `그룹` 태그이고 보완 인덱스를 신설하지 않는다)을 기록했다.
- `webapp/join.py` (420행) — 사유코드 5종·버킷 2종 상수 + `market_number` · `group_index` · `ad_groups_by_product` · `strip_display_rules` · `재검증판정` · `attach` · `resolution` · `cleanup_groups` · `index_targets` · `selectable`.
- `webapp/tests/test_state.py` (208행) — 13종.
- `webapp/tests/test_join.py` (507행) — 18종.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `test_번호추출_전수` 의 실회차 기댓값을 "추출실패 0" 에서 "정확히 1" 로 고쳤다**
- **Found during:** Task 2 (테스트 작성)
- **Issue:** 플랜의 behavior 는 *"`result_join_real.json` 의 **모든** 광고그룹명에서 번호가 추출된다(추출실패 0)"* 라고 적었다. 그런데 그 픽스처는 **용팀장이 광고그룹을 정리하기 전** 회차이고, 번호 없는 그룹이 정확히 1개 남아 있다(실측: 고유 46개 중 1개). `03-01-SUMMARY.md` 의 "Issues Encountered" 가 이미 이 사실을 경고했다.
- **Fix:** `len(실패) == 1` 로 잡고, **그 1개에 하이픈이 정말 없다**(정규식이 게을러서 놓친 게 아니다)는 것과 **나머지 45개는 전부 이름 안에 실제로 있는 번호를 뽑는다**(지어낸 값이 아니다)를 같이 단언했다. "추출실패 0" 을 억지로 맞추려면 픽스처를 고치거나 정규식을 느슨하게 해야 하는데 둘 다 틀린 길이다.
- **Files modified:** `webapp/tests/test_join.py`
- **Commit:** `1c9e65f`

**2. [Rule 3 - Blocking] `join_doc=None` 검사를 번호 추출보다 앞으로 옮겼다**
- **Found during:** Task 2
- **Issue:** 플랜 action 의 판정 순서는 ①번호추출(`추출실패`) → ②`join_doc` None 이면 `미조회` 였다. 그 순서면 번호 없는 광고그룹 행이 **스캔 전에도** `추출실패`/`광고청소` 로 떨어진다. 그런데 같은 플랜의 behavior 는 *"`join_doc=None` 이면 모든 행이 `미조회`/`시스템` 이고 `광고청소` 버킷이 **0**"* 을 요구한다. 두 지시가 충돌한다.
- **Fix:** `join_doc` 부재 검사를 맨 앞으로 뒀다. 근거를 함수 docstring 에 적었다 — 번호가 없다는 사실 자체는 참이지만, **조인을 한 번도 안 돌린 상태의 산출물을 "광고를 고쳐라" 로 내보내는 것**이 Pitfall 3 의 핵심이다. 대신 `번호` 필드는 그대로 채워 화면이 "무엇을 훑을 것인지" 를 보여줄 수 있게 했다.
- **Files modified:** `webapp/join.py`
- **Commit:** `aea4186`

**3. [Rule 3 - Blocking] `state.py` docstring 에서 금지 단어를 우회 표현으로 바꿨다**
- **Found during:** Task 1
- **Issue:** 플랜 action 은 docstring 에 *"MCP 호출 (D-19 — `eroomlib` import 금지. `.venv-web` 에 `requests` 가 없다)"* 와 *"`bool()` 로 플래그 읽기"* 를 적으라고 했다. 그런데 같은 플랜의 수용 기준은 `grep -cE '(eroomlib|requests|fastapi|starlette)' webapp/state.py` 가 **0**, `grep -v '^#' webapp/state.py | grep -c 'bool('` 가 **0** 이다. grep 은 주석과 docstring 을 구분하지 않으므로 지시를 그대로 따르면 수용 기준이 깨진다.
- **Fix:** 뜻을 유지하면서 표현을 바꿨다 — "불사자 클라이언트 라이브러리를 import 하지 않는다. 웹앱 전용 venv 에 그 HTTP 의존성이 없어 import 하는 순간 ImportError 다" · "내장 캐스팅으로 플래그 읽기". 기계가 검사하는 쪽(수용 기준)을 정본으로 삼았다.
- **Files modified:** `webapp/state.py`
- **Commit:** `270cb3a`

**4. [Rule 1 - Bug] `test_표시규칙은_버린다` 의 원본 검사를 전문 문자열 → **키** 기준으로 고쳤다**
- **Found during:** Task 2 GREEN (첫 실행에서 이 테스트만 red)
- **Issue:** `strip_display_rules(join_traps)` 의 `json.dumps` 전문에 `표시규칙` 이 없어야 한다고 단언했는데, 픽스처의 `_주석` **본문**이 그 단어를 설명으로 적고 있다. 그 단언은 "설명 문장까지 지웠는가" 를 묻게 되어 틀렸다 — 지워야 할 것은 모델 대상 지시문이 담긴 **키**다.
- **Fix:** `_표시규칙_키가_남았나()` 재귀 헬퍼를 더해 키 기준으로 검사한다. **`attach()` 결과에 대한 전문 문자열 검사는 그대로 남겼다** — 거기엔 `_주석` 이 안 실리므로 유효하고, 그게 T-3-06 이 실제로 막아야 할 경로다.
- **Verification:** 원본에서 키 2개(`$.표시규칙`, `$.행[2].표시규칙`)가 검출되고 제거 후 0개가 되는 것을 직접 실행해 확인했다 — 가드가 있는 척만 하지 않는다.
- **Files modified:** `webapp/tests/test_join.py`
- **Commit:** `aea4186`

**5. [Rule 1 - Bug] `test_불리언순서가_int보다_먼저다` 를 "분기 순서" 가 아니라 "반환 타입 동일성" 으로 고정했다**
- **Found during:** Task 1
- **Issue:** 플랜 behavior 는 *"`isinstance(v, bool)` 분기를 `int` 분기 앞에 두지 않으면 통과할 수 없는 케이스로 고정한다"* 를 요구했다. 실제로 그런 순수 동작 케이스는 **존재하지 않는다** — `isinstance(True, (int,float))` 는 참이고 `True != 0` 도 참이라 숫자 분기가 앞에 와도 `True`/`False` 가 우연히 맞고, 문자열 폴백(`str(False).lower() == "false"`)조차 맞는다.
- **Fix:** 대신 **진짜 잡히는 버그**를 고정했다 — 입력을 그대로 돌려주는 구현(`return v`)이다. `불리언정규화(1) is True` 는 `1 is True` 가 거짓이라 그런 구현에서 red 가 되고, `type(결과) is bool` 이 한 번 더 막는다. 그게 `board.js:68-72` 가 경고하는 "화면에 1/0 이 찍힌다" 의 실제 원인이다. 판단 근거를 테스트 docstring 에 적었다.
- **Files modified:** `webapp/tests/test_state.py`
- **Commit:** `3433d95`

**6. [Rule 3 - Blocking] 워크트리에 `.venv` · `.venv-web` · `workspace.toml` 이 없어 검증을 못 돌렸다**
- **Found during:** 실행 시작 직전
- **Issue:** 세 항목 모두 `.gitignore` 대상이라 git worktree 에 복사되지 않는다. 플랜의 모든 `<automated>` verify 가 `.venv-web/bin/pytest` 로 시작한다. (03-01 이 겪은 것과 같은 문제다.)
- **Fix:** 본체 저장소의 세 항목을 워크트리 안으로 심볼릭 링크했다. 링크 후 기존 스위트 205종 전량 green 인 것을 베이스라인으로 확인했다.
- **Files modified:** 없음 (링크는 `.gitignore` 대상이고 커밋에 안 들어갔다 — `git status --short` 에 `?? .venv` · `?? .venv-web` 만 남았다)
- **Commit:** 없음 (런타임 환경 구성)

### 플랜이 요구했지만 할 게 없었던 것

**`test_board.py` 의 `런타임_파일들` 등록** — 플랜은 *"새 런타임 파일을 등록해야 리터럴 가드가 작동한다. 단 등록 한 줄만 최소 변경으로 추가하라"* 고 했는데, **03-01 이 이미 `join.py`·`state.py`·`bulsaja_index.py` 를 선등록해 뒀다**(T-3-02 의 "파일보다 가드를 먼저 넣는다"). 그래서 `test_board.py` 를 한 글자도 건드리지 않았다 — 03-06 과의 충돌 위험도 0 이다. 파일이 생긴 지금 `f.is_file()` 이 `join.py`·`state.py` 둘 다 True 를 돌려주는 것을 직접 확인했고, `test_계정을_코드에_박지_않는다` 가 두 파일을 실제로 훑으며 통과한다.

### 계획된 이탈 (플랜이 SUMMARY 에 적으라고 지시한 것)

**`test_히트도_재검증한다` · `test_불일치는_미해소` 가 `test_index.py` 가 아니라 `test_join.py` 에 있다.**
`03-VALIDATION.md` 는 두 노드를 `test_index.py` 행에 적어 뒀지만, 판정 함수 `재검증판정` 이 **조인 의미론**이라 `join.py` 에 산다(`bulsaja_index.py` 는 인덱스에 적힌 값을 꺼내 주는 데까지만 한다 — 판정이 두 곳에 있으면 화면과 산출물이 다른 말을 한다). 그래서 **같은 이름으로** `test_join.py` 에 뒀다. **검증 내용은 그대로다** — 관측값이 없으면 히트가 안 나오고(JOIN-04), 불일치는 `해소=False`·`버킷=시스템` 으로 떨어진다. 03-05 가 `test_index.py` 를 만들 때 이 두 이름을 다시 만들지 마라.

**추가한 테스트 3종 (플랜 behavior 에 없던 것):**
- `test_스킵은_목표장수를_모른다` (`test_state.py`) — 플랜의 수용 기준이 `inspect.signature` 검사를 `python -c` 로 요구했다. 수용 기준에만 있고 스위트에 없으면 다음 회차에 아무도 안 돌린다. 테스트로 승격했다.
- `test_원본_행을_고치지_않는다` (`test_join.py`) — 플랜 action 의 "원본 mutate 금지" 를 기계가 보게 했다. 같은 rows 를 보드와 집계가 두 번 쓰면 조용히 어긋난다.
- `test_조인은_네트워크도_파일도_안_연다` (`test_join.py`) — 플랜 수용 기준의 grep 3종을 스위트 안으로 옮겼다(`test_board.py::test_보드는_ads_json_을_열지_않는다` 관용구). D-19 는 수용 기준에서만 살면 안 된다.

---

**Total deviations:** 6 auto-fixed (3 blocking, 3 bug) + 계획된 이탈 1 + 추가 테스트 3
**Impact on plan:** 범위 확장 없음. 산출물 4파일은 플랜 그대로이고, 공개 함수 이름·반환 키도 `<interfaces>` 그대로다.

## Issues Encountered

**🔴 03-04·03-05 가 알아야 할 것 — `재검증판정` 의 위치와 `미조회` 이름 가림.**

`재검증판정` 의 세 번째 파라미터 이름이 `미조회` 라 모듈 상수 `미조회` 를 함수 안에서 가린다. `join.py` 에 `_미조회 = 미조회` 별칭을 두고 그걸 쓴다(문자열을 다시 적으면 진실이 둘이 된다). **이 함수를 옮기거나 감싸는 코드를 쓸 때 같은 함정을 밟지 마라.**

**`index_targets` 의 빈 리스트는 "전량" 이 아니다.**
`argv.py:79-84` / `jobs.py:389-395` 와 같은 부류의 함정이다. docstring 에 못 박아 뒀지만, 03-04 의 인덱스 CLI 가 이 값을 받을 때 **빈 리스트를 "제한 없음" 으로 읽으면 47,105 상품을 통째로 다시 훑는다.**

**`resolution()` 은 비율을 안 낸다.**
분모가 0 이면 비율을 지어내지 않는다(`board.py:174-178` 정신). 03-06 화면이 비율을 만들되, **"92%" 옆에 해석을 붙여라** — RESEARCH §미해소 표시 설계요구 4: 숫자만 띄우면 시스템 고장처럼 읽히는데 실제 의미는 "광고 쪽에 청소할 그룹이 N개 있다" 다. `cleanup_groups()` 가 그 N 을 바로 준다.

**그 밖:** `.venv-web` 스위트의 `starlette`/`anyio` DeprecationWarning 2건은 Phase 1 부터 있던 외부 라이브러리 경고다. 우리 코드와 무관해 건드리지 않았다(`pytest.ini` 의 `filterwarnings = error` 미채택 판단과 같다).

## Known Stubs

없다. 두 런타임 모듈은 전부 실제 값을 계산하고, 빈 결과를 내는 경로는 **의도된 방어**(입력이 비었을 때 빈 목록)뿐이다. 하드코딩된 빈 값이 화면으로 흘러가는 자리는 없다.

`사본N`·`잠금혼재`·`상세상태` 가 미해소 행에서 `None` 인 것은 스텁이 아니라 규약이다 — 0 이나 빈 문자열로 채우면 "사본이 0건이었다"/"중국어 원본이다" 라는 **판정처럼** 보이는데, 실제로는 아직 안 본 것이다(`board.py:174-176` 의 "0 이 아니라 None").

## Threat Flags

없다. 새로 생긴 보안 표면이 0 이다 — 두 모듈은 네트워크·파일·DB 를 열지 않고, 외부 입력은 dict 로만 받는다. 플랜의 위협 5종은 전부 mitigate 로 처리됐다:

| Threat ID | 처리 | 고정 장치 |
|---|---|---|
| T-3-06 `표시규칙` 프롬프트 인젝션 | mitigate | `strip_display_rules()` + `test_표시규칙은_버린다` (키 기준 재귀 검사 + `attach` 결과 전문 검사) |
| T-3-07 429/미조회가 광고 오류로 둔갑 | mitigate | 사유코드 5종 + 버킷 2종. `test_인덱스없음이_광고오류로_둔갑하지_않는다` · `test_미해소_사유_3종` |
| T-3-08 판정 순서 역전 | mitigate | `test_AI생성이_번역보다_우선` |
| T-3-09 마켓그룹명·alias 소스 박힘 | mitigate | 사유는 전부 f-string. `test_계정을_코드에_박지_않는다` 가 이제 두 파일을 실제로 훑는다 |
| T-3-10 웹앱이 MCP 직접 호출 | mitigate | grep 수용 기준 + `test_조인은_네트워크도_파일도_안_연다` (스위트 안으로 승격) |

## Next Phase Readiness

**준비된 것:**
- **03-04 인덱스 CLI** — `index_targets(rows, join_doc, excluded)` 가 훑을 groupId 목록을 준다(번호 기준 중복제거 완료). 조인 산출물 스키마는 `join_traps.json` 이 정본이고, CLI 는 **관측만** 적으면 된다(`productId` · `인덱스_smartstore` · `관측_smartstore` · `미조회` · `uploadDetailContents` · `그룹태그` · `사본`). 판정 필드(`조회`·`기대_상태`)를 CLI 가 쓰면 진실이 둘이 된다.
- **03-05 `ss_index`** — `재검증판정` 이 이미 `join.py` 에 있다. 인덱스 모듈은 **값만 꺼내라.**
- **03-06 보드 UI** — `attach()` 의 키 14종이 그대로 열이 된다. 이모지(⚪🟡🔴)는 화면에서 붙인다 — 판정값은 문자열이다. `resolution()` 의 두 버킷을 **한 숫자로 합쳐 띄우지 마라.**
- **Phase 5 상세페이지** — `selectable()` 이 기작업 제외 대상 목록을 준다. 목표 장수와 무관한 절대 조건이다(STATE-05).

**주의:**
- 해상률이 100% 라고 **미해소 경로를 빼지 마라.** 물갈이·신규 수집·광고 재등록으로 번호는 다시 어긋난다.
- `test_실회차_해상률`(기댓값 179/194)은 **이 플랜에서 만들지 않았다.** 03-01-SUMMARY 가 실측으로 확인했듯 디스크의 픽스처는 정리 **전** 스냅샷이라 179 가 안 나온다. 03-04 가 정리 후 회차를 뜬 다음에 만들어라.

## Self-Check: PASSED

**생성 파일 존재 확인** — 4/4 FOUND
`webapp/state.py` · `webapp/join.py` · `webapp/tests/test_state.py` · `webapp/tests/test_join.py`

**커밋 존재 확인** — 4/4 FOUND
`3433d95` · `270cb3a` · `1c9e65f` · `aea4186`

**플랜 `<verification>` 블록 전량**
- `.venv-web/bin/pytest webapp/tests -q` → **236 passed** (시작 시 205 → 신규 31)
- `.venv-web/bin/pytest webapp/tests/test_join.py webapp/tests/test_state.py -q` → **31 passed**
- `.venv-web/bin/pytest webapp/tests/test_paths.py -k 리터럴 -x` → **3 passed**
- `bash webapp/tests/no_commit_guard.sh` → **OK (--commit 리터럴 0건)**

**수용 기준 grep 전량**
- `grep -c 'def 상세상태(' webapp/state.py` → **1**
- `grep -v '^#' webapp/state.py | grep -c 'bool('` → **0**
- `grep -cE '(eroomlib|requests|fastapi|starlette)' webapp/state.py` → **0**
- `기작업여부` 시그니처에 `pages`/`장수` 없음 → **PASS**
- `grep -c 'def attach(' webapp/join.py` → **1**
- `grep -cE '(eroomlib|requests|fastapi|starlette|APIRouter)' webapp/join.py` → **0**
- `grep -cE '(sqlite3|open\()' webapp/join.py` → **0**
- `.venv-web/bin/pytest webapp/tests/test_board.py -k 계정을_코드에 -x` → **1 passed** · `grep -c 'join.py' webapp/tests/test_board.py` → **1**
- VALIDATION 지목 노드 16종(state 5 + join 11) 전부 존재하고 통과

---
*Phase: 03-join-detail-state*
*Completed: 2026-09-21*
