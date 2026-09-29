---
phase: 7
slug: thumb-coupang
status: approved
nyquist_compliant: true
wave_0_complete: false   # Wave 0 테스트·골든은 07-01/02/03 각 첫 태스크에서 생성 — 실행 전이라 false
created: 2026-09-29
---

# Phase 7 — Validation Strategy

> 회차별 검증 계약. 근거는 `07-RESEARCH.md` §Validation Architecture.
> 크레딧 0·쓰기 0 작업은 전부 자동 검증, 첫 썸네일 생성·쿠팡 `apply --commit` 은 blocking human checkpoint(L-01) 뒤에서만 실측한다.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 (`.venv-web` · `.venv` 두 venv) + `uat-verifier` 에이전트(UI) |
| **Config file** | `webapp/pytest.ini` (웹앱) · 스킬 쪽 설정 없음 |
| **Quick run command** | 웹: `.venv-web/bin/pytest webapp/tests/test_jobs.py webapp/tests/test_argv.py -q` · CLI: `.venv/bin/python3 -m pytest -q .claude/skills/coupang-candidates/scripts/ .claude/skills/bulsaja-thumbnail/scripts/` |
| **Full suite command** | `.venv-web/bin/pytest webapp/tests -q` + 위 CLI 명령 |
| **Estimated runtime** | quick ~2초 · full ~20초 (기준선: 웹 ~808 · 썸네일 205 · 쿠팡 36 passed) |

---

## Sampling Rate

- **After every task commit:** 해당 트랙 quick run
- **After every plan wave:** 두 스위트 전체 + `node --check webapp/static/board.js` + 트리 가드(`webapp/**` 에 `--skip-group-check`·`--min-margin`·`--min-orders` 0회, requests·eroomlib·PIL import 0)
- **Before first paid/irreversible checkpoint:** full suite green + 크레딧 0 스모크 evidence(썸네일 prep 1회 · 쿠팡 미리보기 1회) + uat-verifier PASS
- **Max feedback latency:** 20초

---

## Per-Task Verification Map

| Req | Behavior | Test Type | Automated Command | File Exists | Status |
|-----|----------|-----------|-------------------|-------------|--------|
| THUMB-01 | ② 행 선택 → 서버 재구성 · 미해소 제외 사유 · 그룹명 매핑 · 상한 | unit/route | `.venv-web/bin/pytest webapp/tests/test_routes_thumb.py -q` | ❌ W0 | ⬜ |
| THUMB-02 | `--max-credits` 누적 초과 exit 5 · 무플래그 불변 · `--only-pending` · `--expect-nick` exit 4 | unit(가짜 MCP·matrix) | `.venv/bin/python3 -m pytest -q .claude/skills/bulsaja-thumbnail/scripts/test_thumb_web.py` | ❌ W0 | ⬜ |
| THUMB-03 | `--estimate-out` 4갈래 + K×5/K×10 · 견적 표 렌더 · web_approval.json 스키마 | unit + TestClient | 위 둘 | ❌ W0 | ⬜ |
| CP-01 | 체인 단계 순서 · 비0 정지 · 단계명/stderr 꼬리 · summary | unit(가짜 stage 실행기) | `.venv/bin/python3 -m pytest -q .claude/skills/coupang-candidates/scripts/test_coupang_web.py` | ❌ W0 | ⬜ |
| CP-02 | 커밋 라우트 = 미리보기 id 하나 · 타이핑 불일치 400 · 첫 회 10 · 재커밋 400 · WRITE 가드 409 · 재gate 늘어남 exit 5 · `--pids-file` | unit/route | `.venv-web/bin/pytest webapp/tests/test_routes_coupang.py -q` + 위 | ❌ W0 | ⬜ |
| CP-03 | webapp 트리에 기준 플래그 0회 · cfg min_margin == 20 | tree grep | `.venv-web/bin/pytest webapp/tests/test_argv.py -q -k 쿠팡` | ❌ W0 | ⬜ |
| CP-04 | `--skip-group-check` 트리 0회 · 스냅샷 오류 → 비0 · 빈 페이지 조기종료 비0 · 불사자코드 2차 키 · 무플래그 골든 | unit | `test_coupang_web.py` | ❌ W0 | ⬜ |
| (todo) | `_alive` 좀비 → False | unit | `.venv-web/bin/pytest webapp/tests/test_jobs.py -q -k 좀비` | ❌ W0 | ⬜ |
| 실측 | 썸네일 prep 1회 · 쿠팡 미리보기 1회(1차 파일럿분이 `쿠팡그룹에이미있음`) | smoke(크레딧 0) | 체크포인트 플랜 | ❌ evidence | ⬜ |
| UI | 버튼·견적 표·미리보기 표·커밋 버튼 분리 | uat-verifier | — | — | ⬜ |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `.claude/skills/coupang-candidates/scripts/test_coupang_web.py` — 가짜 `CoupangMCP` + 무플래그 골든(CLI 수정 전 커밋에서 생성)
- [ ] `.claude/skills/bulsaja-thumbnail/scripts/test_thumb_web.py` — `test_thumb_prep.py` 몽키패치 관용구 재사용
- [ ] `webapp/tests/test_routes_thumb.py` · `webapp/tests/test_routes_coupang.py` — `jobs.spawn` 가짜(Phase 5 관례)
- 프레임워크 설치 없음

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 첫 썸네일 `apply --generate` 실행 승인 | THUMB-02/03 | 크레딧 소모(L-01) | 견적 표(건수·크레딧·계정·판매자상품코드) 확인 후 승인, 인계 명령을 Claude 세션이 `--max-credits` 로 실행 |
| 쿠팡 `apply --commit` 실행 승인(매번) | CP-02 | 되돌릴 수 없는 복사(L-01) | 미리보기 표·건수 타이핑 확인 후 승인, 첫 회 상한 10 |
| 커밋 버튼 색·위치 심미 | CP-02 | 시각 심미는 사람 몫 | uat-verifier 스크린샷 확인 |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 20s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-09-29 (plan-checker: 7개 플랜 전 태스크 automated 검증 확인)
