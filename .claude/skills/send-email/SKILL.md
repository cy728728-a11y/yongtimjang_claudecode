---
name: send-email
description: 대화 내용이나 지정한 텍스트를 이메일로 발송. 기본 수신자는 cy728@daum.net. "이 내용 메일로 보내줘", "이메일 보내줘", "메일로 보내", "메일 발송", "이거 이메일로", "다음으로 보내줘" 등을 언급하면 자동 실행. 수신자·제목·첨부파일을 지정하면 그에 맞춰 발송.
allowed-tools: Bash, Write, Read
argument-hint: [받는사람(선택, 기본 cy728@daum.net) / 제목(선택) / 첨부(선택)]
---

# send-email

대화에서 나온 내용(또는 사용자가 지정한 텍스트/파일)을 SMTP로 이메일 발송하는 스킬.
발송 엔진은 `10-projects/이메일-자동화/send_email.py` (표준 라이브러리만 사용, 추가 설치 불필요).

## 전제
- 발신 자격증명은 워크스페이스 루트 `.env`의 `EMAIL_ADDRESS` / `EMAIL_APP_PASSWORD`에서 읽음 (git 제외).
  - `EMAIL_APP_PASSWORD`는 일반 비번이 아니라 Gmail 2단계 인증 후 발급한 16자리 앱 비밀번호.
  - 값이 없거나 잘못되면 스크립트가 안내 메시지 출력 → 사용자에게 발급 안내(https://myaccount.google.com/apppasswords).
- **기본 발신**: cy728728@gmail.com  ·  **기본 수신**: cy728@daum.net

## 수행 순서

### 1. 발송 대상 결정
- **본문(body)**: 사용자가 "이 내용"이라고 하면 → 직전 대화에서 사용자가 가리키는 내용(방금 만든 분석·정리·초안 등)을 본문으로 구성. 별도 텍스트/파일을 주면 그것을 사용.
- **수신자(to)**: 사용자가 지정 안 하면 **cy728@daum.net** (기본). 지정하면 그 주소.
- **제목(subject)**: 사용자가 주면 그대로. 없으면 내용 요지로 간결하게 생성 (예: `[무료강의 → 실전반 2기] 전환 극대화 준비 포인트`).
- **첨부(attach)**: 사용자가 파일을 지정하면 `--attach 경로` (여러 개 가능).

### 2. 본문을 UTF-8 파일로 저장
> PowerShell에서 한글을 CLI 인자로 직접 넘기면 인코딩이 깨질 수 있으므로 **반드시 `--body-file` 사용**.

`Write` 도구로 본문을 스크래치패드 또는 임시 `.txt`에 저장 (UTF-8 보장). 예:
`<scratchpad>/mail-body.txt`

### 3. 발송 실행
Windows(이 워크스페이스)에서는 venv 파이썬을 사용:

```bash
.venv/Scripts/python.exe "10-projects/이메일-자동화/send_email.py" \
  --to "cy728@daum.net" \
  --subject "제목" \
  --body-file "<본문파일 경로>"
```

- 다른 수신자: `--to 주소`
- 첨부: `--body-file ... --attach "파일경로"` (반복 가능)
- 발신 주소 변경: `--from 주소` (해당 도메인이 gmail/daum/naver면 자동, 아니면 `--smtp-host`/`--smtp-port` 지정)

### 4. 결과 보고
- 성공 시: `[성공] 발송 완료: <발신> → <수신>` 출력 → 사용자에게 수신자·제목 한 줄로 확인.
- 인증 실패(`SMTPAuthenticationError`): `.env`의 앱 비밀번호 확인/재발급 안내.
- 그 외 오류: 스크립트가 출력한 오류 메시지를 그대로 전달.

## 참고
- 지원 제공자(발신): Gmail / Daum / Naver (SMTP SSL 465). 발신 주소 도메인으로 자동 판별.
- 스크립트 상세: `10-projects/이메일-자동화/send_email.py`
- 자격증명 템플릿: `10-projects/이메일-자동화/.env.example`
