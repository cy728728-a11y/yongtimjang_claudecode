# 카톡 체크 → 업무 라우팅 상세 (Mac)

> SKILL.md "카톡 체크 워크플로"의 상세 규약. raw 파일 포맷·1:1 판별·노이즈 필터.

## 라우팅 연결고리 (방안 A — 2026-06-02)

카톡 직독은 raw 파일을 안 만들어서 그냥 두면 inbox-triage의 성숙한 라우팅(목적지 매핑·이중등록 방지·proposal 게이트)을 **하나도 못 쓴다.** 그래서 카톡 체크가 업무 후보를 **텔레그램과 호환되는 raw 파일**로 떨궈 같은 디스패처를 타게 한다. 라우팅 로직은 inbox-triage 한 곳에만 산다(중복·drift 없음).

**언제 떨구나**: 읽은 창에 *업무 신호*(날짜·시간·장소 약속 / 해야 할 일 / 회사·AX 도입 문의 / 사람이 보낸 회신요망 질문)가 있을 때만. 잡담·안부·이미 끝난 대화는 떨구지 않는다.

**무엇을 떨구나**: **읽은 방(1:1) 1개당 raw 파일 1개.** 한 방에 여러 업무 항목이 섞여 있어도 한 파일에 담는다 — 쪼개기/흡수는 inbox-triage가 한다. 본문에는 (a) 판정 근거가 되도록 *관련 메시지 원문 인용* + (b) 추출한 업무 후보 요약을 같이 넣는다.

**파일명·포맷** (telegram-inbox-reader.py 규약과 1:1 호환, `source`만 다름):

```
파일명: 00-inbox/raw/{방의_마지막메시지시각 YYYY-MM-DD_HHMMSS}_kakao-{chatId}.md
```
```markdown
---
source: kakao-check
collected: {지금 YYYY-MM-DD HH:MM:SS}
kakao_date: {방 마지막 메시지 시각 YYYY-MM-DD HH:MM:SS}
kakao_chat_id: {chatId}
kakao_room: {방 이름}
direction: in
channel: kakao
processed: false
---

# [미처리] 카톡 체크 — {방 이름}

- 방: {방 이름} (chatId {chatId})
- 창: '지난 체크 이후' 메시지

## 본문
\```
{관련 메시지 원문 — 발신자/시각 포함, 판정 근거로 충분하게}
\```

## 업무 후보 (추출 요약)
- {약속/할일/AX 등 1줄씩}
```

`processed:false`라서 inbox-triage Step 0 스캔(`grep -lZ "processed: false"`)에 그대로 잡힌다. inbox-triage는 `source: kakao-check`도 인식한다(그쪽 Step 1 참조). 마킹(routed_to/triaged)·라우팅은 전부 inbox-triage가 한다 — 카톡 체크는 떨구고 손 뗀다.

## 방 판별 (검증 2026-06-02, 소규모 그룹 확장 2026-06-09)

**1:1**: `NTChatRoom.directChatMemberUserId != 0`. **모든 방이 이 칸 NOT NULL**이고, 단톡(type1)·오픈챗(type4)·채널(type5)은 값이 **0**, 친구(type0)·비즈니스 계정(type2, 업무 1:1 포함)은 상대 userId가 들어 있다. (`IS NOT NULL`은 전부 참이라 판별 못 함 — `!= 0`이 맞다.)

**소규모 그룹**(2026-06-09 추가): `directChatMemberUserId = 0 AND type = 1 AND activeMembersCount <= check_group_max_members`(기본 5). B2B 인바운드가 담당자 2~3명+본인 그룹방으로 들어오는 경우(예: 거래처 담당자 2명+본인 3인방)가 1:1 필터에서 새던 문제를 막는다. 대형 단톡은 같은 type 1이지만 인원이 수십~수백(검증: 79·156명) → 임계값으로 갈린다. 오픈챗(type4)·채널(type5)은 타입으로 제외. 그룹방은 `chatName`이 비면 발신자(본인 제외) `group_concat`으로 라벨을 만든다. **실증**: 확장 당일 거래처 담당자 그룹방·신규 소개 연결 그룹방을 즉시 포착(둘 다 1:1-only 필터에선 안 잡혔음).

## 노이즈 정리 (선택)

비즈니스 계정에는 업무 1:1(거래처·세무회계 등)과 마케팅·알림 계정(예: 각종 앱 알림)이 섞여 있다. config(`~/.config/kakao-read/config.json`)에 `"check_blocklist": ["토스","알라딘", ...]`(방 이름 부분일치)를 두면 `check` 목록에서 가려진다. 기본은 빈 목록(필터 없음). SMS blocklist와 같은 철학.
