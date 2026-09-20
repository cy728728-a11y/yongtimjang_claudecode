---
phase: 01-board-bid-raise
reviewed: 2026-09-20T22:10:00+09:00
depth: standard
files_reviewed: 28
files_reviewed_list:
  - webapp/__init__.py
  - webapp/argv.py
  - webapp/board.py
  - webapp/flow.py
  - webapp/jobs.py
  - webapp/logtail.py
  - webapp/main.py
  - webapp/paths.py
  - webapp/security.py
  - webapp/settings.py
  - webapp/routes/__init__.py
  - webapp/routes/board.py
  - webapp/routes/health.py
  - webapp/routes/jobs.py
  - webapp/static/board.js
  - webapp/templates/board.html
  - webapp/templates/_bid_macros.html
  - webapp/templates/_job_panel.html
  - webapp/templates/_job_status.html
  - webapp/templates/_preview_table.html
  - webapp/templates/_result_table.html
  - webapp/templates/_revert_table.html
  - webapp/run-webapp.sh
  - webapp/pytest.ini
  - .claude/skills/naver-ads-weekly/scripts/bids.py
  - .claude/skills/naver-ads-weekly/scripts/run_ads.py
  - webapp/tests/*.sh
  - webapp/tests/*.mjs
findings:
  critical: 2
  warning: 11
  info: 6
  total: 19
status: fixed
fixed_at: 2026-09-20
fixed:
  critical: 2
  warning: 11
  info: 0          # 범위 밖 (지시로 손대지 않음)
  skipped: 0
  no_change_needed: 0
fix_commits: 11
---

# Phase 01: 코드 리뷰 — 보드 + 입찰가 인상 버튼

**리뷰:** 2026-09-20 · **깊이:** standard · **상태:** issues_found

## 요약

먼저 결론. **틀은 잘 짜였다.** 대상 파일 하나(D-11), 미리보기→실행 결합, 되돌리기 범위 가드,
argv 단일 조립점, Origin/토큰 3층 — 네가 걱정한 "범위가 조용히 넓어지는" 경로는
**웹앱 쪽에서는** 거의 다 닫혀 있다. `only_ads is not None` / `_load_only_ads` / `run_bids`의
`if only_ads is not None:` 이 세 군데가 전부 `None`과 빈 집합을 구분하고 있어서,
0건이 전량이 되는 그 버그는 **재발 안 한다.** 확인했다.

그런데 **잡 엔진에 재현 가능한 경합이 하나 있다.** 전역 쓰기 락이 풀린다.
직접 돌려서 재현시켰다 — 아래 CR-01. 이게 이번 리뷰의 본론이다.

그리고 하네스 쪽. 네가 말한 "영원히 통과하는 검사"를 **세 건 더** 찾았다 (WR-05·06·07).
그중 하나는 하필 되돌리기 하네스의 **제일 강한 안전 주장**("되돌리기 잡이 한 건도 안 생겼다")이다.

---

## 처리 결과 (2026-09-20 · 커밋 11개)

Critical 2 + Warning 11 = **13건 전부 fixed.** Info 6건은 범위 밖이라 손대지 않았다.
**skipped 0 · no_change_needed 0 · 리뷰 반박 0건** — 재현한 것은 전부 리뷰가 맞았다.

| ID | 결과 | 커밋 | 음성 대조군(red 확인) |
|---|---|---|---|
| CR-01 | **fixed** | `54b2073` | 3개 — INSERT 를 running 으로 되돌리면 `창안=[(id,'orphaned',None)]` + 두 번째 쓰기 잡이 들어감 / 가드를 running 만 보게 하면 `DID NOT RAISE` / starting 타임아웃을 지우면 영원히 BusyError |
| CR-02 | **fixed** | `6774ab3` | 3개 — 읽기 실패를 삼키면 `aborted is None` / `write_text` 로 되돌리면 "os.replace 를 안 거쳤다" / 화면 배너를 지우면 "중단한 계정이 화면에 없다" |
| WR-01 | **fixed** | `6bdfc68` | 1개 — `compare_digest` 로 되돌리면 `TypeError` |
| WR-02 | **fixed** | `f64ed84` | 1개 — 가드를 지우면 `DID NOT RAISE ValueError` |
| WR-03 | **fixed** | `6f8327c` | 3개 — 상태 가드를 빼면 `running is not True` / 템플릿 순서를 되돌리면 "running 이 error 에 밀렸다" / 사유에 경로를 붙이면 기대값 불일치 |
| WR-04 | **fixed** | `09e72e1` | 2개 — 옛 문구로 되돌리면 `'ownway1 0건' in …` 실패 / 라우트가 `by_account` 를 안 넘기면 409 본문만 빨감 |
| WR-05 | **fixed** | `2862640` | 1개(시나리오 그대로 재현) — 창 20건 밖으로 밀리는 조건에서 **옛 검사 "PASS (뚫렸다)"**, 새 검사 `새로 생긴 것 1건 [FAKENEW]` |
| WR-06 | **fixed** | `2862640` | 1개 — 2차를 아예 안 누르면 **옛 검사 "PASS (뚫렸다)"**, 새 검사 V-PRE-15a·15 둘 다 FAIL |
| WR-07 | **fixed** | `c0d69b7` + `766fa72` | 2개 — 틀린 토큰이면 "보드를 못 받았다(검사 불가)" / 서버를 뽑으면 healthz 게이트에서 멈춤 |
| WR-08 | **fixed** | `c0d69b7` | 2개 — 래퍼 한 겹(`_작업만들기`)을 낀 GET 에서 **옛 스캐너 "PASS (뚫렸다)"**, 새 스캐너 `→ Popen · create_job · spawn` / docstring 80줄 뒤의 직접 호출도 새 스캐너만 잡음 |
| WR-09 | **fixed** | `e0d2c61` | 1개 — `apply_revert` 를 옛 모양으로 되돌리면 3종 red(429 재시도 실패 · 호출 `1 != 4` · 같은 경로 아님) |
| WR-10 | **부분 fixed** | `b772bcf` | 2개 — `read_from` 을 루프 위로 되돌리면 "이벤트 루프 스레드에서 돌았다: {'MainThread'}" / 상한을 지우면 `28890 <= 1067` 실패. **`await anyio.sleep(0)` 한 줄은 대조군이 빨개지지 않는다** — 아래 참조 |
| WR-11 | **fixed** | `c0d69b7` | 1개(부수효과 실측) — 옛 c2 를 한 번 쏘면 잡 레지스트리 최신 id 가 바뀌고, 새 c2 는 안 바뀜 |
| IN-01~06 | **범위 밖** | — | 지시대로 손대지 않았다 |

### 정직하게 남기는 것 (WR-10)

`await anyio.sleep(0)` 한 줄은 **음성 대조군을 빨갛게 만들지 못했다.** 바로 위의
`anyio.to_thread.run_sync` 가 이미 매 바퀴 await 점이라, 그 줄만 떼어내도 다른 태스크가
그대로 돈다(실측: 그 줄을 지운 상태에서 끼어든 횟수 50/50). 그래서 그 줄에 대한 assert 를
**쓰지 않았다** — 영원히 통과하는 검사를 하나 더 만드는 것이 이 리뷰가 잡아낸 바로 그 병이다.
줄 자체는 남겼다(나중에 읽기를 다시 동기로 바꾸는 사람이 있으면 그때 유일한 양보 지점이
된다). 코드 주석에도 "보험이다 · 대조군이 안 빨개진다" 고 적어 뒀다.

### 고치다 새로 만든 버그 하나 (자백)

WR-07 1차 수정(`c0d69b7`)에서 넣은 `printf '%s' "$body" | grep -q` 가 flaky 했다.
`set -o pipefail` 인데 `grep -q` 는 매치 즉시 끝나므로, 2.4MB(6,945행)를 아직 쓰고 있던
`printf` 가 SIGPIPE 로 죽어 파이프라인 종료코드가 141 이 된다 — 보드를 멀쩡히 받았는데
"못 받았다" 로 빨개진다. **실측: 같은 응답으로 8회 돌려 2회가 141.**
`766fa72` 에서 본문을 mktemp 파일로 받아 파일을 grep 하도록 고쳤다(연속 5회 9 PASS).
WR-11 이 말한 "보안과 무관한 이유로 빨개지는 스크립트" 를 내가 한 번 만들었다가 지웠다.

### 리뷰가 맞았음을 재현으로 확인한 것

- **CR-01** — 리뷰의 실측 출력(`[('…','orphaned', None)]` + 두 번째 쓰기 잡 접수)을
  pytest 에서 그대로 재현했다. 확률 테스트가 아니라 `spawn` 안에서 창을 정확히 한 번
  벌리는 결정적 재현이다.
- **WR-05 · WR-06 · WR-08** — 세 건 모두 **옛 검사가 PASS 하고 새 검사가 FAIL** 하는
  것을 같은 조건에서 나란히 찍었다. "영원히 통과하는 검사" 라는 판정이 정확했다.
- **WR-01** — `non-ascii t -> 500` 실측 재현, 고친 뒤 403.

---

## Critical

### CR-01: 도는 잡이 `orphaned` 로 찍히고 전역 쓰기 락이 풀린다 (재현함)

> **[fixed · `54b2073`]** INSERT 를 `starting` 으로 두고 spawn 성공 뒤 `pid`+`status='running'` 을 한 UPDATE 로. 전역 가드는 `LIVE_STATUSES=('running','starting')` 둘 다 본다. `_reap` 은 `starting` 의 생사를 묻지 않고 `STARTING_TIMEOUT_SEC`(60초)만 본다 — (b) 요구(띄우다 죽은 행이 가드를 영영 잡지 않게)를 그걸로 지킨다. 리뷰가 제안한 모양 그대로다. 재현 테스트 3종 추가, 음성 대조군 3개 전부 red 확인.

**파일:** `webapp/jobs.py:194-212` · `webapp/jobs.py:460-500`

**무엇이 잘못됐나**

`create_job` 은 잡 행을 `status='running'` · `pid=NULL` 로 INSERT 하고 **트랜잭션을 닫은 뒤에**
`spawn()` 을 부른다. pid 는 그 다음 UPDATE 로 들어간다. 그 사이 창에서 누가 `_reap` 을 돌리면:

```python
proc = _PROCS.get(r["id"])     # 아직 spawn 전 → None
...
if not _alive(r["pid"]):       # pid 가 NULL → _alive(None) → False
    UPDATE jobs SET status = 'orphaned' ...
```

멀쩡히 뜰 잡이 `orphaned` 로 찍히고, **그 상태는 되돌아오지 않는다** — `spawn` 뒤 UPDATE 는
`pid` 만 쓰고 `status` 는 안 건드린다.

**실패 시나리오 (실측)**

`_reap` 은 폴링마다 돈다 — `GET /jobs/{id}`(2초), `GET /`, `GET /jobs`,
그리고 **SSE 스트림이 `POLL_INTERVAL=0.4초` 마다** `jobs.job_status` 를 부른다
(`logtail.py:137`). 즉 앞 작업의 로그창이 열려 있는 상태(= 다음 버튼을 누르는 바로 그 상태)에서는
초당 2.5회씩 `_reap` 이 돈다. 재현 결과:

```
폴링 중 상태:   [('d1611ab1', 'orphaned', None)]
spawn 이후 상태: [('d1611ab1', 'orphaned', 41515)]    ← pid 는 살아 있는데 orphaned
두 번째 쓰기 잡이 들어갔다: 5a69efec   ← 전역 가드 무력
```

그래서 나는 것:

1. **쓰기 잡 두 개가 겹친다.** 네가 `jobs.py:49-56` 에 직접 써 둔 그 사고다 —
   "`run_bids` 가 `before_bids_<alias>.json` 과 `ledger/<alias>.json` 을 읽고-병합하고-통째로
   다시 쓰는데 락이 없다. 쓰기 잡 두 개가 겹치면 백업 항목이 사라지고 **그 소재는 영영
   되돌릴 수 없다.**" 가드가 있는데 가드가 풀리는 경로가 있는 것이다.
2. **인상 중에 되돌리기가 들어간다.** `post_revert_job` 은 `running` 만 막고
   `orphaned` 는 **일부러 허용한다**(`routes/jobs.py:456-458`, 근거는 "중간에 끊긴 실행이야말로
   되돌려야 한다"). 정상 경로에서는 `orphaned` = pid 사망이라 그 판단이 맞다. 그런데 이 경합이
   만드는 `orphaned` 는 **살아서 PUT 을 날리는 중**이다. 472건 인상 중에 되돌리기가 같은
   ledger 를 read-modify-write 한다.
3. 화면은 "결과 미상 — 작업이 도는 중에 서버가 재시작됐다"(`_job_status.html:66-70`)고
   거짓말한다. 재시작한 적 없다.

**확률:** spawn 창이 수~수십 ms, `_reap` 이 초당 2.5회면 잡 생성당 대략 1~3%. 472건짜리
버튼에 1~3%면 그냥 시간문제다.

**고칠 것**

INSERT 시점 상태를 `running` 이 아닌 값으로 두고, spawn 이 성공한 뒤에 `running` 으로 올려라.

```python
# create_job — ⑤ INSERT
"VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
(job_id, kind, run_dir, ..., "starting", str(log_path), ...)   # ← 'running' 아님

# ⑥ spawn 성공 후
cx.execute("UPDATE jobs SET pid = ?, status = 'running' WHERE id = ?", (proc.pid, job_id))
```

`_reap` 은 `status='running'` 만 보므로 창이 통째로 사라진다. 대신 `starting` 이 영원히
남는 경우(INSERT 와 spawn 사이에 프로세스가 통째로 죽는 경우)를 위해 `_reap` 에 한 줄 더:

```python
# starting 인 채로 60초 넘게 있으면 띄우다 죽은 것이다 — 가드를 영영 잡고 있게 두지 않는다
cx.execute("UPDATE jobs SET status='failed', exit_code=-1, ended_at=? "
           "WHERE status='starting' AND started_at < ?", (_now(), 예순초전))
```

그리고 **전역 가드 쿼리도 `kind IN (...) AND status IN ('running','starting')`** 로 넓혀라.
안 그러면 `starting` 인 쓰기 잡이 가드를 못 잡는다 — 지금 고치려는 그 구멍이 이름만 바뀐다.

---

### CR-02: 백업 파일을 비원자적으로 쓰고, 읽기 실패하면 조용히 새로 만든다

> **[fixed · `6774ab3`]** 읽기 실패 → `aborted: backup_unreadable` 로 중단(덮어쓰지 않는다). 쓰기는 tmp→`os.replace`. 웹앱은 `flow.aborted_accounts` 로 그 사유를 결과·되돌리기 표 맨 위에 띄운다. CLI 회귀 100 → 107 tests 전부 green. 음성 대조군 3개 red 확인.

**파일:** `.claude/skills/naver-ads-weekly/scripts/bids.py:201-216`

※ 이건 **Phase 01 변경분이 아니다** (기존 코드다). 그래도 적는 이유는, 웹앱이 회차 하나에
`bids --commit` 을 여러 번 태우는 구조를 새로 만들었기 때문에 노출이 명확히 커졌기 때문이다.

**무엇이 잘못됐나**

```python
try:
    existing_bk = json.loads(bk.read_text(encoding="utf-8")) if bk.exists() else {}
except Exception as e:
    log(f"  ⚠ 기존 백업 읽기 실패(새로 만든다): {type(e).__name__}: {e}")
    existing_bk = {}          # ← 여기
...
bk.write_text(json.dumps(merged_bk, ...), encoding="utf-8")   # ← 원자적이지 않다
```

`write_text` 는 truncate 후 write 다. 그리고 읽기가 실패하면 **기존 백업을 버리고 덮어쓴다.**

**실패 시나리오**

1. 472건 인상 중 `bk.write_text` 도중에 맥북이 잠들거나 디스크가 차서 쓰기가 반쪽 남는다
   (자식은 `start_new_session=True` 라 서버를 껐다 켜도 안 죽지만, 프로세스가 죽는 경로는 여럿이다).
2. 그 회차 `before_bids_ownway1.json` 이 깨진 JSON 이 된다.
   → `run_revert` 이 파싱 실패 → `{}` 리턴 → **그 계정은 되돌리기 불가.**
   → 웹앱 쪽은 `flow.revert_round_targets` 가 `ValueError` 로 막아 주긴 한다(그건 잘 짠 것이다).
3. **그런데 같은 회차에서 인상을 한 번 더 누르면** 위 `except` 가 걸려 `existing_bk = {}` 가 되고,
   `merged_bk` 에는 **이번 plans 만** 담겨 그 파일을 덮어쓴다. 앞서 올린 소재들의
   원본 `adAttr` 가 **영구히 사라진다.** "같은 키는 먼저 것을 유지한다(Important 1)" 는 규칙이
   파일이 한 번 깨지는 순간 무효가 된다.

저장소에는 이미 원자적 쓰기 관례가 바로 옆에 있다 — `run_ads._dump_preview`(tmp→`os.replace`),
`jobs._write_targets`, `flow.revert_targets_for_job`. 정작 **제일 잃으면 안 되는 파일**만
그 관례를 안 쓴다.

**고칠 것**

```python
    # 읽기 실패는 삼키지 않는다 — 원본을 잃는 쪽이 훨씬 비싸다
    try:
        existing_bk = json.loads(bk.read_text(encoding="utf-8")) if bk.exists() else {}
    except Exception as e:
        log(f"  ✗ 기존 백업을 못 읽었다 — 덮어쓰지 않고 중단한다: {type(e).__name__}: {e}")
        return {"plans": plans, "counts": counts, "committed": 0,
                "aborted": "backup_unreadable"}
    ...
    # 원자적 쓰기 (run_ads._dump_preview 와 같은 관례)
    tmp = bk.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(merged_bk, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, bk)
```

`webapp/flow.py` 쪽은 `aborted` 를 이미 읽을 수 있는 모양이라(`read_preview` 가 dict 통째로
넘긴다) 화면에 사유를 띄우는 건 한 줄이면 된다.

---

## Warning

### WR-01: `GET /?t=<한글>` 이 403 이 아니라 500 이다 (확인함)

> **[fixed · `6bdfc68`]** `security.토큰이같나` 로 바꿨다. 실측 재현 후 고침: `non-ascii t -> 500` → `403`. 쿼리스트링 층 테스트가 통째로 비어 있었다(기존 테스트는 헤더·쿠키만 덮었다).

**파일:** `webapp/routes/board.py:61`

`security.py:46-61` 에 비ASCII 입력으로 `compare_digest` 가 `TypeError` 를 던지는 걸 막으려고
`토큰이같나()` 를 만들어 놓고, **정작 토큰을 처음 받는 자리에서 그 함수를 안 쓴다.**

```python
if t and secrets.compare_digest(t, security.BOOT_TOKEN):
```

실측:

```
non-ascii t -> 500
wrong t     -> 403
good t      -> 303
```

`security.py` 자기 docstring이 말하는 그대로다 — "403 이어야 할 자리에 500 이 나오면
① 거부 경로가 에러 핸들러로 새고 ② 로그가 트레이스백으로 더럽혀진다."
주소창에 한글이 섞여 붙여넣어지기만 해도 난다.

**고칠 것**

```python
if t and security.토큰이같나(t, security.BOOT_TOKEN):
```

### WR-02: `revert_only` 인데 대상 파일이 없으면 조용히 회차 전체가 된다

> **[fixed · `f64ed84`]** 가드를 `create_job` 이 아니라 `_build_argv` 에 뒀다 — argv 를 실제로 조립하는 유일한 지점이고, `argv_override`(테스트 전용) 경로는 애초에 거기를 안 지난다. 반대편도 같이 고정했다: 대상 파일이 있으면 `--only-ads` 가 붙고, `revert_all` 은 대상 파일 없이도 만들어진다(D-14 의 두 번째 버튼).

**파일:** `webapp/jobs.py:348-354`

```python
if kind in ("revert_only", "revert_all"):
    return argv_mod.AdsArgv(..., revert=True, commit=commit,
                            only_ads=targets_path if kind == "revert_only" else None, ...)
```

`targets_path` 가 `None` 이면 `AdsArgv` 가 `--only-ads` 를 **안 붙이고**, CLI 는 그걸
"백업 전량"으로 읽는다(`bids.run_revert:286` — `only_ads is None or ...`).
즉 **kind 이름은 `revert_only` 인데 동작은 `revert_all`** 이 된다. D-12 가 막으려던 바로 그것이다.

**실패 시나리오:** 지금 운영 라우트는 항상 `targets_path_override` 를 넘기므로 **현재는 안 난다.**
다만 v2 의 APScheduler 가 `create_job("revert_only", run_dir=X, commit=True)` 로 부르는
순간(D-17 이 그렇게 부르라고 설계한 모양 그대로다) 회차 전체가 풀린다. 인자 하나 빼먹으면
2,242건이 풀리는 함수 시그니처를 남겨 두는 건, 이 페이즈에서 두 번 난 사고와 같은 종류다.

**고칠 것** — `create_job` 의 kind 검사 근처에 한 줄:

```python
if kind == "revert_only" and targets_path is None:
    raise ValueError("revert_only 에는 대상 파일이 반드시 있어야 한다 — "
                     "대상 없는 되돌리기는 회차 전체다(D-12)")
```

### WR-03: 표 템플릿의 `"도는 중"` 분기는 죽은 코드다 — 대신 절대경로가 화면에 뜬다

> **[fixed · `6f8327c`]** `_산출물` 이 `jobs.LIVE_STATUSES` 면 파일을 안 읽고 `running=True` 를 준다. 세 템플릿 분기를 `running → error` 로 뒤집었고, `read_preview` 사유를 예외 **이름까지만**으로 줄였다. ※ 분기 순서만 떼어낸 대조군은 라우트 경유로는 안 빨개진다(`_산출물` 이 둘을 배타로 만들어서) — 그래서 템플릿을 직접 렌더해 순서를 재는 테스트를 따로 뒀다.

**파일:** `webapp/routes/jobs.py:204-209` · `_preview_table.html:23-28` ·
`_result_table.html:15-21` · `_revert_table.html:17-24`

세 템플릿 모두 `{% if error %}` → `{% elif job.status == "running" %}` 순서인데,
`_산출물()` 이 **도는 중에도 result_path 를 읽으려 하고 파일이 아직 없으니 항상 error 를 채운다.**
그래서 `running` 분기에 도달하는 경우가 없다. 실측:

```
status: running
<p class="stale"><strong>미리보기를 못 읽었다 — FileNotFoundError: [Errno 2] No such file
or directory: &#39;/…/runs/2026-08-30/web/preview_6248ec43-…json&#39;</strong><br>
산출물이 없거나 깨졌다. 빈 표를 결과로 읽지 않게 표를 그리지 않는다.</p>
```

**실패 시나리오:** `board.js:364-382` 의 폴링 한도가 끝나면(미리보기 150회=60초, 실행 3000회)
아직 도는 중인데도 결과를 갈아끼운다. 그러면 사용자는 "산출물이 없거나 깨졌다" 를 보고
**작업이 실패한 줄 알고 다시 누른다** — 실제로는 잘 돌고 있는 중에 두 번째 쓰기 잡을 접수하는
꼴이다(409 로 막히긴 하지만 그 문구는 또 다른 오해를 만든다). 덤으로 내부 절대경로가
화면에 그대로 나간다 — `_load_result`·`read_preview` 가 지키려던 ASVS V7 규칙과 어긋난다.

**고칠 것** — 산출물을 읽기 전에 상태부터 본다.

```python
def _산출물(상태: dict, 없을때: str) -> dict:
    if (상태 or {}).get("status") == "running":
        return {"accounts": {}, "blind": [], "error": None, "running": True}
    ...
```

그리고 템플릿 분기 순서를 `running` → `error` 로 뒤집어라. 파일명은 사유에서 빼라
(`f"{type(e).__name__}"` 까지만).

### WR-04: 되돌리기 범위 가드가 막히면 남는 길이 제일 위험한 버튼뿐이다

> **[fixed · `09e72e1`]** 리뷰 제안대로 `check_revert_scope(..., by_account)` 로 계정별 내역을 싣고, 0건인 계정이 있으면 "소재 스냅샷을 못 읽은 것이다 — 새로 수집(prep)부터" 까지 말한다. 0인 계정이 없으면 그 처방을 안 붙인다(어떤 불일치에나 같은 말을 하는 문구가 되지 않게).

**파일:** `webapp/flow.py:498-511` · `webapp/routes/jobs.py:475-497`

`check_revert_scope` 는 `expected != dry_run_targets` 면 무조건 409 다. 방향은 맞다(fail-closed).
문제는 **풀 길이 없다는 것**이다.

**실패 시나리오:** 인상 성공 472건짜리 실행 잡이 있는데, 그 뒤에 같은 회차로 `prep` 을 한 번
돌려 `accounts/<alias>/ads.json` 이 갈렸다고 하자. `run_revert` 은 소재 스냅샷을 못 읽으면
`{}` 를 리턴하고(`bids.py:281-283`), `revert_dry_run` 은 그 계정을 0 으로 센다.
→ `expected=472 · dry_run=0` → **"이 작업분만 되돌리기" 가 영구히 409.**
그 상태에서 사용자에게 남은 되돌리기 수단은 **"이 회차 전체 되돌리기" 하나뿐**이다 —
D-14 가 "절대 실수로 누르면 안 된다" 고 페이지 맨 아래 접어 둔 그 버튼. 정밀한 도구가
막히면 사람은 무딘 도구를 쓴다.

**고칠 것:** 409 메시지에 계정별 내역을 실어라(`범위["by_account"]` 를 이미 들고 있다).
"어느 계정이 0 이라서 막혔는지" 가 화면에 있어야 사용자가 `prep` 을 다시 돌릴지 판단한다.

```python
flow.check_revert_scope(기대, 범위["targets"])  # →
flow.check_revert_scope(기대, 범위["targets"], by_account=범위["by_account"])
# ScopeError 문구에 "ownway1 0건 / pogeunae 472건 — 0 인 계정은 소재 스냅샷을 못 읽은 것이다" 추가
```

### WR-05: `V-RVT-26`("되돌리기 잡 0건")이 위음성을 낼 수 있다 — 하네스의 제일 강한 주장이다

> **[fixed · `2862640`]** id 집합 비교로 바꿨다. 판정은 **"사전에 없던 revert 잡 id 가 0개"** — 창 밖으로 밀려난 것 때문에 위양성이 나지 않으면서 새로 생긴 것은 무조건 잡는다. 같은 개수 비교를 쓰던 **V-RVT-17 도 같이** 고쳤다(리뷰에 없던 같은 자리다). 시나리오를 그대로 재현: 옛 검사 `PASS (뚫렸다) — 전 1건 / 후 1건`, 새 검사 FAIL.

**파일:** `webapp/tests/revert_cdp.mjs:51-54, 236-239`

전후 비교의 출처가 `GET /jobs` 인데, 그 라우트는 **최근 20건만** 준다
(`routes/jobs.py:556` → `jobs.recent_jobs(20)`).

**실패 시나리오:** 창(20건) 안에 `revert_*` 잡이 이미 1건 이상 있는 상태에서 하네스가 진짜로
되돌리기를 접수해 버리면, 새 잡이 들어오고 **제일 오래된 revert 잡이 창 밖으로 밀려나** 개수가
그대로다 → `사후 === 사전` → **PASS.** "되돌리기 요청은 서버에 한 건도 안 나갔다" 라는 문장이
거짓이 되는데 초록이다. 어제 472건을 실제로 되돌린 뒤라 레지스트리에 `revert_*` 잡이 있는
지금이 정확히 그 조건이다.

**고칠 것** — 개수가 아니라 **id 집합**을 비교해라.

```js
const 되돌리기ID들 = (j) => j.jobs.filter(x=>/^revert_/.test(x.kind)).map(x=>x.id).sort();
// 사전/사후를 집합으로 받아서
check("V-RVT-26", "…", JSON.stringify(사후ID) === JSON.stringify(사전ID), …);
```

### WR-06: `V-PRE-15` 는 어떤 경우에도 통과한다 (영원한 초록)

> **[fixed · `2862640`]** 리뷰 제안대로 표 자리를 비우고 `commit-preview-job` 이 바뀔 때까지 기다린다. 그 대기 자체를 `V-PRE-15a` 로 분리해 따로 판정한다(31 → 32종). 2차를 아예 안 누르는 대조군에서 옛 검사 `PASS (뚫렸다)`, 새 검사 둘 다 FAIL.

**파일:** `webapp/tests/preview_cdp.mjs:186-194, 389-394`

```js
async function 표기다리기(초 = 60) {
  for (...) {
    const 글 = await 평가(`window.__ct.미리보기글()`);
    if (글 && !/만드는 중/.test(글)) { return 글; }   // ← 직전 결과가 그대로 걸린다
```

두 번째 미리보기를 누른 뒤 `표기다리기` 를 다시 부르면, `#preview-body` 에는 **1차 결과가
그대로 남아 있다**(`실행닫기()` 는 `#result` 만 닫는다). 그래서 즉시 1차 텍스트가 반환되고
`글 === 첫결과` 가 참이 된다.

**실패 시나리오:** 2차 미리보기가 아예 접수되지 않았거나, 409 로 거부됐거나, 다른 결과를
냈어도 이 검사는 PASS 다. "dry-run 은 이력을 안 건드린다" 는 **한 번도 검증된 적이 없다.**
`update_streaks` 가 dry-run 에서 파일을 안 쓴다는 것이 이 하네스가 지켜야 할 성질인데,
그걸 지키는 코드가 깨져도 초록이다.

**고칠 것** — 누르기 전에 자리를 비우고, 새 job_id 를 기다려라.

```js
const 이전잡 = await 평가(`document.getElementById("commit-preview-job").value`);
await 평가(`document.getElementById("preview-body").textContent = ""`);
await 평가(`window.__ct.미리보기클릭()`);
// commit-preview-job 값이 이전잡과 달라질 때까지 기다린 뒤에 표를 읽는다
```

### WR-07: `V-SAFE-03`(시크릿 비노출)이 공허하게 통과할 수 있다

> **[fixed · `c0d69b7` + `766fa72`]** 보드(`id="board-rows"`)를 먼저 못박고, `webapp-logs` 를 `$ROOT` 기준 절대경로로 본다(스크립트가 저장소 루트로 `cd` 한다). 로그 디렉터리가 없으면 "로그 검사 못 했다" 고 말한다. ⚠ 1차 수정이 `pipefail` + SIGPIPE 로 flaky 했다 — 2.4MB 본문에서 8회 중 2회가 141. `766fa72` 에서 파이프를 버리고 파일 grep 으로 고쳤다(연속 5회 9 PASS).

**파일:** `webapp/tests/security_curl.sh:150-163`

```bash
curl -s --max-time 10 -H "Cookie: ct_session=$T" "$B/" | grep -q -- "$S" && leaked=1
```

**응답이 보드 페이지인지 확인하지 않는다.** 쿠키가 안 맞으면 본문은
`"토큰이 필요하다 — 서버 기동 로그의 URL 로 들어와라"`(403)이고, 당연히 시크릿이 없으니 PASS 다.
서버를 뽑아 놔도(000, 빈 본문) PASS 다.

**실패 시나리오:** `CT_DEV_TOKEN` 과 서버 토큰이 어긋난 채 돌리면 "시크릿 0건" 이 초록으로
뜬다. 진짜로 보드가 계정 객체를 통째로 렌더하기 시작해도 못 잡는다.

또 `webapp-logs/` 를 상대경로로 본다 — 저장소 루트가 아닌 곳에서 부르면
`[ -d webapp-logs ]` 가 거짓이라 **로그 검사를 조용히 건너뛴다.**

**고칠 것**

```bash
body=$(curl -s --max-time 10 -H "Cookie: ct_session=$T" "$B/")
# 먼저 "이게 진짜 보드다" 를 못박는다 — 아니면 검사 자체가 성립 안 한다
printf '%s' "$body" | grep -q 'id="board-rows"' || { check V-SAFE-03 "보드를 못 받았다(검사 불가)" 1; }
printf '%s' "$body" | grep -q -- "$S" && leaked=1
LOGDIR="$(cd "$(dirname "$0")/../.." && pwd)/webapp-logs"   # 상대경로 금지
```

### WR-08: `V-SAFE-01d` 스캐너는 직접 호출만 본다 — 래퍼 한 겹이면 통과한다

> **[fixed · `c0d69b7`]** 리뷰가 제시한 두 안 중 **강한 쪽**을 골랐다 — `ast` 로 GET 핸들러에서 도달 가능한 함수 집합을 펼친다. 줄 수 상한이 없어지고(ast 가 함수 경계를 안다) 래퍼를 몇 겹 끼워도 안 뚫린다. GET 핸들러를 0개 찾으면 그것도 FAIL 이다(눈먼 스캐너를 초록으로 두지 않는다). 실측: 래퍼 케이스에서 옛 스캐너 PASS, 새 스캐너 `→ Popen · create_job · spawn`.

**파일:** `webapp/tests/security_curl.sh:71-103`

`RISK = create_job|spawn|Popen|run_bids|run_revert` 를 GET 핸들러 본문에서 찾는다.
현재 0건인 건 확인했다. 그런데 **이 저장소에는 이미 간접 래퍼가 있다** —
`routes/jobs.py:322` 의 `_작업만들기(request, kind, req)`. 누가 GET 핸들러에서
`return _작업만들기(request, "prep", req)` 라고 쓰면 스캐너는 **통과시킨다.**

덤으로 `end = min(j + 60, len(lines))` 라 핸들러가 60줄을 넘으면 그 뒤는 안 본다.
이 파일의 GET 핸들러들은 docstring 이 길어서 이미 20~25줄을 쓴다 — 여유가 생각보다 없다.

**고칠 것:** 호출 대상 대신 **호출 관계**를 보거나(ast 로 GET 핸들러에서 도달 가능한 함수 집합을
계산), 최소한 `RISK` 에 "작업을 만드는 래퍼" 이름을 같이 넣고 60줄 상한을 들여쓰기 기반
블록 끝 탐지로 바꿔라. 지금 문구("상태를 바꾸는 GET 엔드포인트 0건")는 증명한 것보다 세다.

### WR-09: `apply_revert` 에는 재시도가 없다 — `apply_raise` 에는 4회 있다

> **[fixed · `e0d2c61`]** 리뷰 제안대로 `_put_ad` 공용 헬퍼로 뺐다(복사하지 않았다). 인상 쪽과 **같은 3종** 테스트를 되돌리기에도 걸고, "루프를 복사하지 않았다" 는 성질 자체도 고정했다. CLI 회귀 bids 30 → 35 tests.

**파일:** `.claude/skills/naver-ads-weekly/scripts/bids.py:80-86` vs `49-66`

```python
def apply_revert(acct, ad_obj, original_attr):
    st, res = nvad.call(acct, "PUT", ...)     # 한 번 쏘고 끝
    if st in (200, 201): return True, ""
    return False, f"{st} {str(res)[:150]}"
```

`apply_raise` 는 429/5xx/0 을 지수 백오프로 4회 재시도한다. **되돌리기는 안 한다.**

**실패 시나리오:** 472건을 초당 4.3건으로 되돌리는 중에 429 가 하나 뜨면 그 소재는
즉시 `실패` 로 기록되고 **인상된 채로 남는다.** 되돌리기는 사고 대응 경로라 인상보다
회복력이 더 필요한 자리인데 더 약하다. `_revert_table.html:53-57` 이 "같은 버튼을 다시
눌러 재시도할 수 있다" 고 안내하긴 하지만, 그건 사람이 표를 끝까지 읽었을 때 얘기다.

**고칠 것:** `apply_raise` 의 재시도 루프를 그대로 복사하지 말고 공용 헬퍼로 빼서 양쪽이 쓰게 해라.

```python
def _put_ad(acct, ad_obj, body, tries=4):
    st, res = 0, ""
    for attempt in range(tries):
        st, res = nvad.call(acct, "PUT", f"/ncc/ads/{ad_obj['nccAdId']}",
                            params={"fields": "adAttr"}, body=body)
        if st in (200, 201): return True, ""
        if st in (429, 500, 502, 503, 0):
            time.sleep(2 * (attempt + 1)); continue
        return False, f"{st} {str(res)[:150]}"
    return False, f"{st} {str(res)[:150]} (재시도 소진)"
```

### WR-10: SSE 제너레이터가 이벤트 루프에서 blocking 파일 IO 를 한다

> **[부분 fixed · `b772bcf`]** `read_from` 을 스레드로 밀었고(대조군 red 확인: `{'MainThread'}`), 누적 상한 1MB 를 **줄 경계에서** 잘라 붙인다(escape 된 HTML 이라 엔티티가 반 토막 나면 안 된다). **`await anyio.sleep(0)` 만 대조군이 빨개지지 않는다** — `to_thread.run_sync` 가 이미 매 바퀴 await 점이라 그 줄만 떼도 다른 태스크가 돈다(실측 50/50). 그래서 그 줄에 대한 assert 는 쓰지 않았다. 줄은 남겼고 주석에 그 사실을 적었다.

**파일:** `webapp/logtail.py:66-72, 129`

`jobs.job_status`(sqlite)는 `anyio.to_thread.run_sync` 로 밀어내면서 — 바로 그 이유를
docstring 에 적어 두고 — **같은 루프에서 `open()/read()` 는 직접 한다.**

```python
덩어리, off = read_from(경로, off)     # 이벤트 루프 위에서 blocking read
```

그리고 새 바이트가 있으면 `continue` 로 **sleep 없이** 다시 돈다. 자식이 빠르게 찍는 동안은
루프가 파일 읽기로만 돌아간다.

**실패 시나리오:** `prep` 은 계정당 3분 × 4계정이고 로그가 계속 자란다. 이벤트마다
**누적본 전체**를 다시 보내는 설계(의도된 것이다)라, 로그가 수백 KB 가 되면 한 바퀴에
그만큼을 escape 하고 직렬화해서 보낸다. 그 사이 다른 SSE 스트림·`/healthz` 가 같이 멈춘다.
"멈춘 게 아니다" 라고 안내하는 화면 자체가 멈추는 게 제일 나쁜 모양이다.

**고칠 것:** `read_from` 도 스레드로 밀고(한 줄이다), 새 바이트가 있어도 매 바퀴
`await anyio.sleep(0)` 최소한 한 번은 양보해라.

```python
덩어리, off = await anyio.to_thread.run_sync(read_from, 경로, off)
```

(누적본 전량 재전송 자체는 T-1-26 근거가 명확하니 건드리지 마라. 다만 상한은 필요하다 —
예: 누적이 1MB 를 넘으면 앞을 잘라내고 "앞부분 N KB 생략" 을 붙이는 식.)

### WR-11: 보안 하네스가 실서버에 진짜 잡을 접수하고, 회차를 하드코딩한다

> **[fixed · `c0d69b7`]** c2 를 "없는 회차 + 모양이 맞는 `ad_ids` → 400 + 사유" 로 바꿨다(리뷰 제안). 회차는 **환경변수로 빼지 않고 의존 자체를 없앴다** — `CT_RUN_DIR` 로 빼면 다른 하네스용으로 export 해 둔 세션에서 실재 회차가 들어와 부수효과가 되살아나고 검사의 뜻도 달라진다(실측으로 FAIL 재현). `없는회차-$$` 를 쓴다. 실측: 옛 c2 는 잡 레지스트리 최신 id 를 바꾸고, 새 c2 는 안 바꾼다.

**파일:** `webapp/tests/security_curl.sh:137-146`

```bash
ok_code=$(code -X POST ... -d '{"run_dir":"2026-08-30","ad_ids":[]}' "$B/jobs/bids/preview")
...
test "$ok_code" -lt 400
```

두 가지가 문제다.

1. **부수효과가 있다.** 이건 진짜로 `bids_preview` 잡을 만들고 CLI 자식을 띄운다
   (`ad_ids:[]` → `accounts=[]` → `--account` 플래그 없음 → **전 계정**을 dry-run 으로 돈다).
   광고비는 0 이지만, 보안 검증을 돌릴 때마다 회차의 `web/` 에 `targets_*`·`preview_*` 파일이
   쌓이고 잡 레지스트리에 유령 작업이 남는다. `V-SAFE-02c` 주석은 c1 에 대해
   "부수효과 0" 이라고 정확히 적어 놨는데, c2 는 그 원칙을 안 지킨다.
2. **`2026-08-30` 이 박혀 있다.** 그 회차가 사라지면(정리하거나 다른 PC) 400 이 나오고
   `-lt 400` 이 거짓 → **보안 검증이 보안과 무관한 이유로 빨개진다.** 빨개진 보안 스크립트는
   곧 안 돌리는 스크립트가 된다.

**고칠 것:** 회차를 `CT_RUN_DIR` 환경변수로 빼고(다른 하네스들은 이미 그렇게 한다),
c2 는 부수효과 없는 거부 경로로 바꿔라 — 예를 들어 없는 회차 + 모양이 맞는 `ad_ids` 를 보내
**400 + 사유**를 확인하면 "가드 3층을 통과해 앱 로직이 답했다" 를 똑같이 증명하면서
잡은 안 생긴다.

---

## Info

> **[범위 밖 — 손대지 않았다]** 이번 수정 범위는 Critical 2 + Warning 11 이다.
> IN-01~06 은 그대로 열려 있다.

### IN-01: 기동 URL 이 토큰을 stdout 에 찍는다 — launchd 로 올리면 디스크에 남는다

**파일:** `webapp/main.py:63` · `webapp/security.py:38`

`security.py` 는 "토큰을 파일로 떨구지 않는다 — 메모리에만 둔다 (T-1-16)" 라고 적고,
`main.py` 는 "launchd LaunchAgent 는 stdout 을 파일로 돌리므로" 라고 적는다. 둘이 어긋난다.
LaunchAgent 로 상시 기동하는 순간 `?t=<토큰>` 한 줄이 로그 파일(기본 0644)에 영구히 남는다.
로컬 전용이라 실제 위험은 낮지만, **주석이 주장하는 성질이 참이 아니다** — 나중에 그 주석을
근거로 판단하는 사람이 틀린다. 문구를 사실에 맞추든지("재시작마다 바뀌고, 기동 로그에만 남는다"),
로그 파일 권한을 600 으로 만드는 안내를 같이 넣어라.

### IN-02: 쓰기 토큰과 페이지 쿠키가 같은 비밀값이라 `httponly` 가 아무것도 못 막는다

**파일:** `webapp/routes/board.py:63-66` · `webapp/templates/board.html:64`

쿠키에 `httponly=True` 를 걸면서 "JS 가 못 읽는다(XSS 가 나도 쿠키는 안 샌다)" 라고 적었는데,
**같은 값이 `<body hx-headers='{"X-CT-Token": "…"}'>` 로 DOM 에 노출**돼 있고
`board.js:346-349` 가 그걸 읽는다. XSS 가 나면 쿠키를 훔칠 필요가 없다 — 옆에 평문으로 있다.
역할 분리(쿠키=페이지, 헤더=쓰기)라는 설계는 맞지만 **값이 하나라 분리가 아니다.**
Jinja 자동 이스케이프 덕에 지금 XSS 경로는 안 보이므로 Info 로 둔다. 제대로 하려면
페이지 쿠키와 쓰기 토큰을 서로 다른 난수로 만들면 된다(각각 8줄).

### IN-03: `active_job()` 이 최근 50건 안에서만 도는 잡을 찾는다

**파일:** `webapp/jobs.py:560-566`

`recent_jobs(50)` 을 `started_at DESC` 로 받아 그 안에서 `running` 을 고른다. 장시간 `prep`
(계정당 3분 × 4)이 도는 동안 미리보기를 50번 넘게 누르면 도는 잡이 창 밖으로 밀려
**새로고침했을 때 작업 패널이 안 뜬다** — 성공기준 3 이 조용히 깨진다. 확신도는 낮다(50번은 많다).
`SELECT ... WHERE status='running' ORDER BY started_at LIMIT 1` 로 바꾸면 창이 사라진다.

### IN-04: 하네스 안내가 실서버를 공개된 고정 토큰으로 띄우라고 말한다

**파일:** `webapp/tests/{security_curl,board_cdp,preview_cdp,commit_cdp,revert_cdp}.sh`

넷 다 `CT_DEV_TOKEN=devtoken123 ./webapp/run-webapp.sh` 를 안내한다. 검증이 끝나고 서버를
재시작 안 하면 **저장소에 적힌 토큰으로 도는 실서버**가 남는다. Origin 가드와 CORS 미개방
덕분에 브라우저 경유 공격은 여전히 막히므로 실질 위험은 "이 맥북의 다른 로컬 프로세스" 뿐이다.
그래도 각 스크립트 끝에 "검증 끝났으면 서버를 재시작해라 — 토큰이 알려진 값이다" 한 줄은 있어야 한다.
(`sse_cdp.sh` 는 임시 포트에 따로 띄우고 `ct-sse-$$` 를 쓴다 — 이쪽이 옳은 모양이다.)

### IN-05: 읽기 라우트가 요청마다 전역 Jinja 환경을 바꾼다

**파일:** `webapp/routes/board.py:93`

```python
templates.env.policies["json.dumps_kwargs"] = {"ensure_ascii": False}
```

`GET /` 가 들어올 때마다 **프로세스 전역 템플릿 환경**을 갱신한다. 값이 항상 같아서 지금은
무해하지만, 이건 요청 핸들러가 아니라 `main.py` 의 `Jinja2Templates(...)` 바로 밑에 한 번
있어야 하는 설정이다. 지금 자리에 있으면 "`/` 를 한 번도 안 열고 조각만 받으면 `ensure_ascii`
가 다르게 나온다" 는 상태 의존이 생긴다.

### IN-06: 회차 전체 되돌리기 확인 버튼이 요청 중에 다시 열린다

**파일:** `webapp/static/board.js:617-627` · `578-582`

`전체확인ok` 클릭 → `되돌리기접수(...)`(비동기) → 곧바로 `전체확인닫기()` 가
`전체버튼.disabled = false` 로 **되돌리기 버튼을 다시 연다.** 접수가 아직 왕복 중인데 열린다.
두 번 누르면 두 번째는 `create_job` 의 전역 가드가 409 로 막으므로(확인했다) 실제 이중 되돌리기는
안 난다 — 그래서 Info 다. 다만 사용자에게는 "눌렀는데 에러가 떴다" 로 보인다.
`되돌리기접수` 의 콜백에서 열어라.

---

## 확인했고 문제 없었던 것 (기록용)

무엇을 봤는지 남겨 둔다. 다음에 같은 자리를 또 뒤지지 않게.

- **"빈 값이 전량이 되는" 경로** — `create_job` 의 `if only_ads is not None:`(jobs.py:441),
  `run_ads._load_only_ads`(빈 배열 → `set()`, `None` 아님), `bids.run_bids:171`
  (`if only_ads is not None:`), `bids.run_revert:286`. 네 군데가 전부 `None` 과 빈 집합을
  구분한다. 빈 선택으로 미리보기→실행을 태워도 PUT 0건이다.
- **헤더 체크박스** — `titleFormatterParams: { rowRange: "visible" }` 있다(board.js:100).
- **미리보기→실행 결합** — `BidsCommitReq` 에 `ad_ids` 필드가 **없다**. 대상은 부모 잡의
  targets 파일뿐이고 `_override_targets` 가 회차 `web/` 밖을 부모 디렉터리 비교로 거부한다
  (접두 비교가 아니다 — 옳다).
- **경로 탈출** — 회차 이름은 `paths.run_dir_path` 화이트리스트(실재 목록 대조)를 통과해야만
  경로가 된다. 라우트·`create_job` 양쪽에서 통과한다.
- **명령 주입** — argv 는 리스트, `shell=True`·`os.system` 0건(테스트가 감시), `Alias`·`AdId`
  패턴 검증, adId 는 argv 가 아니라 파일로 건너간다.
- **웹앱이 입찰가를 재계산하는 곳** — 없다. `flow.raise_total` 의 `to - from` 은 산출물 두 값의
  차이지 새 정본이 아니다. `board.fold_products` 의 `ctr` 재계산은 합산 후 표시용이고
  `bid`/`groupBid` 는 읽기만 한다.
- **`①행에 imp/clk 이 없다`** — `board.py` 도 `board.js` 도 전부 `.get()` / `빈칸이면()` 으로만
  만진다. 0 으로 대체하지 않는다.
- **파이썬 테스트** — 가짜 초록 없음. 특히 `test_화면이_본_건수와_다르면_거부한다` 가
  `revert_dry_run` 을 **통과하도록 고정해 놓고** `부른적 == []` 을 확인한다 — 네가 말한
  그 사고를 정확히 닫았다. `_되돌리기가_떴나(자식금지)` 음성 대조군도 대부분의 거부 테스트에 붙어 있다.
- **`no_commit_guard.sh`** — 테스트 트리에 `--commit` 리터럴 0건. 파이썬 테스트가 쓰는
  `commit=True` 는 전부 `spawn` 을 monkeypatch 한 픽스처(`잡판`) 안이거나 순수 함수 호출이다.
  실수로 실탄이 나갈 경로는 없다.

---

_Reviewed: 2026-09-20_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
_Fixed: 2026-09-20 — Critical 2 + Warning 11 전부 fixed (커밋 11개) · Info 6 범위 밖_

### 수정 후 검증 스위트 (실측)

```
.venv-web/bin/pytest webapp/tests -q -p no:warnings        → 199 passed   (186 → +13)
bash webapp/tests/no_commit_guard.sh                        → exit 0
CT_DEV_TOKEN=… bash webapp/tests/security_curl.sh           →  9 PASS / 0 FAIL
CT_DEV_TOKEN=… bash webapp/tests/board_cdp.sh               → 22 PASS / 0 FAIL
bash webapp/tests/sse_cdp.sh                                → 12 PASS / 0 FAIL
CT_DEV_TOKEN=… bash webapp/tests/preview_cdp.sh             → 32 PASS / 0 FAIL  (31 → +1)
CT_DEV_TOKEN=… bash webapp/tests/commit_cdp.sh              → 15 PASS / 0 FAIL
CT_DEV_TOKEN=… bash webapp/tests/revert_cdp.sh              → 26 PASS / 0 FAIL
CLI 회귀 6종                                                 → 전부 exit 0 · 107 tests (100 → +7)
   nvad 7 · reports 7 · ads_rules 21 · ledger 21 · bids 35 · prune 16
```

**검사 수는 늘기만 했다** — 줄어든 것 0. 지운 검사도 0.

**광고 API 쓰기 0건.** `bids --commit` / `--revert --commit` 을 실계정에 태우지 않았다.
검증 후 실측: `GET /jobs/revert/round/count?run_dir=2026-09-20` → `{"cy728":472,"total":472}`
(오늘 인상한 472건 그대로) · 잡 레지스트리의 `revert%` 잡 **0건**.
