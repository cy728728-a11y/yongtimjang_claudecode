---
status: complete
---
# 261016-wb2 업무판 연동·이월 (work-board)
- `board_sync.py sync|rollover` + 테스트 6개 통과. 이룸 '오늘'에서 용팀장 몫 연동(1행), 빈 줄 체크박스 문제 정리(append 가 301행으로 밀리던 것), dry-run 시험 행 제거.
- launchd: board-sync 매시간 · board-rollover 04:30 로드 완료. workspace.toml 에 `eroom_board` 추가(git 밖).
