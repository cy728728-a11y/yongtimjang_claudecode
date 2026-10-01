---
phase: 02-prune-ads
plan: 04
subsystem: webapp 보드 투영 (board.py · routes/board.py · board.js)
tags: [board, board-05, board-06, sc-4, misjudged, stop-badge, d-12, d-13, d-14]
requires:
  - "02-01 규칙⑥ 행의 statusReason · editTm · productLive"
provides:
  - "board.fold_products 행 필드 정지사유 {라벨: 건수} · 광고정지 True|False|None"
  - "board.정지사유_라벨 (AD_ABNORMAL_INTERLOCK→연동끊김 · AD_UNDER_REVIEW→검수중 · AD_DISAPPROVED→거부 · 그 외 원문 · None→미상)"
  - "POST /board/misjudged {run_dir, key, rule, memo, on} → <회차>/misjudged.jsonl append"
  - "GET / 행 필드 오판정: bool (키별 최신 줄)"
  - "board.js 정지 컬럼 · 오판정 버튼 컬럼"
affects: [02-06]
tech-stack:
  added: []
  patterns: ["투영에 얹기(join.attach 뒤)", "append-only 사람 기록 + 최신 줄 승리", "formatter 는 DOM 노드 반환(innerHTML 금지)"]
key-files:
  created: []
  modified:
    - webapp/board.py
    - webapp/routes/board.py
    - webapp/static/board.js
    - webapp/tests/test_board.py
decisions:
  - "오판정 줄의 규칙 값은 그 행의 rules 문자열 전체(예 '②③') — 과기록이 누락보다 낫다(RESEARCH Open Q3). rule 은 ①~⑥ 기호 1~12자만"
  - "⑥ 만 가진 소재 슬롯은 SUM_FIELDS 합산을 건너뛴다. ②~⑤ 와 겹친 소재는 기존대로(실데이터에선 겹치지 않음)"
  - "statusReason 이 없으면 정지사유 라벨 '미상'으로 센다(지어낸 라벨 금지 · 원문 우선)"
  - "새 두 컬럼(정지 64 · 오판정 56)을 넣으면서 숫자 열을 깎아 고정폭 합 1,270 을 유지하고 columnDefaults.headerTooltip 으로 잘린 머리글을 hover 로 읽게 했다"
  - "오판정 POST 는 JSON 본문만 받는다(Pydantic 바디 → 422). htmx 폼 경로가 없어 _요청_풀기 불필요"
metrics:
  duration: "약 25분"
  completed: 2026-10-01
  tasks: 2
  files: 4
---

# Phase 2 Plan 04: 정지 소재 표시 · 오판정 1클릭 Summary

보드가 꺼진 소재를 현재 유입처럼 보이게 하던 문제를 막았다. 정지사유를 세 갈래로 나눠 보이고, 소재가 전부 꺼진 상품엔 "광고 정지" 배지를 붙이고, 꺼진 소재 실적은 합산에서 뺐다. 행마다 오판정 버튼도 달았다. 누르면 회차 폴더에 한 줄이 남고 판정 결과는 그대로다.

## 무엇이 바뀌었나

**board.py (Task 1)**
- `fold_products` 가 ⑥ 슬롯을 만나면 statusReason 을 라벨로 세서 `정지사유` 에 넣고, `productLive` 값은 내부 `_live_flags` 에 모은다. 키가 없으면 None 으로 담는다.
- ⑥ 만 가진 소재는 `SUM_FIELDS` 합산 전에 `continue` 한다. 지금은 ⑥ 행에 지표 키가 없어서 결과가 같다. 그래도 나중에 CLI 가 키를 실었을 때 과거 실적이 현재 유입으로 바뀌는 걸 막으려고 명시적으로 끊었다.
- out 루프에서 `광고정지` 를 정한다.
  - ⑥ 이 없으면 False
  - productLive 를 모르는 ⑥ 행이 하나라도 있으면 None (추정하지 않는다)
  - 전부 False 면 True
  - `_live_flags` 는 빼고 내보낸다.
- 원본 덤프 파일명은 모듈에 쓰지 않았다. `test_보드는_ads_json_을_열지_않는다` 가드는 그대로 통과한다.

**routes/board.py (Task 2)**
- 요청 모델 `MisjudgedReq` 를 추가했다.
  - 추가 필드는 거부한다(extra=forbid).
  - key 는 `routes.jobs.보드키` 를 import 해서 검사한다.
  - rule 은 `^[①-⑥]{1,12}$` 패턴, memo 는 200자까지, on 은 StrictBool 이다.
- `POST /board/misjudged` 는 이 순서로 처리한다.
  1. `paths.run_dir_path` 로 회차를 검사한다. 실패하면 400.
  2. `_load_result` 를 읽고 `fold_products` 에 그 키가 있는지 본다. 없으면 400.
  3. `misjudged.jsonl` 에 `open("a")` 로 한 줄을 붙인다(ensure_ascii=False). 쓰기 실패는 500 이고 예외 이름만 싣는다.
- `GET /` 는 `join.attach` 뒤에서 `_오판정읽기(선택)` 결과를 각 행의 `오판정` 에 얹는다.
  - 파일이 없으면 `{}` 를 돌려주고 파일을 만들지 않는다.
  - 깨진 줄, dict 가 아닌 줄, on 이 bool 이 아닌 줄은 건너뛴다.
  - 키마다 마지막 줄이 이긴다.

**board.js**
- 정지 컬럼은 formatter 가 DOM 노드를 돌려준다.
  - `광고정지` 가 true 면 `<mark>광고 정지</mark>` 를 그리고, title 은 "소재가 전부 꺼져 있다 — 이 행의 과거 실적은 현재 유입이 아니다" 다.
  - null 이면 "?" 를 그리고, title 은 "판정을 다시 돌려야(run) 보인다" 다.
  - 그 뒤에 "연동끊김 3 · 거부 1" 형식의 요약을 붙이고, hover 하면 전문이 보인다.
- 오판정 컬럼은 `<button type="button">` 을 DOM API 로 만든다.
  - 클릭은 `stopPropagation` 으로 막아 행 선택이 되지 않게 했다.
  - `window.관제탑.요청("/board/misjudged", {run_dir, key, rule: rules, on: !현재})` 를 보낸다.
  - 응답이 성공하고 bool 을 읽었을 때만 `row.update({오판정})` 한다. 실패하면 `오류표시` 로 알린다.

## 검증

- `.venv-web/bin/pytest webapp/tests -p no:warnings` → **1086 passed** (02-03 의 1061 + 신규 25)
- `-k "정지 or 꺼진"` 7개 · `-k 오판정` 18개 선택 · 전부 통과
- `node --check webapp/static/board.js` OK · `no_commit_guard.sh` OK
- `security_curl.sh` 는 격리 서버에서 돌렸다. 설정은 CT_PORT=8799, CT_DB_PATH·CT_DATA_ROOT·CT_AUDIT_PATH 는 scratchpad, CT_SKIP_STARTUP_REAP=1 이다.
  - **보안 9종 전량 PASS.** V-SAFE-01d 는 GET 핸들러 11개를 훑었다.
  - 새 POST 를 직접 쳐 봤다. 토큰이 없으면 403, Origin 이 evil 이면 403, 정상 요청은 200 이고 jsonl 줄 모양도 맞았다.
- 보너스로 같은 격리 서버에서 `board_cdp.sh` 를 돌렸다(CDP 포트 9333). **전량 PASS** 이고 SKIP 3건은 픽스처에 조인 데이터가 없어서다.
  - V-BOARD-07 은 표 1448 / 컨테이너 1448 로 가로 스크롤이 없다.
  - V-BOARD-06 은 렌더된 셀 180개에 undefined/NaN 0건이다.
  - 헤더에 정지·오판정이 들어갔다.
- 검증이 끝난 뒤 격리 서버를 내렸다. 운영 :8765 는 PID 45857 그대로다. 네트워크 호출 0, 실제 API 0.

## Commits

| Task | Gate | Commit | 내용 |
|------|------|--------|------|
| 1 | RED | 7c3f667 | 정지사유·광고정지·합산 배제 테스트 |
| 1 | GREEN | bdc4a14 | board.py 정지 집계 + board.js 정지 컬럼 |
| 2 | RED | cb90edd | 오판정 POST·GET 투영·가드 테스트 |
| 2 | GREEN | e9c7144 | POST /board/misjudged + 투영 + 버튼 컬럼 |

## Deviations from Plan

**1. [Rule 2 - 레이아웃 예산] 컬럼 2개를 넣으면서 기존 숫자 열 폭을 깎았다**
- 보드는 "고정폭 합 1,270 + 상품명 130 ≤ 컨테이너 1,448" 예산으로 가로 스크롤을 막고 있다(board.js 주석 · V-BOARD-07). 컬럼 2개(120px)를 그냥 더하면 이 예산이 깨진다.
- 그래서 숫자·라벨 열을 4~14px 씩 깎아 합 1,270 을 지켰다. 잘린 머리글은 `columnDefaults.headerTooltip` 으로 hover 하면 보인다.
- board_cdp V-BOARD-07 PASS 로 확인했다. 머리글이 좁아 보이는지 같은 시각 판단은 02-06 사람 확인으로 넘긴다. (bdc4a14, e9c7144)

**2. [Rule 1 - 테스트] 가드 테스트의 틀린 토큰 값을 ASCII 로 바꿨다**
- httpx 는 비ASCII 헤더를 인코딩하지 못한다. 앱 문제가 아니라 테스트 쪽 문제다. (cb90edd)

## Known Stubs

없음. 정지사유·광고정지는 result.json 에서, 오판정은 misjudged.jsonl 에서 온다.

## Threat Flags

없음. 새 표면은 POST /board/misjudged 하나이고 T-02-25~31 에 이미 들어 있다. 가드는 테스트와 security_curl 로 확인했다.

## 02-06 으로 넘기는 것

- 운영 :8765 재시작 뒤 실데이터에서 볼 것:
  - 정지 배지와 사유 요약이 어떻게 보이는지
  - 오판정 버튼 폭이 충분한지("오판정 ✓" 가 56px 에 들어가는지)
- 옛 result.json 회차는 정지 칸이 "?" 로 보인다. 새 판정(run) 을 한 번 돌려야 배지가 뜬다.

## TDD Gate Compliance

두 태스크 모두 `test(02-04)` 를 먼저 커밋하고 그다음 `feat(02-04)` 를 커밋했다. RED 단계에서 신규 테스트가 실패하는 것을 확인했다(필드·라우트 부재). 오판정 가드 403 테스트는 기존 미들웨어를 고정하는 회귀 테스트라 RED 에서 이미 통과했다.

## Self-Check: PASSED
