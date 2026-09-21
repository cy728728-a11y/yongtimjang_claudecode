---
phase: 3
slug: join-detail-state
status: draft
# 🔴 아래 둘은 Task 3(보드 최종 확인 · 사람 게이트)이 **아직 안 끝나서** false 다.
#    산출물은 전부 섰고 자동 검증은 전량 green 이지만, "이 화면이 실제 작업에 쓸 만한가" 를
#    사람이 아직 확인하지 않았다. 승인 전에 true 로 올리면 그건 위조다.
nyquist_compliant: false   # pending — Task 3 미완
wave_0_complete: false     # pending — Task 3 미완 (산출물 자체는 전부 존재. §마감 현황 참조)
created: 2026-09-21
last_verified: 2026-09-21   # 03-07 Task 4 — 아래 표는 전부 이 날 실제로 돌려 본 결과다
---

# Phase 3 — Validation Strategy

> 회차별 검증 계약. 근거는 `03-RESEARCH.md` §Validation Architecture.
> 🔴 RESEARCH 최상단 갱신 공지를 먼저 읽어라 — 해상률 기댓값이 92 가 아니라 **179** 다.
> 🔴 **그 179 는 이 저장소의 픽스처로는 재현되지 않는다.** 아래 JOIN-01 실데이터 회귀 행을 봐라.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (`.venv-web/bin/pytest`) + 헤드리스 크롬 CDP 하네스 (`webapp/tests/*.sh` + `*.mjs`) |
| **Config file** | `webapp/pytest.ini` (`addopts = -q --strict-markers`) |
| **Quick run command** | `.venv-web/bin/pytest webapp/tests/test_join.py webapp/tests/test_state.py webapp/tests/test_index.py -x -q` |
| **Full suite command** | `.venv-web/bin/pytest webapp/tests -q && bash webapp/tests/no_commit_guard.sh && bash webapp/tests/board_cdp.sh` |
| **Estimated runtime** | quick ~5초 · full ~90초 |
| **실측 (2026-09-21)** | quick **73건 / 0.29초** · full **340건 / 11.4초** (exit 0) · `no_commit_guard.sh` exit 0 · CDP **38 PASS / 0 FAIL** |

> ⚠️ `board_cdp.sh` 는 **살아 있는 서버 + `CT_DEV_TOKEN`** 이 필요하다. 토큰은 서버 기동마다
> 바뀌므로, 토큰 없이 띄워 둔 서버에는 붙을 수 없다. 이번 검증은 8765 의 서버를 건드리지 않고
> 같은 코드·같은 `webapp.db` 로 **8766 에 임시 서버를 따로 띄워** 돌린 뒤 그 임시 서버만 껐다.
> 증거: `03-07-evidence/06-보드-CDP-전량PASS.txt`

---

## Sampling Rate

- **작업 커밋마다:** quick run command
- **웨이브 머지마다:** full suite command
- **`/gsd:verify-work` 전:** full suite 전부 green
- **Max feedback latency:** 90초 → **실측 11.4초** (full). quick 은 0.29초

---

## Per-Task Verification Map

> 아래 `Status` 는 **2026-09-21 에 명령을 실제로 실행한 결과**다. 추정으로 채운 칸은 없다.
> `File Exists` 는 그 검증이 실제로 어느 파일에 사는지를 적는다 — 계획된 자리와 다르면 ⚠️.

| Requirement | 동작 | Threat Ref | Test Type | Automated Command | File Exists | Status |
|---|---|---|---|---|---|---|
| STATE-01 | `detail_batch.py --help` 가 exit 0 | — | smoke | `.venv/bin/python3 .claude/skills/bulsaja-detail-page/scripts/detail_batch.py --help` | ✅ `test_cli_shim.py::test_상세배치가_이_맥북에서_뜬다` | ✅ exit 0 · 회귀도 pass |
| STATE-02 | `'0'`/`'1'`/`False`/`1`/`None` 5종 정규화 | — | unit | `pytest webapp/tests/test_state.py::test_불리언정규화 -x` | ✅ `test_state.py:32` | ✅ |
| STATE-02 | `bool('0')` 함정 회귀 | — | unit | `pytest webapp/tests/test_state.py::test_문자열0은_거짓이다 -x` | ✅ `test_state.py:51` | ✅ |
| STATE-03 | ⚪🟡🔴 3단계 판정 | — | unit | `pytest webapp/tests/test_state.py::test_상세상태_3단계 -x` | ✅ `test_state.py:65` | ✅ |
| STATE-03 | **판정 순서** — `{ai:True, translated:'1'}` → ⚪ | 크레딧 이중지불 | unit | `pytest webapp/tests/test_state.py::test_AI생성이_번역보다_우선 -x` | ✅ `test_state.py:80` | ✅ |
| STATE-03 | `aiImageGenerated` **키 부재**에 KeyError 없음 | — | unit | `pytest webapp/tests/test_state.py::test_키가_없어도_안터진다 -x` | ✅ `test_state.py:96` | ✅ |
| STATE-04 | 외부 경로는 `aiImageGenerated` 를 안 찍는다 — 결론이 문서에 반영 | — | doc | `grep -c 'aiImageGenerated' webapp/state.py` | ✅ `webapp/state.py` docstring 31–38행 (§"STATE-04 확정") | ✅ grep 6건 · 결론 문장 존재 (아래 근거) |
| STATE-05 | 기작업(태그 or AI) 상품이 기본 선택에서 빠진다 | 크레딧 이중지불 | unit | `pytest webapp/tests/test_join.py::test_기작업은_기본선택에서_빠진다 -x` | ✅ `test_join.py:460` | ✅ |
| STATE-05 | 목표 장수를 바꿔도 스킵이 유지된다 | 크레딧 이중지불 | unit | `pytest webapp/tests/test_join.py::test_스킵은_장수와_무관하다 -x` | ✅ `test_join.py:493` | ✅ |
| JOIN-01 | 해상률 = 해소/전체 | — | unit | `pytest webapp/tests/test_join.py::test_해상률 -x` | ✅ `test_join.py:159` | ✅ |
| JOIN-01 | **실데이터 회귀 — 2026-09-20 회차에서 179/194** | 무결성 | unit(fixture) | `pytest webapp/tests/test_join.py::test_실회차_해상률 -x` | ✅ `test_join.py:187` | ⚠️ **테스트는 green, 기댓값은 이탈** — 실측 **92/194** (아래 ①) |
| JOIN-02 | 미해소 사유 **3종 구분** (추출실패 / 번호없음 / **미조회**) | Pitfall 3 | unit | `pytest webapp/tests/test_join.py::test_미해소_사유_3종 -x` | ✅ `test_join.py:280` | ✅ |
| JOIN-02 | 사유 문자열에 **광고그룹명 원문**이 들어간다 | — | unit | `pytest webapp/tests/test_join.py::test_사유에_광고그룹명 -x` | ✅ `test_join.py:311` | ✅ |
| JOIN-02 | 번호 추출 전수 — 정리 후 **58개 광고그룹명** (`1000개_22-1_…` 포함) | — | unit | `pytest webapp/tests/test_join.py::test_번호추출_전수 -x` | ✅ `test_join.py:74` | ✅ |
| JOIN-02 | **같은 번호 7쌍 중복제거** — 번호 기준 1그룹으로 접힌다 | 비용 | unit | `pytest webapp/tests/test_join.py::test_같은번호_중복제거 -x` | ✅ `test_join.py:129` | ✅ |
| JOIN-03 | 사본 N건 팬아웃 표시 | 오작업 | unit | `pytest webapp/tests/test_join.py::test_팬아웃_N건 -x` | ✅ `test_join.py:442` | ✅ |
| JOIN-04 | 인덱스 히트가 **재검증 없이** 쓰이지 않는다 | 물갈이 재발급 | unit | ~~`test_index.py::test_히트도_재검증한다`~~ → `pytest webapp/tests/test_join.py::test_히트도_재검증한다 -x` | ⚠️ **파일 이탈** — `test_index.py` 가 아니라 `test_join.py:372` | ✅ (계획한 파일에서는 `ERROR: not found`) |
| JOIN-04 | 재검증 불일치 시 미해소로 떨어진다 | 물갈이 재발급 | unit | ~~`test_index.py::test_불일치는_미해소`~~ → `pytest webapp/tests/test_join.py::test_불일치는_미해소 -x` | ⚠️ **파일 이탈** — `test_join.py:385` | ✅ (계획한 파일에서는 `ERROR: not found`) |
| ENG-08 | 기대 계정 아니면 **쓰기 잡 생성이 거부**된다 | Elevation | unit | `pytest webapp/tests/test_jobs.py::test_계정불일치_거부 -x` | ✅ `test_jobs.py:865` | ✅ |
| ENG-08 | 기대 계정명이 코드·주석에 리터럴로 없다 | 리터럴 가드 | unit(guard) | `pytest webapp/tests/test_paths.py -k 리터럴 -x` | ✅ `test_paths.py:277·313·326` | ✅ 3건 pass |
| ENG-08 | MCP 응답의 `표시규칙` 필드가 화면에 안 나온다 | 프롬프트 인젝션 | unit | `pytest webapp/tests/test_join.py::test_표시규칙은_버린다 -x` | ✅ `test_join.py:515` (+ `test_index.py:344` · `test_board.py:559`) | ✅ |
| D-18 | **제외 그룹이 설정값**이다 — 코드·주석에 리터럴 없음 | 리터럴 가드 | unit(guard) | `pytest webapp/tests/test_paths.py -k 리터럴 -x` | ✅ `test_paths.py:326` | ✅ |
| D-18 | 제외 그룹의 행은 **"미조회"** 이고 "번호없음"과 구분된다 | Pitfall 3 | unit | `pytest webapp/tests/test_join.py::test_미해소_사유_3종 -x` | ✅ `test_join.py:280` | ✅ **+ 실서버 실측 PASS** (13-2 197행 전부 `미조회` · `번호없음` 0건 — `03-07-evidence/03-완주-실측.txt`) |
| — | 레이트리밋 throttle 이 **0.26초 이상** 유지 | 429 | unit(fake clock) | `pytest webapp/tests/test_index.py::test_초당4회_상한 -x` | ✅ `test_index.py:412` | ✅ (단, **프로세스마다** 0.26초다 — 아래 ②) |
| — | **429 를 삼키지 않고** 미조회로 기록 | Pitfall 2·3 | unit | `pytest webapp/tests/test_index.py::test_429는_미조회로_남는다 -x` | ✅ `test_index.py:447` | ⚠️ **단위는 green, 실서버에 구멍** — 그룹 **목록 조회** 단계의 429 는 미조회로 안 남는다 (아래 ②) |
| — | 새 런타임 파일이 계정 리터럴 가드 **대상 리스트에 포함** | 가드 무력화 | unit(guard) | `pytest webapp/tests/test_board.py -k 계정을_코드에 -x` | ✅ `test_board.py:82` (`런타임_파일들()` 이 `webapp/**` 를 통째로 훑는다 — 리스트가 아니라 글롭이라 빠뜨릴 수 없다) | ✅ |
| — | 보드에 상태 열·해상률 배너가 **실제로 그려진다** | — | CDP | `bash webapp/tests/board_cdp.sh` | ✅ `board_cdp.sh` + `board_cdp.mjs` | ✅ **38 PASS / 0 FAIL** (V-BOARD-00~22, exit 0) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ green 이지만 계약과 어긋남*

### 표에 달린 주석

**① JOIN-01 실데이터 회귀 — 기댓값 179/194 vs 실측 92/194**
`result_join_real.json` 은 **광고그룹 정리 전(2026-09-20)** 스냅샷이다. CONTEXT 의 179 는
69→58그룹 정리 + 번호 9건 정정을 끝낸 뒤 같은 회차에 재판정한 값이라 이 디스크 픽스처로는
재현되지 않는다. 숫자를 맞추려고 픽스처를 고치면 이 테스트는 아무것도 안 지킨다.
그래서 테스트는 **92 를 만드는 계산이 안 바뀐다**를 고정하고, docstring(`test_join.py:187-200`)이
그 사유를 안고 있다. 179 를 보려면 정리 후 광고 회차를 새로 떠야 한다 — Phase 4 이후.

**② 429 — 단위 테스트가 보는 곳과 실서버가 터진 곳이 다르다**
`test_429는_미조회로_남는다` 는 **상품 단위** 429 만 본다. 2026-09-21 14:01 인덱스 재실행에서
**그룹 목록 조회 단계**가 429 로 죽었는데(그룹 5·6), 최종 요약은 `끝 — 그룹 30개 … 미조회 0`
이라고 말했고 `ss_index` 에도 미조회 행이 0건이었다. 이번엔 이미 채워진 그룹이라 손실이
없었지만 **첫 구축 중에 같은 일이 나면 그 그룹이 통째로 비고 화면은 "완주"라고 말한다.**
증거: `03-07-evidence/05-재실행-429-그룹5-6.txt`. → §미해결 1번.

**③ STATE-04 근거 (실제 grep 결과)**
`webapp/state.py:31` — 제목 그대로: "STATE-04 확정 — 외부 반영 경로는 `aiImageGenerated` 를 찍지 않는다"
`webapp/state.py:33-36` — 양성대조 8건 전부 `aiImageGenerated=True`, 음성대조 26건 전부 키 부재.
**실탄 보강(2026-09-21 Task 2):** 첫 인덱스 완주 뒤 해소 51행의 상태 분포가
🔴 31 · 🟡 20 · **⚪ 0** 이었고, `uploadDetailContents` 의 키가 `{imageTranslated, renderContent}`
**둘뿐**이었다. `aiImageGenerated` 키가 응답에 아예 안 실린다 — 외부 경로로만 가공된 상품이
⚪ 로 안 올라온다는 결론이 실데이터로 한 번 더 맞았다. CDP 도 같은 값을 봤다
(`V-BOARD-12 AI가공완료 배지 = 0`).

---

## Wave 0 Requirements

> 실제로 파일이 있는 것만 체크했다 (2026-09-21 `test -f` · `pytest --co` 로 확인).

- [x] `webapp/join.py` — 번호 추출 · 마켓그룹 매칭 · 해상률 · 미해소 사유 3종 (JOIN-01/02)
- [x] `webapp/state.py` — 불리언 정규화 · 3단계 판정 (STATE-02/03)
- [x] `webapp/bulsaja_index.py` — 인덱스 조회 · 재검증 · throttle (JOIN-04)
- [x] 인덱스 구축 CLI (`.claude/skills/bulsaja-detail-page/scripts/ss_index_build.py`) + `webapp/argv.py` 의 `BulsajaArgv` (`argv.py:120`)
- [x] `webapp/tests/test_join.py`(20건) · `test_state.py`(13건) · `test_index.py`(40건) · `test_cli_shim.py`(6건)
- [x] `webapp/tests/fixtures/` —
      ① 실회차 ③⑤ **194행** 축약본 → `result_join_real.json` (`test_실회차_해상률` 이 `집계["전체"]==194` 로 단언. **단 해상률 회귀값은 179 가 아니라 92 다 — 위 ①**)
      ② 불사자 마켓그룹 목록 **86개** → `bulsaja_groups_real.json` (`len(...)==86` 단언 통과)
      ③ `workdata` 응답 **4종**(⚪/🟡/🔴/키부재) → `join_traps.json` (`test_픽스처_함정_전수` 가 `본_행 == 4` 로 단언)
      ④ **정리 후 광고그룹명 58종** → `test_번호추출_전수` 통과
      · 익명화 규율 지켜짐: 그룹명은 `zzfake`, 마켓번호 `NN-N` 만 글자 그대로 보존
        (`test_실회차_그룹픽스처에_실물이름이_없다` 가 기계로 본다)
- [x] `test_board.py` 의 계정 리터럴 가드 — **리스트가 아니라 `webapp/**` 글롭**으로 바뀌었다
      (`런타임_파일들()`). 파일을 새로 만들어도 자동으로 훑기 때문에 "빠뜨려서 있는 척"이 구조적으로 불가능하다.
      `assert len(파일들) >= 15` 가 제외 규칙이 과하게 넓어지는 것을 같이 막는다
- [x] `settings.DEFAULTS` 에 `expected_bulsaja_nick` · `mcp_min_interval` · `mcp_retry_after` ·
      `mcp_batch_size` · **`index_excluded_groups`(D-18)** 추가 — 5키 전부 존재 확인

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions | 실측 결과 (2026-09-21) |
|---|---|---|---|---|
| 첫 인덱스 구축이 36그룹 47,105 상품을 완주한다 (~3시간 32분) | JOIN-04 / D-18 | 실시간 3시간 반. 자동 스위트에 넣을 수 없다 | `caffeinate -i` 로 감싼 인덱스 잡을 띄우고, 그룹 단위 체크포인트가 SQLite 에 쌓이는지 확인. 중간에 한 번 죽이고 재개되는지 본다 | ✅ **완주.** 아래 §완주 실측 표 참조. 단 모수는 36그룹이 아니라 **서버가 계산한 30그룹**이 정본이다 |
| 외부 경로 상세 반영 후 `aiImageGenerated` 미기록 | STATE-04 | 실제 쓰기 + 크레딧 소모 | RESEARCH §STATE-04 의 음성대조 26건으로 대체. 확정 실험은 Phase 5 에서 | ✅ **실데이터로 재확인.** 해소 51행 중 ⚪ **0건** · `uploadDetailContents` 키가 `{imageTranslated, renderContent}` 둘뿐 (위 ③). 확정 실험은 예정대로 Phase 5 |
| 보드가 광고 청소 목록으로 실제 쓸 만한지 | JOIN-02 | 사람 판단 | 미해소 행의 사유만 보고 네이버 광고에서 해당 그룹을 찾을 수 있는지 용팀장이 확인 | ⬜ **Task 3 사람 게이트 대기** — 용팀장이 "나중에 확인할게". 기계 쪽 선행 확인은 끝났다(청소 목록 19그룹이 그려지고 셀 값이 원본 `adGroups` 와 정확히 일치 — `V-BOARD-20/21`). 남은 건 **사유만 보고 광고 화면에서 그 그룹을 찾을 수 있는가**라는 사람 판단 하나다 |

### 완주 실측 (Task 2 · `03-07-evidence/` 4파일)

| 항목 | 실측 | 근거 |
|---|---|---|
| 소요시간 | **2시간 8분** (7,681초) | 잡 `4180682f` 11:43:03 → 13:51:25 · exit 0 |
| 인덱스 행수 | **30,546행** / 30그룹 (smartstore 번호 있는 행 26,551) | `sqlite3 webapp.db 'select count(*), sum(unresolved) from ss_index'` → `30546` / `0` |
| 미조회 수 | **0** | 같은 쿼리 |
| 429 발생 | **0회** (첫 완주 한정. 14:01 재실행에서는 2그룹이 429 로 죽었다 — 위 ②) | 진행 로그 전문에 `HTTP 429`·`Retry-After` 0건 |
| 재개가 건너뛴 것 | **1그룹 통째 + 그룹2 내 142건 = 상품 3,688건** | `03-07-evidence/01-재개-실증.txt` |
| `[그룹 1/N]` 의 N | **30** (플랜 본문의 36 은 옛 숫자. D-18 제외 + ③⑤ 행으로 좁힌 결과) | 진행 로그 |
| 보드 상품 연결 | **0 → 51** (/6062) | 인덱스 전후 배너 |
| 인덱스 불완전 | **84행(30그룹) → 0행(0그룹)** | 인덱스 전후 배너 |
| 🔴 13-2 제외 그룹 검사 (T-3-38) | **PASS** — 197행 전부 `미조회` · `번호없음` **0건** | `03-완주-실측.txt` |
| 상태 분포 (Phase 5 의 입력) | 🔴 31 · 🟡 20 · ⚪ 0 / 기작업 29 / 사본 1건 이상 42행(최대 23) | CDP `V-BOARD-12` 가 같은 값을 독립 확인 |
| 재개 전수 실증 (보너스) | 2차 재실행이 30그룹 전부 "조회할 것 0건" 으로 **171.9초**에 종료 | `05-재실행-429-그룹5-6.txt` |

---

## Validation Sign-Off

- [x] 모든 태스크에 `<automated>` verify 또는 Wave 0 의존성이 있다 — 7개 플랜 21태스크 전부 `<automated>` 보유 (체크포인트 2개도 `<automated>` 를 같이 들고 있다)
- [x] 샘플링 연속성: 자동 검증 없는 태스크가 3연속으로 나오지 않는다 — 자동 검증 없는 태스크가 **0개**다
- [x] Wave 0 가 모든 MISSING 참조를 덮는다 — 위 Wave 0 체크박스 8행 전부 실물 확인
- [x] watch 모드 플래그 없음 — `grep -- '--watch|watch mode|pytest-watch'` 0건
- [x] Feedback latency < 90초 — 실측 full **11.4초** / quick **0.29초**
- [ ] `nyquist_compliant: true` 를 frontmatter 에 설정 — **pending. Task 3 미완이라 false 로 둔다**

- [x] 요구사항 10종이 전부 어느 플랜의 `requirements` 에 등장한다 (Task 4 수용 기준)

```
$ grep -h '^requirements:' .planning/phases/03-join-detail-state/03-0*-PLAN.md \
  | tr -d '[]' | tr ',' '\n' | tr -d ' ' | sed 's/requirements://' | sort -u
ENG-08  JOIN-01  JOIN-02  JOIN-03  JOIN-04
STATE-01  STATE-02  STATE-03  STATE-04  STATE-05
```
10종 전부 등장한다. 플랜별 배정:
`03-01`=STATE-01 · `03-02`=STATE-02/03/04/05+JOIN-01/02/03/04 · `03-03`=ENG-08,JOIN-04 ·
`03-04`=ENG-08,JOIN-03,JOIN-04 · `03-05`=ENG-08,JOIN-01,JOIN-04 ·
`03-06`=JOIN-01/02/03,STATE-03/05 · `03-07`=JOIN-01,JOIN-04,STATE-04

**Approval:** **pending — Task 3(보드 최종 확인) 미완.** 용팀장이 "나중에 확인할게" 로 보류.
Task 1·2 는 마감됐고 자동 검증은 전량 green 이다. 승인 시 이 줄에 날짜를 적는다.

---

## 마감 현황 (2026-09-21 · 03-07 Task 4)

**닫힌 것:** Per-Task Verification Map 27행 전부 실행 완료 (✅ 23 · ⚠️ 4 · ❌ 0) ·
Wave 0 체크박스 8행 · Manual-Only 3행 중 2행 · Sign-Off 6행 중 5행.

### 미해결 목록 (`/gsd:verify-work` 가 읽는다 — 숨기지 않았다)

1. 🔴 **그룹 목록 조회 단계의 HTTP 429 가 아무 데도 안 남는다.**
   2026-09-21 14:01 인덱스 재실행에서 그룹 5·6 이 `⛔ 실패: 요청 실패(재시도 4회 초과): HTTP 429`
   로 죽었는데, 최종 요약은 `끝 — 그룹 30개 · 누적 27775행 · 미조회 0` 이라고 말했다.
   `ss_index` 의 `sum(unresolved)` 도 그대로 0 이다. 최종 '누적' 이 죽은 2그룹(760+2,011=2,771행)을
   빼고 세는 것만이 유일한 힌트인데, 화면에서 그걸 알아챌 방법이 없다.
   **위험:** 첫 구축 중에 같은 일이 나면 그 그룹이 통째로 비고 화면은 "완주"라고 말한다 →
   Phase 5 가 대상 목록을 통째로 놓친다.
   **안 고친 이유:** 이 태스크의 `<files>` 는 `03-VALIDATION.md` 하나이고, 지금 용팀장이
   Task 3 용으로 그 CLI 가 붙은 서버를 열어 두고 있다. 도는 물건을 바꾸지 않는 쪽을 골랐다.
   **고칠 자리:** `ss_index_build.py` — ① 그룹 실패를 최종 요약에 `실패 N그룹` 으로 싣고
   ② 종료코드를 0 이 아닌 값으로 내고 ③ 실패 그룹을 `완결=아니오` 로 남긴다.
   증거: `03-07-evidence/05-재실행-429-그룹5-6.txt`

2. 🟡 **레이트리밋이 프로세스마다 걸린다.** `test_초당4회_상한` 은 한 프로세스 안에서만 0.26초를
   보장한다. 인덱스 잡과 스캔 잡이 동시에 돌면 합쳐서 상한을 넘는다 — 1번의 429 가 정확히
   그 상황(4초 차로 두 잡 동시 기동)에서 났다. **가설이고 아직 검증 안 했다.**
   당장의 회피책: 인덱스와 스캔을 같이 누르지 않는다. 구조적 해법은 잡 kind 간 상호배제.

3. 🟡 **JOIN-01 실데이터 회귀 기댓값이 179 가 아니라 92 다.** 픽스처가 광고그룹 정리 **전**
   스냅샷이라 구조적으로 재현 불가. 정리 후 회차를 새로 떠서 픽스처를 갈아끼우면 179 가 되고,
   그때 `test_실회차_해상률` 의 docstring 과 이 문서의 기댓값을 같이 고쳐야 한다. (위 ①)

4. 🟡 **`JOIN-04` 검증 2종의 파일 이탈.** 계약은 `test_index.py` 를 지목하는데 실제로는
   `test_join.py` 에 있다. 사유: 재검증 판정 함수 `재검증판정` 이 `join.py` 에 살아서
   테스트도 그 짝을 따라갔다. 동작은 green 이라 표에서 명령만 고쳐 두었다.
   원래 자리로 옮길 계획은 없다 — 옮기면 테스트가 판정 대상과 멀어진다.

5. ⬜ **Task 3(보드 최종 확인)이 안 끝났다.** 그래서 `nyquist_compliant` ·
   `wave_0_complete` · `Approval` 이 전부 false/pending 이다. 남은 사람 판단 3가지:
   ① 🔴 목록이 "유입은 있는데 상세가 중국어 원본인 상품" 으로 읽히는가
   ② 미해소 사유만 보고 네이버 광고에서 그 그룹을 찾을 수 있는가 (JOIN-02 수동 검증)
   ③ 두 배너("내가 지울 것" vs "시스템이 못 읽은 것")가 헷갈리지 않는가
   기계 쪽 선행 확인은 전부 끝났다(CDP 38 PASS). 서버는 8765 에 그대로 떠 있다 (PID 49565).

6. 🟢 **Task 4 수용 기준 중 "`⬜` 0건" 은 의도적으로 안 지켰다.**
   이 문서의 `⬜` 는 **Task 3 에 달린 것뿐**이다(Manual-Only 3행 · 위 5번). Task 3 가
   안 끝났는데 ✅ 를 적으면 그게 T-3-40(검증 문서를 추정으로 채움) 그 자체다.
   Task 3 승인 뒤에 그 칸만 채우면 0건이 된다.

7. ⚪ **참고 — 잡 2건이 `running` 으로 남아 있다.** `f5c960da`(index) · `218104ba`(scan).
   로그상 둘 다 정상 종료했는데 자식이 `defunct` 로 남아 상태가 안 갱신됐다. 서버를 다시
   띄우면 고아 스윕이 정리한다. 같은 kind 를 다시 누르면 409 가 날 수 있다 — Task 3 중에
   버튼이 거부되면 이것 때문이다.
