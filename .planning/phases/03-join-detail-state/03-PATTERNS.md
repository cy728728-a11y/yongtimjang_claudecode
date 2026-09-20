# Phase 3: 작업 대상 확정 — 엔티티 해소 + 상세 상태 판정 - Pattern Map

**Mapped:** 2026-09-21
**Files analyzed:** 18 (신규 10 · 수정 8)
**Analogs found:** 17 / 18

> 이 문서가 답하는 질문 하나: **"새로 만드는 파일은 어떤 기존 파일을 베껴야 하나."**
> 추상적인 조언은 안 적는다. 파일·줄번호·발췌만 적는다.
> 플래너는 각 플랜의 action 에 아래 "Analog" 와 "발췌"를 그대로 인용해라.

---

## 🔴 먼저 읽어라 — 계획을 바꾸는 발견 3개

리서치·검증 문서에 안 적혀 있는데 **코드를 읽어서 나온** 것들이다. 셋 다 플랜을 바꾼다.

### ① `.venv-web` 에는 `requests` 가 없다 → 웹앱 프로세스는 불사자 MCP 를 못 부른다

```
$ ls .venv-web/lib/python3.12/site-packages/ | grep -i requests
(없음 — httpx 만 있다)
```

`eroomlib/bulsaja.py:23` 가 `import requests` 다. `.claude/skills/bulsaja-category-fix/scripts/bulsaja_mcp.py`
도 그 모듈을 상속한다. 그래서 **`webapp/bulsaja_index.py` 가 `eroomlib` 를 import 하는 순간 ImportError 다.**

RESEARCH §Architectural Responsibility Map 은 *"인덱스 조회·재검증 | 웹앱(SQLite 읽기 + MCP 1회)"* 라고 적었는데,
**그 MCP 1회가 웹앱 프로세스 안에서 안 된다.** 게다가 `webapp/paths.py:4-10` 이 이미 못을 박아 놨다:

```python
# webapp/paths.py:4-10
"""**eroomlib 을 import 하지 않는다.** run_ads.py 는 `sys.path.insert` 로 스크립트 디렉터리를
최상위에 꽂는데(`collect`·`reports` 같은 흔한 이름이 전역이 된다), 그 경로를 웹앱 프로세스에
넣으면 stdlib 이 가려진다. 같은 결과를 stdlib `tomllib` 로 낸다 — CLI 와 규약만 공유하고
프로세스는 subprocess 경계로 갈라 둔다."""
```

**결론 — 플래너가 셋 중 하나를 골라야 한다:**

| 길 | 대가 | 기존 패턴 정합성 |
|---|---|---|
| **(a) `webapp/bulsaja_index.py` 는 stdlib `sqlite3` 읽기 전용. MCP 접촉은 전부 CLI 자식** | 재검증이 요청 안에서 안 되고 잡이 된다 | ⭐ `board.py` 가 이미 이 모양이다 — "CLI 가 써 둔 산출물을 읽을 뿐" |
| (b) `.venv-web` 에 `requests` 설치 | RESEARCH §Standard Stack *"이 페이즈는 새 외부 패키지를 하나도 설치하지 않는다"* 와 충돌 | ✗ |
| (c) 웹앱이 `httpx` 로 MCP transport 를 따로 짠다 | **transport 진실이 둘** — CLAUDE.md 금지항목 | ✗ |

**권고: (a).** `board.py` 의 주석이 그 근거를 이미 적어 뒀다 (아래 §공유 패턴 1).

### ② `test_jobs.py:460` 이 `ss_index` 테이블을 막는다 — 이미 있는 가드다

```python
# webapp/tests/test_jobs.py:460-471
def test_보드캐시와_대상별락_테이블을_만들지_않는다(잡판):
    """스키마는 jobs 하나뿐이다. ..."""
    이름들 = {r[0] for r in cx.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "jobs" in 이름들
    assert 이름들 - {"jobs"} == set(), f"예상 밖 테이블: {이름들}"
```

RESEARCH §Runtime State Inventory 가 *"신설 예정: `webapp.db` 의 `ss_index` 테이블 … `jobs.DDL` 과 같은 자리에"*
라고 적은 대로 하면 **이 테스트가 빨개진다.** 우연히 깨는 게 아니라 **일부러 고쳐야 하는** 테스트다 —
플랜에 "이 테스트의 허용 집합을 `{"jobs", "ss_index"}` 로 넓히고 **왜 캐시가 아닌지** 를 docstring 에 적는다"
를 명시적 작업으로 넣어라. 조용히 고치면 다음 사람이 "보드 캐시 금지"가 풀린 줄 안다.

⚠️ 구분을 docstring 에 써라: `ss_index` 는 **보드 캐시가 아니다.** 보드 캐시는 `result.json` 에서 언제든
재생성 가능한 투영이고, `ss_index` 는 **4시간을 태워야 다시 얻는 외부 관측 기록**이다. 성격이 다르다.

### ③ `workspace.toml` 에 `[webapp]` 테이블이 **아직 없다**

```
$ grep -n -A10 "\[webapp\]" workspace.toml
(no [webapp] table)
```

ENG-08 의 `settings.cfg("expected_bulsaja_nick", required=True)` 는 **오늘 당장 KeyError** 다.
그게 설계 의도(§ENG-08: *"값이 비면 KeyError 로 터져야지, 조용히 폴백해 가드가 사라지면 안 된다"*)이긴 한데,
**플랜에 `workspace.toml [webapp]` 테이블 신설 + 값 기입을 작업으로 넣지 않으면 서버가 기동 직후 죽는다.**
그리고 그 값은 `workspace.toml` 에만 있고 `settings.DEFAULTS` 에는 **빈 문자열**이어야 한다 (§공유 패턴 3).

---

## File Classification

| 만들/고칠 파일 | 역할 | 데이터 흐름 | 가장 가까운 유사 파일 | 매치 |
|---|---|---|---|---|
| `webapp/join.py` | service (순수 함수) | transform | `webapp/board.py` | exact |
| `webapp/state.py` | service (순수 함수) | transform | `webapp/board.py` (§`_rule_key`/`fold_products` 방어 관용구) | role-match |
| `webapp/bulsaja_index.py` | repository (SQLite 읽기) | CRUD (read-only) | `webapp/jobs.py` §DDL·`_conn`·`_row` + `webapp/paths.py` | role-match |
| 인덱스 구축 CLI (예 `.claude/skills/bulsaja-detail-page/scripts/ss_index_build.py`) | CLI batch | batch · rate-limited request-response | `.claude/skills/bulsaja-detail-page/scripts/detail_batch.py` | exact |
| `webapp/argv.py` — `BulsajaArgv` 추가 | config/builder | transform | `webapp/argv.py:49` `AdsArgv` (**같은 파일**) | exact |
| `webapp/settings.py` — DEFAULTS 확장 | config | — | `webapp/settings.py:18-25` (**같은 파일**) | exact |
| `webapp/jobs.py` — `kind` 추가 + ENG-08 가드 | service | event/process | `webapp/jobs.py:365/404` (**같은 파일**) | exact |
| `webapp/board.py` — 상태 열 투영 | service | transform | `webapp/board.py:108` `fold_products` (**같은 파일**) | exact |
| `webapp/routes/board.py` — ctx 확장 | route | request-response | `webapp/routes/board.py:57` `home` (**같은 파일**) | exact |
| `webapp/templates/board.html` — 상태열·해상률 배너·계정 표시 | template | — | `board.html:70-96` 신선도 배너 | exact |
| `webapp/static/board.js` — 컬럼 추가 | component | — | `board.js:89-127` `columns` | exact |
| `.claude/skills/bulsaja-detail-page/scripts/detail_batch.py:46-48` | CLI (수정 3줄) | — | `.claude/skills/product-name/scripts/run_names.py:40-46` | exact |
| `webapp/tests/test_join.py` | test (unit) | — | `webapp/tests/test_board.py` | exact |
| `webapp/tests/test_state.py` | test (unit) | — | `webapp/tests/test_board.py` | exact |
| `webapp/tests/test_index.py` | test (unit, fake clock) | — | `webapp/tests/test_jobs.py` §`잡판` 픽스처 | role-match |
| `webapp/tests/test_cli_shim.py` | test (smoke, subprocess) | — | `webapp/tests/test_cli_patch.py` | exact |
| `webapp/tests/fixtures/*.json` | fixture | — | `webapp/tests/fixtures/result_min.json` + `conftest.py:29` | exact |
| `webapp/tests/test_board.py` · `test_paths.py` · `test_jobs.py` — 가드 확장 | test (guard) | — | (자기 자신) | exact |

**유사 파일 없음:** 0건. 이 페이즈에 진짜 새 부품은 없다 — RESEARCH §Don't Hand-Roll 의
*"새로 쓰는 로직은 사실상 함수 3개"* 가 코드에서 확인된다.

---

## Pattern Assignments

### `webapp/join.py` (service, transform)

**Analog:** `webapp/board.py` — 같은 성질이다. 읽기 전용 · 네트워크 0 · 순수 함수 · 판정 재계산 금지.

**모듈 docstring 패턴** (`board.py:3-13`) — **이 모양을 그대로 베껴라.** "이 모듈이 절대 하지 않는 것"을
목록으로 못박는 게 이 저장소의 관용구다:

```python
# webapp/board.py:3-13
"""보드 투영 — 판정 결과를 상품 단위 표로 **모으기만** 한다.

**읽기 전용이다. CLI 를 실행하지 않고 판정값을 만들지 않는다.** `result.json` 만 읽는다.
...
이게 STACK.md 의 "세 번째 길" 이다. 보드 데이터는 CLI 를 실행해서도, CLI 모듈을 불러와서도
얻지 않는다. CLI 가 **이미 써 둔 산출물**을 읽을 뿐이다. 그래서 이 모듈은 네트워크도
크레딧도 광고비도 0 이고, 회차 파일이 없으면 빈 목록을 돌려줄 뿐 아무것도 고장내지 않는다.
"""
```

**"이 모듈이 절대 하지 않는 것" 블록** (`board.py:23-29`) — `join.py` 판 목록:
- 상품명 매칭 (D-03) · 별칭표/폴백 매핑 (D-02b) · `mallProductId` 영구 캐시 (D-04)

**빈 입력 방어 패턴** (`board.py:63-67`, `board.py:129-130`) — 전부 이 모양이다:

```python
# webapp/board.py:63-67
def account_list(result: dict) -> list[str]:
    if not isinstance(result, dict):
        return []
    return sorted((result.get("accounts") or {}).keys())
```

```python
# webapp/board.py:129-130
    if not isinstance(result, dict):
        return []
```

> 회귀 근거: `test_board.py:97-98` 이 `board.account_list({}) == []` 와 `fold_products({}) == []` 를 고정한다.
> `join.py` 의 모든 공개 함수에 같은 테스트를 걸어라.

**`.get()` 만 쓰는 규율** (`board.py:36-40`) — STATE-03 의 `aiImageGenerated` 키 부재와 **같은 부류**다:

```python
# webapp/board.py:36-40
"""**①·⑥ 행에는 `imp`/`clk`/`ctr`/`rank`/`cost` 키가 아예 없다.** 7일 통계에 행이 없는
것이 규칙①의 정의이기 때문이다. 실데이터에서 그런 행이 2,274개다 — `row["imp"]` 를
쓰면 거기서 통째로 깨진다. 이 파일은 `.get()` 으로만 만진다."""
```

**"0 이 아니라 None" 규율** (`board.py:174-176`) — 미해소 사유 3종 분리(Pitfall 3)의 같은 철학:

```python
# webapp/board.py:174-176
        # CTR 은 합산하지 않고 **다시 낸다**. 노출이 없으면 비율도 없다(0 이 아니라 None) —
        # 0.00% 로 찍으면 "클릭이 0 이었다" 는 판정처럼 보이는데, 실제로는 분모가 없다.
```

→ **미해소 사유도 같다.** `"못 찾았다"` 한 통에 담지 마라. `추출실패` / `번호없음` / `미조회` 3종을
**서로 다른 값**으로 내라 (JOIN-02 / VALIDATION `test_미해소_사유_3종`).

**정렬키 관용구** (`board.py:52-56`) — 미해소 사유 정렬에 그대로 쓸 모양:

```python
# webapp/board.py:52-56
def _rule_key(name: str) -> tuple:
    """규칙 키를 `①②③④⑤⑥` 순서로 정렬하기 위한 정렬키."""
    head = name[:1]
    return (RULE_ORDER.index(head) if head in RULE_ORDER else len(RULE_ORDER), name)
```

**한글 함수명 규약:** RESEARCH §Code Examples 는 `마켓번호()` / `마켓그룹색인()` 으로 썼고,
저장소도 `board.py:159` `첫_규칙1`, `logtail.py:58` `앞을자른다`, `security.py` `토큰이같나` 처럼
**내부 이름은 한글, 공개 API 는 영문**이다. `board.py` 의 공개 함수는 전부 영문(`account_list`,
`fold_products`)이다. **`join.py` 도 공개 함수는 영문, 지역변수·private 헬퍼는 한글로 가라.**
⚠️ 단 VALIDATION 의 테스트 이름은 한글(`test_해상률`, `test_미해소_사유_3종`)로 고정돼 있다.

---

### `webapp/state.py` (service, transform — 순수 함수 2개)

**Analog:** `webapp/board.py` (모듈 성격) + RESEARCH §D-12 확정 판정 규약 (로직 정본).

**로직은 RESEARCH 03-RESEARCH.md:338-380 에 완성본이 있다. 그대로 옮겨라.** 다시 설계하지 마라.
아래는 그 코드가 **왜 저 모양인지**를 뒷받침하는 저장소 내부 근거다:

**bool 순서 함정 — 같은 실수가 이미 두 곳에 적혀 있다:**

```javascript
// webapp/static/board.js:68-72
  function 예아니오(cell) {
    var v = cell.getValue();
    // **bool 을 먼저 분기한다.** 파이썬에서 bool 은 int 의 하위 타입이라 순서를
    // 바꾸면 1/0 으로 찍혀 사람이 못 읽는다(report_md.py:17-40 의 함정).
    if (typeof v === "boolean") { return v ? "예" : "아니오"; }
```

RESEARCH 의 `불리언정규화()` 가 `isinstance(v, bool)` 을 `isinstance(v, (int,float))` **앞에** 두는 게
같은 이유다. 순서를 바꾸면 `False` 가 `0 != 0` → False 로 **우연히** 맞고, `True` 도 우연히 맞아서
**테스트가 통과한다.** 그래서 이 순서는 주석으로 남겨라.

**CLI 쪽 기존 판정 로직 — 절대 베끼지 마라 (STATE-05 깨짐 ①):**

```python
# .claude/skills/bulsaja-detail-page/scripts/detail_batch.py:137-140 (현행, 깨져 있다)
def existing_ai_detail(data):
    dc = data.get("uploadDetailContents") or {}
    if not dc.get("aiImageGenerated"):        # ← 외부 경로 기작업분을 못 잡는다
        return None
```

그리고 **`eroomlib.snapshot.ProductMCP.workdata()` 의 투영도 쓰지 마라** — `bool()` 을 그냥 쓴다:

```python
# .claude/lib/eroomlib/snapshot.py:184-189
            "상세": {
                "AI생성": bool(det.get("aiImageGenerated")),   # ← 문자열 '0' 이 True 가 된다
                "장수": int(det.get("aiImageOutputCount") or 0),
                ...
            },
```

동시에 `snapshot.py:165-192` 반환 dict 에 **`uploadedSuccessUrl` 이 없다** (Pitfall 1). 인덱스 구축은
`call_tool("bulsaja_product_workdata", {...})` **원본**을 읽어야 한다.

**Pitfall 8 — 태그와 기계기록을 한 값으로 합치지 마라.** `board.py:107` 의 `_dedupe_ads` 가
"규칙 기호는 set 에 모으고 지표는 첫 값 유지"로 **두 성격을 섞지 않는** 모양을 이미 보여준다.
`state.py` 도 `상세상태` (⚪🟡🔴, 기계기록)와 `기작업태그` (`구매_가공완료`, 사람 손자국)를
**별개 반환값**으로 내라.

---

### `webapp/bulsaja_index.py` (repository, CRUD read-only)

**Analog:** `webapp/jobs.py` (SQLite 관용구) + `webapp/paths.py` (stdlib 만 쓰는 경계).

⚠️ **§🔴① 을 먼저 읽어라.** 이 파일은 `eroomlib` 를 import 할 수 없다. stdlib `sqlite3` 만이다.

**DDL 은 `jobs.py:76-96` 옆에 같은 모양으로:**

```python
# webapp/jobs.py:76-96
DDL = """
CREATE TABLE IF NOT EXISTS jobs (
  id            TEXT PRIMARY KEY,
  kind          TEXT NOT NULL,
  ...
  started_at    TEXT NOT NULL,
  ended_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_parent ON jobs(parent_job_id);
"""
# ※ RESEARCH §5.7 의 DDL 에서 `run_dir` 만 NOT NULL 을 뺐다. ...
# ※ 보드용 캐시 테이블은 만들지 않는다. 보드는 매번 `result.json` 을 투영한다(수십 ms).
#    캐시는 최적화이고, 지금 넣으면 "진실이 둘" 위험만 는다.
```

**DDL 아래 `# ※` 주석으로 "왜 이 컬럼이 이 모양인지"를 남기는 게 이 저장소 관용구다.**
`ss_index` DDL 에는 최소 이 두 줄을 남겨라:
- `※ observed_at 이 있어야 D-04 를 안 어긴다` — "영구 키로 쓰는 것"과 "관측 기록을 관측시각과 함께
  보관하는 것"은 다르다. 쓰기 직전 재검증이 그 선을 지킨다 (RESEARCH §D-13 권장설계 A).
- `※ 이건 보드 캐시가 아니다` — §🔴② 참조.

**DB 경로 관용구** (`jobs.py:120-123`) — `ss_index` 도 같은 `webapp.db` 를 쓴다면 이걸 재사용해라:

```python
# webapp/jobs.py:120-123
def db_path() -> Path:
    """잡 레지스트리 파일. 상대경로면 저장소 루트 기준."""
    p = Path(settings.DB_PATH).expanduser()
    return p if p.is_absolute() else paths.repo_root() / p
```

**테스트에서 tmp 로 돌리는 방법** (`test_jobs.py:72-77`) — `test_index.py` 가 그대로 쓴다:

```python
# webapp/tests/test_jobs.py:72-77
@pytest.fixture
def 잡판(tmp_path, monkeypatch):
    """잡 DB·로그 디렉터리를 tmp 로 돌린다. 저장소 루트의 webapp.db 를 안 건드린다."""
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.setattr(settings, "JOB_LOG_DIR", str(tmp_path / "logs"))
    jobs.init_db()
```

**throttle / 429 재시도 로직의 자리:** VALIDATION 이 `test_index.py::test_초당4회_상한`(fake clock)과
`test_429는_미조회로_남는다` 를 요구한다. **순수 함수로 떼어내야 fake clock 이 붙는다.**
저장소의 주입 관용구가 이미 있다:

```python
# .claude/lib/eroomlib/snapshot.py:191-192
    def poll_ai_task(self, task_id, target="detail", interval=10, timeout=900,
                     sleep_fn=time.sleep):
        """... `sleep_fn` 은 테스트가 대기를 없애려고 주입한다."""
```

→ **인덱스 루프도 `sleep_fn=time.sleep` · `now_fn=time.time` 을 인자로 받아라.** 그래야 3시간짜리
루프의 레이트리밋 규율을 0.01초 안에 검증한다.

---

### 인덱스 구축 CLI (CLI batch, rate-limited)

**Analog:** `.claude/skills/bulsaja-detail-page/scripts/detail_batch.py` — **성질이 정확히 같다.**
장시간 · 체크포인트 재개 · `flush=True` 줄 출력 · 불사자 MCP · argparse.

**docstring 패턴** (`detail_batch.py:2-32`) — 실측 근거와 체크포인트 규약을 최상단에 적는다:

```python
# .claude/skills/bulsaja-detail-page/scripts/detail_batch.py:2-30
"""불사자 AI 상세페이지 배치 생성 (기본 10장, 일반화질).

⚠️ 핵심 (2026-07-23 실측): 10장짜리 상세페이지가 되려면
   imageUrls(상품 이미지 목록, 최대 10장) + sectionCount(장수) 를 **동시에** 보내야 한다.
...
- 체크포인트: <run-dir>/detail_status.json {pid: {taskId, status, pages, ...}}
- 재개: taskId 있는 상품은 접수 스킵, 미완료만 폴링 (--poll-only)
- 크레딧: 일반화질 장당 5 / 고화질 장당 10 (성공분만 과금)

사용:
  python detail_batch.py --run-dir <RUN> [--pages 10] ...
"""
```

⚠️ **체크포인트 위치만 다르다.** `detail_batch.py` 는 run-dir JSON 에 두는데, 인덱스는
**SQLite 에 둬야 한다** (RESEARCH §D-13 "인덱스는 회차를 넘어 산다"). 그리고 체크포인트 단위는
**페이지 번호가 아니라 처리한 productId 집합**이다 (Pitfall 6) — `collect_group` 의 `seen` 과 같은 원리:

```python
# .claude/lib/eroomlib/snapshot.py:215-228
        out, seen, page = [], set(), 1
        while True:
            r = self.call_tool("bulsaja_market_group_products",
                               {"groupId": group_id, "page": page, "pageSize": page_size})
            items = r.get("항목") or []
            if not items:
                break
            for it in items:
                pid = it.get("productId")
                if not pid or pid in seen:
                    continue
                seen.add(pid)
```

**argparse 패턴** (`detail_batch.py:210-230`):

```python
# .claude/skills/bulsaja-detail-page/scripts/detail_batch.py:210-220
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--pages", type=int, default=10, ...)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--submit-only", action="store_true")
    ap.add_argument("--poll-only", action="store_true")
```

**`flush=True` — 협상 불가** (`detail_batch.py:275,281,342` 등 전부). RESEARCH §Pattern 4 근거.
동시에 `jobs.spawn` 이 `PYTHONUNBUFFERED=1` 을 주입하지만(`jobs.py:294`), **둘 다 있어야 한다** —
CLI 를 터미널에서 직접 돌릴 때는 env 주입이 없다.

**인코딩 관용구** (`detail_batch.py:40-43` · `run_names.py:34-37` 동일):

```python
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
```

**MCP 루프 코드 자체는 RESEARCH 03-RESEARCH.md:956-1003 에 완성본이 있다. 그대로 써라.**
(최소간격 0.26초 · 429 시 21초 대기 · 실패 시 `기록(pid, None, 미조회=True)` — 조용히 continue 금지)

**파일 위치 결정 필요 (플래너 몫):** `argv.py:40` 의 `RUN_ADS` 처럼 경로 상수가 하나 생긴다.
`.claude/skills/bulsaja-detail-page/scripts/` 밑에 두면 `run_names.py:40-46` shim 으로 `bulsaja_mcp`
를 바로 찾는다 (§`detail_batch.py` 항목 참조). 새 디렉터리를 파면 shim 경로 계산도 새로 해야 한다.

---

### `webapp/argv.py` — `BulsajaArgv` 추가 (config/builder)

**Analog:** 같은 파일의 `AdsArgv` (`webapp/argv.py:49-96`). **다른 파일에 만들지 마라** —
`test_argv.py:159-171` 이 "조립은 한 곳" 을 기계로 집행한다.

**Pydantic 조립 패턴 — 이 세 줄이 핵심이다:**

```python
# webapp/argv.py:21-23
from typing import Annotated, Literal
from pydantic import BaseModel, StringConstraints

# webapp/argv.py:46
Alias = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]+$", min_length=1)]

# webapp/argv.py:56
    subcommand: Literal["prep", "run", "apply", "bids", "accounts"]
```

**`BulsajaArgv` 가 받는 값에도 같은 `Annotated[str, StringConstraints(...)]` 를 걸어라.**
마켓그룹 ID·번호(`NN-N`)가 argv 로 나가니까:
- 그룹 ID: 숫자만 (`^[0-9]+$`)
- 마켓번호: `^\d{1,2}-\d{1,2}$`

**`PY_CLI` 는 그대로 쓴다** (`argv.py:38`). `.venv-web` 인터프리터로 CLI 를 띄우면 죽는다 —
`test_argv.py:29-40` 이 `av[0].endswith("/.venv/bin/python3")` 와 `"/.venv-web/" not in av[0]` 를 고정.

**`prefix` 필드를 반드시 넣어라** — `caffeinate -i` 자리다. `AdsArgv` 가 이유까지 적어 놨다:

```python
# webapp/argv.py:62-68
    # Phase 2 의 `caffeinate -i` 자리 (ENG-06). 예: ["/usr/bin/caffeinate", "-i"]
    # 맥북 idle sleep 이 수십 분짜리 폴링을 끊는다. `man caffeinate` 기준
    # utility 를 지정하면 그 프로세스 수명 동안만 assertion 이 유지된다 —
    # 자식이 끝나면 저절로 풀리므로 따로 해제할 일이 없다.
    # Phase 1 에서는 항상 비어 있지만 **필드가 존재해야** Phase 2 가 한 줄로 끝난다.
    prefix: list[str] = []
```

**`build()` 의 "빈 리스트면 플래그 자체를 안 붙인다" 함정** (`argv.py:79-84`) — 인덱스 잡에도 똑같이 온다.
`--group` 을 값 없이 붙이면 **전 그룹(75,335건 / 5시간 39분)** 이 된다. `D-18` 제외 그룹이
빈 값으로 넘어가면 13-2 를 다시 훑는다:

```python
# webapp/argv.py:79-84
        # **빈 리스트면 플래그 자체를 안 붙인다.**
        # `run_ads.py` 의 `--account` 는 `nargs="*"` 라 값 없이 붙으면 `[]` 가 되고,
        # `_accounts(only=[])` 의 `if only:` 가 falsy 로 떨어져 **전 계정**을 돈다.
        # 한 계정만 돌리려다 4계정(=수 분 × 4)을 돌리는 사고가 여기서 난다.
        if self.accounts:
            av += ["--account", *self.accounts]
```

**경로는 `str()` 로 못박는다** (`argv.py:90-91`) — `Path` 를 그대로 두면 jobs 테이블 argv JSON 직렬화가 터진다.

---

### `webapp/jobs.py` — 새 `kind` + ENG-08 계정 가드 (service, process)

**Analog:** 같은 파일. 고칠 자리가 6군데다.

| 자리 | 줄 | 무엇을 |
|---|---|---|
| `JobKind` | `jobs.py:43-44` | `"bulsaja_index"` 추가 |
| `KINDS` | `jobs.py:46-47` | 같이 추가 (**둘 다 고쳐야 한다 — 하나만 고치면 타입만 맞고 런타임은 거부**) |
| `WRITE_KINDS` | `jobs.py:56` | ⚠️ 판단 필요 — 아래 참조 |
| `DDL` | `jobs.py:76-96` | `ss_index` 추가 (+ `test_jobs.py:460` 동시 수정, §🔴②) |
| `_build_argv` | `jobs.py:365-402` | `BulsajaArgv` 분기 추가 |
| `create_job` | `jobs.py:404+` | ENG-08 계정 가드 |

**작업 종류 표를 docstring 에 갱신하는 것도 작업이다** (`jobs.py:11-19`):

```python
# webapp/jobs.py:11-19
| kind           | 서브커맨드        | 디스크 쓰기 | 광고 API 쓰기 | 전역 가드 |
|----------------|-------------------|-------------|---------------|-----------|
| `prep`         | `prep`            | run-dir 생성 | 없음(리포트 잡 접수는 한다) | **탄다** |
...
```

**`WRITE_KINDS` 판단 — 인덱스 잡은 넣지 마라.** 근거가 주석에 있다:

```python
# webapp/jobs.py:50-56
# 전역 1개 가드의 대상. **왜 전역인가:** ... 쓰기 잡 두 개가 겹치면 백업 항목이 사라지고
# **그 소재는 영영 되돌릴 수 없다.** 되돌릴 수 없는 손실이라 넓게, 그리고 지금 막는다.
# ... 미리보기·판정은 아무것도 안 쓰므로 뺀다 —
# 쓰기가 아닌 것까지 막는 가드는 사람이 가드를 끄게 만든다.
WRITE_KINDS: frozenset[str] = frozenset({"prep", "bids_commit", "revert_only", "revert_all"})
```

인덱스 잡은 **불사자에 아무것도 안 쓴다**(읽기 전용 workdata 조회). 넣으면 3시간 32분 동안
입찰가 인상이 전부 409 가 된다. → **넣지 마라.** 대신 `ss_index` **자기 테이블 안**에서 잡이
겹치지 않게 막는 건 별개 문제고, 그건 플래너가 정한다.

**ENG-08 계정 가드의 자리 — `create_job` 안이다.** 라우트가 아니다:

```python
# webapp/jobs.py:412-419
    """...
    **이 함수는 HTTP 를 모른다** (D-17 / ENG-07). 요청 객체를 받지 않고 상태코드를
    모른다. v2 의 APScheduler 가 이 함수를 그대로 부른다 — 그때 라우트를 통해
    자기 서버에 요청을 쏘는 모양이 되지 않게 지금 경계를 그어 둔다.

    순서에 의미가 있다:
      ① 쓰기 잡 전역 가드 (BusyError) — 자식을 띄우기 **전에** 막는다
      ② 회차 화이트리스트 — 라우트가 깜빡해도 여기서 막힌다 (T-1-11)
```

**예외 → 상태코드 번역은 라우트 몫** (`jobs.py:99-100`):

```python
# webapp/jobs.py:99-100
class BusyError(RuntimeError):
    """이미 도는 쓰기 작업이 있다. 라우트가 409 로 번역한다."""
```

→ ENG-08 도 같은 모양의 전용 예외를 하나 세워라 (예: `AccountMismatchError(ValueError)` →
라우트가 400/409 로 번역). `ValueError` 를 그냥 쓰면 "모르는 회차"와 구분이 안 된다.

**"빈 값이 전량이 되는 경로는 예외로 터뜨린다"** (`jobs.py:389-395`) — **이 페이즈의 D-18 제외 그룹이
정확히 같은 부류다.** 이 주석을 인덱스 잡 쪽에 옮겨 적어라:

```python
# webapp/jobs.py:389-395
        # **그래서 대상 파일이 없는 `revert_only` 는 존재할 수 없다.** 없으면
        # `AdsArgv` 가 `--only-ads` 를 안 붙이고 CLI 는 그걸 "백업 전량" 으로 읽는다
        # ... **빈 값이 '전량' 으로 해석되는 경로는 예외로 터뜨린다** —
        if kind == "revert_only" and targets_path is None:
            raise ValueError("revert_only 에는 대상 파일이 반드시 있어야 한다 — "
                             "대상 없는 되돌리기는 회차 전체다(D-12)")
```

---

### `webapp/board.py` — 상세 상태 열 투영 확장

**Analog:** 같은 파일 `fold_products` (`board.py:108-180`).

**접기 키는 `(alias, mallProductId)` 다** (`board.py:138`) — 상태는 **불사자 productId 단위**로 오므로
1:N 이 생긴다 (RESEARCH §보드에 붙일 때 주의):

```python
# webapp/board.py:137-140
    for alias, account in (result.get("accounts") or {}).items():
        for adId, slot in _dedupe_ads(account).items():
            r = slot["row"]
            key = (alias, r.get("mallProductId"))
```

**행 dict 의 초기화 모양** (`board.py:141-153`) — 새 열도 **여기에 `None` 으로 먼저 선언**해야
"키가 없는 행"이 안 생긴다:

```python
# webapp/board.py:141-153
                p = prod[key] = {
                    "acct": alias,
                    "mallProductId": r.get("mallProductId"),
                    "title": r.get("title") or "",
                    "_rules": set(),
                    "rule1_ads": [],          # ← 버튼이 적용될 소재 (D-06)
                    "bid": None, "useGroupBid": None, "groupBid": None,
                    "_bid_from_rule1": False,
                    "imp": None, "clk": None, "ctr": None,
                    "purCnt": None, "purAmt": None, "cost": None,
                }
```

**후처리 자리** (`board.py:169-178`) — 상태 열·해소여부·사본N 은 여기 붙는다:

```python
# webapp/board.py:169-178
    out = []
    for p in prod.values():
        p["rules"] = "".join(sorted(p.pop("_rules")))
        p["rule1_count"] = len(p["rule1_ads"])   # "이 버튼이 N건에 적용됩니다"
        p.pop("_bid_from_rule1", None)
        p["ctr"] = round(p["clk"] / p["imp"] * 100, 2) if p["imp"] else None
        out.append(p)
    return out
```

⚠️ **`fold_products(result)` 의 시그니처를 바꾸지 마라.** `routes/board.py:135` 와 `test_board.py` 가
1인자로 부른다. 조인 결과는 **별도 함수**(예: `board.attach_join(rows, 조인결과)`)로 붙여라 —
`fold_products` 가 SQLite 나 MCP 를 알게 되면 "네트워크도 크레딧도 0" 이라는 이 모듈의 계약이 깨진다.

---

### `webapp/routes/board.py` — ctx 확장 (route, request-response)

**Analog:** 같은 파일 `home()` (`routes/board.py:57`).

**라우트는 얇다 — `async def` 가 아니라 `def`** (`routes/board.py:20-23`):

```python
# webapp/routes/board.py:20-23
"""**CLI 를 실행하지 않는다.** 보드 데이터는 `run-dir/result.json` 을 읽어 투영할 뿐이라
네트워크도 크레딧도 광고비도 0 이다(STACK.md "세 번째 길"). 무거운 건 파일 읽기 하나뿐이라
`async def` 가 아니라 **`def`** 로 선언한다 — async 핸들러에서 blocking 파일 IO 를 하면
이벤트 루프가 멈춰 SSE 진행 로그가 같이 끊긴다(Anti-Patterns)."""
```

> `test_jobs.py:714` `test_라우트_중_async_는_스트림_하나다` 가 이걸 기계로 집행한다.
> **SQLite 읽기를 async 핸들러에 넣지 마라.**

**ctx 딕셔너리** (`routes/board.py:104-117`) — 해상률·계정정보가 붙을 자리:

```python
# webapp/routes/board.py:104-117
    ctx = {
        "token": security.BOOT_TOKEN,
        "job": jobs.active_job(),
        "runs": 회차들,
        "run_dir": 선택,
        "freshness": None,
        "accounts": [],
        "rules": [],
        "rows": [],
        "load_error": None,
    }
```

**"폴백하지 않는다" 패턴** (`routes/board.py:36-46`) — 인덱스 로드 실패에 그대로 적용:

```python
# webapp/routes/board.py:36-46
def _load_result(run_dir_name: str) -> tuple[dict, str | None]:
    """`result.json` 을 읽는다. 실패하면 `({}, 사유)` — **폴백하지 않는다**.
    ... 읽기 실패는 화면에 사유를 띄우고 빈 보드를 보여준다 ...
    그렇다고 조용히 넘어가면 사용자가 "오늘은 판정 대상이 없구나" 로 오독한다.
    예외 문자열은 `f"{type(e).__name__}: {e}"` 로 축약한다 — 트레이스백을 화면에
    실으면 경로·내부 구조가 그대로 나간다(ASVS V7)."""
```

→ **인덱스가 비었을 때 "미해소 전량"으로 보이면 Pitfall 3 그 자체다.** `load_error` 와 같은 자리에
`index_error` / `index_incomplete` 를 **따로** 실어라.

**화이트리스트 투영** (`routes/board.py:131-133`):

```python
# webapp/routes/board.py:131-133
    # 템플릿에 넘기는 것은 화면에 필요한 **값**뿐이다. 계정 객체를 통째로 넘기지 않는다
    # (SAFE-03 화이트리스트 투영). 웹앱은 계정 자격증명 파일을 아예 열지 않는다.
```

→ **불사자 MCP 응답의 `표시규칙` 필드를 버리는 코드가 정확히 이 자리 관용구다** (ENG-08 / 프롬프트 인젝션).
응답 dict 를 통째로 ctx 에 넣지 말고 필요한 키만 뽑아라. VALIDATION `test_표시규칙은_버린다` 가 고정한다.

---

### `webapp/templates/board.html` — 상태열 · 해상률 배너 · 계정 표시

**Analog:** 신선도 배너 (`board.html:70-96`) — **해상률 배너가 정확히 같은 성격이다.**
"숫자만 띄우면 오독되는 값에 해석을 붙인다":

```jinja
{# webapp/templates/board.html:70-76 #}
    {# 신선도 배너 (D-16) — 회차명과 실제 통계기간은 늘 며칠 어긋난다.
       collect.window() 가 until = 오늘-2일 이라 회차명이 항상 더 신선해 보인다.
       둘을 같이 안 보여주면 8월 30일 자료인 줄 알고 8월 22~28일 자료로 입찰가를 올린다. #}
    {% if freshness %}
      <p id="freshness" {% if freshness.stale %}class="stale"{% endif %}>
        <strong>{{ freshness.run_dir }}</strong> 회차
```

**`.stale` CSS 클래스를 재사용해라** (`board.html:24-30`) — 이미 "스크롤하기 전에 눈에 걸리는" 스타일이다:

```css
/* webapp/templates/board.html:24-30 */
    .stale {
      border-left: .4rem solid var(--pico-del-color, #d93526);
      background: var(--pico-mark-background-color, #fff3cd);
      color: var(--pico-mark-color, inherit);
      padding: .6rem .8rem; border-radius: .25rem;
    }
```

⚠️ **미해소 배너와 "인덱스 불완전" 배너는 생김새가 달라야 한다** (Pitfall 3). `#danger-zone`
(`board.html:52-55`)이 같은 원리를 이미 쓴다: *"결과 표의 되돌리기 버튼과 **생김새가 달라야** 한다 —
거리만으로는 부족하고, 눈이 '여기는 다른 종류의 버튼' 이라고 읽어야 한다."*

**자동 이스케이프를 끄지 마라** (`board.html:7-11`):

```jinja
{# webapp/templates/board.html:7-11 #}
   자동 이스케이프를 끄는 필터를 쓰지 마라 — 상품명에 중국어 원문과 특수문자가
   섞여 들어온다(T-1-17). 보드 데이터는 tojson 으로 내보낸다: 그 필터가
   < > & ' 를 \uXXXX 로 바꿔 주므로 상품명에 닫는 script 태그가 들어 있어도
   스크립트가 끊기지 않는다.
```

→ **미해소 사유 문자열에 광고그룹명 원문이 들어간다** (JOIN-02). 그게 사용자 입력이 아닌 것처럼
보여도 네이버 광고 화면에서 사람이 지은 이름이다. `|safe` 를 붙이지 마라.

**⚪🟡🔴 이모지:** `board.py:34` 의 `RULE_ORDER = "①②③④⑤⑥"` 이 선례다 — 기호를 상수로 두고
의도를 주석에 남기는 모양. 다만 **판정값 자체는 문자열(`"AI가공완료"` 등)로 내고 이모지는 화면에서 붙여라**
(RESEARCH 의 판정 함수가 이미 그 모양이다 — `return "AI가공완료"  # ⚪`).

---

### `webapp/static/board.js` — 컬럼 추가

**Analog:** 같은 파일 `columns` 배열 (`board.js:88-127`).

```javascript
// webapp/static/board.js:80-87
  // 컬럼 정의를 **데이터 구조로** 둔다 (sheets_out.py:28-48 의 COLS 관례).
  // 규칙마다 있는 필드가 다르다는 사실이 이 표에 그대로 드러나야, ①의 빈칸이
  // 버그가 아니라 설계상 정상값이라는 게 읽는 사람에게 보인다.

// webapp/static/board.js:102-106
    { title: "계정", field: "acct", width: 95 },
    { title: "규칙", field: "rules", width: 85 },
    { title: "상품명", field: "title", minWidth: 200, widthGrow: 5, tooltip: true },
    { title: "노출", field: "imp", hozAlign: "right", width: 90,
      sorter: "number", sorterParams: 빈칸아래, formatter: 정수 },
```

**formatter 3종이 이미 있다** (`board.js:50-73`): `정수` · `비율` · `예아니오`.
**상태 열 formatter 는 네 번째로 같은 자리에 추가해라.** `빈칸이면()` 가드를 반드시 통과시켜라:

```javascript
// webapp/static/board.js:50-56
  // 값이 없는 칸은 **빈칸**이다. ... 0 으로 대체하지도 않는다 — "노출 0 이었다" 는
  // 판정처럼 보이는데, 실제로는 숫자가 존재하지 않는다.
  function 빈칸이면(v) { return v === null || v === void 0 || v === ""; }
```

**필터에 상태·해소여부를 더하는 자리** (`board.js:165-186`) — **함수 하나로 합쳐야 한다**:

```javascript
// webapp/static/board.js:167-169
    // 세 조건을 함수 하나로 합친다. 필터를 따로 걸면 해제 순서에 따라
    // 하나가 남아 "왜 안 보이지" 가 된다.
    table.setFilter(function (d) {
```

**D-08 회색 표시 = 기본 선택에서 제외:** `selectableRows: true` (`board.js:141`) 와
`titleFormatterParams: { rowRange: "visible" }` (`board.js:99`) 의 주석이 "선택 범위" 함정을 이미
전부 적어 놨다. **기작업 상품을 선택에서 빼는 로직은 화면이 아니라 서버(`flow.check_limits` 자리)에 둬라** —
`board.js:136-140` 이 같은 판단을 적고 있다: *"숫자(상한)를 주지 않는다: 상한은 화면이 아니라 서버
`flow.check_limits` 가 설정값으로 건다(D-08). 여기 숫자를 박으면 설정을 고쳐도 화면이 안 따라온다."*

---

### `.claude/skills/bulsaja-detail-page/scripts/detail_batch.py:46-48` (CLI 수정 3줄)

**Analog:** `.claude/skills/product-name/scripts/run_names.py:40-46` — **같은 모듈을 같은 방식으로
이미 부르고 있다. 새 패턴을 발명하지 말고 그대로 복사해라.**

**고칠 것 (현행):**

```python
# .claude/skills/bulsaja-detail-page/scripts/detail_batch.py:45-48
# 불사자 MCP 클라이언트는 카테고리 교정 스킬의 것을 재사용
SKILL_SCRIPTS = r"C:\Users\workspace\.claude\skills\bulsaja-category-fix\scripts"
sys.path.insert(0, SKILL_SCRIPTS)
from bulsaja_mcp import BulsajaMCP  # noqa: E402
```

**베낄 관용구 (실재·검증됨):**

```python
# .claude/skills/product-name/scripts/run_names.py:40-47
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILLS_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", ".."))
BULSAJA_SCRIPTS = os.path.join(SKILLS_DIR, "bulsaja-category-fix", "scripts")
KEYWORD_SCRIPTS = os.path.join(SKILLS_DIR, "keyword-pick", "scripts")

sys.path.insert(0, KEYWORD_SCRIPTS)
sys.path.insert(0, BULSAJA_SCRIPTS)
sys.path.insert(0, SCRIPT_DIR)
```

`os` 는 `detail_batch.py:35` 에 이미 import 돼 있다 → **순수 3줄 치환. import 추가 없음.**

**같이 고칠 것 (docstring 함정):** `detail_batch.py:31` 이 *"용쌤 계정: python run_yong.py …"* 라고
안내하는데 **이 맥북엔 `bulsaja-yongssaem` MCP 항목이 없다** (RESEARCH §STATE-01 실측).
그 줄을 따라 하면 실패한다. 한 줄 고쳐라.

**검증:** `--help` 가 exit 0 (모듈 최상위 import 라 `--help` 만으로 증명된다. 크레딧 0, 쓰기 0).

---

### `webapp/tests/test_join.py` · `test_state.py` (test, unit)

**Analog:** `webapp/tests/test_board.py` — **파일 IO 없이 순수 함수만 때린다.**

**모듈 docstring 패턴** (`test_board.py:3-13`) — "픽스처에 일부러 심어 둔 함정"을 열거한다:

```python
# webapp/tests/test_board.py:3-13
"""보드 투영(`webapp/board.py`) 검증 — 파일 IO 없이 순수 함수만 때린다.

`fake_result_json` 픽스처(Plan 01-01)가 주는 dict 하나로 전부 끝난다.
실제 `~/python_work/data` 를 열지 않으므로 회차 파일이 없어도 돌고, 빠르다.

픽스처에 일부러 심어 둔 함정 4종을 각각 하나씩 겨눈다:
  (a) ①·⑥ 행에 `imp`/`clk`/`ctr`/`rank`/`cost` 가 **아예 없다** (BOARD-01)
  (b) 설정에 없는 가짜 5번째 계정 `zzfake` (BOARD-02)
  (c) 같은 `adId` 가 ②와 ③에 동시에 들어 있다 (PATTERNS §C-2 / T-1-21)
  (d) 한 상품에 ①소재 2개 + ③소재 1개 (D-06 의 rule1_count)
"""
```

→ **Phase 3 판 함정 목록** (픽스처에 심어야 할 것):
  (a) `aiImageGenerated` **키 자체가 없는** workdata
  (b) `{ai: True, translated: '1'}` — 판정 순서 역전 탐지용
  (c) `imageTranslated` 가 **문자열 `'0'`** — `bool('0')` 함정
  (d) 가짜 광고그룹명 (`zzfake` 계열) — 리터럴 가드 회피
  (e) 같은 번호를 쓰는 광고그룹 2개 — 중복제거 검증
  (f) 번호가 불사자에 없는 그룹 · 제외 그룹(미조회) — 사유 3종 분리

**실패 메시지가 원인을 말하게 하는 헬퍼** (`test_board.py:34-39`):

```python
# webapp/tests/test_board.py:34-39
def _행(rows, acct, mpid):
    """접힌 행 하나를 (계정, 상품) 으로 집어 온다. 없으면 테스트를 세운다."""
    found = [r for r in rows if r["acct"] == acct and r["mallProductId"] == mpid]
    assert len(found) == 1, f"{acct}/{mpid} 가 {len(found)}줄이다 (1줄이어야 한다)"
    return found[0]
```

**"이 값이면 두 번 셌다" 식 단언** (`test_board.py:110-113`) — **기대값 옆에 틀린 값도 적는다:**

```python
# webapp/tests/test_board.py:110-113
    assert dup["imp"] == 25850            # 51,700 이면 두 번 셌다
    assert dup["clk"] == 60               # 120 이면 두 번 셌다
    assert dup["cost"] == 10087           # 20,174 면 두 번 셌다
```

→ `test_state.py` 판: `assert 상세상태(...) == "AI가공완료"  # "단순번역만" 이면 판정 순서가 뒤집혔다`

---

### `webapp/tests/test_index.py` (test, unit + fake clock)

**Analog:** `test_jobs.py` — `잡판` 픽스처(위 §`bulsaja_index.py` 참조) + 시간 주입.

**"문자열 검사로 때우지 않는다" 규율** (`test_jobs.py:474-478`):

```python
# webapp/tests/test_jobs.py:474-478
def test_자식_환경에_버퍼링해제가_들어간다(잡판, tmp_path):
    """`spawn` 이 실제로 환경변수를 주입하는지 자식에게 물어본다.

    문자열 검사(`'PYTHONUNBUFFERED' in 소스`)로 때우지 않는다 — 그건 주석에도 걸린다.
    """
```

→ `test_초당4회_상한` 도 **소스에 `0.26` 이 있나** 를 보면 안 된다. **가짜 시계를 주입하고
호출 간격을 실제로 재라.**

**폴링 헬퍼** (`test_jobs.py:44-52`) — 필요하면 그대로 쓴다.

---

### `webapp/tests/test_cli_shim.py` (test, smoke)

**Analog:** `webapp/tests/test_cli_patch.py` (276줄) — CLI 를 subprocess 로 때리는 유일한 기존 테스트.

**검증:** `.venv/bin/python3 .claude/skills/bulsaja-detail-page/scripts/detail_batch.py --help` 가 exit 0.
⚠️ **`sys.executable` 을 쓰지 마라** — `test_argv.py:175-187` 이 웹앱 런타임에서 그걸 금지하고,
테스트도 `.venv-web` 인터프리터로 CLI 를 띄우면 무의미하다. `argv.PY_CLI` 를 쓰거나
`paths.repo_root() / ".venv" / "bin" / "python3"` 를 직접 계산해라.

---

### `webapp/tests/fixtures/` (fixture)

**Analog:** `webapp/tests/fixtures/result_min.json` + `conftest.py:29-37`.

```python
# webapp/tests/conftest.py:29-37
@pytest.fixture
def fake_result_json() -> dict:
    """`result_min.json` 을 파싱한 dict.

    파일 IO 없이 순수 함수(보드 투영·집계)를 때릴 때 쓴다.
    매번 새로 파싱한다 — 테스트가 dict 를 고쳐도 다음 테스트에 안 샌다.
    """
    return json.loads(RESULT_MIN.read_text(encoding="utf-8"))
```

**🔴 가짜 이름 규약 — 이게 리터럴 가드를 통과시키는 방법이다.**
`result_min.json` 에는 **진짜 계정 4개 + 가짜 1개(`zzfake`)** 가 섞여 있다. 가짜를 넣는 이유는
"코드에 안 박혔다"를 **증명**하기 위해서다 (`test_board.py:74-98`).

⚠️ **Phase 3 픽스처가 진짜 마켓그룹명·계정 닉네임을 그대로 담으면 리터럴 가드와 충돌한다.**
VALIDATION §Wave 0 가 경고한 그대로다. 방법:
- 광고그룹명 58종 픽스처는 **번호 체계만 실물, 이름은 가짜**로 (`판매상품_15-2_zzfakecompany`)
- 불사자 마켓그룹 86개도 같은 방식 (`15번_zzfake15-2`)
- **기대 계정 닉네임은 픽스처에도 가짜**로 (`zzfake닉`) — `settings.cfg` 를 monkeypatch 해서 주입
- ⚠️ 단 **번호 추출 정규식 전수 테스트**는 실제 포맷 3종(`판매상품_NN-N_`·`NN-N ` 공백·`1000개_NN-N_`)을
  반드시 커버해야 한다. RESEARCH §광고그룹명 번호 추출 실측 근거.

**`conftest.py` 의 "tmp 밖을 못 만진다" 원칙** (`conftest.py:4-9`) — 새 픽스처도 이걸 지켜라:

```python
# webapp/tests/conftest.py:4-9
"""웹앱 테스트 공통 픽스처.

원칙 하나: **테스트는 실제 `~/python_work/data` 를 절대 만지지 않는다.**
`tmp_run_dir` 이 monkeypatch 로 `paths.data_root` 를 tmp_path 로 갈아끼우고,
모든 파일 접근은 그 아래에서만 일어난다. 여기가 뚫리면 테스트 한 번에
실제 회차의 `before_bids_*.json` 백업이나 ledger 가 오염될 수 있다."""
```

---

## Shared Patterns (여러 파일에 공통으로 적용)

### 공유 1 — "웹앱은 CLI 산출물을 읽을 뿐" (세 번째 길)

**Source:** `webapp/board.py:8-12` · `webapp/routes/board.py:20-23`
**Apply to:** `webapp/join.py` · `webapp/state.py` · `webapp/bulsaja_index.py` · `webapp/board.py`

```python
# webapp/board.py:8-12
이게 STACK.md 의 "세 번째 길" 이다. 보드 데이터는 CLI 를 실행해서도, CLI 모듈을 불러와서도
얻지 않는다. CLI 가 **이미 써 둔 산출물**을 읽을 뿐이다. 그래서 이 모듈은 네트워크도
크레딧도 광고비도 0 이고, 회차 파일이 없으면 빈 목록을 돌려줄 뿐 아무것도 고장내지 않는다.
```

→ **§🔴① 의 결론(a)이 이 패턴의 자연스러운 연장이다.** 인덱스도 CLI 가 써 두고 웹앱은 읽는다.

---

### 공유 2 — 리터럴 가드 3종. **새 파일은 리스트에 넣어야 걸린다**

**Source:** `test_board.py:26-31` · `test_paths.py:277-290` · `no_commit_guard.sh`
**Apply to:** 새로 만드는 **모든 런타임 파일**

**(a) 계정 가드 — `test_board.py:24-31`. 이 리스트에 안 넣으면 가드가 있는 척만 한다:**

```python
# webapp/tests/test_board.py:23-31
# 이 플랜이 만드는 **런타임 경로** 전부. 계정 alias 가 여기 한 글자라도 박히면
# `~/.eroom/naver-ads.json` 에 계정을 더해도 화면이 안 따라온다 (BOARD-02).
# 테스트 파일 자신은 대상이 아니다 — 픽스처를 단언하려면 alias 를 적어야 한다.
런타임_파일들 = [
    WEBAPP / "board.py",
    WEBAPP / "routes" / "board.py",
    WEBAPP / "templates" / "board.html",
    WEBAPP / "static" / "board.js",
]
```

**추가할 것:** `join.py` · `state.py` · `bulsaja_index.py` · (새 라우트/템플릿/JS 가 생기면 그것도)
그리고 **기대 불사자 닉네임도 같은 방식으로 훑어라** (ENG-08 / VALIDATION 행).

⚠️ 위 리스트는 `f.is_file()` 로 없는 파일을 건너뛴다(`test_board.py:91-92`) — **Wave 0 에서 미리
추가해도 red 가 안 난다.** 플랜 순서를 걱정하지 말고 먼저 넣어라.

**(b) 숫자 가드 — `test_paths.py:277-290`. `webapp/**` 의 `.py`/`.html`/`.js` 를 전문 substring 으로 훑는다.
주석도 잡는다:**

```python
# webapp/tests/test_paths.py:277-290
def test_상한_숫자가_settings_밖에_리터럴로_박혀있지_않다():
    """D-08: 상한은 설정파일로 조정 가능해야 한다.
    다른 파일에 1500 이 박히면 workspace.toml 을 고쳐도 동작이 안 바뀐다.
    이 테스트는 Wave 1~7 이 파일을 더해도 계속 감시한다."""
    금지 = {str(settings.DEFAULTS["per_account_limit"]), str(settings.DEFAULTS["port"])}
    루트 = Path(paths.__file__).resolve().parent
    for f in list(루트.rglob("*.py")) + list(루트.rglob("*.html")) + list(루트.rglob("*.js")):
        if f.name == "settings.py" or "tests" in f.parts or "vendor" in f.parts:
            continue
```

⚠️ **새 설정값을 `금지` 집합에 더하면 오탐이 난다.** `mcp_batch_size: 50` · `page_size: 50` 을 넣으면
`50` 이라는 두 글자가 웹앱 전체에서 금지된다 (`width: 50`, `limit=50`, 주석의 "50코드"…).
**숫자 가드에 추가할 값은 신중히 골라라** — `index_excluded_groups`(문자열)와 `expected_bulsaja_nick`
(문자열)은 안전하고, 작은 정수는 위험하다.

**(c) `no_commit_guard.sh`** — `webapp/tests/` 트리에 `--commit` 리터럴 0건. Phase 3 이 쓰기 CLI 를
안 부르니 직접 영향은 없지만, **테스트가 실행 플래그 리터럴을 못 쓰는 관용구**는 그대로다:

```python
# webapp/tests/test_argv.py:25-27
# 가드가 스캔하는 문자열을 이 파일에 남기지 않으려고 런타임에 조립한다.
실행플래그 = "--" + "commit"
```

**(d) 셸 경유 금지 — `test_argv.py:159-171` · `175-187`.** 새 파일에 `shell=True`·`os.system(`·
`sys.executable` 이 있으면 red.

---

### 공유 3 — 설정값은 `settings.DEFAULTS` + `cfg()` 한 곳에서

**Source:** `webapp/settings.py:18-25` · `47-64`
**Apply to:** `join.py` · `state.py` · `bulsaja_index.py` · 인덱스 CLI · `board.html` · `board.js`

```python
# webapp/settings.py:18-25
DEFAULTS = {
    "port": 8765,                  # 127.0.0.1 전용. 인증이 없으므로 외부 바인드 금지
    "per_account_limit": 1500,     # D-08 — 1회 실행 계정별 쓰기 상한
    "stale_days": 8,               # 회차가 이보다 오래되면 보드에서 경고 (D-16)
    "poll_interval": 0.4,          # 로그 tail 폴링 간격(초)
    "job_log_dir": "webapp-logs",  # 잡 로그 루트 (.gitignore 대상)
    "db_path": "webapp.db",        # 잡 레지스트리 (.gitignore 대상)
}
```

**Phase 3 이 더할 키 (VALIDATION §Wave 0):**

| 키 | 값 | 비고 |
|---|---|---|
| `expected_bulsaja_nick` | **`""`** | ⚠️ **빈 문자열이어야 한다.** `cfg(..., required=True)` 가 `""` 을 "비었다"로 보고 KeyError 를 던진다(`settings.py:57-61`). 실제 닉네임은 `workspace.toml [webapp]` 에만 (§🔴③) |
| `mcp_min_interval` | `0.26` | 초당 4회 하한 |
| `mcp_retry_after` | `21` | 서버 `Retry-After: 20` + 1초 |
| `mcp_batch_size` | `50` | `find_by_code` 상한 · 페이지 크기 |
| `index_excluded_groups` | `[]` | **D-18. 기본이 빈 리스트여야 한다** — 그룹명/ID 를 DEFAULTS 에 박으면 그게 리터럴이다 |

⚠️ `index_excluded_groups` 의 빈 리스트가 "전부 제외"로 읽히지 않게 해라 — `argv.py:79-84` 와
`jobs.py:389-395` 가 경고하는 "빈 값이 전량이 되는" 부류의 거울상이다. **빈 리스트 = 제외 없음.**

**`required=True` 규율** (`settings.py:52-55`):

```python
# webapp/settings.py:52-55
    """... required=True 인데 비어 있으면 KeyError — 배포본처럼 값이 비워진 환경에서
    "조용히 기본값으로 돌다가 가드가 없는 채로 쓰는" 사고를 막는다 (위협 T-1-12)."""
```

**모듈 상수를 쓸 거면 `reload()` 도 같이 고쳐야 한다** (`settings.py:72`):

```python
# webapp/settings.py:72
    global PORT, PER_ACCOUNT_LIMIT, STALE_DAYS, POLL_INTERVAL, JOB_LOG_DIR, DB_PATH
```

→ `test_paths.py:255-265` 가 `workspace.toml` 로 덮이는지를 검증한다. 새 상수도 같은 테스트를 달아라.

---

### 공유 4 — 잡 계약 (호출 가능한 함수 · HTTP 모름 · flush · 파일로 로그)

**Source:** `webapp/jobs.py:3-8` · `251-300` · `webapp/logtail.py:73`
**Apply to:** 인덱스 구축 잡 전체

```python
# webapp/jobs.py:3-8
"""작업(잡) 엔진 — CLI 를 자식 프로세스로 띄우고 그 생사를 SQLite 에 적는다.

**이 모듈은 HTTP 를 모른다.** 웹 프레임워크를 import 하지 않고, 요청 객체도 받지 않는다.
`create_job()` 은 그냥 부를 수 있는 함수고, 라우트는 그걸 얇게 감싸기만 한다 (D-17 / ENG-07).
v2 의 APScheduler 가 **같은 함수**를 부를 것이기 때문이다"""
```

> `test_jobs.py:107-109` 가 기계로 집행: `jobs.py` 본문에 `fastapi`/`starlette`/`APIRouter`/
> `HTTPException` 이 0건이어야 한다. **`join.py`·`state.py`·`bulsaja_index.py` 에도 같은 테스트를 걸어라.**

**`spawn` 의 인자 5개는 전부 실측으로 정해졌다** (`jobs.py:252-278`). 인덱스 잡도 그대로 탄다:

```python
# webapp/jobs.py:293-302
        return subprocess.Popen(
            argv_list,
            cwd=str(paths.repo_root()),
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
            stdout=fh,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
```

- `start_new_session=True` → `uvicorn --reload` 재시작에도 3시간 32분짜리 자식이 산다 (Pitfall 7)
- 로그는 **파일**로. 파이프 금지 → "브라우저 닫았다 재접속"이 성립 (`jobs.py:274-278`)

**SSE 는 `logtail` 을 그대로 쓴다** (`logtail.py:73` `read_from(path, offset)` · `logtail.py:120`
`sse_generator(job_id, request)`). 새로 짜지 마라.

**실패를 삼키는 기준** (`logtail.py:86-91`):

```python
# webapp/logtail.py:86-91
    """실패(파일 없음·디렉터리·권한)는 **예외 없이 `("", offset)` 으로 폴백한다.**
    로그를 못 읽는 것은 돈으로 이어지지 않는다(저장소 S-2 판별 기준). 여기서
    예외를 올리면 작업이 시작되자마자 스트림이 죽고, 사용자는 "작업이 멈췄다"로
    오독한다 — 실제로는 잘 돌고 있는데."""
```

→ **이 기준을 인덱스에 적용하면 정반대 결론이 나온다.** 429 로 빠진 상품은 **돈으로 이어진다**
(Pitfall 3: 멀쩡한 광고그룹을 지우러 간다 = 되돌릴 수 없는 손실). **삼키지 마라. 미조회로 명시 기록.**

---

### 공유 5 — CDP 하네스 (화면 검증)

**Source:** `webapp/tests/board_cdp.sh` + `board_cdp.mjs`
**Apply to:** 상태 열 · 해상률 배너 · 계정 표시

```bash
# webapp/tests/board_cdp.sh:1-19
# 보드 브라우저 동작 검증 — 헤드리스 크롬을 띄워 **실제 JS 를 실행**하고 확인한다.
# 쓰는 법 (터미널 2개):
#   A) CT_DEV_TOKEN=devtoken123 ./webapp/run-webapp.sh
#   B) CT_DEV_TOKEN=devtoken123 bash webapp/tests/board_cdp.sh
#
# 왜 필요한가: 2026-09-20 에 "건수 배지가 필터보다 한 스텝 뒤처지는" 버그가 있었다.
# 필터를 바꾸면 숫자가 *움직이긴 해서* 육안 확인으로는 PASS 가 나왔다.
# 두 번 연속 바꿔 직전 값과 대조해야만 드러나는 종류다 — 그래서 기계가 본다.
#
# 변수·함수 이름을 한글로 쓰지 않는다. macOS 기본 bash 는 3.2 라 비ASCII 식별자에서
# "command not found" 로 죽는다(security_curl.sh 에서 실측한 교훈). 설명만 한국어다.
```

⚠️ **쉘 스크립트 식별자는 ASCII.** 파이썬은 한글 이름을 쓰지만 bash 3.2 는 죽는다.

---

## No Analog Found

| 파일 | 역할 | 흐름 | 사유 |
|---|---|---|---|
| — | — | — | 없음. 전부 유사 파일이 있다 |

다만 **패턴 공백이 하나 있다:** 이 저장소에 **"웹앱 프로세스가 외부 HTTP API 를 직접 부르는"
기존 코드가 0건**이다. `board.py`·`routes/board.py`·`flow.py` 전부 파일 읽기뿐이고, 모든 네트워크는
CLI 자식 몫이다. §🔴① 과 합치면 결론이 같다 — **그 공백은 버그가 아니라 설계다. 채우지 마라.**

---

## Metadata

**Analog search scope:** `webapp/**` · `webapp/tests/**` · `.claude/lib/eroomlib/**` ·
`.claude/skills/{bulsaja-detail-page,bulsaja-category-fix,product-name}/scripts/**` ·
`.venv-web/lib/python3.12/site-packages/` (의존성 실측)
**Files scanned:** 24 (읽기 전용)
**Pattern extraction date:** 2026-09-21
