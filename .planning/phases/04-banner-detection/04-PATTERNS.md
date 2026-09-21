# Phase 4: 홍보배너 식별 - Pattern Map

**Mapped:** 2026-09-22
**Files analyzed:** 16 (신규 9 · 수정 7)
**Analogs found:** 15 / 16 (exact 9 · role-match 5 · partial 1 · 없음 1)

출처: `04-CONTEXT.md` (D-01~D-12 · D-19 상속) · `04-RESEARCH.md` §Architectural Responsibility Map /
§Recommended Project Structure / §Pattern 1~4 / §산출물 계약 · `04-VALIDATION.md` §Wave 0 Requirements.

**이 문서의 모든 코드 블록은 실제 파일에서 읽은 것이다.** 추측 발췌는 한 줄도 없다.
행 번호는 2026-09-22 기준(`main` @ cda51d0).

---

## File Classification

| 신규/수정 파일 | 역할 | 데이터 흐름 | 가장 가까운 analog | 일치도 |
|---|---|---|---|---|
| `webapp/banner.py` (신규) | 순수 모듈 (pure) | transform (dict/str in → dict/list out) | `webapp/state.py` · `webapp/join.py` | **exact** |
| `.claude/skills/bulsaja-detail-page/scripts/banner_scan.py` (신규) | CLI 자식 프로세스 | batch + file-I/O + network | `ss_index_build.py` · `bulsaja_scan.py` | **exact** |
| `banner_scan.py` 내 OCR/Pillow 층 | CLI 내부 유틸 | transform (이미지 → 특징) | `.claude/skills/bulsaja-detail-remix/scripts/stitch.py` | role-match |
| `banner_scan.py` 내 "모양 아니면 예외" 규약 | CLI 내부 규약 | transform | `ss_index_calls.목록꺼내기` | **exact** |
| `webapp/routes/banner.py` (신규) | route (GET×2 + POST×1) | request-response | `webapp/routes/board.py` + `webapp/routes/jobs.py` | **exact** |
| `webapp/templates/banner_review.html` (신규) | template | server-render | `webapp/templates/board.html` (+ `_job_panel.html`) | role-match |
| `banner_label` 테이블 DDL (`webapp/jobs.py` 수정) | schema | CRUD | `jobs.py` DDL 의 `ss_index` 블록 | **exact** |
| 라벨 read/write 접근 모듈 (위치 미정) | store | CRUD | `webapp/bulsaja_index.py`(읽기) + `jobs.py:_conn/init_db`(쓰기) | **partial — 아래 §결정필요** |
| `webapp/jobs.py` (수정: KINDS·SINGLETON·_build_argv·프리픽스) | job registry | event-driven | 같은 파일의 `bulsaja_*` 3종 등록부 | **exact** |
| `webapp/argv.py` (수정: `BannerArgv`) | config/builder | transform | 같은 파일 `BulsajaArgv` | **exact** |
| `webapp/main.py` (수정: 라우터 1줄) | config | — | 같은 파일 `include_router` 3줄 | **exact** |
| `webapp/settings.py` (수정: 캐시경로 등 키) | config | — | 같은 파일 `DEFAULTS` Phase 3 블록 | **exact** |
| `webapp/tests/test_banner.py` (신규) | test (unit, 순수) | — | `webapp/tests/test_state.py` · `test_join.py` | **exact** |
| `webapp/tests/test_routes_banner.py` (신규) | test (route) | — | `webapp/tests/test_routes_jobs.py` | **exact** |
| `webapp/tests/test_ocr_determinism.py` (신규 · `.venv` 전용) | test (integration) | — | **없음 — `.venv` 로 도는 테스트가 저장소에 0건** | **없음** |
| `webapp/tests/fixtures/render_content.json` · `banner_labels.json` (신규) | fixture | — | `fixtures/join_traps.json` + `conftest.py` 등록 관용구 | **exact** |
| `webapp/tests/test_argv.py` (수정: import 가드 확장) | test (guard) | — | `test_index.py:369` · `test_join.py:589` | **exact** |
| `webapp/tests/conftest.py` (수정: 픽스처 2개) | test fixture | — | 같은 파일 Phase 3 픽스처 블록 | **exact** |

---

## Pattern Assignments

### 1. `webapp/banner.py` (순수 모듈 · transform)

**Analog:** `webapp/state.py` (122행 · 전량이 순수 함수) / 보조 `webapp/join.py`

이 파일은 **`state.py` 의 쌍둥이**로 만든다. 같은 성질(네트워크 0 · 파일 0 · dict in / 값 out)이고,
같은 grep 가드(`test_join.py:589`)의 감시 대상에 들어간다.

**(a) 모듈 docstring — "이 모듈이 절대 하지 않는 것" 목록을 반드시 갖춘다**
`webapp/state.py:1-30` (발췌):

```python
"""상세 상태 3단계 판정 — 불사자가 써 둔 플래그를 **읽기만** 한다 (STATE-02/03/04/05).

**순수 함수뿐이다. 네트워크도 크레딧도 파일도 0 이다.** dict 하나를 받아 문자열 하나를 낸다.
`board.py` 와 같은 성질이다 — CLI 가 이미 써 둔 산출물을 투영할 뿐, 판정 대상을 직접
조회하지 않는다. 그래서 회차 파일이 없어도, 불사자가 죽어 있어도 이 모듈은 안 깨진다.
...
이 모듈이 절대 하지 않는 것:
  - 불사자 MCP 호출 (D-19). 불사자 클라이언트 라이브러리를 import 하지 않는다 —
    웹앱 전용 venv 에는 그 라이브러리가 쓰는 HTTP 패키지가 없어서 import 하는 순간
    ImportError 다. MCP 접촉은 전부 CLI 자식 프로세스 몫이다
  ...
  - 판정값을 캐시하기. 불사자 서버 플래그가 정본이고(PROJECT.md), 캐시하는 순간
    Phase 5 가 낡은 상태로 크레딧을 태운다
"""
```

> **따라할 것:** 이 형식 그대로. `banner.py` 의 금지 목록은 최소 4줄 —
> ① 이미지 다운로드·Pillow·OCR (전부 CLI 몫, D-19) ② **배너 판정 규칙 재구현**
> (정본은 산출물 JSON) ③ 기계 판정을 DB 에 복사 ④ 미판정·스킵을 "배너 아님"으로 흡수.
> **바꿀 것:** import 는 `from webapp import state` 하나까지만 허용(불리언정규화 재사용).
> `sqlite3`·`urllib`·`PIL` 은 **글자로도 넣지 마라** — 아래 §6 의 가드가 주석까지 훑는다.

**(b) 판정 상수를 모듈 최상단에 문자열로 둔다 — 이모지는 화면에서 붙인다**
`webapp/state.py:49-57`:

```python
# 판정값. **이모지는 화면에서 붙인다** — 여기서는 문자열이다.
# 화면 표시는 ⚪ AI가공완료 / 🟡 단순번역만 / 🔴 중국어원본.
AI가공완료 = "AI가공완료"
단순번역만 = "단순번역만"
중국어원본 = "중국어원본"
```

`webapp/join.py:36-48` 도 같은 모양(사유코드 5종 + 버킷 2종):

```python
# ── 미해소 사유코드 5종 ────────────────────────────────────────────────────
# **서로 다른 값이어야 한다.** 한 칸에 담으면 광고 쪽 오류와 시스템 문제가 섞인다.
추출실패 = "추출실패"   # 광고그룹명에 NN-N 번호가 없다            → 광고 쪽 오류
...
미조회 = "미조회"       # 제외 설정 · 레이트리밋 · 스캔 전          → 우리가 안 본 것
```

> **따라할 것:** 장 판정 4종(`배너` / `제품` / `무내용` / `미판정`)과 스킵사유 3종
> (`잔여부족` / `제거율초과` / `판정불가`)을 이 형태로 박는다. **`미판정` 과 `배너아님` 을
> 같은 값으로 접지 마라** — `join.py` 주석의 "한 칸에 담으면 섞인다"가 정확히 이 경우다
> (RESEARCH §Anti-Patterns "404 를 배너 아님으로 흡수").
> `routes/banner.py` 는 이 상수를 import 해 화면 문자열로 투영한다
> (`routes/board.py:50-56` 의 `_사유이름` 표가 그 관용구다).

**(c) 타입이 제각각인 입력의 정규화 — `bool()` 금지 규율**
`webapp/state.py:60-78`:

```python
def 불리언정규화(v) -> bool:
    """'0' '1' False 1 None 을 전부 같은 규약으로 읽는다.

    파이썬 내장 캐스팅을 그대로 쓰지 마라 — 문자열 '0' 은 파이썬에서 **참**이다.
    ...
    분기 순서에도 의미가 있다. `bool` 은 `int` 의 하위타입이라 숫자 분기를 앞에 두면
    `True`/`False` 가 숫자 경로로 새고, ...
    """
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    return str(v).strip().lower() not in _FALSY
```

> **따라할 것:** `imageTranslated` 를 읽어야 하면 **이 함수를 재사용**한다
> (`from webapp import state` → `state.불리언정규화`). RESEARCH §Pattern 1 의 함정 표가
> `'0' 33 / '1' 19 / False 4 / True 1` 을 실측으로 적어 뒀고 CONTEXT D-11(Phase 3)이
> `bool()` 금지를 못박았다. **재구현 금지 — 판정이 두 곳이 되면 화면과 산출물이 달라진다.**

**(d) "못 읽었다"와 "0개다"를 예외로 가르는 규약 — `상세이미지목록()`의 정본**
`.claude/skills/bulsaja-detail-page/scripts/ss_index_calls.py:68-101` (이 규약의 저장소 정본):

```python
def 목록꺼내기(r, 키들, 맥락="", 이름="목록"):
    """응답 dict 에서 **처음으로 존재하는** 키의 리스트를 꺼낸다. 모양이 아니면 예외다.
    ...
    규약 셋:
      · 키가 **없다** → 예외. "못 물어봤다" 를 "물어봤더니 없더라" 로 읽지 않는다
      · 키가 **있는데 리스트가 아니다** → 예외. 판이 바뀐 것이지 빈 결과가 아니다
      · 키가 **있고 비었다(또는 None)** → `[]`. 이건 정상이다 (진짜 빈 그룹 · 마지막 페이지)
    """
    if not isinstance(r, dict):
        raise RuntimeError(f"{이름} 응답이 dict 가 아니다{맥락}: {type(r).__name__}")

    for 키 in 키들:
        if 키 in r:
            값 = r.get(키)
            if 값 is None:
                return []
            if not isinstance(값, list):
                raise RuntimeError(f"{이름} 응답의 '{키}' 가 리스트가 아니다{맥락}: "
                                   f"{type(값).__name__}")
            return 값
    키표기 = "/".join(f"'{k}'" for k in 키들)
    raise RuntimeError(f"{이름} 응답에 {키표기} 이 없다{맥락}: {str(_사유(r))[:300]}")
```

그리고 그 모듈이 생긴 경위 — `ss_index_calls.py:10-24`:

```python
    """**이 모듈이 생긴 경위 (03-07 첫 실탄, 2026-09-21):**
    30그룹짜리 인덱스 구축이 9.2초 만에 `exit 0` 으로 끝났다. ...
    그 오류 응답에는 `항목` 키가 없다. 호출부는 `r.get("항목") or []` 로 읽어
    **"이 그룹은 상품이 0건이구나"** 로 해석하고 조용히 다음 그룹으로 넘어갔다.
    크레딧이 0이라 아무 경보도 안 울렸다 ..."""
```

> **따라할 것:** `banner.상세이미지목록(render_content)` 은 RESEARCH §Pattern 1 의 코드대로
> `None` → `ValueError("renderContent 가 None 이다 — 미조회와 0장을 같은 값으로 접지 마라")`,
> 비문자열 → `ValueError`, 빈 문자열 → `[]`. 위 세 줄 규약과 **같은 갈래**다.
> **바꿀 것:** 여기서는 `RuntimeError` 가 아니라 `ValueError` — 웹앱 라우트가
> `ValueError → 400` 으로 번역하는 표(`routes/jobs.py:354-392`)를 이미 갖고 있다.

**(e) "빈 목록이 전량이 되는 경로를 막는다" — `제품이미지목록()` 의 정본**
`webapp/jobs.py:523-536` (이 규율의 원조. RESEARCH 가 `jobs.py:427-441` 로 지목한 그 코드):

```python
    if kind in ("revert_only", "revert_all"):
        # `revert_only` 는 대상 목록으로 좁힌다(D-13 — 이 작업분만).
        # `revert_all` 은 좁히지 않는다(회차 전체). 대상 파일 유무가 그 차이의 전부다.
        #
        # **그래서 대상 파일이 없는 `revert_only` 는 존재할 수 없다.** 없으면
        # `AdsArgv` 가 `--only-ads` 를 안 붙이고 CLI 는 그걸 "백업 전량" 으로 읽는다
        # ... **빈 값이 '전량' 으로 해석되는 경로는 예외로
        # 터뜨린다** — 이 페이즈에서 같은 부류가 두 번 사고 직전까지 갔다.
        if kind == "revert_only" and targets_path is None:
            raise ValueError("revert_only 에는 대상 파일이 반드시 있어야 한다 — "
                             "대상 없는 되돌리기는 회차 전체다(D-12)")
```

`webapp/jobs.py:545-552` (같은 규율의 두 번째 적용):

```python
        if kind == "bulsaja_index" and targets_path is None:
            raise ValueError("인덱스 잡에는 그룹 목록 파일이 반드시 있어야 한다 — "
                             "없으면 전 그룹(실측 75,335건 · 5시간 39분)이다")
        if kind == "bulsaja_scan" and targets_path is None:
            raise ValueError("스캔 잡에는 대상 목록 파일이 반드시 있어야 한다 (FLOW-02 / D-11)")
```

> **따라할 것:** RESEARCH §산출물 계약의 `제품이미지목록(상품)` 을 **이 모양 그대로** 쓴다 —
> 스킵 → `ValueError`, 미판정 장 존재 → `ValueError`, 빈 목록 → `ValueError("빈 목록은 '전량'이 아니다")`,
> 2장 미만 → `ValueError`(D-07). 메시지에 **실측 숫자와 결정 번호를 적는 것**까지 따라한다
> (위 두 발췌가 전부 그렇게 돼 있다 — 그게 다음 사람이 가드를 못 지우게 하는 장치다).
> **바꿀 것:** 여기(`banner.py`)가 Phase 5 의 **유일한 접근자**다. 규칙이 두 곳이 되지 않게
> `routes/banner.py` 는 이 함수를 부르기만 하고 자기 판단을 넣지 않는다.

**(f) 집계 함수의 반환 모양 — 숫자 두 개를 한 칸에 담지 않는다**
`webapp/routes/board.py:216-234` 부근의 `_인덱스표시` 집계 초기화가 관용구다:

```python
    집계 = {"불완전": 0, "그룹": 0, "미보유": 0, "불일치": 0, "그룹에없음": 0,
           "팬아웃미조회": 0}
```

그리고 `bulsaja_scan.py:526-531` 의 "두 미조회를 합치지 않는다":

```python
    미조회합 = sum(1 for 행 in 행들 if 행.get("미조회"))
    # 팬아웃 미조회는 **따로 센다.** 번호층 미조회와 합치면 "사본을 못 물어봤다" 가
    # "상품을 못 찾았다" 에 묻혀 사라진다 — 두 사실은 화면에서도 따로 읽힌다.
    팬아웃미조회합 = sum(1 for 행 in 행들 if 행.get("팬아웃미조회"))
```

> **따라할 것:** `게이트집계()` 는 **분모 둘을 모두** 돌려준다(D-11 — `오탐율_정밀도` 15.6% /
> `오탐율_누락률` 1.8%). `무내용` 은 분자 어느 쪽에도 안 넣고 **별도 칸**이다.
> `미검수상품` 도 별도 칸(D-03a / RESEARCH Pitfall 8 — 확인 안 한 것을 동의로 세면 미탐 0%가 거짓말).

---

### 2. `.claude/skills/bulsaja-detail-page/scripts/banner_scan.py` (CLI · batch + file-I/O + network)

**Analog:** `.claude/skills/bulsaja-detail-page/scripts/ss_index_build.py` (456행) —
같은 디렉터리·같은 인자 규약·같은 종료코드 계약. 보조: `bulsaja_scan.py`(산출물 쓰기).

**(a) 파일 위치와 sys.path shim** — `ss_index_build.py:62-74`:

```python
# 불사자 MCP 클라이언트는 카테고리 교정 스킬의 것을 재사용한다.
# **경로를 박지 않는다** — 이 파일 위치에서 스킬 루트를 거슬러 올라가 찾는다.
# (같은 관용구: product-name/scripts/run_names.py:40-46 · detail_batch.py:47-52)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILLS_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", ".."))
SKILL_SCRIPTS = os.path.join(SKILLS_DIR, "bulsaja-category-fix", "scripts")
if SKILL_SCRIPTS not in sys.path:
    sys.path.insert(0, SKILL_SCRIPTS)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
```

> **따라할 것:** 같은 디렉터리에 둔다(`argv.py:43-50` 주석이 그 이유를 적어 뒀다 — 새 디렉터리를
> 파면 STATE-01 에서 한 번 고장났던 지점을 다시 만든다).
> **바꿀 것:** `banner_scan.py` 는 **MCP 를 한 번도 안 부른다.** `bulsaja_mcp` import 를 넣지 마라 —
> 넣는 순간 `bulsaja_rate`·MCP 세션까지 끌려오고 "크레딧 0 · MCP 0회"라는 주장이 코드로 깨진다.
> `SCRIPT_DIR` 삽입만 남기고 `SKILL_SCRIPTS` 줄은 뺀다.

**(b) 로그 관용구 — `flush=True` 는 협상 불가** `ss_index_build.py:80-102`:

```python
def 말하기(줄):
    """진행 출력. **`flush=True` 가 협상 불가다.**

    3시간짜리 잡의 로그가 0바이트로 머물면 사람이 "멈췄나" 를 판단할 수 없다.
    잡으로 띄울 때는 `PYTHONUNBUFFERED` 가 주입되지만(`webapp/jobs.py`), 터미널에서
    직접 돌릴 때는 그게 없으므로 **둘 다** 필요하다.
    """
    try:
        print(줄, flush=True)
    except Exception:
        pass


def 오류말하기(줄):
    """치명적 사유는 stderr 로도 남긴다 — 잡 레코드가 보관하는 게 stderr 꼬리다."""
```

> **따라할 것:** 이 두 함수를 그대로 복사한다(스크립트 간 공유 모듈 없음 — 저장소 관례가 복사다).
> 단계 로그는 RESEARCH §진행 표시의 문구를 쓴다:
> `[1/5] URL 추출 916장` → … → `[5/5] 썸네일 891장 · 판정 배너 87 / 제품 804`.
> SSE(`logtail.py` + `_job_panel.html`)가 그대로 붙는다 — **새 진행 채널을 만들지 마라.**

**(c) 원자적 쓰기 + 시각** `ss_index_build.py:119-138`:

```python
def 원자적쓰기(경로, obj):
    """`tmp → os.replace` — 반쯤 쓴 JSON 을 읽는 쪽이 보지 않게 한다.

    (`webapp/jobs.py:340-350` 의 `_write_targets` 와 같은 관용구)
    """
    try:
        경로 = str(경로)
        os.makedirs(os.path.dirname(경로) or ".", exist_ok=True)
        tmp = 경로 + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        os.replace(tmp, 경로)
    except Exception as e:
        말하기(f"[경고] 파일 저장 실패({경로}): {e}")


def 지금():
    """로컬 시각 + 오프셋 (`webapp/jobs._now()` 와 같은 모양)."""
    return datetime.now().astimezone().isoformat(timespec="seconds")
```

**(d) 산출물 조립 — 모르는 값은 `null`, 지어내지 않는다** `bulsaja_scan.py:511-523`:

```python
    # ⑦ 산출물 — 쓰기 직전 한 번 더 `표시규칙` 을 훑는다.
    산출물 = 표시규칙제거({
        "run_dir": 인자.run_dir,
        "생성시각": 지금(),
        "계정": 계정,
        "마켓그룹": 마켓그룹,
        # D-18 제외 설정은 **웹앱이 읽어 `join.attach(excluded=...)` 로 넘긴다.**
        # 자식에게는 그 값을 주는 플래그가 없으므로 여기에 빈 배열을 적으면
        # "제외 없음" 이라는 거짓말이 된다. `null` = 모른다 (설정의 정본은 한 곳이다).
        "제외그룹": None,
        "행": 행들,
    })
    원자적쓰기(인자.out, 산출물)
```

> **따라할 것:** RESEARCH §산출물 계약의 스키마를 그대로. `"소요초"` 를 **CLI 가 직접 찍는다**
> — `jobs.ended_at` 은 "끝난 시각"이 아니라 "눈치챈 시각"이다
> (`.planning/todos/pending/job-reap-depends-on-polling.md` 실측: 실제 60초 → 기록 2,421초).
> `"게이트통과": false` 를 **기본값으로 박는다**(VALIDATION §성공기준 2).
> **바꿀 것:** `표시규칙제거` 는 불필요하다(MCP 응답을 안 받는다). 대신 **URL 스킴 화이트리스트**가
> 그 자리에 온다 — RESEARCH §Security 가 `https://` 만 허용 + 사설 IP 거부(SSRF)를 요구한다.

**(e) 인자 검증 순서 — "아무것도 하기 전에" 터뜨린다** `ss_index_build.py:365-384`:

```python
    # ① 대상 확인 — **MCP 도 SQLite 도 건드리기 전에** 본다.
    #    빈 목록에서 전 그룹(실측 75,335건 · 5시간 39분)으로 미끄러지는 경로를 막는다.
    #    웹앱 `jobs._build_argv` 의 ValueError 와 짝을 이루는 2층 방어다.
    try:
        with open(인자.groups, encoding="utf-8") as f:
            그룹들 = json.load(f)
    except FileNotFoundError:
        말하기(f"⛔ 그룹 목록 파일이 없다: {인자.groups} — 빈 목록은 전량이 아니다")
        return 2
    ...
    그룹들 = [str(g) for g in (그룹들 or []) if g]
    if not 그룹들:
        사유 = ("⛔ 훑을 마켓그룹이 없다 — **빈 목록은 전량이 아니다.** "
               "훑을 그룹을 지정해서 다시 불러라.")
        말하기(사유)
        오류말하기(사유)
        return 2
```

그리고 모드별 필수 인자 검사(`bulsaja_scan.py:291-299`) — `argparse required` 를 안 쓰는 이유까지:

```python
        # ② 대상 확인. **빈 목록은 전량이 아니다.**
        for 필수, 이름 in ((인자.run_dir, "--run-dir"), (인자.targets, "--targets"),
                          (인자.out, "--out")):
            if not 필수:
                사유 = f"⛔ 스캔에는 {이름} 이 반드시 있어야 한다"
                말하기(사유)
                오류말하기(사유)
                return 2
```

**(f) 종료코드 계약을 docstring 맨 위에 적는다** `ss_index_build.py:37-47`:

```python
종료코드
  0  정상
  2  훑을 대상이 없다 (`--groups` 파일이 없거나 배열이 비었다). **빈 목록은 전량이 아니다**
  3  계정 불일치 (ENG-08). SQLite 에 한 글자도 쓰기 전에 죽는다
  4  `ss_index` 테이블이 없다. 웹앱을 한 번 띄워 스키마를 만들어라

사용:
  python3 ss_index_build.py --db <webapp.db> --groups <groups.json> --out <summary.json>
        ...
```

> **따라할 것:** `banner_scan.py` 종료코드 제안 — `0` 정상 / `2` 대상 없음(조인 산출물에 상세 보유
> 행이 0건) / `3` **미판정 장이 남았다**(404 등 — RESEARCH 가 "판정 불가"를 성공으로 적지 말라고 했다)
> / `4` `pyobjc-framework-Vision` 미설치. **`3` 을 0 으로 접지 마라** — 25장 404 중 20장이 한 상품에
> 몰려 있고(실측), 흡수하면 그 상품이 "제품 0장 + 배너 0장"으로 조용히 보인다.
> **바꿀 것:** 계정 확인(ENG-08)·`스키마확인`은 **없다**. MCP 도 SQLite 도 안 만진다.
> 대신 "① 조인 산출물 읽기 → ② URL 추출 → ③ 다운로드" 순서에서 ①②가 `return 2` 자리다.

**(g) 중단 안전성** `ss_index_build.py:449-456`:

```python
if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        # 중단이 안전하다는 것이 이 스크립트의 설계다 — 건마다 커밋했으므로
        # 여기까지 적힌 행은 그대로 남고, 같은 명령이 productId 집합으로 이어서 간다.
        말하기("\n중단됨 — 여기까지 적힌 행은 남아 있다. 같은 명령으로 이어서 돌려라.")
        sys.exit(130)
```

`bulsaja_scan.py:544-548` 은 **반대 규약**(산출물을 안 쓴다)이고, 배너 스캔은 이쪽에 가깝다:

```python
    except KeyboardInterrupt:
        말하기("\n중단됨 — 산출물을 쓰지 않았다. 다시 돌려라 (크레딧 0).")
        sys.exit(130)
```

> **따라할 것:** `bulsaja_scan.py` 쪽. 배너 스캔은 크레딧 0 · 4분이라 **부분 산출물을 남기지 않는다**.
> 다만 **다운로드 캐시는 남긴다**(271MB 재다운로드 방지) — 캐시는 산출물이 아니다.

**(h) Pillow 사용 관용구** `.claude/skills/bulsaja-detail-remix/scripts/stitch.py:1-13, 38-44`:

```python
"""zip 안 이미지 자연정렬 + 리사이즈(가로 고정폭) + 세로 이어붙이기 + 용량/픽셀 클램프.

네트워크·MCP 없는 순수 로직만 담는다 — 유일하게 로컬 단위테스트 가능한 부분(test_stitch.py).
"""
import io
import re
import zipfile
from pathlib import Path

from PIL import Image

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
...
def resize_to_width(img, width):
    """비율을 유지한 채 가로폭을 width 로 맞춘다."""
    w, h = img.size
    if w == width:
        return img
    new_h = max(1, round(h * width / w))
    return img.resize((width, new_h), Image.LANCZOS)
```

> **따라할 것:** ① `from PIL import Image` 는 **CLI 쪽에서만** ② 순수 이미지 로직을 별도 함수로
> 떼어 단위테스트 가능하게 두는 구조(`test_stitch.py` 가 그 증거) ③ 확장자 집합 상수화.
> **바꿀 것:** 이 페이즈는 **가로폭이 아니라 높이 200px 고정**(RESEARCH §검수 화면: 한 줄의
> 세로 크기가 일정해야 3초 훑기가 된다)이고, `resize()` 전에 `im.draft("RGB", (400,400))` 를
> 반드시 넣는다(RESEARCH §Don't Hand-Roll — 891장 5.7초 vs draft 없이 수 배).
> `Image.MAX_IMAGE_PIXELS` 기본 제한을 **끄지 마라**(decompression bomb, RESEARCH §Security).
> `stitch.py` 자체는 이 페이즈에서 **호출하지 않는다**(RESEARCH §Supporting: Phase 5/6 자산).

---

### 3. `webapp/routes/banner.py` (route · request-response)

**Analog:** `webapp/routes/board.py`(GET 렌더·산출물 읽기) + `webapp/routes/jobs.py`(POST·토큰·예외 번역)

**(a) 라우터 모듈 docstring — GET/POST 규약을 맨 위에 박는다** `webapp/routes/board.py:3-23`:

```python
"""보드 화면.

    GET /                토큰(쿼리) → 쿠키 교환 후 보드 렌더                  [읽기]
    GET /?run_dir=<회차>  다른 회차로 갈아타기                                 [읽기]
...
**이 라우트는 GET 이지만 서버 상태를 바꾸지 않는다.** 쿠키를 심는 것은 *브라우저*
상태를 바꾸는 것이고, 디스크·광고 API·잡 레지스트리에는 아무 일도 일어나지 않는다.
그 구분이 중요한 이유: "GET 은 상태를 안 바꾼다" 가 `security.guard` 의 Origin 방어를
성립시키는 전제이기 때문이다(T-1-01b). ...
`security_curl.sh` 의 V-SAFE-01d 가 이 파일의 GET 핸들러 본문을 실제로 훑어서 기계로 집행한다.

**CLI 를 실행하지 않는다.** 보드 데이터는 `run-dir/result.json` 을 읽어 투영할 뿐이라
네트워크도 크레딧도 광고비도 0 이다(STACK.md "세 번째 길"). 무거운 건 파일 읽기 하나뿐이라
`async def` 가 아니라 **`def`** 로 선언한다 — async 핸들러에서 blocking 파일 IO 를 하면
이벤트 루프가 멈춰 SSE 진행 로그가 같이 끊긴다(Anti-Patterns).
"""
```

> **따라할 것:** 세 라우트를 이 표 형식으로 맨 위에 적는다. **핸들러는 `def`(async 아님)** —
> 썸네일 `FileResponse` 와 산출물 JSON 읽기가 전부 blocking 파일 IO 다.
> `routes/jobs.py:31-42` 는 "GET 핸들러를 파일 맨 아래에 모아 둔다"까지 규율로 적어 뒀다 —
> 이 파일은 GET 2 · POST 1 이므로 **POST 를 위, GET 을 아래**로 배치해 같은 규율을 지킨다.

**(b) 쿠키 게이트 — 모든 읽기 라우트의 첫 줄** `webapp/routes/jobs.py:770-776`:

```python
@router.get("/jobs")
def get_jobs(request: Request):
    """최근 작업 20건. 화면이 고장났을 때 "뭐가 돌았나" 를 보는 창이다."""
    if not security.page_cookie_ok(request):
        return PlainTextResponse("토큰이 필요하다", status_code=403)
    return {"jobs": [_투영(j) for j in jobs.recent_jobs(20)]}
```

`webapp/security.py:105-111` (그 함수):

```python
def page_cookie_ok(request: Request) -> bool:
    """페이지를 그려도 되는지 — 쿠키 게이트. 라우트 레벨에서 부른다.

    미들웨어가 아니라 라우트에서 보는 이유: `/healthz` 처럼 쿠키 없이도 열려야 하는
    읽기 창이 있다. 화면이 고장났을 때 서버가 살았는지 보려면 그 창은 막히면 안 된다.
    """
    return 토큰이같나(request.cookies.get(COOKIE_NAME, ""), BOOT_TOKEN)
```

> **따라할 것:** `GET /banner/review` 와 `GET /banner/thumb/...` **둘 다** 이 3줄로 시작한다.
> 썸네일에도 붙여야 한다 — 안 붙이면 271MB 캐시에서 파생된 이미지가 쿠키 없이 열린다.

**(c) 쓰기(POST)의 3층 방어 — `guard` 는 미들웨어라 라우트가 할 일이 없다**
`webapp/security.py:77-102`:

```python
async def guard(request: Request, call_next):
    """쓰기 메서드만 검사한다. **상태를 바꾸는 GET 을 만들지 않는 것이 이 방어의 전제다.**

    브라우저는 모든 POST/PUT/DELETE 에 `Origin` 을 붙인다(교차 사이트 `<form>` POST 도).
    그런데 단순 교차 사이트 GET(`<img src>`·`<script src>`·링크)에는 Origin 이 **없다**.
    따라서 부수효과가 있는 엔드포인트를 GET 으로 하나라도 만들면 이 층이 통째로 뚫린다.
    htmx 쪽에서도 `hx-post`/`hx-delete` 만 쓴다 (T-1-01b).
    ...
    """
    if request.method not in SAFE_METHODS:
        origin = request.headers.get("origin")
        if origin is not None and origin not in allowed_origins():
            return PlainTextResponse("origin 거부", status_code=403)
        if origin is None and request.headers.get("sec-fetch-site") not in (None, "same-origin"):
            return PlainTextResponse("sec-fetch-site 거부", status_code=403)
        토큰 = request.headers.get(HEADER_NAME.lower()) or ""
        if not 토큰이같나(토큰, BOOT_TOKEN):
            return PlainTextResponse("토큰 거부", status_code=403)
    return await call_next(request)
```

> **따라할 것:** `POST /banner/label` 은 **자동으로 이 층을 탄다** — 라우트에 추가 코드가 필요 없다.
> 플래너가 할 일은 "라벨 기록을 GET 으로 만들지 않는다"를 플랜 본문에 못박고,
> 템플릿에서 `hx-post` 를 쓰게 하는 것뿐이다. **예외를 만들지 마라**(RESEARCH §ASVS V4).

**(d) htmx 폼/JSON 양쪽 받기 + Pydantic 단일 관문** `webapp/routes/jobs.py:88-124` (발췌):

```python
async def 요청_풀기(request: Request) -> JobReq:
    """JSON 과 폼 인코딩을 **둘 다** 받아 `JobReq` 로 만든다.

    htmx 는 기본이 `application/x-www-form-urlencoded` 라 `hx-post` 가 JSON 을 안 보낸다.
    JSON 만 받으면 버튼이 422 로 튕기고, 폼만 받으면 v2 스케줄러·`curl` 이 불편해진다.
    입력 모양을 둘 받되 **검증은 한 곳(Pydantic)** 에서 한다 — 그게 진짜 관문이다.

    폼을 `request.form()` 으로 풀지 않는다. Starlette 은 urlencoded 폼에도
    `python-multipart` 를 요구해서 ... stdlib `parse_qsl` 로 충분하고, 이게 정확히 필요한 만큼이다.
    """
```

그리고 입력 모양 제약(`routes/jobs.py:126-137`):

```python
# adId 의 모양. `nad-` 로 시작하는 영숫자·`_`·`-` 만 (ASVS V5 / T-1-31).
# 길이 상한을 함께 둔다 — 패턴만 있으면 1MB 짜리 문자열이 그대로 통과한다.
AdId = Annotated[str, StringConstraints(pattern=r"^nad-[A-Za-z0-9_-]{1,64}$")]
```

> **따라할 것:** `LabelReq(BaseModel)` 에 `run_dir: str` · `타오바오상품번호: <패턴+길이상한>` ·
> `판매자상품코드: <패턴>` · `이미지순번: int(ge=0, le=상한)` · `사람판정: Literal["배너","제품","무내용"]`.
> **`Literal` 이 핵심이다** — `argv.py:8` 이 "Literal 화이트리스트가 1차 방어선"이라고 적었고,
> 라벨 값이 자유 문자열이면 DB 에 아무 글자나 들어가 `게이트집계` 분모가 조용히 틀어진다.

**(e) 썸네일 라우트의 경로 탈출 방어 — 이름을 받지 않고 화이트리스트를 통과시킨다**
`webapp/paths.py:139-151`:

```python
def run_dir_path(name: str) -> Path:
    """회차 이름 → 디렉터리. **화이트리스트를 통과한 이름만** 경로가 된다.

    사용자 입력으로 경로를 조합하지 않는다(ASVS V12 / 위협 T-1-11).
    `..` 를 거르는 식의 블랙리스트가 아니라, 실제로 존재하는 회차 목록에
    들어 있는 이름만 통과시킨다 — 이 함수가 run-dir 이름의 **유일한 관문**이고
    이후 모든 플랜이 여기를 통과한 뒤에만 파일을 만진다.
    """
    if name not in scan_run_dirs():
        raise ValueError(f"모르는 회차다: {name}")
    return runs_root() / name
```

`webapp/routes/board.py:271-280` (그 관문을 쓰는 라우트 쪽):

```python
    # 회차 선택. 쿼리로 온 이름은 `paths.run_dir_path` 화이트리스트를 통과해야 한다 —
    # 사용자 입력으로 경로를 조합하지 않는다(위협 T-1-11 / ASVS V12).
    # `..` 를 거르는 블랙리스트가 아니라, 실제로 존재하는 회차 목록에 든 이름만 통과한다.
    선택 = run_dir or (회차들[0]["name"] if 회차들 else None)
    if run_dir is not None:
        try:
            paths.run_dir_path(run_dir)
        except ValueError as e:
            return PlainTextResponse(f"{e}", status_code=400)
```

그리고 부모 디렉터리 **경로 비교**(접두 비교 금지) `webapp/jobs.py:437-444`:

```python
    p = Path(path).expanduser()
    if not p.is_absolute():
        raise ValueError("대상 파일 경로가 절대경로가 아니다")
    p = p.resolve()
    # 부모 디렉터리 비교다. 접두 비교(`startswith`)로 하면 `web-남의것/` 같은
    # 형제 디렉터리가 통과한다 — 경계를 글자가 아니라 경로로 본다.
    if p.parent != _web_dir(run_dir).resolve():
        raise ValueError("회차 밖 대상 파일은 쓸 수 없다")
```

> **따라할 것:** `GET /banner/thumb/{run_dir}/{상품순번}/{장순번}` — **정수 인덱스만 받는다**
> (RESEARCH Pitfall 7). `run_dir` 은 `paths.run_dir_path` 화이트리스트를 탄다.
> 서버가 산출물 JSON 의 `장[].썸네일` 값을 읽어 경로를 만들고, 만든 뒤 **위 `p.parent != ...resolve()`
> 비교를 한 번 더** 건다(2층). `FileResponse(..., media_type="image/webp")`.
> **절대 하지 말 것:** `app.mount("/static", StaticFiles(...))`(`main.py:84`)를 캐시 디렉터리로
> 늘리는 것 — 271MB 원본 디렉터리 전체가 토큰 없이 열린다.

**(f) 산출물 읽기 — 레지스트리가 정본, glob 금지, 실패는 사유를 들고 온다**
`webapp/routes/board.py:119-172` (핵심부):

```python
def _load_join(run_dir_name: str) -> tuple[dict | None, str | None, str | None]:
    """마지막 성공 스캔의 조인 산출물을 읽는다 — `(문서, 스캔시각, 사유)`.
    ...
    어느 잡이 성공했는지는 **레지스트리가 정본**이다. 회차 폴더의 파일을 뒤져서 찾지
    마라 — 파일이 있다는 것과 그 잡이 성공했다는 것은 다르다(중간에 죽은 잡도 반쯤
    쓴 파일을 남긴다). `jobs.latest_done` 이 그 질문에 답하려고 있는 함수다.

    **스캔을 한 번도 안 돌린 것은 실패가 아니다** — 사유 없이 `(None, None, None)` 이고,
    화면이 "아직 조인 스캔을 안 돌렸다" 를 말한다. 사유를 채우면 고장으로 읽힌다.
    """
    try:
        잡 = jobs.latest_done("bulsaja_scan", run_dir_name)
    except Exception as e:
        return None, None, f"{type(e).__name__}: {e}"
    if not 잡:
        return None, None, None

    경로 = 잡.get("result_path")
    ...
    try:
        문서 = json.loads(Path(경로).read_text(encoding="utf-8"))
    except Exception as e:
        # 트레이스백을 화면에 싣지 않는다 — 경로·내부 구조가 그대로 나간다(ASVS V7).
        return None, None, f"{type(e).__name__}: {e}"
    if not isinstance(문서, dict):
        return None, None, "조인 산출물의 모양이 다르다 — 조인 스캔을 다시 돌려라"
    if not (문서.get("마켓그룹") or []):
        # 시각도 같이 버린다 — 못 믿는 산출물의 시각을 "마지막 스캔" 으로 띄우면
        # 화면이 "방금 훑었는데 이 모양이다" 로 읽힌다.
        return None, None, ("조인 산출물에 마켓그룹이 없다 — 조인 스캔을 다시 돌려라 "
                            "(0개는 관측이 아니라 조회 실패다)")
    return 문서, 시각, None
```

> **따라할 것:** `_load_banner(run_dir)` 를 **이 함수 모양 그대로** 만든다:
> `jobs.latest_done("banner_scan", run_dir)` → `result_path` → JSON → `isinstance(dict)` →
> **`문서.get("상품")` 이 비면 `None` + 사유**(CR-01 과 같은 규율: 0건은 관측이 아니라 실패일 수 있다).
> 화면은 그 사유를 배너로 띄운다. 트레이스백 금지 — `f"{type(e).__name__}: {e}"` 축약.

**(g) 예외 → 상태코드 번역표** `webapp/routes/jobs.py:354-392` (표 부분):

```python
def _작업만들기(request: Request, kind: str, req: JobReq, **더):
    """POST 핸들러 3줄의 공통부. **kind 는 호출부가 고정한다** — 요청에서 오지 않는다.

    예외 → 상태코드 표. **`except` 의 순서가 곧 동작이다** (상속 관계가 있다):

      | 예외                       | 코드 | 뜻                                   |
      |----------------------------|------|--------------------------------------|
      | `jobs.AccountMismatchError`| 409  | 붙어 있는 불사자 계정이 다르다 (ENG-08) |
      | `jobs.BusyError`           | 409  | 지금은 때가 아니다 (같은 kind 중복 포함) |
      | `ValueError`               | 400  | 요청이 틀렸다 (모르는 회차 등)         |
      | `KeyError`                 | 500  | 설정이 비었다                          |
      | `RuntimeError`             | 500  | 그 밖의 서버 문제                      |
    """
```

> **따라할 것:** 배너 스캔 접수 라우트(`POST /jobs/banner/scan`)는 `routes/jobs.py` 의
> `_작업만들기` 를 **그대로 재사용**한다 — `routes/banner.py` 에 잡 생성을 복제하지 마라.
> 접수 버튼은 기존 잡 패널 흐름(`_응답` → `_job_panel.html`)에 붙는다.

---

### 4. `webapp/templates/banner_review.html` (template · server-render)

**Analog:** `webapp/templates/board.html` (578행)

**(a) 파일 머리 주석 + 자동 이스케이프 규약** `webapp/templates/board.html:1-11`:

```jinja
{# 보드 화면 — Plan 01-03 이 만든 셸에 Plan 01-04 가 데이터를 채웠다.
   ...
   정적파일은 전부 /static/vendor/ 다. CDN 을 런타임에 부르지 않는다 —
   맥북이 오프라인이거나 CDN 이 흔들리면 관제탑이 통째로 안 뜬다.

   자동 이스케이프를 끄는 필터를 쓰지 마라 — 상품명에 중국어 원문과 특수문자가
   섞여 들어온다(T-1-17). ... #}
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  {# 토큰이 Referer 로 새 나가지 않게. 어차피 외부로 나갈 일이 없지만 기본을 좁혀 둔다 #}
  <meta name="referrer" content="no-referrer">
  <title>셀러 관제탑</title>
  <link rel="stylesheet" href="/static/vendor/pico-2.1.1.min.css">
  <link rel="stylesheet" href="/static/vendor/tabulator-6.5.3.min.css">
```

> **따라할 것:** `pico-2.1.1.min.css` 만 링크한다. **`tabulator-6.5.3.min.css` 줄은 빼라** —
> RESEARCH §검수 화면이 Tabulator 행 확장을 기각했다(100상품 = 100클릭, D-03 "훑기"가 "클릭"이 된다).
> `| safe` 금지는 `main.py:39-40` 의 grep 가드가 집행한다.

**(b) 토큰 헤더 배선 — 한 줄** `webapp/templates/board.html:83-86`:

```jinja
{# 이 한 줄이 모든 htmx 쓰기 요청에 X-CT-Token 을 붙인다.
   쿠키가 아니라 헤더인 이유: 커스텀 헤더는 교차 오리진에서 붙일 수 없다(CORS 미개방).
   쿠키 = 페이지 접근, 헤더 = 쓰기 인가. #}
<body hx-headers='{"X-CT-Token": "{{ token }}"}'>
```

> **따라할 것:** 그대로 복사. 라우트 ctx 에 `"token": security.BOOT_TOKEN` 을 넣는다
> (`routes/board.py:288` 의 ctx 첫 줄이 그 모양이다).

**(c) 쓰기 버튼 = `hx-post`** `webapp/templates/board.html:204-227` (주석 + 실제 배선):

```jinja
    {# 작업 버튼 (D-15). **hx-post 다 — hx-get 으로 바꾸지 마라.**
       교차 사이트 단순 GET 에는 Origin 헤더가 없어서, 작업 생성을 GET 으로 만드는
       순간 security.guard 의 Origin 층이 통째로 무력화된다 (T-1-01b).
       ...
       hx-disabled-elt="this" — 응답이 올 때까지 버튼을 잠근다. ...
       hx-swap="outerHTML" — 조각이 <section id="job-panel"> 을 스스로 품는다.
       innerHTML 로 하면 같은 id 의 섹션이 중첩된다. #}
    <div class="job-actions" role="group">
      <button type="button"
              hx-post="/jobs/prep"
              hx-include="#f-acct"
              hx-target="#job-panel" hx-swap="outerHTML"
              hx-disabled-elt="this"
              hx-on::before-request="document.getElementById('job-error').hidden = true"
              hx-on::response-error="var b = document.getElementById('job-error');
                b.textContent = event.detail.xhr.status === 409 ? ... ;
                b.hidden = false;">새로 수집</button>
```

> **따라할 것:** 장 클릭 = `hx-post="/banner/label"` + `hx-swap="outerHTML"` 로 그 `<img>`
> (또는 감싼 `<figure>`) 하나만 교체. `hx-vals` 로 `(타오바오상품번호, 이미지순번, 사람판정)` 을 싣는다.
> 오류 표시는 위 `hx-on::response-error` 관용구를 그대로 — 라벨이 저장 안 됐는데 테두리만
> 바뀌면 "미탐 0%"가 거짓말이 된다.
> **바꿀 것:** 상품 줄 "확인함" 버튼도 같은 POST 계열이다(RESEARCH Pitfall 8 / D-03a).

**(d) CSS — Pico 변수를 쓰고 색만으로 가르지 않는다** `webapp/templates/board.html:22-46`:

```css
    /* 신선도 경고 (D-16). 낡은 판정으로 입찰가를 올리는 게 이 단계의 실질 위험이라
       사용자가 스크롤하기 전에 눈에 걸려야 한다. Pico 변수를 써서 다크모드도 따라간다. */
    .stale {
      border-left: .4rem solid var(--pico-del-color, #d93526);
      background: var(--pico-mark-background-color, #fff3cd);
      ...
    }
    /* 시스템 사정 배너 (Pitfall 3). **`.stale` 과 생김새가 달라야 한다.**
       ... 색만으로 가르지 않는다(흑백 출력·색맹): 테두리 위치와 기울임까지 바꾼다. */
    .system-warn {
      border-left: .4rem dashed var(--pico-primary, #0172ad);
      ...
      font-style: italic;
    }
    /* 기작업 행 회색 처리 (D-08). **숨기는 게 아니다** — 목록에 남고 태그가 보이며
       사용자가 직접 체크하면 대상에 들어간다. 기본 선택에서만 빠진다.
       `pointer-events` 를 막지 마라: 못 고르게 하는 순간 D-08 이 깨진다. */
    .tabulator-row.ct-done { opacity: .5; font-style: italic; }
```

> **따라할 것:** 배너(빨강 실선) / 무내용(회색 점선) / 미판정(주황 + `⚠` 글자)을
> **테두리 스타일까지 다르게** 만든다 — 색만으로 가르면 흑백·색맹에서 미탐 검수가 무너진다.
> 스킵된 상품은 `.ct-done` 처럼 흐리게 하되 **전장을 그대로 깐다**(D-03a · D-09).
> 추가로 RESEARCH §검수 화면이 요구한 3줄: 썸네일 `height: 200px; width: auto`,
> 줄 넘침은 `overflow-x: auto`, 화면 밖 상품은 `content-visibility: auto` + `loading="lazy"`.

**(e) SSE 진행 로그는 기존 조각을 include 한다** `webapp/templates/_job_panel.html:43-54`:

```jinja
{% if job %}
<section id="job-panel">
  <h2>작업 진행</h2>

  {% include "_job_status.html" %}

  <div hx-ext="sse" sse-connect="/jobs/{{ job.id }}/stream" sse-close="done">
    <div id="job-log-box"><pre id="job-log" sse-swap="log">작업 로그를 기다리는 중…</pre></div>
    <div id="job-done" sse-swap="done"></div>
  </div>
</section>
```

> **따라할 것:** 스캔 접수 UI 를 검수 페이지에 둔다면 `{% include "_job_panel.html" %}` 로 끝낸다.
> **스트림은 활성 잡 하나만** (같은 파일 주석: HTTP/1.1 호스트당 6커넥션, T-1-24).

---

### 5. `webapp/jobs.py` 수정 (job registry · event-driven)

**Analog:** 같은 파일의 `bulsaja_*` 3종 등록부. **네 군데를 한 커밋에서 같이 고친다.**

**(a) `JobKind` + `KINDS` 는 항상 같이** `webapp/jobs.py:54-62`:

```python
# **`JobKind` 와 `KINDS` 는 항상 같이 고친다.** 하나만 고치면 타입 검사는 통과하는데
# `create_job` 첫 줄의 `kind not in KINDS` 가 런타임에 거부한다 — "코드상 맞는데 화면에서만
# 안 되는" 부류의 고장이다.
JobKind = Literal["prep", "run", "bids_preview", "bids_commit",
                  "revert_only", "revert_all", "synthetic",
                  "bulsaja_profile", "bulsaja_index", "bulsaja_scan"]

KINDS: tuple[str, ...] = ("prep", "run", "bids_preview", "bids_commit",
                          "revert_only", "revert_all", "synthetic",
                          "bulsaja_profile", "bulsaja_index", "bulsaja_scan")
```

**(b) `WRITE_KINDS` — 넣지 않는다** `webapp/jobs.py:72-77`:

```python
WRITE_KINDS: frozenset[str] = frozenset({"prep", "bids_commit", "revert_only", "revert_all"})
# **불사자 잡 3종을 여기 넣지 마라.** 셋 다 불사자에 아무것도 안 쓴다(workdata·프로필 조회는
# 읽기 전용이다). 넣으면 3시간 32분짜리 인덱스가 도는 동안 입찰가 인상·되돌리기가 전부
# 409 가 된다 — 위 "쓰기가 아닌 것까지 막는 가드는 사람이 가드를 끄게 만든다" 가 바로 이 경우다.
```

> **따라할 것:** `banner_scan` 을 `WRITE_KINDS`·`BULSAJA_KINDS` **어디에도 넣지 않는다**
> (RESEARCH §잡 종류 배치 권고). 4분 동안 입찰가 인상이 409 가 되면 사람이 가드를 끈다.

**(c) `SINGLETON_KINDS` — 넣되 사유 주석을 바꿔 적는다** `webapp/jobs.py:88-99`:

```python
# **같은 kind 가 동시에 두 개 돌면 안 되는 작업.** 전역 쓰기 락과 **다른 이유로** 존재한다.
#
# 왜 전역이 아니라 kind 단위인가: 인덱스 잡은 불사자에 아무것도 안 쓴다. ...
# 그런데 **같은 잡 두 개가 동시에 도는 건 막아야 한다.** 각자 최소간격 0.26초(초당 4회)를
# 지켜도 합산 8회/초라 서버 정책(RateLimit-Policy: 240;w=60)을 넘긴다. ...
# 화면의 `hx-disabled-elt` 는 이 방어의 대체물이 **아니다.** POST 왕복 중에만 버튼을 잠그므로
# 새로고침한 뒤 다시 누르면 두 번째 프로세스가 그대로 뜬다.
#
# ⚠️ `BULSAJA_KINDS` 와 멤버가 같지만 **뜻이 다르다.** 앞은 "불사자 MCP 를 부른다",
#    이쪽은 "둘이 동시에 돌면 레이트리밋 예산이 깨진다" 다. 합치지 마라 ...
SINGLETON_KINDS: frozenset[str] = frozenset({"bulsaja_index", "bulsaja_scan"})
```

> **따라할 것:** `"banner_scan"` 추가. **바꿀 것:** 위 주석 블록 아래에 한 줄을 덧붙인다 —
> *"`banner_scan` 은 레이트리밋 때문이 아니다. 불사자 MCP 를 0회 부른다.
> 같은 잡 둘이 271MB 를 두 번 받는 낭비를 막으려는 것이다."*
> (CONTEXT §Claude's Discretion 이 이 사유 표기를 명시적으로 요구했다.)

**(d) DDL — `banner_label` 을 여기에 추가한다** `webapp/jobs.py:140-160` (`ss_index` 블록과 그 판별 기준):

```python
CREATE TABLE IF NOT EXISTS ss_index (
  product_id      TEXT PRIMARY KEY,
  smartstore      TEXT,
  market_group_id TEXT NOT NULL,
  group_total     INTEGER,
  unresolved      INTEGER NOT NULL DEFAULT 0,
  observed_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ss_index_smartstore ON ss_index(smartstore);
CREATE INDEX IF NOT EXISTS idx_ss_index_group ON ss_index(market_group_id);
"""
# ※ 보드용 캐시 테이블은 만들지 않는다. 보드는 매번 `result.json` 을 투영한다(수십 ms).
#    캐시는 최적화이고, 지금 넣으면 "진실이 둘" 위험만 는다.
...
# ※ 이건 보드 캐시가 아니다. 보드 캐시는 `result.json` 에서 언제든 재생성되는 투영이라
#    두는 순간 진실이 둘이 되지만, 이건 **3시간 반을 태워야 다시 얻는 외부 관측 기록**이다
#    (36그룹 / 47,105 상품). 재생성이 공짜가 아니면 그건 캐시가 아니라 기록이다.
# ※ `unresolved` 는 429·타임아웃으로 **못 본 것**이다. 0 으로 접지 마라 — 미조회를 성공으로
#    적으면 그 행이 화면에서 "미해소(광고 쪽 오류)" 로 둔갑한다(Pitfall 3).
```

> **따라할 것:** `banner_label` DDL 을 같은 문자열 안에 잇고, 아래 `※` 블록에 판별 근거를 적는다 —
> *"사람 라벨은 재생성 불가다(사람의 시간). 그래서 캐시가 아니라 기록이고, 위의 '보드용 캐시
> 테이블은 만들지 않는다' 와 충돌하지 않는다."* 컬럼은 RESEARCH §라벨 저장의 DDL 그대로
> (`PRIMARY KEY (run_dir, 타오바오상품번호, 이미지순번)` — **URL 을 키로 쓰지 마라**, D-01a 실측).
> **절대 하지 말 것:** 기계 판정(배너/제품/무내용)을 이 테이블에 복사 — 산출물 JSON 이 정본이다.
> 스키마 정본이 한 곳이라는 규율은 `ss_index_build.py:165-176`(스키마확인 · 만들지 않고 exit 4)와
> 짝을 이룬다. `banner_scan.py` 도 **테이블을 만들지 않는다**(애초에 SQLite 를 안 만진다).

**(e) `_build_argv` 분기** `webapp/jobs.py:493-566` — 위 §1(e) 발췌 참조. 추가 분기는:

```python
    if kind == "banner_scan":
        if targets_path is None:   # ← RESEARCH 가 요구한 같은 규율
            raise ValueError(...)
```

> **판단 필요:** 배너 스캔의 "대상"은 조인 산출물 그 자체다(상품 목록을 따로 안 넘긴다).
> `routes/jobs.py:661-687`(`post_bulsaja_scan`)이 **서버가 대상을 계산해 넘기는** 관용구를 보여준다:
> *"대상은 여기서 만든다 — 화면이 고른 행 목록을 받지 않는다. 회차의 판정 결과가 정본이고,
> 그래야 '본 것과 다른 게 돈다' 가 성립하지 않는다 (D-11 / FLOW-02)."*
> → 권고: `--join` 에 **직전 성공 `bulsaja_scan` 의 `result_path`** 를 넘기고,
> 그게 없으면 **409**(요청은 멀쩡하고 순서가 아직 아니다 — `post_bulsaja_index` 의 판단 그대로).

**(f) `caffeinate` 프리픽스** `webapp/jobs.py:474-491`:

```python
def _수면방지_프리픽스(kind: str) -> list[str]:
    """`["/usr/bin/caffeinate", "-i"]` 또는 빈 리스트.

    바이너리 존재를 확인하고 없으면 **안 붙인다.** 맥 전용 바이너리라, 없는데 붙이면
    자식이 아예 안 뜬다 — "절전 방지" 하나 때문에 잡 전체가 실행 불가가 되는 건
    바꿔치기가 너무 나쁘다. ...
    """
    if kind != "bulsaja_index":
        return []
    try:
        return [CAFFEINATE, "-i"] if os.path.exists(CAFFEINATE) else []
    except OSError:
        return []
```

> **따라할 것:** `if kind not in ("bulsaja_index", "banner_scan"):` 로 넓힌다.
> 바로 위 주석(`jobs.py:470-473`)이 *"인덱스에만 붙인다: 계정 확인은 0.14초, 조인 스캔은 18초다.
> 수 초짜리 잡에 전력 assertion 을 거는 건 비용만 있고 얻는 게 없다"* 라고 적어 뒀으므로,
> **4분 12초짜리 배너 스캔을 넣는 근거(실측 소요)를 그 주석에 한 줄 덧붙인다.**

---

### 6. `webapp/argv.py` 수정 — `BannerArgv`

**Analog:** 같은 파일 `BulsajaArgv` (`webapp/argv.py:120-196`)

**(a) CLI 인터프리터·스크립트 경로 상수** `webapp/argv.py:27-50`:

```python
# CLI 전용 인터프리터. **지금 이 코드를 돌리고 있는 인터프리터를 쓰지 마라.**
#
# 웹앱은 `.venv-web`(fastapi·uvicorn·pydantic)에서 돌고, CLI 는
# `.venv`(selenium·openpyxl·pillow·requests)가 필요하다. ...
PY_CLI = paths.repo_root() / ".venv" / "bin" / "python3"
...
# 불사자 CLI 두 개. **기존 스킬 디렉터리 밑에 둔다** — 그 자리의 스크립트는 `bulsaja_mcp`
# 를 `__file__` 기준 상대 shim 으로 이미 찾는다(`run_names.py:40-46` 관용구).
# 새 디렉터리를 파면 그 shim 경로 계산을 새로 해야 하고, 그게 STATE-01 에서 이미 한 번
# 고장났던 지점이다(윈도 절대경로 하드코딩).
SS_INDEX_BUILD = (paths.repo_root() / ".claude" / "skills" / "bulsaja-detail-page"
                  / "scripts" / "ss_index_build.py")
BULSAJA_SCAN = (paths.repo_root() / ".claude" / "skills" / "bulsaja-detail-page"
                / "scripts" / "bulsaja_scan.py")
```

> **따라할 것:** `BANNER_SCAN = (...) / "banner_scan.py"` 한 줄을 같은 자리에 추가.
> `PY_CLI` 를 쓴다 — **Pillow·Vision 이 `.venv` 에만 있으므로 이게 물리적 요구사항이다.**

**(b) 모델 + `build()`** `webapp/argv.py:120-196` (핵심 규율만 발췌):

```python
class BulsajaArgv(BaseModel):
    """불사자 CLI 호출 한 번을 표현하는 모델. `AdsArgv` 와 **같은 파일**에 둔다.

    `AdsArgv` 를 재사용하지 않는 이유: 저쪽은 `run_ads.py` 전용이고 플래그 집합이
    겹치는 게 하나도 없다. 그렇다고 다른 파일로 빼면 "조립은 한 곳" 이 깨진다 —
    `test_argv.py` 의 마지막 두 테스트가 웹앱 런타임 전체를 훑어 그걸 기계로 집행한다.
    ...
    `min_interval`·`retry_after`·`batch_size`·`expect_nick` 에 **기본값이 없다.**
    호출부(`jobs._build_argv`)가 `settings.cfg()` 로 읽어 넘긴다. 기본값을 모델이나
    CLI 에 두면 `workspace.toml` 을 고쳐도 동작이 안 바뀌는 **가짜 설정**이 된다
    (T-1-12 와 같은 부류).
    """
    ...
    def build(self) -> list[str]:
        """argv 리스트. 셸을 거치지 않으므로 따옴표·이스케이프가 필요 없다."""
        스크립트 = SS_INDEX_BUILD if self.subcommand == "index" else BULSAJA_SCAN
        av: list[str] = [*self.prefix, str(PY_CLI), str(스크립트)]
        ...
        # 경로는 전부 `str()` 로 못박는다 — `Path` 를 두면 jobs 테이블의 argv 컬럼
        # (JSON 배열) 직렬화가 터진다 (`AdsArgv.build()` 와 같은 이유).
        av += ["--db", str(self.db)]
        ...
        # **`groups` 가 None 이면 `--groups` 를 안 붙이는데, 그 상태로 인덱스를 돌리면
        # 전 그룹(실측 75,335건 · 5시간 39분)이다.** 그래서 여기서 터뜨리지 않고
        # `jobs._build_argv` 가 **먼저** ValueError 를 던진다 — 빈 값이 '전량' 으로
        # 해석되는 경로를 막는 자리는 한 곳이어야 한다(`revert_only` 와 같은 모양).
        # 조립 단계에서도 터뜨리면 같은 규칙이 두 곳이 되고, 둘이 어긋나면 어느 쪽이
        # 진짜 가드인지 모르게 된다.
        if self.groups:
            av += ["--groups", str(self.groups)]
        ...
        # 0 은 "상한 없음" 이다. 플래그를 붙여 `--limit 0` 을 넘기면 자식이 그걸
        # "0건만 처리" 로 읽을 수도 있어서, 빈 리스트 규율과 같이 **아예 안 붙인다.**
        if self.limit:
            av += ["--limit", str(self.limit)]
        return av
```

> **따라할 것:** `BannerArgv` 를 **같은 파일**에 둔다(다른 파일로 빼면 가드가 깨진다).
> 필드 제안: `join: Path`(조인 산출물) · `out: Path`(산출물 JSON) · `thumbs: Path`(썸네일 디렉터리) ·
> `cache: Path`(원본 캐시) · `run_dir: str` · `workers: int` · `vision_revision: int` ·
> `무내용_종횡비: float` · `무내용_짧은변px: int` · `스킵_잔여하한: int` · `스킵_제거율상한: float` ·
> `prefix: list[str]`. **임계값·리비전에 모델 기본값을 두지 마라** — `settings.cfg()` 가 정본이고,
> 그래야 산출물 `판정규칙` 블록(RESEARCH §산출물 계약)과 실제 동작이 같은 출처에서 나온다.
> 경로는 전부 `str()`, 0/빈값은 플래그 자체를 생략.

---

### 7. 라벨 read/write 접근 — **analog 조합 필요 (결정필요)**

**partial match.** 저장소에 "웹앱이 SQLite 에 쓰는 새 모듈"의 선례가 없다.
읽기 전용 모듈(`bulsaja_index.py`)과 쓰기(`jobs.py`)가 갈라져 있다.

**(a) 읽기 쪽 analog** `webapp/bulsaja_index.py:59-67` + `81-127`:

```python
def _ro_conn() -> sqlite3.Connection:
    """읽기 전용 커넥션. `mode=ro` URI 라 쓰기는 `OperationalError` 로 터진다.

    호출 전에 파일 존재를 확인해야 한다 — `mode=ro` 는 파일이 없으면 열기 자체가 실패한다
    (그게 의도다: 읽기 경로가 파일을 만들지 않는다).
    """
    cx = sqlite3.connect(f"file:{db_path()}?mode=ro", uri=True, timeout=5)
    cx.row_factory = sqlite3.Row
    return cx


def lookup(smartstores) -> dict:
    """...
    DB 파일이 없으면 `{}` 다. **만들지 않는다.**
    같은 번호가 여러 번 관측됐으면 **최신 관측이 이긴다** ...
    """
    ...
    if not db_path().is_file():
        return {}
    ...
    try:
        cx = _ro_conn()
    except sqlite3.Error:
        # 파일이 있어도 못 열 수 있다(권한·손상). 화면이 통째로 500 이 되는 것보다
        # "인덱스가 아직 없다" 로 보이는 쪽이 낫다 — 그 상태도 미조회로 떠야 맞다.
        return {}
    try:
        for i in range(0, len(키들), 묶음):
            조각 = 키들[i:i + 묶음]
            자리 = ",".join("?" * len(조각))
            # 오름차순으로 훑어 **뒤에 온 최신 관측이 앞을 덮게** 한다.
            행들 = cx.execute(
                "SELECT smartstore, product_id, ... FROM ss_index WHERE smartstore IN ({자리}) "
                "ORDER BY observed_at ASC", tuple(조각)).fetchall()
```

**(b) 쓰기 쪽 analog** `webapp/jobs.py:252-272`:

```python
def _conn() -> sqlite3.Connection:
    """커넥션은 작업마다 새로 연다. `timeout=5` 로 잠깐의 경합은 기다린다."""
    cx = sqlite3.connect(db_path(), timeout=5)
    cx.row_factory = sqlite3.Row
    return cx


def init_db() -> None:
    """테이블·인덱스를 만들고 WAL 을 켠다. 여러 번 불러도 안전하다.

    WAL 인 이유: 상태 폴링(읽기)과 잡 생성·종료 기록(쓰기)이 겹친다.
    기본 저널 모드면 읽는 동안 쓰기가 막혀 버튼이 잠깐씩 먹통이 된다.
    """
    db_path().parent.mkdir(parents=True, exist_ok=True)
    cx = _conn()
    try:
        cx.execute("PRAGMA journal_mode = WAL")
        cx.executescript(DDL)
        cx.commit()
    finally:
        cx.close()
```

**(c) 순환 import 회피 관용구** `webapp/bulsaja_index.py:47-57`:

```python
def db_path() -> Path:
    """인덱스가 사는 파일. `jobs.db_path()` 와 **같은 파일**이다.

    `jobs` 를 import 하지 않고 세 줄을 복제한다. ENG-08 가드가 `jobs.create_job` 에서
    이 모듈의 `profile_ok` 를 부르므로, 여기서 `jobs` 를 import 하면
    `jobs → bulsaja_index → jobs` 순환이 된다. 계산이 세 줄뿐이라 복제가 싸다 —
    대신 `settings.DB_PATH` 라는 **같은 출처**를 보므로 둘이 어긋날 길은 없다.
    """
    p = Path(settings.DB_PATH).expanduser()
    return p if p.is_absolute() else paths.repo_root() / p
```

> **플래너 결정 필요 (2안):**
> **A안 — `webapp/banner_store.py` 신규** (권고): 위 (a)(b)(c)를 합친 모듈.
> 읽기는 `_ro_conn()`, 쓰기(`INSERT OR REPLACE INTO banner_label ...`)는 `_conn()`.
> DDL 은 여기 두지 않고 `jobs.DDL` 이 정본(§5(d)).
> 장점: `banner.py` 가 **순수한 채로 남는다**(§9 의 grep 가드가 `sqlite3` 를 금지한다).
> **B안 — `routes/banner.py` 안에 직접 sqlite3**: 파일이 하나 준다.
> 단점: 라우트가 얇다는 규율(`routes/jobs.py:36-39`)이 깨지고, 라벨 로직을 단위테스트하려면
> TestClient 가 필요해진다.
> **어느 쪽이든 `banner.py` 에는 sqlite3 를 넣지 않는다.** `게이트집계(기계판정, 사람라벨)` 는
> dict 두 개를 받는 순수 함수다(RESEARCH §라벨 저장).

---

### 8. `webapp/tests/test_banner.py` (unit · 순수)

**Analog:** `webapp/tests/test_state.py`(208행) + `webapp/tests/test_join.py`(676행)

**(a) 파일 docstring — 픽스처의 함정을 번호로 나열한다** `webapp/tests/test_state.py:1-18`:

```python
"""상세 상태 판정(`webapp/state.py`) 검증 — 파일 IO 없이 순수 함수만 때린다.

`join_traps` 픽스처(Plan 03-01)가 주는 dict 하나로 끝난다. 네트워크도 크레딧도 0 이다.

픽스처에 일부러 심어 둔 함정 4종을 각각 하나씩 겨눈다:
  (a) `{aiImageGenerated: true, imageTranslated: "1"}` — **판정 순서 역전 탐지** (STATE-03)
  (b) `{imageTranslated: "0"}` 이고 `aiImageGenerated` **키 자체가 없다** — 내장 캐스팅 함정 (STATE-02)
  ...
"""
```

> **따라할 것:** RESEARCH §Pattern 1 의 **실측 함정 표본 6종**을 그대로 번호 매겨 적는다:
> ① `uploadDetailContents` 가 None(194행 중 137행) ② `renderContent` 가 `&nbsp;` 만
> ③ 같은 URL 2번(57건 중 3건 — **중복 제거하지 말고 순서 보존**) ④ 1장짜리 상품(D-07 즉시)
> ⑤ 전 장 404(ri=39 — **"배너 0장"이 아니라 판정 불가**) ⑥ `imageTranslated` 타입 4종.

**(b) 단언 스타일 — 실패 시 "무엇을 틀렸는지"를 말한다** `webapp/tests/test_state.py:33-46`:

```python
def test_불리언정규화():
    """`'0'` `'1'` `False` `1` `None` 5종이 전부 같은 규약으로 읽힌다 (STATE-02).

    실측 타입이 제각각이다 — 문자열 `'1'`/`'0'`, 불리언 `False`, 키 부재(None).
    요구사항이 예고한 정수 `1` 도 같이 받는다.
    """
    assert state.불리언정규화("0") is False      # True 면 내장 캐스팅을 그대로 쓴 것이다
    assert state.불리언정규화("1") is True
    ...
    assert state.불리언정규화(None) is False     # 키 부재 — 실측 34건 중 26건이 이 모양이다
```

> **따라할 것:** `is False` / `is True` 처럼 **정체성까지** 보는 습관과, 실패 원인을 주석으로
> 미리 적어 두는 습관. VALIDATION 이 지목한 테스트 이름 12개를 **글자 그대로** 쓴다
> (`test_렌더콘텐츠_이미지목록`, `test_None_은_예외`, `test_빈목록은_전량이_아니다`,
> `test_미판정_흡수금지`, `test_게이트집계_분모둘`, `test_미검수_분모제외`,
> `test_타오바오distinct_집계`, `test_D07_잔여부족`, `test_D08_제거율초과`, `test_사람큐_없음`,
> `test_어휘군_한중`, `test_라벨픽스처_미탐0`, `test_순서유지_상한없음`).

**(c) 회귀 픽스처를 실데이터에서 만들되 익명화한다** `webapp/tests/conftest.py:10-13` + `70-88`:

```python
원칙 둘: **Phase 3 픽스처는 진짜 마켓그룹명·계정 닉네임을 담지 않는다.**
담으면 리터럴 가드(`test_paths.py -k 리터럴` · `test_board.py::test_계정을_코드에_박지_않는다`)와
충돌하고, 저장소가 공개될 때 영업 정보가 같이 나간다. 전부 `zz*` 가짜 이름이다.
재생성 방법은 `fixtures/anonymize_join.py` 에 있다.
...
@pytest.fixture
def result_join_real() -> dict:
    """실회차 ③⑤ 194행 익명화본 — 해상률 회귀의 모수(분모).
    ...
    """
    return json.loads(RESULT_JOIN_REAL.read_text(encoding="utf-8"))
```

> **따라할 것:** `fixtures/banner_labels.json`(RESEARCH Appendix A 의 308장 정답지)은
> **URL·판매자상품코드를 익명화**하고 `(상품순번, 장순번, 라벨)` + OCR 텍스트만 남긴다.
> `fixtures/anonymize_join.py` 옆에 `anonymize_labels.py` 를 두어 재생성 경로를 남긴다 —
> Phase 3 이 그렇게 했고, 그게 없으면 다음 회차에 픽스처를 못 갱신한다.

---

### 9. `webapp/tests/test_argv.py` 수정 — **D-19 import 가드 확장 (절대조건)**

**Analog 겸 확장 대상이 셋이다.** VALIDATION 이 `test_argv.py -k import가드` 를 지목했지만,
**실제 D-19 가드의 실물은 `test_index.py` 와 `test_join.py` 에 있다.** 셋을 다 적는다.

**(a) `webapp/tests/test_join.py:589-601` — 파일 지정형 (가장 가까운 모양)**

```python
def test_조인은_네트워크도_파일도_안_연다():
    """`join.py`·`state.py` 는 dict 만 받는다 — MCP·DB·파일 접촉 0 (D-19 / T-3-10).

    웹앱 전용 venv 에는 불사자 클라이언트가 쓰는 HTTP 패키지가 없다. import 하는 순간
    ImportError 이고, 그게 이 설계의 물리적 근거다. 문자열 검사로 그 선을 고정한다.
    """
    for 파일 in ("join.py", "state.py"):
        src = (WEBAPP / 파일).read_text(encoding="utf-8")
        for 금지 in ("eroomlib", "requests", "fastapi", "starlette",
                     "APIRouter", "sqlite3", "subprocess", "httpx", "urllib"):
            assert 금지 not in src, f"{파일} 에 '{금지}' 가 있다 (D-19)"
        assert "open(" not in src, f"{파일} 이 파일을 연다 — dict 만 받아야 한다"
```

> **확장 방법:** `("join.py", "state.py")` → `("join.py", "state.py", "banner.py")`.
> **`PIL` 과 `Pillow` 를 금지 목록에 추가한다** (지금은 없다 — 이 페이즈에서 처음 필요해진다).
> `"open("` 금지도 그대로 상속된다 — `banner.py` 는 파일을 열지 않는다.

**(b) `webapp/tests/test_index.py:369-384` — 모듈 지정형 (쓰기 금지까지 본다)**

```python
def test_이_모듈은_네트워크도_쓰기도_안_한다():
    """`.venv-web` 에 `requests` 가 없다 — `eroomlib` 를 import 하면 ImportError 다 (D-19).

    문자열 검사로 때우는 게 아니라 **소스에 그 경로 자체가 없음**을 고정한다.
    MCP 접촉은 전부 CLI 자식 몫이고, 이 모듈은 CLI 가 써 둔 기록을 읽을 뿐이다.
    """
    본문 = bulsaja_index.__file__
    소스 = open(본문, encoding="utf-8").read()

    for 금지 in ("eroomlib", "requests", "fastapi", "starlette",
                 "APIRouter", "HTTPException", "subprocess"):
        assert 금지 not in 소스, f"bulsaja_index.py 에 {금지} 가 있다 (D-19)"
    for 쓰기 in ("INSERT", "UPDATE", "DELETE", "CREATE"):
        assert 쓰기 not in 소스, f"bulsaja_index.py 에 {쓰기} 가 있다 — 읽기 전용이어야 한다"
```

> **확장 방법:** A안(`banner_store.py`)을 택하면 이 모양의 **읽기/쓰기 분리 가드**가 필요하다 —
> 단, `banner_store.py` 는 `INSERT` 를 해야 하므로 `CREATE` 만 금지한다
> (*"DDL 정본은 `jobs.py` 하나다"*, §5(d)).

**(c) `webapp/tests/test_argv.py:161-186` — 트리 전체 순회형 (D-19 확장의 진짜 자리)**

```python
def test_문자열로_명령을_만드는_코드가_없다():
    """`shell=True` 와 `os.system` 이 웹앱 런타임에 0건 (T-1-10).

    조립이 한 곳이라는 주장은 "다른 곳에 조립이 없다" 를 기계로 확인해야 주장이 된다.
    """
    웹앱 = Path(A.__file__).resolve().parent
    for f in 웹앱.rglob("*.py"):
        if "tests" in f.parts:
            continue
        본문 = f.read_text(encoding="utf-8", errors="ignore")
        assert "shell=True" not in 본문, f"{f} 에 shell=True 가 있다"
        assert "os.system(" not in 본문, f"{f} 에 os.system 이 있다"


def test_sys_executable_을_쓰지_않는다():
    """웹앱 런타임 어디에도 `sys.executable` 이 없다.
    ...
    """
    웹앱 = Path(A.__file__).resolve().parent
    for f in 웹앱.rglob("*.py"):
        if "tests" in f.parts:
            continue
        assert "sys.executable" not in f.read_text(encoding="utf-8", errors="ignore"), \
            f"{f} 에 sys.executable 이 있다 — .venv-web 으로 CLI 를 띄우게 된다"
```

> **따라할 것 (D-19 절대조건의 집행 장치):** 이 순회 형태로
> `test_웹앱에_다운로더도_Pillow도_없다` 를 **새로 추가**한다:
>
> ```python
> 웹앱 = Path(A.__file__).resolve().parent
> for f in 웹앱.rglob("*.py"):
>     if "tests" in f.parts:
>         continue
>     본문 = f.read_text(encoding="utf-8", errors="ignore")
>     for 금지 in ("from PIL", "import PIL", "urllib.request", "import requests",
>                  "httpx.", "urlopen("):
>         assert 금지 not in 본문, f"{f} 에 {금지} 가 있다 (D-19)"
> ```
>
> **왜 트리 전체인가:** 파일 지정형(a)은 `banner.py` 만 지킨다. 다음 사람이
> `routes/banner.py` 에 썸네일 생성을 넣으면 (a)는 통과한다. D-19 는 **`webapp/` 전체**가
> 대상이므로 순회형이어야 주장이 성립한다 — `test_argv.py:163-165` 주석이 그 논리를 이미 적었다.
> **주의:** `webapp/tests` 안에도 이 문자열을 남기지 마라 — `test_argv.py:9-14` 의
> "가드가 감시하는 문자열을 테스트가 들고 있으면 예외가 생긴다" 규율대로
> `"from " + "PIL"` 처럼 런타임 조립한다.

---

### 10. `webapp/tests/test_routes_banner.py` (route test)

**Analog:** `webapp/tests/test_routes_jobs.py:1-72`

```python
"""작업 라우터(`webapp/routes/jobs.py`) 검증 — **실제 CLI 는 한 번도 안 뜬다.**
...
겨누는 위협:
  T-1-01b  작업 생성이 전부 POST 이고 GET 은 아무것도 만들지 않는다
  T-1-02   토큰 없는 쓰기는 403
  T-1-23   클라이언트가 작업 종류·argv 를 고르지 못한다
  T-1-09   이미 도는 쓰기 작업은 409 로 거부되고 **사유가 몸통에 실린다**
"""
...
@pytest.fixture
def 화면(client, tmp_path, monkeypatch):
    """보드에서 온 것처럼 쿠키까지 붙인 클라이언트 + tmp 잡 DB."""
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.setattr(settings, "JOB_LOG_DIR", str(tmp_path / "logs"))
    jobs.init_db()
    client.cookies.set(security.COOKIE_NAME, security.BOOT_TOKEN)
    yield client
    ...


def test_토큰_없는_작업생성은_403(화면, 엿듣기):
    """SAFE-02 — 부팅 토큰 없이는 아무 작업도 못 만든다."""
    응답 = 화면.post("/jobs/prep", json={}, headers={"X-CT-Token": "wrong-token"})
    assert 응답.status_code == 403
    assert not 엿듣기, "토큰이 틀렸는데 작업 생성까지 갔다"


def test_타사이트_origin_은_토큰이_맞아도_403(화면, 엿듣기):
    """SAFE-01 — 다른 탭이 쏘는 쓰기(CSRF). 토큰이 새도 여기서 막힌다."""
    응답 = 화면.post("/jobs/prep", json={}, headers={"Origin": "https://evil.com"})
    assert 응답.status_code == 403
    assert not 엿듣기
```

> **따라할 것:** 위 `화면` 픽스처를 그대로(+ `banner_label` 을 위해 `jobs.init_db()` 가 필요하다 —
> DDL 이 거기 있다). VALIDATION 이 지목한 3개 테스트:
> · `test_GET_무부작용` — `GET /banner/review` 두 번 호출 후 `banner_label` 행수·mtime 불변
>   (`routes/board.py:12-17` 의 "GET 은 서버 상태를 안 바꾼다" 를 기계로 집행)
> · `test_경로탈출` — `/banner/thumb/{run_dir}/../../etc/passwd` · `%2e%2e%2f` · 절대경로 → 400/404
> · `test_라벨_POST_토큰` — 위 403 테스트 2개를 `/banner/label` 로 복제 + `GET /banner/label` 은 405
> 추가로 VALIDATION §성공기준 3 의 grep 가드: *"`routes/banner.py` 에 '보류/대기' 상태나
> 큐 엔드포인트가 **없음**"* — `test_join.py:589` 의 소스 문자열 검사 형태로 쓴다.

---

### 11. `webapp/tests/test_ocr_determinism.py` — **analog 없음**

`webapp/pytest.ini:1-9` 가 전제를 못박는다:

```ini
# 웹앱 전용 pytest 설정.
#
# testpaths 를 일부러 비워둔다 — 실행은 항상 저장소 루트에서
# `.venv-web/bin/pytest webapp/tests ...` 형태로 경로를 명시해 돈다.
# webapp/__init__.py · webapp/tests/__init__.py 가 있으므로 pytest 가
# 패키지 조상을 따라 저장소 루트를 sys.path 에 넣어준다 → `import webapp.paths` 가 산다.
```

**현재 스위트 355개가 전부 `.venv-web` 으로 돈다.** `.venv` 로 도는 테스트는 0건이고,
`.venv` 에는 pytest 가 깔려 있는지조차 확인되지 않았다(VALIDATION §Wave 0 이 Vision 설치만 적었다).

> **플래너가 반드시 처리할 것:**
> ① `.venv` 에 pytest 설치 여부 확인 → 없으면 Wave 0 에 `.venv/bin/pip install pytest` 추가
> ② `conftest.py` 는 `.venv-web` 전용 import(`fastapi.testclient`)를 **지연 import** 하고 있어
>    (`conftest.py:140-142`) 이 파일에서는 안전하다. 다만 `conftest.py:22` 의
>    `from webapp import paths, settings` 는 `.venv` 에서도 import 가능해야 한다
>    (`paths`·`settings` 는 stdlib + `webapp` 내부만 쓴다 — **확인됨, 안전**).
> ③ `.venv` 실행에서 `webapp/tests` 전체를 수집하면 fastapi 가 없어 collect 에러가 난다.
>    VALIDATION 이 적은 대로 **파일 하나만 지목**해 돌린다:
>    `.venv/bin/python3 -m pytest webapp/tests/test_ocr_determinism.py`
> ④ 이 파일에 `pytest.importorskip("Vision")` 을 **쓰지 마라** — `conftest.py:136-138` 이
>    같은 함정을 이미 적었다: *"`pytest.importorskip` 으로 덮지 않는다 — 덮으면 Wave 1 이
>    라우트를 못 만들어도 테스트가 초록으로 보인다."* 미설치는 **실패**여야 한다.
> ⑤ 결정성 단언은 RESEARCH §Pattern 3 실측 기준: 같은 이미지 3회 → 출력 완전 동일,
>    `setRevision_(3)` 이 소스에 박혀 있음을 문자열로도 확인(OS 업데이트 방어).

---

## Shared Patterns

### S-1. "판정의 정본은 CLI 산출물" — 웹앱은 투영만

**Source:** `webapp/routes/board.py:19-22` · `webapp/bulsaja_index.py:7-9`
**Apply to:** `webapp/banner.py` · `webapp/routes/banner.py` · 템플릿

```python
"""**CLI 를 실행하지 않는다.** 보드 데이터는 `run-dir/result.json` 을 읽어 투영할 뿐이라
네트워크도 크레딧도 광고비도 0 이다(STACK.md "세 번째 길")."""
```

```python
"""이게 `board.py` 와 같은 "세 번째 길" 이다. 인덱스 데이터는 CLI 를 실행해서도, CLI 모듈을
불러와서도 얻지 않는다. CLI 자식이 **이미 써 둔 기록**을 읽을 뿐이다."""
```

> 배너 판정 규칙(어휘군 매칭·무내용 규칙·D-07/D-08)은 **`banner_scan.py` 에만** 산다.
> `webapp/banner.py` 가 스킵 규칙을 "재현"하면 진실이 둘이 된다 —
> RESEARCH §Recommended Project Structure 의 "스킵 규칙 재현" 표현은 **집계·표시용 읽기**로
> 좁혀 읽어야 하고, 플래너는 그 함수 이름을 `스킵사유읽기()` 처럼 **읽기임이 드러나게** 지어라.

### S-2. 화이트리스트 투영 — 받은 dict 를 통째로 템플릿에 넘기지 않는다

**Source:** `webapp/routes/board.py:61-80`
**Apply to:** `routes/banner.py` 의 ctx 조립

```python
def _불사자표시() -> dict:
    """보드 상단에 상시로 띄울 불사자 계정 정보 (ENG-08 / 성공기준 6).

    **필요한 값만 뽑아 싣는다.** `bulsaja_index.profile()` 응답을 통째로 넘기지 않는
    이유는 두 가지다: ① 이 파일의 화이트리스트 투영 관례(SAFE-03) ② 불사자 응답에
    섞여 오는 모델 대상 지시문(`표시규칙`)이 화면으로 새는 길을 구조적으로 막는 것.
    `profile()` 이 이미 그 필드를 버리지만, 투영이 두 번째 벽이다.
    """
    받은것 = bulsaja_index.profile()
    표시 = {
        "닉네임": (받은것 or {}).get("닉네임") or None,
        ...
    }
```

> 산출물 JSON 에는 CDN URL 원문이 들어 있다. 검수 화면은 **서버 썸네일**을 쓰므로
> 템플릿에 URL 을 실을 이유가 없다(실으면 브라우저가 외부 CDN 에 직접 붙어 Referer 가 샌다 —
> RESEARCH §Security). `{판매자상품코드(표시용), 상세상태, 장수, 제거율, 스킵사유, 장[{순번,판정,사유}]}`
> 만 투영한다.

### S-3. 실패는 사유를 들고 오고, 트레이스백은 화면에 안 싣는다

**Source:** `webapp/routes/board.py:99-117`
**Apply to:** 모든 신규 라우트

```python
def _load_result(run_dir_name: str) -> tuple[dict, str | None]:
    """`result.json` 을 읽는다. 실패하면 `({}, 사유)` — **폴백하지 않는다**.

    다른 회차로 몰래 갈아타거나 빈 dict 를 성공인 척 돌려주지 않는다. 읽기 실패는
    화면에 사유를 띄우고 빈 보드를 보여준다: 이 실패는 돈으로 이어지지 않으므로
    프로세스를 죽일 일이 아니고(저장소 S-2 판별 기준), 그렇다고 조용히 넘어가면
    사용자가 "오늘은 판정 대상이 없구나" 로 오독한다.

    예외 문자열은 `f"{type(e).__name__}: {e}"` 로 축약한다 — 트레이스백을 화면에
    실으면 경로·내부 구조가 그대로 나간다(ASVS V7).
    """
    try:
        raw = (paths.run_dir_path(run_dir_name) / "result.json").read_text(encoding="utf-8")
        return json.loads(raw), None
    except Exception as e:
        return {}, f"{type(e).__name__}: {e}"
```

> **`_load_result` 와 `_load_join` 의 반환 빈값이 다른 것**(`{}` vs `None`)에 뜻이 있다
> (`routes/board.py:123-128`). 배너는 `_load_join` 쪽 — **`None` = "아직 배너 스캔을 안 돌렸다"**.
> 빈 dict 를 주면 화면이 "판정 대상 0건"으로 읽히고, 그게 CR-01 과 같은 병이다.

### S-4. 설정은 한 곳 — 숫자를 코드·템플릿에 박지 않는다

**Source:** `webapp/settings.py:19-45`
**Apply to:** `jobs._build_argv` → `BannerArgv` 로 흐르는 모든 임계값

```python
DEFAULTS = {
    "port": 8765,                  # 127.0.0.1 전용. 인증이 없으므로 외부 바인드 금지
    ...
    # ── Phase 3 (조인 · 상세 상태) 에서 더한 키 ───────────────────────────
    # **이 8키는 일부러 모듈 상수로 올리지 않는다.** 상수를 늘리면 아래 reload() 의
    # `global` 목록을 같이 고쳐야 하는데, 그걸 빠뜨리면 테스트가 workspace.toml 을
    # 갈아끼워도 값이 안 따라온다(있는 척만 하는 설정). 전부 아래 형태로만 읽어라:
    #     settings.cfg("키", settings.DEFAULTS["키"])
    "mcp_min_interval": 0.26,      # 불사자 MCP 호출 최소 간격(초). ... 실측 = 초당 4회
    "index_excluded_groups": [],   # D-18 ... **빈 리스트 = 제외 없음** (전량 제외가 아니다)
```

> **Phase 4 키 제안(같은 블록 형식으로 `# ── Phase 4 (배너 판정) ──` 주석과 함께):**
> `banner_cache_dir` · `banner_thumb_dir` · `banner_workers`(8, 실측) · `vision_revision`(3) ·
> `banner_무내용_종횡비`(6.0) · `banner_무내용_짧은변px`(32) · `banner_스킵_잔여하한`(2) ·
> `banner_스킵_제거율상한`(0.5) · `banner_어휘군버전`("2026-09-21").
> **어휘군 문자열 목록 자체는 `banner_scan.py` 에 둔다**(설정 파일에 200개 문자열을 넣으면
> 회귀 픽스처와 버전이 어긋난다). 대신 `어휘군버전` 을 산출물에 싣는다(RESEARCH §산출물 계약).

### S-5. `ended_at` 으로 소요시간을 말하지 않는다

**Source:** `webapp/jobs.py:853-862` (`latest_done` 이 `_reap` 을 자기 안에서 부른다) +
`.planning/todos/pending/job-reap-depends-on-polling.md`

```python
def latest_done(kind: str, run_dir: str | None = None) -> dict | None:
    """그 종류의 **가장 최근 성공 잡** 1건. 없으면 None.
    ...
    `web/join_*.json` 을 glob 으로 뒤지지 마라 — 파일이 있다는 것과 그 잡이 성공했다는 것은
    다르다(중간에 죽은 잡도 반쯤 쓴 파일을 남긴다). 어느 잡이 성공했는지는 레지스트리가 정본이다.
    """
```

> 검수 화면 헤더의 "소요 4분 12초"는 **산출물 JSON 의 `소요초`** 를 읽는다.
> `jobs.ended_at` 은 "눈치챈 시각"이다(실측 60초 → 기록 2,421초).

### S-6. 사람 판단 큐를 만들지 않는다 (D-09 / `minimize-user-queues`)

**Source:** `webapp/join.py:36-48` 의 "사유코드는 서로 다른 값" + `routes/board.py:44-49`

```python
# 이름 자체가 버킷을 말하게 지었다 — **기호나 색에 기대지 않는다.**
#   `번호…`   로 시작하면 광고 쪽 오류 (사람이 네이버 광고에서 고친다)
#   `인덱스…` 로 시작하면 시스템 사정 (기계가 더 돌면 된다)
# 흑백 출력·색맹에서도 이 구분이 살아 있어야 한다. 이 화면이 존재하는 이유다.
```

> 스킵 상품은 **배지 + 사유 문자열**로 끝난다(D-09). "보류"·"대기"·"검토요청" 같은
> 상태값이나 엔드포인트를 만들지 마라 — VALIDATION §성공기준 3 이 grep 으로 집행한다.

---

## No Analog Found

| 파일 | 역할 | 데이터 흐름 | 사유 |
|---|---|---|---|
| `webapp/tests/test_ocr_determinism.py` | test (integration) | — | **`.venv` 로 도는 테스트가 저장소에 0건.** venv 이중 실행을 플래너가 새로 설계해야 한다 (위 §11 의 5개 항목) |

**부분 analog (조합 필요):**

| 파일 | 역할 | 조합할 analog | 사유 |
|---|---|---|---|
| 라벨 store (`webapp/banner_store.py` 또는 라우트 내장) | store | `bulsaja_index._ro_conn`(읽기) + `jobs._conn/init_db`(쓰기) + `bulsaja_index.db_path`(순환 회피) | 웹앱이 SQLite 에 **쓰는** 모듈의 선례가 `jobs.py`(잡 레지스트리) 하나뿐이다 |
| `banner_scan.py` 의 다운로드 층 | CLI network | 선례 없음 — `urllib.request` + `ThreadPoolExecutor` 는 이 저장소 첫 사용 | 기존 CLI 는 전부 MCP 클라이언트(`bulsaja_mcp`)를 통했다. RESEARCH §Standard Stack 의 stdlib 조합이 정본 |

---

## Metadata

**Analog search scope:** `webapp/` (13 모듈 · 3 라우트 · 7 템플릿 · 18 테스트) ·
`.claude/skills/bulsaja-detail-page/scripts/` (7 스크립트) ·
`.claude/skills/bulsaja-detail-remix/scripts/stitch.py`
**Files scanned:** 26 (실제 Read 한 파일 21 · grep 으로 위치만 확인 5)
**Pattern extraction date:** 2026-09-22
**Git ref:** `main` @ cda51d0

**플래너에게 남기는 미결 3건:**
1. 라벨 store 위치 — A안(`banner_store.py`) / B안(라우트 내장). 권고 A (§7)
2. `.venv` pytest 설치 여부 — Wave 0 에서 확인 필요 (§11)
3. `banner_scan.py` 의 "대상"을 무엇으로 넘길지 — 권고: 직전 성공 `bulsaja_scan` 의
   `result_path` 를 `--join` 으로. 없으면 409 (§5(e))
