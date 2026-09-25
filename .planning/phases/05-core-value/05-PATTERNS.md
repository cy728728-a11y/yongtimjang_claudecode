# Phase 5: 상세페이지 작업 버튼 ★ Core Value - Pattern Map

**Mapped:** 2026-09-25
**Files analyzed:** 17 (수정 11 · 신규 6)
**Analogs found:** 17 / 17 (새 패턴 0 — 전부 Phase 1 입찰가 미리보기→실행, Phase 3 불사자 잡, Phase 4 배너 잡을 따라 쓰면 된다)

> 결론: **새로 설계할 것이 없다.** 견적→접수는 `bids_preview → bids_commit` 을 그대로 따르고, 잡 등록은 `banner_scan` 을, CLI 계정 확인과 태그 조회는 `bulsaja_scan.py` 를, CLI 테스트 로더는 `test_banner_scan.py` 를 따른다.

## File Classification

| 신규/수정 파일 | 역할 | 데이터 흐름 | 가장 가까운 기존 코드 | 일치도 |
|---|---|---|---|---|
| `.claude/skills/bulsaja-detail-page/scripts/detail_batch.py` (수정: 플래그 7개) | CLI | batch + request-response (MCP) | 같은 파일의 `submit_one`/`try_submit`/폴링 + `bulsaja_scan.py` 계정확인·배치조회 + `run_ads.py` `_load_only_ads`/`_dump_preview` | exact |
| `webapp/argv.py` (+`DetailArgv`, `DETAIL_BATCH`) | config/argv 모델 | transform | 같은 파일의 `BannerArgv`/`BulsajaArgv` | exact |
| `webapp/jobs.py` (kind 3개 · 가드 집합 · `_build_argv` · result_path · `_finish`) | service (잡 엔진) | event-driven (subprocess) | `banner_scan`/`bulsaja_scan` 분기 | exact |
| `webapp/banner.py` (+`상세입력목록`) | utility (순수 관문 함수) | transform | 같은 파일의 `제품이미지목록` 185-250 | exact |
| `webapp/banner_store.py` (+`확인시각읽기`) | store (ro 읽기) | CRUD 읽기 | 같은 파일의 `확인읽기` 115-141 | exact |
| `webapp/routes/jobs.py` (+`/jobs/detail/estimate`·`/submit`·`/poll` + 결과 ctx) | controller | request-response | `post_bids_preview` 414-449 · `post_bids_commit` 452-501 · `get_job_result` 856-889 | exact |
| `webapp/routes/banner.py` (`_화면투영` 의 `확인됨` 신선도 — 선택) | controller | transform | 같은 파일 483행 | exact |
| `webapp/templates/banner_review.html` (D-03 재확인 버튼) | template | request-response | 같은 파일 304-318 | exact |
| `webapp/templates/_detail_estimate_table.html` (신규) | template | 표시 | `_preview_table.html` | role-match |
| `webapp/templates/_detail_result_table.html` (신규) | template | 표시 | `_result_table.html` | role-match |
| `webapp/templates/board.html` (상세 견적 버튼 + 접수 블록) | template | request-response | `#preview`/`#commit-wrap` 309-347 · `#preview-btn` 482-487 | exact |
| `webapp/static/board.js` (견적·접수·이어서확인 배선) | component (JS) | request-response + 폴링 | `미리보기버튼` 577-620 · `실행버튼` 680-712 · `결과기다리기` 557-575 | exact |
| `webapp/templates/_job_status.html` (kind 이름 + exit 3 문구) | template | 표시 | 같은 파일 20-73 | exact |
| `webapp/settings.py` (`detail_max_poll_min`·`detail_poll_interval`) | config | — | `DEFAULTS` 30-41 | exact |
| `webapp/tests/test_detail_cli.py` (신규) | test | 오프라인 가짜 MCP | `test_banner_scan.py:41-61` 로더 + `test_cli_patch.py` `네트워크차단` | exact |
| `webapp/tests/test_jobs.py` · `test_routes_jobs.py` · `test_banner.py` · `test_routes_banner.py` (추가) | test | — | `test_jobs.py:1147-1235` 배너잡 테스트 묶음 | exact |
| `webapp/tests/fixtures/detail_inputs_*.json` (신규) | fixture | — | `fixtures/targets_one.json` · 익명화 규율(`zz*`, `zzcdn.example`) | role-match |

---

## Pattern Assignments

### `detail_batch.py` (CLI, batch) — 주입구 플래그만

**규율:** 새 분기는 전부 `if args.inputs:` 안. 플래그 없는 줄은 한 줄도 안 건드린다(01-02 `--only-ads` 선례). 현재 파일 381줄 전문 확인됨.

**고칠 자리(줄 번호):**
- 인자 정의: `main()` 215-235 — 여기에 `--inputs --done-tags --estimate-only --estimate-out --max-credits --expect-nick --summary-out` 추가
- 대상 로딩: 241-247 (`products.json` → inputs 모드면 `items` 순서로 교체)
- 스킵 판정: `submit_one` 190-193 `prev["pages"] >= sc` → inputs 모드에서 절대조건 `기작업()`
- 이미지: `submit_one` 186 `collect_images(data, pages)` → inputs 모드면 `imgs_override`
- 장수 불일치: 205-210 (`isinstance(exp,int)` 가 아니면 조용히 통과 — **Pitfall 2**) + `try_submit` 287-291 (taskId 저장 없이 exit 2)
- 폴링 조기종료: 359-367 `done + fail >= taskId보유수` (**Pitfall 1**) · 타임아웃도 exit 0 (339-368)
- 센티널: 374-375 `###DETAIL###`

**기존 핵심 — 동시 전송 (DETAIL-03, 테스트로 고정만)** (194-201):
```python
base = {"productId": pid, "imageUrls": imgs, "sectionCount": sc,
        "quality": quality, "confirm": False}
pre = mcp.call_tool("bulsaja_detail_page_generate", base)
token = pre.get("confirmationToken")
...
fin = mcp.call_tool("bulsaja_detail_page_generate",
                    {**base, "confirm": True, "confirmationToken": token})
```

**체크포인트 원자 쓰기 — 그대로 재사용** (63-70):
```python
def save_json(path, obj):
    try:
        tmp = str(path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except Exception as e:
        print(f"[경고] 체크포인트 저장 실패: {e}")
```
→ `--estimate-out`·`--summary-out` 도 이 함수로 쓴다.

**`--expect-nick` 복사원:** `bulsaja-detail-page/scripts/bulsaja_scan.py:142-153` + 호출부 277-285
```python
def 계정확인(mcp, 기대닉, 프로필경로):
    프로필 = 표시규칙제거(mcp.call_tool("bulsaja_my_profile", {}) or {})
    닉 = str(프로필.get("닉네임") or "")
    기록 = {"닉네임": 닉, "크레딧": str(프로필.get("크레딧") or ""), "확인시각": 지금()}
    ...
    return 기록, 닉 == str(기대닉)
# 호출부
계정, 통과 = 계정확인(mcp, 인자.expect_nick, 인자.profile_out)
if not 통과:
    사유 = ("⛔ 붙어 있는 불사자 계정이 기대한 계정이 아니다 (ENG-08). ...")
    return 3          # detail_batch 는 exit 4 (3 은 폴링미완에 배정)
```
→ `크레딧` 필드가 견적 JSON 의 `잔액`(참고용) 출처다. 프로필 파일은 안 써도 된다(닉 비교만).

**태그 조회(D-12) 복사원:** `bulsaja_scan.py:211-246` `배치조회` — 50개 배치, 실패 코드를 들고 나온다(CR-02). 응답 해석은 `ss_index_calls.항목꺼내기`(116-134) 한 곳:
```python
r = mcp.call_tool("bulsaja_product_find_by_code", {"codes": 조각})
항목들.extend(항목꺼내기(표시규칙제거(r), 맥락=f" (코드 {len(조각)}건)"))
# except RuntimeError → 실패코드.update(조각)   ← 실패 = 접수 안 함(status "태그미조회")
```
import 방식은 `bulsaja_scan.py:80-89` (`SCRIPT_DIR` 를 sys.path 에 넣고 `from ss_index_calls import 항목꺼내기`). detail_batch 는 같은 디렉터리라 스크립트 실행 시 sys.path[0] 로 잡힌다. `bulsaja_rate.안전호출` 까지 끌어올지는 재량(5건 규모라 단순 호출로 충분).

**`불리언정규화` 복제원:** `webapp/state.py:57-78` (6줄 + `_FALSY`). CLI 는 웹앱을 import 하지 않으므로 **복제** + 교차 테스트.
```python
_FALSY = {"0", "false", "no", "n", "", "none", "null"}
def 불리언정규화(v) -> bool:
    if v is None: return False
    if isinstance(v, bool): return v          # bool 분기가 int 보다 먼저
    if isinstance(v, (int, float)): return v != 0
    return str(v).strip().lower() not in _FALSY
```
**`기작업` 규칙 정본:** `state.py:99-122` `기작업여부(그룹태그, dc, done_tags)` — 태그 strip 후 집합 비교 OR `상세상태(dc)==AI가공완료`.

**입력 파일 읽기 — 폴백 금지 복사원:** `naver-ads-weekly/scripts/run_ads.py:165-175, 202-208`
```python
try:
    only = _load_only_ads(args.only_ads)
except Exception as e:
    print(f"--only-ads 읽기 실패 — 전량 실행으로 폴백하지 않는다: {type(e).__name__}: {e}")
    return 1
```
→ `--inputs` 깨짐 = exit 2 (전량 폴백 금지). `--done-tags` 비면 exit 2.

**종료코드(권장, RESEARCH):** 0 전부 종결 · 2 입력오류/장수불일치 · **3 폴링미완(실패 아님)** · 4 계정 불일치 · 5 `--max-credits` 초과. `caffeinate -i` 는 exit code 를 그대로 넘긴다(`jobs.py:559-560` 실측 주석).

---

### `webapp/argv.py` — `DetailArgv` (argv 모델)

**Analog:** `BannerArgv` 216-302 (기본값 없는 필수 필드 + 조건 없이 전부 붙이기), `BulsajaArgv` 137-213 (`expect_nick: Nick`, 선택 플래그는 값 있을 때만).

**경로 상수 자리** (47-57 옆에 추가):
```python
BANNER_SCAN = (paths.repo_root() / ".claude" / "skills" / "bulsaja-detail-page"
               / "scripts" / "banner_scan.py")
# → DETAIL_BATCH = (... / "bulsaja-detail-page" / "scripts" / "detail_batch.py")
```

**타입 재사용:** `Nick`(73-74) → `expect_nick`, `PlainArg`(83-84) → `done_tags: list[PlainArg]` (`구매_가공완료` 는 패턴 `^[^-\s][^\s]*$` 통과).

**build 모양** (269-277 따라):
```python
def build(self) -> list[str]:
    av: list[str] = [*self.prefix, str(PY_CLI), str(BANNER_SCAN)]
    av += ["--join", str(self.join)]          # 경로는 전부 str() — argv 컬럼 JSON 직렬화
    av += ["--workers", str(self.workers)]    # 숫자도 str()
```
- `mode` Literal["estimate","submit","poll"] → estimate 면 `--estimate-only --estimate-out`, poll 이면 `--poll-only`, submit 이면 `--max-credits` 필수(None 이면 **build 가 아니라 `_build_argv` 에서** ValueError — 가드 한 곳 규율, `BulsajaArgv` 197-202 주석).
- `done_tags` 는 반복 인자 또는 JSON 한 개로 — CLI 계약과 1:1.
- `test_argv.py` 트리 가드(셸 경유 0 · requests/eroomlib import 0)가 자동 집행.

---

### `webapp/jobs.py` — kind 3개 등록 (service, event-driven)

**Analog:** `banner_scan` 등록 전부.

**① kind 둘 같이 고친다** (68-76):
```python
JobKind = Literal[..., "banner_scan"]          # + "detail_estimate","detail_submit","detail_poll"
KINDS: tuple[str, ...] = (..., "banner_scan")  # 둘 다
```
**② 가드 집합** (85, 97, 122) — 각 집합 위 주석에 **왜 넣었/뺐는지** 한 단락씩 추가(기존 관례):
```python
WRITE_KINDS = frozenset({"prep", "bids_commit", "revert_only", "revert_all"})  # + detail_submit, detail_poll
BULSAJA_KINDS = frozenset({"bulsaja_index", "bulsaja_scan"})                   # + 세 개 전부
SINGLETON_KINDS = frozenset({"bulsaja_index", "bulsaja_scan", "banner_scan"})  # + detail_estimate
```
**③ 수면방지** (552-568):
```python
if kind not in ("bulsaja_index", "banner_scan"):   # + "detail_submit", "detail_poll"
    return []
```
**④ `_build_argv` 분기** — `banner_scan` 645-709 모양 그대로:
```python
if kind == "banner_scan":
    if targets_path is None:
        raise ValueError("배너 스캔에는 조인 산출물이 반드시 있어야 한다 — "
                         "빈 값은 전량이 아니다")
    if not run_dir: raise ValueError(...)
    if result_path is None: raise ValueError(...)
    settings.load(force=True)        # 설정 재읽기 (04-10)
    return argv_mod.BannerArgv(..., prefix=_수면방지_프리픽스(kind)).build()
```
→ detail 세 kind: `targets_path`(=inputs) None 이면 ValueError. `expect_nick=settings.cfg("expected_bulsaja_nick", required=True)`(632), `done_tags=settings.cfg("done_tags", settings.DEFAULTS["done_tags"])`, 폴링 값도 `settings.cfg`.
- ⚠️ `_build_argv` 시그니처(571-573)에 `parent`/`detail run-dir` 이 없다 → 인자 하나 추가하거나 `create_job` 에서 detail 폴더를 계산해 넘긴다(재량). detail 폴더 규칙: **견적 잡 id 로 짓고**, submit/poll 은 `parent_job_id` 체인을 따라 같은 폴더.

**⑤ result_path 분기** (872-880 `banner_scan` 옆에 나란히):
```python
elif kind == "banner_scan":
    if not run_dir: raise ValueError(...)
    result_path = _web_dir(run_dir) / f"banner_{job_id}.json"
```
→ estimate: `web/detail_<estimate_id>/estimate.json` · submit/poll: `web/detail_<부모estimate_id>/summary_<job_id>.json`.

**⑥ 대상 파일 재사용 — 그대로 사용** (`_override_targets` 493-516): 부모 디렉터리가 **정확히 `web/`** 여야 통과(512). 그래서 inputs 파일은 `web/targets_<estimate_id>.json` 에 두고, 견적 라우트는 `only_ads=` 대신 **inputs 모양 JSON 을 쓸 새 writer** 가 필요하다(`_write_targets` 479-490 는 리스트를 `json.dumps` 만 한다 → 같은 tmp→`os.replace` 관례로 dict 쓰기). `_count_targets`(519-531)는 리스트/`adIds` 만 센다 → `items` 모양도 세도록 한 줄 확장.

**⑦ `_finish` exit 3** (375-378) — 현재:
```python
def _finish(cx, job_id, code):
    cx.execute("UPDATE jobs SET status = ?, exit_code = ?, ended_at = ? WHERE id = ?",
               ("done" if code == 0 else "failed", code, _now(), job_id))
```
→ detail kind + code 3 이면 `"done"` 유지 + `exit_code=3`. kind 를 알려면 `_reap`(396-401) 쿼리에 `kind` 컬럼 추가 또는 `_finish` 안에서 조회. **새 상태값을 만들지 않는다**(`latest_done`·가드 쿼리 불변).

**⑧ create_job 순서 불변** (714-939) — 계정 가드(765-771) → BEGIN IMMEDIATE → WRITE 가드(790-801) → SINGLETON 가드(808-819) → 회차 화이트리스트 → 대상 파일 → argv → INSERT `starting` → spawn → `running`. detail 도 이 함수만 탄다(라우트에서 가드 재구현 금지).

---

### `webapp/banner.py` — `상세입력목록` (순수 관문 함수)

**Analog:** `제품이미지목록` 185-250. **옛 함수는 지우지 않는다**(테스트 15곳 참조). 새 함수를 옆에 추가.

**구조 복사 — 예외 메시지에 결정 번호·실측 숫자 적기**:
```python
def 제품이미지목록(상품: dict, 게이트통과: bool = False, *,
              잔여하한: int | None = None) -> list[str]:
    if not isinstance(상품, dict):
        raise ValueError(f"상품이 dict 가 아니다: {type(상품).__name__}")
    if 게이트통과 is not True: raise ValueError(...)          # ← D-02 로 교체: 확인시각 ≥ 생성시각
    사유 = 스킵사유읽기(상품)                                  # ② 그대로 재사용 (163-183)
    if 사유:
        raise ValueError(f"스킵된 상품이다: {사유} — Phase 5 입력으로 쓸 수 없다 (D-07/D-08)")
    장들 = 상품.get("장")
    미판정장 = [c for c in 장들 if isinstance(c, dict) and c.get("판정") == 미판정]
    if 미판정장: raise ValueError(...)                        # ③ 유효판정(라벨 우선) 기준으로 바꿔서
```
- 라벨 키 정수화는 `_라벨정규화` 253-274 재사용(문자열 키면 라벨이 조용히 사라진다).
- 상품 키는 `상품키()` 143-160 (타오바오상품번호 → 불사자코드 폴백).
- 시각 비교는 `datetime.fromisoformat` — `jobs._reap` 407-413 관용구(문자열 비교 금지). 저장 시각은 `banner_store._now()`(72-75) 오프셋 포함 ISO.
- 기계 `제품이미지` 필드를 쓰지 말고 `장` + 라벨로 다시 고른다(D-23 ①). URL 중복 제거(순서 유지)는 `detail_batch.collect_images` 161-163 의 `if u not in urls` 관용구.
- 하한 기본값은 `기본_잔여하한`, 정본은 `settings.cfg("banner_skip_min_keep", ...)` — 키워드 인자 필수(기본값 없음 = 누락 시 TypeError).

---

### `webapp/banner_store.py` — `확인시각읽기`

**Analog:** `확인읽기` 115-141 (그대로 복사, SELECT 컬럼만 추가):
```python
키 = str(run_dir or "").strip()
if not 키:
    raise ValueError("run_dir 이 비었다 — 회차 없이 확인 표시를 묶으면 회차가 섞인다")
if not db_path().is_file():
    return set()                     # → {}
try:
    cx = _ro_conn()
except sqlite3.Error:
    return set()                     # → {}
try:
    행들 = cx.execute(
        "SELECT 타오바오상품번호 FROM banner_confirm WHERE run_dir = ?", (키,)).fetchall()
        # → "SELECT 타오바오상품번호, 확인시각 FROM banner_confirm WHERE run_dir = ?"
finally:
    cx.close()
```
`확인기록`(186-207)은 이미 `INSERT OR REPLACE` + `_now()` 라 재클릭이 시각을 갱신한다 — 서버 수정 불필요.

---

### `webapp/routes/jobs.py` — detail 라우트 3개 + 결과 ctx (controller)

**요청 모델 Analog** (138-172):
```python
class BidsCommitReq(BaseModel):
    """실행 요청. **받는 것은 부모 미리보기 job_id 하나뿐이다.** ..."""
    preview_job_id: JobId            # JobId 패턴 133-135 재사용
```
→ `DetailSubmitReq(estimate_job_id: JobId)`, `DetailPollReq(submit_job_id: JobId)`. 견적 요청은 `BidsPreviewReq` 모양: `run_dir: str` + `keys: list[판매자상품코드 패턴]` + `@field_validator` 개수 상한(148-159).

**견적 라우트 Analog** `post_bids_preview` 414-449 — 서버가 대상을 **다시 검증**(①)하고 `create_job`:
```python
try:
    rows = board.fold_products(_판정읽기(req.run_dir))
    계정별 = flow.collect_targets(rows, req.ad_ids)     # → 조인 산출물로 코드→productId, 관문 통과분만
    ...
    job_id = jobs.create_job("bids_preview", run_dir=req.run_dir, ..., only_ads=대상)
except jobs.BusyError as e:
    raise HTTPException(status_code=409, detail=f"이미 도는 작업이 있다 — 끝나고 다시 눌러라 ({e})")
except ValueError as e:
    raise HTTPException(status_code=400, detail=str(e))
return {"job_id": job_id}
```
- 입력 재료: 배너 산출물 = `jobs.latest_done("banner_scan", run_dir)` (`post_banner_scan` 792-804 관용구 — glob 금지, 파일 사라짐은 409), 조인 산출물 = `latest_done("bulsaja_scan", ...)`, 라벨 = `banner_store.라벨읽기`, 확인시각 = `확인시각읽기`.
- ⚠️ `post_bids_preview` 는 `AccountMismatchError` 를 따로 안 잡는다. detail 은 BULSAJA_KINDS 라 **`_작업만들기` 355-394 의 except 순서**(AccountMismatchError → BusyError → ValueError → KeyError → RuntimeError)를 복사할 것.

**접수 라우트 Analog** `post_bids_commit` 452-501 — 부모 검사 3단 그대로:
```python
부모 = jobs.job_status(req.preview_job_id)
if 부모 is None or 부모.get("kind") != "bids_preview":
    raise HTTPException(status_code=400, detail="미리보기 작업이 아니다 — 먼저 미리보기부터 해라")
if 부모.get("status") == "running": raise HTTPException(400, ...)
if 부모.get("status") != "done": raise HTTPException(400, ...)
대상파일 = 부모.get("targets_path")
if not 대상파일 or not Path(대상파일).is_file(): raise HTTPException(400, ...)
job_id = jobs.create_job("bids_commit", run_dir=부모.get("run_dir"), ...,
                         parent_job_id=req.preview_job_id, targets_path_override=대상파일)
```
→ detail_submit: 부모 kind `detail_estimate` · `max_credits` 는 **부모 estimate.json 의 `집계.예상크레딧`** 을 서버가 읽어 넘긴다(화면 값 안 믿음). 예상크레딧 0 이면 400(접수할 게 없음).
→ detail_poll: 부모 kind `detail_submit` (status `done`+exit 3 **또는** `orphaned` 허용 — Pitfall 4), 같은 inputs/detail 폴더.

**결과 조각 분기 Analog** `get_job_result` 877-882:
```python
조각, ctx = {
    "bids_commit": ("_result_table.html", _실행표ctx),
    "revert_only": ("_revert_table.html", _되돌리기표ctx),
    ...
}.get(kind, ("_preview_table.html", _미리보기표ctx))
```
→ `"detail_estimate": ("_detail_estimate_table.html", _상세견적ctx)`, `"detail_submit"/"detail_poll": ("_detail_result_table.html", _상세결과ctx)`. ctx 는 `_산출물` 214-235 규율(도는 중이면 읽지 않음 → `running: True`). 결과 ctx 는 **`detail_status.json` 을 정본으로** 읽고 exit_code 는 보조(Pitfall 4).

**라우트 배치:** POST 는 812행 "여기서부터 읽기 전용" 위에. GET 은 아래(V-SAFE-01d 스캐너). 쓰기 토큰은 `security.guard` 미들웨어가 자동(`post_banner_scan` docstring 785-787).

---

### `webapp/templates/banner_review.html` — D-03 (304-318)

현재 `{% if 상품.확인됨 %}` 이면 배지만, `{% elif 상품.확인요청 %}` 이면 버튼. 수정 = 확인됨이어도 배지 + 같은 버튼(`hx-post="/banner/confirm"`, `hx-vals='{{ 상품.확인요청 | tojson }}'`, `hx-target="this" hx-swap="outerHTML"`)을 같이 그린다. 버튼 속성 블록(311-318)을 그대로 복사하고 문구만 `다시 확인`. 라우트 응답(`routes/banner.py:360-361`)은 배지 조각이라 재클릭 후 배지로 바뀐다 — 재재클릭까지 원하면 응답 조각에도 버튼을 넣는 것은 재량.

**선택 보강:** `routes/banner.py:483` `"확인됨": bool(키 and 키 in 확인)` → `확인시각 ≥ 문서["생성시각"]` 으로 계산하면 낡은 확인이 화면에 바로 드러난다(`확인시각읽기` 사용).

---

### `_detail_estimate_table.html` / `_detail_result_table.html` (신규 template)

**Analog:** `_preview_table.html` 1-40+ / `_result_table.html`.
복사할 뼈대:
```jinja
{% if running %}
  <p>미리보기를 만드는 중이다… 위 진행 로그를 봐라.</p>
{% elif error %}
  <p class="stale"><strong>미리보기를 못 읽었다 — {{ error }}</strong><br>
    산출물이 없거나 깨졌다. 빈 표를 결과로 읽지 않게 표를 그리지 않는다.</p>
{% else %}
  {# 집계 줄 — 항상 먼저. 0건이어도 띄운다 (Pitfall 6) #}
```
- `running → error` 순서 고정(뒤집으면 죽은 코드).
- 견적 집계 줄: 선택 N → 스킵 M → 접수 K · 총장수 · 예상크레딧 · 잘린 상품 X · 계정 · 잔액(참고). 숫자는 전부 CLI `estimate.json` 에서, 템플릿·JS 에서 계산 금지.
- 결과 표: 판매자상품코드 · 상태(접수/완료/실패/스킵/폴링중) · 장수 · 크레딧 · 사유. exit 3 / 미완료 있음 → `이어서 확인` 버튼만, 재접수 버튼 **없음**(D-17).
- 자동 이스케이프, `| safe` 금지.

---

### `webapp/templates/board.html` + `webapp/static/board.js` (선택 → 견적 → 접수)

**HTML Analog:** `#preview`/`#commit-wrap` 309-347 (hidden 섹션 + 요약 `<p>` + contrast 버튼 + hidden input 에 부모 job_id), 선택 바 `#sel-bar` 462-488 (D-07: 선택 UI 재사용 — `sel-all`/`sel-banner` 그대로).
```html
<button type="button" id="commit-btn" class="contrast" disabled>진짜 올린다</button>
<input type="hidden" id="commit-preview-job" value="">
<p><small>누르는 즉시 접수된다 — 확인 창은 없다. 위 표가 곧 확인 창이다.</small></p>
```
→ 상세용 id 는 별도(`detail-estimate-btn`, `detail-submit-btn`, `detail-estimate-job`, `#detail-estimate`/`#detail-result` 섹션). 입찰가 블록과 id 공유 금지.

**JS Analog:** `미리보기버튼` 577-620 → 견적; `실행버튼` 680-712 → 접수; `결과기다리기(job_id, 남은, 자리id, 몸통id, 끝났을때)` 557-575 재사용.
```js
fetch("/jobs/bids/preview", {
  method: "POST",
  headers: { "Content-Type": "application/json", "X-CT-Token": 토큰() },
  body: JSON.stringify({ run_dir: 회차칸값 ? 회차칸값.value : "", ad_ids: ids })
}).then(...)
  var job_id = JSON.parse(res.본문).job_id;
  htmx.ajax("GET", "/jobs/" + encodeURIComponent(job_id) + "/panel",
            { target: "#job-panel", swap: "outerHTML" });
  결과기다리기(job_id, 150, "preview", "preview-body", function (상태) { 실행열기(job_id, 상태); });
```
- 대상 키: `table.getSelectedData()` 의 판매자상품코드(`r.key` 가 아닌 코드 필드 — 행 데이터 확인). 🔴 기본 선택·🟡 수동은 `고를수있는`(419-421)·`요약갱신`(423-) 규칙 재사용, 상태 판별은 `상태기호[r.상세상태] === "🔴"`(429).
- 접수 요청 몸통은 `{ estimate_job_id }` 하나뿐(690행 `{ preview_job_id: 부모 }` 모양).
- 접수 잡은 수십 분 — `결과기다리기` 폴링 한도로 끝까지 기다리지 말고, 패널(SSE)로 보고 결과 표는 끝났을 때/재방문 시 `GET /jobs/{id}/result` 로.
- 오류 표시는 `오류표시`(544-548) + detail 파싱(598-604) 그대로.

---

### `webapp/templates/_job_status.html` (20-73)

`작업이름` dict(20-23 부근)에 세 kind 이름 추가. `상태이름` 은 불변. `job.status == "done" and job.exit_code == 3` 분기를 `failed` 분기(62-66) 옆에 추가 — 문구 "폴링 미완 — 실패 아님. `이어서 확인` 을 눌러라". running 문구(56-61)의 "입찰가 인상은 초당 12건" 은 kind 별로 가를 것.

---

### `webapp/settings.py` (DEFAULTS 30-41)

Phase 4 블록처럼 **Phase 5 주석 블록**을 새로 열고 `"detail_max_poll_min": 60`, `"detail_poll_interval": 45` 추가. 읽기는 `settings.cfg("키", settings.DEFAULTS["키"])` 로만. `done_tags` 는 기존 키(41) 재사용.

---

### `webapp/tests/test_detail_cli.py` (신규, 가짜 MCP)

**로더 Analog:** `test_banner_scan.py:36-61`
```python
저장소루트 = Path(__file__).resolve().parents[2]
스캐너경로 = (저장소루트 / ".claude" / "skills" / "bulsaja-detail-page" / "scripts" / "banner_scan.py")

def _스캐너():
    규격 = importlib.util.spec_from_file_location("_banner_scan_under_test", 스캐너경로)
    모듈 = importlib.util.module_from_spec(규격)
    규격.loader.exec_module(모듈)
    return 모듈

@pytest.fixture(scope="module")
def 스캐너():
    이전 = list(sys.path)
    try:
        yield _스캐너()
    finally:
        sys.path[:] = 이전           # detail_batch 도 최상위에서 sys.path.insert 한다(51행)
```
→ 추가: 로드 **전** `monkeypatch.setitem(sys.modules, "bulsaja_mcp", 스텁)` (detail_batch 52행 `from bulsaja_mcp import BulsajaMCP` 가 eroomlib 을 끌지 않게). `ss_index_calls` 는 외부 import 0 이라 그대로 로드됨. 가정 A1 을 Wave 0 첫 테스트로 실측.

**네트워크 차단 Analog:** `test_cli_patch.py` `네트워크차단` fixture(~64-) — 호출 기록 리스트 + `time.sleep` 무력화. `main()` 은 `monkeypatch.setattr(sys, "argv", [...])` 후 호출, `SystemExit.code` 로 종료코드 단언.

**골든(L-04):** 플래그 없는 호출 순서·인자를 **패치 전 커밋에서** 기록 → `fixtures/` 에 두고 비교.

### `test_jobs.py` 추가분

**Analog:** 1147-1235 배너잡 묶음을 kind 별로 복사:
- `test_배너잡_kind_가_등록돼_있다` → `KINDS` 와 `JobKind.__args__` 둘 다
- `test_배너잡은_전역_쓰기가드에_안_들어간다` → detail_submit/poll ∈ WRITE_KINDS, estimate ∉; 셋 다 ∈ BULSAJA_KINDS; estimate ∈ SINGLETON_KINDS
- `test_배너잡은_조인_산출물이_없으면_안_만들어진다` → `jobs._build_argv("detail_submit", ..., None, ...)` ValueError
- `test_배너잡_argv_가_설정에서_온다` → `_toml덮기`(1138-1144) + `av[av.index("--max-poll-min")+1]` + `av[:2] == [jobs.CAFFEINATE, "-i"]`
- 공용 fixture: `잡판`(73-), `안띄운다`(882-884), `가짜프로세스`
- `_finish` exit 3 → status `done` 단언 (새 테스트, `test_잡이_끝나면_exit_code_가_기록된다` 330 모양)

### `test_routes_jobs.py` / `test_routes_banner.py` / `test_banner.py`

- 라우트: `test_불사자_라우트는_토큰없이_안된다`(250) · `_타사이트_origin_도_403`(258) · `_GET이_아니다`(266) · `test_계정불일치면_409`(275) 를 `/jobs/detail/*` 로 복사. 접수는 "대상 필드 없음 · 부모 kind 틀리면 400".
- 배너 화면: `test_라벨과_확인이_실제로_저장된다`(408) 옆에 `다시확인` — 확인된 상품 HTML 에 `hx-post="/banner/confirm"` 버튼이 있다.
- 관문: `test_banner.py` 에 `상세입력` 케이스(낡은 확인 · 스킵 · 미판정 · <2장 → ValueError / 라벨우선 · 무내용 제외 · 중복 제거 · 10장 자르기 · 키워드 인자 누락 TypeError).

---

## Shared Patterns

### 빈 값 ≠ 전량 (5번째 적용)
**Source:** `jobs.py:599-601, 617-621, 652-659` · `banner.py:185-250` · `run_ads.py:202-208`
**Apply to:** `_build_argv` detail 분기, `상세입력목록`, CLI `--inputs`/`--done-tags`
```python
if targets_path is None:
    raise ValueError("배너 스캔에는 조인 산출물이 반드시 있어야 한다 — 빈 값은 전량이 아니다")
```
막는 자리는 한 곳(`_build_argv`), CLI exit 2 가 2층.

### 부모 파일만 가리키기 (D-11 / FLOW-02)
**Source:** `routes/jobs.py:452-501` + `jobs._override_targets` 493-516
**Apply to:** detail_submit, detail_poll — 요청 모델에 대상 필드 자체가 없다.

### 예외 → 상태코드 번역
**Source:** `routes/jobs.py:_작업만들기` 373-392 (AccountMismatchError 를 ValueError 보다 **먼저**)
**Apply to:** 세 detail POST 라우트 전부.

### 설정은 호출부에서 읽어 넘긴다 (T-1-12)
**Source:** `jobs.py:625-643, 661-709` — `settings.cfg("키", settings.DEFAULTS["키"])`, 닉은 `required=True`
**Apply to:** `DetailArgv` 필드(기본값 없음), 폴링 상한·간격, done_tags.

### 산출물은 읽기만 · 도는 중이면 안 읽는다
**Source:** `routes/jobs.py:_산출물` 214-235, `_preview_table.html` running→error 순서
**Apply to:** 견적·결과 ctx/템플릿. 결과 정본은 `detail_status.json`(Pitfall 4).

### 원자적 JSON 쓰기
**Source:** `jobs._write_targets` 479-490 (tmp → `os.replace`) · `detail_batch.save_json` 63-70
**Apply to:** inputs 파일(웹앱), estimate/summary(CLI).

### 한국어 주석 + 결정 번호 인용
모든 가드·분기 위에 "왜"를 결정 번호(D-xx, L-xx, Pitfall N)와 실측 숫자로 적는다 — 기존 파일 전부의 관례이자 가드 삭제 방지 장치.

## No Analog Found

없음. 참고로 **기존 패턴을 넓혀야 하는 곳** 3개:

| 자리 | 문제 | 제안 |
|---|---|---|
| `jobs._finish` 375-378 | kind 를 모른다 → detail exit 3 을 `failed` 로 찍는다 | `_reap` 쿼리에 kind 추가 후 넘기기 |
| `jobs._write_targets` 479-490 / `_count_targets` 519-531 | 리스트만 쓰고/센다 | inputs dict 용 writer 추가 + `items` 세기 한 줄 |
| `jobs._build_argv` 571-573 시그니처 | 부모 job 의 detail 폴더를 모른다 | `create_job` 에서 detail run-dir 계산해 인자로 전달 |

## Metadata

**Analog search scope:** `webapp/` (jobs · argv · banner · banner_store · state · join · settings · routes/jobs · routes/banner · templates · static/board.js · tests), `.claude/skills/bulsaja-detail-page/scripts/` (detail_batch · bulsaja_scan · ss_index_calls), `.claude/skills/naver-ads-weekly/scripts/run_ads.py`
**Files scanned:** 20
**Pattern extraction date:** 2026-09-25
