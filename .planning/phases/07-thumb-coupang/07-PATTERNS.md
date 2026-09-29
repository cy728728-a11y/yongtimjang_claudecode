# Phase 7: 남은 버튼 — 썸네일 교체 / 쿠팡 복사 - Pattern Map

**Mapped:** 2026-09-29
**Files analyzed:** 24 (수정 12 · 신규 12)
**Analogs found:** 23 / 24

> 결론: **새 패턴은 러너 스크립트 2개(`thumb_web.py` · `coupang_web.py`) 하나뿐이다.** 나머지는 Phase 5 detail
> (견적→접수) · Phase 6 market (미리보기→반영, extra=forbid, 서버 상한) · Phase 1 되돌리기(건수 확인)를 한 벌 더 복사한다.
> 05-PATTERNS · 06-PATTERNS 에 이미 있는 발췌는 다시 적지 않고 **줄 번호만** 가리킨다(아래 줄 번호는 2026-09-29 현재 파일 기준 재확인).
>
> ⚠️ Phase 6 이후 줄 번호가 밀렸다. 06-PATTERNS 의 jobs.py/routes 줄 번호는 믿지 말고 이 문서 것을 써라.

## File Classification

| 신규/수정 파일 | 역할 | 데이터 흐름 | 가장 가까운 기존 코드 | 일치도 |
|---|---|---|---|---|
| `.claude/skills/bulsaja-thumbnail/scripts/run_thumbs.py` (수정: `prep --estimate-out/--only-pending/--expect-nick`, `apply --max-credits`, `apply --commit --summary-out`) | CLI | batch + file-I/O | 같은 파일 `cmd_prep` 292-535 · `_guard_credits` 1299-1324 · `cmd_apply` generate 블록 1401-1411 · argparse 2375-2500 · `detail_batch._계정확인` 323-334 | exact |
| `.claude/skills/coupang-candidates/scripts/run_coupang.py` (수정: 공통 `--expect-nick` · `apply --pids-file` · gate fail-closed D-17) | CLI | batch + request-response (MCP) | 같은 파일 `CoupangMCP` 97-135 · `cmd_gate` 334-436 · `cmd_apply` 441-516 · `main.common` 800-803 | exact |
| `.claude/skills/bulsaja-thumbnail/scripts/thumb_web.py` (신규 러너) | CLI 러너 | batch (자식 subprocess 순회) | RESEARCH Pattern 1 골격 + `run_thumbs.py` 머리 45-65(경로·line_buffering) | partial (새 패턴) |
| `.claude/skills/coupang-candidates/scripts/coupang_web.py` (신규 러너: preview 체인 / commit 재조회→apply→verify) | CLI 러너 | batch (단계 체인) | RESEARCH Pattern 1 골격 + `run_coupang.py` 머리 20-50 · `_dump` 68-74 | partial (새 패턴) |
| `.claude/skills/bulsaja-thumbnail/scripts/test_thumb_web.py` (신규) | test | 오프라인 몽키패치 | `test_thumb_prep.py` 1-80 (matrix/snapshot 교체 관용구, unittest) | exact |
| `.claude/skills/coupang-candidates/scripts/test_coupang_web.py` (신규 + 골든) | test | 오프라인 가짜 MCP | `webapp/tests/test_detail_cli.py` 36-147 (로더·가짜MCP·주입·실행) + 골든 252- · `test_coupang_rules.py` 1-10 (import 방식) | role-match |
| 골든 픽스처 (`gate` 무플래그 candidates.json · `prep` 무플래그) | fixture | — | `webapp/tests/fixtures/detail_golden_noflag.json` + `test_detail_cli.py:19-24,252-` 쓰기 규율 | exact |
| `webapp/jobs.py` (kind 3종 · 가드 집합 · 수면방지 · `_build_argv` 분기 · `create_job` 분기 · 쿠팡/썸네일 폴더 유도 · `first_coupang_commit_done()` · `_alive` 좀비) | service (잡 엔진) | event-driven (subprocess) | 같은 파일 market 등록 전부: 68-80, 89-114, 144-146, 406-416, 424-425, 655-720, 741-760, 942-973, 1026-1035, 1177-1184, 1315-1347, 1365-1385 | exact |
| `webapp/argv.py` (`THUMB_WEB`·`COUPANG_WEB` 상수, `ThumbArgv`·`CoupangArgv`) | config/argv 모델 | transform | `MARKET_UPDATE` 64-67 · `MarketArgv` 381-435 · `Nick`/`PlainArg` 83-94 | exact |
| `webapp/settings.py` (Phase 7 블록) | config | — | `DEFAULTS` Phase 6 블록 104-109 | exact |
| `webapp/paths.py` (`thumb_runs_root()` · `coupang_runs_root()`) | utility | — | `ads_root()` 65-66 · `runs_root()` 69 | exact |
| `webapp/routes/jobs.py` — `/jobs/thumb/estimate` | controller | request-response | `DetailEstimateReq` 218-235 · `post_detail_estimate` 1516-1637 | exact |
| `webapp/routes/jobs.py` — `/jobs/thumb/approve` (잡 아님, 파일 쓰기) | controller | request-response (파일 쓰기) | `post_market_gate` 1921- (+ `_게이트요청` 1911) · `routes/banner.py post_confirm` | role-match |
| `webapp/routes/jobs.py` — `/jobs/coupang/preview` | controller | request-response | `post_bulsaja_scan` 1345 (`JobReq` 무대상) · `_상세잡만들기` 1640-1660 | exact |
| `webapp/routes/jobs.py` — `/jobs/coupang/commit` (잡id + 타이핑 건수) | controller | request-response | `MarketCommitReq` 276-285 · `post_market_commit` 1808-1876 · `RevertRoundReq` 195-205 · `post_revert_round` 1245-1290 · `_마켓반영상한` 596-616 | exact |
| `webapp/routes/jobs.py` — ctx 4개 + `get_job_result` 분기 | controller | 표시 (읽기) | `_산출물` 335-356 · `_상세견적ctx` 376-407 · `get_job_result` 2014-2053 | exact |
| `webapp/templates/_thumb_estimate_table.html` (신규) | template | 표시 | `_detail_estimate_table.html` (92줄) | exact |
| `webapp/templates/_thumb_result_table.html` (신규) | template | 표시 | `_detail_result_table.html` 1-100 | exact |
| `webapp/templates/_coupang_preview_table.html` (신규, 접힌 커밋 영역 포함) | template | 표시 + 요청 | `_market_preview_table.html` 1-84 + `board.html` 위험구역 570-605 (`<details>` + 건수 확인) | exact |
| `webapp/templates/_coupang_result_table.html` (신규) | template | 표시 | `_market_result_table.html` 1-74 | exact |
| `webapp/templates/board.html` (썸네일 견적 버튼 · 쿠팡 상단 패널) | template | request-response | 상세 견적 버튼 515-528 · `#detail-estimate` 349-356 · 위험구역 570-605 | exact |
| `webapp/static/board.js` (배선) | component (JS) | request-response | `상세견적버튼` 659-700 · `상세작업접수` 729-760 · 위임 804-820 · 되돌리기 건수확인 1005- | exact |
| `webapp/templates/_job_status.html` (kind 이름·종료코드 문구) | template | 표시 | 같은 파일 15-30 `작업이름` · 73 running 문구 · 98-106 종료코드 계약 | exact |
| `webapp/tests/test_jobs.py` · `test_argv.py` · `test_routes_thumb.py` · `test_routes_coupang.py` | test | unit / TestClient | `test_jobs.py` 1521-1666 market 묶음 · `test_routes_market.py` 34-365 · `test_argv.py` 162-247 트리 가드 | exact |
| `workspace.toml [coupang] min_margin = 20.0` (1줄) | config | — | `workspace.toml` 43-49 | exact (값만) |
| **D-08 썸네일 → market_preview 부모 출처** | — | — | **이 페이즈에서 안 만든다** (RESEARCH §D-08) | 미룸 |

---

## Pattern Assignments

### `run_thumbs.py` — 주입구 5개 (CLI, 무플래그 불변)

**규율:** 새 분기는 전부 `if getattr(args, "<flag>", None):` 안. 골든을 **CLI 한 줄 고치기 전** 커밋에서 만든다.

**인자 자리** — `main()` prep 서브파서 2383-2393, apply 2436-2449:
```python
    p = sub.add_parser("prep")
    _common(p)
    p.add_argument("--run-dir", required=True)
    p.add_argument("--ids", nargs="+", default=None)
    ...
    p.set_defaults(func=cmd_prep)
```
→ prep 에 `--estimate-out`(default None) · `--only-pending`(store_true) · `--expect-nick`(default ""); apply 에 `--max-credits`(type=int, default=None) · `--summary-out`(default None).

**`--only-pending` 주입점** — `cmd_prep` 298-303:
```python
    m = matrix.read(sheet)
    if args.ids:
        pids = [i for i in args.ids if i.strip()]
    else:
        pids = matrix.pending(m, TASK)
```
→ `if args.ids and args.only_pending:` 에서 `pids ∩ matrix.pending(m, TASK)` 로 좁히고 빠진 건 `{pid: 현황판값}` 을 estimate-out `현황판제외` 에 싣는다.

**estimate-out 재료** — 4갈래 분기 322-338 (`already` / `targets` / `audit_needed`) + `recs, errors = snapshot.ensure(...)` 316-318 + 404 삭제대상. 산출은 `_dump`(175) 로 원자 쓰기. 0건 조기 반환(309-314)·조회실패 경로에서도 **estimate-out 은 써야** 러너가 "고장 vs 0건" 을 구분한다(Pitfall 3). 크레딧은 `R.credit_estimate(K)` · 최대 `R.credit_estimate(K) * R.MAX_REGEN`.

**`--expect-nick` (prep)** — `cmd_prep` 맨 앞(293 `run_dir = ...` 바로 뒤, 시트 읽기 전). 모양은 `detail_batch._계정확인` 323-334:
```python
    try:
        p = _표시규칙제거(mcp.call_tool("bulsaja_my_profile", {}) or {})
        닉 = str(p.get("닉네임") or "")
    except Exception as e:
        print(f"[경고] 계정 조회 실패: {str(e)[:120]}", flush=True)
        return None, None, 기대닉 is None
    return 닉, 크레딧, (기대닉 is None or 닉 == str(기대닉))
```
→ 연결은 `ThumbMCP()`(191, `snapshot.ProductMCP` 상속) open/close — `_guard_credits` 1309-1315 의 open/try/finally close 모양 그대로. 불일치 `sys.exit(4)` (prep 경로엔 잔액가드 4 가 없어 모호하지 않다).

**`--max-credits` 주입점** — `cmd_apply` generate 블록 1401-1411, `_guard_credits(items)` **직전**:
```python
    if args.generate:
        if has_missing and not getattr(args, "allow_missing", False):
            ...
            sys.exit(3)
        _guard_credits(items)
        _generate(sheet, run_dir, items, args)
        return
```
→ RESEARCH §D-07 코드(누적 = `generated.json` 의 `재생성횟수` 합 + 미회수 taskId) 그대로. 계획 계산은 `_generate` 1497-1498 과 **같은 호출** `R.generate_plan(items, prev, getattr(args, "ids", None))`. 초과 `sys.exit(5)` (4 는 이미 잔액부족 — 바꾸지 않는다).

**`--summary-out` (apply --commit)** — `_commit` 1634- 끝의 `###COMMIT###` 줄 직전에 `{완료:[pid], 보류:{pid:사유}}` `_dump`.

---

### `run_coupang.py` — 주입구 + D-17 fail-closed

**`--expect-nick` 한 곳 주입** — `CoupangMCP` 97 에 `open()` 오버라이드 + 모듈 전역 `_EXPECT_NICK`. 인자는 `common()` 800-803:
```python
    def common(p):
        p.add_argument("--run-dir", required=True)
        p.add_argument("--sleep", type=float, default=0.3)
        return p
```
→ `p.add_argument("--expect-nick", default="")`; `main()` 857-859 `args = ap.parse_args()` 뒤 전역에 넣는다. 빈 문자열 = 검사 안 함(무플래그 불변). 불일치/조회실패 → `close()` 후 `sys.exit(4)`. prep·build 는 MCP 를 안 열어 자동 무관.

**D-17 gate 구멍** — 349-362:
```python
    already = set()
    if not args.skip_group_check:
        gid = int(cfg("coupang.group_id", required=True))
        mcp = CoupangMCP()
        mcp.open()
        try:
            items = mcp.collect_group(gid)
            snaps, _ = snapshot.ensure([i["productId"] for i in items], mcp=mcp, log=None)
            already = {str((snaps.get(i["productId"]) or {}).get("타오바오상품번호") or "")
                       for i in items}
            already.discard("")
```
→ ① `snaps, errs = ...`; `errs` 있으면 `[gate] 쿠팡 그룹 스냅샷 N건 실패 — 부분 대조 금지` + candidates.json **안 쓰고** `return 3`. ② `collect_group_strict`: `group_products` 110-128 의 페이지 루프 모양 + 첫 페이지 `총상품수` 기억 → 끝에 `len(out) < 총상품수` 면 RuntimeError(A3 — 실 1회 읽기로 먼저 확인). ③ `불사자코드` 2차 키 → 400행 `elif row["타오바오상품번호"] and row["타오바오상품번호"] in already:` 옆에 `or row["불사자코드"] in already_codes`. 정상 경로 산출물은 골든과 byte 동일.

**`apply --pids-file`** — 447-453:
```python
    done = {r["원본pid"] for r in _read_jsonl(_p(args.run_dir, "copied.jsonl"))}
    todo = [c for c in cands if c["대표pid"] not in done]

    if args.limit:
        todo = todo[:args.limit]
```
→ `done` 필터와 `limit` **사이**에 `if args.pids_file:` 로 `todo = [c for c in todo if c["대표pid"] in set(pids)]` + 후보에 없는 승인 pid 를 `[apply] 승인됐지만 재조회 후보에 없음:` 으로 출력. 파일 깨짐 = `return 2`(전량 폴백 금지 — 05-PATTERNS §입력 파일 읽기).

**종료코드 계약(유지):** gate 2 = reps 없음, apply 2 = 후보 없음 · 3 = strict-shipping, verify `--only all` 은 중복이어도 0 → **러너/웹은 `verified.json["중복0"]` 을 읽는다**(종료코드 믿지 마라).

---

### `thumb_web.py` · `coupang_web.py` (신규 러너 — 유일한 새 패턴)

**머리** — 각 스킬의 기존 머리를 복사한다. 썸네일은 `run_thumbs.py` 45-52 (`line_buffering=True` — 로그 tail 이 살아 있으려면 필수), 쿠팡은 `run_coupang.py` 26-27 `_HERE` + `_dump` 68-74(원자 쓰기).

**단계 호출 골격** — RESEARCH Pattern 1 (285-302) 그대로: `subprocess.call([sys.executable, RUN_X, stage, "--run-dir", R, *extra], cwd=REPO_ROOT)` → stdout 을 물려받아 잡 로그로 흐른다. `###STAGE### <이름> exit <n>` 센티널, 비0 즉시 정지. **CLI 를 import 하지 않는다**(크레딧 산식만 예외: `thumb_web` 이 `thumb_rules` 의 `credit_estimate`·`MAX_REGEN` import — 순수 함수).
- 러너는 스킬 디렉터리(.venv)에서 돈다 — `sys.executable` 사용 OK. `webapp/**` 트리 가드(`test_argv.py:175-187` sys.executable 금지)는 webapp 트리만 본다.
- 금지 문자열: `--skip-group-check` · `--min-margin` · `--min-orders` · `--strict-shipping` 가 `coupang_web.py` 에 0회(트리 grep 테스트).
- 요약 JSON 모양 = RESEARCH §Code Examples 436-449 (웹이 읽는 유일한 계약). 마지막 줄 센티널 `###COUPANG### ...`/`###THUMB### ...` + `flush=True` (`detail_batch` `###DETAIL###` 규율 — 06-PATTERNS 146-151).
- commit 모드 비교(D-12): RESEARCH §D-12 355-360 — `새 - 옛` 비어있지 않으면 exit 5, 아니면 `승인 ∩ 새` 를 `--pids-file` 로.
- 종료코드: 0/2/3/4/5 (detail_batch `EXIT_OK, EXIT_INPUT, EXIT_POLL, EXIT_NICK, EXIT_BUDGET` 226). 단계 자식의 4 는 그대로 전달.

---

### `webapp/jobs.py` — kind 3종 (service, event-driven)

**① kind 둘 같이** (68-80) — `JobKind` Literal + `KINDS` 에 `"thumb_estimate", "coupang_preview", "coupang_commit"`. 65-67 주석 규율.

**② 가드 집합** — 집합마다 위에 "왜" 단락(89-114, 144-149 관례):
```python
WRITE_KINDS = frozenset({..., "market_commit", "market_poll"})          # + coupang_commit
BULSAJA_KINDS = frozenset({..., "market_preview", "market_commit", "market_poll"})  # + 셋 다
SINGLETON_KINDS = frozenset({..., "detail_estimate", "market_preview"})  # + thumb_estimate, coupang_preview
```
`POLL_INCOMPLETE_OK_KINDS` 424-425 에는 **넣지 않는다**(러너 3 = 폴링미완 아님 — gate 부분읽기 실패는 failed 가 맞다).

**③ 수면방지** (753-755):
```python
    if kind not in ("bulsaja_index", "banner_scan", "detail_submit", "detail_poll",
                    "market_commit", "market_poll"):
        return []
```
→ 세 kind 추가(쿠팡 ship 단계 수 분 · 썸네일 prep 이미지 다운로드).

**④ 폴더 유도** — `_마켓폴더` 663-720 의 "지어내지 않고 부모 체인에서만 푼다" 규율. 차이: 광고 회차 `run_dir` 이 없다.
- 쿠팡: `paths.coupang_runs_root() / f"web-{미리보기잡id}"` — preview 는 자기 id, commit 은 `parent_job_id`(kind == coupang_preview 확인, 아니면 ValueError). **jobs 행 `run_dir` 칸은 비운다**(RESEARCH Anti-Pattern — `paths.run_dir_path` 화이트리스트는 광고 runs 전용, `create_job` 1102-1103 이 run_dir 을 주면 검사한다).
- 썸네일: `paths.thumb_runs_root() / f"web-{잡id}"` — 견적 잡은 보드 재구성에 광고 회차가 필요하므로 `run_dir` 은 광고 회차(화이트리스트 통과), CLI run-dir 은 따로 유도.

**⑤ `_build_argv` 분기** — market 분기 942-973 모양(빈 값 ValueError → `settings.load(force=True)` → `XxxArgv(...).build()` → `prefix=_수면방지_프리픽스(kind)`). 시그니처 763-769 에 kwarg 추가(`thumb_dir`, `coupang_dir`, `approved_path`, `copy_limit`). `coupang_commit` 에 `copy_limit is None` → ValueError("상한 없는 복사는 없다").

**⑥ `create_job`** (978-1248):
- 인자 추가: 1026-1035 의 kind-전용 인자 검사 모양으로(`if max_items is not None and kind != "market_commit": raise`) → `copy_limit` 은 coupang_commit 전용, `thumb_inputs` 는 thumb_estimate 전용.
- `INPUTS_KINDS` 1029 에 **넣지 마라** — 그 경로는 run_dir 필수(1122-1123)다. 썸네일 inputs 는 `_write_detail_inputs` 592-603 모양(tmp → `os.replace`)의 writer 로 thumb 폴더 안에 쓴다. 쿠팡 approved.json 도 같은 writer.
- result_path 분기 1177-1184 옆 `elif kind in COUPANG_KINDS:` / `elif kind == "thumb_estimate":` → `summary.json` / `summary_<job_id>.json`.
- 가드 순서(①.5 계정 → BEGIN IMMEDIATE → `_reap` → WRITE → SINGLETON → 회차 → 대상 → argv → INSERT → spawn) **불변**.

**⑦ `first_coupang_commit_done()`** — `latest_done` 1315-1347 모양 그대로(DB 없으면 만들지 않고 None/False, `_reap` 후 조회). 조건만 `kind='coupang_commit' AND status='done' AND exit_code=0`. DB 접근은 jobs.py 한 곳 규율(`children_of` 1365 선례).

**⑧ `_alive` 좀비** (406-416):
```python
def _alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
```
→ 마지막 `return True` 앞에 `ps -o stat= -p <pid>` (argv 리스트 subprocess, timeout, 예외 시 True 유지) 첫 글자 `Z` 면 False. **`os.waitpid(WNOHANG)` 금지**(RESEARCH §Folded Todo — Popen.poll ECHILD → returncode 0 오기록). `_reap` 453-462 는 손대지 않는다.

---

### `webapp/argv.py` — `ThumbArgv` · `CoupangArgv`

**경로 상수** — 64-67 모양, 주석 한 단락("같은 스킬 디렉터리다" 규율):
```python
MARKET_UPDATE = (paths.repo_root() / ".claude" / "skills" / "bulsaja-detail-page"
                 / "scripts" / "market_update.py")
```
→ `THUMB_WEB = ... / "bulsaja-thumbnail" / "scripts" / "thumb_web.py"`, `COUPANG_WEB = ... / "coupang-candidates" / "scripts" / "coupang_web.py"`.

**모델** — `MarketArgv` 381-435 복사: 기본값 없는 필드, `expect_nick: Nick`, `prefix: list[str] = []`, `build()` 가 `[*self.prefix, str(PY_CLI), str(<SCRIPT>)]` 로 시작, 경로·숫자는 `str()`.
- `CoupangArgv(mode: Literal["preview","commit"], run_dir, expect_nick, summary_out, approved: Path|None, limit: int|None)` — commit 에서 `approved is None` 또는 `limit is None or limit < 1` → ValueError(424-426 모양: "상한 없는 복사는 없다"). **게이트 기준·skip·strict 필드 자체가 없다**(모델에 필드 없음 = 방어, `MarketArgv` 391 "마켓 필드가 없다" 주석 모양).
- `ThumbArgv(run_dir, inputs, expect_nick, summary_out)` — 그룹명은 argv 가 아니라 inputs 파일로(그룹명에 공백·한글 — `PlainArg` 83-94 제약에 안 맞는다).

---

### `webapp/settings.py`
104-109 Phase 6 블록 아래 `# ── Phase 7 (썸네일 · 쿠팡) 에서 더한 키 ──` + `"thumb_max_items": 20`, `"coupang_copy_max_items": 20`, `"coupang_first_max_items": 10`. 읽기는 `settings.cfg("키", settings.DEFAULTS["키"])` 로만.

### `webapp/paths.py`
65-66 `ads_root()` 모양: `def thumb_runs_root(): return data_root() / "thumbnail" / "runs"`, `def coupang_runs_root(): return data_root() / "coupang" / "runs"`.

---

### `routes/jobs.py` — 썸네일 견적 `POST /jobs/thumb/estimate`

**Analog:** `DetailEstimateReq` 218-235 + `post_detail_estimate` 1516-1637 — **거의 그대로**.
- 요청 모델 = `run_dir` + `keys: list[보드키]`(210-211), `_개수` validator 228-235 (상한 = `thumb_max_items` 는 여기가 아니라 본문에서 노출순 자르기 — 초과분은 `상한초과` 사유로 제외).
- 1552-1565 보드 재구성 + 모르는 키 400 그대로(`_판정읽기` → `board.fold_products` → `join.attach`).
- 1580-1611 행 루프의 `뺀다(사유)` 관용구 그대로. 차이: 배너 관문 대신 ② 규칙 소속 확인 + `join.group_index(조인문서["마켓그룹"])[번호]["그룹명"]`(join.py 101-116) 으로 그룹명 매핑 → `{그룹명: [pid…]}` + `pid→판매자상품코드` 맵.
- 1616-1619 통과 0건 400 · 1622-1637 예외 번역 그대로(`_상세잡만들기` 1640-1660 재사용 권장).

### `POST /jobs/thumb/approve` (잡 아님 — 파일 쓰기만)

**Analog:** `post_market_gate` 1921- (`GateReq` 298-309 `extra="forbid"` · 잡 id 하나). 요청 = `ThumbApproveReq(estimate_job_id: JobId)`, 부모 3단 검사는 `post_detail_submit` 1679-1687 모양. 스키마 값(ids·예상·상한)은 전부 **부모 summary.json 에서** 서버가 읽는다(1692-1701 `예상크레딧` 양의 정수 검사 모양 — bool 배제 포함). 그룹 run-dir 마다 `web_approval.json` 원자 쓰기. 응답은 복사용 명령 텍스트 조각(서버가 실행하지 않음).

### `POST /jobs/coupang/preview`

**Analog:** `post_bulsaja_scan` 1345- (클라이언트가 대상을 안 보냄) + `_상세잡만들기` 1640-1660 예외 번역. 요청 모델은 빈 본문 또는 `extra="forbid"` 모델 — 게이트 기준 필드 없음.

### `POST /jobs/coupang/commit` (잡id + 타이핑 건수)

**Analog A — 부모·상한 규율:** `MarketCommitReq` 276-285(`extra="forbid"`) + `post_market_commit` 1825-1876:
```python
    부모 = jobs.job_status(req.preview_job_id)
    if 부모 is None or 부모.get("kind") != "market_preview":
        raise HTTPException(status_code=400, detail="반영 미리보기 작업이 아니다 — 미리보기부터 해라")
    if 부모.get("status") in jobs.LIVE_STATUSES: ...
    if 부모.get("status") != "done" or 부모.get("exit_code") != 0: ...
    경과 = _경과초(부모.get("started_at"))
    ...
    자식들 = jobs.children_of(req.preview_job_id, "market_commit")
```
→ 부모 kind `coupang_preview`; 같은 미리보기 성공 커밋이 있으면 400(RESEARCH Pattern 2). 상한은 `_마켓반영상한` 596-616 모양의 `_쿠팡복사상한()` 한 곳: `coupang_first_max_items if not jobs.first_coupang_commit_done() else coupang_copy_max_items`, `max(1, n)`. 24h 유효시간 `_미리보기유효시간` 1760 재사용.

**Analog B — 건수 확인:** `RevertRoundReq` 195-205 + `post_revert_round` 1262-1268:
```python
    서버가센수 = sum(계정별.values())
    if 서버가센수 != req.confirmed_count:
        raise HTTPException(status_code=409, detail=(f"화면이 본 건수({req.confirmed_count:,})와 지금 건수"
                    f"({서버가센수:,})가 다르다 — 다시 확인해라"))
```
→ `CoupangCommitReq(preview_job_id: JobId, typed_count: int)`. 서버가 `min(통과수, 상한)` 을 다시 세서 다르면 400(CONTEXT/RESEARCH 는 400, 되돌리기는 409 — 플랜에서 하나로 고정).

### ctx 4개 + 결과 분기

- 모두 `_상세견적ctx` 376-407 뼈대: `LIVE_STATUSES` → running, result_path 없음/깨짐 → error(종료코드 안내 402-403), 숫자는 파일 값 그대로.
- `_쿠팡미리보기ctx`: summary.json `기준`·`통과`·`탈락사유별`·`이미있음` + 상한 밖 행 `상한초과` 표시. `_쿠팡결과ctx`: `copied.jsonl` + `verified.json["중복0"]` (종료코드 아님) + `신pid: null` 경고색 + 잠금 승계 안내 1줄.
- `_썸네일결과ctx`: `generated.json` · `decisions.json` · `commit_summary.json` · `review.html` **경로만**(`_경로표시` 685 재사용). taskId 남은 건 = `회수 대기` + recover 명령 텍스트(버튼 없음, L-03).
- `get_job_result` 2036-2046 dict 에 4줄 추가.

---

### 템플릿

- `_thumb_estimate_table.html` ← `_detail_estimate_table.html`: 머리 주석(정본 · "그리지 않는 것" — 재생성 버튼 없음 L-03, 곱셈 없음 L-02 · `| safe` 금지), `running → error → 집계 줄` 순서. 집계 줄 = `선택 N → 이미가공 M · 정합검사 A · 삭제대상 D · 조회실패 E · 현황판제외 → 생성 K · 예상 K×5 · 최대 K×10`(전부 파일값). 버튼 `실행 승인 — 크레딧 0`(`data-estimate-job`).
- `_coupang_preview_table.html` ← `_market_preview_table.html` 1-30 머리·뼈대 + 커밋 영역은 `board.html` 위험구역 585-603 모양:
```jinja
      <details id="danger-details">
        <summary><strong>...</strong> — 펼치기</summary>
        <div class="stale"> ... </div>
        <button type="button" id="revert-round-btn" class="contrast">...</button>
```
→ `<details>` 기본 접힘 · `class="contrast"`(다른 색) · 건수 입력칸 · `data-preview-job`. 기준 문구는 summary `기준` 그대로(`15.0%` 가 보이면 Pitfall 1).
- `_coupang_result_table.html` ← `_market_result_table.html`. `_thumb_result_table.html` ← `_detail_result_table.html`(스토어 반영 버튼 **없음** — "스토어 반영 미연결(Phase 6 완료 후)" 한 줄, D-08 미룸).
- `_job_status.html` 15-30 `작업이름` 에 3줄, 73 running 문구, 98-106 종료코드 블록 복사(러너 계약: 2 입력 · 3 gate 부분읽기(재시도) · 4 계정 · 5 상한/재조회 늘어남).
- `board.html`: 썸네일 버튼은 515-528 `role="group"` 블록 옆(`thumb-estimate-btn`, 문구 `썸네일 견적 — 크레딧 0` — prep 이 현황판에 쓰므로 "쓰기 0" 금지, RESEARCH §Runtime State). 결과 자리 `#thumb-estimate`/`#thumb-estimate-body` 는 349-356 `#detail-estimate` 모양. 쿠팡 패널은 보드 상단 별도 `<section id="coupang">` (회차 무관 → `{% if run_dir %}` 밖).

### `board.js`
- 썸네일 견적: `상세견적버튼` 659-700 복사(`/jobs/thumb/estimate`, `{run_dir, keys}`, `결과기다리기(job_id, 150, "thumb-estimate", "thumb-estimate-body", ...)`). 선택은 기존 `table.getSelectedData()`.
- 쿠팡 미리보기/승인/커밋: `상세작업접수` 729-760 + 위임 804-820 모양. 커밋만 추가로 입력칸 정수 → `{preview_job_id, typed_count}` (되돌리기 건수확인 1005- 모양). 몸통엔 잡 id(+건수)만.

---

### 테스트

- **`test_coupang_web.py` / CLI 주입구** — 로드 방식은 `test_coupang_rules.py` 6-8(`sys.path.insert` + 직접 import, `.venv` 에서 돈다). 가짜 MCP 는 `test_detail_cli.py` `가짜MCP` 99-125("시나리오에 없는 도구 호출 = AssertionError") 를 `CoupangMCP` 자리에 monkeypatch. `실행` 138-147 의 SystemExit→코드 관용구. 케이스: 스냅샷 오류 1건 → candidates.json 미생성·비0 / 빈 페이지 조기종료 → 비0 / 불사자코드 2차 키 / `--pids-file` 필터 / `--expect-nick` 불일치 exit 4 / 러너 비0 정지·센티널 / 늘어남 exit 5.
- **골든** — `test_detail_cli.py` 19-24 docstring 규율 + 252- `test_플래그없음_골든_불변` (환경변수 `*_GOLDEN_WRITE=1` 일 때만 재생성). gate 무플래그 candidates/rejected byte 동일 · prep 무플래그 산출물 동일.
- **`test_thumb_web.py`** — `test_thumb_prep.py` 33-49 setUp/tearDown 몽키패치(`matrix.read/redo_pending/mark_many`, `snapshot.ensure`) + `_args` 27-29 Namespace 관용구. 케이스: estimate-out 4갈래 + K×5/K×10 · `--only-pending` · `--max-credits` 누적 초과 exit 5(무플래그면 `_guard_credits` 경로 불변) · 러너 그룹 실패 격리.
- **`test_jobs.py`** — 1521-1666 market 묶음 복사: kind 등록(`KINDS` + `JobKind.__args__`) · 가드집합 · 수면방지 · coupang exit3 = failed · `_build_argv` 빈 값 거부 · 폴더 유도 · `first_coupang_commit_done` · `_alive` 좀비(가짜 ps).
- **`test_routes_thumb.py` · `test_routes_coupang.py`** — `test_routes_market.py` 34-365 헬퍼(`_행박기` 38 · `_쓰기` 55)·픽스처(`화면`·`엿듣기`·`안띄운다`·`프로필`·`기대닉`·`tmp_run_dir`) 재사용. 추가: 첫 회 argv `--limit 10` · 타이핑 불일치 400 · 두 번째 커밋 400 · WRITE 가드 409 · 모르는 필드 422.
- **`test_argv.py`** — 162-247 트리 가드 모양으로 새 가드 1개: `webapp/**` + 두 러너에 `--skip-group-check`/`--min-margin`/`--min-orders`/`--strict-shipping` 0회(금지 문자열은 런타임 조립 — 212-213 규율). `cfg("coupang.min_margin") == 20.0` 고정 테스트.

---

## Shared Patterns

### 빈 값 ≠ 전량
**Source:** `jobs.py:944-952` · `argv.py:424-426`
**Apply to:** `CoupangArgv.limit`(≥1)·`approved`, `_build_argv` 새 분기, 썸네일 inputs(그룹 0개 = ValueError), CLI `--pids-file` 깨짐 = exit 2.

### 부모 잡 id 하나만 · 상한은 서버가
**Source:** `routes/jobs.py:264-295`(extra=forbid) · `596-616`(`_마켓반영상한`) · `1825-1876`
**Apply to:** thumb approve, coupang commit. 요청에 대상·경로·상한·기준 필드 없음.

### 예외 → 상태코드 번역
**Source:** `routes/jobs.py:_상세잡만들기` 1640-1660 (AccountMismatchError 가 ValueError 보다 먼저)
**Apply to:** 새 POST 3개(approve 제외).

### 산출물은 읽기만 · 도는 중이면 안 읽는다 · 종료코드 대신 파일
**Source:** `_산출물` 335-356 · `_상세견적ctx` 376-407
**Apply to:** 4개 ctx. verify 는 `verified.json["중복0"]`, 썸네일 반영은 `--summary-out` 파일.

### 원자적 JSON 쓰기
**Source:** `run_coupang._dump` 68-74 · `run_thumbs._dump` 175 · `jobs._write_detail_inputs` 592-603
**Apply to:** 러너 summary, estimate-out, approved.json, web_approval.json, 썸네일 inputs.

### 계정 가드 이중 방어
**Source:** `jobs.create_job` 1044-1050 (BULSAJA_KINDS 사전점검) + CLI `_계정확인`(detail_batch 323-334) exit 4
**Apply to:** 세 kind 전부 BULSAJA_KINDS, CLI 두 개에 `--expect-nick`.

### 한국어 주석 + 결정 번호 인용
모든 가드·분기 위에 "왜" 를 L-xx/D-xx/Pitfall N 과 실측 숫자로(기존 파일 전부의 관례이자 가드 삭제 방지 장치).

## No Analog Found

| 파일 | 역할 | 데이터 흐름 | 이유 | 대신 쓸 것 |
|---|---|---|---|---|
| `coupang_web.py` · `thumb_web.py` 의 **다단계 체인 러너** | CLI 러너 | batch (subprocess 체인) | 기존 잡은 전부 CLI 1회 호출. 단계 체인·재조회 비교가 한 프로세스에 있는 선례 없음 | RESEARCH Pattern 1 (280-303) · §D-12 (355-360) · Code Examples 436-449 |
| 광고 회차 없는 잡(쿠팡) 의 폴더 유도 | service | — | 기존 폴더 유도(`_상세폴더`·`_마켓폴더`)는 전부 `_web_dir(run_dir)` 밑 | `paths.coupang_runs_root()/web-<미리보기id>` + `run_dir` 칸 NULL (RESEARCH Anti-Patterns) |

## Metadata

**Analog search scope:** `webapp/` (jobs · argv · settings · paths · join · routes/jobs · templates/_detail_* · _market_* · board.html · _job_status · static/board.js · tests/test_detail_cli · test_routes_market · test_jobs · test_argv), `.claude/skills/bulsaja-thumbnail/scripts/` (run_thumbs · test_thumb_prep), `.claude/skills/coupang-candidates/scripts/` (run_coupang · test_coupang_rules), `.claude/skills/bulsaja-detail-page/scripts/detail_batch.py`, `workspace.toml`
**Files scanned:** 20
**Pattern extraction date:** 2026-09-29
