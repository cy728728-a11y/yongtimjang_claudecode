# 네이버 사입 소싱 벤치마크 (naver-sourcing-bench) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 네이버 쇼핑에서 "리뷰 검증된 세부 카테고리 → 키워드 → 벤치마크 상품" 을 Aside 브라우저로 읽어 구글 시트(`카테고리스캔` / `후보` 탭)에 정리하는 스킬을 만든다.

**Architecture:** 파이썬 CLI(`sourcing_bench.py`) 가 서브커맨드(`init`/`login-check`/`scan`/`bench`/`annotate`)를 받는다. 네이버 화면 읽기는 Aside REPL 에 JS 드라이버를 넘겨 `__R__ {json}` 줄로 결과를 받는다(aside-category 의 `_run_repl` 재사용). 판정·행 조립은 순수 함수 모듈(`rules.py`, `sheet_schema.py`)로 분리해 pytest 로 검증하고, 시트 쓰기는 `gws` CLI 래퍼(`gws_sheet.py`)가 맡는다.

**Tech Stack:** Python 3.12 (`.venv/bin/python`), pytest (`.venv/bin/pytest`), Aside CLI (`~/.local/bin/aside repl`), gws CLI (`gws sheets ...`), 네이버 카테고리 마스터 JSON(`30-knowledge/39-naver-category/naver-category-master.json`).

**Spec:** `docs/superpowers/specs/2026-10-01-naver-sourcing-bench-design.md`

## Global Constraints

- 코드 주석 한국어, Python, 외부 호출(subprocess·파일·JSON 파싱)마다 try-except.
- 네이버 접근은 **Aside 브라우저만**. selenium·requests 로 네이버를 직접 치지 않는다.
- **네이버 로그인 게이트**: `scan`/`bench` 는 시작 시 Aside 의 네이버 로그인 상태를 확인하고, 안 돼 있으면 "Aside 창에서 네이버에 직접 로그인한 뒤 다시 실행" 을 안내하고 종료코드 3 으로 끝낸다. 아이디·비밀번호는 묻지도 받지도 저장하지도 않는다.
- 캡챠·차단 감지 시 남은 건을 두드리지 않고 즉시 중단(체크포인트 저장 후 종료코드 4).
- 필터 값: 스캔 = 리뷰 많은 순 상위 40개 중 **리뷰 ≥ 1000** 상품 수. 벤치 = 키워드 랭킹순 상위 40개(광고 제외) 중 **리뷰 ≥ 500 AND 판매가 ≥ 10,000원**.
- 환산: 위안 × **210** = 원화, × **1.4** = 추정 국내 원가. 일 판매량 = 180일 판매량 / **180**, 월 = 일 × **30**.
- 계산 기준 판매가 = **대표 옵션(최저 옵션가)**, 옵션이 없으면 검색 결과 가격.
- 시트는 누적. 상품 URL(정규화) 중복이면 행을 추가하지 않는다.
- 수동 칸: 11(180일 판매량), 15(1688 링크), 16(1688 위안). 옵션 수집 실패 시 9·10 도 수동(`상태=옵션수동`).

## Review Focus

1. 가격이 `"12,900원"`·`"12900"`·`None` 처럼 섞여 들어옴 → 숫자로 정규화, 없으면 그 상품은 벤치에서 제외(크래시 금지).
2. 리뷰수 필드 누락/`None`/문자열 → 0 으로 취급, 크래시 금지.
3. 같은 상품이 광고+일반으로 두 번, 또는 추적 파라미터만 다른 URL 로 나옴 → 1행만.
4. 카테고리가 3단에서 끝나는 리프(세부 없음) → 스캔 대상에 포함, 시트에는 세부 칸 빈칸.
5. 스캔 도중 캡챠 → 거기까지 저장, `--resume` 재실행 시 완료 카테고리를 다시 열지 않음.

---

## File Structure

모두 `.claude/skills/naver-sourcing-bench/` 아래.

| 파일 | 책임 |
|---|---|
| `SKILL.md` | 트리거·사용 순서·로그인 요청 문구·수동 입력 안내 |
| `scripts/rules.py` | 순수 함수: 숫자 정규화, URL 정규화, 리프 카테고리 추출, 스캔 집계, 벤치 필터, 대표가·옵션 문자열 |
| `scripts/sheet_schema.py` | 순수 함수: 탭 헤더, 행 조립(값 + 수식) |
| `scripts/gws_sheet.py` | gws CLI 래퍼: 스프레드시트 생성, 열 읽기, 행 추가, 셀 갱신 |
| `scripts/aside_bridge.py` | aside-category 의 `_run_repl`/청크 계산 재사용 + 드라이버 템플릿 로드 |
| `scripts/drivers/login.js` | 네이버 로그인 여부 판정 |
| `scripts/drivers/common.js` | 상태 판정·캡챠 정착 대기·상품 추출(공통 조각) |
| `scripts/drivers/scan.js` | 카테고리 페이지(리뷰 많은 순) 상품 목록 |
| `scripts/drivers/search.js` | 키워드 검색(랭킹순) 상품 목록 |
| `scripts/drivers/detail.js` | 스마트스토어 상세 옵션·옵션가 |
| `scripts/sourcing_bench.py` | CLI 진입점, 체크포인트 |
| `scripts/test_rules.py`, `scripts/test_sheet_schema.py`, `scripts/test_gws_sheet.py`, `scripts/test_cli.py` | pytest |
| `runs/` (gitignore) | 체크포인트 JSON, `config.json`(시트 ID) |

### 공용 데이터 형태 (모든 태스크가 이 이름을 쓴다)

드라이버가 내보내는 **상품 dict** (`__R__` 한 줄 = 한 페이지 결과):

```json
{"kind": "page", "key": "<카테고리코드 또는 키워드>", "상태": "성공|캡챠감지|차단감지|조회실패|파싱실패",
 "error": null,
 "products": [{"순위": 1, "상품명": "...", "url": "...", "마켓명": "...", "가격": "12,900",
               "리뷰수": 1532, "광고": false,
               "카테고리": ["생활/건강", "수납/정리", "압축봉", ""]}]}
```

상세 드라이버 결과: `{"kind": "detail", "key": "<url>", "상태": "...", "error": null, "options": [{"이름": "화이트/100cm", "가격": 12900}]}`

---

### Task 1: 스킬 뼈대 + 네이버 데이터 실측(spike) + 로그인 게이트

목적: 드라이버가 기대는 필드명이 실제로 있는지 먼저 확정한다. 이 태스크의 실측 결과가 Task 4 의 `EXTRACT` 상수를 결정한다.

**Files:**
- Create: `.claude/skills/naver-sourcing-bench/scripts/aside_bridge.py`
- Create: `.claude/skills/naver-sourcing-bench/scripts/drivers/login.js`
- Create: `.claude/skills/naver-sourcing-bench/scripts/drivers/probe.js` (실측용, 커밋은 하되 CLI 에선 안 씀)
- Create: `.claude/skills/naver-sourcing-bench/evidence/probe-2026-10.md`
- Modify: `.gitignore` (끝에 `.claude/skills/naver-sourcing-bench/runs/` 추가)

**Interfaces:**
- Produces: `aside_bridge.run_driver(name: str, items: list, opts: dict, timeout: int) -> list[dict]` — `drivers/common.js` + `drivers/<name>.js` 를 이어붙여 `__ITEMS__`/`__OPTS__` 치환 후 aside-category 의 `_run_repl` 로 실행, `__R__` 결과 리스트 반환.
- Produces: `aside_bridge.auto_chunk(count: int, sec_per_item: float, sleep_max: float) -> int`
- Produces: `aside_bridge.ASIDE_BIN: str`

- [ ] **Step 1: 사용자 로그인 요청**

사용자에게 그대로 보낸다: "Aside 브라우저를 열고 네이버에 직접 로그인해 줘. 끝나면 '로그인 했어' 라고 말해줘." 답을 받을 때까지 다음 단계로 가지 않는다.

- [ ] **Step 2: `aside_bridge.py` 작성**

```python
# -*- coding: utf-8 -*-
"""Aside REPL 실행 다리. aside-category 의 검증된 _run_repl 을 그대로 빌려 쓴다."""
import importlib.util
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DRIVERS = HERE / "drivers"
_AC_PATH = HERE.parents[1] / "aside-category" / "scripts" / "aside_category.py"

try:
    _spec = importlib.util.spec_from_file_location("aside_category", _AC_PATH)
    _ac = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_ac)
except (OSError, ImportError) as e:
    sys.exit(f"aside-category 스크립트를 불러오지 못했다: {_AC_PATH} ({e})")

ASIDE_BIN = _ac.ASIDE_BIN
REPL_WALL_SEC = _ac.REPL_WALL_SEC      # repl 호출당 ~120초 벽
CHUNK_MARGIN = _ac.CHUNK_MARGIN


def auto_chunk(count, sec_per_item, sleep_max):
    """120초 벽 아래로 들어가는 한 호출당 건수. 최소 1."""
    if count <= 0:
        return 1
    per = sec_per_item + (sleep_max or 0) / 2
    return max(1, min(count, int(REPL_WALL_SEC * CHUNK_MARGIN / per)))


def load_driver(name):
    """common.js + <name>.js 를 이어붙인 템플릿. common 이 없으면 단독 파일만."""
    try:
        body = (DRIVERS / f"{name}.js").read_text(encoding="utf-8")
        common = DRIVERS / "common.js"
        head = common.read_text(encoding="utf-8") if common.exists() and name not in ("login", "probe") else ""
    except OSError as e:
        raise RuntimeError(f"드라이버 파일 읽기 실패: {name} ({e})")
    return head + "\n" + body


def run_driver(name, items, opts, timeout):
    """드라이버 실행 → __R__ 결과 리스트. aside 가 없으면 RuntimeError."""
    if not os.path.exists(ASIDE_BIN):
        raise RuntimeError(f"aside CLI 없음: {ASIDE_BIN} (ASIDE_BIN 환경변수로 지정)")
    return _ac._run_repl(load_driver(name), items, opts, timeout)
```

- [ ] **Step 3: `drivers/login.js` 작성**

```javascript
// 네이버 로그인 여부 판정. ITEMS/OPTS 는 쓰지 않지만 치환 자리는 남긴다.
const ITEMS = __ITEMS__; const OPTS = __OPTS__;
await openTab("https://www.naver.com/");
await page.goto("https://www.naver.com/");
await sleep(2000);
const r = await page.evaluate(() => {
  const t = document.body.innerText || "";
  const out = !!document.querySelector('a[href*="nidlogin.logout"], a[href*="logout"]');
  const inBtn = !!document.querySelector('a[href*="nidlogin.login"], .link_login, a.MyView-module__link_login');
  return { loggedIn: out || (!inBtn && /로그아웃/.test(t)), hint: inBtn ? "로그인 버튼 보임" : "" };
});
console.log("__R__ " + JSON.stringify({ kind: "login", ...r }));
console.log("__DONE__");
```

- [ ] **Step 4: `drivers/probe.js` 작성 — 세 화면의 원본 데이터 구조 덤프**

```javascript
// 실측 전용. 검색·카테고리·상세 페이지의 내장 JSON 키 구조를 덤프한다.
const ITEMS = __ITEMS__; const OPTS = __OPTS__;
const keysOf = (o, d = 0) => (o && typeof o === "object" && d < 6)
  ? Object.fromEntries(Object.keys(o).slice(0, 40).map(k => [k, keysOf(o[k], d + 1)])) : typeof o;
await openTab("https://search.shopping.naver.com/");
for (const url of ITEMS) {
  await page.goto(url); await sleep(4000);
  const r = await page.evaluate(() => {
    const nd = document.querySelector("#__NEXT_DATA__");
    const pre = window.__PRELOADED_STATE__;
    return { href: location.href,
             next: nd ? JSON.parse(nd.textContent) : null,
             pre: pre ? JSON.parse(JSON.stringify(pre)) : null,
             text: (document.body.innerText || "").slice(0, 1500) };
  });
  // 첫 상품 하나만 통째로, 나머지는 키 구조만
  console.log("__R__ " + JSON.stringify({ kind: "probe", url, href: r.href,
    nextKeys: keysOf(r.next), preKeys: keysOf(r.pre), text: r.text,
    sample: JSON.stringify(r.next || r.pre).slice(0, 20000) }));
}
console.log("__DONE__");
```

- [ ] **Step 5: 로그인 확인 + 실측 실행**

```bash
cd /Users/choiyongsmacbook/Documents/yongtimjang_claudecode
D=.claude/skills/naver-sourcing-bench/scripts
.venv/bin/python -c "
import sys; sys.path.insert(0,'$D'); import aside_bridge as b, json
print(b.run_driver('login', [], {}, 60))
urls=['https://search.shopping.naver.com/search/all?query=%EC%95%95%EC%B6%95%EB%B4%89&sort=rel&pagingSize=40',
      'https://search.shopping.naver.com/search/category/100000837?sort=review&pagingSize=40']
json.dump(b.run_driver('probe', urls, {}, 110), open('/tmp/probe_list.json','w'), ensure_ascii=False)
"
```

Expected: login 결과 `loggedIn: true`. probe 2건 저장. (카테고리코드 `100000837` 이 없는 코드면 마스터에서 `last: true` 인 아무 코드로 바꾼다: `.venv/bin/python -c "import json;d=json.load(open('30-knowledge/39-naver-category/naver-category-master.json'));print([c for c in d['카테고리'] if c['last']][:3])"`)

이어서 probe 결과의 첫 스마트스토어 상품 URL 하나로 상세를 실측한다(같은 명령, urls 만 그 URL 로).

- [ ] **Step 6: 실측 결과 기록 — `evidence/probe-2026-10.md`**

아래 표를 실제 값으로 채운다(필드 경로는 덤프에서 찾은 그대로):

| 항목 | 검색 페이지 경로 | 카테고리 페이지 경로 | 상세 페이지 경로 |
|---|---|---|---|
| 상품 배열 | | | — |
| 상품명 / URL / 마켓명 / 가격 / 리뷰수 / 광고여부 | | | — |
| 카테고리 1~4 이름 | | | — |
| 리뷰 많은 순 정렬 파라미터 동작 여부 | — | | — |
| 옵션 배열 / 옵션명 / 옵션 추가금 / 기본 판매가 | — | — | |
| 로그인 판정 결과 | | | |

**분기:** (a) 리뷰수가 목록 데이터에 없으면 → 작업 중단하고 사용자에게 보고(설계 재검토). (b) 상세 옵션을 못 읽으면 → Task 6 은 건너뛰고 9·10 열 수동 확정(스펙 §6-3). (c) 정렬 파라미터가 `sort=review` 가 아니면 실제 값을 기록.

- [ ] **Step 7: 커밋**

```bash
printf '\n.claude/skills/naver-sourcing-bench/runs/\n' >> .gitignore
git add .gitignore .claude/skills/naver-sourcing-bench/scripts/aside_bridge.py \
  .claude/skills/naver-sourcing-bench/scripts/drivers/login.js \
  .claude/skills/naver-sourcing-bench/scripts/drivers/probe.js \
  .claude/skills/naver-sourcing-bench/evidence/probe-2026-10.md
git commit -m "feat(sourcing-bench): Aside 다리 + 로그인 판정 + 네이버 데이터 실측"
```

---

### Task 2: 순수 판정 규칙 `rules.py`

**Files:**
- Create: `.claude/skills/naver-sourcing-bench/scripts/rules.py`
- Test: `.claude/skills/naver-sourcing-bench/scripts/test_rules.py`

**Interfaces:**
- Produces:
  - `to_int(v) -> int | None` — `"12,900원"`→12900, `None`/`""`/비숫자→None
  - `norm_url(url: str) -> str` — 쿼리스트링·프래그먼트 제거, 스마트스토어는 `https://smartstore.naver.com/<store>/products/<id>` 형태로
  - `leaf_categories(master: dict, root_path: str) -> list[dict]` — `[{"코드","경로":[대,중,소,세부]}]`, 경로는 항상 4칸(모자라면 `""`)
  - `scan_summary(products: list[dict], min_review=1000) -> dict` — `{"리뷰1000+": int, "상위3": "a / b / c"}`
  - `bench_filter(products: list[dict], top_n=40, min_review=500, min_price=10000) -> list[dict]` — 광고 제외 → 순위 상위 40 → 필터 → URL 정규화 중복 제거, 원래 순위 순
  - `rep_price(options: list[dict], fallback: int | None) -> int | None` — 옵션 최저가, 없으면 fallback
  - `options_text(options: list[dict]) -> str` — `"화이트/100cm:12,900 / 블랙/100cm:13,900"`

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# -*- coding: utf-8 -*-
import rules


def test_to_int_variants():
    assert rules.to_int("12,900원") == 12900
    assert rules.to_int(12900) == 12900
    assert rules.to_int("12900") == 12900
    assert rules.to_int(None) is None
    assert rules.to_int("") is None
    assert rules.to_int("가격문의") is None


def test_norm_url_strips_tracking():
    a = rules.norm_url("https://smartstore.naver.com/abc/products/123?NaPm=ct%3Dx&nl-au=1#rev")
    b = rules.norm_url("https://smartstore.naver.com/abc/products/123")
    assert a == b == "https://smartstore.naver.com/abc/products/123"
    assert rules.norm_url("https://m.smartstore.naver.com/abc/products/123?x=1") == b


MASTER = {"카테고리": [
    {"id": "1", "last": False, "경로정규화": "생활/건강"},
    {"id": "2", "last": False, "경로정규화": "생활/건강 > 수납/정리"},
    {"id": "3", "last": True,  "경로정규화": "생활/건강 > 수납/정리 > 압축봉"},
    {"id": "4", "last": False, "경로정규화": "생활/건강 > 수납/정리 > 선반"},
    {"id": "5", "last": True,  "경로정규화": "생활/건강 > 수납/정리 > 선반 > 벽선반"},
    {"id": "6", "last": True,  "경로정규화": "생활/건강 > 수납/정리비슷 > 엉뚱"},
]}


def test_leaf_categories_includes_3level_leaf_and_pads():
    got = rules.leaf_categories(MASTER, "생활/건강>수납/정리")
    assert got == [
        {"코드": "3", "경로": ["생활/건강", "수납/정리", "압축봉", ""]},
        {"코드": "5", "경로": ["생활/건강", "수납/정리", "선반", "벽선반"]},
    ]


def test_leaf_categories_unknown_root_raises():
    import pytest
    with pytest.raises(ValueError):
        rules.leaf_categories(MASTER, "없는>경로")


def P(rank, name, review, price, ad=False, url=None):
    return {"순위": rank, "상품명": name, "리뷰수": review, "가격": price, "광고": ad,
            "url": url or f"https://smartstore.naver.com/s/products/{rank}", "마켓명": "s",
            "카테고리": ["a", "b", "c", "d"]}


def test_scan_summary_counts_and_handles_bad_review():
    ps = [P(1, "가", 3000, "10000"), P(2, "나", "1,200", "1"), P(3, "다", None, "1"), P(4, "라", 999, "1")]
    assert rules.scan_summary(ps) == {"리뷰1000+": 2, "상위3": "가 / 나 / 다"}


def test_bench_filter_rules_and_dedup():
    ps = [
        P(1, "광고", 9999, "20000", ad=True),
        P(2, "통과", 800, "15,000원"),
        P(3, "리뷰부족", 499, "15000"),
        P(4, "싸다", 900, "9,900"),
        P(5, "가격없음", 900, None),
        P(6, "중복", 700, "12000", url="https://smartstore.naver.com/s/products/2?NaPm=1"),
        P(7, "경계", 500, "10000"),
    ]
    got = [p["상품명"] for p in rules.bench_filter(ps)]
    assert got == ["통과", "경계"]


def test_bench_filter_top_n_after_ads_removed():
    ps = [P(i, f"p{i}", 600, "20000") for i in range(1, 51)]
    assert len(rules.bench_filter(ps, top_n=40)) == 40


def test_rep_price_and_options_text():
    opts = [{"이름": "흰", "가격": 13900}, {"이름": "검", "가격": 12900}]
    assert rules.rep_price(opts, 15000) == 12900
    assert rules.rep_price([], 15000) == 15000
    assert rules.options_text(opts) == "흰:13,900 / 검:12,900"
    assert rules.options_text([]) == ""
```

- [ ] **Step 2: 실패 확인**

Run: `cd .claude/skills/naver-sourcing-bench/scripts && ../../../../.venv/bin/pytest test_rules.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rules'`

- [ ] **Step 3: 구현**

```python
# -*- coding: utf-8 -*-
"""소싱 벤치마크 판정 규칙. 네트워크·파일 접근 없는 순수 함수만 둔다."""
import re
from urllib.parse import urlsplit


def to_int(v):
    """'12,900원' / 12900 / '12900' → 12900. 숫자가 없으면 None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    digits = re.sub(r"[^\d]", "", str(v))
    return int(digits) if digits else None


def norm_url(url):
    """추적 파라미터를 떼어 같은 상품이면 같은 문자열이 되게 한다."""
    try:
        s = urlsplit(str(url).strip())
    except ValueError:
        return str(url).strip()
    host = s.netloc.lower()
    if host.startswith("m.smartstore."):
        host = host[2:]
    return f"https://{host}{s.path.rstrip('/')}"


def _split(path):
    return [p.strip() for p in str(path).split(">") if p.strip()]


def leaf_categories(master, root_path):
    """root_path(대 또는 대>중) 하위의 리프 카테고리. 경로는 4칸으로 맞춘다."""
    root = _split(root_path)
    rows = master.get("카테고리", [])
    if not any(_split(c.get("경로정규화", "")) == root for c in rows):
        raise ValueError(f"카테고리 마스터에 없는 경로: {root_path}")
    out = []
    for c in rows:
        parts = _split(c.get("경로정규화", ""))
        if c.get("last") and parts[:len(root)] == root and len(parts) > len(root):
            out.append({"코드": str(c.get("id")), "경로": (parts + ["", "", "", ""])[:4]})
    return out


def _review(p):
    return to_int(p.get("리뷰수")) or 0


def scan_summary(products, min_review=1000):
    """리뷰 많은 순 목록에서 기준 이상 상품 수와 상위 3개 이름."""
    n = sum(1 for p in products if _review(p) >= min_review)
    top3 = " / ".join(str(p.get("상품명", "")) for p in products[:3])
    return {"리뷰1000+": n, "상위3": top3}


def bench_filter(products, top_n=40, min_review=500, min_price=10000):
    """광고 제외 → 순위 상위 top_n → 리뷰·가격 필터 → URL 중복 제거."""
    organic = sorted((p for p in products if not p.get("광고")), key=lambda p: p.get("순위") or 0)[:top_n]
    seen, out = set(), []
    for p in organic:
        price = to_int(p.get("가격"))
        if price is None or price < min_price or _review(p) < min_review:
            continue
        key = norm_url(p.get("url", ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def rep_price(options, fallback):
    """대표 판매가 = 옵션 최저가. 옵션이 없으면 fallback."""
    prices = [to_int(o.get("가격")) for o in options or []]
    prices = [x for x in prices if x]
    return min(prices) if prices else fallback


def options_text(options):
    return " / ".join(f"{o.get('이름', '')}:{to_int(o.get('가격')) or 0:,}" for o in options or [])
```

- [ ] **Step 4: 통과 확인**

Run: `cd .claude/skills/naver-sourcing-bench/scripts && ../../../../.venv/bin/pytest test_rules.py -v`
Expected: 8 passed

- [ ] **Step 5: 커밋**

```bash
git add .claude/skills/naver-sourcing-bench/scripts/rules.py .claude/skills/naver-sourcing-bench/scripts/test_rules.py
git commit -m "feat(sourcing-bench): 스캔·벤치 판정 규칙"
```

---

### Task 3: 시트 스키마와 행 조립 `sheet_schema.py`

**Files:**
- Create: `.claude/skills/naver-sourcing-bench/scripts/sheet_schema.py`
- Test: `.claude/skills/naver-sourcing-bench/scripts/test_sheet_schema.py`

**Interfaces:**
- Consumes: `rules.rep_price`, `rules.options_text`, `rules.to_int`, `rules.norm_url`
- Produces:
  - `SCAN_TAB = "카테고리스캔"`, `BENCH_TAB = "후보"`
  - `SCAN_HEADER: list[str]` (13열, 마지막 `벤치완료`), `BENCH_HEADER: list[str]` (24열)
  - `scan_row(date: str, cat: dict, summary: dict) -> list` — cat 은 `rules.leaf_categories` 원소
  - `bench_row(date: str, keyword: str, product: dict, options: list | None) -> list` — 24칸, 수식 포함
  - `SCAN_COL = {"키워드": 8, "검색량": 9, "경쟁도": 10, "벤치완료": 12}` (0-based)

열 배치(1-based, A..X): 1~20 = 스펙 20열, 21 U `대표판매가`, 22 V `수집일`, 23 W `리뷰수`, 24 X `상태`.
수식은 행 번호에 묶이지 않게 `INDEX(열:열,ROW())` 로 쓴다(append 위치를 몰라도 맞는다).

- [ ] **Step 1: 실패하는 테스트**

```python
# -*- coding: utf-8 -*-
import sheet_schema as S

PROD = {"순위": 1, "상품명": "압축봉 120cm", "url": "https://smartstore.naver.com/s/products/9?NaPm=1",
        "마켓명": "가나상점", "가격": "15,000", "리뷰수": 812, "광고": False,
        "카테고리": ["생활/건강", "수납/정리", "압축봉", ""]}


def test_headers():
    assert len(S.BENCH_HEADER) == 24
    assert S.BENCH_HEADER[:5] == ["대카테고리", "중카테고리", "소카테고리", "세부카테고리", "키워드"]
    assert S.BENCH_HEADER[10] == "180일 판매수량"
    assert S.BENCH_HEADER[20:] == ["대표판매가", "수집일", "리뷰수", "상태"]
    assert S.SCAN_HEADER[S.SCAN_COL["키워드"]] == "키워드"
    assert S.SCAN_HEADER[S.SCAN_COL["벤치완료"]] == "벤치완료"


def test_bench_row_with_options():
    opts = [{"이름": "흰", "가격": 13900}, {"이름": "검", "가격": 12900}]
    r = S.bench_row("2026-10-02", "압축봉", PROD, opts)
    assert len(r) == 24
    assert r[:9] == ["생활/건강", "수납/정리", "압축봉", "", "압축봉", "가나상점",
                     "https://smartstore.naver.com/s/products/9", "압축봉 120cm", 2]
    assert r[9] == "흰:13,900 / 검:12,900"
    assert r[10] == "" and r[14] == "" and r[15] == ""        # 수동 칸
    assert r[11] == '=IF(INDEX(K:K,ROW())="","",INDEX(K:K,ROW())/180)'
    assert r[12] == '=IF(INDEX(L:L,ROW())="","",INDEX(L:L,ROW())*INDEX(U:U,ROW()))'
    assert r[13] == '=IF(INDEX(M:M,ROW())="","",INDEX(M:M,ROW())*30)'
    assert r[16] == '=IF(INDEX(P:P,ROW())="","",INDEX(P:P,ROW())*210)'
    assert r[17] == '=IF(INDEX(Q:Q,ROW())="","",INDEX(Q:Q,ROW())*1.4)'
    assert r[18] == '=IF(INDEX(R:R,ROW())="","",INDEX(U:U,ROW())-INDEX(R:R,ROW()))'
    assert r[19] == '=IF(OR(INDEX(L:L,ROW())="",INDEX(S:S,ROW())=""),"",INDEX(L:L,ROW())*30*INDEX(S:S,ROW()))'
    assert r[20:] == [12900, "2026-10-02", 812, ""]


def test_bench_row_options_failed_marks_manual():
    r = S.bench_row("2026-10-02", "압축봉", PROD, None)
    assert r[8] == "" and r[9] == ""
    assert r[20] == 15000          # 검색 가격으로 대체
    assert r[23] == "옵션수동"


def test_scan_row():
    cat = {"코드": "3", "경로": ["생활/건강", "수납/정리", "압축봉", ""]}
    r = S.scan_row("2026-10-02", cat, {"리뷰1000+": 4, "상위3": "a / b / c"})
    assert r == ["2026-10-02", "생활/건강", "수납/정리", "압축봉", "", "3", 4, "a / b / c", "", "", "", "", ""]
```

- [ ] **Step 2: 실패 확인**

Run: `cd .claude/skills/naver-sourcing-bench/scripts && ../../../../.venv/bin/pytest test_sheet_schema.py -v`
Expected: FAIL — `No module named 'sheet_schema'`

- [ ] **Step 3: 구현**

```python
# -*- coding: utf-8 -*-
"""시트 탭 구조와 행 조립. 수식 열은 값이 아니라 수식 문자열로 넣는다."""
import rules

SCAN_TAB = "카테고리스캔"
BENCH_TAB = "후보"

SCAN_HEADER = ["스캔일", "대", "중", "소", "세부", "카테고리코드", "리뷰1000+ 상품수", "상위 상품명 3개",
               "키워드", "검색량(참고)", "경쟁도(참고)", "상태", "벤치완료"]
SCAN_COL = {"키워드": 8, "검색량": 9, "경쟁도": 10, "벤치완료": 12}

BENCH_HEADER = ["대카테고리", "중카테고리", "소카테고리", "세부카테고리", "키워드", "마켓명", "상품 URL",
                "상품명", "옵션 개수", "각 옵션 가격", "180일 판매수량", "일 예상판매량", "일 예상매출",
                "월 예상매출", "1688 이미지검색 링크", "1688 위안가격", "원화환산(×210)",
                "추정 국내원가(×1.4)", "1개당 예상마진", "월 예상마진",
                "대표판매가", "수집일", "리뷰수", "상태"]


def _c(col):
    """현재 행의 해당 열 참조."""
    return f"INDEX({col}:{col},ROW())"


FORMULAS = {
    11: f'=IF({_c("K")}="","",{_c("K")}/180)',
    12: f'=IF({_c("L")}="","",{_c("L")}*{_c("U")})',
    13: f'=IF({_c("M")}="","",{_c("M")}*30)',
    16: f'=IF({_c("P")}="","",{_c("P")}*210)',
    17: f'=IF({_c("Q")}="","",{_c("Q")}*1.4)',
    18: f'=IF({_c("R")}="","",{_c("U")}-{_c("R")})',
    19: f'=IF(OR({_c("L")}="",{_c("S")}=""),"",{_c("L")}*30*{_c("S")})',
}


def scan_row(date, cat, summary):
    return [date, *cat["경로"], cat["코드"], summary["리뷰1000+"], summary["상위3"], "", "", "", "", ""]


def bench_row(date, keyword, product, options):
    """options=None 이면 옵션 수집 실패 → 9·10열 비우고 상태=옵션수동."""
    cats = (list(product.get("카테고리") or []) + ["", "", "", ""])[:4]
    fallback = rules.to_int(product.get("가격"))
    ok = options is not None
    row = [*cats, keyword, product.get("마켓명", ""), rules.norm_url(product.get("url", "")),
           product.get("상품명", ""),
           len(options) if ok else "", rules.options_text(options) if ok else "",
           "", "", "", "", "", "", "", "", "", ""]
    for idx, f in FORMULAS.items():
        row[idx] = f
    row += [rules.rep_price(options or [], fallback), date,
            rules.to_int(product.get("리뷰수")) or 0, "" if ok else "옵션수동"]
    return row
```

- [ ] **Step 4: 통과 확인**

Run: `cd .claude/skills/naver-sourcing-bench/scripts && ../../../../.venv/bin/pytest test_sheet_schema.py test_rules.py -v`
Expected: 12 passed

- [ ] **Step 5: 커밋**

```bash
git add .claude/skills/naver-sourcing-bench/scripts/sheet_schema.py .claude/skills/naver-sourcing-bench/scripts/test_sheet_schema.py
git commit -m "feat(sourcing-bench): 시트 스키마·수식 행 조립"
```

---

### Task 4: gws 시트 래퍼 `gws_sheet.py`

**Files:**
- Create: `.claude/skills/naver-sourcing-bench/scripts/gws_sheet.py`
- Test: `.claude/skills/naver-sourcing-bench/scripts/test_gws_sheet.py`

**Interfaces:**
- Consumes: `sheet_schema.SCAN_TAB/BENCH_TAB/SCAN_HEADER/BENCH_HEADER`
- Produces: 클래스 `Sheet(spreadsheet_id: str, runner=None)` — runner 는 `(argv: list[str]) -> dict` (테스트 주입용, 기본은 gws subprocess)
  - `Sheet.create(title: str, runner=None) -> "Sheet"` (classmethod) — 두 탭 생성 + 헤더 기록
  - `.read(tab: str) -> list[list[str]]` — 헤더 제외 전체 행
  - `.append(tab: str, rows: list[list]) -> int` — `USER_ENTERED`, 추가 행 수
  - `.set_cell(tab: str, row_index: int, col_index: int, value) -> None` — 0-based, row_index 는 헤더 제외 데이터 행 기준
  - `GwsError(Exception)`

- [ ] **Step 1: 실패하는 테스트 (가짜 runner 로 argv 검증)**

```python
# -*- coding: utf-8 -*-
import json
import pytest
import gws_sheet as G


class Fake:
    def __init__(self, replies):
        self.calls, self.replies = [], list(replies)

    def __call__(self, argv):
        self.calls.append(argv)
        return self.replies.pop(0)


def _params(argv):
    return json.loads(argv[argv.index("--params") + 1])


def test_read_skips_header():
    f = Fake([{"values": [["h1", "h2"], ["a", "b"], ["c"]]}])
    rows = G.Sheet("SID", runner=f).read("후보")
    assert rows == [["a", "b"], ["c"]]
    assert f.calls[0][:4] == ["sheets", "spreadsheets", "values", "get"]
    assert _params(f.calls[0]) == {"spreadsheetId": "SID", "range": "후보!A:X"}


def test_read_empty_tab():
    assert G.Sheet("SID", runner=Fake([{}])).read("후보") == []


def test_append_user_entered():
    f = Fake([{"updates": {"updatedRows": 2}}])
    n = G.Sheet("SID", runner=f).append("후보", [["a"], ["=1+1"]])
    assert n == 2
    p = _params(f.calls[0])
    assert p["valueInputOption"] == "USER_ENTERED" and p["range"] == "후보!A1"
    assert json.loads(f.calls[0][f.calls[0].index("--json") + 1]) == {"values": [["a"], ["=1+1"]]}


def test_append_nothing_makes_no_call():
    f = Fake([])
    assert G.Sheet("SID", runner=f).append("후보", []) == 0 and f.calls == []


def test_set_cell_a1():
    f = Fake([{"updatedCells": 1}])
    G.Sheet("SID", runner=f).set_cell("카테고리스캔", 0, 12, "Y")
    assert _params(f.calls[0])["range"] == "카테고리스캔!M2"


def test_error_reply_raises():
    with pytest.raises(G.GwsError):
        G.Sheet("SID", runner=Fake([{"error": {"code": 403, "message": "x"}}])).read("후보")
```

- [ ] **Step 2: 실패 확인**

Run: `cd .claude/skills/naver-sourcing-bench/scripts && ../../../../.venv/bin/pytest test_gws_sheet.py -v`
Expected: FAIL — `No module named 'gws_sheet'`

- [ ] **Step 3: 구현**

```python
# -*- coding: utf-8 -*-
"""gws CLI 로 구글 시트를 읽고 쓴다. JSON 은 셸 치환 없이 argv 로 넘긴다."""
import json
import shutil
import subprocess

import sheet_schema as S


class GwsError(Exception):
    pass


def _gws_runner(argv):
    """실제 gws 호출. 결과 JSON dict 를 돌려준다."""
    gws = shutil.which("gws")
    if not gws:
        raise GwsError("gws CLI 를 찾지 못했다")
    try:
        r = subprocess.run([gws, *argv, "--format", "json"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise GwsError(f"gws 실행 실패: {e}")
    try:
        return json.loads(r.stdout or "{}")
    except ValueError:
        raise GwsError(f"gws 응답 파싱 실패: {(r.stdout + r.stderr)[-300:]}")


def _col(i):
    """0-based 열 번호 → A1 열 문자."""
    s = ""
    i += 1
    while i:
        i, rem = divmod(i - 1, 26)
        s = chr(65 + rem) + s
    return s


class Sheet:
    def __init__(self, spreadsheet_id, runner=None):
        self.sid = spreadsheet_id
        self.run = runner or _gws_runner

    def _call(self, argv):
        out = self.run(argv)
        if isinstance(out, dict) and out.get("error"):
            raise GwsError(f"gws 오류: {out['error']}")
        return out

    @classmethod
    def create(cls, title, runner=None):
        run = runner or _gws_runner
        body = {"properties": {"title": title},
                "sheets": [{"properties": {"title": S.SCAN_TAB}}, {"properties": {"title": S.BENCH_TAB}}]}
        out = run(["sheets", "spreadsheets", "create", "--json", json.dumps(body, ensure_ascii=False)])
        if not isinstance(out, dict) or not out.get("spreadsheetId"):
            raise GwsError(f"스프레드시트 생성 실패: {out}")
        sh = cls(out["spreadsheetId"], runner=run)
        sh.append(S.SCAN_TAB, [S.SCAN_HEADER])
        sh.append(S.BENCH_TAB, [S.BENCH_HEADER])
        return sh

    def read(self, tab):
        p = {"spreadsheetId": self.sid, "range": f"{tab}!A:X"}
        out = self._call(["sheets", "spreadsheets", "values", "get", "--params", json.dumps(p, ensure_ascii=False)])
        return (out.get("values") or [])[1:]

    def append(self, tab, rows):
        if not rows:
            return 0
        p = {"spreadsheetId": self.sid, "range": f"{tab}!A1",
             "valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"}
        out = self._call(["sheets", "spreadsheets", "values", "append",
                          "--params", json.dumps(p, ensure_ascii=False),
                          "--json", json.dumps({"values": rows}, ensure_ascii=False)])
        return int((out.get("updates") or {}).get("updatedRows", 0))

    def set_cell(self, tab, row_index, col_index, value):
        rng = f"{tab}!{_col(col_index)}{row_index + 2}"
        p = {"spreadsheetId": self.sid, "range": rng, "valueInputOption": "USER_ENTERED"}
        self._call(["sheets", "spreadsheets", "values", "update",
                    "--params", json.dumps(p, ensure_ascii=False),
                    "--json", json.dumps({"values": [[value]]}, ensure_ascii=False)])
```

- [ ] **Step 4: 통과 확인**

Run: `cd .claude/skills/naver-sourcing-bench/scripts && ../../../../.venv/bin/pytest test_gws_sheet.py -v`
Expected: 6 passed

- [ ] **Step 5: 커밋**

```bash
git add .claude/skills/naver-sourcing-bench/scripts/gws_sheet.py .claude/skills/naver-sourcing-bench/scripts/test_gws_sheet.py
git commit -m "feat(sourcing-bench): gws 시트 래퍼"
```

---

### Task 5: 목록 드라이버 `common.js` / `scan.js` / `search.js`

Task 1 실측표의 경로를 `EXTRACT` 에 반영한다. 아래 코드는 네이버 쇼핑 `__NEXT_DATA__` 의 알려진 구조(`props.pageProps.initialState.products.list[].item`) 기준이며, 실측표와 다르면 **`EXTRACT` 함수 안의 경로만** 실측값으로 바꾼다.

**Files:**
- Create: `.claude/skills/naver-sourcing-bench/scripts/drivers/common.js`
- Create: `.claude/skills/naver-sourcing-bench/scripts/drivers/scan.js`
- Create: `.claude/skills/naver-sourcing-bench/scripts/drivers/search.js`

**Interfaces:**
- Consumes: `aside_bridge.run_driver`
- Produces: `run_driver("scan", [{"코드": "..."}], opts, t)` / `run_driver("search", [{"키워드": "..."}], opts, t)` → `kind:"page"` dict 리스트 (위 "공용 데이터 형태"). opts = `{"sleep": float, "sleepMax": float}`

- [ ] **Step 1: `common.js`**

```javascript
// 공통 조각 — scan/search/detail 앞에 이어붙는다.
const ITEMS = __ITEMS__;
const OPTS = __OPTS__;
const CAPTCHA_SETTLE_TRIES = 5;   // aside-category 실측: 캡챠 화면이 5초 안에 스스로 풀리기도 한다
const CAPTCHA_SETTLE_MS = 2000;
const rand = (a, b) => a + Math.random() * (b - a);
const emit = (r) => console.log("__R__ " + JSON.stringify(r));

const PAGESTATE = () => {
  const t = document.body.innerText || "";
  if (/자동입력 방지|보안문자|캡차|captcha|보안 확인을 완료/i.test(t) || /captcha/i.test(location.href)) return "캡챠";
  if (document.querySelector('img[src*="captcha" i], input[id*="captcha" i], input[name*="captcha" i]')) return "캡챠";
  if (/일시적으로 제한|접속이 제한|비정상적인 접근|비정상적인 검색/.test(t)) return "차단";
  if (/검색결과가 없습니다|검색 결과가 없습니다|일치하는 상품이 없습니다/.test(t)) return "없음";
  return "정상";
};

// goto 후 캡챠 정착까지 기다린 최종 상태
async function settle(url) {
  await page.goto(url);
  await sleep(1500);
  let st = await page.evaluate(PAGESTATE);
  for (let k = 0; st === "캡챠" && k < CAPTCHA_SETTLE_TRIES; k++) {
    await sleep(CAPTCHA_SETTLE_MS);
    st = await page.evaluate(PAGESTATE);
  }
  return st;
}

// 목록 페이지 → 공용 상품 dict 배열. 경로는 Task 1 실측표 기준.
const EXTRACT = () => {
  const nd = document.querySelector("#__NEXT_DATA__");
  if (!nd) return null;
  const root = JSON.parse(nd.textContent);
  const list = (((root.props || {}).pageProps || {}).initialState || {}).products?.list || [];
  return list.map((x, i) => {
    const it = x.item || x;
    return {
      순위: it.rank || i + 1,
      상품명: it.productTitle || it.productName || "",
      url: it.mallProductUrl || it.crUrl || it.adcrUrl || "",
      마켓명: it.mallName || "",
      가격: it.price || it.lowPrice || null,
      리뷰수: it.reviewCount ?? it.reviewCountSum ?? null,
      광고: !!(it.adId || x.adId || /adcr/.test(it.adcrUrl || "")),
      카테고리: [it.category1Name || "", it.category2Name || "", it.category3Name || "", it.category4Name || ""],
    };
  });
};

// 한 페이지 읽기. 캡챠/차단이면 true 를 돌려 호출부가 중단하게 한다.
async function readList(key, url) {
  const r = { kind: "page", key, 상태: null, error: null, products: [] };
  try {
    const st = await settle(url);
    if (st === "캡챠" || st === "차단") {
      r.상태 = st === "캡챠" ? "캡챠감지" : "차단감지";
      r.error = "Aside 창에서 직접 확인 필요";
      emit(r); return true;
    }
    if (st === "없음") { r.상태 = "조회실패"; r.error = "결과 없음"; emit(r); return false; }
    const ps = await page.evaluate(EXTRACT);
    if (!ps || !ps.length) { r.상태 = "파싱실패"; r.error = "상품 목록 데이터 없음"; emit(r); return false; }
    r.상태 = "성공"; r.products = ps; emit(r);
  } catch (e) {
    r.상태 = "파싱실패"; r.error = String(e && e.message ? e.message : e); emit(r);
  }
  return false;
}
```

- [ ] **Step 2: `scan.js`**

```javascript
// 세부 카테고리 페이지를 리뷰 많은 순으로 연다 (정렬 파라미터는 Task 1 실측값).
await openTab("https://search.shopping.naver.com/");
for (let i = 0; i < ITEMS.length; i++) {
  const code = ITEMS[i].코드;
  const url = `https://search.shopping.naver.com/search/category/${code}?sort=review&pagingSize=40`;
  const stop = await readList(code, url);
  console.log(`[${i + 1}/${ITEMS.length}] ${code}`);
  if (stop) { console.log(`  ↳ 중단 (남은 ${ITEMS.length - i - 1}건)`); break; }
  if (i < ITEMS.length - 1) await sleep(rand(OPTS.sleep, OPTS.sleepMax) * 1000);
}
console.log("__DONE__");
```

- [ ] **Step 3: `search.js`**

```javascript
// 키워드 검색 랭킹순 상위 40.
await openTab("https://search.shopping.naver.com/");
for (let i = 0; i < ITEMS.length; i++) {
  const kw = ITEMS[i].키워드;
  const url = "https://search.shopping.naver.com/search/all?query=" + encodeURIComponent(kw) + "&sort=rel&pagingSize=40";
  const stop = await readList(kw, url);
  console.log(`[${i + 1}/${ITEMS.length}] ${kw}`);
  if (stop) break;
  if (i < ITEMS.length - 1) await sleep(rand(OPTS.sleep, OPTS.sleepMax) * 1000);
}
console.log("__DONE__");
```

- [ ] **Step 4: 실물 확인 (로그인 상태 전제)**

```bash
D=.claude/skills/naver-sourcing-bench/scripts
.venv/bin/python -c "
import sys,json; sys.path.insert(0,'$D'); import aside_bridge as b, rules
r=b.run_driver('search',[{'키워드':'압축봉'}],{'sleep':2,'sleepMax':5},110)
ps=r[0]['products']; print(r[0]['상태'], len(ps)); print(json.dumps(ps[:2],ensure_ascii=False,indent=1))
print('벤치통과', len(rules.bench_filter(ps)))
"
```

Expected: `성공 40` 안팎, 상품 2건에 상품명·url·마켓명·가격·리뷰수(숫자)·카테고리 1~3 이상이 채워짐. 비어 있는 필드가 있으면 `EXTRACT` 경로를 실측표대로 고친 뒤 재실행. 같은 방식으로 `scan` 을 리프 코드 1개로 확인(리뷰수가 내림차순인지 눈으로 확인).

- [ ] **Step 5: 커밋**

```bash
git add .claude/skills/naver-sourcing-bench/scripts/drivers/common.js .claude/skills/naver-sourcing-bench/scripts/drivers/scan.js .claude/skills/naver-sourcing-bench/scripts/drivers/search.js
git commit -m "feat(sourcing-bench): 카테고리·검색 목록 드라이버"
```

---

### Task 6: 상세 옵션 드라이버 `detail.js`

Task 1 실측 분기 (b) 에서 "상세 옵션 못 읽음" 이면 이 태스크는 **건너뛰고**, Task 7 에서 `options=None` 고정(전 행 `옵션수동`)으로 간다.

**Files:**
- Create: `.claude/skills/naver-sourcing-bench/scripts/drivers/detail.js`

**Interfaces:**
- Produces: `run_driver("detail", [{"url": "..."}], opts, t)` → `kind:"detail"` dict 리스트. 스마트스토어가 아닌 URL 은 `상태:"대상아님"`, `options: null`.

- [ ] **Step 1: 구현**

```javascript
// 스마트스토어 상세의 옵션 조합과 옵션가. 경로는 Task 1 실측표 기준.
const DETAIL = () => {
  const st = window.__PRELOADED_STATE__;
  const p = st && (st.simpleProductForDetailPage?.A || st.product?.A);
  if (!p) return null;
  const base = p.benefitsView?.discountedSalePrice ?? p.salePrice ?? null;
  const combos = p.optionCombinations || [];
  if (!combos.length) return { base, options: [] };
  return { base, options: combos
    .filter(c => c.usable !== false && (c.stockQuantity ?? 1) > 0)
    .map(c => ({ 이름: [c.optionName1, c.optionName2, c.optionName3].filter(Boolean).join("/"),
                 가격: (base || 0) + (c.price || 0) })) };
};
await openTab("https://smartstore.naver.com/");
for (let i = 0; i < ITEMS.length; i++) {
  const url = ITEMS[i].url;
  const r = { kind: "detail", key: url, 상태: null, error: null, options: null };
  if (!/smartstore\.naver\.com|brand\.naver\.com/.test(url)) { r.상태 = "대상아님"; emit(r); continue; }
  try {
    const st = await settle(url);
    if (st === "캡챠" || st === "차단") { r.상태 = st === "캡챠" ? "캡챠감지" : "차단감지"; emit(r); break; }
    const d = await page.evaluate(DETAIL);
    if (!d) { r.상태 = "파싱실패"; r.error = "상세 데이터 없음"; }
    else { r.상태 = "성공"; r.options = d.options.length ? d.options : [{ 이름: "단일", 가격: d.base }]; }
  } catch (e) { r.상태 = "파싱실패"; r.error = String(e && e.message ? e.message : e); }
  emit(r);
  if (i < ITEMS.length - 1) await sleep(rand(OPTS.sleep, OPTS.sleepMax) * 1000);
}
console.log("__DONE__");
```

- [ ] **Step 2: 실물 확인**

Task 5 Step 4 에서 나온 스마트스토어 URL 2개로:

```bash
D=.claude/skills/naver-sourcing-bench/scripts
.venv/bin/python -c "
import sys,json; sys.path.insert(0,'$D'); import aside_bridge as b
print(json.dumps(b.run_driver('detail',[{'url':'<URL1>'},{'url':'<URL2>'}],{'sleep':3,'sleepMax':6},110),ensure_ascii=False,indent=1))"
```

Expected: `성공` 과 옵션 이름·가격 목록. 사용자가 자기 브라우저에서 같은 상품의 옵션가와 맞는지 대조해 준다(네이버 화면 확인은 사용자 몫).

- [ ] **Step 3: 커밋**

```bash
git add .claude/skills/naver-sourcing-bench/scripts/drivers/detail.js
git commit -m "feat(sourcing-bench): 스마트스토어 옵션 드라이버"
```

---

### Task 7: CLI `sourcing_bench.py` (init / login-check / scan / bench / annotate)

**Files:**
- Create: `.claude/skills/naver-sourcing-bench/scripts/sourcing_bench.py`
- Test: `.claude/skills/naver-sourcing-bench/scripts/test_cli.py`

**Interfaces:**
- Consumes: `aside_bridge.run_driver/auto_chunk`, `rules.*`, `sheet_schema.*`, `gws_sheet.Sheet`
- Produces (테스트가 부르는 내부 함수):
  - `require_login(run=aside_bridge.run_driver) -> None` — 미로그인이면 안내 출력 후 `SystemExit(3)`
  - `do_scan(sheet, master, root_path, ckpt_path, run, date, opts) -> int` — 추가한 스캔 행 수. 캡챠면 `SystemExit(4)`
  - `do_bench(sheet, keyword, ckpt_path, run, date, opts, with_options=True) -> int` — 추가한 후보 행 수
  - `bench_from_scan(sheet, ckpt_dir, run, date, opts, with_options=True) -> int`
- 종료코드: 0 정상, 2 입력 오류, 3 로그인 필요, 4 캡챠/차단 중단.
- 체크포인트: `runs/scan-<root 슬러그>.json` = `{"done": {"<코드>": <page dict>}}`, `runs/bench-<키워드>.json` = `{"page": <page dict>|null, "details": {"<url>": <detail dict>}}`
- 설정: `runs/config.json` = `{"sheet_id": "..."}` (`init` 이 쓴다, `--sheet` 가 우선)

- [ ] **Step 1: 실패하는 테스트 (가짜 run·가짜 sheet)**

```python
# -*- coding: utf-8 -*-
import json
import pytest
import sourcing_bench as C
import sheet_schema as S


class FakeSheet:
    def __init__(self, scan_rows=None, bench_rows=None):
        self.tabs = {S.SCAN_TAB: scan_rows or [], S.BENCH_TAB: bench_rows or []}
        self.cells = []

    def read(self, tab):
        return [list(r) for r in self.tabs[tab]]

    def append(self, tab, rows):
        self.tabs[tab] += rows
        return len(rows)

    def set_cell(self, tab, r, c, v):
        self.cells.append((tab, r, c, v))


def prod(rank, review, price="15,000", url=None):
    return {"순위": rank, "상품명": f"p{rank}", "url": url or f"https://smartstore.naver.com/s/products/{rank}",
            "마켓명": "s", "가격": price, "리뷰수": review, "광고": False, "카테고리": ["a", "b", "c", "d"]}


MASTER = {"카테고리": [
    {"id": "2", "last": False, "경로정규화": "A > B"},
    {"id": "10", "last": True, "경로정규화": "A > B > C1"},
    {"id": "11", "last": True, "경로정규화": "A > B > C2"},
]}
OPTS = {"sleep": 0, "sleepMax": 0}


def test_require_login_blocks():
    with pytest.raises(SystemExit) as e:
        C.require_login(run=lambda *a: [{"kind": "login", "loggedIn": False}])
    assert e.value.code == 3


def test_require_login_passes():
    C.require_login(run=lambda *a: [{"kind": "login", "loggedIn": True}])


def test_scan_sorted_desc_and_checkpoint(tmp_path):
    pages = {"10": [prod(1, 1500)], "11": [prod(1, 2000), prod(2, 1200)]}
    calls = []

    def run(name, items, opts, t):
        calls.append([i["코드"] for i in items])
        return [{"kind": "page", "key": i["코드"], "상태": "성공", "products": pages[i["코드"]]} for i in items]

    sh = FakeSheet()
    ck = tmp_path / "scan.json"
    n = C.do_scan(sh, MASTER, "A>B", ck, run, "2026-10-02", OPTS)
    assert n == 2
    assert [r[5] for r in sh.tabs[S.SCAN_TAB]] == ["11", "10"]       # 리뷰1000+ 많은 순
    # 재실행: 체크포인트가 있으니 aside 를 다시 부르지 않고, 이미 시트에 있는 코드는 안 쓴다
    calls.clear()
    assert C.do_scan(sh, MASTER, "A>B", ck, run, "2026-10-02", OPTS) == 0
    assert calls == []


def test_scan_captcha_saves_partial_and_exits4(tmp_path):
    def run(name, items, opts, t):
        return [{"kind": "page", "key": "10", "상태": "성공", "products": [prod(1, 1500)]},
                {"kind": "page", "key": "11", "상태": "캡챠감지", "products": []}]

    ck = tmp_path / "scan.json"
    with pytest.raises(SystemExit) as e:
        C.do_scan(FakeSheet(), MASTER, "A>B", ck, run, "2026-10-02", OPTS)
    assert e.value.code == 4
    assert list(json.loads(ck.read_text(encoding="utf-8"))["done"]) == ["10"]


def test_bench_appends_filtered_and_skips_existing_url(tmp_path):
    existing = [["a", "b", "c", "d", "kw", "s", "https://smartstore.naver.com/s/products/1"]]
    sh = FakeSheet(bench_rows=existing)

    def run(name, items, opts, t):
        if name == "search":
            return [{"kind": "page", "key": "kw", "상태": "성공",
                     "products": [prod(1, 900), prod(2, 800), prod(3, 100), prod(4, 900, "9,000")]}]
        return [{"kind": "detail", "key": i["url"], "상태": "성공", "options": [{"이름": "x", "가격": 14000}]}
                for i in items]

    n = C.do_bench(sh, "kw", tmp_path / "b.json", run, "2026-10-02", OPTS)
    assert n == 1
    row = sh.tabs[S.BENCH_TAB][-1]
    assert row[6] == "https://smartstore.naver.com/s/products/2" and row[20] == 14000


def test_bench_detail_failure_marks_manual(tmp_path):
    def run(name, items, opts, t):
        if name == "search":
            return [{"kind": "page", "key": "kw", "상태": "성공", "products": [prod(1, 900)]}]
        return [{"kind": "detail", "key": items[0]["url"], "상태": "파싱실패", "options": None}]

    sh = FakeSheet()
    C.do_bench(sh, "kw", tmp_path / "b.json", run, "2026-10-02", OPTS)
    assert sh.tabs[S.BENCH_TAB][-1][23] == "옵션수동"


def test_bench_from_scan_marks_done(tmp_path):
    row = ["2026-10-02", "A", "B", "C1", "", "10", 3, "x", "압축봉", "", "", "", ""]
    sh = FakeSheet(scan_rows=[row, ["2026-10-02", "A", "B", "C2", "", "11", 1, "y", "", "", "", "", ""]])

    def run(name, items, opts, t):
        if name == "search":
            return [{"kind": "page", "key": "압축봉", "상태": "성공", "products": [prod(1, 900)]}]
        return [{"kind": "detail", "key": items[0]["url"], "상태": "성공", "options": [{"이름": "x", "가격": 15000}]}]

    assert C.bench_from_scan(sh, tmp_path, run, "2026-10-02", OPTS) == 1
    assert sh.cells == [(S.SCAN_TAB, 0, S.SCAN_COL["벤치완료"], "Y")]
```

- [ ] **Step 2: 실패 확인**

Run: `cd .claude/skills/naver-sourcing-bench/scripts && ../../../../.venv/bin/pytest test_cli.py -v`
Expected: FAIL — `No module named 'sourcing_bench'`

- [ ] **Step 3: 구현**

```python
# -*- coding: utf-8 -*-
"""네이버 사입 소싱 벤치마크 CLI.

    PY=.venv/bin/python; S=.claude/skills/naver-sourcing-bench/scripts/sourcing_bench.py
    $PY $S init --title "사입 소싱 후보"
    $PY $S login-check
    $PY $S scan --category "생활/건강>수납/정리"
    $PY $S bench --keyword "압축봉"          # 또는 --from-scan
    $PY $S annotate --row 3 --volume 12000 --competition 낮음
"""
import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

import aside_bridge
import rules
import sheet_schema as S
from gws_sheet import GwsError, Sheet

HERE = Path(__file__).resolve().parent
RUNS = HERE.parent / "runs"
CONFIG = RUNS / "config.json"
MASTER = HERE.parents[3] / "30-knowledge" / "39-naver-category" / "naver-category-master.json"
SEC_LIST, SEC_DETAIL = 6.0, 5.0     # 페이지당 대략 소요(초) — 청크 계산용
STOP = ("캡챠감지", "차단감지")
LOGIN_MSG = ("네이버 로그인이 안 돼 있다. Aside 브라우저 창에서 네이버에 직접 로그인한 뒤 다시 실행해 줘.\n"
             "(아이디·비밀번호는 여기에 입력하지 않는다)")


def _load(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _save(path, data):
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError as e:
        print(f"[warn] 체크포인트 저장 실패: {e}", flush=True)


def _slug(s):
    return re.sub(r"[^\w가-힣]+", "_", s).strip("_")[:60]


def _chunks(items, n):
    for i in range(0, len(items), n):
        yield items[i:i + n]


def require_login(run=aside_bridge.run_driver):
    """Aside 의 네이버 로그인 여부. 미로그인이면 안내 후 종료코드 3."""
    try:
        res = run("login", [], {}, 60)
    except RuntimeError as e:
        print(f"Aside 실행 실패: {e}", flush=True)
        raise SystemExit(3)
    if not res or not res[0].get("loggedIn"):
        print(LOGIN_MSG, flush=True)
        raise SystemExit(3)


def do_scan(sheet, master, root_path, ckpt_path, run, date, opts):
    cats = rules.leaf_categories(master, root_path)
    ck = _load(ckpt_path, {"done": {}})
    todo = [c for c in cats if c["코드"] not in ck["done"]]
    stopped = False
    for chunk in _chunks(todo, aside_bridge.auto_chunk(len(todo), SEC_LIST, opts["sleepMax"])):
        for r in run("scan", [{"코드": c["코드"]} for c in chunk], opts, 115):
            if r.get("상태") in STOP:
                stopped = True
                break
            ck["done"][r["key"]] = r
        _save(ckpt_path, ck)
        if stopped:
            break
    # 시트에 아직 없는 카테고리만, 리뷰1000+ 많은 순으로 기록
    have = {row[5] for row in sheet.read(S.SCAN_TAB) if len(row) > 5}
    rows = []
    for c in cats:
        page = ck["done"].get(c["코드"])
        if not page or c["코드"] in have:
            continue
        summ = rules.scan_summary(page.get("products") or [])
        row = S.scan_row(date, c, summ)
        if page.get("상태") != "성공":
            row[11] = f"{page.get('상태')}: {page.get('error') or ''}"
        rows.append(row)
    rows.sort(key=lambda r: r[6], reverse=True)
    n = sheet.append(S.SCAN_TAB, rows)
    if stopped:
        print("캡챠/차단으로 중단했다. Aside 창에서 확인 후 같은 명령을 다시 실행하면 이어서 한다.", flush=True)
        raise SystemExit(4)
    return n


def do_bench(sheet, keyword, ckpt_path, run, date, opts, with_options=True):
    ck = _load(ckpt_path, {"page": None, "details": {}})
    if not ck["page"] or ck["page"].get("상태") != "성공":
        res = run("search", [{"키워드": keyword}], opts, 115)
        page = res[0] if res else {"상태": "파싱실패", "products": []}
        if page.get("상태") in STOP:
            print("캡챠/차단으로 중단했다.", flush=True)
            raise SystemExit(4)
        ck["page"] = page
        _save(ckpt_path, ck)
    picks = rules.bench_filter(ck["page"].get("products") or [])
    have = {rules.norm_url(r[6]) for r in sheet.read(S.BENCH_TAB) if len(r) > 6}
    picks = [p for p in picks if rules.norm_url(p["url"]) not in have]
    if with_options:
        need = [{"url": p["url"]} for p in picks if p["url"] not in ck["details"]]
        for chunk in _chunks(need, aside_bridge.auto_chunk(len(need), SEC_DETAIL, opts["sleepMax"])):
            stop = False
            for d in run("detail", chunk, opts, 115):
                if d.get("상태") in STOP:
                    stop = True
                    break
                ck["details"][d["key"]] = d
            _save(ckpt_path, ck)
            if stop:
                print("상세 조회 중 캡챠/차단 — 남은 상품은 옵션수동으로 기록한다.", flush=True)
                break
    rows = []
    for p in picks:
        d = ck["details"].get(p["url"]) if with_options else None
        opts_ = d.get("options") if d and d.get("상태") == "성공" else None
        rows.append(S.bench_row(date, keyword, p, opts_))
    return sheet.append(S.BENCH_TAB, rows)


def bench_from_scan(sheet, ckpt_dir, run, date, opts, with_options=True):
    total = 0
    kc, dc = S.SCAN_COL["키워드"], S.SCAN_COL["벤치완료"]
    for i, row in enumerate(sheet.read(S.SCAN_TAB)):
        row = row + [""] * (len(S.SCAN_HEADER) - len(row))
        kw = str(row[kc]).strip()
        if not kw or str(row[dc]).strip():
            continue
        total += do_bench(sheet, kw, Path(ckpt_dir) / f"bench-{_slug(kw)}.json", run, date, opts, with_options)
        sheet.set_cell(S.SCAN_TAB, i, dc, "Y")
    return total


def _sheet(args):
    sid = args.sheet or _load(CONFIG, {}).get("sheet_id")
    if not sid:
        sys.exit("시트 ID 가 없다. 먼저 `init` 을 실행하거나 --sheet 를 준다.")
    return Sheet(sid)


def main():
    ap = argparse.ArgumentParser(description="네이버 사입 소싱 벤치마크")
    ap.add_argument("--sheet", help="스프레드시트 ID (기본: runs/config.json)")
    ap.add_argument("--sleep", type=float, default=3.0)
    ap.add_argument("--sleep-max", type=float, default=9.0)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("--title", default="사입 소싱 후보")
    sub.add_parser("login-check")
    p = sub.add_parser("scan"); p.add_argument("--category", required=True)
    p = sub.add_parser("bench")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--keyword"); g.add_argument("--from-scan", action="store_true")
    p.add_argument("--no-options", action="store_true", help="상세 옵션 수집 생략(9·10열 수동)")
    p = sub.add_parser("annotate")
    p.add_argument("--row", type=int, required=True, help="카테고리스캔 탭의 시트 행 번호(헤더=1)")
    p.add_argument("--volume", default=""); p.add_argument("--competition", default="")
    args = ap.parse_args()

    opts = {"sleep": args.sleep, "sleepMax": args.sleep_max}
    date = dt.date.today().isoformat()
    try:
        if args.cmd == "init":
            sh = Sheet.create(args.title)
            _save(CONFIG, {"sheet_id": sh.sid})
            print(f"https://docs.google.com/spreadsheets/d/{sh.sid}")
        elif args.cmd == "login-check":
            require_login()
            print("네이버 로그인 확인됨")
        elif args.cmd == "scan":
            require_login()
            master = _load(MASTER, None)
            if not master:
                sys.exit(f"카테고리 마스터 없음: {MASTER} (naver-category-master 스킬로 갱신)")
            n = do_scan(_sheet(args), master, args.category,
                        RUNS / f"scan-{_slug(args.category)}.json", aside_bridge.run_driver, date, opts)
            print(f"카테고리스캔 {n}행 추가")
        elif args.cmd == "bench":
            require_login()
            sh = _sheet(args)
            if args.from_scan:
                n = bench_from_scan(sh, RUNS, aside_bridge.run_driver, date, opts, not args.no_options)
            else:
                n = do_bench(sh, args.keyword, RUNS / f"bench-{_slug(args.keyword)}.json",
                             aside_bridge.run_driver, date, opts, not args.no_options)
            print(f"후보 {n}행 추가")
        elif args.cmd == "annotate":
            sh = _sheet(args)
            sh.set_cell(S.SCAN_TAB, args.row - 2, S.SCAN_COL["검색량"], args.volume)
            sh.set_cell(S.SCAN_TAB, args.row - 2, S.SCAN_COL["경쟁도"], args.competition)
    except ValueError as e:
        print(f"입력 오류: {e}", flush=True); sys.exit(2)
    except (GwsError, RuntimeError) as e:
        print(f"실패: {e}", flush=True); sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 통과 확인 (전체)**

Run: `cd .claude/skills/naver-sourcing-bench/scripts && ../../../../.venv/bin/pytest -v`
Expected: 25 passed (rules 8 + schema 4 + gws 6 + cli 7)

- [ ] **Step 5: 커밋**

```bash
git add .claude/skills/naver-sourcing-bench/scripts/sourcing_bench.py .claude/skills/naver-sourcing-bench/scripts/test_cli.py
git commit -m "feat(sourcing-bench): CLI — init/login-check/scan/bench/annotate"
```

---

### Task 8: SKILL.md + 실전 E2E

**Files:**
- Create: `.claude/skills/naver-sourcing-bench/SKILL.md`
- Modify: `.claude/skills/naver-sourcing-bench/evidence/probe-2026-10.md` (E2E 결과 추가)

- [ ] **Step 1: `SKILL.md` 작성**

````markdown
---
name: naver-sourcing-bench
description: 중국 사입 소싱용으로 네이버 쇼핑에서 리뷰 많은 세부 카테고리를 스캔하고, 고른 키워드의 벤치마크 상품(리뷰 500+·1만원 이상)을 구글 시트 20열(+보조열)로 정리한다. "사입 소싱", "벤치마크 상품 찾아줘", "카테고리 스캔", "소싱 후보 정리", "리뷰 많은 카테고리", "사입 후보 시트" 등을 언급하면 자동 실행. 1688·180일 판매량은 사용자가 수동 입력.
allowed-tools:
  - Bash
  - Read
---

# 네이버 사입 소싱 벤치마크

설계: `docs/superpowers/specs/2026-10-01-naver-sourcing-bench-design.md`

## 0. 시작 전 — 반드시 사용자에게 로그인 요청

작업 시작 시 가장 먼저 이렇게 말하고 답을 기다린다:

> Aside 브라우저에서 네이버에 직접 로그인해 줘. 로그인돼 있으면 캡챠가 덜 걸린다. 끝나면 알려줘.

아이디·비밀번호는 묻지도 받지도 않는다. 답을 받으면 `login-check` 로 확인한다(종료코드 3 = 아직 미로그인 → 같은 요청 반복).

## 1. 명령

```bash
PY=.venv/bin/python; S=.claude/skills/naver-sourcing-bench/scripts/sourcing_bench.py
$PY $S init --title "사입 소싱 후보"           # 최초 1회. 시트 URL 출력, ID 는 runs/config.json
$PY $S login-check
$PY $S scan --category "생활/건강>수납/정리"    # 대 또는 대>중
$PY $S bench --from-scan                        # 스캔 탭에 키워드 적힌 행 일괄
$PY $S bench --keyword "압축봉"                 # 키워드 하나
$PY $S annotate --row 3 --volume 12000 --competition 낮음
```

옵션: `--sleep 3 --sleep-max 9`(기본), `bench --no-options`(상세 옵션 생략).
종료코드: 2 입력오류 · 3 로그인 필요 · 4 캡챠/차단 중단(같은 명령 재실행 = 이어서).

## 2. 흐름

1. 로그인 요청 → `login-check`
2. 사용자가 준 대/중카테고리로 `scan` → 시트 `카테고리스캔` 탭 링크와 상위 5개 카테고리를 보고
3. 사용자가 `키워드` 열을 채우면, 각 키워드를 불사자 `bulsaja_keyword_search` 로 조회해 검색량·경쟁도를 `annotate` 로 기입
4. `bench --from-scan` → `후보` 탭 행 수 보고
5. 사용자에게 수동 칸 안내: 11 180일 판매수량, 15 1688 이미지검색 링크, 16 1688 위안가격. `상태=옵션수동` 행은 9·10 도.

## 3. 캡챠

종료코드 4 → `captcha-relay` 스킬 또는 사용자가 Aside 창에서 해결 → 같은 명령 재실행.
연속 캡챠면 `--sleep 5 --sleep-max 15` 로 올린다.
````

- [ ] **Step 2: 사용자 로그인 요청 → 실전 E2E**

사용자에게 로그인 요청(§0 문구) 후:

```bash
PY=.venv/bin/python; S=.claude/skills/naver-sourcing-bench/scripts/sourcing_bench.py
$PY $S init --title "사입 소싱 후보"
$PY $S login-check
$PY $S scan --category "<사용자가 준 대>중 카테고리>"
```

Expected: 시트 URL, `카테고리스캔 N행 추가`(N = 리프 수, 리뷰1000+ 내림차순). 사용자에게 상위 카테고리 보여주고 키워드 1개를 받아 `bench --keyword <키워드>` → `후보 M행 추가`.

- [ ] **Step 3: 값 대조**

- 시트 `후보` 행 중 5건: 리뷰수·대표판매가·카테고리를 사용자가 자기 브라우저에서 네이버 화면과 대조(네이버 화면 확인은 사용자 몫). 결과를 evidence 에 기록.
- 수식 확인: 첫 행 K 에 `1800`, P 에 `20` 입력 → L=10, M=10×대표가, N=M×30, Q=4200, R=5880, S=대표가−5880, T=10×30×S 인지 확인 후 두 칸 지운다.
- 재실행 확인: 같은 `bench --keyword` 재실행 → `후보 0행 추가`(중복 차단).

- [ ] **Step 4: 커밋**

```bash
git add .claude/skills/naver-sourcing-bench/SKILL.md .claude/skills/naver-sourcing-bench/evidence/probe-2026-10.md
git commit -m "feat(sourcing-bench): SKILL.md + 실전 E2E 기록"
```
