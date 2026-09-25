# Phase 5: 상세페이지 작업 버튼 ★ Core Value - Research

**Researched:** 2026-09-25
**Domain:** 기존 CLI(`detail_batch.py`) 주입구 플래그 추가 + 웹앱 견적→승인→접수→폴링 잡 3종 + 배너 관문 교체
**Confidence:** HIGH (코드·실데이터 직접 확인. 네트워크 0회 — 불사자·네이버 미접속)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**🔒 잠긴 제약 (auto 아님)**
- **L-01:** 크레딧을 쓰는 동작과 되돌릴 수 없는 동작은 전부 플랜의 blocking human checkpoint 다. ① 모든 실제 AI 상세 접수(첫 5건 실탄 포함) ② 비전 2차 유료 호출 상한을 0 에서 올리는 것 ③ 실패분 재접수 ④ 불사자 태그 쓰기(D-10 폴백이 발동할 때). 각 체크포인트 앞에 **견적(건수 · 장수 · 크레딧)** 을 보여 준다. `autonomous: false` 이고 `--auto` 체인도 이 체크포인트를 자동 승인하지 않는다.
- **L-02:** 접수 전 예상 크레딧 보고 → 승인 → 접수. 순서 예외 없음.
- **L-03:** 폴링 타임아웃은 실패가 아니다. 재접수로 풀지 않는다 — 크레딧 이중 지불.
- **L-04:** 기존 CLI 재작성 금지. `detail_batch.py` 는 subprocess 로 부르고, 필요한 건 **주입구 플래그 추가**만 한다. 웹앱은 불사자 MCP 를 직접 부르지 않는다.
- **L-05:** 진실의 원천은 불사자 서버. 기작업 판정용 로컬 대장을 새로 만들지 않는다. run-dir 의 `detail_status.json` 은 그 회차 접수의 재개 체크포인트일 뿐.
- **L-06:** 계정 가드(ENG-08) 그대로. 기대 계정(부킹/용쌤)이 아니면 미리보기·접수 모두 거부.

**배너 입력**
- **D-01 `[auto — 용팀장 확인 필요]`:** 새 회차는 검수 화면 사람 확인을 통과해야 접수 가능. 비전 2차는 끈 채(`banner_vision2_max_calls = 0`).
- **D-02 `[auto — 용팀장 확인 필요]`:** 상세 입력 관문은 `게이트통과` 대신 "사람 확인된 상품 + 사람 라벨 우선 판정". 입장 조건(상품 단위): ① `banner_confirm` 에 있고 확인시각 ≥ 해당 산출물 `생성시각` ② 스킵 상품 아님 ③ 미판정 장 0. 제품 이미지 = 라벨 있으면 라벨, 없으면 기계 (`무내용` 제외). 구조 가드 유지(인자 누락 = 예외).
- **D-03:** 검수 화면 `확인함` 재클릭 불가 결함을 고친다 — 이미 확인된 상품에도 `확인함`(다시 확인) 버튼. 그 이상은 안 한다.
- **D-04:** 배너 스킵 상품은 상세 대상에서 빠진다. 사람 라벨로 스킵 재계산하지 않는다.

**대상 고르기**
- **D-05:** 기본 🔴. 🟡 수동 선택 허용. ⚪·`구매_가공완료` 는 회색·기본 제외.
- **D-06:** 작업 대상은 조인으로 이어진 사본 1개(판매자상품코드)뿐. 표기는 판매자상품코드.
- **D-07:** 선택 UI 는 Phase 1 입찰가 인상의 선택 UI(보이는 것만 vs 필터 전체) 재사용.

**생성 파라미터**
- **D-08:** 입력 이미지 목록은 웹앱이 D-02 관문으로 만들어 CLI 에 파일로 넘긴다 — `--inputs <json>`. 플래그 있으면 `collect_images` 를 타지 않는다. 플래그 없는 기존 동작 불변. 입력 파일에 없는 상품은 접수하지 않는다.
- **D-09 `[auto — 용팀장 확인 필요]`:** 제품 이미지 10장 초과 시 원래 순서 앞 10장 + 누락 장수를 견적 화면에 표시.
- **D-10:** 장수 = `max(2, min(입력 제품이미지 수, 10))`, `imageUrls`+`sectionCount` 동시, 예상장수 불일치 시 전량 중단(exit 2). 테스트로 고정만.
- **D-11:** 화질 일반(standard, 장당 5크레딧) 고정. 화질·장수 선택지 없음.

**기작업 스킵**
- **D-12:** 스킵 판정은 `state.py::기작업여부` 와 같은 규칙 — `구매_가공완료` 태그 OR `aiImageGenerated` — 을 CLI 가 접수 직전 실시간으로. 목표 장수와 무관한 절대 조건. 현행 `prev["pages"] >= sc` 를 절대 조건으로. 태그 목록은 `done_tags` 인자로. 교차 테스트 필수.
- **D-13:** 첫 5건 실탄 뒤 `aiImageGenerated` 가 실제로 찍히는지 재조회로 실측. 안 찍히면 태그 쓰기 폴백(L-01 ④). 어느 쪽이든 같은 목록 두 번째 견적 = 접수 0건이 SC-3 증거.

**견적 → 승인 → 접수**
- **D-14 `[auto — 용팀장 확인 필요]`:** 견적은 크레딧 0 미리보기 잡 — CLI `--estimate-only`. 견적 화면: 선택 N → 스킵 M → 실제 접수 K · 총 장수 · 예상 크레딧 · 10장 초과 상품 수 · 현재 계정 · 잔액(참고). 접수 버튼은 견적 잡의 targets 파일만 가리킨다. 접수 시 스킵이 늘면 줄여 접수·재보고, **늘어나는 방향이면 멈춘다**. 상한 없음 · 버튼이 승인(추천).
- **D-15:** 접수 잡은 `WRITE_KINDS` 에 넣는다. `caffeinate -i` 프리픽스 대상에 추가.

**폴링 · 복구**
- **D-16:** 접수 잡 하나가 접수→폴링. 복구는 별도 잡 `--poll-only`.
- **D-17:** 폴링 시간 상한 → `폴링 미완 N건` 으로 끝, 실패 아님. 전용 종료코드. 화면은 `이어서 확인` 버튼만. 재접수 버튼 없음.
- **D-18:** 서버가 실패로 확정한 건만 `실패`. 실패분 재접수 버튼은 MVP 밖.
- **D-19:** 결과 화면 = 항목 단위 표(판매자상품코드 · 접수/완료/실패/스킵/폴링중 · 장수 · 크레딧 · 사유). 별도 적용 버튼 없음.

### Claude's Discretion
- 상세 잡 run-dir 위치·파일 이름(예: `<회차>/web/detail_<job>/` 에 `products.json` · `inputs.json` · `detail_status.json`)
- 견적·결과 표 레이아웃(기존 `_preview_table.html`·`_result_table.html` 재사용 정도)
- 생성 이미지 썸네일을 결과 표에 띄울지
- 폴링 종료코드 번호, `--estimate-only` 산출물 JSON 모양
- 견적 잡과 접수 잡 사이 유효시간 여부

### Deferred Ideas (OUT OF SCOPE)
- 10장 초과 상품 분할 생성 · 실패분 재접수 버튼 · 워터마크 제거 가공 · 사람 라벨 기준 스킵 재계산 · 대량 접수 금액 상한
- (Phase 4 D-23 이월) out-of-sample 재측정(Q2) · 비전 지시문 v4 · 검수 화면 `게이트: 열렸다` 문구
- 생성 이미지 품질 검수 화면 · 고화질 선택 · 장수 수동 조정
- todo `429-group-stage-silent-completion`, `job-reap-depends-on-polling` 은 접지 않음(후자는 SC-1 검증 때 증상 확인만)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DETAIL-01 | 입력 = 기존 상세 이미지 − 홍보배너 (썸네일·옵션 안 씀) | `--inputs` 플래그로 `collect_images` 우회 (§CLI 패치 A). 웹앱 `banner.상세입력목록`(D-02 새 관문) 이 라벨우선 판정으로 URL 생성 (§관문 교체). **주의: 최신 산출물 기준 확인시각이 전부 낡아 지금 적격 0건** (§실데이터) |
| DETAIL-02 | 장수 = min(제품이미지,10), 하한 2 | 현행 `sc = max(2, min(pages, len(imgs)))` 그대로. inputs 모드는 중복 URL 제거 후 세고, 2장 미만은 접수 거부(fail-closed) |
| DETAIL-03 | imageUrls + sectionCount 동시 | 현행 `submit_one` 의 `base` dict 그대로. 오프라인 스텁 MCP 로 호출 인자 단언 테스트 |
| DETAIL-04 | 예상장수 불일치 → 전량 중단 | 현행 exit 2. **구멍 2개**: 예상장수가 int 가 아니면 조용히 통과 · 중단된 그 1건의 taskId 를 체크포인트에 안 남김 (§Pitfall 2) |
| DETAIL-05 | 견적 보고 → 실제 접수분 재보고 | `--estimate-only` + `--estimate-out`(크레딧 0) · 접수 잡은 `--max-credits <견적값>` 로 증가 방향 차단 · 끝 리포트 JSON |
| DETAIL-06 | 폴링 타임아웃 ≠ 실패 | 전용 exit 3 + `jobs._finish` 의 kind별 해석 + 화면은 `detail_status.json` 을 정본으로 읽음. **현행 폴링 조기종료 버그** 수정 필요 (§Pitfall 1) |
| DETAIL-07 | 접수·폴링 분리, 끊겨도 체크포인트로 이어 확인 | 현행 `--poll-only` + `detail_status.json` 재사용. 웹앱 `detail_poll` 잡이 같은 detail run-dir 을 가리킴 |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- 웹앱은 기존 CLI 스크립트의 래퍼 — 검증된 로직을 재작성하지 않는다 (subprocess 경계)
- 모든 쓰기 작업 dry-run 선행 · 크레딧 소모 작업은 접수 전 견적 보고
- 작업 완료 여부 정본 = 불사자 서버 플래그. 로컬 대장 정본 금지
- 코드 주석 한국어 · Python · try-except 포함
- `uvicorn --workers 1` 고정 · `.venv-web` 에 requests/eroomlib/PIL 없음 (`test_argv.py` 트리 가드가 집행)
- 반말 · 결론 먼저 (문서 톤)
- 검증은 `uat-verifier` 에 맡긴다 (사람 몫: 심미·실계정 실행 승인·네이버 로그인·법적 문구). **네이버 직접 접속 금지**
- GSD 워크플로 경유 편집

## Summary

이 페이즈는 **새 기술이 0개**다. 필요한 부품(subprocess 잡 엔진 · SSE 로그 tail · 미리보기→실행 targets 재사용 · caffeinate · 계정 가드 · CLI 체크포인트 · `--poll-only`)이 전부 이미 있고, 새로 짤 것은 ① `detail_batch.py` 주입구 플래그 6개 ② 웹앱 잡 kind 3개(`detail_estimate`·`detail_submit`·`detail_poll`) ③ 배너 관문 함수 교체 ④ 검수 화면 버튼 한 줄 ⑤ 견적/결과 화면이다. 새 패키지 설치 없음.

하지만 코드를 직접 읽고 실데이터를 세 보니 **CONTEXT 가 가정한 두 가지가 틀렸다.** 첫째, "회차 2026-09-20 은 60/60 확인 완료라 바로 접수 가능" 은 **D-02 ① 을 글자대로 적용하면 거짓이다** — `latest_done("banner_scan")` 이 가리키는 산출물 `banner_232c3bb3`(생성시각 2026-09-25T00:14)보다 모든 확인시각(최대 2026-09-23T00:55)이 앞선다. 지금 적격은 **0건**이고, D-03 수정 후 사람이 대상 상품을 다시 `확인함` 눌러야 열린다(첫 5건이면 클릭 5~6번). 둘째, 기작업(`구매_가공완료` 태그) 40건을 빼면 **🔴 적격 후보는 6건뿐**(🟡 10건)이고 그중 **5건이 제품 이미지 10장 초과**(16~29장)라 D-09 앞 10장 자르기가 첫 실탄 거의 전부에 걸린다. SC-1 의 "🔴 5건" 은 여유 1건으로 겨우 성립한다.

그리고 CLI 에 **실측 가능한 버그 2개**가 있다: 폴링 루프 종료 조건이 스킵·접수실패 건을 "끝남" 에 세어 **미완료 작업을 남긴 채 exit 0** 으로 나갈 수 있고(DETAIL-06 을 정면으로 깬다), 장수 불일치로 중단할 때 이미 접수된 그 1건의 작업번호를 체크포인트에 안 적어 재실행 시 이중 지불 경로가 생긴다. 둘 다 `--inputs` 모드 안에서 고치면 플래그 없는 동작은 바이트 단위로 불변이다.

**Primary recommendation:** CLI 패치(오프라인 테스트로 고정) → 관문 교체 + D-03 → 잡 3종 + 화면 → **사람 체크포인트: 6건 재확인 + 견적 승인** → 5건 실탄 → 두 번째 견적 0건 확인. 크레딧을 쓰는 건 실탄 단계 하나뿐이고 그 전 전부는 크레딧 0.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| 대상 선택(🔴 기본·🟡 수동) | Browser (`board.js` Tabulator) | API (`join.selectable`) | Phase 1/3 선택 UI 재사용(D-07). 기작업 제외는 서버 판정을 따른다 |
| 상세 입력 목록 생성(D-02 관문·라벨우선·중복제거·10장 자르기) | API (`webapp/banner.py` 순수 함수) | DB (`banner_label`·`banner_confirm`) | 순수 함수 + SQLite 읽기. 네트워크 0 |
| 입력 파일 기록(`inputs.json`) | API (`jobs.create_job` 경유) | Storage (`<회차>/web/detail_<id>/`) | 경로는 웹앱이 만든다(T-1-11) |
| 기작업 실시간 판정·장수 계산·견적 | CLI 자식 (`detail_batch.py --estimate-only`) | 불사자 MCP(읽기) | 웹앱 MCP 금지(L-04/D-19). 실시간 workdata 는 CLI 만 본다 |
| 접수·예상장수 검증·폴링 | CLI 자식 (`detail_batch.py`) | 불사자 MCP(쓰기·크레딧) | 기존 검증 로직 그대로 |
| 잡 생명주기·전역 쓰기 가드·수면방지 | API (`webapp/jobs.py`) | SQLite `jobs` | 기존 엔진 |
| 진행 로그 | API (`logtail.py` SSE) | Browser (htmx-ext-sse) | 파일 tail → 브라우저 닫아도 무관 |
| 결과 표(항목 단위 상태) | API (`detail_status.json` + 끝 리포트 읽기) | Browser | CLI 체크포인트가 정본. 잡 exit code 는 보조 |

## Standard Stack

새 라이브러리 **없음**. 전부 기존 스택이다 `[VERIFIED: 코드베이스 grep]`.

| 부품 | 위치 | 이 페이즈 용도 |
|------|------|---------------|
| `jobs.create_job` / `WRITE_KINDS` / `BULSAJA_KINDS` / `SINGLETON_KINDS` / `_수면방지_프리픽스` / `_override_targets` / `_reap` / `_finish` | `webapp/jobs.py` | 잡 3종 등록 |
| `argv.PY_CLI` + Pydantic argv 모델 | `webapp/argv.py` | `DetailArgv` 추가(조립은 이 파일 한 곳) |
| `logtail` + `_job_panel.html`/`_job_status.html` | 기존 | 진행 로그 SSE |
| `banner_store.라벨읽기`/`확인읽기`/`확인기록` | `webapp/banner_store.py` | + `확인시각읽기` 추가 |
| `state.기작업여부` | `webapp/state.py` | 교차 테스트 기준 |
| `ss_index_calls.항목꺼내기`/`워크데이터꺼내기` | `.claude/skills/bulsaja-detail-page/scripts/` | CLI 쪽 응답 해석(외부 import 0, 순수) |
| `BulsajaMCP` | `bulsaja-category-fix/scripts/bulsaja_mcp.py` | CLI 가 이미 씀 |

**Installation:** 없음.

## Package Legitimacy Audit

이 페이즈는 외부 패키지를 설치하지 않는다 — slopcheck 대상 없음.
**Packages removed:** none · **Packages flagged:** none

## 코드 실측 — `detail_batch.py` 현재 동작 (381줄) `[VERIFIED: 파일 전문 읽음]`

| 항목 | 현재 동작 | 비고 |
|------|----------|------|
| 인자 | `--run-dir`(필수·경로) `--pages`(10) `--quality`(standard) `--limit` `--submit-only` `--poll-only` `--retry-failed` `--force` `--poll-interval`(45) `--max-poll-min`(240) `--sleep`(1.0) `--dup-wait`(60) `--dup-rounds`(8) | `--run-dir` 은 회차 이름이 아니라 **디렉터리 경로**다 |
| 대상 | `<run-dir>/products.json` (문자열 또는 `{"productId"}` 리스트) | productId = 불사자 내부 ID(`U01K…`) |
| 체크포인트 | `<run-dir>/detail_status.json` `{pid: {taskId, status, pages, ...}}` — **run-dir 단위 누적** | 웹 잡마다 전용 하위 디렉터리 필수 |
| `get_workdata` | `bulsaja_product_workdata(mode="summary")` → `data` | summary 에 `uploadDetailContents` 는 있고 `uploadBulsajaCode`·그룹태그는 **없다** (bulsaja_scan.py:404-416 실측 주석) |
| `existing_ai_detail` | `aiImageGenerated` 참이면 `{pages, at}` | 내장 truthiness — 문자열 `'0'` 이 참이 되는 함정(state.py `불리언정규화` 참조) |
| `collect_images` | 썸네일 + 옵션 이미지, cap 장 | inputs 모드에서 우회 |
| `submit_one` | workdata → 이미지 → `sc=max(2,min(pages,len))` → `prev["pages"] >= sc` 면 `AlreadyDone` → generate(confirm=False)→토큰→confirm=True → taskId → `예상장수` int 이고 ≠ sc 면 RuntimeError("장수 불일치") | D-12 로 스킵 조건 교체 |
| 장수 불일치 | `sys.exit(2)` (체크포인트 저장 후) | 그 1건 taskId 는 **저장 안 됨** |
| 견적 출력 | `len(todo) × pages × per_credit` (예상 **최대**) | 스킵·실장수 미반영 |
| 폴링 | deadline = `max_poll_min` · pending 없으면 break · `done+fail >= taskId보유수` 면 break · 타임아웃이면 루프만 빠짐 | **타임아웃과 완료가 같은 exit 0** |
| 센티널 | `###DETAIL### 완료 N (신규 a + 기작업스킵 b) / 실패 f / 전체 t` 마지막 줄 | 폴링미완 수가 없다 |
| 종료코드 | 0 정상(타임아웃 포함) · 1 `--pages` 범위 · 2 장수 불일치 · 기타 예외는 파이썬 기본 1 | |
| 계정 가드 | **없음** | bulsaja_scan 은 `--expect-nick` 자가검증이 있다 |
| MCP 반환 | `mcp.call_tool(name, args)` → dict | 오프라인 스텁 가능 |

## CLI 패치 설계 (주입구 플래그만 · 플래그 없으면 바이트 불변)

모든 새 분기는 `if args.inputs:` 안에 둔다. 플래그 없는 경로의 코드 줄은 건드리지 않는다(01-02 `--only-ads` 선례).

| 플래그 | 뜻 | 구현 자리 |
|--------|----|----------|
| `--inputs <json>` | `{"items":[{"productId","판매자상품코드","imageUrls":[...],"제품이미지총수":N}]}`. 있으면 pids = items 순서, `products.json` 무시, `collect_images` 안 탐 | `main()` 대상 로딩 · `submit_one` 에 `imgs_override` 인자 |
| `--done-tags <json 또는 반복 인자>` | D-12 태그 목록. inputs 모드에서 **필수**(없으면 exit 2 — 빈 목록이 "태그 안 봄" 으로 새지 않게) | 스킵 판정 |
| `--estimate-only` | workdata + 태그 조회 + 스킵 판정 + 장수 계산만. generate 0회 | 접수 루프 대신 견적 루프 |
| `--estimate-out <json>` | 견적 산출물 경로 | 아래 모양 |
| `--max-credits N` | 접수 누적 예상크레딧이 N 을 넘기려 하면 그 건 접수 전 exit 5 | D-14 증가 방향 차단 |
| `--expect-nick <닉>` | 시작 시 `bulsaja_my_profile` 1회, 다르면 exit 4 (bulsaja_scan `계정확인` 관용구) | L-06 자가검증 |
| `--summary-out <json>` | 종료 시 항목별 상태·크레딧 집계 | 결과 화면 정본 |

**D-12 절대조건 (inputs 모드에서만):**
```python
# 스킵 = 태그가 done_tags 안 OR aiImageGenerated 참 — 목표 장수와 무관 (STATE-05)
def 기작업(태그, dc, done_tags):
    t = (태그 or "").strip()
    if t and t in {str(x).strip() for x in done_tags}:
        return True
    return 불리언정규화((dc or {}).get("aiImageGenerated"))   # state.py 와 같은 정규화
```
- 태그는 workdata summary 에 없다 → **`bulsaja_product_find_by_code {"codes":[판매자상품코드...]}` 배치 1회**(50개/회, 실측 0.53초 — bulsaja_scan.py:216). 응답 해석은 `ss_index_calls.항목꺼내기`(외부 import 0 · 같은 디렉터리라 스크립트 실행 시 sys.path[0] 로 잡힌다). 항목 중 `판매자상품코드 == 대상코드` 인 것의 `그룹` 을 쓴다.
- **태그 조회 실패 = 접수 안 함**(fail-closed, CR-02 규율). 그 건은 `status: "태그미조회"` 로 남기고 견적에서 빠진다.
- `불리언정규화` 는 `state.py` 의 6줄을 CLI 에 **복제**한다(웹앱 import 금지 방향과 반대라 CLI 가 웹앱을 import 하지도 않는다). 두 복제본의 일치는 교차 테스트가 집행한다.

**`--estimate-out` 모양(권장):**
```json
{"생성시각": "...", "계정": "<닉>", "잔액": {...참고용}, "per_credit": 5,
 "항목": [{"productId": "...", "판매자상품코드": "...", "판정": "접수|기작업|태그미조회|입력부족",
           "사유": "...", "장수": 10, "제품이미지총수": 27, "잘림": 17, "크레딧": 50}],
 "집계": {"선택": N, "스킵": M, "접수": K, "총장수": P, "예상크레딧": C, "잘린상품": X}}
```
`잘림`/`제품이미지총수` 는 웹앱이 inputs 에 넣어 준 값을 그대로 옮긴다(자르는 건 웹앱, 보고는 CLI 가 한 파일에 모음).

**종료코드(권장):** 0 전부 종결 · 2 장수 불일치/입력 오류(기존 의미 유지) · **3 폴링 미완(타임아웃, 실패 아님)** · 4 계정 불일치 · 5 견적 초과. `caffeinate -i` 가 exit code 를 그대로 넘기는 것은 실측됨(jobs.py:559 주석).

## 웹앱 설계

### 시스템 흐름

```
보드(선택 🔴/🟡) ──POST /jobs/detail/estimate {run_dir, keys[]}──▶ 라우트
   │                                                                │
   │                 banner.상세입력목록(산출물, 라벨, 확인시각)  ◀──┤ (순수·네트워크0)
   │                 join 산출물로 판매자상품코드→productId          │
   │                 inputs.json 기록 (<회차>/web/detail_<id>/)      │
   │                                                                ▼
   │                         create_job("detail_estimate")  ── BULSAJA_KINDS(계정 사전점검)
   │                                    │ subprocess
   │                                    ▼
   │                  detail_batch.py --inputs --estimate-only --estimate-out
   │                      (workdata·find_by_code 읽기, 크레딧 0)
   ▼
견적 표(N→M 스킵→K · 장수 · 크레딧 · 잘린 상품 · 계정 · 잔액)
   │  [사람: 접수 버튼 = 승인]  ◀── L-01 체크포인트
   ▼
POST /jobs/detail/submit {estimate_job_id}  ── 대상 안 받음(부모 파일만)
   │  create_job("detail_submit") WRITE_KINDS · caffeinate · parent=estimate
   ▼
detail_batch.py --inputs(같은 파일) --max-credits C --expect-nick --summary-out
   접수 → 예상장수 검증 → 폴링 ─┬─ 전부 종결 → exit 0
                                 └─ 시간 상한 → exit 3 "폴링 미완"
   ▼ (로그 파일 → SSE, 브라우저 닫아도 계속)
결과 표 ← detail_status.json + summary.json (정본) ; exit 3 이면 [이어서 확인]
   ▼
POST /jobs/detail/poll {submit_job_id} → detail_batch.py --poll-only (같은 run-dir)
```

### 파일 배치(권장)
```
<runs>/<회차>/web/
├── targets_<estimate_id>.json          # = inputs.json (목록 파일 규약: web/ 바로 밑이어야 _override_targets 통과)
└── detail_<estimate_id>/               # CLI --run-dir (견적·접수·이어서확인이 같은 폴더 공유)
    ├── estimate.json
    ├── detail_status.json              # CLI 체크포인트 (재개 정본)
    └── summary_<job_id>.json
```
`_override_targets` 는 `p.parent == web/` 를 요구한다(jobs.py:512) — inputs 파일은 `web/` 바로 밑에 둬야 접수 잡이 부모 파일을 그대로 가리킬 수 있다. detail 하위 디렉터리는 **견적 잡 id 로 이름 짓고** 접수·이어서확인이 부모 체인을 따라 같은 폴더를 받는다.

### jobs.py 변경 목록
- `JobKind`/`KINDS` 에 `detail_estimate`·`detail_submit`·`detail_poll` (둘 **같이** 고친다 — 주석 경고)
- `WRITE_KINDS += {"detail_submit", "detail_poll"}` — poll 도 크레딧은 안 쓰지만 같은 `detail_status.json` 을 쓰므로 submit 과 겹치면 체크포인트가 깨진다. **estimate 는 넣지 않는다**(읽기)
- `BULSAJA_KINDS += 세 개 전부` (L-06 사전점검 · profile_max_age_min 120분)
- `SINGLETON_KINDS += {"detail_estimate"}` (레이트리밋 · 429 todo 와 같은 계열)
- `_수면방지_프리픽스`: `("bulsaja_index","banner_scan","detail_submit","detail_poll")`
- `_build_argv`: 세 kind 분기 — **targets_path None 이면 ValueError**(빈 값이 전량 규율 5번째 적용)
- `_finish(cx, job_id, code)` 에 kind 를 넘겨 **detail kind 의 exit 3 → status `done` 유지 + exit_code 3** (또는 새 상태 `incomplete`). 권장: 새 상태를 만들지 말고 `done`+`exit_code=3` 으로 두고 화면이 해석 — `latest_done`·가드 쿼리를 안 건드린다
- `result_path` = `detail_<부모>/estimate.json` 또는 `summary_<job>.json`

### DetailArgv (argv.py)
```python
class DetailArgv(BaseModel):
    """detail_batch.py 호출 1회. 설정값은 전부 호출부가 settings.cfg 로 읽어 넘긴다(T-1-12)."""
    mode: Literal["estimate", "submit", "poll"]
    run_dir: Path            # --run-dir  detail_<estimate_id>/ 절대경로
    inputs: Path             # --inputs   (poll 모드도 넘긴다 — pid 집합 확인용)
    done_tags: list[PlainArg]  # --done-tags (빈 리스트면 build 가 예외)
    expect_nick: Nick
    estimate_out: Path | None = None
    summary_out: Path | None = None
    max_credits: int | None = None   # submit 필수
    max_poll_min: int
    poll_interval: int
    prefix: list[str] = []
```
`DETAIL_BATCH` 경로 상수는 `SS_INDEX_BUILD` 옆에. `test_argv.py` 트리 가드(셸 경유 0 · requests/eroomlib import 0)가 자동으로 집행.

### 관문 교체 — `banner.py` (D-02)

현재 `제품이미지목록(상품, 게이트통과=False)` 은 `게이트통과 is not True` 면 예외 → 게이트가 false(D-23)라 **영원히 0건**. 교체안:

```python
def 상세입력목록(상품: dict, *, 라벨: dict, 확인시각: str | None, 생성시각: str,
            잔여하한: int, 상한: int = 10) -> dict:
    """D-02 관문. 기본값으로 열리는 길 없음 — 키워드 인자 누락 = TypeError."""
    # ① 확인시각 None 이거나 < 생성시각 → ValueError("재스캔 뒤 다시 확인 안 함")
    #    (datetime.fromisoformat 로 비교 — 문자열 비교 금지, 오프셋 다를 수 있다)
    # ② 스킵사유읽기(상품) 있으면 ValueError (D-04, 재계산 금지)
    # ③ 유효판정 = 라벨.get(순번, 기계판정); '미판정' 하나라도 → ValueError
    # ④ 제품 = [장 for 장 in 장들 if 유효판정 == '제품'] (무내용·배너 제외, 원래 순서)
    # ⑤ URL 중복 제거(순서 유지) — BANNER-01 이 Phase 5 로 넘긴 일
    # ⑥ len < 잔여하한 → ValueError
    # ⑦ return {"urls": 앞 상한장, "총수": len, "잘림": max(0, len-상한)}
```
- **기계 `제품이미지` 필드를 쓰지 않는다** — 그건 기계 판정 기준이라 라벨 우선이 안 된다(D-23 ①). `장` 목록 + 라벨로 다시 고른다.
- 기존 `제품이미지목록` 은 삭제하지 말고 남겨도 되지만 테스트 15곳(`test_banner.py`·`test_banner_scan.py`)이 참조한다. 권장: 새 함수를 추가하고 옛 함수는 그대로 두어 기존 테스트 불변. Phase 5 입력 경로는 새 함수만 부른다.
- `banner_store.확인시각읽기(run_dir) -> {상품키: 확인시각}` 추가(`확인읽기` 와 같은 ro 규율).

### D-03 검수 화면 수정
`banner_review.html:304-318`: `{% if 상품.확인됨 %}` 이면 배지만 그린다. 수정 = 배지 + `확인함`(다시 확인) 버튼을 같이 그린다(같은 `hx-post="/banner/confirm"`). 권장 보강: 라우트 `_화면투영` 이 `확인됨` 을 "확인시각 ≥ 산출물 생성시각" 으로 계산하면 낡은 확인이 화면에서 바로 보인다 — D-03 범위 안(버튼 조건 한 줄)으로 볼 수 있다. `확인기록` 은 이미 `INSERT OR REPLACE` 라 재클릭이 시각을 갱신한다(서버 쪽 수정 불필요).

### 교차 테스트 (D-12)
웹앱 런타임은 CLI 를 import 하지 않는다. 테스트 프로세스만 허용(test_cli_patch.py 선례):
```python
# webapp/tests/test_detail_cli.py
import importlib.util, sys, types
def _load(monkeypatch):
    stub = types.ModuleType("bulsaja_mcp"); stub.BulsajaMCP = object
    monkeypatch.setitem(sys.modules, "bulsaja_mcp", stub)   # 네트워크 코드 대체
    spec = importlib.util.spec_from_file_location("_detail_batch_under_test", DETAIL_BATCH)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

표본 = [("구매_가공완료", {}, True), (None, {"aiImageGenerated": "1"}, True),
       (None, {"aiImageGenerated": "0"}, False), (None, {}, False),
       ("구매_가공완료 ", {"aiImageGenerated": False}, True),
       (None, {"aiImageGenerated": True, "aiImageOutputCount": 1}, True)]  # 1장 사고분도 스킵(절대조건)
@pytest.mark.parametrize("태그,dc,기대", 표본)
def test_기작업_규칙_일치(monkeypatch, 태그, dc, 기대):
    cli = _load(monkeypatch)
    assert state.기작업여부(태그, dc, ["구매_가공완료"]) == cli.기작업(태그, dc, ["구매_가공완료"]) == 기대
```
`detail_batch.py` 는 최상위에서 `from bulsaja_mcp import BulsajaMCP` 만 하므로 `sys.modules` 스텁으로 `.venv-web` 에서 로드된다(bulsaja_mcp 가 끌고 오는 eroomlib 을 안 탐). **확인 필요:** 로드 전에 `sys.path.insert` 가 실행돼도 모듈 캐시가 우선이라 문제없다 `[ASSUMED — 표준 import 동작, Wave 0 에서 1회 실측]`.

같은 방법으로 **가짜 MCP**(`call_tool` 이 시나리오 dict 를 돌려주는 클래스)를 `m.BulsajaMCP` 에 주입하고 `main()` 을 `sys.argv` 몽키패치로 돌리면 접수·폴링 전체가 오프라인으로 테스트된다(`time.sleep` 도 몽키패치).

## 실데이터 — 회차 2026-09-20 (네트워크 0, 파일·DB 직접 집계) `[VERIFIED]`

| 사실 | 값 |
|------|----|
| `latest_done("banner_scan","2026-09-20")` | `232c3bb3…` · 산출물 생성시각 **2026-09-25T00:14:25** · 62상품(사본 2) · 비전 2차 사용 |
| 이전 산출물 | `97c3578d…` · 생성시각 2026-09-22T03:54 |
| `banner_confirm` | 60건 · 확인시각 2026-09-22T15:11 ~ **2026-09-23T00:55** → **최신 산출물 대비 전부 낡음** |
| `banner_label` | 135건 · 그중 **103건이 최신 산출물 이후 기록**(재검수는 했는데 확인 버튼은 못 누름 = D-03 결함 그대로) |
| 조인 산출물 | `join_0889aa1f…` (두 배너 잡 모두의 입력) · 배너 62상품 전부 판매자상품코드로 매칭 · 코드당 productId 1개 |
| 기작업(`구매_가공완료` 태그 등) | 60 중 **40** |
| 배너 스킵 | 4 |
| **D-02 ②③ 통과(①신선도 제외)** | **🔴 6 · 🟡 10** |
| 🔴 6건 제품장수(라벨우선) | 27 · 10 · 29 · 20 · 21 · 16 → **5/6 이 10장 초과** |
| 적격 16건 중 10장 초과 | 9 |
| **D-02 ① 까지 적용한 지금 적격** | **0** |

→ SC-1 첫 5건은 이 6건 중에서 고른다. 최대 5 × 10 × 5 = **250크레딧**. 실탄 전 **사람이 6건만 다시 `확인함`**(D-03 수정 후) 하면 열린다 — 11분 전수가 아니라 1~2분.

## Common Pitfalls

### Pitfall 1: 폴링 조기 종료 — 미완료를 남기고 exit 0 `[VERIFIED: 코드]`
**What goes wrong:** `done + fail >= (taskId 보유 수)` 에서 `done` 은 `완료(기작업)`(taskId 없음)을, `fail` 은 `접수실패`(taskId 없음)를 센다. 5건 접수 + 1건 스킵이면 4건만 끝나도 5 ≥ 5 로 break → 1건 폴링중인데 `###DETAIL###` 찍고 exit 0.
**How to avoid:** inputs 모드에서 종료 조건을 "taskId 가 있고 완료/실패 아닌 건 = 0" 으로 직접 센다. 타임아웃으로 나가면 exit 3. 센티널에 `폴링미완 N` 추가(센티널 줄 모양 바꾸는 건 inputs 모드만).
**Warning signs:** 잡 `done` 인데 `detail_status.json` 에 `접수` 상태 항목이 남아 있다.

### Pitfall 2: 장수 불일치 중단 시 이미 접수된 1건이 체크포인트에서 사라진다 `[VERIFIED: 코드]`
**What goes wrong:** `submit_one` 이 taskId 를 받은 **뒤** RuntimeError 를 던지고 `try_submit` 은 status 에 안 적고 exit 2. 다음 실행은 그 상품을 미접수로 보고 다시 접수 → 이중 지불.
**How to avoid:** inputs 모드에서 불일치 시 `{taskId, status:"장수불일치", 요청장수, 서버장수}` 를 저장하고 exit 2. `예상장수` 가 없거나 int 가 아니면(문자열 "10장" 등) **통과시키지 말고** 같은 처리(현행은 `isinstance(exp,int)` 가 아니면 조용히 통과). 첫 실탄 로그에서 실제 응답 모양을 확인.

### Pitfall 3: 최신 배너 산출물이 모든 확인보다 새롭다 → 적격 0건 `[VERIFIED: DB]`
**How to avoid:** 플랜에 "D-03 수정 → 사람이 첫 실탄 후보 6건 재확인" 을 **실탄 체크포인트 전 사람 단계**로 넣는다. 옛 산출물(`97c3578d`)로 우회하지 않는다 — 사람 라벨 103건이 새 산출물 기준으로 찍혔고, 기계 판정도 달라 라벨우선 합성이 섞인다.

### Pitfall 4: 서버 재시작하면 exit code 가 사라진다 `[VERIFIED: jobs.py _reap]`
**What goes wrong:** `uvicorn --reload`(코드 수정)·재부팅이면 `_PROCS` 가 비고, 자식은 `start_new_session` 으로 살아서 끝난 뒤 `orphaned`(exit_code NULL)로 찍힌다. exit 3 판별이 불가능.
**How to avoid:** 결과 화면은 **`detail_status.json`(+ summary)을 정본으로** 항목별 상태를 계산한다. 잡 status/exit_code 는 보조 표시. `orphaned` 여도 체크포인트에 미완료가 있으면 `이어서 확인` 을 보인다. **실탄 도중엔 웹앱 코드를 고치지 않는다**(--reload).

### Pitfall 5: 관측자 없으면 잡이 `running` 에 갇힘 (todo job-reap-depends-on-polling) `[CITED: .planning/todos/pending]`
**What goes wrong:** 브라우저를 닫은 채 접수 잡이 끝나면 DB 는 계속 `running`. `ended_at` 은 "눈치챈 시각".
**Impact on SC-1:** 실해는 작다 — `create_job`·`job_status`·`recent_jobs` 가 먼저 `_reap` 하므로 다음 화면 열기·다음 잡 생성 때 닫힌다(같은 서버 프로세스면 `_PROCS` 에 Popen 이 있어 `poll()` 로 정확히 수거). SC-1 검증 때 "브라우저 재오픈 → 즉시 done/exit 표시" 를 확인하고, 소요시간은 `ended_at` 대신 CLI 로그 타임스탬프로 본다. 고치지 않는다(Deferred).

### Pitfall 6: 오류 응답을 서버 실패로 오판 (D-18) `[VERIFIED: 코드]`
**What goes wrong:** `extract_status` 가 status 키를 못 찾으면 응답 JSON 문자열을 돌려주고, `is_failed` 는 `"error"`·`"오류"` 부분문자열만 봐도 실패로 친다. MCP 가 예외 대신 오류 dict 를 돌려주면 일시 오류가 영구 `실패` 가 된다.
**How to avoid:** inputs 모드에서 status 키를 못 찾으면 `poll_error` 로만 적고 상태는 바꾸지 않는다(다음 라운드 재시도).

### Pitfall 7: `detail_status.json` 은 run-dir 누적 — 섞이면 스킵·완료 집계가 오염
**How to avoid:** 견적 잡마다 새 `detail_<id>/`. 접수·이어서확인은 부모 체인의 폴더만. 두 번째 회차(SC-3)는 **새 견적 = 새 폴더**라 체크포인트가 아니라 서버 플래그(D-12)로 스킵된다는 게 증명된다.

### Pitfall 8: 🟡 인데 태그가 붙은 행
실데이터 첫 행이 `상세상태=중국어원본` 인데 `그룹태그=구매_가공완료` 다(외부 반영 경로). 보드의 🔴 표시만 믿으면 기작업이 섞인다 — 서버 `join.selectable` + CLI 실시간 태그 조회 둘 다 걸러야 한다(이미 설계에 있음).

### Pitfall 9: 이미지 URL 접근성
적격 상품 중 alicdn 원본 URL 이 있다(한 상품은 HTTP 403 으로 판정불가 스킵). 불사자 서버가 그 URL 을 못 받으면 생성 실패/장수 불일치로 나타날 수 있다 `[ASSUMED]`. 첫 실탄 5건에서 관찰만 하고, 실패는 D-18 대로 `실패` 로 남긴다.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| 재개·체크포인트 | 웹앱 잡 레코드로 상품 상태 추적 | CLI `detail_status.json` + `--poll-only` | 정본이 둘이면 이중 지불 |
| 기작업 판정 | 로컬 대장/웹앱 캐시 | CLI 가 접수 직전 workdata+find_by_code | L-05 |
| 진행 스트리밍 | 파이프·WebSocket | 기존 로그파일 tail SSE | 브라우저 닫기 생존 |
| 백그라운드 실행 | 큐·스레드 | `create_job` + `start_new_session` | 기존 |
| 응답 해석 | 새 파서 | `ss_index_calls.항목꺼내기`/`워크데이터꺼내기` | CR-01~03 교훈 내장 |
| 불리언 플래그 읽기 | `bool(v)` | `불리언정규화` 복제 + 교차 테스트 | `'0'` 이 참 |

## Code Examples

### 가짜 MCP 로 오프라인 end-to-end
```python
class 가짜MCP:
    def __init__(self, 시나리오): self.호출 = []; self.s = 시나리오
    def open(self): pass
    def close(self): pass
    def call_tool(self, name, args):
        self.호출.append((name, dict(args)))
        return self.s[name](args)    # 시나리오별 응답 함수

# 단언 예: generate 호출의 args 에 imageUrls 와 sectionCount 가 동시에 있다 (DETAIL-03)
# 단언 예: --estimate-only 에서 bulsaja_detail_page_generate 호출 0회 (L-01)
# 단언 예: 예상장수 불일치 → exit 2 + detail_status 에 taskId 보존 (Pitfall 2)
# 단언 예: 폴링 deadline 도달 → exit 3, 센티널에 폴링미완 (DETAIL-06)
# 단언 예: --max-credits 초과 → generate 호출 전 exit 5 (D-14)
```

### 플래그 없는 동작 불변 증명
기존 코드 경로를 건드리지 않는 것이 1차 방어. 2차로 가짜 MCP 로 플래그 없이 돌린 호출 순서·인자 목록을 **패치 전 커밋에서 기록한 골든**과 비교(`git stash` 불필요 — 패치 첫 커밋 전에 골든 파일을 생성해 fixtures 에 둔다).

## State of the Art

| Old | Current | Impact |
|-----|---------|--------|
| 스킵 = `prev.pages >= sc` | 절대조건(태그 OR aiImageGenerated) | 8장 기작업이 10장 목표로 재접수되던 경로 차단 |
| 입력 = 썸네일+옵션 | 기존 상세 − 배너(라벨우선) | DETAIL-01 |
| 게이트 전역 통과 | 상품별 사람 확인(D-01/02) | BANNER-04 문구 사실상 대체 — 용팀장 확인 필요 |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `sys.modules` 스텁으로 `detail_batch.py` 를 `.venv-web` 에서 로드 가능 | 교차 테스트 | 테스트를 `.venv` 로 돌려야 함(webapp/tests/cli/ 로 이동) — 작은 비용 |
| A2 | `bulsaja_product_find_by_code` 응답 항목의 `그룹` 이 태그 정본(bulsaja_scan 1단과 동일) | CLI 패치 | 태그 스킵 누락 → 이중 지불. bulsaja_scan 이 실탄에서 이미 이 필드로 기작업 29건을 잡았으므로 위험 낮음 |
| A3 | `detail_page_generate` 가 완료 시 `aiImageGenerated` 를 찍는다 | D-13 | 안 찍어도 첫 5건에 태그가 없으므로 두 번째 견적에서 재접수 대상이 됨 → D-13 폴백(태그 쓰기, L-01 ④) 필요. 첫 실탄 후 재조회로 판정 |
| A4 | 불사자 서버가 alicdn 원본 URL 을 입력으로 받아들인다 | Pitfall 9 | 해당 건 실패/장수불일치 — exit 2 가 전량 멈추게 해 크레딧 손실은 1건 한정 |
| A5 | 접수 응답 `예상장수` 가 int 다 (SKILL 실측 "예상 10장, 50크레딧") | Pitfall 2 | 문자열이면 현행은 검증을 건너뛴다 — inputs 모드 fail-closed 로 막음 |

## Open Questions (RESOLVED)

1. **D-02 ① 을 지금 회차에 어떻게 여는가** — 권장: D-03 수정 후 첫 실탄 후보 6건만 사람이 재확인(1~2분). 옛 산출물 사용 금지. 실탄 체크포인트와 같은 사람 단계에 묶으면 사람 큐가 하나로 끝난다. → **RESOLVED:** 05-02(D-03 다시 확인 버튼) + 05-05 Task 1(사람 재확인, 첫 유료 체크포인트와 같은 정지).
2. **D-09 앞 10장 자르기가 첫 실탄 5/6 에 걸린다** — CONTEXT 가 "초과 비율을 견적 화면에 띄워 판단 재료로" 라 했다. 실측 비율(🔴 5/6, 전체 9/16)을 확인 질문에 같이 올린다. → **RESOLVED:** 05-05 Task 1 의 D-09 한 줄에 실측 비율 포함.
3. **`detail_poll` 을 WRITE_KINDS 에 넣을까** — 권장: 넣는다(같은 체크포인트 파일 동시 쓰기 방지). 부작용은 폴링 중 입찰가 인상이 409 — 수 분~수십 분이라 수용 가능. 싫으면 "같은 detail 폴더 잡 중복" 전용 가드로 대체. → **RESOLVED:** 넣는다 — 05-03 Task 1.
4. **`--max-poll-min` 기본값** — CLI 기본 240분. 설정 `detail_max_poll_min` 으로 넘기되(S-4) 기본 60분 권장 — 생성은 수 분이고, 넘기면 exit 3 → `이어서 확인` 이 싸다. → **RESOLVED:** 설정 `detail_max_poll_min`=60 — 05-03 Task 1.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `.venv/bin/python3` (CLI) | detail_batch | ✓ | 3.12 | — |
| `.venv-web` pytest | 테스트 | ✓ | 전 스위트 12초 통과 | — |
| `/usr/bin/caffeinate` | 수면방지 | ✓ (기존 잡이 씀) | — | 없으면 안 붙임(기존 로직) |
| 불사자 MCP(`bulsaja` 항목) | 견적·실탄 | 실탄 때만 | — | 없음 — 실탄 체크포인트에서 확인 |
| 헤드리스 크롬(CDP) | `board_cdp.sh` 계층 | ✓ (기존 스크립트) | — | uat-verifier(Playwright) |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (`.venv-web`), 설정 `webapp/pytest.ini` (`cli/` 수집 제외) |
| Quick run | `.venv-web/bin/pytest webapp/tests/test_detail_cli.py webapp/tests/test_banner.py -q` |
| Full suite | `.venv-web/bin/pytest webapp/tests -q` (현재 전부 통과 · 약 12초) |
| 브라우저 계층 | `CT_DEV_TOKEN=… bash webapp/tests/board_cdp.sh` / `banner_cdp.sh` / `sse_cdp.sh` (살아 있는 서버 필요) + uat-verifier |

### Phase Requirements → Test Map
| Req ID | Behavior | Type | Command | File Exists? |
|--------|----------|------|---------|-------------|
| DETAIL-01 | `--inputs` 면 collect_images 미호출 · imageUrls = 입력 그대로 | unit(가짜 MCP) | `pytest webapp/tests/test_detail_cli.py -k 입력` | ❌ Wave 0 |
| DETAIL-01 | 관문: 낡은 확인·스킵·미판정·<2장 → 예외, 라벨우선·무내용 제외·중복 제거·10장 자르기 | unit | `pytest webapp/tests/test_banner.py -k 상세입력` | 파일 ✅ / 테스트 ❌ |
| DETAIL-02 | sc = max(2,min(n,10)); inputs <2장 거부 | unit | `-k 장수` | ❌ |
| DETAIL-03 | generate args 에 imageUrls·sectionCount 동시 | unit | `-k 동시` | ❌ |
| DETAIL-04 | 예상장수 ≠ sc 또는 비정수 → exit 2 + taskId 보존 | unit | `-k 불일치` | ❌ |
| DETAIL-05 | estimate-only 에서 generate 0회 · 견적 JSON 집계 · max-credits 초과 exit 5 | unit | `-k 견적` | ❌ |
| DETAIL-05 | 접수 라우트는 대상 안 받고 부모 targets 만 | route | `pytest webapp/tests/test_routes_jobs.py -k detail` | 파일 ✅ / 테스트 ❌ |
| DETAIL-06 | deadline → exit 3 · 조기종료 버그 재현 테스트 · `_finish` 가 detail exit3 을 실패로 안 적음 | unit | `-k 폴링미완` + `pytest webapp/tests/test_jobs.py -k detail` | ❌ |
| DETAIL-07 | `--poll-only` 가 같은 run-dir 체크포인트로 이어짐 · poll 라우트는 submit 부모 체인만 | unit+route | `-k 이어서` | ❌ |
| D-12 | 웹앱·CLI 기작업 규칙 교차 일치 | unit | `-k 기작업_규칙_일치` | ❌ |
| L-04 | 플래그 없는 호출 순서·인자 골든 불변 | unit | `-k 플래그없음` | ❌ (골든을 패치 전 생성) |
| L-06 | detail kind 가 BULSAJA_KINDS · `--expect-nick` 불일치 exit 4 | unit | `pytest webapp/tests/test_jobs.py -k 계정` | 파일 ✅ |
| D-03 | 확인된 상품에도 재확인 버튼 | route(HTML) + cdp | `pytest webapp/tests/test_routes_banner.py -k 다시확인` | 파일 ✅ |
| SC-1 | 5건 실탄 · 브라우저 닫고 완주 | **manual + uat-verifier** | 사람 승인 후 실행 · 재오픈 시 done 확인 | — |
| SC-3 | 같은 목록 두 번째 견적 접수 0 | 실측(크레딧 0) | 견적 잡 재실행 | — |

### Sampling Rate
- 태스크 커밋마다: quick run
- 웨이브 병합마다: full suite + `test_argv.py` 트리 가드
- 실탄 체크포인트 전: full suite green + uat-verifier(견적 화면까지, 크레딧 0)

### Wave 0 Gaps
- [ ] `webapp/tests/test_detail_cli.py` — 가짜 MCP · `sys.modules` 스텁 로더 · 골든(패치 **전** 커밋에서 생성)
- [ ] `webapp/tests/fixtures/detail_inputs_*.json` — 익명화(`zz*` 코드, `zzcdn.example`) 규율
- [ ] `test_banner.py` 에 `상세입력목록` 케이스 · `test_routes_jobs.py` detail 라우트 · `test_jobs.py` kind 등록/가드

## 크레딧 0 작업 vs 크레딧 소비 작업 (L-01)

| 단계 | 크레딧 | 외부 쓰기 | 사람 |
|------|--------|-----------|------|
| CLI 패치 + 오프라인 테스트 | 0 | 없음 | — |
| 관문 교체 · D-03 · 잡 3종 · 화면 | 0 | 없음 | — |
| 견적 잡 실행(workdata·find_by_code·잔액 조회) | 0 | 없음(MCP 읽기) | — |
| 6건 재확인 클릭 | 0 | 로컬 DB | **사람** |
| **5건 접수 실탄** | **≤250** | 불사자 AI 생성(상세 자동 반영) | **blocking checkpoint (L-01 ①)** |
| 이어서 확인(`--poll-only`) | 0 | 없음 | — |
| 두 번째 견적(SC-3) + aiImageGenerated 재조회(D-13) | 0 | 없음 | — |
| (조건부) 태그 쓰기 폴백 | 0 | 불사자 태그 | **blocking checkpoint (L-01 ④)** |

## Security Domain

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2/V3 Authentication/Session | no (127.0.0.1 · 1인) | 기존 X-CT-Token 쓰기 가드 |
| V4 Access Control | yes | 쓰기 라우트 토큰 필요(기존 `security.py`) |
| V5 Input Validation | yes | Pydantic 요청 모델 — 접수/이어서확인은 **job_id 하나만** 받음; 선택 키는 조인 산출물에 있는 것만 통과 |
| V12 Files | yes | 경로는 웹앱이 생성 · `_override_targets` 부모 디렉터리 검사 · 회차 화이트리스트 |
| V6 Crypto | no | — |

| Threat | STRIDE | Mitigation |
|--------|--------|-----------|
| 명령 주입(닉네임·태그가 `--force` 모양) | Tampering | `DetailArgv` 의 `Nick`/`PlainArg` 제약 · 리스트 argv |
| 견적과 다른 대상 접수 | Tampering | 부모 targets 재사용 + `--max-credits` |
| 계정 오접속으로 남의 크레딧 소비 | Spoofing | BULSAJA_KINDS 사전점검 + CLI `--expect-nick` |
| 이중 지불(재접수) | Repudiation/비용 | 체크포인트 · exit 3 화면에 재접수 버튼 없음 · Pitfall 1/2 수정 |

## Sources

### Primary (HIGH)
- `.claude/skills/bulsaja-detail-page/scripts/detail_batch.py` 전문 · `bulsaja_scan.py:400-510, 211-246` · `ss_index_calls.py`(import 0 확인)
- `webapp/jobs.py`(1053줄 핵심부) · `argv.py` · `banner.py` · `banner_store.py` · `state.py` · `routes/jobs.py:160-503` · `routes/banner.py:347-500` · `templates/banner_review.html:280-320`
- `webapp.db` 직접 조회(banner_confirm 60 · banner_label 135 · jobs) · `<runs>/2026-09-20/web/banner_232c3bb3…json`·`banner_97c3578d…json`·`join_0889aa1f…json` 집계
- `.planning/phases/04-banner-detection/04-12-SUMMARY.md`(확인시각 < 생성시각 기록) · `04-GATE.md` §17 · `.planning/todos/pending/job-reap-depends-on-polling.md`
- `.venv-web/bin/pytest webapp/tests` 전부 통과(2026-09-25)

### Tertiary (LOW)
- A3/A4 — 첫 실탄으로만 확정 가능

## Metadata

**Confidence breakdown:**
- CLI 동작·버그: HIGH — 전문을 읽고 분기별 확인
- 웹앱 통합 지점: HIGH — 기존 패턴 그대로
- 실데이터 적격 건수: HIGH — DB·산출물 직접 집계(태그는 조인 산출물 시점 기준, 실시간 아님)
- aiImageGenerated 기록 여부(D-13): LOW — 실탄 필요

**Research date:** 2026-09-25
**Valid until:** 회차 2026-09-20 데이터 사실은 다음 배너 스캔/조인 스캔 전까지. 코드 사실은 해당 파일 수정 전까지.
