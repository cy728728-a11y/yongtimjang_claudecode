---
phase: 1
slug: board-bid-raise
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-09-19
updated: 2026-09-20
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> 근거: `01-RESEARCH.md` § Validation Architecture (전부 이 맥북에서 실측).
> **2026-09-20 갱신:** PLAN 확정에 따라 `Plan`·`Wave` 열을 실제 값으로 채웠고, 명령을 `.venv-web/bin/pytest` 로 실행 가능한 형태로 고쳤다. 행 6개를 추가했다(표시: ✚).
> **2026-09-20 재검(plan-checker 반영):** `Automated Command` 를 **파일 단위**로 통일하고 노드 ID 는 `(핵심 노드: …)` 로 병기했다 — 태스크의 `<verify>` 가 실제로 파일 전체를 돌리기 때문이다(주장과 실행의 불일치 제거).
> BID-01 · BOARD-04 는 대상 테스트가 `test_board.py` → **`test_flow.py`(01-07 Task 2)** 로 옮겨졌다 — 그 테스트들이 부르는 `webapp/flow.py` 가 Task 2 에서 처음 생겨, Task 1 에 두면 collect 단계에서 깨진다.

---

## Test Infrastructure

프레임워크를 **섞는다.** CLI 테스트를 pytest 로 옮기는 것 자체가 회귀 위험이라, CLI 는 `unittest` 그대로 두고 웹앱만 pytest 로 간다.
(PATTERNS.md §C-1 충돌은 이 결정으로 해소됐다.)

> **브라우저 JS 계층은 pytest 에 없다.** Tabulator 동작(정렬·필터·건수 배지·가상 DOM)은
> `TestClient` 가 JS 를 한 줄도 실행하지 않아 자동 스위트로 못 덮는다. 흉내 내면
> "우리가 짠 가짜 Tabulator" 를 검증하게 되므로 **만들지 않았다.** 대신 `security_curl.sh` 와
> 같은 계층에 `webapp/tests/board_cdp.sh`(헤드리스 크롬 + CDP)를 두고, 보드 JS 를 고치면 손으로 돌린다.

| Property | Value |
|----------|-------|
| **Framework (CLI 회귀 방어)** | stdlib `unittest` — 러너는 파일 직접 실행 |
| **Framework (신규 웹앱)** | `pytest` + `fastapi.testclient.TestClient` (`.venv-web`) |
| **Config file** | CLI: 없음(파일 직접 실행) · 웹앱: `webapp/pytest.ini` — **Plan 01-01 Task 1 이 만든다** |
| **Quick run command** | `.venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/test_bids.py` |
| **Full suite command** | `for t in nvad reports ads_rules ledger bids prune; do .venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/test_$t.py \|\| exit 1; done && .venv-web/bin/pytest webapp/tests -q` |
| **Estimated runtime** | CLI 100 tests ~0.02초 · 웹앱 전체 ~10초 (합성 잡 포함) |
| **Baseline (2026-09-19 실측)** | CLI **100 tests, 6 파일 전부 exit=0** (7+7+21+21+28+16) |

---

## Sampling Rate

- **After every task commit:** `.venv/bin/python3 .../test_bids.py` (0.003초) + `.venv-web/bin/pytest webapp/tests -x -q`
- **After every plan wave:** 위 **Full suite command** 전량
- **Before `/gsd:verify-work`:** Full suite 전량 green + 보안 curl 8종 전량 PASS + Skeleton B 수동 1회(`prep --account cy728` 실행 중 탭 닫았다 다시 열기)
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

> `Plan` 열은 `01-NN-PLAN.md` 의 NN. `Wave` 열은 그 플랜의 frontmatter `wave`.
> Threat Ref 는 각 PLAN.md `<threat_model>` 의 T-1-XX 와 연결된다.
> **Automated Command 는 `파일 단위` 로 적는다** — 태스크의 `<verify>` 가 실제로 그렇게 돈다(노드 하나만 돌리는 것보다
> 파일 전체가 도는 편이 회귀 방어에 낫다). 그 행이 **겨누는** 특정 테스트는 같은 칸에 `(핵심 노드: ::test_이름)` 으로 병기한다.
> 태스크의 `<acceptance_criteria>` 는 "이 행이 지목한 파일이 명령에 들어 있고 핵심 노드가 그 실행에 포함된다" 를 주장한다.

| Req ID | Plan | Wave | 증명할 동작 | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|--------|------|------|------------|-----------|-----------------|-----------|-------------------|-------------|--------|
| ✚경로-01 | 01-01 | 0 | `data_root` 가 workspace.toml 에서 오고, 모르는 회차는 경로가 되지 않는다 | T-1-11 | 사용자 입력이 파일 경로가 되지 않는다 | unit | `.venv-web/bin/pytest webapp/tests/test_paths.py -x -q` | ❌ W0 | ⬜ pending |
| ✚픽스처-01 | 01-01 | 0 | 테스트 기반(가짜 5번째 계정 · ①행 imp 없음)이 선다 | T-1-SC2 | 테스트에 `--commit` 리터럴 0건 | unit | `.venv-web/bin/pytest webapp/tests -x -q && bash webapp/tests/no_commit_guard.sh` | ❌ W0 | ⬜ pending |
| 회귀-01 | 01-02 | 1 | CLI 패치 후 기존 가드 100개 불변 | — | N/A | unit | `for t in nvad reports ads_rules ledger bids prune; do .venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/test_$t.py \|\| exit 1; done` | ✅ 존재 (100 OK) | ⬜ pending |
| 회귀-02 | 01-02 | 1 | `--only-ads` 없이 부르면 필터 전과 동일 | — | N/A | unit | `.venv-web/bin/pytest webapp/tests/test_cli_patch.py -x -q` (핵심 노드: `::test_only_ads_none_은_전량과_같다`) | ❌ W0 | ⬜ pending |
| 회귀-03 | 01-02 | 1 | `--only-ads` 가 `update_streaks` **뒤에** 걸린다 | T-1-04 | 필터가 연속실패 카운팅을 오염시키지 않는다 | unit | `.venv-web/bin/pytest webapp/tests/test_cli_patch.py -x -q` (핵심 노드: `::test_필터해도_streak_은_전량기준`) | ❌ W0 | ⬜ pending |
| 회귀-04 | 01-02 | 1 | `--only-ads` 파일 손상 시 exit 1 (전량 폴백 **금지**) | T-1-05 | 대상 파일이 깨지면 전량 실행으로 번지지 않는다 | unit | `.venv-web/bin/pytest webapp/tests/test_cli_patch.py -x -q` (핵심 노드: `::test_only_ads_깨지면_실패한다`) | ❌ W0 | ⬜ pending |
| FLOW-05 (CLI) | 01-02 | 1 | 결과 JSON 이 항목별 성공/실패/스킵+사유를 담는다 | T-1-15 | 에러 문자열을 축약해 담는다 | unit | `.venv-web/bin/pytest webapp/tests/test_cli_patch.py -x -q` (핵심 노드: `::test_항목단위_결과`) | ❌ W0 | ⬜ pending |
| SAFE-01 | 01-03 | 1 | Host `evil.com` → 400 / Origin `evil.com` → 403 | T-1-01, T-1-01b | DNS rebinding·타 탭 CSRF 차단 | unit | `.venv-web/bin/pytest webapp/tests/test_security.py -x -q` | ❌ W0 | ⬜ pending |
| SAFE-02 | 01-03 | 1 | 토큰 없음·틀림 → 403, 맞음 → 200 | T-1-02, T-1-16 | 부팅 토큰 없이는 쓰기 불가 | unit | `.venv-web/bin/pytest webapp/tests/test_security.py -x -q` | ❌ W0 | ⬜ pending |
| SAFE-03 | 01-03 | 1 | 응답·로그·템플릿 어디에도 시크릿 문자열이 없다 | T-1-03 | 광고 시크릿·불사자 토큰 미노출 | unit | `.venv-web/bin/pytest webapp/tests/test_security.py -x -q` (핵심 노드: `::test_시크릿이_새지_않는다`) | ❌ W0 | ⬜ pending |
| ✚보안-curl | 01-03 | 1 | 실행 중인 서버에 대한 보안 8종 | T-1-01, T-1-02, T-1-03 | 바인드·Host·Origin·토큰·시크릿 | integration | `CT_DEV_TOKEN=devtoken123 bash webapp/tests/security_curl.sh` | ❌ W0 | ⬜ pending |
| ✚보드-CDP | 01-04 | 2 | 필터 전환 시 건수 배지가 **직전 값이 아니라** 현재 값이다 | T-1-32 (선행) | 실행 규모를 사람이 오독하지 않는다 | integration | `CT_DEV_TOKEN=devtoken123 bash webapp/tests/board_cdp.sh` | ❌ W0 | ⬜ pending |
| BOARD-01 | 01-04 | 2 | ①행에 `imp` 가 없어도 접기가 안 깨진다 | T-1-21 | 지표 중복 계상 없음 | unit | `.venv-web/bin/pytest webapp/tests/test_board.py -x -q` | ❌ W0 | ⬜ pending |
| BOARD-02 | 01-04 | 2 | 계정 alias 가 `result.json` 에서만 온다 (가짜 5번째 계정 픽스처) | — | N/A | unit | `.venv-web/bin/pytest webapp/tests/test_board.py -x -q` (핵심 노드: `::test_계정을_코드에_박지_않는다`) | ❌ W0 | ⬜ pending |
| ✚신선도-01 | 01-04 | 2 | 회차 날짜·경과일·통계기간이 함께 나오고 임계값 초과를 stale 로 본다 (D-16) | T-1-20 | 낡은 판정으로 실행하는 것을 경고한다 | manual | 브라우저 확인 (Plan 01-04 Task 3 의 2번 단계) | — | ⬜ pending |
| ENG-01 | 01-05 | 3 | argv 가 `.venv/bin/python3` + `run_ads.py` 로 조립된다 | T-1-10 | shell=False · Literal 화이트리스트 | unit | `.venv-web/bin/pytest webapp/tests/test_argv.py -x -q` | ✅ 존재 | ✅ green |
| ENG-07 | 01-05 | 3 | `create_job` 이 HTTP 없이 호출된다 | — | N/A | unit | `.venv-web/bin/pytest webapp/tests/test_jobs.py -x -q` (핵심 노드: `::test_create_job_은_http_없이_돈다`) | ✅ 존재 | ✅ green |
| ✚동시쓰기-01 | 01-05 | 3 | 쓰기 잡은 전역에서 한 번에 하나만 돈다 (Pitfall 3) | T-1-09 | 백업·ledger read-modify-write 레이스 차단 | unit | `.venv-web/bin/pytest webapp/tests/test_jobs.py -x -q` (핵심 노드: `::test_쓰기잡은_동시에_두개가_안된다`) | ✅ 존재 | ✅ green |
| ✚라우터-01 | 01-05 | 3 | 작업 생성이 전부 POST · kind 를 클라이언트가 못 고른다 · 409/400 번역 | T-1-01b, T-1-23, T-1-09 | 임의 argv·작업종류 주입 차단 | unit | `.venv-web/bin/pytest webapp/tests/test_routes_jobs.py -x -q` | ✅ 존재 | ✅ green |
| ENG-02 | 01-06 | 4 | 서버가 죽어도 자식이 산다 (`start_new_session=True`) | — | N/A | integration | `.venv-web/bin/pytest webapp/tests/test_jobs.py -x -q` (핵심 노드: `::test_자식은_서버_종료를_견딘다`) | ✅ 존재 | ✅ green — **01-05 가 미리 충족**(잡 엔진이 이 플랜에서 태어났다) |
| ENG-03 | 01-06 | 4 | 작업 **중간 시점**에 로그파일이 이미 커져 있다 (`PYTHONUNBUFFERED=1`) | T-1-25 | 진행 로그 은폐 방지 | integration | `.venv-web/bin/pytest webapp/tests/test_jobs.py -x -q` (핵심 노드: `::test_로그가_실시간으로_쌓인다`) | ✅ 존재 | ✅ green — **01-05 가 미리 충족** |
| SC-03 | 01-06 | 4 | 탭 닫았다 열어도 로그를 처음부터 이어본다 | T-1-26, T-1-27 | Last-Event-ID 미의존 · 중복 미표시 | integration | `.venv-web/bin/pytest webapp/tests/test_jobs.py -x -q` (핵심 노드: `::test_재접속하면_처음부터_이어본다`) | ❌ W0 | ⬜ pending |
| ✚로그tail-01 | 01-06 | 4 | 오프셋 읽기가 멀티바이트 절단·파일 부재를 버틴다 | T-1-03d, T-1-17b | 스크러버 + escape 통과 | unit | `.venv-web/bin/pytest webapp/tests/test_logtail.py -x -q` | ❌ W0 | ⬜ pending |
| FLOW-02 | 01-07 | 5 | 실행이 미리보기와 **같은 targets 파일**을 지목 | T-1-06 | 화면 상태에서 대상을 다시 만들지 않는다 | unit | `.venv-web/bin/pytest webapp/tests/test_flow.py -x -q` (핵심 노드: `::test_targets_파일이_하나다`) | ❌ W0 | ⬜ pending |
| BID-01 | 01-07 | 5 | ①만 대상으로 잡힌다 (②③ 소재 제외) | T-1-30 | 대상 규칙 오염 차단 | unit | `.venv-web/bin/pytest webapp/tests/test_flow.py -x -q` (핵심 노드: `::test_대상은_규칙1_소재만`) — **01-07 Task 2**. `flow.collect_rule1_ads` 가 태어나는 태스크에 테스트가 같이 있다 | ❌ W0 | ⬜ pending |
| BID-02 | 01-07 | 5 | 그룹입찰 행의 `from` 이 `groupBid` 다 (웹앱은 **계산하지 않는다**) | T-1-07 | 진실이 둘이 되지 않는다 | unit | **기존** `.venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/test_bids.py` + `.venv-web/bin/pytest webapp/tests/test_flow.py -x -q` (핵심 노드: `::test_웹앱은_입찰가를_계산하지_않는다`) | ✅ 존재 / ❌ W0 | ⬜ pending |
| BID-03 | 01-07 | 5 | 미리보기가 현재가 → 인상 후 가격을 보여준다 | T-1-07 | 산출물 값 그대로 표시 | unit | `.venv-web/bin/pytest webapp/tests/test_flow.py -x -q` (핵심 노드: `::test_미리보기_표`) | ❌ W0 | ⬜ pending |
| BOARD-04 | 01-07 | 5 | 선택 건수·예상 인상액 합계가 맞는다 | T-1-32 | 0건이어도 집계를 보여준다 | unit | `.venv-web/bin/pytest webapp/tests/test_flow.py -x -q` (핵심 노드: `::test_예상_인상액_합계`) — **01-07 Task 2**. `flow.raise_total` 이 태어나는 태스크에 테스트가 같이 있다 | ❌ W0 | ⬜ pending |
| ✚상한-01 | 01-07 | 5 | 계정별 1,500건 상한을 넘으면 거부된다 (D-08) | T-1-29 | 의도치 않은 대량 쓰기 차단 | unit | `.venv-web/bin/pytest webapp/tests/test_flow.py -x -q` (핵심 노드: `::test_계정별_상한을_넘으면_거부한다`) | ❌ W0 | ⬜ pending |
| BOARD-03 | 01-07 | 5 | 보이는 선택 vs 필터 전체가 다른 수를 준다 | T-1-29 | 대량 선택을 한 번 더 확인 | manual | 브라우저 확인 (Tabulator API 는 JS) — Plan 01-07 Task 3 의 3번 단계 | — | ⬜ pending |
| FLOW-04 | 01-07 | 5 | 필터 전체 선택은 별도 배너로 한 번 더 확인 (건수 타이핑 없음) | T-1-29 | 되돌릴 수 있는 작업은 타이핑을 받지 않는다 | manual | 브라우저 확인 — Plan 01-07 Task 3 의 4·5번 단계 | — | ⬜ pending |
| FLOW-01 | 01-08 | 6 | 미리보기 → 실행이 한 흐름으로 이어진다 (미리보기 없이 실행 불가) | T-1-34 | dry-run 선행 강제 | integration | `.venv-web/bin/pytest webapp/tests/test_flow.py -x -q` | ❌ W0 | ⬜ pending |
| FLOW-05 (화면) | 01-08 | 6 | 항목별 성공/실패/스킵+사유가 화면에 투영된다 | T-1-37 | 스킵·실패를 은폐하지 않는다 | unit | `.venv-web/bin/pytest webapp/tests/test_flow.py -x -q` (핵심 노드: `::test_항목단위_결과가_화면투영된다`) | ❌ W0 | ⬜ pending |
| ✚diff-01 | 01-08 | 6 | 미리보기와 달라진 N건을 사유와 함께 보고한다 (D-10) | T-1-36 | 재계산 차이를 은폐하지 않는다 | unit | `.venv-web/bin/pytest webapp/tests/test_flow.py -x -q` (핵심 노드: `::test_미리보기와_달라진건을_보고한다`) | ❌ W0 | ⬜ pending |
| BID-04 | 01-09 | 7 | 되돌리기가 **그 작업분만** 되돌린다 (백업 파일 불변) | T-1-08, T-1-40 | 회차 전체가 풀리지 않는다 | unit | `.venv-web/bin/pytest webapp/tests/test_revert.py -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**커버리지 확인:** Phase 1 요구사항 19개(ENG-01·02·03·07 / SAFE-01·02·03 / FLOW-01·02·04·05 / BOARD-01~04 / BID-01~04)가 전부 위 표에 있다. FLOW-05 는 CLI 산출(01-02)과 화면 투영(01-08) 두 줄로 나뉜다.

---

## 크레딧·광고비 0 으로 쓰기 경로를 검증하는 3층

프로젝트 제약이 "모든 쓰기는 dry-run 선행" 이다. 돈을 쓰지 않고 쓰기 경로를 증명하는 층이 셋 있다.

1. **`nvad.call` 몽키패치** — 기존 `test_bids.py` 가 이미 쓰는 방식(`bids.nvad.call = fake`). PUT 을 한 번도 안 내보내고 `committed`/`failed`/`result` 를 검증한다. (Plan 01-02 `test_cli_patch.py` · Plan 01-09 `test_revert.py`)
2. **CLI dry-run 실측 회귀** — `bids --preview-out` 은 **0.066초, 네트워크 0**:
   ```bash
   echo '["nad-a001-02-000000495390006"]' > /tmp/t.json
   .venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/run_ads.py bids \
     --run-dir 2026-08-30 --only-ads /tmp/t.json --preview-out /tmp/p.json
   .venv-web/bin/python -c "import json;d=json.load(open('/tmp/p.json'));print({k:len(v.get('plans',[])) for k,v in d.items()})"
   # 기대: {'cy728':0,'cy7728':0,'ownway1':1,'pogeunae':0}
   ```
   (Plan 01-02 · 01-07 의 `<verification>` 에 들어 있다)
3. **웹앱 레벨** — `create_job` 이 조립한 argv 를 **실행하지 않고 문자열로만** 검증. `--commit` 이 안 붙는 경로를 못박는다. (Plan 01-05 `test_argv.py`)

**절대 금지:** 자동 테스트에서 `--commit` 실행. grep 가드가 Plan 01-01 Task 1 에서 `webapp/tests/no_commit_guard.sh` 로 만들어진다:
```bash
! grep -rn '"--commit"' webapp/tests/ || { echo "테스트에 --commit 이 있다"; exit 1; }
```

---

## 보안 3종 curl 검증 (전부 2026-09-19 실측 통과)

> Plan 01-03 Task 3 이 이 8개를 `webapp/tests/security_curl.sh` 로 옮긴다.
> 토큰은 `CT_DEV_TOKEN` 환경변수로 받는다 — **`.boot-token-for-test` 파일을 만들지 마라**(토큰을 디스크에 남기지 않는다).

```bash
PORT=8765; T="$CT_DEV_TOKEN"; B=http://127.0.0.1:$PORT

# V-SAFE-01a  127.0.0.1 에만 바인드
lsof -nP -iTCP:$PORT -sTCP:LISTEN | grep -q '127.0.0.1:'"$PORT" && echo PASS || echo FAIL
# V-SAFE-01b  Host 화이트리스트 (DNS rebinding) → 400
test "$(curl -s -o /dev/null -w '%{http_code}' -H "Host: evil.com" $B/)" = 400 && echo PASS || echo FAIL
# V-SAFE-01c  타 사이트 Origin 의 쓰기 (토큰이 있어도) → 403
test "$(curl -s -o /dev/null -w '%{http_code}' -X POST -H "Origin: https://evil.com" -H "X-CT-Token: $T" $B/jobs/bids/preview)" = 403 && echo PASS || echo FAIL
# V-SAFE-02a  토큰 없는 쓰기 → 403
test "$(curl -s -o /dev/null -w '%{http_code}' -X POST $B/jobs/bids/preview)" = 403 && echo PASS || echo FAIL
# V-SAFE-02b  틀린 토큰 → 403
test "$(curl -s -o /dev/null -w '%{http_code}' -X POST -H "Origin: $B" -H "X-CT-Token: wrong" $B/jobs/bids/preview)" = 403 && echo PASS || echo FAIL
# V-SAFE-02c  정상 쓰기는 통과 (이게 없으면 '전부 막힘' 을 성공으로 오독한다)
#   ※ Plan 01-03 시점에는 라우트가 아직 없어 404 다 → 판정 기준 "403 이 아닐 것".
#      Plan 01-07 완료 후 아래대로 -lt 400 으로 조인다.
test "$(curl -s -o /dev/null -w '%{http_code}' -X POST -H "Origin: $B" -H "X-CT-Token: $T" \
        -H 'Content-Type: application/json' -d '{"run_dir":"2026-08-30","ad_ids":[]}' $B/jobs/bids/preview)" -lt 400 && echo PASS || echo FAIL
# V-SAFE-03  응답·로그 어디에도 시크릿이 없다
S=$(python3 -c "import json,pathlib;print(json.loads((pathlib.Path.home()/'.eroom/naver-ads.json').read_text())['accounts'][0]['secret_key'])")
curl -s -H "Cookie: ct_session=$T" $B/ | grep -q "$S" && echo FAIL || echo PASS
grep -rq "$S" webapp-logs/ && echo FAIL || echo PASS
# V-SAFE-01d  상태를 바꾸는 GET 이 없다 (Origin 방어의 전제)
! grep -rnE '@app\.get\(.*\)\s*\n\s*def .*(create_job|spawn)' webapp/ && echo PASS
```

---

## Wave 0 Requirements

> 전부 **Plan 01-01** 이 만든다.

- [ ] `.venv-web` 생성 + 의존 4종 설치 (fastapi · uvicorn · jinja2 · sse-starlette) — **모든 웹앱 테스트의 전제** — Plan 01-01 Task 1
- [ ] `webapp/pytest.ini` + `.venv-web` 에 `pytest` 설치 — Plan 01-01 Task 1
- [ ] `webapp/tests/conftest.py` — `client`(TestClient + 토큰 픽스처) · `tmp_run_dir` · `fake_result_json` · `synthetic_job` — Plan 01-01 Task 3
- [ ] `webapp/tests/fixtures/result_min.json` — 계정 **5개**(가짜 `zzfake` 추가해 BOARD-02 를 진짜로 검증) × 6규칙, ①은 `imp` 없이 — Plan 01-01 Task 3
- [ ] `webapp/tests/fixtures/targets_one.json` · `targets_broken.json` — Plan 01-01 Task 3
- [ ] 합성 잡 러너 `webapp/tests/fixtures/synthetic_job.py` — `create_job(kind="synthetic", …)` 을 **테스트 전용**으로 열되 운영 라우트에는 노출 금지 — Plan 01-01 Task 3 / Plan 01-05 Task 2
- [ ] `.gitignore`: `.venv-web/` · `webapp.db*` · `webapp-logs/` · `node_modules/`(기존) · `package*.json` — Plan 01-01 Task 1
- [ ] 테스트에 `--commit` 리터럴 금지 grep 가드 `webapp/tests/no_commit_guard.sh` — Plan 01-01 Task 1
- [ ] 프론트 정적파일 `curl` vendoring (npm 안 쓴다 — 리서치 중 `node_modules/` 가 생겼다 삭제된 전례) — Plan 01-01 Task 1
- [ ] `webapp/paths.py` · `webapp/settings.py` — conftest 가 monkeypatch 할 대상 — Plan 01-01 Task 2

---

## Manual-Only Verifications

| Behavior | Requirement | Plan / Task | Why Manual | Test Instructions |
|----------|-------------|-------------|------------|-------------------|
| 보이는 선택 vs 필터 전체 선택이 다른 건수를 준다 | BOARD-03 | 01-07 Task 3 (3번) | Tabulator 선택 API 가 브라우저 JS 안에서만 산다 | 보드에서 계정 필터를 건 뒤 헤더 체크박스 → 건수 확인 → "필터 전체 N건 선택" 배너 → 건수가 커지는지 확인 |
| 필터 전체 선택 시 확인 배너가 한 번 더 뜬다 | FLOW-04 | 01-07 Task 3 (4·5번) | 같음 | 위 배너가 실제로 뜨고, 취소하면 선택이 안 넘어가는지. 건수 타이핑 입력칸이 없는지 |
| 탭 닫았다 열어 진행 로그 이어보기 (실작업) | SC-03 | 01-06 Task 3 (6·7번) | 실제 브라우저 생명주기 | `prep --account cy728` 실행 → 탭 닫기 → 30초 뒤 다시 열기 → 처음부터 로그가 다시 흐르고 진행이 이어지는지. **합성 잡 테스트가 자동 커버하므로 이건 최종 1회 확인용** |
| 회차 신선도 배너 | D-16 | 01-04 Task 3 (2번) | 시각 확인 | 보드 상단에 `2026-08-30 회차 · N일 전 · 통계 기간 08-22~08-28` 이 뜨고, 오래되면 경고색인지 |
| 보드 건수 배지가 필터를 정확히 따라온다 | (BOARD-01 부수) | 01-04 — **자동화됨** | ~~시각 확인~~ → **육안으로는 못 잡는다** | 필터를 한 번만 바꾸면 숫자가 *움직이긴 해서* 사람은 PASS 를 준다. **두 번 연속 바꿔 직전 값과 대조해야만** 랙이 드러난다(2026-09-20 실제 버그). 그래서 수동 항목에서 빼고 `webapp/tests/board_cdp.sh` 로 옮겼다. 보드 JS 를 건드리면 그걸 돌려라 |
| 그룹입찰 행의 현재가가 그룹 기본가다 | BID-03 | 01-07 Task 3 (8번) | 실데이터 대조 | `nad-a001-02-000000495390006` 이 70 → 80 인지. **50 → 60 이면 웹앱이 재계산한 것** |
| 실제 광고 입찰가가 +10 됐다 | FLOW-01 | 01-08 Task 3 (8번) | 외부 시스템(네이버 광고 관리 화면) | 소재 하나를 직접 열어 입찰가 확인. 이게 유일한 최종 진실 |
| 되돌리기가 그 작업분만 내린다 / 백업 불변 | BID-04 | 01-09 Task 3 (4·5·6번) | 외부 시스템 + 디스크 상태 대조 | 되돌린 건수 == 성공 건수, `before_bids_*.json` 전후 건수 동일, 광고 화면에서 원복 확인 |
| 광고 API 자격증명 유효성 | (OQ-6) | 01-06 Task 3 (2번) | 리서치가 광고 API 를 한 번도 호출하지 않았다 | `run_ads.py prep --account cy728` 가 401/403 없이 완주하는지. 실패하면 자격증명 갱신부터 |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies — Plan 01-01~01-09 전 태스크 확인
- [x] Sampling continuity: no 3 consecutive tasks without automated verify — 체크포인트 태스크도 `<automated>` 를 갖는다
- [x] Wave 0 covers all ❌ W0 references above — Plan 01-01 이 전부 만든다
- [x] No watch-mode flags — `-x -q` 만 쓴다
- [x] Feedback latency < 15s — 웹앱 전체 ~10초
- [ ] 테스트에 `--commit` 리터럴 0건 (실행 중 `no_commit_guard.sh` 로 상시 확인)
- [ ] CLI 100 tests 여전히 exit=0 (회귀 기준선 불변)
- [ ] 보드 JS 수정 시 `bash webapp/tests/board_cdp.sh` 전량 PASS (pytest 가 못 덮는 계층)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** planned (2026-09-20) — 실행은 `/gsd:execute-phase 1`
