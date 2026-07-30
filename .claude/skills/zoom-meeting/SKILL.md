---
name: zoom-meeting
description: 자연어 요청("줌미팅 잡아줘", "줌 링크 만들어줘")을 받아 Zoom Server-to-Server OAuth API로 실제 미팅을 생성하고 join 링크를 반환. 날짜/시작시간/소요시간이 빠지면 먼저 질문하고, 제목은 명시돼도 없어도 항상 확인 질문. 생성 직후 (시작시간-30분)에 "줌 오픈" 리마인더를 todo에 자동 등록.
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
---

# zoom-meeting

Zoom Server-to-Server OAuth로 실제 미팅을 예약하고 join_url을 대화창에 반환하는 스킬.
실행 엔진은 `10-projects/줌미팅-자동화/zoom_meeting.py` (표준 라이브러리만 사용).

## 전제

- 자격증명은 워크스페이스 루트 `.env`의 `ZOOM_ACCOUNT_ID`/`ZOOM_CLIENT_ID`/`ZOOM_CLIENT_SECRET`/`ZOOM_USER_EMAIL`에서 읽음 (git 제외)
- 값이 없으면 스크립트가 안내 메시지 출력 → 사용자에게 Server-to-Server OAuth 앱 생성 안내 (marketplace.zoom.us > Developer > Build App)

## 수행 순서

### 1. 입력 파싱 및 확인

사용자 요청에서 **날짜 / 시작시간 / 소요시간 / 제목** 4개를 추출한다.

- 날짜/시작시간/소요시간 중 빠진 게 있으면, 빠진 항목만 한 번에 질문
- **제목은 요청에 이미 포함돼 있어도 항상 재확인 질문한다.** ("제목은 뭐로 할까요?") 절대 임의로 만들거나, 사용자가 준 값을 확인 없이 그대로 쓰지 않는다.
  - 예시 1 (제목 미지정): "8월5일 2시에 2시간 줌미팅 잡아줘" → "제목은 뭐로 할까요?" 질문
  - 예시 2 (제목 기제시): "8월5일 2시에 2시간 '실전반 4주차' 줌미팅 잡아줘" → "제목은 '실전반 4주차'로 할까요?" 재확인 질문
- 연도 생략 시 올해로 간주, 시간대는 KST 고정
- "N시간" → 분 단위로 환산 (예: 2시간 → 120)

### 2. 미팅 생성

Windows(이 워크스페이스)에서는 venv 파이썬 사용:

```bash
.venv/Scripts/python.exe "10-projects/줌미팅-자동화/zoom_meeting.py" \
  --topic "제목" \
  --start "2026-08-05T14:00:00" \
  --duration 120
```

- 성공: stdout에 JSON 한 줄 (`topic`, `start_time`, `duration`, `join_url`, `start_url`)
- 실패: stderr 메시지를 그대로 사용자에게 전달 (자격증명 문제 / Zoom API 에러)

### 3. 결과 출력

대화창에는 다음만 간결하게 표시:
- 제목
- 일시 (날짜 + 시작시간 + 소요시간)
- join_url

`start_url`은 호스트 전용 링크이므로 대화 로그에 노출하지 않는다 (리마인더 등록에만 사용).

### 4. 조기 오픈 리마인더 자동 등록

미팅 생성 성공 직후, (시작시간 - 30분) 시각을 계산해 `40-personal/46-todos/active-todos.md`에 아래 규칙으로 직접 추가 (별도 확인 질문 없이 바로 등록):

- **당일 미팅**: `## Today` 섹션에 추가 (added 필드만, due 필드 불필요)
- **미래 날짜**: `## Scheduled` 섹션에 추가 (due 필드는 미팅 날짜로 설정)

예시:

```markdown
# 당일 미팅 (## Today에 추가)
- [ ] 줌 오픈: [제목] (HH:MM 접속 → start_url로 열기)
  - added: YYYY-MM-DD HH:MM
  - priority: normal

# 미래 날짜 미팅 (## Scheduled에 추가)
- [ ] 줌 오픈: [제목] (HH:MM 접속 → start_url로 열기)
  - added: YYYY-MM-DD
  - due: YYYY-MM-DD
  - priority: normal
```

Zoom은 호스트가 `start_url`로 접속하는 순간 예약 시간과 무관하게 즉시 미팅을 열기 때문에, 이 리마인더 시각에 접속하면 30분 조기 오픈이 그대로 달성된다.

## 참고

- `waiting_room: false`로 생성되므로 참가자는 대기실 없이 바로 입장 (단, 호스트가 미팅을 연 이후에만 가능)
- 반복 미팅/참가자 초대/Google Calendar 등록은 범위 밖 (필요 시 send-email 스킬과 별도 조합)
- 스크립트 상세: `10-projects/줌미팅-자동화/zoom_meeting.py`
- 자격증명 템플릿: `10-projects/줌미팅-자동화/.env.example`
