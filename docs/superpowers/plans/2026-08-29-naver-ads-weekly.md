# naver-ads-weekly 스킬 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 네이버 검색광고 다계정을 주 1회 훑어 6개 규칙으로 상품을 분류하고, 구글시트 원장과 마크다운 총괄 보고서를 만들며, 입찰 인상과 꺼진 소재 삭제는 승인 후 별도 명령으로 실행하는 스킬을 만든다.

**Architecture:** 주간 배치(`prep`→`run`→`apply`)는 **쓰기를 전혀 하지 않는다**. 광고 API를 건드리는 두 동작은 `bids`(입찰 인상)·`prune`(꺼진 소재 삭제)로 분리하고 둘 다 `--commit` 없이는 dry-run 이다. 판정 로직(`ads_rules.py`)은 순수 함수로 두어 네트워크 없이 테스트한다.

**Tech Stack:** Python 3.12 · 표준 라이브러리(urllib/hmac/hashlib/json) · `unittest` · `eroomlib.config` · gws CLI(구글시트)

**Spec:** `docs/superpowers/specs/2026-08-27-naver-ads-weekly-design.md`

## Global Constraints

- **pytest 를 쓰지 않는다.** 이 워크스페이스는 `unittest` + 스크립트 직접 실행이다: `python3 .claude/skills/naver-ads-weekly/scripts/test_xxx.py`
- 파이썬은 `/Users/choiyongsmacbook/Documents/yongtimjang_claudecode/.venv/bin/python3`
- 주석은 한국어. 네트워크·파일 I/O 는 `try-except` 로 감싼다
- **자격증명**: `~/.eroom/naver-ads.json` (권한 600, git 밖). 형태: `{"accounts":[{"alias","customer_id","api_key","secret_key"}, ...]}`
- **경로를 코드에 박지 않는다** — `eroomlib.config.cfg()` + `workspace.toml`. 데이터 루트는 `/Users/choiyongsmacbook/python_work/data`
- **API Base**: `https://api.searchad.naver.com`
- **서명**: `base64(HMAC-SHA256(secret, "{timestamp_ms}.{METHOD}.{path}"))`. **path 에 쿼리스트링을 넣지 않는다**
- **헤더**: `X-Timestamp` / `X-API-KEY` / `X-Customer` / `X-Signature` / `User-Agent` 명시(기본 urllib UA 는 막힌다)
- **쓰기는 `bids`·`prune` 두 진입점만.** `--commit` 없으면 dry-run
- **판정 기간**: ① 7일 / ②③④⑤ 30일. 기간 끝은 항상 **D-2**(D-1 은 `20007 지표 준비중`)
- **노출 하한**: ②④ 는 노출 100회 이상만
- **입찰 상한 200원**, 3주 연속 인상 실패 시 중단
- **보고서에 총전환·장바구니 수치를 싣지 않는다.** 구매완료 기준만
- **`/stats` 의 `convAmt`·`ccnt` 는 장바구니 포함이라 쓰지 않는다.** 전환은 `AD_CONVERSION` 리포트의 `purchase` 유형만
- **`salesAmt` 는 매출이 아니라 광고비**다

---

## File Structure

```
.claude/skills/naver-ads-weekly/
├── SKILL.md                     # 요약 + 진입점 + 링크 (500줄/5k토큰 이내)
├── references/
│   └── 규칙-판정기준.md          # 6개 규칙 전문 · 가드레일 · 전환 함정
└── scripts/
    ├── nvad.py                  # API 클라이언트: 서명·호출 (Task 1)
    ├── reports.py               # StatReport 생성·폴링·다운로드·파싱 (Task 2)
    ├── ads_rules.py             # 6개 규칙 판정 — 순수 함수 (Task 3)
    ├── ledger.py                # 회차 이력: 3주 연속·상한도달 판정 (Task 4)
    ├── collect.py               # 계정 순회 수집 (Task 5)
    ├── report_md.py             # 마크다운 총괄 보고서 (Task 7)
    ├── sheets_out.py            # 구글시트 원장 기록 (Task 8)
    ├── bids.py                  # ① 입찰 인상 + 가드레일 (Task 9)
    ├── prune.py                 # ⑥ 꺼진 소재 삭제 + 백업 (Task 10)
    ├── run_ads.py               # CLI 진입점 prep/run/apply/bids/prune (Task 6)
    ├── test_nvad.py
    ├── test_reports.py
    ├── test_ads_rules.py
    ├── test_ledger.py
    └── test_bids.py
```

**책임 분리 원칙**: 네트워크를 타는 것(`nvad`·`reports`·`collect`)과 판정하는 것(`ads_rules`·`ledger`)을 분리한다. 판정은 순수 함수라 네트워크 없이 전량 테스트되고, 이 스킬의 버그는 대부분 판정에서 난다.

**run-dir 구조** (`<데이터루트>/naver-ads/runs/<YYYY-MM-DD>/`):
```
accounts/<alias>/ads.json        소재 목록 (enable 포함 전량)
accounts/<alias>/stats_7d.json   7일 통계
accounts/<alias>/stats_30d.json  30일 통계
accounts/<alias>/purchase.json   30일 구매완료 (adId → {cnt, amt})
result.json                      6개 규칙 판정 결과
report.md                        총괄 보고서
```

---

### Task 1: API 클라이언트 (nvad.py)

실측으로 검증된 서명·호출 로직을 스킬로 이식한다. 서명 규칙이 틀리면 전부가 무너지므로 여기부터 테스트한다.

**Files:**
- Create: `.claude/skills/naver-ads-weekly/scripts/nvad.py`
- Test: `.claude/skills/naver-ads-weekly/scripts/test_nvad.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `load_accounts() -> list[dict]` — `~/.eroom/naver-ads.json` 의 `accounts` 배열
  - `sign(secret: str, ts: str, method: str, path: str) -> str` — base64 서명
  - `call(acct: dict, method: str, path: str, params: dict|None = None, body: dict|None = None, raw: bool = False) -> tuple[int, object]`
    **어떤 입력에도 예외를 올리지 않는다** — 자격증명 키 누락·직렬화 불가 body 포함 전부 `(0, "에러문자열")`
  - `download(acct: dict, url: str) -> str|None` — 리포트 다운로드. **실패하면 None**(예외를 올리지 않는다)
  - `chunks(seq: list, n: int)` — 제너레이터
  - `BASE: str`, `CRED: Path`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`test_nvad.py`:

```python
#!/usr/bin/env python3
"""nvad 서명 회귀 테스트 — 네트워크 없이 돈다.

    .venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/test_nvad.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nvad  # noqa: E402


class TestSign(unittest.TestCase):
    def test_서명은_고정입력에_고정출력을_낸다(self):
        # 서명 규칙이 바뀌면 여기가 제일 먼저 깨져야 한다
        got = nvad.sign("mysecret", "1700000000000", "GET", "/ncc/campaigns")
        self.assertEqual(got, "1Zx3mYX9wLQhUEwPHFPkGCLPXNzYUUL8GcC8gVN+ZKk=")

    def test_서명대상에_쿼리스트링이_들어가면_안된다(self):
        a = nvad.sign("s", "1", "GET", "/stats")
        b = nvad.sign("s", "1", "GET", "/stats?ids=x")
        self.assertNotEqual(a, b, "path 를 그대로 서명하므로 둘은 달라야 한다")

    def test_메서드가_다르면_서명이_다르다(self):
        self.assertNotEqual(
            nvad.sign("s", "1", "GET", "/ncc/ads"),
            nvad.sign("s", "1", "PUT", "/ncc/ads"),
        )


class TestChunks(unittest.TestCase):
    def test_100개씩_자른다(self):
        self.assertEqual([len(c) for c in nvad.chunks(list(range(250)), 100)], [100, 100, 50])

    def test_빈리스트는_아무것도_내지_않는다(self):
        self.assertEqual(list(nvad.chunks([], 100)), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/test_nvad.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'nvad'`

- [ ] **Step 3: nvad.py 를 쓴다**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""네이버 검색광고 API 클라이언트.

서명 규칙(2026-08-27 실측 검증):
    base64(HMAC-SHA256(secret, "{timestamp_ms}.{METHOD}.{path}"))
    · path 에 쿼리스트링을 넣지 않는다
    · 리포트 다운로드 URL 도 같은 서명이 필요하다(URL 의 path 부분만 사용)
"""
import base64
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://api.searchad.naver.com"
CRED = Path.home() / ".eroom" / "naver-ads.json"
# 기본 urllib UA 를 막는 앞단이 있어 UA 를 명시한다
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"


def load_accounts():
    """자격증명 파일에서 계정 목록을 읽는다. 없으면 빈 리스트."""
    try:
        d = json.loads(CRED.read_text(encoding="utf-8"))
    except Exception:
        return []
    return d.get("accounts", []) if isinstance(d, dict) else d


def sign(secret, ts, method, path):
    """HMAC-SHA256 서명. 서명 대상은 쿼리스트링을 제외한 path 다."""
    msg = f"{ts}.{method}.{path}".encode("utf-8")
    return base64.b64encode(hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).digest()).decode("utf-8")


def headers(acct, method, path):
    """요청 헤더 4종 + UA."""
    ts = str(round(time.time() * 1000))
    return {
        "X-Timestamp": ts,
        "X-API-KEY": acct["api_key"],
        "X-Customer": str(acct["customer_id"]),
        "X-Signature": sign(acct["secret_key"], ts, method, path),
        "Content-Type": "application/json; charset=UTF-8",
        "User-Agent": UA,
    }


def call(acct, method, path, params=None, body=None, raw=False):
    """API 1회 호출. (status, body) 반환. 예외는 (0, "에러문자열")."""
    url = BASE + path + (("?" + urllib.parse.urlencode(params)) if params else "")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers(acct, method, path))
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            text = r.read().decode("utf-8")
            if raw:
                return r.status, text
            return r.status, (json.loads(text) if text.strip() else None)
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read().decode("utf-8")
        except Exception:
            return e.code, ""
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"


def download(acct, url):
    """리포트 다운로드. 같은 서명이 필요하고 서명 대상은 URL 의 path 부분이다."""
    p = urllib.parse.urlparse(url)
    h = headers(acct, "GET", p.path)
    h.pop("Content-Type", None)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read().decode("utf-8", errors="replace")


def chunks(seq, n):
    """seq 를 n개씩 자른다. /stats 의 ids 상한이 100 이라 필요하다."""
    for i in range(0, len(seq), n):
        yield seq[i:i + n]
```

- [ ] **Step 4: 테스트를 돌려 통과를 확인한다**

Run: `.venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/test_nvad.py`
Expected: PASS (5 tests)

> 서명 기대값이 다르면 **테스트의 기대값을 고치지 말고** 구현을 의심한다.
> 기대값은 `sign("mysecret","1700000000000","GET","/ncc/campaigns")` 을 직접 계산해 확인한다:
> `.venv/bin/python3 -c "import sys;sys.path.insert(0,'.claude/skills/naver-ads-weekly/scripts');import nvad;print(nvad.sign('mysecret','1700000000000','GET','/ncc/campaigns'))"`

- [ ] **Step 5: 실계정으로 연기 테스트(smoke)한다**

Run:
```bash
.venv/bin/python3 -c "
import sys; sys.path.insert(0,'.claude/skills/naver-ads-weekly/scripts')
import nvad
for a in nvad.load_accounts():
    st, r = nvad.call(a, 'GET', '/ncc/campaigns')
    print(a['alias'], st, len(r) if isinstance(r, list) else r)
"
```
Expected: 각 계정 `200` 과 캠페인 개수

- [ ] **Step 6: 커밋**

```bash
git add .claude/skills/naver-ads-weekly/scripts/nvad.py .claude/skills/naver-ads-weekly/scripts/test_nvad.py
git commit -m "feat(naver-ads): 검색광고 API 클라이언트 + 서명 회귀 테스트"
```

---

### Task 2: 전환 리포트 클라이언트 (reports.py)

`/stats` 의 전환값은 장바구니가 섞여 있어 쓸 수 없다. 구매완료만 얻으려면 일자별 `AD_CONVERSION` 리포트를 받아야 한다.

**Files:**
- Create: `.claude/skills/naver-ads-weekly/scripts/reports.py`
- Test: `.claude/skills/naver-ads-weekly/scripts/test_reports.py`

**Interfaces:**
- Consumes: `nvad.call`, `nvad.download`
- Produces:
  - `parse_conversion_tsv(text: str) -> list[dict]` — 각 `{"adId","convType","cnt","amt"}`
  - `fetch_purchases(acct: dict, until: date, days: int, log=print) -> dict[str, dict]` — `{adId: {"cnt": int, "amt": int}}`, `purchase` 유형만

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`test_reports.py`:

```python
#!/usr/bin/env python3
"""AD_CONVERSION 리포트 파싱 회귀 테스트 — 네트워크 없이 돈다."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reports  # noqa: E402

# 2026-08-25 cy728 실제 응답 2행 (탭 구분, 13열)
REAL = (
    "20260825\t4158478\tcmp-a001-02-000000009889842\tgrp-a001-02-000000056901303\t-\t"
    "nad-a001-02-000000487628566\tbsn-a001-00-000000012981745\t623353\tM\t1\tadd_to_cart\t1\t218600\n"
    "20260825\t4158478\tcmp-a001-02-000000009889842\tgrp-a001-02-000000056901104\t-\t"
    "nad-a001-02-000000501855520\tbsn-a001-00-000000012981702\t644590\tM\t1\tpurchase\t1\t233900\n"
)


class TestParse(unittest.TestCase):
    def test_전환유형과_금액을_뽑는다(self):
        rows = reports.parse_conversion_tsv(REAL)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["convType"], "add_to_cart")
        self.assertEqual(rows[1]["convType"], "purchase")
        self.assertEqual(rows[1]["adId"], "nad-a001-02-000000501855520")
        self.assertEqual(rows[1]["cnt"], 1)
        self.assertEqual(rows[1]["amt"], 233900)

    def test_짧은_행은_버린다(self):
        self.assertEqual(reports.parse_conversion_tsv("a\tb\tc\n"), [])

    def test_빈_문자열은_빈_리스트다(self):
        self.assertEqual(reports.parse_conversion_tsv(""), [])

    def test_빈_줄을_건너뛴다(self):
        self.assertEqual(len(reports.parse_conversion_tsv(REAL + "\n\n")), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/test_reports.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'reports'`

- [ ] **Step 3: reports.py 를 쓴다**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AD_CONVERSION 리포트 — 구매완료(purchase) 전환만 뽑는다.

왜 필요한가(2026-08-27 실측):
    /stats 의 ccnt·convAmt 는 전환유형을 전부 합산한 값이라 장바구니가 섞인다.
    cy728 30일: add_to_cart 7,321,700원 vs purchase 596,920원 — 12배 차이.
    breakdown 파라미터는 400 이 아니라 200 에 안 쪼개진 값을 주므로 눈치채기 어렵다.

리포트는 하루치씩만 생성된다. D-1 은 "20007 지표 준비중" 이라 D-2 부터 쓴다.
"""
import time
from collections import defaultdict
from datetime import timedelta

import nvad

# 전환유형 컬럼은 0-based 10 번, 전환수 11, 금액 12
_COL_AD_ID = 5
_COL_CONV_TYPE = 10
_COL_CNT = 11
_COL_AMT = 12
_MIN_COLS = 13


def parse_conversion_tsv(text):
    """리포트 TSV 를 행 리스트로 바꾼다. 열이 모자란 행은 버린다."""
    rows = []
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        c = line.split("\t")
        if len(c) < _MIN_COLS:
            continue
        try:
            rows.append({
                "adId": c[_COL_AD_ID],
                "convType": c[_COL_CONV_TYPE],
                "cnt": int(c[_COL_CNT] or 0),
                "amt": int(c[_COL_AMT] or 0),
            })
        except (ValueError, IndexError):
            continue
    return rows


def _build_and_download(acct, day, log):
    """하루치 리포트를 생성·폴링·다운로드한다. 전환 0인 날은 빌드되지 않는다."""
    st, job = nvad.call(acct, "POST", "/stat-reports",
                        body={"reportTp": "AD_CONVERSION", "statDt": day.isoformat() + "T00:00:00Z"})
    if st not in (200, 201) or not isinstance(job, dict):
        log(f"    {day} 생성 실패 {st} {str(job)[:120]}")
        return None
    jid = job.get("reportJobId")
    for _ in range(12):
        time.sleep(4)
        st, j = nvad.call(acct, "GET", f"/stat-reports/{jid}")
        if not isinstance(j, dict):
            continue
        if j.get("status") == "BUILT" and j.get("downloadUrl"):
            # nvad.download 는 실패하면 예외 대신 None 을 준다
            text = nvad.download(acct, j["downloadUrl"])
            if text is None:
                log(f"    {day} 다운로드 실패")
            return text
        if j.get("status") in ("NONE", "ERROR"):
            return None
    log(f"    {day} 빌드 대기 초과")
    return None


def fetch_purchases(acct, until, days, log=print):
    """until 부터 거슬러 days 일치 구매완료 전환을 소재별로 합산한다."""
    out = defaultdict(lambda: {"cnt": 0, "amt": 0})
    ok_days = 0
    for d in range(days):
        day = until - timedelta(days=d)
        text = _build_and_download(acct, day, log)
        if text is None:
            continue
        ok_days += 1
        for r in parse_conversion_tsv(text):
            if r["convType"] != "purchase":
                continue
            out[r["adId"]]["cnt"] += r["cnt"]
            out[r["adId"]]["amt"] += r["amt"]
    log(f"    구매완료 리포트 {ok_days}/{days}일 · 발생 소재 {len(out)}개")
    return dict(out)
```

- [ ] **Step 4: 테스트를 돌려 통과를 확인한다**

Run: `.venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/test_reports.py`
Expected: PASS (4 tests)

- [ ] **Step 5: 커밋**

```bash
git add .claude/skills/naver-ads-weekly/scripts/reports.py .claude/skills/naver-ads-weekly/scripts/test_reports.py
git commit -m "feat(naver-ads): 구매완료 전환 리포트 클라이언트"
```

---

### Task 3: 규칙 판정 (ads_rules.py)

이 스킬의 심장이다. 네트워크를 타지 않는 순수 함수라 전량 테스트한다.

**Files:**
- Create: `.claude/skills/naver-ads-weekly/scripts/ads_rules.py`
- Test: `.claude/skills/naver-ads-weekly/scripts/test_ads_rules.py`

**Interfaces:**
- Consumes: 없음(순수 함수)
- Produces:
  - `IMP_MIN = 100`, `CLICK_MIN = 20`, `CTR_LOW = 1.0`, `CTR_HIGH = 2.0`
  - `live_ads(ads: list[dict]) -> list[dict]` — `enable=True` 만
  - `effective_bid(ad: dict, group_bid: int|None) -> int|None` — 실제 적용 입찰가
  - `ad_info(ad: dict, group_name: str, group_bid: int|None) -> dict`
  - `classify(ads, group_of, stats_7d, stats_30d, purchases) -> dict[str, list[dict]]`
    반환 키: `"①노출0"`, `"②썸네일교체"`, `"③원인분석"`, `"④효자후보"`, `"⑤효자확정"`, `"⑥삭제대상"`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`test_ads_rules.py`:

```python
#!/usr/bin/env python3
"""6개 규칙 판정 회귀 테스트 — 네트워크 없이 돈다.

수치는 cy728 실측(2026-08-27~29)에서 가져왔다. 규칙이 바뀌면 여기가 먼저 깨져야 한다.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ads_rules as R  # noqa: E402


def ad(ad_id, enable=True, bid=None, use_group=True, title="상품", mall="1", group="grp1"):
    """소재 1건을 만든다. adAttr 구조는 실측 응답 그대로다."""
    return {
        "nccAdId": ad_id, "nccAdgroupId": group, "enable": enable,
        "adAttr": {"bidAmt": bid, "useGroupBidAmt": use_group},
        "referenceData": {"productTitle": title, "mallProductId": mall},
    }


def stat(imp=0, clk=0, ctr=0.0, cost=0, rank=0.0):
    return {"impCnt": imp, "clkCnt": clk, "ctr": ctr, "salesAmt": cost, "avgRnk": rank}


class TestLiveAds(unittest.TestCase):
    def test_꺼진_소재를_거른다(self):
        got = R.live_ads([ad("a"), ad("b", enable=False)])
        self.assertEqual([x["nccAdId"] for x in got], ["a"])


class TestEffectiveBid(unittest.TestCase):
    def test_그룹입찰이면_그룹_기본가가_적용가다(self):
        # 잠자던 bidAmt(50)가 아니라 그룹값(70)이 실제 적용가다
        self.assertEqual(R.effective_bid(ad("a", bid=50, use_group=True), 70), 70)

    def test_개별입찰이면_자기_bidAmt_가_적용가다(self):
        self.assertEqual(R.effective_bid(ad("a", bid=120, use_group=False), 70), 120)

    def test_그룹가가_없으면_None(self):
        self.assertIsNone(R.effective_bid(ad("a", bid=50, use_group=True), None))


class TestClassify(unittest.TestCase):
    def setUp(self):
        self.group_of = {"grp1": {"name": "판매상품_11-2_테스트", "bidAmt": 70}}

    def _run(self, ads, s7=None, s30=None, pur=None):
        return R.classify(ads, self.group_of, s7 or {}, s30 or {}, pur or {})

    def test_규칙1_7일_통계에_없는_게재중_소재가_노출0이다(self):
        res = self._run([ad("a"), ad("b")], s7={"a": stat(imp=10)})
        self.assertEqual([x["adId"] for x in res["①노출0"]], ["b"])

    def test_규칙1은_꺼진_소재를_담지_않는다(self):
        # 꺼진 소재는 당연히 노출 0이다. 담으면 죽은 광고 입찰가만 올리게 된다
        res = self._run([ad("a", enable=False)])
        self.assertEqual(res["①노출0"], [])

    def test_규칙6은_꺼진_소재만_담는다(self):
        res = self._run([ad("a"), ad("b", enable=False)])
        self.assertEqual([x["adId"] for x in res["⑥삭제대상"]], ["b"])

    def test_규칙2는_노출하한_미만을_제외한다(self):
        # 노출 99·CTR 0% 는 표본 부족이지 썸네일 문제가 아니다
        res = self._run([ad("a"), ad("b")],
                        s30={"a": stat(imp=99, ctr=0.0), "b": stat(imp=100, ctr=0.5)})
        self.assertEqual([x["adId"] for x in res["②썸네일교체"]], ["b"])

    def test_규칙2는_노출_많은_순으로_정렬된다(self):
        res = self._run([ad("a"), ad("b")],
                        s30={"a": stat(imp=200, ctr=0.5), "b": stat(imp=900, ctr=0.5)})
        self.assertEqual([x["adId"] for x in res["②썸네일교체"]], ["b", "a"])

    def test_규칙3은_구매완료가_있으면_제외한다(self):
        res = self._run([ad("a"), ad("b")],
                        s30={"a": stat(imp=500, clk=25), "b": stat(imp=500, clk=25)},
                        pur={"a": {"cnt": 1, "amt": 1000}})
        self.assertEqual([x["adId"] for x in res["③원인분석"]], ["b"])

    def test_규칙3은_클릭이_모자라면_제외한다(self):
        res = self._run([ad("a")], s30={"a": stat(imp=500, clk=19)})
        self.assertEqual(res["③원인분석"], [])

    def test_규칙4는_CTR2퍼센트_이상_노출하한_충족만(self):
        res = self._run([ad("a"), ad("b"), ad("c")],
                        s30={"a": stat(imp=500, ctr=2.0), "b": stat(imp=500, ctr=1.9),
                             "c": stat(imp=50, ctr=5.0)})
        self.assertEqual([x["adId"] for x in res["④효자후보"]], ["a"])

    def test_규칙5는_구매완료_금액을_싣는다(self):
        res = self._run([ad("a")], s30={"a": stat(imp=500, cost=1000)},
                        pur={"a": {"cnt": 2, "amt": 50000}})
        row = res["⑤효자확정"][0]
        self.assertEqual(row["purCnt"], 2)
        self.assertEqual(row["purAmt"], 50000)
        self.assertEqual(row["cost"], 1000)

    def test_판정행에_매칭키_mallProductId_가_실린다(self):
        # ②를 썸네일 스킬로 넘기려면 이 키가 반드시 있어야 한다
        res = self._run([ad("a", mall="12896544275")], s30={"a": stat(imp=500, ctr=0.1)})
        self.assertEqual(res["②썸네일교체"][0]["mallProductId"], "12896544275")

    def test_판정행에_광고그룹명이_실린다(self):
        res = self._run([ad("a")], s7={})
        self.assertEqual(res["①노출0"][0]["adGroup"], "판매상품_11-2_테스트")


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/test_ads_rules.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'ads_rules'`

- [ ] **Step 3: ads_rules.py 를 쓴다**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""6개 규칙 판정 — 순수 함수. 네트워크·파일을 타지 않는다.

기간은 호출자가 정한다: ① 은 7일 통계, ②③④⑤ 는 30일 통계를 넘긴다.
노출 0 소재는 /stats 응답에서 행 자체가 빠지므로 '게재중 전체 − 통계에 있는 것' 으로 역산한다.
"""

IMP_MIN = 100      # ②④ 노출 하한 — 없으면 ②가 전체의 66% 가 된다(실측)
CLICK_MIN = 20     # ③ 클릭 하한
CTR_LOW = 1.0      # ② 기준
CTR_HIGH = 2.0     # ④ 기준


def live_ads(ads):
    """게재중 소재만. 꺼진 소재를 안 거르면 죽은 광고 입찰가만 올리게 된다."""
    return [a for a in ads if a.get("enable")]


def effective_bid(ad, group_bid):
    """실제로 적용되는 입찰가.

    useGroupBidAmt=True 면 adAttr.bidAmt 는 잠자는 값이고 그룹 기본가가 적용된다.
    이걸 헷갈리면 입찰가를 올리려다 오히려 내리게 된다(실측: 그룹 70원 / 잠자던 값 50원).
    """
    attr = ad.get("adAttr") or {}
    if attr.get("useGroupBidAmt"):
        return group_bid
    return attr.get("bidAmt")


def ad_info(ad, group_name, group_bid):
    """판정 결과 1행의 공통 필드."""
    rd = ad.get("referenceData") or {}
    attr = ad.get("adAttr") or {}
    return {
        "adId": ad["nccAdId"],
        "adGroup": group_name,
        "title": rd.get("productTitle") or "",
        "mallProductId": rd.get("mallProductId"),   # 썸네일 스킬 매칭 키
        "bid": effective_bid(ad, group_bid),
        "useGroupBid": bool(attr.get("useGroupBidAmt")),
        "groupBid": group_bid,
    }


def _with_stat(info, s):
    """통계 지표를 판정행에 붙인다. salesAmt 는 매출이 아니라 광고비다."""
    info = dict(info)
    info.update({
        "imp": s.get("impCnt", 0), "clk": s.get("clkCnt", 0),
        "ctr": s.get("ctr") or 0.0, "rank": s.get("avgRnk") or 0.0,
        "cost": s.get("salesAmt", 0),
    })
    return info


def classify(ads, group_of, stats_7d, stats_30d, purchases):
    """6개 규칙으로 소재를 분류한다.

    ads        : 소재 전량(꺼진 것 포함)
    group_of   : {nccAdgroupId: {"name": str, "bidAmt": int|None}}
    stats_7d   : {adId: stat}  — 규칙 ① 용
    stats_30d  : {adId: stat}  — 규칙 ②③④⑤ 용
    purchases  : {adId: {"cnt": int, "amt": int}} — 구매완료만
    """
    def info_of(a):
        g = group_of.get(a.get("nccAdgroupId")) or {}
        return ad_info(a, g.get("name") or "", g.get("bidAmt"))

    live = live_ads(ads)
    off = [a for a in ads if not a.get("enable")]

    # ① 7일 통계에 행이 없는 게재중 소재 = 노출 0
    r1 = [info_of(a) for a in live if a["nccAdId"] not in stats_7d]

    r2, r3, r4, r5 = [], [], [], []
    for a in live:
        s = stats_30d.get(a["nccAdId"])
        if not s:
            continue
        row = _with_stat(info_of(a), s)
        imp, clk, ctr = row["imp"], row["clk"], row["ctr"]
        pur = purchases.get(a["nccAdId"])

        if imp >= IMP_MIN and ctr < CTR_LOW:
            r2.append(row)
        if clk >= CLICK_MIN and not pur:
            r3.append(row)
        if imp >= IMP_MIN and ctr >= CTR_HIGH:
            r4.append(row)
        if pur:
            r5.append(dict(row, purCnt=pur["cnt"], purAmt=pur["amt"]))

    # ② 는 노출 많은 순 — 노출은 많은데 클릭이 안 되는 쪽이 썸네일 문제가 가장 확실하다
    r2.sort(key=lambda x: -x["imp"])
    r4.sort(key=lambda x: -x["ctr"])
    r5.sort(key=lambda x: -x["purAmt"])

    return {
        "①노출0": r1,
        "②썸네일교체": r2,
        "③원인분석": r3,
        "④효자후보": r4,
        "⑤효자확정": r5,
        "⑥삭제대상": [info_of(a) for a in off],
    }
```

- [ ] **Step 4: 테스트를 돌려 통과를 확인한다**

Run: `.venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/test_ads_rules.py`
Expected: PASS (14 tests)

- [ ] **Step 5: 커밋**

```bash
git add .claude/skills/naver-ads-weekly/scripts/ads_rules.py .claude/skills/naver-ads-weekly/scripts/test_ads_rules.py
git commit -m "feat(naver-ads): 6개 규칙 판정 로직 + 회귀 테스트"
```

---

### Task 4: 회차 이력 (ledger.py)

"3주 연속 인상 실패"와 "상한도달-무노출"은 지난 회차를 알아야 판정된다. 이력 없이는 그 규칙이 작동하지 않는다.

**Files:**
- Create: `.claude/skills/naver-ads-weekly/scripts/ledger.py`
- Test: `.claude/skills/naver-ads-weekly/scripts/test_ledger.py`

**Interfaces:**
- Consumes: 없음(파일 I/O 만)
- Produces:
  - `BID_CAP = 200`, `FAIL_STREAK = 3`
  - `load(path) -> dict[str, dict]` — `{adId: {"raises": [{"date","from","to"}], "streak": int, "capped": bool}}`
  - `save(path, data) -> None`
  - `record_raise(data, ad_id, date_str, old_bid, new_bid) -> None`
  - `record_still_zero(data, ad_id) -> None` — 인상했는데 또 노출 0이면 streak +1
  - `record_recovered(data, ad_id) -> None` — 노출이 생기면 streak 초기화
  - `bid_decision(data, ad_id, current_bid) -> tuple[str, int|None]` — `("인상", 새값)` / `("상한도달", None)` / `("연속실패중단", None)`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`test_ledger.py`:

```python
#!/usr/bin/env python3
"""입찰 이력·상한 판정 회귀 테스트 — 네트워크 없이 돈다."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger as L  # noqa: E402


class TestDecision(unittest.TestCase):
    def test_상한_미만이면_10원_올린다(self):
        self.assertEqual(L.bid_decision({}, "a", 120), ("인상", 130))

    def test_상한에_닿으면_올리지_않는다(self):
        self.assertEqual(L.bid_decision({}, "a", 200), ("상한도달", None))

    def test_인상하면_상한을_넘는_경우도_올리지_않는다(self):
        # 195 + 10 = 205 > 200
        self.assertEqual(L.bid_decision({}, "a", 195), ("상한도달", None))

    def test_3주_연속_실패면_중단한다(self):
        data = {"a": {"raises": [], "streak": 3, "capped": False}}
        self.assertEqual(L.bid_decision(data, "a", 100), ("연속실패중단", None))

    def test_2주_연속까지는_계속_올린다(self):
        data = {"a": {"raises": [], "streak": 2, "capped": False}}
        self.assertEqual(L.bid_decision(data, "a", 100), ("인상", 110))

    def test_현재값을_모르면_올리지_않는다(self):
        self.assertEqual(L.bid_decision({}, "a", None), ("입찰가불명", None))


class TestStreak(unittest.TestCase):
    def test_또_노출0이면_연속이_쌓인다(self):
        d = {}
        L.record_raise(d, "a", "2026-08-29", 100, 110)
        L.record_still_zero(d, "a")
        L.record_still_zero(d, "a")
        self.assertEqual(d["a"]["streak"], 2)

    def test_노출이_생기면_연속이_초기화된다(self):
        d = {"a": {"raises": [], "streak": 2, "capped": False}}
        L.record_recovered(d, "a")
        self.assertEqual(d["a"]["streak"], 0)

    def test_인상이력이_쌓인다(self):
        d = {}
        L.record_raise(d, "a", "2026-08-29", 100, 110)
        L.record_raise(d, "a", "2026-09-05", 110, 120)
        self.assertEqual(len(d["a"]["raises"]), 2)
        self.assertEqual(d["a"]["raises"][-1], {"date": "2026-09-05", "from": 110, "to": 120})


class TestIO(unittest.TestCase):
    def test_없는_파일은_빈_dict(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(L.load(Path(t) / "none.json"), {})

    def test_쓰고_다시_읽으면_같다(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "l.json"
            d = {"a": {"raises": [{"date": "2026-08-29", "from": 100, "to": 110}], "streak": 1, "capped": False}}
            L.save(p, d)
            self.assertEqual(L.load(p), d)

    def test_깨진_파일은_빈_dict(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "bad.json"
            p.write_text("{{{", encoding="utf-8")
            self.assertEqual(L.load(p), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/test_ledger.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'ledger'`

- [ ] **Step 3: ledger.py 를 쓴다**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""입찰 인상 이력 — 3주 연속 실패·상한도달 판정의 근거.

이 파일이 없으면 "3주 연속 올렸는데도 노출 0" 규칙이 아예 작동하지 않는다.
회차마다 갱신되며 run-dir 이 아니라 계정별 고정 위치에 쌓인다.
"""
import json

BID_CAP = 200       # 2026-08-28 용팀장 확정. 도달분은 상한도달-무노출 리스트로 뺀다
BID_STEP = 10
FAIL_STREAK = 3     # 3주 연속 인상했는데 여전히 노출 0이면 중단


def load(path):
    """이력을 읽는다. 없거나 깨졌으면 빈 dict — 첫 회차도 그냥 돈다."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save(path, data):
    """이력을 쓴다. 부모 폴더가 없으면 만든다."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:
        print(f"이력 저장 실패 {path}: {type(e).__name__}: {e}")


def _entry(data, ad_id):
    return data.setdefault(ad_id, {"raises": [], "streak": 0, "capped": False})


def record_raise(data, ad_id, date_str, old_bid, new_bid):
    """인상 사실을 기록한다."""
    _entry(data, ad_id)["raises"].append({"date": date_str, "from": old_bid, "to": new_bid})


def record_still_zero(data, ad_id):
    """인상했는데 다음 회차에도 노출 0 — 연속 실패를 쌓는다."""
    e = _entry(data, ad_id)
    e["streak"] = e.get("streak", 0) + 1


def record_recovered(data, ad_id):
    """노출이 생겼다 — 연속을 끊는다."""
    _entry(data, ad_id)["streak"] = 0


def bid_decision(data, ad_id, current_bid):
    """이 소재를 올릴지 정한다. (사유, 새 입찰가) 를 돌려준다."""
    if current_bid is None:
        return ("입찰가불명", None)
    e = data.get(ad_id) or {}
    if e.get("streak", 0) >= FAIL_STREAK:
        return ("연속실패중단", None)
    new = current_bid + BID_STEP
    if new > BID_CAP:
        return ("상한도달", None)
    return ("인상", new)
```

- [ ] **Step 4: 테스트를 돌려 통과를 확인한다**

Run: `.venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/test_ledger.py`
Expected: PASS (12 tests)

- [ ] **Step 5: 커밋**

```bash
git add .claude/skills/naver-ads-weekly/scripts/ledger.py .claude/skills/naver-ads-weekly/scripts/test_ledger.py
git commit -m "feat(naver-ads): 입찰 이력·상한·연속실패 판정"
```

---

### Task 5: 수집 (collect.py)

계정을 순회하며 소재·통계·구매완료를 모아 run-dir 에 떨군다. 여기서 네트워크가 전부 끝난다.

**Files:**
- Create: `.claude/skills/naver-ads-weekly/scripts/collect.py`

**Interfaces:**
- Consumes: `nvad.call`, `nvad.chunks`, `reports.fetch_purchases`
- Produces:
  - `STATS_FIELDS: list[str]`
  - `window(days: int) -> tuple[date, date]` — `(since, until)`, until 은 항상 D-2
  - `fetch_ads(acct) -> tuple[list[dict], dict[str, dict]]` — `(소재 전량, group_of)`
  - `fetch_stats(acct, ad_ids, since, until) -> dict[str, dict]`
  - `collect_account(acct, run_dir, log=print) -> dict` — 계정 1개 수집 후 파일로 저장, 요약 dict 반환

- [ ] **Step 1: 창(window) 계산 테스트를 쓴다**

`test_ads_rules.py` 끝에 이어 붙이지 말고 새 클래스를 `test_reports.py` 에 추가한다
(collect 는 네트워크 의존이라 순수 부분만 테스트한다):

```python
# test_reports.py 하단, TestParse 클래스 다음에 추가
from datetime import date  # noqa: E402
import collect  # noqa: E402


class TestWindow(unittest.TestCase):
    def test_끝은_D_2_다(self):
        # D-1 은 "20007 지표 준비중" 이라 못 쓴다
        since, until = collect.window(7, today=date(2026, 8, 29))
        self.assertEqual(until, date(2026, 8, 27))

    def test_7일이면_시작은_끝에서_6일_전이다(self):
        since, until = collect.window(7, today=date(2026, 8, 29))
        self.assertEqual(since, date(2026, 8, 21))
        self.assertEqual((until - since).days, 6)

    def test_30일_창(self):
        since, until = collect.window(30, today=date(2026, 8, 29))
        self.assertEqual((until - since).days, 29)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/test_reports.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'collect'`

- [ ] **Step 3: collect.py 를 쓴다**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""계정 순회 수집 — prep 단계의 본체. 여기서 네트워크가 전부 끝난다.

호출 규모(실측): 계정 1개당 캠페인 1 + 그룹 1 + 소재 10~13 + /stats 3~6
                + 전환 리포트 30(생성·폴링). 계정 수에 선형이다.
"""
import json
from datetime import date, timedelta

import nvad
import reports

# salesAmt 는 광고비다(매출 아님). convAmt·ccnt 는 장바구니가 섞여 있어 요청하지 않는다
STATS_FIELDS = ["impCnt", "clkCnt", "ctr", "salesAmt", "avgRnk"]


def window(days, today=None):
    """(since, until) — until 은 항상 D-2. D-1 은 리포트 지표가 준비되지 않는다."""
    today = today or date.today()
    until = today - timedelta(days=2)
    return until - timedelta(days=days - 1), until


def fetch_ads(acct):
    """SHOPPING 캠페인의 소재 전량과 광고그룹 정보를 받는다.

    SHOPPING 캠페인은 계정당 여러 개일 수 있다(cy7728 은 2개) — 전부 순회한다.
    WEB_SITE 등 다른 유형은 이 스킬 범위가 아니다.
    """
    ads, group_of = [], {}
    st, camps = nvad.call(acct, "GET", "/ncc/campaigns")
    if st != 200 or not isinstance(camps, list):
        return [], {}
    for c in [x for x in camps if x.get("campaignTp") == "SHOPPING"]:
        st, groups = nvad.call(acct, "GET", "/ncc/adgroups", {"nccCampaignId": c["nccCampaignId"]})
        if st != 200 or not isinstance(groups, list):
            continue
        for g in groups:
            group_of[g["nccAdgroupId"]] = {"name": g.get("name") or "", "bidAmt": g.get("bidAmt")}
            st, a = nvad.call(acct, "GET", "/ncc/ads", {"nccAdgroupId": g["nccAdgroupId"]})
            if st == 200 and isinstance(a, list):
                ads.extend(a)
    return ads, group_of


def fetch_stats(acct, ad_ids, since, until):
    """기간 합계 통계. ids 는 100개씩 끊어 보낸다.

    노출 0 소재는 응답에서 행 자체가 빠진다 — 그래서 규칙 ① 이 역산이다.
    """
    tr = json.dumps({"since": since.isoformat(), "until": until.isoformat()})
    fields = json.dumps(STATS_FIELDS)
    out = {}
    for batch in nvad.chunks(ad_ids, 100):
        st, res = nvad.call(acct, "GET", "/stats",
                            {"ids": ",".join(batch), "fields": fields, "timeRange": tr})
        if st != 200:
            continue
        rows = res.get("data", []) if isinstance(res, dict) else (res or [])
        for r in rows:
            if isinstance(r, dict) and r.get("id"):
                out[r["id"]] = r
    return out


def collect_account(acct, run_dir, log=print):
    """계정 1개를 수집해 run-dir 에 저장하고 요약을 돌려준다."""
    alias = acct.get("alias") or str(acct.get("customer_id"))
    out_dir = run_dir / "accounts" / alias
    out_dir.mkdir(parents=True, exist_ok=True)
    log(f"[{alias}] 수집 시작")

    ads, group_of = fetch_ads(acct)
    live_ids = [a["nccAdId"] for a in ads if a.get("enable")]
    log(f"  소재 {len(ads)}개 (게재중 {len(live_ids)})")
    (out_dir / "ads.json").write_text(
        json.dumps({"ads": ads, "groups": group_of}, ensure_ascii=False), encoding="utf-8")

    s7_since, s7_until = window(7)
    s30_since, s30_until = window(30)
    s7 = fetch_stats(acct, live_ids, s7_since, s7_until)
    s30 = fetch_stats(acct, live_ids, s30_since, s30_until)
    log(f"  통계 7일 {len(s7)}행 / 30일 {len(s30)}행")
    (out_dir / "stats_7d.json").write_text(json.dumps(s7, ensure_ascii=False), encoding="utf-8")
    (out_dir / "stats_30d.json").write_text(json.dumps(s30, ensure_ascii=False), encoding="utf-8")

    pur = reports.fetch_purchases(acct, s30_until, 30, log=log)
    (out_dir / "purchase.json").write_text(json.dumps(pur, ensure_ascii=False), encoding="utf-8")

    return {
        "alias": alias, "ads": len(ads), "live": len(live_ids),
        "stats7": len(s7), "stats30": len(s30), "purchaseAds": len(pur),
        "window7": [s7_since.isoformat(), s7_until.isoformat()],
        "window30": [s30_since.isoformat(), s30_until.isoformat()],
    }
```

- [ ] **Step 4: 테스트를 돌려 통과를 확인한다**

Run: `.venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/test_reports.py`
Expected: PASS (7 tests — 파싱 4 + 창 3)

- [ ] **Step 5: 커밋**

```bash
git add .claude/skills/naver-ads-weekly/scripts/collect.py .claude/skills/naver-ads-weekly/scripts/test_reports.py
git commit -m "feat(naver-ads): 계정 순회 수집 + 판정창 계산"
```

---

### Task 6: CLI 진입점 — prep · run (run_ads.py)

수집과 판정을 명령으로 묶는다. 이 태스크가 끝나면 `result.json` 이 실제로 나온다.

**Files:**
- Create: `.claude/skills/naver-ads-weekly/scripts/run_ads.py`

**Interfaces:**
- Consumes: `nvad.load_accounts`, `collect.collect_account`, `ads_rules.classify`
- Produces:
  - `data_root() -> Path` — `eroomlib.config.cfg("paths.data_root")` 실패 시 `~/python_work/data`
  - `run_dir_of(name: str|None) -> Path` — `<데이터루트>/naver-ads/runs/<name 또는 오늘>`
  - `cmd_prep(args)`, `cmd_run(args)`
  - `result.json` 형식: `{"generated": "YYYY-MM-DD", "accounts": {alias: {"summary": {...}, "rules": {규칙명: [행...]}}}}`

- [ ] **Step 1: run_ads.py 를 쓴다**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""naver-ads-weekly 진입점.

    prep   전 계정 수집 → run-dir
    run    수집분으로 6개 규칙 판정 → result.json
    apply  시트 기록 + 보고서 (Task 7·8 에서 채운다)
    bids   ① 입찰 인상 (Task 9)
    prune  ⑥ 꺼진 소재 삭제 (Task 10)

주간 배치(prep/run/apply)는 광고 API 에 아무것도 쓰지 않는다.
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ads_rules
import collect
import nvad


def data_root():
    """경로를 코드에 박지 않는다 — workspace.toml 을 먼저 본다."""
    try:
        sys.path.insert(0, "/Users/choiyongsmacbook/Documents/yongtimjang_claudecode/.claude/lib")
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


def _accounts(only=None):
    accts = nvad.load_accounts()
    if only:
        accts = [a for a in accts if a.get("alias") in only]
    return accts


def cmd_prep(args):
    run_dir = run_dir_of(args.run_dir)
    accts = _accounts(args.account)
    if not accts:
        print("계정이 없다 — ~/.eroom/naver-ads.json 을 확인해라")
        return 1
    summaries = {}
    for a in accts:
        try:
            summaries[a.get("alias")] = collect.collect_account(a, run_dir)
        except Exception as e:
            print(f"[{a.get('alias')}] 수집 실패: {type(e).__name__}: {e}")
    (run_dir / "prep_summary.json").write_text(
        json.dumps(summaries, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n수집 완료 → {run_dir}")
    return 0


def cmd_run(args):
    run_dir = run_dir_of(args.run_dir)
    acc_dir = run_dir / "accounts"
    if not acc_dir.exists():
        print("수집 결과가 없다 — 먼저 prep 을 돌려라")
        return 1
    out = {"generated": date.today().isoformat(), "accounts": {}}
    for d in sorted(acc_dir.iterdir()):
        if not d.is_dir():
            continue
        try:
            adsdata = json.loads((d / "ads.json").read_text(encoding="utf-8"))
            s7 = json.loads((d / "stats_7d.json").read_text(encoding="utf-8"))
            s30 = json.loads((d / "stats_30d.json").read_text(encoding="utf-8"))
            pur = json.loads((d / "purchase.json").read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[{d.name}] 읽기 실패: {type(e).__name__}: {e}")
            continue
        rules = ads_rules.classify(adsdata["ads"], adsdata["groups"], s7, s30, pur)
        out["accounts"][d.name] = {"rules": rules}
        print(f"[{d.name}] " + " · ".join(f"{k} {len(v)}" for k, v in rules.items()))
    (run_dir / "result.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n판정 완료 → {run_dir / 'result.json'}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="네이버 검색광고 주간 관리")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("prep", "run"):
        s = sub.add_parser(name)
        s.add_argument("--run-dir", help="회차 이름(기본: 오늘 날짜)")
        s.add_argument("--account", nargs="*", help="특정 계정 alias 만")
    args = ap.parse_args()
    return {"prep": cmd_prep, "run": cmd_run}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 실제로 수집해본다**

Run: `.venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/run_ads.py prep --account cy728`
Expected: `[cy728] 수집 시작` → 소재/통계 개수 출력 → `수집 완료 → .../runs/2026-XX-XX`

- [ ] **Step 3: 판정해본다**

Run: `.venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/run_ads.py run`
Expected: `[cy728] ①노출0 N · ②썸네일교체 N · ...` 과 `result.json` 생성

- [ ] **Step 4: 실측 대조로 검산한다**

Run:
```bash
.venv/bin/python3 -c "
import json,glob
p=sorted(glob.glob('/Users/choiyongsmacbook/python_work/data/naver-ads/runs/*/result.json'))[-1]
d=json.load(open(p,encoding='utf-8'))
for a,v in d['accounts'].items():
    print(a, {k:len(x) for k,x in v['rules'].items()})
"
```
Expected: cy728 의 ②가 40~50건, ④가 25~35건 범위 (2026-08-29 실측 45·32). **크게 벗어나면 기간·하한 상수를 의심한다.**

- [ ] **Step 5: 커밋**

```bash
git add .claude/skills/naver-ads-weekly/scripts/run_ads.py
git commit -m "feat(naver-ads): prep/run CLI 진입점"
```

---

### Task 7: 총괄 보고서 (report_md.py)

시트를 열지 않고도 읽을 수 있어야 한다. **총전환·장바구니 수치는 싣지 않는다.**

**Files:**
- Create: `.claude/skills/naver-ads-weekly/scripts/report_md.py`
- Modify: `.claude/skills/naver-ads-weekly/scripts/run_ads.py` (`cmd_apply` 추가, `main()` 의 서브커맨드에 `apply` 추가)

**Interfaces:**
- Consumes: `result.json`
- Produces: `build_report(result: dict, top_n: int = 20) -> str`

- [ ] **Step 1: report_md.py 를 쓴다**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""주간 총괄 보고서(마크다운).

보고서에는 구매완료 기준 숫자만 싣는다(2026-08-28 용팀장).
총전환·장바구니는 착시라 나란히 놓으면 헷갈리기만 한다.
"""

TOP_N = 20   # ② 는 주당 이만큼만 처리한다


def _table(rows, cols, limit=None):
    """(헤더, 접근키) 목록으로 마크다운 표를 만든다."""
    rows = rows[:limit] if limit else rows
    if not rows:
        return "_해당 없음_\n"
    head = "| " + " | ".join(h for h, _ in cols) + " |\n"
    sep = "|" + "|".join("---" for _ in cols) + "|\n"
    body = ""
    for r in rows:
        cells = []
        for _, k in cols:
            v = r.get(k, "")
            cells.append(f"{v:,}" if isinstance(v, int) else (f"{v:.2f}" if isinstance(v, float) else str(v)))
        body += "| " + " | ".join(cells) + " |\n"
    return head + sep + body


def build_report(result, top_n=TOP_N):
    """result.json 을 사람이 읽는 보고서로 바꾼다."""
    lines = [f"# 네이버 광고 주간 보고 — {result.get('generated','')}\n"]

    # 계정 총괄 — 구매완료 기준만
    lines.append("## 총괄\n")
    lines.append("| 계정 | 게재중 | 광고비 | 구매완료 매출 | ROAS | 노출0 | 썸네일교체 | 구매0 | 효자 |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    tot_cost = tot_pur = 0
    for alias, v in result.get("accounts", {}).items():
        r = v["rules"]
        cost = sum(x.get("cost", 0) for x in r["②썸네일교체"] + r["③원인분석"] + r["④효자후보"] + r["⑤효자확정"])
        pur = sum(x.get("purAmt", 0) for x in r["⑤효자확정"])
        tot_cost += cost
        tot_pur += pur
        roas = f"{pur / cost * 100:.0f}%" if cost else "—"
        lines.append(f"| {alias} | — | {cost:,}원 | {pur:,}원 | {roas} | "
                     f"{len(r['①노출0'])} | {len(r['②썸네일교체'])} | {len(r['③원인분석'])} | {len(r['⑤효자확정'])} |")
    roas_all = f"{tot_pur / tot_cost * 100:.0f}%" if tot_cost else "—"
    lines.append(f"| **합계** | | **{tot_cost:,}원** | **{tot_pur:,}원** | **{roas_all}** | | | | |\n")
    lines.append("> 매출은 **구매완료 기준**이다. 장바구니는 세지 않는다.\n")

    for alias, v in result.get("accounts", {}).items():
        r = v["rules"]
        lines.append(f"\n## {alias}\n")

        lines.append(f"### ① 노출 0 — 입찰 인상 대상 {len(r['①노출0'])}건\n")
        lines.append("`bids --commit` 으로 실행한다. 그룹입찰 상품은 개별 전환 후 `그룹기본가+10원`으로 시작한다.\n")
        lines.append(_table(r["①노출0"], [("상품", "title"), ("광고그룹", "adGroup"),
                                          ("현재입찰", "bid"), ("그룹입찰따름", "useGroupBid")]))

        lines.append(f"\n### ② 썸네일 교체 — {len(r['②썸네일교체'])}건 중 상위 {top_n}건\n")
        lines.append("노출 100회 이상인데 CTR 1% 미만. 노출 많은 순.\n")
        lines.append(_table(r["②썸네일교체"], [("상품", "title"), ("노출", "imp"), ("클릭", "clk"),
                                              ("CTR", "ctr"), ("순위", "rank"), ("상품ID", "mallProductId")],
                            limit=top_n))

        lines.append(f"\n### ③ 클릭 20+ 인데 구매완료 0 — {len(r['③원인분석'])}건\n")
        lines.append(_table(r["③원인분석"], [("상품", "title"), ("클릭", "clk"), ("CTR", "ctr"),
                                            ("광고비", "cost")]))

        lines.append(f"\n### ④ CTR 2% 이상 — 효자 후보 {len(r['④효자후보'])}건\n")
        lines.append(_table(r["④효자후보"], [("상품", "title"), ("노출", "imp"), ("CTR", "ctr"),
                                            ("순위", "rank")], limit=top_n))

        lines.append(f"\n### ⑤ 구매완료 발생 — 효자 확정 {len(r['⑤효자확정'])}건\n")
        lines.append(_table(r["⑤효자확정"], [("상품", "title"), ("구매", "purCnt"), ("매출", "purAmt"),
                                            ("광고비", "cost")]))

        off = len(r["⑥삭제대상"])
        lines.append(f"\n### ⑥ 꺼진 소재 — {off}건\n")
        if off:
            lines.append(f"`prune --commit` 으로 삭제한다(백업 선행). "
                         f"**꺼진 사유가 `AD_ABNORMAL_INTERLOCK`(연동 비정상)이면 원인 규명이 먼저다** — "
                         f"매주 삭제만 하면 광고 소재가 줄어들기만 한다.\n")
        else:
            lines.append("_해당 없음_\n")

    return "\n".join(lines)
```

- [ ] **Step 2: run_ads.py 에 apply 를 붙인다**

`run_ads.py` 의 `import` 에 `import report_md` 를 추가하고, `cmd_run` 아래에 다음을 넣는다:

```python
def cmd_apply(args):
    run_dir = run_dir_of(args.run_dir)
    rp = run_dir / "result.json"
    if not rp.exists():
        print("판정 결과가 없다 — 먼저 run 을 돌려라")
        return 1
    result = json.loads(rp.read_text(encoding="utf-8"))
    md = report_md.build_report(result)
    out = run_dir / "report.md"
    out.write_text(md, encoding="utf-8")
    print(f"보고서 → {out}")
    return 0
```

그리고 `main()` 의 `for name in ("prep", "run"):` 를 `for name in ("prep", "run", "apply"):` 로 바꾸고,
디스패치 dict 를 `{"prep": cmd_prep, "run": cmd_run, "apply": cmd_apply}` 로 바꾼다.

- [ ] **Step 3: 보고서를 만들어 눈으로 본다**

Run: `.venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/run_ads.py apply`
Expected: `보고서 → .../report.md`

Run: `head -40 $(ls -td /Users/choiyongsmacbook/python_work/data/naver-ads/runs/*/ | head -1)report.md`
Expected: 총괄 표에 ROAS 가 뜨고, **장바구니·총전환이라는 낱말이 없어야 한다**

- [ ] **Step 4: 금칙어를 확인한다**

Run:
```bash
grep -c "장바구니\|총전환\|add_to_cart" $(ls -td /Users/choiyongsmacbook/python_work/data/naver-ads/runs/*/ | head -1)report.md
```
Expected: `0`

- [ ] **Step 5: 커밋**

```bash
git add .claude/skills/naver-ads-weekly/scripts/report_md.py .claude/skills/naver-ads-weekly/scripts/run_ads.py
git commit -m "feat(naver-ads): 주간 총괄 보고서(구매완료 기준)"
```

---

### Task 8: 구글시트 원장 (sheets_out.py)

원장은 시트다. 회차가 쌓여도 과거를 잃지 않아야 한다.

**Files:**
- Create: `.claude/skills/naver-ads-weekly/scripts/sheets_out.py`
- Modify: `.claude/skills/naver-ads-weekly/scripts/run_ads.py` (`cmd_apply` 에 시트 기록 추가, `--sheet`·`--no-sheet` 인자)

**Interfaces:**
- Consumes: `result.json`, `gws` CLI
- Produces:
  - `rows_for(rule_name: str, rows: list[dict], alias: str, generated: str) -> list[list]`
  - `write_sheet(sheet_id: str, result: dict, log=print) -> None`

- [ ] **Step 1: sheets_out.py 를 쓴다**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""구글시트 원장 기록 — gws CLI 를 subprocess 로 부른다.

탭 구성: 00_총괄 / ①노출0 / ②썸네일교체 / ③원인분석 / ④효자후보 / ⑤효자확정 / 이력
회차마다 append 한다 — 덮어쓰면 과거 회차를 잃는다.
"""
import json
import subprocess

# 규칙별 열 정의 (헤더, 접근키)
COLS = {
    "①노출0": [("회차", None), ("계정", None), ("상품", "title"), ("광고그룹", "adGroup"),
               ("현재입찰", "bid"), ("그룹입찰따름", "useGroupBid"), ("소재ID", "adId")],
    "②썸네일교체": [("회차", None), ("계정", None), ("상품", "title"), ("노출", "imp"), ("클릭", "clk"),
                 ("CTR", "ctr"), ("순위", "rank"), ("스토어상품ID", "mallProductId"), ("소재ID", "adId")],
    "③원인분석": [("회차", None), ("계정", None), ("상품", "title"), ("노출", "imp"), ("클릭", "clk"),
                ("CTR", "ctr"), ("광고비", "cost"), ("스토어상품ID", "mallProductId")],
    "④효자후보": [("회차", None), ("계정", None), ("상품", "title"), ("노출", "imp"), ("CTR", "ctr"),
                ("순위", "rank"), ("스토어상품ID", "mallProductId")],
    "⑤효자확정": [("회차", None), ("계정", None), ("상품", "title"), ("구매수", "purCnt"),
                ("구매매출", "purAmt"), ("광고비", "cost"), ("스토어상품ID", "mallProductId")],
}


def rows_for(rule_name, rows, alias, generated):
    """규칙 1개를 시트 행 목록으로 바꾼다. 첫 두 열은 회차·계정이다."""
    cols = COLS.get(rule_name)
    if not cols:
        return []
    out = []
    for r in rows:
        line = []
        for _, key in cols:
            if key is None:
                line.append(generated if not line else alias)
            else:
                v = r.get(key, "")
                line.append("" if v is None else v)
        out.append(line)
    return out


def _gws(args_json, service="sheets", resource="spreadsheets.values", method="append"):
    """gws CLI 호출. 실패해도 배치를 죽이지 않는다."""
    cmd = ["gws", service, *resource.split("."), method, "--params", json.dumps(args_json, ensure_ascii=False)]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if p.returncode != 0:
            return False, (p.stderr or p.stdout)[:300]
        return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def write_sheet(sheet_id, result, log=print):
    """전 계정·전 규칙을 각 탭에 append 한다."""
    generated = result.get("generated", "")
    for rule_name, cols in COLS.items():
        all_rows = []
        for alias, v in result.get("accounts", {}).items():
            all_rows.extend(rows_for(rule_name, v["rules"].get(rule_name, []), alias, generated))
        if not all_rows:
            continue
        ok, err = _gws({
            "spreadsheetId": sheet_id,
            "range": f"{rule_name}!A1",
            "valueInputOption": "USER_ENTERED",
            "insertDataOption": "INSERT_ROWS",
            "body": {"values": all_rows},
        })
        log(f"  {rule_name:<12} {len(all_rows):>4}행 {'✓' if ok else '✗ ' + err}")
```

- [ ] **Step 2: run_ads.py 의 cmd_apply 에 시트 기록을 붙인다**

`import sheets_out` 를 추가하고, `cmd_apply` 의 `print(f"보고서 → {out}")` 앞에 다음을 넣는다:

```python
    if args.sheet and not args.no_sheet:
        print("시트 기록:")
        sheets_out.write_sheet(args.sheet, result)
```

`main()` 의 apply 서브파서에만 인자를 추가한다 — `for name in (...)` 루프 뒤에:

```python
    ap_apply = sub.choices["apply"]
    ap_apply.add_argument("--sheet", help="구글시트 ID (없으면 마크다운만)")
    ap_apply.add_argument("--no-sheet", action="store_true", help="원장 탭 쓰기만 막는다")
```

> `--no-sheet` 는 **원장 탭만** 막는다. 현황판·이력 쓰기를 같이 묶지 않는다
> (스킬 계약 §`--no-sheet` 로 현황판을 막지 않는다 — 옵션정리에서 두 번 밟은 사고).

- [ ] **Step 3: 행 변환을 직접 확인한다**

Run:
```bash
.venv/bin/python3 -c "
import sys; sys.path.insert(0,'.claude/skills/naver-ads-weekly/scripts')
import sheets_out as S
rows = S.rows_for('②썸네일교체', [{'title':'북카트','imp':27176,'clk':61,'ctr':0.22,'rank':8.0,'mallProductId':'12625037255','adId':'nad-1'}], 'cy728', '2026-08-29')
print(rows)
assert rows[0][0]=='2026-08-29' and rows[0][1]=='cy728' and rows[0][7]=='12625037255'
print('OK')
"
```
Expected: 행 출력 후 `OK`

- [ ] **Step 4: 시트에 실제로 써본다**

먼저 시트를 하나 만들고 탭 6개(`00_총괄`·`①노출0`·`②썸네일교체`·`③원인분석`·`④효자후보`·`⑤효자확정`)를 준비한 뒤:

Run: `.venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/run_ads.py apply --sheet <시트ID>`
Expected: 각 규칙별 `✓` 와 행 수

- [ ] **Step 5: 커밋**

```bash
git add .claude/skills/naver-ads-weekly/scripts/sheets_out.py .claude/skills/naver-ads-weekly/scripts/run_ads.py
git commit -m "feat(naver-ads): 구글시트 원장 기록"
```

---

### Task 9: 입찰 인상 (bids.py)

**돈이 나가는 유일한 곳이다.** `--commit` 없이는 아무것도 쓰지 않는다.

**Files:**
- Create: `.claude/skills/naver-ads-weekly/scripts/bids.py`
- Test: `.claude/skills/naver-ads-weekly/scripts/test_bids.py`
- Modify: `.claude/skills/naver-ads-weekly/scripts/run_ads.py` (`cmd_bids` 추가)

**Interfaces:**
- Consumes: `nvad.call`, `ledger.bid_decision`, `ledger.record_raise`, `result.json`
- Produces:
  - `plan_raise(row: dict, ledger_data: dict) -> dict` — `{"adId","action","from","to","reason"}`
  - `apply_raise(acct, ad_obj: dict, new_bid: int) -> tuple[bool, str]`
  - `run_bids(acct, run_dir, rows, commit: bool, log=print) -> dict`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`test_bids.py`:

```python
#!/usr/bin/env python3
"""입찰 인상 가드레일 회귀 테스트 — 네트워크 없이 돈다.

여기서 틀리면 실제 광고비가 잘못 나간다. 가장 조심할 곳이다.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bids  # noqa: E402


def row(ad_id="a", bid=100, use_group=False, group_bid=70):
    return {"adId": ad_id, "bid": bid, "useGroupBid": use_group, "groupBid": group_bid, "title": "상품"}


class TestPlanRaise(unittest.TestCase):
    def test_개별입찰은_현재값에_10원(self):
        p = bids.plan_raise(row(bid=120, use_group=False), {})
        self.assertEqual((p["action"], p["from"], p["to"]), ("인상", 120, 130))

    def test_그룹입찰은_그룹기본가에_10원이다(self):
        # 잠자던 bidAmt 를 쓰면 올리려다 내리게 된다. 실측: 그룹 70 / 잠자던 값 50
        p = bids.plan_raise(row(bid=70, use_group=True, group_bid=70), {})
        self.assertEqual((p["action"], p["from"], p["to"]), ("인상", 70, 80))

    def test_상한_200원을_넘기지_않는다(self):
        p = bids.plan_raise(row(bid=195), {})
        self.assertEqual(p["action"], "상한도달")
        self.assertIsNone(p["to"])

    def test_정확히_200원이면_더_올리지_않는다(self):
        self.assertEqual(bids.plan_raise(row(bid=200), {})["action"], "상한도달")

    def test_3주_연속_실패면_중단한다(self):
        led = {"a": {"raises": [], "streak": 3, "capped": False}}
        self.assertEqual(bids.plan_raise(row(), led)["action"], "연속실패중단")

    def test_입찰가를_모르면_건드리지_않는다(self):
        p = bids.plan_raise(row(bid=None, use_group=True, group_bid=None), {})
        self.assertEqual(p["action"], "입찰가불명")
        self.assertIsNone(p["to"])


class TestBody(unittest.TestCase):
    def test_전환시_useGroupBidAmt_를_False_로_바꾼다(self):
        ad_obj = {"nccAdId": "a", "adAttr": {"bidAmt": 50, "useGroupBidAmt": True}}
        body = bids.build_body(ad_obj, 80)
        self.assertEqual(body["adAttr"], {"bidAmt": 80, "useGroupBidAmt": False})

    def test_원본_객체를_변조하지_않는다(self):
        ad_obj = {"nccAdId": "a", "adAttr": {"bidAmt": 50, "useGroupBidAmt": True}}
        bids.build_body(ad_obj, 80)
        self.assertEqual(ad_obj["adAttr"], {"bidAmt": 50, "useGroupBidAmt": True})

    def test_다른_필드는_그대로_보낸다(self):
        ad_obj = {"nccAdId": "a", "nccAdgroupId": "g", "type": "SHOPPING_PRODUCT_AD",
                  "adAttr": {"bidAmt": 120, "useGroupBidAmt": False}}
        body = bids.build_body(ad_obj, 130)
        self.assertEqual(body["nccAdgroupId"], "g")
        self.assertEqual(body["type"], "SHOPPING_PRODUCT_AD")


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `.venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/test_bids.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'bids'`

- [ ] **Step 3: bids.py 를 쓴다**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""① 노출 0 소재의 입찰가를 10원 올린다. 이 스킬에서 돈이 나가는 유일한 곳이다.

가드레일(2026-08-28~29 확정):
  1. enable=true 인 소재만            — 꺼진 광고 입찰가를 올리지 않는다
  2. 7일 노출 0 만                    — 30일 노출0 은 포기 후보이지 인상 대상이 아니다
  3. 그룹입찰이면 개별 전환 + 그룹기본가+10원
  4. 상한 200원 — 도달분은 상한도달-무노출 리스트
  5. 3주 연속 인상 실패면 중단
  6. 실행 전 원본 adAttr 전량 백업
  7. 결과를 이력에 기록
쓰기 방법(실측): PUT /ncc/ads/{adId}?fields=adAttr, body = 조회한 소재 객체 전체
"""
import json
from datetime import date

import ledger
import nvad


def plan_raise(row, ledger_data):
    """이 소재를 어떻게 할지 정한다. 네트워크를 타지 않는다."""
    # 그룹입찰을 따르는 상품은 '잠자던 bidAmt' 가 아니라 그룹 기본가가 출발점이다
    base = row.get("groupBid") if row.get("useGroupBid") else row.get("bid")
    action, new = ledger.bid_decision(ledger_data, row["adId"], base)
    return {"adId": row["adId"], "title": row.get("title", ""), "action": action,
            "from": base, "to": new, "useGroupBid": bool(row.get("useGroupBid"))}


def build_body(ad_obj, new_bid):
    """PUT 본문. 조회한 소재 객체 전체에 adAttr 만 갈아끼운다.

    useGroupBidAmt 는 False 로 바꾼다 — 개별 입찰가를 적용하려면 필수다.
    가역적이므로(실측 확인) 되돌릴 수 있다.
    """
    body = dict(ad_obj)
    body["adAttr"] = dict(ad_obj.get("adAttr") or {})
    body["adAttr"]["bidAmt"] = new_bid
    body["adAttr"]["useGroupBidAmt"] = False
    return body


def apply_raise(acct, ad_obj, new_bid):
    """실제로 입찰가를 바꾼다. (성공여부, 메시지)."""
    st, res = nvad.call(acct, "PUT", f"/ncc/ads/{ad_obj['nccAdId']}",
                        params={"fields": "adAttr"}, body=build_body(ad_obj, new_bid))
    if st in (200, 201):
        return True, ""
    return False, f"{st} {str(res)[:150]}"


def run_bids(acct, run_dir, rows, commit=False, log=print):
    """규칙 ① 대상 전체를 처리한다. commit 이 False 면 계획만 세운다."""
    alias = acct.get("alias") or str(acct.get("customer_id"))
    led_path = run_dir.parent.parent / "ledger" / f"{alias}.json"
    led = ledger.load(led_path)

    # 현재 소재 상태를 다시 조회한다 — 수집 이후 바뀌었을 수 있다
    ad_by_id = {}
    ads_path = run_dir / "accounts" / alias / "ads.json"
    try:
        for a in json.loads(ads_path.read_text(encoding="utf-8"))["ads"]:
            ad_by_id[a["nccAdId"]] = a
    except Exception as e:
        log(f"[{alias}] 소재 읽기 실패: {type(e).__name__}: {e}")
        return {}

    plans = [plan_raise(r, led) for r in rows]
    counts = {}
    for p in plans:
        counts[p["action"]] = counts.get(p["action"], 0) + 1

    log(f"[{alias}] 대상 {len(plans)}건 → " + " · ".join(f"{k} {v}" for k, v in counts.items()))
    for p in plans[:10]:
        log(f"    {p['action']:<10} {str(p['from']):>4}→{str(p['to']):<4} {p['title'][:30]}")
    if len(plans) > 10:
        log(f"    … 외 {len(plans)-10}건")

    if not commit:
        log("  (dry-run — --commit 을 주면 실제로 바꾼다)")
        return {"plans": plans, "counts": counts, "committed": 0}

    # 백업 먼저 — 실행 전 원본 adAttr 전량
    bk = run_dir / f"before_bids_{alias}.json"
    bk.write_text(json.dumps(
        {p["adId"]: (ad_by_id.get(p["adId"], {}).get("adAttr")) for p in plans if p["action"] == "인상"},
        ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"  백업 → {bk.name}")

    today = date.today().isoformat()
    ok = fail = 0
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
    ledger.save(led_path, led)
    log(f"  인상 완료 {ok}건 / 실패 {fail}건 · 이력 → {led_path}")
    return {"plans": plans, "counts": counts, "committed": ok, "failed": fail}
```

- [ ] **Step 4: 테스트를 돌려 통과를 확인한다**

Run: `.venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/test_bids.py`
Expected: PASS (9 tests)

- [ ] **Step 5: run_ads.py 에 bids 를 붙인다**

`import bids` 추가 후:

```python
def cmd_bids(args):
    run_dir = run_dir_of(args.run_dir)
    rp = run_dir / "result.json"
    if not rp.exists():
        print("판정 결과가 없다 — 먼저 run 을 돌려라")
        return 1
    result = json.loads(rp.read_text(encoding="utf-8"))
    accts = {a.get("alias"): a for a in _accounts(args.account)}
    for alias, v in result.get("accounts", {}).items():
        acct = accts.get(alias)
        if not acct:
            continue
        bids.run_bids(acct, run_dir, v["rules"]["①노출0"], commit=args.commit)
    return 0
```

`main()` 에 서브파서를 추가한다:

```python
    s = sub.add_parser("bids")
    s.add_argument("--run-dir")
    s.add_argument("--account", nargs="*")
    s.add_argument("--commit", action="store_true", help="실제로 입찰가를 바꾼다")
```

디스패치 dict 에 `"bids": cmd_bids` 를 추가한다.

- [ ] **Step 6: dry-run 으로 확인한다**

Run: `.venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/run_ads.py bids`
Expected: `[cy728] 대상 N건 → 인상 N · …` 과 `(dry-run …)` 메시지. **광고는 하나도 안 바뀐다.**

- [ ] **Step 7: 커밋**

```bash
git add .claude/skills/naver-ads-weekly/scripts/bids.py .claude/skills/naver-ads-weekly/scripts/test_bids.py .claude/skills/naver-ads-weekly/scripts/run_ads.py
git commit -m "feat(naver-ads): 입찰 인상 + 가드레일 7종"
```

---

### Task 10: 꺼진 소재 삭제 (prune.py)

되돌릴 수 없다. **백업 없이는 한 건도 지우지 않는다.**

**Files:**
- Create: `.claude/skills/naver-ads-weekly/scripts/prune.py`
- Modify: `.claude/skills/naver-ads-weekly/scripts/run_ads.py` (`cmd_prune` 추가)

**Interfaces:**
- Consumes: `nvad.call`, `ads.json`
- Produces:
  - `backup_paused(acct, ads: list[dict], out_dir) -> Path`
  - `delete_ads(acct, ad_ids: list[str], progress_path, log=print) -> dict`
  - `run_prune(acct, run_dir, commit: bool, log=print) -> dict`

- [ ] **Step 1: prune.py 를 쓴다**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""⑥ 꺼진 소재(enable=false) 삭제. 되돌릴 수 없으므로 백업이 선행 조건이다.

2026-08-29 첫 회차로 5,062건을 삭제했다(실패 0). 꺼진 사유는 거의 전부
AD_ABNORMAL_INTERLOCK(연동 비정상) — 사용자가 끈 게 아니라 시스템 자동 일시중지다.
원인은 미규명이고 지금도 발생 중이라, 신규 발생 건수를 매주 보고해야 한다.
"""
import json
import time
from collections import Counter
from datetime import date

import nvad

# 재등록에 필요한 최소 필드 + 원본 통째로
BACKUP_KEYS = ("nccAdId", "nccAdgroupId", "referenceKey", "type", "adAttr",
               "status", "statusReason", "inspectStatus", "regTm", "editTm")


def backup_paused(acct, ads, out_dir):
    """꺼진 소재 전량을 백업한다. referenceKey·mallProductId 가 있어야 재등록이 가능하다."""
    alias = acct.get("alias") or str(acct.get("customer_id"))
    off = [a for a in ads if not a.get("enable")]
    rows = []
    for a in off:
        rd = a.get("referenceData") or {}
        row = {k: a.get(k) for k in BACKUP_KEYS}
        row.update({
            "mallProductId": rd.get("mallProductId"),
            "productTitle": rd.get("productTitle"),
            "referenceData": rd,
        })
        rows.append(row)
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"paused_{alias}_{date.today().isoformat()}.json"
    p.write_text(json.dumps({"account": alias, "customer_id": acct.get("customer_id"),
                             "count": len(rows), "ads": rows}, ensure_ascii=False, indent=1),
                 encoding="utf-8")
    return p


def delete_ads(acct, ad_ids, progress_path, log=print):
    """소재를 삭제한다. 진행 파일로 재개 가능하고, 404 는 이미 없는 것으로 성공 처리한다."""
    done = set()
    if progress_path.exists():
        for line in progress_path.read_text(encoding="utf-8").splitlines():
            try:
                done.add(json.loads(line)["nccAdId"])
            except Exception:
                pass
    todo = [i for i in ad_ids if i not in done]
    log(f"  삭제 대상 {len(todo)}건 (이미 처리 {len(done)})")

    stat = Counter()
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    with progress_path.open("a", encoding="utf-8") as fp:
        for n, aid in enumerate(todo, 1):
            for attempt in range(4):
                st, res = nvad.call(acct, "DELETE", f"/ncc/ads/{aid}")
                if st in (200, 204, 404):
                    stat["ok" if st != 404 else "already"] += 1
                    fp.write(json.dumps({"nccAdId": aid, "status": st}) + "\n")
                    break
                if st in (429, 500, 502, 503, 0):
                    time.sleep(2 * (attempt + 1))
                    continue
                stat[f"err{st}"] += 1
                fp.write(json.dumps({"nccAdId": aid, "status": st, "err": str(res)[:200]},
                                    ensure_ascii=False) + "\n")
                break
            else:
                stat["retry_exhausted"] += 1
            if n % 250 == 0:
                fp.flush()
                log(f"    {n}/{len(todo)} {dict(stat)}")
            time.sleep(0.08)   # 초당 12건 — 5,062건 실측에서 429 가 없었다
    return dict(stat)


def run_prune(acct, run_dir, commit=False, log=print):
    """계정 1개의 꺼진 소재를 백업하고 삭제한다."""
    alias = acct.get("alias") or str(acct.get("customer_id"))
    try:
        ads = json.loads((run_dir / "accounts" / alias / "ads.json").read_text(encoding="utf-8"))["ads"]
    except Exception as e:
        log(f"[{alias}] 소재 읽기 실패: {type(e).__name__}: {e}")
        return {}

    off = [a for a in ads if not a.get("enable")]
    reasons = Counter(a.get("statusReason") or "?" for a in off)
    log(f"[{alias}] 꺼진 소재 {len(off)}건 · 사유 {dict(reasons.most_common(3))}")
    interlock = reasons.get("AD_ABNORMAL_INTERLOCK", 0)
    if interlock:
        log(f"  ⚠ 연동 비정상 {interlock}건 — 원인 미규명. 매주 삭제만 하면 소재가 줄어들기만 한다")

    if not off:
        return {"paused": 0, "reasons": dict(reasons)}

    backup_root = run_dir.parent.parent / "paused-backup"
    bk = backup_paused(acct, ads, backup_root)
    log(f"  백업 {len(off)}건 → {bk}")

    if not commit:
        log("  (dry-run — --commit 을 주면 실제로 지운다)")
        return {"paused": len(off), "reasons": dict(reasons), "backup": str(bk), "deleted": 0}

    stat = delete_ads(acct, [a["nccAdId"] for a in off],
                      backup_root / f"delete_progress_{alias}.jsonl", log=log)
    log(f"  삭제 결과 {stat}")
    return {"paused": len(off), "reasons": dict(reasons), "backup": str(bk), "result": stat}
```

- [ ] **Step 2: run_ads.py 에 prune 을 붙인다**

`import prune` 추가 후:

```python
def cmd_prune(args):
    run_dir = run_dir_of(args.run_dir)
    for a in _accounts(args.account):
        prune.run_prune(a, run_dir, commit=args.commit)
    return 0
```

`main()` 에:

```python
    s = sub.add_parser("prune")
    s.add_argument("--run-dir")
    s.add_argument("--account", nargs="*")
    s.add_argument("--commit", action="store_true", help="실제로 삭제한다(되돌릴 수 없다)")
```

디스패치 dict 에 `"prune": cmd_prune` 를 추가한다.

- [ ] **Step 3: dry-run 으로 확인한다**

Run: `.venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/run_ads.py prune`
Expected: 꺼진 소재 개수·사유 분포·백업 경로 출력 후 `(dry-run …)`. **아무것도 안 지운다.**

- [ ] **Step 4: 백업 파일이 재등록 가능한지 확인한다**

Run:
```bash
.venv/bin/python3 -c "
import json,glob
fs=glob.glob('/Users/choiyongsmacbook/python_work/data/naver-ads/paused-backup/paused_*.json')
if not fs: print('꺼진 소재 없음 — 정상'); raise SystemExit
d=json.load(open(sorted(fs)[-1],encoding='utf-8'))
n=len(d['ads']); k=sum(1 for a in d['ads'] if a.get('referenceKey') and a.get('mallProductId'))
print(f'{n}건 중 재등록키 보유 {k}건'); assert n==k
"
```
Expected: 전량 보유 (꺼진 소재가 0이면 "정상" 출력)

- [ ] **Step 5: 커밋**

```bash
git add .claude/skills/naver-ads-weekly/scripts/prune.py .claude/skills/naver-ads-weekly/scripts/run_ads.py
git commit -m "feat(naver-ads): 꺼진 소재 삭제(백업 선행·재개 가능)"
```

---

### Task 11: SKILL.md + 판정기준 문서

스킬이 자동 트리거되고, 규칙 전문이 한 곳에만 있어야 한다.

**Files:**
- Create: `.claude/skills/naver-ads-weekly/SKILL.md`
- Create: `.claude/skills/naver-ads-weekly/references/규칙-판정기준.md`

- [ ] **Step 1: references/규칙-판정기준.md 를 쓴다**

규칙 전문·가드레일·전환 함정을 여기 한 벌만 둔다. SKILL.md 는 요약 + 링크다(두 벌로 적으면 반드시 어긋난다).

내용은 스펙 `docs/superpowers/specs/2026-08-27-naver-ads-weekly-design.md` 의 §2.3(전환 함정)·§2.4(노출0 역산)·§쟁점 C·D(기간·하한)·§4.2(가드레일 7종)·§2.11(삭제)을 옮긴다. 특히 다음 세 줄은 **반드시 포함한다**:

```markdown
- `/stats` 의 `convAmt`·`ccnt` 는 장바구니 포함 총전환이다. 구매완료는 `AD_CONVERSION` 리포트의 `purchase` 유형만.
- `salesAmt` 는 매출이 아니라 광고비다.
- 그룹입찰 상품을 개별 전환할 때 출발점은 `잠자던 bidAmt` 가 아니라 `그룹 기본입찰가` 다. 헷갈리면 올리려다 내린다.
```

- [ ] **Step 2: SKILL.md 를 쓴다**

```markdown
---
name: naver-ads-weekly
description: 네이버 검색광고 여러 계정을 주 1회 훑어 노출0·저CTR·구매0·효자상품을 분류하고 총괄 보고서를 만든다. 입찰가 인상과 꺼진 소재 삭제는 승인 후 별도 명령으로 실행한다. "광고 주간보고", "광고 성과 정리", "노출 안 되는 상품", "입찰가 올려줘", "꺼진 광고 정리", "광고 리포트", "썸네일 바꿀 상품 뽑아줘" 등을 언급하면 자동 실행.
---

# 네이버 광고 주간 관리

## 왜 필요한가

여러 광고계정을 눈으로 훑으면 **구매완료가 아니라 장바구니를 매출로 착각한다.**
`/stats` 의 전환값은 장바구니가 섞여 있어 실측에서 14배 부풀어 보였다(ROAS 3,844% vs 실제 275%).

## 흐름

```bash
P=.venv/bin/python3
S=.claude/skills/naver-ads-weekly/scripts/run_ads.py

$P $S prep                      # 전 계정 수집 (쓰기 0)
$P $S run                       # 6개 규칙 판정 → result.json
$P $S apply --sheet <시트ID>     # 시트 원장 + report.md

# 여기서 용팀장이 ①번 리스트를 확인한 뒤
$P $S bids                      # dry-run — 뭘 올릴지만 보여준다
$P $S bids --commit             # 실제 인상
$P $S prune --commit            # 꺼진 소재 삭제 (백업 선행)
```

**`prep`·`run`·`apply` 는 광고 API 에 아무것도 쓰지 않는다.**
`bids`·`prune` 만 쓰고, 둘 다 `--commit` 없이는 dry-run 이다.

## 6개 규칙

| # | 조건 | 기간 | 결과 |
|---|---|---|---|
| ① | 노출 0 (게재중만) | 7일 | 입찰 +10원 (`bids`) |
| ② | 노출 100+ & CTR<1% | 30일 | 썸네일 교체 리스트 (상위 20건) |
| ③ | 클릭 20+ & 구매완료 0 | 30일 | 원인분석 리스트 |
| ④ | 노출 100+ & CTR≥2% | 30일 | 효자 후보 |
| ⑤ | 구매완료 발생 | 30일 | 효자 확정 |
| ⑥ | `enable=false` | — | 삭제 (`prune`, 백업 선행) |

전문: [`references/규칙-판정기준.md`](references/규칙-판정기준.md)

## 반드시 지킬 것 3가지

1. **`/stats` 의 `convAmt`·`ccnt` 를 매출로 쓰지 않는다** — 장바구니 포함이다. 구매완료는 `AD_CONVERSION` 리포트의 `purchase` 유형만.
2. **`salesAmt` 는 광고비다** — 매출이 아니다.
3. **그룹입찰 상품의 인상 출발점은 그룹 기본입찰가다** — 잠자던 `bidAmt` 를 쓰면 올리려다 내린다.

## 자격증명

`~/.eroom/naver-ads.json` (권한 600, git 밖)

```json
{"accounts":[{"alias":"cy728","customer_id":"...","api_key":"...","secret_key":"..."}]}
```

계정마다 광고플랫폼 → 도구 → **API 사용 관리** 에서 3종을 발급받아 블록을 추가한다.

## 테스트

```bash
for t in nvad reports ads_rules ledger bids; do
  .venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/test_$t.py
done
```

전부 네트워크 없이 돈다.

## 알려진 미해결

**`AD_ABNORMAL_INTERLOCK`(연동 비정상) 으로 소재가 계속 자동 정지된다.**
2026-08-29 에 5,062건을 삭제했지만 원인은 규명되지 않았고 지금도 발생 중이다.
`prune` 이 매주 신규 발생 건수를 보고한다 — **급증하면 삭제보다 원인 규명이 먼저다.**
```

- [ ] **Step 3: 전체 테스트를 한 번에 돌린다**

Run:
```bash
for t in nvad reports ads_rules ledger bids; do
  echo "=== $t ==="
  .venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/test_$t.py 2>&1 | tail -3
done
```
Expected: 5개 전부 `OK`

- [ ] **Step 4: 전체 흐름을 처음부터 돌린다**

Run:
```bash
P=.venv/bin/python3; S=.claude/skills/naver-ads-weekly/scripts/run_ads.py
$P $S prep && $P $S run && $P $S apply && $P $S bids && $P $S prune
```
Expected: 수집 → 판정 → 보고서 → bids dry-run → prune dry-run 이 에러 없이 통과. **광고는 하나도 안 바뀐다.**

- [ ] **Step 5: 커밋**

```bash
git add .claude/skills/naver-ads-weekly/
git commit -m "feat(naver-ads): SKILL.md + 규칙 판정기준 문서"
```

---

## Self-Review 결과

**1. 스펙 커버리지**

| 스펙 요구 | 태스크 |
|---|---|
| §2.1 인증·서명 | Task 1 |
| §2.2 입찰가 쓰기·가역성 | Task 9 |
| §2.3 전환 함정 (`purchase` 만) | Task 2 |
| §2.4 노출0 역산 | Task 3 (`classify` 의 `①`) |
| §2.5 리포트 D-2 지연 | Task 5 (`window`) |
| §2.6 `mallProductId` 전달 | Task 3 (`ad_info`) · Task 8 (시트 열) |
| §2.7 계정 편차 (SHOPPING 복수·enable) | Task 5 (`fetch_ads`) · Task 3 (`live_ads`) |
| §2.8 짧은 표본 함정 (30일 고정) | Task 5 (`window(30)`) |
| §2.10 호출 비용 (100개 청크) | Task 1 (`chunks`) · Task 5 |
| §2.11 꺼진 소재 삭제·백업 | Task 10 |
| §쟁점 A 그룹입찰 전환 | Task 9 (`plan_raise`·`build_body`) |
| §쟁점 B 상한 200·3주 연속 | Task 4 |
| §쟁점 C·D 기간·노출하한 | Task 3 (상수) · Task 5 |
| §쟁점 E 시트+마크다운 | Task 7 · Task 8 |
| §5 총전환 미표기 | Task 7 (Step 4 금칙어 확인) |
| §4.1 진입점 5개 | Task 6 · 7 · 9 · 10 |

**빠진 것 없음.** §2.12(상품 매칭)·§2.13(썸네일)은 `naver-ads-thumbnail` 스킬 소관이라 이 계획 범위 밖이다 — ②번 판정행에 `mallProductId` 를 싣는 것까지가 여기 책임이고, Task 3 테스트가 그걸 검증한다.

**2. Placeholder 스캔** — "TBD"·"적절히 처리"·"위 내용대로 테스트" 없음. 모든 코드 단계에 실제 코드가 있다.

**3. 타입 일관성**

- `classify` 반환 키(`"①노출0"` 등)를 Task 3·6·7·8·9 가 모두 같은 문자열로 쓴다
- `ad_info` 가 만드는 필드명(`adId`·`bid`·`useGroupBid`·`groupBid`·`mallProductId`)을 `plan_raise`(Task 9)·`rows_for`(Task 8)·`build_report`(Task 7)가 그대로 쓴다
- `ledger.bid_decision` 이 돌려주는 사유 문자열(`"인상"`·`"상한도달"`·`"연속실패중단"`·`"입찰가불명"`)을 Task 9 테스트가 같은 문자열로 검증한다
- `fetch_purchases` 반환 형태 `{adId: {"cnt","amt"}}` 를 `classify` 의 `purchases` 가 그대로 받는다

