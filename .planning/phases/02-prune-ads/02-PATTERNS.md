# Phase 2: 되돌릴 수 없는 쓰기 — 꺼진 소재 정리 - Pattern Map

**Mapped:** 2026-10-01
**Files analyzed:** 26 (신규 8 · 수정 18)
**Analogs found:** 25 / 26 (`webapp/audit.py` 만 부분 일치)

> 원칙: 이 페이즈의 새 코드는 **접착부**(파일명·트랜잭션·테스트 격리)다. 삭제 로직은 `prune.py` 에 이미 있다 — 아래 analog 는 "같은 접착을 이미 한 곳" 을 가리킨다.
> 주 analog 두 트랙: **Phase 7 쿠팡**(`routes/coupang.py` · `coupang.js` · `_coupang_*_table.html` · `test_routes_coupang.py`) = 웹 트랙 통째 복제 틀, **Phase 1 입찰가**(`run_ads.cmd_bids` · `jobs._build_argv` bids 분기 · `test_cli_patch.py`) = CLI 주입구 틀.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `.claude/skills/naver-ads-weekly/scripts/prune.py` (수정) | service (CLI 로직) | batch / 파괴적 쓰기 | 자기 자신 + `run_ads.cmd_bids` 의 `only_ads` 관례 | exact (self-extend) |
| `.claude/skills/naver-ads-weekly/scripts/run_ads.py` (수정) | controller (CLI 진입) | request-response(argv→파일) | `run_ads.py` `cmd_bids` L198-238 | exact |
| `.claude/skills/naver-ads-weekly/scripts/ads_rules.py` (수정) | utility (순수 판정) | transform | `ads_rules.classify` L60-123 (⑤ 행 `dict(row, purCnt=…)` 보강 L98) | exact |
| `.claude/skills/naver-ads-weekly/scripts/test_prune.py` (확장) | test | — | 같은 파일 `TestRunPruneCommitRechecks` L171-255 | exact |
| `.claude/skills/naver-ads-weekly/scripts/test_ads_rules.py` (확장) | test | — | 같은 파일 헬퍼 `ad()`·`stat()` L14-25 | exact |
| `webapp/jobs.py` (수정·공유) | service (잡 엔진) | event-driven(subprocess) | 같은 파일 coupang_commit / bids_commit 분기 | exact |
| `webapp/argv.py` (수정·공유) | utility (argv 조립) | transform | `AdsArgv` L105-152 | exact |
| `webapp/audit.py` (신규) | utility | file-I/O append-only | `prune.delete_ads` 진행파일 append L96-110 · `jobs._write_json_atomic` L788-794 | partial |
| `webapp/settings.py` (수정) | config | — | `DEFAULTS` Phase 7 블록 L111-116 | exact |
| `webapp/flow.py` (수정) | utility | transform | `중단사유` L329-333 · `aborted_accounts` L336-348 | exact |
| `webapp/main.py` (수정·공유) | config (조립) | — | `lifespan` L44-64 · `include_router` L89-97 | exact |
| `webapp/board.py` (수정) | utility (보드 투영) | transform | `fold_products` L108-180 | exact |
| `webapp/routes/prune.py` (신규·트랙) | controller | request-response | `webapp/routes/coupang.py` 전체 | exact |
| `webapp/routes/board.py` (수정) | controller | request-response + file append | GET `/` L354-360 (`join.attach`) · POST `routes/banner.py` `post_label` L329-345 | role-match |
| `webapp/routes/jobs.py` (수정·공유) | controller | request-response | `get_job_result` L2129-2132 트랙 병합 | exact |
| `webapp/templates/_prune_preview_table.html` (신규) | component | — | `_coupang_preview_table.html` | exact |
| `webapp/templates/_prune_result_table.html` (신규) | component | — | `_coupang_result_table.html` (+ `_result_table.html` 중단사유) | exact |
| `webapp/templates/board.html` (수정·공유) | component | — | `<section id="coupang">` L303-316 · script L651-653 | exact |
| `webapp/static/prune.js` (신규·트랙) | component (JS) | request-response | `webapp/static/coupang.js` 전체 | exact |
| `webapp/static/board.js` (수정·공유) | component (JS) | — | `columns` L180-231 · `window.관제탑` L1071-1083 | exact |
| `webapp/tests/test_prune_cli.py` (신규) | test | subprocess dry-run + in-process | `webapp/tests/test_cli_patch.py` L183-266 / L44-73 | exact |
| `webapp/tests/test_routes_prune.py` (신규) | test | — | `webapp/tests/test_routes_coupang.py` | exact |
| `webapp/tests/test_audit.py` (신규) | test | — | `test_jobs.py` `잡판` 픽스처 L73-83 | role-match |
| `webapp/tests/test_jobs.py` (확장) | test | — | `test_고아_잡은_orphaned_로_남는다` L443-457 · `test_phase7_수면방지` L1727-1730 | exact |
| `webapp/tests/test_board.py` (확장) | test | — | 기존 `test_board.py` | exact |
| `webapp/tests/conftest.py` (수정) | test config | — | `tmp_run_dir` L120-141 · `test_routes_jobs.화면` L29-41 | role-match |

---

## Pattern Assignments

### `.claude/skills/naver-ads-weekly/scripts/prune.py` (service, 파괴적 batch)

**Analog:** 자기 자신. 기존 시그니처에 **키워드 인자만** 추가(기본값 = 기존 동작). `revived_filter` 반환형·`delete_ads` 반환형(`dict(stat)`)은 바꾸지 않는다 — 기존 테스트가 `out.get("revived")`, `stat.get("ok")` 를 본다.

**현재 시그니처 (확장 지점)**:
- `backup_paused(acct, ads, out_dir)` L46 → `tag=None` 추가. 파일명 L63:
```python
path = out_dir / f"paused_{alias}_{date.today().isoformat()}.json"
```
  → tag 있으면 `paused_{alias}_{날짜}_{tag}.json` (Pitfall 1). 무플래그 이름 불변.
- `delete_ads(acct, ad_ids, progress_path, log=print)` L75 → `items=None` 리스트 인자. 결과 기록 지점 L101-113:
```python
if st in (200, 204, 404):
    stat["ok" if st != 404 else "already"] += 1
    fp.write(json.dumps({"nccAdId": aid, "status": st}) + "\n")
    break
if st in (429, 500, 502, 503, 0):
    time.sleep(2 * (attempt + 1))
    continue
stat[f"err{st}"] += 1
...
else:
    stat["retry_exhausted"] += 1
```
  각 분기에서 `items.append({"adId","status","결과":"성공|이미없음|실패|재시도소진","err"})`. 진행 파일 재개(L77-92 — 200/204/404 만 done)는 건드리지 않는다.
- `run_prune(acct, run_dir, commit=False, log=print)` L121 → `only_ads=None, tag=None, collect_items=False`. 삽입 지점: `tgt = deletable(ads)` L132 바로 뒤에 `only_ads` 교집합; 백업 호출 L142-143; 재조회 L164-176 뒤 `excluded_reasons()` + `new_since_preview` 계산.

**백업 실패 → 계정 0건 (SAFE-04 이미 있음)** L143-147:
```python
bk = backup_paused(acct, ads, backup_root)
if bk is None:
    return {"paused": len(off), "deletable": len(tgt), "reasons": dict(reasons),
            "aborted": "backup_failed"}
```

**재조회 빈 결과 → recheck_failed** L170-173 (그대로 둔다 — 웹 `중단사유` 에 라벨만 추가).

**새 순수 함수** `excluded_reasons(target_ads, fresh_ads)` — `revived_filter` L33-43 옆에 둔다(RESEARCH Pattern 1 코드 그대로). 사유 문구 "재조회에_없음" 은 "이미 삭제됐거나 조회 실패" 로 단정하지 않는다(Pitfall 6).

**`--max-items` 초과 = exit 2, 백업 전 중단** — 자르지 않고 전량 거부.

---

### `.claude/skills/naver-ads-weekly/scripts/run_ads.py` (CLI controller)

**Analog:** `cmd_bids` L198-238 — 쌍둥이로 만든다.

**대상 파일 읽기 + 폴백 금지** (L204-208 그대로 복제):
```python
try:
    only = _load_only_ads(args.only_ads)
except Exception as e:
    print(f"--only-ads 읽기 실패 — 전량 실행으로 폴백하지 않는다: {type(e).__name__}: {e}")
    return 1
```
`_load_only_ads` L165-174 는 `{"adIds":[...]}` 모양을 이미 받는다 → 미리보기 산출물에 최상위 `adIds` 를 두면 **그 파일 자체**가 커밋의 `--only-ads` 다.

**반환값 수집 + 원자적 덤프** (L210-212, L238):
```python
outputs = {}
...
outputs[alias] = bids.run_bids(acct, run_dir, ..., commit=args.commit, only_ads=only)
return _dump_preview(args.preview_out, outputs)
```
`_dump_preview` L177-195 를 재사용(tmp→os.replace, `ensure_ascii=False`, 쓰기 실패 1). prune 산출물은 최상위에 `generated/mode/limit/total/adIds/accounts` 를 둬야 하므로 `outputs` 를 그 모양으로 감싸 넘긴다.

**현재 cmd_prune — 반환값을 버린다** L241-260 (`prune.run_prune(acct, run_dir, commit=args.commit)` L259). 계정 순회·"자격증명 없음"/"prep 없음" 문구 L250-258 은 유지.

**서브파서** — bids L273-280 을 본떠 prune L282-285 에 추가:
```python
s.add_argument("--only-ads", help="대상 adId 목록 JSON 파일 — 이 목록에 있는 소재만 처리한다")
s.add_argument("--preview-out", help="계정별 계획/결과를 이 JSON 파일에 쓴다")
```
+ `--max-items`(int), `--backup-tag`(str). 무플래그 경로 종료코드 0 불변.

---

### `.claude/skills/naver-ads-weekly/scripts/ads_rules.py` (utility, transform)

**Analog:** `classify` 안 ⑤ 행 보강 L97-98 — `ad_info` 를 바꾸지 않고 행 단위로 `dict(...)` 확장:
```python
if pur:
    r5.append(dict(row, purCnt=pur["cnt"], purAmt=pur["amt"]))
```
⑥ 행 L121 을 같은 방식으로:
```python
"⑥삭제대상": [info_of(a) for a in off],
```
→ `dict(info_of(a), statusReason=a.get("statusReason"), editTm=a.get("editTm"), productLive=…)`. `productLive` 는 `live` L73 에서 같은 `mallProductId` 집합으로 계산(순수 함수). `ad_info` L34-46 은 손대지 않는다(①~⑤ 행 비대화 방지).

**BOARD-05 고정 대상**: ②~⑤ 루프가 `for a in live:` L83 — 테스트로 고정만.

---

### `.claude/skills/naver-ads-weekly/scripts/test_prune.py` (test 확장)

**Analog:** `TestRunPruneCommitRechecks` L171-221. setUp/tearDown 으로 `nvad.call`·`time.sleep` 원복, `collect.fetch_ads` 는 try/finally 원복:
```python
def setUp(self):
    self._orig_call = prune.nvad.call
    self._orig_sleep = prune.time.sleep
    prune.time.sleep = lambda *_: None
...
orig_fetch = prune.collect.fetch_ads
prune.collect.fetch_ads = lambda acct: (fresh_ads, {})
deleted_ids = []
def fake_call(acct, method, path, params=None, body=None):
    if method == "DELETE":
        deleted_ids.append(path.rsplit("/", 1)[-1])
        return 204, None
    return 200, {}
prune.nvad.call = fake_call
try:
    out = prune.run_prune({"alias": "cy728"}, run_dir, commit=True)
finally:
    prune.collect.fetch_ads = orig_fetch
```
- 회차 구조: `Path(t) / "runs" / "2026-08-30" / "accounts" / alias` (L190-192) — 백업 루트가 `run_dir.parent.parent / "paused-backup"` 라 2단 구조 필수.
- 헬퍼 `ad(ad_id, enable, reason, ...)` L19-24 재사용.
- `--commit` 리터럴 금지 — `commit=True` 키워드로만.
- 추가 케이스: only_ads 밖 DELETE 0회 · `new_since_preview` · 백업 태그로 같은 날 두 백업 공존 · items 결과 분류 · excluded_reasons 3종.

---

### `.claude/skills/naver-ads-weekly/scripts/test_ads_rules.py` (test 확장)

**Analog:** 헬퍼 L14-25 (`ad()` 에 `statusReason` 인자만 추가하거나 dict 에 덮어씀), `unittest.TestCase` 클래스 스타일(`TestLiveAds` L28-31). 추가: 꺼진 소재에 30일 통계(clk≥20·imp≥100·구매)가 있어도 ②③④⑤ 미포함 · ⑥ 행에 statusReason/editTm/productLive.

---

### `webapp/jobs.py` (service, 공유 — 한 플랜에 몰아라)

**① kind 등록 — 둘을 같이** (L66-83 주석 경고):
```python
JobKind = Literal["prep", ..., "thumb_estimate", "coupang_preview", "coupang_commit"]
KINDS: tuple[str, ...] = ("prep", ..., "thumb_estimate", "coupang_preview", "coupang_commit")
```
→ 둘 다 `"prune_preview", "prune_commit"` 추가.

**② WRITE_KINDS** L92-95 에 `"prune_commit"` (주석 블록 L96-114 처럼 "왜 넣나/왜 preview 는 안 넣나" 를 남긴다). **SINGLETON_KINDS** L155-157 에 `"prune_preview"` (사유 주석 L158-163 형식). `BULSAJA_KINDS` 에는 **넣지 않는다**(광고 API — 불사자 MCP 0회).

**③ caffeinate** L850-852 튜플에 `"prune_commit"` 추가:
```python
if kind not in ("bulsaja_index", "banner_scan", "detail_submit", "detail_poll",
                "market_commit", "market_poll",
                "thumb_estimate", "coupang_preview", "coupang_commit"):
    return []
```

**④ `_build_argv` prune 분기** — bids_commit L881-884 + "빈 값은 전량이 아니다" ValueError 관례 L897-899:
```python
if kind == "bids_commit":
    return argv_mod.AdsArgv(subcommand="bids", run_dir=run_dir, accounts=accounts,
                            commit=True, only_ads=targets_path,
                            preview_out=result_path).build()
...
if kind == "revert_only" and targets_path is None:
    raise ValueError("revert_only 에는 대상 파일이 반드시 있어야 한다 — ...")
```
→ `prune_commit` 인데 `targets_path is None` 또는 `prune_max_items is None` 이면 ValueError. `prefix=_수면방지_프리픽스(kind)` 전달. 시그니처 L861-871 에 `prune_max_items: int | None = None`, `backup_tag` 키워드 추가.

**⑤ create_job kind 전용 인자 검사** L1178-1184 — `max_items` 는 마켓 전용이라 **새 이름**:
```python
if max_items is not None and kind != "market_commit":
    raise ValueError("max_items 는 마켓 반영 전용이다")
...
if (coupang_approved is not None or copy_limit is not None) and kind != "coupang_commit":
    raise ValueError("coupang_approved · copy_limit 은 쿠팡 복사 전용이다")
```
→ `prune_max_items`·`prune_retry`(멱등 예외 표시) 를 같은 모양으로 추가.

**⑥ 부모 검사는 트랜잭션 안** — coupang_commit L1370-1383 복제:
```python
부모 = cx.execute("SELECT kind, status, exit_code FROM jobs WHERE id = ?",
                  (parent_job_id,)).fetchone()
if (부모 is None or 부모["kind"] != "coupang_preview"
        or 부모["status"] != "done" or 부모["exit_code"] != 0):
    raise ValueError("쿠팡 복사의 부모는 성공(done/0)한 쿠팡 후보 뽑기여야 한다")
```
→ `prune_preview` 기준. **멱등(ENG-04)** 도 여기: `SELECT 1 FROM jobs WHERE parent_job_id=? AND kind='prune_commit' AND status='done' AND exit_code=0` → 있으면 `BusyError`(409), 재시도 표시면 건너뛰되 LIVE 자식 있으면 409. SINGLETON 가드 L1259-1270 과 같은 "트랜잭션 안" 논리.

**⑦ result_path** — BIDS L1313-1315 모양:
```python
if run_dir and kind in BIDS_KINDS:
    접두 = "preview" if kind == "bids_preview" else "result"
    result_path = _web_dir(run_dir) / f"{접두}_{job_id}.json"
```
→ `prune_preview_<id>.json` / `prune_result_<id>.json`. 커밋 targets 는 `_override_targets` L584-607(web/ 부모 검사)로 미리보기 산출물을 그대로 가리킨다. 재시도 부분집합은 `only_ads=` → `_write_targets` L570-581.

**⑧ 종료 지점 3곳 (감사 훅)**:
- `_finish` L465-469
- `_reap` orphaned 분기 L494-496
- spawn 실패 L1426-1436
**롤백 버그(Pitfall 2)**: `create_job` 이 `BEGIN IMMEDIATE` L1239 → `_reap(cx)` L1240 → 가드 raise 시 commit 없이 close(L1421-1422). `_reap` 을 별도 커밋 트랜잭션으로 먼저 분리 — 다른 조회 함수들이 이미 쓰는 모양(L1484-1488):
```python
cx = _conn()
try:
    cx.execute("BEGIN IMMEDIATE")
    _reap(cx)
    cx.commit()
    ...
finally:
    cx.close()
```

**⑨ `reap_on_startup()`** — `first_coupang_commit_done` L1553-1573 이 정확한 틀(DB 없으면 만들지 않음 + BEGIN IMMEDIATE·_reap·COMMIT + sqlite3.Error 삼킴):
```python
if not db_path().is_file():
    return False
cx = _conn()
try:
    cx.execute("BEGIN IMMEDIATE")
    _reap(cx)
    cx.commit()
    ...
except sqlite3.Error:
    return False
finally:
    cx.close()
```
반환은 정리 건수(int). `CT_SKIP_STARTUP_REAP=1` 이면 0 (Pitfall 3). PID 재사용 검사(Pitfall 4)는 이 함수 안에서만.

---

### `webapp/argv.py` (utility)

**Analog:** `AdsArgv` L105-152.
```python
subcommand: Literal["prep", "run", "apply", "bids", "accounts"]
...
if self.only_ads:
    av += ["--only-ads", str(self.only_ads)]
if self.preview_out:
    av += ["--preview-out", str(self.preview_out)]
```
→ Literal 에 `"prune"`, 필드 `max_items: int | None = None`, `backup_tag: str | None = None`, `build()` 에서 조건부로 `["--max-items", str(n)]`, `["--backup-tag", tag]`. 경로·숫자는 `str()` (L145-146 주석 — argv 컬럼 JSON 직렬화).

---

### `webapp/audit.py` (신규 utility, file-I/O append-only) — partial

**Analog 조합:**
- JSONL append: `prune.delete_ads` L96-110 (`progress_path.parent.mkdir(...)`, `open("a")`, `json.dumps(..., ensure_ascii=False) + "\n"`)
- 경로 해석: `settings.reload()` L180-181 의 환경변수 우선 관례 → `CT_AUDIT_PATH` 오버라이드
```python
JOB_LOG_DIR = str(os.environ.get("CT_JOB_LOG_DIR") or cfg("job_log_dir", DEFAULTS["job_log_dir"]))
DB_PATH = str(os.environ.get("CT_DB_PATH") or cfg("db_path", DEFAULTS["db_path"]))
```
- 데이터루트: `paths.data_root()` (webapp/paths.py L50) → `<데이터루트>/control-tower/audit.jsonl`
- kind 별 요약 추출: `prune_commit` → 산출물 items 집계, `bids_commit` → `flow.result_counts`(flow.py L303), 나머지 성공/실패 `null`(0 으로 지어내지 않음 — `_count_targets` L610-623 의 "못 셌으면 None" 규율). 추출 실패는 `{"요약오류": type(e).__name__}`.

---

### `webapp/settings.py` (config)

**Analog:** Phase 7 블록 L111-116:
```python
# ── Phase 7 (썸네일 · 쿠팡) 에서 더한 키 ──────────────────────────────
# 같은 규율 — 읽기는 settings.cfg("키", settings.DEFAULTS["키"]) 로만.
"thumb_max_items": 20,
"coupang_copy_max_items": 20,
"coupang_first_max_items": 10,
```
→ `# ── Phase 2 (꺼진 소재 정리) ──` 블록: `"prune_max_items": 8000,` (D-07 `[용팀장 확인 필요]` 주석), `"audit_path": ""`(빈 문자열 = 데이터루트 기본). 모듈 상수로 올리지 않는다(L27-30).

---

### `webapp/flow.py` (utility)

**Analog:** L327-333 — 사유 dict 에 키만 추가:
```python
중단사유 = {
    "backup_unreadable": "...",
    "backup_failed": "백업을 못 써서 중단했다 — 되돌릴 수단 없이 광고비를 건드리지 않는다",
}
```
→ `"recheck_failed": "재확인 조회가 0건/실패 — 인증 만료·방화벽 가능성. 이 계정은 지우지 않았다"`. `backup_failed` 문구가 "광고비" 를 말하므로 prune 결과표에서는 별도 문구가 필요하면 결과표 ctx 에서 덮는다(flow 문구는 bids 공용). `aborted_accounts` L336-348 은 `_계정들(result)` 로 읽으므로 prune 산출물의 `accounts` 모양과 맞는지 확인할 것(L248 `_계정들`).

---

### `webapp/main.py` (조립, 공유)

**lifespan** L44-64 — 기존 print 옆, `yield` 앞:
```python
print(f"→ http://127.0.0.1:{settings.PORT}/?t={security.BOOT_TOKEN}", flush=True)
yield
```
→ 그 앞에 RESEARCH "lifespan 기동 reap" try/except 블록(`flush=True` 필수, L48-54 주석 사유). `from webapp import jobs` import 추가.

**라우터** L89-97:
```python
from webapp.routes import banner, board, coupang, health, jobs, thumb  # noqa: E402
...
# Phase 7 트랙 라우터 — 트랙 플랜(07-04 · 07-05)이 공유 파일을 안 건드리고 붙는 자리다(D-19).
app.include_router(thumb.router)
app.include_router(coupang.router)
```
→ `prune` import + `app.include_router(prune.router)`.

---

### `webapp/board.py` (utility, transform)

**Analog:** `fold_products` L108-180. 상품 dict 초기값 L135-145 에 필드 추가 후 ⑥ 행에서 집계(지표 합산 루프 L166-169 와 같은 `.get()` 전용 규율):
```python
if "①" in slot["rules"]:
    p["rule1_ads"].append(adId)
```
→ `if "⑥" in slot["rules"]:` 에서 `statusReason` 카운트(연동끊김/검수중/거부) + `productLive` 수집. 배지 `광고정지` = ⑥ 소재가 있고 그 행들이 전부 `productLive is False`; **필드가 없으면(옛 result.json) 배지 None** — 추정 금지. 모듈 독스트링 L5-8: 원본 덤프 파일명을 이 모듈에 적지 않는다(grep 가드).

---

### `webapp/routes/prune.py` (신규 controller, 트랙 소유)

**Analog:** `webapp/routes/coupang.py` 전체 (299줄).

**Imports** (L22-30):
```python
import json
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from webapp import jobs, settings
from webapp.routes.jobs import JobId, _경과초, _미리보기유효시간, _상세잡만들기, _투영
```
(prune 은 `flow` 도 import — `aborted_accounts`.)

**요청 모델** (L52-62):
```python
class CoupangCommitReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preview_job_id: JobId
    typed_count: StrictInt = Field(ge=0)
```
→ `PruneCommitReq` 동일, `PruneRetryReq{commit_job_id: JobId, typed_count}`, `PrunePreviewReq{run_dir: str, accounts: list[Alias] = []}` (`Alias` 는 `webapp.argv`).

**상한 한 곳** (L67-80 `_쿠팡복사상한`):
```python
try:
    n = int(settings.cfg(키, settings.DEFAULTS[키]))
except (TypeError, ValueError):
    n = int(settings.DEFAULTS[키])
return max(1, n)
```
→ `_삭제상한()` = `prune_max_items`.

**커밋 라우트 6단계** (L139-186) — 그대로 복제, 차이 하나: 성공 자식 있으면 **409**(쿠팡은 400, L167-168):
```python
부모 = jobs.job_status(req.preview_job_id)
if 부모 is None or 부모.get("kind") != "coupang_preview":
    raise HTTPException(status_code=400, detail="...")
if 부모.get("status") in jobs.LIVE_STATUSES:
    raise HTTPException(status_code=409, detail="...")
if 부모.get("status") != "done" or 부모.get("exit_code") != 0:
    raise HTTPException(status_code=400, detail=...)
경과 = _경과초(부모.get("started_at"))
if 경과 is None or 경과 > _미리보기유효시간:
    raise HTTPException(status_code=400, detail="미리보기가 24시간을 넘었다 — 새 미리보기부터 해라")
자식들 = jobs.children_of(req.preview_job_id, "coupang_commit")
if any(c.get("status") in jobs.LIVE_STATUSES for c in 자식들):
    raise HTTPException(status_code=409, ...)
if _성공복사(자식들):
    raise HTTPException(status_code=400, detail="이 미리보기로 이미 복사했다 — 새 미리보기부터")
...
if req.typed_count != len(승인):
    raise HTTPException(status_code=409, detail=(f"화면이 본 건수({req.typed_count:,})와 ..."))
결과 = _상세잡만들기("coupang_commit", parent_job_id=req.preview_job_id, ...)
```
전체 형태는 RESEARCH "커밋 라우트 뼈대" (02-RESEARCH.md L399-435). `--account` 는 대상>0 계정만 명시.

**미리보기 라우트**: `post_coupang_preview` L127-134 처럼 `_상세잡만들기("prune_preview", run_dir=…, accounts=…)` 한 줄. 추가로 같은 run_dir 의 `prep` 이 LIVE 면 409 (Pitfall 7) — `jobs.children_of` 대신 `jobs.recent_jobs`/`active_job` 로 확인.

**결과 ctx 뼈대** (`_쿠팡미리보기ctx` L208-250 · `_쿠팡결과ctx` L253-292):
```python
상태 = 상태 or {}
기본 = {"job": _투영(상태), "running": False, "error": None, ...}
if 상태.get("status") in jobs.LIVE_STATUSES:
    return {**기본, "running": True}
요약 = _미리보기요약(상태)
if 요약 is None:
    return {**기본, "error": f"... (종료코드 {상태.get('exit_code')})"}
```
미리보기 ctx 에 `이미삭제`(성공 자식) · `삭제중` · `만료` · `상한초과` 플래그(L245-249 모양).

**결과표 등록** (L295-299):
```python
결과표: dict[str, tuple[str, Callable[[dict], dict]]] = {
    "coupang_preview": ("_coupang_preview_table.html", _쿠팡미리보기ctx),
    "coupang_commit": ("_coupang_result_table.html", _쿠팡결과ctx),
}
```

---

### `webapp/routes/board.py` (controller 수정)

**GET `/` 투영에 얹기** L354-360 — `fold_products` 는 안 고치고 그 위에 얹는 층:
```python
join_doc, ctx["join_at"], ctx["index_error"] = _load_join(선택)
ctx["rows"] = join.attach(
    board.fold_products(result), result, join_doc, ...)
```
→ 그 뒤에 `misjudged.jsonl` 최신 줄을 key 별로 읽어 `row["오판정"]` 주입(읽기만 — GET 에서 파일을 만들지 않는다, main.py L9-12).

**POST `/board/misjudged`** — `routes/banner.py` `post_label` L329-345 + 최신 1건이 이긴다(banner_store `라벨기록` L169-208 의 의미론을 JSONL append 로). 키 검증은 `routes/jobs.py` L205-209 `보드키`:
```python
보드키 = Annotated[str, StringConstraints(
    pattern=r"^[A-Za-z0-9_][A-Za-z0-9_-]{0,63}\|[0-9A-Za-z_]{1,40}$")]
```
모델은 `ConfigDict(extra="forbid")` + memo 길이 상한. 회차는 `paths.run_dir_path` 화이트리스트, key 존재는 `board.fold_products(result)` 로 확인(없으면 400). guard 미들웨어가 Origin/토큰을 이미 본다(banner.py L321-324 주석).

---

### `webapp/routes/jobs.py` (공유 — 한 줄)

**트랙 병합** L2129-2132:
```python
from webapp.routes import coupang as _쿠팡트랙, thumb as _썸네일트랙
for 트랙표 in (_썸네일트랙.결과표, _쿠팡트랙.결과표):
    for 키, 값 in 트랙표.items():
        결과표.setdefault(키, 값)
```
→ `prune as _삭제트랙` 추가, 튜플에 `_삭제트랙.결과표`. 결과표 ctx 가 `flow.aborted_accounts` 를 쓰는 모양은 `_실행표ctx` L985-1015 참조(`"aborted": flow.aborted_accounts(결과)`).

---

### `webapp/templates/_prune_preview_table.html` (component)

**Analog:** `_coupang_preview_table.html` 전체. 뼈대: `running → error → 요약 줄 → 표 → 접힌 커밋 영역`. 커밋 영역 4중 마찰 (L72-80):
```html
<details id="coupang-commit-details">
  <summary>쿠팡 복사 실행 (되돌릴 수 없음 — 펼쳐서 확인)</summary>
  ...
  <label for="coupang-typed-count">복사할 건수를 직접 입력해라 ({{ 복사예정 }})</label>
  <input type="number" id="coupang-typed-count" inputmode="numeric" min="0" step="1" autocomplete="off">
  <button type="button" class="contrast" id="coupang-commit-btn" data-preview-job="{{ job.id }}">쿠팡 복사 실행 — 되돌릴 수 없음</button>
</details>
```
분기 L64-71 (`이미복사 / 복사중 / 만료 / 복사예정`) 그대로 → `이미삭제 / 삭제중 / 만료 / 상한초과 / 삭제예정`. 문구: "꺼진 소재(연동끊김) N건 삭제", 검수중·거부는 "남김" 으로 따로. 수천 행이라 `<table>` 대신 계정별 요약 + Tabulator 마운트 자리(`<div id="prune-preview-grid">` + `<script type="application/json">` 데이터 — board.html L645 `board-rows` 관례). `| safe` 금지(main.py L39-40).

### `webapp/templates/_prune_result_table.html` (component)

**Analog:** `_coupang_result_table.html` 전체 — `빠짐` 표 L42-50 이 `excluded`(adId·사유) 표의 틀, `exit5` 경고 L17-21 자리는 `new_since_preview` "미리보기 이후 새로 꺼진 N건 — 이번엔 안 지움" 안내로 바꾼다(Pitfall 5: exit 5 는 구현하지 않음). 계정별 `aborted`(backup_failed/recheck_failed) 줄 + 실패 N 건 있으면 `실패분만 재시도` details(타이핑 = 실패 수). 정렬은 실패·제외가 위(flow.result_rows L351-359 관례).

### `webapp/templates/board.html` (공유)

**Analog:** L303-316 섹션 + L651-653 스크립트:
```html
<section id="coupang">
  <h2>쿠팡 복사</h2>
  ...
  <button type="button" id="coupang-preview-btn" disabled>쿠팡 후보 뽑기 — 쓰기 0</button>
  <div id="coupang-body"></div>
  <input type="hidden" id="coupang-preview-job" value="">
</section>
...
<script src="/static/coupang.js"></script>
```
→ `<section id="prune">` (버튼 `disabled` 로 그림 — prune.js 가 켬). 회차가 필요하므로 쿠팡과 달리 `if run_dir` 블록 **안**. `<script src="/static/prune.js">` 는 board.js 뒤.

---

### `webapp/static/prune.js` (트랙 JS)

**Analog:** `webapp/static/coupang.js` 전체. 그대로 가져올 것:
- IIFE + `var 훅 = window.관제탑; if (!훅) { return; }` (L16-20)
- `사유뽑기(res)` (L32-39) · `패널열기(job_id)` (L41-44) · starting 재시도 `기다리기` (L48-54) · `결과자리()` (L56-64)
- 위임 클릭 + 정수 검증 + 입력 비우기 (L94-127):
```js
if (!/^[0-9]+$/.test(글)) {
  훅.오류표시("복사할 건수를 숫자로 직접 입력해라 — 입력 없이는 복사하지 않는다");
  return;
}
...
if (입력) { 입력.value = ""; }   // 요청 뒤 다시 누르려면 다시 타이핑해야 한다
훅.요청("/jobs/coupang/commit", { preview_job_id: id, typed_count: 건수 })
```
- 한도: 미리보기 수 초~수십 초, 커밋 8,000건 ≈ 40분 → `(60 * 60 * 1000) / 400` (L30).
- 미리보기 요청 몸통: `{ run_dir: 훅.회차(), accounts: [...] }` (훅 `회차` L1075).
- 재시도 버튼도 같은 위임 핸들러(`/jobs/prune/retry`, `commit_job_id`).
- Tabulator 미리보기 표: board.js `columns`(L180-231) 형식으로 계정 groupBy.

### `webapp/static/board.js` (공유)

**Analog:** `columns` L180-231 (formatter 함수형), 훅 L1071-1083. 오판정 버튼 컬럼 1개(formatter 가 버튼 그림 → `훅.요청("/board/misjudged", …)` → 성공 시 `row.update({오판정: …})`), `광고정지` 배지·정지사유 표시 컬럼. 공유 파일이라 공용 계약 플랜에 몰아라.

---

### `webapp/tests/test_prune_cli.py` (신규 test)

**Analog:** `webapp/tests/test_cli_patch.py`.
- in-process import (L20-33): `SCRIPTS_DIR` sys.path 삽입은 **테스트 전용**(주석 L21-26 그대로 옮김) → `import prune`.
- 네트워크 차단 픽스처 (L62-73) — `monkeypatch.setattr(prune.nvad, "call", fake)`, `prune.time.sleep`, `prune.collect.fetch_ads`.
- subprocess dry-run (L189-205):
```python
def _격리된_데이터루트(tmp_path):
    toml = tmp_path / "workspace.toml"
    toml.write_text(f'[paths]\ndata_root = "{tmp_path}"\n', encoding="utf-8")
    env = dict(os.environ, EROOM_WORKSPACE_TOML=str(toml))
    return env, tmp_path

def _cli(env, *argv):
    return subprocess.run([str(CLI_PY), str(RUN_ADS), *argv],
                          capture_output=True, text=True, env=env, cwd=str(REPO))
```
- alias 는 `_cli(env, "accounts")` 에서 받는다(L238-240) — 테스트에도 계정 하드코딩 금지.
- `--only-ads` 깨짐 exit 1 + "폴백하지 않는다" (L207-219) · `--preview-out` 전량·한국어 보존 (L230-266) 를 prune 판으로.
- **커밋 경로는 subprocess 금지**(실자격증명으로 DELETE) — in-process 만. `--commit` 리터럴 금지(`no_commit_guard.sh`), 필요하면 `"--" + "commit"`.

### `webapp/tests/test_routes_prune.py` (신규 test)

**Analog:** `webapp/tests/test_routes_coupang.py`.
- imports L17-27: `from webapp.tests.test_routes_jobs import 기대닉, 안띄운다, 프로필, 화면  # noqa: F401`
- `_지금(시간전)` L36-37 · `_행박기(kind, …)` L60-73 · `_미리보기잡(...)` L76-96(산출물 파일 + INSERT) — prune 은 `run_dir` 컬럼에 `tmp_run_dir.name` 을 넣고 산출물은 `<run_dir>/web/prune_preview_<id>.json`.
- 픽스처 L99-103:
```python
@pytest.fixture
def 쿠팡판(tmp_run_dir, 화면, 프로필, 기대닉, 안띄운다):
    프로필()
    return 화면
```
  → prune 은 불사자 MCP 를 안 부르므로 `프로필`·`기대닉` 불필요: `삭제판(tmp_run_dir, 화면, 안띄운다)`.
- 테스트 목록 L162-253 을 1:1 로 옮긴다: 부모 이상 400 · 도는 중 409 · 24시간 400 · **성공 자식 409**(쿠팡 L190-195 는 400) · 산출물 깨짐 400 · 0건 400 · 타이핑 불일치 409 + 자식 미생성 · 쓰기잡 동시 409 · 상한 초과 400 · argv 에 `--only-ads == 미리보기 result_path` · 재시도.

### `webapp/tests/test_audit.py` (신규 test)

**Analog:** `test_jobs.py` `잡판` L73-83 (DB·로그 tmp) + 감사 경로 `monkeypatch.setenv("CT_AUDIT_PATH", tmp)`. 검증: WRITE_KINDS 종료 1줄 · orphaned 1줄 · BusyError 롤백 경로에서도 중복 0 · 실데이터루트 미생성.

### `webapp/tests/test_jobs.py` (확장)

- 고아 재현 L443-457 (`proc = jobs._PROCS.pop(job_id); proc.wait(...)`) → `reap_on_startup()` 호출 후 orphaned, DB 없으면 파일 미생성.
- caffeinate L1727-1730:
```python
def test_phase7_수면방지(monkeypatch):
    monkeypatch.setattr(jobs.os.path, "exists", lambda p: True)
    for k in 칠단계3종:
        assert jobs._수면방지_프리픽스(k) == [jobs.CAFFEINATE, "-i"]
```
  → `prune_commit` 은 붙고 `prune_preview` 는 안 붙는다.
- 롤백 버그 회귀: 끝난 쓰기 잡이 있는 상태에서 BusyError 거부 뒤에도 그 잡 `done/코드`.
- 스키마 가드 `test_스키마는_기록_테이블만_있다` (L460~) — 테이블을 늘리지 않으므로 그대로 통과해야 한다.

### `webapp/tests/conftest.py` (수정)

**Analog:** `tmp_run_dir` L120-141 (`monkeypatch.setattr(paths, "data_root", lambda: tmp_path)`), `화면` (test_routes_jobs L29-41, `settings.DB_PATH` monkeypatch). Pitfall 3: `client` 픽스처(L161-178)의 `TestClient(app)` 진입 시 lifespan 이 **화면 픽스처보다 먼저** 돈다 → **autouse** 픽스처로 `CT_SKIP_STARTUP_REAP=1`·`CT_AUDIT_PATH=<tmp>` 를 `monkeypatch.setenv` (lifespan 이전에 적용되도록 autouse + session 순서 확인).

---

## Shared Patterns

### 예외 → 상태코드 번역 (모든 POST)
**Source:** `webapp/routes/jobs.py` `_상세잡만들기` L1708-1728
**Apply to:** `routes/prune.py` 의 preview/commit/retry
```python
try:
    job_id = jobs.create_job(kind, **kw)
except jobs.AccountMismatchError as e:
    raise HTTPException(status_code=409, detail=str(e))
except jobs.BusyError as e:
    raise HTTPException(status_code=409,
                        detail=f"이미 도는 쓰기 작업이 있다 — 끝나고 다시 눌러라 ({e})")
except ValueError as e:
    raise HTTPException(status_code=400, detail=str(e))
...
except RuntimeError as e:
    raise HTTPException(status_code=500, detail=str(e))
return {"job_id": job_id}
```
`AccountMismatchError` 가 `ValueError` 상속 — 순서가 동작이다(L1098-1101).

### 미리보기→커밋 "부모 3단 검사 + 24h + 타이핑"
**Source:** `webapp/routes/coupang.py` L150-186, `_미리보기유효시간`·`_경과초` `routes/jobs.py` L1828-1838
**Apply to:** prune commit · retry

### 원자적 JSON 쓰기
**Source:** `run_ads._dump_preview` L177-195 (CLI), `jobs._write_json_atomic` L788-794 · `jobs._write_targets` L570-581 (웹)
**Apply to:** `--preview-out`, 재시도 대상 파일. 새 헬퍼 만들지 않는다.

### "빈 값은 전량이 아니다"
**Source:** `jobs._build_argv` L897-899 · L1099-1104, `run_ads.cmd_bids` L204-208
**Apply to:** `prune_commit` argv 조립(targets·max_items 없으면 ValueError), CLI `--only-ads` 깨짐 exit 1

### 설정값 읽기
**Source:** `settings.py` L27-30 · `coupang._쿠팡복사상한` L76-80
**Apply to:** `prune_max_items`, `audit_path` — 항상 `settings.cfg("키", settings.DEFAULTS["키"])`, 숫자 리터럴 복사 금지

### 결과는 산출물에서만
**Source:** `routes/jobs._실행표ctx` 독스트링 L985-995 · `coupang._쿠팡결과ctx` L253-258
**Apply to:** prune 결과 ctx · audit 요약 (종료코드로 성공 추정 금지, 모르면 None)

### GET 은 상태를 안 바꾼다
**Source:** `webapp/main.py` L9-12 · `jobs.active_job` L1505-1510 (DB 없으면 만들지 않음)
**Apply to:** 오판정(POST 전용), GET `/` 의 misjudged 읽기, `reap_on_startup`(DB 없으면 미생성)

### 트랙 소유 / 공유 파일 경계
**Source:** `routes/coupang.py` 독스트링 L9-10, `coupang.js` 헤더 L1-15, board.html L651
**Apply to:** 트랙 파일(`routes/prune.py`·`prune.js`·`_prune_*.html`)은 `window.관제탑` 훅·`routes/jobs` 도우미 import 만. 공유 파일(`jobs.py`·`argv.py`·`main.py`·`routes/jobs.py`·`board.html`·`board.js`·`conftest.py`)은 한 플랜에 몰아 고친다(07-01 방식).

### 한국어 주석 · try-except · `flush=True`
**Source:** 전 파일 관례, `main.lifespan` L48-54
**Apply to:** 기동 reap print, CLI 진행 로그

---

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `webapp/audit.py` | utility | append-only JSONL (여러 kind 요약) | 웹앱에 JSONL 감사 기록기가 아직 없다. append 는 `prune.delete_ads` 진행파일, 경로 오버라이드는 `settings.reload` env 관례, 요약 추출은 `flow.result_counts` 를 조합한다 — RESEARCH Pattern 5 를 설계 정본으로 쓴다 |

(부분 해당) `jobs.reap_on_startup` 의 PID 재사용 검사(`ps -o lstart=`)는 코드베이스에 선례가 없다 — `_alive` L420 은 건드리지 말고 이 함수 안에서만.

## Metadata

**Analog search scope:** `.claude/skills/naver-ads-weekly/scripts/`, `webapp/{*.py, routes/, templates/, static/, tests/}`
**Files scanned:** 22 (정독 14 · grep 8)
**Pattern extraction date:** 2026-10-01
