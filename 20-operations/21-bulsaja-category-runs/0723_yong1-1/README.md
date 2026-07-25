# 용쌤 1-1 신규수집 100건 일괄 작업 (2026-07-23)

용쌤 계정(bulsaja-yongssaem) `1번_용쌤1-1` 그룹, 7/22 23:44 일괄 수집분 100개 대상.
카테고리 교정 → 썸네일 배경교체 → AI 상세페이지 3단계 파이프라인 실행 기록.

## 결과 요약

| 단계 | 결과 |
|------|------|
| 카테고리 교정 | **100/100 저장** (1차 자동 93 + 썸네일 비전보정 5 + 조준 재시도 2, 이후 썸네일 불일치 3건 재교정) |
| 썸네일 (gpt-image-2 배경교체) | 100장 생성, **99건 반영** (윈드스크린 1건 원본 유지), 비전 검수 100장 |
| AI 상세페이지 (일반화질) | **96/100 완료** (4건 서버측 생성 실패 3회 — 크레딧 미차감). **⚠️ 전량 1장짜리로 생성됨** → 7/23 다장수 재작업으로 대체 (아래 "재작업" 참조) |

- 상세페이지 실패 4건: 탁상바이스(0RA4FADX) · 판금 스폿용접기(6SA6D188) · 카약보트(CAN0HG6T) · 포대 봉합기(9S54JN6H)
- 썸네일 불일치 재교정 3건: 달비계의자→오토바이 윈드스크린 / 걸이식 쓰레기통→싱크대 배수관 / 낚시텐트 매트→놀이방 단면매트
- 크레딧: 오늘 무료분 480만 사용(96장×5), 보유분 그대로

## 파일

- `targets.json` 대상 100건 (시트 A열 순서 = row)
- `products.json` workdata 요약 (기존 카테고리·썸네일 URL)
- `keywords.json` / `sellha.json` 대표 검색어·셀하 조회 결과
- `decisions*.json` / `steer_results.json` 카테고리 저장 판정 (메인/비전/fix3/조준)
- `gen_status.json` / `upload_status.json` 썸네일 생성·업로드 체크포인트
- `detail_status.json` 상세페이지 taskId·상태
- `scripts/` 재사용 스크립트 (아래)

## 재사용 스크립트 (scripts/)

- `run_yong.py` — **용쌤 서버 라우팅 래퍼**: `~/.claude.json` 의 `mcpServers.bulsaja-yongssaem`
  토큰을 `BULSAJA_MCP_URL/BULSAJA_MCP_TOKEN` 환경변수로 주입해 하위 명령 실행.
  bulsaja-category-fix 스킬의 `bulsaja_mcp.py` 는 이 환경변수를 최우선으로 읽으므로
  `python run_yong.py python <스킬스크립트> ...` 형태로 스킬 전체를 용쌤 계정으로 돌릴 수 있음.
- `stage2_gen.py` — 썸네일 원본 다운로드 + gpt-image-2 배경교체 배치(병렬 3워커, 체크포인트).
  **전역 완료 대장(`../thumbnail-done.json`) 연동** — 과거 run에서 작업한 상품은 생성 자체 skip
  (`--account`, `--ignore-ledger` 참조. 규칙: thumbnail-bg-replace 스킬 문서)
- `stage2_upload.py` — 불사자 업로드 티켓(`X-MCP-Upload-Ticket` 헤더) → 대표이미지 교체(2단계 확인).
  저장 성공 시 전역 완료 대장에 자동 기록
- `stage3_detail.py` — AI 상세페이지 접수(확인식)→폴링 배치 (체크포인트·재개).
  **⚠️ 구버전 — 사용 금지**: 장수(섹션 수) 미지정으로 96건 전부 **1장짜리**로 생성된 원인
  (2026-07-23 발견, 서버 기록 "진행 1/1" 확인). UI 버튼은 10장 기준.
  → `.claude/skills/bulsaja-detail-page/scripts/detail_batch.py` (기본 10장 + 첫 건 검증)로 대체됨.
- `setup_sheet.py` / `sheet_sync.py` — 카테고리교정 로그 시트 생성·일괄 동기화 (gws 인증 필요)
- `commit_steer.py` — 부분일치확인요 keyword 변형 조준+즉시 커밋

## 재작업 (7/23, 상세페이지 다장수)

1장 사고분을 `bulsaja-detail-page` 스킬(`detail_batch.py`)로 전량 재작업.
핵심: **이미지 목록(썸네일+옵션, 최대 10장) + 장수(sectionCount)를 동시에 접수해야** 다장수가 됨.

- 결과: **95/100 완료** (10장 60 · 9장 7 · 8장 7 · 7장 15 · 6장 4 · 5장 2 — 10장 미만은 상품 보유 이미지 수 한계)
- 생성 이미지 858장+, 실사용 약 4,355크레딧 (실패분 미차감)
- 실패 5건 (각 2회 시도, 서버측 생성 실패 — 고객센터 문의 대상):
  쇠모루(0RA4FADX) · 판금 스폿(6SA6D188) · 카약보트(CAN0HG6T) · 함마드릴(1WJE9SRF) · 포대 봉합기(9S54JN6H)
  ※ 이 중 앞의 3건 + 포대 봉합기는 7/22 1장 작업 때도 3회 실패했던 동일 상품
- 체크포인트: `detail_status_redo10.json` (작업번호·장수·상태)

## 미완(시트)

gws 토큰 만료(OAuth Testing 모드 7일 주기)로 구글시트 로그 미기록.
재인증 후 `setup_sheet.py <targets.json>` → `sheet_sync.py <이 폴더>` 실행하면
`카테고리교정_1번_용쌤1-1` 시트가 생성·기록됨 (폴더/마스터 인덱스는 스킬 문서 참조).
