---
phase: quick-261016-wbc
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - .claude/skills/naver-ads-weekly/scripts/ads_rules.py
  - .claude/skills/naver-ads-weekly/scripts/test_ads_rules.py
  - .claude/skills/naver-ads-weekly/scripts/run_ads.py
  - .claude/skills/naver-ads-weekly/scripts/sheets_out.py
  - .claude/skills/naver-ads-weekly/scripts/report_md.py
  - .claude/skills/naver-ads-weekly/scripts/bulsaja_join.py
  - .claude/skills/naver-ads-weekly/scripts/test_bulsaja_join.py
  - .claude/skills/naver-ads-weekly/scripts/weekly_monday.py
  - .claude/skills/naver-ads-weekly/scripts/test_weekly_monday.py
  - .claude/skills/naver-ads-weekly/launchd/com.eroom.ads-weekly.plist
  - .claude/skills/naver-ads-weekly/SKILL.md
  - .claude/skills/naver-ads-weekly/references/규칙-판정기준.md
autonomous: true
requirements: [ADS-W7a, ADS-W7b, ADS-W7c, ADS-W7d, ADS-JOIN, ADS-OUT, ADS-BOARD, ADS-MONDAY]

must_haves:
  truths:
    - "run 이 전 계정 합산 1개 풀(7일 노출 ≥ 50)에서 CTR 하위 10%(⑦b)·상위 10%(⑦c 후보)를 ceil(풀×0.10)건씩 뽑아 result.json 에 싣는다"
    - "run 이 30일 클릭 ≥ 20 게재중 소재 전체를 구매 여부와 무관하게 ⑦d 후보로 싣는다"
    - "enrich 가 ⑦c 후보·⑦d 후보에만 불사자를 조회해 판매자상품코드·상세상태·옵션상태를 붙이고, 못 이은 행은 '불사자 미매칭: <사유>'로 남긴다"
    - "apply --sheet 가 ⑦b썸네일변형·⑦c상세꾸미기·⑦d정비점검 탭에 append 하고 ②썸네일교체·④효자후보 탭에는 더 이상 쓰지 않는다"
    - "weekly_monday.py 가 prep→run→enrich→apply→bids --commit→prune --commit→업무판 순으로 돌고, 앞 단계가 하나라도 실패하면 bids/prune 을 건너뛰고 업무판에 실패를 적는다"
    - "기존 test_ads_rules/test_bids/test_prune/test_ledger/test_nvad/test_reports 가 그대로 통과한다"
  artifacts:
    - path: ".claude/skills/naver-ads-weekly/scripts/ads_rules.py"
      provides: "⑦ 상수(POP_IMP_MIN·CTR_TAIL_PCT·MAINT_CLICK_MIN) + pool_rows·ctr_tail·split_global·final_7c·maintenance_verdict 순수함수 + classify 의 ⑦d후보 키"
      contains: "CTR_TAIL_PCT"
    - path: ".claude/skills/naver-ads-weekly/scripts/bulsaja_join.py"
      provides: "⑦c/⑦d 후보 → 불사자 조인·상세상태·옵션상태 보강, run-dir 캐시"
    - path: ".claude/skills/naver-ads-weekly/scripts/weekly_monday.py"
      provides: "월요일 자동 실행 래퍼 + 업무판 1행"
    - path: ".claude/skills/naver-ads-weekly/launchd/com.eroom.ads-weekly.plist"
      provides: "월 07:00 caffeinate -i 템플릿 (load 안 함)"
      contains: "Weekday"
  key_links:
    - from: "bulsaja_join.py"
      to: "webapp/join.py · webapp/state.py"
      via: "sys.path 에 저장소 루트를 넣고 from webapp import join, state (market_number·group_index·재검증판정·상세상태 재사용)"
      pattern: "from webapp import"
    - from: "run_ads.py cmd_run"
      to: "ads_rules.split_global"
      via: "계정 루프 뒤 전 계정 풀로 한 번 계산해 각 계정 rules 에 되돌려 넣는다"
      pattern: "split_global"
    - from: "weekly_monday.py"
      to: "run_ads.py 서브커맨드"
      via: "subprocess(.venv python) 단계별 종료코드 검사"
      pattern: "run_ads.py"
---

<objective>
naver-ads-weekly 의 규칙 체계를 ⑦(a/b/c/d)로 개편하고, 매주 월요일 07:00 무인 실행 경로(래퍼 + launchd 템플릿)를 만든다. 첫 실전은 2026-10-19(월).

Purpose: 썸네일·상세·옵션 작업 대상을 "전 계정에서 노출이 잘 되는 소재의 CTR 양 끝단"과 "클릭 20+ 상품의 정비 상태"로 좁혀, 용팀장이 월요일 아침 시트만 열면 이번 주 할 일이 판매자상품코드로 나와 있게 한다.
Output: 개편된 ads_rules/run_ads/sheets_out/report_md, 새 bulsaja_join.py(enrich)·weekly_monday.py·launchd plist, 갱신된 SKILL.md·규칙-판정기준.md, 새 단위테스트.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@./CLAUDE.md
@.claude/skills/naver-ads-weekly/SKILL.md
@.claude/skills/naver-ads-weekly/scripts/ads_rules.py
@.claude/skills/naver-ads-weekly/scripts/run_ads.py
@.claude/skills/naver-ads-weekly/scripts/sheets_out.py
@.claude/skills/naver-ads-weekly/scripts/report_md.py

<user_decisions>
2026-10-16 용팀장 확정 (이 표가 정본이다 — 바꾸지 마라)

| 규칙 | 조건 | 결과 |
|---|---|---|
| ⑦a (=기존 ①) | 7일 노출 0 (게재중·검수대기 제외) | 입찰 +10원 — 기존 `bids` 그대로. result.json 키 `①노출0` 이름 유지(bids 가 읽는다) |
| ⑦b (② 대체) | 7일. 모집단 = 7일 노출 ≥ 50 인 게재중 소재(전 계정 합산 1풀). CTR 오름차순·동률은 노출 많은 순, 개수 = ceil(모집단×0.10) | 썸네일 변형 리스트 |
| ⑦c (④ 대체) | 같은 모집단 CTR 상위 10%(내림차순·동률 노출 많은 순) → 그중 상세 미가공(중국어원본/단순번역)만 | 상세 꾸미기 리스트 |
| ⑦d (신규) | 30일 클릭 ≥ 20 전체(구매 무관) | 상세+옵션명 정비 점검 — 상세미가공·옵션명미정리 표시, 둘 다 OK 면 '정비완료' |
| ③ ⑤ ⑥ | 그대로 | |

- 50·10%·20 은 ads_rules.py 상수 한 곳(2~3주 뒤 조정 예정).
- 조인: 광고그룹명 NN-N → 불사자 마켓그룹 `용쌤NN-N` → 그 그룹 안에서 상품명으로 1건. webapp/join.py 재사용(복제 금지). 실패는 '불사자 미매칭'.
- 상세 미가공 판정: webapp/state.py 재사용. 옵션명 미정리: option-cleanup 기작업 기록이 있으면 재사용, 없으면 '판정 불가'(추측 금지).
- 불사자 조회는 ⑦c 후보·⑦d 후보에만, 캐시는 run-dir.
- 시트 원장 1-oSQepeUGbdmRfSizJHUIjgHu-UYxMtyS504mzDeJKI 에 탭 ⑦b썸네일변형·⑦c상세꾸미기·⑦d정비점검 추가, ②·④ 탭 쓰기 중단(과거 행 보존). 사람이 볼 표기에 판매자상품코드.
- 보고서는 구매완료 기준 숫자만 — '장바구니'·'총전환'·'add_to_cart' 금지(기존 규칙).
- 업무판(workspace.toml sheets.work_board) '오늘' 탭 1행, 실패해도 본 작업 유지.
- 월요일 래퍼: prep → run → apply --sheet → bids --commit → prune --commit → 업무판. 입찰 +10 자동 적용 OK(되돌리기 bids --revert). 실패 시 이후 쓰기 단계(bids/prune) 스킵 + 업무판에 실패 기록. launchd 템플릿만, load 금지.
</user_decisions>

<planner_decisions>
(Claude 재량 — 근거 포함)
- P-1 조인 방식 충돌 처리: webapp/join.py 머리말 D-03 은 "상품명 매칭 금지(실측 6건 중 2건 깨짐)"다. 용팀장이 이번에 명시적으로 상품명 매칭을 지정했으므로 **용팀장 지시를 따른다.** 대신 깨짐을 줄이는 장치 2개: (a) 그룹 안에서 정규화(공백 제거·전각/반각 무시 없이 strip+연속공백 1칸) 후 **정확히 1건 일치만** 히트, 0건 '미스', 2건 이상 '중복'으로 미매칭 처리 (b) 히트 행에 `번호검증` = join.재검증판정(광고 mallProductId, 불사자 workdata 의 스스번호, False) 결과(히트/불일치/미조회)를 증거로 싣는다(차단하지 않는다 — 물갈이로 번호만 바뀐 같은 상품일 수 있다). join.py 자체는 고치지 않는다(웹앱 테스트 보존).
- P-2 상품명 매칭 함수는 join.py 에 없는 새 로직이라 bulsaja_join.py 에 둔다. market_number·group_index·재검증판정·state.상세상태·state.불리언정규화 는 import 재사용.
- P-3 옵션명 미정리 판정 원천 = eroomlib.matrix 현황판(그룹 시트 `00_진행` 탭 `옵션` 열). option-cleanup 이 저장 후 이 열을 `완료` 로 찍는 기존 기록이다. 매핑: `완료`·`해당없음` → 정리완료 / 빈칸·`재작업(...)`·그 밖 진행값 → 미정리 / 그룹 시트 없음·상품 행 없음·읽기 실패 → '판정 불가'. option_rules.name_problems 로 이름을 재채점하지 않는다(정리 완료 여부의 기록이 아니라 추측이 된다).
- P-4 ⑦c 최종 리스트 = 상위 10% 후보 중 (히트 & 상세상태 ∈ {중국어원본, 단순번역만}) ∪ (미매칭 행 — '불사자 미매칭' 라벨로 남김). 히트 & AI가공완료 는 제외.
- P-5 ⑦b 는 불사자를 조회하지 않으므로(사용자 지정) 판매자상품코드 열이 없다 — 광고그룹·스토어상품ID 로 표기한다.
- P-6 ②④ 는 classify 결과(result.json)에는 계속 남긴다 — test_ads_rules·웹앱이 키를 읽는다. 시트 탭 쓰기와 report 섹션만 뺀다.
- P-7 래퍼의 실패 정책: enrich 실패도 "앞 단계 실패"로 본다(사용자 문구 그대로 엄격 적용) → bids/prune 스킵. apply 는 enrich 실패여도 돌린다(읽기·시트 기록이라 ⑦c/⑦d 가 '불사자 미조회'로 남는다).
- P-8 시트 ID: 래퍼 `--sheet` 기본값 = cfg("sheets.naver_ads") 있으면 그것, 없으면 상수 `DEFAULT_SHEET = "1-oSQepeUGbdmRfSizJHUIjgHu-UYxMtyS504mzDeJKI"` (workspace.toml 은 git 밖이라 수정하지 않는다).
</planner_decisions>

<interfaces>
기존 계약 (그대로 쓴다)

ads_rules.py
- 상수 IMP_MIN=100, CLICK_MIN=20, CTR_LOW=1.0, CTR_HIGH=2.0, INSPECT_WAITING
- live_ads(ads), ad_info(ad, group_name, group_bid) → {adId, adGroup, title, mallProductId, bid, useGroupBid, groupBid}
- _with_stat(info, s) → + {imp, clk, ctr, rank, cost}   (s 는 /stats 행: impCnt, clkCnt, ctr, avgRnk, salesAmt)
- classify(ads, group_of, stats_7d, stats_30d, purchases) → {"①노출0","②썸네일교체","③원인분석","④효자후보","⑤효자확정","⑥삭제대상","_summary"}

run_ads.py
- run_dir_of(name) → data_root()/naver-ads/runs/<name|오늘>; accounts/<alias>/{ads.json(ads,groups), stats_7d.json, stats_30d.json, purchase.json}
- cmd_run 이 result.json = {"generated", "accounts": {alias: {"summary", "rules"}}} 를 쓴다
- bids 는 rules["①노출0"] 만 읽는다. prune 은 run_dir 의 accounts/ 를 읽는다
- bids.run_bids 반환: {"plans","counts","committed",("failed"|"aborted")}

webapp/join.py (CLI venv 에서 import 확인됨: 저장소 루트를 sys.path 에 넣고 from webapp import join, state)
- join.market_number(ad_group_name) -> "NN-N" | None
- join.group_index(groups) -> {번호: 그룹dict}   (그룹 dict 의 키 "그룹명")
- join.재검증판정(인덱스_smartstore, 관측_smartstore, 미조회) -> "히트"|"미스"|"불일치"|"미조회"
- join.strip_display_rules(obj)
webapp/state.py
- state.상세상태(uploadDetailContents) -> "AI가공완료"|"단순번역만"|"중국어원본"   (dict 아니어도 예외 없음)
- state.불리언정규화(v) -> bool

불사자 접근 (sold-lock 이 쓰는 검증된 경로 — run_sold_lock.py 45~215행 참고)
- MCP: from eroomlib.snapshot import ProductMCP; mcp = ProductMCP(); mcp.open(); mcp.call_tool(name, args); mcp.close()
- 레이트 간격 0.26초(초당 4회), 응답은 표시규칙 재귀 제거
- bulsaja_my_profile → {"닉네임"} — 기대값 "부킹"(용쌤 그룹이 있는 계정). 불일치면 enrich 전체 중단
- bulsaja_market_groups → {"그룹":[{"groupId","그룹명"}]}
- ProductMCP.collect_group(group_id) → [{"productId","상품명","상태코드","잠금"}]
- bulsaja_product_workdata {"productId", "mode":"full"} → 응답 해석은 bulsaja-detail-page/scripts/ss_index_calls.워크데이터꺼내기 (sold-lock `_calls()` 지연 import 관용구). data 의 uploadDetailContents(상세상태 입력) · uploadBulsajaCode(= 판매자상품코드, 메모리 report-with-seller-product-code) · uploadedSuccessUrl.smartstore(스스번호, sold-lock 의 R.extract_ss_no 로 추출)
- eroomlib.matrix: index_groups() -> [(그룹명, 시트ID)], read(sheet) -> {상품id: {"옵션": 값, ...}}, DONE="완료", NA="해당없음", is_redo(v)

업무판 기록 (run_sold_lock.py 415~434행 패턴 그대로)
- board_get(work_board_id, "'오늘'!A:A") 로 번호 최대값+1, board_append(work_board_id, "오늘", [row])
- row = [번호, YYYY-MM-DD, ✓칸, 할 일, 업무#, 담당, 출처, 메모, 이월]
- eroomlib.gsheets.append_rows / sheets_get, cfg("sheets.work_board")

launchd 치환 방식: .claude/skills/sold-lock/launchd/com.eroom.sold-lock.plist (__WORKSPACE__/__HOME__ 를 SKILL.md 의 sed 가 치환)

보강 필드 계약 (Task 2 가 ⑦c후보·⑦d후보 행에 붙이고, Task 1 의 출력이 읽는다 — 키 없으면 '불사자 미조회')
- 마켓번호: str|None
- 불사자매칭: "히트" | "미매칭: 추출실패" | "미매칭: 번호없음" | "미매칭: 미스" | "미매칭: 중복" | "미매칭: 조회실패"
- productId, 판매자상품코드: str|None
- 상세상태: "AI가공완료"|"단순번역만"|"중국어원본"|None ; 상세미가공: bool|None (None = 판정 못 함)
- 옵션상태: "정리완료"|"미정리"|"판정 불가" ; 옵션미정리: bool|None
- 번호검증: "히트"|"불일치"|"미조회"
- 정비판정(⑦d 만): maintenance_verdict 결과 문자열
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: ⑦ 규칙 순수함수 + run 전 계정 풀 + 시트/보고서 출력 개편</name>
  <files>.claude/skills/naver-ads-weekly/scripts/ads_rules.py, .claude/skills/naver-ads-weekly/scripts/test_ads_rules.py, .claude/skills/naver-ads-weekly/scripts/run_ads.py, .claude/skills/naver-ads-weekly/scripts/sheets_out.py, .claude/skills/naver-ads-weekly/scripts/report_md.py</files>
  <behavior>
    - pool_rows: 게재중 + 7일 통계 있음 + impCnt ≥ 50 만. 49 는 빠지고 50 은 들어간다. 꺼진 소재·통계 없는 소재 제외
    - ctr_tail(rows, pct=0.10, top=False): 풀 20건 → 2건, 풀 21건 → 3건(ceil), 풀 0건 → [] , 풀 1건 → 1건. 하위는 CTR 오름차순, CTR 동률이면 노출 많은 쪽 먼저. 상위는 CTR 내림차순, 동률 노출 많은 쪽 먼저
    - split_global({alias: pool_rows}): 계정 A 의 CTR 0.1 소재 1건 + 계정 B 의 CTR 0.5 소재 19건 → 하위 2건이 A 1건 + B 1건으로 계정별로 되돌아간다(계정별 계산이 아님을 고정). 각 행에 acct 키가 붙는다
    - classify 가 "⑦d정비점검후보" 를 추가: 30일 clk ≥ 20 인 게재중 소재 전부, 구매 있어도 포함, purCnt(없으면 0) 동반, 클릭 많은 순. 기존 ①~⑥ 키·값은 바이트 단위로 그대로(기존 테스트 무수정 통과)
    - final_7c(rows): 히트+중국어원본/단순번역만 → 포함, 히트+AI가공완료 → 제외, 불사자매칭이 '미매칭:' 으로 시작 → 포함, 보강 키 자체가 없음 → 포함(라벨 '불사자 미조회')
    - maintenance_verdict(row): 미매칭 → "불사자 미매칭"; 상세미가공 False & 옵션미정리 False → "정비완료"; 상세미가공 True → "상세 미가공" 포함; 옵션미정리 True → "옵션명 미정리" 포함(둘 다면 " · " 로 연결); 어느 쪽이든 None 이고 나머지가 OK 면 "판정 불가(옵션)" 또는 "판정 불가(상세)"; 보강 키 없음 → "불사자 미조회"
  </behavior>
  <action>
ads_rules.py (per ⑦a~⑦d 결정표):
1) 상수를 파일 상단 한 곳에 추가 — POP_IMP_MIN = 50(⑦b/⑦c 모집단 7일 노출 하한), CTR_TAIL_PCT = 0.10(⑦b/⑦c 끝단 비율), MAINT_CLICK_MIN = 20(⑦d 30일 클릭 하한). 각 상수에 "2026-10-16 용팀장 확정 · 2~3주 뒤 조정 예정" 한국어 주석. 기존 IMP_MIN/CTR_LOW/CTR_HIGH 는 ②④ 가 result.json 에 계속 남으므로 지우지 않는다(P-6).
2) pool_rows(ads, group_of, stats_7d): live_ads 순회, stats_7d 에 행이 있고 impCnt ≥ POP_IMP_MIN 인 소재를 ad_info+_with_stat 로 만든 행 목록(7일 지표). group_of 해석은 classify 의 info_of 와 같은 방식(공용 내부 헬퍼로 빼서 classify 도 그걸 쓰게 해도 된다 — 출력 불변 조건).
3) ctr_tail(rows, pct=CTR_TAIL_PCT, top=False): n = math.ceil(len(rows)*pct) (빈 풀이면 0), 정렬키는 behavior 대로, 상위 n 행의 사본을 돌려준다.
4) split_global(pools): pools = {alias: [행]} → 모든 행에 acct=alias 를 붙인 사본을 합쳐 한 풀로 ctr_tail 하위/상위를 구한 뒤 {alias: {"⑦b썸네일변형": [...], "⑦c상세꾸미기후보": [...]}} 로 되돌린다. 풀에 없는 alias 도 빈 리스트 두 개를 갖게 한다.
5) classify 끝에 "⑦d정비점검후보" 추가 — 기존 live 30일 루프 안에서 clk ≥ MAINT_CLICK_MIN 이면 dict(row, purCnt=(pur or {}).get("cnt", 0)) 를 모으고 clk 내림차순 정렬. 기존 키 순서 뒤(⑥ 다음, _summary 앞)에 둔다.
6) final_7c(rows), maintenance_verdict(row) 를 behavior 대로 구현. 보강 필드 이름은 <interfaces> 의 "보강 필드 계약" 그대로.
7) 모듈 docstring 의 "6개 규칙" 설명을 ⑦ 체계로 갱신.

run_ads.py cmd_run: 계정 루프에서 classify 와 함께 pool_rows 를 모아 두고, 루프가 끝난 뒤 split_global 을 한 번 불러 각 계정 rules 에 "⑦b썸네일변형"·"⑦c상세꾸미기후보" 를 넣은 다음 result.json 을 쓴다(전 계정 합산 1풀 — 계정별 아님). 출력 줄에 풀 크기와 ⑦b/⑦c 건수를 한 줄 찍는다. --account 로 일부만 돌리면 그 계정들만의 풀이 된다는 사실을 주석으로 남긴다. 모듈 docstring 서브커맨드 목록에 enrich(Task 2) 자리를 미리 적는다.

sheets_out.py: COLS 에서 "②썸네일교체"·"④효자후보" 를 제거(과거 탭은 건드리지 않는다는 주석)하고 세 탭 추가 —
- "⑦b썸네일변형": 상품 title, 노출 imp, 클릭 clk, CTR % ctr, 순위 rank, 광고그룹 adGroup, 스토어상품ID mallProductId, 소재ID adId (P-5: 판매자상품코드 없음)
- "⑦c상세꾸미기": 상품, 판매자상품코드, 상세상태, 노출, 클릭, CTR %, 광고그룹, 불사자매칭, 스토어상품ID, 소재ID
- "⑦d정비점검": 상품, 판매자상품코드, 클릭(30일) clk, 구매수 purCnt, 상세상태, 옵션상태, 정비판정, 광고그룹, 불사자매칭, 스토어상품ID
write_sheet 는 ⑦c 탭에는 rules["⑦c상세꾸미기후보"] 를 final_7c 로 거른 행, ⑦d 탭에는 rules["⑦d정비점검후보"] 각 행에 정비판정 = maintenance_verdict(row) 를 붙인 행을 쓴다. 탭 이름 → 원천 규칙 키 매핑은 SOURCE dict 하나로 둔다(나머지 탭은 이름 = 키). 보강 키가 없을 때 판매자상품코드 칸은 빈칸, 불사자매칭 칸은 "불사자 미조회". 규칙별 try/except 구조 유지.

report_md.py: 계정별 ②·④ 섹션 삭제, 총괄표 열을 `노출0 | ③구매0 | ⑤효자` 로 줄이고, 계정별 섹션 뒤에 "## ⑦ 전 계정 합산 (7일 노출 50+ 모집단 N건)" 섹션 추가 — ⑦b(상위 TOP_N 표시, _count_label), ⑦c(final_7c 결과, 판매자상품코드·상세상태·불사자매칭 열), ⑦d(maintenance_verdict 별 건수 요약 한 줄 + 정비완료 아닌 행 표, 판매자상품코드·클릭·상세상태·옵션상태·정비판정 열). 모집단 크기는 result.json 의 최상위 "pool7" = {"size": N, "imp_min": 50, "pct": 0.10} 로 cmd_run 이 함께 기록해 둔 값을 읽는다(없으면 "?"). ⑦a 문구는 기존 ① 섹션 제목에 "(⑦a)" 만 덧붙인다. 금칙어(장바구니·총전환·add_to_cart)를 주석·문자열 어디에도 쓰지 않는다.

test_ads_rules.py: 기존 테스트는 수정하지 않고 TestPool7·TestCtrTail·TestSplitGlobal·TestRule7d·TestFinal7c·TestMaintenanceVerdict 클래스를 추가(behavior 항목 전부). 기존 헬퍼 ad()/stat() 재사용. 네트워크 0.
  </action>
  <verify>
    <automated>cd /Users/choiyongsmacbook/Documents/yongtimjang_claudecode && for t in nvad reports ads_rules ledger bids prune; do .venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/test_$t.py || exit 1; done && .venv/bin/python3 -c "import sys; sys.path.insert(0,'.claude/skills/naver-ads-weekly/scripts'); import report_md, sheets_out; assert '②썸네일교체' not in sheets_out.COLS and '⑦d정비점검' in sheets_out.COLS; r={'generated':'t','pool7':{'size':0},'accounts':{'a':{'summary':{},'rules':{k:[] for k in ['①노출0','②썸네일교체','③원인분석','④효자후보','⑤효자확정','⑥삭제대상','⑦b썸네일변형','⑦c상세꾸미기후보','⑦d정비점검후보']}}}}; md=report_md.build_report(r); assert not any(w in md for w in ['장바구니','총전환','add_to_cart']); print('ok')" && grep -v '^\s*#' .claude/skills/naver-ads-weekly/scripts/report_md.py | grep -c -e '장바구니' -e 'add_to_cart' | grep -qx 0</automated>
  </verify>
  <done>기존 6개 테스트 + 새 ⑦ 테스트 전부 통과. result.json 에 ⑦b/⑦c후보/⑦d후보·pool7 이 실리고, sheets_out 은 ①③⑤⑦b⑦c⑦d 6탭만 쓰며 ②④ 는 쓰지 않는다. report.md 에 ⑦ 합산 섹션이 있고 금칙어 0.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: bulsaja_join.py — ⑦c/⑦d 후보 불사자 조인·상세/옵션 상태 보강 (run_ads enrich)</name>
  <files>.claude/skills/naver-ads-weekly/scripts/bulsaja_join.py, .claude/skills/naver-ads-weekly/scripts/test_bulsaja_join.py, .claude/skills/naver-ads-weekly/scripts/run_ads.py</files>
  <behavior>
    - normalize_name: 앞뒤 공백 제거 + 연속 공백 1칸. 대소문자·기호는 그대로
    - match_in_group(title, products): 정규화 이름이 정확히 1건 일치 → ("히트", productId); 0건 → ("미스", None); 2건 이상 → ("중복", None). 빈 title → ("미스", None)
    - resolve_group(adGroup, group_idx): join.market_number 로 번호 추출 실패 → "추출실패"; 번호가 group_idx 에 없음 → "번호없음"; 있으면 그룹 dict. group_idx 는 join.group_index 로 만든 것만 쓴다 — 단 그룹명에 "용쌤" 이 들어간 그룹만 넘긴다(같은 번호의 쿠팡·기타 그룹 오매칭 방지)
    - option_status(matrix_value, found): found False → ("판정 불가", None); "완료"/"해당없음" → ("정리완료", False); 빈칸·재작업(...)·기타 → ("미정리", True)
    - enrich_rows(rows, lookup): lookup 가짜 객체(그룹 목록·그룹 상품·workdata·현황판 값을 dict 로 주입)로 히트/미매칭 각 경로의 보강 필드가 계약대로 붙는다. 같은 (번호, 정규화 이름) 은 workdata 를 한 번만 부른다
    - 계정 불일치(닉네임 ≠ 부킹)면 rows 를 바꾸지 않고 "enrich_status": "계정불일치" 를 돌려주며 종료코드 3
  </behavior>
  <action>
새 파일 bulsaja_join.py (한국어 주석, try-except 포함, 공개 함수 영문 / 내부 한글 허용). 맨 위에서 저장소 루트(스크립트에서 위로 올라가며 webapp/ 와 .claude/lib/eroomlib 가 있는 곳을 찾는 run_ads.py 의 _d 루프 관용구)를 sys.path 에 넣고 from webapp import join, state 로 market_number·group_index·재검증판정·strip_display_rules·상세상태·불리언정규화 를 재사용한다(P-2, 로직 복제 금지 — 같은 정규식·판정을 이 파일에 다시 쓰지 마라). 머리말에 P-1 근거(join.py D-03 은 상품명 매칭을 금했지만 2026-10-16 용팀장 지시로 그룹 내 정확 1건 일치만 허용, 번호검증을 증거로 싣는다)를 적는다.

순수 함수: normalize_name, match_in_group, resolve_group, option_status (behavior 대로).

I/O 계층(주입 가능하게 클래스 하나 — 이름 예 BulsajaLookup): ProductMCP 를 열고 0.26초 간격·표시규칙 제거로 감싼 call (run_sold_lock._Bulsaja 패턴), my_profile 닉네임 확인(기대 "부킹", 인자 --expect-nick), market_groups 1회, group_products(groupId) = collect_group 결과, workdata_full(pid) = ss_index_calls.워크데이터꺼내기 로 꺼낸 data, matrix_option(그룹명, pid) = eroomlib.matrix.index_groups() 로 그룹명→시트 매핑 후 matrix.read(sheet) 를 그룹당 1회 읽어 "옵션" 값 반환(그룹 시트 없음·행 없음·예외 → found False, P-3). 스스번호 추출은 sold-lock 의 sold_lock_rules.extract_ss_no 를 import 재사용(경로는 sold-lock 스크립트 디렉터리 sys.path 추가).

캐시: run-dir/bulsaja_cache/ 아래 group_<groupId>.json(그룹 상품 목록) · wd_<productId>.json(workdata 에서 필요한 필드만: uploadDetailContents, uploadBulsajaCode, uploadedSuccessUrl) · matrix_<그룹명 안전화>.json. 캐시가 있으면 MCP/시트를 부르지 않는다(재실행 시 비용 0). 원자적 쓰기(tmp→os.replace), ensure_ascii=False.

enrich_rows(rows, lookup): 각 행에 대해 resolve_group → match_in_group → workdata_full → 상세상태 = state.상세상태(uploadDetailContents), 상세미가공 = 상세상태 != "AI가공완료", 판매자상품코드 = uploadBulsajaCode, 번호검증 = join.재검증판정(row.mallProductId, 스스번호, False), option_status(matrix_option) → 옵션상태/옵션미정리. 단계별 실패는 그 행만 "미매칭: 조회실패"(workdata 예외) 로 두고 계속 간다. 보강 필드 이름은 <interfaces> 계약 그대로. 원본 행을 mutate 하지 않고 사본을 돌려준다.

cmd_enrich(run_dir, expect_nick): result.json 을 읽어 모든 계정의 "⑦c상세꾸미기후보"·"⑦d정비점검후보" 행만 모아(다른 규칙은 조회하지 않는다 — 비용 한정) 중복 (acct, adId) 는 한 번만 조회, 결과를 같은 키 자리에 되돌려 넣고 result.json 을 원자적으로 다시 쓴다. 최상위에 "enrich" = {"status": "ok"|"계정불일치"|"실패", "rows": n, "hit": h, "unmatched": u, "at": ISO} 기록. 종료코드 0 정상 / 3 계정 불일치 / 1 그 밖 실패(그 경우에도 result.json 원본은 그대로 남는다).

run_ads.py: 서브커맨드 enrich 추가(--run-dir, --expect-nick 기본 "부킹") → bulsaja_join.cmd_enrich 호출. 지연 import(enrich 를 안 쓰는 prep/run/bids/prune 이 webapp·eroomlib.snapshot import 실패에 영향받지 않게).

test_bulsaja_join.py: unittest, 네트워크 0. 순수 함수 + enrich_rows 를 가짜 lookup 으로 검증(behavior 전부, 히트·추출실패·번호없음·미스·중복·조회실패·옵션 판정 불가 경로). "용쌤" 없는 같은 번호 그룹이 무시되는지 포함.
  </action>
  <verify>
    <automated>cd /Users/choiyongsmacbook/Documents/yongtimjang_claudecode && .venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/test_bulsaja_join.py && .venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/run_ads.py enrich --help >/dev/null && grep -c "from webapp import" .claude/skills/naver-ads-weekly/scripts/bulsaja_join.py && ! grep -v '^\s*#' .claude/skills/naver-ads-weekly/scripts/bulsaja_join.py | grep -q 'd{1,2})-('</automated>
  </verify>
  <done>test_bulsaja_join 통과, run_ads enrich 서브커맨드 존재, 번호 정규식·상세 판정이 bulsaja_join.py 에 복제되지 않고 webapp import 로 재사용됨. 조회 대상은 ⑦c후보·⑦d후보 행뿐이고 캐시가 run-dir/bulsaja_cache 에 남는다.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: 월요일 래퍼(weekly_monday.py) + 업무판 1행 + launchd 템플릿 + 문서 갱신</name>
  <files>.claude/skills/naver-ads-weekly/scripts/weekly_monday.py, .claude/skills/naver-ads-weekly/scripts/test_weekly_monday.py, .claude/skills/naver-ads-weekly/launchd/com.eroom.ads-weekly.plist, .claude/skills/naver-ads-weekly/SKILL.md, .claude/skills/naver-ads-weekly/references/규칙-판정기준.md</files>
  <behavior>
    - 전 단계 성공(가짜 러너 전부 0) → 호출 순서가 prep, run, enrich, apply --sheet <ID>, bids --commit, prune --commit 이고 업무판 1행이 append 된다
    - run 이 1 을 반환 → enrich/apply/bids/prune 미호출, 업무판 메모가 "실패: run" 으로 시작
    - enrich 가 3 을 반환 → apply 는 호출, bids·prune 은 미호출(P-7), 메모에 "실패: enrich(쓰기 단계 생략)"
    - apply 실패 → bids·prune 미호출
    - 업무판 append 가 예외 → 래퍼 종료코드는 단계 결과대로(0), weekly_result.json 의 board.status = "failed"
    - 메모 문자열 형식: "입찰+10 N · 썸네일변형 b · 상세꾸미기 c · 정비점검 d(미정비 x) · 꺼진소재 삭제 p" — N 은 bids preview-out 의 계정별 committed 합, b/c 는 ⑦b·final_7c 건수, d/x 는 ⑦d후보 건수·정비완료 아닌 건수, p 는 prune preview-out 의 total
    - 업무판 행 = [max번호+1, 날짜, 체크칸, "⑦ 광고 주간 <run-dir>", "⑦", "Claude", "자동", 메모, ""]
  </behavior>
  <action>
weekly_monday.py (새 파일, 한국어 주석·try-except): 본체 run(args, runner=None, board_append=None, board_get=None, work_board_id=None, today=None) 와 얇은 main — sold-lock 의 run()/main 분리 관용구(3단계 스케줄러가 같은 함수를 부를 수 있게).
- run-dir 이름 = --run-dir 또는 오늘 날짜(ISO). 모든 단계에 같은 --run-dir 을 넘긴다.
- 기본 runner = subprocess.run([sys.executable, <run_ads.py 절대경로>, *argv], 출력은 run-dir/weekly.log 에 이어쓰기, timeout 단계별 넉넉히(prep 3600초, 그 외 1800초)) → 종료코드. 경로는 __file__ 기준으로 계산(하드코딩 금지).
- 단계: prep → run → enrich(--expect-nick 부킹) → apply --sheet <ID> → bids --commit --preview-out <run-dir>/bids_commit.json → prune --commit --preview-out <run-dir>/prune_commit.json --backup-tag weekly-<YYYYMMDD>. 시트 ID 는 P-8 규칙(--sheet 인자 > cfg("sheets.naver_ads") > DEFAULT_SHEET 상수).
- 실패 정책(behavior, P-7): prep/run 실패 → 이후 전부 생략. enrich 실패 → apply 는 실행, bids/prune 생략. apply 실패 → bids/prune 생략. bids 실패 → prune 은 여전히 생략(앞 단계 실패 규칙). 생략 사유를 weekly_result.json 의 steps 에 {이름: 종료코드|"skipped"} 로 남긴다.
- 집계: result.json·bids_commit.json·prune_commit.json 을 읽어 메모 숫자를 만든다(behavior 형식). 파일이 없거나 깨지면 그 숫자는 "?"(예외로 죽지 않는다). ⑦c 건수는 ads_rules.final_7c, ⑦d 미정비는 ads_rules.maintenance_verdict != "정비완료" 로 센다(판정 재구현 금지). 실패가 있으면 메모 앞에 "실패: <단계>" 를 붙인다.
- 업무판: run_sold_lock.py 415~434행 패턴 그대로(board_get 으로 A열 번호 최대값+1 → board_append "오늘" 탭 1행, 실패해도 본 작업 유지·weekly_result.json 에 board.status 기록). 체크칸은 전 단계 성공이면 "✓"(sold-lock 의 checked_flag 의미와 같게 — 실패면 빈칸).
- run-dir/weekly_result.json 에 steps·memo·board 를 원자적으로 쓴다. 종료코드: 전 단계 성공 0, 하나라도 실패 1.
- --dry-run 플래그: bids/prune 을 --commit 없이 돌리고 업무판 할 일에 "[dry-run] " 접두(사용자 첫 실행 전 점검용).

test_weekly_monday.py: 가짜 runner(호출 argv 기록 + 단계별 반환값 지정) · 가짜 board_get/board_append · tmp run-dir 에 미리 써 둔 result.json/bids_commit.json/prune_commit.json 으로 behavior 전부 검증. 네트워크·subprocess 0.

launchd/com.eroom.ads-weekly.plist: sold-lock plist 를 그대로 본떠 Label com.eroom.ads-weekly, ProgramArguments = /usr/bin/caffeinate -i __WORKSPACE__/.venv/bin/python3 __WORKSPACE__/.claude/skills/naver-ads-weekly/scripts/weekly_monday.py, StartCalendarInterval = Weekday 1 · Hour 7 · Minute 0, RunAtLoad false, 로그 __HOME__/python_work/data/naver-ads/logs/launchd.{out,err}.log, PATH·PYTHONUNBUFFERED 동일. 상단 주석에 "load 하지 않는다 — 설치는 SKILL.md 명령으로 사람이". **launchctl bootstrap/load 를 실행하지 마라.** plutil -lint 로 문법만 확인.

SKILL.md: description 의 규칙 문구를 ⑦ 체계로, "6개 규칙" 표를 user_decisions 표(⑦a~⑦d + ③⑤⑥ 유지)로 교체, 흐름에 enrich 단계 추가, "월요일 자동 실행" 절 신설(weekly_monday.py 단계·실패 정책·업무판 메모 형식·되돌리기 bids --revert · 설치 명령 = sold-lock SKILL.md 67~79행과 같은 sed 치환 + plutil -lint + launchctl bootstrap, 로그 경로, 첫 실행 2026-10-19), 구글시트 절의 탭 목록을 ①③⑤⑦b⑦c⑦d 로 갱신(②④ 는 2026-10-16 부로 쓰기 중단·과거 행 보존), 테스트 루프에 bulsaja_join·weekly_monday 추가.
references/규칙-판정기준.md: §4 표·상수 설명을 ⑦ 체계(POP_IMP_MIN·CTR_TAIL_PCT·MAINT_CLICK_MIN, 전 계정 합산 1풀, ceil, 동률 규칙)로 갱신하고, 조인(P-1, 용쌤 그룹만·정확 1건·번호검증 증거)·상세 판정(state.상세상태 재사용)·옵션 판정(P-3 현황판 옵션 열, 없으면 판정 불가)·불사자 조회 범위(⑦c/⑦d 후보만, run-dir 캐시) 절을 추가. 과거 ②④ 기준은 "2026-10-16 이전 기준" 으로 남겨 이력을 지우지 않는다. 금칙어 규칙 문단 유지.
  </action>
  <verify>
    <automated>cd /Users/choiyongsmacbook/Documents/yongtimjang_claudecode && .venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/test_weekly_monday.py && plutil -lint .claude/skills/naver-ads-weekly/launchd/com.eroom.ads-weekly.plist && grep -q "⑦d" .claude/skills/naver-ads-weekly/SKILL.md && grep -q "CTR_TAIL_PCT" .claude/skills/naver-ads-weekly/references/규칙-판정기준.md && ! launchctl list 2>/dev/null | grep -q com.eroom.ads-weekly && for t in nvad reports ads_rules ledger bids prune bulsaja_join weekly_monday; do .venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/test_$t.py >/dev/null 2>&1 || { echo FAIL $t; exit 1; }; done && echo ALL_OK</automated>
  </verify>
  <done>weekly_monday 테스트 통과, plist lint OK·미로드, SKILL.md·규칙-판정기준.md 가 ⑦ 체계와 월요일 자동 실행을 설명, 전체 8개 테스트 파일 통과.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| 래퍼 → 네이버 광고 API (쓰기) | 무인 실행에서 입찰가 변경·소재 삭제가 일어난다 |
| 불사자 MCP 응답 → result.json/시트 | 외부 응답에 모델 대상 지시문(표시규칙)이 섞여 온다 |
| launchd → 래퍼 | 사람 없이 매주 돈다 |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-wbc-01 | Tampering | weekly_monday 실패 정책 | mitigate | 앞 단계 하나라도 비정상 종료면 bids/prune 미실행(테스트로 고정). bids 는 기존 before_bids 백업 선행, 되돌리기 bids --revert |
| T-wbc-02 | Elevation | prune --commit 무인 실행 | mitigate | 기존 prune 백업 선행 유지 + --backup-tag weekly-YYYYMMDD 로 회차 식별, 결과 total 을 업무판 메모에 노출 |
| T-wbc-03 | Tampering (prompt injection) | bulsaja_join 캐시·result.json | mitigate | join.strip_display_rules 로 모든 MCP 응답에서 표시규칙 키 재귀 제거 후 저장 |
| T-wbc-04 | Spoofing | 불사자 계정 혼동(용팀장/부킹) | mitigate | enrich 시작 시 my_profile 닉네임 = 부킹 확인, 불일치면 조회 0·종료코드 3·bids/prune 생략 |
| T-wbc-05 | Information Disclosure | weekly.log·업무판 | accept | 광고 자격증명은 nvad 내부에서만 쓰이고 기존 서브커맨드가 출력하지 않는다. 래퍼는 자격증명을 읽지 않는다 |
| T-wbc-06 | Tampering | 상품명 오매칭으로 엉뚱한 상품을 작업 대상에 올림 | mitigate | 용쌤 그룹만·정확 1건 일치만 히트, 번호검증(재검증판정) 증거 열 표기. 이 단계는 리스트 생성뿐이라 쓰기 없음 |
</threat_model>

<verification>
- 전체 테스트: test_nvad/reports/ads_rules/ledger/bids/prune/bulsaja_join/weekly_monday 전부 통과 (네트워크 0)
- webapp 테스트 회귀 없음: `cd webapp && ../.venv-web/bin/python -m pytest tests/test_join.py tests/test_state.py -q` (webapp/ 파일은 수정하지 않으므로 통과해야 한다; .venv-web 이 없으면 생략하고 SUMMARY 에 기록)
- 실데이터 무쓰기 리허설(선택, 최근 run-dir 이 있으면): `run_ads.py run --run-dir <최근>` 후 result.json 에 ⑦b/⑦c후보/⑦d후보·pool7 존재 확인. enrich·apply --sheet·bids --commit·prune --commit 은 실행하지 않는다(실 계정 쓰기는 2026-10-19 월요일 첫 실행 몫)
- launchctl 에 com.eroom.ads-weekly 가 로드되어 있지 않음
</verification>

<success_criteria>
- ⑦a~⑦d 가 결정표대로 판정되고 상수 3개가 ads_rules.py 한 곳에만 있다
- ⑦c/⑦d 행에 판매자상품코드·상세상태·옵션상태가 붙고, 못 이은 행은 '불사자 미매칭: <사유>' 로 남는다
- 시트는 ⑦b썸네일변형·⑦c상세꾸미기·⑦d정비점검 탭으로 기록되고 ②④ 탭 쓰기는 없다
- 월요일 래퍼가 단계·실패 정책·업무판 1행을 지키고, plist 템플릿이 존재하되 로드되지 않았다
- 기존 테스트 무수정 통과
</success_criteria>

<output>
Create `.planning/quick/261016-wbc-ads-weekly-v2/261016-wbc-SUMMARY.md` when done
</output>

## 오케스트레이터 수정 지시 (2026-10-16, 실행 전 확정 — 위 본문보다 우선)

1. **불사자 조인 = 상품명 매칭 금지(D-03 유지).** 대신 번호 경로를 1차로 쓴다(실측 확인):
   광고 소재의 스토어상품ID(채널상품번호) + 광고그룹명 `NN-N` 마켓번호
   → 그 마켓의 커머스API 키(`.claude/skills/sold-lock/scripts/commerce_orders.py` 의 키 로딩/토큰 재사용)
   → `GET https://api.commerce.naver.com/external/v2/products/channel-products/{채널상품번호}`
   → `originProduct.detailAttribute.sellerCodeInfo.sellerManagementCode` (=판매자상품코드; 13-2 / 13265084103 → doLXkoGRnARoqlVjlZiyB 실측 200)
   → 불사자 `bulsaja_product_find_by_code` 정확히 1건 → 워크데이터 `uploadedSuccessUrl.smartstore` 가 채널상품번호와 일치하면 매칭.
   실패 사유는 '키없음/커머스조회실패/판매자코드없음/불사자미매칭/다건/번호불일치' 로 기록. 상품명 fallback 은 넣지 않는다.
2. **enrich 실패가 입찰·소재정리를 막지 않는다.** bids --commit / prune --commit 은 prep·run 성공에만 의존. enrich·apply·업무판 실패는 각자 기록만 하고 계속.
