---
phase: 3
slug: join-detail-state
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-09-21
---

# Phase 3 — Validation Strategy

> 회차별 검증 계약. 근거는 `03-RESEARCH.md` §Validation Architecture.
> 🔴 RESEARCH 최상단 갱신 공지를 먼저 읽어라 — 해상률 기댓값이 92 가 아니라 **179** 다.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (`.venv-web/bin/pytest`) + 헤드리스 크롬 CDP 하네스 (`webapp/tests/*.sh` + `*.mjs`) |
| **Config file** | `webapp/pytest.ini` (`addopts = -q --strict-markers`) |
| **Quick run command** | `.venv-web/bin/pytest webapp/tests/test_join.py webapp/tests/test_state.py webapp/tests/test_index.py -x -q` |
| **Full suite command** | `.venv-web/bin/pytest webapp/tests -q && bash webapp/tests/no_commit_guard.sh && bash webapp/tests/board_cdp.sh` |
| **Estimated runtime** | quick ~5초 · full ~90초 |

---

## Sampling Rate

- **작업 커밋마다:** quick run command
- **웨이브 머지마다:** full suite command
- **`/gsd:verify-work` 전:** full suite 전부 green
- **Max feedback latency:** 90초

---

## Per-Task Verification Map

> Task ID 는 PLAN 이 확정되면 채운다. 아래는 **요구사항 → 검증** 계약이고, 플래너는 모든 행을 어떤 태스크에든 배정해야 한다.

| Requirement | 동작 | Threat Ref | Test Type | Automated Command | File Exists | Status |
|---|---|---|---|---|---|---|
| STATE-01 | `detail_batch.py --help` 가 exit 0 | — | smoke | `.venv/bin/python3 .claude/skills/bulsaja-detail-page/scripts/detail_batch.py --help` | ❌ W0 `test_cli_shim.py` | ⬜ |
| STATE-02 | `'0'`/`'1'`/`False`/`1`/`None` 5종 정규화 | — | unit | `pytest webapp/tests/test_state.py::test_불리언정규화 -x` | ❌ W0 | ⬜ |
| STATE-02 | `bool('0')` 함정 회귀 | — | unit | `pytest webapp/tests/test_state.py::test_문자열0은_거짓이다 -x` | ❌ W0 | ⬜ |
| STATE-03 | ⚪🟡🔴 3단계 판정 | — | unit | `pytest webapp/tests/test_state.py::test_상세상태_3단계 -x` | ❌ W0 | ⬜ |
| STATE-03 | **판정 순서** — `{ai:True, translated:'1'}` → ⚪ | 크레딧 이중지불 | unit | `pytest webapp/tests/test_state.py::test_AI생성이_번역보다_우선 -x` | ❌ W0 | ⬜ |
| STATE-03 | `aiImageGenerated` **키 부재**에 KeyError 없음 | — | unit | `pytest webapp/tests/test_state.py::test_키가_없어도_안터진다 -x` | ❌ W0 | ⬜ |
| STATE-04 | 외부 경로는 `aiImageGenerated` 를 안 찍는다 — 결론이 문서에 반영 | — | doc | — | 수동 (RESEARCH §STATE-04) | ⬜ |
| STATE-05 | 기작업(태그 or AI) 상품이 기본 선택에서 빠진다 | 크레딧 이중지불 | unit | `pytest webapp/tests/test_join.py::test_기작업은_기본선택에서_빠진다 -x` | ❌ W0 | ⬜ |
| STATE-05 | 목표 장수를 바꿔도 스킵이 유지된다 | 크레딧 이중지불 | unit | `pytest webapp/tests/test_join.py::test_스킵은_장수와_무관하다 -x` | ❌ W0 | ⬜ |
| JOIN-01 | 해상률 = 해소/전체 | — | unit | `pytest webapp/tests/test_join.py::test_해상률 -x` | ❌ W0 | ⬜ |
| JOIN-01 | **실데이터 회귀 — 2026-09-20 회차에서 179/194** | 무결성 | unit(fixture) | `pytest webapp/tests/test_join.py::test_실회차_해상률 -x` | ❌ W0 | ⬜ |
| JOIN-02 | 미해소 사유 **3종 구분** (추출실패 / 번호없음 / **미조회**) | Pitfall 3 | unit | `pytest webapp/tests/test_join.py::test_미해소_사유_3종 -x` | ❌ W0 | ⬜ |
| JOIN-02 | 사유 문자열에 **광고그룹명 원문**이 들어간다 | — | unit | `pytest webapp/tests/test_join.py::test_사유에_광고그룹명 -x` | ❌ W0 | ⬜ |
| JOIN-02 | 번호 추출 전수 — 정리 후 **58개 광고그룹명** (`1000개_22-1_…` 포함) | — | unit | `pytest webapp/tests/test_join.py::test_번호추출_전수 -x` | ❌ W0 | ⬜ |
| JOIN-02 | **같은 번호 7쌍 중복제거** — 번호 기준 1그룹으로 접힌다 | 비용 | unit | `pytest webapp/tests/test_join.py::test_같은번호_중복제거 -x` | ❌ W0 | ⬜ |
| JOIN-03 | 사본 N건 팬아웃 표시 | 오작업 | unit | `pytest webapp/tests/test_join.py::test_팬아웃_N건 -x` | ❌ W0 | ⬜ |
| JOIN-04 | 인덱스 히트가 **재검증 없이** 쓰이지 않는다 | 물갈이 재발급 | unit | `pytest webapp/tests/test_index.py::test_히트도_재검증한다 -x` | ❌ W0 | ⬜ |
| JOIN-04 | 재검증 불일치 시 미해소로 떨어진다 | 물갈이 재발급 | unit | `pytest webapp/tests/test_index.py::test_불일치는_미해소 -x` | ❌ W0 | ⬜ |
| ENG-08 | 기대 계정 아니면 **쓰기 잡 생성이 거부**된다 | Elevation | unit | `pytest webapp/tests/test_jobs.py::test_계정불일치_거부 -x` | ❌ W0 | ⬜ |
| ENG-08 | 기대 계정명이 코드·주석에 리터럴로 없다 | 리터럴 가드 | unit(guard) | `pytest webapp/tests/test_paths.py -k 리터럴 -x` | ✅ 확장 | ⬜ |
| ENG-08 | MCP 응답의 `표시규칙` 필드가 화면에 안 나온다 | 프롬프트 인젝션 | unit | `pytest webapp/tests/test_join.py::test_표시규칙은_버린다 -x` | ❌ W0 | ⬜ |
| D-18 | **제외 그룹이 설정값**이다 — 코드·주석에 리터럴 없음 | 리터럴 가드 | unit(guard) | `pytest webapp/tests/test_paths.py -k 리터럴 -x` | ✅ 확장 | ⬜ |
| D-18 | 제외 그룹의 행은 **"미조회"** 이고 "번호없음"과 구분된다 | Pitfall 3 | unit | `pytest webapp/tests/test_join.py::test_미해소_사유_3종 -x` | ❌ W0 | ⬜ |
| — | 레이트리밋 throttle 이 **0.26초 이상** 유지 | 429 | unit(fake clock) | `pytest webapp/tests/test_index.py::test_초당4회_상한 -x` | ❌ W0 | ⬜ |
| — | **429 를 삼키지 않고** 미조회로 기록 | Pitfall 2·3 | unit | `pytest webapp/tests/test_index.py::test_429는_미조회로_남는다 -x` | ❌ W0 | ⬜ |
| — | 새 런타임 파일이 계정 리터럴 가드 **대상 리스트에 포함** | 가드 무력화 | unit(guard) | `pytest webapp/tests/test_board.py -k 계정을_코드에 -x` | ✅ 리스트 확장 | ⬜ |
| — | 보드에 상태 열·해상률 배너가 **실제로 그려진다** | — | CDP | `bash webapp/tests/board_cdp.sh` | ✅ 확장 | ⬜ |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `webapp/join.py` — 번호 추출 · 마켓그룹 매칭 · 해상률 · 미해소 사유 3종 (JOIN-01/02)
- [ ] `webapp/state.py` — 불리언 정규화 · 3단계 판정 (STATE-02/03)
- [ ] `webapp/bulsaja_index.py` — 인덱스 조회 · 재검증 · throttle (JOIN-04)
- [ ] 인덱스 구축 CLI + `webapp/argv.py` 의 `BulsajaArgv`
- [ ] `webapp/tests/test_join.py` · `test_state.py` · `test_index.py` · `test_cli_shim.py`
- [ ] `webapp/tests/fixtures/` —
      ① 실회차 ③⑤ 194행 축약본 (**해상률 179 회귀용**)
      ② 불사자 마켓그룹 목록 86개
      ③ `workdata` 응답 4종 (⚪ / 🟡 / 🔴 / 키부재)
      ④ **정리 후 광고그룹명 58종** (옛 이름 쓰지 마라 — 더 이상 존재하지 않는다)
      ⚠️ 픽스처에 진짜 계정 alias·마켓그룹명을 그대로 넣으면 **리터럴 가드와 충돌한다.**
      `test_board.py` 처럼 가짜 이름(`zzfake`)을 섞어 "코드에 안 박혔다"를 증명하는 쪽으로 만들어라.
- [ ] `test_board.py` 의 `런타임_파일들` 리스트에 새 파일 추가 — **빠뜨리면 가드가 있는 척만 한다**
- [ ] `settings.DEFAULTS` 에 `expected_bulsaja_nick` · `mcp_min_interval` · `mcp_retry_after` ·
      `mcp_batch_size` · **`index_excluded_groups`(D-18)** 추가

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|---|---|---|---|
| 첫 인덱스 구축이 36그룹 47,105 상품을 완주한다 (~3시간 32분) | JOIN-04 / D-18 | 실시간 3시간 반. 자동 스위트에 넣을 수 없다 | `caffeinate -i` 로 감싼 인덱스 잡을 띄우고, 그룹 단위 체크포인트가 SQLite 에 쌓이는지 확인. 중간에 한 번 죽이고 재개되는지 본다 |
| 외부 경로 상세 반영 후 `aiImageGenerated` 미기록 | STATE-04 | 실제 쓰기 + 크레딧 소모 | RESEARCH §STATE-04 의 음성대조 26건으로 대체. 확정 실험은 Phase 5 에서 |
| 보드가 광고 청소 목록으로 실제 쓸 만한지 | JOIN-02 | 사람 판단 | 미해소 행의 사유만 보고 네이버 광고에서 해당 그룹을 찾을 수 있는지 용팀장이 확인 |

---

## Validation Sign-Off

- [ ] 모든 태스크에 `<automated>` verify 또는 Wave 0 의존성이 있다
- [ ] 샘플링 연속성: 자동 검증 없는 태스크가 3연속으로 나오지 않는다
- [ ] Wave 0 가 모든 MISSING 참조를 덮는다
- [ ] watch 모드 플래그 없음
- [ ] Feedback latency < 90초
- [ ] `nyquist_compliant: true` 를 frontmatter 에 설정

**Approval:** pending
