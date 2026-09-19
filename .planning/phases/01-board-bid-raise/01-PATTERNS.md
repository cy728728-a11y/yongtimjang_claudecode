# Phase 1: 첫 왕복 — 보드 + 입찰가 인상 버튼 - Pattern Map

**Mapped:** 2026-09-20
**Files analyzed:** 18 (기존 CLI 수정 3 · 웹앱 신규 15)
**Analogs found:** 12 / 18 (exact 3 · role-match 5 · partial 4 · none 6)

> **이 저장소에 웹앱은 없다.** FastAPI·Jinja2·SSE·uvicorn 문자열이 `.py` 어디에도 없다
> (`grep -rln "fastapi\|jinja2\|uvicorn" --include=*.py .` → 0건). 라우터·템플릿·SSE·미들웨어는
> **analog 없음**이다. 지어내지 않았다. 그 자리는 RESEARCH.md §4·§5 의 실측 코드를 쓴다.
>
> 대신 값이 있는 analog 는 **Python CLI·배치 스크립트**다. 잡 엔진(subprocess·체크포인트·append-only),
> 산출물 JSON → 표 투영, 시크릿 비노출, 한국어 주석·try-except 관용구가 전부 여기 이미 있다.

---

## File Classification

### A. 기존 CLI 패치 (원위치 수정 — 복사본 금지)

| 수정 파일 | Role | Data Flow | Closest Analog | Match |
|---|---|---|---|---|
| `.claude/skills/naver-ads-weekly/scripts/run_ads.py` | CLI 진입점 (route) | request-response (argv in / 파일 out) | **자기 자신** — 기존 `cmd_apply`/`cmd_bids` 방어 패턴 | exact |
| `.claude/skills/naver-ads-weekly/scripts/bids.py` | service | batch + 외부쓰기 | **자기 자신** — 기존 `run_bids` 가드 배치 | exact |
| `.claude/skills/naver-ads-weekly/scripts/test_bids.py` (회귀 보강) | test | unit + tempfile 픽스처 | `test_bids.py:210-267` `TestRunBidsBackupMerge` | exact |

### B. 웹앱 신규 (`webapp/` — 새 최상위 디렉터리)

| 신규 파일 | Role | Data Flow | Closest Analog | Match |
|---|---|---|---|---|
| `webapp/paths.py` | utility | file-I/O | `run_ads.py:29-57` + `.claude/lib/eroomlib/config.py:82-97` | exact |
| `webapp/settings.py` | config | 읽기 | `.claude/lib/eroomlib/config.py:32-76,135-154` | role-match |
| `webapp/argv.py` | model/builder | transform | `run_ads.py:198-220` (argv 계약의 반대편) + `runner/onestep.py:365-371` | role-match |
| `webapp/jobs.py` | service (잡 엔진) | event-driven + batch | `sellerlife-keyword/scripts/run_all.py:33-48` (Popen) + `detail_batch.py:59-66,306-311` (체크포인트) | role-match |
| `webapp/board.py` | service (투영) | file-I/O → transform | `report_md.py:17-45,48-71` + `sheets_out.py:32-48` | exact |
| `webapp/security.py` | middleware | request-response | **없음** (웹 계층 부재). 시크릿 스크러버만 `detail_batch.py:69-78` | partial |
| `webapp/logtail.py` | service | streaming | **없음** (생산자 쪽만 있다: `detail_batch.py` `flush=True`) | partial |
| `webapp/main.py` | config/조립 | — | **없음** | none |
| `webapp/routes/board.py` | controller | request-response | **없음** | none |
| `webapp/routes/jobs.py` | controller | request-response + SSE | **없음** | none |
| `webapp/routes/health.py` | controller | request-response | **없음** | none |
| `webapp/templates/board.html` 외 | view | 서버 렌더 | `.claude/lib/eroomlib/review_page.py:35-62` (Jinja 아님 — escape 관례만) | partial |
| `webapp/static/vendor/*` | asset | — | **없음** (vendoring 선례 없음) | none |
| `webapp/tests/conftest.py` · `test_*.py` | test | unit/integration | `test_bids.py:80-115,210-239` · `test_nvad.py` | role-match |
| `webapp/tests/fixtures/result_min.json` | fixture | — | `test_bids.py:235-239` `_write_ads` (인라인 픽스처) | partial |

---

## Pattern Assignments

### 1. `run_ads.py` 패치 (CLI 진입점, request-response)

**Analog: 자기 자신.** 새 플래그는 **기존 `cmd_apply`/`cmd_bids` 의 방어 수준을 그대로 복제**해야 한다.

**서브파서 등록 관례** (`run_ads.py:208-213`) — 헬프 문자열이 한국어 반말 명령형:
```python
    s = sub.add_parser("bids")
    s.add_argument("--run-dir")
    s.add_argument("--account", nargs="*")
    s.add_argument("--commit", action="store_true", help="실제로 입찰가를 바꾼다")
    s.add_argument("--revert", action="store_true",
                   help="직전 인상을 before_bids 백업으로 되돌린다(스펙 §4.3)")
```
→ `--only-ads` · `--preview-out` 을 **이 블록 끝에 두 줄로** 붙인다. 디스패치 dict(`run_ads.py:219-220`)에
`accounts` 키를 추가한다.

**파일 읽기 방어 패턴** (`run_ads.py:160-164`) — 돈이 나가는 명령은 읽기도 try-except 로 감싸고 **exit 1**:
```python
    # Important 10: cmd_apply 와 같은 수준으로 읽기를 보호한다 — 돈이 나가는 명령이다.
    try:
        result = json.loads(rp.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"result.json 읽기 실패: {type(e).__name__}: {e}")
        return 1
```
→ `_load_only_ads` 실패도 **이 모양 그대로**. 전량 폴백 금지(RESEARCH §1.3). 예외 문자열 포맷
`f"{type(e).__name__}: {e}"` 는 저장소 표준 관용구다 — `run_ads.py:78,107,130,137` · `bids.py:140,157,186,235,247` 에 9회 반복.

**스킵을 조용히 하지 않는다** (`run_ads.py:166-171`) — 새 `accounts` 서브커맨드가 존재하는 이유:
```python
    for alias, v in result.get("accounts", {}).items():
        acct = accts.get(alias)
        if not acct:
            # Important 2: 돈이 나가는 명령이니 자격증명 없어 건너뛴 계정도 로그에 남긴다
            print(f"[{alias}] 자격증명 없음 — 건너뛴다")
            continue
```

**`accounts` 서브커맨드가 베낄 자리** (`nvad.py:26-32`) — **화이트리스트 투영**, 시크릿은 애초에 안 담는다:
```python
def load_accounts():
    """자격증명 파일에서 계정 목록을 읽는다. 없으면 빈 리스트."""
    try:
        d = json.loads(CRED.read_text(encoding="utf-8"))
    except Exception:
        return []
    return d.get("accounts", []) if isinstance(d, dict) else d
```
→ `cmd_accounts` 는 `[{"alias":…, "customer_id":…}]` 만 `json.dumps` 해서 stdout 에 찍고 `return 0`.
**`api_key`·`secret_key` 키를 코드에 쓰지 마라** — 쓰는 순간 SAFE-03 이 구조적 보장에서 리뷰 대상으로 떨어진다.

**경로 규약** (`run_ads.py:42-57`) — 웹앱이 그대로 따라야 할 정본:
```python
def data_root():
    """경로를 코드에 박지 않는다 — workspace.toml 을 먼저 본다."""
    try:
        from eroomlib.config import cfg
        p = cfg("paths.data_root")
        if p:
            return Path(p).expanduser()
    except Exception:
        pass
    return Path.home() / "python_work" / "data"


def run_dir_of(name=None):
    d = data_root() / "naver-ads" / "runs" / (name or date.today().isoformat())
    d.mkdir(parents=True, exist_ok=True)
    return d
```

---

### 2. `bids.py` 패치 (service, batch + 외부쓰기)

**Analog: 자기 자신.** 필터의 **위치**가 전부다.

**가드 순서 — `update_streaks` 뒤** (`bids.py:143-160`):
```python
    # 지난 회차 인상의 결과를 먼저 반영한다 — 이게 판정보다 앞서야
    # "3주 연속 실패" 가 이번 회차 판정에 반영된다.
    # dry-run 은 메모리에서만 갱신하고 파일에 쓰지 않는다.
    update_streaks(led, {r["adId"] for r in rows}, recovered_ids, today, log=log)
    ...
    plans = [plan_raise(r, led, today=today) for r in rows]
```
→ `if only_ads is not None: rows = [...]` 는 `update_streaks` **다음**, `plans = [...]` **직전** 딱 한 줄
(RESEARCH §1.3 · CONTEXT 확정). 앞에 걸면 streak 카운팅이 조용히 멈춘다.

**`log=print` 주입이 이 파일 전체의 관례** (`bids.py:89,127,224` · `collect.py:67` · `reports.py:72`):
```python
def run_bids(acct, run_dir, rows, commit=False, log=print):
```
→ 새 kwarg 도 **`log` 뒤에** 붙여라(`only_ads=None`). 테스트가 `log=lambda *a, **k: None` 로 끄는 게
`test_bids.py:248,262` 의 실제 호출 방식이다. 웹앱 잡 엔진은 `log` 를 건드리지 않는다 — stdout 이 곧 진행로그다.

**dry-run / commit 분기 + 상위 10건 접기** (`bids.py:165-173`) — D-02 가 지적한 "표를 못 만드는" 지점:
```python
    log(f"[{alias}] 대상 {len(plans)}건 → " + " · ".join(f"{k} {v}" for k, v in counts.items()))
    for p in plans[:10]:
        log(f"    {p['action']:<10} {str(p['from']):>4}→{str(p['to']):<4} {p['title'][:30]}")
    if len(plans) > 10:
        log(f"    … 외 {len(plans)-10}건")

    if not commit:
        log("  (dry-run — --commit 을 주면 실제로 바꾼다)")
        return {"plans": plans, "counts": counts, "committed": 0}
```
→ **이 로그 출력은 그대로 둔다.** `--preview-out` 은 `plans` 전량을 별도 파일로 쓸 뿐이다.
같은 접기 관용구(`… 외 N건`)가 `run_revert:252-255` · `run_coupang.py:470-474` 에도 있다 — 화면에서도 같은 말투를 쓴다.

**항목 단위 결과를 다는 자리** (`bids.py:199-221`) — 현재 `ok`/`fail` 카운트만 세고 사유는 stdout 에만 있다:
```python
    ok = fail = 0
    try:
        for p in plans:
            if p["action"] != "인상":
                continue
            ad_obj = ad_by_id.get(p["adId"])
            if not ad_obj:
                fail += 1
                continue
            good, err = apply_raise(acct, ad_obj, p["to"])
            if good:
                ok += 1
                ledger.record_raise(led, p["adId"], today, p["from"], p["to"])
            else:
                fail += 1
                log(f"    ✗ {p['adId']} {err}")
            time.sleep(0.08)   # prune.delete_ads 와 같은 페이싱 — 초당 12건
    finally:
        # 중간에 끊겨도 이미 올린 것은 반드시 남긴다.
        # 안 남기면 다음 회차가 같은 상품 입찰가를 또 올린다.
        ledger.save(led_path, led)
```
→ `p["result"]`/`p["error"]` 키만 더한다(FLOW-05 · D-03 · D-10 · D-13 을 한 번에 푼다).
**`try/finally` 로 `ledger.save` 를 보장하는 구조는 건드리지 마라** — 이 파일의 핵심 안전장치다.

**되돌리기 필터가 붙을 자리** (`bids.py:250`):
```python
    targets = [ad_id for ad_id, attr in backup.items() if attr is not None]
```
→ `and (only_ads is None or ad_id in only_ads)` 를 같은 줄에 더한다. **백업 파일은 읽기만 한다**(D-13).

**건드리면 안 되는 것 — 백업 병합 규칙** (`bids.py:175-193`):
```python
    # Important 1: 기존 백업 키는 보존한 채 병합한다(덮어쓰지 않는다). … 같은 키는 먼저 것을 유지한다
    merged_bk = dict(existing_bk)
    for p in plans:
        if p["action"] == "인상" and p["adId"] not in merged_bk:
            merged_bk[p["adId"]] = ad_by_id.get(p["adId"], {}).get("adAttr")
```
→ `only_ads` 로 `rows` 가 줄면 `plans` 도 줄고, 따라서 **이번 백업에 안 담기는 adId 가 생긴다.**
기존 키는 보존되므로 안전하지만, 이게 D-12~D-14("이 작업분만 되돌리기")가 성립하는 근거다.

---

### 3. `webapp/board.py` (service, file-I/O → transform)

**Analog: `report_md.py` + `sheets_out.py`** — 둘 다 `result.json` 을 읽어 표로 만드는 기존 코드다. exact match.

**규칙별 컬럼 정의를 데이터로 둔다** (`sheets_out.py:28-48`) — ★ 보드 컬럼 구성이 베낄 정본:
```python
# 모든 탭의 앞 두 열은 회차·계정으로 고정한다. 코드가 붙이지 데이터가 정하지 않는다
PREFIX = ("회차", "계정")

# 규칙별 열 정의 (헤더, 접근키) — PREFIX 뒤에 붙는 것들만 적는다
COLS = {
    "①노출0": [("상품", "title"), ("광고그룹", "adGroup"),
               ("현재입찰", "bid"), ("그룹입찰따름", "useGroupBid"), ("소재ID", "adId")],
    "②썸네일교체": [("상품", "title"), ("노출", "imp"), ("클릭", "clk"),
                 ("CTR %", "ctr"), ("순위", "rank"), ("스토어상품ID", "mallProductId"), ("소재ID", "adId")],
    ...
}
```
→ **①에 `imp`/`clk` 가 없다는 사실이 이 표에 이미 박혀 있다.** Tabulator 컬럼 정의를 이 구조로 만들면
BOARD-01 의 빈칸이 설계상 정상값이 된다. 위험 1(`row.imp` 무조건 읽기)이 구조적으로 막힌다.

**누락 필드를 `.get(k, "")` 로만 만진다** (`report_md.py:17-40`):
```python
def _table(rows, cols, limit=None):
    """(헤더, 접근키) 목록으로 마크다운 표를 만든다."""
    rows = rows[:limit] if limit else rows
    if not rows:
        return "_해당 없음_\n"
    ...
    for r in rows:
        cells = []
        for _, k in cols:
            v = r.get(k, "")
            # bool 을 int 보다 먼저 본다 — 파이썬에서 bool 은 int 의 하위 타입이라
            # 순서를 바꾸면 True/False 가 1/0 으로 찍혀 사람이 못 읽는다
            if isinstance(v, bool):
                cells.append("예" if v else "아니오")
            elif isinstance(v, int):
                cells.append(f"{v:,}")
```
→ `useGroupBid`(bool) 렌더에 같은 함정이 있다. 보드에서도 **bool 을 int 보다 먼저 분기**해라.

**잘렸으면 잘렸다고 말한다** (`report_md.py:43-45`):
```python
def _count_label(n, limit):
    """헤더에 쓸 건수 표기. 표가 잘렸으면 잘렸다고 반드시 말한다."""
    return f"{n}건 중 상위 {limit}건" if limit and n > limit else f"{n}건"
```
→ D-07 "필터 전체 N건 선택" 배너 문구가 이 관례를 따른다.

**계정을 코드에 박지 않는 순회** (`report_md.py:57-59,73-75`) — BOARD-02 의 정본:
```python
    for alias, v in result.get("accounts", {}).items():
        r = v["rules"]
        # 규칙별 행을 합산하지 않는다 — 같은 소재가 ②와 ③에 동시에 들어가 두 번 세진다
        s = v.get("summary") or {}
```
→ 보드 필터의 계정 목록도 `result["accounts"]` 키에서만 온다. `sorted()` 로 순서를 준다.
**"규칙별 행을 합산하지 않는다"** 는 경고가 D-05(상품 단위 접기)에 그대로 적용된다 — 같은 소재가 ②③에
동시에 들어가므로, 접을 때 `imp` 를 규칙마다 더하면 두 번 세진다. RESEARCH §Pattern 2 의 `fold_products`
가 `p[f] = (p[f] or 0) + r[f]` 로 더하는 부분은 **이 함정에 걸려 있다 — 플래너가 규칙당 1회만 반영하도록 좁혀라.**

**판정행 스키마의 정본** (`ads_rules.py:34-57`) — 보드 컬럼은 여기서만 온다. 웹앱이 재계산 금지:
```python
def ad_info(ad, group_name, group_bid):
    """판정 결과 1행의 공통 필드."""
    return {
        "adId": ad["nccAdId"],
        "adGroup": group_name,
        "title": rd.get("productTitle") or "",
        "mallProductId": rd.get("mallProductId"),   # 썸네일 스킬 매칭 키
        "bid": effective_bid(ad, group_bid),
        "useGroupBid": bool(attr.get("useGroupBidAmt")),
        "groupBid": group_bid,
    }
```
```python
def effective_bid(ad, group_bid):
    """실제로 적용되는 입찰가.

    useGroupBidAmt=True 면 adAttr.bidAmt 는 잠자는 값이고 그룹 기본가가 적용된다.
    이걸 헷갈리면 입찰가를 올리려다 오히려 내리게 된다(실측: 그룹 70원 / 잠자던 값 50원).
    """
```
→ `ads_rules.py:22-31`. **웹앱은 `bid` 필드를 읽기만 한다.** BID-03 은 `from`/`to`/`useGroupBid`
(`bids.plan_raise:32-33`)로 이미 충족된다 — 예상 인상액 합계(BOARD-04)도 `to - from` 합이지 자체 계산이 아니다.

---

### 4. `webapp/jobs.py` (service, 잡 엔진)

**Analog 3개를 합성한다.** 단일 exact analog 는 없다.

**(a) Popen + 줄 단위 스트리밍** — `.claude/skills/sellerlife-keyword/scripts/run_all.py:33-48`:
```python
def sh(script, *args):
    """스크립트를 실행하고 stdout 을 그대로 흘리며 전체 출력을 반환."""
    cmd = [PY, os.path.join(SCRIPT_DIR, script), *[str(a) for a in args]]
    print(f"\n$ {script} {' '.join(str(a) for a in args)}\n{'-'*60}")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace",
                            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    lines = []
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        lines.append(line.rstrip("\n"))
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"{script} 실패 (exit {proc.returncode})")
    return lines
```
**베낄 것:** `stderr=STDOUT` 합류 · `text=True, encoding="utf-8", errors="replace"` ·
`env={**os.environ, ...}` 병합(환경 통째 교체 금지) · exit code 로 실패 판정.
**⚠ 베끼면 안 되는 것 (RESEARCH §5.1~5.3 과 정면충돌):**
| 여기 코드 | 웹앱에서는 |
|---|---|
| 파이프를 직접 읽음 | **로그파일로 리다이렉트하고 오프셋 tail** (브라우저 닫았다 재접속이 성립하려면) |
| `PYTHONIOENCODING` 만 | **`PYTHONUNBUFFERED=1` 추가** — 없으면 ENG-03 이 조용히 깨진다 |
| `start_new_session` 없음 | **`start_new_session=True`** — `uvicorn --reload` 가 자식을 죽인다 |
| 호출부 블로킹 | `create_job` 은 띄우고 즉시 `job_id` 반환 |

**(b) 체크포인트 저장 = 원자적 쓰기** — `detail_batch.py:59-66`:
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
같은 관용구가 `run_coupang.py:68-74` · `runner/onestep.py:244-255` · `eroomlib/snapshot.py:293`
· `bulsaja-shipping-cost/scripts/run_shipping.py:67` 등 저장소 전역 10곳에 있다. **targets/preview/result
파일도 이 방식으로 쓴다** — 반쪽 JSON 을 CLI 가 `--only-ads` 로 읽는 사고를 막는다.
`runner/onestep.py:252` 는 tmp 이름에 pid 를 넣는다(`f"{p}.{os.getpid()}.tmp"`) — 동시 실행 가능성이 있으면 이 변형을 써라.

**(c) 건건 즉시 append = 중복 방지 유일 방어선** — `run_coupang.py:77-94`:
```python
def _append_jsonl(path, rec):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
```
**`flush()` + `fsync()` 둘 다 있다.** append-only 잡 로그와 (Phase 2 의) 감사 로그가 이걸 그대로 쓴다.

**(d) 재개 판정 = 이미 한 것을 빼는 집합 연산** — `run_coupang.py:448-449`:
```python
    done = {r["원본pid"] for r in _read_jsonl(_p(args.run_dir, "copied.jsonl"))}
    todo = [c for c in cands if c["대표pid"] not in done]
```
그리고 `detail_batch.py:251-262`:
```python
            def need_submit(pid):
                v = status.get(pid, {})
                if args.force and v.get("status") == SKIP_STATUS:
                    return True
                if args.retry_failed and (is_failed(v.get("status", ""))
                                          or v.get("status") == "접수실패"):
                    return True
                return not v.get("taskId") and not is_done(v.get("status", ""))
```
→ jobs SQLite 의 `status` 컬럼(`running|done|failed|orphaned`)이 이 판정의 자리를 대신한다.
**Phase 1 은 CLI 의 ledger 쿨다운이 이미 중복 인상을 막으므로 잡 레벨 재개 로직을 새로 만들지 마라**(PROJECT.md 제약).

**(e) 건건 저장** — `detail_batch.py:306-311`:
```python
            for i, pid in enumerate(todo, 1):
                r = try_submit(pid, f"[{i}/{len(todo)}]")
                if r == "dup":
                    dup_queue.append(pid)
                save_json(status_path, status)
                time.sleep(args.sleep)
```
`[{i}/{len(todo)}]` 진행 태그 + `flush=True` 출력이 저장소의 진행로그 관례다(`detail_batch.py:274-275,342,359-360`).

**(f) 환경변수 주입 래퍼 — 토큰을 argv 에 안 싣는다** — `bulsaja-detail-page/scripts/run_yong.py:49-56`:
```python
        env = {
            **os.environ,
            "BULSAJA_MCP_URL": server["url"],
            "BULSAJA_MCP_TOKEN": auth,
            "PYTHONIOENCODING": "utf-8",
        }
        proc = subprocess.run(sys.argv[1:], env=env)
        sys.exit(proc.returncode)
```
docstring 에 **"토큰 값은 절대 출력하지 않는다"**(`run_yong.py:7`)가 명시돼 있다.
→ jobs 테이블의 `argv` 컬럼에 시크릿이 없는 이유가 이 관례다. 광고 CLI 는 시크릿을 `~/.eroom` 에서 직접
읽으므로 웹앱은 env 주입조차 필요 없다 — **더 안전한 쪽으로 이미 기울어 있다.**

---

### 5. `webapp/paths.py` (utility, file-I/O)

**Analog: `run_ads.py:42-57` (위 §1 발췌) + `.claude/lib/eroomlib/config.py:82-97`** — exact.

**루트 탐색 = `.claude` 앵커를 위로 올라가며 찾기** (`config.py:82-97`):
```python
def workspace_root(start=None):
    """`.claude` 디렉터리를 품은 조상 = 워크스페이스 루트. 못 찾으면 None."""
    d = os.path.dirname(os.path.abspath(start or __file__))
    while d and d != os.path.dirname(d):
        if os.path.isdir(os.path.join(d, ".claude")):
            return d
        d = os.path.dirname(d)
    return None


def _toml_path():
    p = os.environ.get("EROOM_WORKSPACE_TOML")
    if p:
        return p
    root = workspace_root()
    return os.path.join(root, "workspace.toml") if root else None
```
같은 while-loop 관용구가 `run_ads.py:32-39` · `sheets_out.py:17-24` · `run_coupang.py:30-42` 에 반복된다.
저장소 표준이다 — **절대경로를 박는 순간 다른 PC·배포본에서 조용히 폴백된다**(`run_ads.py:29-31` 주석).

**웹앱은 `eroomlib` 를 import 하지 않는다.** stdlib `tomllib` 로 같은 결과를 낸다(RESEARCH §3.3 실측).
`run_ads.py` 가 `sys.path.insert` 로 최상위 이름(`bids`·`collect`·`reports`)을 끌어오기 때문에,
웹앱 프로세스에 그 경로를 넣으면 stdlib 이 가려진다(RESEARCH §5.6 — 이번 리서치 중 실제 재현됨).

---

### 6. `webapp/settings.py` (config)

**Analog: `.claude/lib/eroomlib/config.py:32-76,135-154`** — role-match.

**DEFAULTS + 점 경로 조회 + `required=True` 로 조용한 폴백 차단**:
```python
def cfg(dotted, default=None, required=False):
    """`"drive.category_folder"` 처럼 점 경로로 값 하나를 꺼낸다.

    required=True 인데 값이 없거나 빈 문자열이면 KeyError — 배포본처럼 값이 비워진 환경에서
    "조용히 기본값으로 돌다가 남의 시트에 쓰는" 사고를 막는다.
    """
```
```python
        except Exception as e:
            # 설정이 깨졌으면 조용히 넘어가지 않는다 — 엉뚱한 시트에 쓰는 사고가 난다.
            raise RuntimeError(f"workspace.toml 파싱 실패({path}): {e}")
```
→ `config.py:126-128`. **D-08 의 "1회 실행 계정별 상한 1,500건"은 이 구조로 둔다** —
`DEFAULTS` 에 값을 두고 `workspace.toml` 이 덮는다. 화면·코드에 1500 을 박지 않는다.
`_deep_merge`(`config.py:100-108`)가 중첩 dict 를 재귀 병합하는 것도 그대로 쓸 수 있다.

---

### 7. `webapp/security.py` (middleware, request-response)

**Analog 없음 (웹 계층 부재).** 미들웨어·Origin 가드·부팅토큰은 RESEARCH §4.2~4.4 의 실측 통과본을 쓴다.

**단, 시크릿 스크러버(SAFE-03)에는 analog 가 있다** — `detail_batch.py:69-78`:
```python
def sanitize(obj, depth=0):
    """응답 구조 확인용 (값 축약, 토큰류 노출 방지)."""
    if depth > 3:
        return "..."
    if isinstance(obj, dict):
        return {k: sanitize(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(v, depth + 1) for v in obj[:3]] + (["..."] if len(obj) > 3 else [])
    s = str(obj)
    return s[:60] + ("..." if len(s) > 60 else "")
```
**에러 문자열도 이미 잘라 쓴다** — `bids.py:65,86`(`str(res)[:150]`) · `detail_batch.py:292,352`(`str(e)[:200]`,`[:120]`)
· `reports.py:52`(`str(job)[:120]`). **웹앱 에러 응답도 이 관례를 따른다** — 원문 예외를 통째로 화면에 띄우지 마라.

**HTML escape 관례** — `.claude/lib/eroomlib/review_page.py:35-54`:
```python
def img_tag(url, label, cls=""):
    """이미지 1장. 빈 url 이면 빈 문자열(호출부에서 분기하지 않게)."""
    if not url:
        return ""
    return (f'<div class="col {html.escape(cls, quote=True)}">'
            f'<img src="{html.escape(str(url), quote=True)}" loading="lazy">'
```
→ 저장소는 **`html.escape(..., quote=True)` 를 값마다 명시**한다. Jinja2 자동 이스케이프에 기대되,
`| safe` 를 쓰는 순간 이 관례를 깨는 것이다. 상품명에 중국어 원문·특수문자가 섞여 들어온다.

---

### 8. `webapp/logtail.py` (service, streaming)

**Analog 없음 (소비자 쪽).** 저장소에 오프셋 tail·SSE 코드가 없다. RESEARCH §5.3~5.4 를 쓴다.

**생산자 쪽 관례만 있다** — 로그 한 줄의 모양을 여기 맞춘다:
- `flush=True` 명시 출력: `detail_batch.py:274-275,281,342,359-360`
- 진행 태그 `[{i}/{n}]`: `detail_batch.py:307`
- 요약 센티널: `detail_batch.py:370` `###DETAIL###` · `run_all.py:51-57` `marker()` 로 `###NAME###` 다음 줄을 파싱
- **광고 CLI 에는 센티널이 없다**(RESEARCH §1.2). → **센티널을 새로 만들지 마라.** D-02/D-03 이 이미
  "stdout 파싱 금지, CLI 가 파일로 쓴다"로 정했다. 로그는 사람이 보는 용도로만 쓴다.

---

### 9. `webapp/argv.py` (model/builder, transform)

**Analog: `run_ads.py:198-220` (계약의 반대편) + `runner/onestep.py:365-371`** — role-match.

```python
def _sh(argv, dry=False):
    print(f"\n$ {os.path.basename(argv[0])} {' '.join(argv[1:])}\n{'-' * 56}")
    if dry:
        print("(dry-run — 실행하지 않음)")
        return 0
    proc = subprocess.run([PY, *argv],
                          env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    return proc.returncode
```
→ `runner/onestep.py:365-371`. **실행 전 argv 를 사람이 읽는 한 줄로 찍는 관례**가 저장소 전체에 있다
(`run_all.py:36` 도 동일). 웹앱은 이걸 **jobs 테이블 `argv` 컬럼 + 로그 첫 줄**로 옮긴다 — 감사와 재현이 공짜로 된다.
`PY = sys.executable`(`onestep.py:36`, `run_all.py:30`) 관례는 웹앱에서 **쓰면 안 된다** — `.venv-web` 이 잡힌다.
`PY_CLI = REPO/".venv/bin/python3"` 로 명시해야 CLI 가 selenium/openpyxl 을 찾는다(RESEARCH §5.5).

**caffeinate 프리픽스 자리**(Phase 2, ENG-06)를 `build()` 맨 앞에 끼울 수 있는 모양으로 만들어 둔다 — RESEARCH §5.8.

---

### 10. `webapp/tests/*` (test)

**Analog: `test_bids.py`** — role-match. 단 **프레임워크가 갈린다**(§Shared Patterns 참조).

**(a) 네트워크 없이 도는 단언** (`test_bids.py:2-5`):
```python
"""입찰 인상 가드레일 회귀 테스트 — 네트워크 없이 돈다.

여기서 틀리면 실제 광고비가 잘못 나간다. 가장 조심할 곳이다.
"""
```

**(b) 모듈 속성 몽키패치 + setUp/tearDown 복원** (`test_bids.py:83-104`) — ★ 웹앱 테스트가 그대로 따를 패턴:
```python
    def setUp(self):
        self._orig_call = bids.nvad.call
        self._orig_sleep = bids.time.sleep
        bids.time.sleep = lambda *_: None  # 테스트가 실제로 기다리지 않게 한다
        self.calls = []

    def tearDown(self):
        bids.nvad.call = self._orig_call
        bids.time.sleep = self._orig_sleep

    def test_429는_재시도후_성공한다(self):
        seq = [(429, "too many"), (200, {})]

        def fake_call(acct, method, path, params=None, body=None):
            self.calls.append(1)
            return seq.pop(0)

        bids.nvad.call = fake_call
```
→ **웹앱 테스트도 `bids.nvad.call` 을 이렇게 가로챈다.** RESEARCH §"크레딧·광고비를 쓰지 않고 쓰기 경로를
검증하는 방법"이 요구하는 것이 정확히 이 패턴이다. `time.sleep` 도 같이 끈다(`time.sleep(0.08)` × 1,200건).

**(c) tempfile run-dir 픽스처** (`test_bids.py:217-239`) — ★ `tmp_run_dir` conftest 픽스처의 원형:
```python
    def setUp(self):
        self._orig_call = bids.nvad.call
        self._orig_sleep = bids.time.sleep
        bids.time.sleep = lambda *_: None
        self.tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.tmp.name) / "runs" / "2026-08-30"
        acc_dir = self.run_dir / "accounts" / "cy728"
        acc_dir.mkdir(parents=True)
        (acc_dir / "stats_7d.json").write_text("{}", encoding="utf-8")
        self.ads_path = acc_dir / "ads.json"
        self._write_ads(100, 100)
        self.acct = {"alias": "cy728"}

    def tearDown(self):
        bids.nvad.call = self._orig_call
        bids.time.sleep = self._orig_sleep
        self.tmp.cleanup()

    def _write_ads(self, bid_a, bid_b):
        self.ads_path.write_text(json.dumps({"ads": [
            {"nccAdId": "a", "adAttr": {"bidAmt": bid_a, "useGroupBidAmt": False}},
            {"nccAdId": "b", "adAttr": {"bidAmt": bid_b, "useGroupBidAmt": False}},
        ]}), encoding="utf-8")
```
**`run_dir.parent.parent / "ledger"` 규약 때문에 `runs/<회차>` 2단을 반드시 만들어야 한다**(`bids.py:130`).
tmp 안에 `runs/2026-08-30` 을 쓰는 이유가 그것이다 — 빼먹으면 테스트가 실제 ledger 를 오염시킨다.

**(d) 픽스처는 최소 + 헬퍼 함수** (`test_bids.py:19-20`):
```python
def row(ad_id="a", bid=100, use_group=False, group_bid=70):
    return {"adId": ad_id, "bid": bid, "useGroupBid": use_group, "groupBid": group_bid, "title": "상품"}
```

**(e) 한국어 테스트 이름 + "왜 이 테스트가 있는지" 주석** (`test_bids.py:50-53`):
```python
    def test_오늘_이미_인상한_소재는_재수집후_또_올리지_않는다(self):
        # Critical 1 재현: bids --commit 이 100→110 올린 뒤 죽고, 운영자가
        # prep && run && bids --commit 으로 복구하면 새 스냅샷의 bid=110 을 보고
        # 계획을 세운다 — today 를 넘기지 않으면 110→120 으로 또 올라간다.
```
→ RESEARCH 의 Test Map 이 이미 한국어 이름을 쓰고 있다(`test_only_ads_없이_부르면_필터_전과_동일`). 일관된다.

**(f) 회귀 증명 — 기존 호출부가 안 깨진다** (`test_bids.py:248,262`):
```python
        bids.run_bids(self.acct, self.run_dir, rows, commit=True, log=lambda *a, **k: None)
```
`only_ads` 기본값이 `None` 이라 이 호출은 그대로 통과한다. **패치 커밋에 기존 테스트 전량 통과를 같이 남겨라**
(RESEARCH §1.3 — 100개 통과 확인됨).

---

### 11. `webapp/main.py` · `webapp/routes/*` · `webapp/templates/*` · `webapp/static/vendor/*`

**Analog 없음.** 이 저장소에 웹 계층이 존재하지 않는다(검증: `grep -rln "fastapi|jinja2|uvicorn" --include=*.py .` → 0건,
`find . -name "*.html"` → 스킬 산출물·크롬 프로필뿐, 템플릿 없음).

플래너는 RESEARCH.md 의 다음 절을 **그 자리의 정본**으로 써라:
- §4.2~4.4 — Host/Origin 가드 + 부팅토큰 (이 맥북에서 curl 6케이스 통과 실측)
- §"보안 3층 조립 (실측 통과본)" · §"자식 띄우기" · §"오프셋 tail" · §"Tabulator 선택 모델" · §"미리보기↔실행 diff"
- §5.7 — SQLite 잡 레지스트리 DDL

다만 **한국어 docstring·`try-except`·에러 축약·경로 비하드코딩은 이 문서 §Shared Patterns 가 그대로 적용된다.**
analog 가 없다는 건 "구조를 새로 짠다"는 뜻이지 "관례를 버린다"는 뜻이 아니다.

---

## Shared Patterns

### S-1. 한국어 docstring 은 "무엇"이 아니라 "왜"를 적는다
**Source:** 저장소 전역. 대표 발췌 `ads_rules.py:22-27` · `bids.py:89-104` · `ledger.py:54-67` · `config.py:4-10`
**Apply to:** 모든 신규 파일
```python
def update_streaks(led, zero_ids, recovered_ids, run_date, log=print):
    """지난 회차에 올린 소재가 이번에도 노출 0인지 보고 연속 실패를 갱신한다.

    **이 함수가 없으면 streak 이 영원히 0 이라 "3주 연속 올렸는데도 노출 0이면 중단"
    규칙이 실전에서 절대 발동하지 않는다.** …
    """
```
관례: ① 한 줄 요약 ② 빈 줄 ③ **실측 날짜와 함께 근거**(`(2026-08-27 실측)`) ④ `Critical N`/`Important N`/`Minor N`
번호로 리뷰 지적을 추적. 신규 웹앱 코드도 **Pitfall 번호**(RESEARCH §Pitfall 1~9)를 이 자리에 인용해라.

### S-2. `try-except` 는 두 종류다 — 폴백이냐 중단이냐
**Source:** `ledger.py:17-22` (폴백) vs `run_ads.py:160-164` (중단)
```python
def load(path):
    """이력을 읽는다. 없거나 깨졌으면 빈 dict — 첫 회차도 그냥 돈다."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
```
```python
    except Exception as e:
        print(f"result.json 읽기 실패: {type(e).__name__}: {e}")
        return 1
```
**판별 기준(저장소가 실제로 쓰는 것): 그 실패가 돈·크레딧·되돌릴 수 없는 쓰기로 이어지느냐.**
`--only-ads` 읽기 실패 → **중단**(5건 고른 줄 알았는데 2,242건이 올라간다). run-dir 스캔 실패 → 폴백 가능.
예외 문자열은 항상 `f"{type(e).__name__}: {e}"`.

### S-3. 경로는 절대 박지 않는다
**Source:** `run_ads.py:29-51` · `config.py:82-97` · `run_coupang.py:30-42` · `sheets_out.py:16-24`
**Apply to:** `webapp/paths.py` · `webapp/settings.py` · 모든 테스트
```python
# eroomlib 찾기 — 스크립트 위치에서 위로 올라가며 lib/eroomlib 를 찾는다.
# 절대경로를 박으면 다른 PC·배포본에서 조용히 폴백돼 workspace.toml 이 영영 안 읽힌다
```
→ `run_ads.py:29-31`. **반례가 저장소에 있다:** `detail_batch.py:46` 이
`SKILL_SCRIPTS = r"C:\Users\workspace\.claude\skills\..."` 를 박아 이 맥북에서 안 돈다.
**그건 베끼지 마라.** 그리고 `nvad.py:21` 의 `CRED = Path.home()/".eroom"/"naver-ads.json"` 은
**웹앱이 두 번째로 갖지 마라** — `accounts` 서브커맨드가 존재하는 이유다(RESEARCH §3.4).

### S-4. 원자적 쓰기 (tmp → `os.replace`)
**Source:** `run_coupang.py:68-74` · `detail_batch.py:59-66` · `onestep.py:244-255` (전역 10곳)
**Apply to:** targets/preview/result 파일 · jobs 부수 산출물
```python
def _dump(path, obj):
    """원자적 쓰기 — 중간에 끊겨도 반쪽 파일이 남지 않는다."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
```
**`ensure_ascii=False` 는 예외 없이 전부 붙는다** — 한국어 상품명이 `\uXXXX` 로 깨지면 사람이 못 읽는다.

### S-5. append-only + `flush` + `fsync`
**Source:** `run_coupang.py:77-83`
**Apply to:** `webapp-logs/<job_id>.log` · (Phase 2) 감사 로그 JSONL
**근거 문장** (`run_coupang.py:14-15`): *"중복 방지 옵션이 없으므로 `copied.jsonl` 이 같은 상품을
두 번 복사하지 않게 막는 **유일한 방어선**이다 — 건건 즉시 append 한다."*

### S-6. `log=print` 주입
**Source:** `bids.py:89,127,224` · `collect.py:67` · `reports.py:72` · `prune.run_prune`
**Apply to:** CLI 패치(새 kwarg 는 `log` 뒤에) · 웹앱 순수 함수(`board.fold_products` 등은 로그를 안 받는다)
테스트는 `log=lambda *a, **k: None` 로 끈다(`test_bids.py:248`).

### S-7. 시크릿은 프로세스에 안 들어오는 게 최선, 들어오면 화이트리스트 투영
**Source:** `nvad.py:26-32,41-51` · `run_yong.py:7,49-56` · `detail_batch.py:69-78`
**Apply to:** `webapp/security.py` · `webapp/argv.py` · jobs `argv` 컬럼 · 모든 에러 응답
- `nvad.headers()` 는 시크릿으로 서명만 하고 **어디에도 찍지 않는다**
- 에러는 항상 잘라서: `str(res)[:150]` / `str(e)[:200]`
- 화면·로그·템플릿 어디에도 `api_key`·`secret_key` 문자열이 없어야 한다(SAFE-03)

### S-8. 잘린 표시는 반드시 말한다 / 건수를 항상 먼저 보여준다
**Source:** `report_md.py:43-45` · `bids.py:165-169` · `run_coupang.py:459,470-474` · `detail_batch.py:263-265`
```python
            est = len(todo) * args.pages * per_credit
            print(f"접수 대상 {len(todo)}건 × 최대 {args.pages}장 "
                  f"× {per_credit}크레딧 = 예상 최대 {est}크레딧")
```
→ `detail_batch.py:263-265`. **BOARD-04("선택 건수 + 예상 인상액 합계가 항상 보인다")가 요구하는 문장이
이 저장소에 이미 이 모양으로 있다.** 크레딧 자리를 "예상 인상액 합계"로 바꾸면 그대로다.

### S-9. 읽기 전용 단계와 쓰기 단계를 문서 첫머리에서 갈라 적는다
**Source:** `run_coupang.py:3-13` · `run_ads.py:3-11`
```
    prep    주문시트 12탭 → 코드별 실적·배송비 원장          [읽기]
    ...
    apply   쿠팡 마켓그룹으로 복사                          [쓰기 — --commit 필요]

**S6(apply) 이전은 전부 읽기 전용이라 언제 끊겨도 손실이 0이다.**
```
→ D-15("새로 수집" 버튼이 안전한 대상으로 엔진을 먼저 검증)의 논리가 이 관례와 같다.
**`webapp/main.py` docstring 을 이 모양으로 시작해라** — 어떤 라우트가 쓰기인지 한눈에 보인다.

---

## No Analog Found

| 파일 | Role | Data Flow | 이유 |
|---|---|---|---|
| `webapp/main.py` | config/조립 | — | 저장소에 ASGI/WSGI 앱이 없다. FastAPI 미설치(`.venv` site-packages 48항목, FastAPI 없음) |
| `webapp/routes/board.py` · `routes/jobs.py` · `routes/health.py` | controller | request-response · SSE | HTTP 라우터 자체가 없다 |
| `webapp/security.py` (미들웨어 부분) | middleware | request-response | Host/Origin/토큰 가드 선례 없음 → RESEARCH §4.2~4.4 실측본 사용 |
| `webapp/logtail.py` | service | streaming | 오프셋 tail·SSE 선례 없음 → RESEARCH §5.3~5.4 |
| `webapp/templates/*.html` | view | 서버 렌더 | Jinja2 템플릿 0개. `review_page.py` 는 f-string HTML 조립이라 구조는 다름(escape 관례만 이식) |
| `webapp/static/vendor/*` | asset | — | 프런트 자산 vendoring 선례 없음 |

---

## ⚠ Planner 가 반드시 결정해야 할 관례 충돌

### C-1. 테스트 프레임워크: 저장소는 `unittest`, RESEARCH 는 `pytest`
- 저장소 테스트 20+개가 전부 stdlib `unittest` + `if __name__ == "__main__": unittest.main(verbosity=2)`
  (`test_bids.py` · `test_nvad.py:58-59` · `eroomlib/test_*.py`)
- `.venv/lib/python3.12/site-packages` 에 **pytest 없음** (확인: grep 0건). 실행법도
  `.venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/test_nvad.py` 로 docstring 에 박혀 있다(`test_nvad.py:4`)
- RESEARCH Validation Architecture 는 `.venv-web` 에 pytest 를 깔고 `pytest webapp/tests -x -q` 를 쓴다

**권고:** pytest 는 unittest 클래스를 그대로 수집하므로 **CLI 패치 회귀는 `test_bids.py` 에 unittest 스타일로
추가**(기존 실행법 무변경), **웹앱 신규 테스트만 `.venv-web` + pytest**. 두 런타임이 이미 갈려 있으므로
(`.venv` = CLI, `.venv-web` = 웹앱) 테스트 도구가 갈리는 것도 같은 경계다. 플래너가 확정해라.

### C-2. `fold_products` 의 지표 합산이 `report_md.py:59` 경고와 충돌
RESEARCH §Pattern 2 는 규칙을 순회하며 `p[f] = (p[f] or 0) + r[f]` 로 더한다. 그런데
`report_md.py:59` 가 명시한다: *"규칙별 행을 합산하지 않는다 — 같은 소재가 ②와 ③에 동시에 들어가 두 번 세진다."*
**같은 (계정, adId) 가 ②③④⑤ 에 중복 등장하므로, 접기에서도 `imp`/`clk` 가 중복 가산된다.**
→ 플래너는 접기를 **adId 단위로 먼저 dedupe 한 뒤 상품으로 접도록** 좁혀라. 테스트 이름 제안:
`test_같은_소재가_두_규칙에_있어도_노출이_두번_세지지_않는다`.

### C-3. `run_all.py` 의 파이프 직독을 베끼면 ENG-03 이 깨진다
유일한 Popen analog(`run_all.py:37-44`)가 **파이프를 직접 읽는다.** 이건 "브라우저 닫았다 재접속"과
양립하지 않는다(STACK.md §핵심결정 3). 플래너는 이 analog 를 **argv/env/인코딩 관례 출처로만** 인용하고,
로그 경로는 **파일 리다이렉트 + 오프셋 tail** 로 못박아라.

---

## Metadata

**Analog search scope:**
`.claude/skills/naver-ads-weekly/scripts/` (전량) ·
`.claude/skills/bulsaja-detail-page/scripts/` · `.claude/skills/coupang-candidates/scripts/` ·
`.claude/skills/sellerlife-keyword/scripts/` · `.claude/lib/eroomlib/` · `.claude/lib/eroomlib/runner/`

**Files read (full or targeted):** `run_ads.py`(224줄, 전량) · `bids.py`(282줄, 전량) · `ads_rules.py`(123줄, 전량) ·
`nvad.py`(90줄, 전량) · `collect.py`(96줄, 전량) · `ledger.py`(114줄, 전량) · `reports.py`(88줄, 전량) ·
`report_md.py`(1-80) · `sheets_out.py`(1-60) · `test_bids.py`(1-120, 210-270) · `test_nvad.py`(59줄, 전량) ·
`detail_batch.py`(1-120, 210-377) · `run_yong.py`(63줄, 전량) · `run_coupang.py`(1-100, 441-520) ·
`run_all.py`(1-70) · `eroomlib/config.py`(182줄, 전량) · `eroomlib/review_page.py`(1-62) ·
`eroomlib/runner/onestep.py`(1-40, 220-260, 360-380) · `eroomlib/runner/approval_log.py`(1-50)

**Negative searches (analog 부재의 근거):**
- `grep -rln "fastapi\|jinja2\|uvicorn" --include="*.py" .` → **0건**
- `grep -rn "Popen" --include="*.py" .claude/` → **4건** (webdriver·cookie_extractor·aside_category·run_all) — 잡 엔진 analog 는 `run_all.py` 뿐
- `grep -rn "start_new_session\|PYTHONUNBUFFERED" --include="*.py" .claude/` → **0건**
- `find . -name "pytest.ini" -o -name "conftest.py"` → **0건**
- `ls .venv/lib/python3.12/site-packages | grep -iE "pytest|fastapi|jinja|starlette"` → **0건**

**Pattern extraction date:** 2026-09-20
