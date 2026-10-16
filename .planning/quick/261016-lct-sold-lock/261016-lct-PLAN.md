---
phase: quick-261016-lct
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - .claude/skills/sold-lock/scripts/sold_lock_rules.py
  - .claude/skills/sold-lock/scripts/test_sold_lock_rules.py
  - .claude/skills/sold-lock/scripts/commerce_orders.py
  - .claude/skills/sold-lock/scripts/run_sold_lock.py
  - .claude/skills/sold-lock/scripts/test_run_sold_lock.py
  - .claude/skills/sold-lock/SKILL.md
  - .claude/skills/sold-lock/launchd/com.eroom.sold-lock.plist
  - workspace.toml
autonomous: true
requirements: [SOLD-LOCK-01, SOLD-LOCK-02, SOLD-LOCK-03, SOLD-LOCK-04, SOLD-LOCK-05, SOLD-LOCK-06, SOLD-LOCK-07, SOLD-LOCK-08]

must_haves:
  truths:
    - "`run_sold_lock.py --date D --dry-run` 이 52마켓 전날 결제완료 주문을 커머스API로 모아 상품별 잠금 판정만 하고 불사자에는 아무것도 쓰지 않는다"
    - "기본 실행은 판정 통과 상품만 bulsaja_product_hide(hide:true)로 잠그고, 재조회로 잠금이 확인된 것만 locked_new 로 센다"
    - "정확히 1건 + 스스 상품번호 일치 + 마켓그룹에 용쌤{마켓번호} 가 있을 때만 잠근다. 나머지는 사유별 skipped"
    - "한 마켓의 토큰·주문조회 실패(예: 15-3 정지 400)가 다른 마켓 처리를 막지 않는다"
    - "같은 날짜 재실행 시 이미 잠근 상품은 already_locked 로 남고 새 쓰기가 없다"
    - "커머스 시크릿이 stdout·로그·orders.json·result.json·new_locks.json 어디에도 나오지 않는다"
    - "업무판 '오늘' 탭에 요약 1행이 붙고, 시트 쓰기가 실패해도 result.json 은 남는다"
  artifacts:
    - path: ".claude/skills/sold-lock/scripts/sold_lock_rules.py"
      provides: "순수 판정 함수 (날짜 범위·대상마켓·중복제거·매칭판정·요약문·시크릿 마스킹)"
    - path: ".claude/skills/sold-lock/scripts/run_sold_lock.py"
      provides: "CLI 진입점 (--date/--dry-run/--markets)"
    - path: ".claude/skills/sold-lock/scripts/commerce_orders.py"
      provides: "키 로드(시트→캐시) + 토큰 + 주문 수집"
    - path: ".claude/skills/sold-lock/launchd/com.eroom.sold-lock.plist"
      provides: "매일 00:01 caffeinate -i 실행 템플릿 (load 안 함)"
    - path: ".claude/skills/sold-lock/SKILL.md"
      provides: "스킬 설명 + 설치 명령"
  key_links:
    - from: "commerce_orders.py"
      to: "naver-ads-thumbnail/scripts/verify_creds.py issue_token"
      via: "sys.path 삽입 후 import"
      pattern: "from verify_creds import issue_token"
    - from: "run_sold_lock.py"
      to: "eroomlib.bulsaja.BulsajaMCP (requests 전송 — urllib UA 403 회피)"
      via: "eroomlib.snapshot.ProductMCP 상속/사용"
      pattern: "ProductMCP"
    - from: "run_sold_lock.py"
      to: "eroomlib.gsheets.append_rows"
      via: "업무판 요약 append"
      pattern: "append_rows"
---

<objective>
판매상품 자동잠금(sold-lock) 스킬 신설. 매일 00:01 맥북에서 전날(KST) 결제완료 주문을 52개 스마트스토어 커머스API로 모으고, 그 상품을 불사자에서 '잠금'(= MCP 숨김) 처리해 물갈이 삭제에 휩쓸리지 않게 한다.

Purpose: 팔린 상품이 물갈이 삭제로 사라지는 사고를 사람 손 없이 막는다.
Output: `.claude/skills/sold-lock/` (SKILL.md + scripts/ + launchd 템플릿), 단위테스트, workspace.toml 시트 키.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@./CLAUDE.md
@.claude/skills/bulsaja-product-lock/SKILL.md
@.claude/skills/_shared/불사자-안전규칙.md
@.claude/skills/_shared/스킬-계약.md

<interfaces>
<!-- 재사용할 기존 코드. 새로 만들지 마라. -->

토큰 — .claude/skills/naver-ads-thumbnail/scripts/verify_creds.py (모듈 최상단은 import 뿐, main 은 __main__ 가드. import 안전):
  issue_token(client_id, client_secret) -> (access_token | None, 오류문자열 | None)
  오류문자열에 응답 본문 앞 200자가 섞인다 → 그대로 로그에 찍기 전 sold_lock_rules.redact 를 통과시킬 것.
  BASE = "https://api.commerce.naver.com/external"

불사자 MCP 전송 — .claude/lib/eroomlib/bulsaja.py, eroomlib/snapshot.py:
  eroomlib 로드 관용구: 스크립트 위치에서 상위로 올라가며 `lib/eroomlib` 디렉터리를 찾아 그 lib 를 sys.path 에 1회 insert (bulsaja-category-fix/scripts/bulsaja_mcp.py:37-46 와 동일).
  ProductMCP() → .open() → .call_tool(name, arguments) -> dict → .close()
  전송은 requests.Session (UA python-requests) 이라 urllib UA 403 에 안 걸린다. Bearer 는 ~/.claude.json 에서 런타임 로드, 출력 금지.
  .workdata(pid, mode) 는 카테고리 요약용이라 스스 번호를 안 돌려준다 → 스스 번호는 call_tool("bulsaja_product_workdata", {"productId": pid, "mode": "full"}) 원응답의 data.uploadedSuccessUrl.smartstore (URL 이거나 숫자 — 끝 숫자열 추출).

응답 해석 — .claude/skills/bulsaja-detail-page/scripts/ss_index_calls.py (import 없음, import 안전):
  항목꺼내기(r, 맥락="") -> list   # find_by_code 응답 '항목'. 오류응답이면 RuntimeError (0건으로 접지 않는다)
  워크데이터꺼내기(r, 맥락="") -> dict  # workdata 'data'. 'data' 키 없으면 RuntimeError, 빈 data 는 {} (업로드 안 된 상품)
  표시규칙제거: bulsaja_scan.py:110 의 `표시규칙제거(obj)` — 그 파일은 무거우니 import 하지 말고 동작(표시규칙 키 제거)만 run_sold_lock 에 짧게 재현해도 된다.

find_by_code 항목 키(실측 사용처 bulsaja_scan.py:472-505, bulsaja-product-lock SKILL.md):
  "productId", "판매자상품코드", "불사자코드", "그룹"(마켓그룹명, 예 "1번_용쌤1-1"), 잠금상태는 "숨김"(lock 스킬 문서) 또는 "잠금"(bulsaja_scan) — 둘 중 bool 인 것을 쓴다. 응답 '못찾은코드' 리스트.
  배치 최대 50, 서버 레이트리밋 초당 4회 → 호출 간 최소 0.26초.

잠금 — bulsaja_product_hide: 1차 호출이 confirmationToken 반환 → 같은 인자 + confirm:true + confirmationToken 으로 즉시 재제출(안전규칙: 이미 동의한 작업의 2단계 확인). 최대 50개. 정확한 인자 이름(productIds 등)은 실행 시 ProductMCP.list_tools() 의 inputSchema 로 확인하고 그대로 쓴다.

계정 확인 — call_tool("bulsaja_my_profile", {}) 의 "닉네임" == "부킹" 아니면 중단 (detail_batch.py:323 _계정확인 관용구). 조회 실패도 불통과.

시트 — .claude/lib/eroomlib/gsheets.py (gws CLI 래퍼, 쿼터 백오프 내장):
  sheets_get(spreadsheet_id, rng) -> 2차원 list
  append_rows(spreadsheet_id, tab, rows)   # USER_ENTERED, INSERT_ROWS
설정 — eroomlib.config.cfg(dotted, default=None, required=False). workspace.toml(.gitignore 대상, 로컬 전용):
  paths.data_root = ~/python_work/data  → run-dir = <data_root>/sold-lock/<대상날짜>/
  sheets.orders   = 1D--UaQRTt3ofTQo087F0-HrcebR9SistTBmXezIwY90  (★마진율계산기★ = 키 정본 시트와 같은 ID)
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: 순수 판정 규칙 모듈 + 단위테스트 (네트워크 0)</name>
  <files>.claude/skills/sold-lock/scripts/sold_lock_rules.py, .claude/skills/sold-lock/scripts/test_sold_lock_rules.py</files>
  <behavior>
    - target_markets(): 정확히 52개 = 1-1~4-3(12) + 11-1~11-3(3) + 13-1~24-3(36) + 25-1(1). 5-x~10-x, 12-x, 25-2 는 미포함
    - parse_markets_arg("1-1,2-1") → ["1-1","2-1"]; 대상 밖 번호("5-1")는 ValueError
    - day_range_kst("2026-10-15") → ("2026-10-15T00:00:00.000+09:00", "2026-10-15T23:59:59.999+09:00"); default_target_date(now_kst=2026-10-16 00:01) → "2026-10-15"
    - is_paid_on(payment_date_str, "2026-10-15"): "+09:00" 문자열·UTC "Z" 문자열 모두 KST 로 환산해 판정 (2026-10-14T15:30:00Z → KST 10-15 00:30 → True)
    - dedup_orders(rows): 같은 마켓 안에서 판매자상품코드 기준, 코드 없으면 상품번호(productId) 기준 1건으로. 주문수는 묶인 개수로 보존. 다른 마켓의 같은 코드는 별개
    - decide(order, found_items, ss_no_by_pid, market_no) → (verdict, reason):
      0건 → skip "not_found"; 2건 이상 → skip "multiple"; 스스번호 조회실패(None 표식) → skip "ss_lookup_failed"; 스스번호 ≠ 주문 productId → skip "productno_mismatch"; 그룹명에 용쌤{마켓번호} 가 경계 포함 안 됨 → skip "market_mismatch" (용쌤1-1 이 "용쌤11-1"·"용쌤1-12" 에 매칭되면 안 된다 — 정규식 용쌤{번호}(?!\d) 이고 앞도 숫자 경계); 잠금상태 bool 없음 → skip "lock_state_unknown"; 잠금 True → "already_locked"; 그 외 → "lock"
    - extract_ss_no("https://smartstore.naver.com/x/products/12345678") → "12345678"; "12345678" → "12345678"; None/"" → None
    - summary_memo(result) → "주문 N · 신규잠금 a · 기존잠금 b · 스킵 c(not_found 2, multiple 1) · 실패마켓 15-3(정지/토큰실패)"; checked_flag(result) 는 스킵 0 이고 실패마켓 0 일 때만 True
    - redact(text, secrets): secrets 각 값을 "***" 로 치환. 시크릿이 포함된 dict 를 safe_json(obj, secrets) 로 직렬화하면 결과 문자열에 시크릿 원문이 없다
  </behavior>
  <action>
    RED 먼저: test_sold_lock_rules.py (unittest, 표준라이브러리만) 를 위 behavior 전부로 작성하고 실패 확인 후 커밋. GREEN: sold_lock_rules.py 를 구현 — 외부 의존(requests·gws·MCP) import 금지, 표준라이브러리만(datetime/zoneinfo Asia/Seoul, re, json). 한국어 docstring·주석, 사유 코드는 위 영문 키로 고정(result.json 집계 키로 그대로 쓰인다). find_by_code 항목의 잠금상태는 "숨김" 이 bool 이면 그것, 아니면 "잠금" 이 bool 이면 그것, 둘 다 아니면 None 으로 해석하는 lock_state(item) 를 두고 decide 가 그것을 쓴다(키 이름이 문서마다 달라서 둘 다 받는다). 주문 행 형식은 dict {"market","product_order_id","product_id","seller_code","product_name","payment_date"} 로 고정하고 docstring 에 명시 — Task 2 가 이 형식으로 채운다.
  </action>
  <verify>
    <automated>cd /Users/choiyongsmacbook/Documents/yongtimjang_claudecode/.claude/skills/sold-lock/scripts && ../../../../.venv/bin/python3 -m unittest test_sold_lock_rules -v</automated>
  </verify>
  <done>behavior 항목 전부가 테스트로 존재하고 통과. sold_lock_rules.py 에 requests/gws/eroomlib import 없음.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: 커머스 주문 수집 + 불사자 잠금 CLI (run-dir 산출물·업무판 기록)</name>
  <files>.claude/skills/sold-lock/scripts/commerce_orders.py, .claude/skills/sold-lock/scripts/run_sold_lock.py, .claude/skills/sold-lock/scripts/test_run_sold_lock.py, workspace.toml</files>
  <behavior>
    - 가짜 커머스(마켓 2개, 그중 하나 토큰 실패) + 가짜 MCP 로 run(): 실패 마켓은 result.markets[n].status="token_failed", 다른 마켓은 정상 처리
    - --dry-run 이면 가짜 MCP 에 bulsaja_product_hide 호출 0회, 판정은 result.json 에 "would_lock" 으로 남는다
    - 실제 모드: hide 1차 → confirmationToken → confirm:true 재제출 → find_by_code 재조회 잠금 True 면 locked_new, 재조회가 False/불명이면 skipped "lock_unverified"
    - 같은 입력으로 두 번 run(): 두 번째는 hide 호출 0회, 전부 already_locked
    - 계정 닉네임이 "부킹" 이 아니면 종료코드 3, 불사자 쓰기 0, 주문 수집도 하지 않는다
    - 산출 파일 3종(orders.json, result.json, new_locks.json) 어디에도 가짜 시크릿 문자열이 없다; 캡처한 stdout 에도 없다
    - append_rows 가 예외를 던져도 run() 은 정상 종료하고 result.json 의 board.status="failed"(오류문 redact) 로 남는다
  </behavior>
  <action>
    workspace.toml [sheets] 에 work_board = "1kuw0kpqT5gjgx5KiOIkDrOfVWmUu7O0k-Dnbq4yspAg" (업무판) 한 줄 추가(키 시트는 기존 sheets.orders 재사용 — 스킬-계약 §경로·시트ID·계정은 코드에 박지 않는다). 코드에서는 cfg("sheets.orders", required=True), cfg("sheets.work_board", required=True), cfg("paths.data_root", required=True) 로만 참조.

    commerce_orders.py: (1) load_stores(market_filter): sheets_get(cfg sheets.orders, "'사업자정리'!A48:L120") 로 A=마켓번호, C=마켓명, G=애플리케이션ID, H=시크릿 을 읽어 sold_lock_rules.target_markets() 교집합만 취한다. 성공하면 ~/.eroom/naver-commerce-stores.json 에 원자적 쓰기 후 os.chmod 0o600(캐시). 시트 실패 시 그 캐시로 폴백하고 출처("sheet"/"cache")를 result 에 기록, 둘 다 없으면 종료코드 2. 시크릿은 반환 dict 안에만 두고 출력 금지. (2) verify_creds.issue_token 재사용: naver-ads-thumbnail/scripts 를 스크립트 위치 기준 상대경로로 sys.path 에 넣고 import (경로 하드코딩 금지, run_names.py 관용구). 토큰 실패 메시지는 redact 후 저장하고 마켓 status="token_failed"(15-3 같은 정지 마켓 포함) — 계속 진행. (3) fetch_paid_orders(token, market, date): GET {BASE}/v1/pay-order/seller/product-orders/last-changed-statuses, params lastChangedFrom/lastChangedTo=day_range_kst, lastChangedType=PAYED, 응답 data.more 가 있으면 moreFrom 을 다음 lastChangedFrom, moreSequence 를 moreSequence 로 넣어 반복. productOrderId 를 300개씩 POST /v1/pay-order/seller/product-orders/query {"productOrderIds":[...]} → productOrder.productId·sellerProductCode·productName, order.paymentDate 로 Task1 주문 행 dict 생성, is_paid_on 으로 재필터. requests 사용, 429/5xx 지수백오프 최대 4회, 마켓별 try/except → status="orders_failed". 호출 간 0.2초 이상 간격.

    run_sold_lock.py: argparse --date(기본 default_target_date), --dry-run, --markets, --expect-nick(기본 "부킹"). 의존성 주입 가능한 run(args, commerce=..., mcp_factory=..., board_append=...) 함수에 본체를 두고 main 은 얇게(3단계 스케줄러가 같은 함수를 부를 수 있게). 순서: ① ProductMCP open → bulsaja_my_profile 닉네임 확인(불일치/실패 → exit 3, 아무것도 쓰지 않음) ② 키 로드 ③ 마켓별 주문 수집 → dedup_orders → orders.json ④ 판매자상품코드 목록을 find_by_code 50개 배치(0.26초 간격, 항목꺼내기로 해석 — 오류는 0건이 아니라 해당 코드 skip "lookup_error"), 판매자상품코드 0건인 주문은 상품번호(productId 문자열)로 한 번 더 find_by_code ⑤ 정확히 1건인 후보만 workdata(full) 로 스스번호 추출(워크데이터꺼내기 예외 → ss_lookup_failed) ⑥ decide ⑦ dry-run 이 아니면 "lock" 판정을 50개씩 bulsaja_product_hide hide:true → confirmationToken 재제출 → find_by_code 재조회로 잠금 True 확인 시에만 locked_new. 인자명은 실행 첫 단계에서 list_tools() inputSchema 로 확인해 맞춘다(문서 bulsaja-product-lock SKILL.md 의 흐름 그대로, 판정 규칙만 추가). ⑧ run-dir <data_root>/sold-lock/<대상날짜>/ 에 orders.json(시크릿 없음), result.json(마켓별 status·주문수·markets_source, totals{orders, lock_targets, locked_new, already_locked, skipped{사유:건수}}, 항목별 판매자상품코드·사유), new_locks.json([{마켓번호, 마켓명, 판매자상품코드, 스스상품번호, 불사자ID}]) 를 safe_json 으로 원자적 쓰기. 재실행 시 new_locks.json 은 덮지 말고 기존 목록과 판매자상품코드 기준 병합(이전 실행의 신규잠금이 사라지지 않게). ⑨ 업무판: sheets_get(work_board, "'오늘'!A:A") 로 번호 최댓값+1, append_rows(work_board, "오늘", [[번호, 실행일 KST YYYY-MM-DD, checked_flag, "⑥ 판매상품 잠금 <대상날짜>", "⑥", "Claude", "자동", summary_memo, ""]]). dry-run 이면 할 일 앞에 "[dry-run] " 을 붙인다. try/except 로 감싸 실패는 result.board 에 기록. stdout 진행로그는 print(flush=True), 사람용 표기는 판매자상품코드(내부 productId 는 파일에만). 한 마켓 예외가 루프를 끊지 않게 마켓 단위 try/except. 종료코드: 0 정상(스킵 있어도), 2 키 로드 불가, 3 계정 불일치. 주석 한국어.

    test_run_sold_lock.py: behavior 항목을 가짜 commerce/MCP/board 주입으로 검증. tempfile 로 data_root 를 바꾸고(cfg 대신 run() 인자로 run_dir 주입 허용) 실제 네트워크·gws·MCP 호출 0.
  </action>
  <verify>
    <automated>cd /Users/choiyongsmacbook/Documents/yongtimjang_claudecode/.claude/skills/sold-lock/scripts && ../../../../.venv/bin/python3 -m unittest test_sold_lock_rules test_run_sold_lock -v && ../../../../.venv/bin/python3 run_sold_lock.py --help</automated>
  </verify>
  <done>두 테스트 파일 통과, --help 가 --date/--dry-run/--markets 를 보여준다. workspace.toml 에 sheets.work_board 존재. 코드에 시트 ID·절대경로 하드코딩 없음(grep -v '^\s*#' 로 1kuw/1D--/python_work 미검출).</done>
</task>

<task type="auto">
  <name>Task 3: SKILL.md + launchd plist 템플릿 (load 하지 않음)</name>
  <files>.claude/skills/sold-lock/SKILL.md, .claude/skills/sold-lock/launchd/com.eroom.sold-lock.plist</files>
  <action>
    plist: Label com.eroom.sold-lock, StartCalendarInterval Hour 0 Minute 1, ProgramArguments = /usr/bin/caffeinate, -i, <워크스페이스>/.venv/bin/python3, <워크스페이스>/.claude/skills/sold-lock/scripts/run_sold_lock.py. WorkingDirectory = 워크스페이스 루트, EnvironmentVariables PATH 에 /opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin 포함(gws CLI 를 찾아야 한다 — 실행 전 `command -v gws` 로 실제 위치 확인해 포함), PYTHONUNBUFFERED=1. StandardOutPath/StandardErrorPath = ~/python_work/data/sold-lock/logs/launchd.out.log / .err.log (launchd 는 ~ 를 안 펴므로 절대경로로; 템플릿 안에는 __WORKSPACE__·__HOME__ 자리표시자로 두고 SKILL.md 의 설치 명령이 sed 로 치환해 ~/Library/LaunchAgents/ 에 복사). RunAtLoad false. 이 태스크에서 launchctl load/bootstrap 은 절대 실행하지 않는다(orchestrator 몫).

    SKILL.md (스킬-계약 §SKILL.md 분량 준수, 짧게): frontmatter name sold-lock, description 에 트리거 "판매상품 잠금", "팔린 상품 잠가줘", "sold-lock", "주문상품 잠금 돌려줘" + 매일 00:01 자동 실행 명시. 본문: 무엇을 하는가(전날 결제완료 → 불사자 잠금=숨김), 잠금 판정 규칙 표(사유 코드 ↔ 한국어 설명), 실행법(--date/--dry-run/--markets, 실행 파이썬 .venv/bin/python3), 산출물 3종과 run-dir 표기 `<데이터루트>/sold-lock/<대상날짜>/`(절대경로 박지 않기), 업무판 기록 규칙, 키 정본(시트 이름으로만 참조, ID 미기재)·캐시 위치·시크릿 비출력 원칙, 15-3 같은 정지 마켓은 token_failed 로 기록 후 계속, launchd 설치·해제 명령(sed 치환 → cp → launchctl bootstrap gui/$(id -u) … / bootout, 로그 위치), 반영 기본 자동 근거(사용자 실제 잠금 승인 2026-10-16, _shared/스킬-계약.md §반영은 기본 자동이다). bulsaja-product-lock 와의 관계(같은 hide 흐름 + 판정 가드 추가) 한 줄.
  </action>
  <verify>
    <automated>cd /Users/choiyongsmacbook/Documents/yongtimjang_claudecode/.claude/skills/sold-lock && plutil -lint launchd/com.eroom.sold-lock.plist && grep -q "caffeinate" launchd/com.eroom.sold-lock.plist && grep -q "<integer>1</integer>" launchd/com.eroom.sold-lock.plist && grep -q "launchctl bootstrap" SKILL.md && ! launchctl list | grep -q com.eroom.sold-lock</automated>
  </verify>
  <done>plist lint OK, 00:01·caffeinate -i 포함, 로드 안 된 상태. SKILL.md 에 실행법·판정표·설치/해제 명령 존재, 시트 ID 미기재.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| 스크립트 → 네이버 커머스API | 마켓별 앱 시크릿으로 토큰 발급 (시크릿 유출 위험) |
| 스크립트 → 불사자 MCP | 상품 상태 쓰기(숨김) — 잘못된 상품 잠금 위험 |
| 구글시트/로컬 캐시 → 스크립트 | 키 정본 입력 |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-lct-01 | Information Disclosure | 시크릿 (로그·산출물·토큰 오류문) | mitigate | safe_json/redact 로만 직렬화, issue_token 오류문 redact, 테스트로 산출물·stdout 시크릿 부재 단언, 캐시 chmod 600 |
| T-lct-02 | Tampering | 잘못된 상품 잠금 | mitigate | 1건·스스번호·마켓그룹 경계정규식 3중 가드, 불명은 변경 없음, 쓰기 후 재조회 확인 |
| T-lct-03 | Spoofing | 다른 불사자 계정에 쓰기 | mitigate | 시작 시 닉네임 "부킹" 확인, 불일치·조회실패 exit 3 |
| T-lct-04 | Denial of Service | 한 마켓 실패/레이트리밋 | mitigate | 마켓 단위 try/except, 커머스 백오프, 불사자 0.26초 간격 |
| T-lct-05 | Repudiation | 무엇을 잠갔는지 | mitigate | result.json·new_locks.json(병합 보존)·업무판 1행 |
</threat_model>

<verification>
- `.venv/bin/python3 -m unittest test_sold_lock_rules test_run_sold_lock` 전부 통과
- plist lint 통과, launchctl 에 미로드
- 실 API dry-run(`run_sold_lock.py --dry-run --markets 1-1`)과 launchd load 는 orchestrator 가 수행 — 이 플랜 범위에서 실 잠금 호출 금지
</verification>

<success_criteria>
- 52마켓 대상·전날 KST 범위·판매자상품코드 중복제거·3중 매칭 가드가 코드와 테스트로 고정
- dry-run/실행/재실행 멱등/계정 불일치/시트 실패 경로가 가짜 주입 테스트로 검증
- 시크릿 비노출이 테스트로 단언
- 스킬 폴더(SKILL.md + scripts + launchd 템플릿) 완성, 스케줄 미로드
</success_criteria>

<output>
Create `.planning/quick/261016-lct-sold-lock/261016-lct-SUMMARY.md` when done
</output>
