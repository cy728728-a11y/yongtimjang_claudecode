---
name: daily-note
description: 오늘 날짜의 Daily Note 생성 또는 열기. gws (Google Workspace CLI) 인증 시 Google Calendar 오늘 일정 포함. "오늘 daily note", "일일 노트", "daily note", "오늘 작성", "하루 기록" 등을 언급하면 자동 실행.
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
---

# daily-note

오늘 날짜의 Daily Note를 생성하거나 여는 스킬.

## 수행 작업

### 1. 오늘 날짜 확인

```bash
TODAY=$(date +%Y-%m-%d)
MONTH=$(date +%Y-%m)
DAY_NUM=$(date +%u)  # 1=월 ~ 7=일

case $DAY_NUM in
  1) WEEKDAY="월요일";;
  2) WEEKDAY="화요일";;
  3) WEEKDAY="수요일";;
  4) WEEKDAY="목요일";;
  5) WEEKDAY="금요일";;
  6) WEEKDAY="토요일";;
  7) WEEKDAY="일요일";;
esac
```

### 2. 파일 경로

```
./40-personal/41-daily/{MONTH}/{TODAY}.md
```

월별 폴더가 없으면 먼저 생성: `mkdir -p ./40-personal/41-daily/{MONTH}`

### 3. 파일이 있으면 → 열기

기존 내용 표시. 업데이트하고 싶은지 물어보기.

### 4. 파일이 없으면 → 템플릿으로 생성

템플릿: `./00-system/01-templates/daily-note-template.md`

변수 치환:
- `YYYY-MM-DD` → `{TODAY}`
- `(요일)` → `{WEEKDAY}`

### 5. (선택) Google Calendar 오늘 일정 추가

**도구**: `gws` (Google Workspace CLI). 설치/인증은 교육 과정에서 `gws auth login`으로 1회 세팅.
JSON 파싱은 Python3 내장 `json` 모듈 사용 (별도 설치 불필요).

```bash
if command -v gws &> /dev/null; then
  # 인증 안 되어 있으면 error 객체 반환 → Python에서 조용히 스킵
  EVENTS_JSON=$(gws calendar +agenda --today --format json 2>/dev/null)

  EVENTS_MD=$(echo "$EVENTS_JSON" | python3 - <<'PYEOF' 2>/dev/null
import json, sys
try:
    data = json.load(sys.stdin)
    for ev in data.get("items", []):
        start = ev.get("start", {})
        dt = start.get("dateTime") or start.get("date", "")
        # dateTime("2026-04-24T10:00:00+09:00") → "10:00"
        # date("2026-04-24", 종일 일정) → "종일"
        time_str = dt[11:16] if "T" in dt else "종일"
        summary = ev.get("summary", "(제목 없음)")
        print(f"- **{time_str}** {summary}")
except Exception:
    pass  # 인증 실패/error 응답 구조 → 조용히 스킵
PYEOF
)
fi
```

- `EVENTS_MD`를 daily note의 "오늘 일정" 섹션(템플릿에 없으면 상단에 신설)에 삽입
- `gws` 미설치 / 인증 실패 / Python3 미설치 → 단계 전체 스킵 (에러 메시지 X)
- 참고: `gws calendar +agenda --today`는 오늘 일정만 반환하는 read-only 헬퍼

### 5.5. (매월 1일) 원천세 신고 체크리스트 자동 삽입

`date +%d` 가 `01` 이면(=매월 1일), "오늘 할 일" 섹션에 3.3% 원천세 신고 체크리스트를 자동 추가한다.
(매월 1~10일 사이 처리해야 하는 정기 업무 — 놓치지 않게 1일에 리마인드)

```bash
if [ "$(date +%d)" = "01" ]; then
  PREV_MONTH_NUM=$(( 10#$(date +%m) - 1 )); [ "$PREV_MONTH_NUM" = "0" ] && PREV_MONTH_NUM=12
  # "오늘 할 일" 섹션(- [ ] 목록)에 아래 항목들을 삽입
fi
```

삽입할 체크리스트(전달 지급분 기준):

```markdown
- [ ] 📋 **원천세 신고** (기한: 이번달 10일) — 전달 급여 지급분 3.3% 신고
  - [ ] 급여 엑셀 준비 → "지난달 소득 신고해줘" (payroll-tax-filing 스킬 실행)
  - [ ] 홈택스 사업소득 원천세 신고 + 소득세 3% 납부
  - [ ] 지급명세서 PDF 다운로드 → 근거폴더 저장
  - [ ] 위택스 지방소득세 0.3% 신고·납부 + 영수증 출력
  - [ ] 간이지급명세서(사업소득) 제출 (월말까지)
```

- 이미 같은 항목이 있으면 중복 삽입하지 않는다.
- 신고 자체는 `payroll-tax-filing` 스킬이 담당. 여기선 할일 리마인드만.

### 6. 결과 보고

```
✅ Daily Note 생성: ./40-personal/41-daily/2026-04/2026-04-24.md
   요일: 목요일
   일정: 3건 (Google Calendar에서 가져옴)
```

## 팁

- 전날/내일 계산 (Mac/Linux 호환):
  ```bash
  # Mac
  YESTERDAY=$(date -v-1d +%Y-%m-%d)
  TOMORROW=$(date -v+1d +%Y-%m-%d)

  # Linux
  YESTERDAY=$(date -d "yesterday" +%Y-%m-%d)
  TOMORROW=$(date -d "tomorrow" +%Y-%m-%d)
  ```
  OS 체크: `[ "$(uname)" = "Darwin" ]`

- 경로는 항상 **상대 경로** (`./40-personal/...`). 워크스페이스 루트에서 실행 전제.
