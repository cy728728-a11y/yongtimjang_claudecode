---
phase: 6
slug: market-update
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-09-26
---

# Phase 6 — Validation Strategy

> 회차별 검증 계약. 근거는 `06-RESEARCH.md` §Validation Architecture.
> 크레딧 0·쓰기 0 작업은 전부 자동 검증, 실제 마켓 쓰기·복원은 blocking human checkpoint(L-01) 뒤에서만 실측한다.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (`.venv-web/bin/pytest`) + `uat-verifier` 에이전트(격리 포트·DB 사본·spawn 가짜) |
| **Config file** | `webapp/pytest.ini` |
| **Quick run command** | `.venv-web/bin/pytest webapp/tests/test_detail_cli.py webapp/tests/test_market_cli.py -q` |
| **Full suite command** | `.venv-web/bin/pytest webapp/tests -q` |
| **Estimated runtime** | quick ~1초 · full ~15초 |

---

## Sampling Rate

- **After every task commit:** quick run
- **After every plan wave:** full suite + `node --check webapp/static/board.js` + 트리 가드(`webapp/**` 에 requests·eroomlib·PIL import 0)
- **Before first real market write checkpoint:** full suite green + uat-verifier PASS(게이트 화면까지) + 라이브 미리보기 쓰기 0 스모크 evidence
- **Max feedback latency:** 15초

---

## Per-Task Verification Map

| Req | Behavior | Test Type | Automated Command | File Exists | Status |
|-----|----------|-----------|-------------------|-------------|--------|
| MARKET-03 | `--backup-out` 접수 직전 ⓐ 파일 · 6키 · 불덮음 · 추가 호출 0 | unit(가짜MCP) | `pytest webapp/tests/test_detail_cli.py -k 백업` | ❌ W0 | ⬜ |
| MARKET-03 | 백업 실패 → generate 0회 | unit | 同 | ❌ W0 | ⬜ |
| MARKET-03 | 플래그 없음 골든 불변 | unit | `-k 골든` | ✅ | ⬜ |
| MARKET-03 | DetailArgv submit 은 `--backup-out` 항상 | unit | `pytest webapp/tests/test_argv.py -k Detail` | ❌ W0 | ⬜ |
| MARKET-03 | market_update ⓐ 없으면 backup_failed · ⓑ before_market 기록 | unit | `pytest webapp/tests/test_market_cli.py -k 백업` | ❌ W0 | ⬜ |
| MARKET-01 | preview confirm:true 0회 · 토큰 없는 성공 → 중단 · 확인모드 fast → exit 2 · 계정 → exit 4 | unit | `-k "미리보기 or 모드 or 계정"` | ❌ W0 | ⬜ |
| MARKET-01 | 스킵 분류(미업로드·AI상세없음·이미진행중) | unit | `-k 스킵` | ❌ W0 | ⬜ |
| MARKET-01 | commit 2단·새 토큰·taskId 선저장·폴링 매칭·exit 3·센티널 | unit(가짜시계) | `-k "접수 or 폴링"` | ❌ W0 | ⬜ |
| MARKET-02 | `--max-items` 필수 · 초과 exit 5 | unit | `-k max_items` | ❌ W0 | ⬜ |
| MARKET-02 | 게이트 전 commit 은 1건 강제 · 이상이면 거부 · 정상 후 N | integration(TestClient) | `pytest webapp/tests/test_routes_market.py` | ❌ W0 | ⬜ |
| MARKET-01/02 | kind 등록·가드 집합·caffeinate·exit3 done | unit | `pytest webapp/tests/test_jobs.py -k market` | ❌ W0 | ⬜ |
| MARKET-03 | 미리보기/결과 표에 ⓐ·ⓑ 경로 텍스트 | integration | `test_routes_market.py -k 경로` | ❌ W0 | ⬜ |
| MARKET-01 | 라이브 미리보기 쓰기 0(upload_tasks·work_progress 최대 taskId diff) | manual-live(크레딧 0) | 플랜 스모크 스크립트 | ❌ evidence | ⬜ |
| UI | 버튼·미리보기·게이트 패널·결과 표 | uat-verifier | — | — | ⬜ |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `webapp/tests/test_market_cli.py` — `test_detail_cli.py` 가짜MCP·가짜시계 하네스 복제, 시나리오 밖 도구 호출 = 즉시 실패
- [ ] `webapp/tests/fixtures/upload_tasks_real.json` — 실측 응답 익명화본
- [ ] `webapp/tests/test_routes_market.py`
- 프레임워크 설치 없음

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 첫 1건 반영 후 스토어 육안 확인(본문·상하단·기타 필드) | MARKET-02 | 네이버 접속은 사람 몫(CLAUDE.md) · 되돌릴 수 없는 쓰기 | 게이트 패널의 링크를 용팀장 브라우저로 열어 3항목 확인 후 판정 버튼 |
| 실제 `market_update(confirm:true)` 실행 승인 | MARKET-01 | 되돌릴 수 없는 실계정 쓰기(L-01) | 체크포인트에 건수·판매자상품코드·계정·백업 경로 표시 후 승인 |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
