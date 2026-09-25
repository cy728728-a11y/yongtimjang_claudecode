---
phase: 5
slug: core-value
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-09-25
---

# Phase 5 — Validation Strategy

> 회차별 검증 계약. 근거는 `05-RESEARCH.md` §Validation Architecture.
> 크레딧 0 작업은 전부 자동 검증, 크레딧 소비(5건 실탄)는 blocking human checkpoint(L-01) 뒤에서만 실측한다.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (`.venv-web/bin/pytest`) + 헤드리스 크롬 CDP 하네스(`webapp/tests/*_cdp.sh`) + `uat-verifier` 에이전트 |
| **Config file** | `webapp/pytest.ini` |
| **Quick run command** | `.venv-web/bin/pytest webapp/tests/test_detail_cli.py webapp/tests/test_banner.py -q` |
| **Full suite command** | `.venv-web/bin/pytest webapp/tests -q` |
| **Estimated runtime** | quick ~3초 · full ~15초 |

---

## Sampling Rate

- **After every task commit:** quick run
- **After every plan wave:** full suite (+ `test_argv.py` 트리 가드: `webapp/**` 에 requests·eroomlib·PIL import 0)
- **Before first paid checkpoint:** full suite green + uat-verifier(견적 화면까지, 크레딧 0)
- **Max feedback latency:** 15초

---

## Per-Task Verification Map

| Req | Behavior | Test Type | Automated Command | File Exists | Status |
|-----|----------|-----------|-------------------|-------------|--------|
| DETAIL-01 | `--inputs` 면 collect_images 미호출 · imageUrls = 입력 | unit(가짜 MCP) | `pytest webapp/tests/test_detail_cli.py -k 입력` | ❌ W0 | ⬜ |
| DETAIL-01 | 관문(D-02): 낡은 확인·스킵·미판정·<2장 → 예외, 라벨우선·10장 자르기 | unit | `pytest webapp/tests/test_banner.py -k 상세입력` | ✅ 파일 | ⬜ |
| DETAIL-02 | sc = max(2,min(n,10)) | unit | `-k 장수` | ❌ W0 | ⬜ |
| DETAIL-03 | imageUrls·sectionCount 동시 | unit | `-k 동시` | ❌ W0 | ⬜ |
| DETAIL-04 | 예상장수 불일치/비정수 → exit 2 + taskId 보존 | unit | `-k 불일치` | ❌ W0 | ⬜ |
| DETAIL-05 | estimate-only generate 0회 · 견적 JSON · max-credits 초과 exit 5 · 접수 라우트는 부모 targets 만 | unit+route | `-k 견적` / `test_routes_jobs.py -k detail` | ❌ W0 | ⬜ |
| DETAIL-06 | deadline → exit 3(실패 아님) · 조기종료 버그 회귀 · `_finish` 해석 | unit | `-k 폴링미완` / `test_jobs.py -k detail` | ❌ W0 | ⬜ |
| DETAIL-07 | `--poll-only` 체크포인트 재개 · poll 라우트 부모 체인 | unit+route | `-k 이어서` | ❌ W0 | ⬜ |
| D-12 | 웹앱·CLI 기작업 규칙 교차 일치 | unit | `-k 기작업_규칙_일치` | ❌ W0 | ⬜ |
| L-04 | 플래그 없는 호출 골든 불변 | unit | `-k 플래그없음` | ❌ W0 | ⬜ |
| L-06 | `--expect-nick` 불일치 exit 4 · detail kind 계정 사전점검 | unit | `test_jobs.py -k 계정` | ✅ 파일 | ⬜ |
| D-03 | 확인된 상품에도 재확인 버튼 | route(HTML) | `test_routes_banner.py -k 다시확인` | ✅ 파일 | ⬜ |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `webapp/tests/test_detail_cli.py` — 가짜 MCP · `sys.modules` 스텁 로더 · 플래그 없음 골든(패치 **전** 생성)
- [ ] `webapp/tests/fixtures/detail_inputs_*.json` — 익명화(`zz*` 코드, `zzcdn.example`)
- [ ] `test_banner.py` `상세입력목록` · `test_routes_jobs.py` detail 라우트 · `test_jobs.py` kind 등록/가드

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 5건 실탄 접수→폴링, 브라우저 닫고 완주 | SC-1 / DETAIL-05~07 | 크레딧 소비(L-01 ①) — 사람 승인 필수 | 견적 보고 → 승인 → 접수 → 탭 닫기 → 재오픈 시 결과 표 확인(uat-verifier 가 재오픈 판정) |
| 두 번째 견적 접수 0건 | SC-3 | 실탄 결과가 전제(크레딧 0) | 같은 대상으로 견적 잡 재실행 → 실제 접수 0 |
| aiImageGenerated 기록 실측 | D-13 | 실탄 결과가 전제 | 견적 잡의 workdata 재조회 결과 확인 |
| 결과물 워터마크 잔존 여부 | specifics | 시각 심미 | 5건 결과를 사람이 눈으로 확인 |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
