# 소싱 파이프라인 1단계(장부·중복 제거·재수확 파일럿) 실행 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 본 상품·마켓·타오바오 장부 세 개를 만들고, 기존 검수 흐름 앞뒤에 중복 제거와 장부 기록을 끼운 뒤, 마켓 2,000개 3일베스트 파일럿을 돌려 재수확 수율을 숫자로 낸다.

**Architecture:** 기존 `sourcing-inspect` 스킬의 run-dir 흐름(fetch → prep → batch → 팬아웃 → merge → trash/match/collect)은 그대로 두고, 그 앞(네이버 번호 중복)·중간(타오바오 번호 중복)·뒤(장부 기록)에 독립 스크립트 세 개를 붙인다. 중복 판정은 `dup_verdicts.json` 한 파일로 넘겨 `prep`이 대상에서 빼고 `merge`가 drop으로 합치므로 휴지통 반영은 기존 `apply_sourcing.py trash`가 그대로 한다. 장부는 로컬 jsonl/txt, 정본은 디스크.

**Tech Stack:** Python 3(`.venv/bin/python3`), 표준 라이브러리 + 기존 `requests`. 테스트는 기존 방식(pytest 없이 `check()` 로 실행하는 스크립트).

**Spec:** `docs/superpowers/specs/2026-11-08-sourcing-pipeline-design.md`

**이 계획의 범위(1단계)와 다음 계획:** 설계서는 서브시스템 네 개다. 이 계획은 ①장부+중복 제거+보고+파일럿 측정만 다룬다. ②소싱기 화면 자동 조작(Playwright: 수집사이트 내보내기·캠페인 생성·ID 읽기·로그인 유지), ③무인 스케줄(일요일 23:00 끊기·수집 완료 후 자동 흐름·카톡 보고·타오바오 장부 야간 채우기·옛 9,398개 재검수), ④공급원 D(3만~5만 원 전체 이력)는 각각 별도 계획으로 쓴다. 파일럿 캠페인은 이번엔 용팀장이 화면에서 만든다(설계서 7절의 예외). ③의 가장 큰 미결은 2차 AI 판정이 Claude 세션의 Workflow(inspect-fanout)로 돌아 무인 실행 경로가 아직 없다는 점이다 — 2단계 계획에서 푼다.

## Global Constraints

- 코드는 Python, 한국어 주석, 바깥 I/O는 try-except. 불사자 쓰기는 `apply_sourcing.py` 경로만 쓴다(설계서 9절).
- 네이버에 직접 접속하지 않는다. 소싱기가 대신 한다(설계서 3절).
- 장부 위치 `~/python_work/data/sourcing-pipeline/`. 파일명 `markets.jsonl` · `seen_products.jsonl` · `seen_taobao.txt`(설계서 5절). 불사자 내부 번호(`U01M…` 등 숫자 아닌 것)는 `internal_ids.txt`로 분리 보관.
- 중복 휴지통 사유는 정확히 `DUP_SEEN`(네이버 번호) · `DUP_TAOBAO`(타오바오 번호). 휴지통 대장(`trash_ledger`)에 남는다.
- 캠페인 조건: 파일럿·재수확 = 3일베스트, 3만~50만 원, 마켓당 100개. 캠페인 이름 `R-YYMMDD-파일럿3일`.
- 파일럿 대상 2,000 = 28765 캠페인(`kwy9jllI5NICgPo`)에서 상품을 낸 마켓 중 상품 수 상위 1,000 + 나머지에서 무작위 1,000(seed 20261110). 두 묶음을 따로 집계한다.
- 월 공급 목표 2차 통과 140,000. 보고서에 이 숫자와의 차이를 반드시 적는다.
- run-dir 는 이름만 주면 `~/python_work/data/sourcing-inspect/runs/<이름>`(기존 `resolve_run_dir`).

## Review Focus

- **네이버 번호가 비었거나 숫자가 아닌 상품**(스냅샷 `productId` 가 `None`·`''`·`U01M…`) → 중복 아님으로 통과시키고 장부에도 넣지 않는다. 죽지 않는다. → Task 1 테스트 `is_naver_pid`, Task 3 테스트 "숫자 아닌 번호는 건너뜀".
- **같은 마켓 주소의 표기 변형**(`http://`, 끝 슬래시, 대문자, `m.smartstore.naver.com`) → 같은 slug 로 합쳐진다. → Task 1 테스트 `mall_slug`.
- **아직 수집이 시작 안 된 캠페인**(상품 0건이 계속) → 완료로 보지 않는다. 1건 이상이면서 변화가 없을 때만 완료. → Task 4 테스트 "0건 안정은 완료 아님".
- **한 스냅샷 안에 같은 네이버 번호가 두 번**(3일베스트가 재판매 상품을 또 담은 경우) → 첫 번째만 살리고 나머지는 `DUP_SEEN`(note "같은 회차 중복"). → Task 3 테스트 "회차 내 중복".
- **장부 파일이 없는 첫 실행** → 빈 장부로 동작하고 쓰기 때 폴더·파일을 만든다. → Task 1 테스트 "없는 파일은 빈 집합".

---

### Task 1: 장부 모듈 `ledger.py`

**Files:**
- Create: `.claude/skills/sourcing-inspect/scripts/ledger.py`
- Test: `.claude/skills/sourcing-inspect/scripts/test_ledger.py`

**Interfaces:**
- Produces:
  - `DATA_DIR = os.path.expanduser("~/python_work/data/sourcing-pipeline")`, 상수 `MARKETS`, `SEEN_PRODUCTS`, `SEEN_TAOBAO`, `INTERNAL_IDS`(각 파일 절대경로)
  - `mall_slug(url: str | None) -> str | None` — `https://smartstore.naver.com/clover131/` → `clover131`; `m.smartstore.naver.com/X` → `X`; 스마트스토어가 아니면 `host/path` 소문자(끝 슬래시 제거); 빈 값은 `None`
  - `is_naver_pid(pid) -> bool` — 문자열로 바꿔 숫자만 6자리 이상이면 True
  - `load_seen_products(path=SEEN_PRODUCTS) -> set[str]`, `append_seen_products(rows: list[dict], path=SEEN_PRODUCTS) -> int` (row = `{"pid","campaign","date","verdict"}`, 이미 있는 pid 는 건너뛰고 추가한 수를 돌려줌)
  - `load_seen_taobao(path=SEEN_TAOBAO) -> set[str]`, `append_seen_taobao(ids: Iterable, path=SEEN_TAOBAO) -> int` (str 로 정규화, 중복 제외)
  - `load_markets(path=MARKETS) -> dict[str, dict]` (slug → row), `upsert_markets(rows: dict[str, dict], path=MARKETS) -> None` (전체 다시 쓰기). row 키: `slug, url, first_seen, full_run(None|{"campaign","date"}), last_3day(None|date), products(int), empty(bool)`
  - `taobao_item_id(item: dict) -> str | None` — `apply_sourcing.collect_item` 과 같은 경로(`taobaoResult[0].item.itemId`)

- [ ] **Step 1: 실패하는 테스트 작성** — `test_ledger.py`, 기존 `test_run_inspect.py` 의 `check()` 방식. `tempfile.TemporaryDirectory()` 안에서:

```python
check("slug 표기 변형 통일", mall_slug("HTTP://smartstore.naver.com/Clover131/") == "clover131"
      and mall_slug("https://m.smartstore.naver.com/clover131") == "clover131"
      and mall_slug("https://brand.naver.com/abc/") == "brand.naver.com/abc" and mall_slug("") is None)
check("네이버 번호 판별", is_naver_pid("10162030898") and is_naver_pid(10162030898)
      and not is_naver_pid("U01M123") and not is_naver_pid(None) and not is_naver_pid(""))
check("없는 파일은 빈 집합", load_seen_products(p) == set() and load_seen_taobao(t) == set() and load_markets(m) == {})
check("append 는 중복 제외·개수 반환", append_seen_products([{"pid":"1","campaign":"c","date":"d","verdict":"pass"}]*2, p) == 1
      and append_seen_products([{"pid":"1",...}], p) == 0 and load_seen_products(p) == {"1"})
check("타오바오 int→str", append_seen_taobao([123, "123", "456"], t) == 2 and load_seen_taobao(t) == {"123","456"})
check("markets 왕복", (upsert_markets({"a": row}, m), load_markets(m)["a"]["products"] == 3)[1])
check("taobao_item_id", taobao_item_id({"taobaoResult":[{"item":{"itemId":77}}]}) == "77" and taobao_item_id({"taobaoResult":None}) is None)
```

- [ ] **Step 2: 실패 확인** — `.venv/bin/python3 .claude/skills/sourcing-inspect/scripts/test_ledger.py` → `ModuleNotFoundError: ledger`
- [ ] **Step 3: `ledger.py` 구현** — 위 시그니처 그대로. jsonl 은 한 줄 한 행, txt 는 한 줄 한 번호. 쓰기 전에 `os.makedirs(DATA_DIR, exist_ok=True)`.
- [ ] **Step 4: 통과 확인** — 같은 명령, 마지막 줄 `FAILED: []` 또는 전부 `ok`.
- [ ] **Step 5: 커밋** — `git add .claude/skills/sourcing-inspect/scripts/ledger.py .claude/skills/sourcing-inspect/scripts/test_ledger.py && git commit -m "feat(sourcing-pipeline): 장부 모듈(마켓·네이버·타오바오)"`

### Task 2: 장부 초기값 생성 `ledger_init.py`

**Files:**
- Create: `.claude/skills/sourcing-inspect/scripts/ledger_init.py`

**Interfaces:**
- Consumes: Task 1 전부.
- Produces: 명령 `ledger_init.py [--runs-dir ~/python_work/data/sourcing-inspect/runs] [--seen-markets ~/python_work/data/sourcing-pipeline/seen_markets.txt] [--market-list <28765 입력 파일>]`. 실행 결과 `seen_products.jsonl`, `seen_taobao.txt`, `internal_ids.txt`, `markets.jsonl` 생성, 요약 한 줄 출력.

- [ ] **Step 1: 구현** — `runs/*/snapshot.json` 전부를 순회(파일 없으면 건너뜀, 깨진 JSON 은 경고 후 건너뜀).
  - 상품: `is_naver_pid(productId)` 면 `seen_products` 행(campaign = `campaignId`, date = `timestamp[:10]`, verdict = 그 run-dir 의 `verdicts.json` 에 있으면 그 값, 없으면 `"unjudged"`). 아니면 `internal_ids.txt` 에 `id` 기록.
  - 타오바오: `taobao_item_id(item)` 가 있으면 `seen_taobao` 에.
  - 마켓: `mall_slug(mallUrl)` 별 상품 수 집계. `campaignId == "kwy9jllI5NICgPo"` 또는 `"YWfs4MpPnVWHzYW"` 면 `full_run = {"campaign": id, "date": timestamp[:10]}`.
  - `seen_markets.txt`(한 줄 한 URL)와 `--market-list`(있으면) 의 마켓은 상품 0개로 추가(`empty=True`, `full_run` 은 28765 로 표시). 이미 있으면 상품 수 유지.
  - 멱등: 두 번 돌려도 수가 안 변한다(append 함수가 중복 제외).
- [ ] **Step 2: 실행** — `.venv/bin/python3 .claude/skills/sourcing-inspect/scripts/ledger_init.py`
  Expected 출력 예: `[ledger_init] 네이버 ≈291,000 / 내부번호 ≈170,000 / 타오바오 ≥ 100,000 / 마켓 ≥ 16,459(상품 있음 ≈16,227)`. 네이버 수가 20만 미만이거나 타오바오가 5만 미만이면 멈추고 원인을 보고한다(스냅샷 경로 문제).
- [ ] **Step 3: 멱등 확인** — 한 번 더 실행 → 같은 숫자, `추가 0`.
- [ ] **Step 4: 커밋** — `git commit -m "feat(sourcing-pipeline): 장부 초기값 생성(스냅샷 전부)"`. 장부 데이터 파일은 커밋하지 않는다(홈 폴더).

### Task 3: 중복 제거 단계 `dedup_stage.py` + 기존 흐름 연결

**Files:**
- Create: `.claude/skills/sourcing-inspect/scripts/dedup_stage.py`
- Modify: `.claude/skills/sourcing-inspect/scripts/run_inspect.py` — `cmd_prep`(대상 제외), `cmd_merge`(drop 합치기)
- Test: `.claude/skills/sourcing-inspect/scripts/test_dedup_stage.py`, `test_run_inspect.py` 에 1건 추가

**Interfaces:**
- Consumes: Task 1 `load_seen_products`, `load_seen_taobao`, `is_naver_pid`, `taobao_item_id`.
- Produces:
  - 순수 함수 `judge_naver(items: list[dict], seen: set[str]) -> dict[str, dict]` — `{문서id: {"verdict":"drop","reason":"DUP_SEEN","note":"장부" | "같은 회차 중복","by":"ledger"}}`. 회차 내 중복은 첫 등장만 살림.
  - 순수 함수 `judge_taobao(items, seen: set[str]) -> dict[str, dict]` — reason `DUP_TAOBAO`. 타오바오 번호 없는 상품은 건너뜀(그건 기계 NO_MATCH 몫).
  - 명령 `dedup_stage.py naver|taobao --run-dir R` → `<R>/dup_verdicts.json` 에 **합쳐서** 저장(기존 내용 유지, 키 덮어쓰기), 출력 `[dedup] naver 대상 N건 중 중복 M건(장부 a, 회차내 b)`.
  - `run_inspect.cmd_prep`: `<R>/dup_verdicts.json` 이 있으면 그 id 를 `targets` 에서 제외하고 `[prep] 중복 제외 N건` 출력.
  - `run_inspect.cmd_merge`: `dup_verdicts.json` 항목을 verdicts 에 추가(이미 판정이 있는 id 는 기존 판정 유지). 요약 출력에 `중복 N` 추가.

- [ ] **Step 1: 실패하는 테스트** — `test_dedup_stage.py`:

```python
items = [{"id":"a","productId":"1"},{"id":"b","productId":"2"},{"id":"c","productId":"1"},{"id":"d","productId":"U01M9"},{"id":"e","productId":None}]
r = judge_naver(items, {"2"})
check("장부 중복", r["b"]["reason"] == "DUP_SEEN" and r["b"]["note"] == "장부")
check("회차 내 중복은 두 번째만", "a" not in r and r["c"]["note"] == "같은 회차 중복")
check("숫자 아닌 번호는 건너뜀", "d" not in r and "e" not in r)
TB = lambda i: {"taobaoResult":[{"item":{"itemId":i}}]}
r = judge_taobao([{"id":"x",**TB(5)},{"id":"y",**TB(6)},{"id":"z","taobaoResult":[]}], {"5"})
check("타오바오 중복", set(r) == {"x"} and r["x"]["reason"] == "DUP_TAOBAO")
```
  `test_run_inspect.py` 에 추가: 임시 run-dir 에 `snapshot.json`(3건) + `dup_verdicts.json`(1건) 두고 `select_targets` 결과에 prep 제외 로직을 흉내 낸 헬퍼 `exclude_dups(targets, run_dir)` 가 2건을 돌려주는지. (`cmd_prep` 안에서 이 헬퍼를 쓰도록 구현한다.)
- [ ] **Step 2: 실패 확인** — 두 테스트 파일 실행, `ModuleNotFoundError` / `ImportError: exclude_dups`.
- [ ] **Step 3: 구현** — `dedup_stage.py`(위 함수 + main), `run_inspect.py` 에 `exclude_dups(targets, run_dir) -> list` 추가해 `cmd_prep` 의 `targets` 계산 직후 호출, `cmd_merge` 끝에서 `dup_verdicts.json` 합치기.
- [ ] **Step 4: 통과 확인** — `test_dedup_stage.py`, `test_run_inspect.py`, `test_rules.py` 전부 ok.
- [ ] **Step 5: 기존 회귀 확인** — 기존 run-dir 하나(`1107_revive38`)에 `merge` 를 다시 돌려 verdicts 수가 변하지 않는지 확인(dup 파일이 없으면 동작 동일).
- [ ] **Step 6: 커밋** — `git commit -m "feat(sourcing-inspect): 장부 기반 중복 제거 단계(DUP_SEEN·DUP_TAOBAO)"`

### Task 4: 수집 완료 감지 `campaign_watch.py`

**Files:**
- Create: `.claude/skills/sourcing-inspect/scripts/campaign_watch.py`
- Test: `.claude/skills/sourcing-inspect/scripts/test_campaign_watch.py`

**Interfaces:**
- Consumes: `sourcing_api.fetch_products`, `sourcing_api.load_token`, `run_inspect._save`/`_p`/`resolve_run_dir`.
- Produces:
  - 순수 함수 `is_complete(history: list[int], stable: int) -> bool` — 마지막 `stable`개 값이 모두 같고 0보다 크면 True.
  - 명령 `campaign_watch.py --campaign ID --run-dir R [--interval 600] [--stable 3] [--max-hours 48]` → 주기적으로 상품 수를 `<R>/watch.log` 에 적고, 완료되면 `<R>/snapshot.json`·`run_meta.json`(`{"campaign","count","completed_at"}`) 저장 후 종료코드 0. 401 이면 종료코드 2 + 안내문. `--max-hours` 넘으면 종료코드 3.

- [ ] **Step 1: 실패하는 테스트**

```python
check("0건 안정은 완료 아님", not is_complete([0,0,0], 3))
check("3회 같으면 완료", is_complete([10, 50, 50, 50], 3))
check("아직 늘면 미완료", not is_complete([10, 50, 60], 3) and not is_complete([50, 50], 3))
```
- [ ] **Step 2: 실패 확인** → `ModuleNotFoundError`.
- [ ] **Step 3: 구현** — 메인 루프는 `time.sleep(interval)`; 네트워크 예외는 로그만 남기고 다음 주기로.
- [ ] **Step 4: 통과 확인.**
- [ ] **Step 5: 실연 확인** — 지금 돌아가는 캠페인 ID 가 없으면 `--campaign kwy9jllI5NICgPo --interval 5 --stable 2 --run-dir /tmp/watch_test` 로 돌려 두 번째 조회에서 완료(이미 끝난 캠페인이라 수가 같음)로 끝나는지 본다. 토큰 401 이면 `web_token.py` 먼저.
- [ ] **Step 6: 커밋** — `git commit -m "feat(sourcing-inspect): 캠페인 수집 완료 감지"`

### Task 5: 장부 기록 `ledger_commit.py`

**Files:**
- Create: `.claude/skills/sourcing-inspect/scripts/ledger_commit.py`
- Test: `.claude/skills/sourcing-inspect/scripts/test_ledger_commit.py`

**Interfaces:**
- Consumes: Task 1 전부, `<R>/snapshot.json`, `<R>/verdicts.json`.
- Produces:
  - 순수 함수 `market_rows(items: list[dict], kind: str, campaign: str, date: str, existing: dict) -> dict` — kind `full` 이면 `full_run` 세팅, `3day` 면 `last_3day=date`; `products` 는 **누적**(기존 + 이번 회차 상품 수), `empty = products == 0`.
  - 순수 함수 `product_rows(items, verdicts: dict, campaign, date) -> list[dict]` — 네이버 번호 있는 상품만, verdict 없으면 `"unjudged"`.
  - 명령 `ledger_commit.py --run-dir R --kind full|3day [--stage 1|2] [--date YYYY-MM-DD]` → 세 장부 갱신, 출력 `[ledger] 네이버 +a 타오바오 +b 마켓 갱신 c(새 마켓 d)`. `--stage 2` 일 때만 타오바오 장부에 추가(2차 run-dir 의 스냅샷에 번호가 있다).

- [ ] **Step 1: 실패하는 테스트** — `market_rows` 에 두 상품(같은 slug) + 기존 row(products 3) → products 5, `last_3day` 날짜 세팅, `full_run` 유지; `product_rows` 가 `U01M` 건너뛰고 verdict 없는 건 `unjudged`.
- [ ] **Step 2: 실패 확인.** **Step 3: 구현.** **Step 4: 통과 확인.**
- [ ] **Step 5: 커밋** — `git commit -m "feat(sourcing-pipeline): 회차 결과 장부 기록"`

### Task 6: 파일럿 마켓 선정 `pilot_select.py`

**Files:**
- Create: `.claude/skills/sourcing-inspect/scripts/pilot_select.py`
- Test: `.claude/skills/sourcing-inspect/scripts/test_pilot_select.py`

**Interfaces:**
- Consumes: Task 1 `load_markets`.
- Produces:
  - 순수 함수 `pick(markets: dict, top_n=1000, rand_n=1000, seed=20261110, campaign="kwy9jllI5NICgPo") -> dict[str, str]` — slug → `"top"`/`"random"`. 대상은 `products > 0` 이고 `full_run.campaign == campaign` 인 마켓. 상위 `top_n` 는 products 내림차순(동률은 slug 순), 나머지에서 `random.Random(seed).sample`.
  - 명령 `pilot_select.py [--out-dir 10-projects/16-불사자-소싱-파이프라인]` → `pilot_markets_YYMMDD.txt`(한 줄 한 URL, 소싱기 붙여넣기용) + `pilot_meta_YYMMDD.json`(`{slug: bucket}`) 저장, 출력 `[pilot] top 1000 / random 1000 → 파일 경로`.

- [ ] **Step 1: 실패하는 테스트** — 마켓 5개(products 9,5,5,1,0; 그중 하나는 다른 캠페인)로 `pick(..., top_n=1, rand_n=2)` → top 1건은 9짜리, random 2건은 나머지 상품>0·같은 캠페인에서만, 0개·다른 캠페인은 안 뽑힘, 같은 seed 면 결과 동일.
- [ ] **Step 2: 실패 확인.** **Step 3: 구현.** **Step 4: 통과 확인.**
- [ ] **Step 5: 실제 생성** — `.venv/bin/python3 .claude/skills/sourcing-inspect/scripts/pilot_select.py` → 파일 두 개, 줄 수 2,000 확인(`wc -l`).
- [ ] **Step 6: 커밋** — 스크립트와 생성된 두 파일 모두 커밋. `git commit -m "feat(sourcing-pipeline): 재수확 파일럿 마켓 2,000 선정"`

### Task 7: 회차 보고 `pipeline_report.py`

**Files:**
- Create: `.claude/skills/sourcing-inspect/scripts/pipeline_report.py`
- Test: `.claude/skills/sourcing-inspect/scripts/test_pipeline_report.py`

**Interfaces:**
- Consumes: `<R1>/snapshot.json`(1차 run), `<R1>/verdicts.json`, `<R1>/dup_verdicts.json`, `<R2>/verdicts.json`, `<R2>/dup_verdicts.json`, `<R2>/apply_collect.jsonl`, `pilot_meta_*.json`(선택), Task 1 `mall_slug`.
- Produces:
  - 순수 함수 `summarize(items, v1: dict, dup1: dict, v2: dict, dup2: dict, collect: dict, meta: dict|None) -> dict` — 키: `markets_total, markets_with_items, collected, dup_naver, dup_taobao, pass1, pass2, pass_rate, per_market_collected, per_market_pass2, buckets({bucket: {markets, collected, pass2, per_market_pass2}}), monthly_B(= per_market_pass2 × 16227 × 4), gap_to_140000`.
  - `render(summary: dict) -> str` — 마크다운 표. 첫 줄은 "월 공급 예측 B = N건 / 목표 140,000 / 차이 ±M" 한 문장.
  - 명령 `pipeline_report.py --run1 R1 --run2 R2 [--pilot-meta 파일] [--out <R2>/report.md] [--copy-to 10-projects/16-불사자-소싱-파이프라인/]`

- [ ] **Step 1: 실패하는 테스트** — 손으로 만든 6건 상품(마켓 3개, 묶음 top/random)과 판정으로 `summarize` 숫자 검증(`collected 6, dup_naver 1, pass2 2, per_market_pass2 = 2/3, monthly_B = round(2/3×16227×4)`), `render` 첫 줄에 `140,000` 포함.
- [ ] **Step 2: 실패 확인.** **Step 3: 구현.** **Step 4: 통과 확인.**
- [ ] **Step 5: 커밋** — `git commit -m "feat(sourcing-pipeline): 회차 보고서(마켓당 수율·월 공급 예측)"`

### Task 8: 운영 문서 — SKILL.md 갱신 + 파일럿 실행 절차서

**Files:**
- Modify: `.claude/skills/sourcing-inspect/SKILL.md` — "흐름" 아래에 "## 파이프라인(장부·중복·보고)" 절 추가
- Create: `10-projects/16-불사자-소싱-파이프라인/파일럿-실행-절차.md`

- [ ] **Step 1: SKILL.md 에 명령 순서 추가** (코드 블록 하나, 아래 Task 9 의 순서 그대로) + 규칙 세 줄: 중복 사유 `DUP_SEEN/DUP_TAOBAO` 는 장부가 정본, `ledger_commit` 은 2차 merge 뒤 한 번만, 장부 파일은 git 밖(`~/python_work/data/sourcing-pipeline/`).
- [ ] **Step 2: 절차서 작성** — 용팀장이 읽는 문서(비개발 용어). ① 소싱기에서 캠페인 `R-YYMMDD-파일럿3일` 만들기: 마켓 모드 → 3일베스트 → 가격 3만~50만 원 → 마켓당 100개 → `pilot_markets_YYMMDD.txt` 내용 붙여넣기 → 실행 ② 캠페인 주소창의 ID 를 Claude 에게 알려 주기 ③ 그 뒤는 Claude 가 한다(완료 감지 → 검수 → 보고) ④ 보고서 읽는 법(첫 줄의 월 예측과 목표 차이, 묶음별 수율).
- [ ] **Step 3: 커밋** — `git commit -m "docs(sourcing-pipeline): 파이프라인 명령 순서·파일럿 실행 절차"`

### Task 9: 파일럿 실행(운영 작업, 코드 없음)

**선행:** Task 1~8 완료, 용팀장이 절차서대로 캠페인 생성 후 캠페인 ID 전달. 아래 `C`=캠페인 ID, `D`=YYMMDD, `R1=pilot_D_s1`, `R2=pilot_D_s2`.

- [ ] **Step 1: 토큰** — `web_token.py` (401 이면 절차서의 재로그인 안내).
- [ ] **Step 2: 완료 감지(백그라운드 + 완료 감시 필수)** — `campaign_watch.py --campaign C --run-dir R1` (기본 30분 무변화). `caffeinate -i` 와 함께, 메모리 `never-launch-without-watcher` 대로 감시를 건다.
- [ ] **Step 3: 네이버 중복 제거** — `dedup_stage.py naver --run-dir R1` → 중복 수 기록.
- [ ] **Step 4: 1차(기계만)** — `run_inspect.py prep --run-dir R1 --stage 1 --machine-only` → `merge` → `apply_sourcing.py trash --run-dir R1`(DUP_SEEN 포함 drop 전부 휴지통) → `apply_sourcing.py match --run-dir R1 --workers 3`.
- [ ] **Step 5: 2차 준비** — `run_inspect.py fetch --run-dir R2 --campaign C` → `dedup_stage.py taobao --run-dir R2 --stage1-run R1` → `prep --run-dir R2 --stage 2` → `batch` → `pending` → Workflow `inspect-fanout`(effort 낮추지 않음) → `merge` → `report`.
- [ ] **Step 6: 반영** — `apply_sourcing.py trash --run-dir R2` → `apply_sourcing.py collect --run-dir R2`(그룹 1007620). 옮기기(신규소싱상품 → 소싱테스트_통과, 그룹 변경만)는 2단계 계획에서 자동화하므로 **이번 회차는 결과 수만 보고하고 옮기지 않는다**(용팀장이 앱에서 그룹 변경, 또는 2단계 완성 후 일괄).
- [ ] **Step 7: 장부 기록** — `ledger_commit.py --run-dir R2 --kind 3day --stage 2` → `ledger_commit.py --run-dir R1 --kind 3day --stage 1` (2차 먼저 — 최종 판정이 장부에 남게. 최종 검토 I3).
- [ ] **Step 8: 보고** — `pipeline_report.py --run1 R1 --run2 R2 --pilot-meta <파일> --copy-to 10-projects/16-불사자-소싱-파이프라인/`. 용팀장에게 첫 줄(월 예측 vs 140,000)과 묶음별 마켓당 수율, 재수확 대상을 상위 마켓으로 좁힐 수 있는지 한 줄 판단을 보고한다.
- [ ] **Step 9: 커밋** — 보고서 사본 커밋. `git commit -m "report(sourcing-pipeline): 재수확 파일럿 R-D 결과"`

---

## 자기 검토 메모

- 설계서 4절 B(재수확 수율 측정)·5절(장부 3개·2단계 중복)·6절 4·5(자동 흐름의 중복 단계·보고)·7절(파일럿)·8절(성공 기준 중 "두 번 검수 0")은 Task 1~9 에 있다. 6절 1~3(내보내기·캠페인 자동 생성)·3절의 Playwright/토큰 유지·"옮기기 그룹 변경"·9,398 재검수·타오바오 장부 야간 채우기·공급원 D·카톡 보고는 **의도적으로 다음 계획**이다(위 범위 문단).
- 함수 이름은 Task 간 일치: `mall_slug`, `is_naver_pid`, `taobao_item_id`, `load_*`/`append_*`/`upsert_markets`, `judge_naver`/`judge_taobao`, `is_complete`, `market_rows`/`product_rows`, `pick`, `summarize`/`render`.
