# Phase 6: 마켓 수정업로드 (market-update) - Pattern Map

**Mapped:** 2026-09-26
**Files analyzed:** 19 (수정 10 · 신규 9)
**Analogs found:** 18 / 19 (새 패턴 0에 가깝다 — 전부 Phase 5 detail 슬라이스 + Phase 4 `banner_store` + `category_gate` upload_tasks 확정 로직을 따라 쓴다)

> 결론: **Phase 5 detail 슬라이스를 "market" 이름으로 한 벌 더 복사하면 된다.** 견적→접수→이어서 확인 = 미리보기→반영→이어서 확인. 새로 설계하는 건 둘뿐이다: ① `market_gate` 사람 판정 기록(→ `banner_store.py` 모양) ② upload_tasks 30건 창 매칭(→ `category_gate.verify_tasks` 모양 + 워터마크).

## File Classification

| 신규/수정 파일 | 역할 | 데이터 흐름 | 가장 가까운 기존 코드 | 일치도 |
|---|---|---|---|---|
| `.claude/skills/bulsaja-detail-page/scripts/detail_batch.py` (수정: `--backup-out` + `_원본백업`) | CLI | batch + file-I/O | 같은 파일 `시도()` 568-607 · `save_json` 63-70 · `_입력모드` 683-721 · 인자 745-759 | exact |
| `.claude/skills/bulsaja-detail-page/scripts/market_update.py` (신규: preview/commit/poll/restore) | CLI | batch + request-response (MCP) + polling | `detail_batch.py` 전체 뼈대(40-52 import, 323-334 계정, 445-464 2단 접수, 507-535 마무리/센티널, 538-680 접수와폴링, 683-721 진입점) + `category_gate.verify_tasks` 868-906 + `bulsaja_client.apply_detail` 66-78 | exact |
| `webapp/argv.py` (+`MARKET_UPDATE` 상수, +`MarketArgv`, `DetailArgv.backup_out`) | config/argv 모델 | transform | 같은 파일 `DETAIL_BATCH` 59-62 · `DetailArgv` 310-367 | exact |
| `webapp/jobs.py` (kind 3종 · 가드 집합 · `_마켓폴더` · `_build_argv` 분기 · result_path · DDL `market_gate` · detail 분기에 backup_out) | service (잡 엔진) | event-driven (subprocess) | 같은 파일 detail 등록 전부: 68-78, 87-106, 134-136, 396, 575-617, 649, 799-828, 1016-1023, DDL 190-205 | exact |
| `webapp/market_gate_store.py` (신규: DDL 0줄, 읽기 ro / 쓰기 INSERT) | store | CRUD (사람 기록) | `webapp/banner_store.py` 1-232 전체 | exact |
| `webapp/routes/jobs.py` (+`/jobs/market/preview`·`/commit`·`/poll` + `_마켓미리보기ctx`·`_마켓결과ctx` + 결과 조각 분기) | controller | request-response | `DetailSubmitReq` 232-250 · `_상세견적ctx` 311-342 · `_상세결과ctx`·헬퍼 345-477 · `_상세잡만들기` 1182-1202 · `post_detail_submit` 1205-1257 · `post_detail_poll` 1260-1290 · `get_job_result` 1359-1366 | exact |
| `POST /market/gate` (routes/jobs.py 안 또는 `webapp/routes/market.py` 신규) | controller | request-response (사람 판정 쓰기) | `webapp/routes/banner.py` `ConfirmReq` 81-85 · `post_confirm` 347-362 | exact |
| `webapp/settings.py` (Phase 6 블록: `market_update_max_items`·`market_poll_interval`·`market_max_poll_min`) | config | — | `DEFAULTS` Phase 5 블록 95-103 | exact |
| `webapp/templates/_market_preview_table.html` (신규) | template | 표시 | `_detail_estimate_table.html` (92줄) | exact |
| `webapp/templates/_market_result_table.html` (신규) | template | 표시 | `_detail_result_table.html` 1-71 | exact |
| `webapp/templates/_market_gate_panel.html` (신규) | template | request-response (htmx POST) | `banner_review.html` 확인 버튼 304-318 + `_detail_result_table.html` 43-50 stale 블록 | role-match |
| `webapp/templates/_detail_result_table.html` (수정: `스마트스토어 반영 미리보기 — 쓰기 0` 버튼) | template | request-response | 같은 파일 43-50 `.detail-poll-btn` | exact |
| `webapp/templates/_job_status.html` (kind 이름 3개 + 종료코드 문구) | template | 표시 | 같은 파일 27-29, 68-69, 85-86 | exact |
| `webapp/static/board.js` (market 버튼 위임 배선) | component (JS) | request-response | `상세작업접수` 729- · `.detail-poll-btn` 위임 792-797 · `상세결과불러오기` 722-727 | exact |
| `webapp/tests/test_detail_cli.py` (수정: 백업 케이스) | test | 오프라인 가짜 MCP | 같은 파일 `cli` 52-78 · `가짜MCP` 99-125 · `주입`/`실행` 128-147 | exact |
| `webapp/tests/test_market_cli.py` (신규) | test | 오프라인 가짜 MCP | `test_detail_cli.py` 1-147 (복제) | exact |
| `webapp/tests/test_routes_market.py` (신규) | test | integration (TestClient) | `test_routes_jobs.py` detail 묶음 642-1080 | exact |
| `webapp/tests/test_jobs.py` · `test_argv.py` (추가) | test | unit | `test_jobs.py` 1314-1495 detail 묶음 | exact |
| `webapp/tests/fixtures/upload_tasks_real.json` · `market_targets_min.json` (신규) | fixture | — | `fixtures/detail_inputs_min.json` · 익명화 규율(`zz*`) | role-match |

---

## Pattern Assignments

### `detail_batch.py` — `--backup-out` 주입구 (CLI, file-I/O)

**규율:** 플래그 없는 줄은 한 줄도 안 건드린다(L-04). 새 분기는 전부 `if args.backup_out:` 안. 골든(`fixtures/detail_golden_noflag.json`)이 자동 집행.

**인자 추가 자리** (745-759, 05-01 주입구 블록 끝에):
```python
    ap.add_argument("--summary-out", help="접수/폴링 결과 요약 JSON 경로")
    # → ap.add_argument("--backup-out", help="AI 접수 직전 원본 상세 백업 폴더 (MARKET-03 · D-03)")
```

**`_판정` 이 `dc` 를 돌려주게** (396, 413-414) — 결과 dict 에 키 하나 추가:
```python
    dc = data.get("uploadDetailContents") or {}
    ...
    결과.update({"판정": "접수", "사유": "", "장수": sc,
                 "크레딧": sc * per_credit, "imgs": imgs[:sc]})   # + "dc": dc
```
견적 경로(`_견적` 423-427)는 키를 골라 담으므로 영향 없음.

**주입 지점** — `시도()` 581(상한 검사 뒤) · 583 `_입력접수` 직전:
```python
            try:
                tid, exp = _입력접수(mcp, pid, r["imgs"], r["장수"], args.quality)
            except Exception as e:
                ...
                status[pid] = {"status": "접수실패", "error": str(e)[:200]}
                return "fail"
```
→ 그 앞에 `if args.backup_out: ok, why = _원본백업(...); if not ok: status[pid] = {"status": "접수실패", "사유": f"backup_failed: {why}"}; return "fail"`. 상태어휘 `접수실패` 재사용 → `_요약상태` 496 · 웹앱 `_상세항목상태` 387 이 이미 인식(새 어휘 금지).

**계정 닉 흘리기:** `_입력모드` 711 에서 `계정` 을 받는다 → `args` 에 싣거나 `_접수와폴링` 인자로 넘긴다(재량). `_원본백업` 본문은 RESEARCH §Code Examples 373-405 그대로(O_EXCL `open(경로, "x")` · 기존 파일 불덮음).

---

### `market_update.py` (신규 CLI, batch + MCP + polling)

**Analog:** `detail_batch.py` inputs 모드 경로 전체. 파일 구조를 그대로 복사한다.

**머리 (40-52)** — 그대로 복사:
```python
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILLS_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", ".."))
SKILL_SCRIPTS = os.path.join(SKILLS_DIR, "bulsaja-category-fix", "scripts")
sys.path.insert(0, SKILL_SCRIPTS)
from bulsaja_mcp import BulsajaMCP  # noqa: E402
```
→ 이 모양이어야 `test_market_cli.py` 의 `sys.modules["bulsaja_mcp"]` 스텁이 먹는다. `ss_index_calls.목록꺼내기`(68-) 는 `_태그조회` 346-348 식 **지연 import**.

**유틸 복사(또는 동일 구현):** `load_json`/`save_json` 55-70 · `sanitize` 73- · `_표시규칙제거` 272-280 · `_지금` 282- · `_계정확인` 323-334.

**진입점 모양** `_입력모드` 683-721:
```python
    if not args.estimate_only and not args.poll_only:
        if args.max_credits is None or args.max_credits < 0:
            print("⛔ --inputs 접수 모드는 --max-credits(0 이상)가 필요하다 (D-14)", flush=True)
            return EXIT_INPUT
    mcp = BulsajaMCP()
    mcp.open()
    try:
        계정, 잔액, 통과 = _계정확인(mcp, args.expect_nick)
        if not 통과:
            print(f"⛔ 붙어 있는 불사자 계정({계정})이 기대 계정 ..."); return EXIT_NICK
        ...
    finally:
        mcp.close()
```
→ `--commit` + `--max-items` None → EXIT_INPUT(2) (D-06). 계정 직후 `bulsaja_mcp_settings(mode=get)` → `confirmationMode ∉ {strict, balanced}` 면 exit 2 (RESEARCH Q1).

**2단 접수 (445-464 `_입력접수`)** — 상품당 1호출로 바꿔 복사:
```python
    base = {..., "confirm": False}
    pre = mcp.call_tool("bulsaja_detail_page_generate", base) or {}
    token = pre.get("confirmationToken")
    if not token:
        raise RuntimeError(f"확인토큰 없음: {str(sanitize(pre))[:150]}")
    fin = mcp.call_tool(..., {**base, "confirm": True, "confirmationToken": token}) or {}
    tid = extract_task_id(fin)
```
→ 차이: 토큰 없음 + (`success` or taskId) = P0 "쓰기의심" 중단 exit 2 (RESEARCH Pattern 1 284-301). `--preview` 는 confirm:false 에서 멈추고 토큰을 **저장하지 않는다**. 응답 결과 행 해석은 `category_gate.delete_batch` 840-864(`_rows` · `결과` · `taskId` · 응답에 없는 pid 는 실패로 setdefault).

**taskId 선저장 + 재접수 금지 (591-594, 551-558)**:
```python
            status[pid] = {"taskId": tid, "status": "접수", "pages": sc}
            save_json(status_path, status)
    ...
        def 필요(it):
            ...
            return not v.get("taskId") and not is_done(st)
```
→ 체크포인트 = `<run-dir>/market_status.json`. `--max-items` 검사는 `시도()` 578-581 `budget` 자리에서: `taskId 보유 수 + 1 > max_items` → EXIT_BUDGET(5) 접수 전 중단.

**폴링 확정 (`category_gate.verify_tasks` 868-906)**:
```python
            for r in _rows(resp, "마켓작업"):
                tid = str(r.get("taskId") or "")
                if tid not in pend or tid in seen:
                    continue      # 이 조회는 무관한 최근 작업도 같이 돌려준다
                st = str(r.get("상태") or "")
                if st not in TASK_FINAL:
                    continue      # 대기·진행중 — 아직 끝나지 않았다
    for pid in pend.values():
        out.setdefault(pid, (False, "미확정(...)"))
```
→ 차이: `taskIds` 필터를 넘기지 말 것(무시됨) · `list` 기본 + status SUCCESS/FAILED/DLQ 창 합치기(RESEARCH Pattern 2 303-318) · `_rows` 대신 `목록꺼내기`(키 없음 = 조회 실패 예외) · 미확정은 실패 아님 → 루프는 `detail_batch` 647-679 deadline 모양, 남으면 EXIT_POLL(3).

**마무리/센티널 (507-535)** — `_마무리` 복사, 마지막 줄만:
```python
    print(f"###DETAIL### 완료 {집계['완료']} / 실패 {집계['실패']} / 스킵 {집계['스킵']}"
          f" / 폴링미완 {집계['폴링미완']} / 전체 {len(items)}", flush=True)
```
→ `###MARKET### 성공 a / 실패 f / 스킵 s / 대기 p / 전체 t`.

**restore 서브커맨드** — `bulsaja-detail-remix/scripts/bulsaja_client.py:66-78` `apply_detail` 모양(`productId`·`html`·`imageReplacements: []`·confirm 2단). `--preview` 는 confirm:false 에서 멈춤.

**종료코드 상수:** detail_batch 의 `EXIT_OK/EXIT_INPUT/EXIT_POLL/EXIT_NICK/EXIT_BUDGET` (0/2/3/4/5) 이름 그대로.

---

### `webapp/argv.py` — `MarketArgv` + `DetailArgv.backup_out`

**경로 상수** (59-62 옆):
```python
DETAIL_BATCH = (paths.repo_root() / ".claude" / "skills" / "bulsaja-detail-page"
                / "scripts" / "detail_batch.py")
# → MARKET_UPDATE = (... / "bulsaja-detail-page" / "scripts" / "market_update.py")
```

**`DetailArgv` 수정** (331-366): 필드 `backup_out: Path | None = None` 추가, `mode == "submit"` 분기(360-363)에서:
```python
            if self.mode == "submit":
                if self.max_credits is None:
                    raise ValueError("접수 모드에는 max_credits 가 필요하다 — 상한 없는 접수는 없다")
                av += ["--max-credits", str(self.max_credits)]
```
→ 바로 아래 `if self.backup_out is None: raise ValueError("백업 없는 접수는 없다 (MARKET-03)")` + `av += ["--backup-out", str(self.backup_out)]`. estimate/poll 은 안 붙임.

**`MarketArgv` 신규** — `DetailArgv` 310-367 모양 그대로: `mode: Literal["preview","commit","poll"]`, 전부 기본값 없음(`expect_nick: Nick`, `max_items: int | None`, `poll_interval`, `max_poll_min`, `run_dir: Path`, `targets: Path`, `backup_dir`, `detail_backup_dir`, `summary_out`), `prefix: list[str] = []`. 경로·숫자 전부 `str()`. commit 인데 `max_items` None → ValueError(빈 값 ≠ 전량).

---

### `webapp/jobs.py` — kind 3종 (service, event-driven)

**① kind 둘 같이** (68-78): `JobKind` Literal + `KINDS` 튜플에 `"market_preview", "market_commit", "market_poll"`.

**② 가드 집합** — 집합마다 위에 한국어 "왜" 단락(87-106, 134-136 관례):
```python
WRITE_KINDS = frozenset({..., "detail_submit", "detail_poll"})        # + market_commit, market_poll
BULSAJA_KINDS = frozenset({..., "detail_estimate", "detail_submit", "detail_poll"})  # + 셋 다
SINGLETON_KINDS = frozenset({..., "detail_estimate"})                 # + market_preview
POLL_INCOMPLETE_OK_KINDS = frozenset({"detail_submit", "detail_poll"})  # 396 + market_commit, market_poll
```
`_finish` 399-403 은 kind 를 이미 받으므로 수정 불필요.

**③ 수면방지** (649):
```python
    if kind not in ("bulsaja_index", "banner_scan", "detail_submit", "detail_poll"):   # + market_commit, market_poll
```

**④ `_마켓폴더` / `_마켓부모`** — `_상세부모`·`_상세폴더` 575-617 복제:
```python
_상세부모 = {"detail_submit": "detail_estimate", "detail_poll": "detail_submit"}
...
        부모 = _행(parent_job_id)
        if 부모 is None or 부모["kind"] != 기대:
            raise ValueError(f"{kind} 의 부모는 {기대} 여야 한다")
        if 부모["run_dir"] != run_dir:
            raise ValueError("부모 잡과 회차가 다르다")
    d = _web_dir(run_dir) / f"detail_{견적id}"
```
→ 차이: `market_preview` 의 부모 = `detail_submit`/`detail_poll`(둘 중 하나 — 집합으로), 폴더 id = 미리보기 잡 id → `market_<미리보기id>/`. commit 부모 = preview, poll 부모 = commit/poll → 체인 따라 미리보기 id 복원. ⓐ 폴더(`detail_backup_dir`)는 preview 부모 detail 잡의 `result_path.parent / "before_detail"`.

**⑤ `_build_argv` 분기** — 799-828 모양:
```python
    if kind in ("detail_estimate", "detail_submit", "detail_poll"):
        if targets_path is None:
            raise ValueError("상세 잡에는 inputs 파일이 반드시 있어야 한다 — 빈 값은 전량이 아니다")
        ...
        settings.load(force=True)
        return argv_mod.DetailArgv(..., expect_nick=settings.cfg("expected_bulsaja_nick", required=True),
            poll_interval=int(settings.cfg("detail_poll_interval", settings.DEFAULTS["detail_poll_interval"])),
            ..., prefix=_수면방지_프리픽스(kind)).build()
```
→ detail 분기에 `backup_out=detail_dir / "before_detail" if kind == "detail_submit" else None` 추가(D-03). market 분기는 `max_items` 를 kwarg 로 받는다(시그니처에 `max_credits` 처럼 한 개 추가 · 1029-1032 호출부도).

**⑥ create_job** (833-): 인자 `max_items: int | None = None` 추가. result_path 분기 1016-1023 옆에 `elif kind in MARKET_KINDS:` → preview `market_dir / "preview.json"`, commit/poll `market_dir / f"summary_{job_id}.json"`. 가드 순서(①.5 계정 → BEGIN IMMEDIATE → WRITE → SINGLETON → 회차 → 대상 → argv → INSERT → spawn) **불변**. 미리보기 targets 는 `_write_detail_inputs` 560-571 (tmp→`os.replace`, `web/targets_<id>.json` — `_override_targets` 부모==web/ 검사 통과) 재사용 또는 동형 writer.

**⑦ DDL** (158-206 문자열 끝, `banner_confirm` 뒤) — `CREATE TABLE IF NOT EXISTS market_gate (...)` (RESEARCH Q6 90행 스키마). 아래 주석에 "완료 대장이 아니라 사람 판정 기록 — L-05 비충돌" 을 적는다(207-219 관례).

**⑧ `children_of`** (1201-1221) 그대로 사용 — commit 라우트의 "같은 미리보기 최대 2회" 판정.

---

### `webapp/market_gate_store.py` (신규 store)

**Analog:** `webapp/banner_store.py` — 파일 전체 모양 복사.
- 모듈 docstring 17-32 "이 모듈이 절대 하지 않는 것" 구조 복사 — **DDL 0줄**, 테이블 정본은 `jobs.DDL`, DDL 낱말을 주석에도 안 쓴다(grep 가드).
- `db_path` 41-51 · `_ro_conn` 54-62 · `_conn` 65-69 · `_now` 72-74 그대로.
- 읽기 (`확인시각읽기` 143-165 모양):
```python
    if not db_path().is_file():
        return {}
    try:
        cx = _ro_conn()
    except sqlite3.Error:
        return {}
    try:
        행들 = cx.execute("SELECT ... FROM banner_confirm WHERE run_dir = ?", (키,)).fetchall()
    finally:
        cx.close()
```
→ `최신판정()` = `SELECT ... FROM market_gate ORDER BY id DESC LIMIT 1` → None / dict. `통과()` = 최신이 `정상`. **DB 없음/못 엶 → None = 게이트 닫힘(안전 쪽)**.
- 쓰기 (`확인기록` 211-232 모양): 빈 값 ValueError → `_conn()` → `INSERT` (REPLACE 아님 — 판정 이력 누적) → `commit()`. 판정 화이트리스트(`정상`/`이상`) 한 번 더 확인(`라벨기록` 193-194 관례).

---

### `webapp/routes/jobs.py` — market 라우트 3개 + ctx 2개 (controller)

**요청 모델** — `DetailSubmitReq`/`DetailPollReq` 232-250 복사: `MarketPreviewReq(detail_job_id: JobId)`, `MarketCommitReq(preview_job_id: JobId)`, `MarketPollReq(commit_job_id: JobId)`. 대상·상한·마켓 필드 **없음**(docstring 에 이유).

**미리보기 라우트** — `post_detail_submit` 1221-1233 부모 검사 3단:
```python
    부모 = jobs.job_status(req.estimate_job_id)
    if 부모 is None or 부모.get("kind") != "detail_estimate":
        raise HTTPException(status_code=400, detail="견적 작업이 아니다 — 먼저 상세 견적부터 해라")
    if 부모.get("status") in jobs.LIVE_STATUSES:
        raise HTTPException(status_code=400, detail="견적이 아직 안 끝났다 — 끝나고 다시 눌러라")
```
→ 부모 kind ∈ {detail_submit, detail_poll}. 대상 = `_상세체크포인트(_상세폴더_of(부모))`(355-363) 에서 `_상세항목상태(v) == "완료"`(376-395) 인 pid 만 + 부모 targets `items` 에서 판매자상품코드 보충. 0건 → 400. **exit 3 done 도 허용**(완료분만 뽑으므로).

**반영 라우트** — `post_detail_submit` 1245-1257 의 "이미 접수" 판정:
```python
    체크 = _상세체크포인트(폴더) or {}
    돈나감 = any(isinstance(v, dict) and v.get("taskId") for v in 체크.values())
    for 자식 in jobs.children_of(req.estimate_job_id, "detail_submit"):
        if 자식.get("status") != "failed" or 돈나감:
            raise HTTPException(status_code=400, detail="이 견적으로 이미 접수했다 — ...")
```
→ market 규칙: 같은 미리보기 commit 은 최대 2회(게이트 전 1 + 통과 후 1, RESEARCH Pitfall 5). `max_items = 1 if not market_gate_store.통과() else settings.cfg("market_update_max_items", ...)` — 요청값 없음. 최신 판정 `이상` → 400.

**이어서 확인** — `post_detail_poll` 1270-1290 그대로(부모 kind 집합만 교체, 허용 = done+exit3 또는 done/orphaned+미종결>0).

**예외 번역** — `_상세잡만들기` 1182-1202 재사용(AccountMismatchError → 409 가 ValueError 보다 먼저).

**결과 ctx** — `_상세결과ctx` 404-477 모양: `LIVE_STATUSES` → running, 정본 = `market_status.json`(없으면 error), summary 는 사유 보충, taskId 끝 8자리(461-462), 집계는 여기서 계산. 백업 경로 ⓐ·ⓑ 는 **경로 문자열 + `Path.is_file()`** 만(내용 읽지 않음). 미리보기 ctx 는 `_상세견적ctx` 311-342 모양(preview.json 읽기, 깨지면 종료코드 안내).

**결과 조각 분기** (1359-1366):
```python
        "detail_submit": ("_detail_result_table.html", _상세결과ctx),
        "detail_poll": ("_detail_result_table.html", _상세결과ctx),
```
→ `"market_preview": ("_market_preview_table.html", _마켓미리보기ctx)`, commit/poll → `("_market_result_table.html", _마켓결과ctx)`.

**배치:** POST 는 1293 "여기서부터 읽기 전용" **위**. GET 추가 없음.

---

### `POST /market/gate` (사람 판정 쓰기)

**Analog:** `routes/banner.py` `ConfirmReq` 81-85 · `post_confirm` 347-362:
```python
@router.post("/banner/confirm")
async def post_confirm(request: Request):
    요청 = await _요청_풀기(request, ConfirmReq)
    _회차확인(요청.run_dir)
    try:
        banner_store.확인기록(요청.run_dir, 요청.타오바오상품번호)
    except Exception as e:
        raise _쓰기예외(e)
    return HTMLResponse(f'<span class="ct-confirmed" ...>확인함</span>')
```
→ `GateReq(commit_job_id: JobId, 판정: Literal["정상","이상"], 스토어교체여부: ..., 메모: str 상한)`. 서버가 commit 잡의 체크포인트에서 성공 1건의 판매자상품코드·productId 를 읽어 기록(화면 값 안 믿음). htmx 폼·JSON 둘 다(`_요청_풀기`). 응답은 게이트 패널 조각. 토큰·Origin 은 `security.guard` 가 자동.

---

### 템플릿 3종 + `_detail_result_table.html` 버튼

**뼈대** — `_detail_result_table.html` 18-25 순서 고정:
```jinja
{% if running %}
  <p>상세 작업이 도는 중이다… 위 진행 로그를 봐라. ...</p>
{% elif error %}
  <p class="stale"><strong>결과를 못 읽었다 — {{ error }}</strong><br>
    빈 표를 결과로 읽지 않게 표를 그리지 않는다.</p>
{% else %}
  {# 집계 줄 — 규모를 먼저 읽는다 #}
```
- 파일 머리 주석 1-16 모양: 정본 · "그리지 않는 것(의도)" 목록(재반영 버튼 없음 · 복원 버튼 없음 D-05) · `| safe` 금지.
- 결과 표 컬럼: 판매자상품코드 · 상태 · 사유 · ⓐ 경로(+있음/없음) · ⓑ 경로 · 작업번호 끝 8자리 (53-69 테이블 복사).
- 이어서 확인 블록 43-50 복사 → 클래스 `market-poll-btn`, `data-commit-job`.
- 미리보기 버튼(`_detail_result_table.html` 에 추가): 43-50 블록 모양으로 `{% if 집계.get("완료", 0) %}<button class="market-preview-btn" data-detail-job="{{ job.id }}">스마트스토어 반영 미리보기 — 쓰기 0</button>{% endif %}`.
- 게이트 패널: 체크 3개 + 두 버튼 `hx-post="/market/gate"` — `banner_review.html` 304-318 의 hx 속성 블록(`hx-vals` · `hx-target="this"` · `hx-swap="outerHTML"`) 복사. 스토어 링크는 번호 텍스트 병기(A6).

### `_job_status.html`
27-29 `작업이름` 에 `"market_preview": "마켓 반영 미리보기"` 등 3개. 68-69 running 문구 kind 분기 추가. 85-86 종료코드 계약 블록 복사(2 입력·P0 / 4 계정 / 5 상한 초과).

### `board.js`
`.detail-poll-btn` 위임 792-797 모양 그대로 3개:
```js
  document.addEventListener("click", function (ev) {
    var 버튼 = ev.target.closest ? ev.target.closest(".detail-poll-btn") : null;
    if (!버튼 || 버튼.disabled) { return; }
    상세작업접수("/jobs/detail/poll", { submit_job_id: 버튼.dataset.submitJob }, 버튼, "이어서 확인");
  });
```
→ `.market-preview-btn` → `/jobs/market/preview {detail_job_id}`, `.market-commit-btn` → `/jobs/market/commit {preview_job_id}`, `.market-poll-btn`. 결과는 `상세결과불러오기` 722-727 모양으로 `#market-result-body`(또는 `#detail-result-body` 아래 새 섹션). 몸통엔 잡 id 하나만.

### `settings.py`
95-103 Phase 5 블록 아래 `# ── Phase 6 (마켓 수정업로드) 에서 더한 키 ──` 주석 + `"market_update_max_items": 20`, `"market_poll_interval": 20`(재량, RESEARCH Q2 15~30초), `"market_max_poll_min": 30`(재량). 읽기는 `settings.cfg("키", settings.DEFAULTS["키"])` 로만.

---

### 테스트

**`test_market_cli.py`** — `test_detail_cli.py` 36-147 복제: `cli` 픽스처(스텁 `bulsaja_mcp` → `spec_from_file_location` → finally 로 `sys.path`·`ss_index_calls` 원복), `가짜시계`, `가짜MCP`("시나리오에 없는 도구 호출 = AssertionError"), `주입`, `실행`(SystemExit.code). 시나리오 도구 6개: `bulsaja_my_profile`, `bulsaja_mcp_settings`, `bulsaja_product_workdata`, `bulsaja_market_update`, `bulsaja_upload_tasks`, `bulsaja_detail_apply`. 단언 예: `mcp.이름들("bulsaja_market_update")` 에 `confirm: True` 가 preview 에서 0회.

**`test_detail_cli.py` 추가** — 백업 5케이스(RESEARCH Q3 57행). 골든 테스트는 손대지 않는다.

**`test_jobs.py`** — 1314-1331 · 1471-1491 복사: kind 등록(`KINDS` + `JobKind.__args__`), 가드집합, 수면방지, exit3=done(market_commit/poll) · 다른 kind 는 여전히 failed, `_build_argv` targets None ValueError, 폴더 체인 거부(1422-).

**`test_routes_market.py`** — `test_routes_jobs.py` 897-1080 복사: 토큰없이 403 · GET 아님 · 부모만 가리킴 · 부모 kind/running/failed 400 · 잡id 모양 422 · 계정불일치 409 · 진짜 create_job argv(1010-) · 이어서 확인 허용/거부. 추가: 게이트 전 argv `--max-items 1` · `이상` 최신이면 400 · 같은 미리보기 3번째 commit 400 · 조각에 ⓐ/ⓑ 경로 텍스트. 픽스처 `화면`·`엿듣기`·`안띄운다`·`프로필`·`기대닉`·`tmp_run_dir` 재사용.

**`test_argv.py`** — 트리 가드 162-247 가 새 코드에 자동 적용. `DetailArgv` submit 은 `--backup-out` 항상 · estimate/poll 은 없음 · submit 에 backup_out None 이면 ValueError. `MarketArgv` commit 에 max_items None 이면 ValueError.

---

## Shared Patterns

### 빈 값 ≠ 전량
**Source:** `jobs.py:802-803` · `argv.py:341-342, 361-362` · `detail_batch.py:698-701`
**Apply to:** `MarketArgv` (max_items·targets), `_build_argv` market 분기, CLI `--commit` 의 `--max-items`, `DetailArgv.backup_out`(submit)
```python
        if targets_path is None:
            raise ValueError("상세 잡에는 inputs 파일이 반드시 있어야 한다 — 빈 값은 전량이 아니다")
```

### 부모 잡 id 하나만 받는다 (L-02)
**Source:** `routes/jobs.py:232-250` 요청 모델 · `1221-1233` 부모 3단 검사 · `jobs._override_targets` 518-
**Apply to:** preview / commit / poll 세 라우트 전부. 게이트 강제(max_items)는 서버가 결정.

### 예외 → 상태코드 번역
**Source:** `routes/jobs.py:_상세잡만들기` 1182-1202 (AccountMismatchError 를 ValueError 보다 먼저)
**Apply to:** market 라우트 3개.

### taskId 선저장 · 재접수 금지 · 미확정 ≠ 실패
**Source:** `detail_batch.py:591-594, 551-558, 679` · `category_gate.py:876-906`
**Apply to:** `market_update.py` commit/poll. exit 3 은 `POLL_INCOMPLETE_OK_KINDS` 로 done.

### 산출물은 읽기만 · 도는 중이면 안 읽는다 · 체크포인트가 정본
**Source:** `routes/jobs.py:_산출물` 270-291 · `_상세결과ctx` 404-477
**Apply to:** `_마켓미리보기ctx`·`_마켓결과ctx`. 백업 JSON 은 **경로·존재만**.

### 원자적 JSON 쓰기
**Source:** `detail_batch.save_json` 63-70 · `jobs._write_detail_inputs` 560-571
**Apply to:** CLI 체크포인트·preview·summary·ⓑ 백업, 웹앱 targets 파일. (ⓐ 원본 백업만 예외 — O_EXCL `"x"` 로 불덮음.)

### 사람 기록은 DDL 없는 별도 모듈
**Source:** `banner_store.py` 전체 + `jobs.DDL` 190-205
**Apply to:** `market_gate_store.py`.

### 설정은 호출부에서 읽어 넘긴다 (T-1-12)
**Source:** `jobs.py:811-827` · `settings.py:95-103`
**Apply to:** `MarketArgv` 필드, 게이트 후 상한.

### 한국어 주석 + 결정 번호 인용
모든 가드·분기 위에 "왜" 를 L-xx/D-xx/Pitfall N 과 실측 숫자로 — 기존 파일 전부의 관례이자 가드 삭제 방지 장치.

## No Analog Found

| 자리 | 역할 | 이유 | 대신 쓸 것 |
|---|---|---|---|
| upload_tasks **30건 창 + 워터마크 대체 매칭** (`market_update.py` 내부) | CLI polling | 기존 `verify_tasks` 는 `taskIds` 필터가 먹는다고 가정했다(실측상 무시됨) | RESEARCH Pattern 2 (303-318) + Q2 매칭 전략 1~5. `verify_tasks` 는 종결 판정 모양만 빌린다 |

**기존 패턴을 넓혀야 하는 곳:**

| 자리 | 문제 | 제안 |
|---|---|---|
| `jobs._build_argv` 시그니처 · `create_job` 인자 | `max_items`·market 폴더·ⓐ 폴더를 모른다 | `max_credits`/`detail_dir` 처럼 kwarg 추가, 1029-1032 호출부 갱신 |
| `detail_batch._접수와폴링` | 계정 닉이 `시도()` 까지 안 내려온다 | `_입력모드` 711 의 `계정` 을 인자로 전달 |
| `_상세폴더` 체인 | market_preview 부모가 두 kind(submit/poll) 중 하나 | `_마켓부모` 값을 집합으로 |

## Metadata

**Analog search scope:** `.claude/skills/bulsaja-detail-page/scripts/` (detail_batch · ss_index_calls), `.claude/skills/bulsaja-category-fix/scripts/category_gate.py`, `.claude/skills/bulsaja-detail-remix/scripts/bulsaja_client.py`, `webapp/` (argv · jobs · banner_store · settings · routes/jobs · routes/banner · templates/_detail_result_table · _job_status · static/board.js · tests/test_detail_cli · test_jobs · test_routes_jobs · fixtures)
**Files scanned:** 18
**Pattern extraction date:** 2026-09-26
