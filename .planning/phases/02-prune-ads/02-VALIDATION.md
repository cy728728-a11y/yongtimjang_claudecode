---
phase: 2
slug: prune-ads
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-10-01
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. 근거: `02-RESEARCH.md` §Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (웹 `.venv-web`, CLI `.venv`) |
| **Config file** | `webapp/pytest.ini` |
| **Quick run command** | `.venv-web/bin/pytest webapp/tests/test_routes_prune.py webapp/tests/test_prune_cli.py webapp/tests/test_audit.py -q -p no:warnings` · `.venv/bin/python3 -m pytest -q .claude/skills/naver-ads-weekly/scripts/test_prune.py .claude/skills/naver-ads-weekly/scripts/test_ads_rules.py` |
| **Full suite command** | `.venv-web/bin/pytest webapp/tests -q -p no:warnings && .venv/bin/python3 -m pytest -q .claude/skills/naver-ads-weekly/scripts && bash webapp/tests/no_commit_guard.sh && bash webapp/tests/security_curl.sh` |
| **Estimated runtime** | ~20 seconds |

---

## Sampling Rate

- **After every task commit:** Quick run 두 줄 + `no_commit_guard.sh`
- **After every plan wave:** Full suite
- **Before `/gsd:verify-work`:** Full suite green + 실 `webapp.db`·실데이터루트 불변 확인
- **Max feedback latency:** 20 seconds

---

## Per-Task Verification Map

| Req | Behavior | Test Type | Automated Command | File Exists | Status |
|-----|----------|-----------|-------------------|-------------|--------|
| PRUNE-01 | 연동끊김만, 검수중/거부 제외 | unit + CLI | `pytest test_prune.py` · `test_prune_cli.py -k 연동끊김` | ✅ / ❌ W0 | ⬜ |
| PRUNE-02 | 백업 실패 → DELETE 0 · backup_failed 표시 | unit + route | `-k 백업실패` · `-k backup` | ❌ W0 | ⬜ |
| PRUNE-03 | preview-out 전 계정 전 행 | CLI | `test_prune_cli.py -k preview_out` | ❌ W0 | ⬜ |
| SAFE-04 | 잡별 백업 태그로 첫 백업 보존 | unit | `-k 백업태그` | ❌ W0 | ⬜ |
| SAFE-05 | 재조회 제외 소재별 사유 · 대상 밖 DELETE 0 | unit | `-k excluded` | ❌ W0 | ⬜ |
| SAFE-06 | 커밋 `--only-ads` == 미리보기 산출물 · 무플래그 불변 | unit + CLI | `-k only_ads` · `-k 무플래그` | ❌ W0 | ⬜ |
| SAFE-07 | 상한 초과 → 미리보기 표시 · 커밋 400 · CLI exit 2 | route + unit | `-k 상한` | ❌ W0 | ⬜ |
| FLOW-03 | 24h 초과 커밋 400 | route | `-k 24시간` | ❌ W0 | ⬜ |
| FLOW-06 | 실패분만 재시도 · typed=실패수 | route | `-k 재시도` | ❌ W0 | ⬜ |
| FLOW-07 | WRITE_KINDS 종료마다 감사 1줄 · 중복 0 · 테스트 격리 | unit | `test_audit.py` · `test_jobs.py -k 감사` | ❌ W0 | ⬜ |
| ENG-04 | 같은 미리보기 두 번째 커밋 409 | unit + route | `-k 멱등` | ❌ W0 | ⬜ |
| ENG-05 | 기동 시 고아 정리 · 테스트 실DB 불변 | unit | `-k 기동` | ❌ W0 | ⬜ |
| ENG-06 | prune_commit argv caffeinate -i | unit | `test_argv.py -k caffeinate` | ✅ 확장 | ⬜ |
| BOARD-05 | 꺼진 소재 통계 ②~⑤ 미포함 · ⑥ 사유 · 광고정지 배지 | unit | `test_ads_rules.py -k 꺼진` · `test_board.py -k 정지` | ❌ W0 | ⬜ |
| BOARD-06 | 오판정 POST append · 최신 줄 승 · GET 쓰기 0 | route | `test_board.py -k 오판정` · `security_curl.sh` | ❌ W0 | ⬜ |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `webapp/tests/test_prune_cli.py`
- [ ] `webapp/tests/test_routes_prune.py` (쿠팡 라우트 테스트 픽스처 복제)
- [ ] `webapp/tests/test_audit.py`
- [ ] conftest autouse — DB·감사 경로 tmp 고정(lifespan 이전)
- [ ] `test_prune.py` · `test_ads_rules.py` 확장

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 미리보기·커밋·재시도 화면 흐름(수천 행) | PRUNE-03 · FLOW-06 | 브라우저 | uat-verifier(목 산출물, 격리 인스턴스) |
| 첫 실제 삭제 | PRUNE-02 · SC-1 | 되돌릴 수 없는 쓰기(L-01) | 용팀장 승인 후 실행 — 건수·계정·샘플 제시 |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 20s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
