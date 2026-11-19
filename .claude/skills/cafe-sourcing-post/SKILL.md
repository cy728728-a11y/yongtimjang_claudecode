---
name: cafe-sourcing-post
description: 셀러라이프 '전체 카테고리 엑셀' zip 을 받아 구글 드라이브에 올리고 네이버 카페(하우제로) 실전반 소통방에 'YYYY년 M월 D일 최신화' 글로 링크를 자동 게시한다. 맥북이 매주 월요일 09:00 에 알아서 돌리고, 새 데이터가 없으면 아무것도 안 한다. "카페 자료 올려줘", "소싱데이터 최신화 올려", "실전반 소통방 자료 올려", "셀러라이프 자료 카페에", "카페 자료 지금 올려" 등을 언급하면 자동 실행.
---

# 카페 소싱데이터 자동 게시

설계: `10-projects/18-카페-소싱데이터-자동게시/설계.md` · 계획: 같은 폴더 `계획.md`

## 지금 바로 한 번 올리기 ("지금 올려")

```bash
.venv/Scripts/python .claude/skills/cafe-sourcing-post/scripts/run.py            # 윈도우
.venv/bin/python .claude/skills/cafe-sourcing-post/scripts/run.py                # 맥북
```
- `--dry-run` : 받기까지만 하고, 올릴 내용만 보여 준다
- `--skip-download <zip>` : 이미 받은 zip 으로 진행
- 결과: `posted`(올림) / `skipped`(이미 올린 데이터 — 셀러라이프가 아직 새로 안 냄) / `failed`(메일로 사유·해결법·붙여넣을 제목·링크 전송)

## 하는 일

1. `sellerlife-keyword/scripts/download.py` 로 전체 카테고리 zip 받기(크롬 창이 1~2분 떴다 닫힘 — 창 없는 방식은 구글이 로그인을 막음)
2. zip 안 날짜(= 데이터 날짜)로 이미 올린 회차인지 확인 → 올렸으면 끝
3. **rclone** 으로 드라이브 `cy728728@gmail.com` 폴더(`1tHxVObirOwYoxAZAcslA24mV_VctmJXB`)에 `SellarSourcingAll_<날짜>.zip` 업로드, 링크 공개. 게시 후 같은 폴더에 `posted_SellarSourcingAll_<날짜>.txt`(글 주소)를 남겨 어느 PC에서든 중복 게시를 막는다
4. 네이버 공식 카페 API 로 실전반 소통방에 게시(제목 = 게시한 날 `YYYY년 M월 D일 최신화`, 본문 = 링크)
5. 드라이브의 `SellarSourcingAll_*.zip` 최근 3개만 남기고 휴지통
6. 본인 메일로 완료/실패 알림

회차 기록: `~/.eroom/cafe-sourcing-state.json` · 네이버 설정·토큰: `~/.eroom/naver-cafe.json` (둘 다 저장소 밖)

## 최초 설정(컴퓨터마다 1회, 사람이 해야 하는 것)

1. **셀러라이프 로그인**: `python .claude/skills/sellerlife-keyword/scripts/download.py --setup --wait 600`
2. **구글 드라이브(rclone)**: rclone 설치(윈도우 `winget install Rclone.Rclone`, 맥 `brew install rclone`) → `rclone config create gdrive drive scope=drive` → 뜨는 브라우저에서 `cy728728@gmail.com` 허용
   - rclone 은 구글 정식 승인 앱이라 로그인이 7일마다 풀리지 않는다(2026-11-19 gws 프로젝트를 '프로덕션 게시'하려 했으나 버튼이 막혀 rclone 으로 교체)
   - 풀리면: `rclone config reconnect gdrive:`
   - 설정 파일(접속 열쇠 포함): 윈도우 `%APPDATA%\rclone\rclone.conf`, 맥 `~/.config/rclone/rclone.conf` — 맥북엔 이 파일을 복사해도 된다
   - **알림 메일은 여전히 gws**(`gws auth login`, cy728728). gws 는 테스트 모드라 7일마다 풀려 메일이 안 갈 수 있다 → 그때는 맥북 화면 알림 + `~/.eroom/cafe-sourcing-LAST-FAILURE.txt` 로 남는다. 게시 자체에는 영향 없음
3. **네이버 허락**:
   - developers.naver.com → 애플리케이션 등록: 사용 API '네이버 로그인' + '카페' 권한, 환경 'PC 웹', Callback URL `http://localhost:8765/callback`
   - 카페 실전반 소통방 게시판 주소에서 카페 번호(clubid)·게시판 번호(menuid) 확인
   - `python .claude/skills/cafe-sourcing-post/scripts/cafe_setup.py --client-id … --client-secret … --club-id … --menu-id …` → 뜨는 주소에서 네이버 로그인·동의
   - 허락이 만료되면(실패 메일이 알려 줌) 인자 없이 `cafe_setup.py` 만 다시 실행

## 맥북 이전 체크리스트

1. 워크스페이스 동기화(git pull) 후 `.venv` 에 requests·selenium·openpyxl 있는지 확인
2. 위 '최초 설정' 1~3을 맥북에서 진행 (또는 윈도우의 `~/.eroom/naver-cafe.json`·`rclone.conf` 를 맥북으로 복사하면 2·3번 생략)
3. 윈도우의 `~/.eroom/cafe-sourcing-state.json` 을 맥북 `~/.eroom/` 로 복사(선택 — 없어도 드라이브의 posted_ 표시 파일로 중복 게시는 막힌다)
4. `which rclone gws node` 로 프로그램 위치 확인 → `/opt/homebrew/bin`·`/usr/local/bin` 이 아니면(예: nvm) 그 폴더를 plist 의 PATH 맨 앞에 추가
5. 예약 등록:
   ```bash
   W="$(pwd)"   # 워크스페이스 최상위에서
   sed "s#__WORKSPACE__#$W#g" .claude/skills/cafe-sourcing-post/launchd/com.yongteam.cafe-sourcing.plist > ~/Library/LaunchAgents/com.yongteam.cafe-sourcing.plist
   plutil -lint ~/Library/LaunchAgents/com.yongteam.cafe-sourcing.plist
   launchctl load ~/Library/LaunchAgents/com.yongteam.cafe-sourcing.plist
   launchctl list | grep cafe-sourcing
   ```
6. `.venv/bin/python .claude/skills/cafe-sourcing-post/scripts/run.py --dry-run` 로 마무리 확인
7. 첫 예약 실행 다음 날 `/tmp/cafe-sourcing.log` 에 키체인 오류가 없는지 확인 — **plist 에 `GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND=file` 을 넣지 말 것**(맥북 gws 로그인 삭제 사고 전력)
8. 예약은 맥북 한 대에만 건다. 다른 PC 에서 '지금 올려'를 해도 드라이브 파일 설명란의 `게시: <글주소>` 를 보고 중복 게시를 막지만, 예약까지 두 대에 걸 이유는 없다

## 실패했을 때

- 메일 제목 `[카페 자료] 자동 게시 실패 — <단계>` 에 해결법이 들어 있다. **카페에 손으로 올리지 말고** 해결법대로 한 뒤 "지금 올려" — 손으로 올리면 다음 실행이 같은 글을 또 올린다
- 메일조차 못 보냈으면(구글 로그인 만료 등) `~/.eroom/cafe-sourcing-LAST-FAILURE.txt` 에 내용이 남고, 맥북 화면에 알림이 뜬다

## 테스트

```bash
.venv/Scripts/python -m pytest .claude/skills/cafe-sourcing-post/tests -q
```
