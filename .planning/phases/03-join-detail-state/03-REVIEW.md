---
phase: 03-join-detail-state
reviewed: 2026-09-21T15:20:00Z
depth: standard
files_reviewed: 22
files_reviewed_list:
  - webapp/state.py
  - webapp/join.py
  - webapp/bulsaja_index.py
  - webapp/argv.py
  - webapp/jobs.py
  - webapp/flow.py
  - webapp/paths.py
  - webapp/settings.py
  - webapp/security.py
  - webapp/main.py
  - webapp/routes/board.py
  - webapp/routes/jobs.py
  - webapp/static/board.js
  - webapp/templates/board.html
  - webapp/run-webapp.sh
  - .claude/skills/bulsaja-detail-page/scripts/bulsaja_rate.py
  - .claude/skills/bulsaja-detail-page/scripts/bulsaja_scan.py
  - .claude/skills/bulsaja-detail-page/scripts/ss_index_build.py
  - .claude/skills/bulsaja-detail-page/scripts/ss_index_calls.py
  - .claude/skills/bulsaja-detail-page/scripts/ss_index_resume.py
  - .claude/skills/bulsaja-detail-page/scripts/detail_batch.py
  - webapp/tests/ (conftest · test_join · test_jobs · test_cli_shim · fixtures/render_check · fixtures/anonymize_join)
findings:
  critical: 3
  warning: 9
  info: 5
  total: 17
status: issues_found
---

# Phase 3: Code Review Report

**Reviewed:** 2026-09-21
**Depth:** standard (파일별 정독 + 언어별 검사 + 실행 가능한 재현)
**Files Reviewed:** 22
**Status:** issues_found

## Summary

웹앱 쪽(`state.py` · `join.py` · `bulsaja_index.py` · `jobs.py` · 라우트)은 **의도대로 잠겨 있다.**
D-19(웹앱에 `requests`/`eroomlib` 0건), `--workers 1`, 보드 캐시 금지(`{jobs, ss_index}`),
`bool()` 금지, 미해소 버킷 2분리, 빈 목록이 전량이 되는 3층 방어 — 전부 코드에서 실제로 확인됐다.
테스트 340건도 전부 green 이다(`.venv-web/bin/python -m pytest webapp/tests`).

**그런데 이 페이즈가 가장 무서워하는 실패 — "화면이 조용히 거짓말한다" — 가
CLI 쪽(`bulsaja_scan.py` · `ss_index_build.py`)에 세 군데 그대로 살아 있다.**
셋 다 03-07 첫 실탄에서 났던 `r.get("항목") or []` 와 **완전히 같은 모양**이다:
불사자 MCP 의 **툴 레벨 오류 응답은 예외가 아니라 `{"_text": "..."}` dict 로 돌아오는데**
(`eroomlib/bulsaja.py:101-111` · `224-240` 실측), 호출부가 그 dict 에서 원하는 키를
`.get(...) or []` / `or {}` 로 꺼내 **"물어봤더니 없더라"** 로 읽는다.
`ss_index_calls.항목꺼내기` 가 그 구멍을 막으려고 만들어졌는데 **호출부 1곳에만 적용됐다.**

가장 비싼 것은 CR-01 이다 — 재현으로 확인했다: 마켓그룹 조회가 오류 dict 를 주면
스캔이 `exit 0` 으로 `"마켓그룹": []` 산출물을 쓰고, 보드는 **전 행을 광고청소 버킷**에 담아
멀쩡한 광고그룹 8개를 "네이버 광고에서 찾아 지워라" 로 띄운다. 이 페이즈가 정의한 최대 오진
(Pitfall 3)이 정확히 그 경로로 성립한다. 웹앱은 `join_doc=None` 만 막고 있고, `[]` 는 못 막는다.

보안 쪽(경계 자체)은 구멍을 못 찾았다: 토큰 비교 상수시간·비ASCII 안전, Origin+Host+커스텀 헤더
3층, 경로는 화이트리스트, argv 는 리스트 조립, SQL 은 전부 파라미터 바인딩, 템플릿에 `|safe` 0건.

---

## Critical Issues

### CR-01: 마켓그룹 조회 오류가 "마켓그룹 0개"로 흡수되고, 보드는 그걸 **전 행 광고청소**로 읽는다

> ✅ **수정 완료 (2026-09-21)** — RED `eba6fda` · GREEN **`ec2d5e7`**
> 1층 CLI: `bulsaja_scan.py` 가 `ss_index_calls.그룹꺼내기`(= `항목꺼내기` 와 같은 규약, 공통 본체
> `목록꺼내기` 로 합쳤다)로 해석하고, 못 읽었거나 0개면 **exit 2 · 산출물 없음**.
> 2층 웹앱: `_load_join` 이 `마켓그룹` 빈 산출물을 `None` + 사유로 내려 전 행을 `미조회`/`시스템`
> (안전한 쪽)으로 떨어뜨린다. 회귀 5건 추가 — 재현값 `광고청소행 9 · 청소그룹 8` 이 0 으로 고정됐다
> (`test_board.py::test_마켓그룹이_빈_산출물은_광고청소를_만들지_않는다` ·
> `test_index.py` §11 네 건). MCP 는 한 번도 안 때린다(크레딧 0).
> **CR-02 · CR-03 은 열린 채다 — 이번 수정 범위가 아니다.**

**File:** `.claude/skills/bulsaja-detail-page/scripts/bulsaja_scan.py:309-313`
**같이 볼 곳:** `webapp/join.py:217-261` · `webapp/routes/board.py:116-150`

**Issue:**
```python
그룹응답 = 표시규칙제거(mcp.call_tool("bulsaja_market_groups", {}) or {})
마켓그룹 = [... for g in (그룹응답.get("그룹") or 그룹응답.get("항목") or []) ...]
```
불사자 MCP 는 **툴 레벨 오류를 예외로 올리지 않는다.** JSON-RPC error 만 `RuntimeError` 로
승격되고(`eroomlib/bulsaja.py:224-240`), `isError` + 텍스트 본문은
`extract_tool_payload` 가 `{"_text": "MCP error -32602: ..."}` 같은 **평범한 dict** 로 돌려준다
(`eroomlib/bulsaja.py:101-111`). 03-07 첫 실탄의 9.2초 미스터리가 바로 이 경로였고,
`ss_index_calls.항목꺼내기` 가 그 교훈으로 생겼다 — **그런데 이 호출부는 그 함수를 안 쓴다.**

결과: 오류 응답(또는 응답 키 이름 변경) → `마켓그룹 = []` → 경고 한 줄 없이 스캔 계속 →
`exit 0` → `jobs.latest_done("bulsaja_scan")` 이 그 잡을 **성공**으로 집어 옴 →
`join.attach` 는 `문서 is not None` 이므로 정상 경로로 들어가고 `그룹색인 = {}` 이 되어
**번호가 있는 모든 행이 `번호없음`(= 광고청소)** 이 된다.

실제 재현 (`result_traps.json` + `"마켓그룹": []`):
```
전체 9 · 광고청소행 9 · 광고청소그룹 8 · 시스템행 0
사유별 {'추출실패': 1, '번호없음': 8}
청소목록 그룹수 8
```
즉 화면은 **"이 광고그룹 8개가 불사자와 안 이어진다 — 네이버 광고에서 찾아 지우거나
번호를 고쳐라"**(`board.html:496-520`)라고 말한다. 시스템 고장이 사람의 삭제 작업 목록으로
둔갑하는 것 — 이 페이즈 최대 오진이고 되돌릴 수 없다.

`routes/board.py:116-150` 의 `_load_join` 은 이 함정을 **정확히 알고 주석에 적어 뒀는데**
(`빈 dict 를 주면 … 전 행이 광고 청소 대상으로 둔갑한다 — 그게 Pitfall 3 그 자체다`)
막고 있는 것은 `join_doc is None` 뿐이고, **`마켓그룹: []` 은 통과**한다.

**Fix:** 응답 해석을 `항목꺼내기` 와 같은 규약으로 올리고, **빈 그룹 목록으로는 산출물을 쓰지 않는다**
(계정에 마켓그룹이 0개인 상태는 이 워크플로에서 유효한 관측이 아니다 — 실측 86개).
```python
# bulsaja_scan.py
def 그룹꺼내기(r):
    """마켓그룹 목록 응답 → 리스트. **모양이 아니면 예외다** (ss_index_calls.항목꺼내기 와 같은 규약)."""
    if not isinstance(r, dict):
        raise RuntimeError(f"마켓그룹 응답이 dict 가 아니다: {type(r).__name__}")
    for 키 in ("그룹", "항목"):
        if 키 in r:
            값 = r.get(키) or []
            if not isinstance(값, list):
                raise RuntimeError(f"마켓그룹 응답의 '{키}' 가 리스트가 아니다")
            return 값
    사유 = r.get("_text") or r.get("error") or r.get("message") or f"키 {sorted(r.keys())[:8]}"
    raise RuntimeError(f"마켓그룹 응답에 '그룹'/'항목' 이 없다: {str(사유)[:300]}")

그룹응답 = 표시규칙제거(mcp.call_tool("bulsaja_market_groups", {}) or {})
마켓그룹 = [{"groupId": str(g.get("groupId") or ""), "그룹명": str(g.get("그룹명") or "")}
           for g in 그룹꺼내기(그룹응답) if isinstance(g, dict)]
if not 마켓그룹:
    사유 = "⛔ 마켓그룹이 0개다 — 그건 관측이 아니라 조회 실패다. 산출물을 쓰지 않는다."
    말하기(사유); 오류말하기(사유)
    return 2
```
2층 방어로 `webapp/routes/board.py::_load_join` 에도
`if not (문서.get("마켓그룹") or []): return None, 시각, "조인 산출물에 마켓그룹이 없다 — 스캔을 다시 돌려라"`
를 더해라. `None` 으로 내려가면 전 행이 `미조회`/`시스템` 이 되어 **안전한 쪽**으로 떨어진다.

---

### CR-02: 팬아웃(사본·기작업 태그) 조회 실패가 "사본 0건 · 기작업 아님"으로 둔갑한다 → D-08 크레딧 재지불

> ✅ **수정 완료 (2026-09-21)** — RED `ac669f6` · GREEN **`1ee701a`**
> 3층으로 막았다.
> **1층 CLI** `배치조회` 가 `(항목들, 실패코드)` 를 돌려준다(해석은 `ss_index_calls.항목꺼내기`
> 재사용). 행 기본값 `사본: []` → **`None`**, 그리고 `팬아웃미조회` 칸 신설 —
> 1단 실패·2단 실패·2단 무응답이 전부 여기로 모인다. 끝 로그에 건수를 따로 싣는다.
> **2층 웹앱** `join.attach` 가 미조회면 `사본N` 을 `0` 이 아니라 빈칸으로 두고,
> `join.selectable` 이 그 행을 **기본 선택에서 뺀다**(기작업과 같은 수법 — 목록에는 남고
> 직접 체크하면 대상이 된다). 키가 없는 **옛 산출물은 `False`** 로 읽어 하위호환이다.
> **3층 화면** 사본·기작업 칸에 `⚙ ?` + hover 전문("0건이라는 뜻이 아니다"), `고를수있는`
> 이 `selectable` 과 같은 규약을 타고(필터 전체 선택의 마지막 자리), 선택 요약·배너가
> "기작업 제외" 와 "태그 미조회 제외" 를 **한 칸에 담지 않는다**. 시스템 배너에 건수를
> 싣되 광고 청소 배너·청소 목록은 한 행도 안 늘어난다(⚙ 시스템 / 🛠 광고 분리).
> 회귀 6건 추가 — 재현값 `기본선택 대상: 1` 이 0 으로 고정됐다
> (`test_index.py::test_팬아웃_조회오류를_사본0건으로_읽지_않는다` ·
> `test_스캔은_팬아웃_미조회를_행에_적는다` · `test_join.py` 3건 ·
> `test_board.py::test_화면도_팬아웃_미조회를_기본선택에서_뺀다` ·
> `test_팬아웃_미조회는_시스템칸에_뜨고_광고청소에_안_섞인다`).
> MCP 는 한 번도 안 때린다(크레딧 0).

**File:** `.claude/skills/bulsaja-detail-page/scripts/bulsaja_scan.py:213-222`, `:400-422`
**같이 볼 곳:** `webapp/join.py:304-312` · `webapp/join.py:412-420`

**Issue:** `배치조회()` 의 두 줄이 실패를 정상값으로 흡수한다.
```python
if 미조회 or not isinstance(r, dict):
    말하기(f"[경고] 코드 조회 {len(조각)}건을 못 받았다 — 사본 정보가 빈다")
    continue
항목들.extend(표시규칙제거(r).get("항목") or [])   # ← 오류 dict 는 여기로 샌다(경고도 없다)
```
- **오류 응답**: `{"_text": ...}` 는 dict 이고 `미조회=False` 라 위 `if` 에 안 걸린다 →
  `.get("항목") or []` → **로그 한 줄 없이** 0건.
- **429 소진**(`안전호출` 6회 실패): 경고는 찍히지만 **행에는 아무 표시가 안 남는다.**
  산출물의 행 스키마에 "팬아웃을 못 했다" 를 적을 칸 자체가 없다.

두 경우 모두 그 행은 `불사자코드=None` · `그룹태그=None` · `사본=[]` 로 저장되고
(`:422` `행["사본"] = 사본별.get(묶음, [])`), 웹앱은 그걸 확정값으로 읽는다
(`join.py:307-312`: `isinstance(사본, list)` → `사본N = 0`, `잠금혼재 = False`).

재현 (팬아웃만 조용히 실패한 행 1개):
```
{'해소': True, '상세상태': '단순번역만', '기작업': False, '기작업태그': None,
 '사본N': 0, '잠금혼재': False}
기본선택 대상: 1
```
즉 ① 화면이 **"사본 0건"** 이라고 단언하고(JOIN-03 팬아웃 경고가 통째로 죽는다)
② `그룹태그` 가 비어 `state.기작업여부` 가 **False** → `join.selectable` 의 기본 선택에 들어간다.
`구매_가공완료` 가 붙은 상품이 Phase 5 의 크레딧 대상이 된다 — **D-08/STATE-05 가 무력화된다.**

이 증상은 **이미 한 번 났다.** `bulsaja_scan.py:355-364` 주석이 직접 적고 있다:
*"그러면 그룹태그도 안 채워져 기작업(D-08) 제외가 통째로 죽는다. 실제로 첫 실탄에서
사본 0건 · 기작업 0건이 나왔다."* 그때 고친 것은 **원인 하나(summary→full)뿐**이고,
"실패를 0으로 읽는 해석" 은 그대로 남았다.

**Fix:** (1) 응답 해석을 `항목꺼내기` 로 올리고, (2) **행마다 팬아웃 실패를 기록**해 웹앱이
"0건" 과 "못 물어봤다" 를 구분하게 한다.
```python
# bulsaja_scan.py — 배치조회
from ss_index_calls import 항목꺼내기          # 이미 있는 규약을 쓴다
...
if 미조회:
    말하기(f"[경고] 코드 조회 {len(조각)}건 — 레이트리밋으로 못 받았다")
    실패코드.update(조각)                      # 호출부로 돌려준다
    continue
try:
    항목들.extend(항목꺼내기(r, 맥락=f" (코드 {len(조각)}건)"))
except RuntimeError as e:
    말하기(f"[경고] 코드 조회 응답이 모양이 아니다 — {e}")
    실패코드.update(조각)

# 행 기록
행["사본"] = 사본별.get(묶음) if 묶음 in 사본별 else None   # None = 못 물어봤다
행["팬아웃미조회"] = 행["판매자상품코드"] in 실패코드
```
웹앱 쪽은 `join.attach` 에서 `사본 is None` 이면 `사본N=None`(빈칸)으로 두고,
`팬아웃미조회` 인 행은 **기본 선택에서 뺀다**(`selectable`) — 태그를 못 읽은 행에
크레딧을 태우지 않는 쪽이 안전한 기본값이다. `_기본값` 에 `"팬아웃미조회": None` 을 더해라.

---

### CR-03: 인덱스 구축에서 오류 응답이 `unresolved=0`(성공 관측)으로 적히고, 재개가 영영 다시 안 본다

> ✅ **수정 완료 (2026-09-21)** — RED `ac669f6` · GREEN **`268b3dc`**
> `ss_index_calls.워크데이터꺼내기` 를 추가했다 — `목록꺼내기` 와 **같은 규약**이다
> (키 부재·타입 불일치 = 예외 · 키가 있고 비었으면 `{}` = 정상 관측). 빈 `data` 는
> 막지 않는다: 업로드 안 된 수집상품이 대부분이라 막으면 반대 방향으로 틀린다.
> 서버 문구 추출(`_사유`)도 한 곳으로 합쳐 `목록꺼내기` 와 규칙이 두 벌이 되는 것을 막았다.
> `ss_index_build.그룹훑기` 는 모양오류를 **`unresolved = 1`(미조회)** 로 적고 미조회수에
> 센다 — `번호없음`(smartstore NULL + unresolved 0)으로 적지 않는다. 그래서
> `ss_index_resume.처리완료()` 가 그 행을 안 세고 **다음 실행이 다시 조회한다**
> (03-04 이탈 #1 계약 유지). 그룹도 `완결=False` 로 남아 화면이 "인덱스에 없음" 을
> 확정하지 않는다. `bulsaja_scan` 의 같은 자리도 같은 함수로 통일했다(거기선
> `행["미조회"]=True` 라 `재검증판정` 이 시스템 버킷으로 떨어뜨린다).
> 회귀 3건 추가 — 재현값 `unresolved=0` 이 `1` 로 고정됐다
> (`test_index.py::test_워크데이터_오류응답을_빈_data로_읽지_않는다` ·
> `test_빌더는_workdata_오류를_미조회로_적는다` ·
> `test_빌더가_workdata_응답을_직접_해석하지_않는다` — 문자열 가드, 두 CLI 모두).

**File:** `.claude/skills/bulsaja-detail-page/scripts/ss_index_build.py:283-296`
**같이 볼 곳:** `.claude/skills/bulsaja-detail-page/scripts/ss_index_resume.py:27-38` · `webapp/bulsaja_index.py:146-199`

**Issue:**
```python
r, 미조회 = 안전호출(lambda: mcp.call_tool("bulsaja_product_workdata",
                                          {"productId": pid, "mode": "summary"}), ...)
if 미조회:
    ss, unresolved = None, 1
else:
    d = (r or {}).get("data") or {}                       # ← 오류 dict 가 여기서 {} 가 된다
    값 = (d.get("uploadedSuccessUrl") or {}).get("smartstore")
    ss, unresolved = (str(값) if 값 else None), 0         # ← "못 물어봤다" 가 "업로드 안 된 상품"이 된다
```
`안전호출` 은 **429 만** 미조회로 돌리고 나머지는 그대로 올린다 — 그런데 툴 레벨 오류는
예외가 아니라 dict 라서 `미조회=False` 로 내려온다(CR-01 과 같은 근거). 그러면
`data` 키가 없는 응답 = `{}` = "smartstore 번호가 없는 정상 상품" 으로 **확정 기록**된다.

파급이 세 겹이다:
1. `ss_index_resume.처리완료()` 는 `unresolved = 0` 행을 "성공" 으로 보고 **재개에서 건너뛴다** →
   그 상품은 같은 잡을 몇 번 다시 돌려도 **영원히 다시 조회되지 않는다.**
2. `완결 = 행수>0 and 누적미조회==0 and 행수>=총계` (`:322-324`) 가 **참**이 된다 →
   `bulsaja_index.group_health` 도 같은 식이라 화면이 그 그룹을 "다 훑었다" 로 본다 →
   `routes/board.py:189-205` 가 그 행을 "인덱스 불완전" 이 아니라 **"인덱스에 없음"** 으로 확정 표기한다.
3. 그 상품은 Phase 5 의 작업 대상에서 **조용히 빠진다** — 알려진 429 이월 항목이 걱정한
   "그 그룹이 통째로 비고 화면은 완주라고 말한다" 와 같은 피해가 **상품 단위로** 난다.

`mode=summary` 응답에 `uploadedSuccessUrl` 이 없던 그 사고와 구조가 동일하다 —
**필드 부재와 조회 실패를 구분하는 장치가 이 경로에 하나도 없다.**

**Fix:** 응답 모양을 검증하고, 모양이 아니면 **미조회로 적는다**(건너뛰지 않는다).
```python
def 워크데이터꺼내기(r, 맥락=""):
    """workdata 응답에서 `data` dict 를 꺼낸다. **모양이 아니면 예외다.**"""
    if not isinstance(r, dict) or "data" not in r:
        사유 = (r or {}).get("_text") or (r or {}).get("error") if isinstance(r, dict) else type(r).__name__
        raise RuntimeError(f"workdata 응답에 'data' 가 없다{맥락}: {str(사유)[:300]}")
    d = r.get("data")
    if not isinstance(d, dict):
        raise RuntimeError(f"workdata 의 'data' 가 dict 가 아니다{맥락}: {type(d).__name__}")
    return d

...
if 미조회:
    ss, unresolved = None, 1
else:
    try:
        d = 워크데이터꺼내기(r, 맥락=f" (pid {pid[-8:]})")
    except RuntimeError as e:
        말하기(f"{머리} [모양오류] {e} — 미조회로 적는다")
        ss, unresolved = None, 1          # 성공으로 접지 않는다
        미조회수 += 1
    else:
        값 = (d.get("uploadedSuccessUrl") or {}).get("smartstore")
        ss, unresolved = (str(값) if 값 else None), 0
```
`bulsaja_scan.py:363-372` 의 같은 `(r or {}).get("data") or {}` 도 함께 고쳐라.
(그쪽은 결과적으로 `관측_smartstore=None` → `재검증판정` 이 `미조회` 를 내서 안전한 쪽으로
떨어지지만, 같은 함수로 통일해야 다음 사람이 두 규약을 안 외운다.)

---

## Warnings

### WR-01: 마켓번호 정규식에 숫자 경계가 없다 — **다른 그룹 번호를 집는다**

**File:** `webapp/join.py:66`
**Issue:** `_번호패턴 = re.compile(r"(\d{1,2})-(\d{1,2})")` 에 앞뒤 경계가 없다. 실측:
```
market_number('A4-2매_15-2_zz')       → '4-2'    (정답은 15-2)
market_number('판매상품_2026-09-21_zz') → '26-09'
market_number('100-2 zz')             → '00-2'
```
`4-2` 가 불사자에 실재하면 그 행은 **엉뚱한 마켓그룹으로 좁혀지고**, `index_targets` 가
그 그룹을 대상에 넣어 **수십 분~수 시간을 엉뚱한 곳에 태운다.** 실재하지 않으면 `번호없음`
(광고청소)이 되어 멀쩡한 그룹이 삭제 목록에 오른다.
같은 저장소의 픽스처 생성기는 **경계를 이미 넣어 뒀다** — `webapp/tests/fixtures/anonymize_join.py:44`
의 `(?<![0-9-])(\d{1,2}-\d{1,2})(?![0-9-])` 와 그 주석(*"앞뒤에 숫자·하이픈이 붙으면 번호가 아니다"*).
즉 **런타임과 픽스처가 다른 규칙을 쓰고 있다.**
회귀 테스트(`test_join.py:95-101`)는 "뽑힌 번호가 이름 안에 들어 있다" 만 보므로 이 오탐을 못 문다.

**Fix:** 런타임 패턴을 픽스처 생성기와 같게 맞추고, 테스트에 위 3개 입력을 그대로 넣어라.
```python
_번호패턴 = re.compile(r"(?<![0-9-])(\d{1,2})-(\d{1,2})(?![0-9-])")
```

### WR-02: 그룹 목록 조회 단계만 429 재시도를 안 탄다 (상품 단계는 6회 재시도)

**File:** `.claude/skills/bulsaja-detail-page/scripts/ss_index_build.py:203-226`
**Issue:** 상품 조회는 `안전호출(..., 재시도대기=인자.retry_after)` 로 6회까지 버티는데,
같은 루프 안의 `bulsaja_market_group_products` 는 **맨손 호출**이다. 일시적 429 하나로
그 그룹의 목록 조회가 통째로 죽고, 그때까지 수집한 페이지도 버려진다(예외가
`그룹상품목록` 밖으로 나간다). `--retry-after` 설정값이 이 단계에는 **적용조차 안 된다.**
알려진 이월 항목(429 가 요약에서 사라지는 문제)과는 **다른 결함**이다 — 그쪽은 보고,
이쪽은 재시도다. 둘 다 고쳐야 첫 구축이 안 무너진다.
**Fix:** 목록 호출도 `안전호출` 로 감싸고, 미조회가 나면 그 그룹을 `완결=False` 로 남겨라
(반환에 `목록미조회` 를 실어 `그룹훑기` 가 요약에 적게).

### WR-03: 광고 배너의 "미해소 N행" 이 스캔 전에는 시스템 행까지 포함한다

**File:** `webapp/templates/board.html:369-374` (`webapp/join.py:337-341`)
**Issue:** `resolution.번호미해소 = 전체 - 번호해소` 인데, 스캔을 안 돌린 상태
(`join_doc=None`)에서는 **전 행이 번호미해소**다. 그 숫자가 **광고 쪽 배너**
(`id="resolution-ads"`, *"여기 숫자는 사람이 고칠 것이다"*)에 실린다.
바로 아래 시스템 배너가 "광고 쪽 오류가 아니다" 라고 말해 주긴 하지만, 두 배너가
**같은 행 집합을 서로 다른 소속으로 말하는** 상태다. Pitfall 3 를 이중으로 막자는
설계 의도와 어긋난다.
**Fix:** 광고 배너의 분자를 버킷에서 직접 받아라 — `resolution.광고청소.행`
(그 값은 정의상 `추출실패 + 번호없음` 뿐이다). `번호미해소` 는 시스템 배너 쪽이나
디버그 값으로만 쓴다.

### WR-04: 폴링이 `starting` 상태를 "끝남"으로 읽는다

**File:** `webapp/static/board.js:507`
**Issue:** `if (j.status === "running" && 남은 > 0)` — 잡 상태는 `running`/`starting`
둘 다 살아 있는 것이다(`jobs.LIVE_STATUSES`). 서버 쪽 `_산출물`
(`routes/jobs.py:232-236`)은 그 둘을 같이 보는데 화면은 `running` 만 본다.
`starting` 을 한 번이라도 받으면 폴링이 **영구히 멈추고** "도는 중" 표가 그대로 굳는다.
현재 운영 경로에서는 `create_job` 이 `status='running'` 까지 올린 뒤에야 job_id 를 주므로
재현 확률이 낮다(그래서 Critical 이 아니다). 다만 `_reap`·재접속·v2 스케줄러 경로가
생기면 바로 새는 자리다.
**Fix:** `if ((j.status === "running" || j.status === "starting") && 남은 > 0)`.
상태 목록을 서버가 내려 주면 더 좋다.

### WR-05: `active_job()` 이 최근 50건만 본다 — 3시간짜리 인덱스 잡이 패널에서 사라질 수 있다

**File:** `webapp/jobs.py:845-850`
**Issue:** `recent_jobs(50)` 은 `started_at DESC` 로 자른다. 인덱스 잡(실측 3시간 32분)이
도는 동안 다른 잡 50건이 생기면 그 잡이 목록에서 밀려나 `active_job()` 이 `None` 이 된다 →
새로고침 순간 진행 패널과 SSE 가 사라지고 사용자는 "죽었나" 로 읽는다(성공기준 3 이 깨진다).
**Fix:** 도는 잡은 목록이 아니라 상태로 직접 물어라.
```sql
SELECT * FROM jobs WHERE status IN ('running','starting') ORDER BY rowid LIMIT 1
```
(`_reap` 을 먼저 돌린 뒤 같은 커넥션에서.)

### WR-06: `detail_batch.py` 의 기작업 판별이 파이썬 truthiness 이고, 스킵이 목표 장수에 묶여 있다

**File:** `.claude/skills/bulsaja-detail-page/scripts/detail_batch.py:148`, `:192`
**Issue:** ① `if not dc.get("aiImageGenerated"):` — `'0'` 이 오면 파이썬에서 참이다.
이번 페이즈가 `webapp/state.py:60-78` 에 만든 `불리언정규화` 규약(“`bool()` 금지”)과
**두 벌**이 됐다. 방향이 "과잉 스킵"(크레딧 안 나감)이라 덜 급하지만, 판정 규약이 둘이면
어느 쪽이 정본인지 다음 사람이 모른다.
② `if prev and prev["pages"] >= sc:` — 스킵이 **이번 목표 장수**에 묶여 있다.
8장짜리 기작업 상품이 이번에 이미지를 10장 모으면 재접수돼 크레딧을 다시 낸다.
`state.기작업여부` 의 docstring 이 이걸 D-10/STATE-05 위반으로 못 박아 뒀는데
CLI 쪽은 그대로다. Phase 5 가 이 CLI 를 그대로 래핑하면 웹앱 가드를 통과한 뒤
**CLI 안에서** 재지불이 난다.
**Fix:** ①은 `ss_index_*`/`state.py` 와 같은 정규화 헬퍼를 CLI 쪽에도 두고 쓴다.
②는 Phase 5 계획에 "기작업 스킵은 절대 조건" 을 CLI 에 반영하는 작업을 명시적으로 넣어라
(이번 페이즈에서 고치지 않는다면 `03-VALIDATION.md` 미해결 목록에 올려야 한다 — 지금은 없다).

### WR-07: 읽기 전용 스키마 점검이 빈 `webapp.db` 를 **만든다**

**File:** `.claude/skills/bulsaja-detail-page/scripts/ss_index_build.py:165-174`
**Issue:** `sqlite3.connect(db경로)` 는 파일이 없으면 **만든다.** 그 다음 `exit 4`
("웹앱을 한 번 띄워 스키마를 만들어라")로 죽지만, 디스크에는 테이블이 하나도 없는
`webapp.db` 가 남는다. 그러면 `webapp/bulsaja_index.db_path().is_file()` 이 참이 되어
"DB 가 없다" 와 "DB 는 있는데 테이블이 없다" 가 갈라지고, `lookup()` 은 `sqlite3.Error`
경로로 빠져 `{}` 를 돌려준다(결과적으로는 미조회라 안전하지만 진단이 흐려진다).
웹앱이 `active_job()`·`latest_done()` 에서 지키는 "읽기 경로가 파일을 만들지 않는다"(T-1-01b)
규율과도 어긋난다.
**Fix:**
```python
def 스키마확인(db경로):
    if not os.path.isfile(db경로):
        return False
    cx = sqlite3.connect(f"file:{db경로}?mode=ro", uri=True)
    ...
```

### WR-08: 청소 목록의 그룹 `사유코드` 가 **처음 만난 행**으로 정해진다

**File:** `webapp/join.py:363-382`
**Issue:** `cleanup_groups` 는 그룹을 처음 만들 때만 `사유코드` 를 박는다. 한 행에
광고그룹이 여러 개 걸릴 수 있으므로(`adGroups` 가 리스트다), 같은 그룹 이름이
`추출실패` 행과 `번호없음` 행 양쪽에서 나올 수 있다. 그러면 화면의 "사유" 칸이
**행 순서에 따라 달라진다**(`board.html:513`). 용팀장이 이 표로 광고를 고치는데,
"번호가 없다" 와 "번호가 안 맞는다" 는 조치가 다르다.
**Fix:** 그룹별로 사유코드 집합을 모아 표시하거나(`번호없음 · 추출실패`),
그룹 이름에서 직접 `market_number()` 를 다시 뽑아 사유를 결정해라
(이미 `번호` 칸은 그렇게 계산하고 있다 — 두 칸이 서로 다른 출처를 쓰는 게 이 불일치의 뿌리다).

### WR-09: 기동 스크립트가 `--workers` 를 사용자 인자로 덮어쓸 수 있다

**File:** `webapp/run-webapp.sh:34-38`
**Issue:** `exec "$PY" -m uvicorn ... --workers 1 "$@"` — `"$@"` 가 **뒤에** 붙으므로
`./webapp/run-webapp.sh --workers 4` 가 그대로 통한다(uvicorn/click 은 마지막 값이 이긴다).
바로 위 주석이 *"--workers 1: 협상 불가다"* 라고 적어 둔 값이 인자 하나로 뚫린다.
`main.py:56-62` 의 경고는 `WEB_CONCURRENCY` 환경변수만 본다.
**Fix:** 넘어온 인자에서 `--workers` 를 거부해라.
```bash
for a in "$@"; do
  case "$a" in --workers|--workers=*) echo "워커 수는 고정이다 (Pitfall 9)" >&2; exit 2;; esac
done
```

---

## Info

### IN-01: 요청 핸들러가 전역 Jinja 환경을 바꾼다
**File:** `webapp/routes/board.py:262` — `templates.env.policies["json.dumps_kwargs"] = {...}`
요청마다 전역 상태를 쓴다. 동작은 멱등이라 문제가 안 나지만, 설정 자리는
`main.py` 의 `Jinja2Templates(...)` 생성부다. (참고: `tojson` 의 `<`/`>`/`&`/`'` 이스케이프는
`ensure_ascii=False` 와 무관하게 적용되므로 XSS 위험은 없다 — 실제로 확인했다.)

### IN-02: `_계정캐시` 가 무한히 커진다
**File:** `webapp/paths.py:94-126` — 키가 `(경로, mtime_ns, size)` 라 회차가 갱신될 때마다
새 항목이 쌓이고 지워지지 않는다. 1인 로컬이라 실질 영향은 없지만 상한(예: 128개 LRU)을 두면 끝난다.

### IN-03: 조인 키를 타입 정규화 없이 맞댄다
**File:** `webapp/join.py:224`, `:234` — `(acct, mallProductId)` 튜플을 그대로 dict 키로 쓴다.
지금은 양쪽 다 문자열이라(픽스처 전수 확인: `str` 194/194) 안전하지만, `result.json` 이
숫자를 내는 날 **전 행이 조용히 미조회**가 된다. `str()` 로 정규화해 두면 그 창이 닫힌다.

### IN-04: `불리언정규화` 가 dict/list 를 참으로 읽는다
**File:** `webapp/state.py:72-78` — `불리언정규화({})`·`불리언정규화([])` 가 `True` 다
(`str({})` = `"{}"` 가 `_FALSY` 에 없다). `aiImageGenerated` 가 빈 컨테이너로 오면
🔴 상품이 ⚪(AI가공완료)로 뒤집힌다 — 방향은 "과잉 스킵"이라 크레딧은 안 나가지만
값이 없는 것을 "완료" 로 읽는 셈이다. `if isinstance(v, (dict, list, tuple, set)): return bool(v)` 한 줄이면 닫힌다.

### IN-05: `groupId` 가 빈 문자열인 마켓그룹은 인덱스 대상에서 조용히 빠진다
**File:** `.claude/skills/bulsaja-detail-page/scripts/bulsaja_scan.py:310` →
`webapp/join.py:405-408` — `str(g.get("groupId") or "")` 로 `""` 가 저장되면
`index_targets` 의 `if gid:` 가 걸러 낸다. 로그도 경고도 없다. 응답에 groupId 가 없는 그룹은
**적지 말고 경고를 찍는** 쪽이 규약과 맞는다(빈 값을 정상값으로 흡수하지 않는다).

---

## 확인했고 문제 없었던 것 (중복 지적 방지용)

- **D-19** — `webapp/` 런타임에 `requests`/`eroomlib` import 0건 (주석 언급만 존재).
- **판정 순서 / `bool()` 금지** — `state.상세상태` 가 `aiImageGenerated` 를 먼저 보고
  `불리언정규화` 를 통과시킨다. `'0'` → False 확인.
- **보드 캐시 금지** — DDL 은 `jobs`·`ss_index` 뿐이고 `test_jobs.py:460-480` 가 집행한다.
- **빈 목록 = 전량 방어** — 라우트 400 · `_build_argv` ValueError · CLI `exit 2` 3층 전부 실재.
- **명령 주입 / 경로 조작** — argv 는 리스트 조립 한 곳, 회차 이름은 화이트리스트
  (`paths.run_dir_path`), 대상 파일은 `_override_targets` 의 부모 디렉터리 동일성 검사.
- **SQL** — 전 질의 파라미터 바인딩. `IN (...)` 은 플레이스홀더 생성뿐이고 값은 안 끼운다.
- **XSS** — 템플릿에 `| safe` 0건, `board.js` 는 `textContent` 만 쓴다, 데이터는
  `<script type="application/json">` + `tojson`.
- **자원 누수** — `spawn` 의 fd 정리, 모든 sqlite 커넥션이 `finally: close()`.
- **알려진 이월 항목 3건**(그룹 단계 429 요약 · 프로세스별 레이트리밋 · `재검증판정` 파일 위치)은
  다시 보고하지 않았다. WR-02 는 그중 첫 번째와 **다른 결함**(보고가 아니라 재시도)이다.

---

_Reviewed: 2026-09-21_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
