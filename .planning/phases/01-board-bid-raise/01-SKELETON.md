# Walking Skeleton — 셀러 관제탑 (Seller Control Tower)

**Phase:** 1
**Generated:** 2026-09-20

## Capability Proven End-to-End

> 사용자가 브라우저(127.0.0.1:8765)에서 보드의 상품 줄을 고르고 버튼을 누르면, 웹앱이 기존 CLI 를
> 서브프로세스로 띄우고, 그 진행 로그를 **탭을 닫았다 다시 열어도 처음부터 이어서** 본다.

RESEARCH.md §6.2 의 2단 스켈레톤을 그대로 따른다.

| 단계 | 내용 | 소요 | 광고 API |
|---|---|---|---|
| **Skeleton A — 프레임** | 상품 줄 선택 → `create_job("bids_preview", only_ads=[adId…])` → targets 파일 기록 → subprocess → SSE 로그 → `--preview-out` 읽어 `70 → 80` 표 | **0.066초** | 없음 (dry-run) |
| **Skeleton B — 지속시간** | 같은 엔진으로 `prep --account cy728` 실행 → 탭 닫기 → 30초 뒤 재접속 → 로그가 처음부터 다시 흐름 | ~3분 | GET + `POST /stat-reports` (광고 자체는 불변) |
| **Skeleton C — 자동화** | 같은 `create_job` 을 타는 5초짜리 합성 잡 — SSE 재접속·로그 전량 재생·종료 감지를 네트워크 0 으로 결정적 검증 | 5초 | 없음 |

**왜 A 만으로는 안 되는가:** A 는 0.066초라 "탭 닫았다 이어보기"(ENG-02 / Success Criteria 3)를 증명할 수 없다.
**왜 B 만으로는 안 되는가:** B 는 3분이라 CI·개발 루프에서 돌릴 수 없다 → C 가 자동 검증을 맡는다.

## Architectural Decisions

이 표는 **계약이다.** Phase 2~7 은 이 결정을 재논의하지 않고 그 위에 슬라이스를 얹는다.

| Decision | Choice | Rationale |
|---|---|---|
| 앱 프레임워크 | FastAPI 0.141.1 + Uvicorn 0.53.0, **`--workers 1` 고정** | CLAUDE.md 확정. 워커 2개면 잡 레지스트리·SSE 구독자가 프로세스별로 갈라져 "가끔 로그가 안 뜬다"가 간헐 발생 (RESEARCH Pitfall 9) |
| 렌더링 | Jinja2 서버 렌더 + htmx 2.0.10 + htmx-ext-sse 2.2.4 + Tabulator 6.5.3 + Pico.css 2.1.1 | 빌드체인 0. npm 을 쓰지 않는다 — 정적파일은 `curl` vendoring 으로 `webapp/static/vendor/` 에 받는다 |
| CLI 통합 | **subprocess only.** `import` 금지 | `run_ads.py:21-27` 이 `sys.path.insert` 후 네임스페이스 없는 최상위 이름(`bids`·`collect`·`nvad`)을 import 한다. 웹앱 프로세스에 들어오면 stdlib 이 가려진다 (RESEARCH §5.6 에서 `inspect` 로 실제 재현됨) |
| CLI 런타임 | `PY_CLI = REPO/".venv/bin/python3"` — 웹앱의 `.venv-web` 이 **아니다** | 섞으면 CLI 가 selenium/openpyxl 을 못 찾는다 |
| 데이터 계층 | stdlib `sqlite3`, `webapp.db`, `PRAGMA journal_mode=WAL`, 테이블 **1개(`jobs`)** | `board_cache` 는 만들지 않는다 — 보드는 `result.json` 을 매번 투영한다(547KB ≈ 수십 ms). 캐시는 "진실이 둘" 위험만 늘린다 |
| 판정값의 진실 | `run-dir/result.json` + CLI 의 `--preview-out` 산출물 | **웹앱은 입찰가를 계산하지 않는다.** ①행의 92%가 `useGroupBid=true` 라 재계산하면 거의 전량 틀린다 (실측: 잠자던 값 50 vs 실제 그룹가 70) |
| 자격증명 경계 | 시크릿은 **CLI 서브프로세스에만** 존재. 웹앱은 `~/.eroom/naver-ads.json` 을 열지 않는다 | 계정 목록이 필요하면 `run_ads.py accounts` (읽기 전용 서브커맨드, alias·customer_id 만 stdout) 를 subprocess 로 부른다. SAFE-03 을 테스트가 아니라 **구조**로 보장 |
| 인증 | 없음 (Out of Scope). 대신 3층: `--host 127.0.0.1` + `TrustedHostMiddleware(["127.0.0.1","localhost"], www_redirect=False)` + 쓰기 메서드 전용 Origin 검증 + `secrets.token_urlsafe(32)` 부팅 토큰(`X-CT-Token` 헤더 / `ct_session` 쿠키) | RESEARCH §4 에서 이 맥북 curl 6케이스 실측 통과 |
| **상태를 바꾸는 GET 금지** | 모든 작업 생성은 POST | 교차 사이트 단순 GET 에는 `Origin` 헤더가 없다 → 쓰기를 GET 에 두면 Origin 방어가 통째로 무력화된다 |
| 진행 로그 | 자식 stdout+stderr → `webapp-logs/<job_id>.log` (append-only, `buffering=0`) → 오프셋 tail → `sse-starlette` `EventSourceResponse(ping=15)` | 파이프 직결 금지. 브라우저를 닫은 사이의 출력이 사라진다 |
| SSE 재개 | **매 접속마다 로그 전량 재생 후 tail.** `Last-Event-ID` 에 의존하지 않는다 | htmx-ext-sse 2.2.4 가 재연결 시 `htmx.createEventSource(url)` 를 새로 호출해 last event ID 를 버린다(소스 확인). 잡 로그가 4.5KB/53줄이라 전량 재생이 더 단순하고, 성공기준 3("처음부터 이어서 본다")과 글자 그대로 일치 |
| 자식 프로세스 | `subprocess.Popen(argv, cwd=REPO, env={**os.environ,"PYTHONUNBUFFERED":"1"}, stdout=<로그파일 ab>, stderr=STDOUT, stdin=DEVNULL, start_new_session=True, close_fds=True)` | `PYTHONUNBUFFERED` 없으면 0.5초 시점 로그파일 **0바이트**(실측) → ENG-03 이 조용히 깨진다. `start_new_session` 이 `uvicorn --reload` 재시작에서 자식을 살린다(실측 2회) |
| 작업 생성 경계 | `jobs.create_job(kind, *, run_dir, accounts, only_ads, commit, parent_job_id) -> job_id` 는 **HTTP 를 모른다.** 라우트는 얇게 감싸기만 | D-17 / ENG-07. v2 의 APScheduler 가 같은 함수를 부른다 |
| argv 조립 | `webapp/argv.py` 의 `AdsArgv` Pydantic 모델 **한 곳에서만**. `shell=False`, 리스트 argv | 명령 주입 차단 + Phase 2 의 `caffeinate -i` 프리픽스를 `build()` 맨 앞에 한 줄로 끼울 자리 |
| 3단 계약의 매체 | **파일** — `run-dir/web/targets_<job>.json` → `preview_<job>.json` → `result_<job>.json` → `targets_revert_<job>.json`, `jobs.parent_job_id` 로 사슬 | FLOW-02 / D-11: 화면 상태가 아니라 파일이 진실. 미리보기·실행·되돌리기가 **같은 targets 파일**을 지목 |
| 원자적 쓰기 | 모든 JSON 산출물은 `tmp → os.replace`, `ensure_ascii=False` | 저장소 전역 10곳의 관례. 반쪽 JSON 을 CLI 가 `--only-ads` 로 읽는 사고를 막는다 |
| 동시성 | `async def` 는 **SSE 엔드포인트만**. 나머지 라우트는 전부 `def` (Starlette 스레드풀) | `async def` 안의 sqlite/파일 blocking IO 는 이벤트 루프를 막는다 |
| 응답 압축 | `GZipMiddleware(minimum_size=1000)` | 보드 547KB → 95KB (실측) |
| 테스트 | **CLI 는 stdlib `unittest` 그대로**(러너: 파일 직접 실행), **웹앱만 `.venv-web` + pytest** | PATTERNS §C-1 충돌 해소. CLI 테스트 100개를 pytest 로 옮기는 것 자체가 회귀 위험이다 |
| 디렉터리 | `webapp/` 새 최상위. CLI 패치는 `.claude/skills/naver-ads-weekly/scripts/` **원위치**에서 (복사본 금지) | 복사본을 만들면 진실이 둘이 된다 |

## Stack Touched in Phase 1

- [x] 프로젝트 스캐폴드 — `.venv-web` (uv) · `webapp/pytest.ini` · `.gitignore` · 정적파일 vendoring (Plan 01-01)
- [x] 라우팅 — `GET /` (보드) · `POST /jobs/*` · `GET /jobs/{id}/stream` · `GET /jobs/{id}/result` (Plan 01-03 / 01-05)
- [x] 데이터베이스 — `jobs` 테이블 실제 INSERT(작업 생성) + SELECT(상태·동시쓰기 가드) (Plan 01-05)
- [x] UI — Tabulator 보드 행 선택 → htmx `hx-post` → SSE 로그 패널 (Plan 01-04 / 01-05 / 01-06)
- [x] 로컬 풀스택 실행 명령 — `webapp/run-webapp.sh` (`.venv-web/bin/python -m uvicorn webapp.main:app --host 127.0.0.1 --port 8765 --workers 1`) (Plan 01-03)

## Out of Scope (Deferred to Later Slices)

Phase 1 의 최소성을 나중 단계가 재논의하지 못하도록 명시한다.

- **launchd 상시 기동 / LaunchAgent plist** — 사용자 확정(OQ-5). 서버는 수동 기동. 성공기준 3 은 "브라우저 탭"이지 "맥북 재부팅"이 아니다
- **작업 잠금(ENG-04) 전체 · 고아 작업 정리(ENG-05) · `caffeinate -i`(ENG-06)** — Phase 2. 단 Phase 1 은 `jobs.pid`·`started_at` 컬럼과 **쓰기 잡 전역 1개 가드**(Pitfall 3)를 남겨 Phase 2 가 끼워 넣을 자리를 만든다
- **실행 직전 재조회 · 미리보기 스테일 거부(SAFE-05 / FLOW-03)** — Phase 2. Phase 1 은 D-10 의 diff 보고로 "달라졌다는 사실"만 보여주고 거부하지 않는다
- **감사 로그 JSONL(FLOW-07) · 실패분 재시도(FLOW-06) · 오판정 표시(BOARD-06) · 정지 소재 과거실적 방어(BOARD-05)** — Phase 2
- **`bids --commit` 진행률 출력** — CLI 로직 변경이라 범위 밖(OQ-3). 화면의 경과시간 표시로 덮는다
- **`ledger.record_reverted` 의 날짜 불일치 수정** — 로직 변경(OQ-2). Phase 1 은 경고 배너만
- **불사자 계정 확인 게이트(ENG-08)** — Phase 3. Phase 1 은 광고 API 만 건드리고 불사자 토큰을 아예 로드하지 않는다
- **서버사이드 페이징 · 가상 스크롤 · `board_cache` 테이블** — 2,637행은 Tabulator 클라이언트 사이드로 충분
- **APScheduler 스케줄 자동화** — v2. D-17 이 전제만 깔아둔다
- **태스크 큐(Celery/RQ/Huey) · Redis · Docker · WebSocket · React/Vite/Tailwind · SQLAlchemy/Alembic** — CLAUDE.md 확정 배제

## Subsequent Slice Plan

각 후속 단계는 위 결정을 바꾸지 않고 슬라이스 하나를 얹는다.

- **Phase 2:** 꺼진 소재 정리(파괴적 삭제) — 같은 `create_job` 엔진에 `prune` kind 를 더하고, 전역 쓰기 가드를 **대상별 락**으로 넓히고(ENG-04), 고아 정리(ENG-05)·`caffeinate` 프리픽스(ENG-06)·감사 로그(FLOW-07)를 붙인다
- **Phase 3:** 광고↔불사자 조인 + 상세 상태 판정 — 보드 컬럼이 늘어날 뿐 `fold_products` 의 접기 키 `(alias, mallProductId)` 는 그대로
- **Phase 4:** 홍보배너 식별 — 웹앱은 결과 표시만, 판정은 새 CLI 스크립트
- **Phase 5:** 상세페이지 작업 버튼(Core Value) — `detail_batch.py` 를 같은 엔진으로 래핑. 폴링이 수십 분이므로 여기서 `caffeinate` 가 실제로 필요해진다
- **Phase 6:** 마켓 수정업로드 — 1건 육안 확인 게이트를 `checkpoint` 라우트로
- **Phase 7:** 썸네일 교체 / 쿠팡 복사 — 버튼 2개 추가. 엔진·보안·3단 계약 무변경
