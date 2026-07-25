---
name: kakao-read
description: 본인 카카오톡 대화·사진·파일을 로컬에서 직접 읽어 요약·할일 추출·검색·내용 파악. "카톡 읽어줘", "카톡 대화 정리", "카톡 요약", "카톡에서 X 찾아줘", "카톡 사진 내용 확인", "그 방 사진 뭐야", "카톡 파일 받아줘", "어제 그 방 대화 정리해줘", "카톡 체크"(지난 체크 이후 새 활동 1:1 방 메뉴형 수집), "최근 카톡 보여줘" 등 본인 카톡 내용을 가져올 때 자동 실행. Mac은 로컬 암호화 DB 직독(서버 접속 0). 윈도우는 실행 중 프로세스 메모리 직독(키 불필요). 메시지 보내기/온라인 LOCO는 범위 밖.
allowed-tools: Bash, Read
---

# kakao-read — 본인 카톡 로컬 읽기 (Mac · 윈도우)

**환경 분기 먼저 판단한다.**
- **Mac** (`~/Library/Containers/com.kakao.KakaoTalkMac` 존재): 아래 "Mac 카톡 오프라인 읽기" 전체 절차 사용. SQLCipher DB 직독.
- **윈도우 / WSL** (`/mnt/c/Users/*/AppData/Local/Kakao` 존재): 맨 아래 "## 윈도우 카톡 읽기 (Tier-2)" 절 사용. 메모리 덤프 직독. Mac 절차(ioreg·sqlcipher·NTChatRoom)는 윈도우에서 동작 안 함.

# Mac 카톡 오프라인 읽기

Mac 카카오톡 앱이 디스크에 저장하는 암호화 DB(SQLCipher)를 복호화해, **본인 대화를 텍스트로 직접 읽는다.** 화면 캡처 없이, 서버 접속 없이, 데스크톱 앱을 건드리지 않고 전체 히스토리를 읽는다.

## 범위 (중요 — 이 선을 넘지 않는다)

- **읽기 전용 · 본인 기기의 본인 계정만.** 자기 Mac에 로그인된 자기 카톡 데이터를 읽는다.
- **텍스트(chats/read/search)**: 서버 접속 0, 완전 오프라인. 로컬 암호화 DB 직독.
- **사진/파일(media)**: 메시지 메타데이터에 든 카톡 **CDN 서명URL로 평문 다운로드** → 사진은 비전, 텍스트 파일은 그대로 내용 파악. 이 부분만 네트워크(CDN GET)를 쓰지만 **LOCO/로그인이 아니라 단순 파일 GET**이라 세션 충돌·밴 위험 없음. 단 URL에 만료가 있어 **최근 미디어만** 받힌다(오래된 건 링크 만료).
- **하지 않는 것**: 메시지 보내기/삭제/수정, 온라인 LOCO 로그인·watch, 남의 기기·계정. 이것들은 데스크톱 앱 세션을 밀어내거나(로그아웃) 계정 밴 위험이 있어 다루지 않는다.
- 교육(AX 캠프 등)에서 시연·전달할 때도 "각자 본인 Mac·본인 카톡"이 전제다.

## 전제

- macOS + 카카오톡 데스크톱 앱(로그인 상태로 한 번 이상 사용)
- `sqlcipher` 설치: `brew install sqlcipher`
- 최초 1회 `setup`으로 본인 userId를 등록·캐시 (`~/.config/kakao-read/config.json` — 워크스페이스 밖 HOME에 저장, git 추적 안 됨). userId를 몰라도 됨 — 26.x는 plist 해시에서 자동 역산

## 사용법

실행 전 워크스페이스 루트에서 `cd .claude/skills/kakao-read/scripts` 후 아래 (또는 명령에 전체 경로 사용).

```bash
python3 kakao_read.py setup             # 최초 1회: userId 자동 역산·캐시 (userId 몰라도 됨)
python3 kakao_read.py chats 20          # 최근 방 20개 (chatId·type·인원·이름)
python3 kakao_read.py read <chatId> 50  # 방 메시지 50개 (시간 오름차순)
python3 kakao_read.py search "키워드" 30 # 전체 메시지 검색
python3 kakao_read.py media <chatId> 5  # 방의 최근 미디어 5개 다운로드(사진/파일)
python3 kakao_read.py check             # '지난 체크 이후' 새 활동 방 목록 (1:1 + 소규모 그룹 ≤5명, 메뉴형 수집)
python3 kakao_read.py since <chatId>    # 그 방의 '지난 체크 이후' 메시지만 (창 기준)
python3 kakao_read.py mark              # 지금을 '마지막 체크 시각'으로 저장 (창 전진)
python3 kakao_read.py tables            # 스키마 확인
```

## 카톡 체크 워크플로 (on-demand 메뉴형 수집)

"카톡 체크"는 **놓친 대화를 빠짐없이 훑는** 수집 동선. 정보 수집 파이프라인의 카톡 채널(의도·메뉴형, on-demand)을 구현한다. **1:1 + 소규모 그룹방(type 1, 인원 5명 이하)**을 본다 — B2B 인바운드가 담당자 2~3명+본인 그룹방으로 들어오는 경우를 놓치지 않기 위함. 캠프 단톡(수십~수백명)·오픈챗(type4)·채널(type5)은 인원수/타입으로 자동 제외. 임계값은 config `check_group_max_members`(기본 5)로 조정. 그룹방 이름이 비면 발신자(본인 제외) 집계로 라벨 보강.

1. **`check`** — '지난 체크 이후'(마지막 `mark` 시각, 없으면 최근 2일) 새 활동이 있는 방을 `chatId | 이름 | 마지막시각 | 마지막메시지 미리보기`로 나열. 며칠 건너뛰어도 그 사이 활동한 방이 전부 떠서 빠짐 없음(창 기준).
2. **목록을 사용자에게 메뉴로 제시** — 시스템이 후보를 차려주고 사용자가 고른다(proposal-first). 어떤 방을 읽을지 고르게 한다.
3. **고른 방마다 `since <chatId>`** — 그 방의 '지난 체크 이후' 메시지만 시간순으로. (전체 히스토리가 아니라 새 창만 → 가볍고 빠짐 0). 미디어는 표준 워크플로대로 필요시 `media`.
4. **업무 후보를 `00-inbox/raw/`에 떨군다** (아래 "라우팅 연결고리" 참조). 읽은 창에서 업무 정보(약속·할일·문의)가 보이면 raw 파일로 떨군다. **여기서 직접 todo/캘린더에 쓰지 않는다** — 카톡 체크는 *수집 계층*이고, 분류·라우팅은 inbox-triage 한 곳이 전담한다.
5. **inbox-triage 체이닝** — raw를 하나라도 떨궜으면 이어서 `inbox-triage`를 호출해 라우팅한다. 라우팅 proposal(어디로 보낼지 승인)은 거기서 한 번만 받는다. (step 2의 "어느 방 읽을지"는 수집 proposal, 이건 라우팅 proposal — 서로 다른 게이트.)
6. **`mark`** — 체크가 끝나면 실행해 창을 전진시킨다(다음 `check`의 시작점). **읽기를 마친 뒤에만** 호출.

**raw 파일 떨구기 규약**: 읽은 창에 업무 신호(약속·할일·문의·회신요망)가 있을 때만, **읽은 방 1개당 raw 1개**를 `00-inbox/raw/`에 떨군다(잡담·안부 제외). 파일명·frontmatter 포맷(`source: kakao-check`/`processed: false`), 방 판별자(1:1 = `directChatMemberUserId != 0` / 소규모 그룹 = `type=1 AND activeMembersCount<=5`), 노이즈 blocklist 상세는 **`reference/kakao-check-routing.md` 참조.** 라우팅·마킹은 inbox-triage가 전담 — 카톡 체크는 떨구고 손 뗀다.

## 표준 워크플로 (미디어 처리 판단을 포함한다)

1. `chats`로 chatId 확인.
2. `read <chatId>`로 대화를 가져온다. 사진·파일은 본문 흐름 안에 **`[사진]` · `[파일] 이름` · `[동영상]`** 으로 인라인 표시되고, 미디어가 있으면 출력 끝에 안내가 뜬다.
3. **미디어 처리 필요 판단 (이 단계 생략 금지).** `read` 결과에 `[사진]`/`[파일]`/`[동영상]`이 있으면, 그 내용이 이번 요청에 필요한지 본다:
   - 요약·할일 추출·"무슨 내용/얘기야"처럼 **맥락이 필요하면** → `media <chatId> <N>`으로 받아, 출력된 각 경로를 **Read 도구로 열어** 내용 파악(사진=비전으로 이미지 속 글자까지, 텍스트 파일=본문 그대로). 파악한 내용을 대화 정리에 **녹여서** 제시(예: "[사진]" 자리에 '세미나 WiFi 안내(PW: …)'처럼).
   - 텍스트만으로 충분하거나 미디어가 요청과 무관하면 → 받지 않는다(불필요한 CDN 접속·시간 절약).
   - 애매하면 한 번만 묻는다: "사진 N장·파일 M개도 내용 확인할까요?"
4. **핵심 요약 + 할 일 추출** (사용자 선호 출력 형태).

받히는 미디어: 사진(2,27)·동영상(3)·음성(12)·GIF(14)·파일(18). 동영상·대용량은 시간이 걸릴 수 있음. **최근 것만**(서명URL 만료 — "실패(만료)"로 뜨면 오래된 미디어).

## setup — userId 등록

`setup`은 userId를 구해 캐시한다. 버전별로 추출 경로가 다르지만 **둘 다 userId를 몰라도 자동으로 된다.**

```bash
python3 kakao_read.py setup             # 자동 (userId 몰라도 됨)
python3 kakao_read.py setup <userId>    # userId를 알면 즉시 등록(역산 생략)
```

- **25.x**: `Cache.db`의 `talk-user-id` 헤더에서 즉시 추출.
- **26.x (26.5.0 확인)**: 헤더가 사라지고 평문 userId도 디스크 어디에도 없다. 대신 카톡이 일부 plist 키 이름을 `DESIGNATEDFRIENDSREVISION:<SHA-512(str(userId)) 128hex>` 형태로 저장한다. 이 해시를 **brute force 역산**해 userId를 복구한다(`recover_user_id_from_plist`). SHA-512는 PBKDF2보다 ~10만 배 빨라 멀티코어로 보통 **수 초~수 분**(7자리 ~1초, 9자리 ~2분, 최악 10자리 ~17분). plist는 캐시와 달리 항상 디스크에 있어 안정적이다.

어느 경로든 찾은 userId는 `derive_db_name(userId, uuid)`가 **디스크 DB 파일명과 일치하는지 오라클 검증**한 뒤에만 캐시한다(100% 정답 확인). 한 번 캐시되면 이후 `chats`/`read`/`search`는 바로 동작한다.

> **다른 기기로 옮길 때**: userId를 아는 기기의 `~/.config/kakao-read/config.json`에서 `user_id`를 복사해 `setup <그 값>` 하면 역산 없이 즉시 검증·등록된다. 임시 사용은 `KT_USER_ID=<숫자> python3 kakao_read.py chats`.

> 키 도출·복호화 알고리즘은 25.x·26.x 동일(파일명·키 = UUID+userId PBKDF2). 버전마다 바뀐 건 "userId를 어디서 얻느냐"뿐.

## 작동 원리 (교육용)

네 단계. 상세·왜 그런지·흔한 함정은 `reference/how-it-works.md` 참조.

1. **UUID** = `ioreg`의 IOPlatformUUID (기기 고유)
2. **userId** = 계정 고유 정수. 25.x는 Cache.db `talk-user-id` 헤더, **26.x는 plist 키에 박힌 SHA-512(userId) 해시를 brute force 역산**. 둘 다 자동(userId 몰라도 됨), 찾은 값은 디스크 DB 파일명으로 오라클 검증
3. **DB 파일명·SQLCipher 키** = UUID+userId를 정해진 포맷으로 엮어 PBKDF2-HMAC-SHA256(100,000회, 128B) 도출
4. **열기** = `PRAGMA key` 먼저 → `PRAGMA cipher_compatibility=3` 나중 (순서가 바뀌면 실패)

테이블: `NTChatRoom`(방) / `NTChatMessage`(메시지) / `NTUser`(사람).

## 자주 막히는 곳

- `file is not a database` → PRAGMA 순서(key 먼저) 또는 userId/UUID 불일치. 스크립트는 순서를 지킨다.
- 도출 파일명이 디스크에 없음 → userId가 이 기기 계정과 안 맞음. `setup` 다시(자동 역산이 맞는 값을 찾아 검증 통과).
- 26.x `setup`이 "자동 추출 실패"로 끝남 → plist에 userId 해시가 없음(카톡 미로그인 등). 로그인 상태 확인 후 재시도. userId를 알면 `setup <userId>`.
- brute force가 오래 걸림 → userId가 큰 값(최근 가입, 10자리). 멀티코어로도 최대 ~17분. userId를 알면 `setup <userId>`로 즉시.
- 그룹방 이름이 `(이름없음)` → `chatName`이 비고 멤버명 집계가 필요한 방. chatId로 `read`는 정상 동작.

## 백업 경로

DB 접근이 막힌 환경이면 화면 기반 cua 백그라운드 캡처(trycua)로 읽는다.

---

# 윈도우 카톡 읽기 (Tier-2)

윈도우 카톡(v26.x)은 Mac과 완전히 다르다. 방마다 AES-256-CBC로 암호화한 `chatLogs_{chatId}.edb`로 저장하고, **키는 파일별·페이지별 IV는 비공개**라 오프라인 파일 복호화는 막혀 있다. 대신 **카톡이 실행 중이면 복호화된 SQLite가 프로세스 메모리에 있으므로, 메모리를 덤프해 직접 파싱**한다. 키가 필요 없다. 덤프는 그 순간 스냅샷이라 매번 결과가 달라지므로, **`sync` 할 때마다 누적 저장소(`store.db`)에 병합**해 커버리지를 시간에 따라 쌓는다. (원리·연구기록: `reference/how-it-works-windows.md`)

## 범위·전제

- **읽기 전용 · 본인 기기의 본인 계정만.** 본인 PC에 로그인된 본인 카톡.
- 메모리 덤프는 본인 프로세스를 **읽기만** 한다(수정·네트워크·LOCO 없음).
- **전제**: 카톡 실행 중 + 읽고 싶은 대화방을 열어 본 적이 있어야 메모리에 올라온다.
- procdump64.exe 필요(설치형 아님). **`sync` 첫 실행 시 Sysinternals에서 자동 다운로드**되어 `~/.config/kakao-read/`에 캐시된다(클론 사용자 수동 설치 불필요). 자동이 막히면 `https://download.sysinternals.com/files/Procdump.zip` 받아 `config.procdump_path` 지정 또는 PATH에.
- **클론 후 첫 실행**: `python kakao_win.py doctor` 로 환경·의존성·데이터 상태를 한 번에 점검(파이썬·카톡 실행 여부·procdump·누적 저장소).
- **WSL·네이티브 윈도우 양쪽 동작**: 스크립트가 `/mnt/c` 유무로 환경을 자동 감지해 경로를 처리한다(WSL=`/mnt/c/...`, 네이티브=`C:\...`). 네이티브에선 `python3` 대신 `python` 일 수 있음. 의존성은 표준 라이브러리뿐(다운로드·DB·압축해제 모두 stdlib).

## 사용법

실행 전 워크스페이스 루트에서 `cd .claude/skills/kakao-read/scripts/win` 후 아래 (표준 라이브러리만, 네이티브는 `python`).

```bash
python3 kakao_win.py doctor          # 자가진단: 환경·procdump·카톡 실행·저장소 상태 (클론 후 첫 실행)
python3 kakao_win.py sync            # KakaoTalk 메모리 덤프 → 누적 저장소에 병합 (=dump, procdump 자동 다운로드)
python3 kakao_win.py stats           # 누적 저장소 현황 (총 메시지·사용자·방·기간)
python3 kakao_win.py recent 20       # 최근 메시지 20개 (시각|발신자|내용)
python3 kakao_win.py rooms           # 방 목록 (참여자 이름으로 라벨)
python3 kakao_win.py read <번호|이름> 40   # 특정 방 대화 (시간순)
python3 kakao_win.py search "키워드" 30
python3 kakao_win.py users           # id→이름 매핑 수 확인 (디버그)
```

표준 워크플로: `sync` 1회 → `rooms`로 방 확인 → `read <번호>`로 그 방 대화. 새 대화를 보려면 카톡에서 그 방을 연 뒤 다시 `sync`.

**누적 저장(핵심)**: 메모리 덤프는 '지금 카톡이 RAM에 띄워둔 방'만 가진 **스냅샷**이라, 덤프마다 어떤 방은 사라지고 어떤 방은 새로 잡힌다. 그래서 `sync` 할 때마다 결과를 `~/.config/kakao-read/store.db`에 **병합(union)** 한다. 읽기 명령(`recent`/`rooms`/`read`/`search`)은 이 누적 DB에서 조회하므로 **한 번 잡힌 방·메시지는 다시 사라지지 않고**, 평소 카톡을 쓰며 가끔 `sync`만 돌리면 활성 대화가 점점 다 쌓인다. (단, **한 번도 안 열어 본 방**은 메모리에 올라온 적이 없어 여전히 없다 → 카톡에서 그 방을 열고 스크롤한 뒤 `sync`.)

**방 구분 원리**: `chatLogs`에 chatId는 없지만 `prevLogId`(이전 메시지 id)가 있어, logId↔prevLogId 사슬의 연결요소 = 방. 참여자(본인 제외 authorId)→이름으로 방 라벨을 만든다(1:1은 상대 이름, 그룹은 "A 외 N명").

## 한계 (Mac과 다른 점 — 반드시 인지)

- **한 번이라도 메모리에 올라온 것만** 쌓인다. `sync`로 누적되므로 과거에 본 방은 사라지지 않지만, 카톡에서 **한 번도 열어 본 적 없는 방**은 여전히 없다 → 열고 스크롤 후 `sync`.
- **방 라벨은 참여자 기반**(실제 방 이름 아님). 같은 사슬이 메모리에서 끊기면 한 방이 여러 조각으로 보일 수 있음(참여자 같으면 병합함).
- **오픈챗/비친구 발신자**는 이름 대신 숫자 ID로 표시(친구는 이름 매핑됨).
- **본인 메시지** "나" 표시는 write_on_pc로 자동 추정(불확실 시 `config.win_own_id`에 본인 userId 지정).
- 사진/파일 내용 파악은 미지원(인라인 `[사진]`/`[파일] 이름`까지만. Mac은 CDN 다운로드 지원).

## 자주 막히는 곳

- "저장된 데이터 없음" → 먼저 `sync`. 카톡 실행 + 방 하나 열어두기.
- "KakaoTalk 프로세스를 못 찾음" → 카톡이 안 떠 있음.
- procdump 권한 오류 → 프롬프트에서 `!` 로 직접 실행하거나 관리자 권한 필요할 수 있음.
- 특정 방이 안 보인다 / 최근 메시지가 적다 → 그 방을 카톡에서 열어 스크롤한 뒤 다시 `sync`(페이지 캐시에 올라온 뒤 누적 DB에 병합됨).
- **sync 해도 신규 +0이 반복 / 덤프 크기가 매번 똑같다** → procdump가 기존 파일이 있으면 `kt_kakao-1.dmp`처럼 번호를 붙여 새로 만드는데, 옛 `kt_kakao.dmp`만 읽으면 갱신이 안 됨. (2026-06 수정: `cmd_dump`가 덤프 전에 기존 `kt_kakao*.dmp`를 모두 지워 항상 새 덤프를 보장.)
- **인코딩**: 스크립트가 stdout을 UTF-8로 자동 전환하므로 콘솔이 cp949여도 한글 정상.
