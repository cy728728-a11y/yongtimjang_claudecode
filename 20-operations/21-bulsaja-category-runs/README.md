# 불사자 배치 작업 run 기록

불사자 상품 일괄 작업(카테고리 교정·썸네일 배경교체·상세페이지)의 run별 실행 기록.
run 폴더 명명: `MMDD_그룹명` (예: `0723_yong1-1`).

## thumbnail-done.json — 썸네일 전역 완료 대장

배치(run)를 넘어 "이미 썸네일 스킬로 작업한 상품"을 기억하는 장부.
새 썸네일 작업 시 이 대장과 대조해 완료 상품은 skip 한다.

- 구조: `accounts.<계정>.<productId>` = `{status, date, run, url?, name?, reason?}`
- 계정 키: `bulsaja`(용팀장) / `bulsaja-yongssaem`(용쌤)
- `status`: `ok`(교체 반영) | `kept-original`(생성 후 원본 유지 결정) — 둘 다 완료 취급
- 관리 모듈/CLI: `.claude/skills/thumbnail-bg-replace/scripts/thumb_ledger.py`
- 운영 규칙 전문: `thumbnail-bg-replace` 스킬 문서(SKILL.md)

## run 목록

- `0723_yong1-1` — 용쌤 1-1 신규수집 100건 (카테고리 100 · 썸네일 99+원본유지 1 · 상세 96, 상세는 1장 사고)
