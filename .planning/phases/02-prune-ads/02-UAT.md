---
status: complete
verdict: PASS (PASS 11 · FLAKY 0 · FAIL 0 · BLOCKED 0)
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

판정은 playwright-cli(헤드리스 Chrome, 세션 `uat-prune`)로 냈다. 이 실행기에는 서브에이전트를 띄우는 도구가 없어서 `uat-verifier` 를 부르지 못했다. 그래서 `~/.claude/uat/` 참고서와 같은 방식으로 직접 돌렸다. 브라우저는 격리 :8799 에만 접속했다. 콘솔 로그에 8765 문자열 0건, 소스 수정 0건(`git status` 깨끗).

시드 잡은 실제 버튼이 쓰는 경로와 같은 `htmx.ajax GET /jobs/<id>/result → #prune-body` 로 띄웠다. prune.js 의 `htmx:afterSwap` 마운트도 그대로 탄다. 클릭·입력은 전부 실제 포인터·키보드 이벤트(`click`·`fill`·`mousewheel`)로 했다.

| ID | 항목 | 판정 | 근거 |
|----|------|------|------|
| U1 | 보드(uat-prune)에 '꺼진 소재 정리' 섹션 · 계정 체크박스 3개 · 미리보기 버튼 활성 | PASS | h2 "꺼진 소재 정리" · 체크박스 `uat-a/uat-b/uat-c` · 버튼 disabled=false "꺼진 소재 정리 미리보기 — 광고 쓰기 0" |
| U2 | 잡 A: 계정 요약 · 3,000행 끝까지 스크롤 · 계정 그룹 접힘/펼침 · 컬럼 7개 · `<b>` 가 글자로 | PASS | 요약 uat-a 2000(거부 12 · 검수중 5) · uat-b 1000(검수중 3) · uat-c "건너뜀: 자격증명 없음" + "건너뛴 계정은 안 본 것이다". Tabulator 3,000행, 두 그룹 기본 접힘 → 화살표 클릭으로 펼침. 마우스 휠로 마지막 행 `nad-uat-b-00999` 까지 도달(scrollTop+clientHeight=scrollHeight). 컬럼 7개 = 계정·광고그룹·소재id·상품id·상품명·정지사유·마지막 변경(캠페인 없음). 그리드 안 `<b>` 요소 0개, 상품명에 `<b>굵게</b>` 가 글자로 보인다. 중국어 상품명 8셀 정상. 스크린샷 `U2-preview-A.png` |
| U3 | 커밋 details 기본 접힘 · 버튼 다른 색 · 빈 입력 → "숫자로 직접 입력" · 잡 미생성 | PASS | details open=false, summary "꺼진 소재 삭제 실행 (되돌릴 수 없음 — 펼쳐서 확인)". 삭제 버튼 class=contrast, 배경 rgb(24,28,37)이고 미리보기 버튼은 rgb(1,114,173). 빈 입력으로 클릭하면 "지울 건수를 숫자로 직접 입력해라 — 입력 없이는 지우지 않는다". 잡 수 5 → 5 |
| U4 | 틀린 건수(2999) → 409 문구 · 잡 미생성 · 입력칸 비워짐 | PASS | "꺼진 소재 삭제 작업을 못 띄웠다 (409) — 화면이 본 건수(2,999)와 지금 지울 건수(3,000)가 다르다 — 다시 확인해라". 입력값 "" · 잡 수 5 → 5 · 서버 로그 POST /jobs/prune/commit 409 |
| U5 | 잡 B 만료 안내 · 삭제 영역 없음 / 잡 C 상한 초과 · 삭제 영역 없음 | PASS | B: "미리보기가 24시간이 지났다 — 다시 미리보기해라." 이고 details·버튼·입력칸이 없다. C: "상한 초과 — 9000건 > 상한 8000건. 계정을 골라 나눠 미리보기해라. 앞에서 잘라 지우지 않는다." 이고 역시 삭제 영역이 없다. 스크린샷 `U5-expired-B.png` · `U5-overlimit-C.png` |
| U6 | 잡 D: 성공 100 · 실패 7 · 제외 5행 한국어 사유 · 새로 꺼진 4건 · uat-b 백업 실패 · 실패·제외가 위 | PASS | "성공 100 · 이미없음 0 · 실패 7 · 재조회 제외 5". "미리보기 이후 새로 꺼진 4건 — 이번엔 안 지움". 계정표는 uat-b("백업을 못 써서 이 계정은 한 건도 지우지 않았다")가 uat-a 위에 온다. 실패표 7행(실패 5 + 재시도소진 2, 오류 `<b>` 는 글자로). 제외표 5행: "다시 켜짐" 3 · "재조회에 없음(이미 삭제됐거나 조회 실패)" 2. 성공 행은 나열하지 않아 실패·제외가 위로 온다. 스크린샷 `U6-result-D.png` |
| U7 | 잡 D 재시도: 틀린 수 409 / 7 → 새 잡 → uat-a 자격증명 없음 건너뜀 | PASS | 6 입력 → "실패분 재시도 작업을 못 띄웠다 (409) — 화면이 본 건수(6)와 지금 재시도할 건수(7)가 다르다", 입력칸 비워짐, 잡 수 불변. 7 입력 → 잡 `1a8b07c9…` (prune_commit, parent=E, `--account uat-a`). `--only-ads` 파일은 실패 7개 adId 정확히. 로그 "[uat-a] 자격증명 없음 — 건너뛴다" · done/0. 결과 조각 "uat-a … 건너뜀: 자격증명 없음" |
| U8 | 잡 A 3000 → 커밋 잡 → 결과 표 → 다시 3000 → 409 "이미 삭제" | PASS | 3000 입력 → 잡 `24daddda…` (`--account uat-a uat-b`) done/0 → 결과 표 두 계정 "건너뜀: 자격증명 없음". 성공 뒤 삭제 버튼은 disabled 로 남는다(1겹). 조각을 다시 받으면 "이 미리보기로 이미 삭제했다 — 실패분 재시도나 새 미리보기를 써라." 이고 삭제 영역이 없다(2겹). 페이지 훅 `관제탑.요청` 으로 같은 3000 을 POST 하면 409 "이 미리보기로 이미 삭제했다"(3겹 · ENG-04). 잡 수 7 불변 |
| U9 | 보드 정지 컬럼: 광고 정지 배지 · "?" · "연동끊김 N · 거부 M" | PASS | ⑥ 15행. productLive 전부 false 인 상품 8개에 `<mark>광고 정지</mark>` 가 붙었다. 라이브 상품 6개는 배지 없음. productLive 키 없는 uat-a 70000054 는 "?". 사유 요약은 "연동끊김 1 · 검수중 1" / "거부 1 · 연동끊김 1" 형식. 스크린샷 `U9-board-stop-column.png` |
| U10 | 오판정 토글 → 새로고침 유지 → 해제 → 새로고침 해제 | PASS | uat-a 70000050 "오판정" 클릭 → "오판정 ✓" → reload 후 유지 → 다시 클릭 → "오판정" → reload 후 해제. 행 선택은 안 됨(stopPropagation). `misjudged.jsonl` 2줄(on true → false, 규칙 "⑥") |
| U11 | 전 과정 콘솔 오류 0 | PASS | JS 예외 0. 콘솔 ERROR 는 두 종류뿐이다. ① favicon 404 1건 — 허용목록에 이미 있다. ② U4·U7·U8 에서 일부러 낸 409 응답의 브라우저 자동 로그 3건(`Failed to load resource: 409`) — 의도한 응답이다. WARNING 은 Tabulator "Table Not Initialized"(getSelectedData) — 보드 로드 때마다 1건 |

**전체 판정: PASS** (PASS 11 · FLAKY 0 · FAIL 0 · BLOCKED 0)

### 관찰(결함 아님)

- P3 · U2: 그룹 머리글 글자를 눌러도 안 펼쳐지고 ▸ 화살표를 눌러야 펼쳐진다(Tabulator 기본 `groupToggleElement: "arrow"`). 명세 위반은 아니고 사용성 메모다.
- U8: 삭제 성공 뒤 같은 조각의 삭제 버튼이 disabled 로 남는다. 그래서 사람은 409 까지 갈 수 없다. 409 는 페이지 훅으로 서버 계약을 직접 확인했다.

## 화면 밖 증거

- 격리 `audit.jsonl` 의 `prune_commit` 줄은 **2줄**이다(FLOW-07). U7 은 `1a8b07c9…` 대상수 7 · 계정 [uat-a], U8 은 `24daddda…` 대상수 3000 · 계정 [uat-a, uat-b] 다. 둘 다 성공 0 · 종료코드 0 · done.
- 네이버 광고 API 호출 0. 두 커밋 잡 모두 CLI 로그가 "자격증명 없음 — 건너뛴다" 로 끝났다.
- 기동 reap: `[기동] 고아 잡 0건 정리` (격리 DB).

## 정리 결과

- 격리 uvicorn PID 46229 를 kill 했다. `lsof -nP -iTCP:8799 -sTCP:LISTEN` 출력은 없다.
- 브라우저 세션 `uat-prune` 을 close 했다. `playwright-cli list` 결과는 "(no browsers)".
- 운영 :8765 는 PID 45857 그대로다. 접속도 재시작도 하지 않았다.
- 격리 데이터(`<S>`)는 scratchpad 에 남겼다. 세션 종료 때 사라진다. 실데이터 쪽에 남은 시드는 없다.

## 실데이터 지문(후)

| 항목 | 전 | 후 |
|------|----|----|
| 실 webapp.db 잡 수 · 최근 종료 | `75 \| 2026-09-30T20:07:13+09:00` | `75 \| 2026-09-30T20:07:13+09:00` |
| 실 paused-backup 파일 수 · 목록 지문 | 7 · a5241c12… | 7 · a5241c12… |
| 실 control-tower/audit.jsonl | 없음 | 없음 |
| 실 runs/*/web 파일 수 | 159 | 159 |
| 실 runs 아래 uat-* 회차 | — | 0 |

`diff fp_before fp_after` 결과 차이 0. **실데이터 쓰기 0.**

## 노이즈 후보 (허용목록 추가는 메인 세션 몫)

- `Failed to load resource: the server responded with a status of 409 (Conflict) @ */jobs/prune/(commit|retry)` — 건수 불일치·재요청 거부를 일부러 시험할 때 나는 브라우저 자동 로그
- `[WARNING] Table Not Initialized - Calling the getSelectedData function before the table is initialized` (tabulator-6.5.3) — 보드 로드 때마다 1건. 기능 영향 없음

## 검증 중 소스 변경

없음 (`git status --short` 깨끗).

## 사용자 확인 (① 시각 심미만)

스크린샷은 `~/.claude/uat/uat-artifacts/02-prune-ads/` 에 있다. 실데이터 화면은 02-06 에서 운영 서버를 재시작한 뒤 본다.

1. 미리보기 표(`U2-preview-A.png`): 계정 요약 표와 Tabulator 그룹 머리글이 읽기 편한가
2. 결과 표(`U6-result-D.png`): 실패 7 강조와 "새로 꺼진 4건" 경고 띠의 색·무게가 적당한가
3. 보드 정지 컬럼(`U9-board-stop-column.png`): "광고 정지" 배지와 사유 요약이 64px 칸에서 읽히는가, "오판정 ✓" 가 56px 에 들어가는가

<!-- uat-auto: done -->
