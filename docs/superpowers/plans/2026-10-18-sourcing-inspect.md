# sourcing-inspect 구현 계획 (1단계: 판정 파이프라인 + 파일럿)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 불사자 소싱 캠페인 스냅샷을 받아 1차·2차 검수 판정(기계 판정 + AI 팬아웃)을 하고, 사람이 훑어볼 결과표(HTML)를 만든다. 불사자에 쓰는 반영 단계는 2단계 계획에서 다룬다(쓰기 API 형식 실측이 선행 조건이라서).

**Architecture:** `catfix-fanout`과 같은 3단 구조다. ① Python `run_inspect.py`가 스냅샷을 받아 기계 판정을 하고 배치를 만든다. ② Workflow `inspect-fanout.js`가 Sonnet 워커에게 배치를 나눠 판정시키고, 결과를 run-dir 에 파일로 남긴다. ③ Python 이 결과를 합쳐 결과표를 만든다. 정본은 디스크(run-dir)이고, 재실행하면 남은 배치만 다시 돈다.

**Tech Stack:** Python 3.12(`.venv`, requests), plain-run 테스트(pytest 없음, 기존 관례), Workflow JS, `eroomlib.review_page`.

**Spec:** `docs/superpowers/specs/2026-10-18-sourcing-inspection-design.md`

## Global Constraints
- 코드 주석 한국어, try-except 포함, 스크립트는 `.venv/bin/python3`로 실행한다.
- 이 계획 범위에서는 불사자에 **쓰기 호출을 하지 않는다**(읽기 `bulsa-sourcing-products`만).
- run-dir 루트: `<workspace.toml data_root>/sourcing-inspect/runs/<이름>`
- 웹 토큰 파일: `~/.eroom/bulsaja-web.json` `{"token": "<JWT>"}`. 사용자가 직접 넣거나, 로그인된 브라우저에서 스냅샷을 받아 `--from-file`로 넘긴다.
- 판정값은 `pass` | `drop` 둘뿐이다. 애매하면 `drop`(스펙 §4-2).
- 금지 카테고리: `rules/banned_cats.txt` 3,290개. 227개는 마스터에 없지만 그대로 `catId` 일치로 쓴다(실측: 중간 단계 번호가 아니라 마스터에 없는 번호였다).

## Review Focus
- `taobaoResult`가 빈 배열이거나 `item`이 없는 상품 → 2차 대상에서 빠지고, `match_failed`는 기계 판정 `drop`(사유 `NO_MATCH`)으로 처리한다.
- `catId`가 문자열·숫자로 섞여 오는 경우 → 문자열로 정규화해서 비교한다.
- 워커가 일부 상품을 빠뜨리거나 배치에 없는 id 를 지어내는 경우 → merge 가 누락은 `missing`으로, 환각은 버림으로 보고한다.
- 썸네일 다운로드 실패 → 판정에서 빼지 않고 텍스트로만 판정한다(`thumb: null`).
- 같은 run-dir 로 재실행 → 이미 끝난 배치는 건너뛴다.

---

### Task 1: 규칙 파일 + 기계 판정 (`rules.py`)

**Files:**
- Create: `.claude/skills/sourcing-inspect/rules/banned_cats.txt` (spec 첨부 파일 복사)
- Create: `.claude/skills/sourcing-inspect/rules/banned_keywords.json`
- Create: `.claude/skills/sourcing-inspect/scripts/rules.py`
- Test: `.claude/skills/sourcing-inspect/scripts/test_rules.py`

**Interfaces:**
- Produces: `load_banned_cats(path=None) -> set[str]`, `load_keywords(path=None) -> dict[str, list[str]]` (사유코드 → 키워드들), `machine_judge(item: dict, stage: int, cats: set, kws: dict) -> dict | None`. 반환은 `{"verdict": "drop", "reason": <코드>, "note": <근거>}`이거나, 기계로 못 정하면 `None`이다.
- 사유코드(전 단계 공통): `BANNED_CAT`, `NO_MATCH`, `KEYWORD_<분류>`, 그리고 AI용 `LAW`·`DANGER`·`TARGET`·`IP`·`FASHION`·`SHIP`·`OTHER`

- [ ] 테스트: `catId="50000979"` → `BANNED_CAT`. `catId=50000979`(정수)도 같다. 상품명에 "레고 호환" → `KEYWORD_IP`. stage 2 에서 `taobao_match_status="match_failed"` → `NO_MATCH`. 일반 상품 → `None`.
- [ ] 구현: 키워드는 공백을 제거하고 소문자로 바꾼 부분일치로 본다. stage 1 은 `productName`·`sellerTags`를 보고, stage 2 는 타오바오 `title`도 함께 본다.
- [ ] 실행해서 통과하는지 확인한다: `.venv/bin/python3 .claude/skills/sourcing-inspect/scripts/test_rules.py`

### Task 2: 스냅샷·대상 선별·배치 (`run_inspect.py fetch|prep|batch|pending`)

**Files:**
- Create: `.claude/skills/sourcing-inspect/scripts/sourcing_api.py`
- Create: `.claude/skills/sourcing-inspect/scripts/run_inspect.py`
- Test: `.claude/skills/sourcing-inspect/scripts/test_run_inspect.py`

**Interfaces:**
- `sourcing_api.fetch_products(campaign_id: str, token: str) -> list[dict]`: `POST https://api.bulsaja.com/api/sourcing/bulsa-sourcing-products`. 브라우저 UA 헤더를 붙이고, 401 이면 토큰 재발급 안내를 담아 RuntimeError 를 낸다.
- `run_inspect.select_targets(items, stage) -> list[dict]`: stage 1 은 `taobaoResult`가 빈 상품, stage 2 는 `taobaoResult[0].item`이 있는 상품이다. 휴지통·수집완료 상태는 제외한다(상태값은 2단계 계획에서 확정. 지금은 `EXCLUDE_STATUS = set()`).
- `run_inspect.to_view(item, stage) -> dict`: 워커에 넘길 축약본 `{id, name, tags, catPath, brand, price, thumb_url, tb_title, tb_price, tb_thumb_url, fee}`. `catPath`는 마스터에서 찾는다.
- `run_inspect.make_batches(views, size=40) -> list[list]`
- 산출물 `<run>/snapshot.json`, `machine.json`(`{id: 판정}`), `views.json`, `thumbs/<id>_n.jpg|_t.jpg`, `batches/batch_NNN.json`, `batches_index.json`
- 명령: `fetch --campaign ID [--from-file F]`, `prep --stage 1|2 [--limit N] [--sample random|head]`, `batch --size 40`, `pending`
- [ ] 테스트: `select_targets`가 상태에 따라 가르는지, `to_view`가 `taobaoResult` 빈 배열에서도 죽지 않는지, `make_batches(85건, 40)` → 3배치, pending 이 `judged/judged_NNN.json`이 있는 배치를 빼는지.
- [ ] 구현: 썸네일은 requests 로 받아 긴 변 384px 로 줄여 저장한다(pillow). 실패하면 `null`로 둔다.
- [ ] 실행해서 통과하는지 확인한다.

### Task 3: 워커 지시서 + Workflow (`inspect-fanout.js`)

**Files:**
- Create: `.claude/skills/sourcing-inspect/rules/worker-prompt.md`
- Create: `.claude/workflows/inspect-fanout.js`

**Interfaces:**
- 워커 출력 `<run>/judged/judged_NNN.json`: `[{"id", "verdict": "pass"|"drop", "reason", "note"}]` 형식이고, note 는 한국어 한 줄이다.
- Workflow args 는 `pending` 출력을 그대로 쓴다: `{runDir, promptPath, stage, batches:[{n,path,count,imgs}]}`
- [ ] 지시서: 스펙 §4-2 표를 그대로 옮긴다. 1차는 텍스트로 먼저 판정하고, 애매할 때만 썸네일을 Read 한다. 2차는 타오바오 썸네일을 Read 하는 게 기본이다. 2차에서는 왼쪽과 오른쪽이 같은 상품인지는 판정하지 않는다.
- [ ] Workflow: catfix-fanout 의 빈패킹, 오디트, 1회 재시도 구조를 그대로 쓴다(이미지 예산 20장).

### Task 4: 합치기 + 결과표 (`run_inspect.py merge|report`)

**Interfaces:**
- `merge_judged(expected_ids, docs) -> (verdicts: dict, missing: list, extra: list)`
- `report`: `<run>/review.html`을 만든다. 탈락과 통과를 나눠 카드로 보여 주고, 카드마다 네이버·타오바오 썸네일, 사유, 근거를 넣는다. 사유별 건수 요약도 붙인다. `verdicts.json`은 기계 판정과 AI 판정을 합친 최종본이다.
- [ ] 테스트: 누락, 환각 id, 같은 id 중복 판정 시 drop 우선.
- [ ] 실행해서 통과하는지 확인한다.

### Task 5: SKILL.md + 파일럿 500건 (엔잡곰마켓 1차)

- [ ] SKILL.md: 트리거 문구, 흐름(fetch → prep → batch → Workflow → merge → report), 안전 규칙(이번 단계는 쓰기 없음)을 적는다.
- [ ] 로그인된 크롬에서 스냅샷을 받아 `fetch --from-file`로 넣는다.
- [ ] `prep --stage 1 --limit 500 --sample random` → batch → Workflow → merge → report 를 돌린다.
- [ ] 2차 대상(이미 매칭된 1,580건 중 무작위 200건)도 같은 방식으로 돌린다.
- [ ] 결과를 요약한다: 기계 판정 탈락률, AI 탈락률, 사유 분포, 소요시간.
