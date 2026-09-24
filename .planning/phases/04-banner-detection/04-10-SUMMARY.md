---
phase: 04-banner-detection
plan: 10
subsystem: banner-webapp
tags: [banner, d22, vision2, argv, settings, 검수화면, 판정출처, 규칙불일치, gap-closure]
status: Task 1·2 완료 · Task 3(uat-verifier) 오케스트레이터 몫으로 대기. 실제 Gemini 호출 0회 · 실탄 스캔 0회.

requires:
  - phase: 04-banner-detection
    plan: 09
    provides: "--vision2-* CLI 계약 · settings banner_vision2_* 7키 · 산출물 판정규칙.2차판정 · 장별 1차/2차/출처"
provides:
  - "BannerArgv vision2_* 7필드(기본값 없음) — build() 가 7플래그를 조건 없이 붙인다(꺼짐도 off 명시)"
  - "jobs._build_argv banner_scan 분기의 settings.load(force=True) — toml 변경이 재시작 없이 다음 잡에 반영"
  - "검수 화면: 장별 출처 표식(👁 비전 · ↩ 뒤집기)·2차 근거, 판정규칙 3갈래(켜짐/꺼짐/옛 회차), 현재 설정 불일치 경고"
affects: [04-11, 04-12]

tech-stack:
  added: []
  patterns:
    - "설정 대조는 새로 읽은 설정으로만 — 라우트도 load(force=True)"
    - "테스트의 설정 덮기는 _cache 가 아니라 paths.read_workspace_toml 자리에서(강제 재적재가 _cache 덮기를 버리므로)"

key-files:
  created:
    - .planning/phases/04-banner-detection/04-10-SUMMARY.md
  modified:
    - webapp/argv.py
    - webapp/jobs.py
    - webapp/routes/banner.py
    - webapp/templates/banner_review.html
    - webapp/templates/_banner_strip.html
    - webapp/tests/test_argv.py
    - webapp/tests/test_jobs.py
    - webapp/tests/test_routes_banner.py

decisions:
  - "배너 잡 조립과 검수 화면 대조 둘 다 settings.load(force=True) 로 toml 을 새로 읽는다 — 04-08 낡은 캐시 사고(04-GATE §0) 재발 방지"
  - "2차 모델·지시문판은 산출물·현재 설정 양쪽이 켜졌을 때만 비교한다. 옛 회차는 2차 항목을 비교하지 않고 옛회차로 따로 표시한다"
  - "출처 표식은 서버(_출처표식)가 정한다 — 템플릿이 출처 문자열로 분기하지 않는다(S-1)"

metrics:
  duration: 12min
  completed: 2026-09-24
  tasks: 2 of 3 (Task 3 = uat-verifier 대기)
  files: 8
---

# Phase 4 Plan 10: 비전 2차 웹앱 배선 · 검수 화면 규칙 표기 Summary

04-09의 `--vision2-*` 계약을 웹앱 잡과 검수 화면에 연결했다. 이제 배너 잡은 조립할 때마다 `workspace.toml`을 새로 읽어서 7개 플래그를 전부 명시적으로 넘긴다. `jobs.argv`에는 키 파일 경로만 들어가고 키 값은 들어가지 않는다. 검수 화면은 장마다 누가 배너라고 판정했는지, 이 산출물이 어떤 규칙으로 나왔는지, 그 규칙이 현재 설정과 같은지를 보여준다.

## 만든 것

- **Task 1** (`f605940`): `BannerArgv`에 `vision2_enabled/model/prompt/key_file/timeout/max_calls/interval` 필드를 추가했다. 기본값은 없다. `model`과 `prompt`는 `PlainArg`라서 플래그처럼 생긴 값을 거부한다. `build()`는 `--vision2-enabled on|off`부터 `--vision2-interval`까지 조건 없이 붙이고, `--vision2-estimate`는 넘기지 않는다. `_build_argv`의 `banner_scan` 분기는 맨 앞에서 `settings.load(force=True)`를 부르고, 그 뒤 설정 키 7개를 `cfg(..., DEFAULTS[...])` 모양으로 넘긴다. 키 파일은 `Path(str(...))`로만 만든다(`banner_dir` 미사용). `KINDS` 계열 집합은 바꾸지 않았다.
- **Task 2** (`8b7a436`):
  - `_장투영`이 `출처`, `출처표식`(비전 `👁`, 뒤집기 `↩`), `이차근거`(`2차.근거`, 실패 시 `2차 실패: 타입`)를 싣는다.
  - `_규칙불일치()`는 어휘군버전, 2차 사용 여부, 2차 모델, 2차 지시문판을 새로 읽은 설정과 대조한다.
  - `banner_review.html`의 판정규칙은 세 갈래로 나뉜다. 켜진 회차는 모델, 응답모델, 지시문/sha12, 합성, 범위, 대상, 비전추가배너, 뒤집기, 실패를 보여준다. 꺼진 회차는 "2차 판정 꺼짐 — 1차 어휘군 단독", 옛 회차는 "2차 판정 칸이 없는 옛 회차"로 표시한다.
  - 불일치가 있으면 `⚠ 이 산출물은 현재 설정과 다른 규칙으로 나왔다` 블록을 띄운다(이중선, 색만으로 구분하지 않음). 미탐 칸에는 in-sample 주석을 달았다.
  - `_banner_strip.html`의 title과 figcaption에 출처와 근거를 넣었다. 자동 이스케이프는 켜 둔 채다.

## 테스트

- `.venv-web` `webapp/tests`: 462 → **472 passed** (+10). argv 3개(7플래그/on·off, 키 값 부재, 플래그 모양 거부), 필수 필드 누락 거부 목록에 vision2 7개 추가, jobs 2개(재시작 없이 반영, argv 컬럼에 키 없음), routes 5개(켜짐, 옛, 꺼짐, 불일치, 장별 출처 👁/↩/근거).
- `bash webapp/tests/banner_cdp.sh`: **전량 PASS** (V-BANNER-00~04, 합성 산출물, 임시 포트, 자기 서버는 스스로 종료)
- `.venv` `webapp/tests/cli`: 4 passed
- D-19 트리 가드는 초록이다. `webapp/`에 네트워크 코드와 PIL은 0줄이다. `git diff webapp/banner.py`는 비어 있다(게이트 산식 불변).
- 새로 생긴 `vision2_*.jsonl` 체크포인트는 0개다. 유료 호출은 없었다.

## Task 3 — uat-verifier: **대기 (오케스트레이터가 실행)**

이 실행기 환경에는 에이전트를 띄우는 도구가 없어서 `uat-verifier`를 부르지 못했다. 플랜의 자동 검증(위 3개)은 전부 통과했다. **오케스트레이터가 `uat-verifier`(sonnet)를 불러야 한다.** 넘길 조건:
- 명세: must_haves.truths 1·3·4·5
- 실데이터 배너 스캔 금지. 합성 산출물 3종(2차 켜짐, 꺼짐, 옛 회차)에 `출처`가 섞인 장(`비전`, `뒤집기`)을 넣어 확인한다. `banner_cdp.sh` 방식이다.
- 설정 반영 확인은 `workspace.toml [webapp] banner_vision2_model`을 임시로 바꾸고 `jobs` 테이블의 argv를 읽는 데까지만 한다. 자식이 exit 5(승인 상한 0)로 멈추면 기대 동작이다. 끝나면 toml을 원복한다.
- Gemini, 불사자, 네이버 호출은 0이어야 한다.
- 사용자에게 남길 것: 표식(👁 ↩)과 경고 블록의 시각 심미만.

UAT 판정: **미실행** (PASS/FLAKY/FAIL/BLOCKED 없음. P0 "검증 중 소스 변경"도 해당 없음).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] 기존 `test_배너잡_argv_가_설정에서_온다`가 `_cache` 덮기 방식이라 force 재적재와 충돌했다**
- **Found during:** Task 1
- **Issue:** 이 테스트는 `settings._cache`를 monkeypatch로 덮는데, 새 `load(force=True)`가 그 덮기를 버린다.
- **Fix:** `_toml덮기()` 헬퍼를 추가해서 `paths.read_workspace_toml` 자리를 갈아끼운다(`[webapp]`만 덮고 `_cache` 복원도 등록). 기존 테스트도 이 헬퍼로 바꿨다. 단언 내용은 그대로다.
- **Commit:** f605940

**2. [계획 보강] 출처 표식을 서버 dict(`_출처표식`)로 정했다.** 템플릿에 출처 문자열 분기를 넣지 않는 S-1 규율을 따른 것이다.

**3. [계획 보강] 설정 대조가 실패하면 빈 목록이 아니라 "설정 대조 실패" 항목을 띄운다.** 빈 목록은 "같다"로 읽히기 때문이다.

## 남은 것 / 주의

- **사용자 서버(PID 2259, 2026-09-22 기동, :8765)는 04-10 이전 코드를 들고 있다.** 새 화면을 보려면 재시작이 한 번 필요하다. 이번 수정 이후로는 설정 변경에 재시작이 필요 없다. 이 실행기는 그 서버를 건드리지 않았다.
- 검수 화면 상단 문구 "토큰 0 · 크레딧 0"은 2차가 켜진 스캔(유료 가능)과 어긋날 수 있다. 기본 승인 상한이 0이라 지금은 호출 전에 exit 5로 멈추므로 사실과 모순되지는 않는다. 04-11 실탄 때 문구를 다시 볼 것.
- BANNER-01·BANNER-03b 완료 표시는 하지 않았다. 게이트(미탐 0%)가 아직 통과하지 않았다.

## Threat Flags

없음. 새 표면은 없다. T-4-40~43의 완화 조치는 전부 구현했고 회귀 테스트로 검증했다(키 값 부재, 네트워크 0, force 재적재와 불일치 경고, 실탄 0).

## Known Stubs

없음.

## Self-Check: PASSED
