---
name: work-board
description: 용팀장 업무판(구글시트 '🖤 용팀장 업무판') '오늘' 탭을 관리한다 — 이룸 업무판에서 용팀장 몫 행을 매시간 가져오고(sync), 매일 04:30 지난 행을 정리한다(rollover: 완료·자동 보고는 '기록' 탭으로, 미완료는 오늘로 이월). "업무판 연동", "업무판 정리", "오늘 탭 정리", "이룸 판에서 가져와", "work-board" 등을 언급하면 자동 실행.
---

# 용팀장 업무판 연동·이월

시트 ID 는 `workspace.toml` `[sheets]` 의 `work_board`(내 판) · `eroom_board`(이룸 판, 읽기만).

```bash
.venv/bin/python3 .claude/skills/work-board/scripts/board_sync.py sync [--dry-run]      # 이룸 몫 가져오기
.venv/bin/python3 .claude/skills/work-board/scripts/board_sync.py rollover [--dry-run]  # 날짜 넘기기
```

## 규칙
- **이룸 몫**: 이룸 '오늘' 행 중 담당 또는 할 일에 `용팀장` 이 들어간 행. 연동키 = `업무# + 할 일의 '—' 앞부분`
  (숫자가 바뀌어도 같은 행으로 보고 할 일·메모를 갱신). 이룸이 ✓ 하면 내 것도 ✓, 반대로 되돌리지는 않는다.
- **rollover**: 날짜가 지난 행 중 ✓ 완료 · 출처 `자동`(sold-lock·광고 주간 보고) · `[dry-run]` 행은 '기록' 탭으로,
  나머지는 오늘 날짜로 바꾸고 이월 +1.
- 매번 '오늘' 탭을 **빈 줄 없이** 다시 쓰고 체크박스를 실제 행에만 건다. 빈 줄에 체크박스(FALSE)가 깔리면
  다른 스크립트의 append 가 300행 아래로 밀린다(2026-10-16 실측).
- 열 J `연동키` 는 스크립트용이다. 손으로 고치지 않는다.

## 자동 실행 (맥북 launchd)
- `com.eroom.board-sync` — 1시간마다 sync
- `com.eroom.board-rollover` — 매일 04:30 rollover (00:01 sold-lock 보다 뒤, 그날 행은 안 건드림)

설치(템플릿 치환 후 로드):
```bash
W=$PWD; for n in board-sync board-rollover; do
  sed -e "s|__WORKSPACE__|$W|g" -e "s|__HOME__|$HOME|g" .claude/skills/work-board/launchd/com.eroom.$n.plist > ~/Library/LaunchAgents/com.eroom.$n.plist
  launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.eroom.$n.plist; done
```
로그: `~/python_work/data/work-board/logs/`

## 예약 실행 (2026-10-17 변경)

> **예약 실행은 `.claude/lib/eroom_scheduler.py`(launchd `com.eroom.scheduler`, 1분 틱) 한 곳에서 한다.** 이 맥북에선 새로 등록한 StartCalendarInterval 이 안 터져서(2026-10-17 실측) 개별 plist 를 없앴다. 시각을 바꾸려면 그 파일의 `JOBS` 표를 고친다. 로그: `~/python_work/data/scheduler/logs/<작업>.log`
