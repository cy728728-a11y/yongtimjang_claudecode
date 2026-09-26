# Phase 6: 마켓 수정업로드 (market-update) - Research

**Researched:** 2026-09-26
**Domain:** 불사자 MCP `bulsaja_market_update`(SMARTSTORE) 래핑 CLI + 웹앱 잡/게이트 슬라이스 + `detail_batch.py --backup-out` 주입구
**Confidence:** MEDIUM-HIGH (코드·실호출로 확인한 부분은 HIGH, `market_update` 응답 모양은 실호출 금지라 MEDIUM/ASSUMED)

## 핵심 답 (MUST-VERIFY 7문항)

> 이 세션의 **실제 불사자 호출은 전부 읽기**다. 쓰기 도구(`market_update`·`detail_apply`·`generate`)는 `confirm:false` 로도 **한 번도 부르지 않았다.**
> 호출 기록(스크립트 전송 계층 `eroomlib.bulsaja.BulsajaMCP`, 계정 **부킹** 확인):
> `bulsaja_my_profile` 1 · `tools/list` 2 · `bulsaja_upload_tasks(mode=list)` 기본 1 + status=PENDING/PROCESSING/FAILED/DLQ 4 + `taskIds=[…]` 2 + `taskId=…` 2 · `bulsaja_product_workdata` summary 1 / full 1 (U01K5H6KT40SPD0AEPTCW1HB3P4) · `bulsaja_product_find_by_code` 1 · `bulsaja_market_groups(groupId=1001135)` 1 · `bulsaja_mcp_settings(mode=get)` 1 · `bulsaja_work_progress` 1. 크레딧 0.

### Q1. `market_update(confirm:false)` 는 정말 쓰기 0 인가? — **거의 확실하지만 이 도구로는 미실측. 계획에 실측 스모크를 넣어라** (MEDIUM)

근거:
1. **불사자 쓰기 도구 전부가 같은 2단 프로토콜**이고, 1차 호출은 저장하지 않는다는 실측이 여러 건 있다 [VERIFIED: 코드·주석 grep]
   - `run_options.py:148` — "1번만 부르면 `success:false` + `confirmationToken` 만 오고 **아무것도 저장되지 않는다**(2026-07-28 파일럿 5건 무변경, 재조회로 확인)"
   - `category_gate.py:826-840` — `market_delete` 는 **`confirm=True` 인데 토큰 없이** 1차 호출해도 실행되지 않고 토큰만 돌려준다(2026-08-09 293건 실측). `bulsaja-category-fix/SKILL.md:561-568`: "확인키는 **호출마다 새로 발급**… 앞 호출의 토큰을 재사용하면 만료로 거부"
   - `detail_batch._입력접수`·`bulsaja-detail-remix/bulsaja_client.apply_detail`·`run_thumbs`·`run_names`·`bulsaja_ship_mcp` 동일 모양
2. `market_update` 스키마: `confirm` default **false**, `confirmationToken` 20~128자 [VERIFIED: tools/list 2026-09-26]. 단 **`market_delete` 설명에 있는 "확인 키 없이는 실행되지 않습니다" 문장이 `market_update` 설명에는 없다** — 서버 강제라는 문서 근거는 없다.
3. 🔴 **새 발견 — 확인 방식은 계정 설정이다.** `bulsaja_mcp_settings(get)` → `confirmationMode: "balanced"`("기본 모드: 일반/위험 변경 확인", 선택지 `strict/balanced/fast`, **fast = "고위험 작업만 확인"**) [VERIFIED: 실호출]. 즉 **confirm:false 가 쓰기 0 인 것은 모드에 달린 성질**이다. `run_options.py:169-170` 의 "토큰 없이 success 면 확인 불필요 응답으로 보고 그대로 반환" 경로가 바로 그 경우다.
4. confirm:false 응답에 무엇이 실리는지(미리보기 항목·토큰 TTL·접수 여부)는 **이 저장소에 기록이 0건**이다. `market_update`/`market_upload` 를 부른 코드·로그·run-dir 이 없다(grep: 전 저장소·data_root). [VERIFIED: grep]

**계획 지시:**
- `market_update.py` 첫 동작 = `my_profile`(ENG-08) + **`mcp_settings(get)` 가 `strict|balanced` 아니면 exit 2 거부**.
- 미리보기 응답에 `confirmationToken` 이 없는데 `success:true` 또는 `taskId` 가 있으면 = **"쓰기가 났을 수 있다" P0 알람** → 즉시 전량 중단, 원문 보존, exit 2. (`option_update` 식 "확인 불필요 성공"으로 **읽지 마라**.)
- 미리보기 잡의 토큰은 **저장·재사용하지 않는다.** 실행 잡이 같은 대상으로 confirm:false 를 다시 불러 새 토큰을 받고 곧바로 confirm:true 한다(토큰 TTL 모름 + 호출마다 새 발급 실측).
- **라이브 스모크(계획 태스크, 연구에서 안 함):** 대상 1건 `market_update(confirm:false)` 전후로 `upload_tasks(list)` 기본 + `status=PENDING` + `status=PROCESSING` + `work_progress` 를 떠서 **최대 taskId 불변 · 대상 productId 신규 행 0 · 마켓작업 대기/진행중 0→0** 을 쓰기 0 증거로 남긴다. 응답 원문(토큰 마스킹)을 `evidence/` 에 박제 → 미리보기 표 컬럼은 그걸 보고 정한다.

### Q2. `upload_tasks` 결과를 상품에 어떻게 붙이나 — **taskId 매칭. 단 목록은 "최근 30건 창"이고 taskId 필터가 안 먹는다** (HIGH)

실측 응답 스키마 [VERIFIED: 실호출 2026-09-26]:
```
{success, 마켓작업:[{상태:"성공"|"실패"|…, 마켓:"스마트스토어", 작업:"업로드", productId, taskId:"49416818", 실패사유?}],
 확장작업:{대기,진행중,내역[]}, 삭제후처리:{진행중,대기,재시도대기,휴지통이동완료,확인필요,내역[{실행방식,상태,마켓,productId,taskId,재시도횟수,다음시도,오류}]}, 표시규칙}
```
- **타임스탬프 필드 없음.** 페이지 인자 없음. 항상 **최근 30건**(taskId 내림차순, 숫자 문자열 단조증가).
- `status=` 필터는 **먹는다**(FAILED → 실패만 30건, PENDING/PROCESSING/DLQ → 0건).
- `taskIds=[…]`·`taskId=…` 는 **list 모드에서 무시된다** — 창 밖의 옛 taskId(40733296)를 줘도 똑같은 최근 30건만 온다. `category_gate.py:902` 의 "무관한 최근 작업도 같이 돌려준다"와 같은 현상이고, 2026-08-09 "198건 중 168건 조회에 안 잡힘"의 진짜 원인이 이 **30건 창**으로 보인다.
- 상태 어휘: 필터는 영문 enum, 응답은 한국어(`성공`/`실패` 확인, 대기·진행 한국어 표기는 미관측 [ASSUMED "대기"/"진행중"]). 수정 작업의 `작업` 값은 미관측 [ASSUMED "수정"] — **작업 문자열로 거르지 마라**(삭제만 제외).

**매칭 전략(권장):**
1. 접수 직전 `list` 로 **워터마크 = 최대 taskId** 를 잰다.
2. **상품 1건당 호출 1회**(`productIds=[pid]`)로 접수 → 응답에서 taskId 추출(`market_delete` 는 `결과[{productId,결과,taskId}]` 모양 — 같다고 가정 [ASSUMED]). 받은 taskId 를 **검증 전에** 체크포인트에 먼저 쓴다(Phase 5 Pitfall 2 관용).
3. 폴링: `list` 기본 + `status=SUCCESS` + `status=FAILED` + `status=DLQ` 창을 모아 taskId 로 찾는다. 응답에 taskId 가 없었으면 **`productId` 일치 + 마켓 스마트스토어 + taskId > 워터마크 + 작업≠삭제** 로 대체 매칭.
4. `성공` 만 성공, `실패`/DLQ 만 실패(`실패사유` 그대로). 끝까지 창에서 못 찾으면 **대기 미완(exit 3) — 실패로 세지 않는다**(`category_gate.verify_tasks` 의 `미확정` 규율 그대로).
5. 1회 상한 20(D-12) < 창 30 이라 평소엔 충분. 다른 스킬이 동시에 수십 건 올리면 창에서 밀린다 → 폴링 간격을 짧게(15~30초) 시작하고, 미확인은 `이어서 확인`.

### Q3. `_판정` 의 workdata 와 `--backup-out` — **추가 호출 0 으로 가능. summary 모드에 renderContent 전문이 있다** (HIGH)

- `detail_batch.py:376 _판정` → `:392 get_workdata(mcp, pid)`(`:135`, **mode=summary**) → `:396 dc = data["uploadDetailContents"]`. 이 `_판정` 은 견적(`_견적:423`)과 **접수 직전 재판정**(`_접수와폴링.시도:568-572`) 두 곳에서 불린다. [VERIFIED: 코드]
- 실측: 같은 상품의 summary/full `uploadDetailContents` 가 **완전히 같다**(`renderContent` 5,512자 전문, `imageTranslated: "0"`) — summary 가 잘린 값이 아니다 [VERIFIED: 실호출 비교 `==`]. AI 미생성 상품엔 `aiImageGenerated` 키가 **없다**(05-04 실측과 일치).
- 주입 지점: `시도()` 안, `r["판정"] == "접수"` 확정 후 · `_입력접수` **직전**. `_판정` 결과 dict 에 `"dc": dc` 를 한 키 더 실어 돌려주면 된다(견적 경로는 무시). 백업 쓰기 실패 → `status[pid] = {"status":"접수실패","사유":"backup_failed: …"}` 로 **generate 안 함**(L-03 을 AI 접수에 적용).
- 파일: `<backup_out>/<productId>.json` = `{productId, 판매자상품코드, 조회시각, 계정, renderContent, imageTranslated}` (D-03). **이미 있으면 덮지 않는다**(O_EXCL/`exists()` 확인) — 재시도·중복대기열 재접수 때 "이미 AI 가 부분 반영된 뒤" 값으로 원본을 덮는 사고 방지. 계정은 `_입력모드` 에서 `_계정확인` 이 받은 닉을 args 로 흘린다(submit 경로에서 `--expect-nick` 을 주므로 항상 채워진다).
- 플래그 없는 경로·`--estimate-only`·`--poll-only` 는 불변. 골든(`fixtures/detail_golden_noflag.json`)은 **무플래그 products.json 경로**만 박제하므로 inputs 모드 변경과 무관 — `test_플래그없음_골든_불변` 이 그대로 지킨다.
- 웹앱: `webapp/argv.py:310 DetailArgv` 에 `backup_out: Path | None = None` 추가, `build()` 에서 `mode == "submit"` 일 때만 `--backup-out` 부착(없으면 ValueError — "백업 없는 접수는 없다"). `webapp/jobs.py:799-829` detail 분기에서 `backup_out=detail_dir / "before_detail"` (detail_dir = `_상세폴더` 가 푼 `<회차>/web/detail_<견적잡id>/`).
- 테스트: `webapp/tests/test_detail_cli.py` 의 `cli` 픽스처 + `가짜MCP` + `가짜시계` + `주입()`/`실행()` 을 그대로 쓴다. 추가할 케이스 = 백업 파일 생성·내용 · 기존 파일 불덮음 · 백업 쓰기 실패 시 generate 0회 · 플래그 없으면 파일 0 · 견적 모드에선 파일 0.

### Q4. "스마트스토어에 올라간 적 있음"·marketGroupId·스토어 링크 (HIGH, 링크 URL 모양만 ASSUMED)

- **미업로드 판별:** `workdata(summary).data.uploadedSuccessUrl` = `{coupang, st11, gmarket, smartstore:"13192250286", auction}` — `smartstore` 가 비면 `미업로드` 스킵 [VERIFIED]. 보조: `find_by_code` 의 `업로드된마켓:["스마트스토어"]`·`상태:"업로드 완료"` [VERIFIED].
- **채널상품번호:** `uploadedSuccessUrl.smartstore` == 조인 산출물의 `mallProductId`/`인덱스_smartstore`(같은 상품 13192250286 일치) [VERIFIED]. 게이트 패널 링크는 이 번호로. URL 모양 `https://smartstore.naver.com/main/products/<번호>` 는 [ASSUMED] — 에이전트는 네이버 접속 금지라 검증 불가, 번호를 복사 가능한 텍스트로 항상 같이 보인다.
- **marketGroupId:** `workdata(full).data.uploadSelectedMarketGroupId` = 1001135 (summary 에는 없음) [VERIFIED]. `market_groups(1001135)` → `2번_용쌤22-1`, 연결마켓 `["스마트스토어"]` [VERIFIED]. `market_update` 에서 **옵션 인자**라, 넘길지 말지는 스모크 미리보기 응답(대상 그룹 표기 여부)을 보고 정한다. 권장 기본 = 넘기지 않는다 + full 값은 증거로 기록 [ASSUMED].
- 🔴 **상하단 모순에 직결되는 실측:** `workdata(full).data.uploadDetail_page` 에 **상품 단위 사본**이 있다: `top_image/bottom_image = cdn…/marketGroups/1001135/fixedImages/…/top.png?t=1758132676314`(=2025-09-18), `is_include_fixed_image:true` [VERIFIED]. 그룹 설정을 바꿔도 상품에 박힌 이 URL 이 남아 있다면 인계 확정사실 1("최초 업로드 때 이미지가 계속 올라간다")의 **기전 설명**이 된다 [ASSUMED 추론]. → 미리보기 표·ⓑ 백업·게이트 패널에 **이 상품의 상하단 URL + 타임스탬프 날짜**를 같이 싣는다. 게이트 ② 판정 재료가 생긴다(비용: 상품당 full 조회 1회).

### Q5. MCP 클라이언트 규약 (HIGH)

- `detail_batch.py:47-52` 관용구 그대로: `SKILL_SCRIPTS = …/bulsaja-category-fix/scripts` 를 sys.path 에 넣고 `from bulsaja_mcp import BulsajaMCP`(= `eroomlib.snapshot.ProductMCP` → `eroomlib.bulsaja.BulsajaMCP`). 전송은 **`requests`**(UA `python-requests`)라 urllib UA 403 문제 없음 [VERIFIED: `eroomlib/bulsaja.py:21`]. 429/5xx 재시도·세션·토큰(`~/.claude.json` 매번 새로 읽음) 내장.
- 이 import 형태면 `test_detail_cli.py` 식 `sys.modules["bulsaja_mcp"]` 스텁으로 `.venv-web` 에서 오프라인 로드된다(05-01 A1 실측).
- 응답 해석: 오류를 빈 결과로 접지 않는다 — `ss_index_calls.항목꺼내기`/`목록꺼내기` 규약(지연 import). `마켓작업` 키가 없거나 리스트가 아니면 "0건"이 아니라 **조회 실패**로 처리.
- `표시규칙` 키는 응답마다 붙는다 — `detail_batch._표시규칙제거` 와 같이 떼고 저장.
- 레이트: `settings.mcp_min_interval 0.26s`(240/60s). 20건 × (workdata 2 + update 2 + 폴링) 여유 충분.

### Q6. 웹앱 통합 지점 (HIGH)

| 자리 | 파일:줄 | Phase 6 에서 할 일 |
|---|---|---|
| kind 등록 | `jobs.py:68-78` `JobKind`+`KINDS` (**둘 다 같이**) | `market_preview`, `market_commit`, (`market_poll` — 재량, 아래) |
| 쓰기 가드 | `jobs.py:87` `WRITE_KINDS` | `market_commit`(+`market_poll`) — 체크포인트 파일을 읽고-고치고-쓰므로 poll 도 |
| 계정 사전점검 | `jobs.py:105` `BULSAJA_KINDS` | 셋 다 |
| 같은 kind 중복 | `jobs.py:134` `SINGLETON_KINDS` | `market_preview`(쓰기 가드 밖이라 레이트리밋 보호) |
| exit 3=done | `jobs.py:396` `POLL_INCOMPLETE_OK_KINDS` | `market_commit`(+`market_poll`) |
| 수면방지 | `jobs.py:649` `_수면방지_프리픽스` | `market_commit`(+`market_poll`) |
| 폴더 규칙 | `jobs.py:575-620` `_상세부모`/`_상세폴더` | 같은 모양 `_마켓폴더`: `<회차>/web/market_<미리보기잡id>/` (부모 체인 preview←detail_submit/poll, commit←preview, poll←commit, 회차 일치 검사) |
| argv 조립 | `argv.py:310` 옆 | `MarketArgv(mode: preview/commit/poll, run_dir, targets, expect_nick, max_items, backup_dir, detail_backup_dir, summary_out, poll_interval, max_poll_min, prefix)` — 기본값 없음, `_build_argv` 가 `settings.cfg` 로 채움 |
| 부모 자식 조회 | `jobs.py:1201` `children_of` | 한 미리보기로 게이트 1건 commit 후 나머지 commit 1회 허용(아래 Pitfall 5) |
| 라우트 | `routes/jobs.py:1205-1296` detail submit/poll | `POST /jobs/market/preview`(부모=detail 잡 id), `/jobs/market/commit`(미리보기 잡 id 하나), `/jobs/market/poll`, `POST /market/gate`(판정 기록) |
| 결과 분기 | `routes/jobs.py:1358-1366` | `market_preview`→`_market_preview_table.html`, commit/poll→`_market_result_table.html` |
| 결과 정본 | `_상세결과ctx`(`:404`) 모양 | `market_status.json` 체크포인트를 정본으로 읽는 `_마켓결과ctx` |
| DDL | `jobs.py:159-215` `DDL` (+`init_db:349`) | `CREATE TABLE IF NOT EXISTS market_gate (id INTEGER PK, 판정 TEXT CHECK(판정 IN ('정상','이상')), 기록시각, 판매자상품코드, productId, commit_job_id, 스토어교체여부 TEXT, 메모 TEXT)` — 접근은 `banner_store.py` 모양의 별도 모듈(`market_gate_store.py`, **DDL 0줄**·읽기 `mode=ro`) |
| 설정 | `settings.py:DEFAULTS` Phase 5 블록 아래 | `market_update_max_items: 20`, `market_poll_interval`, `market_max_poll_min` — 상수로 올리지 말고 `settings.cfg` 로만 |
| 트리 가드 | `tests/test_argv.py:162-247` (문자열 명령 금지·sys.executable 금지·`webapp/**` 에 requests/Pillow/eroomlib 0) | 새 코드도 자동 적용. 웹앱은 백업 JSON 을 **읽지도 않는다**(경로·존재만 `Path.is_file()`) |
| 보드 | `_detail_result_table.html` | `완료` 행이 1개 이상이면 `스마트스토어 반영 미리보기 — 쓰기 0` 버튼 (부모 = 그 detail 잡 id) |

게이트 강제는 **두 겹**: 서버가 `market_gate` 에 `정상` 행이 없으면 commit 잡의 `max_items=1` 로 조립하고(요청값 무시), CLI 도 `--max-items` 초과 시 exit 5. 판정 `이상` 행이 최신이면 commit 라우트 400.

### Q7. Phase 5 와의 순서 (HIGH — 단 운영 조치 1건 필수)

- 05-05 는 진행 중: 견적 잡 `5f5feac7`(detail_estimate, done, 2026-09-26 13:14) 존재, `evidence/05-05-estimate.md` 에 결정 4줄 "추천대로" 기록 · 재확인 대기 [VERIFIED: webapp.db ro · 파일].
- 05-06 제약: "실탄이 도는 동안 웹앱 코드를 고치지 않는다(Pitfall 4)" — **도는 동안**만 금지. 05-06 truth 는 `--max-credits == 승인 예상크레딧` 만 요구하므로 `--backup-out` 추가와 충돌 없음 [VERIFIED: 05-06-PLAN:15-22,43].
- 접수 argv 는 **접수 순간** `_build_argv` 로 새로 조립된다 → 이미 끝난 견적(5f5feac7)으로 접수해도 새 플래그가 붙는다.
- ⚠️ **사용자 서버(PID 45635)는 `--reload` 없이 돈다**(`uvicorn … --workers 1`) [VERIFIED: ps]. 06-01 을 머지해도 **서버를 재시작하기 전엔 옛 DetailArgv 로 접수된다.** → 06-01 의 마지막 태스크 = "도는 잡 0건 확인 → 서버 재시작 → `/jobs` 에서 다음 접수 argv 에 `--backup-out` 이 있는지 확인(테스트 접수 없이: 조립 함수 직접 호출 또는 05-06 첫 접수 직후 argv 확인)". 재시작은 사람 확인(사용자 서버라서).
- 06-01 은 **크레딧 0 · 불사자 호출 0**(오프라인 테스트만)이라 05-05 체크포인트를 기다리는 동안 머지 가능. 06-02 이후 웹앱 편집은 05-06 **실탄이 도는 동안엔 금지**(Wave 설계로 05-06 완료 후 또는 실탄 사이에).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### 🔒 잠긴 제약 (auto 아님 — 프로젝트·메모리·Phase 5 에서 승계)

- **L-01: 모든 실제 `market_update(confirm:true)` 는 플랜의 blocking human checkpoint 다.** 첫 1건(게이트) · 나머지 일괄 · 복원 실행 전부.
  `autonomous: false` 이고 `--auto` 체인·`workflow.auto_advance` 도 이 체크포인트를 자동 승인하지 않는다. 체크포인트 앞에 **대상 건수 · 판매자상품코드 · 계정 · 백업 경로**를 보여 준다.
- **L-02: dry-run 선행.** 실제 쓰기 전에 반드시 같은 대상으로 미리보기 잡(`confirm:false` — 쓰기 0)이 `done` 이어야 하고, 실행 라우트는 **미리보기 잡 id 하나만** 받는다(대상을 새로 받지 않는다 — Phase 1 01-08 D-11 · Phase 5 05-04 선례).
- **L-03: 백업 없으면 쓰기 없음.** 대상 상품의 원본 상세 HTML 백업 파일이 없거나 읽히지 않으면 그 건은 쓰지 않는다(`backup_failed` 로 스킵/중단, 폴백 없음) — MARKET-03 · PITFALLS Pitfall 10.
- **L-04: 기존 CLI 재작성 금지 · 웹앱은 MCP 를 직접 부르지 않는다.** 마켓 반영은 새 CLI 스크립트를 subprocess 로, 기존 `detail_batch.py` 는 **주입구 플래그 추가만**(Phase 5 L-04 · Phase 3 D-19 · ENG-01).
- **L-05: 진실의 원천은 불사자 서버.** "반영했음" 로컬 대장을 새로 만들지 않는다. 잡 산출물(summary)은 그 회차 기록일 뿐이고 반영 상태는 불사자 `upload_tasks` 가 정본(PROJECT.md).
- **L-06: 계정 가드(ENG-08) 그대로** — 기대 계정(부킹/용쌤) 아니면 미리보기·반영 모두 exit 4 로 거부.
- **L-07: 마켓은 SMARTSTORE 고정.** 화면에 마켓 선택지를 두지 않는다. 같은 상품이 쿠팡에도 올라가 있어도 이 버튼은 스마트스토어만 친다.

#### 대상 — 무엇을 반영하나 (MARKET-01)

- **D-01 [auto]: 대상은 Phase 5 상세 잡 결과에서 `완료` 인 항목뿐이다.** 보드의 "최근 상세 작업" 결과 표(`_detail_result_table.html`)에 `스마트스토어 반영` 미리보기 버튼을 단다.
  · [auto] Q: "대상 출처 — ⓐ 상세 잡 완료분 ⓑ 보드에서 아무 상품이나" → Selected: **ⓐ 상세 잡 완료분** (recommended — Phase 1 부모 잡 체인 패턴 그대로, 엉뚱한 상품 반영 차단)
  · 미리보기 잡 = `parent_job_id` 가 detail_submit/detail_poll 잡. 서버는 그 잡의 `detail_status.json`(Phase 5 결과 정본) 에서 `완료` 만 뽑아 targets 파일로 쓴다
  · 사본 1개 원칙(Phase 5 D-06) 그대로 — 표기는 **판매자상품코드**
- **D-02 [auto]: CLI 는 반영 직전 workdata 를 실시간 재조회해 "AI 상세가 실제로 붙어 있는지"(Phase 5 D-12 와 같은 `기작업` 규칙)를 확인한다.** 아니면 그 건은 `AI상세없음` 으로 스킵. 스마트스토어 업로드 흔적이 없는 상품(미업로드)은 `미업로드` 로 스킵.

#### 원본 백업 (MARKET-03 · SC-3)

- **D-03 `[auto — 용팀장 확인 필요]`: "원본 상세 HTML" = AI 생성 직전의 불사자 상세(`uploadDetailContents.renderContent` + `imageTranslated`). 이 스냅샷은 Phase 5 접수 순간에 떠야 하므로, `detail_batch.py` 에 `--backup-out <dir>` 주입구를 추가하고 05-06 첫 실탄 전에 들어가게 한다.**
  · [auto] Q: "백업 시점 — ⓐ AI 접수 직전(원본) ⓑ 마켓 반영 직전(이미 AI 버전)" → Selected: **ⓐ + ⓑ 둘 다, 복원 기준은 ⓐ** (recommended)
  · 근거(실측): AI 생성 결과는 **완료 시 불사자 상세를 자동으로 덮는다**(bulsaja-detail-page SKILL · `detail_apply` 도구 설명). 지금 코드에 renderContent 원문 백업은 **어디에도 없다**(detail_batch·banner_scan 모두 URL 만 뽑고 버림). 마켓 반영 시점에 뜨면 원본은 이미 사라진 뒤다. 스마트스토어 쪽 원문은 맥북에서 커머스API 로 못 읽는다(IP 허용목록 — 00-inbox 인계 확정사실 6)
  · 비용 0: `_판정` 이 이미 접수 전 `get_workdata` 를 부른다 — 같은 응답에서 원문을 파일로 떨군다. 추가 호출 없음. 백업 쓰기 실패 = 그 건 generate 하지 않음(L-03 을 AI 접수에도 적용)
  · 파일: `<회차>/web/detail_<견적잡id>/before_detail/<productId>.json` = `{productId, 판매자상품코드, 조회시각, 계정, renderContent, imageTranslated}`
  · ⓑ 마켓 반영 직전 스냅샷도 같은 모양으로 `market_<잡id>/before_market/` 에 남긴다(무엇을 밀었는지의 증거, 비용 0)
  · 플래그 없는 기존 동작은 불변(골든 테스트 유지). 웹앱 `DetailArgv` submit 이 이 플래그를 항상 붙인다
  · **확인이 필요한 이유:** Phase 5 실행 순서를 바꾼다 — 06-01(백업 플래그, 크레딧 0)이 05-06 실탄보다 먼저 머지돼야 첫 5건의 원본이 남는다. 이미 백업 없이 생성된 상품이 생기면 그 건은 ⓑ 만 있고 **원본 복원 불가**로 표시한다
- **D-04 [auto]: 화면은 결과 표와 미리보기 표에 상품별 백업 파일 경로(ⓐ·ⓑ)와 존재 여부를 보인다.** 경로는 텍스트(복사 가능)로. 파일 뷰어는 만들지 않는다 — SC-3 은 "위치를 화면에서 확인"까지다.
- **D-05 [auto]: 복원은 CLI 서브커맨드로만 만든다(웹 버튼 없음).** `restore --backup <before_detail/…json>` = `detail_apply(html=ⓐ원문, confirm:false→true)` 후 `market_update`. 미리보기(confirm:false)까지 오프라인+실제 MCP 크레딧 0 로 검증하고, **실제 복원 실행은 게이트 실패 등 필요할 때만 L-01 체크포인트로**.
  · [auto] Q: "복원을 이 페이즈에 넣나" → Selected: **CLI 만 넣는다** (recommended — Pitfall 10 "백업만 있고 복원 경로가 없으면 위안", 웹 버튼은 Deferred)

#### 미리보기 → 반영 (쓰기 경로)

- **D-06 [auto]: 새 CLI `market_update.py`(bulsaja-detail-page/scripts, 기존 MCP 클라이언트·`ss_index_calls` 호출 규약 재사용)를 만든다.** 인자: `--targets` · `--expect-nick` · `--preview`(confirm:false 만, 쓰기 0) · `--commit` · `--max-items N` · `--backup-dir` · `--summary-out` · `--run-dir`. 마지막 줄 센티널 `###MARKET### 성공 a / 실패 f / 스킵 s / 대기 p / 전체 t`, `flush=True`.
  · 종료코드는 Phase 5 계약을 따른다: 0 전부 종결 · 2 입력 오류 · 3 서버 작업 대기 미완(실패 아님) · 4 계정 불일치 · 5 `--max-items` 초과 시도
  · `--commit` 은 `--max-items` 없으면 exit 2(Phase 5 `--max-credits` 와 같은 규율 — 빈 값이 "전량"이 되지 않는다)
- **D-07 [auto]: 웹앱 잡 kind 2종 — `market_preview`(BULSAJA_KINDS · 쓰기 아님) · `market_commit`(WRITE_KINDS · `caffeinate -i`).** 버튼 흐름은 Phase 1/5 와 같다: 결과 표 → `반영 미리보기 — 쓰기 0` → 미리보기 표 → `반영 실행` (미리보기 잡 id 만 전송).
- **D-08 [auto]: 반영 결과 확인은 `bulsaja_upload_tasks(list)` 폴링으로 한다** — 접수 응답만 믿지 않는다(불사자 안전규칙 ⑤). 시간 상한에 닿으면 `대기 미완` exit 3 · 실패 아님 · `이어서 확인` 만(재반영 버튼 없음 — Phase 5 D-17 과 같은 규율). 서버 `FAILED/DLQ` 만 `실패`.
  · 같은 상품·마켓 작업이 진행 중이면 서버가 자동 차단한다(도구 설명) → 그 응답은 `실패` 가 아니라 `이미진행중` 스킵

#### 첫 1건 육안 게이트 (MARKET-02 · SC-2 · STATE Blocker)

- **D-09 `[auto — 용팀장 확인 필요]`: 게이트는 1회성이다 — 상하단 안내이미지 모순을 깨는 용도. 판명 전까지 `market_commit` 은 코드로 `--max-items 1` 로만 나가고, 판정이 기록된 뒤에는 이 강제 1건 정지가 풀린다.**
  · [auto] Q: "매 실행마다 첫 1건 정지 ⓐ vs 모순 판명 1회 ⓑ" → Selected: **ⓑ 1회** (recommended — 처리량 우선 · 사람 큐 최소화. 모순은 한 번 보면 끝나는 사실 문제)
  · 게이트 상태는 웹앱 SQLite 한 줄(`market_gate`: 판정 · 시각 · 확인한 상품코드 · 메모). 이건 "작업 완료 대장"이 아니라 사람 판정 기록이라 L-05 와 충돌하지 않는다
  · 판정 전: 미리보기 표의 실행 버튼은 `첫 1건만 반영 (육안 확인 게이트)` 한 가지뿐. 대상이 N건이어도 1건만 나간다(나머지는 표에 `게이트 대기`)
  · **확인이 필요한 이유:** SC-2 문구("첫 1건이 반영된 뒤 … 나머지가 나가지 않는다")를 매 실행 규칙으로 읽을 수도 있다. 1회로 풀면 이후 대량 반영이 사람 개입 없이 나간다(단 L-01 실행 체크포인트는 그대로)
- **D-10 [auto]: 게이트 화면 = 1건 반영 성공 후 결과 표 위에 고정 패널.** 내용: 판매자상품코드 · 스마트스토어 상품 링크(조인 산출물의 채널상품번호로 조립, 없으면 코드만) · 확인 체크 3개 ① 본문이 AI 상세로 바뀌었다 ② 상단·하단 안내이미지가 **현재 불사자 설정** 것이다 ③ 가격·상품명·옵션 등 다른 곳이 의도치 않게 바뀌지 않았다 → 버튼 `정상 — 나머지 진행 허용` / `이상 있음 — 멈춤`.
  · ③ 을 넣은 이유: `market_update` 는 "가격/상품명/상세 등 변경사항"을 통째로 다시 민다(도구 설명). 다른 스킬(option-cleanup·product-name)이 불사자에만 저장해 둔 변경이 이 버튼으로 같이 나갈 수 있다 — 첫 1건에서 눈으로 본다
  · 에이전트는 네이버·스마트스토어에 접속하지 않는다(CLAUDE.md 네이버 규칙) — 육안 확인은 용팀장 브라우저 몫
- **D-11 [auto]: `이상 있음` 이면 게이트는 닫힌 채(나머지 0건) 그 상품의 복원 절차(D-05)와 증상 메모를 보여 주고 끝.** 옛 안내이미지로 판명되면 PROJECT.md `[!contradiction]` 을 전자로 확정 기록하고, **"상하단 교체 프로젝트는 관제탑 반영 뒤에 돌리거나 재실행"** 순서 제약을 STATE Blockers 에 올린다. 진행 여부는 그때 용팀장이 정한다(자동 진행 없음). `정상` 이면 contradiction 을 후자로 확정 기록.

#### 규모 · 기타

- **D-12 [auto]: 게이트 통과 후 1회 반영 상한은 설정값 `market_update_max_items`(기본 20).** 상한 초과 선택은 미리보기에서 앞 N건 + 나머지 표시. 첫 실사용 대상은 어차피 05-06 의 🔴 5건 이하.
- **D-13 [auto]: 결과 표 = 항목 단위**(판매자상품코드 · 성공/실패/스킵/대기 · 사유 · 백업 경로 · 서버 작업 시각). Phase 5 결과 표 레이아웃 재사용.

### Claude's Discretion

- `market_update.py` 내부 구조 · 폴링 간격/상한 기본값 · `upload_tasks` 응답에서 상품별 매칭 방법(연구에서 실측 스키마 확인)
- 미리보기(confirm:false) 응답에 무엇이 실리는지에 따라 미리보기 표 컬럼 구성
- `market_gate` 테이블 스키마 · 게이트 패널 문구
- 스마트스토어 상품 링크 조립 가능 여부(조인 산출물 필드 실측)
- run-dir 파일 배치(권장: `<회차>/web/market_<미리보기잡id>/`)

### Deferred Ideas (OUT OF SCOPE)

- 웹 화면 `복원` 버튼 (D-05 — MVP 는 CLI)
- 스토어 쪽 HTML 자동 대조(커머스API — 맥북 IP 불가, 데스크탑 전용)
- 매 실행 첫 1건 정지 (D-09 대안 ⓐ — 용팀장이 원하면 설정 플래그로)
- 쿠팡·다른 마켓 반영 (Phase 7 이후)
- 반영 실패분 재시도 버튼 (`upload_tasks retry`) — MVP 는 결과 표만
- 백업 없이 이미 생성된 상품의 원본 복구 수단 탐색(불사자 이력 API 등)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MARKET-01 | 생성 완료분을 `market_update` 로 스마트스토어에 반영 | Q2 매칭 전략 · Q4 미업로드/AI 확인 필드 · Q5 클라이언트 · Q6 kind/라우트 · 상품당 1호출 2단 접수 |
| MARKET-02 | 1건 먼저 반영 → 스토어 육안 확인 뒤에야 나머지 | Q6 게이트 두 겹 강제(서버 max_items=1 + CLI exit 5) · `market_gate` 테이블 · Q4 상품 단위 상하단 URL 사본(게이트 ② 재료) |
| MARKET-03 | 반영 전 원본 상세 HTML 보관 | Q3 `--backup-out`(summary renderContent 전문 실측) · 불덮음 규칙 · Q7 05-06 전 머지 + 서버 재시작 · ⓑ before_market · restore(`detail_apply` 2단) |
</phase_requirements>

## Summary

Phase 6 는 새 라이브러리가 0개인 **래퍼 페이즈**다. 필요한 부품(2단 확인 호출·upload_tasks 폴링·체크포인트·부모 잡 체인·SSE 결과 표·SQLite 사람 기록)이 전부 저장소에 이미 검증된 모양으로 있다: `category_gate.delete_batch/verify_tasks`(마켓 쓰기 + upload_tasks 확정), `detail_batch._접수와폴링`(taskId 선저장·exit 3·센티널), `routes/jobs.py` detail 슬라이스(견적→접수→이어서 확인), `banner_store.py`(DDL 없는 사람 기록 모듈).

실측으로 계획을 바꿔야 할 사실이 셋 나왔다. ① **`upload_tasks list` 는 최근 30건 창만 주고 taskId 필터를 무시한다** — 상품별 결과는 접수 응답 taskId(+워터마크 대체)로 창 안에서 찾고, 못 찾으면 실패가 아니라 대기 미완이다. ② **확인 방식이 계정 설정(`balanced`)이다** — confirm:false 쓰기 0 은 모드 조건부이므로 CLI 가 매번 모드를 확인하고, 토큰 없는 성공 응답을 P0 알람으로 다룬다. ③ **상품 workdata(full)에 상하단 안내이미지 URL 사본(2025-09-18 타임스탬프)이 박혀 있다** — 모순 ①(옛 이미지가 올라간다)의 기전 후보이며, 게이트 ② 판단 재료로 화면에 싣는다.

**Primary recommendation:** 06-01(`--backup-out` + DetailArgv, 크레딧 0)을 즉시 머지하고 **사용자 서버를 재시작한 뒤** 05-06 을 돌린다. 이후 `market_update.py`(preview/commit/poll/restore, 상품당 1호출, 체크포인트 `market_status.json`) → 웹앱 슬라이스 → 라이브 쓰기 0 스모크(upload_tasks diff) → 게이트 1건(사람) → 나머지(사람) 순.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| 원본 상세 백업 ⓐ | CLI (`detail_batch.py --backup-out`) | — | workdata 응답을 가진 유일한 곳. 웹앱은 MCP·백업 내용을 모른다(L-04) |
| 반영 직전 재조회·ⓑ 백업·접수·폴링 | CLI (`market_update.py`) | 불사자 서버(정본) | subprocess 경계, 서버 upload_tasks 가 진실(L-05) |
| 대상 추출(완료분) | 웹앱 API (`routes/jobs.py`) | — | detail_status.json 을 읽기만 해 targets 파일을 떨군다 |
| 게이트 강제(1건) | 웹앱 API + CLI 이중 | SQLite `market_gate` | 서버가 max_items 를 정하고 CLI 가 exit 5 로 재확인 |
| 게이트 육안 판정 | 사람(용팀장 브라우저) | 웹앱 기록 | 에이전트 네이버 접속 금지 |
| 복원 | CLI `restore` 서브커맨드 | — | 웹 버튼 Deferred |
| 결과 표·백업 경로 표시 | 웹앱 템플릿(Jinja2+htmx) | — | 파일 경로·존재만(`is_file`) |

## Standard Stack

새 패키지 없음. [VERIFIED: 코드베이스]

| 부품 | 위치 | 용도 |
|---|---|---|
| `BulsajaMCP`(eroomlib.bulsaja, requests) | `.venv` (CLI) | 불사자 JSON-RPC 전송·재시도 |
| stdlib `json/argparse/pathlib/time` | CLI | market_update.py |
| FastAPI/Jinja2/htmx/sqlite3 (기존) | `.venv-web` | kind·라우트·템플릿·`market_gate` |
| pytest (기존) | `.venv-web/bin/pytest` | 오프라인 가짜MCP 테스트 |

**Installation:** 없음.

## Package Legitimacy Audit

이 페이즈는 외부 패키지를 설치하지 않는다 — 감사 대상 0건. (slopcheck 미실행: 대상 없음)

## Architecture Patterns

### System Architecture Diagram

```
[보드 · 최근 상세 작업 결과표 (detail_status.json 정본)]
      │ "스마트스토어 반영 미리보기 — 쓰기 0" (부모=detail_submit/poll 잡 id)
      ▼
POST /jobs/market/preview ── 서버: 부모 체인 검사 → `완료` 항목만 targets_<id>.json
      │ create_job("market_preview")  [BULSAJA · SINGLETON · 계정 사전점검]
      ▼
market_update.py --preview ──► my_profile(닉) ─► mcp_settings(모드 strict|balanced?)
      │  상품마다: workdata(summary) → 미업로드? AI상세없음? ─► ⓐ 백업 존재? (없으면 backup_failed)
      │           workdata(full) → 상하단 URL·그룹 · ⓑ before_market/<pid>.json 쓰기
      │           market_update(confirm:false) → 토큰 있음? (없는데 success/taskId = P0 중단)
      ▼
preview.json (항목별 판정·백업경로·상하단URL·채널번호) ──► 미리보기 표
      │ market_gate 에 '정상' 없음 → 버튼 "첫 1건만 반영 (육안 확인 게이트)"  /  있음 → "반영 실행 (최대 N)"
      ▼  [L-01 사람 체크포인트]
POST /jobs/market/commit (미리보기 잡 id 하나) ── 서버가 max_items 결정 (게이트 전=1)
      │ create_job("market_commit") [WRITE · caffeinate]
      ▼
market_update.py --commit ─► 워터마크(list 최대 taskId) ─► 상품마다: 재조회+백업확인 → confirm:false(새 토큰) → confirm:true
      │                       → taskId 를 market_status.json 에 먼저 기록
      ▼
폴링: upload_tasks list(기본/SUCCESS/FAILED/DLQ 창) → taskId 매칭 → 성공/실패/대기
      │ 시간 상한 → exit 3(대기 미완, done) → "이어서 확인"(market_poll, 접수 0)
      ▼
결과 표 (market_status.json 정본) ─► [게이트 전이면] 고정 패널: 코드·채널번호·상하단 URL·체크 3 → 정상/이상
      ▼
POST /market/gate → market_gate 1행 → (정상) 다음 commit 은 N건 / (이상) commit 400 + restore 안내
```

### Recommended Project Structure
```
.claude/skills/bulsaja-detail-page/scripts/
├── detail_batch.py          # --backup-out 추가만 (L-04)
└── market_update.py         # 신규: preview / commit / poll / restore
webapp/
├── argv.py                  # MarketArgv 추가, DetailArgv.backup_out
├── jobs.py                  # kind·가드 집합·_마켓폴더·DDL market_gate
├── market_gate_store.py     # 신규: DDL 0줄, 읽기 mode=ro / 쓰기 INSERT
├── routes/jobs.py           # /jobs/market/{preview,commit,poll} · _마켓미리보기ctx · _마켓결과ctx
├── routes/market.py (또는 jobs.py 안) # POST /market/gate
├── templates/_market_preview_table.html · _market_result_table.html · _market_gate_panel.html
└── tests/test_market_cli.py · test_routes_market.py · (test_detail_cli.py 백업 케이스 추가)
<회차>/web/detail_<견적id>/before_detail/<pid>.json         # ⓐ
<회차>/web/market_<미리보기id>/{preview.json, market_status.json, summary_<잡id>.json, before_market/<pid>.json}  # ⓑ
```

### Pattern 1: 상품당 1호출 2단 접수 + taskId 선저장
**What:** `productIds=[pid]` 로 confirm:false → 토큰 → confirm:true. taskId 를 받자마자 체크포인트 저장.
**Why:** 배치는 "원자적 생성 실패로 전체 그룹 미접수"(market_delete 실측 23%)로 한 건 때문에 전부 막힌다; 20건 이하라 호출 수 부담 없음; 결과 귀속이 명확.
```python
# 출처: category_gate.py:823-857 · detail_batch.py:445-464 관용구
def 접수1건(mcp, pid, 그룹=None):
    기본 = {"productIds": [pid], "market": "SMARTSTORE"}
    if 그룹: 기본["marketGroupId"] = int(그룹)          # 스모크 후 결정
    pre = 표시규칙제거(mcp.call_tool("bulsaja_market_update", {**기본, "confirm": False}) or {})
    토큰 = pre.get("confirmationToken")
    if not 토큰:
        if pre.get("success") or 작업번호찾기(pre):
            raise 쓰기의심("토큰 없이 성공/작업번호 — 확인 모드가 바뀌었을 수 있다. 전량 중단")
        return None, 사유(pre)                           # 이미진행중·미업로드 등 → 스킵 분류
    fin = 표시규칙제거(mcp.call_tool("bulsaja_market_update",
                      {**기본, "confirm": True, "confirmationToken": 토큰}) or {})
    return 작업번호찾기(fin, pid), fin
```

### Pattern 2: 창 매칭 폴링 (upload_tasks)
```python
# 출처: category_gate.verify_tasks + 이 세션 실측(30건 창, taskIds 무시)
def 창읽기(mcp):
    행들 = {}
    for 인자 in ({"mode": "list"}, {"mode": "list", "status": "SUCCESS"},
                 {"mode": "list", "status": "FAILED"}, {"mode": "list", "status": "DLQ"}):
        r = 표시규칙제거(mcp.call_tool("bulsaja_upload_tasks", 인자))
        목록 = r.get("마켓작업")
        if not isinstance(목록, list):
            raise 조회실패(인자)                          # 빈 결과로 접지 않는다
        for x in 목록:
            행들[str(x.get("taskId"))] = x
    return 행들
# 종결: 상태 == "성공" → 성공 / "실패" 또는 DLQ 창에서 발견 → 실패(실패사유) / 그 밖·미발견 → 대기
```

### Pattern 3: 게이트 이중 강제
서버: `max_items = 1 if not market_gate_store.통과() else settings.cfg("market_update_max_items", 20)` — 요청 본문에 상한 필드를 두지 않는다. CLI: `--commit` 은 `--max-items` 필수, 체크포인트상 taskId 보유 수 + 이번 건 > max_items 면 접수 전 exit 5.

### Anti-Patterns to Avoid
- **미리보기 잡의 토큰을 실행 잡이 재사용** — TTL 모름, 호출마다 새 발급 실측. 실행 잡이 새로 받는다.
- **`taskIds` 필터를 믿고 조회** — 무시된다. 창 밖이면 "없음"이 아니라 "못 봄".
- **upload_tasks 에 없다 = 실패** — 대기열 미소진일 뿐(2026-08-09 성공 0·대기 30·미조회 168).
- **`작업=="수정"` 문자열로 필터** — 값 미관측.
- **백업 ⓐ 덮어쓰기** — 재시도 때 AI 버전으로 원본이 사라진다.
- **웹앱이 백업 JSON 내용을 읽어 렌더** — 경로·존재만. 원문 HTML 을 화면에 띄우면 XSS 표면도 생긴다.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| 불사자 전송·재시도·세션 | 새 HTTP 클라이언트 | `bulsaja_mcp.BulsajaMCP`(eroomlib) | 429·SSE 파싱·UTF-8 디코딩 함정 이미 해결 |
| 응답 목록 해석 | `r.get("마켓작업") or []` | `ss_index_calls.목록꺼내기` 규약 | 오류를 0건으로 접던 실사고(03-07) |
| 잡 엔진·가드·SSE | 새 실행기 | `jobs.create_job` + kind 집합 | 쓰기 가드·starting 경합·orphaned 이미 해결 |
| 상세 결과 분류 | 새 상태 규칙 | `routes/jobs._상세항목상태` 의 `완료` | Phase 5 와 같은 대상 정의 |
| 복원 2단 호출 | 새 detail_apply 래퍼 | `bulsaja-detail-remix/bulsaja_client.apply_detail` 모양 | 2026-09-01 실측 스키마 |
| 사람 기록 저장 | jobs 테이블에 컬럼 추가 | `banner_store.py` 모양 별도 모듈 + `jobs.DDL` | DDL 한 곳·읽기 ro 규율 |

## Common Pitfalls

### Pitfall 1: 확인 모드가 fast 로 바뀌면 "미리보기"가 쓰기가 된다
**What goes wrong:** confirm:false 첫 호출이 곧바로 접수된다. **Why:** `mcp_settings.confirmationMode` 가 계정 단위 설정, fast = 고위험만 확인. **How to avoid:** CLI 시작 시 모드 확인(strict|balanced 아니면 exit 2), 토큰 없는 성공 = P0 중단. **Warning signs:** 미리보기 뒤 upload_tasks 최대 taskId 증가.

### Pitfall 2: upload_tasks 30건 창
**What goes wrong:** 다른 작업이 몰리면 우리 taskId 가 창에서 밀려 영영 "대기". **How to avoid:** status 별 창 합치기, 짧은 첫 간격, 미확인은 exit 3 + 이어서 확인(재반영 금지). **Warning signs:** `work_progress.마켓작업.대기` 가 큼.

### Pitfall 3: 서버 재시작 없이 05-06 접수
**What goes wrong:** 06-01 머지했는데 PID 45635 가 옛 코드로 `--backup-out` 없이 접수 → 첫 5건 원본 유실(ⓑ만 남아 "원본 복원 불가"). **How to avoid:** 06-01 끝에 재시작 체크포인트 + 접수 잡 argv 에 `--backup-out` 존재 확인을 05-06 사전조건으로. **Warning signs:** `jobs.argv` 에 `--backup-out` 없음 / `before_detail/` 비어 있음.

### Pitfall 4: market_update 는 상세만이 아니라 "변경사항 전부"를 민다
가격·상품명·옵션(option-cleanup·product-name 이 불사자에만 저장해 둔 것)까지 스토어로 나간다(도구 설명) [CITED: tools/list]. 게이트 ③ 체크가 그래서 있다. 미리보기 응답이 변경 필드를 알려 주면 표에 싣는다.

### Pitfall 5: 한 미리보기로 commit 이 여러 번
게이트 1건 commit 뒤 "나머지" commit 이 같은 미리보기에서 나와야 한다(대상 재선택 금지 L-02). 규칙: 같은 미리보기의 commit 은 **체크포인트에 taskId 없는 항목만** 대상, 최대 2회(게이트 전 1회 + 게이트 통과 후 1회). taskId 가 있는 항목은 절대 재접수하지 않는다. 미리보기가 오래됐으면(예: 24시간) 새 미리보기 요구 [재량].

### Pitfall 6: AI 반영 확인 필드 미검증
`aiImageGenerated` 가 생성 완료 상품에 실제로 찍히는지는 05-06 이 실측할 항목이다(지금 표본 전량 부재). **D-02 판정을 한 신호에 걸지 마라:** `aiImageGenerated` truthy **또는** 현재 `renderContent` ≠ ⓐ 백업 `renderContent`. 둘 다 아니면 `AI상세없음`. ⓐ 가 없으면 `backup_failed`(L-03).

### Pitfall 7: 복원 후 기작업 플래그
`detail_apply` 로 원문을 되돌려도 `aiImageGenerated` 가 남으면 이후 견적이 그 상품을 영영 `기작업` 으로 스킵할 수 있다 [ASSUMED]. restore 결과에 "재생성은 --force 필요할 수 있음" 을 적고, 복원 뒤 workdata 재조회 결과를 기록.

### Pitfall 8: 잡 수거가 폴링에 의존
`todos/pending/job-reap-depends-on-polling.md`: 브라우저 닫힌 채 끝난 WRITE 잡이 `running` 으로 남아 가드를 붙잡는다. 게이트 1건 commit 뒤 다음 commit 이 409 면 `GET /jobs/{id}` 한 번으로 수거된다 — 게이트 패널이 결과 표를 로드하며 자연히 부르도록.

### Pitfall 9: 실탄 중 웹앱 편집
05-06 Pitfall 4 그대로. 06 웹앱 플랜은 05-06 실탄이 끝난 뒤(또는 도는 잡 0 확인 후) 실행.

## Code Examples

### detail_batch.py 백업 주입 (시도 내부, 접수 직전)
```python
# 출처: detail_batch.py:568-584 시도() 구조
r = _판정(mcp, it, 태그맵, 실패코드, done_tags, args.pages, per_credit)   # r["dc"] 추가 반환
...
if args.backup_out:
    ok, why = _원본백업(Path(args.backup_out), it, r.get("dc") or {}, args.계정)
    if not ok:
        status[pid] = {"status": "접수실패", "사유": f"backup_failed: {why}"}
        return "fail"                                   # generate 0회 (L-03)
tid, exp = _입력접수(mcp, pid, r["imgs"], r["장수"], args.quality)

def _원본백업(폴더, it, dc, 계정):
    """AI 접수 직전 원본. 이미 있으면 덮지 않는다(첫 기록이 원본)."""
    try:
        폴더.mkdir(parents=True, exist_ok=True)
        경로 = 폴더 / f"{it['productId']}.json"
        if 경로.exists():
            return True, "기존 원본 유지"
        rc = dc.get("renderContent")
        if not isinstance(rc, str) or len(rc) < 10:
            return False, "renderContent 없음"
        문서 = {"productId": it["productId"], "판매자상품코드": it["판매자상품코드"],
               "조회시각": _지금(), "계정": 계정, "renderContent": rc,
               "imageTranslated": dc.get("imageTranslated")}
        with open(경로, "x", encoding="utf-8") as f:      # O_EXCL
            json.dump(문서, f, ensure_ascii=False)
        return True, ""
    except FileExistsError:
        return True, "기존 원본 유지"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"[:160]
```

### 복원 (restore 서브커맨드)
```python
# 출처: bulsaja-detail-remix/scripts/bulsaja_client.py:66-78 (2026-09-01 실측 스키마)
base = {"productId": pid, "html": 원본["renderContent"], "imageReplacements": [], "confirm": False}
pre = mcp.call_tool("bulsaja_detail_apply", base)          # --preview 는 여기서 멈춘다(쓰기 0 가정 — 스모크로 확인)
tok = pre.get("confirmationToken")
# --commit(사람 체크포인트 뒤): detail_apply confirm:true → workdata 재조회로 renderContent == 원본 확인 → market_update 1건
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| 배치 `productIds` 수백 건 접수 | 작은 배치/1건 + 사후 확정 | 2026-08-09/17 market_delete 실측 | 원자성 실패·대기열 포화 회피 |
| upload_tasks 1회 조회로 판정 | 종결 상태만 확정, 나머지 재조회·미확정 | 2026-08-09 | 조기 실패 오판 방지 |
| `bulsaja-yongssaem` 서버로 계정 전환 | `bulsaja` 서버 하나 = 부킹 | 2026-09-19 | SKILL 문서 서술 낡음 — 믿지 마라 |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `market_update(confirm:false)` 는 balanced 모드에서 쓰기 0, 토큰을 돌려준다 | Q1 | 미리보기가 실제 반영 — 스모크 diff 로 먼저 확인, 모드 가드·P0 알람으로 완화 |
| A2 | confirm:true 응답에 상품별 taskId 가 실린다(`market_delete` 의 `결과[]` 모양) | Q2 | 워터마크+productId 대체 매칭으로 동작은 유지 |
| A3 | 수정 작업의 `작업` 값은 "수정", 대기·진행 상태는 한국어 "대기"/"진행중" | Q2 | 문자열 필터 안 쓰므로 영향 작음 |
| A4 | marketGroupId 를 안 넘기면 서버가 상품의 업로드 그룹을 쓴다 | Q4 | 잘못된 그룹/거부 — 스모크 미리보기로 결정 |
| A5 | 상품 `uploadDetail_page` 사본이 수정업로드의 상하단 소스다 | Q4 | 게이트 ② 해석 재료일 뿐, 판정은 사람 육안 |
| A6 | `https://smartstore.naver.com/main/products/<번호>` 가 열린다 | Q4 | 링크가 안 열리면 번호 텍스트로 대체(항상 병기) |
| A7 | `detail_apply(confirm:false)` 도 쓰기 0 | 복원 | 복원 미리보기 스모크를 같은 diff 방식으로(workdata renderContent 전후 비교) |
| A8 | 잠금(`잠금:true`) 상품도 수정업로드는 막히지 않는다 | Q4 | 스모크 대상이 잠금 상품이라 미리보기 응답으로 판명 |
| A9 | 복원 후 `aiImageGenerated` 가 남는다 | Pitfall 7 | 재생성 스킵 — restore 뒤 재조회로 기록 |

## Open Questions

1. **confirm:false 응답 원문** — PENDING LIVE DATA (06-05 Task 1 스모크가 박제) — 무엇을 보여 주나(변경 필드·대상 그룹·토큰 TTL). → 라이브 스모크 태스크(쓰기 0 diff 포함)가 박제, 미리보기 표 컬럼은 그 뒤 확정.
2. **완료 상품의 AI 흔적 필드** — PENDING LIVE DATA (05-06 실측 → 06-05 에서 반영, 그 전엔 OR 규칙) — 05-06 실측(`aiImageGenerated`) 결과를 06 CLI 판정에 반영. 그 전엔 Pitfall 6 의 OR 규칙.
3. **D-03 · D-09 용팀장 확인** — RESOLVED (D-03: 06-01 이 05-06 전 머지 + STATE Blockers 순서 기록 · D-09: 06-05 Task 2 체크포인트에서 한 줄 확인) — D-03 은 05-06 전에(순서 변경), D-09 는 첫 실제 쓰기 체크포인트 전에 한 줄씩.
4. **상품 상하단 사본 vs 현재 그룹 설정** — RESOLVED (06-04 게이트 패널 · 06-06 육안 판정 체크포인트) — 그룹의 현재 top/bottom URL 을 MCP 로 못 읽는다(`market_groups` 응답에 없음 [VERIFIED]). 게이트에서 용팀장이 불사자 화면 설정과 스토어를 같이 본다.
5. **`market_poll` kind** — RESOLVED (06-03 에서 세 번째 kind 로 채택) — D-07 은 2종이지만 D-08 "이어서 확인" 에 접수 0 잡이 필요. 권장: 세 번째 kind `market_poll`(WRITE·BULSAJA·POLL_INCOMPLETE_OK) — `detail_poll` 과 같은 이유.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `.venv` Python (CLI) | market_update.py · detail_batch | ✓ | 3.12 | — |
| `.venv-web` pytest | 오프라인 테스트 | ✓ | 기존 스위트 613 통과(12.9초) | — |
| 불사자 MCP (`bulsaja`, 부킹) | 라이브 스모크·실행 | ✓ | 계정 부킹 확인 2026-09-26 | — |
| `/usr/bin/caffeinate` | market_commit | ✓ (기존 잡 argv 에 사용 중) | — | 없으면 프리픽스 생략(기존 규칙) |
| 사용자 웹앱 서버 :8765 | UAT·실행 | ✓ PID 45635, **--reload 없음** | — | 코드 반영엔 재시작 필요 |
| 스마트스토어 육안 확인 | 게이트 | 사람만 | — | 에이전트 불가(네이버 규칙) |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (`.venv-web`) — `webapp/pytest.ini` |
| Config file | `webapp/pytest.ini` (`cli/` 는 수집 제외) |
| Quick run command | `.venv-web/bin/pytest webapp/tests/test_detail_cli.py webapp/tests/test_market_cli.py -q` (<1초) |
| Full suite command | `.venv-web/bin/pytest webapp/tests -q` (~13초) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MARKET-03 | `--backup-out` 가 접수 직전 ⓐ 파일을 쓴다 · 내용 6키 · 기존 파일 불덮음 | unit(가짜MCP) | `pytest webapp/tests/test_detail_cli.py -k 백업` | ❌ Wave 0 (케이스 추가) |
| MARKET-03 | 백업 실패 → generate 0회 · 상태 접수실패/backup_failed | unit | 同 | ❌ |
| MARKET-03 | 플래그 없음/견적/poll-only → 백업 파일 0 · 골든 불변 | unit | `-k "골든 or 백업"` | ✅ 골든 / ❌ 신규 |
| MARKET-03 | DetailArgv submit 은 `--backup-out` 항상, estimate/poll 은 없음 | unit | `pytest webapp/tests/test_argv.py -k DetailArgv` | ❌ |
| MARKET-03 | market_update ⓐ 없으면 backup_failed 스킵 · ⓑ before_market 기록 | unit | `pytest webapp/tests/test_market_cli.py -k 백업` | ❌ |
| MARKET-01 | preview: `market_update` confirm:true 0회 · 토큰 없는 success → exit 2 P0 | unit | `-k 미리보기` | ❌ |
| MARKET-01 | 모드 fast → exit 2 · 계정 불일치 → exit 4 (MCP 쓰기 0) | unit | `-k "모드 or 계정"` | ❌ |
| MARKET-01 | 미업로드/AI상세없음/이미진행중 스킵 분류 | unit | `-k 스킵` | ❌ |
| MARKET-01 | commit: 상품당 2단, 새 토큰, taskId 선저장, 재실행 시 재접수 0 | unit | `-k 접수` | ❌ |
| MARKET-01 | 폴링: 창 매칭(taskId·워터마크 대체) · 성공/실패/DLQ · 미발견=대기 · 시간상한 exit 3 · 센티널 | unit(가짜시계) | `-k 폴링` | ❌ |
| MARKET-01 | `--commit` 에 `--max-items` 없으면 exit 2 | unit | `-k max_items` | ❌ |
| MARKET-02 | `--max-items` 초과 시 접수 전 exit 5 | unit | `-k 초과` | ❌ |
| MARKET-02 | 게이트 전 commit 라우트는 max_items=1 로 조립 · 게이트 이상이면 400 · 정상 후 N | integration(TestClient, spawn 몽키패치) | `pytest webapp/tests/test_routes_market.py` | ❌ |
| MARKET-02 | commit 은 미리보기 잡 id 하나만 받음 · 부모 체인/회차 검사 · 같은 미리보기 3번째 commit 거부 | integration | 同 | ❌ |
| MARKET-01/02 | kind 등록·가드 집합·caffeinate·exit3 done | unit | `pytest webapp/tests/test_jobs.py -k market` | ❌ |
| MARKET-03 | 결과/미리보기 표에 ⓐ·ⓑ 경로 텍스트 + 존재 여부 | integration(조각 렌더) | `test_routes_market.py -k 경로` | ❌ |
| MARKET-01 | 라이브 쓰기 0 스모크(upload_tasks·work_progress diff) | manual-live(크레딧 0) | 계획 태스크 스크립트 | ❌ evidence |
| MARKET-02 | 스토어 육안 확인 | manual-only (네이버 — 사람) | — | — |
| UI | 보드 버튼·미리보기·게이트 패널·결과 표 | uat-verifier(격리 포트·DB 사본·시드, spawn 가짜) | — | — |

### Sampling Rate
- **Per task commit:** quick run
- **Per wave merge:** full suite + `node --check webapp/static/board.js` + `no_commit_guard.sh`
- **Phase gate:** full suite green + uat-verifier PASS + 라이브 스모크 evidence + 게이트 판정 기록

### Wave 0 Gaps
- [ ] `webapp/tests/test_market_cli.py` — `test_detail_cli.py` 의 `cli` 픽스처·`가짜MCP`·`가짜시계` 복제(파일 로드 + `sys.modules["bulsaja_mcp"]` 스텁). 시나리오 도구: `bulsaja_my_profile`, `bulsaja_mcp_settings`, `bulsaja_product_workdata`, `bulsaja_market_update`, `bulsaja_upload_tasks`, `bulsaja_detail_apply`. **시나리오에 없는 도구 호출 = 즉시 실패**(예상 밖 쓰기 차단)
- [ ] 픽스처 `fixtures/upload_tasks_real.json` — 이 세션 실측 모양(30건 창, 한국어 상태, 실패사유) 익명화본
- [ ] `webapp/tests/test_routes_market.py`
- [ ] 프레임워크 설치: 없음

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no (127.0.0.1 단일 사용자) | 기존 `security.guard` 토큰·Origin |
| V3 Session Management | no | — |
| V4 Access Control | yes (쓰기 라우트) | POST 전용 · 기존 페이지 토큰/Origin 검사 · GET 은 작업 생성 금지(V-SAFE 스캐너) |
| V5 Input Validation | yes | Pydantic 요청 모델: **잡 id 하나만**(대상·상한·마켓 필드 없음) · `MarketArgv` Nick/PlainArg · 경로는 웹앱이 생성 |
| V6 Cryptography | no | 토큰은 `~/.claude.json` 런타임 로드, 로그 출력 금지(기존) |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| 미리보기가 실제 쓰기(확인 모드 변경) | Tampering | 모드 가드 exit 2 · 토큰 없는 성공 P0 중단 · 스모크 diff |
| 틀린 계정에 반영(남의 스토어) | Spoofing | BULSAJA 사전점검 409 + CLI `--expect-nick` exit 4 (ENG-08) |
| 대상 바꿔치기(요청에 상품 목록) | Tampering | 실행 라우트는 미리보기 잡 id 하나 · targets 는 서버가 detail_status.json 에서 |
| 게이트 우회(대량 반영) | Elevation | 서버 max_items 결정 + CLI exit 5 · `market_gate` 쓰기는 POST+토큰 · 판정 `이상` 이면 commit 400 |
| 되돌릴 수 없는 스토어 변경 | Repudiation/Tampering | ⓐ·ⓑ 백업 없으면 쓰기 없음 · restore CLI · 모든 confirm:true 는 L-01 사람 체크포인트 |
| 이중 반영 | Tampering | taskId 선저장 · taskId 보유 항목 재접수 금지 · 서버 중복 차단은 `이미진행중` 스킵 |
| 서버 원문(사유·HTML) 렌더 XSS | Tampering | Jinja2 자동 이스케이프 · `| safe` 금지 · 백업 HTML 은 화면에 안 띄움(경로만) |
| 내부 ID 노출 | Info disclosure | taskId 끝 8자리만 표시(T-05-20 관용) · 로그에 토큰 마스킹 |

## Project Constraints (from CLAUDE.md)

- 반말 · 결론 먼저. 코드: Python, **한국어 주석**, try-except 포함.
- 웹앱은 기존 CLI 의 **래퍼** — 검증된 로직 재작성 금지. 모든 쓰기는 **dry-run 선행**. 진실의 원천은 불사자 서버(로컬 대장 금지).
- 맥북 로컬 단독, `--workers 1`, `127.0.0.1`. 기술 스택: FastAPI+Jinja2+htmx+stdlib sqlite3, 새 의존성 없음.
- GSD 워크플로 안에서만 편집.
- 검증: 기능 검증은 `uat-verifier` 에이전트(격리 포트·DB 사본). 사람 몫은 ①심미 ②되돌릴 수 없는 외부 작업 실행 승인(= 마켓 반영) ③네이버 로그인 필요한 확인(= 스토어 육안 게이트) ④법적 문구.
- **AI 는 네이버·스마트스토어에 직접 접속하지 않는다** — 게이트 확인은 용팀장 브라우저, 에이전트는 확인 절차만 적어 준다.
- 메모리: 백그라운드 작업은 완료 감시와 함께 · 판정 큐엔 판매자상품코드 표기 · 계정 기대값 부킹 · 폴링 타임아웃은 실패가 아니다(재실행 = 이중 지불).

## Sources

### Primary (HIGH confidence)
- 불사자 MCP 실호출(읽기 전용, 2026-09-26): `tools/list` 스키마(market_update/upload/delete, upload_tasks, detail_apply, workdata, find_by_code, market_groups, mcp_settings, work_progress, market_guard) · `upload_tasks list`(기본/status 4종/taskIds/taskId) · workdata summary/full · find_by_code · market_groups · mcp_settings get · work_progress
- 코드: `detail_batch.py`(135, 376-416, 445-464, 538-680) · `category_gate.py`(780-905) · `run_options.py:143-180` · `bulsaja-detail-remix/scripts/bulsaja_client.py:66-78` · `eroomlib/bulsaja.py` · `eroomlib/runner/propagate.py:106-130` · `webapp/argv.py:310-367` · `webapp/jobs.py`(68-215, 396-404, 555-660, 795-1060, 1201) · `webapp/routes/jobs.py`(345-477, 1182-1296, 1337-1373) · `webapp/settings.py` · `webapp/banner_store.py` · `webapp/tests/test_detail_cli.py`
- 문서: `.claude/skills/_shared/불사자-안전규칙.md` · `bulsaja-category-fix/SKILL.md:540-600` · 05-01/03/04 SUMMARY · 05-04 zero-cost evidence · 05-05 estimate evidence · 05-06-PLAN · PITFALLS §10·11 · PROJECT.md §contradiction
- 운영 상태: `webapp.db`(ro) 최근 잡 · `ps`(uvicorn PID 45635, --reload 없음) · run-dir 2026-09-20 join/estimate

### Secondary (MEDIUM)
- `00-inbox/2026-09-19-스마트스토어-상하단이미지-교체-인계.md` 확정사실 1·6 (용팀장 실측 기재, 이 세션 재확인 불가)

### Tertiary (LOW)
- 스마트스토어 상품 URL 모양 (A6) — 훈련 지식

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — 새 의존성 0, 전부 기존 코드
- Architecture: HIGH — Phase 5 detail 슬라이스와 동형, 통합 지점 줄 번호 확인
- upload_tasks 매칭: HIGH(스키마·창·필터 무시 실측) / 접수 응답 taskId: MEDIUM(ASSUMED A2)
- confirm:false 쓰기 0: MEDIUM — 동형 도구 실측 다수 + 모드 조건부 발견, 이 도구 자체는 스모크 필요
- Pitfalls: HIGH

**Research date:** 2026-09-26
**Valid until:** 2026-10-10 (불사자 MCP 서버 도구 설명·스키마가 수시로 바뀐다 — 실행 직전 tools/list 재확인 권장)
