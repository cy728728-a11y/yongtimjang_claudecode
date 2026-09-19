---
phase: 1
slug: board-bid-raise
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-09-19
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> 근거: `01-RESEARCH.md` § Validation Architecture (전부 이 맥북에서 실측).

---

## Test Infrastructure

프레임워크를 **섞는다.** CLI 테스트를 pytest 로 옮기는 것 자체가 회귀 위험이라, CLI 는 `unittest` 그대로 두고 웹앱만 pytest 로 간다.

| Property | Value |
|----------|-------|
| **Framework (CLI 회귀 방어)** | stdlib `unittest` — 러너는 파일 직접 실행 |
| **Framework (신규 웹앱)** | `pytest` + `fastapi.testclient.TestClient` |
| **Config file** | CLI: 없음(파일 직접 실행) · 웹앱: `webapp/pytest.ini` — **none — Wave 0 installs** |
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

> 태스크 ID 는 PLAN.md 가 확정된 뒤 executor 가 채운다. 아래는 **요구 단위 계약** — 모든 태스크는 이 표의 한 줄 이상에 매달려야 한다.
> Threat Ref 는 PLAN.md `<threat_model>` 이 생성하는 T-1-XX 와 연결한다.

| Req ID | Plan | Wave | 증명할 동작 | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|--------|------|------|------------|-----------|-----------------|-----------|-------------------|-------------|--------|
| 회귀-01 | TBD | 1 | CLI 패치 후 기존 가드 100개 불변 | — | N/A | unit | `for t in nvad reports ads_rules ledger bids prune; do .venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/test_$t.py \|\| exit 1; done` | ✅ 존재 (100 OK) | ⬜ pending |
| 회귀-02 | TBD | 1 | `--only-ads` 없이 부르면 필터 전과 동일 | — | N/A | unit | `pytest webapp/tests/test_cli_patch.py::test_only_ads_none_은_전량과_같다 -x` | ❌ W0 | ⬜ pending |
| 회귀-03 | TBD | 1 | `--only-ads` 가 `update_streaks` **뒤에** 걸린다 | T-1-04 | 필터가 연속실패 카운팅을 오염시키지 않는다 | unit | `pytest webapp/tests/test_cli_patch.py::test_필터해도_streak_은_전량기준 -x` | ❌ W0 | ⬜ pending |
| 회귀-04 | TBD | 1 | `--only-ads` 파일 손상 시 exit 1 (전량 폴백 **금지**) | T-1-05 | 대상 파일이 깨지면 전량 실행으로 번지지 않는다 | unit | `pytest webapp/tests/test_cli_patch.py::test_only_ads_깨지면_실패한다 -x` | ❌ W0 | ⬜ pending |
| ENG-01 | TBD | 1 | argv 가 `.venv/bin/python3` + `run_ads.py` 로 조립된다 | — | N/A | unit | `pytest webapp/tests/test_argv.py -x` | ❌ W0 | ⬜ pending |
| ENG-02 | TBD | 2 | 서버가 죽어도 자식이 산다 (`start_new_session=True`) | — | N/A | integration | `pytest webapp/tests/test_jobs.py::test_자식은_서버_종료를_견딘다 -x` | ❌ W0 | ⬜ pending |
| ENG-03 | TBD | 2 | 작업 **중간 시점**에 로그파일이 이미 커져 있다 (`PYTHONUNBUFFERED=1`) | — | N/A | integration | `pytest webapp/tests/test_jobs.py::test_로그가_실시간으로_쌓인다 -x` | ❌ W0 | ⬜ pending |
| ENG-07 | TBD | 2 | `create_job` 이 HTTP 없이 호출된다 | — | N/A | unit | `pytest webapp/tests/test_jobs.py::test_create_job_은_http_없이_돈다 -x` | ❌ W0 | ⬜ pending |
| SAFE-01 | TBD | 1 | Host `evil.com` → 400 / Origin `evil.com` → 403 | T-1-01 | DNS rebinding·타 탭 CSRF 차단 | unit | `pytest webapp/tests/test_security.py -x` | ❌ W0 | ⬜ pending |
| SAFE-02 | TBD | 1 | 토큰 없음·틀림 → 403, 맞음 → 200 | T-1-02 | 부팅 토큰 없이는 쓰기 불가 | unit | `pytest webapp/tests/test_security.py -x` | ❌ W0 | ⬜ pending |
| SAFE-03 | TBD | 1 | 응답·로그·템플릿 어디에도 시크릿 문자열이 없다 | T-1-03 | 광고 시크릿·불사자 토큰 미노출 | unit | `pytest webapp/tests/test_security.py::test_시크릿이_새지_않는다 -x` | ❌ W0 | ⬜ pending |
| FLOW-01 | TBD | 3 | 미리보기 → 실행이 한 흐름으로 이어진다 | — | N/A | integration | `pytest webapp/tests/test_flow.py -x` | ❌ W0 | ⬜ pending |
| FLOW-02 | TBD | 3 | 실행이 미리보기와 **같은 targets 파일**을 지목 | T-1-06 | 화면 상태에서 대상을 다시 만들지 않는다 | unit | `pytest webapp/tests/test_flow.py::test_targets_파일이_하나다 -x` | ❌ W0 | ⬜ pending |
| FLOW-04 | TBD | 3 | 필터 전체 선택은 별도 배너로 한 번 더 확인 | — | N/A | manual | 브라우저 확인 (Tabulator API 는 JS) | — | ⬜ pending |
| FLOW-05 | TBD | 3 | 결과 JSON 이 항목별 성공/실패/스킵+사유를 담는다 | — | N/A | unit | `pytest webapp/tests/test_cli_patch.py::test_항목단위_결과 -x` | ❌ W0 | ⬜ pending |
| BOARD-01 | TBD | 2 | ①행에 `imp` 가 없어도 접기가 안 깨진다 | — | N/A | unit | `pytest webapp/tests/test_board.py::test_imp_없는_행도_접힌다 -x` | ❌ W0 | ⬜ pending |
| BOARD-02 | TBD | 2 | 계정 alias 가 `result.json` 에서만 온다 (가짜 5번째 계정 픽스처) | — | N/A | unit | `pytest webapp/tests/test_board.py::test_계정을_코드에_박지_않는다 -x` | ❌ W0 | ⬜ pending |
| BOARD-03 | TBD | 3 | 보이는 선택 vs 필터 전체가 다른 수를 준다 | — | N/A | manual | 브라우저 확인 | — | ⬜ pending |
| BOARD-04 | TBD | 3 | 선택 건수·예상 인상액 합계가 맞는다 | — | N/A | unit | `pytest webapp/tests/test_board.py::test_예상_인상액_합계 -x` | ❌ W0 | ⬜ pending |
| BID-01 | TBD | 3 | ①만 대상으로 잡힌다 (②③ 소재 제외) | — | N/A | unit | `pytest webapp/tests/test_board.py::test_대상은_규칙1_소재만 -x` | ❌ W0 | ⬜ pending |
| BID-02 | TBD | 3 | 그룹입찰 행의 `from` 이 `groupBid` 다 (웹앱은 **계산하지 않는다**) | T-1-07 | 진실이 둘이 되지 않는다 | unit | **기존** `test_bids.py::test_그룹입찰은_그룹기본가에_10원이다` + `pytest webapp/tests/test_board.py::test_웹앱은_입찰가를_계산하지_않는다 -x` | ✅ 존재 / ❌ W0 | ⬜ pending |
| BID-03 | TBD | 3 | 미리보기가 현재가 → 인상 후 가격을 보여준다 | — | N/A | unit | `pytest webapp/tests/test_flow.py::test_미리보기_표 -x` | ❌ W0 | ⬜ pending |
| BID-04 | TBD | 4 | 되돌리기가 **그 작업분만** 되돌린다 (백업 파일 불변) | T-1-08 | 회차 전체가 풀리지 않는다 | unit | `pytest webapp/tests/test_revert.py -x` | ❌ W0 | ⬜ pending |
| SC-03 | TBD | 2 | 탭 닫았다 열어도 로그를 처음부터 이어본다 | — | N/A | integration | `pytest webapp/tests/test_jobs.py::test_재접속하면_처음부터_이어본다 -x` (합성 잡, 3초) | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## 크레딧·광고비 0 으로 쓰기 경로를 검증하는 3층

프로젝트 제약이 "모든 쓰기는 dry-run 선행" 이다. 돈을 쓰지 않고 쓰기 경로를 증명하는 층이 셋 있다.

1. **`nvad.call` 몽키패치** — 기존 `test_bids.py` 가 이미 쓰는 방식(`bids.nvad.call = fake`). PUT 을 한 번도 안 내보내고 `committed`/`failed`/`result` 를 검증한다.
2. **CLI dry-run 실측 회귀** — `bids --preview-out` 은 **0.066초, 네트워크 0**:
   ```bash
   echo '["nad-a001-02-000000495390006"]' > /tmp/t.json
   .venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/run_ads.py bids \
     --run-dir 2026-08-30 --only-ads /tmp/t.json --preview-out /tmp/p.json
   python3 -c "import json;d=json.load(open('/tmp/p.json'));print({k:len(v.get('plans',[])) for k,v in d.items()})"
   # 기대: {'cy728':0,'cy7728':0,'ownway1':1,'pogeunae':0}
   ```
3. **웹앱 레벨** — `create_job` 이 조립한 argv 를 **실행하지 않고 문자열로만** 검증. `--commit` 이 안 붙는 경로를 못박는다.

**절대 금지:** 자동 테스트에서 `--commit` 실행. grep 가드를 Wave 0 에 둔다:
```bash
! grep -rn '"--commit"' webapp/tests/ || { echo "테스트에 --commit 이 있다"; exit 1; }
```

---

## 보안 3종 curl 검증 (전부 2026-09-19 실측 통과)

```bash
PORT=8765; T="$(cat .boot-token-for-test)"; B=http://127.0.0.1:$PORT

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

- [ ] `.venv-web` 생성 + 의존 4종 설치 (fastapi · uvicorn · jinja2 · sse-starlette) — **모든 웹앱 테스트의 전제**
- [ ] `webapp/pytest.ini` (또는 `pyproject.toml [tool.pytest.ini_options]`) + `.venv-web` 에 `pytest` 설치
- [ ] `webapp/tests/conftest.py` — `client`(TestClient + 토큰 픽스처) · `tmp_run_dir` · `fake_result_json` · `synthetic_job`
- [ ] `webapp/tests/fixtures/result_min.json` — 계정 **5개**(가짜 하나 추가해 BOARD-02 를 진짜로 검증) × 6규칙, ①은 `imp` 없이
- [ ] `webapp/tests/fixtures/targets_*.json`
- [ ] 합성 잡 러너 — `create_job(kind="synthetic", …)` 을 **테스트 전용**으로 열되 운영 라우트에는 노출 금지
- [ ] `.gitignore`: `.venv-web/` · `webapp.db*` · `webapp-logs/` · `node_modules/` · `package*.json`
- [ ] 테스트에 `--commit` 리터럴 금지 grep 가드
- [ ] 프론트 정적파일 `curl` vendoring (npm 안 쓴다 — 리서치 중 `node_modules/` 가 생겼다 삭제된 전례)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 보이는 선택 vs 필터 전체 선택이 다른 건수를 준다 | BOARD-03 | Tabulator 선택 API 가 브라우저 JS 안에서만 산다 | 보드에서 계정 필터를 건 뒤 헤더 체크박스 → 건수 확인 → "필터 전체 N건 선택" 배너 → 건수가 커지는지 확인 |
| 필터 전체 선택 시 확인 배너가 한 번 더 뜬다 | FLOW-04 | 같음 | 위 배너가 실제로 뜨고, 취소하면 선택이 안 넘어가는지 |
| 탭 닫았다 열어 진행 로그 이어보기 (실작업) | SC-03 | 실제 브라우저 생명주기 | `prep --account cy728` 실행 → 탭 닫기 → 30초 뒤 다시 열기 → 처음부터 로그가 다시 흐르고 진행이 이어지는지. **합성 잡 테스트가 자동 커버하므로 이건 최종 1회 확인용** |
| 회차 신선도 배너 | D-16 | 시각 확인 | 보드 상단에 `2026-08-30 회차 · N일 전` 이 뜨고, 오래되면 경고색인지 |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all ❌ W0 references above
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] 테스트에 `--commit` 리터럴 0건
- [ ] CLI 100 tests 여전히 exit=0 (회귀 기준선 불변)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
