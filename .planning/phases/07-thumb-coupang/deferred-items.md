# Phase 07 — Deferred Items

## D-08 썸네일 → Phase 6 market_preview 부모 출처 — 미룸 (07-04, 2026-09-29)

- **무엇:** 썸네일 결과(불사자 저장 완료분)를 스마트스토어 반영(Phase 6 `market_preview` → `market_commit`)의 부모로 잇는 연결.
- **이유:** Phase 6 미완(06-05 / 06-06). 그리고 `argv.MarketArgv` 가 ⓐ `detail_backup_dir` 를 필수로 받는데, 썸네일에는 ⓐ 에 대응하는 상세 백업이 없다 — 의미를 다시 정해야 한다.
- **재개 조건:** Phase 6 완료 + ⓐ(상세 백업) 의미 재정의(썸네일 반영에선 무엇을 되돌림 근거로 삼는가).
- **재개 시 바꿀 자리:**
  - `webapp/jobs.py` 의 `_마켓부모` 집합 — `thumb_estimate`(또는 썸네일 커밋 잡)를 부모로 허용
  - `webapp/argv.py` `MarketArgv` 의 ⓐ 검사
  - 입력 = 그룹 run-dir 의 `commit_summary.json`(`완료` pid 목록)
- **지금 화면:** 썸네일 결과 표 하단에 "스토어 반영 미연결(Phase 6 완료 후)" 한 줄.
- **확인:** 07-06 첫 체크포인트에서 용팀장 확인.
