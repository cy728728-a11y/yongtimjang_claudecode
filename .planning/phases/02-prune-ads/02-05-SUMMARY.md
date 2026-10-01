---
phase: 02-prune-ads
plan: 05
subsystem: UAT (격리 인스턴스 · 꺼진 소재 정리 화면 흐름)
tags: [uat, prune, isolation, playwright-cli, prune-03, safe-05, safe-07, flow-03, flow-06, eng-04, board-05, board-06]
requires:
  - "02-03 삭제 트랙 웹 슬라이스 (미리보기·커밋·재시도 라우트 · 조각 · prune.js)"
  - "02-04 정지 컬럼 · 오판정 1클릭"
  - "02-02 CT_DATA_ROOT · EROOM_WORKSPACE_TOML 격리 경로"
provides:
  - "webapp/tests/fixtures/prune_uat_seed.py — 실계정 교집합 0 확인 후에만 시드하는 격리 시드"
  - "02-UAT.md — U1~U11 PASS · 실데이터 지문 전/후 · uat-auto: done"
affects: [02-06]
tech-stack:
  added: []
  patterns: ["격리 인스턴스 UAT(별도 포트·tmp DB·tmp 데이터루트·tmp 감사·가짜 alias)", "실데이터 지문 전/후 diff"]
key-files:
  created:
    - webapp/tests/fixtures/prune_uat_seed.py
    - .planning/phases/02-prune-ads/02-UAT.md
  modified: []
decisions:
  - "uat-verifier 서브에이전트를 띄울 도구가 이 실행기에 없어 playwright-cli 로 같은 절차를 직접 돌렸다(오케스트레이터 지시의 대체 경로)"
  - "시드 잡은 prune.js 가 쓰는 것과 같은 htmx GET /jobs/<id>/result → #prune-body 로 띄웠다 — afterSwap 마운트까지 실제 경로"
  - "U8 의 409 는 성공 뒤 삭제 버튼이 disabled 로 남아 사람이 닿을 수 없으므로 페이지 훅 관제탑.요청으로 서버 계약을 확인했다"
metrics:
  duration: "약 15분"
  completed: 2026-10-01
  tasks: 2
  files: 2
---

# Phase 2 Plan 05: 꺼진 소재 정리 화면 UAT (격리 인스턴스) Summary

삭제 트랙과 보드 화면 흐름을 실데이터와 분리된 :8799 인스턴스에서 브라우저로 끝까지 눌러 봤다. U1~U11 전부 PASS 다. 커밋 2번은 가짜 alias 라 CLI 가 "자격증명 없음 — 건너뛴다" 로 끝났다. 그래서 네이버 API 호출은 0회다. 실데이터 지문은 전과 후가 같다.

## 무엇을 했나

**Task 1 — 격리 시드 + 기동 (6b31de6)**
- `prune_uat_seed.py` 는 이 순서로 돈다.
  1. `run_ads.py accounts` 를 깨끗한 env 로 불러 실계정 alias 를 받는다.
  2. `uat-a/b/c` 와 교집합이 있으면 아무것도 쓰지 않고 exit 1 한다.
  3. 격리 루트가 저장소나 실데이터 안이어도 exit 1 한다.
  4. CT_* 와 EROOM_WORKSPACE_TOML 을 import 전에 설정하고, 적용됐는지 다시 확인한 뒤 시드한다.
- 시드한 것:
  - 보드 result.json: 3계정, ② 12행과 ⑥ 27소재. productLive 는 True/False 를 섞고, 키 없는 상품을 1개 넣었다.
  - 잡 5개:
    - A: 3,000건 미리보기
    - B: 25시간 지나 만료된 미리보기
    - C: 9,000건이라 상한을 넘는 미리보기
    - E: 120건 미리보기
    - D: E 의 자식 커밋. 성공 100 · 실패 5 · 재시도소진 2 · 제외 5 · 새로 꺼짐 4 · uat-b 는 backup_failed
- 기동 로그에 `[기동] 고아 잡 0건 정리` 가 찍혔다. 루트 응답은 303 → 200 이다.

**Task 2 — 자동 판정 · 정리 · 불변 확인 (7e16dfd)**
- U1~U11 판정과 근거는 02-UAT.md 에 있다. 결과는 PASS 11 · FLAKY 0 · FAIL 0 · BLOCKED 0 이다.
- 격리 audit.jsonl 에 prune_commit 이 2줄 남았다. U7 재시도(대상 7)와 U8 커밋(대상 3000)이다.
- 격리 uvicorn 을 kill 했고 :8799 LISTEN 은 없다. 브라우저 세션도 닫았다. 운영 :8765 는 PID 45857 그대로다.
- 실데이터 지문을 전후로 비교했다. 항목은 webapp.db 잡 수 75 · paused-backup 7개와 목록 해시 · control-tower 없음 · runs/*/web 159 다. diff 결과 차이 0 이다.

## Deviations from Plan

**1. [지시된 대체 경로] uat-verifier 대신 playwright-cli 직접 실행**
- 이 실행기에는 서브에이전트 생성 도구가 없다. 오케스트레이터 지시대로 `~/.claude/uat/` 설정(헤드리스 Chrome)과 같은 방식으로 직접 돌렸다. 리포트 형식(판정 · 노이즈 후보 · 정리 결과 · 소스 변경)도 uat-verifier 와 같게 남겼다.

**2. [관찰] U8 의 409 확인 경로**
- 삭제가 성공하면 같은 조각의 삭제 버튼이 disabled 로 남는다. 그래서 사람이 같은 미리보기로 두 번 누를 수 없다. 이건 의도된 1겹 방어다.
- 서버 409(ENG-04)는 페이지 훅으로 같은 몸통을 보내 확인했다. 조각을 다시 받으면 "이미 삭제했다" 안내가 뜨고 삭제 영역이 없다.

## 노이즈 후보 (메인 세션 몫)

- 의도적으로 낸 409 에 대한 브라우저 `Failed to load resource: 409` 로그 (`/jobs/prune/(commit|retry)`)
- Tabulator `Table Not Initialized - getSelectedData` WARNING (보드 로드 때마다)

## 사람 몫 (① 시각 심미)

02-UAT.md "사용자 확인" 절에 3항목이 있다. 미리보기 표, 결과 표의 경고 띠, 정지 배지와 오판정 버튼 폭이다. 스크린샷은 `~/.claude/uat/uat-artifacts/02-prune-ads/` 에 있다.

## Known Stubs

없음.

## Threat Flags

없음. T-02-32~35 를 전부 완화했다. 실계정 교집합 검사, 격리 경로, 전후 지문 비교, git status 깨끗, 프로세스 종료를 확인했다.

## Self-Check: PASSED
- FOUND: webapp/tests/fixtures/prune_uat_seed.py
- FOUND: .planning/phases/02-prune-ads/02-UAT.md (uat-auto: done 1줄 · U1~U11 11행)
- FOUND: 6b31de6 · 7e16dfd
