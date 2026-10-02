---
phase: quick-261002-mbo
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - .claude/skills/naver-sourcing-bench/scripts/rules.py
  - .claude/skills/naver-sourcing-bench/scripts/test_rules.py
  - .claude/skills/naver-sourcing-bench/scripts/gws_sheet.py
  - .claude/skills/naver-sourcing-bench/scripts/test_gws_sheet.py
  - .claude/skills/naver-sourcing-bench/scripts/drivers/options.js
  - .claude/skills/naver-sourcing-bench/scripts/sourcing_bench.py
  - .claude/skills/naver-sourcing-bench/scripts/test_cli.py
  - .claude/skills/naver-sourcing-bench/scripts/test_sheet_schema.py
  - .claude/skills/naver-sourcing-bench/SKILL.md
  - .claude/skills/naver-sourcing-bench/evidence/probe-2026-10.md
autonomous: true
requirements: [QUICK-261002-MBO]

must_haves:
  truths:
    - "bench 가 후보 상품 상세페이지에서 옵션을 읽어 후보 탭 9열(옵션 개수)·10열(옵션명:가격 / …)을 자동 기입한다"
    - "옵션 조합이 50개를 넘는 상품은 후보 탭에 추가되지 않는다"
    - "options --keyword 바지걸이 가 기존 후보 행의 9·10열을 채우고, 50 초과 행은 시트에서 삭제한다 (수식 깨짐 없음)"
    - "옵션 없는 단품은 9열=1, 10열=단품:<가격>"
    - "못 읽은 상품은 9·10열 빈칸 + 상태 옵션수동, 가격비교(/catalog/) 상품은 상세를 열지 않는다"
    - "캡챠/차단 감지 시 종료코드 4, 같은 명령 재실행으로 체크포인트부터 이어간다"
  artifacts:
    - path: ".claude/skills/naver-sourcing-bench/scripts/drivers/options.js"
      provides: "상세페이지 옵션 펼쳐 읽기 드라이버"
      contains: "aria-haspopup"
    - path: ".claude/skills/naver-sourcing-bench/scripts/rules.py"
      provides: "옵션 파싱·조합 판정 순수 함수"
      contains: "def build_options"
    - path: ".claude/skills/naver-sourcing-bench/scripts/gws_sheet.py"
      provides: "여러 칸 일괄 갱신 + 행 삭제"
      contains: "deleteDimension"
  key_links:
    - from: "sourcing_bench.py do_bench / do_refill"
      to: "drivers/options.js"
      via: "run('options', [{url}], opts, 115)"
      pattern: "run\\(\"options\""
    - from: "sourcing_bench.py"
      to: "rules.build_options"
      via: "드라이버 원시 결과 → {판정, options}"
      pattern: "rules\\.build_options"
    - from: "do_refill"
      to: "Sheet.delete_rows"
      via: "옵션초과 행 삭제(재조회 후 URL 로 위치 찾기, 아래→위)"
      pattern: "delete_rows"
---

<objective>
naver-sourcing-bench 의 `bench` 가 후보 상품 상세페이지를 Aside 로 열어 옵션을 펼쳐 읽고 `후보` 탭 9·10열을 자동 기입하게 한다. 옵션 조합 50개 초과 상품은 소싱 대상이 아니므로 후보에서 뺀다(이미 있으면 행 삭제). 기존 후보 행에 다시 적용하는 `options` 명령을 추가한다.

Purpose: 사용자가 손으로 채우던 옵션 칸(9·10열)을 없애고, 소싱 안 할 옵션 50+ 상품을 자동으로 걸러낸다.
Output: drivers/options.js, rules.py 옵션 파싱 함수, gws_sheet 일괄갱신·행삭제, `options` 서브커맨드, 갱신된 SKILL.md·실측 기록.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@./CLAUDE.md
@.claude/skills/naver-sourcing-bench/SKILL.md
@.claude/skills/naver-sourcing-bench/evidence/probe-2026-10.md
@.claude/skills/naver-sourcing-bench/scripts/rules.py
@.claude/skills/naver-sourcing-bench/scripts/sheet_schema.py
@.claude/skills/naver-sourcing-bench/scripts/gws_sheet.py
@.claude/skills/naver-sourcing-bench/scripts/sourcing_bench.py
@.claude/skills/naver-sourcing-bench/scripts/aside_bridge.py
@.claude/skills/naver-sourcing-bench/scripts/drivers/common.js
@.claude/skills/naver-sourcing-bench/scripts/test_cli.py
@.planning/quick/261002-mbo-bench-option-auto-fill/optprobe4.reference.js

<locked_decisions>
D-01 옵션 조합 50개 초과 → 후보에서 삭제(시트에 안 넣음, 이미 있으면 행 삭제).
D-02 10열 = `옵션명:가격 / 옵션명:가격 …` 한 셀. 가격 = 페이지 기본 판매가 + 추가금(원). 다단 조합명은 구분자 `-` 로 일관되게 잇는다(예 `화이트-10개`).
D-03 못 읽으면 9·10열 빈칸 + 상태 `옵션수동`. 가격비교(`/catalog/`) 상품은 옵션 읽기를 건너뛰고 빈칸(상태는 기존대로 `옵션수동`).
D-04 옵션 없는 단품 → 9열=1, 10열=`단품:<가격>`.
</locked_decisions>

<probe_findings date="2026-10-02">
- `smartstore.naver.com/main/products/<id>` 는 smartstore/brand.naver.com 으로 리다이렉트. 6개 열람 중 캡챠 0회.
- 옵션 섹션 = 리프 텍스트가 `옵션 선택` 으로 시작하는 span 의 부모 div(최대 5단계 올라가 a/button 을 가진 조상). 축 = 섹션 안 `a[role="button"][aria-haspopup="listbox"]`(텍스트=축 이름). 목록 = 섹션 안 `ul[role="listbox"] li`(li 안 `a[role="option"]`). 1단 목록은 클릭 전에도 DOM 에 있음.
- 항목 텍스트 예: `5. 찝게형 바지걸이 - 화이트 (+200원)`, `블랙 10+10개`. 추가금 `(+N원)`/`(-N원)`(콤마 가능), 품절 표기 가능.
- 다단: 1축 항목을 클릭해야 2축 목록이 열림 → 1축 값마다 (축 버튼 클릭 → 항목 클릭 → 다음 축 읽기) 반복, 3축 이상도 재귀로 일반화.
- 옵션 섹션 없음 + "수량" 선택만 있음 = 단품(예 스토리행거 smartstore.naver.com/main/products/3942331141).
- 표준그룹상품(brand.naver.com, `div[role=radiogroup]` 색상 버튼 + 수량 티어 텍스트): 읽기 실패로 `옵션수동` 처리 허용.
- 기본 판매가 = 페이지 "상품 가격" 아래 첫 금액(할인가). 검색 대표가와 다를 수 있음 — 계산은 페이지 기본가 기준.
- repl 호출당 ~120초 벽, 상품당 ~10~15초(다단은 더 김).
</probe_findings>

<interfaces>
기존 계약(코드에서 추출 — 탐색 불필요):

rules.py
- to_int(v) -> int|None ; norm_url(url) -> str
- rep_price(options, fallback) -> 옵션 최저가 또는 fallback
- options_text(options) -> "이름:13,900 / 이름:12,900"  (options = [{"이름","가격"}])

sheet_schema.py
- BENCH_TAB="후보"; 0-based 열: 4 키워드, 6 상품 URL, 8 옵션 개수, 9 각 옵션 가격, 20 대표판매가(U), 23 상태(X)
- bench_row(date, keyword, product, options) — options=None 이면 8·9 빈칸 + 상태 "옵션수동"; U = rep_price(options, 검색가)
- FORMULAS 는 전부 `INDEX(X:X,ROW())` 행 상대참조 → 행 삭제해도 아래 행 수식이 깨지지 않는다(Task 1 테스트로 고정).

gws_sheet.Sheet(sid, runner)
- read(tab) -> 헤더 뺀 행들 (range "{tab}!A:X")
- append(tab, rows) -> int ; set_cell(tab, row_index, col_index, value)  (row_index 0 = 시트 2행)
- _col(i) 0-based → A1 열 문자 ; runner(argv) -> dict (테스트는 Fake runner 로 argv 검사)

aside_bridge
- run_driver(name, items, opts, timeout) -> [__R__ dict…] ; load_driver(name) = common.js + name.js (login/probe 제외)
- auto_chunk(count, sec_per_item, sleep_max) -> 한 호출당 건수

drivers/common.js 제공: ITEMS, OPTS, rand, emit(r), PAGESTATE(), settle(url) -> "캡챠"|"차단"|"없음"|"정상"

sourcing_bench.py
- STOP=("캡챠감지","차단감지"); _load/_save/_slug/_chunks; RUNS 경로; do_bench(sheet, keyword, ckpt_path, run, date, opts, with_options=True)
- 현재 bench 는 `--options` 플래그(기본 끔)로 존재하지 않는 "detail" 드라이버를 부른다 → 이번에 "options" 드라이버로 교체하고 기본 켬.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: 옵션 파싱 순수 함수(rules.py) + 시트 일괄갱신·행삭제(gws_sheet.py)</name>
  <files>.claude/skills/naver-sourcing-bench/scripts/rules.py, .claude/skills/naver-sourcing-bench/scripts/test_rules.py, .claude/skills/naver-sourcing-bench/scripts/gws_sheet.py, .claude/skills/naver-sourcing-bench/scripts/test_gws_sheet.py, .claude/skills/naver-sourcing-bench/scripts/test_sheet_schema.py</files>
  <behavior>
    - parse_option_item("5. 찝게형 바지걸이 - 화이트 (+200원)") → 이름 "찝게형 바지걸이 - 화이트", 추가금 200, 품절 False (앞 번호 "N. " 제거, 공백 정리)
    - parse_option_item("블랙 10+10개") → 이름 "블랙 10+10개", 추가금 0 (괄호 없는 + 는 추가금 아님)
    - parse_option_item("대형 (+1,200원)") → 1200 ; "소형 (-500원)" → -500 ; "레드 (품절)" → 품절 True, 이름에서 "(품절)" 제거
    - parse_base_price("상품 가격\n할인가\n12,900원\n…18,000원") → 12900 (첫 "N원"); 숫자 없음 → None
    - build_options(probe, fallback) — probe 는 드라이버 원시 결과:
      · 상태 "단품" → {"판정":"성공","options":[{"이름":"단품","가격":기본가}]} (D-04)
      · 상태 "성공", combos=[["화이트","10개 (+3,000원)"],…] → 이름 "화이트-10개", 가격 = 기본가 + 각 부분 추가금 합 (D-02)
      · 품절 조합은 이름 끝에 "(품절)" 을 붙여 포함(개수에 셈)
      · 상태 "옵션초과" 또는 combos 개수 > max_combos(기본 50) → {"판정":"옵션초과","options":None} (D-01). 정확히 50 → 성공
      · 기본가 None 이면 fallback(검색 대표가) 사용; 둘 다 없으면 판정 "실패"
      · 상태 "읽기실패"·combos 비었음·probe None → {"판정":"실패","options":None} (D-03)
    - is_catalog("https://search.shopping.naver.com/catalog/123") → True, 스마트스토어 URL → False
    - options_text(build_options(단품…)["options"]) == "단품:12,900" ; 9열 = len(options)
    - Sheet.update_cells("후보", [(row_index, col_index, value), …]) → `sheets spreadsheets values batchUpdate` 1회, data 의 range 가 "후보!I5" 꼴(row_index 3 → 5행), valueInputOption USER_ENTERED; 빈 목록이면 호출 0회
    - Sheet.delete_rows("후보", [3, 7]) → `spreadsheets get`(fields=sheets.properties) 로 sheetId 조회 후 `spreadsheets batchUpdate` 1회, deleteDimension 요청이 내림차순(7 먼저), dimension ROWS, startIndex = row_index+1(헤더 보정), endIndex = startIndex+1; 탭 없으면 GwsError; 빈 목록이면 호출 0회
    - test_sheet_schema: FORMULAS 의 모든 수식에 "ROW()" 가 있고 `[A-Z]+\d+` 꼴 고정 셀 참조가 없다(행 삭제 안전성 고정)
  </behavior>
  <action>
rules.py 에 순수 함수 추가(네트워크·파일 접근 없음, 한국어 docstring/주석): parse_option_item(text) → dict(이름, 추가금, 품절); parse_base_price(text) → int|None; is_catalog(url) → "/catalog/" 포함 여부; build_options(probe, fallback, max_combos=50) → {"판정": "성공"|"옵션초과"|"실패", "options": list|None}. 조합명 구분자는 상수 OPTION_JOIN = "-" 로 두고 각 부분의 정리된 이름을 잇는다(D-02). 추가금 합산 규칙: 조합의 모든 부분 추가금을 더한다(네이버 조합형은 마지막 축에만 금액이 붙으므로 합 = 마지막 축 금액, 독립형은 합이 맞다 — 주석으로 근거 남김). 품절 조합 처리는 Claude 재량으로 "포함 + 이름 끝 (품절)" 을 택한다(옵션 개수는 판매자가 운영하는 조합 수라서). 기본가 미확보 시 fallback 사용도 재량 결정(사람 큐 최소화) — 주석에 명시. 정규식은 `\(\s*([+-])\s*([\d,]+)\s*원\s*\)` 류로 추가금, `^\d+\.\s*` 로 앞 번호 제거. 예외를 던지지 말고 이상 입력은 "실패" 판정으로 돌린다(try-except).

gws_sheet.py Sheet 에 update_cells(tab, cells) 와 delete_rows(tab, row_indices) 추가. update_cells 는 values batchUpdate 를 `--params {"spreadsheetId"}` + `--json {"valueInputOption":"USER_ENTERED","data":[{"range":"후보!I5","values":[[v]]},…]}` 로 한 번에 보낸다. delete_rows 는 `_sheet_id(tab)` 로 `sheets spreadsheets get --params {"spreadsheetId", "fields":"sheets.properties(sheetId,title)"}` 결과에서 제목이 일치하는 sheetId 를 찾고(없으면 GwsError), `sheets spreadsheets batchUpdate --params {"spreadsheetId"} --json {"requests":[{"deleteDimension":{"range":{"sheetId","dimension":"ROWS","startIndex","endIndex"}}}…]}` 를 내림차순 정렬·중복 제거한 행으로 보낸다(위 행을 먼저 지우면 아래 인덱스가 밀리므로). 기존 _call 의 error 처리 재사용.

테스트는 기존 Fake runner 패턴(test_gws_sheet.py 의 Fake/_params)을 따라 argv 와 JSON 바디를 검사한다. 먼저 테스트 작성 → 실패 확인 → 구현.
  </action>
  <verify>
    <automated>cd /Users/choiyongsmacbook/Documents/yongtimjang_claudecode && .venv/bin/python -m pytest -q .claude/skills/naver-sourcing-bench/scripts</automated>
  </verify>
  <done>새 rules·gws_sheet 테스트와 수식 행상대참조 테스트가 통과하고, 기존 32개 테스트도 전부 통과.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: drivers/options.js + bench 연동 + `options` 재적용 명령</name>
  <files>.claude/skills/naver-sourcing-bench/scripts/drivers/options.js, .claude/skills/naver-sourcing-bench/scripts/sourcing_bench.py, .claude/skills/naver-sourcing-bench/scripts/test_cli.py</files>
  <behavior>
    - do_bench: 옵션 판정 "옵션초과" 상품은 후보 탭에 추가되지 않는다 (D-01)
    - do_bench: 단품 결과 → 행 9열 1, 10열 "단품:12,900", 상태 빈칸 (D-04)
    - do_bench: /catalog/ 상품은 run("options") 에 넘기지 않고 9·10열 빈칸 + 옵션수동 (D-03)
    - do_bench: 드라이버 결과에 캡챠감지 → 체크포인트 저장 후 SystemExit(4), 시트에 아무것도 추가 안 함. 재실행 시 이미 받은 상품은 run 에 다시 넘기지 않는다
    - do_bench: run 이 RuntimeError → 남은 상품 옵션수동(기존 테스트 test_bench_detail_driver_missing_marks_manual 유지)
    - bench 파서: 기본 옵션 수집 켬, `--no-options` 로 끔 (기존 test_cli_bench_options_off_by_default 는 이번 작업이 뒤집는 동작이므로 새 기본값을 검사하도록 고친다)
    - do_refill(sheet, keyword, ckpt, run, opts): 후보 탭에서 키워드 일치 + 9열 빈칸 + 카탈로그 아닌 행만 대상. 성공 → update_cells 로 8(개수)·9(문자열)·20(rep_price)·23("") 한 번에 기록. 옵션초과 → 시트를 다시 read 해서 URL(norm_url)로 현재 행 위치를 찾아 delete_rows. 실패 → 손대지 않음(옵션수동 유지). 반환 {"채움","삭제","수동","건너뜀"} 개수
    - do_refill: 재실행하면 이미 채운 행은 대상에서 빠지고(9열 채워짐), 체크포인트에 있는 URL 은 run 을 다시 부르지 않는다
    - do_refill: 캡챠 → 그때까지 결과는 반영(update/delete) 후 SystemExit(4)
  </behavior>
  <action>
drivers/options.js 신규(common.js 가 앞에 붙는다 — ITEMS=[{url}], OPTS={sleep, sleepMax, maxCombos}). optprobe4.reference.js 의 섹션 탐색(SEC) 로직을 출발점으로, 실측 셀렉터(probe_findings)를 써서 상품마다:
1) settle(url) 로 이동·캡챠 정착. "캡챠"/"차단" → emit({kind:"options", key:url, 상태:"캡챠감지"|"차단감지"}) 후 루프 중단(호출부가 종료코드 4 처리).
2) priceText = body innerText 에서 "상품 가격" 이후 ~200자(Python 이 parse_base_price 로 첫 금액을 뽑는다).
3) 옵션 섹션 탐색. 없으면: 본문에 "수량" 선택이 있고 radiogroup 이 없으면 상태 "단품", 아니면 "읽기실패"(표준그룹상품 등 — probe 상 허용).
4) 섹션이 있으면 축 버튼 `a[role="button"][aria-haspopup="listbox"]`(보이는 것) 목록을 axes 로 잡고 재귀 수집: 축 k 버튼 클릭 → 대기(~1초) → 섹션 안 보이는 `ul[role="listbox"] li` 텍스트 수집. 마지막 축이면 각 항목을 [앞 축 선택값…, 항목] 조합으로 combos 에 추가; 아니면 항목 j 마다 축 k 버튼 다시 클릭 → `li` j 번째의 `a[role="option"]`(없으면 li) 클릭 → 축 k+1 로 재귀. combos 개수가 OPTS.maxCombos(50) 를 넘는 순간 중단하고 상태 "옵션초과"(D-01). 1축 단계에서 항목 수만으로 50 초과가 확정돼도 즉시 중단.
5) 상품당 시간 상한(예 90초) 초과 시 "읽기실패"(error "시간초과"). 모든 page.evaluate/click 은 try-catch 로 감싸 예외 시 "읽기실패"+error.
6) emit({kind:"options", key:url, 상태, axes, priceText, combos, error}); 상품 간 rand(OPTS.sleep, OPTS.sleepMax) 대기; 마지막에 console.log("__DONE__").
주석은 한국어로, 실측 근거(2026-10-02)를 남긴다.

sourcing_bench.py:
- SEC_OPTIONS = 20.0(다단 클릭 반영 청크 계산용), MAX_COMBOS = 50 상수. opts 에 maxCombos 를 실어 드라이버로 넘긴다.
- 공용 헬퍼 _read_options(urls, ck, run, opts): 카탈로그·체크포인트에 있는 URL 은 빼고 auto_chunk 로 run("options", [{"url"}…], opts, 115) 호출, 결과를 ck["details"][key] 에 저장·_save; STOP 상태를 만나면 True 반환(중단 신호), RuntimeError 면 경고 출력 후 False 로 남은 건 미수집 처리.
- do_bench: 기존 "detail" 호출부를 _read_options 로 교체. 중단 신호면 SystemExit(4)(행 추가 전). 행 조립 시 rules.build_options(d, 검색가) 로 판정 → "옵션초과" 는 건너뛰고 건수 출력, "성공" 은 options 전달, 그 외(카탈로그·실패·미수집)는 None → bench_row 가 옵션수동(D-03).
- do_refill 신규(행동 명세대로). 체크포인트 RUNS / f"options-{_slug(keyword)}.json" ({"details":{}}). 쓰기 순서: 성공 행 update_cells 먼저(읽은 시점 인덱스 유효) → 옵션초과는 시트 재조회 후 URL 로 위치를 다시 찾아 delete_rows(인덱스 밀림 방지).
- 파서: bench 의 `--options` 를 `--no-options`(store_true) 로 바꾸고 with_options = not args.no_options. 서브커맨드 `options --keyword K` 추가 → require_login → do_refill → "옵션 채움 N · 삭제 N(50초과) · 수동 N · 건너뜀 N" 출력. 종료코드 규칙은 기존과 동일(1/2/3/4).
- test_cli.py: 기존 detail 목(mock) 결과를 새 드라이버 원시 형태({"kind":"options","key","상태","priceText","combos"})로 바꾸되 기존 단언(추가 행 수, U열 값, 옵션수동)은 유지. FakeSheet 에 update_cells/delete_rows 기록용 구현 추가. 행동 명세의 새 케이스를 테스트로 추가.
  </action>
  <verify>
    <automated>cd /Users/choiyongsmacbook/Documents/yongtimjang_claudecode && .venv/bin/python -m pytest -q .claude/skills/naver-sourcing-bench/scripts && (cd .claude/skills/naver-sourcing-bench/scripts && ../../../../.venv/bin/python -c "import aside_bridge;open('/tmp/claude-501/opt_check.js','w').write('(async()=>{'+aside_bridge.load_driver('options')+'\n})')") && node --check /tmp/claude-501/opt_check.js && .venv/bin/python .claude/skills/naver-sourcing-bench/scripts/sourcing_bench.py options --help</automated>
  </verify>
  <done>전체 pytest 통과, options.js 가 load_driver("options") 로 조립되고(최상위 await 외 문법 오류 없음), `options --keyword` 와 `bench --no-options` 가 파서에 존재.</done>
</task>

<task type="auto">
  <name>Task 3: 라이브 드라이버 확인(시트 쓰기 없음) + SKILL.md·실측 기록 갱신</name>
  <files>.claude/skills/naver-sourcing-bench/SKILL.md, .claude/skills/naver-sourcing-bench/evidence/probe-2026-10.md</files>
  <action>
라이브 확인 — 시트 쓰기 금지(전체 재적용 `options --keyword 바지걸이` 는 오케스트레이터 몫이므로 실행하지 않는다):
1) `.venv/bin/python .claude/skills/naver-sourcing-bench/scripts/sourcing_bench.py login-check`. 종료코드 3 이면 라이브 확인을 멈추고 SUMMARY 에 "네이버 로그인 필요 — 사용자가 Aside 창에서 직접 로그인 후 재확인" 으로 남긴다(아이디·비밀번호는 묻지 않는다).
2) scratchpad 에 작은 Python 스크립트를 만들어 scripts 경로를 sys.path 에 넣고 aside_bridge.run_driver("options", items, {"sleep":3,"sleepMax":6,"maxCombos":50}, 115) 를 직접 호출한 뒤 각 결과를 rules.build_options 로 판정해 출력한다. items 는 3건: runs/bench-바지걸이.json 의 page.products 를 rules.bench_filter 로 거른 것 중 스마트스토어 URL 2건(다단 옵션 상품이 있으면 우선) + 단품 기준 `https://smartstore.naver.com/main/products/3942331141`.
3) 기대: 단품 → 9열=1·"단품:<가격>", 옵션 상품 → 개수와 "이름:가격 / …" 문자열이 화면 가격과 상식적으로 맞음(기본가+추가금). 셀렉터가 실측과 다르게 동작하면 options.js 를 고치고 Task 2 테스트를 다시 돌린 뒤 재확인(최대 2회). 캡챠 → 종료, SUMMARY 에 기록.

문서 갱신:
- SKILL.md: frontmatter description 의 "옵션은 사용자가 수동 입력" 을 "옵션(9·10열)은 상세페이지에서 자동 수집" 취지로 고친다. §1 명령에 `$PY $S options --keyword "바지걸이"  # 기존 후보 행에 옵션 채우기, 50조합 초과 행 삭제` 와 `bench --no-options` 추가. §2-5 수동 칸 안내에서 9·10 을 빼고 "옵션수동 행만 손으로" 로. §3 의 "옵션(9·10열)은 자동 수집 안 된다" 문구를 새 규칙으로 교체: 10열 형식(D-02, 구분자 `-`), 단품(D-04), 50 초과 제외·행 삭제(D-01), 못 읽음/표준그룹상품/카탈로그 → 옵션수동(D-03), U열 대표판매가 = 옵션 최저가. 체크포인트 목록에 `runs/options-*.json` 추가.
- evidence/probe-2026-10.md: 옵션 칸의 ❌ 기록은 그대로 두고(이력), "## 2026-10-02 재실측 — 상세 DOM 으로 옵션 읽기 성공" 절을 추가해 probe_findings 의 셀렉터·다단 동작·단품/표준그룹상품 판별·기본가 위치·캡챠 0회를 적고, 분기 결과 (b) 를 "API 경로는 실패, DOM 경로로 자동 수집 전환" 으로 갱신. 2) 의 라이브 결과(상품별 판정·개수·소요 초)를 표로 덧붙인다.
  </action>
  <verify>
    <automated>cd /Users/choiyongsmacbook/Documents/yongtimjang_claudecode/.claude/skills/naver-sourcing-bench && ! grep -q "자동 수집 안 된다" SKILL.md && grep -q "options --keyword" SKILL.md && grep -q "2026-10-02" evidence/probe-2026-10.md && cd ../../.. && .venv/bin/python -m pytest -q .claude/skills/naver-sourcing-bench/scripts</automated>
  </verify>
  <done>라이브 드라이버가 바지걸이 상품 2~3건에서 판정을 돌려줬거나(또는 로그인/캡챠로 멈춘 사유가 SUMMARY 에 기록됨), SKILL.md·실측 기록이 새 동작을 설명하고, 시트에는 이 태스크에서 아무것도 쓰지 않았다.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| 네이버 상세페이지 DOM → 드라이버 | 외부 페이지 텍스트(옵션명·가격)가 시트 셀로 흘러간다 |
| CLI → 구글 시트(gws) | 행 삭제는 되돌리기 어려운 쓰기 |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-mbo-01 | Tampering | update_cells (USER_ENTERED) | mitigate | 옵션명이 "=" 로 시작하면 수식으로 해석되므로 build_options 에서 이름 앞 "=", "+", "@" 를 제거하거나 앞에 작은따옴표를 붙여 문자열로 고정 |
| T-mbo-02 | Tampering | delete_rows | mitigate | 삭제 직전 시트 재조회 + norm_url 일치 행만, 내림차순 단일 batchUpdate. 엉뚱한 행 삭제 방지 테스트 포함 |
| T-mbo-03 | Denial of Service | 네이버 캡챠/차단 | mitigate | 캡챠·차단 감지 즉시 중단 → 종료코드 4, 체크포인트 재개, 상품 간 랜덤 대기 유지 |
| T-mbo-04 | Information Disclosure | 네이버 로그인 | accept | 자격증명을 다루지 않음 — 사용자가 Aside 창에서 직접 로그인 |
</threat_model>

<verification>
- `.venv/bin/python -m pytest -q .claude/skills/naver-sourcing-bench/scripts` 전부 통과(기존 32 + 신규)
- options.js 문법 확인, `sourcing_bench.py options --help` 동작
- 라이브: 바지걸이 2~3건 드라이버 판정 출력(시트 쓰기 없음)
</verification>

<success_criteria>
- bench 가 기본으로 옵션을 읽어 9·10열을 채우고, 50조합 초과 상품은 추가하지 않는다
- `options --keyword K` 로 기존 행 재적용·50초과 행 삭제가 가능하다(실행은 오케스트레이터)
- 단품/카탈로그/읽기실패 처리가 D-03·D-04 대로
- 문서가 새 동작과 2026-10-02 실측을 반영
</success_criteria>

<output>
Create `.planning/quick/261002-mbo-bench-option-auto-fill/261002-mbo-SUMMARY.md` when done
</output>
