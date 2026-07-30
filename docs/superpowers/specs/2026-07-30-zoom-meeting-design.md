# Zoom 미팅 생성 스킬 — 설계 문서

## 배경 / 목적

"몇월몇일 몇시에 제목 뭐로 몇시간짜리 줌미팅 잡아줘" 같은 자연어 요청을 받으면, 실제 Zoom API를 호출해 미팅을 생성하고 join 링크를 대화창에 바로 반환하는 스킬. 강의(구매대행 실전반 등) 진행용으로 사용.

## 전제 조건

- Zoom 계정 플랜: 유료(Pro 이상) — 시간 제한 없음
- Zoom App Marketplace에서 **Server-to-Server OAuth 앱** 생성 필요 (Account ID / Client ID / Client Secret 발급)
- 자격증명은 워크스페이스 루트 `.env`에 저장 (git 제외, send-email 스킬과 동일 패턴):
  - `ZOOM_ACCOUNT_ID`
  - `ZOOM_CLIENT_ID`
  - `ZOOM_CLIENT_SECRET`

## 아키텍처

```
스킬 트리거 (자연어 요청)
  → [1] 필수 항목 확인 (날짜/시작시간/소요시간/제목 중 누락분 질문)
  → [2] zoom_meeting.py 실행 (OAuth 토큰 발급 → 미팅 생성 API 호출)
  → [3] 결과 출력 (제목/일시/join_url)
  → [4] "줌 오픈" 리마인더 자동 등록 (시작시간 - 30분)
```

- 스킬 정의: `.claude/skills/zoom-meeting/SKILL.md`
- 실행 스크립트: `10-projects/줌미팅-자동화/zoom_meeting.py` (Python 표준 라이브러리 + `requests`, 한국어 주석, try-except)
- 자격증명 템플릿: `10-projects/줌미팅-자동화/.env.example`

## 컴포넌트 상세

### 1. 입력 파싱 및 확인 (Claude 담당, 스크립트 아님)

사용자 요청에서 다음 4개 항목을 자연어로 추출:
- 날짜 (연도 생략 시 올해로 간주)
- 시작시간 (시간대는 KST 고정)
- 소요시간 (예: "2시간" → 120분)
- 제목

**4개 중 하나라도 빠져 있으면, 진행 전에 빠진 항목만 사용자에게 질문한다.** (한 번에 몰아서 질문, 있는 정보는 다시 묻지 않음)

**제목은 특별 취급**: 날짜/시간/소요시간과 달리, 제목은 요청에 명시되지 않은 경우 **절대 임의로 추정/생성하지 않고 항상 질문한다.** (예: "8월5일 2시에 2시간 줌미팅 잡아줘"처럼 제목 없이 요청이 와도 "제목은 뭐로 할까요?"를 반드시 물어본다.)

### 2. zoom_meeting.py

**입력 (CLI 인자)**:
```
--topic "제목"
--start "2026-08-05T14:00:00"   # KST, ISO8601
--duration 120                    # 분 단위
```

**동작**:
1. `POST https://zoom.us/oauth/token` (`grant_type=account_credentials`, `account_id=...`) 로 access token 발급
2. `POST https://api.zoom.us/v2/users/me/meetings` 로 미팅 생성
   - `type: 2` (예약)
   - `timezone: Asia/Seoul`
   - `settings.waiting_room: false`
   - `settings.join_before_host` 등 조기입장 관련 설정은 사용하지 않음 (아래 "조기 오픈" 참고)
3. 응답에서 `topic`, `start_time`, `join_url`, `start_url` 추출

**출력**: stdout에 JSON 한 줄 (Claude가 파싱해서 사용자에게 보여줌)
```json
{"topic": "...", "start_time": "...", "join_url": "...", "start_url": "..."}
```

**에러 처리**:
- `.env` 값 누락/빈 값 → 실행 전 체크, Zoom App Marketplace에서 Server-to-Server OAuth 앱 만드는 법 안내 메시지 출력 후 종료
- OAuth 토큰 발급 실패 (401 등) → Zoom이 반환한 에러 메시지 그대로 stderr 출력
- 미팅 생성 API 실패 → 동일하게 Zoom 에러 메시지 그대로 전달

### 3. 결과 출력 (Claude 담당)

성공 시 대화창에 다음만 간결하게 표시:
- 제목
- 일시 (날짜 + 시작시간 + 소요시간)
- join_url

`start_url`은 화면에 노출하지 않고 리마인더 등록에만 사용 (호스트 전용 링크이므로 대화 로그에 남기지 않는 것이 안전).

### 4. 조기 오픈 처리

**핵심 사실**: Zoom에서 `start_time`/`duration`은 캘린더 표시용 메타데이터일 뿐이다. 호스트가 `start_url`로 접속하는 순간 미팅은 즉시 열리며(예약 시간과 무관), 참가자는 `waiting_room: false` 설정 덕분에 그 순간부터 바로 입장 가능하다. 즉 "30분 일찍 열기"는 API 설정이 아니라 **호스트가 30분 일찍 접속하기만 하면 되는 것**이다.

**구현**: 미팅 생성 성공 직후, (시작시간 - 30분) 시각에 "줌 오픈" 리마인더를 todo 스킬을 통해 자동 등록한다. 별도 사용자 확인 없이 등록 (메모리 규칙: 리마인더는 일단 다 건다).

`join_before_host` API 설정(Zoom 제약상 최대 15분까지만 지원, 30분 불가)은 사용하지 않는다 — 리마인더 방식으로 충분히 해결되므로 범위 밖.

## 범위 밖 (YAGNI)

- Google Calendar 등록 없음 (join_url만 반환)
- 반복 미팅 없음, 단건 생성만
- 참가자 초대(이메일 발송) 없음 — 필요 시 send-email 스킬과 별도 조합
- `join_before_host` 미적용 (리마인더로 대체)
- 미팅 자동 종료/시간 강제 없음 (Zoom 자체가 duration을 강제하지 않음, 최대 약 30시간까지 무제한 진행)

## 테스트 계획

- `.env` 자격증명 없이 실행 → 안내 메시지 확인
- 정상 입력으로 실제 Zoom 미팅 생성 → join_url 유효성 확인 (브라우저에서 열어 미팅 존재 확인)
- 날짜/시간/제목 중 일부 누락된 자연어 요청 → 빠진 항목만 질문하는지 확인
- 미팅 생성 후 리마인더가 (시작시간-30분)에 정확히 등록되는지 확인
