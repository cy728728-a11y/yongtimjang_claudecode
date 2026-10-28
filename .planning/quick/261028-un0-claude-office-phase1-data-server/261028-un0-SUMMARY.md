---
phase: quick-261028-un0
plan: 01
subsystem: 클로드 사무실 (10-projects/13-클로드-사무실)
tags: [claude-office, stdlib-http, transcript-parsing, team-mapping]
requires: []
provides:
  - "GET /api/office (CONTRACT §4 + team 필드 + robots)"
  - "GET /api/config, /api/health, web/ 정적 화면"
affects: []
tech-stack:
  added: []
  patterns: ["stdlib only (http.server, json, re)", "꼬리 창 64KB→4MB", "mtime 기반 캐시"]
key-files:
  created:
    - 10-projects/13-클로드-사무실/server/activity.py
    - 10-projects/13-클로드-사무실/server/sessions.py
    - 10-projects/13-클로드-사무실/server/teams.py
    - 10-projects/13-클로드-사무실/server/robots.py
    - 10-projects/13-클로드-사무실/server/snapshot.py
    - 10-projects/13-클로드-사무실/server/server.py
    - 10-projects/13-클로드-사무실/config/office.json
    - 10-projects/13-클로드-사무실/config/office-map.json
    - 10-projects/13-클로드-사무실/config/robots.json
    - 10-projects/13-클로드-사무실/web/ (원본 35개 파일)
    - 10-projects/13-클로드-사무실/NOTICE
    - 10-projects/13-클로드-사무실/tests/{conftest,test_activity,test_sessions,test_teams_snapshot,test_server}.py
  modified: []
decisions:
  - "팀 매핑·로봇 설정은 YAML 이 아니라 JSON(office-map.json · robots.json) — stdlib 에 YAML 파서가 없어 의존성 0 유지. 구조는 구현계획서 §4 YAML 과 동일. 구현계획서 §3 의 .yaml 표기는 고치지 않았다"
  - "robots.json log_path 는 glob(*) 을 허용 — 고퀄 상세 밤 배치는 날짜별 폴더라 가장 최근 batch.log 를 본다"
  - "미해결 도구 판정: tool_use id 집합을 tool_result 로 닫고, 사람이 새로 친 말·end_turn 이면 비운다(병렬 도구 호출이 줄마다 따로 기록되는 형식 대응)"
metrics:
  duration: "~35m"
  completed: 2026-10-28
  tasks: 3
  tests: 60
---

# Phase quick-261028-un0 Plan 01: 클로드 사무실 1단계 데이터 서버 Summary

Python 표준 라이브러리만으로 원본 개구리 사무실의 `/api/office` 계약을 그대로 내주되 **세션 1개 = 직원 1명**(이름 = customTitle → aiTitle → sid 8자, 팀 = sessions > rules > 로비)으로 바꾼 127.0.0.1 전용 서버 + 원본 web/ 화면 복사.

## 실행 방법

```
/opt/homebrew/bin/python3 10-projects/13-클로드-사무실/server/server.py [--port N]   # 기본 4778
# 시험
cd 10-projects/13-클로드-사무실 && ../../.venv/bin/python3 -m pytest tests -q        # 60 passed
```

## Tasks

| # | Task | Commits |
|---|------|---------|
| 1 | activity.py · sessions.py + 시험 | c4406ba (RED), d821f88 (GREEN) |
| 2 | teams.py · robots.py · snapshot.py · config/*.json + 시험 | d8a98f6 (RED), 2677368 (GREEN) |
| 3 | server.py + web/ 복사 + NOTICE + test_server + 실데이터 스모크 | 1d7028c |

## robots 로그 경로 조사 (읽기 전용)

예약 작업은 개별 plist 가 아니라 `~/Library/LaunchAgents/com.eroom.scheduler.plist` → `.claude/lib/eroom_scheduler.py` 의 `JOBS` 표(1분 틱) 한 곳에서 돈다. 로그는 `~/python_work/data/scheduler/logs/<작업>.log`.

| 로봇 | schedule | log_path | 결과 |
|---|---|---|---|
| 물갈이(Aside) | null | null | **못 찾음** — Aside 루틴이라 로컬 로그 없음. note "경로 미확인 — 2단계 전 확인" |
| 판매상품 잠금 | 00:01 | ~/python_work/data/scheduler/logs/sold-lock.log | 찾음 (JOBS sold-lock) |
| auto-watch | 07:30 | ~/python_work/data/scheduler/logs/auto-watch.log | 찾음 (JOBS auto-watch) |
| 고퀄 상세 밤 배치 | null | ~/python_work/data/detail-opus/batches/*/batch.log | 찾음 (detail-page-opus SKILL.md 배치 모드). 예약 시각 없음(수동 밤 실행) |
| 권리침해 소명 | 09:00 | ~/python_work/data/scheduler/logs/rights-claim.log | 찾음 (JOBS rights-claim) |

## web/ 외부 URL grep 결과

`grep -rnE "https?://" web/*.js web/index.html web/*.css` → 1건뿐: `index.html:8` 파비콘 data: URI 안의 SVG 네임스페이스 `xmlns='http://www.w3.org/2000/svg'`(네트워크 요청 아님). 외부로 나가는 fetch·script src 없음. web/ 안의 fetch 는 `fetch("/api/office")`(office-view.js:434) · `fetch("/api/config")`(i18n.js:175) 두 개.

## 실데이터 스모크 (2026-10-28 22:16 KST, /opt/homebrew/bin/python3 3.14, 포트 4778)

- people 13명, id 중복 0, sid 8자 폴백 이름 1명(913028ed — `~/test` 폴더의 제목 없는 세션), hooks=false, version=1
- 남의 Host(`evil.com`) → **403**, `/` → index.html 200(`<!doctype html><html lang="ko">…<title>3D 사무실`), `/office/frog.webp` 200, `/api/config` → `{"lang":"ko","version":"0.1.0-py"}`
- 스냅샷 조립 시간(3.12 .venv): 처음 0.13초, 캐시 후 0.001초 (49MB·22MB 대화 파일 포함)
- 서버 종료 후 `lsof -iTCP:4778 -sTCP:LISTEN` 결과 없음, `pgrep -f server/server.py` 없음 — 잔류 프로세스 0

```
status   team   teamName      subs id8      name
rest     edu    콘텐츠·강의팀  0    005e8656 구매대행 숏폼 초반 멘트
rest     edu    콘텐츠·강의팀  0    d2b6a53c 유튜브·릴스·쓰레드 영상 촬영 방법
rest     edu    콘텐츠·강의팀  0    e13de8e4 하입덕 수업 자료 학습
rest     it     IT개발팀       2    0839cd59 Claude 3D frog 가상 오피스
rest     it     IT개발팀       0    76b1198f uat-verifier 설치
rest     it     IT개발팀       0    f8032b96 카테고리픽스 스킬 노션 프롬프트
rest     lobby  로비·미배정    0    913028ed 913028ed
rest     ops    상품운영팀     0    e2d14270 상품명 작성용 키워드 추천
rest     plan   상품기획팀     0    783b23c2 아스트라 고퀄리티 상세페이지 제작법
rest     sec    비서실         0    9e68be60 to-do-list            (role 업무관리)
rest     sec    비서실         0    fd34b822 안산 호수마을 아파트 매도 잔금
rest     sec    비서실         0    b2684187 이메일 속 상품 정체
rest     src    소싱팀         0    f00dceb7 소싱 검수 1차 탈락결과 v3

robots: unknown 물갈이(Aside) / idle 판매상품 잠금 00:01 (last 2026-10-27T15:02Z) / idle auto-watch 07:30 (last 2026-10-27T22:30Z)
        idle 고퀄 상세 밤 배치 (last 2026-10-28T10:36Z) / idle 권리침해 소명 09:00 (last 2026-10-28T00:00Z)
```

**working 0명 — 규칙대로 맞는 결과다.** 스모크 시점(22:16:51)에 가장 최근 바뀐 대화 파일이 22:13:24(0839cd59, 3분 27초 전)라 90초 규칙에 안 걸렸고, 미해결 도구 호출도 없었다. 플랜은 "지금 이 작업을 하는 세션이 working" 을 기대했지만, 실제 작업은 0839cd59 의 **서브에이전트**(이 실행기, subCount=2 로 보임)가 하고 있었고 부모 대화는 턴을 마치고 기다리는 중이었다. uat-verifier 는 사용자가 직접 대화 중인 세션으로 working 을 확인하면 된다.
→ 2단계 전 결정할 것: "서브에이전트가 일하는 중이면 부모도 working" 규칙을 넣을지(구현계획서 §4 에는 없음, 이번엔 넣지 않았다).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] 시험 JSON 을 compact 형식으로**
- **Found during:** Task 1
- **Issue:** Python `json.dumps` 기본값은 `"type": "assistant"`(공백)라 바이트 필터(`"type":"assistant"`)에 안 걸린다. 실제 Claude Code 파일은 compact(`{"type":"ai-title",...}` 실측 확인)
- **Fix:** conftest 의 줄 헬퍼를 `separators=(",", ":")` 로
- **Commit:** c4406ba

**2. [Rule 2 - Robustness] robots log_path glob 지원**
- **Found during:** Task 2 로그 경로 조사
- **Issue:** 고퀄 상세 밤 배치 로그는 `batches/<날짜>/batch.log` 라 고정 경로로 못 적는다
- **Fix:** `*?[` 가 있으면 glob 으로 가장 최근 파일 mtime 사용
- **Commit:** 2677368

**3. [Plan 조정] 이름 중복 처리·정렬**: 원본 "(부모 폴더)" 대신 "(sid 앞 8자)", people 은 (team, name, id) 순 — 플랜 지시대로.

그 밖 플랜대로 실행. 증분 이어읽기(원본 readTranscript 의 늘어난 부분만 읽기)는 플랜대로 하지 않았고, 파일이 바뀌면 꼬리 창을 다시 읽는다(실측 cold 0.13s).

## 안전 확인

- `grep -nE "open\([^)]*['\"](w|a|r\+|wb|ab)" server/*.py` → 0줄 (~/.claude 쓰기 없음)
- 바인딩 127.0.0.1 만, Host 화이트리스트, GET 외 405, `..`/%2e/%5c/%00 → 404, 정적 파일은 시작 때 만든 화이트리스트에서만
- 참고 저장소 안에서는 아무것도 실행하지 않았다(cp 와 cat 만)
- 3.12 문법 확인(ast feature_version=(3,12)), 서버는 3.14(homebrew)·3.12(.venv) 양쪽에서 돌았다

## Known Stubs

- `robots.json` 물갈이(Aside): `log_path: null` → 화면에 status "unknown". 2단계 전 Aside 쪽 흔적(있다면) 확인 필요.
- Person `commits: null`, `kid: false`, `home: null`, `pending: 0`, `ask: ""`, `hooks: false` — 1단계 범위(훅 없음, 폴더별 git 집계 안 함)에서 의도된 고정값.

## Self-Check: PASSED

- 파일: server/*.py 6개, config/*.json 3개, web/index.html·office-view.js, NOTICE(MIT License 포함), tests/*.py 5개 — 모두 존재
- 커밋: c4406ba, d821f88, d8a98f6, 2677368, 1d7028c — 모두 git log 에 있음
- `pytest tests -q` → 60 passed
