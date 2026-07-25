# 윈도우 카톡 읽기 — 작동 원리·연구 기록 (2026-06)

윈도우 카카오톡(v26.4.0 기준)은 Mac과 저장 방식이 완전히 다르다. 이 문서는
무엇이 되고 무엇이 막혔는지, 왜 그런지, 어떤 방식을 택했는지 기록한다.

## 한눈에

- 윈도우 카톡은 대화를 **방마다 별도 파일** `chatLogs_{chatId}.edb`로 저장
  (`C:\Users\<user>\AppData\Local\Kakao\KakaoTalk\users\<해시폴더>\chat_data\`).
- 암호화는 **AES-256-CBC, 4096바이트 페이지 단위, 패딩 없음** (구버전 문서는 AES-128이라 했으나 v26은 256).
- **키는 파일(방)마다 다름**(per-file). 페이지별 IV는 비공개 도출식.
- → **오프라인 파일 복호화는 막힘.** 대신 **메모리 직독(Tier-2)** 으로 읽는다.

## 채택한 방식 (Tier-2: 메모리 페이지 직독)

카톡이 실행 중이면 복호화된 SQLite가 프로세스 메모리에 올라온다. 그래서:

1. `procdump64.exe -ma <KakaoTalk PID>` 로 프로세스 전체 메모리 덤프(~수백 MB).
2. 덤프에서 SQLite **table-leaf 페이지(첫 바이트 0x0d)** 를 직접 스캔·파싱.
3. `chatLogs` 레코드(21컬럼: logId·authorId·type·sendAt·message…)와
   `talkUser` 레코드(userId→nickName)를 추출.
4. authorId→이름 매핑 후 시각순 정렬 → 최근 메시지·검색 제공.

키·IV가 전혀 필요 없다 — 이미 복호화된 평문 페이지를 읽기 때문.
구현: `scripts/win/kakao_win.py` (의존성: pycryptodome 불필요, 표준 라이브러리만).

## Tier-1(키 기반 오프라인 복호화)을 왜 안 쓰나 — 연구 기록

키 회수까지는 성공했다. 끝까지 막힌 건 페이지별 IV다.

### 성공한 것
- **AES-256 확정**: AES-128 known-plaintext 공격은 전부 실패, AES-256으로 적중.
- **키 회수 성공**: 실행 중 메모리에 raw 32바이트 키가 상주. 검증 오라클
  (스키마 텍스트는 메모리=디스크 바이트 동일, 페이지 내 b≥1 블록은 IV 무관)로
  덤프를 훑어 키를 회수. CalendarDB 키로 스키마 블록 30/30 CBC 복호화 검증.
  도구: `scripts/win/keyscan.c`(AES128/256 enc/dec·MD5·base64 자체내장),
  `make_pairs2.py`(스키마영역 페어 생성).
- **키는 per-file**: DB마다 다른 키(3개 DB → 3개 키 확인).

### 막힌 것
- **per-page IV 도출식 미해독**: 키가 맞아도 페이지마다 IV가 별도 방식으로
  생성됨. 글로벌 IV·연속 CBC·페이지번호 기반 IV 모두 실패(340 페이지 중 5~6개만
  우연 적중). page0 블록2~7은 표준 CBC로 복호화되지만 블록1/page1+는 안 됨.
  → IV 생성 루틴은 KakaoTalk.exe Ghidra 분석 필요(미수행).
- per-file 키라 오프라인 전체 복호화도 결국 "메모리에 올라온 방"에 의존 →
  Tier-2 대비 이점이 제한적(다만 로드된 방의 *전체 history*는 가능했을 것).

결론: 비용 대비 효율로 Tier-2 채택. Tier-1 재개 시 출발점은 위 도구 + Ghidra.

## 누적 저장(accumulation) — 스냅샷 한계 완화 (2026-06 추가)

덤프는 '그 순간 RAM에 올라온 방'만 가진 스냅샷이라, 덤프마다 어떤 방은 사라지고
어떤 방은 새로 잡힌다(같은 시점에 본 방도 페이지 캐시 eviction으로 빠질 수 있음).
그래서 `sync`(=dump) 할 때마다 스캔 결과를 **영구 SQLite `~/.config/kakao-read/store.db`
에 병합(union)** 한다.

- 스키마: `messages(logId PK, sendAt, authorId, type, message, write_on_pc, prevLogId)`,
  `users(userId PK, name)`, `meta(key,value)`. logId는 카톡 전역 유일 → `INSERT OR IGNORE`.
- 읽기 명령(recent/rooms/read/search/users)은 단일 덤프가 아니라 **누적 DB 전체**를 읽는다
  (`load()` → `load_store()`). 덕분에 "어제 본 방이 오늘 덤프엔 없어 사라짐"이 해결된다.
- 한계는 남는다: **한 번도 열어 본 적 없는 방**은 메모리에 올라온 적이 없어 누적도 안 됨.
  → 그 방을 카톡에서 열고 스크롤한 뒤 `sync`.
- 본인 추정 own_id는 meta에 캐시(또는 `config.win_own_id` 우선).
- stdout을 UTF-8로 자동 reconfigure → cp949 콘솔에서도 한글 정상.

## 한계 (Tier-2)

- **한 번이라도 메모리에 올라온 것만 누적됨**: 누적 저장으로 과거에 본 방은 유지되나,
  열어 본 적 없는 방은 여전히 없다. 전체 history 아님.
- **방별 그룹핑은 prevLogId 사슬로 해결**: `chatLogs`에 chatId는 없지만 `prevLogId`
  (이전 메시지 id)가 있어 logId↔prevLogId 연결요소 = 방. 검증: 265건 중 254건이
  사슬 연결 → 11개 방. 다만 (a) 실제 방 이름이 아니라 참여자 기반 라벨,
  (b) 메모리에서 사슬이 끊기면 한 방이 여러 조각(참여자 같으면 병합).
- **오픈챗/비친구 발신자 이름 미해결**: 친구(작은 userId)는 talkUser로 매핑되나
  오픈챗 멤버(대형 ID)는 별도 테이블이라 숫자로 표시.
- **본인 표시**: write_on_pc가 신뢰도 낮음. `config.win_own_id`에 본인 userId를
  넣으면 "나"로 표시.

## 파일 위치·환경

- edb: `/mnt/c/Users/<user>/AppData/Local/Kakao/KakaoTalk/users/<40자hex>/chat_data/chatLogs_*.edb`
- DeviceInfo(참고): 레지스트리 `HKCU\Software\Kakao\KakaoTalk\DeviceInfo\<타임스탬프>`
  (sys_uuid·hdd_model·hdd_serial — 구버전 pragma 도출용. v26 키엔 직접 안 맞음)
- WSL에서 `/mnt/c`·`reg.exe`·`powershell.exe`·`python.exe`로 전부 접근 가능.

## 도구

런타임 본체: `scripts/win/kakao_win.py` — Tier-2 리더(dump/recent/rooms/read/search/users).

Tier-1 연구 산출물(참고용, 런타임 아님)은 `reference/windows-research/`에 보존:
- `keyscan.c` — 메모리에서 AES 키 회수(--selftest/--kpa/--kpa256).
- `carve_sqlite.py` — 덤프에서 복호화 SQLite carve(스키마 확인용).
- `make_pairs.py`·`make_pairs2.py`·`strkey_test.py`·`cipher_diag.py`·`poc_decrypt.py` — Tier-1 키/복호화 연구.
- `page_carve.py` — chatLogs 레코드 직접 파싱 PoC(kakao_win.py의 원형).
