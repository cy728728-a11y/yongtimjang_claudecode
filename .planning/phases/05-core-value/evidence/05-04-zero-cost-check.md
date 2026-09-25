# 05-04 크레딧 0 실측 기록

- 일시: 2026-09-25 14:45~14:47 KST
- 판정: **A(CLI 견적 스모크) PASS** · **B(uat-verifier 화면 점검) BLOCKED — 실행기에서 에이전트를 못 띄워 오케스트레이터로 넘겼다(아래 조건)**
- 접수 0 · generate 0 · 불사자 쓰기 0 · 크레딧 변화 0

## 사전 확인

| 항목 | 결과 |
|------|------|
| 도는 불사자·쓰기 잡 | 없음 — `webapp.db` 를 `mode=ro` 로 조회(`status IN (running, starting)` 0건), `ps` 에 detail_batch/bulsaja_scan/ss_index/banner_scan 프로세스 없음 (429 todo 준수) |
| 사용자 웹앱 서버(:8765, PID 41865) | 건드리지 않음 — 재시작·POST·GET 0회 |
| 계정 (ENG-08) | `bulsaja_my_profile` 읽기 1회 → 닉네임 **부킹** = `workspace.toml [webapp] expected_bulsaja_nick` 일치 |
| 잔액 (전) | **보유 929,482 · 오늘 무료 800 · 총 930,282크레딧** (05:45:17Z) |

## A. CLI 견적 스모크 — PASS

### 입력 (`smoke_inputs.py`)

- 회차 2026-09-20 · 배너 산출물 `232c3bb3`(생성 2026-09-25T00:14:25) · 조인 산출물 `0889aa1f` — 잡 DB 를 읽기 전용으로 조회해 찾았다(`jobs.latest_done` 은 `_reap` 로 DB 를 고치므로 안 불렀다)
- 보드 기준 🔴 후보(= `join.selectable` 통과 · 상세상태 `중국어원본`): **5건**
- 관문 결과: inputs **4건** · 제외 1건(사유 `스킵된 상품이다: 제거율초과 — 라벨로 되살리지 않는다 (D-04)`)
- **D-02 ① 우회는 이 스크립트에서만** 했다(`확인시각=산출물 생성시각`). 출력은 `evidence/smoke/`(회차 `web/` 밖, `.gitignore`) — 접수 라우트가 가리킬 수 없다
- 연구 §실데이터의 "🔴 6건" 과 1건 차이: 연구는 ②③ 통과 기준 집계, 여기선 보드의 기본 선택 규칙(`join.selectable`) + 배너 스킵(D-04) 을 먼저 거쳤다. 5건 중 1건이 제거율초과 스킵이라 4건

### 실행

```
.venv/bin/python3 .claude/skills/bulsaja-detail-page/scripts/detail_batch.py \
  --run-dir evidence/smoke --inputs evidence/smoke/inputs.json \
  --done-tag 구매_가공완료 --expect-nick 부킹 \
  --estimate-only --estimate-out evidence/smoke/estimate.json
```

`--max-credits` · `--summary-out` 를 주지 않았다 — 접수 모드로 들어갈 길이 없다(주면 CLI 가 exit 2).
실행 전 코드로 확인: 견적 경로(`_입력모드 → _계정확인 → _견적`)가 부르는 MCP 도구는 `bulsaja_my_profile` · `bulsaja_product_find_by_code` · `bulsaja_product_workdata(mode=summary)` 셋뿐이다(전부 조회). `bulsaja_detail_page_generate` 는 `_입력접수`/`submit_one` 에만 있다.

### 결과

| 항목 | 값 |
|------|----|
| 종료코드 | **0** (6초, 05:46:10Z → 05:46:16Z) |
| 계정 / 잔액(CLI 가 실은 값) | 부킹 / `보유 929,482 · 오늘 무료 800 · 총 930,282크레딧` (문자열 — 숫자 아님, 견적 표는 문자열 그대로 보인다) |
| 선택 · 스킵 · 접수 | 4 · 0 · 4 |
| 총 장수 | **40장** (4 × 10) |
| 예상 크레딧 | **200** (장당 5 · 일반화질) |
| 잘린 상품(10장 초과) | **3개** (제품 이미지 27→10 · 29→10 · 15→10, 나머지 1건은 딱 10장) |
| 항목별 판정 | 4건 모두 `접수`, 사유 없음 — 태그 근거 스킵 0 · aiImageGenerated 근거 스킵 0 |
| 센티널 | `###ESTIMATE### 선택 4 / 접수 4 / 스킵 0 / 총장수 40 / 예상크레딧 200 / 잘린상품 3` |

### 응답 모양 (A2 포함)

- **A2 — `find_by_code` 의 `그룹` 필드가 채워지는가: 예.** 같은 4코드로 한 번 더 읽어 봤다 → 3건 `'구매'`, 1건 `None`. 키 목록 `productId · 그룹 · 불사자코드 · 상태 · 상품명 · 수집처 · 업로드된마켓 · 잠금 · 판매가 · 판매자상품코드`. `None` 1건은 조인 산출물(`그룹태그`)에서도 `None` 이라 서로 맞다(그룹 미배정으로 보인다)
  - ⚠️ 남은 위험: 메모리 `bulsaja-list-group-field-null` 처럼 이 필드가 다시 **전건 null** 로 내려오면 CLI 는 태그 없음으로 읽고 `aiImageGenerated` 한 줄만 남는다. 05-05 실탄 전 견적에서 `그룹` 분포(전건 None 이면 멈춤)를 한 번 더 본다
- **workdata(summary)**: 최상위 `data · success · 상세페이지있음 · 상품명 · 썸네일번역됨 · 썸네일수 · 옵션번역됨 · 옵션수 · 표시규칙`. `data.uploadDetailContents` 키는 `imageTranslated · renderContent` 두 개 — **`aiImageGenerated` 키 자체가 없다**(아직 AI 상세를 만든 적 없는 상품의 정상 모양으로 보인다. CLI 는 없으면 False 로 읽는다). 이상 없음

### 크레딧 0 증거

| 증거 | 결과 |
|------|------|
| 잔액 (후, 05:46Z 두 번) | **총 930,282크레딧 — 전과 같다** |
| `evidence/smoke/detail_status.json` | **없다** (접수 체크포인트 0) |
| 스모크 폴더에 `bulsaja_detail_page_generate` 문자열 | 없다 |
| 추가 읽기 호출 | my_profile 3회(전·후·후) · find_by_code 2회 · workdata 5회 — 전부 조회 |

## B. uat-verifier 화면 점검 — BLOCKED (오케스트레이터 대기)

이 실행기(gsd-executor)에는 에이전트를 띄우는 도구가 없어 uat-verifier 를 부르지 못했다. **05-02 · 05-03 · 05-04 를 한 번에 묶어** 오케스트레이터가 부른다. 조건과 항목은 `05-04-SUMMARY.md` 의 "UI 자동 검증 — 오케스트레이터 대기" 에 통합해 뒀다.

대신 한 자동 점검(브라우저 없음): 웹앱 스위트 **613 passed** · `node --check webapp/static/board.js` OK · 새 템플릿 `| safe` 0건 · 결과 표에 재접수/retry 문구 0건.

## 정리 결과

- 띄운 서버·브라우저 없음. 스모크 산출물은 `evidence/smoke/`(git 제외)에 남겨 뒀다 — 05-05 가 같은 비교를 할 때 참고
