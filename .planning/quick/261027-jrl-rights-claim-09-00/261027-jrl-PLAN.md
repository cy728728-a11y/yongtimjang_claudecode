---
phase: quick-261027-jrl
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - .claude/skills/rights-claim/SKILL.md
  - .claude/skills/rights-claim/references/소명문구.txt
  - .claude/skills/rights-claim/scripts/run_rights_claim.py
  - .claude/skills/rights-claim/scripts/test_rights_claim.py
  - .claude/lib/eroom_scheduler.py
autonomous: true
requirements: [RIGHTS-CLAIM-AUTO]

must_haves:
  truths:
    - "매일 09:00 예약관리자가 run_rights_claim.py --apply 를 1회 띄운다"
    - "수집함에 새 소명요청 메일이 있으면 신고 상품(+상표명 들어간 복사본)이 불사자에서 MARKET_AND_SOURCE 삭제되고 소명이 고정 문구로 접수된다"
    - "처리 결과(성공/부분/실패+수동처리 정보)가 카톡으로 오고 대장에 한 줄 남는다"
    - "대장 상태가 done 인 대표접수번호는 다시 처리하지 않고, failed/partial 은 다음날 재시도된다"
    - "오늘 건 261022S506292 는 대장에 done 으로 기록돼 첫 09:00 실행에서 재처리되지 않는다"
    - "메일의 권리명으로 불사자 keyword 검색을 하는 코드 경로가 없다"
  artifacts:
    - path: ".claude/skills/rights-claim/scripts/run_rights_claim.py"
      provides: "파서·필터(순수함수) + IMAP/Aside(stdio MCP)/커머스/불사자/카톡 어댑터 + CLI"
      contains: "def parse_mail"
    - path: ".claude/skills/rights-claim/scripts/test_rights_claim.py"
      provides: "순수함수 + 가짜 어댑터 오케스트레이션 테스트"
    - path: ".claude/skills/rights-claim/references/소명문구.txt"
      provides: "고정 소명 문구 424자"
    - path: ".claude/lib/eroom_scheduler.py"
      provides: "JOBS 의 rights-claim daily 09:00"
      contains: "rights-claim"
  key_links:
    - from: ".claude/lib/eroom_scheduler.py"
      to: ".claude/skills/rights-claim/scripts/run_rights_claim.py"
      via: "JOBS cmd ... --apply"
      pattern: "rights-claim/scripts/run_rights_claim.py"
    - from: "run_rights_claim.py"
      to: "/Users/choiyongsmacbook/.local/bin/aside mcp"
      via: "subprocess stdio JSON-RPC → tools/call repl"
      pattern: "notifications/initialized"
    - from: "run_rights_claim.py"
      to: "attr_tag.CommerceApi.get_product / category_gate.delete_batch / sold_lock_rules.redact"
      via: "sys.path 삽입 후 import 재사용"
      pattern: "delete_batch|get_product|redact"
---

<objective>
네이버 권리보호센터 "[권리보호센터]권리침해로 인한 소명요청" 메일을 매일 09:00 무인 처리하는 rights-claim 스킬을 만든다.
흐름: 수집함 IMAP 감지·파싱 → Aside 로 소명페이지 OTP 조회(신고 상품번호) → 커머스API 로 판매자상품코드 → 불사자 원본+상표명 복사본 삭제 → 마켓삭제 확인 폴링 → Aside 로 고정 문구 소명 제출 → 카톡 보고 + 대장 기록.

Purpose: 3일 내 미소명 시 상품조치·몰 폐쇄 위험. 2026-10-27 수동 1회 성공한 절차를 그대로 자동화한다.
Output: `.claude/skills/rights-claim/` 스킬 일체, 예약 작업 1줄, 오늘 건 대장 done 기록.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@./CLAUDE.md
@/Users/choiyongsmacbook/.claude/projects/-Users-choiyongsmacbook-Documents-yongtimjang-claudecode/memory/rights-claim-auto-handling.md

## 오늘 실측 픽스처 (플래너가 세션 기록에서 추출해 둠 — 그대로 쓴다)
- `.planning/quick/261027-jrl-rights-claim-09-00/fixtures/소명문구.txt` — 실제 제출한 문구 원문, 정확히 424자(끝 개행 없음). references/소명문구.txt 로 **바이트 그대로 복사**.
- `.planning/quick/261027-jrl-rights-claim-09-00/fixtures/mail_261022S506292.txt` — 오늘 메일 본문(Gmail 화면 복사본, 텍스트). 파서 fixture.
- `.planning/quick/261027-jrl-rights-claim-09-00/fixtures/explains_snapshot_261026X309964.txt` — OTP 후 소명페이지 스냅샷. 신고대상 6개 상품번호·항목 텍스트, 소명란 placeholder, '서약 및 동의' checkbox/label, '소명 접수하기'(체크 전 disabled) 확인용.

실측 사실 (픽스처에서 확인된 것):
- 메일: 신고자 `[원일산업]`, 권리 `대한민국 등록권리 (물레방아MULLEBANGA)(400231875)`, 대표접수번호 `[261022S506292]`, 링크 `https://right.naver.com/otp?code=...=`(base64, `=` 포함), 링크 다음 줄에 6자리 OTP `463355`, To `yjzcompany`.
- OTP 후 URL 은 `/explains/261026X309964?type=PAY` — **대표접수번호(261022S…)와 다른 개별 접수번호**다. 대장 키는 대표접수번호, 개별번호는 기록용 필드로만 저장.
- 항목 텍스트 형식 `"1. 소형이동식오피스 원형회전식 물레방아커터기 …"` → 번호 뒤 첫 토큰이 스토어명. `~/.eroom/naver-commerce-stores.json` 에 `25-2: 소형이동식오피스` 존재(이름 정확일치 가능, 54개 이름 고유).
- 소명란 textarea placeholder 는 `재게시를 요청하는 이유와 재게시 요청 의사가 있음에 대한 이유 등을 상세하게 기재해 주세요.` (OTP 입력란은 `인증번호를 입력하세요.`). 500자 제한.
- Aside MCP 등록: `~/.claude.json` mcpServers.aside = command `/Users/choiyongsmacbook/.local/bin/aside`, args `["mcp"]`. tool `repl` 인자 `{title, code}`, 결과는 `content[0].text` 에 console.log 출력과 "✔︎ Opened a new tab…" 같은 안내 줄이 섞여 온다 → **센티널 줄(`###RC###` + JSON)로만 파싱**. repl 변수는 같은 aside 프로세스 안에서 호출 간 유지됐다(오늘 `rp` 재사용).

<interfaces>
재사용 대상 (직접 재작성 금지):

10-projects/이메일-자동화/imap_triage.py — `ACCOUNT = "cy728728@gmail.com"`, `get_password()`(키체인), `decode(v)`(헤더 디코드). 모듈이 import 시 같은 폴더의 `rules` 를 import 하므로 forward_codes.py 처럼 그 폴더를 sys.path 에 넣고 `from imap_triage import ACCOUNT, get_password, decode`. 로그인: `imaplib.IMAP4_SSL("imap.gmail.com", 993)`.

.claude/skills/attr-tag/scripts/attr_tag.py — `CommerceApi(client, secrets)`; `get_product(market, no)` 는 채널상품번호→원상품번호 검색 실패 시 `RuntimeError("원상품번호를 찾지 못함 (no)")` (= 이미 삭제됨 판정 근거). `_default_api(secrets)` 가 키정본 시트+캐시로 생성. 이 파일은 import 시 sold-lock/scripts 를 sys.path 에 넣는다.

.claude/skills/sold-lock/scripts/sold_lock_rules.py — `redact(text, secrets)`, `safe_json(obj, secrets)`, `lock_state(item)`(불사자 항목의 잠금=숨김 판정, None=불명).

.claude/skills/sold-lock/scripts/run_sold_lock.py — 계정 확인 패턴: `call("bulsaja_my_profile", {})["닉네임"] == "부킹"` 아니면 종료코드 3. find_by_code 응답 해석은 `bulsaja-detail-page/scripts/ss_index_calls.항목꺼내기(resp, label)`.

.claude/skills/bulsaja-category-fix/scripts/category_gate.py — `DELETE_ARGS = {"scope":"ALL","deleteAction":"MARKET_AND_SOURCE"}`, `delete_batch(mcp, product_ids, log)` → `[{productId, 판정(접수/잠금/이미없음/미접수/실패), 사유, taskId}]` (confirm=true → confirmationToken → 재제출, 실측 검증된 해석기).

.claude/lib/eroomlib — `from eroomlib.bulsaja import BulsajaMCP` (`open()`, `call_tool(name, args)`, `close()`), `from eroomlib.config import cfg` (`cfg("paths.data_root", required=True)`), `from eroomlib import kakao` (`kakao.send_me(text, link=...)` — 200자 초과 시 잘림, link 인자에 URL 별도 전달 가능).

.claude/lib/eroom_scheduler.py — `PY`, `JOBS` 리스트(dict: name, kind, at, cmd[, caffeinate]).
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: 고정 문구 + 순수함수(파서·필터·대장·보고문) TDD</name>
  <files>.claude/skills/rights-claim/references/소명문구.txt, .claude/skills/rights-claim/scripts/run_rights_claim.py, .claude/skills/rights-claim/scripts/test_rights_claim.py</files>
  <behavior>
    - parse_mail(본문 fixture 텍스트, to="yjzcompany", date=…) → reporter="원일산업", right_name="물레방아MULLEBANGA", right_no="400231875", receipt="261022S506292", link 가 `https://right.naver.com/otp?code=` 로 시작하고 `=` 로 끝남, otp="463355". 같은 내용을 `<p>`/`<a href=…>`/`&amp;`/`<br>` 로 감싼 HTML 판도 동일 결과. 필수값(receipt·link·otp) 누락 시 None 또는 예외 대신 `{"error": ...}` 형태로 표시.
    - is_claim_mail(from, subject): 발신 nv_shopping_ips@navercorp.com + 제목에 "소명요청" → True. "접수 결과" 등 다른 제목 → False.
    - parse_targets(repl 출력 텍스트): `###RC###{json}` 센티널 줄만 읽어 [{no:"13738816405", store:"소형이동식오피스", title:…}] 6건(스냅샷 fixture 기반 JSON). 센티널 없으면 빈 리스트+오류.
    - right_tokens("물레방아MULLEBANGA") == ["물레방아","MULLEBANGA"]; 한글/영문 run 분리, 2자 미만 버림, 숫자 무시.
    - filter_copies(items, tokens, exclude_pids): 상품명에 토큰 중 하나라도(대소문자·공백 무시) 들어간 항목만, 이미 원본으로 잡힌 productId 제외, 중복 productId 1회.
    - store_market(name, stores_dict) → "25-2"; 없으면 None.
    - ledger_should_skip(rows, receipt): 해당 receipt 의 **마지막** 행 status=="done" 일 때만 True (failed/partial → False).
    - load_appeal_text(): references/소명문구.txt 읽어 len==424 이고 <=500 (500 초과면 AssertionError).
    - build_report(result): 성공 시 접수번호·신고자·권리명·삭제 N(복사본 M, 잠금 K)·마켓삭제확인 여부·"소명 완료" 포함; 실패 시 "수동 처리 필요"+실패 단계+OTP 포함하고 소명링크는 send_me 의 link 인자로 넘기도록 (text, link) 튜플 반환. text 200자 이내.
  </behavior>
  <action>
fixtures/소명문구.txt 를 references/소명문구.txt 로 바이트 그대로 복사(cp). run_rights_claim.py 상단에 순수함수 구역을 만든다(한국어 주석, 외부 호출 없음): parse_mail, html_to_text(html.parser 또는 re 로 태그 제거 + html.unescape, br/p/div 는 개행), is_claim_mail, parse_targets, right_tokens, filter_copies, store_market, ledger_should_skip, load_appeal_text, build_report 위 behavior 대로. parse_mail 정규식은 공백·개행·HTML 잔여에 관대하게(신고자 `신고자\s*\[(.+?)\]`, 권리명은 "등록권리" 뒤 첫 괄호쌍과 이어지는 숫자 괄호, 대표접수번호 `대표접수번호\s*\[([0-9A-Z]+)\]`, 링크는 원문 HTML href 에서도 찾고 unescape, OTP 는 링크 위치 이후 첫 독립 6자리 숫자). 상수: CLAIM_FROM, CLAIM_SUBJECT_KEY="소명요청", SENTINEL="###RC###", APPEAL_MAX=500, SUCCESS_TEXT_NOSPACE="권리소명이접수되었어요"(공백 제거 비교).
테스트는 unittest(기존 스킬 test_*.py 관례)로 fixtures 디렉터리의 mail/snapshot 파일을 읽어 쓴다 — 테스트 파일 안에 경로 상수로 `.planning/quick/261027-jrl-rights-claim-09-00/fixtures` 를 쓰지 말고, 메일 텍스트·신고대상 JSON 6건은 테스트 파일 안에 리터럴로 옮겨 넣어 스킬이 자립하게 한다. 이 태스크에서는 main/CLI 없이 함수만(Task 2 가 같은 파일에 이어 붙임). RED→GREEN 순서로 커밋.
  </action>
  <verify>
    <automated>cd /Users/choiyongsmacbook/Documents/yongtimjang_claudecode && .venv/bin/python3 -m pytest .claude/skills/rights-claim/scripts/test_rights_claim.py -q && .venv/bin/python3 -c "s=open('.claude/skills/rights-claim/references/소명문구.txt',encoding='utf-8').read(); assert len(s)==424, len(s)"</automated>
  </verify>
  <done>순수함수 테스트 전부 통과, 소명문구 424자, 외부 호출 0.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: 어댑터(IMAP·Aside stdio MCP·커머스·불사자·카톡) + 오케스트레이션 + CLI</name>
  <files>.claude/skills/rights-claim/scripts/run_rights_claim.py, .claude/skills/rights-claim/scripts/test_rights_claim.py</files>
  <behavior>
    - 가짜 어댑터 주입 run(args, deps): --dry-run 이면 삭제(delete_batch)·소명제출·kakao 호출 0회, 대장 쓰기 0회, 조회 결과(대상 상품·판매자코드·복사본·잠금)는 출력.
    - --apply 정상: 원본+복사본 productId 로 삭제 1배치, 잠금 항목은 삭제 목록에서 빠지고 보고 K 에 집계, 소명 제출 호출 1회, kakao 1회, 대장 status=done 1행.
    - 소명 제출 실패(성공 텍스트 미확인) → status=failed, kakao text 에 "수동 처리 필요"+OTP, link=소명링크.
    - 삭제 일부 실패 또는 마켓삭제 미확인이지만 소명 성공 → status=partial(다음날 재시도 대상), 보고에 "마켓삭제 미확인" 표시.
    - 대장에 done 인 receipt 는 건너뜀; --receipt X 는 done 여부와 무관하게 X 만 처리(dry-run 포함).
    - --mark-done X → 대장에 {receipt:X, status:"done", source:"manual"} 1행 append, 외부 호출 0.
    - 커머스 조회가 "원상품번호를 찾지 못함" → 그 상품은 already_deleted 로 표시하고 불사자 삭제 목록엔 넣지 않되 소명은 진행.
    - 코드 전체에 불사자 keyword/검색 계열 tool 호출이 없다 (테스트: 가짜 불사자가 find_by_code·market_delete·my_profile 외 tool 이름을 받으면 실패).
  </behavior>
  <action>
같은 파일에 어댑터 클래스 + run() + main() 을 이어 붙인다. 각 외부 호출은 try-except 로 감싸 단계명(mail/aside_lookup/commerce/bulsaja_find/delete/confirm/appeal/kakao)과 redact 된 오류를 result 에 남긴다. 로그는 attr_tag._Log 처럼 SR.redact(msg, secrets) 경유 print(flush=True); secrets 에는 IMAP 비밀번호·커머스 시크릿/토큰·OTP·소명링크 code 값을 넣는다(카톡 본문의 OTP 는 의도된 노출이므로 로그만 마스킹).

어댑터:
(a) MailSource — imap_triage 재사용(sys.path 에 10-projects/이메일-자동화). INBOX(+ "[Gmail]/All Mail" 은 불필요, INBOX 만)에서 `SINCE <since-days 전>` + `FROM "nv_shopping_ips@navercorp.com"` SEARCH, 헤더 Subject/To/Date 디코드 후 is_claim_mail 통과분만 본문(text/html 우선, 없으면 text/plain; charset 디코드) → parse_mail. 읽음 표시 바꾸지 않게 BODY.PEEK[] 사용. logout 은 finally.
(b) AsideMCP — `/Users/choiyongsmacbook/.local/bin/aside mcp` 를 subprocess.Popen(stdin/stdout PIPE, text, bufsize=1) 로 띄우는 최소 stdio JSON-RPC 클라이언트(claude -p 금지). 줄 단위 JSON: initialize(protocolVersion "2025-06-18", capabilities {}, clientInfo {name:"rights-claim"}) → 응답 대기 → notifications/initialized 통지 → tools/call name="repl" arguments={title, code}. 응답은 id 일치하는 줄만 채택(그 외 통지·로그 줄은 무시), 읽기 타임아웃(스레드+queue, 기본 120초), isError 이면 예외. close() 는 terminate→wait(5)→kill. 결과 텍스트는 content 의 text 들을 이어붙여 반환.
   repl JS 는 문자열 템플릿으로 조립하되 링크·OTP·문구는 json.dumps 로 이스케이프해 주입. ref 하드코딩 금지 — 셀렉터만: lookup 단계 = `globalThis.rcPage = await openTab(link)` → `rcPage.getByPlaceholder('인증번호를 입력하세요.').fill(otp)` → `rcPage.getByRole('button',{name:'확인'}).click()` → `/explains/` URL 대기(최대 15초, sleep 루프) → `a[href*="smartstore.naver.com/main/products/"]` 를 순회하며 각 링크의 상품번호와 직전 항목 텍스트(링크의 이전 형제/부모 블록 텍스트 중 `^\d+\.` 로 시작하는 것)를 모아 `console.log('###RC###'+JSON.stringify({url, explainNo, targets}))`. appeal 단계 = rcPage 가 살아있고 소명란이 보이면 재사용, 아니면 lookup 과 같은 방식으로 재오픈+OTP 후 진행 → `getByPlaceholder('재게시를 요청하는 이유')` fill(문구) → label '서약 및 동의' 클릭 후 `getByRole('checkbox',{name:'서약 및 동의'})` 가 checked 아니면 `.check({force:true})` → `getByRole('button',{name:'소명 접수하기'})` 활성 대기 후 click → 최대 15초 동안 본문 텍스트(공백 제거)에 SUCCESS_TEXT_NOSPACE 포함 확인 → 센티널로 {ok, url} 출력 → 성공 시 closeTab(rcPage). 실패 시 `rcPage.screenshot({path})` 시도(경로 `<data_root>/rights-claim/shots/<receipt>_<ts>.png`)하고 경로를 result 에 기록. dry-run 은 lookup 까지만, --no-browser 면 Aside 단계 전부 생략(신고대상 비어 있음으로 진행·보고).
   스토어명 신뢰: targets 의 store 가 stores.json 이름과 정확히 일치하면 그 마켓, 아니면 stores.json 전 마켓을 순회하며 get_product 성공하는 첫 마켓(폴백, 결과에 fallback 표시).
(c) Commerce — attr_tag 를 import(SKILLS_DIR/attr-tag/scripts 를 sys.path) 해 `_default_api(secrets)` 생성. get_product → originProduct.detailAttribute.sellerCodeInfo.sellerManagementCode, statusType 기록. "원상품번호를 찾지 못함" RuntimeError → already_deleted.
(d) Bulsaja — eroomlib.bulsaja.BulsajaMCP open/close, 계정 닉네임 "부킹" 확인(--expect-nick, 불일치면 bulsaja 단계 failed 로 중단하되 카톡 보고는 보냄). find_by_code(판매자상품코드들) → productId·불사자코드·상품명·lock_state; 이어 find_by_code(불사자코드들) → filter_copies(right_tokens(right_name)). 잠금(lock_state True) 은 삭제 제외·K 집계. dry-run 은 여기까지 + market_delete 를 confirm 없이 1회 호출해 미리보기 응답 요약만 출력(이것은 쓰기 아님 — 응답에 confirmationToken 이 오더라도 재제출 금지). --apply 는 category_gate.delete_batch(mcp, pids) 로 confirm→token→재제출(사용자 승인 흐름의 2·3단계, 1단계가 위 미리보기).
(e) 마켓삭제 확인 — 원본 상품번호마다 30초 간격 최대 20회(약 10분) get_product 재조회; "원상품번호를 찾지 못함" 또는 statusType != "SALE" 이면 확인. 미확인이어도 소명으로 진행. sleep 은 주입(테스트에서 0).
(f) Kakao — eroomlib.kakao.send_me(text, link) ; 실패는 로그만(종료코드엔 반영 X).

대장: `<data_root>/rights-claim/ledger.jsonl` (cfg("paths.data_root")), 행 = {ts, receipt, explain_no, reporter, right_name, to, mail_date, status, deleted, copies, locked, already_deleted, market_confirmed, appeal_ok, fail_stage, shot}. 디렉터리 없으면 생성, append 후 flush. 동시실행 방지: 같은 폴더 `.lock` 파일을 fcntl.flock(LOCK_EX|LOCK_NB) — 실패 시 "다른 실행 중" 종료코드 4.

CLI(argparse): `--dry-run` / `--apply`(상호배타, 둘 다 없으면 dry-run 으로 동작하고 안내), `--since-days`(기본 14), `--receipt`, `--mark-done`, `--no-browser`, `--expect-nick`(기본 "부킹"). 대상 메일 0건이면 카톡 없이 "새 소명요청 없음" 출력 후 종료코드 0. 실패 건이 하나라도 있으면 종료코드 1. 예약 실행에서 맥북 잠자기 방지가 필요할 수 있으니 JOBS 에서 caffeinate:True 로 감싼다(Task 3).

테스트(같은 test 파일에 추가): FakeMail/FakeAside/FakeCommerce/FakeBulsaja/FakeKakao/임시 data_root 를 주입해 behavior 항목 전부 검증. 실제 IMAP·Aside·커머스·불사자·카톡에 연결하는 코드는 테스트에서 절대 실행되지 않게 deps 기본값은 main() 에서만 만든다.
  </action>
  <verify>
    <automated>cd /Users/choiyongsmacbook/Documents/yongtimjang_claudecode && .venv/bin/python3 -m pytest .claude/skills/rights-claim/scripts/test_rights_claim.py -q && ! grep -v '^\s*#' .claude/skills/rights-claim/scripts/run_rights_claim.py | grep -nE '"(keyword|searchKeyword)"\s*:|bulsaja_product_search|bulsaja_product_list|\["claude"' && grep -c "notifications/initialized" .claude/skills/rights-claim/scripts/run_rights_claim.py</automated>
  </verify>
  <done>오케스트레이션 테스트 통과(dry-run 무쓰기, apply 정상/부분/실패, mark-done, done 스킵, 검색 tool 미사용). keyword 인자·검색 tool·claude CLI 호출 코드 없음(주석·docstring 언급은 무방). stdio 핸드셰이크 구현됨.</done>
</task>

<task type="auto">
  <name>Task 3: SKILL.md + 예약 등록 + 오늘 건 done 기록 + 실측 dry-run</name>
  <files>.claude/skills/rights-claim/SKILL.md, .claude/lib/eroom_scheduler.py</files>
  <action>
(1) SKILL.md 작성(sold-lock SKILL.md 형식): frontmatter name: rights-claim, description 에 "네이버 권리보호센터 소명요청 메일을 감지해 신고 상품을 불사자에서 삭제하고 고정 문구로 소명을 접수한 뒤 카톡 보고한다. 매일 09:00 예약 실행." + 트리거 "권리침해 메일 처리", "소명요청 처리", "권리보호센터", "소명 처리해줘". 본문: 무엇을 하나(①~⑦ 흐름), CLI 표(--dry-run/--apply/--since-days/--receipt/--mark-done/--no-browser/--expect-nick), 안전 규칙(메일 권리명으로 불사자 검색 금지 — 물레방아 분수대 사고, 잠금 상품 삭제 제외, Aside 쓰기 예외는 right.naver.com 소명 페이지 한정, 실패 시 카톡의 링크+OTP 로 수동 처리), 대장 경로·상태 의미(done 만 건너뜀), 종료코드(0/1/3/4), 수동 처리 시 `--mark-done` 사용법. 메모리 파일 rights-claim-auto-handling 링크.
(2) eroom_scheduler.JOBS 의 auto-watch 다음에 `{"name": "rights-claim", "kind": "daily", "at": "09:00", "cmd": [PY, ".claude/skills/rights-claim/scripts/run_rights_claim.py", "--apply"], "caffeinate": True}` 1줄 추가(마켓삭제 확인 폴링 최대 10분이라 caffeinate). 다른 작업은 건드리지 않는다.
(3) 실행: `.venv/bin/python3 .claude/skills/rights-claim/scripts/run_rights_claim.py --mark-done 261022S506292` → 대장에 done 1행.
(4) 실측 검증(쓰기 0): `--dry-run --receipt 261022S506292 --no-browser` 로 실제 수집함 IMAP 에서 오늘 메일을 찾아 parse_mail 결과(신고자 원일산업·권리명·권리번호·대표접수번호·링크 앞부분·OTP 마스킹·To)가 출력되는지 확인. **Aside 소명페이지 재접속 금지(이미 접수된 링크), 삭제·소명·카톡 실행 금지.** 불사자/커머스 단계는 신고대상이 비어 있으므로 호출되지 않아야 한다. 파싱 실패 시 실제 메일 본문 구조(HTML)에 맞게 parse_mail 을 고치고 해당 HTML 조각을 테스트 fixture 로 추가한 뒤 재실행. 이어 `--dry-run`(receipt 지정 없이) 실행 시 261022S506292 가 "대장 done — 건너뜀" 으로 나오는지 확인.
(5) 스케줄러 문법 확인: JOBS 를 import 해 rights-claim 항목이 있는지 출력.
  </action>
  <verify>
    <automated>cd /Users/choiyongsmacbook/Documents/yongtimjang_claudecode && .venv/bin/python3 -c "import sys; sys.path.insert(0,'.claude/lib'); import eroom_scheduler as s; j=[x for x in s.JOBS if x['name']=='rights-claim'][0]; assert j['at']=='09:00' and j['cmd'][-1]=='--apply'; print('ok')" && .venv/bin/python3 -c "import sys,os,json; sys.path.insert(0,'.claude/lib'); from eroomlib.config import cfg; p=os.path.join(os.path.expanduser(cfg('paths.data_root')),'rights-claim','ledger.jsonl'); rows=[json.loads(l) for l in open(p)]; assert any(r['receipt']=='261022S506292' and r['status']=='done' for r in rows); print('ledger ok')" && .venv/bin/python3 .claude/skills/rights-claim/scripts/run_rights_claim.py --dry-run --receipt 261022S506292 --no-browser 2>&1 | grep -E "원일산업|261022S506292"</automated>
  </verify>
  <done>SKILL.md 존재(트리거 4종 포함), JOBS 에 rights-claim 09:00 --apply, 대장에 261022S506292 done, 실제 수집함 dry-run 에서 오늘 메일 파싱 확인, 쓰기·Aside 접속·카톡 0회.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| 수집함 메일 → 스크립트 | 외부(네이버 사칭 가능) 메일 본문을 파싱해 링크를 브라우저로 연다 |
| 소명페이지 DOM → 삭제 대상 | 페이지가 준 상품번호로 실제 불사자 삭제가 일어난다 |
| 스크립트 → 로그/대장/카톡 | IMAP 비밀번호·커머스 시크릿·토큰·OTP 가 새어나갈 수 있다 |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-jrl-01 | Spoofing | is_claim_mail/parse_mail | mitigate | 발신 주소 정확일치 + 링크는 `https://right.naver.com/otp?code=` 접두만 허용(그 외 도메인이면 failed, 브라우저 미오픈) |
| T-jrl-02 | Tampering | 삭제 대상 결정 | mitigate | 대상은 소명페이지 상품번호→커머스 sellerManagementCode→find_by_code 체인만. 권리명 keyword 검색 코드 없음(verify grep). 복사본은 같은 불사자코드+상품명 토큰 일치만. 잠금 상품 제외 |
| T-jrl-03 | Information Disclosure | 로그·대장·스크린샷 | mitigate | SR.redact 로 비밀번호·시크릿·토큰·OTP·code 마스킹, 대장엔 링크 저장 안 함(receipt 만). 카톡 OTP 는 실패 시 수동처리용 의도 노출(본인 나와의 채팅) |
| T-jrl-04 | Repudiation | 처리 이력 | mitigate | ledger.jsonl append-only, 단계별 fail_stage·삭제 판정 기록 |
| T-jrl-05 | Denial of Service | 중복/동시 실행 | mitigate | fcntl 락(종료코드 4), done 스킵으로 재처리 방지, 마켓 확인 폴링 상한 10분 |
| T-jrl-06 | Elevation of Privilege | Aside 쓰기 범위 | accept | 메모리 rights-claim-auto-handling 의 사용자 허용 예외(right.naver.com 소명 제출 한정). 다른 네이버 쓰기 경로 없음 |
</threat_model>

<verification>
- pytest test_rights_claim.py 전부 통과
- 실제 수집함 dry-run(--no-browser)에서 오늘 메일 파싱 확인, 대장 done 스킵 확인
- 검증 중 실제 삭제·소명제출·카톡 발송·소명페이지 재접속 0회
- eroom_scheduler JOBS 에 rights-claim 09:00 --apply
</verification>

<success_criteria>
다음날 09:00 부터 새 소명요청 메일이 오면 사람 손 없이 삭제+소명+카톡 보고가 이뤄지고, 실패 시 카톡에 링크·OTP·실패 단계가 와서 수동 처리할 수 있다. 오늘 건은 재처리되지 않는다.
</success_criteria>

<output>
Create `.planning/quick/261027-jrl-rights-claim-09-00/261027-jrl-SUMMARY.md` when done
</output>
