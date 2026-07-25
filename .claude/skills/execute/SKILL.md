---
name: execute
description: 매니페스트의 병렬 작업을 워커 에이전트로 실행. "작업 실행", "워커 실행", "병렬 처리 시작", "execute tasks" 등을 언급하면 자동 실행. /decompose 후 사용.
argument-hint: [all 또는 작업번호]
context: fork
allowed-tools:
  - Read
  - Write
  - Task
  - Glob
---

**실행 요청**: $ARGUMENTS

---

## 실행 프로세스

### 1단계: 매니페스트 찾기

현재 디렉토리 또는 최근 작업한 프로젝트에서 `_parallel/_manifest.md` 파일을 찾으세요.

검색 순서:
1. 현재 디렉토리의 `_parallel/_manifest.md`
2. 최근 `/decompose` 실행 경로

매니페스트를 찾지 못하면:
> "_parallel/_manifest.md 파일을 찾을 수 없습니다. 먼저 /decompose를 실행해주세요."

### 2단계: 매니페스트 파싱

매니페스트에서 작업 목록을 읽으세요:

```
## 작업 목록

| # | 작업 | 파일 | 워커 | 상태 |
|---|------|------|------|------|
| 1 | [작업1] | `01-xxx.md` | research-worker | pending |
| 2 | [작업2] | `02-xxx.md` | analysis-worker | pending |
```

### 3단계: 실행 대상 결정

**인자 해석**:
- `all` → 모든 pending 상태 작업 실행
- `1` → 작업 번호 1만 실행
- `1,2,3` → 작업 번호 1, 2, 3 실행
- 빈 값 → 사용자에게 선택 요청

### 4단계: 워커 에이전트 실행

각 작업에 대해 Task tool로 해당 워커 에이전트를 호출:

```
Task tool 호출:
- subagent_type: [워커 이름] (research-worker, analysis-worker, etc.)
- prompt: 매니페스트의 세션 프롬프트 + 저장 경로 지시
```

**워커 매핑**:
| 워커 | subagent_type |
|------|---------------|
| research-worker | research-worker |
| analysis-worker | analysis-worker |
| content-worker | content-worker |
| design-worker | design-worker |
| development-worker | development-worker |

### 5단계: 결과 확인

각 워커 실행 후:
1. 결과 파일 존재 확인 (`_parallel/XX-xxx.md`)
2. "메인 세션 전달 사항" 섹션 포함 확인
3. 매니페스트 상태 업데이트 (pending → completed)

### 6단계: 완료 보고

```
## 실행 완료

| # | 작업 | 워커 | 결과 | 상태 |
|---|------|------|------|------|
| 1 | [작업1] | research-worker | `01-xxx.md` | completed |
| 2 | [작업2] | analysis-worker | `02-xxx.md` | completed |

**다음 단계**: /integrate 실행하여 결과 통합
```

---

## 병렬 vs 순차 실행

**병렬 실행** (독립 작업):
- 의존성 없는 작업들은 동시에 Task tool 호출
- 예: 리서치 3개가 모두 독립적 → 병렬 실행

**순차 실행** (의존 작업):
- 선행 작업 완료 후 후행 작업 실행
- 매니페스트의 의존성 정보 확인

---

## 에러 처리

**워커 실행 실패 시**:
1. 에러 메시지 기록
2. 해당 작업 상태를 `failed`로 업데이트
3. 다른 독립 작업은 계속 실행
4. 완료 보고에 실패 작업 명시

**매니페스트 형식 오류 시**:
1. 파싱 가능한 부분만 처리
2. 오류 내용 사용자에게 보고

---

## 예시

### 입력: `/execute all`

```
## 실행 시작

매니페스트: `10-projects/[프로젝트명]/_parallel/_manifest.md`

### 실행 대상
- [1] Founder 소개 콘텐츠 작성 (content-worker) - pending
- [2] 증거 자료 목록화 (research-worker) - pending
- [3] 안내 메시지 초안 (content-worker) - pending

### 실행 중...

[1] content-worker 실행 중...
    → 완료: `_parallel/01-founder-intro.md`

[2] research-worker 실행 중...
    → 완료: `_parallel/02-evidence-list.md`

[3] content-worker 실행 중...
    → 완료: `_parallel/03-announcement-drafts.md`

## 실행 완료

| # | 작업 | 결과 |
|---|------|------|
| 1 | Founder 소개 | completed |
| 2 | 증거 자료 | completed |
| 3 | 안내 메시지 | completed |

**다음 단계**: /integrate 실행하여 결과 통합
```

### 입력: `/execute 2`

```
## 실행 시작

매니페스트: `.../_parallel/_manifest.md`

### 실행 대상
- [2] 증거 자료 목록화 (research-worker) - pending

### 실행 중...

[2] research-worker 실행 중...
    → 완료: `_parallel/02-evidence-list.md`

## 실행 완료

**남은 작업**: 1, 3 (pending)
**다음 단계**: /execute all 또는 /integrate
```

---

## 주의사항

1. **매니페스트 필수**: `/decompose`를 먼저 실행해야 함
2. **워커 등록 필요**: `~/.claude/agents/`에 워커 파일이 있어야 함
3. **저장 경로 확인**: `_parallel/` 폴더가 쓰기 가능해야 함
4. **실행 시간**: 각 워커는 독립 세션으로 시간이 소요됨
