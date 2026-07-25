# Notion API 연동 설정 가이드

> Claude Code에서 Notion을 사용하기 위한 초기 설정

---

## Step 1: Notion Integration 생성

### 1-1. Notion Developers 페이지 접속

브라우저에서 접속:
```
https://www.notion.so/my-integrations
```

또는 Notion 앱에서:
- 설정(Settings) → 내 연결(My connections) → 새 Integration 개발

### 1-2. 새 Integration 만들기

1. **"+ New integration"** 클릭

2. 기본 정보 입력:
   - **Name**: `Claude Code` (원하는 이름)
   - **Associated workspace**: 본인 워크스페이스 선택
   - **Type**: Internal (기본값)

3. **"Submit"** 클릭

### 1-3. 토큰 복사

생성 완료 후 화면에서:
- **Internal Integration Secret** 확인
- `ntn_` 또는 `secret_`으로 시작하는 긴 문자열
- **"Copy"** 버튼 클릭하여 복사

**주의**: 이 토큰은 한 번만 표시됩니다. 안전한 곳에 저장하세요.

---

## Step 2: 페이지에 Integration 연결

**중요**: Integration을 만들었다고 바로 접근되지 않습니다.
사용할 페이지마다 권한을 부여해야 합니다.

### 2-1. Notion 페이지 열기

Claude Code로 접근할 페이지 열기

### 2-2. Integration 연결

1. 페이지 우측 상단 **"..."** (더보기) 클릭
2. **"Connections"** 또는 **"연결"** 선택
3. 방금 만든 Integration 이름 검색 (`Claude Code`)
4. **"Confirm"** 클릭

### 2-3. 하위 페이지 자동 연결

상위 페이지에 연결하면 하위 페이지도 자동 접근 가능

**팁**: 작업할 최상위 페이지 하나에 연결하면 편함

---

## Step 3: Claude Code에서 토큰 설정

### 3-1. 환경변수 설정

터미널(Claude Code 실행 전)에서:

**Mac/Linux:**
```bash
export NOTION_TOKEN="ntn_xxxxxxxxxxxxx"
```

**Windows (PowerShell):**
```powershell
$env:NOTION_TOKEN="ntn_xxxxxxxxxxxxx"
```

**Windows (CMD):**
```cmd
set NOTION_TOKEN=ntn_xxxxxxxxxxxxx
```

### 3-2. 영구 설정 (선택)

매번 입력하기 싫다면:

**Mac/Linux** (~/.zshrc 또는 ~/.bashrc에 추가):
```bash
export NOTION_TOKEN="ntn_xxxxxxxxxxxxx"
```

**Windows**: 시스템 환경변수에 추가

---

## Step 4: 연결 테스트

Claude Code에서 테스트:

```
"Notion에서 '테스트'라는 단어로 검색해줘"
```

또는 직접 실행:
```bash
python3 .claude/skills/notion-handler/scripts/notion_api.py search --query "테스트"
```

---

## 페이지 ID 찾는 방법

Notion API 사용 시 페이지 ID가 필요합니다.

### 방법 1: URL에서 추출

Notion 페이지 URL:
```
https://www.notion.so/My-Page-Title-abc123def456...
                                    ^^^^^^^^^^^^^^^^
                                    이 부분이 페이지 ID
```

32자리 문자열 (하이픈 없이)

### 방법 2: "Copy link" 사용

1. 페이지에서 우클릭 또는 "..." 클릭
2. "Copy link" 선택
3. URL에서 ID 추출

---

## 자주 묻는 질문

### Q: "Unauthorized" 오류가 나요
**A**:
1. 토큰이 올바른지 확인
2. 해당 페이지에 Integration이 연결되었는지 확인

### Q: 페이지를 못 찾아요
**A**:
1. 페이지에 Integration 연결했는지 확인
2. 페이지 ID가 정확한지 확인

### Q: 토큰을 분실했어요
**A**:
1. https://www.notion.so/my-integrations 접속
2. 해당 Integration 선택
3. "Show" → "Regenerate" 클릭

---

## 보안 주의사항

- 토큰을 코드나 문서에 직접 입력 금지
- `.env` 파일은 `.gitignore`에 추가
- 토큰 유출 시 즉시 Regenerate

---

## 다음 단계

설정 완료 후 사용 가능한 기능:
- 데이터베이스 생성/조회
- 페이지 생성/수정
- 블록 추가
- 검색

자세한 사용법: `.claude/skills/notion-handler/SKILL.md` 참조
