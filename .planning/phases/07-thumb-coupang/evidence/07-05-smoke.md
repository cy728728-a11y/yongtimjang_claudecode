# 07-05 실데이터 미리보기 스모크 — BLOCKED (gws 인증 만료)

- 일시: 2026-09-29 11:25:44 ~ 11:25:47 (+09:00)
- 잡 id: `f54afee0-3f7a-4df1-9ca2-9f49e1b43667` (coupang_preview)
- 경로: 서버 재기동(도는 잡 0개 확인 후) → `curl -X POST /jobs/coupang/preview -d '{}'` (토큰 헤더) — 빈 본문
- run-dir: `~/python_work/data/coupang/runs/web-f54afee0-3f7a-4df1-9ca2-9f49e1b43667/` — **파일은 `summary.json` 하나뿐**
- 쓰기 0 · 크레딧 0 · 불사자 접속 0 (prep 에서 멈춰 resolve 이후 단계가 안 떴다)

## 판정: BLOCKED — prep 단계 gws 401

진행 로그 원문(요지):

```
###STAGE### prep 시작
[prep] 주문시트 1D--UaQRTt3ofTQo087F0-HrcebR9SistTBmXezIwY90
RuntimeError: gws API 오류 401: Authentication failed: Failed to get token: Server error: invalid_grant: Bad Request
###STAGE### prep exit 1
###COUPANG### preview 통과 0 · 이미있음 0 · 기준 - · 정지 prep
```

summary.json: `{"단계":[{"이름":"prep","exit":1}], "정지단계":"prep", "기준":"", "통과":[], ...}`

화면 조각(`GET /jobs/{id}/result`, HX): `'prep' 단계에서 멈췄다(종료코드 1) — 복사 버튼을 그리지 않는다` ·
`정지단계: prep (주문시트 집계(gws))` · gws 재로그인 안내 1줄 · 복사 영역(details) 없음. — D-09 "비0 이면 그 단계 이름이 보인다" 는 실데이터로 확인됨.

## 확인 못 한 항목 (gws 복구 뒤 07-07 첫 미리보기에서)

| 항목 | 상태 | 비고 |
|---|---|---|
| 기준 문구 | **미측정** | 기준 줄은 gate 가 찍는다 — prep 에서 멈춰 없음. 게다가 workspace.toml `[coupang] min_margin = 15.0` 그대로(07-07 용팀장 결정) → 지금 돌려도 15.0 이 찍힌다. CP-03 20% 는 toml 전환 뒤에만 성립 |
| 통과 N · 이미있음 M · 탈락사유별 | 미측정 | |
| 그룹읽기 총상품수 == 읽음 (A3) | 미측정 | 07-03 `collect_group_strict` — 틀리면 exit 3 fail-closed |
| 파일럿 교집합 0 (CP-04) | 미측정 | 1차 파일럿 `coupang/runs/20260913-1215/copied.jsonl` = 85행(원본pid·타오바오상품번호 있음). 07-07 미리보기 뒤 이번 통과 대표pid/타오바오번호와 교집합 0, rejected.json 에서 그 원본들이 `쿠팡그룹에이미있음` 인 건수를 셀 것 |
| 첫 커밋 상한 · 복사예정 목록 | 미측정 | 상한은 코드상 10(`first_coupang_commit_done()` = False — 레지스트리에 coupang_commit 0개) |
| uat-verifier 화면 판정 | **pending** | 이 실행 환경에서 서브에이전트를 띄울 수 없다 — SUMMARY 의 Pending UAT 조건으로 넘김 |

## 쓰기 0 증명

- 미리보기 run-dir 에 `copied.jsonl` 없음 (파일 = summary.json 1개)
- 잡 레지스트리 `coupang_commit` 0개 (`children_of(f54afee0…, "coupang_commit")` = 0)
- 건수 입력·복사 버튼 조작 없음 (curl 로 미리보기만)

## 복구 절차 (사용자 몫 — 에이전트는 재로그인하지 않는다)

1. 터미널에서 `gws auth login` — **cy728728 계정**으로 로그인("다른 계정 사용")
2. 그래도 401/403 이면 gws `token_cache.json` 삭제 후 다시 로그인
3. 보드 상단 `쿠팡 후보 뽑기 — 쓰기 0` 을 다시 누르면 된다 (07-07 에서 toml 20.0 전환과 함께)

## 부수 관찰

- 잡 행 상태가 `failed` 가 아니라 `orphaned`(exit None)로 남았다. 원인: 검증용으로 **서버 밖 파이썬 프로세스**에서 `jobs.job_status()` 를 폴링했고, 그 프로세스는 `_PROCS` 에 Popen 이 없어 자식이 끝난 순간 `_reap` 이 `orphaned` 로 적었다(서버가 먼저 거뒀다면 failed/1). 운영 경로(브라우저 → 서버)에선 안 생긴다. 화면이 "종료코드 None" 을 보이던 것은 f9f2263 에서 요약의 단계 코드(1)를 보이게 고쳤다.
