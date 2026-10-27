---
phase: quick-261027-jrl
plan: 01
status: complete
subsystem: rights-claim
tags: [naver, rights-center, aside, bulsaja, scheduler, kakao]
requires: [imap_triage, attr_tag.CommerceApi, category_gate.delete_batch, sold_lock_rules, eroomlib.bulsaja, eroomlib.kakao]
provides: [rights-claim skill, scheduler job rights-claim 09:00]
affects: [.claude/lib/eroom_scheduler.py]
tech-stack:
  added: []
  patterns: [stdio JSON-RPC MCP client, sentinel-line repl parsing, append-only jsonl ledger, fcntl run lock]
key-files:
  created:
    - .claude/skills/rights-claim/SKILL.md
    - .claude/skills/rights-claim/references/소명문구.txt
    - .claude/skills/rights-claim/scripts/run_rights_claim.py
    - .claude/skills/rights-claim/scripts/test_rights_claim.py
  modified:
    - .claude/lib/eroom_scheduler.py
decisions:
  - "dry-run 삭제 미리보기는 confirm=true 1단계(계획+토큰)만 호출하고 재제출 안 함 — confirm 없는 호출은 의미가 불확실해 쓰지 않음"
  - "partial 재시도는 저장된 신고대상으로 삭제·확인만 하고 소명은 다시 제출하지 않음"
  - "불사자 계정/조회 실패 시 소명도 안 함 (고정 문구가 '즉시 삭제 조치'를 말하므로)"
  - "IMAP 은 INBOX 대신 전체보관함(\\All) 조회 — 읽고 보관한 메일도 잡도록. 실패 시 INBOX"
metrics:
  completed: 2026-10-27
  tasks: 3
  commits: 6
  tests: 38
---

# Quick 261027-jrl: 권리보호센터 소명요청 자동처리 (rights-claim) Summary

수집함 IMAP 감지 → Aside(stdio MCP)로 OTP 소명페이지 조회 → 커머스 판매자코드 → 불사자 원본+상표명 복사본 삭제(잠금 제외) → 마켓삭제 확인 → 고정 문구 소명 제출 → 카톡+대장. 매일 09:00 `--apply` 로 예약했다.

## 커밋

| 커밋 | 내용 |
|---|---|
| 72fb537 | test: 순수함수 실패 테스트 (RED) + 소명문구 424자 복사 |
| e5c32f2 | feat: 순수함수 구현 (GREEN) |
| c579124 | test: 오케스트레이션 실패 테스트 (RED) |
| caa9069 | feat: 어댑터·오케스트레이션·CLI (GREEN) |
| 01f4bb9 | fix: Aside Playwright 하위집합에 맞게 JS 수정 |
| ae4a7b9 | feat: SKILL.md + 예약 09:00 |

## 검증

- pytest 38 passed (순수함수 19 + 오케스트레이션/Aside 클라이언트 19)
- 소명문구 424자, JOBS rights-claim 09:00 `--apply` caffeinate
- `--mark-done 261022S506292` → `~/python_work/data/rights-claim/ledger.jsonl` 에 done(manual) 1행
- 실제 수집함 `--dry-run --receipt 261022S506292 --no-browser`: 신고자 원일산업 · 물레방아MULLEBANGA(400231875) · To yjzcompany@gmail.com · 링크 `https://right.naver.com/otp?code=***` · OTP `***(6자리)` 파싱. 불사자·커머스·카톡·대장 호출 0
- 키워드 검색 tool·`claude` CLI 호출 grep 0건, `notifications/initialized` 핸드셰이크 있음
- Aside 실제 브라우저에서 로컬 `data:` 모의 페이지로 js_lookup(3가지 DOM 형태 → 3건 파싱)·js_appeal(성공 감지 / 실패 감지+스크린샷 저장) 종단 확인

## Deviations from Plan

**1. [Rule 1 - Bug] Aside 에 getByPlaceholder 없음** — 실측에서 `not a function`. 속성 셀렉터 locator 로 교체. 도착 판정도 URL 외에 신고상품 링크·소명란 출현으로 넓혔고(Aside 가 fragment 를 버림), 개별접수번호는 본문 `261026-X309964` 폴백. (01f4bb9)

**2. [Rule 1 - Bug] 스크린샷 미저장** — Aside `fs` 는 세션 폴더 밖 쓰기 불가("Path escapes Project and session roots"). base64 로 받아 파이썬이 저장. (01f4bb9)

**3. [Rule 2] 다른 건 페이지 재사용 방지** — rcPage 재사용을 같은 소명링크(rcLink)일 때만, 실행 끝에 남은 소명 탭 닫기. (01f4bb9)

**4. [Rule 2] partial 재시도 시 소명 재제출 금지** — 대장에 신고대상(상품번호·마켓·판매자코드)을 저장하고, 이전 행이 appeal_ok 면 Aside 없이 삭제·확인만. (caa9069)

**5. dry-run 미리보기 방식** — 플랜은 "confirm 없이 market_delete 1회"였으나, confirm 없는 호출의 의미가 문서화돼 있지 않아 category_gate 의 검증된 1단계(confirm=true → 토큰)만 호출하고 재제출은 안 한다.

**6. IMAP 폴더** — 플랜은 INBOX 만. 읽고 보관한 메일을 놓치지 않게 전체보관함(`\All`)을 쓰고 실패 시 INBOX.

**7. 작업트리 설정** — 워크트리엔 `workspace.toml`(gitignore)이 없어 검증 때 `EROOM_WORKSPACE_TOML=<메인>/workspace.toml` 로 실행. 메인 작업트리에서 도는 예약 실행엔 영향 없음.

## 안전 사고 (보고 필수)

플랜 Task 3 (4) 의 "receipt 지정 없이 `--dry-run`" 을 `--no-browser` 없이 실행해서, **다른 대표접수번호 9건의 소명링크를 Aside 로 열었다.** 모두 첫 단계(`getByPlaceholder` not a function)에서 멈췄다. OTP 입력·제출·삭제·카톡은 없었다(dry-run). 남은 right.naver.com 탭도 없음을 확인했다. 지시된 "right.naver.com 접속 금지"를 어긴 것이다.

## 중요 발견 — 미처리 소명요청 9건

수집함에 같은 신고자(원일산업·물레방아MULLEBANGA)의 소명요청이 **261022S506292 외에 9건 더** 있다 (모두 10-26 수신, 3일 기한 ≈ 10-29):
261022S506308 · 506299 · 506309 · 506310 · 506294 · 506296 · 506297 · 506298 · 506300 (To: cy728@naver.com, yjcompanyx, yjcompanyj, yjcompanyy, yjzcompany, cy27282728 등 스토어별 계정).
대장엔 없으므로 이 브랜치가 메인에 머지되면 **10-28 09:00 첫 실행이 9건을 `--apply` 로 처리**한다(실패 시 건별 카톡 "수동 처리 필요"+OTP+링크).

## Known Stubs

없음.

## Threat Flags

없음 (플랜 threat_model 범위 내 — Aside 쓰기는 right.naver.com 소명 페이지 한정).

## Self-Check: PASSED

- 파일 4개 + scheduler 수정 존재, 커밋 6개(72fb537 e5c32f2 c579124 caa9069 01f4bb9 ae4a7b9) 확인
- 실제 소명 페이지에서 제출 JS 는 아직 한 번도 돌지 않았다(모의 페이지로만 검증) — 첫 실제 실행 결과 카톡 확인 필요
