---
name: email-triage
description: 수집함 cy728728@gmail.com 에 모인 메일을 정리·검증·규칙수정한다. "이메일 정리해줘", "메일 정리", "메일 뭐 왔어", "확인필요 메일", "전달 잘 되고 있어", "전달 확인", "스팸에 뭐 갇혔어", "네이버 메일 가져와", "삭제 규칙 추가", "이 발신자 지워줘", "이건 남겨줘" 등 **수집함 메일 관리**를 언급하면 자동 실행. ※ 메일을 보내는 것은 send-email 스킬.
allowed-tools: Bash, Read, Edit, Write
argument-hint: [정리 | 확인 | 전달검증 | 스팸구조 | 규칙수정]
---

# email-triage

사업자 계정 17개(Gmail 16 + 네이버 `cy728@naver.com`)의 메일이 수집함
**`cy728728@gmail.com`** 한 곳에 모인다. 이 스킬은 그 수집함을 다룬다.

작업 디렉터리: `10-projects/이메일-자동화/`
접속은 **IMAP + 앱 비밀번호**(macOS 키체인). OAuth·gws 를 쓰지 않는다 — 만료가 없다.

## 명령 빠른 참조

| 하려는 것 | 명령 |
|---|---|
| 정리 미리보기 (삭제 안 함) | `python3 imap_triage.py` |
| 실제 정리 (휴지통, 30일 복구) | `python3 imap_triage.py --apply` |
| 네이버 메일 끌어오기 | `python3 naver_pull.py --apply` |
| 전달 실제 가동 검증 | `python3 verify_forwarding.py --days 7` |
| 스팸에 갇힌 전달 메일 구조 | `python3 rescue_spam.py --apply` |
| 전달 확인 링크 열기 | `python3 forward_codes.py --open` |
| 매일 자동 실행 리포트 | `cat logs/daily-report.md` |

전부 `10-projects/이메일-자동화/` 에서 실행. 미리보기가 기본이고 `--apply` 를 붙여야 실제로 바뀐다.

## 판정 규칙

`rules.py` 가 발신자·제목으로 DELETE / KEEP / UNKNOWN 을 가른다.
평가 순서가 중요하다 — **위가 아래를 이긴다**:

1. `DEL_FROM_ABSOLUTE` — 무조건 삭제 (알리익스프레스 전량)
2. `KEEP_FROM` / `KEEP_SUBJ` — 보안·세금·제재·금융·영수증·전달확인메일
3. `DEL_FROM` / `DEL_SUBJ` — 광고·뉴스레터·소셜알림·정산입금·주문현황
4. `DEL_SUBJ_BULK` — 상업 키워드(할인·특가·쿠폰). **List-Unsubscribe 가 있을 때만** 적용
5. 어디에도 안 걸리면 **UNKNOWN → 남김**

애매하면 남긴다. 오삭제가 놓침보다 나쁘다.

## 규칙을 고칠 때 (반드시 이 순서)

1. `rules.py` 수정
2. **회귀 검증** — 기존 판정이 의도치 않게 바뀌지 않았는지:
   ```bash
   python3 -c "
   import json,sys,collections; sys.path.insert(0,'.')
   from rules import judge2
   d=json.load(open('logs/<최근>-imap-preview.json'))
   print(collections.Counter(judge2(m) for m in d['delete']+d['keep']))"
   ```
3. 미리보기로 실제 영향 확인 — `python3 imap_triage.py`
4. **`./install.sh` 실행** ← 이걸 빼면 자동 실행에 반영 안 된다
5. 커밋

## 자동 실행

매일 **08:00** launchd (`com.yongtimjang.mailtriage`).
네이버 수집 → 판정 → `logs/daily-report.md` 에 한 줄.

**현재 `preview` 모드 — 아무것도 지우지 않는다.** 실삭제 전환:
```bash
sed -i '' 's|<string>preview</string>|<string>apply</string>|' \
  ~/Library/LaunchAgents/com.yongtimjang.mailtriage.plist
launchctl unload ~/Library/LaunchAgents/com.yongtimjang.mailtriage.plist
launchctl load   ~/Library/LaunchAgents/com.yongtimjang.mailtriage.plist
```

## 흔한 함정

| 증상 | 원인 · 해결 |
|---|---|
| 규칙 고쳤는데 자동 실행이 옛날대로 | `./install.sh` 안 돌림. 자동 실행은 저장소가 아니라 `~/.local/share/mail-triage` 를 읽는다 |
| launchd 가 `can't open input file` | macOS TCC — launchd 프로세스는 `~/Documents` 안의 파일을 못 연다(stat 은 됨). 런타임을 `~/.local/share` 에 두는 이유 |
| 건수가 이상하게 적다 | Gmail `resultSizeEstimate` 는 거짓말이다(201 vs 실제 6,059). 페이지네이션으로 직접 세라 |
| 전달 메일이 안 보인다 | 수집함 **스팸함**에 갇혔을 수 있다. `rescue_spam.py` 로 꺼낸다 |
| `UID_FETCH: Invalid arguments` | FETCH 스펙에 `UID` 를 명시 안 함. 네이버는 UID 를 응답에 안 실어준다 |
| UID MOVE 가 조용히 no-op | 응답 앞머리 첫 숫자는 **시퀀스 번호**다. `UID <n>` 을 파싱해야 한다 |
| 계정 설정 화면에 버튼이 없다 | **한국어 Gmail UI 에는 `전달 주소 추가` 가 없다.** 언어를 English (US) 로 바꾸면 나타난다 |

## 하지 않는 것

- **비밀번호 입력·계정 로그인** — 사용자가 직접 한다. 앱 비밀번호는 키체인에서 읽고 값을 출력하지 않는다
- **브라우저로 전달 설정 조작** — Google 보안 검증에 막힌다. 확인 메일이 발송되지 않고 조용히 실패한다
- **휴지통 비우기·영구 삭제** — 삭제는 항상 휴지통(30일 복구)까지만

## 관련 문서

- `10-projects/이메일-자동화/실행-가이드.md` — 설계·진행 현황·전환 절차
- `10-projects/이메일-자동화/계정-목록.md` — 계정 목록·삭제 규칙 원문
- `10-projects/이메일-자동화/전달설정-진행표.md` — 계정별 전달 설정 상태
