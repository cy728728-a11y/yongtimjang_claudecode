---
status: testing
phase: 02-prune-ads
plan: 05
source: [02-03-SUMMARY.md, 02-04-SUMMARY.md]
started: 2026-10-01
---

# Phase 02 UAT — 꺼진 소재 정리 화면 흐름 (격리 인스턴스)

## 실데이터 지문(전)

쓰기 0 명령으로만 쟀다. 운영 :8765 는 PID 45857 로 떠 있었고 손대지 않았다.

| 항목 | 명령 | 값 |
|------|------|----|
| 실 webapp.db 잡 수 · 최근 종료 | `sqlite3 webapp.db "select count(*), max(ended_at) from jobs"` | `75 \| 2026-09-30T20:07:13+09:00` |
| 실 paused-backup 파일 수 | `ls ~/python_work/data/naver-ads/paused-backup \| wc -l` | 7 |
| 실 paused-backup 목록 지문 | `ls -la …/paused-backup \| shasum` | `a5241c12b968b153c3bd8d3fedbd409e93f6d829` |
| 실 paused-backup 최신 mtime | `stat` | 2026-08-30 00:15:58 (delete_progress_pogeunae_20260830.jsonl) |
| 실 control-tower/audit.jsonl | `ls -la ~/python_work/data/control-tower/` | 없음(디렉터리 자체 없음) |
| 실 runs/*/web 파일 수 | `ls ~/python_work/data/naver-ads/runs/*/web \| wc -l` | 159 |

## 환경

| 항목 | 값 |
|------|----|
| 포트 | 8799 (127.0.0.1 · --workers 1) |
| 토큰 | CT_DEV_TOKEN=uat-prune → `http://127.0.0.1:8799/?t=uat-prune` |
| `<S>` | 세션 scratchpad `/uat-prune` (저장소·실데이터 밖) |
| CT_DB_PATH | `<S>/uat.db` |
| CT_DATA_ROOT / EROOM_WORKSPACE_TOML | `<S>/data` / `<S>/workspace.toml` (`data_root = <S>/data`) |
| CT_AUDIT_PATH · CT_JOB_LOG_DIR | `<S>/audit.jsonl` · `<S>/logs` |
| 계정 | 가짜 alias `uat-a` · `uat-b` · `uat-c`. 시드 전에 `run_ads.py accounts` 로 실계정 alias 를 받아 교집합 0 을 확인했다 |
| 기동 로그 | `[기동] 고아 잡 0건 정리` (격리 DB 에서 reap 이 돌았다 — ENG-05 화면 밖 증거) |
| 루트 응답 | `GET /?t=uat-prune` → 303 → `/` 200 |

**왜 커밋을 눌러도 API 가 0회인가.** 커밋 라우트는 `--account uat-a uat-b` 를 넘긴다. CLI 는 `nvad.load_accounts()` 에서 이 alias 를 못 찾으니 "자격증명 없음 — 건너뛴다" 로 끝난다. `--account` 가 비는 경로가 있더라도 2차 방어가 있다. 실계정은 격리 회차에 prep 디렉터리가 없어 "prep 없음 — 건너뛴다" 로 빠진다.

## 시드 잡

| 잡 | id | 종류 | 상태 | 내용 |
|----|----|------|------|------|
| A | 9084bb0f-9fcb-478d-903c-ae17daa118bb | prune_preview | done/0 · 지금 | total 3,000 (uat-a 2,000 · uat-b 1,000 · keep 거부/검수중 · uat-c 자격증명 없음) · 상품명에 한국어·중국어·`<b>` |
| B | 5f80adfc-ab7b-4750-b947-d239be94b66d | prune_preview | done/0 · 25시간 전 | total 10 (만료) |
| C | 61b5be36-5334-4483-814b-6d23506a22ac | prune_preview | done/0 · 지금 | total 9,000 (상한 8,000 초과) |
| E | 6011e8df-b971-4686-abfd-66b0131f3128 | prune_preview | done/0 · 1시간 전 | total 120 (D 의 부모) |
| D | bec5f328-0234-4c93-8cf4-b371fc74e701 | prune_commit | done/0 · 30분 전 | uat-a 성공 100 · 실패 5 · 재시도소진 2 · 제외 다시_켜짐 3 + 재조회에_없음 2 · new_since_preview 4 / uat-b aborted backup_failed |

결과 조각 URL 은 `/jobs/<id>/result` 다. 보드 URL 은 `/?run_dir=uat-prune` 다.

## UAT 항목

| ID | 항목 | 판정 | 근거 |
|----|------|------|------|
| U1 | 보드(uat-prune)에 '꺼진 소재 정리' 섹션 · 계정 체크박스 3개 · 미리보기 버튼 활성 | 미판정 | |
| U2 | 잡 A: 계정 요약 · 3,000행 끝까지 스크롤 · 계정 그룹 접힘/펼침 · 컬럼 7개 · `<b>` 가 글자로 | 미판정 | |
| U3 | 커밋 details 기본 접힘 · 버튼 다른 색 · 빈 입력 → "숫자로 직접 입력" · 잡 미생성 | 미판정 | |
| U4 | 틀린 건수(2999) → 409 문구 · 잡 미생성 · 입력칸 비워짐 | 미판정 | |
| U5 | 잡 B 만료 안내 · 삭제 영역 없음 / 잡 C 상한 초과 · 삭제 영역 없음 | 미판정 | |
| U6 | 잡 D: 성공 100 · 실패 7 · 제외 5행 한국어 사유 · 새로 꺼진 4건 · uat-b 백업 실패 · 실패·제외가 위 | 미판정 | |
| U7 | 잡 D 재시도: 틀린 수 409 / 7 → 새 잡 → uat-a 자격증명 없음 건너뜀 | 미판정 | |
| U8 | 잡 A 3000 → 커밋 잡 → 결과 표 → 다시 3000 → 409 "이미 삭제" | 미판정 | |
| U9 | 보드 정지 컬럼: 광고 정지 배지 · "?" · "연동끊김 N · 거부 M" | 미판정 | |
| U10 | 오판정 토글 → 새로고침 유지 → 해제 → 새로고침 해제 | 미판정 | |
| U11 | 전 과정 콘솔 오류 0 | 미판정 | |
